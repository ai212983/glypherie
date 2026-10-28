//! Recognizer geometry for width-only direct-diagonal fitting.
//!
//! Source: Hobby sections 3.2-3.4 (medial intervals, competing-boundary
//! clearance, width as twice the medial radius) and Hersch sections 5-6.
//! Project adaptations: canonical exact crossings with one transported common
//! point, certified two-sided winding, interval ownership with eroded cores.
//! Captured coordinates are exact `f32`-bit lifts in `f64`; raw feature
//! outlines can independently retain f64 coordinates. Only open
//! interval interiors are sampled and every sampled disk is rechecked.

use super::{exact::Exact as BigRational, intervals};
use crate::probe::FittedCommand;
use std::collections::{BTreeMap, HashMap, HashSet};

/// Exact `f32`-bit lift, never resnapped.
pub type Pt = [f64; 2];
/// Bounding box as `(lo_x, lo_y, hi_x, hi_y)`.
pub type BBox = (f64, f64, f64, f64);

/// Outline segment with parsed point indices, mirroring `parse_commands`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum Segment {
    Line {
        a: usize,
        b: usize,
    },
    Quad {
        c: usize,
        a: usize,
        b: usize,
    },
    Cubic {
        c1: usize,
        c2: usize,
        a: usize,
        b: usize,
    },
}

impl Segment {
    pub fn endpoints(self) -> (usize, usize) {
        match self {
            Segment::Line { a, b } => (a, b),
            Segment::Quad { a, b, .. } => (a, b),
            Segment::Cubic { a, b, .. } => (a, b),
        }
    }

    pub fn is_line(self) -> bool {
        matches!(self, Segment::Line { .. })
    }
}

/// Parsed outline: on-curve vertices, off-curve controls, contour segments.
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct Parsed {
    pub oncurve: Vec<Pt>,
    pub offcurve: Vec<Pt>,
    pub contours: Vec<Vec<Segment>>,
}

/// Split straight border portion with affine correspondence to its edge.
#[derive(Clone, Debug)]
pub struct Portion {
    pub contour: usize,
    pub seg: usize,
    pub t0: f64,
    pub t1: f64,
    pub p0: Pt,
    pub p1: Pt,
    pub i0: usize,
    pub i1: usize,
    pub hidden: bool,
    pub unknown: bool,
}

/// Competitor border for clearance; `key` drives exclusion, `tag` is evidence.
#[derive(Clone, Debug)]
pub struct Border {
    pub seg: (Pt, Pt),
    pub tag: String,
    pub key: (usize, usize, f64, f64),
}

/// Recognized opposing pair; `feet` is present only for interval ownership.
#[derive(Debug)]
pub struct Pair {
    pub a: Portion,
    pub b: Portion,
    pub dom: intervals::Dominance,
    pub feet: Option<Vec<intervals::FootRange>>,
}

/// Certified width station over one dominance interval.
#[derive(Debug)]
pub struct Station {
    pub s: f64,
    pub hit: intervals::Contact,
}

/// Prepared diagonal pair with its source frame.
#[derive(Debug)]
pub struct PreppedPair {
    pub id: String,
    pub a: Portion,
    pub b: Portion,
    pub normal: Pt,
    pub stations: Vec<Station>,
    pub src_widths: Vec<f64>,
    pub fit_widths: Vec<f64>,
    pub arc: f64,
    pub span_lo: f64,
    pub span_hi: f64,
}

/// Nearest 1/64 unit, ties toward positive infinity (scanner convention).
pub fn round_26_6(x: f64) -> f64 {
    (x * 64.0 + 0.5).floor() / 64.0
}

/// Split commands into contours of indexed segments, mirroring `parse_commands`.
pub fn parse_commands(commands: &[FittedCommand]) -> Result<Parsed, ()> {
    let mut oncurve: Vec<Pt> = Vec::new();
    let mut offcurve: Vec<Pt> = Vec::new();
    let mut contours: Vec<Vec<Segment>> = Vec::new();
    let mut current: Vec<Segment> = Vec::new();
    let mut pen: Option<usize> = None;
    let mut start: Option<usize> = None;
    let finite = |x: f32, y: f32| {
        if x.is_finite() && y.is_finite() {
            Some([x as f64, y as f64])
        } else {
            None
        }
    };
    for cmd in commands {
        match *cmd {
            FittedCommand::MoveTo(x, y) => {
                if !current.is_empty() {
                    contours.push(std::mem::take(&mut current));
                }
                let Some(pt) = finite(x, y) else {
                    return Err(());
                };
                oncurve.push(pt);
                pen = Some(oncurve.len() - 1);
                start = pen;
            }
            FittedCommand::LineTo(x, y) => {
                let Some(pt) = finite(x, y) else {
                    return Err(());
                };
                let Some(p) = pen else {
                    return Err(());
                };
                oncurve.push(pt);
                let nxt = oncurve.len() - 1;
                current.push(Segment::Line { a: p, b: nxt });
                pen = Some(nxt);
            }
            FittedCommand::QuadTo(x1, y1, x, y) => {
                let (Some(c), Some(pt)) = (finite(x1, y1), finite(x, y)) else {
                    return Err(());
                };
                let Some(p) = pen else {
                    return Err(());
                };
                offcurve.push(c);
                let ci = offcurve.len() - 1;
                oncurve.push(pt);
                let nxt = oncurve.len() - 1;
                current.push(Segment::Quad {
                    c: ci,
                    a: p,
                    b: nxt,
                });
                pen = Some(nxt);
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                let (Some(c1), Some(c2), Some(pt)) = (finite(x1, y1), finite(x2, y2), finite(x, y))
                else {
                    return Err(());
                };
                let Some(p) = pen else {
                    return Err(());
                };
                offcurve.push(c1);
                let i1 = offcurve.len() - 1;
                offcurve.push(c2);
                let i2 = offcurve.len() - 1;
                oncurve.push(pt);
                let nxt = oncurve.len() - 1;
                current.push(Segment::Cubic {
                    c1: i1,
                    c2: i2,
                    a: p,
                    b: nxt,
                });
                pen = Some(nxt);
            }
            FittedCommand::Close => {
                if let (Some(p), Some(s)) = (pen, start) {
                    if p != s {
                        current.push(Segment::Line { a: p, b: s });
                    }
                }
                if !current.is_empty() {
                    contours.push(std::mem::take(&mut current));
                }
                pen = None;
                start = None;
            }
        }
    }
    if !current.is_empty() {
        contours.push(current);
    }
    Ok(Parsed {
        oncurve,
        offcurve,
        contours,
    })
}

