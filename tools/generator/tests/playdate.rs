use font_generator::{playdate, Config, FontMetrics, GeneratedFont, Glyph, KerningPair};
use std::{collections::BTreeMap, io::Cursor};

struct Parsed {
    fields: BTreeMap<String, String>,
    entries: Vec<(String, i32)>,
    pixels: Vec<u8>,
    width: usize,
    // Common left inset applied to every cell; informational only.
    origin_x: i32,
}

fn parse(bytes: &[u8]) -> Parsed {
    let text = std::str::from_utf8(bytes).unwrap();
    let mut fields = BTreeMap::new();
    let mut entries = Vec::new();
    for line in text.lines().filter(|l| !l.starts_with("--")) {
        if let Some((k, v)) = line.split_once('=') {
            fields.insert(k.to_owned(), v.to_owned());
        } else if let Some((k, v)) = line.split_once('\t') {
            entries.push((k.to_owned(), v.parse().unwrap()));
        }
    }
    let origin_x = text
        .lines()
        .find_map(|l| l.strip_prefix("--origin_x="))
        .map(|v| v.parse().unwrap())
        .unwrap_or(0);
    let data = &fields["data"];
    assert_eq!(fields["datalen"].parse::<usize>().unwrap(), data.len());
    let alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut accumulator = 0u32;
    let mut bits = 0;
    let mut png = Vec::new();
    for byte in data.bytes().take_while(|b| *b != b'=') {
        accumulator = (accumulator << 6) | alphabet.iter().position(|b| *b == byte).unwrap() as u32;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            png.push((accumulator >> bits) as u8);
        }
    }
    let mut reader = png::Decoder::new(Cursor::new(png)).read_info().unwrap();
    let mut pixels = vec![0; reader.output_buffer_size().unwrap()];
    let info = reader.next_frame(&mut pixels).unwrap();
    assert_eq!(info.color_type, png::ColorType::Rgba);
    pixels.truncate(info.buffer_size());
    Parsed {
        fields,
        entries,
        pixels,
        width: info.width as usize,
        origin_x,
    }
}

fn fixture() -> GeneratedFont {
    GeneratedFont {
        source_sha256: "fixture".into(),
        config: Config {
            characters: " A".into(),
            ..Config::default()
        },
        metrics: FontMetrics {
            ascent_26_6: 128,
            descent_26_6: -64,
            line_gap_26_6: 64,
        },
        glyphs: vec![
            Glyph {
                codepoint: 65,
                glyph_id: 1,
                advance_26_6: 64,
                left: 1,
                top: -2,
                width: 3,
                height: 3,
                pixels: vec![1, 0, 1, 1, 1, 1, 1, 0, 1],
            },
            Glyph {
                codepoint: 32,
                glyph_id: 2,
                advance_26_6: 128,
                left: 0,
                top: 0,
                width: 0,
                height: 0,
                pixels: vec![],
            },
        ],
        missing_codepoints: vec![],
        kerning: vec![
            KerningPair {
                left: 65,
                right: 65,
                adjustment_26_6: -64,
            },
            KerningPair {
                left: 32,
                right: 65,
                adjustment_26_6: 64,
            },
        ],
    }
}

#[test]
fn standalone_font_preserves_overhangs_spaces_descenders_and_signed_kerning() {
    let font = fixture();
    let bytes = playdate::encode(&font).unwrap();
    assert_eq!(bytes, playdate::encode(&font).unwrap());
    // Zero inset stays byte-identical: no informational header line appears.
    assert_eq!(parse(&bytes).origin_x, 0);
    assert!(!std::str::from_utf8(&bytes).unwrap().contains("--origin_x="));
    let p = parse(&bytes);
    assert_eq!(p.fields["height"], "4");
    assert_eq!(p.fields["width"], "5");
    assert_eq!(p.fields["tracking"], "-3");
    assert_eq!(
        p.entries,
        vec![
            ("U+0020".into(), 5),
            ("U+0041".into(), 4),
            ("U+0020U+0041".into(), 1),
            ("U+0041U+0041".into(), -1)
        ]
    );
    let mut ink = 0;
    for y in 0..4 {
        for x in 0..10 {
            let alpha = p.pixels[(y * p.width + x) * 4 + 3];
            let expected = if (6..9).contains(&x) && y < 3 {
                font.glyphs[0].pixels[y * 3 + x - 6] * 255
            } else {
                0
            };
            assert_eq!(alpha, expected, "({x},{y})");
            ink += usize::from(alpha != 0);
        }
    }
    assert_eq!(ink, 7);
}

