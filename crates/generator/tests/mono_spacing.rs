//! Candidate Mono guard properties and bitmap identity under placement.
//!
//! The projected-gap placement model is removed; only the general
//! source/ink geometry for the explicit-tracking floor remains, and its
//! font properties must not depend on the selected repertoire.
#![cfg(feature = "candidate")]

use font_generator::{
    candidate::generate_bitmap_font,
    mono_spacing::font_spacing_properties,
    renderer::RendererRole,
    surface::{render_text_with_renderer, HAlign, TextRenderRequest, WrapMode},
    Config,
};
use std::{collections::BTreeMap, path::Path};

fn load_font(name: &str) -> Vec<u8> {
    std::fs::read(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../fonts")
            .join(name),
    )
    .unwrap()
}

fn axes_for(name: &str, wght: f32) -> BTreeMap<String, f32> {
    let mut axes = BTreeMap::from([("wght".into(), wght)]);
    if name == "Roboto.ttf" {
        axes.insert("wdth".into(), 100.0);
    }
    axes
}

#[test]
fn font_spacing_properties_are_font_level_not_repertoire_level() {
    // Tabular/fixed-pitch classification reads all ten digits and the post
    // table, so asking with different configs that share size and axes
    // cannot change the answer.
    let bytes = load_font("Roboto.ttf");
    let axes = axes_for("Roboto.ttf", 400.0);
    let first = font_spacing_properties(
        &bytes,
        &Config {
            size_px: 14.0,
            axes: axes.clone(),
            characters: "AV".into(),
            ..Config::default()
        },
    )
    .unwrap();
    let second = font_spacing_properties(
        &bytes,
        &Config {
            size_px: 14.0,
            axes,
            characters: "0123456789".into(),
            ..Config::default()
        },
    )
    .unwrap();
    assert_eq!(first, second);
    assert!(!first.monospace, "Roboto is not a fixed-pitch font");
}

#[test]
fn candidate_glyph_bitmaps_are_unchanged_by_placement() {
    // Placement translates the exported bitmap without resampling: a
    // single glyph rendered on the surface must reproduce the exported
    // strike's pixels at its bitmap offset from the baseline.
    let bytes = load_font("Roboto.ttf");
    let axes = axes_for("Roboto.ttf", 536.0);
    let exported = generate_bitmap_font(
        &bytes,
        &Config {
            size_px: 14.0,
            axes: axes.clone(),
            characters: "mlin".into(),
            ..Config::default()
        },
        None,
    )
    .unwrap();
    let baseline_y = (i64::from(exported.metrics.ascent_26_6) + 63).div_euclid(64);
    for ch in ['m', 'l', 'i', 'n'] {
        let request = TextRenderRequest {
            config: Config {
                size_px: 14.0,
                axes: axes.clone(),
                ..Config::default()
            },
            text: ch.to_string(),
            width: 64,
            height: 64,
            wrap: WrapMode::Clip,
            align: HAlign::Left,
            foreground: [0, 0, 0, 255],
            background: [255, 255, 255, 255],
            palette: None,
        };
        let single = render_text_with_renderer(&bytes, &request, RendererRole::Candidate).unwrap();
        let glyph = exported
            .glyphs
            .iter()
            .find(|glyph| glyph.codepoint == ch as u32)
            .unwrap();
        for y in 0..glyph.height {
            for x in 0..glyph.width {
                let expected = glyph.pixels[(y * glyph.width + x) as usize];
                let canvas_x = (i64::from(glyph.left) + i64::from(x)) as usize;
                let canvas_y = (baseline_y + i64::from(glyph.top) + i64::from(y)) as usize;
                let cell = &single.pixels[(canvas_y * 64 + canvas_x) * 4..][..4];
                if expected == 0 {
                    assert_eq!(cell, &[255, 255, 255, 255], "background for {ch}");
                } else {
                    assert_eq!(cell, &[0, 0, 0, 255], "ink for {ch}");
                }
            }
        }
    }
}
