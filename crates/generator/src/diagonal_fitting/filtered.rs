//! Certified interval filters for exact geometric predicates.
//!
//! Source architecture: CGAL `Filtered_predicate`
//! ([kernel adaptor](https://doc.cgal.org/latest/Kernel_23/classCGAL_1_1Filtered__predicate.html),
//! [reference implementation](https://github.com/CGAL/cgal/blob/main/Filtered_kernel/include/CGAL/Filtered_predicate.h))
//! with Shewchuk-style adaptive error bounds
//! ([predicates](https://www.cs.cmu.edu/~quake/robust.html)). A
//! checked-integer tier ([dyadic](super::dyadic), after Shewchuk's exact
//! predicates and [CGAL's lazy exact numbers](https://doc.cgal.org/latest/Number_types/classCGAL_1_1Lazy__exact__nt.html))
//! proves dyadic predicates with `i128` arithmetic first. Project
//! adaptation: enclose every exact rational input in a proven `f64`
//! interval, evaluate the predicate with outward-rounded interval
//! arithmetic, and run the original exact fallback whenever the enclosure
//! is not decisive. No heuristic epsilon decides a verdict: indecision
//! always falls back. Portable: no rounding-mode changes, so native and
//! WASM share the same semantics.

use super::dyadic;
use super::exact::Exact as BigRational;
use num_bigint::{BigUint, Sign};
use num_traits::{ToPrimitive, Zero};

/// One endpoint pair: `lo <= exact <= hi`, both finite.
#[derive(Clone, Copy, Debug)]
struct Interval {
    lo: f64,
    hi: f64,
}

/// Exact input coordinate pair.
type Coords<'a> = (&'a BigRational, &'a BigRational);

/// Interval point with per-coordinate enclosures and the prepared
/// checked-integer image from the same exact input (when dyadic), never
/// from rounded `f64`. One preparation per immutable geometry; hull
/// predicates reuse these without rebuilding `BigRational` determinants.
#[derive(Clone, Copy, Debug)]
pub(crate) struct PtI {
    x: Interval,
    y: Interval,
    dy: Option<dyadic::DyPt>,
}

impl PtI {
    /// Prepared enclosure endpoints `((lo_x, hi_x), (lo_y, hi_y))`, used
    /// by caller tests to check bounds track their exact geometry.
    #[cfg(test)]
    pub(crate) fn bounds(&self) -> ((f64, f64), (f64, f64)) {
        ((self.x.lo, self.x.hi), (self.y.lo, self.y.hi))
    }
}

/// Exact upward successor without relying on platform libm.
fn up(f: f64) -> f64 {
    if f.is_nan() || f == f64::INFINITY {
        return f;
    }
    if f == 0.0 {
        // Covers both signed zeros: the successor of zero is the smallest
        // positive subnormal.
        return f64::from_bits(1);
    }
    let bits = f.to_bits();
    f64::from_bits(if f > 0.0 { bits + 1 } else { bits - 1 })
}

/// Exact downward predecessor without relying on platform libm.
fn down(f: f64) -> f64 {
    if f.is_nan() || f == f64::NEG_INFINITY {
        return f;
    }
    if f == 0.0 {
        return f64::from_bits(0x8000_0000_0000_0001);
    }
    let bits = f.to_bits();
    f64::from_bits(if f > 0.0 { bits - 1 } else { bits + 1 })
}

/// Two outward steps contain one rounding (half an ulp). Any nonfinite
/// operand or widened endpoint (overflow, infinite arithmetic, NaN)
/// returns `None` so the exact fallback decides; every kept `Interval`
/// is finite on both ends.
fn outward(lo: f64, hi: f64) -> Option<Interval> {
    if !lo.is_finite() || !hi.is_finite() {
        return None;
    }
    let out = Interval {
        lo: down(down(lo)),
        hi: up(up(hi)),
    };
    if !out.lo.is_finite() || !out.hi.is_finite() {
        return None;
    }
    Some(out)
}

fn add(a: Interval, b: Interval) -> Option<Interval> {
    outward(a.lo + b.lo, a.hi + b.hi)
}

fn sub(a: Interval, b: Interval) -> Option<Interval> {
    outward(a.lo - b.hi, a.hi - b.lo)
}

fn mul(a: Interval, b: Interval) -> Option<Interval> {
    let ps = [a.lo * b.lo, a.lo * b.hi, a.hi * b.lo, a.hi * b.hi];
    if ps.iter().any(|p| p.is_nan()) {
        return None;
    }
    let (mut lo, mut hi) = (ps[0], ps[0]);
    for p in ps.iter().skip(1) {
        lo = lo.min(*p);
        hi = hi.max(*p);
    }
    outward(lo, hi)
}

/// Widen one correctly-rounded quotient into a containing interval.
fn widen(f: f64) -> Interval {
    Interval {
        lo: down(down(f)),
        hi: up(up(f)),
    }
}

/// Exact IEEE singleton for a normal binary fraction with at most 53
/// significant bits. Constructing its significand and exponent changes
/// no value bits; larger or subnormal values use the general proof.
fn enclose_dyadic_fast(r: &BigRational) -> Option<Interval> {
    let d = r.small_dyadic()?;
    let m = d.m.unsigned_abs();
    let width = 128 - m.leading_zeros();
    if width == 0 || width > 53 {
        return None;
    }
    let exponent = i64::from(d.e) + i64::from(width) - 1;
    if !(-1022..=1023).contains(&exponent) {
        return None;
    }
    let significand = (m as u64) << (53 - width);
    let sign = if d.m < 0 { 1u64 << 63 } else { 0 };
    let bits = sign | (((exponent + 1023) as u64) << 52) | (significand & ((1u64 << 52) - 1));
    let f = f64::from_bits(bits);
    Some(Interval { lo: f, hi: f })
}

/// Proven enclosure of one exact rational, or `None` when the magnitude
/// overflows finite `f64`, or a subnormal cannot be proved by the exact
/// roundtrip. Such values defer to exact predicates.
/// Non-dyadic rationals are enclosed by bit construction, never by
/// rounding the quotient.
fn enclose_rational(r: &BigRational) -> Option<Interval> {
    if r.is_zero() {
        return Some(Interval { lo: 0.0, hi: 0.0 });
    }
    if let Some(iv) = enclose_dyadic_fast(r) {
        return Some(iv);
    }
    let f = r.to_f64()?;
    if !f.is_finite() {
        return None;
    }
    // Roundtrip identity is an exactness proof, not a floating guess:
    // `from_f64(f) == r` holds only when `f` is exactly `r`, independent
    // of how `to_f64` rounded.
    if BigRational::from_f64(f).as_ref() == Some(r) {
        return Some(Interval { lo: f, hi: f });
    }
    enclose_slow(r)
}

/// Bit-constructed enclosure for rationals not exactly representable as
/// `f64` (e.g. thirds): with `e = floor(log2(|r|))` and
/// `m = floor(|r| * 2^(52-e))`, the value lies in `[m, m+1] * 2^(e-52)`,
/// both bounds exactly representable when `e` is a normal exponent.
/// Overflow, subnormal magnitudes and oversized inputs return `None`.
fn enclose_slow(r: &BigRational) -> Option<Interval> {
    const MAX_BYTES: usize = 512;
    let rational = r.to_rational();
    let (sign, nb) = rational.numer().to_bytes_be();
    let (_, db) = rational.denom().to_bytes_be();
    if nb.len() + db.len() > MAX_BYTES {
        return None;
    }
    let n = BigUint::from_bytes_be(&nb);
    let d = BigUint::from_bytes_be(&db);
    let en = n.bits() as i64 - 1;
    let ed = d.bits() as i64 - 1;
    let mut e = en - ed;
    if e >= 0 {
        if n < (&d << (e as usize)) {
            e -= 1;
        }
    } else if (&n << ((-e) as usize)) < d {
        e -= 1;
    }
    if e < -1022 || e > 1023 {
        return None;
    }
    let shift = 52 - e;
    let (m, rem) = if shift >= 0 {
        let t = &n << (shift as usize);
        (&t / &d, &t % &d)
    } else {
        let t = &d << ((-shift) as usize);
        (&n / &t, &n % &t)
    };
    let m64 = m.to_u64()?;
    if m64 < (1u64 << 52) || m64 >= (1u64 << 53) {
        return None;
    }
    let bits = ((e + 1023) as u64) << 52 | (m64 - (1u64 << 52));
    let lo = f64::from_bits(bits);
    if !lo.is_finite() {
        return None;
    }
    let hi = if rem.is_zero() {
        lo
    } else {
        // A successor past MAX is +Inf: fall back rather than widen.
        let up = f64::from_bits(bits + 1);
        if !up.is_finite() {
            return None;
        }
        up
    };
    if matches!(sign, Sign::Minus) {
        Some(Interval { lo: -hi, hi: -lo })
    } else {
        Some(Interval { lo, hi })
    }
}

fn small_point(p: Coords) -> Option<dyadic::DyPt> {
    Some(dyadic::DyPt {
        x: p.0.small_dyadic()?,
        y: p.1.small_dyadic()?,
    })
}

fn enclose_point(p: Coords) -> Option<PtI> {
    Some(PtI {
        x: enclose_rational(p.0)?,
        y: enclose_rational(p.1)?,
        dy: small_point(p),
    })
}

fn enclose_slice(ps: &[(BigRational, BigRational)]) -> Option<Vec<PtI>> {
    ps.iter().map(|p| enclose_point((&p.0, &p.1))).collect()
}

