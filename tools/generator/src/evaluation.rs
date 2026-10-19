//! Mechanical checks and descriptive diagnostics, deliberately without an optical score.
//!
//! Hersch (1993), sections 5–6, separates continuous outline geometry, grid phase,
//! stem relations and continuity. Shamir (2003), section 3, describes feature and
//! dependency preservation. These motivate measuring geometry and raster topology
//! separately rather than treating ink quantity as quality. References are vendored
//! in `docs/references/papers/{1993-hersch,2003-shamir}/paper.md`.
//!
//! Project diagnostic hypotheses (not acceptance rules): corresponding command
//! coordinates describe motion, eight-connected ink/four-connected background
//! describe diagonal continuity and counters, and ±16 coverage units around the
//! configured threshold reveal local sensitivity. Tests exercise diagonal contacts,
//! counters and equal-ink shapes with different connectivity. These cannot identify
//! intentional counters, serifs, optical weight or the designer's intended shape.

use crate::{
    probe::{rasterize, FittedCommand},
    reference::{RasterPolicy, ReferenceRecord, ReferenceReport, PROFILE_GRAY_3BIT},
    Config,
};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, VecDeque};

#[derive(Debug, Serialize)]
pub struct Failure {
    pub report: String,
    pub codepoint: Option<u32>,
    pub invariant: String,
}

#[derive(Debug, Serialize)]
pub struct Evaluation {
    pub schema_version: u32,
    /// This means only that the mechanical contract passed, never optical acceptance.
    pub hard_invariants_pass: bool,
    pub hard_failures: Vec<Failure>,
    pub glyphs: Vec<GlyphDiagnostics>,
    pub limits: &'static str,
}

#[derive(Debug, Serialize)]
pub struct GlyphDiagnostics {
    pub codepoint: u32,
    pub source: RasterDiagnostics,
    pub upstream: RasterDiagnostics,
    pub candidate: RasterDiagnostics,
    pub source_to_upstream: Option<Motion>,
    pub source_to_candidate: Option<Motion>,
    pub upstream_to_candidate: Option<Motion>,
    pub source_command_correspondence: bool,
    pub candidate_outline_changed: bool,
    /// [detected, applied, unapplied]; coverage information, not a success score.
    pub candidate_diagonal_pairs: Option<[u32; 3]>,
}

#[derive(Debug, Serialize)]
pub struct Motion {
    pub coordinate_pairs: usize,
    pub maximum_px: f64,
    pub rms_px: f64,
}

#[derive(Debug, Serialize, PartialEq, Eq)]
pub struct Topology {
    pub ink_components_8: usize,
    pub enclosed_background_components_4: usize,
}

#[derive(Debug, Serialize)]
pub struct ThresholdSample {
    pub threshold: u8,
    /// Count is descriptive; either increasing or decreasing it can be appropriate.
    pub ink_pixels: usize,
    pub topology: Topology,
}

#[derive(Debug, Serialize)]
pub struct RasterDiagnostics {
    /// Delivered pixels, distinct from hypothetical thresholdings of raw coverage.
    pub delivered_ink_pixels: usize,
    pub delivered_topology: Topology,
    pub coverage_area_px: f64,
    /// Hypothetical binarizations of coverage, including for gray reports.
    pub threshold_samples: Vec<ThresholdSample>,
}

