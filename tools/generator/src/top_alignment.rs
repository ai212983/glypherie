//! Recover missed x-height associations on automatic Mono outlines.
//!
//! [Model and sources](../../../docs/revisions/001/03-spacing-kerning.md#source-defined-x-height-alignment).

use crate::{fail, probe::FittedCommand, Config, Error};
use skrifa::MetadataProvider;

pub const MODEL: &str = "top-align-02";

// FreeType compute_blue_edges: association is capped at half a pixel.
const MISS_PX: f64 = 0.5;
// Adapt FreeType compute_edges' one-pixel segment minimum to top regions.
const MIN_RUN_PX: f64 = 1.0;

pub struct Zone {
    pub source_ref: f64,
    pub target: f64,
}

pub struct Fit {
    pub commands: Vec<FittedCommand>,
    pub applied: bool,
    pub contours: Vec<usize>,
    pub excess_px: f64,
    pub mark_translations: Vec<(usize, f64)>,
}

/// Variation-aware OS/2 height seeds; fitted donors determine the target.
pub fn zone_refs(data: &[u8], settings: &Config) -> Result<(Option<f64>, Option<f64>), Error> {
    if !settings.size_px.is_finite() || settings.size_px <= 0.0 {
        return Err(fail("top alignment requires finite positive size"));
    }
    let font = skrifa::FontRef::new(data).map_err(|e| fail(format!("invalid font: {e}")))?;
    for (tag, value) in &settings.axes {
        if tag.len() != 4 || !tag.is_ascii() {
            return Err(fail(format!("axis tag {tag:?} must be four ASCII bytes")));
        }
        let axis = font
            .axes()
            .iter()
            .find(|a| a.tag().to_string() == *tag)
            .ok_or_else(|| fail(format!("unsupported axis {tag}")))?;
        if !value.is_finite() || *value < axis.min_value() || *value > axis.max_value() {
            return Err(fail(format!(
                "axis {tag} must be within {}..={}",
                axis.min_value(),
                axis.max_value()
            )));
        }
    }
    let location = font
        .axes()
        .location(settings.axes.iter().map(|(t, v)| (t.as_str(), *v)));
    let metrics = font.metrics(skrifa::instance::Size::new(settings.size_px), &location);
    let zone = |v: Option<f32>| {
        v.filter(|v| v.is_finite() && *v > 0.0)
            .map(|v| f64::from(v))
    };
    Ok((zone(metrics.x_height), zone(metrics.cap_height)))
}

fn fitted_reference(position_px: f64) -> f64 {
    (position_px + 0.5).floor()
}

fn association(size_px: f32) -> f64 {
    (f64::from(size_px) / 40.0).min(MISS_PX)
}

fn coords(command: &FittedCommand) -> Vec<(f32, f32)> {
    match *command {
        FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => vec![(x, y)],
        FittedCommand::QuadTo(x1, y1, x, y) => vec![(x1, y1), (x, y)],
        FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => vec![(x1, y1), (x2, y2), (x, y)],
        FittedCommand::Close => vec![],
    }
}

fn endpoint(command: &FittedCommand) -> Option<(f64, f64)> {
    match *command {
        FittedCommand::MoveTo(x, y)
        | FittedCommand::LineTo(x, y)
        | FittedCommand::QuadTo(_, _, x, y)
        | FittedCommand::CurveTo(_, _, _, _, x, y) => Some((f64::from(x), f64::from(y))),
        FittedCommand::Close => None,
    }
}

fn contour_ranges(commands: &[FittedCommand]) -> Option<Vec<(usize, usize)>> {
    let mut ranges = Vec::new();
    let mut open: Option<usize> = None;
    for (i, command) in commands.iter().enumerate() {
        match command {
            FittedCommand::MoveTo(..) => {
                if open.is_some() {
                    return None;
                }
                open = Some(i);
            }
            FittedCommand::Close => {
                let Some(start) = open.take() else {
                    return None;
                };
                ranges.push((start, i + 1));
            }
            _ => {
                if open.is_none() {
                    return None;
                }
            }
        }
    }
    if open.is_some() {
        return None;
    }
    Some(ranges)
}

fn contour_min_max(commands: &[FittedCommand]) -> (f64, f64) {
    let mut lo = f64::INFINITY;
    let mut hi = f64::NEG_INFINITY;
    for command in commands {
        for (_, y) in coords(command) {
            let y = f64::from(y);
            lo = lo.min(y);
            hi = hi.max(y);
        }
    }
    (lo, hi)
}

