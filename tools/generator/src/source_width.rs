//! Straight source-relative width fitter.
//!
//! Source: Hobby (4) defines width as twice the medial radius, (5) the signed
//! projected relative width error, (17) couples every related sample with
//! every anchor sample by sqrt(s_i s_j psi_1); section 3.2 builds stroke
//! widths from the segment-site Voronoi diagram (bisectors carry the two
//! contact feet, vertex-dominated branches are pruned); section 3.3 motivates
//! the rectilinear anchor with integral fitted boundaries. Audit notes the
//! d_AB=(A-B)/|A-B| orientation and the printed radian/0.7 weight scales.
//! Project adaptations: medial-interval extraction before recognition with
//! open-foot and disk-clearance clipping, upstream position reference,
//! relative-only coupling, normalized arithmetic guards.
//! Invariant: coordinates are translated and scaled to a unit frame before
//! recognition so fixed guards stay translation and scale independent; the
//! least-squares weights use H/S and 0.7/S, leaving the objective invariant
//! under this internal unit conversion. Physical pixel-size changes still
//! change the published pixel-dependent weights. Anchor and unowned vertices stay exactly upstream,
//! including after 26.6 quantization; shared attachment is exact.
//! Invariant: removal-free correction only; unsupported geometry, rank loss,
//! budget overrun, movement or validity failure all return the upstream
//! outline unchanged with applied=false. Only malformed, non-finite or
//! out-of-range input is an error.
//! Limitation: straight single-contour slice only; curves, multi-contour,
//! self-intersection, vertex-dominated branches and ambiguous ownership
//! abstain.

use crate::{fail, probe::FittedCommand, Error};

/// Guard in normalized units; arithmetic only, never a model gate.
const GUARD: f64 = 1e-9;
/// Degree-detection threshold for linear/constant/quadratic cases.
const DEG: f64 = 1e-12;
const ERRBOUND_A: f64 = (3.0 + 16.0 * f64::EPSILON) * f64::EPSILON;
/// Eligibility cap: straight on-curve vertices on the single contour.
const MAX_VERTS: usize = 64;
/// Work and size caps keeping the slice bounded.
const MAX_WORK: u64 = 4_194_304;
const MAX_ROWS: usize = 8192;
/// Coordinate bound matching the scanner-facing grammar.
const BOUND: f64 = 32768.0;
/// Opposition-angle cosine floor; branches below 157 degrees are pruned.
/// Source: Hobby section 3.2 single-stage primary threshold (Fig 18b); the
/// segment-endpoint Voronoi edges this removes carry opposition zero.
const OPPOSITION_COS: f64 = -0.92050485345244;

/// Fitted outline, corrected or passed through unchanged.
pub struct FitResult {
    pub commands: Vec<FittedCommand>,
    pub applied: bool,
}

struct Ownership {
    related: Vec<usize>,
    owned_related: Vec<bool>,
    free: Vec<usize>,
}

fn partition_ownership(kept: &[PairOut], anchor: usize, len: usize) -> Option<Ownership> {
    let related: Vec<usize> = kept
        .iter()
        .enumerate()
        .filter(|(i, _)| {
            *i != anchor
                && kept[*i]
                    .verts
                    .iter()
                    .any(|v| kept[anchor].verts.contains(v))
        })
        .map(|(i, _)| i)
        .collect();
    if related.is_empty() {
        return None;
    }
    let owned_anchor = kept[anchor].verts.clone();
    let mut owned_related = vec![false; len];
    for r in &related {
        for v in &kept[*r].verts {
            owned_related[*v] = true;
        }
    }
    for v in &owned_anchor {
        owned_related[*v] = false;
    }
    let free: Vec<usize> = (0..len).filter(|v| owned_related[*v]).collect();
    if free.is_empty() {
        return None;
    }
    Some(Ownership {
        related,
        owned_related,
        free,
    })
}

fn limit_movement(
    cand: &mut [[f64; 2]],
    up: &[[f64; 2]],
    free: &[usize],
    bound: f64,
    scale: f64,
) -> bool {
    let mut movement = 0.0_f64;
    for v in free {
        let dx = cand[*v][0] - up[*v][0];
        let dy = cand[*v][1] - up[*v][1];
        movement = movement.max(dx * dx + dy * dy);
    }
    movement = movement.sqrt();
    // Convex quadratic descent along the segment to the free-variable LS
    // minimizer (Boyd/Vandenberghe, chapters 2/9). This feasible prefix is
    // a project adaptation, not the exact constrained optimum. Preserve the
    // source budget and reserve the worst Euclidean nearest-26.6 error.
    let reserve = 2.0_f64.sqrt() / 128.0 / scale;
    let available = bound - reserve;
    if available <= 0.0 {
        return false;
    }
    let fraction = if movement > available {
        available / movement
    } else {
        1.0
    };
    for v in free {
        cand[*v] = [
            up[*v][0] + fraction * (cand[*v][0] - up[*v][0]),
            up[*v][1] + fraction * (cand[*v][1] - up[*v][1]),
        ];
    }
    true
}

