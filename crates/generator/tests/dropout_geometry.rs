//! Geometric tests for outline-driven mono dropout restoration.
//!
//! Sources: Hersch 1993 section 7 (interior null spans, pixel nearest the
//! contour-intersection midpoint, horizontal and vertical scans); OpenType
//! SCANTYPE rules 5/6 (on/off-transition pair between adjacent pixel centers,
//! midpoint selection, stub rule); OpenType Fundamentals (nonzero-winding
//! interior, dropout and stub definitions). Project hypothesis under test: the
//! core adapts those scan-converter rules to coverage-thresholded output by
//! rescuing subpixel interior spans with no delivered ink, keeping raw
//! coverage and ordinary threshold conversion unchanged.

use font_generator::{
    dropout,
    probe::{self, FittedCommand, RasterOutput},
    reference::{reference, ReferenceRequest, PROFILE_MONO_1BIT},
    Config, Hinting,
};
use std::{fs, path::Path};

fn mono() -> Config {
    Config {
        output_bits: 1,
        mono_threshold: 128,
        characters: "a".into(),
        ..Config::default()
    }
}

fn gray() -> Config {
    Config {
        output_bits: 3,
        characters: "a".into(),
        ..Config::default()
    }
}

fn rect(x0: f32, y0: f32, x1: f32, y1: f32) -> Vec<FittedCommand> {
    vec![
        FittedCommand::MoveTo(x0, y0),
        FittedCommand::LineTo(x1, y0),
        FittedCommand::LineTo(x1, y1),
        FittedCommand::LineTo(x0, y1),
        FittedCommand::Close,
    ]
}

fn rect_reversed(x0: f32, y0: f32, x1: f32, y1: f32) -> Vec<FittedCommand> {
    vec![
        FittedCommand::MoveTo(x0, y0),
        FittedCommand::LineTo(x0, y1),
        FittedCommand::LineTo(x1, y1),
        FittedCommand::LineTo(x1, y0),
        FittedCommand::Close,
    ]
}

fn ink_pixels(output: &RasterOutput) -> usize {
    output.pixels.iter().map(|pixel| *pixel as usize).sum()
}

fn at(output: &RasterOutput, i: i32, j: i32) -> u8 {
    assert!(i >= 0 && j >= 0);
    output.pixels[j as usize * output.width as usize + i as usize]
}

fn components(output: &RasterOutput) -> usize {
    let width = output.width as usize;
    let mut visited = vec![false; output.pixels.len()];
    let mut count = 0;
    for start in 0..output.pixels.len() {
        if visited[start] || output.pixels[start] == 0 {
            continue;
        }
        count += 1;
        visited[start] = true;
        let mut queue = vec![start];
        let mut next = 0;
        while next < queue.len() {
            let p = queue[next];
            next += 1;
            for dy in -1..=1isize {
                for dx in -1..=1isize {
                    let x = (p % width) as isize + dx;
                    let y = (p / width) as isize + dy;
                    if x < 0 || y < 0 || x >= width as isize {
                        continue;
                    }
                    let neighbor = y as usize * width + x as usize;
                    if neighbor < visited.len()
                        && !visited[neighbor]
                        && output.pixels[neighbor] != 0
                    {
                        visited[neighbor] = true;
                        queue.push(neighbor);
                    }
                }
            }
        }
    }
    count
}

// Ordinary conversion is unchanged, rescue only adds ink, and every rescued
// pixel is corroborated by positive raw coverage: the geometric invariant
// behind the coverage-thresholding project hypothesis.
fn assert_rescue_contract(base: &RasterOutput, fixed: &RasterOutput) {
    assert_eq!(fixed.left, base.left);
    assert_eq!(fixed.top, base.top);
    assert_eq!(fixed.width, base.width);
    assert_eq!(fixed.height, base.height);
    assert_eq!(fixed.coverage, base.coverage);
    for (k, (delivered, rescued)) in base.pixels.iter().zip(&fixed.pixels).enumerate() {
        assert!(
            rescued >= delivered,
            "dropout must only add ink, pixel {k} went {delivered} -> {rescued}"
        );
        if rescued > delivered {
            assert!(
                base.coverage[k] > 0,
                "rescued pixel {k} has no raw coverage corroboration"
            );
        }
    }
}

