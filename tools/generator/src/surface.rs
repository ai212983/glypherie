//! Bounded multi-line text rendering over [`crate::generate`] output.
//!
//! Parity contract: glyph bitmaps, advances, kerning adjustments and metrics are
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
use crate::{fail, renderer::RendererRole, Config, Error, GeneratedFont, Glyph, MissingGlyphs};
use std::collections::{BTreeSet, HashMap};

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
    render_inner(font_data, request, None)
}

/// Render bounded multi-line text with an explicit stable renderer role.
///
/// `Baseline` is the approved production path: shaping, metrics, kerning and
/// bitmaps come from `generate()` unchanged, so this equals [`render_text`]
/// bit-for-bit. `Reference` and `Candidate` keep that same `generate()` output
/// for validation, layout, advances, kerning and metrics, and replace only
/// each monochrome glyph's bitmap box with the role capture (`mono_1bit`;
/// extensions `none` for reference, `diagonal-01` for candidate). Preview
/// depths other than 1/3-bit, candidate hinting other than `Auto`, and a
/// candidate request without the `candidate` feature fail explicitly.
///
/// Gray is outside the monochrome experiment: every role uses the unchanged
/// production gray target and coverage. Published captures separately use
/// the reference gray target; baseline and candidate agree within each target.
pub fn render_text_with_renderer(
    font_data: &[u8],
    request: &TextRenderRequest,
    role: RendererRole,
) -> Result<RenderedText, Error> {
    #[cfg(not(feature = "candidate"))]
    if role == RendererRole::Candidate {
        return Err(fail(
            "candidate rendering requires the candidate Cargo feature",
        ));
    }
    render_inner(font_data, request, Some(role))
}

/// Shared validation/layout/compositing pipeline behind [`render_text`] and
/// [`render_text_with_renderer`]; `None` and `Some(Baseline)` both take the
/// approved `generate()` path unchanged.
fn render_inner(
    font_data: &[u8],
    request: &TextRenderRequest,
    role: Option<RendererRole>,
) -> Result<RenderedText, Error> {
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
    // Preview roles bind to the interactive 1/3-bit profiles; anything else
    // fails here, before any allocation, rather than rendering a nearby depth.
    if let Some(role @ (RendererRole::Reference | RendererRole::Candidate)) = role {
        if !matches!(request.config.output_bits, 1 | 3) {
            return Err(fail(format!(
                "preview role {} requires output_bits 1 or 3, got {}",
                role_name(role),
                request.config.output_bits
            )));
        }
        match (role, request.config.hinting) {
            (RendererRole::Candidate, crate::Hinting::Auto) => {}
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
    // Reuses the approved baseline path: shaping support, missing-glyph policy
    // and `fixed()` rounding all come from `generate()` unchanged. When every
    // repertoire glyph is skipped, the render contract is a blank canvas
    // naming each codepoint — no surrogate placeholder is rendered. The Error
    // policy keeps the `generate()` failure unchanged.
    let generated = match crate::generate(font_data, &config) {
        Ok(generated) => generated,
        Err(error)
            if request.config.missing_glyphs == MissingGlyphs::Skip
                && error.0 == "repertoire contains no available glyphs" =>
        {
            // `generate()` validated settings, font, axes and per-character
            // shaping support before reporting the empty repertoire; re-check
            // shaping support here so this path can never mask a capability
            // error, then report the sorted repertoire as skipped.
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
    // Preview roles reuse the approved `generate()` output above for shaping
    // support, missing-glyph policy, metrics, advances and kerning, then swap
    // in only the role's glyph bitmaps so layout never diverges. Baseline
    // keeps the approved bitmaps verbatim.
    if let Some(role @ (RendererRole::Reference | RendererRole::Candidate)) =
        role.filter(|_| generated.config.output_bits == 1)
    {
        let profile = crate::reference::PROFILE_MONO_1BIT;
        let extensions = match role {
            RendererRole::Reference => crate::reference::EXTENSIONS_NONE,
            _ => crate::baseline::EXTENSIONS_DIAGONAL_01,
        };
        let preview = crate::reference::ReferenceRequest {
            profile: profile.to_string(),
            extensions: extensions.to_string(),
            settings: generated.config.clone(),
        };
        let report = crate::renderer::render(font_data, &preview, role)?;
        swap_bitmaps(&mut generated, &report, role)?;
    }
    let levels = 1u32 << generated.config.output_bits;
    let map = palette_map(&request.foreground, request.palette.as_deref(), levels)?;
    let glyphs: HashMap<u32, &Glyph> = generated.glyphs.iter().map(|g| (g.codepoint, g)).collect();
    // Bounded by repertoire^2 (<= 1024^2) via `generate()`; per-pair lookup is O(1).
    let kerning: HashMap<(u32, u32), i32> = generated
        .kerning
        .iter()
        .map(|k| ((k.left, k.right), k.adjustment_26_6))
        .collect();
    let metrics = &generated.metrics;
    let line_height_px = ((i64::from(metrics.ascent_26_6) - i64::from(metrics.descent_26_6)
        + i64::from(metrics.line_gap_26_6)
        + 63)
        / 64)
        .max(1) as u32;
    let ascent_px = (i64::from(metrics.ascent_26_6) + 63).div_euclid(64);
    let limit_26_6 = i64::from(request.width) * 64;
    let layout = Layout {
        glyphs: &glyphs,
        kerning: &kerning,
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
/// the same codepoint. Advances, glyph ids, metrics, kerning and the skipped
/// set stay on the approved `generate()` output so layout is identical.
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
    glyphs: &'a HashMap<u32, &'a Glyph>,
    kerning: &'a HashMap<(u32, u32), i32>,
    wrap: WrapMode,
    limit_26_6: i64,
}

impl Layout<'_> {
    /// Advance of `ch` after `prev`, or `None` for Skip-missing glyphs.
    fn advance(&self, prev: Option<u32>, ch: char) -> Option<i64> {
        let glyph = self.glyphs.get(&(ch as u32))?;
        let kern = match prev {
            Some(left) => self.kerning.get(&(left, ch as u32)).copied().unwrap_or(0),
            None => 0,
        };
        Some(i64::from(glyph.advance_26_6) + i64::from(kern))
    }

    fn push(&self, line: &mut LineBuild, ch: char, byte: usize, len: usize) -> Result<(), Error> {
        let Some(glyph) = self.glyphs.get(&(ch as u32)) else {
            // Skip-missing glyphs contribute no advance and break kern adjacency.
            line.last = None;
            line.byte_end = byte + len;
            if line.placed.is_empty() {
                line.byte_start = byte + len;
            }
            return Ok(());
        };
        // The pair kern shifts the current glyph origin; the pen then advances
        // by the glyph's own advance.
        let kern = match line.last {
            Some(left) => self.kerning.get(&(left, ch as u32)).copied().unwrap_or(0),
            None => 0,
        };
        let origin = line
            .pen_26_6
            .checked_add(i64::from(kern))
            .ok_or_else(|| fail("layout advance overflow"))?;
        line.pen_26_6 = origin
            .checked_add(i64::from(glyph.advance_26_6))
            .ok_or_else(|| fail("layout advance overflow"))?;
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
            match self.advance(last, *ch) {
                None => last = None,
                Some(advance) => {
                    pen = pen.checked_add(advance)?;
                    last = Some(*ch as u32);
                }
            }
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
                        let advance = self.advance(line.last, *ch).unwrap_or(0);
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
                        let advance = self.advance(line.last, ch).unwrap_or(0);
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