/// Couple related straight strokes to the upstream-fitted rectilinear anchor.
///
/// Source carries the unhinted outline, upstream the fitted outline at
/// identical ops; size_px is the nominal pixel height. Returns the upstream
/// outline unchanged with applied=false whenever the slice abstains.
pub fn fit(
    source: &[FittedCommand],
    upstream: &[FittedCommand],
    size_px: f32,
) -> Result<FitResult, Error> {
    if !size_px.is_finite() || !(size_px > 0.0) {
        return Err(fail("source width requires finite positive size"));
    }
    let unchanged = || FitResult {
        commands: upstream.to_vec(),
        applied: false,
    };
    let src = parse(source)?;
    let fit = parse(upstream)?;
    if src.ops != fit.ops {
        return Ok(unchanged());
    }
    if src.loops.len() != 1 || fit.loops.len() != 1 {
        return Ok(unchanged());
    }
    if src.has_curves || fit.has_curves {
        return Ok(unchanged());
    }
    if src.points.len() > MAX_VERTS {
        return Ok(unchanged());
    }
    match proper_crossings(&src.loops, &src.points) {
        Some(0) => {}
        _ => return Ok(unchanged()),
    }
    // Invariant: recognition and solve run in a translated and scaled frame
    // so fixed guards do not depend on input placement or size.
    let frame = match Frame::of(&src.points) {
        Some(frame) => frame,
        None => {
            return Ok(unchanged());
        }
    };
    let height = f64::from(size_px) / frame.scale;
    let base: Vec<[f64; 2]> = src.points.iter().map(|p| frame.forward(p)).collect();
    let up: Vec<[f64; 2]> = fit.points.iter().map(|p| frame.forward(p)).collect();
    let loops = vec![(0..base.len()).collect::<Vec<usize>>()];
    let edges = straight_edges(&base);
    if edges.iter().any(|e| e.len <= 0.0) {
        return Ok(unchanged());
    }
    let mut work = 0u64;
    let pairs = recognize(&base, &edges, &loops, &mut work);
    if pairs.ambiguous {
        return Ok(unchanged());
    }
    // Invariant: rectilinear eligibility and integral fitted boundaries are
    // checked in original pixel space; normalization follows eligibility.
    let edges_pix = straight_edges(&src.points);
    let anchor = match select_anchor(&pairs.kept, &edges_pix, &fit.points) {
        Some(anchor) => anchor,
        None => {
            return Ok(unchanged());
        }
    };
    let Ownership {
        related,
        owned_related,
        free,
    } = match partition_ownership(&pairs.kept, anchor, base.len()) {
        Some(ownership) => ownership,
        None => {
            return Ok(unchanged());
        }
    };
    let shift: Vec<[f64; 2]> = base
        .iter()
        .zip(up.iter())
        .map(|(b, u)| [u[0] - b[0], u[1] - b[1]])
        .collect();
    let mut system = System::new(base.len());
    for edge in &edges {
        system.edge_row(&shift, edge, height);
    }
    let mut anchor_samples = Vec::new();
    for sample in &pairs.kept[anchor].samples {
        anchor_samples.push(system.sample_row(sample));
    }
    let mut related_samples: Vec<Vec<SampleRow>> = Vec::new();
    for r in &related {
        let mut rows = Vec::new();
        for sample in &pairs.kept[*r].samples {
            rows.push(system.sample_row(sample));
        }
        related_samples.push(rows);
    }
    system.shape_rows = system.rows.len();
    let row_count = related_samples
        .iter()
        .map(Vec::len)
        .sum::<usize>()
        .checked_mul(anchor_samples.len())
        .and_then(|n| n.checked_add(system.rows.len()));
    let Some(row_count) = row_count else {
        return Ok(unchanged());
    };
    let qr_work = row_count as u64 * (2 * free.len()) as u64 * (2 * free.len()) as u64;
    if row_count > MAX_ROWS || qr_work.saturating_add(work) > MAX_WORK {
        return Ok(unchanged());
    }
    // Source: (17) couples each i with each j by sqrt(s_i s_j psi_1); index
    // matching between independently divided strokes has no meaning.
    for rows in &related_samples {
        for row in rows {
            for anchor_row in &anchor_samples {
                system.match_row(row, anchor_row, height, 0.7 / frame.scale);
            }
        }
    }
    if system.rows.len() > MAX_ROWS {
        return Ok(unchanged());
    }
    let mut fixed: Vec<(usize, [f64; 2])> = Vec::new();
    for v in 0..base.len() {
        if !owned_related[v] {
            fixed.push((v, shift[v]));
        }
    }
    let solved = match system.solve(&free, &fixed, &mut work) {
        Some(solved) => solved,
        None => {
            return Ok(unchanged());
        }
    };
    let mut cand = base.clone();
    for (v, d) in solved.0.iter().enumerate() {
        cand[v] = [base[v][0] + d[0], base[v][1] + d[1]];
    }
    for v in 0..base.len() {
        if !owned_related[v] {
            cand[v] = up[v];
        }
    }
    let bound = 0.5
        * std::iter::once(anchor)
            .chain(related.iter().copied())
            .flat_map(|idx| pairs.kept[idx].samples.iter().map(|sample| sample.width))
            .fold(f64::INFINITY, f64::min);
    if !(bound > 0.0) {
        return Ok(unchanged());
    }
    // Invariant: movement is candidate relative to upstream, before and
    // after quantization, bounded by half the narrowest coupled width.
    if !limit_movement(&mut cand, &up, &free, bound, frame.scale) {
        return Ok(unchanged());
    }
    if !valid_geometry(&base, &cand, &loops) {
        return Ok(unchanged());
    }
    let rounded: Vec<[f64; 2]> = cand
        .iter()
        .enumerate()
        .map(|(v, p)| {
            if !owned_related[v] {
                fit.points[v]
            } else {
                [
                    round_26_6(frame.back_x(p[0])),
                    round_26_6(frame.back_y(p[1])),
                ]
            }
        })
        .collect();
    let mut movement_q = 0.0_f64;
    for v in &free {
        let target = fit.points[*v];
        let dx = rounded[*v][0] - target[0];
        let dy = rounded[*v][1] - target[1];
        movement_q = movement_q.max(dx * dx + dy * dy);
    }
    movement_q = movement_q.sqrt() / frame.scale;
    if movement_q > bound {
        return Ok(unchanged());
    }
    let cand_q: Vec<[f64; 2]> = rounded.iter().map(|p| frame.forward(p)).collect();
    if !valid_geometry(&base, &cand_q, &loops) {
        return Ok(unchanged());
    }
    let before_width = width_cost(&system, &shift);
    let rounded_delta: Vec<[f64; 2]> = cand_q
        .iter()
        .zip(&base)
        .map(|(c, b)| [c[0] - b[0], c[1] - b[1]])
        .collect();
    let after_width = width_cost(&system, &rounded_delta);
    if !after_width.is_finite() || after_width >= before_width {
        return Ok(unchanged());
    }
    let mut out = source.to_vec();
    let mut k = 0;
    for cmd in out.iter_mut() {
        match cmd {
            FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => {
                if k >= rounded.len() {
                    return Ok(unchanged());
                }
                *x = rounded[k][0] as f32;
                *y = rounded[k][1] as f32;
                k += 1;
            }
            FittedCommand::QuadTo(..) | FittedCommand::CurveTo(..) => {
                return Ok(unchanged());
            }
            FittedCommand::Close => {}
        }
    }
    if k != rounded.len() {
        return Ok(unchanged());
    }
    Ok(FitResult {
        commands: out,
        applied: true,
    })
}

fn round_26_6(x: f64) -> f64 {
    // Source: floor(x*64+.5)/64 scanner convention.
    (x * 64.0 + 0.5).floor() / 64.0
}

struct Parsed {
    ops: Vec<u8>,
    points: Vec<[f64; 2]>,
    loops: Vec<Vec<usize>>,
    has_curves: bool,
}

fn check_point(x: f32, y: f32) -> Result<[f64; 2], Error> {
    if !x.is_finite() || !y.is_finite() {
        return Err(fail("source width outline is non-finite"));
    }
    let v = [f64::from(x), f64::from(y)];
    if v[0].abs() > BOUND || v[1].abs() > BOUND {
        return Err(fail("source width coordinate out of range"));
    }
    Ok(v)
}

fn parse(commands: &[FittedCommand]) -> Result<Parsed, Error> {
    // Source: TrueType glyph outline grammar; identity of op sequences is
    // the correspondence contract between source and fitted outlines.
    let mut ops = Vec::new();
    let mut points = Vec::new();
    let mut loops: Vec<Vec<usize>> = Vec::new();
    let mut current: Option<Vec<usize>> = None;
    let mut has_curves = false;
    for command in commands {
        match *command {
            FittedCommand::MoveTo(x, y) => {
                if current.is_some() {
                    return Err(fail("source width outline has unclosed contour"));
                }
                let p = check_point(x, y)?;
                let mut contour = Vec::new();
                contour.push(points.len());
                points.push(p);
                current = Some(contour);
                ops.push(0);
            }
            FittedCommand::LineTo(x, y) => {
                let contour = current
                    .as_mut()
                    .ok_or_else(|| fail("source width segment has no contour"))?;
                let p = check_point(x, y)?;
                contour.push(points.len());
                points.push(p);
                ops.push(1);
            }
            FittedCommand::QuadTo(x1, y1, x, y) => {
                let contour = current
                    .as_mut()
                    .ok_or_else(|| fail("source width segment has no contour"))?;
                check_point(x1, y1)?;
                let p = check_point(x, y)?;
                contour.push(points.len());
                points.push(p);
                has_curves = true;
                ops.push(2);
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                let contour = current
                    .as_mut()
                    .ok_or_else(|| fail("source width segment has no contour"))?;
                check_point(x1, y1)?;
                check_point(x2, y2)?;
                let p = check_point(x, y)?;
                contour.push(points.len());
                points.push(p);
                has_curves = true;
                ops.push(3);
            }
            FittedCommand::Close => {
                let mut contour = current
                    .take()
                    .ok_or_else(|| fail("source width outline closes no contour"))?;
                if contour.len() > 1 && points[contour[0]] == points[contour[contour.len() - 1]] {
                    contour.pop();
                    points.pop();
                }
                loops.push(contour);
                ops.push(4);
            }
        }
    }
    if current.is_some() {
        return Err(fail("source width outline has unclosed contour"));
    }
    Ok(Parsed {
        ops,
        points,
        loops,
        has_curves,
    })
}

/// Translation- and scale-free working frame of the source outline.
struct Frame {
    min_x: f64,
    min_y: f64,
    scale: f64,
}

