//! Bounded-text adapter checks over [`font_generator::surface`].
//!
//! Fixture: `fonts/Roboto.ttf` (variable, `wght`; Latin/Greek/Cyrillic coverage).
//! Parity rationale: `surface::render_text` reuses the approved `generate()`
//! path unchanged and only places/wraps/clips/composites, so for an unclipped
//! single line the canvas must equal the `generate()` glyph bitmaps composited
//! at the documented pen positions. These tests rebuild that expectation from
//! public `generate()` output and require exact byte identity.
use font_generator::{
    generate,
    surface::{render_text, HAlign, TextRenderRequest, WrapMode},
    Config, GeneratedFont, Hinting,
};
use std::collections::HashMap;
use std::path::Path;

const FG: [u8; 4] = [0, 0, 0, 255];
const BG: [u8; 4] = [255, 255, 255, 255];

fn font_bytes() -> Vec<u8> {
    std::fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fonts/Roboto.ttf"))
        .expect("fixture fonts/Roboto.ttf")
}

fn config_16_mono() -> Config {
    let mut config = Config::default();
    config.size_px = 16.0;
    config.output_bits = 1;
    config.hinting = Hinting::Auto;
    config.axes.insert("wght".into(), 400.0);
    config
}

fn request(config: Config, text: &str, width: u32, height: u32) -> TextRenderRequest {
    TextRenderRequest {
        config,
        text: text.into(),
        width,
        height,
        wrap: WrapMode::Clip,
        align: HAlign::Left,
        foreground: FG,
        background: BG,
        palette: None,
    }
}

fn advances(gen: &GeneratedFont) -> (HashMap<u32, i32>, HashMap<(u32, u32), i32>) {
    let glyphs = gen
        .glyphs
        .iter()
        .map(|g| (g.codepoint, g.advance_26_6))
        .collect();
    let kerning = gen
        .kerning
        .iter()
        .map(|k| ((k.left, k.right), k.adjustment_26_6))
        .collect();
    (glyphs, kerning)
}

/// 26.6 pen origin of each character, mirroring the adapter's advance + pair
/// kerning accumulation (missing glyphs contribute nothing; tests here only
/// use present glyphs).
fn pen_origins(gen: &GeneratedFont, text: &str) -> Vec<(char, i64)> {
    let (glyphs, kerning) = advances(gen);
    let mut pen = 0i64;
    let mut prev = None;
    let mut out = Vec::new();
    for ch in text.chars() {
        let code = ch as u32;
        let advance = i64::from(*glyphs.get(&code).expect("glyph present"));
        let kern = i64::from(
            prev.map(|p| kerning.get(&(p, code)).copied().unwrap_or(0))
                .unwrap_or(0),
        );
        let origin = pen + kern;
        pen = origin + advance;
        out.push((ch, origin));
        prev = Some(code);
    }
    out
}

/// Documented line geometry: baseline at `ascent_px + index * line_height_px`.
fn line_geometry(gen: &GeneratedFont) -> (i64, u32) {
    let metrics = &gen.metrics;
    let ascent_px = (i64::from(metrics.ascent_26_6) + 63).div_euclid(64);
    let line_height_px = ((i64::from(metrics.ascent_26_6) - i64::from(metrics.descent_26_6)
        + i64::from(metrics.line_gap_26_6)
        + 63)
        / 64)
        .max(1) as u32;
    (ascent_px, line_height_px)
}

/// Default color semantics replicated here to pin the adapter's wiring
/// (placement, level mapping, draw order): constant foreground RGB with
/// coverage applied once, `sa = fg.a * v / (levels - 1)`, then source-over.
fn composite_coverage(canvas: &mut [u8], fg: [u8; 4], level: u32, levels: u32) {
    let coverage = f64::from(level) / f64::from(levels - 1);
    source_over(canvas, fg, f64::from(fg[3]) / 255.0 * coverage);
}

/// Explicit-palette semantics: entry `i` is the source color for level `i`
/// with its own alpha used directly (no extra coverage scaling).
fn composite_direct(canvas: &mut [u8], entry: [u8; 4]) {
    source_over(canvas, entry, f64::from(entry[3]) / 255.0);
}

