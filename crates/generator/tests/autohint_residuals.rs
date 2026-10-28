#![cfg(feature = "candidate")]
use font_generator::{
    candidate::render_with_rasterization,
    reference::{self, ReferenceRequest},
    renderer::Rasterization,
    Config, Hinting,
};
use std::{collections::BTreeMap, fs, path::Path};

fn roboto() -> Vec<u8> {
    fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fonts/Roboto.ttf")).unwrap()
}

fn ascii() -> String {
    (0x20u32..=0x7Eu32)
        .map(|code| char::from_u32(code).unwrap())
        .collect()
}

fn config(characters: &str, hinting: Hinting) -> Config {
    let mut axes = BTreeMap::new();
    axes.insert("wght".into(), 400.0);
    axes.insert("wdth".into(), 100.0);
    Config {
        size_px: 16.0,
        axes,
        characters: characters.into(),
        hinting,
        ..Default::default()
    }
}

fn request(characters: &str, extensions: &str, hinting: Hinting) -> ReferenceRequest {
    ReferenceRequest {
        profile: "mono_1bit".into(),
        extensions: extensions.into(),
        settings: config(characters, hinting),
    }
}

#[test]
fn upstream_mono_carries_snapshot_residuals() {
    let data = roboto();
    let report = render_with_rasterization(
        &data,
        &request(&ascii(), "mono-width-01", Hinting::Auto),
        Rasterization::FreeTypeMono,
    )
    .unwrap();
    assert_eq!(report.records.len(), 95);
    for record in &report.records {
        assert_eq!(record.selected_engine, "auto");
        assert!(
            record.side_bearing_deltas_26_6.is_some(),
            "U+{:04X} lacks automatic bearing residuals",
            record.codepoint
        );
    }
    // SPACE keeps its empty-outline distinction; digits stay zeroed.
    let by_code: std::collections::HashMap<u32, [i32; 2]> = report
        .records
        .iter()
        .map(|record| (record.codepoint, record.side_bearing_deltas_26_6.unwrap()))
        .collect();
    assert_eq!(by_code[&32], [0, 2]);
    for digit in 0x30u32..=0x39u32 {
        assert_eq!(by_code[&digit], [0, 0]);
    }
}

#[test]
fn native_hints_keep_no_automatic_residuals() {
    let data = roboto();
    // Roboto carries native instructions, so font-hints-first selects
    // the interpreter: X stays native-owned.
    let report = render_with_rasterization(
        &data,
        &request(&ascii(), "font-hints-01", Hinting::Auto),
        Rasterization::FreeTypeMono,
    )
    .unwrap();
    assert!(report
        .records
        .iter()
        .all(|record| record.side_bearing_deltas_26_6.is_none()));
}

#[test]
fn scanner_choice_keeps_identical_residuals_and_reference_keeps_none() {
    let data = roboto();
    let mono = render_with_rasterization(
        &data,
        &request(&ascii(), "mono-width-01", Hinting::Auto),
        Rasterization::FreeTypeMono,
    )
    .unwrap();
    let coverage = render_with_rasterization(
        &data,
        &request(&ascii(), "mono-width-01", Hinting::Auto),
        Rasterization::Coverage,
    )
    .unwrap();
    assert_eq!(mono.records.len(), coverage.records.len());
    assert_eq!(mono.records.len(), 95);
    for (m, c) in mono.records.iter().zip(&coverage.records) {
        assert_eq!(m.codepoint, c.codepoint);
        assert_eq!(
            m.fitted_commands, c.fitted_commands,
            "U+{:04X} keeps its fitted outline across scanners",
            m.codepoint
        );
        assert_eq!(
            m.side_bearing_deltas_26_6, c.side_bearing_deltas_26_6,
            "U+{:04X} keeps its residuals across scanners",
            m.codepoint
        );
        assert!(
            m.side_bearing_deltas_26_6.is_some(),
            "U+{:04X} lacks automatic bearing residuals",
            m.codepoint
        );
    }
    let reference = reference::reference(&data, &request(&ascii(), "none", Hinting::Auto)).unwrap();
    assert!(reference
        .records
        .iter()
        .all(|record| record.side_bearing_deltas_26_6.is_none()));
}

#[test]
fn gray_and_reference_keep_no_residuals() {
    let data = roboto();
    let mut gray = request(&ascii(), "mono-width-01", Hinting::Auto);
    gray.profile = "gray_3bit".into();
    gray.settings.output_bits = 3;
    let gray_report = render_with_rasterization(&data, &gray, Rasterization::Coverage).unwrap();
    assert!(gray_report
        .records
        .iter()
        .all(|record| record.side_bearing_deltas_26_6.is_none()));
    let reference = reference::reference(&data, &request(&ascii(), "none", Hinting::Auto)).unwrap();
    assert!(reference
        .records
        .iter()
        .all(|record| record.side_bearing_deltas_26_6.is_none()));
}
