#![cfg(feature = "candidate")]
use font_generator::{
    candidate::{render_with_pipeline, render_with_rasterization},
    evaluation::evaluate,
    probe::FittedCommand,
    reference::{reference, ReferenceReport, ReferenceRequest},
    renderer::{Rasterization, RenderPipeline},
    stem_fitting::StemFittingStrategy,
    Config, Hinting,
};
use std::{collections::BTreeMap, fs, path::Path};

fn font(name: &str) -> Vec<u8> {
    fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join(format!("../../fonts/{name}.ttf"))).unwrap()
}

fn axes(pairs: &[(&str, f32)]) -> BTreeMap<String, f32> {
    pairs
        .iter()
        .map(|(tag, value)| (tag.to_string(), *value))
        .collect()
}

fn settings(text: &str, size: f32, axes: BTreeMap<String, f32>, hinting: Hinting) -> Config {
    Config {
        size_px: size,
        axes,
        characters: text.into(),
        hinting,
        ..Config::default()
    }
}

fn upstream_and_source(data: &[u8], settings: &Config) -> (ReferenceReport, ReferenceReport) {
    let base = ReferenceRequest {
        profile: "mono_1bit".into(),
        extensions: "none".into(),
        settings: settings.clone(),
    };
    let mut auto = base.clone();
    auto.settings.hinting = Hinting::Auto;
    let upstream = reference(data, &auto).unwrap();
    let mut none = base;
    none.settings.hinting = Hinting::None;
    let source = reference(data, &none).unwrap();
    (source, upstream)
}

fn candidate_direct(data: &[u8], settings: &Config) -> ReferenceReport {
    render_with_pipeline(
        data,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: "font-hints-auto-01".into(),
            settings: settings.clone(),
        },
        RenderPipeline {
            fitting: StemFittingStrategy::FontHintsAuto,
            rasterization: Rasterization::FreeTypeMono,
            diagonal_fitting: false,
        },
    )
    .unwrap()
}

fn split(commands: &[FittedCommand]) -> Vec<&[FittedCommand]> {
    let mut out = Vec::new();
    let mut start = 0;
    for (i, command) in commands.iter().enumerate() {
        if matches!(command, FittedCommand::Close) {
            out.push(&commands[start..=i]);
            start = i + 1;
        }
    }
    out
}

fn ys(contour: &[FittedCommand]) -> Vec<f32> {
    contour
        .iter()
        .flat_map(|command| match *command {
            FittedCommand::MoveTo(_, y) | FittedCommand::LineTo(_, y) => vec![y],
            FittedCommand::QuadTo(_, y1, _, y) => vec![y1, y],
            FittedCommand::CurveTo(_, y1, _, y2, _, y) => vec![y1, y2, y],
            FittedCommand::Close => vec![],
        })
        .collect()
}

fn min_y(contour: &[FittedCommand]) -> f32 {
    ys(contour).iter().fold(f32::INFINITY, |a, b| a.min(*b))
}

fn max_y(contour: &[FittedCommand]) -> f32 {
    ys(contour).iter().fold(f32::NEG_INFINITY, |a, b| a.max(*b))
}

fn body(commands: &[FittedCommand]) -> &[FittedCommand] {
    split(commands)
        .into_iter()
        .find(|contour| min_y(contour) <= 0.0)
        .expect("body contour")
}

// Baseline-relative ink rows use y-down coordinates.
fn bands(record: &font_generator::reference::ReferenceRecord) -> Vec<(i32, i32)> {
    let width = record.width as usize;
    let height = if width == 0 {
        0
    } else {
        record.pixels.len() / width
    };
    let mut rows: Vec<i32> = Vec::new();
    for row in 0..height {
        if record.pixels[row * width..(row + 1) * width]
            .iter()
            .any(|&pixel| pixel > 0)
        {
            rows.push(record.top + row as i32);
        }
    }
    let mut out = Vec::new();
    let mut start: Option<i32> = None;
    let mut prev = 0;
    for row in rows {
        match start {
            None => {
                start = Some(row);
                prev = row;
            }
            Some(_) if row == prev + 1 => prev = row,
            Some(first) => {
                out.push((first, prev));
                start = Some(row);
                prev = row;
            }
        }
    }
    if let Some(first) = start {
        out.push((first, prev));
    }
    out
}

