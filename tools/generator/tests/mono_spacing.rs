#![cfg(feature = "candidate")]

//! Candidate Mono pair layout follows the experimental projected source-gap
//! model (`mono_spacing::PairSpacing`), shared by the interactive surface and
//! native specimens. The old integer-bearing transcription is superseded only
//! for supported candidate pairs; space/empty/missing pairs, first glyphs and
//! the baseline path keep it.

use font_generator::{
    candidate, generate,
    mono_spacing::{tight_source_x, PairSpacing},
    reference::{AdvancePolicy, ReferenceRequest},
    renderer::RendererRole,
    surface::{render_text_with_renderer, HAlign, TextRenderRequest, WrapMode},
    Config,
};
use std::{collections::BTreeMap, path::Path};

fn load_font(name: &str) -> Vec<u8> {
    std::fs::read(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../fonts")
            .join(name),
    )
    .unwrap()
}

fn axes_for(name: &str, wght: f32) -> BTreeMap<String, f32> {
    let mut axes = BTreeMap::from([("wght".into(), wght)]);
    if name == "Roboto.ttf" {
        axes.insert("wdth".into(), 100.0);
    }
    axes
}

fn repertoire_of(text: &str) -> String {
    text.chars().filter(|c| *c != '\n' && *c != '\r').collect()
}

fn config_for(size: f32, axes: BTreeMap<String, f32>, repertoire: &str) -> Config {
    Config {
        size_px: size,
        axes,
        characters: repertoire.into(),
        ..Config::default()
    }
}

fn candidate_report(
    bytes: &[u8],
    size: f32,
    axes: BTreeMap<String, f32>,
    repertoire: &str,
) -> font_generator::reference::ReferenceReport {
    candidate::render(
        bytes,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: "diagonal-01".into(),
            settings: config_for(size, axes, repertoire),
        },
    )
    .unwrap()
}

fn source_report(
    bytes: &[u8],
    size: f32,
    axes: BTreeMap<String, f32>,
    repertoire: &str,
) -> font_generator::reference::ReferenceReport {
    let mut settings = config_for(size, axes, repertoire);
    settings.hinting = font_generator::Hinting::None;
    font_generator::reference::reference(
        bytes,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: "none".into(),
            settings,
        },
    )
    .unwrap()
}

/// Independent source-gap target from raw fields: tight outline extents plus
/// source advance and pair kern. Mirrors the documented relationship without
/// calling `PairSpacing`, so the layout wiring stays independently checked.
fn source_target_gap(
    source: &font_generator::reference::ReferenceReport,
    left: u32,
    right: u32,
    kern_26_6: i32,
) -> i64 {
    let records: BTreeMap<_, _> = source.records.iter().map(|r| (r.codepoint, r)).collect();
    let (min_right, _) = tight_source_x(&records[&right].fitted_commands).unwrap();
    let (_, max_left) = tight_source_x(&records[&left].fitted_commands).unwrap();
    let gap = f64::from(records[&left].advance_26_6) / 64.0
        + f64::from(kern_26_6) / 64.0
        + f64::from(min_right)
        - f64::from(max_left);
    (gap + 0.5).floor() as i64
}

fn ink_extent(record: &font_generator::reference::ReferenceRecord) -> (i32, i32) {
    let mut min_col: Option<i32> = None;
    let mut max_col: Option<i32> = None;
    for y in 0..record.height {
        for x in 0..record.width {
            if record.pixels[(y * record.width + x) as usize] == 0 {
                continue;
            }
            let column = record.left + x as i32;
            min_col = Some(min_col.map_or(column, |best| best.min(column)));
            max_col = Some(max_col.map_or(column, |best| best.max(column)));
        }
    }
    (min_col.unwrap(), max_col.unwrap())
}

fn expected_pair_extra(
    source: &font_generator::reference::ReferenceReport,
    fitted: &font_generator::reference::ReferenceReport,
    left: u32,
    right: u32,
    kern: i32,
) -> Option<i32> {
    let a = fitted.records.iter().find(|r| r.codepoint == left)?;
    let b = fitted.records.iter().find(|r| r.codepoint == right)?;
    if left == ' ' as u32
        || right == ' ' as u32
        || !a.pixels.iter().any(|p| *p != 0)
        || !b.pixels.iter().any(|p| *p != 0)
    {
        return None;
    }
    let target = source_target_gap(source, left, right, kern);
    let step = i64::from(ink_extent(a).1) + 1 - i64::from(ink_extent(b).0) + target;
    i32::try_from(step * 64 - i64::from(a.advance_26_6) - i64::from(kern)).ok()
}

