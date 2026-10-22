//! Restricted segment-site Voronoi dominance intervals for straight pairs.
//!
//! Native Rust port of `experiments/hobby_fitting/intervals.py`, which is
//! the authoritative primary source for every formula, normalization, and
//! guard. Background: Hobby section 3.2, the medial axis as the Voronoi
//! diagram of boundary sites; opposition pruning removes corner branches.
//! Along one straight bisector center and radius are affine in the overlap
//! parameter. Working in canonical f in [0,1] over translated and scaled
//! coordinates keeps every epsilon relative, so translation or uniform
//! scaling cannot change a verdict. Positive radius, open interior feet,
//! and distance to every other segment bound the intervals; foot-projection
//! endpoints split the point/line distance pieces, whose equality events
//! are quadratic in global f. Only open interval interiors are sampled and
//! every sampled disk is rechecked. Parabolic branches are not traced:
//! contacts with endpoint feet never qualify, and vertex-dominated cells
//! are unsupported. Uncertain degree or root abstains the pair instead of
//! guessing. Width-only port: no grid, no tolerance retuning.
//!
//! Float rules preserved from the source: interval math is guarded `f64`,
//! never exact rational. Exact zero stays exact; only the `EPS` noise band
//! abstains as uncertain. `math.hypot` maps to the `super::numeric` port of
//! CPython 3.14 `vector_norm` (same operations, same order). The quadratic
//! Bernstein common-sign certificate keeps its outward rounding; there is
//! no approximate-root weakening.

use serde::{Deserialize, Serialize};

/// Relative float guard in normalized space; never a model gate. Exact zero
/// stays exact; only the noise band abstains as uncertain.
pub const EPS: f64 = 1e-9;

/// Single-stage opposition pruning from Hobby section 3.2, figure 18b: a
/// published conservative project choice, not a fitted value. The angle is
/// constant on a segment/segment bisector; pairs opposed by less than 157
/// degrees are corner branches, not strokes.
/// Source value: `math.cos(math.radians(157.0))`.
pub const OPP_COS: f64 = -0.9205048534524404;

/// Point in caller coordinates.
pub type Point = [f64; 2];
/// Segment as a nested array: `[p0, p1]`.
pub type Segment = [Point; 2];

/// A competing segment carrying an opaque tag reported on third contact.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Border {
    pub seg: Segment,
    pub tag: String,
}

/// Shared corridor direction and overlap of two segments. `None` when the
/// overlap is empty or a direction is degenerate.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Corridor {
    pub d: Point,
    pub u: Point,
    pub t1: Point,
    pub t2: Point,
    pub lo: f64,
    pub hi: f64,
    pub l0: f64,
}

/// Shared corridor direction and overlap of two segments.
///
/// Segments follow their edges' own orientation. Returns `None` when the
/// overlap is empty.
pub fn corridor(a: Segment, b: Segment) -> Option<Corridor> {
    let (adx, ady) = (a[1][0] - a[0][0], a[1][1] - a[0][1]);
    let (bdx, bdy) = (b[1][0] - b[0][0], b[1][1] - b[0][1]);
    let alen = super::numeric::hypot(adx, ady);
    let blen = super::numeric::hypot(bdx, bdy);
    if alen == 0.0 || blen == 0.0 {
        return None;
    }
    let t1 = [adx / alen, ady / alen];
    let t2 = [bdx / blen, bdy / blen];
    let mut t2c = t2;
    if t1[0] * t2[0] + t1[1] * t2[1] < 0.0 {
        t2c = [-t2[0], -t2[1]];
    }
    let (dx, dy) = (t1[0] + t2c[0], t1[1] + t2c[1]);
    let norm = super::numeric::hypot(dx, dy);
    if norm == 0.0 {
        return None;
    }
    let d = [dx / norm, dy / norm];
    let (a0, a1) = (
        d[0] * a[0][0] + d[1] * a[0][1],
        d[0] * a[1][0] + d[1] * a[1][1],
    );
    let (b0, b1) = (
        d[0] * b[0][0] + d[1] * b[0][1],
        d[0] * b[1][0] + d[1] * b[1][1],
    );
    let lo = a0.min(a1).max(b0.min(b1));
    let hi = a0.max(a1).min(b0.max(b1));
    if hi <= lo {
        return None;
    }
    Some(Corridor {
        d,
        u: [-d[1], d[0]],
        t1,
        t2,
        lo,
        hi,
        l0: hi - lo,
    })
}

/// Bisector constants, opposition angle, and uncertainty verdict.
///
/// Exact zero stays exact; near-zero sides or determinant in the noise band
/// cannot certify the geometry and abstain the pair. The 157 degree
/// opposition gate is constant on the bisector.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct FrameResult {
    pub status: String,
    pub opp: Option<f64>,
    inner: Option<FrameInner>,
}

/// Private bisector constants for internal use by dominance/contact.
#[derive(Clone, Debug, Serialize, Deserialize)]
struct FrameInner {
    n1: Point,
    n2: Point,
    c1: f64,
    c2: f64,
    s1: f64,
    s2: f64,
    a11: f64,
    a12: f64,
    a21: f64,
    a22: f64,
    det: f64,
    d: Point,
    u: Point,
    t1: Point,
    t2: Point,
    lo: f64,
    hi: f64,
    l0: f64,
}

pub fn frame(a: Segment, b: Segment, cor: &Corridor) -> FrameResult {
    let ok = |opp: f64, inner: FrameInner| FrameResult {
        status: "ok".to_string(),
        opp: Some(opp),
        inner: Some(inner),
    };
    let fail = |status: &str, opp: Option<f64>| FrameResult {
        status: status.to_string(),
        opp,
        inner: None,
    };
    let t1 = cor.t1;
    let t2 = cor.t2;
    let n1 = [-t1[1], t1[0]];
    let n2 = [-t2[1], t2[0]];
    let c1 = n1[0] * a[0][0] + n1[1] * a[0][1];
    let c2 = n2[0] * b[0][0] + n2[1] * b[0][1];
    let m1 = [(a[0][0] + a[1][0]) / 2.0, (a[0][1] + a[1][1]) / 2.0];
    let m2 = [(b[0][0] + b[1][0]) / 2.0, (b[0][1] + b[1][1]) / 2.0];
    let s1 = (n1[0] * m2[0] + n1[1] * m2[1]) - c1;
    let s2 = (n2[0] * m1[0] + n2[1] * m1[1]) - c2;
    if s1 == 0.0 || s2 == 0.0 {
        return fail("degenerate-side", None);
    }
    let l0 = cor.l0;
    if !(l0 > 0.0) {
        return fail("degenerate-side", None);
    }
    if s1.abs() <= EPS * l0 || s2.abs() <= EPS * l0 {
        return fail("uncertain-side", None);
    }
    let s1 = if s1 > 0.0 { 1.0 } else { -1.0 };
    let s2 = if s2 > 0.0 { 1.0 } else { -1.0 };
    let opp = (s1 * n1[0]) * (s2 * n2[0]) + (s1 * n1[1]) * (s2 * n2[1]);
    if opp > OPP_COS {
        return fail("opposition-pruned", Some(opp));
    }
    let u = cor.u;
    let a11 = n1[0] * u[0] + n1[1] * u[1];
    let a12 = -s1;
    let a21 = n2[0] * u[0] + n2[1] * u[1];
    let a22 = -s2;
    let det = a11 * a22 - a12 * a21;
    if det == 0.0 {
        return fail("degenerate-bisector", None);
    }
    if det.abs() <= EPS {
        return fail("uncertain-bisector", None);
    }
    ok(
        opp,
        FrameInner {
            n1,
            n2,
            c1,
            c2,
            s1,
            s2,
            a11,
            a12,
            a21,
            a22,
            det,
            d: cor.d,
            u,
            t1,
            t2,
            lo: cor.lo,
            hi: cor.hi,
            l0,
        },
    )
}

/// Outcome of a linear bound `p*f+q` on the open interval (0,1).
enum LinRoot {
    /// Bound crosses strictly inside; carries the root.
    Root(f64),
    /// No root in (0,1).
    Miss,
    /// Noise-scale slope cannot certify either side.
    Uncertain,
}

/// Root of `p*f+q` on (0,1): value, uncertain flag, or none.
///
/// Exact zero slope with exact zero value pins the bound and stays out of
/// open interiors; a noise-scale slope cannot certify either side, so the
/// pair abstains instead of guessing.
fn linear_root(p: f64, q: f64) -> LinRoot {
    if p.abs() <= EPS {
        if q.abs() <= EPS {
            return LinRoot::Uncertain;
        }
        return LinRoot::Miss;
    }
    let t = -q / p;
    if t > 0.0 && t < 1.0 {
        LinRoot::Root(t)
    } else {
        LinRoot::Miss
    }
}

