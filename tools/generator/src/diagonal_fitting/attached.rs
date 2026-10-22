//! Source-preserving attached curved-diagonal fit (native port of the frozen experiment).
//!
//! Source: Hersch fixed-direction diagonal constraints with shared Hobby
//! curve controls. The source border classifier and integer target are reused
//! unchanged. Hobby (1)-(3), (17), and section 6 supply the distortion/width
//! objective. Hersch section 6 Figure 25 supplies two parallel borders at
//! integer axis separation. With upstream Y retained, both those constraints
//! and curve joint cross products are linear in the remaining X displacements.
//!
//! Project adaptations: widths reuse the maintained width system and its
//! exact upstream fallback; the joint couples (17) relative-width rows with
//! hard parallel/separation rows about the integer target. Smooth-curve
//! helpers (weld map, joints, G1 rows, cross bounds, emit, quad-interval
//! certificate) come from the sibling worker module `super::curve_model`.
//! Native-owned X abstains outright; upstream Y is always retained, so only
//! X displacements solve. Any infeasible gate returns the exact upstream
//! commands with `applied=false`. Only malformed, non-finite or out-of-range
//! input is an error. Runtime never uses experiments, Python, subprocesses
//! or corpus corrections.

use super::curve_model as scf;
use super::{
    acute, curves, geometry, qp, width_weight, FitResult, Reference, HEADROOM, MAX_COMMANDS,
};
use crate::{fail, probe::FittedCommand, Error};
use std::collections::{HashMap, HashSet};

/// Diagonal spread gate over one pair (prototype `GRID_SPREAD`).
const GRID_SPREAD: f64 = 0.25;

fn dot(a: &[f64], b: &[f64]) -> f64 {
    a.iter().zip(b.iter()).map(|(x, y)| x * y).sum()
}

fn abstain(upstream: &[FittedCommand], reason: &str, diagnostics: serde_json::Value) -> FitResult {
    FitResult {
        commands: upstream.to_vec(),
        applied: false,
        reason: reason.to_string(),
        diagnostics,
    }
}

/// Integer line-separation target from the coupled normal width.
struct Gate {
    axis: usize,
    integer: i64,
    target: f64,
    coupled: f64,
    rel: f64,
    w_src: f64,
    fa: f64,
    fb: f64,
}

/// Integer line separation from the coupled normal width.
///
/// The weighted anchor mean gives the coupled relative change; the integer
/// counts axis units of line separation, so the normal target divides by the
/// axis normal component. Line separation between parallel borders is normal
/// width over that component, never the contact-chord projection. The axis
/// rule keeps the component above sqrt(2)/2 by construction.
fn grid_target(
    info: &geometry::PreppedPair,
    direction: [f64; 2],
    anchors: &[super::Anchor],
    size_px: f64,
) -> Option<Gate> {
    let widths = &info.src_widths;
    if widths.is_empty() {
        return None;
    }
    let mean = widths.iter().sum::<f64>() / widths.len() as f64;
    let (mut lo, mut hi) = (f64::INFINITY, f64::NEG_INFINITY);
    for w in widths {
        lo = lo.min(*w);
        hi = hi.max(*w);
    }
    if hi - lo > GRID_SPREAD / hi.max(0.0).sqrt() {
        return None;
    }
    let axis = if direction[1].abs() >= direction[0].abs() {
        0
    } else {
        1
    };
    let n_axis = info.normal[axis];
    if n_axis == 0.0 {
        return None;
    }
    let (mut num, mut den) = (0.0, 0.0);
    for anchor in anchors {
        let tangent = acute(direction, anchor.tangent);
        let psi = width_weight(
            mean,
            anchor.source_width,
            tangent,
            acute(anchor.tangent, direction),
            size_px,
        );
        let w = anchor.length * psi;
        num += w * anchor.rel;
        den += w;
    }
    if den == 0.0 {
        return None;
    }
    let coupled = mean * (1.0 + num / den);
    let scaled = coupled / n_axis.abs();
    if !scaled.is_finite() {
        return None;
    }
    // Deterministic nearest integer, ties to even (Python round).
    let integer = scaled.round_ties_even() as i64;
    if integer <= 0 {
        return None;
    }
    let mid = &info.stations[info.stations.len() / 2].hit;
    Some(Gate {
        axis,
        integer,
        target: integer as f64 * n_axis.abs(),
        coupled,
        rel: num / den,
        w_src: info.normal[0] * (mid.qb[0] - mid.qa[0]) + info.normal[1] * (mid.qb[1] - mid.qa[1]),
        fa: mid.sa,
        fb: mid.sb,
    })
}

