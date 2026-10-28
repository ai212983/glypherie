#![cfg(feature = "candidate")]
use font_generator::{
    candidate, evaluation,
    reference::{reference, ReferenceRequest},
    renderer::Rasterization,
    Config, Hinting, MonoRasterSettings,
};
fn captures(
    font: &str,
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
        "{}/../../fonts/{font}.ttf",
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
    req.settings.hinting = Hinting::AutoFallback;
    req.settings.mono_raster = MonoRasterSettings {
        include_stubs: true,
        font_instructions: true,
        ..Default::default()
    };
    req.extensions = "font-hints-01".into();
    let raw =
        candidate::render_with_rasterization(&data, &req, Rasterization::FreeTypeMonoTerminals)
            .unwrap();
    req.extensions = "source-width-01".into();
    let fit =
        candidate::render_with_rasterization(&data, &req, Rasterization::FreeTypeMonoTerminals)
            .unwrap();
    (source, upstream, raw, fit)
}
#[test]
fn source_width_capture_reproduces_and_keeps_attachment_and_advance() {
    // Hobby (5)/(17): coupled relative width errors preserve source contrast.
    let (source, upstream, raw, fit) = captures("RobotoFlex", 16., 400., "1k");
    let a = &raw.records[0];
    let b = &fit.records[0];
    assert!(
        b.width_fitting.is_some(),
        "reported straight feature must be recognized"
    );
    assert_ne!(a.fitted_commands, b.fitted_commands);
    assert_ne!(a.pixels, b.pixels);
    assert_eq!(
        (a.advance_26_6, a.hinted_lsb, a.hinted_advance_width),
        (b.advance_26_6, b.hinted_lsb, b.hinted_advance_width)
    );
    assert!(evaluation::evaluate(&source, &upstream, &fit).hard_invariants_pass);
    let mut corrupt = fit.clone();
    corrupt.records[0]
        .width_fitting
        .as_mut()
        .unwrap()
        .upstream_commands
        .clear();
    assert!(!evaluation::evaluate(&source, &upstream, &corrupt).hard_invariants_pass);
    let mut corrupt = fit;
    corrupt.records[0].source_commands.as_mut().unwrap().clear();
    assert!(!evaluation::evaluate(&source, &upstream, &corrupt).hard_invariants_pass);
}
#[test]
fn source_width_keeps_interpreter_geometry_and_curved_junctions() {
    // Unsupported curved ownership and authoritative font hints keep their path.
    for (font, weight) in [("Roboto", 400.), ("SourceSans3", 200.)] {
        let (source, upstream, raw, fit) = captures(font, 12., weight, "R69");
        for (a, b) in raw.records.iter().zip(&fit.records) {
            assert_eq!(a.fitted_commands, b.fitted_commands);
            assert_eq!(a.pixels, b.pixels);
            assert!(b.width_fitting.is_none());
        }
        assert!(evaluation::evaluate(&source, &upstream, &fit).hard_invariants_pass);
    }
}