/// Correctly-rounded 3-term sum matching `math.fsum((c, b, a))`.
///
/// The 2-term case (`middle = c + b/2`) is a single rounding either way.
/// Here Neumaier summation reproduces the correctly-rounded triple sum;
/// any residual last-ulp difference is absorbed by the outward double
/// `next_after` rounding of the Bernstein bounds below.
fn fsum3(x: f64, y: f64, z: f64) -> f64 {
    let mut sum = 0.0;
    let mut comp = 0.0;
    for v in [x, y, z] {
        let t = sum + v;
        if sum.abs() >= v.abs() {
            comp += (sum - t) + v;
        } else {
            comp += (v - t) + sum;
        }
        sum = t;
    }
    sum + comp
}

/// IEEE-754 `nextAfter(x, y)`, matching `math.nextafter` bit for bit.
///
/// Stable `next_up`/`next_down` cover the half-line cases, but the source
/// applies directed double steps, so this helper keeps the exact
/// direction. Zero steps to the smallest subnormal of `y`'s sign; equal
/// inputs return `y` (hence `-0.0` toward `+0.0` yields `+0.0`); NaN
/// propagates; finite overflow yields infinity without a trap.
fn next_after(x: f64, y: f64) -> f64 {
    if x.is_nan() || y.is_nan() {
        return f64::NAN;
    }
    if x == y {
        return y;
    }
    if x == 0.0 {
        return f64::from_bits(if y > 0.0 { 1 } else { (1u64 << 63) | 1 });
    }
    let mut bits = x.to_bits() as i64;
    if y > x {
        bits += 1;
    } else {
        bits -= 1;
    }
    f64::from_bits(bits as u64)
}

/// Roots of `a*f^2+b*f+c` on (0,1) with explicit degenerate cases.
///
/// Exact zero stays exact. A near-negative discriminant inside the
/// uncertainty band abstains before any no-roots decision; tangency at
/// exactly zero splits the interval there.
fn quad_roots(a: f64, b: f64, c: f64) -> (Vec<f64>, bool) {
    let scale = a.abs().max(b.abs()).max(c.abs());
    if scale <= EPS {
        return (vec![], true);
    }
    // Hobby's segment-site equality pieces use g in [0, 1]. In the
    // quadratic Bernstein basis the coefficients are c, c+b/2, c+b+a;
    // their convex hull bounds the polynomial. A strict common sign
    // certifies no local root even when a distant root is near tangent.
    // Round outward and retain the existing relative arithmetic band;
    // this does not relax genuine near-zero/tangency uncertainty.
    let middle = c + b / 2.0;
    let end = fsum3(c, b, a);
    let lower = next_after(
        next_after(c.min(middle).min(end), f64::NEG_INFINITY),
        f64::NEG_INFINITY,
    );
    let upper = next_after(
        next_after(c.max(middle).max(end), f64::INFINITY),
        f64::INFINITY,
    );
    if lower > EPS * scale || upper < -EPS * scale {
        return (vec![], false);
    }
    if a.abs() <= EPS * scale {
        if b.abs() <= EPS * scale {
            // Constant sign; the piece midpoint test decides keep/drop.
            return (vec![], false);
        }
        let t = -c / b;
        return (if t > 0.0 && t < 1.0 { vec![t] } else { vec![] }, false);
    }
    let disc = b * b - 4.0 * a * c;
    if disc == 0.0 {
        let t = -b / (2.0 * a);
        return (if t > 0.0 && t < 1.0 { vec![t] } else { vec![] }, false);
    }
    if disc.abs() <= EPS * scale * scale {
        return (vec![], true);
    }
    if disc < 0.0 {
        return (vec![], false);
    }
    let root = disc.sqrt();
    let q = -0.5 * (b + root.copysign(b));
    let mut out = Vec::new();
    for t in [q / a, c / q] {
        if t > 0.0 && t < 1.0 {
            out.push(t);
        }
    }
    (out, false)
}

fn seg_dist(pt: Point, a: Point, b: Point) -> (f64, f64) {
    let (dx, dy) = (b[0] - a[0], b[1] - a[1]);
    let denom = dx * dx + dy * dy;
    if denom == 0.0 {
        return (super::numeric::hypot(pt[0] - a[0], pt[1] - a[1]), 0.0);
    }
    let s = ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / denom;
    let c = if s < 0.0 {
        0.0
    } else if s > 1.0 {
        1.0
    } else {
        s
    };
    (
        super::numeric::hypot(pt[0] - (a[0] + c * dx), pt[1] - (a[1] + c * dy)),
        s,
    )
}

fn winding(pt: Point, loops: &[Vec<Point>]) -> i64 {
    let (x, y) = (pt[0], pt[1]);
    let mut total: i64 = 0;
    for lp in loops {
        let mut a = lp[lp.len() - 1];
        for &b in lp {
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

/// Center/radius affine coefficients over the frame overlap.
///
/// Solves the pair bisector in translated and scaled coordinates, so exact
/// zero stays exact and every later epsilon is relative. The parallel case
/// falls on the midpoint line, which is also affine.
fn affine_system(fr: &FrameInner, lo: f64, hi: f64) -> ((f64, f64), (f64, f64)) {
    let (t1, t2) = (fr.t1, fr.t2);
    let par = (t1[0] * t2[1] - t1[1] * t2[0]).abs() <= EPS;
    if par {
        // Opposed parallel lines share the midpoint line; radius is
        // the half gap. Line 2 sits at n1-coordinate sig_nn*c2 with
        // sig_nn = n1.n2 = +/-1. Zero gap or a degenerate across
        // direction yields no positive radius, hence no intervals.
        let (n1, u) = (fr.n1, fr.u);
        let sig_nn = n1[0] * fr.n2[0] + n1[1] * fr.n2[1];
        let center = (fr.c1 + sig_nn * fr.c2) / 2.0;
        let half = (fr.c1 - sig_nn * fr.c2).abs() / 2.0;
        let a = n1[0] * u[0] + n1[1] * u[1];
        if a.abs() <= EPS {
            return ((0.0, 0.0), (0.0, 0.0));
        }
        let lam0 = (center - (n1[0] * fr.d[0] + n1[1] * fr.d[1]) * lo) / a;
        let lam_p = -(n1[0] * fr.d[0] + n1[1] * fr.d[1]) * (hi - lo) / a;
        return ((lam0, half), (lam_p, 0.0));
    }
    let (a11, a12, a21, a22) = (fr.a11, fr.a12, fr.a21, fr.a22);
    let det = fr.det;
    let (n1, c1, c2) = (fr.n1, fr.c1, fr.c2);
    let d = fr.d;
    let k1 = n1[0] * d[0] + n1[1] * d[1];
    let k2 = fr.n2[0] * d[0] + fr.n2[1] * d[1];
    let b10 = c1 - k1 * lo;
    let b20 = c2 - k2 * lo;
    let lam0 = (a22 * b10 - a12 * b20) / det;
    let sig0 = (a11 * b20 - a21 * b10) / det;
    let lam_p = (a22 * (-k1) - a12 * (-k2)) / det * (hi - lo);
    let sig_p = (a11 * (-k2) - a21 * (-k1)) / det * (hi - lo);
    ((lam0, sig0), (lam_p, sig_p))
}

/// Exact shared-vertex test on common normalized coordinates.
fn coincides(pt: Point, ends: &[Point]) -> bool {
    ends.iter().any(|e| pt[0] == e[0] && pt[1] == e[1])
}

fn foot_frac(c: Point, p0: Point, p1: Point) -> Option<f64> {
    let (dx, dy) = (p1[0] - p0[0], p1[1] - p0[1]);
    let den = dx * dx + dy * dy;
    if den == 0.0 {
        return None;
    }
    Some(((c[0] - p0[0]) * dx + (c[1] - p0[1]) * dy) / den)
}

fn center_at(d: Point, u: Point, lo: f64, hi: f64, lam0: f64, lam_p: f64, t: f64) -> Point {
    let f = (t - lo) / (hi - lo);
    let lam = lam0 + lam_p * f;
    [d[0] * t + u[0] * lam, d[1] * t + u[1] * lam]
}

/// Evaluated medial contact at corridor parameter `t` (normalized space).
struct ContactEval {
    hit: Option<Contact>,
    stage: String,
    tag: Option<String>,
}

/// Competitor segment in pair-normalized coordinates borrowing its tag.
///
/// Normalized per pair (normalization depends on the pair origin and
/// overlap length); only the tag string is shared with the caller.
struct NormOther<'a> {
    seg: Segment,
    tag: &'a str,
}

/// Normalized borrowed competitor view of `others`.
///
/// Segment arithmetic keeps the direct paths' evaluation order; tags are
/// borrowed so repeated queries over one prepared set clone no strings.
fn norm_others<'a>(others: &'a [Border], o: Point, l0: f64) -> Vec<NormOther<'a>> {
    others
        .iter()
        .map(|ob| NormOther {
            seg: norm_seg(ob.seg, o, l0),
            tag: ob.tag.as_str(),
        })
        .collect()
}

/// Index-filtered borrowed view excluding two edge positions.
///
/// Preserves edge order and drops exactly the positions `ea` and `eb`,
/// matching a caller-side filter over the same slice.
fn norm_others_except<'a>(
    all: &'a [Border],
    o: Point,
    l0: f64,
    ea: usize,
    eb: usize,
) -> Vec<NormOther<'a>> {
    all.iter()
        .enumerate()
        .filter(|(i, _)| *i != ea && *i != eb)
        .map(|(_, ob)| NormOther {
            seg: norm_seg(ob.seg, o, l0),
            tag: ob.tag.as_str(),
        })
        .collect()
}