impl Frame {
    fn of(points: &[[f64; 2]]) -> Option<Frame> {
        if points.is_empty() {
            return None;
        }
        let mut min_x = f64::INFINITY;
        let mut min_y = f64::INFINITY;
        let mut max_x = f64::NEG_INFINITY;
        let mut max_y = f64::NEG_INFINITY;
        for p in points {
            min_x = min_x.min(p[0]);
            min_y = min_y.min(p[1]);
            max_x = max_x.max(p[0]);
            max_y = max_y.max(p[1]);
        }
        let scale = (max_x - min_x).max(max_y - min_y);
        // Invariant: a sub-pixel-degenerate outline carries no stroke to fit.
        if !(scale > 1e-9) {
            return None;
        }
        Some(Frame {
            min_x,
            min_y,
            scale,
        })
    }

    fn forward(&self, p: &[f64; 2]) -> [f64; 2] {
        [
            (p[0] - self.min_x) / self.scale,
            (p[1] - self.min_y) / self.scale,
        ]
    }

    fn back_x(&self, x: f64) -> f64 {
        x * self.scale + self.min_x
    }

    fn back_y(&self, y: f64) -> f64 {
        y * self.scale + self.min_y
    }
}

/// Error-filtered orientation sign for widened f32 geometry.
///
/// Source: Shewchuk error-filtered predicates
/// (https://www.cs.cmu.edu/~quake/robust.html); the opposite-sign fast path
/// and the static error bound are exact filters, and anything below the bound
/// abstains. Axis-aligned exact zeros and shared points are decided
/// structurally; other computed zeros abstain.
fn orient(ax: f64, ay: f64, bx: f64, by: f64, cx: f64, cy: f64) -> Option<i8> {
    if (ax == bx && ay == by) || (ax == cx && ay == cy) || (bx == cx && by == cy) {
        return Some(0);
    }
    if (ay == by && ay == cy) || (ax == bx && ax == cx) {
        return Some(0);
    }
    let detleft = (ax - cx) * (by - cy);
    let detright = (ay - cy) * (bx - cx);
    let det = detleft - detright;
    if detleft > 0.0 && detright <= 0.0 {
        return Some(1);
    }
    if detleft < 0.0 && detright >= 0.0 {
        return Some(-1);
    }
    if det == 0.0 {
        return None;
    }
    let bound = ERRBOUND_A * (detleft.abs() + detright.abs());
    if det.abs() >= bound {
        return Some(det.signum() as i8);
    }
    None
}

/// Nonzero winding test on straight loops.
fn winding_number(pt: [f64; 2], loops: &[Vec<usize>], pts: &[[f64; 2]]) -> i32 {
    let (x, y) = (pt[0], pt[1]);
    let mut total = 0;
    for contour in loops {
        let n = contour.len();
        for i in 0..n {
            let a = pts[contour[i]];
            let b = pts[contour[(i + 1) % n]];
            if (a[1] <= y) != (b[1] <= y) {
                let xi = a[0] + (y - a[1]) / (b[1] - a[1]) * (b[0] - a[0]);
                if xi > x {
                    total += if b[1] > a[1] { 1 } else { -1 };
                }
            }
        }
    }
    total
}

fn signed_area(loop_idx: &[usize], pts: &[[f64; 2]]) -> f64 {
    let n = loop_idx.len();
    let mut sum = 0.0;
    for i in 0..n {
        let a = pts[loop_idx[i]];
        let b = pts[loop_idx[(i + 1) % n]];
        sum += a[0] * b[1] - b[0] * a[1];
    }
    sum / 2.0
}

fn proper_crossings(loops: &[Vec<usize>], pts: &[[f64; 2]]) -> Option<usize> {
    // Source: segment-intersection counting with shared endpoints excluded.
    // Uncertain orientations abstain rather than miscount.
    let mut segs = Vec::new();
    for contour in loops {
        let n = contour.len();
        for i in 0..n {
            segs.push((pts[contour[i]], pts[contour[(i + 1) % n]]));
        }
    }
    let mut count = 0;
    for i in 0..segs.len() {
        for j in (i + 1)..segs.len() {
            let (p1, p2) = segs[i];
            let (p3, p4) = segs[j];
            if p1 == p3 || p1 == p4 || p2 == p3 || p2 == p4 {
                continue;
            }
            let o1 = orient(p1[0], p1[1], p2[0], p2[1], p3[0], p3[1])?;
            let o2 = orient(p1[0], p1[1], p2[0], p2[1], p4[0], p4[1])?;
            let o3 = orient(p3[0], p3[1], p4[0], p4[1], p1[0], p1[1])?;
            let o4 = orient(p3[0], p3[1], p4[0], p4[1], p2[0], p2[1])?;
            if o1 != 0
                && o2 != 0
                && o3 != 0
                && o4 != 0
                && ((o1 > 0) != (o2 > 0))
                && ((o3 > 0) != (o4 > 0))
            {
                count += 1;
            } else if o1 == 0 || o2 == 0 || o3 == 0 || o4 == 0 {
                // Collinear overlap needs exact contact analysis; the slice
                // treats touching nonadjacent geometry as unsupported.
                return None;
            }
        }
    }
    Some(count)
}

struct Edge {
    va: usize,
    vb: usize,
    a: [f64; 2],
    b: [f64; 2],
    t: [f64; 2],
    n: [f64; 2],
    len: f64,
    #[allow(dead_code)]
    c: f64,
}

fn straight_edges(pts: &[[f64; 2]]) -> Vec<Edge> {
    let n = pts.len();
    let mut edges = Vec::with_capacity(n);
    for i in 0..n {
        let a = pts[i];
        let b = pts[(i + 1) % n];
        let dx = b[0] - a[0];
        let dy = b[1] - a[1];
        let len = dx.hypot(dy);
        let (t, nrm) = if len > 0.0 {
            ([dx / len, dy / len], [-dy / len, dx / len])
        } else {
            ([0.0, 0.0], [0.0, 0.0])
        };
        edges.push(Edge {
            va: i,
            vb: (i + 1) % n,
            a,
            b,
            t: t,
            n: nrm,
            len,
            c: nrm[0] * a[0] + nrm[1] * a[1],
        });
    }
    edges
}

/// A sampled medial contact with affine foot correspondences.
struct SamplePt {
    fa: [(usize, f64); 2],
    fb: [(usize, f64); 2],
    normal: [f64; 2],
    tangent: [f64; 2],
    width: f64,
    arc: f64,
}

struct PairOut {
    verts: [usize; 4],
    samples: Vec<SamplePt>,
}

struct Recognition {
    kept: Vec<PairOut>,
    ambiguous: bool,
}

fn dot(a: [f64; 2], b: [f64; 2]) -> f64 {
    a[0] * b[0] + a[1] * b[1]
}

/// Solve a t + b = 0 with explicit linear/constant cases; uncertain
/// constant-zero (identically satisfied) yields no event since no crossing
/// can occur. Returns roots to keep.
fn linear_roots(a: f64, b: f64) -> Vec<f64> {
    let scale = a.abs().max(b.abs());
    if scale == 0.0 {
        return Vec::new();
    }
    if a.abs() <= DEG * scale {
        return Vec::new();
    }
    vec![-b / a]
}

/// Quadratic roots with explicit degree fallback; a genuinely uncertain
/// degree (vanishing leading terms against a live constant) abstains the
/// pair via None. Tangent discriminants yield the single touch point.
fn quad_roots(a: f64, b: f64, c: f64) -> Option<Vec<f64>> {
    let scale = a.abs().max(b.abs()).max(c.abs());
    if scale == 0.0 {
        return Some(Vec::new());
    }
    if a.abs() <= DEG * scale {
        return Some(linear_roots(b, c));
    }
    let disc = b * b - 4.0 * a * c;
    if disc == 0.0 {
        return Some(vec![-b / (2.0 * a)]);
    }
    if disc.abs() <= DEG * (b * b + (4.0 * a * c).abs()) {
        return None;
    }
    if disc < 0.0 {
        return Some(Vec::new());
    }
    let q = -0.5 * (b + disc.sqrt().copysign(b));
    let mut roots = vec![q / a, c / q];
    roots.sort_by(|x, y| x.total_cmp(y));
    Some(roots)
}

