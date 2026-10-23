#![cfg(feature = "candidate")]
use font_generator::{
    candidate::{render_with_pipeline, render_with_rasterization},
    evaluation::evaluate,
    probe::FittedCommand,
    reference::{
        DiagonalFittingCapture, RasterPolicy, ReferenceRecord, ReferenceReport, ReferenceRequest,
        SourceWidthCapture,
    },
    renderer::{Rasterization, RenderPipeline},
    stem_fitting::StemFittingStrategy,
    Config, Hinting, MonoRasterSettings,
};
use sha2::{Digest, Sha256};
use std::{fs, path::Path};

fn font(name: &str) -> Vec<u8> {
    fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join(format!("../../fonts/{name}.ttf"))).unwrap()
}

fn request(characters: &str, hinting: Hinting) -> ReferenceRequest {
    ReferenceRequest {
        profile: "mono_1bit".into(),
        extensions: "none".into(),
        settings: Config {
            characters: characters.into(),
            size_px: 16.0,
            hinting,
            ..Default::default()
        },
    }
}

fn source_and_upstream(data: &[u8], characters: &str) -> (ReferenceReport, ReferenceReport) {
    let upstream =
        font_generator::reference::reference(data, &request(characters, Hinting::Auto)).unwrap();
    let source =
        font_generator::reference::reference(data, &request(characters, Hinting::None)).unwrap();
    (source, upstream)
}

