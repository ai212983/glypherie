//! Working Mono candidate: registry Skrifa fitting with explicit source-width policy.
//!
//! The default uses Target::Mono with upstream engine selection
//! (Engine::AutoFallback: font-provided hints when available, otherwise the
//! upstream autohinter), except that TrueType fonts verified to carry no
//! hint programs use the upstream autohinter directly. The explicit
//! automatic control forces Engine::Auto. This follows Skrifa's documented
//! FreeType engine selection. SourceRelative adds the sourced straight-width
//! correction before scan conversion; historical fitting policies stay upstream.
//! See https://docs.rs/skrifa/0.48.0/skrifa/outline/enum.Engine.html.
//! Fitting is upstream; candidate Mono scan conversion uses pinned FreeType.
//! Gray retains its existing upstream Normal automatic fitting.
use crate::{
    fail,
    layout_spacing::finalize_bitmap_metrics,
    mono_spacing::font_spacing_properties,
    reference::{
        CapturePolicy, CaptureSession, ReferenceReport, ReferenceRequest, PROFILE_GRAY_3BIT,
        PROFILE_MONO_1BIT,
    },
    stem_fitting::{
        StemFittingStrategy, EXTENSIONS_FONT_HINTS_AUTO, EXTENSIONS_FONT_HINTS_FIRST,
        EXTENSIONS_MONO_WIDTH_01, EXTENSIONS_SOURCE_WIDTH_01,
    },
    Config, Error, GeneratedFont, Glyph, Hinting, KerningPair,
};
use sha2::Digest;
use skrifa::outline::{SmoothMode, Target};
use std::collections::HashMap;

pub fn render(data: &[u8], request: &ReferenceRequest) -> Result<ReferenceReport, Error> {
    render_with_rasterization(data, request, crate::renderer::Rasterization::FreeTypeMono)
}

/// Frozen width-only diagonal reference donors; never the request text.
const DIAGONAL_DONORS: &str = "itflInhkyxzvAVW";

/// Explicit-pipeline capture with optional reviewed stroke
/// fitting. `diagonal_fitting=false` is identity with
/// `render_with_rasterization`; export and preview both route here once.
pub fn render_with_pipeline(
    data: &[u8],
    request: &ReferenceRequest,
    pipeline: crate::renderer::RenderPipeline,
) -> Result<ReferenceReport, Error> {
    render_with_pipeline_in_session(&CaptureSession::new(data), request, pipeline)
}

pub(crate) fn render_with_pipeline_in_session(
    session: &CaptureSession<'_>,
    request: &ReferenceRequest,
    pipeline: crate::renderer::RenderPipeline,
) -> Result<ReferenceReport, Error> {
    pipeline.validate(&request.settings)?;
    // The extensions select the upstream reference; a mismatch would mix
    // references, so reject before any capture rather than normalizing.
    if request.extensions != StemFittingStrategy::extension(Some(pipeline.fitting)) {
        return Err(fail("pipeline fitting does not match request extensions"));
    }
    let mut report =
        render_with_rasterization_in_session(session, request, pipeline.rasterization)?;
    if !pipeline.diagonal_fitting {
        return Ok(report);
    }
    apply_diagonal_fitting(session, request, &pipeline, &mut report)?;
    Ok(report)
}

