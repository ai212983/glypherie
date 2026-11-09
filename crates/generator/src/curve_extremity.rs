//! Smooth-arc extremity phase placement for bilevel scan conversion.
//!
//! [Model and assessment](../../../docs/revisions/001/03-spacing-kerning.md#curve-extremity-phase).
//!
//! Hersch 1995 "Displacement" (Fig. 5) keeps each arc extremity's phase
//! (distance from the pixel center) inside a stated window; Hu (thesis
//! section 4.5.2.2) cites the 1/16-9/16 window as preventing single-pixel
//! spurs and flat long runs at smooth loop extrema. Hobby 1993 section 3.3
//! diagnoses the cause (tangent near a pixel-square middle) and states the
//! horizontal rule from the vertical one by axis symmetry. Only the window's
//! lower edge is adopted here, as the minimal interior-ward placement that
//! leaves the excluded phase-0 placement; the window choice within
//! stays with the sources and the sweep evidence.
//!
//! Project adaptation: bounded local fitting of each smooth axis
//! extremum (Hobby section 6 constraints on Bezier controls, Shamir
//! feature/Dist/Ratio relations). Phase is signed: the outward-normal
//! distance from the nearest pixel center. Each qualifying extremum moves
//! interior-ward to the interior-side window edge (at most 1/8 px at the
//! apex), editing only its incident segments: a joint apex and its
//! axis-aligned incident controls translate together, fixed shoulder
//! endpoints anchor the crown, and an interior apex moves its controls by
//! the stationary-point weight. Subordinate extrema therefore move
//! without dragging a flat stem top or another end of the contour.
//! Borders paired by overlapping incident spans in the same contour or in
//! a source-and-fitted nest share one deficit, so the apex wall is exact;
//! an already-clear paired inner border follows a certified outer deficit
//! when its landing stays phase-valid and ordered, and any other paired
//! disagreement freezes that pair. Sharp corners, cusps, plateaus,
//! diagonal-owned curves, native-owned axes and segment-sharing conflicts
//! abstain (no per-glyph exceptions).

use crate::{fail, probe::FittedCommand, Error};
use serde::{Deserialize, Serialize};

pub const MODEL: &str = "extremity-phase-05";
// Hu section 4.5.2.2, citing Hersch95: phase window lower edge. An extremum
// nearer a pixel center than this moves interior-ward to the interior-side
// edge: an inner-side end by its shortfall, an outer-side end across its
// pixel center (at most twice the edge distance).
const PHASE_MIN_PX: f64 = 1.0 / 16.0;
// Maximum interior-ward movement of one loop end (an outer-side extremum
// just short of the next window edge crosses its center to the far edge).
const MAX_END_PX: f64 = 2.0 * PHASE_MIN_PX;
// Shared computational bound with the existing outline fitting stages.
const MAX_COMMANDS: usize = crate::diagonal_fitting::MAX_COMMANDS;

/// One local extremum correction, for capture and replay. `segment` is the
/// incident segment of a joint apex (its end joint) or the segment holding
/// an interior stationary apex; `delta` is the signed axis displacement
/// of the apex itself (controls move by the stationary weight).
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct LocalCorrection {
    pub contour: usize,
    pub axis: usize,
    pub max: bool,
    pub segment: usize,
    pub interior: bool,
    #[serde(default)]
    pub flat: bool,
    pub delta: f64,
}

/// Backwards-compatible name for the recorded correction record.
pub type LoopCorrection = LocalCorrection;

pub struct Fit {
    pub commands: Vec<FittedCommand>,
    pub applied: bool,
    pub loops: Vec<LoopCorrection>,
}

#[derive(Clone, Copy)]
struct Pt {
    x: f64,
    y: f64,
}

impl Pt {
    fn axis(&self, axis: usize) -> f64 {
        if axis == 0 {
            self.x
        } else {
            self.y
        }
    }
    fn other(&self, axis: usize) -> f64 {
        if axis == 0 {
            self.y
        } else {
            self.x
        }
    }
}

enum Seg {
    Line { a: Pt, b: Pt },
    Quad { a: Pt, c: Pt, b: Pt },
    Cubic { a: Pt, c1: Pt, c2: Pt, b: Pt },
}

fn pt(x: f32, y: f32) -> Result<Pt, Error> {
    let (x, y) = (f64::from(x), f64::from(y));
    if !x.is_finite() || !y.is_finite() {
        return Err(fail("extremity phase requires finite outline coordinates"));
    }
    Ok(Pt { x, y })
}

fn seg_endpoints(seg: &Seg) -> (Pt, Pt) {
    match *seg {
        Seg::Line { a, b } => (a, b),
        Seg::Quad { a, b, .. } => (a, b),
        Seg::Cubic { a, b, .. } => (a, b),
    }
}

/// Parse one closed contour into segments. The implicit closing edge back
/// to the move point is a real straight segment for scan conversion.
fn parse_contour(contour: &[FittedCommand]) -> Result<Vec<Seg>, Error> {
    let mut segs = Vec::new();
    let mut first: Option<Pt> = None;
    let mut pen: Option<Pt> = None;
    for command in contour {
        match *command {
            FittedCommand::MoveTo(x, y) => {
                if pen.is_some() {
                    return Err(fail("extremity phase contour has multiple moves"));
                }
                let p = pt(x, y)?;
                first = Some(p);
                pen = Some(p);
            }
            FittedCommand::LineTo(x, y) => {
                let a = pen.ok_or_else(|| fail("extremity phase segment has no contour"))?;
                let b = pt(x, y)?;
                segs.push(Seg::Line { a, b });
                pen = Some(b);
            }
            FittedCommand::QuadTo(x1, y1, x, y) => {
                let a = pen.ok_or_else(|| fail("extremity phase segment has no contour"))?;
                let b = pt(x, y)?;
                segs.push(Seg::Quad {
                    a,
                    c: pt(x1, y1)?,
                    b,
                });
                pen = Some(b);
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                let a = pen.ok_or_else(|| fail("extremity phase segment has no contour"))?;
                let b = pt(x, y)?;
                segs.push(Seg::Cubic {
                    a,
                    c1: pt(x1, y1)?,
                    c2: pt(x2, y2)?,
                    b,
                });
                pen = Some(b);
            }
            FittedCommand::Close => {}
        }
    }
    let (Some(start), Some(end)) = (first, pen) else {
        return Err(fail("extremity phase contour is empty"));
    };
    if segs.is_empty() {
        return Err(fail("extremity phase contour is empty"));
    }
    if end.x != start.x || end.y != start.y {
        segs.push(Seg::Line { a: end, b: start });
    }
    Ok(segs)
}

/// True outline values of one segment along an axis: endpoints plus any
/// interior stationary point (axis-aligned tangent by construction).
fn segment_values(seg: &Seg, axis: usize) -> Result<Vec<(f64, bool)>, Error> {
    // (value, is_interior)
    let mut out = Vec::new();
    match *seg {
        Seg::Line { a, b } => {
            out.push((a.axis(axis), false));
            out.push((b.axis(axis), false));
        }
        Seg::Quad { a, c, b } => {
            out.push((a.axis(axis), false));
            out.push((b.axis(axis), false));
            let (a, c, b) = (a.axis(axis), c.axis(axis), b.axis(axis));
            let denom = (a - c) - (c - b);
            if denom != 0.0 && denom.is_finite() {
                let t = (a - c) / denom;
                if t > 0.0 && t < 1.0 && t.is_finite() {
                    let mt = 1.0 - t;
                    out.push((mt * mt * a + 2.0 * mt * t * c + t * t * b, true));
                }
            }
        }
        Seg::Cubic { a, c1, c2, b } => {
            out.push((a.axis(axis), false));
            out.push((b.axis(axis), false));
            let (a, c1, c2, b) = (a.axis(axis), c1.axis(axis), c2.axis(axis), b.axis(axis));
            let qa = 3.0 * (-a + 3.0 * c1 - 3.0 * c2 + b);
            let qb = 6.0 * (a - 2.0 * c1 + c2);
            let qc = 3.0 * (c1 - a);
            let mut roots = Vec::new();
            if qa != 0.0 && qa.is_finite() {
                let disc = qb * qb - 4.0 * qa * qc;
                if disc < 0.0 || !disc.is_finite() {
                    return Ok(out);
                }
                let sq = disc.sqrt();
                roots.push((-qb + sq) / (2.0 * qa));
                roots.push((-qb - sq) / (2.0 * qa));
            } else if qb != 0.0 && qb.is_finite() {
                roots.push(-qc / qb);
            }
            for t in roots {
                if t > 0.0 && t < 1.0 && t.is_finite() {
                    let mt = 1.0 - t;
                    out.push((
                        mt * mt * mt * a
                            + 3.0 * mt * mt * t * c1
                            + 3.0 * mt * t * t * c2
                            + t * t * t * b,
                        true,
                    ));
                }
            }
        }
    }
    if out.iter().any(|(v, _)| !v.is_finite()) {
        return Err(fail("extremity phase segment extremum is non-finite"));
    }
    Ok(out)
}

#[cfg(test)]
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum EndKind {
    Flat,
    Smooth,
    Other,
}

/// Near control point of a joint: the adjacent control point, or the
/// neighboring joint for straight lines.
fn near_point(seg: &Seg, at_start: bool) -> Pt {
    match *seg {
        Seg::Line { a, b } => {
            if at_start {
                b
            } else {
                a
            }
        }
        Seg::Quad { c, .. } => c,
        Seg::Cubic { c1, c2, .. } => {
            if at_start {
                c1
            } else {
                c2
            }
        }
    }
}

/// Classify one loop end (extremum) along an axis.
///
/// `Flat`: a straight run attains the extremum (stem/flat ownership).
/// `Smooth`: only smooth curve points (axis-aligned tangents, strict
/// neighbors) attain it (round-overshoot ownership). Anything else (sharp
/// corners, plateaus, degenerate contacts) is `Other` and abstains.
#[cfg(test)]
fn classify_end(segs: &[Seg], axis: usize, is_max: bool) -> EndKind {
    let mut extremum = if is_max {
        f64::NEG_INFINITY
    } else {
        f64::INFINITY
    };
    let mut values: Vec<Vec<(f64, bool)>> = Vec::new();
    for seg in segs {
        let vals = match segment_values(seg, axis) {
            Ok(v) => v,
            Err(_) => return EndKind::Other,
        };
        for (v, _) in &vals {
            extremum = if is_max {
                extremum.max(*v)
            } else {
                extremum.min(*v)
            };
        }
        values.push(vals);
    }
    if !extremum.is_finite() {
        return EndKind::Other;
    }
    let at = |v: f64| v == extremum;
    // Straight runs at the extremum own it as a flat.
    for seg in segs {
        let flat = match *seg {
            Seg::Line { a, b } => at(a.axis(axis)) && at(b.axis(axis)),
            Seg::Quad { a, c, b } => at(a.axis(axis)) && at(c.axis(axis)) && at(b.axis(axis)),
            Seg::Cubic { a, c1, c2, b } => {
                at(a.axis(axis)) && at(c1.axis(axis)) && at(c2.axis(axis)) && at(b.axis(axis))
            }
        };
        if flat {
            return EndKind::Flat;
        }
    }
    // On-curve joints at the extremum must be smooth pass-throughs: both
    // near controls share the extremum level (axis-aligned tangents) with
    // the joint strictly between them, while the neighboring joints sit
    // strictly interior.
    let n = segs.len();
    let mut smooth_attainers = 0u32;
    for i in 0..n {
        // The joint is the end of segs[i] and the start of segs[i+1].
        let (_, end) = seg_endpoints(&segs[i]);
        if !at(end.axis(axis)) {
            continue;
        }
        let prev = &segs[i];
        let next = &segs[(i + 1) % n];
        if near_point(prev, false).axis(axis) != extremum
            || near_point(next, true).axis(axis) != extremum
        {
            return EndKind::Other;
        }
        // Tangent continuity through the joint: the incoming travel
        // (joint minus incoming control) and outgoing travel (outgoing
        // control minus joint) must be collinear continuations, never a
        // cusp or reversal. Axis-aligned handles make both tangents lie
        // along the other axis; the product is positive only for a
        // strict pass-through with controls on opposite sides.
        let cin = near_point(prev, false);
        let cout = near_point(next, true);
        let tin = end.other(axis) - cin.other(axis);
        let tout = cout.other(axis) - end.other(axis);
        if !(tin * tout > 0.0) {
            return EndKind::Other;
        }
        // Neighboring joints strictly interior on both sides.
        let (pstart, _) = seg_endpoints(prev);
        let (_, nend) = seg_endpoints(next);
        let inner = |v: f64| {
            if is_max {
                v < extremum
            } else {
                v > extremum
            }
        };
        if !inner(pstart.axis(axis)) || !inner(nend.axis(axis)) {
            return EndKind::Other;
        }
        smooth_attainers += 1;
    }
    // Curve-interior stationary points at the extremum are smooth by
    // construction; a repeated one on a segment is a degenerate plateau.
    // Endpoints are joints, handled above, so only interior hits count.
    for (vals, seg) in values.iter().zip(segs) {
        if vals
            .iter()
            .filter(|(v, interior)| *interior && at(*v))
            .count()
            > 1
        {
            return EndKind::Other;
        }
        if vals.iter().any(|(v, interior)| *interior && at(*v)) {
            let (a, b) = seg_endpoints(seg);
            let inner = |v: f64| {
                if is_max {
                    v < extremum
                } else {
                    v > extremum
                }
            };
            if !inner(a.axis(axis)) || !inner(b.axis(axis)) {
                return EndKind::Other;
            }
            smooth_attainers += 1;
        }
    }
    // Near-touch guard: a segment that never attains the extremum must
    // not touch its level either. An off-curve control at the extremum
    // level with the curve strictly below is a plateau-adjacent contact
    // and abstains; handles of attaining segments are already certified
    // by the joint and stationary checks above.
    for (vals, seg) in values.iter().zip(segs) {
        if vals.iter().any(|(v, _)| at(*v)) {
            continue;
        }
        let touched = match *seg {
            Seg::Line { .. } => false,
            Seg::Quad { c, .. } => at(c.axis(axis)),
            Seg::Cubic { c1, c2, .. } => at(c1.axis(axis)) || at(c2.axis(axis)),
        };
        if touched {
            return EndKind::Other;
        }
    }
    if smooth_attainers > 0 {
        EndKind::Smooth
    } else {
        EndKind::Other
    }
}

