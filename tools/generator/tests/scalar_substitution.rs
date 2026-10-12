//! Coordinate-dependent one-to-one scalar substitutions.
//!
//! Pinned RobotoFlex reproducer: `$` (U+0024) maps nominally to glyph 7, but
//! the font's Required Variation Alternates (`rvrn` single substitution)
//! select glyph 602 at weight 700. Generation, reference and candidate
//! captures, pair kerning and renderer captures must all use the selected
//! glyph while preserving Unicode identity. These are pinned mechanical
//! checks; they do not establish optical acceptance.
use font_generator::{ascii_kerning_pairs, generate, Config, Hinting};
use skrifa::MetadataProvider;
use std::collections::BTreeMap;
use std::path::Path;

fn font_bytes() -> Vec<u8> {
    std::fs::read(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .join("fonts/RobotoFlex.ttf"),
    )
    .expect("RobotoFlex fixture")
}

fn axes(wght: f32, slnt: f32) -> BTreeMap<String, f32> {
    BTreeMap::from([
        ("wght".to_string(), wght),
        ("slnt".to_string(), slnt),
        ("opsz".to_string(), 14.0),
        ("wdth".to_string(), 100.0),
    ])
}

fn config(characters: &str, wght: f32, slnt: f32) -> Config {
    Config {
        size_px: 14.0,
        axes: axes(wght, slnt),
        characters: characters.into(),
        hinting: Hinting::None,
        ..Config::default()
    }
}

/// Independent source metric for `gid` at these axes via registry Skrifa,
/// separate from the generator's own advance path.
fn source_advance_26_6(data: &[u8], size_px: f32, axes: &BTreeMap<String, f32>, gid: u32) -> i32 {
    let font = skrifa::FontRef::new(data).expect("skrifa font");
    let location = font
        .axes()
        .location(axes.iter().map(|(tag, value)| (tag.as_str(), *value)));
    let advance = font
        .glyph_metrics(skrifa::instance::Size::new(size_px), &location)
        .advance_width(skrifa::GlyphId::new(gid))
        .expect("source advance");
    (advance * 64.0).round() as i32
}

/// Independent unhinted outline raster for `gid` at these axes: drawn with
/// registry Skrifa directly, rasterized with the shared coverage rasterizer.
/// Returns pixels plus the bitmap box, matching the [`font_generator::Glyph`]
/// fields under test.
fn source_outline(data: &[u8], settings: &Config, gid: u32) -> (Vec<u8>, i32, i32, u32, u32) {
    let font = skrifa::FontRef::new(data).expect("skrifa font");
    let location = font.axes().location(
        settings
            .axes
            .iter()
            .map(|(tag, value)| (tag.as_str(), *value)),
    );
    let outline = font
        .outline_glyphs()
        .get(skrifa::GlyphId::new(gid))
        .expect("source outline");
    let mut pen = font_generator::probe::FittedPen::default();
    outline
        .draw(
            skrifa::outline::DrawSettings::unhinted(
                skrifa::instance::Size::new(settings.size_px),
                &location,
            ),
            &mut pen,
        )
        .expect("source draw");
    let output =
        font_generator::probe::rasterize(&pen.into_commands(), settings).expect("source raster");
    (
        output.pixels,
        output.left,
        output.top,
        output.width,
        output.height,
    )
}

