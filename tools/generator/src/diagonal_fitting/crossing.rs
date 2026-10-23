//! Bounded joint curved-crossing fit (native port).
//!
//! Source: `experiments/hobby_fitting/curved_crossing.py` (Hobby sections
//! 3.2, 3.5, 3.6, 6; Hersch section 5 symmetry phase; Hersch section 2
//! endpoint relationships for smooth joins; Forsgren, Gill and Wong for
//! the equality-and-bound formulation). Sharp joins keep orientation,
//! nondegeneracy and forward legs rather than the upstream corner
//! magnitude; only source-smooth joints keep exact G1 hard. The
//! approximate-reflection correspondence is soft (Hobby (16) rows in
//! the least-squares objective), never a hard phase. Project
//! adaptations: raw arrives as native `f64` coordinates through the
//! shared `SourceOutline` alias; captured and upstream inputs must be
//! 26.6-grid aligned as in the prototype; delivery re-certifies the
//! substituted outlines through `curves::compare_substituted` and solves
//! through `super::qp::convex_qp`. Invariant: removal-free correction
//! only; unsupported geometry, budget overrun, movement or validity
//! failure all return the upstream outline unchanged with
//! `applied=false`. Only malformed, non-finite or out-of-range input is
//! an error. Runtime never uses experiments, Python, CGAL subprocesses
//! or corpus corrections.

use super::geometry::{self, Segment as GeomSegment};
use super::qp;
use super::{curves, FitResult, Reference, HEADROOM, MAX_COMMANDS};
use crate::fail;
use crate::{fitting_source::SourceOutline, probe::FittedCommand, Error};
use num_rational::BigRational;
use num_traits::{FromPrimitive, Signed, ToPrimitive, Zero};
use std::collections::{HashMap, HashSet};

/// Nearest-26.6 rounding reserve per moved coordinate.
const RESERVE_26_6: f64 = 1.0 / 128.0;
/// Curvature/leg inequality slack for one rounding quantum.
const CROSS_QUANTUM: f64 = 1.0 / 4096.0;
/// Reflection-match tolerance between crossing arms.
const EPS_PARITY: f64 = 0.25;
/// Hobby (16) symmetry-row weight scale.
const ALPHA6: f64 = 5e5;

fn abstain(upstream: &[FittedCommand], reason: &str, diagnostics: serde_json::Value) -> FitResult {
    FitResult {
        commands: upstream.to_vec(),
        applied: false,
        reason: reason.to_string(),
        diagnostics,
    }
}

/// Parity-compatible axis position from geometry, never from pixels.
/// Returns `None` when the snapped count is below one: centering on a
/// boundary for a sub-half-pixel span guarantees dropout, so the parity
/// choice is unsupported rather than defaulted.
pub(super) fn parity_target(axis: f64, width: f64) -> Option<f64> {
    let n = (width + 0.5).floor() as i64;
    if n < 1 {
        return None;
    }
    if n % 2 == 1 {
        let base = (axis - 0.5).floor() + 0.5;
        Some(if (axis - base).abs() <= (axis - (base + 1.0)).abs() {
            base
        } else {
            base + 1.0
        })
    } else {
        let base = (axis + 0.5).floor();
        Some(if (axis - base).abs() <= (axis - (base - 1.0)).abs() {
            base
        } else {
            base - 1.0
        })
    }
}

/// Slope sign of the pair tangent orients the two crossing arms.
pub(super) fn arm_of(normal: [f64; 2]) -> &'static str {
    let mut tangent = [-normal[1], normal[0]];
    if tangent[1] < 0.0 {
        tangent = [-tangent[0], -tangent[1]];
    }
    if tangent[0] >= 0.0 {
        "rising"
    } else {
        "falling"
    }
}

fn sub(a: [f64; 2], b: [f64; 2]) -> [f64; 2] {
    [a[0] - b[0], a[1] - b[1]]
}

fn dot(a: [f64; 2], b: [f64; 2]) -> f64 {
    a[0] * b[0] + a[1] * b[1]
}

fn norm(v: [f64; 2]) -> f64 {
    v[0].hypot(v[1])
}

fn cross2(a: [f64; 2], b: [f64; 2]) -> f64 {
    a[0] * b[1] - a[1] * b[0]
}

/// Exact rational point for fail-closed predicates on binary64 input.
type Rat = (BigRational, BigRational);

fn rat(p: &[f64; 2]) -> Option<Rat> {
    Some((BigRational::from_f64(p[0])?, BigRational::from_f64(p[1])?))
}

/// Duplicate-endpoint alias pairs from closure encoding.
///
/// The parser materializes a closing line when the last endpoint index
/// differs from the first; when that edge is zero-length its start
/// vertex duplicates the contour start coordinates. That alias is an
/// encoding artifact, not zero-tangent geometry.
pub(super) fn weld_map(
    contours: &[Vec<GeomSegment>],
    points: &[[f64; 2]],
) -> HashMap<usize, usize> {
    let mut weld = HashMap::new();
    for contour in contours {
        let segs: Vec<GeomSegment> = contour.to_vec();
        if segs.is_empty() {
            continue;
        }
        let first = segs[0].endpoints().0;
        let last = segs[segs.len() - 1];
        if last.is_line() && last.endpoints().1 == first {
            let dup = last.endpoints().0;
            if dup != first && points[dup] == points[first] {
                weld.insert(dup, first);
            }
        }
    }
    weld
}

fn seg_start(seg: &GeomSegment) -> usize {
    seg.endpoints().0
}

fn seg_end(seg: &GeomSegment) -> usize {
    seg.endpoints().1
}

fn zero_seg(seg: &GeomSegment, points: &[[f64; 2]], no: usize) -> bool {
    match *seg {
        GeomSegment::Line { a, b } => points[a] == points[b],
        GeomSegment::Quad { c, a, b } => points[a] == points[no + c] && points[no + c] == points[b],
        GeomSegment::Cubic { c1, c2, a, b } => {
            points[a] == points[no + c1]
                && points[no + c1] == points[no + c2]
                && points[no + c2] == points[b]
        }
    }
}

#[derive(Clone, Debug)]
pub(super) struct JointOcc {
    pub(super) prev_kind: &'static str,
    pub(super) prev_iv: usize,
    pub(super) seg_kind: &'static str,
    pub(super) seg_ov: usize,
    pub(super) smooth: bool,
    pub(super) degenerate: bool,
}

/// Joint legs in exact arithmetic; smooth needs cross 0, forward dot.
///
/// The predecessor wraps only on geometrically closed contours; open
/// ends carry no joint entry. Zero-length closure aliases are filtered
/// from logical joins; genuine internal zero legs stay classified.
pub(super) fn joints(raw: &SourceOutline, points: &[[f64; 2]]) -> HashMap<usize, Vec<JointOcc>> {
    use num_rational::BigRational as Br;
    let no = raw.oncurve.len();
    let mut out: HashMap<usize, Vec<JointOcc>> = HashMap::new();
    for contour in &raw.contours {
        if contour
            .iter()
            .any(|s| matches!(s, GeomSegment::Cubic { .. }))
        {
            continue;
        }
        let segs = contour.clone();
        if segs.is_empty() {
            continue;
        }
        let closed = seg_end(&segs[segs.len() - 1]) == seg_start(&segs[0]);
        let mut logical = segs.clone();
        if closed
            && matches!(logical[logical.len() - 1], GeomSegment::Line { .. })
            && zero_seg(&logical[logical.len() - 1], points, no)
            && seg_end(&logical[logical.len() - 1]) == seg_start(&logical[0])
        {
            logical.pop();
        }
        if logical.is_empty() {
            continue;
        }
        for (k, seg) in logical.iter().enumerate() {
            if k == 0 && !closed {
                continue;
            }
            let prev = &logical[(k + logical.len() - 1) % logical.len()];
            let j = match *seg {
                GeomSegment::Line { a, .. } => a,
                GeomSegment::Quad { a, .. } => a,
                GeomSegment::Cubic { .. } => continue,
            };
            // In-leg far endpoint: quad control, or the line start.
            let in_far = match *prev {
                GeomSegment::Quad { c, .. } => points[no + c],
                GeomSegment::Line { a, .. } => points[a],
                GeomSegment::Cubic { .. } => points[j],
            };
            let out_far = match *seg {
                GeomSegment::Quad { c, .. } => points[no + c],
                GeomSegment::Line { b, .. } => points[b],
                GeomSegment::Cubic { .. } => points[j],
            };
            let lin = (
                Br::from_f64(points[j][0]).unwrap_or_else(Br::zero)
                    - Br::from_f64(in_far[0]).unwrap_or_else(Br::zero),
                Br::from_f64(points[j][1]).unwrap_or_else(Br::zero)
                    - Br::from_f64(in_far[1]).unwrap_or_else(Br::zero),
            );
            let lout = (
                Br::from_f64(out_far[0]).unwrap_or_else(Br::zero)
                    - Br::from_f64(points[j][0]).unwrap_or_else(Br::zero),
                Br::from_f64(out_far[1]).unwrap_or_else(Br::zero)
                    - Br::from_f64(points[j][1]).unwrap_or_else(Br::zero),
            );
            let degenerate =
                (lin.0.is_zero() && lin.1.is_zero()) || (lout.0.is_zero() && lout.1.is_zero());
            let cross = &lin.0 * &lout.1 - &lin.1 * &lout.0;
            let smooth = !degenerate
                && cross.is_zero()
                && (&lin.0 * &lout.0 + &lin.1 * &lout.1).is_positive();
            let (prev_kind, prev_iv) = match *prev {
                GeomSegment::Quad { c, .. } => ("quad", no + c),
                GeomSegment::Line { a, .. } => ("line", a),
                GeomSegment::Cubic { .. } => ("cubic", j),
            };
            let (seg_kind, seg_ov) = match *seg {
                GeomSegment::Quad { c, .. } => ("quad", no + c),
                GeomSegment::Line { b, .. } => ("line", b),
                GeomSegment::Cubic { .. } => ("cubic", j),
            };
            out.entry(j).or_default().push(JointOcc {
                prev_kind,
                prev_iv,
                seg_kind,
                seg_ov,
                smooth,
                degenerate,
            });
        }
    }
    out
}

/// Linearized joint-cross row with frozen upstream coefficients.
///
/// `cross(J-I, O-J)` linearized at the upstream fit keeps every residual
/// linear in control points (Hobby linearity requirement). Smooth joints
/// target zero shared-tangent cross, permitting common rotation; other
/// joints target the upstream defect, preserving it instead of
/// smoothing.
pub(super) fn g1_row(
    upstream: &[[f64; 2]],
    j: usize,
    prev_kind: &str,
    prev_iv: usize,
    seg_kind: &str,
    seg_ov: usize,
    size_px: f64,
    smooth: bool,
) -> Option<(Vec<f64>, f64)> {
    let at = |v: usize| upstream[v];
    let jj = at(j);
    let ii = at(prev_iv);
    let oo = at(seg_ov);
    let li = sub(jj, ii);
    let lo = sub(oo, jj);
    let ni = norm(li);
    let no_ = norm(lo);
    if !(ni > 0.0) || !(no_ > 0.0) {
        return None;
    }
    let cross_up = cross2(li, lo);
    let mut row = vec![0.0; 2 * upstream.len()];
    let dj = [lo[1] + li[1], -(li[0] + lo[0])];
    let di = [-lo[1], lo[0]];
    let do_ = [-li[1], li[0]];
    row[2 * j] += dj[0];
    row[2 * j + 1] += dj[1];
    row[2 * prev_iv] += di[0];
    row[2 * prev_iv + 1] += di[1];
    row[2 * seg_ov] += do_[0];
    row[2 * seg_ov + 1] += do_[1];
    let arc = (ni + no_) / 2.0;
    let scale = (25.0 / size_px * arc).sqrt() / (ni * no_);
    let _ = (prev_kind, seg_kind, smooth);
    let constant = if smooth { cross_up } else { 0.0 };
    for x in row.iter_mut() {
        *x *= scale;
    }
    Some((row, constant * scale))
}

pub(super) fn cross_of(
    coords: &[[f64; 2]],
    j: usize,
    iv: usize,
    ov: usize,
) -> (f64, [f64; 2], [f64; 2]) {
    let li = sub(coords[j], coords[iv]);
    let lo = sub(coords[ov], coords[j]);
    (cross2(li, lo), li, lo)
}

