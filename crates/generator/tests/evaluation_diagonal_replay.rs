#![cfg(feature = "candidate")]
use font_generator::{
    candidate,
    evaluation::evaluate,
    reference::{reference, RasterPolicy, ReferenceReport, ReferenceRequest},
    renderer::{Rasterization, RenderPipeline},
    stem_fitting::StemFittingStrategy,
    Config, Hinting, MonoDropoutMode, MonoRasterSettings,
};

fn roboto_flex() -> Vec<u8> {
    std::fs::read(format!(
        "{}/../../fonts/RobotoFlex.ttf",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap()
}

fn fitting() -> StemFittingStrategy {
    StemFittingStrategy::FontHintsAuto
}

fn base_settings(characters: &str, hinting: Hinting) -> Config {
    Config {
        size_px: 16.0,
        characters: characters.into(),
        output_bits: 1,
        hinting,
        ..Config::default()
    }
}

fn base_request(characters: &str, hinting: Hinting) -> ReferenceRequest {
    ReferenceRequest {
        profile: "mono_1bit".into(),
        extensions: "none".into(),
        settings: base_settings(characters, hinting),
    }
}

fn pipeline_request(characters: &str) -> ReferenceRequest {
    ReferenceRequest {
        profile: "mono_1bit".into(),
        extensions: StemFittingStrategy::extension(Some(fitting())).into(),
        settings: Config {
            characters: characters.into(),
            size_px: 16.0,
            output_bits: 1,
            hinting: fitting().hinting(),
            mono_raster: MonoRasterSettings {
                font_instructions: true,
                include_stubs: true,
                ..Default::default()
            },
            ..Config::default()
        },
    }
}

fn pipeline(enabled: bool) -> RenderPipeline {
    RenderPipeline {
        fitting: fitting(),
        rasterization: Rasterization::FreeTypeMonoTerminals,
        diagonal_fitting: enabled,
    }
}

fn source_and_upstream(characters: &str) -> (ReferenceReport, ReferenceReport) {
    let data = roboto_flex();
    let upstream = reference(&data, &base_request(characters, Hinting::Auto)).unwrap();
    let source = reference(&data, &base_request(characters, Hinting::None)).unwrap();
    (source, upstream)
}

fn diagonal_candidate(characters: &str) -> ReferenceReport {
    candidate::render_with_pipeline(
        &roboto_flex(),
        &pipeline_request(characters),
        pipeline(true),
    )
    .unwrap()
}

fn plain_candidate(characters: &str) -> ReferenceReport {
    candidate::render_with_pipeline(
        &roboto_flex(),
        &pipeline_request(characters),
        pipeline(false),
    )
    .unwrap()
}

fn applied_index(candidate: &ReferenceReport) -> usize {
    candidate
        .records
        .iter()
        .position(|record| record.diagonal_fitting.is_some())
        .expect("pipeline must produce an applied diagonal capture")
}

fn invariants(report: &font_generator::evaluation::Evaluation) -> Vec<&str> {
    report
        .hard_failures
        .iter()
        .map(|failure| failure.invariant.as_str())
        .collect()
}

fn diagonal_failures(report: &font_generator::evaluation::Evaluation) -> Vec<&str> {
    invariants(report)
        .into_iter()
        .filter(|invariant| invariant.contains("diagonal"))
        .collect()
}

#[test]
fn applied_diagonal_replay_accepts() {
    let (source, upstream, candidate) = (
        source_and_upstream("s").0,
        source_and_upstream("s").1,
        diagonal_candidate("s"),
    );
    let index = applied_index(&candidate);
    let diagonal = candidate.records[index].diagonal_fitting.as_ref().unwrap();
    assert_eq!(diagonal.model, "diagonal-shape-05");
    assert_eq!(diagonal.reason, "curve:fitted");
    assert!(!diagonal.upstream_commands.is_empty());
    assert_ne!(
        candidate.records[index].fitted_commands,
        diagonal.upstream_commands
    );
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(diagonal_failures(&evaluation), Vec::<&str>::new());
    assert!(
        evaluation.hard_invariants_pass,
        "{:?}",
        evaluation.hard_failures
    );
}

#[test]
fn preceding_shape_capture_still_replays_with_its_original_authority() {
    let (source, upstream) = source_and_upstream("s");
    let mut candidate = diagonal_candidate("s");
    let index = applied_index(&candidate);
    // This unsupported coupled contour retains the preceding local curve
    // model, so an 04 capture remains independently reproducible.
    let capture = candidate.records[index].diagonal_fitting.as_mut().unwrap();
    assert_eq!(capture.reason, "curve:fitted");
    capture.model = "diagonal-shape-04".into();
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(
        evaluation.hard_invariants_pass,
        "{:?}",
        evaluation.hard_failures
    );
}

#[test]
fn coupled_native_y_capture_replays_and_requires_its_scan_policy() {
    let data = std::fs::read(format!(
        "{}/../../fonts/Roboto.ttf",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap();
    let request = pipeline_request("c");
    let upstream = candidate::render_with_pipeline(&data, &request, pipeline(false)).unwrap();
    let independent_upstream = reference(&data, &base_request("c", Hinting::Auto)).unwrap();
    let source = reference(&data, &base_request("c", Hinting::None)).unwrap();
    let mut candidate = candidate::render_with_pipeline(&data, &request, pipeline(true)).unwrap();
    let old = &upstream.records[0];
    let new = &candidate.records[0];
    let capture = new
        .diagonal_fitting
        .as_ref()
        .expect("reviewed native-Y curve fits");
    assert_eq!(capture.model, "diagonal-shape-05");
    assert_eq!(capture.reason, "coupled:fitted");
    assert_eq!(capture.native_axes, [false, true]);
    assert_eq!(capture.upstream_commands, old.fitted_commands);
    assert_ne!(old.fitted_commands, new.fitted_commands);
    assert_eq!(new.advance_26_6, old.advance_26_6);
    assert_eq!(new.hinted_advance_width, old.hinted_advance_width);
    assert_eq!(new.font_scan, old.font_scan);
    assert_eq!(new.raster_policy, RasterPolicy::FreeTypeMono);
    let evaluation = evaluate(&source, &independent_upstream, &candidate);
    assert!(
        evaluation.hard_invariants_pass,
        "{:?}",
        evaluation.hard_failures
    );
    candidate.records[0].raster_policy = RasterPolicy::FreeTypeMonoTerminals;
    let evaluation = evaluate(&source, &independent_upstream, &candidate);
    assert!(invariants(&evaluation)
        .iter()
        .any(|failure| failure.contains("coupled fit requires")));
}

#[test]
fn plain_candidate_has_no_diagonal_failures() {
    let (source, upstream) = source_and_upstream("s");
    let candidate = plain_candidate("s");
    assert!(candidate
        .records
        .iter()
        .all(|record| record.diagonal_fitting.is_none()));
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(diagonal_failures(&evaluation), Vec::<&str>::new());
}

#[test]
fn empty_reason_accumulates_with_later_raster_fault() {
    let (source, upstream) = source_and_upstream("s");
    let mut candidate = diagonal_candidate("s");
    let index = applied_index(&candidate);
    candidate.records[index]
        .diagonal_fitting
        .as_mut()
        .unwrap()
        .reason
        .clear();
    candidate.records[index].pixels[0] ^= 1;
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec![
            "diagonal capture inconsistent",
            "stored raster does not reproduce from fitted outline",
        ]
    );
}

#[test]
fn empty_upstream_accumulates_with_later_raster_fault() {
    let (source, upstream) = source_and_upstream("s");
    let mut candidate = diagonal_candidate("s");
    let index = applied_index(&candidate);
    candidate.records[index]
        .diagonal_fitting
        .as_mut()
        .unwrap()
        .upstream_commands
        .clear();
    candidate.records[index].pixels[0] ^= 1;
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec![
            "diagonal capture inconsistent",
            "stored raster does not reproduce from fitted outline",
        ]
    );
}

#[test]
fn incompatible_policy_accumulates_scan_and_raster_faults() {
    let (source, upstream) = source_and_upstream("s");
    let mut candidate = diagonal_candidate("s");
    let index = applied_index(&candidate);
    candidate.records[index].raster_policy = RasterPolicy::Coverage;
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec![
            "source outline on an incompatible raster policy",
            "diagonal capture inconsistent",
            "monochrome scan settings on a coverage raster",
            "stored raster does not reproduce from fitted outline",
            "source outline identity changed",
        ]
    );
}

#[test]
fn missing_source_returns_before_later_guards() {
    let (source, upstream) = source_and_upstream("s");
    let mut candidate = diagonal_candidate("s");
    let index = applied_index(&candidate);
    candidate.records[index].source_commands = None;
    candidate.records[index].pixels[0] ^= 1;
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec![
            "diagonal source outline missing",
            "terminal source outline missing",
        ]
    );
}

