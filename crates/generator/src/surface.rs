//! Bounded multi-line text rendering over [`crate::generate`] output.
//!
//! Approved-path parity: glyph bitmaps, advances, kerning adjustments and metrics are
//! copied from `generate()` bit-for-bit. This adapter never refits, rescales or
//! reinterprets coverage levels; it only places, wraps, clips and composites.
//!
//! Coordinate invariant: the canvas is y-down RGBA with origin at the top-left.
//! A line baseline sits `ascent_px + index * line_height_px` from the top, where
//! `ascent_px` is the ceiling of `metrics.ascent_26_6 / 64` and `line_height_px`
//! mirrors the specimen layout, `((ascent - descent + gap) + 63) / 64` (min 1).
//! A glyph texel at bitmap `(gx, gy)` lands on canvas
//! `(pen_px + glyph.left + gx, baseline_px + glyph.top + gy)`; `pen_px` rounds
//! the 26.6 pen with `(pen + 32).div_euclid(64)`, matching specimen placement.
use crate::{
    fail,
    layout_spacing::{finalize_bitmap_metrics, EngineInputs, SpacingEngine},
    mono_spacing::font_spacing_properties,
    reference::CaptureSession,
    renderer::RendererRole,
    stem_fitting::StemFittingStrategy,
    Config, Error, GeneratedFont, Glyph, MissingGlyphs,
};
use std::borrow::Cow;
use std::collections::{BTreeSet, HashMap};

pub use crate::source::PreparedFont;

impl PreparedFont {
    /// Same validation and delivery as the raw-byte fitting entry point.
    /// Completed diagonal fits can be reused for identical geometric inputs.
    pub fn render_text_with_fitting_strategy(
        &self,
        request: &TextRenderRequest,
        role: RendererRole,
        letter_spacing_px: f32,
        strategy: Option<StemFittingStrategy>,
    ) -> Result<RenderedText, Error> {
        render_fitting_in_session(
            &CaptureSession::from_font(self),
            request,
            role,
            letter_spacing_px,
            strategy,
        )
    }

    /// Same explicit pipeline as the raw-byte entry point, with shared identity.
    pub fn render_text_with_pipeline_and_spacing(
        &self,
        request: &TextRenderRequest,
        pipeline: crate::renderer::RenderPipeline,
        letter_spacing_px: f32,
    ) -> Result<RenderedText, Error> {
        render_pipeline_in_session(
            &CaptureSession::from_font(self),
            request,
            pipeline,
            letter_spacing_px,
        )
    }
}

/// Maximum canvas width or height in pixels.
pub const MAX_CANVAS_DIM: u32 = 4096;
/// Maximum canvas texels (width * height); 16_777_216 texels bound the ~64MB buffer.
pub const MAX_CANVAS_TEXELS: u64 = 16_777_216;
/// Maximum accepted Unicode scalar count per request.
pub const MAX_TEXT_CHARS: usize = 8192;
/// Maximum distinct scalars per request; mirrors `generate()` repertoire validation.
pub const MAX_DISTINCT_CHARS: usize = 1024;

/// Horizontal overflow behavior.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum WrapMode {
    /// No wrapping; overlong runs are clipped at the canvas edge.
    Clip,
    /// Word wrap; an overlong word falls back to character breaks.
    Word,
    /// Break anywhere, including inside words.
    Char,
}

impl Default for WrapMode {
    fn default() -> Self {
        WrapMode::Word
    }
}

/// Horizontal alignment of each laid-out line within the canvas.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HAlign {
    /// Lines start at the left canvas edge.
    Left,
    /// Lines are centered; odd remainders truncate toward zero.
    Center,
    /// Line ends meet the right canvas edge.
    Right,
}

impl Default for HAlign {
    fn default() -> Self {
        HAlign::Left
    }
}

/// Bounded text render request.
#[derive(Clone, Debug, PartialEq)]
pub struct TextRenderRequest {
    /// Generation settings (size, axes, hinting, output depth, kerning, rounding,
    /// missing-glyph policy). `characters` is IGNORED: the repertoire is derived
    /// from `text` (minus newline separators) for every call.
    pub config: Config,
    /// Source text. Lines split on `\n`, `\r\n` and `\r`. Only
    /// Latin/Greek/Cyrillic/Common scalar glyphs plus pair kerning are supported;
    /// combining marks, controls/format characters (including tab) and other
    /// scripts are capability errors naming the codepoint. Empty text (or text of
    /// only newlines) yields a blank canvas with zero lines.
    pub text: String,
    /// Exact output canvas width in pixels, within 1..=4096.
    pub width: u32,
    /// Exact output canvas height in pixels, within 1..=4096.
    pub height: u32,
    /// Horizontal overflow behavior.
    pub wrap: WrapMode,
    /// Horizontal alignment within the canvas.
    pub align: HAlign,
    /// Glyph ink color, RGBA.
    pub foreground: [u8; 4],
    /// Canvas clear color, RGBA; transparency (`a < 255`) is supported.
    pub background: [u8; 4],
    /// Optional explicit color per coverage level. Entry `i` colors level `i`
    /// verbatim (its alpha is used as-is, with no coverage scaling); must hold
    /// exactly `1 << output_bits` entries. `None` maps every nonzero level to
    /// the constant foreground color; level 0 leaves the background untouched.
    /// These map coverage levels to colors; they are NOT native COLR color-font
    /// support (color fonts stay rejected by `generate()`).
    pub palette: Option<Vec<[u8; 4]>>,
}

/// One laid-out visual line.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RenderedLine {
    /// Byte offset into the request text of the first placed character.
    pub byte_start: usize,
    /// Byte offset one past the last placed character (excludes break
    /// whitespace and newline terminators); equals `byte_start` when empty.
    pub byte_end: usize,
    /// Total laid-out advance of the line in 26.6 pixels.
    pub width_26_6: i32,
    /// Line height in pixels (uniform across lines).
    pub height_px: u32,
}

/// Composited bounded text render.
///
/// Coverage compositing per texel with level `v` (`0..=levels - 1`,
/// `levels = 1 << output_bits`): the source color is the mapped entry for `v`
/// and its alpha is scaled once by coverage, `sa = map[v].a * coverage`,
/// where `coverage = v / (levels - 1)` for the default foreground mapping and
/// `coverage = 1` for an explicit palette (whose entries apply verbatim).
/// Standard source-over blends it onto the canvas texel
/// (`out_a = sa + da * (1 - sa)`,
/// `out_rgb = (src_rgb * sa + dst_rgb * da * (1 - sa)) / out_a`),
/// starting from the background. Level 0 is a no-op. Overlapping glyphs blend
/// in draw order (lines top-to-bottom, glyphs left-to-right).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RenderedText {
    /// Canvas width in pixels (equals the request width).
    pub width: u32,
    /// Canvas height in pixels (equals the request height).
    pub height: u32,
    /// RGBA row-major canvas, length `width * height * 4`.
    pub pixels: Vec<u8>,
    /// Visual lines in top-to-bottom order, including empty paragraph lines.
    pub lines: Vec<RenderedLine>,
    /// Codepoints skipped under the `Skip` missing-glyph policy, in sorted order.
    pub missing_codepoints: Vec<u32>,
}

