//! Exercise completed kerning methods through the shared preview/export seam.
//! These establish module contracts, not optical acceptance of any method.
#![cfg(feature = "candidate")]

use font_generator::{
    candidate, playdate,
    renderer::{Rasterization, RenderPipeline},
    stem_fitting::StemFittingStrategy,
    surface::{self, TextRenderRequest, WrapMode},
    Config, GeneratedFont, HuHerschSettings, KerningMethod,
};
use skrifa::MetadataProvider;
use std::collections::{BTreeSet, HashMap};

fn data() -> &'static [u8] {
    include_bytes!("../../../fonts/Literata.ttf")
}

fn method(name: &str) -> KerningMethod {
    let value = match name {
        "hu_hersch" => serde_json::json!({ "method": name }),
        "hu_hersch_half" => serde_json::json!({ "method": "hu_hersch", "strength": 0.5 }),
        "fontforge" => serde_json::json!({ "method": name, "strength": 1.0 }),
        _ => panic!("unexpected test method"),
    };
    serde_json::from_value(value).unwrap()
}

fn pipeline(bits: u8) -> RenderPipeline {
    if bits == 1 {
        RenderPipeline::default()
    } else {
        RenderPipeline {
            fitting: StemFittingStrategy::UpstreamMono,
            rasterization: Rasterization::Coverage,
            diagonal_fitting: false,
        }
    }
}

fn config(text: &str, bits: u8) -> Config {
    Config {
        characters: text.into(),
        output_bits: bits,
        size_px: 16.0,
        ..Config::default()
    }
}

fn generate(config: &Config, method: KerningMethod, tracking: f32) -> GeneratedFont {
    candidate::generate_bitmap_font_with_pipeline_and_kerning(
        data(),
        config,
        pipeline(config.output_bits),
        tracking,
        method,
    )
    .unwrap_or_else(|error| {
        panic!(
            "{method:?}, depth {}, {:?}: {error}",
            config.output_bits, config.characters
        )
    })
}

fn pair_map(font: &GeneratedFont) -> HashMap<(u32, u32), i32> {
    font.kerning
        .iter()
        .map(|pair| ((pair.left, pair.right), pair.adjustment_26_6))
        .collect()
}

fn pair_step(font: &GeneratedFont, left: char, right: char) -> i32 {
    let advance = font
        .glyphs
        .iter()
        .find(|glyph| glyph.codepoint == u32::from(left))
        .unwrap()
        .advance_26_6;
    advance
        + pair_map(font)
            .get(&(u32::from(left), u32::from(right)))
            .copied()
            .unwrap_or(0)
}

#[test]
fn calibration_is_separate_from_the_requested_output_repertoire() {
    for bits in [1, 3] {
        let small_config = config("caÉé", bits);
        let small = generate(&small_config, method("hu_hersch"), 0.0);
        let expected: BTreeSet<_> = small_config.characters.chars().map(u32::from).collect();
        assert_eq!(
            small
                .glyphs
                .iter()
                .map(|glyph| glyph.codepoint)
                .collect::<BTreeSet<_>>(),
            expected,
            "auxiliary alphabet glyphs must not enter the output strike"
        );
        assert!(small
            .kerning
            .iter()
            .all(|pair| expected.contains(&pair.left) && expected.contains(&pair.right)));

        let large = generate(
            &config(
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZÉé",
                bits,
            ),
            method("hu_hersch"),
            0.0,
        );
        for (left, right) in [('c', 'a'), ('É', 'é'), ('é', 'a'), ('a', 'É')] {
            assert_eq!(
                pair_step(&small, left, right),
                pair_step(&large, left, right),
                "fixed calibration domain must not be chosen by output text: {left}{right}, depth {bits}"
            );
        }
    }
}

#[test]
fn unsupported_scripts_keep_source_without_cross_script_calibration_pairs() {
    let bytes = include_bytes!("../../../fonts/SourceSans3.ttf");
    let config = config("αβΩ", 1);
    let render = |method| {
        candidate::generate_bitmap_font_with_pipeline_and_kerning(
            bytes,
            &config,
            pipeline(1),
            0.0,
            method,
        )
        .unwrap()
    };
    for name in ["hu_hersch", "hu_hersch_half"] {
        assert_eq!(render(KerningMethod::Source), render(method(name)));
    }
}

