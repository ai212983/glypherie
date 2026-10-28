//! Public render-request validation and error precedence.
use font_generator::{
    renderer::{Rasterization, RenderPipeline, RendererRole},
    stem_fitting::StemFittingStrategy,
    surface::{
        render_text, render_text_with_fitting_strategy, render_text_with_pipeline,
        render_text_with_pipeline_and_spacing, render_text_with_renderer_and_spacing, HAlign,
        TextRenderRequest, WrapMode,
    },
    Config, Hinting, MonoDropoutMode, MonoRasterSettings,
};
use std::path::Path;

const FG: [u8; 4] = [0, 0, 0, 255];
const BG: [u8; 4] = [255, 255, 255, 255];
const TRACKING_ERROR: &str = "letter_spacing_px must be finite and within -16..=16";

fn font_bytes() -> Vec<u8> {
    std::fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fonts/Roboto.ttf"))
        .expect("fixture fonts/Roboto.ttf")
}

fn config_16_mono() -> Config {
    let mut config = Config::default();
    config.size_px = 16.0;
    config.output_bits = 1;
    config.hinting = Hinting::Auto;
    config.axes.insert("wght".into(), 400.0);
    config
}

fn request(config: Config, text: &str, width: u32, height: u32) -> TextRenderRequest {
    TextRenderRequest {
        config,
        text: text.into(),
        width,
        height,
        wrap: WrapMode::Clip,
        align: HAlign::Left,
        foreground: FG,
        background: BG,
        palette: None,
    }
}

fn nondefault_mono() -> Config {
    let mut config = config_16_mono();
    config.mono_raster = MonoRasterSettings {
        dropout: MonoDropoutMode::Simple,
        ..Default::default()
    };
    config
}

fn default_pipeline() -> RenderPipeline {
    RenderPipeline {
        fitting: StemFittingStrategy::FontHintsFirst,
        rasterization: Rasterization::FreeTypeMono,
        diagonal_fitting: false,
    }
}

#[test]
fn tracking_rejected_on_renderer_path_under_both_features() {
    let bytes = font_bytes();
    for spacing in [f32::NAN, f32::INFINITY, 16.5, -16.5] {
        let error = render_text_with_renderer_and_spacing(
            &bytes,
            &request(config_16_mono(), "A", 64, 40),
            RendererRole::Baseline,
            spacing,
        )
        .unwrap_err();
        assert_eq!(error.to_string(), TRACKING_ERROR);
    }
    let error = render_text_with_renderer_and_spacing(
        b"not a font",
        &request(config_16_mono(), "A", 64, 40),
        RendererRole::Baseline,
        99.0,
    )
    .unwrap_err();
    assert_eq!(error.to_string(), TRACKING_ERROR);
    for spacing in [16.0, -16.0] {
        let rendered = render_text_with_renderer_and_spacing(
            &bytes,
            &request(config_16_mono(), "A", 64, 40),
            RendererRole::Baseline,
            spacing,
        )
        .unwrap();
        assert_eq!((rendered.width, rendered.height), (64, 40));
        assert_eq!(rendered.pixels.len(), 64 * 40 * 4);
    }
}

#[test]
fn role_depth_and_hinting_gates_before_font_open() {
    let bytes = font_bytes();
    let mut bits2 = config_16_mono();
    bits2.output_bits = 2;
    let error = render_text_with_renderer_and_spacing(
        &bytes,
        &request(bits2, "A", 64, 40),
        RendererRole::Reference,
        0.0,
    )
    .unwrap_err();
    assert_eq!(
        error.to_string(),
        "preview role reference requires output_bits 1 or 3, got 2"
    );
    let mut fallback = config_16_mono();
    fallback.hinting = Hinting::AutoFallback;
    let error = render_text_with_renderer_and_spacing(
        &bytes,
        &request(fallback, "A", 64, 40),
        RendererRole::Reference,
        0.0,
    )
    .unwrap_err();
    assert_eq!(
        error.to_string(),
        "preview role reference requires explicit hinting, got auto_fallback"
    );
    let mut bits2 = config_16_mono();
    bits2.output_bits = 2;
    let error = render_text_with_renderer_and_spacing(
        b"not a font",
        &request(bits2, "A", 64, 40),
        RendererRole::Candidate,
        0.0,
    )
    .unwrap_err();
    assert_eq!(
        error.to_string(),
        "preview role candidate requires output_bits 1 or 3, got 2"
    );
}