/// Render bounded multi-line text with `generate()` glyphs.
///
/// See [`TextRenderRequest`] for capability limits and [`RenderedText`] for the
/// compositing formula. Validation runs before any large allocation, in order:
/// canvas bounds, text length, generation config (via `generate()`), palette
/// shape, then canvas allocation. Blank requests validate settings, font,
/// axes and palette before returning the background canvas.
pub fn render_text(font_data: &[u8], request: &TextRenderRequest) -> Result<RenderedText, Error> {
    render_inner(
        &CaptureSession::new(font_data),
        request,
        None,
        0.0,
        None,
        None,
    )
}

/// Render bounded multi-line text with an explicit stable renderer role.
///
/// `Baseline` is the approved production path: shaping, metrics, kerning and
/// bitmaps come from `generate()` unchanged, so this equals [`render_text`]
/// bit-for-bit. `Reference` keeps source layout and replaces monochrome
/// bitmaps. `Candidate` replaces Mono and Gray bitmaps with its capture and
/// lays out with the single bitmap policy: whole-pixel fitted advances and
/// whole-pixel pair adjustments. The role capture uses extensions `none`
/// for reference and `font-hints-01` by default for candidate. Preview
/// depths other than 1/3-bit, candidate hinting other than automatic, and
/// a candidate request without the `candidate` feature fail explicitly.
pub fn render_text_with_renderer(
    font_data: &[u8],
    request: &TextRenderRequest,
    role: RendererRole,
) -> Result<RenderedText, Error> {
    render_text_with_renderer_and_spacing(font_data, request, role, 0.0)
}

/// Preview tracking: add a signed pixel offset to every available glyph's
/// advance. Negative offsets preserve neutral ASCII word gaps; positive
/// offsets widen spaces too. Pair adjustments remain intact. Mono rounds
/// the offset to whole pixels and limits tightening so normally separated
/// source pairs retain a blank column. Fixed pitch, tabular digits and
/// intentional source overlaps bypass the pair floor. The candidate uses
/// whole-pixel tracking at any depth; baseline and reference Gray retain
/// fractional tracking with the same word-gap policy. Glyph outlines and
/// bitmaps never change. Line measurement and wrapping use the same
/// constrained advances.
pub fn render_text_with_renderer_and_spacing(
    font_data: &[u8],
    request: &TextRenderRequest,
    role: RendererRole,
    letter_spacing_px: f32,
) -> Result<RenderedText, Error> {
    render_inner(
        &CaptureSession::new(font_data),
        request,
        Some(role),
        letter_spacing_px,
        None,
        None,
    )
}

/// Render bounded multi-line text with an explicit renderer role, preview
/// tracking and selectable [`StemFittingStrategy`].
///
/// Layout is determined by role, not by a user-selectable spacing model:
/// baseline and reference keep source layout (fractional source advances
/// and source kerning); the working candidate uses the single bitmap
/// policy (whole-pixel advances and pair adjustments) for Mono and Gray.
/// `None` keeps the current default exactly: the candidate role renders
/// the `FontHintsFirst` (`font-hints-01`) fit. An explicit strategy routes
/// the candidate capture to that strategy's extension instead; anything
/// else is rejected before blank-text handling. A compatible blank request
/// produces the normal background canvas. Gray rejects an explicit
/// strategy; the default `None` gray path is unchanged in fitting.
pub fn render_text_with_fitting_strategy(
    font_data: &[u8],
    request: &TextRenderRequest,
    role: RendererRole,
    letter_spacing_px: f32,
    strategy: Option<StemFittingStrategy>,
) -> Result<RenderedText, Error> {
    render_fitting_in_session(
        &CaptureSession::new(font_data),
        request,
        role,
        letter_spacing_px,
        strategy,
    )
}

fn render_fitting_in_session(
    session: &CaptureSession<'_>,
    request: &TextRenderRequest,
    role: RendererRole,
    letter_spacing_px: f32,
    strategy: Option<StemFittingStrategy>,
) -> Result<RenderedText, Error> {
    #[cfg(not(feature = "candidate"))]
    if role == RendererRole::Candidate {
        return Err(fail(
            "candidate rendering requires the candidate Cargo feature",
        ));
    }
    if !letter_spacing_px.is_finite() || !(-16.0..=16.0).contains(&letter_spacing_px) {
        return Err(fail("letter_spacing_px must be finite and within -16..=16"));
    }
    // Explicit-strategy validation lives in `render_inner`, before blank
    // handling, so every entry point shares one gate.
    render_inner(
        session,
        request,
        Some(role),
        letter_spacing_px,
        strategy,
        None,
    )
}

/// Render explicit fitting and rasterization stages with one bitmap layout.
/// Tracking is neutral and cannot activate preview minimum-gap corrections.
/// The fitter's returned advances remain layout inputs; changing only the
/// scanner therefore cannot change advances, pair adjustments or wrapping.
pub fn render_text_with_pipeline(
    font_data: &[u8],
    request: &TextRenderRequest,
    pipeline: crate::renderer::RenderPipeline,
) -> Result<RenderedText, Error> {
    render_text_with_pipeline_and_spacing(font_data, request, pipeline, 0.0)
}

/// Render explicit fitting and rasterization stages with uniform tracking.
///
/// Bakes a signed whole-pixel step into every finalized advance, including
/// spaces and the final glyph advance; bitmaps, offsets and sparse pair
/// adjustments are unchanged, with no minimum-gap floor and no word-gap
/// refund. Zero is identity. Negative results are kept: tightening may
/// overlap. Only `i32` overflow fails.
pub fn render_text_with_pipeline_and_spacing(
    font_data: &[u8],
    request: &TextRenderRequest,
    pipeline: crate::renderer::RenderPipeline,
    letter_spacing_px: f32,
) -> Result<RenderedText, Error> {
    render_pipeline_in_session(
        &CaptureSession::new(font_data),
        request,
        pipeline,
        letter_spacing_px,
    )
}

fn render_pipeline_in_session(
    session: &CaptureSession<'_>,
    request: &TextRenderRequest,
    pipeline: crate::renderer::RenderPipeline,
    letter_spacing_px: f32,
) -> Result<RenderedText, Error> {
    pipeline.validate(&request.config)?;
    #[cfg(not(feature = "candidate"))]
    {
        let _ = (session, letter_spacing_px);
        Err(fail(
            "explicit pipeline requires the candidate Cargo feature",
        ))
    }
    #[cfg(feature = "candidate")]
    {
        let mut effective = request.clone();
        effective.config.hinting = if request.config.output_bits == 1 {
            pipeline.fitting.hinting()
        } else {
            crate::Hinting::Auto
        };
        render_inner(
            session,
            &effective,
            Some(RendererRole::Candidate),
            letter_spacing_px,
            (request.config.output_bits == 1).then_some(pipeline.fitting),
            Some(pipeline),
        )
    }
}

