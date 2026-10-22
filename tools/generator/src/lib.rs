//! Deterministic outline glyph generation, independent of display and output adapters.
//! Metrics use signed 26.6 pixels. Bitmaps contain unpacked coverage levels, row-major.
pub mod baseline;
pub mod batch;
#[cfg(feature = "candidate")]
pub mod candidate;
#[cfg(feature = "native-io")]
pub mod comparison;
#[cfg(feature = "candidate")]
pub mod diagonal_fitting;
pub mod dropout;
pub mod evaluation;
#[cfg(feature = "candidate")]
pub mod fitting_source;
#[cfg(feature = "candidate")]
pub(crate) mod font_hints;
#[cfg(feature = "candidate")]
pub(crate) mod font_scan;
pub mod layout_spacing;
pub mod metadata;
#[cfg(feature = "candidate")]
pub mod mono;
pub mod mono_spacing;
#[cfg(feature = "candidate")]
pub mod overlap;
#[cfg(feature = "candidate")]
mod selective_fitting;
/// Compatibility name for earlier diagnostic callers; renderer selection uses roles.
#[cfg(feature = "candidate")]
pub use candidate as iteration;
pub mod preview_selection;
pub mod probe;
mod raster;
pub mod reference;
pub mod renderer;
pub(crate) mod source;
#[cfg(feature = "candidate")]
pub mod source_width;
mod spacing;
pub use spacing::{ascii_kerning_pairs, AsciiKerning};
#[cfg(feature = "native-io")]
pub mod specimen_config;
#[cfg(feature = "native-io")]
pub mod specimens;
pub mod stem_fitting;
pub mod surface;
#[cfg(feature = "candidate")]
pub mod terminal_caps;

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

/// Upstream monochrome dropout correction, VER-2-15-0
/// `include/freetype/ftimage.h` `FT_OUTLINE_*` flags. Smart is the pinned
/// default; Simple selects plain dropout control; Off ignores dropouts
/// (upstream then also ignores stub control).
#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum MonoDropoutMode {
    Off,
    Simple,
    #[default]
    Smart,
}

