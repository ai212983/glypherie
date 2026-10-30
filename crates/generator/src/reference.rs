use crate::{
    fail, fixed,
    probe::{
        lock_sha256, rasterize, skrifa_checksum, skrifa_version, zeno_version, FittedCommand,
        FittedPen,
    },
    validate_config, Config, Error, FontMetrics, Hinting, MonoRasterSettings,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use skrifa::{
    instance::Size,
    outline::{DrawSettings, Engine, HintingInstance, HintingOptions, SmoothMode, Target},
    FontRef, MetadataProvider,
};
use std::{
    borrow::Cow,
    cell::OnceCell,
    collections::{BTreeMap, BTreeSet},
};

#[cfg(any(feature = "candidate", test))]
use std::{cell::RefCell, rc::Rc};

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
    /// Pinned scanner identity; absent for coverage-based renderers.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mono_rasterizer: Option<MonoRasterizer>,
    /// Effective scan-converter settings; present only for FreeType Mono
    /// records so reference/baseline/Gray captures stay byte-identical.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mono_raster: Option<MonoRasterSettings>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub font_scan: Option<FontScanState>,
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
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source_commands: Option<Vec<FittedCommand>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub width_fitting: Option<SourceWidthCapture>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub selective_fitting: Option<SelectiveFittingCapture>,
    // Width-only diagonal fitting input: upstream outline, native axes and
    // core reason. Present only on changed records; evaluator replays from
    // source/upstream rather than reusing `width_fitting`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub diagonal_fitting: Option<DiagonalFittingCapture>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub top_alignment: Option<TopAlignmentCapture>,
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

#[derive(Clone, Debug, Serialize)]
pub struct SourceWidthCapture {
    pub size_px: f32,
    pub upstream_commands: Vec<FittedCommand>,
}

#[derive(Clone, Debug, Serialize)]
pub struct TopAlignmentCapture {
    pub model: String,
    pub size_px: f32,
    pub source_ref_px: f64,
    pub target_px: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cap_height_px: Option<f64>,
    pub upstream_commands: Vec<FittedCommand>,
    pub contours: Vec<usize>,
    pub excess_px: f64,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub mark_translations: Vec<(usize, f64)>,
}

#[derive(Clone, Debug, Serialize)]
pub struct DiagonalFittingCapture {
    pub model: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub raw_source: Option<serde_json::Value>,
    pub upstream_commands: Vec<FittedCommand>,
    pub native_axes: [bool; 2],
    pub reason: String,
    pub size_px: f64,
    // Core `Reference` as JSON value: the baseline build has no core type.
    pub reference: serde_json::Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub upright_stem: Option<serde_json::Value>,
    // Applied source-shape provenance for `diagonal-shape-06` captures:
    // the kernel prototype carrying the public stage identity and the
    // kernel identity. Present only with the shape stage reason; absent on
    // every older packet and on new non-shape captures, never populated
    // under the legacy field.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source_shape: Option<serde_json::Value>,
}

#[derive(Clone, Debug, Serialize)]
pub struct SelectiveFittingCapture {
    pub native_axes: [bool; 2],
    pub native_commands: Vec<FittedCommand>,
    pub automatic_commands: Vec<FittedCommand>,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct MonoRasterizer {
    pub version: String,
    pub source_sha256: String,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct FontScanState {
    pub source_sha256: String,
    pub enabled: bool,
    pub scan_type: u16,
    pub contour_modes: Vec<Option<u8>>,
    pub hinting_axes: [bool; 2],
}
#[cfg(feature = "candidate")]
impl MonoRasterizer {
    pub fn current() -> Self {
        Self {
            version: crate::mono::VERSION.into(),
            source_sha256: crate::mono::SOURCE_SHA256.into(),
        }
    }
}

#[derive(Clone, Copy, Debug, Default, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RasterPolicy {
    #[default]
    Coverage,
    CoverageDropout,
    CoverageOverlap4xDropout,
    FreeTypeMono,
    FreeTypeMonoTerminals,
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
    /// Candidate-only pinned monochrome scanner; other captures keep coverage.
    pub mono_scanner: bool,
    /// Candidate-only `FontHintsFirst` fallback: use upstream automatic Mono
    /// fitting for fonts verified to carry no hint programs. The requested
    /// policy name is unchanged; only the resolved engine differs. Every
    /// other capture leaves this false and keeps upstream selection.
    pub force_auto: bool,
    pub implementation: String,
    pub fork: bool,
    pub extensions: String,
}

pub fn reference(data: &[u8], request: &ReferenceRequest) -> Result<ReferenceReport, Error> {
    CaptureSession::new(data).reference(request)
}

// A render owns its source preparation scope. Loaded immutable fonts also
// lend their byte identity and exact completed-fit cache across requests:
// https://doc.rust-lang.org/std/cell/struct.OnceCell.html
pub(crate) struct CaptureSession<'a> {
    pub(crate) data: &'a [u8],
    source_sha256: Cow<'a, OnceCell<String>>,
    #[cfg(feature = "candidate")]
    pub(crate) diagonal_fits: Option<&'a RefCell<crate::diagonal_fitting::reuse::FitCache>>,
    #[cfg(any(feature = "candidate", test))]
    sources: RefCell<Vec<(ReferenceRequest, Rc<OutlineCapture>)>>,
}

#[cfg(any(feature = "candidate", test))]
pub(crate) struct OutlineCapture {
    pub(crate) records: Vec<OutlineRecord>,
    pub(crate) missing_codepoints: Vec<u32>,
}

#[cfg(any(feature = "candidate", test))]
pub(crate) struct OutlineRecord {
    pub(crate) codepoint: u32,
    pub(crate) glyph_id: u32,
    pub(crate) fitted_commands: Vec<FittedCommand>,
}

impl<'a> CaptureSession<'a> {
    pub(crate) fn new(data: &'a [u8]) -> Self {
        Self {
            data,
            source_sha256: Cow::Owned(OnceCell::new()),
            #[cfg(feature = "candidate")]
            diagonal_fits: None,
            #[cfg(any(feature = "candidate", test))]
            sources: RefCell::new(Vec::new()),
        }
    }

    pub(crate) fn from_font(font: &'a crate::source::PreparedFont) -> Self {
        Self {
            data: font.as_bytes(),
            source_sha256: Cow::Borrowed(&font.identity),
            #[cfg(feature = "candidate")]
            diagonal_fits: Some(&font.diagonal_fits),
            #[cfg(any(feature = "candidate", test))]
            sources: RefCell::new(Vec::new()),
        }
    }

    pub(crate) fn source_sha256(&self) -> &str {
        self.source_sha256.get_or_init(|| {
            #[cfg(test)]
            crate::source::raster_counter::record_font_identity_hash();
            format!("{:x}", Sha256::digest(self.data))
        })
    }

    #[cfg(any(feature = "candidate", test))]
    pub(crate) fn source(&self, request: &ReferenceRequest) -> Result<Rc<OutlineCapture>, Error> {
        let mut request = request.clone();
        request.extensions = EXTENSIONS_NONE.into();
        request.settings.hinting = Hinting::None;
        request.settings.mono_raster = Default::default();
        if let Some((_, capture)) = self
            .sources
            .borrow()
            .iter()
            .find(|(key, _)| key == &request)
        {
            return Ok(Rc::clone(capture));
        }
        let (selected, policy) = reference_policy(&request)?;
        let batch = draw_with_policy(self.data, &request, &selected, &policy, |drawn, advance| {
            // Retain the same failures as the discarded source raster,
            // including bounds and advance checks, before retaining commands.
            crate::probe::validate_raster_bounds(&drawn.commands)?;
            advance.ok_or_else(|| fail(format!("missing advance U+{:04X}", drawn.codepoint)))?;
            Ok(OutlineRecord {
                codepoint: drawn.codepoint,
                glyph_id: drawn.glyph_id,
                fitted_commands: drawn.commands,
            })
        })?;
        let capture = Rc::new(OutlineCapture {
            records: batch.records,
            missing_codepoints: batch.missing_codepoints,
        });
        self.sources
            .borrow_mut()
            .push((request, Rc::clone(&capture)));
        Ok(capture)
    }

    pub(crate) fn reference(&self, request: &ReferenceRequest) -> Result<ReferenceReport, Error> {
        let (selected, policy) = reference_policy(request)?;
        self.capture(request, &selected, &policy)
    }
}

fn reference_policy(request: &ReferenceRequest) -> Result<(String, CapturePolicy), Error> {
    let config = &request.settings;
    validate_config(config)?;
    crate::require_default_mono_raster(config)?;
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
        mono_scanner: false,
        force_auto: false,
        implementation: String::from(IMPLEMENTATION_UPSTREAM),
        fork: false,
        extensions: request.extensions.clone(),
    };
    Ok((selected, policy))
}