fn flat_top(contour: &[FittedCommand], reference: f64, band: f64) -> Option<f64> {
    let (_, src_max) = contour_min_max(contour);
    if !src_max.is_finite() {
        return None;
    }
    let mut pen: Option<(f64, f64)> = None;
    let mut start: Option<(f64, f64)> = None;
    let mut found = false;
    let mut run = |a: (f64, f64), b: (f64, f64)| {
        let (dx, dy) = (b.0 - a.0, b.1 - a.1);
        if dx == 0.0 && dy == 0.0 {
            return;
        }
        if a.1.max(b.1) == src_max
            && dx.abs() >= MIN_RUN_PX
            && (a.1 - reference).abs() <= band
            && (b.1 - reference).abs() <= band
        {
            found = true;
        }
    };
    for command in contour {
        match *command {
            FittedCommand::MoveTo(x, y) => {
                pen = Some((f64::from(x), f64::from(y)));
                start = pen;
            }
            FittedCommand::LineTo(x, y) => {
                let q = (f64::from(x), f64::from(y));
                if let Some(p) = pen {
                    run(p, q);
                }
                pen = Some(q);
            }
            FittedCommand::QuadTo(..) | FittedCommand::CurveTo(..) => {
                pen = endpoint(command);
            }
            FittedCommand::Close => {
                if let (Some(p), Some(s)) = (pen, start) {
                    run(p, s);
                }
                pen = None;
                start = None;
            }
        }
    }
    found.then_some(src_max)
}

/// Retain the donors' agreed fitted height, including upstream x-height scaling.
pub fn zone(
    pairs: &[(&[FittedCommand], &[FittedCommand])],
    seed_x_height_px: f64,
    size_px: f32,
) -> Option<Zone> {
    if !seed_x_height_px.is_finite() || !(seed_x_height_px > 0.0) {
        return None;
    }
    if !size_px.is_finite() || !(size_px > 0.0) {
        return None;
    }
    let band = association(size_px);
    let mut tops = Vec::new();
    let mut target = None;
    for (source, upstream) in pairs {
        if source.len() != upstream.len()
            || source
                .iter()
                .zip(*upstream)
                .any(|(a, b)| std::mem::discriminant(a) != std::mem::discriminant(b))
        {
            continue;
        }
        let (Some(src_ranges), Some(fit_ranges)) =
            (contour_ranges(source), contour_ranges(upstream))
        else {
            continue;
        };
        if src_ranges != fit_ranges {
            continue;
        }
        for (a, b) in src_ranges {
            let Some(top) = flat_top(&source[a..b], seed_x_height_px, band) else {
                continue;
            };
            let (_, fitted_top) = contour_min_max(&upstream[a..b]);
            if !fitted_top.is_finite() || fitted_top <= 0.0 || fitted_top.fract() != 0.0 {
                continue;
            }
            if target.is_some_and(|height| height != fitted_top) {
                return None;
            }
            target = Some(fitted_top);
            tops.push(top);
        }
    }
    let target = target?;
    tops.sort_by(|a, b| a.total_cmp(b));
    Some(Zone {
        source_ref: tops[tops.len() / 2],
        target,
    })
}