/// Monochrome scan policy; manual controls remain the fallback when no
/// embedded TrueType interpreter produces scan state.
#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields, default)]
pub struct MonoRasterSettings {
    pub dropout: MonoDropoutMode,
    pub include_stubs: bool,
    pub font_instructions: bool,
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
    /// Scan-converter overrides; default reproduces the pinned smart-dropout,
    /// stub-excluded scan. Only the candidate Mono path applies non-defaults.
    #[serde(default)]
    pub mono_raster: MonoRasterSettings,
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
            mono_raster: MonoRasterSettings::default(),
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
/// Coordinate-dependent one-to-one scalar substitutions resolve through the
/// shaper at the exact axes; outlines, advances and `glyph_id` use the
/// selected glyph while Unicode identity is preserved. Pair positioning is
/// accepted only when representable as a left advance change.
pub fn generate(data: &[u8], config: &Config) -> Result<GeneratedFont, Error> {
    validate_config(config)?;
    require_default_mono_raster(config)?;
    let font = open_font(data)?;
    validate_axes(&font, &config.axes)?;
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
    // Approved dropout applies only to an actually enabled Mono automatic
    // instance: both setters must accept, so AutoFallback resolving to the
    // embedded interpreter, like gray/None/Interpreter, retains upstream
    // identity. Never infer enablement from the requested hinting mode alone.
    let mut dropout_enabled = false;
    if config.output_bits == 1 && matches!(config.hinting, Hinting::Auto | Hinting::AutoFallback) {
        if let Some(instance) = hinting.as_mut() {
            if instance.set_diagonal_constraints(true) {
                if !instance.set_diagonal_stem_relative(true) {
                    return Err(fail("accepted diagonal width policy could not be enabled"));
                }
                dropout_enabled = true;
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
    let mut present = Vec::new();
    for ch in config.characters.chars().collect::<BTreeSet<_>>() {
        // Missing-glyph policy covers unassigned scalars; controls and text-run
        // shaping requests remain capability errors even when absent in cmap.
        spacing::validate_request(ch)?;
        if font.charmap().map(ch).is_none_or(|g| g.to_u32() == 0) {
            if config.missing_glyphs == MissingGlyphs::Error {
                return Err(fail(format!("missing glyph U+{:04X}", ch as u32)));
            }
            missing_codepoints.push(ch as u32);
            continue;
        };
        spacing::validate_character(ch)?;
        present.push(ch);
    }
    // One reusable shaper resolves every scalar to the glyph actually drawn
    // at these axes (coordinate-dependent single substitutions included);
    // outlines, metrics and kerning below all use the selected glyph.
    let resolved = spacing::resolve_scalars(data, &config.axes, config.kerning, &present)?;
    for scalar in &resolved {
        let ch = char::from_u32(scalar.codepoint).unwrap();
        let gid = production_skrifa::GlyphId::new(scalar.glyph_id);
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
        let (pixels, left, top, width, height) =
            raster::render(pen.commands(), config, dropout_enabled)?;
        // Linear advances share the same variation coordinates as the shaper;
        // pixel rounding is applied once, explicitly, to the output metric.
        let advance = advances
            .advance_width(gid)
            .ok_or_else(|| fail(format!("missing advance U+{:04X}", ch as u32)))?;
        let advance_26_6 = fixed(advance, config.metric_rounding);
        glyphs.push(Glyph {
            codepoint: ch as u32,
            glyph_id: scalar.glyph_id,
            advance_26_6,
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
    let kerning = spacing::extract(data, config, &resolved)?;
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
    validate_settings(c)?;
    let count = c.characters.chars().collect::<BTreeSet<_>>().len();
    if !(1..=1024).contains(&count) {
        return Err(fail(
            "select between 1 and 1024 distinct characters per generation",
        ));
    }
    Ok(())
}
/// Numeric generation settings without the repertoire count, so adapters can
/// validate blank requests that carry no characters.
pub(crate) fn validate_settings(c: &Config) -> Result<(), Error> {
    if !c.size_px.is_finite() || !(1.0..=512.0).contains(&c.size_px) {
        return Err(fail("size_px must be finite and within 1..=512"));
    }
    if !matches!(c.output_bits, 1 | 2 | 3 | 4 | 8) {
        return Err(fail("output_bits must be 1, 2, 3, 4 or 8"));
    }
    if c.mono_threshold == 0 {
        return Err(fail("mono_threshold must be within 1..=255"));
    }
    if c.output_bits != 1 && c.mono_raster != MonoRasterSettings::default() {
        return Err(fail("mono raster settings require output_bits 1"));
    }
    if !c.gray_gamma.is_finite() || c.gray_gamma <= 0.0 {
        return Err(fail("gray_gamma must be finite and positive"));
    }
    Ok(())
}
/// Explicit scan overrides apply only through the candidate monochrome
/// scanner. Every other 1-bit renderer uses coverage, so it must fail
/// rather than silently ignore them. Non-1-bit depths are rejected in
/// `validate_settings`.
pub(crate) fn require_default_mono_raster(c: &Config) -> Result<(), Error> {
    if c.mono_raster != MonoRasterSettings::default() {
        return Err(fail(
            "mono raster settings require the candidate monochrome scanner",
        ));
    }
    Ok(())
}
/// Raw font acceptance shared with `generate()`: single sfnt outline font
/// with supported glyph outlines and no color tables.
pub(crate) fn open_font(data: &[u8]) -> Result<FontRef<'_>, Error> {
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
    Ok(font)
}
/// Variation-axis validation shared with `generate()`.
pub(crate) fn validate_axes(font: &FontRef, axes: &BTreeMap<String, f32>) -> Result<(), Error> {
    for (tag, value) in axes {
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
    Ok(())
}