#[test]
fn thin_vertical_stem_is_continuous() {
    // Interior span 0.375 px wide: Hersch section 7 dropout, SCANTYPE rule 5
    // midpoint selects the span's own pixel column in every row.
    let commands = rect(2.0, 0.0, 2.375, 8.0);
    let base = probe::rasterize(&commands, &mono()).unwrap();
    assert!(base.pixels.iter().all(|pixel| *pixel == 0));
    let fixed = dropout::rasterize(&commands, &mono()).unwrap();
    assert_rescue_contract(&base, &fixed);
    assert_eq!((fixed.width, fixed.height), (1, 8));
    assert!(fixed.pixels.iter().all(|pixel| *pixel == 1));
    assert_eq!(
        dropout::rasterize(&commands, &mono()).unwrap().pixels,
        fixed.pixels
    );
}

#[test]
fn thin_stem_family_survives_translation_reflection_and_quarter_turn() {
    // Same thin span under integer translation, reflection and a 90-degree
    // turn. Asymmetric subpixel placement keeps every midpoint away from an
    // exact equidistance tie, so expectations do not depend on tie-breaking.
    let upright = rect(2.0, 0.0, 2.375, 8.0);
    let shifted = rect(5.0, 2.0, 5.375, 10.0);
    let mirrored = rect(5.625, 0.0, 6.0, 8.0);
    for commands in [&upright, &shifted, &mirrored] {
        let base = probe::rasterize(commands, &mono()).unwrap();
        let fixed = dropout::rasterize(commands, &mono()).unwrap();
        assert_rescue_contract(&base, &fixed);
        assert_eq!((fixed.width, fixed.height), (1, 8));
        assert_eq!(ink_pixels(&fixed), 8);
    }
    let turned = rect(0.0, 5.0, 8.0, 5.375);
    let base = probe::rasterize(&turned, &mono()).unwrap();
    let fixed = dropout::rasterize(&turned, &mono()).unwrap();
    assert_rescue_contract(&base, &fixed);
    assert_eq!((fixed.width, fixed.height), (8, 1));
    assert_eq!(ink_pixels(&fixed), 8);
}

#[test]
fn quadratic_shoulder_band_stays_continuous() {
    // Thin curved shoulder: every scan column keeps ink and the band is one
    // connected stroke, exercising exact quadratic contour intersections.
    let commands = vec![
        FittedCommand::MoveTo(0.0, 1.0),
        FittedCommand::QuadTo(4.0, 5.0, 8.0, 1.0),
        FittedCommand::LineTo(8.0, 0.6),
        FittedCommand::QuadTo(4.0, 4.6, 0.0, 0.6),
        FittedCommand::Close,
    ];
    let base = probe::rasterize(&commands, &mono()).unwrap();
    let fixed = dropout::rasterize(&commands, &mono()).unwrap();
    assert_rescue_contract(&base, &fixed);
    assert!(ink_pixels(&fixed) > 0);
    for i in 0..fixed.width as i32 {
        let column_has_coverage = (0..fixed.height as i32)
            .any(|j| base.coverage[j as usize * fixed.width as usize + i as usize] > 0);
        if column_has_coverage {
            assert!(
                (0..fixed.height as i32).any(|j| at(&fixed, i, j) != 0),
                "band column {i} lost continuity"
            );
        }
    }
    assert_eq!(components(&fixed), 1);
}