fn source_over(canvas: &mut [u8], source: [u8; 4], sa: f64) {
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

fn glyph_of<'a>(gen: &'a GeneratedFont, ch: char) -> &'a font_generator::Glyph {
    gen.glyphs
        .iter()
        .find(|g| g.codepoint == ch as u32)
        .expect("glyph present")
}

fn check_single_glyph_mono_parity(ch: char) {
    let bytes = font_bytes();
    let mut config = config_16_mono();
    config.characters = ch.into();
    let gen = generate(&bytes, &config).unwrap();
    let glyph = glyph_of(&gen, ch);
    assert!(
        glyph.pixels.iter().any(|&v| v != 0),
        "fixture glyph {ch:?} must carry ink"
    );

    let width = 64u32;
    let height = 40u32;
    let req = request(config, &ch.to_string(), width, height);
    let rendered = render_text(&bytes, &req).unwrap();

    assert_eq!(rendered.width, width);
    assert_eq!(rendered.height, height);
    assert_eq!(rendered.pixels.len(), width as usize * height as usize * 4);
    assert_eq!(rendered.missing_codepoints, Vec::<u32>::new());
    assert_eq!(rendered.lines.len(), 1);
    let line = rendered.lines[0];
    // Advance/offset agreement with generate(): no kerning applies to one glyph.
    assert_eq!(line.width_26_6, glyph.advance_26_6);
    assert_eq!((line.byte_start, line.byte_end), (0, ch.len_utf8()));

    let (ascent_px, line_height_px) = line_geometry(&gen);
    assert_eq!(line.height_px, line_height_px);
    let mut expected = vec![0u8; width as usize * height as usize * 4];
    for chunk in expected.chunks_exact_mut(4) {
        chunk.copy_from_slice(&BG);
    }
    // Pen starts at zero, so pen_px is zero and the bitmap lands at
    // (left + gx, baseline + top + gy).
    let baseline = ascent_px;
    for (row, gy) in (0..glyph.height).enumerate() {
        for (col, gx) in (0..glyph.width).enumerate() {
            if glyph.pixels[row * glyph.width as usize + col] == 0 {
                continue;
            }
            let x = i64::from(glyph.left) + gx as i64;
            let y = baseline + i64::from(glyph.top) + gy as i64;
            assert!(
                x >= 0 && x < i64::from(width) && y >= 0 && y < i64::from(height),
                "test canvas must fit {ch:?} without clipping"
            );
            let at = (y as usize) * (width as usize) * 4 + (x as usize) * 4;
            expected[at..at + 4].copy_from_slice(&FG);
        }
    }
    assert_eq!(rendered.pixels, expected, "glyph {ch:?}");
}

#[test]
fn single_glyph_mono_parity_with_generate() {
    check_single_glyph_mono_parity('A');
    check_single_glyph_mono_parity('g');
}

