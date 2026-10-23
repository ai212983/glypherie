//! General curved-stroke horizontal completion (native port of the smooth prototype).
//!
//! Source: Hobby (31)-(33) sampled normal displacement with frozen
//! source tangents and midpoint arc weights, (2),(3) strain projection
//! through the cubic derivative (project adaptation in
//! `docs/hobby-fitting.md`), (4),(5) medial width, (17) relative-contrast
//! coupling; Hersch sections 5-6 grid/parallel borders. Join certificate:
//! G1 cross determinant linearized with frozen upstream coefficients
//! (Hobby linearity requirement). Delivery: station-disk, hull, sweep and
//! exact-arrangement gates; exact upstream fallback on any failure.
//! Invariant: Y stays at the retained upstream fit, X moves only on free
//! axes; removal-free correction only. Only malformed, non-finite or
//! out-of-range input is an error. Runtime never uses experiments, Python
//! or corpus data. The bounded-equality solve is the maintained
//! `super::qp` active set; the moving-curve topology gate is the
//! maintained `super::curves::compare_substituted`.

#[cfg(test)]
use super::curves::poly_edges;
use super::curves::{
    boxes_strictly_separate as boxes_separate_f, convex_hull, hull_bbox as rat_box,
    hulls_meet_only_at, piece_chains, piece_hulls, strictly_disjoint, strictly_disjoint_exact,
};
use super::exact::Exact as BigRational;
use super::{
    abstain, acute, basis_row, curves, filtered, geometry, intervals, min_norm_solve,
    qp::{bounded_equalities, QpInfo},
    reference_meta, width_weight, FitResult, Reference, HEADROOM, MAX_COMMANDS,
};
use crate::{fail, probe::FittedCommand, Error};
use std::collections::{BTreeMap, HashMap, HashSet};

/// Dyadic substitution depths tried in order (prototype `DEPTHS`).
const DEPTHS: [usize; 3] = [2, 3, 4];
/// Curve shape quadrature intervals (prototype `curve_intervals=16`).
const CURVE_INTERVALS: usize = 16;
/// Prefix attempts from full step by halves (prototype `range(7)`).
const PREFIX_ATTEMPTS: usize = 7;
/// Nearest-26.6 half-quantum error per moved coordinate (prototype `ROUND_HALF`).
const ROUND_HALF: f64 = 1.0 / 128.0;
/// Box-gap work bound as a fraction of size (prototype `size_px / 4`).
const BOX_DIVISOR: f64 = 4.0;

/// Recognized opposing source-curve pair (prototype `recognize` record).
#[derive(Clone, Debug)]
pub(super) struct CurvePair {
    pub(super) a_ctrl: [usize; 3],
    pub(super) b_ctrl: [usize; 3],
    pub(super) a_t: f64,
    pub(super) b_t: f64,
    pub(super) medial: [f64; 2],
    pub(super) normal: [f64; 2],
    pub(super) width_2r: f64,
    pub(super) radii: [f64; 2],
    pub(super) approx_bound: f64,
    pub(super) arc: f64,
    pub(super) shape_ctrl: Vec<[usize; 3]>,
}

/// Real-outline segment reference with global control indices.
#[derive(Clone, Copy, Debug)]
pub(super) enum SegRef {
    Line { a: usize, b: usize },
    Quad { off: usize, a: usize, b: usize },
}

impl SegRef {
    fn start(self) -> usize {
        match self {
            SegRef::Line { a, .. } => a,
            SegRef::Quad { a, .. } => a,
        }
    }
}

/// One joint occurrence with exact classification (prototype `_joints`).
#[derive(Clone, Debug)]
pub(super) struct JointOcc {
    pub(super) prev: SegRef,
    pub(super) seg: SegRef,
    pub(super) smooth: bool,
    pub(super) degenerate: bool,
}

/// Exact point as a rational pair.
type Rat = (BigRational, BigRational);

fn lift(p: &[f64; 2]) -> Option<Rat> {
    Some((BigRational::from_f64(p[0])?, BigRational::from_f64(p[1])?))
}

fn cross_rat(o: &Rat, a: &Rat, b: &Rat) -> BigRational {
    (&a.0 - &o.0) * (&b.1 - &o.1) - (&a.1 - &o.1) * (&b.0 - &o.0)
}

#[cfg(test)]
/// Exact cross sign with no filtering: test reference.
fn cross_sign_rat_exact(o: &Rat, a: &Rat, b: &Rat) -> i8 {
    let v = cross_rat(o, a, b);
    if v.is_zero() {
        0
    } else if v.is_positive() {
        1
    } else {
        -1
    }
}

#[cfg(test)]
/// Exact on-segment test with no filtering: test reference.
fn on_segment(a: &Rat, b: &Rat, p: &Rat) -> bool {
    use std::cmp::{max, min};
    cross_sign_rat_exact(a, b, p) == 0
        && min(&a.0, &b.0) <= &p.0
        && &p.0 <= max(&a.0, &b.0)
        && min(&a.1, &b.1) <= &p.1
        && &p.1 <= max(&a.1, &b.1)
}

#[cfg(test)]
/// Exact segment-aware outside test via fan triangulation.
fn strictly_outside(pt: &Rat, poly: &[Rat]) -> bool {
    if poly.is_empty() {
        return true;
    }
    if poly.len() == 1 {
        return pt != &poly[0];
    }
    if poly.len() == 2 {
        let (a, b) = (&poly[0], &poly[1]);
        return !(pt == a || pt == b || on_segment(a, b, pt));
    }
    let ccw = cross_sign_rat_exact(&poly[0], &poly[1], &poly[2]) > 0;
    for i in 1..poly.len() - 1 {
        let (t0, t1, t2) = (&poly[0], &poly[i], &poly[i + 1]);
        let signs = [
            cross_sign_rat_exact(t0, t1, pt),
            cross_sign_rat_exact(t1, t2, pt),
            cross_sign_rat_exact(t2, t0, pt),
        ];
        if ccw && signs.iter().all(|&s| s >= 0) {
            return false;
        }
        if !ccw && signs.iter().all(|&s| s <= 0) {
            return false;
        }
    }
    true
}

#[cfg(test)]
/// Exact narrow phase with no filtering: test reference.
fn hulls_meet_only_at_exact(poly_p: &[Rat], poly_q: &[Rat], shared: &Rat) -> bool {
    let orient = |a: &Rat, b: &Rat, c: &Rat| -> i8 { cross_sign_rat_exact(a, b, c) };
    for (a, b) in poly_edges(poly_p) {
        for (c, d) in poly_edges(poly_q) {
            let (o1, o2, o3, o4) = (
                orient(&a, &b, &c),
                orient(&a, &b, &d),
                orient(&c, &d, &a),
                orient(&c, &d, &b),
            );
            if o1 * o2 < 0 && o3 * o4 < 0 {
                return false;
            }
            for (p, u, v) in [(&c, &a, &b), (&d, &a, &b), (&a, &c, &d), (&b, &c, &d)] {
                if on_segment(u, v, p) && p != shared {
                    return false;
                }
            }
        }
    }
    if !poly_p
        .iter()
        .filter(|v| *v != shared)
        .all(|v| strictly_outside(v, poly_q))
    {
        return false;
    }
    poly_q
        .iter()
        .filter(|v| *v != shared)
        .all(|v| strictly_outside(v, poly_p))
}

/// Substitution certification lives in the shared exact certificate
/// (`curves::certify_parsed`); this module keeps only the polyline build.

/// Substituted polyline edge with true-curve provenance.
struct SubEdge {
    p0: [f64; 2],
    p1: [f64; 2],
    prov: Option<([usize; 3], f64, f64)>,
}

/// Dyadic substitution with per-edge source intervals.
///
/// Lines pass through; each quad contributes its joint polyline with
/// `(t0, t1)` provenance per piece. The closing edge carries no
/// provenance and stays a competitor only.
fn substitute(parsed: &geometry::Parsed, depth: usize) -> (Vec<SubEdge>, Vec<Vec<[f64; 2]>>) {
    let no = parsed.oncurve.len();
    let mut edges: Vec<SubEdge> = Vec::new();
    let mut loops: Vec<Vec<[f64; 2]>> = Vec::new();
    for contour in &parsed.contours {
        let mut ring: Vec<[f64; 2]> = Vec::new();
        let mut first: Option<[f64; 2]> = None;
        let mut pen: Option<[f64; 2]> = None;
        let push = |pt: [f64; 2],
                    ring: &mut Vec<[f64; 2]>,
                    first: &mut Option<[f64; 2]>,
                    pen: &mut Option<[f64; 2]>| {
            if first.is_none() {
                *first = Some(pt);
            }
            if *pen != Some(pt) {
                ring.push(pt);
            }
            *pen = Some(pt);
        };
        for seg in contour {
            match *seg {
                geometry::Segment::Line { a, b } => {
                    let (p0, p1) = (parsed.oncurve[a], parsed.oncurve[b]);
                    push(p0, &mut ring, &mut first, &mut pen);
                    push(p1, &mut ring, &mut first, &mut pen);
                    edges.push(SubEdge { p0, p1, prov: None });
                }
                geometry::Segment::Quad { c, a, b } => {
                    let ctrls = [parsed.oncurve[a], parsed.offcurve[c], parsed.oncurve[b]];
                    let n = 1usize << depth;
                    for k in 0..n {
                        let t0 = k as f64 / n as f64;
                        let t1 = (k + 1) as f64 / n as f64;
                        let (p0, p1) = (eval_quad(&ctrls, t0), eval_quad(&ctrls, t1));
                        push(p0, &mut ring, &mut first, &mut pen);
                        push(p1, &mut ring, &mut first, &mut pen);
                        edges.push(SubEdge {
                            p0,
                            p1,
                            prov: Some(([a, no + c, b], t0, t1)),
                        });
                    }
                }
                geometry::Segment::Cubic { .. } => {}
            }
        }
        if let (Some(f), Some(p)) = (first, pen) {
            edges.push(SubEdge {
                p0: p,
                p1: f,
                prov: None,
            });
            ring.push(f);
        }
        loops.push(ring);
    }
    (edges, loops)
}

/// Quadratic Bezier point.
fn eval_quad(ctrls: &[[f64; 2]; 3], t: f64) -> [f64; 2] {
    let mt = 1.0 - t;
    [
        mt * mt * ctrls[0][0] + 2.0 * mt * t * ctrls[1][0] + t * t * ctrls[2][0],
        mt * mt * ctrls[0][1] + 2.0 * mt * t * ctrls[1][1] + t * t * ctrls[2][1],
    ]
}

/// Exact dyadic deviation bound of one quad piece (prototype `_piece_eps`).
fn piece_eps_rat(ctrls: &[Rat]) -> f64 {
    let two = BigRational::integer(2);
    let four = BigRational::integer(4);
    let dx = &ctrls[0].0 - &(&ctrls[1].0 * &two) + &ctrls[2].0;
    let dy = &ctrls[0].1 - &(&ctrls[1].1 * &two) + &ctrls[2].1;
    ((&dx * &dx + &dy * &dy).to_f64().unwrap_or(f64::INFINITY)).sqrt()
        / four.to_f64().unwrap_or(4.0)
}

fn box_gap(a: (f64, f64, f64, f64), b: (f64, f64, f64, f64)) -> f64 {
    (a.0 - b.2)
        .max(b.0 - a.2)
        .max(0.0)
        .hypot((a.1 - b.3).max(b.1 - a.3).max(0.0))
}

/// Exact squared contact radius `(w/2 ± shell)²` for the source-contact
/// certificate.
///
/// Both inputs lift exactly (prototype `Fraction(w)/2 ± Fraction(shell)`
/// squared); `None` on non-finite input fails closed at the call site,
/// matching the old malformed-radius rejection. `upper` selects the
/// margin shell, otherwise the shrink shell.
fn contact_r2(w_poly: f64, shell: f64, upper: bool) -> Option<BigRational> {
    let (w, s) = match (BigRational::from_f64(w_poly), BigRational::from_f64(shell)) {
        (Some(w), Some(s)) => (w, s),
        _ => return None,
    };
    let two = BigRational::integer(2);
    let r = if upper {
        &w / &two + &s
    } else {
        &w / &two - &s
    };
    Some(&r * &r)
}