fn point_seg_dist2(c: [f64; 2], p: [f64; 2], q: [f64; 2]) -> (f64, f64) {
    // Returns (squared distance, foot parameter clamped to [0,1]).
    let dx = q[0] - p[0];
    let dy = q[1] - p[1];
    let denom = dx * dx + dy * dy;
    if denom <= 0.0 {
        let ddx = c[0] - p[0];
        let ddy = c[1] - p[1];
        return (ddx * ddx + ddy * ddy, 0.0);
    }
    let mut s = ((c[0] - p[0]) * dx + (c[1] - p[1]) * dy) / denom;
    s = s.clamp(0.0, 1.0);
    let fx = p[0] + s * dx - c[0];
    let fy = p[1] + s * dy - c[1];
    (fx * fx + fy * fy, s)
}

struct RawPair {
    q: [f64; 2],
    u: [f64; 2],
    r0: f64,
    g: f64,
    s1: f64,
    s2: f64,
    intervals: Vec<(f64, f64)>,
}

/// Medial intervals of one straight border pair, Hobby section 3.2.
///
/// The bisector carries affine center and radius; feet stay in open segment
/// interiors (vertex-dominated branches unsupported), radius stays positive
/// and every sampled disk clears all borders including adjacent caps.
/// Equality events are linear for line pieces and quadratic for vertex
/// pieces; sub-interval midpoints decide retention.
#[allow(clippy::too_many_arguments)]
fn pair_intervals(
    e1: &Edge,
    e2: &Edge,
    edges: &[Edge],
    loops: &[Vec<usize>],
    pts: &[[f64; 2]],
    work: &mut u64,
) -> Option<RawPair> {
    let bump = |work: &mut u64| {
        *work = work.saturating_add(1);
        *work <= MAX_WORK
    };
    // Shared corridor direction and overlap window.
    let mut t2 = e2.t;
    if dot(e1.t, t2) < 0.0 {
        t2 = [-t2[0], -t2[1]];
    }
    let mut dx = e1.t[0] + t2[0];
    let mut dy = e1.t[1] + t2[1];
    let norm = dx.hypot(dy);
    if !(norm > 0.0) {
        return None;
    }
    dx /= norm;
    dy /= norm;
    let project = |p: [f64; 2]| dx * p[0] + dy * p[1];
    let lo = project(e1.a)
        .min(project(e1.b))
        .max(project(e2.a).min(project(e2.b)));
    let hi = project(e1.a)
        .max(project(e1.b))
        .min(project(e2.a).max(project(e2.b)));
    if !(hi > lo) {
        return None;
    }
    let m1 = [(e1.a[0] + e1.b[0]) / 2.0, (e1.a[1] + e1.b[1]) / 2.0];
    let m2 = [(e2.a[0] + e2.b[0]) / 2.0, (e2.a[1] + e2.b[1]) / 2.0];
    let s1 = (e1.n[0] * m2[0] + e1.n[1] * m2[1] - e1.c).signum();
    let s2 = (e2.n[0] * m1[0] + e2.n[1] * m1[1] - e2.c).signum();
    if s1 == 0.0 || s2 == 0.0 {
        return None;
    }
    // Bisector line C(t) = Q + t u with affine radius r(t) = r0 + g t.
    let det = e1.n[0] * e2.n[1] - e1.n[1] * e2.n[0];
    let (q, u, r0, g) = if det.abs() > DEG {
        let qx = (e1.c * e2.n[1] - e2.c * e1.n[1]) / det;
        let qy = (e1.n[0] * e2.c - e2.n[0] * e1.c) / det;
        let vx = s1 * e1.n[0] - s2 * e2.n[0];
        let vy = s1 * e1.n[1] - s2 * e2.n[1];
        let vn = vx.hypot(vy);
        if !(vn > 0.0) {
            return None;
        }
        let ux = -vy / vn;
        let uy = vx / vn;
        let g = s1 * (e1.n[0] * ux + e1.n[1] * uy);
        ([qx, qy], [ux, uy], 0.0, g)
    } else {
        // Parallel borders share a midline; radius is half the separation.
        let mut ux = -e1.n[1];
        let mut uy = e1.n[0];
        let un = ux.hypot(uy);
        if !(un > 0.0) {
            return None;
        }
        ux /= un;
        uy /= un;
        let mx = (m1[0] + m2[0]) / 2.0;
        let my = (m1[1] + m2[1]) / 2.0;
        let r0 = s1 * (e1.n[0] * (mx - e1.a[0]) + e1.n[1] * (my - e1.a[1]));
        if !(r0 > 0.0) {
            return None;
        }
        ([mx, my], [ux, uy], r0, 0.0)
    };
    // Feet as affine functions of t; open interiors only.
    let foot = |e: &Edge, s: f64, n: [f64; 2]| {
        let fx = q[0] - s * r0 * n[0];
        let fy = q[1] - s * r0 * n[1];
        let vx = u[0] - s * g * n[0];
        let vy = u[1] - s * g * n[1];
        let ex = e.b[0] - e.a[0];
        let ey = e.b[1] - e.a[1];
        let l2 = ex * ex + ey * ey;
        let alpha = (vx * ex + vy * ey) / l2;
        let beta = ((fx - e.a[0]) * ex + (fy - e.a[1]) * ey) / l2;
        (alpha, beta)
    };
    let (a1, b1) = foot(e1, s1, e1.n);
    let (a2, b2) = foot(e2, s2, e2.n);
    let mut t_lo = f64::NEG_INFINITY;
    let mut t_hi = f64::INFINITY;
    for (alpha, beta) in [(a1, b1), (a2, b2)] {
        let scale = alpha.abs().max(beta.abs()).max((beta - 1.0).abs());
        if alpha.abs() <= DEG * scale.max(1e-300) {
            if !(beta > GUARD && beta < 1.0 - GUARD) {
                return None;
            }
            continue;
        }
        let r0t = -beta / alpha;
        let r1t = (1.0 - beta) / alpha;
        let (lo_t, hi_t) = if alpha > 0.0 { (r0t, r1t) } else { (r1t, r0t) };
        t_lo = t_lo.max(lo_t);
        t_hi = t_hi.min(hi_t);
        if !(t_hi > t_lo) {
            return None;
        }
    }
    // Positive radius with normalized margin.
    if g.abs() <= DEG * g.abs().max(r0.abs()).max(1e-300) {
        if !(r0 > GUARD) {
            return None;
        }
    } else {
        let tr = (GUARD - r0) / g;
        if g > 0.0 {
            t_lo = t_lo.max(tr);
        } else {
            t_hi = t_hi.min(tr);
        }
        if !(t_hi > t_lo) {
            return None;
        }
    }
    // Bounding box of the outline keeps the window finite; the fill test on
    // samples decides containment.
    let (mut bx0, mut by0, mut bx1, mut by1) = (
        f64::INFINITY,
        f64::INFINITY,
        f64::NEG_INFINITY,
        f64::NEG_INFINITY,
    );
    for p in pts.iter() {
        bx0 = bx0.min(p[0]);
        by0 = by0.min(p[1]);
        bx1 = bx1.max(p[0]);
        by1 = by1.max(p[1]);
    }
    for (o, d, lo_b, hi_b) in [(q[0], u[0], bx0, bx1), (q[1], u[1], by0, by1)] {
        if d.abs()
            <= DEG
                * d.abs()
                    .max((o - lo_b).abs())
                    .max((o - hi_b).abs())
                    .max(1e-300)
        {
            if o < lo_b || o > hi_b {
                return None;
            }
            continue;
        }
        let ta = (lo_b - o) / d;
        let tb = (hi_b - o) / d;
        let (lo_t, hi_t) = if d > 0.0 { (ta, tb) } else { (tb, ta) };
        t_lo = t_lo.max(lo_t);
        t_hi = t_hi.min(hi_t);
        if !(t_hi > t_lo) {
            return None;
        }
    }
    if !t_lo.is_finite() || !t_hi.is_finite() {
        return None;
    }
    // Equality events against every other border; vertex pieces contribute
    // quadratic events, line pieces linear ones. Spurious roots only add
    // sub-intervals; every true crossing is present.
    let mut events = vec![t_lo, t_hi];
    for e in edges {
        if !bump(work) {
            return None;
        }
        // Paired borders carry the feet; clearance applies to the rest.
        let paired = (e.va == e1.va && e.vb == e1.vb) || (e.va == e2.va && e.vb == e2.vb);
        if paired {
            continue;
        }
        let ex = e.b[0] - e.a[0];
        let ey = e.b[1] - e.a[1];
        let l2 = ex * ex + ey * ey;
        if !(l2 > 0.0) {
            continue;
        }
        // Foot parameter affine in t; endpoints split point/line pieces.
        let ca = (q[0] - e.a[0]) * ex + (q[1] - e.a[1]) * ey;
        let cb = (u[0] * ex + u[1] * ey) / l2;
        let c0 = ca / l2;
        let alpha_s = cb;
        for edge_t in [0.0, 1.0] {
            for root in linear_roots(alpha_s, c0 - edge_t) {
                if root > t_lo && root < t_hi {
                    events.push(root);
                }
            }
        }
        // Line-piece equality |n.C(t)-c| = r(t), both signs.
        let anx = e.n[0];
        let any = e.n[1];
        let a_lin = anx * u[0] + any * u[1];
        let b_lin = anx * q[0] + any * q[1] - e.c;
        for root in linear_roots(a_lin - g, b_lin - r0)
            .into_iter()
            .chain(linear_roots(a_lin + g, b_lin + r0))
        {
            if root > t_lo && root < t_hi {
                events.push(root);
            }
        }
        // Vertex-piece equality |C(t)-V|^2 = r(t)^2, quadratic.
        for v in [e.a, e.b] {
            // A paired endpoint's point-distance equation is the square of
            // its along-edge foot distance (Pythagoras). Its only equality
            // is already a finite-foot boundary, so do not re-solve a
            // cancellation-prone quadratic for that known double root.
            if [e1.a, e1.b, e2.a, e2.b].contains(&v) {
                continue;
            }
            let qx = q[0] - v[0];
            let qy = q[1] - v[1];
            let qa = u[0] * u[0] + u[1] * u[1] - g * g;
            let qb = 2.0 * (qx * u[0] + qy * u[1] - r0 * g);
            let qc = qx * qx + qy * qy - r0 * r0;
            match quad_roots(qa, qb, qc) {
                Some(roots) => {
                    for root in roots {
                        if root > t_lo && root < t_hi {
                            events.push(root);
                        }
                    }
                }
                None => {
                    return None;
                }
            }
        }
    }
    events.sort_by(|a, b| a.total_cmp(b));
    events.dedup();
    let margin = GUARD * r0.abs().max(1.0);
    let mut kept: Vec<(f64, f64)> = Vec::new();
    for pair in events.windows(2) {
        let (ta, tb) = (pair[0], pair[1]);
        if !(tb > ta) {
            continue;
        }
        let tm = (ta + tb) / 2.0;
        *work = work.saturating_add(4 * (edges.len() as u64 + 1));
        if *work > MAX_WORK {
            return None;
        }
        if valid_station(e1, e2, s1, s2, q, u, r0, g, tm, edges, loops, pts, margin) {
            // Out-of-regime distance roots and competitor projection events
            // need not end this pair's medial branch. Merge only across a
            // boundary that itself has unique, clear interior contacts.
            if let Some(last) = kept.last_mut() {
                if last.1 == ta
                    && valid_station(e1, e2, s1, s2, q, u, r0, g, ta, edges, loops, pts, margin)
                {
                    last.1 = tb;
                    continue;
                }
            }
            kept.push((ta, tb));
        }
    }
    if kept.is_empty() {
        return None;
    }
    Some(RawPair {
        q,
        u,
        r0,
        g,
        s1,
        s2,
        intervals: kept,
    })
}

