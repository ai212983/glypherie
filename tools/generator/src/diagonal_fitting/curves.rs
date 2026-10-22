//! Certified curve clearance and exact-join comparison (native port).
//!
//! Source: `experiments/hobby_fitting/curve_clearance.py` (substitution
//! theorem in its module docstring; [Shene's convex-hull/subdivision
//! construction](https://pages.mtu.edu/~shene/COURSES/cs3621/NOTES/spline/bezier-construct.html)).
//! Project adaptation: sufficient certificate only — chord-monotone pieces
//! whose hulls meet every other boundary hull solely at incident shared
//! junctions may be replaced by joint polylines; uncertified contact,
//! loops, degenerate pieces and inexact joints fail closed. Curve fitting
//! uses a separate substitution gate for moving controls; the width-only
//! gate still requires identical upstream/candidate curves. Runtime never uses experiments, Python,
//! subprocesses or corpus data. All predicates are exact `Exact` lifts
//! of finite coordinates (never resnapped, no denominator limit).

use super::{exact::Exact as BigRational, filtered, topology};
use crate::probe::FittedCommand;

/// Exact `f32`-bit lift, never resnapped.
pub type Pt = [f64; 2];

/// Exact point as a rational pair.
type Rat = (BigRational, BigRational);

const DISK_DEPTH: usize = 8;
const SWEEP_DEPTH: usize = 4;

fn zero() -> BigRational {
    BigRational::zero()
}

fn two() -> BigRational {
    BigRational::integer(2)
}

/// Exact lift of one finite coordinate pair; non-finite fails closed.
fn lift(p: &[f64; 2]) -> Option<Rat> {
    Some((BigRational::from_f64(p[0])?, BigRational::from_f64(p[1])?))
}

/// Exact lift of `f32` command coordinates (`f32 as f64` is exact).
fn lift32(x: f32, y: f32) -> Option<Rat> {
    if !x.is_finite() || !y.is_finite() {
        return None;
    }
    lift(&[x as f64, y as f64])
}

/// True only when the rational is exactly representable as `f64`.
fn exact_f64(r: &BigRational) -> Option<f64> {
    let f = r.to_f64()?;
    if !f.is_finite() {
        return None;
    }
    if BigRational::from_f64(f).as_ref() == Some(r) {
        Some(f)
    } else {
        None
    }
}

/// Exact orientation sign of (a, b, c): +1, -1, or 0; the independent
/// test reference used by every exact narrow phase below.
fn orient_exact(a: &Rat, b: &Rat, c: &Rat) -> i8 {
    let v = (&b.0 - &a.0) * (&c.1 - &a.1) - (&b.1 - &a.1) * (&c.0 - &a.0);
    if v.is_zero() {
        0
    } else if v.is_positive() {
        1
    } else {
        -1
    }
}

/// Exact cross product; the certified filter's fallback.
fn cross_exact(o: &Rat, a: &Rat, b: &Rat) -> BigRational {
    (&a.0 - &o.0) * (&b.1 - &o.1) - (&a.1 - &o.1) * (&b.0 - &o.0)
}

/// Exact cross sign with no filtering: test reference.
fn cross_sign_exact(o: &Rat, a: &Rat, b: &Rat) -> i8 {
    let v = cross_exact(o, a, b);
    if v.is_zero() {
        0
    } else if v.is_positive() {
        1
    } else {
        -1
    }
}

/// Filter-first cross sign for the hull loop: decisive interval sign,
/// else exact.
fn cross_sign(o: &Rat, a: &Rat, b: &Rat) -> i8 {
    if let Some(s) = filtered::orient_sign((&o.0, &o.1), (&a.0, &a.1), (&b.0, &b.1)) {
        return s;
    }
    cross_sign_exact(o, a, b)
}

fn midpoint(a: &Rat, b: &Rat) -> Rat {
    ((&a.0 + &b.0) / two(), (&a.1 + &b.1) / two())
}