/// Certified-intermediate curved contacts beyond axis extrema.
///
/// Pairing runs per source-curve pair over the polygonal intermediate;
/// every pair keeps its longest-span dominance-interval midpoint, so
/// shared movement solves jointly instead of pruned. Recognition itself
/// is unbounded (prototype `recognize(source)` with `size_px=None`): the
/// box-gap skip is an optional runtime work bound only, never a
/// geometric eligibility rule, so the fit entry passes infinity.
pub(super) fn recognize(
    source: &[FittedCommand],
    size_px: f64,
) -> (Vec<CurvePair>, serde_json::Value) {
    let mut rejected: BTreeMap<String, usize> = BTreeMap::new();
    let mut reject = |reason: &str| {
        *rejected.entry(reason.to_string()).or_insert(0) += 1;
    };
    let fail = |reason: &str, rejected: &BTreeMap<String, usize>| {
        (
            Vec::new(),
            serde_json::json!({"candidates": 0, "rejected": rejected, "reason": reason}),
        )
    };
    let Ok(parsed) = geometry::parse_commands(source) else {
        reject("malformed-commands");
        return fail("malformed-commands", &rejected);
    };
    if parsed.contours.len() != 1 {
        reject("multi-contour-unsupported");
        return fail("multi-contour-unsupported", &rejected);
    }
    if parsed.contours.iter().flatten().any(|s| {
        !matches!(
            s,
            geometry::Segment::Line { .. } | geometry::Segment::Quad { .. }
        )
    }) {
        reject("cubic-curve-present");
        return fail("cubic-curve-present", &rejected);
    }
    let no = parsed.oncurve.len();
    let points: Vec<[f64; 2]> = parsed
        .oncurve
        .iter()
        .chain(parsed.offcurve.iter())
        .copied()
        .collect();
    let mut depths_tried = Vec::new();
    let mut chosen: Option<usize> = None;
    for depth in DEPTHS {
        depths_tried.push(depth);
        match curves::certify_parsed(&parsed, depth) {
            Ok(()) => {
                chosen = Some(depth);
                break;
            }
            Err(reason) => reject(reason),
        }
    }
    let Some(depth) = chosen else {
        reject("uncertified-substitution");
        return fail("uncertified-substitution", &rejected);
    };
    let (edges, loops) = substitute(&parsed, depth);
    let mut eps_global = 0.0f64;
    for contour in &parsed.contours {
        for seg in contour {
            if let geometry::Segment::Quad { c, a, b } = *seg {
                let ctrls = [parsed.oncurve[a], parsed.offcurve[c], parsed.oncurve[b]];
                let lifted = [lift(&ctrls[0]), lift(&ctrls[1]), lift(&ctrls[2])];
                if lifted.iter().any(Option::is_none) {
                    reject("malformed-commands");
                    return fail("malformed-commands", &rejected);
                }
                let rats = [
                    lifted[0].clone().unwrap(),
                    lifted[1].clone().unwrap(),
                    lifted[2].clone().unwrap(),
                ];
                for piece in piece_chains(&rats, depth) {
                    eps_global = eps_global.max(piece_eps_rat(&piece));
                }
            }
        }
    }
    let _ = points;
    let mut by_seg: HashMap<[usize; 3], Vec<usize>> = HashMap::new();
    for (e, edge) in edges.iter().enumerate() {
        if let Some((ctrl, _, _)) = edge.prov {
            by_seg.entry(ctrl).or_default().push(e);
        }
    }
    let mut boxes: HashMap<[usize; 3], (f64, f64, f64, f64)> = HashMap::new();
    for (ctrl, list) in &by_seg {
        let mut bb = (
            f64::INFINITY,
            f64::INFINITY,
            f64::NEG_INFINITY,
            f64::NEG_INFINITY,
        );
        for &e in list {
            for p in [edges[e].p0, edges[e].p1] {
                bb.0 = bb.0.min(p[0]);
                bb.1 = bb.1.min(p[1]);
                bb.2 = bb.2.max(p[0]);
                bb.3 = bb.3.max(p[1]);
            }
        }
        boxes.insert(*ctrl, bb);
    }
    let cap = if size_px.is_finite() && size_px > 0.0 {
        size_px / BOX_DIVISOR
    } else {
        f64::INFINITY
    };
    let mut keys: Vec<[usize; 3]> = by_seg.keys().copied().collect();
    keys.sort_by_key(|ctrl| {
        for (ci, contour) in parsed.contours.iter().enumerate() {
            for (si, seg) in contour.iter().enumerate() {
                if let geometry::Segment::Quad { c, a, b } = *seg {
                    if [a, no + c, b] == *ctrl {
                        return (ci, si);
                    }
                }
            }
        }
        (usize::MAX, usize::MAX)
    });
    // Invariant per-edge competitors and tags prepared once per source
    // geometry (Hobby section 3.2 setup reused across pair attempts).
    let competitors = intervals::CompetitorSet::new(intervals::tagged_borders(
        &edges.iter().map(|e| [e.p0, e.p1]).collect::<Vec<_>>(),
    ));
    // Source primitives for the exact contact certificates; they depend
    // only on the parsed outline, not on the candidate pair.
    let prims: Vec<Prim> = parsed
        .contours
        .iter()
        .flat_map(|c| c.iter())
        .filter_map(|seg| match *seg {
            geometry::Segment::Line { a, b } => {
                Some(Prim::Seg(vec![parsed.oncurve[a], parsed.oncurve[b]], false))
            }
            geometry::Segment::Quad { c, a, b } => Some(Prim::Seg(
                vec![parsed.oncurve[a], parsed.offcurve[c], parsed.oncurve[b]],
                true,
            )),
            // Unreachable: recognition rejects cubics up front.
            geometry::Segment::Cubic { .. } => None,
        })
        .collect();
    let mut pairs = Vec::new();
    let mut candidates = 0usize;
    for i in 0..keys.len() {
        for j in (i + 1)..keys.len() {
            let (ka, kb) = (keys[i], keys[j]);
            if box_gap(boxes[&ka], boxes[&kb]) > cap {
                reject("work-bound-skip");
                continue;
            }
            candidates += 1;
            let mut best: Option<(f64, f64, usize, usize, f64, intervals::PairSetup)> = None;
            for &ea in &by_seg[&ka] {
                let seg_a = [edges[ea].p0, edges[ea].p1];
                for &eb in &by_seg[&kb] {
                    let seg_b = [edges[eb].p0, edges[eb].p1];
                    // Same corridor/frame checks as the direct path; a
                    // failed setup rejects the pair before any competitor
                    // is normalized or compared.
                    let Ok(setup) = intervals::prepare(seg_a, seg_b) else {
                        continue;
                    };
                    // A returned interval cannot exceed this pair's
                    // conservatively rounded full-domain span. Prune only
                    // strict losers (Boyd/Mattingley bound-based pruning;
                    // see PairSetup::span_upper_bound), keeping order,
                    // ties and uncertain bounds on the existing path.
                    if best.as_ref().is_some_and(|(lo, hi, ..)| {
                        setup
                            .span_upper_bound()
                            .is_some_and(|bound| bound < hi - lo)
                    }) {
                        continue;
                    }
                    let dom = competitors.dominance_for(&setup, ea, eb, Some(&loops));
                    if dom.status != "ok" || dom.intervals.is_empty() {
                        continue;
                    }
                    let span = dom.intervals.iter().max_by(|x, y| {
                        (x.hi - x.lo)
                            .partial_cmp(&(y.hi - y.lo))
                            .unwrap_or(std::cmp::Ordering::Equal)
                    });
                    let Some(span) = span else { continue };
                    let width = (span.hi - span.lo) * dom.speed.unwrap_or(0.0);
                    let longer = best
                        .as_ref()
                        .map_or(true, |(lo, hi, ..)| span.hi - span.lo > hi - lo);
                    if longer {
                        best = Some((span.lo, span.hi, ea, eb, width, setup));
                    }
                }
            }
            let Some((lo, hi, ea, eb, arc, setup)) = best else {
                reject("no-interval");
                continue;
            };
            let mid = (lo + hi) / 2.0;
            let out = competitors.contact_for(&setup, mid, ea, eb, Some(&loops));
            let Some(hit) = out.hit else {
                reject("contact-failed");
                continue;
            };
            let (Some((ta_ctrl, ta0, ta1)), Some((tb_ctrl, tb0, tb1))) =
                (edges[ea].prov, edges[eb].prov)
            else {
                reject("contact-failed");
                continue;
            };
            let _ = (ta_ctrl, tb_ctrl);
            let ta = ta0 + hit.sa * (ta1 - ta0);
            let tb = tb0 + hit.sb * (tb1 - tb0);
            if !(0.0 <= ta && ta <= 1.0 && 0.0 <= tb && tb <= 1.0) {
                reject("contact-failed");
                continue;
            }
            let fa = [
                parsed.oncurve[ka[0]],
                parsed.offcurve[ka[1] - no],
                parsed.oncurve[ka[2]],
            ];
            let fb = [
                parsed.oncurve[kb[0]],
                parsed.offcurve[kb[1] - no],
                parsed.oncurve[kb[2]],
            ];
            let w_poly = hit.width;
            let chord = [hit.qa[0] - hit.qb[0], hit.qa[1] - hit.qb[1]];
            let dist = chord[0].hypot(chord[1]);
            if !(dist > 0.0) {
                reject("coincident");
                continue;
            }
            let shell = 2.0 * eps_global;
            let qa = eval_quad(&fa, ta);
            let qb = eval_quad(&fb, tb);
            let ra = [(qa[0] - hit.center[0]), (qa[1] - hit.center[1])];
            let rb = [(qb[0] - hit.center[0]), (qb[1] - hit.center[1])];
            let ra_len = ra[0].hypot(ra[1]);
            let rb_len = rb[0].hypot(rb[1]);
            if !((ra_len - w_poly / 2.0).abs() <= shell && (rb_len - w_poly / 2.0).abs() <= shell) {
                reject("approx-diverged");
                continue;
            }
            if !(w_poly / 2.0 > shell) {
                reject("approx-too-coarse");
                continue;
            }
            if !(arc > 0.0) {
                reject("degenerate-arc");
                continue;
            }
            let own_a = [fa[0], fa[1], fa[2]];
            let own_b = [fb[0], fb[1], fb[2]];
            // Exact source-contact certificate (prototype `_true_disk_clear`
            // with `(Fraction(w)/2 ± Fraction(shell))**2`): the squared
            // radius stays rational, never a rounded float, and the
            // Bernstein nonneg certificate allows exact tangency. This is
            // distinct from the bbox station gate in `clearance_ok`, which
            // keeps the conservative `disk_clear`.
            let rshrink2 = contact_r2(w_poly, shell, false);
            let mut bad: Option<&str> = None;
            for prim in &prims {
                let (ctrls, is_curve) = match prim {
                    Prim::Seg(c, q) => (c.as_slice(), *q),
                };
                let ok = rshrink2
                    .as_ref()
                    .map_or(false, |r2| curves::source_disk_clear(hit.center, r2, ctrls));
                if !ok {
                    bad = Some(if is_curve {
                        "curve-contact"
                    } else {
                        "line-contact"
                    });
                    break;
                }
            }
            if let Some(reason) = bad {
                reject(reason);
                continue;
            }
            let rmargin2 = contact_r2(w_poly, shell, true);
            let mut tight = false;
            for prim in &prims {
                let (ctrls, _) = match prim {
                    Prim::Seg(c, q) => (c.as_slice(), *q),
                };
                if ctrls.len() == 3
                    && ((ctrls[0] == own_a[0] && ctrls[1] == own_a[1] && ctrls[2] == own_a[2])
                        || (ctrls[0] == own_b[0] && ctrls[1] == own_b[1] && ctrls[2] == own_b[2]))
                {
                    continue;
                }
                let ok = rmargin2
                    .as_ref()
                    .map_or(false, |r2| curves::source_disk_clear(hit.center, r2, ctrls));
                if !ok {
                    tight = true;
                    break;
                }
            }
            if tight {
                reject("third-boundary-tight");
                continue;
            }
            let normal = [chord[0] / dist, chord[1] / dist];
            pairs.push(CurvePair {
                a_ctrl: ka,
                b_ctrl: kb,
                a_t: ta,
                b_t: tb,
                medial: hit.center,
                normal,
                width_2r: w_poly,
                radii: [ra_len, rb_len],
                approx_bound: 2.0 * shell,
                arc,
                shape_ctrl: vec![ka, kb],
            });
        }
    }
    (
        pairs,
        serde_json::json!({
            "candidates": candidates,
            "rejected": rejected,
            "depths_tried": depths_tried,
            "depth": depth,
            "eps_global": eps_global,
            "poly_edges": edges.iter().filter(|e| e.prov.is_some()).count(),
        }),
    )
}

enum Prim {
    Seg(Vec<[f64; 2]>, bool),
}

fn to_seg_ref(seg: &geometry::Segment, no: usize) -> Option<SegRef> {
    match *seg {
        geometry::Segment::Line { a, b } => Some(SegRef::Line { a, b }),
        geometry::Segment::Quad { c, a, b } => Some(SegRef::Quad { off: no + c, a, b }),
        geometry::Segment::Cubic { .. } => None,
    }
}

/// Duplicate-endpoint alias pairs from closure encoding.
///
/// The parser materializes a closing line when the last endpoint index
/// differs from the first; when that edge is zero-length its start vertex
/// duplicates the contour start coordinates. That alias is an encoding
/// artifact, not zero-tangent geometry.
pub(super) fn weld_map(parsed: &geometry::Parsed) -> HashMap<usize, usize> {
    let mut weld = HashMap::new();
    for contour in &parsed.contours {
        if contour.is_empty() {
            continue;
        }
        let first = match contour[0] {
            geometry::Segment::Line { a, .. } => a,
            geometry::Segment::Quad { a, .. } => a,
            geometry::Segment::Cubic { .. } => continue,
        };
        let last = &contour[contour.len() - 1];
        if let geometry::Segment::Line { a, b } = *last {
            let (_, end) = (a, b);
            if end == first && parsed.oncurve[a] == parsed.oncurve[first] && a != first {
                weld.insert(a, first);
            }
        }
    }
    weld
}

/// Joint legs in exact arithmetic; smooth needs cross 0, forward dot.
///
/// The predecessor wraps only on geometrically closed contours; open
/// ends carry no joint entry. Zero-length closure aliases are filtered
/// from logical joins; genuine internal zero legs stay classified.
pub(super) fn joints(parsed: &geometry::Parsed) -> HashMap<usize, Vec<JointOcc>> {
    let mut out: HashMap<usize, Vec<JointOcc>> = HashMap::new();
    for contour in &parsed.contours {
        let mut refs: Vec<SegRef> = Vec::new();
        for seg in contour {
            if let Some(r) = to_seg_ref(seg, parsed.oncurve.len()) {
                refs.push(r);
            }
        }
        if refs.is_empty() {
            continue;
        }
        let first_start = refs[0].start();
        let last_end = match refs[refs.len() - 1] {
            SegRef::Line { b, .. } => b,
            SegRef::Quad { b, .. } => b,
        };
        let closed = last_end == first_start;
        let mut logical = refs.clone();
        if closed {
            if let SegRef::Line { a, b } = refs[refs.len() - 1] {
                if parsed.oncurve[a] == parsed.oncurve[b] && b == first_start {
                    logical.pop();
                }
            }
        }
        if logical.is_empty() {
            continue;
        }
        for k in 0..logical.len() {
            if k == 0 && !closed {
                continue;
            }
            let prev = logical[(k + logical.len() - 1) % logical.len()];
            let seg = logical[k];
            let j = seg.start();
            let j_pt = match (lift(&parsed.oncurve[j]), true) {
                (Some(p), _) => p,
                _ => continue,
            };
            let leg = |s: SegRef, at_joint: bool| -> Option<Rat> {
                let f = match (s, at_joint) {
                    (SegRef::Quad { off, .. }, _) => {
                        let no = parsed.oncurve.len();
                        if off >= no {
                            lift(&parsed.offcurve[off - no])?
                        } else {
                            lift(&parsed.oncurve[off])?
                        }
                    }
                    (SegRef::Line { b, .. }, true) => lift(&parsed.oncurve[b])?,
                    (SegRef::Line { a, .. }, false) => lift(&parsed.oncurve[a])?,
                };
                Some(f)
            };
            let (Some(fin_pt), Some(fout_pt)) = (leg(prev, false), leg(seg, true)) else {
                continue;
            };
            let (lin, lout) = (
                (&j_pt.0 - &fin_pt.0, &j_pt.1 - &fin_pt.1),
                (&fout_pt.0 - &j_pt.0, &fout_pt.1 - &j_pt.1),
            );
            let zero = |l: &Rat| l.0.is_zero() && l.1.is_zero();
            let degenerate = zero(&lin) || zero(&lout);
            let smooth = !degenerate
                && cross_rat(&(BigRational::zero(), BigRational::zero()), &lin, &lout).is_zero()
                && (&lin.0 * &lout.0 + &lin.1 * &lout.1).is_positive();
            out.entry(j).or_default().push(JointOcc {
                prev,
                seg,
                smooth,
                degenerate,
            });
        }
    }
    out
}