/// Evaluate reports for the same font/axes/size/profile/repertoire. Source must be
/// unhinted and upstream must be independently captured with extensions disabled.
/// Gray identity is a hard invariant of the current Mono fitting policies.
/// Failures are returned as data so a corpus run can finish all cases.
pub fn evaluate(
    source: &ReferenceReport,
    upstream: &ReferenceReport,
    candidate: &ReferenceReport,
) -> Evaluation {
    let mut failures = Vec::new();
    let mut push = |report: &str, codepoint: Option<u32>, invariant: &str| {
        failures.push(Failure {
            report: report.into(),
            codepoint,
            invariant: invariant.into(),
        });
    };
    if source.hinting_requested != "none"
        || source.extensions != "none"
        || source.fork
        || source.implementation != "upstream"
    {
        push("source", None, "independent unhinted source required");
    }
    if upstream.extensions != "none" || upstream.fork || upstream.implementation != "upstream" {
        push("upstream", None, "independent upstream baseline required");
    }
    for (name, report) in [("source", source), ("upstream", upstream)] {
        if report.advance_policy != crate::reference::AdvancePolicy::Linear
            || report
                .records
                .iter()
                .any(|record| record.side_bearing_deltas_26_6.is_some())
        {
            push(
                name,
                None,
                "independent rendering requires linear metrics without bearing correction",
            );
        }
        if report
            .records
            .iter()
            .any(|record| record.raster_policy != RasterPolicy::Coverage)
        {
            push(
                name,
                None,
                "independent rendering requires coverage raster policy",
            );
        }
    }
    let font_hints_candidate = candidate.extensions
        == crate::stem_fitting::EXTENSIONS_FONT_HINTS_FIRST
        && candidate.profile != PROFILE_GRAY_3BIT;
    let mono_width_candidate = candidate.extensions
        == crate::stem_fitting::EXTENSIONS_MONO_WIDTH_01
        && candidate.profile != PROFILE_GRAY_3BIT;
    if (font_hints_candidate || mono_width_candidate) && candidate.target != "mono" {
        push(
            "candidate",
            None,
            "Mono candidate must declare the upstream mono target",
        );
    }
    if font_hints_candidate && candidate.hinting_requested != "auto_fallback" {
        push(
            "candidate",
            None,
            "font-hints candidate requires the upstream fallback policy",
        );
    }
    for (name, report) in [("source", source), ("candidate", candidate)] {
        if report.source_sha256 != upstream.source_sha256
            || report.size_px != upstream.size_px
            || report.axes != upstream.axes
        {
            push(name, None, "font, size or variation identity changed");
        }
        let target_changed = report.profile != upstream.profile
            || report.draw_pedantic != upstream.draw_pedantic
            || report.zeno_version != upstream.zeno_version
            || {
                report.target != upstream.target
                    || report.smooth_mode != upstream.smooth_mode
                    || report.symmetric_rendering != upstream.symmetric_rendering
                    || report.preserve_linear_metrics != upstream.preserve_linear_metrics
            };
        if target_changed {
            push(name, None, "render profile or rasterizer policy changed");
        }
        if report.metrics != upstream.metrics
            || report.missing_codepoints != upstream.missing_codepoints
        {
            push(name, None, "layout metrics or missing repertoire changed");
        }
    }
    if candidate.hinting_requested != upstream.hinting_requested && !font_hints_candidate {
        push("candidate", None, "requested hinting policy changed");
    }
    if candidate.advance_policy == crate::reference::AdvancePolicy::Hinted
        && (candidate.target != "mono"
            || candidate.hinting_requested != "auto"
            || candidate.extensions == "none")
    {
        push(
            "candidate",
            None,
            "hinted advance policy requires enabled automatic mono fitting",
        );
    }
    let mut indexes = Vec::new();
    for (name, report) in [
        ("source", source),
        ("upstream", upstream),
        ("candidate", candidate),
    ] {
        let mut index = BTreeMap::new();
        for record in &report.records {
            if index.insert(record.codepoint, record).is_some() {
                push(name, Some(record.codepoint), "duplicate glyph record");
            }
            for invariant in validate_record(record) {
                push(name, Some(record.codepoint), invariant);
            }
            if record.target != report.target
                || (record.selected_engine != report.hinting_requested
                    && !(report.hinting_requested == "auto_fallback"
                        && matches!(record.selected_engine.as_str(), "auto" | "interpreter")))
                || record.smooth_mode != report.smooth_mode
                || record.symmetric_rendering != report.symmetric_rendering
                || record.preserve_linear_metrics != report.preserve_linear_metrics
                || record.draw_pedantic != report.draw_pedantic
                || record.zeno_version != report.zeno_version
            {
                push(
                    name,
                    Some(record.codepoint),
                    "record and report policy inconsistent",
                );
            }
        }
        indexes.push(index);
    }
    for (name, index) in [("source", &indexes[0]), ("candidate", &indexes[2])] {
        if !index.keys().eq(indexes[1].keys()) {
            push(name, None, "glyph repertoire changed");
        }
    }
    let mut glyphs = Vec::new();
    for (&codepoint, &baseline) in &indexes[1] {
        let (Some(&raw), Some(&fitted)) = (indexes[0].get(&codepoint), indexes[2].get(&codepoint))
        else {
            continue;
        };
        for (name, record) in [("source", raw), ("candidate", fitted)] {
            // The spacing experiment explicitly replaces advance identity with
            // equality to the actual scaler-returned advance. Linear, gray and
            // disabled paths retain their original independent identity contract.
            let expected_advance = if name == "candidate"
                && candidate.advance_policy == crate::reference::AdvancePolicy::Hinted
            {
                record
                    .hinted_advance_width
                    .filter(|advance| advance.is_finite())
                    .map(|advance| (advance * 64.0).round() as i32)
                    .unwrap_or(baseline.advance_26_6)
            } else {
                baseline.advance_26_6
            };
            if record.glyph_id != baseline.glyph_id || record.advance_26_6 != expected_advance {
                push(name, Some(codepoint), "glyph mapping or advance changed");
            }
            let target_fields_changed = record.target != baseline.target
                || record.smooth_mode != baseline.smooth_mode
                || record.symmetric_rendering != baseline.symmetric_rendering
                || record.preserve_linear_metrics != baseline.preserve_linear_metrics;
            if target_fields_changed
                || record.output_bits != baseline.output_bits
                || record.mono_threshold != baseline.mono_threshold
                || record.gray_gamma != baseline.gray_gamma
                || record.zeno_format != baseline.zeno_format
                || record.zeno_version != baseline.zeno_version
                || record.draw_pedantic != baseline.draw_pedantic
            {
                push(name, Some(codepoint), "glyph render policy changed");
            }
        }
        // The bounded 4x overlap Mono raster without horizontal correction
        // metadata is shared by both mono candidates.
        if font_hints_candidate || mono_width_candidate {
            let kind = if font_hints_candidate {
                "font-hints"
            } else {
                "mono-width"
            };
            if fitted.raster_policy != RasterPolicy::CoverageOverlap4xDropout
                || fitted.side_bearing_deltas_26_6.is_some()
                || fitted.diagonal_pairs.is_some()
            {
                push(
                    "candidate",
                    Some(codepoint),
                    &format!(
                        "{kind} candidate requires overlap 4x dropout without horizontal correction metadata"
                    ),
                );
            }
        }
        if (font_hints_candidate
            && !matches!(fitted.selected_engine.as_str(), "auto" | "interpreter"))
            || (!font_hints_candidate && fitted.selected_engine != baseline.selected_engine)
        {
            push(
                "candidate",
                Some(codepoint),
                "selected hinting engine changed",
            );
        }
        if candidate.profile == PROFILE_GRAY_3BIT
            && (fitted.fitted_commands != baseline.fitted_commands
                || fitted.coverage != baseline.coverage
                || fitted.pixels != baseline.pixels
                || placement(fitted) != placement(baseline))
        {
            push(
                "candidate",
                Some(codepoint),
                "mono-only iteration changed gray output",
            );
        }
        let source_to_candidate = motion(&raw.fitted_commands, &fitted.fitted_commands);
        glyphs.push(GlyphDiagnostics {
            codepoint,
            source: diagnostics(raw),
            upstream: diagnostics(baseline),
            candidate: diagnostics(fitted),
            source_to_upstream: motion(&raw.fitted_commands, &baseline.fitted_commands),
            source_command_correspondence: source_to_candidate.is_some(),
            source_to_candidate,
            upstream_to_candidate: motion(&baseline.fitted_commands, &fitted.fitted_commands),
            candidate_outline_changed: fitted.fitted_commands != baseline.fitted_commands,
            candidate_diagonal_pairs: fitted.diagonal_pairs,
        });
    }
    Evaluation {
        schema_version: 1,
        hard_invariants_pass: failures.is_empty(),
        hard_failures: failures,
        glyphs,
        limits: "Mechanical invariants and descriptive diagnostics only. Coordinate correspondence is not a shape-distance metric; topology cannot distinguish intentional components/counters/serifs from defects; threshold samples are local probes, not robustness proof. No ink-count preference or optical acceptance score. Designer intent and optical weight still require assessment in the web preview.",
    }
}