// Reviewed stroke fitting sequence over the frozen donor reference.
// Invariant: removal-free post-fit only; missing donors, unsupported
// geometry or core abstention keep the upstream outline, metrics and
// layout bit-identical, never a new render failure.
fn apply_diagonal_fitting(
    session: &CaptureSession<'_>,
    request: &ReferenceRequest,
    pipeline: &crate::renderer::RenderPipeline,
    report: &mut ReferenceReport,
) -> Result<(), Error> {
    let data = session.data;
    if !matches!(
        pipeline.fitting,
        StemFittingStrategy::FontHintsAuto | StemFittingStrategy::UpstreamMono
    ) || !matches!(
        pipeline.rasterization,
        crate::renderer::Rasterization::FreeTypeMono
            | crate::renderer::Rasterization::FreeTypeMonoTerminals
    ) || request.profile != PROFILE_MONO_1BIT
        || request.settings.output_bits != 1
    {
        return Err(fail(
            "diagonal fitting requires 1-bit FreeTypeMono/Terminals with FontHintsAuto or UpstreamMono",
        ));
    }
    let mut source_request = request.clone();
    source_request.extensions = "none".into();
    source_request.settings.hinting = Hinting::None;
    source_request.settings.mono_raster = Default::default();
    let Ok(source) = session.source(&source_request) else {
        return Ok(());
    };
    let Some(donors) = diagonal_reference(session, request, pipeline) else {
        return Ok(());
    };
    let Ok(donors_value) = serde_json::to_value(&donors) else {
        return Ok(());
    };
    let size_px = f64::from(request.settings.size_px);
    let mut applied_any = false;
    for record in report.records.iter_mut() {
        let Some(raw) = source.records.iter().find(|candidate| {
            candidate.codepoint == record.codepoint && candidate.glyph_id == record.glyph_id
        }) else {
            continue;
        };
        let native_axes = record
            .selective_fitting
            .as_ref()
            .map(|capture| capture.native_axes)
            .unwrap_or(if record.selected_engine == "auto" {
                [false, false]
            } else {
                [true, true]
            });
        let raw_features =
            crate::fitting_source::draw(data, &request.settings, record.glyph_id).ok();
        let compute = || {
            crate::diagonal_fitting::reuse::fit(
                raw_features.as_ref(),
                &raw.fitted_commands,
                &record.fitted_commands,
                size_px,
                &donors,
                native_axes,
            )
        };
        let fit = match session.diagonal_fits {
            Some(cache) => cache.borrow_mut().fit(
                raw_features.as_ref(),
                &raw.fitted_commands,
                &record.fitted_commands,
                size_px,
                &donors,
                native_axes,
            ),
            None => compute(),
        };
        let Ok(fit) = fit else {
            continue;
        };
        if !fit.applied {
            continue;
        }
        // Post-fit raster follows the record's own policy:
        // selective-native records stay on FreeTypeMono with their executed
        // scan state; terminals reuse the certified kernel. Other policies
        // keep upstream. Advances and hinted metrics stay upstream.
        // Per-record scan authority: the record's captured settings govern
        // its raster, falling back to the request only when absent.
        let mut scan_config = request.settings.clone();
        scan_config.mono_raster = record.mono_raster.unwrap_or(request.settings.mono_raster);
        let raster = match record.raster_policy {
            crate::reference::RasterPolicy::FreeTypeMono => crate::mono::rasterize_with_scan_state(
                &fit.commands,
                &scan_config,
                record.font_scan.as_ref(),
            ),
            crate::reference::RasterPolicy::FreeTypeMonoTerminals => {
                rasterize_terminals(&raw.fitted_commands, &fit.commands, &scan_config)
            }
            _ => continue,
        };
        let Ok(raster) = raster else { continue };
        record.diagonal_fitting = Some(crate::reference::DiagonalFittingCapture {
            model: "diagonal-shape-04".into(),
            raw_source: raw_features
                .as_ref()
                .and_then(|r| serde_json::to_value(r).ok()),
            upstream_commands: record.fitted_commands.clone(),
            native_axes,
            reason: fit.reason.clone(),
            size_px,
            reference: donors_value.clone(),
        });
        record.source_commands = Some(raw.fitted_commands.clone());
        record.fitted_commands = fit.commands;
        record.coverage_sha256 = format!("{:x}", sha2::Sha256::digest(&raster.coverage));
        record.coverage = raster.coverage;
        record.pixels = raster.pixels;
        record.left = raster.left;
        record.top = raster.top;
        record.width = raster.width;
        record.height = raster.height;
        applied_any = true;
    }
    if applied_any {
        report.implementation.push_str(":diagonal-shape-04");
    }
    Ok(())
}