/// Degenerate-joint vertex triples `[joint, leg-prev, leg-seg]`, mirroring the
/// frozen prototype's `degenerate_verts = [j, iv, ov]`: the joint index is
/// the map key, never a hardcoded vertex. Callers freeze and guard exactly
/// these vertices so unrelated motion (e.g. at vertex 0) never trips the
/// degenerate-joint gate.
fn degenerate_triples(map: &HashMap<usize, Vec<JointOcc>>) -> Vec<[usize; 3]> {
    let mut degenerate: Vec<[usize; 3]> = Vec::new();
    for (j, occs) in map {
        for occ in occs {
            if occ.degenerate {
                degenerate.push([*j, leg_vertex(occ.prev, false), leg_vertex(occ.seg, true)]);
            }
        }
    }
    degenerate
}

/// Far endpoint or off-curve control adjacent to the joint, global index.
fn leg_vertex(s: SegRef, at_joint_out: bool) -> usize {
    match (s, at_joint_out) {
        (SegRef::Line { b, .. }, true) => b,
        (SegRef::Line { a, .. }, false) => a,
        (SegRef::Quad { off, .. }, _) => off,
    }
}

/// Linearized joint-cross row with frozen upstream coefficients.
///
/// cross(J-I, O-J) linearized at the upstream fit keeps every residual
/// linear in control points. Smooth joints target zero shared-tangent
/// cross, permitting common rotation; other joints target the upstream
/// defect, preserving it instead of smoothing.
pub(super) fn g1_row(
    upstream: &[[f64; 2]],
    j: usize,
    prev: SegRef,
    seg: SegRef,
    size_px: f64,
    smooth: bool,
) -> Option<(Vec<f64>, f64)> {
    let pt = |v: usize| upstream[v];
    let j_pt = pt(j);
    let i_pt = pt(leg_vertex(prev, false));
    let o_pt = pt(leg_vertex(seg, true));
    let li = [j_pt[0] - i_pt[0], j_pt[1] - i_pt[1]];
    let lo = [o_pt[0] - j_pt[0], o_pt[1] - j_pt[1]];
    let ni = li[0].hypot(li[1]);
    let no_ = lo[0].hypot(lo[1]);
    let cross_up = li[0] * lo[1] - li[1] * lo[0];
    if !(ni > 0.0 && no_ > 0.0) {
        return None;
    }
    let mut row = vec![0.0; 2 * upstream.len()];
    let dj = [lo[1] + li[1], -(li[0] + lo[0])];
    let di = [-lo[1], lo[0]];
    let do_ = [-li[1], li[0]];
    let iv = leg_vertex(prev, false);
    let ov = leg_vertex(seg, true);
    row[2 * j] = dj[0];
    row[2 * j + 1] = dj[1];
    row[2 * iv] = di[0];
    row[2 * iv + 1] = di[1];
    row[2 * ov] = do_[0];
    row[2 * ov + 1] = do_[1];
    let arc = (ni + no_) / 2.0;
    let scale = (25.0 / size_px * arc).sqrt() / (ni * no_);
    for x in row.iter_mut() {
        *x *= scale;
    }
    let constant = if smooth { cross_up } else { 0.0 } * scale;
    Some((row, constant))
}

/// 26.6 rounding bound on joint-cross perturbation.
///
/// Only moved coordinates err, at most 1/128 per axis; unmoved legs
/// contribute zero. The bilinear cross pairs each leg's error with the
/// OTHER leg (prototype `ein_x * by + ein_y * bx + eout_x * ay +
/// eout_y * ax`), plus the second-order product.
pub(super) fn quant_cross_bound(
    leg_in: [f64; 2],
    leg_out: [f64; 2],
    moved: [(bool, bool); 3],
) -> f64 {
    let err = |m: (bool, bool)| {
        [
            if m.0 { ROUND_HALF } else { 0.0 },
            if m.1 { ROUND_HALF } else { 0.0 },
        ]
    };
    let (ei, ej, eo) = (err(moved[0]), err(moved[1]), err(moved[2]));
    let ein = [ei[0] + ej[0], ei[1] + ej[1]];
    let eout = [ej[0] + eo[0], ej[1] + eo[1]];
    ein[0] * leg_out[1].abs()
        + ein[1] * leg_out[0].abs()
        + eout[0] * leg_in[1].abs()
        + eout[1] * leg_in[0].abs()
        + ein[0] * eout[1]
        + ein[1] * eout[0]
}

/// Clip the peak Euclidean control displacement to the movement bound.
///
/// Both free axes of one control count together; a diagonal move peaks
/// at its hypotenuse, not its largest coordinate.
fn scale_to_bound(sol: &[f64], cols: &[(usize, usize)], bound: f64) -> (Vec<f64>, f64) {
    let mut acc: HashMap<usize, f64> = HashMap::new();
    for ((v, _), d) in cols.iter().zip(sol.iter()) {
        *acc.entry(*v).or_insert(0.0) += d * d;
    }
    let peak = acc.values().cloned().fold(0.0, f64::max).sqrt();
    if peak > bound {
        (sol.iter().map(|d| d * (bound / peak)).collect(), bound)
    } else {
        (sol.to_vec(), peak)
    }
}

/// Joint cross and legs at one coordinate set.
///
/// cross(J-I, O-J) with the incoming and outgoing legs at global control
/// indices.
pub(super) fn cross_of(
    coords: &[[f64; 2]],
    j: usize,
    iv: usize,
    ov: usize,
) -> (f64, [f64; 2], [f64; 2]) {
    let (j_pt, i_pt, o_pt) = (coords[j], coords[iv], coords[ov]);
    let li = [j_pt[0] - i_pt[0], j_pt[1] - i_pt[1]];
    let lo = [o_pt[0] - j_pt[0], o_pt[1] - j_pt[1]];
    (li[0] * lo[1] - li[1] * lo[0], li, lo)
}

fn cross_of_seg(
    coords: &[[f64; 2]],
    j: usize,
    prev: SegRef,
    seg: SegRef,
) -> (f64, [f64; 2], [f64; 2]) {
    cross_of(coords, j, leg_vertex(prev, false), leg_vertex(seg, true))
}

/// Unit chord direction between the true pair contacts on the source.
pub(super) fn pair_normal(
    source: &[FittedCommand],
    a_ctrl: [usize; 3],
    a_t: f64,
    b_ctrl: [usize; 3],
    b_t: f64,
) -> Option<[f64; 2]> {
    let parsed = geometry::parse_commands(source).ok()?;
    let no = parsed.oncurve.len();
    let total = no + parsed.offcurve.len();
    if [a_ctrl, b_ctrl]
        .iter()
        .flat_map(|c| c.iter())
        .any(|v| *v >= total)
    {
        return None;
    }
    if a_ctrl[1] < no || b_ctrl[1] < no {
        return None;
    }
    let fa = [
        parsed.oncurve[a_ctrl[0]],
        parsed.offcurve[a_ctrl[1] - no],
        parsed.oncurve[a_ctrl[2]],
    ];
    let fb = [
        parsed.oncurve[b_ctrl[0]],
        parsed.offcurve[b_ctrl[1] - no],
        parsed.oncurve[b_ctrl[2]],
    ];
    let qa = eval_quad(&fa, a_t);
    let qb = eval_quad(&fb, b_t);
    let d = [qb[0] - qa[0], qb[1] - qa[1]];
    let n = d[0].hypot(d[1]);
    if n > 0.0 {
        Some([d[0] / n, d[1] / n])
    } else {
        None
    }
}

/// Entire-interval tangent/curvature certificate for quadratics.
///
/// cross(d1, d2) is constant over the interval, so the control polygon
/// certifies curvature sign; strict positivity of all four leg dot
/// products keeps every candidate tangent within 90 degrees of every
/// source tangent. No sampling, no angular threshold.
pub(super) fn quad_interval_ok(
    src: &[[f64; 2]; 3],
    cand: &[[f64; 2]; 3],
) -> Result<(), &'static str> {
    let legs = |c: &[[f64; 2]; 3]| {
        (
            [c[1][0] - c[0][0], c[1][1] - c[0][1]],
            [c[2][0] - c[1][0], c[2][1] - c[1][1]],
        )
    };
    let (us, vs) = legs(src);
    let (uc, vc) = legs(cand);
    if !([us, vs, uc, vc].iter().all(|l| l[0].hypot(l[1]) > 0.0)) {
        return Err("degenerate-leg");
    }
    let (ss, cs) = (us[0] * vs[1] - us[1] * vs[0], uc[0] * vc[1] - uc[1] * vc[0]);
    if ss == 0.0 || cs == 0.0 {
        return Err("degenerate-curvature");
    }
    if ss.signum() != cs.signum() {
        return Err("curvature-sign");
    }
    for (u, v) in [(uc, us), (vc, vs), (uc, vs), (vc, us)] {
        if u[0] * v[0] + u[1] * v[1] <= 0.0 {
            return Err("tangent-reversed");
        }
    }
    Ok(())
}

#[derive(Clone, Copy, PartialEq)]
enum RowKind {
    Shape,
    Joint,
    Ink,
}

fn projected_row(basis: &[f64], dir: [f64; 2], other: Option<&[f64]>, n: usize) -> Vec<f64> {
    let mut row = vec![0.0; 2 * n];
    for (k, w) in basis.iter().enumerate() {
        row[2 * k] = w * dir[0];
        row[2 * k + 1] = w * dir[1];
    }
    if let Some(o) = other {
        for (k, w) in o.iter().enumerate() {
            row[2 * k] -= w * dir[0];
            row[2 * k + 1] -= w * dir[1];
        }
    }
    row
}

/// Quadratic form of the (31)-(33) + (2),(3) construction.
///
/// Mirrors the shared cubic algebra with quadratic Bernstein weights
/// and derivative weights; same group feeds the same upstream-gap
/// constant substitution.
fn add_quad_shape(
    rows: &mut Vec<(RowKind, Vec<f64>, f64)>,
    base: &[[f64; 2]],
    ctrl: [usize; 3],
    height: f64,
) {
    let c: [[f64; 2]; 3] = [base[ctrl[0]], base[ctrl[1]], base[ctrl[2]]];
    for j in 0..CURVE_INTERVALS {
        let t = (j as f64 + 0.5) / CURVE_INTERVALS as f64;
        let mt = 1.0 - t;
        let basis = [(mt) * mt, 2.0 * t * mt, t * t];
        let deriv_w = [-2.0 * mt, 2.0 * mt - 2.0 * t, 2.0 * t];
        let deriv = [
            deriv_w[0] * c[0][0] + deriv_w[1] * c[1][0] + deriv_w[2] * c[2][0],
            deriv_w[0] * c[0][1] + deriv_w[1] * c[1][1] + deriv_w[2] * c[2][1],
        ];
        let speed = deriv[0].hypot(deriv[1]);
        if !(speed > 0.0) {
            continue;
        }
        let normal = [deriv[1] / speed, -deriv[0] / speed];
        let brow = basis_row(
            &[
                (ctrl[0], basis[0]),
                (ctrl[1], basis[1]),
                (ctrl[2], basis[2]),
            ],
            base.len(),
        );
        let pos: Vec<f64> = projected_row(&brow, normal, None, base.len())
            .iter()
            .map(|x| x * (1000.0 / height.powi(3) * speed / CURVE_INTERVALS as f64).sqrt())
            .collect();
        rows.push((RowKind::Shape, pos, 0.0));
        let drow = basis_row(
            &[
                (ctrl[0], deriv_w[0]),
                (ctrl[1], deriv_w[1]),
                (ctrl[2], deriv_w[2]),
            ],
            base.len(),
        );
        let tangent = [deriv[0] / speed, deriv[1] / speed];
        let factor = (25.0 / height * speed / CURVE_INTERVALS as f64).sqrt() / speed;
        let stretch: Vec<f64> = projected_row(&drow, tangent, None, base.len())
            .iter()
            .map(|x| x * factor)
            .collect();
        let bend: Vec<f64> = projected_row(&drow, normal, None, base.len())
            .iter()
            .map(|x| x * factor)
            .collect();
        rows.push((RowKind::Shape, stretch, 0.0));
        rows.push((RowKind::Shape, bend, 0.0));
    }
}

/// Hobby (1)-(3), with directions/lengths from input geometry.
fn add_edge(
    rows: &mut Vec<(RowKind, Vec<f64>, f64)>,
    base: &[[f64; 2]],
    i: usize,
    j: usize,
    height: f64,
) -> Result<(), ()> {
    let (pa, pb) = (base[i], base[j]);
    let delta = [pb[0] - pa[0], pb[1] - pa[1]];
    let length = delta[0].hypot(delta[1]);
    if !(length > 0.0) {
        return Err(());
    }
    let tangent = [delta[0] / length, delta[1] / length];
    let normal = [-tangent[1], tangent[0]];
    let n = base.len();
    let mut bi = vec![0.0; n];
    bi[i] = 1.0;
    let mut bj = vec![0.0; n];
    bj[j] = 1.0;
    let ri = projected_row(&bi, normal, None, n);
    let rj = projected_row(&bj, normal, None, n);
    let alpha1 = 1000.0 / height.powi(3);
    let sum: Vec<f64> = ri
        .iter()
        .zip(rj.iter())
        .map(|(x, y)| (x + y) * (alpha1 * length / 4.0).sqrt())
        .collect();
    let diff: Vec<f64> = rj
        .iter()
        .zip(ri.iter())
        .map(|(x, y)| (x - y) * (alpha1 * length / 12.0).sqrt())
        .collect();
    rows.push((RowKind::Shape, sum, 0.0));
    rows.push((RowKind::Shape, diff, 0.0));
    let scale = (25.0 * length / height).sqrt() / length;
    let stretch: Vec<f64> = projected_row(&bj, tangent, Some(&bi), n)
        .iter()
        .map(|x| x * scale)
        .collect();
    let bend: Vec<f64> = rj
        .iter()
        .zip(ri.iter())
        .map(|(x, y)| (x - y) * scale)
        .collect();
    rows.push((RowKind::Shape, stretch, 0.0));
    rows.push((RowKind::Shape, bend, 0.0));
    Ok(())
}