#[test]
fn gray_pair_with_explicit_palette_parity_with_generate() {
    // Two glyphs (advance + pair kerning) under a 4-bit profile with an opaque
    // explicit palette; the expectation replicates placement and the
    // documented source-over blend per coverage level.
    let bytes = font_bytes();
    let mut config = config_16_mono();
    config.output_bits = 4;
    config.characters = "Ag".into();
    let gen = generate(&bytes, &config).unwrap();
    let levels = 1u32 << 4;
    let palette: Vec<[u8; 4]> = (0..levels)
        .map(|v| {
            [
                (v * 16) as u8,
                (255 - v * 16) as u8,
                (v * 32 % 256) as u8,
                255,
            ]
        })
        .collect();
    let mut req = request(config, "Ag", 64, 40);
    req.palette = Some(palette.clone());
    let rendered = render_text(&bytes, &req).unwrap();

    let glyphs: HashMap<u32, _> = gen.glyphs.iter().map(|g| (g.codepoint, g)).collect();
    let (ascent_px, _) = line_geometry(&gen);
    let mut expected = vec![0u8; 64 * 40 * 4];
    for chunk in expected.chunks_exact_mut(4) {
        chunk.copy_from_slice(&BG);
    }
    for (ch, origin) in pen_origins(&gen, "Ag") {
        let glyph = glyphs[&(ch as u32)];
        let pen_px = (origin + 32).div_euclid(64);
        for gy in 0..glyph.height {
            for gx in 0..glyph.width {
                let v = u32::from(glyph.pixels[gy as usize * glyph.width as usize + gx as usize]);
                if v == 0 {
                    continue;
                }
                let x = pen_px + i64::from(glyph.left) + gx as i64;
                let y = ascent_px + i64::from(glyph.top) + gy as i64;
                assert!(
                    x >= 0 && x < 64 && y >= 0 && y < 40,
                    "test canvas must fit the pair without clipping"
                );
                let at = (y as usize) * 64 * 4 + (x as usize) * 4;
                composite_direct(&mut expected[at..at + 4], palette[v as usize]);
            }
        }
    }
    assert_eq!(rendered.pixels, expected);
    let (adv_map, kern_map) = advances(&gen);
    let mut pen = 0i64;
    let mut prev = None;
    for ch in "Ag".chars() {
        let code = ch as u32;
        pen += i64::from(adv_map[&code])
            + i64::from(
                prev.map(|p| kern_map.get(&(p, code)).copied().unwrap_or(0))
                    .unwrap_or(0),
            );
        prev = Some(code);
    }
    assert_eq!(rendered.lines.len(), 1);
    assert_eq!(rendered.lines[0].width_26_6, pen as i32);
    assert_eq!(
        (rendered.lines[0].byte_start, rendered.lines[0].byte_end),
        (0, 2)
    );
}

#[test]
fn nonzero_kern_pair_origin_parity_with_generate() {
    // Witness for pair-kerning placement: the second glyph origin must be
    // old_pen + kern, not old_pen. The pair is discovered from generate()
    // output so the test is valid only when the kern is provably nonzero.
    let bytes = font_bytes();
    let mut config = config_16_mono();
    config.output_bits = 4;
    config.characters = "AVTo".into();
    let gen = generate(&bytes, &config).unwrap();
    let pair = gen
        .kerning
        .iter()
        .find(|k| k.adjustment_26_6 != 0)
        .expect("fixture must kern at least one repertoire pair");
    assert_ne!(pair.adjustment_26_6, 0);
    let text: String = [pair.left, pair.right]
        .into_iter()
        .map(|code| char::from_u32(code).unwrap())
        .collect();

    let levels = 1u32 << 4;
    let rendered = render_text(&bytes, &request(config, &text, 96, 48)).unwrap();
    let glyphs: HashMap<u32, _> = gen.glyphs.iter().map(|g| (g.codepoint, g)).collect();
    let (ascent_px, _) = line_geometry(&gen);
    let mut expected = vec![0u8; 96 * 48 * 4];
    for chunk in expected.chunks_exact_mut(4) {
        chunk.copy_from_slice(&BG);
    }
    for (ch, origin) in pen_origins(&gen, &text) {
        let glyph = glyphs[&(ch as u32)];
        let pen_px = (origin + 32).div_euclid(64);
        for gy in 0..glyph.height {
            for gx in 0..glyph.width {
                let v = u32::from(glyph.pixels[gy as usize * glyph.width as usize + gx as usize]);
                if v == 0 {
                    continue;
                }
                let x = pen_px + i64::from(glyph.left) + gx as i64;
                let y = ascent_px + i64::from(glyph.top) + gy as i64;
                assert!(
                    x >= 0 && x < 96 && y >= 0 && y < 48,
                    "test canvas must fit the pair without clipping"
                );
                let at = (y as usize) * 96 * 4 + (x as usize) * 4;
                composite_coverage(&mut expected[at..at + 4], FG, v, levels);
            }
        }
    }
    assert_eq!(rendered.pixels, expected);
    // The corrected origin differs from the kern-ignoring one by construction.
    let origins = pen_origins(&gen, &text);
    let first_advance = i64::from(glyphs[&pair.left].advance_26_6);
    assert_eq!(
        origins[1].1,
        first_advance + i64::from(pair.adjustment_26_6),
        "second origin must carry the pair kern"
    );
    assert_ne!(
        origins[1].1, first_advance,
        "witness pair must shift placement"
    );
}

