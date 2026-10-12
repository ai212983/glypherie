#![cfg(feature = "candidate")]

use font_generator::{comparison, specimens};
use serde_json::{json, Value};
use std::{
    fs,
    io::Cursor,
    path::{Path, PathBuf},
};

fn fixture() -> (tempfile::TempDir, PathBuf, PathBuf) {
    let temp = tempfile::tempdir().unwrap();
    let mut config: Value = serde_json::from_str(include_str!("../specimens.json")).unwrap();
    config.as_object_mut().unwrap().remove("preview_policy");
    config.as_object_mut().unwrap().remove("cards");
    config["families"].as_array_mut().unwrap().truncate(1);
    config["families"][0]["font"] =
        json!(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fonts/Roboto.ttf"));
    config["defaults"]["sizes"] = json!([16, 14]);
    config["variants"].as_array_mut().unwrap().truncate(2);
    config["defaults"]["variants"] = json!(["reference", "iteration-02"]);
    config["characters"] = json!("AX\"");
    config["samples"] = json!([{ "id": "text", "label": "Text", "text": "A X\"" }]);
    let specimen_config = temp.path().join("specimens.json");
    fs::write(&specimen_config, serde_json::to_vec(&config).unwrap()).unwrap();
    let root = temp.path().join("output");
    specimens::publish(&specimen_config, &root).unwrap();
    let config = temp.path().join("comparisons.json");
    let mut selection: Value =
        serde_json::from_slice(include_bytes!("../comparisons.json")).unwrap();
    // This fixture explicitly publishes the accepted baseline/reference pair.
    selection["id"] = json!("01");
    fs::write(&config, serde_json::to_vec(&selection).unwrap()).unwrap();
    (temp, root, config)
}

fn manifest(root: &Path) -> (PathBuf, Value) {
    let index: Value =
        serde_json::from_slice(&fs::read(root.join("comparisons/index.json")).unwrap()).unwrap();
    let path = root
        .join("comparisons")
        .join(index["comparisons"][0]["manifest"].as_str().unwrap());
    let manifest = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    (path, manifest)
}

#[test]
fn exports_configured_glyphs_profiles_and_sizes_without_changing_active_selection() {
    let (_temp, root, config) = fixture();
    let active = fs::read(root.join("active.json")).unwrap();
    assert_eq!(comparison::publish(&config, &root).unwrap(), 1);
    assert_eq!(fs::read(root.join("active.json")).unwrap(), active);
    let (path, m) = manifest(&root);
    assert_eq!(m["id"], "01");
    assert_eq!(m["previous"]["label"], "Reference");
    assert_eq!(m["current"]["label"], font_generator::baseline::VERSION);
    let sizes = m["families"][0]["sizes"].as_array().unwrap();
    assert_eq!(
        sizes
            .iter()
            .map(|s| s["size_px"].as_f64().unwrap())
            .collect::<Vec<_>>(),
        [14., 16.]
    );
    for size in sizes {
        assert_eq!(size["glyphs"].as_array().unwrap().len(), 2);
        for glyph in size["glyphs"].as_array().unwrap() {
            assert_ne!(glyph["character"], "\"");
            for profile in glyph["profiles"].as_array().unwrap() {
                assert_eq!(profile["id"], "mono_1bit");
                assert!(profile["reason"].is_null());
                for kind in ["previous", "current", "difference"] {
                    let file = path
                        .parent()
                        .unwrap()
                        .join(profile[kind]["path"].as_str().unwrap());
                    let mut decoder = png::Decoder::new(Cursor::new(fs::read(file).unwrap()))
                        .read_info()
                        .unwrap();
                    let mut pixels = vec![0; decoder.output_buffer_size().unwrap()];
                    let info = decoder.next_frame(&mut pixels).unwrap();
                    assert_eq!(
                        info.width as u64,
                        size["canvas"]["width_px"].as_u64().unwrap()
                    );
                    assert_eq!(
                        info.height as u64,
                        size["canvas"]["height_px"].as_u64().unwrap()
                    );
                    assert_eq!(info.color_type, png::ColorType::Rgb);
                    if kind == "difference" {
                        assert!(pixels[..info.buffer_size()].chunks_exact(3).any(|pixel| {
                            pixel == comparison::ADDED || pixel == comparison::REMOVED
                        }));
                    }
                }
            }
        }
    }
    let bytes = fs::read(&path).unwrap();
    for stats in m["statistics"].as_array().unwrap() {
        let profile_id = stats["profile"].as_str().unwrap();
        let mut changed_pixels = Vec::new();
        for size in sizes {
            for glyph in size["glyphs"].as_array().unwrap() {
                for profile in glyph["profiles"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .filter(|p| p["id"] == profile_id)
                {
                    let file = path
                        .parent()
                        .unwrap()
                        .join(profile["difference"]["path"].as_str().unwrap());
                    let mut decoder = png::Decoder::new(Cursor::new(fs::read(file).unwrap()))
                        .read_info()
                        .unwrap();
                    let mut pixels = vec![0; decoder.output_buffer_size().unwrap()];
                    let info = decoder.next_frame(&mut pixels).unwrap();
                    changed_pixels.push(
                        pixels[..info.buffer_size()]
                            .chunks_exact(3)
                            .filter(|pixel| {
                                *pixel == comparison::ADDED || *pixel == comparison::REMOVED
                            })
                            .count(),
                    );
                }
            }
        }
        changed_pixels.sort_unstable();
        assert_eq!(
            stats["changed_symbols"].as_u64().unwrap() as usize,
            changed_pixels.len()
        );
        assert_eq!(
            stats["same_symbols"].as_u64().unwrap() as usize,
            6 - changed_pixels.len()
        );
        assert!(stats.get("unavailable_symbols").is_none());
        let (average, median) = if changed_pixels.is_empty() {
            (0.0, 0.0)
        } else {
            let n = changed_pixels.len();
            (
                changed_pixels.iter().sum::<usize>() as f64 / n as f64,
                (changed_pixels[(n - 1) / 2] + changed_pixels[n / 2]) as f64 / 2.0,
            )
        };
        assert_eq!(stats["average_changed_pixels"].as_f64().unwrap(), average);
        assert_eq!(stats["median_changed_pixels"].as_f64().unwrap(), median);
    }
    let index_time = fs::metadata(root.join("comparisons/index.json"))
        .unwrap()
        .modified()
        .unwrap();
    comparison::publish(&config, &root).unwrap();
    assert_eq!(fs::read(&path).unwrap(), bytes);
    assert_eq!(
        fs::metadata(root.join("comparisons/index.json"))
            .unwrap()
            .modified()
            .unwrap(),
        index_time
    );
}

#[test]
fn identical_inputs_export_no_comparison_images() {
    let (_temp, root, config) = fixture();
    let source_path = config.parent().unwrap().join("specimens.json");
    let mut source: Value = serde_json::from_slice(&fs::read(&source_path).unwrap()).unwrap();
    // Gray rendering leaves diagonal fitting disabled in both renderer roles.
    source["defaults"]["profiles"] = json!(["gray_3bit"]);
    fs::write(&source_path, serde_json::to_vec(&source).unwrap()).unwrap();
    specimens::publish(&source_path, &root).unwrap();
    comparison::publish(&config, &root).unwrap();
    let (path, m) = manifest(&root);
    for size in m["families"][0]["sizes"].as_array().unwrap() {
        assert!(size["glyphs"].as_array().unwrap().is_empty());
    }
    for stats in m["statistics"].as_array().unwrap() {
        assert_eq!(stats["same_symbols"], 6);
        assert_eq!(stats["changed_symbols"], 0);
        assert!(stats.get("unavailable_symbols").is_none());
        assert_eq!(stats["average_changed_pixels"], 0.0);
        assert_eq!(stats["median_changed_pixels"], 0.0);
    }
    assert_eq!(
        fs::read_dir(path.parent().unwrap().join("assets"))
            .unwrap()
            .count(),
        0
    );
}

#[test]
fn rejects_unsafe_routes_and_unknown_selections_without_changing_index() {
    let (_temp, root, config) = fixture();
    comparison::publish(&config, &root).unwrap();
    let original = fs::read(root.join("comparisons/index.json")).unwrap();
    let base: Value = serde_json::from_slice(include_bytes!("../comparisons.json")).unwrap();
    for (field, value) in [
        ("id", "../escape"),
        ("id", "iteration-02"),
        ("current", "missing-package"),
        ("previous", "reference"),
    ] {
        let mut doc = base.clone();
        doc[field] = json!(value);
        fs::write(&config, serde_json::to_vec(&doc).unwrap()).unwrap();
        assert!(comparison::publish(&config, &root).is_err());
        assert_eq!(
            fs::read(root.join("comparisons/index.json")).unwrap(),
            original
        );
    }
}

#[test]
fn missing_previous_size_fails_without_replacing_comparison_index() {
    let (_temp, root, config) = fixture();
    comparison::publish(&config, &root).unwrap();
    let index = fs::read(root.join("comparisons/index.json")).unwrap();
    let mut source: Value = serde_json::from_str(include_str!("../specimens.json")).unwrap();
    source.as_object_mut().unwrap().remove("preview_policy");
    source["variants"].as_array_mut().unwrap().truncate(2);
    source["defaults"]["variants"] = json!(["reference", "iteration-02"]);
    source["families"].as_array_mut().unwrap().truncate(1);
    source["families"][0]["font"] =
        json!(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fonts/Roboto.ttf"));
    source["defaults"]["sizes"] = json!([14, {"size_px": 16, "variants": ["iteration-02"]}]);
    let source_path = config.parent().unwrap().join("limited.json");
    fs::write(&source_path, serde_json::to_vec(&source).unwrap()).unwrap();
    specimens::publish(&source_path, &root).unwrap();
    let error = comparison::publish(&config, &root).unwrap_err().to_string();
    assert!(
        error.contains("Previous comparison glyph missing"),
        "{error}"
    );
    assert!(
        error.contains("family roboto, size 16 px, profile mono_1bit, U+0021"),
        "{error}"
    );
    assert_eq!(
        fs::read(root.join("comparisons/index.json")).unwrap(),
        index
    );
}

#[test]
fn missing_previous_or_current_glyph_fails_with_context_and_preserves_index() {
    for (characters, expected_side) in [("AX\"Z", "Previous"), ("AX\"\u{10ffff}", "Current")] {
        let (_temp, root, config) = fixture();
        comparison::publish(&config, &root).unwrap();
        let index = fs::read(root.join("comparisons/index.json")).unwrap();
        let published: Value =
            serde_json::from_slice(&fs::read(root.join("published.json")).unwrap()).unwrap();
        let source_path = config.parent().unwrap().join("specimens.json");
        let mut source: Value = serde_json::from_slice(&fs::read(&source_path).unwrap()).unwrap();
        source["characters"] = json!(characters);
        fs::write(&source_path, serde_json::to_vec(&source).unwrap()).unwrap();
        specimens::publish(&source_path, &root).unwrap();
        // Keep the baseline immutable while extending the latest iteration's repertoire.
        let mut updated: Value =
            serde_json::from_slice(&fs::read(root.join("published.json")).unwrap()).unwrap();
        updated["variants"]["reference"] = published["variants"]["reference"].clone();
        fs::write(
            root.join("published.json"),
            serde_json::to_vec(&updated).unwrap(),
        )
        .unwrap();
        let error = comparison::publish(&config, &root).unwrap_err().to_string();
        assert!(
            error.contains(&format!("{expected_side} comparison glyph missing")),
            "{error}"
        );
        assert!(
            error.contains("family roboto")
                && error.contains("profile mono_1bit")
                && error.contains("U+"),
            "{error}"
        );
        assert_eq!(
            fs::read(root.join("comparisons/index.json")).unwrap(),
            index
        );
    }
}

#[test]
fn candidate_compares_to_approved_baseline_across_versions() {
    let (_temp, root, config) = fixture();
    let source_path = config.parent().unwrap().join("specimens.json");
    let mut source: Value = serde_json::from_slice(&fs::read(&source_path).unwrap()).unwrap();
    // Hypothetical future iterations exercise selection after explicit user closure.
    let mut newer = source["variants"][1].clone();
    newer["renderer"] = json!("candidate");
    newer["id"] = json!("future-iteration");
    newer["version"] = json!("001.03");
    source["variants"].as_array_mut().unwrap().push(newer);
    source["defaults"]["variants"] = json!(["reference", "iteration-02", "future-iteration"]);
    fs::write(&source_path, serde_json::to_vec(&source).unwrap()).unwrap();
    specimens::publish(&source_path, &root).unwrap();
    comparison::publish(&config, &root).unwrap();
    let (_, m) = manifest(&root);
    assert_eq!(m["current"]["label"], "001.03");
    assert_eq!(m["previous"]["label"], font_generator::baseline::VERSION);
    let mut next_revision = source["variants"][2].clone();
    next_revision["id"] = json!("next-revision");
    next_revision["version"] = json!("002.01");
    source["variants"]
        .as_array_mut()
        .unwrap()
        .push(next_revision);
    source["defaults"]["variants"] = json!([
        "reference",
        "iteration-02",
        "future-iteration",
        "next-revision"
    ]);
    fs::write(&source_path, serde_json::to_vec(&source).unwrap()).unwrap();
    specimens::publish(&source_path, &root).unwrap();
    comparison::publish(&config, &root).unwrap();
    let (_, m) = manifest(&root);
    assert_eq!(m["current"]["label"], "002.01");
    assert_eq!(m["previous"]["label"], font_generator::baseline::VERSION);
}
