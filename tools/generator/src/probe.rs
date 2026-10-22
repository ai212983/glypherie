use crate::{fail, fixed, validate_config, Config, Error, FontMetrics, Hinting};
use serde::{ser::SerializeMap, Serialize, Serializer};
use sha2::{Digest, Sha256};
use skrifa::{
    instance::Size,
    outline::{DrawSettings, Engine, HintingInstance, HintingOptions, OutlinePen, Target},
    FontRef, MetadataProvider,
};
use std::collections::{BTreeMap, BTreeSet};
use zeno::{Command, Format, Mask, Point};

const LOCK: &str = include_str!("../Cargo.lock");

pub fn lock_version(name: &str) -> String {
    let package = format!("name = \"{name}\"");
    let mut want = false;
    for line in LOCK.lines() {
        let line = line.trim();
        if line == package {
            want = true;
            continue;
        }
        if want && line.starts_with("version = \"") {
            return line
                .trim_start_matches("version = \"")
                .trim_end_matches('"')
                .to_string();
        }
        if line == "[[package]]" {
            want = false;
        }
    }
    String::from("unknown")
}

pub fn skrifa_version() -> String {
    env!("GENERATOR_SKRIFA_VERSION").into()
}

pub fn zeno_version() -> String {
    env!("GENERATOR_ZENO_VERSION").into()
}

pub fn lock_sha256() -> String {
    env!("GENERATOR_LOCK_SHA256").into()
}

pub fn lock_package_checksum(name: &str) -> String {
    let package = format!("name = \"{name}\"");
    let mut want = false;
    for line in LOCK.lines() {
        let line = line.trim();
        if line == package {
            want = true;
            continue;
        }
        if want && line.starts_with("checksum = \"") {
            return line
                .trim_start_matches("checksum = \"")
                .trim_end_matches('"')
                .to_string();
        }
        if line == "[[package]]" {
            want = false;
        }
    }
    String::from("unknown")
}

pub fn skrifa_checksum() -> String {
    env!("GENERATOR_SKRIFA_CHECKSUM").into()
}

#[derive(Clone, Debug, PartialEq)]
pub enum FittedCommand {
    MoveTo(f32, f32),
    LineTo(f32, f32),
    QuadTo(f32, f32, f32, f32),
    CurveTo(f32, f32, f32, f32, f32, f32),
    Close,
}