fn render_candidate(
    bytes: &[u8],
    size: f32,
    axes: BTreeMap<String, f32>,
    text: &str,
    width: u32,
    wrap: WrapMode,
) -> font_generator::surface::RenderedText {
    let request = TextRenderRequest {
        config: config_for(size, axes, &repertoire_of(text)),
        text: text.into(),
        width,
        height: 64,
        wrap,
        align: HAlign::Left,
        foreground: [0, 0, 0, 255],
        background: [255, 255, 255, 255],
        palette: None,
    };
    render_text_with_renderer(bytes, &request, RendererRole::Candidate).unwrap()
}

#[test]
fn candidate_layout_applies_source_gap_pairs_once() {
    const TEXTS: [&str; 9] = [
        "mi",
        "Pac",
        "quo",
        "AV",
        "VA",
        "mimimimimimimimi",
        "mi\nPac",
        "mi mi",
        "mimimi mimimi",
    ];
    for name in ["Roboto.ttf", "Literata.ttf", "SourceSans3.ttf"] {
        let bytes = load_font(name);
        for size in [14.0, 16.0, 18.0, 20.0] {
            let mut axes = axes_for(name, 400.0);
            if name == "Literata.ttf" {
                axes.insert("opsz".into(), size);
            }
            for text in TEXTS {
                let repertoire = repertoire_of(text);
                let config = config_for(size, axes.clone(), &repertoire);
                let approved = generate(&bytes, &config).unwrap();
                let fitted = candidate_report(&bytes, size, axes.clone(), &repertoire);
                assert_eq!(fitted.advance_policy, AdvancePolicy::Hinted);
                let source = source_report(&bytes, size, axes.clone(), &repertoire);
                let advances: BTreeMap<_, _> = fitted
                    .records
                    .iter()
                    .map(|r| (r.codepoint, r.advance_26_6))
                    .collect();
                let deltas: BTreeMap<_, _> = fitted
                    .records
                    .iter()
                    .map(|r| (r.codepoint, r.side_bearing_deltas_26_6.unwrap_or([0, 0])))
                    .collect();
                let kern: BTreeMap<_, _> = approved
                    .kerning
                    .iter()
                    .map(|p| ((p.left, p.right), p.adjustment_26_6))
                    .collect();
                // Independent transcription of the shared pair rule: source
                // kern once plus the gap extra when supported, else the prior
                // integer-bearing correction. First glyphs keep origin zero.
                let mut expected_lines = Vec::new();
                let mut expected_pixels = [255, 255, 255, 255].repeat(1024 * 64);
                let baseline_y = (i64::from(approved.metrics.ascent_26_6) + 63).div_euclid(64);
                let line_height = ((i64::from(approved.metrics.ascent_26_6)
                    - i64::from(approved.metrics.descent_26_6)
                    + i64::from(approved.metrics.line_gap_26_6)
                    + 63)
                    / 64)
                    .max(1);
                for paragraph in text.split('\n') {
                    let mut pen = 0_i64;
                    let mut previous: Option<u32> = None;
                    let mut previous_rsb = 0;
                    for ch in paragraph.chars().map(|ch| ch as u32) {
                        let current = deltas[&ch];
                        let kern_pair = previous
                            .and_then(|left| kern.get(&(left, ch)).copied())
                            .unwrap_or(0);
                        let adjustment = match previous {
                            Some(left) => {
                                kern_pair
                                    + expected_pair_extra(&source, &fitted, left, ch, kern_pair)
                                        .unwrap_or_else(|| {
                                            let difference = previous_rsb - current[0];
                                            if difference > 32 {
                                                -64
                                            } else if difference < -31 {
                                                64
                                            } else {
                                                0
                                            }
                                        })
                            }
                            None => {
                                let difference = -current[0];
                                if difference > 32 {
                                    -64
                                } else if difference < -31 {
                                    64
                                } else {
                                    0
                                }
                            }
                        };
                        pen += i64::from(adjustment);
                        previous_rsb = current[1];
                        let glyph = fitted.records.iter().find(|r| r.codepoint == ch).unwrap();
                        let origin = (pen + 32).div_euclid(64);
                        for y in 0..glyph.height {
                            for x in 0..glyph.width {
                                if glyph.pixels[(y * glyph.width + x) as usize] == 0 {
                                    continue;
                                }
                                let dx = origin + i64::from(glyph.left) + i64::from(x);
                                let dy = baseline_y
                                    + expected_lines.len() as i64 * line_height
                                    + i64::from(glyph.top)
                                    + i64::from(y);
                                if (0..1024).contains(&dx) && (0..64).contains(&dy) {
                                    let offset = (dy * 1024 + dx) as usize * 4;
                                    expected_pixels[offset..offset + 4]
                                        .copy_from_slice(&[0, 0, 0, 255]);
                                }
                            }
                        }
                        pen += i64::from(advances[&ch]);
                        previous = Some(ch);
                    }
                    expected_lines.push(pen);
                }
                let request = TextRenderRequest {
                    config,
                    text: text.into(),
                    width: 1024,
                    height: 64,
                    wrap: WrapMode::Clip,
                    align: HAlign::Left,
                    foreground: [0, 0, 0, 255],
                    background: [255, 255, 255, 255],
                    palette: None,
                };
                let rendered =
                    render_text_with_renderer(&bytes, &request, RendererRole::Candidate).unwrap();
                assert_eq!(
                    rendered.lines.len(),
                    expected_lines.len(),
                    "{name} {size} {text:?}"
                );
                for (line, expected) in rendered.lines.iter().zip(&expected_lines) {
                    assert_eq!(
                        i64::from(line.width_26_6),
                        *expected,
                        "{name} {size} {text:?}"
                    );
                }
                assert_eq!(
                    rendered.pixels, expected_pixels,
                    "{name} {size} {text:?}: independent composition"
                );
                let baseline =
                    render_text_with_renderer(&bytes, &request, RendererRole::Baseline).unwrap();
                // Baseline keeps linear advances plus source kern, per paragraph.
                let mut design_widths = Vec::new();
                for paragraph in text.split('\n') {
                    let mut width = 0_i64;
                    let mut prev = None;
                    for ch in paragraph.chars().map(|ch| ch as u32) {
                        width += i64::from(
                            approved
                                .glyphs
                                .iter()
                                .find(|g| g.codepoint == ch)
                                .unwrap()
                                .advance_26_6,
                        );
                        if let Some(left) = prev {
                            width += i64::from(*kern.get(&(left, ch)).unwrap_or(&0));
                        }
                        prev = Some(ch);
                    }
                    design_widths.push(width);
                }
                assert_eq!(baseline.lines.len(), design_widths.len());
                for (line, expected) in baseline.lines.iter().zip(&design_widths) {
                    assert_eq!(
                        i64::from(line.width_26_6),
                        *expected,
                        "{name} {size} {text:?}: baseline keeps design advances"
                    );
                }
            }
        }
    }
}