fn require_candidate_mono(
    config: &Config,
    role: Option<RendererRole>,
    requirement_clause: &'static str,
) -> Result<(), Error> {
    #[cfg(not(feature = "candidate"))]
    {
        let _ = (config, role);
        return Err(fail(format!(
            "{requirement_clause} the candidate Cargo feature"
        )));
    }
    #[cfg(feature = "candidate")]
    {
        if role != Some(RendererRole::Candidate) {
            return Err(fail(format!(
                "{requirement_clause} the candidate preview role"
            )));
        }
        if config.output_bits != 1 {
            return Err(fail(format!(
                "{requirement_clause} monochrome output_bits 1, got {}",
                config.output_bits
            )));
        }
        if !matches!(
            config.hinting,
            crate::Hinting::Auto | crate::Hinting::AutoFallback
        ) {
            return Err(fail(format!(
                "{requirement_clause} automatic hinting, got {:?}",
                config.hinting
            )));
        }
        Ok(())
    }
}

fn admit_request(
    request: &TextRenderRequest,
    role: Option<RendererRole>,
    letter_spacing_px: f32,
    strategy: Option<StemFittingStrategy>,
    pipeline: Option<crate::renderer::RenderPipeline>,
) -> Result<Cow<'_, TextRenderRequest>, Error> {
    if !letter_spacing_px.is_finite() || !(-16.0..=16.0).contains(&letter_spacing_px) {
        return Err(fail("letter_spacing_px must be finite and within -16..=16"));
    }
    // The Mono strategy owns automatic engine selection. Normalize the
    // effective configuration before validation, blank handling or generation
    // so report settings and layout provenance match the actual draw.
    let request = if role == Some(RendererRole::Candidate)
        && matches!(
            request.config.hinting,
            crate::Hinting::Auto | crate::Hinting::AutoFallback
        ) {
        let mut owned = request.clone();
        owned.config.hinting = if request.config.output_bits == 1 {
            strategy.unwrap_or_default().hinting()
        } else {
            crate::Hinting::Auto
        };
        Cow::Owned(owned)
    } else {
        Cow::Borrowed(request)
    };
    if !(1..=MAX_CANVAS_DIM).contains(&request.width) {
        return Err(fail("canvas width must be within 1..=4096"));
    }
    if !(1..=MAX_CANVAS_DIM).contains(&request.height) {
        return Err(fail("canvas height must be within 1..=4096"));
    }
    if u64::from(request.width) * u64::from(request.height) > MAX_CANVAS_TEXELS {
        return Err(fail("canvas exceeds 16777216 texels"));
    }
    if request.text.chars().count() > MAX_TEXT_CHARS {
        return Err(fail("text exceeds 8192 characters"));
    }
    // Historical preview roles keep the interactive 1/3-bit profiles; 2/4-bit
    // coverage stays on the explicit pipeline. Anything else fails here,
    // before any allocation, rather than rendering a nearby depth.
    if let Some(role @ (RendererRole::Reference | RendererRole::Candidate)) = role {
        let palette_coverage = pipeline.is_some() && matches!(request.config.output_bits, 2 | 4);
        if !matches!(request.config.output_bits, 1 | 3) && !palette_coverage {
            return Err(fail(format!(
                "preview role {} requires output_bits 1 or 3, got {}",
                role_name(role),
                request.config.output_bits
            )));
        }
        match (role, request.config.hinting) {
            (RendererRole::Candidate, crate::Hinting::Auto | crate::Hinting::AutoFallback) => {}
            (RendererRole::Reference, crate::Hinting::AutoFallback) => {
                return Err(fail(format!(
                    "preview role {} requires explicit hinting, got auto_fallback",
                    role_name(role)
                )));
            }
            (RendererRole::Candidate, other) => {
                return Err(fail(format!(
                    "preview role candidate requires automatic hinting, got {other:?}"
                )));
            }
            _ => {}
        }
    }
    // Validate explicit Mono options before the blank-text shortcut.
    if request.config.mono_raster != crate::MonoRasterSettings::default() {
        require_candidate_mono(&request.config, role, "mono raster settings require")?;
    }
    if strategy.is_some() {
        require_candidate_mono(&request.config, role, "explicit fitting strategy requires")?;
    }
    Ok(request)
}

