#![cfg(feature = "candidate")]

//! Selectable stem-fitting strategies: `FontHintsFirst` is the default and
//! `UpstreamMono` (`mono-width-01`, explicit experimental) renders registry
//! `Target::Mono` through the same pinned monochrome scanner with source metrics.
//! Mechanical checks only; no optical acceptance. There is no StrokeStyles
//! strategy, and none may be named here until one executes.

use font_generator::{
    candidate,
    evaluation::evaluate,
    mono,
    reference::{
        reference, RasterPolicy, ReferenceRequest, EXTENSIONS_NONE, PROFILE_GRAY_3BIT,
        PROFILE_MONO_1BIT,
    },
    renderer::RendererRole,
    stem_fitting::{StemFittingStrategy, EXTENSIONS_FONT_HINTS_FIRST, EXTENSIONS_MONO_WIDTH_01},
    surface::{render_text_with_fitting_strategy, HAlign, TextRenderRequest, WrapMode},
    Config, Hinting,
};
use std::collections::HashMap;
use std::path::Path;

fn font_bytes() -> Vec<u8> {
    std::fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fonts/Roboto.ttf"))
        .expect("fixture fonts/Roboto.ttf")
}

fn fixture_bytes(name: &str) -> Vec<u8> {
    std::fs::read(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../fonts")
            .join(name),
    )
    .unwrap_or_else(|_| panic!("fixture fonts/{name}"))
}

fn mono_config() -> Config {
    let mut config = Config::default();
    config.size_px = 16.0;
    config.characters = "aHm".into();
    config.hinting = Hinting::Auto;
    config.output_bits = 1;
    config.axes.insert("wght".into(), 400.0);
    config
}

fn request(extensions: &str, profile: &str) -> ReferenceRequest {
    let mut config = mono_config();
    if profile == PROFILE_GRAY_3BIT {
        config.output_bits = 3;
    }
    ReferenceRequest {
        profile: profile.into(),
        extensions: extensions.into(),
        settings: config,
    }
}

fn records_by_codepoint(
    report: &font_generator::reference::ReferenceReport,
) -> HashMap<u32, &font_generator::reference::ReferenceRecord> {
    report
        .records
        .iter()
        .map(|record| (record.codepoint, record))
        .collect()
}

#[test]
fn strategy_selects_extension_with_font_hints_default() {
    assert_eq!(
        StemFittingStrategy::extension(None),
        EXTENSIONS_FONT_HINTS_FIRST
    );
    assert_eq!(
        StemFittingStrategy::extension(Some(StemFittingStrategy::FontHintsFirst)),
        EXTENSIONS_FONT_HINTS_FIRST
    );
    assert_eq!(
        StemFittingStrategy::extension(Some(StemFittingStrategy::UpstreamMono)),
        EXTENSIONS_MONO_WIDTH_01
    );
    assert_eq!(
        serde_json::from_str::<StemFittingStrategy>("\"font_hints_first\"").unwrap(),
        StemFittingStrategy::FontHintsFirst
    );
    assert_eq!(
        serde_json::from_str::<StemFittingStrategy>("\"upstream_mono\"").unwrap(),
        StemFittingStrategy::UpstreamMono
    );
    assert!(serde_json::from_str::<StemFittingStrategy>("\"strokestyles\"").is_err());
    assert!(serde_json::from_str::<StemFittingStrategy>("\"auto\"").is_err());
    assert!(serde_json::from_str::<StemFittingStrategy>("\"vertical_only\"").is_err());
}

#[test]
fn literata_scan_only_prep_falls_back_to_automatic() {
    use skrifa::{FontRef, MetadataProvider};
    let data = fixture_bytes("Literata.ttf");
    let face = FontRef::new(&data).unwrap();
    // Fixture premise: no `fpgm`, a scan-control-only `prep` (PUSHW 511,
    // SCANCTRL, PUSHB 4, SCANTYPE), and a misleading zero maximum, so
    // upstream still prefers the interpreter despite empty glyph programs.
    assert!(face.table_data(skrifa::Tag::new(b"fpgm")).is_none());
    assert_eq!(
        face.table_data(skrifa::Tag::new(b"prep"))
            .unwrap()
            .as_bytes(),
        &[0xb8, 0x01, 0xff, 0x85, 0xb0, 0x04, 0x8d]
    );
    let maxp = face.table_data(skrifa::Tag::new(b"maxp")).unwrap();
    assert_eq!(&maxp.as_bytes()[26..28], &[0u8, 0u8][..]);
    assert!(face.outline_glyphs().prefer_interpreter());
    let mut config = mono_config();
    config.characters = "ij".into();
    config.hinting = Hinting::AutoFallback;
    config.axes.insert("opsz".into(), 12.0);
    let actual = candidate::render(
        &data,
        &ReferenceRequest {
            profile: PROFILE_MONO_1BIT.into(),
            extensions: EXTENSIONS_FONT_HINTS_FIRST.into(),
            settings: config.clone(),
        },
    )
    .unwrap();
    assert_eq!(actual.hinting_requested, "auto_fallback");
    assert!(!actual.records.is_empty());
    for record in &actual.records {
        assert_eq!(record.selected_engine, "auto", "U+{:04X}", record.codepoint);
    }
    let mut explicit = config.clone();
    explicit.hinting = Hinting::Auto;
    let expected = font_generator::reference::reference(
        &data,
        &ReferenceRequest {
            profile: PROFILE_MONO_1BIT.into(),
            extensions: font_generator::reference::EXTENSIONS_NONE.into(),
            settings: explicit,
        },
    )
    .unwrap();
    for (a, b) in actual.records.iter().zip(&expected.records) {
        assert_eq!(
            a.fitted_commands, b.fitted_commands,
            "U+{:04X}",
            a.codepoint
        );
    }
}

