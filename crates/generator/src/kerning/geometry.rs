//! TypeFacet capture adapters. Coverage values never define an outline.
//! Both adapters return baseline-relative, y-up font-unit contours for the
//! same TypeFacet profile calculation; neither chooses an origin or kerning.
use super::typefacet::{GeometryGlyph, Point, Segment};
use crate::{fail, probe::FittedCommand, reference::ReferenceRecord, Error, Glyph};
use std::collections::HashSet;

const MAX_SEGMENTS: usize = 131_072;

fn validate_scale(scale: f64) -> Result<(), Error> {
    if !scale.is_finite() || scale <= 0.0 {
        return Err(fail(
            "kerning geometry requires a positive finite coordinate scale",
        ));
    }
    Ok(())
}

pub(super) fn delivered_cells<'a>(
    glyphs: impl IntoIterator<Item = &'a Glyph>,
    unit: f64,
) -> Result<Vec<GeometryGlyph>, Error> {
    validate_scale(unit)?;
    let mut result = Vec::new();
    let mut seen = HashSet::new();
    let mut segments = 0usize;
    for glyph in glyphs {
        if !seen.insert(glyph.codepoint) {
            return Err(fail("duplicate kerning geometry glyph"));
        }
        let length = (glyph.width as usize)
            .checked_mul(glyph.height as usize)
            .ok_or_else(|| fail("kerning bitmap dimensions overflow"))?;
        if length > 1_048_576
            || glyph.width > 4096
            || glyph.height > 4096
            || glyph.left.unsigned_abs() > 32768
            || glyph.top.unsigned_abs() > 32768
            || glyph.pixels.len() != length
            || glyph.pixels.iter().any(|v| *v > 1)
        {
            return Err(fail(
                "delivered-cell geometry requires bounded unpacked binary pixels",
            ));
        }
        let mut contours = Vec::new();
        for row in 0..glyph.height as usize {
            let mut col = 0;
            while col < glyph.width as usize {
                if glyph.pixels[row * glyph.width as usize + col] == 0 {
                    col += 1;
                    continue;
                }
                let start = col;
                while col < glyph.width as usize
                    && glyph.pixels[row * glyph.width as usize + col] != 0
                {
                    col += 1;
                }
                let x0 = (f64::from(glyph.left) + start as f64) * unit;
                let x1 = (f64::from(glyph.left) + col as f64) * unit;
                let y0 = (-f64::from(glyph.top) - row as f64 - 1.0) * unit;
                let y1 = (-f64::from(glyph.top) - row as f64) * unit;
                // Original delivered-cell experiment: one clockwise rectangle
                // per occupied row run, retaining exact pixel-cell boundaries.
                let p = [
                    Point { x: x0, y: y0 },
                    Point { x: x0, y: y1 },
                    Point { x: x1, y: y1 },
                    Point { x: x1, y: y0 },
                ];
                contours.push(
                    (0..4)
                        .map(|i| Segment::Line([p[i], p[(i + 1) % 4]]))
                        .collect(),
                );
                segments += 4;
                if segments > MAX_SEGMENTS {
                    return Err(fail("kerning geometry segment work limit exceeded"));
                }
            }
        }
        result.push(GeometryGlyph {
            codepoint: glyph.codepoint,
            contours,
        });
    }
    Ok(result)
}

pub(super) fn fitted_outlines<'a>(
    records: impl IntoIterator<Item = &'a ReferenceRecord>,
    unit: f64,
) -> Result<Vec<GeometryGlyph>, Error> {
    validate_scale(unit)?;
    let mut seen = HashSet::new();
    let mut remaining = MAX_SEGMENTS;
    records
        .into_iter()
        .map(|record| {
            if !seen.insert(record.codepoint) {
                return Err(fail("duplicate kerning geometry glyph"));
            }
            outline(
                record.codepoint,
                &record.fitted_commands,
                unit,
                &mut remaining,
            )
        })
        .collect()
}