/// Depth-zero chord substitution loops: quads become chords, lines stay.
///
/// Joints are the input coordinates themselves, so depth-zero joints are
/// exactly float-representable; the certificate is checked separately by
/// the caller. Cubic outlines are unsupported and fail closed here.
pub(super) fn chord_loops(raw: &SourceOutline) -> Option<Vec<Vec<[f64; 2]>>> {
    let mut loops = Vec::with_capacity(raw.contours.len());
    for contour in &raw.contours {
        let mut pts: Vec<[f64; 2]> = Vec::new();
        for seg in contour {
            match *seg {
                GeomSegment::Line { a, b } => {
                    if pts.is_empty() {
                        pts.push(raw.oncurve[a]);
                    }
                    pts.push(raw.oncurve[b]);
                }
                GeomSegment::Quad { a, b, .. } => {
                    if pts.is_empty() {
                        pts.push(raw.oncurve[a]);
                    }
                    pts.push(raw.oncurve[b]);
                }
                GeomSegment::Cubic { .. } => return None,
            }
        }
        // Deduplicate consecutive joints, mirroring the substitution.
        let mut dedup: Vec<[f64; 2]> = Vec::with_capacity(pts.len());
        for p in pts {
            if dedup.last() != Some(&p) {
                dedup.push(p);
            }
        }
        if dedup.len() < 3 {
            return None;
        }
        loops.push(dedup);
    }
    if loops.is_empty() {
        return None;
    }
    Some(loops)
}

pub(super) struct Waist {
    pub(super) width: f64,
    pub(super) mid: f64,
    pub(super) level: f64,
}