#[test]
fn default_gray_on_transparent_matches_oracle() {
    // Host oracle: output_bits 3 (8 levels), foreground [20,30,40,255] on
    // transparent background. Every nonzero level v must yield exactly
    // [20,30,40,round(255*v/7)] with coverage applied once; level 0 leaves
    // the background untouched.
    let bytes = font_bytes();
    let mut config = config_16_mono();
    config.output_bits = 3;
    config.characters = "A".into();
    let gen = generate(&bytes, &config).unwrap();
    let glyph = glyph_of(&gen, 'A');
    let fg = [20, 30, 40, 255];
    let bg = [0, 0, 0, 0];
    let mut req = request(config, "A", 64, 40);
    req.foreground = fg;
    req.background = bg;
    let rendered = render_text(&bytes, &req).unwrap();
    let (ascent_px, _) = line_geometry(&gen);
    let mut ink_texels = 0usize;
    let mut seen_partial = false;
    for gy in 0..glyph.height {
        for gx in 0..glyph.width {
            let v = u32::from(glyph.pixels[gy as usize * glyph.width as usize + gx as usize]);
            let x = i64::from(glyph.left) + gx as i64;
            let y = ascent_px + i64::from(glyph.top) + gy as i64;
            assert!(
                x >= 0 && x < 64 && y >= 0 && y < 40,
                "test canvas must fit without clipping"
            );
            let at = (y as usize) * 64 * 4 + (x as usize) * 4;
            if v == 0 {
                assert_eq!(rendered.pixels[at..at + 4], bg);
            } else {
                let alpha = (255.0 * f64::from(v) / 7.0).round() as u8;
                assert_eq!(
                    rendered.pixels[at..at + 4],
                    [20, 30, 40, alpha],
                    "level {v} must keep foreground RGB with once-scaled alpha"
                );
                ink_texels += 1;
                if v < 7 {
                    seen_partial = true;
                }
            }
        }
    }
    assert!(seen_partial, "gray glyph must carry intermediate levels");
    let canvas_ink = rendered.pixels.chunks_exact(4).filter(|t| *t != bg).count();
    assert_eq!(canvas_ink, ink_texels, "no texel may be written twice");
}

#[test]
fn explicit_palette_alpha_used_without_coverage_scaling() {
    // output_bits 1 on a transparent canvas: the nonzero-level entry is used
    // directly, so ink texels equal the entry (alpha 128, not 128 * coverage).
    let bytes = font_bytes();
    let mut req = request(config_16_mono(), "A", 64, 40);
    let bg = [9, 9, 9, 0];
    let entry = [20, 30, 40, 128];
    req.background = bg;
    req.palette = Some(vec![[0, 0, 0, 0], entry]);
    let rendered = render_text(&bytes, &req).unwrap();
    let mut ink = false;
    for texel in rendered.pixels.chunks_exact(4) {
        assert!(
            texel == bg || texel == entry,
            "texel must be background or the exact entry, got {texel:?}"
        );
        ink |= texel == entry;
    }
    assert!(ink, "glyph must write entry texels");
}

fn leftmost_ink_x(pixels: &[u8], width: u32, height: u32) -> Option<i64> {
    for x in 0..width {
        for y in 0..height {
            let at = (y as usize) * (width as usize) * 4 + (x as usize) * 4;
            if pixels[at..at + 4] != BG {
                return Some(i64::from(x));
            }
        }
    }
    None
}