/// Monotone-chain hull over exact rationals; collinear interiors drop.
fn convex_hull(points: &[Rat]) -> Vec<Rat> {
    let mut pts: Vec<Rat> = points.to_vec();
    pts.sort();
    pts.dedup();
    if pts.len() <= 2 {
        return pts;
    }
    let mut lower: Vec<Rat> = Vec::new();
    for p in &pts {
        while lower.len() >= 2
            && cross_sign(&lower[lower.len() - 2], &lower[lower.len() - 1], p) <= 0
        {
            lower.pop();
        }
        lower.push(p.clone());
    }
    let mut upper: Vec<Rat> = Vec::new();
    for p in pts.iter().rev() {
        while upper.len() >= 2
            && cross_sign(&upper[upper.len() - 2], &upper[upper.len() - 1], p) <= 0
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

/// Exact hull with no filtering: test reference.
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
            && cross_sign_exact(&lower[lower.len() - 2], &lower[lower.len() - 1], p) <= 0
        {
            lower.pop();
        }
        lower.push(p.clone());
    }
    let mut upper: Vec<Rat> = Vec::new();
    for p in pts.iter().rev() {
        while upper.len() >= 2
            && cross_sign_exact(&upper[upper.len() - 2], &upper[upper.len() - 1], p) <= 0
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

fn poly_edges(poly: &[Rat]) -> Vec<(Rat, Rat)> {
    if poly.len() < 2 {
        return Vec::new();
    }
    (0..poly.len())
        .map(|i| (poly[i].clone(), poly[(i + 1) % poly.len()].clone()))
        .collect()
}

/// True only with a strict separating-axis gap; touch fails closed.
/// A decided exact/filter verdict returns at once; otherwise the general
/// rational narrow phase runs unchanged.
fn strictly_disjoint(poly_p: &[Rat], poly_q: &[Rat]) -> bool {
    if let Some(verdict) = filtered::polys_strictly_disjoint(poly_p, poly_q) {
        return verdict;
    }
    strictly_disjoint_exact(poly_p, poly_q)
}

/// Exact narrow phase; the certified filter's fallback.
fn strictly_disjoint_exact(poly_p: &[Rat], poly_q: &[Rat]) -> bool {
    let mut axes: Vec<Rat> = Vec::new();
    for poly in [poly_p, poly_q] {
        for (a, b) in poly_edges(poly) {
            let n = (&a.1 - &b.1, &b.0 - &a.0);
            if n.0.is_zero() && n.1.is_zero() {
                continue;
            }
            axes.push(n);
        }
    }
    if axes.is_empty() {
        return false;
    }
    let proj = |p: &Rat, n: &Rat| &p.0 * &n.0 + &p.1 * &n.1;
    for n in &axes {
        let mut ps: Vec<BigRational> = poly_p.iter().map(|p| proj(p, n)).collect();
        let mut qs: Vec<BigRational> = poly_q.iter().map(|p| proj(p, n)).collect();
        ps.sort();
        qs.sort();
        if ps.last().unwrap() < qs.first().unwrap() || qs.last().unwrap() < ps.first().unwrap() {
            return true;
        }
    }
    false
}

/// One exact de Casteljau step at t=1/2; returns (left, right).
fn subdivide(ctrls: &[Rat]) -> (Vec<Rat>, Vec<Rat>) {
    let mut level: Vec<Rat> = ctrls.to_vec();
    let mut left = vec![level[0].clone()];
    let mut right = vec![level[level.len() - 1].clone()];
    while level.len() > 1 {
        level = level.windows(2).map(|w| midpoint(&w[0], &w[1])).collect();
        left.push(level[0].clone());
        right.push(level[level.len() - 1].clone());
    }
    right.reverse();
    (left, right)
}

/// Exact dyadic control chains of the 2**depth sub-pieces.
fn piece_chains(ctrls: &[Rat], depth: usize) -> Vec<Vec<Rat>> {
    let mut pieces = vec![ctrls.to_vec()];
    for _ in 0..depth {
        let mut halves = Vec::with_capacity(2 * pieces.len());
        for piece in &pieces {
            let (left, right) = subdivide(piece);
            halves.push(left);
            halves.push(right);
        }
        pieces = halves;
    }
    pieces
}

/// Control hulls of the 2**depth dyadic sub-pieces.
fn piece_hulls(ctrls: &[Rat], depth: usize) -> Vec<Vec<Rat>> {
    piece_chains(ctrls, depth)
        .iter()
        .map(|piece| convex_hull(piece))
        .collect()
}

/// Exact on-segment test with no filtering: test reference.
fn on_segment_exact(a: &Rat, b: &Rat, p: &Rat) -> bool {
    use std::cmp::{max, min};
    orient_exact(a, b, p) == 0
        && min(&a.0, &b.0) <= &p.0
        && &p.0 <= max(&a.0, &b.0)
        && min(&a.1, &b.1) <= &p.1
        && &p.1 <= max(&a.1, &b.1)
}

/// Exact outside test with no filtering: test reference.
fn strictly_outside_exact(pt: &Rat, poly: &[Rat]) -> bool {
    if poly.is_empty() {
        return true;
    }
    if poly.len() == 1 {
        return pt != &poly[0];
    }
    if poly.len() == 2 {
        let (a, b) = (&poly[0], &poly[1]);
        return !(pt == a || pt == b || on_segment_exact(a, b, pt));
    }
    let ccw = orient_exact(&poly[0], &poly[1], &poly[2]) > 0;
    for i in 1..poly.len() - 1 {
        let (t0, t1, t2) = (&poly[0], &poly[i], &poly[i + 1]);
        let (s0, s1, s2) = (
            orient_exact(t0, t1, pt),
            orient_exact(t1, t2, pt),
            orient_exact(t2, t0, pt),
        );
        if ccw && s0 >= 0 && s1 >= 0 && s2 >= 0 {
            return false;
        }
        if !ccw && s0 <= 0 && s1 <= 0 && s2 <= 0 {
            return false;
        }
    }
    true
}

/// Exact certificate that convex hulls intersect at most at `shared`.
///
/// No proper edge crossing; every segment contact point is exactly the
/// shared junction (collinear opposite-ray tangency allowed); no vertex
/// of either hull lies inside or on the other hull except the junction.
/// Filter-first: a proven interval verdict returns at once, else the
/// exact narrow phase below runs unchanged.
fn hulls_meet_only_at(poly_p: &[Rat], poly_q: &[Rat], shared: &Rat) -> bool {
    if let Some(v) = filtered::hulls_meet_only_at(poly_p, poly_q, shared) {
        return v;
    }
    hulls_meet_only_at_exact(poly_p, poly_q, shared)
}

/// Exact narrow phase with no filtering: the certified filter's fallback
/// and the independent test reference.
fn hulls_meet_only_at_exact(poly_p: &[Rat], poly_q: &[Rat], shared: &Rat) -> bool {
    for (a, b) in poly_edges(poly_p) {
        for (c, d) in poly_edges(poly_q) {
            let (o1, o2, o3, o4) = (
                orient_exact(&a, &b, &c),
                orient_exact(&a, &b, &d),
                orient_exact(&c, &d, &a),
                orient_exact(&c, &d, &b),
            );
            if o1 * o2 < 0 && o3 * o4 < 0 {
                return false;
            }
            for (p, u, v) in [(&c, &a, &b), (&d, &a, &b), (&a, &c, &d), (&b, &c, &d)] {
                if on_segment_exact(u, v, p) && p != shared {
                    return false;
                }
            }
        }
    }
    if !poly_p
        .iter()
        .filter(|v| *v != shared)
        .all(|v| strictly_outside_exact(v, poly_q))
    {
        return false;
    }
    poly_q
        .iter()
        .filter(|v| *v != shared)
        .all(|v| strictly_outside_exact(v, poly_p))
}

/// Strictly positive projection of every control leg on the chord.
///
/// The derivative is a positive Bernstein combination of the legs, so the
/// arc projection is strictly increasing: the piece is a graph over its
/// chord axis, hence simple. A graph may still cross its chord. Zero
/// chord or any non-positive leg projection fails closed. Filter-first:
/// a proven interval verdict returns at once, else exact runs.
/// Unprepared chord verdict used by tests without a prepared `Entry`:
/// same filter-first path with bounds enclosed on the fly.
#[cfg(test)]
fn is_chord_monotone(ctrls: &[Rat]) -> bool {
    chord_monotone_cached(ctrls, None)
}

/// Exact predicate; the certified filter's fallback.
fn is_chord_monotone_exact(ctrls: &[Rat]) -> bool {
    if ctrls.len() < 2 {
        return false;
    }
    let chord = (
        ctrls[ctrls.len() - 1].0.clone() - &ctrls[0].0,
        ctrls[ctrls.len() - 1].1.clone() - &ctrls[0].1,
    );
    if chord.0.is_zero() && chord.1.is_zero() {
        return false;
    }
    ctrls
        .windows(2)
        .all(|w| ((&w[1].0 - &w[0].0) * &chord.0 + (&w[1].1 - &w[0].1) * &chord.1).is_positive())
}

/// Exact open-disk predicate used by source-contact recognition.
///
/// Port of `curve_contacts._seg_clear` / `_quad_disk_clear`: the product
/// rule for quadratic Bernstein polynomials gives a quartic squared
/// distance. Nonnegative coefficients certify clearance, including
/// tangency; unresolved dyadic subdivision at depth 12 fails closed.
/// Keep the squared radius rational: adding the approximation shell and
/// squaring in floating point would change this exact input predicate.
pub(super) fn source_disk_clear(center: Pt, radius_squared: &BigRational, controls: &[Pt]) -> bool {
    if radius_squared.is_negative() || !matches!(controls.len(), 2 | 3) {
        return false;
    }
    let Some(center) = lift(&center) else {
        return false;
    };
    let Some(points): Option<Vec<Rat>> = controls
        .iter()
        .map(|p| {
            let p = lift(p)?;
            Some((p.0 - &center.0, p.1 - &center.1))
        })
        .collect()
    else {
        return false;
    };
    // Acceptance-only interval proof first (`points` are already
    // center-relative): a proven clearance returns at once, while
    // tangency, contact and indecision run the exact narrow phase below
    // with its finite-depth verdicts unchanged.
    if points.len() == 3 && filtered::source_quad_clear(radius_squared, &points) == Some(true) {
        return true;
    }
    source_disk_clear_native(&points, radius_squared)
}

/// Exact narrow phase with no filtering: the native core behind
/// `source_disk_clear`, kept under its established name as the
/// cross-module test reference. The independent `BigRational` oracle is
/// `source_disk_clear_oracle` (test-only, below).
#[cfg_attr(not(test), allow(dead_code))]
pub(super) fn source_disk_clear_exact(points: &[Rat], radius_squared: &BigRational) -> bool {
    source_disk_clear_native(points, radius_squared)
}

/// Exact narrow phase with no filtering: the native core. `points` are
/// center-relative rationals.
pub(super) fn source_disk_clear_native(points: &[Rat], radius_squared: &BigRational) -> bool {
    let dot = |a: &Rat, b: &Rat| &a.0 * &b.0 + &a.1 * &b.1;
    if points.len() == 2 {
        let (a, b) = (&points[0], &points[1]);
        let d = (&b.0 - &a.0, &b.1 - &a.1);
        let length_squared = dot(&d, &d);
        let projection = dot(a, &d);
        if length_squared.is_zero() || !projection.is_negative() {
            return dot(a, a) >= *radius_squared;
        }
        if projection <= -&length_squared {
            return dot(b, b) >= *radius_squared;
        }
        return dot(a, a) * &length_squared - &projection * &projection
            >= radius_squared * &length_squared;
    }
    fn visit(points: &[Rat], reach: &BigRational, depth: usize) -> bool {
        // Product rule for quadratic Bernstein polynomials: the squared
        // distance is quartic with Bernstein coefficients
        // `sum c2[i]*c2[j]*(pi.pj) / c4[k] - reach`. Scaling by the
        // positive c4[k] = [1, 4, 6, 4, 1] preserves the >=0/<0 verdicts
        // with exact +,-,* only, at the same depth-12 recursion.
        let c2: [i32; 3] = [1, 2, 1];
        let c4: [i32; 5] = [1, 4, 6, 4, 1];
        let mut all_nonneg = true;
        let mut all_neg = true;
        for k in 0..5 {
            let mut value = zero();
            for i in 0..3 {
                for j in 0..3 {
                    if i + j == k {
                        let product = &points[i].0 * &points[j].0 + &points[i].1 * &points[j].1;
                        value += product * BigRational::integer(i128::from(c2[i] * c2[j]));
                    }
                }
            }
            let scaled = value - BigRational::integer(i128::from(c4[k])) * reach;
            if scaled.is_negative() {
                all_nonneg = false;
            } else {
                all_neg = false;
            }
        }
        if all_nonneg {
            return true;
        }
        if all_neg || depth >= 12 {
            return false;
        }
        let (left, right) = subdivide(points);
        visit(&left, reach, depth + 1) && visit(&right, reach, depth + 1)
    }
    visit(points, radius_squared, 0)
}

/// Original `BigRational` narrow phase: independent test oracle for the
/// native core above (same Bernstein certificate, same depth-12
/// recursion, same tangency acceptance).
#[cfg(test)]
pub(super) fn source_disk_clear_oracle(
    points: &[(num_rational::BigRational, num_rational::BigRational)],
    radius_squared: &num_rational::BigRational,
) -> bool {
    use num_rational::BigRational as NumRat;
    use num_traits::{Signed, Zero};
    let dot = |a: &(NumRat, NumRat), b: &(NumRat, NumRat)| &a.0 * &b.0 + &a.1 * &b.1;
    if points.len() == 2 {
        let (a, b) = (&points[0], &points[1]);
        let d = (&b.0 - &a.0, &b.1 - &a.1);
        let length_squared = dot(&d, &d);
        let projection = dot(a, &d);
        if length_squared.is_zero() || !projection.is_negative() {
            return dot(a, a) >= *radius_squared;
        }
        if projection <= -&length_squared {
            return dot(b, b) >= *radius_squared;
        }
        return dot(a, a) * &length_squared - &projection * &projection
            >= radius_squared * &length_squared;
    }
    fn midpoint_o(a: &(NumRat, NumRat), b: &(NumRat, NumRat)) -> (NumRat, NumRat) {
        use num_rational::BigRational as NumRat;
        let two = NumRat::from_integer(2.into());
        ((&a.0 + &b.0) / &two, (&a.1 + &b.1) / &two)
    }
    fn subdivide_o(points: &[(NumRat, NumRat)]) -> (Vec<(NumRat, NumRat)>, Vec<(NumRat, NumRat)>) {
        let mut level: Vec<(NumRat, NumRat)> = points.to_vec();
        let mut left = vec![level[0].clone()];
        let mut right = vec![level[level.len() - 1].clone()];
        while level.len() > 1 {
            level = level.windows(2).map(|w| midpoint_o(&w[0], &w[1])).collect();
            left.push(level[0].clone());
            right.push(level[level.len() - 1].clone());
        }
        right.reverse();
        (left, right)
    }
    fn visit(points: &[(NumRat, NumRat)], reach: &NumRat, depth: usize) -> bool {
        use num_rational::BigRational as NumRat;
        use num_traits::{Signed, Zero};
        let c2 = [1, 2, 1];
        let c4 = [1, 4, 6, 4, 1];
        let coefficients: Vec<NumRat> = (0..5)
            .map(|k| {
                let mut value = NumRat::zero();
                for i in 0..3 {
                    for j in 0..3 {
                        if i + j == k {
                            let product = &points[i].0 * &points[j].0 + &points[i].1 * &points[j].1;
                            value += product * NumRat::new((c2[i] * c2[j]).into(), c4[k].into());
                        }
                    }
                }
                value - reach
            })
            .collect();
        if coefficients.iter().all(|c| !c.is_negative()) {
            return true;
        }
        if coefficients.iter().all(|c| c.is_negative()) || depth >= 12 {
            return false;
        }
        let (left, right) = subdivide_o(points);
        visit(&left, reach, depth + 1) && visit(&right, reach, depth + 1)
    }
    visit(points, radius_squared, 0)
}

/// Certify a station disk avoids a fixed curve.
///
/// Exact squared distance from the center to each sub-piece bbox
/// lower-bounds the true curve distance (curve in hull, hull in bbox);
/// a strict greater-than-radius-squared bound prunes the piece, else
/// exact de Casteljau subdivision recurses. Unresolved proximity at the
/// depth-8 budget fails closed.
pub fn disk_clear(center: Pt, radius: f64, controls: &[Pt]) -> (bool, &'static str) {
    if radius < 0.0 {
        return (false, "negative-radius");
    }
    let reach = match BigRational::from_f64(radius) {
        Some(r) => &r * &r,
        None => return (false, "malformed-curve"),
    };
    let point = match lift(&center) {
        Some(p) => p,
        None => return (false, "malformed-curve"),
    };
    if controls.is_empty() {
        return (false, "malformed-curve");
    }
    let mut ctrls = Vec::with_capacity(controls.len());
    for p in controls {
        match lift(p) {
            Some(q) => ctrls.push(q),
            None => return (false, "malformed-curve"),
        }
    }
    fn bbox_d2(chain: &[Rat], point: &Rat) -> BigRational {
        let (mut lo_x, mut hi_x) = (chain[0].0.clone(), chain[0].0.clone());
        let (mut lo_y, mut hi_y) = (chain[0].1.clone(), chain[0].1.clone());
        for p in &chain[1..] {
            if p.0 < lo_x {
                lo_x = p.0.clone();
            }
            if p.0 > hi_x {
                hi_x = p.0.clone();
            }
            if p.1 < lo_y {
                lo_y = p.1.clone();
            }
            if p.1 > hi_y {
                hi_y = p.1.clone();
            }
        }
        let dx = if lo_x <= point.0 && point.0 <= hi_x {
            zero()
        } else {
            (&point.0 - &lo_x).abs().min((&point.0 - &hi_x).abs())
        };
        let dy = if lo_y <= point.1 && point.1 <= hi_y {
            zero()
        } else {
            (&point.1 - &lo_y).abs().min((&point.1 - &hi_y).abs())
        };
        &dx * &dx + &dy * &dy
    }
    fn visit(chain: &[Rat], depth: usize, point: &Rat, reach: &BigRational) -> bool {
        if bbox_d2(chain, point) > *reach {
            return true;
        }
        if depth >= DISK_DEPTH {
            return false;
        }
        let (left, right) = subdivide(chain);
        visit(&left, depth + 1, point, reach) && visit(&right, depth + 1, point, reach)
    }
    if visit(&ctrls, 0, &point, &reach) {
        (true, "clear")
    } else {
        (false, "disk-too-close")
    }
}

/// Certify one straight sweep against one fixed curve.
///
/// The swept hull contains the linear homotopy of the straight edge.
/// Returns strict separation, or clearance when every intersecting
/// sub-hull meets the sweep solely at one pinned point that is an
/// endpoint of both segments and a curve endpoint, with the remaining
/// old/new rays strictly unreversed (exact dot > 0, so the ray neither
/// collapses nor flips during the homotopy). No tangent-side test: the
/// sweep certificate stands on its own. Anything else fails closed.
fn edge_vs_curve_clear(
    old: ((f64, f64), (f64, f64)),
    new: ((f64, f64), (f64, f64)),
    ctrls: &[Pt],
) -> (bool, &'static str) {
    let (Some(old0), Some(old1), Some(new0), Some(new1)) = (
        lift(&[old.0 .0, old.0 .1]),
        lift(&[old.1 .0, old.1 .1]),
        lift(&[new.0 .0, new.0 .1]),
        lift(&[new.1 .0, new.1 .1]),
    ) else {
        return (false, "curve-contact");
    };
    if ctrls.is_empty() {
        return (false, "curve-contact");
    }
    let mut pts = Vec::with_capacity(ctrls.len());
    for p in ctrls {
        match lift(p) {
            Some(q) => pts.push(q),
            None => return (false, "curve-contact"),
        }
    }
    let swept = convex_hull(&[old0.clone(), old1.clone(), new0.clone(), new1.clone()]);
    for hull in piece_hulls(&pts, SWEEP_DEPTH) {
        if strictly_disjoint(&swept, &hull) {
            continue;
        }
        let mut shared: Option<Rat> = None;
        for end in [&pts[0], &pts[pts.len() - 1]] {
            if (end == &old0 || end == &old1) && (end == &new0 || end == &new1) {
                shared = Some(end.clone());
                break;
            }
        }
        let Some(shared) = shared else {
            return (false, "curve-contact");
        };
        let old_far = if old0 == shared { &old1 } else { &old0 };
        let new_far = if new0 == shared { &new1 } else { &new0 };
        let dot = (&old_far.0 - &shared.0) * (&new_far.0 - &shared.0)
            + (&old_far.1 - &shared.1) * (&new_far.1 - &shared.1);
        if dot.is_zero() {
            return (false, "ray-collapse");
        }
        if dot.is_negative() {
            return (false, "ray-reversal");
        }
        if !hulls_meet_only_at(&swept, &hull, &shared) {
            return (false, "curve-contact");
        }
    }
    (true, "clear")
}

/// Certify every straight sweep against every fixed curve.
///
/// Changed straight segments sweep from old to new positions while
/// curves stay fixed; the first failing pair reports its reason.
pub fn movement_clear(
    old_segs: &[((f64, f64), (f64, f64))],
    new_segs: &[((f64, f64), (f64, f64))],
    curves: &[Vec<Pt>],
) -> (bool, &'static str) {
    for (old, new) in old_segs.iter().zip(new_segs.iter()) {
        for ctrls in curves {
            let (ok, reason) = edge_vs_curve_clear(*old, *new, ctrls);
            if !ok {
                return (false, reason);
            }
        }
    }
    (true, "clear")
}

enum Prim {
    Line(Rat, Rat),
    Curve(Vec<Rat>),
}

struct Contour {
    prims: Vec<Prim>,
    closed: bool,
    start: Rat,
}

/// Strict command grammar with materialized implicit close.
///
/// Move while a contour is open, any operation after close without a new
/// move, an unclosed trailing contour, unknown ops and bad/non-finite
/// coordinates all fail closed. An explicit close materializes the
/// implicit closing edge when non-degenerate, so the certificate sees
/// exactly the edges the substituted outline uses; wraparound adjacency
/// is allowed solely on closed contours.
fn parse_commands(cmds: &[FittedCommand]) -> Option<Vec<Contour>> {
    let mut contours = Vec::new();
    let mut prims: Vec<Prim> = Vec::new();
    let mut pen: Option<(f32, f32)> = None;
    let mut start: Option<(f32, f32)> = None;
    let mut open = false;
    for cmd in cmds {
        match cmd {
            FittedCommand::MoveTo(x, y) => {
                if open {
                    return None;
                }
                lift32(*x, *y)?;
                prims = Vec::new();
                pen = Some((*x, *y));
                start = Some((*x, *y));
                open = true;
            }
            FittedCommand::LineTo(x, y) => {
                let (px, py) = pen?;
                if !open {
                    return None;
                }
                let q = lift32(*x, *y)?;
                prims.push(Prim::Line(lift32(px, py)?, q));
                pen = Some((*x, *y));
            }
            FittedCommand::QuadTo(x1, y1, x, y) => {
                let (px, py) = pen?;
                if !open {
                    return None;
                }
                prims.push(Prim::Curve(vec![
                    lift32(px, py)?,
                    lift32(*x1, *y1)?,
                    lift32(*x, *y)?,
                ]));
                pen = Some((*x, *y));
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                let (px, py) = pen?;
                if !open {
                    return None;
                }
                prims.push(Prim::Curve(vec![
                    lift32(px, py)?,
                    lift32(*x1, *y1)?,
                    lift32(*x2, *y2)?,
                    lift32(*x, *y)?,
                ]));
                pen = Some((*x, *y));
            }
            FittedCommand::Close => {
                if !open {
                    return None;
                }
                let (px, py) = pen?;
                let (sx, sy) = start?;
                if (px, py) != (sx, sy) {
                    prims.push(Prim::Line(lift32(px, py)?, lift32(sx, sy)?));
                }
                contours.push(Contour {
                    prims: std::mem::take(&mut prims),
                    closed: true,
                    start: lift32(sx, sy)?,
                });
                pen = None;
                start = None;
                open = false;
            }
        }
    }
    if open {
        return None;
    }
    Some(contours)
}

struct Entry {
    curve: bool,
    ci: usize,
    si: usize,
    k: usize,
    pts: Vec<Rat>,
    hull: Vec<Rat>,
    bbox: (BigRational, BigRational, BigRational, BigRational),
    /// Interval bounds prepared once per immutable hull/chain alongside
    /// the exact values above; the entry is never mutated after `push`,
    /// so these cannot go stale within a `certify` call, and a fresh
    /// candidate builds fresh entries with fresh bounds.
    pts_iv: Option<Vec<filtered::PtI>>,
    hull_iv: Option<Vec<filtered::PtI>>,
}

/// Exact bounding box of a nonempty hull: (lo_x, lo_y, hi_x, hi_y).
fn hull_bbox(hull: &[Rat]) -> (BigRational, BigRational, BigRational, BigRational) {
    let (mut lo_x, mut lo_y) = (hull[0].0.clone(), hull[0].1.clone());
    let (mut hi_x, mut hi_y) = (hull[0].0.clone(), hull[0].1.clone());
    for p in &hull[1..] {
        if p.0 < lo_x {
            lo_x = p.0.clone();
        }
        if p.0 > hi_x {
            hi_x = p.0.clone();
        }
        if p.1 < lo_y {
            lo_y = p.1.clone();
        }
        if p.1 > hi_y {
            hi_y = p.1.clone();
        }
    }
    (lo_x, lo_y, hi_x, hi_y)
}

/// Strict box separation on exact bounds; shared edges do not separate.
fn boxes_strictly_separate(
    a: &(BigRational, BigRational, BigRational, BigRational),
    b: &(BigRational, BigRational, BigRational, BigRational),
) -> bool {
    a.2 < b.0 || b.2 < a.0 || a.3 < b.1 || b.3 < a.1
}

fn build_entries(contours: &[Contour], depth: usize) -> Vec<Entry> {
    let mut entries = Vec::new();
    let mut push = |curve: bool, ci: usize, si: usize, k: usize, pts: Vec<Rat>| {
        let hull = convex_hull(&pts);
        let bbox = hull_bbox(&hull);
        // Prepared once here, reused across every pairwise call below;
        // `None` keeps the unprepared filter path with the same fallback.
        let hull_iv = filtered::enclose_hull(&hull);
        let pts_iv = filtered::enclose_hull(&pts);
        entries.push(Entry {
            curve,
            ci,
            si,
            k,
            pts,
            hull,
            bbox,
            pts_iv,
            hull_iv,
        });
    };
    for (ci, contour) in contours.iter().enumerate() {
        for (si, prim) in contour.prims.iter().enumerate() {
            match prim {
                Prim::Line(a, b) => push(false, ci, si, 0, vec![a.clone(), b.clone()]),
                Prim::Curve(ctrls) => {
                    for (k, chain) in piece_chains(ctrls, depth).iter().enumerate() {
                        push(true, ci, si, k, chain.clone());
                    }
                }
            }
        }
    }
    entries
}

/// Incident-adjacent shared junction, or `None`.
///
/// Pieces of one primitive, or consecutive primitives (with wraparound
/// only on closed contours) of one contour, share a junction when an
/// endpoint of one chain is exactly an endpoint of the other.
fn adjacent(a: &Entry, b: &Entry, contours: &[Contour], last_piece: usize) -> Option<Rat> {
    if a.ci != b.ci {
        return None;
    }
    let n = contours[a.ci].prims.len();
    let wrap_ok = contours[a.ci].closed;
    let a_last = if a.curve { last_piece } else { 0 };
    let b_last = if b.curve { last_piece } else { 0 };
    let consecutive = (a.si == b.si && a.k.abs_diff(b.k) == 1)
        || ((a.si + 1 == b.si || (wrap_ok && n > 0 && (a.si + 1) % n == b.si))
            && a.k == a_last
            && b.k == 0)
        || ((b.si + 1 == a.si || (wrap_ok && n > 0 && (b.si + 1) % n == a.si))
            && b.k == b_last
            && a.k == 0);
    if !consecutive {
        return None;
    }
    for v in [&a.pts[0], &a.pts[a.pts.len() - 1]] {
        if v == &b.pts[0] || v == &b.pts[b.pts.len() - 1] {
            return Some(v.clone());
        }
    }
    None
}

#[cfg_attr(not(test), allow(dead_code))]
struct Report {
    ok: bool,
    reason: &'static str,
    at: Option<(usize, usize, usize)>,
    with: Option<(usize, usize, usize)>,
}

/// Filter-first chord verdict reusing bounds prepared once per immutable
/// chain; the exact predicate runs unchanged on any fallback.
fn chord_monotone_cached(ctrls: &[Rat], iv: Option<&[filtered::PtI]>) -> bool {
    if let Some(bound) = iv.and_then(|iv| filtered::BoundHull::new(ctrls, iv)) {
        if let Some(v) = filtered::chord_monotone_h(&bound) {
            return v;
        }
        return is_chord_monotone_exact(ctrls);
    }
    if let Some(v) = filtered::chord_monotone(ctrls) {
        return v;
    }
    is_chord_monotone_exact(ctrls)
}

/// Filter-first strict separation reusing bounds prepared once per
/// immutable hull; the exact narrow phase runs unchanged.
fn entry_disjoint(
    hp: &[Rat],
    hpi: Option<&filtered::BoundHull<'_>>,
    hq: &[Rat],
    hqi: Option<&filtered::BoundHull<'_>>,
) -> bool {
    if let (Some(x), Some(y)) = (hpi, hqi) {
        if let Some(verdict) = filtered::polys_strictly_disjoint_h(x, y) {
            return verdict;
        }
        return strictly_disjoint_exact(hp, hq);
    }
    strictly_disjoint(hp, hq)
}

/// Filter-first shared-contact verdict reusing prepared bounds; the exact
/// narrow phase runs unchanged, including degenerate SAT semantics.
fn entry_meet_only_at(
    hp: &[Rat],
    hpi: Option<&filtered::BoundHull<'_>>,
    hq: &[Rat],
    hqi: Option<&filtered::BoundHull<'_>>,
    shared: &Rat,
) -> bool {
    if let (Some(x), Some(y)) = (hpi, hqi) {
        if let Some(v) = filtered::hulls_meet_only_at_h(x, y, shared) {
            return v;
        }
        return hulls_meet_only_at_exact(hp, hq, shared);
    }
    hulls_meet_only_at(hp, hq, shared)
}

/// Certify curve-to-polyline substitution for one outline.
///
/// Every curve piece at the dyadic depth must be chord-monotone, and
/// every piece hull must be strictly disjoint from every other
/// primitive hull except incident-adjacent ones sharing exactly their
/// junction (tangency allowed). Joints must also be exactly
/// float-representable for the polyline build.
fn certify(contours: &[Contour], depth: usize) -> Report {
    let entries = build_entries(contours, depth);
    // Bind each immutable hull to its prepared bounds once; the borrow
    // keeps each exact hull paired with its entry-owned bounds, and a
    // fresh candidate rebuilds both together.
    let bounds: Vec<Option<filtered::BoundHull<'_>>> = entries
        .iter()
        .map(|e| {
            e.hull_iv
                .as_ref()
                .and_then(|iv| filtered::BoundHull::new(&e.hull, iv))
        })
        .collect();
    let last_piece = if depth >= usize::BITS as usize {
        usize::MAX
    } else {
        (1usize << depth) - 1
    };
    let fail = |reason: &'static str,
                at: Option<(usize, usize, usize)>,
                with: Option<(usize, usize, usize)>| Report {
        ok: false,
        reason,
        at,
        with,
    };
    let mut joints: Vec<Rat> = Vec::new();
    for entry in &entries {
        if !entry.curve {
            continue;
        }
        if !chord_monotone_cached(&entry.pts, entry.pts_iv.as_deref()) {
            return fail(
                "nonmonotone-piece",
                Some((entry.ci, entry.si, entry.k)),
                None,
            );
        }
        joints.push(entry.pts[entry.pts.len() - 1].clone());
    }
    for (i, entry) in entries.iter().enumerate() {
        if !entry.curve {
            continue;
        }
        for (j, other) in entries.iter().enumerate() {
            // Earlier curve pairs already passed their symmetric disjointness
            // or single-contact certificate. Lines have no outer-loop visit.
            if i == j || (other.curve && j < i) {
                continue;
            }
            // Conservative broad phase after the CGAL AABB-tree principle
            // ([CGAL AABB](https://doc.cgal.org/latest/AABB_tree/index.html)):
            // strictly separated exact boxes prove disjoint hulls, so the
            // separating-axis test below must accept as well. Restricted to
            // strictly convex hulls, where edge-normal separation is
            // complete; degenerate point/segment hulls keep the exact
            // fail-closed narrow phase, since no edge normal need separate
            // them (e.g. disjoint collinear segments share one normal).
            if entry.hull.len() >= 3
                && other.hull.len() >= 3
                && boxes_strictly_separate(&entry.bbox, &other.bbox)
            {
                continue;
            }
            if entry_disjoint(
                &entry.hull,
                bounds[i].as_ref(),
                &other.hull,
                bounds[j].as_ref(),
            ) {
                continue;
            }
            match adjacent(entry, other, contours, last_piece) {
                Some(shared)
                    if entry_meet_only_at(
                        &entry.hull,
                        bounds[i].as_ref(),
                        &other.hull,
                        bounds[j].as_ref(),
                        &shared,
                    ) => {}
                _ => {
                    return fail(
                        "hull-contact",
                        Some((entry.ci, entry.si, entry.k)),
                        Some((other.ci, other.si, other.k)),
                    );
                }
            }
        }
    }
    for joint in &joints {
        if exact_f64(&joint.0).is_none() || exact_f64(&joint.1).is_none() {
            return fail("joint-inexact", None, None);
        }
    }
    Report {
        ok: true,
        reason: "substitution-certified",
        at: None,
        with: None,
    }
}

/// Bit identity of one coordinate: `f32` bits pair value and storage, so
/// numeric `==` cannot confuse -0.0 with 0.0 and no stale-bits alias
/// exists. Non-finite values fail closed.
fn coord_bits(x: f32) -> Option<u32> {
    if !x.is_finite() {
        return None;
    }
    Some(x.to_bits())
}

/// Bit-exact Bezier control geometry per curve op, or `None`.
///
/// Each key holds the full control tuple including the implied start
/// point resolved from the preceding command, so moving a line/move
/// start while leaving the curve dict untouched still mismatches.
fn curve_keys(cmds: &[FittedCommand]) -> Option<Vec<Vec<(u32, u32)>>> {
    let mut keys: Vec<Vec<(u32, u32)>> = Vec::new();
    let mut current: Option<(u32, u32)> = None;
    let mut contour_start: Option<(u32, u32)> = None;
    let mut open = false;
    for cmd in cmds {
        match cmd {
            FittedCommand::MoveTo(x, y) => {
                if open {
                    return None;
                }
                let bits = (coord_bits(*x)?, coord_bits(*y)?);
                current = Some(bits);
                contour_start = Some(bits);
                open = true;
            }
            FittedCommand::LineTo(x, y) => {
                if !open {
                    return None;
                }
                current = Some((coord_bits(*x)?, coord_bits(*y)?));
            }
            FittedCommand::QuadTo(x1, y1, x, y) => {
                if !open {
                    return None;
                }
                let start = current?;
                let end = (coord_bits(*x)?, coord_bits(*y)?);
                keys.push(vec![start, (coord_bits(*x1)?, coord_bits(*y1)?), end]);
                current = Some(end);
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                if !open {
                    return None;
                }
                let start = current?;
                let end = (coord_bits(*x)?, coord_bits(*y)?);
                keys.push(vec![
                    start,
                    (coord_bits(*x1)?, coord_bits(*y1)?),
                    (coord_bits(*x2)?, coord_bits(*y2)?),
                    end,
                ]);
                current = Some(end);
            }
            FittedCommand::Close => {
                if !open {
                    return None;
                }
                open = false;
                current = contour_start;
            }
        }
    }
    if open {
        return None;
    }
    Some(keys)
}

fn rat_pair_to_pt(p: &Rat) -> Option<Pt> {
    Some([exact_f64(&p.0)?, exact_f64(&p.1)?])
}

/// Polyline loops with identical contour labels and endpoints.
///
/// Each curve op becomes line-to joints through the exact dyadic chain;
/// original endpoints keep their exact float bits.
fn substituted_loops(cmds: &[FittedCommand], depth: usize) -> Option<Vec<Vec<Pt>>> {
    let contours = parse_commands(cmds)?;
    substituted_contours(&contours, depth)
}

fn substituted_contours(contours: &[Contour], depth: usize) -> Option<Vec<Vec<Pt>>> {
    if !certify(&contours, depth).ok {
        return None;
    }
    let mut loops = Vec::with_capacity(contours.len());
    for contour in contours {
        let mut pts = vec![rat_pair_to_pt(&contour.start)?];
        for prim in &contour.prims {
            match prim {
                Prim::Line(_, b) => pts.push(rat_pair_to_pt(b)?),
                Prim::Curve(ctrls) => {
                    let chains = piece_chains(ctrls, depth);
                    let mut joints: Vec<Rat> = vec![chains[0][0].clone()];
                    for chain in &chains {
                        joints.push(chain[chain.len() - 1].clone());
                    }
                    for joint in joints.iter().skip(1) {
                        pts.push(rat_pair_to_pt(joint)?);
                    }
                }
            }
        }
        if pts.len() > 1 && pts[0] == pts[pts.len() - 1] {
            pts.pop();
        }
        loops.push(pts);
    }
    Some(loops)
}

fn parsed_contours(parsed: &super::geometry::Parsed) -> Option<Vec<Contour>> {
    use super::geometry::Segment;
    let mut out = Vec::with_capacity(parsed.contours.len());
    for segments in &parsed.contours {
        let start = segments.first()?.endpoints().0;
        if segments.last()?.endpoints().1 != start {
            return None;
        }
        let mut prims = Vec::new();
        for segment in segments {
            let (a, b) = segment.endpoints();
            let p = parsed.oncurve.get(a)?;
            let q = parsed.oncurve.get(b)?;
            // A constant line has no directed extent or winding. Omit it
            // only in this certificate representation, so its two incident
            // primitives remain adjacent after hinting collapses a line.
            // Delivery and same_segment_shape still retain every source op.
            // This is the same exact zero-edge elimination used by the
            // CGAL arrangement port in topology::signature.
            if segment.is_line() && p == q {
                continue;
            }
            prims.push(match *segment {
                Segment::Line { .. } => Prim::Line(lift(p)?, lift(q)?),
                Segment::Quad { c, .. } => {
                    Prim::Curve(vec![lift(p)?, lift(parsed.offcurve.get(c)?)?, lift(q)?])
                }
                Segment::Cubic { c1, c2, .. } => Prim::Curve(vec![
                    lift(p)?,
                    lift(parsed.offcurve.get(c1)?)?,
                    lift(parsed.offcurve.get(c2)?)?,
                    lift(q)?,
                ]),
            });
        }
        out.push(Contour {
            prims,
            closed: true,
            start: lift(parsed.oncurve.get(start)?)?,
        });
    }
    Some(out)
}

pub(super) fn certify_parsed(
    parsed: &super::geometry::Parsed,
    depth: usize,
) -> Result<(), &'static str> {
    let contours = parsed_contours(parsed).ok_or("malformed-commands")?;
    let report = certify(&contours, depth);
    if report.ok {
        Ok(())
    } else {
        Err(report.reason)
    }
}

/// One immutable outline's depth-zero substitution and finite signature.
/// Keeping the certificate with the borrowed geometry follows CGAL's
/// cached exact-representation approach (https://doc.cgal.org/latest/Number_types/classCGAL_1_1Lazy__exact__nt.html).
/// Failed certificates are cached too; a changed candidate needs a new value.
pub(super) struct PreparedSubstitution<'a> {
    parsed: &'a super::geometry::Parsed,
    signature: std::cell::OnceCell<Option<serde_json::Value>>,
}

