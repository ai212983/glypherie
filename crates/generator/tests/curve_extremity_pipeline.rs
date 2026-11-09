#![cfg(feature = "candidate")]
//! Extremity-phase seam coverage at the real fitting boundary.
//!
//! Roboto Flex 48 px round tops sit exactly on pixel centers (phase 0) and
//! grow stub-rescue/center-fill tips. The extremity stage moves qualifying
//! smooth loop extrema interior-ward onto the sourced window edge (signed
//! deficit at most 1/8 px per end; nested loops with unequal deficits
//! abstain together). These tests assert geometric relationships (edge
//! placement, extremal crown distance, movement bounds, replay, evaluator
//! chaining), never preferred pixel counts; optical acceptance stays with
//! browser review.

use font_generator::{
    candidate,
    curve_extremity::{self, LoopCorrection},
    evaluation::evaluate,
    probe::FittedCommand,
    reference::{reference, ReferenceRecord, ReferenceReport, ReferenceRequest},
    renderer::{Rasterization, RenderPipeline},
    stem_fitting::StemFittingStrategy,
    Config, Hinting, MonoDropoutMode, MonoRasterSettings,
};

fn font() -> Vec<u8> {
    std::fs::read(format!(
        "{}/../../fonts/RobotoFlex.ttf",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap()
}

fn settings(characters: &str) -> Config {
    Config {
        size_px: 48.0,
        axes: [
            ("wght", 400.0),
            ("wdth", 100.0),
            ("slnt", 0.0),
            ("opsz", 48.0),
        ]
        .into_iter()
        .map(|(k, v)| (k.to_string(), v))
        .collect(),
        hinting: Hinting::Auto,
        output_bits: 1,
        mono_raster: MonoRasterSettings {
            dropout: MonoDropoutMode::Smart,
            include_stubs: true,
            font_instructions: false,
        },
        characters: characters.into(),
        ..Config::default()
    }
}

fn pipeline() -> RenderPipeline {
    RenderPipeline {
        fitting: StemFittingStrategy::FontHintsAuto,
        rasterization: Rasterization::FreeTypeMonoTerminals,
        diagonal_fitting: true,
    }
}

/// Explicit reported-case axes: optical size 48, weight 400.
fn axes_48_400() -> std::collections::BTreeMap<String, f32> {
    [
        ("wght", 400.0),
        ("wdth", 100.0),
        ("slnt", 0.0),
        ("opsz", 48.0),
    ]
    .into_iter()
    .map(|(k, v)| (k.to_string(), v))
    .collect()
}

/// Maintained evaluate seam: independent source/upstream reference reports
/// plus the real candidate pipeline at the reported settings (48 px, opsz
/// 48, wght 400, dropout smart with stubs, no font instructions).
fn eval_reports(glyphs: &str) -> (ReferenceReport, ReferenceReport, ReferenceReport) {
    let data = font();
    let base = |hinting| ReferenceRequest {
        profile: "mono_1bit".into(),
        extensions: "none".into(),
        settings: Config {
            size_px: 48.0,
            axes: axes_48_400(),
            characters: glyphs.into(),
            hinting,
            output_bits: 1,
            ..Config::default()
        },
    };
    let source = reference(&data, &base(Hinting::None)).unwrap();
    let upstream = reference(&data, &base(Hinting::Auto)).unwrap();
    let candidate = candidate::render_with_pipeline(
        &data,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: extension(),
            settings: Config {
                size_px: 48.0,
                axes: axes_48_400(),
                characters: glyphs.into(),
                hinting: Hinting::AutoFallback,
                output_bits: 1,
                mono_raster: MonoRasterSettings {
                    dropout: MonoDropoutMode::Smart,
                    include_stubs: true,
                    font_instructions: false,
                },
                ..Config::default()
            },
        },
        pipeline(),
    )
    .unwrap();
    (source, upstream, candidate)
}

fn has_invariant(report: &font_generator::evaluation::Evaluation, invariant: &str) -> bool {
    report
        .hard_failures
        .iter()
        .any(|failure| failure.invariant == invariant)
}

fn extension() -> String {
    StemFittingStrategy::extension(Some(StemFittingStrategy::FontHintsAuto)).into()
}

fn captures(glyphs: &str) -> ReferenceReport {
    let data = font();
    candidate::render_with_pipeline(
        &data,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: extension(),
            settings: settings(glyphs),
        },
        pipeline(),
    )
    .unwrap()
}