/// Full station predicate: open feet, positive radius, disk clearance of
/// every other border, center inside nonzero fill.
#[allow(clippy::too_many_arguments)]
fn valid_station(
    e1: &Edge,
    e2: &Edge,
    s1: f64,
    s2: f64,
    q: [f64; 2],
    u: [f64; 2],
    r0: f64,
    g: f64,
    t: f64,
    edges: &[Edge],
    loops: &[Vec<usize>],
    pts: &[[f64; 2]],
    margin: f64,
) -> bool {
    let r = r0 + g * t;
    if !(r > margin) {
        return false;
    }
    let center = [q[0] + t * u[0], q[1] + t * u[1]];
    for (e, s) in [(e1, s1), (e2, s2)] {
        let fx = center[0] - s * r * e.n[0];
        let fy = center[1] - s * r * e.n[1];
        let ex = e.b[0] - e.a[0];
        let ey = e.b[1] - e.a[1];
        let l2 = ex * ex + ey * ey;
        if !(l2 > 0.0) {
            return false;
        }
        let sa = ((fx - e.a[0]) * ex + (fy - e.a[1]) * ey) / l2;
        if !(sa > GUARD && sa < 1.0 - GUARD) {
            return false;
        }
    }
    for e in edges {
        let paired = (e.va == e1.va && e.vb == e1.vb) || (e.va == e2.va && e.vb == e2.vb);
        if paired {
            continue;
        }
        let (d2, _) = point_seg_dist2(center, e.a, e.b);
        if d2 <= (r + margin) * (r + margin) {
            return false;
        }
    }
    winding_number(center, loops, pts) != 0
}

fn contact_at(
    e1: &Edge,
    e2: &Edge,
    s1: f64,
    s2: f64,
    q: [f64; 2],
    u: [f64; 2],
    r0: f64,
    g: f64,
    t: f64,
    arc: f64,
) -> Option<SamplePt> {
    // Source: Hobby (4) takes width as twice the medial radius, not the
    // foot chord; the chord midpoint substitution is wrong for taper.
    let r = r0 + g * t;
    if !(r > 0.0) {
        return None;
    }
    let center = [q[0] + t * u[0], q[1] + t * u[1]];
    let mut feet = [[0.0, 0.0]; 2];
    let mut sas = [0.0; 2];
    for (k, (e, s)) in [(e1, s1), (e2, s2)].into_iter().enumerate() {
        let fx = center[0] - s * r * e.n[0];
        let fy = center[1] - s * r * e.n[1];
        let ex = e.b[0] - e.a[0];
        let ey = e.b[1] - e.a[1];
        let l2 = ex * ex + ey * ey;
        if !(l2 > 0.0) {
            return None;
        }
        let sa = ((fx - e.a[0]) * ex + (fy - e.a[1]) * ey) / l2;
        if !(sa > GUARD && sa < 1.0 - GUARD) {
            return None;
        }
        feet[k] = [fx, fy];
        sas[k] = sa;
        // Invariant: each foot sits on the disk by construction; mismatch
        // beyond arithmetic noise drops the interval.
        let rr = ((fx - center[0]).hypot(fy - center[1]) - r).abs() / r;
        if !(rr <= 1e-9) {
            return None;
        }
    }
    let nx = feet[0][0] - feet[1][0];
    let ny = feet[0][1] - feet[1][1];
    let nl = nx.hypot(ny);
    if !(nl > 0.0) {
        return None;
    }
    let normal = [nx / nl, ny / nl];
    let tangent = [-normal[1], normal[0]];
    Some(SamplePt {
        fa: [(e1.va, 1.0 - sas[0]), (e1.vb, sas[0])],
        fb: [(e2.va, 1.0 - sas[1]), (e2.vb, sas[1])],
        normal,
        tangent,
        width: 2.0 * r,
        arc,
    })
}

