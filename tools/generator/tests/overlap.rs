#![cfg(feature = "candidate")]

//! Bounded 4x overlap mitigation contracts: FreeType-style per-sample
//! reduction, native grid preservation, tiled-vs-full agreement (including
//! tile boundaries, curves, holes, crossings and opposite winding),
//! integer-translation and negative-origin behavior, original coordinate
//! limits, threshold-once/dropout-once ordering, and the reported Roboto A
//! 14 px coverage pair. Mechanical checks only; optical acceptance of the
//! two pending findings (Source Sans 3 `!` 14 px dot/body join, `[` 16 px
//! half cells 127 -> 128) remains pending assessment and is preserved here
//! as rounding evidence, never as a fix claim.

use font_generator::{
    candidate,
    probe::{self, FittedCommand, RasterOutput},
    reference::{RasterPolicy, ReferenceRequest, PROFILE_MONO_1BIT},
    stem_fitting::EXTENSIONS_FONT_HINTS_FIRST,
    Config,
};
use std::{fs, path::Path};

fn mono() -> Config {
    Config {
        size_px: 16.0,
        characters: "A".into(),
        ..Config::default()
    }
}

fn rect(x: f32, y: f32, w: f32, h: f32) -> Vec<FittedCommand> {
    vec![
        FittedCommand::MoveTo(x, y),
        FittedCommand::LineTo(x + w, y),
        FittedCommand::LineTo(x + w, y + h),
        FittedCommand::LineTo(x, y + h),
        FittedCommand::Close,
    ]
}

fn rect_reversed(x: f32, y: f32, w: f32, h: f32) -> Vec<FittedCommand> {
    vec![
        FittedCommand::MoveTo(x, y),
        FittedCommand::LineTo(x, y + h),
        FittedCommand::LineTo(x + w, y + h),
        FittedCommand::LineTo(x + w, y),
        FittedCommand::Close,
    ]
}

fn placement(raster: &RasterOutput) -> (i32, i32, u32, u32) {
    (raster.left, raster.top, raster.width, raster.height)
}

/// Independent full-high Zeno oracle for tractable paths: one 4x render
/// with the same global native-grid anchor as the engine, transcribed
/// reduction, no tiling. Panics on intractable sizes to keep the oracle
/// bounded; the engine itself never allocates the full high image.
fn full_high_oracle(commands: &[FittedCommand], config: &Config) -> RasterOutput {
    let native = probe::rasterize(commands, config).unwrap();
    assert!(native.width > 0 && native.height > 0);
    let hr_w = native.width.checked_mul(4).unwrap();
    let hr_h = native.height.checked_mul(4).unwrap();
    let len = (hr_w as usize)
        .checked_mul(hr_h as usize)
        .expect("oracle tractability bound");
    assert!(len <= 16_777_216, "oracle only for tractable paths");
    let zeno = probe::to_zeno(commands);
    let mut buf = vec![0u8; len];
    let mut mask = zeno::Mask::new(zeno.as_slice());
    mask.format(zeno::Format::Alpha);
    mask.transform(Some(zeno::Transform::scale(4.0, 4.0)));
    mask.size(hr_w, hr_h);
    mask.render_offset(zeno::Vector::new(
        -4.0 * f64::from(native.left) as f32,
        -4.0 * f64::from(native.top) as f32,
    ));
    mask.render_into(&mut buf, None);
    let mut coverage = Vec::with_capacity((native.width * native.height) as usize);
    for ny in 0..native.height {
        for nx in 0..native.width {
            let mut acc = 0u32;
            for dy in 0..4 {
                for dx in 0..4 {
                    let v = buf[((ny * 4 + dy) * hr_w + nx * 4 + dx) as usize];
                    acc += (u32::from(v) + 8) / 16;
                }
            }
            coverage.push(acc.min(255) as u8);
        }
    }
    let pixels = coverage
        .iter()
        .map(|&v| u8::from(v >= config.mono_threshold))
        .collect();
    RasterOutput {
        pixels,
        coverage,
        left: native.left,
        top: native.top,
        width: native.width,
        height: native.height,
    }
}

fn assert_matches_oracle(commands: &[FittedCommand], config: &Config, context: &str) {
    let engine = font_generator::overlap::rasterize(commands, config).unwrap();
    let oracle = full_high_oracle(commands, config);
    assert_eq!(
        placement(&engine),
        placement(&oracle),
        "{context}: placement"
    );
    assert_eq!(engine.coverage, oracle.coverage, "{context}: coverage");
    // Pixel equality holds where dropout stays silent; coverage equality
    // above is the dropout-independent contract.
    let thresholded: Vec<u8> = engine
        .coverage
        .iter()
        .map(|&v| u8::from(v >= config.mono_threshold))
        .collect();
    assert_eq!(engine.pixels, thresholded, "{context}: no dropout expected");
}

