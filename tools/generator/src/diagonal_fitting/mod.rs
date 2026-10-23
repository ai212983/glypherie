//! Width-only direct-diagonal fitting (native port of the frozen experiment).
//!
//! Source: Hobby (4),(5) medial width and signed projected relative width
//! error, (17) relative-contrast coupling, sections 3.2-3.4; Hersch sections
//! 5-6 and Figure 25 supply diagonal parallelization; VTT `DStroke` supplies
//! stationary/floating ownership. Project adaptations: upstream position
//! reference, joint solve with shared vertices, exact upstream fallback.
//! Invariant: removal-free correction only; unsupported geometry, budget
//! overrun, movement or validity failure all return the upstream outline
//! unchanged with `applied=false`. Only malformed, non-finite or out-of-range
//! input is an error. Runtime never uses experiments, Python, CGAL subprocesses
//! or corpus corrections.

pub mod approved;
pub mod attached;
pub mod crossing;
pub mod curve_model;
pub mod curves;
pub(crate) mod dyadic;
pub(crate) mod exact;
pub(crate) mod filtered;
pub(crate) mod geometry;
pub mod intervals;
pub mod joint;
pub(crate) mod numeric;
pub(crate) mod qp;
pub(crate) mod reuse;
pub mod terminal;
pub mod topology;

use crate::{fail, probe::FittedCommand, Error};
/// Unrounded raw source outline in pixels; the parent owns raw capture
/// integration and scaling, this is only the already-scaled geometry.
pub use geometry::Parsed as RawOutline;
use geometry::{Parsed, Portion, Station};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

// Immutable source analysis for one approved fit. Only stages reading the
// identical captured source share these results; raw font geometry, preferred
// streams and moved candidates remain distinct. OnceCell makes preparation
// lazy, preserving the replacement-stage evaluation order.
type VisibleSource = (
    Vec<geometry::Portion>,
    Vec<geometry::BBox>,
    Vec<Vec<geometry::Pt>>,
    Vec<(Vec<geometry::Pt>, geometry::BBox)>,
);
pub(super) struct SourceAnalysis<'a> {
    commands: &'a [FittedCommand],
    parsed: std::cell::OnceCell<Result<Parsed, ()>>,
    visible: std::cell::OnceCell<VisibleSource>,
    pairs: std::cell::OnceCell<(Vec<geometry::Pair>, Vec<geometry::Skipped>)>,
}
impl<'a> SourceAnalysis<'a> {
    pub(super) fn new(commands: &'a [FittedCommand]) -> Self {
        Self {
            commands,
            parsed: Default::default(),
            visible: Default::default(),
            pairs: Default::default(),
        }
    }
    pub(super) fn parsed(&self) -> Result<&Parsed, ()> {
        self.parsed
            .get_or_init(|| geometry::parse_commands(self.commands))
            .as_ref()
            .map_err(|()| ())
    }
    fn visible(&self) -> &VisibleSource {
        self.visible
            .get_or_init(|| geometry::split_visible(self.parsed().expect("validated source"), true))
    }
    fn pairs(&self) -> &(Vec<geometry::Pair>, Vec<geometry::Skipped>) {
        self.pairs.get_or_init(|| {
            let (portions, _, loops, _) = self.visible();
            geometry::recognize(portions, loops, true)
        })
    }
}

/// Nearest-26.6 Euclidean rounding reserve (Hobby interval model).
pub const HEADROOM: f64 = std::f64::consts::SQRT_2 / 128.0;
/// Width-only station fractions over the longest kept interval.
pub const STATION_FRACS: [f64; 3] = [0.25, 0.5, 0.75];
/// Computational bound on outline commands, not a model threshold: split
/// recognition is quadratic in the segment count. The frozen corpus peaks
/// at 89 commands; oversized input fails closed, never tuned per font.
pub const MAX_COMMANDS: usize = 512;

/// Supplied fixed affine correspondence to outline controls (Hobby (31)).
#[derive(Clone, Debug)]
pub struct Sample {
    pub terms: Vec<(usize, f64)>,
}

impl Sample {
    pub fn vertex(index: usize) -> Self {
        Sample {
            terms: vec![(index, 1.0)],
        }
    }

    pub fn affine(i0: usize, t0: f64, i1: usize, t1: f64) -> Self {
        Sample {
            terms: vec![(i0, t0), (i1, t1)],
        }
    }
}

/// Frozen upright reference anchor: same font, axes, size and native settings.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Anchor {
    pub source_width: f64,
    pub fitted_width: f64,
    pub rel: f64,
    pub length: f64,
    pub tangent: [f64; 2],
    pub source_ids: String,
}

/// Font-wide upright anchor list with build diagnostics.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Reference {
    pub anchors: Vec<Anchor>,
    pub size_px: f64,
    pub records: usize,
    pub n_anchors: usize,
    pub rel_min: Option<f64>,
    pub rel_max: Option<f64>,
    pub notes: Vec<ReferenceNote>,
}

/// One skipped donor record and its cause.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ReferenceNote {
    pub record: usize,
    pub reason: String,
}

/// Fitted outline, corrected or passed through unchanged.
#[derive(Clone, Debug)]
pub struct FitResult {
    pub commands: Vec<FittedCommand>,
    pub applied: bool,
    pub reason: String,
    pub diagnostics: serde_json::Value,
}