/// Identical op sequences contour by contour; identity is the contract.
pub fn check_correspondence(a: &[FittedCommand], b: &[FittedCommand]) -> bool {
    fn ops(cmds: &[FittedCommand]) -> Vec<Vec<&'static str>> {
        let mut seq: Vec<Vec<&'static str>> = Vec::new();
        let mut cur: Vec<&'static str> = Vec::new();
        for cmd in cmds {
            let op = match cmd {
                FittedCommand::MoveTo(..) => "move_to",
                FittedCommand::LineTo(..) => "line_to",
                FittedCommand::QuadTo(..) => "quad_to",
                FittedCommand::CurveTo(..) => "curve_to",
                FittedCommand::Close => "close",
            };
            if op == "move_to" && !cur.is_empty() {
                seq.push(std::mem::take(&mut cur));
            }
            cur.push(op);
            if op == "close" {
                seq.push(std::mem::take(&mut cur));
            }
        }
        if !cur.is_empty() {
            seq.push(cur);
        }
        seq
    }
    ops(a) == ops(b)
}

/// On-curve index to owning command position, mirroring `parse_commands`.
pub fn index_map(commands: &[FittedCommand]) -> Vec<Option<usize>> {
    let mut table: Vec<Option<usize>> = Vec::new();
    for (pos, cmd) in commands.iter().enumerate() {
        match cmd {
            FittedCommand::MoveTo(..)
            | FittedCommand::LineTo(..)
            | FittedCommand::QuadTo(..)
            | FittedCommand::CurveTo(..) => {
                table.push(Some(pos));
            }
            FittedCommand::Close => {}
        }
    }
    table
}

/// Constant axis of a straight side; `None` when not axis-aligned.
pub fn axis_of(p0: Pt, p1: Pt) -> Option<char> {
    if p0[0] == p1[0] {
        Some('x')
    } else if p0[1] == p1[1] {
        Some('y')
    } else {
        None
    }
}

fn winding_dir(pt: Pt, loops: &[Vec<Pt>], axis: usize, positive: bool) -> i32 {
    let mv = |p: Pt| -> Pt {
        let (mut x, mut y) = (p[0], p[1]);
        if axis == 1 {
            std::mem::swap(&mut x, &mut y);
        }
        if !positive {
            x = -x;
        }
        [x, y]
    };
    let [x, y] = mv(pt);
    let mut total = 0;
    // Exact Python iteration: start from the last stored vertex and visit
    // every stored vertex, including an explicit closing duplicate (its
    // degenerate edge never crosses). Never pop: loops_points stores
    // implicitly closed loops, so popping would drop a real vertex.
    for lp in loops {
        if lp.is_empty() {
            continue;
        }
        let moved: Vec<Pt> = lp.iter().map(|&p| mv(p)).collect();
        let mut a = moved[moved.len() - 1];
        for &b in &moved {
            if (a[1] <= y) != (b[1] <= y) {
                let xi = a[0] + (y - a[1]) / (b[1] - a[1]) * (b[0] - a[0]);
                if xi > x {
                    total += if b[1] > a[1] { 1 } else { -1 };
                }
            }
            a = b;
        }
    }
    total
}

fn ray_hits_box(pt: Pt, bbox: &BBox, axis: usize, positive: bool) -> bool {
    let (lo_x, lo_y, hi_x, hi_y) = *bbox;
    let (x, y) = (pt[0], pt[1]);
    if axis == 0 {
        if y < lo_y || y > hi_y {
            return false;
        }
        return if positive { hi_x >= x } else { lo_x <= x };
    }
    if x < lo_x || x > hi_x {
        return false;
    }
    if positive {
        hi_y >= y
    } else {
        lo_y <= y
    }
}

/// Certified winding: valid only along a ray avoiding every curve box.
pub fn certified_winding(
    pt: Pt,
    straight_loops: &[Vec<Pt>],
    curve_flats: &[(Vec<Pt>, BBox)],
) -> Option<i32> {
    for axis in [0, 1] {
        for positive in [true, false] {
            if curve_flats
                .iter()
                .any(|(_, b)| ray_hits_box(pt, b, axis, positive))
            {
                continue;
            }
            let mut loops: Vec<Vec<Pt>> = straight_loops.to_vec();
            for (flat, _) in curve_flats {
                loops.push(flat.clone());
            }
            return Some(winding_dir(pt, &loops, axis, positive));
        }
    }
    None
}

fn seg_point_dist(p: Pt, a: Pt, b: Pt) -> f64 {
    let (dx, dy) = (b[0] - a[0], b[1] - a[1]);
    let den = dx * dx + dy * dy;
    if den == 0.0 {
        return (p[0] - a[0]).hypot(p[1] - a[1]);
    }
    let mut t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / den;
    t = t.clamp(0.0, 1.0);
    (p[0] - (a[0] + t * dx)).hypot(p[1] - (a[1] + t * dy))
}

fn bbox_point_dist(p: Pt, bbox: &BBox) -> f64 {
    let (lo_x, lo_y, hi_x, hi_y) = *bbox;
    let dx = if p[0] < lo_x {
        lo_x - p[0]
    } else if p[0] > hi_x {
        p[0] - hi_x
    } else {
        0.0
    };
    let dy = if p[1] < lo_y {
        lo_y - p[1]
    } else if p[1] > hi_y {
        p[1] - hi_y
    } else {
        0.0
    };
    dx.hypot(dy)
}

fn bbox_overlap(a: &BBox, b: &BBox) -> bool {
    a.0 <= b.2 && b.0 <= a.2 && a.1 <= b.3 && b.1 <= a.3
}

pub fn signed_areas(loops: &[Vec<Pt>]) -> Vec<f64> {
    loops
        .iter()
        .map(|lp| {
            let n = lp.len();
            lp.iter()
                .enumerate()
                .map(|(i, p)| p[0] * lp[(i + 1) % n][1] - lp[(i + 1) % n][0] * p[1])
                .sum::<f64>()
                / 2.0
        })
        .collect()
}

/// Split parameters for a proper crossing or endpoint touch (float legacy).
fn seg_intersection(p1: Pt, p2: Pt, p3: Pt, p4: Pt) -> Option<(f64, f64)> {
    let d = (p2[0] - p1[0]) * (p4[1] - p3[1]) - (p2[1] - p1[1]) * (p4[0] - p3[0]);
    if d == 0.0 {
        return None;
    }
    let t = ((p3[0] - p1[0]) * (p4[1] - p3[1]) - (p3[1] - p1[1]) * (p4[0] - p3[0])) / d;
    let u = ((p3[0] - p1[0]) * (p2[1] - p1[1]) - (p3[1] - p1[1]) * (p2[0] - p1[0])) / d;
    if 0.0 < t && t < 1.0 && 0.0 < u && u < 1.0 {
        return Some((t, u));
    }
    if 0.0 < t && t < 1.0 && (u == 0.0 || u == 1.0) {
        return Some((t, u));
    }
    if 0.0 < u && u < 1.0 && (t == 0.0 || t == 1.0) {
        return Some((t, u));
    }
    None
}

fn rat(x: f64) -> Option<BigRational> {
    BigRational::from_f64(x)
}