fn outline(
    codepoint: u32,
    commands: &[FittedCommand],
    unit: f64,
    remaining: &mut usize,
) -> Result<GeometryGlyph, Error> {
    let point = |x: f32, y: f32| -> Result<Point, Error> {
        // Prove line equivalence in the exact fitted f32 coordinate domain,
        // before a non-dyadic font-unit scale can introduce rounding residuals.
        let (x, y) = (f64::from(x), f64::from(y));
        if !x.is_finite() || !y.is_finite() {
            return Err(fail("nonfinite fitted kerning outline"));
        }
        Ok(Point { x, y })
    };
    let same = |a: Point, b: Point| a.x == b.x && a.y == b.y;
    let mut contours = Vec::new();
    let mut contour = Vec::new();
    let mut current = None;
    let mut start = None;
    for command in commands {
        let segment = match *command {
            FittedCommand::MoveTo(x, y) => {
                if current.is_some() {
                    return Err(fail("unclosed fitted kerning contour"));
                }
                let p = point(x, y)?;
                current = Some(p);
                start = Some(p);
                None
            }
            FittedCommand::LineTo(x, y) => {
                let a = current.ok_or_else(|| fail("kerning contour has no move"))?;
                let b = point(x, y)?;
                current = Some(b);
                (!same(a, b)).then_some(Segment::Line([a, b]))
            }
            FittedCommand::QuadTo(x1, y1, x, y) => {
                let a = current.ok_or_else(|| fail("kerning contour has no move"))?;
                let b = point(x, y)?;
                current = Some(b);
                Some(Segment::Quad([a, point(x1, y1)?, b]))
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                let a = current.ok_or_else(|| fail("kerning contour has no move"))?;
                let b = point(x, y)?;
                current = Some(b);
                Some(Segment::Cubic([a, point(x1, y1)?, point(x2, y2)?, b]))
            }
            FittedCommand::Close => {
                let a = current
                    .take()
                    .ok_or_else(|| fail("kerning contour has no move"))?;
                let b = start
                    .take()
                    .ok_or_else(|| fail("kerning contour has no start"))?;
                if !same(a, b) {
                    *remaining = remaining
                        .checked_sub(1)
                        .ok_or_else(|| fail("kerning geometry segment work limit exceeded"))?;
                    contour.push(Segment::Line([a, b]));
                }
                if !contour.is_empty() {
                    contours.push(std::mem::take(&mut contour));
                }
                None
            }
        };
        if let Some(segment) = segment.and_then(canonical_segment) {
            *remaining = remaining
                .checked_sub(1)
                .ok_or_else(|| fail("kerning geometry segment work limit exceeded"))?;
            contour.push(segment);
        }
    }
    if current.is_some() {
        return Err(fail("unclosed fitted kerning contour"));
    }
    let scale = |p: Point| -> Result<Point, Error> {
        let p = Point {
            x: p.x * unit,
            y: p.y * unit,
        };
        if !p.x.is_finite() || !p.y.is_finite() {
            return Err(fail("nonfinite fitted kerning outline"));
        }
        Ok(p)
    };
    for contour in &mut contours {
        for segment in contour {
            *segment = match *segment {
                Segment::Line([a, b]) => Segment::Line([scale(a)?, scale(b)?]),
                Segment::Quad([a, b, c]) => Segment::Quad([scale(a)?, scale(b)?, scale(c)?]),
                Segment::Cubic([a, b, c, d]) => {
                    Segment::Cubic([scale(a)?, scale(b)?, scale(c)?, scale(d)?])
                }
            };
        }
    }
    Ok(GeometryGlyph {
        codepoint,
        contours,
    })
}

// A Bezier stays in its control hull and includes both endpoints:
// https://people.eecs.ku.edu/~jrmiller/Courses/IntroToCurvesAndSurfaces/BezierCurveProperties.html
// Collinear controls INSIDE the endpoint segment therefore describe precisely
// that directed line locus. This exact analysis-only normalization handles
// curves collapsed by hinting; upstream's quadratic offset cannot intersect
// parallel tangents. It never flattens a curved or overshooting segment.
fn canonical_segment(segment: Segment) -> Option<Segment> {
    let points: &[Point] = match &segment {
        Segment::Line(p) => p,
        Segment::Quad(p) => p,
        Segment::Cubic(p) => p,
    };
    let a = points[0];
    let b = *points.last().unwrap();
    if points.iter().all(|p| *p == a) {
        return None;
    }
    // Cubic and straight offsets already have a defined upstream route; keep
    // their original parameterization even when their locus is straight.
    if !matches!(segment, Segment::Quad(_)) || a == b {
        return Some(segment);
    }
    if points.iter().all(|p| {
        p.x >= a.x.min(b.x) && p.x <= a.x.max(b.x) && p.y >= a.y.min(b.y) && p.y <= a.y.max(b.y)
    }) && exact_collinear(points)
    {
        Some(Segment::Line([a, b]))
    } else {
        Some(segment)
    }
}

