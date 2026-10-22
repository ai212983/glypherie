//! Uniform whole-pixel tracking on the separated bitmap pipeline.
//!
//! The tracked export bakes one signed step into every finalized advance;
//! the tracked pipeline entry point recomposes the same table, so export,
//! preview, measurement and wrapping share one layout with no second
//! application and no legacy floor or refund.
#![cfg(feature = "candidate")]

use font_generator::{
    ascii_kerning_pairs,
    candidate::{generate_bitmap_font, generate_bitmap_font_with_tracking},
    layout_spacing::apply_uniform_tracking,
    renderer::RendererRole,
    stem_fitting::StemFittingStrategy,
    surface::{
        render_text_with_fitting_strategy, render_text_with_pipeline,
        render_text_with_pipeline_and_spacing, HAlign, TextRenderRequest, WrapMode,
    },
    Config, GeneratedFont,
};
use std::collections::{BTreeMap, HashMap};

fn load_font(name: &str) -> Vec<u8> {
    std::fs::read(
        std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../fonts")
            .join(name),
    )
    .unwrap()
}

fn axes() -> BTreeMap<String, f32> {
    BTreeMap::from([("wght".into(), 400.0), ("wdth".into(), 100.0)])
}

fn export_config(size: f32, text: &str, output_bits: u8, kerning: bool) -> Config {
    let mut repertoire: Vec<char> = text.chars().collect();
    repertoire.sort_unstable();
    repertoire.dedup();
    Config {
        size_px: size,
        axes: axes(),
        characters: repertoire.into_iter().collect(),
        output_bits,
        kerning,
        ..Config::default()
    }
}

fn render_request(size: f32, text: &str, output_bits: u8, kerning: bool) -> TextRenderRequest {
    let config = Config {
        size_px: size,
        axes: axes(),
        output_bits,
        kerning,
        ..Config::default()
    };
    TextRenderRequest {
        config,
        text: text.into(),
        width: 512,
        height: 64,
        wrap: WrapMode::Clip,
        align: HAlign::Left,
        foreground: [0, 0, 0, 255],
        background: [255, 255, 255, 255],
        palette: None,
    }
}

fn mono_pipelines() -> Vec<font_generator::renderer::RenderPipeline> {
    use font_generator::renderer::{Rasterization, RenderPipeline};
    [
        StemFittingStrategy::FontHintsFirst,
        StemFittingStrategy::UpstreamMono,
    ]
    .into_iter()
    .flat_map(|fitting| {
        [Rasterization::FreeTypeMono, Rasterization::Coverage]
            .into_iter()
            .map(move |rasterization| RenderPipeline {
                fitting,
                rasterization,
                diagonal_fitting: false,
            })
    })
    .collect()
}

fn gray_pipeline() -> font_generator::renderer::RenderPipeline {
    use font_generator::renderer::{Rasterization, RenderPipeline};
    RenderPipeline {
        fitting: StemFittingStrategy::UpstreamMono,
        rasterization: Rasterization::Coverage,
        diagonal_fitting: false,
    }
}

/// Pen origins from one strike's own advances and pair adjustments.
fn origins(font: &GeneratedFont, text: &str) -> (Vec<i64>, i64) {
    let advances: HashMap<u32, i32> = font
        .glyphs
        .iter()
        .map(|glyph| (glyph.codepoint, glyph.advance_26_6))
        .collect();
    let pairs: HashMap<(u32, u32), i32> = font
        .kerning
        .iter()
        .map(|pair| ((pair.left, pair.right), pair.adjustment_26_6))
        .collect();
    let mut pen = 0_i64;
    let mut previous = None;
    let mut out = Vec::new();
    for ch in text.chars() {
        let codepoint = ch as u32;
        let adjustment = previous
            .and_then(|left| pairs.get(&(left, codepoint)))
            .copied()
            .unwrap_or(0);
        let origin = pen + i64::from(adjustment);
        out.push(origin);
        pen = origin + i64::from(advances[&codepoint]);
        previous = Some(codepoint);
    }
    (out, pen)
}

