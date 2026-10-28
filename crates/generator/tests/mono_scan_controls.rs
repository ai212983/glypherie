#![cfg(feature = "candidate")]
//! Manual monochrome scan-converter settings: upstream dropout/stub flags
//! as explicit uniform overrides. Defaults preserve delivered pixels;
//! non-defaults apply only through candidate Mono.
use font_generator::{
    candidate,
    evaluation::evaluate,
    reference::{
        reference, ReferenceRequest, EXTENSIONS_NONE, PROFILE_GRAY_3BIT, PROFILE_MONO_1BIT,
    },
    renderer::RendererRole,
    stem_fitting::{EXTENSIONS_FONT_HINTS_FIRST, EXTENSIONS_MONO_WIDTH_01},
    surface::{render_text_with_fitting_strategy, HAlign, TextRenderRequest, WrapMode},
    Config, Hinting, MonoDropoutMode, MonoRasterSettings,
};
use std::path::Path;

fn font_bytes() -> Vec<u8> {
    std::fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fonts/Roboto.ttf"))
        .expect("fixture fonts/Roboto.ttf")
}

fn mono_config(characters: &str, mono_raster: MonoRasterSettings) -> Config {
    Config {
        size_px: 16.0,
        characters: characters.into(),
        hinting: Hinting::Auto,
        output_bits: 1,
        mono_raster,
        ..Config::default()
    }
}

fn mono_request(mono_raster: MonoRasterSettings) -> ReferenceRequest {
    ReferenceRequest {
        profile: PROFILE_MONO_1BIT.into(),
        extensions: EXTENSIONS_FONT_HINTS_FIRST.into(),
        settings: mono_config("Avo", mono_raster),
    }
}

fn records(
    report: &font_generator::reference::ReferenceReport,
) -> std::collections::HashMap<u32, &font_generator::reference::ReferenceRecord> {
    report
        .records
        .iter()
        .map(|record| (record.codepoint, record))
        .collect()
}

#[test]
fn absent_settings_default_and_explicit_defaults_preserve_pixels() {
    // Old jobs/requests omit the field: deserialization must default.
    let parsed: Config = serde_json::from_value(serde_json::json!({
        "size_px": 16.0, "characters": "Avo",
    }))
    .unwrap();
    assert_eq!(parsed.mono_raster, MonoRasterSettings::default());
    assert_eq!(parsed.mono_raster.dropout, MonoDropoutMode::Smart);
    assert!(!parsed.mono_raster.include_stubs);
    // Explicit defaults render byte-identical pixels through the capture.
    let data = font_bytes();
    let implicit = candidate::render(&data, &mono_request(MonoRasterSettings::default())).unwrap();
    for record in &implicit.records {
        assert_eq!(record.mono_raster, Some(MonoRasterSettings::default()));
    }
    let partial: Config = serde_json::from_value(serde_json::json!({
        "size_px": 16.0, "characters": "Avo", "mono_raster": { "dropout": "off" },
    }))
    .unwrap();
    assert!(!partial.mono_raster.include_stubs);
    // Unknown modes and fields are rejected, not silently reinterpreted.
    for settings in [
        serde_json::json!({ "mono_raster": { "dropout": "cleartype" } }),
        serde_json::json!({ "mono_raster": { "dropout": "smart", "high_precision": true } }),
        serde_json::json!({ "mono_raster": "smart" }),
    ] {
        assert!(
            serde_json::from_value::<Config>(settings).is_err(),
            "unknown scan settings must be rejected"
        );
    }
}