/// Align supported body tops and marks; unsupported geometry keeps the preceding fit.
pub fn fit(
    source: &[FittedCommand],
    upstream: &[FittedCommand],
    zone: &Zone,
    cap_height_px: Option<f64>,
    size_px: f32,
) -> Result<Fit, Error> {
    let unchanged = || Fit {
        commands: upstream.to_vec(),
        applied: false,
        contours: Vec::new(),
        excess_px: 0.0,
        mark_translations: Vec::new(),
    };
    if !size_px.is_finite() || !(size_px > 0.0) {
        return Err(fail("top alignment requires finite positive size"));
    }
    if !zone.source_ref.is_finite() || !zone.target.is_finite() {
        return Ok(unchanged());
    }
    if source.len() != upstream.len()
        || source
            .iter()
            .zip(upstream)
            .any(|(a, b)| std::mem::discriminant(a) != std::mem::discriminant(b))
    {
        return Ok(unchanged());
    }
    for command in source.iter().chain(upstream) {
        if coords(command)
            .iter()
            .any(|&(x, y)| !x.is_finite() || !y.is_finite())
        {
            return Err(fail("top alignment requires finite outline coordinates"));
        }
    }
    let (Some(src_ranges), Some(fit_ranges)) = (contour_ranges(source), contour_ranges(upstream))
    else {
        return Ok(unchanged());
    };
    if src_ranges.len() != fit_ranges.len() {
        return Ok(unchanged());
    }
    let band = association(size_px);
    let mut commands = upstream.to_vec();
    let mut contours = Vec::new();
    let mut excess_px: f64 = 0.0;
    for (index, ((a, b), (c, d))) in src_ranges.iter().zip(&fit_ranges).enumerate() {
        if (a, b) != (c, d) {
            continue;
        }
        if !isolated_contour(source, &src_ranges, index)
            || !isolated_contour(upstream, &fit_ranges, index)
        {
            continue;
        }
        let Some(anchors) = contour_anchors(
            &source[*a..*b],
            &upstream[*c..*d],
            zone,
            cap_height_px,
            band,
        ) else {
            continue;
        };
        for command in &mut commands[*c..*d] {
            let remap = |v: &mut f32| {
                let y = f64::from(*v);
                let mut prev = &anchors[0];
                for next in &anchors[1..] {
                    if y <= next.0 || next == &anchors[anchors.len() - 1] {
                        let k = (next.1 - prev.1) / (next.0 - prev.0);
                        *v = (prev.1 + (y - prev.0) * k) as f32;
                        break;
                    }
                    prev = next;
                }
            };
            match command {
                FittedCommand::MoveTo(_, y) | FittedCommand::LineTo(_, y) => remap(y),
                FittedCommand::QuadTo(_, y1, _, y) => {
                    remap(y1);
                    remap(y);
                }
                FittedCommand::CurveTo(_, y1, _, y2, _, y) => {
                    remap(y1);
                    remap(y2);
                    remap(y);
                }
                FittedCommand::Close => {}
            }
        }
        let (_, top) = contour_min_max(&upstream[*c..*d]);
        excess_px = excess_px.max(top - zone.target);
        contours.push(index);
    }
    if contours.is_empty() {
        return Ok(unchanged());
    }
    let Some(mark_translations) =
        position_marks(source, upstream, &mut commands, &src_ranges, &contours)
    else {
        return Ok(unchanged());
    };
    Ok(Fit {
        commands,
        applied: true,
        contours,
        excess_px,
        mark_translations,
    })
}

fn contour_bounds(commands: &[FittedCommand]) -> [f64; 4] {
    let mut bounds = [
        f64::INFINITY,
        f64::INFINITY,
        f64::NEG_INFINITY,
        f64::NEG_INFINITY,
    ];
    for command in commands {
        for (x, y) in coords(command) {
            let (x, y) = (f64::from(x), f64::from(y));
            bounds[0] = bounds[0].min(x);
            bounds[1] = bounds[1].min(y);
            bounds[2] = bounds[2].max(x);
            bounds[3] = bounds[3].max(y);
        }
    }
    bounds
}

fn isolated_contour(commands: &[FittedCommand], ranges: &[(usize, usize)], index: usize) -> bool {
    let (a, b) = ranges[index];
    let a = contour_bounds(&commands[a..b]);
    ranges.iter().enumerate().all(|(i, &(start, end))| {
        if i == index {
            return true;
        }
        let b = contour_bounds(&commands[start..end]);
        a[2] < b[0] || b[2] < a[0] || a[3] < b[1] || b[3] < a[1]
    })
}

fn certified_minimum(commands: &[FittedCommand]) -> Option<f64> {
    let min = contour_min_max(commands).0;
    // An on-curve point attains the hull bound, certifying the true extremum.
    commands
        .iter()
        .filter_map(endpoint)
        .any(|(_, y)| y == min)
        .then_some(min)
}