fn composite_expected(font: &GeneratedFont, text: &str, width: u32, height: u32) -> Vec<u8> {
    let (placed, _) = origins(font, text);
    let glyphs: HashMap<u32, _> = font
        .glyphs
        .iter()
        .map(|glyph| (glyph.codepoint, glyph))
        .collect();
    let levels = 1_u32 << font.config.output_bits;
    let ascent_px = (i64::from(font.metrics.ascent_26_6) + 63).div_euclid(64);
    let mut canvas = vec![255_u8; (width * height * 4) as usize];
    for (ch, origin) in text.chars().zip(&placed) {
        let glyph = glyphs[&(ch as u32)];
        let origin_px = (origin + 32).div_euclid(64);
        for gy in 0..i64::from(glyph.height) {
            for gx in 0..i64::from(glyph.width) {
                let value =
                    u32::from(glyph.pixels[(gy as usize) * (glyph.width as usize) + (gx as usize)]);
                if value == 0 {
                    continue;
                }
                let x = origin_px + i64::from(glyph.left) + gx;
                let y = ascent_px + i64::from(glyph.top) + gy;
                if x < 0 || y < 0 || x >= i64::from(width) || y >= i64::from(height) {
                    continue;
                }
                let index = ((y * i64::from(width) + x) * 4) as usize;
                let sa = f64::from(value) / f64::from(levels - 1);
                let da = f64::from(canvas[index + 3]) / 255.0;
                let out_a = sa + da * (1.0 - sa);
                for channel in 0..3 {
                    let mixed =
                        (0.0 * sa + f64::from(canvas[index + channel]) * da * (1.0 - sa)) / out_a;
                    canvas[index + channel] = mixed.round().clamp(0.0, 255.0) as u8;
                }
                canvas[index + 3] = (out_a * 255.0).round().clamp(0.0, 255.0) as u8;
            }
        }
    }
    canvas
}

#[test]
fn zero_is_identity_for_export_and_pipeline() {
    let data = load_font("Roboto.ttf");
    for output_bits in [1, 3] {
        let strategies: &[Option<StemFittingStrategy>] = if output_bits == 1 {
            &[
                Some(StemFittingStrategy::FontHintsFirst),
                Some(StemFittingStrategy::UpstreamMono),
            ]
        } else {
            &[None]
        };
        for strategy in strategies {
            let neutral = generate_bitmap_font(
                &data,
                &export_config(14.0, "AV a", output_bits, true),
                *strategy,
            )
            .unwrap();
            assert_eq!(
                generate_bitmap_font_with_tracking(
                    &data,
                    &export_config(14.0, "AV a", output_bits, true),
                    *strategy,
                    0.0
                )
                .unwrap(),
                neutral
            );
        }
    }
    for pipeline in mono_pipelines() {
        let request = render_request(14.0, "AV a", 1, true);
        assert_eq!(
            render_text_with_pipeline(&data, &request, pipeline).unwrap(),
            render_text_with_pipeline_and_spacing(&data, &request, pipeline, 0.0).unwrap()
        );
    }
    let gray = render_request(14.0, "AV a", 3, true);
    assert_eq!(
        render_text_with_pipeline(&data, &gray, gray_pipeline()).unwrap(),
        render_text_with_pipeline_and_spacing(&data, &gray, gray_pipeline(), 0.0).unwrap()
    );
}

#[test]
fn tracked_export_shifts_every_advance_and_keeps_pairs_and_bitmaps() {
    let data = load_font("Roboto.ttf");
    for output_bits in [1, 3] {
        let strategies: &[Option<StemFittingStrategy>] = if output_bits == 1 {
            &[
                Some(StemFittingStrategy::FontHintsFirst),
                Some(StemFittingStrategy::UpstreamMono),
            ]
        } else {
            &[None]
        };
        for strategy in strategies {
            for kerning in [true, false] {
                let neutral = generate_bitmap_font(
                    &data,
                    &export_config(14.0, "AV a09", output_bits, kerning),
                    *strategy,
                )
                .unwrap();
                for spacing in [-2.0, -1.0, 1.0, 2.0] {
                    let tracked = generate_bitmap_font_with_tracking(
                        &data,
                        &export_config(14.0, "AV a09", output_bits, kerning),
                        *strategy,
                        spacing,
                    )
                    .unwrap();
                    let step = spacing.round() as i32 * 64;
                    for glyph in &tracked.glyphs {
                        let base = neutral
                            .glyphs
                            .iter()
                            .find(|g| g.codepoint == glyph.codepoint)
                            .unwrap();
                        assert_eq!(glyph.advance_26_6 - base.advance_26_6, step);
                        assert_eq!(
                            (glyph.left, glyph.top, glyph.width, glyph.height),
                            (base.left, base.top, base.width, base.height)
                        );
                        assert_eq!(glyph.pixels, base.pixels);
                        assert_eq!(glyph.glyph_id, base.glyph_id);
                    }
                    // Pair adjustments resolve once from source kerning and
                    // any fitted bearing correction; tracking never touches
                    // them, so no representation correction is required.
                    assert_eq!(tracked.kerning, neutral.kerning);
                    assert_eq!(tracked.metrics, neutral.metrics);
                    assert_eq!(tracked.missing_codepoints, neutral.missing_codepoints);
                    assert!(tracked
                        .glyphs
                        .iter()
                        .all(|glyph| glyph.advance_26_6 % 64 == 0));
                }
            }
        }
    }
}