fn replace_table(tag: &[u8; 4], bytes: &[u8]) -> Vec<u8> {
    let source = skrifa::FontRef::new(data()).unwrap();
    let mut builder = write_fonts::FontBuilder::new();
    for record in source.table_directory().table_records() {
        let table_tag = record.tag();
        if table_tag.to_be_bytes() != *tag {
            builder.add_raw(table_tag, source.table_data(table_tag).unwrap().as_bytes());
        }
    }
    builder.add_raw(write_fonts::types::Tag::new(tag), bytes);
    builder.build()
}

#[test]
fn missing_auxiliary_glyph_does_not_change_the_requested_missing_glyph_policy() {
    // Remove only the reference n from cmap; requested c/a remain fully valid.
    // No reduced-alphabet calibration target is permitted.
    let source = skrifa::FontRef::new(data()).unwrap();
    let cmap = write_fonts::tables::cmap::Cmap::from_mappings(
        source.charmap().mappings().filter_map(|(cp, gid)| {
            char::from_u32(cp)
                .filter(|ch| *ch != 'n')
                .map(|ch| (ch, gid))
        }),
    )
    .unwrap();
    let bytes = replace_table(b"cmap", &write_fonts::dump_table(&cmap).unwrap());
    let config = config("ca", 1);
    let render = |method| {
        candidate::generate_bitmap_font_with_pipeline_and_kerning(
            &bytes,
            &config,
            pipeline(1),
            0.0,
            method,
        )
        .unwrap()
    };
    assert_eq!(render(method("hu_hersch")), render(KerningMethod::Source));
    assert_eq!(
        render(method("hu_hersch_half")),
        render(KerningMethod::Source)
    );
    assert!(render(method("hu_hersch")).missing_codepoints.is_empty());
}

#[test]
fn unrepresentable_auxiliary_pair_retains_source_for_valid_requested_text() {
    // OpenType GPOS PairPos with a right-advance change for zz. The scalar
    // and ca output pair domain are valid; the independent fixed alphabet
    // domain contains zz and is unrepresentable by this renderer.
    // https://learn.microsoft.com/en-us/typography/opentype/spec/gpos#lookup-type-2-pair-adjustment-positioning-subtable
    let source = skrifa::FontRef::new(data()).unwrap();
    let z = source.charmap().map('z').unwrap().to_u32() as u16;
    let words = |values: &[u16]| {
        values
            .iter()
            .flat_map(|value| value.to_be_bytes())
            .collect::<Vec<_>>()
    };
    let mut gpos = words(&[1, 0, 10, 30, 44]);
    gpos.extend(words(&[1]));
    gpos.extend(b"DFLT");
    gpos.extend(words(&[8, 4, 0, 0, 0xffff, 1, 0]));
    gpos.extend(words(&[1]));
    gpos.extend(b"kern");
    gpos.extend(words(&[8, 0, 1, 0]));
    gpos.extend(words(&[1, 4, 2, 0, 1, 8]));
    // PairPos format1: no first value, xAdvance in second value, z coverage.
    gpos.extend(words(&[1, 12, 0, 4, 1, 18, 1, 1, z, 1, z, 1]));
    let bytes = replace_table(b"GPOS", &gpos);
    let config = config("ca", 1);
    let render = |method| {
        candidate::generate_bitmap_font_with_pipeline_and_kerning(
            &bytes,
            &config,
            pipeline(1),
            0.0,
            method,
        )
    };
    let source = render(KerningMethod::Source).unwrap();
    assert_eq!(render(method("hu_hersch")).unwrap(), source);
    assert_eq!(render(method("hu_hersch_half")).unwrap(), source);
    let invalid = Config {
        characters: "zz".into(),
        ..config
    };
    assert!(
        candidate::generate_bitmap_font_with_pipeline_and_kerning(
            &bytes,
            &invalid,
            pipeline(1),
            0.0,
            KerningMethod::Source
        )
        .is_err(),
        "fixture must actually reject its requested zz pair"
    );

    // Mixed calibration owns only the two ordered lower/upper products. Its
    // glyph capture contains z, but zz is not a pair in that declared domain.
    // Compare with the same replacement GPOS whose zz right advance is zero.
    let mut valid_gpos = gpos;
    let len = valid_gpos.len();
    valid_gpos[len - 2..].copy_from_slice(&0u16.to_be_bytes());
    let valid_bytes = replace_table(b"GPOS", &valid_gpos);
    let mixed_config = Config {
        characters: "abcnxAHT".into(),
        ..invalid
    };
    let mixed = |bytes: &[u8], method| {
        candidate::generate_bitmap_font_with_pipeline_and_kerning(
            bytes,
            &mixed_config,
            pipeline(1),
            0.0,
            method,
        )
        .unwrap()
    };
    let expected = mixed(&valid_bytes, method("hu_hersch"));
    let actual = mixed(&bytes, method("hu_hersch"));
    let source = mixed(&bytes, KerningMethod::Source);
    let mut changed = 0;
    for left in mixed_config.characters.chars() {
        for right in mixed_config.characters.chars() {
            if left.is_ascii_lowercase() == right.is_ascii_lowercase() {
                continue;
            }
            assert_eq!(
                pair_step(&actual, left, right),
                pair_step(&expected, left, right),
                "unrelated lowercase zz cannot disable mixed calibration for {left}{right}"
            );
            changed +=
                usize::from(pair_step(&expected, left, right) != pair_step(&source, left, right));
        }
    }
    assert!(
        changed > 0,
        "mixed fixture must distinguish an active calibrated method from Source retention"
    );
}

