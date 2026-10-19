//! Numerical placement contracts, independent of glyph fitting or optical scores.
//!
//! The engine consumes already-finalized advances and pair adjustments:
//! source layout passes fractional values, bitmap layout passes whole
//! pixels. These tests pin the single-application, word-gap and tracking
//! rules for both feedings without re-deriving a renderer's metrics.
use font_generator::layout_spacing::{quantize_26_6, EngineInputs, SpacingEngine};
use std::collections::HashMap;

/// Finalized pair table as an adapter would bake it: AV carries source
/// kern -64 plus the -64 fitting correction, VA carries only -32.
fn inputs() -> EngineInputs<'static> {
    EngineInputs {
        advances_26_6: HashMap::from([(65, 6 * 64), (86, 7 * 64)]),
        pair_adjustments_26_6: HashMap::from([((65, 86), -128), ((86, 65), -32)]),
        guard_kern_26_6: HashMap::from([((65, 86), -64), ((86, 65), -32)]),
        minimum: None,
        mono: true,
        integer_positions: true,
        letter_spacing_px: 0.0,
    }
}

fn plain_inputs() -> EngineInputs<'static> {
    let mut inputs = inputs();
    inputs.pair_adjustments_26_6 = HashMap::from([((65, 86), -64), ((86, 65), -32)]);
    inputs
}

#[test]
fn quantization_is_nearest_pixel_and_sign_symmetric() {
    for (value, expected) in [
        (0, 0),
        (31, 0),
        (32, 64),
        (33, 64),
        (64 + 31, 64),
        (64 + 32, 128),
        (-31, 0),
        (-32, -64),
        (-33, -64),
        (-(64 + 32), -128),
        (506, 512),
        (-506, -512),
    ] {
        assert_eq!(quantize_26_6(value), expected, "quantize {value}");
        assert_eq!(quantize_26_6(-value), -expected, "sign symmetry {value}");
    }
}

#[test]
fn placement_applies_asymmetric_pair_kern_once() {
    // Source-layout feeding: fractional pair values pass through as the
    // finalized pair adjustments for that role.
    let source = SpacingEngine::new(inputs()).unwrap();
    assert_eq!(source.place(0, None, 65), Some((0, 6 * 64)));
    assert_eq!(source.place(6 * 64, Some(65), 86), Some((4 * 64, 11 * 64)));
    let plain = SpacingEngine::new(plain_inputs()).unwrap();
    assert_eq!(plain.place(0, None, 65), Some((0, 6 * 64)));
    assert_eq!(plain.place(6 * 64, Some(65), 86), Some((5 * 64, 12 * 64)));
    assert_eq!(
        plain.place(7 * 64, Some(86), 65),
        Some((7 * 64 - 32, 13 * 64 - 32))
    );
}

#[test]
fn bitmap_feeding_places_whole_pixels_with_baked_correction_once() {
    // Bitmap feeding: the pair table already contains kern plus the
    // fitting correction; placement applies that value exactly once and
    // never adds another correction at draw time.
    let engine = SpacingEngine::new(inputs()).unwrap();
    assert_eq!(engine.place(0, None, 65), Some((0, 6 * 64)));
    assert_eq!(engine.place(6 * 64, Some(65), 86), Some((4 * 64, 11 * 64)));
    // Every origin stays a whole pixel regardless of the starting pixel.
    for start in [-3 * 64, 0, 5 * 64] {
        let (origin, next) = engine.place(start + 6 * 64, Some(65), 86).unwrap();
        assert_eq!((origin - start) % 64, 0);
        assert_eq!((next - start) % 64, 0);
    }
}

#[test]
fn kerning_off_table_retains_only_the_baked_fitting_correction() {
    // An adapter with kerning disabled bakes only the -64 correction
    // into the pair table; placement applies that single value.
    let mut kerning_off = plain_inputs();
    kerning_off.pair_adjustments_26_6 = HashMap::from([((65, 86), -64)]);
    let engine = SpacingEngine::new(kerning_off).unwrap();
    assert_eq!(engine.pair_kern(Some(65), 86), -64);
    assert_eq!(engine.place(6 * 64, Some(65), 86), Some((5 * 64, 12 * 64)));
    for shift in [-21 * 64, 37 * 64] {
        let moved = engine.place(6 * 64 + shift, Some(65), 86).unwrap();
        assert_eq!(moved, (5 * 64 + shift, 12 * 64 + shift));
    }
    let mut no_correction = plain_inputs();
    no_correction.pair_adjustments_26_6.clear();
    let plain = SpacingEngine::new(no_correction).unwrap();
    assert_eq!(plain.place(6 * 64, Some(65), 86), Some((6 * 64, 13 * 64)));
}

#[test]
fn negative_and_overhang_pair_adjustments_are_not_floored_at_neutral() {
    // Signed kerning stronger than the advance moves the next origin back
    // over the previous glyph; neutral layout imposes no blank-column floor.
    let mut overhang = plain_inputs();
    overhang.pair_adjustments_26_6 = HashMap::from([((65, 86), -8 * 64)]);
    overhang.guard_kern_26_6 = overhang.pair_adjustments_26_6.clone();
    let engine = SpacingEngine::new(overhang).unwrap();
    assert_eq!(engine.place(6 * 64, Some(65), 86), Some((-2 * 64, 5 * 64)));
}

/// ASCII space codepoint: the existing explicit word-wrap separator and the
/// only whitespace this spacing policy treats as a word gap.
const SPACE_CP: u32 = ' ' as u32;