#[test]
fn dollar_selects_the_coordinate_glyph_with_its_source_advance() {
    let data = font_bytes();
    // Nominal cmap identity is glyph 7 at every coordinate; the substitution
    // is coordinate-dependent shaping, not a remapped font.
    let nominal = skrifa::FontRef::new(&data)
        .expect("skrifa font")
        .charmap()
        .map('$')
        .expect("cmap dollar")
        .to_u32();
    assert_eq!(nominal, 7);
    for (wght, slnt, expected_gid) in [
        (400.0, 0.0, 7),
        (400.0, -10.0, 7),
        (700.0, 0.0, 602),
        (700.0, -10.0, 602),
    ] {
        let settings = config("$", wght, slnt);
        let generated = generate(&data, &settings)
            .unwrap_or_else(|error| panic!("wght {wght} slnt {slnt}: {error}"));
        assert_eq!(generated.glyphs.len(), 1);
        let glyph = &generated.glyphs[0];
        assert_eq!(glyph.codepoint, u32::from('$'));
        assert_eq!(glyph.glyph_id, expected_gid, "wght {wght} slnt {slnt}");
        // The recorded advance is the selected glyph's source metric.
        assert_eq!(
            glyph.advance_26_6,
            source_advance_26_6(&data, 14.0, &axes(wght, slnt), expected_gid)
        );
        assert!(
            glyph.pixels.iter().any(|&pixel| pixel != 0),
            "wght {wght} slnt {slnt}: dollar must draw ink"
        );
    }
    // The substituted outline is actually drawn: at weight 700 the generated
    // bitmap box matches the independently drawn selected glyph 602 at the
    // same coordinate, not the nominal glyph 7 at that coordinate. Advances
    // cannot establish this: both glyphs measure 507 here.
    for slnt in [0.0, -10.0] {
        let settings = config("$", 700.0, slnt);
        let generated = generate(&data, &settings).unwrap();
        let glyph = &generated.glyphs[0];
        let selected = source_outline(&data, &settings, 602);
        assert_eq!(
            (
                glyph.pixels.clone(),
                glyph.left,
                glyph.top,
                glyph.width,
                glyph.height
            ),
            (selected.0, selected.1, selected.2, selected.3, selected.4),
            "slnt {slnt}: must draw the selected glyph 602 outline"
        );
        let nominal_outline = source_outline(&data, &settings, nominal);
        assert_ne!(
            (glyph.width, glyph.height, glyph.pixels.clone()),
            (nominal_outline.3, nominal_outline.4, nominal_outline.0),
            "slnt {slnt}: must not draw the nominal glyph 7 outline"
        );
    }
}

#[test]
fn full_ascii_repertoire_and_kerning_cover_the_substituted_coordinate() {
    let data = font_bytes();
    let repertoire: String = (0x20u32..=0x7E).filter_map(char::from_u32).collect();
    for (wght, slnt) in [(400.0, 0.0), (400.0, -10.0), (700.0, 0.0), (700.0, -10.0)] {
        let generated = generate(&data, &config(&repertoire, wght, slnt))
            .unwrap_or_else(|error| panic!("wght {wght} slnt {slnt}: {error}"));
        assert_eq!(generated.glyphs.len(), 95, "wght {wght} slnt {slnt}");
        assert!(
            generated
                .glyphs
                .iter()
                .any(|glyph| glyph.codepoint == u32::from('$') && glyph.glyph_id == 602)
                == (wght == 700.0),
            "wght {wght} slnt {slnt}: substitution must apply consistently"
        );
        let table = ascii_kerning_pairs(&data, 14.0, &axes(wght, slnt))
            .unwrap_or_else(|error| panic!("wght {wght} slnt {slnt}: {error}"));
        assert!(
            !table.pairs.is_empty(),
            "wght {wght} slnt {slnt}: pairs must not be hidden"
        );
        assert_eq!(
            table.skipped_pairs, 0,
            "wght {wght} slnt {slnt}: one-to-one substitution must not skip pairs"
        );
    }
}

#[test]
fn omitted_axes_match_explicit_defaults_with_and_without_kerning() {
    let data = font_bytes();
    let font = skrifa::FontRef::new(&data).unwrap();
    let defaults: BTreeMap<String, f32> = font
        .axes()
        .iter()
        .map(|axis| (axis.tag().to_string(), axis.default_value()))
        .collect();
    for requested in [BTreeMap::new(), BTreeMap::from([("wght".into(), 700.0)])] {
        let mut explicit = defaults.clone();
        explicit.extend(requested.clone());
        for kerning in [false, true] {
            let settings = Config {
                axes: requested.clone(),
                kerning,
                ..config("$A", 400.0, 0.0)
            };
            let implicit = generate(&data, &settings).unwrap();
            let explicit = generate(
                &data,
                &Config {
                    axes: explicit.clone(),
                    ..settings.clone()
                },
            )
            .unwrap();
            assert_eq!(implicit.glyphs, explicit.glyphs);
            assert_eq!(implicit.kerning, explicit.kerning);
            let dollar = implicit.glyphs.iter().find(|g| g.codepoint == 36).unwrap();
            assert_eq!(dollar.glyph_id, if requested.is_empty() { 7 } else { 602 });
            assert_eq!(
                dollar.advance_26_6,
                source_advance_26_6(&data, settings.size_px, &requested, dollar.glyph_id)
            );
        }
        assert_eq!(
            ascii_kerning_pairs(&data, 14.0, &requested).unwrap(),
            ascii_kerning_pairs(&data, 14.0, &explicit).unwrap()
        );
    }
}