/// Exact crossing parameters with one transported common point.
fn exact_intersection(p1: Pt, p2: Pt, p3: Pt, p4: Pt) -> Option<(BigRational, BigRational, Pt)> {
    let (a1x, a1y) = (rat(p1[0])?, rat(p1[1])?);
    let (a2x, a2y) = (rat(p2[0])?, rat(p2[1])?);
    let (b1x, b1y) = (rat(p3[0])?, rat(p3[1])?);
    let (b2x, b2y) = (rat(p4[0])?, rat(p4[1])?);
    let den = (&a2x - &a1x) * (&b2y - &b1y) - (&a2y - &a1y) * (&b2x - &b1x);
    if den.is_zero() {
        return None;
    }
    // True divisions promote to rationals: the parameters are the exact
    // rational quotients, never rounded floats. Map keys keep exact order.
    let den_q = den.to_rational();
    let num_t = (&b1x - &a1x) * (&b2y - &b1y) - (&b1y - &a1y) * (&b2x - &b1x);
    let num_u = (&b1x - &a1x) * (&a2y - &a1y) - (&b1y - &a1y) * (&a2x - &a1x);
    let t = BigRational::from_rational(num_t.to_rational() / den_q.clone());
    let u = BigRational::from_rational(num_u.to_rational() / den_q);
    let zero = BigRational::zero();
    let one = BigRational::integer(1);
    if zero < t && t < one && zero < u && u < one {
        let px = (&a1x + &t * (&a2x - &a1x)).to_f64()?;
        let py = (&a1y + &t * (&a2y - &a1y)).to_f64()?;
        Some((t, u, [px, py]))
    } else if zero < t && t < one && (u == zero || u == one) {
        let point = if u == zero { p3 } else { p4 };
        Some((t, u, point))
    } else if zero < u && u < one && (t == zero || t == one) {
        let point = if t == zero { p1 } else { p2 };
        Some((t, u, point))
    } else {
        None
    }
}

struct Edge {
    contour: usize,
    seg: usize,
    i0: usize,
    i1: usize,
    p0: Pt,
    p1: Pt,
}

/// Closed segment bounds, selecting only original finite endpoints.
/// CGAL CLOSED boxes retain boundary and zero-width contacts:
/// https://doc.cgal.org/latest/Box_intersection_d/index.html
/// Invalid endpoints bypass this optimization and retain the old exact path.
fn segment_bounds(p0: Pt, p1: Pt) -> Option<BBox> {
    if !p0.iter().chain(&p1).all(|x| x.is_finite()) {
        return None;
    }
    Some((
        p0[0].min(p1[0]),
        p0[1].min(p1[1]),
        p0[0].max(p1[0]),
        p0[1].max(p1[1]),
    ))
}

/// Canonical split sites keyed by exact parameter, mirroring the legacy rule.
fn exact_cut_sites(edges: &[Edge]) -> Vec<BTreeMap<BigRational, Pt>> {
    let bounds: Vec<_> = edges.iter().map(|e| segment_bounds(e.p0, e.p1)).collect();
    let mut sites: Vec<BTreeMap<BigRational, Pt>> =
        (0..edges.len()).map(|_| BTreeMap::new()).collect();
    for i in 0..edges.len() {
        for j in (i + 1)..edges.len() {
            let (a, b) = (&edges[i], &edges[j]);
            if a.contour == b.contour && a.seg.abs_diff(b.seg) <= 1 {
                continue;
            }
            if bounds[i]
                .as_ref()
                .zip(bounds[j].as_ref())
                .is_some_and(|(a, b)| !bbox_overlap(a, b))
            {
                continue;
            }
            let Some((t, u, point)) = exact_intersection(a.p0, a.p1, b.p0, b.p1) else {
                continue;
            };
            let zero = BigRational::zero();
            let one = BigRational::integer(1);
            if zero < t && t < one {
                sites[i].insert(t, point);
            }
            if zero < u && u < one {
                sites[j].insert(u, point);
            }
        }
    }
    sites
}

fn controls(seg: &Segment, oncurve: &[Pt], offcurve: &[Pt]) -> Vec<Pt> {
    match *seg {
        Segment::Line { a, b } => vec![oncurve[a], oncurve[b]],
        Segment::Quad { c, a, b } => vec![oncurve[a], offcurve[c], oncurve[b]],
        Segment::Cubic { c1, c2, a, b } => {
            vec![oncurve[a], offcurve[c1], offcurve[c2], oncurve[b]]
        }
    }
}

fn flatten_seg(seg: &Segment, oncurve: &[Pt], offcurve: &[Pt], parts: usize) -> Vec<Pt> {
    let base = controls(seg, oncurve, offcurve);
    if seg.is_line() {
        return base;
    }
    let mut out = Vec::with_capacity(parts + 1);
    for i in 0..=parts {
        let t = i as f64 / parts as f64;
        let mut pts = base.clone();
        while pts.len() > 1 {
            pts = pts
                .windows(2)
                .map(|w| {
                    [
                        (1.0 - t) * w[0][0] + t * w[1][0],
                        (1.0 - t) * w[0][1] + t * w[1][1],
                    ]
                })
                .collect();
        }
        out.push(pts[0]);
    }
    out
}

fn curve_box(seg: &Segment, oncurve: &[Pt], offcurve: &[Pt]) -> BBox {
    let pts = controls(seg, oncurve, offcurve);
    let (mut lo_x, mut lo_y, mut hi_x, mut hi_y) = (
        f64::INFINITY,
        f64::INFINITY,
        f64::NEG_INFINITY,
        f64::NEG_INFINITY,
    );
    for p in &pts {
        lo_x = lo_x.min(p[0]);
        lo_y = lo_y.min(p[1]);
        hi_x = hi_x.max(p[0]);
        hi_y = hi_y.max(p[1]);
    }
    (lo_x, lo_y, hi_x, hi_y)
}

/// Actual Bezier controls per curved segment, contour order.
pub fn curve_controls(parsed: &Parsed) -> Vec<Vec<Pt>> {
    let mut out = Vec::new();
    for contour in &parsed.contours {
        for seg in contour {
            if seg.is_line() {
                continue;
            }
            out.push(controls(seg, &parsed.oncurve, &parsed.offcurve));
        }
    }
    out
}

/// Vertex loops sharing one flattening, replicating the exact prototype
/// point sequence: the first segment contributes all its points, later
/// segments drop only their last point (shared vertices stay duplicated),
/// and the loop start is appended explicitly. No vertex is removed, so
/// near-center queries decide identically to the prototype.
pub fn loops_points(parsed: &Parsed) -> Vec<Vec<Pt>> {
    let mut loops = Vec::new();
    for contour in &parsed.contours {
        let mut lp: Vec<Pt> = Vec::new();
        for seg in contour {
            let pts = flatten_seg(seg, &parsed.oncurve, &parsed.offcurve, 32);
            if lp.is_empty() {
                lp.extend_from_slice(&pts);
            } else {
                lp.extend_from_slice(&pts[..pts.len().saturating_sub(1)]);
            }
        }
        // Prototype inputs are never empty; an empty loop fails closed
        // downstream via the winding guard rather than here.
        if let Some(first) = lp.first().copied() {
            lp.push(first);
        }
        loops.push(lp);
    }
    loops
}