#[test]
fn hu_calibration_uses_full_designed_kerning_independently_of_source_toggle() {
    for bits in [1, 3] {
        let on = config("AVTo caenri", bits);
        let mut off = on.clone();
        off.kerning = false;
        let with_source = generate(&on, method("hu_hersch"), 0.0);
        let without_source = generate(&off, method("hu_hersch"), 0.0);
        for (left, right) in [('A', 'V'), ('T', 'o'), ('c', 'a'), ('e', 'n'), ('r', 'i')] {
            assert_eq!(
                pair_step(&with_source, left, right),
                pair_step(&without_source, left, right),
                "the active Hu endpoint must not recalibrate when Source is toggled: {left}{right}"
            );
        }
    }
}

#[test]
fn gray_methods_do_not_measure_quantized_coverage() {
    for name in ["hu_hersch", "hu_hersch_half", "fontforge"] {
        let mut reference = None;
        for bits in [2, 3, 4] {
            let original = config("AVcaen osri", bits);
            let plain = generate(&original, method(name), 0.0);
            if let Some(expected) = &reference {
                assert_eq!(
                    &plain.kerning, expected,
                    "{name} must use fitted geometry at every Gray depth"
                );
            }
            reference = Some(plain.kerning.clone());
            let altered = Config {
                gray_gamma: 2.0,
                mono_threshold: 230,
                ..original
            };
            let changed = generate(&altered, method(name), 0.0);
            assert_eq!(
                plain.kerning, changed.kerning,
                "{name} cannot infer walls from gamma or a coverage threshold"
            );
        }
    }
}

#[test]
fn methods_complete_pair_tables_before_tracking_preview_and_export() {
    let text = "ca en os nx AV";
    let config = config(text, 1);
    for name in ["hu_hersch", "hu_hersch_half", "fontforge"] {
        let plain = generate(&config, method(name), 0.0);
        let source = generate(&config, KerningMethod::Source, 0.0);
        assert_eq!(
            plain.glyphs, source.glyphs,
            "{name} may change placement only"
        );
        let tracked = generate(&config, method(name), 1.0);
        assert_eq!(
            plain.kerning, tracked.kerning,
            "tracking must not recalibrate {name}"
        );
        for (a, b) in plain.glyphs.iter().zip(&tracked.glyphs) {
            assert_eq!(b.advance_26_6 - a.advance_26_6, 64);
            assert_eq!((a.left, a.top, &a.pixels), (b.left, b.top, &b.pixels));
        }
        let advances: HashMap<_, _> = tracked
            .glyphs
            .iter()
            .map(|glyph| (glyph.codepoint, glyph.advance_26_6))
            .collect();
        let pairs = pair_map(&tracked);
        let codepoints: Vec<_> = text.chars().map(u32::from).collect();
        let expected = codepoints.iter().map(|cp| advances[cp]).sum::<i32>()
            + codepoints
                .windows(2)
                .map(|p| pairs.get(&(p[0], p[1])).copied().unwrap_or(0))
                .sum::<i32>();
        let request = TextRenderRequest {
            config: config.clone(),
            text: text.into(),
            width: 1000,
            height: 100,
            wrap: WrapMode::Clip,
            align: Default::default(),
            foreground: [0, 0, 0, 255],
            background: [255, 255, 255, 255],
            palette: None,
        };
        let preview = surface::render_text_with_pipeline_and_kerning(
            data(),
            &request,
            pipeline(1),
            1.0,
            method(name),
        )
        .unwrap();
        assert_eq!(
            preview.lines[0].width_26_6, expected,
            "{name} preview consumes the completed export table once"
        );
        let export = playdate::export(
            data(),
            &playdate::ExportRequest {
                config: config.clone(),
                pipeline: pipeline(1),
                letter_spacing_px: 1.0,
                kerning_method: method(name),
            },
        )
        .unwrap();
        assert_eq!(export, playdate::encode(&tracked).unwrap());
    }
}