/// Internal crossing neck, with separated ink spans above and below.
///
/// This restricted feature class applies Hersch center-phase to a
/// waist, rather than mistaking a silhouette tip for a thin central
/// stroke. Exact critical sections make collinear subdivision
/// immaterial. Exact rational arithmetic decides every comparison.
pub(super) fn waist_from_slabs(loops: &[Vec<[f64; 2]>]) -> Option<Waist> {
    // Chord polyline points as exact rationals.
    let mut contours: Vec<Vec<Rat>> = Vec::new();
    for lp in loops {
        let mut pts = Vec::with_capacity(lp.len());
        for p in lp {
            pts.push(rat(p)?);
        }
        contours.push(pts);
    }
    let mut levels: Vec<BigRational> = contours
        .iter()
        .flat_map(|lp| lp.iter().map(|p| p.1.clone()))
        .collect();
    levels.sort();
    levels.dedup();
    if levels.len() < 2 {
        return None;
    }
    let mut edges: Vec<(Rat, Rat)> = Vec::new();
    for lp in &contours {
        for w in 0..lp.len() {
            let a = lp[w].clone();
            let b = lp[(w + 1) % lp.len()].clone();
            if a.1 == b.1 {
                continue;
            }
            edges.push((a, b));
        }
    }
    let cross = |a: &Rat, b: &Rat, at: &BigRational| -> Option<BigRational> {
        let denom = &b.1 - &a.1;
        if denom.is_zero() {
            return None;
        }
        Some(&a.0 + (at - &a.1) * (&b.0 - &a.0) / denom)
    };
    // (spans, endpoints) per slab.
    let mut slabs: Vec<(usize, Vec<(BigRational, BigRational, BigRational)>)> = Vec::new();
    for pair in levels.windows(2) {
        let (lo, hi) = (pair[0].clone(), pair[1].clone());
        let mid = (&lo + &hi) / BigRational::from_integer(2.into());
        let mut active: Vec<(Rat, Rat)> = edges
            .iter()
            .filter(|(a, b)| {
                let lo_y = std::cmp::min(&a.1, &b.1);
                let hi_y = std::cmp::max(&a.1, &b.1);
                lo_y < &mid && &mid < hi_y
            })
            .cloned()
            .collect();
        active.sort_by(|e1, e2| {
            cross(&e1.0, &e1.1, &mid)
                .partial_cmp(&cross(&e2.0, &e2.1, &mid))
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        let spans = if active.len() % 2 == 0 {
            active.len() / 2
        } else {
            0
        };
        let mut endpoints = Vec::new();
        if spans == 1 {
            for at in [&lo, &hi] {
                let mut xs: Vec<BigRational> =
                    active.iter().filter_map(|(a, b)| cross(a, b, at)).collect();
                xs.sort();
                if xs.len() == 2 {
                    let width = &xs[1] - &xs[0];
                    let midp = (&xs[0] + &xs[1]) / BigRational::from_integer(2.into());
                    endpoints.push((width, midp, (*at).clone()));
                }
            }
        }
        slabs.push((spans, endpoints));
    }
    let mut candidates: Vec<(BigRational, BigRational, BigRational)> = Vec::new();
    let mut i = 0;
    let mut runs = 0;
    while i < slabs.len() {
        if slabs[i].0 != 1 {
            i += 1;
            continue;
        }
        let start = i;
        while i < slabs.len() && slabs[i].0 == 1 {
            i += 1;
        }
        if start == 0 || i == slabs.len() {
            continue;
        }
        if slabs[start - 1].0 < 2 || slabs[i].0 < 2 {
            continue;
        }
        runs += 1;
        if runs > 1 {
            return None;
        }
        for (_, endpoints) in &slabs[start..i] {
            candidates.extend(endpoints.iter().cloned());
        }
        let best = candidates.iter().min()?;
        let first = candidates.first()?;
        let last = candidates.last()?;
        let zero = BigRational::zero();
        if !(best.0 > zero && best.0 < first.0.clone().min(last.0.clone())) {
            return None;
        }
        let result = Waist {
            width: best.0.to_f64()?,
            mid: best.1.to_f64()?,
            level: best.2.to_f64()?,
        };
        if !result.width.is_finite() || !result.mid.is_finite() || !result.level.is_finite() {
            return None;
        }
        return Some(result);
    }
    None
}

#[derive(Clone, Debug)]
pub(super) struct Side {
    pub(super) pair: String,
    pub(super) p0: [f64; 2],
    pub(super) p1: [f64; 2],
    pub(super) i0: usize,
    pub(super) i1: usize,
    pub(super) t0: f64,
    pub(super) t1: f64,
}

pub(super) fn reflect(point: [f64; 2], axis: f64) -> [f64; 2] {
    [2.0 * axis - point[0], point[1]]
}

/// Segment-to-segment reflection matches about the source axis.
///
/// The returned second side is re-encoded to the matching orientation,
/// so corresponding coefficient indices always reflect that
/// orientation.
pub(super) fn match_borders(sides: &[Side], axis: f64, epsilon: f64) -> Vec<(Side, Side, f64)> {
    let mut matches = Vec::new();
    let mut seen: HashSet<(usize, usize)> = HashSet::new();
    for (i, s) in sides.iter().enumerate() {
        let rp0 = reflect(s.p0, axis);
        let rp1 = reflect(s.p1, axis);
        let mut best: Option<(f64, usize, bool)> = None;
        for (j, o) in sides.iter().enumerate() {
            if i == j || s.pair == o.pair {
                continue;
            }
            for reversed in [false, true] {
                let (q0, q1) = if !reversed {
                    (o.p0, o.p1)
                } else {
                    (o.p1, o.p0)
                };
                let dist = norm(sub(rp0, q0)).max(norm(sub(rp1, q1)));
                if best.is_none_or(|(b, _, _)| dist < b) {
                    best = Some((dist, j, reversed));
                }
            }
        }
        let Some((dist, j, reversed)) = best else {
            continue;
        };
        if dist > epsilon {
            continue;
        }
        let key = (i.min(j), i.max(j));
        if !seen.insert(key) {
            continue;
        }
        let mut second = sides[j].clone();
        if reversed {
            std::mem::swap(&mut second.p0, &mut second.p1);
            std::mem::swap(&mut second.i0, &mut second.i1);
            let (t0, t1) = (second.t0, second.t1);
            second.t0 = 1.0 - t1;
            second.t1 = 1.0 - t0;
        }
        matches.push((s.clone(), second, dist));
    }
    matches
}

/// Entire-interval tangent/curvature certificate for quadratics.
///
/// For a quadratic, cross(d1, d2) is constant along the interval, so
/// the control polygon alone certifies curvature sign over the whole
/// interval. Strict positivity of all four leg dot products keeps every
/// candidate tangent within 90 degrees of every source tangent over
/// the whole interval. No sampling, no angular threshold.
pub(super) fn quad_interval_ok(
    src: &[[f64; 2]; 3],
    cand: &[[f64; 2]; 3],
) -> Result<(), &'static str> {
    let (s0, sc, s1) = (src[0], src[1], src[2]);
    let (c0, cc, c1) = (cand[0], cand[1], cand[2]);
    let legs = [sub(sc, s0), sub(s1, sc), sub(cc, c0), sub(c1, cc)];
    if legs.iter().any(|v| !(norm(*v) > 0.0)) {
        return Err("degenerate-leg");
    }
    let ss = cross2(legs[0], legs[1]);
    let cs = cross2(legs[2], legs[3]);
    if ss == 0.0 || cs == 0.0 {
        return Err("degenerate-curvature");
    }
    if cs.signum() != ss.signum() {
        return Err("curvature-sign");
    }
    for (u, v) in [
        (legs[2], legs[0]),
        (legs[3], legs[1]),
        (legs[2], legs[1]),
        (legs[3], legs[0]),
    ] {
        if !(dot(u, v) > 0.0) {
            return Err("tangent-reversed");
        }
    }
    Ok(())
}

/// Exact open-disk clearance of a fixed segment: touch allowed.
pub(super) fn seg_open_clear(center: [f64; 2], radius: f64, seg: ([f64; 2], [f64; 2])) -> bool {
    let (Some(c), Some(a), Some(b)) = (rat(&center), rat(&seg.0), rat(&seg.1)) else {
        return false;
    };
    let Some(r) = BigRational::from_f64(radius) else {
        return false;
    };
    if r < BigRational::zero() {
        return false;
    }
    let ab = (&b.0 - &a.0, &b.1 - &a.1);
    let denom = &ab.0 * &ab.0 + &ab.1 * &ab.1;
    if denom.is_zero() {
        let d2 = (&c.0 - &a.0) * (&c.0 - &a.0) + (&c.1 - &a.1) * (&c.1 - &a.1);
        return d2 >= &r * &r;
    }
    let t = ((&c.0 - &a.0) * &ab.0 + (&c.1 - &a.1) * &ab.1) / &denom;
    let zero = BigRational::zero();
    let one = BigRational::from_integer(1.into());
    let t = if t < zero {
        zero
    } else if t > one {
        one
    } else {
        t
    };
    let q = (&a.0 + &t * &ab.0, &a.1 + &t * &ab.1);
    let d2 = (&c.0 - &q.0) * (&c.0 - &q.0) + (&c.1 - &q.1) * (&c.1 - &q.1);
    d2 >= &r * &r
}

/// 26.6 rounding bound on joint-cross perturbation.
///
/// Only moved coordinates err, at most 1/128 per axis; unmoved legs
/// contribute zero. The bilinear cross gains first-order leg-error
/// terms plus the second-order product.
pub(super) fn quant_cross_bound(
    leg_in: [f64; 2],
    leg_out: [f64; 2],
    moved: [(bool, bool); 3],
) -> f64 {
    let half = |m: bool| if m { RESERVE_26_6 } else { 0.0 };
    let ein_x = half(moved[0].0) + half(moved[1].0);
    let ein_y = half(moved[0].1) + half(moved[1].1);
    let eout_x = half(moved[1].0) + half(moved[2].0);
    let eout_y = half(moved[1].1) + half(moved[2].1);
    let (ax, ay) = (leg_in[0].abs(), leg_in[1].abs());
    let (bx, by) = (leg_out[0].abs(), leg_out[1].abs());
    ein_x * by + ein_y * bx + eout_x * ay + eout_y * ax + ein_x * eout_y + ein_y * eout_x
}

/// Supplied fixed affine correspondence to outline controls (Hobby (31)).
#[derive(Clone, Debug)]
struct Sample {
    terms: Vec<(usize, f64)>,
}

impl Sample {
    fn vertex(index: usize) -> Self {
        Sample {
            terms: vec![(index, 1.0)],
        }
    }

    fn affine(i0: usize, t0: f64, i1: usize, t1: f64) -> Self {
        Sample {
            terms: vec![(i0, t0), (i1, t1)],
        }
    }
}

/// Hobby (17) angular/width coupling weight; the printed 9 is radians.
fn width_weight(w1: f64, w2: f64, t1: [f64; 2], t2: [f64; 2], height: f64) -> f64 {
    let cos = ((t1[0] * t2[0] + t1[1] * t2[1]) / (t1[0].hypot(t1[1]) * t2[0].hypot(t2[1])))
        .clamp(-1.0, 1.0);
    let angle = cos.acos();
    let dw = (w1 - w2) / 0.7;
    500.0 / (height * height) * (-(dw * dw) - (angle / 9.0).powi(2)).exp()
}

/// Linear weighted residuals in displacements at nominal scale.
struct RowSys {
    points: Vec<[f64; 2]>,
    height: f64,
    rows: Vec<(u8, Vec<f64>, f64)>,
}

const GROUP_STRETCH: u8 = 1;
const GROUP_BEND: u8 = 2;

impl RowSys {
    fn new(points: Vec<[f64; 2]>, height: f64) -> Self {
        RowSys {
            points,
            height,
            rows: Vec::new(),
        }
    }

    fn basis(&self, sample: &Sample) -> Vec<f64> {
        let mut row = vec![0.0; self.points.len()];
        for &(index, weight) in &sample.terms {
            row[index] += weight;
        }
        row
    }

    fn point(&self, sample: &Sample) -> [f64; 2] {
        let mut p = [0.0, 0.0];
        for &(index, weight) in &sample.terms {
            p[0] += weight * self.points[index][0];
            p[1] += weight * self.points[index][1];
        }
        p
    }

    /// Outer product of the correspondence basis with a direction, raveled
    /// per-coordinate `(x0, y0, x1, y1, ...)`.
    fn projected(&self, a: &Sample, dir: [f64; 2], b: Option<&Sample>) -> Vec<f64> {
        let ba = self.basis(a);
        let mut row = vec![0.0; 2 * self.points.len()];
        for (k, w) in ba.iter().enumerate() {
            row[2 * k] += w * dir[0];
            row[2 * k + 1] += w * dir[1];
        }
        if let Some(other) = b {
            let bb = self.basis(other);
            for (k, w) in bb.iter().enumerate() {
                row[2 * k] -= w * dir[0];
                row[2 * k + 1] -= w * dir[1];
            }
        }
        row
    }

    /// Hobby (1)-(3), with directions/lengths from input geometry.
    fn edge(&mut self, i: usize, j: usize) -> Result<(), ()> {
        let a = Sample::vertex(i);
        let b = Sample::vertex(j);
        let pa = self.point(&a);
        let pb = self.point(&b);
        let delta = [pb[0] - pa[0], pb[1] - pa[1]];
        let length = delta[0].hypot(delta[1]);
        if !(length > 0.0) {
            return Err(());
        }
        let tangent = [delta[0] / length, delta[1] / length];
        let normal = [-tangent[1], tangent[0]];
        let alpha1 = 1000.0 / self.height.powi(3);
        let ri = self.projected(&a, normal, None);
        let rj = self.projected(&b, normal, None);
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
        self.rows.push((0, sum, 0.0));
        self.rows.push((0, diff, 0.0));
        let scale = (25.0 * length / self.height).sqrt() / length;
        let stretch: Vec<f64> = self
            .projected(&b, tangent, Some(&a))
            .iter()
            .map(|x| x * scale)
            .collect();
        let bend: Vec<f64> = rj
            .iter()
            .zip(ri.iter())
            .map(|(x, y)| (x - y) * scale)
            .collect();
        self.rows.push((GROUP_STRETCH, stretch, 0.0));
        self.rows.push((GROUP_BEND, bend, 0.0));
        Ok(())
    }

    /// Hobby (4),(5): input contacts, medial point and arc-length weight.
    fn pair(
        &self,
        a: &Sample,
        b: &Sample,
        arc: f64,
        medial: [f64; 2],
    ) -> Result<(Vec<f64>, f64, [f64; 2]), ()> {
        if !(arc.is_finite() && arc > 0.0) {
            return Err(());
        }
        let pa = self.point(a);
        let pb = self.point(b);
        let chord = [pa[0] - pb[0], pa[1] - pb[1]];
        let distance = chord[0].hypot(chord[1]);
        if !(distance > 0.0) {
            return Err(());
        }
        let width = 2.0 * (pa[0] - medial[0]).hypot(pa[1] - medial[1]);
        let other = 2.0 * (pb[0] - medial[0]).hypot(pb[1] - medial[1]);
        if !(width > 0.0) || (width - other).abs() > 1e-12 + 1e-10 * other.abs() {
            return Err(());
        }
        let normal = [chord[0] / distance, chord[1] / distance];
        let tangent = [-normal[1], normal[0]];
        let mut error = self.projected(a, normal, Some(b));
        for x in error.iter_mut() {
            *x /= -width;
        }
        Ok((error, width, tangent))
    }

    /// Quadratic form of the Hobby (31)-(33) + (2),(3) construction.
    ///
    /// Quadratic Bernstein weights and derivative weights
    /// `(-2(1-t), 2(1-t)-2t, 2t)` with 16 midpoint intervals; same group
    /// names feed the same upstream-gap constant substitution.
    fn quad_shape(&mut self, ctrl: [usize; 3]) {
        let get = |v: usize| self.points[v];
        let controls = [get(ctrl[0]), get(ctrl[1]), get(ctrl[2])];
        let intervals = 16;
        for j in 0..intervals {
            let t = (f64::from(j) + 0.5) / f64::from(intervals);
            let basis = [(1.0 - t).powi(2), 2.0 * t * (1.0 - t), t * t];
            let deriv_w = [-2.0 * (1.0 - t), 2.0 * (1.0 - t) - 2.0 * t, 2.0 * t];
            let mut deriv = [0.0, 0.0];
            for (w, c) in deriv_w.iter().zip(controls.iter()) {
                deriv[0] += w * c[0];
                deriv[1] += w * c[1];
            }
            let speed = norm(deriv);
            if !(speed > 0.0) {
                continue;
            }
            let normal = [deriv[1] / speed, -deriv[0] / speed];
            let tangent = [deriv[0] / speed, deriv[1] / speed];
            let mut pos = vec![0.0; 2 * self.points.len()];
            for (w, v) in basis.iter().zip(ctrl.iter()) {
                pos[2 * v] += w * normal[0];
                pos[2 * v + 1] += w * normal[1];
            }
            let kpos = (1000.0 / self.height.powi(3) * speed / f64::from(intervals)).sqrt();
            for x in pos.iter_mut() {
                *x *= kpos;
            }
            let factor = (25.0 / self.height * speed / f64::from(intervals)).sqrt() / speed;
            let mut stretch = vec![0.0; 2 * self.points.len()];
            let mut bend = vec![0.0; 2 * self.points.len()];
            for (w, v) in deriv_w.iter().zip(ctrl.iter()) {
                stretch[2 * v] += w * tangent[0] * factor;
                stretch[2 * v + 1] += w * tangent[1] * factor;
                bend[2 * v] += w * normal[0] * factor;
                bend[2 * v + 1] += w * normal[1] * factor;
            }
            self.rows.push((0, pos, 0.0));
            self.rows.push((GROUP_STRETCH, stretch, 0.0));
            self.rows.push((GROUP_BEND, bend, 0.0));
        }
    }
}

/// Nearest 1/64 unit, ties toward positive infinity.
pub(super) fn round_26_6(x: f64) -> f64 {
    (x * 64.0 + 0.5).floor() / 64.0
}

/// True on the 26.6 grid, mirroring the prototype input gate.
fn is_on_grid(value: f64) -> bool {
    value.is_finite() && value * 64.0 == (value * 64.0).round()
}

/// Hobby (16) rows about the fixed parity axis, source mismatch retained.
///
/// Symmetric soft coupling: corresponding coefficient rows carry the
/// reflected source mismatch as finite distortion terms with the fixed
/// map, never as hard equalities.
fn symmetry_rows(
    system: &RowSys,
    base_flat: &[f64],
    matches: &[(Side, Side, f64)],
    axis_src: f64,
    f_k: f64,
) -> Vec<(Vec<f64>, f64)> {
    let mut rows = Vec::new();
    for (first, second, _) in matches {
        let a1 = first.p0;
        let b1 = first.p1;
        let a2 = second.p0;
        let b2 = second.p1;
        let direct = [
            -(b1[0] - a1[0]) + (b2[0] - a2[0]),
            (b1[1] - a1[1]) + (b2[1] - a2[1]),
        ];
        let dist = norm(direct);
        if !(dist > 0.0) {
            continue;
        }
        let normal = [direct[1] / dist, -direct[0] / dist];
        let dab = dist / 2.0;
        let r1 = reflect(a1, axis_src);
        let r2 = reflect(b1, axis_src);
        let src = [dot(normal, sub(a2, r1)), dot(normal, sub(b2, r2))];
        let mut legs = Vec::new();
        for (t, t2, m) in [(first.t0, second.t0, src[0]), (first.t1, second.t1, src[1])] {
            let sample_a = Sample::affine(first.i0, 1.0 - t, first.i1, t);
            let sample_b = Sample::affine(second.i0, 1.0 - t2, second.i1, t2);
            let row: Vec<f64> = system
                .projected(&sample_a, [normal[0], -normal[1]], None)
                .iter()
                .zip(system.projected(&sample_b, normal, None).iter())
                .map(|(x, y)| x + y)
                .collect();
            let constant: f64 = row
                .iter()
                .zip(base_flat.iter())
                .map(|(r, p)| r * p)
                .sum::<f64>()
                - normal[0] * f_k
                - m;
            legs.push((row, constant));
        }
        let factor = (ALPHA6 / system.height.powi(3) * dab).sqrt();
        let ((ra, ca), (rb, cb)) = (&legs[0], &legs[1]);
        let sum_row: Vec<f64> = ra
            .iter()
            .zip(rb.iter())
            .map(|(x, y)| (x + y) * (1.0 / 4.0_f64).sqrt() * factor)
            .collect();
        let sum_c = (ca + cb) * (1.0 / 4.0_f64).sqrt() * factor;
        let diff_row: Vec<f64> = rb
            .iter()
            .zip(ra.iter())
            .map(|(x, y)| (x - y) * (1.0 / 12.0_f64).sqrt() * factor)
            .collect();
        let diff_c = (cb - ca) * (1.0 / 12.0_f64).sqrt() * factor;
        rows.push((sum_row, sum_c));
        rows.push((diff_row, diff_c));
    }
    rows
}

fn shape_objective_rows(
    raw: &SourceOutline,
    no: usize,
    involved: &HashSet<usize>,
    base_all: &[[f64; 2]],
    size_px: f64,
) -> (RowSys, Vec<(Vec<f64>, f64)>) {
    let mut system = RowSys::new(base_all.to_vec(), size_px);
    for contour in &raw.contours {
        for seg in contour {
            match *seg {
                GeomSegment::Quad { c, a, b } => {
                    let idx = [a, no + c, b];
                    if idx.iter().any(|v| involved.contains(v)) {
                        system.quad_shape(idx);
                    }
                }
                GeomSegment::Line { a, b } => {
                    if involved.contains(&a) || involved.contains(&b) {
                        let _ = system.edge(a, b);
                    }
                }
                GeomSegment::Cubic { .. } => {}
            }
        }
    }
    let mut plain: Vec<(Vec<f64>, f64)> = Vec::new();
    for (_, row, _) in &system.rows {
        plain.push((row.clone(), 0.0));
    }
    (system, plain)
}

fn width_objective_rows(
    system: &RowSys,
    prepared: &[geometry::PreppedPair],
    anchors: &[AnchorV],
    size_px: f64,
) -> Vec<(Vec<f64>, f64)> {
    let mut soft: Vec<(Vec<f64>, f64)> = Vec::new();
    for info in prepared {
        let mut station_pairs: Vec<(Vec<f64>, f64, [f64; 2])> = Vec::new();
        let mut usable = true;
        for st in &info.stations {
            let ta = info.a.t0 + (info.a.t1 - info.a.t0) * st.hit.sa;
            let tb = info.b.t0 + (info.b.t1 - info.b.t0) * st.hit.sb;
            match system.pair(
                &Sample::affine(info.a.i0, 1.0 - ta, info.a.i1, ta),
                &Sample::affine(info.b.i0, 1.0 - tb, info.b.i1, tb),
                info.arc,
                st.hit.center,
            ) {
                Ok(triple) => station_pairs.push(triple),
                Err(()) => {
                    usable = false;
                    break;
                }
            }
        }
        if !usable {
            continue;
        }
        for (error, width, tangent) in &station_pairs {
            for anchor in anchors {
                let mut directed = *tangent;
                if dot(directed, anchor.tangent) < 0.0 {
                    directed = [-directed[0], -directed[1]];
                }
                let psi = width_weight(*width, anchor.width, directed, anchor.tangent, size_px);
                let scale = (info.arc * anchor.length * psi).sqrt();
                soft.push((
                    error.iter().map(|x| x * scale).collect(),
                    anchor.rel * scale,
                ));
            }
        }
    }
    soft
}

fn dotv(a: &[f64], b: &[f64]) -> f64 {
    a.iter().zip(b.iter()).map(|(x, y)| x * y).sum()
}

fn ravel(points: &[[f64; 2]]) -> Vec<f64> {
    points.iter().flat_map(|p| [p[0], p[1]]).collect()
}

struct AnchorV {
    tangent: [f64; 2],
    length: f64,
    width: f64,
    rel: f64,
}

/// Joint curved-crossing correction; exact upstream on any gate failure.
///
/// Raw (`SourceOutline`) carries native `f64` source coordinates;
/// captured and upstream outlines must be 26.6-grid aligned. Diagonal
/// stations couple softly to every reference anchor through Hobby (17);
/// approximate reflection enters as soft Hobby (16) rows about the
/// parity axis; only source-smooth joints keep hard G1 rows. The
/// candidate rounds moved X to 26.6 and must preserve orientation,
/// curvature sign, forward tangents, station ink and exact substituted
/// topology, or the exact upstream commands return with the validity
/// evidence.
pub fn fit(
    raw: &SourceOutline,
    source: &[FittedCommand],
    upstream: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> Result<FitResult, Error> {
    fit_impl::<false>(raw, source, upstream, size_px, reference, native_axes)
}

/// Selection discards unapplied-stage diagnostics; standalone capture retains them.
pub(super) fn fit_for_selection(
    raw: &SourceOutline,
    source: &[FittedCommand],
    upstream: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> Result<FitResult, Error> {
    fit_impl::<true>(raw, source, upstream, size_px, reference, native_axes)
}

fn fit_impl<const SELECTING: bool>(
    raw: &SourceOutline,
    source: &[FittedCommand],
    upstream: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> Result<FitResult, Error> {
    if !(size_px.is_finite() && size_px > 0.0) {
        return Err(fail("curved crossing requires finite positive size"));
    }
    if native_axes[0] {
        return Ok(abstain(
            upstream,
            "native-X-owned",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    if !geometry::check_correspondence(source, upstream) {
        return Ok(abstain(
            upstream,
            "no-correspondence",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    if source.len() > MAX_COMMANDS || upstream.len() > MAX_COMMANDS {
        return Ok(abstain(
            upstream,
            "oversize-outline",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    let (Ok(captured), Ok(fitted)) = (
        geometry::parse_commands(source),
        geometry::parse_commands(upstream),
    ) else {
        return Ok(abstain(
            upstream,
            "malformed-commands",
            serde_json::json!({"size_px": size_px}),
        ));
    };
    if raw.oncurve.len() != fitted.oncurve.len()
        || raw.offcurve.len() != fitted.offcurve.len()
        || captured.oncurve.len() != fitted.oncurve.len()
        || captured.offcurve.len() != fitted.offcurve.len()
    {
        return Ok(abstain(
            upstream,
            "no-correspondence",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    for pt in captured
        .oncurve
        .iter()
        .chain(captured.offcurve.iter())
        .chain(fitted.oncurve.iter())
        .chain(fitted.offcurve.iter())
    {
        if !(is_on_grid(pt[0]) && is_on_grid(pt[1])) {
            return Ok(abstain(
                upstream,
                "non-26.6-input",
                serde_json::json!({"size_px": size_px}),
            ));
        }
    }
    let mut anchors: Vec<AnchorV> = Vec::new();
    for anchor in &reference.anchors {
        if anchor.tangent.len() != 2
            || !anchor.tangent.iter().all(|v| v.is_finite())
            || !(anchor.length.is_finite() && anchor.length > 0.0)
            || !(anchor.source_width.is_finite() && anchor.source_width > 0.0)
            || !anchor.rel.is_finite()
        {
            return Ok(abstain(
                upstream,
                "no-reference-anchors",
                serde_json::json!({"size_px": size_px}),
            ));
        }
        let tangent = [anchor.tangent[0], anchor.tangent[1]];
        if !(norm(tangent) > 0.0) {
            return Ok(abstain(
                upstream,
                "no-reference-anchors",
                serde_json::json!({"size_px": size_px}),
            ));
        }
        anchors.push(AnchorV {
            tangent,
            length: anchor.length,
            width: anchor.source_width,
            rel: anchor.rel,
        });
    }
    if anchors.is_empty() {
        return Ok(abstain(
            upstream,
            "no-reference-anchors",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    // Single-contour line/quad raw outline; anything else leaves the
    // attached-diagonal stage empty, exactly as the prototype.
    let raw_supported = raw.contours.len() == 1
        && raw.contours[0]
            .iter()
            .all(|s| !matches!(s, GeomSegment::Cubic { .. }));
    let no = raw.oncurve.len();
    let mut raw_crosses: Vec<serde_json::Value> = Vec::new();
    let mut quantized_zero: Vec<usize> = Vec::new();
    if raw_supported {
        for contour in &raw.contours {
            for seg in contour {
                if let GeomSegment::Quad { c, a, b } = *seg {
                    let cross = cross2(
                        sub(raw.offcurve[c], raw.oncurve[a]),
                        sub(raw.oncurve[b], raw.offcurve[c]),
                    );
                    raw_crosses.push(serde_json::json!({"idx": [a, no + c, b], "cross": cross}));
                    if cross == 0.0 {
                        return Ok(abstain(
                            upstream,
                            "source-degenerate-curvature",
                            serde_json::json!({
                                "size_px": size_px,
                                "raw_crosses": raw_crosses,
                            }),
                        ));
                    }
                }
            }
        }
        for contour in &captured.contours {
            for seg in contour {
                if let geometry::Segment::Quad { c, a, b } = *seg {
                    let cap_cross = cross2(
                        sub(captured.offcurve[c], captured.oncurve[a]),
                        sub(captured.oncurve[b], captured.offcurve[c]),
                    );
                    if cap_cross == 0.0 {
                        quantized_zero.push(no + c);
                    }
                }
            }
        }
    }
    // Dead-work elimination (https://llvm.org/docs/Passes.html#adce-aggressive-dead-code-elimination):
    // the preparation loop below cannot produce a pair without supported raw
    // geometry and a quadratic attachment. Only selection may omit the skipped
    // diagnostics; eligible inputs keep every subsequent certificate unchanged.
    if SELECTING
        && (!raw_supported
            || !raw
                .contours
                .iter()
                .flatten()
                .any(|segment| matches!(segment, GeomSegment::Quad { .. })))
    {
        return Ok(abstain(
            upstream,
            "no-attached-diagonals",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    let (portions, curve_boxes, loops, flats) = geometry::split_visible(raw, true);
    let (pairs, mut skipped) = geometry::recognize(&portions, &loops, true);
    let borders = geometry::visible_borders(&portions);
    let straights = loops.clone();
    let fitted_coords = fitted.oncurve.clone();
    let exact_curves = geometry::curve_controls(raw);
    let mut curved: HashSet<usize> = HashSet::new();
    for contour in &raw.contours {
        for seg in contour {
            if let GeomSegment::Quad { a, b, .. } = *seg {
                curved.insert(a);
                curved.insert(b);
            }
        }
    }
    let mut prepared: Vec<geometry::PreppedPair> = Vec::new();
    if raw_supported {
        for pair in &pairs {
            if geometry::upright_pairs(std::slice::from_ref(pair)).len() == 1 {
                skipped.push(geometry::Skipped {
                    pair: (pair.a.seg, pair.b.seg),
                    reason: "upright-anchor".to_string(),
                });
                continue;
            }
            if !curved.contains(&pair.a.i0)
                && !curved.contains(&pair.a.i1)
                && !curved.contains(&pair.b.i0)
                && !curved.contains(&pair.b.i1)
            {
                skipped.push(geometry::Skipped {
                    pair: (pair.a.seg, pair.b.seg),
                    reason: "no-curve-attachment".to_string(),
                });
                continue;
            }
            match geometry::prepare_pair(
                pair,
                &borders,
                &loops,
                &straights,
                &flats,
                &curve_boxes,
                &fitted_coords,
                &exact_curves,
            ) {
                Ok(info) => prepared.push(info),
                Err(reason) => skipped.push(geometry::Skipped {
                    pair: (pair.a.seg, pair.b.seg),
                    reason: reason.to_string(),
                }),
            }
        }
    }
    let skipped_json = || -> Vec<serde_json::Value> {
        skipped
            .iter()
            .map(|s| serde_json::json!({"pair": [s.pair.0, s.pair.1], "reason": s.reason}))
            .collect()
    };
    if prepared.is_empty() {
        return Ok(abstain(
            upstream,
            "no-attached-diagonals",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
                "quantized_zero_curves": quantized_zero,
            }),
        ));
    }
    // Exact depth-zero substitution certificate on raw input.
    let raw_topology = curves::PreparedSubstitution::new(raw);
    if !raw_topology.is_valid() {
        return Ok(abstain(
            upstream,
            "uncertified-substitution",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
                "quantized_zero_curves": quantized_zero,
            }),
        ));
    }
    let chord = chord_loops(raw);
    let waist = chord.as_ref().and_then(|loops| waist_from_slabs(loops));
    let Some(waist) = waist else {
        return Ok(abstain(
            upstream,
            "no-waist",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
                "quantized_zero_curves": quantized_zero,
            }),
        ));
    };
    // Both directions on both sides of the waist distinguish four arms
    // from a remote fork or hook.
    let mut above: HashSet<&'static str> = HashSet::new();
    let mut below: HashSet<&'static str> = HashSet::new();
    for info in &prepared {
        let heights: Vec<f64> = info
            .stations
            .iter()
            .flat_map(|st| [st.hit.qa[1], st.hit.qb[1]])
            .collect();
        if heights.iter().all(|h| *h > waist.level) {
            above.insert(arm_of(info.normal));
        } else if heights.iter().all(|h| *h < waist.level) {
            below.insert(arm_of(info.normal));
        } else {
            return Ok(abstain(
                upstream,
                "unsupported-crossing-class",
                serde_json::json!({
                    "size_px": size_px,
                    "skipped": skipped_json(),
                    "quantized_zero_curves": quantized_zero,
                    "waist": {"width": waist.width, "mid": waist.mid, "level": waist.level},
                }),
            ));
        }
    }
    let four_arms = above.contains("rising")
        && above.contains("falling")
        && below.contains("rising")
        && below.contains("falling");
    if !four_arms {
        return Ok(abstain(
            upstream,
            "unsupported-crossing-class",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
                "quantized_zero_curves": quantized_zero,
                "waist": {"width": waist.width, "mid": waist.mid, "level": waist.level},
                "arms_above": above.into_iter().collect::<Vec<_>>(),
                "arms_below": below.into_iter().collect::<Vec<_>>(),
            }),
        ));
    }
    // Median over anchor relative changes, matching statistics.median:
    // the middle value, or the mean of the two middles for even counts.
    let mut rels: Vec<f64> = anchors.iter().map(|a| a.rel).collect();
    rels.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let rel_med = if rels.len() % 2 == 1 {
        rels[rels.len() / 2]
    } else {
        (rels[rels.len() / 2 - 1] + rels[rels.len() / 2]) / 2.0
    };
    let pair_mean: f64 = prepared
        .iter()
        .map(|i| i.src_widths.iter().sum::<f64>() / i.src_widths.len() as f64)
        .sum::<f64>()
        / prepared.len() as f64;
    let predicted = waist.width * (1.0 + rel_med);
    if !(predicted > 0.0) {
        return Ok(abstain(
            upstream,
            "no-waist",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
            }),
        ));
    }
    let axis_src = waist.mid;
    let parity_pair = parity_target(axis_src, pair_mean * (1.0 + rel_med));
    let parity_pred = parity_target(axis_src, predicted);
    if parity_pair != parity_pred || parity_pred.is_none() {
        return Ok(abstain(
            upstream,
            "parity-ambiguous",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
                "waist": {"width": waist.width, "mid": waist.mid, "level": waist.level},
            }),
        ));
    }
    let target = parity_pred.unwrap_or(0.0);
    let mut sides: Vec<Side> = Vec::new();
    for info in &prepared {
        for side in [&info.a, &info.b] {
            sides.push(Side {
                pair: info.id.clone(),
                p0: side.p0,
                p1: side.p1,
                i0: side.i0,
                i1: side.i1,
                t0: side.t0,
                t1: side.t1,
            });
        }
    }
    let matches = match_borders(&sides, axis_src, EPS_PARITY);
    if matches.is_empty() {
        return Ok(abstain(
            upstream,
            "no-symmetry-matches",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
                "quantized_zero_curves": quantized_zero,
                "waist": {"width": waist.width, "mid": waist.mid, "level": waist.level},
            }),
        ));
    }
    finish(
        raw,
        &raw_topology,
        &captured,
        &fitted,
        upstream,
        size_px,
        &anchors,
        &prepared,
        &skipped,
        waist,
        rel_med,
        target,
        &matches,
        quantized_zero,
        raw_crosses,
    )
}

struct ControlOwnership {
    weld: HashMap<usize, usize>,
    quads: Vec<[usize; 3]>,
    involved: HashSet<usize>,
    cols: Vec<usize>,
}

enum OwnershipAbort {
    WeldMismatch,
    NoFreeControls,
}

fn compatible_welds(
    raw: &SourceOutline,
    fitted: &geometry::Parsed,
    base_all: &[[f64; 2]],
    up_all: &[[f64; 2]],
) -> Result<HashMap<usize, usize>, OwnershipAbort> {
    // Weld aliases must agree between raw and upstream encodings.
    let weld = weld_map(&raw.contours, base_all);
    let up_weld = weld_map(&fitted.contours, up_all);
    if weld != up_weld {
        return Err(OwnershipAbort::WeldMismatch);
    }
    for (dup, canon) in &weld {
        if up_all[*dup] != up_all[*canon] {
            return Err(OwnershipAbort::WeldMismatch);
        }
    }
    Ok(weld)
}

fn quadratic_indices(raw: &SourceOutline) -> Vec<[usize; 3]> {
    let no = raw.oncurve.len();
    let mut quads: Vec<[usize; 3]> = Vec::new();
    for contour in &raw.contours {
        for seg in contour {
            if let GeomSegment::Quad { c, a, b } = *seg {
                quads.push([a, no + c, b]);
            }
        }
    }
    quads
}

fn involved_closure(
    prepared: &[geometry::PreppedPair],
    quads: &[[usize; 3]],
    weld: &HashMap<usize, usize>,
) -> HashSet<usize> {
    let mut involved: HashSet<usize> = HashSet::new();
    for info in prepared {
        for side in [&info.a, &info.b] {
            involved.insert(side.i0);
            involved.insert(side.i1);
        }
    }
    loop {
        let mut grown = involved.clone();
        for idx in quads {
            if idx.iter().any(|v| involved.contains(v)) {
                grown.extend(idx.iter().copied());
            }
        }
        for v in involved.iter() {
            grown.insert(*weld.get(v).unwrap_or(v));
        }
        if grown == involved {
            break;
        }
        involved = grown;
    }
    involved
}

fn upright_controls(
    raw: &SourceOutline,
    base_all: &[[f64; 2]],
    weld: &HashMap<usize, usize>,
) -> HashSet<usize> {
    let mut upright: HashSet<usize> = HashSet::new();
    for contour in &raw.contours {
        for seg in contour {
            if let GeomSegment::Line { a, b } = *seg {
                if base_all[a][0] == base_all[b][0] && base_all[a][1] != base_all[b][1] {
                    upright.insert(a);
                    upright.insert(b);
                }
            }
        }
    }
    for v in upright.clone() {
        if let Some(canon) = weld.get(&v) {
            upright.insert(*canon);
        }
    }
    upright
}

impl ControlOwnership {
    fn prepare(
        raw: &SourceOutline,
        fitted: &geometry::Parsed,
        base_all: &[[f64; 2]],
        up_all: &[[f64; 2]],
        prepared: &[geometry::PreppedPair],
    ) -> Result<ControlOwnership, OwnershipAbort> {
        let weld = compatible_welds(raw, fitted, base_all, up_all)?;
        let quads = quadratic_indices(raw);
        let involved = involved_closure(prepared, &quads, &weld);
        let upright = upright_controls(raw, base_all, &weld);
        let mut cols: Vec<usize> = involved
            .iter()
            .filter(|v| !upright.contains(v) && !weld.contains_key(v))
            .copied()
            .collect();
        cols.sort();
        if cols.is_empty() {
            return Err(OwnershipAbort::NoFreeControls);
        }
        Ok(ControlOwnership {
            weld,
            quads,
            involved,
            cols,
        })
    }
}

enum JointAbort {
    DegenerateJoint,
    DegenerateLeg,
}

enum HardRowAbort {
    FixedIncompatible,
}

fn collect_joint_constraints(
    joint_iter: impl IntoIterator<Item = (usize, Vec<JointOcc>)>,
    up_all: &[[f64; 2]],
    involved: &HashSet<usize>,
    size_px: f64,
) -> Result<(Vec<(Vec<f64>, f64)>, Vec<JointGate>), JointAbort> {
    // Hard G1 rows: source-smooth joints only.
    let mut hard_full: Vec<(Vec<f64>, f64)> = Vec::new();
    let mut gates: Vec<JointGate> = Vec::new();
    for (j, occs) in joint_iter {
        for occ in occs {
            if ![j, occ.prev_iv, occ.seg_ov]
                .iter()
                .any(|v| involved.contains(v))
            {
                continue;
            }
            if occ.degenerate {
                return Err(JointAbort::DegenerateJoint);
            }
            if occ.smooth {
                match g1_row(
                    up_all,
                    j,
                    occ.prev_kind,
                    occ.prev_iv,
                    occ.seg_kind,
                    occ.seg_ov,
                    size_px,
                    true,
                ) {
                    Some((row, constant)) => hard_full.push((row, -constant)),
                    None => return Err(JointAbort::DegenerateLeg),
                }
            }
            gates.push(JointGate {
                j,
                iv: occ.prev_iv,
                ov: occ.seg_ov,
                prev_line: occ.prev_kind == "line",
                seg_line: occ.seg_kind == "line",
                smooth: occ.smooth,
            });
        }
    }
    Ok((hard_full, gates))
}

fn reduce_joint_rows(
    hard_full: &[(Vec<f64>, f64)],
    reduce: &impl Fn(&[f64]) -> Vec<f64>,
) -> Result<Vec<(Vec<f64>, f64)>, HardRowAbort> {
    let mut kept_hard: Vec<(Vec<f64>, f64)> = Vec::new();
    for (row, target_h) in hard_full {
        let red = reduce(row);
        if red.iter().any(|x| *x != 0.0) {
            kept_hard.push((red, *target_h));
        } else if target_h.abs() > 1e-9 {
            return Err(HardRowAbort::FixedIncompatible);
        }
    }
    Ok(kept_hard)
}

enum QuadraticAbort {
    DegenerateCurvature,
}

fn quadratic_constraints(
    quads: &[[usize; 3]],
    involved: &HashSet<usize>,
    base_all: &[[f64; 2]],
    up_all: &[[f64; 2]],
    flat_up: &[f64],
    reduce: &impl Fn(&[f64]) -> Vec<f64>,
) -> Result<(Vec<Vec<f64>>, Vec<f64>), QuadraticAbort> {
    let nvars = base_all.len();
    let mut cmat: Vec<Vec<f64>> = Vec::new();
    let mut clower: Vec<f64> = Vec::new();
    for idx in quads {
        if !idx.iter().any(|v| involved.contains(v)) {
            continue;
        }
        let (p0, ctrl, p1) = (idx[0], idx[1], idx[2]);
        let su = sub(base_all[ctrl], base_all[p0]);
        let sv = sub(base_all[p1], base_all[ctrl]);
        let source_cross = cross2(su, sv);
        if source_cross == 0.0 {
            return Err(QuadraticAbort::DegenerateCurvature);
        }
        let sign = if source_cross > 0.0 { 1.0 } else { -1.0 };
        let mut row = vec![0.0; 2 * nvars];
        row[2 * p0] = up_all[ctrl][1] - up_all[p1][1];
        row[2 * ctrl] = up_all[p1][1] - up_all[p0][1];
        row[2 * p1] = up_all[p0][1] - up_all[ctrl][1];
        for x in row.iter_mut() {
            *x *= sign;
        }
        let red = reduce(&row);
        let reserve = red.iter().map(|x| x.abs()).sum::<f64>() * RESERVE_26_6 + CROSS_QUANTUM;
        clower.push(reserve - dotv(&row, flat_up));
        cmat.push(red);
        for (i, j) in [(p0, ctrl), (ctrl, p1)] {
            for leg in [su, sv] {
                let mut leg_row = vec![0.0; 2 * nvars];
                leg_row[2 * j] = leg[0];
                leg_row[2 * i] = -leg[0];
                let value = dot(sub(up_all[j], up_all[i]), leg);
                let leg_red = reduce(&leg_row);
                let leg_reserve =
                    leg_red.iter().map(|x| x.abs()).sum::<f64>() * RESERVE_26_6 + CROSS_QUANTUM;
                clower.push(leg_reserve - value);
                cmat.push(leg_red);
            }
        }
    }
    Ok((cmat, clower))
}

struct JointGate {
    j: usize,
    iv: usize,
    ov: usize,
    prev_line: bool,
    seg_line: bool,
    smooth: bool,
}

fn append_sharp_joint_constraints(
    gates: &[JointGate],
    base_all: &[[f64; 2]],
    up_all: &[[f64; 2]],
    reduce: &impl Fn(&[f64]) -> Vec<f64>,
    cmat: &mut Vec<Vec<f64>>,
    clower: &mut Vec<f64>,
) {
    let nvars = base_all.len();
    for gate in gates {
        if gate.smooth {
            continue;
        }
        let (s_cross, _, _) = cross_of(base_all, gate.j, gate.iv, gate.ov);
        if s_cross != 0.0 {
            let s = s_cross.signum();
            let (yi, yj, yo) = (up_all[gate.iv][1], up_all[gate.j][1], up_all[gate.ov][1]);
            let mut grow = vec![0.0; 2 * nvars];
            grow[2 * gate.iv] = -(yo - yj) * s;
            grow[2 * gate.j] = (yo - yi) * s;
            grow[2 * gate.ov] = -(yj - yi) * s;
            let here = sub(up_all[gate.j], up_all[gate.iv]);
            let there = sub(up_all[gate.ov], up_all[gate.j]);
            let value = s * (here[0] * there[1] - here[1] * there[0]);
            let red = reduce(&grow);
            let reserve = red.iter().map(|x| x.abs()).sum::<f64>() * RESERVE_26_6 + CROSS_QUANTUM;
            clower.push(reserve - value);
            cmat.push(red);
        }
        if gate.prev_line {
            let src_leg = sub(base_all[gate.j], base_all[gate.iv]);
            let mut leg_row = vec![0.0; 2 * nvars];
            leg_row[2 * gate.j] = src_leg[0];
            leg_row[2 * gate.iv] = -src_leg[0];
            let value = dot(sub(up_all[gate.j], up_all[gate.iv]), src_leg);
            let red = reduce(&leg_row);
            let reserve = red.iter().map(|x| x.abs()).sum::<f64>() * RESERVE_26_6 + CROSS_QUANTUM;
            clower.push(reserve - value);
            cmat.push(red);
        }
        if gate.seg_line {
            let src_leg = sub(base_all[gate.ov], base_all[gate.j]);
            let mut leg_row = vec![0.0; 2 * nvars];
            leg_row[2 * gate.ov] = src_leg[0];
            leg_row[2 * gate.j] = -src_leg[0];
            let value = dot(sub(up_all[gate.ov], up_all[gate.j]), src_leg);
            let red = reduce(&leg_row);
            let reserve = red.iter().map(|x| x.abs()).sum::<f64>() * RESERVE_26_6 + CROSS_QUANTUM;
            clower.push(reserve - value);
            cmat.push(red);
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn finish(
    raw: &SourceOutline,
    raw_topology: &curves::PreparedSubstitution<'_>,
    captured: &geometry::Parsed,
    fitted: &geometry::Parsed,
    upstream: &[FittedCommand],
    size_px: f64,
    anchors: &[AnchorV],
    prepared: &[geometry::PreppedPair],
    skipped: &[geometry::Skipped],
    waist: Waist,
    rel_med: f64,
    target: f64,
    matches: &[(Side, Side, f64)],
    quantized_zero: Vec<usize>,
    raw_crosses: Vec<serde_json::Value>,
) -> Result<FitResult, Error> {
    let skipped_json = || -> Vec<serde_json::Value> {
        skipped
            .iter()
            .map(|s| serde_json::json!({"pair": [s.pair.0, s.pair.1], "reason": s.reason}))
            .collect()
    };
    let waist_json =
        || serde_json::json!({"width": waist.width, "mid": waist.mid, "level": waist.level});
    let no = raw.oncurve.len();
    let base_all: Vec<[f64; 2]> = raw
        .oncurve
        .iter()
        .chain(raw.offcurve.iter())
        .copied()
        .collect();
    let up_all: Vec<[f64; 2]> = fitted
        .oncurve
        .iter()
        .chain(fitted.offcurve.iter())
        .copied()
        .collect();
    let base_flat = ravel(&base_all);
    let gaps_flat: Vec<f64> = up_all
        .iter()
        .zip(base_all.iter())
        .flat_map(|(u, b)| [u[0] - b[0], u[1] - b[1]])
        .collect();
    let flat_up = ravel(&up_all);
    let ControlOwnership {
        weld,
        quads,
        involved,
        cols,
    } = match ControlOwnership::prepare(raw, fitted, &base_all, &up_all, prepared) {
        Ok(ownership) => ownership,
        Err(OwnershipAbort::WeldMismatch) => {
            return Ok(abstain(
                upstream,
                "weld-mismatch",
                serde_json::json!({
                    "size_px": size_px,
                    "skipped": skipped_json(),
                    "waist": waist_json(),
                }),
            ));
        }
        Err(OwnershipAbort::NoFreeControls) => {
            return Ok(abstain(
                upstream,
                "no-free-controls",
                serde_json::json!({
                    "size_px": size_px,
                    "skipped": skipped_json(),
                    "waist": waist_json(),
                }),
            ));
        }
    };
    let (system, plain) = shape_objective_rows(raw, no, &involved, &base_all, size_px);
    // Shape rows keep the upstream gap unsubstituted: like the prototype
    // `soft_plain` block, their target is `-c`, so they regularize the
    // displacement itself. Only width and symmetry rows (the `soft_gap`
    // block) substitute the upstream gap into their constants.
    let mut soft = width_objective_rows(&system, prepared, anchors, size_px);
    let sym = symmetry_rows(&system, &base_flat, matches, waist.mid, 2.0 * target);
    if sym.is_empty() {
        return Ok(abstain(
            upstream,
            "phase-unconstrained",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
                "waist": waist_json(),
            }),
        ));
    }
    for (row, constant) in &sym {
        soft.push((row.clone(), *constant));
    }
    // Weld-folded reduction to free X columns.
    let reduce = |row: &[f64]| -> Vec<f64> {
        let mut full = row.to_vec();
        let mut keys: Vec<usize> = weld.keys().copied().collect();
        keys.sort();
        for dup in keys {
            let canon = weld[&dup];
            full[2 * canon] += full[2 * dup];
        }
        cols.iter().map(|v| full[2 * v]).collect()
    };
    let mat: Vec<Vec<f64>> = plain
        .iter()
        .chain(soft.iter())
        .map(|(row, _)| reduce(row))
        .collect();
    let rhs: Vec<f64> = plain
        .iter()
        .map(|(_, constant)| -constant)
        .chain(
            soft.iter()
                .map(|(row, constant)| -dotv(row, &gaps_flat) - constant),
        )
        .collect();
    let (hard_full, gates) =
        match collect_joint_constraints(joints(raw, &base_all), &up_all, &involved, size_px) {
            Ok(collected) => collected,
            Err(JointAbort::DegenerateJoint) => {
                return Ok(abstain(
                    upstream,
                    "degenerate-joint",
                    serde_json::json!({
                        "size_px": size_px,
                        "skipped": skipped_json(),
                        "waist": waist_json(),
                    }),
                ));
            }
            Err(JointAbort::DegenerateLeg) => {
                return Ok(abstain(
                    upstream,
                    "degenerate-leg",
                    serde_json::json!({
                        "size_px": size_px,
                        "skipped": skipped_json(),
                        "waist": waist_json(),
                    }),
                ));
            }
        };
    let kept_hard = match reduce_joint_rows(&hard_full, &reduce) {
        Ok(kept) => kept,
        Err(HardRowAbort::FixedIncompatible) => {
            return Ok(abstain(
                upstream,
                "fixed-constraints-incompatible",
                serde_json::json!({
                    "size_px": size_px,
                    "skipped": skipped_json(),
                    "waist": waist_json(),
                }),
            ));
        }
    };
    let ge: Vec<Vec<f64>> = kept_hard.iter().map(|(r, _)| r.clone()).collect();
    let he: Vec<f64> = kept_hard.iter().map(|(_, t)| *t).collect();
    // Linear curvature/leg inequalities with frozen upstream coefficients.
    let (mut cmat, mut clower) =
        match quadratic_constraints(&quads, &involved, &base_all, &up_all, &flat_up, &reduce) {
            Ok(constraints) => constraints,
            Err(QuadraticAbort::DegenerateCurvature) => {
                return Ok(abstain(
                    upstream,
                    "source-degenerate-curvature",
                    serde_json::json!({
                        "size_px": size_px,
                        "raw_crosses": raw_crosses,
                    }),
                ));
            }
        };
    append_sharp_joint_constraints(&gates, &base_all, &up_all, &reduce, &mut cmat, &mut clower);
    if cmat.is_empty() {
        return Ok(abstain(
            upstream,
            "no-curve-constraints",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
                "waist": waist_json(),
            }),
        ));
    }
    let radius = prepared
        .iter()
        .map(|i| i.src_widths.iter().cloned().fold(f64::INFINITY, f64::min) / 2.0)
        .fold(f64::INFINITY, f64::min);
    let bound = radius - HEADROOM;
    if !(bound > 0.0) {
        return Ok(abstain(
            upstream,
            "movement-budget-empty",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
                "waist": waist_json(),
            }),
        ));
    }
    let Some((delta, qp_info)) = qp::convex_qp(&mat, &rhs, &ge, &he, &cmat, &clower, bound) else {
        return Ok(abstain(
            upstream,
            "constraints-incompatible",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
                "waist": waist_json(),
                "parity_target": target,
                "matches": matches.len(),
                "n_hard": he.len(),
                "n_bound": cols.len(),
                "bound": bound,
                "radius": radius,
                "quantized_zero_curves": quantized_zero,
            }),
        ));
    };
    deliver(
        raw,
        raw_topology,
        captured,
        fitted,
        upstream,
        size_px,
        prepared,
        skipped,
        waist,
        rel_med,
        target,
        matches,
        quantized_zero,
        raw_crosses,
        &base_all,
        &up_all,
        cols,
        weld,
        delta,
        qp_info,
        radius,
        bound,
        kept_hard,
        gates,
        quads,
        involved,
    )
}

fn rounded_hard_checks(
    cols: &[usize],
    kept_hard: &[(Vec<f64>, f64)],
    raw_new: &[[f64; 2]],
    cand_all: &[[f64; 2]],
    up_all: &[[f64; 2]],
) -> (bool, Vec<serde_json::Value>) {
    // Rounded hard-constraint check with per-coordinate allowance.
    let col_x: Vec<usize> = cols.iter().map(|v| 2 * v).collect();
    let flat = |pts: &[[f64; 2]]| -> Vec<f64> { ravel(pts) };
    let raw_flat = flat(raw_new);
    let cand_flat = flat(cand_all);
    let up_flat = flat(up_all);
    let d_raw: Vec<f64> = raw_flat
        .iter()
        .zip(up_flat.iter())
        .map(|(a, b)| a - b)
        .collect();
    let d_cand: Vec<f64> = cand_flat
        .iter()
        .zip(up_flat.iter())
        .map(|(a, b)| a - b)
        .collect();
    let mut hard_checks: Vec<serde_json::Value> = Vec::new();
    for (red, target_h) in kept_hard {
        // Reduced rows act on the free X columns only.
        let d_raw_red: Vec<f64> = col_x.iter().map(|c| d_raw[*c]).collect();
        let d_cand_red: Vec<f64> = col_x.iter().map(|c| d_cand[*c]).collect();
        let raw_error = (dotv(red, &d_raw_red) - target_h).abs();
        let error = (dotv(red, &d_cand_red) - target_h).abs();
        let mut allowance = 0.0;
        for (k, v) in cols.iter().enumerate() {
            if raw_new[*v][0] != up_all[*v][0] {
                allowance += red[k].abs() * RESERVE_26_6;
            }
        }
        let norm_red = red.iter().map(|x| x * x).sum::<f64>().sqrt();
        let ok = raw_error <= 1e-7 * (1.0 + target_h.abs()) * (1.0 + norm_red)
            && error <= allowance + 1e-9;
        hard_checks.push(serde_json::json!({
            "raw_error": raw_error,
            "rounded_error": error,
            "allowance": allowance,
            "ok": ok,
        }));
        if !ok {
            return (false, hard_checks);
        }
    }
    (true, hard_checks)
}

fn rounded_joint_checks(
    gates: &[JointGate],
    raw_new: &[[f64; 2]],
    cand_all: &[[f64; 2]],
    up_all: &[[f64; 2]],
    base_all: &[[f64; 2]],
) -> (bool, Vec<serde_json::Value>) {
    // Joint continuity with the 26.6 perturbation bound.
    let mut continuity: Vec<serde_json::Value> = Vec::new();
    for gate in gates {
        let (raw_cross, _, _) = cross_of(raw_new, gate.j, gate.iv, gate.ov);
        let (old_cross, li_u, lo_u) = cross_of(up_all, gate.j, gate.iv, gate.ov);
        let (cross, li_c, lo_c) = cross_of(cand_all, gate.j, gate.iv, gate.ov);
        let (source_cross, _, _) = cross_of(base_all, gate.j, gate.iv, gate.ov);
        let target_cross = if gate.smooth { 0.0 } else { old_cross };
        let moved = [
            (raw_new[gate.iv] != up_all[gate.iv], false),
            (raw_new[gate.j] != up_all[gate.j], false),
            (raw_new[gate.ov] != up_all[gate.ov], false),
        ];
        let allowance = quant_cross_bound(li_u, lo_u, moved);
        let mut ok = norm(li_c) > 0.0 && norm(lo_c) > 0.0;
        if gate.smooth {
            ok &= (raw_cross - target_cross).abs() <= 1e-8 * (1.0 + target_cross.abs());
            ok &= (cross - target_cross).abs() <= allowance + 1e-9;
            ok &= dot(li_c, lo_c) > 0.0;
        } else if source_cross != 0.0 {
            ok &= cross * source_cross > 0.0;
        } else {
            ok = false;
        }
        continuity.push(serde_json::json!({
            "joint": gate.j,
            "smooth": gate.smooth,
            "cross_src": source_cross,
            "cross_up": old_cross,
            "cross_cand": cross,
            "allowed": allowance,
            "ok": ok,
        }));
        if !ok {
            return (false, continuity);
        }
    }
    (true, continuity)
}

type ClearanceLine = ([f64; 2], [f64; 2]);

struct ClearancePrimitives {
    fixed_curves: Vec<Vec<[f64; 2]>>,
    fixed_lines: Vec<ClearanceLine>,
    moved_lines: Vec<(ClearanceLine, ClearanceLine)>,
}

fn collect_clearance_primitives(
    raw: &SourceOutline,
    quads: &[[usize; 3]],
    involved: &HashSet<usize>,
    cand_all: &[[f64; 2]],
    up_all: &[[f64; 2]],
) -> ClearancePrimitives {
    let mut fixed_curves: Vec<Vec<[f64; 2]>> = Vec::new();
    for idx in quads {
        if idx.iter().any(|v| involved.contains(v))
            && idx.iter().any(|v| cand_all[*v] != up_all[*v])
        {
            continue;
        }
        fixed_curves.push(vec![cand_all[idx[0]], cand_all[idx[1]], cand_all[idx[2]]]);
    }
    let mut fixed_lines: Vec<ClearanceLine> = Vec::new();
    let mut moved_lines: Vec<(ClearanceLine, ClearanceLine)> = Vec::new();
    for contour in &raw.contours {
        for seg in contour {
            if let GeomSegment::Line { a, b } = *seg {
                let old = (up_all[a], up_all[b]);
                let new = (cand_all[a], cand_all[b]);
                if old == new {
                    fixed_lines.push(old);
                } else {
                    moved_lines.push((old, new));
                }
            }
        }
    }
    ClearancePrimitives {
        fixed_curves,
        fixed_lines,
        moved_lines,
    }
}

#[allow(clippy::too_many_arguments)]
fn deliver(
    raw: &SourceOutline,
    raw_topology: &curves::PreparedSubstitution<'_>,
    captured: &geometry::Parsed,
    fitted: &geometry::Parsed,
    upstream: &[FittedCommand],
    size_px: f64,
    prepared: &[geometry::PreppedPair],
    skipped: &[geometry::Skipped],
    waist: Waist,
    rel_med: f64,
    target: f64,
    matches: &[(Side, Side, f64)],
    quantized_zero: Vec<usize>,
    raw_crosses: Vec<serde_json::Value>,
    base_all: &[[f64; 2]],
    up_all: &[[f64; 2]],
    cols: Vec<usize>,
    weld: HashMap<usize, usize>,
    delta: Vec<f64>,
    qp_info: qp::QpInfo,
    radius: f64,
    bound: f64,
    kept_hard: Vec<(Vec<f64>, f64)>,
    gates: Vec<JointGate>,
    quads: Vec<[usize; 3]>,
    involved: HashSet<usize>,
) -> Result<FitResult, Error> {
    let no = raw.oncurve.len();
    let skipped_json = || -> Vec<serde_json::Value> {
        skipped
            .iter()
            .map(|s| serde_json::json!({"pair": [s.pair.0, s.pair.1], "reason": s.reason}))
            .collect()
    };
    let waist_json =
        || serde_json::json!({"width": waist.width, "mid": waist.mid, "level": waist.level});
    let cols_set: HashSet<usize> = cols.iter().copied().collect();
    // Rounded candidate: upstream X plus the solved step, weld-closed.
    let mut raw_new: Vec<[f64; 2]> = up_all.to_vec();
    for (k, v) in cols.iter().enumerate() {
        raw_new[*v][0] += delta[k];
    }
    for (dup, canon) in &weld {
        raw_new[*dup] = raw_new[*canon];
    }
    let mut cand_all: Vec<[f64; 2]> = raw_new.clone();
    for v in &cols {
        cand_all[*v][0] = round_26_6(cand_all[*v][0]);
    }
    for (dup, canon) in &weld {
        cand_all[*dup] = cand_all[*canon];
    }
    let movement: f64 = cand_all
        .iter()
        .zip(up_all.iter())
        .map(|(c, u)| sub(*c, *u))
        .map(norm)
        .fold(0.0, f64::max);
    if !(movement <= radius) {
        return Ok(abstain(
            upstream,
            "rounded-movement-budget",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
                "waist": waist_json(),
                "movement": movement,
                "bound": bound,
                "radius": radius,
            }),
        ));
    }
    let (hard_ok, hard_checks) =
        rounded_hard_checks(&cols, &kept_hard, &raw_new, &cand_all, up_all);
    if !hard_ok {
        return Ok(abstain(
            upstream,
            "rounded-hard-constraint",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
                "waist": waist_json(),
                "hard_checks": hard_checks,
            }),
        ));
    }
    let (joints_ok, continuity) =
        rounded_joint_checks(&gates, &raw_new, &cand_all, up_all, base_all);
    if !joints_ok {
        return Ok(abstain(
            upstream,
            "joint-continuity",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
                "waist": waist_json(),
                "continuity": continuity,
            }),
        ));
    }
    // Source curvature and forward tangent over whole intervals.
    for idx in &quads {
        if !idx.iter().any(|v| involved.contains(v)) {
            continue;
        }
        let src = [base_all[idx[0]], base_all[idx[1]], base_all[idx[2]]];
        let cand = [cand_all[idx[0]], cand_all[idx[1]], cand_all[idx[2]]];
        if let Err(why) = quad_interval_ok(&src, &cand) {
            return Ok(abstain(
                upstream,
                &format!("curve-{why}"),
                serde_json::json!({
                    "size_px": size_px,
                    "skipped": skipped_json(),
                    "waist": waist_json(),
                    "curve_indices": idx,
                }),
            ));
        }
    }
    // Delivery clearance: station disks clear every fixed primitive and
    // swept moved lines clear every fixed curve.
    let cand_on: Vec<[f64; 2]>;
    {
        let ClearancePrimitives {
            fixed_curves,
            fixed_lines,
            moved_lines,
        } = collect_clearance_primitives(raw, &quads, &involved, &cand_all, up_all);
        // Candidate oncurve shares the raw vertex order.
        cand_on = cand_all[..no].to_vec();
        for info in prepared {
            for st in &info.stations {
                let qa = geometry::edge_point(&info.a, st.hit.sa, &cand_on);
                let qb = geometry::edge_point(&info.b, st.hit.sb, &cand_on);
                let center = [(qa[0] + qb[0]) / 2.0, (qa[1] + qb[1]) / 2.0];
                let radius_st = norm(sub(qb, qa)) / 2.0;
                for fix in &fixed_curves {
                    if !curves::disk_clear(center, radius_st, fix).0 {
                        return Ok(abstain(
                            upstream,
                            "clearance-station-disk-curve",
                            serde_json::json!({
                                "size_px": size_px,
                                "skipped": skipped_json(),
                                "waist": waist_json(),
                            }),
                        ));
                    }
                }
                for line in &fixed_lines {
                    if !seg_open_clear(center, radius_st, *line) {
                        return Ok(abstain(
                            upstream,
                            "clearance-station-disk-line",
                            serde_json::json!({
                                "size_px": size_px,
                                "skipped": skipped_json(),
                                "waist": waist_json(),
                            }),
                        ));
                    }
                }
            }
        }
        let olds: Vec<((f64, f64), (f64, f64))> = moved_lines
            .iter()
            .map(|(o, _)| ((o.0[0], o.0[1]), (o.1[0], o.1[1])))
            .collect();
        let news: Vec<((f64, f64), (f64, f64))> = moved_lines
            .iter()
            .map(|(_, n)| ((n.0[0], n.0[1]), (n.1[0], n.1[1])))
            .collect();
        if !olds.is_empty() {
            let (ok, _) = curves::movement_clear(&olds, &news, &fixed_curves);
            if !ok {
                return Ok(abstain(
                    upstream,
                    "clearance-swept-fixed-curve",
                    serde_json::json!({
                        "size_px": size_px,
                        "skipped": skipped_json(),
                        "waist": waist_json(),
                    }),
                ));
            }
        }
    }
    // Y and cap preservation: the solve moves X only.
    if cand_all
        .iter()
        .zip(up_all.iter())
        .any(|(c, u)| c[1] != u[1])
    {
        return Ok(abstain(
            upstream,
            "y-changed",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
                "waist": waist_json(),
            }),
        ));
    }
    let cap_up = up_all
        .iter()
        .map(|p| p[1])
        .fold(f64::NEG_INFINITY, f64::max);
    let cap_cand = cand_all
        .iter()
        .map(|p| p[1])
        .fold(f64::NEG_INFINITY, f64::max);
    if cap_cand != cap_up {
        return Ok(abstain(
            upstream,
            "cap-changed",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
                "waist": waist_json(),
            }),
        ));
    }
    // Emit X-only commands preserving ops and order.
    let onmap = geometry::index_map(upstream);
    let mut offmap: Vec<usize> = Vec::new();
    for (pos, cmd) in upstream.iter().enumerate() {
        match cmd {
            FittedCommand::QuadTo(..) => offmap.push(pos),
            FittedCommand::CurveTo(..) => {
                offmap.push(pos);
                offmap.push(pos);
            }
            _ => {}
        }
    }
    let mut candidate = upstream.to_vec();
    let mut order: Vec<usize> = cols_set.iter().copied().collect();
    for dup in weld.keys() {
        if !cols_set.contains(dup) {
            order.push(*dup);
        }
    }
    order.sort();
    for v in order {
        let src = *weld.get(&v).unwrap_or(&v);
        if !cols_set.contains(&src) {
            continue;
        }
        let new_x = cand_all[src][0];
        if new_x == up_all[v][0] {
            continue;
        }
        let new_f = new_x as f32;
        if v < no {
            let Some(pos) = onmap[v] else {
                continue;
            };
            match &mut candidate[pos] {
                FittedCommand::MoveTo(x, _) | FittedCommand::LineTo(x, _) => *x = new_f,
                FittedCommand::QuadTo(_, _, x, _) => *x = new_f,
                FittedCommand::CurveTo(..) | FittedCommand::Close => {}
            }
        } else {
            let fi = v - no;
            if fi >= offmap.len() {
                continue;
            }
            let pos = offmap[fi];
            if let FittedCommand::QuadTo(x1, _, _, _) = &mut candidate[pos] {
                *x1 = new_f;
            }
        }
    }
    if candidate == upstream {
        return Ok(abstain(
            upstream,
            "no-movement",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
                "waist": waist_json(),
            }),
        ));
    }
    // Exact substituted topology on raw and captured outlines.
    let Ok(cand_parsed) = geometry::parse_commands(&candidate) else {
        return Ok(abstain(
            upstream,
            "topology",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
                "waist": waist_json(),
            }),
        ));
    };
    let fitted_topology = curves::PreparedSubstitution::new(fitted);
    let candidate_topology = curves::PreparedSubstitution::new(&cand_parsed);
    if !curves::compare_prepared(raw_topology, &fitted_topology, &candidate_topology) {
        return Ok(abstain(
            upstream,
            "topology",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
                "waist": waist_json(),
            }),
        ));
    }
    if !curves::compare_prepared(
        &curves::PreparedSubstitution::new(captured),
        &fitted_topology,
        &candidate_topology,
    ) {
        return Ok(abstain(
            upstream,
            "topology-captured",
            serde_json::json!({
                "size_px": size_px,
                "skipped": skipped_json(),
                "waist": waist_json(),
            }),
        ));
    }
    // Arm widths, phase and delivery evidence.
    let cand_pts: &[[f64; 2]] = &cand_parsed.oncurve;
    let mut pairs_json: Vec<serde_json::Value> = Vec::new();
    let mut arms: std::collections::HashMap<&str, (f64, f64)> = std::collections::HashMap::new();
    for info in prepared {
        let mut got = Vec::with_capacity(info.stations.len());
        for st in &info.stations {
            let qa = geometry::edge_point(&info.a, st.hit.sa, cand_pts);
            let qb = geometry::edge_point(&info.b, st.hit.sb, cand_pts);
            got.push(((qb[0] - qa[0]) * info.normal[0] + (qb[1] - qa[1]) * info.normal[1]).abs());
        }
        let arm = arm_of(info.normal);
        let src_mean = info.src_widths.iter().sum::<f64>() / info.src_widths.len() as f64;
        let up_mean = info.fit_widths.iter().sum::<f64>() / info.fit_widths.len() as f64;
        let cand_mean = got.iter().sum::<f64>() / got.len() as f64;
        pairs_json.push(serde_json::json!({
            "id": info.id,
            "arm": arm,
            "source_width": src_mean,
            "upstream_width": up_mean,
            "candidate_width": cand_mean,
        }));
        let entry = arms.entry(arm).or_insert((0.0, 0.0));
        entry.0 += src_mean;
        entry.1 += cand_mean;
    }
    let mut arms_json = serde_json::Map::new();
    for (arm, (src_sum, cand_sum)) in &arms {
        let count = pairs_json
            .iter()
            .filter(|p| p["arm"] == *arm)
            .count()
            .max(1) as f64;
        arms_json.insert(
            arm.to_string(),
            serde_json::json!({
                "source": src_sum / count,
                "candidate": cand_sum / count,
            }),
        );
    }
    // Source mismatch of the reflection about the parity axis.
    let mut mismatch = 0.0;
    for (first, second, _) in matches {
        mismatch += (base_all[first.i0][0]
            + base_all[first.i1][0]
            + base_all[second.i0][0]
            + base_all[second.i1][0])
            / 4.0
            - waist.mid;
    }
    mismatch /= matches.len() as f64;
    let phase = |pts: &[[f64; 2]]| -> f64 {
        matches
            .iter()
            .map(|(first, second, _)| {
                (pts[first.i0][0] + pts[first.i1][0] + pts[second.i0][0] + pts[second.i1][0]) / 4.0
            })
            .sum::<f64>()
            / matches.len() as f64
    };
    let phase_cand = phase(&cand_all);
    let phase_up = phase(up_all);
    Ok(FitResult {
        commands: candidate,
        applied: true,
        reason: "applied-curved-crossing".to_string(),
        diagnostics: serde_json::json!({
            "waist": waist_json(),
            "parity_target": target,
            "rel_median": rel_med,
            "quantized_zero_curves": quantized_zero,
            "raw_crosses": raw_crosses,
            "pairs": pairs_json,
            "arms": arms_json,
            "skipped": skipped_json(),
            "movement": movement,
            "bound": bound,
            "radius": radius,
            "hard_checks": hard_checks,
            "continuity": continuity,
            "matches": matches.len(),
            "phase_mid_cand": phase_cand,
            "phase_mid_up": phase_up,
            "phase_residual": phase_cand - (target + mismatch),
            "certificate": "compare-substituted",
            "qp": {
                "iterations": qp_info.iterations,
                "equality_error": qp_info.equality_error,
                "stationarity_error": qp_info.stationarity_error,
                "inequality_slack": qp_info.inequality_slack,
                "active": qp_info.active,
            },
            "size_px": size_px,
        }),
    })
}