/// Straight border portions with certified winding visibility.
///
/// Canonical discovery builds split sites from exact rational crossings with
/// one transported common point; the legacy float path keeps the reference
/// control exactly. Segments split at exact straight intersections; each
/// portion keeps affine correspondence to its original edge endpoints.
pub fn split_visible(
    parsed: &Parsed,
    canonical: bool,
) -> (Vec<Portion>, Vec<BBox>, Vec<Vec<Pt>>, Vec<(Vec<Pt>, BBox)>) {
    let mut edges: Vec<Edge> = Vec::new();
    for (ci, contour) in parsed.contours.iter().enumerate() {
        for (si, seg) in contour.iter().enumerate() {
            if let Segment::Line { a, b } = *seg {
                edges.push(Edge {
                    contour: ci,
                    seg: si,
                    i0: a,
                    i1: b,
                    p0: parsed.oncurve[a],
                    p1: parsed.oncurve[b],
                });
            }
        }
    }
    let exact_sites = if canonical {
        Some(exact_cut_sites(&edges))
    } else {
        None
    };
    let mut legacy: Vec<HashSet<u64>> = Vec::new();
    if !canonical {
        legacy = (0..edges.len()).map(|_| HashSet::new()).collect();
        for i in 0..edges.len() {
            for j in (i + 1)..edges.len() {
                let (a, b) = (&edges[i], &edges[j]);
                if a.contour == b.contour && a.seg.abs_diff(b.seg) <= 1 {
                    continue;
                }
                if let Some((t, u)) = seg_intersection(a.p0, a.p1, b.p0, b.p1) {
                    legacy[i].insert(t.to_bits());
                    legacy[j].insert(u.to_bits());
                }
            }
        }
    }
    let mut straight_loops: Vec<Vec<Pt>> = Vec::new();
    let mut curve_flats: Vec<(Vec<Pt>, BBox)> = Vec::new();
    let mut curve_boxes: Vec<BBox> = Vec::new();
    // Exact prototype sequence: the first segment contributes all its
    // points, later ones drop only their last point (pts[:-1]).
    for contour in &parsed.contours {
        let mut straight: Vec<Pt> = Vec::new();
        for seg in contour {
            if seg.is_line() {
                let pts = controls(seg, &parsed.oncurve, &parsed.offcurve);
                if straight.is_empty() {
                    straight.extend_from_slice(&pts);
                } else {
                    straight.extend_from_slice(&pts[..pts.len().saturating_sub(1)]);
                }
            } else {
                let flat = flatten_seg(seg, &parsed.oncurve, &parsed.offcurve, 32);
                let bbox = curve_box(seg, &parsed.oncurve, &parsed.offcurve);
                curve_flats.push((flat.clone(), bbox));
                curve_boxes.push(bbox);
                if straight.is_empty() {
                    straight.extend_from_slice(&flat);
                } else {
                    straight.extend_from_slice(&flat[..flat.len().saturating_sub(1)]);
                }
            }
        }
        if let Some(first) = straight.first().copied() {
            straight.push(first);
        }
        straight_loops.push(straight);
    }
    let mut portions = Vec::new();
    for (i, edge) in edges.iter().enumerate() {
        let dx = edge.p1[0] - edge.p0[0];
        let dy = edge.p1[1] - edge.p0[1];
        let length = dx.hypot(dy);
        if !(length > 0.0) {
            continue;
        }
        if let Some(sites) = exact_sites.as_ref() {
            let zero = BigRational::zero();
            let one = BigRational::integer(1);
            let mut bounds: Vec<BigRational> = vec![zero.clone(), one.clone()];
            bounds.extend(sites[i].keys().cloned());
            bounds.sort();
            bounds.dedup();
            let normal = [-dy / length, dx / length];
            for pair in bounds.windows(2) {
                let (t0r, t1r) = (&pair[0], &pair[1]);
                if t1r <= t0r {
                    continue;
                }
                let f0 = t0r.to_f64().unwrap_or(0.0);
                let f1 = t1r.to_f64().unwrap_or(1.0);
                let q0 = sites[i]
                    .get(t0r)
                    .copied()
                    .unwrap_or([edge.p0[0] + dx * f0, edge.p0[1] + dy * f0]);
                let q1 = sites[i]
                    .get(t1r)
                    .copied()
                    .unwrap_or([edge.p0[0] + dx * f1, edge.p0[1] + dy * f1]);
                let mid = [(q0[0] + q1[0]) / 2.0, (q0[1] + q1[1]) / 2.0];
                let (hidden, unknown) = classify_portion(
                    mid,
                    normal,
                    edge,
                    &edges,
                    &straight_loops,
                    &curve_flats,
                    &curve_boxes,
                );
                portions.push(Portion {
                    contour: edge.contour,
                    seg: edge.seg,
                    t0: f0,
                    t1: f1,
                    p0: q0,
                    p1: q1,
                    i0: edge.i0,
                    i1: edge.i1,
                    hidden,
                    unknown,
                });
            }
        } else {
            let mut params: Vec<f64> = legacy[i]
                .iter()
                .map(|bits| f64::from_bits(*bits))
                .filter(|&t| 0.0 < t && t < 1.0)
                .collect();
            params.sort_by(|a, b| a.partial_cmp(b).unwrap());
            let mut bounds = vec![0.0];
            bounds.extend(params);
            bounds.push(1.0);
            let normal = [-dy / length, dx / length];
            for pair in bounds.windows(2) {
                let (t0, t1) = (pair[0], pair[1]);
                if !(t1 > t0) {
                    continue;
                }
                let q0 = [edge.p0[0] + dx * t0, edge.p0[1] + dy * t0];
                let q1 = [edge.p0[0] + dx * t1, edge.p0[1] + dy * t1];
                let mid = [(q0[0] + q1[0]) / 2.0, (q0[1] + q1[1]) / 2.0];
                let (hidden, unknown) = classify_portion(
                    mid,
                    normal,
                    edge,
                    &edges,
                    &straight_loops,
                    &curve_flats,
                    &curve_boxes,
                );
                portions.push(Portion {
                    contour: edge.contour,
                    seg: edge.seg,
                    t0,
                    t1,
                    p0: q0,
                    p1: q1,
                    i0: edge.i0,
                    i1: edge.i1,
                    hidden,
                    unknown,
                });
            }
        }
    }
    (portions, curve_boxes, straight_loops, curve_flats)
}