#[test]
fn invalid_reference_returns_before_later_guards() {
    let (source, upstream) = source_and_upstream("s");
    let mut candidate = diagonal_candidate("s");
    let index = applied_index(&candidate);
    candidate.records[index]
        .diagonal_fitting
        .as_mut()
        .unwrap()
        .reference = serde_json::json!(5);
    candidate.records[index].pixels[0] ^= 1;
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec!["diagonal reference does not deserialize"]
    );
}

#[test]
fn invalid_raw_source_returns_before_later_guards() {
    let (source, upstream) = source_and_upstream("s");
    let mut candidate = diagonal_candidate("s");
    let index = applied_index(&candidate);
    let diagonal = candidate.records[index].diagonal_fitting.as_mut().unwrap();
    assert_eq!(diagonal.model, "diagonal-shape-05");
    diagonal.raw_source = Some(serde_json::json!(5));
    candidate.records[index].pixels[0] ^= 1;
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec!["diagonal raw source does not deserialize"]
    );
}

#[test]
fn guard_flaw_skips_corrupt_reference_decoding() {
    let (source, upstream) = source_and_upstream("s");
    let mut candidate = diagonal_candidate("s");
    let index = applied_index(&candidate);
    let diagonal = candidate.records[index].diagonal_fitting.as_mut().unwrap();
    diagonal.reason.clear();
    diagonal.reference = serde_json::json!(5);
    candidate.records[index].pixels[0] ^= 1;
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec![
            "diagonal capture inconsistent",
            "stored raster does not reproduce from fitted outline",
        ]
    );
}

