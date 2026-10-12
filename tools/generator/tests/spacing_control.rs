//! Explicit tracking is a layout control; it must not alter glyph shapes.
use font_generator::{
    renderer::RendererRole,
    surface::{
        render_text_with_renderer, render_text_with_renderer_and_spacing, HAlign,
        TextRenderRequest, WrapMode,
    },
    Config,
};

fn fixture() -> Vec<u8> {
    std::fs::read(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../fonts/Roboto.ttf"
    ))
    .unwrap()
}

fn request(text: &str) -> TextRenderRequest {
    let mut config = Config {
        size_px: 14.0,
        ..Config::default()
    };
    config.axes.insert("wght".into(), 536.0);
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

fn roles() -> Vec<RendererRole> {
    #[allow(unused_mut)]
    let mut roles = vec![RendererRole::Baseline, RendererRole::Reference];
    #[cfg(feature = "candidate")]
    roles.push(RendererRole::Candidate);
    roles
}

#[test]
fn zero_is_identity_and_signed_tracking_includes_spaces_and_kerned_pairs() {
    let bytes = fixture();
    for role in roles() {
        for bits in [1, 3] {
            for text in ["mi li ni AV VA", "a a", " "] {
                let mut req = request(text);
                req.config.output_bits = bits;
                let neutral = render_text_with_renderer(&bytes, &req, role).unwrap();
                assert_eq!(
                    neutral,
                    render_text_with_renderer_and_spacing(&bytes, &req, role, 0.0).unwrap()
                );
                for spacing in [-1.0, 0.25, 1.0] {
                    let tracked =
                        render_text_with_renderer_and_spacing(&bytes, &req, role, spacing).unwrap();
                    assert_eq!(tracked.lines.len(), 1);
                    let effective = if bits == 1 {
                        spacing.round() * 64.0
                    } else {
                        spacing * 64.0
                    };
                    let delta = tracked.lines[0].width_26_6 - neutral.lines[0].width_26_6;
                    if spacing >= 0.0 {
                        // Positive tracking still applies to every glyph.
                        let requested = text.chars().count() as i32 * effective as i32;
                        assert_eq!(delta, requested);
                    } else if bits == 3 {
                        // Explicit user policy: negative tracking keeps word
                        // gaps at neutral width, so only nonspace glyphs
                        // without a following space keep the step (gray has
                        // no minimum floor, hence exact).
                        assert_eq!(delta, kept_tracking_steps(text) * effective as i32);
                    } else {
                        // The minimum floor can limit letter tightening;
                        // compression must never exceed the kept steps.
                        assert!(delta >= kept_tracking_steps(text) * effective as i32);
                    }
                }
            }
        }
    }
}

#[test]
fn tracking_moves_whole_glyphs_without_changing_their_ink() {
    let bytes = fixture();
    for role in roles() {
        let req = request("l l");
        let neutral = render_text_with_renderer_and_spacing(&bytes, &req, role, 0.0).unwrap();
        let wider = render_text_with_renderer_and_spacing(&bytes, &req, role, 1.0).unwrap();
        let ink = |image: &font_generator::surface::RenderedText| {
            image
                .pixels
                .chunks_exact(4)
                .enumerate()
                .filter(|(_, px)| *px == [0, 0, 0, 255])
                .map(|(i, _)| {
                    (
                        (i % image.width as usize) as i32,
                        (i / image.width as usize) as i32,
                    )
                })
                .collect::<Vec<_>>()
        };
        let before = ink(&neutral);
        let after = ink(&wider);
        assert_eq!(before.len(), after.len());
        // Two narrow l glyphs are separated by a space. Each next origin
        // gains 1px per preceding glyph, including the intervening space.
        let split = before.iter().map(|(x, _)| *x).max().unwrap() / 2;
        let expected = before
            .into_iter()
            .map(|(x, y)| (x + if x > split { 2 } else { 0 }, y))
            .collect::<Vec<_>>();
        assert_eq!(after, expected);
    }
}

#[test]
fn wrapping_measures_the_same_tracked_advances_as_placement() {
    let bytes = fixture();
    for role in roles() {
        for wrap in [WrapMode::Word, WrapMode::Char] {
            let mut req = request("mi li ni AV VA mi li ni AV VA");
            req.wrap = wrap;
            req.width = 60;
            let neutral = render_text_with_renderer_and_spacing(&bytes, &req, role, 0.0).unwrap();
            let wider = render_text_with_renderer_and_spacing(&bytes, &req, role, 4.0).unwrap();
            assert!(wider.lines.len() > neutral.lines.len());
            for spacing in [-2.0, -0.5, 4.0] {
                let tracked =
                    render_text_with_renderer_and_spacing(&bytes, &req, role, spacing).unwrap();
                for line in &tracked.lines {
                    assert!(line.width_26_6 <= req.width as i32 * 64);
                    let part = &req.text[line.byte_start..line.byte_end];
                    let mut clipped = req.clone();
                    clipped.text = part.into();
                    clipped.wrap = WrapMode::Clip;
                    assert_eq!(
                        render_text_with_renderer_and_spacing(&bytes, &clipped, role, spacing)
                            .unwrap()
                            .lines[0]
                            .width_26_6,
                        line.width_26_6
                    );
                }
            }
        }
    }
}

#[test]
fn invalid_spacing_is_rejected_even_for_empty_text() {
    let bytes = fixture();
    for offset in [f32::NAN, f32::INFINITY, -16.25, 16.25] {
        let error = render_text_with_renderer_and_spacing(
            &bytes,
            &request(""),
            RendererRole::Baseline,
            offset,
        )
        .unwrap_err();
        assert!(error.to_string().contains("letter_spacing_px"));
    }
}

#[cfg(feature = "candidate")]
#[test]
fn reported_pairs_keep_one_column_and_fractional_mono_offsets_are_normalized() {
    let bytes = fixture();
    let mut req = request("mi\nin\nac");
    req.config.axes.insert("wght".into(), 641.0);
    for spacing in [-0.5, -1.0, -2.0] {
        let rendered =
            render_text_with_renderer_and_spacing(&bytes, &req, RendererRole::Candidate, spacing)
                .unwrap();
        for (line_index, line) in rendered.lines.iter().enumerate() {
            let mut spans: Vec<(u32, u32)> = Vec::new();
            for x in 0..rendered.width {
                let occupied = (line_index as u32 * line.height_px
                    ..(line_index as u32 + 1) * line.height_px)
                    .any(|y| rendered.pixels[((y * rendered.width + x) * 4) as usize] == 0);
                if occupied {
                    match spans.last_mut() {
                        Some((_, hi)) if x == *hi + 1 => *hi = x,
                        _ => spans.push((x, x)),
                    }
                }
            }
            assert_eq!(
                spans.len(),
                2,
                "pair {}, offset {spacing}",
                &req.text[line.byte_start..line.byte_end]
            );
            assert_eq!(spans[1].0 - spans[0].1 - 1, 1);
        }
    }
    assert_eq!(
        render_text_with_renderer_and_spacing(&bytes, &req, RendererRole::Candidate, -0.5).unwrap(),
        render_text_with_renderer_and_spacing(&bytes, &req, RendererRole::Candidate, -1.0).unwrap(),
    );
}

/// Nonspace glyphs whose advance keeps negative tracking: spaces stay
/// neutral and each entry into a space run refunds the preceding glyph's
/// step exactly once, so glyphs immediately followed by a space keep none.
fn kept_tracking_steps(text: &str) -> i32 {
    let chars: Vec<char> = text.chars().collect();
    chars
        .iter()
        .enumerate()
        .filter(|(index, glyph)| {
            **glyph != ' ' && chars.get(index + 1).map_or(true, |next| *next != ' ')
        })
        .count() as i32
}

#[test]
fn negative_tracking_keeps_word_gaps_at_neutral_width() {
    // Explicit user policy superseding the former one-pixel space floor:
    // negative tracking leaves neutral word gaps unchanged. Single-letter
    // words keep every origin, so their ink is unchanged and only the
    // trailing advance keeps one step; leading, trailing and repeated
    // spaces are neutral with no double refund.
    let bytes = fixture();
    for role in roles() {
        for bits in [1, 3] {
            let render = |text: &str, spacing: f32| {
                let mut req = request(text);
                req.config.output_bits = bits;
                render_text_with_renderer_and_spacing(&bytes, &req, role, spacing).unwrap()
            };
            for spacing in [-1.0f32, -2.0] {
                let step = if bits == 1 {
                    spacing.round() as i32 * 64
                } else {
                    (spacing * 64.0) as i32
                };
                assert_eq!(
                    render(" ", spacing).lines[0].width_26_6,
                    render(" ", 0.0).lines[0].width_26_6
                );
                for text in ["a a", "l l"] {
                    let (neutral, tracked) = (render(text, 0.0), render(text, spacing));
                    assert_eq!(tracked.pixels, neutral.pixels);
                    assert_eq!(
                        tracked.lines[0].width_26_6 - neutral.lines[0].width_26_6,
                        step
                    );
                }
                assert_eq!(
                    render("a ", spacing).lines[0].width_26_6,
                    render("a ", 0.0).lines[0].width_26_6
                );
                let (neutral, tracked) = (render(" a", 0.0), render(" a", spacing));
                assert_eq!(tracked.pixels, neutral.pixels);
                assert_eq!(
                    tracked.lines[0].width_26_6 - neutral.lines[0].width_26_6,
                    step
                );
                let (neutral, tracked) = (render("a  b", 0.0), render("a  b", spacing));
                assert_eq!(
                    tracked.lines[0].width_26_6 - neutral.lines[0].width_26_6,
                    step
                );
            }
        }
    }
}
