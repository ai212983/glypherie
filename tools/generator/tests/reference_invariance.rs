use font_generator::{
    reference::{reference, ReferenceRequest, PROFILE_GRAY_3BIT, PROFILE_MONO_1BIT},
    Config, Hinting,
};
use std::{collections::BTreeMap, fs, path::PathBuf};

fn font_bytes(name: &str) -> Vec<u8> {
    fs::read(
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../fonts")
            .join(name),
    )
    .unwrap()
}

fn corpus_chars() -> String {
    let mut text = String::new();
    for byte in 33u8..=126u8 {
        text.push(byte as char);
    }
    text.push('°');
    text
}

fn axes_for(family: &str, ppem: f32) -> BTreeMap<String, f32> {
    let mut axes = BTreeMap::new();
    if family == "Roboto.ttf" {
        axes.insert(String::from("wght"), 400.0);
        axes.insert(String::from("wdth"), 100.0);
    } else if family == "Literata.ttf" {
        axes.insert(String::from("wght"), 400.0);
        axes.insert(String::from("opsz"), ppem);
    } else {
        axes.insert(String::from("wght"), 400.0);
    }
    axes
}

fn build_request(
    profile: &str,
    hinting: Hinting,
    ppem: f32,
    axes: BTreeMap<String, f32>,
    characters: String,
) -> ReferenceRequest {
    ReferenceRequest {
        profile: String::from(profile),
        extensions: String::from("none"),
        settings: Config {
            size_px: ppem,
            axes,
            hinting,
            output_bits: if profile == PROFILE_MONO_1BIT { 1 } else { 3 },
            mono_threshold: 128,
            gray_gamma: 1.0,
            characters,
            ..Config::default()
        },
    }
}

fn check_case(data: &[u8], family: &str, ppem: u32, profile: &str, hinting: Hinting) {
    let label = format!("{family} {ppem}px {profile} {hinting:?}");
    let full_text = corpus_chars();
    let reversed_text: String = full_text.chars().rev().collect();
    let size = ppem as f32;
    let full = reference(
        data,
        &build_request(profile, hinting, size, axes_for(family, size), full_text),
    )
    .unwrap();
    let reversed = reference(
        data,
        &build_request(
            profile,
            hinting,
            size,
            axes_for(family, size),
            reversed_text,
        ),
    )
    .unwrap();
    assert_eq!(full.records.len(), 95, "{label}");
    assert_eq!(reversed.records.len(), 95, "{label}");
    assert!(full.missing_codepoints.is_empty(), "{label}");
    assert!(reversed.missing_codepoints.is_empty(), "{label}");
    assert_eq!(
        serde_json::to_vec(&full).unwrap(),
        serde_json::to_vec(&reversed).unwrap(),
        "{label}"
    );
    let full_value = serde_json::to_value(&full).unwrap();
    let full_records = full_value
        .get("records")
        .unwrap()
        .as_array()
        .unwrap()
        .clone();
    assert_eq!(full_records.len(), 95, "{label}");
    for record_value in &full_records {
        let codepoint = record_value.get("codepoint").unwrap().as_u64().unwrap() as u32;
        let glyph = char::from_u32(codepoint).unwrap().to_string();
        let single = reference(
            data,
            &build_request(profile, hinting, size, axes_for(family, size), glyph),
        )
        .unwrap();
        assert_eq!(single.records.len(), 1, "{label} U+{codepoint:04X}");
        assert!(
            single.missing_codepoints.is_empty(),
            "{label} U+{codepoint:04X}"
        );
        let single_value = serde_json::to_value(&single).unwrap();
        let single_records = single_value.get("records").unwrap().as_array().unwrap();
        assert_eq!(single_records.len(), 1, "{label} U+{codepoint:04X}");
        assert_eq!(
            &single_records[0], record_value,
            "{label} U+{codepoint:04X}"
        );
        for key in [
            "metrics",
            "source_sha256",
            "size_px",
            "axes",
            "profile",
            "extensions",
            "hinting_requested",
            "target",
            "smooth_mode",
            "symmetric_rendering",
            "preserve_linear_metrics",
            "draw_pedantic",
            "implementation",
        ] {
            assert_eq!(
                single_value.get(key).unwrap(),
                full_value.get(key).unwrap(),
                "{label} U+{codepoint:04X} {key}"
            );
        }
        let pixels = record_value.get("pixels").unwrap().as_array().unwrap();
        let coverage = record_value.get("coverage").unwrap().as_array().unwrap();
        let width = record_value.get("width").unwrap().as_u64().unwrap() as usize;
        let height = record_value.get("height").unwrap().as_u64().unwrap() as usize;
        assert_eq!(pixels.len(), width * height, "{label} U+{codepoint:04X}");
        assert_eq!(coverage.len(), width * height, "{label} U+{codepoint:04X}");
        assert!(!coverage.is_empty(), "{label} U+{codepoint:04X}");
        use sha2::{Digest, Sha256};
        let raw: Vec<u8> = coverage.iter().map(|v| v.as_u64().unwrap() as u8).collect();
        assert_eq!(
            format!("{:x}", Sha256::digest(&raw)),
            record_value
                .get("coverage_sha256")
                .unwrap()
                .as_str()
                .unwrap(),
            "{label} U+{codepoint:04X}"
        );
    }
}

fn run_family_profile(family: &str, profile: &str) {
    let data = font_bytes(family);
    for ppem in [14u32, 16, 18, 20] {
        for hinting in [Hinting::Auto, Hinting::Interpreter, Hinting::None] {
            check_case(&data, family, ppem, profile, hinting);
        }
    }
}

#[test]
fn roboto_mono_invariance() {
    run_family_profile("Roboto.ttf", PROFILE_MONO_1BIT);
}

#[test]
fn roboto_gray_invariance() {
    run_family_profile("Roboto.ttf", PROFILE_GRAY_3BIT);
}

#[test]
fn literata_mono_invariance() {
    run_family_profile("Literata.ttf", PROFILE_MONO_1BIT);
}

#[test]
fn literata_gray_invariance() {
    run_family_profile("Literata.ttf", PROFILE_GRAY_3BIT);
}

#[test]
fn source_sans_mono_invariance() {
    run_family_profile("SourceSans3.ttf", PROFILE_MONO_1BIT);
}

#[test]
fn source_sans_gray_invariance() {
    run_family_profile("SourceSans3.ttf", PROFILE_GRAY_3BIT);
}