fn selective_candidate(data: &[u8], characters: &str) -> ReferenceReport {
    render_with_rasterization(
        data,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: "font-hints-auto-01".into(),
            settings: Config {
                characters: characters.into(),
                size_px: 16.0,
                hinting: Hinting::AutoFallback,
                mono_raster: MonoRasterSettings {
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

fn selective_index(candidate: &ReferenceReport) -> usize {
    candidate
        .records
        .iter()
        .position(|record| record.selective_fitting.is_some())
        .expect("selective capture")
}

fn invariants(report: &font_generator::evaluation::Evaluation) -> Vec<&str> {
    report
        .hard_failures
        .iter()
        .map(|failure| failure.invariant.as_str())
        .collect()
}

fn rescanned(record: &mut ReferenceRecord) {
    let config = Config {
        output_bits: record.output_bits,
        mono_threshold: record.mono_threshold,
        gray_gamma: record.gray_gamma,
        mono_raster: record.mono_raster.unwrap_or_default(),
        ..Config::default()
    };
    let output = font_generator::mono::rasterize_with_scan_state(
        &record.fitted_commands,
        &config,
        record.font_scan.as_ref(),
    )
    .unwrap();
    record.coverage_sha256 = format!("{:x}", Sha256::digest(&output.coverage));
    record.coverage = output.coverage;
    record.pixels = output.pixels;
    record.left = output.left;
    record.top = output.top;
    record.width = output.width;
    record.height = output.height;
}

fn transpose(commands: &[FittedCommand]) -> Vec<FittedCommand> {
    use FittedCommand::*;
    commands
        .iter()
        .map(|command| match *command {
            MoveTo(x, y) => MoveTo(y, x),
            LineTo(x, y) => LineTo(y, x),
            QuadTo(x1, y1, x, y) => QuadTo(y1, x1, y, x),
            CurveTo(x1, y1, x2, y2, x, y) => CurveTo(y1, x1, y2, x2, y, x),
            Close => Close,
        })
        .collect()
}

fn diagonal_capture() -> DiagonalFittingCapture {
    let data = font("RobotoFlex");
    let mut candidate = render_with_pipeline(
        &data,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: StemFittingStrategy::extension(Some(StemFittingStrategy::FontHintsAuto))
                .into(),
            settings: Config {
                characters: "s".into(),
                size_px: 16.0,
                output_bits: 1,
                hinting: StemFittingStrategy::FontHintsAuto.hinting(),
                mono_raster: MonoRasterSettings {
                    font_instructions: true,
                    include_stubs: true,
                    ..Default::default()
                },
                ..Default::default()
            },
        },
        RenderPipeline {
            fitting: StemFittingStrategy::FontHintsAuto,
            rasterization: Rasterization::FreeTypeMonoTerminals,
            diagonal_fitting: true,
        },
    )
    .unwrap();
    let index = candidate
        .records
        .iter()
        .position(|record| record.diagonal_fitting.is_some())
        .expect("applied diagonal capture");
    candidate.records[index]
        .diagonal_fitting
        .take()
        .expect("diagonal capture")
}

#[test]
fn selective_valid_fixture_passes() {
    let data = font("Roboto");
    let (source, upstream) = source_and_upstream(&data, "itflnh");
    let candidate = selective_candidate(&data, "itflnh");
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(
        evaluation.hard_invariants_pass,
        "{:?}",
        evaluation.hard_failures
    );
}

#[test]
fn selective_absent_skips_block() {
    let data = font("Roboto");
    let (source, upstream) = source_and_upstream(&data, "itflnh");
    let mut candidate = selective_candidate(&data, "itflnh");
    let index = selective_index(&candidate);
    candidate.records[index].selective_fitting = None;
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(!evaluation.hard_invariants_pass);
    assert!(!invariants(&evaluation)
        .contains(&"selective fitting does not reproduce from captured inputs"));
}

#[test]
fn selective_native_axes_map_to_expected_engines() {
    let data = font("Roboto");
    let (source, upstream) = source_and_upstream(&data, "itflnh");
    let mut candidate = selective_candidate(&data, "itflnh");
    let index = selective_index(&candidate);
    let selective = candidate.records[index]
        .selective_fitting
        .as_ref()
        .expect("selective capture");
    assert_eq!(selective.native_axes, [false, true]);
    assert_eq!(candidate.records[index].selected_engine, "auto_x_native_y");
    candidate.records[index]
        .selective_fitting
        .as_mut()
        .expect("selective capture")
        .native_axes = [false; 2];
    candidate.records[index].selected_engine = "auto_with_native_scan".into();
    candidate.records[index]
        .font_scan
        .as_mut()
        .expect("font scan")
        .hinting_axes = [false; 2];
    let automatic = candidate.records[index]
        .selective_fitting
        .as_ref()
        .expect("selective capture")
        .automatic_commands
        .clone();
    candidate.records[index].fitted_commands = automatic;
    rescanned(&mut candidate.records[index]);
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(
        evaluation.hard_invariants_pass,
        "{:?}",
        evaluation.hard_failures
    );
}

#[test]
fn selective_all_native_axes_rejected() {
    let data = font("Roboto");
    let (source, upstream) = source_and_upstream(&data, "itflnh");
    let mut candidate = selective_candidate(&data, "itflnh");
    let index = selective_index(&candidate);
    let native = candidate.records[index]
        .selective_fitting
        .as_ref()
        .expect("selective capture")
        .native_commands
        .clone();
    candidate.records[index]
        .selective_fitting
        .as_mut()
        .expect("selective capture")
        .native_axes = [true; 2];
    candidate.records[index].selected_engine = "invalid".into();
    candidate.records[index]
        .font_scan
        .as_mut()
        .expect("font scan")
        .hinting_axes = [true; 2];
    candidate.records[index].fitted_commands = native;
    rescanned(&mut candidate.records[index]);
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec!["selective fitting does not reproduce from captured inputs"]
    );
}

#[test]
fn selective_transposed_replay_passes_identity_fails() {
    let data = font("Roboto");
    let (source, upstream) = source_and_upstream(&data, "itflnh");
    let mut candidate = selective_candidate(&data, "itflnh");
    let index = selective_index(&candidate);
    {
        let record = &mut candidate.records[index];
        {
            let selective = record
                .selective_fitting
                .as_mut()
                .expect("selective capture");
            selective.native_axes = [true, false];
            let native = std::mem::take(&mut selective.native_commands);
            selective.native_commands = transpose(&native);
            let automatic = std::mem::take(&mut selective.automatic_commands);
            selective.automatic_commands = transpose(&automatic);
        }
        let source_outline = record.source_commands.take().expect("source outline");
        record.source_commands = Some(transpose(&source_outline));
        let fitted = std::mem::take(&mut record.fitted_commands);
        record.fitted_commands = transpose(&fitted);
        record.font_scan.as_mut().expect("font scan").hinting_axes = [true, false];
        record.selected_engine = "native_x_auto_y".into();
        rescanned(record);
    }
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec![
            "source outline identity changed",
            "selective automatic input identity changed"
        ]
    );
}

#[test]
fn selective_source_missing_fails_reproduction() {
    let data = font("Roboto");
    let (source, upstream) = source_and_upstream(&data, "itflnh");
    let mut candidate = selective_candidate(&data, "itflnh");
    let index = selective_index(&candidate);
    candidate.records[index].source_commands = None;
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec!["selective fitting does not reproduce from captured inputs"]
    );
}