impl CaptureSession<'_> {
    pub(crate) fn capture(
        &self,
        request: &ReferenceRequest,
        selected: &str,
        policy: &CapturePolicy,
    ) -> Result<ReferenceReport, Error> {
        let config = &request.settings;
        let target_name = &policy.target_name;
        let batch = draw_with_policy(self.data, request, selected, policy, |drawn, advance| {
            let fitted = drawn.commands;
            let font_scan = drawn.font_scan;
            let output = if policy.mono_scanner {
                #[cfg(feature = "candidate")]
                {
                    crate::mono::rasterize_with_scan_state(&fitted, config, font_scan.as_ref())?
                }
                #[cfg(not(feature = "candidate"))]
                {
                    return Err(fail("FreeType mono raster requires the candidate feature"));
                }
            } else if policy.dropout {
                crate::dropout::rasterize(&fitted, config)?
            } else {
                rasterize(&fitted, config)?
            };
            let advance = advance
                .ok_or_else(|| fail(format!("missing advance U+{:04X}", drawn.codepoint)))?;
            let advance_26_6 = fixed(advance, config.metric_rounding);
            Ok(ReferenceRecord {
                side_bearing_deltas_26_6: drawn.side_bearing_deltas,
                raster_policy: if policy.mono_scanner {
                    RasterPolicy::FreeTypeMono
                } else if policy.dropout {
                    RasterPolicy::CoverageDropout
                } else {
                    RasterPolicy::Coverage
                },
                mono_rasterizer: {
                    #[cfg(feature = "candidate")]
                    {
                        policy.mono_scanner.then(MonoRasterizer::current)
                    }
                    #[cfg(not(feature = "candidate"))]
                    {
                        None
                    }
                },
                mono_raster: policy.mono_scanner.then(|| config.mono_raster),
                font_scan,
                diagonal_pairs: None,
                codepoint: drawn.codepoint,
                glyph_id: drawn.glyph_id,
                selected_engine: drawn.selected_engine,
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
                source_commands: None,
                width_fitting: None,
                selective_fitting: None,
                top_alignment: None,
                diagonal_fitting: None,
                coverage_sha256: format!("{:x}", Sha256::digest(&output.coverage)),
                coverage: output.coverage,
                left: output.left,
                top: output.top,
                width: output.width,
                height: output.height,
                pixels: output.pixels,
                advance_26_6,
                hinted_has_overlaps: drawn.has_overlaps,
                hinted_lsb: drawn.lsb,
                hinted_advance_width: drawn.advance_width,
            })
        })?;
        Ok(ReferenceReport {
            advance_policy: AdvancePolicy::Linear,
            source_sha256: self.source_sha256().to_owned(),
            size_px: config.size_px,
            axes: config.axes.clone(),
            profile: request.profile.clone(),
            extensions: policy.extensions.clone(),
            hinting_requested: batch.requested,
            target: policy.target_name.clone(),
            smooth_mode: policy.smooth_mode.clone(),
            symmetric_rendering: policy.symmetric_rendering,
            preserve_linear_metrics: policy.preserve_linear_metrics,
            draw_pedantic: false,
            implementation: {
                #[cfg(feature = "candidate")]
                if batch.uses_scan_fitter {
                    format!(
                        "{}:scan-metadata:{}",
                        policy.implementation,
                        crate::font_scan::SOURCE_SHA256
                    )
                } else {
                    policy.implementation.clone()
                }
                #[cfg(not(feature = "candidate"))]
                {
                    policy.implementation.clone()
                }
            },
            fork: {
                #[cfg(feature = "candidate")]
                {
                    policy.fork || batch.uses_scan_fitter
                }
                #[cfg(not(feature = "candidate"))]
                {
                    policy.fork
                }
            },
            skrifa_version: skrifa_version(),
            skrifa_registry_checksum: skrifa_checksum(),
            zeno_version: zeno_version(),
            dependency_lock_sha256: lock_sha256(),
            metrics: batch.metrics,
            missing_codepoints: batch.missing_codepoints,
            records: batch.records,
        })
    }
}