/// Pair error row: Hobby (4),(5) with the true mapped medial disk.
fn pair_error(base: &[[f64; 2]], pair: &CurvePair) -> Option<(Vec<f64>, [f64; 2], [f64; 2])> {
    let n = base.len();
    let wa = {
        let t = pair.a_t;
        let mt = 1.0 - t;
        [mt * mt, 2.0 * t * mt, t * t]
    };
    let wb = {
        let t = pair.b_t;
        let mt = 1.0 - t;
        [mt * mt, 2.0 * t * mt, t * t]
    };
    let ba = basis_row(
        &[
            (pair.a_ctrl[0], wa[0]),
            (pair.a_ctrl[1], wa[1]),
            (pair.a_ctrl[2], wa[2]),
        ],
        n,
    );
    let bb = basis_row(
        &[
            (pair.b_ctrl[0], wb[0]),
            (pair.b_ctrl[1], wb[1]),
            (pair.b_ctrl[2], wb[2]),
        ],
        n,
    );
    let fa = [
        base[pair.a_ctrl[0]],
        base[pair.a_ctrl[1]],
        base[pair.a_ctrl[2]],
    ];
    let fb = [
        base[pair.b_ctrl[0]],
        base[pair.b_ctrl[1]],
        base[pair.b_ctrl[2]],
    ];
    if !(pair.width_2r > 0.0) {
        return None;
    }
    let mut normal = pair.normal;
    let nn = normal[0].hypot(normal[1]);
    if !(nn > 0.0) {
        return None;
    }
    normal = [normal[0] / nn, normal[1] / nn];
    let tangent = [-normal[1], normal[0]];
    let qa = eval_quad(&fa, pair.a_t);
    let qb = eval_quad(&fb, pair.b_t);
    let shell = pair.approx_bound / 2.0;
    let ra = (qa[0] - pair.medial[0]).hypot(qa[1] - pair.medial[1]);
    let rb = (qb[0] - pair.medial[0]).hypot(qb[1] - pair.medial[1]);
    if !((ra - pair.width_2r / 2.0).abs() <= shell && (rb - pair.width_2r / 2.0).abs() <= shell) {
        return None;
    }
    let mut error = projected_row(&ba, normal, Some(&bb), n);
    for x in error.iter_mut() {
        *x /= -pair.width_2r;
    }
    Some((error, normal, tangent))
}

/// Exact depth-4 subdivision hulls of one candidate curve with per-piece
/// boxes, built once per clearance call and reused across every pair.
/// Dyadic subdivision points are convex combinations of the controls, so
/// every piece hull stays inside the control box.
struct CachedCurve {
    hulls: Vec<Vec<Rat>>,
    boxes: Vec<(BigRational, BigRational, BigRational, BigRational)>,
    /// Interval bounds prepared once per immutable piece hull alongside
    /// the exact hulls; the cache is call-local to one candidate, so a
    /// fresh candidate always prepares fresh bounds.
    bounds: Vec<Option<Vec<filtered::PtI>>>,
}

/// Subdivision hulls of one curve, or `None` for non-finite controls
/// (matching the old empty-hull fail-closed verdict).
fn cached_curve(controls: &[[f64; 2]; 3]) -> Option<CachedCurve> {
    let rats: Vec<Rat> = controls.iter().filter_map(lift).collect();
    if rats.len() != 3 {
        return None;
    }
    let hulls = piece_hulls(&rats, 4);
    let boxes = hulls.iter().map(|hull| rat_box(hull)).collect();
    let bounds = hulls
        .iter()
        .map(|hull| filtered::enclose_hull(hull))
        .collect();
    Some(CachedCurve {
        hulls,
        boxes,
        bounds,
    })
}

/// Filter-first strict separation reusing bounds prepared once per
/// immutable hull; the exact narrow phase runs unchanged.
fn disjoint_cached(
    hp: &[Rat],
    hpi: Option<&[filtered::PtI]>,
    hq: &[Rat],
    hqi: Option<&[filtered::PtI]>,
) -> bool {
    if let (Some(x), Some(y)) = (hpi, hqi) {
        if let (Some(bx), Some(by)) = (
            filtered::BoundHull::new(hp, x),
            filtered::BoundHull::new(hq, y),
        ) {
            if let Some(verdict) = filtered::polys_strictly_disjoint_h(&bx, &by) {
                return verdict;
            }
            return strictly_disjoint_exact(hp, hq);
        }
    }
    strictly_disjoint(hp, hq)
}

/// Filter-first shared-contact verdict reusing prepared bounds; the exact
/// narrow phase runs unchanged, including degenerate SAT semantics.
fn meet_cached(
    hp: &[Rat],
    hpi: Option<&[filtered::PtI]>,
    hq: &[Rat],
    hqi: Option<&[filtered::PtI]>,
    shared: &Rat,
) -> bool {
    if let (Some(x), Some(y)) = (hpi, hqi) {
        if let (Some(bx), Some(by)) = (
            filtered::BoundHull::new(hp, x),
            filtered::BoundHull::new(hq, y),
        ) {
            if let Some(v) = filtered::hulls_meet_only_at_h(&bx, &by, shared) {
                return v;
            }
            return curves::hulls_meet_only_at_exact(hp, hq, shared);
        }
    }
    hulls_meet_only_at(hp, hq, shared)
}

/// Float control box of one curve: (min_x, min_y, max_x, max_y).
fn control_box(controls: &[[f64; 2]; 3]) -> (f64, f64, f64, f64) {
    (
        controls.iter().map(|p| p[0]).fold(f64::INFINITY, f64::min),
        controls.iter().map(|p| p[1]).fold(f64::INFINITY, f64::min),
        controls
            .iter()
            .map(|p| p[0])
            .fold(f64::NEG_INFINITY, f64::max),
        controls
            .iter()
            .map(|p| p[1])
            .fold(f64::NEG_INFINITY, f64::max),
    )
}

/// Exact pair verdict over cached subdivision hulls.
///
/// The whole-curve box gate runs before any subdivision: piece hulls stay
/// inside the control boxes, so strict separation decides clearance exactly
/// as the per-piece gates below would. Finite inputs only; non-finite
/// controls fail closed through the cache lookup, as before.
fn hulls_ok(
    a_idx: [usize; 3],
    a: &[[f64; 2]; 3],
    b_idx: [usize; 3],
    b: &[[f64; 2]; 3],
    shared: Option<Rat>,
    cache: &mut HashMap<[usize; 3], Option<CachedCurve>>,
) -> bool {
    if a.iter().all(|p| p[0].is_finite() && p[1].is_finite())
        && b.iter().all(|p| p[0].is_finite() && p[1].is_finite())
        && boxes_separate(control_box(a), control_box(b))
    {
        return true;
    }
    cache.entry(a_idx).or_insert_with(|| cached_curve(a));
    if a_idx != b_idx {
        cache.entry(b_idx).or_insert_with(|| cached_curve(b));
    }
    let (Some(Some(ha)), Some(Some(hb))) = (cache.get(&a_idx), cache.get(&b_idx)) else {
        return false;
    };
    for ((hp, bp), bpi) in ha.hulls.iter().zip(ha.boxes.iter()).zip(ha.bounds.iter()) {
        for ((hq, bq), bqi) in hb.hulls.iter().zip(hb.boxes.iter()).zip(hb.bounds.iter()) {
            if boxes_separate_f(bp, bq) {
                continue;
            }
            if let Some(ref s) = shared {
                if meet_cached(hp, bpi.as_deref(), hq, bqi.as_deref(), s) {
                    continue;
                }
            }
            if !disjoint_cached(hp, bpi.as_deref(), hq, bqi.as_deref()) {
                return false;
            }
        }
    }
    true
}

/// Delivery clearance with subdivision certificates.
///
/// Station disks clear fixed primitives exactly; moved/fixed and
/// moved/moved hulls separate at depth 4 with incident-junction
/// exemption. Paired curves skip hull separation (their interval is
/// width-governed; the exact gate covers crossings), and swept lines
/// skip incident curves (folding there is blocked by the
/// tangent/curvature gate plus the topology gate). All exemptions are
/// recorded, none silent.
#[allow(clippy::too_many_arguments)]
pub(super) fn clearance_ok(
    pairs: &[CurvePair],
    cand: &[[f64; 2]],
    parsed: &geometry::Parsed,
    involved: &HashSet<usize>,
    upstream: &[[f64; 2]],
    paired: &HashSet<([usize; 3], [usize; 3])>,
) -> Result<(), String> {
    let no = parsed.oncurve.len();
    let _ = no;
    let ctrl_of = |idx: [usize; 3]| -> [[f64; 2]; 3] { [cand[idx[0]], cand[idx[1]], cand[idx[2]]] };
    let mut fixed_curves: Vec<([usize; 3], [[f64; 2]; 3])> = Vec::new();
    let mut moved_curves: Vec<([usize; 3], [[f64; 2]; 3])> = Vec::new();
    for contour in &parsed.contours {
        for seg in contour {
            if let geometry::Segment::Quad { c, a, b } = *seg {
                let idx = [a, no + c, b];
                let entry = (idx, ctrl_of(idx));
                if idx.iter().any(|v| involved.contains(v)) {
                    moved_curves.push(entry);
                } else {
                    fixed_curves.push(entry);
                }
            }
        }
    }
    let mut moved_lines: Vec<(usize, usize, [f64; 2], [f64; 2], [f64; 2], [f64; 2])> = Vec::new();
    let mut fixed_lines: Vec<([f64; 2], [f64; 2])> = Vec::new();
    for contour in &parsed.contours {
        for seg in contour {
            if let geometry::Segment::Line { a, b } = *seg {
                let old = (upstream[a], upstream[b]);
                let new = (cand[a], cand[b]);
                if old != new {
                    moved_lines.push((a, b, old.0, old.1, new.0, new.1));
                } else {
                    fixed_lines.push(old);
                }
            }
        }
    }
    for pair in pairs {
        let fa = ctrl_of(pair.a_ctrl);
        let fb = ctrl_of(pair.b_ctrl);
        let qa = eval_quad(&fa, pair.a_t);
        let qb = eval_quad(&fb, pair.b_t);
        let center = [(qa[0] + qb[0]) / 2.0, (qa[1] + qb[1]) / 2.0];
        let radius = (qb[0] - qa[0]).hypot(qb[1] - qa[1]) / 2.0;
        for (_, fix) in &fixed_curves {
            if !curves::disk_clear(center, radius, fix).0 {
                return Err("station-disk-curve".to_string());
            }
        }
        for seg in &fixed_lines {
            if !curves::disk_clear(center, radius, &[seg.0, seg.1]).0 {
                return Err("station-disk-line".to_string());
            }
        }
    }
    let live: Vec<([usize; 3], [[f64; 2]; 3])> = moved_curves
        .iter()
        .filter(|(idx, _)| idx.iter().any(|v| cand[*v] != upstream[*v]))
        .cloned()
        .collect();
    let shared_point = |a: &[[f64; 2]; 3], b: &[[f64; 2]; 3]| -> Option<Rat> {
        for p in [a[0], a[2]] {
            for q in [b[0], b[2]] {
                if p == q {
                    return lift(&p);
                }
            }
        }
        None
    };
    // Subdivision hulls by curve identity, reused across every pair of this
    // call only; the candidate geometry is fixed while it lives.
    let mut hull_cache: HashMap<[usize; 3], Option<CachedCurve>> = HashMap::new();
    for (idx, new) in &live {
        for (fix_idx, fix) in &fixed_curves {
            let shared = shared_point(new, fix);
            if !hulls_ok(*idx, new, *fix_idx, fix, shared, &mut hull_cache) {
                return Err("moved-fixed-hull".to_string());
            }
        }
        for (other_idx, other) in &live {
            if other_idx == idx {
                continue;
            }
            let key = if idx < other_idx {
                (*idx, *other_idx)
            } else {
                (*other_idx, *idx)
            };
            if paired.contains(&key) {
                continue;
            }
            let shared = shared_point(new, other);
            if !hulls_ok(*idx, new, *other_idx, other, shared, &mut hull_cache) {
                return Err("moved-moved-hull".to_string());
            }
        }
    }
    if !moved_lines.is_empty() && !fixed_curves.is_empty() {
        let olds: Vec<((f64, f64), (f64, f64))> = moved_lines
            .iter()
            .map(|(_, _, a, b, _, _)| ((a[0], a[1]), (b[0], b[1])))
            .collect();
        let news: Vec<((f64, f64), (f64, f64))> = moved_lines
            .iter()
            .map(|(_, _, _, _, c, d)| ((c[0], c[1]), (d[0], d[1])))
            .collect();
        let curve_pts: Vec<Vec<[f64; 2]>> = fixed_curves
            .iter()
            .map(|(_, c)| vec![c[0], c[1], c[2]])
            .collect();
        if !curves::movement_clear(&olds, &news, &curve_pts).0 {
            return Err("swept-fixed-curve".to_string());
        }
    }
    for (i, j, a0, b0, a1, b1) in &moved_lines {
        let (Some(r0), Some(r1), Some(r2), Some(r3)) = (lift(a0), lift(b0), lift(a1), lift(b1))
        else {
            return Err("swept-moved-curve".to_string());
        };
        let swept = convex_hull(&[r0, r1, r2, r3]);
        // Prepared once per immutable sweep, reused across every hull.
        let swept_iv = filtered::enclose_hull(&swept);
        for (c_idx, c_new) in &live {
            if c_idx.contains(i) || c_idx.contains(j) {
                continue;
            }
            let cached = hull_cache
                .entry(*c_idx)
                .or_insert_with(|| cached_curve(c_new));
            let Some(cached) = cached else {
                return Err("swept-moved-curve".to_string());
            };
            for (hull, bi) in cached.hulls.iter().zip(cached.bounds.iter()) {
                if !disjoint_cached(&swept, swept_iv.as_deref(), hull, bi.as_deref()) {
                    return Err("swept-moved-curve".to_string());
                }
            }
        }
    }
    Ok(())
}