impl<'a> PreparedSubstitution<'a> {
    pub(super) fn new(parsed: &'a super::geometry::Parsed) -> Self {
        Self {
            parsed,
            signature: std::cell::OnceCell::new(),
        }
    }

    fn signature(&self) -> Option<&serde_json::Value> {
        self.signature
            .get_or_init(|| {
                if self.parsed.contours.is_empty() {
                    return None;
                }
                let contours = parsed_contours(self.parsed)?;
                topology::signature(&substituted_contours(&contours, 0)?)
            })
            .as_ref()
    }

    pub(super) fn is_valid(&self) -> bool {
        self.signature().is_some()
    }
}

fn same_segment_shape(a: &super::geometry::Parsed, b: &super::geometry::Parsed) -> bool {
    a.contours.len() == b.contours.len()
        && a.contours.iter().zip(&b.contours).all(|(a, b)| {
            a.len() == b.len()
                && a.iter()
                    .zip(b)
                    .all(|(a, b)| std::mem::discriminant(a) == std::mem::discriminant(b))
        })
}

/// Source validity remains mandatory, including finite-signature existence;
/// only upstream/candidate signature values are compared, as before.
pub(super) fn compare_prepared(
    source: &PreparedSubstitution<'_>,
    upstream: &PreparedSubstitution<'_>,
    candidate: &PreparedSubstitution<'_>,
) -> bool {
    if source.parsed.contours.is_empty()
        || !same_segment_shape(source.parsed, upstream.parsed)
        || !same_segment_shape(upstream.parsed, candidate.parsed)
        || !source.is_valid()
    {
        return false;
    }
    match (upstream.signature(), candidate.signature()) {
        (Some(up), Some(new)) => up == new,
        _ => false,
    }
}

