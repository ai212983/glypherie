//! Candidate bitmap spacing: one whole-pixel placement policy for the
//! exported strike, the interactive preview and native specimens.
//!
//! Expectations are transcribed from fitted record fields and source
//! metrics directly, or composed from the exported strike's own glyphs,
//! rather than by calling the shared placement builder.
#![cfg(feature = "candidate")]

use font_generator::{
    candidate::generate_bitmap_font,
    generate,
    renderer::RendererRole,
    stem_fitting::StemFittingStrategy,
    surface::{render_text_with_fitting_strategy, HAlign, TextRenderRequest, WrapMode},
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

fn flex_axes() -> BTreeMap<String, f32> {
    BTreeMap::from([
        ("opsz".into(), 14.0),
        ("wght".into(), 400.0),
        ("GRAD".into(), 0.0),
        ("wdth".into(), 100.0),
        ("slnt".into(), 0.0),
        ("XOPQ".into(), 96.0),
        ("YOPQ".into(), 79.0),
        ("XTRA".into(), 468.0),
        ("YTUC".into(), 712.0),
        ("YTLC".into(), 514.0),
        ("YTAS".into(), 750.0),
        ("YTDE".into(), -203.0),
        ("YTFI".into(), 738.0),
    ])
}

fn config(
    size: f32,
    axes: BTreeMap<String, f32>,
    text: &str,
    output_bits: u8,
    kerning: bool,
) -> Config {
    let mut repertoire: Vec<char> = text.chars().collect();
    repertoire.sort_unstable();
    repertoire.dedup();
    Config {
        size_px: size,
        axes,
        characters: repertoire.into_iter().collect(),
        output_bits,
        kerning,
        ..Config::default()
    }
}

/// Pen origins transcribed from exported advances and pair adjustments:
/// each pair adjustment shifts the next origin exactly once.
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

fn ink_extent(font: &GeneratedFont, codepoint: u32) -> (i64, i64) {
    let glyph = font
        .glyphs
        .iter()
        .find(|glyph| glyph.codepoint == codepoint)
        .unwrap();
    let mut min = i64::MAX;
    let mut max = i64::MIN;
    for y in 0..glyph.height {
        for x in 0..glyph.width {
            if glyph.pixels[(y * glyph.width + x) as usize] != 0 {
                let column = i64::from(glyph.left) + i64::from(x);
                min = min.min(column);
                max = max.max(column);
            }
        }
    }
    (min, max)
}

#[test]
fn flex_digit_witness_has_prefix_independent_integer_placement() {
    let data = load_font("RobotoFlex.ttf");
    // Independent source premise: the digits share a fractional advance.
    let source = generate(&data, &config(14.0, flex_axes(), "09", 1, true)).unwrap();
    for glyph in &source.glyphs {
        assert_eq!(glyph.advance_26_6, 506, "source digit advance premise");
    }
    for strategy in [
        StemFittingStrategy::FontHintsFirst,
        StemFittingStrategy::UpstreamMono,
    ] {
        let exported = generate_bitmap_font(
            &data,
            &config(14.0, flex_axes(), "0123456789", 1, true),
            Some(strategy),
        )
        .unwrap();
        for glyph in &exported.glyphs {
            assert_eq!(glyph.advance_26_6, 8 * 64, "digit advance {strategy:?}");
            assert_eq!(glyph.advance_26_6 % 64, 0);
        }
        let (_, max_nine) = ink_extent(&exported, u32::from('9'));
        let (min_eight, _) = ink_extent(&exported, u32::from('8'));
        for text in ["909192939495969798", "09192939495969798"] {
            let (placed, width) = origins(&exported, text);
            assert_eq!(width, text.len() as i64 * 8 * 64, "{text} total width");
            assert!(placed.iter().all(|origin| origin % 64 == 0));
            let nine = placed.len() - 2;
            // The same 9-8 pair keeps the same relative placement and one
            // blank column regardless of the preceding digits.
            assert_eq!(placed[nine + 1] - placed[nine], 8 * 64, "{text} pair step");
            // Origins are 26.6; ink extents are whole pixels. The pair
            // must not touch (the source-layout witness touched on several
            // rows) and must keep the same separation for both prefixes.
            let blank = (placed[nine + 1] - placed[nine]) / 64 + min_eight - max_nine - 1;
            assert!(blank >= 1, "{text} blank columns {blank} between 9 and 8");
        }
    }
}

#[test]
fn pair_placement_is_prefix_invariant_with_and_without_kerning() {
    let data = load_font("Roboto.ttf");
    let mut axes = BTreeMap::new();
    axes.insert("wght".into(), 400.0);
    axes.insert("wdth".into(), 100.0);
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
            let exported = generate_bitmap_font(
                &data,
                &config(20.0, axes.clone(), "AVToa", output_bits, true),
                *strategy,
            )
            .unwrap();
            // Relative steps for each adjacent pair, collected at every
            // position where the pair occurs across different prefixes.
            let mut steps: HashMap<(char, char), Vec<i64>> = HashMap::new();
            for text in ["AV", "VAV", "AAAV", "To", "aTo", "AVTo", "VTo"] {
                let (placed, _) = origins(&exported, text);
                for (index, pair) in text.chars().collect::<Vec<_>>().windows(2).enumerate() {
                    steps
                        .entry((pair[0], pair[1]))
                        .or_default()
                        .push(placed[index + 1] - placed[index]);
                }
            }
            for (pair, values) in &steps {
                assert!(
                    values.iter().all(|value| value == &values[0]),
                    "pair {pair:?} steps differ by prefix: {values:?} bits={output_bits}"
                );
            }
            // With kerning disabled, only a fitting correction may remain;
            // these captures supply none, so the AV step is the advance.
            let unkerned = generate_bitmap_font(
                &data,
                &config(20.0, axes.clone(), "AV", output_bits, false),
                *strategy,
            )
            .unwrap();
            assert!(unkerned.kerning.is_empty(), "bits={output_bits}");
            let (placed, _) = origins(&unkerned, "AV");
            let advance_a = unkerned
                .glyphs
                .iter()
                .find(|glyph| glyph.codepoint == u32::from('A'))
                .unwrap()
                .advance_26_6;
            assert_eq!(placed[1] - placed[0], i64::from(advance_a));
            // Kerning must actually move this witness pair, otherwise the
            // prefix check above could pass with kerning silently dropped.
            let (kerned_placed, _) = origins(&exported, "AV");
            assert_ne!(
                kerned_placed[1] - kerned_placed[0],
                i64::from(advance_a),
                "AV kerning must change the integer step at 20 px, bits={output_bits}"
            );
        }
    }
}