#[test]
fn selective_ownership_changed_fails_reproduction() {
    let data = font("Roboto");
    let (source, upstream) = source_and_upstream(&data, "itflnh");
    let mut candidate = selective_candidate(&data, "itflnh");
    let index = selective_index(&candidate);
    let native = &mut candidate.records[index]
        .selective_fitting
        .as_mut()
        .expect("selective capture")
        .native_commands;
    let first = native
        .iter_mut()
        .find_map(|command| match command {
            FittedCommand::MoveTo(x, _) | FittedCommand::LineTo(x, _) => Some(x),
            _ => None,
        })
        .expect("open command");
    *first += 1.0;
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec!["selective fitting does not reproduce from captured inputs"]
    );
}

#[test]
fn selective_combine_mismatch_accumulates_identity_fault() {
    let data = font("Roboto");
    let (source, upstream) = source_and_upstream(&data, "itflnh");
    let mut candidate = selective_candidate(&data, "itflnh");
    let index = selective_index(&candidate);
    candidate.records[index]
        .selective_fitting
        .as_mut()
        .expect("selective capture")
        .automatic_commands
        .pop()
        .expect("automatic command");
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec![
            "selective fitting does not reproduce from captured inputs",
            "selective automatic input identity changed"
        ]
    );
}

#[test]
fn selective_wrong_raster_policy_accumulates_scan_and_raster_faults() {
    let data = font("Roboto");
    let (source, upstream) = source_and_upstream(&data, "itflnh");
    let mut candidate = selective_candidate(&data, "itflnh");
    let index = selective_index(&candidate);
    candidate.records[index].raster_policy = RasterPolicy::Coverage;
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec![
            "source outline on an incompatible raster policy",
            "selective fitting does not reproduce from captured inputs",
            "monochrome scan settings on a coverage raster",
            "font scan state on an incompatible render policy",
            "stored raster does not reproduce from fitted outline",
            "font-hints candidate requires FreeType mono without horizontal correction metadata",
            "source outline identity changed"
        ]
    );
}

#[test]
fn selective_font_scan_axes_mismatch_fails_reproduction() {
    let data = font("Roboto");
    let (source, upstream) = source_and_upstream(&data, "itflnh");
    let mut candidate = selective_candidate(&data, "itflnh");
    let index = selective_index(&candidate);
    candidate.records[index]
        .font_scan
        .as_mut()
        .expect("font scan")
        .hinting_axes = [true, false];
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec!["selective fitting does not reproduce from captured inputs"]
    );
}

