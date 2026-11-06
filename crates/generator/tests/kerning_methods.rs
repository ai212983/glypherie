//! Method selection resolves complete pair adjustments before shared placement.
use font_generator::{FontforgeSettings, HuHerschSettings, KerningMethod, TypefacetSettings};

#[test]
fn hu_depth_defaults_legacy_requests_and_validates_finite_range() {
    let legacy: KerningMethod =
        serde_json::from_value(serde_json::json!({"method":"hu_hersch"})).unwrap();
    assert_eq!(legacy, KerningMethod::HuHersch(HuHerschSettings::default()));
    // The retired `strength` blend is rejected, never loaded as defaults.
    for strength in [
        serde_json::json!(0.0),
        serde_json::json!(0.35),
        serde_json::json!(1.0),
        serde_json::json!(null),
        serde_json::json!("0.35"),
        serde_json::json!(true),
    ] {
        assert!(
            serde_json::from_value::<KerningMethod>(
                serde_json::json!({"method":"hu_hersch","strength":strength})
            )
            .is_err(),
            "hu_hersch strength {strength} must not parse"
        );
    }
    for (aperture, global) in [(0.0, 0.0), (0.21, 0.25), (0.35, 0.4), (1.0, 1.0)] {
        let method = KerningMethod::HuHersch(HuHerschSettings {
            aperture_depth_factor: aperture,
            global_depth_factor: global,
        });
        method.validate(true).unwrap();
        assert!(method.validate(false).is_err());
        assert_eq!(
            serde_json::from_value::<KerningMethod>(serde_json::to_value(method).unwrap()).unwrap(),
            method
        );
    }
    for (aperture, global) in [
        (-0.01, 0.25),
        (0.21, 1.01),
        (f64::NAN, 0.25),
        (0.21, f64::INFINITY),
        (f64::NEG_INFINITY, f64::NEG_INFINITY),
    ] {
        assert!(KerningMethod::HuHersch(HuHerschSettings {
            aperture_depth_factor: aperture,
            global_depth_factor: global,
        })
        .validate(true)
        .is_err());
    }
    // Unknown siblings still fail alongside the retired key.
    for value in [
        serde_json::json!({"method":"hu_hersch","aperture_depth_factor":0.21,"unknown":true}),
        serde_json::json!({"method":"hu_hersch","aperture_depth_factor":"0.21","global_depth_factor":0.25}),
    ] {
        assert!(serde_json::from_value::<KerningMethod>(value).is_err());
    }
}

#[test]
fn fontforge_rejects_strength_and_keeps_the_parameterless_method() {
    let current: KerningMethod =
        serde_json::from_value(serde_json::json!({"method":"fontforge"})).unwrap();
    assert_eq!(
        current,
        KerningMethod::Fontforge(FontforgeSettings::default())
    );
    current.validate(true).unwrap();
    for rejected in [
        serde_json::json!({"method":"fontforge","strength":0.0}),
        serde_json::json!({"method":"fontforge","strength":0.35}),
        serde_json::json!({"method":"fontforge","strength":1.0}),
        serde_json::json!({"method":"fontforge","strength":null}),
        serde_json::json!({"method":"fontforge","strength":"1"}),
        serde_json::json!({"method":"fontforge","target":0}),
    ] {
        assert!(
            serde_json::from_value::<KerningMethod>(rejected).is_err(),
            "fontforge strength must not parse"
        );
    }
}

#[test]
fn method_wire_is_closed_and_keeps_source_default() {
    assert_eq!(KerningMethod::default(), KerningMethod::Source);
    for method in [
        KerningMethod::Source,
        KerningMethod::Typefacet(TypefacetSettings::default()),
    ] {
        let value = serde_json::to_value(method).unwrap();
        assert_eq!(
            serde_json::from_value::<KerningMethod>(value).unwrap(),
            method
        );
    }
    for value in [
        serde_json::json!({"method":"unknown"}),
        serde_json::json!({"method":"source","normal_distance_em":0.1}),
        serde_json::json!({"method":"typefacet","normal_distance_em":0.1,"intrusion_tolerance_em":0.1,"unknown":true}),
    ] {
        assert!(serde_json::from_value::<KerningMethod>(value).is_err());
    }
}