#[test]
fn tabular_digits_retain_a_common_integer_advance() {
    for (name, axes) in [
        ("RobotoFlex.ttf", flex_axes()),
        ("Roboto.ttf", {
            let mut axes = BTreeMap::new();
            axes.insert("wght".into(), 400.0);
            axes.insert("wdth".into(), 100.0);
            axes
        }),
    ] {
        let data = load_font(name);
        for output_bits in [1, 3] {
            let exported = generate_bitmap_font(
                &data,
                &config(14.0, axes.clone(), "0123456789", output_bits, true),
                None,
            )
            .unwrap();
            let advances: Vec<i32> = exported
                .glyphs
                .iter()
                .map(|glyph| glyph.advance_26_6)
                .collect();
            assert_eq!(advances.len(), 10, "{name} bits={output_bits}");
            assert!(
                advances
                    .iter()
                    .all(|advance| *advance == advances[0] && advance % 64 == 0),
                "{name} bits={output_bits}: {advances:?}"
            );
        }
    }
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
fn exported_bitmap_metrics_match_preview_for_mono_and_gray() {
    let data = load_font("Roboto.ttf");
    let mut axes = BTreeMap::new();
    axes.insert("wght".into(), 400.0);
    axes.insert("wdth".into(), 100.0);
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
            for text in ["AVmi09", "A V mi", "909192939495969798"] {
                let exported = generate_bitmap_font(
                    &data,
                    &config(14.0, axes.clone(), text, output_bits, true),
                    *strategy,
                )
                .unwrap();
                assert!(exported
                    .glyphs
                    .iter()
                    .all(|glyph| glyph.advance_26_6 % 64 == 0));
                assert!(exported
                    .kerning
                    .iter()
                    .all(|pair| pair.adjustment_26_6 % 64 == 0));
                let (_, expected_width) = origins(&exported, text);
                let mut request_config = config(14.0, axes.clone(), text, output_bits, true);
                request_config.characters = String::new();
                let request = TextRenderRequest {
                    config: request_config,
                    text: text.into(),
                    width: 512,
                    height: 64,
                    wrap: WrapMode::Clip,
                    align: HAlign::Left,
                    foreground: [0, 0, 0, 255],
                    background: [255, 255, 255, 255],
                    palette: None,
                };
                let rendered = render_text_with_fitting_strategy(
                    &data,
                    &request,
                    RendererRole::Candidate,
                    0.0,
                    *strategy,
                )
                .unwrap();
                assert_eq!(
                    i64::from(rendered.lines[0].width_26_6),
                    expected_width,
                    "preview width bits={output_bits} strategy={strategy:?} text={text}"
                );
                assert_eq!(
                    rendered.pixels,
                    composite_expected(&exported, text, 512, 64),
                    "preview pixels bits={output_bits} strategy={strategy:?} text={text}"
                );
            }
        }
    }
}