/// Certified existing border portion prepared for the attached solve.
struct AttachedPair {
    id: String,
    a: geometry::Portion,
    b: geometry::Portion,
    normal: [f64; 2],
    stations: Vec<geometry::Station>,
    src_widths: Vec<f64>,
    arc: f64,
    gate: Gate,
}

/// Certified existing border portions, restricted to curve attachments.
///
/// Single-contour line/quad outlines only; anything else reports an
/// unsupported contour. Only pairs touching a curve attachment survive;
/// rectilinear sides never reach the solver.
fn recognize(
    analysis: &super::SourceAnalysis<'_>,
    fitted_oncurve: &[[f64; 2]],
    size_px: f64,
    anchors: &[super::Anchor],
) -> (Vec<AttachedPair>, Vec<String>) {
    let parsed = analysis.parsed().expect("validated source");
    let single = parsed.contours.len() == 1
        && parsed
            .contours
            .iter()
            .flatten()
            .all(|s| s.is_line() || matches!(s, geometry::Segment::Quad { .. }));
    if !single {
        return (Vec::new(), vec!["unsupported-contour".to_string()]);
    }
    let mut curved: HashSet<usize> = HashSet::new();
    for contour in &parsed.contours {
        for seg in contour {
            if let geometry::Segment::Quad { a, b, .. } = *seg {
                curved.insert(a);
                curved.insert(b);
            }
        }
    }
    if curved.is_empty() {
        return (Vec::new(), vec!["no-curve-attachments".to_string()]);
    }
    let (portions, curve_boxes, loops, flats) = analysis.visible();
    let (pairs, _) = analysis.pairs();
    let borders = geometry::visible_borders(&portions);
    let exact = geometry::curve_controls(parsed);
    let mut prepared = Vec::new();
    let mut skipped = Vec::new();
    for pair in pairs {
        let (a, b) = (&pair.a, &pair.b);
        if geometry::axis_of(a.p0, a.p1).is_some() || geometry::axis_of(b.p0, b.p1).is_some() {
            continue;
        }
        if ![a.i0, a.i1, b.i0, b.i1].iter().any(|v| curved.contains(v)) {
            continue;
        }
        let info = match geometry::prepare_pair(
            pair,
            &borders,
            &loops,
            &loops,
            &flats,
            &curve_boxes,
            fitted_oncurve,
            &exact,
        ) {
            Ok(info) => info,
            Err(reason) => {
                skipped.push(reason.to_string());
                continue;
            }
        };
        let Some(cor) =
            super::intervals::corridor([info.a.p0, info.a.p1], [info.b.p0, info.b.p1]).map(|c| c.d)
        else {
            skipped.push("no-corridor".to_string());
            continue;
        };
        let Some(gate) = grid_target(&info, cor, anchors, size_px) else {
            skipped.push("no-grid-target".to_string());
            continue;
        };
        prepared.push(AttachedPair {
            id: info.id,
            a: info.a,
            b: info.b,
            normal: info.normal,
            stations: info.stations,
            src_widths: info.src_widths,
            arc: info.arc,
            gate,
        });
    }
    (prepared, skipped)
}