/// Nearest pixel center on the half-integer grid (Hobby section 3.3 grid
/// lines divide pixel squares; our scanner centers fill on half-integers).
fn nearest_center(value: f64) -> f64 {
    (value - 0.5).round() + 0.5
}

/// Signed phase: the extremum's outward-normal distance from its nearest
/// pixel center. Positive means the extremum lies on the outer side of the
/// center (beyond it, away from the loop interior); negative means the
/// inner side. The unsigned distance is the Hersch/Hu window phase; the
/// sign orients the interior-ward correction. Exact centers read 0 and take
/// the interior-ward tie break (overshoot suppression, never growth).
fn outward_gap(extremum: f64, is_max: bool) -> f64 {
    let signed = extremum - nearest_center(extremum);
    if is_max {
        signed
    } else {
        -signed
    }
}

#[cfg(test)]
fn outline_extremum(segs: &[Seg], axis: usize, is_max: bool) -> Option<f64> {
    let mut extremum = if is_max {
        f64::NEG_INFINITY
    } else {
        f64::INFINITY
    };
    for seg in segs {
        for (v, _) in segment_values(seg, axis).ok()? {
            extremum = if is_max {
                extremum.max(v)
            } else {
                extremum.min(v)
            };
        }
    }
    extremum.is_finite().then_some(extremum)
}

fn bbox(segs: &[Seg]) -> [f64; 4] {
    let mut bb = [
        f64::INFINITY,
        f64::INFINITY,
        f64::NEG_INFINITY,
        f64::NEG_INFINITY,
    ];
    let eat = |bb: &mut [f64; 4], p: Pt| {
        bb[0] = bb[0].min(p.x);
        bb[1] = bb[1].min(p.y);
        bb[2] = bb[2].max(p.x);
        bb[3] = bb[3].max(p.y);
    };
    for seg in segs {
        let (a, b) = seg_endpoints(seg);
        eat(&mut bb, a);
        eat(&mut bb, b);
        match *seg {
            Seg::Line { .. } => {}
            Seg::Quad { c, .. } => eat(&mut bb, c),
            Seg::Cubic { c1, c2, .. } => {
                eat(&mut bb, c1);
                eat(&mut bb, c2);
            }
        }
    }
    bb
}

/// Strict two-dimensional bbox containment: every wall of the inner loop
/// sits strictly inside the outer loop's walls.
fn strictly_contains(outer: &[f64; 4], inner: &[f64; 4]) -> bool {
    outer[0] < inner[0] && outer[1] < inner[1] && inner[2] < outer[2] && inner[3] < outer[3]
}

fn contour_ranges(commands: &[FittedCommand]) -> Option<Vec<(usize, usize)>> {
    let mut ranges = Vec::new();
    let mut open: Option<usize> = None;
    for (i, command) in commands.iter().enumerate() {
        match command {
            FittedCommand::MoveTo(..) => {
                if open.is_some() {
                    return None;
                }
                open = Some(i);
            }
            FittedCommand::Close => {
                let Some(start) = open.take() else {
                    return None;
                };
                ranges.push((start, i + 1));
            }
            _ => {
                if open.is_none() {
                    return None;
                }
            }
        }
    }
    if open.is_some() {
        return None;
    }
    Some(ranges)
}

fn discriminants(commands: &[FittedCommand]) -> Vec<u8> {
    commands
        .iter()
        .map(|c| match c {
            FittedCommand::MoveTo(..) => 0,
            FittedCommand::LineTo(..) => 1,
            FittedCommand::QuadTo(..) => 2,
            FittedCommand::CurveTo(..) => 3,
            FittedCommand::Close => 4,
        })
        .collect()
}

fn axis_values(command: &FittedCommand, axis: usize) -> Vec<f32> {
    match *command {
        FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => {
            vec![if axis == 0 { x } else { y }]
        }
        FittedCommand::QuadTo(x1, y1, x, y) => {
            let (a, b) = if axis == 0 { (x1, x) } else { (y1, y) };
            vec![a, b]
        }
        FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
            let (a, b, c) = if axis == 0 { (x1, x2, x) } else { (y1, y2, y) };
            vec![a, b, c]
        }
        FittedCommand::Close => vec![],
    }
}

#[derive(Clone, Debug)]
struct Feature {
    contour: usize,
    axis: usize,
    is_max: bool,
    segment: usize,
    interior: bool,
    flat: bool,
    movable: bool,
    t: f64,
    value: f64,
    transverse: f64,
    span: (f64, f64),
    far: (f64, f64),
    deficit: f64,
    delta: f64,
}

fn seg_point(seg: &Seg, t: f64) -> Pt {
    match *seg {
        Seg::Line { a, b } => Pt {
            x: a.x + (b.x - a.x) * t,
            y: a.y + (b.y - a.y) * t,
        },
        Seg::Quad { a, c, b } => {
            let m = 1.0 - t;
            Pt {
                x: m * m * a.x + 2.0 * m * t * c.x + t * t * b.x,
                y: m * m * a.y + 2.0 * m * t * c.y + t * t * b.y,
            }
        }
        Seg::Cubic { a, c1, c2, b } => {
            let m = 1.0 - t;
            Pt {
                x: m * m * m * a.x
                    + 3.0 * m * m * t * c1.x
                    + 3.0 * m * t * t * c2.x
                    + t * t * t * b.x,
                y: m * m * m * a.y
                    + 3.0 * m * m * t * c1.y
                    + 3.0 * m * t * t * c2.y
                    + t * t * t * b.y,
            }
        }
    }
}

fn stationary_ts(seg: &Seg, axis: usize) -> Vec<f64> {
    match *seg {
        Seg::Line { .. } => Vec::new(),
        Seg::Quad { a, c, b } => {
            let (a, c, b) = (a.axis(axis), c.axis(axis), b.axis(axis));
            let d = (a - c) - (c - b);
            if d == 0.0 {
                return Vec::new();
            }
            let t = (a - c) / d;
            if t > 0.0 && t < 1.0 {
                vec![t]
            } else {
                Vec::new()
            }
        }
        Seg::Cubic { a, c1, c2, b } => {
            let (a, c1, c2, b) = (a.axis(axis), c1.axis(axis), c2.axis(axis), b.axis(axis));
            let qa = 3.0 * (-a + 3.0 * c1 - 3.0 * c2 + b);
            let qb = 6.0 * (a - 2.0 * c1 + c2);
            let qc = 3.0 * (c1 - a);
            let mut roots = Vec::new();
            if qa != 0.0 {
                let disc = qb * qb - 4.0 * qa * qc;
                if disc >= 0.0 {
                    let s = disc.sqrt();
                    roots.push((-qb + s) / (2.0 * qa));
                    roots.push((-qb - s) / (2.0 * qa));
                }
            } else if qb != 0.0 {
                roots.push(-qc / qb);
            }
            roots.retain(|t| *t > 0.0 && *t < 1.0);
            roots
        }
    }
}

fn seg_span(seg: &Seg, axis: usize) -> (f64, f64) {
    let mut pts = Vec::new();
    let (a, b) = seg_endpoints(seg);
    pts.push(a);
    pts.push(b);
    match *seg {
        Seg::Quad { c, .. } => pts.push(c),
        Seg::Cubic { c1, c2, .. } => {
            pts.push(c1);
            pts.push(c2);
        }
        Seg::Line { .. } => {}
    }
    let o = 1 - axis;
    (
        pts.iter().map(|p| p.axis(o)).fold(f64::INFINITY, f64::min),
        pts.iter()
            .map(|p| p.axis(o))
            .fold(f64::NEG_INFINITY, f64::max),
    )
}

/// All smooth local axis extrema of one contour: joint apexes with
/// axis-aligned incident controls and strict interior neighbours, plus
/// interior stationary apexes with strict interior endpoints. Flat runs,
/// sharp joints, cusps and plateau contacts produce no feature.
fn detect_features(segs: &[Seg], contour: usize, axis: usize) -> Vec<Feature> {
    let n = segs.len();
    let mut out = Vec::new();
    if n == 0 {
        return out;
    }
    for is_max in [true, false] {
        let strict = |v: f64, ext: f64| if is_max { v < ext } else { v > ext };
        for i in 0..n {
            let (_, joint) = seg_endpoints(&segs[i]);
            let v = joint.axis(axis);
            let next = &segs[(i + 1) % n];
            let cin = near_point(&segs[i], false);
            let cout = near_point(next, true);
            if cin.axis(axis) != v || cout.axis(axis) != v {
                continue;
            }
            let tin = joint.other(axis) - cin.other(axis);
            let tout = cout.other(axis) - joint.other(axis);
            if !(tin * tout > 0.0) {
                continue;
            }
            let (ps, _) = seg_endpoints(&segs[i]);
            let (_, ne) = seg_endpoints(next);
            if !strict(ps.axis(axis), v) || !strict(ne.axis(axis), v) {
                continue;
            }
            let s1 = seg_span(&segs[i], axis);
            let s2 = seg_span(next, axis);
            let deficit = phase_deficit(v, is_max);
            out.push(Feature {
                contour,
                axis,
                is_max,
                segment: i,
                interior: false,
                flat: false,
                movable: true,
                t: 1.0,
                value: v,
                transverse: joint.other(axis),
                span: (s1.0.min(s2.0), s1.1.max(s2.1)),
                far: (ps.axis(axis), ne.axis(axis)),
                deficit,
                delta: 0.0,
            });
        }
        for (si, seg) in segs.iter().enumerate() {
            for t in stationary_ts(seg, axis) {
                let p = seg_point(seg, t);
                let v = p.axis(axis);
                let (a, b) = seg_endpoints(seg);
                if !strict(a.axis(axis), v) || !strict(b.axis(axis), v) {
                    continue;
                }
                // A second stationary point on the same segment at the same
                // level is a plateau, not a single crown.
                if stationary_ts(seg, axis)
                    .iter()
                    .filter(|u| (seg_point(seg, **u).axis(axis) - v).abs() < 1e-12)
                    .count()
                    > 1
                {
                    continue;
                }
                let deficit = phase_deficit(v, is_max);
                out.push(Feature {
                    contour,
                    axis,
                    is_max,
                    segment: si,
                    interior: true,
                    flat: false,
                    movable: true,
                    t,
                    value: v,
                    transverse: p.other(axis),
                    span: seg_span(seg, axis),
                    far: (a.axis(axis), b.axis(axis)),
                    deficit,
                    delta: 0.0,
                });
            }
        }
        // Flat runs and non-smooth local extrema never initiate a move,
        // but they are borders: a flat run may follow a paired outer
        // deficit, and any other such border freezes its pair.
        for (si, seg) in segs.iter().enumerate() {
            let pts: Vec<Pt> = {
                let (a, b) = seg_endpoints(seg);
                let mut v = vec![a, b];
                match *seg {
                    Seg::Quad { c, .. } => v.push(c),
                    Seg::Cubic { c1, c2, .. } => {
                        v.push(c1);
                        v.push(c2);
                    }
                    Seg::Line { .. } => {}
                }
                v
            };
            if pts.iter().all(|p| p.axis(axis) == pts[0].axis(axis))
                && pts
                    .iter()
                    .map(|p| p.other(axis))
                    .fold(f64::INFINITY, f64::min)
                    < pts
                        .iter()
                        .map(|p| p.other(axis))
                        .fold(f64::NEG_INFINITY, f64::max)
            {
                let v = pts[0].axis(axis);
                let (a, _) = seg_endpoints(&segs[(si + n - 1) % n]);
                let (_, b) = seg_endpoints(&segs[(si + 1) % n]);
                if strict(a.axis(axis), v)
                    && strict(b.axis(axis), v)
                    && !out
                        .iter()
                        .any(|f: &Feature| f.is_max == is_max && f.segment == si)
                {
                    let sp = seg_span(seg, axis);
                    out.push(Feature {
                        contour,
                        axis,
                        is_max,
                        segment: si,
                        interior: false,
                        flat: true,
                        movable: false,
                        t: 0.0,
                        value: v,
                        transverse: (sp.0 + sp.1) / 2.0,
                        span: sp,
                        far: (a.axis(axis), b.axis(axis)),
                        deficit: 0.0,
                        delta: 0.0,
                    });
                }
                continue;
            }
            // Non-smooth joint extremum (sharp/other border).
            let (_, joint) = seg_endpoints(seg);
            let v = joint.axis(axis);
            let (ps, _) = seg_endpoints(seg);
            let (_, ne) = seg_endpoints(&segs[(si + 1) % n]);
            if strict(ps.axis(axis), v)
                && strict(ne.axis(axis), v)
                && !out
                    .iter()
                    .any(|f: &Feature| f.is_max == is_max && !f.interior && f.segment == si)
            {
                let s1 = seg_span(seg, axis);
                let s2 = seg_span(&segs[(si + 1) % n], axis);
                out.push(Feature {
                    contour,
                    axis,
                    is_max,
                    segment: si,
                    interior: false,
                    flat: false,
                    movable: false,
                    t: 1.0,
                    value: v,
                    transverse: joint.other(axis),
                    span: (s1.0.min(s2.0), s1.1.max(s2.1)),
                    far: (ps.axis(axis), ne.axis(axis)),
                    deficit: 0.0,
                    delta: 0.0,
                });
            }
        }
    }
    out
}