#[test]
fn mono_strategy_geometry_matches_independent_upstream_mono() {
    let data = font_bytes();
    let upstream = reference(&data, &request(EXTENSIONS_NONE, PROFILE_MONO_1BIT)).unwrap();
    let fitted =
        candidate::render(&data, &request(EXTENSIONS_MONO_WIDTH_01, PROFILE_MONO_1BIT)).unwrap();
    assert_eq!(fitted.extensions, EXTENSIONS_MONO_WIDTH_01);
    assert_eq!(fitted.target, "mono");
    assert!(fitted
        .implementation
        .starts_with("skrifa-mono-width-01:registry:"));
    // Source metrics unchanged: same advances, ids, layout metrics, repertoire.
    assert_eq!(fitted.metrics, upstream.metrics);
    assert_eq!(fitted.missing_codepoints, upstream.missing_codepoints);
    let strategy_records = records_by_codepoint(&fitted);
    let upstream_records = records_by_codepoint(&upstream);
    assert_eq!(strategy_records.keys().collect::<Vec<_>>().len(), 3);
    for (codepoint, record) in &strategy_records {
        let baseline = upstream_records[codepoint];
        // Independent upstream-Mono fitted commands equal the strategy geometry.
        assert_eq!(
            record.fitted_commands, baseline.fitted_commands,
            "U+{codepoint:04X}: strategy geometry must equal upstream Mono"
        );
        assert_eq!(record.glyph_id, baseline.glyph_id);
        assert_eq!(record.advance_26_6, baseline.advance_26_6);
        assert_eq!(record.raster_policy, RasterPolicy::FreeTypeMono);
        assert!(
            record.side_bearing_deltas_26_6.is_some(),
            "U+{codepoint:04X}: automatic fitting carries its residuals",
        );
        assert_eq!(record.diagonal_pairs, None);
    }
}

#[test]
fn mono_strategy_pixels_match_pinned_scanner_on_upstream_geometry() {
    let data = font_bytes();
    let config = mono_config();
    let upstream = reference(&data, &request(EXTENSIONS_NONE, PROFILE_MONO_1BIT)).unwrap();
    let fitted =
        candidate::render(&data, &request(EXTENSIONS_MONO_WIDTH_01, PROFILE_MONO_1BIT)).unwrap();
    let strategy_records = records_by_codepoint(&fitted);
    for record in &upstream.records {
        let raster = mono::rasterize(&record.fitted_commands, &config).unwrap();
        let stored = strategy_records[&record.codepoint];
        assert_eq!(stored.pixels, raster.pixels);
        assert_eq!(stored.coverage, raster.coverage);
        assert_eq!(
            (stored.left, stored.top, stored.width, stored.height),
            (raster.left, raster.top, raster.width, raster.height)
        );
    }
}

