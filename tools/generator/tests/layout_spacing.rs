//! Numerical model contracts, independent of glyph fitting or optical scores.
use font_generator::layout_spacing::{EngineInputs, SpacingEngine, SpacingModel};
use std::collections::HashMap;

fn inputs(model: SpacingModel, enabled: bool) -> EngineInputs<'static> {
    EngineInputs {
        model,
        source_advances_26_6: HashMap::from([(65, 6 * 64), (86, 7 * 64)]),
        fitted_advances_26_6: HashMap::from([(65, 8 * 64), (86, 8 * 64)]),
        kern_26_6: HashMap::from([((65, 86), -64), ((86, 65), -32)]),
        bearing_deltas_26_6: HashMap::from([(65, [0, 48]), (86, [0, 0])]),
        pair: None,
        minimum: None,
        apply_kerning: enabled,
        mono: true,
        letter_spacing_px: 0.0,
    }
}

#[test]
fn strategies_choose_advances_and_apply_asymmetric_source_kerning_once() {
    let source = SpacingEngine::new(inputs(SpacingModel::Source, true)).unwrap();
    assert_eq!(source.place(0, None, 65), Some((0, 6 * 64)));
    assert_eq!(source.place(6 * 64, Some(65), 86), Some((5 * 64, 12 * 64)));
    assert_eq!(
        source.place(7 * 64, Some(86), 65),
        Some((7 * 64 - 32, 13 * 64 - 32))
    );
    // Fitted right-bearing residual48 crosses the documented FT boundary,
    // so the AV step contains one source kern and one bearing correction.
    let fitted = SpacingEngine::new(inputs(SpacingModel::Fitted, true)).unwrap();
    assert_eq!(fitted.place(0, None, 65), Some((0, 8 * 64)));
    assert_eq!(fitted.place(8 * 64, Some(65), 86), Some((6 * 64, 14 * 64)));
}

#[test]
fn disabling_kerning_preserves_bearing_policy_and_translation() {
    for model in [SpacingModel::Source, SpacingModel::Fitted] {
        let engine = SpacingEngine::new(inputs(model, false)).unwrap();
        let step = if model == SpacingModel::Source {
            6 * 64
        } else {
            8 * 64
        };
        let pair = engine.place(step, Some(65), 86).unwrap();
        assert_eq!(engine.pair_kern(Some(65), 86), 0);
        assert_eq!(
            pair.0,
            step - if model == SpacingModel::Fitted { 64 } else { 0 }
        );
        for shift in [-21 * 64, 37 * 64] {
            let moved = engine.place(step + shift, Some(65), 86).unwrap();
            assert_eq!(moved, (pair.0 + shift, pair.1 + shift));
        }
    }
}

/// ASCII space codepoint: the existing explicit word-wrap separator and the
/// only whitespace this spacing policy treats as a word gap.
const SPACE_CP: u32 = ' ' as u32;

fn word_inputs(
    mono: bool,
    model: SpacingModel,
    letter_spacing_px: f32,
    kerning: bool,
) -> EngineInputs<'static> {
    EngineInputs {
        model,
        source_advances_26_6: HashMap::from([(65, 6 * 64), (66, 7 * 64), (SPACE_CP, 4 * 64)]),
        fitted_advances_26_6: HashMap::from([(65, 8 * 64), (66, 9 * 64), (SPACE_CP, 5 * 64)]),
        kern_26_6: HashMap::from([((65, SPACE_CP), -16), ((SPACE_CP, 66), 24), ((65, 66), -32)]),
        bearing_deltas_26_6: HashMap::from([(65, [0, 48]), (66, [16, 0]), (SPACE_CP, [8, 8])]),
        pair: None,
        minimum: None,
        apply_kerning: kerning,
        mono,
        letter_spacing_px,
    }
}

/// Origins and final pen for `text` starting at `pen`.
fn lay(engine: &SpacingEngine, pen: i64, text: &[u32]) -> (Vec<i64>, i64) {
    let mut pen = pen;
    let mut previous = None;
    let mut origins = Vec::with_capacity(text.len());
    for &current in text {
        let (origin, next) = engine.place(pen, previous, current).unwrap();
        origins.push(origin);
        pen = next;
        previous = Some(current);
    }
    (origins, pen)
}