/// Prepared interval bounds for one immutable exact hull.
///
/// The cached approximate representation is computed once via
/// `enclose_hull` and reused across every orientation/SAT/shared-contact
/// call in the owning scope, mirroring the CGAL `Lazy_exact_nt` pattern
/// of keeping an approximate value alongside the exact one
/// ([lazy exact number type](https://doc.cgal.org/latest/Number_types/classCGAL_1_1Lazy__exact__nt.html);
/// adaptation is ours). The checked-integer images ride inside each
/// `PtI`, prepared once from the same exact input and borrowed here, so
/// preparing a hull allocates no second vector per pair. Scope is
/// strictly call-local with geometry ownership: no global, persistent or
/// pointer-identity caches, so a fresh candidate always prepares fresh
/// bounds and moved geometry can never reuse stale intervals in these
/// scopes. Callers must pair the exact slice with the bounds prepared
/// from it; the length check only rejects truncation, not a different
/// hull with the same vertex count.
pub(crate) struct BoundHull<'a> {
    exact: &'a [Rat],
    iv: &'a [PtI],
}

impl<'a> BoundHull<'a> {
    /// Bind an exact hull to its prepared bounds. A length mismatch
    /// (impossible when both come from the same `enclose_hull` call)
    /// fails closed so callers run the exact fallback.
    pub(crate) fn new(exact: &'a [Rat], iv: &'a [PtI]) -> Option<Self> {
        (exact.len() == iv.len()).then_some(Self { exact, iv })
    }
}

/// Enclose one immutable exact hull once for later reuse; `None` runs
/// the exact fallback.
pub(crate) fn enclose_hull(exact: &[Rat]) -> Option<Vec<PtI>> {
    enclose_slice(exact)
}

/// Certified sign of `(b-a) x (c-a)`: `Some` is provably the exact sign,
/// including true exact zero from the checked-integer tier; `None`
/// (straddle, NaN, unenclosable input) runs the exact fallback.
pub(crate) fn orient_sign(a: Coords, b: Coords, c: Coords) -> Option<i8> {
    if let Some(s) = small_point(a)
        .zip(small_point(b))
        .zip(small_point(c))
        .and_then(|((a, b), c)| dyadic::orient(&a, &b, &c))
    {
        return Some(s);
    }
    let (ae, be, ce) = (enclose_point(a)?, enclose_point(b)?, enclose_point(c)?);
    orient_i(&ae, &be, &ce)
}

fn orient_i(a: &PtI, b: &PtI, c: &PtI) -> Option<i8> {
    let x1 = sub(b.x, a.x)?;
    let y1 = sub(b.y, a.y)?;
    let x2 = sub(c.x, a.x)?;
    let y2 = sub(c.y, a.y)?;
    let d = sub(mul(x1, y2)?, mul(y1, x2)?)?;
    if d.hi < 0.0 {
        Some(-1)
    } else if d.lo > 0.0 {
        Some(1)
    } else {
        None
    }
}

/// Certified strict positivity of the dot product of two displacements,
/// same contract: `Some` is provably the exact verdict.
fn dot_vec_positive(ax: Interval, ay: Interval, bx: Interval, by: Interval) -> Option<bool> {
    let d = add(mul(ax, bx)?, mul(ay, by)?)?;
    if d.lo > 0.0 {
        Some(true)
    } else if d.hi <= 0.0 {
        Some(false)
    } else {
        None
    }
}

/// Strict separation: `Some(true)` proves the exact narrow phase separates
/// on the same axis with the same strict gap; `Some(false)` proves exact
/// overlap on every axis, so the exact rerun finds no gap either. Callers
/// that only consume `Some(true)` keep their verdict by running the
/// fallback on `Some(false)`; consuming it skips that rerun. `None` runs
/// the exact test (touch, overlap and degenerate cases).
pub(crate) fn polys_strictly_disjoint(
    p: &[(BigRational, BigRational)],
    q: &[(BigRational, BigRational)],
) -> Option<bool> {
    if p.is_empty() || q.is_empty() {
        return None;
    }
    let (pe, qe) = (enclose_slice(p)?, enclose_slice(q)?);
    polys_disjoint_inner(p, &pe, q, &qe)
}

/// Same verdict reusing bounds prepared once per immutable hull.
pub(crate) fn polys_strictly_disjoint_h(a: &BoundHull<'_>, b: &BoundHull<'_>) -> Option<bool> {
    if a.exact.is_empty() || b.exact.is_empty() {
        return None;
    }
    polys_disjoint_inner(a.exact, a.iv, b.exact, b.iv)
}

/// Certified gap on one interval axis: `Some(true)` proves a strict gap,
/// `None` is undecided on this axis only.
fn gap_on_axis(nx: Interval, ny: Interval, pe: &[PtI], qe: &[PtI]) -> Option<bool> {
    let bounds = |pts: &[PtI]| -> Option<(f64, f64)> {
        let (mut lo, mut hi) = (f64::INFINITY, f64::NEG_INFINITY);
        for v in pts {
            let d = add(mul(v.x, nx)?, mul(v.y, ny)?)?;
            lo = lo.min(d.lo);
            hi = hi.max(d.hi);
        }
        Some((lo, hi))
    };
    let (p_lo, p_hi) = bounds(pe)?;
    let (q_lo, q_hi) = bounds(qe)?;
    Some(p_hi < q_lo || q_hi < p_lo)
}

fn polys_disjoint_inner(
    p: &[(BigRational, BigRational)],
    pe: &[PtI],
    q: &[(BigRational, BigRational)],
    qe: &[PtI],
) -> Option<bool> {
    // Edge list with the same degenerate rule as the exact phase: only
    // zero-length edges are skipped, never generic segment separation.
    let mut edges: Vec<(bool, usize, usize)> = Vec::new();
    for (first, poly) in [(true, p), (false, q)] {
        if poly.len() < 2 {
            continue;
        }
        for i in 0..poly.len() {
            let j = (i + 1) % poly.len();
            if poly[i] == poly[j] {
                continue;
            }
            edges.push((first, i, j));
        }
    }
    if edges.is_empty() {
        return None;
    }
    // Interval phase: a proven gap returns at once; an undecided axis is
    // skipped so later axes still decide, keeping every proven subresult.
    for &(first, i, j) in &edges {
        let e = if first { pe } else { qe };
        let (Some(nx), Some(ny)) = (sub(e[i].y, e[j].y), sub(e[j].x, e[i].x)) else {
            continue;
        };
        if gap_on_axis(nx, ny, pe, qe) == Some(true) {
            return Some(true);
        }
    }
    // Checked-integer phase: exact projections on every axis over the
    // prepared images. A proven gap returns at once; overlap needs every
    // axis decisive, otherwise the chain defers to the fallback.
    dyadic_disjoint(p, q, pe, qe)
}

/// Exact SAT over checked integers with the same degenerate axes as the
/// exact phase. `Some(false)` is a proven verdict, not indecision: every
/// extremum comparison on every axis decided exactly. Any undecided
/// comparison defers, never a stale extremum or a false overlap.
fn dyadic_disjoint(p: &[Rat], q: &[Rat], pe: &[PtI], qe: &[PtI]) -> Option<bool> {
    use std::cmp::Ordering::{Greater, Less};
    if pe.len() != p.len() || qe.len() != q.len() {
        return None;
    }
    let at = |e: &[PtI], i: usize| -> Option<dyadic::DyPt> { e.get(i)?.dy };
    let proj = |v: &[PtI], nx: dyadic::Dy, ny: dyadic::Dy| -> Option<(dyadic::Dy, dyadic::Dy)> {
        let first = at(v, 0)?;
        let mut lo = dyadic::dot(first.x, first.y, nx, ny)?;
        let mut hi = lo;
        for u in &v[1..] {
            let d = dyadic::dot(u.dy?.x, u.dy?.y, nx, ny)?;
            match dyadic::cmp(d, lo) {
                Some(Less) => lo = d,
                Some(_) => {}
                None => return None,
            }
            match dyadic::cmp(d, hi) {
                Some(Greater) => hi = d,
                Some(_) => {}
                None => return None,
            }
        }
        Some((lo, hi))
    };
    let mut any_axis = false;
    let mut uncertain = false;
    for (poly, e) in [(p, pe), (q, qe)] {
        if poly.len() < 2 {
            continue;
        }
        for i in 0..poly.len() {
            let j = (i + 1) % poly.len();
            if poly[i] == poly[j] {
                continue;
            }
            any_axis = true;
            let (Some(di), Some(dj)) = (at(e, i), at(e, j)) else {
                uncertain = true;
                continue;
            };
            let (Some(nx), Some(ny)) = (dyadic::sub(di.y, dj.y), dyadic::sub(dj.x, di.x)) else {
                uncertain = true;
                continue;
            };
            let (Some(pp), Some(qq)) = (proj(pe, nx, ny), proj(qe, nx, ny)) else {
                uncertain = true;
                continue;
            };
            match (dyadic::cmp(pp.1, qq.0), dyadic::cmp(qq.1, pp.0)) {
                (Some(Less), _) | (_, Some(Less)) => return Some(true),
                (Some(_), Some(_)) => {}
                _ => uncertain = true,
            }
        }
    }
    if uncertain {
        None
    } else {
        any_axis.then_some(false)
    }
}

/// Exact point pair.
type Rat = (BigRational, BigRational);

/// Exact orientation of one rational triple: the local fallback for one
/// undecided subpredicate, identical to the outer exact narrow phase.
fn orient_exact_local(a: &Rat, b: &Rat, c: &Rat) -> i8 {
    let v = (&b.0 - &a.0) * (&c.1 - &a.1) - (&b.1 - &a.1) * (&c.0 - &a.0);
    if v.is_zero() {
        0
    } else if v.is_positive() {
        1
    } else {
        -1
    }
}