#[test]
fn cubic_shoulder_band_stays_continuous() {
    // Same continuity contract for a cubic band, exercising exact cubic
    // contour intersections without flattening approximations.
    let commands = vec![
        FittedCommand::MoveTo(0.0, 1.0),
        FittedCommand::CurveTo(2.5, 5.0, 5.5, 5.0, 8.0, 1.0),
        FittedCommand::LineTo(8.0, 0.6),
        FittedCommand::CurveTo(5.5, 4.6, 2.5, 4.6, 0.0, 0.6),
        FittedCommand::Close,
    ];
    let base = probe::rasterize(&commands, &mono()).unwrap();
    let fixed = dropout::rasterize(&commands, &mono()).unwrap();
    assert_rescue_contract(&base, &fixed);
    assert!(ink_pixels(&fixed) > 0);
    for i in 0..fixed.width as i32 {
        let column_has_coverage = (0..fixed.height as i32)
            .any(|j| base.coverage[j as usize * fixed.width as usize + i as usize] > 0);
        if column_has_coverage {
            assert!(
                (0..fixed.height as i32).any(|j| at(&fixed, i, j) != 0),
                "band column {i} lost continuity"
            );
        }
    }
}

#[test]
fn shared_scanline_edge_has_single_ownership() {
    // Two contours sharing an edge that lies exactly on a pixel-center
    // scanline must render like their union: half-open branches own the
    // shared vertices once, so no span opens or closes there.
    let single = rect(1.0, 0.0, 3.0, 4.5);
    let mut stacked = rect(1.0, 0.0, 3.0, 2.5);
    stacked.extend(rect(1.0, 2.5, 3.0, 4.5));
    let base = probe::rasterize(&single, &mono()).unwrap();
    for commands in [&single, &stacked] {
        let fixed = dropout::rasterize(commands, &mono()).unwrap();
        assert_eq!(fixed.pixels, base.pixels);
    }
}

#[test]
fn tangent_apex_touch_cancels_on_its_scanline() {
    // Apex touching a row-center scanline with both neighbors on one side
    // contributes cancelling transitions, never an interior span there: the
    // touch row keeps its ordinary conversion exactly, while other rows may
    // gain legitimate thin-span rescues elsewhere.
    let commands = vec![
        FittedCommand::MoveTo(0.0, 0.0),
        FittedCommand::LineTo(4.0, 0.0),
        FittedCommand::LineTo(2.0, 1.5),
        FittedCommand::Close,
    ];
    let base = probe::rasterize(&commands, &mono()).unwrap();
    let fixed = dropout::rasterize(&commands, &mono()).unwrap();
    assert_rescue_contract(&base, &fixed);
    assert_eq!(base.top, -2);
    for i in 0..base.width as i32 {
        assert_eq!(at(&fixed, i, 0), at(&base, i, 0));
    }
}

#[test]
fn opposite_contours_cancel_while_overlap_stays_interior() {
    // Nonzero winding (OpenType Fundamentals): coincident reversed contours
    // have no interior and rescue nothing; coincident same-winding contours
    // stay interior, and their thick spans are unchanged.
    let forward = rect(1.0, 1.0, 4.0, 4.0);
    let backward = rect_reversed(1.0, 1.0, 4.0, 4.0);
    let mut cancelled = forward.clone();
    cancelled.extend(backward);
    let fixed = dropout::rasterize(&cancelled, &mono()).unwrap();
    assert!(fixed.pixels.iter().all(|pixel| *pixel == 0));
    let mut doubled = forward.clone();
    doubled.extend(forward);
    let base = probe::rasterize(&doubled, &mono()).unwrap();
    assert!(ink_pixels(&base) > 0);
    let fixed = dropout::rasterize(&doubled, &mono()).unwrap();
    assert_eq!(fixed.pixels, base.pixels);
}

#[test]
fn open_counter_and_separated_strokes_are_not_bridged() {
    // Geometry invariant: only thin interior spans are rescued, never real
    // white gaps or counters, which present exterior (exit/entry) crossings.
    let mut pair = rect(0.0, 0.0, 1.5, 6.0);
    pair.extend(rect(2.0, 0.0, 3.5, 6.0));
    let base = probe::rasterize(&pair, &mono()).unwrap();
    let fixed = dropout::rasterize(&pair, &mono()).unwrap();
    assert_rescue_contract(&base, &fixed);
    let gap = 1 - base.left;
    for j in 0..base.height as i32 {
        assert_eq!(at(&fixed, gap, j), at(&base, gap, j));
    }
    let mut ring = rect(0.0, 0.0, 6.0, 6.0);
    ring.extend(rect_reversed(2.0, 2.0, 4.0, 4.0));
    let base = probe::rasterize(&ring, &mono()).unwrap();
    assert!(ink_pixels(&base) > 0);
    let fixed = dropout::rasterize(&ring, &mono()).unwrap();
    assert_eq!(fixed.pixels, base.pixels);
}

