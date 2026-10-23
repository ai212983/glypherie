use font_generator::{
    evaluation::evaluate,
    probe::{rasterize, FittedCommand},
    reference::{reference, ReferenceReport, ReferenceRequest},
    Config, Hinting,
};
use sha2::{Digest, Sha256};

fn reports(profile: &str) -> (ReferenceReport, ReferenceReport, ReferenceReport) {
    let data = include_bytes!("fixtures/static-cff.otf");
    let settings = Config {
        size_px: 16.0,
        characters: "A".into(),
        hinting: Hinting::Auto,
        output_bits: if profile == "mono_1bit" { 1 } else { 3 },
        ..Config::default()
    };
    let request = ReferenceRequest {
        profile: profile.into(),
        extensions: "none".into(),
        settings,
    };
    let upstream = reference(data, &request).unwrap();
    let mut raw_request = request;
    raw_request.settings.hinting = Hinting::None;
    let source = reference(data, &raw_request).unwrap();
    let candidate = upstream.clone();
    (source, upstream, candidate)
}

fn replace_outline(report: &mut ReferenceReport, commands: Vec<FittedCommand>) {
    let record = &mut report.records[0];
    let config = Config {
        output_bits: record.output_bits,
        mono_threshold: record.mono_threshold,
        gray_gamma: record.gray_gamma,
        ..Config::default()
    };
    let bitmap = rasterize(&commands, &config).unwrap();
    record.fitted_commands = commands;
    record.left = bitmap.left;
    record.top = bitmap.top;
    record.width = bitmap.width;
    record.height = bitmap.height;
    record.pixels = bitmap.pixels;
    record.coverage = bitmap.coverage;
    record.coverage_sha256 = format!("{:x}", Sha256::digest(&record.coverage));
}

fn rectangle(x: f32, y: f32, width: f32, height: f32) -> Vec<FittedCommand> {
    vec![
        FittedCommand::MoveTo(x, y),
        FittedCommand::LineTo(x + width, y),
        FittedCommand::LineTo(x + width, y + height),
        FittedCommand::LineTo(x, y + height),
        FittedCommand::Close,
    ]
}

#[test]
fn changed_ink_quantity_is_not_an_acceptance_rule() {
    let (mut source, mut upstream, mut candidate) = reports("mono_1bit");
    replace_outline(&mut source, rectangle(0.0, 0.0, 1.0, 2.0));
    replace_outline(&mut upstream, rectangle(0.0, 0.0, 1.0, 2.0));
    replace_outline(&mut candidate, rectangle(0.0, 0.0, 2.0, 2.0));
    let wider = evaluate(&source, &upstream, &candidate);
    let narrower = evaluate(&source, &candidate, &upstream);
    assert!(wider.hard_invariants_pass && narrower.hard_invariants_pass);
    assert_eq!(
        wider.glyphs[0]
            .source_to_candidate
            .as_ref()
            .unwrap()
            .maximum_px,
        1.0
    );
    assert_ne!(
        wider.glyphs[0].upstream.coverage_area_px,
        wider.glyphs[0].candidate.coverage_area_px
    );
    let serialized = serde_json::to_value(wider).unwrap();
    assert!(serialized.get("score").is_none());
}

#[test]
fn equal_ink_can_have_different_connectivity_without_an_automatic_verdict() {
    let (mut source, mut upstream, mut candidate) = reports("mono_1bit");
    let mut touching = rectangle(0.0, 0.0, 1.0, 1.0);
    touching.extend(rectangle(1.0, 1.0, 1.0, 1.0));
    let mut separated = rectangle(0.0, 0.0, 1.0, 1.0);
    separated.extend(rectangle(2.0, 2.0, 1.0, 1.0));
    replace_outline(&mut source, touching.clone());
    replace_outline(&mut upstream, touching);
    replace_outline(&mut candidate, separated);
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(evaluation.hard_invariants_pass);
    let glyph = &evaluation.glyphs[0];
    let (a, b) = (
        &glyph.upstream.threshold_samples[1],
        &glyph.candidate.threshold_samples[1],
    );
    assert_eq!(a.ink_pixels, b.ink_pixels);
    assert_eq!(a.topology.ink_components_8, 1);
    assert_eq!(b.topology.ink_components_8, 2);
    assert!(evaluation.limits.contains("intentional"));
}