fn placement(record: &ReferenceRecord) -> (i32, i32, u32, u32) {
    (record.left, record.top, record.width, record.height)
}

fn coordinates(command: &FittedCommand) -> Vec<(f64, f64)> {
    let point = |x: f32, y: f32| (f64::from(x), f64::from(y));
    match *command {
        FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => vec![point(x, y)],
        FittedCommand::QuadTo(a, b, x, y) => vec![point(a, b), point(x, y)],
        FittedCommand::CurveTo(a, b, c, d, x, y) => vec![point(a, b), point(c, d), point(x, y)],
        FittedCommand::Close => vec![],
    }
}

fn motion(a: &[FittedCommand], b: &[FittedCommand]) -> Option<Motion> {
    if a.len() != b.len() {
        return None;
    }
    let mut count = 0;
    let mut sum = 0.0_f64;
    let mut maximum = 0.0_f64;
    for (a, b) in a.iter().zip(b) {
        if std::mem::discriminant(a) != std::mem::discriminant(b) {
            return None;
        }
        for ((x, y), (u, v)) in coordinates(a).into_iter().zip(coordinates(b)) {
            let squared = (x - u).powi(2) + (y - v).powi(2);
            if !squared.is_finite() {
                return None;
            }
            maximum = maximum.max(squared.sqrt());
            sum += squared;
            count += 1;
        }
    }
    Some(Motion {
        coordinate_pairs: count,
        maximum_px: maximum,
        rms_px: if count == 0 {
            0.0
        } else {
            (sum / count as f64).sqrt()
        },
    })
}