#[test]
fn canvas_size_respected_and_newline_forms_agree() {
    let bytes = font_bytes();
    let config = config_16_mono();
    let req = request(config, "A", 37, 23);
    let rendered = render_text(&bytes, &req).unwrap();
    assert_eq!((rendered.width, rendered.height), (37, 23));
    assert_eq!(rendered.pixels.len(), 37 * 23 * 4);

    // LF, CRLF and CR split paragraphs identically on the canvas; only the
    // byte offsets of later lines differ (CRLF consumes two bytes).
    let lf = render_text(&bytes, &request(config_16_mono(), "A\nB", 64, 64)).unwrap();
    let crlf = render_text(&bytes, &request(config_16_mono(), "A\r\nB", 64, 64)).unwrap();
    let cr = render_text(&bytes, &request(config_16_mono(), "A\rB", 64, 64)).unwrap();
    assert_eq!(lf.pixels, crlf.pixels);
    assert_eq!(lf.pixels, cr.pixels);
    assert_eq!(lf.lines.len(), 2);
    assert_eq!((lf.lines[0].byte_start, lf.lines[0].byte_end), (0, 1));
    assert_eq!((lf.lines[1].byte_start, lf.lines[1].byte_end), (2, 3));
    assert_eq!((crlf.lines[1].byte_start, crlf.lines[1].byte_end), (3, 4));
    assert_eq!((cr.lines[1].byte_start, cr.lines[1].byte_end), (2, 3));
    for line in lf.lines.iter().chain(crlf.lines.iter()) {
        assert!(line.width_26_6 > 0);
    }
}

#[test]
fn word_wrap_breaks_overlong_word_and_clip_does_not() {
    let bytes = font_bytes();
    let config = config_16_mono();
    // Narrow canvas: a single long word cannot fit on one line.
    let word = "AAAAAAAAAAAAAAAAAAAA";
    let mut word_req = request(config.clone(), word, 40, 200);
    word_req.wrap = WrapMode::Word;
    let word_lines = render_text(&bytes, &word_req).unwrap();
    assert!(
        word_lines.lines.len() > 1,
        "overlong word must fall back to character breaks"
    );
    let limit = i64::from(word_req.width) * 64;
    let mut covered = String::new();
    for line in &word_lines.lines {
        assert!(
            i64::from(line.width_26_6) <= limit,
            "wrapped line must fit the canvas width"
        );
        covered.push_str(&word[line.byte_start..line.byte_end]);
    }
    assert_eq!(covered, word, "every character lands on exactly one line");

    // Clip keeps one visual line per paragraph regardless of overflow.
    let clip_req = request(config.clone(), word, 40, 200);
    let clipped = render_text(&bytes, &clip_req).unwrap();
    assert_eq!(clipped.lines.len(), 1);
    assert_eq!(clipped.pixels.len(), 40 * 200 * 4);

    // Char mode breaks anywhere, including inside words.
    let mut char_req = request(config.clone(), word, 40, 200);
    char_req.wrap = WrapMode::Char;
    let char_lines = render_text(&bytes, &char_req).unwrap();
    assert!(char_lines.lines.len() > 1);

    // Spaced text wraps at word boundaries and stays within the canvas.
    let mut spaced_req = request(config, "AA AA AA AA AA AA", 40, 200);
    spaced_req.wrap = WrapMode::Word;
    let spaced = render_text(&bytes, &spaced_req).unwrap();
    assert!(spaced.lines.len() > 1);
    for line in &spaced.lines {
        assert!(i64::from(line.width_26_6) <= limit);
    }
}

#[test]
fn alignment_shifts_ink_right() {
    let bytes = font_bytes();
    let config = config_16_mono();
    let mut inks = Vec::new();
    for align in [HAlign::Left, HAlign::Center, HAlign::Right] {
        let mut req = request(config.clone(), "A", 120, 32);
        req.align = align;
        let rendered = render_text(&bytes, &req).unwrap();
        inks.push(leftmost_ink_x(&rendered.pixels, 120, 32).expect("ink present"));
    }
    assert!(inks[1] > inks[0], "center starts right of left: {inks:?}");
    assert!(inks[2] > inks[0], "right starts right of left: {inks:?}");

    // Left alignment places the pen at zero, so the leftmost ink texel is the
    // glyph's left bearing plus its first nonzero bitmap column.
    let mut gen_config = config_16_mono();
    gen_config.characters = "A".into();
    let gen = generate(&bytes, &gen_config).unwrap();
    let glyph = glyph_of(&gen, 'A');
    let first_column = (0..glyph.width)
        .find(|&gx| {
            (0..glyph.height)
                .any(|gy| glyph.pixels[gy as usize * glyph.width as usize + gx as usize] != 0)
        })
        .expect("ink present");
    assert_eq!(inks[0], i64::from(glyph.left) + i64::from(first_column));
}

