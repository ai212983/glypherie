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
    assemble, degenerate_triples, hard_solve, joints, prefix_diag, qp_json, recognize,
    restricted_matrix, run_prefixes, weld_map, with_effectibility, WhiteSpec, DEPTHS,
};
use crate::{fail, probe::FittedCommand, Error};
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
    let mut depth = None;
    for candidate in DEPTHS {
        if curves::certify_parsed(&parsed, candidate).is_ok() {
            depth = Some(candidate);
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
    if !(size_px.is_finite() && size_px > 0.0) {
        return Err(fail("curve model requires finite positive size"));
    }
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