#[test]
fn exported_bitmap_metrics_match_specimen_placement() {
    use font_generator::specimens::publish;
    use serde_json::{json, Value};
    let temp = tempfile::tempdir().unwrap();
    let mut value: Value = serde_json::from_str(include_str!("../specimens.json")).unwrap();
    value.as_object_mut().unwrap().remove("preview_policy");
    value.as_object_mut().unwrap().remove("cards");
    // Publication selection requires the reference and legacy baseline
    // alongside the candidate; the active package is the candidate.
    value["defaults"]["variants"] = json!(["reference", "iteration-02", "iteration-03"]);
    value["families"].as_array_mut().unwrap().truncate(1);
    value["families"][0]["font"] =
        json!(std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fonts/Roboto.ttf"));
    value["defaults"]["sizes"] = json!([14]);
    value["characters"] = json!("AV09");
    value["samples"] = json!([{ "id": "text", "label": "Test sample", "text": "A V09" }]);
    let config_path = temp.path().join("config.json");
    std::fs::write(&config_path, serde_json::to_vec(&value).unwrap()).unwrap();
    let output = temp.path().join("output");
    let published = publish(&config_path, &output).unwrap();
    let manifest: Value = serde_json::from_slice(
        &std::fs::read(
            output
                .join(&published.active.variant_id)
                .join("manifest.json"),
        )
        .unwrap(),
    )
    .unwrap();
    let composition: Value = serde_json::from_slice(
        &std::fs::read(output.join("canonical").join(format!(
            "{}.json",
            manifest["variant"]["composition_sha256"].as_str().unwrap()
        )))
        .unwrap(),
    )
    .unwrap();

    let data = load_font("Roboto.ttf");
    let mut axes = BTreeMap::new();
    axes.insert("wght".into(), 400.0);
    axes.insert("wdth".into(), 100.0);
    for (profile, output_bits) in [("mono_1bit", 1), ("gray_3bit", 3)] {
        let exported = generate_bitmap_font(
            &data,
            &config(14.0, axes.clone(), "A V09", output_bits, true),
            None,
        )
        .unwrap();
        let (placed, _) = origins(&exported, "A V09");
        let advances: HashMap<u32, i32> = exported
            .glyphs
            .iter()
            .map(|glyph| (glyph.codepoint, glyph.advance_26_6))
            .collect();
        let pairs: HashMap<(u32, u32), i32> = exported
            .kerning
            .iter()
            .map(|pair| ((pair.left, pair.right), pair.adjustment_26_6))
            .collect();
        let item = composition["items"]
            .as_array()
            .unwrap()
            .iter()
            .find(|item| item["profile"] == profile && item["sample"]["text"] == "A V09")
            .unwrap_or_else(|| panic!("specimen item for {profile}"));
        let glyphs = item["layout"]["glyphs"].as_array().unwrap();
        assert_eq!(glyphs.len(), 5, "{profile}");
        for (index, glyph) in glyphs.iter().enumerate() {
            let codepoint = glyph["codepoint"].as_u64().unwrap() as u32;
            assert_eq!(
                glyph["x_26_6"].as_i64().unwrap(),
                placed[index],
                "{profile} origin {index}"
            );
            let outgoing = if index + 1 < 5 {
                let next = glyphs[index + 1]["codepoint"].as_u64().unwrap() as u32;
                pairs.get(&(codepoint, next)).copied().unwrap_or(0)
            } else {
                0
            };
            assert_eq!(
                glyph["advance_26_6"].as_i64().unwrap(),
                i64::from(advances[&codepoint]) + i64::from(outgoing),
                "{profile} exported advance {index}"
            );
        }
    }
}