/// Shared validation/layout/compositing pipeline behind [`render_text`]
/// and [`render_text_with_renderer`]; `None` and `Some(Baseline)` both
/// take the approved `generate()` path unchanged. All numerical spacing
/// decisions (finalized advances, single pair application, tracking and
/// the tracking floor) run through the [`SpacingEngine`] built below.
fn render_inner(
    session: &CaptureSession<'_>,
    request: &TextRenderRequest,
    role: Option<RendererRole>,
    letter_spacing_px: f32,
    strategy: Option<StemFittingStrategy>,
    pipeline: Option<crate::renderer::RenderPipeline>,
) -> Result<RenderedText, Error> {
    let font_data = session.data;
    let admitted = admit_request(request, role, letter_spacing_px, strategy, pipeline)?;
    let request = admitted.as_ref();
    let paragraphs = split_paragraphs(&request.text);
    let repertoire: BTreeSet<char> = request
        .text
        .chars()
        .filter(|c| *c != '\n' && *c != '\r')
        .collect();
    if repertoire.is_empty() {
        // Blank requests validate exactly what a rendered request would
        // check — settings, font bytes, axes and palette shape — before
        // allocating the canvas.
        crate::validate_settings(&request.config)?;
        let font = crate::open_font(font_data)?;
        crate::validate_axes(&font, &request.config.axes)?;
        let levels = 1u32 << request.config.output_bits;
        palette_map(&request.foreground, request.palette.as_deref(), levels)?;
        return blank(
            request.width,
            request.height,
            &request.background,
            Vec::new(),
        );
    }
    if repertoire.len() > MAX_DISTINCT_CHARS {
        return Err(fail(
            "select between 1 and 1024 distinct characters per generation",
        ));
    }
    // `characters` is derived from `text`; the request value is ignored.
    let mut config = request.config.clone();
    config.characters = repertoire.iter().collect();
    let is_candidate = role == Some(RendererRole::Candidate);
    let mono = config.output_bits == 1;
    // Candidate: source advances/kerning and line metrics come from
    // source preparation (no raster), then the fitted capture supplies
    // the one bitmap per unique character. Other roles keep the
    // approved `generate()` path unchanged; reference Mono swaps its
    // independently captured bitmaps over that output.
    let (generated, role_report) = if is_candidate {
        let source = match crate::source::prepare_source_in_session(session, &config) {
            Ok(source) => source,
            Err(error)
                if request.config.missing_glyphs == MissingGlyphs::Skip
                    && error.0 == "repertoire contains no available glyphs" =>
            {
                for ch in &repertoire {
                    crate::spacing::validate_request(*ch)?;
                }
                let levels = 1u32 << request.config.output_bits;
                palette_map(&request.foreground, request.palette.as_deref(), levels)?;
                let missing: Vec<u32> = repertoire.iter().map(|ch| *ch as u32).collect();
                return blank(request.width, request.height, &request.background, missing);
            }
            Err(error) => return Err(error),
        };
        let preview = crate::reference::ReferenceRequest {
            profile: if mono {
                crate::reference::PROFILE_MONO_1BIT.to_string()
            } else {
                crate::reference::PROFILE_GRAY_3BIT.to_string()
            },
            // Explicit pipelines stamp their own fitting; the legacy role
            // path keeps the strategy-derived default.
            extensions: StemFittingStrategy::extension(
                pipeline.map(|selected| selected.fitting).or(strategy),
            )
            .to_string(),
            settings: config.clone(),
        };
        let report = match pipeline {
            #[cfg(feature = "candidate")]
            Some(pipeline) => {
                crate::candidate::render_with_pipeline_in_session(session, &preview, pipeline)?
            }
            _ => {
                #[cfg(feature = "candidate")]
                {
                    crate::candidate::render_with_rasterization_in_session(
                        session,
                        &preview,
                        crate::renderer::Rasterization::FreeTypeMono,
                    )?
                }
                #[cfg(not(feature = "candidate"))]
                {
                    crate::renderer::render(font_data, &preview, RendererRole::Candidate)?
                }
            }
        };
        let source_advance_by_codepoint: HashMap<u32, i32> = source
            .glyphs
            .iter()
            .map(|glyph| (glyph.codepoint, glyph.advance_26_6))
            .collect();
        let mut glyphs = Vec::with_capacity(report.records.len());
        for record in &report.records {
            let advance = source_advance_by_codepoint
                .get(&record.codepoint)
                .copied()
                .ok_or_else(|| {
                    fail(format!("missing source advance U+{:04X}", record.codepoint))
                })?;
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
        let generated = GeneratedFont {
            source_sha256: source.source_sha256.clone(),
            config: config.clone(),
            metrics: source.metrics.clone(),
            glyphs,
            missing_codepoints: source.missing_codepoints.clone(),
            kerning: source.kerning.clone(),
        };
        (generated, Some(report))
    } else {
        let generated = match crate::generate(font_data, &config) {
            Ok(generated) => generated,
            Err(error)
                if request.config.missing_glyphs == MissingGlyphs::Skip
                    && error.0 == "repertoire contains no available glyphs" =>
            {
                // `generate()` validated settings, font, axes and
                // per-character shaping support before reporting the
                // empty repertoire; re-check shaping support here so
                // this path can never mask a capability error, then
                // report the sorted repertoire as skipped.
                for ch in &repertoire {
                    crate::spacing::validate_request(*ch)?;
                }
                let levels = 1u32 << request.config.output_bits;
                palette_map(&request.foreground, request.palette.as_deref(), levels)?;
                let missing: Vec<u32> = repertoire.iter().map(|ch| *ch as u32).collect();
                return blank(request.width, request.height, &request.background, missing);
            }
            Err(error) => return Err(error),
        };
        let mut generated = generated;
        let needs_report = matches!(role, Some(RendererRole::Reference)) && mono;
        let role_report = if needs_report {
            let selected_role = role.unwrap_or(RendererRole::Baseline);
            let preview = crate::reference::ReferenceRequest {
                profile: if mono {
                    crate::reference::PROFILE_MONO_1BIT.to_string()
                } else {
                    crate::reference::PROFILE_GRAY_3BIT.to_string()
                },
                extensions: crate::reference::EXTENSIONS_NONE.to_string(),
                settings: generated.config.clone(),
            };
            debug_assert_eq!(selected_role, RendererRole::Reference);
            Some(session.reference(&preview)?)
        } else {
            None
        };
        if let Some(report) = &role_report {
            swap_bitmaps(
                &mut generated,
                report,
                role.unwrap_or(RendererRole::Baseline),
            )?;
        }
        (generated, role_report)
    };
    // Source advances before any role swap; baseline and reference keep
    // them as their layout, while the candidate finalizes bitmap metrics
    // from its own capture below.
    let source_advances: HashMap<u32, i32> = generated
        .glyphs
        .iter()
        .map(|glyph| (glyph.codepoint, glyph.advance_26_6))
        .collect();
    let source_kern: HashMap<(u32, u32), i32> = generated
        .kerning
        .iter()
        .map(|k| ((k.left, k.right), k.adjustment_26_6))
        .collect();
    // Finalize the one layout this role consumes. The candidate resolves
    // fitted advances and pair adjustments to whole pixels once, here and
    // in the exported strike, so preview, measurement and wrapping cannot
    // diverge; other roles keep fractional source layout. The separated
    // pipeline instead bakes uniform whole-pixel tracking into those
    // advances and lays out with neutral engine tracking, so no
    // minimum-gap guard or word-gap refund can activate.
    let uniform = pipeline.is_some();
    let (advances, pair_adjustments, guard_kern, integer_positions) = if is_candidate {
        let report = role_report
            .as_ref()
            .ok_or_else(|| fail("candidate layout requires its fitted capture"))?;
        let properties = font_spacing_properties(font_data, &generated.config)?;
        // The one finalized bitmap table, resolved exactly as in the
        // exported strike; placement applies its pair values once.
        let finalized = finalize_bitmap_metrics(
            &report.records,
            &source_advances,
            &source_kern,
            generated.config.kerning,
            properties.monospace,
            properties.tabular_digits,
        );
        if uniform {
            let advances = crate::layout_spacing::apply_uniform_tracking(
                &finalized.advances_26_6,
                letter_spacing_px,
            )?;
            (
                advances,
                finalized.pair_adjustments_26_6,
                HashMap::new(),
                true,
            )
        } else {
            let guard = if generated.config.kerning {
                finalized.source_kern_26_6.clone()
            } else {
                HashMap::new()
            };
            (
                finalized.advances_26_6,
                finalized.pair_adjustments_26_6,
                guard,
                true,
            )
        }
    } else {
        let guard = if generated.config.kerning {
            source_kern.clone()
        } else {
            HashMap::new()
        };
        (source_advances.clone(), source_kern.clone(), guard, false)
    };
    // Uniform pipeline tracking already lives in the baked advances, so
    // the engine itself stays neutral and draws no source geometry.
    let engine_spacing = if uniform { 0.0 } else { letter_spacing_px };
    let tracking_26_6 =
        SpacingEngine::normalize_tracking_offset(mono || integer_positions, engine_spacing);
    // Nonzero Mono tracking needs only unhinted source extents:
    // geometry is drawn without any coverage or raster.
    let geometry = if mono && tracking_26_6 != 0 {
        Some(crate::mono_spacing::TrackingGuard::for_output_from_geometry(font_data, &generated)?)
    } else {
        None
    };
    let levels = 1u32 << generated.config.output_bits;
    let map = palette_map(&request.foreground, request.palette.as_deref(), levels)?;
    let glyphs: HashMap<u32, &Glyph> = generated.glyphs.iter().map(|g| (g.codepoint, g)).collect();
    // Bounded by repertoire^2 (<= 1024^2) via `generate()`; per-pair lookup is O(1).
    let engine = SpacingEngine::new(EngineInputs {
        advances_26_6: advances,
        pair_adjustments_26_6: pair_adjustments,
        guard_kern_26_6: guard_kern,
        minimum: geometry.as_ref(),
        mono,
        integer_positions,
        letter_spacing_px: engine_spacing,
    })?;
    let metrics = &generated.metrics;
    let line_height_px = ((i64::from(metrics.ascent_26_6) - i64::from(metrics.descent_26_6)
        + i64::from(metrics.line_gap_26_6)
        + 63)
        / 64)
        .max(1) as u32;
    let ascent_px = (i64::from(metrics.ascent_26_6) + 63).div_euclid(64);
    let limit_26_6 = i64::from(request.width) * 64;
    let layout = Layout {
        engine,
        wrap: request.wrap,
        limit_26_6,
    };
    let mut lines = Vec::new();
    for paragraph in &paragraphs {
        layout.layout_paragraph(paragraph, &mut lines)?;
    }
    let mut canvas = Canvas {
        width: request.width,
        height: request.height,
        levels,
        alpha_by_coverage: request.palette.is_none(),
        map,
        pixels: background_pixels(request.width, request.height, &request.background),
    };
    for (index, line) in lines.iter().enumerate() {
        let baseline = ascent_px + index as i64 * i64::from(line_height_px);
        canvas.draw_line(line, baseline, request.align, &glyphs)?;
    }
    let mut rendered = Vec::with_capacity(lines.len());
    for line in &lines {
        rendered.push(RenderedLine {
            byte_start: line.byte_start,
            byte_end: line.byte_end,
            width_26_6: line.width_26_6()?,
            height_px: line_height_px,
        });
    }
    Ok(RenderedText {
        width: request.width,
        height: request.height,
        pixels: canvas.pixels,
        lines: rendered,
        missing_codepoints: generated.missing_codepoints.clone(),
    })
}

/// Byte ranges of one paragraph slice within the request text.
struct Paragraph {
    start: usize,
    chars: Vec<(char, usize, usize)>,
}

/// Split on `\r\n` (one break), `\r` or `\n`, tracking byte offsets.
fn split_paragraphs(text: &str) -> Vec<Paragraph> {
    let mut paragraphs = Vec::new();
    let mut start = 0;
    let mut chars = Vec::new();
    let mut iter = text.char_indices().peekable();
    while let Some((index, ch)) = iter.next() {
        if ch == '\r' {
            if let Some((_, '\n')) = iter.peek() {
                iter.next();
            }
            paragraphs.push(Paragraph { start, chars });
            start = index
                + ch.len_utf8()
                + if text[index + ch.len_utf8()..].starts_with('\n') {
                    1
                } else {
                    0
                };
            chars = Vec::new();
        } else if ch == '\n' {
            paragraphs.push(Paragraph { start, chars });
            start = index + 1;
            chars = Vec::new();
        } else {
            chars.push((ch, index, ch.len_utf8()));
        }
    }
    paragraphs.push(Paragraph { start, chars });
    paragraphs
}

/// Blank canvas; callers pass the skipped codepoints, if any.
fn blank(
    width: u32,
    height: u32,
    background: &[u8; 4],
    missing_codepoints: Vec<u32>,
) -> Result<RenderedText, Error> {
    Ok(RenderedText {
        width,
        height,
        pixels: background_pixels(width, height, background),
        lines: Vec::new(),
        missing_codepoints,
    })
}

fn background_pixels(width: u32, height: u32, background: &[u8; 4]) -> Vec<u8> {
    let texels = width as usize * height as usize;
    let mut pixels = Vec::with_capacity(texels * 4);
    for _ in 0..texels {
        pixels.extend_from_slice(background);
    }
    pixels
}

/// Stable lowercase role name for capability errors.
fn role_name(role: RendererRole) -> &'static str {
    match role {
        RendererRole::Reference => "reference",
        RendererRole::Baseline => "baseline",
        RendererRole::Candidate => "candidate",
    }
}