#[test]
fn disabled_analytic_methods_are_exact_source_without_postsolve_feasibility_changes() {
    for name in ["fontforge", "hu_hersch"] {
        let disabled = serde_json::from_value(serde_json::json!({
            "method": name, "strength": 0.0,
        }))
        .unwrap();
        for bits in [1, 3] {
            for source_enabled in [false, true] {
                for tracking in [-1., 0., 1.] {
                    let config = Config {
                        kerning: source_enabled,
                        ..config("AV ff ca", bits)
                    };
                    assert_eq!(
                        generate(&config, disabled, tracking),
                        generate(&config, KerningMethod::Source, tracking)
                    );
                }
            }
        }
    }
}

#[test]
fn hu_legacy_endpoint_and_invalid_strength_on_blank_reused_fonts() {
    for bits in [1, 3] {
        let config = config("AV ca en os 012", bits);
        assert_eq!(
            generate(&config, method("hu_hersch"), 0.),
            generate(
                &config,
                KerningMethod::HuHersch(HuHerschSettings { strength: 1. }),
                0.
            )
        );
        let prepared = surface::PreparedFont::new(data().to_vec());
        let req = TextRenderRequest {
            config: config.clone(),
            text: "".into(),
            width: 64,
            height: 32,
            wrap: WrapMode::Clip,
            align: Default::default(),
            foreground: [0, 0, 0, 255],
            background: [255, 255, 255, 255],
            palette: None,
        };
        let source = prepared
            .render_text_with_pipeline_and_kerning(&req, pipeline(bits), 0., KerningMethod::Source)
            .unwrap();
        assert_eq!(
            prepared
                .render_text_with_pipeline_and_kerning(
                    &req,
                    pipeline(bits),
                    0.,
                    KerningMethod::HuHersch(HuHerschSettings { strength: 0. })
                )
                .unwrap(),
            source
        );
        for strength in [-0.1, 1.1, f64::NAN, f64::INFINITY] {
            let invalid = KerningMethod::HuHersch(HuHerschSettings { strength });
            assert!(prepared
                .render_text_with_pipeline_and_kerning(&req, pipeline(bits), 0., invalid)
                .is_err());
            let blank = Config {
                characters: String::new(),
                ..config.clone()
            };
            assert!(candidate::generate_bitmap_font_with_pipeline_and_kerning(
                data(),
                &blank,
                pipeline(bits),
                0.,
                invalid
            )
            .is_err());
        }
    }
}

#[test]
fn mono_methods_allow_contact_without_occupied_cell_overlap_or_row_inversion() {
    let config = config("abcdefghijklmnopqrstuvwxyz", 1);
    for name in ["hu_hersch", "hu_hersch_half", "fontforge"] {
        let font = generate(&config, method(name), 0.0);
        for a in &font.glyphs {
            for b in &font.glyphs {
                let left = char::from_u32(a.codepoint).unwrap();
                let right = char::from_u32(b.codepoint).unwrap();
                let step = pair_step(&font, left, right) / 64;
                for ay in 0..a.height as usize {
                    let y = a.top + ay as i32;
                    let by = y - b.top;
                    if by < 0 || by >= b.height as i32 {
                        continue;
                    }
                    let arow = &a.pixels[ay * a.width as usize..(ay + 1) * a.width as usize];
                    let by = by as usize;
                    let brow = &b.pixels[by * b.width as usize..(by + 1) * b.width as usize];
                    // An independent cell oracle checks actual occupied integer
                    // locations. Adjacency at x+1 remains permitted.
                    for (ax, _) in arow.iter().enumerate().filter(|(_, ink)| **ink != 0) {
                        for (bx, _) in brow.iter().enumerate().filter(|(_, ink)| **ink != 0) {
                            assert_ne!(
                                a.left + ax as i32,
                                step + b.left + bx as i32,
                                "{name}: {left}{right} overlaps at row {y}"
                            );
                        }
                    }
                    if let (Some(aright), Some(bleft)) = (
                        arow.iter().rposition(|ink| *ink != 0),
                        brow.iter().position(|ink| *ink != 0),
                    ) {
                        assert!(
                            a.left + aright as i32 + 1 <= step + b.left + bleft as i32,
                            "{name}: {left}{right} reverses facing walls at row {y}"
                        );
                    }
                }
            }
        }
    }
}
