//! Terminal reference-height constraints inside the width solve.
//!
//! Source: Hersch sections 5-6 (reference-line phase with diagonal-width
//! control) and Hobby 3.3 (common displacement of horizontal regions).
//! Project adaptation: a nonzero horizontal straight source edge whose
//! endpoints also share one upstream height pins both Y coordinates to that
//! height while X joins the source-relative width solve. Source control-box
//! planes classify diagnostics; another stroke extending beyond an edge
//! cannot release its local reference phase. Upright source
//! verticals keep their upstream X while Y stays free. Explicit closing
//! endpoints alias one shared unknown (Hobby 6). Invariant: removal-free
//! correction only; unsupported geometry, budget overrun, movement or
//! validity failure all return the upstream outline unchanged.

use super::{
    abstain, curves, geometry, geometry::Parsed, FitResult, Reference, RowGroup, HEADROOM,
    MAX_COMMANDS,
};
use crate::probe::FittedCommand;
use nalgebra::{DMatrix, DVector};
use std::collections::{BTreeMap, HashMap, HashSet};

/// Unrounded raw source command in f64, pre-scaled to pixels.
///
/// The parent owns raw capture integration (units, scaling); this type only
/// carries the already-scaled geometry [`parse_raw`] folds into [`Parsed`].
#[derive(Clone, Copy, Debug)]
pub enum RawCommand {
    MoveTo([f64; 2]),
    LineTo([f64; 2]),
    QuadTo([f64; 2], [f64; 2]),
    CurveTo([f64; 2], [f64; 2], [f64; 2]),
    Close,
}

/// Reference edge location relative to the raw control box.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Plane {
    Min,
    Max,
    Interior,
}

impl Plane {
    fn as_str(self) -> &'static str {
        match self {
            Plane::Min => "min",
            Plane::Max => "max",
            Plane::Interior => "interior",
        }
    }
}

/// Source-horizontal reference edge with one retained upstream height.
#[derive(Clone, Debug)]
pub struct Cap {
    pub vertices: (usize, usize),
    pub plane: Plane,
    pub source_y: f64,
    pub upstream_y: f64,
}

/// Vertical straight source edge sharing one upstream X.
#[derive(Clone, Debug)]
pub struct Upright {
    pub vertices: (usize, usize),
    pub source_x: f64,
    pub upstream_x: f64,
}

/// Fold unrounded raw commands into contours, mirroring
/// [`geometry::parse_commands`] without f32 rounding.
pub fn parse_raw(commands: &[RawCommand]) -> Result<Parsed, ()> {
    let mut oncurve: Vec<[f64; 2]> = Vec::new();
    let mut offcurve: Vec<[f64; 2]> = Vec::new();
    let mut contours: Vec<Vec<geometry::Segment>> = Vec::new();
    let mut current: Vec<geometry::Segment> = Vec::new();
    let mut pen: Option<usize> = None;
    let mut start: Option<usize> = None;
    let finite = |p: [f64; 2]| {
        if p[0].is_finite() && p[1].is_finite() {
            Some(p)
        } else {
            None
        }
    };
    for cmd in commands {
        match *cmd {
            RawCommand::MoveTo(p) => {
                if !current.is_empty() {
                    contours.push(std::mem::take(&mut current));
                }
                let Some(pt) = finite(p) else {
                    return Err(());
                };
                oncurve.push(pt);
                pen = Some(oncurve.len() - 1);
                start = pen;
            }
            RawCommand::LineTo(p) => {
                let (Some(pt), Some(prev)) = (finite(p), pen) else {
                    return Err(());
                };
                oncurve.push(pt);
                let next = oncurve.len() - 1;
                current.push(geometry::Segment::Line { a: prev, b: next });
                pen = Some(next);
            }
            RawCommand::QuadTo(c, p) => {
                let (Some(cc), Some(pt), Some(prev)) = (finite(c), finite(p), pen) else {
                    return Err(());
                };
                offcurve.push(cc);
                let ci = offcurve.len() - 1;
                oncurve.push(pt);
                let next = oncurve.len() - 1;
                current.push(geometry::Segment::Quad {
                    c: ci,
                    a: prev,
                    b: next,
                });
                pen = Some(next);
            }
            RawCommand::CurveTo(c1, c2, p) => {
                let (Some(cc1), Some(cc2), Some(pt), Some(prev)) =
                    (finite(c1), finite(c2), finite(p), pen)
                else {
                    return Err(());
                };
                offcurve.push(cc1);
                let i1 = offcurve.len() - 1;
                offcurve.push(cc2);
                let i2 = offcurve.len() - 1;
                oncurve.push(pt);
                let next = oncurve.len() - 1;
                current.push(geometry::Segment::Cubic {
                    c1: i1,
                    c2: i2,
                    a: prev,
                    b: next,
                });
                pen = Some(next);
            }
            RawCommand::Close => {
                if let (Some(p), Some(s)) = (pen, start) {
                    if p != s {
                        current.push(geometry::Segment::Line { a: p, b: s });
                    }
                }
                if !current.is_empty() {
                    contours.push(std::mem::take(&mut current));
                }
                pen = None;
                start = None;
            }
        }
    }
    if !current.is_empty() {
        contours.push(current);
    }
    Ok(Parsed {
        oncurve,
        offcurve,
        contours,
    })
}