#[cfg(test)]
mod ownership_tests {
    use super::*;
    use geometry::{Portion, PreppedPair};

    fn prep(a0: usize, a1: usize, b0: usize, b1: usize, pts: &[[f64; 2]]) -> PreppedPair {
        let side = |i0: usize, i1: usize| Portion {
            contour: 0,
            seg: 0,
            t0: 0.0,
            t1: 1.0,
            p0: pts[i0],
            p1: pts[i1],
            i0,
            i1,
            hidden: false,
            unknown: false,
        };
        PreppedPair {
            id: String::from("t"),
            a: side(a0, a1),
            b: side(b0, b1),
            normal: [0.0, 1.0],
            stations: Vec::new(),
            src_widths: Vec::new(),
            fit_widths: Vec::new(),
            arc: 0.0,
            span_lo: 0.0,
            span_hi: 0.0,
        }
    }

    fn parsed(
        oncurve: Vec<[f64; 2]>,
        offcurve: Vec<[f64; 2]>,
        contours: Vec<Vec<GeomSegment>>,
    ) -> SourceOutline {
        SourceOutline {
            oncurve,
            offcurve,
            contours,
        }
    }

    fn sorted(set: &HashSet<usize>) -> Vec<usize> {
        let mut out: Vec<usize> = set.iter().copied().collect();
        out.sort();
        out
    }