#[test]
fn manual_modes_render_with_stable_placement_and_off_ignores_stubs() {
    let data = font_bytes();
    let baseline = candidate::render(&data, &mono_request(MonoRasterSettings::default())).unwrap();
    let placed: std::collections::HashMap<u32, (i32, i32, u32, u32)> = records(&baseline)
        .iter()
        .map(|(&codepoint, record)| {
            (
                codepoint,
                (record.left, record.top, record.width, record.height),
            )
        })
        .collect();
    for dropout in [
        MonoDropoutMode::Off,
        MonoDropoutMode::Simple,
        MonoDropoutMode::Smart,
    ] {
        for include_stubs in [false, true] {
            let settings = MonoRasterSettings {
                dropout,
                include_stubs,
                font_instructions: false,
            };
            let report = candidate::render(&data, &mono_request(settings)).unwrap();
            assert_eq!(report.records.len(), baseline.records.len());
            for record in &report.records {
                // Settings are uniforms, never per-glyph tuning: placement
                // comes from the fitted outline, not the dropout policy.
                assert_eq!(
                    (record.left, record.top, record.width, record.height),
                    placed[&record.codepoint],
                    "U+{:04X} {settings:?}",
                    record.codepoint
                );
                assert!(record.pixels.iter().all(|&p| p <= 1));
            }
        }
    }
    // Upstream semantics, VER-2-15-0 ftimage.h: stub control is ignored when
    // dropouts are ignored, so Off must not depend on the stubs toggle.
    let off_plain = candidate::render(
        &data,
        &mono_request(MonoRasterSettings {
            dropout: MonoDropoutMode::Off,
            include_stubs: false,
            font_instructions: false,
        }),
    )
    .unwrap();
    let off_stubs = candidate::render(
        &data,
        &mono_request(MonoRasterSettings {
            dropout: MonoDropoutMode::Off,
            include_stubs: true,
            font_instructions: false,
        }),
    )
    .unwrap();
    assert_eq!(off_plain.records.len(), off_stubs.records.len());
    for (plain, stubbed) in off_plain.records.iter().zip(&off_stubs.records) {
        assert_eq!(plain.codepoint, stubbed.codepoint);
        assert_eq!(
            plain.pixels, stubbed.pixels,
            "stubs must not affect Off output U+{:04X}",
            plain.codepoint
        );
    }
}

#[test]
fn non_candidate_paths_reject_explicit_settings() {
    let data = font_bytes();
    let settings = MonoRasterSettings {
        dropout: MonoDropoutMode::Off,
        include_stubs: false,
        font_instructions: false,
    };
    let mut config = mono_config("Avo", settings);
    // Legacy generation and the independent reference keep coverage: an
    // explicit override must fail rather than render silently different ink.
    assert!(font_generator::generate(&data, &config)
        .unwrap_err()
        .0
        .contains("candidate monochrome scanner"));
    assert!(reference(
        &data,
        &ReferenceRequest {
            profile: PROFILE_MONO_1BIT.into(),
            extensions: EXTENSIONS_NONE.into(),
            settings: config.clone(),
        },
    )
    .unwrap_err()
    .0
    .contains("candidate monochrome scanner"));
    assert!(font_generator::probe::probe(&data, &config)
        .unwrap_err()
        .0
        .contains("candidate monochrome scanner"));
    // Non-1-bit depths reject overrides in shared settings validation.
    config.output_bits = 3;
    assert!(font_generator::generate(&data, &config)
        .unwrap_err()
        .0
        .contains("output_bits 1"));
}

fn surface_request(config: Config, text: &str) -> TextRenderRequest {
    TextRenderRequest {
        config,
        text: text.into(),
        width: 200,
        height: 60,
        wrap: WrapMode::Clip,
        align: HAlign::Left,
        foreground: [0, 0, 0, 255],
        background: [255, 255, 255, 255],
        palette: None,
    }
}

