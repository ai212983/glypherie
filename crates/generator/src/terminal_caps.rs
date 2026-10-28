//! Straight supporting-cap suppression kernel.
//!
//! Source: TrueType SCANTYPE Rules 5/6 (cap closure needs both borders to
//! continue past the dropout scan line); pinned FreeType ftraster.c profile-pair
//! stub test (same-contour successor/top-bottom checks); Hersch 1993 section 7
//! (subpixel interior null-span rescue); 26.6 conversion
//! (floor(x*64+0.5)) per mono.rs; Shewchuk error-filtered orientation
//! predicates (https://www.cs.cmu.edu/~quake/robust.html).
//! Project hypothesis (owning design docs/revisions/001/03-spacing-kerning.md):
//! a straight cap edge that is a supporting line of the WHOLE filled outline,
//! with both adjacent stroke borders continuing into the filled half-plane and
//! unambiguous span ownership, is a genuine terminal; curves, interior
//! junctions and uncertain overlap abstain (keep rescue).
//! Invariant: removal needs the fixed-grid FreeType stubs on/off pixel
//! difference AND attribution to exactly one dually-certified cap; bytes are
//! otherwise preserved verbatim. Unsupported or ambiguous input yields a
//! clone of the with-stubs raster, never an error; malformed, non-finite or
//! out-of-range input is an explicit error.
//! Invariant: fitted 26.6 predicates are exact in i64 (|coord| <= 2097152,
//! crosses below 2**45). Source f32 geometry is widened exactly to f64 and
//! oriented only through the error-filtered predicate; a non-structural zero
//! or a below-bound determinant abstains instead of deciding.
//! Invariant: total predicate/edge work is budget-capped; complex outlines
//! fail closed instead of running unbounded.
//! Limitation: long hull-border caps can certify; attribution still requires
//! the FreeType diff pixel plus a square meeting only the cap wedge, and the
//! owning document records this residual long-border span risk.
//! Limitation: single-point grazes never associate; closed contact by any
//! non-cap geometry abstains.

use crate::{
    fail,
    orientation::filtered_sign as orient_f,
    probe::{FittedCommand, RasterOutput},
    Error,
};

const BOUND: f32 = 32768.0;
const QBOUND: i64 = 2_097_152;
const MAX_WORK: u64 = 4_194_304;
const MAX_POINTS: usize = u16::MAX as usize;
const MAX_PIXELS: u64 = 4_194_304;

/// Suppressed raster plus removed outline-space pixel coordinates.
pub struct Suppression {
    pub pixels: Vec<u8>,
    pub removed: Vec<[i32; 2]>,
}

struct Work(u64);

impl Work {
    fn step(&mut self, n: u64) -> Result<(), Error> {
        self.0 = self.0.saturating_add(n);
        if self.0 > MAX_WORK {
            return Err(fail("terminal cap work exceeds limit"));
        }
        Ok(())
    }
}

