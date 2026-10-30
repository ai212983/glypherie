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
use std::collections::BTreeMap;

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

struct CandidateKind {
    selective_candidate: bool,
    source_width_candidate: bool,
    font_hints_candidate: bool,
    mono_width_candidate: bool,
}

fn check_report_identity(
    source: &ReferenceReport,
    upstream: &ReferenceReport,
    candidate: &ReferenceReport,
    push: &mut impl FnMut(&str, Option<u32>, &str),
) -> CandidateKind {
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
    let selective_candidate =
        candidate.extensions == crate::stem_fitting::EXTENSIONS_FONT_HINTS_AUTO;
    let source_width_candidate = candidate.extensions
        == crate::stem_fitting::EXTENSIONS_SOURCE_WIDTH_01
        || selective_candidate;
    let font_hints_candidate = (candidate.extensions
        == crate::stem_fitting::EXTENSIONS_FONT_HINTS_FIRST
        || source_width_candidate)
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
    CandidateKind {
        selective_candidate,
        source_width_candidate,
        font_hints_candidate,
        mono_width_candidate,
    }
}

struct ReportRecords<'a> {
    source: BTreeMap<u32, &'a ReferenceRecord>,
    upstream: BTreeMap<u32, &'a ReferenceRecord>,
    candidate: BTreeMap<u32, &'a ReferenceRecord>,
}

fn index_records<'a>(
    name: &str,
    report: &'a ReferenceReport,
    selective_candidate: bool,
    push: &mut impl FnMut(&str, Option<u32>, &str),
) -> BTreeMap<u32, &'a ReferenceRecord> {
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
                    && (matches!(record.selected_engine.as_str(), "auto" | "interpreter")
                        || (name == "candidate"
                            && selective_candidate
                            && record.selective_fitting.is_some()))))
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
    index
}

/// Emits per-glyph failures in invariant order before producing diagnostics.
struct GlyphComparison<'a> {
    codepoint: u32,
    source: &'a ReferenceRecord,
    upstream: &'a ReferenceRecord,
    candidate: &'a ReferenceRecord,
    candidate_report: &'a ReferenceReport,
    policy: &'a CandidateKind,
}