#[cfg(feature = "candidate")]
#[test]
fn candidate_hint_priority_beats_mono_strategy_and_blank() {
    let bytes = font_bytes();
    for hinting in [Hinting::None, Hinting::Interpreter] {
        let mut config = nondefault_mono();
        config.hinting = hinting;
        let expected =
            format!("preview role candidate requires automatic hinting, got {hinting:?}");
        for text in ["", "\n", "A"] {
            let error = render_text_with_fitting_strategy(
                &bytes,
                &request(config.clone(), text, 64, 40),
                RendererRole::Candidate,
                0.0,
                Some(StemFittingStrategy::FontHintsFirst),
            )
            .unwrap_err();
            assert_eq!(error.to_string(), expected, "text {text:?}");
        }
    }
}

#[cfg(feature = "candidate")]
#[test]
fn mono_raster_gates_in_priority_order() {
    let bytes = font_bytes();
    let error = render_text_with_renderer_and_spacing(
        &bytes,
        &request(nondefault_mono(), "A", 64, 40),
        RendererRole::Baseline,
        0.0,
    )
    .unwrap_err();
    assert_eq!(
        error.to_string(),
        "mono raster settings require the candidate preview role"
    );
    let mut gray = nondefault_mono();
    gray.output_bits = 3;
    let error = render_text_with_renderer_and_spacing(
        &bytes,
        &request(gray, "A", 64, 40),
        RendererRole::Candidate,
        0.0,
    )
    .unwrap_err();
    assert_eq!(
        error.to_string(),
        "mono raster settings require monochrome output_bits 1, got 3"
    );
    let admitted = request(nondefault_mono(), "A", 64, 40);
    let before = admitted.clone();
    let rendered =
        render_text_with_renderer_and_spacing(&bytes, &admitted, RendererRole::Candidate, 0.0)
            .unwrap();
    assert_eq!(rendered.pixels.len(), 64 * 40 * 4);
    assert_eq!(admitted, before);
}

#[cfg(not(feature = "candidate"))]
#[test]
fn mono_raster_off_feature_errors() {
    let bytes = font_bytes();
    let error = render_text_with_renderer_and_spacing(
        &bytes,
        &request(nondefault_mono(), "A", 64, 40),
        RendererRole::Baseline,
        0.0,
    )
    .unwrap_err();
    assert_eq!(
        error.to_string(),
        "mono raster settings require the candidate Cargo feature"
    );
}

#[cfg(feature = "candidate")]
#[test]
fn strategy_gates_in_priority_order() {
    let bytes = font_bytes();
    let error = render_text_with_fitting_strategy(
        &bytes,
        &request(config_16_mono(), "A", 64, 40),
        RendererRole::Baseline,
        0.0,
        Some(StemFittingStrategy::UpstreamMono),
    )
    .unwrap_err();
    assert_eq!(
        error.to_string(),
        "explicit fitting strategy requires the candidate preview role"
    );
    let mut gray = config_16_mono();
    gray.output_bits = 3;
    let error = render_text_with_fitting_strategy(
        &bytes,
        &request(gray, "A", 64, 40),
        RendererRole::Candidate,
        0.0,
        Some(StemFittingStrategy::UpstreamMono),
    )
    .unwrap_err();
    assert_eq!(
        error.to_string(),
        "explicit fitting strategy requires monochrome output_bits 1, got 3"
    );
    let admitted = request(config_16_mono(), "A", 64, 40);
    let before = admitted.clone();
    let rendered = render_text_with_fitting_strategy(
        &bytes,
        &admitted,
        RendererRole::Candidate,
        0.0,
        Some(StemFittingStrategy::UpstreamMono),
    )
    .unwrap();
    assert_eq!(rendered.pixels.len(), 64 * 40 * 4);
    assert_eq!(admitted, before);
}

#[cfg(not(feature = "candidate"))]
#[test]
fn strategy_off_feature_errors() {
    let bytes = font_bytes();
    let error = render_text_with_fitting_strategy(
        &bytes,
        &request(config_16_mono(), "A", 64, 40),
        RendererRole::Baseline,
        0.0,
        Some(StemFittingStrategy::UpstreamMono),
    )
    .unwrap_err();
    assert_eq!(
        error.to_string(),
        "explicit fitting strategy requires the candidate Cargo feature"
    );
}

#[cfg(feature = "candidate")]
#[test]
fn fitting_wrapper_reports_tracking_not_feature() {
    let bytes = font_bytes();
    let error = render_text_with_fitting_strategy(
        &bytes,
        &request(config_16_mono(), "A", 64, 40),
        RendererRole::Candidate,
        f32::NAN,
        None,
    )
    .unwrap_err();
    assert_eq!(error.to_string(), TRACKING_ERROR);
}