#[test]
fn reference_baseline_and_candidate_agree_on_the_selected_glyph() {
    let data = font_bytes();
    let settings = config("$", 700.0, 0.0);
    let generated = generate(&data, &settings).unwrap();
    let reference = font_generator::reference::reference(
        &data,
        &font_generator::reference::ReferenceRequest {
            profile: font_generator::reference::PROFILE_MONO_1BIT.to_string(),
            extensions: font_generator::reference::EXTENSIONS_NONE.to_string(),
            settings: settings.clone(),
        },
    )
    .expect("independent reference");
    assert_eq!(reference.records.len(), 1);
    let record = &reference.records[0];
    assert_eq!(record.codepoint, u32::from('$'));
    assert_eq!(record.glyph_id, 602);
    // Unhinted production and independent reference share outline, advance
    // and placement for the selected glyph.
    assert_eq!(record.glyph_id, generated.glyphs[0].glyph_id);
    assert_eq!(record.advance_26_6, generated.glyphs[0].advance_26_6);
    assert_eq!(record.pixels, generated.glyphs[0].pixels);
    assert_eq!(record.left, generated.glyphs[0].left);
    assert_eq!(record.top, generated.glyphs[0].top);
    // Baseline and candidate captures record the same selected glyph. Fitting
    // may change advances and coverage under their own policies; identity
    // must not change.
    let mut fitted_settings = settings.clone();
    fitted_settings.hinting = Hinting::Auto;
    for role in [
        font_generator::renderer::RendererRole::Baseline,
        font_generator::renderer::RendererRole::Candidate,
    ] {
        let report = font_generator::renderer::render(
            &data,
            &font_generator::reference::ReferenceRequest {
                profile: font_generator::reference::PROFILE_MONO_1BIT.to_string(),
                extensions: "diagonal-01".to_string(),
                settings: fitted_settings.clone(),
            },
            role,
        )
        .unwrap_or_else(|error| panic!("{role:?}: {error}"));
        assert_eq!(report.records.len(), 1);
        assert_eq!(report.records[0].codepoint, u32::from('$'));
        assert_eq!(report.records[0].glyph_id, 602, "{role:?}");
    }
}

#[test]
fn renderer_captures_draw_the_substituted_scalar() {
    use font_generator::renderer::RendererRole;
    use font_generator::surface::{render_text_with_renderer, TextRenderRequest};
    let data = font_bytes();
    for role in [
        RendererRole::Baseline,
        RendererRole::Reference,
        RendererRole::Candidate,
    ] {
        let mut settings = config("$", 700.0, 0.0);
        settings.hinting = match role {
            RendererRole::Baseline => Hinting::None,
            _ => Hinting::Auto,
        };
        // Reference keeps production layout with replaced bitmaps; candidate
        // lays out with its fitted advances. Both must accept the scalar.
        let rendered = render_text_with_renderer(
            &data,
            &TextRenderRequest {
                config: settings,
                text: "$".to_string(),
                width: 64,
                height: 32,
                wrap: font_generator::surface::WrapMode::Clip,
                align: font_generator::surface::HAlign::Left,
                foreground: [0, 0, 0, 255],
                background: [255, 255, 255, 255],
                palette: None,
            },
            role,
        )
        .unwrap_or_else(|error| panic!("{role:?}: {error}"));
        assert!(
            rendered
                .pixels
                .chunks_exact(4)
                .any(|texel| texel != [255, 255, 255, 255]),
            "{role:?}: substituted dollar must draw ink"
        );
    }
}