fn record(report: &ReferenceReport, ch: char) -> &font_generator::reference::ReferenceRecord {
    report
        .records
        .iter()
        .find(|record| record.codepoint == ch as u32)
        .unwrap()
}

fn upstream_record(
    upstream: &ReferenceReport,
    ch: char,
) -> &font_generator::reference::ReferenceRecord {
    record(upstream, ch)
}

const LIGHT_AXES: [(&str, f32); 2] = [("wght", 252.22), ("opsz", 16.0)];
const DEFAULT_AXES: [(&str, f32); 2] = [("wght", 400.0), ("opsz", 12.0)];

#[test]
fn literata_light16_aligns_ij_body_tops() {
    let data = font("Literata");
    let config = settings("Hhiljnux", 16.0, axes(&LIGHT_AXES), Hinting::AutoFallback);
    let (source, upstream) = upstream_and_source(&data, &config);
    let candidate = candidate_direct(&data, &config);
    assert!(
        candidate.implementation.contains(":top-align-02"),
        "implementation {}",
        candidate.implementation
    );
    for ch in ['i', 'j'] {
        let fixed = record(&candidate, ch);
        let raw = upstream_record(&upstream, ch);
        let top = fixed.top_alignment.as_ref().expect("aligned record");
        assert_eq!(top.model, "top-align-02");
        assert_eq!(top.target_px, 8.0);
        assert_eq!(top.contours, vec![0]);
        assert!(
            (0.5..1.5).contains(&top.excess_px),
            "excess {}",
            top.excess_px
        );
        let fixed_body = body(&fixed.fitted_commands);
        let raw_body = body(&raw.fitted_commands);
        assert!(
            (max_y(fixed_body) - 8.0).abs() < 1e-4,
            "body top {}",
            max_y(fixed_body)
        );
        assert_eq!(min_y(fixed_body), min_y(raw_body));
        let fixed_dot: Vec<&[FittedCommand]> = split(&fixed.fitted_commands)
            .into_iter()
            .filter(|contour| min_y(contour) > 0.0)
            .collect();
        let raw_dot: Vec<&[FittedCommand]> = split(&raw.fitted_commands)
            .into_iter()
            .filter(|contour| min_y(contour) > 0.0)
            .collect();
        assert_eq!(top.mark_translations, vec![(1, -1.0)]);
        assert_eq!(fixed_dot.len(), raw_dot.len());
        for (fixed, raw) in fixed_dot.iter().zip(&raw_dot) {
            assert!(ys(fixed).iter().zip(ys(raw)).all(|(a, b)| *a - b == -1.0));
        }
        assert_eq!(fixed.advance_26_6, raw.advance_26_6);
    }
    assert_eq!(bands(record(&candidate, 'i')), vec![(-11, -11), (-8, -1)]);
    assert_eq!(bands(record(&candidate, 'j')), vec![(-11, -11), (-8, 1)]);
    for ch in ['H', 'h', 'l', 'n', 'u', 'x'] {
        let fixed = record(&candidate, ch);
        assert!(
            fixed.top_alignment.is_none(),
            "{ch} must keep upstream geometry"
        );
        assert_eq!(
            fixed.fitted_commands,
            upstream_record(&upstream, ch).fitted_commands
        );
    }
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(
        evaluation.hard_invariants_pass,
        "unexpected failures: {:?}",
        evaluation.hard_failures
    );
    let mut corrupt = candidate.clone();
    corrupt.records[2]
        .top_alignment
        .as_mut()
        .unwrap()
        .upstream_commands
        .clear();
    assert!(!evaluate(&source, &upstream, &corrupt).hard_invariants_pass);
    let mut corrupt = candidate.clone();
    corrupt.records[2].top_alignment.as_mut().unwrap().size_px += 1.0;
    assert!(evaluate(&source, &upstream, &corrupt)
        .hard_failures
        .iter()
        .any(|failure| failure.invariant == "top alignment input identity changed"));
    let mut corrupt = candidate.clone();
    corrupt.records[2]
        .top_alignment
        .as_mut()
        .unwrap()
        .mark_translations
        .clear();
    assert!(!evaluate(&source, &upstream, &corrupt).hard_invariants_pass);
    let mut corrupt = candidate;
    corrupt.records[2].source_commands = None;
    assert!(!evaluate(&source, &upstream, &corrupt).hard_invariants_pass);
}