fn add_axis(command: &mut FittedCommand, axis: usize, delta: f64, which: usize) {
    // which: 0 endpoint/start, 1 first control, 2 second control
    let set = |x: &mut f32, y: &mut f32| {
        if axis == 0 {
            *x = (*x as f64 + delta) as f32;
        } else {
            *y = (*y as f64 + delta) as f32;
        }
    };
    match command {
        FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => {
            if which == 0 {
                set(x, y);
            }
        }
        FittedCommand::QuadTo(x1, y1, x, y) => {
            if which == 0 {
                set(x, y);
            } else if which == 1 {
                set(x1, y1);
            }
        }
        FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
            if which == 0 {
                set(x, y);
            } else if which == 1 {
                set(x1, y1);
            } else if which == 2 {
                set(x2, y2);
            }
        }
        FittedCommand::Close => {}
    }
}

fn cmd_seg_count(contour: &[FittedCommand]) -> usize {
    contour
        .iter()
        .filter(|c| !matches!(c, FittedCommand::MoveTo(..) | FittedCommand::Close))
        .count()
}

/// Apply one recorded local correction to a mutable command list.
fn apply_local(
    commands: &mut [FittedCommand],
    ranges: &[(usize, usize)],
    corr: &LocalCorrection,
    fitted_segs: &[Vec<Seg>],
) -> Result<(), Error> {
    let &(a, b) = ranges
        .get(corr.contour)
        .ok_or_else(|| fail("extremity phase replay contour index out of range"))?;
    let contour = &mut commands[a..b];
    let ncmd = cmd_seg_count(contour);
    let nseg = fitted_segs
        .get(corr.contour)
        .map(|s| s.len())
        .unwrap_or(ncmd);
    if corr.axis > 1
        || corr.delta == 0.0
        || !corr.delta.is_finite()
        || corr.delta.abs() > MAX_END_PX + 1e-12
    {
        return Err(fail("extremity phase replay correction out of bounds"));
    }
    if corr.flat {
        if corr.segment >= ncmd {
            return Err(fail("extremity phase replay segment out of range"));
        }
        let d = corr.delta;
        // Both run endpoints and the adjacent near controls translate.
        add_axis(&mut contour[1 + corr.segment], corr.axis, d, 0);
        if corr.segment == 0 {
            add_axis(&mut contour[0], corr.axis, d, 0);
        } else {
            add_axis(&mut contour[corr.segment], corr.axis, d, 0);
            if matches!(contour[corr.segment], FittedCommand::CurveTo(..)) {
                add_axis(&mut contour[corr.segment], corr.axis, d, 2);
            } else {
                add_axis(&mut contour[corr.segment], corr.axis, d, 1);
            }
        }
        let next = (corr.segment + 1) % nseg;
        if next != 0
            && next < ncmd
            && matches!(
                contour[1 + next],
                FittedCommand::QuadTo(..) | FittedCommand::CurveTo(..)
            )
        {
            add_axis(&mut contour[1 + next], corr.axis, d, 1);
        }
        if matches!(contour[1 + corr.segment], FittedCommand::QuadTo(..)) {
            add_axis(&mut contour[1 + corr.segment], corr.axis, d, 1);
        }
        if matches!(contour[1 + corr.segment], FittedCommand::CurveTo(..)) {
            add_axis(&mut contour[1 + corr.segment], corr.axis, d, 1);
            add_axis(&mut contour[1 + corr.segment], corr.axis, d, 2);
        }
        return Ok(());
    }
    if corr.interior {
        if corr.segment >= ncmd {
            return Err(fail("extremity phase replay segment out of range"));
        }
        let seg = &fitted_segs[corr.contour][corr.segment];
        let ts = stationary_ts(seg, corr.axis);
        // Recompute the stationary weight from the recorded segment.
        let mut applied = false;
        for t in ts {
            let weight = stationary_weight(seg, t);
            if weight <= 0.0 {
                continue;
            }
            let cd = corr.delta / weight;
            if cd.abs() > 2.0 * MAX_END_PX + 1e-12 {
                return Err(fail("extremity phase replay control out of bounds"));
            }
            match &mut contour[1 + corr.segment] {
                FittedCommand::QuadTo(..) => {
                    add_axis(&mut contour[1 + corr.segment], corr.axis, cd, 1);
                    applied = true;
                }
                FittedCommand::CurveTo(..) => {
                    add_axis(&mut contour[1 + corr.segment], corr.axis, cd, 1);
                    add_axis(&mut contour[1 + corr.segment], corr.axis, cd, 2);
                    applied = true;
                }
                _ => return Err(fail("extremity phase replay segment is not a curve")),
            }
            break;
        }
        if !applied {
            return Err(fail("extremity phase replay has no stationary apex"));
        }
        return Ok(());
    }
    // Joint apex: end of segment `segment`.
    if corr.segment >= nseg {
        return Err(fail("extremity phase replay segment out of range"));
    }
    let d = corr.delta;
    if corr.segment < ncmd {
        add_axis(&mut contour[1 + corr.segment], corr.axis, d, 0);
        if matches!(contour[1 + corr.segment], FittedCommand::CurveTo(..)) {
            add_axis(&mut contour[1 + corr.segment], corr.axis, d, 2);
        } else {
            add_axis(&mut contour[1 + corr.segment], corr.axis, d, 1);
        }
    } else {
        // Implicit closing segment: its end joint is the MoveTo point.
        add_axis(&mut contour[0], corr.axis, d, 0);
    }
    let next = (corr.segment + 1) % nseg;
    if next < ncmd {
        // Near-start control of the outgoing segment (first control).
        if matches!(
            contour[1 + next],
            FittedCommand::QuadTo(..) | FittedCommand::CurveTo(..)
        ) {
            add_axis(&mut contour[1 + next], corr.axis, d, 1);
        }
    }
    if next == 0 {
        add_axis(&mut contour[0], corr.axis, d, 0);
        // If the last command segment ends at the start point, it was
        // already moved as the end of `segment` when segment is last.
    }
    Ok(())
}

/// Replay recorded local corrections without re-deriving eligibility.
pub fn replay(
    upstream: &[FittedCommand],
    loops: &[LocalCorrection],
) -> Result<Vec<FittedCommand>, Error> {
    let Some(ranges) = contour_ranges(upstream) else {
        return Err(fail("extremity phase replay requires closed contours"));
    };
    // Parse fitted segments for stationary weights / segment counts.
    let mut segs: Vec<Vec<Seg>> = Vec::new();
    for (a, b) in &ranges {
        segs.push(
            parse_contour(&upstream[*a..*b])
                .map_err(|_| fail("extremity phase replay contour parse failed"))?,
        );
    }
    let mut commands = upstream.to_vec();
    for corr in loops {
        apply_local(&mut commands, &ranges, corr, &segs)?;
    }
    Ok(commands)
}

/// Interior-ward deficit from the signed phase: the window shortfall when the
/// extremum sits inside the excluded band, zero when already clear. (Hu
/// section 4.5.2.2 lower 1/16 edge; Hersch95 displacement window.)
fn phase_deficit(value: f64, is_max: bool) -> f64 {
    let gap = outward_gap(value, is_max);
    if gap.abs() < PHASE_MIN_PX {
        PHASE_MIN_PX + gap
    } else {
        0.0
    }
}

/// Signed interior-ward move for a positive deficit: maxima move down, minima
/// move up; a clear end stays put.
fn inward_delta(deficit: f64, is_max: bool) -> f64 {
    if deficit > 0.0 {
        if is_max {
            -deficit
        } else {
            deficit
        }
    } else {
        0.0
    }
}

/// Stationary-point weight mapping an apex move onto its controls: quads and
/// cubics scale by the Bernstein weight at `t`; lines carry no interior apex.
/// (Hersch Fig. 16 exterior/interior weight control.)
fn stationary_weight(seg: &Seg, t: f64) -> f64 {
    match seg {
        Seg::Quad { .. } => 2.0 * t * (1.0 - t),
        Seg::Cubic { .. } => 3.0 * t * (1.0 - t),
        Seg::Line { .. } => 0.0,
    }
}

/// Segments edited by one feature: the holding segment for an interior apex,
/// the apex segment plus its outgoing neighbor for a joint apex.
fn incident_segments(f: &Feature, loop_len: usize) -> Vec<usize> {
    if f.interior {
        vec![f.segment]
    } else {
        vec![f.segment, (f.segment + 1) % loop_len]
    }
}

/// Validated outline pair for the extremity phases: fitted and source loops
/// parsed from corresponding command ranges. Construction enforces every
/// input contract `fit` previously checked inline (command limit, shape
/// identity, finite bounded coordinates, closed-contour correspondence), so
/// later phases trust this representation.
struct ParsedOutlines {
    up_ranges: Vec<(usize, usize)>,
    fitted_loops: Vec<Vec<Seg>>,
    source_loops: Vec<Vec<Seg>>,
}

/// Parse and validate the source/upstream outline pair. `Ok(None)` abstains
/// (`fit` keeps the upstream outline); `Err` is a hard input error. Checks
/// keep their original order, limits and messages.
fn parse_outline_pair(
    source: &[FittedCommand],
    upstream: &[FittedCommand],
) -> Result<Option<ParsedOutlines>, Error> {
    if source.len() > MAX_COMMANDS || upstream.len() > MAX_COMMANDS {
        return Err(fail("extremity phase outline exceeds command limit"));
    }
    if source.len() != upstream.len() || discriminants(source) != discriminants(upstream) {
        return Ok(None);
    }
    for command in source.iter().chain(upstream) {
        for axis in 0..2 {
            for v in axis_values(command, axis) {
                if !v.is_finite() {
                    return Err(fail("extremity phase requires finite outline coordinates"));
                }
                if v.abs() > 32768.0 {
                    return Err(fail("extremity phase coordinate exceeds supported bounds"));
                }
            }
        }
    }
    let (Some(src_ranges), Some(up_ranges)) = (contour_ranges(source), contour_ranges(upstream))
    else {
        return Ok(None);
    };
    if src_ranges.len() != up_ranges.len() || src_ranges.is_empty() {
        return Ok(None);
    }
    let mut fitted_loops: Vec<Vec<Seg>> = Vec::new();
    let mut source_loops: Vec<Vec<Seg>> = Vec::new();
    for ((a, b), (c, d)) in src_ranges.iter().zip(&up_ranges) {
        if (a, b) != (c, d) {
            return Ok(None);
        }
        let (Ok(f), Ok(s)) = (
            parse_contour(&upstream[*c..*d]),
            parse_contour(&source[*a..*b]),
        ) else {
            return Ok(None);
        };
        fitted_loops.push(f);
        source_loops.push(s);
    }
    Ok(Some(ParsedOutlines {
        up_ranges,
        fitted_loops,
        source_loops,
    }))
}

/// Eligible smooth extrema with exact source correspondence: a joint apex or
/// interior stationary apex certified at the same segment in both outlines.
/// Plateau-adjacent contacts and overweight interior controls lose their
/// deficit here; `delta` is the signed interior-ward move (0 when clear).
fn select_eligible_features(parsed: &ParsedOutlines, native_axes: [bool; 2]) -> Vec<Feature> {
    let mut features: Vec<Feature> = Vec::new();
    for axis in 0..2 {
        if native_axes[axis] {
            continue;
        }
        for ci in 0..parsed.fitted_loops.len() {
            let src_feats = detect_features(&parsed.source_loops[ci], ci, axis);
            for mut f in detect_features(&parsed.fitted_loops[ci], ci, axis) {
                if !src_feats.iter().any(|s| {
                    s.segment == f.segment
                        && s.interior == f.interior
                        && s.is_max == f.is_max
                        && s.flat == f.flat
                        && s.movable == f.movable
                }) {
                    continue;
                }
                // Plateau-adjacent contact: a non-incident control touching
                // the apex level while its curve stays strictly inside.
                if f.movable && plateau_touched(&parsed.fitted_loops, ci, &f) {
                    f.deficit = 0.0;
                }
                // Interior control bound: stationary weight must not
                // amplify the apex move beyond twice the per-end bound.
                if f.interior {
                    let w = stationary_weight(&parsed.fitted_loops[ci][f.segment], f.t);
                    if w <= 0.0 || (f.deficit / w).abs() > 2.0 * MAX_END_PX {
                        f.deficit = 0.0;
                    }
                }
                f.delta = inward_delta(f.deficit, f.is_max);
                features.push(f);
            }
        }
    }
    features
}