#[test]
fn counters_and_threshold_sensitivity_are_independent_signals() {
    let (mut source, mut upstream, mut candidate) = reports("mono_1bit");
    let mut ring = rectangle(0.0, 0.0, 3.0, 3.0);
    ring.extend([
        FittedCommand::MoveTo(1.0, 1.0),
        FittedCommand::LineTo(1.0, 2.0),
        FittedCommand::LineTo(2.0, 2.0),
        FittedCommand::LineTo(2.0, 1.0),
        FittedCommand::Close,
    ]);
    replace_outline(&mut source, ring.clone());
    replace_outline(&mut upstream, ring);
    replace_outline(&mut candidate, rectangle(0.5, 0.0, 1.0, 2.0));
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(evaluation.hard_invariants_pass);
    let glyph = &evaluation.glyphs[0];
    assert_eq!(
        glyph.upstream.threshold_samples[1]
            .topology
            .enclosed_background_components_4,
        1
    );
    assert_eq!(
        glyph
            .candidate
            .threshold_samples
            .iter()
            .map(|sample| sample.threshold)
            .collect::<Vec<_>>(),
        vec![112, 128, 144]
    );
    assert_ne!(
        glyph.candidate.threshold_samples[0].ink_pixels,
        glyph.candidate.threshold_samples[2].ink_pixels
    );
    assert!(!glyph.source_command_correspondence);
    assert!(glyph.source_to_candidate.is_none());
}

#[test]
fn layout_and_raster_integrity_failures_are_separate_from_shape_signals() {
    let (source, upstream, mut candidate) = reports("mono_1bit");
    candidate.records[0].advance_26_6 += 64;
    candidate.records[0].pixels[0] ^= 1;
    candidate.records[0].diagonal_pairs = Some([2, 2, 1]);
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(!evaluation.hard_invariants_pass);
    for expected in [
        "glyph mapping or advance changed",
        "stored raster does not reproduce from fitted outline",
        "feature application accounting inconsistent",
    ] {
        assert!(
            evaluation
                .hard_failures
                .iter()
                .any(|failure| failure.invariant == expected),
            "missing {expected}"
        );
    }
    assert_eq!(evaluation.glyphs.len(), 1);
}

#[test]
fn hinted_advance_policy_checks_scaler_metrics_without_allowing_arbitrary_changes() {
    use font_generator::reference::AdvancePolicy;
    let (source, upstream, mut candidate) = reports("mono_1bit");
    candidate.advance_policy = AdvancePolicy::Hinted;
    candidate.extensions = "diagonal-01".into();
    let returned = candidate.records[0].hinted_advance_width.unwrap();
    candidate.records[0].advance_26_6 = (returned * 64.0).round() as i32;
    assert!(evaluate(&source, &upstream, &candidate).hard_invariants_pass);
    candidate.records[0].advance_26_6 += 64;
    assert!(!evaluate(&source, &upstream, &candidate).hard_invariants_pass);
    candidate.records[0].hinted_advance_width = Some(f32::NAN);
    assert!(!evaluate(&source, &upstream, &candidate).hard_invariants_pass);
    let (source, upstream, mut gray) = reports("gray_3bit");
    gray.advance_policy = AdvancePolicy::Hinted;
    gray.extensions = "diagonal-01".into();
    assert!(!evaluate(&source, &upstream, &gray).hard_invariants_pass);
}

#[cfg(feature = "candidate")]
fn font_hints_reports() -> (ReferenceReport, ReferenceReport, ReferenceReport) {
    let (source, upstream, _) = reports("mono_1bit");
    let candidate = font_generator::candidate::render(
        include_bytes!("fixtures/static-cff.otf"),
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: "font-hints-01".into(),
            settings: Config {
                size_px: 16.0,
                characters: "A".into(),
                ..Config::default()
            },
        },
    )
    .unwrap();
    (source, upstream, candidate)
}

#[test]
#[cfg(feature = "candidate")]
fn font_hints_candidate_target_is_declared_exactly() {
    let (source, upstream, mut candidate) = font_hints_reports();
    let checked = evaluate(&source, &upstream, &candidate);
    assert!(checked.hard_invariants_pass, "{:?}", checked.hard_failures);
    candidate.target = "smooth".into();
    candidate.records[0].target = "smooth".into();
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(evaluation.hard_failures.iter().any(|failure| {
        failure.invariant == "Mono candidate must declare the upstream mono target"
    }));
}

