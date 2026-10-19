//! Outline-driven monochrome dropout control.
//!
//! Hersch (1993) §7 and TrueType SCANTYPE rules 5/6 select the pixel nearest
//! an interior span's midpoint in both scan directions. We include stubs, as in
//! SCANTYPE 4. Project hypothesis: adapt those rules to the existing coverage
//! image by rescuing subpixel interior spans with no delivered ink. This is not
//! full TrueType center-fill scan conversion. Raw coverage is never modified.
use crate::{
    fail,
    probe::{self, FittedCommand, RasterOutput},
    Config, Error,
};

const MAX_WORK: usize = 4_194_304;
#[derive(Clone, Copy, Default)]
struct Point {
    x: f64,
    y: f64,
}
impl Point {
    fn new(x: f32, y: f32) -> Self {
        Self {
            x: f64::from(x),
            y: -f64::from(y),
        }
    }
    fn along(self, vertical: bool) -> f64 {
        if vertical {
            self.y
        } else {
            self.x
        }
    }
    fn scan(self, vertical: bool) -> f64 {
        if vertical {
            self.x
        } else {
            self.y
        }
    }
}
#[derive(Clone)]
struct Segment {
    p: [Point; 4],
    degree: usize,
}
impl Segment {
    fn at(&self, t: f64) -> Point {
        let mut p = self.p;
        for n in (1..=self.degree).rev() {
            for i in 0..n {
                p[i].x = p[i].x * (1.0 - t) + p[i + 1].x * t;
                p[i].y = p[i].y * (1.0 - t) + p[i + 1].y * t;
            }
        }
        p[0]
    }
    fn cuts(&self, vertical: bool) -> Vec<f64> {
        let mut cuts = vec![0.0, 1.0];
        let p = self.p.map(|p| p.scan(vertical));
        let d0 = p[1] - p[0];
        match self.degree {
            2 => {
                let d1 = p[2] - p[1];
                if d0 != d1 {
                    cuts.push(d0 / (d0 - d1));
                }
            }
            3 => {
                let d1 = p[2] - p[1];
                let d2 = p[3] - p[2];
                let a = d0 - 2.0 * d1 + d2;
                let b = 2.0 * (d1 - d0);
                let c = d0;
                if a == 0.0 {
                    if b != 0.0 {
                        cuts.push(-c / b);
                    }
                } else {
                    let disc = b * b - 4.0 * a * c;
                    if disc >= 0.0 {
                        let q = -0.5 * (b + disc.sqrt().copysign(b));
                        if q == 0.0 {
                            cuts.push(-b / (2.0 * a));
                        } else {
                            cuts.push(q / a);
                            cuts.push(c / q);
                        }
                    }
                }
            }
            _ => {}
        }
        cuts.retain(|t| t.is_finite() && *t >= 0.0 && *t <= 1.0);
        cuts.sort_by(f64::total_cmp);
        cuts.dedup();
        cuts
    }
}
fn segments(commands: &[FittedCommand]) -> Result<Vec<Segment>, Error> {
    let mut segments = Vec::new();
    let mut current = None;
    let mut start = None;
    for c in commands {
        if segments.len() >= MAX_WORK {
            return Err(fail("dropout outline exceeds work limit"));
        }
        let (p, degree) = match *c {
            FittedCommand::MoveTo(x, y) => {
                if current.is_some() {
                    return Err(fail("dropout outline has unclosed contour"));
                }
                current = Some(Point::new(x, y));
                start = current;
                continue;
            }
            FittedCommand::Close => {
                let a = current
                    .take()
                    .ok_or_else(|| fail("dropout outline closes no contour"))?;
                let b = start.take().unwrap();
                ([a, b, Point::default(), Point::default()], 1)
            }
            FittedCommand::LineTo(x, y) => {
                let a = current.ok_or_else(|| fail("dropout outline segment has no contour"))?;
                let b = Point::new(x, y);
                current = Some(b);
                ([a, b, Point::default(), Point::default()], 1)
            }
            FittedCommand::QuadTo(x1, y1, x, y) => {
                let a = current.ok_or_else(|| fail("dropout outline segment has no contour"))?;
                let b = Point::new(x, y);
                current = Some(b);
                ([a, Point::new(x1, y1), b, Point::default()], 2)
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                let a = current.ok_or_else(|| fail("dropout outline segment has no contour"))?;
                let b = Point::new(x, y);
                current = Some(b);
                ([a, Point::new(x1, y1), Point::new(x2, y2), b], 3)
            }
        };
        segments.push(Segment { p, degree });
    }
    if current.is_some() {
        return Err(fail("dropout outline has unclosed contour"));
    }
    Ok(segments)
}
#[derive(Clone, Copy)]
struct Crossing {
    at: f64,
    winding: i32,
}

// A numerical coincidence bound, not an optical width/phase threshold. Inputs
// are f32; intersections are solved in f64. Coincident reversed curves must not
// manufacture a microscopic filled span from floating-point roundoff.
fn coincidence(a: f64, b: f64) -> f64 {
    32.0 * f64::EPSILON * a.abs().max(b.abs()).max(1.0)
}