/// Suppress only FreeType stub-rescue pixels at dually-certified terminal caps.
///
/// Source commands carry the unhinted shape; fitted commands carry the current
/// fitted shape scanned at 26.6. Pixel attribution uses fitted coordinates.
pub fn suppress_certified(
    source: &[FittedCommand],
    fitted: &[FittedCommand],
    with_stubs: &RasterOutput,
    without_stubs: &RasterOutput,
) -> Result<Suppression, Error> {
    validate(source)?;
    validate(fitted)?;
    if (
        with_stubs.left,
        with_stubs.top,
        with_stubs.width,
        with_stubs.height,
    ) != (
        without_stubs.left,
        without_stubs.top,
        without_stubs.width,
        without_stubs.height,
    ) {
        return Err(fail("terminal cap raster frames differ"));
    }
    let cells = u64::from(with_stubs.width) * u64::from(with_stubs.height);
    let right = i64::from(with_stubs.left) + i64::from(with_stubs.width);
    let bottom = i64::from(with_stubs.top) + i64::from(with_stubs.height);
    if cells > MAX_PIXELS
        || i64::from(with_stubs.left).abs() > 32768
        || i64::from(with_stubs.top).abs() > 32768
        || right.abs() > 32768
        || bottom.abs() > 32768
    {
        return Err(fail("terminal cap raster exceeds scanner bounds"));
    }
    let cells = usize::try_from(cells).map_err(|_| fail("terminal cap raster size overflow"))?;
    if with_stubs.pixels.len() != cells || without_stubs.pixels.len() != cells {
        return Err(fail("terminal cap raster buffers differ"));
    }
    if with_stubs.pixels.is_empty() {
        return Ok(Suppression {
            pixels: with_stubs.pixels.clone(),
            removed: Vec::new(),
        });
    }
    let (src_contours, src_struct) = parse(source)?;
    let (fit_contours, fit_struct) = parse(fitted)?;
    // Invariant: identical op/contour/edge identity across source and fitted.
    if src_struct != fit_struct {
        return Ok(Suppression {
            pixels: with_stubs.pixels.clone(),
            removed: Vec::new(),
        });
    }
    let mut work = Work(0);
    let fit_q = quantize(&fit_contours)?;
    let fit_hulls = hull_set(&fit_q);
    // Optional geometry work may abstain; the underlying FreeType raster
    // has already succeeded. Budget exhaustion never changes its bytes.
    let Ok(caps) = certify(&src_contours, &fit_q, &fit_hulls, &mut work) else {
        return Ok(Suppression {
            pixels: with_stubs.pixels.clone(),
            removed: Vec::new(),
        });
    };
    if caps.is_empty() {
        return Ok(Suppression {
            pixels: with_stubs.pixels.clone(),
            removed: Vec::new(),
        });
    }
    let mut out = with_stubs.pixels.clone();
    let mut removed = Vec::new();
    let w = with_stubs.width as usize;
    for (idx, (&a, &b)) in with_stubs
        .pixels
        .iter()
        .zip(without_stubs.pixels.iter())
        .enumerate()
    {
        if a != 1 || b != 0 {
            continue;
        }
        let i = idx % w;
        let j = idx / w;
        let square = pixel_square(with_stubs.left, with_stubs.top, i as i32, j as i32);
        let Ok(owner) = attribute(square, &caps, &fit_q, &fit_hulls, &mut work) else {
            return Ok(Suppression {
                pixels: with_stubs.pixels.clone(),
                removed: Vec::new(),
            });
        };
        if owner.is_some() {
            out[idx] = 0;
            removed.push([with_stubs.left + i as i32, with_stubs.top + j as i32]);
        }
    }
    Ok(Suppression {
        pixels: out,
        removed,
    })
}

fn validate(commands: &[FittedCommand]) -> Result<(), Error> {
    // Invariant: rejects malformed, non-finite and out-of-range input.
    // Matches the coordinate bound enforced in mono.rs.
    let mut open = false;
    let mut points = 0usize;
    for command in commands {
        points += match command {
            FittedCommand::Close => 0,
            FittedCommand::QuadTo(..) => 2,
            FittedCommand::CurveTo(..) => 3,
            _ => 1,
        };
        if points > MAX_POINTS {
            return Err(fail("terminal cap outline exceeds scanner point limit"));
        }
        match *command {
            FittedCommand::MoveTo(x, y) => {
                if open {
                    return Err(fail("terminal cap outline has unclosed contour"));
                }
                check_point(x, y)?;
                open = true;
            }
            FittedCommand::Close => {
                if !open {
                    return Err(fail("terminal cap outline closes no contour"));
                }
                open = false;
            }
            FittedCommand::LineTo(x, y) => {
                if !open {
                    return Err(fail("terminal cap segment has no contour"));
                }
                check_point(x, y)?;
            }
            FittedCommand::QuadTo(x1, y1, x, y) => {
                if !open {
                    return Err(fail("terminal cap segment has no contour"));
                }
                check_point(x1, y1)?;
                check_point(x, y)?;
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                if !open {
                    return Err(fail("terminal cap segment has no contour"));
                }
                check_point(x1, y1)?;
                check_point(x2, y2)?;
                check_point(x, y)?;
            }
        }
    }
    if open {
        return Err(fail("terminal cap outline has unclosed contour"));
    }
    Ok(())
}