#[test]
#[cfg(feature = "candidate")]
fn font_hints_evaluation_checks_raster_and_engine_metadata() {
    use font_generator::reference::RasterPolicy;
    let (source, upstream, candidate) = font_hints_reports();
    let mut mislabeled = candidate.clone();
    mislabeled.hinting_requested = "auto".into();
    assert!(evaluate(&source, &upstream, &mislabeled)
        .hard_failures
        .iter()
        .any(|f| f.invariant == "font-hints candidate requires the upstream fallback policy"));

    let mut wrong_scanner = candidate.clone();
    wrong_scanner.records[0]
        .mono_rasterizer
        .as_mut()
        .unwrap()
        .version = "2.14.3".into();
    assert!(evaluate(&source, &upstream, &wrong_scanner)
        .hard_failures
        .iter()
        .any(|f| f.invariant == "monochrome scanner identity inconsistent"));

    // Recompute a valid coverage-only bitmap: raster reproduction alone
    // must not permit the candidate to silently drop the overlap policy.
    let mut coverage_only = candidate.clone();
    let commands = coverage_only.records[0].fitted_commands.clone();
    replace_outline(&mut coverage_only, commands);
    coverage_only.records[0].raster_policy = RasterPolicy::Coverage;
    assert!(evaluate(&source, &upstream, &coverage_only)
        .hard_failures
        .iter()
        .any(|failure| {
            failure.invariant
                == "font-hints candidate requires FreeType mono without horizontal correction metadata"
        }));

    // A valid plain-dropout bitmap must not satisfy the font-hints candidate
    // either: only the pinned monochrome scanner is accepted.
    let mut plain_dropout = candidate.clone();
    let commands = plain_dropout.records[0].fitted_commands.clone();
    let config = Config {
        output_bits: 1,
        ..Config::default()
    };
    let bitmap = font_generator::dropout::rasterize(&commands, &config).unwrap();
    plain_dropout.records[0].left = bitmap.left;
    plain_dropout.records[0].top = bitmap.top;
    plain_dropout.records[0].width = bitmap.width;
    plain_dropout.records[0].height = bitmap.height;
    plain_dropout.records[0].pixels = bitmap.pixels;
    plain_dropout.records[0].coverage = bitmap.coverage;
    plain_dropout.records[0].coverage_sha256 =
        format!("{:x}", Sha256::digest(&plain_dropout.records[0].coverage));
    plain_dropout.records[0].raster_policy = RasterPolicy::CoverageOverlap4xDropout;
    assert!(
        evaluate(&source, &upstream, &plain_dropout)
            .hard_failures
            .iter()
            .any(|failure| failure.invariant
                == "stored raster does not reproduce from fitted outline")
    );
    plain_dropout.records[0].raster_policy = RasterPolicy::CoverageDropout;
    assert!(evaluate(&source, &upstream, &plain_dropout)
        .hard_failures
        .iter()
        .any(|failure| {
            failure.invariant
                == "font-hints candidate requires FreeType mono without horizontal correction metadata"
        }));
}

#[test]
fn dropout_policy_reproduces_delivered_pixels_and_keeps_independent_coverage_hard() {
    use font_generator::reference::RasterPolicy;
    let (mut source, mut upstream, mut candidate) = reports("mono_1bit");
    let outline = rectangle(0.25, 0.0, 0.375, 3.0);
    for report in [&mut source, &mut upstream, &mut candidate] {
        replace_outline(report, outline.clone());
    }
    let raster = font_generator::dropout::rasterize(&outline, &Config::default()).unwrap();
    candidate.records[0].raster_policy = RasterPolicy::CoverageDropout;
    candidate.records[0].pixels = raster.pixels;
    assert!(evaluate(&source, &upstream, &candidate).hard_invariants_pass);

    let mut wrong_policy = candidate.clone();
    wrong_policy.records[0].raster_policy = RasterPolicy::Coverage;
    assert!(!evaluate(&source, &upstream, &wrong_policy).hard_invariants_pass);
    candidate.records[0].pixels[0] ^= 1;
    assert!(!evaluate(&source, &upstream, &candidate).hard_invariants_pass);

    upstream.records[0].raster_policy = RasterPolicy::CoverageDropout;
    assert!(evaluate(&source, &upstream, &wrong_policy)
        .hard_failures
        .iter()
        .any(
            |failure| failure.invariant == "independent rendering requires coverage raster policy"
        ));
}

#[test]
fn dropout_policy_cannot_be_declared_for_gray() {
    use font_generator::reference::RasterPolicy;
    let (source, upstream, mut candidate) = reports("gray_3bit");
    for policy in [
        RasterPolicy::CoverageDropout,
        RasterPolicy::CoverageOverlap4xDropout,
        RasterPolicy::FreeTypeMono,
    ] {
        candidate.records[0].raster_policy = policy;
        assert!(evaluate(&source, &upstream, &candidate)
            .hard_failures
            .iter()
            .any(|failure| failure.invariant
                == "unsupported raster policy for this profile or build"));
    }
}