/// Hobby section 6 / Shene substitution for independently certified moving
/// curves. This compares finite arrangement invariants, not a homotopy.
/// Raw feature coordinates stay f64 through exact rational lifting.
pub fn compare_substituted(
    source: &super::geometry::Parsed,
    upstream: &super::geometry::Parsed,
    candidate: &super::geometry::Parsed,
) -> bool {
    compare_prepared(
        &PreparedSubstitution::new(source),
        &PreparedSubstitution::new(upstream),
        &PreparedSubstitution::new(candidate),
    )
}

fn straight_loops(cmds: &[FittedCommand]) -> Option<Vec<Vec<Pt>>> {
    let contours = parse_commands(cmds)?;
    let mut loops = Vec::with_capacity(contours.len());
    for contour in &contours {
        let to_pt = |p: &Rat| -> Option<Pt> { rat_pair_to_pt(p) };
        let mut pts = vec![to_pt(&contour.start)?];
        for prim in &contour.prims {
            match prim {
                Prim::Line(_, b) => pts.push(to_pt(b)?),
                Prim::Curve(_) => return None,
            }
        }
        if pts.len() > 1 && pts[0] == pts[pts.len() - 1] {
            pts.pop();
        }
        loops.push(pts);
    }
    Some(loops)
}

fn op_shape(cmds: &[FittedCommand]) -> Vec<u8> {
    cmds.iter()
        .map(|cmd| match cmd {
            FittedCommand::MoveTo(..) => 0,
            FittedCommand::LineTo(..) => 1,
            FittedCommand::QuadTo(..) => 2,
            FittedCommand::CurveTo(..) => 3,
            FittedCommand::Close => 4,
        })
        .collect()
}