#[test]
fn negative_tracking_preserves_neutral_word_gap_geometry() {
    // Explicit user policy: negative tracking keeps word gaps at neutral
    // width. Entering the first space refunds the preceding nonspace
    // glyph's trailing step once; leading/repeated spaces take no refund
    // and internal letter tightening is unchanged.
    for mono in [true, false] {
        // Explicit fitted-family models are monochrome-only; gray layout
        // always uses the source model with fractional tracking.
        let models: &[SpacingModel] = if mono {
            &[SpacingModel::Source, SpacingModel::Fitted]
        } else {
            &[SpacingModel::Source]
        };
        for model in models {
            for kerning in [true, false] {
                let offset = if mono { -1.0 } else { -0.5 };
                let neutral = SpacingEngine::new(word_inputs(mono, *model, 0.0, kerning)).unwrap();
                let tracked =
                    SpacingEngine::new(word_inputs(mono, *model, offset, kerning)).unwrap();
                let step = i64::from(tracked.tracking_26_6());
                assert!(step < 0);
                for text in [
                    vec![65, SPACE_CP, 66],
                    vec![SPACE_CP, 65],
                    vec![65, SPACE_CP],
                    vec![65, SPACE_CP, SPACE_CP, 66],
                    vec![SPACE_CP, SPACE_CP, 65],
                    vec![65, 66, SPACE_CP, 65, SPACE_CP, SPACE_CP, 66],
                ] {
                    for pen in [0, 37 * 64, -21 * 64] {
                        let (base, base_pen) = lay(&neutral, pen, &text);
                        let (origins, final_pen) = lay(&tracked, pen, &text);
                        assert_eq!(origins[0], base[0]);
                        for i in 1..text.len() {
                            let gap = origins[i] - origins[i - 1];
                            let base_gap = base[i] - base[i - 1];
                            if text[i - 1] != SPACE_CP && text[i] != SPACE_CP {
                                assert_eq!(gap, base_gap + step);
                            } else {
                                assert_eq!(gap, base_gap);
                            }
                        }
                        let trailing = if text[text.len() - 1] == SPACE_CP {
                            0
                        } else {
                            step
                        };
                        assert_eq!(
                            final_pen - origins[text.len() - 1],
                            (base_pen - base[text.len() - 1]) + trailing
                        );
                    }
                }
            }
        }
    }
}

#[test]
fn extreme_negative_tracking_keeps_word_gaps_without_overflow() {
    for mono in [true, false] {
        let models: &[SpacingModel] = if mono {
            &[SpacingModel::Source, SpacingModel::Fitted]
        } else {
            &[SpacingModel::Source]
        };
        for model in models {
            let neutral = SpacingEngine::new(word_inputs(mono, *model, 0.0, true)).unwrap();
            let tracked = SpacingEngine::new(word_inputs(mono, *model, -16.0, true)).unwrap();
            let step = i64::from(tracked.tracking_26_6());
            assert_eq!(step, -16 * 64);
            let text = vec![65, SPACE_CP, 66, SPACE_CP, SPACE_CP, 65];
            for pen in [0, 1_000_000] {
                let (base, _) = lay(&neutral, pen, &text);
                let (origins, _) = lay(&tracked, pen, &text);
                assert_eq!(origins[0], base[0]);
                for i in 1..text.len() {
                    let gap = origins[i] - origins[i - 1];
                    let base_gap = base[i] - base[i - 1];
                    if text[i - 1] != SPACE_CP && text[i] != SPACE_CP {
                        assert_eq!(gap, base_gap + step);
                    } else {
                        assert_eq!(gap, base_gap);
                    }
                }
            }
        }
    }
}