/// True when a non-incident control touches the apex level while its curve
/// stays strictly inside: a plateau-adjacent contact, never a single crown.
fn plateau_touched(loops: &[Vec<Seg>], ci: usize, f: &Feature) -> bool {
    let incident = incident_segments(f, loops[ci].len());
    loops[ci].iter().enumerate().any(|(si, seg)| {
        !incident.contains(&si) && {
            let ctrls: Vec<Pt> = match *seg {
                Seg::Quad { c, .. } => vec![c],
                Seg::Cubic { c1, c2, .. } => vec![c1, c2],
                Seg::Line { .. } => vec![],
            };
            ctrls.iter().any(|c| c.axis(f.axis) == f.value)
                && segment_values(seg, f.axis)
                    .map(|vals| {
                        vals.iter()
                            .all(|(v, _)| if f.is_max { *v < f.value } else { *v > f.value })
                    })
                    .unwrap_or(false)
        }
    })
}

/// Paired borders: nearest opposite border by axis value, apex of each inside
/// the other's incident span, same contour or a nest present in both source
/// and fitted boxes. (Hersch Fig. 16 exterior/interior weight with Hobby
/// section 6 and Shamir width, tangent and attachment relations.)
fn discover_pairs(
    features: &[Feature],
    boxes: &[[f64; 4]],
    src_boxes: &[[f64; 4]],
) -> Vec<(usize, usize)> {
    let nested = |i: usize, j: usize| {
        (strictly_contains(&boxes[i], &boxes[j]) && strictly_contains(&src_boxes[i], &src_boxes[j]))
            || (strictly_contains(&boxes[j], &boxes[i])
                && strictly_contains(&src_boxes[j], &src_boxes[i]))
    };
    // Nearest border in each direction, by axis separation.
    let nearest = |i: usize, inward_dir: bool| -> Option<usize> {
        let f = &features[i];
        let mut best: Option<(f64, usize)> = None;
        for (j, g) in features.iter().enumerate() {
            if i == j || f.axis != g.axis || f.is_max != g.is_max {
                continue;
            }
            if f.contour != g.contour && !nested(f.contour, g.contour) {
                continue;
            }
            let sep = if f.is_max == inward_dir {
                f.value - g.value
            } else {
                g.value - f.value
            };
            if sep <= 0.0 {
                continue;
            }
            if g.transverse < f.span.0
                || g.transverse > f.span.1
                || f.transverse < g.span.0
                || f.transverse > g.span.1
            {
                continue;
            }
            if best.map_or(true, |(d, _)| sep < d) {
                best = Some((sep, j));
            }
        }
        best.map(|(_, j)| j)
    };
    let mut pairs: Vec<(usize, usize)> = Vec::new();
    for i in 0..features.len() {
        if let Some(j) = nearest(i, true) {
            if nearest(j, false) == Some(i) {
                let (o, n) = (i, j);
                if !pairs.contains(&(o, n)) {
                    pairs.push((o, n));
                }
            }
        }
    }
    pairs
}

/// A fitted nest without the same source nest, and overlapping or touching
/// non-nested loops, freeze every feature of both contours: pair ownership
/// and clearance both need source correspondence.
fn freeze_unmatched_layouts(features: &mut [Feature], boxes: &[[f64; 4]], src_boxes: &[[f64; 4]]) {
    let mut frozen = vec![false; features.len()];
    for i in 0..boxes.len() {
        for j in (i + 1)..boxes.len() {
            let fit_nest =
                strictly_contains(&boxes[i], &boxes[j]) || strictly_contains(&boxes[j], &boxes[i]);
            let src_nest = strictly_contains(&src_boxes[i], &src_boxes[j])
                || strictly_contains(&src_boxes[j], &src_boxes[i]);
            let overlap = boxes[i][0] <= boxes[j][2]
                && boxes[j][0] <= boxes[i][2]
                && boxes[i][1] <= boxes[j][3]
                && boxes[j][1] <= boxes[i][3];
            if (fit_nest && !src_nest) || (overlap && !fit_nest) {
                for (k, f) in features.iter().enumerate() {
                    if f.contour == i || f.contour == j {
                        frozen[k] = true;
                    }
                }
            }
        }
    }
    for (k, f) in features.iter_mut().enumerate() {
        if frozen[k] {
            f.delta = 0.0;
        }
    }
}

/// Border constraints shared by paired extrema: mutual deficits resolve to
/// one wall, clear followers track certified outer moves, and any other
/// paired or segment-sharing disagreement freezes its features.
fn constrain_borders(features: &mut [Feature], parsed: &ParsedOutlines) {
    let boxes: Vec<[f64; 4]> = parsed.fitted_loops.iter().map(|s| bbox(s)).collect();
    let src_boxes: Vec<[f64; 4]> = parsed.source_loops.iter().map(|s| bbox(s)).collect();
    let pairs = discover_pairs(features, &boxes, &src_boxes);
    freeze_unmatched_layouts(features, &boxes, &src_boxes);
    settle_pair_constraints(features, &parsed.fitted_loops, &pairs);
}

/// Resolve pair and segment-sharing constraints until stable: at most 16
/// passes over the four rules below, matching the original iteration bound.
fn settle_pair_constraints(
    features: &mut [Feature],
    fitted_loops: &[Vec<Seg>],
    pairs: &[(usize, usize)],
) {
    for _ in 0..16 {
        let mut changed = false;
        changed |= settle_pair_deltas(features, pairs);
        changed |= enforce_flat_ordering(features, fitted_loops);
        changed |= freeze_shared_segments(features);
        changed |= freeze_shared_incidents(features, fitted_loops);
        if !changed {
            break;
        }
    }
}

/// One pair rule: conflicting deficits freeze both borders; a clear inner
/// border follows a certified outer deficit to a valid ordered landing.
fn settle_pair_deltas(features: &mut [Feature], pairs: &[(usize, usize)]) -> bool {
    let mut changed = false;
    for &(o, n) in pairs {
        let (do_, dn) = (features[o].delta, features[n].delta);
        if do_ != 0.0 && dn != 0.0 && do_ != dn {
            features[o].delta = 0.0;
            features[n].delta = 0.0;
            changed = true;
        } else if do_ != 0.0 && dn == 0.0 {
            if !features[n].movable && !features[n].flat {
                features[o].delta = 0.0;
                changed = true;
                continue;
            }
            // Clear inner follows only to a valid ordered landing.
            let moved = features[n].value + do_;
            let land_ok = outward_gap(moved, features[n].is_max).abs() >= PHASE_MIN_PX - 1e-12
                && (if features[n].is_max {
                    moved > features[n].far.0 && moved > features[n].far.1
                } else {
                    moved < features[n].far.0 && moved < features[n].far.1
                })
                && (if features[n].is_max {
                    features[o].value + do_ > moved
                } else {
                    features[o].value + do_ < moved
                });
            if land_ok {
                features[n].delta = do_;
            } else {
                features[o].delta = 0.0;
            }
            changed = true;
        } else if do_ == 0.0 && dn != 0.0 {
            features[n].delta = 0.0;
            changed = true;
        }
    }
    changed
}

/// Flat-ordering guard: a moved apex must stay beyond every flat run level
/// it was beyond in its contour.
fn enforce_flat_ordering(features: &mut [Feature], fitted_loops: &[Vec<Seg>]) -> bool {
    let mut changed = false;
    for f in features.iter_mut() {
        if f.delta == 0.0 {
            continue;
        }
        let moved = f.value + f.delta;
        let mut bad = if f.is_max {
            !(moved > f.far.0 && moved > f.far.1)
        } else {
            !(moved < f.far.0 && moved < f.far.1)
        };
        for seg in &fitted_loops[f.contour] {
            if let Seg::Line { a, b } = *seg {
                if a.axis(f.axis) == b.axis(f.axis) {
                    let l = a.axis(f.axis);
                    if (f.is_max && f.value > l && moved <= l)
                        || (!f.is_max && f.value < l && moved >= l)
                    {
                        bad = true;
                    }
                }
            }
        }
        if bad {
            f.delta = 0.0;
            changed = true;
        }
    }
    changed
}

/// Segment-sharing on the same axis freezes both features.
fn freeze_shared_segments(features: &mut [Feature]) -> bool {
    let mut changed = false;
    for i in 0..features.len() {
        for j in (i + 1)..features.len() {
            if features[i].delta != 0.0
                && features[j].delta != 0.0
                && features[i].contour == features[j].contour
                && features[i].axis == features[j].axis
                && features[i].segment == features[j].segment
            {
                features[i].delta = 0.0;
                features[j].delta = 0.0;
                changed = true;
            }
        }
    }
    changed
}

/// Joint features sharing an incident segment (segment or next) freeze both.
fn freeze_shared_incidents(features: &mut [Feature], fitted_loops: &[Vec<Seg>]) -> bool {
    let mut changed = false;
    for i in 0..features.len() {
        for j in (i + 1)..features.len() {
            if features[i].delta == 0.0
                || features[j].delta == 0.0
                || features[i].contour != features[j].contour
                || features[i].axis != features[j].axis
            {
                continue;
            }
            let segs_i = incident_segments(&features[i], fitted_loops[features[i].contour].len());
            let segs_j = incident_segments(&features[j], fitted_loops[features[j].contour].len());
            if segs_i.iter().any(|s| segs_j.contains(s)) {
                features[i].delta = 0.0;
                features[j].delta = 0.0;
                changed = true;
            }
        }
    }
    changed
}

/// Reparse fitted commands into loops over the validated ranges; `None`
/// keeps the upstream outline (the former inline fallback).
fn parse_command_loops(
    commands: &[FittedCommand],
    ranges: &[(usize, usize)],
) -> Option<Vec<Vec<Seg>>> {
    let mut new_loops: Vec<Vec<Seg>> = Vec::new();
    for (a, b) in ranges {
        let Ok(s) = parse_contour(&commands[*a..*b]) else {
            return None;
        };
        new_loops.push(s);
    }
    Some(new_loops)
}

/// Hersch's phase constraint also applies to smooth neighboring extrema
/// moved by a stencil. Preserve their classification and reject changed or
/// new apexes in the excluded band; untouched existing cases abstain from
/// this guard just as they do from fitting eligibility.
fn neighbors_preserved(before_loops: &[Vec<Seg>], after_loops: &[Vec<Seg>]) -> bool {
    for (ci, segs) in after_loops.iter().enumerate() {
        for axis in 0..2 {
            let before = detect_features(&before_loops[ci], ci, axis);
            let after = detect_features(segs, ci, axis);
            let same = |a: &Feature, b: &Feature| {
                a.segment == b.segment
                    && a.interior == b.interior
                    && a.is_max == b.is_max
                    && a.flat == b.flat
            };
            if before
                .iter()
                .filter(|f| f.movable)
                .any(|f| !after.iter().any(|g| g.movable && same(f, g)))
            {
                return false;
            }
            for g in after.iter().filter(|f| f.movable) {
                if outward_gap(g.value, g.is_max).abs() < PHASE_MIN_PX - 1e-6
                    && !before
                        .iter()
                        .any(|f| f.movable && same(f, g) && f.value == g.value)
                {
                    return false;
                }
            }
        }
    }
    true
}

/// Every moved apex re-detects smooth at a valid phase near its target.
fn apexes_landed(new_loops: &[Vec<Seg>], active: &[&Feature]) -> bool {
    for f in active {
        let feats = detect_features(&new_loops[f.contour], f.contour, f.axis);
        let Some(g) = feats.iter().find(|g| {
            g.segment == f.segment
                && g.interior == f.interior
                && g.is_max == f.is_max
                && g.flat == f.flat
        }) else {
            return false;
        };
        if (g.value - (f.value + f.delta)).abs() > 1e-4
            || outward_gap(g.value, g.is_max).abs() < PHASE_MIN_PX - 1e-6
        {
            return false;
        }
    }
    true
}