#[test]
fn fractional_tracking_quantizes_to_whole_pixels() {
    let data = load_font("Roboto.ttf");
    let whole =
        generate_bitmap_font_with_tracking(&data, &export_config(14.0, "AV", 1, true), None, 1.0)
            .unwrap();
    let fractional =
        generate_bitmap_font_with_tracking(&data, &export_config(14.0, "AV", 1, true), None, 1.25)
            .unwrap();
    assert_eq!(fractional, whole);
    let down =
        generate_bitmap_font_with_tracking(&data, &export_config(14.0, "AV", 1, true), None, -0.5)
            .unwrap();
    let neutral = generate_bitmap_font(&data, &export_config(14.0, "AV", 1, true), None).unwrap();
    for glyph in &down.glyphs {
        let base = neutral
            .glyphs
            .iter()
            .find(|g| g.codepoint == glyph.codepoint)
            .unwrap();
        assert_eq!(glyph.advance_26_6 - base.advance_26_6, -64);
    }
}

#[test]
fn pipeline_tracking_is_exact_with_no_floor_or_refund() {
    let data = load_font("Roboto.ttf");
    // Spaces and the final advance keep the step; negative tracking keeps
    // every step too, so the width delta is always glyph count times step.
    for text in ["AV", "A V", "a ", " a", " ", "a  b", "mi li ni AV VA"] {
        for spacing in [-2.0, -1.0, 1.0, 2.0] {
            for pipeline in mono_pipelines() {
                let request = render_request(14.0, text, 1, true);
                let neutral = render_text_with_pipeline(&data, &request, pipeline).unwrap();
                let tracked =
                    render_text_with_pipeline_and_spacing(&data, &request, pipeline, spacing)
                        .unwrap();
                let step = spacing.round() as i32 * 64;
                assert_eq!(
                    tracked.lines[0].width_26_6 - neutral.lines[0].width_26_6,
                    text.chars().count() as i32 * step,
                    "text={text:?} spacing={spacing}"
                );
            }
            let gray = render_request(14.0, text, 3, true);
            let neutral = render_text_with_pipeline(&data, &gray, gray_pipeline()).unwrap();
            let tracked =
                render_text_with_pipeline_and_spacing(&data, &gray, gray_pipeline(), spacing)
                    .unwrap();
            assert_eq!(
                tracked.lines[0].width_26_6 - neutral.lines[0].width_26_6,
                text.chars().count() as i32 * (spacing.round() as i32 * 64),
                "gray text={text:?} spacing={spacing}"
            );
        }
    }
}

