use font_generator::metadata::extract;
use skrifa::{
    raw::{types::Tag, TableProvider},
    FontRef,
};
use std::{fs, path::Path};
use write_fonts::FontBuilder;

const STATIC: &[u8] = include_bytes!("fixtures/static-cff.otf");
const VARIABLE: &[u8] = include_bytes!("fixtures/variable-cff2.otf");

fn font_with(tag: &[u8; 4], table: Vec<u8>) -> Vec<u8> {
    FontBuilder::new().add_raw(Tag::new(tag), table).build()
}

fn words(words: &[u16]) -> Vec<u8> {
    words.iter().flat_map(|word| word.to_be_bytes()).collect()
}

// GPOS with one DFLT script, one feature and a format-1 PairPos lookup.
// The pair (glyphs 1, 2) has xAdvance -20; this is independent of font outlines.
fn gpos(tag: &[u8; 4], empty_feature: bool) -> Vec<u8> {
    let mut bytes = words(&[1, 0, 10, 30, 44]);
    bytes.extend(words(&[1]));
    bytes.extend(b"DFLT");
    bytes.extend(words(&[8, 4, 0, 0, 0xffff, 1, 0]));
    bytes.extend(words(&[1]));
    bytes.extend(tag);
    bytes.extend(words(&[8, 0, if empty_feature { 0 } else { 1 }, 0]));
    bytes.extend(words(&[1, 4, 2, 0, 1, 8]));
    bytes.extend(words(&[1, 12, 4, 0, 1, 18]));
    bytes.extend(words(&[1, 1, 1])); // Coverage: glyph 1.
    bytes.extend(words(&[1, 2, (-20_i16) as u16]));
    bytes
}

#[test]
fn shipped_fonts_export_names_license_axes_style_and_coverage() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fonts");
    for (file, family, tags, weight) in [
        ("Roboto.ttf", "Roboto", vec!["wght", "wdth"], 400),
        ("Literata.ttf", "Literata", vec!["opsz", "wght"], 400),
        ("SourceSans3.ttf", "Source Sans 3", vec!["wght"], 200),
    ] {
        let data = fs::read(root.join(file)).unwrap();
        let metadata = extract(&data).unwrap();
        assert_eq!(
            metadata.glyph_count,
            Some(u32::from(
                FontRef::new(&data).unwrap().maxp().unwrap().num_glyphs()
            ))
        );
        assert_eq!(metadata.names["family"].as_deref(), Some(family));
        assert!(metadata.names["license"]
            .as_deref()
            .unwrap()
            .contains("Open Font License"));
        assert!(metadata.names["license_url"].is_some());
        assert_eq!(
            metadata
                .axes
                .iter()
                .map(|axis| axis.tag.as_str())
                .collect::<Vec<_>>(),
            tags
        );
        assert!(metadata.axes.iter().all(|axis| axis.name.is_some()
            && axis.min <= axis.default
            && axis.default <= axis.max));
        assert!(metadata.kerning.horizontal);
        assert!(!metadata.kerning.vertical);
        assert_eq!(metadata.kerning.sources, ["GPOS kern"]);
        assert_eq!(metadata.style.slope.as_deref(), Some("upright"));
        assert_eq!(metadata.style.weight_class, Some(weight));
        assert_eq!(metadata.classification.monospaced, Some(false));
        let coverage = metadata.coverage.unwrap();
        assert!(coverage
            .ranges
            .iter()
            .any(|range| range[0] <= 65 && range[1] >= 65));
        assert_eq!(
            coverage.character_count,
            coverage
                .ranges
                .iter()
                .map(|range| range[1] - range[0] + 1)
                .sum::<u32>()
        );
        assert!(metadata.declared_unicode_ranges.is_some());
    }
}

#[test]
fn static_and_variable_postscript_fonts_and_absent_optional_metadata() {
    let static_metadata = extract(STATIC).unwrap();
    assert!(static_metadata.axes.is_empty());
    assert!(!static_metadata.kerning.horizontal);
    let variable = extract(VARIABLE).unwrap();
    assert_eq!(variable.axes.len(), 1);
    let axis = &variable.axes[0];
    assert_eq!(axis.tag, "wght");
    assert_eq!((axis.min, axis.default, axis.max), (100.0, 100.0, 900.0));
    // A valid SFNT directory with no descriptive tables must not invent defaults.
    let bare = font_with(b"TEST", vec![]);
    let unknown = extract(&bare).unwrap();
    assert!(unknown.names.values().all(Option::is_none));
    assert_eq!(unknown.style.slope, None);
    assert_eq!(unknown.style.weight_class, None);
    assert_eq!(unknown.classification.panose, None);
    assert_eq!(unknown.classification.monospaced, None);
    assert!(unknown.coverage.is_none());
    assert_eq!(unknown.glyph_count, None);
    assert!(extract(b"not a font").is_err());
}

#[test]
fn gpos_features_distinguish_horizontal_vertical_unrelated_and_empty_data() {
    for (tag, empty, horizontal, vertical) in [
        (b"kern", false, true, false),
        (b"vkrn", false, false, true),
        (b"mark", false, false, false),
        (b"kern", true, false, false),
    ] {
        let data = font_with(b"GPOS", gpos(tag, empty));
        let metadata = extract(&data).unwrap();
        assert_eq!(
            (metadata.kerning.horizontal, metadata.kerning.vertical),
            (horizontal, vertical)
        );
    }
}