#[test]
fn fatal_reference_after_earlier_checksum_skips_later_raster() {
    let (source, upstream) = source_and_upstream("s");
    let mut candidate = diagonal_candidate("s");
    let index = applied_index(&candidate);
    candidate.records[index]
        .diagonal_fitting
        .as_mut()
        .unwrap()
        .reference = serde_json::json!(5);
    candidate.records[index].coverage[0] ^= 1;
    candidate.records[index].pixels[0] ^= 1;
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec![
            "coverage checksum inconsistent",
            "diagonal reference does not deserialize",
        ]
    );
}

#[test]
fn tampered_reason_breaks_replay_identity() {
    let (source, upstream) = source_and_upstream("s");
    let mut candidate = diagonal_candidate("s");
    let index = applied_index(&candidate);
    candidate.records[index]
        .diagonal_fitting
        .as_mut()
        .unwrap()
        .reason = "terminal:fitted".into();
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec!["diagonal fitting does not reproduce from captured inputs"]
    );
}

#[test]
fn tampered_commands_break_replay_and_raster() {
    let (source, upstream) = source_and_upstream("s");
    let mut candidate = diagonal_candidate("s");
    let index = applied_index(&candidate);
    match &mut candidate.records[index].fitted_commands[0] {
        font_generator::probe::FittedCommand::MoveTo(x, _) => *x += 0.5,
        command => panic!("first command must move, got {command:?}"),
    }
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec![
            "diagonal fitting does not reproduce from captured inputs",
            "stored raster does not reproduce from fitted outline",
        ]
    );
}

#[test]
fn legacy_model_route_diverges_from_approved() {
    let (source, upstream) = source_and_upstream("s");
    let mut candidate = diagonal_candidate("s");
    let index = applied_index(&candidate);
    candidate.records[index]
        .diagonal_fitting
        .as_mut()
        .unwrap()
        .model = "diagonal-shape-legacy".into();
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec!["diagonal fitting does not reproduce from captured inputs"]
    );
}