#[test]
fn tracked_pipeline_matches_tracked_export_recomposition() {
    let data = load_font("Roboto.ttf");
    for size in [14.0, 20.0] {
        for output_bits in [1, 3] {
            use font_generator::renderer::{Rasterization, RenderPipeline};
            let cases: Vec<(RenderPipeline, Option<StemFittingStrategy>)> = if output_bits == 1 {
                [
                    StemFittingStrategy::FontHintsFirst,
                    StemFittingStrategy::UpstreamMono,
                ]
                .into_iter()
                .flat_map(|fitting| {
                    [Rasterization::FreeTypeMono, Rasterization::Coverage]
                        .into_iter()
                        .map(move |rasterization| {
                            (
                                RenderPipeline {
                                    fitting,
                                    rasterization,
                                    diagonal_fitting: false,
                                },
                                Some(fitting),
                            )
                        })
                })
                .collect()
            } else {
                vec![(gray_pipeline(), None)]
            };
            for (pipeline, strategy) in &cases {
                for kerning in [true, false] {
                    for text in [
                        "AV To zxcekw 909192939495969798",
                        "VAV Toa 09192939495969798",
                        "AAAV aV09 To",
                        "A V mi 09",
                    ] {
                        for spacing in [-2.0, 2.0] {
                            let exported = generate_bitmap_font_with_tracking(
                                &data,
                                &export_config(size, text, output_bits, kerning),
                                *strategy,
                                spacing,
                            )
                            .unwrap();
                            let request = render_request(size, text, output_bits, kerning);
                            let rendered = render_text_with_pipeline_and_spacing(
                                &data, &request, *pipeline, spacing,
                            )
                            .unwrap();
                            let (_, expected_width) = origins(&exported, text);
                            assert_eq!(
                                i64::from(rendered.lines[0].width_26_6),
                                expected_width,
                                "width size={size} bits={output_bits} kerning={kerning} text={text:?} spacing={spacing}"
                            );
                            // The exported strike always carries FreeType Mono
                            // bitmaps; a Coverage pipeline recomposes the same
                            // layout with different ink, so pixels only
                            // compare when the scanners agree.
                            if pipeline.rasterization
                                == font_generator::renderer::Rasterization::FreeTypeMono
                                || output_bits == 3
                            {
                                assert_eq!(
                                    rendered.pixels,
                                    composite_expected(&exported, text, 512, 64),
                                    "pixels size={size} bits={output_bits} kerning={kerning} text={text:?} spacing={spacing}"
                                );
                            }
                        }
                    }
                }
            }
        }
    }
}

#[test]
fn small_advances_keep_signed_tracking_without_clamping() {
    let data = load_font("Roboto.ttf");
    for output_bits in [1, 3] {
        let (pipeline, strategy) = if output_bits == 1 {
            (
                font_generator::renderer::RenderPipeline {
                    fitting: StemFittingStrategy::FontHintsFirst,
                    rasterization: font_generator::renderer::Rasterization::FreeTypeMono,
                    diagonal_fitting: false,
                },
                Some(StemFittingStrategy::FontHintsFirst),
            )
        } else {
            (gray_pipeline(), None)
        };
        // Tightening past zero stays signed: rendering and export agree
        // instead of clamping individual glyphs.
        for spacing in [-2.0, -16.0] {
            let exported = generate_bitmap_font_with_tracking(
                &data,
                &export_config(8.0, "A V", output_bits, true),
                strategy,
                spacing,
            )
            .unwrap();
            if spacing == -16.0 {
                assert!(exported.glyphs.iter().any(|glyph| glyph.advance_26_6 < 0));
            }
            let request = render_request(8.0, "A V", output_bits, true);
            let rendered =
                render_text_with_pipeline_and_spacing(&data, &request, pipeline, spacing).unwrap();
            let (_, expected_width) = origins(&exported, "A V");
            assert_eq!(i64::from(rendered.lines[0].width_26_6), expected_width);
            assert_eq!(
                rendered.pixels,
                composite_expected(&exported, "A V", 512, 64)
            );
        }
    }
}

#[test]
fn tracked_wrapping_measures_the_same_baked_advances_as_placement() {
    let data = load_font("Roboto.ttf");
    for pipeline in mono_pipelines() {
        let mut request = render_request(14.0, "mi li ni AV VA mi li ni AV VA", 1, true);
        request.width = 60;
        request.wrap = WrapMode::Word;
        for spacing in [-1.0, 2.0] {
            let tracked =
                render_text_with_pipeline_and_spacing(&data, &request, pipeline, spacing).unwrap();
            assert!(tracked.lines.len() > 1);
            for line in &tracked.lines {
                assert!(line.width_26_6 <= request.width as i32 * 64);
                let part = &request.text[line.byte_start..line.byte_end];
                let mut clipped = request.clone();
                clipped.text = part.into();
                clipped.wrap = WrapMode::Clip;
                assert_eq!(
                    render_text_with_pipeline_and_spacing(&data, &clipped, pipeline, spacing)
                        .unwrap()
                        .lines[0]
                        .width_26_6,
                    line.width_26_6
                );
            }
        }
    }
}

