//! Shared-border upright normalization (see docs/hobby-fitting.md).
//!
//! Shamir sections 3.2-3.6: separate width relations to one shared point,
//! inserted once. Hobby section 3.2 (4)-(5) local widths, section 3.6 (17)
//! relative coupling preserving source contrast, section 4 (20) one shared
//! integer width parameter, section 4.2 width clustering; Hersch sections
//! 5-6 standard snapping and phase. Project adaptations: bounded 26.6 phase
//! search over geometry-derived caps and exact abstention gates.

use super::{abstain, geometry, FitResult, Reference, HEADROOM, MAX_COMMANDS};
use crate::{probe::FittedCommand, Error};
use std::collections::{BTreeMap, HashMap, HashSet};

const GRID: f64 = 64.0;

fn quad_x_at_y_all(p0: [f64; 2], c: [f64; 2], p1: [f64; 2], y: f64) -> Vec<f64> {
    // Solve the quadratic Bernstein Y polynomial; adaptation of Hobby
    // section 6's polygonal-intermediate correspondence to a Y station.
    let a = p0[1] - 2.0 * c[1] + p1[1];
    let b = 2.0 * (c[1] - p0[1]);
    let d = p0[1] - y;
    let mut roots = Vec::new();
    if a == 0.0 {
        if b == 0.0 {
            return Vec::new();
        }
        roots.push(-d / b);
    } else {
        let disc = b * b - 4.0 * a * d;
        if disc < 0.0 {
            return Vec::new();
        }
        let s = disc.sqrt();
        roots.push((-b + s) / (2.0 * a));
        roots.push((-b - s) / (2.0 * a));
    }
    let mut out = Vec::new();
    for t in roots {
        if (0.0..=1.0).contains(&t) {
            let u = 1.0 - t;
            out.push(u * u * p0[0] + 2.0 * u * t * c[0] + t * t * p1[0]);
        }
    }
    out
}

fn quad_x_at_y(p0: [f64; 2], c: [f64; 2], p1: [f64; 2], y: f64) -> Option<f64> {
    // Analytic f64 roots, not exact arithmetic: a station with two
    // distinct crossings is ambiguous and fails closed rather than
    // selecting an arbitrary first root.
    let mut hits = quad_x_at_y_all(p0, c, p1, y);
    hits.dedup_by(|a, b| (*a - *b).abs() == 0.0);
    if hits.len() == 1 {
        Some(hits[0])
    } else {
        None
    }
}

/// Station certification through the existing certified winding path:
/// the station midpoint must be ink, and no competing straight or curved
/// boundary may cross the open station segment. Curve crossings use the
/// analytic quadratic roots above; ambiguous stations fail closed.
fn station_certified(
    parsed: &geometry::Parsed,
    chain: &HashSet<usize>,
    station_seg: usize,
    y: f64,
    x_left: f64,
    x_r: f64,
) -> bool {
    let (portions, _, loops, flats) = geometry::split_visible(parsed, true);
    let _ = portions;
    // Dominance below proves no boundary crosses the open station
    // segment, so one interior ink point certifies the whole segment.
    // Sample toward the straight border, away from the curved border's
    // hull, which the certified winding path conservatively avoids.
    let mid = [x_left + 0.75 * (x_r - x_left), y];
    match geometry::certified_winding(mid, &loops, &flats) {
        Some(w) if w != 0 => {}
        _ => return false,
    }
    for (idx, seg) in parsed.contours[0].iter().enumerate() {
        match *seg {
            geometry::Segment::Line { a, b } => {
                let (pa, pb) = (parsed.oncurve[a], parsed.oncurve[b]);
                if pa[0] == x_r && pb[0] == x_r {
                    continue;
                }
                if (pa[1] <= y) != (pb[1] <= y) && pa[1] != pb[1] {
                    let xi = pa[0] + (y - pa[1]) / (pb[1] - pa[1]) * (pb[0] - pa[0]);
                    if xi > x_left && xi < x_r {
                        return false;
                    }
                }
            }
            geometry::Segment::Quad { c, a, b } => {
                if chain.contains(&idx) && idx == station_seg {
                    continue;
                }
                let (pa, pc, pb) = (parsed.oncurve[a], parsed.offcurve[c], parsed.oncurve[b]);
                for x in quad_x_at_y_all(pa, pc, pb, y) {
                    if x > x_left && x < x_r {
                        return false;
                    }
                }
            }
            geometry::Segment::Cubic { .. } => return false,
        }
    }
    true
}

/// Merge straight collinear subdivision vertices determined by the
/// source outline (exact cross-product identity), applied by segment
/// index to a corresponding outline. Returns None when that outline's
/// dropped vertex is not exactly on the merged chord.
fn merged_collinear(
    source: &geometry::Parsed,
    other: &geometry::Parsed,
) -> Option<geometry::Parsed> {
    let mut contours = Vec::new();
    for (ci, contour) in source.contours.iter().enumerate() {
        let other_contour = other.contours.get(ci)?;
        let mut segs: Vec<geometry::Segment> = Vec::new();
        for seg in contour.iter() {
            if let geometry::Segment::Line { a, b } = *seg {
                if let Some(geometry::Segment::Line { a: pa, b: pb }) = segs.last_mut() {
                    if *pb == a {
                        let (p0, p1, p2) =
                            (source.oncurve[*pa], source.oncurve[a], source.oncurve[b]);
                        let cross =
                            (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0]);
                        let dot =
                            (p1[0] - p0[0]) * (p2[0] - p1[0]) + (p1[1] - p0[1]) * (p2[1] - p1[1]);
                        if cross == 0.0 && dot > 0.0 {
                            let (q0, q1, q2) =
                                (other.oncurve[*pa], other.oncurve[a], other.oncurve[b]);
                            let ocross = (q1[0] - q0[0]) * (q2[1] - q0[1])
                                - (q1[1] - q0[1]) * (q2[0] - q0[0]);
                            // Collinearity alone is insufficient: the
                            // dropped vertex must also lie in positive
                            // order on the chord, or a moved border has
                            // reversed past it and merging would hide
                            // the resulting backtracking.
                            let odot = (q1[0] - q0[0]) * (q2[0] - q1[0])
                                + (q1[1] - q0[1]) * (q2[1] - q1[1]);
                            if ocross != 0.0 || odot <= 0.0 {
                                return None;
                            }
                            *pb = b;
                            continue;
                        }
                    }
                }
            }
            segs.push(*seg);
        }
        let _ = other_contour;
        contours.push(segs);
    }
    Some(geometry::Parsed {
        oncurve: other.oncurve.clone(),
        offcurve: other.offcurve.clone(),
        contours,
    })
}