    #[test]
    fn transitive_quad_closure_through_alias_needs_fixpoint() {
        let pts: Vec<[f64; 2]> = vec![
            [0.0, 0.0],
            [1.0, 0.0],
            [2.0, 0.0],
            [3.0, 0.0],
            [2.0, 0.0],
            [9.0, 9.0],
            [10.0, 10.0],
        ];
        let raw = parsed(
            pts.clone(),
            vec![[1.5, 1.0], [2.5, 1.0], [9.5, 10.0]],
            vec![
                vec![
                    GeomSegment::Quad { c: 1, a: 2, b: 3 },
                    GeomSegment::Line { a: 3, b: 0 },
                    GeomSegment::Line { a: 0, b: 1 },
                    GeomSegment::Quad { c: 0, a: 1, b: 4 },
                    GeomSegment::Line { a: 4, b: 2 },
                ],
                vec![
                    GeomSegment::Quad { c: 2, a: 5, b: 6 },
                    GeomSegment::Line { a: 6, b: 5 },
                ],
            ],
        );
        let base: Vec<[f64; 2]> = raw.oncurve.clone();
        let weld = weld_map(&raw.contours, &base);
        assert_eq!(weld, HashMap::from([(4, 2)]));
        let quads = quadratic_indices(&raw);
        assert_eq!(quads, vec![[2, 8, 3], [1, 7, 4], [5, 9, 6]]);
        let prepared = vec![prep(0, 1, 0, 1, &pts)];
        assert_eq!(
            sorted(&involved_closure(&prepared, &quads, &weld)),
            vec![0, 1, 2, 3, 4, 7, 8]
        );
    }