fn word_inputs(mono: bool, letter_spacing_px: f32, kerning: bool) -> EngineInputs<'static> {
    // With kerning disabled the adapter bakes an empty pair table; the
    // word-gap comparisons below only require that both engines agree.
    let pairs = if kerning {
        HashMap::from([((65, SPACE_CP), -16), ((SPACE_CP, 66), 24), ((65, 66), -32)])
    } else {
        HashMap::new()
    };
    EngineInputs {
        advances_26_6: HashMap::from([(65, 6 * 64), (66, 7 * 64), (SPACE_CP, 4 * 64)]),
        pair_adjustments_26_6: pairs.clone(),
        guard_kern_26_6: pairs,
        minimum: None,
        mono,
        integer_positions: mono,
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
        for kerning in [true, false] {
            let offset = if mono { -1.0 } else { -0.5 };
            let neutral = SpacingEngine::new(word_inputs(mono, 0.0, kerning)).unwrap();
            let tracked = SpacingEngine::new(word_inputs(mono, offset, kerning)).unwrap();
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

#[test]
fn extreme_negative_tracking_keeps_word_gaps_without_overflow() {
    for mono in [true, false] {
        let neutral = SpacingEngine::new(word_inputs(mono, 0.0, true)).unwrap();
        let tracked = SpacingEngine::new(word_inputs(mono, -16.0, true)).unwrap();
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

#[test]
fn positive_tracking_still_applies_to_spaces() {
    for mono in [true, false] {
        let offset = if mono { 1.0 } else { 0.25 };
        let neutral = SpacingEngine::new(word_inputs(mono, 0.0, true)).unwrap();
        let tracked = SpacingEngine::new(word_inputs(mono, offset, true)).unwrap();
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

#[test]
fn invalid_engine_inputs_and_missing_glyphs_are_explicit() {
    let mut malformed = inputs();
    malformed.letter_spacing_px = f32::NAN;
    assert!(SpacingEngine::new(malformed).is_err());
    let engine = SpacingEngine::new(inputs()).unwrap();
    assert!(!engine.has_glyph(90));
    assert_eq!(engine.place(0, None, 90), None);
    assert_eq!(engine.place(i64::MAX, None, 65), None);
}

#[cfg(feature = "candidate")]
mod renderer {
    use font_generator::{
        renderer::RendererRole,
        surface::{render_text_with_renderer_and_spacing, HAlign, TextRenderRequest, WrapMode},
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

    #[test]
    fn candidate_and_baseline_single_glyph_shapes_agree() {
        let data = bytes();
        for role in [
            RendererRole::Baseline,
            RendererRole::Reference,
            RendererRole::Candidate,
        ] {
            for ch in ["m", "i", "a", "c", "V"] {
                let request = req(ch);
                let rendered =
                    render_text_with_renderer_and_spacing(&data, &request, role, 0.0).unwrap();
                assert_eq!(rendered.lines.len(), 1);
                assert!(
                    rendered
                        .pixels
                        .chunks_exact(4)
                        .any(|pixel| *pixel == [0, 0, 0, 255]),
                    "{role:?} {ch} must render ink"
                );
            }
        }
        // Candidate line widths are whole pixels at neutral tracking.
        let rendered = render_text_with_renderer_and_spacing(
            &data,
            &req("mi in ac AV VA"),
            RendererRole::Candidate,
            0.0,
        )
        .unwrap();
        assert_eq!(rendered.lines[0].width_26_6 % 64, 0);
    }

    #[test]
    fn negative_tracking_keeps_single_letter_word_pixels_at_neutral_origins() {
        // Explicit user policy: single-letter words have no internal
        // tightening, so every origin stays neutral under negative
        // tracking and only the trailing advance keeps the step.
        let data = bytes();
        for role in [
            RendererRole::Baseline,
            RendererRole::Reference,
            RendererRole::Candidate,
        ] {
            for text in ["a a", "l l"] {
                let neutral_request = req(text);
                let neutral =
                    render_text_with_renderer_and_spacing(&data, &neutral_request, role, 0.0)
                        .unwrap();
                let tracked =
                    render_text_with_renderer_and_spacing(&data, &neutral_request, role, -1.0)
                        .unwrap();
                assert_eq!(tracked.pixels, neutral.pixels, "{role:?} {text}");
                assert_eq!(
                    tracked.lines[0].width_26_6 - neutral.lines[0].width_26_6,
                    -64
                );
            }
        }
    }

    #[test]
    fn candidate_wrap_measures_the_same_advances_as_placement() {
        let data = bytes();
        for wrap in [WrapMode::Word, WrapMode::Char] {
            let mut request = req("mi in ac AV VA mi in ac AV VA");
            request.width = 60;
            request.wrap = wrap;
            let wrapped = render_text_with_renderer_and_spacing(
                &data,
                &request,
                RendererRole::Candidate,
                -1.0,
            )
            .unwrap();
            for line in wrapped.lines {
                assert!(line.width_26_6 <= 60 * 64);
                assert_eq!(line.width_26_6 % 64, 0);
                let mut part = request.clone();
                part.wrap = WrapMode::Clip;
                part.text = request.text[line.byte_start..line.byte_end].into();
                assert_eq!(
                    render_text_with_renderer_and_spacing(
                        &data,
                        &part,
                        RendererRole::Candidate,
                        -1.0
                    )
                    .unwrap()
                    .lines[0]
                        .width_26_6,
                    line.width_26_6
                );
            }
        }
    }
}
