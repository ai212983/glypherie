//! Host correctness checks; these do not establish physical panel readability.
use font_generator::{generate, Config, Hinting, MetricRounding, MissingGlyphs};
use std::path::Path;

fn font(path: &str) -> Vec<u8> {
    std::fs::read(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .join(path),
    )
    .unwrap_or_else(|error| panic!("fixture {path}: {error}"))
}

const CALIBRATION: [&str; 3] = [
    "fonts/Roboto.ttf",
    "fonts/Literata.ttf",
    "fonts/SourceSans3.ttf",
];

fn config(characters: &str) -> Config {
    Config {
        size_px: 32.0,
        characters: characters.into(),
        hinting: Hinting::Auto,
        ..Config::default()
    }
}

#[test]
fn calibration_fonts_generate_deterministically_at_each_output_depth() {
    for path in CALIBRATION {
        let bytes = font(path);
        for bits in [1, 2, 3, 4, 8] {
            let mut cfg = config(" AVTo08°bhmnp");
            cfg.axes.insert("wght".into(), 400.0);
            cfg.output_bits = bits;
            let a = generate(&bytes, &cfg).unwrap();
            let b = generate(&bytes, &cfg).unwrap();
            assert_eq!(
                serde_json::to_vec(&a).unwrap(),
                serde_json::to_vec(&b).unwrap(),
                "{path}/{bits}"
            );
            assert_eq!(a.glyphs.len(), cfg.characters.chars().count());
            for glyph in &a.glyphs {
                assert_eq!(glyph.pixels.len(), (glyph.width * glyph.height) as usize);
                assert!(glyph.pixels.iter().all(|&p| u16::from(p) < (1u16 << bits)));
                assert!(glyph.advance_26_6 > 0);
            }
            let space = a
                .glyphs
                .iter()
                .find(|g| g.codepoint == u32::from(' '))
                .unwrap();
            assert!(space.pixels.iter().all(|&p| p == 0));
            assert!(a.metrics.ascent_26_6 > 0);
            assert!(a.metrics.descent_26_6 < 0);
        }
    }
}

#[test]
fn unsupported_axes_and_out_of_range_values_are_reported() {
    let variable = font(CALIBRATION[0]);
    let mut cfg = config("A");
    cfg.axes.insert("opsz".into(), 12.0);
    assert!(generate(&variable, &cfg).is_err());
    cfg.axes.clear();
    cfg.axes.insert("wght".into(), 1000.0);
    assert!(generate(&variable, &cfg).is_err());
    cfg.axes.insert("wght".into(), f32::NAN);
    assert!(generate(&variable, &cfg).is_err());
}

#[test]
fn variable_axes_change_glyphs_and_metrics() {
    let bytes = font(CALIBRATION[0]);
    let mut cfg = config("Hm");
    cfg.axes.insert("wght".into(), 100.0);
    let thin = generate(&bytes, &cfg).unwrap();
    cfg.axes.insert("wght".into(), 900.0);
    let heavy = generate(&bytes, &cfg).unwrap();
    let ink = |f: &font_generator::GeneratedFont| {
        f.glyphs
            .iter()
            .flat_map(|g| &g.pixels)
            .map(|&p| u64::from(p))
            .sum::<u64>()
    };
    assert!(ink(&heavy) > ink(&thin));
    cfg.axes.insert("wdth".into(), 75.0);
    let narrow = generate(&bytes, &cfg).unwrap();
    assert!(
        narrow.glyphs.iter().map(|g| g.advance_26_6).sum::<i32>()
            < heavy.glyphs.iter().map(|g| g.advance_26_6).sum::<i32>()
    );
}

#[test]
fn missing_characters_follow_explicit_policy() {
    let bytes = font(CALIBRATION[0]);
    let mut cfg = config("A\u{1e02}");
    cfg.missing_glyphs = MissingGlyphs::Error;
    assert!(generate(&bytes, &cfg).is_err());
    cfg.missing_glyphs = MissingGlyphs::Skip;
    let generated = generate(&bytes, &cfg).unwrap();
    assert_eq!(generated.missing_codepoints, vec![0x1e02]);
    assert_eq!(generated.glyphs.len(), 1);
    assert_eq!(generated.glyphs[0].codepoint, u32::from('A'));
}

#[test]
fn invalid_files_and_rendering_options_are_reported() {
    for bytes in [
        b"".as_slice(),
        b"404: Not Found",
        b"wOFFinvalid",
        b"ttcfinvalid",
    ] {
        assert!(generate(bytes, &config("A")).is_err());
    }
    let bytes = font(CALIBRATION[0]);
    for size in [0.0, -1.0, f32::NAN, f32::INFINITY] {
        let mut cfg = config("A");
        cfg.size_px = size;
        assert!(generate(&bytes, &cfg).is_err());
    }
    for bits in [0, 5, 16] {
        let mut cfg = config("A");
        cfg.output_bits = bits;
        assert!(generate(&bytes, &cfg).is_err());
    }
}