#[cfg(not(feature = "candidate"))]
#[test]
fn overlap_policy_requires_candidate_feature() {
    let (source, upstream, mut candidate) = reports("mono_1bit");
    candidate.records[0].raster_policy =
        font_generator::reference::RasterPolicy::CoverageOverlap4xDropout;
    assert!(evaluate(&source, &upstream, &candidate)
        .hard_failures
        .iter()
        .any(|failure| failure.invariant == "unsupported raster policy for this profile or build"));
}

#[test]
fn malformed_outlines_and_buffers_report_failures_without_crashing() {
    let (source, upstream, mut candidate) = reports("mono_1bit");
    candidate.records[0].fitted_commands = vec![FittedCommand::LineTo(f32::NAN, 0.0)];
    candidate.records[0].width = u32::MAX;
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(!evaluation.hard_invariants_pass);
    assert!(evaluation
        .hard_failures
        .iter()
        .any(|failure| failure.invariant.contains("contour command")));
    assert!(evaluation.glyphs[0].candidate.threshold_samples.is_empty());
    assert!(evaluation.glyphs[0].source_to_candidate.is_none());
}

#[test]
fn gray_identity_is_a_scope_contract_not_a_pixel_quality_measure() {
    let (source, upstream, mut candidate) = reports("gray_3bit");
    assert!(evaluate(&source, &upstream, &candidate).hard_invariants_pass);
    replace_outline(&mut candidate, rectangle(0.0, 0.0, 1.0, 1.0));
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(evaluation
        .hard_failures
        .iter()
        .any(|failure| failure.invariant == "mono-only iteration changed gray output"));
    assert!(!evaluation
        .hard_failures
        .iter()
        .any(|failure| failure.invariant.contains("stored raster")));
}

#[test]
fn unlike_inputs_and_duplicate_records_cannot_pass_comparability_checks() {
    let (source, upstream, mut candidate) = reports("mono_1bit");
    candidate.axes.insert("wght".into(), 700.0);
    candidate.profile = "gray_3bit".into();
    candidate.records.push(candidate.records[0].clone());
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(!evaluation.hard_invariants_pass);
    for expected in [
        "font, size or variation identity changed",
        "render profile or rasterizer policy changed",
        "duplicate glyph record",
    ] {
        assert!(evaluation
            .hard_failures
            .iter()
            .any(|failure| failure.invariant == expected));
    }
}

const OUTLINE_INVARIANT: &str = "outline coordinates or contour command structure invalid";
const STORED_RASTER_INVARIANT: &str = "stored raster does not reproduce from fitted outline";
const COVERAGE_CHECKSUM_INVARIANT: &str = "coverage checksum inconsistent";

fn has_invariant(evaluation: &font_generator::evaluation::Evaluation, invariant: &str) -> bool {
    evaluation
        .hard_failures
        .iter()
        .any(|failure| failure.invariant == invariant)
}

fn candidate_with_outline(base: &ReferenceReport, commands: Vec<FittedCommand>) -> ReferenceReport {
    let mut candidate = base.clone();
    candidate.records[0].fitted_commands = commands;
    candidate
}