#[test]
fn surface_applies_manual_modes_only_on_candidate_mono() {
    let data = font_bytes();
    for settings in [
        MonoRasterSettings {
            dropout: MonoDropoutMode::Off,
            include_stubs: false,
            font_instructions: false,
        },
        MonoRasterSettings {
            dropout: MonoDropoutMode::Simple,
            include_stubs: true,
            font_instructions: false,
        },
    ] {
        let request = surface_request(mono_config("Avo", settings), "Avo");
        // Candidate Mono renders; the pixels equal the capture path.
        let rendered =
            render_text_with_fitting_strategy(&data, &request, RendererRole::Candidate, 0.0, None)
                .unwrap();
        assert!(rendered.pixels.iter().any(|&p| p != 255));
        // Baseline, reference and gray keep coverage and reject overrides,
        // including on blank text where no raster runs.
        for (role, bits, blank) in [
            (RendererRole::Baseline, 1, false),
            (RendererRole::Reference, 1, false),
            (RendererRole::Candidate, 3, false),
            (RendererRole::Baseline, 1, true),
        ] {
            let mut config = mono_config("Avo", settings);
            config.output_bits = bits;
            let error = render_text_with_fitting_strategy(
                &data,
                &surface_request(config, if blank { "" } else { "Avo" }),
                role,
                0.0,
                None,
            )
            .unwrap_err();
            assert!(
                error.0.contains("mono raster"),
                "role={role:?} bits={bits} blank={blank}: {error:?}"
            );
        }
    }
    // Compatible blank candidate Mono still returns the background canvas.
    let blank = surface_request(
        mono_config(
            "Avo",
            MonoRasterSettings {
                dropout: MonoDropoutMode::Off,
                include_stubs: false,
                font_instructions: false,
            },
        ),
        "",
    );
    assert!(
        render_text_with_fitting_strategy(&data, &blank, RendererRole::Candidate, 0.0, None)
            .unwrap()
            .pixels
            .chunks_exact(4)
            .all(|px| px == [255, 255, 255, 255])
    );
}

#[test]
fn evaluation_accepts_manual_modes_and_requires_record_settings() {
    let data = font_bytes();
    let mut source_config = mono_config("Avo", MonoRasterSettings::default());
    source_config.hinting = Hinting::None;
    let source = reference(
        &data,
        &ReferenceRequest {
            profile: PROFILE_MONO_1BIT.into(),
            extensions: EXTENSIONS_NONE.into(),
            settings: source_config,
        },
    )
    .unwrap();
    let upstream = reference(
        &data,
        &ReferenceRequest {
            profile: PROFILE_MONO_1BIT.into(),
            extensions: EXTENSIONS_NONE.into(),
            settings: mono_config("Avo", MonoRasterSettings::default()),
        },
    )
    .unwrap();
    for extensions in [EXTENSIONS_FONT_HINTS_FIRST, EXTENSIONS_MONO_WIDTH_01] {
        for settings in [
            MonoRasterSettings {
                dropout: MonoDropoutMode::Off,
                include_stubs: true,
                font_instructions: false,
            },
            MonoRasterSettings {
                dropout: MonoDropoutMode::Simple,
                include_stubs: true,
                font_instructions: false,
            },
            MonoRasterSettings {
                dropout: MonoDropoutMode::Smart,
                include_stubs: true,
                font_instructions: false,
            },
        ] {
            let mut request = mono_request(settings);
            request.extensions = extensions.into();
            let candidate = candidate::render(&data, &request).unwrap();
            let evaluation = evaluate(&source, &upstream, &candidate);
            assert!(
                evaluation.hard_invariants_pass,
                "unexpected failures for {extensions}/{settings:?}: {:?}",
                evaluation.hard_failures
            );
        }
    }
    // Gray captures stay unchanged by Mono scan controls.
    let gray = reference(
        &data,
        &ReferenceRequest {
            profile: PROFILE_GRAY_3BIT.into(),
            extensions: EXTENSIONS_NONE.into(),
            settings: Config {
                size_px: 16.0,
                characters: "Avo".into(),
                output_bits: 3,
                ..Config::default()
            },
        },
    )
    .unwrap();
    for record in &gray.records {
        assert_eq!(record.mono_raster, None);
    }
}