#[test]
fn gray_reports_carry_no_diagonal_captures() {
    let data = roboto_flex();
    let settings = Config {
        size_px: 16.0,
        characters: "s".into(),
        hinting: Hinting::Auto,
        output_bits: 3,
        ..Config::default()
    };
    let request = ReferenceRequest {
        profile: "gray_3bit".into(),
        extensions: "none".into(),
        settings,
    };
    let upstream = reference(&data, &request).unwrap();
    let mut raw_request = request;
    raw_request.settings.hinting = Hinting::None;
    let source = reference(&data, &raw_request).unwrap();
    let evaluation = evaluate(&source, &upstream, &upstream);
    assert!(
        evaluation.hard_invariants_pass,
        "{:?}",
        evaluation.hard_failures
    );
    assert!(upstream
        .records
        .iter()
        .all(|record| record.diagonal_fitting.is_none()));
}

#[test]
fn terminal_scan_settings_fail_independently_per_field() {
    let (source, upstream) = source_and_upstream("s");
    let base = plain_candidate("s");
    let evaluation = evaluate(&source, &upstream, &base);
    assert!(
        evaluation.hard_invariants_pass,
        "{:?}",
        evaluation.hard_failures
    );
    let cp = base.records[0].codepoint;
    let mut identity = base.clone();
    identity.records[0]
        .mono_rasterizer
        .as_mut()
        .unwrap()
        .version = "rolled".into();
    let evaluation = evaluate(&source, &upstream, &identity);
    assert_eq!(
        evaluation
            .hard_failures
            .iter()
            .map(|failure| (
                failure.report.as_str(),
                failure.codepoint,
                failure.invariant.as_str()
            ))
            .collect::<Vec<_>>(),
        vec![(
            "candidate",
            Some(cp),
            "terminal scan settings or identity inconsistent"
        )]
    );
    let mut missing = base.clone();
    missing.records[0].mono_raster = None;
    let evaluation = evaluate(&source, &upstream, &missing);
    assert_eq!(
        evaluation
            .hard_failures
            .iter()
            .map(|failure| (
                failure.report.as_str(),
                failure.codepoint,
                failure.invariant.as_str()
            ))
            .collect::<Vec<_>>(),
        vec![(
            "candidate",
            Some(cp),
            "terminal scan settings or identity inconsistent"
        )]
    );
    let mut engine = base.clone();
    engine.records[0].selected_engine = "none".into();
    let evaluation = evaluate(&source, &upstream, &engine);
    assert_eq!(
        evaluation
            .hard_failures
            .iter()
            .map(|failure| (
                failure.report.as_str(),
                failure.codepoint,
                failure.invariant.as_str()
            ))
            .collect::<Vec<_>>(),
        vec![
            (
                "candidate",
                Some(cp),
                "invalid monochrome side bearing deltas"
            ),
            (
                "candidate",
                Some(cp),
                "terminal scan settings or identity inconsistent"
            ),
            (
                "candidate",
                Some(cp),
                "record and report policy inconsistent"
            ),
            (
                "candidate",
                Some(cp),
                "font-hints candidate requires FreeType mono without horizontal correction metadata"
            ),
            ("candidate", Some(cp), "selected hinting engine changed")
        ]
    );
    let mut stubs = base.clone();
    stubs.records[0].mono_raster.as_mut().unwrap().include_stubs = false;
    let evaluation = evaluate(&source, &upstream, &stubs);
    assert_eq!(
        evaluation
            .hard_failures
            .iter()
            .map(|failure| (
                failure.report.as_str(),
                failure.codepoint,
                failure.invariant.as_str()
            ))
            .collect::<Vec<_>>(),
        vec![(
            "candidate",
            Some(cp),
            "terminal scan settings or identity inconsistent"
        )]
    );
    let mut dropout = base.clone();
    dropout.records[0].mono_raster.as_mut().unwrap().dropout = MonoDropoutMode::Off;
    let evaluation = evaluate(&source, &upstream, &dropout);
    assert_eq!(
        evaluation
            .hard_failures
            .iter()
            .map(|failure| (
                failure.report.as_str(),
                failure.codepoint,
                failure.invariant.as_str()
            ))
            .collect::<Vec<_>>(),
        vec![(
            "candidate",
            Some(cp),
            "terminal scan settings or identity inconsistent"
        )]
    );
}