fn exact_collinear(points: &[Point]) -> bool {
    // Integer dyadic arithmetic proves collinearity without an epsilon. If an
    // extreme exponent span exceeds i128, retain the original curve instead.
    fn dyadic(value: f64) -> (i128, i32) {
        if value == 0.0 {
            return (0, 0);
        }
        let bits = value.to_bits();
        let exponent = ((bits >> 52) & 0x7ff) as i32;
        let mut mantissa = (bits & ((1u64 << 52) - 1)) | if exponent == 0 { 0 } else { 1u64 << 52 };
        let zeros = mantissa.trailing_zeros();
        mantissa >>= zeros;
        let sign = if bits >> 63 == 0 { 1 } else { -1 };
        (
            i128::from(mantissa) * sign,
            if exponent == 0 {
                -1074
            } else {
                exponent - 1023 - 52
            } + zeros as i32,
        )
    }
    let values: Vec<_> = points.iter().map(|p| [dyadic(p.x), dyadic(p.y)]).collect();
    let bases = [0, 1].map(|axis| {
        values
            .iter()
            .filter(|v| v[axis].0 != 0)
            .map(|v| v[axis].1)
            .min()
            .unwrap_or(0)
    });
    let integer = |value: (i128, i32), axis: usize| -> Option<i128> {
        if value.0 == 0 {
            return Some(0);
        }
        let shift = u32::try_from(value.1 - bases[axis]).ok()?;
        if shift >= 127 {
            return None;
        }
        value.0.checked_mul(1i128.checked_shl(shift)?)
    };
    let Some(values) = values
        .iter()
        .map(|v| Some([integer(v[0], 0)?, integer(v[1], 1)?]))
        .collect::<Option<Vec<_>>>()
    else {
        return false;
    };
    let start = values[0];
    let end = *values.last().unwrap();
    let Some(dx) = end[0].checked_sub(start[0]) else {
        return false;
    };
    let Some(dy) = end[1].checked_sub(start[1]) else {
        return false;
    };
    values.iter().all(|v| {
        let cross = || {
            Some((
                v[0].checked_sub(start[0])?.checked_mul(dy)?,
                v[1].checked_sub(start[1])?.checked_mul(dx)?,
            ))
        };
        cross().is_some_and(|(left, right)| left == right)
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn outline_adapter_keeps_curves_and_baseline_coordinates() {
        let commands = [
            FittedCommand::MoveTo(-1., 0.),
            FittedCommand::QuadTo(1., 4., 3., 0.),
            FittedCommand::CurveTo(2., -2., 0., -2., -1., 0.),
            FittedCommand::Close,
        ];
        let outline = outline(0x00e9, &commands, 62.5, &mut MAX_SEGMENTS.clone()).unwrap();
        assert_eq!(outline.contours.len(), 1);
        assert!(matches!(outline.contours[0][0], Segment::Quad(_)));
        assert!(matches!(outline.contours[0][1], Segment::Cubic(_)));
        if let Segment::Quad(points) = outline.contours[0][0] {
            assert_eq!((points[0].x, points[0].y), (-62.5, 0.));
            assert_eq!((points[1].x, points[1].y), (62.5, 250.));
        }
    }
    #[test]
    fn incomplete_and_nonfinite_outlines_fail_before_preparation() {
        for commands in [
            vec![FittedCommand::LineTo(1., 0.)],
            vec![FittedCommand::MoveTo(0., 0.)],
            vec![FittedCommand::MoveTo(f32::NAN, 0.), FittedCommand::Close],
        ] {
            assert!(outline(97, &commands, 1., &mut MAX_SEGMENTS.clone()).is_err());
        }
    }

    #[test]
    fn only_exact_line_loci_are_normalized() {
        // Actual Literata16 Gray e: hinting collapses this quadratic to a
        // vertical line. Keep its endpoints, orientation and complete locus.
        let a = Point {
            x: 6.390625,
            y: 5.21875,
        };
        let b = Point {
            x: 6.390625,
            y: 5.546875,
        };
        assert_eq!(
            canonical_segment(Segment::Quad([
                a,
                Point {
                    x: 6.390625,
                    y: 5.375
                },
                b
            ])),
            Some(Segment::Line([a, b]))
        );
        let a = Point { x: -2., y: -3. };
        let b = Point { x: 4., y: 9. };
        let straight_cubic = Segment::Cubic([a, Point { x: 0., y: 1. }, Point { x: 1., y: 3. }, b]);
        assert_eq!(canonical_segment(straight_cubic), Some(straight_cubic));
        assert_eq!(
            canonical_segment(Segment::Quad([a, Point { x: 0., y: 1. }, b])),
            Some(Segment::Line([a, b]))
        );
        for control in [
            Point { x: 5., y: 11. },
            Point {
                x: 0.,
                y: 1. + f64::EPSILON,
            },
        ] {
            let curve = Segment::Quad([a, control, b]);
            assert_eq!(
                canonical_segment(curve),
                Some(curve),
                "retain overshoot and nonzero curvature"
            );
        }
        assert_eq!(canonical_segment(Segment::Quad([a, a, a])), None);

        // Decide in the fitted-coordinate domain before non-dyadic scaling.
        let commands = [
            FittedCommand::MoveTo(-2., -3.),
            FittedCommand::QuadTo(0., 1., 4., 9.),
            FittedCommand::Close,
        ];
        let result = outline(97, &commands, 1000. / 17., &mut MAX_SEGMENTS.clone()).unwrap();
        assert!(matches!(result.contours[0][0], Segment::Line(_)));
    }
}