#[test]
fn left_overhang_shifts_every_cell_and_preserves_advances() {
    // A `j`-like glyph with actual ink left of the pen origin, surrounded by
    // ordinary glyphs and spaces, with signed pairs in both directions.
    let left_overhang = GeneratedFont {
        source_sha256: "fixture".into(),
        config: Config {
            characters: " AjV".into(),
            ..Config::default()
        },
        metrics: FontMetrics {
            ascent_26_6: 128,
            descent_26_6: -64,
            line_gap_26_6: 64,
        },
        glyphs: vec![
            Glyph {
                codepoint: 32,
                glyph_id: 10,
                advance_26_6: 128,
                left: 0,
                top: 0,
                width: 0,
                height: 0,
                pixels: vec![],
            },
            Glyph {
                codepoint: 65,
                glyph_id: 11,
                advance_26_6: 64,
                left: 1,
                top: -2,
                width: 3,
                height: 3,
                pixels: vec![1, 0, 1, 1, 1, 1, 1, 0, 1],
            },
            Glyph {
                codepoint: 106,
                glyph_id: 12,
                advance_26_6: 64,
                left: -2,
                top: -2,
                width: 3,
                height: 4,
                pixels: vec![0, 0, 1, 0, 0, 1, 1, 1, 1, 1, 1, 0],
            },
            Glyph {
                codepoint: 86,
                glyph_id: 13,
                advance_26_6: 128,
                left: 0,
                top: -2,
                width: 4,
                height: 3,
                pixels: vec![1, 0, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0],
            },
        ],
        missing_codepoints: vec![],
        kerning: vec![
            KerningPair {
                left: 65,
                right: 86,
                adjustment_26_6: -64,
            },
            KerningPair {
                left: 86,
                right: 65,
                adjustment_26_6: 64,
            },
        ],
    };
    let bytes = playdate::encode(&left_overhang).unwrap();
    let p = parse(&bytes);
    // The common inset covers the leftmost ink (x = -2), not glyph padding.
    assert_eq!(p.origin_x, 2);
    assert_eq!(p.fields["height"], "4");
    assert_eq!(p.fields["tracking"], "-5");
    // Every entry keeps width + tracking == finalized advance, so line
    // widths and pair-adjusted spacing are unchanged by the inset. Glyph
    // entries precede pair entries; both are ordered by codepoint.
    assert_eq!(
        p.entries,
        vec![
            ("U+0020".into(), 7),
            ("U+0041".into(), 6),
            ("U+0056".into(), 7),
            ("U+006A".into(), 6),
            ("U+0041U+0056".into(), -1),
            ("U+0056U+0041".into(), 1),
        ]
    );
    let tracking: i32 = p.fields["tracking"].parse().unwrap();
    for g in &left_overhang.glyphs {
        let width = p
            .entries
            .iter()
            .find(|e| e.0 == format!("U+{:04X}", g.codepoint))
            .unwrap()
            .1;
        assert_eq!(width + tracking, g.advance_26_6 / 64);
    }
    // No ink is lost: the sheet holds every fixture pixel, and every cell
    // moved right by the same inset, including ordinary positive bearings.
    // Cells follow codepoint order: space, A, V, then the overhanging glyph.
    let cell_width: usize = p.fields["width"].parse().unwrap();
    assert_eq!(cell_width, 7);
    let mut sorted = left_overhang.glyphs.clone();
    sorted.sort_by_key(|g| g.codepoint);
    let mut ink = 0;
    for (i, g) in sorted.iter().enumerate() {
        for y in 0..g.height as usize {
            for x in 0..g.width as usize {
                if g.pixels[y * g.width as usize + x] == 0 {
                    continue;
                }
                let sx = i * cell_width + (p.origin_x + g.left) as usize + x;
                let sy = y;
                assert_eq!(p.pixels[(sy * p.width + sx) * 4 + 3], 255);
                ink += 1;
            }
        }
    }
    assert_eq!(ink, 7 + 7 + 6);
    assert_eq!(
        p.pixels
            .chunks_exact(4)
            .filter(|pixel| pixel[3] == 255)
            .count(),
        ink
    );
    // The overhanging glyph starts at its cell edge; its transparent columns
    // hold no ink. The ordinary glyph keeps the same inset-shifted bearing.
    let j_cell = 3 * cell_width;
    let a_cell = 1 * cell_width;
    assert_eq!(p.pixels[(0 * p.width + j_cell) * 4 + 3], 0);
    assert_eq!(p.pixels[(2 * p.width + j_cell) * 4 + 3], 255);
    assert_eq!(p.pixels[(0 * p.width + a_cell + 3) * 4 + 3], 255);
    // Pen math over spaces and signed pairs matches advances plus pairs.
    let advance = |cp: u32| {
        left_overhang
            .glyphs
            .iter()
            .find(|g| g.codepoint == cp)
            .unwrap()
            .advance_26_6
            / 64
    };
    let pair = |key: &str| {
        p.entries
            .iter()
            .find(|e| e.0 == key)
            .map(|e| e.1)
            .unwrap_or(0)
    };
    let pen = |text: &str| {
        let mut pen = 0;
        let mut previous: Option<String> = None;
        for ch in text.chars() {
            if let Some(left) = previous {
                pen += pair(&format!("{left}U+{:04X}", ch as u32));
            }
            let key = format!("U+{:04X}", ch as u32);
            pen += p.entries.iter().find(|e| e.0 == key).unwrap().1 + tracking;
            previous = Some(key);
        }
        pen
    };
    assert_eq!(
        pen("A j V"),
        advance(65) + advance(32) + advance(106) + advance(32) + advance(86)
    );
    assert_eq!(pen("AV"), advance(65) + pair("U+0041U+0056") + advance(86));
    assert_eq!(pen("VA"), advance(86) + pair("U+0056U+0041") + advance(65));
}