impl GlyphComparison<'_> {
    fn compare(&self, push: &mut impl FnMut(&str, Option<u32>, &str)) -> GlyphDiagnostics {
        for (name, record) in [("source", self.source), ("candidate", self.candidate)] {
            self.check_baseline_identity(name, record, push);
        }
        self.check_candidate_policy(push);
        self.check_source_outline(push);
        self.check_width_input(push);
        self.check_top_alignment_input(push);
        self.check_selective_input(push);
        self.check_engine(push);
        self.check_gray_identity(push);
        glyph_diagnostics(self.codepoint, self.source, self.upstream, self.candidate)
    }

    fn check_baseline_identity(
        &self,
        name: &str,
        record: &ReferenceRecord,
        push: &mut impl FnMut(&str, Option<u32>, &str),
    ) {
        // The spacing experiment explicitly replaces advance identity with
        // equality to the actual scaler-returned advance. Linear, gray and
        // disabled paths retain their original independent identity contract.
        let expected_advance = if name == "candidate"
            && self.candidate_report.advance_policy == crate::reference::AdvancePolicy::Hinted
        {
            record
                .hinted_advance_width
                .filter(|advance| advance.is_finite())
                .map(|advance| (advance * 64.0).round() as i32)
                .unwrap_or(self.upstream.advance_26_6)
        } else {
            self.upstream.advance_26_6
        };
        if record.glyph_id != self.upstream.glyph_id || record.advance_26_6 != expected_advance {
            push(
                name,
                Some(self.codepoint),
                "glyph mapping or advance changed",
            );
        }
        let target_fields_changed = record.target != self.upstream.target
            || record.smooth_mode != self.upstream.smooth_mode
            || record.symmetric_rendering != self.upstream.symmetric_rendering
            || record.preserve_linear_metrics != self.upstream.preserve_linear_metrics;
        if target_fields_changed
            || record.output_bits != self.upstream.output_bits
            || record.mono_threshold != self.upstream.mono_threshold
            || record.gray_gamma != self.upstream.gray_gamma
            || record.zeno_format != self.upstream.zeno_format
            || record.zeno_version != self.upstream.zeno_version
            || record.draw_pedantic != self.upstream.draw_pedantic
        {
            push(name, Some(self.codepoint), "glyph render policy changed");
        }
    }

    fn check_candidate_policy(&self, push: &mut impl FnMut(&str, Option<u32>, &str)) {
        if self.policy.font_hints_candidate || self.policy.mono_width_candidate {
            let kind = if self.policy.font_hints_candidate {
                "font-hints"
            } else {
                "mono-width"
            };
            let residuals_allowed = residuals_allowed(self.candidate);
            // Fitting and raster stages are independent: the Coverage
            // capture of the same fitting carries the same residuals.
            if !matches!(
                self.candidate.raster_policy,
                RasterPolicy::FreeTypeMono
                    | RasterPolicy::FreeTypeMonoTerminals
                    | RasterPolicy::Coverage
            ) || (self.candidate.side_bearing_deltas_26_6.is_some() && !residuals_allowed)
                || self.candidate.diagonal_pairs.is_some()
            {
                push(
                    "candidate",
                    Some(self.codepoint),
                    &format!(
                        "{kind} candidate requires FreeType mono without horizontal correction metadata"
                    ),
                );
            }
        }
    }

    fn check_source_outline(&self, push: &mut impl FnMut(&str, Option<u32>, &str)) {
        if let Some(commands) = &self.candidate.source_commands {
            if (!matches!(
                self.candidate.raster_policy,
                RasterPolicy::FreeTypeMono | RasterPolicy::FreeTypeMonoTerminals
            ) || (self.candidate.raster_policy != RasterPolicy::FreeTypeMonoTerminals
                && self.candidate.width_fitting.is_none()
                && self.candidate.selective_fitting.is_none()
                && self.candidate.diagonal_fitting.is_none()
                && self.candidate.top_alignment.is_none()))
                || *commands != self.source.fitted_commands
            {
                push(
                    "candidate",
                    Some(self.codepoint),
                    "source outline identity changed",
                );
            }
        } else if self.candidate.raster_policy == RasterPolicy::FreeTypeMonoTerminals {
            push(
                "candidate",
                Some(self.codepoint),
                "terminal source outline missing",
            );
        }
    }

    fn check_width_input(&self, push: &mut impl FnMut(&str, Option<u32>, &str)) {
        if let Some(width) = &self.candidate.width_fitting {
            if !self.policy.source_width_candidate
                || width.size_px != self.candidate_report.size_px
                || (self.candidate.selected_engine == self.upstream.selected_engine
                    && width.upstream_commands != self.upstream.fitted_commands)
            {
                push(
                    "candidate",
                    Some(self.codepoint),
                    "width fitting input identity changed",
                );
            }
        }
    }

    fn check_top_alignment_input(&self, push: &mut impl FnMut(&str, Option<u32>, &str)) {
        if let Some(top) = &self.candidate.top_alignment {
            if top.size_px != self.candidate_report.size_px
                || (self.candidate.width_fitting.is_none()
                    && top.upstream_commands != self.upstream.fitted_commands)
            {
                push(
                    "candidate",
                    Some(self.codepoint),
                    "top alignment input identity changed",
                );
            }
        }
    }

    fn check_selective_input(&self, push: &mut impl FnMut(&str, Option<u32>, &str)) {
        if let Some(selective) = &self.candidate.selective_fitting {
            if !self.policy.selective_candidate
                || selective.automatic_commands != self.upstream.fitted_commands
            {
                push(
                    "candidate",
                    Some(self.codepoint),
                    "selective automatic input identity changed",
                );
            }
        }
    }

    fn check_engine(&self, push: &mut impl FnMut(&str, Option<u32>, &str)) {
        if (self.policy.font_hints_candidate
            && !matches!(
                self.candidate.selected_engine.as_str(),
                "auto" | "interpreter"
            )
            && !(self.policy.selective_candidate && self.candidate.selective_fitting.is_some()))
            || (!self.policy.font_hints_candidate
                && self.candidate.selected_engine != self.upstream.selected_engine)
        {
            push(
                "candidate",
                Some(self.codepoint),
                "selected hinting engine changed",
            );
        }
    }

    fn check_gray_identity(&self, push: &mut impl FnMut(&str, Option<u32>, &str)) {
        if self.candidate_report.profile == PROFILE_GRAY_3BIT
            && (self.candidate.fitted_commands != self.upstream.fitted_commands
                || self.candidate.coverage != self.upstream.coverage
                || self.candidate.pixels != self.upstream.pixels
                || placement(self.candidate) != placement(self.upstream))
        {
            push(
                "candidate",
                Some(self.codepoint),
                "mono-only iteration changed gray output",
            );
        }
    }
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
    let policy = check_report_identity(source, upstream, candidate, &mut push);
    let records = ReportRecords {
        source: index_records("source", source, policy.selective_candidate, &mut push),
        upstream: index_records("upstream", upstream, policy.selective_candidate, &mut push),
        candidate: index_records(
            "candidate",
            candidate,
            policy.selective_candidate,
            &mut push,
        ),
    };
    for (name, index) in [
        ("source", &records.source),
        ("candidate", &records.candidate),
    ] {
        if !index.keys().eq(records.upstream.keys()) {
            push(name, None, "glyph repertoire changed");
        }
    }
    let mut glyphs = Vec::new();
    for (&codepoint, &upstream_record) in &records.upstream {
        let (Some(&source_record), Some(&candidate_record)) = (
            records.source.get(&codepoint),
            records.candidate.get(&codepoint),
        ) else {
            continue;
        };
        glyphs.push(
            GlyphComparison {
                codepoint,
                source: source_record,
                upstream: upstream_record,
                candidate: candidate_record,
                candidate_report: candidate,
                policy: &policy,
            }
            .compare(&mut push),
        );
    }
    Evaluation {
        schema_version: 1,
        hard_invariants_pass: failures.is_empty(),
        hard_failures: failures,
        glyphs,
        limits: "Mechanical invariants and descriptive diagnostics only. Coordinate correspondence is not a shape-distance metric; topology cannot distinguish intentional components/counters/serifs from defects; threshold samples describe hypothetical AA conversion (not center-fill output), not robustness proof. No ink-count preference or optical acceptance score. Designer intent and optical weight still require assessment in the web preview.",
    }
}