fn recognize(
    pts: &[[f64; 2]],
    edges: &[Edge],
    loops: &[Vec<usize>],
    work: &mut u64,
) -> Recognition {
    struct Scored {
        samples: Vec<SamplePt>,
        verts: [usize; 4],
        borders: [usize; 2],
    }
    let mut scored: Vec<Scored> = Vec::new();
    let n = edges.len();
    for i in 0..n {
        for j in (i + 1)..n {
            let (e1, e2) = (&edges[i], &edges[j]);
            if e1.va == e2.va || e1.va == e2.vb || e1.vb == e2.va || e1.vb == e2.vb {
                continue;
            }
            // Hobby section 3.2 Figure 18b: prune corner branches uniformly.
            let side1 = dot(
                e1.n,
                [
                    (e2.a[0] + e2.b[0]) / 2.0 - e1.a[0],
                    (e2.a[1] + e2.b[1]) / 2.0 - e1.a[1],
                ],
            );
            let side2 = dot(
                e2.n,
                [
                    (e1.a[0] + e1.b[0]) / 2.0 - e2.a[0],
                    (e1.a[1] + e1.b[1]) / 2.0 - e2.a[1],
                ],
            );
            if side1 == 0.0
                || side2 == 0.0
                || side1.signum() * side2.signum() * dot(e1.n, e2.n) > OPPOSITION_COS
            {
                continue;
            }
            let raw = match pair_intervals(e1, e2, edges, loops, pts, work) {
                Some(v) => v,
                None => continue,
            };
            // Three equal-midpoint samples per actual valid interval; a
            // failing recheck drops the interval.
            let mut samples = Vec::new();
            for (ta, tb) in &raw.intervals {
                let arc = (tb - ta) / 3.0;
                let mut kept = Vec::new();
                for k in 0..3 {
                    let t = ta + (k as f64 + 0.5) * (tb - ta) / 3.0;
                    *work = work.saturating_add(edges.len() as u64);
                    if *work > MAX_WORK {
                        return Recognition {
                            kept: Vec::new(),
                            ambiguous: true,
                        };
                    }
                    if !valid_station(
                        e1, e2, raw.s1, raw.s2, raw.q, raw.u, raw.r0, raw.g, t, edges, loops, pts,
                        GUARD,
                    ) {
                        break;
                    }
                    match contact_at(e1, e2, raw.s1, raw.s2, raw.q, raw.u, raw.r0, raw.g, t, arc) {
                        Some(sample) => kept.push(sample),
                        None => break,
                    }
                }
                if kept.len() == 3 {
                    samples.extend(kept);
                }
            }
            if samples.is_empty() {
                continue;
            }
            scored.push(Scored {
                samples,
                verts: [e1.va, e1.vb, e2.va, e2.vb],
                borders: [i, j],
            });
        }
    }
    if *work > MAX_WORK {
        return Recognition {
            kept: Vec::new(),
            ambiguous: true,
        };
    }
    // Multiple surviving partners require interval ownership across branches.
    let mut claims = vec![0usize; n];
    for pair in &scored {
        for border in pair.borders {
            claims[border] += 1;
        }
    }
    if claims.iter().any(|count| *count > 1) {
        return Recognition {
            kept: Vec::new(),
            ambiguous: true,
        };
    }
    let mut kept = Vec::new();
    for idx in 0..scored.len() {
        let samples = std::mem::take(&mut scored[idx].samples);
        kept.push(PairOut {
            verts: scored[idx].verts,
            samples,
        });
    }
    Recognition {
        kept,
        ambiguous: false,
    }
}

/// Rectilinear anchor with integral fitted boundaries, unique.
fn select_anchor(pairs: &[PairOut], edges: &[Edge], fit_pts: &[[f64; 2]]) -> Option<usize> {
    let mut found = None;
    for (idx, pair) in pairs.iter().enumerate() {
        let e1 = edges.get(pair_edge_index(edges, pair, 0)?)?;
        let e2 = edges.get(pair_edge_index(edges, pair, 1)?)?;
        let vertical = e1.a[0] == e1.b[0] && e2.a[0] == e2.b[0];
        let horizontal = e1.a[1] == e1.b[1] && e2.a[1] == e2.b[1];
        if vertical == horizontal {
            continue;
        }
        let axis = if vertical { 0 } else { 1 };
        let mut integral = true;
        for v in pair.verts {
            if fit_pts[v][axis].fract() != 0.0 {
                integral = false;
                break;
            }
        }
        if !integral {
            continue;
        }
        if found.is_some() {
            return None;
        }
        found = Some(idx);
    }
    found
}

/// Edge index of a pair vertex edge; pairs store vertices in edge order.
fn pair_edge_index(edges: &[Edge], pair: &PairOut, which: usize) -> Option<usize> {
    let (va, vb) = if which == 0 {
        (pair.verts[0], pair.verts[1])
    } else {
        (pair.verts[2], pair.verts[3])
    };
    edges.iter().position(|e| e.va == va && e.vb == vb)
}

struct SampleRow {
    row: Vec<(usize, f64)>,
    width: f64,
    tangent: [f64; 2],
    arc: f64,
}

struct System {
    n: usize,
    shape_rows: usize,
    rows: Vec<(Vec<(usize, f64)>, f64)>,
}

impl System {
    fn new(n: usize) -> System {
        System {
            n,
            shape_rows: 0,
            rows: Vec::new(),
        }
    }

    fn sample_row(&self, sample: &SamplePt) -> SampleRow {
        // Source: (5) error row is the projected correspondence difference
        // over the medial width; Hobby (4) fixes the denominator at 2r.
        let mut row = Vec::with_capacity(8);
        for (v, w) in sample.fa {
            row.push((2 * v, -w * sample.normal[0] / sample.width));
            row.push((2 * v + 1, -w * sample.normal[1] / sample.width));
        }
        for (v, w) in sample.fb {
            row.push((2 * v, w * sample.normal[0] / sample.width));
            row.push((2 * v + 1, w * sample.normal[1] / sample.width));
        }
        SampleRow {
            row,
            width: sample.width,
            tangent: sample.tangent,
            arc: sample.arc,
        }
    }

    fn edge_row(&mut self, shift: &[[f64; 2]], edge: &Edge, height: f64) {
        // Source: edge residuals (1)-(3) with the upstream position target.
        let alpha1 = 1000.0 / (height * height * height);
        let t = edge.t;
        let nrm = edge.n;
        let a = edge.va;
        let b = edge.vb;
        let scale_pos = (alpha1 * edge.len / 4.0).sqrt();
        let mut mean = Vec::with_capacity(4);
        mean.push((2 * a, nrm[0] * scale_pos));
        mean.push((2 * a + 1, nrm[1] * scale_pos));
        mean.push((2 * b, nrm[0] * scale_pos));
        mean.push((2 * b + 1, nrm[1] * scale_pos));
        let scale_d = (alpha1 * edge.len / 12.0).sqrt();
        let mut diff = Vec::with_capacity(4);
        diff.push((2 * a, -nrm[0] * scale_d));
        diff.push((2 * a + 1, -nrm[1] * scale_d));
        diff.push((2 * b, nrm[0] * scale_d));
        diff.push((2 * b + 1, nrm[1] * scale_d));
        let scale_s = (25.0 * edge.len / height).sqrt() / edge.len;
        let mut stretch = Vec::with_capacity(4);
        stretch.push((2 * a, -t[0] * scale_s));
        stretch.push((2 * a + 1, -t[1] * scale_s));
        stretch.push((2 * b, t[0] * scale_s));
        stretch.push((2 * b + 1, t[1] * scale_s));
        let mut bend = Vec::with_capacity(4);
        bend.push((2 * a, -nrm[0] * scale_s));
        bend.push((2 * a + 1, -nrm[1] * scale_s));
        bend.push((2 * b, nrm[0] * scale_s));
        bend.push((2 * b + 1, nrm[1] * scale_s));
        for r in [mean, diff, stretch, bend] {
            let constant = -r.iter().map(|(k, v)| v * shift[k / 2][k % 2]).sum::<f64>();
            self.rows.push((r, constant));
        }
    }

    fn match_row(&mut self, row: &SampleRow, other: &SampleRow, height: f64, width_scale: f64) {
        // Source: (17) couples each i with each j by sqrt(s_i s_j psi_1).
        let psi = width_weight(
            row.width,
            other.width,
            row.tangent,
            other.tangent,
            height,
            width_scale,
        );
        let factor = (row.arc * other.arc * psi).sqrt();
        let mut combined: Vec<(usize, f64)> = Vec::with_capacity(row.row.len() + other.row.len());
        for (k, v) in &row.row {
            combined.push((*k, v * factor));
        }
        for (k, v) in &other.row {
            combined.push((*k, -v * factor));
        }
        self.rows.push((combined, 0.0));
    }