fn boxes_separate(a: (f64, f64, f64, f64), b: (f64, f64, f64, f64)) -> bool {
    a.2 < b.0 || b.2 < a.0 || a.3 < b.1 || b.3 < a.1
}

/// Rebuild commands, preserving ops/order; float storage refreshes bits.
pub(super) fn emit(upstream: &[FittedCommand], cand: &[[f64; 2]], no: usize) -> Vec<FittedCommand> {
    let mut on_iter = cand.iter().take(no);
    let mut off_iter = cand.iter().skip(no);
    let mut out = Vec::with_capacity(upstream.len());
    for cmd in upstream {
        match *cmd {
            FittedCommand::MoveTo(..) | FittedCommand::LineTo(..) => {
                if let Some(pt) = on_iter.next() {
                    match cmd {
                        FittedCommand::MoveTo(..) => {
                            out.push(FittedCommand::MoveTo(pt[0] as f32, pt[1] as f32))
                        }
                        _ => out.push(FittedCommand::LineTo(pt[0] as f32, pt[1] as f32)),
                    }
                }
            }
            FittedCommand::QuadTo(..) => {
                if let (Some(c), Some(p)) = (off_iter.next(), on_iter.next()) {
                    out.push(FittedCommand::QuadTo(
                        c[0] as f32,
                        c[1] as f32,
                        p[0] as f32,
                        p[1] as f32,
                    ));
                }
            }
            FittedCommand::CurveTo(..) => {
                if let (Some(c1), Some(c2), Some(p)) =
                    (off_iter.next(), off_iter.next(), on_iter.next())
                {
                    out.push(FittedCommand::CurveTo(
                        c1[0] as f32,
                        c1[1] as f32,
                        c2[0] as f32,
                        c2[1] as f32,
                        p[0] as f32,
                        p[1] as f32,
                    ));
                }
            }
            FittedCommand::Close => out.push(FittedCommand::Close),
        }
    }
    out
}

fn qp_json(info: &QpInfo) -> serde_json::Value {
    serde_json::json!({
        "iterations": info.iterations,
        "equality_error": info.equality_error,
        "stationarity_error": info.stationarity_error,
        "inequality_slack": info.inequality_slack,
        "active": info.active,
    })
}

/// Assembled joint row with its occurrence.
struct JointRow {
    occ_prev: SegRef,
    occ_seg: SegRef,
    joint: usize,
    smooth: bool,
}

struct PairWork {
    error: Vec<f64>,
    tangent: [f64; 2],
    width: f64,
    err_gap: f64,
}

struct SolveCtx {
    rows: Vec<(RowKind, Vec<f64>, f64)>,
    pair_work: Vec<(PairWork, CurvePair)>,
    joint_rows: Vec<JointRow>,
    involved: Vec<usize>,
    cols: Vec<(usize, usize)>,
    bound: f64,
    hard: bool,
    base: Vec<[f64; 2]>,
    upstream: Vec<[f64; 2]>,
    no: usize,
}

#[allow(clippy::too_many_arguments)]
fn assemble(
    parsed: &geometry::Parsed,
    upstream: &[[f64; 2]],
    pairs: &[CurvePair],
    reference: &Reference,
    size_px: f64,
    owned: &[usize],
    frozen_in: &HashSet<usize>,
    hard: bool,
) -> Result<SolveCtx, String> {
    let no = parsed.oncurve.len();
    let base: Vec<[f64; 2]> = parsed
        .oncurve
        .iter()
        .chain(parsed.offcurve.iter())
        .copied()
        .collect();
    if upstream.len() != base.len() {
        return Err("no-correspondence".to_string());
    }
    let gaps: Vec<f64> = upstream
        .iter()
        .zip(base.iter())
        .flat_map(|(u, b)| [u[0] - b[0], u[1] - b[1]])
        .collect();
    let mut involved_set: HashSet<usize> = HashSet::new();
    for pair in pairs {
        for v in pair.a_ctrl.into_iter().chain(pair.b_ctrl.into_iter()) {
            if v >= base.len() {
                return Err("malformed-pairs".to_string());
            }
            involved_set.insert(v);
        }
    }
    let mut frozen: HashSet<usize> = frozen_in.clone();
    let map = joints(parsed);
    let mut joint_parts: Vec<(Vec<f64>, f64, JointRow)> = Vec::new();
    let mut order: Vec<usize> = map.keys().copied().collect();
    order.sort();
    for j in order {
        let Some(occs) = map.get(&j) else { continue };
        for occ in occs {
            let iv = leg_vertex(occ.prev, false);
            let ov = leg_vertex(occ.seg, true);
            if ![j, iv, ov].iter().any(|v| involved_set.contains(v)) {
                continue;
            }
            // An immutable attachment keeps the preferred polynomial even
            // when hinting collapsed one of its legs. No movable degree of
            // freedom reaches this joint, so it needs no deformation row.
            if [j, iv, ov].iter().all(|v| frozen.contains(v)) {
                continue;
            }
            if occ.degenerate {
                frozen.insert(j);
                frozen.insert(iv);
                frozen.insert(ov);
                involved_set.insert(j);
                involved_set.insert(iv);
                involved_set.insert(ov);
                continue;
            }
            let Some((row, constant)) = g1_row(upstream, j, occ.prev, occ.seg, size_px, occ.smooth)
            else {
                return Err("degenerate-leg".to_string());
            };
            joint_parts.push((
                row,
                constant,
                JointRow {
                    occ_prev: occ.prev,
                    occ_seg: occ.seg,
                    joint: j,
                    smooth: occ.smooth,
                },
            ));
            involved_set.insert(j);
            involved_set.insert(iv);
            involved_set.insert(ov);
        }
    }
    let mut rows: Vec<(RowKind, Vec<f64>, f64)> = Vec::new();
    let mut pair_ctrls: Vec<[usize; 3]> = Vec::new();
    for pair in pairs {
        for key in [&pair.a_ctrl, &pair.b_ctrl] {
            if !pair_ctrls.contains(key) {
                pair_ctrls.push(*key);
            }
        }
        for ctrl in &pair.shape_ctrl {
            if !pair_ctrls.contains(ctrl) {
                pair_ctrls.push(*ctrl);
            }
        }
    }
    for contour in &parsed.contours {
        for seg in contour {
            if let geometry::Segment::Quad { c, a, b } = *seg {
                let ctrl = [a, no + c, b];
                if ctrl.iter().any(|v| involved_set.contains(v)) && !pair_ctrls.contains(&ctrl) {
                    pair_ctrls.push(ctrl);
                }
            }
        }
    }
    for ctrl in &pair_ctrls {
        add_quad_shape(&mut rows, &base, *ctrl, size_px);
    }
    for contour in &parsed.contours {
        for seg in contour {
            if let geometry::Segment::Line { a, b } = *seg {
                if involved_set.contains(&a) || involved_set.contains(&b) {
                    let _ = add_edge(&mut rows, &base, a, b, size_px);
                }
            }
        }
    }
    let mut joint_rows: Vec<JointRow> = Vec::new();
    for (row, constant, jr) in joint_parts {
        joint_rows.push(jr);
        rows.push((RowKind::Joint, row, constant));
    }
    let mut pair_work = Vec::new();
    for pair in pairs {
        let Some((error, _, tangent)) = pair_error(&base, pair) else {
            return Err("malformed-pairs".to_string());
        };
        let err_gap: f64 = error.iter().zip(gaps.iter()).map(|(r, g)| r * g).sum();
        pair_work.push((
            PairWork {
                error,
                tangent,
                width: pair.width_2r,
                err_gap,
            },
            pair.clone(),
        ));
    }
    for (work, pair) in &pair_work {
        for anchor in &reference.anchors {
            let tangent = acute(work.tangent, anchor.tangent);
            let psi = width_weight(
                work.width,
                anchor.source_width,
                tangent,
                anchor.tangent,
                size_px,
            );
            let w = pair.arc * anchor.length * psi;
            if !(w > 0.0) {
                continue;
            }
            let s = w.sqrt();
            rows.push((
                RowKind::Ink,
                work.error.iter().map(|x| x * s).collect(),
                (work.err_gap + anchor.rel) * s,
            ));
        }
    }
    let mut involved: Vec<usize> = involved_set.into_iter().collect();
    involved.sort();
    let mut cols = Vec::new();
    for &v in &involved {
        for axis in 0..2 {
            if owned.contains(&axis) || frozen.contains(&v) {
                continue;
            }
            cols.push((v, axis));
        }
    }
    if cols.is_empty() {
        return Err("no-free-controls".to_string());
    }
    let bound = pair_work
        .iter()
        .map(|(w, p)| w.width / 2.0 - p.approx_bound / 2.0)
        .fold(f64::INFINITY, f64::min)
        - HEADROOM;
    if !(bound >= HEADROOM) {
        return Err("movement-budget-empty".to_string());
    }
    Ok(SolveCtx {
        rows,
        pair_work,
        joint_rows,
        involved,
        cols,
        bound,
        hard,
        base,
        upstream: upstream.to_vec(),
        no,
    })
}

fn restricted_matrix(
    ctx: &SolveCtx,
    weld: &HashMap<usize, usize>,
) -> (Vec<Vec<f64>>, Vec<f64>, Vec<RowKind>) {
    let mut merged: Vec<(RowKind, Vec<f64>, f64)> = ctx
        .rows
        .iter()
        .map(|(k, r, c)| {
            let mut row = r.clone();
            let mut keys: Vec<usize> = weld.keys().copied().collect();
            keys.sort();
            for dup in keys {
                let canon = weld[&dup];
                for axis in 0..2 {
                    row[2 * canon + axis] += row[2 * dup + axis];
                }
            }
            (*k, row, *c)
        })
        .collect();
    let mut kinds = Vec::with_capacity(merged.len());
    let mut mat = Vec::with_capacity(merged.len());
    let mut rhs = Vec::with_capacity(merged.len());
    for (k, row, c) in merged.drain(..) {
        kinds.push(k);
        mat.push(ctx.cols.iter().map(|(v, axis)| row[2 * v + axis]).collect());
        rhs.push(-c);
    }
    (mat, rhs, kinds)
}

fn min_norm_vec(mat: &[Vec<f64>], rhs: &[f64]) -> Vec<f64> {
    let (m, n) = (mat.len(), mat.first().map_or(0, Vec::len));
    if m == 0 || n == 0 {
        return vec![0.0; n];
    }
    let flat: Vec<f64> = mat.iter().flat_map(|r| r.iter().copied()).collect();
    let a = nalgebra::DMatrix::from_row_slice(m, n, &flat);
    let b = nalgebra::DVector::from_vec(rhs.to_vec());
    min_norm_solve(&a, &b).iter().copied().collect()
}

struct AttemptOk {
    out: Vec<FittedCommand>,
    continuity: Vec<serde_json::Value>,
    widths: Vec<serde_json::Value>,
}