/// Attached curved chain: contour-adjacency walk from each endpoint of
/// the head's shared-border segment, through non-vertical connectors and
/// consecutive quads, stopping at a vertical straight or the shared
/// border itself. No extent constant: attachment is topological.
fn attached_chain(
    contour: &[geometry::Segment],
    parsed: &geometry::Parsed,
    head_seg: usize,
    x_r: f64,
    head_ylo: f64,
    head_yhi: f64,
) -> HashSet<usize> {
    let mut adjacency: HashMap<usize, Vec<usize>> = HashMap::new();
    for (idx, seg) in contour.iter().enumerate() {
        let (a, b) = seg.endpoints();
        adjacency.entry(a).or_default().push(idx);
        adjacency.entry(b).or_default().push(idx);
    }
    let mut chain = HashSet::new();
    let (ha, hb) = contour[head_seg].endpoints();
    for start in [ha, hb] {
        let mut current = start;
        let mut prev = head_seg;
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
                    // The walk stays within the head interval's span: a
                    // quad lying wholly outside it belongs to another
                    // feature (crossbar, foot, terminal), not the head.
                    let ymin = parsed.oncurve[a][1].min(parsed.oncurve[b][1]);
                    let ymax = parsed.oncurve[a][1].max(parsed.oncurve[b][1]);
                    if ymax < head_ylo || ymin > head_yhi {
                        break;
                    }
                    chain.insert(next);
                }
                geometry::Segment::Line { .. } => {
                    let (pa, pb) = (parsed.oncurve[a], parsed.oncurve[b]);
                    // Vertical straights and the shared border terminate
                    // the walk; a connector line is traversed once.
                    if pa[0] == pb[0] || pa[0] == x_r && pb[0] == x_r {
                        break;
                    }
                    if !chain.is_empty() {
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
    chain
}

#[derive(Clone, Debug)]
struct Interval {
    ylo: f64,
    yhi: f64,
    segs: Vec<usize>,
}

/// Certified standard from `DonorCert` metadata: source-exact class
/// membership on the certificate's coordinate-difference border width,
/// unanimous integer fitted target. Shared by the upright stage and the
/// automatic-Y shape prototype; class authority stays the captured
/// certificates regardless of the shape authority in use.
pub(crate) fn certified_standard(reference: &Reference, w_body: f64) -> Option<f64> {
    let mut standard: Option<i64> = None;
    for anchor in &reference.anchors {
        let Some(cert) = &anchor.cert else {
            continue;
        };
        if !cert.unambiguous || cert.border_width != w_body {
            continue;
        }
        let k = cert.fitted_border_width.round();
        if (cert.fitted_border_width - k).abs() > HEADROOM || k < 1.0 {
            return None;
        }
        match standard {
            None => standard = Some(k as i64),
            Some(sv) if sv == k as i64 => {}
            _ => return None,
        }
    }
    standard.map(|k| k as f64)
}

pub fn fit(
    source: &[FittedCommand],
    upstream: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> Result<FitResult, Error> {
    let no = |reason: &str| abstain(upstream, reason, serde_json::json!({}));
    if native_axes != [false, false] {
        return Ok(no("upright-native-axes"));
    }
    if !(size_px.is_finite() && size_px > 0.0) {
        return Ok(no("upright-size"));
    }
    if !geometry::check_correspondence(source, upstream) {
        return Ok(no("upright-no-correspondence"));
    }
    let (Ok(src), Ok(fit)) = (
        geometry::parse_commands(source),
        geometry::parse_commands(upstream),
    ) else {
        return Ok(no("upright-malformed"));
    };
    if source.len() > MAX_COMMANDS || upstream.len() > MAX_COMMANDS {
        return Ok(no("upright-oversize"));
    }
    if src.contours.len() != 1 || fit.contours.len() != 1 {
        return Ok(no("upright-contour-count"));
    }
    let contour = &src.contours[0];
    if contour
        .iter()
        .any(|s| matches!(s, geometry::Segment::Cubic { .. }))
    {
        return Ok(no("upright-cubic"));
    }
    // Vertical straight segments grouped by exact supporting line.
    let mut groups: BTreeMap<u64, (f64, Vec<(usize, usize, usize, f64, f64)>)> = BTreeMap::new();
    for (idx, seg) in contour.iter().enumerate() {
        if let geometry::Segment::Line { a, b } = *seg {
            let (pa, pb) = (src.oncurve[a], src.oncurve[b]);
            if pa[0] == pb[0] && pa[1] != pb[1] {
                let e = groups.entry(pa[0].to_bits()).or_insert((pa[0], Vec::new()));
                e.1.push((idx, a, b, pa[1].min(pb[1]), pa[1].max(pb[1])));
            }
        }
    }
    let mut candidates: Vec<(f64, Vec<Interval>)> = Vec::new();
    for (_, (x, segs)) in groups.iter() {
        let mut segs = segs.clone();
        segs.sort_by(|p, q| p.3.partial_cmp(&q.3).unwrap());
        let mut merged: Vec<Interval> = Vec::new();
        for s in segs {
            if let Some(last) = merged.last_mut() {
                if s.3 <= last.yhi {
                    last.yhi = last.yhi.max(s.4);
                    last.segs.push(s.0);
                    continue;
                }
            }
            merged.push(Interval {
                ylo: s.3,
                yhi: s.4,
                segs: vec![s.0],
            });
        }
        if merged.len() >= 2 {
            candidates.push((*x, merged));
        }
    }
    if candidates.len() != 1 {
        return Ok(no("upright-shared-border-count"));
    }
    let (x_r, intervals) = candidates.into_iter().next().unwrap();
    // Classify each interval by its left partner.
    let mut body: Option<(Interval, f64, usize, usize)> = None;
    let mut head: Option<(Interval, f64, Vec<usize>, Vec<f64>)> = None;
    for iv in &intervals {
        let mut straight: Vec<(f64, usize)> = Vec::new();
        for (idx, seg) in contour.iter().enumerate() {
            if let geometry::Segment::Line { a, b } = *seg {
                let (pa, pb) = (src.oncurve[a], src.oncurve[b]);
                if pa[0] == pb[0] && pa[0] < x_r && pa[1] != pb[1] {
                    let lo = pa[1].min(pb[1]).max(iv.ylo);
                    let hi = pa[1].max(pb[1]).min(iv.yhi);
                    if hi > lo {
                        straight.push((pa[0], idx));
                    }
                }
            }
        }
        straight.sort_by(|p, q| p.0.partial_cmp(&q.0).unwrap());
        straight.dedup_by(|p, q| p.0 == q.0);
        // Curved partner widths at the interval's Y stations.
        let mut curve_segs: Vec<usize> = Vec::new();
        let mut station_widths: Vec<f64> = Vec::new();
        let mut mid_width: Option<f64> = None;
        let mut curve_ok = true;
        for (k, frac) in [0.25, 0.5, 0.75].iter().enumerate() {
            let y = iv.ylo + (iv.yhi - iv.ylo) * frac;
            let mut hits: Vec<(usize, f64)> = Vec::new();
            for (idx, seg) in contour.iter().enumerate() {
                if let geometry::Segment::Quad { c, a, b } = *seg {
                    let (pa, pc, pb) = (src.oncurve[a], src.offcurve[c], src.oncurve[b]);
                    if pa[0] < x_r && pb[0] < x_r {
                        if let Some(x) = quad_x_at_y(pa, pc, pb, y) {
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
            if k == 1 {
                mid_width = Some(hits[0].1);
            }
            station_widths.push(hits[0].1);
            curve_segs.push(hits[0].0);
        }
        let has_curve = curve_ok && mid_width.is_some();
        match (straight.len(), has_curve) {
            (1, false) => {
                if body.is_some() {
                    return Ok(no("upright-multiple-bodies"));
                }
                body = Some((iv.clone(), x_r - straight[0].0, straight[0].1, iv.segs[0]));
            }
            (0, true) => {
                if head.is_some() {
                    return Ok(no("upright-multiple-heads"));
                }
                head = Some((iv.clone(), mid_width.unwrap(), curve_segs, station_widths));
            }
            _ => return Ok(no("upright-ambiguous-interval")),
        }
    }
    let (
        Some((body_iv, w_body, body_l_seg, body_r_seg)),
        Some((head_iv, w_head, head_segs, head_station_widths)),
    ) = (body, head)
    else {
        return Ok(no("upright-feature-incomplete"));
    };
    let _ = &body_iv;
    // Attachment, ink and dominance certification for the curved head:
    // the station curve must be the chain contour-attached to the shared
    // border, and every station segment must lie in certified ink.
    let chain = attached_chain(
        contour,
        &src,
        head_iv.segs[0],
        x_r,
        head_iv.ylo,
        head_iv.yhi,
    );
    if chain.is_empty() || !head_segs.iter().all(|sg| chain.contains(sg)) {
        return Ok(no("upright-head-unattached"));
    }
    for (k, frac) in [0.25, 0.5, 0.75].iter().enumerate() {
        let y = head_iv.ylo + (head_iv.yhi - head_iv.ylo) * frac;
        let geometry::Segment::Quad { c, a, b } = contour[head_segs[k]] else {
            return Ok(no("upright-head-not-quad"));
        };
        let Some(x_left) = quad_x_at_y(src.oncurve[a], src.offcurve[c], src.oncurve[b], y) else {
            return Ok(no("upright-head-unmeasured"));
        };
        if !station_certified(&src, &chain, head_segs[k], y, x_left, x_r) {
            return Ok(no("upright-head-uncertified"));
        }
    }
    if !(w_body > 0.0 && w_head > 0.0) {
        return Ok(no("upright-width-nonpositive"));
    }
    // Fitted borders: every endpoint of the shared line must agree exactly.
    let mut fx_r_opt: Option<f64> = None;
    for iv in &intervals {
        for &si in &iv.segs {
            let geometry::Segment::Line { a, b } = contour[si] else {
                unreachable!()
            };
            for v in [a, b] {
                match fx_r_opt {
                    None => fx_r_opt = Some(fit.oncurve[v][0]),
                    Some(x) if x == fit.oncurve[v][0] => {}
                    _ => return Ok(no("upright-fitted-border-split")),
                }
            }
        }
    }
    let fx_r = fx_r_opt.unwrap();
    let geometry::Segment::Line { a: la, b: lb } = contour[body_l_seg] else {
        return Ok(no("upright-body-not-straight"));
    };
    if fit.oncurve[la][0] != fit.oncurve[lb][0] {
        return Ok(no("upright-fitted-body-split"));
    }
    let w_up = fx_r - fit.oncurve[la][0];
    if !(w_up > 0.0) {
        return Ok(no("upright-fitted-width-nonpositive"));
    }
    // Standard: certified donors only (shared helper; the target's own
    // necessarily ambiguous anchor is excluded by its certificate).
    let Some(s) = certified_standard(reference, w_body) else {
        return Ok(no("upright-standard-empty"));
    };
    let d = s - w_up;
    if d == 0.0 {
        return Ok(no("upright-already-standard"));
    }
    if (w_up * GRID).round() != w_up * GRID {
        return Ok(no("upright-fitted-off-grid"));
    }
    // Runtime curved-head fitted width at the corresponding station.
    let head_mid_seg = head_segs[1];
    let geometry::Segment::Quad {
        c: hc,
        a: ha,
        b: hb,
    } = contour[head_mid_seg]
    else {
        return Ok(no("upright-head-not-quad"));
    };
    let y_mid_fit = {
        let geometry::Segment::Line { a, b } = contour[head_iv.segs[0]] else {
            return Ok(no("upright-head-border"));
        };
        (fit.oncurve[a][1] + fit.oncurve[b][1]) / 2.0
    };
    let Some(fx_head) = quad_x_at_y(
        fit.oncurve[ha],
        fit.offcurve[hc],
        fit.oncurve[hb],
        y_mid_fit,
    ) else {
        return Ok(no("upright-head-unmeasured"));
    };
    let w_head_fit = fx_r - fx_head;
    if !(w_head_fit > 0.0) {
        return Ok(no("upright-head-fitted-nonpositive"));
    }
    // Fitted widths at the same three stations; the candidate must
    // retain this profile shifted by the shared-border displacement,
    // not only the midpoint width.
    let (fit_ylo, fit_yhi) = {
        let geometry::Segment::Line { a, b } = contour[head_iv.segs[0]] else {
            return Ok(no("upright-head-border"));
        };
        (
            fit.oncurve[a][1].min(fit.oncurve[b][1]),
            fit.oncurve[a][1].max(fit.oncurve[b][1]),
        )
    };
    let mut station_fit_widths: Vec<f64> = Vec::new();
    for (k, frac) in [0.25, 0.5, 0.75].iter().enumerate() {
        let y = fit_ylo + (fit_yhi - fit_ylo) * frac;
        let geometry::Segment::Quad { c, a, b } = contour[head_segs[k]] else {
            return Ok(no("upright-head-not-quad"));
        };
        let Some(x_left) = quad_x_at_y(fit.oncurve[a], fit.offcurve[c], fit.oncurve[b], y) else {
            return Ok(no("upright-head-unmeasured"));
        };
        station_fit_widths.push(fx_r - x_left);
    }
    // Contrast target uses the midpoint width; the movement budget
    // uses the narrowest certified source profile sample, matching the
    // existing per-pair cap rule (narrowest width / 2 - HEADROOM).
    let w_head_min = head_station_widths
        .iter()
        .cloned()
        .fold(f64::INFINITY, f64::min);
    let target_head = s * (w_head / w_body);
    // Per-feature caps; shared border obeys the intersection (minimum).
    let cap_body = w_body / 2.0 - HEADROOM;
    let cap_head = w_head_min / 2.0 - HEADROOM;
    if cap_body < HEADROOM || cap_head < HEADROOM {
        return Ok(no("upright-budget-empty"));
    }
    let cap_r = cap_body.min(cap_head);
    // Bounded phase optimization; no pixel-derived objective. Both
    // lexicographic keys (max movement, centre shift) grow monotonically
    // with distance from the continuous optimum dr = D/2, so checking
    // the 26.6 grid points around that optimum, around the feasible
    // interval ends from the body/head caps, and around the head-cap
    // interval ends is exact while evaluating a constant number of
    // candidates for any finite source width.
    let head_change = target_head - w_head_fit;
    let lo = (-cap_r)
        .max(d - cap_body)
        .max(head_change - cap_head - 1.0 / GRID);
    let hi = cap_r
        .min(d + cap_body)
        .min(head_change + cap_head + 1.0 / GRID);
    let mut candidate_ks: Vec<i64> = Vec::new();
    for v in [lo * GRID, hi * GRID, (d / 2.0) * GRID] {
        if !v.is_finite() || v.abs() > 4.5e15 {
            continue;
        }
        for k in (v.floor() as i64 - 2)..=(v.ceil() as i64 + 2) {
            candidate_ks.push(k);
        }
    }
    candidate_ks.sort_unstable();
    candidate_ks.dedup();
    let mut best: Option<(f64, f64, f64, [f64; 3])> = None;
    for k in candidate_ks {
        let dr = k as f64 / GRID;
        let dl = dr - d;
        if dr.abs() > cap_r || dl.abs() > cap_body {
            continue;
        }
        // Hersch sections 5-6 phase: a stem border on the exact
        // half-pixel coordinate is the monochrome scanner's tie, where
        // both edge columns can be taken and an integer-width stem
        // delivers one column too many. Feasible phases keep both body
        // borders off that tie; no delivered pixels are consulted.
        let gl = (fx_r - w_up + dl) * GRID;
        let gr = (fx_r + dr) * GRID;
        if gl != gl.round()
            || gr != gr.round()
            || (gl.round() as i64).rem_euclid(64) == 32
            || (gr.round() as i64).rem_euclid(64) == 32
        {
            continue;
        }
        let dh_raw = dr - head_change;
        let dh = geometry::round_26_6(dh_raw);
        if dh.abs() > cap_head {
            continue;
        }
        let achieved = w_head_fit + dr - dh;
        if (achieved - target_head).abs() > HEADROOM {
            continue;
        }
        let key = (dr.abs().max(dl.abs()), ((dl + dr) / 2.0).abs(), dh.abs());
        let cand = (key.0, key.1, key.2, [dl, dr, dh]);
        if best
            .as_ref()
            .is_none_or(|b| (cand.0, cand.1, cand.2) < (b.0, b.1, b.2))
        {
            best = Some(cand);
        }
    }
    let Some((_, _, _, [dl, dr, dh])) = best else {
        return Ok(no("upright-budget-infeasible"));
    };
    // Move sets by exact source supporting lines and curve-chain attachment.
    let mut moves: HashMap<usize, f64> = HashMap::new();
    let assign = |moves: &mut HashMap<usize, f64>, v: usize, delta: f64| -> bool {
        match moves.get(&v) {
            None => {
                moves.insert(v, delta);
                true
            }
            Some(&old) => old == delta,
        }
    };
    for (v, p) in src.oncurve.iter().enumerate() {
        if p[0] == x_r && !assign(&mut moves, v, dr) {
            return Ok(no("upright-attachment-conflict"));
        }
    }
    let x_l = x_r - w_body;
    for (v, p) in src.oncurve.iter().enumerate() {
        if p[0] == x_l && !assign(&mut moves, v, dl) {
            return Ok(no("upright-attachment-conflict"));
        }
    }
    // Head curve chain certified by contour attachment above.
    for &ci in &chain {
        let (a, b) = contour[ci].endpoints();
        for v in [a, b] {
            if src.oncurve[v][0] < x_r && !assign(&mut moves, v, dh) {
                return Ok(no("upright-attachment-conflict"));
            }
        }
    }
    // Off-curve controls follow an incident moved endpoint; conflicting
    // incident displacements abstain.
    let mut off_moves: HashMap<usize, f64> = HashMap::new();
    for seg in contour.iter() {
        let geometry::Segment::Quad { c, a, b } = *seg else {
            continue;
        };
        let mut deltas: HashSet<i64> = HashSet::new();
        for v in [a, b] {
            if let Some(&delta) = moves.get(&v) {
                deltas.insert((delta * GRID) as i64);
            }
        }
        if src.offcurve[c][0] == x_r {
            deltas.insert((dr * GRID) as i64);
        }
        if src.offcurve[c][0] == x_l {
            deltas.insert((dl * GRID) as i64);
        }
        if deltas.len() > 1 {
            return Ok(no("upright-control-conflict"));
        }
        if let Some(&k) = deltas.iter().next() {
            off_moves.insert(c, k as f64 / GRID);
        }
    }
    // Apply X-only moves; Y bits are retained by construction.
    let on_map = geometry::index_map(upstream);
    let mut off_map: Vec<Option<usize>> = vec![None; src.offcurve.len()];
    {
        let mut oi = 0usize;
        for (pos, cmd) in upstream.iter().enumerate() {
            match cmd {
                FittedCommand::QuadTo(..) => {
                    if oi < off_map.len() {
                        off_map[oi] = Some(pos);
                    }
                    oi += 1;
                }
                FittedCommand::CurveTo(..) => {
                    oi += 2;
                }
                _ => {}
            }
        }
    }
    let mut candidate = upstream.to_vec();
    let apply = |cmd: &mut FittedCommand, delta: f64| -> bool {
        let nx = match cmd {
            FittedCommand::MoveTo(x, _) | FittedCommand::LineTo(x, _) => {
                let v = *x as f64 + delta;
                *x = v as f32;
                v
            }
            FittedCommand::QuadTo(_, _, x, _) => {
                let v = *x as f64 + delta;
                *x = v as f32;
                v
            }
            FittedCommand::CurveTo(_, _, _, _, x, _) => {
                let v = *x as f64 + delta;
                *x = v as f32;
                v
            }
            FittedCommand::Close => return true,
        };
        (nx as f32) as f64 == nx
    };
    for (&v, &delta) in &moves {
        let Some(Some(pos)) = on_map.get(v) else {
            return Ok(no("upright-index-missing"));
        };
        if !apply(&mut candidate[*pos], delta) {
            return Ok(no("upright-unrepresentable"));
        }
    }
    for (&c, &delta) in &off_moves {
        let Some(Some(pos)) = off_map.get(c) else {
            return Ok(no("upright-index-missing"));
        };
        match &mut candidate[*pos] {
            FittedCommand::QuadTo(x1, _, _, _) => {
                let v = *x1 as f64 + delta;
                if (v as f32) as f64 != v {
                    return Ok(no("upright-unrepresentable"));
                }
                *x1 = v as f32;
            }
            _ => return Ok(no("upright-index-missing")),
        }
    }
    // Validate: exact body width, head ratio, non-degeneracy, winding sign.
    let Ok(cand) = geometry::parse_commands(&candidate) else {
        return Ok(no("upright-candidate-malformed"));
    };
    if cand.oncurve[la][0] - fit.oncurve[la][0] != dl {
        return Ok(no("upright-candidate-check"));
    }
    let new_r = cand.oncurve[contour[body_r_seg].endpoints().0][0];
    if new_r - cand.oncurve[la][0] != s {
        return Ok(no("upright-candidate-width"));
    }
    let Some(cx_head) = quad_x_at_y(
        cand.oncurve[ha],
        cand.offcurve[hc],
        cand.oncurve[hb],
        y_mid_fit,
    ) else {
        return Ok(no("upright-candidate-head"));
    };
    if ((new_r - cx_head) - target_head).abs() > HEADROOM {
        return Ok(no("upright-candidate-head-width"));
    }
    // Whole-outline topology (components, counters, contacts) must match
    // upstream under the existing substituted-curve certificate, after
    // exact collinear merging of straight subdivisions.
    let (Some(ms), Some(mf), Some(mc)) = (
        merged_collinear(&src, &src),
        merged_collinear(&src, &fit),
        merged_collinear(&src, &cand),
    ) else {
        return Ok(no("upright-candidate-topology"));
    };
    if !super::curves::compare_substituted(&ms, &mf, &mc) {
        return Ok(no("upright-candidate-topology"));
    }
    // Retained head contrast profile at every station.
    for (k, frac) in [0.25, 0.5, 0.75].iter().enumerate() {
        let y = fit_ylo + (fit_yhi - fit_ylo) * frac;
        let geometry::Segment::Quad { c, a, b } = contour[head_segs[k]] else {
            return Ok(no("upright-head-not-quad"));
        };
        let Some(x_left) = quad_x_at_y(cand.oncurve[a], cand.offcurve[c], cand.oncurve[b], y)
        else {
            return Ok(no("upright-candidate-head"));
        };
        let expected = station_fit_widths[k] + (dr - dh);
        if ((new_r - x_left) - expected).abs() > HEADROOM {
            return Ok(no("upright-candidate-head-profile"));
        }
    }
    // Endpoint tangents of every moved head quad retain direction.
    for &ci in &chain {
        let geometry::Segment::Quad { c, a, b } = contour[ci] else {
            continue;
        };
        for (v, ctrl) in [(a, c), (b, c)] {
            let ft = [
                fit.offcurve[ctrl][0] - fit.oncurve[v][0],
                fit.offcurve[ctrl][1] - fit.oncurve[v][1],
            ];
            let ct = [
                cand.offcurve[ctrl][0] - cand.oncurve[v][0],
                cand.offcurve[ctrl][1] - cand.oncurve[v][1],
            ];
            if (ft[0] != 0.0 || ft[1] != 0.0) && ft[0] * ct[0] + ft[1] * ct[1] <= 0.0 {
                return Ok(no("upright-candidate-tangent"));
            }
        }
    }
    let area = |pts: &[[f64; 2]]| -> f64 {
        let mut a = 0.0;
        for i in 0..pts.len() {
            let p = pts[i];
            let q = pts[(i + 1) % pts.len()];
            a += p[0] * q[1] - q[0] * p[1];
        }
        a
    };
    if area(&fit.oncurve).signum() != area(&cand.oncurve).signum() || area(&cand.oncurve) == 0.0 {
        return Ok(no("upright-candidate-winding"));
    }
    for seg in contour.iter() {
        let (a, b) = seg.endpoints();
        if src.oncurve[a] != src.oncurve[b] && cand.oncurve[a] == cand.oncurve[b] {
            return Ok(no("upright-candidate-degenerate"));
        }
    }
    Ok(FitResult {
        commands: candidate,
        applied: true,
        reason: "upright-shared-border".to_string(),
        diagnostics: serde_json::json!({
            "model": "upright-shared-border-01",
            "standard": s, "source_body_width": w_body, "source_head_width": w_head,
            "source_head_min_width": w_head_min,
            "fitted_body_width": w_up, "fitted_head_width": w_head_fit,
            "target_head_width": target_head, "delta_body_left": dl,
            "delta_shared_right": dr, "delta_head_left": dh,
            "cap_body": cap_body, "cap_head": cap_head,
        }),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::diagonal_fitting::Anchor;

    #[derive(Clone, Copy)]
    enum S {
        L([f64; 2], [f64; 2]),
        Q([f64; 2], [f64; 2], [f64; 2]),
    }
    fn cmds(segs: &[S], reverse: bool) -> Vec<FittedCommand> {
        let pt = |p: [f64; 2]| (p[0] as f32, p[1] as f32);
        let mut out = Vec::new();
        if !reverse {
            let start = match segs[0] {
                S::L(a, _) | S::Q(a, _, _) => a,
            };
            out.push(FittedCommand::MoveTo(pt(start).0, pt(start).1));
            for s in segs {
                match *s {
                    S::L(_, b) => out.push(FittedCommand::LineTo(pt(b).0, pt(b).1)),
                    S::Q(_, c, b) => {
                        out.push(FittedCommand::QuadTo(pt(c).0, pt(c).1, pt(b).0, pt(b).1))
                    }
                }
            }
        } else {
            let end = match segs[segs.len() - 1] {
                S::L(_, b) | S::Q(_, _, b) => b,
            };
            out.push(FittedCommand::MoveTo(pt(end).0, pt(end).1));
            for s in segs.iter().rev() {
                match *s {
                    S::L(a, _) => out.push(FittedCommand::LineTo(pt(a).0, pt(a).1)),
                    S::Q(a, c, _) => {
                        out.push(FittedCommand::QuadTo(pt(c).0, pt(c).1, pt(a).0, pt(a).1))
                    }
                }
            }
        }
        out.push(FittedCommand::Close);
        out
    }
    fn scale(segs: &[S], k: f64) -> Vec<S> {
        segs.iter()
            .map(|s| match *s {
                S::L(a, b) => S::L([a[0] * k, a[1] * k], [b[0] * k, b[1] * k]),
                S::Q(a, c, b) => S::Q(
                    [a[0] * k, a[1] * k],
                    [c[0] * k, c[1] * k],
                    [b[0] * k, b[1] * k],
                ),
            })
            .collect()
    }
    fn shift(segs: &[S], dx: f64, dy: f64) -> Vec<S> {
        segs.iter()
            .map(|s| match *s {
                S::L(a, b) => S::L([a[0] + dx, a[1] + dy], [b[0] + dx, b[1] + dy]),
                S::Q(a, c, b) => S::Q(
                    [a[0] + dx, a[1] + dy],
                    [c[0] + dx, c[1] + dy],
                    [b[0] + dx, b[1] + dy],
                ),
            })
            .collect()
    }
    fn source_segs(head_left: f64) -> Vec<S> {
        vec![
            S::Q([4.0, 0.0], [3.0, 0.0], [2.0, 0.3]),
            S::Q([2.0, 0.3], [1.85, 0.8], [1.85, 2.2]),
            S::L([1.85, 2.2], [1.85, 7.0]),
            S::L([1.85, 7.0], [0.6, 7.0]),
            S::L([0.6, 7.0], [0.6, 7.95]),
            S::Q([0.6, 7.95], [1.2, 8.3], [head_left, 8.6]),
            S::Q(
                [head_left, 8.6],
                [head_left + 0.4, 9.8],
                [head_left + 0.5, 10.8],
            ),
            S::L([head_left + 0.5, 10.8], [3.3, 10.8]),
            S::L([3.3, 10.8], [3.3, 8.1]),
            S::L([3.3, 8.1], [5.8, 8.1]),
            S::L([5.8, 8.1], [5.8, 7.0]),
            S::L([5.8, 7.0], [3.3, 7.0]),
            S::L([3.3, 7.0], [3.3, 2.3]),
            S::Q([3.3, 2.3], [3.6, 1.3], [3.9, 0.9]),
            S::Q([3.9, 0.9], [5.0, 0.9], [5.6, 1.2]),
            S::L([5.6, 1.2], [6.0, 0.9]),
            S::L([6.0, 0.9], [4.0, 0.0]),
        ]
    }
    fn upstream_segs() -> Vec<S> {
        // Body collapsed to 1px (L=2, R=3); head curve shifted -0.13 in X.
        let mut segs = source_segs(1.9);
        for s in segs.iter_mut() {
            let map = |p: [f64; 2]| -> [f64; 2] {
                if p[0] == 3.3 {
                    [3.0, p[1]]
                } else if p[0] == 1.85 {
                    [2.0, p[1]]
                } else if p[1] >= 7.95 && p[0] < 3.3 && p[0] > 0.6 {
                    [p[0] - 0.13, p[1]]
                } else {
                    p
                }
            };
            *s = match *s {
                S::L(a, b) => S::L(map(a), map(b)),
                S::Q(a, c, b) => S::Q(map(a), map(c), map(b)),
            };
        }
        segs
    }
    fn anchor(seg_a: usize, seg_b: usize, fitted: f64) -> Anchor {
        anchor_w(seg_a, seg_b, fitted, 3.3f32 as f64 - 1.85f32 as f64)
    }
    fn anchor_w(seg_a: usize, seg_b: usize, fitted: f64, width: f64) -> Anchor {
        anchor_cert(seg_a, seg_b, fitted, width, true)
    }
    fn anchor_cert(
        seg_a: usize,
        seg_b: usize,
        fitted: f64,
        width: f64,
        unambiguous: bool,
    ) -> Anchor {
        Anchor {
            cert: Some(crate::diagonal_fitting::DonorCert {
                record: 9,
                contour: 0,
                seg_a,
                seg_b,
                border_width: width,
                fitted_border_width: fitted,
                unambiguous,
            }),
            source_width: width,
            fitted_width: fitted,
            rel: 0.0,
            length: 5.0,
            tangent: [0.0, 1.0],
            source_ids: format!("r9:c0a({seg_a},0.0000,1.0000)/b({seg_b},0.0000,1.0000)"),
        }
    }
    fn reference(donors: Vec<Anchor>) -> Reference {
        Reference {
            anchors: donors,
            size_px: 16.0,
            records: 3,
            n_anchors: 3,
            rel_min: None,
            rel_max: None,
            notes: vec![],
        }
    }
    fn taper_segs(bottom: f64, ctrl: f64, top: f64) -> Vec<S> {
        let mut segs = source_segs(bottom);
        segs[5] = S::Q([0.6, 7.95], [1.2, 8.3], [bottom, 8.6]);
        segs[6] = S::Q([bottom, 8.6], [ctrl, 9.8], [top, 10.8]);
        segs[7] = S::L([top, 10.8], [3.3, 10.8]);
        segs
    }
    fn map_upstream(segs: &[S]) -> Vec<S> {
        segs.iter()
            .map(|s| {
                let map = |p: [f64; 2]| -> [f64; 2] {
                    if p[0] == 3.3 {
                        [3.0, p[1]]
                    } else if p[0] == 1.85 {
                        [2.0, p[1]]
                    } else if p[1] >= 7.95 && p[0] < 3.3 && p[0] > 0.6 {
                        [p[0] - 0.13, p[1]]
                    } else {
                        p
                    }
                };
                match *s {
                    S::L(a, b) => S::L(map(a), map(b)),
                    S::Q(a, c, b) => S::Q(map(a), map(c), map(b)),
                }
            })
            .collect()
    }

    fn good_reference() -> Reference {
        // Self anchor (fitted 1) is certified ambiguous in its own
        // geometry; two unambiguous donors agree on the 2px standard.
        reference(vec![
            anchor_cert(2, 12, 1.0, 3.3f32 as f64 - 1.85f32 as f64, false),
            anchor(4, 14, 2.0),
            anchor(5, 15, 2.0),
        ])
    }
    fn run(
        src: &[S],
        up: &[S],
        reference: &Reference,
        axes: [bool; 2],
        reverse: bool,
    ) -> FitResult {
        fit(
            &cmds(src, reverse),
            &cmds(up, reverse),
            16.0,
            reference,
            axes,
        )
        .unwrap()
    }

    #[test]
    fn shared_border_body_reaches_standard_and_head_keeps_contrast() {
        let r = run(
            &source_segs(1.9),
            &upstream_segs(),
            &good_reference(),
            [false, false],
            false,
        );
        assert!(r.applied, "{}", r.reason);
        let parsed = geometry::parse_commands(&r.commands).unwrap();
        let up = geometry::parse_commands(&cmds(&upstream_segs(), false)).unwrap();
        // Y retained bit-exact; body width exactly the 2px standard.
        assert_eq!(
            parsed.oncurve.iter().map(|p| p[1]).collect::<Vec<_>>(),
            up.oncurve.iter().map(|p| p[1]).collect::<Vec<_>>()
        );
        let d = &r.diagnostics;
        assert_eq!(d["standard"], 2.0);
        let target_head = d["target_head_width"].as_f64().unwrap();
        assert!(
            target_head > 1.0 && target_head < 2.0,
            "head contrast retained: {target_head}"
        );
    }

    #[test]
    fn translation_reversal_and_subdivision_agree() {
        let base = run(
            &source_segs(1.9),
            &upstream_segs(),
            &good_reference(),
            [false, false],
            false,
        );
        assert!(base.applied);
        let w_shift = 13.3f32 as f64 - 11.85f32 as f64;
        let moved = run(
            &shift(&source_segs(1.9), 10.0, -5.0),
            &shift(&upstream_segs(), 10.0, -5.0),
            &reference(vec![
                anchor_cert(2, 12, 1.0, w_shift, false),
                anchor_w(4, 14, 2.0, w_shift),
                anchor_w(5, 15, 2.0, w_shift),
            ]),
            [false, false],
            false,
        );
        assert!(moved.applied, "{}", moved.reason);
        let rev = run(
            &source_segs(1.9),
            &upstream_segs(),
            &reference(vec![anchor(4, 14, 2.0), anchor(5, 15, 2.0)]),
            [false, false],
            true,
        );
        assert!(rev.applied, "{}", rev.reason);
        // Subdivide both body borders at their midpoints.
        let mut src = source_segs(1.9);
        src.splice(
            2..3,
            [
                S::L([1.85, 2.2], [1.85, 4.6]),
                S::L([1.85, 4.6], [1.85, 7.0]),
            ],
        );
        // R body segment is now index 13.
        src.splice(
            13..14,
            [S::L([3.3, 7.0], [3.3, 4.6]), S::L([3.3, 4.6], [3.3, 2.3])],
        );
        let mut up = upstream_segs();
        up.splice(
            2..3,
            [S::L([2.0, 2.2], [2.0, 4.6]), S::L([2.0, 4.6], [2.0, 7.0])],
        );
        up.splice(
            13..14,
            [S::L([3.0, 7.0], [3.0, 4.6]), S::L([3.0, 4.6], [3.0, 2.3])],
        );
        let sub = run(
            &src,
            &up,
            &reference(vec![
                anchor_cert(2, 14, 1.0, 3.3f32 as f64 - 1.85f32 as f64, false),
                anchor(4, 14, 2.0),
                anchor(5, 15, 2.0),
            ]),
            [false, false],
            false,
        );
        assert!(sub.applied, "{}", sub.reason);
    }

    #[test]
    fn abstains_on_native_conflict_ambiguous_standard_and_infeasible_budget() {
        let native = run(
            &source_segs(1.9),
            &upstream_segs(),
            &good_reference(),
            [false, true],
            false,
        );
        assert!(!native.applied);
        assert_eq!(native.commands, cmds(&upstream_segs(), false));
        let ambiguous = run(
            &source_segs(1.9),
            &upstream_segs(),
            &reference(vec![anchor(4, 14, 2.0), anchor(5, 15, 1.0)]),
            [false, false],
            false,
        );
        assert!(!ambiguous.applied);
        // Narrow head: its cap cannot cover the shared-border movement.
        let narrow_src = source_segs(3.0);
        let mut narrow_up = upstream_segs();
        for s in narrow_up.iter_mut() {
            *s = match *s {
                S::Q(a, c, b) if a[1] >= 7.95 => {
                    S::Q([a[0] + 1.1, a[1]], [c[0] + 1.1, c[1]], [b[0] + 1.1, b[1]])
                }
                other => other,
            };
        }
        let infeasible = run(
            &narrow_src,
            &narrow_up,
            &good_reference(),
            [false, false],
            false,
        );
        assert!(!infeasible.applied, "{}", infeasible.reason);
        // Already at the unanimous standard: exact no-op.
        let noop = run(
            &source_segs(1.9),
            &upstream_segs(),
            &reference(vec![anchor(4, 14, 1.0), anchor(5, 15, 1.0)]),
            [false, false],
            false,
        );
        assert!(!noop.applied);
    }

    #[test]
    fn uncertified_or_coincidental_donors_never_manufacture_unanimity() {
        // No certificate (pre-certificate packet): fail closed.
        let mut uncertified = anchor(4, 14, 2.0);
        uncertified.cert = None;
        let mut uncertified2 = anchor(5, 15, 2.0);
        uncertified2.cert = None;
        let r = run(
            &source_segs(1.9),
            &upstream_segs(),
            &reference(vec![uncertified, uncertified2]),
            [false, false],
            false,
        );
        assert!(!r.applied);
        // A genuinely unambiguous donor whose segments coincide with the
        // target's and whose fitted width equals the collapsed width is a
        // real dissenter, not self: the standard must not be manufactured.
        let r = run(
            &source_segs(1.9),
            &upstream_segs(),
            &reference(vec![anchor(2, 12, 1.0), anchor(4, 14, 2.0)]),
            [false, false],
            false,
        );
        assert!(!r.applied, "{}", r.reason);
    }

    #[test]
    fn build_reference_certificates_feed_the_stage() {
        // Real builder path (F3): rectangle donors measured by
        // build_reference itself, not hand-built widths.
        let donor_src = cmds(
            &[
                S::L([1.85, 2.2], [3.3, 2.2]),
                S::L([3.3, 2.2], [3.3, 7.0]),
                S::L([3.3, 7.0], [1.85, 7.0]),
                S::L([1.85, 7.0], [1.85, 2.2]),
            ],
            false,
        );
        let donor_fit = cmds(
            &[
                S::L([2.0, 2.2], [4.0, 2.2]),
                S::L([4.0, 2.2], [4.0, 7.0]),
                S::L([4.0, 7.0], [2.0, 7.0]),
                S::L([2.0, 7.0], [2.0, 2.2]),
            ],
            false,
        );
        // The MoveTo-based rectangle above starts at its first corner;
        // build_reference only needs source/fitted command pairs.
        let records: Vec<(&[FittedCommand], &[FittedCommand])> = vec![
            (donor_src.as_slice(), donor_fit.as_slice()),
            (donor_src.as_slice(), donor_fit.as_slice()),
        ];
        let built = crate::diagonal_fitting::build_reference(&records, 16.0);
        assert!(
            built
                .anchors
                .iter()
                .any(|a| a.cert.as_ref().is_some_and(|c| c.unambiguous)),
            "certs: {:?}",
            built.anchors
        );
        let r = fit(
            &cmds(&source_segs(1.9), false),
            &cmds(&upstream_segs(), false),
            16.0,
            &built,
            [false, false],
        )
        .unwrap();
        assert!(r.applied, "{}", r.reason);
    }

    #[test]
    fn historical_05_returns_upright_only_result_as_applied() {
        // Frozen 05 sequence: downstream stages abstain on this synthetic
        // outline; the upright-only correction ships with applied=true.
        let result = crate::diagonal_fitting::approved::fit_v05(
            None,
            &cmds(&source_segs(1.9), false),
            &cmds(&upstream_segs(), false),
            16.0,
            &good_reference(),
            [false, false],
        )
        .unwrap();
        assert!(result.applied, "{}", result.reason);
        assert_ne!(result.commands, cmds(&upstream_segs(), false));
        // Whole-outline authority: the delivered commands are exactly the
        // upright stage's certified output, not a downstream re-spend.
        let direct = fit(
            &cmds(&source_segs(1.9), false),
            &cmds(&upstream_segs(), false),
            16.0,
            &good_reference(),
            [false, false],
        )
        .unwrap();
        assert_eq!(result.commands, direct.commands);
        assert!(
            result.diagnostics.get("upright_stem").is_some()
                || result.reason.starts_with("upright:")
        );
    }

    #[test]
    fn approved_without_raw_never_applies_legacy_upright() {
        // New routing contract: without a raw source outline the
        // production route never ships the legacy upright stage; the
        // outline passes through unchanged with no legacy provenance.
        // The new route explicitly never applies an old stage and
        // requires the raw source for the shape mode.
        let upstream = cmds(&upstream_segs(), false);
        let result = crate::diagonal_fitting::approved::fit(
            None,
            &cmds(&source_segs(1.9), false),
            &upstream,
            16.0,
            &good_reference(),
            [false, false],
        )
        .unwrap();
        assert!(!result.applied, "{}", result.reason);
        assert_eq!(result.commands, upstream);
        assert!(result.diagnostics.get("upright_stem").is_none());
        assert!(result.diagnostics.get("source_shape").is_none());
    }

    #[test]
    fn station_certification_rejects_white_and_competing_boundaries() {
        // Ink rectangle: a station inside is certified, a station in the
        // white outside is not, and a competing boundary crossing the
        // station segment defeats dominance.
        let rect = geometry::parse_commands(&cmds(
            &[
                S::L([0.0, 0.0], [4.0, 0.0]),
                S::L([4.0, 0.0], [4.0, 4.0]),
                S::L([4.0, 4.0], [0.0, 4.0]),
                S::L([0.0, 4.0], [0.0, 0.0]),
            ],
            false,
        ))
        .unwrap();
        let chain = HashSet::new();
        assert!(station_certified(&rect, &chain, usize::MAX, 2.0, 1.0, 3.0));
        assert!(!station_certified(&rect, &chain, usize::MAX, 5.0, 1.0, 3.0));
        let crossed = geometry::parse_commands(&cmds(
            &[
                S::L([0.0, 0.0], [4.0, 0.0]),
                S::L([4.0, 0.0], [4.0, 4.0]),
                S::L([4.0, 4.0], [2.5, 4.0]),
                S::L([2.5, 4.0], [2.5, 1.5]),
                S::L([2.5, 1.5], [1.0, 1.5]),
                S::L([1.0, 1.5], [1.0, 4.0]),
                S::L([1.0, 4.0], [0.0, 4.0]),
                S::L([0.0, 4.0], [0.0, 0.0]),
            ],
            false,
        ))
        .unwrap();
        assert!(!station_certified(
            &crossed,
            &chain,
            usize::MAX,
            2.0,
            1.0,
            3.0
        ));
    }

    #[test]
    fn subdivided_horizontal_connector_reversing_past_moved_border_abstains() {
        // The crossbar connector is split very near the shared border.
        // The candidate moves the border past the stationary subdivision
        // point; collinearity survives but positive order does not, so
        // merging must not hide the backtracking from topology.
        let mut src = source_segs(1.9);
        src.splice(
            9..10,
            [S::L([3.3, 8.1], [3.35, 8.1]), S::L([3.35, 8.1], [5.8, 8.1])],
        );
        let mut up = upstream_segs();
        up.splice(
            9..10,
            [
                S::L([3.0, 8.1], [3.03125, 8.1]),
                S::L([3.03125, 8.1], [5.5, 8.1]),
            ],
        );
        let r = run(&src, &up, &good_reference(), [false, false], false);
        assert!(!r.applied, "{}", r.reason);
        assert_eq!(r.commands, cmds(&up, false));
    }

    #[test]
    fn huge_finite_width_abstains_without_unbounded_enumeration() {
        // Finite but enormous coordinates: the bounded critical-point
        // search evaluates a constant candidate set and abstains when
        // grid values leave the exactly representable range.
        let k = 1e17;
        let w = ((3.3f64 * k) as f32) as f64 - ((1.85f64 * k) as f32) as f64;
        let reference = reference(vec![
            anchor_cert(2, 12, 1.0, w, false),
            anchor_cert(4, 14, 2.0, w, true),
            anchor_cert(5, 15, 2.0, w, true),
        ]);
        let r = run(
            &scale(&source_segs(1.9), k),
            &scale(&upstream_segs(), k),
            &reference,
            [false, false],
            false,
        );
        assert!(!r.applied, "{}", r.reason);
    }

    #[test]
    fn legacy_reference_without_certificates_replays_as_abstention() {
        // Pre-certificate packets deserialize with cert=None and remain
        // on the historical path: no donor is eligible, exact abstention.
        let legacy: Reference = serde_json::from_str(
            r#"{"anchors":[{"source_width":1.45,"fitted_width":2.0,"rel":0.0,
            "length":5.0,"tangent":[0.0,1.0],"source_ids":"r0:c0a(4,0)/b(14,0)"}],
            "size_px":16.0,"records":1,"n_anchors":1,"rel_min":null,
            "rel_max":null,"notes":[]}"#,
        )
        .unwrap();
        assert!(legacy.anchors[0].cert.is_none());
        let r = run(
            &source_segs(1.9),
            &upstream_segs(),
            &legacy,
            [false, false],
            false,
        );
        assert!(!r.applied);
        assert_eq!(r.commands, cmds(&upstream_segs(), false));
    }

    #[test]
    fn tapered_head_uses_narrowest_certified_sample_for_its_cap() {
        // Moderate taper: quarter width below the midpoint width, but a
        // feasible phase exists inside the narrowest-sample cap.
        let moderate_src = taper_segs(2.8, 1.5, 2.8);
        let moderate = run(
            &moderate_src,
            &map_upstream(&moderate_src),
            &good_reference(),
            [false, false],
            false,
        );
        assert!(moderate.applied, "{}", moderate.reason);
        assert!(
            moderate.diagnostics["cap_head"].as_f64().unwrap()
                < moderate.diagnostics["source_head_width"].as_f64().unwrap() / 2.0
        );
        // Strong taper: the midpoint budget would admit the shared-border
        // move, but the quarter-station cap cannot cover it together
        // with the body cap, so the stage fails closed exactly.
        let strong_src = taper_segs(3.1, 1.5, 3.1);
        let strong_up = map_upstream(&strong_src);
        let strong = run(
            &strong_src,
            &strong_up,
            &good_reference(),
            [false, false],
            false,
        );
        assert!(!strong.applied, "{}", strong.reason);
        assert_eq!(strong.commands, cmds(&strong_up, false));
    }

    #[test]
    fn oversize_outline_abstains() {
        let big: Vec<FittedCommand> = (0..600)
            .flat_map(|_| cmds(&upstream_segs(), false))
            .collect();
        let r = fit(
            &cmds(&source_segs(1.9), false),
            &big,
            16.0,
            &good_reference(),
            [false, false],
        )
        .unwrap();
        assert!(!r.applied);
    }
}