#[test]
fn typefacet_new_controls_default_legacy_requests_and_validate_cross_field_bounds() {
    let legacy: KerningMethod = serde_json::from_value(serde_json::json!({
        "method": "typefacet", "normal_distance_em": 0.1, "intrusion_tolerance_em": 0.1,
    }))
    .unwrap();
    assert_eq!(
        legacy,
        KerningMethod::Typefacet(TypefacetSettings::default())
    );
    let configured: KerningMethod = serde_json::from_value(serde_json::json!({
        "method": "typefacet", "normal_distance_em": 0.2, "intrusion_tolerance_em": 0.05,
        "minimum_distance_em": 0.075, "max_x_extrema_overlap_em": 0.25,
    }))
    .unwrap();
    configured.validate(true).unwrap();
    assert_eq!(
        serde_json::from_value::<KerningMethod>(serde_json::to_value(configured).unwrap()).unwrap(),
        configured
    );
    let base = TypefacetSettings::default();
    for invalid in [
        TypefacetSettings {
            minimum_distance_em: -0.001,
            ..base
        },
        TypefacetSettings {
            minimum_distance_em: 0.101,
            ..base
        },
        TypefacetSettings {
            minimum_distance_em: f64::NAN,
            ..base
        },
        TypefacetSettings {
            minimum_distance_em: f64::INFINITY,
            ..base
        },
        TypefacetSettings {
            max_x_extrema_overlap_em: -0.001,
            ..base
        },
        TypefacetSettings {
            max_x_extrema_overlap_em: 0.501,
            ..base
        },
        TypefacetSettings {
            max_x_extrema_overlap_em: f64::NAN,
            ..base
        },
        TypefacetSettings {
            max_x_extrema_overlap_em: f64::INFINITY,
            ..base
        },
    ] {
        assert!(KerningMethod::Typefacet(invalid).validate(true).is_err());
    }
    for allowed in [
        TypefacetSettings {
            minimum_distance_em: 0.1,
            max_x_extrema_overlap_em: 0.0,
            ..base
        },
        TypefacetSettings {
            minimum_distance_em: 0.1,
            max_x_extrema_overlap_em: 0.5,
            ..base
        },
    ] {
        KerningMethod::Typefacet(allowed).validate(true).unwrap();
    }
}

#[cfg(feature = "candidate")]
mod runtime {
    use super::*;
    use font_generator::{
        candidate, playdate,
        renderer::{Rasterization, RenderPipeline},
        stem_fitting::StemFittingStrategy,
        surface::{self, TextRenderRequest, WrapMode},
        Config,
    };
    use std::collections::HashMap;