/// Topology gate through certified polyline substitution.
///
/// Source, upstream and candidate certify independently at depth 0;
/// straight-only outlines delegate directly. Candidate Bezier control
/// geometry must be bit-identical to upstream, including implied starts
/// and signed-zero bits. True only when all three classify and the
/// upstream and candidate canonical signatures match exactly; source is
/// supported independently but an inherited source-upstream difference
/// is allowed. No result caching: every call re-verifies its inputs.
/// The comparison rests on equal finite topological invariants per
/// geometry, not on a continuous straight-edge homotopy guarantee.
pub fn compare_commands(
    source: &[FittedCommand],
    upstream: &[FittedCommand],
    candidate: &[FittedCommand],
) -> bool {
    if source.is_empty() || upstream.is_empty() || candidate.is_empty() {
        return false;
    }
    let (src_ops, up_ops, cand_ops) = (op_shape(source), op_shape(upstream), op_shape(candidate));
    if src_ops != up_ops || up_ops != cand_ops {
        return false;
    }
    let curved = src_ops.iter().any(|&op| op == 2 || op == 3);
    if curved {
        match (curve_keys(upstream), curve_keys(candidate)) {
            (Some(up_keys), Some(cand_keys)) if up_keys == cand_keys => {}
            _ => return false,
        }
    }
    let loops = if curved {
        match (
            substituted_loops(source, 0),
            substituted_loops(upstream, 0),
            substituted_loops(candidate, 0),
        ) {
            (Some(s), Some(u), Some(c)) => (s, u, c),
            _ => return false,
        }
    } else {
        match (
            straight_loops(source),
            straight_loops(upstream),
            straight_loops(candidate),
        ) {
            (Some(s), Some(u), Some(c)) => (s, u, c),
            _ => return false,
        }
    };
    match (
        topology::signature(&loops.0),
        topology::signature(&loops.1),
        topology::signature(&loops.2),
    ) {
        (Some(_), Some(up_sig), Some(cand_sig)) => up_sig == cand_sig,
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn constant_lines_preserve_certificate_adjacency_without_hiding_short_edges() {
        // Exact zero-edge elimination in the CGAL arrangement model:
        // source/delivery keep the op, certificate geometry keeps winding.
        let plain = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::QuadTo(2.0, 0.0, 2.0, 2.0),
            FittedCommand::QuadTo(2.0, 4.0, 0.0, 4.0),
            FittedCommand::QuadTo(-2.0, 4.0, -2.0, 2.0),
            FittedCommand::QuadTo(-2.0, 0.0, 0.0, 0.0),
            FittedCommand::Close,
        ];
        let parsed = super::super::geometry::parse_commands(&plain).unwrap();
        let mut duplicate = plain.clone();
        duplicate.insert(2, FittedCommand::LineTo(2.0, 2.0));
        let repeated = super::super::geometry::parse_commands(&duplicate).unwrap();
        assert_eq!(repeated.contours[0].len(), parsed.contours[0].len() + 1);
        for depth in [0, 1, 2] {
            assert_eq!(certify_parsed(&parsed, depth), Ok(()));
            assert_eq!(certify_parsed(&repeated, depth), Ok(()));
        }
        let signature = |p: &super::super::geometry::Parsed| {
            topology::signature(&substituted_contours(&parsed_contours(p).unwrap(), 0).unwrap())
        };
        assert_eq!(signature(&parsed), signature(&repeated));
        assert!(compare_substituted(&repeated, &repeated, &repeated));
        // Shape matching still refuses a removed output operator.
        assert!(!compare_substituted(&repeated, &repeated, &parsed));
        // A short nonconstant edge is retained exactly; no epsilon erasure.
        duplicate[2] = FittedCommand::LineTo(2.0, 2.0 + 1.0 / 65536.0);
        let short = super::super::geometry::parse_commands(&duplicate).unwrap();
        let contours = parsed_contours(&short).unwrap();
        assert_eq!(contours[0].prims.len(), 5);
        // Normalizing a constant line must not normalize away a collision.
        duplicate[2] = FittedCommand::LineTo(2.0, 2.0);
        duplicate[3] = FittedCommand::QuadTo(-4.0, -4.0, 0.0, 4.0);
        let crossing = super::super::geometry::parse_commands(&duplicate).unwrap();
        assert!(certify_parsed(&crossing, 0).is_err());
        assert!(!compare_substituted(&repeated, &repeated, &crossing));
    }

    fn seg(a: (f64, f64), b: (f64, f64)) -> ((f64, f64), (f64, f64)) {
        (a, b)
    }

    fn quad(a: [f64; 2], c: [f64; 2], b: [f64; 2]) -> Vec<Pt> {
        vec![a, c, b]
    }

    const FAR_QUAD: [[f64; 2]; 3] = [[10.0, 10.0], [12.0, 14.0], [14.0, 10.0]];
    const ARCH: [[f64; 2]; 3] = [[0.0, 0.0], [1.0, 3.0], [2.0, 0.0]];

    fn rpts(pts: &[[f64; 2]]) -> Vec<Rat> {
        pts.iter().map(lift).map(Option::unwrap).collect()
    }

    #[test]
    fn distant_curve_clears() {
        let (ok, reason) = edge_vs_curve_clear(
            seg((0.0, 0.0), (0.0, 2.0)),
            seg((0.25, 0.0), (0.25, 2.0)),
            &FAR_QUAD,
        );
        assert!(ok, "{reason}");
        assert_eq!(reason, "clear");
    }

    #[test]
    fn sweep_crossing_fixed_curve_rejected() {
        let (ok, reason) = edge_vs_curve_clear(
            seg((0.0, -1.0), (0.0, 1.0)),
            seg((2.0, -1.0), (2.0, 1.0)),
            &ARCH,
        );
        assert!(!ok);
        assert_eq!(reason, "curve-contact");
    }

    #[test]
    fn hidden_mid_sweep_collision_rejected() {
        // Endpoints sit clear above/below the bump legs; the swept band
        // still crosses them, which endpoint sampling alone would miss.
        let bump = [[0.0, 0.0], [1.0, 1.0], [2.0, 0.0]];
        let (ok, _) = edge_vs_curve_clear(
            seg((0.2, 0.1), (1.8, 0.1)),
            seg((0.2, 0.4), (1.8, 0.4)),
            &bump,
        );
        assert!(!ok);
    }

    #[test]
    fn endpoint_tangency_accepted_only_isolated_shared() {
        let (ok, reason) = edge_vs_curve_clear(
            seg((0.0, 0.0), (-2.0, 1.0)),
            seg((0.0, 0.0), (-2.25, 0.75)),
            &ARCH,
        );
        assert!(ok, "{reason}");
    }

    #[test]
    fn endpoint_reversal_to_other_side_rejected() {
        let (ok, reason) = edge_vs_curve_clear(
            seg((0.0, 0.0), (-2.0, 1.0)),
            seg((0.0, 0.0), (2.0, 1.0)),
            &ARCH,
        );
        assert!(!ok);
        assert_eq!(reason, "ray-reversal");
    }

    #[test]
    fn ray_collapse_refused() {
        let (ok, reason) = edge_vs_curve_clear(
            seg((0.0, 0.0), (-2.0, 1.0)),
            seg((0.0, 0.0), (0.0, 0.0)),
            &ARCH,
        );
        assert!(!ok);
        assert_eq!(reason, "ray-collapse");
    }

    #[test]
    fn curve_endpoint_inside_sweep_not_pinned_refused() {
        // A curve endpoint inside the sweep that no segment shares is
        // contact, not a pinned joint.
        let inside = [[0.25, 0.5], [0.3, 1.0], [0.25, 1.5]];
        let (ok, reason) = edge_vs_curve_clear(
            seg((0.0, 0.0), (0.0, 2.0)),
            seg((0.5, 0.0), (0.5, 2.0)),
            &inside,
        );
        assert!(!ok);
        assert_eq!(reason, "curve-contact");
    }

    #[test]
    fn fitted_y_descender_sweep_clears() {
        // Actual fitted y: descender straight shares pinned curve-0
        // start; the sweep meets sub-hulls only there.
        let pinned = [3.984375, -1.3125];
        let curve = vec![pinned, [3.875, -1.625], [3.671875, -1.984375]];
        let (ok, reason) = edge_vs_curve_clear(
            ((7.375, 9.0), (pinned[0], pinned[1])),
            ((7.0, 9.0), (pinned[0], pinned[1])),
            &curve,
        );
        assert!(ok, "{reason}");
    }

    fn pt(a: [f64; 2]) -> (f64, f64) {
        (a[0], a[1])
    }

    #[test]
    fn control_point_change_flips_verdict() {
        let old = seg((0.0, 0.0), (0.0, 2.0));
        let new = seg((0.25, 0.0), (0.25, 2.0));
        let (ok_far, _) = edge_vs_curve_clear(old, new, &quad([3.0, 0.0], [5.0, 1.0], [3.0, 2.0]));
        let (ok_near, _) =
            edge_vs_curve_clear(old, new, &quad([3.0, 0.0], [-3.0, 1.0], [3.0, 2.0]));
        assert!(ok_far);
        assert!(!ok_near);
    }

    #[test]
    fn curve_through_sweep_without_shared_endpoint_vetoes() {
        let crossing = [[0.3, 1.0], [0.6, 1.5], [0.9, 1.0]];
        let (ok, reason) = edge_vs_curve_clear(
            seg((0.0, 0.0), (0.0, 2.0)),
            seg((0.5, 0.0), (0.5, 2.0)),
            &crossing,
        );
        assert!(!ok);
        assert_eq!(reason, "curve-contact");
    }

    #[test]
    fn verdict_translation_and_scale_invariant() {
        let old = seg((0.0, 0.0), (0.0, 2.0));
        let new = seg((0.25, 0.0), (0.25, 2.0));
        let expected = edge_vs_curve_clear(old, new, &FAR_QUAD);
        for (dx, k) in [(37.0, 1.0), (-1024.0, 1.0), (0.0, 2.0)] {
            let mv = |p: [f64; 2]| [p[0] * k + dx, p[1] * k + dx];
            let got = edge_vs_curve_clear(
                (pt(mv([0.0, 0.0])), pt(mv([0.0, 2.0]))),
                (pt(mv([0.25, 0.0])), pt(mv([0.25, 2.0]))),
                &FAR_QUAD.map(mv),
            );
            assert_eq!(got, expected);
        }
    }

    #[test]
    fn cubic_supported() {
        let cubic = [[8.0, 8.0], [9.0, 10.0], [11.0, 10.0], [12.0, 8.0]];
        let (ok, _) = edge_vs_curve_clear(
            seg((0.0, 0.0), (0.0, 2.0)),
            seg((0.25, 0.0), (0.25, 2.0)),
            &cubic,
        );
        assert!(ok);
    }

    #[test]
    fn movement_clear_pairs_reports_first_failure() {
        let olds = [seg((0.0, 0.0), (0.0, 2.0)), seg((0.0, -1.0), (0.0, 1.0))];
        let news = [seg((0.25, 0.0), (0.25, 2.0)), seg((2.0, -1.0), (2.0, 1.0))];
        let far = vec![FAR_QUAD.to_vec()];
        let arch = vec![ARCH.to_vec()];
        let both = vec![FAR_QUAD.to_vec(), ARCH.to_vec()];
        assert!(!movement_clear(&olds, &news, &both).0);
        assert!(movement_clear(&olds[..1], &news[..1], &far).0);
        let _ = arch;
    }

    #[test]
    fn monotone_quad_accepted() {
        assert!(is_chord_monotone(&rpts(&[
            [0.0, 0.0],
            [1.0, 1.0],
            [2.0, 0.0]
        ])));
    }

    #[test]
    fn loop_cubic_rejected_nonmonotone() {
        // Classic self-loop: one leg projects backwards on the chord.
        assert!(!is_chord_monotone(&rpts(&[
            [0.0, 0.0],
            [2.0, 1.0],
            [-1.0, 1.0],
            [1.0, 0.0]
        ])));
    }

    #[test]
    fn degenerate_chord_projection_rejected() {
        assert!(!is_chord_monotone(&rpts(&[
            [0.0, 0.0],
            [2.0, 2.0],
            [-2.0, 2.0],
            [0.0, 4.0]
        ])));
        assert!(!is_chord_monotone(&rpts(&[
            [1.0, 1.0],
            [1.0, 1.0],
            [1.0, 1.0]
        ])));
    }

    #[test]
    fn tangent_touch_meets_only_at_junction() {
        // C1-joined quads: hulls share the tangent line through the
        // junction but intersect only there; no wedge required.
        let left = convex_hull(&rpts(&[[0.0, 0.0], [1.0, 0.0], [2.0, 1.0]]));
        let right = convex_hull(&rpts(&[[2.0, 1.0], [3.0, 2.0], [4.0, 2.0]]));
        let shared = lift(&[2.0, 1.0]).unwrap();
        assert!(hulls_meet_only_at(&left, &right, &shared));
    }

    #[test]
    fn crossing_hulls_rejected() {
        let left = convex_hull(&rpts(&[[0.0, 0.0], [1.0, 0.0], [2.0, 1.0]]));
        let over = convex_hull(&rpts(&[[1.0, -1.0], [1.0, 1.0], [3.0, 0.0]]));
        let shared = lift(&[2.0, 1.0]).unwrap();
        assert!(!strictly_disjoint(&left, &over));
        assert!(!hulls_meet_only_at(&left, &over, &shared));
    }

    fn sweep_next(s: &mut u64) -> u64 {
        *s ^= *s << 13;
        *s ^= *s >> 7;
        *s ^= *s << 17;
        *s
    }

    fn sweep_rat(s: &mut u64) -> BigRational {
        let v = sweep_next(s) as i128;
        match sweep_next(s) % 6 {
            0 => BigRational::from_integer(v.into()),
            1 => BigRational::new(v.into(), 64.into()),
            2 => BigRational::new(v.into(), 3.into()),
            3 => BigRational::from_integer(v.wrapping_mul(1i128 << 90).into()),
            4 => BigRational::new(v.wrapping_mul(7).wrapping_add(1).into(), 4096.into()),
            _ => BigRational::new(v.into(), 113.into()),
        }
    }

    fn sweep_pt(s: &mut u64) -> Rat {
        (sweep_rat(s), sweep_rat(s))
    }

    #[test]
    fn filtered_predicates_match_exact_narrow_phases_on_sweep() {
        let mut s = 0xD1B5_4A32_0F6C_9E5Du64;
        let (mut decided, mut fallbacks) = (0usize, 0usize);
        for i in 0..2000 {
            let (a, b, mut c) = (sweep_pt(&mut s), sweep_pt(&mut s), sweep_pt(&mut s));
            if i % 7 == 6 {
                // Exact midpoint collinearity exercises either a checked
                // integer zero or the general rational fallback.
                let two = BigRational::integer(2);
                c = ((&a.0 + &b.0) / &two, (&a.1 + &b.1) / &two);
            }
            match filtered::orient_sign((&a.0, &a.1), (&b.0, &b.1), (&c.0, &c.1)) {
                Some(got) => {
                    decided += 1;
                    assert_eq!(got, orient_exact(&a, &b, &c));
                }
                None => fallbacks += 1,
            }
            if i % 4 == 0 {
                let p = vec![a.clone(), b.clone(), c.clone()];
                let shift = (
                    BigRational::from_integer(num_bigint::BigInt::from(1) << 200usize),
                    BigRational::integer(0),
                );
                let q: Vec<Rat> = p
                    .iter()
                    .map(|v| (&v.0 + &shift.0, &v.1 + &shift.1))
                    .collect();
                assert_eq!(convex_hull(&p), convex_hull_exact(&p));
                match filtered::polys_strictly_disjoint(&p, &q) {
                    Some(true) => {
                        decided += 1;
                        assert!(strictly_disjoint_exact(&p, &q));
                    }
                    _ => fallbacks += 1,
                }
                match filtered::hulls_meet_only_at(&p, &q, &p[0]) {
                    Some(got) => {
                        decided += 1;
                        assert_eq!(got, hulls_meet_only_at_exact(&p, &q, &p[0]));
                    }
                    None => fallbacks += 1,
                }
                match filtered::chord_monotone(&p) {
                    Some(got) => {
                        decided += 1;
                        assert_eq!(got, is_chord_monotone_exact(&p));
                    }
                    None => fallbacks += 1,
                }
                match filtered::source_quad_clear(&BigRational::integer(1), &p) {
                    Some(true) => {
                        decided += 1;
                        let one = BigRational::integer(1);
                        assert!(source_disk_clear_exact(&p, &one));
                        // Independent rational oracle on the promoted inputs.
                        let op: Vec<(num_rational::BigRational, num_rational::BigRational)> = p
                            .iter()
                            .map(|v| (v.0.to_rational(), v.1.to_rational()))
                            .collect();
                        assert!(source_disk_clear_oracle(&op, &one.to_rational()));
                    }
                    _ => fallbacks += 1,
                }
            }
        }
        assert!(decided > 0 && fallbacks > 0);
    }

    fn bump_cmds() -> Vec<FittedCommand> {
        vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(4.0, 0.0),
            FittedCommand::QuadTo(5.0, 1.0, 4.0, 2.0),
            FittedCommand::LineTo(0.0, 4.0),
            FittedCommand::Close,
        ]
    }

    fn op_names(cmds: &[FittedCommand]) -> Vec<&'static str> {
        cmds.iter()
            .map(|c| match c {
                FittedCommand::MoveTo(..) => "move_to",
                FittedCommand::LineTo(..) => "line_to",
                FittedCommand::QuadTo(..) => "quad_to",
                FittedCommand::CurveTo(..) => "curve_to",
                FittedCommand::Close => "close",
            })
            .collect()
    }

    #[test]
    fn substitution_certifies_closed_bump() {
        let cmds = bump_cmds();
        let contours = parse_commands(&cmds).expect("strict grammar parses");
        let rep = certify(&contours, 0);
        assert!(rep.ok, "{}", rep.reason);
        let loops = substituted_loops(&cmds, 0).expect("polyline builds");
        assert_eq!(loops.len(), 1);
        assert_eq!(loops[0].len(), 4);
        assert_eq!(loops[0][0], [0.0, 0.0]);
        assert_eq!(loops[0][1], [4.0, 0.0]);
        assert_eq!(loops[0][3], [0.0, 4.0]);
    }

    #[test]
    fn substitution_rejects_curve_crossing_straight() {
        let cmds = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(2.0, -1.0),
            FittedCommand::LineTo(2.0, 5.0),
            FittedCommand::LineTo(4.0, 5.0),
            FittedCommand::QuadTo(2.0, 2.0, 0.0, 5.0),
            FittedCommand::Close,
        ];
        let contours = parse_commands(&cmds).expect("strict grammar parses");
        let rep = certify(&contours, 1);
        assert!(!rep.ok);
        assert_eq!(rep.reason, "hull-contact");
    }

    #[test]
    fn substitution_rejects_loop() {
        // A self-looping cubic: coarse depth fails monotonicity, while
        // fine pieces are locally monotone but overlap non-adjacently.
        let cmds = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::CurveTo(2.0, 1.0, -1.0, 1.0, 1.0, 0.0),
            FittedCommand::Close,
        ];
        let contours = parse_commands(&cmds).expect("strict grammar parses");
        let rep = certify(&contours, 0);
        assert!(!rep.ok);
        assert_eq!(rep.reason, "nonmonotone-piece");
        let rep = certify(&contours, 2);
        assert!(!rep.ok);
        assert_eq!(rep.reason, "hull-contact");
    }

    #[test]
    fn wrapper_refuses_moved_curves() {
        let base = bump_cmds();
        let mut moved = base.clone();
        moved[2] = FittedCommand::QuadTo(6.0, 1.0, 4.0, 2.0);
        assert!(!compare_commands(&base, &base, &moved));
    }

    #[test]
    fn wrapper_spoof_implied_start_refused() {
        // Identical quad values, but the preceding line moved: the Bezier
        // start point moved, so the curve geometry differs.
        let base = bump_cmds();
        let mut spoofed = base.clone();
        spoofed[1] = FittedCommand::LineTo(4.5, 0.0);
        assert!(!compare_commands(&base, &base, &spoofed));
    }

    #[test]
    fn wrapper_signed_zero_distinguished() {
        // Numeric == yet bit-distinct signed zeros must refuse.
        let base = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::QuadTo(1.0, 1.0, 2.0, 0.0),
            FittedCommand::Close,
        ];
        let neg = vec![
            FittedCommand::MoveTo(-0.0, 0.0),
            FittedCommand::QuadTo(1.0, 1.0, 2.0, 0.0),
            FittedCommand::Close,
        ];
        assert!(!compare_commands(&base, &base, &neg));
    }

    #[test]
    fn wrapper_command_shape_mismatch_refused() {
        let base = bump_cmds();
        let mut other = base.clone();
        other[2] = FittedCommand::LineTo(4.0, 2.0);
        assert!(!compare_commands(&base, &base, &other));
    }

    #[test]
    fn nonstart_straight_move_passes_pin_gate() {
        // A moved straight that starts no curve must pass the pin gate;
        // only curve geometry (with implied starts) is pinned.
        let base = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(2.0, 0.0),
            FittedCommand::LineTo(4.0, 0.0),
            FittedCommand::QuadTo(5.0, 1.0, 4.0, 2.0),
            FittedCommand::LineTo(0.0, 4.0),
            FittedCommand::Close,
        ];
        let mut moved = base.clone();
        moved[1] = FittedCommand::LineTo(2.2, 0.0);
        let (Some(up_keys), Some(cand_keys)) = (curve_keys(&base), curve_keys(&moved)) else {
            panic!("pin gate parses");
        };
        assert_eq!(up_keys, cand_keys);
    }

    #[test]
    fn identical_straight_triangle_matches() {
        let tri = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(4.0, 0.0),
            FittedCommand::LineTo(0.0, 4.0),
            FittedCommand::Close,
        ];
        assert!(compare_commands(&tri, &tri, &tri));
    }

    #[test]
    fn identical_bump_matches() {
        // Chord-crossing certificate is supported: a graph over its
        // chord may still cross the chord; hull separation decides.
        let base = bump_cmds();
        assert!(compare_commands(&base, &base, &base));
    }

    #[test]
    fn disk_clear_far_curve() {
        let (ok, reason) = disk_clear([0.0, 0.0], 0.5, &FAR_QUAD);
        assert!(ok);
        assert_eq!(reason, "clear");
    }

    #[test]
    fn disk_clear_collision_fails_closed() {
        let (ok, reason) = disk_clear([1.0, 1.0], 1.0, &ARCH);
        assert!(!ok);
        assert_eq!(reason, "disk-too-close");
    }

    #[test]
    fn disk_clear_touch_is_not_clear() {
        // Bbox distance exactly equals the radius: strict bound fails.
        let (ok, _) = disk_clear([0.0, 0.0], 1.0, &[[1.0, 0.0], [2.0, 0.0], [3.0, 0.0]]);
        assert!(!ok);
    }

    #[test]
    fn disk_clear_rejects_negative_radius_and_malformed() {
        assert_eq!(
            disk_clear([0.0, 0.0], -1.0, &ARCH),
            (false, "negative-radius")
        );
        assert_eq!(
            disk_clear([0.0, 0.0], 0.5, &[[f64::NAN, 0.0], [1.0, 1.0]]),
            (false, "malformed-curve")
        );
        assert_eq!(
            disk_clear([0.0, 0.0], f64::INFINITY, &ARCH),
            (false, "malformed-curve")
        );
    }

    #[test]
    fn disk_clear_exactness_third_offset() {
        // A 1/3-offset sweep toward a dyadic hull stays exact: no float
        // rounding may turn near-touch into clearance.
        let third = 1.0f64 / 3.0;
        let (ok, _) = edge_vs_curve_clear(
            seg((0.0, 0.0), (0.0, 2.0)),
            seg((third, 0.0), (third, 2.0)),
            &FAR_QUAD,
        );
        assert!(ok);
    }

    #[test]
    fn closing_edge_collision_certified() {
        // The implicit closing edge overlaps the quad hull while all
        // explicit lines clear it; without materialization the outline
        // would wrongly certify.
        let cmds = vec![
            FittedCommand::MoveTo(0.0, -4.0),
            FittedCommand::QuadTo(2.0, 1.0, 4.0, 0.0),
            FittedCommand::LineTo(6.0, 2.0),
            FittedCommand::Close,
        ];
        let contours = parse_commands(&cmds).expect("strict grammar parses");
        let rep = certify(&contours, 0);
        assert!(!rep.ok);
        assert_eq!(rep.reason, "hull-contact");
        assert_eq!(rep.at, Some((0, 0, 0)));
        assert_eq!(rep.with, Some((0, 2, 0)));
    }

    #[test]
    fn closing_edge_retained_when_clear() {
        let cmds = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(4.0, 0.0),
            FittedCommand::LineTo(4.0, 4.0),
            FittedCommand::QuadTo(2.0, 5.0, 0.0, 4.0),
            FittedCommand::Close,
        ];
        let contours = parse_commands(&cmds).expect("strict grammar parses");
        assert!(certify(&contours, 0).ok);
    }

    #[test]
    fn wraparound_and_second_contour() {
        let cmds = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::QuadTo(1.0, 3.0, 4.0, 2.0),
            FittedCommand::LineTo(6.0, 0.0),
            FittedCommand::Close,
            FittedCommand::MoveTo(10.0, 10.0),
            FittedCommand::LineTo(14.0, 10.0),
            FittedCommand::LineTo(14.0, 14.0),
            FittedCommand::LineTo(10.0, 14.0),
            FittedCommand::Close,
        ];
        let contours = parse_commands(&cmds).expect("strict grammar parses");
        assert!(certify(&contours, 0).ok);
    }

    #[test]
    fn strict_grammar_fails_closed() {
        let open = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(4.0, 0.0),
            FittedCommand::QuadTo(5.0, 1.0, 4.0, 2.0),
        ];
        assert!(parse_commands(&open).is_none());
        let doubled = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::MoveTo(9.0, 9.0),
        ];
        assert!(curve_keys(&doubled).is_none());
        let trailing = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::Close,
            FittedCommand::LineTo(1.0, 1.0),
        ];
        assert!(curve_keys(&trailing).is_none());
        assert!(!compare_commands(&open, &open, &open));
    }

    #[test]
    fn y_contour_zero_certifies_and_keeps_identity() {
        // Source contour 0 of default Roboto y (U+0079), ASCII recapture.
        let cmds = vec![
            FittedCommand::MoveTo(3.484375, 0.875),
            FittedCommand::LineTo(5.828125, 8.453125),
            FittedCommand::LineTo(7.375, 8.453125),
            FittedCommand::LineTo(3.984375, -1.3125),
            FittedCommand::QuadTo(3.875, -1.625, 3.671875, -1.984375),
            FittedCommand::QuadTo(3.484375, -2.34375, 3.1875, -2.671875),
            FittedCommand::QuadTo(2.890625, -3.0, 2.46875, -3.203125),
            FittedCommand::QuadTo(2.0625, -3.421875, 1.484375, -3.421875),
            FittedCommand::QuadTo(1.3125, -3.421875, 1.046875, -3.375),
            FittedCommand::QuadTo(0.78125, -3.328125, 0.671875, -3.296875),
            FittedCommand::LineTo(0.65625, -2.125),
            FittedCommand::QuadTo(0.71875, -2.125, 0.859375, -2.140625),
            FittedCommand::QuadTo(1.0, -2.15625, 1.046875, -2.15625),
            FittedCommand::QuadTo(1.546875, -2.15625, 1.890625, -2.015625),
            FittedCommand::QuadTo(2.234375, -1.890625, 2.46875, -1.59375),
            FittedCommand::QuadTo(2.703125, -1.296875, 2.875, -0.765625),
            FittedCommand::Close,
        ];
        let contours = parse_commands(&cmds).expect("strict grammar parses");
        let rep = certify(&contours, 0);
        assert!(rep.ok, "{}", rep.reason);
        let loops = substituted_loops(&cmds, 0).expect("polyline builds");
        assert_eq!(loops.len(), 1);
        // 4 lines + 11 single-joint quads + materialized close = 16.
        assert_eq!(loops[0].len(), 16);
        assert_eq!(loops[0][0], [3.484375, 0.875]);
        assert_eq!(
            op_names(&cmds).iter().filter(|o| **o == "quad_to").count(),
            11
        );
    }

    #[test]
    fn y_contour_zero_compare_matches() {
        let cmds = vec![
            FittedCommand::MoveTo(3.484375, 0.875),
            FittedCommand::LineTo(5.828125, 8.453125),
            FittedCommand::LineTo(7.375, 8.453125),
            FittedCommand::LineTo(3.984375, -1.3125),
            FittedCommand::QuadTo(3.875, -1.625, 3.671875, -1.984375),
            FittedCommand::QuadTo(3.484375, -2.34375, 3.1875, -2.671875),
            FittedCommand::QuadTo(2.890625, -3.0, 2.46875, -3.203125),
            FittedCommand::QuadTo(2.0625, -3.421875, 1.484375, -3.421875),
            FittedCommand::QuadTo(1.3125, -3.421875, 1.046875, -3.375),
            FittedCommand::QuadTo(0.78125, -3.328125, 0.671875, -3.296875),
            FittedCommand::LineTo(0.65625, -2.125),
            FittedCommand::QuadTo(0.71875, -2.125, 0.859375, -2.140625),
            FittedCommand::QuadTo(1.0, -2.15625, 1.046875, -2.15625),
            FittedCommand::QuadTo(1.546875, -2.15625, 1.890625, -2.015625),
            FittedCommand::QuadTo(2.234375, -1.890625, 2.46875, -1.59375),
            FittedCommand::QuadTo(2.703125, -1.296875, 2.875, -0.765625),
            FittedCommand::Close,
        ];
        assert!(compare_commands(&cmds, &cmds, &cmds));
    }

    #[test]
    fn joint_representability_gate() {
        // Dyadic joints stay exact; a repeating rational cannot survive
        // the round trip, which is what fails substitution closed.
        let half = BigRational::integer(1) / two();
        assert_eq!(exact_f64(&half), Some(0.5));
        let third = BigRational::integer(1) / BigRational::integer(3);
        assert_eq!(exact_f64(&third), None);
    }

    /// Pre-optimization pair loop: hull rebuilt per pair, no box shortcut.
    #[cfg(test)]
    fn oracle_certify(
        contours: &[Contour],
        depth: usize,
    ) -> (
        bool,
        &'static str,
        Option<(usize, usize, usize)>,
        Option<(usize, usize, usize)>,
    ) {
        let entries = build_entries(contours, depth);
        let last_piece = if depth >= usize::BITS as usize {
            usize::MAX
        } else {
            (1usize << depth) - 1
        };
        // Unfiltered reference chain: every predicate below is an exact
        // narrow phase, so this oracle stays independent of the filters.
        let mut joints: Vec<Rat> = Vec::new();
        for entry in &entries {
            if !entry.curve {
                continue;
            }
            if !is_chord_monotone_exact(&entry.pts) {
                return (
                    false,
                    "nonmonotone-piece",
                    Some((entry.ci, entry.si, entry.k)),
                    None,
                );
            }
            joints.push(entry.pts[entry.pts.len() - 1].clone());
        }
        for (i, entry) in entries.iter().enumerate() {
            if !entry.curve {
                continue;
            }
            let hull = convex_hull_exact(&entry.pts);
            for (j, other) in entries.iter().enumerate() {
                if i == j {
                    continue;
                }
                let other_hull = convex_hull_exact(&other.pts);
                if strictly_disjoint_exact(&hull, &other_hull) {
                    continue;
                }
                match adjacent(entry, other, contours, last_piece) {
                    Some(shared) if hulls_meet_only_at_exact(&hull, &other_hull, &shared) => {}
                    _ => {
                        return (
                            false,
                            "hull-contact",
                            Some((entry.ci, entry.si, entry.k)),
                            Some((other.ci, other.si, other.k)),
                        );
                    }
                }
            }
        }
        for joint in &joints {
            if exact_f64(&joint.0).is_none() || exact_f64(&joint.1).is_none() {
                return (false, "joint-inexact", None, None);
            }
        }
        (true, "substitution-certified", None, None)
    }

    fn check_certify_equiv(cmds: &[FittedCommand], depths: &[usize]) {
        let contours = parse_commands(cmds).expect("strict grammar parses");
        for &depth in depths {
            let rep = certify(&contours, depth);
            let oracle = oracle_certify(&contours, depth);
            assert_eq!(
                (rep.ok, rep.reason, rep.at, rep.with),
                oracle,
                "depth {depth} for {}",
                op_names(cmds).join(",")
            );
        }
    }

    fn square_at(x: f32, y: f32) -> Vec<FittedCommand> {
        vec![
            FittedCommand::MoveTo(x, y),
            FittedCommand::LineTo(x + 4.0, y),
            FittedCommand::QuadTo(x + 5.0, y + 1.0, x + 4.0, y + 2.0),
            FittedCommand::LineTo(x, y + 4.0),
            FittedCommand::Close,
        ]
    }

    #[test]
    fn certify_opt_matches_oracle_separated_and_overlapping() {
        let mut far = square_at(0.0, 0.0);
        far.extend(square_at(10.0, 10.0));
        check_certify_equiv(&far, &[0, 1, 2]);
        // Overlapping second contour: its quad crosses the first square.
        let mut over = square_at(0.0, 0.0);
        over.extend(vec![
            FittedCommand::MoveTo(2.0, -1.0),
            FittedCommand::LineTo(2.0, 5.0),
            FittedCommand::QuadTo(6.0, 2.0, 2.0, 6.0),
            FittedCommand::Close,
        ]);
        check_certify_equiv(&over, &[0, 1]);
    }

    #[test]
    fn certify_opt_matches_oracle_touching() {
        // Second contour starts exactly on the first quad's endpoint:
        // non-adjacent touch still fails closed in both.
        let mut touch = square_at(0.0, 0.0);
        touch.extend(vec![
            FittedCommand::MoveTo(4.0, 2.0),
            FittedCommand::LineTo(8.0, 2.0),
            FittedCommand::QuadTo(9.0, 3.0, 8.0, 4.0),
            FittedCommand::Close,
        ]);
        check_certify_equiv(&touch, &[0, 1, 2]);
        // Shared closing edge point across contours.
        let mut pinch = square_at(0.0, 0.0);
        pinch.extend(vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(-4.0, 0.0),
            FittedCommand::QuadTo(-5.0, 1.0, -4.0, 2.0),
            FittedCommand::Close,
        ]);
        check_certify_equiv(&pinch, &[0, 1]);
    }

    #[test]
    fn certify_opt_matches_oracle_degenerate() {
        // Zero-length line plus a zero-length (single-point) quad piece.
        let degenerate = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(0.0, 0.0),
            FittedCommand::LineTo(4.0, 0.0),
            FittedCommand::QuadTo(4.0, 0.0, 4.0, 0.0),
            FittedCommand::LineTo(4.0, 4.0),
            FittedCommand::Close,
        ];
        check_certify_equiv(&degenerate, &[0, 1, 2]);
        // Disjoint collinear segments across contours: one normal direction
        // only, so the narrow phase fails closed and no box shortcut applies.
        let mut collinear = square_at(0.0, 0.0);
        collinear.extend(vec![
            FittedCommand::MoveTo(10.0, 0.0),
            FittedCommand::LineTo(12.0, 0.0),
            FittedCommand::QuadTo(13.0, 0.0, 14.0, 0.0),
            FittedCommand::Close,
        ]);
        check_certify_equiv(&collinear, &[0, 1]);
        // Collinear overlapping quad controls (flat hull) near a line.
        let flat = vec![
            FittedCommand::MoveTo(0.0, 1.0),
            FittedCommand::LineTo(4.0, 1.0),
            FittedCommand::QuadTo(2.0, 0.0, 0.0, 0.0),
            FittedCommand::LineTo(0.0, 4.0),
            FittedCommand::Close,
        ];
        check_certify_equiv(&flat, &[0, 1, 2]);
    }

    #[test]
    fn certify_opt_matches_oracle_rounding_sensitive() {
        // Repeating-fraction offsets near contact: exact boxes must agree
        // with the narrow phase on strictness.
        let third = 1.0f32 / 3.0;
        let frac = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(4.0, 0.0),
            FittedCommand::QuadTo(4.0 + third, 1.0, 4.0, 2.0),
            FittedCommand::LineTo(third, 4.0),
            FittedCommand::Close,
            FittedCommand::MoveTo(8.0, 8.0),
            FittedCommand::LineTo(12.0, 8.0),
            FittedCommand::QuadTo(12.0 + third, 9.0, 12.0, 10.0),
            FittedCommand::Close,
        ];
        check_certify_equiv(&frac, &[0, 1, 2]);
        // 26.6-quantum offsets straddling a shared grid line.
        let quantum = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(4.0, 0.0),
            FittedCommand::QuadTo(4.0625, 1.0, 4.0, 2.0),
            FittedCommand::LineTo(0.0, 4.0),
            FittedCommand::Close,
        ];
        check_certify_equiv(&quantum, &[0, 1, 2, 3]);
    }

    #[test]
    fn certify_opt_matches_oracle_subdivided_adjacency() {
        // Self-looping cubic: monotone at coarse depth, overlapping
        // non-adjacent pieces when subdivided.
        let looped = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::CurveTo(2.0, 1.0, -1.0, 1.0, 1.0, 0.0),
            FittedCommand::Close,
        ];
        check_certify_equiv(&looped, &[0, 1, 2, 3]);
        // C1-joined quad chain sharing tangent junctions.
        let chain = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::QuadTo(1.0, 0.0, 2.0, 1.0),
            FittedCommand::QuadTo(3.0, 2.0, 4.0, 2.0),
            FittedCommand::LineTo(4.0, 6.0),
            FittedCommand::LineTo(0.0, 6.0),
            FittedCommand::Close,
        ];
        check_certify_equiv(&chain, &[0, 1, 2]);
    }

    #[test]
    fn unordered_curve_pairs_preserve_ordered_oracle_failure() {
        for scale in [0.5, 1.0, 4.0] {
            for (dx, dy) in [(0.0, 0.0), (37.5, -17.25)] {
                for height in [0.0, 1.0, 4.0, -1.0] {
                    let p = |x: f32, y: f32| (x * scale + dx, y * scale + dy);
                    let (x, y) = p(0.0, 0.0);
                    let (cx, cy) = p(2.0, height);
                    let (ex, ey) = p(4.0, 0.0);
                    let (bx, by) = p(2.0, -height);
                    // Two curves share both endpoints; the ordered oracle
                    // still rejects any second, uncertified contact.
                    check_certify_equiv(
                        &[
                            FittedCommand::MoveTo(x, y),
                            FittedCommand::QuadTo(cx, cy, ex, ey),
                            FittedCommand::QuadTo(bx, by, x, y),
                            FittedCommand::Close,
                        ],
                        &[0, 1, 2],
                    );
                }
            }
        }
    }
}