#[test]
fn deep_left_overhang_keeps_empty_glyphs_small_but_still_bounds_large_cells() {
    // A single ink pixel far left of a 1px advance must not inflate empty
    // glyphs: blanks keep the legacy 1px floor with no inset added.
    let narrow = GeneratedFont {
        source_sha256: "fixture".into(),
        config: Config {
            characters: " A".into(),
            ..Config::default()
        },
        metrics: FontMetrics {
            ascent_26_6: 64,
            descent_26_6: 0,
            line_gap_26_6: 0,
        },
        glyphs: vec![
            Glyph {
                codepoint: 32,
                glyph_id: 2,
                advance_26_6: 64,
                left: 0,
                top: 0,
                width: 0,
                height: 0,
                pixels: vec![],
            },
            Glyph {
                codepoint: 65,
                glyph_id: 1,
                advance_26_6: 64,
                left: -130,
                top: -1,
                width: 1,
                height: 1,
                pixels: vec![1],
            },
        ],
        missing_codepoints: vec![],
        kerning: vec![],
    };
    let bytes = playdate::encode(&narrow).unwrap();
    let p = parse(&bytes);
    assert_eq!(p.origin_x, 130);
    assert_eq!(p.fields["tracking"], "0");
    assert_eq!(p.fields["width"], "1");
    assert_eq!(p.entries, vec![("U+0020".into(), 1), ("U+0041".into(), 1)]);
    assert_eq!(
        p.pixels
            .chunks_exact(4)
            .filter(|pixel| pixel[3] == 255)
            .count(),
        1
    );
    // Deep-negative ink combined with ordinary rightward ink still exceeds the
    // shared tracking budget instead of clipping.
    let mut wide = narrow.clone();
    let dot = wide.glyphs.iter_mut().find(|g| g.codepoint == 65).unwrap();
    dot.advance_26_6 = 128;
    dot.width = 132;
    dot.pixels = vec![0; 132];
    dot.pixels[0] = 1;
    dot.pixels[131] = 1;
    assert!(playdate::encode(&wide).is_err());
}