/// Certified orientation with local resolution: algebraic zero, then the
/// checked-integer tier, then the interval, then one exact determinant.
/// Decided subresults are kept; uncertainty never discards them.
#[allow(clippy::too_many_arguments)]
fn orient_resolved(
    xe: &Rat,
    ye: &Rat,
    ze: &Rat,
    xd: Option<&dyadic::DyPt>,
    yd: Option<&dyadic::DyPt>,
    zd: Option<&dyadic::DyPt>,
    xi: &PtI,
    yi: &PtI,
    zi: &PtI,
) -> i8 {
    if xe == ye || ye == ze || xe == ze {
        return 0;
    }
    if let (Some(x), Some(y), Some(z)) = (xd, yd, zd) {
        if let Some(s) = dyadic::orient(x, y, z) {
            return s;
        }
    }
    if let Some(s) = orient_i(xi, yi, zi) {
        return s;
    }
    orient_exact_local(xe, ye, ze)
}

/// Exact bounding-box hit test (comparisons only, no products).
fn box_hit(
    w: &(BigRational, BigRational),
    u: &(BigRational, BigRational),
    v: &(BigRational, BigRational),
) -> bool {
    use std::cmp::{max, min};
    let (lox, hix) = (min(&u.0, &v.0), max(&u.0, &v.0));
    let (loy, hiy) = (min(&u.1, &v.1), max(&u.1, &v.1));
    lox <= &w.0 && &w.0 <= hix && loy <= &w.1 && &w.1 <= hiy
}

/// Certified meet-at-most-at certificate: `Some` provably equals the exact
/// verdict in both directions; `None` runs the exact test. Every check is
/// an exact identity, an exact box comparison, or a locally resolved
/// orientation with the same exact value the fallback computes. A
/// shared-junction contact passes without proving collinearity, exactly
/// as the fallback does.
pub(crate) fn hulls_meet_only_at(p: &[Rat], q: &[Rat], shared: &Rat) -> Option<bool> {
    let (pe, qe) = (enclose_slice(p)?, enclose_slice(q)?);
    hulls_meet_inner(p, &pe, q, &qe, shared)
}

/// Same verdict reusing bounds prepared once per immutable hull.
pub(crate) fn hulls_meet_only_at_h(
    a: &BoundHull<'_>,
    b: &BoundHull<'_>,
    shared: &Rat,
) -> Option<bool> {
    hulls_meet_inner(a.exact, a.iv, b.exact, b.iv, shared)
}

/// Exact on-segment test for one locally resolved contact, mirroring the
/// outer exact narrow phase.
fn on_segment_exact_local(a: &Rat, b: &Rat, p: &Rat) -> bool {
    use std::cmp::{max, min};
    orient_exact_local(a, b, p) == 0
        && min(&a.0, &b.0) <= &p.0
        && &p.0 <= max(&a.0, &b.0)
        && min(&a.1, &b.1) <= &p.1
        && &p.1 <= max(&a.1, &b.1)
}