    #[test]
    fn alias_expansion_runs_dup_to_canon_only() {
        let pts: Vec<[f64; 2]> = vec![
            [0.0, 0.0],
            [1.0, 0.0],
            [2.0, 0.0],
            [3.0, 0.0],
            [2.0, 0.0],
            [5.0, 0.0],
        ];
        let weld: HashMap<usize, usize> = HashMap::from([(4, 2)]);
        let no_quads: Vec<[usize; 3]> = Vec::new();
        let canon_seed = involved_closure(&[prep(2, 3, 2, 3, &pts)], &no_quads, &weld);
        assert_eq!(sorted(&canon_seed), vec![2, 3]);
        let chain: Vec<[usize; 3]> = vec![[4, 6, 5]];
        let dup_seed = involved_closure(&[prep(5, 3, 5, 3, &pts)], &chain, &weld);
        assert_eq!(sorted(&dup_seed), vec![2, 3, 4, 5, 6]);
    }

    #[test]
    fn free_columns_keep_canonical_drop_aliases_sorted() {
        let raw = parsed(
            vec![
                [0.0, 0.0],
                [1.0, 0.0],
                [2.0, 0.0],
                [3.0, 1.0],
                [2.0, 0.0],
                [5.0, 0.0],
            ],
            Vec::new(),
            vec![vec![
                GeomSegment::Line { a: 2, b: 3 },
                GeomSegment::Line { a: 3, b: 5 },
                GeomSegment::Line { a: 5, b: 4 },
                GeomSegment::Line { a: 4, b: 2 },
            ]],
        );
        let base_all: Vec<[f64; 2]> = raw.oncurve.clone();
        let ownership = ControlOwnership::prepare(
            &raw,
            &raw,
            &base_all,
            &base_all,
            &[prep(2, 5, 3, 4, &base_all)],
        )
        .ok()
        .expect("aliased columns must prepare");
        assert_eq!(ownership.weld, HashMap::from([(4, 2)]));
        assert_eq!(sorted(&ownership.involved), vec![2, 3, 4, 5]);
        assert_eq!(ownership.cols, vec![2, 3, 5]);
    }