fn coordinate_outlines(value: f32) -> Vec<(&'static str, Vec<FittedCommand>)> {
    vec![
        (
            "move_x",
            vec![FittedCommand::MoveTo(value, 0.0), FittedCommand::Close],
        ),
        (
            "move_y",
            vec![FittedCommand::MoveTo(0.0, value), FittedCommand::Close],
        ),
        (
            "line_x",
            vec![
                FittedCommand::MoveTo(0.0, 0.0),
                FittedCommand::LineTo(value, 0.0),
                FittedCommand::Close,
            ],
        ),
        (
            "line_y",
            vec![
                FittedCommand::MoveTo(0.0, 0.0),
                FittedCommand::LineTo(0.0, value),
                FittedCommand::Close,
            ],
        ),
        (
            "quad_x1",
            vec![
                FittedCommand::MoveTo(0.0, 0.0),
                FittedCommand::QuadTo(value, 0.0, 0.0, 0.0),
                FittedCommand::Close,
            ],
        ),
        (
            "quad_y1",
            vec![
                FittedCommand::MoveTo(0.0, 0.0),
                FittedCommand::QuadTo(0.0, value, 0.0, 0.0),
                FittedCommand::Close,
            ],
        ),
        (
            "quad_x",
            vec![
                FittedCommand::MoveTo(0.0, 0.0),
                FittedCommand::QuadTo(0.0, 0.0, value, 0.0),
                FittedCommand::Close,
            ],
        ),
        (
            "quad_y",
            vec![
                FittedCommand::MoveTo(0.0, 0.0),
                FittedCommand::QuadTo(0.0, 0.0, 0.0, value),
                FittedCommand::Close,
            ],
        ),
        (
            "curve_x1",
            vec![
                FittedCommand::MoveTo(0.0, 0.0),
                FittedCommand::CurveTo(value, 0.0, 0.0, 0.0, 0.0, 0.0),
                FittedCommand::Close,
            ],
        ),
        (
            "curve_y1",
            vec![
                FittedCommand::MoveTo(0.0, 0.0),
                FittedCommand::CurveTo(0.0, value, 0.0, 0.0, 0.0, 0.0),
                FittedCommand::Close,
            ],
        ),
        (
            "curve_x2",
            vec![
                FittedCommand::MoveTo(0.0, 0.0),
                FittedCommand::CurveTo(0.0, 0.0, value, 0.0, 0.0, 0.0),
                FittedCommand::Close,
            ],
        ),
        (
            "curve_y2",
            vec![
                FittedCommand::MoveTo(0.0, 0.0),
                FittedCommand::CurveTo(0.0, 0.0, 0.0, value, 0.0, 0.0),
                FittedCommand::Close,
            ],
        ),
        (
            "curve_x",
            vec![
                FittedCommand::MoveTo(0.0, 0.0),
                FittedCommand::CurveTo(0.0, 0.0, 0.0, 0.0, value, 0.0),
                FittedCommand::Close,
            ],
        ),
        (
            "curve_y",
            vec![
                FittedCommand::MoveTo(0.0, 0.0),
                FittedCommand::CurveTo(0.0, 0.0, 0.0, 0.0, 0.0, value),
                FittedCommand::Close,
            ],
        ),
    ]
}

#[test]
fn outline_grammar_valid_shapes_have_no_outline_failure() {
    let (source, upstream, base) = reports("mono_1bit");
    let mut multi = rectangle(0.0, 0.0, 1.0, 1.0);
    multi.extend(rectangle(2.0, 2.0, 1.0, 1.0));
    let cases: Vec<(&str, Vec<FittedCommand>)> = vec![
        ("empty", vec![]),
        (
            "move_close",
            vec![FittedCommand::MoveTo(0.0, 0.0), FittedCommand::Close],
        ),
        ("multi_closed_contours", multi),
        (
            "line_within_open",
            vec![
                FittedCommand::MoveTo(0.0, 0.0),
                FittedCommand::LineTo(1.0, 0.0),
                FittedCommand::Close,
            ],
        ),
        (
            "quad_within_open",
            vec![
                FittedCommand::MoveTo(0.0, 0.0),
                FittedCommand::QuadTo(1.0, 0.0, 1.0, 1.0),
                FittedCommand::Close,
            ],
        ),
        (
            "curve_within_open",
            vec![
                FittedCommand::MoveTo(0.0, 0.0),
                FittedCommand::CurveTo(1.0, 0.0, 1.0, 1.0, 0.0, 1.0),
                FittedCommand::Close,
            ],
        ),
    ];
    for (name, commands) in cases {
        let mut candidate = base.clone();
        replace_outline(&mut candidate, commands);
        let evaluation = evaluate(&source, &upstream, &candidate);
        assert!(
            !has_invariant(&evaluation, OUTLINE_INVARIANT),
            "{name} should have no outline failure"
        );
        assert!(
            evaluation.hard_invariants_pass,
            "{name}: {:?}",
            evaluation.hard_failures
        );
    }
}

#[test]
fn outline_grammar_invalid_shapes_fail_exact_invariant_and_skip_raster() {
    let (source, upstream, base) = reports("mono_1bit");
    let cases: Vec<(&str, Vec<FittedCommand>)> = vec![
        ("stray_line", vec![FittedCommand::LineTo(1.0, 0.0)]),
        (
            "stray_quad",
            vec![FittedCommand::QuadTo(1.0, 0.0, 1.0, 1.0)],
        ),
        (
            "stray_curve",
            vec![FittedCommand::CurveTo(1.0, 0.0, 1.0, 1.0, 0.0, 1.0)],
        ),
        ("stray_close", vec![FittedCommand::Close]),
        (
            "nested_move",
            vec![
                FittedCommand::MoveTo(0.0, 0.0),
                FittedCommand::LineTo(1.0, 0.0),
                FittedCommand::MoveTo(2.0, 0.0),
                FittedCommand::Close,
            ],
        ),
        (
            "open_ended_path",
            vec![
                FittedCommand::MoveTo(0.0, 0.0),
                FittedCommand::LineTo(1.0, 0.0),
            ],
        ),
        (
            "double_close",
            vec![
                FittedCommand::MoveTo(0.0, 0.0),
                FittedCommand::Close,
                FittedCommand::Close,
            ],
        ),
    ];
    for (name, commands) in cases {
        let candidate = candidate_with_outline(&base, commands);
        let evaluation = evaluate(&source, &upstream, &candidate);
        assert!(!evaluation.hard_invariants_pass, "{name}");
        assert!(
            has_invariant(&evaluation, OUTLINE_INVARIANT),
            "{name} missing exact contour invariant"
        );
        assert!(
            !has_invariant(&evaluation, STORED_RASTER_INVARIANT),
            "{name} must skip stored raster reproduction"
        );
    }
}