#[test]
fn tiled_reduction_matches_full_high_for_plain_rect() {
    let config = mono();
    assert_matches_oracle(&rect(0.25, 0.5, 5.0, 4.0), &config, "plain rect");
}

#[test]
fn tiled_reduction_matches_full_high_for_curves_across_tiles() {
    // ~300 px wide so column tiling engages; quadratic and cubic contours
    // cross the tile boundary.
    let config = mono();
    let mut commands = vec![
        FittedCommand::MoveTo(0.5, 0.5),
        FittedCommand::LineTo(300.5, 0.5),
        FittedCommand::QuadTo(302.0, 6.0, 296.0, 8.5),
        FittedCommand::CurveTo(200.0, 14.0, 100.0, 2.0, 0.5, 9.5),
        FittedCommand::Close,
    ];
    assert_matches_oracle(&commands, &config, "curved tile crosser");
    // Negative origin with the same shape exercises the global integer
    // origin path through tiling.
    for command in &mut commands {
        match command {
            FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => {
                *x -= 40.0;
                *y += 30.0;
            }
            FittedCommand::QuadTo(x1, y1, x, y) => {
                *x1 -= 40.0;
                *y1 += 30.0;
                *x -= 40.0;
                *y += 30.0;
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                *x1 -= 40.0;
                *y1 += 30.0;
                *x2 -= 40.0;
                *y2 += 30.0;
                *x -= 40.0;
                *y += 30.0;
            }
            FittedCommand::Close => {}
        }
    }
    let shifted = font_generator::overlap::rasterize(&commands, &config).unwrap();
    let oracle = full_high_oracle(&commands, &config);
    assert_eq!(placement(&shifted), placement(&oracle), "negative origin");
    assert_eq!(shifted.coverage, oracle.coverage, "negative origin");
    assert!(shifted.left < 0 && shifted.top < 0);
}

#[test]
fn tiled_reduction_matches_full_high_for_large_glyph() {
    // Natively valid 600x600 (360k px) whose full 2400x2400 high image must
    // never be allocated by the engine; the oracle renders it directly.
    let config = mono();
    assert_matches_oracle(&rect(0.5, 0.5, 600.0, 600.0), &config, "600x600");
}

#[test]
fn curved_outline_and_hole_keep_winding_across_row_and_column_tiles() {
    // A curved outer boundary spanning both tile axes, with a reversed
    // interior contour crossing the same boundaries. Tiling must preserve
    // nonzero winding, including contributions outside an individual tile.
    let mut commands = vec![
        FittedCommand::MoveTo(-20.5, -20.5),
        FittedCommand::LineTo(300.5, -20.5),
        FittedCommand::QuadTo(302.0, 600.0, 296.0, 640.5),
        FittedCommand::CurveTo(200.0, 670.0, 100.0, 200.0, -20.5, 641.5),
        FittedCommand::Close,
    ];
    commands.extend(rect_reversed(20.25, 50.5, 250.0, 250.0));
    let config = mono();
    let tiled = font_generator::overlap::rasterize(&commands, &config).unwrap();
    let full = full_high_oracle(&commands, &config);
    assert_eq!(placement(&tiled), placement(&full));
    assert_eq!(tiled.coverage, full.coverage);
}

#[test]
fn empty_degenerate_and_invalid_coordinates_keep_native_bounds_contract() {
    let config = mono();
    for commands in [vec![], rect(0.0, 0.0, 0.0, 4.0)] {
        let plain = probe::rasterize(&commands, &config).unwrap();
        let overlap = font_generator::overlap::rasterize(&commands, &config).unwrap();
        assert_eq!(placement(&overlap), placement(&plain));
        assert_eq!(overlap.coverage, plain.coverage);
        assert_eq!(overlap.pixels, plain.pixels);
    }
    for bad in [f32::NAN, f32::INFINITY, 32769.0, -32769.0] {
        let commands = rect(bad, 0.0, 1.0, 1.0);
        assert!(font_generator::overlap::rasterize(&commands, &config).is_err());
    }
}

