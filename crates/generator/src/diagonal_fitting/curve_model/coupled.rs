//! Coupled whole-outline width solve (Hobby 3.1, 3.2, 3.6, 6; Hersch 2).
//!
//! Hobby supplies integrated shape distortion, normal widths and shared curve
//! variables; Hersch supplies Bernstein and endpoint-derivative identities.
//! Project adaptations couple all X controls and use hard white-gap equalities
//! instead of finite width penalties.
//!
//! Inputs are one closed quadratic contour with exactly f32-representable,
//! jointly canonicalized source points. Retain upstream Y and upright-edge X,
//! share closure aliases, and use the default unbounded ink-pair set. Exterior
//! straight-site gaps hold exactly and recheck against true curves after fitting.
//! Unsupported geometry or incompatible constraints retain the upstream outline.

use super::super::exact::Exact as BigRational;
use super::super::{
    abstain, curves, geometry, intervals, reference_meta, FitResult, Reference, MAX_COMMANDS,
};
use super::{
    assemble, degenerate_triples, g1_row, hard_solve, hard_solve_bounded_phase1, joints,
    leg_vertex, prefix_diag, qp_json, recognize, recognize_parsed_depths,
    require_finite_positive_size, restricted_matrix, rounding_reserve, run_prefixes, weld_map,
    with_effectibility, RowKind, WhiteSpec, DEPTHS,
};
use crate::{probe::FittedCommand, Error};
use std::collections::{HashMap, HashSet};

struct StraightEdge {
    ci: usize,
    si: usize,
    i0: usize,
    i1: usize,
    p0: [f64; 2],
    p1: [f64; 2],
}

/// Ignore zero-length borders, which carry no corridor.
fn straight_edges(parsed: &geometry::Parsed) -> Vec<StraightEdge> {
    let mut edges = Vec::new();
    for (ci, contour) in parsed.contours.iter().enumerate() {
        for (si, seg) in contour.iter().enumerate() {
            if let geometry::Segment::Line { a, b } = *seg {
                let (p0, p1) = (parsed.oncurve[a], parsed.oncurve[b]);
                if (p1[0] - p0[0]).hypot(p1[1] - p0[1]) > 0.0 {
                    edges.push(StraightEdge {
                        ci,
                        si,
                        i0: a,
                        i1: b,
                        p0,
                        p1,
                    });
                }
            }
        }
    }
    edges
}