/// Least distance from a portion midpoint to other boundaries.
///
/// Straight borders use exact point-segment distance; curves use bbox
/// distance, a certified lower bound since the curve lies inside its
/// control-hull box. A zero bbox distance is only the lower bound, never
/// actual contact.
fn portion_clearance(
    mid: Pt,
    edge: &Edge,
    edges: &[Edge],
    curve_boxes: &[BBox],
) -> (f64, &'static str) {
    let mut best: Option<f64> = None;
    let mut cause = "no-clearance";
    for other in edges {
        if other.contour == edge.contour && other.seg == edge.seg {
            continue;
        }
        let dist = seg_point_dist(mid, other.p0, other.p1);
        if best.is_none_or(|b: f64| dist < b) {
            best = Some(dist);
            cause = "clear";
        }
    }
    for bbox in curve_boxes {
        let dist = bbox_point_dist(mid, bbox);
        if dist == 0.0 {
            return (0.0, "box-zero");
        }
        if best.is_none_or(|b: f64| dist < b) {
            best = Some(dist);
            cause = "clear";
        }
    }
    match best {
        None => (0.0, "no-clearance"),
        Some(0.0) => (0.0, "touch"),
        Some(b) => (b, cause),
    }
}

fn classify_portion(
    mid: Pt,
    normal: Pt,
    edge: &Edge,
    edges: &[Edge],
    straight_loops: &[Vec<Pt>],
    curve_flats: &[(Vec<Pt>, BBox)],
    curve_boxes: &[BBox],
) -> (bool, bool) {
    let (clearance, cause) = portion_clearance(mid, edge, edges, curve_boxes);
    if cause == "no-clearance" || cause == "box-zero" {
        return (false, true);
    }
    if cause == "touch" {
        return (true, false);
    }
    let off = clearance / 2.0;
    let sides = [
        certified_winding(
            [mid[0] + normal[0] * off, mid[1] + normal[1] * off],
            straight_loops,
            curve_flats,
        ),
        certified_winding(
            [mid[0] - normal[0] * off, mid[1] - normal[1] * off],
            straight_loops,
            curve_flats,
        ),
    ];
    if sides.iter().any(|s| s.is_none()) {
        return (false, true);
    }
    (sides.iter().all(|s| s.unwrap() != 0), false)
}

/// Competitors include uncertain boundaries conservatively: only proven
/// both-sides-nonzero hidden interior seams are dropped.
pub fn visible_borders(portions: &[Portion]) -> Vec<Border> {
    let mut others = Vec::new();
    for p in portions {
        if p.hidden {
            continue;
        }
        others.push(Border {
            seg: (p.p0, p.p1),
            tag: format!("edge({},{},{:.6},{:.6})", p.contour, p.seg, p.t0, p.t1),
            key: (p.contour, p.seg, p.t0, p.t1),
        });
    }
    others
}

/// Convert core borders to the intervals worker API; `key` stays core-side.
fn api_borders(borders: &[Border]) -> Vec<intervals::Border> {
    borders
        .iter()
        .map(|b| intervals::Border {
            seg: [b.seg.0, b.seg.1],
            tag: b.tag.clone(),
        })
        .collect()
}

fn pair_others(a: &Portion, b: &Portion, borders: &[Border]) -> Vec<Border> {
    borders
        .iter()
        .filter(|o| {
            o.key != (a.contour, a.seg, a.t0, a.t1) && o.key != (b.contour, b.seg, b.t0, b.t1)
        })
        .cloned()
        .collect()
}

pub fn others_for(pair: &PairCombo, borders: &[Border]) -> Vec<Border> {
    pair_others(&pair.a, &pair.b, borders)
}

/// Any remaining contact between certified cores is conflict: overlap or
/// touch fails closed as double ownership rather than guessing a boundary.
fn strict_overlap(first: [f64; 2], second: [f64; 2]) -> bool {
    !(first[1] < second[0] || second[1] < first[0])
}

/// Opposing visible border portions with certified ink intervals.
#[derive(Debug)]
pub struct PairCombo {
    pub a: Portion,
    pub b: Portion,
    pub dom: intervals::Dominance,
}

/// Portion ownership drops every pair sharing a whole portion; interval
/// ownership drops only provably overlapping contact-foot ranges.
pub fn recognize(
    portions: &[Portion],
    loops: &[Vec<Pt>],
    interval: bool,
) -> (Vec<Pair>, Vec<Skipped>) {
    let visible: Vec<&Portion> = portions
        .iter()
        .filter(|p| !p.hidden && !p.unknown)
        .collect();
    let borders = visible_borders(portions);
    let mut combos: Vec<PairCombo> = Vec::new();
    let mut skipped: Vec<Skipped> = Vec::new();
    for i in 0..visible.len() {
        for j in (i + 1)..visible.len() {
            let (a, b) = (visible[i], visible[j]);
            let seg_a = [a.p0, a.p1];
            let seg_b = [b.p0, b.p1];
            let Some(cor) = intervals::corridor(seg_a, seg_b) else {
                continue;
            };
            let frame = intervals::frame(seg_a, seg_b, &cor);
            if frame.status != "ok" {
                skipped.push(Skipped {
                    pair: (a.seg, b.seg),
                    reason: format!("opposition-{}", frame.status),
                });
                continue;
            }
            let others = pair_others(a, b, &borders);
            let api_others = api_borders(&others);
            let dom = intervals::dominance(seg_a, seg_b, &api_others, Some(loops));
            if dom.status != "ok" || dom.intervals.is_empty() {
                skipped.push(Skipped {
                    pair: (a.seg, b.seg),
                    reason: format!("no-dominance-{}", dom.status),
                });
                continue;
            }
            combos.push(PairCombo {
                a: (*a).clone(),
                b: (*b).clone(),
                dom,
            });
        }
    }
    if interval {
        return resolve_interval(combos, skipped, &borders, loops);
    }
    let mut use_count: HashMap<(usize, usize, u64, u64), usize> = HashMap::new();
    for combo in &combos {
        for side in [&combo.a, &combo.b] {
            let key = (side.contour, side.seg, side.t0.to_bits(), side.t1.to_bits());
            *use_count.entry(key).or_insert(0) += 1;
        }
    }
    let mut pairs = Vec::new();
    for combo in combos {
        let keys = [
            (
                combo.a.contour,
                combo.a.seg,
                combo.a.t0.to_bits(),
                combo.a.t1.to_bits(),
            ),
            (
                combo.b.contour,
                combo.b.seg,
                combo.b.t0.to_bits(),
                combo.b.t1.to_bits(),
            ),
        ];
        if keys
            .iter()
            .any(|k| use_count.get(k).copied().unwrap_or(0) > 1)
        {
            skipped.push(Skipped {
                pair: (combo.a.seg, combo.b.seg),
                reason: "ambiguous-portion".to_string(),
            });
            continue;
        }
        pairs.push(Pair {
            a: combo.a,
            b: combo.b,
            dom: combo.dom,
            feet: None,
        });
    }
    (pairs, skipped)
}

/// Skipped pair with its cause; evidence only, never a verdict.
#[derive(Clone, Debug)]
pub struct Skipped {
    pub pair: (usize, usize),
    pub reason: String,
}