/// Flat source reference edges, including stroke ends below an ascender.
///
/// An empty outline is a valid font glyph and carries no caps. Only nonzero
/// exactly horizontal straight source segments whose endpoints also share
/// one upstream Y qualify. Hobby section 3.3 fits horizontal regions locally;
/// Hersch sections 5-6 preserve their grid phase while controlling diagonal
/// width. The height belongs to the existing fit, never a new rounded target.
/// Global control-box planes classify diagnostics, not eligibility: a
/// different stroke extending higher cannot release this reference edge.
pub fn detect_caps(raw: &Parsed, upstream: &Parsed) -> (Vec<Cap>, Option<f64>, Option<f64>) {
    let mut ys = raw.oncurve.iter().chain(raw.offcurve.iter()).map(|p| p[1]);
    let Some(first) = ys.next() else {
        return (Vec::new(), None, None);
    };
    let mut lo = first;
    let mut hi = first;
    for y in ys {
        lo = lo.min(y);
        hi = hi.max(y);
    }
    let up = &upstream.oncurve;
    let mut caps = Vec::new();
    let mut seen = HashSet::new();
    for contour in &raw.contours {
        for seg in contour {
            if !seg.is_line() {
                continue;
            }
            let (i0, i1) = seg.endpoints();
            let (Some(a), Some(b)) = (raw.oncurve.get(i0), raw.oncurve.get(i1)) else {
                continue;
            };
            if a[0] == b[0] || a[1] != b[1] {
                continue;
            }
            let (Some(ua), Some(ub)) = (up.get(i0), up.get(i1)) else {
                continue;
            };
            if ua[1] != ub[1] {
                continue;
            }
            if !seen.insert((i0, i1, a[1].to_bits())) {
                continue;
            }
            caps.push(Cap {
                vertices: (i0, i1),
                plane: if a[1] == lo {
                    Plane::Min
                } else if a[1] == hi {
                    Plane::Max
                } else {
                    Plane::Interior
                },
                source_y: a[1],
                upstream_y: ua[1],
            });
        }
    }
    (caps, Some(lo), Some(hi))
}

/// Nonzero vertical straight source edges with shared upstream X.
pub fn detect_uprights(raw: &Parsed, upstream: &Parsed) -> Vec<Upright> {
    let up = &upstream.oncurve;
    let mut found = Vec::new();
    let mut seen = HashSet::new();
    for contour in &raw.contours {
        for seg in contour {
            if !seg.is_line() {
                continue;
            }
            let (i0, i1) = seg.endpoints();
            let (Some(a), Some(b)) = (raw.oncurve.get(i0), raw.oncurve.get(i1)) else {
                continue;
            };
            if a[1] == b[1] || a[0] != b[0] {
                continue;
            }
            let (Some(ua), Some(ub)) = (up.get(i0), up.get(i1)) else {
                continue;
            };
            if ua[0] != ub[0] {
                continue;
            }
            if !seen.insert((i0, i1)) {
                continue;
            }
            found.push(Upright {
                vertices: (i0, i1),
                source_x: a[0],
                upstream_x: ua[0],
            });
        }
    }
    found
}

/// Contour/segment shape agreement between two parsed outlines.
fn same_shape(a: &Parsed, b: &Parsed) -> bool {
    if a.contours.len() != b.contours.len() || a.oncurve.len() != b.oncurve.len() {
        return false;
    }
    let op = |s: &geometry::Segment| match s {
        geometry::Segment::Line { .. } => 0,
        geometry::Segment::Quad { .. } => 1,
        geometry::Segment::Cubic { .. } => 2,
    };
    a.contours.iter().zip(b.contours.iter()).all(|(ca, cb)| {
        ca.len() == cb.len() && ca.iter().zip(cb.iter()).all(|(x, y)| op(x) == op(y))
    })
}

/// Explicit closing-endpoint aliases for line/quad/cubic contours.
///
/// `parse_commands` materializes a closing line when the last endpoint index
/// differs from the contour start; when that edge ends at duplicate contour
/// start coordinates its start vertex is an encoding artifact, not separate
/// geometry.
fn closure_aliases(parsed: &Parsed) -> BTreeMap<usize, usize> {
    let mut weld = BTreeMap::new();
    for contour in &parsed.contours {
        if contour.is_empty() {
            continue;
        }
        let (Some(first), Some(last)) = (contour.first(), contour.last()) else {
            continue;
        };
        if !last.is_line() {
            continue;
        }
        let (canon, _) = first.endpoints();
        let (dup, end) = last.endpoints();
        if end != canon || dup == canon {
            continue;
        }
        let (Some(pd), Some(pc)) = (parsed.oncurve.get(dup), parsed.oncurve.get(canon)) else {
            continue;
        };
        if *pd != *pc {
            continue;
        }
        weld.insert(dup, canon);
    }
    weld
}

