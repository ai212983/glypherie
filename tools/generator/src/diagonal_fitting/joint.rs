//! Straight-crossing joint diagonal fit (native port of the frozen experiment).
//!
//! Source: Hobby 1993 section 3.5, (14)-(16): approximate reflection with
//! adjustable map Mbar and per-endpoint residuals; the audit-supported
//! normal (D_y,-D_x) replaces the stored D-dot form, which measures sliding,
//! not separation. Hobby 1993 sections 3.6/4.2, (17): relative-error
//! coupling with the printed 9-radian weight. Hobby 1993 section 2, Fig. 8:
//! scan conversion turns on pixels whose centers lie inside; an odd snapped
//! waist width is deterministic only with its axis on a pixel center, an
//! even one on a boundary. Hersch 1993 section 5, Figs. 17-18:
//! symmetry-center phase and centering between extremal points. The parity
//! half and the waist/axis recognition below are project adaptations; hard
//! (11)-(13) rows are excluded because they dominate the solve and move
//! absolute widths.
//!
//! Project adaptations: widths reuse the maintained width-only system and
//! its exact upstream fallback; the joint couples (16) symmetry rows about
//! a fixed parity axis with soft (17) relative-width rows. Curves abstain.
//! Any infeasible gate returns the exact upstream commands with
//! `applied=false`. Only malformed, non-finite or out-of-range input is an
//! error. Runtime never uses experiments, Python, subprocesses or corpus
//! corrections.

use super::{
    abstain, achieved_json, achieved_widths, assemble, crossing, geometry, mean_widths, qp,
    reference_meta, validate, FitResult, Reference, Sample, HEADROOM, MAX_COMMANDS,
};
use crate::{fail, probe::FittedCommand, Error};
use std::collections::{HashMap, HashSet};

/// Symmetry match tolerance in outline units (prototype `EPS_PARITY`).
const EPS_PARITY: f64 = 0.25;
/// Hobby (16) symmetry weight scale (prototype `ALPHA6`).
const ALPHA6: f64 = 5e5;
/// Fixed station fractions are owned by the baseline width system.

fn dot(a: &[f64], b: &[f64]) -> f64 {
    a.iter().zip(b.iter()).map(|(x, y)| x * y).sum()
}

/// Slab-interval summary of the source outline along x.
struct AxisLocus {
    cmin: f64,
    cmax: f64,
    n: usize,
    skipped: usize,
}

/// Source approximate-axis interval from slab-end pair midpoints.
///
/// Native port of the symmetry-placement slab interval: sorted crossings at
/// each slab end pair outer-to-inner, an odd middle crossing standing alone.
/// Exactly symmetric input yields the axis at every measurement. Straight
/// outlines only; curves return `None`.
fn axis_interval(source: &[FittedCommand]) -> Option<AxisLocus> {
    let parsed = geometry::parse_commands(source).ok()?;
    let mut segments: Vec<(usize, usize, [f64; 2], [f64; 2])> = Vec::new();
    for contour in &parsed.contours {
        for seg in contour {
            match *seg {
                geometry::Segment::Line { a, b } => {
                    segments.push((a, b, parsed.oncurve[a], parsed.oncurve[b]))
                }
                _ => return None,
            }
        }
    }
    if segments.is_empty() {
        return None;
    }
    let mut crit: Vec<f64> = parsed.oncurve.iter().map(|p| p[1]).collect();
    crit.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    crit.dedup();
    if crit.len() < 2 {
        return None;
    }
    let mut meas = Vec::new();
    let mut skipped = 0usize;
    for ends in crit.windows(2) {
        let (lo, hi) = (ends[0], ends[1]);
        if !(hi > lo) {
            continue;
        }
        let mut span = Vec::new();
        for (_, _, a, b) in &segments {
            let (u1, v1, u2, v2) = (a[1], a[0], b[1], b[0]);
            if u1 == u2 {
                continue;
            }
            if (u1 <= lo && u2 >= hi) || (u2 <= lo && u1 >= hi) {
                span.push((u1, v1, u2, v2));
            }
        }
        if span.len() < 2 {
            skipped += 1;
            continue;
        }
        for end in [lo, hi] {
            let mut xs: Vec<f64> = span
                .iter()
                .map(|(u1, v1, u2, v2)| v1 + (end - u1) * (v2 - v1) / (u2 - u1))
                .collect();
            xs.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
            let n = xs.len();
            for i in 0..n / 2 {
                meas.push((xs[i] + xs[n - 1 - i]) / 2.0);
            }
            if n % 2 == 1 {
                meas.push(xs[n / 2]);
            }
        }
    }
    if meas.is_empty() {
        return None;
    }
    Some(AxisLocus {
        cmin: meas.iter().cloned().fold(f64::INFINITY, f64::min),
        cmax: meas.iter().cloned().fold(f64::NEG_INFINITY, f64::max),
        n: meas.len(),
        skipped,
    })
}