// Small original CFF fixture: glyph 1 is space (advance 300), glyph 2 is A
// (advance 600). Construct layout tables from the OpenType layouts rather
// than relying on a particular production font to exercise capability guards.
// https://learn.microsoft.com/en-us/typography/opentype/spec/gsub
// https://learn.microsoft.com/en-us/typography/opentype/spec/gpos
fn words(values: &[u16]) -> Vec<u8> {
    values
        .iter()
        .flat_map(|value| value.to_be_bytes())
        .collect()
}

fn layout_table(feature: &[u8; 4], lookup_type: u16, subtable: &[u8]) -> Vec<u8> {
    let mut bytes = words(&[1, 0, 10, 30, 44]);
    bytes.extend(words(&[1]));
    bytes.extend(b"DFLT");
    bytes.extend(words(&[8, 4, 0, 0, 0xffff, 1, 0]));
    bytes.extend(words(&[1]));
    bytes.extend(feature);
    bytes.extend(words(&[8, 0, 1, 0]));
    bytes.extend(words(&[1, 4, lookup_type, 0, 1, 8]));
    bytes.extend(subtable);
    bytes
}

fn fixture_with(tag: &[u8; 4], table: Vec<u8>) -> Vec<u8> {
    const STATIC: &[u8] = include_bytes!("fixtures/static-cff.otf");
    let source = skrifa::FontRef::new(STATIC).unwrap();
    let mut builder = write_fonts::FontBuilder::new();
    for record in source.table_directory().table_records() {
        let table_tag = record.tag();
        if table_tag.to_be_bytes() != *tag {
            builder.add_raw(table_tag, source.table_data(table_tag).unwrap().as_bytes());
        }
    }
    builder.add_raw(write_fonts::types::Tag::new(tag), table);
    builder.build()
}

fn static_config() -> Config {
    Config {
        characters: "A".into(),
        size_px: 14.0,
        hinting: Hinting::None,
        ..Config::default()
    }
}

#[test]
fn generic_single_substitution_uses_selected_glyph_metrics() {
    // SingleSubst format 2: A -> space, with coverage of A.
    let table = layout_table(b"rvrn", 1, &words(&[2, 8, 1, 1, 1, 1, 2]));
    let bytes = fixture_with(b"GSUB", table);
    let generated = generate(&bytes, &static_config()).unwrap();
    let glyph = &generated.glyphs[0];
    assert_eq!(glyph.codepoint, u32::from('A'));
    assert_eq!(glyph.glyph_id, 1);
    assert!(glyph.pixels.is_empty());
    assert_eq!(
        glyph.advance_26_6,
        source_advance_26_6(&bytes, 14.0, &BTreeMap::new(), 1)
    );
    assert_ne!(
        glyph.advance_26_6,
        source_advance_26_6(&bytes, 14.0, &BTreeMap::new(), 2)
    );
    assert_eq!(
        ascii_kerning_pairs(&bytes, 14.0, &BTreeMap::new())
            .unwrap()
            .skipped_pairs,
        0
    );
}

#[test]
fn scalar_count_changes_and_notdef_remain_explicit_errors() {
    for (lookup_type, subtable) in [
        // SingleSubst: A -> .notdef.
        (1, words(&[2, 8, 1, 0, 1, 1, 2])),
        // MultipleSubst: A -> A A; one sequence, then coverage of A.
        (2, words(&[1, 14, 1, 8, 2, 2, 2, 1, 1, 2])),
    ] {
        let bytes = fixture_with(b"GSUB", layout_table(b"rvrn", lookup_type, &subtable));
        assert!(generate(&bytes, &static_config()).is_err());
        assert!(ascii_kerning_pairs(&bytes, 14.0, &BTreeMap::new()).is_err());
    }
}

#[test]
fn standalone_positioning_is_rejected_before_output_rounding() {
    for value_format in [1, 2, 4] {
        // SinglePos format 1: one design unit of x/y offset or horizontal advance.
        // At 14 px, xAdvance rounds to less than one 26.6 unit; it must still
        // be rejected, not hidden by a size-dependent metric tolerance.
        let table = layout_table(b"kern", 1, &words(&[1, 8, value_format, 1, 1, 1, 2]));
        let bytes = fixture_with(b"GPOS", table);
        for size_px in [1.0, 14.0, 31.5, 512.0] {
            let settings = Config {
                size_px,
                ..static_config()
            };
            assert!(
                generate(&bytes, &settings).is_err(),
                "format {value_format}, size {size_px}"
            );
            assert!(ascii_kerning_pairs(&bytes, size_px, &BTreeMap::new()).is_err());
        }
    }
}