#[allow(clippy::too_many_arguments)]
fn attempt(
    ctx: &SolveCtx,
    sol: &[f64],
    frac: f64,
    weld: &HashMap<usize, usize>,
    owned: &[usize],
    degenerate: &[[usize; 3]],
    parsed: &geometry::Parsed,
    upstream_cmds: &[FittedCommand],
    parsed_up: &geometry::Parsed,
) -> Result<AttemptOk, (String, serde_json::Value)> {
    let fail = |reason: &str, extra: serde_json::Value| (reason.to_string(), extra);
    let n = ctx.base.len();
    let mut cand = ctx.upstream.clone();
    for ((v, axis), d) in ctx.cols.iter().zip(sol.iter()) {
        if *d != 0.0 {
            cand[*v][*axis] = ctx.upstream[*v][*axis] + frac * d;
        }
    }
    let mut weld_keys: Vec<usize> = weld.keys().copied().collect();
    weld_keys.sort();
    for dup in &weld_keys {
        cand[*dup] = cand[weld[dup]];
    }
    let raw = cand.clone();
    for (v, axis) in &ctx.cols {
        if cand[*v][*axis] != ctx.upstream[*v][*axis] {
            cand[*v][*axis] = geometry::round_26_6(cand[*v][*axis]);
        }
    }
    for dup in &weld_keys {
        for axis in 0..2 {
            if !owned.contains(&axis) {
                cand[*dup][axis] = cand[weld[dup]][axis];
            }
        }
    }
    for v in 0..n {
        for axis in owned {
            if cand[v][*axis] != ctx.upstream[v][*axis] {
                return Err(fail("native-violated", serde_json::json!({})));
            }
        }
    }
    for verts in degenerate {
        if verts.iter().any(|v| cand[*v] != ctx.upstream[*v]) {
            return Err(fail(
                "degenerate-joint-moved",
                serde_json::json!({ "joint": verts[0] }),
            ));
        }
    }
    let mut continuity = Vec::new();
    for jr in &ctx.joint_rows {
        let (cross_c, li_c, lo_c) = cross_of_seg(&cand, jr.joint, jr.occ_prev, jr.occ_seg);
        let (cross_u, li_u, lo_u) = cross_of_seg(&ctx.upstream, jr.joint, jr.occ_prev, jr.occ_seg);
        let iv = leg_vertex(jr.occ_prev, false);
        let ov = leg_vertex(jr.occ_seg, true);
        let raw_moved = |v: usize| {
            (
                raw[v][0] != ctx.upstream[v][0],
                raw[v][1] != ctx.upstream[v][1],
            )
        };
        let moved = [raw_moved(iv), raw_moved(jr.joint), raw_moved(ov)];
        let qb = quant_cross_bound(li_u, lo_u, moved);
        let (raw_cross, _, _) = cross_of_seg(&raw, jr.joint, jr.occ_prev, jr.occ_seg);
        let raw_target = if jr.smooth { 0.0 } else { cross_u };
        let raw_ok = (raw_cross - raw_target).abs() <= 1e-9 * (1.0 + raw_target.abs());
        let legs_ok = li_c[0].hypot(li_c[1]) > 0.0 && lo_c[0].hypot(lo_c[1]) > 0.0;
        let (_, sli, slo) = cross_of_seg(&ctx.base, jr.joint, jr.occ_prev, jr.occ_seg);
        let cross_s = sli[0] * slo[1] - sli[1] * slo[0];
        let (ok, allowed, defect) = if jr.smooth {
            let fwd = li_c[0] * lo_c[0] + li_c[1] * lo_c[1] > 0.0;
            let allowed = if ctx.hard {
                qb
            } else {
                (cross_s - cross_u).abs() + qb
            };
            let defect = cross_c.abs();
            (
                legs_ok && fwd && defect <= allowed && (raw_ok || !ctx.hard),
                allowed,
                defect,
            )
        } else {
            let allowed = (cross_s - cross_u).abs() + qb;
            let defect = (cross_c - cross_u).abs();
            let fwd = li_c[0] * li_u[0] + li_c[1] * li_u[1] > 0.0
                && lo_c[0] * lo_u[0] + lo_c[1] * lo_u[1] > 0.0;
            let mut sign_ok = cross_u == 0.0 || cross_c * cross_u >= 0.0;
            if ctx.hard {
                sign_ok = raw_ok;
            }
            (
                legs_ok && fwd && sign_ok && defect <= allowed,
                allowed,
                defect,
            )
        };
        continuity.push(serde_json::json!({
            "joint": jr.joint,
            "smooth": jr.smooth,
            "cross_up": cross_u,
            "cross_cand": cross_c,
            "allowed": allowed,
            "defect": defect,
            "raw_cross": raw_cross,
            "raw_target": raw_target,
            "ok": ok,
        }));
        if !ok {
            return Err(fail(
                "joint-continuity-failed",
                serde_json::json!({ "continuity": continuity }),
            ));
        }
    }
    let moved: HashSet<usize> = (0..n).filter(|v| cand[*v] != ctx.upstream[*v]).collect();
    let mut incident: HashMap<usize, Vec<[usize; 3]>> = HashMap::new();
    for contour in &parsed.contours {
        for seg in contour {
            match *seg {
                geometry::Segment::Quad { c, a, b } => {
                    let ctrl = [a, ctx.no + c, b];
                    for v in ctrl {
                        incident.entry(v).or_default().push(ctrl);
                    }
                }
                geometry::Segment::Cubic { .. } => {
                    return Err(fail(
                        "cubic-interval-uncertified",
                        serde_json::json!({ "continuity": continuity }),
                    ));
                }
                geometry::Segment::Line { .. } => {}
            }
        }
    }
    let mut order: Vec<usize> = moved.iter().copied().collect();
    order.sort();
    for v in order {
        if let Some(ctrls) = incident.get(&v) {
            for ctrl in ctrls {
                let src = [ctx.base[ctrl[0]], ctx.base[ctrl[1]], ctx.base[ctrl[2]]];
                let got = [cand[ctrl[0]], cand[ctrl[1]], cand[ctrl[2]]];
                if let Err(reason) = quad_interval_ok(&src, &got) {
                    return Err(fail(
                        reason,
                        serde_json::json!({ "continuity": continuity, "interval_ctrl": ctrl }),
                    ));
                }
            }
        }
    }
    let paired: HashSet<([usize; 3], [usize; 3])> = ctx
        .pair_work
        .iter()
        .map(|(_, p)| {
            if p.a_ctrl < p.b_ctrl {
                (p.a_ctrl, p.b_ctrl)
            } else {
                (p.b_ctrl, p.a_ctrl)
            }
        })
        .collect();
    let involved: HashSet<usize> = ctx.involved.iter().copied().collect();
    if let Err(stage) = clearance_ok(
        &ctx.pair_work
            .iter()
            .map(|(_, p)| p.clone())
            .collect::<Vec<_>>(),
        &cand,
        parsed,
        &involved,
        &ctx.upstream,
        &paired,
    ) {
        return Err(fail(
            "clearance-failed",
            serde_json::json!({ "continuity": continuity, "clearance_stage": stage }),
        ));
    }
    let out = emit(upstream_cmds, &cand, ctx.no);
    let parsed_cand = match geometry::parse_commands(&out) {
        Ok(p) => p,
        Err(()) => {
            return Err(fail(
                "topology-changed",
                serde_json::json!({ "continuity": continuity }),
            ))
        }
    };
    if !curves::compare_substituted(parsed, parsed_up, &parsed_cand) {
        return Err(fail(
            "topology-changed",
            serde_json::json!({ "continuity": continuity, "topology_certificates": {
                "source": curves::certify_parsed(parsed, 0).err(),
                "upstream": curves::certify_parsed(parsed_up, 0).err(),
                "candidate": curves::certify_parsed(&parsed_cand, 0).err(),
            }}),
        ));
    }
    let mut widths = Vec::new();
    for (work, pair) in &ctx.pair_work {
        let nrm = [pair.normal[0], pair.normal[1]];
        let fa_u = [
            ctx.upstream[pair.a_ctrl[0]],
            ctx.upstream[pair.a_ctrl[1]],
            ctx.upstream[pair.a_ctrl[2]],
        ];
        let fb_u = [
            ctx.upstream[pair.b_ctrl[0]],
            ctx.upstream[pair.b_ctrl[1]],
            ctx.upstream[pair.b_ctrl[2]],
        ];
        let fa_c = [
            cand[pair.a_ctrl[0]],
            cand[pair.a_ctrl[1]],
            cand[pair.a_ctrl[2]],
        ];
        let fb_c = [
            cand[pair.b_ctrl[0]],
            cand[pair.b_ctrl[1]],
            cand[pair.b_ctrl[2]],
        ];
        let proj = |a: [[f64; 2]; 3], b: [[f64; 2]; 3], t0: f64, t1: f64| {
            let qa = eval_quad(&a, t0);
            let qb = eval_quad(&b, t1);
            ((qb[0] - qa[0]) * nrm[0] + (qb[1] - qa[1]) * nrm[1]).abs()
        };
        widths.push(serde_json::json!({
            "source_2r": work.width,
            "upstream": proj(fa_u, fb_u, pair.a_t, pair.b_t),
            "candidate": proj(fa_c, fb_c, pair.a_t, pair.b_t),
            "approx_bound": pair.approx_bound,
            "radii": pair.radii,
        }));
    }
    Ok(AttemptOk {
        out,
        continuity,
        widths,
    })
}

/// Straight attachments own whole incident curves, not just endpoints.
///
/// Hersch section 2: Bernstein controls determine the whole curve and its
/// endpoint derivatives. Keeping these controls at the preferred fit
/// preserves the attachment polynomial exactly, including a source line
/// that the hinter collapses. This conservative local boundary replaces
/// the whole-outline upright exclusion; length and direction are irrelevant.
/// Hobby section 6 permits medial constraints on the remaining curves.
fn attachment_controls(parsed: &geometry::Parsed) -> HashSet<usize> {
    let weld = weld_map(parsed);
    let canonical = |v: usize| weld.get(&v).copied().unwrap_or(v);
    let mut endpoints = HashSet::new();
    for segment in parsed.contours.iter().flatten() {
        if let geometry::Segment::Line { a, b } = *segment {
            if parsed.oncurve[a] != parsed.oncurve[b] {
                endpoints.extend([canonical(a), canonical(b)]);
            }
        }
    }
    let mut frozen = endpoints.clone();
    for segment in parsed.contours.iter().flatten() {
        if let geometry::Segment::Quad { c, a, b } = *segment {
            if endpoints.contains(&canonical(a)) || endpoints.contains(&canonical(b)) {
                frozen.extend([canonical(a), parsed.oncurve.len() + c, canonical(b)]);
            }
        }
    }
    for (&duplicate, &canon) in &weld {
        if frozen.contains(&canon) {
            frozen.insert(duplicate);
        }
    }
    frozen
}