#[cfg(test)]
mod source_disk_tests {
    use super::*;

    #[test]
    fn bernstein_certificate_allows_tangency_and_rejects_penetration() {
        let one = BigRational::integer(1);
        let tangent = [[-1.0, 1.0], [0.0, 1.0], [1.0, 1.0]];
        assert!(source_disk_clear([0.0, 0.0], &one, &tangent));
        assert!(!disk_clear([0.0, 0.0], 1.0, &tangent).0);
        let inside = [[-1.0, 0.5], [0.0, 0.5], [1.0, 0.5]];
        assert!(!source_disk_clear([0.0, 0.0], &one, &inside));
        let through = [[-2.0, 2.0], [0.0, -2.0], [2.0, 2.0]];
        assert!(!source_disk_clear([0.0, 0.0], &one, &through));
    }

    #[test]
    fn segment_distance_checks_interior_and_degenerate_contacts() {
        let one = BigRational::integer(1);
        assert!(source_disk_clear(
            [0.0, 0.0],
            &one,
            &[[-1.0, 1.0], [1.0, 1.0]]
        ));
        assert!(source_disk_clear(
            [0.0, 0.0],
            &one,
            &[[1.0, 0.0], [1.0, 0.0]]
        ));
        assert!(!source_disk_clear(
            [0.0, 0.0],
            &one,
            &[[-2.0, 0.0], [2.0, 0.0]]
        ));
        assert!(!source_disk_clear(
            [0.0, 0.0],
            &one,
            &[[f64::NAN, 0.0], [2.0, 0.0]]
        ));
    }

