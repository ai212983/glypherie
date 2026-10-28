#![cfg(feature = "candidate")]
use font_generator::{
    candidate,
    reference::{RasterPolicy, ReferenceRequest},
    renderer::{Rasterization, RenderPipeline, RendererRole},
    stem_fitting::StemFittingStrategy,
    surface::{self, HAlign, TextRenderRequest, WrapMode},
    Config, Hinting, MonoRasterSettings,
};

fn font(name: &str) -> Vec<u8> {
    std::fs::read(format!(
        "{}/../../fonts/{name}.ttf",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap()
}

fn request(size: f32, bits: u8) -> TextRenderRequest {
    TextRenderRequest {
        config: Config {
            size_px: size,
            output_bits: bits,
            hinting: Hinting::Auto,
            ..Config::default()
        },
        text: "AV To zxcekw 909192939495969798\n09192939495969798".into(),
        width: 110,
        height: 160,
        wrap: WrapMode::Word,
        align: HAlign::Left,
        foreground: [0, 0, 0, 255],
        background: [255, 255, 255, 255],
        palette: None,
    }
}

#[test]
fn scanner_choice_preserves_fitting_metrics_and_line_layout() {
    // FreeType glyph metric convention: advances and bearings belong to the
    // fitted glyph, not to the scan converter. Compare both scanners using
    // the same fitting inputs, including a font with embedded TT instructions
    // and fonts whose default resolves to automatic fitting.
    let mut changed_pixels = false;
    for name in ["Roboto", "SourceSans3", "Literata"] {
        let data = font(name);
        for size in [12.0, 16.0, 20.0] {
            for fitting in [
                StemFittingStrategy::FontHintsFirst,
                StemFittingStrategy::UpstreamMono,
            ] {
                let text = request(size, 1);
                let capture = ReferenceRequest {
                    profile: "mono_1bit".into(),
                    extensions: StemFittingStrategy::extension(Some(fitting)).into(),
                    settings: Config {
                        characters: text.text.replace('\n', ""),
                        ..text.config.clone()
                    },
                };
                let mono = candidate::render_with_rasterization(
                    &data,
                    &capture,
                    Rasterization::FreeTypeMono,
                )
                .unwrap();
                let coverage =
                    candidate::render_with_rasterization(&data, &capture, Rasterization::Coverage)
                        .unwrap();
                for (a, b) in mono.records.iter().zip(&coverage.records) {
                    assert_eq!(a.raster_policy, RasterPolicy::FreeTypeMono);
                    assert_eq!(b.raster_policy, RasterPolicy::Coverage);
                    assert_eq!(
                        a.fitted_commands, b.fitted_commands,
                        "{name} {size} {fitting:?}"
                    );
                    assert_eq!(a.selected_engine, b.selected_engine);
                    assert_eq!(a.advance_26_6, b.advance_26_6);
                    assert_eq!(a.hinted_advance_width, b.hinted_advance_width);
                    assert_eq!(a.hinted_lsb, b.hinted_lsb);
                    assert_eq!(a.side_bearing_deltas_26_6, b.side_bearing_deltas_26_6);
                    assert_eq!(
                        (a.left, a.top, a.width, a.height),
                        (b.left, b.top, b.width, b.height)
                    );
                    assert_eq!(a.coverage, b.coverage);
                    changed_pixels |= a.pixels != b.pixels;
                }
                let a = surface::render_text_with_pipeline(
                    &data,
                    &text,
                    RenderPipeline {
                        fitting,
                        rasterization: Rasterization::FreeTypeMono,
                        diagonal_fitting: false,
                    },
                )
                .unwrap();
                let b = surface::render_text_with_pipeline(
                    &data,
                    &text,
                    RenderPipeline {
                        fitting,
                        rasterization: Rasterization::Coverage,
                        diagonal_fitting: false,
                    },
                )
                .unwrap();
                assert_eq!(
                    a.lines, b.lines,
                    "scanner must not change wrapping or line widths"
                );
                assert_eq!(a.missing_codepoints, b.missing_codepoints);
                let legacy = surface::render_text_with_fitting_strategy(
                    &data,
                    &text,
                    RendererRole::Candidate,
                    0.0,
                    Some(fitting),
                )
                .unwrap();
                assert_eq!(
                    a, legacy,
                    "default stages retain the existing candidate output"
                );
            }
        }
    }
    assert!(
        changed_pixels,
        "the scanner comparison must exercise different delivered pixels"
    );
}

#[test]
fn explicit_depths_share_fitting_and_layout_with_depth_only_quantization() {
    // Palette depths share upstream Normal fitting and bitmap layout at
    // 2/3/4 bits; only quantization levels change.
    let data = font("Roboto");
    let gray = RenderPipeline {
        fitting: StemFittingStrategy::UpstreamMono,
        rasterization: Rasterization::Coverage,
        diagonal_fitting: false,
    };
    let mut baseline_lines = None;
    for bits in [2u8, 3, 4] {
        let capture = ReferenceRequest {
            profile: "gray_3bit".into(),
            extensions: StemFittingStrategy::extension(Some(StemFittingStrategy::UpstreamMono))
                .into(),
            settings: Config {
                characters: "AV To".into(),
                size_px: 16.0,
                output_bits: bits,
                hinting: Hinting::Auto,
                ..Config::default()
            },
        };
        let report =
            candidate::render_with_rasterization(&data, &capture, Rasterization::Coverage).unwrap();
        assert_eq!(
            report.extensions, "mono-width-01",
            "explicit depths stamp the requested fitting"
        );
        assert_eq!(report.hinting_requested, "auto");
        let levels = 1u16 << bits;
        for record in &report.records {
            assert_eq!(record.output_bits, bits);
            assert!(
                record.pixels.iter().all(|&p| u16::from(p) < levels),
                "every level stays inside {bits}-bit membership"
            );
        }
        let text = request(16.0, bits);
        let rendered = surface::render_text_with_pipeline(&data, &text, gray).unwrap();
        if baseline_lines.is_none() {
            baseline_lines = Some(rendered.lines.clone());
        } else {
            assert_eq!(
                rendered.lines,
                baseline_lines.clone().unwrap(),
                "layout is depth-independent at {bits} bits"
            );
        }
    }
    let three = ReferenceRequest {
        profile: "gray_3bit".into(),
        extensions: StemFittingStrategy::extension(Some(StemFittingStrategy::UpstreamMono)).into(),
        settings: Config {
            characters: "AV To".into(),
            size_px: 16.0,
            output_bits: 3,
            hinting: Hinting::Auto,
            ..Config::default()
        },
    };
    let three =
        candidate::render_with_rasterization(&data, &three, Rasterization::Coverage).unwrap();
    for bits in [2u8, 4] {
        let other = ReferenceRequest {
            profile: "gray_3bit".into(),
            extensions: StemFittingStrategy::extension(Some(StemFittingStrategy::UpstreamMono))
                .into(),
            settings: Config {
                characters: "AV To".into(),
                size_px: 16.0,
                output_bits: bits,
                hinting: Hinting::Auto,
                ..Config::default()
            },
        };
        let other =
            candidate::render_with_rasterization(&data, &other, Rasterization::Coverage).unwrap();
        assert_eq!(other.records.len(), three.records.len());
        for (a, b) in other.records.iter().zip(&three.records) {
            assert_eq!(a.codepoint, b.codepoint);
            assert_eq!(
                a.fitted_commands, b.fitted_commands,
                "U+{:04X} keeps its fitted outline",
                a.codepoint
            );
            assert_eq!(a.advance_26_6, b.advance_26_6);
            assert_eq!(a.side_bearing_deltas_26_6, b.side_bearing_deltas_26_6);
            assert_eq!(
                (a.left, a.top, a.width, a.height),
                (b.left, b.top, b.width, b.height)
            );
            assert_eq!(
                a.coverage, b.coverage,
                "quantization starts from identical coverage"
            );
        }
        assert_ne!(
            other.records.iter().map(|r| &r.pixels).collect::<Vec<_>>(),
            three.records.iter().map(|r| &r.pixels).collect::<Vec<_>>(),
            "{bits}-bit quantization actually requantizes levels"
        );
    }
}

#[test]
fn explicit_palette_shape_holds_including_blank_text() {
    let data = font("Roboto");
    let gray = RenderPipeline {
        fitting: StemFittingStrategy::UpstreamMono,
        rasterization: Rasterization::Coverage,
        diagonal_fitting: false,
    };
    let palette: Vec<[u8; 4]> = vec![
        [255, 255, 255, 255],
        [255, 0, 0, 255],
        [0, 255, 0, 255],
        [0, 0, 0, 255],
    ];
    for text in ["A", ""] {
        let mut request = request(16.0, 2);
        request.text = text.into();
        request.palette = Some(palette.clone());
        let rendered = surface::render_text_with_pipeline(&data, &request, gray).unwrap();
        if text.is_empty() {
            assert!(rendered.lines.is_empty());
        }
        let allowed: std::collections::BTreeSet<[u8; 4]> = std::iter::once([255, 255, 255, 255])
            .chain(palette.iter().copied())
            .collect();
        for texel in rendered.pixels.chunks_exact(4) {
            let color = [texel[0], texel[1], texel[2], texel[3]];
            assert!(
                allowed.contains(&color),
                "every texel is a palette entry, got {color:?}"
            );
        }
    }
    // Shape is validated before any canvas work, even for blank text.
    for text in ["A", ""] {
        let mut request = request(16.0, 2);
        request.text = text.into();
        request.palette = Some(palette[..3].to_vec());
        assert!(surface::render_text_with_pipeline(&data, &request, gray).is_err());
    }
}

#[test]
fn explicit_depths_reject_deeper_bits_and_historical_role_extras() {
    let data = font("Roboto");
    let gray = RenderPipeline {
        fitting: StemFittingStrategy::UpstreamMono,
        rasterization: Rasterization::Coverage,
        diagonal_fitting: false,
    };
    for bits in [5u8, 8] {
        let text = request(16.0, bits);
        assert!(
            surface::render_text_with_pipeline(&data, &text, gray).is_err(),
            "explicit pipelines stop at 4 bits, got {bits}"
        );
    }
    // Historical preview roles keep their 1/3-bit profiles; palette depths
    // stay on the explicit pipeline.
    for bits in [2u8, 4] {
        let text = request(16.0, bits);
        assert!(surface::render_text_with_renderer(&data, &text, RendererRole::Candidate).is_err());
        assert!(surface::render_text_with_renderer(&data, &text, RendererRole::Reference).is_err());
        assert!(surface::render_text_with_fitting_strategy(
            &data,
            &text,
            RendererRole::Candidate,
            0.0,
            None
        )
        .is_err());
        assert!(candidate::generate_bitmap_font(&data, &text.config, None).is_err());
    }
    // Historical extras stay mono-only: fitting strategies, scan overrides
    // and the FreeType scanner never apply to palette depths.
    let mono_pipeline = RenderPipeline {
        fitting: StemFittingStrategy::FontHintsFirst,
        rasterization: Rasterization::FreeTypeMono,
        diagonal_fitting: false,
    };
    let text = request(16.0, 2);
    assert!(surface::render_text_with_pipeline(&data, &text, mono_pipeline).is_err());
    let fitting_first = RenderPipeline {
        fitting: StemFittingStrategy::FontHintsFirst,
        rasterization: Rasterization::Coverage,
        diagonal_fitting: false,
    };
    assert!(surface::render_text_with_pipeline(&data, &text, fitting_first).is_err());
    let mut scan = request(16.0, 2);
    scan.config.mono_raster = MonoRasterSettings {
        include_stubs: true,
        ..MonoRasterSettings::default()
    };
    assert!(surface::render_text_with_pipeline(&data, &scan, gray).is_err());
    assert!(surface::render_text_with_fitting_strategy(
        &data,
        &text,
        RendererRole::Candidate,
        0.0,
        Some(StemFittingStrategy::UpstreamMono),
    )
    .is_err());
    // Blank text runs the same gates.
    let mut blank = request(16.0, 4);
    blank.text = String::new();
    assert!(surface::render_text_with_pipeline(&data, &blank, gray).is_ok());
    assert!(surface::render_text_with_renderer(&data, &blank, RendererRole::Candidate).is_err());
}

#[test]
fn pipeline_validates_stages_even_for_blank_text_and_keeps_gray_candidate() {
    let data = font("Roboto");
    let mut text = request(16.0, 3);
    let gray = RenderPipeline {
        fitting: StemFittingStrategy::UpstreamMono,
        rasterization: Rasterization::Coverage,
        diagonal_fitting: false,
    };
    assert_eq!(
        surface::render_text_with_pipeline(&data, &text, gray).unwrap(),
        surface::render_text_with_fitting_strategy(
            &data,
            &text,
            RendererRole::Candidate,
            0.0,
            None
        )
        .unwrap()
    );
    for value in ["", "AV"] {
        text.text = value.into();
        assert!(
            surface::render_text_with_pipeline(&data, &text, RenderPipeline::default()).is_err()
        );
        text.config.output_bits = 1;
        text.config.mono_raster = MonoRasterSettings {
            include_stubs: true,
            ..MonoRasterSettings::default()
        };
        assert!(surface::render_text_with_pipeline(&data, &text, gray).is_err());
        text.config.output_bits = 3;
        text.config.mono_raster = MonoRasterSettings::default();
    }
    assert!(serde_json::from_str::<RenderPipeline>(
        r#"{"fitting":"font_hints_first","rasterization":"unknown"}"#
    )
    .is_err());
    assert!(serde_json::from_str::<RenderPipeline>(
        r#"{"fitting":"font_hints_first","rasterization":"coverage","layout":"source"}"#
    )
    .is_err());
}