fn check_point(x: f32, y: f32) -> Result<(), Error> {
    if !x.is_finite() || !y.is_finite() {
        return Err(fail("terminal cap outline is non-finite"));
    }
    if x.abs() > BOUND || y.abs() > BOUND {
        return Err(fail("terminal cap coordinate out of range"));
    }
    Ok(())
}

fn q26(v: f64) -> i64 {
    // Source: floor(x*64+0.5) per mono.rs.
    (v * 64.0 + 0.5).floor() as i64
}

fn quantize(contours: &[ContourF]) -> Result<Vec<ContourI>, Error> {
    let mut out = Vec::with_capacity(contours.len());
    for contour in contours {
        let mut qc = ContourI {
            points: Vec::with_capacity(contour.points.len()),
            curves: Vec::with_capacity(contour.curves.len()),
            edges: Vec::with_capacity(contour.edges.len()),
        };
        for point in &contour.points {
            let q = [q26(point[0]), q26(point[1])];
            if q[0].abs() > QBOUND || q[1].abs() > QBOUND {
                return Err(fail("terminal cap quantized coordinate out of range"));
            }
            qc.points.push(q);
        }
        for curve in &contour.curves {
            let mut qc_curve = Vec::with_capacity(curve.len());
            for point in curve {
                let q = [q26(point[0]), q26(point[1])];
                if q[0].abs() > QBOUND || q[1].abs() > QBOUND {
                    return Err(fail("terminal cap quantized coordinate out of range"));
                }
                qc_curve.push(q);
            }
            qc.curves.push(qc_curve);
        }
        for (a, b) in &contour.edges {
            qc.edges
                .push(([q26(a[0]), q26(a[1])], [q26(b[0]), q26(b[1])]));
        }
        out.push(qc);
    }
    Ok(out)
}

struct ContourF {
    points: Vec<[f64; 2]>,
    curves: Vec<Vec<[f64; 2]>>,
    edges: Vec<([f64; 2], [f64; 2])>,
}

struct ContourI {
    points: Vec<[i64; 2]>,
    curves: Vec<Vec<[i64; 2]>>,
    edges: Vec<([i64; 2], [i64; 2])>,
}

fn parse(commands: &[FittedCommand]) -> Result<(Vec<ContourF>, Vec<Vec<u8>>), Error> {
    // Source: TrueType glyph outline model (move/line/quad/cubic/close).
    let mut contours = Vec::new();
    let mut structure = Vec::new();
    let mut current: Option<ContourF> = None;
    let mut ops: Vec<u8> = Vec::new();
    for command in commands {
        match *command {
            FittedCommand::MoveTo(x, y) => {
                if current.is_some() {
                    return Err(fail("terminal cap outline has unclosed contour"));
                }
                current = Some(ContourF {
                    points: vec![[f64::from(x), f64::from(y)]],
                    curves: Vec::new(),
                    edges: Vec::new(),
                });
                ops = vec![0];
            }
            FittedCommand::LineTo(x, y) => {
                let contour = current
                    .as_mut()
                    .ok_or_else(|| fail("terminal cap segment has no contour"))?;
                let point = [f64::from(x), f64::from(y)];
                contour
                    .edges
                    .push((contour.points[contour.points.len() - 1], point));
                contour.points.push(point);
                ops.push(1);
            }
            FittedCommand::QuadTo(x1, y1, x, y) => {
                let contour = current
                    .as_mut()
                    .ok_or_else(|| fail("terminal cap segment has no contour"))?;
                let p0 = contour.points[contour.points.len() - 1];
                let p2 = [f64::from(x), f64::from(y)];
                contour
                    .curves
                    .push(vec![p0, [f64::from(x1), f64::from(y1)], p2]);
                contour.points.push(p2);
                ops.push(2);
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                let contour = current
                    .as_mut()
                    .ok_or_else(|| fail("terminal cap segment has no contour"))?;
                let p0 = contour.points[contour.points.len() - 1];
                let p3 = [f64::from(x), f64::from(y)];
                contour.curves.push(vec![
                    p0,
                    [f64::from(x1), f64::from(y1)],
                    [f64::from(x2), f64::from(y2)],
                    p3,
                ]);
                contour.points.push(p3);
                ops.push(3);
            }
            FittedCommand::Close => {
                let mut contour = current
                    .take()
                    .ok_or_else(|| fail("terminal cap outline closes no contour"))?;
                if contour.points.len() > 1 {
                    let first = contour.points[0];
                    let last = contour.points[contour.points.len() - 1];
                    contour.edges.push((last, first));
                    contour.points.push(first);
                }
                contours.push(contour);
                ops.push(4);
                structure.push(ops);
                ops = Vec::new();
            }
        }
    }
    if current.is_some() {
        return Err(fail("terminal cap outline has unclosed contour"));
    }
    Ok((contours, structure))
}