#[test]
fn pair_right_advance_and_offsets_still_fail_or_report_omissions() {
    for (left_format, right_format) in [(0, 4), (1, 0)] {
        // PairPos format 1 for A A: either the right advance or left xOffset
        // changes. Singles stay unchanged, so only pair validation can detect it.
        let subtable = words(&[1, 12, left_format, right_format, 1, 18, 1, 1, 2, 1, 2, 1]);
        let bytes = fixture_with(b"GPOS", layout_table(b"kern", 2, &subtable));
        assert!(generate(&bytes, &static_config()).is_err());
        assert_eq!(
            ascii_kerning_pairs(&bytes, 14.0, &BTreeMap::new())
                .unwrap()
                .skipped_pairs,
            1
        );
    }
    // Required ligature: A A -> A changes pair count although A alone is valid.
    let ligature = words(&[1, 18, 1, 8, 1, 4, 2, 2, 2, 1, 1, 2]);
    let bytes = fixture_with(b"GSUB", layout_table(b"rlig", 4, &ligature));
    assert!(generate(&bytes, &static_config()).is_err());
    assert_eq!(
        ascii_kerning_pairs(&bytes, 14.0, &BTreeMap::new())
            .unwrap()
            .skipped_pairs,
        1
    );
}

#[test]
fn fractional_axes_and_sizes_keep_selected_linear_metrics() {
    let data = font_bytes();
    for (size_px, wght, opsz, wdth, slnt) in [
        (14.7, 100.0, 8.0, 151.0, -10.0),
        (31.5, 523.0, 31.5, 87.5, -7.3),
        (512.0, 523.0, 144.0, 87.5, -7.3),
    ] {
        let settings = Config {
            size_px,
            axes: BTreeMap::from([
                ("wght".into(), wght),
                ("opsz".into(), opsz),
                ("wdth".into(), wdth),
                ("slnt".into(), slnt),
            ]),
            characters: "@$W".into(),
            hinting: Hinting::None,
            kerning: false,
            ..Config::default()
        };
        for rounding in [
            font_generator::MetricRounding::Subpixel,
            font_generator::MetricRounding::Pixel,
        ] {
            let settings = Config {
                metric_rounding: rounding,
                ..settings.clone()
            };
            let generated = generate(&data, &settings).unwrap();
            for glyph in generated.glyphs {
                let expected = source_advance_26_6(&data, size_px, &settings.axes, glyph.glyph_id);
                let expected = match rounding {
                    font_generator::MetricRounding::Subpixel => expected,
                    font_generator::MetricRounding::Pixel => {
                        let font = skrifa::FontRef::new(&data).unwrap();
                        let location = font.axes().location(
                            settings
                                .axes
                                .iter()
                                .map(|(tag, value)| (tag.as_str(), *value)),
                        );
                        let value = font
                            .glyph_metrics(skrifa::instance::Size::new(size_px), &location)
                            .advance_width(skrifa::GlyphId::new(glyph.glyph_id))
                            .unwrap();
                        (value.round() * 64.0) as i32
                    }
                };
                assert_eq!(glyph.advance_26_6, expected);
            }
        }
    }
}

#[test]
fn contextual_one_to_one_pair_substitution_remains_unsupported() {
    // ReverseChainSingleSubst: A -> space only after space. A alone stays A;
    // the pair changes an identity, not its count or positioning.
    let subtable = words(&[1, 14, 1, 20, 0, 1, 1, 1, 1, 2, 1, 1, 1]);
    let bytes = fixture_with(b"GSUB", layout_table(b"rvrn", 8, &subtable));
    let settings = Config {
        characters: " A".into(),
        ..static_config()
    };
    assert!(generate(&bytes, &settings).is_err());
    assert_eq!(
        ascii_kerning_pairs(&bytes, 14.0, &BTreeMap::new())
            .unwrap()
            .skipped_pairs,
        1
    );
}
