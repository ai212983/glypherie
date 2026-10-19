use crate::{
    fail, fixed,
    probe::{lock_sha256, zeno_version, FittedPen},
    reference::{
        ReferenceRecord, ReferenceReport, ReferenceRequest, PROFILE_GRAY_3BIT, PROFILE_MONO_1BIT,
    },
    validate_config, Error, FontMetrics, Hinting,
};
use fitting_skrifa::{
    instance::Size,
    outline::{DrawSettings, Engine, HintingInstance, HintingOptions, Target},
    FontRef, MetadataProvider,
};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;

pub const EXTENSIONS_DIAGONAL_01: &str = "diagonal-01";

pub fn render(data: &[u8], request: &ReferenceRequest) -> Result<ReferenceReport, Error> {
    if request.extensions != EXTENSIONS_DIAGONAL_01 {
        return Err(fail("iteration rendering requires diagonal-01"));
    }
    if request.settings.hinting != Hinting::Auto {
        return Err(fail("diagonal fitting requires automatic hinting"));
    }
    if request.profile == PROFILE_GRAY_3BIT {
        let mut upstream = request.clone();
        upstream.extensions = String::from("none");
        let mut report = crate::reference::reference(data, &upstream)?;
        report.extensions = request.extensions.clone();
        return Ok(report);
    }
    capture(data, request, true)
}

/// Capture with the legacy fork, or, when disabled, the independent
/// reference unchanged. Disabled capture therefore reports the current
/// registry identity, not the legacy fork's.
pub fn capture(
    data: &[u8],
    request: &ReferenceRequest,
    enabled: bool,
) -> Result<ReferenceReport, Error> {
    if !enabled {
        if request.extensions != "none" {
            return Err(fail("disabled fork capture requires extensions none"));
        }
        return crate::reference::reference(data, request);
    }
    capture_enabled(data, request)
}