#[test]
fn dead_end_stub_tip_is_included_without_extension() {
    // Milestone stub policy follows Hersch section 7 with SCANTYPE smart
    // including stubs: the tip column's in-span center is rescued, while no
    // pixel past the outline end is invented.
    let commands = rect(0.0, 3.0, 4.0, 3.375);
    let base = probe::rasterize(&commands, &mono()).unwrap();
    assert!(base.pixels.iter().all(|pixel| *pixel == 0));
    let fixed = dropout::rasterize(&commands, &mono()).unwrap();
    assert_rescue_contract(&base, &fixed);
    assert_eq!((fixed.width, fixed.height), (4, 1));
    assert!(fixed.pixels.iter().all(|pixel| *pixel == 1));
}

#[cfg(feature = "candidate")]
#[test]
fn candidate_excludes_terminal_caps_under_curve_subdivision_and_grid_transforms() {
    // SCANTYPE rule 6 / FreeType ftraster.c at
    // 57617782464411201ce7bbc93b086c1b4d7d84a5: a contour cap closing before
    // the next scan line is a stub. This shallow diagonal terminal has no
    // pixel center in its cap, while the stroke below is already visible.
    let points = [(0.25, 2.25), (1.75, 2.25), (4.75, -2.25), (3.25, -2.25)];
    for degree in [1, 2, 3] {
        for (dx, dy, reflect, turn) in [
            (0.0, 0.0, false, false),
            (-5.0, 3.0, false, false),
            (0.0, 0.0, true, false),
            (0.0, 0.0, false, true),
        ] {
            let map = |(x, y): (f32, f32)| {
                let x = if reflect { -x } else { x };
                let (x, y) = if turn { (-y, x) } else { (x, y) };
                (x + dx, y + dy)
            };
            let p: Vec<_> = points.into_iter().map(map).collect();
            let mut commands = vec![FittedCommand::MoveTo(p[0].0, p[0].1)];
            for i in 0..4 {
                let (a, b) = (p[i], p[(i + 1) % 4]);
                commands.push(match degree {
                    1 => FittedCommand::LineTo(b.0, b.1),
                    2 => FittedCommand::QuadTo((a.0 + b.0) / 2.0, (a.1 + b.1) / 2.0, b.0, b.1),
                    _ => FittedCommand::CurveTo(
                        (2.0 * a.0 + b.0) / 3.0,
                        (2.0 * a.1 + b.1) / 3.0,
                        (a.0 + 2.0 * b.0) / 3.0,
                        (a.1 + 2.0 * b.1) / 3.0,
                        b.0,
                        b.1,
                    ),
                });
            }
            commands.push(FittedCommand::Close);
            let candidate = font_generator::overlap::rasterize(&commands, &mono()).unwrap();
            let legacy = dropout::rasterize(&commands, &mono()).unwrap();
            let (x, y) = map((0.5, 2.5));
            let index = ((-y).floor() as i32 - candidate.top) as usize * candidate.width as usize
                + (x.floor() as i32 - candidate.left) as usize;
            assert!(candidate.coverage[index] < 128, "cap is below threshold");
            assert_eq!(candidate.pixels[index], 0, "terminal cap excluded");
            assert_eq!(legacy.pixels[index], 1, "legacy still includes stubs");
            assert!(candidate.pixels.iter().any(|&p| p != 0), "stroke retained");
            for (&coverage, &pixel) in candidate.coverage.iter().zip(&candidate.pixels) {
                if coverage >= 128 {
                    assert_eq!(pixel, 1, "ordinary ink is never removed");
                }
            }
        }
    }
}