/// Normalized medial contact at corridor parameter `t`.
///
/// Endpoint-dominated contacts never qualify: vertex-dominated cells and
/// parabolic branches are unsupported. Clearance holds against every other
/// segment; equality within the relative band abstains as near-tangent
/// instead of passing.
fn contact_eval(
    fr: &FrameInner,
    lam_sig: ((f64, f64), (f64, f64)),
    seg_a: Segment,
    seg_b: Segment,
    t: f64,
    others: &[NormOther],
    loops: Option<&[Vec<Point>]>,
) -> ContactEval {
    let no = |stage: &str, tag: Option<String>| ContactEval {
        hit: None,
        stage: stage.to_string(),
        tag,
    };
    let ((lam0, sig0), (lam_p, sig_p)) = lam_sig;
    let f = (t - fr.lo) / (fr.hi - fr.lo);
    let sig = sig0 + sig_p * f;
    if !(sig > 0.0) {
        return no("nonpositive-radius", None);
    }
    let c = center_at(fr.d, fr.u, fr.lo, fr.hi, lam0, lam_p, t);
    let sa = foot_frac(c, seg_a[0], seg_a[1]);
    let sb = foot_frac(c, seg_b[0], seg_b[1]);
    let (sa, sb) = match (sa, sb) {
        (Some(sa), Some(sb)) => (sa, sb),
        _ => return no("degenerate-pair", None),
    };
    if !(sa > 0.0 && sa < 1.0) {
        return no("endpoint-foot-a", None);
    }
    if !(sb > 0.0 && sb < 1.0) {
        return no("endpoint-foot-b", None);
    }
    if let Some(loops) = loops {
        if winding(c, loops) == 0 {
            return no("outside-fill", None);
        }
    }
    let band = EPS * 1.0f64.max(sig);
    for o in others {
        let (ax, ay) = (o.seg[0], o.seg[1]);
        let (dist, _) = seg_dist(c, ax, ay);
        if dist < sig - band {
            return no("third-contact", Some(o.tag.to_string()));
        }
        if (dist - sig).abs() <= band {
            return no("uncertain-clearance", Some(o.tag.to_string()));
        }
    }
    let qa = [
        seg_a[0][0] + sa * (seg_a[1][0] - seg_a[0][0]),
        seg_a[0][1] + sa * (seg_a[1][1] - seg_a[0][1]),
    ];
    let qb = [
        seg_b[0][0] + sb * (seg_b[1][0] - seg_b[0][0]),
        seg_b[0][1] + sb * (seg_b[1][1] - seg_b[0][1]),
    ];
    ContactEval {
        hit: Some(Contact {
            center: c,
            r: sig,
            width: 2.0 * sig,
            qa,
            qb,
            sa,
            sb,
        }),
        stage: "clear".to_string(),
        tag: None,
    }
}

/// Certified medial contact at a corridor parameter.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Contact {
    pub center: Point,
    pub qa: Point,
    pub qb: Point,
    pub r: f64,
    pub width: f64,
    pub sa: f64,
    pub sb: f64,
}

/// Medial contact verdict with the per-piece stage/tag reasons.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ContactResult {
    pub status: String,
    pub hit: Option<Contact>,
    pub stage: String,
    pub tag: Option<String>,
}

/// Raw corridor plus translation/scale normalization bundle.
///
/// `o` is an input vertex and `l0` the raw overlap length, so translating
/// or uniformly scaling every input leaves the canonical verdict
/// unchanged. Canonical f in [0,1] maps to raw t by `lo + l0*f`.
/// Prepared once per segment pair (Hobby section 3.2 corridor/frame
/// checks) and reused by every dominance/contact query on that pair.
#[derive(Clone, Debug)]
pub(super) struct PairSetup {
    a: Segment,
    b: Segment,
    fr: FrameInner,
    lam_sig: ((f64, f64), (f64, f64)),
    o: Point,
    l0: f64,
    lo: f64,
    hi: f64,
    nlo: f64,
    nhi: f64,
}

impl PairSetup {
    /// Upper bound on every returned raw interval span, including rounding.
    /// Boyd/Mattingley bound-based pruning (not a geometric work cutoff):
    /// https://web.stanford.edu/class/ee364b/lectures/bb_notes.pdf, p. 3.
    /// Initial cuts lie in [0,1]. The single equality-root transport
    /// l + g*(r-l), with 0<=l<=r<=1 and 0<g<1, is nonnegative and at
    /// most nextUp(1): rounding r-l adds at most 2^-53, multiplication
    /// by g cannot increase it, and the rounded sum is at most nextUp(1).
    /// Monotone multiplication/addition then bound reconstructed endpoints
    /// lo + l0*f; monotone subtraction bounds their returned difference.
    /// Unsafe bounds retain full dominance evaluation, without a tolerance.
    pub(super) fn span_upper_bound(&self) -> Option<f64> {
        if !self.lo.is_finite() || !self.l0.is_finite() || self.l0 <= 0.0 {
            return None;
        }
        let hi = self.lo + self.l0 * next_after(1.0, f64::INFINITY);
        let span = hi - self.lo;
        (hi.is_finite() && span.is_finite() && span >= 0.0).then_some(span)
    }
}

/// Pair-setup failure verdict with the same status strings as the
/// direct dominance/contact paths.
#[derive(Clone, Debug)]
pub(super) struct SetupError {
    pub status: String,
    pub opp: Option<f64>,
}

fn norm_seg(seg: Segment, o: Point, l0: f64) -> Segment {
    [
        [(seg[0][0] - o[0]) / l0, (seg[0][1] - o[1]) / l0],
        [(seg[1][0] - o[0]) / l0, (seg[1][1] - o[1]) / l0],
    ]
}

fn norm_loops(loops: &[Vec<Point>], o: Point, l0: f64) -> Vec<Vec<Point>> {
    loops
        .iter()
        .map(|lp| {
            lp.iter()
                .map(|p| [(p[0] - o[0]) / l0, (p[1] - o[1]) / l0])
                .collect()
        })
        .collect()
}

/// Corridor/frame/affine checks for one segment pair.
///
/// Runs the same corridor, normalization, frame and affine steps as the
/// direct paths, with identical status strings and floating-point
/// evaluation order. A failed setup rejects the pair before any
/// competitor is constructed or normalized.
pub(super) fn prepare(a: Segment, b: Segment) -> Result<PairSetup, SetupError> {
    let cor = corridor(a, b).ok_or(SetupError {
        status: "no-overlap".to_string(),
        opp: None,
    })?;
    let l0 = cor.hi - cor.lo;
    let o = a[0];
    let xf = |p: Point| [(p[0] - o[0]) / l0, (p[1] - o[1]) / l0];
    let na = [xf(a[0]), xf(a[1])];
    let nb = [xf(b[0]), xf(b[1])];
    let d = cor.d;
    let base = d[0] * o[0] + d[1] * o[1];
    let nlo = (cor.lo - base) / l0;
    let nhi = (cor.hi - base) / l0;
    let cor_n = Corridor {
        d,
        u: cor.u,
        lo: nlo,
        hi: nhi,
        t1: cor.t1,
        t2: cor.t2,
        l0: nhi - nlo,
    };
    let fr = frame(na, nb, &cor_n);
    if fr.status != "ok" {
        return Err(SetupError {
            status: fr.status.clone(),
            opp: fr.opp,
        });
    }
    let inner = fr.inner.expect("ok frame carries constants");
    let lam_sig = affine_system(&inner, nlo, nhi);
    Ok(PairSetup {
        a: na,
        b: nb,
        fr: inner,
        lam_sig,
        o,
        l0,
        lo: cor.lo,
        hi: cor.hi,
        nlo,
        nhi,
    })
}

/// Medial contact at corridor parameter `t` with full guards.
///
/// `t` is the actual corridor projection in caller units. `others` excludes
/// the pair's own segments; each entry carries an opaque tag reported on
/// third contact.
pub fn contact(
    a: Segment,
    b: Segment,
    t: f64,
    others: &[Border],
    loops: Option<&[Vec<Point>]>,
) -> ContactResult {
    let setup = match prepare(a, b) {
        Ok(s) => s,
        Err(e) => {
            let stage = if e.status == "no-overlap" {
                "outside-overlap"
            } else {
                "degenerate-frame"
            };
            return ContactResult {
                hit: None,
                stage: stage.to_string(),
                tag: None,
                status: e.status,
            };
        }
    };
    contact_prepared(&setup, t, others, loops)
}