/// True outline extremum of one closed contour along an axis: on-curve
/// endpoints plus quadratic interior stationary points. Local to this
/// test; the stage owns the general classifier.
fn contour_extremum(contour: &[FittedCommand], axis: usize, is_max: bool) -> f64 {
    let coord = |x: f32, y: f32| {
        if axis == 0 {
            f64::from(x)
        } else {
            f64::from(y)
        }
    };
    let mut edge = if is_max {
        f64::NEG_INFINITY
    } else {
        f64::INFINITY
    };
    let mut eat = |v: f64| {
        edge = if is_max { edge.max(v) } else { edge.min(v) };
    };
    let mut pen: Option<f64> = None;
    for command in contour {
        match *command {
            FittedCommand::MoveTo(x, y) => pen = Some(coord(x, y)),
            FittedCommand::LineTo(x, y) => {
                eat(coord(x, y));
                pen = Some(coord(x, y));
            }
            FittedCommand::QuadTo(x1, y1, x, y) => {
                let (a, c, b) = (pen.unwrap(), coord(x1, y1), coord(x, y));
                eat(b);
                let denom = (a - c) - (c - b);
                if denom != 0.0 {
                    let t = (a - c) / denom;
                    if t > 0.0 && t < 1.0 {
                        let mt = 1.0 - t;
                        eat(mt * mt * a + 2.0 * mt * t * c + t * t * b);
                    }
                }
                pen = Some(b);
            }
            FittedCommand::CurveTo(..) => panic!("Roboto Flex outlines are quadratic"),
            FittedCommand::Close => {}
        }
    }
    edge
}

fn split_contours(commands: &[FittedCommand]) -> Vec<Vec<FittedCommand>> {
    let mut contours = Vec::new();
    let mut cur = Vec::new();
    for command in commands {
        cur.push(command.clone());
        if matches!(command, FittedCommand::Close) {
            contours.push(std::mem::take(&mut cur));
        }
    }
    contours
}

fn phase(value: f64) -> f64 {
    (value - ((value - 0.5).round() + 0.5)).abs()
}

const WINDOW_EDGE: f64 = 1.0 / 16.0;
/// Sourced per-end displacement bound: an end inside the window moves at
/// most the edge distance plus its own gap, always below 1/8 px.
const MAX_END_PX: f64 = 1.0 / 8.0;