/// Interval-level ownership over certified interval cores.
fn resolve_interval(
    mut combos: Vec<PairCombo>,
    mut skipped: Vec<Skipped>,
    borders: &[Border],
    loops: &[Vec<Pt>],
) -> (Vec<Pair>, Vec<Skipped>) {
    let mut feet: Vec<Option<Vec<intervals::FootRange>>> = Vec::new();
    let mut bad: HashSet<usize> = HashSet::new();
    for (pos, combo) in combos.iter_mut().enumerate() {
        let seg_a = [combo.a.p0, combo.a.p1];
        let seg_b = [combo.b.p0, combo.b.p1];
        let others = others_for(combo, borders);
        let api_others = api_borders(&others);
        let core =
            intervals::core_intervals(seg_a, seg_b, &combo.dom.intervals, &api_others, Some(loops));
        let ranges = match core {
            None => None,
            Some(core) => {
                let ranges = intervals::foot_ranges(seg_a, seg_b, &core);
                match ranges {
                    None => None,
                    Some(r) => {
                        combo.dom.intervals = core;
                        Some(r)
                    }
                }
            }
        };
        match ranges {
            None => {
                bad.insert(pos);
                skipped.push(Skipped {
                    pair: (combo.a.seg, combo.b.seg),
                    reason: "foot-uncertain".to_string(),
                });
                feet.push(None);
            }
            Some(r) => {
                feet.push(Some(r));
            }
        }
    }
    let mut claimants: HashMap<(usize, usize, u64, u64), Vec<usize>> = HashMap::new();
    for (pos, combo) in combos.iter().enumerate() {
        for side in [&combo.a, &combo.b] {
            let key = (side.contour, side.seg, side.t0.to_bits(), side.t1.to_bits());
            claimants.entry(key).or_default().push(pos);
        }
    }
    let mut drop: HashSet<usize> = HashSet::new();
    // Deterministic diagnostic order: HashMap iteration is random.
    let mut ordered: Vec<&(usize, usize, u64, u64)> = claimants.keys().collect();
    ordered.sort();
    for key in ordered {
        let members = &claimants[key];
        for x in 0..members.len() {
            for y in (x + 1)..members.len() {
                let (px, py) = (members[x], members[y]);
                if bad.contains(&px) || bad.contains(&py) {
                    continue;
                }
                let palette = |combo: &PairCombo| {
                    if (
                        combo.a.contour,
                        combo.a.seg,
                        combo.a.t0.to_bits(),
                        combo.a.t1.to_bits(),
                    ) == *key
                    {
                        0
                    } else {
                        1
                    }
                };
                let (fx, fy) = (palette(&combos[px]), palette(&combos[py]));
                let side = |r: &intervals::FootRange, index: usize| {
                    if index == 0 {
                        r.a
                    } else {
                        r.b
                    }
                };
                let clash = feet[px].as_ref().unwrap().iter().any(|rx| {
                    feet[py]
                        .as_ref()
                        .unwrap()
                        .iter()
                        .any(|ry| strict_overlap(side(rx, fx), side(ry, fy)))
                });
                if clash {
                    drop.insert(px);
                    drop.insert(py);
                }
            }
        }
    }
    let mut pairs = Vec::new();
    for ((pos, combo), franges) in combos.into_iter().enumerate().zip(feet) {
        if drop.contains(&pos) {
            if !bad.contains(&pos) {
                skipped.push(Skipped {
                    pair: (combo.a.seg, combo.b.seg),
                    reason: "ambiguous-portion".to_string(),
                });
            }
            continue;
        }
        pairs.push(Pair {
            a: combo.a,
            b: combo.b,
            dom: combo.dom,
            feet: franges,
        });
    }
    (pairs, skipped)
}

/// Longest kept dominance interval; first maximum wins.
pub fn longest_span(dom: &intervals::Dominance) -> Option<(f64, f64)> {
    let mut best: Option<(f64, f64, f64)> = None;
    for iv in &dom.intervals {
        let len = iv.hi - iv.lo;
        if best.is_none_or(|(_, _, blen)| len > blen) {
            best = Some((iv.lo, iv.hi, len));
        }
    }
    best.map(|(lo, hi, _)| (lo, hi))
}

/// Certified width stations over the longest kept interval.
///
/// Stations sit strictly inside one open dominance interval; every sampled
/// disk is rechecked. A missing contact abstains instead of interpolating.
pub fn station_contacts(
    seg_a: [[f64; 2]; 2],
    seg_b: [[f64; 2]; 2],
    dom: &intervals::Dominance,
    others: &[Border],
    loops: &[Vec<Pt>],
) -> Option<Vec<Station>> {
    let (lo, hi) = longest_span(dom)?;
    if !(hi > lo) {
        return None;
    }
    let api_others = api_borders(others);
    let mut out = Vec::new();
    for frac in [0.25, 0.5, 0.75] {
        let s = lo + (hi - lo) * frac;
        let seen = intervals::contact(seg_a, seg_b, s, &api_others, Some(loops));
        if seen.status != "ok" {
            return None;
        }
        let Some(hit) = seen.hit else {
            return None;
        };
        out.push(Station { s, hit });
    }
    Some(out)
}

/// Portion-fraction point: edge fraction `t0 + (t1 - t0) * frac`.
///
/// Virtual cut parameters keep exact affine correspondence to the original
/// edge endpoints; ignoring the cuts would misplace interior station feet.
pub fn edge_point(side: &Portion, frac: f64, coords: &[Pt]) -> Pt {
    let t = side.t0 + (side.t1 - side.t0) * frac;
    let p0 = coords[side.i0];
    let p1 = coords[side.i1];
    [p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t]
}

/// Vertical rectilinear opposing pairs; exact equality decides.
///
/// Horizontal bars (serifs, caps) are excluded: they are not the upright
/// reference even when rectilinear.
pub fn upright_pairs(pairs: &[Pair]) -> Vec<&Pair> {
    pairs
        .iter()
        .filter(|pair| {
            axis_of(pair.a.p0, pair.a.p1) == Some('x') && axis_of(pair.b.p0, pair.b.p1) == Some('x')
        })
        .collect()
}

/// True when an uncertified curve may enter the pair's ink zone.
///
/// Curves are tested per segment against their control-hull boxes; box
/// overlap alone does not abstain when every station's medial disk clears
/// the hull box.
pub fn near_curves(pair: &Pair, stations: &[Station], boxes: &[BBox]) -> bool {
    let xs = [pair.a.p0[0], pair.a.p1[0], pair.b.p0[0], pair.b.p1[0]];
    let ys = [pair.a.p0[1], pair.a.p1[1], pair.b.p0[1], pair.b.p1[1]];
    let bbox = (
        xs.iter().cloned().fold(f64::INFINITY, f64::min),
        ys.iter().cloned().fold(f64::INFINITY, f64::min),
        xs.iter().cloned().fold(f64::NEG_INFINITY, f64::max),
        ys.iter().cloned().fold(f64::NEG_INFINITY, f64::max),
    );
    for hull in boxes {
        if !bbox_overlap(&bbox, hull) {
            continue;
        }
        let mut clear = true;
        for st in stations {
            if bbox_point_dist(st.hit.center, hull) <= st.hit.r {
                clear = false;
                break;
            }
        }
        if !clear {
            return true;
        }
    }
    false
}