/// Hobby (17) angular/width coupling weight; the printed 9 is radians.
fn width_weight(w1: f64, w2: f64, t1: [f64; 2], t2: [f64; 2], height: f64) -> f64 {
    let cos = ((t1[0] * t2[0] + t1[1] * t2[1]) / (t1[0].hypot(t1[1]) * t2[0].hypot(t2[1])))
        .clamp(-1.0, 1.0);
    let angle = cos.acos();
    let dw = (w1 - w2) / 0.7;
    500.0 / (height * height) * (-(dw * dw) - (angle / 9.0).powi(2)).exp()
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum RowGroup {
    Position,
    Stretch,
    Bend,
    InkMatch,
}

/// Linear weighted residuals in displacements at nominal scale.
struct System {
    points: Vec<[f64; 2]>,
    height: f64,
    rows: Vec<(RowGroup, Vec<f64>, f64)>,
}

impl System {
    fn new(points: Vec<[f64; 2]>, height: f64) -> Self {
        System {
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
            row[2 * k] = w * dir[0];
            row[2 * k + 1] = w * dir[1];
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
        self.rows.push((RowGroup::Position, sum, 0.0));
        self.rows.push((RowGroup::Position, diff, 0.0));
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
        self.rows.push((RowGroup::Stretch, stretch, 0.0));
        self.rows.push((RowGroup::Bend, bend, 0.0));
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
}

/// Minimum-norm least squares via SVD, NumPy `lstsq(rcond=None)` semantics.
///
/// Rank rule matches the prototype exactly: singular values above
/// `eps * max(m, n) * sigma_max` are kept (`eps` is machine epsilon);
/// the solution is the minimum-norm one in the free modes. No regularizer,
/// no rank-loss rejection: rank deficiency still solves.
fn min_norm_solve(
    a: &nalgebra::DMatrix<f64>,
    b: &nalgebra::DVector<f64>,
) -> nalgebra::DVector<f64> {
    let (m, n) = (a.nrows(), a.ncols());
    if m == 0 || n == 0 {
        return nalgebra::DVector::zeros(n);
    }
    let svd = a.clone().svd(true, true);
    let sigmax = svd.singular_values.iter().cloned().fold(0.0_f64, f64::max);
    if !(sigmax > 0.0) {
        return nalgebra::DVector::zeros(n);
    }
    let tol = f64::EPSILON * (m.max(n) as f64) * sigmax;
    let (Some(u), Some(vt)) = (svd.u, svd.v_t) else {
        return nalgebra::DVector::zeros(n);
    };
    let utb: nalgebra::DVector<f64> = u.transpose() * b;
    let mut x = nalgebra::DVector::zeros(n);
    for (i, &s) in svd.singular_values.iter().enumerate() {
        if s > tol {
            let c = utb[i] / s;
            for j in 0..n {
                x[j] += vt[(i, j)] * c;
            }
        }
    }
    x
}

/// Per-coordinate fixed-column elimination (`System.solve` form).
fn eliminate(
    rows: &[(RowGroup, Vec<f64>, f64)],
    fixed: &HashMap<(usize, usize), f64>,
    nvars: usize,
) -> (Vec<Vec<f64>>, Vec<f64>, Vec<usize>) {
    let mut free = Vec::new();
    for v in 0..nvars {
        for c in 0..2 {
            if !fixed.contains_key(&(v, c)) {
                free.push(2 * v + c);
            }
        }
    }
    let mut matrix = Vec::with_capacity(rows.len());
    let mut constants = Vec::with_capacity(rows.len());
    // Deterministic accumulation order: HashMap iteration is random, and
    // float addition is not associative.
    let mut keys: Vec<(usize, usize)> = fixed.keys().copied().collect();
    keys.sort();
    for (_, row, constant) in rows {
        let mut adjusted = *constant;
        for &(v, c) in &keys {
            adjusted += row[2 * v + c] * fixed[&(v, c)];
        }
        matrix.push(row.clone());
        constants.push(adjusted);
    }
    (matrix, constants, free)
}

fn solve_constrained(
    rows: &[(RowGroup, Vec<f64>, f64)],
    fixed: &HashMap<(usize, usize), f64>,
    nvars: usize,
) -> Vec<f64> {
    let (matrix, constants, free) = eliminate(rows, fixed, nvars);
    let mut loose = vec![0.0; 2 * nvars];
    for (&(v, c), &value) in fixed {
        loose[2 * v + c] = value;
    }
    if free.is_empty() {
        return loose;
    }
    if matrix.is_empty() {
        return loose;
    }
    let m = matrix.len();
    let n = free.len();
    let mut flat = Vec::with_capacity(m * n);
    for row in &matrix {
        for &col in &free {
            flat.push(row[col]);
        }
    }
    let a = nalgebra::DMatrix::from_row_slice(m, n, &flat);
    let rhs: Vec<f64> = constants.iter().map(|c| -c).collect();
    let b = nalgebra::DVector::from_vec(rhs);
    let x = min_norm_solve(&a, &b);
    for (k, &col) in free.iter().enumerate() {
        loose[col] = x[k];
    }
    loose
}

/// Build the font-wide upright anchor list (legacy portion discovery).
///
/// Each vertical rectilinear pair contributes its source width, fitted width
/// measured directly on the fitted outline through exact op correspondence,
/// relative change, arc length, tangent and source identity. No medians across
/// different features. The caller groups records by font, axes, size and hint
/// mode; donor glyphs are the frozen original set.
pub fn build_reference(
    records: &[(&[FittedCommand], &[FittedCommand])],
    size_px: f64,
) -> Reference {
    let mut anchors = Vec::new();
    let mut notes = Vec::new();
    let mut seen = 0usize;
    for (num, (src_cmds, fit_cmds)) in records.iter().enumerate() {
        let (Ok(parsed), Ok(fitted)) = (
            geometry::parse_commands(src_cmds),
            geometry::parse_commands(fit_cmds),
        ) else {
            notes.push(ReferenceNote {
                record: num,
                reason: "missing-commands".to_string(),
            });
            continue;
        };
        if !geometry::check_correspondence(src_cmds, fit_cmds) {
            notes.push(ReferenceNote {
                record: num,
                reason: "no-correspondence".to_string(),
            });
            continue;
        }
        if src_cmds.len() > MAX_COMMANDS || fit_cmds.len() > MAX_COMMANDS {
            notes.push(ReferenceNote {
                record: num,
                reason: "oversize-donor".to_string(),
            });
            continue;
        }
        seen += 1;
        let (portions, _, loops, _) = geometry::split_visible(&parsed, false);
        let (pairs, _) = geometry::recognize(&portions, &loops, false);
        let borders = geometry::visible_borders(&portions);
        for pair in geometry::upright_pairs(&pairs) {
            let (a, b) = (&pair.a, &pair.b);
            let seg_a = [a.p0, a.p1];
            let seg_b = [b.p0, b.p1];
            let Some(cor) = intervals::corridor(seg_a, seg_b) else {
                continue;
            };
            let others = borders
                .iter()
                .filter(|o| {
                    o.key != (a.contour, a.seg, a.t0, a.t1)
                        && o.key != (b.contour, b.seg, b.t0, b.t1)
                })
                .cloned()
                .collect::<Vec<_>>();
            let Some(stations) =
                geometry::station_contacts(seg_a, seg_b, &pair.dom, &others, &loops)
            else {
                notes.push(ReferenceNote {
                    record: num,
                    reason: "unmeasurable-anchor".to_string(),
                });
                continue;
            };
            let src: Vec<f64> = stations.iter().map(|st| st.hit.width).collect();
            let mut fit_widths = Vec::with_capacity(stations.len());
            for st in &stations {
                let qa = geometry::edge_point(a, st.hit.sa, &fitted.oncurve);
                let qb = geometry::edge_point(b, st.hit.sb, &fitted.oncurve);
                fit_widths.push((qb[0] - qa[0]).abs());
            }
            let src_mean = src.iter().sum::<f64>() / src.len() as f64;
            let fit_mean = fit_widths.iter().sum::<f64>() / fit_widths.len() as f64;
            if !(src_mean > 0.0) {
                continue;
            }
            let (lo, hi) = geometry::longest_span(&pair.dom).unwrap_or((0.0, 0.0));
            anchors.push(Anchor {
                source_width: src_mean,
                fitted_width: fit_mean,
                rel: fit_mean / src_mean - 1.0,
                length: hi - lo,
                tangent: cor.d,
                source_ids: format!(
                    "r{}:c{}a({},{:.4},{:.4})/b({},{:.4},{:.4})",
                    num, a.contour, a.seg, a.t0, a.t1, b.seg, b.t0, b.t1
                ),
            });
        }
    }
    let rels: Vec<f64> = anchors.iter().map(|an| an.rel).collect();
    Reference {
        n_anchors: anchors.len(),
        rel_min: rels
            .iter()
            .cloned()
            .fold(None, |m: Option<f64>, v| Some(m.map_or(v, |m| m.min(v)))),
        rel_max: rels
            .iter()
            .cloned()
            .fold(None, |m: Option<f64>, v| Some(m.map_or(v, |m| m.max(v)))),
        anchors,
        size_px,
        records: seen,
        notes,
    }
}

/// Prepared diagonal pair with its movement budget and solve state.
struct PreppedInfo {
    id: String,
    a: Portion,
    b: Portion,
    normal: [f64; 2],
    stations: Vec<Station>,
    src_widths: Vec<f64>,
    fit_widths: Vec<f64>,
    arc: f64,
    span_lo: f64,
    span_hi: f64,
    bound: f64,
    prefix: f64,
    peak: f64,
    rounded_peak: Option<f64>,
    pairs: Vec<(Vec<f64>, f64, [f64; 2])>,
    feet: serde_json::Value,
}

fn acute(tangent: [f64; 2], other: [f64; 2]) -> [f64; 2] {
    if tangent[0] * other[0] + tangent[1] * other[1] < 0.0 {
        [-tangent[0], -tangent[1]]
    } else {
        tangent
    }
}

/// Joint system: source shape rows plus (17) anchor coupling.
///
/// Coefficients come from the source outline with the upstream gap
/// substituted into the geometry constants, so shape residuals vanish at
/// upstream. Every diagonal station couples to every reference anchor
/// through its own (17) row. Width-only: no hard rows; only per-coordinate
/// fixed elimination, and every unconstrained coordinate solves minimum-norm.
#[allow(clippy::too_many_arguments)]
fn assemble(
    parsed: &Parsed,
    fitted_coords: &[[f64; 2]],
    prepped: &mut [PreppedInfo],
    anchors: &[Anchor],
    size_px: f64,
    pins: &HashSet<usize>,
    owned_axes: &[usize],
) -> (System, HashMap<(usize, usize), f64>, HashSet<usize>) {
    let mut system = System::new(parsed.oncurve.clone(), size_px);
    let mut var_verts = HashSet::new();
    for info in prepped.iter() {
        var_verts.insert(info.a.i0);
        var_verts.insert(info.a.i1);
        var_verts.insert(info.b.i0);
        var_verts.insert(info.b.i1);
    }
    let mut ring = HashSet::new();
    for contour in &parsed.contours {
        for seg in contour {
            if !seg.is_line() {
                continue;
            }
            let (i, j) = seg.endpoints();
            if var_verts.contains(&i) || var_verts.contains(&j) {
                ring.insert((i, j));
            }
        }
    }
    let mut ring_sorted: Vec<(usize, usize)> = ring.into_iter().collect();
    ring_sorted.sort();
    for (i, j) in ring_sorted {
        let _ = system.edge(i, j);
    }
    let base = parsed.oncurve.clone();
    let upstream = fitted_coords.to_vec();
    let shift: Vec<f64> = base
        .iter()
        .zip(upstream.iter())
        .flat_map(|(b, u)| [u[0] - b[0], u[1] - b[1]])
        .collect();
    for (group, row, constant) in system.rows.iter_mut() {
        match group {
            RowGroup::Position | RowGroup::Stretch | RowGroup::Bend => {
                let dot: f64 = row.iter().zip(shift.iter()).map(|(r, s)| r * s).sum();
                *constant -= dot;
            }
            RowGroup::InkMatch => {}
        }
    }
    for info in prepped.iter_mut() {
        let ta = |frac: f64| Sample::affine(info.a.i0, 1.0 - frac, info.a.i1, frac);
        let tb = |frac: f64| Sample::affine(info.b.i0, 1.0 - frac, info.b.i1, frac);
        let mut station_pairs = Vec::new();
        let mut ok = true;
        for st in &info.stations {
            let fa = info.a.t0 + (info.a.t1 - info.a.t0) * st.hit.sa;
            let fb = info.b.t0 + (info.b.t1 - info.b.t0) * st.hit.sb;
            match system.pair(&ta(fa), &tb(fb), info.arc, st.hit.center) {
                Ok(p) => station_pairs.push(p),
                Err(()) => {
                    ok = false;
                    break;
                }
            }
        }
        if !ok {
            continue;
        }
        info.pairs = Vec::with_capacity(station_pairs.len());
        for ((error, width, tangent), st) in station_pairs.into_iter().zip(info.stations.iter()) {
            info.pairs.push((error.clone(), width, tangent));
            for anchor in anchors {
                // Hobby (17) couples through the acute meeting angle: spine
                // order carries no orientation, so only the run side is
                // flipped toward the anchor; the reference stays unchanged.
                let run_tangent = acute(tangent, anchor.tangent);
                let psi = width_weight(
                    width,
                    anchor.source_width,
                    run_tangent,
                    anchor.tangent,
                    size_px,
                );
                let weight = info.arc * anchor.length * psi;
                let scaled: Vec<f64> = error.iter().map(|x| x * weight.sqrt()).collect();
                system
                    .rows
                    .push((RowGroup::InkMatch, scaled, anchor.rel * weight.sqrt()));
            }
            let _ = st;
        }
    }
    let mut fixed: HashMap<(usize, usize), f64> = HashMap::new();
    let gaps: Vec<[f64; 2]> = upstream
        .iter()
        .zip(base.iter())
        .map(|(u, b)| [u[0] - b[0], u[1] - b[1]])
        .collect();
    for &v in pins {
        fixed.insert((v, 0), gaps[v][0]);
        fixed.insert((v, 1), gaps[v][1]);
    }
    for &v in &var_verts {
        for &axis in owned_axes {
            fixed.insert((v, axis), gaps[v][axis]);
        }
    }
    let mut far = HashSet::new();
    for contour in &parsed.contours {
        for seg in contour {
            if !seg.is_line() {
                continue;
            }
            let (i, j) = seg.endpoints();
            if var_verts.contains(&i) && !var_verts.contains(&j) {
                far.insert(j);
            }
            if var_verts.contains(&j) && !var_verts.contains(&i) {
                far.insert(i);
            }
        }
    }
    for v in far {
        for axis in 0..2 {
            fixed.entry((v, axis)).or_insert(gaps[v][axis]);
        }
    }
    (system, fixed, var_verts)
}

/// Sorted vertex list for deterministic diagnostics; HashSet order is random.
fn sorted_verts(set: &HashSet<usize>) -> Vec<usize> {
    let mut out: Vec<usize> = set.iter().copied().collect();
    out.sort();
    out
}

fn abstain(upstream: &[FittedCommand], reason: &str, diagnostics: serde_json::Value) -> FitResult {
    FitResult {
        commands: upstream.to_vec(),
        applied: false,
        reason: reason.to_string(),
        diagnostics,
    }
}

/// Fit diagonal pairs of one glyph; exact upstream on abstention.
///
/// The joint system couples every diagonal station to every reference
/// anchor through (17) rows while source shape rows hold the outline;
/// shared vertices carry one unknown. Native-owned components and upright
/// anchors stay at upstream exactly. The candidate rounds moved coordinates
/// to 26.6 and must preserve orientation signs, upstream portion topology
/// and station ink, or the exact upstream commands return with the validity
/// evidence. Width-only: no grid arm, canonical exact crossings, interval
/// ownership.
pub fn fit(
    source: &[FittedCommand],
    upstream: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> Result<FitResult, Error> {
    fit_with_analysis(
        source,
        upstream,
        size_px,
        reference,
        native_axes,
        &SourceAnalysis::new(source),
    )
}

pub(super) fn fit_with_analysis(
    source: &[FittedCommand],
    upstream: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
    analysis: &SourceAnalysis<'_>,
) -> Result<FitResult, Error> {
    if !(size_px.is_finite() && size_px > 0.0) {
        return Err(fail("diagonal width requires finite positive size"));
    }
    if !geometry::check_correspondence(source, upstream) {
        return Ok(abstain(
            upstream,
            "no-correspondence",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    let (Ok(parsed), Ok(fitted)) = (analysis.parsed(), geometry::parse_commands(upstream)) else {
        return Ok(abstain(
            upstream,
            "malformed-commands",
            serde_json::json!({"size_px": size_px}),
        ));
    };
    if source.len() > MAX_COMMANDS || upstream.len() > MAX_COMMANDS {
        return Ok(abstain(
            upstream,
            "oversize-outline",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    if reference.anchors.is_empty() {
        return Ok(abstain(
            upstream,
            "no-reference-anchors",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    let (portions, curve_boxes, loops, flats) = analysis.visible();
    let (pairs, skipped) = analysis.pairs();
    let mut skipped = skipped.clone();
    let straights = loops.clone();
    let mut pins: HashSet<usize> = HashSet::new();
    for pair in geometry::upright_pairs(&pairs) {
        for side in [&pair.a, &pair.b] {
            pins.insert(side.i0);
            pins.insert(side.i1);
        }
    }
    for contour in &parsed.contours {
        for seg in contour {
            if seg.is_line() {
                continue;
            }
            let (a, b) = seg.endpoints();
            pins.insert(a);
            pins.insert(b);
        }
    }
    let owned: Vec<usize> = native_axes
        .iter()
        .enumerate()
        .filter(|(_, on)| **on)
        .map(|(axis, _)| axis)
        .collect();
    let borders = geometry::visible_borders(&portions);
    let fitted_coords = fitted.oncurve.clone();
    let mut prepped: Vec<PreppedInfo> = Vec::new();
    for pair in pairs {
        if geometry::upright_pairs(std::slice::from_ref(pair)).len() == 1 {
            skipped.push(geometry::Skipped {
                pair: (pair.a.seg, pair.b.seg),
                reason: "upright-anchor".to_string(),
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
            &geometry::curve_controls(&parsed),
        ) {
            Ok(prepped_pair) => {
                let bound = prepped_pair
                    .src_widths
                    .iter()
                    .cloned()
                    .fold(f64::INFINITY, f64::min)
                    / 2.0
                    - HEADROOM;
                if !(bound >= HEADROOM) {
                    skipped.push(geometry::Skipped {
                        pair: (pair.a.seg, pair.b.seg),
                        reason: "movement-budget-empty".to_string(),
                    });
                    continue;
                }
                let feet = serde_json::Value::Array(
                    pair.feet
                        .as_ref()
                        .map(|ranges| {
                            ranges
                                .iter()
                                .map(|r| serde_json::json!({"a": r.a, "b": r.b}))
                                .collect()
                        })
                        .unwrap_or_default(),
                );
                prepped.push(PreppedInfo {
                    id: prepped_pair.id,
                    a: prepped_pair.a,
                    b: prepped_pair.b,
                    normal: prepped_pair.normal,
                    stations: prepped_pair.stations,
                    src_widths: prepped_pair.src_widths,
                    fit_widths: prepped_pair.fit_widths,
                    arc: prepped_pair.arc,
                    span_lo: prepped_pair.span_lo,
                    span_hi: prepped_pair.span_hi,
                    bound,
                    prefix: 1.0,
                    peak: 0.0,
                    rounded_peak: None,
                    pairs: Vec::new(),
                    feet,
                });
            }
            Err(reason) => {
                skipped.push(geometry::Skipped {
                    pair: (pair.a.seg, pair.b.seg),
                    reason: reason.to_string(),
                });
            }
        }
    }
    let fixed_meta = serde_json::json!({
        "anchors": sorted_verts(&pins),
        "native_axes": [native_axes[0], native_axes[1]],
    });
    let skipped_json: Vec<serde_json::Value> = skipped
        .iter()
        .map(|s| serde_json::json!({"pair": [s.pair.0, s.pair.1], "reason": s.reason}))
        .collect();
    if prepped.is_empty() {
        return Ok(abstain(
            upstream,
            "all-abstained",
            serde_json::json!({"skipped": skipped_json, "fixed": fixed_meta}),
        ));
    }
    let (system, fixed, var_verts) = assemble(
        &parsed,
        &fitted_coords,
        &mut prepped,
        &reference.anchors,
        size_px,
        &pins,
        &owned,
    );
    let loose = solve_constrained(&system.rows, &fixed, parsed.oncurve.len());
    let base = parsed.oncurve.clone();
    let upstream_coords = fitted_coords.clone();
    let mut deltas: Vec<[f64; 2]> = (0..base.len())
        .map(|v| {
            [
                base[v][0] + loose[2 * v] - upstream_coords[v][0],
                base[v][1] + loose[2 * v + 1] - upstream_coords[v][1],
            ]
        })
        .collect();
    for info in prepped.iter_mut() {
        let verts = [info.a.i0, info.a.i1, info.b.i0, info.b.i1];
        info.peak = verts
            .iter()
            .map(|&v| deltas[v][0].hypot(deltas[v][1]))
            .fold(0.0, f64::max);
    }
    let over: Vec<&PreppedInfo> = prepped
        .iter()
        .filter(|info| info.peak > info.bound)
        .collect();
    if !over.is_empty() {
        // Convex descent along the upstream-to-minimizer segment: the
        // objective decreases monotonically, so the feasible prefix keeps
        // every fixed coordinate exact while restoring the budget.
        let scale = over
            .iter()
            .map(|info| info.bound / info.peak)
            .fold(f64::INFINITY, f64::min);
        for d in deltas.iter_mut() {
            d[0] *= scale;
            d[1] *= scale;
        }
        for info in prepped.iter_mut() {
            info.prefix = scale;
        }
        for info in prepped.iter_mut() {
            let verts = [info.a.i0, info.a.i1, info.b.i0, info.b.i1];
            info.peak = verts
                .iter()
                .map(|&v| deltas[v][0].hypot(deltas[v][1]))
                .fold(0.0, f64::max);
        }
    }
    let table = geometry::index_map(upstream);
    let mut candidate = upstream.to_vec();
    for &v in &var_verts {
        let Some(pos) = table.get(v).copied().flatten() else {
            continue;
        };
        for axis in 0..2 {
            if fixed.contains_key(&(v, axis)) {
                continue;
            }
            let value = upstream_coords[v][axis] + deltas[v][axis];
            if value == upstream_coords[v][axis] {
                continue;
            }
            let rounded = geometry::round_26_6(value) as f32;
            match &mut candidate[pos] {
                FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => {
                    if axis == 0 {
                        *x = rounded;
                    } else {
                        *y = rounded;
                    }
                }
                FittedCommand::QuadTo(x1, y1, x, y) => {
                    if axis == 0 {
                        *x = rounded;
                    } else {
                        *y = rounded;
                    }
                    let _ = (x1, y1);
                }
                FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                    if axis == 0 {
                        *x = rounded;
                    } else {
                        *y = rounded;
                    }
                    let _ = (x1, y1, x2, y2);
                }
                FittedCommand::Close => {}
            }
        }
    }
    let achieved_fallback = achieved_widths(&prepped, upstream);
    if candidate == upstream {
        let widths = mean_widths(&achieved_fallback);
        return Ok(FitResult {
            commands: upstream.to_vec(),
            applied: false,
            reason: "no-movement".to_string(),
            diagnostics: serde_json::json!({
                "validity": {"ok": true, "stage": "zero-change"},
                "pairs": achieved_json(&prepped, &achieved_fallback),
                "skipped": skipped_json,
                "phase_applied": false,
                "fixed": fixed_meta,
                "movement": 0.0,
                "bound": prepped.iter().map(|i| i.bound).fold(f64::INFINITY, f64::min),
                "size_px": size_px,
                "grid": false,
                "widths": widths,
                "reference": reference_meta(reference),
            }),
        });
    }
    let validity = validate(
        &parsed,
        &fitted,
        upstream,
        &candidate,
        &portions,
        &mut prepped,
        &pins,
        &owned,
        source,
    );
    let mut validity = validity;
    if validity.ok {
        if let Err(reason) = geometry::curve_sweep_ok(
            &parsed,
            &fitted_coords,
            &candidate,
            &geometry::curve_controls(&fitted),
        ) {
            validity.ok = false;
            validity.stage = reason.to_string();
        }
    }
    let match_rows: Vec<(&Vec<f64>, f64)> = system
        .rows
        .iter()
        .filter(|(g, _, _)| *g == RowGroup::InkMatch)
        .map(|(_, row, constant)| (row, *constant))
        .collect();
    let flat_base_up: Vec<f64> = upstream_coords
        .iter()
        .zip(base.iter())
        .flat_map(|(u, b)| [u[0] - b[0], u[1] - b[1]])
        .collect();
    let cost_upstream: f64 = match_rows
        .iter()
        .map(|(row, constant)| {
            let dot: f64 = row
                .iter()
                .zip(flat_base_up.iter())
                .map(|(r, s)| r * s)
                .sum();
            (dot + constant).powi(2)
        })
        .sum();
    let cand_parsed =
        geometry::parse_commands(&candidate).map_err(|_| fail("unparseable-candidate"))?;
    let flat_base_cand: Vec<f64> = cand_parsed
        .oncurve
        .iter()
        .zip(base.iter())
        .flat_map(|(c, b)| [c[0] - b[0], c[1] - b[1]])
        .collect();
    let cost_candidate: f64 = match_rows
        .iter()
        .map(|(row, constant)| {
            let dot: f64 = row
                .iter()
                .zip(flat_base_cand.iter())
                .map(|(r, s)| r * s)
                .sum();
            (dot + constant).powi(2)
        })
        .sum();
    let cost_ok = cost_candidate < cost_upstream;
    validity.cost_upstream = Some(cost_upstream);
    validity.cost_candidate = Some(cost_candidate);
    validity.cost_ok = cost_ok;
    if !cost_ok {
        validity.ok = false;
        validity.stage = "no-cost-decrease".to_string();
    }
    let achieved = achieved_widths(&prepped, &candidate);
    let widths = mean_widths(&achieved);
    if !validity.ok {
        let tried = mean_widths(&achieved);
        return Ok(FitResult {
            commands: upstream.to_vec(),
            applied: false,
            reason: "invalid-candidate".to_string(),
            diagnostics: serde_json::json!({
                "validity": validity_json(&validity),
                "pairs": achieved_json(&prepped, &achieved),
                "skipped": skipped_json,
                "phase_applied": false,
                "attempt": {
                    "movement": prepped.iter().map(|i| i.peak).fold(0.0, f64::max),
                    "widths": tried,
                    "pairs": achieved_json(&prepped, &achieved),
                    "validity": validity_json(&validity),
                },
                "fixed": fixed_meta,
                "movement": 0.0,
                "bound": prepped.iter().map(|i| i.bound).fold(f64::INFINITY, f64::min),
                "size_px": size_px,
                "grid": false,
                "widths": mean_widths(&achieved_fallback),
                "reference": reference_meta(reference),
            }),
        });
    }
    Ok(FitResult {
        commands: candidate,
        applied: true,
        reason: "applied".to_string(),
        diagnostics: serde_json::json!({
            "validity": validity_json(&validity),
            "pairs": achieved_json(&prepped, &achieved),
            "skipped": skipped_json,
            "phase_applied": false,
            "fixed": fixed_meta,
            "movement": prepped.iter().map(|i| i.peak).fold(0.0, f64::max),
            "bound": prepped.iter().map(|i| i.bound).fold(f64::INFINITY, f64::min),
            "size_px": size_px,
            "grid": false,
            "widths": widths,
            "reference": reference_meta(reference),
        }),
    })
}

/// Post-rounding gates; any failure rejects the whole glyph.
struct Validity {
    ok: bool,
    stage: String,
    split_topology: bool,
    pins_exact: bool,
    centers_inked: bool,
    movement_ok: bool,
    cost_upstream: Option<f64>,
    cost_candidate: Option<f64>,
    cost_ok: bool,
}

fn validity_json(v: &Validity) -> serde_json::Value {
    serde_json::json!({
        "ok": v.ok,
        "stage": v.stage,
        "ops": true,
        "orientation": true,
        "split_topology": v.split_topology,
        "topology_mode": "exact_arrangement",
        "pins_exact": v.pins_exact,
        "centers_inked": v.centers_inked,
        "movement_ok": v.movement_ok,
        "hard_rounded_ok": true,
        "cost_upstream": v.cost_upstream,
        "cost_candidate": v.cost_candidate,
        "cost_ok": v.cost_ok,
    })
}

#[allow(clippy::too_many_arguments)]
fn validate(
    parsed: &Parsed,
    fitted: &Parsed,
    fitted_commands: &[FittedCommand],
    candidate: &[FittedCommand],
    portions: &[geometry::Portion],
    prepped: &mut [PreppedInfo],
    pins: &HashSet<usize>,
    owned: &[usize],
    source_commands: &[FittedCommand],
) -> Validity {
    let mut v = Validity {
        ok: true,
        stage: String::new(),
        split_topology: false,
        pins_exact: true,
        centers_inked: true,
        movement_ok: true,
        cost_upstream: None,
        cost_candidate: None,
        cost_ok: false,
    };
    if !geometry::check_correspondence(fitted_commands, candidate) {
        v.ok = false;
        v.stage = "ops-changed".to_string();
        return v;
    }
    let cand = match geometry::parse_commands(candidate) {
        Ok(c) => c,
        Err(()) => {
            v.ok = false;
            v.stage = "unparseable-candidate".to_string();
            return v;
        }
    };
    let before = geometry::signed_areas(&geometry::loops_points(fitted));
    let after = geometry::signed_areas(&geometry::loops_points(&cand));
    let orientation = before
        .iter()
        .zip(after.iter())
        .all(|(a, b)| a.signum() == b.signum());
    if !orientation {
        v.ok = false;
        v.stage = "orientation-flip".to_string();
        return v;
    }
    let (cand_portions, _, _, cand_flats) = geometry::split_visible(&cand, true);
    let (up_portions, _, _, up_flats) = geometry::split_visible(fitted, true);
    v.split_topology =
        geometry::topology_signature(&cand_portions) == geometry::topology_signature(&up_portions);
    let _ = portions;
    // Width-only adoption replaces the split gate with the exact arrangement
    // reference; ownership, correspondence, movement and ink checks stay.
    if !curves::compare_commands(source_commands, fitted_commands, candidate) {
        v.ok = false;
        v.stage = "topology-mismatch".to_string();
        return v;
    }
    let table = geometry::index_map(candidate);
    for &pin in pins {
        let Some(pos) = table.get(pin).copied().flatten() else {
            continue;
        };
        let (cx, cy) = match &candidate[pos] {
            FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => (*x as f64, *y as f64),
            FittedCommand::QuadTo(_, _, x, y) | FittedCommand::CurveTo(_, _, _, _, x, y) => {
                (*x as f64, *y as f64)
            }
            FittedCommand::Close => continue,
        };
        if cx != fitted.oncurve[pin][0] || cy != fitted.oncurve[pin][1] {
            v.pins_exact = false;
        }
    }
    let mut inverted: HashMap<usize, usize> = HashMap::new();
    for (idx, pos) in table.iter().enumerate() {
        if let Some(p) = pos {
            inverted.insert(*p, idx);
        }
    }
    for (pos, cmd) in candidate.iter().enumerate() {
        let Some(&idx) = inverted.get(&pos) else {
            continue;
        };
        for &axis in owned {
            let (cx, cy) = match cmd {
                FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => (*x as f64, *y as f64),
                FittedCommand::QuadTo(_, _, x, y) | FittedCommand::CurveTo(_, _, _, _, x, y) => {
                    (*x as f64, *y as f64)
                }
                FittedCommand::Close => continue,
            };
            let want = fitted.oncurve[idx][axis];
            if (axis == 0 && cx != want) || (axis == 1 && cy != want) {
                v.pins_exact = false;
            }
        }
        let _ = parsed;
    }
    if !v.pins_exact {
        v.ok = false;
        v.stage = "pins-moved".to_string();
        return v;
    }
    let cand_loops = geometry::loops_points(&cand);
    let up_loops = geometry::loops_points(fitted);
    for info in prepped.iter_mut() {
        let mid = &info.stations[info.stations.len() / 2].hit;
        let qa = geometry::edge_point(&info.a, mid.sa, &cand.oncurve);
        let qb = geometry::edge_point(&info.b, mid.sb, &cand.oncurve);
        let center = [(qa[0] + qb[0]) / 2.0, (qa[1] + qb[1]) / 2.0];
        let wc = geometry::certified_winding(center, &cand_loops, &cand_flats);
        let ua = geometry::edge_point(&info.a, mid.sa, &fitted.oncurve);
        let ub = geometry::edge_point(&info.b, mid.sb, &fitted.oncurve);
        let ucenter = [(ua[0] + ub[0]) / 2.0, (ua[1] + ub[1]) / 2.0];
        let wu = geometry::certified_winding(ucenter, &up_loops, &up_flats);
        match (wc, wu) {
            (Some(a), Some(b)) if a != 0 && a == b => {}
            _ => {
                v.centers_inked = false;
            }
        }
        let mut peak = 0.0f64;
        for vert in [info.a.i0, info.a.i1, info.b.i0, info.b.i1] {
            let Some(pos) = table.get(vert).copied().flatten() else {
                continue;
            };
            let (cx, cy) = match &candidate[pos] {
                FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => (*x as f64, *y as f64),
                FittedCommand::QuadTo(_, _, x, y) | FittedCommand::CurveTo(_, _, _, _, x, y) => {
                    (*x as f64, *y as f64)
                }
                FittedCommand::Close => continue,
            };
            peak = peak.max((cx - fitted.oncurve[vert][0]).hypot(cy - fitted.oncurve[vert][1]));
        }
        info.rounded_peak = Some(peak);
        if !(peak <= info.bound + HEADROOM) {
            v.movement_ok = false;
        }
    }
    if !v.centers_inked {
        v.ok = false;
        v.stage = "center-uninked".to_string();
        return v;
    }
    if !v.movement_ok {
        v.ok = false;
        v.stage = "movement-over-budget".to_string();
        return v;
    }
    v
}

/// Measured post-rounding widths on one command set.
struct Achieved {
    source: f64,
    upstream: f64,
    candidate: f64,
}

fn achieved_widths(prepped: &[PreppedInfo], commands: &[FittedCommand]) -> Vec<Achieved> {
    let cand = geometry::parse_commands(commands)
        .map(|p| p.oncurve)
        .unwrap_or_default();
    prepped
        .iter()
        .map(|info| {
            let mut src = 0.0;
            let mut ups = 0.0;
            let mut got = 0.0;
            for (k, st) in info.stations.iter().enumerate() {
                let qa = geometry::edge_point(&info.a, st.hit.sa, &cand);
                let qb = geometry::edge_point(&info.b, st.hit.sb, &cand);
                got += ((qb[0] - qa[0]) * info.normal[0] + (qb[1] - qa[1]) * info.normal[1]).abs();
                src += info.src_widths[k];
                // Upstream widths reuse the prepare-time measurement, as in
                // the prototype, rather than recomputing the same projection.
                ups += info.fit_widths[k];
            }
            let n = info.stations.len() as f64;
            Achieved {
                source: src / n,
                upstream: ups / n,
                candidate: got / n,
            }
        })
        .collect()
}

fn mean_widths(achieved: &[Achieved]) -> serde_json::Value {
    let n = achieved.len().max(1) as f64;
    serde_json::json!({
        "source": achieved.iter().map(|a| a.source).sum::<f64>() / n,
        "upstream": achieved.iter().map(|a| a.upstream).sum::<f64>() / n,
        "candidate": achieved.iter().map(|a| a.candidate).sum::<f64>() / n,
    })
}

fn achieved_json(prepped: &[PreppedInfo], achieved: &[Achieved]) -> serde_json::Value {
    prepped
        .iter()
        .zip(achieved.iter())
        .map(|(info, a)| {
            serde_json::json!({
                "id": info.id,
                "interval": [info.span_lo, info.span_hi],
                "feet": info.feet,
                "stations": info.stations.iter().map(|st| st.s).collect::<Vec<f64>>(),
                "source_width": a.source,
                "upstream_width": a.upstream,
                "candidate_width": a.candidate,
                "bound": info.bound,
                "prefix": info.prefix,
                "peak": info.peak,
                "rounded_peak": info.rounded_peak,
                "phase_applied": false,
                "grid": null,
            })
        })
        .collect()
}

fn reference_meta(reference: &Reference) -> serde_json::Value {
    serde_json::json!({
        "n_anchors": reference.n_anchors,
        "rel_min": reference.rel_min,
        "rel_max": reference.rel_max,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn anchor(rel: f64) -> Anchor {
        Anchor {
            source_width: 1.0,
            fitted_width: 1.0 + rel,
            rel,
            length: 4.0,
            tangent: [0.0, 1.0],
            source_ids: "r0:c0a(0,0.0000,1.0000)/b(1,0.0000,1.0000)".to_string(),
        }
    }

    #[test]
    fn empty_anchors_fail_closed() {
        let square = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(4.0, 0.0),
            FittedCommand::LineTo(4.0, 4.0),
            FittedCommand::LineTo(0.0, 4.0),
            FittedCommand::Close,
        ];
        let reference = Reference {
            anchors: vec![],
            size_px: 16.0,
            records: 0,
            n_anchors: 0,
            rel_min: None,
            rel_max: None,
            notes: vec![],
        };
        let result = fit(&square, &square, 16.0, &reference, [false, false]).unwrap();
        assert!(!result.applied);
        assert_eq!(result.reason, "no-reference-anchors");
        assert_eq!(result.commands, square);
    }

    #[test]
    fn mismatched_ops_fail_closed() {
        let a = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(4.0, 0.0),
            FittedCommand::Close,
        ];
        let b = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(4.0, 0.0),
            FittedCommand::LineTo(4.0, 4.0),
            FittedCommand::Close,
        ];
        let reference = Reference {
            anchors: vec![anchor(0.0)],
            size_px: 16.0,
            records: 1,
            n_anchors: 1,
            rel_min: Some(0.0),
            rel_max: Some(0.0),
            notes: vec![],
        };
        let result = fit(&a, &b, 16.0, &reference, [false, false]).unwrap();
        assert!(!result.applied);
        assert_eq!(result.reason, "no-correspondence");
        assert_eq!(result.commands, b);
    }

    #[test]
    fn nonpositive_size_is_an_error() {
        let square = vec![FittedCommand::Close];
        let reference = Reference {
            anchors: vec![anchor(0.0)],
            size_px: 16.0,
            records: 1,
            n_anchors: 1,
            rel_min: Some(0.0),
            rel_max: Some(0.0),
            notes: vec![],
        };
        assert!(fit(&square, &square, 0.0, &reference, [false, false]).is_err());
    }

    #[test]
    fn width_weight_matches_published_form() {
        let w = width_weight(1.0, 1.0, [0.0, 1.0], [0.0, 1.0], 16.0);
        assert!((w - 500.0 / 256.0).abs() < 1e-12);
    }

    #[test]
    fn coupling_weight_ignores_run_direction() {
        // Hobby (17) weighs the acute meeting angle: flipping the run
        // spine must not change the coupling, since spine order carries
        // no orientation. Both acute branches are exercised.
        let anchor = [0.0, 1.0];
        let run = [0.7071067811865476, 0.7071067811865476];
        let neg = [-run[0], -run[1]];
        let a = width_weight(1.2, 1.0, acute(run, anchor), anchor, 16.0);
        let b = width_weight(1.2, 1.0, acute(neg, anchor), anchor, 16.0);
        assert_eq!(a, b);
        let cross = [-run[1], run[0]];
        let flipped = [-cross[0], -cross[1]];
        let c = width_weight(1.2, 1.0, acute(cross, anchor), anchor, 16.0);
        let d = width_weight(1.2, 1.0, acute(flipped, anchor), anchor, 16.0);
        assert_eq!(c, d);
    }

    #[test]
    fn svd_solves_rank_deficient_minimum_norm() {
        // Two identical rows: infinite solutions; NumPy lstsq returns the
        // minimum-norm one (0.5 each for x1 + x2 = 1).
        let a = nalgebra::DMatrix::from_row_slice(2, 2, &[1.0, 1.0, 1.0, 1.0]);
        let b = nalgebra::DVector::from_vec(vec![1.0, 1.0]);
        let x = min_norm_solve(&a, &b);
        assert!((x[0] - 0.5).abs() < 1e-12);
        assert!((x[1] - 0.5).abs() < 1e-12);
    }

    #[test]
    fn svd_keeps_small_rank_rule() {
        // Single tiny-but-nonzero singular value above the NumPy cutoff.
        let a = nalgebra::DMatrix::from_row_slice(2, 2, &[1.0, 0.0, 0.0, 1e-10]);
        let b = nalgebra::DVector::from_vec(vec![1.0, 1e-10]);
        let x = min_norm_solve(&a, &b);
        assert!((x[0] - 1.0).abs() < 1e-9);
        assert!((x[1] - 1.0).abs() < 1e-6);
    }

    #[test]
    fn width_weight_asymmetric_scaled_tangents() {
        let w = width_weight(1.7, 1.0, [3.0, 4.0], [-1.0, 7.0], 10.0);
        assert!((w - 1.8254425977371571).abs() < 1e-12);
    }
}
