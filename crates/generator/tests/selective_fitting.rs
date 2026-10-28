#![cfg(feature = "candidate")]
use font_generator::{
    candidate::render_with_rasterization,
    metadata,
    probe::FittedCommand,
    reference::{ReferenceReport, ReferenceRequest},
    renderer::Rasterization,
    Config, Hinting,
};
use std::{fs, path::Path};

fn font(name: &str) -> Vec<u8> {
    fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join(format!("../../fonts/{name}.ttf"))).unwrap()
}

fn capture(data: &[u8], policy: &str, size: f32, characters: &str) -> ReferenceReport {
    render_with_rasterization(
        data,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: policy.into(),
            settings: Config {
                characters: characters.into(),
                size_px: size,
                hinting: Hinting::AutoFallback,
                mono_raster: font_generator::MonoRasterSettings {
                    font_instructions: true,
                    include_stubs: true,
                    ..Default::default()
                },
                ..Default::default()
            },
        },
        Rasterization::FreeTypeMonoTerminals,
    )
    .unwrap()
}

fn coordinates(commands: &[FittedCommand], x: bool) -> Vec<f32> {
    use FittedCommand::*;
    commands
        .iter()
        .flat_map(|c| match c {
            MoveTo(a, b) | LineTo(a, b) => vec![if x { *a } else { *b }],
            QuadTo(a, b, c, d) => {
                if x {
                    vec![*a, *c]
                } else {
                    vec![*b, *d]
                }
            }
            CurveTo(a, b, c, d, e, f) => {
                if x {
                    vec![*a, *c, *e]
                } else {
                    vec![*b, *d, *f]
                }
            }
            Close => vec![],
        })
        .collect()
}

#[test]
fn y_only_native_hints_keep_y_and_fill_x_from_automatic() {
    // Turner/Lemberg's independent-axis fitting, with native ownership
    // supplied by executed TrueType projection/freedom semantics. Verify
    // the relationship rather than preferring a particular pixel count.
    let data = font("Roboto");
    for size in [12., 14., 16., 18., 20., 24.] {
        let native = capture(&data, "font-hints-01", size, "itflnh");
        let auto = capture(&data, "mono-width-01", size, "itflnh");
        let hybrid = capture(&data, "font-hints-auto-01", size, "itflnh");
        for ((n, a), h) in native
            .records
            .iter()
            .zip(&auto.records)
            .zip(&hybrid.records)
        {
            assert_eq!(n.font_scan.as_ref().unwrap().hinting_axes, [false, true]);
            assert_eq!(h.selected_engine, "auto_x_native_y");
            assert_eq!(
                coordinates(&h.fitted_commands, true),
                coordinates(&a.fitted_commands, true)
            );
            assert_eq!(
                coordinates(&h.fitted_commands, false),
                coordinates(&n.fitted_commands, false)
            );
            assert_eq!(h.advance_26_6, a.advance_26_6);
            assert_eq!(h.font_scan, n.font_scan);
        }
    }
}

#[test]
fn instruction_free_fonts_use_automatic_and_metadata_reports_presence() {
    let roboto = font("Roboto");
    let literata = font("Literata");
    assert_eq!(metadata::extract(&roboto).unwrap().font_hints, Some(true));
    assert_eq!(
        metadata::extract(&literata).unwrap().font_hints,
        Some(false)
    );
    for name in ["Literata", "RobotoFlex"] {
        let data = font(name);
        let hybrid = capture(&data, "font-hints-auto-01", 16., "itfk1");
        let auto = capture(&data, "source-width-01", 16., "itfk1");
        for (h, a) in hybrid.records.iter().zip(&auto.records) {
            assert_eq!(h.fitted_commands, a.fitted_commands);
            assert_eq!(h.pixels, a.pixels);
            assert_eq!(h.advance_26_6, a.advance_26_6);
        }
    }
}

#[test]
fn selective_corpus_reconstructs_against_independent_source_and_auto() {
    for name in [
        "Roboto",
        "Roboto-Italic",
        "RobotoFlex",
        "Literata",
        "SourceSans3",
    ] {
        let data = font(name);
        for size in [12., 16., 20.] {
            let characters = "itflnhmuA7kR069";
            let mut request = ReferenceRequest {
                profile: "mono_1bit".into(),
                extensions: "none".into(),
                settings: Config {
                    characters: characters.into(),
                    size_px: size,
                    hinting: Hinting::None,
                    ..Default::default()
                },
            };
            let source = font_generator::reference::reference(&data, &request).unwrap();
            request.settings.hinting = Hinting::Auto;
            let auto = font_generator::reference::reference(&data, &request).unwrap();
            let hybrid = capture(&data, "font-hints-auto-01", size, characters);
            let result = font_generator::evaluation::evaluate(&source, &auto, &hybrid);
            assert!(
                result.hard_invariants_pass,
                "{name} {size}: {:?}",
                result.hard_failures
            );
        }
    }
}

#[test]
fn auto_x_without_font_instructions_keeps_snapshot_provenance() {
    let data = font("Roboto");
    let hybrid = render_with_rasterization(
        &data,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: "font-hints-auto-01".into(),
            settings: Config {
                characters: "itflnh".into(),
                size_px: 16.0,
                hinting: Hinting::AutoFallback,
                mono_raster: font_generator::MonoRasterSettings {
                    font_instructions: false,
                    ..Default::default()
                },
                ..Default::default()
            },
        },
        Rasterization::FreeTypeMono,
    )
    .unwrap();
    assert!(
        hybrid.records.iter().any(|record| {
            record
                .selective_fitting
                .as_ref()
                .is_some_and(|capture| !capture.native_axes[0])
                && record.side_bearing_deltas_26_6.is_some()
        }),
        "expected an automatic-X record with snapshot residuals"
    );
    assert!(hybrid.fork, "automatic X must mark the snapshot fork");
    assert!(
        hybrid.implementation.contains(":scan-metadata:"),
        "automatic X must record the snapshot source hash, got {:?}",
        hybrid.implementation
    );
    let mut source_request = ReferenceRequest {
        profile: "mono_1bit".into(),
        extensions: "none".into(),
        settings: Config {
            characters: "itflnh".into(),
            size_px: 16.0,
            hinting: Hinting::None,
            ..Default::default()
        },
    };
    let source = font_generator::reference::reference(&data, &source_request).unwrap();
    source_request.settings.hinting = Hinting::Auto;
    let upstream = font_generator::reference::reference(&data, &source_request).unwrap();
    let result = font_generator::evaluation::evaluate(&source, &upstream, &hybrid);
    assert!(result.hard_invariants_pass, "{:?}", result.hard_failures);
}

#[test]
fn selective_capture_rejects_corrupt_axis_ownership() {
    let data = font("Roboto");
    let mut request = ReferenceRequest {
        profile: "mono_1bit".into(),
        extensions: "none".into(),
        settings: Config {
            characters: "i".into(),
            size_px: 16.,
            hinting: Hinting::None,
            ..Default::default()
        },
    };
    let source = font_generator::reference::reference(&data, &request).unwrap();
    request.settings.hinting = Hinting::Auto;
    let auto = font_generator::reference::reference(&data, &request).unwrap();
    let mut hybrid = capture(&data, "font-hints-auto-01", 16., "i");
    assert!(font_generator::evaluation::evaluate(&source, &auto, &hybrid).hard_invariants_pass);
    hybrid.records[0]
        .selective_fitting
        .as_mut()
        .unwrap()
        .native_axes = [true, true];
    assert!(!font_generator::evaluation::evaluate(&source, &auto, &hybrid).hard_invariants_pass);
}