#[test]
fn vertical_overflow_clips_without_error() {
    let bytes = font_bytes();
    let req = request(config_16_mono(), "A\nB\nC", 64, 1);
    let rendered = render_text(&bytes, &req).unwrap();
    // Layout is independent of canvas height; drawing clips to the one row.
    assert_eq!(rendered.lines.len(), 3);
    assert_eq!(rendered.pixels.len(), 64 * 4);
}

#[test]
fn output_profile_level_mapping_sanity() {
    let bytes = font_bytes();
    for bits in [1u8, 2, 4, 8] {
        let mut config = config_16_mono();
        config.output_bits = bits;
        let rendered = render_text(&bytes, &request(config, "Ag", 64, 40)).unwrap();
        assert_eq!(rendered.pixels.len(), 64 * 40 * 4);
        if bits == 1 {
            // Mono texels are exactly foreground or background.
            for texel in rendered.pixels.chunks_exact(4) {
                assert!(
                    texel == FG || texel == BG,
                    "mono texel must be fg or bg, got {texel:?}"
                );
            }
        } else {
            // Opaque bg-to-fg interpolation plus source-over keeps every
            // channel on the segment between background and foreground.
            for texel in rendered.pixels.chunks_exact(4) {
                for channel in 0..3 {
                    let (lo, hi) = (BG[channel].min(FG[channel]), BG[channel].max(FG[channel]));
                    assert!(
                        (lo..=hi).contains(&texel[channel]),
                        "gray texel channel out of bg/fg segment: {texel:?}"
                    );
                }
                assert_eq!(texel[3], 255);
            }
        }
    }
}

#[test]
fn variable_axis_changes_output_and_unknown_axis_errors() {
    let bytes = font_bytes();
    let render_at = |wght: f32| {
        let mut config = config_16_mono();
        config.axes.insert("wght".into(), wght);
        render_text(&bytes, &request(config, "Ag", 64, 40)).unwrap()
    };
    let regular = render_at(400.0);
    let bold = render_at(700.0);
    assert_ne!(
        regular.pixels, bold.pixels,
        "wght 400 vs 700 must change the raster"
    );

    let mut bad_axis = config_16_mono();
    bad_axis.axes.insert("XXXX".into(), 1.0);
    let error = render_text(&bytes, &request(bad_axis, "A", 64, 40)).unwrap_err();
    assert!(error.to_string().contains("unsupported axis"), "{error}");

    let mut out_of_range = config_16_mono();
    out_of_range.axes.insert("wght".into(), 5000.0);
    assert!(render_text(&bytes, &request(out_of_range, "A", 64, 40)).is_err());
}

#[test]
fn explicit_mono_palette_reproduces_entries() {
    let bytes = font_bytes();
    let mut config = config_16_mono();
    config.characters = "A".into();
    let ink = [9, 8, 7, 255];
    let paper = [210, 211, 212, 255];
    let mut req = request(config, "A", 64, 40);
    req.foreground = ink;
    req.background = paper;
    req.palette = Some(vec![paper, ink]);
    let rendered = render_text(&bytes, &req).unwrap();
    for texel in rendered.pixels.chunks_exact(4) {
        assert!(
            texel == ink || texel == paper,
            "mono palette texel must be an exact entry, got {texel:?}"
        );
    }
    assert!(rendered.pixels.chunks_exact(4).any(|t| t == ink));
}