fn position_marks(
    source: &[FittedCommand],
    upstream: &[FittedCommand],
    commands: &mut [FittedCommand],
    ranges: &[(usize, usize)],
    bodies: &[usize],
) -> Option<Vec<(usize, f64)>> {
    let bounds: Vec<_> = ranges
        .iter()
        .map(|&(a, b)| contour_bounds(&source[a..b]))
        .collect();
    let fitted_bounds: Vec<_> = ranges
        .iter()
        .map(|&(a, b)| contour_bounds(&upstream[a..b]))
        .collect();
    let corrected_bounds: Vec<_> = ranges
        .iter()
        .map(|&(a, b)| contour_bounds(&commands[a..b]))
        .collect();
    let above = |bounds: &[[f64; 4]], body: usize, mark: usize| {
        let b = bounds[body];
        let m = bounds[mark];
        body != mark && b[1] <= 0.0 && b[3] > 0.0 && m[1] > b[3] && m[0] < b[2] && b[0] < m[2]
    };
    let mut translations = Vec::new();
    for &body in bodies {
        let marks: Vec<_> = (0..ranges.len())
            .filter(|&mark| above(&bounds, body, mark))
            .collect();
        if marks.is_empty() {
            continue;
        }
        if marks.len() != 1 {
            return None;
        }
        let mark = marks[0];
        if (0..ranges.len())
            .filter(|&candidate| above(&bounds, candidate, mark))
            .count()
            != 1
            || !above(&fitted_bounds, body, mark)
            || !above(&corrected_bounds, body, mark)
            || (0..ranges.len())
                .filter(|&candidate| above(&fitted_bounds, candidate, mark))
                .count()
                != 1
            || (0..ranges.len())
                .filter(|&candidate| above(&corrected_bounds, candidate, mark))
                .count()
                != 1
            || !isolated_contour(source, ranges, mark)
            || !isolated_contour(upstream, ranges, mark)
        {
            return None;
        }
        let (a, b) = ranges[body];
        let (c, d) = ranges[mark];
        let source_gap = certified_minimum(&source[c..d])? - contour_min_max(&source[a..b]).1;
        let gap = fitted_reference(source_gap);
        let old_bottom = certified_minimum(&upstream[c..d])?;
        let old_gap = old_bottom - contour_min_max(&upstream[a..b]).1;
        // Nearest-pixel rounding accounts for at most half a pixel of gap error.
        if gap <= 0.0 || (old_gap - gap).abs() > 0.5 {
            return None;
        }
        let delta = contour_min_max(&commands[a..b]).1 + gap - old_bottom;
        for command in &mut commands[c..d] {
            let shift = |y: &mut f32| *y = (f64::from(*y) + delta) as f32;
            match command {
                FittedCommand::MoveTo(_, y) | FittedCommand::LineTo(_, y) => shift(y),
                FittedCommand::QuadTo(_, y1, _, y) => {
                    shift(y1);
                    shift(y);
                }
                FittedCommand::CurveTo(_, y1, _, y2, _, y) => {
                    shift(y1);
                    shift(y2);
                    shift(y);
                }
                FittedCommand::Close => {}
            }
        }
        if !isolated_contour(commands, ranges, mark)
            || commands[c..d]
                .iter()
                .flat_map(coords)
                .any(|(_, y)| !y.is_finite())
        {
            return None;
        }
        translations.push((mark, delta));
    }
    Some(translations)
}

/// Retained `(fitted, corrected)` anchors for a missed top association.
fn contour_anchors(
    source: &[FittedCommand],
    upstream: &[FittedCommand],
    zone: &Zone,
    cap_height_px: Option<f64>,
    band: f64,
) -> Option<Vec<(f64, f64)>> {
    let (src_min, _) = contour_min_max(source);
    let top = flat_top(source, zone.source_ref, band)?;
    if (top - zone.source_ref).abs() > band {
        return None;
    }
    if !(src_min <= 0.0) {
        return None;
    }
    let (anchor, fit_top) = contour_min_max(upstream);
    if !(anchor <= 0.0) {
        return None;
    }
    let excess = fit_top - zone.target;
    if excess < MISS_PX {
        return None;
    }
    // A top reaching the next reference may belong to that zone.
    if let Some(cap) = cap_height_px {
        if !cap.is_finite() || fit_top >= fitted_reference(cap) {
            return None;
        }
    }
    if !(zone.target > anchor) {
        return None;
    }
    let protected = baseline_protection(upstream);
    if protected >= zone.target {
        return None;
    }
    let mut anchors = vec![(anchor, anchor)];
    if protected > anchor {
        anchors.push((protected, protected));
    }
    anchors.push((fit_top, zone.target));
    for pair in anchors.windows(2) {
        let k = (pair[1].1 - pair[0].1) / (pair[1].0 - pair[0].0);
        if !(k > 0.0 && k <= 1.0) {
            return None;
        }
    }
    if (fit_top - anchor) <= 0.0 {
        return None;
    }
    let top_k =
        (zone.target - anchors[anchors.len() - 2].1) / (fit_top - anchors[anchors.len() - 2].0);
    if !(top_k < 1.0) {
        return None;
    }
    Some(anchors)
}