/// Winding on certified substitution rings; zero is exterior.
fn winding_number(pt: [f64; 2], loops: &[Vec<[f64; 2]>]) -> i64 {
    let (x, y) = (pt[0], pt[1]);
    let mut total = 0i64;
    for lp in loops {
        if lp.is_empty() {
            continue;
        }
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

/// Check disk clearance against every true line or quadratic using exact arithmetic.
fn true_disk_clear(center: [f64; 2], r2: &BigRational, parsed: &geometry::Parsed) -> bool {
    for contour in &parsed.contours {
        for seg in contour {
            let ctrls: Vec<[f64; 2]> = match *seg {
                geometry::Segment::Line { a, b } => vec![parsed.oncurve[a], parsed.oncurve[b]],
                geometry::Segment::Quad { c, a, b } => {
                    vec![parsed.oncurve[a], parsed.offcurve[c], parsed.oncurve[b]]
                }
                geometry::Segment::Cubic { .. } => return false,
            };
            if !curves::source_disk_clear(center, r2, &ctrls) {
                return false;
            }
        }
    }
    true
}

/// Certified medial contact of one straight pair. The contact radius is
/// consumed as an exact rational square inside `white_hit`; the center
/// stays as the contact identity for the exterior test.
struct WhiteHit {
    #[cfg(test)]
    center: [f64; 2],
    width: f64,
    sa: f64,
    sb: f64,
    qa: [f64; 2],
    qb: [f64; 2],
}

/// Hobby 3.2 exterior empty-disk feature on straight sites. Dominance alone
/// does not establish exteriority: require zero winding on the certified
/// substitution and exact clearance from every true source primitive.
fn white_hit(
    parsed: &geometry::Parsed,
    edges: &[StraightEdge],
    ea: usize,
    eb: usize,
    depth: usize,
) -> Option<WhiteHit> {
    let setup =
        intervals::prepare([edges[ea].p0, edges[ea].p1], [edges[eb].p0, edges[eb].p1]).ok()?;
    let set = intervals::CompetitorSet::new(intervals::tagged_borders(
        &edges.iter().map(|e| [e.p0, e.p1]).collect::<Vec<_>>(),
    ));
    let dom = set.dominance_for(&setup, ea, eb, None);
    if dom.status != "ok" || dom.intervals.is_empty() {
        return None;
    }
    let span = dom.intervals.iter().reduce(|best, next| {
        if next.hi - next.lo > best.hi - best.lo {
            next
        } else {
            best
        }
    })?;
    let hit = set
        .contact_for(&setup, (span.lo + span.hi) / 2.0, ea, eb, None)
        .hit?;
    if curves::certify_parsed(parsed, depth).is_err() {
        return None;
    }
    let (_, loops) = super::substitute(parsed, depth);
    if winding_number(hit.center, &loops) != 0 {
        return None;
    }
    // Exact squared radius from the float contact, as the prototype's
    // `Fraction(hit['r']) ** 2`; non-finite input fails closed.
    let r2 = BigRational::from_f64(hit.r).map(|r| &r * &r)?;
    if !true_disk_clear(hit.center, &r2, parsed) {
        return None;
    }
    Some(WhiteHit {
        #[cfg(test)]
        center: hit.center,
        width: hit.width,
        sa: hit.sa,
        sb: hit.sb,
        qa: hit.qa,
        qb: hit.qb,
    })
}

pub(super) struct WhiteFeature {
    a_ci: usize,
    a_si: usize,
    b_ci: usize,
    b_si: usize,
    spec: WhiteSpec,
    source_width: f64,
    depth: usize,
}

/// Curved white sites are unsupported.
fn white_contacts(source: &[FittedCommand]) -> (Vec<WhiteFeature>, Option<String>) {
    let parsed = match geometry::parse_commands(source) {
        Ok(parsed) => parsed,
        Err(()) => return (Vec::new(), Some("malformed-commands".to_string())),
    };
    white_contacts_parsed(&parsed)
}

/// White features on already-parsed source geometry (raw f64 outlines
/// use the same machinery without a command round-trip).
fn white_contacts_parsed(parsed: &geometry::Parsed) -> (Vec<WhiteFeature>, Option<String>) {
    white_contacts_parsed_depths(parsed, &DEPTHS)
}

fn white_contacts_parsed_depths(
    parsed: &geometry::Parsed,
    depths: &[usize],
) -> (Vec<WhiteFeature>, Option<String>) {
    let mut depth = None;
    for candidate in depths {
        if curves::certify_parsed(parsed, *candidate).is_ok() {
            depth = Some(*candidate);
            break;
        }
    }
    let Some(depth) = depth else {
        return (
            Vec::new(),
            Some("uncertified-white-substitution".to_string()),
        );
    };
    let edges = straight_edges(&parsed);
    let mut features = Vec::new();
    for ea in 0..edges.len() {
        for eb in (ea + 1)..edges.len() {
            let Some(hit) = white_hit(&parsed, &edges, ea, eb, depth) else {
                continue;
            };
            let chord = [hit.qa[0] - hit.qb[0], hit.qa[1] - hit.qb[1]];
            let dist = chord[0].hypot(chord[1]);
            if !(dist > 0.0) {
                continue;
            }
            let (a, b) = (&edges[ea], &edges[eb]);
            features.push(WhiteFeature {
                a_ci: a.ci,
                a_si: a.si,
                b_ci: b.ci,
                b_si: b.si,
                spec: WhiteSpec {
                    a0: a.i0,
                    a1: a.i1,
                    ta: hit.sa,
                    b0: b.i0,
                    b1: b.i1,
                    tb: hit.sb,
                    normal: [chord[0] / dist, chord[1] / dist],
                },
                source_width: hit.width,
                depth,
            });
        }
    }
    (features, None)
}

/// Fitted projected gap of one feature at a coordinate set (prototype
/// `_gap`): affine edge samples dotted with the source normal.
fn gap(feature: &WhiteFeature, points: &[[f64; 2]]) -> f64 {
    let s = &feature.spec;
    let pa = [
        (1.0 - s.ta) * points[s.a0][0] + s.ta * points[s.a1][0],
        (1.0 - s.ta) * points[s.a0][1] + s.ta * points[s.a1][1],
    ];
    let pb = [
        (1.0 - s.tb) * points[s.b0][0] + s.tb * points[s.b1][0],
        (1.0 - s.tb) * points[s.b0][1] + s.tb * points[s.b1][1],
    ];
    (pa[0] - pb[0]) * s.normal[0] + (pa[1] - pb[1]) * s.normal[1]
}

fn contour_closed(parsed: &geometry::Parsed) -> bool {
    let Some(contour) = parsed.contours.first() else {
        return false;
    };
    let (Some(first), Some(last)) = (contour.first(), contour.last()) else {
        return false;
    };
    first.endpoints().0 == last.endpoints().1
}

/// Fit canonical outlines with coupled X controls, pinned uprights and hard
/// white-gap constraints. Returned canonical commands remain the scan input.
pub(super) fn fit_coupled(
    source: &[FittedCommand],
    upstream_cmds: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> Result<FitResult, Error> {
    require_finite_positive_size(size_px)?;
    // Only native Y with automatic X is approved for this model.
    if native_axes != [false, true] {
        return Ok(abstain(
            upstream_cmds,
            "native-X-owned-or-invalid",
            serde_json::json!({ "size_px": size_px, "native_axes": native_axes }),
        ));
    }
    if source.len() > MAX_COMMANDS || upstream_cmds.len() > MAX_COMMANDS {
        return Ok(abstain(
            upstream_cmds,
            "oversize-outline",
            serde_json::json!({ "size_px": size_px }),
        ));
    }
    if !geometry::check_correspondence(source, upstream_cmds) {
        return Ok(abstain(
            upstream_cmds,
            "unsupported-correspondence",
            serde_json::json!({ "size_px": size_px }),
        ));
    }
    let (Ok(parsed), Ok(fitted)) = (
        geometry::parse_commands(source),
        geometry::parse_commands(upstream_cmds),
    ) else {
        return Ok(abstain(
            upstream_cmds,
            "malformed-commands",
            serde_json::json!({ "size_px": size_px }),
        ));
    };
    let has_cubic = |p: &geometry::Parsed| {
        p.contours
            .iter()
            .flatten()
            .any(|s| matches!(s, geometry::Segment::Cubic { .. }))
    };
    if parsed.contours.len() != 1
        || fitted.contours.len() != 1
        || has_cubic(&parsed)
        || has_cubic(&fitted)
        || !contour_closed(&parsed)
        || !source.iter().any(|c| matches!(c, FittedCommand::Close))
    {
        return Ok(abstain(
            upstream_cmds,
            "unsupported-correspondence",
            serde_json::json!({ "size_px": size_px }),
        ));
    }
    let up_global: Vec<[f64; 2]> = fitted
        .oncurve
        .iter()
        .chain(fitted.offcurve.iter())
        .copied()
        .collect();
    // Scaling a 26.6 coordinate by 64 is exact in binary.
    if up_global
        .iter()
        .flat_map(|p| [p[0], p[1]])
        .any(|v| v * 64.0 != (v * 64.0).round())
    {
        return Ok(abstain(
            upstream_cmds,
            "upstream-not-26.6",
            serde_json::json!({ "size_px": size_px }),
        ));
    }
    let (features, white_reason) = white_contacts(source);
    if let Some(reason) = white_reason {
        return Ok(abstain(
            upstream_cmds,
            &reason,
            serde_json::json!({ "size_px": size_px }),
        ));
    }
    if features.is_empty() {
        return Ok(abstain(
            upstream_cmds,
            "no-certified-straight-white-feature",
            serde_json::json!({ "size_px": size_px }),
        ));
    }
    // Use the default mode's unbounded ink-pair set.
    let (pairs, recognition) = recognize(source, f64::INFINITY);
    if pairs.is_empty() {
        return Ok(abstain(
            upstream_cmds,
            "no-certified-pairs",
            serde_json::json!({
                "size_px": size_px,
                "recognition": recognition,
                "native_axes": native_axes,
            }),
        ));
    }
    if reference.anchors.is_empty() {
        return Ok(abstain(
            upstream_cmds,
            "no-reference-anchors",
            serde_json::json!({ "size_px": size_px, "recognition": recognition }),
        ));
    }
    let weld = weld_map(&parsed);
    let up_weld = weld_map(&fitted);
    if weld != up_weld {
        return Ok(abstain(
            upstream_cmds,
            "weld-mismatch",
            serde_json::json!({ "size_px": size_px }),
        ));
    }
    for (dup, canon) in &weld {
        if up_global[*dup] != up_global[*canon] {
            return Ok(abstain(
                upstream_cmds,
                "weld-mismatch",
                serde_json::json!({ "size_px": size_px }),
            ));
        }
    }
    // Upright edges retain fitted X; weld aliases pin through their canonical vertex.
    let mut fixed_x = HashSet::new();
    for edge in straight_edges(&parsed) {
        if edge.p0[0] == edge.p1[0] {
            for v in [edge.i0, edge.i1] {
                fixed_x.insert(weld.get(&v).copied().unwrap_or(v));
            }
        }
    }
    let owned = vec![1usize];
    let frozen: HashSet<usize> = weld.keys().copied().collect();
    let specs: Vec<WhiteSpec> = features.iter().map(|f| f.spec.clone()).collect();
    let ctx = match assemble(
        &parsed, &up_global, &pairs, reference, size_px, &owned, &frozen, true, &fixed_x, true,
        &specs, true,
    ) {
        Ok(ctx) => ctx,
        Err(reason) => {
            return Ok(abstain(
                upstream_cmds,
                &reason,
                serde_json::json!({ "size_px": size_px, "recognition": recognition }),
            ));
        }
    };
    let (mat, rhs, kinds) = restricted_matrix(&ctx, &weld);
    let (sol, peak, qp) = match hard_solve(&mat, &rhs, &kinds, ctx.bound, ctx.cols.len()) {
        Ok(done) => done,
        Err(reason) => {
            return Ok(abstain(
                upstream_cmds,
                &reason,
                serde_json::json!({ "size_px": size_px, "recognition": recognition }),
            ));
        }
    };
    let map = joints(&parsed);
    let degenerate: Vec<[usize; 3]> = degenerate_triples(&map);
    let ok = match run_prefixes(
        &ctx,
        &sol,
        &weld,
        &owned,
        &degenerate,
        &parsed,
        upstream_cmds,
        &fitted,
    ) {
        Ok(ok) => ok,
        Err(fail) => {
            return Ok(abstain(
                upstream_cmds,
                &fail.reason,
                prefix_diag(serde_json::json!({ "recognition": recognition }), &fail),
            ));
        }
    };
    // Y stays at the retained upstream fit (prototype `retained-Y-violated`).
    let cand_parsed = match geometry::parse_commands(&ok.out) {
        Ok(parsed) => parsed,
        Err(()) => {
            return Ok(abstain(
                upstream_cmds,
                "topology-changed",
                serde_json::json!({ "size_px": size_px }),
            ));
        }
    };
    let cand_global: Vec<[f64; 2]> = cand_parsed
        .oncurve
        .iter()
        .chain(cand_parsed.offcurve.iter())
        .copied()
        .collect();
    if cand_global.len() != up_global.len()
        || cand_global
            .iter()
            .zip(up_global.iter())
            .any(|(c, u)| c[1] != u[1])
    {
        return Ok(abstain(
            upstream_cmds,
            "retained-Y-violated",
            serde_json::json!({ "size_px": size_px }),
        ));
    }
    // Recheck candidate contacts outside the filled true curves after the
    // fit (prototype post-fit `_white_hit` loop).
    let cand_edges = straight_edges(&cand_parsed);
    let cand_pos: HashMap<(usize, usize), usize> = cand_edges
        .iter()
        .enumerate()
        .map(|(pos, e)| ((e.ci, e.si), pos))
        .collect();
    let mut white_features = Vec::new();
    for feature in &features {
        let (Some(&ea), Some(&eb)) = (
            cand_pos.get(&(feature.a_ci, feature.a_si)),
            cand_pos.get(&(feature.b_ci, feature.b_si)),
        ) else {
            return Ok(abstain(
                upstream_cmds,
                "white-boundary-collapsed",
                serde_json::json!({ "size_px": size_px }),
            ));
        };
        let Some(hit) = white_hit(&cand_parsed, &cand_edges, ea, eb, feature.depth) else {
            return Ok(abstain(
                upstream_cmds,
                "white-feature-clearance",
                serde_json::json!({ "size_px": size_px }),
            ));
        };
        white_features.push(serde_json::json!({
            "a_segment": [feature.a_ci, feature.a_si],
            "b_segment": [feature.b_ci, feature.b_si],
            "source_width": feature.source_width,
            "upstream_gap": gap(feature, &up_global),
            "candidate_gap": gap(feature, &cand_global),
            "candidate_width": hit.width,
        }));
    }
    let mut widths = ok.widths;
    with_effectibility(source, &pairs, &mut widths);
    let mean = |key: &str| {
        widths
            .iter()
            .filter_map(|w| w.get(key)?.as_f64())
            .sum::<f64>()
            / widths.len().max(1) as f64
    };
    let mut pins: Vec<usize> = fixed_x.into_iter().collect();
    pins.sort_unstable();
    Ok(FitResult {
        commands: ok.out,
        applied: true,
        reason: "fitted".to_string(),
        diagnostics: serde_json::json!({
            "model": "coupled-outline-01",
            "pairs": widths,
            "continuity": ok.continuity,
            "recognition": recognition,
            "n_pairs": pairs.len(),
            "n_joints": ctx.joint_rows.len(),
            "bound": ctx.bound,
            "peak": peak,
            "qp": qp.as_ref().map(qp_json),
            "native_axes": native_axes,
            "retained_upstream_axes": [false, true],
            "source_upright_x_pins": pins,
            "coupled_control_count": up_global.len(),
            "white_features": white_features,
            "topology": { "ok": true },
            "widths": { "source": mean("source_2r"), "upstream": mean("upstream"), "candidate": mean("candidate") },
            "size_px": size_px,
            "reference": reference_meta(reference),
        }),
    })
}

/// Diagnostics-first front half of the automatic-Y shape mode
/// (docs/hobby-fitting.md#automatic-y-coupled-shape-mode-feasibility-prototype).
///
/// Runs the existing coupled gates in order and always abstains: no
/// candidate is solved, rounded, or delivered. The native-Y slice in
/// `fit_coupled` is untouched; this entry requires automatic axes
/// exactly and reports retained (not native-owned) Y.
pub(super) fn gate_report_automatic(
    source: &[FittedCommand],
    upstream_cmds: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> Result<FitResult, Error> {
    if !geometry::check_correspondence(source, upstream_cmds) {
        return Ok(FitResult {
            commands: upstream_cmds.to_vec(),
            applied: false,
            reason: "shape-gate:unsupported-correspondence".to_string(),
            diagnostics: serde_json::json!({
                "model": "coupled-shape-auto-01", "gate_report": true, "reached": "correspondence",
            }),
        });
    }
    let Ok(parsed) = geometry::parse_commands(source) else {
        return Ok(FitResult {
            commands: upstream_cmds.to_vec(),
            applied: false,
            reason: "shape-gate:malformed-commands".to_string(),
            diagnostics: serde_json::json!({
                "model": "coupled-shape-auto-01", "gate_report": true, "reached": "parse",
            }),
        });
    };
    gate_report_parsed(
        &parsed,
        upstream_cmds,
        size_px,
        reference,
        native_axes,
        true,
    )
}

/// Gate report on already-parsed source geometry: raw f64 outlines keep
/// their exact dyadic coordinates; only segment-for-segment topology
/// correspondence with the upstream is supported.
pub(super) fn gate_report_parsed(
    parsed: &geometry::Parsed,
    upstream_cmds: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
    from_commands: bool,
) -> Result<FitResult, Error> {
    require_finite_positive_size(size_px)?;
    let report = |reached: &str, reason: &str, mut diag: serde_json::Value| {
        diag["model"] = serde_json::json!("coupled-shape-auto-01");
        diag["gate_report"] = serde_json::json!(true);
        diag["reached"] = serde_json::json!(reached);
        diag["native_axes"] = serde_json::json!(native_axes);
        diag["retained_upstream_axes"] = serde_json::json!([false, true]);
        Ok(FitResult {
            commands: upstream_cmds.to_vec(),
            applied: false,
            reason: format!("shape-gate:{reason}"),
            diagnostics: diag,
        })
    };
    if native_axes != [false, false] {
        return report("axes", "automatic-axes-required", serde_json::json!({}));
    }
    let source_units = parsed.oncurve.len()
        + parsed.offcurve.len()
        + parsed.contours.iter().map(|c| c.len()).sum::<usize>();
    if source_units > MAX_COMMANDS || upstream_cmds.len() > MAX_COMMANDS {
        return report("size", "oversize-outline", serde_json::json!({}));
    }
    let Ok(fitted) = geometry::parse_commands(upstream_cmds) else {
        return report("parse", "malformed-commands", serde_json::json!({}));
    };
    let topology_match = parsed.contours.len() == fitted.contours.len()
        && parsed.oncurve.len() == fitted.oncurve.len()
        && parsed.offcurve.len() == fitted.offcurve.len()
        && parsed.contours.iter().zip(&fitted.contours).all(|(a, b)| {
            a.len() == b.len()
                && a.iter()
                    .zip(b)
                    .all(|(x, y)| std::mem::discriminant(x) == std::mem::discriminant(y))
        });
    let _ = from_commands;
    if !topology_match {
        return report(
            "correspondence",
            "unsupported-correspondence",
            serde_json::json!({}),
        );
    }
    let has_cubic = |p: &geometry::Parsed| {
        p.contours
            .iter()
            .flatten()
            .any(|s| matches!(s, geometry::Segment::Cubic { .. }))
    };
    if parsed.contours.len() != 1
        || fitted.contours.len() != 1
        || has_cubic(&parsed)
        || has_cubic(&fitted)
        || !contour_closed(parsed)
    {
        return report(
            "contour",
            "unsupported-correspondence",
            serde_json::json!({}),
        );
    }
    let up_global: Vec<[f64; 2]> = fitted
        .oncurve
        .iter()
        .chain(fitted.offcurve.iter())
        .copied()
        .collect();
    if up_global
        .iter()
        .flat_map(|p| [p[0], p[1]])
        .any(|v| v * 64.0 != (v * 64.0).round())
    {
        return report("grid", "upstream-not-26.6", serde_json::json!({}));
    }
    let (features, white_reason) = white_contacts_parsed_depths(parsed, &[0, 2, 3, 4]);
    if let Some(reason) = white_reason {
        let certify_error = (0..=4usize)
            .map(|d| {
                serde_json::json!({
                    "depth": d,
                    "error": super::super::curves::certify_parsed(parsed, d)
                        .err()
                        .map(|e| e.to_string()),
                })
            })
            .collect::<Vec<_>>();
        return report(
            "white",
            &reason,
            serde_json::json!({ "white_certify_error": certify_error }),
        );
    }
    // Diagnostics continue past the white gate with an empty spec set so
    // the report can name the next binding gate; no candidate follows.
    let white_empty = features.is_empty();
    let _ = &white_reason;
    let (pairs, recognition) = recognize_parsed_depths(parsed, f64::INFINITY, &[0, 2, 3, 4]);
    if pairs.is_empty() {
        return report(
            "recognition",
            "no-certified-pairs",
            serde_json::json!({ "recognition": recognition }),
        );
    }
    if reference.anchors.is_empty() {
        return report(
            "reference",
            "no-reference-anchors",
            serde_json::json!({ "recognition": recognition }),
        );
    }
    let weld = weld_map(&parsed);
    let up_weld = weld_map(&fitted);
    if weld != up_weld {
        return report("weld", "weld-mismatch", serde_json::json!({}));
    }
    for (dup, canon) in &weld {
        if up_global[*dup] != up_global[*canon] {
            return report("weld", "weld-mismatch", serde_json::json!({}));
        }
    }
    let mut fixed_x = HashSet::new();
    for edge in straight_edges(&parsed) {
        if edge.p0[0] == edge.p1[0] {
            for v in [edge.i0, edge.i1] {
                fixed_x.insert(weld.get(&v).copied().unwrap_or(v));
            }
        }
    }
    let owned = vec![1usize];
    let frozen: HashSet<usize> = weld.keys().copied().collect();
    let specs: Vec<WhiteSpec> = features.iter().map(|f| f.spec.clone()).collect();
    let ctx = match assemble(
        parsed, &up_global, &pairs, reference, size_px, &owned, &frozen, true, &fixed_x, true,
        &specs, true,
    ) {
        Ok(ctx) => ctx,
        Err(reason) => {
            return report(
                "assemble",
                &reason,
                serde_json::json!({
                    "recognition": recognition,
                    "n_pairs": pairs.len(),
                    "n_white_features": features.len(),
                }),
            );
        }
    };
    let pair_widths: Vec<f64> = ctx.pair_work.iter().map(|(w, _)| w.width).collect();
    report(
        "assemble",
        if white_empty {
            "reached-assemble-no-white-feature"
        } else {
            "reached-assemble"
        },
        serde_json::json!({
            "recognition": recognition,
            "n_pairs": pairs.len(),
            "pair_widths": pair_widths,
            "n_white_features": features.len(),
            "white_feature_empty": white_empty,
            "n_upright_pins": fixed_x.len(),
            "n_free_cols": ctx.cols.len(),
            "bound": ctx.bound,
        }),
    )
}

#[cfg(test)]
mod tests {
    use super::super::{axis_corner_tangent, rounding_reserve, SegRef};
    use super::*;

    fn reference() -> Reference {
        Reference {
            anchors: Vec::new(),
            size_px: 16.0,
            records: 0,
            n_anchors: 0,
            rel_min: None,
            rel_max: None,
            notes: Vec::new(),
        }
    }

    /// C-shaped single contour: the notch between the (0,4)-(4,4) and
    /// (4,2)-(0,2) straight borders opens to the exterior left.
    fn notch() -> Vec<FittedCommand> {
        vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(6.0, 0.0),
            FittedCommand::LineTo(6.0, 6.0),
            FittedCommand::LineTo(0.0, 6.0),
            FittedCommand::LineTo(0.0, 4.0),
            FittedCommand::LineTo(4.0, 4.0),
            FittedCommand::LineTo(4.0, 2.0),
            FittedCommand::LineTo(0.0, 2.0),
            FittedCommand::Close,
        ]
    }

    fn edge_pos(edges: &[StraightEdge], si: usize) -> usize {
        edges.iter().position(|e| e.ci == 0 && e.si == si).unwrap()
    }

    fn certified_depth(parsed: &geometry::Parsed) -> usize {
        DEPTHS
            .iter()
            .copied()
            .find(|d| curves::certify_parsed(parsed, *d).is_ok())
            .expect("lines-only contour certifies")
    }

    #[test]
    fn white_exterior_notch_accepted_outside_fill() {
        // Hobby 3.2 exterior feature: the notch gap is white space, so the
        // straight pair certifies with its contact outside the fill.
        let source = notch();
        let (features, reason) = white_contacts(&source);
        assert_eq!(reason, None);
        assert!(!features.is_empty());
        assert!(features.iter().any(|f| (f.source_width - 2.0).abs() < 1e-6));
        let parsed = geometry::parse_commands(&source).unwrap();
        let edges = straight_edges(&parsed);
        let depth = certified_depth(&parsed);
        let hit = white_hit(
            &parsed,
            &edges,
            edge_pos(&edges, 4),
            edge_pos(&edges, 6),
            depth,
        )
        .expect("notch pair certifies");
        assert!((hit.width - 2.0).abs() < 1e-6);
        let (_, loops) = super::super::substitute(&parsed, depth);
        assert_eq!(winding_number(hit.center, &loops), 0);
    }

    #[test]
    fn white_interior_rejected_by_fill_membership() {
        // The same corridor machinery sees the tall-rectangle uprights
        // across the interior, but the medial contact sits inside the
        // filled shape, so no white feature certifies.
        let square = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(4.0, 0.0),
            FittedCommand::LineTo(4.0, 6.0),
            FittedCommand::LineTo(0.0, 6.0),
            FittedCommand::Close,
        ];
        let parsed = geometry::parse_commands(&square).unwrap();
        let edges = straight_edges(&parsed);
        let (ea, eb) = (edge_pos(&edges, 1), edge_pos(&edges, 3));
        let setup = intervals::prepare([edges[ea].p0, edges[ea].p1], [edges[eb].p0, edges[eb].p1])
            .expect("opposed uprights frame");
        let set = intervals::CompetitorSet::new(intervals::tagged_borders(
            &edges.iter().map(|e| [e.p0, e.p1]).collect::<Vec<_>>(),
        ));
        let dom = set.dominance_for(&setup, ea, eb, None);
        assert_eq!(dom.status, "ok");
        assert!(!dom.intervals.is_empty());
        let depth = certified_depth(&parsed);
        assert!(white_hit(&parsed, &edges, ea, eb, depth).is_none());
        let (features, reason) = white_contacts(&square);
        assert_eq!(reason, None);
        assert!(features.is_empty());
    }

    #[test]
    fn axis_corner_row_keeps_curve_direction() {
        // Hersch 2: vertical line into a quadratic at joint 1 is angular,
        // so the row keeps the upstream curve-leg direction: +normal at
        // the off-curve control, -normal at the joint, zero elsewhere. A
        // common translation along the leg row-dots to zero.
        let cmds = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(0.0, 4.0),
            FittedCommand::QuadTo(1.0, 6.0, 3.0, 6.0),
        ];
        let parsed = geometry::parse_commands(&cmds).unwrap();
        let no = parsed.oncurve.len();
        let pts: Vec<[f64; 2]> = parsed
            .oncurve
            .iter()
            .chain(parsed.offcurve.iter())
            .copied()
            .collect();
        let row = axis_corner_tangent(
            &pts,
            &pts,
            1,
            SegRef::Line { a: 0, b: 1 },
            SegRef::Quad {
                off: no,
                a: 1,
                b: 2,
            },
        )
        .expect("axis corner row");
        assert_eq!(row.len(), 2 * pts.len());
        let len = 5.0f64.sqrt();
        let normal = [-2.0 / len, 1.0 / len];
        for (k, c) in row.iter().enumerate() {
            let expected = if k == 2 * no {
                normal[0]
            } else if k == 2 * no + 1 {
                normal[1]
            } else if k == 2 {
                -normal[0]
            } else if k == 3 {
                -normal[1]
            } else {
                0.0
            };
            assert!((c - expected).abs() < 1e-15, "col {k}: {c} vs {expected}");
        }
        let dot: f64 = row
            .iter()
            .enumerate()
            .map(|(k, c)| {
                let d = if k / 2 == no || k / 2 == 1 {
                    if k % 2 == 0 {
                        1.0
                    } else {
                        2.0
                    }
                } else {
                    0.0
                };
                c * d
            })
            .sum();
        assert!(dot.abs() < 1e-12, "dot {dot}");
    }

    #[test]
    fn axis_corner_row_absent_without_axis_alignment() {
        // A diagonal straight leg has no retained axis, so the corner
        // keeps the default cross behavior (`None` row).
        let cmds = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(4.0, 4.0),
            FittedCommand::QuadTo(5.0, 6.0, 7.0, 6.0),
        ];
        let parsed = geometry::parse_commands(&cmds).unwrap();
        let no = parsed.oncurve.len();
        let pts: Vec<[f64; 2]> = parsed
            .oncurve
            .iter()
            .chain(parsed.offcurve.iter())
            .copied()
            .collect();
        assert!(axis_corner_tangent(
            &pts,
            &pts,
            1,
            SegRef::Line { a: 0, b: 1 },
            SegRef::Quad {
                off: no,
                a: 1,
                b: 2
            },
        )
        .is_none());
    }

    #[test]
    fn rounding_reserve_folds_closure_aliases() {
        // Prototype `_rounding_reserve`: the duplicate column folds into
        // its canonical column before summing, since aliases share one
        // 26.6 rounding.
        let row = vec![2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0];
        let weld = HashMap::from([(3usize, 0usize)]);
        let upstream = vec![[0.0, 0.0]; 4];
        let mut raw = upstream.clone();
        raw[0][0] = 0.5;
        let cols = vec![(0usize, 0usize)];
        assert_eq!(
            rounding_reserve(&row, &cols, &raw, &upstream, &weld),
            3.0 / 128.0
        );
        assert_eq!(
            rounding_reserve(&row, &cols, &upstream, &upstream, &weld),
            0.0
        );
    }

    #[test]
    fn other_native_axes_abstain_without_solving() {
        // Initial slice owns native Y only: native X or automatic Y keeps
        // the upstream outline with a helpful reason.
        for axes in [[true, true], [false, false], [true, false]] {
            let out = fit_coupled(&[], &[], 16.0, &reference(), axes).unwrap();
            assert!(!out.applied);
            assert_eq!(out.reason, "native-X-owned-or-invalid");
        }
    }

    #[test]
    fn missing_white_feature_beats_missing_anchors() {
        // Precedence follows the prototype: the white gate runs before ink
        // recognition and the anchor check, so a featureless outline reports
        // the missing white feature even with an anchorless reference.
        let rect = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(4.0, 0.0),
            FittedCommand::LineTo(4.0, 6.0),
            FittedCommand::LineTo(0.0, 6.0),
            FittedCommand::Close,
        ];
        let out = fit_coupled(&rect, &rect, 16.0, &reference(), [false, true]).unwrap();
        assert!(!out.applied);
        assert_eq!(out.reason, "no-certified-straight-white-feature");
    }

    #[test]
    fn multi_contour_abstains_as_unsupported_correspondence() {
        let two = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(1.0, 0.0),
            FittedCommand::Close,
            FittedCommand::MoveTo(2.0, 0.0),
            FittedCommand::LineTo(3.0, 0.0),
            FittedCommand::Close,
        ];
        let out = fit_coupled(&two, &two, 16.0, &reference(), [false, true]).unwrap();
        assert!(!out.applied);
        assert_eq!(out.reason, "unsupported-correspondence");
    }
}