#[test]
fn positive_tracking_still_applies_to_spaces() {
    for mono in [true, false] {
        let models: &[SpacingModel] = if mono {
            &[SpacingModel::Source, SpacingModel::Fitted]
        } else {
            &[SpacingModel::Source]
        };
        for model in models {
            let offset = if mono { 1.0 } else { 0.25 };
            let neutral = SpacingEngine::new(word_inputs(mono, *model, 0.0, true)).unwrap();
            let tracked = SpacingEngine::new(word_inputs(mono, *model, offset, true)).unwrap();
            let step = i64::from(tracked.tracking_26_6());
            assert!(step > 0);
            let text = vec![65, SPACE_CP, 66];
            for pen in [0, 37 * 64] {
                let (base, base_pen) = lay(&neutral, pen, &text);
                let (origins, final_pen) = lay(&tracked, pen, &text);
                assert_eq!(origins[0], base[0]);
                for i in 1..text.len() {
                    assert_eq!(origins[i] - origins[i - 1], base[i] - base[i - 1] + step);
                }
                assert_eq!(
                    final_pen - origins[text.len() - 1],
                    (base_pen - base[text.len() - 1]) + step
                );
            }
        }
    }
}

#[test]
fn invalid_engine_inputs_and_missing_glyphs_are_explicit() {
    assert!(SpacingEngine::new(inputs(SpacingModel::Auto, true)).is_err());
    assert!(SpacingEngine::new(inputs(SpacingModel::Projected, true)).is_err());
    let mut malformed = inputs(SpacingModel::Source, true);
    malformed.letter_spacing_px = f32::NAN;
    assert!(SpacingEngine::new(malformed).is_err());
    let source = SpacingEngine::new(inputs(SpacingModel::Source, true)).unwrap();
    assert!(!source.has_glyph(90));
    assert_eq!(source.place(0, None, 90), None);
    assert_eq!(source.place(i64::MAX, None, 65), None);
}