/// Quadratic form of the Hobby (31)-(33) + (2),(3) construction.
///
/// Native port of the curved-width quad shape rows: quadratic Bernstein
/// weights with derivative weights (-2(1-t), 2(1-t)-2t, 2t). Curve-position
/// rows hold the outline, curve-stretch/bend rows hold the distortion, all
/// with zero constants on the source outline. Groups map onto the
/// maintained position/stretch/bend rows; the attached solve reads every
/// system row uniformly as objective, so the grouping is evidence only.
fn add_quad_shape(system: &mut super::System, ctrl: [usize; 3]) {
    // Quadratic Bernstein weights with derivative weights
    // (-2(1-t), 2(1-t)-2t, 2t), sixteen stations per curve.
    let controls = [
        system.points[ctrl[0]],
        system.points[ctrl[1]],
        system.points[ctrl[2]],
    ];
    let height = system.height;
    for j in 0..16 {
        let t = (j as f64 + 0.5) / 16.0;
        let basis = [(1.0 - t).powi(2), 2.0 * t * (1.0 - t), t.powi(2)];
        let deriv = [-2.0 * (1.0 - t), 2.0 * (1.0 - t) - 2.0 * t, 2.0 * t];
        let mut dpt = [0.0, 0.0];
        for (w, p) in deriv.iter().zip(controls.iter()) {
            dpt[0] += w * p[0];
            dpt[1] += w * p[1];
        }
        let speed = dpt[0].hypot(dpt[1]);
        if !(speed > 0.0) {
            continue;
        }
        let normal = [dpt[1] / speed, -dpt[0] / speed];
        let tangent = [dpt[0] / speed, dpt[1] / speed];
        let normal_row = |weights: [f64; 3]| {
            let mut out = vec![0.0; 2 * system.points.len()];
            for (w, i) in weights.iter().zip(ctrl.iter()) {
                out[2 * *i] += w * normal[0];
                out[2 * *i + 1] += w * normal[1];
            }
            out
        };
        let tangent_row = |weights: [f64; 3]| {
            let mut out = vec![0.0; 2 * system.points.len()];
            for (w, i) in weights.iter().zip(ctrl.iter()) {
                out[2 * *i] += w * tangent[0];
                out[2 * *i + 1] += w * tangent[1];
            }
            out
        };
        let arc = speed / 16.0;
        let pos_scale = (1000.0 / height.powi(3) * arc).sqrt();
        let shape_scale = (25.0 / height * arc).sqrt() / speed;
        let pos: Vec<f64> = normal_row(basis).iter().map(|x| x * pos_scale).collect();
        let stretch: Vec<f64> = tangent_row(deriv).iter().map(|x| x * shape_scale).collect();
        let bend: Vec<f64> = normal_row(deriv).iter().map(|x| x * shape_scale).collect();
        system.rows.push((super::RowGroup::Position, pos, 0.0));
        system.rows.push((super::RowGroup::Stretch, stretch, 0.0));
        system.rows.push((super::RowGroup::Bend, bend, 0.0));
    }
}

/// Retained joint leg for the post-rounding continuity check.
#[derive(Clone, Copy)]
struct JointCheck {
    j: usize,
    iv: usize,
    ov: usize,
    constrained: bool,
    smooth: bool,
}

/// Far endpoint or off-curve control adjacent to the joint, global index.
///
/// Mirrors the sibling worker's leg rule exactly: a line leg resolves to its
/// non-joint endpoint, a quad leg to its off-curve control.
fn leg_far(prev: scf::SegRef, seg: scf::SegRef) -> (usize, usize) {
    let iv = match prev {
        scf::SegRef::Line { a, .. } => a,
        scf::SegRef::Quad { off, .. } => off,
    };
    let ov = match seg {
        scf::SegRef::Line { b, .. } => b,
        scf::SegRef::Quad { off, .. } => off,
    };
    (iv, ov)
}

/// Joint cross and legs at one coordinate set.
///
/// Local port of the smooth-curve cross check: cross(J-I, O-J) with the
/// incoming and outgoing legs. Kept beside the solver-owned rows until the
/// sibling worker exposes its private cross helper for shared use.
fn cross_of(coords: &[[f64; 2]], j: usize, iv: usize, ov: usize) -> (f64, [f64; 2], [f64; 2]) {
    let (j_pt, i_pt, o_pt) = (coords[j], coords[iv], coords[ov]);
    let li = [j_pt[0] - i_pt[0], j_pt[1] - i_pt[1]];
    let lo = [o_pt[0] - j_pt[0], o_pt[1] - j_pt[1]];
    (li[0] * lo[1] - li[1] * lo[0], li, lo)
}

/// Nearest-26.6 half-quantum error per moved coordinate.
const ROUND_HALF: f64 = 1.0 / 128.0;

/// 26.6 rounding bound on joint-cross perturbation.
///
/// Only moved coordinates err, at most 1/128 per axis; unmoved legs
/// contribute zero. The bilinear cross gains first-order leg-error terms
/// plus the second-order product. Each leg's error partners with the OTHER
/// leg's components (incoming error with the outgoing leg and vice versa):
/// cross(li + ei, lo + eo) - cross(li, lo) expands to ei x lo + li x eo at
/// first order. Local port of the smooth-curve bound, kept beside
/// `cross_of` until shared exposure lands; the sibling worker's copy needs
/// the same partner correction from its owner.
fn quant_cross_bound(leg_in: [f64; 2], leg_out: [f64; 2], moved: [(bool, bool); 3]) -> f64 {
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

/// Weld-aware X-column reduction of a full-coordinate row.
///
/// Duplicate endpoints alias to their canonical control before selecting the
/// solved X columns, in duplicate-index order for determinism.
fn reduce_row(row: &[f64], weld: &HashMap<usize, usize>, cols: &[usize]) -> Vec<f64> {
    let mut full = row.to_vec();
    let mut dups: Vec<usize> = weld.keys().copied().collect();
    dups.sort();
    for d in dups {
        let c = weld[&d];
        full[2 * c] += full[2 * d];
    }
    cols.iter().map(|v| full[2 * v]).collect()
}

/// One bounded solve from the original upstream outline.
///
/// Hersch fixed-direction constraints (parallel borders plus the integer
/// separation target) enter as hard rows; Hobby (17) relative-width rows and
/// the Hobby (1)-(3)/section-6 shape rows enter as soft objective. Variables
/// are upstream X displacements; source directions stay frozen while the
/// distortion residual vanishes at the upstream fit. Unsupported results
/// abstain with the exact upstream commands.
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
        &super::SourceAnalysis::new(source),
    )
}