fn scan_axis(
    shape: &[Segment],
    raster: &RasterOutput,
    vertical: bool,
    rescue: &mut [bool],
    work: &mut usize,
) -> Result<(), Error> {
    let (scan_origin, along_origin, scan_len, along_len) = if vertical {
        (raster.left, raster.top, raster.width, raster.height)
    } else {
        (raster.top, raster.left, raster.height, raster.width)
    };
    let mut lines = vec![Vec::<Crossing>::new(); scan_len as usize];
    for segment in shape {
        let cuts = segment.cuts(vertical);
        for bounds in cuts.windows(2) {
            let (t0, t1) = (bounds[0], bounds[1]);
            let (s0, s1) = (segment.at(t0).scan(vertical), segment.at(t1).scan(vertical));
            if s0 == s1 {
                continue;
            }
            // Half-open monotone branches assign a shared vertex once; at an
            // extremum the two opposite transitions cancel instead of filling.
            let first = (s0.min(s1) - f64::from(scan_origin) - 0.5).ceil().max(0.0) as usize;
            let end = (s0.max(s1) - f64::from(scan_origin) - 0.5).ceil().max(0.0) as usize;
            for (i, line) in lines.iter_mut().enumerate().take(end).skip(first) {
                *work = work
                    .checked_add(1)
                    .ok_or_else(|| fail("dropout scan work exceeds limit"))?;
                if *work > MAX_WORK {
                    return Err(fail("dropout scan work exceeds limit"));
                }
                let scan = f64::from(scan_origin) + i as f64 + 0.5;
                let mut lo = t0;
                let mut hi = t1;
                let t = if scan == s0 {
                    t0
                } else if scan == s1 {
                    t1
                } else {
                    // 64 subdivisions reach f64 precision without flattening
                    // tolerance or a glyph-dependent curve approximation.
                    for _ in 0..64 {
                        let mid = (lo + hi) * 0.5;
                        if mid == lo || mid == hi {
                            break;
                        }
                        let value = segment.at(mid).scan(vertical);
                        if (value < scan) == (s0 < s1) {
                            lo = mid;
                        } else {
                            hi = mid;
                        }
                    }
                    (lo + hi) * 0.5
                };
                line.push(Crossing {
                    at: segment.at(t).along(vertical),
                    winding: if s0 < s1 { 1 } else { -1 },
                });
            }
        }
    }
    let index = |scan: usize, along: usize| {
        if vertical {
            along * raster.width as usize + scan
        } else {
            scan * raster.width as usize + along
        }
    };
    for (scan, line) in lines.iter_mut().enumerate() {
        line.sort_by(|a, b| a.at.total_cmp(&b.at));
        let mut winding = 0i32;
        let mut beginning = 0.0;
        let mut n = 0;
        while n < line.len() {
            let at = line[n].at;
            let mut delta = 0;
            while n < line.len() && (line[n].at - at).abs() <= coincidence(line[n].at, at) {
                delta += line[n].winding;
                n += 1;
            }
            let before = winding;
            winding += delta;
            if before == 0 && winding != 0 {
                beginning = at;
            } else if before != 0 && winding == 0 {
                let width = at - beginning;
                if width <= coincidence(beginning, at) || width >= 1.0 {
                    continue;
                }
                let first = (beginning - f64::from(along_origin) - 0.5).ceil().max(0.0) as usize;
                let end = ((at - f64::from(along_origin) - 0.5).floor() + 1.0).max(0.0) as usize;
                if (first..end.min(along_len as usize))
                    .any(|along| raster.pixels[index(scan, along)] != 0)
                {
                    continue;
                }
                let mid = (beginning + at) * 0.5;
                // Smart midpoint selection; exact equidistance uses the simple
                // rule's left/bottom convention (TrueType SCANTYPE rule 3).
                let pixel = if vertical {
                    mid.floor()
                } else {
                    mid.ceil() - 1.0
                };
                let along = (pixel - f64::from(along_origin)) as i64;
                if along >= 0 && along < i64::from(along_len) {
                    rescue[index(scan, along as usize)] = true;
                }
            }
        }
        if winding != 0 {
            return Err(fail("dropout scan has unbalanced contour winding"));
        }
    }
    Ok(())
}

/// Keep ordinary coverage conversion, adding only outline-derived mono dropouts.
/// Gray uses the unchanged coverage rasterizer. Rescues in the two scan directions
/// are computed against the same original bitmap, making their union independent
/// of traversal order.
pub fn rasterize(commands: &[FittedCommand], config: &Config) -> Result<RasterOutput, Error> {
    let mut raster = probe::rasterize(commands, config)?;
    if config.output_bits != 1 || raster.pixels.is_empty() {
        return Ok(raster);
    }
    apply_to_raster(commands, &mut raster)?;
    Ok(raster)
}

/// Apply the outline-derived mono dropout scan to an already thresholded
/// native raster built from the same original geometry. Coverage is never
/// modified; rescued pixels are set to 1. The caller owns coverage
/// conversion (plain or oversampled); the scan itself always runs on the
/// original fitted outline at native placement.
pub(crate) fn apply_to_raster(
    commands: &[FittedCommand],
    raster: &mut RasterOutput,
) -> Result<(), Error> {
    if raster.pixels.is_empty() {
        return Ok(());
    }
    let shape = segments(commands)?;
    let mut rescue = vec![false; raster.pixels.len()];
    let mut work = shape.len();
    scan_axis(&shape, raster, false, &mut rescue, &mut work)?;
    scan_axis(&shape, raster, true, &mut rescue, &mut work)?;
    for (pixel, rescue) in raster.pixels.iter_mut().zip(rescue) {
        if rescue {
            *pixel = 1;
        }
    }
    Ok(())
}