// Frozen fifteen-glyph upright reference at the request axes, size and
// hint policy. The upstream donors use the current pipeline without
// recursive diagonal fitting; iteration follows sorted codepoints.
fn diagonal_reference(
    session: &CaptureSession<'_>,
    request: &ReferenceRequest,
    pipeline: &crate::renderer::RenderPipeline,
) -> Option<crate::diagonal_fitting::Reference> {
    let mut donor_settings = request.settings.clone();
    donor_settings.characters = DIAGONAL_DONORS.into();
    let upstream = render_with_rasterization_in_session(
        session,
        &ReferenceRequest {
            profile: request.profile.clone(),
            extensions: StemFittingStrategy::extension(Some(pipeline.fitting)).to_string(),
            settings: donor_settings.clone(),
        },
        pipeline.rasterization,
    )
    .ok()?;
    donor_settings.hinting = Hinting::None;
    donor_settings.mono_raster = Default::default();
    let source = session
        .source(&ReferenceRequest {
            profile: request.profile.clone(),
            extensions: "none".into(),
            settings: donor_settings,
        })
        .ok()?;
    // Every donor must resolve on both sides with identical glyph
    // identity; a missing or substituted (.notdef) donor retains upstream.
    let mut expected: Vec<u32> = DIAGONAL_DONORS.chars().map(|ch| ch as u32).collect();
    expected.sort_unstable();
    if !source.missing_codepoints.is_empty() || !upstream.missing_codepoints.is_empty() {
        return None;
    }
    let mut pairs: Vec<(
        &[crate::probe::FittedCommand],
        &[crate::probe::FittedCommand],
    )> = Vec::with_capacity(expected.len());
    for codepoint in &expected {
        let (Some(raw), Some(fitted)) = (
            source
                .records
                .iter()
                .find(|record| record.codepoint == *codepoint),
            upstream
                .records
                .iter()
                .find(|record| record.codepoint == *codepoint),
        ) else {
            return None;
        };
        if raw.glyph_id == 0 || raw.glyph_id != fitted.glyph_id {
            return None;
        }
        pairs.push((
            raw.fitted_commands.as_slice(),
            fitted.fitted_commands.as_slice(),
        ));
    }
    let reference =
        crate::diagonal_fitting::build_reference(&pairs, f64::from(request.settings.size_px));
    if reference.anchors.is_empty() {
        return None;
    }
    Some(reference)
}

/// Keep fitting and its returned metrics identical when comparing scanners.
/// Historical candidate captures retain their pinned scanner through `render`.
pub fn render_with_rasterization(
    data: &[u8],
    request: &ReferenceRequest,
    rasterization: crate::renderer::Rasterization,
) -> Result<ReferenceReport, Error> {
    render_with_rasterization_in_session(&CaptureSession::new(data), request, rasterization)
}