/// Contract check for one corrected record, without mirroring the stage's
/// own classifier: every end moves interior-ward or not at all, no end
/// moves more than the sourced per-end bound, every moved end lands at a
/// valid phase (an own deficit lands exactly on the sourced window edge;
/// a coupled follow lands at a valid phase with the same deficit, and the
/// closed endpoints make a second pass abstain), and each corrected loop
/// did edge-or-follow landing work on at least one end.
fn check_record(record: &ReferenceRecord) {
    let ch = char::from_u32(record.codepoint).unwrap_or('?');
    let capture = record
        .extremity_phase
        .as_ref()
        .unwrap_or_else(|| panic!("glyph {ch} has no extremity capture"));
    assert_eq!(capture.model, curve_extremity::MODEL);
    // Independent replay from captured inputs reproduces the commands.
    let source = record
        .source_commands
        .as_ref()
        .expect("source must be recorded");
    let fit = curve_extremity::fit(source, &capture.upstream_commands, capture.native_axes)
        .expect("replay fit must succeed");
    assert!(fit.applied, "glyph {ch} replay did not apply");
    assert_eq!(
        fit.commands, record.fitted_commands,
        "glyph {ch} replay mismatch"
    );
    let loops: Vec<LoopCorrection> = capture
        .loops
        .iter()
        .map(|v| serde_json::from_value(v.clone()).unwrap())
        .collect();
    assert_eq!(loops, fit.loops, "glyph {ch} loop provenance mismatch");
    assert_eq!(
        curve_extremity::replay(&capture.upstream_commands, &loops).unwrap(),
        record.fitted_commands,
        "glyph {ch} map replay mismatch"
    );
    // A second pass over the corrected outline abstains: corrected ends
    // rest on the closed window edge, so the stage is idempotent.
    let refit = curve_extremity::fit(source, &record.fitted_commands, capture.native_axes)
        .expect("refit must succeed");
    assert!(
        !refit.applied,
        "glyph {ch} correction is not idempotent (second pass applied)"
    );
    // Per-move local contract: each recorded correction is interior-ward
    // within the sourced bound, lands its own segment apex at a valid
    // phase by exactly the recorded delta, and no uncorrected contour
    // changes. Global extrema of a corrected contour may stay anchored
    // (a flat stem top above a subordinate arch is the reported case).
    let fitted = split_contours(&record.fitted_commands);
    let upstream = split_contours(&capture.upstream_commands);
    assert_eq!(
        fitted.len(),
        upstream.len(),
        "glyph {ch} contour count changed"
    );
    let corrected: Vec<usize> = loops.iter().map(|l| l.contour).collect();
    for (index, (new, old)) in fitted.iter().zip(&upstream).enumerate() {
        if !corrected.contains(&index) {
            assert_eq!(
                new, old,
                "glyph {ch} contour {index} changed without a correction"
            );
        }
    }
    assert!(!loops.is_empty(), "glyph {ch} has no local corrections");
    for corr in &loops {
        assert!(
            corr.delta.abs() <= MAX_END_PX + 1e-9,
            "glyph {ch} move {} exceeds bound",
            corr.delta
        );
        assert_eq!(
            corr.delta.signum(),
            if corr.max { -1.0 } else { 1.0 },
            "glyph {ch} move is not interior-ward"
        );
        let apex = |contour: &[FittedCommand]| -> f64 {
            // Apex of the recorded segment: its end joint, the flat run
            // level, or the quadratic stationary point inside it.
            let coord = |x: f32, y: f32| {
                if corr.axis == 0 {
                    f64::from(x)
                } else {
                    f64::from(y)
                }
            };
            let mut pen = 0.0f64;
            let mut seg = 0usize;
            let mut out = f64::NAN;
            for command in contour {
                match *command {
                    FittedCommand::MoveTo(x, y) => pen = coord(x, y),
                    FittedCommand::LineTo(x, y) => {
                        if seg == corr.segment {
                            out = coord(x, y);
                        }
                        pen = coord(x, y);
                        seg += 1;
                    }
                    FittedCommand::QuadTo(x1, y1, x, y) => {
                        if seg == corr.segment {
                            let (a, c, b) = (pen, coord(x1, y1), coord(x, y));
                            out = b;
                            if corr.interior {
                                let d = (a - c) - (c - b);
                                if d != 0.0 {
                                    let t = (a - c) / d;
                                    if t > 0.0 && t < 1.0 {
                                        let m = 1.0 - t;
                                        out = m * m * a + 2.0 * m * t * c + t * t * b;
                                    }
                                }
                            }
                        }
                        pen = coord(x, y);
                        seg += 1;
                    }
                    FittedCommand::CurveTo(..) => panic!("Roboto Flex outlines are quadratic"),
                    FittedCommand::Close => {}
                }
            }
            out
        };
        let before = apex(&upstream[corr.contour]);
        let after = apex(&fitted[corr.contour]);
        assert!(
            (after - before - corr.delta).abs() < 1e-4,
            "glyph {ch} segment {} apex {before} -> {after}, delta {}",
            corr.segment,
            corr.delta
        );
        assert!(
            phase(after) >= WINDOW_EDGE - 1e-6,
            "glyph {ch} segment {} apex at phase {}",
            corr.segment,
            phase(after)
        );
    }
}

