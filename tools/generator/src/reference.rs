use crate::{
    fail, fixed,
    probe::{
        lock_sha256, rasterize, skrifa_checksum, skrifa_version, zeno_version, FittedCommand,
        FittedPen,
    },
    validate_config, Config, Error, FontMetrics, Hinting,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use skrifa::{
    instance::Size,
    outline::{DrawSettings, Engine, HintingInstance, HintingOptions, SmoothMode, Target},
    FontRef, MetadataProvider,
};
use std::collections::{BTreeMap, BTreeSet};

pub const PROFILE_MONO_1BIT: &str = "mono_1bit";
pub const PROFILE_GRAY_3BIT: &str = "gray_3bit";
pub const EXTENSIONS_NONE: &str = "none";
/// Vertical-only candidate policy: ttfautohint fits the Y axis only
/// (<https://freetype.org/ttfautohint/index.html>) and applies no special
/// diagonal handling (<https://freetype.org/ttfautohint/doc/ttfautohint.html#diagonals>).
pub const IMPLEMENTATION_UPSTREAM: &str = "upstream";

fn default_extensions() -> String {
    String::from("none")
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ReferenceRequest {
    pub profile: String,
    #[serde(default = "default_extensions")]
    pub extensions: String,
    pub settings: Config,
}

#[derive(Clone, Debug, Serialize)]
pub struct ReferenceRecord {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub side_bearing_deltas_26_6: Option<[i32; 2]>,
    pub raster_policy: RasterPolicy,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub diagonal_pairs: Option<[u32; 3]>,
    pub codepoint: u32,
    pub glyph_id: u32,
    pub selected_engine: String,
    pub target: String,
    pub smooth_mode: Option<String>,
    pub symmetric_rendering: Option<bool>,
    pub preserve_linear_metrics: Option<bool>,
    pub draw_pedantic: bool,
    pub skrifa_version: String,
    pub skrifa_registry_checksum: String,
    pub zeno_version: String,
    pub zeno_format: String,
    pub output_bits: u8,
    pub mono_threshold: u8,
    pub gray_gamma: f32,
    pub fitted_commands: Vec<FittedCommand>,
    pub coverage: Vec<u8>,
    pub coverage_sha256: String,
    pub left: i32,
    pub top: i32,
    pub width: u32,
    pub height: u32,
    pub pixels: Vec<u8>,
    pub advance_26_6: i32,
    pub hinted_has_overlaps: bool,
    pub hinted_lsb: Option<f32>,
    pub hinted_advance_width: Option<f32>,
}

#[derive(Clone, Copy, Debug, Default, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RasterPolicy {
    #[default]
    Coverage,
    CoverageDropout,
    CoverageOverlap4xDropout,
}

/// The design advance or the advance returned by the actual fitted outline.
#[derive(Clone, Copy, Debug, Default, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum AdvancePolicy {
    #[default]
    Linear,
    Hinted,
}