#[test]
fn transparent_background_blends_glyph_edges() {
    let bytes = font_bytes();
    let mut config = config_16_mono();
    config.output_bits = 4;
    let mut req = request(config, "A", 64, 40);
    req.background = [255, 255, 255, 0];
    let rendered = render_text(&bytes, &req).unwrap();
    let mut untouched = false;
    let mut partial = false;
    let mut full = false;
    for texel in rendered.pixels.chunks_exact(4) {
        if texel == [255, 255, 255, 0] {
            untouched = true;
        } else if texel[3] == 255 {
            full = true;
        } else {
            assert!(
                texel[3] > 0,
                "blended texel must keep positive alpha: {texel:?}"
            );
            partial = true;
        }
    }
    assert!(
        untouched,
        "texels outside the glyph stay exactly background"
    );
    assert!(partial, "gray edges blend to intermediate alpha");
    assert!(full, "coverage cores reach full alpha");
}

#[test]
fn repeated_render_is_byte_identical() {
    let bytes = font_bytes();
    let mut config = config_16_mono();
    config.output_bits = 4;
    let mut req = request(config, "Ag\nAg", 64, 64);
    req.wrap = WrapMode::Word;
    req.align = HAlign::Center;
    let first = render_text(&bytes, &req).unwrap();
    let second = render_text(&bytes, &req).unwrap();
    assert_eq!(first, second);
}

#[test]
fn request_limits_rejected() {
    let bytes = font_bytes();
    let too_long = "a".repeat(8193);
    let distinct: String = (0x20u32..0x20 + 1025)
        .map(|c| char::from_u32(c).unwrap())
        .collect();
    assert_eq!(distinct.chars().count(), 1025);
    let cases: Vec<(TextRenderRequest, &str)> = vec![
        (request(config_16_mono(), "A", 0, 10), "canvas width"),
        (request(config_16_mono(), "A", 10, 0), "canvas height"),
        (request(config_16_mono(), "A", 4097, 10), "canvas width"),
        (request(config_16_mono(), "A", 10, 4097), "canvas height"),
        (request(config_16_mono(), &too_long, 64, 64), "8192"),
        (
            request(config_16_mono(), &distinct, 64, 64),
            "1024 distinct",
        ),
        (
            {
                let mut config = config_16_mono();
                config.size_px = 0.0;
                request(config, "A", 64, 64)
            },
            "size_px",
        ),
        (
            {
                let mut config = config_16_mono();
                config.size_px = 600.0;
                request(config, "A", 64, 64)
            },
            "size_px",
        ),
        (request(config_16_mono(), "A\tB", 64, 64), "shaping"),
        (request(config_16_mono(), "e\u{301}", 64, 64), "shaping"),
        (request(config_16_mono(), "A中", 64, 64), "shaping"),
        (
            {
                let mut req = request(config_16_mono(), "A", 64, 64);
                req.palette = Some(vec![FG]);
                req
            },
            "exactly 2 entries",
        ),
    ];
    for (req, fragment) in cases {
        let error = render_text(&bytes, &req).unwrap_err();
        assert!(
            error.to_string().contains(fragment),
            "text {:?}: expected {fragment:?}, got {error}",
            req.text
        );
    }
    // The texel bound equals the maximum valid-dim product, so the largest
    // valid canvas still renders.
    let max = render_text(&bytes, &request(config_16_mono(), "A", 4096, 4096)).unwrap();
    assert_eq!(max.pixels.len(), 4096 * 4096 * 4);
}