/// Medial contact reusing a prepared pair setup.
///
/// Same guards, verdicts and floating-point evaluation order as
/// [`contact`]; only the corridor/frame setup is shared instead of
/// recomputed, and competitor tags are borrowed.
pub(super) fn contact_prepared(
    setup: &PairSetup,
    t: f64,
    others: &[Border],
    loops: Option<&[Vec<Point>]>,
) -> ContactResult {
    let (lo, hi, l0, o) = (setup.lo, setup.hi, setup.l0, setup.o);
    if !(lo < t && t < hi) {
        return ContactResult {
            hit: None,
            stage: "outside-overlap".to_string(),
            tag: None,
            status: "ok".to_string(),
        };
    }
    let fr = setup.fr.clone();
    let f = (t - lo) / (hi - lo);
    let tn = setup.nlo + (setup.nhi - setup.nlo) * f;
    let on = norm_others(others, o, l0);
    let ln = loops.map(|lps| norm_loops(lps, o, l0));
    let out = contact_eval(&fr, setup.lam_sig, setup.a, setup.b, tn, &on, ln.as_deref());
    let hit = out.hit.map(|h| Contact {
        center: [o[0] + l0 * h.center[0], o[1] + l0 * h.center[1]],
        r: l0 * h.r,
        width: l0 * h.width,
        qa: [o[0] + l0 * h.qa[0], o[1] + l0 * h.qa[1]],
        qb: [o[0] + l0 * h.qb[0], o[1] + l0 * h.qb[1]],
        sa: h.sa,
        sb: h.sb,
    });
    ContactResult {
        hit,
        stage: out.stage,
        tag: out.tag,
        status: "ok".to_string(),
    }
}

/// Retained dominance interval in raw corridor units.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Interval {
    pub lo: f64,
    pub hi: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub speed: Option<f64>,
}

/// Per-piece verdict over canonical f in [0,1].
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Span {
    pub f0: f64,
    pub f1: f64,
    pub kept: bool,
    pub stage: String,
    pub tag: Option<String>,
}

/// Open dominance intervals of a pair with per-piece reasons.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Dominance {
    pub status: String,
    pub intervals: Vec<Interval>,
    pub spans: Vec<Span>,
    pub speed: Option<f64>,
    pub opp: Option<f64>,
}

/// Competitor distance branch at a piece midpoint.
enum Branch {
    /// Closest feature is an endpoint.
    Pt(Point),
    /// Closest feature is interior; stores the supporting line.
    Ln { ax: f64, ay: f64, dx: f64, dy: f64 },
}

/// Open dominance intervals of the pair over canonical f in [0,1].
///
/// Splits at open foot interiors, positive radius, competitor projection
/// endpoints on both sides, and quadratic equality events in global f;
/// every sampled midpoint is rechecked. Returns raw corridor endpoints,
/// the medial speed per corridor unit, and the per-piece stage/tag
/// reasons.
pub fn dominance(
    a: Segment,
    b: Segment,
    others: &[Border],
    loops: Option<&[Vec<Point>]>,
) -> Dominance {
    let fail = |status: String, opp: Option<f64>| Dominance {
        status,
        intervals: vec![],
        spans: vec![],
        speed: None,
        opp,
    };
    let setup = match prepare(a, b) {
        Ok(s) => s,
        Err(e) => return fail(e.status, e.opp),
    };
    dominance_prepared(&setup, others, loops)
}

/// Open dominance intervals reusing a prepared pair setup.
///
/// Same splits, guards, verdicts and floating-point evaluation order as
/// [`dominance`]; only the corridor/frame setup is shared instead of
/// recomputed, and competitor tags are borrowed.
pub(super) fn dominance_prepared(
    setup: &PairSetup,
    others: &[Border],
    loops: Option<&[Vec<Point>]>,
) -> Dominance {
    let (o, l0) = (setup.o, setup.l0);
    let on = norm_others(others, o, l0);
    let ln = loops.map(|lps| norm_loops(lps, o, l0));
    dominance_core(setup, &on, ln.as_deref())
}

/// Dominance over an already normalized borrowed competitor view.
///
/// Shared body behind [`dominance`], [`dominance_prepared`] and
/// [`CompetitorSet::dominance_for`]; every verdict keeps the direct
/// path's splits, guards and floating-point evaluation order.
fn dominance_core(setup: &PairSetup, on: &[NormOther], ln: Option<&[Vec<Point>]>) -> Dominance {
    let fail = |status: String, opp: Option<f64>| Dominance {
        status,
        intervals: vec![],
        spans: vec![],
        speed: None,
        opp,
    };
    let (fr, lam_sig) = (&setup.fr, setup.lam_sig);
    let (pa, pb) = (setup.a, setup.b);
    let l0 = setup.l0;
    let lo = setup.lo;
    let (nlo, nhi) = (setup.nlo, setup.nhi);
    let ((lam0, sig0), (lam_p, sig_p)) = lam_sig;

    let center = |f: f64| center_at(fr.d, fr.u, nlo, nhi, lam0, lam_p, nlo + (nhi - nlo) * f);

    let mut splits = vec![0.0, 1.0];
    // Foot bounds and radius bound are linear in f by the affine
    // bisector; two-point values give global-f roots directly.
    for is_a in [true, false] {
        let (v0, v1) = if is_a {
            (
                foot_frac(center(0.0), pa[0], pa[1]),
                foot_frac(center(1.0), pa[0], pa[1]),
            )
        } else {
            (
                foot_frac(center(0.0), pb[0], pb[1]),
                foot_frac(center(1.0), pb[0], pb[1]),
            )
        };
        let (v0, v1) = match (v0, v1) {
            (Some(v0), Some(v1)) => (v0, v1),
            _ => return fail("degenerate-pair".to_string(), None),
        };
        for edge in [0.0, 1.0] {
            match linear_root(v1 - v0, v0 - edge) {
                LinRoot::Uncertain => return fail("uncertain-foot".to_string(), None),
                LinRoot::Root(root) => splits.push(root),
                LinRoot::Miss => {}
            }
        }
    }
    match linear_root(lam_sig.1 .0, sig0) {
        LinRoot::Uncertain => return fail("uncertain-radius".to_string(), None),
        LinRoot::Root(root) => splits.push(root),
        LinRoot::Miss => {}
    }
    // Competitor projection endpoints split point/line pieces on both
    // sides; equality events are quadratics in global f.
    for ob in on {
        let (ax, ay) = (ob.seg[0][0], ob.seg[0][1]);
        let (bx, by) = (ob.seg[1][0], ob.seg[1][1]);
        let (dx, dy) = (bx - ax, by - ay);
        let den = dx * dx + dy * dy;
        if den == 0.0 {
            continue;
        }
        let (c0, c1) = (center(0.0), center(1.0));
        let s0 = ((c0[0] - ax) * dx + (c0[1] - ay) * dy) / den;
        let s1 = ((c1[0] - ax) * dx + (c1[1] - ay) * dy) / den;
        for edge in [0.0, 1.0] {
            match linear_root(s1 - s0, s0 - edge) {
                LinRoot::Uncertain => return fail("uncertain-projection".to_string(), None),
                LinRoot::Root(root) => splits.push(root),
                LinRoot::Miss => {}
            }
        }
    }
    let mut cuts = to_cuts(&mut splits);
    // Midpoint of each piece selects its point/line branches; the
    // three-point sampler re-evaluates center and radius per f.
    let eval_f_c = |f: f64| -> (Point, f64, Option<f64>, Option<f64>) {
        let tn = nlo + (nhi - nlo) * f;
        let c = center_at(fr.d, fr.u, fr.lo, fr.hi, lam0, lam_p, tn);
        let sig = sig0 + sig_p * f;
        (
            c,
            sig,
            foot_frac(c, pa[0], pa[1]),
            foot_frac(c, pb[0], pb[1]),
        )
    };
    let classify = |cm: Point| -> Vec<Branch> {
        on.iter()
            .map(|ob| {
                let (ax, ay) = (ob.seg[0][0], ob.seg[0][1]);
                let (bx, by) = (ob.seg[1][0], ob.seg[1][1]);
                let (dx, dy) = (bx - ax, by - ay);
                let den = dx * dx + dy * dy;
                if den == 0.0 {
                    return Branch::Pt([ax, ay]);
                }
                let sm = ((cm[0] - ax) * dx + (cm[1] - ay) * dy) / den;
                if sm <= 0.0 {
                    Branch::Pt([ax, ay])
                } else if sm >= 1.0 {
                    Branch::Pt([bx, by])
                } else {
                    Branch::Ln { ax, ay, dx, dy }
                }
            })
            .collect()
    };
    // Three-point interpolation gives global-f quadratic
    // coefficients; tangency and near-tangent bands abstain. A
    // point branch at a shared paired endpoint is never re-solved:
    // |C-V|^2-r^2 = |foot-V|^2 by Pythagoras, so the only zero is
    // the already-split foot event and solving reads float noise.
    let ends = [pa[0], pa[1], pb[0], pb[1]];
    let mut extra = Vec::new();
    for (l, r) in cuts.clone() {
        let m = (l + r) / 2.0;
        let (cm, _, _, _) = eval_f_c(m);
        let branches = classify(cm);
        for branch in &branches {
            if let Branch::Pt(pt) = branch {
                if coincides(*pt, &ends) {
                    continue;
                }
            }
            let mut qs = Vec::with_capacity(3);
            for f in [l, m, r] {
                let (cf, sigf, _, _) = eval_f_c(f);
                let (ex, ey) = match branch {
                    Branch::Pt(pt) => (pt[0], pt[1]),
                    Branch::Ln { ax, ay, dx, dy } => {
                        let sm = ((cf[0] - ax) * dx + (cf[1] - ay) * dy) / (dx * dx + dy * dy);
                        (ax + sm * dx, ay + sm * dy)
                    }
                };
                qs.push((cf[0] - ex).powi(2) + (cf[1] - ey).powi(2) - sigf * sigf);
            }
            let (q0, q1, q2) = (qs[0], qs[1], qs[2]);
            let qa = 2.0 * (q0 - 2.0 * q1 + q2);
            let qb = 4.0 * q1 - 3.0 * q0 - q2;
            let qc = q0;
            let (roots, uncertain) = quad_roots(qa, qb, qc);
            if uncertain {
                return fail("uncertain-equality".to_string(), None);
            }
            for g in roots {
                extra.push(l + g * (r - l));
            }
        }
    }
    splits.extend(extra);
    // Second pass after equality splits: every piece midpoint decides
    // its own span, so constant-sign pieces keep or drop on evidence.
    cuts = to_cuts(&mut splits);
    let speed = super::numeric::hypot(
        fr.d[0] * (nhi - nlo) + fr.u[0] * lam_p,
        fr.d[1] * (nhi - nlo) + fr.u[1] * lam_p,
    );
    let mut intervals = Vec::new();
    let mut spans = Vec::new();
    let mut kept: Vec<(f64, f64)> = Vec::new();
    for (l, r) in &cuts {
        let m = (l + r) / 2.0;
        let tn = nlo + (nhi - nlo) * m;
        let out = contact_eval(&fr, lam_sig, pa, pb, tn, &on, ln.as_deref());
        spans.push(Span {
            f0: *l,
            f1: *r,
            kept: out.hit.is_some(),
            stage: out.stage,
            tag: out.tag,
        });
        if spans.last().expect("just pushed").kept {
            kept.push((*l, *r));
        }
    }
    // Merge adjacent kept cells whose shared boundary itself passes the
    // strict contact guard: projection splits can cut one valid branch,
    // and sampling wants the uncut interval. A third-contact boundary
    // never merges.
    let mut merged: Vec<(f64, f64)> = Vec::new();
    for (l, r) in kept {
        if let Some(last) = merged.last_mut() {
            if last.1 == l {
                let tn = nlo + (nhi - nlo) * l;
                if contact_eval(&fr, lam_sig, pa, pb, tn, &on, ln.as_deref())
                    .hit
                    .is_some()
                {
                    last.1 = r;
                    continue;
                }
            }
        }
        merged.push((l, r));
    }
    for (l, r) in merged {
        intervals.push(Interval {
            lo: lo + l0 * l,
            hi: lo + l0 * r,
            speed: Some(speed),
        });
    }
    Dominance {
        status: "ok".to_string(),
        intervals,
        spans,
        speed: Some(speed),
        opp: None,
    }
}