#[test]
fn literata_light16_selective_pipeline_aligns() {
    let data = font("Literata");
    let mut config = settings("Hhiljnux", 16.0, axes(&LIGHT_AXES), Hinting::AutoFallback);
    config.kerning = false;
    let (source, upstream) = upstream_and_source(&data, &config);
    let candidate = render_with_pipeline(
        &data,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: "font-hints-auto-01".into(),
            settings: config,
        },
        RenderPipeline {
            fitting: StemFittingStrategy::FontHintsAuto,
            rasterization: Rasterization::FreeTypeMonoTerminals,
            diagonal_fitting: true,
        },
    )
    .unwrap();
    for ch in ['i', 'j'] {
        let fixed = record(&candidate, ch);
        assert!(
            fixed.top_alignment.is_some(),
            "{ch} keeps top alignment through selective and diagonal stages"
        );
    }
    assert_eq!(bands(record(&candidate, 'i')), vec![(-11, -11), (-8, -1)]);
    assert_eq!(bands(record(&candidate, 'j')), vec![(-11, -11), (-8, 1)]);
    assert_eq!(bands(record(&candidate, 'n')), vec![(-8, -1)]);
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(
        evaluation.hard_invariants_pass,
        "unexpected failures: {:?}",
        evaluation.hard_failures
    );
}

#[test]
fn literata_default_axes_stay_aligned() {
    let data = font("Literata");
    for size in [16.0, 20.0] {
        let config = settings("Hhiljnux", size, axes(&DEFAULT_AXES), Hinting::AutoFallback);
        let (source, upstream) = upstream_and_source(&data, &config);
        let candidate = candidate_direct(&data, &config);
        assert!(
            candidate
                .records
                .iter()
                .all(|record| record.top_alignment.is_none()),
            "size {size}: no demonstrated miss, no correction"
        );
        for fixed in &candidate.records {
            let raw = upstream_record(&upstream, char::from_u32(fixed.codepoint).unwrap());
            assert_eq!(fixed.fitted_commands, raw.fitted_commands);
        }
        let evaluation = evaluate(&source, &upstream, &candidate);
        assert!(
            evaluation.hard_invariants_pass,
            "size {size}: unexpected failures: {:?}",
            evaluation.hard_failures
        );
    }
}

#[test]
fn literata_light_sizes_without_defect_stay_unchanged() {
    let data = font("Literata");
    for size in [8.0, 12.0, 20.0] {
        let config = settings("Hhiljnux", size, axes(&LIGHT_AXES), Hinting::AutoFallback);
        let (source, upstream) = upstream_and_source(&data, &config);
        let candidate = candidate_direct(&data, &config);
        assert!(
            candidate
                .records
                .iter()
                .all(|record| record.top_alignment.is_none()),
            "size {size}: no demonstrated miss, no correction"
        );
        let evaluation = evaluate(&source, &upstream, &candidate);
        assert!(
            evaluation.hard_invariants_pass,
            "size {size}: unexpected failures: {:?}",
            evaluation.hard_failures
        );
    }
}