// ---------------------------------------------------------------------------
// Automatic-Y source-shape solve (docs/hobby-fitting.md#automatic-y-
// coupled-shape-mode-feasibility-prototype). Active automatic source-shape
// mode: approved::fit routes eligible outlines here; the kernel prototype
// identity `coupled-shape-auto-01` persists as the internal solver
// configuration string.

struct ShapeFeature {
    x_r: f64,
    x_l: f64,
    w_body: f64,
    w_head_mid: f64,
    w_head_min: f64,
    r_verts: Vec<usize>,
    l_verts: Vec<usize>,
    chain_segs: Vec<usize>,
    chain_verts: Vec<usize>,
    chain_ctrls: Vec<usize>,
    cap: Option<(usize, usize, usize, f64)>,
    stations: Vec<(usize, f64, f64)>, // (seg, fitted t, source fraction-matched width)
    body_r_seg: usize,
    body_l_seg: usize,
    head_r_seg: usize,
}

fn quad_roots_y(p0: [f64; 2], c: [f64; 2], p1: [f64; 2], y: f64) -> Vec<(f64, f64)> {
    let a = p0[1] - 2.0 * c[1] + p1[1];
    let b = 2.0 * (c[1] - p0[1]);
    let d = p0[1] - y;
    let mut roots = Vec::new();
    if a == 0.0 {
        if b != 0.0 {
            roots.push(-d / b);
        }
    } else {
        let disc = b * b - 4.0 * a * d;
        if disc >= 0.0 {
            let sq = disc.sqrt();
            roots.push((-b + sq) / (2.0 * a));
            roots.push((-b - sq) / (2.0 * a));
        }
    }
    roots
        .into_iter()
        .filter(|t| (0.0..=1.0).contains(t))
        .map(|t| {
            let u = 1.0 - t;
            (t, u * u * p0[0] + 2.0 * u * t * c[0] + t * t * p1[0])
        })
        .collect()
}