fn validate_record(record: &ReferenceRecord) -> Vec<&'static str> {
    let mut failures = Vec::new();
    // Each pinned phantom-point rounding residual is at most half a pixel;
    // the inherited positive-bearing guard can add at most one more pixel.
    if record.side_bearing_deltas_26_6.is_some_and(|deltas| {
        record.target != "mono"
            || record.selected_engine != "auto"
            || deltas.iter().any(|delta| i64::from(*delta).abs() > 96)
    }) {
        failures.push("invalid monochrome side bearing deltas");
    }
    if record
        .hinted_advance_width
        .is_some_and(|value| !value.is_finite())
        || record.hinted_lsb.is_some_and(|value| !value.is_finite())
    {
        failures.push("nonfinite fitted metrics");
    }
    let size = u64::from(record.width) * u64::from(record.height);
    if size > 4_194_304
        || size != record.pixels.len() as u64
        || size != record.coverage.len() as u64
    {
        failures.push("bitmap dimensions or buffer lengths invalid");
    }
    if !matches!(record.output_bits, 1 | 2 | 3 | 4 | 8)
        || record.mono_threshold == 0
        || !record.gray_gamma.is_finite()
        || record.gray_gamma <= 0.0
    {
        failures.push("raster quantization policy invalid");
        return failures;
    }
    let levels = (1_u16 << record.output_bits) - 1;
    if record.pixels.iter().any(|&p| u16::from(p) > levels) {
        failures.push("pixel level outside configured range");
    }
    if format!("{:x}", Sha256::digest(&record.coverage)) != record.coverage_sha256 {
        failures.push("coverage checksum inconsistent");
    }
    if let Some([detected, applied, unapplied]) = record.diagonal_pairs {
        if applied.checked_add(unapplied) != Some(detected) {
            failures.push("feature application accounting inconsistent");
        }
    }
    let mut open = false;
    let mut invalid = false;
    for command in &record.fitted_commands {
        invalid |= coordinates(command).iter().any(|&(x, y)| {
            !x.is_finite() || !y.is_finite() || x.abs() > 32768.0 || y.abs() > 32768.0
        });
        match command {
            FittedCommand::MoveTo(..) => {
                invalid |= open;
                open = true;
            }
            FittedCommand::Close => {
                invalid |= !open;
                open = false;
            }
            _ => invalid |= !open,
        }
    }
    if open || invalid {
        failures.push("outline coordinates or contour command structure invalid");
        return failures;
    }
    let config = Config {
        output_bits: record.output_bits,
        mono_threshold: record.mono_threshold,
        gray_gamma: record.gray_gamma,
        ..Config::default()
    };
    let reproduced = match record.raster_policy {
        RasterPolicy::Coverage => rasterize(&record.fitted_commands, &config),
        RasterPolicy::CoverageDropout if record.output_bits == 1 => {
            crate::dropout::rasterize(&record.fitted_commands, &config)
        }
        #[cfg(feature = "candidate")]
        RasterPolicy::CoverageOverlap4xDropout if record.output_bits == 1 => {
            crate::overlap::rasterize(&record.fitted_commands, &config)
        }
        _ => {
            return {
                failures.push("unsupported raster policy for this profile or build");
                failures
            }
        }
    };
    match reproduced {
        Ok(raster)
            if raster.pixels == record.pixels
                && raster.coverage == record.coverage
                && (raster.left, raster.top, raster.width, raster.height) == placement(record) => {}
        _ => failures.push("stored raster does not reproduce from fitted outline"),
    }
    failures
}