/// Duplicate-canonical equality rows; unresolved ownership abstains.
///
/// An explicit closing endpoint alias is an encoding artifact, not separate
/// geometry; Hobby 6 carries shared vertices as one unknown, so each alias
/// pair is equated in the source-displacement frame. Only an alias that is
/// itself variable, with a non-variable canonical and no fixed axis of its
/// own, merges into the emission set; any other variable contact abstains
/// rather than splitting the point.
fn weld_constraints(
    weld: &BTreeMap<usize, usize>,
    var_verts: &HashSet<usize>,
    fixed: &HashMap<(usize, usize), f64>,
    base: &[[f64; 2]],
) -> (Vec<(Vec<f64>, f64)>, HashSet<usize>, Option<(usize, usize)>) {
    let mut rows = Vec::new();
    let mut merged = HashSet::new();
    for (&dup, &canon) in weld {
        if !var_verts.contains(&dup) && !var_verts.contains(&canon) {
            continue;
        }
        if var_verts.contains(&canon)
            || !var_verts.contains(&dup)
            || fixed.contains_key(&(dup, 0))
            || fixed.contains_key(&(dup, 1))
        {
            return (Vec::new(), HashSet::new(), Some((dup, canon)));
        }
        for axis in 0..2 {
            let mut row = vec![0.0; 2 * base.len()];
            row[2 * dup + axis] = 1.0;
            row[2 * canon + axis] = -1.0;
            rows.push((row, base[canon][axis] - base[dup][axis]));
        }
        merged.insert(dup);
    }
    (rows, merged, None)
}

/// Finite shape values for the (17) coupling; content outside this is a
/// caller error, never a solved guess.
fn valid_anchors(anchors: &[super::Anchor]) -> bool {
    anchors.iter().all(|a| {
        a.source_width.is_finite()
            && a.source_width > 0.0
            && a.rel.is_finite()
            && a.length.is_finite()
            && a.length > 0.0
            && a.tangent[0].is_finite()
            && a.tangent[1].is_finite()
            && (a.tangent[0] != 0.0 || a.tangent[1] != 0.0)
    })
}

/// Per-coordinate fixed-column elimination, matching the parent solve form.
fn eliminate_plain(
    rows: &[Vec<f64>],
    consts: &[f64],
    fixed: &HashMap<(usize, usize), f64>,
    nvars: usize,
) -> (Vec<Vec<f64>>, Vec<f64>, Vec<usize>) {
    super::eliminate_rows(
        rows.iter()
            .zip(consts.iter())
            .map(|(row, constant)| (row, *constant)),
        fixed,
        nvars,
    )
}

fn inf_norm(v: &DVector<f64>) -> f64 {
    v.iter().fold(0.0_f64, |m, x| m.max(x.abs()))
}

/// Exact hard rows via SVD particular plus nullspace least squares.
///
/// The particular solution carries the hard constraints; source shape and
/// (17) coupling run in the nullspace. Rank follows the NumPy singular-value
/// convention; a hard residual outside the relative band means inconsistent
/// constraints, never a guess. Without hard rows this is plain minimum-norm
/// least squares.
fn solve_hard(
    soft: &[(RowGroup, Vec<f64>, f64)],
    hard: &[(Vec<f64>, f64)],
    fixed: &HashMap<(usize, usize), f64>,
    nvars: usize,
) -> Option<Vec<f64>> {
    if hard.is_empty() {
        return Some(super::solve_constrained(soft, fixed, nvars));
    }
    let soft_rows: Vec<Vec<f64>> = soft.iter().map(|(_, r, _)| r.clone()).collect();
    let soft_c: Vec<f64> = soft.iter().map(|(_, _, c)| *c).collect();
    let hard_rows: Vec<Vec<f64>> = hard.iter().map(|(r, _)| r.clone()).collect();
    let hard_c: Vec<f64> = hard.iter().map(|(_, c)| *c).collect();
    let (soft_m, soft_const, free) = eliminate_plain(&soft_rows, &soft_c, fixed, nvars);
    let (hard_m, hard_const, _) = eliminate_plain(&hard_rows, &hard_c, fixed, nvars);
    let mut loose = vec![0.0; 2 * nvars];
    for (&(v, axis), &value) in fixed {
        loose[2 * v + axis] = value;
    }
    let (k, n) = (hard_m.len(), free.len());
    let mut flat = Vec::with_capacity(k * n);
    for row in &hard_m {
        for &col in &free {
            flat.push(row[col]);
        }
    }
    let mat = DMatrix::from_row_slice(k, n, &flat);
    let rhs = DVector::from_vec(hard_const.iter().map(|c| -c).collect());
    if n == 0 {
        if inf_norm(&rhs) > 1e-9 * inf_norm(&rhs).max(1.0) {
            return None;
        }
        return Some(loose);
    }
    // Zero rows preserve the hard equations while making the thin native
    // factorization retain the complete right singular basis, as NumPy's
    // full_matrices=True does for an underdetermined system.
    let padded = DMatrix::from_fn(k.max(n), n, |i, j| if i < k { mat[(i, j)] } else { 0.0 });
    let padded_rhs = DVector::from_iterator(
        k.max(n),
        (0..k.max(n)).map(|i| if i < k { rhs[i] } else { 0.0 }),
    );
    let svd = padded.svd(true, true);
    let sigma_max = svd.singular_values.iter().cloned().fold(0.0_f64, f64::max);
    let tol = f64::EPSILON * (k.max(n) as f64) * sigma_max;
    let rank = if sigma_max > 0.0 {
        svd.singular_values.iter().filter(|&&s| s > tol).count()
    } else {
        0
    };
    let (Some(u), Some(vt)) = (svd.u, svd.v_t) else {
        return None;
    };
    let utb: DVector<f64> = u.transpose() * &padded_rhs;
    let mut particular = DVector::zeros(n);
    for (i, &s) in svd
        .singular_values
        .iter()
        .enumerate()
        .filter(|(_, s)| **s > tol)
    {
        let c = utb[i] / s;
        for j in 0..n {
            particular[j] += vt[(i, j)] * c;
        }
    }
    let resid = inf_norm(&(mat.clone() * &particular - &rhs));
    if resid > 1e-9 * inf_norm(&rhs).max(1.0) {
        return None;
    }
    let null_dim = n - rank;
    if null_dim == 0 {
        for (t, &col) in free.iter().enumerate() {
            loose[col] = particular[t];
        }
        return Some(loose);
    }
    let mut null_basis = DMatrix::zeros(n, null_dim);
    for (t, (i, _)) in svd
        .singular_values
        .iter()
        .enumerate()
        .filter(|(_, s)| **s <= tol)
        .enumerate()
    {
        for j in 0..n {
            null_basis[(j, t)] = vt[(i, j)];
        }
    }
    let mut a_flat = Vec::with_capacity(soft_m.len() * null_dim);
    for row in &soft_m {
        for t in 0..null_dim {
            let mut dot = 0.0;
            for (k2, &col) in free.iter().enumerate() {
                dot += row[col] * null_basis[(k2, t)];
            }
            a_flat.push(dot);
        }
    }
    let a2 = DMatrix::from_row_slice(soft_m.len(), null_dim, &a_flat);
    let mut want_data = Vec::with_capacity(soft_m.len());
    for (m, row) in soft_m.iter().enumerate() {
        let mut dot = 0.0;
        for (t, &col) in free.iter().enumerate() {
            dot += row[col] * particular[t];
        }
        want_data.push(-soft_const[m] - dot);
    }
    let want = DVector::from_vec(want_data);
    let alpha = super::min_norm_solve(&a2, &want);
    let correction = &null_basis * &alpha;
    for (t, &col) in free.iter().enumerate() {
        loose[col] = particular[t] + correction[t];
    }
    Some(loose)
}