pub(crate) fn render_with_rasterization_in_session(
    session: &CaptureSession<'_>,
    request: &ReferenceRequest,
    rasterization: crate::renderer::Rasterization,
) -> Result<ReferenceReport, Error> {
    let data = session.data;
    if rasterization == crate::renderer::Rasterization::FreeTypeMonoTerminals {
        return render_with_terminals(session, request);
    }
    if request.extensions == EXTENSIONS_SOURCE_WIDTH_01 {
        return render_source_width(session, request, rasterization);
    }
    if request.extensions == EXTENSIONS_FONT_HINTS_AUTO {
        return crate::selective_fitting::render(session, request, rasterization);
    }
    if rasterization == crate::renderer::Rasterization::Coverage {
        crate::require_default_mono_raster(&request.settings)?;
    }
    let strategy = match request.extensions.as_str() {
        EXTENSIONS_FONT_HINTS_FIRST => StemFittingStrategy::FontHintsFirst,
        EXTENSIONS_MONO_WIDTH_01 => StemFittingStrategy::UpstreamMono,
        _ => {
            return Err(fail(
                "candidate rendering requires font-hints-01 or mono-width-01",
            ))
        }
    };
    if !matches!(
        request.settings.hinting,
        Hinting::Auto | Hinting::AutoFallback
    ) {
        return Err(fail(
            "candidate fitting requires automatic policy selection",
        ));
    }
    // Explicit depths share Gray's upstream Normal fitting and Alpha
    // coverage; only quantization changes (probe::raster).
    // https://docs.rs/skrifa/0.48.0/skrifa/outline/enum.SmoothMode.html
    if rasterization == crate::renderer::Rasterization::Coverage
        && matches!(request.settings.output_bits, 2 | 3 | 4)
        && strategy == StemFittingStrategy::UpstreamMono
    {
        let mut effective = request.clone();
        effective.settings.hinting = Hinting::Auto;
        let policy = CapturePolicy {
            target: SmoothMode::Normal.into(),
            target_name: String::from("smooth"),
            smooth_mode: Some(String::from("normal")),
            symmetric_rendering: Some(true),
            preserve_linear_metrics: Some(false),
            dropout: false,
            mono_scanner: false,
            force_auto: false,
            implementation: String::from(crate::reference::IMPLEMENTATION_UPSTREAM),
            fork: false,
            extensions: request.extensions.clone(),
        };
        return session.capture(&effective, "auto", &policy);
    }
    if request.profile == PROFILE_GRAY_3BIT && strategy == StemFittingStrategy::FontHintsFirst {
        let mut upstream = request.clone();
        upstream.extensions = String::from("none");
        upstream.settings.hinting = Hinting::Auto;
        let mut report = session.reference(&upstream)?;
        report.extensions = request.extensions.clone();
        return Ok(report);
    }
    if request.profile != PROFILE_MONO_1BIT {
        return Err(fail("Mono fitting requires profile 'mono_1bit'"));
    }
    if request.settings.output_bits != 1 {
        return Err(fail("profile mono_1bit requires settings.output_bits 1"));
    }
    // Strategy selection explicitly controls the effective automatic policy;
    // normalize before capture so both requested and selected engine metadata
    // describe the actual draw. None/Interpreter never silently enable it.
    let mut effective = request.clone();
    effective.settings.hinting = strategy.hinting();
    // Narrow conservative fallback: `FontHintsFirst` on a TrueType font
    // verified to carry no glyph instructions, no `fpgm`, and at most a
    // scan-control-only `prep` uses upstream automatic Mono fitting instead
    // of upstream selection. Font-wide structural decision resolved once
    // here, never per glyph; every other case keeps upstream selection.
    let force_auto =
        strategy == StemFittingStrategy::FontHintsFirst && crate::font_hints::use_automatic(data);
    let policy = CapturePolicy {
        target: Target::Mono,
        target_name: String::from("mono"),
        smooth_mode: None,
        symmetric_rendering: None,
        preserve_linear_metrics: None,
        dropout: false,
        mono_scanner: rasterization == crate::renderer::Rasterization::FreeTypeMono,
        force_auto,
        implementation: format!(
            "skrifa-{}:registry:{}",
            request.extensions,
            crate::probe::skrifa_version()
        ),
        fork: false,
        extensions: request.extensions.clone(),
    };
    let selected = match strategy {
        StemFittingStrategy::FontHintsFirst
        | StemFittingStrategy::SourceRelative
        | StemFittingStrategy::FontHintsAuto => "auto_fallback",
        StemFittingStrategy::UpstreamMono => "auto",
    };
    session.capture(&effective, selected, &policy)
}