// Keep complete curve hulls crossing the baseline fixed. Changing a positive
// control of such a curve can otherwise move its sub-baseline geometry.
fn baseline_protection(commands: &[FittedCommand]) -> f64 {
    let mut protected = 0.0_f64;
    let mut pen = None;
    let mut start = None;
    for command in commands {
        if let FittedCommand::MoveTo(x, y) = *command {
            pen = Some((x, y));
            start = pen;
            continue;
        }
        let Some((x, y)) = pen else {
            continue;
        };
        let mut points = coords(command);
        if matches!(command, FittedCommand::Close) {
            points.extend(start);
        }
        if points.is_empty() {
            continue;
        }
        let vertical_line = matches!(command, FittedCommand::LineTo(..) | FittedCommand::Close)
            && points.iter().all(|p| p.0 == x);
        let lo = points.iter().fold(y, |v, p| v.min(p.1));
        let hi = points.iter().fold(y, |v, p| v.max(p.1));
        if !vertical_line && lo <= 0.0 && hi > 0.0 {
            protected = protected.max(f64::from(hi));
        }
        pen = points.last().copied();
    }
    protected
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::probe::FittedCommand::{Close, LineTo, MoveTo, QuadTo};

    fn body_source(top: f32) -> Vec<FittedCommand> {
        vec![
            MoveTo(0.0, 0.0),
            LineTo(0.0, 8.0),
            LineTo(2.0, top),
            LineTo(2.2, top - 0.1),
            LineTo(2.2, 0.0),
            Close,
        ]
    }

    fn body_fitted(top: f32) -> Vec<FittedCommand> {
        vec![
            MoveTo(0.0, 0.0),
            LineTo(0.0, 8.0),
            LineTo(2.0, top),
            LineTo(2.2, top - 0.1),
            LineTo(2.2, 0.0),
            Close,
        ]
    }

    fn zone16(source: &[FittedCommand], upstream: &[FittedCommand]) -> Option<Zone> {
        zone(&[(source, upstream)], 8.112, 16.0)
    }

    fn max_y(commands: &[FittedCommand]) -> f64 {
        contour_min_max(commands).1
    }

    #[test]
    fn missed_flat_top_contracts_to_verified_target() {
        let source = body_source(8.156);
        let donor_source = body_source(8.11);
        let donor_fitted = body_fitted(8.0);
        let upstream = body_fitted(8.89);
        let all = [
            (donor_source.as_slice(), donor_fitted.as_slice()),
            (source.as_slice(), upstream.as_slice()),
        ];
        let zone = zone(&all, 8.112, 16.0).expect("verified zone");
        assert_eq!(zone.target, 8.0);
        let fit = fit(&source, &upstream, &zone, Some(11.2), 16.0).unwrap();
        assert!(fit.applied);
        assert_eq!(fit.contours, vec![0]);
        assert!((fit.excess_px - 0.89).abs() < 1e-6);
        assert!((max_y(&fit.commands) - 8.0).abs() < 1e-6);
        let flat: Vec<f64> = fit
            .commands
            .iter()
            .flat_map(|c| coords(c).into_iter().map(|(_, y)| f64::from(y)))
            .collect();
        let raw: Vec<f64> = upstream
            .iter()
            .flat_map(|c| coords(c).into_iter().map(|(_, y)| f64::from(y)))
            .collect();
        assert_eq!(flat[0], 0.0);
        for (a, b) in flat.iter().zip(&raw) {
            assert!(*a <= *b + 1e-9);
        }
        for i in 0..flat.len() {
            for j in 0..flat.len() {
                assert!((raw[i] - raw[j]) * (flat[i] - flat[j]) >= 0.0);
            }
        }
    }

    #[test]
    fn unverified_zone_abstains() {
        let source = body_source(8.156);
        let upstream = body_fitted(8.89);
        assert!(zone16(&source, &upstream).is_none());
    }

    #[test]
    fn curved_top_keeps_automatic_geometry() {
        let arch_source = vec![
            MoveTo(0.0, 0.0),
            LineTo(0.0, 7.0),
            QuadTo(1.0, 8.28, 2.0, 8.28),
            LineTo(2.0, 0.0),
            Close,
        ];
        let arch_fitted = vec![
            MoveTo(0.0, 0.0),
            LineTo(0.0, 7.0),
            QuadTo(1.0, 8.0, 2.0, 8.0),
            LineTo(2.0, 0.0),
            Close,
        ];
        let source = body_source(8.156);
        let upstream = body_fitted(8.0);
        let all = [
            (arch_source.as_slice(), arch_fitted.as_slice()),
            (source.as_slice(), upstream.as_slice()),
        ];
        let zone = zone(&all, 8.112, 16.0).expect("arch verifies");
        assert_eq!(zone.target, 8.0);
        let fit = fit(&arch_source, &arch_fitted, &zone, Some(11.2), 16.0).unwrap();
        assert!(!fit.applied);
    }

    #[test]
    fn decision_survives_translation_and_scaling() {
        let source = body_source(8.156);
        let upstream = body_fitted(8.89);
        let shift_x = |commands: &[FittedCommand], dx: f32| {
            commands
                .iter()
                .map(|c| match c {
                    MoveTo(x, y) => MoveTo(*x + dx, *y),
                    LineTo(x, y) => LineTo(*x + dx, *y),
                    QuadTo(x1, y1, x, y) => QuadTo(*x1 + dx, *y1, *x + dx, *y),
                    Close => Close,
                    _ => unimplemented!(),
                })
                .collect::<Vec<_>>()
        };
        let donor_source = body_source(8.11);
        let donor_fitted = body_fitted(8.0);
        let all = [
            (donor_source.as_slice(), donor_fitted.as_slice()),
            (source.as_slice(), upstream.as_slice()),
        ];
        let zone = zone(&all, 8.112, 16.0).expect("verified zone");
        let plain = fit(&source, &upstream, &zone, Some(11.2), 16.0).unwrap();
        let moved = fit(
            &shift_x(&source, 5.0),
            &shift_x(&upstream, 5.0),
            &zone,
            Some(11.2),
            16.0,
        )
        .unwrap();
        assert!(moved.applied);
        assert_eq!(moved.contours, plain.contours);
        assert!((max_y(&moved.commands) - max_y(&plain.commands)).abs() < 1e-6);
        let scale = |commands: &[FittedCommand], s: f32| {
            commands
                .iter()
                .map(|c| match c {
                    MoveTo(x, y) => MoveTo(*x * s, *y * s),
                    LineTo(x, y) => LineTo(*x * s, *y * s),
                    QuadTo(x1, y1, x, y) => QuadTo(*x1 * s, *y1 * s, *x * s, *y * s),
                    Close => Close,
                    _ => unimplemented!(),
                })
                .collect::<Vec<_>>()
        };
        let s = 2.0;
        let s_zone = Zone {
            source_ref: 8.156 * f64::from(s),
            target: 16.0,
        };
        let fit = fit(
            &scale(&source, s),
            &scale(&upstream, s),
            &s_zone,
            Some(11.2 * f64::from(s)),
            16.0,
        )
        .unwrap();
        assert!(fit.applied);
        assert!((max_y(&fit.commands) - 16.0).abs() < 1e-3);
    }

    #[test]
    fn ineligible_geometry_abstains() {
        let source = body_source(8.156);
        let upstream = body_fitted(8.89);
        let donor_source = body_source(8.11);
        let donor_fitted = body_fitted(8.0);
        let all = [
            (donor_source.as_slice(), donor_fitted.as_slice()),
            (source.as_slice(), upstream.as_slice()),
        ];
        let zone = zone(&all, 8.112, 16.0).expect("verified zone");
        let steep = vec![
            MoveTo(0.0, 0.0),
            LineTo(2.0, 6.0),
            LineTo(2.2, 8.156),
            LineTo(2.4, 0.0),
            Close,
        ];
        assert!(
            !fit(&steep, &body_fitted(8.89), &zone, Some(11.2), 16.0)
                .unwrap()
                .applied
        );
        let short = vec![
            MoveTo(0.0, 0.0),
            LineTo(0.0, 8.0),
            LineTo(0.5, 8.156),
            LineTo(0.6, 8.0),
            LineTo(0.6, 0.0),
            Close,
        ];
        assert!(
            !fit(&short, &body_fitted(8.89), &zone, Some(11.2), 16.0)
                .unwrap()
                .applied
        );
        assert!(
            !fit(&source, &body_fitted(8.2), &zone, Some(11.2), 16.0)
                .unwrap()
                .applied
        );
        assert!(
            !fit(&source, &body_fitted(7.8), &zone, Some(11.2), 16.0)
                .unwrap()
                .applied
        );
        let floating = vec![
            MoveTo(0.0, 10.0),
            LineTo(0.0, 10.5),
            LineTo(2.0, 10.6),
            LineTo(2.0, 10.0),
            Close,
        ];
        let floating_fit = vec![
            MoveTo(0.0, 10.0),
            LineTo(0.0, 10.5),
            LineTo(2.0, 11.5),
            LineTo(2.0, 10.0),
            Close,
        ];
        assert!(
            !fit(&floating, &floating_fit, &zone, Some(12.0), 16.0)
                .unwrap()
                .applied
        );
        assert!(
            !fit(&source, &upstream, &zone, Some(8.0), 16.0)
                .unwrap()
                .applied
        );
        let mut mismatched = upstream.clone();
        mismatched.push(LineTo(0.0, 0.0));
        assert!(
            !fit(&source, &mismatched, &zone, Some(11.2), 16.0)
                .unwrap()
                .applied
        );
        assert!(fit(&source, &upstream, &zone, Some(11.2), 0.0).is_err());
        let mut bad = upstream.clone();
        bad[1] = LineTo(0.0, f32::NAN);
        assert!(fit(&source, &bad, &zone, Some(11.2), 16.0).is_err());
    }

    #[test]
    fn descender_region_and_other_contours_stay_fixed() {
        let source = vec![
            MoveTo(0.0, -3.6),
            LineTo(0.0, 8.0),
            LineTo(2.0, 8.156),
            LineTo(2.2, 8.0),
            LineTo(2.2, -3.0),
            Close,
        ];
        let upstream = vec![
            MoveTo(0.0, -2.28),
            LineTo(0.0, 0.5),
            LineTo(2.0, 9.156),
            LineTo(2.2, 9.0),
            LineTo(2.2, -2.0),
            Close,
        ];
        let donor_source = body_source(8.11);
        let donor_fitted = body_fitted(8.0);
        let all = [
            (donor_source.as_slice(), donor_fitted.as_slice()),
            (source.as_slice(), upstream.as_slice()),
        ];
        let zone = zone(&all, 8.112, 16.0).expect("verified zone");
        let fit = fit(&source, &upstream, &zone, Some(11.2), 16.0).unwrap();
        assert!(fit.applied);
        let flat: Vec<(f32, f32)> = fit
            .commands
            .iter()
            .flat_map(|c| coords(c).into_iter())
            .collect();
        let raw: Vec<(f32, f32)> = upstream
            .iter()
            .flat_map(|c| coords(c).into_iter())
            .collect();
        for ((_, y), (_, u)) in flat.iter().zip(&raw) {
            if *u <= 0.0 {
                assert_eq!(y, u);
            }
        }
        assert!((max_y(&fit.commands) - 8.0).abs() < 1e-6);
    }
    #[test]
    fn zone_retains_actual_fitted_height_and_rejects_disagreement() {
        let mut source = body_source(10.14);
        source[1] = LineTo(0.0, 10.0);
        let fitted = body_fitted(11.0);
        let raised = zone(&[(source.as_slice(), fitted.as_slice())], 10.14, 20.0).unwrap();
        assert_eq!(raised.target, 11.0);
        let conflict = body_fitted(10.0);
        assert!(zone(
            &[
                (source.as_slice(), fitted.as_slice()),
                (source.as_slice(), conflict.as_slice())
            ],
            10.14,
            20.0
        )
        .is_none());
    }

    #[test]
    fn overlapping_contours_cannot_move_against_each_other() {
        let mut source = body_source(8.156);
        let mut upstream = body_fitted(8.89);
        let hole = vec![
            MoveTo(0.5, 1.0),
            LineTo(1.5, 1.0),
            LineTo(1.5, 7.0),
            LineTo(0.5, 7.0),
            Close,
        ];
        source.extend(hole.clone());
        upstream.extend(hole);
        let result = fit(
            &source,
            &upstream,
            &Zone {
                source_ref: 8.112,
                target: 8.0,
            },
            Some(11.2),
            16.0,
        )
        .unwrap();
        assert!(!result.applied);
        assert_eq!(result.commands, upstream);
    }
    fn mark(lo: f32, hi: f32, dx: f32) -> Vec<FittedCommand> {
        vec![
            MoveTo(0.5 + dx, lo),
            LineTo(1.5 + dx, lo),
            LineTo(1.5 + dx, hi),
            LineTo(0.5 + dx, hi),
            Close,
        ]
    }

    #[test]
    fn detached_mark_keeps_shape_and_source_distance() {
        for scale in [1.0, 2.0] {
            for offset in [0.0, 7.0] {
                let source_mark = mark(10.08, 11.75, 0.0);
                let fitted_mark = mark(11.0, 12.0, 0.0);
                let mut source = body_source(8.156);
                source.extend(source_mark);
                let mut upstream = body_fitted(8.89);
                upstream.extend(fitted_mark.clone());
                let transform = |commands: &[FittedCommand]| {
                    commands
                        .iter()
                        .map(|command| match *command {
                            MoveTo(x, y) => MoveTo(x * scale + offset, y * scale),
                            LineTo(x, y) => LineTo(x * scale + offset, y * scale),
                            Close => Close,
                            _ => unreachable!(),
                        })
                        .collect::<Vec<_>>()
                };
                let source = transform(&source);
                let upstream = transform(&upstream);
                let fit = fit(
                    &source,
                    &upstream,
                    &Zone {
                        source_ref: 8.112 * f64::from(scale),
                        target: 8.0 * f64::from(scale),
                    },
                    Some(11.2 * f64::from(scale)),
                    16.0 * scale,
                )
                .unwrap();
                assert!(fit.applied);
                assert_eq!(fit.mark_translations, vec![(1, -f64::from(scale))]);
                let ranges = contour_ranges(&source).unwrap();
                let (a, b) = ranges[1];
                let before: Vec<_> = upstream[a..b].iter().flat_map(coords).collect();
                let after: Vec<_> = fit.commands[a..b].iter().flat_map(coords).collect();
                for ((x, y), (u, v)) in before.iter().zip(after) {
                    assert_eq!(*x, u);
                    assert_eq!(v - *y, -scale);
                }
                assert_eq!(
                    contour_min_max(&fit.commands[a..b]).0,
                    10.0 * f64::from(scale)
                );
            }
        }
    }

    #[test]
    fn multiple_mark_candidates_keep_the_whole_preceding_fit() {
        let mut source = body_source(8.156);
        source.extend(mark(10.08, 11.75, -0.3));
        source.extend(mark(10.08, 11.75, 0.9));
        let mut upstream = body_fitted(8.89);
        upstream.extend(mark(11.0, 12.0, -0.3));
        upstream.extend(mark(11.0, 12.0, 0.9));
        let result = fit(
            &source,
            &upstream,
            &Zone {
                source_ref: 8.112,
                target: 8.0,
            },
            Some(11.2),
            16.0,
        )
        .unwrap();
        assert!(!result.applied);
        assert_eq!(result.commands, upstream);
    }

    #[test]
    fn uncertified_curved_minimum_and_large_existing_gap_abstain() {
        for mark_source in [
            vec![
                MoveTo(0.5, 10.2),
                QuadTo(1.0, 9.8, 1.5, 10.2),
                LineTo(1.5, 11.75),
                LineTo(0.5, 11.75),
                Close,
            ],
            mark(10.08, 11.75, 0.0),
        ] {
            let mut source = body_source(8.156);
            source.extend(mark_source.clone());
            let mut upstream = body_fitted(8.89);
            if matches!(mark_source[1], QuadTo(..)) {
                upstream.extend(vec![
                    MoveTo(0.5, 11.2),
                    QuadTo(1.0, 10.8, 1.5, 11.2),
                    LineTo(1.5, 12.0),
                    LineTo(0.5, 12.0),
                    Close,
                ]);
            } else {
                upstream.extend(mark(15.0, 16.0, 0.0));
            }
            let result = fit(
                &source,
                &upstream,
                &Zone {
                    source_ref: 8.112,
                    target: 8.0,
                },
                Some(11.2),
                16.0,
            )
            .unwrap();
            assert!(!result.applied);
            assert_eq!(result.commands, upstream);
        }
    }

    #[test]
    fn unrelated_detached_contour_does_not_follow_the_body() {
        let mut source = body_source(8.156);
        source.extend(mark(10.08, 11.75, 5.0));
        let mut upstream = body_fitted(8.89);
        upstream.extend(mark(11.0, 12.0, 5.0));
        let result = fit(
            &source,
            &upstream,
            &Zone {
                source_ref: 8.112,
                target: 8.0,
            },
            Some(11.2),
            16.0,
        )
        .unwrap();
        assert!(result.applied);
        assert!(result.mark_translations.is_empty());
        let ranges = contour_ranges(&source).unwrap();
        let (a, b) = ranges[1];
        assert_eq!(result.commands[a..b], upstream[a..b]);
    }
    #[test]
    fn fitted_horizontal_ownership_must_match_source() {
        let mut source = body_source(8.156);
        source.extend(mark(10.08, 11.75, 0.0));
        let mut upstream = body_fitted(8.89);
        upstream.extend(mark(11.0, 12.0, 5.0));
        let result = fit(
            &source,
            &upstream,
            &Zone {
                source_ref: 8.112,
                target: 8.0,
            },
            Some(11.2),
            16.0,
        )
        .unwrap();
        assert!(!result.applied);
        assert_eq!(result.commands, upstream);
    }
}