#[test]
fn missing_glyph_policy_blank_text_and_ignored_characters() {
    let bytes = font_bytes();
    // U+0378 is unassigned: it passes script validation but has no outline.
    let error = render_text(&bytes, &request(config_16_mono(), "\u{378}", 64, 40)).unwrap_err();
    assert!(error.to_string().contains("missing glyph"), "{error}");

    let mut skip_config = config_16_mono();
    skip_config.missing_glyphs = font_generator::MissingGlyphs::Skip;
    let skipped = render_text(&bytes, &request(skip_config, "A\u{378}", 64, 40)).unwrap();
    assert_eq!(skipped.missing_codepoints, vec![0x378]);
    assert_eq!(skipped.lines.len(), 1);
    assert_eq!(
        (skipped.lines[0].byte_start, skipped.lines[0].byte_end),
        (0, 3)
    );

    // Empty and newline-only text yields a blank canvas, but only after the
    // same font/config/axes/palette validation as any other request.
    for text in ["", "\n\n"] {
        let blank = render_text(&bytes, &request(config_16_mono(), text, 12, 8)).unwrap();
        assert!(blank.lines.is_empty());
        assert!(blank.missing_codepoints.is_empty());
        assert!(blank.pixels.chunks_exact(4).all(|t| t == BG));
    }
    let mut bad_size = config_16_mono();
    bad_size.size_px = 0.0;
    assert!(render_text(&bytes, &request(bad_size, "", 12, 8)).is_err());
    let mut bad_axis = config_16_mono();
    bad_axis.axes.insert("XXXX".into(), 1.0);
    assert!(render_text(&bytes, &request(bad_axis, "\n", 12, 8)).is_err());
    let mut bad_palette = request(config_16_mono(), "", 12, 8);
    bad_palette.palette = Some(vec![FG]);
    assert!(render_text(&bytes, &bad_palette).is_err());
    let mut bad_bits = config_16_mono();
    bad_bits.output_bits = 5;
    assert!(render_text(&bytes, &request(bad_bits, "", 12, 8)).is_err());
    let mut short_palette = config_16_mono();
    short_palette.output_bits = 3;
    let mut short_req = request(short_palette, "\n", 12, 8);
    short_req.palette = Some(vec![FG, BG]);
    assert!(render_text(&bytes, &short_req).is_err());
    assert!(render_text(b"not a font", &request(config_16_mono(), "", 12, 8)).is_err());
    // Text whose glyphs are all skipped yields a blank canvas reporting
    // every codepoint, instead of the empty-repertoire error.
    let mut skip_config = config_16_mono();
    skip_config.missing_glyphs = font_generator::MissingGlyphs::Skip;
    let blank = render_text(&bytes, &request(skip_config, "\u{378}\u{379}", 64, 40)).unwrap();
    assert!(blank.lines.is_empty());
    assert_eq!(blank.missing_codepoints, vec![0x378, 0x379]);
    assert!(blank.pixels.chunks_exact(4).all(|t| t == BG));

    // `characters` is derived from the text; the request value is ignored.
    let mut ignored = config_16_mono();
    ignored.characters = "ZZZ".into();
    let via_ignored = render_text(&bytes, &request(ignored, "A", 64, 40)).unwrap();
    let mut direct = config_16_mono();
    direct.characters = "A".into();
    let via_direct = render_text(&bytes, &request(direct, "A", 64, 40)).unwrap();
    assert_eq!(via_ignored.pixels, via_direct.pixels);
}

#[test]
fn blank_requests_reject_unsupported_fonts_like_nonempty_requests() {
    let empty_sfnt = [0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
    let bytes = font_bytes();
    // Copy the source tables verbatim and add a color table: acceptance
    // depends on its presence, before any color-table parsing or rendering.
    let mut builder = write_fonts::FontBuilder::new();
    let source = skrifa::FontRef::new(&bytes).unwrap();
    for record in source.table_directory().table_records() {
        let tag = record.tag();
        builder.add_raw(
            write_fonts::types::Tag::new(&tag.to_be_bytes()),
            source.table_data(tag).unwrap().as_bytes(),
        );
    }
    builder.add_raw(write_fonts::types::Tag::new(b"COLR"), vec![0u8; 14]);
    let color_font = builder.build();
    for (font, expected) in [
        (
            empty_sfnt.as_slice(),
            "font has no supported glyf/CFF/CFF2 outlines",
        ),
        (
            color_font.as_slice(),
            "color fonts require a color output adapter",
        ),
    ] {
        for text in ["", "\n", "A"] {
            let error = render_text(font, &request(config_16_mono(), text, 12, 8)).unwrap_err();
            assert_eq!(error.to_string(), expected);
        }
    }
}