/// Tagged competitors for every edge position, built once per geometry.
///
/// Tags match the direct call sites (`e({index})`); positions line up with
/// the caller's edge order so [`CompetitorSet`] exclusion drops exactly the
/// paired edges.
pub(super) fn tagged_borders(segments: &[Segment]) -> Vec<Border> {
    segments
        .iter()
        .enumerate()
        .map(|(i, seg)| Border {
            seg: *seg,
            tag: format!("e({i})"),
        })
        .collect()
}

/// Competitor set prepared once per source geometry.
///
/// Holds the invariant per-edge borders and tags. Queries borrow from it
/// through an index-filtered view, so repeated pair attempts share the
/// tags instead of cloning every entry per pair. Exclusion drops exactly
/// the positions `ea` and `eb` in edge order, matching a caller-side
/// filter over the same slice.
#[derive(Clone, Debug)]
pub(super) struct CompetitorSet {
    borders: Vec<Border>,
}

impl CompetitorSet {
    pub fn new(borders: Vec<Border>) -> Self {
        Self { borders }
    }

    /// Dominance of `setup` against every competitor except `ea`/`eb`.
    ///
    /// Same verdicts and floating-point evaluation order as [`dominance`]
    /// on the same pair with a caller-filtered slice.
    pub fn dominance_for(
        &self,
        setup: &PairSetup,
        ea: usize,
        eb: usize,
        loops: Option<&[Vec<Point>]>,
    ) -> Dominance {
        let (o, l0) = (setup.o, setup.l0);
        let on = norm_others_except(&self.borders, o, l0, ea, eb);
        let ln = loops.map(|lps| norm_loops(lps, o, l0));
        dominance_core(setup, &on, ln.as_deref())
    }

    /// Contact of `setup` at `t` against every competitor except `ea`/`eb`.
    ///
    /// Same verdicts and floating-point evaluation order as [`contact`]
    /// on the same pair with a caller-filtered slice.
    pub fn contact_for(
        &self,
        setup: &PairSetup,
        t: f64,
        ea: usize,
        eb: usize,
        loops: Option<&[Vec<Point>]>,
    ) -> ContactResult {
        let (lo, hi, l0, o) = (setup.lo, setup.hi, setup.l0, setup.o);
        if !(lo < t && t < hi) {
            return ContactResult {
                hit: None,
                stage: "outside-overlap".to_string(),
                tag: None,
                status: "ok".to_string(),
            };
        }
        let fr = setup.fr.clone();
        let f = (t - lo) / (hi - lo);
        let tn = setup.nlo + (setup.nhi - setup.nlo) * f;
        let on = norm_others_except(&self.borders, o, l0, ea, eb);
        let ln = loops.map(|lps| norm_loops(lps, o, l0));
        let out = contact_eval(&fr, setup.lam_sig, setup.a, setup.b, tn, &on, ln.as_deref());
        let hit = out.hit.map(|h| Contact {
            center: [o[0] + l0 * h.center[0], o[1] + l0 * h.center[1]],
            r: l0 * h.r,
            width: l0 * h.width,
            qa: [o[0] + l0 * h.qa[0], o[1] + l0 * h.qa[1]],
            qb: [o[0] + l0 * h.qb[0], o[1] + l0 * h.qb[1]],
            sa: h.sa,
            sb: h.sb,
        });
        ContactResult {
            hit,
            stage: out.stage,
            tag: out.tag,
            status: "ok".to_string(),
        }
    }
}

/// Sorted unique cut list from raw splits, dropping hairline pieces.
fn to_cuts(splits: &mut Vec<f64>) -> Vec<(f64, f64)> {
    splits.sort_by(|a, b| a.partial_cmp(b).expect("splits are finite"));
    splits.dedup();
    let mut cuts = Vec::new();
    for w in splits.windows(2) {
        let (l, r) = (w[0], w[1]);
        if r - l <= 1e-12 {
            continue;
        }
        cuts.push((l, r));
    }
    cuts
}

/// Certified core of retained dominance intervals.
///
/// Kept boundaries are float equality events with arithmetic
/// uncertainty; ownership is certified only away from them. Each end
/// retreats by margin of the corridor span, using the module's own
/// relative guard rather than any fitted value. Emptied intervals
/// drop, and every surviving midpoint is rechecked with full guards.
pub fn core_intervals(
    a: Segment,
    b: Segment,
    kept: &[Interval],
    others: &[Border],
    loops: Option<&[Vec<Point>]>,
) -> Option<Vec<Interval>> {
    core_intervals_with_margin(a, b, kept, others, loops, EPS)
}

fn core_intervals_with_margin(
    a: Segment,
    b: Segment,
    kept: &[Interval],
    others: &[Border],
    loops: Option<&[Vec<Point>]>,
    margin: f64,
) -> Option<Vec<Interval>> {
    let setup = prepare(a, b).ok()?;
    let span = setup.hi - setup.lo;
    if !(span > 0.0) {
        return None;
    }
    let trim = margin * span;
    let mut out = Vec::new();
    for iv in kept {
        let (lo, hi) = (iv.lo + trim, iv.hi - trim);
        if !(hi > lo) {
            continue;
        }
        let seen = contact(a, b, (lo + hi) / 2.0, others, loops);
        if seen.status != "ok" || seen.hit.is_none() {
            continue;
        }
        out.push(Interval {
            lo,
            hi,
            speed: None,
        });
    }
    Some(out)
}

/// Affine contact-foot ranges over retained dominance intervals.
///
/// Hobby 3.2 assigns each medial point to its nearest boundary sites;
/// center and feet are affine in the corridor parameter, so each kept
/// interval maps to foot ranges bounded by its endpoint values. Any
/// degenerate evaluation fails closed with `None` instead of guessing.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct FootRange {
    pub a: [f64; 2],
    pub b: [f64; 2],
}