fn diagnostics(record: &ReferenceRecord) -> RasterDiagnostics {
    let mut thresholds = vec![
        record.mono_threshold.saturating_sub(16).max(1),
        record.mono_threshold.max(1),
        record.mono_threshold.saturating_add(16),
    ];
    thresholds.sort_unstable();
    thresholds.dedup();
    let valid_size = u64::from(record.width) * u64::from(record.height);
    let threshold_samples = if valid_size == record.coverage.len() as u64 && valid_size <= 4_194_304
    {
        thresholds
            .into_iter()
            .map(|threshold| {
                let bitmap: Vec<_> = record.coverage.iter().map(|&v| v >= threshold).collect();
                ThresholdSample {
                    threshold,
                    ink_pixels: bitmap.iter().filter(|&&v| v).count(),
                    topology: topology(&bitmap, record.width as usize, record.height as usize),
                }
            })
            .collect()
    } else {
        Vec::new()
    };
    RasterDiagnostics {
        delivered_ink_pixels: record.pixels.iter().filter(|&&v| v != 0).count(),
        delivered_topology: if valid_size == record.pixels.len() as u64 && valid_size <= 4_194_304 {
            topology(
                &record.pixels.iter().map(|&v| v != 0).collect::<Vec<_>>(),
                record.width as usize,
                record.height as usize,
            )
        } else {
            topology(&[], 0, 0)
        },
        coverage_area_px: record.coverage.iter().map(|&v| f64::from(v) / 255.0).sum(),
        threshold_samples,
    }
}

fn topology(bitmap: &[bool], width: usize, height: usize) -> Topology {
    // Complementary adjacency avoids calling a diagonal ink contact both a bridge
    // and a background crossing. Enclosed background is measured against the
    // actual bitmap boundary, equivalent to a surrounding white frame.
    let mut seen = vec![false; bitmap.len()];
    let mut ink = 0;
    let mut holes = 0;
    for start in 0..bitmap.len() {
        if seen[start] {
            continue;
        }
        let foreground = bitmap[start];
        let mut boundary = false;
        let mut queue = VecDeque::from([start]);
        seen[start] = true;
        while let Some(index) = queue.pop_front() {
            let (x, y) = (index % width, index / width);
            boundary |= x == 0 || y == 0 || x + 1 == width || y + 1 == height;
            for dy in -1_isize..=1 {
                for dx in -1_isize..=1 {
                    if (dx == 0 && dy == 0) || (!foreground && dx != 0 && dy != 0) {
                        continue;
                    }
                    let (nx, ny) = (x as isize + dx, y as isize + dy);
                    if nx < 0 || ny < 0 || nx as usize >= width || ny as usize >= height {
                        continue;
                    }
                    let next = ny as usize * width + nx as usize;
                    if !seen[next] && bitmap[next] == foreground {
                        seen[next] = true;
                        queue.push_back(next);
                    }
                }
            }
        }
        if foreground {
            ink += 1;
        } else if !boundary {
            holes += 1;
        }
    }
    Topology {
        ink_components_8: ink,
        enclosed_background_components_4: holes,
    }
}