    #[test]
    fn source_wrapper_matches_exact_core_on_translated_sweep() {
        let one = BigRational::integer(1);
        // Includes the translated-penetration regression shape.
        let bases: Vec<(Pt, Vec<Pt>)> = vec![
            ([0.0, 10.0], vec![[-1.0, 10.0], [0.0, 9.5], [1.0, 10.0]]),
            ([0.0, 10.0], vec![[-1.0, 12.0], [0.0, 12.0], [1.0, 12.0]]),
            ([0.0, 0.0], vec![[-1.0, 1.0], [0.0, 1.0], [1.0, 1.0]]),
            ([0.0, 0.0], vec![[-1.0, 0.5], [0.0, 0.5], [1.0, 0.5]]),
            ([0.0, 0.0], vec![[10.0, 10.0], [12.0, 14.0], [14.0, 10.0]]),
        ];
        for (dx, dy) in [(0.0, 0.0), (37.5, -1024.25), (-513.0, 257.0)] {
            for (center, ctrls) in &bases {
                let tc = [center[0] + dx, center[1] + dy];
                let tctrls: Vec<Pt> = ctrls.iter().map(|p| [p[0] + dx, p[1] + dy]).collect();
                let got = source_disk_clear(tc, &one, &tctrls);
                let c = lift(&tc).expect("finite");
                let rel: Vec<Rat> = tctrls
                    .iter()
                    .map(|p| {
                        let q = lift(p).expect("finite");
                        ((&q.0 - &c.0), (&q.1 - &c.1))
                    })
                    .collect();
                assert_eq!(got, source_disk_clear_native(&rel, &one));
                // Independent rational oracle on the promoted inputs.
                let op: Vec<(num_rational::BigRational, num_rational::BigRational)> = rel
                    .iter()
                    .map(|p| (p.0.to_rational(), p.1.to_rational()))
                    .collect();
                assert_eq!(got, source_disk_clear_oracle(&op, &one.to_rational()));
            }
        }
    }