    fn solve(
        &self,
        free: &[usize],
        fixed: &[(usize, [f64; 2])],
        work: &mut u64,
    ) -> Option<(Vec<[f64; 2]>, usize)> {
        // Invariant: fixed vertices fold into the constants; the free block
        // needs full column rank under the machine-eps scaled tolerance.
        let n_all = self.n;
        let mut is_free = vec![false; n_all];
        for v in free {
            is_free[*v] = true;
        }
        let mut fixed_val = vec![[0.0; 2]; n_all];
        for (v, d) in fixed {
            fixed_val[*v] = *d;
        }
        let nf = 2 * free.len();
        let mut dense: Vec<Vec<f64>> = Vec::with_capacity(self.rows.len());
        let mut rhs: Vec<f64> = Vec::with_capacity(self.rows.len());
        for (entries, constant) in &self.rows {
            let mut row = vec![0.0; nf];
            let mut c = *constant;
            for (k, v) in entries {
                let vert = k / 2;
                let comp = k % 2;
                if is_free[vert] {
                    let fi = free.iter().position(|x| *x == vert)?;
                    row[2 * fi + comp] += v;
                } else {
                    c += v * fixed_val[vert][comp];
                }
            }
            *work = work.saturating_add(nf as u64 + 1);
            if *work > MAX_WORK {
                return None;
            }
            dense.push(row);
            rhs.push(-c);
        }
        if nf == 0 {
            return Some((vec![[0.0; 2]; n_all], 0));
        }
        if dense.iter().any(|row| row.iter().any(|v| !v.is_finite()))
            || rhs.iter().any(|v| !v.is_finite())
        {
            return None;
        }
        let delta_free = householder_solve(&mut dense, &mut rhs)?;
        let mut delta = vec![[0.0; 2]; n_all];
        for (i, v) in free.iter().enumerate() {
            delta[*v] = [delta_free[2 * i], delta_free[2 * i + 1]];
        }
        for (v, d) in fixed {
            delta[*v] = *d;
        }
        Some((delta, dense.len() * nf))
    }
}

/// Relative width penalty psi_1 with the audit's radian and 0.7 scales.
fn width_weight(
    w1: f64,
    w2: f64,
    d1: [f64; 2],
    d2: [f64; 2],
    height: f64,
    width_scale: f64,
) -> f64 {
    // Source: psi_1 = 500/H^2 exp(-((w1-w2)/.7)^2 - (dtheta/9)^2), audit
    // notes radians and the 0.7/9 scales.
    if !(height > 0.0) || !w1.is_finite() || !w2.is_finite() {
        return 0.0;
    }
    let cos = (d1[0] * d2[0] + d1[1] * d2[1]).clamp(-1.0, 1.0);
    let theta = cos.acos();
    let dw = (w1 - w2) / width_scale;
    500.0 / (height * height) * (-(dw * dw) - (theta / 9.0).powi(2)).exp()
}

/// Full-rank least squares via Householder QR with column pivoting.
///
/// Source: column-pivoted Householder QR (LAPACK Working Note 114,
/// https://www.netlib.org/lapack/lawnspdf/lawn114.pdf); rank rejects at
/// machine-eps * max(M, N) * matrix-scale with no regularizer.
fn householder_solve(a: &mut [Vec<f64>], b: &mut [f64]) -> Option<Vec<f64>> {
    let m = a.len();
    if m == 0 {
        return None;
    }
    let n = a[0].len();
    if n == 0 || m < n {
        return None;
    }
    let mut perm: Vec<usize> = (0..n).collect();
    let mut colnorm = vec![0.0; n];
    for j in 0..n {
        colnorm[j] = a.iter().map(|row| row[j] * row[j]).sum::<f64>().sqrt();
    }
    let maxnorm = colnorm.iter().cloned().fold(0.0, f64::max);
    if !(maxnorm > 0.0) {
        return None;
    }
    let tol = f64::EPSILON * (m.max(n) as f64) * maxnorm;
    let mut rank = 0;
    for k in 0..n.min(m) {
        let mut pivot = k;
        for j in (k + 1)..n {
            if colnorm[j] > colnorm[pivot] {
                pivot = j;
            }
        }
        if colnorm[pivot] <= 0.0 {
            break;
        }
        if pivot != k {
            perm.swap(k, pivot);
            colnorm.swap(k, pivot);
            for row in a.iter_mut() {
                row.swap(k, pivot);
            }
        }
        let mut norm = 0.0;
        for row in a.iter().skip(k) {
            norm += row[k] * row[k];
        }
        norm = norm.sqrt();
        if !(norm > 0.0) {
            break;
        }
        let alpha = if a[k][k] >= 0.0 { -norm } else { norm };
        let mut v: Vec<f64> = a.iter().skip(k).map(|row| row[k]).collect();
        v[0] -= alpha;
        let mut vnorm = v.iter().map(|x| x * x).sum::<f64>().sqrt();
        if !(vnorm > 0.0) {
            break;
        }
        for x in v.iter_mut() {
            *x /= vnorm;
        }
        vnorm = 1.0;
        let _ = vnorm;
        // Apply I - 2 v v^T to the trailing submatrix and rhs.
        for j in k..n {
            let mut dot = 0.0;
            for (i, row) in a.iter().enumerate().skip(k) {
                dot += v[i - k] * row[j];
            }
            dot *= 2.0;
            for (i, row) in a.iter_mut().enumerate().skip(k) {
                row[j] -= dot * v[i - k];
            }
        }
        let mut dot = 0.0;
        for (i, val) in b.iter().enumerate().skip(k) {
            dot += v[i - k] * val;
        }
        dot *= 2.0;
        for (i, val) in b.iter_mut().enumerate().skip(k) {
            *val -= dot * v[i - k];
        }
        rank += 1;
        for j in (k + 1)..n {
            colnorm[j] = a
                .iter()
                .skip(k + 1)
                .map(|row| row[j] * row[j])
                .sum::<f64>()
                .sqrt();
        }
    }
    if rank < n {
        return None;
    }
    // Rank tolerance: every kept diagonal must clear the scaled bound.
    for k in 0..n {
        if a[k][k].abs() <= tol {
            return None;
        }
    }
    let mut y = vec![0.0; n];
    for k in (0..n).rev() {
        let mut sum = b[k];
        for j in (k + 1)..n {
            sum -= a[k][j] * y[j];
        }
        if a[k][k] == 0.0 {
            return None;
        }
        y[k] = sum / a[k][k];
    }
    let mut x = vec![0.0; n];
    for (k, p) in perm.iter().enumerate() {
        x[*p] = y[k];
    }
    Some(x)
}

/// Whole-outline validity: loop signs, crossing counts, nesting and edge
/// directions must match the source.
fn valid_geometry(base: &[[f64; 2]], cand: &[[f64; 2]], loops: &[Vec<usize>]) -> bool {
    for contour in loops {
        let a = signed_area(contour, base);
        let b = signed_area(contour, cand);
        if !(a > 0.0) != !(b > 0.0) || a == 0.0 || b == 0.0 {
            return false;
        }
    }
    let src_cross = proper_crossings(loops, base);
    let cand_cross = proper_crossings(loops, cand);
    match (src_cross, cand_cross) {
        (Some(s), Some(c)) if s == c => {}
        _ => return false,
    }
    for (i, loop_i) in loops.iter().enumerate() {
        for (j, loop_j) in loops.iter().enumerate() {
            if i == j {
                continue;
            }
            let before =
                winding_number(base[loop_i[0]], std::slice::from_ref(&loops[j]), base) != 0;
            let after = winding_number(cand[loop_i[0]], std::slice::from_ref(&loops[j]), cand) != 0;
            if before != after {
                return false;
            }
            let _ = loop_j;
        }
    }
    // Invariant: no edge may reverse direction; reversal is damage.
    for contour in loops {
        let n = contour.len();
        for i in 0..n {
            let a0 = base[contour[i]];
            let b0 = base[contour[(i + 1) % n]];
            let a1 = cand[contour[i]];
            let b1 = cand[contour[(i + 1) % n]];
            let dot = (b0[0] - a0[0]) * (b1[0] - a1[0]) + (b0[1] - a0[1]) * (b1[1] - a1[1]);
            if !(dot > 0.0) {
                return false;
            }
        }
    }
    true
}

