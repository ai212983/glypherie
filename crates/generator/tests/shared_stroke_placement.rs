#![cfg(feature = "candidate")]
//! Whole-feature placement regressions: eligibility is source geometry,
//! never a glyph-specific pixel target (Hobby §§3.5–3.6; Hersch §§5–6).
use font_generator::{
    candidate,
    evaluation::evaluate,
    probe::FittedCommand,
    reference::{reference, ReferenceRequest},
    renderer::{Rasterization, RenderPipeline},
    stem_fitting::StemFittingStrategy,
    Config, Hinting, MonoRasterSettings,
};

fn request() -> ReferenceRequest {
    ReferenceRequest {
        profile: "mono_1bit".into(),
        extensions: "font-hints-auto-01".into(),
        settings: Config {
            characters: "HNV".into(),
            size_px: 16.0,
            hinting: Hinting::AutoFallback,
            mono_raster: MonoRasterSettings {
                font_instructions: true,
                include_stubs: true,
                ..Default::default()
            },
            ..Config::default()
        },
    }
}

#[test]
fn shared_placement_moves_n_attachments_and_phases_v_without_changing_layout() {
    let data = std::fs::read(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../fonts/RobotoFlex.ttf"
    ))
    .unwrap();
    let request = request();
    let render = |enabled| {
        candidate::render_with_pipeline(
            &data,
            &request,
            RenderPipeline {
                fitting: StemFittingStrategy::FontHintsAuto,
                rasterization: Rasterization::FreeTypeMonoTerminals,
                diagonal_fitting: enabled,
            },
        )
        .unwrap()
    };
    let off = render(false);
    let on = render(true);
    assert_eq!(
        off.records[0].fitted_commands,
        on.records[0].fitted_commands
    );
    assert_eq!(off.records[0].pixels, on.records[0].pixels);
    for (up, new) in off.records.iter().zip(&on.records) {
        assert_eq!(up.advance_26_6, new.advance_26_6);
        assert_eq!(up.hinted_advance_width, new.hinted_advance_width);
        for (a, b) in up.fitted_commands.iter().zip(&new.fitted_commands) {
            let ys = |c: &FittedCommand| match *c {
                FittedCommand::MoveTo(_, y) | FittedCommand::LineTo(_, y) => vec![y],
                FittedCommand::QuadTo(_, y1, _, y) => vec![y1, y],
                FittedCommand::CurveTo(_, y1, _, y2, _, y) => vec![y1, y2, y],
                FittedCommand::Close => vec![],
            };
            assert_eq!(
                ys(a),
                ys(b),
                "all preceding Y constraints stay authoritative"
            );
        }
    }
    let n = &on.records[1];
    assert_eq!(n.codepoint, u32::from('N'));
    assert_eq!(
        n.diagonal_fitting.as_ref().unwrap().model,
        "diagonal-placement-01"
    );
    assert!(
        off.records[1]
            .fitted_commands
            .iter()
            .zip(&n.fitted_commands)
            .any(|(a, b)| { matches!(a, FittedCommand::QuadTo(..)) && a != b }),
        "whole-stroke solve must move the eligible curved attachments, not only cap endpoints"
    );
    let v = &on.records[2];
    assert_eq!(v.codepoint, u32::from('V'));
    let v_capture = v.diagonal_fitting.as_ref().unwrap();
    assert_eq!(v_capture.model, "diagonal-placement-01");
    assert_eq!(v_capture.reason, "placement:shared-placement");
    let xs = v
        .fitted_commands
        .iter()
        .filter_map(|c| match *c {
            FittedCommand::MoveTo(x, _)
            | FittedCommand::LineTo(x, _)
            | FittedCommand::QuadTo(_, _, x, _) => Some(x),
            _ => None,
        })
        .collect::<Vec<_>>();
    let outer_sum = xs.iter().copied().fold(f32::INFINITY, f32::min)
        + xs.iter().copied().fold(f32::NEG_INFINITY, f32::max);
    assert_eq!(
        outer_sum.fract(),
        0.0,
        "reflected frame axis must preserve the pixel-center lattice"
    );
    let mut source_request = request.clone();
    source_request.extensions = "none".into();
    source_request.settings.hinting = Hinting::None;
    source_request.settings.mono_raster = Default::default();
    let source = reference(&data, &source_request).unwrap();
    source_request.settings.hinting = Hinting::Auto;
    let upstream = reference(&data, &source_request).unwrap();
    let evaluation = evaluate(&source, &upstream, &on);
    assert!(
        evaluation.hard_invariants_pass,
        "{:?}",
        evaluation.hard_failures
    );
}