#[test]
fn weight_536_facing_stems_recover_two_pixel_gaps() {
    let bytes = load_font("Roboto.ttf");
    let axes = axes_for("Roboto.ttf", 536.0);
    for (left, right) in [('m', 'i'), ('l', 'i'), ('n', 'i')] {
        let pair: String = [left, right].into_iter().collect();
        let fitted = candidate_report(&bytes, 14.0, axes.clone(), &pair);
        let source = source_report(&bytes, 14.0, axes.clone(), &pair);
        let approved = generate(&bytes, &config_for(14.0, axes.clone(), &pair)).unwrap();
        let kern = approved
            .kerning
            .iter()
            .find(|p| p.left == left as u32 && p.right == right as u32)
            .map(|p| p.adjustment_26_6)
            .unwrap_or(0);
        // Geometry-based target from independent source data: all three
        // facing-stem gaps round to two pixels.
        let target = source_target_gap(&source, left as u32, right as u32, kern);
        assert_eq!(target, 2, "source target for {pair}");
        // Rendered blank-column gap between the delivered ink columns.
        let rendered = render_candidate(&bytes, 14.0, axes.clone(), &pair, 1024, WrapMode::Clip);
        let records: BTreeMap<_, _> = fitted.records.iter().map(|r| (r.codepoint, r)).collect();
        let total = i64::from(rendered.lines[0].width_26_6);
        let origin_right = (total - i64::from(records[&(right as u32)].advance_26_6)) / 64;
        assert!(
            (total - i64::from(records[&(right as u32)].advance_26_6)) % 64 == 0,
            "pair step must land on whole pixels for {pair}"
        );
        let (_, ink_max_left) = ink_extent(records[&(left as u32)]);
        let (ink_min_right, _) = ink_extent(records[&(right as u32)]);
        let gap = origin_right + i64::from(ink_min_right) - i64::from(ink_max_left) - 1;
        assert_eq!(gap, 2, "rendered gap for {pair}");
        assert_eq!(gap, target, "rendered gap meets source target for {pair}");
    }
}