/// Horizontal completion retaining the fitted Y grid and straight attachments.
/// Turner/Lemberg axis separation; Hersch sections 2 and 5: local width
/// completion retains existing alignment and attachment curves.
pub fn fit_horizontal(
    source: &[FittedCommand],
    preferred: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> Result<FitResult, Error> {
    if !(size_px.is_finite() && size_px > 0.0) {
        return Err(fail("curve model requires finite positive size"));
    }
    let base_diag = serde_json::json!({ "size_px": size_px });
    if !geometry::check_correspondence(source, preferred) {
        return Ok(abstain(preferred, "no-correspondence", base_diag));
    }
    let (Ok(parsed), Ok(fitted)) = (
        geometry::parse_commands(source),
        geometry::parse_commands(preferred),
    ) else {
        return Ok(abstain(preferred, "malformed-commands", base_diag));
    };
    if source.len() > MAX_COMMANDS || preferred.len() > MAX_COMMANDS {
        return Ok(abstain(preferred, "oversize-outline", base_diag));
    }
    if parsed
        .contours
        .iter()
        .flatten()
        .any(|s| matches!(s, geometry::Segment::Cubic { .. }))
    {
        return Ok(abstain(preferred, "cubic-curve-present", base_diag));
    }
    if reference.anchors.is_empty() {
        return Ok(abstain(preferred, "no-reference-anchors", base_diag));
    }
    let retained = [native_axes[0], true];
    let owned: Vec<usize> = retained
        .iter()
        .enumerate()
        .filter(|(_, on)| **on)
        .map(|(a, _)| a)
        .collect();
    // Prototype `fit_glyph` recognizes unbounded (`size_px=None`); the
    // box-gap skip stays available inside `recognize` for other callers
    // but must not narrow the delivered pair set here.
    let (pairs, recognition) = recognize(source, f64::INFINITY);
    if pairs.is_empty() {
        return Ok(abstain(
            preferred,
            "no-certified-pairs",
            serde_json::json!({ "size_px": size_px, "recognition": recognition, "native_axes": native_axes }),
        ));
    }
    let up_global: Vec<[f64; 2]> = fitted
        .oncurve
        .iter()
        .chain(fitted.offcurve.iter())
        .copied()
        .collect();
    let weld = weld_map(&parsed);
    let up_weld = weld_map(&fitted);
    if weld != up_weld {
        return Ok(abstain(
            preferred,
            "weld-mismatch",
            serde_json::json!({ "size_px": size_px }),
        ));
    }
    for (dup, canon) in &weld {
        if up_global[*dup] != up_global[*canon] {
            return Ok(abstain(
                preferred,
                "weld-mismatch",
                serde_json::json!({ "size_px": size_px }),
            ));
        }
    }
    let attachments = attachment_controls(&parsed);
    let mut frozen = attachments.clone();
    frozen.extend(weld.keys().copied());
    let hard = !retained[0];
    let ctx = match assemble(
        &parsed, &up_global, &pairs, reference, size_px, &owned, &frozen, hard,
    ) {
        Ok(c) => c,
        Err(reason) => {
            return Ok(abstain(
                preferred,
                &reason,
                serde_json::json!({ "size_px": size_px, "recognition": recognition }),
            ));
        }
    };
    let _ = fitted;
    let (mat, rhs, kinds) = restricted_matrix(&ctx, &weld);
    let ncols = ctx.cols.len();
    let bounds = vec![ctx.bound; ncols];
    let (sol, peak, qp): (Vec<f64>, f64, Option<QpInfo>) = if hard {
        let mut a_free = Vec::new();
        let mut b_free = Vec::new();
        let mut g = Vec::new();
        let mut h = Vec::new();
        for (i, kind) in kinds.iter().enumerate() {
            if *kind == RowKind::Joint {
                g.push(mat[i].clone());
                h.push(rhs[i]);
            } else {
                a_free.push(mat[i].clone());
                b_free.push(rhs[i]);
            }
        }
        let mut gz = Vec::new();
        let mut hz = Vec::new();
        for (row, val) in g.iter().zip(h.iter()) {
            if row.iter().map(|x| x * x).sum::<f64>().sqrt() > 1e-12 {
                gz.push(row.clone());
                hz.push(*val);
            } else if val.abs() > 1e-10 {
                return Ok(abstain(
                    preferred,
                    "joint-pins-incompatible",
                    serde_json::json!({ "size_px": size_px }),
                ));
            }
        }
        if gz.is_empty() {
            return Ok(abstain(
                preferred,
                "joint-bounds-incompatible",
                serde_json::json!({ "size_px": size_px }),
            ));
        }
        match bounded_equalities(&a_free, &b_free, &gz, &hz, &bounds) {
            Some((s, info)) => {
                let peak = s.iter().map(|x| x.abs()).fold(0.0, f64::max);
                (s, peak, Some(info))
            }
            None => {
                return Ok(abstain(
                    preferred,
                    "joint-bounds-incompatible",
                    serde_json::json!({ "size_px": size_px }),
                ));
            }
        }
    } else {
        let raw = min_norm_vec(&mat, &rhs);
        let (s, peak) = scale_to_bound(&raw, &ctx.cols, ctx.bound);
        (s, peak, None)
    };
    let paired: HashSet<([usize; 3], [usize; 3])> = pairs
        .iter()
        .map(|p| {
            if p.a_ctrl < p.b_ctrl {
                (p.a_ctrl, p.b_ctrl)
            } else {
                (p.b_ctrl, p.a_ctrl)
            }
        })
        .collect();
    let _ = paired;
    let map = joints(&parsed);
    let degenerate: Vec<[usize; 3]> = degenerate_triples(&map);
    let _ = frozen;
    let mut tried = Vec::new();
    let mut frac = 1.0;
    let mut done: Option<AttemptOk> = None;
    let mut last_err: (String, serde_json::Value) =
        ("no-feasible-prefix".to_string(), serde_json::json!({}));
    for _ in 0..PREFIX_ATTEMPTS {
        tried.push(frac);
        match attempt(
            &ctx,
            &sol,
            frac,
            &weld,
            &owned,
            &degenerate,
            &parsed,
            preferred,
            &fitted,
        ) {
            Ok(ok) => {
                done = Some(ok);
                break;
            }
            Err((reason, extra)) => {
                last_err = (reason.clone(), extra.clone());
                if hard || reason == "native-violated" {
                    break;
                }
                let mut probe = ctx.upstream.clone();
                for ((v, axis), d) in ctx.cols.iter().zip(sol.iter()) {
                    if *d != 0.0 {
                        probe[*v][*axis] = ctx.upstream[*v][*axis] + frac * d;
                    }
                }
                let mut identical = true;
                for (v, axis) in &ctx.cols {
                    let mut pv = probe[*v][*axis];
                    if pv != ctx.upstream[*v][*axis] {
                        pv = geometry::round_26_6(pv);
                    }
                    if pv != ctx.upstream[*v][*axis] {
                        identical = false;
                        break;
                    }
                }
                if identical {
                    last_err = ("no-effective-move".to_string(), extra);
                    break;
                }
                frac /= 2.0;
            }
        }
    }
    let Some(ok) = done else {
        let mut diag = serde_json::json!({ "tried_prefixes": tried, "recognition": recognition });
        if let Some(extra) = last_err.1.as_object() {
            for key in [
                "continuity",
                "clearance_stage",
                "interval_ctrl",
                "joint",
                "topology_certificates",
            ] {
                if let Some(v) = extra.get(key) {
                    diag[key] = v.clone();
                }
            }
        }
        return Ok(abstain(preferred, &last_err.0, diag));
    };
    let mut widths = ok.widths;
    for (row, pair) in widths.iter_mut().zip(pairs.iter()) {
        let n = pair_normal(source, pair.a_ctrl, pair.a_t, pair.b_ctrl, pair.b_t);
        row["effectibility_x"] = match n {
            Some(v) => serde_json::json!(v[0].abs()),
            None => serde_json::Value::Null,
        };
    }
    let mean = |key: &str| {
        widths
            .iter()
            .filter_map(|w| w.get(key)?.as_f64())
            .sum::<f64>()
            / widths.len().max(1) as f64
    };
    let mut attachment_controls: Vec<_> = attachments.into_iter().collect();
    attachment_controls.sort_unstable();
    Ok(FitResult {
        commands: ok.out,
        applied: true,
        reason: "fitted".to_string(),
        diagnostics: serde_json::json!({
            "pairs": widths,
            "continuity": ok.continuity,
            "recognition": recognition,
            "n_pairs": pairs.len(),
            "n_joints": ctx.joint_rows.len(),
            "bound": ctx.bound,
            "peak": peak,
            "qp": qp.as_ref().map(qp_json),
            "native_axes": native_axes,
            "retained_upstream_axes": retained,
            "attachment_controls": attachment_controls,
            "topology": { "ok": true },
            "widths": { "source": mean("source_2r"), "upstream": mean("upstream"), "candidate": mean("candidate") },
            "size_px": size_px,
            "reference": reference_meta(reference),
        }),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn attachment_ownership_is_local_and_independent_of_direction_and_scale() {
        // Hersch section 2: a full quadratic control polygon determines
        // the attachment; a zero closure is only an encoding alias.
        let commands = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(0.0, 2.0),
            FittedCommand::QuadTo(1.0, 3.0, 2.0, 3.0),
            FittedCommand::QuadTo(3.0, 3.0, 4.0, 2.0),
            FittedCommand::QuadTo(5.0, 1.0, 4.0, 0.0),
            FittedCommand::QuadTo(3.0, -1.0, 2.0, 0.0),
            FittedCommand::QuadTo(1.0, 1.0, 0.0, 0.0),
            FittedCommand::Close,
        ];
        let parsed = geometry::parse_commands(&commands).unwrap();
        let expected = HashSet::from([0, 1, 2, 5, 6, 7, 11]);
        assert_eq!(attachment_controls(&parsed), expected);
        // Transform the source geometry, keeping its topology and roles.
        // The line is horizontal after rotation, so an upright-only rule
        // or a source-length threshold would fail this invariant.
        for scale in [1.0 / 1024.0, 1.0, 1024.0] {
            let mut rotated = parsed.clone();
            for point in rotated.oncurve.iter_mut().chain(&mut rotated.offcurve) {
                *point = [8.0 - scale * point[1], -4.0 + scale * point[0]];
            }
            assert_eq!(attachment_controls(&rotated), expected);
        }
        let pure_curve = geometry::parse_commands(&[
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::QuadTo(1.0, 1.0, 2.0, 0.0),
            FittedCommand::QuadTo(1.0, -1.0, 0.0, 0.0),
            FittedCommand::Close,
        ])
        .unwrap();
        assert!(attachment_controls(&pure_curve).is_empty());
    }

    fn line_quad() -> Vec<FittedCommand> {
        vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(2.0, 0.0),
            FittedCommand::QuadTo(3.0, 0.0, 4.0, 0.0),
            FittedCommand::Close,
        ]
    }

    fn global(parsed: &geometry::Parsed) -> Vec<[f64; 2]> {
        parsed
            .oncurve
            .iter()
            .chain(parsed.offcurve.iter())
            .copied()
            .collect()
    }

    #[test]
    fn joints_classify_smooth_kink_and_closed_wrap() {
        let parsed = geometry::parse_commands(&line_quad()).unwrap();
        let map = joints(&parsed);
        // Joint 1 joins collinear legs; joints 0 and 2 reverse direction.
        assert_eq!(map.get(&1).map(|v| v.len()), Some(1));
        assert!(map[&1][0].smooth);
        assert!(!map[&1][0].degenerate);
        assert!(!map[&0][0].smooth && !map[&0][0].degenerate);
        assert!(!map[&2][0].smooth && !map[&2][0].degenerate);
    }

    #[test]
    fn weld_map_empty_without_alias_and_pinned_with_alias() {
        let plain = geometry::parse_commands(&line_quad()).unwrap();
        assert!(weld_map(&plain).is_empty());
        let aliased = geometry::parse_commands(&vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(2.0, 0.0),
            FittedCommand::LineTo(0.0, 0.0),
            FittedCommand::Close,
        ])
        .unwrap();
        assert_eq!(weld_map(&aliased), HashMap::from([(2usize, 0usize)]));
    }

    #[test]
    fn g1_row_smooth_targets_zero_and_spans_free_modes() {
        let parsed = geometry::parse_commands(&line_quad()).unwrap();
        let up = global(&parsed);
        let (row, constant) = g1_row(
            &up,
            1,
            SegRef::Line { a: 0, b: 1 },
            SegRef::Quad { off: 3, a: 1, b: 2 },
            16.0,
            true,
        )
        .expect("nondegenerate legs linearize");
        assert_eq!(row.len(), 8);
        assert_eq!(constant, 0.0);
        assert!(row.iter().any(|x| *x != 0.0));
    }

    #[test]
    fn quant_bound_zero_when_nothing_moved() {
        assert_eq!(
            quant_cross_bound([2.0, 0.0], [1.0, 0.0], [(false, false); 3]),
            0.0
        );
        let got = quant_cross_bound([2.0, 0.0], [1.0, 0.0], [(true, true); 3]);
        assert!((got - (6.0 / 128.0 + 8.0 / 16384.0)).abs() < 1e-15);
    }

    #[test]
    fn quant_bound_pairs_incoming_error_with_outgoing_leg() {
        // Bilinear cross: incoming-vertex error scales with the outgoing
        // leg (prototype `ein_x * by + ein_y * bx`), not the incoming one.
        // Unequal legs with only incoming-X moved separate the partners:
        // bound must be half-quantum times |leg_out.y| = 12/128.
        let got = quant_cross_bound(
            [3.0, 4.0],
            [5.0, 12.0],
            [(true, false), (false, false), (false, false)],
        );
        assert!((got - 12.0 / 128.0).abs() < 1e-15, "got {got}");
        let got = quant_cross_bound(
            [3.0, 4.0],
            [5.0, 12.0],
            [(false, false), (false, false), (false, true)],
        );
        assert!((got - 3.0 / 128.0).abs() < 1e-15, "got {got}");
    }

    #[test]
    fn contact_radius_squared_stays_rational() {
        // Roboto 300/14 `S` pair that the float-rounded certificate dropped:
        // `(w/2 ± shell)²` must equal the prototype's exact `Fraction`
        // square, not the rounded-float square (both differ here).
        use num_bigint::BigInt;
        use num_rational::BigRational as Oracle;
        let rat = |num: &[u8], den: &[u8]| {
            Oracle::new(
                BigInt::parse_bytes(num, 10).unwrap(),
                BigInt::parse_bytes(den, 10).unwrap(),
            )
        };
        let den = b"332306998946228968225951765070086144";
        // Compared through the rational image, so the num-rational
        // library stays the reference domain for the exact square.
        assert_eq!(
            contact_r2(0.7473149119635287, 0.015440808887540915, false).map(|r| r.to_rational()),
            Some(rat(b"42641357045623301168557511803828081", den))
        );
        assert_eq!(
            contact_r2(0.7473149119635287, 0.015440808887540915, true).map(|r| r.to_rational()),
            Some(rat(b"50310435489066047239683240985767025", den))
        );
        // Non-finite input fails closed instead of producing a radius.
        assert_eq!(contact_r2(f64::NAN, 0.01, true), None);
        assert_eq!(contact_r2(1.0, f64::INFINITY, false), None);
    }

    #[test]
    fn source_certificate_allows_exact_tangency() {
        // Generic tangency through the recognition wiring inputs: with
        // `w = 2, shell = 0` the disk is exactly unit, so a tangent line
        // or quad is clearance (Bernstein nonneg) while penetration fails.
        // The old bbox gate rejected this tangent case closed.
        let unit = contact_r2(2.0, 0.0, true).expect("unit disk");
        assert!(curves::source_disk_clear(
            [0.0, 0.0],
            &unit,
            &[[-1.0, 1.0], [1.0, 1.0]]
        ));
        assert!(curves::source_disk_clear(
            [0.0, 0.0],
            &unit,
            &[[-1.0, 1.0], [0.0, 1.0], [1.0, 1.0]]
        ));
        assert!(!curves::source_disk_clear(
            [0.0, 0.0],
            &unit,
            &[[-1.0, 0.5], [0.0, 0.5], [1.0, 0.5]]
        ));
        assert!(!curves::source_disk_clear(
            [0.0, 0.0],
            &unit,
            &[[-2.0, 0.0], [2.0, 0.0]]
        ));
    }

    #[test]
    fn interval_ok_accepts_same_and_rejects_reversal_and_sign() {
        let src = [[0.0, 0.0], [1.0, 0.0], [2.0, 1.0]];
        assert!(quad_interval_ok(&src, &src).is_ok());
        let reversed = [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]];
        assert_eq!(quad_interval_ok(&src, &reversed), Err("tangent-reversed"));
        let flipped = [[0.0, 0.0], [1.0, 0.1], [2.0, 0.0]];
        assert_eq!(quad_interval_ok(&src, &flipped), Err("curvature-sign"));
        let straight = [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]];
        assert_eq!(
            quad_interval_ok(&straight, &straight),
            Err("degenerate-curvature")
        );
    }

    #[test]
    fn emit_roundtrips_unmoved_coordinates() {
        let cmds = line_quad();
        let parsed = geometry::parse_commands(&cmds).unwrap();
        let no = parsed.oncurve.len();
        let pts = global(&parsed);
        assert_eq!(emit(&cmds, &pts, no), cmds);
    }

    #[test]
    fn recognize_prepared_wiring_keeps_diagnostics() {
        // The prepared-competitor path keeps candidate accounting and
        // diagnostics shape: two runs agree exactly, and the unbounded
        // delivered entry (INFINITY cap) tries at least the pairs the
        // finite-cap probe tries.
        let lens = vec![
            FittedCommand::MoveTo(0.0, 1.0),
            FittedCommand::QuadTo(-1.0, 0.5, 0.0, 0.0),
            FittedCommand::QuadTo(1.0, 0.5, 0.0, 1.0),
            FittedCommand::Close,
        ];
        let (pairs_a, diag_a) = recognize(&lens, 16.0);
        let (pairs_b, diag_b) = recognize(&lens, 16.0);
        assert_eq!(pairs_a.len(), pairs_b.len());
        assert_eq!(diag_a, diag_b);
        for key in [
            "candidates",
            "rejected",
            "depths_tried",
            "depth",
            "eps_global",
            "poly_edges",
        ] {
            assert!(diag_a.get(key).is_some(), "missing {key}");
        }
        let (pairs_inf, diag_inf) = recognize(&lens, f64::INFINITY);
        assert!(diag_inf["candidates"].as_u64().unwrap() >= diag_a["candidates"].as_u64().unwrap());
        // The cap only skips key pairs, so the unbounded run keeps every
        // finite-cap pair.
        assert!(pairs_inf.len() >= pairs_a.len());
    }

    #[test]
    fn recognize_rejects_contour_and_cubic_scope() {
        let two = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(1.0, 0.0),
            FittedCommand::Close,
            FittedCommand::MoveTo(2.0, 0.0),
            FittedCommand::LineTo(3.0, 0.0),
            FittedCommand::Close,
        ];
        let (_, diag) = recognize(&two, 16.0);
        assert_eq!(
            diag["rejected"]["multi-contour-unsupported"],
            serde_json::json!(1)
        );
        let cubic = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::CurveTo(1.0, 0.0, 2.0, 1.0, 3.0, 1.0),
            FittedCommand::Close,
        ];
        let (_, diag) = recognize(&cubic, 16.0);
        assert_eq!(
            diag["rejected"]["cubic-curve-present"],
            serde_json::json!(1)
        );
    }

    #[test]
    fn degenerate_triples_keep_true_joint_not_vertex_zero() {
        // Zero-length line between vertices 2 and 3 makes joints 2 and 3
        // degenerate; vertex 0 is unrelated to either triple.
        let cmds = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(4.0, 0.0),
            FittedCommand::LineTo(4.0, 4.0),
            FittedCommand::LineTo(4.0, 4.0),
            FittedCommand::LineTo(0.0, 4.0),
            FittedCommand::Close,
        ];
        let parsed = geometry::parse_commands(&cmds).unwrap();
        let map = joints(&parsed);
        let mut degenerate = degenerate_triples(&map);
        degenerate.sort();
        assert_eq!(degenerate, vec![[2, 1, 3], [3, 2, 4]]);
        // Guard semantics mirroring `attempt`: unrelated vertex-0 motion
        // trips nothing, while moving the true joint trips its triple.
        let trips = |moved: &[usize]| {
            degenerate
                .iter()
                .any(|t| t.iter().any(|v| moved.contains(v)))
        };
        assert!(!trips(&[0]));
        assert!(trips(&[2]));
        assert!(trips(&[0, 2]) && !trips(&[0]));
    }

    #[test]
    fn pair_normal_reports_unit_chord() {
        let lens = vec![
            FittedCommand::MoveTo(0.0, 1.0),
            FittedCommand::QuadTo(-1.0, 0.5, 0.0, 0.0),
            FittedCommand::QuadTo(1.0, 0.5, 0.0, 1.0),
            FittedCommand::Close,
        ];
        let n = pair_normal(&lens, [0, 3, 1], 0.5, [1, 4, 2], 0.5).expect("opposed contacts");
        assert!((n[0] - 1.0).abs() < 1e-12 && n[1].abs() < 1e-12);
        assert!(pair_normal(&lens, [0, 3, 9], 0.5, [1, 4, 2], 0.5).is_none());
    }

    /// Exact hull with no filtering: test reference (pre-optimization
    /// `convex_hull` over `cross_rat` magnitude).
    #[cfg(test)]
    fn convex_hull_exact(points: &[Rat]) -> Vec<Rat> {
        let mut pts: Vec<Rat> = points.to_vec();
        pts.sort();
        pts.dedup();
        if pts.len() <= 2 {
            return pts;
        }
        let mut lower: Vec<Rat> = Vec::new();
        for p in &pts {
            while lower.len() >= 2
                && !cross_rat(&lower[lower.len() - 2], &lower[lower.len() - 1], p).is_positive()
            {
                lower.pop();
            }
            lower.push(p.clone());
        }
        let mut upper: Vec<Rat> = Vec::new();
        for p in pts.iter().rev() {
            while upper.len() >= 2
                && !cross_rat(&upper[upper.len() - 2], &upper[upper.len() - 1], p).is_positive()
            {
                upper.pop();
            }
            upper.push(p.clone());
        }
        lower.pop();
        upper.pop();
        lower.extend(upper);
        lower
    }

    /// Exact control hulls of the 2**depth dyadic sub-pieces: test reference.
    #[cfg(test)]
    fn piece_hulls_exact(ctrls: &[Rat], depth: usize) -> Vec<Vec<Rat>> {
        piece_chains(ctrls, depth)
            .iter()
            .map(|piece| convex_hull_exact(piece))
            .collect()
    }

    /// Pre-optimization pair verdict: subdivision hulls rebuilt per pair,
    /// whole-curve box gate after construction. Fully exact: no filtered
    /// predicates on any path.
    #[cfg(test)]
    fn oracle_hulls_ok(a: &[[f64; 2]; 3], b: &[[f64; 2]; 3], shared: Option<Rat>) -> bool {
        let hull_of = |c: &[[f64; 2]; 3]| -> Vec<Vec<Rat>> {
            let rats: Vec<Rat> = c.iter().filter_map(lift).collect();
            if rats.len() != 3 {
                return Vec::new();
            }
            piece_hulls_exact(&rats, 4)
        };
        let (ha, hb) = (hull_of(a), hull_of(b));
        if ha.is_empty() || hb.is_empty() {
            return false;
        }
        let abox = |c: &[[f64; 2]; 3]| {
            (
                c.iter().map(|p| p[0]).fold(f64::INFINITY, f64::min),
                c.iter().map(|p| p[1]).fold(f64::INFINITY, f64::min),
                c.iter().map(|p| p[0]).fold(f64::NEG_INFINITY, f64::max),
                c.iter().map(|p| p[1]).fold(f64::NEG_INFINITY, f64::max),
            )
        };
        if boxes_separate(abox(a), abox(b)) {
            return true;
        }
        for hp in &ha {
            for hq in &hb {
                let bp = rat_box(hp);
                let bq = rat_box(hq);
                if boxes_separate_f(&bp, &bq) {
                    continue;
                }
                if let Some(ref s) = shared {
                    if hulls_meet_only_at_exact(hp, hq, s) {
                        continue;
                    }
                }
                if !strictly_disjoint_exact(hp, hq) {
                    return false;
                }
            }
        }
        true
    }

    fn check_hulls_equiv(a: [[f64; 2]; 3], b: [[f64; 2]; 3], shared: Option<Rat>) {
        // Fresh and pre-warmed caches must both match the oracle, in both
        // argument orders: cache reuse must not change the verdict. The
        // reversed call reselects its shared junction as the clearance
        // traversal would.
        let rev_shared = match &shared {
            Some(_) => shared_point_of(&b, &a).or_else(|| shared.clone()),
            None => None,
        };
        for (x, y, s) in [(a, b, shared.clone()), (b, a, rev_shared)] {
            let oracle = oracle_hulls_ok(&x, &y, s.clone());
            let mut fresh: HashMap<[usize; 3], Option<CachedCurve>> = HashMap::new();
            assert_eq!(
                hulls_ok([0, 1, 2], &x, [3, 4, 5], &y, s.clone(), &mut fresh),
                oracle,
                "fresh cache for {x:?} vs {y:?}"
            );
            assert_eq!(
                hulls_ok([0, 1, 2], &x, [3, 4, 5], &y, s.clone(), &mut fresh),
                oracle,
                "reused cache for {x:?} vs {y:?}"
            );
        }
        // Same-identity lookup exercises the shared cache slot.
        let oracle = oracle_hulls_ok(&a, &a, shared.clone());
        let mut cache: HashMap<[usize; 3], Option<CachedCurve>> = HashMap::new();
        assert_eq!(
            hulls_ok([0, 1, 2], &a, [0, 1, 2], &a, shared, &mut cache),
            oracle,
            "same-identity cache for {a:?}"
        );
    }

    #[cfg(test)]
    fn shared_point_of(a: &[[f64; 2]; 3], b: &[[f64; 2]; 3]) -> Option<Rat> {
        for p in [a[0], a[2]] {
            for q in [b[0], b[2]] {
                if p == q {
                    return lift(&p);
                }
            }
        }
        None
    }

    #[test]
    fn hull_cache_matches_oracle_separated_touching_overlapping() {
        let base = [[0.0, 0.0], [1.0, 2.0], [2.0, 0.0]];
        let far = [[10.0, 10.0], [11.0, 12.0], [12.0, 10.0]];
        check_hulls_equiv(base, far, None);
        // Endpoint touch without a shared junction still fails closed.
        let touch = [[2.0, 0.0], [3.0, 2.0], [4.0, 0.0]];
        check_hulls_equiv(base, touch, None);
        // ... while the incident junction exempts exactly that contact.
        check_hulls_equiv(base, touch, lift(&[2.0, 0.0]));
        // Crossing interiors overlap with no shared endpoint.
        let cross = [[1.0, -1.0], [1.0, 1.0], [3.0, 0.0]];
        check_hulls_equiv(base, cross, None);
        // Contained small curve inside the base arch.
        let inside = [[0.8, 0.4], [1.0, 0.8], [1.2, 0.4]];
        check_hulls_equiv(base, inside, None);
    }

    #[test]
    fn hull_cache_matches_oracle_degenerate() {
        // Zero-length curve: every piece hull is one point.
        let point = [[1.0, 1.0], [1.0, 1.0], [1.0, 1.0]];
        let far = [[10.0, 10.0], [11.0, 12.0], [12.0, 10.0]];
        check_hulls_equiv(point, far, None);
        check_hulls_equiv(point, point, lift(&[1.0, 1.0]));
        // Collinear controls collapse every hull to a segment.
        let flat = [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]];
        let flat_far = [[5.0, 0.0], [6.0, 0.0], [7.0, 0.0]];
        check_hulls_equiv(flat, flat_far, None);
        let flat_over = [[1.0, 0.0], [2.0, 0.0], [3.0, 0.0]];
        check_hulls_equiv(flat, flat_over, None);
        check_hulls_equiv(flat, flat_over, lift(&[2.0, 0.0]));
        // Repeated control point: zero-length first leg.
        let pinned = [[0.0, 0.0], [0.0, 0.0], [2.0, 1.0]];
        check_hulls_equiv(pinned, far, None);
        check_hulls_equiv(pinned, flat, None);
    }

    #[test]
    fn hull_cache_matches_oracle_shared_both_endpoints() {
        // Lens sharing both endpoints: the two argument orders may select
        // different shared junctions, so both must match the oracle.
        let upper = [[0.0, 0.0], [1.0, 1.0], [2.0, 0.0]];
        let lower = [[0.0, 0.0], [1.0, -1.0], [2.0, 0.0]];
        check_hulls_equiv(upper, lower, lift(&[0.0, 0.0]));
        check_hulls_equiv(upper, lower, lift(&[2.0, 0.0]));
        check_hulls_equiv(upper, lower, None);
    }

    #[test]
    fn hull_cache_matches_oracle_rounding_sensitive() {
        // Repeating-fraction and 26.6-quantum offsets near contact.
        let third = 1.0 / 3.0;
        let a = [[0.0, 0.0], [1.0, 1.0], [2.0, 0.0]];
        let b = [[2.0 + third, 0.0], [3.0 + third, 1.0], [4.0 + third, 0.0]];
        check_hulls_equiv(a, b, None);
        let c = [[2.0625, 0.0], [3.0625, 1.0], [4.0625, 0.0]];
        check_hulls_equiv(a, c, None);
        // Near-touch straddling the whole-curve box boundary.
        let d = [[2.0, 0.5], [3.0, 1.5], [4.0, 0.5]];
        check_hulls_equiv(a, d, None);
        check_hulls_equiv(a, d, lift(&[2.0, 0.0]));
    }

    #[test]
    fn hull_cache_matches_oracle_non_finite() {
        // Non-finite controls fail closed with or without the box gate.
        let bad = [[f64::NAN, 0.0], [1.0, 1.0], [2.0, 0.0]];
        let ok = [[0.0, 0.0], [1.0, 2.0], [2.0, 0.0]];
        let far = [[10.0, 10.0], [11.0, 12.0], [12.0, 10.0]];
        check_hulls_equiv(bad, ok, None);
        check_hulls_equiv(bad, far, None);
        check_hulls_equiv(ok, bad, None);
        let inf = [[0.0, 0.0], [1.0, 1.0], [f64::INFINITY, 0.0]];
        check_hulls_equiv(inf, far, None);
        check_hulls_equiv(inf, ok, None);
    }

    #[test]
    fn reprepared_bounds_follow_changed_candidate() {
        // A fresh candidate prepares fresh bounds: warming a cache with
        // one geometry and then deciding a moved geometry from a fresh
        // call-local cache (as `clearance_ok` builds per call) matches
        // the exact oracle, with no stale intervals involved.
        let base = [[0.0, 0.0], [1.0, 2.0], [2.0, 0.0]];
        let far = [[10.0, 10.0], [11.0, 12.0], [12.0, 10.0]];
        let mut stale: HashMap<[usize; 3], Option<CachedCurve>> = HashMap::new();
        assert!(hulls_ok(
            [0, 1, 2],
            &base,
            [3, 4, 5],
            &far,
            None,
            &mut stale
        ));
        // The moved curve crosses the base arch: the fresh decision must
        // refuse, exactly as the oracle does.
        let near = [[1.0, -1.0], [1.0, 1.0], [3.0, 0.0]];
        let mut fresh: HashMap<[usize; 3], Option<CachedCurve>> = HashMap::new();
        assert_eq!(
            hulls_ok([0, 1, 2], &base, [3, 4, 5], &near, None, &mut fresh),
            oracle_hulls_ok(&base, &near, None)
        );
        assert!(!oracle_hulls_ok(&base, &near, None));
        // Prepared bounds track the geometry they were built from: the
        // cached enclosure of the moved curve contains its controls and
        // differs from the far curve's enclosure.
        let cached = |c: &[[f64; 2]; 3]| cached_curve(c).unwrap();
        let (cf, cn) = (cached(&far), cached(&near));
        assert_eq!(cf.bounds.len(), cf.hulls.len());
        assert_eq!(cn.bounds.len(), cn.hulls.len());
        for (hull, iv) in cn.hulls.iter().zip(cn.bounds.iter()) {
            let iv = iv.as_ref().expect("finite curve encloses");
            assert_eq!(hull.len(), iv.len());
            for (v, b) in hull.iter().zip(iv.iter()) {
                let ((lox, hix), (loy, hiy)) = b.bounds();
                let (fx, fy) = (v.0.to_f64().unwrap(), v.1.to_f64().unwrap());
                assert!(lox <= fx && fx <= hix && loy <= fy && fy <= hiy);
            }
        }
        assert_ne!(
            cf.bounds[0].as_ref().unwrap()[0].bounds(),
            cn.bounds[0].as_ref().unwrap()[0].bounds()
        );
    }

    #[test]
    fn hull_cache_matches_oracle_translated_scaled_shared() {
        // Translated/scaled shared contacts agree with the oracle in both
        // argument orders: prepared bounds move with the exact geometry.
        let upper = [[0.0, 0.0], [1.0, 1.0], [2.0, 0.0]];
        let touch = [[2.0, 0.0], [3.0, 2.0], [4.0, 0.0]];
        let mv = |p: [f64; 2]| [p[0] * 2.0 + 37.0, p[1] * 2.0 - 13.0];
        let (su, st) = (upper.map(mv), touch.map(mv));
        check_hulls_equiv(su, st, None);
        check_hulls_equiv(su, st, lift(&mv([2.0, 0.0])));
        // Near-collinear overlap defers to exact without a false accept.
        let flat = [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]];
        let over = [[1.0, 0.0], [2.0, 0.0], [3.0, 0.0]];
        check_hulls_equiv(flat, over, None);
        check_hulls_equiv(flat, over, lift(&[2.0, 0.0]));
    }

    #[test]
    fn quant_cross_bound_joint_error_partner_table() {
        let h = 1.0 / 128.0;
        let li = [3.0, 4.0];
        let lo = [5.0, 12.0];
        let cases: [([(bool, bool); 3], f64, &str); 4] = [
            (
                [(false, false), (true, false), (false, false)],
                16.0 * h,
                "joint-x-only",
            ),
            (
                [(false, false), (false, true), (false, false)],
                8.0 * h,
                "joint-y-only",
            ),
            (
                [(true, false), (false, false), (false, true)],
                15.0 * h + h * h,
                "incoming-x-outgoing-y",
            ),
            (
                [(false, true), (false, false), (true, false)],
                9.0 * h + h * h,
                "incoming-y-outgoing-x",
            ),
        ];
        for (moved, expected, label) in cases {
            assert_eq!(quant_cross_bound(li, lo, moved), expected, "{label}");
        }
    }
}