impl Serialize for FittedCommand {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        match *self {
            FittedCommand::MoveTo(x, y) => {
                let mut m = serializer.serialize_map(Some(5))?;
                m.serialize_entry("op", "move_to")?;
                m.serialize_entry("x", &x)?;
                m.serialize_entry("y", &y)?;
                m.serialize_entry("x_bits", &x.to_bits())?;
                m.serialize_entry("y_bits", &y.to_bits())?;
                m.end()
            }
            FittedCommand::LineTo(x, y) => {
                let mut m = serializer.serialize_map(Some(5))?;
                m.serialize_entry("op", "line_to")?;
                m.serialize_entry("x", &x)?;
                m.serialize_entry("y", &y)?;
                m.serialize_entry("x_bits", &x.to_bits())?;
                m.serialize_entry("y_bits", &y.to_bits())?;
                m.end()
            }
            FittedCommand::QuadTo(x1, y1, x, y) => {
                let mut m = serializer.serialize_map(Some(9))?;
                m.serialize_entry("op", "quad_to")?;
                m.serialize_entry("x1", &x1)?;
                m.serialize_entry("y1", &y1)?;
                m.serialize_entry("x", &x)?;
                m.serialize_entry("y", &y)?;
                m.serialize_entry("x1_bits", &x1.to_bits())?;
                m.serialize_entry("y1_bits", &y1.to_bits())?;
                m.serialize_entry("x_bits", &x.to_bits())?;
                m.serialize_entry("y_bits", &y.to_bits())?;
                m.end()
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                let mut m = serializer.serialize_map(Some(13))?;
                m.serialize_entry("op", "curve_to")?;
                m.serialize_entry("x1", &x1)?;
                m.serialize_entry("y1", &y1)?;
                m.serialize_entry("x2", &x2)?;
                m.serialize_entry("y2", &y2)?;
                m.serialize_entry("x", &x)?;
                m.serialize_entry("y", &y)?;
                m.serialize_entry("x1_bits", &x1.to_bits())?;
                m.serialize_entry("y1_bits", &y1.to_bits())?;
                m.serialize_entry("x2_bits", &x2.to_bits())?;
                m.serialize_entry("y2_bits", &y2.to_bits())?;
                m.serialize_entry("x_bits", &x.to_bits())?;
                m.serialize_entry("y_bits", &y.to_bits())?;
                m.end()
            }
            FittedCommand::Close => {
                let mut m = serializer.serialize_map(Some(1))?;
                m.serialize_entry("op", "close")?;
                m.end()
            }
        }
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct FittedPen {
    commands: Vec<FittedCommand>,
}

impl FittedPen {
    pub fn commands(&self) -> &[FittedCommand] {
        &self.commands
    }
    pub fn into_commands(self) -> Vec<FittedCommand> {
        self.commands
    }
}

impl OutlinePen for FittedPen {
    fn move_to(&mut self, x: f32, y: f32) {
        self.commands.push(FittedCommand::MoveTo(x, y));
    }
    fn line_to(&mut self, x: f32, y: f32) {
        self.commands.push(FittedCommand::LineTo(x, y));
    }
    fn quad_to(&mut self, x1: f32, y1: f32, x: f32, y: f32) {
        self.commands.push(FittedCommand::QuadTo(x1, y1, x, y));
    }
    fn curve_to(&mut self, x1: f32, y1: f32, x2: f32, y2: f32, x: f32, y: f32) {
        self.commands
            .push(FittedCommand::CurveTo(x1, y1, x2, y2, x, y));
    }
    fn close(&mut self) {
        self.commands.push(FittedCommand::Close);
    }
}

// The legacy comparison fork uses an older read-fonts pen trait. Forward
// commands into the same capture pen; no geometry is adapted or refitted.
impl skrifa_baseline::outline::OutlinePen for FittedPen {
    fn move_to(&mut self, x: f32, y: f32) {
        <Self as OutlinePen>::move_to(self, x, y);
    }
    fn line_to(&mut self, x: f32, y: f32) {
        <Self as OutlinePen>::line_to(self, x, y);
    }
    fn quad_to(&mut self, x1: f32, y1: f32, x: f32, y: f32) {
        <Self as OutlinePen>::quad_to(self, x1, y1, x, y);
    }
    fn curve_to(&mut self, x1: f32, y1: f32, x2: f32, y2: f32, x: f32, y: f32) {
        <Self as OutlinePen>::curve_to(self, x1, y1, x2, y2, x, y);
    }
    fn close(&mut self) {
        <Self as OutlinePen>::close(self);
    }
}

pub fn to_zeno(commands: &[FittedCommand]) -> Vec<Command> {
    let mut out = Vec::with_capacity(commands.len());
    for command in commands {
        match *command {
            FittedCommand::MoveTo(x, y) => out.push(Command::MoveTo(Point::new(x, -y))),
            FittedCommand::LineTo(x, y) => out.push(Command::LineTo(Point::new(x, -y))),
            FittedCommand::QuadTo(x1, y1, x, y) => {
                out.push(Command::QuadTo(Point::new(x1, -y1), Point::new(x, -y)))
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => out.push(Command::CurveTo(
                Point::new(x1, -y1),
                Point::new(x2, -y2),
                Point::new(x, -y),
            )),
            FittedCommand::Close => out.push(Command::Close),
        }
    }
    out
}

#[derive(Clone, Debug, Serialize)]
pub struct RasterOutput {
    pub pixels: Vec<u8>,
    pub coverage: Vec<u8>,
    pub left: i32,
    pub top: i32,
    pub width: u32,
    pub height: u32,
}

// Source-only captures retain exactly the raster path's rejection gates
// before omitting coverage generation. The outline is never delivered as a
// raster report; its commands feed fitting and independent replay only.
pub(crate) fn validate_raster_bounds(commands: &[FittedCommand]) -> Result<(), Error> {
    if commands.is_empty() {
        return Ok(());
    }
    let mut min = Point::new(f32::INFINITY, f32::INFINITY);
    let mut max = Point::new(f32::NEG_INFINITY, f32::NEG_INFINITY);
    let mut point = |p: Point| -> Result<(), Error> {
        if !p.x.is_finite() || !p.y.is_finite() || p.x.abs() > 32768.0 || p.y.abs() > 32768.0 {
            return Err(fail("outline coordinate exceeds supported bounds"));
        }
        min.x = min.x.min(p.x);
        min.y = min.y.min(p.y);
        max.x = max.x.max(p.x);
        max.y = max.y.max(p.y);
        Ok(())
    };
    for command in commands {
        match *command {
            FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => point(Point::new(x, -y))?,
            FittedCommand::QuadTo(x1, y1, x, y) => {
                point(Point::new(x1, -y1))?;
                point(Point::new(x, -y))?;
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                point(Point::new(x1, -y1))?;
                point(Point::new(x2, -y2))?;
                point(Point::new(x, -y))?;
            }
            FittedCommand::Close => {}
        }
    }
    let width = max.x.ceil() - min.x.floor();
    let height = max.y.ceil() - min.y.floor();
    if width * height > 4_194_304.0 {
        return Err(fail("glyph bitmap exceeds 4 Mi pixels"));
    }
    Ok(())
}

pub fn rasterize(commands: &[FittedCommand], config: &Config) -> Result<RasterOutput, Error> {
    #[cfg(test)]
    crate::source::raster_counter::record_logical(1);
    validate_raster_bounds(commands)?;
    if commands.is_empty() {
        return Ok(RasterOutput {
            pixels: vec![],
            coverage: vec![],
            left: 0,
            top: 0,
            width: 0,
            height: 0,
        });
    }
    let zeno = to_zeno(commands);
    let (coverage, placement) = Mask::new(zeno.as_slice()).format(Format::Alpha).render();
    let levels = (1u16 << config.output_bits) - 1;
    let pixels = coverage
        .iter()
        .map(|&v| {
            if config.output_bits == 1 {
                u8::from(v >= config.mono_threshold)
            } else {
                ((v as f32 / 255.0).powf(config.gray_gamma) * levels as f32).round() as u8
            }
        })
        .collect();
    Ok(RasterOutput {
        pixels,
        coverage,
        left: placement.left,
        top: placement.top,
        width: placement.width,
        height: placement.height,
    })
}

#[derive(Clone, Debug, Serialize)]
pub struct ProbeRecord {
    pub codepoint: u32,
    pub glyph_id: u32,
    pub selected_engine: String,
    pub target: String,
    pub draw_hinted: bool,
    pub skrifa_version: String,
    pub zeno_version: String,
    pub zeno_format: String,
    pub output_bits: u8,
    pub mono_threshold: u8,
    pub gray_gamma: f32,
    pub fitted_commands: Vec<FittedCommand>,
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

#[derive(Clone, Debug, Serialize)]
pub struct ProbeReport {
    pub source_sha256: String,
    pub size_px: f32,
    pub axes: BTreeMap<String, f32>,
    pub hinting_requested: String,
    pub skrifa_version: String,
    pub zeno_version: String,
    pub dependency_lock_sha256: String,
    pub metrics: FontMetrics,
    pub missing_codepoints: Vec<u32>,
    pub records: Vec<ProbeRecord>,
}

pub fn probe(data: &[u8], config: &Config) -> Result<ProbeReport, Error> {
    validate_config(config)?;
    crate::require_default_mono_raster(config)?;
    if config.output_bits != 1 {
        return Err(fail("probe requires output_bits exactly 1 for mono target"));
    }
    let requested = match config.hinting {
        Hinting::Auto => "auto",
        Hinting::Interpreter => "interpreter",
        _ => {
            return Err(fail(
                "probe requires explicit Hinting::Auto or Hinting::Interpreter",
            ));
        }
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
        Hinting::Auto => Engine::Auto(None),
        Hinting::Interpreter => Engine::Interpreter,
        _ => unreachable!(),
    };
    let hinting = HintingInstance::new(
        &outlines,
        size,
        &location,
        HintingOptions {
            engine,
            target: Target::Mono,
        },
    )
    .map_err(|e| fail(format!("hinting setup failed: {e}")))?;
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
    // Same coordinate-selected glyphs as generation and reference captures.
    let resolved = crate::spacing::resolve_scalars(data, &config.axes, config.kerning, &present)?;
    for scalar in &resolved {
        let ch = char::from_u32(scalar.codepoint).unwrap();
        let gid = skrifa::GlyphId::new(scalar.glyph_id);
        let outline = outlines
            .get(gid)
            .ok_or_else(|| fail(format!("missing outline U+{:04X}", ch as u32)))?;
        let mut pen = FittedPen::default();
        let adjusted = outline
            .draw(DrawSettings::hinted(&hinting, false), &mut pen)
            .map_err(|e| fail(format!("outline U+{:04X}: {e}", ch as u32)))?;
        let fitted = pen.into_commands();
        let output = rasterize(&fitted, config)?;
        let advance = advances
            .advance_width(gid)
            .ok_or_else(|| fail(format!("missing advance U+{:04X}", ch as u32)))?;
        let advance_26_6 = fixed(advance, config.metric_rounding);
        records.push(ProbeRecord {
            codepoint: ch as u32,
            glyph_id: scalar.glyph_id,
            selected_engine: requested.to_string(),
            target: String::from("mono"),
            draw_hinted: false,
            skrifa_version: skrifa_version(),
            zeno_version: zeno_version(),
            zeno_format: String::from("alpha"),
            output_bits: config.output_bits,
            mono_threshold: config.mono_threshold,
            gray_gamma: config.gray_gamma,
            fitted_commands: fitted,
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
    Ok(ProbeReport {
        source_sha256: format!("{:x}", Sha256::digest(data)),
        size_px: config.size_px,
        axes: config.axes.clone(),
        hinting_requested: requested.to_string(),
        skrifa_version: skrifa_version(),
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

#[cfg(test)]
mod preparation_tests {
    use super::*;

    #[test]
    fn build_provenance_matches_the_embedded_lock() {
        assert_eq!(skrifa_version(), lock_version("skrifa"));
        assert_eq!(zeno_version(), lock_version("zeno"));
        assert_eq!(skrifa_checksum(), lock_package_checksum("skrifa"));
        assert_eq!(lock_sha256(), format!("{:x}", Sha256::digest(LOCK)));
        assert_eq!(lock_version("nonexistent-package"), "unknown");
        assert_eq!(lock_package_checksum("nonexistent-package"), "unknown");
    }

    #[test]
    fn source_only_capture_retains_raster_rejection_boundaries() {
        // Source-only capture omits rendering, never its coordinate/allocation
        // gates. Exercise both sides of the coordinate limit and an area
        // excess; a valid zero-area outline still captures without ink.
        for (commands, error) in [
            (vec![FittedCommand::MoveTo(32768.0, -32768.0)], None),
            (
                vec![FittedCommand::MoveTo(32769.0, 0.0)],
                Some("outline coordinate exceeds supported bounds"),
            ),
            (
                vec![FittedCommand::QuadTo(0.0, f32::NAN, 0.0, 0.0)],
                Some("outline coordinate exceeds supported bounds"),
            ),
            (
                vec![FittedCommand::CurveTo(
                    0.0,
                    0.0,
                    f32::INFINITY,
                    0.0,
                    0.0,
                    0.0,
                )],
                Some("outline coordinate exceeds supported bounds"),
            ),
            (
                vec![
                    FittedCommand::MoveTo(-1024.0, -1024.0),
                    FittedCommand::LineTo(1025.0, 1025.0),
                ],
                Some("glyph bitmap exceeds 4 Mi pixels"),
            ),
        ] {
            assert_eq!(
                validate_raster_bounds(&commands)
                    .err()
                    .map(|e| e.to_string())
                    .as_deref(),
                error
            );
            assert_eq!(
                rasterize(&commands, &Config::default())
                    .err()
                    .map(|e| e.to_string())
                    .as_deref(),
                error
            );
        }
    }
}