pub fn foot_ranges(a: Segment, b: Segment, kept: &[Interval]) -> Option<Vec<FootRange>> {
    let setup = prepare(a, b).ok()?;
    let (fr, lam_sig) = (&setup.fr, setup.lam_sig);
    let (pa, pb) = (setup.a, setup.b);
    let (lo, hi) = (setup.lo, setup.hi);
    let (nlo, nhi) = (setup.nlo, setup.nhi);
    let span = hi - lo;
    if !(span > 0.0) {
        return None;
    }
    let ((lam0, _), (lam_p, _)) = lam_sig;
    let mut out = Vec::new();
    for iv in kept {
        let (mut fas, mut fbs) = (Vec::new(), Vec::new());
        for t in [iv.lo, iv.hi] {
            let f = (t - lo) / span;
            if !(0.0 <= f && f <= 1.0) {
                return None;
            }
            let tn = nlo + (nhi - nlo) * f;
            let c = center_at(fr.d, fr.u, fr.lo, fr.hi, lam0, lam_p, tn);
            let fa = foot_frac(c, pa[0], pa[1])?;
            let fb = foot_frac(c, pb[0], pb[1])?;
            fas.push(fa);
            fbs.push(fb);
        }
        out.push(FootRange {
            a: [fas[0].min(fas[1]), fas[0].max(fas[1])],
            b: [fbs[0].min(fbs[1]), fbs[0].max(fbs[1])],
        });
    }
    Some(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn span_bound_covers_rounded_root_transport_and_endpoint_reconstruction() {
        // Bound-based pruning must enclose the actual binary64 span,
        // including cancellation, subnormals and single root transport;
        // an ideal real-valued corridor length is not sufficient.
        let mut setup =
            prepare([[0.0, 0.0], [10.0, 0.0]], [[0.0, 2.0], [10.0, 2.0]]).expect("parallel pair");
        let tiny = f64::from_bits(1);
        let fs = [0.0, tiny, 0.125, 0.5, 0.75, next_after(1.0, 0.0), 1.0];
        let mut transported = fs.to_vec();
        for &l in &fs {
            for &r in &fs {
                if l <= r {
                    for &g in &fs[1..fs.len() - 1] {
                        let f = l + g * (r - l);
                        assert!(f >= 0.0 && f <= next_after(1.0, f64::INFINITY));
                        transported.push(f);
                    }
                }
            }
        }
        for lo in [
            -1e300, -1e20, -0.1, -tiny, -0.0, 0.0, tiny, 0.1, 1e20, 1e300,
        ] {
            for l0 in [tiny, 1e-300, 0.1, 1.0, 1e20, 1e300] {
                setup.lo = lo;
                setup.l0 = l0;
                if let Some(bound) = setup.span_upper_bound() {
                    for &f in &transported {
                        let endpoint = lo + l0 * f;
                        assert!(endpoint - lo <= bound);
                        assert!(endpoint >= lo);
                    }
                }
            }
        }
        for l0 in [0.0, -1.0, f64::NAN, f64::INFINITY, f64::MAX] {
            setup.lo = 0.0;
            setup.l0 = l0;
            assert!(setup.span_upper_bound().is_none());
        }
        setup.l0 = 1.0;
        for lo in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            setup.lo = lo;
            assert!(setup.span_upper_bound().is_none());
        }
    }

    #[test]
    fn span_bound_encloses_full_dominance_intervals() {
        // Independent full interval construction is the rejection oracle:
        // the bound neither inspects nor changes its cuts or verdicts.
        for scale in [0.125, 1.0, 8.0] {
            for shift in [-32.0, 0.0, 37.5] {
                let xf = |p: Point| [shift + scale * p[0], -shift + scale * p[1]];
                for taper in [-0.25, 0.0, 0.25] {
                    let a = [[0.0, 0.0], [10.0, 0.0]].map(xf);
                    let b = [[0.0, 2.0], [10.0, 2.0 + taper]].map(xf);
                    let setup = prepare(a, b).expect("opposing borders");
                    let bound = setup.span_upper_bound().unwrap();
                    for x in [-1.0, 0.0, 2.0, 5.0, 10.0, 11.0] {
                        let other = [Border {
                            seg: [[x, 0.5], [x, 1.5]].map(xf),
                            tag: "competitor".into(),
                        }];
                        let dom = dominance_prepared(&setup, &other, None);
                        for span in dom.intervals {
                            assert!(span.hi - span.lo <= bound);
                        }
                    }
                }
            }
        }
    }

    fn close(a: f64, b: f64, tol: f64) -> bool {
        (a - b).abs() <= tol
    }

    fn border(seg: Segment, tag: &str) -> Border {
        Border {
            seg,
            tag: tag.to_string(),
        }
    }

    #[test]
    fn opp_cos_matches_std_cos() {
        // Source value: math.cos(math.radians(157.0)); std cos is an
        // acceptable equivalent (sub-ulp agreement, not a fitted value).
        let std = 157.0f64.to_radians().cos();
        assert!((OPP_COS - std).abs() <= 1e-15, "OPP_COS {OPP_COS} vs {std}");
        assert!(OPP_COS < 0.0 && OPP_COS > -1.0);
    }

    #[test]
    fn quad_certificate_ports() {
        // Port of test_interval_certificate.py decision cases.
        // Distant near-double root: no local event, no uncertainty.
        let b = -0.0012;
        let c = 3.06;
        let a = b * b / (4.0 * c) * (1.0 + 1e-12);
        assert_eq!(quad_roots(a, b, c), (vec![], false));
        assert_eq!(quad_roots(-a, -b, -c), (vec![], false));
        // Local tangency splits; the noise band above it abstains.
        assert_eq!(quad_roots(1.0, -1.0, 0.25), (vec![0.5], false));
        assert_eq!(quad_roots(1.0, -1.0, 0.25 + 1e-12), (vec![], true));
        assert_eq!(quad_roots(0.0, 0.0, 0.0), (vec![], true));
        let (mut roots, uncertain) = quad_roots(1.0, -1.0, 0.1875);
        assert!(!uncertain);
        roots.sort_by(|x, y| x.partial_cmp(y).unwrap());
        assert_eq!(roots, vec![0.25, 0.75]);
        // Bernstein common sign certifies positivity with no local root.
        assert_eq!(quad_roots(0.018, 0.061, 0.0507), (vec![], false));
        assert_eq!(quad_roots(-0.018, -0.061, -0.0507), (vec![], false));
        // Arithmetic band at an endpoint is not certified.
        assert_eq!(quad_roots(1.0, 1e-12, 1e-24), (vec![], true));
    }

    #[test]
    fn clear_pair_values() {
        // Parallel pair: disk center (5,1), radius 1, full-width verdicts.
        let a = [[0.0, 0.0], [10.0, 0.0]];
        let b = [[0.0, 2.0], [10.0, 2.0]];
        let cor = corridor(a, b).expect("overlap");
        assert!(close(cor.lo, 0.0, 1e-12) && close(cor.hi, 10.0, 1e-12));
        assert!(close(cor.l0, 10.0, 1e-12));
        let fr = frame(a, b, &cor);
        assert_eq!(fr.status, "ok");
        let d = dominance(a, b, &[], None);
        assert_eq!(d.status, "ok");
        assert_eq!(d.spans.len(), 1);
        assert!(d.spans[0].kept && d.spans[0].stage == "clear");
        assert!(close(d.spans[0].f0, 0.0, 0.0) && close(d.spans[0].f1, 1.0, 0.0));
        assert_eq!(d.intervals.len(), 1);
        assert!(close(d.intervals[0].lo, 0.0, 1e-12));
        assert!(close(d.intervals[0].hi, 10.0, 1e-12));
        assert!(close(d.speed.unwrap(), 1.0, 1e-12));
        assert_eq!(d.intervals[0].speed, d.speed);
        let c = contact(a, b, 5.0, &[], None);
        assert_eq!((c.status.as_str(), c.stage.as_str()), ("ok", "clear"));
        let hit = c.hit.expect("clear disk");
        for (got, want) in [
            (hit.center[0], 5.0),
            (hit.center[1], 1.0),
            (hit.r, 1.0),
            (hit.width, 2.0),
            (hit.qa[0], 5.0),
            (hit.qa[1], 0.0),
            (hit.qb[0], 5.0),
            (hit.qb[1], 2.0),
            (hit.sa, 0.5),
            (hit.sb, 0.5),
        ] {
            assert!(close(got, want, 1e-12), "{got} vs {want}");
        }
    }

    #[test]
    fn contact_stages() {
        let a = [[0.0, 0.0], [10.0, 0.0]];
        let b = [[0.0, 2.0], [10.0, 2.0]];
        let cross = vec![border([[4.9, -1.0], [5.1, 3.0]], "x")];
        let hit = contact(a, b, 5.0, &cross, None);
        assert_eq!(hit.stage, "third-contact");
        assert_eq!(hit.tag.as_deref(), Some("x"));
        assert!(hit.hit.is_none());
        let tangent = vec![border([[4.0, 2.0], [6.0, 2.0]], "tan")];
        let near = contact(a, b, 5.0, &tangent, None);
        assert_eq!(near.stage, "uncertain-clearance");
        assert_eq!(near.tag.as_deref(), Some("tan"));
        for t in [0.0, 10.0] {
            let out = contact(a, b, t, &[], None);
            assert_eq!(
                (out.status.as_str(), out.stage.as_str()),
                ("ok", "outside-overlap")
            );
        }
        // Foot exits segment a just inside the corridor: endpoint-foot-a.
        let c = [[1.0, 1.0], [9.0, 3.0]];
        let e = [[0.0, 0.0], [10.0, 0.0]];
        let foot = contact(c, e, 1.115, &[], None);
        assert_eq!(foot.stage, "endpoint-foot-a");
        assert!(foot.hit.is_none());
        // Empty overlap fails closed through the corridor.
        let no = contact(
            [[0.0, 0.0], [1.0, 0.0]],
            [[5.0, 5.0], [6.0, 5.0]],
            0.5,
            &[],
            None,
        );
        assert_eq!(
            (no.status.as_str(), no.stage.as_str()),
            ("no-overlap", "outside-overlap")
        );
    }

    #[test]
    fn dominance_gates() {
        // L corner: opposed by ~0 degrees, pruned as a corner branch.
        let l = dominance(
            [[0.0, 0.0], [10.0, 0.0]],
            [[0.0, 0.0], [0.0, 10.0]],
            &[],
            None,
        );
        assert_eq!(l.status, "opposition-pruned");
        assert!(l.opp.is_some_and(|o| o == 0.0));
        // Sub-unit gap sits inside the relative noise band.
        let tiny = dominance(
            [[0.0, 0.0], [10.0, 0.0]],
            [[0.0, 1e-12], [10.0, 1e-12]],
            &[],
            None,
        );
        assert_eq!(tiny.status, "uncertain-side");
        // Disjoint projections have no corridor.
        let none = dominance(
            [[0.0, 0.0], [1.0, 0.0]],
            [[5.0, 5.0], [6.0, 5.0]],
            &[],
            None,
        );
        assert_eq!(none.status, "no-overlap");
        // Tilted pair: leading piece drops on the a-foot, then clears.
        let t = dominance(
            [[1.0, 1.0], [9.0, 3.0]],
            [[0.0, 0.0], [10.0, 0.0]],
            &[],
            None,
        );
        assert_eq!(t.status, "ok");
        assert_eq!(t.spans.len(), 2);
        assert!(!t.spans[0].kept && t.spans[0].stage == "endpoint-foot-a");
        assert!(close(t.spans[0].f0, 0.0, 0.0));
        assert!(close(t.spans[0].f1, 0.007577, 1e-6));
        assert!(t.spans[1].kept && t.spans[1].stage == "clear");
        assert!(t.spans[1].f0 == t.spans[0].f1 && close(t.spans[1].f1, 1.0, 0.0));
        assert_eq!(t.intervals.len(), 1);
        assert!(close(t.intervals[0].lo, 1.1767082956052428, 1e-9));
        assert!(close(t.intervals[0].hi, 9.29911780123324, 1e-9));
    }

    #[test]
    fn dominance_translation_invariant() {
        // Port of the Python translation-invariance control: normalized
        // spans agree across shifts, so verdicts cannot depend on origin.
        let mut verdicts = Vec::new();
        for shift in [0.0, 37.5, -1024.0] {
            let p = |x: f64, y: f64| [x + shift, y + shift];
            let a = [p(0.0, 0.0), p(10.0, 10.0)];
            let b = [p(-1.0, 1.0), p(9.0, 11.0)];
            let lp = vec![a[0], a[1], b[1], b[0]];
            let far = p(1000.0, 1000.0);
            let others = [border([far, far], "far-point")];
            let result = dominance(a, b, &others, Some(&[lp]));
            assert_eq!(result.status, "ok");
            assert!(!result.intervals.is_empty());
            let cor = corridor(a, b).expect("overlap");
            let len = cor.hi - cor.lo;
            verdicts.push(
                result
                    .intervals
                    .iter()
                    .map(|iv| [(iv.lo - cor.lo) / len, (iv.hi - cor.lo) / len])
                    .collect::<Vec<_>>(),
            );
        }
        for actual in verdicts.iter().skip(1) {
            assert_eq!(actual.len(), verdicts[0].len());
            for (got, want) in actual.iter().zip(verdicts[0].iter()) {
                assert!(close(got[0], want[0], 1e-12) && close(got[1], want[1], 1e-12));
            }
        }
    }

    #[test]
    fn dominance_uniform_scale() {
        // Uniform scaling scales corridor endpoints and keeps stages.
        let a = [[0.0, 0.0], [10.0, 0.0]];
        let b = [[1.0, 1.0], [9.0, 3.0]];
        let base = dominance(a, b, &[], None);
        let k = 2.5;
        let sc = |p: Point| [p[0] * k, p[1] * k];
        let sa = [sc(a[0]), sc(a[1])];
        let sb = [sc(b[0]), sc(b[1])];
        let scaled = dominance(sa, sb, &[], None);
        assert_eq!((base.status.as_str(), scaled.status.as_str()), ("ok", "ok"));
        assert_eq!(base.intervals.len(), scaled.intervals.len());
        for (got, want) in scaled.intervals.iter().zip(base.intervals.iter()) {
            assert!(close(got.lo, want.lo * k, 1e-9));
            assert!(close(got.hi, want.hi * k, 1e-9));
        }
        let stages = |d: &Dominance| {
            d.spans
                .iter()
                .map(|s| (s.kept, s.stage.clone()))
                .collect::<Vec<_>>()
        };
        assert_eq!(stages(&scaled), stages(&base));
    }

    #[test]
    fn dominance_reflection() {
        // Mirroring y preserves intervals and widths, mirrors centers.
        let a = [[1.0, 1.0], [9.0, 3.0]];
        let b = [[0.0, 0.0], [10.0, 0.0]];
        let mir = |p: Point| [p[0], -p[1]];
        let ma = [mir(a[0]), mir(a[1])];
        let mb = [mir(b[0]), mir(b[1])];
        let (d0, d1) = (dominance(a, b, &[], None), dominance(ma, mb, &[], None));
        assert_eq!((d0.status.as_str(), d1.status.as_str()), ("ok", "ok"));
        assert_eq!(d0.intervals.len(), d1.intervals.len());
        for (x, y) in d0.intervals.iter().zip(d1.intervals.iter()) {
            assert!(close(x.lo, y.lo, 1e-12) && close(x.hi, y.hi, 1e-12));
        }
        let t = (d0.intervals[0].lo + d0.intervals[0].hi) / 2.0;
        let (h0, h1) = (
            contact(a, b, t, &[], None).hit.expect("clear"),
            contact(ma, mb, t, &[], None).hit.expect("clear"),
        );
        assert!(close(h0.width, h1.width, 1e-12));
        assert!(close(h0.width, 2.0075774975293577, 1e-9));
        assert!(close(h0.center[0], h1.center[0], 1e-12));
        assert!(close(h0.center[1], -h1.center[1], 1e-12));
        assert!(close(h0.center[0], 5.153882032022076, 1e-9));
        assert!(close(h0.center[1], 1.003788748764679, 1e-9));
    }

    #[test]
    fn core_trims_eps_margin() {
        // EPS retreat on both ends of each kept interval, midpoint
        // rechecked; emptied intervals drop; setup failure gives None.
        let a = [[0.0, 0.0], [10.0, 0.0]];
        let b = [[0.0, 2.0], [10.0, 2.0]];
        let d = dominance(a, b, &[], None);
        let core = core_intervals(a, b, &d.intervals, &[], None).expect("core");
        assert_eq!(core.len(), 1);
        assert!(close(core[0].lo, 1e-8, 1e-20));
        assert!(close(core[0].hi, 9.99999999, 1e-12));
        assert_eq!(core[0].speed, None);
        let sliver = [Interval {
            lo: 0.0,
            hi: 1e-9,
            speed: None,
        }];
        assert_eq!(
            core_intervals(a, b, &sliver, &[], None)
                .expect("setup ok")
                .len(),
            0
        );
        assert!(core_intervals(
            [[0.0, 0.0], [1.0, 0.0]],
            [[5.0, 5.0], [6.0, 5.0]],
            &d.intervals,
            &[],
            None
        )
        .is_none());
    }

    #[test]
    fn foot_range_bounds() {
        // Affine foot ranges are bounded by kept-endpoint values; an
        // out-of-span endpoint fails closed.
        let a = [[0.0, 0.0], [10.0, 0.0]];
        let b = [[0.0, 2.0], [10.0, 2.0]];
        let d = dominance(a, b, &[], None);
        let fr = foot_ranges(a, b, &d.intervals).expect("ranges");
        assert_eq!(fr.len(), 1);
        assert!(close(fr[0].a[0], 0.0, 1e-12) && close(fr[0].a[1], 1.0, 1e-12));
        assert!(close(fr[0].b[0], 0.0, 1e-12) && close(fr[0].b[1], 1.0, 1e-12));
        let bad = [Interval {
            lo: -1.0,
            hi: 5.0,
            speed: None,
        }];
        assert!(foot_ranges(a, b, &bad).is_none());
        assert!(foot_ranges(
            [[0.0, 0.0], [1.0, 0.0]],
            [[5.0, 5.0], [6.0, 5.0]],
            &d.intervals
        )
        .is_none());
    }

    fn assert_same_dominance(got: &Dominance, want: &Dominance) {
        // Bit-identical verdicts: the prepared path shares the direct
        // path's setup and evaluation order, never a re-derived value.
        assert_eq!(got.status, want.status);
        assert_eq!(got.opp, want.opp);
        assert_eq!(got.speed, want.speed);
        assert_eq!(got.intervals.len(), want.intervals.len());
        for (g, w) in got.intervals.iter().zip(want.intervals.iter()) {
            assert_eq!((g.lo, g.hi, g.speed), (w.lo, w.hi, w.speed));
        }
        assert_eq!(got.spans.len(), want.spans.len());
        for (g, w) in got.spans.iter().zip(want.spans.iter()) {
            assert_eq!(g.f0, w.f0);
            assert_eq!(g.f1, w.f1);
            assert_eq!((g.kept, &g.stage, &g.tag), (w.kept, &w.stage, &w.tag));
        }
    }

    fn assert_same_contact(got: &ContactResult, want: &ContactResult) {
        assert_eq!(
            (&got.status, &got.stage, &got.tag),
            (&want.status, &want.stage, &want.tag)
        );
        match (&got.hit, &want.hit) {
            (None, None) => {}
            (Some(g), Some(w)) => {
                assert_eq!(g.center, w.center);
                assert_eq!(g.qa, w.qa);
                assert_eq!(g.qb, w.qb);
                assert_eq!((g.r, g.width, g.sa, g.sb), (w.r, w.width, w.sa, w.sb));
            }
            _ => panic!("hit mismatch: {got:?} vs {want:?}"),
        }
    }

    struct Case {
        a: Segment,
        b: Segment,
        others: Vec<Border>,
        loops: Option<Vec<Vec<Point>>>,
    }

    /// Corridor-relative probes covering exterior, edges and interior.
    fn probes_for(a: Segment, b: Segment) -> Vec<f64> {
        match corridor(a, b) {
            Some(cor) => [-1.0, 0.0, 0.25, 0.5, 0.75, 1.0, 2.0]
                .iter()
                .map(|f| cor.lo + f * (cor.hi - cor.lo))
                .collect(),
            None => vec![0.5],
        }
    }

    fn check_case(c: &Case) {
        let probes = probes_for(c.a, c.b);
        match prepare(c.a, c.b) {
            Err(e) => {
                let d = dominance(c.a, c.b, &c.others, c.loops.as_deref());
                assert_eq!(d.status, e.status);
                assert_eq!(d.opp, e.opp);
                assert!(d.intervals.is_empty() && d.spans.is_empty());
            }
            Ok(setup) => {
                let direct = dominance(c.a, c.b, &c.others, c.loops.as_deref());
                assert_same_dominance(
                    &dominance_prepared(&setup, &c.others, c.loops.as_deref()),
                    &direct,
                );
                for t in &probes {
                    assert_same_contact(
                        &contact_prepared(&setup, *t, &c.others, c.loops.as_deref()),
                        &contact(c.a, c.b, *t, &c.others, c.loops.as_deref()),
                    );
                }
                // Index-filtered set access matches a caller-side filter
                // over the same slice, in edge order.
                let positions: Vec<Segment> = std::iter::once(c.a)
                    .chain(std::iter::once(c.b))
                    .chain(c.others.iter().map(|o| o.seg))
                    .collect();
                let set = CompetitorSet::new(tagged_borders(&positions));
                let oracle: Vec<Border> = c
                    .others
                    .iter()
                    .enumerate()
                    .map(|(k, o)| Border {
                        seg: o.seg,
                        tag: format!("e({})", k + 2),
                    })
                    .collect();
                // The set path carries prepared `e(k)` tags, so it matches
                // the independently filtered oracle with the same tags,
                // while the borrowed prepared path matches direct tags.
                assert_same_dominance(
                    &set.dominance_for(&setup, 0, 1, c.loops.as_deref()),
                    &dominance(c.a, c.b, &oracle, c.loops.as_deref()),
                );
                for t in &probes {
                    let want = contact(c.a, c.b, *t, &oracle, c.loops.as_deref());
                    assert_same_contact(
                        &set.contact_for(&setup, *t, 0, 1, c.loops.as_deref()),
                        &want,
                    );
                }
            }
        }
    }

    #[test]
    fn prepared_paths_match_direct() {
        let cases = [
            // Clear parallel pair.
            Case {
                a: [[0.0, 0.0], [10.0, 0.0]],
                b: [[0.0, 2.0], [10.0, 2.0]],
                others: vec![],
                loops: None,
            },
            // Crossing third competitor splits the span with its tag.
            Case {
                a: [[0.0, 0.0], [10.0, 0.0]],
                b: [[0.0, 2.0], [10.0, 2.0]],
                others: vec![border([[4.9, -1.0], [5.1, 3.0]], "x")],
                loops: None,
            },
            // Near-tangent competitor abstains as uncertain clearance.
            Case {
                a: [[0.0, 0.0], [10.0, 0.0]],
                b: [[0.0, 2.0], [10.0, 2.0]],
                others: vec![border([[4.0, 2.0], [6.0, 2.0]], "tan")],
                loops: None,
            },
            // Tilted pair with an endpoint-foot piece and a far point.
            Case {
                a: [[1.0, 1.0], [9.0, 3.0]],
                b: [[0.0, 0.0], [10.0, 0.0]],
                others: vec![border([[1000.0, 1000.0], [1000.0, 1000.0]], "far-point")],
                loops: None,
            },
            // Fill loop: contact outside the winding is rejected.
            Case {
                a: [[0.0, 0.0], [10.0, 0.0]],
                b: [[0.0, 2.0], [10.0, 2.0]],
                others: vec![],
                loops: Some(vec![vec![[0.0, 5.0], [10.0, 5.0], [10.0, 6.0], [0.0, 6.0]]]),
            },
            // Degenerate frame: coincident pair has no side.
            Case {
                a: [[0.0, 0.0], [10.0, 0.0]],
                b: [[0.0, 0.0], [10.0, 0.0]],
                others: vec![],
                loops: None,
            },
            // Empty corridor fails closed.
            Case {
                a: [[0.0, 0.0], [1.0, 0.0]],
                b: [[5.0, 5.0], [6.0, 5.0]],
                others: vec![],
                loops: None,
            },
            // Corner branch pruned by opposition.
            Case {
                a: [[0.0, 0.0], [10.0, 0.0]],
                b: [[0.0, 0.0], [0.0, 10.0]],
                others: vec![],
                loops: None,
            },
            // Sub-unit gap sits in the relative noise band.
            Case {
                a: [[0.0, 0.0], [10.0, 0.0]],
                b: [[0.0, 1e-12], [10.0, 1e-12]],
                others: vec![],
                loops: None,
            },
        ];
        for c in &cases {
            check_case(c);
            // Translated and uniformly scaled copies agree the same way.
            let mv = |p: Point| [p[0] * 2.5 + 37.0, p[1] * 2.5 - 13.0];
            check_case(&Case {
                a: [mv(c.a[0]), mv(c.a[1])],
                b: [mv(c.b[0]), mv(c.b[1])],
                others: c
                    .others
                    .iter()
                    .map(|o| border([mv(o.seg[0]), mv(o.seg[1])], &o.tag))
                    .collect(),
                loops: c.loops.clone().map(|lps| {
                    lps.iter()
                        .map(|lp| lp.iter().map(|p| mv(*p)).collect())
                        .collect()
                }),
            });
        }
    }

    #[test]
    fn competitor_exclusion_is_positional() {
        // A geometrically identical third segment is still a competitor:
        // exclusion drops positions, never matching geometry.
        let a = [[0.0, 0.0], [10.0, 0.0]];
        let b = [[0.0, 2.0], [10.0, 2.0]];
        let dup = [[0.0, 0.0], [10.0, 0.0]];
        let positions = [a, b, dup];
        let set = CompetitorSet::new(tagged_borders(&positions));
        let setup = prepare(a, b).expect("clear pair sets up");
        let oracle: Vec<Border> = vec![Border {
            seg: dup,
            tag: "e(2)".to_string(),
        }];
        assert_same_dominance(
            &set.dominance_for(&setup, 0, 1, None),
            &dominance(a, b, &oracle, None),
        );
        // Positions, not geometry: the same segments in another order,
        // with the pair at (1, 2), give the same verdict under the moved
        // tags. Dropping a wrong index would change geometry or tags.
        let reordered = CompetitorSet::new(tagged_borders(&[dup, a, b]));
        let oracle_moved: Vec<Border> = vec![Border {
            seg: dup,
            tag: "e(0)".to_string(),
        }];
        assert_same_dominance(
            &reordered.dominance_for(&setup, 1, 2, None),
            &dominance(a, b, &oracle_moved, None),
        );
        // Tags keep edge order and the prepared format.
        assert_eq!(tagged_borders(&positions)[1].tag, "e(1)");
    }
}