#[cfg(not(feature = "candidate"))]
#[test]
fn fitting_wrapper_feature_error_preempts_tracking() {
    let bytes = font_bytes();
    let error = render_text_with_fitting_strategy(
        &bytes,
        &request(config_16_mono(), "A", 64, 40),
        RendererRole::Candidate,
        f32::NAN,
        None,
    )
    .unwrap_err();
    assert_eq!(
        error.to_string(),
        "candidate rendering requires the candidate Cargo feature"
    );
}

#[test]
fn pipeline_validate_runs_before_feature_and_role() {
    let diagonal = RenderPipeline {
        fitting: StemFittingStrategy::FontHintsAuto,
        rasterization: Rasterization::FreeTypeMono,
        diagonal_fitting: true,
    };
    let mut gray3 = config_16_mono();
    gray3.output_bits = 3;
    let error = render_text_with_pipeline(
        &font_bytes(),
        &request(gray3.clone(), "A", 64, 40),
        diagonal,
    )
    .unwrap_err();
    assert_eq!(
        error.to_string(),
        "diagonal fitting requires 1-bit FreeTypeMono/Terminals with FontHintsAuto or UpstreamMono"
    );
    let error = render_text_with_pipeline(b"not a font", &request(gray3, "A", 64, 40), diagonal)
        .unwrap_err();
    assert_eq!(
        error.to_string(),
        "diagonal fitting requires 1-bit FreeTypeMono/Terminals with FontHintsAuto or UpstreamMono"
    );
}

#[cfg(feature = "candidate")]
#[test]
fn admitted_pipeline_renders() {
    let bytes = font_bytes();
    let rendered = render_text_with_pipeline_and_spacing(
        &bytes,
        &request(config_16_mono(), "A", 64, 40),
        default_pipeline(),
        0.0,
    )
    .unwrap();
    assert_eq!((rendered.width, rendered.height), (64, 40));
    assert_eq!(rendered.pixels.len(), 64 * 40 * 4);
}

#[cfg(not(feature = "candidate"))]
#[test]
fn pipeline_off_feature_errors_after_validate() {
    let bytes = font_bytes();
    let error = render_text_with_pipeline(
        &bytes,
        &request(config_16_mono(), "A", 64, 40),
        default_pipeline(),
    )
    .unwrap_err();
    assert_eq!(
        error.to_string(),
        "explicit pipeline requires the candidate Cargo feature"
    );
}

#[cfg(feature = "candidate")]
#[test]
fn candidate_normalization_matches_explicit_pipeline() {
    let bytes = font_bytes();
    let legacy = request(config_16_mono(), "A", 64, 40);
    let before = legacy.clone();
    let via_role =
        render_text_with_renderer_and_spacing(&bytes, &legacy, RendererRole::Candidate, 0.0)
            .unwrap();
    assert_eq!(legacy, before);
    let via_pipeline = render_text_with_pipeline_and_spacing(
        &bytes,
        &legacy,
        RenderPipeline {
            fitting: StemFittingStrategy::FontHintsFirst,
            rasterization: Rasterization::FreeTypeMono,
            diagonal_fitting: false,
        },
        0.0,
    )
    .unwrap();
    assert_eq!(legacy, before);
    assert_eq!(via_role, via_pipeline);
    let mut fallback = config_16_mono();
    fallback.hinting = Hinting::AutoFallback;
    let via_fallback = render_text_with_fitting_strategy(
        &bytes,
        &request(fallback, "A", 64, 40),
        RendererRole::Candidate,
        0.0,
        Some(StemFittingStrategy::UpstreamMono),
    )
    .unwrap();
    let via_auto = render_text_with_fitting_strategy(
        &bytes,
        &request(config_16_mono(), "A", 64, 40),
        RendererRole::Candidate,
        0.0,
        Some(StemFittingStrategy::UpstreamMono),
    )
    .unwrap();
    assert_eq!(via_fallback, via_auto);
}

#[test]
fn text_limit_accepts_boundary() {
    let bytes = font_bytes();
    let accepted =
        render_text(&bytes, &request(config_16_mono(), &"\n".repeat(8192), 1, 1)).unwrap();
    assert_eq!(accepted.pixels.len(), 4);
    assert_eq!(accepted.pixels, BG.to_vec());
    let error =
        render_text(&bytes, &request(config_16_mono(), &"\n".repeat(8193), 1, 1)).unwrap_err();
    assert_eq!(error.to_string(), "text exceeds 8192 characters");
}