#[cfg(feature = "candidate")]
#[test]
fn candidate_retains_interior_dropouts_and_cancels_opposite_winding() {
    // Rule 6 permits rescue where both borders continue to adjacent scan
    // lines. It must not manufacture a connection across nonzero-fill holes.
    let stem = rect(0.4, 0.0, 0.6, 6.0);
    let candidate = font_generator::overlap::rasterize(&stem, &mono()).unwrap();
    assert!(candidate.coverage.iter().all(|&c| c < 128));
    for y in [2, 3] {
        assert_eq!(at(&candidate, 0, y), 1, "interior stem survives");
    }
    let mut cancelled = stem;
    cancelled.extend(rect_reversed(0.4, 0.0, 0.6, 6.0));
    let candidate = font_generator::overlap::rasterize(&cancelled, &mono()).unwrap();
    assert!(candidate.pixels.iter().all(|&p| p == 0));
}

#[cfg(feature = "candidate")]
#[test]
fn candidate_preserves_curved_interior_stroke_continuity() {
    // Rule 6 excludes caps rather than curved interior bands. These real
    // quadratic/cubic extrema must be examined, not just curve endpoints.
    for upper in [
        FittedCommand::QuadTo(4.0, 5.0, 8.0, 1.0),
        FittedCommand::CurveTo(2.5, 5.0, 5.5, 5.0, 8.0, 1.0),
    ] {
        let lower = match upper {
            FittedCommand::QuadTo(..) => FittedCommand::QuadTo(4.0, 4.6, 0.0, 0.6),
            _ => FittedCommand::CurveTo(5.5, 4.6, 2.5, 4.6, 0.0, 0.6),
        };
        let commands = vec![
            FittedCommand::MoveTo(0.0, 1.0),
            upper,
            FittedCommand::LineTo(8.0, 0.6),
            lower,
            FittedCommand::Close,
        ];
        let fixed = font_generator::overlap::rasterize(&commands, &mono()).unwrap();
        assert_eq!(components(&fixed), 1, "curved band remains one stroke");
        for x in 1..fixed.width as i32 - 1 {
            assert!(
                (0..fixed.height as i32).any(|y| at(&fixed, x, y) != 0),
                "interior band column {x} lost continuity"
            );
        }
    }
}

#[cfg(feature = "candidate")]
#[test]
fn candidate_preserves_thin_counter_walls_without_filling_the_counter() {
    // SCANTYPE rule 6 requires a cap joining the paired borders. A wall
    // between separate outer/hole contours has no such cap to exclude.
    let mut ring = rect(0.0, 0.0, 6.0, 6.0);
    ring.extend(rect_reversed(0.375, 0.375, 5.625, 5.625));
    let fixed = font_generator::overlap::rasterize(&ring, &mono()).unwrap();
    assert_eq!(components(&fixed), 1, "thin ring remains connected");
    for i in 0..6 {
        assert_eq!(at(&fixed, i, 0), 1);
        assert_eq!(at(&fixed, i, 5), 1);
        assert_eq!(at(&fixed, 0, i), 1);
        assert_eq!(at(&fixed, 5, i), 1);
    }
    for y in 1..5 {
        for x in 1..5 {
            assert_eq!(at(&fixed, x, y), 0, "counter remains open");
        }
    }
}

#[cfg(feature = "candidate")]
#[test]
fn candidate_leaves_subpixel_detached_stubs_to_ordinary_coverage() {
    // Both sides of this detached contour close before another scan line.
    // Rule 6 excludes its rescues in both directions. This explicitly
    // records the small-mark limitation, not optical acceptance of erasure.
    let mark = rect(0.375, 0.375, 0.625, 0.625);
    let fixed = font_generator::overlap::rasterize(&mark, &mono()).unwrap();
    assert!(fixed.coverage.iter().all(|&c| c < 128));
    assert!(fixed.pixels.iter().all(|&p| p == 0));
    let legacy = dropout::rasterize(&mark, &mono()).unwrap();
    assert!(legacy.pixels.iter().any(|&p| p != 0));
}