#[test]
fn evaluation_accepts_mono_strategy_and_names_target_drift() {
    let data = font_bytes();
    let mut source_config = mono_config();
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
    let upstream = reference(&data, &request(EXTENSIONS_NONE, PROFILE_MONO_1BIT)).unwrap();
    let fitted =
        candidate::render(&data, &request(EXTENSIONS_MONO_WIDTH_01, PROFILE_MONO_1BIT)).unwrap();
    let evaluation = evaluate(&source, &upstream, &fitted);
    assert!(
        evaluation.hard_invariants_pass,
        "unexpected failures: {:?}",
        evaluation.hard_failures
    );
    // A relabelled target is caught by the mono-width declaration guard
    // independently of the font-hints-first policy.
    let mut drifted = fitted.clone();
    drifted.target = "smooth".into();
    let drifted_evaluation = evaluate(&source, &upstream, &drifted);
    assert!(!drifted_evaluation.hard_invariants_pass);
    assert!(
        drifted_evaluation
            .hard_failures
            .iter()
            .any(|failure| failure.invariant
                == "Mono candidate must declare the upstream mono target"),
        "unexpected failures: {:?}",
        drifted_evaluation.hard_failures
    );
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
fn unset_strategy_keeps_font_hints_default_on_surface() {
    let data = font_bytes();
    let req = surface_request(mono_config(), "aHm");
    let current =
        render_text_with_fitting_strategy(&data, &req, RendererRole::Candidate, 0.0, None).unwrap();
    let unset =
        render_text_with_fitting_strategy(&data, &req, RendererRole::Candidate, 0.0, None).unwrap();
    assert_eq!(unset.pixels, current.pixels);
    assert_eq!(unset.lines, current.lines);
    let font_hints = render_text_with_fitting_strategy(
        &data,
        &req,
        RendererRole::Candidate,
        0.0,
        Some(StemFittingStrategy::FontHintsFirst),
    )
    .unwrap();
    assert_eq!(font_hints.pixels, current.pixels);
}

#[test]
fn strategy_surface_keeps_tracking_and_spacing_validation_for_blank_text() {
    let data = font_bytes();
    let request = surface_request(mono_config(), "");
    for strategy in [None, Some(StemFittingStrategy::UpstreamMono)] {
        for tracking in [f32::NAN, 17.0] {
            let error = render_text_with_fitting_strategy(
                &data,
                &request,
                RendererRole::Candidate,
                tracking,
                strategy,
            )
            .unwrap_err();
            assert!(error.0.contains("letter_spacing_px"));
        }
    }
    let mut gray = request;
    gray.config.output_bits = 3;
    let error = render_text_with_fitting_strategy(
        &data,
        &gray,
        RendererRole::Baseline,
        0.0,
        Some(StemFittingStrategy::UpstreamMono),
    )
    .unwrap_err();
    assert!(error.0.contains("candidate preview role"));
}

#[test]
fn explicit_strategy_routes_and_rejects_before_blank_handling() {
    let data = font_bytes();
    let req = surface_request(mono_config(), "aHm");
    // Explicit upstream-Mono renders through the mono-width extension.
    let _ = render_text_with_fitting_strategy(
        &data,
        &req,
        RendererRole::Candidate,
        0.0,
        Some(StemFittingStrategy::UpstreamMono),
    )
    .unwrap();
    let via_enum =
        candidate::render(&data, &request(EXTENSIONS_MONO_WIDTH_01, PROFILE_MONO_1BIT)).unwrap();
    assert_eq!(via_enum.extensions, EXTENSIONS_MONO_WIDTH_01);
    // Wrong role, gray depth, non-automatic hinting and blank text reject.
    assert!(render_text_with_fitting_strategy(
        &data,
        &req,
        RendererRole::Baseline,
        0.0,
        Some(StemFittingStrategy::UpstreamMono),
    )
    .unwrap_err()
    .0
    .contains("candidate preview role"));
    let mut gray = mono_config();
    gray.output_bits = 3;
    assert!(render_text_with_fitting_strategy(
        &data,
        &surface_request(gray, "aHm"),
        RendererRole::Candidate,
        0.0,
        Some(StemFittingStrategy::UpstreamMono),
    )
    .unwrap_err()
    .0
    .contains("monochrome output_bits 1"));
    let mut unhinted = mono_config();
    unhinted.hinting = Hinting::None;
    assert!(render_text_with_fitting_strategy(
        &data,
        &surface_request(unhinted, "aHm"),
        RendererRole::Candidate,
        0.0,
        Some(StemFittingStrategy::UpstreamMono),
    )
    .unwrap_err()
    .0
    .contains("automatic hinting"));
    assert!(render_text_with_fitting_strategy(
        &data,
        &surface_request(mono_config(), ""),
        RendererRole::Candidate,
        0.0,
        Some(StemFittingStrategy::UpstreamMono),
    )
    .is_ok());
    // Direct routing guards: unknown extension and gray under mono-width.
    assert!(
        candidate::render(&data, &request("diagonal-01", PROFILE_MONO_1BIT))
            .unwrap_err()
            .0
            .contains("candidate rendering requires font-hints-01 or mono-width-01")
    );
    assert!(
        candidate::render(&data, &request(EXTENSIONS_MONO_WIDTH_01, PROFILE_GRAY_3BIT),)
            .unwrap_err()
            .0
            .contains("requires profile 'mono_1bit'")
    );
}