#[test]
fn unrepresentable_metrics_and_invalid_bitmaps_fail_without_clipping() {
    let mut cases = Vec::new();
    let mut f = fixture();
    f.glyphs[0].top = -3;
    cases.push(f);
    let mut f = fixture();
    f.glyphs[0].height = 4;
    f.glyphs[0].pixels.resize(12, 1);
    f.glyphs[0].top = 0;
    cases.push(f);
    let mut f = fixture();
    f.glyphs[0].advance_26_6 = 65;
    cases.push(f);
    let mut f = fixture();
    f.glyphs[0].advance_26_6 = -64;
    cases.push(f);
    let mut f = fixture();
    f.glyphs[0].pixels[0] = 2;
    cases.push(f);
    let mut f = fixture();
    f.glyphs[0].pixels.pop();
    cases.push(f);
    let mut f = fixture();
    f.glyphs[0].codepoint = 0x40000;
    cases.push(f);
    let mut f = fixture();
    f.glyphs[0].codepoint = 0xd800;
    cases.push(f);
    let mut f = fixture();
    f.glyphs[0].codepoint = 32;
    cases.push(f);
    let mut f = fixture();
    f.config.output_bits = 3;
    cases.push(f);
    let mut f = fixture();
    f.missing_codepoints.push(66);
    cases.push(f);
    let mut f = fixture();
    f.kerning[0].right = 66;
    cases.push(f);
    let mut f = fixture();
    f.kerning[0].adjustment_26_6 = 128 * 64;
    cases.push(f);
    let mut f = fixture();
    f.kerning.push(f.kerning[0].clone());
    cases.push(f);
    let mut f = fixture();
    f.metrics.ascent_26_6 = i32::MAX;
    cases.push(f);
    for (i, font) in cases.iter().enumerate() {
        assert!(playdate::encode(font).is_err(), "invalid case {i}");
    }
}