fn orient_i(ax: i64, ay: i64, bx: i64, by: i64, cx: i64, cy: i64) -> i8 {
    // Invariant: exact in i64; inputs bounded so crosses stay below 2**45.
    let det = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
    det.signum() as i8
}

fn on_segment_i(p: [i64; 2], a: [i64; 2], b: [i64; 2]) -> bool {
    if orient_i(a[0], a[1], b[0], b[1], p[0], p[1]) != 0 {
        return false;
    }
    p[0] >= a[0].min(b[0])
        && p[0] <= a[0].max(b[0])
        && p[1] >= a[1].min(b[1])
        && p[1] <= a[1].max(b[1])
}

fn segments_touch_i(a: [i64; 2], b: [i64; 2], c: [i64; 2], d: [i64; 2]) -> bool {
    // Source: exact orientation-predicate segment intersection.
    let o1 = orient_i(a[0], a[1], b[0], b[1], c[0], c[1]);
    let o2 = orient_i(a[0], a[1], b[0], b[1], d[0], d[1]);
    let o3 = orient_i(c[0], c[1], d[0], d[1], a[0], a[1]);
    let o4 = orient_i(c[0], c[1], d[0], d[1], b[0], b[1]);
    if o1 != o2 && o3 != o4 {
        return true;
    }
    (o1 == 0 && on_segment_i(c, a, b))
        || (o2 == 0 && on_segment_i(d, a, b))
        || (o3 == 0 && on_segment_i(a, c, d))
        || (o4 == 0 && on_segment_i(b, c, d))
}

fn segments_touch_f(
    a: [f64; 2],
    b: [f64; 2],
    c: [f64; 2],
    d: [f64; 2],
    work: &mut Work,
) -> Result<bool, Error> {
    // Invariant: any uncertain predicate counts as contact.
    work.step(1)?;
    let o = [
        orient_f(a[0], a[1], b[0], b[1], c[0], c[1]),
        orient_f(a[0], a[1], b[0], b[1], d[0], d[1]),
        orient_f(c[0], c[1], d[0], d[1], a[0], a[1]),
        orient_f(c[0], c[1], d[0], d[1], b[0], b[1]),
    ];
    if o.iter().any(|v| v.is_none()) {
        return Ok(true);
    }
    let o = [o[0].unwrap(), o[1].unwrap(), o[2].unwrap(), o[3].unwrap()];
    if o[0] != o[1] && o[2] != o[3] {
        return Ok(true);
    }
    // Endpoint-on-segment needs exact collinearity; uncertain cases already
    // returned contact above, so only exact zeros reach here.
    let on = |p: [f64; 2], x: [f64; 2], y: [f64; 2]| {
        orient_f(x[0], x[1], y[0], y[1], p[0], p[1]) == Some(0)
            && p[0] >= x[0].min(y[0])
            && p[0] <= x[0].max(y[0])
            && p[1] >= x[1].min(y[1])
            && p[1] <= x[1].max(y[1])
    };
    Ok((o[0] == 0 && on(c, a, b))
        || (o[1] == 0 && on(d, a, b))
        || (o[2] == 0 && on(a, c, d))
        || (o[3] == 0 && on(b, c, d)))
}