#[test]
fn outline_numeric_boundary_inclusive_for_every_slot() {
    let (source, upstream, base) = reports("mono_1bit");
    let mut checked = 0;
    for bound in [32768.0_f32, -32768.0_f32] {
        for (slot, commands) in coordinate_outlines(bound) {
            let candidate = candidate_with_outline(&base, commands);
            let evaluation = evaluate(&source, &upstream, &candidate);
            assert!(
                !has_invariant(&evaluation, OUTLINE_INVARIANT),
                "{slot}_{bound} at inclusive boundary should have no outline failure"
            );
            checked += 1;
        }
    }
    assert_eq!(checked, 28);
}

#[test]
fn outline_numeric_outside_invalid_for_every_slot() {
    let (source, upstream, base) = reports("mono_1bit");
    let just_outside = f32::from_bits(32768.0_f32.to_bits() + 1);
    let just_outside_neg = -just_outside;
    assert!(just_outside.is_finite() && just_outside > 32768.0);
    assert!(just_outside_neg.is_finite() && just_outside_neg < -32768.0);
    let witnesses: Vec<(&str, f32)> = vec![
        ("next_above", just_outside),
        ("next_below", just_outside_neg),
        ("nan", f32::NAN),
        ("pos_inf", f32::INFINITY),
        ("neg_inf", f32::NEG_INFINITY),
    ];
    let mut checked = 0;
    for (witness_name, witness) in &witnesses {
        for (slot, commands) in coordinate_outlines(*witness) {
            let candidate = candidate_with_outline(&base, commands);
            let evaluation = evaluate(&source, &upstream, &candidate);
            assert!(!evaluation.hard_invariants_pass, "{slot}/{witness_name}");
            assert!(
                has_invariant(&evaluation, OUTLINE_INVARIANT),
                "{slot}/{witness_name} missing exact contour invariant"
            );
            assert!(
                !has_invariant(&evaluation, STORED_RASTER_INVARIANT),
                "{slot}/{witness_name} must skip stored raster reproduction"
            );
            checked += 1;
        }
    }
    assert_eq!(checked, 70);
}

#[test]
fn outline_invalid_skips_later_raster_after_earlier_checksum() {
    let (source, upstream, base) = reports("mono_1bit");
    let mut candidate = candidate_with_outline(&base, vec![FittedCommand::LineTo(1.0, 0.0)]);
    candidate.records[0].coverage_sha256 = "0".repeat(64);
    assert!(!candidate.records[0].pixels.is_empty());
    candidate.records[0].pixels[0] ^= 1;
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(!evaluation.hard_invariants_pass);
    let ordered: Vec<&str> = evaluation
        .hard_failures
        .iter()
        .map(|failure| failure.invariant.as_str())
        .collect();
    assert_eq!(
        ordered,
        vec![COVERAGE_CHECKSUM_INVARIANT, OUTLINE_INVARIANT]
    );
}

const SIDEBEARING_INVARIANT: &str = "invalid monochrome side bearing deltas";
const NONFINITE_INVARIANT: &str = "nonfinite fitted metrics";

#[test]
fn fitted_side_bearing_delta_magnitudes() {
    let (source, upstream, base) = reports("mono_1bit");
    let valid: Vec<Option<[i32; 2]>> = vec![
        None,
        Some([96, 0]),
        Some([0, 96]),
        Some([96, 96]),
        Some([-96, -96]),
        Some([96, -96]),
        Some([-96, 96]),
    ];
    for deltas in valid {
        let mut candidate = base.clone();
        candidate.records[0].side_bearing_deltas_26_6 = deltas;
        let evaluation = evaluate(&source, &upstream, &candidate);
        assert!(
            !has_invariant(&evaluation, SIDEBEARING_INVARIANT),
            "{deltas:?} within guard should have no side bearing failure"
        );
    }
    let invalid: Vec<[i32; 2]> = vec![
        [97, 0],
        [0, 97],
        [-97, 0],
        [0, -97],
        [97, 97],
        [-97, -97],
        [i32::MIN, 0],
        [0, i32::MIN],
    ];
    for deltas in invalid {
        let mut candidate = base.clone();
        candidate.records[0].side_bearing_deltas_26_6 = Some(deltas);
        let evaluation = evaluate(&source, &upstream, &candidate);
        assert!(!evaluation.hard_invariants_pass, "{deltas:?}");
        assert!(
            has_invariant(&evaluation, SIDEBEARING_INVARIANT),
            "{deltas:?} missing side bearing failure"
        );
    }
}

