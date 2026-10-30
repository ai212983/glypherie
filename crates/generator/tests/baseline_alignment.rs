#![cfg(feature = "candidate")]

use font_generator::{
    candidate::render_with_pipeline,
    evaluation::evaluate,
    probe::FittedCommand,
    reference::{reference, ReferenceRequest},
    renderer::{Rasterization, RenderPipeline},
    stem_fitting::StemFittingStrategy,
    Config, Hinting,
};

fn font() -> Vec<u8> {
    std::fs::read(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../fonts/Literata.ttf"
    ))
    .unwrap()
}

fn request() -> ReferenceRequest {
    ReferenceRequest {
        profile: "mono_1bit".into(),
        extensions: "font-hints-auto-01".into(),
        settings: Config {
            size_px: 16.0,
            axes: [("wght".into(), 400.0)].into_iter().collect(),
            characters: "78".into(),
            hinting: Hinting::AutoFallback,
            kerning: false,
            ..Config::default()
        },
    }
}

fn endpoint(command: &FittedCommand) -> (f32, f32) {
    match *command {
        FittedCommand::MoveTo(x, y)
        | FittedCommand::LineTo(x, y)
        | FittedCommand::QuadTo(_, _, x, y)
        | FittedCommand::CurveTo(_, _, _, _, x, y) => (x, y),
        FittedCommand::Close => panic!("expected an endpoint"),
    }
}

#[test]
fn source_baseline_terminal_keeps_its_reference_and_slant_without_stub_rescue() {
    // FreeType blue-zone alignment associates source extrema with a common
    // reference; Shamir section 3.2 preserves point/attachment relations.
    // Test the geometric relationship, rather than prescribing a pixel count.
    let bytes = font();
    let request = request();
    let mut raw_request = request.clone();
    raw_request.extensions = "none".into();
    raw_request.settings.hinting = Hinting::None;
    let source = reference(&bytes, &raw_request).unwrap();
    raw_request.settings.hinting = Hinting::Auto;
    let upstream = reference(&bytes, &raw_request).unwrap();
    let result = render_with_pipeline(
        &bytes,
        &request,
        RenderPipeline {
            fitting: StemFittingStrategy::FontHintsAuto,
            rasterization: Rasterization::FreeTypeMonoTerminals,
            diagonal_fitting: false,
        },
    )
    .unwrap();
    let raw = &source.records[0].fitted_commands;
    let before = &upstream.records[0];
    let after = &result.records[0];
    let foot = raw.len() - 2;
    assert_eq!(endpoint(&raw[foot]).1, 0.0, "source baseline endpoint");
    assert!(endpoint(&before.fitted_commands[foot]).1 > 0.5);
    assert_eq!(endpoint(&after.fitted_commands[foot]).1, 0.0);
    let shift =
        endpoint(&after.fitted_commands[foot]).1 - endpoint(&before.fitted_commands[foot]).1;
    assert_eq!(
        endpoint(&after.fitted_commands[0]).1 - endpoint(&before.fitted_commands[0]).1,
        shift,
        "translate the entire closing cap to preserve its slant"
    );
    assert_eq!(after.advance_26_6, before.advance_26_6);
    let evaluation = evaluate(&source, &upstream, &result);
    assert!(
        evaluation.hard_invariants_pass,
        "{:?}",
        evaluation.hard_failures
    );
    assert_eq!(
        result.records[1].fitted_commands,
        upstream.records[1].fitted_commands
    );
    assert!(
        after.pixels[((-1 - after.top) as u32 * after.width) as usize
            ..((-after.top) as u32 * after.width) as usize]
            .iter()
            .any(|&v| v != 0),
        "retain ink in the baseline-adjacent row occupied by 8"
    );
}

#[test]
fn baseline_and_overlay_stages_replay_across_scanners_and_optical_sizes() {
    let bytes = font();
    for opsz in [12.0, 16.0] {
        let mut request = request();
        request.settings.axes.insert("opsz".into(), opsz);
        request.settings.mono_raster.include_stubs = true;
        let mut raw_request = request.clone();
        raw_request.extensions = "none".into();
        raw_request.settings.mono_raster = Default::default();
        raw_request.settings.hinting = Hinting::None;
        let source = reference(&bytes, &raw_request).unwrap();
        raw_request.settings.hinting = Hinting::Auto;
        let upstream = reference(&bytes, &raw_request).unwrap();
        for fitting in [
            StemFittingStrategy::FontHintsAuto,
            StemFittingStrategy::UpstreamMono,
        ] {
            request.extensions = StemFittingStrategy::extension(Some(fitting)).into();
            for rasterization in [
                Rasterization::FreeTypeMono,
                Rasterization::FreeTypeMonoTerminals,
            ] {
                for diagonal_fitting in [false, true] {
                    let mut result = render_with_pipeline(
                        &bytes,
                        &request,
                        RenderPipeline {
                            fitting,
                            rasterization,
                            diagonal_fitting,
                        },
                    )
                    .unwrap();
                    let record = &result.records[0];
                    let capture = record
                        .baseline_alignment
                        .as_ref()
                        .expect("baseline correction");
                    assert_eq!(capture.model, "baseline-align-01");
                    assert_eq!(record.advance_26_6, upstream.records[0].advance_26_6);
                    let evaluation = evaluate(&source, &upstream, &result);
                    assert!(evaluation.hard_invariants_pass, "opsz={opsz} {fitting:?} {rasterization:?} overlay={diagonal_fitting}: {:?}", evaluation.hard_failures);
                    // Provenance is executable evidence, not an unchecked annotation.
                    result.records[0]
                        .baseline_alignment
                        .as_mut()
                        .unwrap()
                        .shift_px += 0.125;
                    assert!(!evaluate(&source, &upstream, &result).hard_invariants_pass);
                }
            }
        }
    }
}

#[test]
fn automatic_mono_baseline_geometry_is_independent_of_the_scanner() {
    let bytes = font();
    let mut request = request();
    request.extensions = "mono-width-01".into();
    let mut reference_request = request.clone();
    reference_request.extensions = "none".into();
    reference_request.settings.hinting = Hinting::None;
    let source = reference(&bytes, &reference_request).unwrap();
    reference_request.settings.hinting = Hinting::Auto;
    let upstream = reference(&bytes, &reference_request).unwrap();
    let mut expected = None;
    for rasterization in [
        Rasterization::FreeTypeMono,
        Rasterization::FreeTypeMonoTerminals,
        Rasterization::Coverage,
    ] {
        let report = render_with_pipeline(
            &bytes,
            &request,
            RenderPipeline {
                fitting: StemFittingStrategy::UpstreamMono,
                rasterization,
                diagonal_fitting: false,
            },
        )
        .unwrap();
        let commands = &report.records[0].fitted_commands;
        assert!(report.records[0].baseline_alignment.is_some());
        if let Some(expected) = &expected {
            assert_eq!(commands, expected);
        } else {
            expected = Some(commands.clone());
        }
        let evaluation = evaluate(&source, &upstream, &report);
        assert!(
            evaluation.hard_invariants_pass,
            "{rasterization:?}: {:?}",
            evaluation.hard_failures
        );
    }
}