    #[test]
    fn squared_radius_is_not_rounded_back_to_floating_point() {
        let one = BigRational::integer(1);
        let reach = one + BigRational::new(1.into(), (1u64 << 60).into());
        assert!(!source_disk_clear(
            [0.0, 0.0],
            &reach,
            &[[1.0, 0.0], [1.0, 0.0]]
        ));
    }
}

#[cfg(test)]
mod moving_substitution_tests {
    use super::super::geometry;
    use super::*;

    fn outline(control_x: f32) -> Vec<FittedCommand> {
        vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(4.0, 0.0),
            FittedCommand::QuadTo(control_x, 2.0, 4.0, 4.0),
            FittedCommand::LineTo(0.0, 4.0),
            FittedCommand::Close,
        ]
    }

    #[test]
    fn independent_moving_curve_certificate_keeps_fixed_curve_gate() {
        let up = outline(5.0);
        let moved = outline(5.25);
        let a = geometry::parse_commands(&up).unwrap();
        let b = geometry::parse_commands(&moved).unwrap();
        assert!(!compare_commands(&up, &up, &moved));
        assert!(compare_substituted(&a, &a, &b));
    }

    #[test]
    fn raw_coordinates_lift_without_f32_roundtrip_and_nonfinite_abstains() {
        let up = geometry::parse_commands(&outline(5.0)).unwrap();
        let mut raw = up.clone();
        raw.offcurve[0][0] += 1.0 / (1u64 << 40) as f64;
        assert_ne!(raw.offcurve[0][0], (raw.offcurve[0][0] as f32) as f64);
        assert!(compare_substituted(&raw, &up, &up));
        raw.offcurve[0][0] = f64::NAN;
        assert!(!compare_substituted(&raw, &up, &up));
    }

    #[test]
    fn open_or_mismatched_contours_do_not_receive_topology_certificate() {
        let up = geometry::parse_commands(&outline(5.0)).unwrap();
        let mut open = up.clone();
        open.contours[0].pop();
        assert!(!compare_substituted(&up, &up, &open));
    }

    #[test]
    fn prepared_signatures_match_independent_substitution_and_cache_failures() {
        fn legacy(a: &geometry::Parsed, b: &geometry::Parsed, c: &geometry::Parsed) -> bool {
            let shape = |p: &geometry::Parsed| {
                p.contours
                    .iter()
                    .map(|contour| {
                        contour
                            .iter()
                            .map(std::mem::discriminant)
                            .collect::<Vec<_>>()
                    })
                    .collect::<Vec<_>>()
            };
            if a.contours.is_empty() || shape(a) != shape(b) || shape(b) != shape(c) {
                return false;
            }
            let signature = |p: &geometry::Parsed| {
                topology::signature(&substituted_contours(&parsed_contours(p)?, 0)?)
            };
            match (signature(a), signature(b), signature(c)) {
                (Some(_), Some(up), Some(new)) => up == new,
                _ => false,
            }
        }
        let up = geometry::parse_commands(&outline(5.0)).unwrap();
        let moved = geometry::parse_commands(&outline(5.25)).unwrap();
        let mut raw = up.clone();
        raw.offcurve[0][0] += 1.0 / (1u64 << 40) as f64;
        let mut open = up.clone();
        open.contours[0].pop();
        let mut nonfinite = up.clone();
        nonfinite.offcurve[0][0] = f64::NAN;
        for source in [&raw, &up, &open, &nonfinite] {
            for candidate in [&up, &moved, &open, &nonfinite] {
                let a = PreparedSubstitution::new(source);
                let b = PreparedSubstitution::new(&up);
                let c = PreparedSubstitution::new(candidate);
                assert_eq!(compare_prepared(&a, &b, &c), legacy(source, &up, candidate));
                let cached = (a.signature.get(), b.signature.get(), c.signature.get());
                assert_eq!(compare_prepared(&a, &b, &c), legacy(source, &up, candidate));
                assert_eq!(
                    cached,
                    (a.signature.get(), b.signature.get(), c.signature.get())
                );
            }
        }
        let a = PreparedSubstitution::new(&up);
        let b = PreparedSubstitution::new(&up);
        let c = PreparedSubstitution::new(&open);
        assert!(!compare_prepared(&a, &b, &c));
        assert!(
            a.signature.get().is_none(),
            "shape guard precedes certification"
        );
        let bad = PreparedSubstitution::new(&nonfinite);
        assert!(!bad.is_valid());
        assert!(matches!(bad.signature.get(), Some(None)));
        assert!(!bad.is_valid());
        assert!(PreparedSubstitution::new(&moved).is_valid());
    }

    /// One square contour with a quad lid; the lid apex moves the candidate.
    fn lid_commands(apex: f32) -> Vec<FittedCommand> {
        vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(4.0, 0.0),
            FittedCommand::LineTo(4.0, 4.0),
            FittedCommand::QuadTo(2.0, apex, 0.0, 4.0),
            FittedCommand::Close,
        ]
    }

    fn apex_y(entries: &[Entry]) -> f64 {
        // Prepared y-interval of the lid control point (2, apex).
        for e in entries {
            if !e.curve {
                continue;
            }
            for (v, iv) in e.pts.iter().zip(e.pts_iv.as_ref().unwrap().iter()) {
                if v.0 == BigRational::integer(2) {
                    let ((_, _), (lo, hi)) = iv.bounds();
                    assert_eq!(lo, hi, "dyadic control takes the proven singleton");
                    return hi;
                }
            }
        }
        panic!("lid control missing");
    }

    #[test]
    fn fresh_candidate_gets_fresh_prepared_bounds() {
        // Far lid certifies; every entry carries bounds prepared from its
        // own exact hull.
        let far = parse_commands(&lid_commands(8.0)).unwrap();
        let entries = build_entries(&far, 0);
        assert!(entries.iter().all(|e| e
            .pts_iv
            .as_ref()
            .is_some_and(|iv| iv.len() == e.pts.len())
            && e.hull_iv
                .as_ref()
                .is_some_and(|iv| iv.len() == e.hull.len())));
        assert_eq!(apex_y(&entries), 8.0);
        let report = certify(&far, 0);
        assert!(report.ok, "{}", report.reason);
        // The moved lid touches a non-incident floor edge: the fresh
        // candidate rebuilds entries and bounds from the moved geometry,
        // so its verdict follows the move instead of stale intervals.
        let moved = parse_commands(&lid_commands(0.0)).unwrap();
        let moved_entries = build_entries(&moved, 0);
        assert_eq!(apex_y(&moved_entries), 0.0);
        let report = certify(&moved, 0);
        assert!(!report.ok);
        assert_eq!(report.reason, "hull-contact");
        // Translated/scaled copies of the far lid keep the verdict: the
        // prepared bounds move with the exact geometry.
        let mv = |x: f32, y: f32| {
            let (x, y) = (x * 2.0 + 37.0, y * 2.0 - 13.0);
            (x, y)
        };
        let (x0, y0) = mv(0.0, 0.0);
        let (x1, y1) = mv(4.0, 0.0);
        let (x2, y2) = mv(4.0, 4.0);
        let (cx, cy) = mv(2.0, 8.0);
        let (x3, y3) = mv(0.0, 4.0);
        let shifted = parse_commands(&[
            FittedCommand::MoveTo(x0, y0),
            FittedCommand::LineTo(x1, y1),
            FittedCommand::LineTo(x2, y2),
            FittedCommand::QuadTo(cx, cy, x3, y3),
            FittedCommand::Close,
        ])
        .unwrap();
        let report = certify(&shifted, 0);
        assert!(report.ok, "{}", report.reason);
    }

    #[test]
    fn entry_prepared_verdicts_match_exact_oracles() {
        // Prepared entry verdicts must equal the unfiltered exact narrow
        // phases wherever the filter is decisive, on the lid outlines
        // above in both positions.
        for apex in [8.0, 0.0] {
            let contours = parse_commands(&lid_commands(apex)).unwrap();
            let entries = build_entries(&contours, 0);
            let bounds: Vec<Option<filtered::BoundHull<'_>>> = entries
                .iter()
                .map(|e| {
                    e.hull_iv
                        .as_ref()
                        .and_then(|iv| filtered::BoundHull::new(&e.hull, iv))
                })
                .collect();
            for (i, a) in entries.iter().enumerate() {
                if a.curve {
                    let exact = is_chord_monotone_exact(&a.pts);
                    if let Some(v) = a
                        .pts_iv
                        .as_ref()
                        .and_then(|iv| filtered::BoundHull::new(&a.pts, iv))
                        .and_then(|b| filtered::chord_monotone_h(&b))
                    {
                        assert_eq!(v, exact);
                    }
                }
                for (j, b) in entries.iter().enumerate() {
                    if i == j {
                        continue;
                    }
                    if let (Some(x), Some(y)) = (bounds[i].as_ref(), bounds[j].as_ref()) {
                        if let Some(v) = filtered::polys_strictly_disjoint_h(x, y) {
                            assert_eq!(v, strictly_disjoint_exact(&a.hull, &b.hull));
                        }
                        for shared in [&a.pts[0], &b.pts[0]] {
                            if let Some(v) = filtered::hulls_meet_only_at_h(x, y, shared) {
                                assert_eq!(v, hulls_meet_only_at_exact(&a.hull, &b.hull, shared));
                            }
                        }
                    }
                }
            }
        }
    }
}