fn convex_hull(points: &[[i64; 2]]) -> Vec<[i64; 2]> {
    // Source: Andrew monotone chain over control points.
    let mut pts = points.to_vec();
    pts.sort_unstable();
    pts.dedup();
    if pts.len() <= 1 {
        return pts;
    }
    let mut lower: Vec<[i64; 2]> = Vec::new();
    let mut upper: Vec<[i64; 2]> = Vec::new();
    for p in &pts {
        while lower.len() >= 2 {
            let n = lower.len();
            if orient_i(
                lower[n - 2][0],
                lower[n - 2][1],
                lower[n - 1][0],
                lower[n - 1][1],
                p[0],
                p[1],
            ) <= 0
            {
                lower.pop();
            } else {
                break;
            }
        }
        lower.push(*p);
    }
    for p in pts.iter().rev() {
        while upper.len() >= 2 {
            let n = upper.len();
            if orient_i(
                upper[n - 2][0],
                upper[n - 2][1],
                upper[n - 1][0],
                upper[n - 1][1],
                p[0],
                p[1],
            ) <= 0
            {
                upper.pop();
            } else {
                break;
            }
        }
        upper.push(*p);
    }
    lower.pop();
    upper.pop();
    lower.extend(upper);
    lower
}

fn point_in_convex_strict(p: [i64; 2], hull: &[[i64; 2]]) -> bool {
    if hull.len() < 3 {
        return false;
    }
    let mut s = 0i8;
    for i in 0..hull.len() {
        let o = orient_i(
            hull[i][0],
            hull[i][1],
            hull[(i + 1) % hull.len()][0],
            hull[(i + 1) % hull.len()][1],
            p[0],
            p[1],
        );
        if o == 0 {
            return false;
        }
        if s == 0 {
            s = o;
        } else if s != o {
            return false;
        }
    }
    true
}

fn hull_meets_segment(hull: &[[i64; 2]], a: [i64; 2], b: [i64; 2]) -> bool {
    // Invariant: closed contact, including a point touch, counts.
    if hull.is_empty() {
        return false;
    }
    let min_hx = hull.iter().map(|p| p[0]).min().unwrap();
    let max_hx = hull.iter().map(|p| p[0]).max().unwrap();
    let min_hy = hull.iter().map(|p| p[1]).min().unwrap();
    let max_hy = hull.iter().map(|p| p[1]).max().unwrap();
    if max_hx < a[0].min(b[0]) || min_hx > a[0].max(b[0]) {
        return false;
    }
    if max_hy < a[1].min(b[1]) || min_hy > a[1].max(b[1]) {
        return false;
    }
    if hull.len() == 1 {
        return on_segment_i(hull[0], a, b);
    }
    if hull.len() == 2 {
        return segments_touch_i(hull[0], hull[1], a, b);
    }
    for i in 0..hull.len() {
        if segments_touch_i(hull[i], hull[(i + 1) % hull.len()], a, b) {
            return true;
        }
    }
    point_in_convex_strict(a, hull) || point_in_convex_strict(b, hull)
}

fn hull_meets_square(hull: &[[i64; 2]], square: ([i64; 2], [i64; 2])) -> bool {
    // Invariant: closed contact, including a point touch, counts.
    if hull.is_empty() {
        return false;
    }
    let ([x0, y0], [x1, y1]) = square;
    for v in hull {
        if v[0] >= x0 && v[0] <= x1 && v[1] >= y0 && v[1] <= y1 {
            return true;
        }
    }
    let corners = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
    if hull.len() >= 3 {
        for c in &corners {
            if point_in_convex_strict(*c, hull) {
                return true;
            }
        }
    }
    let edges: Vec<([i64; 2], [i64; 2])> = if hull.len() == 1 {
        Vec::new()
    } else if hull.len() == 2 {
        vec![(hull[0], hull[1])]
    } else {
        (0..hull.len())
            .map(|i| (hull[i], hull[(i + 1) % hull.len()]))
            .collect()
    };
    for (h0, h1) in &edges {
        for i in 0..4 {
            if segments_touch_i(*h0, *h1, corners[i], corners[(i + 1) % 4]) {
                return true;
            }
        }
    }
    false
}

struct Cap {
    contour: usize,
    edge: usize,
    a: [i64; 2],
    b: [i64; 2],
}