#[test]
fn legacy_opentype_apple_and_extended_kerning_and_empty_tables() {
    let pair = words(&[1, 0, 0, 0, 1, 2, (-20_i16) as u16]);
    for (coverage, horizontal) in [(1, true), (0, false)] {
        let mut table = words(&[0, 1, 0, (6 + pair.len()) as u16, coverage]);
        table.extend(&pair);
        let data = font_with(b"kern", table);
        let kerning = extract(&data).unwrap().kerning;
        assert_eq!(
            (kerning.horizontal, kerning.vertical),
            (horizontal, !horizontal)
        );
        assert_eq!(kerning.sources, ["kern"]);
    }
    let mut apple = words(&[1, 0, 0, 1, 0, (8 + pair.len()) as u16, 0, 0]);
    apple.extend(&pair);
    assert!(
        extract(&font_with(b"kern", apple))
            .unwrap()
            .kerning
            .horizontal
    );
    // kerx format 0: 32-bit counts/header and a 16-bit pair record.
    let mut extended = words(&[2, 0, 0, 1, 0, 34, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0]);
    extended.extend(words(&[1, 2, (-20_i16) as u16]));
    let kerning = extract(&font_with(b"kerx", extended)).unwrap().kerning;
    assert!(kerning.horizontal);
    assert_eq!(kerning.sources, ["kerx"]);
    for (tag, table) in [(b"kern", words(&[0, 0])), (b"kerx", words(&[2, 0, 0, 0]))] {
        let kerning = extract(&font_with(tag, table)).unwrap().kerning;
        assert!(!kerning.horizontal && !kerning.vertical);
        assert!(kerning.sources.is_empty());
    }
    // Pair subtable with zero pairs is also empty.
    let empty = words(&[0, 1, 0, 14, 1, 0, 0, 0, 0]);
    assert!(
        !extract(&font_with(b"kern", empty))
            .unwrap()
            .kerning
            .horizontal
    );
}

#[test]
fn malformed_kerning_is_an_error_instead_of_false_availability() {
    for (tag, bytes) in [
        (b"GPOS", vec![0]),
        (b"kern", words(&[0, 1])),
        (b"kerx", words(&[2, 0, 0, 1])),
    ] {
        assert!(extract(&font_with(tag, bytes)).is_err());
    }
    let mut bad = gpos(b"kern", false);
    bad[42..44].copy_from_slice(&7_u16.to_be_bytes()); // invalid lookup index
    assert!(extract(&font_with(b"GPOS", bad)).is_err());
}

#[test]
fn coverage_reports_actual_scalars_not_declared_ranges_or_notdef() {
    let groups = [
        [32_u32, 32, 0],
        [65, 66, 1],
        [0xd800, 0xd800, 3],
        [0x1f600, 0x1f600, 4],
        [0x1f601, 0x1f601, 50],
    ];
    let mut cmap = words(&[0, 1, 3, 10, 0, 12, 12, 0]);
    for value in [16 + groups.len() as u32 * 12, 0, groups.len() as u32] {
        cmap.extend(value.to_be_bytes());
    }
    for group in groups {
        for value in group {
            cmap.extend(value.to_be_bytes());
        }
    }
    let data = FontBuilder::new()
        .add_raw(Tag::new(b"cmap"), cmap)
        .add_raw(Tag::new(b"maxp"), words(&[0, 0x5000, 5]))
        .build();
    let metadata = extract(&data).unwrap();
    assert_eq!(
        metadata.glyph_count,
        Some(5),
        "glyph total includes unencoded glyphs and .notdef"
    );
    let coverage = metadata.coverage.unwrap();
    assert_eq!(coverage.character_count, 3);
    assert_eq!(coverage.ranges, [[65, 66], [0x1f600, 0x1f600]]);
}

#[test]
fn style_and_classification_preserve_declared_values() {
    let font = FontRef::new(STATIC).unwrap();
    let mut os2 = font.os2().unwrap().offset_data().as_bytes().to_vec();
    os2[4..6].copy_from_slice(&700_u16.to_be_bytes());
    os2[6..8].copy_from_slice(&3_u16.to_be_bytes());
    os2[30..32].copy_from_slice(&0x0802_u16.to_be_bytes());
    os2[32..42].copy_from_slice(&[2, 11, 8, 9, 2, 2, 2, 2, 2, 2]);
    os2[62..64].copy_from_slice(&1_u16.to_be_bytes()); // italic
    let metadata = extract(&font_with(b"OS/2", os2)).unwrap();
    assert_eq!(metadata.style.slope.as_deref(), Some("italic"));
    assert_eq!(metadata.style.weight_class, Some(700));
    assert_eq!(metadata.style.width_class, Some(3));
    assert_eq!(metadata.classification.family_class, Some(0x0802));
    assert_eq!(metadata.classification.panose.unwrap()[1], 11);
}

#[test]
fn localized_names_prefer_english_typographic_names_and_skip_blank_strings() {
    let records = [
        (1_u16, 0x0409_u16, "Legacy family"),
        (16, 0x0407, "Deutsch"),
        (16, 0x0409, "English family"),
        (2, 0x0409, "Regular"),
        (17, 0x0409, " "),
        (13, 0x0409, "License text"),
    ];
    let mut table = words(&[0, records.len() as u16, 6 + records.len() as u16 * 12]);
    let mut strings = Vec::new();
    for (id, language, text) in records {
        let bytes: Vec<_> = text.encode_utf16().flat_map(u16::to_be_bytes).collect();
        table.extend(words(&[
            3,
            1,
            language,
            id,
            bytes.len() as u16,
            strings.len() as u16,
        ]));
        strings.extend(bytes);
    }
    table.extend(strings);
    let names = extract(&font_with(b"name", table)).unwrap().names;
    assert_eq!(names["family"].as_deref(), Some("English family"));
    assert_eq!(names["style"].as_deref(), Some("Regular"));
    assert_eq!(names["license"].as_deref(), Some("License text"));
    assert_eq!(names["license_url"], None);
}