#[test]
fn fitted_side_bearing_deltas_require_mono_target_and_auto_engine() {
    let (source, upstream, base) = reports("mono_1bit");
    let mut control = base.clone();
    control.records[0].side_bearing_deltas_26_6 = Some([0, 0]);
    assert!(!has_invariant(
        &evaluate(&source, &upstream, &control),
        SIDEBEARING_INVARIANT
    ));
    let mut target = base.clone();
    target.records[0].side_bearing_deltas_26_6 = Some([0, 0]);
    target.records[0].target = "smooth".into();
    assert!(has_invariant(
        &evaluate(&source, &upstream, &target),
        SIDEBEARING_INVARIANT
    ));
    let mut engine = base.clone();
    engine.records[0].side_bearing_deltas_26_6 = Some([0, 0]);
    engine.records[0].selected_engine = "interpreter".into();
    assert!(has_invariant(
        &evaluate(&source, &upstream, &engine),
        SIDEBEARING_INVARIANT
    ));
}

#[test]
fn fitted_hinted_metrics_finite_domain() {
    let (source, upstream, base) = reports("mono_1bit");
    let valid: Vec<(Option<f32>, Option<f32>)> = vec![(None, None), (Some(8.0), Some(1.5))];
    for (width, lsb) in valid {
        let mut candidate = base.clone();
        candidate.records[0].hinted_advance_width = width;
        candidate.records[0].hinted_lsb = lsb;
        let evaluation = evaluate(&source, &upstream, &candidate);
        assert!(
            !has_invariant(&evaluation, NONFINITE_INVARIANT),
            "{width:?}/{lsb:?} should have no fitted metric failure"
        );
    }
    let invalid: Vec<(Option<f32>, Option<f32>)> = vec![
        (Some(f32::NAN), None),
        (Some(f32::INFINITY), None),
        (Some(f32::NEG_INFINITY), None),
        (None, Some(f32::NAN)),
        (None, Some(f32::INFINITY)),
        (None, Some(f32::NEG_INFINITY)),
    ];
    for (width, lsb) in invalid {
        let mut candidate = base.clone();
        candidate.records[0].hinted_advance_width = width;
        candidate.records[0].hinted_lsb = lsb;
        let evaluation = evaluate(&source, &upstream, &candidate);
        assert!(!evaluation.hard_invariants_pass, "{width:?}/{lsb:?}");
        assert!(
            has_invariant(&evaluation, NONFINITE_INVARIANT),
            "{width:?}/{lsb:?} missing fitted metric failure"
        );
    }
    let mut both = base.clone();
    both.records[0].hinted_advance_width = Some(f32::NAN);
    both.records[0].hinted_lsb = Some(f32::INFINITY);
    let evaluation = evaluate(&source, &upstream, &both);
    assert!(has_invariant(&evaluation, NONFINITE_INVARIANT));
    assert_eq!(
        evaluation
            .hard_failures
            .iter()
            .filter(|failure| failure.invariant == NONFINITE_INVARIANT)
            .count(),
        1
    );
}

#[test]
fn fitted_metric_failures_continue_to_later_checks_in_order() {
    let (source, upstream, base) = reports("mono_1bit");
    let mut candidate = base.clone();
    candidate.records[0].side_bearing_deltas_26_6 = Some([97, 0]);
    candidate.records[0].hinted_advance_width = Some(f32::NAN);
    candidate.records[0].coverage_sha256 = "0".repeat(64);
    assert!(!candidate.records[0].pixels.is_empty());
    candidate.records[0].pixels[0] ^= 1;
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(!evaluation.hard_invariants_pass);
    let ordered: Vec<&str> = evaluation
        .hard_failures
        .iter()
        .map(|failure| failure.invariant.as_str())
        .collect();
    assert_eq!(
        ordered,
        vec![
            SIDEBEARING_INVARIANT,
            NONFINITE_INVARIANT,
            COVERAGE_CHECKSUM_INVARIANT,
            STORED_RASTER_INVARIANT
        ]
    );
}