/// Replace only each glyph's bitmap box with the role capture's record for
/// the same codepoint. Advances are finalized separately by role; glyph
/// ids, line metrics, source kerning and the skipped set remain shared.
fn swap_bitmaps(
    generated: &mut GeneratedFont,
    report: &crate::reference::ReferenceReport,
    role: RendererRole,
) -> Result<(), Error> {
    let bitmaps: HashMap<u32, _> = report
        .records
        .iter()
        .map(|record| (record.codepoint, record))
        .collect();
    for glyph in &mut generated.glyphs {
        let record = bitmaps.get(&glyph.codepoint).ok_or_else(|| {
            fail(format!(
                "preview role {} has no bitmap for U+{:04X}",
                role_name(role),
                glyph.codepoint
            ))
        })?;
        glyph.left = record.left;
        glyph.top = record.top;
        glyph.width = record.width;
        glyph.height = record.height;
        glyph.pixels.clone_from(&record.pixels);
    }
    Ok(())
}

/// Resolve the per-level color map; validates shape before canvas allocation.
/// The default map is the constant foreground color; coverage scaling happens
/// once at composite time. Explicit entries apply verbatim.
fn palette_map(
    foreground: &[u8; 4],
    palette: Option<&[[u8; 4]]>,
    levels: u32,
) -> Result<Vec<[u8; 4]>, Error> {
    if let Some(entries) = palette {
        if entries.len() != levels as usize {
            return Err(fail(format!(
                "palette must hold exactly {} entries for output_bits {}",
                levels,
                levels.trailing_zeros()
            )));
        }
        return Ok(entries.to_vec());
    }
    Ok(vec![*foreground; levels as usize])
}

/// One visual line under construction: placed chars with their 26.6 pen origins.
struct LineBuild {
    placed: Vec<(char, i64)>,
    pen_26_6: i64,
    last: Option<u32>,
    byte_start: usize,
    byte_end: usize,
}

impl LineBuild {
    fn empty(origin: usize) -> Self {
        LineBuild {
            placed: Vec::new(),
            pen_26_6: 0,
            last: None,
            byte_start: origin,
            byte_end: origin,
        }
    }

    fn width_26_6(&self) -> Result<i32, Error> {
        i32::try_from(self.pen_26_6).map_err(|_| fail("layout advance overflow"))
    }
}