#[cfg(feature = "candidate")]
mod renderer {
    use super::*;
    use font_generator::{
        candidate, generate,
        reference::ReferenceRequest,
        renderer::RendererRole,
        surface::{
            render_text_with_renderer_and_spacing, render_text_with_spacing_model, HAlign,
            TextRenderRequest, WrapMode,
        },
        Config,
    };
    fn bytes() -> Vec<u8> {
        std::fs::read(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../fonts/Roboto.ttf"
        ))
        .unwrap()
    }
    fn req(text: &str) -> TextRenderRequest {
        let mut config = Config {
            size_px: 14.0,
            ..Config::default()
        };
        config.axes.insert("wght".into(), 641.0);
        config.axes.insert("wdth".into(), 100.0);
        TextRenderRequest {
            config,
            text: text.into(),
            width: 512,
            height: 256,
            wrap: WrapMode::Clip,
            align: HAlign::Left,
            foreground: [0, 0, 0, 255],
            background: [255, 255, 255, 255],
            palette: None,
        }
    }
    fn render(
        data: &[u8],
        req: &TextRenderRequest,
        model: SpacingModel,
        spacing: f32,
    ) -> font_generator::surface::RenderedText {
        render_text_with_spacing_model(data, req, RendererRole::Candidate, spacing, model).unwrap()
    }
    #[test]
    fn source_and_fitted_layout_follow_independent_metrics_and_source_kern() {
        let data = bytes();
        for kern in [false, true] {
            let mut request = req("AV VA");
            request.config.kerning = kern;
            let mut settings = request.config.clone();
            settings.characters = request.text.clone();
            let source = generate(&data, &settings).unwrap();
            let fitted = candidate::render(
                &data,
                &ReferenceRequest {
                    profile: "mono_1bit".into(),
                    extensions: "diagonal-01".into(),
                    settings,
                },
            )
            .unwrap();
            for model in [SpacingModel::Source, SpacingModel::Fitted] {
                let mut expected = 0i32;
                let mut previous = None;
                let mut previous_rsb = 0;
                for ch in request.text.chars() {
                    let cp = ch as u32;
                    let pair_kern = source
                        .kerning
                        .iter()
                        .find(|k| Some(k.left) == previous && k.right == cp)
                        .map_or(0, |k| k.adjustment_26_6);
                    expected += pair_kern;
                    if model == SpacingModel::Source {
                        expected += source
                            .glyphs
                            .iter()
                            .find(|g| g.codepoint == cp)
                            .unwrap()
                            .advance_26_6;
                    } else {
                        let record = fitted.records.iter().find(|r| r.codepoint == cp).unwrap();
                        let delta = record.side_bearing_deltas_26_6.unwrap_or([0, 0]);
                        let difference = previous_rsb - delta[0];
                        expected += if difference > 32 {
                            -64
                        } else if difference < -31 {
                            64
                        } else {
                            0
                        };
                        expected += record
                            .hinted_advance_width
                            .map(|width| (width * 64.0).round() as i32)
                            .unwrap_or(record.advance_26_6);
                        previous_rsb = delta[1];
                    }
                    previous = Some(cp);
                }
                assert_eq!(
                    render(&data, &request, model, 0.0).lines[0].width_26_6,
                    expected
                );
            }
        }
    }
    #[test]
    fn projected_is_current_default_and_models_do_not_change_single_glyph_shapes() {
        let data = bytes();
        let request = req("mi in ac AV VA");
        assert_eq!(
            render(&data, &request, SpacingModel::Auto, -1.0),
            render(&data, &request, SpacingModel::Projected, -1.0)
        );
        assert_eq!(
            render(&data, &request, SpacingModel::Auto, 0.0),
            render_text_with_renderer_and_spacing(&data, &request, RendererRole::Candidate, 0.0)
                .unwrap()
        );
        for role in [
            RendererRole::Baseline,
            RendererRole::Reference,
            RendererRole::Candidate,
        ] {
            for ch in ["m", "i", "a", "c", "V"] {
                let request = req(ch);
                let shape = |model| {
                    let rendered =
                        render_text_with_spacing_model(&data, &request, role, 0.0, model).unwrap();
                    let mut ink = rendered
                        .pixels
                        .chunks_exact(4)
                        .enumerate()
                        .filter(|(_, p)| *p == [0, 0, 0, 255])
                        .map(|(i, _)| {
                            (
                                (i % rendered.width as usize) as i32,
                                (i / rendered.width as usize) as i32,
                            )
                        })
                        .collect::<Vec<_>>();
                    let x = ink.iter().map(|(x, _)| *x).min().unwrap();
                    for point in &mut ink {
                        point.0 -= x;
                    }
                    ink
                };
                let source = shape(SpacingModel::Source);
                assert_eq!(shape(SpacingModel::Fitted), source);
                assert_eq!(shape(SpacingModel::Projected), source);
            }
        }
    }
    #[test]
    fn negative_tracking_keeps_single_letter_word_pixels_at_neutral_origins() {
        // Explicit user policy: single-letter words have no internal
        // tightening, so every origin stays neutral under negative
        // tracking and only the trailing advance keeps the step. Covers
        // the Source/Fitted/Projected adapters across preview roles.
        let data = bytes();
        // Explicit models are monochrome-only; gray word gaps are verified
        // through the Auto path in spacing_control.
        for role in [
            RendererRole::Baseline,
            RendererRole::Reference,
            RendererRole::Candidate,
        ] {
            for model in [
                SpacingModel::Source,
                SpacingModel::Fitted,
                SpacingModel::Projected,
            ] {
                for text in ["a a", "l l"] {
                    let neutral_request = req(text);
                    let neutral =
                        render_text_with_spacing_model(&data, &neutral_request, role, 0.0, model)
                            .unwrap();
                    let tracked =
                        render_text_with_spacing_model(&data, &neutral_request, role, -1.0, model)
                            .unwrap();
                    assert_eq!(tracked.pixels, neutral.pixels);
                    assert_eq!(
                        tracked.lines[0].width_26_6 - neutral.lines[0].width_26_6,
                        -64
                    );
                }
            }
        }
    }
    #[test]
    fn every_model_measures_wrap_and_floor_using_its_placement() {
        let data = bytes();
        for model in [
            SpacingModel::Source,
            SpacingModel::Fitted,
            SpacingModel::Projected,
        ] {
            for wrap in [WrapMode::Word, WrapMode::Char] {
                let mut request = req("mi in ac AV VA mi in ac AV VA");
                request.width = 60;
                request.wrap = wrap;
                let wrapped = render(&data, &request, model, -1.0);
                for line in wrapped.lines {
                    assert!(line.width_26_6 <= 60 * 64);
                    let mut part = request.clone();
                    part.wrap = WrapMode::Clip;
                    part.text = request.text[line.byte_start..line.byte_end].into();
                    assert_eq!(
                        render(&data, &part, model, -1.0).lines[0].width_26_6,
                        line.width_26_6
                    );
                }
            }
        }
    }
}