const QUANT_INVARIANT: &str = "raster quantization policy invalid";
const BUFFER_INVARIANT: &str = "bitmap dimensions or buffer lengths invalid";
const PIXEL_LEVEL_INVARIANT: &str = "pixel level outside configured range";
const POLICY_INVARIANT: &str = "glyph render policy changed";

#[test]
fn quantization_output_bits_domain() {
    let (source, upstream, base) = reports("mono_1bit");
    for bits in [1, 2, 3, 4, 8] {
        let mut candidate = base.clone();
        candidate.records[0].output_bits = bits;
        let evaluation = evaluate(&source, &upstream, &candidate);
        assert!(
            !has_invariant(&evaluation, QUANT_INVARIANT),
            "{bits} valid bits should have no quant failure"
        );
    }
    for bits in [0, 5, 16, 255] {
        let mut candidate = base.clone();
        candidate.records[0].output_bits = bits;
        let evaluation = evaluate(&source, &upstream, &candidate);
        assert!(
            has_invariant(&evaluation, QUANT_INVARIANT),
            "{bits} missing quant failure"
        );
    }
}

#[test]
fn quantization_threshold_domain() {
    let (source, upstream, base) = reports("mono_1bit");
    for threshold in [1, 255] {
        let mut candidate = base.clone();
        candidate.records[0].mono_threshold = threshold;
        let evaluation = evaluate(&source, &upstream, &candidate);
        assert!(
            !has_invariant(&evaluation, QUANT_INVARIANT),
            "{threshold} nonzero threshold should have no quant failure"
        );
    }
    let mut candidate = base.clone();
    candidate.records[0].mono_threshold = 0;
    assert!(has_invariant(
        &evaluate(&source, &upstream, &candidate),
        QUANT_INVARIANT
    ));
}

#[test]
fn quantization_gamma_domain() {
    let (source, upstream, base) = reports("mono_1bit");
    for gamma in [0.5, 1e-30, f32::MIN_POSITIVE] {
        let mut candidate = base.clone();
        candidate.records[0].gray_gamma = gamma;
        let evaluation = evaluate(&source, &upstream, &candidate);
        assert!(
            !has_invariant(&evaluation, QUANT_INVARIANT),
            "{gamma} finite positive gamma should have no quant failure"
        );
    }
    for gamma in [0.0, -0.0, -1.0, f32::NAN, f32::INFINITY, f32::NEG_INFINITY] {
        let mut candidate = base.clone();
        candidate.records[0].gray_gamma = gamma;
        let evaluation = evaluate(&source, &upstream, &candidate);
        assert!(
            has_invariant(&evaluation, QUANT_INVARIANT),
            "{gamma} missing quant failure"
        );
    }
}

#[test]
fn quantization_invalid_stops_before_later_checks() {
    let (source, upstream, base) = reports("mono_1bit");
    let mut stopped = base.clone();
    assert!(!stopped.records[0].pixels.is_empty());
    stopped.records[0].output_bits = 0;
    stopped.records[0].pixels[0] = 200;
    stopped.records[0].coverage_sha256 = "0".repeat(64);
    stopped.records[0].fitted_commands = vec![FittedCommand::LineTo(1.0, 0.0)];
    let evaluation = evaluate(&source, &upstream, &stopped);
    assert!(has_invariant(&evaluation, QUANT_INVARIANT));
    for unexpected in [
        PIXEL_LEVEL_INVARIANT,
        COVERAGE_CHECKSUM_INVARIANT,
        OUTLINE_INVARIANT,
        STORED_RASTER_INVARIANT,
    ] {
        assert!(
            !has_invariant(&evaluation, unexpected),
            "quant policy must stop before {unexpected}"
        );
    }
    let ordered: Vec<&str> = evaluation
        .hard_failures
        .iter()
        .map(|failure| failure.invariant.as_str())
        .collect();
    assert_eq!(ordered, vec![QUANT_INVARIANT, POLICY_INVARIANT]);
    let mut buffered = base.clone();
    buffered.records[0].pixels.pop();
    buffered.records[0].mono_threshold = 0;
    buffered.records[0].coverage_sha256 = "0".repeat(64);
    buffered.records[0].fitted_commands = vec![FittedCommand::LineTo(1.0, 0.0)];
    let evaluation = evaluate(&source, &upstream, &buffered);
    assert!(!evaluation.hard_invariants_pass);
    let ordered: Vec<&str> = evaluation
        .hard_failures
        .iter()
        .map(|failure| failure.invariant.as_str())
        .collect();
    assert_eq!(
        ordered,
        vec![BUFFER_INVARIANT, QUANT_INVARIANT, POLICY_INVARIANT]
    );
}