struct Layout<'a> {
    engine: SpacingEngine<'a>,
    wrap: WrapMode,
    limit_26_6: i64,
}

impl Layout<'_> {
    /// Advance of `ch` after `prev`, or `None` for Skip-missing glyphs.
    /// Wrapping simulation and [`Layout::push`] share the engine's placement,
    /// so measurement and placement never diverge.
    fn advance(&self, pen: i64, prev: Option<u32>, ch: char) -> Option<i64> {
        let (_, next) = self.engine.place(pen, prev, ch as u32)?;
        next.checked_sub(pen)
    }

    fn push(&self, line: &mut LineBuild, ch: char, byte: usize, len: usize) -> Result<(), Error> {
        if !self.engine.has_glyph(ch as u32) {
            // Skip-missing glyphs contribute no advance and break kern adjacency.
            line.last = None;
            line.byte_end = byte + len;
            if line.placed.is_empty() {
                line.byte_start = byte + len;
            }
            return Ok(());
        };
        // The pair kern shifts the current glyph origin; the pen then advances
        // by the glyph's own advance. Both come from the engine's single
        // placement operation.
        let (origin, next) = self
            .engine
            .place(line.pen_26_6, line.last, ch as u32)
            .ok_or_else(|| fail("layout advance overflow"))?;
        line.pen_26_6 = next;
        if line.placed.is_empty() {
            line.byte_start = byte;
        }
        line.byte_end = byte + len;
        line.placed.push((ch, origin));
        line.last = Some(ch as u32);
        Ok(())
    }

    /// Simulated pen after appending `extra` chars (missing glyphs add nothing).
    fn simulated(
        &self,
        pen: i64,
        last: Option<u32>,
        extra: &[(char, usize, usize)],
    ) -> Option<i64> {
        let mut pen = pen;
        let mut last = last;
        for (ch, _, _) in extra {
            if !self.engine.has_glyph(*ch as u32) {
                last = None;
                continue;
            }
            let (_, next) = self.engine.place(pen, last, *ch as u32)?;
            pen = next;
            last = Some(*ch as u32);
        }
        Some(pen)
    }

    fn layout_paragraph(
        &self,
        paragraph: &Paragraph,
        lines: &mut Vec<LineBuild>,
    ) -> Result<(), Error> {
        match self.wrap {
            WrapMode::Clip => {
                let mut line = LineBuild::empty(paragraph.start);
                for (ch, byte, len) in &paragraph.chars {
                    self.push(&mut line, *ch, *byte, *len)?;
                }
                lines.push(line);
            }
            WrapMode::Char => {
                let mut line = LineBuild::empty(paragraph.start);
                for (ch, byte, len) in &paragraph.chars {
                    if !line.placed.is_empty() {
                        let advance = self.advance(line.pen_26_6, line.last, *ch).unwrap_or(0);
                        if line.pen_26_6.checked_add(advance).unwrap_or(i64::MAX) > self.limit_26_6
                        {
                            lines.push(std::mem::replace(&mut line, LineBuild::empty(*byte)));
                        }
                    }
                    self.push(&mut line, *ch, *byte, *len)?;
                }
                lines.push(line);
            }
            WrapMode::Word => self.layout_words(paragraph, lines)?,
        }
        Ok(())
    }

    /// Greedy word wrap; ASCII spaces are the only break opportunities and an
    /// overlong word falls back to character breaks for that word only.
    fn layout_words(&self, paragraph: &Paragraph, lines: &mut Vec<LineBuild>) -> Result<(), Error> {
        let mut line = LineBuild::empty(paragraph.start);
        let mut pending: Vec<(usize, usize)> = Vec::new();
        let mut word: Vec<(char, usize, usize)> = Vec::new();
        let mut flush_word = |line: &mut LineBuild,
                              pending: &mut Vec<(usize, usize)>,
                              word: &mut Vec<(char, usize, usize)>|
         -> Result<(), Error> {
            if word.is_empty() {
                return Ok(());
            }
            let mut probe: Vec<(char, usize, usize)> = Vec::new();
            if !line.placed.is_empty() {
                // Separator spaces only count when they join two placed runs.
                for (byte, len) in pending.iter() {
                    probe.push((' ', *byte, *len));
                }
            }
            probe.extend(word.iter().copied());
            let end = self
                .simulated(line.pen_26_6, line.last, &probe)
                .unwrap_or(i64::MAX);
            if !line.placed.is_empty() && end > self.limit_26_6 {
                // Separators are consumed as the breakpoint, not carried over.
                lines.push(std::mem::replace(&mut *line, LineBuild::empty(word[0].1)));
                pending.clear();
            } else if line.placed.is_empty() {
                // Leading separators never start a line.
                pending.clear();
            }
            for (byte, len) in pending.drain(..) {
                self.push(line, ' ', byte, len)?;
            }
            let alone = self.simulated(0, None, word).unwrap_or(i64::MAX);
            if line.placed.is_empty() && alone > self.limit_26_6 {
                // Overlong word: character fallback for this word only.
                for (ch, byte, len) in word.drain(..) {
                    if !line.placed.is_empty() {
                        let advance = self.advance(line.pen_26_6, line.last, ch).unwrap_or(0);
                        if line.pen_26_6.checked_add(advance).unwrap_or(i64::MAX) > self.limit_26_6
                        {
                            lines.push(std::mem::replace(line, LineBuild::empty(byte)));
                        }
                    }
                    self.push(line, ch, byte, len)?;
                }
            } else {
                for (ch, byte, len) in word.drain(..) {
                    self.push(line, ch, byte, len)?;
                }
            }
            Ok(())
        };
        for (ch, byte, len) in &paragraph.chars {
            if *ch == ' ' {
                flush_word(&mut line, &mut pending, &mut word)?;
                pending.push((*byte, *len));
            } else {
                word.push((*ch, *byte, *len));
            }
        }
        flush_word(&mut line, &mut pending, &mut word)?;
        lines.push(line);
        Ok(())
    }
}

struct Canvas {
    width: u32,
    height: u32,
    levels: u32,
    /// Scale source alpha by `v / (levels - 1)` for the default foreground
    /// map; explicit palette entries carry their own final alpha.
    alpha_by_coverage: bool,
    map: Vec<[u8; 4]>,
    pixels: Vec<u8>,
}