/// Ink test at a station center: nonzero, certified, or neither.
///
/// White (counter) pairs need an explicit separate model, so only ink pairs
/// proceed; uncertified queries abstain rather than guessing the fill.
fn inked(center: Pt, straight_loops: &[Vec<Pt>], curve_flats: &[(Vec<Pt>, BBox)]) -> Option<bool> {
    certified_winding(center, straight_loops, curve_flats).map(|w| w != 0)
}

/// Certified stations and source frame for one diagonal pair.
pub fn prepare_pair(
    pair: &Pair,
    borders: &[Border],
    loops: &[Vec<Pt>],
    straights: &[Vec<Pt>],
    flats: &[(Vec<Pt>, BBox)],
    curve_boxes: &[BBox],
    fitted_coords: &[Pt],
    exact_curves: &[Vec<Pt>],
) -> Result<PreppedPair, &'static str> {
    let (a, b) = (&pair.a, &pair.b);
    if axis_of(a.p0, a.p1).is_some() || axis_of(b.p0, b.p1).is_some() {
        return Err("rectilinear-side");
    }
    let seg_a = [a.p0, a.p1];
    let seg_b = [b.p0, b.p1];
    let Some(cor) = intervals::corridor(seg_a, seg_b) else {
        return Err("no-corridor");
    };
    let direction = cor.d;
    if direction[0] == 0.0 || direction[1] == 0.0 {
        return Err("axis-degenerate");
    }
    let others = pair_others(a, b, borders);
    let Some(stations) = station_contacts(seg_a, seg_b, &pair.dom, &others, loops) else {
        return Err("station-uncertified");
    };
    let clear = stations.iter().all(|st| {
        exact_curves
            .iter()
            .all(|ctrls| super::curves::disk_clear(st.hit.center, st.hit.r, ctrls).0)
    });
    if !clear {
        return Err("curved-neighbor");
    }
    if exact_curves.is_empty() && near_curves(pair, &stations, curve_boxes) {
        return Err("curved-neighbor");
    }
    let mid = &stations[stations.len() / 2].hit;
    let mut normal = cor.u;
    let side = (mid.qb[0] - mid.qa[0]) * normal[0] + (mid.qb[1] - mid.qa[1]) * normal[1];
    if side == 0.0 {
        return Err("degenerate-projection");
    }
    let orient = if side > 0.0 { 1.0 } else { -1.0 };
    normal = [normal[0] * orient, normal[1] * orient];
    match inked(mid.center, straights, flats) {
        None => return Err("winding-uncertain-center"),
        Some(false) => return Err("white-pair"),
        Some(true) => {}
    }
    let src_widths: Vec<f64> = stations.iter().map(|st| st.hit.width).collect();
    let fit_a: Vec<Pt> = stations
        .iter()
        .map(|st| edge_point(a, st.hit.sa, fitted_coords))
        .collect();
    let fit_b: Vec<Pt> = stations
        .iter()
        .map(|st| edge_point(b, st.hit.sb, fitted_coords))
        .collect();
    let fit_widths: Vec<f64> = fit_a
        .iter()
        .zip(fit_b.iter())
        .map(|(qa, qb)| ((qb[0] - qa[0]) * normal[0] + (qb[1] - qa[1]) * normal[1]).abs())
        .collect();
    let (lo, hi) = longest_span(&pair.dom).unwrap_or((0.0, 0.0));
    let count = stations.len() as f64;
    Ok(PreppedPair {
        id: format!(
            "a({},{},{:.6},{:.6})/b({},{},{:.6},{:.6})",
            a.contour, a.seg, a.t0, a.t1, b.contour, b.seg, b.t0, b.t1
        ),
        a: a.clone(),
        b: b.clone(),
        normal,
        stations,
        src_widths,
        fit_widths,
        arc: (hi - lo) / count,
        span_lo: lo,
        span_hi: hi,
    })
}

/// Swept straight-border homotopy against fixed curves.
///
/// Only changed straight segments sweep; pinned and untouched geometry is
/// bit-identical and needs no homotopy.
pub fn curve_sweep_ok(
    parsed: &Parsed,
    fitted_oncurve: &[Pt],
    candidate: &[FittedCommand],
    ctrls: &[Vec<Pt>],
) -> Result<(), &'static str> {
    let cand = parse_commands(candidate).map_err(|_| "unparseable-candidate")?;
    let mut old_segs = Vec::new();
    let mut new_segs = Vec::new();
    for contour in &parsed.contours {
        for seg in contour {
            if !seg.is_line() {
                continue;
            }
            let (i, j) = seg.endpoints();
            let old = fitted_oncurve[i];
            let cand_pt = cand.oncurve[i];
            let old_b = fitted_oncurve[j];
            let cand_b = cand.oncurve[j];
            if old != cand_pt || old_b != cand_b {
                old_segs.push(((old[0], old[1]), (old_b[0], old_b[1])));
                new_segs.push(((cand_pt[0], cand_pt[1]), (cand_b[0], cand_b[1])));
            }
        }
    }
    let curves: Vec<Vec<Pt>> = ctrls.to_vec();
    let (ok, reason) = super::curves::movement_clear(&old_segs, &new_segs, &curves);
    if ok {
        Ok(())
    } else {
        Err(reason)
    }
}

