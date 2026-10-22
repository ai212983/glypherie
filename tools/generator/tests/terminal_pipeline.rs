#![cfg(feature = "candidate")]
use font_generator::{
    candidate, evaluation,
    reference::{reference, RasterPolicy, ReferenceRequest},
    renderer::Rasterization,
    Config, Hinting, MonoRasterSettings,
};

fn captures(
    name: &str,
    size: f32,
    weight: f32,
    text: &str,
) -> (
    font_generator::reference::ReferenceReport,
    font_generator::reference::ReferenceReport,
    font_generator::reference::ReferenceReport,
    font_generator::reference::ReferenceReport,
) {
    let data = std::fs::read(format!(
        "{}/../../fonts/{name}.ttf",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap();
    let mut settings = Config {
        size_px: size,
        characters: text.into(),
        ..Config::default()
    };
    settings.axes.insert("wght".into(), weight);
    let mut req = ReferenceRequest {
        profile: "mono_1bit".into(),
        extensions: "none".into(),
        settings,
    };
    let upstream = reference(&data, &req).unwrap();
    req.settings.hinting = Hinting::None;
    let source = reference(&data, &req).unwrap();
    req.extensions = "font-hints-01".into();
    req.settings.hinting = Hinting::AutoFallback;
    req.settings.mono_raster = MonoRasterSettings {
        include_stubs: true,
        font_instructions: true,
        ..Default::default()
    };
    let raw = candidate::render(&data, &req).unwrap();
    let capped =
        candidate::render_with_rasterization(&data, &req, Rasterization::FreeTypeMonoTerminals)
            .unwrap();
    (source, upstream, raw, capped)
}

#[test]
fn terminal_stage_keeps_fitting_layout_and_reconstructible_source_identity() {
    // TrueType SCANTYPE terminal semantics apply to raster rescues, so
    // fitted outlines and their metrics must remain identical.
    let (source, upstream, raw, capped) = captures("RobotoFlex", 16., 400., "1k");
    for (a, b) in raw.records.iter().zip(&capped.records) {
        assert_eq!(a.fitted_commands, b.fitted_commands);
        assert_eq!(
            (a.advance_26_6, a.hinted_lsb, a.hinted_advance_width),
            (b.advance_26_6, b.hinted_lsb, b.hinted_advance_width)
        );
        assert_eq!(
            (a.left, a.top, a.width, a.height),
            (b.left, b.top, b.width, b.height)
        );
        assert_eq!(a.coverage, b.coverage);
        assert_eq!(b.raster_policy, RasterPolicy::FreeTypeMonoTerminals);
        assert!(b.source_commands.is_some());
    }
    assert_eq!(raw.records[0].pixels, capped.records[0].pixels);
    assert_ne!(raw.records[1].pixels, capped.records[1].pixels);
    let check = evaluation::evaluate(&source, &upstream, &capped);
    assert!(
        check.hard_invariants_pass,
        "{:?}",
        check
            .hard_failures
            .iter()
            .map(|f| &f.invariant)
            .collect::<Vec<_>>()
    );
    let mut corrupt = capped;
    corrupt.records[0].source_commands.as_mut().unwrap().clear();
    assert!(!evaluation::evaluate(&source, &upstream, &corrupt).hard_invariants_pass);
}

#[test]
fn curved_junctions_retain_the_raw_scan_at_small_sizes() {
    // The geometric eligibility gate abstains on these source-connected
    // curved junctions; exact identity verifies that untouched path.
    for size in [12., 13., 14., 15.] {
        let (source, upstream, raw, capped) = captures("SourceSans3", size, 200., "R69");
        for (a, b) in raw.records.iter().zip(&capped.records) {
            assert_eq!(a.pixels, b.pixels, "size {size} U+{:04X}", a.codepoint);
        }
        assert!(evaluation::evaluate(&source, &upstream, &capped).hard_invariants_pass);
    }
}

#[test]
fn executed_font_scan_instructions_keep_the_existing_path() {
    let (_, _, raw, capped) = captures("Roboto", 16., 400., "1kR69");
    for (a, b) in raw.records.iter().zip(&capped.records) {
        assert_eq!(a.selected_engine, "interpreter");
        assert_eq!(a.pixels, b.pixels);
        assert_eq!(a.font_scan, b.font_scan);
        assert_eq!(b.raster_policy, RasterPolicy::FreeTypeMono);
        assert!(b.source_commands.is_none());
    }
}

#[test]
fn inapplicable_manual_controls_preserve_raw_capture_provenance() {
    // SCANTYPE-style cap suppression consumes only smart with-stubs rescues.
    let data = std::fs::read(format!(
        "{}/../../fonts/RobotoFlex.ttf",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap();
    for controls in [
        MonoRasterSettings::default(),
        MonoRasterSettings {
            dropout: font_generator::MonoDropoutMode::Simple,
            include_stubs: true,
            font_instructions: false,
        },
    ] {
        let request = ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: "font-hints-01".into(),
            settings: Config {
                characters: "1k".into(),
                mono_raster: controls,
                ..Config::default()
            },
        };
        let raw = candidate::render(&data, &request).unwrap();
        let capped = candidate::render_with_rasterization(
            &data,
            &request,
            Rasterization::FreeTypeMonoTerminals,
        )
        .unwrap();
        assert_eq!(
            serde_json::to_value(raw).unwrap(),
            serde_json::to_value(capped).unwrap()
        );
    }
}