impl Canvas {
    fn draw_line(
        &mut self,
        line: &LineBuild,
        baseline: i64,
        align: HAlign,
        glyphs: &HashMap<u32, &Glyph>,
    ) -> Result<(), Error> {
        let line_px = line.pen_26_6.max(0).saturating_add(32).div_euclid(64);
        let width_px = i64::from(self.width);
        let offset = match align {
            HAlign::Left => 0,
            HAlign::Center => (width_px - line_px) / 2,
            HAlign::Right => width_px - line_px,
        };
        let origin_26_6 = offset
            .checked_mul(64)
            .ok_or_else(|| fail("layout position overflow"))?;
        for (ch, pen) in &line.placed {
            let Some(glyph) = glyphs.get(&(*ch as u32)) else {
                continue;
            };
            let pen_px = pen
                .checked_add(origin_26_6)
                .and_then(|p| p.checked_add(32))
                .map(|p| p.div_euclid(64))
                .ok_or_else(|| fail("layout position overflow"))?;
            let x0 = pen_px + i64::from(glyph.left);
            let y0 = baseline + i64::from(glyph.top);
            for row in 0..i64::from(glyph.height) {
                let canvas_y = y0 + row;
                if canvas_y < 0 || canvas_y >= i64::from(self.height) {
                    continue;
                }
                for col in 0..i64::from(glyph.width) {
                    let canvas_x = x0 + col;
                    if canvas_x < 0 || canvas_x >= width_px {
                        continue;
                    }
                    let v = u32::from(
                        glyph.pixels[(row as usize) * (glyph.width as usize) + (col as usize)],
                    );
                    if v == 0 {
                        continue;
                    }
                    let color = self.map[v as usize % self.map.len()];
                    let coverage = if self.alpha_by_coverage {
                        f64::from(v) / f64::from(self.levels - 1)
                    } else {
                        1.0
                    };
                    let index =
                        (canvas_y as usize) * (self.width as usize) * 4 + (canvas_x as usize) * 4;
                    composite(&mut self.pixels[index..index + 4], color, coverage);
                }
            }
        }
        Ok(())
    }
}

#[cfg(all(test, feature = "candidate"))]
mod tests {
    use super::{render_text_with_renderer_and_spacing, HAlign, TextRenderRequest, WrapMode};
    use crate::{renderer::RendererRole, source::raster_counter, Config};
    use std::path::Path;

    fn roboto() -> Vec<u8> {
        std::fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fonts/Roboto.ttf")).unwrap()
    }

    fn request(text: &str) -> TextRenderRequest {
        let mut config = Config {
            size_px: 14.0,
            ..Config::default()
        };
        config.axes.insert("wght".into(), 400.0);
        config.axes.insert("wdth".into(), 100.0);
        TextRenderRequest {
            config,
            text: text.into(),
            width: 300,
            height: 64,
            wrap: WrapMode::Clip,
            align: HAlign::Left,
            foreground: [0, 0, 0, 255],
            background: [255, 255, 255, 255],
            palette: None,
        }
    }

    #[test]
    fn admit_request_normalizes_effective_hinting() {
        use crate::stem_fitting::StemFittingStrategy;
        use crate::Hinting;
        use RendererRole::*;
        let cases = [
            (
                1,
                Hinting::Auto,
                None,
                Some(Candidate),
                Hinting::AutoFallback,
            ),
            (
                1,
                Hinting::AutoFallback,
                Some(StemFittingStrategy::UpstreamMono),
                Some(Candidate),
                Hinting::Auto,
            ),
            (
                3,
                Hinting::AutoFallback,
                None,
                Some(Candidate),
                Hinting::Auto,
            ),
            (
                1,
                Hinting::AutoFallback,
                None,
                Some(Baseline),
                Hinting::AutoFallback,
            ),
        ];
        for (bits, hinting, strategy, role, expected) in cases {
            let mut input = request("A");
            input.config.output_bits = bits;
            input.config.hinting = hinting;
            let before = input.clone();
            let admitted = super::admit_request(&input, role, 0.0, strategy, None).unwrap();
            assert_eq!(admitted.config.hinting, expected);
            assert_eq!(input, before);
        }
    }

    #[test]
    fn prepared_font_hashes_once_but_refits_changed_requests() {
        use crate::renderer::{Rasterization, RenderPipeline};
        use crate::stem_fitting::StemFittingStrategy;
        for family in ["Roboto", "SourceSans3"] {
            let bytes = std::fs::read(
                Path::new(env!("CARGO_MANIFEST_DIR")).join(format!("../../fonts/{family}.ttf")),
            )
            .unwrap();
            let font = super::PreparedFont::new(bytes);
            assert!(font.identity.get().is_none());
            for (i, (size, weight, text)) in [
                (12., 300., "x s 2"),
                (24., 700., "AyW"),
                (16., 400., "k X"),
                (12., 300., "x s 2"),
            ]
            .into_iter()
            .enumerate()
            {
                let mut req = request(text);
                req.config.size_px = size;
                req.config.axes = [("wght".into(), weight)].into();
                let pipeline = RenderPipeline {
                    fitting: if i % 2 == 0 {
                        StemFittingStrategy::FontHintsAuto
                    } else {
                        StemFittingStrategy::UpstreamMono
                    },
                    rasterization: if i % 2 == 0 {
                        Rasterization::FreeTypeMono
                    } else {
                        Rasterization::FreeTypeMonoTerminals
                    },
                    diagonal_fitting: i != 2,
                };
                raster_counter::reset();
                let cached = font
                    .render_text_with_pipeline_and_spacing(&req, pipeline, 0.)
                    .unwrap();
                assert_eq!(raster_counter::font_identity_hashes(), usize::from(i == 0));
                let fresh = super::render_text_with_pipeline_and_spacing(
                    font.as_bytes(),
                    &req,
                    pipeline,
                    0.,
                )
                .unwrap();
                assert_eq!(
                    raster_counter::font_identity_hashes(),
                    usize::from(i == 0) + 1
                );
                assert_eq!(cached.pixels, fresh.pixels);
                assert_eq!(cached.lines, fresh.lines);
                assert_eq!(cached.missing_codepoints, fresh.missing_codepoints);
            }
        }
    }

