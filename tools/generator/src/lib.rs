//! Deterministic outline glyph generation, independent of display and output adapters.
//! Metrics use signed 26.6 pixels. Bitmaps contain unpacked coverage levels, row-major.
pub mod baseline;
pub mod batch;
#[cfg(feature = "candidate")]
pub mod candidate;
pub mod comparison;
pub mod evaluation;
/// Compatibility name for earlier diagnostic callers; renderer selection uses roles.
#[cfg(feature = "candidate")]
pub use candidate as iteration;
pub mod preview_selection;
pub mod probe;
mod raster;
pub mod reference;
pub mod renderer;
mod spacing;
pub mod specimen_config;
pub mod specimens;

use production_skrifa::{
    instance::Size,
    outline::{DrawSettings, Engine, HintingInstance, HintingOptions, SmoothMode, Target},
    FontRef, MetadataProvider,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use skrifa_baseline as production_skrifa;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Hinting {
    None,
    #[default]
    Auto,
    Interpreter,
    AutoFallback,
}
#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum MissingGlyphs {
    #[default]
    Error,
    Skip,
}
#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum MetricRounding {
    #[default]
    Subpixel,
    Pixel,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(default, deny_unknown_fields)]
pub struct Config {
    pub size_px: f32,
    pub axes: BTreeMap<String, f32>,
    pub hinting: Hinting,
    pub output_bits: u8,
    pub mono_threshold: u8,
    /// Gray coverage becomes coverage.powf(gray_gamma) before nearest-level quantization.
    pub gray_gamma: f32,
    pub characters: String,
    pub missing_glyphs: MissingGlyphs,
    pub kerning: bool,
    pub metric_rounding: MetricRounding,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            size_px: 16.0,
            axes: BTreeMap::new(),
            hinting: Hinting::Auto,
            output_bits: 1,
            mono_threshold: 128,
            gray_gamma: 1.0,
            characters: String::new(),
            missing_glyphs: MissingGlyphs::Error,
            kerning: true,
            metric_rounding: MetricRounding::Subpixel,
        }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct Glyph {
    pub codepoint: u32,
    pub glyph_id: u32,
    pub advance_26_6: i32,
    pub left: i32,
    /// Signed y-down bitmap origin relative to the baseline.
    pub top: i32,
    pub width: u32,
    pub height: u32,
    pub pixels: Vec<u8>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct KerningPair {
    pub left: u32,
    pub right: u32,
    pub adjustment_26_6: i32,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct FontMetrics {
    pub ascent_26_6: i32,
    pub descent_26_6: i32,
    pub line_gap_26_6: i32,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct GeneratedFont {
    pub source_sha256: String,
    pub config: Config,
    pub metrics: FontMetrics,
    pub glyphs: Vec<Glyph>,
    pub missing_codepoints: Vec<u32>,
    pub kerning: Vec<KerningPair>,
}
#[derive(Debug)]
pub struct Error(pub String);
impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}
impl std::error::Error for Error {}
pub(crate) fn fail(message: impl Into<String>) -> Error {
    Error(message.into())
}
pub(crate) fn fixed(value: f32, rounding: MetricRounding) -> i32 {
    match rounding {
        MetricRounding::Subpixel => (value * 64.0).round() as i32,
        MetricRounding::Pixel => value.round() as i32 * 64,
    }
}

/// Generate individual horizontal Latin, Greek, Cyrillic and common-symbol glyphs.
/// Combining marks and other scripts require a text-run shaping adapter. Optional
/// Latin ligatures and contextual alternates are disabled for pair extraction.
/// Pair positioning is accepted only when representable as a left advance change.
pub fn generate(data: &[u8], config: &Config) -> Result<GeneratedFont, Error> {
    validate_config(config)?;
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
        Hinting::None | Hinting::AutoFallback => Engine::AutoFallback,
        Hinting::Auto => Engine::Auto(None),
        Hinting::Interpreter => Engine::Interpreter,
    };
    let target = if config.output_bits == 1 {
        Target::Mono
    } else {
        Target::Smooth {
            mode: SmoothMode::Normal,
            symmetric_rendering: true,
            preserve_linear_metrics: true,
        }
    };
    let hinting = if config.hinting == Hinting::None {
        None
    } else {
        Some(
            HintingInstance::new(
                &outlines,
                size,
                &location,
                HintingOptions { engine, target },
            )
            .map_err(|e| fail(format!("hinting setup failed: {e}")))?,
        )
    };
    let mut hinting = hinting;
    // Accepted 001.01: use the reviewed model only for actual Mono autohint
    // instances. AutoFallback retains upstream embedded-interpreter selection;
    // the setters reject that engine, as well as all non-Mono targets.
    if config.output_bits == 1 && matches!(config.hinting, Hinting::Auto | Hinting::AutoFallback) {
        if let Some(instance) = hinting.as_mut() {
            if instance.set_diagonal_constraints(true) {
                if !instance.set_diagonal_stem_relative(true) {
                    return Err(fail("accepted diagonal width policy could not be enabled"));
                }
            } else if config.hinting == Hinting::Auto {
                return Err(fail("accepted diagonal fitting could not be enabled"));
            }
        }
    }
    let metrics = font.metrics(size, &location);
    if metrics.units_per_em == 0 {
        return Err(fail("font has invalid units per em"));
    }
    let advances = font.glyph_metrics(size, &location);
    let mut glyphs = Vec::new();
    let mut missing_codepoints = Vec::new();
    for ch in config.characters.chars().collect::<BTreeSet<_>>() {
        // Missing-glyph policy covers unassigned scalars; controls and text-run
        // shaping requests remain capability errors even when absent in cmap.
        spacing::validate_request(ch)?;
        let Some(gid) = font.charmap().map(ch).filter(|g| g.to_u32() != 0) else {
            if config.missing_glyphs == MissingGlyphs::Error {
                return Err(fail(format!("missing glyph U+{:04X}", ch as u32)));
            }
            missing_codepoints.push(ch as u32);
            continue;
        };
        spacing::validate_character(ch)?;
        let outline = outlines
            .get(gid)
            .ok_or_else(|| fail(format!("missing outline U+{:04X}", ch as u32)))?;
        let mut pen = probe::FittedPen::default();
        let settings = match &hinting {
            Some(h) => DrawSettings::hinted(h, false),
            None => DrawSettings::unhinted(size, &location),
        };
        outline
            .draw(settings, &mut pen)
            .map_err(|e| fail(format!("outline U+{:04X}: {e}", ch as u32)))?;
        let (pixels, left, top, width, height) = raster::render(pen.commands(), config)?;
        // Linear advances share the same variation coordinates as the shaper;
        // pixel rounding is applied once, explicitly, to the output metric.
        let advance = advances
            .advance_width(gid)
            .ok_or_else(|| fail(format!("missing advance U+{:04X}", ch as u32)))?;
        glyphs.push(Glyph {
            codepoint: ch as u32,
            glyph_id: gid.to_u32(),
            advance_26_6: fixed(advance, config.metric_rounding),
            left,
            top,
            width,
            height,
            pixels,
        });
    }
    if glyphs.is_empty() {
        return Err(fail("repertoire contains no available glyphs"));
    }
    let kerning = spacing::extract(data, config, &glyphs)?;
    Ok(GeneratedFont {
        source_sha256: format!("{:x}", Sha256::digest(data)),
        config: config.clone(),
        metrics: FontMetrics {
            ascent_26_6: fixed(metrics.ascent, config.metric_rounding),
            descent_26_6: fixed(metrics.descent, config.metric_rounding),
            line_gap_26_6: fixed(metrics.leading, config.metric_rounding),
        },
        glyphs,
        missing_codepoints,
        kerning,
    })
}
pub(crate) fn validate_config(c: &Config) -> Result<(), Error> {
    if !c.size_px.is_finite() || !(1.0..=512.0).contains(&c.size_px) {
        return Err(fail("size_px must be finite and within 1..=512"));
    }
    if !matches!(c.output_bits, 1 | 2 | 3 | 4 | 8) {
        return Err(fail("output_bits must be 1, 2, 3, 4 or 8"));
    }
    if c.mono_threshold == 0 {
        return Err(fail("mono_threshold must be within 1..=255"));
    }
    if !c.gray_gamma.is_finite() || c.gray_gamma <= 0.0 {
        return Err(fail("gray_gamma must be finite and positive"));
    }
    let count = c.characters.chars().collect::<BTreeSet<_>>().len();
    if !(1..=1024).contains(&count) {
        return Err(fail(
            "select between 1 and 1024 distinct characters per generation",
        ));
    }
    Ok(())
}