fn half_plane_ok_f(
    contours: &[ContourF],
    a: [f64; 2],
    b: [f64; 2],
    side: i8,
    work: &mut Work,
) -> Result<bool, Error> {
    for contour in contours {
        for p in &contour.points {
            work.step(1)?;
            match orient_f(a[0], a[1], b[0], b[1], p[0], p[1]) {
                Some(s) if s == -side => return Ok(false),
                None => return Ok(false),
                _ => {}
            }
        }
        for curve in &contour.curves {
            for p in curve.iter().skip(1) {
                work.step(1)?;
                // Invariant: Bezier convex-hull property keeps this sufficient.
                match orient_f(a[0], a[1], b[0], b[1], p[0], p[1]) {
                    Some(s) if s == -side => return Ok(false),
                    None => return Ok(false),
                    _ => {}
                }
            }
        }
    }
    Ok(true)
}

fn half_plane_ok_i(
    contours: &[ContourI],
    a: [i64; 2],
    b: [i64; 2],
    side: i8,
    work: &mut Work,
) -> Result<bool, Error> {
    for contour in contours {
        for p in &contour.points {
            work.step(1)?;
            let s = orient_i(a[0], a[1], b[0], b[1], p[0], p[1]);
            if s == -side {
                return Ok(false);
            }
        }
        for curve in &contour.curves {
            for p in curve.iter().skip(1) {
                work.step(1)?;
                // Invariant: Bezier convex-hull property keeps this sufficient.
                if orient_i(a[0], a[1], b[0], b[1], p[0], p[1]) == -side {
                    return Ok(false);
                }
            }
        }
    }
    Ok(true)
}

fn bbox_overlap(
    ax0: f64,
    ay0: f64,
    ax1: f64,
    ay1: f64,
    bx0: f64,
    by0: f64,
    bx1: f64,
    by1: f64,
) -> bool {
    ax0.min(ax1) <= bx0.max(bx1)
        && ax0.max(ax1) >= bx0.min(bx1)
        && ay0.min(ay1) <= by0.max(by1)
        && ay0.max(ay1) >= by0.min(by1)
}

fn touches_other_f(
    contours: &[ContourF],
    ci: usize,
    edge_idx: usize,
    a: [f64; 2],
    b: [f64; 2],
    work: &mut Work,
) -> Result<bool, Error> {
    // Invariant: conservative disjoint control-point boxes for curves, exact
    // segment tests with uncertainty counting as contact for straight edges.
    let n = contours[ci].edges.len();
    for (cj, contour) in contours.iter().enumerate() {
        for (ej, (c, d)) in contour.edges.iter().enumerate() {
            if cj == ci
                && (ej == edge_idx || ej == (edge_idx + n - 1) % n || ej == (edge_idx + 1) % n)
            {
                continue;
            }
            work.step(1)?;
            if segments_touch_f(a, b, *c, *d, work)? {
                return Ok(true);
            }
        }
        for curve in &contour.curves {
            let (mut x0, mut y0) = (curve[0][0], curve[0][1]);
            let (mut x1, mut y1) = (x0, y0);
            for p in curve.iter().skip(1) {
                x0 = x0.min(p[0]);
                y0 = y0.min(p[1]);
                x1 = x1.max(p[0]);
                y1 = y1.max(p[1]);
            }
            if bbox_overlap(a[0], a[1], b[0], b[1], x0, y0, x1, y1) {
                return Ok(true);
            }
        }
    }
    Ok(false)
}

fn touches_other_i(
    contours: &[ContourI],
    hulls: &[Vec<Vec<[i64; 2]>>],
    ci: usize,
    edge_idx: usize,
    a: [i64; 2],
    b: [i64; 2],
    work: &mut Work,
) -> Result<bool, Error> {
    let n = contours[ci].edges.len();
    for (cj, contour) in contours.iter().enumerate() {
        for (ej, (c, d)) in contour.edges.iter().enumerate() {
            if cj == ci
                && (ej == edge_idx || ej == (edge_idx + n - 1) % n || ej == (edge_idx + 1) % n)
            {
                continue;
            }
            work.step(1)?;
            if segments_touch_i(a, b, *c, *d) {
                return Ok(true);
            }
        }
        for hull in &hulls[cj] {
            work.step(1)?;
            // Invariant: hull contact (incl. point touch) counts as contact.
            if hull_meets_segment(hull, a, b) {
                return Ok(true);
            }
        }
    }
    Ok(false)
}