struct DrawnOutline {
    codepoint: u32,
    glyph_id: u32,
    commands: Vec<FittedCommand>,
    selected_engine: String,
    font_scan: Option<FontScanState>,
    has_overlaps: bool,
    lsb: Option<f32>,
    advance_width: Option<f32>,
    side_bearing_deltas: Option<[i32; 2]>,
}

struct OutlineBatch<R> {
    requested: String,
    #[cfg(feature = "candidate")]
    uses_scan_fitter: bool,
    metrics: FontMetrics,
    missing_codepoints: Vec<u32>,
    records: Vec<R>,
}

// Skrifa's HintingInstance fixes font/size/location/target while a batch is
// drawn. The callback separates outline capture from scan conversion without
// changing engine state, draw order or adjusted metrics.
fn draw_with_policy<R>(
    data: &[u8],
    request: &ReferenceRequest,
    selected: &str,
    policy: &CapturePolicy,
    mut record: impl FnMut(DrawnOutline, Option<f32>) -> Result<R, Error>,
) -> Result<OutlineBatch<R>, Error> {
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
        Hinting::AutoFallback if policy.force_auto => Some(Engine::Auto(None)),
        Hinting::AutoFallback => Some(Engine::AutoFallback),
        Hinting::None => None,
    };
    let selected = if config.hinting == Hinting::AutoFallback {
        if policy.force_auto {
            "auto"
        } else if outlines.prefer_interpreter() {
            "interpreter"
        } else {
            "auto"
        }
    } else {
        selected
    }
    .to_string();
    // Snapshot path serves candidate automatic Mono only: the reference
    // stays independent and scanner choice never selects the fitter.
    #[cfg(feature = "candidate")]
    let snapshot_auto_mono = matches!(&engine, Some(Engine::Auto(_)))
        && policy.target_name == "mono"
        && policy.extensions != EXTENSIONS_NONE;
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
    #[cfg(feature = "candidate")]
    let scan_fitter =
        if policy.mono_scanner && config.mono_raster.font_instructions && selected == "interpreter"
        {
            crate::font_scan::FontScanFitter::new(data, config)?
        } else {
            None
        };
    #[cfg(feature = "candidate")]
    let auto_fitter = if snapshot_auto_mono {
        crate::font_scan::AutoFitter::new(data, config)?
    } else {
        None
    };
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
        #[cfg(feature = "candidate")]
        let (has_overlaps, lsb, advance_width, font_scan, side_bearing_deltas) =
            if let Some(fitter) = &auto_fitter {
                let metrics = fitter.draw(scalar.glyph_id, &mut pen)?;
                (
                    metrics.has_overlaps,
                    metrics.lsb,
                    metrics.advance_width,
                    None,
                    metrics.autohint_deltas_26_6,
                )
            } else if let Some(fitter) = &scan_fitter {
                let (adjusted, scan) = fitter.draw(scalar.glyph_id, &mut pen)?;
                (
                    adjusted.has_overlaps,
                    adjusted.lsb,
                    adjusted.advance_width,
                    scan,
                    None,
                )
            } else {
                let adjusted = outline
                    .draw(settings, &mut pen)
                    .map_err(|e| fail(format!("outline U+{:04X}: {e}", ch as u32)))?;
                (
                    adjusted.has_overlaps,
                    adjusted.lsb,
                    adjusted.advance_width,
                    None,
                    None,
                )
            };
        #[cfg(not(feature = "candidate"))]
        let (has_overlaps, lsb, advance_width, font_scan, side_bearing_deltas) = {
            let adjusted = outline
                .draw(settings, &mut pen)
                .map_err(|e| fail(format!("outline U+{:04X}: {e}", ch as u32)))?;
            (
                adjusted.has_overlaps,
                adjusted.lsb,
                adjusted.advance_width,
                None,
                None,
            )
        };
        let fitted = pen.into_commands();
        records.push(record(
            DrawnOutline {
                codepoint: ch as u32,
                glyph_id: scalar.glyph_id,
                commands: fitted,
                selected_engine: selected.clone(),
                font_scan,
                has_overlaps,
                lsb,
                advance_width,
                side_bearing_deltas,
            },
            advances.advance_width(gid),
        )?);
    }
    if records.is_empty() {
        return Err(fail("repertoire contains no available glyphs"));
    }
    Ok(OutlineBatch {
        requested,
        #[cfg(feature = "candidate")]
        uses_scan_fitter: scan_fitter.is_some() || auto_fitter.is_some(),
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

    fn bits(commands: &[FittedCommand]) -> Vec<(u8, Vec<u32>)> {
        use FittedCommand::*;
        commands
            .iter()
            .map(|command| match *command {
                MoveTo(x, y) => (0, vec![x.to_bits(), y.to_bits()]),
                LineTo(x, y) => (1, vec![x.to_bits(), y.to_bits()]),
                QuadTo(a, b, x, y) => (2, vec![a.to_bits(), b.to_bits(), x.to_bits(), y.to_bits()]),
                CurveTo(a, b, c, d, x, y) => (
                    3,
                    vec![
                        a.to_bits(),
                        b.to_bits(),
                        c.to_bits(),
                        d.to_bits(),
                        x.to_bits(),
                        y.to_bits(),
                    ],
                ),
                Close => (4, vec![]),
            })
            .collect()
    }

    #[test]
    fn outline_capture_matches_reference_across_request_changes() {
        // Both paths use Skrifa's unhinted drawing convention. Exact f32 bits
        // matter: source precision participates in feature predicates. Change
        // repertoire, size, axes and missing-glyph policy inside one scope to
        // detect accidental reuse of a different source request.
        for name in ["Roboto", "SourceSans3", "RobotoFlex", "Literata"] {
            let data = std::fs::read(
                std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                    .join(format!("../../fonts/{name}.ttf")),
            )
            .unwrap();
            let session = CaptureSession::new(&data);
            for (size, weight, characters) in [
                (12., 300., "x s 2"),
                (24., 700., "AyW"),
                (12., 300., "x s 2"),
                (16., 400., "A\u{10ffff}"),
            ] {
                let request = ReferenceRequest {
                    profile: PROFILE_MONO_1BIT.into(),
                    extensions: EXTENSIONS_NONE.into(),
                    settings: Config {
                        size_px: size,
                        axes: BTreeMap::from([("wght".into(), weight)]),
                        characters: characters.into(),
                        hinting: Hinting::None,
                        missing_glyphs: crate::MissingGlyphs::Skip,
                        ..Default::default()
                    },
                };
                let expected = reference(&data, &request).unwrap();
                let actual = session.source(&request).unwrap();
                assert_eq!(actual.missing_codepoints, expected.missing_codepoints);
                assert_eq!(actual.records.len(), expected.records.len());
                for (a, b) in actual.records.iter().zip(&expected.records) {
                    assert_eq!((a.codepoint, a.glyph_id), (b.codepoint, b.glyph_id));
                    assert_eq!(bits(&a.fitted_commands), bits(&b.fitted_commands));
                }
            }
            let request = ReferenceRequest {
                profile: PROFILE_MONO_1BIT.into(),
                extensions: EXTENSIONS_NONE.into(),
                settings: Config {
                    characters: "\u{10ffff}".into(),
                    hinting: Hinting::None,
                    ..Default::default()
                },
            };
            assert_eq!(
                session.source(&request).err().unwrap().to_string(),
                reference(&data, &request).err().unwrap().to_string()
            );
        }
    }
}
