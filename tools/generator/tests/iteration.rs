#![cfg(feature = "candidate")]
//! Upstream fitting identity and shared raster contracts. Optical assessment
//! is separate; no source-coordinate freeze constrains the library fit.
use font_generator::{
    candidate::{capture, render},
    probe::{FittedPen, RasterOutput},
    reference::{
        reference, RasterPolicy, ReferenceRecord, ReferenceRequest, PROFILE_GRAY_3BIT,
        PROFILE_MONO_1BIT,
    },
    stem_fitting::{EXTENSIONS_FONT_HINTS_FIRST, EXTENSIONS_MONO_WIDTH_01},
    Config, Hinting,
};
use skrifa::{
    instance::Size,
    outline::{DrawSettings, Engine, HintingInstance, HintingOptions, Target},
    FontRef, MetadataProvider,
};
use std::{fs, path::Path};

fn font(name: &str) -> Vec<u8> {
    fs::read(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../fonts")
            .join(name),
    )
    .unwrap()
}
fn request(name: &str, size: f32, profile: &str) -> ReferenceRequest {
    let mut config = Config {
        size_px: size,
        characters: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789$°".into(),
        hinting: Hinting::AutoFallback,
        output_bits: if profile == PROFILE_MONO_1BIT { 1 } else { 3 },
        ..Config::default()
    };
    config.axes.insert("wght".into(), 400.0);
    if name.starts_with("Roboto") {
        config.axes.insert("wdth".into(), 100.0);
    }
    if name == "Literata.ttf" || name == "RobotoFlex.ttf" {
        config.axes.insert("opsz".into(), size);
    }
    ReferenceRequest {
        profile: profile.into(),
        extensions: EXTENSIONS_FONT_HINTS_FIRST.into(),
        settings: config,
    }
}
fn direct(
    data: &[u8],
    req: &ReferenceRequest,
    record: &ReferenceRecord,
    engine: Engine,
) -> (Vec<font_generator::probe::FittedCommand>, RasterOutput) {
    let face = FontRef::new(data).unwrap();
    let location = face
        .axes()
        .location(req.settings.axes.iter().map(|(t, v)| (t.as_str(), *v)));
    let outlines = face.outline_glyphs();
    let instance = HintingInstance::new(
        &outlines,
        Size::new(req.settings.size_px),
        &location,
        HintingOptions {
            engine,
            target: Target::Mono,
        },
    )
    .unwrap();
    let mut pen = FittedPen::default();
    outlines
        .get(skrifa::GlyphId::new(record.glyph_id))
        .unwrap()
        .draw(DrawSettings::hinted(&instance, false), &mut pen)
        .unwrap();
    let commands = pen.into_commands();
    let raster = font_generator::mono::rasterize(&commands, &req.settings).unwrap();
    (commands, raster)
}
fn assert_direct(data: &[u8], req: &ReferenceRequest, engine: Engine) {
    let result = render(data, req).unwrap();
    assert_eq!(result.target, "mono");
    let automatic = matches!(engine, Engine::Auto(_));
    assert_eq!(
        result.fork, automatic,
        "snapshot provenance follows the automatic fitter"
    );
    assert_eq!(
        result.implementation.contains(":scan-metadata:"),
        automatic,
        "snapshot source hash follows the automatic fitter"
    );
    for r in &result.records {
        let (commands, pixels) = direct(data, req, r, engine.clone());
        assert_eq!(r.fitted_commands, commands, "outline U+{:04X}", r.codepoint);
        assert_eq!(r.pixels, pixels.pixels, "pixels U+{:04X}", r.codepoint);
        assert_eq!(r.coverage, pixels.coverage);
        assert_eq!(
            (r.left, r.top, r.width, r.height),
            (pixels.left, pixels.top, pixels.width, pixels.height)
        );
        assert_eq!(r.raster_policy, RasterPolicy::FreeTypeMono);
        assert_eq!(r.diagonal_pairs, None);
        assert_eq!(
            r.side_bearing_deltas_26_6.is_some(),
            automatic,
            "residual metadata U+{:04X}",
            r.codepoint
        );
    }
}
#[test]
fn font_hints_first_and_automatic_match_unmodified_upstream_across_fonts_sizes_and_axes() {
    for name in [
        "Roboto.ttf",
        "Roboto-Italic.ttf",
        "RobotoFlex.ttf",
        "Literata.ttf",
        "SourceSans3.ttf",
    ] {
        let data = font(name);
        for size in [13.0, 14.0, 14.5, 16.0, 20.0] {
            let mut req = request(name, size, PROFILE_MONO_1BIT);
            if name == "RobotoFlex.ttf" {
                req.settings.axes.insert("wght".into(), 700.0);
                req.settings.axes.insert("slnt".into(), -10.0);
            }
            let fitted = render(&data, &req).unwrap();
            // The candidate reports the engine it actually selected; that
            // selection stays a whole unmodified upstream outline draw. Scan-
            // only programs fall back to automatic fitting while hinted fonts
            // keep the interpreter, so select the direct draw per report.
            assert!(fitted
                .records
                .iter()
                .all(|record| record.selected_engine == fitted.records[0].selected_engine));
            assert_direct(
                &data,
                &req,
                match fitted.records[0].selected_engine.as_str() {
                    "auto" => Engine::Auto(None),
                    "interpreter" => Engine::Interpreter,
                    other => panic!("unexpected selected engine {other}"),
                },
            );
            let mut source = req.clone();
            source.extensions = "none".into();
            source.settings.hinting = Hinting::None;
            let source = reference(&data, &source).unwrap();
            for (a, b) in fitted.records.iter().zip(&source.records) {
                assert_eq!(a.glyph_id, b.glyph_id);
                assert_eq!(a.advance_26_6, b.advance_26_6);
            }
            req.extensions = EXTENSIONS_MONO_WIDTH_01.into();
            assert_direct(&data, &req, Engine::Auto(None));
        }
    }
}
#[test]
fn font_hints_first_reports_interpreter_and_real_automatic_fallback() {
    for use_hints in [true, false] {
        let name = if use_hints {
            "Roboto.ttf"
        } else {
            "SourceSans3.ttf"
        };
        let mut bytes = font(name);
        if !use_hints {
            // This source has no glyph instructions. Rebuild it without its
            // minimal prep program using the font library, preserving tables
            // and recomputing the SFNT directory/checksums.
            let source = FontRef::new(&bytes).unwrap();
            let mut builder = write_fonts::FontBuilder::new();
            for record in source.table_directory().table_records() {
                let tag = record.tag();
                if tag != skrifa::Tag::new(b"fpgm") && tag != skrifa::Tag::new(b"prep") {
                    builder.add_raw(tag, source.table_data(tag).unwrap().as_bytes());
                }
            }
            bytes = builder.build();
        }
        let req = request(name, 14.0, PROFILE_MONO_1BIT);
        let face = FontRef::new(&bytes).unwrap();
        assert_eq!(face.outline_glyphs().prefer_interpreter(), use_hints);
        let actual = render(&bytes, &req).unwrap();
        assert_eq!(actual.hinting_requested, "auto_fallback");
        let mut explicit = req.clone();
        explicit.extensions = "none".into();
        explicit.settings.hinting = if use_hints {
            Hinting::Interpreter
        } else {
            Hinting::Auto
        };
        let expected = reference(&bytes, &explicit).unwrap();
        for (a, b) in actual.records.iter().zip(&expected.records) {
            assert_eq!(
                a.selected_engine,
                if use_hints { "interpreter" } else { "auto" }
            );
            assert_eq!(a.fitted_commands, b.fitted_commands);
        }
    }
}
#[test]
fn font_hints_first_is_deterministic_and_gray_retains_upstream_normal_auto() {
    let data = font("Roboto.ttf");
    for profile in [PROFILE_MONO_1BIT, PROFILE_GRAY_3BIT] {
        let req = request("Roboto.ttf", 14.0, profile);
        let a = render(&data, &req).unwrap();
        let b = render(&data, &req).unwrap();
        assert_eq!(
            serde_json::to_value(&a).unwrap(),
            serde_json::to_value(&b).unwrap()
        );
        if profile == PROFILE_GRAY_3BIT {
            let mut explicit = req.clone();
            explicit.extensions = "none".into();
            explicit.settings.hinting = Hinting::Auto;
            let mut expected = reference(&data, &explicit).unwrap();
            expected.extensions = EXTENSIONS_FONT_HINTS_FIRST.into();
            assert_eq!(
                serde_json::to_value(a).unwrap(),
                serde_json::to_value(expected).unwrap()
            );
        }
    }
}
#[test]
fn retired_policy_is_rejected_and_disabled_capture_is_independent() {
    let data = font("Roboto.ttf");
    let mut req = request("Roboto.ttf", 14.0, PROFILE_MONO_1BIT);
    for ext in ["none", "vertical-01", "diagonal-01", ""] {
        req.extensions = ext.into();
        assert!(render(&data, &req).is_err());
    }
    req.extensions = EXTENSIONS_FONT_HINTS_FIRST.into();
    for mode in [Hinting::None, Hinting::Interpreter] {
        req.settings.hinting = mode;
        assert!(render(&data, &req).is_err());
    }
    req.settings.hinting = Hinting::Auto;
    req.extensions = "none".into();
    assert_eq!(
        serde_json::to_value(capture(&data, &req, false).unwrap()).unwrap(),
        serde_json::to_value(reference(&data, &req).unwrap()).unwrap()
    );
}
#[test]
fn postscript_outlines_use_unmodified_upstream_interpreter() {
    for data in [
        include_bytes!("fixtures/static-cff.otf").as_slice(),
        include_bytes!("fixtures/variable-cff2.otf").as_slice(),
    ] {
        let req = ReferenceRequest {
            profile: PROFILE_MONO_1BIT.into(),
            extensions: EXTENSIONS_FONT_HINTS_FIRST.into(),
            settings: Config {
                characters: "A".into(),
                hinting: Hinting::AutoFallback,
                ..Config::default()
            },
        };
        assert_direct(data, &req, Engine::AutoFallback);
        assert_eq!(
            render(data, &req).unwrap().records[0].selected_engine,
            "interpreter"
        );
    }
}