#[test]
fn corrected_loops_follow_the_signed_window_rule() {
    let rep = captures("amboqdchn");
    assert!(rep.implementation.contains(curve_extremity::MODEL));
    // Geometry scope at the reported settings: every reported glyph
    // corrects locally, including the subordinate arches of `b`, `d`,
    // `q` and the single-contour arch of `h` under its flat stem top.
    let mut corrected = Vec::new();
    for record in &rep.records {
        let ch = char::from_u32(record.codepoint).unwrap_or('?');
        if record.extremity_phase.is_none() {
            continue;
        }
        check_record(record);
        corrected.push(ch);
    }
    corrected.sort_unstable();
    for expected in ['a', 'b', 'c', 'd', 'h', 'm', 'n', 'o', 'q'] {
        assert!(
            corrected.contains(&expected),
            "glyph {expected} must correct at the reported settings (corrected: {corrected:?})"
        );
    }
}

/// Neighbor controls bracketing the reported 48 px case: sizes 46-50
/// with optical size tracking the pixel size, one heavier weight, and one
/// other family. Fully hermetic: structural invariants only (replay, the
/// sourced 1/8 px per-coordinate bound, advance identity); bulk sweeps and
/// pixel tables live in the out/ diagnostic harness, never in test output.
#[test]
fn neighbor_sizes_weights_families() {
    use font_generator::renderer::Rasterization;
    let data = font();
    let roboto = std::fs::read(format!(
        "{}/../../fonts/Roboto.ttf",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap();
    // (font bytes, family label, weight, optical size follows pixel size)
    let flex_400 = |size: f32| {
        [
            ("wght", 400.0),
            ("wdth", 100.0),
            ("slnt", 0.0),
            ("opsz", size),
        ]
        .into_iter()
        .map(|(k, v)| (k.to_string(), v))
        .collect::<std::collections::BTreeMap<String, f32>>()
    };
    let flex_700 = |size: f32| {
        [
            ("wght", 700.0),
            ("wdth", 100.0),
            ("slnt", 0.0),
            ("opsz", size),
        ]
        .into_iter()
        .map(|(k, v)| (k.to_string(), v))
        .collect::<std::collections::BTreeMap<String, f32>>()
    };
    let mut corrected_48 = 0u32;
    for size in [46.0f32, 47.0, 48.0, 49.0, 50.0] {
        for (font_bytes, family, axes) in [
            (&data, "RobotoFlex-400", flex_400(size)),
            (&data, "RobotoFlex-700", flex_700(size)),
            (&roboto, "Roboto", std::collections::BTreeMap::new()),
        ] {
            let glyphs = "aeonsco";
            let req = ReferenceRequest {
                profile: "mono_1bit".into(),
                extensions: extension(),
                settings: Config {
                    size_px: size,
                    axes,
                    hinting: Hinting::Auto,
                    output_bits: 1,
                    mono_raster: MonoRasterSettings {
                        dropout: MonoDropoutMode::Smart,
                        include_stubs: true,
                        font_instructions: false,
                    },
                    characters: glyphs.into(),
                    ..Config::default()
                },
            };
            let rep = candidate::render_with_pipeline(font_bytes, &req, pipeline()).unwrap();
            for record in &rep.records {
                let ch = char::from_u32(record.codepoint).unwrap_or('?');
                let Some(capture) = &record.extremity_phase else {
                    continue;
                };
                assert_eq!(capture.model, curve_extremity::MODEL);
                // Replay reproduces.
                let source = record.source_commands.as_ref().expect("source recorded");
                let fit =
                    curve_extremity::fit(source, &capture.upstream_commands, capture.native_axes)
                        .expect("replay succeeds");
                assert!(fit.applied);
                assert_eq!(fit.commands, record.fitted_commands);
                // Movement bound: no coordinate moves more than the sourced
                // per-end bound (1/8 px) plus float rounding in this panel.
                fn coords(command: &FittedCommand) -> Vec<f32> {
                    match *command {
                        FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => vec![x, y],
                        FittedCommand::QuadTo(x1, y1, x, y) => vec![x1, y1, x, y],
                        FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                            vec![x1, y1, x2, y2, x, y]
                        }
                        FittedCommand::Close => vec![],
                    }
                }
                let mut peak = 0.0f64;
                for (a, b) in capture
                    .upstream_commands
                    .iter()
                    .zip(&record.fitted_commands)
                {
                    for (x, y) in coords(a).into_iter().zip(coords(b)) {
                        peak = peak.max((f64::from(y) - f64::from(x)).abs());
                    }
                }
                assert!(
                    peak <= 1.0 / 8.0 + 1e-6,
                    "{family} {size}px glyph {ch} moved {peak}"
                );
                // Advances stay with the fitter.
                let up = candidate::render_with_pipeline(
                    font_bytes,
                    &ReferenceRequest {
                        profile: "mono_1bit".into(),
                        extensions: StemFittingStrategy::extension(Some(
                            StemFittingStrategy::UpstreamMono,
                        ))
                        .into(),
                        settings: Config {
                            size_px: size,
                            axes: req.settings.axes.clone(),
                            hinting: Hinting::Auto,
                            output_bits: 1,
                            characters: glyphs.into(),
                            ..Config::default()
                        },
                    },
                    RenderPipeline {
                        fitting: StemFittingStrategy::UpstreamMono,
                        rasterization: Rasterization::FreeTypeMono,
                        diagonal_fitting: false,
                    },
                )
                .unwrap();
                let base = up
                    .records
                    .iter()
                    .find(|r| r.codepoint == record.codepoint)
                    .unwrap();
                assert_eq!(record.advance_26_6, base.advance_26_6);
                if size == 48.0 {
                    corrected_48 += 1;
                }
            }
        }
    }
    // The reported neighborhood is not vacuous: 48 px corrects round glyphs
    // across these controls.
    assert!(
        corrected_48 >= 1,
        "no 48 px corrections across neighbor controls"
    );
}

/// The reported spur: `o` carries no isolated crown pixel, and its paired
/// outer/inner crowns keep their fitted weight. The claim is exactly the
/// extremal one: rigid-pair coupling moves nested loops by equal end
/// deficits, so both apexes shift by identical amounts and their distance
/// is unchanged. No claim is made about other interior wall distances
/// under the two per-contour affine scales.
#[test]
fn corrected_o_bowl_keeps_crown_weight() {
    let rep = captures("o");
    check_record(&rep.records[0]);
    let record = &rep.records[0];
    let capture = record
        .extremity_phase
        .as_ref()
        .expect("o must be corrected");
    assert_eq!(
        capture
            .loops
            .iter()
            .map(|l| l["contour"].as_u64().unwrap())
            .collect::<std::collections::BTreeSet<_>>()
            .len(),
        2
    );
    let contours = split_contours(&record.fitted_commands);
    let before = split_contours(&capture.upstream_commands);
    assert_eq!(contours.len(), 2);
    let crown = |contour: &[FittedCommand]| contour_extremum(contour, 1, true);
    let (before_w, after_w) = (
        crown(&before[0]) - crown(&before[1]),
        crown(&contours[0]) - crown(&contours[1]),
    );
    assert!(
        (before_w - after_w).abs() < 1e-9,
        "crown weight {before_w} -> {after_w}"
    );
    assert!((phase(crown(&contours[0])) - WINDOW_EDGE).abs() < 1e-9);
    assert!((phase(crown(&contours[1])) - WINDOW_EDGE).abs() < 1e-9);
    // The first ink row is a full crown, never an isolated spur pixel.
    let mut crown_run = 0u32;
    for row in 0..record.height {
        let run: u32 = (0..record.width)
            .map(|c| u32::from(record.pixels[(row * record.width + c) as usize]))
            .sum();
        if run > 0 {
            crown_run = run;
            break;
        }
    }
    assert!(crown_run > 1, "o crown collapsed to a spur");
}

/// Paired borders on the reported glyphs share one deficit per border:
/// apex walls measured at the paired extrema stay exact, while flat
/// anchors (the `b`/`d` stem tops, the `q` tail, the clear `a` counter
/// ceiling) keep their coordinates and are never dragged by a local move.
#[test]
fn coupled_pairs_keep_wall_weight_on_reported_glyphs() {
    let rep = captures("abdq");
    assert!(rep.implementation.contains(curve_extremity::MODEL));
    for record in &rep.records {
        let ch = char::from_u32(record.codepoint).unwrap_or('?');
        check_record(record);
        let capture = record
            .extremity_phase
            .as_ref()
            .unwrap_or_else(|| panic!("glyph {ch} must be corrected"));
        let before = split_contours(&capture.upstream_commands);
        let after = split_contours(&record.fitted_commands);
        assert_eq!(before.len(), 2, "glyph {ch} loop count");
        let wall = |contours: &[Vec<FittedCommand>], is_max: bool| {
            contour_extremum(&contours[0], 1, is_max) - contour_extremum(&contours[1], 1, is_max)
        };
        match ch {
            'a' => {
                // Bottom paired wall exact; clear counter ceiling anchored.
                assert!((wall(&before, false) - wall(&after, false)).abs() < 1e-9);
                assert!(
                    (contour_extremum(&after[1], 1, true) - contour_extremum(&before[1], 1, true))
                        .abs()
                        < 1e-9
                );
                assert!((phase(contour_extremum(&after[0], 1, true)) - WINDOW_EDGE).abs() < 1e-9);
            }
            'q' => {
                // Crown paired wall exact; tail-anchored global bottom fixed.
                assert!((wall(&before, true) - wall(&after, true)).abs() < 1e-9);
                assert!(
                    (contour_extremum(&after[0], 1, false)
                        - contour_extremum(&before[0], 1, false))
                    .abs()
                        < 1e-9
                );
            }
            'b' | 'd' => {
                // Bottom paired wall exact; stem top anchored, while the
                // subordinate bowl crown and its inner crown both move.
                assert!((wall(&before, false) - wall(&after, false)).abs() < 1e-9);
                assert!(
                    (contour_extremum(&after[0], 1, true) - contour_extremum(&before[0], 1, true))
                        .abs()
                        < 1e-9
                );
                assert!(
                    (contour_extremum(&after[1], 1, true)
                        - (contour_extremum(&before[1], 1, true) - 1.0 / 16.0))
                        .abs()
                        < 1e-9
                );
            }
            _ => panic!("unexpected glyph {ch}"),
        }
    }
}

/// R2: the evaluator chains every earlier stage to its successor's input.
/// `c`, `m` and `n` carry both diagonal and extremity captures; the
/// diagonal re-fit must reproduce the extremity stage's input, not the
/// final post-extremity outline. `h` is the diagonal-only control.
#[test]
fn evaluator_chains_diagonal_through_extremity() {
    let (source, upstream, candidate) = eval_reports("cmnh");
    assert!(candidate.implementation.contains(curve_extremity::MODEL));
    for record in &candidate.records {
        let ch = char::from_u32(record.codepoint).unwrap_or('?');
        let both = record.diagonal_fitting.is_some() && record.extremity_phase.is_some();
        assert!(
            both,
            "glyph {ch} must carry both diagonal and extremity captures"
        );
        // Stable seam replay: captured inputs reproduce the final outline
        // without re-deriving eligibility, whatever the geometric rule.
        if let Some(capture) = &record.extremity_phase {
            let fit = curve_extremity::fit(
                record.source_commands.as_ref().expect("source recorded"),
                &capture.upstream_commands,
                capture.native_axes,
            )
            .expect("replay fit must succeed");
            assert!(fit.applied);
            assert_eq!(
                fit.commands, record.fitted_commands,
                "glyph {ch} replay mismatch"
            );
        }
    }
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(
        evaluation.hard_invariants_pass,
        "chained stages must evaluate clean: {:?}",
        evaluation.hard_failures
    );
}

/// R2 forged-provenance cases: each mutation must fail with its own
/// identity diagnostic rather than passing against a same-implementation
/// comparison.
#[test]
fn evaluator_flags_forged_stage_provenance() {
    let (source, upstream, candidate) = eval_reports("cmn");
    let both = candidate
        .records
        .iter()
        .position(|record| record.diagonal_fitting.is_some() && record.extremity_phase.is_some())
        .expect("c/m/n carry both captures");
    // Tampered diagonal reason no longer reproduces the successor input.
    let mut forged = candidate.clone();
    forged.records[both]
        .diagonal_fitting
        .as_mut()
        .unwrap()
        .reason = "terminal:fitted".into();
    assert!(has_invariant(
        &evaluate(&source, &upstream, &forged),
        "diagonal fitting does not reproduce from captured inputs",
    ));
    // Truncated extremity loop list is inconsistent.
    let mut forged = candidate.clone();
    forged.records[both]
        .extremity_phase
        .as_mut()
        .unwrap()
        .loops
        .clear();
    assert!(has_invariant(
        &evaluate(&source, &upstream, &forged),
        "extremity capture inconsistent",
    ));
    // Rewritten extremity commands no longer replay.
    let mut forged = candidate.clone();
    let final_commands = forged.records[both].fitted_commands.clone();
    forged.records[both]
        .extremity_phase
        .as_mut()
        .unwrap()
        .upstream_commands = final_commands;
    assert!(has_invariant(
        &evaluate(&source, &upstream, &forged),
        "extremity phase does not reproduce from captured inputs",
    ));
    // A tampered local-move delta no longer replays to the final outline.
    let mut forged = candidate.clone();
    forged.records[both].extremity_phase.as_mut().unwrap().loops[0]["delta"] = serde_json::json!(
        forged.records[both].extremity_phase.as_ref().unwrap().loops[0]["delta"]
            .as_f64()
            .unwrap()
            + 0.01
    );
    assert!(has_invariant(
        &evaluate(&source, &upstream, &forged),
        "extremity phase does not reproduce from captured inputs",
    ));
    // Native ownership feeds the replay: all-native forged axes abstain,
    // so the recorded commands no longer reproduce.
    let mut forged = candidate.clone();
    forged.records[both]
        .extremity_phase
        .as_mut()
        .unwrap()
        .native_axes = [true, true];
    assert!(has_invariant(
        &evaluate(&source, &upstream, &forged),
        "extremity phase does not reproduce from captured inputs",
    ));
    // Forged diagonal native axes fail identity on selective records and
    // break the replay otherwise; size is the report-level identity that
    // always survives independently of axis ownership.
    let mut forged = candidate.clone();
    forged.records[both]
        .diagonal_fitting
        .as_mut()
        .unwrap()
        .size_px += 1.0;
    assert!(has_invariant(
        &evaluate(&source, &upstream, &forged),
        "diagonal input identity changed",
    ));
    // Size must survive: a mismatched size fails identity.
    let mut forged = candidate.clone();
    forged.records[both]
        .extremity_phase
        .as_mut()
        .unwrap()
        .size_px += 1.0;
    assert!(has_invariant(
        &evaluate(&source, &upstream, &forged),
        "extremity input identity changed",
    ));
    // A missing source outline aborts before later guards.
    let mut forged = candidate.clone();
    forged.records[both].source_commands = None;
    assert!(has_invariant(
        &evaluate(&source, &upstream, &forged),
        "diagonal source outline missing",
    ));
}