#[test]
fn font_spacing_properties_do_not_depend_on_the_selected_repertoire() {
    let bytes = load_font("Roboto.ttf");
    let axes = axes_for("Roboto.ttf", 536.0);
    let broad = "mnil0123456789AV";
    for pair in ["mm", "li", "17", "AV"] {
        let correction = |repertoire: &str| {
            let config = config_for(14.0, axes.clone(), repertoire);
            let source = source_report(&bytes, 14.0, axes.clone(), repertoire);
            let candidate = candidate_report(&bytes, 14.0, axes.clone(), repertoire);
            let spacing = PairSpacing::from_font(&bytes, &config, &source, &candidate).unwrap();
            let chars: Vec<_> = pair.chars().map(|ch| ch as u32).collect();
            let left = candidate
                .records
                .iter()
                .find(|r| r.codepoint == chars[0])
                .unwrap();
            spacing.correction(chars[0], chars[1], 0, left.advance_26_6)
        };
        let narrow = correction(pair);
        assert_eq!(
            narrow,
            correction(broad),
            "{pair}: unrelated text must not change the pair policy"
        );
        if pair == "17" {
            assert_eq!(
                narrow, None,
                "actual tabular digits retain their advance contract"
            );
        } else {
            assert!(
                narrow.is_some(),
                "equal advances in a subset do not imply a monospace font"
            );
        }
    }
}

#[test]
fn candidate_glyph_bitmaps_are_unchanged_by_spacing() {
    let bytes = load_font("Roboto.ttf");
    let axes = axes_for("Roboto.ttf", 536.0);
    let fitted = candidate_report(&bytes, 14.0, axes.clone(), "mlin");
    let approved = generate(&bytes, &config_for(14.0, axes.clone(), "mlin")).unwrap();
    let baseline_y = (i64::from(approved.metrics.ascent_26_6) + 63).div_euclid(64);
    for ch in ['m', 'l', 'i', 'n'] {
        let single = render_candidate(
            &bytes,
            14.0,
            axes.clone(),
            &ch.to_string(),
            64,
            WrapMode::Clip,
        );
        let record = fitted
            .records
            .iter()
            .find(|r| r.codepoint == ch as u32)
            .unwrap();
        let deltas = record.side_bearing_deltas_26_6.unwrap_or([0, 0]);
        let difference = -deltas[0];
        let origin = if difference > 32 {
            -1
        } else if difference < -31 {
            1
        } else {
            0
        };
        // The record covers antialias coverage, which can include empty Mono
        // border columns. Compare actual ink bounds, then every record cell;
        // spacing must translate the current fitted bitmap without resampling.
        let ink: Vec<_> = record
            .pixels
            .iter()
            .enumerate()
            .filter(|(_, p)| **p != 0)
            .map(|(i, _)| {
                (
                    (i % record.width as usize) as i64,
                    (i / record.width as usize) as i64,
                )
            })
            .collect();
        let ink_bounds = (
            ink.iter().map(|p| p.0).min().unwrap(),
            ink.iter().map(|p| p.1).min().unwrap(),
            ink.iter().map(|p| p.0).max().unwrap(),
            ink.iter().map(|p| p.1).max().unwrap(),
        );
        let mut found: Option<(i64, i64, i64, i64)> = None;
        for (index, cell) in single.pixels.chunks_exact(4).enumerate() {
            if cell[0] == 0 && cell[1] == 0 && cell[2] == 0 {
                let x = (index % 64) as i64;
                let y = (index / 64) as i64;
                found = Some(match found {
                    None => (x, y, x, y),
                    Some((min_x, min_y, max_x, max_y)) => {
                        (min_x.min(x), min_y.min(y), max_x.max(x), max_y.max(y))
                    }
                });
            }
        }
        let (min_x, min_y, max_x, max_y) = found.unwrap();
        assert_eq!(
            min_x,
            origin + i64::from(record.left) + ink_bounds.0,
            "left for {ch}"
        );
        assert_eq!(
            min_y,
            baseline_y + i64::from(record.top) + ink_bounds.1,
            "top for {ch}"
        );
        assert_eq!(
            max_x - min_x + 1,
            ink_bounds.2 - ink_bounds.0 + 1,
            "width for {ch}"
        );
        assert_eq!(
            max_y - min_y + 1,
            ink_bounds.3 - ink_bounds.1 + 1,
            "height for {ch}"
        );
        for y in 0..record.height {
            for x in 0..record.width {
                let expected = record.pixels[(y * record.width + x) as usize];
                let canvas_x = (origin + i64::from(record.left) + i64::from(x)) as usize;
                let canvas_y = (baseline_y + i64::from(record.top) + i64::from(y)) as usize;
                let cell = &single.pixels[(canvas_y * 64 + canvas_x) * 4..][..4];
                if expected == 0 {
                    assert_eq!(cell, &[255, 255, 255, 255], "background for {ch}");
                } else {
                    assert_eq!(cell, &[0, 0, 0, 255], "ink for {ch}");
                }
            }
        }
    }
}