impl AdvancePolicy {
    fn is_linear(&self) -> bool {
        *self == Self::Linear
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct ReferenceReport {
    #[serde(skip_serializing_if = "AdvancePolicy::is_linear")]
    pub advance_policy: AdvancePolicy,
    pub source_sha256: String,
    pub size_px: f32,
    pub axes: BTreeMap<String, f32>,
    pub profile: String,
    pub extensions: String,
    pub hinting_requested: String,
    pub target: String,
    pub smooth_mode: Option<String>,
    pub symmetric_rendering: Option<bool>,
    pub preserve_linear_metrics: Option<bool>,
    pub draw_pedantic: bool,
    pub implementation: String,
    pub fork: bool,
    pub skrifa_version: String,
    pub skrifa_registry_checksum: String,
    pub zeno_version: String,
    pub dependency_lock_sha256: String,
    pub metrics: FontMetrics,
    pub missing_codepoints: Vec<u32>,
    pub records: Vec<ReferenceRecord>,
}

pub(crate) fn resolve(request: &ReferenceRequest) -> Result<(Target, String), Error> {
    if request.profile != PROFILE_MONO_1BIT && request.profile != PROFILE_GRAY_3BIT {
        return Err(fail(format!(
            "profile must be 'mono_1bit' or 'gray_3bit', got {:?}",
            request.profile
        )));
    }
    if request.extensions != EXTENSIONS_NONE {
        return Err(fail(format!(
            "unsupported extensions policy {:?}: reference mode supports only 'none'",
            request.extensions
        )));
    }
    let selected = match request.settings.hinting {
        Hinting::Auto => "auto",
        Hinting::Interpreter => "interpreter",
        Hinting::None => "none",
        Hinting::AutoFallback => {
            return Err(fail(
                "reference requires explicit Hinting::Auto, Hinting::Interpreter or Hinting::None",
            ));
        }
    };
    let want_bits = if request.profile == PROFILE_MONO_1BIT {
        1
    } else {
        3
    };
    if request.settings.output_bits != want_bits {
        return Err(fail(format!(
            "profile {} requires settings.output_bits {want_bits}, got {}",
            request.profile, request.settings.output_bits
        )));
    }
    let target = if request.profile == PROFILE_MONO_1BIT {
        Target::Mono
    } else {
        SmoothMode::Normal.into()
    };
    Ok((target, selected.to_string()))
}

/// Capture policy shared by the independent reference and the Mono
/// candidate. Callers own extension/hinting validation and target choice;
/// glyph resolution, linear metrics and raster settings stay identical so
/// role captures remain directly comparable.
#[derive(Clone)]
pub(crate) struct CapturePolicy {
    pub target: Target,
    pub target_name: String,
    pub smooth_mode: Option<String>,
    pub symmetric_rendering: Option<bool>,
    pub preserve_linear_metrics: Option<bool>,
    pub dropout: bool,
    /// Candidate-only bounded 4x overlap mitigation (FreeType-style
    /// per-sample reduction, uniform across glyphs). Only Mono candidates
    /// set this; every other capture leaves it false.
    pub overlap_4x: bool,
    pub implementation: String,
    pub fork: bool,
    pub extensions: String,
}

pub fn reference(data: &[u8], request: &ReferenceRequest) -> Result<ReferenceReport, Error> {
    let config = &request.settings;
    validate_config(config)?;
    let (target, selected) = resolve(request)?;
    let gray = request.profile == PROFILE_GRAY_3BIT;
    let policy = CapturePolicy {
        target,
        target_name: if gray { "smooth" } else { "mono" }.to_string(),
        smooth_mode: if gray {
            Some(String::from("normal"))
        } else {
            None
        },
        symmetric_rendering: if gray { Some(true) } else { None },
        preserve_linear_metrics: if gray { Some(false) } else { None },
        dropout: false,
        overlap_4x: false,
        implementation: String::from(IMPLEMENTATION_UPSTREAM),
        fork: false,
        extensions: request.extensions.clone(),
    };
    capture_with_policy(data, request, &selected, &policy)
}

pub(crate) fn capture_with_policy(
    data: &[u8],
    request: &ReferenceRequest,
    selected: &str,
    policy: &CapturePolicy,
) -> Result<ReferenceReport, Error> {
    let config = &request.settings;
    validate_config(config)?;
    let requested = selected.to_string();
    let target = policy.target;
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
        Hinting::AutoFallback => Some(Engine::AutoFallback),
        Hinting::None => None,
    };
    let selected = if config.hinting == Hinting::AutoFallback {
        if outlines.prefer_interpreter() {
            "interpreter"
        } else {
            "auto"
        }
    } else {
        selected
    }
    .to_string();
    let hinting = match engine {
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
    let metrics = font.metrics(size, &location);
    if metrics.units_per_em == 0 {
        return Err(fail("font has invalid units per em"));
    }
    let advances = font.glyph_metrics(size, &location);
    let target_name = policy.target_name.clone();
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
    // Same coordinate-selected glyphs as production generation: outlines,
    // metrics and `glyph_id` use the scalar's shaper-resolved glyph.
    let resolved = crate::spacing::resolve_scalars(data, &config.axes, config.kerning, &present)?;
    for scalar in &resolved {
        let ch = char::from_u32(scalar.codepoint).unwrap();
        let gid = skrifa::GlyphId::new(scalar.glyph_id);
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
        // Both Mono policies rasterize the unmodified upstream outline
        // through the same bounded overlap reduction and dropout pipeline.
        let output = if policy.overlap_4x {
            #[cfg(feature = "candidate")]
            {
                crate::overlap::rasterize(&fitted, config)?
            }
            #[cfg(not(feature = "candidate"))]
            {
                return Err(fail("overlap 4x raster requires the candidate feature"));
            }
        } else if policy.dropout {
            crate::dropout::rasterize(&fitted, config)?
        } else {
            rasterize(&fitted, config)?
        };
        let advance = advances
            .advance_width(gid)
            .ok_or_else(|| fail(format!("missing advance U+{:04X}", ch as u32)))?;
        let advance_26_6 = fixed(advance, config.metric_rounding);
        records.push(ReferenceRecord {
            // Source-layout policy deliberately omits fitted phantom-bearing
            // corrections, independently of how the selected hinter moves X.
            side_bearing_deltas_26_6: None,
            raster_policy: if policy.overlap_4x {
                RasterPolicy::CoverageOverlap4xDropout
            } else if policy.dropout {
                RasterPolicy::CoverageDropout
            } else {
                RasterPolicy::Coverage
            },
            diagonal_pairs: None,
            codepoint: ch as u32,
            glyph_id: scalar.glyph_id,
            selected_engine: selected.clone(),
            target: target_name.clone(),
            smooth_mode: policy.smooth_mode.clone(),
            symmetric_rendering: policy.symmetric_rendering,
            preserve_linear_metrics: policy.preserve_linear_metrics,
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
            advance_26_6,
            hinted_has_overlaps: adjusted.has_overlaps,
            hinted_lsb: adjusted.lsb,
            hinted_advance_width: adjusted.advance_width,
        });
    }
    if records.is_empty() {
        return Err(fail("repertoire contains no available glyphs"));
    }
    Ok(ReferenceReport {
        advance_policy: AdvancePolicy::Linear,
        source_sha256: format!("{:x}", Sha256::digest(data)),
        size_px: config.size_px,
        axes: config.axes.clone(),
        profile: request.profile.clone(),
        extensions: policy.extensions.clone(),
        hinting_requested: requested,
        target: target_name,
        smooth_mode: policy.smooth_mode.clone(),
        symmetric_rendering: policy.symmetric_rendering,
        preserve_linear_metrics: policy.preserve_linear_metrics,
        draw_pedantic: false,
        implementation: policy.implementation.clone(),
        fork: policy.fork,
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