#[test]
fn invalid_tracking_is_rejected_for_export_and_pipeline_including_blank() {
    let data = load_font("Roboto.ttf");
    for spacing in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY, -16.25, 16.25] {
        assert!(
            generate_bitmap_font_with_tracking(
                &data,
                &export_config(14.0, "AV", 1, true),
                None,
                spacing
            )
            .unwrap_err()
            .to_string()
            .contains("letter_spacing_px"),
            "export spacing={spacing}"
        );
        // Invalid tracking fails before any repertoire work, even empty.
        assert!(
            generate_bitmap_font_with_tracking(
                &data,
                &export_config(14.0, "", 1, true),
                None,
                spacing
            )
            .unwrap_err()
            .to_string()
            .contains("letter_spacing_px"),
            "empty export spacing={spacing}"
        );
        for pipeline in mono_pipelines() {
            for text in ["", "AV"] {
                let request = render_request(14.0, text, 1, true);
                assert!(
                    render_text_with_pipeline_and_spacing(&data, &request, pipeline, spacing)
                        .unwrap_err()
                        .to_string()
                        .contains("letter_spacing_px"),
                    "pipeline text={text:?} spacing={spacing}"
                );
            }
        }
    }
}

#[test]
fn tracking_overflow_fails_instead_of_wrapping() {
    let mut advances = HashMap::new();
    advances.insert('A' as u32, i32::MAX - 32);
    assert!(apply_uniform_tracking(&advances, 16.0)
        .unwrap_err()
        .to_string()
        .contains("overflow"));
    // Exported strikes never approach this magnitude, so the error only
    // triggers on genuinely overflowing tables, never on small advances.
    advances.insert('A' as u32, 8 * 64);
    assert_eq!(
        apply_uniform_tracking(&advances, 16.0).unwrap()[&('A' as u32)],
        8 * 64 + 16 * 64
    );
}

#[test]
fn source_kerning_inspection_is_unchanged_by_tracking() {
    let data = load_font("Roboto.ttf");
    // The inspection API takes no tracking input and draws no glyphs; it
    // must keep reporting authentic source pairs.
    let first = ascii_kerning_pairs(&data, 16.0, &BTreeMap::new()).unwrap();
    let second = ascii_kerning_pairs(&data, 16.0, &BTreeMap::new()).unwrap();
    assert_eq!(first, second);
    assert!(!first.pairs.is_empty());
    let adjustment = first
        .pairs
        .iter()
        .find(|pair| pair.left == 'A' as u32 && pair.right == 'V' as u32)
        .expect("AV pair")
        .adjustment_26_6;
    assert!(adjustment < 0);
}

#[test]
fn historical_role_tracking_keeps_its_protected_behavior() {
    let data = load_font("Roboto.ttf");
    // The separated pipeline applies every negative step; the historical
    // candidate role preserves neutral ASCII word gaps instead.
    for text in ["a a", "a "] {
        let request = render_request(14.0, text, 1, true);
        let historical = render_text_with_fitting_strategy(
            &data,
            &request,
            RendererRole::Candidate,
            -1.0,
            Some(StemFittingStrategy::FontHintsFirst),
        )
        .unwrap();
        let pipeline = font_generator::renderer::RenderPipeline {
            fitting: StemFittingStrategy::FontHintsFirst,
            rasterization: font_generator::renderer::Rasterization::FreeTypeMono,
            diagonal_fitting: false,
        };
        let separated =
            render_text_with_pipeline_and_spacing(&data, &request, pipeline, -1.0).unwrap();
        let neutral = render_text_with_pipeline(&data, &request, pipeline).unwrap();
        assert_eq!(
            separated.lines[0].width_26_6 - neutral.lines[0].width_26_6,
            text.chars().count() as i32 * -64
        );
        assert_ne!(
            historical.lines[0].width_26_6, separated.lines[0].width_26_6,
            "historical role must keep its word-gap policy for {text:?}"
        );
    }
}
