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