fn caps_json(caps: &[Cap]) -> serde_json::Value {
    caps.iter()
        .map(|c| {
            serde_json::json!({
                "vertices": [c.vertices.0, c.vertices.1],
                "plane": c.plane.as_str(),
                "source_y": c.source_y,
                "upstream_y": c.upstream_y,
            })
        })
        .collect()
}

fn uprights_json(found: &[Upright]) -> serde_json::Value {
    found
        .iter()
        .map(|u| {
            serde_json::json!({
                "vertices": [u.vertices.0, u.vertices.1],
                "source_x": u.source_x,
                "upstream_x": u.upstream_x,
            })
        })
        .collect()
}

/// Pin raw cap edges to upstream heights inside the width solve.
///
/// Width geometry reuses the direct-diagonal discovery exactly: canonical
/// visible-split recognition, interval ownership, exact curve-disk clearance
/// and the source-displacement joint assembly. Upstream Y minus source Y
/// fixed rows then hold each cap vertex at its upstream height while X
/// joins the (17) coupling; raw verticals with shared upstream X keep that
/// X while Y stays free. Weld aliases are exact hard rows in the same frame.
/// Emission, cost improvement, exact substituted topology and the curve sweep
/// must all pass; any failure returns the upstream outline unchanged.
pub fn fit_terminal(
    raw_source: &Parsed,
    captured: &[FittedCommand],
    upstream: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> FitResult {
    if native_axes[1] {
        return abstain(upstream, "native-y-owned", serde_json::json!({}));
    }
    if !(size_px.is_finite() && size_px > 0.0) {
        return abstain(upstream, "malformed-size", serde_json::json!({}));
    }
    let (Ok(captured_parsed), Ok(fitted)) = (
        geometry::parse_commands(captured),
        geometry::parse_commands(upstream),
    ) else {
        return abstain(upstream, "malformed-commands", serde_json::json!({}));
    };
    if !geometry::check_correspondence(captured, upstream)
        || !same_shape(raw_source, &captured_parsed)
    {
        return abstain(upstream, "no-correspondence", serde_json::json!({}));
    }
    let parsed = captured_parsed;
    if !raw_source
        .oncurve
        .iter()
        .chain(raw_source.offcurve.iter())
        .all(|p| p[0].is_finite() && p[1].is_finite())
    {
        return abstain(upstream, "malformed-commands", serde_json::json!({}));
    }
    let (caps, _, _) = detect_caps(raw_source, &fitted);
    let uprights = detect_uprights(raw_source, &fitted);
    let cap_ids: Vec<usize> = {
        let mut ids: Vec<usize> = caps
            .iter()
            .flat_map(|c| [c.vertices.0, c.vertices.1])
            .collect();
        ids.sort();
        ids.dedup();
        ids
    };
    let up_ids: Vec<usize> = {
        let mut ids: Vec<usize> = uprights
            .iter()
            .flat_map(|u| [u.vertices.0, u.vertices.1])
            .collect();
        ids.sort();
        ids.dedup();
        ids
    };
    let context = || {
        serde_json::json!({
            "caps": caps_json(&caps),
            "cap_vertices": cap_ids,
            "uprights": uprights_json(&uprights),
            "upright_vertices": up_ids,
        })
    };
    let weld = closure_aliases(&parsed);
    let up_weld = closure_aliases(&fitted);
    if weld != up_weld
        || weld
            .iter()
            .any(|(&dup, &canon)| fitted.oncurve.get(dup) != fitted.oncurve.get(canon))
    {
        let mut ctx = context();
        ctx["reason_detail"] = serde_json::json!("weld-mismatch");
        return abstain(upstream, "weld-mismatch", ctx);
    }
    if reference.anchors.is_empty() {
        return abstain(upstream, "no-reference-anchors", context());
    }
    if !valid_anchors(&reference.anchors) {
        return abstain(upstream, "malformed-anchors", context());
    }
    if captured.len() > MAX_COMMANDS
        || upstream.len() > MAX_COMMANDS
        || raw_source.oncurve.len() > MAX_COMMANDS
    {
        return abstain(upstream, "oversize-outline", context());
    }
    let (portions, curve_boxes, loops, flats) = geometry::split_visible(&parsed, true);
    let (pairs, mut skipped) = geometry::recognize(&portions, &loops, true);
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
    let exact_curves = geometry::curve_controls(&parsed);
    let fitted_coords = fitted.oncurve.clone();
    let mut prepped = Vec::new();
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
            &exact_curves,
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
                prepped.push(super::PreppedInfo {
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
        let mut ctx = context();
        ctx["skipped"] = serde_json::Value::Array(skipped_json);
        ctx["fixed"] = fixed_meta;
        return abstain(upstream, "all-abstained", ctx);
    }
    let mut infos: Vec<super::PreppedInfo> = prepped;
    let (system, mut fixed, var_verts) = super::assemble(
        &parsed,
        &fitted_coords,
        &mut infos,
        &reference.anchors,
        size_px,
        &pins,
        &owned,
    );
    let base = parsed.oncurve.clone();
    let gaps: Vec<[f64; 2]> = fitted_coords
        .iter()
        .zip(base.iter())
        .map(|(u, b)| [u[0] - b[0], u[1] - b[1]])
        .collect();
    let mut affected: Vec<usize> = caps
        .iter()
        .flat_map(|c| [c.vertices.0, c.vertices.1])
        .filter(|v| var_verts.contains(v))
        .collect();
    affected.sort();
    affected.dedup();
    if affected.is_empty() {
        let mut ctx = context();
        ctx["skipped"] = serde_json::Value::Array(skipped_json);
        ctx["fixed"] = fixed_meta;
        return abstain(upstream, "cap-not-involved", ctx);
    }
    for edge in &uprights {
        for v in [edge.vertices.0, edge.vertices.1] {
            fixed.insert((v, 0), gaps[v][0]);
        }
    }
    let (weld_rows, merged, conflict) = weld_constraints(&weld, &var_verts, &fixed, &base);
    if let Some((dup, canon)) = conflict {
        let mut ctx = context();
        ctx["cap_vertices"] = serde_json::json!(affected);
        ctx["skipped"] = serde_json::Value::Array(skipped_json);
        ctx["fixed"] = fixed_meta;
        ctx["weld_conflict"] = serde_json::json!([dup, canon]);
        return abstain(upstream, "weld-conflict", ctx);
    }
    for cap in &caps {
        for v in [cap.vertices.0, cap.vertices.1] {
            fixed.insert((v, 1), gaps[v][1]);
        }
    }
    let Some(flex) = solve_hard(&system.rows, &weld_rows, &fixed, parsed.oncurve.len()) else {
        let mut ctx = context();
        ctx["cap_vertices"] = serde_json::json!(affected);
        ctx["skipped"] = serde_json::Value::Array(skipped_json);
        ctx["fixed"] = fixed_meta;
        return abstain(upstream, "inconsistent-constraints", ctx);
    };
    if !flex.iter().all(|x| x.is_finite()) {
        let mut ctx = context();
        ctx["cap_vertices"] = serde_json::json!(affected);
        ctx["skipped"] = serde_json::Value::Array(skipped_json);
        ctx["fixed"] = fixed_meta;
        return abstain(upstream, "nonfinite-solution", ctx);
    }
    let upstream_coords = fitted_coords.clone();
    let mut deltas: Vec<[f64; 2]> = (0..base.len())
        .map(|v| {
            [
                base[v][0] + flex[2 * v] - upstream_coords[v][0],
                base[v][1] + flex[2 * v + 1] - upstream_coords[v][1],
            ]
        })
        .collect();
    let mut peaks: Vec<f64> = infos
        .iter()
        .map(|info| {
            [info.a.i0, info.a.i1, info.b.i0, info.b.i1]
                .iter()
                .map(|&v| deltas[v][0].hypot(deltas[v][1]))
                .fold(0.0, f64::max)
        })
        .collect();
    let over: Vec<usize> = peaks
        .iter()
        .enumerate()
        .filter(|(k, peak)| **peak > infos[*k].bound)
        .map(|(k, _)| k)
        .collect();
    let prefix = if over.is_empty() {
        1.0
    } else {
        // Convex descent along the upstream-to-minimizer segment: the
        // objective decreases monotonically, so the feasible prefix keeps
        // every fixed coordinate exact while restoring the budget.
        let scale = over
            .iter()
            .map(|&k| infos[k].bound / peaks[k])
            .fold(f64::INFINITY, f64::min);
        for d in deltas.iter_mut() {
            d[0] *= scale;
            d[1] *= scale;
        }
        peaks = infos
            .iter()
            .map(|info| {
                [info.a.i0, info.a.i1, info.b.i0, info.b.i1]
                    .iter()
                    .map(|&v| deltas[v][0].hypot(deltas[v][1]))
                    .fold(0.0, f64::max)
            })
            .collect();
        scale
    };
    for (info, &peak) in infos.iter_mut().zip(peaks.iter()) {
        info.peak = peak;
        info.prefix = prefix;
    }
    let table = geometry::index_map(upstream);
    let mut emit: Vec<usize> = var_verts.union(&merged).copied().collect();
    emit.sort();
    let mut candidate = upstream.to_vec();
    for &v in &emit {
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
    if candidate == upstream {
        let achieved = super::achieved_widths(&infos, upstream);
        let mut ctx = context();
        ctx["cap_vertices"] = serde_json::json!(affected);
        ctx["skipped"] = serde_json::Value::Array(skipped_json);
        ctx["fixed"] = fixed_meta;
        ctx["movement"] = serde_json::json!(0.0);
        ctx["bound"] =
            serde_json::json!(infos.iter().map(|i| i.bound).fold(f64::INFINITY, f64::min));
        ctx["widths"] = super::mean_widths(&achieved);
        return FitResult {
            commands: upstream.to_vec(),
            applied: false,
            reason: "no-movement".to_string(),
            diagnostics: ctx,
        };
    }
    finish(
        raw_source,
        &parsed,
        &fitted,
        upstream,
        &candidate,
        &mut infos,
        &peaks,
        &skipped_json,
        &fixed_meta,
        &pins,
        &owned,
        &caps,
        &cap_ids,
        &affected,
        &uprights,
        &up_ids,
        &weld,
        &system,
        &base,
        &upstream_coords,
        size_px,
        reference,
    )
}

/// Post-rounding gates; any failure rejects the whole glyph.
#[allow(clippy::too_many_arguments)]
fn finish(
    raw_source: &Parsed,
    parsed: &Parsed,
    fitted: &Parsed,
    upstream: &[FittedCommand],
    candidate: &[FittedCommand],
    infos: &mut [super::PreppedInfo],
    peaks: &[f64],
    skipped_json: &[serde_json::Value],
    fixed_meta: &serde_json::Value,
    pins: &HashSet<usize>,
    owned: &[usize],
    caps: &[Cap],
    cap_ids: &[usize],
    affected: &[usize],
    uprights: &[Upright],
    up_ids: &[usize],
    weld: &BTreeMap<usize, usize>,
    system: &super::System,
    base: &[[f64; 2]],
    upstream_coords: &[[f64; 2]],
    size_px: f64,
    reference: &Reference,
) -> FitResult {
    let mut validity = super::Validity {
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
    let cand = match geometry::parse_commands(candidate) {
        Ok(c) => c,
        Err(()) => {
            validity.ok = false;
            validity.stage = "unparseable-candidate".to_string();
            return invalid(
                upstream,
                infos,
                skipped_json,
                fixed_meta,
                caps,
                affected,
                uprights,
                up_ids,
                peaks,
                size_px,
                reference,
                &validity,
            );
        }
    };
    if !geometry::check_correspondence(upstream, candidate) {
        validity.ok = false;
        validity.stage = "ops-changed".to_string();
        return invalid(
            upstream,
            infos,
            skipped_json,
            fixed_meta,
            caps,
            affected,
            uprights,
            up_ids,
            peaks,
            size_px,
            reference,
            &validity,
        );
    }
    let before = geometry::signed_areas(&geometry::loops_points(fitted));
    let after = geometry::signed_areas(&geometry::loops_points(&cand));
    if !before
        .iter()
        .zip(after.iter())
        .all(|(a, b)| a.signum() == b.signum())
    {
        validity.ok = false;
        validity.stage = "orientation-flip".to_string();
    }
    let (cand_portions, _, _, cand_flats) = geometry::split_visible(&cand, true);
    let (up_portions, _, _, up_flats) = geometry::split_visible(fitted, true);
    validity.split_topology =
        geometry::topology_signature(&cand_portions) == geometry::topology_signature(&up_portions);
    // Exact substituted topology over raw, upstream and candidate replaces
    // the split-signature comparison; the fixed-curve reference stays for
    // curves outside the substitution certificate.
    let fitted_topology = curves::PreparedSubstitution::new(fitted);
    let candidate_topology = curves::PreparedSubstitution::new(&cand);
    if !curves::compare_prepared(
        &curves::PreparedSubstitution::new(raw_source),
        &fitted_topology,
        &candidate_topology,
    ) || !curves::compare_prepared(
        &curves::PreparedSubstitution::new(parsed),
        &fitted_topology,
        &candidate_topology,
    ) {
        validity.ok = false;
        validity.stage = "topology-mismatch".to_string();
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
            validity.pins_exact = false;
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
                validity.pins_exact = false;
            }
        }
    }
    if !validity.pins_exact {
        validity.ok = false;
        validity.stage = "pins-moved".to_string();
    }
    let cand_loops = geometry::loops_points(&cand);
    let up_loops = geometry::loops_points(fitted);
    for info in infos.iter_mut() {
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
                validity.centers_inked = false;
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
            validity.movement_ok = false;
        }
    }
    if !validity.centers_inked {
        validity.ok = false;
        validity.stage = "center-uninked".to_string();
    }
    if !validity.movement_ok {
        validity.ok = false;
        validity.stage = "movement-over-budget".to_string();
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
    let flat_base_cand: Vec<f64> = cand
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
    let mut curve_sweep = "clear".to_string();
    if validity.ok {
        if let Err(reason) = geometry::curve_sweep_ok(
            parsed,
            upstream_coords,
            candidate,
            &geometry::curve_controls(fitted),
        ) {
            validity.ok = false;
            validity.stage = reason.to_string();
            curve_sweep = reason.to_string();
        }
    }
    let cap_exact = cap_ids.iter().all(|&v| {
        let Some(pos) = table.get(v).copied().flatten() else {
            return true;
        };
        match &candidate[pos] {
            FittedCommand::MoveTo(_, y) | FittedCommand::LineTo(_, y) => {
                (*y as f64) == fitted.oncurve[v][1]
            }
            FittedCommand::QuadTo(_, _, _, y) | FittedCommand::CurveTo(_, _, _, _, _, y) => {
                (*y as f64) == fitted.oncurve[v][1]
            }
            FittedCommand::Close => true,
        }
    });
    if !cap_exact {
        validity.ok = false;
        validity.stage = "cap-height-moved".to_string();
    }
    let weld_exact = weld.iter().all(|(&dup, &canon)| {
        (0..2).all(|axis| cand.oncurve[dup][axis].to_bits() == cand.oncurve[canon][axis].to_bits())
    });
    if !weld_exact {
        validity.ok = false;
        validity.stage = "weld-split".to_string();
    }
    let upright_exact = up_ids.iter().all(|&v| {
        let Some(pos) = table.get(v).copied().flatten() else {
            return true;
        };
        match &candidate[pos] {
            FittedCommand::MoveTo(x, _) | FittedCommand::LineTo(x, _) => {
                (*x as f64) == fitted.oncurve[v][0]
            }
            FittedCommand::QuadTo(_, _, x, _) | FittedCommand::CurveTo(_, _, _, _, x, _) => {
                (*x as f64) == fitted.oncurve[v][0]
            }
            FittedCommand::Close => true,
        }
    });
    if !upright_exact {
        validity.ok = false;
        validity.stage = "upright-moved".to_string();
    }
    let achieved = super::achieved_widths(infos, candidate);
    let widths = super::mean_widths(&achieved);
    if !validity.ok {
        return invalid(
            upstream,
            infos,
            skipped_json,
            fixed_meta,
            caps,
            affected,
            uprights,
            up_ids,
            peaks,
            size_px,
            reference,
            &validity,
        );
    }
    let mut diagnostics = super::validity_json(&validity);
    diagnostics["topology_mode"] = serde_json::json!("exact_substituted");
    diagnostics
        .as_object_mut()
        .expect("validity object")
        .remove("hard_rounded_ok");
    diagnostics["cap_exact"] = serde_json::json!(cap_exact);
    diagnostics["weld_exact"] = serde_json::json!(weld_exact);
    diagnostics["upright_exact"] = serde_json::json!(upright_exact);
    diagnostics["curve_sweep"] = serde_json::json!(curve_sweep);
    FitResult {
        commands: candidate.to_vec(),
        applied: true,
        reason: "fitted".to_string(),
        diagnostics: serde_json::json!({
            "validity": diagnostics,
            "pairs": super::achieved_json(infos, &achieved),
            "skipped": skipped_json,
            "caps": caps_json(caps),
            "cap_vertices": affected,
            "uprights": uprights_json(uprights),
            "upright_vertices": up_ids,
            "fixed": fixed_meta,
            "movement": peaks.iter().cloned().fold(0.0, f64::max),
            "bound": infos.iter().map(|i| i.bound).fold(f64::INFINITY, f64::min),
            "size_px": size_px,
            "grid": false,
            "widths": widths,
            "reference": super::reference_meta(reference),
        }),
    }
}

#[allow(clippy::too_many_arguments)]
fn invalid(
    upstream: &[FittedCommand],
    infos: &[super::PreppedInfo],
    skipped_json: &[serde_json::Value],
    fixed_meta: &serde_json::Value,
    caps: &[Cap],
    affected: &[usize],
    uprights: &[Upright],
    up_ids: &[usize],
    peaks: &[f64],
    size_px: f64,
    reference: &Reference,
    validity: &super::Validity,
) -> FitResult {
    let fallback = super::achieved_widths(infos, upstream);
    let achieved = super::mean_widths(&fallback);
    let mut diagnostics = super::validity_json(validity);
    diagnostics["topology_mode"] = serde_json::json!("exact_substituted");
    diagnostics
        .as_object_mut()
        .expect("validity object")
        .remove("hard_rounded_ok");
    FitResult {
        commands: upstream.to_vec(),
        applied: false,
        reason: "invalid-candidate".to_string(),
        diagnostics: serde_json::json!({
            "validity": diagnostics,
            "pairs": super::achieved_json(infos, &fallback),
            "skipped": skipped_json,
            "caps": caps_json(caps),
            "cap_vertices": affected,
            "uprights": uprights_json(uprights),
            "upright_vertices": up_ids,
            "fixed": fixed_meta,
            "attempt": {
                "movement": peaks.iter().cloned().fold(0.0, f64::max),
                "validity": diagnostics,
            },
            "movement": 0.0,
            "bound": infos.iter().map(|i| i.bound).fold(f64::INFINITY, f64::min),
            "size_px": size_px,
            "grid": false,
            "widths": achieved,
            "reference": super::reference_meta(reference),
        }),
    }
}

#[cfg(test)]
mod hard_solve_tests {
    use super::*;

    #[test]
    fn underdetermined_hard_row_keeps_its_nullspace_and_nonzero_target() {
        let soft = vec![
            (RowGroup::Position, vec![1.0, 0.0], -2.0),
            (RowGroup::Position, vec![0.0, 1.0], -4.0),
        ];
        for scale in [1.0, -1.0, 1e-12] {
            let hard = vec![(vec![scale, -scale], scale)];
            let result = solve_hard(&soft, &hard, &HashMap::new(), 1).unwrap();
            assert!((result[0] - 2.5).abs() < 1e-9);
            assert!((result[1] - 3.5).abs() < 1e-9);
        }
    }

    #[test]
    fn redundant_hard_rows_preserve_unconstrained_coordinates() {
        let soft: Vec<_> = (0..4)
            .map(|i| {
                let mut row = vec![0.0; 4];
                row[i] = 1.0;
                (RowGroup::Position, row, -((i + 1) as f64))
            })
            .collect();
        let hard = vec![
            (vec![1.0, -1.0, 0.0, 0.0], 0.0),
            (vec![2.0, -2.0, 0.0, 0.0], 0.0),
            (vec![0.0; 4], 0.0),
        ];
        let result = solve_hard(&soft, &hard, &HashMap::new(), 2).unwrap();
        for (got, want) in result.iter().zip([1.5, 1.5, 3.0, 4.0]) {
            assert!((got - want).abs() < 1e-9);
        }
    }
}

#[cfg(test)]
mod elimination_tests {
    use super::*;

    fn bits(values: &[f64]) -> Vec<u64> {
        values.iter().map(|v| v.to_bits()).collect()
    }

    fn mixed_fixed() -> HashMap<(usize, usize), f64> {
        HashMap::from([((0, 1), 2.0), ((1, 0), -3.0)])
    }

    #[test]
    fn truncates_to_shorter_of_rows_or_consts() {
        let fixed = mixed_fixed();
        let rows = vec![vec![1.0, 2.0, 3.0, 4.0], vec![0.0, 0.0, 0.0, 5.0]];
        let (matrix, constants, free) = eliminate_plain(&rows, &[10.0], &fixed, 2);
        assert_eq!(matrix.len(), 1);
        assert_eq!(bits(&matrix[0]), bits(&[1.0, 2.0, 3.0, 4.0]));
        assert_eq!(constants.len(), 1);
        assert_eq!(constants[0].to_bits(), 5.0f64.to_bits());
        assert_eq!(free, vec![0, 3]);
        let (matrix, constants, _) = eliminate_plain(&rows[..1], &[10.0, 20.0], &fixed, 2);
        assert_eq!(matrix.len(), 1);
        assert_eq!(constants, vec![5.0]);
    }

    #[test]
    fn empty_and_fully_fixed_inputs_keep_free_enumeration() {
        let fixed = mixed_fixed();
        let (matrix, constants, free) = eliminate_plain(&[], &[], &fixed, 2);
        assert!(matrix.is_empty());
        assert!(constants.is_empty());
        assert_eq!(free, vec![0, 3]);
        let full = HashMap::from([((0, 0), 1.0), ((0, 1), -2.0), ((1, 0), 0.5), ((1, 1), 4.0)]);
        let (matrix, constants, free) =
            eliminate_plain(&[vec![1.0, 1.0, 1.0, 1.0]], &[0.0], &full, 2);
        assert!(free.is_empty());
        assert_eq!(matrix.len(), 1);
        assert_eq!(constants[0].to_bits(), 3.5f64.to_bits());
    }

    #[test]
    fn sorted_accumulation_is_insertion_independent() {
        let mut fixed = HashMap::new();
        fixed.insert((1, 0), 1.0);
        fixed.insert((0, 0), 1e16);
        fixed.insert((0, 1), -1e16);
        let rows = vec![vec![1.0, 1.0, 1.0, 0.0]];
        let snapshot = rows.clone();
        let (matrix, constants, free) = eliminate_plain(&rows, &[0.0], &fixed, 2);
        assert_eq!(free, vec![3]);
        assert_eq!(bits(&matrix[0]), bits(&[1.0, 1.0, 1.0, 0.0]));
        assert_eq!(constants[0].to_bits(), 1.0f64.to_bits());
        assert_eq!(rows, snapshot);
        let mut other = HashMap::new();
        other.insert((0, 1), -1e16);
        other.insert((0, 0), 1e16);
        other.insert((1, 0), 1.0);
        let (_, again, _) = eliminate_plain(&rows, &[0.0], &other, 2);
        assert_eq!(bits(&again), bits(&constants));
    }
}