fn capture_enabled(data: &[u8], request: &ReferenceRequest) -> Result<ReferenceReport, Error> {
    let config = &request.settings;
    validate_config(config)?;
    if request.extensions != EXTENSIONS_DIAGONAL_01
        || request.settings.hinting != Hinting::Auto
        || request.profile != PROFILE_MONO_1BIT
    {
        return Err(fail(
            "diagonal fitting requires mono_1bit automatic hinting",
        ));
    }
    let mut upstream_request = request.clone();
    upstream_request.extensions = String::from("none");
    // Profile/bits validation and the selected-engine name stay with the
    // reference contract; the draw below is the legacy Mono capture.
    let (_, selected) = crate::reference::resolve(&upstream_request)?;
    if !matches!(data.get(..4), Some(b"\0\x01\0\0" | b"OTTO")) {
        return Err(fail("supported input is a single sfnt TTF/OTF outline font; collections, WOFF and bitmap formats require conversion"));
    }
    let font = FontRef::new(data).map_err(|e| fail(format!("invalid font: {e}")))?;
    for tag in [b"COLR", b"SVG ", b"CBDT", b"sbix"] {
        if font.table_data(skrifa::Tag::new(tag)).is_some() {
            return Err(fail("color fonts require a color output adapter"));
        }
    }
    if ![b"glyf", b"CFF ", b"CFF2"]
        .iter()
        .any(|t| font.table_data(skrifa::Tag::new(t)).is_some())
    {
        return Err(fail("font has no supported glyf/CFF/CFF2 outlines"));
    }
    for (tag, value) in &config.axes {
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
        .location(config.axes.iter().map(|(t, v)| (t.as_str(), *v)));
    let size = Size::new(config.size_px);
    let outlines = font.outline_glyphs();
    let mut hinting = HintingInstance::new(
        &outlines,
        size,
        &location,
        HintingOptions {
            engine: Engine::Auto(None),
            target: Target::Mono,
        },
    )
    .map_err(|e| fail(format!("hinting setup failed: {e}")))?;
    if !hinting.set_diagonal_constraints(true) {
        return Err(fail("diagonal extension could not be enabled"));
    }
    if !hinting.set_diagonal_stem_relative(true) {
        return Err(fail("stem-relative diagonal policy could not be enabled"));
    }
    let metrics = font.metrics(size, &location);
    if metrics.units_per_em == 0 {
        return Err(fail("font has invalid units per em"));
    }
    let advances = font.glyph_metrics(size, &location);
    let mut records = Vec::new();
    let mut missing_codepoints = Vec::new();
    let mut present = Vec::new();
    for ch in config.characters.chars().collect::<BTreeSet<_>>() {
        crate::spacing::validate_request(ch)?;
        if font.charmap().map(ch).is_none_or(|g| g.to_u32() == 0) {
            if config.missing_glyphs == crate::MissingGlyphs::Error {
                return Err(fail(format!("missing glyph U+{:04X}", ch as u32)));
            }
            missing_codepoints.push(ch as u32);
            continue;
        };
        crate::spacing::validate_character(ch)?;
        present.push(ch);
    }
    // Same coordinate-selected glyphs as production generation and the
    // independent reference: outlines, metrics and `glyph_id` use the
    // scalar's shaper-resolved glyph.
    let resolved =
        crate::spacing::resolve_scalars(data, &config.axes, config.kerning, &present)?;
    for scalar in &resolved {
        let ch = char::from_u32(scalar.codepoint).unwrap();
        let gid = fitting_skrifa::GlyphId::new(scalar.glyph_id);
        let outline = outlines
            .get(gid)
            .ok_or_else(|| fail(format!("missing outline U+{:04X}", ch as u32)))?;
        let mut pen = FittedPen::default();
        let adjusted = outline
            .draw(DrawSettings::hinted(&hinting, false), &mut pen)
            .map_err(|e| fail(format!("outline U+{:04X}: {e}", ch as u32)))?;
        let fitted = pen.into_commands();
        // Approved dropout applies only to this enabled Mono automatic
        // instance; raw coverage is never modified.
        let output = crate::dropout::rasterize(&fitted, config)?;
        let advance = advances
            .advance_width(gid)
            .ok_or_else(|| fail(format!("missing advance U+{:04X}", ch as u32)))?;
        if !advance.is_finite() {
            return Err(fail("nonfinite fitted advance"));
        }
        records.push(ReferenceRecord {
            // Source-layout policy deliberately omits fitted phantom-bearing
            // corrections, independently of how the selected hinter moves X.
            side_bearing_deltas_26_6: None,
            raster_policy: crate::reference::RasterPolicy::CoverageDropout,
            diagonal_pairs: adjusted.diagonal_pairs,
            codepoint: ch as u32,
            glyph_id: scalar.glyph_id,
            selected_engine: selected.clone(),
            target: String::from("mono"),
            smooth_mode: None,
            symmetric_rendering: None,
            preserve_linear_metrics: None,
            draw_pedantic: false,
            skrifa_version: fitting_skrifa_version(),
            skrifa_registry_checksum: fitting_skrifa_checksum(),
            zeno_version: zeno_version(),
            zeno_format: String::from("alpha"),
            output_bits: config.output_bits,
            mono_threshold: config.mono_threshold,
            gray_gamma: config.gray_gamma,
            fitted_commands: fitted,
            coverage_sha256: format!("{:x}", Sha256::digest(&output.coverage)),
            coverage: output.coverage,
            left: output.left,
            top: output.top,
            width: output.width,
            height: output.height,
            pixels: output.pixels,
            advance_26_6: fixed(advance, config.metric_rounding),
            hinted_has_overlaps: adjusted.has_overlaps,
            hinted_lsb: adjusted.lsb,
            hinted_advance_width: adjusted.advance_width,
        });
    }
    if records.is_empty() {
        return Err(fail("repertoire contains no available glyphs"));
    }
    Ok(ReferenceReport {
        advance_policy: ADVANCE_POLICY,
        source_sha256: format!("{:x}", Sha256::digest(data)),
        size_px: config.size_px,
        axes: config.axes.clone(),
        profile: request.profile.clone(),
        extensions: request.extensions.clone(),
        hinting_requested: selected,
        target: String::from("mono"),
        smooth_mode: None,
        symmetric_rendering: None,
        preserve_linear_metrics: None,
        draw_pedantic: false,
        implementation: format!(
            "skrifa-{}:{}",
            request.extensions.as_str(),
            FITTING_SHA256
        ),
        fork: true,
        skrifa_version: fitting_skrifa_version(),
        skrifa_registry_checksum: fitting_skrifa_checksum(),
        zeno_version: zeno_version(),
        dependency_lock_sha256: lock_sha256(),
        metrics: FontMetrics {
            ascent_26_6: fixed(metrics.ascent, config.metric_rounding),
            descent_26_6: fixed(metrics.descent, config.metric_rounding),
            line_gap_26_6: fixed(metrics.leading, config.metric_rounding),
        },
        missing_codepoints,
        records,
    })
}