/// Exact outside test for one locally resolved vertex, mirroring the
/// outer exact narrow phase.
fn outside_exact_local(pt: &Rat, poly: &[Rat]) -> bool {
    if poly.is_empty() {
        return true;
    }
    if poly.len() == 1 {
        return pt != &poly[0];
    }
    if poly.len() == 2 {
        let (a, b) = (&poly[0], &poly[1]);
        return !(pt == a || pt == b || on_segment_exact_local(a, b, pt));
    }
    let ccw = orient_exact_local(&poly[0], &poly[1], &poly[2]) > 0;
    for i in 1..poly.len() - 1 {
        let (t0, t1, t2) = (&poly[0], &poly[i], &poly[i + 1]);
        let (s0, s1, s2) = (
            orient_exact_local(t0, t1, pt),
            orient_exact_local(t1, t2, pt),
            orient_exact_local(t2, t0, pt),
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

/// Certified outside test with local resolution: the interval verdict
/// when decisive, else one exact fan test.
fn outside_resolved(pt_i: &PtI, pt: &Rat, poly: &[Rat], polye: &[PtI]) -> bool {
    if let Some(v) = outside_i(pt_i, pt, poly, polye) {
        return v;
    }
    outside_exact_local(pt, poly)
}

fn hulls_meet_inner(p: &[Rat], pe: &[PtI], q: &[Rat], qe: &[PtI], shared: &Rat) -> Option<bool> {
    // Prepared checked-integer images, one lookup per vertex.
    fn at(e: &[PtI], i: usize) -> Option<&dyadic::DyPt> {
        e.get(i)?.dy.as_ref()
    }
    for (ia, ib) in &poly_edges(p.len()) {
        for (jc, jd) in &poly_edges(q.len()) {
            // Locally resolved signs: an algebraic zero kills its crossing
            // term soundly; every other sign equals its exact value.
            let o = [
                orient_resolved(
                    &p[*ia],
                    &p[*ib],
                    &q[*jc],
                    at(pe, *ia),
                    at(pe, *ib),
                    at(qe, *jc),
                    &pe[*ia],
                    &pe[*ib],
                    &qe[*jc],
                ),
                orient_resolved(
                    &p[*ia],
                    &p[*ib],
                    &q[*jd],
                    at(pe, *ia),
                    at(pe, *ib),
                    at(qe, *jd),
                    &pe[*ia],
                    &pe[*ib],
                    &qe[*jd],
                ),
                orient_resolved(
                    &q[*jc],
                    &q[*jd],
                    &p[*ia],
                    at(qe, *jc),
                    at(qe, *jd),
                    at(pe, *ia),
                    &qe[*jc],
                    &qe[*jd],
                    &pe[*ia],
                ),
                orient_resolved(
                    &q[*jc],
                    &q[*jd],
                    &p[*ib],
                    at(qe, *jc),
                    at(qe, *jd),
                    at(pe, *ib),
                    &qe[*jc],
                    &qe[*jd],
                    &pe[*ib],
                ),
            ];
            if o[0] * o[1] < 0 && o[2] * o[3] < 0 {
                return Some(false);
            }
            // Contact checks mirror the fallback: a nonzero sign or an
            // exact box miss rules the contact out; a box hit at the shared
            // junction is allowed; a proven on-segment contact elsewhere
            // rejects.
            let checks = [
                (&q[*jc], &p[*ia], &p[*ib], o[0]),
                (&q[*jd], &p[*ia], &p[*ib], o[1]),
                (&p[*ia], &q[*jc], &q[*jd], o[2]),
                (&p[*ib], &q[*jc], &q[*jd], o[3]),
            ];
            for (w, u, v, s) in &checks {
                if *s != 0 {
                    continue;
                }
                if !box_hit(w, u, v) {
                    continue;
                }
                if *w == shared {
                    continue;
                }
                return Some(false);
            }
        }
    }
    for (i, v) in p.iter().enumerate() {
        if v != shared && !outside_resolved(&pe[i], v, q, qe) {
            return Some(false);
        }
    }
    for (j, v) in q.iter().enumerate() {
        if v != shared && !outside_resolved(&qe[j], v, p, pe) {
            return Some(false);
        }
    }
    Some(true)
}

/// Closed-loop edge index pairs, mirroring the exact `poly_edges`.
fn poly_edges(n: usize) -> Vec<(usize, usize)> {
    if n < 2 {
        return Vec::new();
    }
    (0..n).map(|i| (i, (i + 1) % n)).collect()
}

/// Certified segment-aware outside test with the same contract.
fn outside_i(
    pt: &PtI,
    exact: &(BigRational, BigRational),
    poly: &[(BigRational, BigRational)],
    polye: &[PtI],
) -> Option<bool> {
    if poly.is_empty() {
        return Some(true);
    }
    if poly.len() == 1 {
        return Some(exact != &poly[0]);
    }
    if poly.len() == 2 {
        let (a, b) = (&poly[0], &poly[1]);
        if exact == a || exact == b {
            return Some(false);
        }
        match orient_i(&polye[0], &polye[1], pt) {
            Some(_) => return Some(true),
            None => {
                // Collinearity unproven: an exact box miss still proves
                // outside without any products.
                use std::cmp::{max, min};
                if &exact.0 < min(&a.0, &b.0)
                    || &exact.0 > max(&a.0, &b.0)
                    || &exact.1 < min(&a.1, &b.1)
                    || &exact.1 > max(&a.1, &b.1)
                {
                    return Some(true);
                }
                return None;
            }
        }
    }
    let ccw = match orient_i(&polye[0], &polye[1], &polye[2])? {
        s => s > 0,
    };
    for i in 1..poly.len() - 1 {
        let s0 = orient_i(&polye[0], &polye[i], pt)?;
        let s1 = orient_i(&polye[i], &polye[i + 1], pt)?;
        let s2 = orient_i(&polye[i + 1], &polye[0], pt)?;
        if ccw && s0 >= 0 && s1 >= 0 && s2 >= 0 {
            return Some(false);
        }
        if !ccw && s0 <= 0 && s1 <= 0 && s2 <= 0 {
            return Some(false);
        }
    }
    Some(true)
}

/// Certified chord-monotone certificate with the same contract: the
/// checked-integer tier decides dyadic chains exactly, the interval
/// decides the rest, and `None` runs the exact test.
pub(crate) fn chord_monotone(ctrls: &[(BigRational, BigRational)]) -> Option<bool> {
    if ctrls.len() < 2 {
        return Some(false);
    }
    let (first, last) = (&ctrls[0], &ctrls[ctrls.len() - 1]);
    if first == last {
        return Some(false);
    }
    let ce = enclose_slice(ctrls)?;
    chord_monotone_inner(&ce)
}

/// Same verdict reusing bounds prepared once per immutable control chain.
pub(crate) fn chord_monotone_h(hull: &BoundHull<'_>) -> Option<bool> {
    if hull.exact.len() < 2 {
        return Some(false);
    }
    let (first, last) = (&hull.exact[0], &hull.exact[hull.exact.len() - 1]);
    if first == last {
        return Some(false);
    }
    chord_monotone_inner(hull.iv)
}

/// Exact leg loop over the prepared images: `Some` is the exact verdict,
/// `None` defers (missing image or overflowed leg). Never a stale dot.
fn dyadic_prepared(ce: &[PtI]) -> Option<bool> {
    let n = ce.len();
    if n < 2 {
        return None;
    }
    let get = |i: usize| -> Option<dyadic::DyPt> { ce.get(i)?.dy };
    let (a, b) = (get(0)?, get(n - 1)?);
    if a == b {
        return Some(false);
    }
    let (cx, cy) = (dyadic::sub(b.x, a.x)?, dyadic::sub(b.y, a.y)?);
    if cx.m == 0 && cy.m == 0 {
        return Some(false);
    }
    for i in 0..n - 1 {
        let (u, v) = (get(i)?, get(i + 1)?);
        let (lx, ly) = (dyadic::sub(v.x, u.x)?, dyadic::sub(v.y, u.y)?);
        match dyadic::dot(lx, ly, cx, cy) {
            Some(d) if dyadic::sign(d) == 1 => {}
            Some(_) => return Some(false),
            None => return None,
        }
    }
    Some(true)
}

fn chord_monotone_inner(ce: &[PtI]) -> Option<bool> {
    // Prepared checked-integer images decide dyadic chains exactly; the
    // interval decides the rest and `None` runs the exact test.
    if let Some(v) = dyadic_prepared(ce) {
        return Some(v);
    }
    let n = ce.len();
    if n < 2 {
        return None;
    }
    let (cx, cy) = (sub(ce[n - 1].x, ce[0].x)?, sub(ce[n - 1].y, ce[0].y)?);
    for w in ce.windows(2) {
        let (lx, ly) = (sub(w[1].x, w[0].x)?, sub(w[1].y, w[0].y)?);
        match dot_vec_positive(lx, ly, cx, cy)? {
            true => {}
            false => return Some(false),
        }
    }
    Some(true)
}

/// Acceptance-only source-contact certificate for one quadratic over
/// CENTER-RELATIVE points (controls minus center, as the exact narrow
/// phase builds them): `Some(true)` proves the exact depth-12 Bernstein
/// verdict is clearance; `None` runs the exact recursion (tangency,
/// contact and indecision all fall back, so the finite-depth verdicts
/// and the exact radius-squared input are preserved). Taking relative
/// points avoids any second center subtraction.
pub(crate) fn source_quad_clear(reach: &BigRational, points: &[Rat]) -> Option<bool> {
    if points.len() != 3 {
        return None;
    }
    let r = enclose_rational(reach)?;
    let pe = enclose_slice(points)?;
    visit_quad(&[pe[0], pe[1], pe[2]], &r, 0)
}

/// Exact Bernstein weight intervals for the quadratic product rule
/// (weights 1, 1/2, 1/6, 2/3); the two rounded quotients are widened.
fn weight(i: usize, j: usize) -> Interval {
    const C2: [f64; 3] = [1.0, 2.0, 1.0];
    const C4: [f64; 5] = [1.0, 4.0, 6.0, 4.0, 1.0];
    let exact = C2[i] * C2[j] / C4[i + j];
    if exact == 1.0 || exact == 0.5 {
        Interval {
            lo: exact,
            hi: exact,
        }
    } else {
        widen(exact)
    }
}

fn midpoint_i(a: Interval, b: Interval) -> Option<Interval> {
    const HALF: Interval = Interval { lo: 0.5, hi: 0.5 };
    mul(add(a, b)?, HALF)
}

fn midpoint_p(a: &PtI, b: &PtI) -> Option<PtI> {
    Some(PtI {
        x: midpoint_i(a.x, b.x)?,
        y: midpoint_i(a.y, b.y)?,
        dy: None,
    })
}

fn subdivide_i(q: &[PtI; 3]) -> Option<([PtI; 3], [PtI; 3])> {
    let m01 = midpoint_p(&q[0], &q[1])?;
    let m12 = midpoint_p(&q[1], &q[2])?;
    let m = midpoint_p(&m01, &m12)?;
    Some(([q[0], m01, m], [m, m12, q[2]]))
}

fn visit_quad(q: &[PtI; 3], reach: &Interval, depth: usize) -> Option<bool> {
    const DEPTH: usize = 12;
    let mut all_nonneg = true;
    let mut all_neg = true;
    for k in 0..5 {
        let mut sum: Option<Interval> = None;
        for i in 0..3 {
            for j in 0..3 {
                if i + j != k {
                    continue;
                }
                let dot = add(mul(q[i].x, q[j].x)?, mul(q[i].y, q[j].y)?)?;
                let term = mul(dot, weight(i, j))?;
                sum = Some(match sum {
                    Some(s) => add(s, term)?,
                    None => term,
                });
            }
        }
        let c = sub(sum?, *reach)?;
        if c.lo < 0.0 {
            all_nonneg = false;
        }
        if !(c.hi < 0.0) {
            all_neg = false;
        }
    }
    if all_nonneg {
        return Some(true);
    }
    if depth >= DEPTH {
        return None;
    }
    if all_neg {
        // The exact verdict is rejection; acceptance-only defers to it.
        return None;
    }
    let (left, right) = subdivide_i(q)?;
    match (
        visit_quad(&left, reach, depth + 1)?,
        visit_quad(&right, reach, depth + 1)?,
    ) {
        (true, true) => Some(true),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::super::curves::{source_disk_clear, source_disk_clear_exact};
    use super::*;
    use num_bigint::BigInt;

    type Rat = (BigRational, BigRational);

    fn int_rat(n: i128) -> BigRational {
        BigRational::from_integer(n.into())
    }

    fn rat(n: i128, d: i128) -> BigRational {
        BigRational::new(n.into(), d.into())
    }

    #[test]
    fn scalar_enclosures_contain_independent_rational_values() {
        use num_rational::BigRational as Oracle;
        use num_traits::FromPrimitive;
        let mut decided = 0;
        let mut deferred = 0;
        for exponent in (-1100..=1100).step_by(19) {
            for mantissa in [
                0,
                1,
                -1,
                3,
                (1i128 << 53) - 1,
                (1i128 << 53) + 1,
                i128::MAX,
                i128::MIN,
            ] {
                for divisor in [1, 3, 113] {
                    let mut n = BigInt::from(mantissa);
                    let mut d = BigInt::from(divisor);
                    if exponent >= 0 {
                        n <<= exponent as usize;
                    } else {
                        d <<= (-exponent) as usize;
                    }
                    let oracle = Oracle::new(n, d);
                    let value = BigRational::from_rational(oracle.clone());
                    match enclose_rational(&value) {
                        Some(iv) => {
                            decided += 1;
                            assert!(iv.lo.is_finite() && iv.hi.is_finite());
                            assert!(Oracle::from_f64(iv.lo).unwrap() <= oracle);
                            assert!(oracle <= Oracle::from_f64(iv.hi).unwrap());
                        }
                        None => deferred += 1,
                    }
                }
            }
        }
        assert!(decided > 0 && deferred > 0);
    }

    fn pt(x: BigRational, y: BigRational) -> Rat {
        (x, y)
    }

    /// Independent containment oracle: exact comparisons only.
    fn contains(r: &BigRational, lo: f64, hi: f64) -> bool {
        let (l, h) = (
            BigRational::from_f64(lo).unwrap(),
            BigRational::from_f64(hi).unwrap(),
        );
        &l <= r && r <= &h
    }

    fn enclosed(r: &BigRational) -> Interval {
        enclose_rational(r).expect("enclosure must succeed here")
    }

    #[test]
    fn enclosure_contains_dyadics_thirds_and_binade_edges() {
        for f in [3.984375, -1.3125, 1.0 / 128.0, 0.0, 2.0f64.powi(-1074)] {
            let r = BigRational::from_f64(f).unwrap();
            let iv = enclosed(&r);
            assert_eq!((iv.lo, iv.hi), (f, f));
        }
        for (n, d) in [(1, 3), (-2, 3), (10, 3), (355, 113), (-7, 11)] {
            let r = rat(n, d);
            let iv = enclosed(&r);
            assert!(iv.lo < iv.hi);
            assert!(contains(&r, iv.lo, iv.hi));
        }
        // Just above a binade: 1 + 2^-53 spans exactly one ulp.
        let r = rat((1i128 << 53) + 1, 1i128 << 53);
        let iv = enclosed(&r);
        assert!(contains(&r, iv.lo, iv.hi));
        assert_eq!(iv.hi - iv.lo, 2.0f64.powi(-52));
        // Deep dyadic just off an integer power of two.
        let r = rat((1i128 << 70) + 1, 1i128 << 70);
        let iv = enclosed(&r);
        assert!(contains(&r, iv.lo, iv.hi));
        // Normal tiny magnitude stays enclosed.
        let r = BigRational::new((-1).into(), BigInt::from(10).pow(300).into());
        let iv = enclosed(&r);
        assert!(contains(&r, iv.lo, iv.hi));
    }

    #[test]
    fn enclosure_rejects_overflow_and_subnormal_magnitudes() {
        // Overflow of the f64 conversion.
        let big400 = BigRational::new(BigInt::from(10).pow(400).into(), 1.into());
        assert!(enclose_rational(&big400).is_none());
        // Just past MAX: enclosure would need +Inf as an upper bound.
        let past_max = BigRational::from_f64(f64::MAX).unwrap() + rat(500, 1);
        assert!(enclose_rational(&past_max).is_none());
        // Exactly representable subnormals have a proven singleton enclosure.
        let subnormal = BigRational::new(1.into(), BigInt::from(2).pow(1024));
        let interval = enclosed(&subnormal);
        assert!(contains(&subnormal, interval.lo, interval.hi));
        // Subnormal magnitude: exact fallback rather than a flushed bound.
        assert!(enclose_rational(&BigRational::new(
            1.into(),
            BigInt::from(2).pow(1075).into()
        ))
        .is_none());
        // Oversized inputs fail closed instead of running huge shifts.
        let huge = BigRational::new(BigInt::from(10).pow(5000).into(), 1.into());
        assert!(enclose_rational(&huge).is_none());
    }

    #[test]
    fn interval_arithmetic_contains_exact_and_falls_back_on_nonfinite() {
        let point = |f: f64| Interval { lo: f, hi: f };
        // add(MAX, 0) would widen past MAX: fall back, never return Inf.
        let max = point(f64::MAX);
        assert!(add(max, point(0.0)).is_none());
        assert!(sub(max, point(-f64::MAX)).is_none());
        // Multiplication overflow falls back.
        assert!(mul(max, point(2.0)).is_none());
        assert!(mul(max, max).is_none());
        // Exact cancellations stay contained: [1]-[1] and [2^53]-[2^53+2].
        let c = sub(point(1.0), point(1.0)).expect("finite");
        assert!(c.lo <= 0.0 && 0.0 <= c.hi);
        let c = sub(point(2.0f64.powi(53)), point(2.0f64.powi(53) + 2.0)).expect("finite");
        assert!(c.lo <= -2.0 && -2.0 <= c.hi);
        // Subnormal products are contained, not flushed to a wrong sign.
        let tiny = point(f64::from_bits(1));
        let c = mul(tiny, tiny).expect("finite");
        assert!(c.lo <= 0.0 && 0.0 <= c.hi);
        assert!(c.lo < 0.0 && c.hi > 0.0);
        // Signed-zero differences straddle zero and decide nothing.
        let c = sub(point(0.0), point(-0.0)).expect("finite");
        assert!(c.lo <= 0.0 && 0.0 <= c.hi);
    }

    fn exact_orient(a: &Rat, b: &Rat, c: &Rat) -> i8 {
        let v = (&b.0 - &a.0) * (&c.1 - &a.1) - (&b.1 - &a.1) * (&c.0 - &a.0);
        if v.is_zero() {
            0
        } else if v.is_positive() {
            1
        } else {
            -1
        }
    }

    fn coords(p: &Rat) -> Coords<'_> {
        (&p.0, &p.1)
    }

    #[test]
    fn orient_decides_clear_cases_and_never_zero() {
        let cases = [
            (
                pt(int_rat(0), int_rat(0)),
                pt(int_rat(1), int_rat(0)),
                pt(int_rat(0), int_rat(1)),
            ),
            (
                pt(rat(1, 3), rat(1, 3)),
                pt(rat(1, 2), rat(0, 1)),
                pt(rat(0, 1), rat(2, 3)),
            ),
            (
                pt(int_rat(-5), int_rat(7)),
                pt(int_rat(3), int_rat(-2)),
                pt(int_rat(9), int_rat(9)),
            ),
        ];
        for (a, b, c) in &cases {
            let got = orient_sign(coords(a), coords(b), coords(c));
            assert_eq!(got, Some(exact_orient(a, b, c)));
            assert_ne!(got, Some(0));
        }
    }

    #[test]
    fn orient_dyadic_tier_decides_and_rest_still_falls_back() {
        // Exact collinearity on thirds: non-dyadic, never decided here.
        let (a, b, c) = (
            pt(rat(0, 1), rat(0, 1)),
            pt(rat(1, 3), rat(1, 3)),
            pt(rat(2, 3), rat(2, 3)),
        );
        assert_eq!(orient_sign(coords(&a), coords(&b), coords(&c)), None);
        assert_eq!(exact_orient(&a, &b, &c), 0);
        // Exact collinearity on dyadics: true zero from checked integers.
        let (a, b, c) = (
            pt(int_rat(0), int_rat(0)),
            pt(rat(1, 2), rat(1, 2)),
            pt(int_rat(3), int_rat(3)),
        );
        assert_eq!(orient_sign(coords(&a), coords(&b), coords(&c)), Some(0));
        assert_eq!(exact_orient(&a, &b, &c), 0);
        // Near-collinear at 2^60 scale: the tier stays exact past the
        // interval rounding width.
        let big = int_rat(1i128 << 60);
        let (a, b, c) = (
            pt(int_rat(0), int_rat(0)),
            pt(big.clone(), big.clone()),
            pt(big.clone() + int_rat(1), big.clone()),
        );
        assert_eq!(orient_sign(coords(&a), coords(&b), coords(&c)), Some(-1));
        assert_eq!(exact_orient(&a, &b, &c), -1);
        // Direct binary decoding lets duplicate huge points prove exact zero.
        let max = BigRational::from_f64(f64::MAX).unwrap();
        let (a, b, c) = (
            pt(int_rat(0), int_rat(0)),
            pt(max.clone(), max.clone()),
            pt(max.clone(), max.clone()),
        );
        assert_eq!(orient_sign(coords(&a), coords(&b), coords(&c)), Some(0));
        assert_eq!(exact_orient(&a, &b, &c), 0);
        // Subnormal coordinates keep an exact exponent beyond f64 products.
        let t = BigRational::from_f64(f64::from_bits(1)).unwrap();
        let (a, b, c) = (
            pt(int_rat(0), int_rat(0)),
            pt(t.clone(), int_rat(0)),
            pt(int_rat(0), t.clone()),
        );
        assert_eq!(orient_sign(coords(&a), coords(&b), coords(&c)), Some(1));
        assert_eq!(exact_orient(&a, &b, &c), 1);
        // Signed-zero lifts are the same exact zero: decided by the tier.
        let (a, b, c) = (
            pt(
                BigRational::from_f64(0.0).unwrap(),
                BigRational::from_f64(0.0).unwrap(),
            ),
            pt(
                BigRational::from_f64(-0.0).unwrap(),
                BigRational::from_f64(0.0).unwrap(),
            ),
            pt(
                BigRational::from_f64(0.0).unwrap(),
                BigRational::from_f64(-0.0).unwrap(),
            ),
        );
        assert_eq!(orient_sign(coords(&a), coords(&b), coords(&c)), Some(0));
        assert_eq!(exact_orient(&a, &b, &c), 0);
    }

    fn square(x0: i128, y0: i128, x1: i128, y1: i128) -> Vec<Rat> {
        vec![
            pt(int_rat(x0), int_rat(y0)),
            pt(int_rat(x1), int_rat(y0)),
            pt(int_rat(x1), int_rat(y1)),
            pt(int_rat(x0), int_rat(y1)),
        ]
    }

    #[test]
    fn sat_accepts_clear_gaps_proves_overlap_and_defers_rest() {
        // Well-separated axis squares on integer and third coordinates.
        let p = square(0, 0, 1, 1);
        let q = square(3, 0, 4, 1);
        assert_eq!(polys_strictly_disjoint(&p, &q), Some(true));
        let p = vec![
            pt(rat(0, 3), rat(0, 3)),
            pt(rat(3, 3), rat(0, 3)),
            pt(rat(3, 3), rat(3, 3)),
            pt(rat(0, 3), rat(3, 3)),
        ];
        let q = vec![
            pt(rat(9, 3), rat(0, 3)),
            pt(rat(12, 3), rat(0, 3)),
            pt(rat(12, 3), rat(3, 3)),
            pt(rat(9, 3), rat(3, 3)),
        ];
        assert_eq!(polys_strictly_disjoint(&p, &q), Some(true));
        // Shared edge: the tier proves exact overlap on every axis.
        let r = square(1, 0, 2, 1);
        let s = square(0, 0, 1, 1);
        assert_eq!(polys_strictly_disjoint(&r, &s), Some(false));
        assert!(!exact_separated(&r, &s));
        // Overlap proves out the same way.
        let o = square(0, 0, 2, 2);
        assert_eq!(polys_strictly_disjoint(&s, &o), Some(false));
        assert!(!exact_separated(&s, &o));
        // Degenerate collinear segments with a gap: no separating normal
        // exists, so the tier proves the exact verdict is overlap, exactly
        // as the narrow phase decides.
        let a = vec![pt(int_rat(0), int_rat(0)), pt(int_rat(1), int_rat(0))];
        let b = vec![pt(int_rat(2), int_rat(0)), pt(int_rat(3), int_rat(0))];
        assert_eq!(polys_strictly_disjoint(&a, &b), Some(false));
        assert!(!exact_separated(&a, &b));
        // A sub-ULP gap at huge coordinates is proved by the integer tier.
        let big = int_rat(1i128 << 100);
        let p = vec![
            pt(int_rat(0), int_rat(0)),
            pt(big.clone(), int_rat(0)),
            pt(int_rat(0), big.clone()),
        ];
        let q = vec![
            pt(big.clone() + int_rat(10), int_rat(0)),
            pt(big.clone() * int_rat(2), int_rat(0)),
            pt(big.clone() + int_rat(10), big.clone()),
        ];
        assert_eq!(polys_strictly_disjoint(&p, &q), Some(true));
        assert!(exact_separated(&p, &q));
    }

    #[test]
    fn sat_defers_when_a_projection_difference_overflows() {
        // Every dot fits, but one extremum comparison needs a 200-bit
        // alignment: the tier defers instead of keeping a stale extremum
        // or a false overlap. The public path still matches the
        // independent exact oracle.
        let big = int_rat(1i128 << 100);
        let tiny = rat(1, 1i128 << 100);
        let p = vec![
            pt(big.clone(), int_rat(0)),
            pt(tiny.clone(), int_rat(0)),
            pt(int_rat(0), int_rat(1)),
        ];
        let q = vec![
            pt(int_rat(10), int_rat(0)),
            pt(int_rat(10), int_rat(5)),
            pt(int_rat(11), int_rat(5)),
        ];
        let (pe, qe) = (enclose_slice(&p).unwrap(), enclose_slice(&q).unwrap());
        assert_eq!(dyadic_disjoint(&p, &q, &pe, &qe), None);
        match polys_strictly_disjoint(&p, &q) {
            Some(v) => assert_eq!(v, exact_separated(&p, &q)),
            None => {}
        }

        // A stale lower extremum would falsely separate this nested box.
        let p = vec![
            pt(int_rat(0), big.clone()),
            pt(int_rat(0), tiny.clone()),
            pt(int_rat(1), tiny),
            pt(int_rat(1), big.clone()),
        ];
        let q = vec![
            pt(rat(1, 4), &big - int_rat(2)),
            pt(rat(3, 4), &big - int_rat(2)),
            pt(rat(3, 4), &big - int_rat(1)),
            pt(rat(1, 4), &big - int_rat(1)),
        ];
        assert!(!exact_separated(&p, &q));
        let (pe, qe) = (enclose_slice(&p).unwrap(), enclose_slice(&q).unwrap());
        assert_ne!(dyadic_disjoint(&p, &q, &pe, &qe), Some(true));
        assert_ne!(polys_strictly_disjoint(&p, &q), Some(true));
    }

    /// Independent hull oracle mirroring the exact narrow phase: proper
    /// crossings, on-segment contacts and fan containment, all exact.
    fn exact_on_segment(a: &Rat, b: &Rat, p: &Rat) -> bool {
        use std::cmp::{max, min};
        exact_orient(a, b, p) == 0
            && min(&a.0, &b.0) <= &p.0
            && &p.0 <= max(&a.0, &b.0)
            && min(&a.1, &b.1) <= &p.1
            && &p.1 <= max(&a.1, &b.1)
    }

    fn exact_outside(pt: &Rat, poly: &[Rat]) -> bool {
        if poly.is_empty() {
            return true;
        }
        if poly.len() == 1 {
            return pt != &poly[0];
        }
        if poly.len() == 2 {
            let (a, b) = (&poly[0], &poly[1]);
            return !(pt == a || pt == b || exact_on_segment(a, b, pt));
        }
        let ccw = exact_orient(&poly[0], &poly[1], &poly[2]) > 0;
        for i in 1..poly.len() - 1 {
            let (s0, s1, s2) = (
                exact_orient(&poly[0], &poly[i], pt),
                exact_orient(&poly[i], &poly[i + 1], pt),
                exact_orient(&poly[i + 1], &poly[0], pt),
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

    fn exact_meet_only_at(p: &[Rat], q: &[Rat], shared: &Rat) -> bool {
        let edges = |n: usize| -> Vec<(usize, usize)> {
            if n < 2 {
                return Vec::new();
            }
            (0..n).map(|i| (i, (i + 1) % n)).collect()
        };
        for (ia, ib) in &edges(p.len()) {
            for (jc, jd) in &edges(q.len()) {
                let (o1, o2, o3, o4) = (
                    exact_orient(&p[*ia], &p[*ib], &q[*jc]),
                    exact_orient(&p[*ia], &p[*ib], &q[*jd]),
                    exact_orient(&q[*jc], &q[*jd], &p[*ia]),
                    exact_orient(&q[*jc], &q[*jd], &p[*ib]),
                );
                if o1 * o2 < 0 && o3 * o4 < 0 {
                    return false;
                }
                for (w, u, v) in [
                    (&q[*jc], &p[*ia], &p[*ib]),
                    (&q[*jd], &p[*ia], &p[*ib]),
                    (&p[*ia], &q[*jc], &q[*jd]),
                    (&p[*ib], &q[*jc], &q[*jd]),
                ] {
                    if exact_on_segment(u, v, w) && w != shared {
                        return false;
                    }
                }
            }
        }
        p.iter()
            .filter(|v| *v != shared)
            .all(|v| exact_outside(v, q))
            && q.iter()
                .filter(|v| *v != shared)
                .all(|v| exact_outside(v, p))
    }

    #[test]
    fn hulls_meet_resolves_locally_and_matches_exact_oracle() {
        // C1-joined quads: hulls meet only at the shared junction.
        let left = vec![
            pt(int_rat(0), int_rat(0)),
            pt(int_rat(1), int_rat(0)),
            pt(int_rat(2), int_rat(1)),
        ];
        let right = vec![
            pt(int_rat(2), int_rat(1)),
            pt(int_rat(3), int_rat(2)),
            pt(int_rat(4), int_rat(2)),
        ];
        let shared = pt(int_rat(2), int_rat(1));
        assert_eq!(
            hulls_meet_only_at(&left, &right, &shared),
            Some(exact_meet_only_at(&left, &right, &shared))
        );
        let far = vec![
            pt(int_rat(5), int_rat(2)),
            pt(int_rat(7), int_rat(4)),
            pt(int_rat(6), int_rat(7)),
        ];
        assert_eq!(hulls_meet_only_at(&left, &far, &shared), Some(true));
        assert!(exact_meet_only_at(&left, &far, &shared));
        // Proper crossing with all decisive signs is proven rejection.
        let over = vec![
            pt(rat(1, 2), int_rat(-1)),
            pt(rat(1, 2), int_rat(1)),
            pt(int_rat(3), int_rat(0)),
        ];
        assert_eq!(hulls_meet_only_at(&left, &over, &shared), Some(false));
        assert!(!exact_meet_only_at(&left, &over, &shared));
        // Near miss with a sub-ulp determinant: the vertex sits 2^-70 off
        // the diagonal inside its box. Local resolution matches the oracle
        // instead of discarding the decided subresults.
        let w = pt(rat((1i128 << 69) + 1, 1i128 << 70), rat(1, 2));
        let p = vec![
            pt(int_rat(0), int_rat(0)),
            pt(int_rat(1), int_rat(1)),
            pt(int_rat(0), int_rat(1)),
        ];
        let q = vec![w, pt(int_rat(2), int_rat(0)), pt(int_rat(2), int_rat(1))];
        let s = pt(int_rat(9), int_rat(9));
        assert_eq!(
            hulls_meet_only_at(&p, &q, &s),
            Some(exact_meet_only_at(&p, &q, &s))
        );
    }

    /// Independent chord oracle mirroring the exact predicate.
    fn chord_exact(chain: &[Rat]) -> bool {
        if chain.len() < 2 || chain.first() == chain.last() {
            return false;
        }
        let chord = (
            &chain[chain.len() - 1].0 - &chain[0].0,
            &chain[chain.len() - 1].1 - &chain[0].1,
        );
        if chord.0.is_zero() && chord.1.is_zero() {
            return false;
        }
        chain.windows(2).all(|w| {
            ((&w[1].0 - &w[0].0) * &chord.0 + (&w[1].1 - &w[0].1) * &chord.1).is_positive()
        })
    }

    #[test]
    fn chord_monotone_matches_exact_in_all_directions() {
        let mono = vec![
            pt(int_rat(0), int_rat(0)),
            pt(int_rat(1), int_rat(3)),
            pt(int_rat(2), int_rat(0)),
        ];
        assert_eq!(chord_monotone(&mono), Some(true));
        let looping = vec![
            pt(int_rat(0), int_rat(0)),
            pt(int_rat(2), int_rat(1)),
            pt(int_rat(-1), int_rat(1)),
            pt(int_rat(1), int_rat(0)),
        ];
        assert_eq!(chord_monotone(&looping), Some(false));
        // Degenerate zero chord fails closed exactly as the fallback does.
        let flat = vec![pt(int_rat(1), int_rat(1)), pt(int_rat(1), int_rat(1))];
        assert_eq!(chord_monotone(&flat), Some(false));
        assert_eq!(chord_monotone(&[]), Some(false));
        // A zero leg projection is decided by the tier, as exact rejects.
        let sideways = vec![
            pt(int_rat(0), int_rat(0)),
            pt(int_rat(0), int_rat(1)),
            pt(int_rat(1), int_rat(0)),
        ];
        assert_eq!(chord_monotone(&sideways), Some(false));
        // A non-dyadic chain agrees with the oracle through the interval
        // or fallback path.
        let sideways_third = vec![
            pt(rat(0, 3), rat(0, 3)),
            pt(rat(0, 3), rat(3, 3)),
            pt(rat(3, 3), rat(3, 3)),
        ];
        assert_eq!(
            chord_monotone(&sideways_third),
            Some(chord_exact(&sideways_third))
        );
    }

    /// Center-relative points, exactly as the narrow phase builds them.
    fn rel_of(center: [f64; 2], controls: &[[f64; 2]]) -> Vec<Rat> {
        let rate = |c: [f64; 2]| {
            (
                BigRational::from_f64(c[0]).unwrap(),
                BigRational::from_f64(c[1]).unwrap(),
            )
        };
        let c = rate(center);
        controls
            .iter()
            .map(|p| {
                let q = rate(*p);
                (q.0 - &c.0, q.1 - &c.1)
            })
            .collect()
    }

    #[test]
    fn quad_filter_agrees_with_exact_and_preserves_tangency() {
        let one = BigRational::from_integer(1.into());
        // Far curve: the filter proves clearance, matching exact.
        let rel = rel_of([0.0, 0.0], &[[10.0, 10.0], [12.0, 14.0], [14.0, 10.0]]);
        assert_eq!(source_quad_clear(&one, &rel), Some(true));
        assert!(source_disk_clear_exact(&rel, &one));
        // Non-dyadic reach on the same far curve still filters.
        let reach = &one + &rat(1, 3);
        assert_eq!(source_quad_clear(&reach, &rel), Some(true));
        // Tangent touch: the filter defers while exact still accepts, so
        // the finite-depth tangency verdict is preserved by the fallback.
        let rel = rel_of([0.0, 0.0], &[[-1.0, 1.0], [0.0, 1.0], [1.0, 1.0]]);
        assert_eq!(source_quad_clear(&one, &rel), None);
        assert!(source_disk_clear_exact(&rel, &one));
        // Penetration and crossing: the filter defers, exact rejects.
        for bad in [
            rel_of([0.0, 0.0], &[[-1.0, 0.5], [0.0, 0.5], [1.0, 0.5]]),
            rel_of([0.0, 0.0], &[[-2.0, 2.0], [0.0, -2.0], [2.0, 2.0]]),
        ] {
            assert_eq!(source_quad_clear(&one, &bad), None);
            assert!(!source_disk_clear_exact(&bad, &one));
        }
        // Non-dyadic controls on a far curve still filter.
        let third = |n: i128| rat(n, 3);
        let trel = vec![
            pt(third(30), third(30)),
            pt(third(36), third(42)),
            pt(third(42), third(30)),
        ];
        assert_eq!(source_quad_clear(&one, &trel), Some(true));
        assert!(source_disk_clear_exact(&trel, &one));
    }

    #[test]
    fn quad_filter_takes_relative_points_without_resubtraction() {
        // Review regression: the filter input is already center-relative,
        // so a translated penetrating curve must not clear. Center
        // [0,10], radius 1, absolute quad through (0,9.5): penetration.
        let one = BigRational::from_integer(1.into());
        let rel = rel_of([0.0, 10.0], &[[-1.0, 10.0], [0.0, 9.5], [1.0, 10.0]]);
        assert!(!source_disk_clear_exact(&rel, &one));
        assert_ne!(source_quad_clear(&one, &rel), Some(true));
        // Full path with absolute controls agrees: penetration, no false
        // clearance.
        assert!(!source_disk_clear(
            [0.0, 10.0],
            &one,
            &[[-1.0, 10.0], [0.0, 9.5], [1.0, 10.0]]
        ));
        // Translated clear curve: relative height 2 above center, radius 1.
        let rel = rel_of([0.0, 10.0], &[[-1.0, 12.0], [0.0, 12.0], [1.0, 12.0]]);
        assert_eq!(source_quad_clear(&one, &rel), Some(true));
        assert!(source_disk_clear_exact(&rel, &one));
        assert!(source_disk_clear(
            [0.0, 10.0],
            &one,
            &[[-1.0, 12.0], [0.0, 12.0], [1.0, 12.0]]
        ));
    }

    fn rng_next(s: &mut u64) -> u64 {
        *s ^= *s << 13;
        *s ^= *s >> 7;
        *s ^= *s << 17;
        *s
    }

    fn rand_rat(s: &mut u64) -> BigRational {
        let v = rng_next(s) as i128;
        match rng_next(s) % 6 {
            0 => int_rat(v),
            1 => rat(v, 64),
            2 => rat(v, 3),
            3 => int_rat(v.wrapping_mul(1i128 << 100)),
            4 => rat(v.wrapping_mul(7).wrapping_add(1), 4096),
            _ => rat(v, 113),
        }
    }

    fn exact_separated(p: &[Rat], q: &[Rat]) -> bool {
        // Independent narrow phase over exact rationals.
        let mut axes: Vec<Rat> = Vec::new();
        for poly in [p, q] {
            if poly.len() < 2 {
                continue;
            }
            for i in 0..poly.len() {
                let (a, b) = (&poly[i], &poly[(i + 1) % poly.len()]);
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
        for n in &axes {
            let mut ps: Vec<BigRational> = p.iter().map(|v| &v.0 * &n.0 + &v.1 * &n.1).collect();
            let mut qs: Vec<BigRational> = q.iter().map(|v| &v.0 * &n.0 + &v.1 * &n.1).collect();
            ps.sort();
            qs.sort();
            if ps.last().unwrap() < qs.first().unwrap() || qs.last().unwrap() < ps.first().unwrap()
            {
                return true;
            }
        }
        false
    }

    #[test]
    fn generated_sweep_matches_exact_oracles_with_fallbacks() {
        let mut s = 0x243F_6A88_85A3_08D3u64;
        let (mut decided, mut undecided) = (0usize, 0usize);
        for i in 0..3000 {
            let mut tri = || {
                (
                    pt(rand_rat(&mut s), rand_rat(&mut s)),
                    pt(rand_rat(&mut s), rand_rat(&mut s)),
                    pt(rand_rat(&mut s), rand_rat(&mut s)),
                )
            };
            let (a, b, mut c) = tri();
            if i % 7 == 6 {
                // Exact midpoint collinearity exercises the zero path; the
                // tier decides it on dyadic inputs.
                let two = int_rat(2);
                c = ((&a.0 + &b.0) / &two, (&a.1 + &b.1) / &two);
            }
            match orient_sign(coords(&a), coords(&b), coords(&c)) {
                Some(got) => {
                    decided += 1;
                    assert_eq!(got, exact_orient(&a, &b, &c));
                }
                None => undecided += 1,
            }
            if i % 3 == 0 {
                let p = vec![a.clone(), b.clone(), c.clone()];
                let shift = pt(
                    BigRational::from_integer(BigInt::from(1) << 200usize),
                    int_rat(0),
                );
                let q = vec![
                    pt(&p[0].0 + &shift.0, &p[0].1 + &shift.1),
                    pt(&p[1].0 + &shift.0, &p[1].1 + &shift.1),
                    pt(&p[2].0 + &shift.0, &p[2].1 + &shift.1),
                ];
                if let Some(true) = polys_strictly_disjoint(&p, &q) {
                    assert!(exact_separated(&p, &q));
                    decided += 1;
                } else {
                    undecided += 1;
                }
                // Translation plus positive scaling preserves exact
                // orientation signs; decisive filters agree across it.
                let t = |v: &Rat| pt(&v.0 * &int_rat(2) + &shift.0, &v.1 * &int_rat(2) + &shift.1);
                let (ta, tb, tc) = (t(&a), t(&b), t(&c));
                assert_eq!(exact_orient(&ta, &tb, &tc), exact_orient(&a, &b, &c));
                if let (Some(got), Some(want)) = (
                    orient_sign(coords(&ta), coords(&tb), coords(&tc)),
                    orient_sign(coords(&a), coords(&b), coords(&c)),
                ) {
                    assert_eq!(got, want);
                }
            }
        }
        assert!(decided > 0 && undecided > 0);
    }

    #[test]
    fn translated_quad_sweep_never_falsely_accepts() {
        let mut s = 0x9E37_79B9_7F4A_7C15u64;
        let (mut decided, mut undecided) = (0usize, 0usize);
        for i in 0..300 {
            let center = pt(rand_rat(&mut s), rand_rat(&mut s));
            let ctrls: Vec<Rat> = if i % 5 == 0 {
                // Far controls: clearance must filter through.
                (0..3)
                    .map(|k| {
                        pt(
                            &center.0 + &int_rat(1000 + k as i128 * 7),
                            &center.1 + &int_rat(1000 + k as i128 * 3),
                        )
                    })
                    .collect()
            } else {
                (0..3)
                    .map(|_| pt(rand_rat(&mut s), rand_rat(&mut s)))
                    .collect()
            };
            let rel: Vec<Rat> = ctrls
                .iter()
                .map(|p| (&p.0 - &center.0, &p.1 - &center.1))
                .collect();
            let reach = int_rat(1 + (rng_next(&mut s) % 50) as i128);
            match source_quad_clear(&reach, &rel) {
                Some(true) => {
                    decided += 1;
                    assert!(source_disk_clear_exact(&rel, &reach));
                }
                _ => undecided += 1,
            }
        }
        assert!(decided > 0 && undecided > 0);
    }

    #[test]
    fn generated_hulls_and_monotone_match_exact() {
        let mut s = 0x4528_21E6_38D0_1377u64;
        let (mut decided, mut undecided) = (0usize, 0usize);
        for case in 0..500 {
            let n = 3 + (rng_next(&mut s) % 3) as usize;
            let mut chain: Vec<Rat> = (0..n)
                .map(|_| pt(rand_rat(&mut s), rand_rat(&mut s)))
                .collect();
            if case % 7 == 0 {
                chain[1] = chain[0].clone();
            }
            let exact = {
                if chain.len() < 2 || chain.first() == chain.last() {
                    false
                } else {
                    let chord = (&chain[n - 1].0 - &chain[0].0, &chain[n - 1].1 - &chain[0].1);
                    if chord.0.is_zero() && chord.1.is_zero() {
                        false
                    } else {
                        chain.windows(2).all(|w| {
                            ((&w[1].0 - &w[0].0) * &chord.0 + (&w[1].1 - &w[0].1) * &chord.1)
                                .is_positive()
                        })
                    }
                }
            };
            match chord_monotone(&chain) {
                Some(got) => {
                    decided += 1;
                    assert_eq!(got, exact);
                }
                None => undecided += 1,
            }
        }
        assert!(decided > 0 && undecided > 0);
    }

    fn singleton(r: &BigRational, f: f64) {
        let iv = enclose_rational(r).expect("dyadic must enclose");
        assert_eq!((iv.lo, iv.hi), (f, f));
        assert!(contains(r, iv.lo, iv.hi));
    }

    #[test]
    fn dyadic_fast_path_proves_exact_singletons() {
        // Common dyadics: numerator magnitude <= 2^53, power-of-two
        // denominator, normal result. Each singleton is proved by bit
        // scaling alone, with no roundtrip allocation.
        for f in [3.984375, -1.3125, 1.0 / 128.0, 0.625, 2.0f64.powi(53)] {
            singleton(&BigRational::from_f64(f).unwrap(), f);
        }
        singleton(&rat(-(1i128 << 53), 8), -(1i128 << 50) as f64);
        singleton(&rat(7, 1), 7.0);
        // Deep dyadic still in the normal range.
        singleton(
            &BigRational::new(1.into(), BigInt::from(2).pow(900)),
            2.0f64.powi(-900),
        );
        // The fast path must decline these; the untouched general
        // conversion still proves them exactly.
        assert!(enclose_dyadic_fast(&rat(1, 3)).is_none());
        assert!(enclose_dyadic_fast(&rat((1i128 << 53) + 1, 1)).is_none());
        let over = rat((1i128 << 53) + 1, 1);
        let iv = enclosed(&over);
        assert!(contains(&over, iv.lo, iv.hi));
    }

    #[test]
    fn dyadic_fast_path_limits_above_2to53_and_off_dyadic() {
        // Just above 2^53: odd numerators are not exactly representable,
        // so no singleton; the bit-constructed span still contains them.
        let odd = rat((1i128 << 53) + 1, 1);
        let iv = enclosed(&odd);
        assert!(iv.lo < iv.hi);
        assert!(contains(&odd, iv.lo, iv.hi));
        assert_eq!((iv.lo, iv.hi), (2.0f64.powi(53), 2.0f64.powi(53) + 2.0));
        // Even above the limit stays exactly representable through the
        // general path, which the fast path leaves untouched.
        // ((2^53+1)/2 needs 54 significant bits, so it spans one ulp;
        // (2^53+2)/2 is exactly representable.)
        singleton(&rat((1i128 << 53) + 2, 1), 2.0f64.powi(53) + 2.0);
        let half = rat((1i128 << 53) + 1, 2);
        let hiv = enclosed(&half);
        assert!(hiv.lo < hiv.hi);
        assert!(contains(&half, hiv.lo, hiv.hi));
        singleton(&rat((1i128 << 53) + 2, 2), 2.0f64.powi(52) + 1.0);
        // Non-dyadic values never take the fast path.
        for (n, d) in [(1, 3), (1, 10), (355, 113)] {
            let r = rat(n, d);
            assert!(enclose_dyadic_fast(&r).is_none());
            let iv = enclosed(&r);
            assert!(iv.lo < iv.hi);
            assert!(contains(&r, iv.lo, iv.hi));
        }
        // Normal dyadics with short mantissas remain exact at large exponents.
        let huge_denom = BigRational::new(3.into(), BigInt::from(2).pow(200));
        assert!(enclose_dyadic_fast(&huge_denom).is_some());
        let huge_numer = BigRational::new(BigInt::from(2).pow(100), 1.into());
        assert!(enclose_dyadic_fast(&huge_numer).is_some());
    }

    #[test]
    fn dyadic_fast_all_u64_denominators_have_exact_singletons() {
        // Rust's numeric cast semantics and binary64's exact powers of
        // two justify every supported denominator. Check actual exact
        // rationals, without using powi as an expected-value oracle.
        for k in 0..64 {
            let d = 1u64 << k;
            for n in [
                1i64,
                -1,
                (1i64 << 53) - 1,
                -((1i64 << 53) - 1),
                1i64 << 53,
                -(1i64 << 53),
            ] {
                let r = BigRational::new(n.into(), d.into());
                let iv = enclose_dyadic_fast(&r).expect("supported normal dyadic");
                assert_eq!(iv.lo.to_bits(), iv.hi.to_bits());
                assert_eq!(BigRational::from_f64(iv.lo).unwrap(), r);
            }
        }
    }

    #[test]
    fn dyadic_fast_path_signed_zero_subnormal_overflow_safe() {
        // Both signed zeros are exact zero before any scaling.
        for f in [0.0, -0.0] {
            let r = BigRational::from_f64(f).unwrap();
            assert!(r.is_zero());
            let iv = enclosed(&r);
            assert_eq!((iv.lo, iv.hi), (0.0, 0.0));
            assert!(enclose_dyadic_fast(&r).is_none() || iv.lo == iv.hi);
        }
        // Normal tiny magnitude keeps a proven enclosure.
        let tiny = BigRational::new(1.into(), BigInt::from(2).pow(1022));
        assert!(enclose_dyadic_fast(&tiny).is_some());
        let iv = enclosed(&tiny);
        assert!(contains(&tiny, iv.lo, iv.hi));
        // Subnormal results decline the fast path: scaling into the
        // subnormal range is no longer exact by exponent move alone.
        let sub = BigRational::new(1.into(), BigInt::from(2).pow(1074));
        assert!(enclose_dyadic_fast(&sub).is_none());
        // Overflow declines everywhere rather than widening to infinity.
        let big = BigRational::new(BigInt::from(10).pow(400).into(), 1.into());
        assert!(enclose_dyadic_fast(&big).is_none());
        assert!(enclose_rational(&big).is_none());
    }

    fn check_prepared(p: &[Rat], q: &[Rat], s: &Rat) {
        let (pie, qie) = (enclose_hull(p).unwrap(), enclose_hull(q).unwrap());
        let (bp, bq) = (
            BoundHull::new(p, &pie).unwrap(),
            BoundHull::new(q, &qie).unwrap(),
        );
        assert_eq!(
            polys_strictly_disjoint_h(&bp, &bq),
            polys_strictly_disjoint(p, q),
            "SAT prepared vs unprepared"
        );
        assert_eq!(
            hulls_meet_only_at_h(&bp, &bq, s),
            hulls_meet_only_at(p, q, s),
            "shared-contact prepared vs unprepared"
        );
        if polys_strictly_disjoint(p, q) == Some(true) {
            assert!(exact_separated(p, q));
        }
        assert_eq!(
            hulls_meet_only_at(p, q, s),
            Some(exact_meet_only_at(p, q, s)),
            "shared-contact matches independent oracle"
        );
        let cp = BoundHull::new(p, &pie).unwrap();
        assert_eq!(chord_monotone_h(&cp), chord_monotone(p));
    }

    #[test]
    fn prepared_variants_agree_with_unprepared_under_transforms() {
        // Prepared bounds must give the identical filter verdict as
        // enclosing on the fly: `Some` equals the exact oracle, `None`
        // defers to it. Translated/scaled shared contacts and
        // near-collinear uncertainty are covered explicitly.
        let shift = BigRational::from_integer(BigInt::from(1) << 200usize);
        let cases: Vec<(Vec<Rat>, Vec<Rat>, Rat)> = vec![
            (
                vec![
                    pt(int_rat(0), int_rat(0)),
                    pt(int_rat(4), int_rat(0)),
                    pt(int_rat(4), int_rat(4)),
                ],
                vec![
                    pt(int_rat(9), int_rat(0)),
                    pt(int_rat(12), int_rat(0)),
                    pt(int_rat(12), int_rat(3)),
                ],
                pt(int_rat(99), int_rat(99)),
            ),
            (
                vec![
                    pt(rat(0, 3), rat(0, 3)),
                    pt(rat(3, 3), rat(0, 3)),
                    pt(rat(3, 3), rat(3, 3)),
                ],
                vec![
                    pt(rat(9, 3), rat(0, 3)),
                    pt(rat(12, 3), rat(0, 3)),
                    pt(rat(12, 3), rat(3, 3)),
                ],
                pt(rat(99, 3), rat(99, 3)),
            ),
        ];
        let mv = |v: &Rat| pt(&v.0 * &int_rat(2) + &shift, &v.1 * &int_rat(2) + &shift);
        let mut all: Vec<(Vec<Rat>, Vec<Rat>, Rat)> = Vec::new();
        for (p, q, s) in &cases {
            all.push((p.clone(), q.clone(), s.clone()));
            all.push((
                p.iter().map(mv).collect(),
                q.iter().map(mv).collect(),
                mv(s),
            ));
        }
        // Near-collinear vertex inside its box: locally resolved, matches
        // the oracle instead of discarding decided subresults.
        let w = pt(rat((1i128 << 69) + 1, 1i128 << 70), rat(1, 2));
        all.push((
            vec![
                pt(int_rat(0), int_rat(0)),
                pt(int_rat(1), int_rat(1)),
                pt(int_rat(0), int_rat(1)),
            ],
            vec![w, pt(int_rat(2), int_rat(0)), pt(int_rat(2), int_rat(1))],
            pt(int_rat(9), int_rat(9)),
        ));
        for (p, q, s) in &all {
            check_prepared(p, q, s);
        }
    }
}
