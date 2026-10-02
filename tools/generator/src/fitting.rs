use crate::{
    fail, fixed,
    probe::{lock_sha256, skrifa_checksum, skrifa_version, zeno_version, FittedPen},
    reference::{
        ReferenceRecord, ReferenceReport, ReferenceRequest, PROFILE_GRAY_3BIT, PROFILE_MONO_1BIT,
    },
    validate_config, Error, FontMetrics, Hinting,
};
use sha2::{Digest, Sha256};
use fitting_skrifa::{
    instance::Size,
    outline::{DrawSettings, Engine, HintingInstance, HintingOptions, SmoothMode, Target},
    FontRef, MetadataProvider,
};
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

pub fn capture(
    data: &[u8],
    request: &ReferenceRequest,
    enabled: bool,
) -> Result<ReferenceReport, Error> {
    let config = &request.settings;
    validate_config(config)?;
    let mut upstream_request = request.clone();
    upstream_request.extensions = String::from("none");
    if request.extensions != "none" && request.extensions != EXTENSIONS_DIAGONAL_01 {
        return Err(fail("unsupported iteration extension policy"));
    }
    if !enabled && request.extensions != "none" {
        return Err(fail("disabled fork capture requires extensions none"));
    }
    if enabled
        && (request.extensions != EXTENSIONS_DIAGONAL_01
            || request.settings.hinting != Hinting::Auto
            || request.profile != PROFILE_MONO_1BIT)
    {
        return Err(fail(
            "diagonal fitting requires mono_1bit automatic hinting",
        ));
    }
    let (_, selected) = crate::reference::resolve(&upstream_request)?;
    let target = if request.profile == PROFILE_MONO_1BIT {
        Target::Mono
    } else {
        SmoothMode::Normal.into()
    };
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
    let engine = match config.hinting {
        Hinting::Auto => Some(Engine::Auto(None)),
        Hinting::Interpreter => Some(Engine::Interpreter),
        _ => None,
    };
    let mut hinting = match engine {
        Some(engine) => Some(
            HintingInstance::new(
                &outlines,
                size,
                &location,
                HintingOptions { engine, target },
            )
            .map_err(|e| fail(format!("hinting setup failed: {e}")))?,
        ),
        None => None,
    };
    if enabled
        && !hinting
            .as_mut()
            .is_some_and(|h| h.set_diagonal_constraints(true))
    {
        return Err(fail("diagonal extension could not be enabled"));
    }
    if enabled {
        if !hinting
            .as_mut()
            .is_some_and(|h| h.set_diagonal_stem_relative(true))
        {
            return Err(fail("stem-relative diagonal policy could not be enabled"));
        }
    }
    let metrics = font.metrics(size, &location);
    if metrics.units_per_em == 0 {
        return Err(fail("font has invalid units per em"));
    }
    let advances = font.glyph_metrics(size, &location);
    let gray = request.profile == PROFILE_GRAY_3BIT;
    let target_name = if gray { "smooth" } else { "mono" }.to_string();
    let mut records = Vec::new();
    let mut missing_codepoints = Vec::new();
    for ch in config.characters.chars().collect::<BTreeSet<_>>() {
        crate::spacing::validate_request(ch)?;
        let Some(gid) = font.charmap().map(ch).filter(|g| g.to_u32() != 0) else {
            if config.missing_glyphs == crate::MissingGlyphs::Error {
                return Err(fail(format!("missing glyph U+{:04X}", ch as u32)));
            }
            missing_codepoints.push(ch as u32);
            continue;
        };
        crate::spacing::validate_character(ch)?;
        let outline = outlines
            .get(gid)
            .ok_or_else(|| fail(format!("missing outline U+{:04X}", ch as u32)))?;
        let mut pen = FittedPen::default();
        let settings = match &hinting {
            Some(h) => DrawSettings::hinted(h, false),
            None => DrawSettings::unhinted(size, &location),
        };
        let adjusted = outline
            .draw(settings, &mut pen)
            .map_err(|e| fail(format!("outline U+{:04X}: {e}", ch as u32)))?;
        let fitted = pen.into_commands();
        let output = rasterize_enabled(&fitted, config, enabled)?;
        let advance = advances
            .advance_width(gid)
            .ok_or_else(|| fail(format!("missing advance U+{:04X}", ch as u32)))?;
        records.push(ReferenceRecord {
            raster_policy: raster_policy(enabled),
            diagonal_pairs: adjusted.diagonal_pairs,
            codepoint: ch as u32,
            glyph_id: gid.to_u32(),
            selected_engine: selected.clone(),
            target: target_name.clone(),
            smooth_mode: if gray {
                Some(String::from("normal"))
            } else {
                None
            },
            symmetric_rendering: if gray { Some(true) } else { None },
            preserve_linear_metrics: if gray { Some(false) } else { None },
            draw_pedantic: false,
            skrifa_version: skrifa_version(),
            skrifa_registry_checksum: skrifa_checksum(),
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
        source_sha256: format!("{:x}", Sha256::digest(data)),
        size_px: config.size_px,
        axes: config.axes.clone(),
        profile: request.profile.clone(),
        extensions: request.extensions.clone(),
        hinting_requested: selected,
        target: target_name,
        smooth_mode: if gray {
            Some(String::from("normal"))
        } else {
            None
        },
        symmetric_rendering: if gray { Some(true) } else { None },
        preserve_linear_metrics: if gray { Some(false) } else { None },
        draw_pedantic: false,
        implementation: format!(
            "skrifa-{}:{}",
            if enabled {
                request.extensions.as_str()
            } else {
                EXTENSIONS_DIAGONAL_01
            },
            FITTING_SHA256
        ),
        fork: true,
        skrifa_version: skrifa_version(),
        skrifa_registry_checksum: skrifa_checksum(),
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