#[cfg(feature = "candidate")]
#[test]
fn exported_font_reconstructs_preview_pixels_and_pen_advances() {
    use font_generator::{
        candidate,
        renderer::{Rasterization, RenderPipeline},
        stem_fitting::StemFittingStrategy,
        surface::{self, HAlign, TextRenderRequest, WrapMode},
    };
    let data = std::fs::read(format!(
        "{}/../../fonts/Roboto.ttf",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap();
    // Ordinary full printable ASCII, including the left-overhanging `j`.
    let characters: String = (0x20u32..=0x7e).filter_map(char::from_u32).collect();
    let text = "AV To j\nj To AV";
    for fitting in [
        StemFittingStrategy::FontHintsFirst,
        StemFittingStrategy::UpstreamMono,
    ] {
        for rasterization in [
            Rasterization::FreeTypeMono,
            Rasterization::FreeTypeMonoTerminals,
            Rasterization::Coverage,
        ] {
            for spacing in [-1.0, 0.0, 2.0] {
                for kerning in [false, true] {
                    let pipeline = RenderPipeline {
                        fitting,
                        rasterization,
                        diagonal_fitting: false,
                    };
                    let config = Config {
                        characters: characters.clone(),
                        size_px: 18.0,
                        kerning,
                        mono_raster: if rasterization != Rasterization::Coverage {
                            font_generator::MonoRasterSettings {
                                include_stubs: true,
                                font_instructions: true,
                                ..Default::default()
                            }
                        } else {
                            Default::default()
                        },
                        ..Config::default()
                    };
                    let font = candidate::generate_monochrome_font_with_pipeline(
                        &data, &config, pipeline, spacing,
                    )
                    .unwrap();
                    let bytes = playdate::export(
                        &data,
                        &playdate::ExportRequest {
                            config: config.clone(),
                            pipeline,
                            letter_spacing_px: spacing,
                        },
                    )
                    .unwrap();
                    let p = parse(&bytes);
                    let cell_width: usize = p.fields["width"].parse().unwrap();
                    let cell_height: usize = p.fields["height"].parse().unwrap();
                    let tracking: i32 = p.fields["tracking"].parse().unwrap();
                    // Every cell carries the same common inset, so the blit
                    // origin moves left by that inset to meet the preview.
                    let inset = p.origin_x;
                    let expected = surface::render_text_with_pipeline_and_spacing(
                        &data,
                        &TextRenderRequest {
                            config,
                            text: text.into(),
                            width: 200,
                            height: 100,
                            wrap: WrapMode::Clip,
                            align: HAlign::Left,
                            foreground: [0, 0, 0, 255],
                            background: [255, 255, 255, 255],
                            palette: None,
                        },
                        pipeline,
                        spacing,
                    )
                    .unwrap();
                    let mut pixels = vec![255u8; 200 * 100 * 4];
                    for (row, line) in text.lines().enumerate() {
                        let mut pen = 0i32;
                        let mut previous = None;
                        for ch in line.chars() {
                            if let Some(left) = previous {
                                let key = format!("U+{left:04X}U+{:04X}", ch as u32);
                                pen += p
                                    .entries
                                    .iter()
                                    .find(|e| e.0 == key)
                                    .map(|e| e.1)
                                    .unwrap_or(0);
                            }
                            let index = font
                                .glyphs
                                .iter()
                                .position(|g| g.codepoint == ch as u32)
                                .unwrap();
                            for y in 0..cell_height {
                                for x in 0..cell_width {
                                    let sx = index % 16 * cell_width + x;
                                    let sy = index / 16 * cell_height + y;
                                    if p.pixels[(sy * p.width + sx) * 4 + 3] == 255 {
                                        let dx = pen + x as i32 - inset;
                                        let dy = row * cell_height + y;
                                        if dx >= 0 && dx < 200 && dy < 100 {
                                            pixels[(dy * 200 + dx as usize) * 4..][..3].fill(0);
                                        }
                                    }
                                }
                            }
                            pen += p.entries[index].1 + tracking;
                            previous = Some(ch as u32);
                        }
                        // Pen accumulation matches the native preview line width.
                        // Playdate-reported bounds additionally include the
                        // terminal cell padding and read wider.
                        assert_eq!(pen * 64, expected.lines[row].width_26_6);
                    }
                    assert_eq!(
                        pixels, expected.pixels,
                        "{pipeline:?}, tracking {spacing}, kerning {kerning}"
                    );
                }
            }
        }
    }
}

#[cfg(feature = "candidate")]
#[test]
fn roboto_and_source_sans_j_export_with_common_inset() {
    use font_generator::{
        candidate,
        renderer::{Rasterization, RenderPipeline},
        stem_fitting::StemFittingStrategy,
    };
    for name in ["Roboto.ttf", "SourceSans3.ttf"] {
        let data =
            std::fs::read(format!("{}/../../fonts/{name}", env!("CARGO_MANIFEST_DIR"))).unwrap();
        let pipeline = RenderPipeline {
            fitting: StemFittingStrategy::FontHintsFirst,
            rasterization: Rasterization::FreeTypeMonoTerminals,
            diagonal_fitting: false,
        };
        let config = Config {
            characters: "Aj".into(),
            size_px: 18.0,
            kerning: true,
            mono_raster: font_generator::MonoRasterSettings {
                include_stubs: true,
                font_instructions: true,
                ..Default::default()
            },
            ..Config::default()
        };
        let font = candidate::generate_monochrome_font_with_pipeline(&data, &config, pipeline, 0.0)
            .unwrap();
        let bytes = playdate::export(
            &data,
            &playdate::ExportRequest {
                config: config.clone(),
                pipeline,
                letter_spacing_px: 0.0,
            },
        )
        .unwrap();
        let p = parse(&bytes);
        // The reported `j` overhang is accommodated, not rejected.
        assert!(p.origin_x > 0, "{name}");
        let tracking: i32 = p.fields["tracking"].parse().unwrap();
        for g in &font.glyphs {
            let width = p
                .entries
                .iter()
                .find(|e| e.0 == format!("U+{:04X}", g.codepoint))
                .unwrap()
                .1;
            assert_eq!(width + tracking, g.advance_26_6 / 64, "{name}");
        }
    }
}

#[test]
fn transparent_scanner_padding_does_not_change_the_export() {
    let original = fixture();
    let mut padded = original.clone();
    let glyph = &mut padded.glyphs[0];
    glyph.left = -1;
    glyph.top = -3;
    glyph.width = 5;
    glyph.height = 4;
    glyph.pixels = vec![0; 20];
    for y in 0..3 {
        glyph.pixels[(y + 1) * 5 + 2..][..3]
            .copy_from_slice(&original.glyphs[0].pixels[y * 3..][..3]);
    }
    assert_eq!(
        playdate::encode(&padded).unwrap(),
        playdate::encode(&original).unwrap()
    );
}

#[cfg(not(feature = "candidate"))]
#[test]
fn production_build_rejects_export_without_falling_back_to_another_renderer() {
    let request = playdate::ExportRequest {
        config: Config {
            characters: "A".into(),
            ..Config::default()
        },
        pipeline: Default::default(),
        letter_spacing_px: 0.0,
    };
    assert!(playdate::export(&[], &request)
        .unwrap_err()
        .to_string()
        .contains("candidate Cargo feature"));
}