#[test]
fn bundled_controls_keep_upstream_geometry() {
    for (family, axes) in [
        ("Roboto", axes(&[("wght", 400.0), ("wdth", 100.0)])),
        ("SourceSans3", axes(&[("wght", 400.0)])),
        ("RobotoFlex", axes(&[("wght", 400.0), ("wdth", 100.0)])),
    ] {
        let data = font(family);
        let config = settings("Hhiljnux", 16.0, axes, Hinting::AutoFallback);
        let (source, upstream) = upstream_and_source(&data, &config);
        let candidate = candidate_direct(&data, &config);
        assert!(
            candidate
                .records
                .iter()
                .all(|record| record.top_alignment.is_none()),
            "{family}: no demonstrated miss, no correction"
        );
        let evaluation = evaluate(&source, &upstream, &candidate);
        assert!(
            evaluation.hard_invariants_pass,
            "{family}: unexpected failures: {:?}",
            evaluation.hard_failures
        );
    }
}

#[test]
fn gray_records_carry_no_top_alignment() {
    let data = font("Literata");
    let mut config = settings("Hhiljnux", 16.0, axes(&LIGHT_AXES), Hinting::Auto);
    config.output_bits = 3;
    let candidate = render_with_rasterization(
        &data,
        &ReferenceRequest {
            profile: "gray_3bit".into(),
            extensions: "mono-width-01".into(),
            settings: config.clone(),
        },
        Rasterization::Coverage,
    )
    .unwrap();
    let expected = reference(
        &data,
        &ReferenceRequest {
            profile: "gray_3bit".into(),
            extensions: "none".into(),
            settings: config,
        },
    )
    .unwrap();
    assert!(candidate
        .records
        .iter()
        .all(|record| record.top_alignment.is_none()));
    for (fixed, raw) in candidate.records.iter().zip(&expected.records) {
        assert_eq!(fixed.fitted_commands, raw.fitted_commands);
    }
}

#[test]
fn height_reference_does_not_depend_on_requested_text() {
    let data = font("Literata");
    for fitting in [
        StemFittingStrategy::FontHintsAuto,
        StemFittingStrategy::UpstreamMono,
    ] {
        for diagonal_fitting in [false, true] {
            let capture = |text: &str| {
                render_with_pipeline(
                    &data,
                    &ReferenceRequest {
                        profile: "mono_1bit".into(),
                        extensions: StemFittingStrategy::extension(Some(fitting)).into(),
                        settings: settings(text, 16.0, axes(&LIGHT_AXES), Hinting::AutoFallback),
                    },
                    RenderPipeline {
                        fitting,
                        rasterization: Rasterization::FreeTypeMonoTerminals,
                        diagonal_fitting,
                    },
                )
                .unwrap()
            };
            let line = capture("Hhiljnux");
            for text in ["i", "ij"] {
                let short = capture(text);
                for ch in text.chars() {
                    let a = record(&short, ch);
                    let b = record(&line, ch);
                    assert_eq!(
                        a.fitted_commands, b.fitted_commands,
                        "{text} {fitting:?} diagonal={diagonal_fitting}"
                    );
                    assert_eq!(
                        (a.left, a.top, a.width, a.height, &a.pixels, a.advance_26_6),
                        (b.left, b.top, b.width, b.height, &b.pixels, b.advance_26_6)
                    );
                    assert_eq!(bands(a).last().unwrap().0, -8);
                }
            }
        }
    }
}

#[test]
fn historical_rendering_keeps_the_independent_automatic_outline() {
    let data = font("Literata");
    let config = settings("ij", 16.0, axes(&LIGHT_AXES), Hinting::AutoFallback);
    let (_, upstream) = upstream_and_source(&data, &config);
    for extensions in ["font-hints-01", "mono-width-01"] {
        let historical = render_with_rasterization(
            &data,
            &ReferenceRequest {
                profile: "mono_1bit".into(),
                extensions: extensions.into(),
                settings: config.clone(),
            },
            Rasterization::FreeTypeMono,
        )
        .unwrap();
        for (actual, expected) in historical.records.iter().zip(&upstream.records) {
            assert_eq!(actual.fitted_commands, expected.fitted_commands);
            assert!(actual.top_alignment.is_none());
        }
    }
}