#[test]
fn empty_and_degenerate_outlines_invent_no_ink() {
    let empty: Vec<FittedCommand> = vec![];
    let fixed = dropout::rasterize(&empty, &mono()).unwrap();
    assert!(fixed.pixels.is_empty());
    let hairline = vec![
        FittedCommand::MoveTo(1.0, 1.0),
        FittedCommand::LineTo(3.0, 3.0),
        FittedCommand::LineTo(1.0, 1.0),
        FittedCommand::Close,
    ];
    let fixed = dropout::rasterize(&hairline, &mono()).unwrap();
    assert!(fixed.pixels.iter().all(|pixel| *pixel == 0));
    // An unclosed contour covering real pixels is rejected rather than wound
    // inconsistently. A lone point has an empty bitmap and returns Ok(empty).
    let open = vec![
        FittedCommand::MoveTo(0.0, 0.0),
        FittedCommand::LineTo(4.0, 0.0),
        FittedCommand::LineTo(4.0, 4.0),
    ];
    assert!(dropout::rasterize(&open, &mono()).is_err());
}

#[test]
fn gray_profile_keeps_upstream_identity() {
    // Dropout is a mono-path adaptation; gray keeps the coverage rasterizer.
    let commands = rect(2.0, 0.0, 2.375, 8.0);
    let base = probe::rasterize(&commands, &gray()).unwrap();
    let fixed = dropout::rasterize(&commands, &gray()).unwrap();
    assert_eq!(fixed.coverage, base.coverage);
    assert_eq!(fixed.pixels, base.pixels);
}

fn roboto() -> Vec<u8> {
    fs::read(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../fonts")
            .join("Roboto.ttf"),
    )
    .unwrap()
}

fn fitted_a(bytes: &[u8], weight: f32) -> Vec<FittedCommand> {
    let mut settings = Config {
        size_px: 14.0,
        characters: "a".into(),
        hinting: Hinting::Auto,
        output_bits: 1,
        ..Config::default()
    };
    settings.axes.insert("wght".into(), weight);
    settings.axes.insert("wdth".into(), 100.0);
    let request = ReferenceRequest {
        profile: PROFILE_MONO_1BIT.into(),
        extensions: "none".into(),
        settings,
    };
    let report = reference(bytes, &request).unwrap();
    assert_eq!(report.records.len(), 1);
    report.records[0].fitted_commands.clone()
}

#[test]
fn roboto_light_shoulder_attachment_is_restored() {
    // Witness from docs/revisions/001/02-light-continuity.md: at 14 px the
    // source-connected shoulder strip loses its attachment pixel (weight 200:
    // glyph x4,y-5 coverage 127 against threshold 128; weight 100: shoulder
    // coverages near 103-106). Independent FreeType evidence for the same
    // fitted outlines is one connected component under smart-with-stubs; no
    // whole-glyph pixel parity is asserted because FreeType center-fill
    // differs from the coverage baseline by design.
    let bytes = roboto();
    let cases: &[(f32, &[i32])] = &[(200.0, &[2, 3, 4]), (100.0, &[3, 4])];
    for (weight, shoulder) in cases {
        let commands = fitted_a(&bytes, *weight);
        let base = probe::rasterize(&commands, &mono()).unwrap();
        let fixed = dropout::rasterize(&commands, &mono()).unwrap();
        assert_rescue_contract(&base, &fixed);
        let j = -5 - base.top;
        assert!(j >= 0 && j < base.height as i32);
        for x in *shoulder {
            let i = x - base.left;
            assert!(i >= 0 && i < base.width as i32);
            let k = j as usize * base.width as usize + i as usize;
            if base.pixels[k] == 0 {
                assert!(
                    base.coverage[k] > 0 && base.coverage[k] < 128,
                    "weight {weight} x{x}: expected a threshold-lost span pixel"
                );
            }
            assert_eq!(
                at(&fixed, i, j),
                1,
                "weight {weight} x{x}: shoulder not restored"
            );
        }
    }
}