#[test]
fn kerning_and_metric_rounding_preserve_spacing_contract() {
    let bytes = font(CALIBRATION[0]);
    let mut cfg = config("AVTo");
    cfg.size_px = 31.0;
    cfg.kerning = true;
    let precise = generate(&bytes, &cfg).unwrap();
    let av = precise
        .kerning
        .iter()
        .find(|p| p.left == u32::from('A') && p.right == u32::from('V'))
        .unwrap();
    assert!(av.adjustment_26_6 < 0);
    cfg.metric_rounding = MetricRounding::Pixel;
    let rounded = generate(&bytes, &cfg).unwrap();
    for (a, b) in precise.glyphs.iter().zip(&rounded.glyphs) {
        assert_eq!(b.advance_26_6 % 64, 0);
        assert!((a.advance_26_6 - b.advance_26_6).abs() <= 32);
        assert_eq!(a.pixels, b.pixels);
    }
    assert!(rounded.kerning.iter().all(|p| p.adjustment_26_6 % 64 == 0));
    cfg.kerning = false;
    assert!(generate(&bytes, &cfg).unwrap().kerning.is_empty());
}

// Foreground uses eight-neighbor connectivity; background uses four-neighbor
// connectivity and a clear border, so its exterior is one component.
fn components(grid: &[bool], width: usize, height: usize, value: bool, diagonal: bool) -> usize {
    let mut seen = vec![false; grid.len()];
    let mut count = 0;
    for start in 0..grid.len() {
        if seen[start] || grid[start] != value {
            continue;
        }
        count += 1;
        seen[start] = true;
        let mut stack = vec![start];
        while let Some(i) = stack.pop() {
            let (x, y) = (i % width, i / width);
            for dy in -1isize..=1 {
                for dx in -1isize..=1 {
                    if (dx == 0 && dy == 0) || (!diagonal && dx != 0 && dy != 0) {
                        continue;
                    }
                    let (nx, ny) = (x as isize + dx, y as isize + dy);
                    if nx < 0 || ny < 0 || nx >= width as isize || ny >= height as isize {
                        continue;
                    }
                    let next = ny as usize * width + nx as usize;
                    if !seen[next] && grid[next] == value {
                        seen[next] = true;
                        stack.push(next);
                    }
                }
            }
        }
    }
    count
}

#[test]
fn focused_join_and_counter_diagnostics() {
    // These simple Latin shapes have an explicit expected topology. This bounded
    // diagnostic is not a claim about every glyph, size, or physical panel.
    for path in CALIBRATION {
        let bytes = font(path);
        for size in [16.0, 32.0] {
            let mut cfg = config("bhmnpo08");
            cfg.size_px = size;
            cfg.axes.insert("wght".into(), 400.0);
            cfg.output_bits = 1;
            cfg.mono_threshold = if size <= 20.0 { 96 } else { 128 };
            let generated = generate(&bytes, &cfg).unwrap();
            for glyph in &generated.glyphs {
                let width = glyph.width as usize + 2;
                let height = glyph.height as usize + 2;
                let mut grid = vec![false; width * height];
                for y in 0..glyph.height as usize {
                    for x in 0..glyph.width as usize {
                        grid[(y + 1) * width + x + 1] =
                            glyph.pixels[y * glyph.width as usize + x] != 0;
                    }
                }
                let ch = char::from_u32(glyph.codepoint).unwrap();
                let expected_holes = match ch {
                    'b' | 'p' | 'o' | '0' => 1,
                    '8' => 2,
                    _ => 0,
                };
                assert_eq!(
                    components(&grid, width, height, true, true),
                    1,
                    "disconnected ink: {path}/{size}/{ch}"
                );
                assert_eq!(
                    components(&grid, width, height, false, false) - 1,
                    expected_holes,
                    "counter topology: {path}/{size}/{ch}"
                );
            }
        }
    }
}

#[test]
fn rendering_controls_have_observable_effects() {
    let bytes = font(CALIBRATION[0]);
    for hinting in [
        Hinting::None,
        Hinting::Auto,
        Hinting::Interpreter,
        Hinting::AutoFallback,
    ] {
        let mut cfg = config("Hob");
        cfg.hinting = hinting;
        assert!(generate(&bytes, &cfg).is_ok());
    }
    let mut cfg = config("Ho");
    cfg.output_bits = 1;
    cfg.mono_threshold = 64;
    let thick = generate(&bytes, &cfg).unwrap();
    cfg.mono_threshold = 192;
    let thin = generate(&bytes, &cfg).unwrap();
    for (a, b) in thick.glyphs.iter().zip(&thin.glyphs) {
        assert!(a.pixels.iter().zip(&b.pixels).all(|(x, y)| x >= y));
        assert!(
            a.pixels.iter().map(|&p| u64::from(p)).sum::<u64>()
                >= b.pixels.iter().map(|&p| u64::from(p)).sum::<u64>()
        );
    }
    cfg.output_bits = 8;
    cfg.gray_gamma = 1.0;
    let linear = generate(&bytes, &cfg).unwrap();
    cfg.gray_gamma = 2.0;
    let adjusted = generate(&bytes, &cfg).unwrap();
    assert!(linear
        .glyphs
        .iter()
        .zip(&adjusted.glyphs)
        .any(|(a, b)| a.pixels != b.pixels));
}

#[test]
fn unsupported_text_shaping_is_explicit() {
    let bytes = font(CALIBRATION[0]);
    for text in ["a\u{301}", "مرحبا", "A\nB", "A\u{200d}B"] {
        for missing_glyphs in [MissingGlyphs::Error, MissingGlyphs::Skip] {
            let mut cfg = config(text);
            cfg.missing_glyphs = missing_glyphs;
            assert!(
                generate(&bytes, &cfg).is_err(),
                "{text:?} {missing_glyphs:?}"
            );
        }
    }
}