#[test]
fn detached_marks_preserve_source_gap_after_body_alignment() {
    let data = font("Literata");
    let config = settings("ijnu", 16.0, axes(&LIGHT_AXES), Hinting::AutoFallback);
    let (source, upstream) = upstream_and_source(&data, &config);
    let candidate = candidate_direct(&data, &config);
    for ch in ['i', 'j'] {
        let original = record(&source, ch);
        let before = record(&upstream, ch);
        let after = record(&candidate, ch);
        let source_mark = split(&original.fitted_commands)
            .into_iter()
            .find(|c| min_y(c) > 0.0)
            .unwrap();
        let fitted_mark = split(&after.fitted_commands)
            .into_iter()
            .find(|c| min_y(c) > 0.0)
            .unwrap();
        let previous_mark = split(&before.fitted_commands)
            .into_iter()
            .find(|c| min_y(c) > 0.0)
            .unwrap();
        let source_gap = min_y(source_mark) - max_y(body(&original.fitted_commands));
        let fitted_gap = min_y(fitted_mark) - max_y(body(&after.fitted_commands));
        assert_eq!(
            fitted_gap,
            source_gap.round(),
            "{ch}: detached mark must follow the corrected body"
        );
        assert_eq!(
            max_y(fitted_mark) - min_y(fitted_mark),
            max_y(previous_mark) - min_y(previous_mark)
        );
        let delta = min_y(fitted_mark) - min_y(previous_mark);
        assert!(ys(fitted_mark)
            .iter()
            .zip(ys(previous_mark))
            .all(|(a, b)| *a - b == delta));
        assert_eq!(bands(after)[0], (-11, -11));
        assert_eq!(after.advance_26_6, before.advance_26_6);
    }
}

#[test]
fn relative_gap_tracks_source_across_neighboring_sizes_and_weights() {
    let data = font("Literata");
    let mut applied = 0;
    for size in [12.0, 14.0, 16.0, 18.0, 20.0] {
        for weight in [200.0, 252.22, 300.0, 400.0, 700.0] {
            let config = settings(
                "ijnu",
                size,
                axes(&[("wght", weight), ("opsz", size)]),
                Hinting::AutoFallback,
            );
            let (source, upstream) = upstream_and_source(&data, &config);
            let candidate = candidate_direct(&data, &config);
            for ch in ['i', 'j'] {
                let after = record(&candidate, ch);
                let Some(capture) = &after.top_alignment else {
                    continue;
                };
                if capture.mark_translations.is_empty() {
                    continue;
                }
                applied += 1;
                let original = record(&source, ch);
                let before = record(&upstream, ch);
                let source_mark = split(&original.fitted_commands)
                    .into_iter()
                    .find(|c| min_y(c) > 0.0)
                    .unwrap();
                let fitted_mark = split(&after.fitted_commands)
                    .into_iter()
                    .find(|c| min_y(c) > 0.0)
                    .unwrap();
                let previous_mark = split(&before.fitted_commands)
                    .into_iter()
                    .find(|c| min_y(c) > 0.0)
                    .unwrap();
                let source_gap =
                    (min_y(source_mark) - max_y(body(&original.fitted_commands))).round();
                assert_eq!(
                    min_y(fitted_mark) - max_y(body(&after.fitted_commands)),
                    source_gap,
                    "{ch} {size}px wght{weight}"
                );
                assert_eq!(
                    max_y(fitted_mark) - min_y(fitted_mark),
                    max_y(previous_mark) - min_y(previous_mark)
                );
                assert_eq!(after.advance_26_6, before.advance_26_6);
            }
            let evaluation = evaluate(&source, &upstream, &candidate);
            assert!(
                evaluation.hard_invariants_pass,
                "{size}px wght{weight}: {:?}",
                evaluation.hard_failures
            );
        }
    }
    assert!(applied >= 2, "sweep must exercise the reported pair");
}