fn render_source_width(
    session: &CaptureSession<'_>,
    request: &ReferenceRequest,
    rasterization: crate::renderer::Rasterization,
) -> Result<ReferenceReport, Error> {
    if request.profile != PROFILE_MONO_1BIT
        || request.settings.output_bits != 1
        || rasterization != crate::renderer::Rasterization::FreeTypeMono
    {
        return Err(fail(
            "source-relative fitting requires monochrome scan conversion",
        ));
    }
    let mut upstream_request = request.clone();
    upstream_request.extensions = EXTENSIONS_FONT_HINTS_FIRST.into();
    let mut report = render_with_rasterization_in_session(
        session,
        &upstream_request,
        crate::renderer::Rasterization::FreeTypeMono,
    )?;
    report.extensions = EXTENSIONS_SOURCE_WIDTH_01.into();
    report.implementation.push_str(":source-width-01");
    if !report
        .records
        .iter()
        .any(|record| record.selected_engine == "auto")
    {
        return Ok(report);
    }
    let mut source_request = request.clone();
    source_request.extensions = "none".into();
    source_request.settings.hinting = Hinting::None;
    source_request.settings.mono_raster = Default::default();
    let source = session.source(&source_request)?;
    if source.records.len() != report.records.len() {
        return Err(fail("width source repertoire changed"));
    }
    for (record, raw) in report.records.iter_mut().zip(&source.records) {
        if record.codepoint != raw.codepoint || record.glyph_id != raw.glyph_id {
            return Err(fail("width source glyph identity changed"));
        }
        if record.selected_engine != "auto" {
            continue;
        }
        // Width recognition is optional after a successful upstream scan.
        // Unsupported source-domain geometry must keep that glyph usable.
        let Ok(fit) = crate::source_width::fit(
            &raw.fitted_commands,
            &record.fitted_commands,
            request.settings.size_px,
        ) else {
            continue;
        };
        if !fit.applied {
            continue;
        }
        // Hobby (5)/(17) adjusts recognized widths before the shared scanner;
        // scaler-returned advances and source layout stay with the upstream fit.
        let Ok(raster) = crate::mono::rasterize(&fit.commands, &request.settings) else {
            continue;
        };
        record.width_fitting = Some(crate::reference::SourceWidthCapture {
            size_px: request.settings.size_px,
            upstream_commands: record.fitted_commands.clone(),
        });
        record.source_commands = Some(raw.fitted_commands.clone());
        record.fitted_commands = fit.commands;
        record.coverage_sha256 = format!("{:x}", sha2::Sha256::digest(&raster.coverage));
        record.coverage = raster.coverage;
        record.pixels = raster.pixels;
        record.left = raster.left;
        record.top = raster.top;
        record.width = raster.width;
        record.height = raster.height;
    }
    Ok(report)
}

fn render_with_terminals(
    session: &CaptureSession<'_>,
    request: &ReferenceRequest,
) -> Result<ReferenceReport, Error> {
    if request.profile != PROFILE_MONO_1BIT || request.settings.output_bits != 1 {
        return Err(fail("terminal scan conversion requires monochrome output"));
    }
    let mut report = render_with_rasterization_in_session(
        session,
        request,
        crate::renderer::Rasterization::FreeTypeMono,
    )?;
    if !request.settings.mono_raster.include_stubs
        || request.settings.mono_raster.dropout != crate::MonoDropoutMode::Smart
        || !report
            .records
            .iter()
            .any(|record| record.selected_engine == "auto")
    {
        return Ok(report);
    }
    let mut source_request = request.clone();
    source_request.extensions = "none".into();
    source_request.settings.hinting = Hinting::None;
    source_request.settings.mono_raster = Default::default();
    let source = session.source(&source_request)?;
    if report.records.len() != source.records.len() {
        return Err(fail("terminal source repertoire changed"));
    }
    for (record, raw) in report.records.iter_mut().zip(&source.records) {
        if record.codepoint != raw.codepoint || record.glyph_id != raw.glyph_id {
            return Err(fail("terminal source glyph identity changed"));
        }
        // Executed font scan state remains authoritative. The automatic
        // path suppresses only source/fitted supporting-cap rescues;
        // SCANTYPE 5 globally would also remove interior junction pixels.
        if record.selected_engine != "auto" {
            continue;
        }
        let output = rasterize_terminals(
            &raw.fitted_commands,
            &record.fitted_commands,
            &request.settings,
        )?;
        record.pixels = output.pixels;
        record.raster_policy = crate::reference::RasterPolicy::FreeTypeMonoTerminals;
        record.source_commands = Some(raw.fitted_commands.clone());
    }
    report.implementation.push_str(":source-terminals-01");
    Ok(report)
}

pub(crate) fn rasterize_terminals(
    source: &[crate::probe::FittedCommand],
    fitted: &[crate::probe::FittedCommand],
    config: &Config,
) -> Result<crate::probe::RasterOutput, Error> {
    let mut output = crate::mono::rasterize(fitted, config)?;
    let mut no_stubs = config.clone();
    no_stubs.mono_raster.include_stubs = false;
    no_stubs.mono_raster.font_instructions = false;
    let without = crate::mono::rasterize(fitted, &no_stubs)?;
    output.pixels =
        crate::terminal_caps::suppress_certified(source, fitted, &output, &without)?.pixels;
    Ok(output)
}