#[test]
fn candidate_char_wrap_uses_the_same_pair_rule() {
    let bytes = load_font("Roboto.ttf");
    let axes = axes_for("Roboto.ttf", 400.0);
    let text = "mimimimimimimimi";
    let repertoire = repertoire_of(text);
    let config = config_for(14.0, axes.clone(), &repertoire);
    let approved = generate(&bytes, &config).unwrap();
    let fitted = candidate_report(&bytes, 14.0, axes.clone(), &repertoire);
    let source = source_report(&bytes, 14.0, axes.clone(), &repertoire);
    let advances: BTreeMap<_, _> = fitted
        .records
        .iter()
        .map(|r| (r.codepoint, r.advance_26_6))
        .collect();
    let deltas: BTreeMap<_, _> = fitted
        .records
        .iter()
        .map(|r| (r.codepoint, r.side_bearing_deltas_26_6.unwrap_or([0, 0])))
        .collect();
    let kern: BTreeMap<_, _> = approved
        .kerning
        .iter()
        .map(|p| ((p.left, p.right), p.adjustment_26_6))
        .collect();
    let pair_adjustment = |previous: Option<u32>, current: u32| -> i64 {
        let pair_kern = previous
            .and_then(|left| kern.get(&(left, current)).copied())
            .unwrap_or(0);
        match previous {
            Some(left) => {
                i64::from(pair_kern)
                    + i64::from(
                        expected_pair_extra(&source, &fitted, left, current, pair_kern)
                            .unwrap_or_else(|| {
                                let difference = deltas[&left][1] - deltas[&current][0];
                                if difference > 32 {
                                    -64
                                } else if difference < -31 {
                                    64
                                } else {
                                    0
                                }
                            }),
                    )
            }
            None => {
                let difference = -deltas[&current][0];
                if difference > 32 {
                    -64
                } else if difference < -31 {
                    64
                } else {
                    0
                }
            }
        }
    };
    // Greedy character wrap transcribed with the same pair rule the wrapping
    // simulation must use.
    let limit = 40_i64 * 64;
    let mut lines: Vec<(i64, Vec<(u32, i64)>)> = vec![(0, Vec::new())];
    let mut last: Option<u32> = None;
    for ch in text.chars().map(|ch| ch as u32) {
        let (pen, _) = lines.last().unwrap();
        let pen = *pen;
        let placed = !lines.last().unwrap().1.is_empty();
        if placed && pen + i64::from(advances[&ch]) + pair_adjustment(last, ch) > limit {
            lines.push((0, Vec::new()));
            last = None;
        }
        let (pen, placed) = lines.last_mut().unwrap();
        let origin = *pen + pair_adjustment(last, ch);
        *pen = origin + i64::from(advances[&ch]);
        placed.push((ch, origin));
        last = Some(ch);
    }
    let rendered = render_candidate(&bytes, 14.0, axes, text, 40, WrapMode::Char);
    assert!(rendered.lines.len() > 1, "narrow canvas must wrap");
    assert_eq!(rendered.lines.len(), lines.len());
    for (line, (pen, _)) in rendered.lines.iter().zip(&lines) {
        assert_eq!(i64::from(line.width_26_6), *pen);
    }
}