    fn data() -> &'static [u8] {
        include_bytes!("../../../fonts/Literata.ttf")
    }
    fn request(text: &str) -> TextRenderRequest {
        TextRenderRequest {
            config: Config {
                size_px: 16.0,
                ..Config::default()
            },
            text: text.into(),
            width: 1000,
            height: 100,
            wrap: WrapMode::Clip,
            align: Default::default(),
            foreground: [0, 0, 0, 255],
            background: [255, 255, 255, 255],
            palette: None,
        }
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
    fn method() -> KerningMethod {
        KerningMethod::Typefacet(TypefacetSettings::default())
    }

    #[test]
    fn nondefault_minimum_and_overlap_reach_preview_and_export_without_changing_glyphs() {
        let text = "AVTa nn";
        let settings = TypefacetSettings {
            minimum_distance_em: 0.1,
            max_x_extrema_overlap_em: 0.25,
            ..Default::default()
        };
        for bits in [1, 3] {
            let req = TextRenderRequest {
                config: Config {
                    output_bits: bits,
                    ..request(text).config
                },
                ..request(text)
            };
            let config = Config {
                characters: text.into(),
                ..req.config.clone()
            };
            let pipeline = pipeline(bits);
            let generate = |settings| {
                candidate::generate_bitmap_font_with_pipeline_and_kerning(
                    data(),
                    &config,
                    pipeline,
                    0.0,
                    KerningMethod::Typefacet(settings),
                )
                .unwrap()
            };
            let before = generate(TypefacetSettings::default());
            let after = generate(settings);
            assert_eq!(before.glyphs, after.glyphs);
            assert_ne!(
                before.kerning, after.kerning,
                "nondefault controls must reach the solver at depth{bits}"
            );
            let advances: HashMap<_, _> = after
                .glyphs
                .iter()
                .map(|g| (g.codepoint, g.advance_26_6))
                .collect();
            let pairs: HashMap<_, _> = after
                .kerning
                .iter()
                .map(|p| ((p.left, p.right), p.adjustment_26_6))
                .collect();
            let chars: Vec<_> = text.chars().map(u32::from).collect();
            let expected = chars.iter().map(|c| advances[c]).sum::<i32>()
                + chars
                    .windows(2)
                    .map(|p| pairs.get(&(p[0], p[1])).copied().unwrap_or(0))
                    .sum::<i32>();
            let selected = surface::render_text_with_pipeline_and_kerning(
                data(),
                &req,
                pipeline,
                0.0,
                KerningMethod::Typefacet(settings),
            )
            .unwrap();
            assert_eq!(selected.lines[0].width_26_6, expected);
            if bits == 1 {
                let exported = playdate::export(
                    data(),
                    &playdate::ExportRequest {
                        config,
                        pipeline,
                        letter_spacing_px: 0.0,
                        kerning_method: KerningMethod::Typefacet(settings),
                    },
                )
                .unwrap();
                assert_eq!(exported, playdate::encode(&after).unwrap());
            }
            let source = candidate::generate_bitmap_font_with_pipeline_and_kerning(
                data(),
                &after.config,
                pipeline,
                0.0,
                KerningMethod::Source,
            )
            .unwrap();
            assert_eq!(source.glyphs, after.glyphs);
        }
    }

    #[test]
    fn explicit_source_keeps_legacy_output_and_method_validation_precedes_blank_results() {
        let font = surface::PreparedFont::new(data().to_vec());
        for bits in [1, 2, 3, 4] {
            for text in ["", "AV type 09"] {
                let mut req = request(text);
                req.config.output_bits = bits;
                let pipeline = pipeline(bits);
                let source = font
                    .render_text_with_pipeline_and_spacing(&req, pipeline, 1.0)
                    .unwrap();
                assert_eq!(
                    source,
                    font.render_text_with_pipeline_and_kerning(
                        &req,
                        pipeline,
                        1.0,
                        KerningMethod::Source
                    )
                    .unwrap()
                );
                // A previous successful capture and source result cannot mask
                // invalid selected-method settings, including on blank text.
                for invalid in [
                    TypefacetSettings {
                        normal_distance_em: f64::NAN,
                        ..Default::default()
                    },
                    TypefacetSettings {
                        minimum_distance_em: 0.101,
                        ..Default::default()
                    },
                    TypefacetSettings {
                        minimum_distance_em: f64::NAN,
                        ..Default::default()
                    },
                    TypefacetSettings {
                        max_x_extrema_overlap_em: 0.501,
                        ..Default::default()
                    },
                    TypefacetSettings {
                        max_x_extrema_overlap_em: f64::NAN,
                        ..Default::default()
                    },
                ] {
                    assert!(font
                        .render_text_with_pipeline_and_kerning(
                            &req,
                            pipeline,
                            0.0,
                            KerningMethod::Typefacet(invalid)
                        )
                        .is_err());
                }
                let active = font
                    .render_text_with_pipeline_and_kerning(&req, pipeline, 1.0, method())
                    .unwrap();
                if text.is_empty() {
                    assert!(active.lines.is_empty());
                }
                assert_eq!(
                    source,
                    font.render_text_with_pipeline_and_spacing(&req, pipeline, 1.0)
                        .unwrap(),
                    "method switching must not alter subsequent source output"
                );
            }
        }
    }

    #[test]
    fn preview_export_and_tracking_consume_the_same_untracked_pair_table() {
        let text = "nn oo tt rf type";
        let req = request(text);
        let pipeline = RenderPipeline::default();
        let config = Config {
            characters: text.into(),
            ..req.config.clone()
        };
        let untracked = candidate::generate_monochrome_font_with_pipeline_and_kerning(
            data(),
            &config,
            pipeline,
            0.0,
            method(),
        )
        .unwrap();
        let tracked = candidate::generate_monochrome_font_with_pipeline_and_kerning(
            data(),
            &config,
            pipeline,
            1.0,
            method(),
        )
        .unwrap();
        assert_eq!(
            untracked.kerning, tracked.kerning,
            "tracking must not enter TypeFacet's pair search"
        );
        for (a, b) in untracked.glyphs.iter().zip(&tracked.glyphs) {
            assert_eq!((a.left, a.top, &a.pixels), (b.left, b.top, &b.pixels));
            assert_eq!(b.advance_26_6 - a.advance_26_6, 64);
        }
        let advances: HashMap<_, _> = tracked
            .glyphs
            .iter()
            .map(|g| (g.codepoint, g.advance_26_6))
            .collect();
        let pairs: HashMap<_, _> = tracked
            .kerning
            .iter()
            .map(|p| ((p.left, p.right), p.adjustment_26_6))
            .collect();
        let chars: Vec<_> = text.chars().map(u32::from).collect();
        let expected: i32 = chars.iter().map(|c| advances[c]).sum::<i32>()
            + chars
                .windows(2)
                .map(|p| pairs.get(&(p[0], p[1])).copied().unwrap_or(0))
                .sum::<i32>();
        let preview =
            surface::render_text_with_pipeline_and_kerning(data(), &req, pipeline, 1.0, method())
                .unwrap();
        assert_eq!(preview.lines[0].width_26_6, expected);
        let export = playdate::export(
            data(),
            &playdate::ExportRequest {
                config,
                pipeline,
                letter_spacing_px: 1.0,
                kerning_method: method(),
            },
        )
        .unwrap();
        assert_eq!(export, playdate::encode(&tracked).unwrap());
        let source = candidate::generate_monochrome_font_with_pipeline(
            data(),
            &untracked.config,
            pipeline,
            0.0,
        )
        .unwrap();
        assert_ne!(
            source.kerning, untracked.kerning,
            "the selected method must reach the shared pair resolver"
        );
    }

    // Derived fixture: retain Literata outlines and replace every horizontal
    // metric with one 1000-unit cell and an explicit post.isFixedPitch declaration.
    // This isolates the font-level fixed-grid contract from glyph proportions.
    fn uniform_advance_fixture(fixed_pitch: bool) -> Vec<u8> {
        let mut bytes = data().to_vec();
        let u16_at =
            |data: &[u8], at: usize| u16::from_be_bytes(data[at..at + 2].try_into().unwrap());
        let u32_at =
            |data: &[u8], at: usize| u32::from_be_bytes(data[at..at + 4].try_into().unwrap());
        let tables: Vec<_> = (0..usize::from(u16_at(&bytes, 4)))
            .map(|i| {
                let entry = 12 + i * 16;
                (
                    entry,
                    bytes[entry..entry + 4].to_vec(),
                    u32_at(&bytes, entry + 8) as usize,
                    u32_at(&bytes, entry + 12) as usize,
                )
            })
            .collect();
        let offset = |tag: &[u8]| tables.iter().find(|t| t.1 == tag).unwrap().2;
        let post = offset(b"post");
        bytes[post + 12..post + 16].copy_from_slice(&u32::from(fixed_pitch).to_be_bytes());
        let hhea = offset(b"hhea");
        let count = usize::from(u16_at(&bytes, hhea + 34));
        bytes[hhea + 10..hhea + 12].copy_from_slice(&1000u16.to_be_bytes());
        let hmtx = offset(b"hmtx");
        for i in 0..count {
            bytes[hmtx + i * 4..hmtx + i * 4 + 2].copy_from_slice(&1000u16.to_be_bytes());
        }
        let head = offset(b"head");
        bytes[head + 8..head + 12].fill(0);
        let checksum = |data: &[u8]| {
            data.chunks(4).fold(0u32, |sum, chunk| {
                let mut word = [0u8; 4];
                word[..chunk.len()].copy_from_slice(chunk);
                sum.wrapping_add(u32::from_be_bytes(word))
            })
        };
        for (entry, _, at, len) in tables {
            let sum = checksum(&bytes[at..at + len]);
            bytes[entry + 4..entry + 8].copy_from_slice(&sum.to_be_bytes());
        }
        let adjustment = 0xB1B0_AFBAu32.wrapping_sub(checksum(&bytes));
        bytes[head + 8..head + 12].copy_from_slice(&adjustment.to_be_bytes());
        bytes
    }

    #[test]
    fn fixed_pitch_all_pairs_and_preview_keep_the_source_grid() {
        let bytes = uniform_advance_fixture(true);
        for bits in [1, 2, 3, 4] {
            let mut req = request("abcdefghijklmnopqrstuvwxyz ");
            req.config.kerning = false;
            req.config.output_bits = bits;
            let config = Config {
                characters: req.text.clone(),
                ..req.config.clone()
            };
            assert!(
                font_generator::mono_spacing::font_spacing_properties(&bytes, &config)
                    .unwrap()
                    .monospace
            );
            let source = candidate::generate_bitmap_font_with_pipeline_and_kerning(
                &bytes,
                &config,
                pipeline(bits),
                0.0,
                KerningMethod::Source,
            )
            .unwrap();
            let selected = candidate::generate_bitmap_font_with_pipeline_and_kerning(
                &bytes,
                &config,
                pipeline(bits),
                0.0,
                method(),
            )
            .unwrap();
            assert_eq!(
                source, selected,
                "all pairs retain the fixed-pitch table at depth {bits}"
            );
            assert!(selected.kerning.is_empty());
            assert!(selected.glyphs.iter().all(|g| g.advance_26_6 == 16 * 64));
            let plain =
                surface::render_text_with_pipeline_and_spacing(&bytes, &req, pipeline(bits), 0.0)
                    .unwrap();
            let chosen = surface::render_text_with_pipeline_and_kerning(
                &bytes,
                &req,
                pipeline(bits),
                0.0,
                method(),
            )
            .unwrap();
            assert_eq!(
                plain, chosen,
                "fixed-grid glyph images and placement are unchanged at depth {bits}"
            );
            assert_eq!(chosen.lines[0].width_26_6, 27 * 16 * 64);
        }
    }

    #[test]
    fn hu_depths_preserve_fixed_pitch_and_tabular_fallbacks() {
        for fixed_pitch in [false, true] {
            let bytes = uniform_advance_fixture(fixed_pitch);
            for bits in [1, 3] {
                let config = Config {
                    characters: if fixed_pitch {
                        "acAV012 "
                    } else {
                        "0123456789 "
                    }
                    .into(),
                    size_px: 16.,
                    output_bits: bits,
                    ..Config::default()
                };
                let generate = |method| {
                    candidate::generate_bitmap_font_with_pipeline_and_kerning(
                        &bytes,
                        &config,
                        pipeline(bits),
                        0.,
                        method,
                    )
                    .unwrap()
                };
                let source = generate(KerningMethod::Source);
                for settings in [
                    HuHerschSettings::default(),
                    HuHerschSettings {
                        aperture_depth_factor: 0.35,
                        global_depth_factor: 0.4,
                    },
                ] {
                    assert_eq!(generate(KerningMethod::HuHersch(settings)), source);
                }
            }
        }
    }

    #[test]
    fn space_and_tabular_pairs_keep_source_fallback_at_every_depth() {
        let text = "AV 0123456789";
        let bytes = uniform_advance_fixture(false);
        for bits in [1, 2, 3, 4] {
            let mut config = Config {
                characters: text.into(),
                ..request(text).config
            };
            config.output_bits = bits;
            let properties =
                font_generator::mono_spacing::font_spacing_properties(&bytes, &config).unwrap();
            assert!(
                properties.tabular_digits,
                "fixture supplies all ten equal-width source digits"
            );
            let source = candidate::generate_bitmap_font_with_pipeline_and_kerning(
                &bytes,
                &config,
                pipeline(bits),
                0.0,
                KerningMethod::Source,
            )
            .unwrap();
            let selected = candidate::generate_bitmap_font_with_pipeline_and_kerning(
                &bytes,
                &config,
                pipeline(bits),
                0.0,
                method(),
            )
            .unwrap();
            assert_eq!(source.glyphs, selected.glyphs);
            let pair_map = |font: &font_generator::GeneratedFont| {
                font.kerning
                    .iter()
                    .map(|p| ((p.left, p.right), p.adjustment_26_6))
                    .collect::<HashMap<_, _>>()
            };
            let (a, b) = (pair_map(&source), pair_map(&selected));
            for left in text.chars().map(u32::from) {
                for right in text.chars().map(u32::from) {
                    if left == 32
                        || right == 32
                        || ((48..=57).contains(&left) && (48..=57).contains(&right))
                    {
                        assert_eq!(
                            a.get(&(left, right)),
                            b.get(&(left, right)),
                            "fallback pair {left} {right}, depth {bits}"
                        );
                    }
                }
            }
        }
    }

    #[test]
    fn all_depths_resolve_mixed_case_and_non_ascii_without_changing_glyph_images() {
        let text = "AV To Éé ty";
        for bits in [1, 2, 3, 4] {
            let mut config = Config {
                characters: text.into(),
                ..request(text).config
            };
            config.output_bits = bits;
            let source = candidate::generate_bitmap_font_with_pipeline_and_kerning(
                data(),
                &config,
                pipeline(bits),
                0.0,
                KerningMethod::Source,
            )
            .unwrap();
            let selected = candidate::generate_bitmap_font_with_pipeline_and_kerning(
                data(),
                &config,
                pipeline(bits),
                0.0,
                method(),
            )
            .unwrap();
            assert_eq!(
                source.glyphs, selected.glyphs,
                "method only changes pair placement at depth {bits}"
            );
            assert_ne!(source.kerning, selected.kerning);
            assert!(
                selected
                    .kerning
                    .iter()
                    .any(|p| p.left > 127 || p.right > 127),
                "accented letters must reach the method at depth {bits}"
            );
            let source_pairs: HashMap<_, _> = source
                .kerning
                .iter()
                .map(|p| ((p.left, p.right), p.adjustment_26_6))
                .collect();
            assert!(
                selected.kerning.iter().any(|p| ((65..=90).contains(&p.left)
                    || (65..=90).contains(&p.right))
                    && source_pairs.get(&(p.left, p.right)).copied().unwrap_or(0)
                        != p.adjustment_26_6),
                "uppercase/mixed pairs must use the method at depth {bits}"
            );
        }
    }

    #[test]
    fn fitted_profile_geometry_accepts_literata_curve_shapes() {
        for ch in "AVtype09Ééminu".chars() {
            let config = Config {
                characters: ch.to_string(),
                output_bits: 2,
                ..request("").config
            };
            candidate::generate_bitmap_font_with_pipeline_and_kerning(
                data(),
                &config,
                pipeline(2),
                0.0,
                method(),
            )
            .unwrap_or_else(|error| {
                let report = candidate::render_with_pipeline(
                    data(),
                    &font_generator::reference::ReferenceRequest {
                        profile: "gray_3bit".into(),
                        extensions: font_generator::stem_fitting::EXTENSIONS_MONO_WIDTH_01.into(),
                        settings: Config {
                            hinting: font_generator::Hinting::Auto,
                            ..config.clone()
                        },
                    },
                    pipeline(2),
                )
                .unwrap();
                panic!(
                    "Literata16 Gray2 U+{:04X} {ch:?}: {error}; paths {:?}",
                    u32::from(ch),
                    report.records[0].fitted_commands
                )
            });
        }
    }

    #[test]
    fn gray_pair_tables_use_fitted_geometry_independently_of_coverage_quantization() {
        let text = "AV To Éé minimum";
        let mut reference = None;
        for bits in [2, 3, 4] {
            let mut config = Config {
                characters: text.into(),
                ..request(text).config
            };
            config.output_bits = bits;
            let original = candidate::generate_bitmap_font_with_pipeline_and_kerning(
                data(),
                &config,
                pipeline(bits),
                0.0,
                method(),
            )
            .unwrap();
            if let Some(expected) = &reference {
                assert_eq!(
                    &original.kerning, expected,
                    "Gray output depth must not alter fitted-outline pair computation"
                );
            }
            reference = Some(original.kerning.clone());
            config.gray_gamma = 2.0;
            config.mono_threshold = 230;
            let changed = candidate::generate_bitmap_font_with_pipeline_and_kerning(
                data(),
                &config,
                pipeline(bits),
                0.0,
                method(),
            )
            .unwrap();
            assert_eq!(
                original.kerning, changed.kerning,
                "quantization cannot enter pair geometry"
            );
            assert!(
                original
                    .glyphs
                    .iter()
                    .zip(&changed.glyphs)
                    .any(|(a, b)| a.pixels != b.pixels),
                "fixture must actually exercise changed gray coverage"
            );
            let tracked = candidate::generate_bitmap_font_with_pipeline_and_kerning(
                data(),
                &config,
                pipeline(bits),
                1.0,
                method(),
            )
            .unwrap();
            assert_eq!(changed.kerning, tracked.kerning);
            let mut req = request(text);
            req.config = config;
            let plain = surface::render_text_with_pipeline_and_kerning(
                data(),
                &req,
                pipeline(bits),
                0.0,
                method(),
            )
            .unwrap();
            let shifted = surface::render_text_with_pipeline_and_kerning(
                data(),
                &req,
                pipeline(bits),
                1.0,
                method(),
            )
            .unwrap();
            assert_eq!(
                shifted.lines[0].width_26_6 - plain.lines[0].width_26_6,
                text.chars().count() as i32 * 64
            );
            let pair_map: HashMap<_, _> = tracked
                .kerning
                .iter()
                .map(|p| ((p.left, p.right), p.adjustment_26_6))
                .collect();
            let advances: HashMap<_, _> = tracked
                .glyphs
                .iter()
                .map(|g| (g.codepoint, g.advance_26_6))
                .collect();
            let chars: Vec<_> = text.chars().map(u32::from).collect();
            let expected: i32 = chars.iter().map(|cp| advances[cp]).sum::<i32>()
                + chars
                    .windows(2)
                    .map(|p| pair_map.get(&(p[0], p[1])).copied().unwrap_or(0))
                    .sum::<i32>();
            assert_eq!(
                shifted.lines[0].width_26_6, expected,
                "Gray strike and preview share finalized placement"
            );
        }
    }
}