    #[test]
    #[cfg(feature = "candidate")]
    fn completed_fit_reuse_preserves_interactions_and_changed_inputs() {
        use crate::renderer::{Rasterization, RenderPipeline};
        use crate::stem_fitting::StemFittingStrategy;
        for family in ["Roboto", "SourceSans3"] {
            let bytes = std::fs::read(
                Path::new(env!("CARGO_MANIFEST_DIR")).join(format!("../../fonts/{family}.ttf")),
            )
            .unwrap();
            let font = super::PreparedFont::new(bytes);
            let base = RenderPipeline {
                fitting: StemFittingStrategy::FontHintsAuto,
                rasterization: Rasterization::FreeTypeMonoTerminals,
                diagonal_fitting: true,
            };
            let mut previous_misses = 0;
            for (i, text) in [
                "s x y 2 A W",
                "s x y 2 A W",
                "s x y 2 A W é",
                "s x",
                "s x y 2 A W",
                "s x y 2 A W",
                "s x y 2 A W",
                "s x y 2 A W",
                "s x y 2 A W",
                "s x y 2 A W",
            ]
            .into_iter()
            .enumerate()
            {
                let mut req = request(text);
                req.config.axes = [("wght".into(), if i == 4 { 410. } else { 400. })].into();
                if i == 1 {
                    req.width = 100;
                }
                if i == 6 {
                    req.config.size_px = 18.;
                }
                let mut pipeline = base;
                if i == 7 {
                    pipeline.fitting = StemFittingStrategy::UpstreamMono;
                }
                if i == 8 {
                    pipeline.rasterization = Rasterization::FreeTypeMono;
                }
                if i == 9 {
                    pipeline.diagonal_fitting = false;
                }
                let tracking = if i == 3 { 1. } else { 0. };
                let cached = font
                    .render_text_with_pipeline_and_spacing(&req, pipeline, tracking)
                    .unwrap();
                let misses = font.diagonal_fits.borrow().misses;
                if i == 1 || i == 3 || i == 5 {
                    assert_eq!(misses, previous_misses);
                }
                if i == 4 || i == 6 {
                    assert!(misses > previous_misses);
                }
                previous_misses = misses;
                let fresh = super::render_text_with_pipeline_and_spacing(
                    font.as_bytes(),
                    &req,
                    pipeline,
                    tracking,
                )
                .unwrap();
                assert_eq!(cached.pixels, fresh.pixels, "{family}/{i}");
                assert_eq!(cached.lines, fresh.lines, "{family}/{i}");
                assert_eq!(cached.missing_codepoints, fresh.missing_codepoints);
            }
            assert!(font.diagonal_fits.borrow().hits > 0);
            let other = super::PreparedFont::new(font.as_bytes().to_vec());
            assert_eq!(
                (
                    other.diagonal_fits.borrow().hits,
                    other.diagonal_fits.borrow().misses
                ),
                (0, 0)
            );
        }
    }

    #[test]
    #[cfg(feature = "candidate")]
    fn completed_fit_cache_cannot_hide_invalid_requests() {
        use crate::renderer::{Rasterization, RenderPipeline};
        use crate::stem_fitting::StemFittingStrategy;
        let font = super::PreparedFont::new(roboto());
        let pipeline = RenderPipeline {
            fitting: StemFittingStrategy::FontHintsAuto,
            rasterization: Rasterization::FreeTypeMonoTerminals,
            diagonal_fitting: true,
        };
        font.render_text_with_pipeline_and_spacing(&request("s x"), pipeline, 0.)
            .unwrap();
        for i in 0..6 {
            let mut req = request("s x");
            match i {
                0 => req.width = 0,
                1 => req.config.axes = [("XXXX".into(), 1.)].into(),
                2 => req.text = "a\u{301}".into(),
                3 => req.text = "\t".into(),
                4 => req.config.size_px = f32::NAN,
                _ => req.palette = Some(vec![[0; 4]]),
            }
            let cached = font
                .render_text_with_pipeline_and_spacing(&req, pipeline, 0.)
                .unwrap_err();
            let fresh =
                super::render_text_with_pipeline_and_spacing(font.as_bytes(), &req, pipeline, 0.)
                    .unwrap_err();
            assert_eq!(cached.0, fresh.0, "invalid request {i}");
        }
    }

    #[test]
    fn prepared_font_does_not_skip_blank_or_cached_request_validation() {
        use crate::renderer::RenderPipeline;
        let font = super::PreparedFont::new(roboto());
        let pipeline = RenderPipeline::default();
        let mut req = request("");
        raster_counter::reset();
        font.render_text_with_pipeline_and_spacing(&req, pipeline, 0.)
            .unwrap();
        assert_eq!(raster_counter::font_identity_hashes(), 0);
        for cached in [false, true] {
            if cached {
                font.render_text_with_pipeline_and_spacing(&request("x"), pipeline, 0.)
                    .unwrap();
                assert!(font.identity.get().is_some());
            }
            for text in ["", "x"] {
                req = request(text);
                req.config.axes.insert("XXXX".into(), 1.);
                let actual = font
                    .render_text_with_pipeline_and_spacing(&req, pipeline, 0.)
                    .unwrap_err();
                let expected = super::render_text_with_pipeline_and_spacing(
                    font.as_bytes(),
                    &req,
                    pipeline,
                    0.,
                )
                .unwrap_err();
                assert_eq!(actual.to_string(), expected.to_string());
            }
        }
        let invalid = super::PreparedFont::new(vec![0; 8]);
        assert!(invalid
            .render_text_with_pipeline_and_spacing(&request(""), pipeline, 0.)
            .is_err());
        assert!(invalid.identity.get().is_none());
    }

    #[test]
    fn candidate_surface_rasterizes_once_per_unique_and_tracking_draws_geometry_only() {
        let data = roboto();
        // "hello world" has 8 unique scalars; repeated letters must not reraster.
        raster_counter::reset();
        let neutral = render_text_with_renderer_and_spacing(
            &data,
            &request("hello world"),
            RendererRole::Candidate,
            0.0,
        )
        .unwrap();
        assert_eq!(raster_counter::logical_rasters(), 8);
        assert_eq!(
            raster_counter::source_geometry_draws(),
            0,
            "neutral tracking needs no source geometry"
        );
        assert!(!neutral.pixels.is_empty());

        raster_counter::reset();
        let tracked = render_text_with_renderer_and_spacing(
            &data,
            &request("hello world"),
            RendererRole::Candidate,
            1.0,
        )
        .unwrap();
        assert_eq!(
            raster_counter::logical_rasters(),
            8,
            "tracking must not add a source raster beyond the final capture"
        );
        assert_eq!(
            raster_counter::source_geometry_draws(),
            8,
            "tracking guard draws each unique glyph's unhinted geometry once"
        );
        assert_ne!(tracked.lines[0].width_26_6, neutral.lines[0].width_26_6);

        // A single repeated character rasterizes and draws geometry once.
        raster_counter::reset();
        render_text_with_renderer_and_spacing(
            &data,
            &request("oooo"),
            RendererRole::Candidate,
            1.0,
        )
        .unwrap();
        assert_eq!(raster_counter::logical_rasters(), 1);
        assert_eq!(raster_counter::source_geometry_draws(), 1);
    }
}

/// Source-over with the source alpha scaled once by coverage:
/// `sa = map[v].a * coverage` over the destination texel.
fn composite(canvas: &mut [u8], source: [u8; 4], coverage: f64) {
    let sa = f64::from(source[3]) / 255.0 * coverage;
    let da = f64::from(canvas[3]) / 255.0;
    let out_a = sa + da * (1.0 - sa);
    if out_a <= 0.0 {
        canvas.fill(0);
        return;
    }
    for channel in 0..3 {
        let mixed = (f64::from(source[channel]) * sa
            + f64::from(canvas[channel]) * da * (1.0 - sa))
            / out_a;
        canvas[channel] = mixed.round().clamp(0.0, 255.0) as u8;
    }
    canvas[3] = (out_a * 255.0).round().clamp(0.0, 255.0) as u8;
}