fn glyph_diagnostics(
    codepoint: u32,
    source: &ReferenceRecord,
    upstream: &ReferenceRecord,
    candidate: &ReferenceRecord,
) -> GlyphDiagnostics {
    let source_to_candidate = motion(&source.fitted_commands, &candidate.fitted_commands);
    GlyphDiagnostics {
        codepoint,
        source: diagnostics(source),
        upstream: diagnostics(upstream),
        candidate: diagnostics(candidate),
        source_to_upstream: motion(&source.fitted_commands, &upstream.fitted_commands),
        source_command_correspondence: source_to_candidate.is_some(),
        source_to_candidate,
        upstream_to_candidate: motion(&upstream.fitted_commands, &candidate.fitted_commands),
        candidate_outline_changed: candidate.fitted_commands != upstream.fitted_commands,
        candidate_diagonal_pairs: candidate.diagonal_pairs,
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

fn outline_valid(commands: &[FittedCommand]) -> bool {
    let mut open = false;
    let mut invalid = false;
    for command in commands {
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
    !(open || invalid)
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

#[cfg(feature = "candidate")]
enum DiagonalReplay {
    Consistent,
    Flaw(&'static str),
    Abort(&'static str),
}

#[cfg(feature = "candidate")]
fn validate_diagonal_replay(record: &ReferenceRecord) -> DiagonalReplay {
    let Some(diagonal) = &record.diagonal_fitting else {
        return DiagonalReplay::Consistent;
    };
    // Independent replay from captured inputs: the stored reference
    // must deserialize and the re-fit must reproduce the applied
    // reason and exact commands.
    if !matches!(
        record.raster_policy,
        RasterPolicy::FreeTypeMono | RasterPolicy::FreeTypeMonoTerminals
    ) || diagonal.upstream_commands.is_empty()
        || diagonal.reason.is_empty()
    {
        return DiagonalReplay::Flaw("diagonal capture inconsistent");
    }
    let Some(source) = &record.source_commands else {
        return DiagonalReplay::Abort("diagonal source outline missing");
    };
    let reference: crate::diagonal_fitting::Reference =
        match serde_json::from_value(diagonal.reference.clone()) {
            Ok(reference) => reference,
            Err(_) => {
                return DiagonalReplay::Abort("diagonal reference does not deserialize");
            }
        };
    let replay = if matches!(
        diagonal.model.as_str(),
        "diagonal-shape-04" | "diagonal-shape-05" | "diagonal-shape-06"
    ) {
        let raw: Option<crate::fitting_source::SourceOutline> = match diagonal
            .raw_source
            .clone()
            .map(serde_json::from_value)
            .transpose()
        {
            Ok(raw) => raw,
            Err(_) => {
                return DiagonalReplay::Abort("diagonal raw source does not deserialize");
            }
        };
        if diagonal.model == "diagonal-shape-05" {
            if diagonal.source_shape.is_some() {
                return DiagonalReplay::Flaw("legacy capture carries new source-shape provenance");
            }
        }
        if matches!(
            diagonal.model.as_str(),
            "diagonal-shape-05" | "diagonal-shape-06"
        ) && diagonal.reason.starts_with("coupled:")
            && record.raster_policy != RasterPolicy::FreeTypeMono
        {
            return DiagonalReplay::Flaw("coupled fit requires recorded FreeType mono policy");
        }
        if diagonal.model == "diagonal-shape-06" {
            // The model identifies the producing sequence. Shape provenance
            // travels only with its own stage; other stages retain their
            // axis and raster-policy requirements.
            if diagonal.upright_stem.is_some() {
                return DiagonalReplay::Flaw("new source capture under legacy provenance field");
            }
            if diagonal.reason.starts_with("source-shape:") {
                let aligned = diagonal.source_shape.as_ref().is_some_and(|shape| {
                    shape
                        .get("model")
                        .is_some_and(|model| model == "upright-source-shape-01")
                        && shape
                            .get("kernel")
                            .is_some_and(|kernel| kernel == "coupled-shape-auto-01")
                });
                if !aligned {
                    return DiagonalReplay::Flaw("new source capture without kernel provenance");
                }
                if !matches!(
                    record.raster_policy,
                    RasterPolicy::FreeTypeMono | RasterPolicy::FreeTypeMonoTerminals
                ) {
                    return DiagonalReplay::Flaw("source-shape fit requires recorded mono policy");
                }
                if diagonal.native_axes != [false, false] {
                    return DiagonalReplay::Flaw("source-shape fit requires automatic axes");
                }
            } else if diagonal.source_shape.is_some() {
                return DiagonalReplay::Flaw("new non-shape capture carries shape provenance");
            }
        }
        let fit = if diagonal.model == "diagonal-shape-04" {
            crate::diagonal_fitting::approved::fit_pre_coupled
        } else if diagonal.model == "diagonal-shape-05" {
            crate::diagonal_fitting::approved::fit_v05
        } else {
            crate::diagonal_fitting::approved::fit
        };
        fit(
            raw.as_ref(),
            source,
            &diagonal.upstream_commands,
            diagonal.size_px,
            &reference,
            diagonal.native_axes,
        )
    } else {
        crate::diagonal_fitting::fit(
            source,
            &diagonal.upstream_commands,
            diagonal.size_px,
            &reference,
            diagonal.native_axes,
        )
    };
    match replay {
        Ok(fit)
            if fit.applied
                && fit.reason == diagonal.reason
                && fit.commands == record.fitted_commands =>
        {
            DiagonalReplay::Consistent
        }
        _ => DiagonalReplay::Flaw("diagonal fitting does not reproduce from captured inputs"),
    }
}

// Bearing corrections are allowed only where the automatic fitter
// owns the X axis on the Mono target: `auto` records, and selective
// records whose capture proves X stayed automatic. Native X,
// fallback, Gray and reference records must carry none.
fn residuals_allowed(record: &ReferenceRecord) -> bool {
    record.target == "mono"
        && match record.selected_engine.as_str() {
            "auto" => true,
            "auto_x_native_y" | "auto_with_native_scan" => record
                .selective_fitting
                .as_ref()
                .is_some_and(|selective| !selective.native_axes[0]),
            _ => false,
        }
}

fn metric_failures(record: &ReferenceRecord) -> Vec<&'static str> {
    let mut failures = Vec::new();
    // Each pinned phantom-point rounding residual is at most half a pixel;
    // the inherited positive-bearing guard can add at most one more pixel.
    if record.side_bearing_deltas_26_6.is_some_and(|deltas| {
        !residuals_allowed(record) || deltas.iter().any(|delta| i64::from(*delta).abs() > 96)
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
    failures
}

fn quantization_config(record: &ReferenceRecord) -> Option<Config> {
    if !matches!(record.output_bits, 1 | 2 | 3 | 4 | 8)
        || record.mono_threshold == 0
        || !record.gray_gamma.is_finite()
        || record.gray_gamma <= 0.0
    {
        return None;
    }
    Some(Config {
        output_bits: record.output_bits,
        mono_threshold: record.mono_threshold,
        gray_gamma: record.gray_gamma,
        mono_raster: record.mono_raster.unwrap_or_default(),
        ..Config::default()
    })
}

#[cfg(feature = "candidate")]
fn selective_replay_valid(
    record: &ReferenceRecord,
    selective: &crate::reference::SelectiveFittingCapture,
) -> bool {
    let axes = selective.native_axes;
    let engine = match axes {
        [false, true] => "auto_x_native_y",
        [true, false] => "native_x_auto_y",
        [false, false] => "auto_with_native_scan",
        _ => "invalid",
    };
    let valid_source = record.source_commands.as_ref().is_some_and(|source| {
        axes == [false; 2]
            || crate::selective_fitting::unowned_unchanged(source, &selective.native_commands, axes)
    });
    let combined = if axes == [false; 2] {
        Some(selective.automatic_commands.clone())
    } else {
        crate::selective_fitting::combine(
            &selective.native_commands,
            &selective.automatic_commands,
            axes,
        )
    };
    // Post-diagonal records reproduce the pre-diagonal outline.
    let expected = record
        .diagonal_fitting
        .as_ref()
        .map(|diagonal| &diagonal.upstream_commands)
        .unwrap_or(&record.fitted_commands);
    !(record.selected_engine != engine
        || engine == "invalid"
        || !valid_source
        || record.raster_policy != RasterPolicy::FreeTypeMono
        || record
            .font_scan
            .as_ref()
            .is_some_and(|s| s.hinting_axes != axes)
        || combined.as_ref() != Some(expected))
}

fn reproduce_raster(record: &ReferenceRecord, config: &Config, failures: &mut Vec<&'static str>) {
    if record.mono_raster.is_some()
        && !matches!(
            record.raster_policy,
            RasterPolicy::FreeTypeMono | RasterPolicy::FreeTypeMonoTerminals
        )
    {
        failures.push("monochrome scan settings on a coverage raster");
    }
    if record.font_scan.is_some()
        && (record.raster_policy != RasterPolicy::FreeTypeMono
            || !config.mono_raster.font_instructions
            || (record.selected_engine != "interpreter" && record.selective_fitting.is_none()))
    {
        failures.push("font scan state on an incompatible render policy");
    }
    let reproduced = match record.raster_policy {
        RasterPolicy::Coverage => rasterize(&record.fitted_commands, config),
        RasterPolicy::CoverageDropout if record.output_bits == 1 => {
            crate::dropout::rasterize(&record.fitted_commands, config)
        }
        #[cfg(feature = "candidate")]
        RasterPolicy::FreeTypeMono if record.output_bits == 1 => {
            if record.mono_rasterizer != Some(crate::reference::MonoRasterizer::current()) {
                failures.push("monochrome scanner identity inconsistent");
            }
            if record.mono_raster.is_none() {
                failures.push("monochrome scan settings missing");
            }
            crate::mono::rasterize_with_scan_state(
                &record.fitted_commands,
                config,
                record.font_scan.as_ref(),
            )
        }
        #[cfg(feature = "candidate")]
        RasterPolicy::FreeTypeMonoTerminals if record.output_bits == 1 => {
            if record.mono_rasterizer != Some(crate::reference::MonoRasterizer::current())
                || record.mono_raster.is_none()
                || record.selected_engine != "auto"
                || !config.mono_raster.include_stubs
                || config.mono_raster.dropout != crate::MonoDropoutMode::Smart
            {
                failures.push("terminal scan settings or identity inconsistent");
            }
            let Some(source) = &record.source_commands else {
                failures.push("terminal source outline missing");
                return;
            };
            crate::candidate::rasterize_terminals(source, &record.fitted_commands, config)
        }
        #[cfg(feature = "candidate")]
        RasterPolicy::CoverageOverlap4xDropout if record.output_bits == 1 => {
            crate::overlap::rasterize(&record.fitted_commands, config)
        }
        _ => {
            failures.push("unsupported raster policy for this profile or build");
            return;
        }
    };
    match reproduced {
        Ok(raster)
            if raster.pixels == record.pixels
                && raster.coverage == record.coverage
                && (raster.left, raster.top, raster.width, raster.height) == placement(record) => {}
        _ => failures.push("stored raster does not reproduce from fitted outline"),
    }
}

fn validate_record(record: &ReferenceRecord) -> Vec<&'static str> {
    let mut failures = metric_failures(record);
    let size = u64::from(record.width) * u64::from(record.height);
    if size > 4_194_304
        || size != record.pixels.len() as u64
        || size != record.coverage.len() as u64
    {
        failures.push("bitmap dimensions or buffer lengths invalid");
    }
    let Some(config) = quantization_config(record) else {
        failures.push("raster quantization policy invalid");
        return failures;
    };
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
    if !outline_valid(&record.fitted_commands) {
        failures.push("outline coordinates or contour command structure invalid");
        return failures;
    }
    if record.source_commands.is_some()
        && record.raster_policy != RasterPolicy::FreeTypeMonoTerminals
        && !(record.raster_policy == RasterPolicy::FreeTypeMono
            && (record.width_fitting.is_some()
                || record.selective_fitting.is_some()
                || record.diagonal_fitting.is_some()
                || record.top_alignment.is_some()))
    {
        failures.push("source outline on an incompatible raster policy");
    }
    #[cfg(feature = "candidate")]
    match validate_diagonal_replay(record) {
        DiagonalReplay::Consistent => {}
        DiagonalReplay::Flaw(failure) => failures.push(failure),
        DiagonalReplay::Abort(failure) => {
            failures.push(failure);
            return failures;
        }
    }
    #[cfg(feature = "candidate")]
    if let Some(selective) = &record.selective_fitting {
        if !selective_replay_valid(record, selective) {
            failures.push("selective fitting does not reproduce from captured inputs");
        }
    }
    #[cfg(feature = "candidate")]
    if let Some(width) = &record.width_fitting {
        if record.selected_engine != "auto"
            || !matches!(
                record.raster_policy,
                RasterPolicy::FreeTypeMono | RasterPolicy::FreeTypeMonoTerminals
            )
        {
            failures.push("width fitting on an incompatible render policy");
        }
        let Some(source) = &record.source_commands else {
            failures.push("width source outline missing");
            return failures;
        };
        let expected: &[crate::probe::FittedCommand] = record
            .top_alignment
            .as_ref()
            .map(|top| top.upstream_commands.as_slice())
            .or_else(|| {
                record
                    .diagonal_fitting
                    .as_ref()
                    .map(|diagonal| diagonal.upstream_commands.as_slice())
            })
            .unwrap_or(record.fitted_commands.as_slice());
        match crate::source_width::fit(source, &width.upstream_commands, width.size_px) {
            Ok(fit) if fit.applied && fit.commands == expected => {}
            _ => failures.push("width fitting does not reproduce from captured inputs"),
        }
    }
    #[cfg(feature = "candidate")]
    if let Some(top) = &record.top_alignment {
        if record.selected_engine != "auto"
            || !matches!(
                record.raster_policy,
                RasterPolicy::FreeTypeMono | RasterPolicy::FreeTypeMonoTerminals
            )
            || top.model != crate::top_alignment::MODEL
        {
            failures.push("top alignment on an incompatible render policy");
        }
        let Some(source) = &record.source_commands else {
            failures.push("top alignment source outline missing");
            return failures;
        };
        let expected: &[crate::probe::FittedCommand] = record
            .diagonal_fitting
            .as_ref()
            .map(|diagonal| diagonal.upstream_commands.as_slice())
            .unwrap_or(record.fitted_commands.as_slice());
        let zone = crate::top_alignment::Zone {
            source_ref: top.source_ref_px,
            target: top.target_px,
        };
        match crate::top_alignment::fit(
            source,
            &top.upstream_commands,
            &zone,
            top.cap_height_px,
            top.size_px,
        ) {
            Ok(fit)
                if fit.applied
                    && fit.commands == expected
                    && fit.contours == top.contours
                    && fit.excess_px == top.excess_px
                    && fit.mark_translations == top.mark_translations => {}
            _ => failures.push("top alignment does not reproduce from captured inputs"),
        }
    }
    reproduce_raster(record, &config, &mut failures);
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
    let counts = crate::bitmap_topology::Bitmap::new(width, height, bitmap)
        .expect("valid bitmap dimensions")
        .counts();
    Topology {
        ink_components_8: counts[0],
        enclosed_background_components_4: counts[1],
    }
}

#[cfg(test)]
#[path = "evaluation/topology_tests.rs"]
mod topology_tests;