/// Local smooth-extremity phase correction. See module docs.
pub fn fit(
    source: &[FittedCommand],
    upstream: &[FittedCommand],
    native_axes: [bool; 2],
) -> Result<Fit, Error> {
    let unchanged = || Fit {
        commands: upstream.to_vec(),
        applied: false,
        loops: Vec::new(),
    };
    // Private phases behind the existing interface: validated outline pair,
    // eligible source-certified features, shared border constraints, then
    // application with post-validation. Each phase keeps the original order,
    // tolerances and fallback identity; see the phase owners above.
    let Some(parsed) = parse_outline_pair(source, upstream)? else {
        return Ok(unchanged());
    };
    let mut features = select_eligible_features(&parsed, native_axes);
    if features.iter().all(|f| f.delta == 0.0) {
        return Ok(unchanged());
    }
    constrain_borders(&mut features, &parsed);
    let active: Vec<&Feature> = features.iter().filter(|f| f.delta != 0.0).collect();
    if active.is_empty() {
        return Ok(unchanged());
    }
    let loops: Vec<LocalCorrection> = active
        .iter()
        .map(|f| LocalCorrection {
            contour: f.contour,
            axis: f.axis,
            max: f.is_max,
            segment: f.segment,
            interior: f.interior,
            flat: f.flat,
            delta: f.delta,
        })
        .collect();
    let mut commands = upstream.to_vec();
    for corr in &loops {
        if apply_local(&mut commands, &parsed.up_ranges, corr, &parsed.fitted_loops).is_err() {
            return Ok(unchanged());
        }
    }
    // Post-validation: every moved apex re-detects smooth at a valid
    // phase near its target, and refitting the result abstains.
    let Some(new_loops) = parse_command_loops(&commands, &parsed.up_ranges) else {
        return Ok(unchanged());
    };
    if !neighbors_preserved(&parsed.fitted_loops, &new_loops) {
        return Ok(unchanged());
    }
    if !apexes_landed(&new_loops, &active) {
        return Ok(unchanged());
    }
    for command in &commands {
        for axis in 0..2 {
            for v in axis_values(command, axis) {
                if !v.is_finite() {
                    return Ok(unchanged());
                }
            }
        }
    }
    Ok(Fit {
        commands,
        applied: true,
        loops,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn segs_of(commands: &[FittedCommand]) -> Vec<Seg> {
        parse_contour(commands).unwrap()
    }

    fn arch(top: f64, shoulder: f64, half: f64, base: f64) -> Vec<FittedCommand> {
        let ctl = 2.0 * top - shoulder;
        vec![
            FittedCommand::MoveTo(-half as f32, base as f32),
            FittedCommand::LineTo(-half as f32, shoulder as f32),
            FittedCommand::QuadTo(0.0, ctl as f32, half as f32, shoulder as f32),
            FittedCommand::LineTo(half as f32, base as f32),
            FittedCommand::Close,
        ]
    }

    #[test]
    fn on_center_smooth_top_moves_by_deficit() {
        let src = arch(23.2, 21.2, 10.0, 0.0);
        let up = arch(22.5, 20.5, 10.0, 0.0);
        let fit = fit(&src, &up, [false, false]).unwrap();
        assert!(fit.applied);
        assert_eq!(fit.loops.len(), 1);
        // Top moves down by the full 1/16 deficit; the flat base anchors.
        // True outline maximum (endpoints plus interior stationary points,
        // never off-curve controls).
        let segs = parse_contour(&fit.commands).unwrap();
        let ymax = outline_extremum(&segs, 1, true).unwrap();
        assert_eq!(ymax, 22.5 - 1.0 / 16.0);
    }

    #[test]
    fn smooth_classification_holds_for_arch() {
        let up = arch(22.5, 20.5, 10.0, 0.0);
        let segs = segs_of(&up);
        assert_eq!(classify_end(&segs, 1, true), EndKind::Smooth);
        // The straight base is not a top flat, but the bottom end spans a
        // straight run only if axis-aligned at the minimum: the base edge
        // LineTo(half, base)->Close->MoveTo is axis-aligned at y = base.
        assert_eq!(classify_end(&segs, 1, false), EndKind::Flat);
    }

    #[test]
    fn flat_top_abstains() {
        let flat = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(0.0, 22.5),
            FittedCommand::LineTo(3.0, 22.5),
            FittedCommand::LineTo(3.0, 0.0),
            FittedCommand::Close,
        ];
        let fit = fit(&flat.clone(), &flat, [false, false]).unwrap();
        assert!(!fit.applied);
    }

    #[test]
    fn sharp_apex_abstains() {
        // Pointed arch: straight lines meeting at the top.
        let roof = vec![
            FittedCommand::MoveTo(-4.0, 0.0),
            FittedCommand::LineTo(0.0, 22.5),
            FittedCommand::LineTo(4.0, 0.0),
            FittedCommand::Close,
        ];
        let fit = fit(&roof.clone(), &roof, [false, false]).unwrap();
        assert!(!fit.applied);
        assert_eq!(classify_end(&segs_of(&roof), 1, true), EndKind::Other);
    }

    #[test]
    fn off_center_smooth_top_keeps_outline() {
        let src = arch(23.2, 21.2, 10.0, 0.0);
        let up = arch(22.4, 20.4, 10.0, 0.0);
        let fit = fit(&src, &up, [false, false]).unwrap();
        assert!(!fit.applied);
        assert_eq!(fit.commands, up);
    }

    #[test]
    fn native_y_keeps_coordinates() {
        let src = arch(23.2, 21.2, 10.0, 0.0);
        let up = arch(22.5, 20.5, 10.0, 0.0);
        let fit = fit(&src, &up, [false, true]).unwrap();
        assert!(!fit.applied);
        assert_eq!(fit.commands, up);
    }

    fn real_o_outer_fitted() -> Vec<FittedCommand> {
        vec![
            FittedCommand::MoveTo(2.0, 10.671875),
            FittedCommand::QuadTo(2.0, 5.65625, 4.84375, 2.578125),
            FittedCommand::QuadTo(7.703125, -0.5, 12.484375, -0.5),
            FittedCommand::QuadTo(17.28125, -0.5, 20.140625, 2.578125),
            FittedCommand::QuadTo(23.0, 5.65625, 23.0, 10.671875),
            FittedCommand::LineTo(23.0, 11.375),
            FittedCommand::QuadTo(23.0, 16.34375, 20.140625, 19.421875),
            FittedCommand::QuadTo(17.28125, 22.5, 12.484375, 22.5),
            FittedCommand::QuadTo(7.734375, 22.5, 4.859375, 19.421875),
            FittedCommand::QuadTo(2.0, 16.34375, 2.0, 11.375),
            FittedCommand::Close,
        ]
    }

    fn real_o_outer_source() -> Vec<FittedCommand> {
        vec![
            FittedCommand::MoveTo(1.578125, 10.984375),
            FittedCommand::QuadTo(1.578125, 5.828125, 4.40625, 2.625),
            FittedCommand::QuadTo(7.234375, -0.5625, 11.953125, -0.5625),
            FittedCommand::QuadTo(16.6875, -0.5625, 19.5, 2.625),
            FittedCommand::QuadTo(22.328125, 5.828125, 22.328125, 10.984375),
            FittedCommand::LineTo(22.328125, 11.734375),
            FittedCommand::QuadTo(22.328125, 16.875, 19.5, 20.0625),
            FittedCommand::QuadTo(16.6875, 23.265625, 11.953125, 23.265625),
            FittedCommand::QuadTo(7.234375, 23.265625, 4.40625, 20.0625),
            FittedCommand::QuadTo(1.578125, 16.875, 1.578125, 11.734375),
            FittedCommand::Close,
        ]
    }

    #[test]
    fn real_o_outer_classifies_smooth_both_ends() {
        let fitted = parse_contour(&real_o_outer_fitted()).unwrap();
        let source = parse_contour(&real_o_outer_source()).unwrap();
        assert_eq!(classify_end(&fitted, 1, true), EndKind::Smooth);
        assert_eq!(classify_end(&fitted, 1, false), EndKind::Smooth);
        assert_eq!(classify_end(&source, 1, true), EndKind::Smooth);
        assert_eq!(classify_end(&source, 1, false), EndKind::Smooth);
    }

    /// The arch builder mirrored to the X axis: the smooth apex becomes a
    /// side extremum at x = `top`, opening toward x = `base`.
    fn x_arch(top: f64, shoulder: f64, half: f64, base: f64) -> Vec<FittedCommand> {
        arch(top, shoulder, half, base)
            .into_iter()
            .map(|c| match c {
                FittedCommand::MoveTo(x, y) => FittedCommand::MoveTo(y, x),
                FittedCommand::LineTo(x, y) => FittedCommand::LineTo(y, x),
                FittedCommand::QuadTo(x1, y1, x, y) => FittedCommand::QuadTo(y1, x1, y, x),
                FittedCommand::CurveTo(..) => panic!("suite uses quads"),
                FittedCommand::Close => FittedCommand::Close,
            })
            .collect()
    }

    /// Mirror about the Y axis: a right-side apex becomes a left-side apex.
    fn reflect_x(commands: &[FittedCommand]) -> Vec<FittedCommand> {
        commands
            .iter()
            .map(|c| match *c {
                FittedCommand::MoveTo(x, y) => FittedCommand::MoveTo(-x, y),
                FittedCommand::LineTo(x, y) => FittedCommand::LineTo(-x, y),
                FittedCommand::QuadTo(x1, y1, x, y) => FittedCommand::QuadTo(-x1, y1, -x, y),
                FittedCommand::CurveTo(..) => panic!("suite uses quads"),
                FittedCommand::Close => FittedCommand::Close,
            })
            .collect()
    }

    #[test]
    fn side_extremum_moves_by_deficit_and_reflects() {
        // Axis symmetry: the X rule mirrors the Y rule. Right-side apex on
        // a pixel center moves left; the reflected left-side apex moves
        // right; the straight base anchors in both cases.
        for (src, up, is_max, moved) in [
            (
                x_arch(23.3, 21.3, 10.0, 0.0),
                x_arch(22.5, 20.5, 10.0, 0.0),
                true,
                22.5 - 1.0 / 16.0,
            ),
            (
                reflect_x(&x_arch(23.3, 21.3, 10.0, 0.0)),
                reflect_x(&x_arch(22.5, 20.5, 10.0, 0.0)),
                false,
                -22.5 + 1.0 / 16.0,
            ),
        ] {
            let fit = fit(&src, &up, [false, false]).unwrap();
            assert!(fit.applied);
            assert_eq!(fit.loops.len(), 1);
            assert_eq!(fit.loops[0].axis, 0);
            let segs = parse_contour(&fit.commands).unwrap();
            let edge = outline_extremum(&segs, 0, is_max).unwrap();
            assert_eq!(edge, moved);
        }
    }

    #[test]
    fn moved_joint_keeps_axis_aligned_tangents() {
        // Translating the incident controls keeps both apex tangents horizontal.
        let src = arch(23.2, 21.2, 10.0, 0.0);
        let up = arch(22.5, 20.5, 10.0, 0.0);
        let fit = fit(&src, &up, [false, false]).unwrap();
        assert!(fit.applied);
        let segs = parse_contour(&fit.commands).unwrap();
        // The top joint is the end of the quad arriving at the maximum.
        let top = outline_extremum(&segs, 1, true).unwrap();
        for (i, seg) in segs.iter().enumerate() {
            let (_, end) = seg_endpoints(seg);
            if end.y == top {
                let cin = near_point(seg, false);
                let cout = near_point(&segs[(i + 1) % segs.len()], true);
                assert_eq!(cin.y, top);
                assert_eq!(cout.y, top);
            }
        }
    }

    #[test]
    fn paired_ring_loops_keep_weight() {
        // Outer and inner loops move their own extrema by the same deficit,
        // so the crown stroke thickness is unchanged.
        let outer_src = arch(23.3, 21.3, 10.0, 0.0);
        let outer_up = arch(22.5, 20.5, 10.0, 0.0);
        let inner_src = arch(20.7, 18.7, 7.0, 2.0);
        let inner_up = arch(19.5, 17.5, 7.0, 2.0);
        let mut src = outer_src.clone();
        src.extend(inner_src);
        let mut up = outer_up.clone();
        up.extend(inner_up);
        let fit = fit(&src, &up, [false, false]).unwrap();
        assert!(fit.applied);
        assert_eq!(fit.loops.len(), 2);
        let thickness = |commands: &[FittedCommand]| -> f64 {
            let contours = contour_ranges(commands).unwrap();
            let top = |range: &(usize, usize)| {
                parse_contour(&commands[range.0..range.1])
                    .unwrap()
                    .iter()
                    .flat_map(|s| segment_values(s, 1).unwrap().into_iter().map(|(v, _)| v))
                    .fold(f64::NEG_INFINITY, f64::max)
            };
            top(&contours[0]) - top(&contours[1])
        };
        assert!((thickness(&up) - thickness(&fit.commands)).abs() < 1e-9);
    }

    #[test]
    fn fit_is_deterministic() {
        let src = real_o_outer_source();
        let up = real_o_outer_fitted();
        let a = fit(&src, &up, [false, false]).unwrap();
        let b = fit(&src, &up, [false, false]).unwrap();
        assert_eq!(a.commands, b.commands);
        assert_eq!(a.loops, b.loops);
    }

    #[test]
    fn replay_reproduces_fit() {
        let src = arch(23.2, 21.2, 10.0, 0.0);
        let up = arch(22.5, 20.5, 10.0, 0.0);
        let fit = fit(&src, &up, [false, false]).unwrap();
        assert!(fit.applied);
        assert_eq!(replay(&up, &fit.loops).unwrap(), fit.commands);
    }

    #[test]
    fn mismatched_source_shape_abstains() {
        // Unrelated source geometry never authorizes fitted movement.
        let src = vec![
            FittedCommand::MoveTo(-10.0, 0.0),
            FittedCommand::LineTo(-10.0, 23.2),
            FittedCommand::LineTo(10.0, 23.2),
            FittedCommand::LineTo(10.0, 0.0),
            FittedCommand::Close,
        ];
        let up = arch(22.5, 20.5, 10.0, 0.0);
        let fit = fit(&src, &up, [false, false]).unwrap();
        assert!(!fit.applied);
    }

    fn stepped_arch(top: f64, step: f64, half: f64, base: f64) -> Vec<FittedCommand> {
        // Arch with a flat step near the crown on the left side.
        let shoulder = top - 2.0;
        let ctl = 2.0 * top - shoulder;
        vec![
            FittedCommand::MoveTo(-half as f32, base as f32),
            FittedCommand::LineTo(-half as f32, step as f32),
            FittedCommand::LineTo((-half + 2.0) as f32, step as f32),
            FittedCommand::LineTo((-half + 2.0) as f32, shoulder as f32),
            FittedCommand::QuadTo(0.0, ctl as f32, half as f32, shoulder as f32),
            FittedCommand::LineTo(half as f32, base as f32),
            FittedCommand::Close,
        ]
    }

    #[test]
    fn ordering_veto_keeps_flat_above_round() {
        // Fitted apex 22.5 clears its 22.47 flat, but the 1/16 move would
        // put the round below the flat: the end anchors instead.
        let src = stepped_arch(23.3, 23.0, 10.0, 0.0);
        let up = stepped_arch(22.5, 22.47, 10.0, 0.0);
        let segs = segs_of(&up);
        assert_eq!(classify_end(&segs, 1, true), EndKind::Smooth);
        let fit = fit(&src, &up, [false, false]).unwrap();
        assert!(!fit.applied);
        assert_eq!(fit.commands, up);
    }

    fn capped_arch(top: f32, bottom: f32, ctl: f32, half: f32) -> Vec<FittedCommand> {
        // Flat top cap with a smooth quad undershoot at the bottom.
        vec![
            FittedCommand::MoveTo(-half, bottom),
            FittedCommand::LineTo(-half, top),
            FittedCommand::LineTo(half, top),
            FittedCommand::LineTo(half, bottom),
            FittedCommand::QuadTo(0.0, ctl, -half, bottom),
            FittedCommand::Close,
        ]
    }

    #[test]
    fn flat_end_anchors_while_smooth_end_moves() {
        // Flat top with a smooth on-center bottom: the bottom moves up by
        // the deficit while the flat top stays (near-)exact.
        let src = capped_arch(23.2, 0.5, -1.5, 10.0);
        let up = capped_arch(22.5, 0.5, -1.5, 10.0);
        let fit = fit(&src, &up, [false, false]).unwrap();
        assert!(fit.applied);
        assert_eq!(fit.loops.len(), 1);
        assert_eq!(fit.loops[0].axis, 1);
        let flat_top = fit
            .commands
            .iter()
            .filter_map(|c| match *c {
                FittedCommand::LineTo(_, y) => Some(y),
                _ => None,
            })
            .fold(f32::NEG_INFINITY, f32::max);
        assert!((flat_top - 22.5).abs() < 1e-4);
        // Quad apex maps affinely: (end + control) / 2 must equal the
        // deficit-shifted extremum -0.4375.
        let (end, ctl) = fit
            .commands
            .iter()
            .find_map(|c| match *c {
                FittedCommand::QuadTo(_, c, _, e) => Some((e, c)),
                _ => None,
            })
            .unwrap();
        assert!(((f64::from(end) + f64::from(ctl)) / 2.0 - (-0.4375)).abs() < 1e-6);
    }

    /// Review probe A2: a maximum on the OUTER side of a pixel center must
    /// cross to the interior window edge, never land on the excluded center.
    #[test]
    fn outer_side_max_crosses_to_interior_edge() {
        let src = arch(23.2, 21.2, 10.0, 0.0);
        let up = arch(22.53125, 20.53125, 10.0, 0.0);
        let first = fit(&src, &up, [false, false]).unwrap();
        assert!(first.applied);
        let segs = parse_contour(&first.commands).unwrap();
        let ymax = outline_extremum(&segs, 1, true).unwrap();
        assert!((ymax - (22.5 - 1.0 / 16.0)).abs() < 1e-9);
        // The corrected outline rests at the window edge: a second pass
        // must abstain (idempotence).
        let refit = fit(&src, &first.commands, [false, false]).unwrap();
        assert!(!refit.applied);
    }

    fn flip_y(commands: &[FittedCommand], about: f64) -> Vec<FittedCommand> {
        commands
            .iter()
            .map(|c| match *c {
                FittedCommand::MoveTo(x, y) => {
                    FittedCommand::MoveTo(x, (about - f64::from(y)) as f32)
                }
                FittedCommand::LineTo(x, y) => {
                    FittedCommand::LineTo(x, (about - f64::from(y)) as f32)
                }
                FittedCommand::QuadTo(x1, y1, x, y) => FittedCommand::QuadTo(
                    x1,
                    (about - f64::from(y1)) as f32,
                    x,
                    (about - f64::from(y)) as f32,
                ),
                FittedCommand::CurveTo(..) => panic!("suite uses quads/lines"),
                FittedCommand::Close => FittedCommand::Close,
            })
            .collect()
    }

    /// Mirror of the outer-side case for minima (review probe A6): a minimum
    /// just below its pixel center moves up to the interior edge.
    #[test]
    fn outer_side_min_crosses_to_interior_edge() {
        let src = flip_y(&arch(23.2, 21.2, 10.0, 0.0), 44.0);
        let up = flip_y(&arch(22.53125, 20.53125, 10.0, 0.0), 44.0);
        let first = fit(&src, &up, [false, false]).unwrap();
        assert!(first.applied);
        let segs = parse_contour(&first.commands).unwrap();
        let ymin = outline_extremum(&segs, 1, false).unwrap();
        assert!((ymin - (21.5 + 1.0 / 16.0)).abs() < 1e-9);
        let refit = fit(&src, &first.commands, [false, false]).unwrap();
        assert!(!refit.applied);
    }

    fn rot180(commands: &[FittedCommand]) -> Vec<FittedCommand> {
        commands
            .iter()
            .map(|c| match *c {
                FittedCommand::MoveTo(x, y) => FittedCommand::MoveTo(-x, -y),
                FittedCommand::LineTo(x, y) => FittedCommand::LineTo(-x, -y),
                FittedCommand::QuadTo(x1, y1, x, y) => FittedCommand::QuadTo(-x1, -y1, -x, -y),
                FittedCommand::CurveTo(..) => panic!("suite uses quads/lines"),
                FittedCommand::Close => FittedCommand::Close,
            })
            .collect()
    }

    fn command_gap(a: &[FittedCommand], b: &[FittedCommand]) -> f64 {
        assert_eq!(a.len(), b.len());
        a.iter()
            .zip(b)
            .map(|(p, q)| {
                let vals = |c: &FittedCommand| -> Vec<f64> {
                    match *c {
                        FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => {
                            vec![f64::from(x), f64::from(y)]
                        }
                        FittedCommand::QuadTo(x1, y1, x, y) => {
                            vec![f64::from(x1), f64::from(y1), f64::from(x), f64::from(y)]
                        }
                        FittedCommand::CurveTo(..) => panic!("suite uses quads/lines"),
                        FittedCommand::Close => vec![],
                    }
                };
                vals(p)
                    .into_iter()
                    .zip(vals(q))
                    .map(|(u, v)| (u - v).abs())
                    .fold(0.0, f64::max)
            })
            .fold(0.0, f64::max)
    }

    /// A half-turn maps maxima to minima and negates the outward normal; the
    /// signed rule must commute with it up to float rounding.
    #[test]
    fn half_turn_commutes_with_signed_rule() {
        let src = arch(23.2, 21.2, 10.0, 0.0);
        let up = arch(22.53125, 20.53125, 10.0, 0.0);
        let first = fit(&src, &up, [false, false]).unwrap();
        assert!(first.applied);
        let rsrc = rot180(&src);
        let rup = rot180(&up);
        let rfit = fit(&rsrc, &rup, [false, false]).unwrap();
        assert!(rfit.applied);
        assert_eq!(rfit.loops.len(), first.loops.len());
        assert!(command_gap(&rfit.commands, &rot180(&first.commands)) < 1e-6);
    }

    /// Dense 1/64-px sweep around both sides of every extremum kind: top,
    /// bottom (Y-mirror), right, left (transposed). Positive and negative
    /// center rows cover translation; every corrected end lands exactly on
    /// the interior window edge and the second pass abstains.
    #[test]
    fn dense_phase_sweep_targets_interior_edge_and_sticks() {
        for center in [22.5f64, -12.5f64] {
            for k in -8i32..=8i32 {
                let apex = center + f64::from(k) / 64.0;
                let src = arch(center + 0.7, center - 1.3, 10.0, center - 22.5);
                let up = arch(apex, apex - 2.0, 10.0, apex - 22.5);
                // Y maximum.
                let first = fit(&src, &up, [false, false]).unwrap();
                let o = outward_gap(apex, true);
                if o.abs() < PHASE_MIN_PX {
                    assert!(first.applied, "center={center} k={k}");
                    let segs = parse_contour(&first.commands).unwrap();
                    let got = outline_extremum(&segs, 1, true).unwrap();
                    assert!((got - (center - PHASE_MIN_PX)).abs() < 1e-9);
                    let refit = fit(&src, &first.commands, [false, false]).unwrap();
                    assert!(!refit.applied, "center={center} k={k}");
                } else {
                    assert!(!first.applied, "center={center} k={k}");
                    assert_eq!(first.commands, up);
                }
                // Y minimum (mirror about the center row).
                let msrc = flip_y(&src, 2.0 * center);
                let mup = flip_y(&up, 2.0 * center);
                let mfirst = fit(&msrc, &mup, [false, false]).unwrap();
                let valley = 2.0 * center - apex;
                let mo = outward_gap(valley, false);
                if mo.abs() < PHASE_MIN_PX {
                    assert!(mfirst.applied, "center={center} k={k}");
                    let segs = parse_contour(&mfirst.commands).unwrap();
                    let got = outline_extremum(&segs, 1, false).unwrap();
                    assert!((got - (center + PHASE_MIN_PX)).abs() < 1e-9);
                    let refit = fit(&msrc, &mfirst.commands, [false, false]).unwrap();
                    assert!(!refit.applied, "center={center} k={k}");
                } else {
                    assert!(!mfirst.applied, "center={center} k={k}");
                }
                // X maximum (transpose) and X minimum (transpose + mirror).
                let tsrc: Vec<FittedCommand> = src
                    .iter()
                    .map(|c| match *c {
                        FittedCommand::MoveTo(x, y) => FittedCommand::MoveTo(y, x),
                        FittedCommand::LineTo(x, y) => FittedCommand::LineTo(y, x),
                        FittedCommand::QuadTo(x1, y1, x, y) => FittedCommand::QuadTo(y1, x1, y, x),
                        FittedCommand::CurveTo(..) => panic!("suite uses quads/lines"),
                        FittedCommand::Close => FittedCommand::Close,
                    })
                    .collect();
                let tup: Vec<FittedCommand> = up
                    .iter()
                    .map(|c| match *c {
                        FittedCommand::MoveTo(x, y) => FittedCommand::MoveTo(y, x),
                        FittedCommand::LineTo(x, y) => FittedCommand::LineTo(y, x),
                        FittedCommand::QuadTo(x1, y1, x, y) => FittedCommand::QuadTo(y1, x1, y, x),
                        FittedCommand::CurveTo(..) => panic!("suite uses quads/lines"),
                        FittedCommand::Close => FittedCommand::Close,
                    })
                    .collect();
                let xfirst = fit(&tsrc, &tup, [false, false]).unwrap();
                if o.abs() < PHASE_MIN_PX {
                    assert!(xfirst.applied, "center={center} k={k}");
                    let segs = parse_contour(&xfirst.commands).unwrap();
                    let got = outline_extremum(&segs, 0, true).unwrap();
                    assert!((got - (center - PHASE_MIN_PX)).abs() < 1e-9);
                    let refit = fit(&tsrc, &xfirst.commands, [false, false]).unwrap();
                    assert!(!refit.applied, "center={center} k={k}");
                } else {
                    assert!(!xfirst.applied, "center={center} k={k}");
                }
                let xup_min = reflect_x(&tup);
                let xsrc_min = reflect_x(&tsrc);
                let xmfirst = fit(&xsrc_min, &xup_min, [false, false]).unwrap();
                if mo.abs() < PHASE_MIN_PX {
                    assert!(xmfirst.applied, "center={center} k={k}");
                    let segs = parse_contour(&xmfirst.commands).unwrap();
                    let got = outline_extremum(&segs, 0, false).unwrap();
                    // The X-mirror negates the center row: the interior
                    // edge sits at -center + 1/16.
                    assert!((got - (-center + PHASE_MIN_PX)).abs() < 1e-9);
                    let refit = fit(&xsrc_min, &xmfirst.commands, [false, false]).unwrap();
                    assert!(!refit.applied, "center={center} k={k}");
                } else {
                    assert!(!xmfirst.applied, "center={center} k={k}");
                }
            }
        }
    }

    /// Review B1: nested loops with conflicting phase deficits must abstain
    /// rather than thin the crown by moving one contour alone.
    #[test]
    fn mixed_phase_nested_ring_abstains() {
        let outer_src = arch(23.3, 21.3, 10.0, 0.0);
        let outer_up = arch(22.5, 20.5, 10.0, 0.0);
        let inner_src = arch(20.8, 18.8, 7.0, 2.0);
        let inner_up = arch(19.59375, 17.59375, 7.0, 2.0);
        let mut src = outer_src.clone();
        src.extend(inner_src);
        let mut up = outer_up.clone();
        up.extend(inner_up);
        let fit = fit(&src, &up, [false, false]).unwrap();
        assert!(!fit.applied);
        assert_eq!(fit.commands, up);
    }

    /// Local pairing is per border, not per contour slot: the flat inner
    /// top follows the outer crown (wall exact), while the inner smooth
    /// bottom, paired with the outer flat base, stays anchored.
    #[test]
    fn nested_mismatched_ends_resolve_per_border() {
        let outer_src = arch(23.2, 21.2, 10.0, 0.0);
        let outer_up = arch(22.5, 20.5, 10.0, 0.0);
        let inner_src = capped_arch(20.2, 3.2, 1.2, 7.0);
        let inner_up = capped_arch(19.5, 2.5, 0.5, 7.0);
        let mut src = outer_src.clone();
        src.extend(inner_src);
        let mut up = outer_up.clone();
        up.extend(inner_up);
        let first = fit(&src, &up, [false, false]).unwrap();
        assert!(first.applied);
        let before = loop_tops(&up, 1, true);
        let after = loop_tops(&first.commands, 1, true);
        assert!((before[0] - before[1] - (after[0] - after[1])).abs() < 1e-9);
        // The paired bottom does not move: inner minimum is unchanged.
        let mins_before = loop_tops(&up, 1, false);
        let mins_after = loop_tops(&first.commands, 1, false);
        assert!((mins_before[1] - mins_after[1]).abs() < 1e-9);
        let refit = fit(&src, &first.commands, [false, false]).unwrap();
        assert!(!refit.applied);
    }

    /// Side-by-side loops sharing an edge and overlapping loops both abstain:
    /// relative motion has no safe direction without a thick nested wall.
    #[test]
    fn touching_and_overlapping_loops_abstain() {
        for shift in [20.0f32, 5.0f32] {
            let base = arch(22.5, 20.5, 10.0, 0.0);
            let moved: Vec<FittedCommand> = base
                .iter()
                .map(|c| match *c {
                    FittedCommand::MoveTo(x, y) => FittedCommand::MoveTo(x + shift, y),
                    FittedCommand::LineTo(x, y) => FittedCommand::LineTo(x + shift, y),
                    FittedCommand::QuadTo(x1, y1, x, y) => {
                        FittedCommand::QuadTo(x1 + shift, y1, x + shift, y)
                    }
                    FittedCommand::Close => FittedCommand::Close,
                    FittedCommand::CurveTo(..) => panic!("suite uses quads/lines"),
                })
                .collect();
            let mut cmds = base.clone();
            cmds.extend(moved);
            let fit = fit(&cmds, &cmds.clone(), [false, false]).unwrap();
            assert!(!fit.applied, "shift={shift}");
        }
    }

    /// A joint at the extremum with a tangent reversal (cusp) is not a
    /// smooth pass-through and anchors the end.
    #[test]
    fn cusp_at_extremum_abstains() {
        let roof = vec![
            FittedCommand::MoveTo(-10.0, 0.0),
            FittedCommand::LineTo(-10.0, 20.5),
            FittedCommand::QuadTo(2.0, 22.5, 0.0, 22.5),
            FittedCommand::QuadTo(2.0, 22.5, 10.0, 20.5),
            FittedCommand::LineTo(10.0, 0.0),
            FittedCommand::Close,
        ];
        assert_eq!(classify_end(&segs_of(&roof), 1, true), EndKind::Other);
        let fit = fit(&roof.clone(), &roof, [false, false]).unwrap();
        assert!(!fit.applied);
    }

    /// An off-curve control touching the extremum level while its curve stays
    /// strictly below is a plateau-adjacent contact and anchors the end.
    #[test]
    fn plateau_touch_at_extremum_abstains() {
        let cmds = vec![
            FittedCommand::MoveTo(-10.0, 0.0),
            FittedCommand::LineTo(-10.0, 20.0),
            FittedCommand::QuadTo(-10.0, 22.5, -8.0, 20.5),
            FittedCommand::QuadTo(-3.0, 22.5, 0.0, 22.5),
            FittedCommand::QuadTo(3.0, 22.5, 8.0, 20.5),
            FittedCommand::LineTo(8.0, 0.0),
            FittedCommand::Close,
        ];
        assert_eq!(classify_end(&segs_of(&cmds), 1, true), EndKind::Other);
        let fit = fit(&cmds.clone(), &cmds, [false, false]).unwrap();
        assert!(!fit.applied);
    }

    fn join(src: Vec<FittedCommand>, inner_src: Vec<FittedCommand>) -> Vec<FittedCommand> {
        src.into_iter().chain(inner_src).collect()
    }

    fn loop_tops(commands: &[FittedCommand], axis: usize, is_max: bool) -> Vec<f64> {
        contour_ranges(commands)
            .unwrap()
            .iter()
            .map(|range| {
                parse_contour(&commands[range.0..range.1])
                    .unwrap()
                    .iter()
                    .flat_map(|s| segment_values(s, axis).unwrap().into_iter().map(|(v, _)| v))
                    .fold(
                        if is_max {
                            f64::NEG_INFINITY
                        } else {
                            f64::INFINITY
                        },
                        if is_max { f64::max } else { f64::min },
                    )
            })
            .collect()
    }

    /// An already-clear smooth inner top follows a certified outer deficit by
    /// the same amount, so the crown wall is preserved exactly and the
    /// second pass abstains.
    #[test]
    fn clear_smooth_inner_top_follows_outer_deficit() {
        let outer_src = arch(23.2, 21.2, 10.0, 0.0);
        let outer_up = arch(22.5, 20.5, 10.0, 0.0);
        // Smooth counter top resting clear with a flat base anchoring the
        // minimum slot on both loops.
        let inner_src = arch(11.7, 9.7, 7.0, 2.0);
        let inner_up = arch(11.0, 9.0, 7.0, 2.0);
        let src = join(outer_src, inner_src);
        let up = join(outer_up, inner_up);
        let first = fit(&src, &up, [false, false]).unwrap();
        assert!(first.applied);
        assert_eq!(first.loops.len(), 2);
        let before = loop_tops(&up, 1, true);
        let after = loop_tops(&first.commands, 1, true);
        assert!((before[0] - before[1] - (after[0] - after[1])).abs() < 1e-9);
        assert!((after[1] - (11.0 - 1.0 / 16.0)).abs() < 1e-9);
        let refit = fit(&src, &first.commands, [false, false]).unwrap();
        assert!(!refit.applied);
    }

    /// A flat counter ceiling drawn in both outlines follows a certified
    /// outer deficit rigidly: the flat stays flat, the wall is exact, and
    /// the second pass abstains. Outer flats only ever anchor (next test).
    #[test]
    fn flat_counter_ceiling_follows_outer_deficit() {
        let outer_src = arch(23.2, 21.2, 10.0, 0.0);
        let outer_up = arch(22.5, 20.5, 10.0, 0.0);
        let flat_top = |top: f32, bottom: f32, ctl: f32| {
            vec![
                FittedCommand::MoveTo(-7.0, bottom),
                FittedCommand::LineTo(-7.0, top),
                FittedCommand::LineTo(7.0, top),
                FittedCommand::LineTo(7.0, bottom),
                FittedCommand::QuadTo(0.0, ctl, -7.0, bottom),
                FittedCommand::Close,
            ]
        };
        // Fitted ceiling flat at clear 11.0 with a smooth clear undershoot;
        // source ceiling flat at 11.7 with the same pattern.
        let inner_src = flat_top(11.7, 2.7, 2.2);
        let inner_up = flat_top(11.0, 2.0, 1.5);
        assert_eq!(classify_end(&segs_of(&inner_up), 1, true), EndKind::Flat);
        assert_eq!(classify_end(&segs_of(&inner_src), 1, true), EndKind::Flat);
        let src = join(outer_src, inner_src);
        let up = join(outer_up.clone(), inner_up);
        let first = fit(&src, &up, [false, false]).unwrap();
        assert!(first.applied);
        assert_eq!(first.loops.len(), 2);
        let before = loop_tops(&up, 1, true);
        let after = loop_tops(&first.commands, 1, true);
        assert!((before[0] - before[1] - (after[0] - after[1])).abs() < 1e-9);
        // The ceiling translates rigidly: both top joints share the level.
        let ranges = contour_ranges(&first.commands).unwrap();
        let mut ceiling = Vec::new();
        for command in &first.commands[ranges[1].0..ranges[1].1] {
            if let FittedCommand::LineTo(x, y) = *command {
                if (f64::from(y) - (11.0 - 1.0 / 16.0)).abs() < 1e-6 {
                    ceiling.push(x);
                }
            }
        }
        assert_eq!(ceiling.len(), 2);
        let refit = fit(&src, &first.commands, [false, false]).unwrap();
        assert!(!refit.applied);
    }

    /// An outer flat top paired with a moving smooth inner crown freezes the
    /// slot instead of shifting the stem: stem-owned flats only anchor.
    #[test]
    fn outer_flat_top_freezes_smooth_inner_crown() {
        let outer_src = capped_arch(35.2, 5.7, 5.2, 10.0);
        let outer_up = capped_arch(34.5, 5.0, 4.5, 10.0);
        let inner_src = arch(20.2, 18.2, 7.0, 7.0);
        let inner_up = arch(19.5, 17.5, 7.0, 7.0);
        assert_eq!(classify_end(&segs_of(&outer_up), 1, true), EndKind::Flat);
        let src = join(outer_src, inner_src);
        let up = join(outer_up, inner_up);
        let fit = fit(&src, &up, [false, false]).unwrap();
        assert!(!fit.applied);
        assert_eq!(fit.commands, up);
    }

    /// A fitted nest without the same nest in the source freezes the axis:
    /// pair ownership is source correspondence, never fitted bbox alone.
    #[test]
    fn fitted_only_nest_freezes_axis() {
        let anchor = arch(23.2, 21.2, 10.0, 0.0);
        let anchor_up = arch(22.5, 20.5, 10.0, 0.0);
        // Source loop stands separate; the fitted loop nests inside the
        // anchor with a conflicting (clear) deficit.
        let shift = |cmds: Vec<FittedCommand>, dx: f32, dy: f32| {
            cmds.into_iter()
                .map(|c| match c {
                    FittedCommand::MoveTo(x, y) => FittedCommand::MoveTo(x + dx, y + dy),
                    FittedCommand::LineTo(x, y) => FittedCommand::LineTo(x + dx, y + dy),
                    FittedCommand::QuadTo(x1, y1, x, y) => {
                        FittedCommand::QuadTo(x1 + dx, y1 + dy, x + dx, y + dy)
                    }
                    FittedCommand::Close => FittedCommand::Close,
                    FittedCommand::CurveTo(..) => panic!("suite uses quads/lines"),
                })
                .collect::<Vec<_>>()
        };
        let src = join(anchor, shift(arch(23.9, 21.9, 5.0, 2.7), 30.0, 0.0));
        let up = join(anchor_up, shift(arch(20.6, 18.6, 5.0, 2.0), 0.0, 0.0));
        let first = fit(&src, &up, [false, false]).unwrap();
        assert!(!first.applied);
        assert_eq!(first.commands, up);
    }

    /// Separated loops with a real gap correct independently on the same
    /// axis: no nest, no pair, no veto.
    #[test]
    fn separated_loops_correct_independently() {
        let shift = |cmds: Vec<FittedCommand>, dx: f32| {
            cmds.into_iter()
                .map(|c| match c {
                    FittedCommand::MoveTo(x, y) => FittedCommand::MoveTo(x + dx, y),
                    FittedCommand::LineTo(x, y) => FittedCommand::LineTo(x + dx, y),
                    FittedCommand::QuadTo(x1, y1, x, y) => {
                        FittedCommand::QuadTo(x1 + dx, y1, x + dx, y)
                    }
                    FittedCommand::Close => FittedCommand::Close,
                    FittedCommand::CurveTo(..) => panic!("suite uses quads/lines"),
                })
                .collect::<Vec<_>>()
        };
        let src = join(
            arch(23.2, 21.2, 10.0, 0.0),
            shift(arch(23.2, 21.2, 10.0, 0.0), 30.0),
        );
        let up = join(
            arch(22.5, 20.5, 10.0, 0.0),
            shift(arch(22.5, 20.5, 10.0, 0.0), 30.0),
        );
        let first = fit(&src, &up, [false, false]).unwrap();
        assert!(first.applied);
        assert_eq!(first.loops.len(), 2);
        let after = loop_tops(&first.commands, 1, true);
        assert!((after[0] - (22.5 - 1.0 / 16.0)).abs() < 1e-9);
        assert!((after[1] - (22.5 - 1.0 / 16.0)).abs() < 1e-9);
        let refit = fit(&src, &first.commands, [false, false]).unwrap();
        assert!(!refit.applied);
    }

    /// The clear-follow coupling holds on all four sides under the same
    /// model: transposed (X maximum/minimum) and mirrored (Y minimum) copies
    /// of the smooth-follow configuration keep the wall exact and stick.
    #[test]
    fn clear_follow_holds_on_all_four_sides() {
        let transpose = |cmds: &Vec<FittedCommand>| {
            cmds.iter()
                .map(|c| match *c {
                    FittedCommand::MoveTo(x, y) => FittedCommand::MoveTo(y, x),
                    FittedCommand::LineTo(x, y) => FittedCommand::LineTo(y, x),
                    FittedCommand::QuadTo(x1, y1, x, y) => FittedCommand::QuadTo(y1, x1, y, x),
                    FittedCommand::CurveTo(..) => panic!("suite uses quads/lines"),
                    FittedCommand::Close => FittedCommand::Close,
                })
                .collect::<Vec<_>>()
        };
        let base_src = join(arch(23.2, 21.2, 10.0, 0.0), arch(11.7, 9.7, 7.0, 2.0));
        let base_up = join(arch(22.5, 20.5, 10.0, 0.0), arch(11.0, 9.0, 7.0, 2.0));
        // (outline transform, axis, wall end): maximum wall for maxima,
        // minimum wall for minima.
        let cases: Vec<(
            Box<dyn Fn(Vec<FittedCommand>) -> Vec<FittedCommand>>,
            usize,
            bool,
        )> = vec![
            (Box::new(|v| v), 1, true),
            (Box::new(|v| flip_y(&v, 44.0)), 1, false),
            (Box::new(|v| transpose(&v)), 0, true),
            (Box::new(|v| reflect_x(&transpose(&v))), 0, false),
        ];
        for (transform, axis, is_max) in cases {
            let src = transform(base_src.clone());
            let up = transform(base_up.clone());
            let first = fit(&src, &up, [false, false]).unwrap();
            assert!(first.applied, "axis={axis} is_max={is_max}");
            assert_eq!(first.loops.len(), 2);
            let before = loop_tops(&up, axis, is_max);
            let after = loop_tops(&first.commands, axis, is_max);
            let wall = |pair: &[f64]| {
                if is_max {
                    pair[0] - pair[1]
                } else {
                    pair[1] - pair[0]
                }
            };
            assert!(
                (wall(&before) - wall(&after)).abs() < 1e-9,
                "axis={axis} is_max={is_max}"
            );
            let refit = fit(&src, &first.commands, [false, false]).unwrap();
            assert!(!refit.applied, "axis={axis} is_max={is_max}");
        }
    }

    fn stem_arch(apex: f64, shoulder: f64, stem_top: f64) -> Vec<FittedCommand> {
        vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(0.0, stem_top as f32),
            FittedCommand::LineTo(3.0, stem_top as f32),
            FittedCommand::LineTo(3.0, shoulder as f32),
            FittedCommand::QuadTo(6.0, apex as f32, 9.0, apex as f32),
            FittedCommand::QuadTo(12.0, apex as f32, 15.0, shoulder as f32),
            FittedCommand::LineTo(15.0, 0.0),
            FittedCommand::Close,
        ]
    }

    /// A subordinate arch below a tall flat stem top in one contour moves
    /// locally: the stem top and base keep their coordinates exactly.
    #[test]
    fn subordinate_arch_below_flat_stem_moves_locally() {
        let src = stem_arch(23.2, 19.7, 35.2);
        let up = stem_arch(22.5, 19.0, 34.5);
        let first = fit(&src, &up, [false, false]).unwrap();
        assert!(first.applied);
        let segs = parse_contour(&first.commands).unwrap();
        // Global maximum is the untouched flat stem top.
        assert_eq!(outline_extremum(&segs, 1, true).unwrap(), 34.5);
        assert!(first
            .commands
            .iter()
            .any(|c| matches!(c, FittedCommand::LineTo(_, y) if *y == 34.5)));
        // Every non-arch point is bit-identical; only the arch apex joint
        // and its incident controls moved down by the deficit.
        for (a, b) in up.iter().zip(&first.commands) {
            match (a, b) {
                (FittedCommand::QuadTo(x1, y1, x, y), FittedCommand::QuadTo(x1b, y1b, xb, yb)) => {
                    assert_eq!((x1, x), (x1b, xb));
                    for (v, w) in [(y1, y1b), (y, yb)] {
                        if *v == 22.5 {
                            assert_eq!(*w, 22.5 - 1.0 / 16.0);
                        } else {
                            assert_eq!(v, w);
                        }
                    }
                }
                _ => assert_eq!(a, b),
            }
        }
        let refit = fit(&src, &first.commands, [false, false]).unwrap();
        assert!(!refit.applied);
        assert_eq!(replay(&up, &first.loops).unwrap(), first.commands);
    }

    /// A flat follower also moves an adjacent segment. Its unselected,
    /// initially phase-valid apex must not enter Hersch's excluded band.
    #[test]
    fn flat_follow_cannot_drag_an_unselected_apex_into_excluded_phase() {
        fn rotate(commands: &[FittedCommand]) -> Vec<FittedCommand> {
            commands
                .iter()
                .map(|command| match *command {
                    FittedCommand::MoveTo(x, y) => FittedCommand::MoveTo(-y, x),
                    FittedCommand::LineTo(x, y) => FittedCommand::LineTo(-y, x),
                    FittedCommand::QuadTo(x1, y1, x, y) => FittedCommand::QuadTo(-y1, x1, -y, x),
                    FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                        FittedCommand::CurveTo(-y1, x1, -y2, x2, -y, x)
                    }
                    FittedCommand::Close => FittedCommand::Close,
                })
                .collect()
        }

        for control in [21.5, 21.53, 21.56] {
            let mut upstream = vec![
                FittedCommand::MoveTo(-2.0, 0.0),
                FittedCommand::LineTo(4.0, 20.5),
                FittedCommand::QuadTo(4.0, 22.5, 5.0, 22.5),
                FittedCommand::QuadTo(6.0, 22.5, 6.0, 20.5),
                FittedCommand::LineTo(16.0, 20.5),
                FittedCommand::LineTo(16.0, 0.0),
                FittedCommand::LineTo(-2.0, 0.0),
                FittedCommand::Close,
                FittedCommand::MoveTo(0.0, 2.0),
                FittedCommand::LineTo(0.0, 19.0),
                FittedCommand::LineTo(3.0, 20.0),
                FittedCommand::LineTo(7.0, 20.0),
                FittedCommand::QuadTo(9.5, control, 12.0, 19.0),
                FittedCommand::LineTo(12.0, 2.0),
                FittedCommand::LineTo(0.0, 2.0),
                FittedCommand::Close,
            ];
            let mut source: Vec<_> = upstream
                .iter()
                .cloned()
                .map(|mut command| {
                    match command {
                        FittedCommand::Close => {}
                        _ => add_axis(&mut command, 1, 0.7, 0),
                    }
                    if matches!(command, FittedCommand::QuadTo(..)) {
                        add_axis(&mut command, 1, 0.7, 1);
                    }
                    command
                })
                .collect();
            for turn in 0..4 {
                let fitted = fit(&source, &upstream, [false, false]).unwrap();
                assert!(
                    !fitted.applied,
                    "control {control}, quarter-turn {turn}: unsafe neighboring apex moved"
                );
                assert_eq!(fitted.commands, upstream);
                assert!(fitted.loops.is_empty());
                source = rotate(&source);
                upstream = rotate(&upstream);
            }
        }
    }

    /// Paired borders within one contour (outer crown and counter ceiling
    /// of a thick arch) share the deficit: apex wall exact, feet anchored.
    #[test]
    fn same_contour_paired_borders_share_deficit() {
        let shape = |outer: f32, inner: f32| {
            vec![
                FittedCommand::MoveTo(0.0, 0.0),
                FittedCommand::LineTo(0.0, 20.0),
                FittedCommand::QuadTo(10.0, 2.0 * outer - 20.0, 20.0, 20.0),
                FittedCommand::LineTo(20.0, 0.0),
                FittedCommand::LineTo(16.0, 0.0),
                FittedCommand::LineTo(16.0, 17.0),
                FittedCommand::QuadTo(10.0, 2.0 * inner - 17.0, 4.0, 17.0),
                FittedCommand::LineTo(4.0, 0.0),
                FittedCommand::Close,
            ]
        };
        let src = shape(23.3, 20.3);
        let up = shape(22.5, 19.5);
        let first = fit(&src, &up, [false, false]).unwrap();
        assert!(first.applied);
        let tops = |cmds: &[FittedCommand]| {
            let s = parse_contour(cmds).unwrap();
            (
                outline_extremum(&s, 1, true).unwrap(),
                s.iter()
                    .flat_map(|g| segment_values(g, 1).unwrap().into_iter().map(|(v, _)| v))
                    .fold(f64::NEG_INFINITY, f64::max),
            )
        };
        let _ = tops;
        // Apex wall: outer true max minus the inner quad apex (19.5 -> moved).
        let apex_of = |cmds: &[FittedCommand], want: f64| {
            let s = parse_contour(cmds).unwrap();
            s.iter()
                .filter_map(|g| {
                    let vs: Vec<f64> = segment_values(g, 1)
                        .unwrap()
                        .into_iter()
                        .map(|(v, _)| v)
                        .collect();
                    vs.into_iter().find(|v| (*v - want).abs() < 0.6)
                })
                .next()
                .unwrap_or(f64::NAN)
        };
        let _ = apex_of;
        let before_outer = 22.5f64;
        let before_inner = 19.5f64;
        let segs = parse_contour(&first.commands).unwrap();
        let after_outer = outline_extremum(&segs, 1, true).unwrap();
        assert!((after_outer - (before_outer - 1.0 / 16.0)).abs() < 1e-9);
        // Inner apex is the stationary point of the reversed quad segment.
        let inner_vals: Vec<f64> = segs
            .iter()
            .flat_map(|g| segment_values(g, 1).unwrap().into_iter().map(|(v, _)| v))
            .filter(|v| *v > 18.0 && *v < 20.0)
            .collect();
        let after_inner = inner_vals.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        assert!(
            ((before_outer - before_inner) - (after_outer - after_inner)).abs() < 1e-6,
            "wall {after_outer} {after_inner}"
        );
        // Feet at y=0 unchanged.
        assert!(first.commands.iter().filter(|c| matches!(c, FittedCommand::LineTo(_, y) | FittedCommand::MoveTo(_, y) if *y == 0.0)).count() >= 3);
        let refit = fit(&src, &first.commands, [false, false]).unwrap();
        assert!(!refit.applied);
    }

    /// Symmetric two-cubic lens: the top joint (end of the second cubic)
    /// and the bottom joint (end of the first cubic) are both smooth
    /// axis-aligned apexes. Each wall leaves its apex horizontally, so the
    /// shared wall cubic carries one control at the top level and the other
    /// at the bottom level. The walls sit 0.2 off the center column so the
    /// transverse wall-bulge extrema rest clear of pixel centers: only the
    /// pinned axis carries active features.
    fn neighbor_lens(top: f64, bottom: f64) -> Vec<FittedCommand> {
        vec![
            FittedCommand::MoveTo(0.2, top as f32),
            FittedCommand::CurveTo(6.2, top as f32, 6.2, bottom as f32, 0.2, bottom as f32),
            FittedCommand::CurveTo(-5.8, bottom as f32, -5.8, top as f32, 0.2, top as f32),
            FittedCommand::Close,
        ]
    }

    fn transpose_lens(commands: &[FittedCommand]) -> Vec<FittedCommand> {
        commands
            .iter()
            .map(|c| match *c {
                FittedCommand::MoveTo(x, y) => FittedCommand::MoveTo(y, x),
                FittedCommand::LineTo(x, y) => FittedCommand::LineTo(y, x),
                FittedCommand::QuadTo(x1, y1, x, y) => FittedCommand::QuadTo(y1, x1, y, x),
                FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                    FittedCommand::CurveTo(y1, x1, y2, x2, y, x)
                }
                FittedCommand::Close => FittedCommand::Close,
            })
            .collect()
    }

    /// Joint apexes sharing only the outgoing neighbor freeze each other.
    ///
    /// [Model and assessment](../../../docs/revisions/001/03-spacing-kerning.md#curve-extremity-phase):
    /// a joint apex owns its holding segment plus its outgoing neighbor, so
    /// two active same-contour, same-axis features on adjacent segments
    /// share an incident segment and both anchor (`freeze_shared_incidents`
    /// via `incident_segments`). The holding segments differ, so the
    /// same-segment guard cannot mask this rule: without the neighbor arm
    /// both features would apply. A second lens with a clear far end is the
    /// control: one active apex with no sharing partner still corrects.
    /// Both orientations pin the axis-symmetric rule; mirroring the
    /// symmetric lens would be vacuous and is not repeated.
    #[test]
    fn adjacent_joint_apexes_sharing_only_the_neighbor_freeze() {
        let cases: Vec<(Box<dyn Fn(Vec<FittedCommand>) -> Vec<FittedCommand>>, usize)> =
            vec![(Box::new(|v| v), 1), (Box::new(|v| transpose_lens(&v)), 0)];
        for (transform, axis) in cases {
            // Both ends on pixel centers: two active joint features on
            // adjacent holding segments (maximum on segment 1, minimum on
            // segment 0 of the two-segment loop).
            let up = transform(neighbor_lens(22.5, 0.5));
            // Detection premises on real geometry: exactly one smooth
            // movable joint apex per end, on the expected segments.
            let segs = segs_of(&up);
            for (is_max, segment) in [(true, 1), (false, 0)] {
                let feats: Vec<_> = detect_features(&segs, 0, axis)
                    .into_iter()
                    .filter(|f| f.movable && !f.interior && f.is_max == is_max)
                    .collect();
                assert_eq!(feats.len(), 1, "axis={axis} is_max={is_max}");
                assert_eq!(feats[0].segment, segment, "axis={axis} is_max={is_max}");
            }
            let frozen = fit(&up.clone(), &up, [false, false]).unwrap();
            assert!(
                !frozen.applied,
                "axis={axis}: neighbor-sharing pair must freeze"
            );
            assert_eq!(frozen.commands, up);
            assert!(frozen.loops.is_empty());
            // Control: the far end rests clear of the excluded band, so the
            // lone active apex with no sharing partner still corrects.
            let control_up = transform(neighbor_lens(22.5, 0.4));
            let first = fit(&control_up.clone(), &control_up, [false, false]).unwrap();
            assert!(first.applied, "axis={axis}: lone apex must correct");
            assert_eq!(first.loops.len(), 1);
            let csegs = parse_contour(&first.commands).unwrap();
            let edge = outline_extremum(&csegs, axis, true).unwrap();
            assert!((edge - (22.5 - 1.0 / 16.0)).abs() < 1e-9, "axis={axis}");
            let refit = fit(&control_up.clone(), &first.commands, [false, false]).unwrap();
            assert!(!refit.applied, "axis={axis}: correction must stick");
        }
    }
}