/// Internal crossing neck with separated ink spans above and below.
struct Waist {
    width: f64,
    mid: f64,
    level: f64,
}

/// Restricted crossing-neck recognition: Hersch center-phase applies to a
/// waist, never to a silhouette tip mistaken for a thin central stroke.
/// Exact critical sections make collinear subdivision immaterial.
fn waist_from_slabs(parsed: &geometry::Parsed) -> Option<Waist> {
    let points = &parsed.oncurve;
    let mut levels: Vec<f64> = points.iter().map(|p| p[1]).collect();
    levels.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    levels.dedup();
    let mut edges = Vec::new();
    for contour in &parsed.contours {
        for seg in contour {
            if let geometry::Segment::Line { a, b } = *seg {
                if points[a][1] != points[b][1] {
                    edges.push((points[a], points[b]));
                }
            }
        }
    }
    let cross =
        |a: [f64; 2], b: [f64; 2], at: f64| a[0] + (at - a[1]) * (b[0] - a[0]) / (b[1] - a[1]);
    // (span count, slab-end width/mid/level samples).
    let mut slabs: Vec<(usize, Vec<(f64, f64, f64)>)> = Vec::new();
    for ends in levels.windows(2) {
        let (lo, hi) = (ends[0], ends[1]);
        let y = (lo + hi) / 2.0;
        let mut active: Vec<([f64; 2], [f64; 2])> = edges
            .iter()
            .filter(|(a, b)| a[1].min(b[1]) < y && y < a[1].max(b[1]))
            .copied()
            .collect();
        active.sort_by(|a, b| {
            cross(a.0, a.1, y)
                .partial_cmp(&cross(b.0, b.1, y))
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        let spans = if active.len() % 2 == 0 {
            active.len() / 2
        } else {
            0
        };
        let mut endpoints = Vec::new();
        if spans == 1 {
            for at in [lo, hi] {
                let mut xs: Vec<f64> = active.iter().map(|(a, b)| cross(*a, *b, at)).collect();
                xs.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
                endpoints.push((xs[1] - xs[0], (xs[0] + xs[1]) / 2.0, at));
            }
        }
        slabs.push((spans, endpoints));
    }
    let mut candidates: Vec<(f64, f64, f64)> = Vec::new();
    let mut i = 0;
    while i < slabs.len() {
        if slabs[i].0 != 1 {
            i += 1;
            continue;
        }
        let start = i;
        while i < slabs.len() && slabs[i].0 == 1 {
            i += 1;
        }
        if start == 0 || i == slabs.len() || slabs[start - 1].0.min(slabs[i].0) < 2 {
            continue;
        }
        let samples: Vec<(f64, f64, f64)> = slabs[start..i]
            .iter()
            .flat_map(|(_, e)| e.iter().copied())
            .collect();
        let Some(best) = samples
            .iter()
            .min_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal))
            .copied()
        else {
            continue;
        };
        if best.0 > 0.0 && best.0 < samples[0].0.min(samples[samples.len() - 1].0) {
            candidates.push(best);
        }
    }
    if candidates.len() != 1 {
        return None;
    }
    Some(Waist {
        width: candidates[0].0,
        mid: candidates[0].1,
        level: candidates[0].2,
    })
}

fn decide_parity_target(
    axis_src: f64,
    predicted: f64,
    rel_med: f64,
    prepped: &[super::PreppedInfo],
) -> Result<f64, &'static str> {
    if !(predicted > 0.0) {
        return Err("no-waist");
    }
    let pair_mean = prepped
        .iter()
        .map(|info| info.src_widths.iter().sum::<f64>() / info.src_widths.len() as f64)
        .sum::<f64>()
        / prepped.len() as f64;
    if crossing::parity_target(axis_src, pair_mean * (1.0 + rel_med))
        != crossing::parity_target(axis_src, predicted)
    {
        return Err("parity-ambiguous");
    }
    crossing::parity_target(axis_src, predicted).ok_or("parity-ambiguous")
}