fn unique_quad_x(parsed: &geometry::Parsed, seg: &geometry::Segment, y: f64) -> Option<(f64, f64)> {
    let geometry::Segment::Quad { c, a, b } = *seg else {
        return None;
    };
    let hits = quad_roots_y(parsed.oncurve[a], parsed.offcurve[c], parsed.oncurve[b], y);
    let mut uniq: Vec<(f64, f64)> = Vec::new();
    for h in hits {
        if !uniq.iter().any(|u| u.0 == h.0) {
            uniq.push(h);
        }
    }
    if uniq.len() == 1 {
        Some(uniq[0])
    } else {
        None
    }
}

fn extract_shape_feature(src: &geometry::Parsed, fit: &geometry::Parsed) -> Option<ShapeFeature> {
    let contour = &src.contours[0];
    // Shared border: one vertical supporting line with >=2 disjoint intervals.
    let mut groups: std::collections::BTreeMap<u64, Vec<(usize, f64, f64)>> =
        std::collections::BTreeMap::new();
    for (idx, seg) in contour.iter().enumerate() {
        if let geometry::Segment::Line { a, b } = *seg {
            let (pa, pb) = (src.oncurve[a], src.oncurve[b]);
            if pa[0] == pb[0] && pa[1] != pb[1] {
                groups.entry(pa[0].to_bits()).or_default().push((
                    idx,
                    pa[1].min(pb[1]),
                    pa[1].max(pb[1]),
                ));
            }
        }
    }
    let mut candidates = Vec::new();
    for (bits, mut segs) in groups {
        segs.sort_by(|x, y| x.1.partial_cmp(&y.1).unwrap());
        let mut merged: Vec<(usize, f64, f64)> = Vec::new();
        for sgm in segs {
            if let Some(last) = merged.last_mut() {
                if sgm.1 <= last.2 {
                    last.2 = last.2.max(sgm.2);
                    continue;
                }
            }
            merged.push(sgm);
        }
        if merged.len() >= 2 {
            candidates.push((f64::from_bits(bits), merged));
        }
    }
    if candidates.len() != 1 {
        return None;
    }
    let (x_r, intervals) = candidates.into_iter().next().unwrap();
    let mut body: Option<(usize, usize, f64, f64)> = None; // (iv_idx, l_seg, ylo, yhi)
    let mut head: Option<(usize, f64, Vec<usize>, Vec<f64>)> = None;
    for (iv_i, iv) in intervals.iter().enumerate() {
        let mut straight: Vec<(f64, usize)> = Vec::new();
        for (idx, seg) in contour.iter().enumerate() {
            if let geometry::Segment::Line { a, b } = *seg {
                let (pa, pb) = (src.oncurve[a], src.oncurve[b]);
                if pa[0] == pb[0] && pa[0] < x_r && pa[1] != pb[1] {
                    let lo = pa[1].min(pb[1]).max(iv.1);
                    let hi = pa[1].max(pb[1]).min(iv.2);
                    if hi > lo {
                        straight.push((pa[0], idx));
                    }
                }
            }
        }
        straight.sort_by(|x, y| x.0.partial_cmp(&y.0).unwrap());
        straight.dedup_by(|x, y| x.0 == y.0);
        let mut station_segs = Vec::new();
        let mut station_widths = Vec::new();
        let mut curve_ok = true;
        for frac in [0.25, 0.5, 0.75] {
            let y = iv.1 + (iv.2 - iv.1) * frac;
            let mut hits = Vec::new();
            for (idx, seg) in contour.iter().enumerate() {
                if let geometry::Segment::Quad { .. } = *seg {
                    let (a, b) = seg.endpoints();
                    if src.oncurve[a][0] < x_r && src.oncurve[b][0] < x_r {
                        if let Some((_, x)) = unique_quad_x(src, seg, y) {
                            if x < x_r {
                                hits.push((idx, x_r - x));
                            }
                        }
                    }
                }
            }
            if hits.len() != 1 {
                curve_ok = false;
                break;
            }
            station_segs.push(hits[0].0);
            station_widths.push(hits[0].1);
        }
        match (straight.len(), curve_ok) {
            (1, false) => {
                if body.is_some() {
                    return None;
                }
                body = Some((iv_i, straight[0].1, iv.1, iv.2));
            }
            (0, true) => {
                if head.is_some() {
                    return None;
                }
                head = Some((iv_i, station_widths[1], station_segs, station_widths));
            }
            _ => return None,
        }
    }
    let (body_iv_i, body_l_seg, _bylo, _byhi) = body?;
    let (head_iv_i, w_head_mid, head_segs, head_station_widths) = head?;
    let body_iv = &intervals[body_iv_i];
    let head_iv = &intervals[head_iv_i];
    // Straight body left x from the body partner segment.
    let geometry::Segment::Line { a: la, .. } = contour[body_l_seg] else {
        return None;
    };
    let x_l = src.oncurve[la][0];
    let w_body = x_r - x_l;
    if !(w_body > 0.0) {
        return None;
    }
    // Attached chain from the head border segment (contour adjacency,
    // bounded by the head interval's Y span).
    let mut adjacency: HashMap<usize, Vec<usize>> = HashMap::new();
    for (idx, seg) in contour.iter().enumerate() {
        let (a, b) = seg.endpoints();
        adjacency.entry(a).or_default().push(idx);
        adjacency.entry(b).or_default().push(idx);
    }
    let mut chain_segs: Vec<usize> = Vec::new();
    let (ha, hb) = contour[head_iv.0].endpoints();
    for start in [ha, hb] {
        let mut current = start;
        let mut prev = head_iv.0;
        for _ in 0..contour.len() {
            let Some(next) = adjacency
                .get(&current)
                .and_then(|v| v.iter().copied().find(|&i| i != prev))
            else {
                break;
            };
            let seg = contour[next];
            let (a, b) = seg.endpoints();
            let other = if a == current { b } else { a };
            match seg {
                geometry::Segment::Quad { .. } => {
                    let ymin = src.oncurve[a][1].min(src.oncurve[b][1]);
                    let ymax = src.oncurve[a][1].max(src.oncurve[b][1]);
                    if ymax < head_iv.1 || ymin > head_iv.2 {
                        break;
                    }
                    if !chain_segs.contains(&next) {
                        chain_segs.push(next);
                    }
                }
                geometry::Segment::Line { .. } => {
                    let (pa, pb) = (src.oncurve[a], src.oncurve[b]);
                    if pa[0] == pb[0] || !chain_segs.is_empty() {
                        break;
                    }
                }
                geometry::Segment::Cubic { .. } => break,
            }
            prev = next;
            current = other;
            if current == ha || current == hb {
                break;
            }
        }
    }
    if chain_segs.is_empty() || !head_segs.iter().all(|sg| chain_segs.contains(sg)) {
        return None;
    }
    // Ink/dominance at stations via the certified winding path.
    let (portions, _, loops, flats) = geometry::split_visible(src, true);
    let _ = portions;
    for (k, frac) in [0.25, 0.5, 0.75].iter().enumerate() {
        let y = head_iv.1 + (head_iv.2 - head_iv.1) * frac;
        let seg = &contour[head_segs[k]];
        let Some((_, x_left)) = unique_quad_x(src, seg, y) else {
            return None;
        };
        let probe = [x_left + 0.75 * (x_r - x_left), y];
        match geometry::certified_winding(probe, &loops, &flats) {
            Some(w) if w != 0 => {}
            _ => return None,
        }
        // No competing boundary crosses the open station segment.
        for (idx, sgm) in contour.iter().enumerate() {
            match *sgm {
                geometry::Segment::Line { a, b } => {
                    let (pa, pb) = (src.oncurve[a], src.oncurve[b]);
                    if pa[0] == x_r && pb[0] == x_r {
                        continue;
                    }
                    if (pa[1] <= y) != (pb[1] <= y) && pa[1] != pb[1] {
                        let xi = pa[0] + (y - pa[1]) / (pb[1] - pa[1]) * (pb[0] - pa[0]);
                        if xi > x_left && xi < x_r {
                            return None;
                        }
                    }
                }
                geometry::Segment::Quad { c, a, b } => {
                    if idx == head_segs[k] {
                        continue;
                    }
                    for (_, x) in quad_roots_y(src.oncurve[a], src.offcurve[c], src.oncurve[b], y) {
                        if x > x_left && x < x_r {
                            return None;
                        }
                    }
                }
                geometry::Segment::Cubic { .. } => return None,
            }
        }
    }
    // Fitted stations (parameter from the fitted curve at matched Y).
    let fseg = &fit.contours[0][head_iv.0];
    let (fa, fb) = fseg.endpoints();
    let (fylo, fyhi) = (
        fit.oncurve[fa][1].min(fit.oncurve[fb][1]),
        fit.oncurve[fa][1].max(fit.oncurve[fb][1]),
    );
    let mut stations = Vec::new();
    for (k, frac) in [0.25, 0.5, 0.75].iter().enumerate() {
        let y = fylo + (fyhi - fylo) * frac;
        let seg = &fit.contours[0][head_segs[k]];
        let Some((t, _)) = unique_quad_x(fit, seg, y) else {
            return None;
        };
        stations.push((head_segs[k], t, head_station_widths[k]));
    }
    // Cap anchor: first line-vertex-line turn walking away from the head
    // border's upper endpoint on the curve side.
    let mut cap = None;
    {
        let mut adjacency_v: HashMap<usize, Vec<usize>> = adjacency.clone();
        let _ = &mut adjacency_v;
        let mut current = if src.oncurve[ha][1] >= src.oncurve[hb][1] {
            ha
        } else {
            hb
        };
        // Walk at most 3 segments collecting line vertices.
        let mut verts = vec![current];
        let mut prev = head_iv.0;
        for _ in 0..3 {
            let Some(next) = adjacency
                .get(&current)
                .and_then(|v| v.iter().copied().find(|&i| i != prev))
            else {
                break;
            };
            let (a, b) = contour[next].endpoints();
            let other = if a == current { b } else { a };
            verts.push(other);
            if !matches!(contour[next], geometry::Segment::Line { .. }) {
                break;
            }
            prev = next;
            current = other;
        }
        if verts.len() >= 3 {
            // Walk order: shared-border top, cap vertex, head-curve end.
            let (right, cap_v, left) = (verts[0], verts[1], verts[2]);
            let run = src.oncurve[right][0] - src.oncurve[left][0];
            if run != 0.0 && src.oncurve[right][0] == x_r {
                let f = (src.oncurve[cap_v][0] - src.oncurve[left][0]) / run;
                cap = Some((cap_v, left, right, f));
            }
        }
        let _ = current;
    }
    let r_verts: Vec<usize> = src
        .oncurve
        .iter()
        .enumerate()
        .filter(|(_, p)| p[0] == x_r)
        .map(|(i, _)| i)
        .collect();
    let l_verts: Vec<usize> = src
        .oncurve
        .iter()
        .enumerate()
        .filter(|(_, p)| p[0] == x_l)
        .map(|(i, _)| i)
        .collect();
    let mut chain_verts = Vec::new();
    let mut chain_ctrls = Vec::new();
    for &sg in &chain_segs {
        let (a, b) = contour[sg].endpoints();
        for v in [a, b] {
            if src.oncurve[v][0] < x_r && !chain_verts.contains(&v) {
                chain_verts.push(v);
            }
        }
        if let geometry::Segment::Quad { c, .. } = contour[sg] {
            if !chain_ctrls.contains(&c) {
                chain_ctrls.push(c);
            }
        }
    }
    Some(ShapeFeature {
        x_r,
        x_l,
        w_body,
        w_head_mid,
        w_head_min: head_station_widths
            .iter()
            .cloned()
            .fold(f64::INFINITY, f64::min),
        r_verts,
        l_verts,
        chain_segs,
        chain_verts,
        chain_ctrls,
        cap,
        stations,
        body_r_seg: body_iv.0,
        body_l_seg,
        head_r_seg: head_iv.0,
    })
}