fn width_cost(system: &System, delta: &[[f64; 2]]) -> f64 {
    system
        .rows
        .iter()
        .skip(system.shape_rows)
        .map(|(entries, constant)| {
            let r = constant
                + entries
                    .iter()
                    .map(|(k, v)| v * delta[k / 2][k % 2])
                    .sum::<f64>();
            r * r
        })
        .sum()
}

#[cfg(test)]
mod math_controls {
    use super::*;
    #[test]
    fn qr_recovers_independent_coordinates_and_rejects_rank_loss() {
        // A^T residual = 0 for this overdetermined full-rank system.
        let mut a = vec![vec![1., 0.], vec![0., 1.], vec![1., 1.]];
        let mut b = vec![1., 2., 4.];
        let x = householder_solve(&mut a, &mut b).unwrap();
        assert!((x[0] - 4. / 3.).abs() < 1e-12);
        assert!((x[1] - 7. / 3.).abs() < 1e-12);
        let mut a = vec![vec![1., 2.], vec![2., 4.]];
        let mut b = vec![3., 6.];
        assert!(householder_solve(&mut a, &mut b).is_none());
    }
    #[test]
    fn published_weight_uses_radians_and_survives_unit_conversion() {
        // Audited Hobby (17): orientation denominator 9 is radians.
        let parallel = width_weight(1., 1., [1., 0.], [1., 0.], 16., 0.7);
        let perpendicular = width_weight(1., 1., [1., 0.], [0., 1.], 16., 0.7);
        assert!(
            (perpendicular / parallel - (-(std::f64::consts::FRAC_PI_2 / 9.).powi(2)).exp()).abs()
                < 1e-12
        );
        let px = width_weight(1., 1.5, [1., 0.], [0., 1.], 16., 0.7);
        let normalized = width_weight(0.1, 0.15, [1., 0.], [0., 1.], 1.6, 0.07);
        assert!((normalized * 0.01 - px).abs() < 1e-12);
    }
    #[test]
    fn edge_residual_zero_at_upstream_shift_positive_at_origin() {
        let pts = [[0.0, 0.0], [3.0, 4.0], [-1.0, 7.0], [-4.0, 3.0]];
        let edges = straight_edges(&pts);
        let shift = [[0.25, -0.5], [0.75, 0.125], [0.0, 0.0], [0.0, 0.0]];
        let mut system = System::new(4);
        system.edge_row(&shift, &edges[0], 10.0);
        assert!(width_cost(&system, &shift) < 1e-24);
        assert!(width_cost(&system, &[[0.0, 0.0]; 4]) > 0.0);
    }
    fn pair(verts: [usize; 4]) -> PairOut {
        PairOut {
            verts,
            samples: Vec::new(),
        }
    }
    #[test]
    fn ownership_isolated_pairs_yield_none() {
        let kept = vec![pair([0, 1, 2, 3]), pair([4, 5, 6, 7])];
        assert!(partition_ownership(&kept, 0, 8).is_none());
    }
    #[test]
    fn ownership_shared_vert_marks_related_and_clears_anchor() {
        let kept = vec![pair([0, 1, 2, 3]), pair([3, 4, 5, 6])];
        let ownership = partition_ownership(&kept, 0, 7).unwrap();
        assert_eq!(ownership.related, vec![1]);
        assert_eq!(
            ownership.owned_related,
            vec![false, false, false, false, true, true, true]
        );
        assert_eq!(ownership.free, vec![4, 5, 6]);
    }
    #[test]
    fn ownership_nonzero_anchor_excludes_anchor_verts() {
        let kept = vec![pair([0, 1, 2, 3]), pair([2, 3, 4, 5])];
        let ownership = partition_ownership(&kept, 1, 6).unwrap();
        assert_eq!(ownership.related, vec![0]);
        assert_eq!(
            ownership.owned_related,
            vec![true, true, false, false, false, false]
        );
        assert_eq!(ownership.free, vec![0, 1]);
    }
    #[test]
    fn ownership_duplicate_verts_leave_free_empty() {
        let kept = vec![pair([0, 1, 2, 3]), pair([0, 1, 2, 3])];
        assert!(partition_ownership(&kept, 0, 4).is_none());
    }
    #[test]
    fn ownership_free_lists_ascending_free_indices() {
        let kept = vec![pair([0, 1, 2, 3]), pair([3, 9, 8, 7])];
        let ownership = partition_ownership(&kept, 0, 10).unwrap();
        assert_eq!(ownership.free, vec![7, 8, 9]);
    }
    #[test]
    fn limited_movement_keeps_under_budget_candidate() {
        let mut cand = vec![[3.0, 4.0], [1.0, 0.0]];
        let up = vec![[0.0, 0.0], [1.0, 0.0]];
        assert!(limit_movement(&mut cand, &up, &[0], 10.0, 1.0));
        assert_eq!(cand, vec![[3.0, 4.0], [1.0, 0.0]]);
    }
    #[test]
    fn limited_movement_scales_over_budget_by_exact_quantum_budget() {
        let mut cand = vec![[5.0, 0.0], [0.0, 5.0], [9.0, 9.0]];
        let up = vec![[1.0, 0.0], [0.0, 2.0], [7.0, 7.0]];
        assert!(limit_movement(
            &mut cand,
            &up,
            &[0, 1],
            1.0,
            std::f64::consts::SQRT_2
        ));
        assert_eq!(cand[0], [1.0 + 127.0 / 128.0, 0.0]);
        assert_eq!(cand[1], [0.0, 2.0 + 381.0 / 512.0]);
        assert_eq!(cand[2], [9.0, 9.0]);
    }
    #[test]
    fn limited_movement_leaves_pinned_vertices_untouched() {
        let mut cand = vec![[3.0, 0.0], [0.0, 4.0]];
        let up = vec![[0.0, 0.0], [0.0, 0.0]];
        assert!(limit_movement(&mut cand, &up, &[0], 3.0, 1.0));
        assert!(cand[0][0] > 2.0 && cand[0][0] < 3.0);
        assert_eq!(cand[0][1], 0.0);
        assert_eq!(cand[1], [0.0, 4.0]);
    }
    #[test]
    fn limited_movement_rejects_exhausted_budget_untouched() {
        let mut cand = vec![[3.0, 4.0]];
        let up = vec![[0.0, 0.0]];
        assert!(!limit_movement(&mut cand, &up, &[0], 0.01, 1.0));
        assert_eq!(cand, vec![[3.0, 4.0]]);
        let mut cand = vec![[3.0, 4.0]];
        assert!(!limit_movement(
            &mut cand,
            &up,
            &[0],
            1.0 / 128.0,
            std::f64::consts::SQRT_2
        ));
        assert_eq!(cand, vec![[3.0, 4.0]]);
    }
    #[test]
    fn limited_movement_accepts_zero_move() {
        let mut cand = vec![[1.0, 2.0]];
        let up = vec![[1.0, 2.0]];
        assert!(limit_movement(&mut cand, &up, &[0], 1.0, 1.0));
        assert_eq!(cand, vec![[1.0, 2.0]]);
    }
    #[test]
    fn limited_movement_reserve_shrinks_with_scale() {
        let mut cand = vec![[4.0, 0.0], [0.0, 1.0]];
        let up = vec![[0.0, 0.0], [0.0, 1.0]];
        assert!(limit_movement(&mut cand, &up, &[0], 1.0, 4.0));
        assert!(cand[0][0] > 0.99 && cand[0][0] < 1.0);
        assert_eq!(cand[0][1], 0.0);
        assert_eq!(cand[1], [0.0, 1.0]);
    }
}
