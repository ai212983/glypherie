#![cfg(feature = "candidate")]
use font_generator::{
    candidate,
    evaluation::evaluate,
    reference::{reference, RasterPolicy, ReferenceReport, ReferenceRequest},
    renderer::{Rasterization, RenderPipeline},
    stem_fitting::StemFittingStrategy,
    Config, Hinting, MonoRasterSettings,
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
    assert_eq!(diagonal.model, "diagonal-shape-04");
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
            "font-hints candidate requires FreeType mono without horizontal correction metadata",
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
    assert_eq!(diagonal.model, "diagonal-shape-04");
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