/// Automatic-Y source-shape solve. Always returns the upstream
/// outline unchanged unless every gate and post-rounding shape check
/// passes. Routed from approved::fit for eligible automatic outlines;
/// the gate-report entries remain diagnostics-first and always abstain.
pub(super) fn fit_shape_automatic(
    parsed: &geometry::Parsed,
    source_captured: &[FittedCommand],
    upstream_cmds: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> Result<FitResult, Error> {
    require_finite_positive_size(size_px)?;
    let no = |reason: &str, diag: serde_json::Value| {
        let mut diag = diag;
        diag["model"] = serde_json::json!("coupled-shape-auto-01");
        Ok(FitResult {
            commands: upstream_cmds.to_vec(),
            applied: false,
            reason: format!("shape:{reason}"),
            diagnostics: diag,
        })
    };
    if native_axes != [false, false] {
        return no("automatic-axes-required", serde_json::json!({}));
    }
    let Ok(fitted) = geometry::parse_commands(upstream_cmds) else {
        return no("malformed-commands", serde_json::json!({}));
    };
    // Raw index graph correspondence plus finite/MAX guards before any
    // raw index dereference (Hobby 6: control variables are named by the
    // source outline graph). Exact contour data equality covers segment
    // variants and endpoint indices, not just counts.
    if !parsed
        .oncurve
        .iter()
        .chain(parsed.offcurve.iter())
        .flat_map(|p| [p[0], p[1]])
        .all(|v| v.is_finite())
    {
        return no("malformed-commands", serde_json::json!({}));
    }
    let source_units = parsed.oncurve.len()
        + parsed.offcurve.len()
        + parsed.contours.iter().map(|c| c.len()).sum::<usize>();
    if source_units > MAX_COMMANDS || upstream_cmds.len() > MAX_COMMANDS {
        return no("oversize-outline", serde_json::json!({}));
    }
    let topology_match = parsed.contours.len() == fitted.contours.len()
        && parsed.oncurve.len() == fitted.oncurve.len()
        && parsed.offcurve.len() == fitted.offcurve.len()
        && parsed.contours == fitted.contours;
    if !topology_match
        || parsed.contours.len() != 1
        || parsed
            .contours
            .iter()
            .flatten()
            .any(|s| matches!(s, geometry::Segment::Cubic { .. }))
        || !contour_closed(parsed)
    {
        return no("unsupported-correspondence", serde_json::json!({}));
    }
    let up_global: Vec<[f64; 2]> = fitted
        .oncurve
        .iter()
        .chain(fitted.offcurve.iter())
        .copied()
        .collect();
    if up_global
        .iter()
        .flat_map(|p| [p[0], p[1]])
        .any(|v| v * 64.0 != (v * 64.0).round())
    {
        return no("upstream-not-26.6", serde_json::json!({}));
    }
    let weld = weld_map(parsed);
    if weld != weld_map(&fitted) {
        return no("weld-mismatch", serde_json::json!({}));
    }
    let Some(feature) = extract_shape_feature(parsed, &fitted) else {
        return no("shape-feature-unsupported", serde_json::json!({}));
    };
    // Narrower-head eligibility from the old source class (fail closed):
    // the head is a genuinely narrower feature than the body.
    if !(0.0 < feature.w_head_mid
        && feature.w_head_mid < feature.w_body
        && 0.0 < feature.w_head_min
        && feature.w_head_min < feature.w_body)
    {
        return no("shape-feature-unsupported", serde_json::json!({}));
    }
    // Standard and class stay on the existing certified certificates
    // (captured-source DonorCert); shape authority below is raw.
    let Ok(captured) = geometry::parse_commands(source_captured) else {
        return no("shape-standard-unavailable", serde_json::json!({}));
    };
    let Some(captured_feature) = extract_shape_feature(&captured, &fitted) else {
        return no("shape-standard-unavailable", serde_json::json!({}));
    };
    let Some(standard) =
        super::super::upright::certified_standard(reference, captured_feature.w_body)
    else {
        return no("shape-standard-unavailable", serde_json::json!({}));
    };
    // Fitted body width from the body borders.
    let geometry::Segment::Line { a: bla, .. } = parsed.contours[0][feature.body_l_seg] else {
        return no("shape-feature-unsupported", serde_json::json!({}));
    };
    let fx_l = fitted.oncurve[bla][0];
    let fx_r = {
        let (a, _) = parsed.contours[0][feature.body_r_seg].endpoints();
        fitted.oncurve[a][0]
    };
    let w_up = fx_r - fx_l;
    if w_up == standard {
        return no(
            "shape-already-standard",
            serde_json::json!({ "standard": standard }),
        );
    }
    let (features, white_reason) = white_contacts_parsed_depths(parsed, &[0, 2, 3, 4]);
    if let Some(reason) = white_reason {
        return no(&reason, serde_json::json!({}));
    }
    let specs: Vec<WhiteSpec> = features.iter().map(|f| f.spec.clone()).collect();
    // Whole-outline free-X coupled assembly (Hobby 3.1/3.6/6: every X
    // control is a coupled variable). Only closure aliases stay frozen;
    // upright pins below hold every non-owned vertical. No ad hoc
    // free_set freeze: the coupled objective already owns all controls,
    // and freezing the complement reintroduces hidden stationary foot
    // attachments and frozen connector points.
    // Weld-canonical release for both body borders, head-owned vertices,
    // and both endpoints of every source vertical connector incident to
    // the head chain. Built completely before assemble.
    let canon = |v: usize| weld.get(&v).copied().unwrap_or(v);
    let chain_set: HashSet<usize> = feature.chain_verts.iter().copied().collect();
    let mut connector_verts: Vec<usize> = Vec::new();
    for seg in &parsed.contours[0] {
        if let geometry::Segment::Line { a, b } = *seg {
            let (pa, pb) = (parsed.oncurve[a], parsed.oncurve[b]);
            if pa[0] == pb[0] && (chain_set.contains(&a) || chain_set.contains(&b)) {
                for v in [a, b] {
                    if !connector_verts.contains(&v) {
                        connector_verts.push(v);
                    }
                }
            }
        }
    }
    // Fitted group coherence plus full-span width verification (not a
    // single point): both body borders must be constant-X in the
    // original upstream, otherwise the straight-border ownership is
    // ineligible and the candidate abstains.
    {
        let mut r_fit: Option<f64> = None;
        for &v in &feature.r_verts {
            let x = fitted.oncurve[v][0];
            match r_fit {
                None => r_fit = Some(x),
                Some(y) if y == x => {}
                _ => {
                    return no(
                        "shape-border-incoherent",
                        serde_json::json!({ "border": "right" }),
                    );
                }
            }
        }
        let mut l_fit: Option<f64> = None;
        for &v in &feature.l_verts {
            let x = fitted.oncurve[v][0];
            match l_fit {
                None => l_fit = Some(x),
                Some(y) if y == x => {}
                _ => {
                    return no(
                        "shape-border-incoherent",
                        serde_json::json!({ "border": "left" }),
                    );
                }
            }
        }
        // Full-span check: every fitted border vertex participates above,
        // so a split border anywhere in the span abstains.
    }
    let mut fixed_x = HashSet::new();
    for edge in straight_edges(parsed) {
        if edge.p0[0] == edge.p1[0] {
            for v in [edge.i0, edge.i1] {
                fixed_x.insert(canon(v));
            }
        }
    }
    // Release weld-canonical vertices for both body borders, the head
    // chain, its controls' endpoints, connector endpoints, and cap.
    for &v in feature
        .r_verts
        .iter()
        .chain(&feature.l_verts)
        .chain(&feature.chain_verts)
        .chain(&connector_verts)
    {
        fixed_x.remove(&canon(v));
    }
    if let Some((cv, lv, rv, _)) = feature.cap {
        for v in [cv, lv, rv] {
            fixed_x.remove(&canon(v));
        }
    }
    let owned = vec![1usize];
    let frozen: HashSet<usize> = weld.keys().copied().collect();
    let empty_reference = Reference {
        anchors: Vec::new(),
        size_px,
        records: 0,
        n_anchors: 0,
        rel_min: None,
        rel_max: None,
        notes: Vec::new(),
    };
    let mut ctx = match assemble(
        parsed,
        &up_global,
        &[],
        &empty_reference,
        size_px,
        &owned,
        &frozen,
        true,
        &fixed_x,
        true,
        &specs,
        true,
    ) {
        Ok(ctx) => ctx,
        Err(reason) => return no(&reason, serde_json::json!({})),
    };
    // Incident-feature movement caps from one original-upstream budget
    // (Hobby 3.1/6 single displacement measure; Shamir shared-feature
    // solve; existing per-pair cap rule: narrowest certified sample of
    // the owning feature over two minus HEADROOM). Body cap from the
    // body width, head cap from the minimum certified head sample.
    // Shared-border R and the cap vertex obey the intersection (minimum);
    // head-chain controls, extreme endpoints and vertical-connector
    // endpoints obey the head cap; body-L and offcurve controls on their
    // source vertical support obey the body cap; all other body/foot
    // controls obey the body cap unless jointly head-owned. The 26.6
    // rounding reserve (half quantum per moved X) sits inside each cap,
    // so the delivered quantized movement never exceeds the cap.
    let body_cap = feature.w_body / 2.0 - super::super::HEADROOM;
    let head_cap = feature.w_head_min / 2.0 - super::super::HEADROOM;
    if body_cap < super::super::HEADROOM || head_cap < super::super::HEADROOM {
        return no("shape-budget-empty", serde_json::json!({}));
    }
    let shared_cap = body_cap.min(head_cap);
    // Solver bounds reserve one half-quantum per moved X inside the cap.
    let solver_body = body_cap - super::ROUND_HALF;
    let solver_head = head_cap - super::ROUND_HALF;
    let solver_shared = shared_cap - super::ROUND_HALF;
    if solver_body < 0.0 || solver_head < 0.0 || solver_shared < 0.0 {
        return no("shape-budget-empty", serde_json::json!({}));
    }
    let no_pts = parsed.oncurve.len();
    let global_index = |oncurve: bool, idx: usize| if oncurve { idx } else { no_pts + idx };
    // Per-control caps metadata (explicit; solver bounds reserve rounding).
    let caps_meta = serde_json::json!({
        "body_cap": body_cap, "head_cap": head_cap, "shared_cap": shared_cap,
        "solver_reserve": super::ROUND_HALF,
        "solver_body": solver_body, "solver_head": solver_head,
        "solver_shared": solver_shared,
    });
    // Hard rows over candidate absolute X (constant folds upstream X).
    // Every row below is an intended source relationship by name:
    // body-width, border-straightness (R/L), head-translation
    // (intrinsic), head-mid, cap-ratio.
    let n = ctx.base.len();
    let mut hard_rows: Vec<(super::RowKind, Vec<f64>, f64)> = Vec::new();
    // Row names parallel to hard_rows for the binding witness.
    let mut hard_names: Vec<&'static str> = Vec::new();
    let mut row_named = |name: &'static str, coeffs: &[(usize, f64)], target: f64| {
        let mut rvec = vec![0.0; 2 * n];
        let mut up_dot = 0.0;
        for &(g, a) in coeffs {
            rvec[2 * g] += a;
            up_dot += a * up_global[g][0];
        }
        hard_rows.push((RowKind::Joint, rvec, up_dot - target));
        hard_names.push(name);
    };
    // Both body borders stay straight constant-X: hard equal-displacement
    // rows for ALL R-group and ALL L-group verts (Shamir shared point).
    // Canonical order for determinism.
    {
        let mut r_sorted = feature.r_verts.clone();
        r_sorted.sort_unstable();
        r_sorted.dedup();
        for w in r_sorted.windows(2) {
            row_named(
                "border-straightness-R",
                &[
                    (global_index(true, w[0]), 1.0),
                    (global_index(true, w[1]), -1.0),
                ],
                up_global[global_index(true, w[0])][0] - up_global[global_index(true, w[1])][0],
            );
        }
        let mut l_sorted = feature.l_verts.clone();
        l_sorted.sort_unstable();
        l_sorted.dedup();
        for w in l_sorted.windows(2) {
            row_named(
                "border-straightness-L",
                &[
                    (global_index(true, w[0]), 1.0),
                    (global_index(true, w[1]), -1.0),
                ],
                up_global[global_index(true, w[0])][0] - up_global[global_index(true, w[1])][0],
            );
        }
    }
    // Body-width row: shared-border X minus body-left X equals S.
    let (r_rep, _) = parsed.contours[0][feature.body_r_seg].endpoints();
    row_named(
        "body-width",
        &[
            (global_index(true, r_rep), 1.0),
            (global_index(true, bla), -1.0),
        ],
        standard,
    );
    // Translated original source head profile (Hobby section 3.1/3.6
    // control variables as one feature; Shamir sections 3.2-3.6 shared
    // feature displacement): intrinsic X distances within the head are
    // the source's, not the compressed hinted ones. One head-mid width
    // relation couples the translated profile to the shared border;
    // tangent survival and station profile are verified post-rounding.
    // Translated original source head X profile with one shared
    // translation (Hobby control variables; Shamir shared feature
    // displacement). Source OFFCURVE X plus chain EXTREME endpoints are
    // copied; interior smooth oncurve knots stay free so existing G1
    // equations determine X under retained Y (Hersch 2 / TrueType
    // midpoint mechanism: oncurve X is weighted by adjacent retained-Y
    // legs between offcurve controls). Connector endpoints share the
    // same translation; the complete set is built BEFORE rows.
    let mut knot_degree: HashMap<usize, usize> = HashMap::new();
    for &sg in &feature.chain_segs {
        let (a, b) = parsed.contours[0][sg].endpoints();
        *knot_degree.entry(a).or_insert(0) += 1;
        *knot_degree.entry(b).or_insert(0) += 1;
    }
    // Conservative smoothness for intrinsic membership (exact; no
    // epsilon). Interior smooth knots stay free for G1; interior
    // sharp knots share the head translation to avoid kinks. Smooth if
    // raw source OR genuine captured source OR upstream is exactly
    // smooth: raw f64 scaling can move an original implicit TrueType
    // midpoint off exact collinearity by 1ULP, while the captured source
    // (producer-proof discrete outline) retains the exact G1. This is a
    // project adaptation (Hersch endpoint identities applied to the
    // producer's discrete proof), not a near-zero threshold.
    let src_map_pre = joints(parsed);
    let cap_map_pre = joints(&captured);
    let up_map_pre = joints(&fitted);
    let smooth_pre = |j: &usize| -> bool {
        src_map_pre
            .get(j)
            .is_some_and(|v| v.iter().any(|o| o.smooth))
            || cap_map_pre
                .get(j)
                .is_some_and(|v| v.iter().any(|o| o.smooth))
            || up_map_pre
                .get(j)
                .is_some_and(|v| v.iter().any(|o| o.smooth))
    };
    let mut intrinsic: Vec<(usize, f64)> = Vec::new();
    let mut seen_intrinsic: HashSet<usize> = HashSet::new();
    let push_intrinsic =
        |g: usize, x: f64, intrinsic: &mut Vec<(usize, f64)>, seen: &mut HashSet<usize>| {
            if seen.insert(g) {
                intrinsic.push((g, x));
            }
        };
    for &v in &feature.chain_verts {
        let deg = knot_degree.get(&v).copied().unwrap_or(0);
        if deg <= 1 || !smooth_pre(&v) {
            push_intrinsic(
                global_index(true, v),
                parsed.oncurve[v][0],
                &mut intrinsic,
                &mut seen_intrinsic,
            );
        }
    }
    for &c in &feature.chain_ctrls {
        push_intrinsic(
            global_index(false, c),
            parsed.offcurve[c][0],
            &mut intrinsic,
            &mut seen_intrinsic,
        );
    }
    for &v in &connector_verts {
        push_intrinsic(
            global_index(true, v),
            parsed.oncurve[v][0],
            &mut intrinsic,
            &mut seen_intrinsic,
        );
    }
    if let Some(&(ref_g, _)) = intrinsic.first() {
        let ref_src = intrinsic[0].1;
        for &(g, src_x) in &intrinsic[1..] {
            row_named(
                "head-translation",
                &[(g, 1.0), (ref_g, -1.0)],
                src_x - ref_src,
            );
        }
    }
    // Head-mid coupling: candidate width at the mid station equals the
    // decided standard times the source head/body ratio (Shamir cap
    // ratio anchored to neighbors; Hersch grid phase elsewhere).
    {
        let (seg_idx, t, src_width) = &feature.stations[1];
        let geometry::Segment::Quad { c, a, b } = parsed.contours[0][*seg_idx] else {
            return no("shape-feature-unsupported", serde_json::json!({}));
        };
        let u = 1.0 - t;
        let target = standard * (src_width / feature.w_body);
        row_named(
            "head-mid",
            &[
                (global_index(true, r_rep), 1.0),
                (global_index(true, a), -u * u),
                (global_index(false, c), -2.0 * u * t),
                (global_index(true, b), -t * t),
            ],
            target,
        );
    }
    // Cap ratio anchored to its neighbors (Shamir ratio relation).
    if let Some((cap_v, left_v, right_v, f)) = feature.cap {
        row_named(
            "cap-ratio",
            &[
                (global_index(true, cap_v), 1.0),
                (global_index(true, left_v), -(1.0 - f)),
                (global_index(true, right_v), -f),
            ],
            0.0,
        );
    } else {
        let (ta, tb) = parsed.contours[0][feature.head_r_seg].endpoints();
        let top = if parsed.oncurve[ta][1] >= parsed.oncurve[tb][1] {
            ta
        } else {
            tb
        };
        let direct = parsed.contours[0].iter().any(|sg| {
            let (a, b) = sg.endpoints();
            (a == top || b == top) && matches!(sg, geometry::Segment::Quad { .. })
        });
        if !direct {
            return no("shape-cap-unsupported", serde_json::json!({}));
        }
    }
    // Smooth joints stay hard (G1). Conservative continuity: a join is
    // smooth if source OR original upstream is smooth (exact rational
    // classification; raw f64 1ULP off-collinearity never reclassifies
    // an upstream-smooth join as a kink). Sharp source corners owned by
    // the feature transform with source orientation plus feature rows;
    // their obsolete preserved-cross/tangent equalities are removed
    // where owned controls move (row identity and joint metadata stay
    // consistent). Native-Y mode untouched.
    {
        let src_map = joints(parsed);
        let cap_map = joints(&captured);
        let up_map = joints(&fitted);
        let smooth_of = |map: &HashMap<usize, Vec<super::JointOcc>>, j: usize| -> bool {
            map.get(&j).is_some_and(|v| v.iter().any(|o| o.smooth))
        };
        let complex: HashSet<usize> = feature
            .r_verts
            .iter()
            .map(|&v| global_index(true, v))
            .chain(feature.l_verts.iter().map(|&v| global_index(true, v)))
            .chain(intrinsic.iter().map(|&(g, _)| g))
            .chain(
                feature
                    .cap
                    .iter()
                    .map(|&(cv, _, _, _)| global_index(true, cv)),
            )
            .chain(feature.chain_verts.iter().map(|&v| global_index(true, v)))
            .chain(feature.chain_ctrls.iter().map(|&c| global_index(false, c)))
            .collect();
        // Map joint_rows index to ctx.rows index for Joint/White rows.
        let mut joint_row_pos: Vec<usize> = Vec::new();
        {
            let mut ji = 0usize;
            for (ri, (k, _, _)) in ctx.rows.iter().enumerate() {
                if matches!(k, RowKind::Joint | RowKind::White) {
                    // White rows have no joint metadata; only Joint rows
                    // advance the joint index in assemble order.
                    if matches!(k, RowKind::Joint) {
                        joint_row_pos.push(ri);
                        ji += 1;
                    }
                }
            }
            let _ = ji;
        }
        // Collect replacements/removals by joint_rows index.
        let mut replace_smooth: Vec<(usize, Vec<f64>, f64)> = Vec::new();
        let mut drop_joints: HashSet<usize> = HashSet::new();
        for (ji, jr) in ctx.joint_rows.iter().enumerate() {
            let cons_smooth = smooth_of(&src_map, jr.joint)
                || smooth_of(&cap_map, jr.joint)
                || smooth_of(&up_map, jr.joint);
            let iv = leg_vertex(jr.occ_prev, false);
            let ov = leg_vertex(jr.occ_seg, true);
            let touches_owned =
                complex.contains(&jr.joint) || complex.contains(&iv) || complex.contains(&ov);
            if cons_smooth {
                if !jr.smooth {
                    // Upgrade sharp defect row to hard G1 zero row with
                    // upstream-frozen coefficients (Hobby linearity).
                    if let Some((new_row, constant)) =
                        g1_row(&up_global, jr.joint, jr.occ_prev, jr.occ_seg, size_px, true)
                    {
                        replace_smooth.push((ji, new_row, constant));
                    }
                }
            } else if touches_owned {
                // Sharp owned corner: obsolete preserved-cross/tangent
                // locks horizontal span under retained Y. Remove it;
                // orientation/nondegeneracy are post-checked.
                drop_joints.insert(ji);
            }
        }
        for (ji, new_row, constant) in replace_smooth {
            let ri = joint_row_pos[ji];
            ctx.rows[ri].1 = new_row;
            ctx.rows[ri].2 = constant;
            ctx.joint_rows[ji].smooth = true;
            ctx.joint_rows[ji].tangent = None;
        }
        if !drop_joints.is_empty() {
            // Consistent rebuild: drop the Joint rows and their joint
            // metadata together, preserving order for the rest.
            let mut new_rows = Vec::with_capacity(ctx.rows.len());
            let mut ji = 0usize;
            for (k, r, c) in ctx.rows.drain(..) {
                if matches!(k, RowKind::Joint) {
                    if drop_joints.contains(&ji) {
                        ji += 1;
                        continue;
                    }
                    ji += 1;
                }
                new_rows.push((k, r, c));
            }
            ctx.rows = new_rows;
            let mut filtered = Vec::with_capacity(ctx.joint_rows.len());
            for (idx, jr) in ctx.joint_rows.drain(..).enumerate() {
                if !drop_joints.contains(&idx) {
                    filtered.push(jr);
                }
            }
            ctx.joint_rows = filtered;
        }
    }
    let n_hard = hard_rows.len();
    ctx.rows.extend(hard_rows.clone());
    let (mat, rhs, kinds) = restricted_matrix(&ctx, &weld);
    if mat.is_empty() || rhs.is_empty() || ctx.cols.is_empty() {
        return no("shape-solve-incompatible", serde_json::json!({}));
    }
    // Per-column incident-feature caps (solver bounds reserve rounding;
    // public caps gate the delivered quantized movement).
    let r_set: HashSet<usize> = feature.r_verts.iter().copied().collect();
    let l_set: HashSet<usize> = feature.l_verts.iter().copied().collect();
    let chain_vset: HashSet<usize> = feature.chain_verts.iter().copied().collect();
    let conn_set: HashSet<usize> = connector_verts.iter().copied().collect();
    let chain_cset: HashSet<usize> = feature.chain_ctrls.iter().copied().collect();
    let (cap_v, cap_l, cap_r, _) = feature
        .cap
        .unwrap_or((usize::MAX, usize::MAX, usize::MAX, 0.0));
    let mut off_seg: HashMap<usize, (usize, usize)> = HashMap::new();
    for seg in &parsed.contours[0] {
        if let geometry::Segment::Quad { c, a, b } = *seg {
            off_seg.insert(c, (a, b));
        }
    }
    let public_cap_of = |g: usize| -> f64 {
        if g < no_pts {
            let v = g;
            if r_set.contains(&v) || v == cap_v || v == cap_l || v == cap_r {
                shared_cap
            } else if chain_vset.contains(&v) || conn_set.contains(&v) {
                head_cap
            } else if l_set.contains(&v) {
                body_cap
            } else {
                body_cap
            }
        } else {
            let c = g - no_pts;
            if chain_cset.contains(&c) {
                head_cap
            } else if parsed.offcurve.get(c).is_some_and(|p| p[0] == feature.x_r) {
                shared_cap
            } else if parsed.offcurve.get(c).is_some_and(|p| p[0] == feature.x_l) {
                body_cap
            } else if let Some((a, b)) = off_seg.get(&c) {
                if chain_vset.contains(a)
                    || chain_vset.contains(b)
                    || conn_set.contains(a)
                    || conn_set.contains(b)
                    || r_set.contains(a)
                    || r_set.contains(b)
                    || *a == cap_v
                    || *b == cap_v
                    || *a == cap_l
                    || *b == cap_l
                    || *a == cap_r
                    || *b == cap_r
                {
                    head_cap
                } else {
                    body_cap
                }
            } else {
                body_cap
            }
        }
    };
    let bounds: Vec<f64> = ctx
        .cols
        .iter()
        .map(|(v, _)| public_cap_of(*v) - super::ROUND_HALF)
        .collect();
    let public_caps: Vec<f64> = ctx.cols.iter().map(|(v, _)| public_cap_of(*v)).collect();
    // Automatic source-shape mode only: elastic Phase-I start repairs an
    // equality minimum-norm start outside the per-column boxes when a
    // feasible point exists (same BOUNDED_TOL, same bounds). Native-Y keeps
    // the legacy strict entry untouched.
    let (sol, peak, qp) = match hard_solve_bounded_phase1(&mat, &rhs, &kinds, &bounds) {
        Ok(v) => v,
        Err(reason) => {
            // Smallest exact binding witness (not a representation limit):
            // retry once with a finite large bound. If that succeeds, the
            // binding constraint is the single movement budget; name the
            // exceeded columns. If it still fails, the binding constraint
            // is among the named intended relationships themselves.
            let big = vec![1e6; bounds.len()];
            let _n_joint_pre = kinds[..kinds.len().saturating_sub(n_hard)]
                .iter()
                .filter(|k| matches!(k, RowKind::Joint | RowKind::White))
                .count();
            // No speculative constraint drops: the witness below names the
            // binding intended relationship instead of hunting pixels.
            // Same Phase-I entry with large bounds distinguishes bound
            // from equality infeasibility under identical start repair.
            let retry = hard_solve_bounded_phase1(&mat, &rhs, &kinds, &big);
            let (finite_retry_ok, exceeded) = match &retry {
                Ok((s2, _, _)) => {
                    let exc: Vec<serde_json::Value> = s2
                        .iter()
                        .zip(&bounds)
                        .enumerate()
                        .filter(|(_, (x, b))| x.abs() > **b)
                        .map(|(ci, (x, b))| {
                            serde_json::json!({
                                "point": ctx.cols[ci].0, "axis": ctx.cols[ci].1,
                                "disp": x, "bound": b,
                            })
                        })
                        .collect();
                    (true, exc)
                }
                Err(_) => (false, Vec::new()),
            };
            // Smallest exact binding witness with its intended relationship
            // (body-width, border-straightness, head translation, head-mid,
            // cap-ratio, or retained smooth G1). Returned in diagnostics for
            // the experiment adapter to save; the kernel writes no files.
            let intended = hard_names.clone();
            let witness = serde_json::json!({
                "reason": reason,
                "n_hard_rows": n_hard,
                "hard_names": intended,
                "finite_retry_ok": finite_retry_ok,
                "bound_exceeded_points": exceeded,
                "caps": caps_meta,
                "public_caps": public_caps,
                "solver_bounds": bounds,
                "cols": ctx.cols,
                "n_cols": ctx.cols.len(),
                "mat": mat,
                "rhs": rhs,
                "kinds": kinds.iter().map(|k| match k {
                    RowKind::Joint => "Joint",
                    RowKind::White => "White",
                    RowKind::Shape => "Shape",
                    RowKind::Ink => "Ink",
                }).collect::<Vec<_>>(),
                "up_global": up_global,
                "source_oncurve": parsed.oncurve,
                "source_offcurve": parsed.offcurve,
                "upstream_oncurve": fitted.oncurve,
                "upstream_offcurve": fitted.offcurve,
                "r_verts": feature.r_verts,
                "l_verts": feature.l_verts,
                "chain_segs": feature.chain_segs,
                "chain_verts": feature.chain_verts,
                "chain_ctrls": feature.chain_ctrls,
                "cap": feature.cap,
                "stations": feature.stations,
                "w_body": feature.w_body,
                "w_head_mid": feature.w_head_mid,
                "standard": standard,
            });
            return no(
                &format!("shape-solve-{reason}"),
                serde_json::json!({
                    "n_hard_rows": n_hard,
                    "hard_names": intended,
                    "finite_retry_ok": finite_retry_ok,
                    "bound_exceeded_points": exceeded,
                    "caps": caps_meta,
                    "witness": witness,
                }),
            );
        }
    };
    // Joint rows were already filtered consistently before the solve;
    // sharp owned corners rely on orientation/nondegeneracy postchecks.
    let map = joints(parsed);
    let degenerate: Vec<[usize; 3]> = degenerate_triples(&map);
    let ok = match run_prefixes(
        &ctx,
        &sol,
        &weld,
        &owned,
        &degenerate,
        parsed,
        upstream_cmds,
        &fitted,
    ) {
        Ok(v) => v,
        Err(fail) => {
            return no(
                &fail.reason,
                serde_json::json!({ "n_hard_rows": n_hard, "attempts": fail.tried, "extra": fail.extra }),
            );
        }
    };
    let mut selected = FitResult {
        commands: ok.out.clone(),
        applied: true,
        reason: "shape-candidate".to_string(),
        diagnostics: serde_json::json!({}),
    };
    // Post-rounding shape verification against the original source.
    let Ok(cand) = geometry::parse_commands(&selected.commands) else {
        return no("shape-candidate-malformed", serde_json::json!({}));
    };
    let mut checks = serde_json::json!({});
    // Unrounded proposal for all row representation allowances (never the
    // already-rounded candidate pretending to be raw).
    let raw_cont: Vec<[f64; 2]> = {
        let mut raw = up_global.clone();
        for ((v, axis), d) in ctx.cols.iter().zip(sol.iter()) {
            raw[*v][*axis] += d;
        }
        for (dup, canon) in &weld {
            raw[*dup] = raw[*canon];
        }
        raw
    };
    let (cand_r_idx, _) = parsed.contours[0][feature.body_r_seg].endpoints();
    let cand_r = cand.oncurve[cand_r_idx][0];
    let body_w = cand_r - cand.oncurve[bla][0];
    checks["body_width"] = serde_json::json!(body_w);
    if body_w != standard {
        return no("shape-candidate-width", checks);
    }
    let gl = (cand.oncurve[bla][0] * 64.0).round() as i64;
    let gr = (cand_r * 64.0).round() as i64;
    if gl.rem_euclid(64) == 32 || gr.rem_euclid(64) == 32 {
        return no("shape-candidate-phase", checks);
    }
    // One head-mid width target only (S*src_mid/w_body). Quarter and
    // three-quarter stations are not independent hard rows; the
    // translated source profile plus the mid anchor determines them.
    // Verifying all three absolute widths would demand different moves
    // per station and contradict the single shared translation.
    {
        let (seg_idx, t, src_width) = &feature.stations[1];
        let geometry::Segment::Quad { c, a, b } = parsed.contours[0][*seg_idx] else {
            return no("shape-feature-unsupported", serde_json::json!({}));
        };
        let u = 1.0 - t;
        let cx = u * u * cand.oncurve[a][0]
            + 2.0 * u * t * cand.offcurve[c][0]
            + t * t * cand.oncurve[b][0];
        let target = standard * (src_width / feature.w_body);
        checks["station_target"] = serde_json::json!(target);
        let u2 = 1.0 - t;
        let mut srow = vec![0.0; 2 * n];
        srow[2 * global_index(true, cand_r_idx)] += 1.0;
        srow[2 * global_index(true, a)] += -u2 * u2;
        srow[2 * global_index(false, c)] += -2.0 * u2 * t;
        srow[2 * global_index(true, b)] += -t * t;
        let allowance = super::rounding_reserve(&srow, &ctx.cols, &raw_cont, &up_global, &weld);
        checks["station_allowance"] = serde_json::json!(allowance);
        checks["station_width"] = serde_json::json!(cand_r - cx);
        if ((cand_r - cx) - target).abs() > allowance + 1e-9 {
            return no("shape-candidate-profile", checks);
        }
    }
    // Foot/lower curve curvature signs against source for every quad
    // whose control or endpoints moved.
    for seg in &parsed.contours[0] {
        let geometry::Segment::Quad { c, a, b } = *seg else {
            continue;
        };
        let moved = cand.oncurve[a] != fitted.oncurve[a]
            || cand.oncurve[b] != fitted.oncurve[b]
            || cand.offcurve[c] != fitted.offcurve[c];
        if !moved {
            continue;
        }
        let cross = |p: &geometry::Parsed| {
            (p.offcurve[c][0] - p.oncurve[a][0]) * (p.oncurve[b][1] - p.oncurve[a][1])
                - (p.offcurve[c][1] - p.oncurve[a][1]) * (p.oncurve[b][0] - p.oncurve[a][0])
        };
        let (cs, cc) = (cross(parsed), cross(&cand));
        if cs != 0.0 && (cc == 0.0 || cs.signum() != cc.signum()) {
            return no("shape-candidate-curvature", checks);
        }
    }
    // Whole-outline topology under the existing substituted-curve
    // certificate (depth-0 substitution, the raw-certified depth).
    if !curves::compare_substituted(parsed, &fitted, &cand) {
        return no("shape-candidate-topology", checks);
    }
    // Source component survival: the top head quad's endpoint tangent
    // keeps a nonzero horizontal component with the source sign. The top
    // endpoint is the chain boundary vertex adjacent to the cap (highest
    // Y among chain endpoints touching cap ownership), independent of
    // chain traversal direction; the incident quad control gives dx.
    {
        let cap_set: HashSet<usize> = feature
            .cap
            .iter()
            .flat_map(|(cv, lv, rv, _)| [*cv, *lv, *rv])
            .collect();
        let mut top_v: Option<usize> = None;
        let mut top_y = f64::NEG_INFINITY;
        for &v in &feature.chain_verts {
            let y = parsed.oncurve[v][1];
            let adjacent = cap_set.contains(&v) || {
                // Contour-adjacent to a cap vertex counts as boundary.
                let mut adj = false;
                for seg in &parsed.contours[0] {
                    let (a, b) = seg.endpoints();
                    if (a == v && cap_set.contains(&b)) || (b == v && cap_set.contains(&a)) {
                        adj = true;
                        break;
                    }
                }
                adj
            };
            if (adjacent || top_v.is_none()) && y > top_y {
                top_y = y;
                top_v = Some(v);
            }
        }
        // Fall back to the highest chain vertex if no cap adjacency found.
        if top_v.is_none() {
            for &v in &feature.chain_verts {
                let y = parsed.oncurve[v][1];
                if y > top_y {
                    top_y = y;
                    top_v = Some(v);
                }
            }
        }
        let Some(tv) = top_v else {
            return no("shape-candidate-tangent", checks);
        };
        let mut top_quad: Option<(usize, usize, usize)> = None;
        for &sg in &feature.chain_segs {
            if let geometry::Segment::Quad { c, a, b } = parsed.contours[0][sg] {
                if a == tv || b == tv {
                    // Prefer the quad where tv is the higher endpoint.
                    let other = if a == tv { b } else { a };
                    if parsed.oncurve[tv][1] >= parsed.oncurve[other][1] {
                        top_quad = Some((c, a, b));
                        break;
                    }
                    if top_quad.is_none() {
                        top_quad = Some((c, a, b));
                    }
                }
            }
        }
        let Some((c, a, b)) = top_quad else {
            return no("shape-candidate-tangent", checks);
        };
        let end = if parsed.oncurve[a][1] >= parsed.oncurve[b][1] {
            a
        } else {
            b
        };
        let src_dx = parsed.offcurve[c][0] - parsed.oncurve[end][0];
        let cand_dx = cand.offcurve[c][0] - cand.oncurve[end][0];
        checks["tangent_dx"] = serde_json::json!({
            "source": src_dx, "candidate": cand_dx, "joint": tv, "control": c, "end": end,
        });
        if src_dx != 0.0 && (cand_dx == 0.0 || cand_dx.signum() != src_dx.signum()) {
            return no("shape-candidate-tangent", checks);
        }
        // Resolvable-component error against the actual row allowance.
        {
            let mut trow = vec![0.0; 2 * n];
            trow[2 * global_index(false, c)] += 1.0;
            trow[2 * global_index(true, end)] += -1.0;
            let allow = rounding_reserve(&trow, &ctx.cols, &raw_cont, &up_global, &weld);
            checks["tangent_allowance"] = serde_json::json!(allow);
            if (cand_dx - src_dx).abs() > allow + 1e-9 {
                return no("shape-candidate-tangent", checks);
            }
        }
    }
    // Y authority: retained upstream Y bit-identical everywhere.
    for (i, (c, u)) in cand.oncurve.iter().zip(fitted.oncurve.iter()).enumerate() {
        if c[1] != u[1] {
            checks["y_changed"] = serde_json::json!({ "point": i });
            return no("shape-candidate-y", checks);
        }
    }
    for (i, (c, u)) in cand.offcurve.iter().zip(fitted.offcurve.iter()).enumerate() {
        if c[1] != u[1] {
            checks["y_changed"] = serde_json::json!({ "offcurve": i });
            return no("shape-candidate-y", checks);
        }
    }
    // Per-feature movement caps after quantization: the delivered
    // quantized displacement must not exceed the public cap (exact).
    // The solver already reserved one half-quantum inside each cap.
    for (ci, (v, axis)) in ctx.cols.iter().enumerate() {
        if *axis != 0 {
            continue;
        }
        let dq = cand
            .oncurve
            .iter()
            .chain(cand.offcurve.iter())
            .nth(*v)
            .map(|pt| pt[*axis])
            .unwrap_or(f64::NAN)
            - up_global[*v][*axis];
        let cap = public_caps[ci];
        if !(dq.abs() <= cap + 1e-12) {
            checks["bound_exceeded"] = serde_json::json!({ "point": v, "disp": dq, "cap": cap });
            return no("shape-candidate-bound", checks);
        }
    }
    // Body width exact plus both borders straight (constant X).
    for &v in &feature.r_verts[1..] {
        if cand.oncurve[v][0] != cand_r {
            return no("shape-candidate-straightness", checks);
        }
    }
    let cand_l = cand.oncurve[bla][0];
    for &v in &feature.l_verts {
        if cand.oncurve[v][0] != cand_l {
            return no("shape-candidate-straightness", checks);
        }
    }
    // Intended feature rows after rounding against their actual row
    // rounding_reserve (never a global tolerance). Uses the unrounded
    // proposal defined above.
    {
        let check_row = |rvec: &[f64], rhs_v: f64, label: &str| -> Option<serde_json::Value> {
            // Quantized displacement dot row minus rhs.
            let mut qd = 0.0;
            for (v, axis) in &ctx.cols {
                let all: Vec<[f64; 2]> = cand
                    .oncurve
                    .iter()
                    .chain(cand.offcurve.iter())
                    .copied()
                    .collect();
                qd += rvec[2 * v + axis] * (all[*v][*axis] - up_global[*v][*axis]);
            }
            let allowance = rounding_reserve(rvec, &ctx.cols, &raw_cont, &up_global, &weld);
            if (qd - rhs_v).abs() > allowance + 1e-9 {
                return Some(serde_json::json!({
                    "row": label, "error": qd - rhs_v, "allowance": allowance,
                }));
            }
            None
        };
        for (hr, nm) in hard_rows.iter().zip(hard_names.iter()) {
            // rhs = target - up_dot, stored constant is up_dot - target.
            let rhs_v = -hr.2;
            if let Some(diag) = check_row(&hr.1, rhs_v, nm) {
                checks["row_error"] = diag;
                return no("shape-candidate-row", checks);
            }
        }
    }
    // Source-sharp transformed corners: retain turn orientation and
    // nondegeneracy against source (no exact-angle claim). Uses exact
    // rational leg geometry via joints plus coordinate orientation
    // postcheck on the quantized candidate.
    {
        let src_map = joints(parsed);
        let cap_map_post = joints(&captured);
        let up_map_post = joints(&fitted);
        let smooth_post = |j: &usize| -> bool {
            src_map.get(j).is_some_and(|v| v.iter().any(|o| o.smooth))
                || cap_map_post
                    .get(j)
                    .is_some_and(|v| v.iter().any(|o| o.smooth))
                || up_map_post
                    .get(j)
                    .is_some_and(|v| v.iter().any(|o| o.smooth))
        };
        for (j, occs) in &src_map {
            for occ in occs {
                if occ.smooth || occ.degenerate {
                    continue;
                }
                // Conservative continuity: raw/captured/upstream-smooth
                // joins stay hard G1 (captured source is the producer
                // proof; raw 1ULP noise never reclassifies them).
                if smooth_post(j) {
                    continue;
                }
                let owned_here = feature.r_verts.contains(j)
                    || feature.l_verts.contains(j)
                    || feature.chain_verts.contains(j)
                    || feature.cap.is_some_and(|(cv, _, _, _)| cv == *j);
                if !owned_here {
                    continue;
                }
                let leg =
                    |p: &geometry::Parsed, s: super::SegRef, at_joint_out: bool| -> [f64; 2] {
                        match (s, at_joint_out) {
                            (super::SegRef::Line { b, .. }, true) => p.oncurve[b],
                            (super::SegRef::Line { a, .. }, false) => p.oncurve[a],
                            (super::SegRef::Quad { off, .. }, _) => {
                                let no = p.oncurve.len();
                                if off >= no {
                                    p.offcurve[off - no]
                                } else {
                                    p.oncurve[off]
                                }
                            }
                        }
                    };
                let fin_s = leg(parsed, occ.prev, false);
                let fout_s = leg(parsed, occ.seg, true);
                let lin_s = [
                    parsed.oncurve[*j][0] - fin_s[0],
                    parsed.oncurve[*j][1] - fin_s[1],
                ];
                let lout_s = [
                    fout_s[0] - parsed.oncurve[*j][0],
                    fout_s[1] - parsed.oncurve[*j][1],
                ];
                let cs = lin_s[0] * lout_s[1] - lin_s[1] * lout_s[0];
                if cs == 0.0 {
                    continue;
                }
                let fin_c = leg(&cand, occ.prev, false);
                let fout_c = leg(&cand, occ.seg, true);
                let lin_c = [
                    cand.oncurve[*j][0] - fin_c[0],
                    cand.oncurve[*j][1] - fin_c[1],
                ];
                let lout_c = [
                    fout_c[0] - cand.oncurve[*j][0],
                    fout_c[1] - cand.oncurve[*j][1],
                ];
                if !(lin_c[0].hypot(lin_c[1]) > 0.0 && lout_c[0].hypot(lout_c[1]) > 0.0) {
                    checks["degenerate"] = serde_json::json!({ "joint": j });
                    return no("shape-candidate-degenerate", checks);
                }
                let cc = lin_c[0] * lout_c[1] - lin_c[1] * lout_c[0];
                if cc == 0.0 || cc.signum() != cs.signum() {
                    let up_smooth = up_map_post
                        .get(j)
                        .is_some_and(|v| v.iter().any(|o| o.smooth));
                    let src_smooth = src_map.get(j).is_some_and(|v| v.iter().any(|o| o.smooth));
                    let cap_smooth = cap_map_post
                        .get(j)
                        .is_some_and(|v| v.iter().any(|o| o.smooth));
                    checks["orientation"] = serde_json::json!({
                        "joint": j, "source": cs, "candidate": cc,
                        "src_smooth": src_smooth, "cap_smooth": cap_smooth,
                        "up_smooth": up_smooth,
                        "in_r": feature.r_verts.contains(j),
                        "in_l": feature.l_verts.contains(j),
                        "in_chain": feature.chain_verts.contains(j),
                        "in_cap": feature.cap.is_some_and(|(cv, _, _, _)| cv == *j),
                        "chain_segs": feature.chain_segs,
                        "cap": feature.cap,
                    });
                    return no("shape-candidate-orientation", checks);
                }
            }
        }
    }
    selected.diagnostics["model"] = serde_json::json!("coupled-shape-auto-01");
    selected.diagnostics["shape_prototype"] = serde_json::json!({
        "standard": standard, "peak": peak, "qp": qp.as_ref().map(qp_json),
        "n_hard_rows": n_hard, "hard_names": hard_names, "checks": checks,
        "caps": caps_meta,
    });
    Ok(selected)
}