    #[test]
    fn upright_pins_endpoints_canon_alias_and_skips_near_misses() {
        let raw = parsed(
            vec![
                [2.0, 0.0],
                [9.0, 9.0],
                [9.0, 9.0],
                [2.0, 0.0],
                [2.0, 3.0],
                [9.0, 9.0],
                [3.0, 0.0],
                [3.5, 2.0],
                [4.0, 0.0],
                [4.0 + 1e-9, 2.0],
                [5.0, 5.0],
                [5.0, 5.0],
            ],
            Vec::new(),
            vec![
                vec![
                    GeomSegment::Line { a: 0, b: 1 },
                    GeomSegment::Line { a: 1, b: 4 },
                    GeomSegment::Line { a: 4, b: 3 },
                    GeomSegment::Line { a: 3, b: 0 },
                ],
                vec![GeomSegment::Line { a: 6, b: 7 }],
                vec![GeomSegment::Line { a: 8, b: 9 }],
                vec![GeomSegment::Line { a: 10, b: 11 }],
            ],
        );
        let base: Vec<[f64; 2]> = raw.oncurve.clone();
        let weld = weld_map(&raw.contours, &base);
        assert_eq!(weld, HashMap::from([(3, 0)]));
        assert_eq!(sorted(&upright_controls(&raw, &base, &weld)), vec![0, 3, 4]);
    }