#[test]
fn tiled_reduction_matches_full_high_for_hole_and_crossing() {
    let config = mono();
    // Ring with an opposite-winding hole: the enclosed center stays empty.
    let mut ring = rect(0.0, 0.0, 6.0, 6.0);
    ring.extend(rect_reversed(2.0, 2.0, 2.0, 2.0));
    let engine = font_generator::overlap::rasterize(&ring, &config).unwrap();
    let oracle = full_high_oracle(&ring, &config);
    assert_eq!(engine.coverage, oracle.coverage, "hole coverage");
    let center = |x: u32, y: u32| (y * engine.width + x) as usize;
    assert_eq!(engine.coverage[center(3, 3)], 0, "hole stays empty");
    assert!(engine.coverage[center(1, 3)] >= 128, "rim stays inked");
    // Integer-aligned crossing bars have saturated interior pixels in both
    // rasters. Their overlap need not change coverage; check fill and grid.
    let mut cross = rect(0.0, 1.0, 6.0, 2.0);
    cross.extend(rect(2.0, 0.0, 2.0, 5.0));
    let crossed = font_generator::overlap::rasterize(&cross, &config).unwrap();
    let crossed_oracle = full_high_oracle(&cross, &config);
    assert_eq!(crossed.coverage, crossed_oracle.coverage, "crossing");
    let plain = probe::rasterize(&cross, &config).unwrap();
    assert_eq!(placement(&crossed), placement(&plain), "crossing grid");
}

#[test]
fn opposite_winding_strips_recover_coverage_before_dropout() {
    // Two disjoint strips sharing native pixels with opposite winding:
    // the signed-area raster cancels to ~0 while 4x separation recovers
    // coverage before dropout runs.
    let config = mono();
    // Binary fractions make the two opposite signed areas exactly equal;
    // at 4x each strip occupies one full high-resolution column.
    let mut strips = rect(0.125, 0.0, 0.25, 3.0);
    strips.extend(rect_reversed(0.625, 0.0, 0.25, 3.0));
    let engine = font_generator::overlap::rasterize(&strips, &config).unwrap();
    let plain = probe::rasterize(&strips, &config).unwrap();
    assert_eq!(placement(&engine), placement(&plain), "strip grid");
    let plain_sum: u32 = plain.coverage.iter().map(|&v| u32::from(v)).sum();
    let engine_sum: u32 = engine.coverage.iter().map(|&v| u32::from(v)).sum();
    assert_eq!(plain_sum, 0, "signed areas cancel in shared pixels");
    assert!(engine_sum > 0, "4x separation recovers coverage");
    assert_eq!(engine.coverage, vec![128; 3], "half-filled native pixels");
    assert!(engine.pixels.iter().any(|&p| p == 1), "strips deliver ink");
    assert_eq!(engine.coverage, full_high_oracle(&strips, &config).coverage);
}

#[test]
fn integer_translation_preserves_pixels_with_shifted_placement() {
    let config = mono();
    let base = rect(0.25, 0.5, 3.0, 4.0);
    let moved: Vec<FittedCommand> = base
        .iter()
        .map(|command| match *command {
            FittedCommand::MoveTo(x, y) => FittedCommand::MoveTo(x + 7.0, y - 3.0),
            FittedCommand::LineTo(x, y) => FittedCommand::LineTo(x + 7.0, y - 3.0),
            FittedCommand::QuadTo(x1, y1, x, y) => {
                FittedCommand::QuadTo(x1 + 7.0, y1 - 3.0, x + 7.0, y - 3.0)
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                FittedCommand::CurveTo(x1 + 7.0, y1 - 3.0, x2 + 7.0, y2 - 3.0, x + 7.0, y - 3.0)
            }
            FittedCommand::Close => FittedCommand::Close,
        })
        .collect();
    let a = font_generator::overlap::rasterize(&base, &config).unwrap();
    let b = font_generator::overlap::rasterize(&moved, &config).unwrap();
    assert_eq!(a.pixels, b.pixels, "integer shift keeps pixels");
    assert_eq!(a.coverage, b.coverage, "integer shift keeps coverage");
    // Fitted coordinates are Y-up; bitmap placement is Y-down.
    assert_eq!((b.left, b.top), (a.left + 7, a.top + 3), "placement shifts");
}