/// Generate the working candidate as a bitmap strike.
///
/// This is the maintained candidate counterpart to legacy `generate()`:
/// glyph bitmaps and offsets come from the candidate capture, advances are
/// whole pixels (fitted when available, otherwise the rounded source
/// advance, with a common advance for source-tabular digits), and pair
/// adjustments are sparse whole-pixel values resolved once from source
/// kerning plus any available fitted bearing correction. Consumers add a
/// pair adjustment exactly once for that pair; pen positions accumulated
/// from these metrics are whole pixels at any starting pixel. Only 1-bit
/// Mono and 3-bit Gray strikes are defined; other depths fail explicitly.
/// `strategy` selects the Mono fitting policy and is ignored for Gray,
/// which retains upstream Normal automatic fitting.
pub fn generate_bitmap_font(
    data: &[u8],
    config: &Config,
    strategy: Option<StemFittingStrategy>,
) -> Result<GeneratedFont, Error> {
    generate_bitmap_font_with_tracking(data, config, strategy, 0.0)
}

/// Generate the working candidate as a bitmap strike with uniform tracking.
///
/// Bakes a signed whole-pixel step into every finalized advance, including
/// spaces and the final glyph advance; bitmaps, offsets and sparse pair
/// adjustments are unchanged. Zero is identity. Negative results are kept:
/// tightening may overlap. Only `i32` overflow fails.
pub fn generate_bitmap_font_with_tracking(
    data: &[u8],
    config: &Config,
    strategy: Option<StemFittingStrategy>,
    letter_spacing_px: f32,
) -> Result<GeneratedFont, Error> {
    generate_bitmap_font_impl(data, config, strategy, letter_spacing_px, None)
}

/// Export Mono using the same explicit stages and uniform tracking as preview.
pub fn generate_monochrome_font_with_pipeline(
    data: &[u8],
    config: &Config,
    pipeline: crate::renderer::RenderPipeline,
    letter_spacing_px: f32,
) -> Result<GeneratedFont, Error> {
    if config.output_bits != 1 {
        return Err(fail("monochrome bitmap export requires output_bits 1"));
    }
    pipeline.validate(config)?;
    generate_bitmap_font_impl(
        data,
        config,
        Some(pipeline.fitting),
        letter_spacing_px,
        Some(pipeline),
    )
}

fn generate_bitmap_font_impl(
    data: &[u8],
    config: &Config,
    strategy: Option<StemFittingStrategy>,
    letter_spacing_px: f32,
    pipeline: Option<crate::renderer::RenderPipeline>,
) -> Result<GeneratedFont, Error> {
    crate::layout_spacing::uniform_tracking_26_6(letter_spacing_px)?;
    let profile = match config.output_bits {
        1 => PROFILE_MONO_1BIT,
        3 => PROFILE_GRAY_3BIT,
        other => {
            return Err(fail(format!(
                "candidate bitmap generation requires output_bits 1 or 3, got {other}"
            )))
        }
    };
    let strategy = strategy.unwrap_or_default();
    let mut effective = config.clone();
    effective.hinting = if config.output_bits == 1 {
        strategy.hinting()
    } else {
        Hinting::Auto
    };
    // Source metrics and kerning are inputs to the bitmap policy, not an
    // alternative layout: prepare them without rasterizing, then take
    // every bitmap from the one candidate capture below.
    let source = crate::source::prepare_source(data, &effective)?;
    let preview = ReferenceRequest {
        profile: profile.to_string(),
        extensions: if config.output_bits == 1 {
            StemFittingStrategy::extension(Some(strategy)).to_string()
        } else {
            EXTENSIONS_FONT_HINTS_FIRST.to_string()
        },
        settings: effective.clone(),
    };
    // Export shares the one explicit-pipeline capture with preview;
    // finalized advances below come from preserved upstream metrics, so a
    // changed diagonal bitmap frame cannot smuggle different layout.
    let report = match pipeline {
        Some(pipeline) => render_with_pipeline(data, &preview, pipeline)?,
        None => {
            render_with_rasterization(data, &preview, crate::renderer::Rasterization::FreeTypeMono)?
        }
    };
    let source_advances: HashMap<u32, i32> = source
        .glyphs
        .iter()
        .map(|glyph| (glyph.codepoint, glyph.advance_26_6))
        .collect();
    let source_kern: HashMap<(u32, u32), i32> = source
        .kerning
        .iter()
        .map(|pair| ((pair.left, pair.right), pair.adjustment_26_6))
        .collect();
    let properties = font_spacing_properties(data, &effective)?;
    // The one finalized bitmap table for this strike; preview and
    // specimens resolve the same table from their own captures.
    let metrics = finalize_bitmap_metrics(
        &report.records,
        &source_advances,
        &source_kern,
        config.kerning,
        properties.monospace,
        properties.tabular_digits,
    );
    let tracked =
        crate::layout_spacing::apply_uniform_tracking(&metrics.advances_26_6, letter_spacing_px)?;
    let mut glyphs = Vec::with_capacity(report.records.len());
    for record in &report.records {
        let advance = tracked
            .get(&record.codepoint)
            .copied()
            .ok_or_else(|| fail(format!("missing bitmap advance U+{:04X}", record.codepoint)))?;
        glyphs.push(Glyph {
            codepoint: record.codepoint,
            glyph_id: record.glyph_id,
            advance_26_6: advance,
            left: record.left,
            top: record.top,
            width: record.width,
            height: record.height,
            pixels: record.pixels.clone(),
        });
    }
    glyphs.sort_by_key(|glyph| glyph.codepoint);
    let mut kerning: Vec<KerningPair> = metrics
        .pair_adjustments_26_6
        .iter()
        .map(|((left, right), adjustment)| KerningPair {
            left: *left,
            right: *right,
            adjustment_26_6: *adjustment,
        })
        .collect();
    kerning.sort_by_key(|pair| (pair.left, pair.right));
    Ok(GeneratedFont {
        source_sha256: report.source_sha256.clone(),
        config: effective,
        metrics: report.metrics.clone(),
        glyphs,
        missing_codepoints: report.missing_codepoints.clone(),
        kerning,
    })
}