#[test]
fn selective_uses_captured_prediagonal_outline_not_final_fitted() {
    let data = font("Roboto");
    let (source, upstream) = source_and_upstream(&data, "itflnh");
    let mut candidate = selective_candidate(&data, "itflnh");
    let index = selective_index(&candidate);
    let mut diagonal = diagonal_capture();
    diagonal.upstream_commands = candidate.records[index].fitted_commands.clone();
    candidate.records[index].diagonal_fitting = Some(diagonal);
    {
        let record = &mut candidate.records[index];
        let first = record
            .fitted_commands
            .iter_mut()
            .find_map(|command| match command {
                FittedCommand::MoveTo(x, _) | FittedCommand::LineTo(x, _) => Some(x),
                _ => None,
            })
            .expect("open command");
        *first += 3.0;
        assert!(!record.pixels.is_empty());
        record.pixels[0] ^= 1;
    }
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec![
            "diagonal fitting does not reproduce from captured inputs",
            "stored raster does not reproduce from fitted outline"
        ]
    );
}

#[test]
fn selective_prediagonal_upstream_mismatch_fails_in_order() {
    let data = font("Roboto");
    let (source, upstream) = source_and_upstream(&data, "itflnh");
    let mut candidate = selective_candidate(&data, "itflnh");
    let index = selective_index(&candidate);
    let mut diagonal = diagonal_capture();
    diagonal.upstream_commands.clear();
    candidate.records[index].diagonal_fitting = Some(diagonal);
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec![
            "diagonal capture inconsistent",
            "selective fitting does not reproduce from captured inputs"
        ]
    );
}

#[test]
fn selective_width_fitting_requires_auto_engine() {
    let data = font("Roboto");
    let (source, upstream) = source_and_upstream(&data, "itflnh");
    let mut candidate = selective_candidate(&data, "itflnh");
    let index = selective_index(&candidate);
    let fitted = candidate.records[index].fitted_commands.clone();
    candidate.records[index].width_fitting = Some(SourceWidthCapture {
        size_px: 16.0,
        upstream_commands: fitted,
    });
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec![
            "width fitting on an incompatible render policy",
            "width fitting does not reproduce from captured inputs"
        ]
    );
}

#[test]
fn selective_wrong_engine_fails_reproduction() {
    let data = font("Roboto");
    let (source, upstream) = source_and_upstream(&data, "itflnh");
    let mut candidate = selective_candidate(&data, "itflnh");
    let index = selective_index(&candidate);
    candidate.records[index].selected_engine = "bogus".into();
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert_eq!(
        invariants(&evaluation),
        vec!["selective fitting does not reproduce from captured inputs"]
    );
}

#[test]
fn selective_without_font_scan_passes() {
    let data = font("Roboto");
    let (source, upstream) = source_and_upstream(&data, "itflnh");
    let mut candidate = selective_candidate(&data, "itflnh");
    let index = selective_index(&candidate);
    candidate.records[index].font_scan = None;
    rescanned(&mut candidate.records[index]);
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(
        evaluation.hard_invariants_pass,
        "{:?}",
        evaluation.hard_failures
    );
    assert_eq!(invariants(&evaluation), Vec::<&str>::new());
}

#[test]
fn selective_false_false_ignores_cleared_native_commands() {
    let data = font("Roboto");
    let (source, upstream) = source_and_upstream(&data, "itflnh");
    let mut candidate = selective_candidate(&data, "itflnh");
    let index = selective_index(&candidate);
    {
        let record = &mut candidate.records[index];
        let selective = record
            .selective_fitting
            .as_mut()
            .expect("selective capture");
        selective.native_axes = [false; 2];
        selective.native_commands.clear();
        let automatic = selective.automatic_commands.clone();
        record.fitted_commands = automatic;
        record.font_scan.as_mut().expect("font scan").hinting_axes = [false; 2];
        record.selected_engine = "auto_with_native_scan".into();
        rescanned(record);
    }
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(
        evaluation.hard_invariants_pass,
        "{:?}",
        evaluation.hard_failures
    );
    assert_eq!(invariants(&evaluation), Vec::<&str>::new());
}