/// Split-signature evidence: contour, seg and hidden triples.
pub fn topology_signature(portions: &[Portion]) -> Vec<(usize, usize, bool)> {
    portions
        .iter()
        .map(|p| (p.contour, p.seg, p.hidden))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn segment_bounds_retain_closed_contacts() {
        let a = segment_bounds([0.0, 0.0], [0.0, 2.0]).unwrap();
        for (p, q) in [
            ([0.0, 2.0], [0.0, 3.0]),
            ([0.0, 1.0], [0.0, 3.0]),
            ([-1.0, 1.0], [1.0, 1.0]),
            ([0.0, 2.0], [2.0, 0.0]),
            ([-0.0, -0.0], [-0.0, 1.0]),
        ] {
            assert!(bbox_overlap(&a, &segment_bounds(p, q).unwrap()));
            assert!(bbox_overlap(&a, &segment_bounds(q, p).unwrap()));
        }
        let gap = f64::from_bits(1);
        assert!(!bbox_overlap(
            &a,
            &segment_bounds([gap, 0.0], [gap, 2.0]).unwrap()
        ));
        let next = f64::from_bits(1.0f64.to_bits() + 1);
        assert!(!bbox_overlap(
            &segment_bounds([0.0, 0.0], [1.0, 1.0]).unwrap(),
            &segment_bounds([next, 0.0], [next, 1.0]).unwrap(),
        ));
        assert!(segment_bounds([f64::NAN, 0.0], [1.0, 1.0]).is_none());
        assert!(segment_bounds([0.0, 0.0], [1.0, f64::INFINITY]).is_none());
    }

    #[test]
    fn separated_segment_bounds_exclude_exact_split_sites() {
        // The unchanged rational intersection constructor supplies the
        // independent rejection oracle. It contains no bounds shortcut.
        let points: Vec<Pt> = [-1.0, 0.0, 1.0]
            .into_iter()
            .flat_map(|x| [-1.0, 0.0, 1.0].map(|y| [x, y]))
            .chain([[0.25, 0.5], [-0.5, 0.25], [1.0, 1.0 + f64::EPSILON]])
            .collect();
        let mut segments = Vec::new();
        for (i, &p) in points.iter().enumerate() {
            for &q in &points[i + 1..] {
                segments.push((p, q, segment_bounds(p, q).unwrap()));
            }
        }
        for &(a, b, box_a) in &segments {
            for &(c, d, box_b) in &segments {
                if !bbox_overlap(&box_a, &box_b) {
                    assert!(exact_intersection(a, b, c, d).is_none());
                }
            }
        }
    }

    fn square() -> Vec<FittedCommand> {
        vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(10.0, 0.0),
            FittedCommand::LineTo(10.0, 10.0),
            FittedCommand::LineTo(0.0, 10.0),
            FittedCommand::Close,
        ]
    }

    #[test]
    fn parse_square_counts_four_vertices() {
        let parsed = parse_commands(&square()).unwrap();
        assert_eq!(parsed.oncurve.len(), 4);
        assert_eq!(parsed.contours.len(), 1);
        assert_eq!(parsed.contours[0].len(), 4);
    }

    #[test]
    fn correspondence_requires_identical_ops() {
        let mut other = square();
        other.push(FittedCommand::Close);
        assert!(check_correspondence(&square(), &square()));
        assert!(!check_correspondence(&square(), &other));
    }

    #[test]
    fn nonfinite_coordinates_are_malformed() {
        let mut cmds = square();
        cmds[1] = FittedCommand::LineTo(f32::INFINITY, 0.0);
        assert!(parse_commands(&cmds).is_err());
    }

    #[test]
    fn rounding_ties_go_toward_positive_infinity() {
        assert_eq!(round_26_6(0.5 / 64.0), 1.0 / 64.0);
        assert_eq!(round_26_6(-0.5 / 64.0), 0.0);
        assert_eq!(round_26_6(1.0078125), 65.0 / 64.0);
        assert_eq!(1.0f32.to_bits(), 0x3f80_0000);
    }

    #[test]
    fn winding_inside_is_nonzero_outside_is_zero() {
        let loops = vec![vec![[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]];
        assert_ne!(certified_winding([5.0, 5.0], &loops, &[]), Some(0));
        assert_eq!(certified_winding([20.0, 5.0], &loops, &[]), Some(0));
    }

    #[test]
    fn closing_vertex_decides_region_count() {
        // The last stored vertex participates in the ray count: moving
        // it flips a query point from outside (0) to inside (nonzero).
        // A pop-the-last-vertex implementation counts both as outside.
        let lower = vec![vec![[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]]];
        let upper = vec![vec![[0.0, 0.0], [10.0, 0.0], [0.0, 10.0]]];
        assert_eq!(winding_dir([2.0, 5.0], &lower, 0, true), 0);
        assert_eq!(winding_dir([2.0, 5.0], &upper, 0, true), 1);
        assert_ne!(winding_dir([8.0, 2.0], &lower, 0, true), 0);
    }

    #[test]
    fn winding_is_rotation_and_closure_invariant() {
        // Cyclic rotation and an explicit closing duplicate must not
        // change the count; both failed under unconditional popping.
        let tri = vec![vec![[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]]];
        let rotated = vec![vec![[10.0, 0.0], [10.0, 10.0], [0.0, 0.0]]];
        let explicit = vec![vec![[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 0.0]]];
        let base = winding_dir([8.0, 2.0], &tri, 0, true);
        assert_ne!(base, 0);
        assert_eq!(winding_dir([8.0, 2.0], &rotated, 0, true), base);
        assert_eq!(winding_dir([8.0, 2.0], &explicit, 0, true), base);
        assert_eq!(winding_dir([2.0, 5.0], &explicit, 0, true), 0);
    }

    #[test]
    fn uncertain_ray_abstains() {
        let loops = vec![vec![[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]];
        let flats = vec![(vec![[4.0, 4.0], [6.0, 6.0]], (4.0, -100.0, 6.0, 100.0))];
        assert_eq!(certified_winding([5.0, 5.0], &loops, &flats), None);
    }

    #[test]
    fn crossing_segments_split_both_edges() {
        let parsed = parse_commands(&vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(10.0, 10.0),
            FittedCommand::Close,
            FittedCommand::MoveTo(0.0, 10.0),
            FittedCommand::LineTo(10.0, 0.0),
            FittedCommand::Close,
        ])
        .unwrap();
        let (portions, _, _, _) = split_visible(&parsed, true);
        // Each contour carries its diagonal plus the implicit closing
        // segment; all four edges split at the crossing.
        assert_eq!(portions.len(), 8);
        for p in &portions {
            assert!((p.t1 - p.t0 - 0.5).abs() < 1e-12);
        }
    }

    #[test]
    fn transported_touch_point_is_shared() {
        let parsed = parse_commands(&vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(10.0, 0.0),
            FittedCommand::Close,
            FittedCommand::MoveTo(5.0, 0.0),
            FittedCommand::LineTo(5.0, 10.0),
            FittedCommand::Close,
        ])
        .unwrap();
        let (portions, _, _, _) = split_visible(&parsed, true);
        // Both horizontal edges split at the touch; the vertical edges
        // meet it at endpoints and stay whole.
        assert_eq!(portions.len(), 6);
        let mut joints: Vec<Pt> = portions.iter().map(|p| p.p1).collect();
        joints.sort_by(|a, b| a[0].partial_cmp(&b[0]).unwrap());
        assert!(joints.iter().any(|q| q[0] == 5.0 && q[1] == 0.0));
    }

    #[test]
    fn legacy_and_canonical_agree_on_simple_crossing() {
        let cmds = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(10.0, 10.0),
            FittedCommand::Close,
            FittedCommand::MoveTo(0.0, 10.0),
            FittedCommand::LineTo(10.0, 0.0),
            FittedCommand::Close,
        ];
        let parsed = parse_commands(&cmds).unwrap();
        let (canon, _, _, _) = split_visible(&parsed, true);
        let (legacy, _, _, _) = split_visible(&parsed, false);
        assert_eq!(canon.len(), legacy.len());
    }

    #[test]
    fn square_sides_find_no_upright_pair() {
        let parsed = parse_commands(&square()).unwrap();
        let (portions, _, loops, _) = split_visible(&parsed, false);
        let (pairs, _) = recognize(&portions, &loops, false);
        assert!(pairs.is_empty());
        assert!(upright_pairs(&pairs).is_empty());
    }
}