#[derive(Clone)]
struct Side {
    pair: String,
    p0: [f64; 2],
    p1: [f64; 2],
    i0: usize,
    i1: usize,
    t0: f64,
    t1: f64,
}

fn reflect(point: [f64; 2], axis: f64) -> [f64; 2] {
    [2.0 * axis - point[0], point[1]]
}

/// Segment-to-segment reflection matches under M about the source axis.
///
/// The returned second side is re-encoded to the matching orientation, so
/// corresponding coefficient indices always reflect that orientation.
fn match_borders(sides: &[Side], axis: f64, epsilon: f64) -> Vec<(Side, Side, f64)> {
    let mut matches = Vec::new();
    let mut seen: HashSet<(usize, usize)> = HashSet::new();
    for (i, s) in sides.iter().enumerate() {
        let (rp0, rp1) = (reflect(s.p0, axis), reflect(s.p1, axis));
        let mut best: Option<(f64, usize, bool)> = None;
        for (j, o) in sides.iter().enumerate() {
            if i == j || s.pair == o.pair {
                continue;
            }
            for reversed in [false, true] {
                let (q0, q1) = if reversed { (o.p1, o.p0) } else { (o.p0, o.p1) };
                let dist = (rp0[0] - q0[0])
                    .hypot(rp0[1] - q0[1])
                    .max((rp1[0] - q1[0]).hypot(rp1[1] - q1[1]));
                if best.is_none_or(|(d, _, _)| dist < d) {
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
        let o = &sides[j];
        let second = if reversed {
            Side {
                p0: o.p1,
                p1: o.p0,
                i0: o.i1,
                i1: o.i0,
                t0: 1.0 - o.t1,
                t1: 1.0 - o.t0,
                ..o.clone()
            }
        } else {
            o.clone()
        };
        matches.push((s.clone(), second, dist));
    }
    matches
}

/// Hobby (16) rows about the fixed parity axis, source mismatch retained.
fn symmetry_rows(
    system: &super::System,
    matches: &[(Side, Side, f64)],
    axis_src: f64,
    f_k: f64,
    size_px: f64,
) -> Vec<(Vec<f64>, f64)> {
    let mut rows = Vec::new();
    let flat: Vec<f64> = system.points.iter().flat_map(|p| [p[0], p[1]]).collect();
    for (first, second, _) in matches {
        let (a1, b1, a2, b2) = (first.p0, first.p1, second.p0, second.p1);
        let direct = [
            -(b1[0] - a1[0]) + (b2[0] - a2[0]),
            (b1[1] - a1[1]) + (b2[1] - a2[1]),
        ];
        let norm = direct[0].hypot(direct[1]);
        if !(norm > 0.0) {
            continue;
        }
        let normal = [direct[1] / norm, -direct[0] / norm];
        let dab = norm / 2.0;
        // Audit-supported normal: the stored D-dot form measures sliding,
        // so the normal here is (D_y,-D_x), with mismatch against the
        // reflected source retained in the constants.
        let src = (
            normal[0] * (a2[0] - (2.0 * axis_src - a1[0])) + normal[1] * (a2[1] - a1[1]),
            normal[0] * (b2[0] - (2.0 * axis_src - b1[0])) + normal[1] * (b2[1] - b1[1]),
        );
        // Endpoint rows at t0 then t1, matching the prototype order.
        let mut built = Vec::new();
        for (ta, tb, m) in [(first.t0, second.t0, src.0), (first.t1, second.t1, src.1)] {
            let sample_a = Sample::affine(first.i0, 1.0 - ta, first.i1, ta);
            let sample_b = Sample::affine(second.i0, 1.0 - tb, second.i1, tb);
            let mut row = system.projected(&sample_a, [normal[0], -normal[1]], None);
            let other = system.projected(&sample_b, normal, None);
            for (r, o) in row.iter_mut().zip(other.iter()) {
                *r += *o;
            }
            let constant = dot(&row, &flat) - normal[0] * f_k - m;
            built.push((row, constant));
        }
        let (ra, ca) = built.remove(0);
        let (rb, cb) = built.remove(0);
        let factor = (ALPHA6 / size_px.powi(3) * dab).sqrt();
        let sum: Vec<f64> = ra
            .iter()
            .zip(rb.iter())
            .map(|(x, y)| (x + y) * (0.25f64).sqrt() * factor)
            .collect();
        let diff: Vec<f64> = rb
            .iter()
            .zip(ra.iter())
            .map(|(x, y)| (x - y) * (1.0f64 / 12.0).sqrt() * factor)
            .collect();
        rows.push((sum, (ca + cb) * (0.25f64).sqrt() * factor));
        rows.push((diff, (cb - ca) * (1.0f64 / 12.0).sqrt() * factor));
    }
    rows
}

fn median(values: &[f64]) -> f64 {
    let mut sorted = values.to_vec();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let n = sorted.len();
    if n % 2 == 1 {
        sorted[n / 2]
    } else {
        (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0
    }
}

fn bits_of(cmd: &FittedCommand, axis: usize) -> Option<u32> {
    match cmd {
        FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => {
            Some(if axis == 0 { x.to_bits() } else { y.to_bits() })
        }
        FittedCommand::QuadTo(_, _, x, y) | FittedCommand::CurveTo(_, _, _, _, x, y) => {
            Some(if axis == 0 { x.to_bits() } else { y.to_bits() })
        }
        FittedCommand::Close => None,
    }
}

/// Fit diagonal crossings with one joint symmetry-plus-width solve.
///
/// The joint system couples every diagonal station to every reference anchor
/// through (17) width rows while (16) symmetry rows hold the crossing phase
/// about the fixed parity axis; shared vertices carry one unknown. Only the
/// X axis moves; pins and native-owned components stay at upstream exactly.
/// The candidate rounds moved coordinates to 26.6 and must preserve
/// orientation, upstream portion topology and station ink, or the exact
/// upstream commands return with the validity evidence.
pub fn fit(
    source: &[FittedCommand],
    original_upstream: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> Result<FitResult, Error> {
    fit_impl::<false>(source, original_upstream, size_px, reference, native_axes)
}

/// Selection discards unapplied-stage diagnostics; standalone capture retains them.
pub(super) fn fit_for_selection(
    source: &[FittedCommand],
    original_upstream: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> Result<FitResult, Error> {
    fit_impl::<true>(source, original_upstream, size_px, reference, native_axes)
}

fn fit_impl<const SELECTING: bool>(
    source: &[FittedCommand],
    original_upstream: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> Result<FitResult, Error> {
    if !(size_px.is_finite() && size_px > 0.0) {
        return Err(fail("joint width requires finite positive size"));
    }
    if !geometry::check_correspondence(source, original_upstream) {
        return Ok(abstain(
            original_upstream,
            "no-correspondence",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    let (Ok(parsed), Ok(fitted)) = (
        geometry::parse_commands(source),
        geometry::parse_commands(original_upstream),
    ) else {
        return Ok(abstain(
            original_upstream,
            "malformed-commands",
            serde_json::json!({"size_px": size_px}),
        ));
    };
    if source.len() > MAX_COMMANDS || original_upstream.len() > MAX_COMMANDS {
        return Ok(abstain(
            original_upstream,
            "oversize-outline",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    for contour in &parsed.contours {
        for seg in contour {
            if !seg.is_line() {
                return Ok(abstain(
                    original_upstream,
                    "curves-unsupported",
                    serde_json::json!({"size_px": size_px}),
                ));
            }
        }
    }
    if reference.anchors.is_empty() {
        return Ok(abstain(
            original_upstream,
            "no-reference-anchors",
            serde_json::json!({"size_px": size_px}),
        ));
    }
    // Dead-work elimination (https://llvm.org/docs/Passes.html#adce-aggressive-dead-code-elimination):
    // these source-only prerequisites already reject the entire stage below.
    // Selection can check them before recognition because it discards failed
    // diagnostics. Retain their values, arithmetic and all later delivery guards.
    let (selected_locus, selected_waist) = if SELECTING {
        let Some(locus) = axis_interval(source) else {
            return Ok(abstain(
                original_upstream,
                "axis-uncontained",
                serde_json::json!({}),
            ));
        };
        if locus.cmax - locus.cmin > EPS_PARITY {
            return Ok(abstain(
                original_upstream,
                "axis-uncontained",
                serde_json::json!({}),
            ));
        }
        let Some(waist) = waist_from_slabs(&parsed) else {
            return Ok(abstain(
                original_upstream,
                "no-waist",
                serde_json::json!({}),
            ));
        };
        (Some(locus), Some(waist))
    } else {
        (None, None)
    };
    let (portions, curve_boxes, loops, flats) = geometry::split_visible(&parsed, true);
    let (pairs, mut skipped) = geometry::recognize(&portions, &loops, true);
    let mut pins: HashSet<usize> = HashSet::new();
    for pair in geometry::upright_pairs(&pairs) {
        for side in [&pair.a, &pair.b] {
            pins.insert(side.i0);
            pins.insert(side.i1);
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
    let straights = loops.clone();
    let mut prepped: Vec<super::PreppedInfo> = Vec::new();
    for pair in &pairs {
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
            Ok(info) => {
                let bound = info
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
                prepped.push(super::PreppedInfo {
                    id: info.id,
                    a: info.a,
                    b: info.b,
                    normal: info.normal,
                    stations: info.stations,
                    src_widths: info.src_widths,
                    fit_widths: info.fit_widths,
                    arc: info.arc,
                    span_lo: info.span_lo,
                    span_hi: info.span_hi,
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
    let skipped_json: Vec<serde_json::Value> = skipped
        .iter()
        .map(|s| serde_json::json!({"pair": [s.pair.0, s.pair.1], "reason": s.reason}))
        .collect();
    let mut sorted_pins: Vec<usize> = pins.iter().copied().collect();
    sorted_pins.sort();
    let fixed_meta = serde_json::json!({
        "anchors": sorted_pins,
        "native_axes": [native_axes[0], native_axes[1]],
    });
    if prepped.is_empty() {
        return Ok(abstain(
            original_upstream,
            "all-abstained",
            serde_json::json!({"skipped": skipped_json, "fixed": fixed_meta}),
        ));
    }
    let Some(locus) = selected_locus.or_else(|| axis_interval(source)) else {
        return Ok(abstain(
            original_upstream,
            "axis-uncontained",
            serde_json::json!({"skipped": skipped_json}),
        ));
    };
    if locus.cmax - locus.cmin > EPS_PARITY {
        return Ok(abstain(
            original_upstream,
            "axis-uncontained",
            serde_json::json!({
                "skipped": skipped_json,
                "locus": {"cmin": locus.cmin, "cmax": locus.cmax,
                          "n": locus.n, "skipped_slabs": locus.skipped},
            }),
        ));
    }
    let Some(waist) = selected_waist.or_else(|| waist_from_slabs(&parsed)) else {
        return Ok(abstain(
            original_upstream,
            "no-waist",
            serde_json::json!({"skipped": skipped_json}),
        ));
    };
    let rel_med = median(
        &reference
            .anchors
            .iter()
            .map(|a| a.rel)
            .collect::<Vec<f64>>(),
    );
    let predicted = waist.width * (1.0 + rel_med);
    let axis_src = locus.mid();
    let target = match decide_parity_target(axis_src, predicted, rel_med, &prepped) {
        Ok(target) => target,
        Err(reason) => {
            return Ok(abstain(
                original_upstream,
                reason,
                serde_json::json!({"skipped": skipped_json}),
            ));
        }
    };
    let f_k = 2.0 * target;
    let mut sides = Vec::new();
    for info in &prepped {
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
            original_upstream,
            "no-symmetry-matches",
            serde_json::json!({"skipped": skipped_json}),
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
    let symmetry = symmetry_rows(&system, &matches, axis_src, f_k, size_px);
    // The distortion and relative-width rows remain soft; symmetry rows
    // alone constrain the parity phase (prototype `group != symmetry`).
    let width_rows: Vec<(&Vec<f64>, f64)> = system
        .rows
        .iter()
        .map(|(_, row, constant)| (row, *constant))
        .collect();
    let base = parsed.oncurve.clone();
    let upstream = fitted_coords.clone();
    let gaps: Vec<f64> = upstream
        .iter()
        .zip(base.iter())
        .flat_map(|(u, b)| [u[0] - b[0], u[1] - b[1]])
        .collect();
    let mut columns: Vec<usize> = var_verts
        .iter()
        .filter(|v| !fixed.contains_key(&(**v, 0)))
        .map(|v| 2 * *v)
        .collect();
    columns.sort();
    if columns.is_empty() {
        return Ok(abstain(
            original_upstream,
            "no-horizontal-freedom",
            serde_json::json!({"skipped": skipped_json}),
        ));
    }
    let project = |row: &[f64], constant: f64| -> (Vec<f64>, f64) {
        (
            columns.iter().map(|c| row[*c]).collect(),
            -dot(row, &gaps) - constant,
        )
    };
    let a_mat: Vec<Vec<f64>> = width_rows.iter().map(|(r, c)| project(r, *c).0).collect();
    let b_vec: Vec<f64> = width_rows.iter().map(|(r, c)| project(r, *c).1).collect();
    let g_mat: Vec<Vec<f64>> = symmetry.iter().map(|(r, c)| project(r, *c).0).collect();
    let h_vec: Vec<f64> = symmetry.iter().map(|(r, c)| project(r, *c).1).collect();
    let bounds: Vec<f64> = columns
        .iter()
        .map(|col| {
            let v = col / 2;
            prepped
                .iter()
                .filter(|info| [info.a.i0, info.a.i1, info.b.i0, info.b.i1].contains(&v))
                .map(|info| info.bound)
                .fold(f64::INFINITY, f64::min)
        })
        .collect();
    let Some((delta, qp_info)) = qp::bounded_equalities(&a_mat, &b_vec, &g_mat, &h_vec, &bounds)
    else {
        return Ok(abstain(
            original_upstream,
            "phase-bounds-incompatible",
            serde_json::json!({"skipped": skipped_json}),
        ));
    };
    let mut flat_delta = vec![0.0; gaps.len()];
    for (k, col) in columns.iter().enumerate() {
        flat_delta[*col] = delta[k];
    }
    let mut peaks: HashMap<String, f64> = HashMap::new();
    for info in &prepped {
        let peak = [info.a.i0, info.a.i1, info.b.i0, info.b.i1]
            .iter()
            .map(|v| flat_delta[2 * *v].hypot(flat_delta[2 * *v + 1]))
            .fold(0.0, f64::max);
        peaks.insert(info.id.clone(), peak);
    }
    let over: Vec<&super::PreppedInfo> = prepped
        .iter()
        .filter(|info| peaks[&info.id] > info.bound)
        .collect();
    if !over.is_empty()
        && over
            .iter()
            .map(|info| peaks[&info.id] - info.bound)
            .fold(0.0, f64::max)
            > 1e-9
    {
        return Ok(abstain(
            original_upstream,
            "movement-budget",
            serde_json::json!({"skipped": skipped_json}),
        ));
    }
    for info in prepped.iter_mut() {
        info.peak = peaks[&info.id];
    }
    let table = geometry::index_map(original_upstream);
    let mut candidate = original_upstream.to_vec();
    let flat_up: Vec<f64> = upstream.iter().flat_map(|p| [p[0], p[1]]).collect();
    let flat_cand: Vec<f64> = flat_up
        .iter()
        .zip(flat_delta.iter())
        .map(|(u, d)| u + d)
        .collect();
    let mut sorted_verts: Vec<usize> = var_verts.iter().copied().collect();
    sorted_verts.sort();
    for v in sorted_verts {
        let Some(pos) = table.get(v).copied().flatten() else {
            continue;
        };
        for axis in 0..2 {
            if fixed.contains_key(&(v, axis)) {
                continue;
            }
            let value = flat_cand[2 * v + axis];
            if value == flat_up[2 * v + axis] {
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
    if candidate == original_upstream {
        return Ok(abstain(
            original_upstream,
            "no-movement",
            serde_json::json!({"skipped": skipped_json}),
        ));
    }
    let mut validity = validate(
        &parsed,
        &fitted,
        original_upstream,
        &candidate,
        &portions,
        &mut prepped,
        &pins,
        &owned,
        source,
    );
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
    // Exact f32-bits pins: coordinate equality also holds across signed
    // zero, but bit identity is the upstream contract here.
    if validity.ok {
        let cand_table = geometry::index_map(&candidate);
        let mut inverted: HashMap<usize, usize> = HashMap::new();
        for (idx, pos) in cand_table.iter().enumerate() {
            if let Some(p) = pos {
                inverted.insert(*p, idx);
            }
        }
        let mut bits_ok = true;
        for (pos, cmd) in candidate.iter().enumerate() {
            let Some(&idx) = inverted.get(&pos) else {
                continue;
            };
            for axis in owned.iter().copied() {
                if bits_of(cmd, axis) != bits_of(&original_upstream[pos], axis) {
                    let _ = idx;
                    bits_ok = false;
                }
            }
        }
        for pin in pins.iter() {
            let Some(pos) = cand_table.get(*pin).copied().flatten() else {
                continue;
            };
            for axis in 0..2 {
                if bits_of(&candidate[pos], axis) != bits_of(&original_upstream[pos], axis) {
                    bits_ok = false;
                }
            }
        }
        if !bits_ok {
            validity.ok = false;
            validity.stage = "pins-bits-changed".to_string();
        }
    }
    let match_cost = |flat: &[f64]| -> f64 {
        width_rows
            .iter()
            .map(|(row, constant)| (dot(row, flat) + constant).powi(2))
            .sum()
    };
    let sym_cost = |flat: &[f64]| -> f64 {
        symmetry
            .iter()
            .map(|(row, constant)| (dot(row, flat) + constant).powi(2))
            .sum()
    };
    let flat_base_up: Vec<f64> = upstream
        .iter()
        .zip(base.iter())
        .flat_map(|(u, b)| [u[0] - b[0], u[1] - b[1]])
        .collect();
    let cost_upstream = match_cost(&flat_base_up);
    let sym_upstream = sym_cost(&flat_base_up);
    let parsed_cand = geometry::parse_commands(&candidate);
    let (cost_candidate, sym_candidate) = match parsed_cand {
        Ok(cand) => {
            let flat: Vec<f64> = cand
                .oncurve
                .iter()
                .zip(base.iter())
                .flat_map(|(c, b)| [c[0] - b[0], c[1] - b[1]])
                .collect();
            (Some(match_cost(&flat)), Some(sym_cost(&flat)))
        }
        Err(()) => (None, None),
    };
    let cost_ok = cost_candidate.is_some_and(|c| c < cost_upstream);
    let symmetry_ok = sym_candidate.is_some_and(|c| c < sym_upstream);
    validity.cost_upstream = Some(cost_upstream);
    validity.cost_candidate = cost_candidate;
    validity.cost_ok = cost_ok;
    if !cost_ok {
        validity.ok = false;
        validity.stage = "no-cost-decrease".to_string();
    } else if !symmetry_ok {
        validity.ok = false;
        validity.stage = "no-symmetry-decrease".to_string();
    }
    let achieved = achieved_widths(&prepped, &candidate);
    let widths = mean_widths(&achieved);
    let diagnostics = serde_json::json!({
        "epsilon": EPS_PARITY,
        "axis_src": axis_src,
        "qp": {"iterations": qp_info.iterations, "equality_error": qp_info.equality_error,
                "stationarity_error": qp_info.stationarity_error, "active": qp_info.active},
        "locus": {"cmin": locus.cmin, "cmax": locus.cmax,
                  "n": locus.n, "skipped_slabs": locus.skipped},
        "waist": {"width": waist.width, "mid": waist.mid, "level": waist.level,
                  "predicted": predicted, "rel_med": rel_med},
        "parity_target": target,
        "f_k": f_k,
        "matches": matches.len(),
        "symmetry_upstream": sym_upstream,
        "symmetry_candidate": sym_candidate,
        "symmetry_ok": symmetry_ok,
    });
    if !validity.ok {
        let fallback = achieved_widths(&prepped, original_upstream);
        return Ok(FitResult {
            commands: original_upstream.to_vec(),
            applied: false,
            reason: "invalid-candidate".to_string(),
            diagnostics: serde_json::json!({
                "validity": super::validity_json(&validity),
                "pairs": achieved_json(&prepped, &achieved),
                "skipped": skipped_json,
                "diagnostics": diagnostics,
                "movement": peaks.values().cloned().fold(0.0, f64::max),
                "bound": prepped.iter().map(|i| i.bound).fold(f64::INFINITY, f64::min),
                "size_px": size_px,
                "widths": mean_widths(&fallback),
                "reference": reference_meta(reference),
            }),
        });
    }
    Ok(FitResult {
        commands: candidate,
        applied: true,
        reason: "applied-joint".to_string(),
        diagnostics: serde_json::json!({
            "validity": super::validity_json(&validity),
            "pairs": achieved_json(&prepped, &achieved),
            "skipped": skipped_json,
            "diagnostics": diagnostics,
            "movement": peaks.values().cloned().fold(0.0, f64::max),
            "bound": prepped.iter().map(|i| i.bound).fold(f64::INFINITY, f64::min),
            "size_px": size_px,
            "widths": widths,
            "reference": reference_meta(reference),
        }),
    })
}

impl AxisLocus {
    fn mid(&self) -> f64 {
        (self.cmin + self.cmax) / 2.0
    }
}

#[cfg(test)]
mod correspondence_tests {
    use super::*;

    #[test]
    fn reflected_portions_keep_their_own_affine_coordinates() {
        // Hobby (16) matches points on two source portions. Their parent
        // edges can have different parameter intervals after subdivision.
        let system =
            super::super::System::new(vec![[-2.0, 0.0], [-4.0, 4.0], [2.0, 0.0], [4.0, 4.0]], 16.0);
        let first = Side {
            pair: "a".into(),
            p0: [-2.5, 1.0],
            p1: [-3.5, 3.0],
            i0: 0,
            i1: 1,
            t0: 0.25,
            t1: 0.75,
        };
        let second = Side {
            pair: "b".into(),
            p0: [3.0, 2.0],
            p1: [3.8, 3.6],
            i0: 2,
            i1: 3,
            t0: 0.5,
            t1: 0.9,
        };
        let rows = symmetry_rows(&system, &[(first, second, 0.0)], 0.0, 0.0, 16.0);
        // Mean endpoint weights on the second edge are 0.3 and 0.7;
        // borrowing the first edge's interval would incorrectly give 1:1.
        assert!((rows[0].0[4] / rows[0].0[6] - 3.0 / 7.0).abs() < 1e-12);
        // The two portions span 0.5 and 0.4 of their parent edges.
        assert!((rows[1].0[4] / rows[1].0[0] - 0.8).abs() < 1e-12);
    }
}

#[cfg(test)]
mod parity_decision_tests {
    use super::super::geometry::Portion;
    use super::super::PreppedInfo;
    use super::decide_parity_target;

    fn info_with_widths(src_widths: Vec<f64>) -> PreppedInfo {
        let blank = Portion {
            contour: 0,
            seg: 0,
            t0: 0.0,
            t1: 0.0,
            p0: [0.0, 0.0],
            p1: [0.0, 0.0],
            i0: 0,
            i1: 0,
            hidden: false,
            unknown: false,
        };
        PreppedInfo {
            id: String::new(),
            a: blank.clone(),
            b: blank,
            normal: [0.0, 0.0],
            stations: Vec::new(),
            src_widths,
            fit_widths: Vec::new(),
            arc: 0.0,
            span_lo: 0.0,
            span_hi: 0.0,
            bound: 0.0,
            prefix: 0.0,
            peak: 0.0,
            rounded_peak: None,
            pairs: Vec::new(),
            feet: serde_json::Value::Null,
        }
    }

    #[test]
    fn no_waist_rejects_nonpositive_and_nan_prediction() {
        let empty: Vec<PreppedInfo> = Vec::new();
        for predicted in [0.0, -1.0, f64::NAN] {
            assert!(matches!(
                decide_parity_target(0.0, predicted, 0.0, &empty),
                Err("no-waist")
            ));
        }
    }

    #[test]
    fn unequal_groups_average_with_nonzero_rel() {
        let prepped = [
            info_with_widths(vec![1.0, 3.0]),
            info_with_widths(vec![5.0]),
        ];
        assert_eq!(decide_parity_target(0.25, 3.85, 0.1, &prepped), Ok(0.0));
        assert_eq!(decide_parity_target(0.25, 2.8, -0.2, &prepped), Ok(0.5));
    }

    #[test]
    fn odd_width_targets_pixel_center_with_lower_tie() {
        for width in [0.5, 1.0, 3.0] {
            let prepped = [info_with_widths(vec![width])];
            assert_eq!(decide_parity_target(0.0, width, 0.0, &prepped), Ok(-0.5));
            assert_eq!(decide_parity_target(0.25, width, 0.0, &prepped), Ok(0.5));
        }
    }

    #[test]
    fn even_width_targets_boundary() {
        let prepped = [info_with_widths(vec![2.0])];
        assert_eq!(decide_parity_target(0.0, 2.0, 0.0, &prepped), Ok(0.0));
        assert_eq!(decide_parity_target(0.5, 2.0, 0.0, &prepped), Ok(1.0));
        assert_eq!(decide_parity_target(-0.25, 2.0, 0.0, &prepped), Ok(0.0));
        let axis = ((1_u64 << 53) - 1) as f64;
        assert_eq!(decide_parity_target(axis, 2.0, 0.0, &prepped), Ok(axis));
    }

    #[test]
    fn width_mismatch_is_ambiguous() {
        let prepped = [info_with_widths(vec![3.0])];
        assert!(matches!(
            decide_parity_target(0.0, 2.0, 0.0, &prepped),
            Err("parity-ambiguous")
        ));
    }

    #[test]
    fn subhalf_widths_fall_through_to_ambiguous() {
        let prepped = [info_with_widths(vec![0.25])];
        assert!(matches!(
            decide_parity_target(0.0, 0.25, 0.0, &prepped),
            Err("parity-ambiguous")
        ));
    }
}