#[cfg(test)]
mod tests {
    use super::generate_bitmap_font;
    use crate::{source::raster_counter, stem_fitting::StemFittingStrategy, Config};
    use std::{collections::BTreeMap, path::Path};

    fn roboto() -> Vec<u8> {
        std::fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fonts/Roboto.ttf")).unwrap()
    }

    fn config(characters: &str, output_bits: u8) -> Config {
        let mut axes = BTreeMap::new();
        axes.insert("wght".into(), 400.0);
        axes.insert("wdth".into(), 100.0);
        Config {
            size_px: 14.0,
            axes,
            characters: characters.into(),
            output_bits,
            ..Config::default()
        }
    }

    #[test]
    fn candidate_rasterizes_once_per_unique_character_and_never_for_source() {
        let data = roboto();
        // Repeated letters collapse: "hello world" has 8 unique scalars,
        // "oooo" has one.
        for (bits, strategies) in [
            (
                1u8,
                vec![
                    Some(StemFittingStrategy::FontHintsFirst),
                    Some(StemFittingStrategy::UpstreamMono),
                ],
            ),
            (3u8, vec![None]),
        ] {
            for strategy in strategies {
                for (characters, unique) in [("hello world", 8usize), ("oooo", 1usize)] {
                    raster_counter::reset();
                    let font =
                        generate_bitmap_font(&data, &config(characters, bits), strategy).unwrap();
                    assert_eq!(
                        font.glyphs.len(),
                        unique,
                        "bits={bits} strategy={strategy:?} text={characters:?}"
                    );
                    assert_eq!(
                        raster_counter::logical_rasters(),
                        unique,
                        "final raster once per unique character, bits={bits} strategy={strategy:?} text={characters:?}"
                    );
                    assert_eq!(raster_counter::source_geometry_draws(), 0);
                }
            }
        }
    }
}

/// Disabled capture returns the explicit independent reference unchanged.
pub fn capture(
    data: &[u8],
    request: &ReferenceRequest,
    enabled: bool,
) -> Result<ReferenceReport, Error> {
    if !enabled {
        if request.extensions != "none" {
            return Err(fail("disabled candidate capture requires extensions none"));
        }
        return crate::reference::reference(data, request);
    }
    render(data, request)
}