fn classify_edge_f(
    contours: &[ContourF],
    ci: usize,
    edge_idx: usize,
    work: &mut Work,
) -> Result<(bool, i8), Error> {
    let edges = &contours[ci].edges;
    let n = edges.len();
    let (a, b) = edges[edge_idx];
    if a == b {
        return Ok((false, 0));
    }
    // Project hypothesis: curves anywhere in the cap contour abstain.
    if !contours[ci].curves.is_empty() {
        return Ok((false, 0));
    }
    let prev_far = edges[(edge_idx + n - 1) % n].0;
    let next_far = edges[(edge_idx + 1) % n].1;
    work.step(2)?;
    let s1 = orient_f(a[0], a[1], b[0], b[1], prev_far[0], prev_far[1]);
    let s2 = orient_f(a[0], a[1], b[0], b[1], next_far[0], next_far[1]);
    let (s1, s2) = match (s1, s2) {
        (Some(x), Some(y)) => (x, y),
        _ => return Ok((false, 0)),
    };
    if s1 != s2 || s1 == 0 {
        return Ok((false, 0));
    }
    if !half_plane_ok_f(contours, a, b, s1, work)? {
        return Ok((false, 0));
    }
    if touches_other_f(contours, ci, edge_idx, a, b, work)? {
        return Ok((false, 0));
    }
    Ok((true, s1))
}

fn classify_edge_i(
    contours: &[ContourI],
    hulls: &[Vec<Vec<[i64; 2]>>],
    ci: usize,
    edge_idx: usize,
    work: &mut Work,
) -> Result<(bool, i8), Error> {
    let edges = &contours[ci].edges;
    let n = edges.len();
    let (a, b) = edges[edge_idx];
    if a == b {
        return Ok((false, 0));
    }
    // Project hypothesis: curves anywhere in the cap contour abstain.
    if !contours[ci].curves.is_empty() {
        return Ok((false, 0));
    }
    let prev_far = edges[(edge_idx + n - 1) % n].0;
    let next_far = edges[(edge_idx + 1) % n].1;
    work.step(2)?;
    let s1 = orient_i(a[0], a[1], b[0], b[1], prev_far[0], prev_far[1]);
    let s2 = orient_i(a[0], a[1], b[0], b[1], next_far[0], next_far[1]);
    if s1 != s2 || s1 == 0 {
        return Ok((false, 0));
    }
    if !half_plane_ok_i(contours, a, b, s1, work)? {
        return Ok((false, 0));
    }
    if touches_other_i(contours, hulls, ci, edge_idx, a, b, work)? {
        return Ok((false, 0));
    }
    Ok((true, s1))
}

fn certify(
    src: &[ContourF],
    fit: &[ContourI],
    fit_hulls: &[Vec<Vec<[i64; 2]>>],
    work: &mut Work,
) -> Result<Vec<Cap>, Error> {
    // Invariant: ELIGIBLE in both the source shape and the quantized fitted
    // shape at the same contour/edge index with the same filled side.
    let mut out = Vec::new();
    for (ci, contour) in src.iter().enumerate() {
        for ei in 0..contour.edges.len() {
            let (ok_s, side_s) = classify_edge_f(src, ci, ei, work)?;
            if !ok_s {
                continue;
            }
            let (ok_f, side_f) = classify_edge_i(fit, fit_hulls, ci, ei, work)?;
            if !ok_f || side_s != side_f {
                continue;
            }
            let (a, b) = fit[ci].edges[ei];
            out.push(Cap {
                contour: ci,
                edge: ei,
                a,
                b,
            });
        }
    }
    Ok(out)
}

fn hull_set(contours: &[ContourI]) -> Vec<Vec<Vec<[i64; 2]>>> {
    contours
        .iter()
        .map(|contour| {
            contour
                .curves
                .iter()
                .map(|curve| convex_hull(curve))
                .collect()
        })
        .collect()
}