pub(super) fn fit_with_analysis(
    source: &[FittedCommand],
    upstream: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
    analysis: &super::SourceAnalysis<'_>,
) -> Result<FitResult, Error> {
    if native_axes[0] {
        return Ok(abstain(
            upstream,
            "native-X-owned",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    if !(size_px.is_finite() && size_px > 0.0) {
        return Err(fail("attached width requires finite positive size"));
    }
    if !geometry::check_correspondence(source, upstream) {
        return Ok(abstain(
            upstream,
            "no-correspondence",
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
    if source.len() > MAX_COMMANDS || upstream.len() > MAX_COMMANDS {
        return Ok(abstain(
            upstream,
            "oversize-outline",
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
    let no = parsed.oncurve.len();
    let base: Vec<[f64; 2]> = parsed
        .oncurve
        .iter()
        .chain(parsed.offcurve.iter())
        .copied()
        .collect();
    let up: Vec<[f64; 2]> = fitted
        .oncurve
        .iter()
        .chain(fitted.offcurve.iter())
        .copied()
        .collect();
    if base.len() != up.len() {
        return Ok(abstain(
            upstream,
            "malformed-coordinates",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    if !base
        .iter()
        .flatten()
        .chain(up.iter().flatten())
        .all(|v| v.is_finite())
    {
        return Ok(abstain(
            upstream,
            "malformed-coordinates",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    // 26.6-grid input, exactly representable in f32 coordinates.
    if !base
        .iter()
        .chain(up.iter())
        .flatten()
        .all(|v| *v * 64.0 == (*v * 64.0).round())
    {
        return Ok(abstain(
            upstream,
            "non-26.6-input",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    let (prepared, skipped) = recognize(analysis, &fitted.oncurve, size_px, &reference.anchors);
    if prepared.is_empty() {
        return Ok(abstain(
            upstream,
            "no-attached-diagonals",
            serde_json::json!({"size_px": size_px, "skipped": skipped}),
        ));
    }
    let weld = scf::weld_map(&parsed);
    if weld != scf::weld_map(&fitted) {
        return Ok(abstain(
            upstream,
            "weld-mismatch",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    for (d, c) in &weld {
        if up[*d] != up[*c] {
            return Ok(abstain(
                upstream,
                "weld-mismatch",
                serde_json::json!({"size_px": size_px}),
            ));
        }
    }
    let mut involved: HashSet<usize> = prepared
        .iter()
        .flat_map(|p| [p.a.i0, p.a.i1, p.b.i0, p.b.i1])
        .collect();
    // Global quad control indices into on/offcurve; the contour gate above
    // admits lines and quads only, so longer chains never occur here.
    let mut curves_idx: Vec<Vec<usize>> = Vec::new();
    for contour in &parsed.contours {
        for seg in contour {
            match *seg {
                geometry::Segment::Quad { c, a, b } => curves_idx.push(vec![a, no + c, b]),
                geometry::Segment::Cubic { c1, c2, a, b } => {
                    curves_idx.push(vec![a, no + c1, no + c2, b])
                }
                _ => {}
            }
        }
    }
    // A shared curve chain carries its controls together; a remote straight
    // anchor is not released merely because an incident edge is regularized.
    loop {
        let mut grown = involved.clone();
        for c in &curves_idx {
            if c.iter().any(|i| involved.contains(i)) {
                grown.extend(c.iter().copied());
            }
        }
        let snapshot: Vec<usize> = grown.iter().copied().collect();
        for i in snapshot {
            grown.insert(*weld.get(&i).unwrap_or(&i));
        }
        if grown == involved {
            break;
        }
        involved = grown;
    }
    let mut upright: HashSet<usize> = HashSet::new();
    for contour in &parsed.contours {
        for seg in contour {
            if let geometry::Segment::Line { a, b } = *seg {
                if base[a][0] == base[b][0] && base[a][1] != base[b][1] {
                    upright.insert(a);
                    upright.insert(b);
                }
            }
        }
    }
    for v in upright.clone() {
        upright.insert(*weld.get(&v).unwrap_or(&v));
    }
    let mut cols: Vec<usize> = involved
        .iter()
        .filter(|v| !upright.contains(v) && !weld.contains_key(v))
        .copied()
        .collect();
    cols.sort();
    if cols.is_empty() {
        return Ok(abstain(
            upstream,
            "no-free-controls",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    let mut system = super::System::new(base.clone(), size_px);
    for c in &curves_idx {
        if c.len() == 3 && c.iter().any(|i| involved.contains(i)) {
            add_quad_shape(&mut system, [c[0], c[1], c[2]]);
        }
    }
    for contour in &parsed.contours {
        for seg in contour {
            if let geometry::Segment::Line { a, b } = *seg {
                if (involved.contains(&a) || involved.contains(&b)) && base[a] != base[b] {
                    let _ = system.edge(a, b);
                }
            }
        }
    }
    // Variables are upstream displacements. Source directions remain frozen,
    // while the distortion residual vanishes at the upstream fit.
    let mut obj_rows: Vec<Vec<f64>> = system.rows.iter().map(|(_, row, _)| row.clone()).collect();
    let mut obj_const: Vec<f64> = vec![0.0; obj_rows.len()];
    let gaps: Vec<f64> = base
        .iter()
        .zip(up.iter())
        .flat_map(|(b, u)| [u[0] - b[0], u[1] - b[1]])
        .collect();
    let up_flat: Vec<f64> = up.iter().flat_map(|p| [p[0], p[1]]).collect();
    struct HardRow {
        kind: &'static str,
        row: Vec<f64>,
        constant: f64,
    }
    let mut hard: Vec<HardRow> = Vec::new();
    for info in &prepared {
        let n = info.normal;
        for edge in [&info.a, &info.b] {
            let row = system.projected(
                &super::Sample::affine(edge.i0, 1.0 - edge.t1, edge.i1, edge.t1),
                n,
                Some(&super::Sample::affine(
                    edge.i0,
                    1.0 - edge.t0,
                    edge.i1,
                    edge.t0,
                )),
            );
            hard.push(HardRow {
                kind: "parallel",
                constant: dot(&row, &up_flat),
                row,
            });
        }
        let ta = info.a.t0 + (info.a.t1 - info.a.t0) * info.gate.fa;
        let tb = info.b.t0 + (info.b.t1 - info.b.t0) * info.gate.fb;
        let row = system.projected(
            &super::Sample::affine(info.b.i0, 1.0 - tb, info.b.i1, tb),
            n,
            Some(&super::Sample::affine(info.a.i0, 1.0 - ta, info.a.i1, ta)),
        );
        hard.push(HardRow {
            kind: "separation",
            constant: dot(&row, &up_flat) - info.gate.target,
            row,
        });
        for st in &info.stations {
            let ta = info.a.t0 + (info.a.t1 - info.a.t0) * st.hit.sa;
            let tb = info.b.t0 + (info.b.t1 - info.b.t0) * st.hit.sb;
            let (error, width, tangent) = match system.pair(
                &super::Sample::affine(info.a.i0, 1.0 - ta, info.a.i1, ta),
                &super::Sample::affine(info.b.i0, 1.0 - tb, info.b.i1, tb),
                info.arc,
                st.hit.center,
            ) {
                Ok(v) => v,
                Err(()) => {
                    return Ok(abstain(
                        upstream,
                        "unsupported-input",
                        serde_json::json!({"size_px": size_px}),
                    ));
                }
            };
            for anchor in &reference.anchors {
                let tangent = acute(tangent, anchor.tangent);
                let weight = info.arc
                    * anchor.length
                    * width_weight(width, anchor.source_width, tangent, anchor.tangent, size_px);
                let scale = weight.sqrt();
                obj_rows.push(error.iter().map(|x| x * scale).collect());
                obj_const.push((dot(&error, &gaps) + anchor.rel) * scale);
            }
        }
    }
    // Hersch's border rotation changes angular line-line corners. Their
    // orientation is checked below; curve joins and collinear subdivision
    // joints retain exact tangent/cross constraints.
    let joints_map = scf::joints(&parsed);
    let mut ordered_j: Vec<usize> = joints_map.keys().copied().collect();
    ordered_j.sort();
    let mut joint_checks: Vec<JointCheck> = Vec::new();
    for j in ordered_j {
        let mut occs = joints_map[&j].clone();
        occs.sort_by_key(|o| leg_far(o.prev, o.seg));
        for occ in &occs {
            let (iv, ov) = leg_far(occ.prev, occ.seg);
            if ![j, iv, ov].iter().any(|v| involved.contains(v)) {
                continue;
            }
            if occ.degenerate {
                return Ok(abstain(
                    upstream,
                    "degenerate-joint",
                    serde_json::json!({"size_px": size_px}),
                ));
            }
            let curved_join = matches!(occ.prev, scf::SegRef::Quad { .. })
                || matches!(occ.seg, scf::SegRef::Quad { .. });
            // Cubic joins never reach here: the contour gate admits lines and
            // quads only, so every joint leg is a line or a quad control.
            let constrained = curved_join || occ.smooth;
            if constrained {
                match scf::g1_row(&up, j, occ.prev, occ.seg, size_px, occ.smooth) {
                    Some((row, constant)) => hard.push(HardRow {
                        kind: "joint",
                        row,
                        constant,
                    }),
                    // A degenerate leg cannot linearize: the joint keeps the
                    // upstream defect instead of constraining it.
                    None => {
                        return Ok(abstain(
                            upstream,
                            "degenerate-leg",
                            serde_json::json!({"size_px": size_px}),
                        ));
                    }
                }
            }
            joint_checks.push(JointCheck {
                j,
                iv,
                ov,
                constrained,
                smooth: occ.smooth,
            });
        }
    }
    let mat: Vec<Vec<f64>> = obj_rows
        .iter()
        .map(|r| reduce_row(r, &weld, &cols))
        .collect();
    let rhs: Vec<f64> = obj_const.iter().map(|c| -c).collect();
    let g_full: Vec<Vec<f64>> = hard
        .iter()
        .map(|h| reduce_row(&h.row, &weld, &cols))
        .collect();
    let h_full: Vec<f64> = hard.iter().map(|h| -h.constant).collect();
    // Redundant equality rows fail closed here with the fixed-constraint
    // reason; the solver repeats the same gate on its normalized rows.
    let mut g_active: Vec<Vec<f64>> = Vec::new();
    let mut h_active: Vec<f64> = Vec::new();
    for (row, rhs) in g_full.iter().zip(h_full.iter()) {
        if row.iter().all(|v| *v == 0.0) {
            if rhs.abs() > 1e-9 {
                return Ok(abstain(
                    upstream,
                    "fixed-constraints-incompatible",
                    serde_json::json!({"size_px": size_px}),
                ));
            }
            continue;
        }
        g_active.push(row.clone());
        h_active.push(*rhs);
    }
    let radius = prepared
        .iter()
        .map(|p| p.src_widths.iter().cloned().fold(f64::INFINITY, f64::min) / 2.0)
        .fold(f64::INFINITY, f64::min);
    let bound = radius - HEADROOM;
    if !(bound > 0.0) {
        return Ok(abstain(
            upstream,
            "movement-budget-empty",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    // Hersch section 2's quadratic derivatives: the signed curvature is
    // cross(C-P0,P1-C), linear in X when Y is fixed. The four source-leg
    // dot products certify forward tangents over the entire interval. One
    // 26.6 product quantum plus the exact X-rounding reserve makes each
    // strict sign representable without a curvature threshold.
    let mut ineq_rows: Vec<Vec<f64>> = Vec::new();
    let mut ineq_lower: Vec<f64> = Vec::new();
    for c in &curves_idx {
        if c.len() != 3 || !c.iter().any(|i| involved.contains(i)) {
            continue;
        }
        let (p0, ctrl, p1) = (c[0], c[1], c[2]);
        let su = [base[ctrl][0] - base[p0][0], base[ctrl][1] - base[p0][1]];
        let sv = [base[p1][0] - base[ctrl][0], base[p1][1] - base[ctrl][1]];
        let source_cross = su[0] * sv[1] - su[1] * sv[0];
        if source_cross == 0.0 {
            return Ok(abstain(
                upstream,
                "source-degenerate-curvature",
                serde_json::json!({"size_px": size_px}),
            ));
        }
        let sign = if source_cross > 0.0 { 1.0 } else { -1.0 };
        let mut row = vec![0.0; 2 * base.len()];
        row[2 * p0] = sign * (up[ctrl][1] - up[p1][1]);
        row[2 * ctrl] = sign * (up[p1][1] - up[p0][1]);
        row[2 * p1] = sign * (up[p0][1] - up[ctrl][1]);
        let red = reduce_row(&row, &weld, &cols);
        let reserve = red.iter().map(|v| v.abs()).sum::<f64>() / 128.0 + 1.0 / 4096.0;
        ineq_rows.push(red);
        ineq_lower.push(reserve - dot(&row, &up_flat));
        for (i, j) in [(p0, ctrl), (ctrl, p1)] {
            for leg in [su, sv] {
                let mut row = vec![0.0; 2 * base.len()];
                row[2 * j] = leg[0];
                row[2 * i] = -leg[0];
                let value = (up[j][0] - up[i][0]) * leg[0] + (up[j][1] - up[i][1]) * leg[1];
                let red = reduce_row(&row, &weld, &cols);
                let reserve = red.iter().map(|v| v.abs()).sum::<f64>() / 128.0 + 1.0 / 4096.0;
                ineq_rows.push(red);
                ineq_lower.push(reserve - value);
            }
        }
    }
    let Some((delta, qp_info)) = qp::convex_qp(
        &mat,
        &rhs,
        &g_active,
        &h_active,
        &ineq_rows,
        &ineq_lower,
        bound,
    ) else {
        return Ok(abstain(
            upstream,
            "constraints-incompatible",
            serde_json::json!({"size_px": size_px}),
        ));
    };
    let mut raw = up.clone();
    for (v, d) in cols.iter().zip(delta.iter()) {
        raw[*v][0] += d;
    }
    let mut weld_order: Vec<usize> = weld.keys().copied().collect();
    weld_order.sort();
    for d in &weld_order {
        raw[*d] = raw[weld[d]];
    }
    let mut cand = raw.clone();
    for v in &cols {
        cand[*v][0] = geometry::round_26_6(cand[*v][0]);
    }
    for d in &weld_order {
        cand[*d] = cand[weld[d]];
    }
    let movement = cand
        .iter()
        .zip(up.iter())
        .map(|(c, u)| (c[0] - u[0]).hypot(c[1] - u[1]))
        .fold(0.0, f64::max);
    if movement > radius {
        return Ok(abstain(
            upstream,
            "rounded-movement-budget",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    let raw_flat: Vec<f64> = raw.iter().flat_map(|p| [p[0], p[1]]).collect();
    let cand_flat: Vec<f64> = cand.iter().flat_map(|p| [p[0], p[1]]).collect();
    let mut hard_checks = Vec::new();
    for h in &hard {
        let raw_error = (dot(&h.row, &raw_flat) - dot(&h.row, &up_flat) + h.constant).abs();
        let error = (dot(&h.row, &cand_flat) - dot(&h.row, &up_flat) + h.constant).abs();
        let allowance = (0..base.len())
            .filter(|v| raw[*v][0] != up[*v][0])
            .map(|v| h.row[2 * v].abs() / 128.0)
            .sum::<f64>();
        let ok = raw_error <= 1e-8 * (1.0 + h.constant.abs()) && error <= allowance + 1e-9;
        hard_checks.push(serde_json::json!({
            "kind": h.kind, "raw_error": raw_error, "rounded_error": error,
            "allowance": allowance, "ok": ok,
        }));
        if !ok {
            return Ok(abstain(
                upstream,
                "rounded-hard-constraint",
                serde_json::json!({"size_px": size_px, "hard_checks": hard_checks}),
            ));
        }
    }
    let mut continuity = Vec::new();
    for jc in &joint_checks {
        let (raw_cross, li, lo) = cross_of(&raw, jc.j, jc.iv, jc.ov);
        let (old_cross, old_li, old_lo) = cross_of(&up, jc.j, jc.iv, jc.ov);
        let (cross, new_li, new_lo) = cross_of(&cand, jc.j, jc.iv, jc.ov);
        let (source_cross, _, _) = cross_of(&base, jc.j, jc.iv, jc.ov);
        let target = if jc.smooth { 0.0 } else { old_cross };
        let moved_flags = [
            (raw[jc.iv][0] != up[jc.iv][0], false),
            (raw[jc.j][0] != up[jc.j][0], false),
            (raw[jc.ov][0] != up[jc.ov][0], false),
        ];
        let allowance = quant_cross_bound(li, lo, moved_flags);
        let legs_live = new_li[0].hypot(new_li[1]) > 0.0 && new_lo[0].hypot(new_lo[1]) > 0.0;
        let mut ok = legs_live;
        if jc.constrained {
            ok &= (raw_cross - target).abs() <= 1e-8 * (1.0 + target.abs())
                && (cross - target).abs() <= allowance + 1e-9;
            ok &= (new_li[0] * old_li[0] + new_li[1] * old_li[1]) > 0.0
                && (new_lo[0] * old_lo[0] + new_lo[1] * old_lo[1]) > 0.0;
            if jc.smooth {
                ok &= (new_li[0] * new_lo[0] + new_li[1] * new_lo[1]) > 0.0;
            }
        } else if source_cross != 0.0 {
            ok &= cross * source_cross > 0.0;
        }
        continuity.push(serde_json::json!({
            "joint": jc.j, "constrained": jc.constrained, "smooth": jc.smooth,
            "raw_cross": raw_cross, "raw_target": if jc.constrained { Some(target) } else { None },
            "source_cross": source_cross, "cross_up": old_cross,
            "cross_cand": cross, "allowed": allowance, "ok": ok,
        }));

        if !ok {
            return Ok(abstain(
                upstream,
                "joint-continuity",
                serde_json::json!({"size_px": size_px, "continuity": continuity}),
            ));
        }
    }
    let moved: HashSet<usize> = (0..base.len()).filter(|i| cand[*i] != up[*i]).collect();
    for c in &curves_idx {
        if c.len() != 3 || !c.iter().any(|i| moved.contains(i)) {
            continue;
        }
        let src_t = [base[c[0]], base[c[1]], base[c[2]]];
        let cand_t = [cand[c[0]], cand[c[1]], cand[c[2]]];
        if let Err(reason) = scf::quad_interval_ok(&src_t, &cand_t) {
            return Ok(abstain(
                upstream,
                &format!("curve-{reason}"),
                serde_json::json!({
                    "size_px": size_px,
                    "curve_indices": c,
                    "source_controls": src_t,
                    "upstream_controls": [up[c[0]], up[c[1]], up[c[2]]],
                    "candidate_controls": cand_t,
                }),
            ));
        }
    }
    // Delivery clearance is the shared smooth-curve gate with no station
    // pairs and no paired curves, exactly as the original calls it: station
    // disks only exist for paired borders, and swept/hull separation carries
    // the incident-junction exemptions. No extra disk or sweep guard here.
    if let Err(reason) = scf::clearance_ok(&[], &cand, &parsed, &moved, &up, &HashSet::new()) {
        return Ok(abstain(
            upstream,
            &format!("clearance-{reason}"),
            serde_json::json!({"size_px": size_px}),
        ));
    }
    let commands = scf::emit(upstream, &cand, no);
    let topology_ok = match geometry::parse_commands(&commands) {
        Ok(cand_parsed) => curves::compare_substituted(&parsed, &fitted, &cand_parsed),
        Err(()) => false,
    };
    if !topology_ok {
        return Ok(abstain(
            upstream,
            "topology",
            serde_json::json!({"size_px": size_px, "topology": {"ok": false}}),
        ));
    }
    if commands == upstream {
        return Ok(abstain(
            upstream,
            "no-movement",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    let mut upright_sorted: Vec<usize> = upright.iter().copied().collect();
    upright_sorted.sort();
    Ok(FitResult {
        commands,
        applied: true,
        reason: "attached-grid".to_string(),
        diagnostics: serde_json::json!({
            "native_axes": [native_axes[0], native_axes[1]],
            "retained_upstream_axes": [native_axes[0], true],
            "upright_x_pins": upright_sorted,
            "qp": {"iterations": qp_info.iterations, "equality_error": qp_info.equality_error,
                    "stationarity_error": qp_info.stationarity_error,
                    "inequality_slack": qp_info.inequality_slack, "active": qp_info.active},
            "bound": bound,
            "radius": radius,
            "movement": movement,
            "hard_checks": hard_checks,
            "continuity": continuity,
            "topology": {"ok": true},
            "pairs": prepared.iter().map(|p| serde_json::json!({
                "id": p.id,
                "source_width": p.src_widths.iter().sum::<f64>() / p.src_widths.len() as f64,
                "normal": p.normal,
                "gate": {"axis": if p.gate.axis == 0 { "x" } else { "y" },
                         "integer": p.gate.integer, "target": p.gate.target,
                         "coupled": p.gate.coupled, "rel": p.gate.rel,
                         "w_src": p.gate.w_src, "fa": p.gate.fa, "fb": p.gate.fb},
            })).collect::<Vec<_>>(),
            "skipped": skipped,
            "size_px": size_px,
        }),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Bilinear partner guard: single incoming X move, unequal leg heights.
    ///
    /// Only vertex 0 moves in x, so the x error e=[h,0] partners the
    /// OUTGOING leg (e x lo), never the incoming leg. With |lo.y|=4 and
    /// |li.y|=1 the swapped-partner formula would return h*1 instead of h*4.
    #[test]
    fn quant_cross_bound_partners_incoming_error_with_outgoing_leg() {
        let leg_in = [3.0, 1.0];
        let leg_out = [0.5, 4.0];
        let moved = [(true, false), (false, false), (false, false)];
        let got = quant_cross_bound(leg_in, leg_out, moved);
        assert_eq!(got, ROUND_HALF * leg_out[1].abs());
    }
}