    #[test]
    fn slanted_raw_beats_vertical_fitted() {
        let raw = parsed(
            vec![[0.0, 0.0], [0.0, 2.0], [3.0, 0.0], [3.5, 2.0]],
            Vec::new(),
            vec![vec![GeomSegment::Line { a: 2, b: 3 }]],
        );
        let fitted = parsed(
            vec![[0.0, 0.0], [0.0, 2.0], [3.0, 0.0], [3.0, 2.0]],
            Vec::new(),
            vec![vec![GeomSegment::Line { a: 2, b: 3 }]],
        );
        let base_all: Vec<[f64; 2]> = raw.oncurve.clone();
        let up_all: Vec<[f64; 2]> = fitted.oncurve.clone();
        let ownership = ControlOwnership::prepare(
            &raw,
            &fitted,
            &base_all,
            &up_all,
            &[prep(2, 3, 2, 3, &base_all)],
        )
        .ok()
        .expect("slanted raw must prepare");
        assert_eq!(ownership.weld, HashMap::new());
        assert_eq!(ownership.quads, Vec::<[usize; 3]>::new());
        assert_eq!(sorted(&ownership.involved), vec![2, 3]);
        assert_eq!(ownership.cols, vec![2, 3]);
    }

    #[test]
    fn weld_mismatch_orders_before_no_free_controls() {
        let base: Vec<[f64; 2]> = vec![[0.0, 0.0], [0.0, 2.0], [0.0, 0.0]];
        let closed = vec![
            GeomSegment::Line { a: 0, b: 1 },
            GeomSegment::Line { a: 1, b: 2 },
            GeomSegment::Line { a: 2, b: 0 },
        ];
        let raw = parsed(base.clone(), Vec::new(), vec![closed.clone()]);
        let fitted = parsed(base.clone(), Vec::new(), vec![closed]);
        assert_eq!(
            compatible_welds(&raw, &fitted, &base, &base).ok(),
            Some(HashMap::from([(2, 0)]))
        );
        let open = vec![
            GeomSegment::Line { a: 0, b: 1 },
            GeomSegment::Line { a: 1, b: 2 },
        ];
        let open_fitted = parsed(base.clone(), Vec::new(), vec![open.clone()]);
        assert!(matches!(
            compatible_welds(&raw, &open_fitted, &base, &base),
            Err(OwnershipAbort::WeldMismatch)
        ));
        let open_raw = parsed(base.clone(), Vec::new(), vec![open]);
        assert!(matches!(
            compatible_welds(&open_raw, &fitted, &base, &base),
            Err(OwnershipAbort::WeldMismatch)
        ));
        assert!(matches!(
            ControlOwnership::prepare(&raw, &open_fitted, &base, &base, &[prep(0, 1, 0, 1, &base)]),
            Err(OwnershipAbort::WeldMismatch)
        ));
        let pinned = parsed(
            vec![[0.0, 0.0], [0.0, 2.0]],
            Vec::new(),
            vec![vec![GeomSegment::Line { a: 0, b: 1 }]],
        );
        let pinned_base: Vec<[f64; 2]> = pinned.oncurve.clone();
        assert!(matches!(
            ControlOwnership::prepare(
                &pinned,
                &pinned,
                &pinned_base,
                &pinned_base,
                &[prep(0, 1, 0, 1, &pinned_base)]
            ),
            Err(OwnershipAbort::NoFreeControls)
        ));
        let mixed = parsed(
            vec![[0.0, 0.0], [0.0, 2.0], [5.0, 0.0], [6.0, 3.0]],
            Vec::new(),
            vec![vec![
                GeomSegment::Line { a: 0, b: 1 },
                GeomSegment::Line { a: 2, b: 3 },
            ]],
        );
        let mixed_base: Vec<[f64; 2]> = mixed.oncurve.clone();
        let ownership = ControlOwnership::prepare(
            &mixed,
            &mixed,
            &mixed_base,
            &mixed_base,
            &[prep(0, 1, 2, 3, &mixed_base)],
        )
        .ok()
        .expect("mixed ownership must prepare");
        assert_eq!(sorted(&ownership.involved), vec![0, 1, 2, 3]);
        assert_eq!(ownership.cols, vec![2, 3]);
    }
}

#[cfg(test)]
mod objective_tests;

#[cfg(test)]
mod joint_tests;

#[cfg(test)]
mod quadratic_tests;

#[cfg(test)]
mod sharp_joint_tests;

#[cfg(test)]
mod hard_check_tests;

#[cfg(test)]
mod continuity_tests;

#[cfg(test)]
mod clearance_primitive_tests;