fn clip_positive(a: [i64; 2], b: [i64; 2], square: ([i64; 2], [i64; 2])) -> bool {
    // Source: Liang-Barsky clipping against the closed unit pixel square;
    // integer rational comparison, bounded crosses fit i64. A single-point
    // graze yields no association.
    let ([x0, y0], [x1, y1]) = square;
    let dx = b[0] - a[0];
    let dy = b[1] - a[1];
    if dx == 0 && dy == 0 {
        return x0 < a[0] && a[0] < x1 && y0 < a[1] && a[1] < y1;
    }
    // t bounds as (num, den) with den > 0: t0 = 0/1, t1 = 1/1.
    let (mut n0, mut d0) = (0i64, 1i64);
    let (mut n1, mut d1) = (1i64, 1i64);
    let less = |n1: i64, d1: i64, n2: i64, d2: i64| n1 * d2 < n2 * d1;
    for (p, q) in [
        (-dx, a[0] - x0),
        (dx, x1 - a[0]),
        (-dy, a[1] - y0),
        (dy, y1 - a[1]),
    ] {
        if p == 0 {
            if q < 0 {
                return false;
            }
        } else {
            let (tn, td) = if p > 0 { (q, p) } else { (-q, -p) };
            if p < 0 {
                if less(n0, d0, tn, td) {
                    n0 = tn;
                    d0 = td;
                }
            } else if less(tn, td, n1, d1) {
                n1 = tn;
                d1 = td;
            }
            if less(n1, d1, n0, d0) || (n1 * d0 == n0 * d1) {
                // t1 <= t0: empty or single point; point grazes abstain.
                return false;
            }
        }
    }
    less(n0, d0, n1, d1)
}

fn segment_meets_square(a: [i64; 2], b: [i64; 2], square: ([i64; 2], [i64; 2])) -> bool {
    // Invariant: closed contact, including a point touch, counts.
    if clip_positive(a, b, square) {
        return true;
    }
    let ([x0, y0], [x1, y1]) = square;
    for p in [a, b] {
        if p[0] >= x0 && p[0] <= x1 && p[1] >= y0 && p[1] <= y1 {
            return true;
        }
    }
    for c in [[x0, y0], [x1, y0], [x1, y1], [x0, y1]] {
        if on_segment_i(c, a, b) {
            return true;
        }
    }
    false
}

fn pixel_square(left: i32, top: i32, i: i32, j: i32) -> ([i64; 2], [i64; 2]) {
    // Source: bitmap row j covers y-down [top+j, top+j+1); y-up negates to
    // [-(top+j)-1, -(top+j)]. 26.6 scale keeps every bound integral.
    let x0 = (i64::from(left) + i64::from(i)) * 64;
    let yhi = -(i64::from(top) + i64::from(j)) * 64;
    ([x0, yhi - 64], [x0 + 64, yhi])
}

fn attribute(
    square: ([i64; 2], [i64; 2]),
    caps: &[Cap],
    fitted: &[ContourI],
    fit_hulls: &[Vec<Vec<[i64; 2]>>],
    work: &mut Work,
) -> Result<Option<usize>, Error> {
    // Source: geometric span ownership (cap contour only, incident wedge
    // allowed); abstains on multiple, other-contour, same-contour-nonincident
    // or curve-hull contact, where zero-touch ambiguity also abstains.
    let mut hit = None;
    for (k, cap) in caps.iter().enumerate() {
        work.step(1)?;
        if clip_positive(cap.a, cap.b, square) {
            if hit.is_some() {
                return Ok(None);
            }
            hit = Some(k);
        }
    }
    let k = match hit {
        Some(k) => k,
        None => return Ok(None),
    };
    let cap = &caps[k];
    let n = fitted[cap.contour].edges.len();
    let allowed = [cap.edge, (cap.edge + n - 1) % n, (cap.edge + 1) % n];
    for (ci, contour) in fitted.iter().enumerate() {
        for (ei, (c, d)) in contour.edges.iter().enumerate() {
            if ci == cap.contour && allowed.contains(&ei) {
                continue;
            }
            work.step(1)?;
            if segment_meets_square(*c, *d, square) {
                return Ok(None);
            }
        }
        for hull in &fit_hulls[ci] {
            work.step(1)?;
            // Invariant: hull contact (incl. point touch) counts as contact.
            if hull_meets_square(hull, square) {
                return Ok(None);
            }
        }
    }
    Ok(Some(k))
}