#[test]
fn original_limits_are_not_tightened_by_scaling() {
    let config = mono();
    // Small rectangle far out at X 8300: natively valid, while its scaled
    // coordinate 33200 exceeds the point bound the engine must not apply
    // to scaled geometry.
    let far = rect(8300.25, 0.5, 2.0, 3.0);
    let engine = font_generator::overlap::rasterize(&far, &config).unwrap();
    let native = probe::rasterize(&far, &config).unwrap();
    assert_eq!(placement(&engine), placement(&native), "far grid");
    assert_eq!(engine.coverage, full_high_oracle(&far, &config).coverage);
    assert!(engine.pixels.iter().any(|&p| p == 1));
    // Oversized native paths still fail exactly as before.
    let huge = rect(0.0, 0.0, 5000.0, 5000.0);
    assert!(probe::rasterize(&huge, &config).is_err());
    assert!(font_generator::overlap::rasterize(&huge, &config).is_err());
    // Non-mono use is an explicit error, never a silent fallback.
    let mut gray = mono();
    gray.output_bits = 3;
    assert!(font_generator::overlap::rasterize(&rect(0.0, 0.0, 2.0, 2.0), &gray).is_err());
}

#[test]
fn duplicate_contours_still_change_sampled_coverage() {
    // Confirmed residual limitation: duplicating a same-winding contour
    // preserves its nonzero filled set but still changes 4x sampled
    // coverage. Finite oversampling mitigates double counting rather than
    // removing it, so exact-union invariance must not be asserted.
    let config = mono();
    // The research counterexample has edges inside high-resolution cells;
    // edges exactly on the 4x grid can saturate identically in both paths.
    let single = rect(0.2, 0.3, 1.2, 2.4);
    let mut doubled = single.clone();
    doubled.extend(single.clone());
    let a = font_generator::overlap::rasterize(&single, &config).unwrap();
    let b = font_generator::overlap::rasterize(&doubled, &config).unwrap();
    assert_eq!(placement(&a), placement(&b), "duplicate grid");
    let sum = |raster: &RasterOutput| raster.coverage.iter().map(|&v| u32::from(v)).sum::<u32>();
    assert!(sum(&b) > sum(&a), "duplicate still double-counts");
}

#[test]
fn threshold_once_then_original_dropout_once_with_raw_coverage() {
    // A 0.2 px stem never reaches threshold on coverage alone, so any
    // delivered ink proves the original-geometry dropout scan ran after
    // thresholding while coverage stayed raw.
    let config = mono();
    let stem = rect(0.4, 0.0, 0.2, 3.0);
    let before = stem.clone();
    let engine = font_generator::overlap::rasterize(&stem, &config).unwrap();
    assert_eq!(stem, before, "source commands never mutated");
    assert!(
        engine.coverage.iter().all(|&v| v < 128),
        "no threshold ink expected"
    );
    assert!(
        engine.pixels.iter().any(|&p| p == 1),
        "dropout rescues stem"
    );
    assert_eq!(engine.coverage, full_high_oracle(&stem, &config).coverage);
}

#[test]
fn candidate_mono_keeps_native_grid_and_raw_coverage() {
    // A real-font outline checks candidate scanner routing, independently of
    // which upstream engine produced that outline.
    let bytes = fs::read(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../fonts")
            .join("Roboto.ttf"),
    )
    .unwrap();
    let mut settings = Config {
        size_px: 14.0,
        characters: "A".into(),
        hinting: font_generator::Hinting::Auto,
        output_bits: 1,
        ..Config::default()
    };
    settings.axes.insert("wght".into(), 400.0);
    settings.axes.insert("wdth".into(), 100.0);
    let request = ReferenceRequest {
        profile: PROFILE_MONO_1BIT.into(),
        extensions: EXTENSIONS_FONT_HINTS_FIRST.into(),
        settings,
    };
    let candidate = candidate::render(&bytes, &request).unwrap();
    assert_eq!(candidate.records.len(), 1);
    let record = &candidate.records[0];
    assert_eq!(record.raster_policy, RasterPolicy::FreeTypeMono);
    let plain =
        font_generator::probe::rasterize(&record.fitted_commands, &request.settings).unwrap();
    assert_eq!(
        placement(&RasterOutput {
            pixels: record.pixels.clone(),
            coverage: record.coverage.clone(),
            left: record.left,
            top: record.top,
            width: record.width,
            height: record.height,
        }),
        placement(&plain),
        "native grid preserved"
    );
    // The fitter may move geometry. This raster contract compares against
    // the shared scanner on that same outline; independent fixtures live in mono_scanner.rs.
    let expected =
        font_generator::mono::rasterize(&record.fitted_commands, &request.settings).unwrap();
    assert_eq!(record.coverage, expected.coverage);
    assert_eq!(record.pixels, expected.pixels);
}
