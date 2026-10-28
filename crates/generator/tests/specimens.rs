use font_generator::{
    reference::{reference, ReferenceRequest},
    specimen_config::load,
    specimens::{publish, validate_package, Manifest, Outcome},
    Config, Hinting,
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::Cursor,
    path::{Path, PathBuf},
    process::Command,
};

fn fixture() -> Value {
    let mut value: Value = serde_json::from_str(include_str!("../specimens.json")).unwrap();
    value.as_object_mut().unwrap().remove("preview_policy");
    value.as_object_mut().unwrap().remove("cards");
    value["variants"].as_array_mut().unwrap().truncate(1);
    value["defaults"]["variants"] = json!(["reference"]);
    value["families"].as_array_mut().unwrap().truncate(1);
    value["families"][0]["font"] =
        json!(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fonts/Roboto.ttf"));
    value["defaults"]["sizes"] = json!([14]);
    value["characters"] = json!("AVTo");
    value["samples"] = json!([{ "id": "text", "label": "Test sample", "text": "A V To" }]);
    value
}

#[test]
fn configurable_cards_publish_titles_content_and_builtin_coverage() {
    let temp = tempfile::tempdir().unwrap();
    let mut value = fixture();
    value.as_object_mut().unwrap().remove("samples");
    value["cards"] = json!([
        {"id": "reading", "title": "Custom reading", "content": "A V\nTo"},
        {"id": "pair", "title": "Letter pair", "content": "AV"}
    ]);
    let path = config(temp.path(), &value);
    let output = temp.path().join("output");
    let first = publish(&path, &output).unwrap();
    let first_manifest = manifest(&output, &first.active.variant_id);
    let items = &first_manifest.families[0].sizes[0].items;
    assert_eq!(items.len(), 6);
    for profile_items in items.chunks(3) {
        assert_eq!(profile_items[0].label, "Custom reading");
        assert_eq!(profile_items[0].text, "A V\nTo");
        assert_eq!(profile_items[1].label, "Letter pair");
        assert_eq!(profile_items[2].label, "Character coverage");
        assert_eq!(profile_items[2].text, "AVT\no");
        assert!(profile_items
            .iter()
            .all(|item| item.outcome == Outcome::Rendered));
    }
    value["cards"][0]["title"] = json!("Updated reading");
    value["cards"][0]["content"] = json!("VA To");
    config(temp.path(), &value);
    let second = publish(&path, &output).unwrap();
    let second_manifest = manifest(&output, &second.active.variant_id);
    assert_eq!(
        first_manifest.variant.generation_sha256,
        second_manifest.variant.generation_sha256
    );
    assert_ne!(first.active.variant_id, second.active.variant_id);
    assert_eq!(
        second_manifest.families[0].sizes[0].items[0].label,
        "Updated reading"
    );
    assert_eq!(second_manifest.families[0].sizes[0].items[0].text, "VA To");
}

fn config(dir: &Path, value: &Value) -> PathBuf {
    let path = dir.join("config.json");
    fs::write(&path, serde_json::to_vec(value).unwrap()).unwrap();
    path
}

fn manifest(output: &Path, id: &str) -> Manifest {
    serde_json::from_slice(&fs::read(output.join(id).join("manifest.json")).unwrap()).unwrap()
}

fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[test]
fn exports_native_reference_pixels_and_separate_canonical_artifacts() {
    let temp = tempfile::tempdir().unwrap();
    let path = config(temp.path(), &fixture());
    let output = temp.path().join("output");
    let result = publish(&path, &output).unwrap();
    assert_eq!(
        (result.case_count, result.image_count, result.failure_count),
        (2, 2, 0)
    );
    let manifest = manifest(&output, &result.active.variant_id);
    validate_package(&output.join(&result.active.variant_id), &manifest).unwrap();
    let generation_bytes = fs::read(
        output
            .join("canonical")
            .join(format!("{}.json", manifest.variant.generation_sha256)),
    )
    .unwrap();
    assert_eq!(hash(&generation_bytes), manifest.variant.generation_sha256);
    assert!(!String::from_utf8_lossy(&generation_bytes).contains(temp.path().to_str().unwrap()));
    let generation: Value = serde_json::from_slice(&generation_bytes).unwrap();
    let composition_bytes = fs::read(
        output
            .join("canonical")
            .join(format!("{}.json", manifest.variant.composition_sha256)),
    )
    .unwrap();
    assert_eq!(
        hash(&composition_bytes),
        manifest.variant.composition_sha256
    );
    let composition: Value = serde_json::from_slice(&composition_bytes).unwrap();
    let loaded = load(&path).unwrap();
    let data = fs::read(&loaded.cases[0].font).unwrap();
    assert_eq!(
        serde_json::to_value(manifest.families[0].metadata.as_ref().unwrap()).unwrap(),
        serde_json::to_value(font_generator::metadata::extract(&data).unwrap()).unwrap()
    );
    let group = &manifest.families[0].sizes[0];
    for (index, item) in group.items.iter().enumerate() {
        let profile = loaded
            .config
            .profiles
            .iter()
            .find(|p| p.id == item.profile)
            .unwrap();
        let report = reference(
            &data,
            &ReferenceRequest {
                profile: item.profile.clone(),
                extensions: "none".into(),
                settings: Config {
                    characters: "AVTo".into(),
                    hinting: Hinting::Auto,
                    size_px: 14.0,
                    axes: group.axes.clone(),
                    output_bits: profile.output_bits,
                    mono_threshold: profile.mono_threshold,
                    gray_gamma: profile.gray_gamma,
                    ..Config::default()
                },
            },
        )
        .unwrap();
        assert_eq!(
            generation["cases"][index]["report"],
            serde_json::to_value(&report).unwrap()
        );
        assert_eq!(report.records.len(), 4);
        assert!(
            generation["cases"][index]["space"]["advance_26_6"]
                .as_i64()
                .unwrap()
                > 0
        );
        let image = item.image.as_ref().unwrap();
        let bytes = fs::read(output.join(&result.active.variant_id).join(&image.path)).unwrap();
        let mut reader = png::Decoder::new(Cursor::new(bytes)).read_info().unwrap();
        let mut actual = vec![0; reader.output_buffer_size().unwrap()];
        let info = reader.next_frame(&mut actual).unwrap();
        assert_eq!(
            (info.width, info.height),
            (group.thumbnail.width_px, group.thumbnail.height_px)
        );
        let layout = &composition["items"][index];
        let bounds = layout["group_bounds"].as_array().unwrap();
        let mut ink = vec![0_u8; actual.len()];
        for glyph in layout["layout"]["glyphs"].as_array().unwrap() {
            let cp = glyph["codepoint"].as_u64().unwrap() as u32;
            if cp == 32 {
                continue;
            }
            let record = report
                .records
                .iter()
                .find(|record| record.codepoint == cp)
                .unwrap();
            let left = glyph["x_px"].as_i64().unwrap() + i64::from(record.left)
                - bounds[0].as_i64().unwrap()
                + 8;
            let top = glyph["y_px"].as_i64().unwrap() + i64::from(record.top)
                - bounds[1].as_i64().unwrap()
                + 8;
            for y in 0..record.height {
                for x in 0..record.width {
                    let pos = (top as usize + y as usize) * info.width as usize
                        + left as usize
                        + x as usize;
                    ink[pos] = ink[pos]
                        .max(record.pixels[y as usize * record.width as usize + x as usize]);
                }
            }
        }
        let levels = (1_u16 << profile.output_bits) - 1;
        let expected: Vec<_> = ink
            .into_iter()
            .map(|q| 255 - ((u16::from(q) * 255 + levels / 2) / levels) as u8)
            .collect();
        assert_eq!(actual, expected);
    }
}

#[test]
fn repeats_reuse_immutable_packages_and_sample_edits_preserve_render_identity() {
    let temp = tempfile::tempdir().unwrap();
    let mut value = fixture();
    let path = config(temp.path(), &value);
    let output = temp.path().join("output");
    let first = publish(&path, &output).unwrap();
    let before = fs::read(output.join(&first.active.manifest)).unwrap();
    let mtime = fs::metadata(output.join(&first.active.manifest))
        .unwrap()
        .modified()
        .unwrap();
    let pointer_mtime = fs::metadata(output.join("active.json"))
        .unwrap()
        .modified()
        .unwrap();
    let repeated = publish(&path, &output).unwrap();
    assert_eq!(first.active.variant_id, repeated.active.variant_id);
    assert_eq!(
        mtime,
        fs::metadata(output.join(&first.active.manifest))
            .unwrap()
            .modified()
            .unwrap()
    );
    assert_eq!(
        pointer_mtime,
        fs::metadata(output.join("active.json"))
            .unwrap()
            .modified()
            .unwrap()
    );
    value["samples"][0]["text"] = json!("AV To");
    config(temp.path(), &value);
    let changed = publish(&path, &output).unwrap();
    assert_ne!(first.active.variant_id, changed.active.variant_id);
    assert_eq!(
        manifest(&output, &first.active.variant_id)
            .variant
            .generation_sha256,
        manifest(&output, &changed.active.variant_id)
            .variant
            .generation_sha256
    );
    assert_eq!(
        before,
        fs::read(output.join(&first.active.manifest)).unwrap()
    );
}

#[test]
fn invalid_inputs_leave_active_pointer_unchanged() {
    let temp = tempfile::tempdir().unwrap();
    let mut value = fixture();
    let path = config(temp.path(), &value);
    let output = temp.path().join("output");
    publish(&path, &output).unwrap();
    let before = fs::read(output.join("active.json")).unwrap();
    value["families"][0]["provenance"]["expected_sha256"] = json!("0".repeat(64));
    config(temp.path(), &value);
    assert!(publish(&path, &output)
        .unwrap_err()
        .to_string()
        .contains("checksum mismatch"));
    assert_eq!(before, fs::read(output.join("active.json")).unwrap());
    value = fixture();
    value["families"][0]["axes"]["wght"] = json!(100000);
    config(temp.path(), &value);
    assert!(publish(&path, &output).is_err());
    assert_eq!(before, fs::read(output.join("active.json")).unwrap());
}

#[test]
fn configured_variants_and_profile_subsets_publish_exact_selection() {
    let temp = tempfile::tempdir().unwrap();
    let mut value = fixture();
    // Exercise legacy roleless publication and retain its selection metadata.
    value["variants"][0]
        .as_object_mut()
        .unwrap()
        .remove("renderer");
    value["variants"].as_array_mut().unwrap().push(json!({"id": "reference-extra", "kind": "iteration", "version": "001.01", "hinting": "auto", "extensions": "none"}));
    value["defaults"]["variants"] = json!(["reference", "reference-extra"]);
    value["defaults"]["profiles"] = json!(["gray_3bit"]);
    let path = config(temp.path(), &value);
    let output = temp.path().join("output");
    let result = publish(&path, &output).unwrap();
    assert_eq!(result.packages.len(), 2);
    assert!(result.active.variant_id.starts_with("reference-extra-"));
    for id in &result.packages {
        let manifest = manifest(&output, id);
        assert!(manifest.variant.renderer.is_none());
        assert_eq!(manifest.profiles.len(), 1);
        assert_eq!(manifest.profiles[0].id, "gray_3bit");
        assert_eq!(manifest.families[0].sizes[0].items.len(), 1);
    }
}

#[test]
fn missing_glyphs_publish_explicit_failure_tiles() {
    let temp = tempfile::tempdir().unwrap();
    let mut value = fixture();
    value["characters"] = json!("\u{10ffff}");
    value["samples"][0]["text"] = json!("\u{10ffff}");
    let path = config(temp.path(), &value);
    let output = temp.path().join("output");
    let result = publish(&path, &output).unwrap();
    assert_eq!((result.image_count, result.failure_count), (0, 2));
    let manifest = manifest(&output, &result.active.variant_id);
    for item in &manifest.families[0].sizes[0].items {
        assert_eq!(item.outcome, Outcome::Failed);
        assert!(item.image.is_none());
        assert!(item.reason.as_ref().unwrap().contains("missing glyph"));
    }
    validate_package(&output.join(&result.active.variant_id), &manifest).unwrap();
}

#[test]
fn unsupported_samples_remain_explicit_manifest_items() {
    let temp = tempfile::tempdir().unwrap();
    let mut value = fixture();
    value["characters"] = json!("A\u{0301}");
    value["samples"][0]["text"] = json!("A\u{0301}");
    let path = config(temp.path(), &value);
    let output = temp.path().join("output");
    let result = publish(&path, &output).unwrap();
    assert_eq!((result.image_count, result.failure_count), (0, 2));
    let manifest = manifest(&output, &result.active.variant_id);
    for item in &manifest.families[0].sizes[0].items {
        assert_eq!(item.outcome, Outcome::Unsupported);
        assert!(item.image.is_none());
        assert!(!item.reason.as_ref().unwrap().is_empty());
    }
    validate_package(&output.join(&result.active.variant_id), &manifest).unwrap();
}

#[test]
fn damaged_existing_assets_block_publication() {
    let temp = tempfile::tempdir().unwrap();
    let path = config(temp.path(), &fixture());
    let output = temp.path().join("output");
    let first = publish(&path, &output).unwrap();
    let manifest = manifest(&output, &first.active.variant_id);
    let image = manifest.families[0].sizes[0].items[0]
        .image
        .as_ref()
        .unwrap();
    fs::write(
        output.join(&first.active.variant_id).join(&image.path),
        b"damaged",
    )
    .unwrap();
    let before = fs::read(output.join("active.json")).unwrap();
    assert!(publish(&path, &output).is_err());
    assert_eq!(before, fs::read(output.join("active.json")).unwrap());
}

#[test]
fn publication_lock_and_input_alias_are_protected() {
    let temp = tempfile::tempdir().unwrap();
    let path = config(temp.path(), &fixture());
    let output = temp.path().join("output");
    fs::create_dir_all(output.join(".publishing")).unwrap();
    assert!(publish(&path, &output)
        .unwrap_err()
        .to_string()
        .contains("locked"));
    assert!(!output.join("active.json").exists());
    let alias = temp.path().join("active.json");
    let bytes = serde_json::to_vec(&fixture()).unwrap();
    fs::write(&alias, &bytes).unwrap();
    assert!(publish(&alias, temp.path()).is_err());
    assert_eq!(bytes, fs::read(alias).unwrap());
}

#[cfg(unix)]
#[test]
fn symlinked_assets_are_rejected() {
    let temp = tempfile::tempdir().unwrap();
    let path = config(temp.path(), &fixture());
    let output = temp.path().join("output");
    let first = publish(&path, &output).unwrap();
    let manifest = manifest(&output, &first.active.variant_id);
    let image = manifest.families[0].sizes[0].items[0]
        .image
        .as_ref()
        .unwrap();
    let asset = output.join(&first.active.variant_id).join(&image.path);
    let external = temp.path().join("external.png");
    fs::rename(&asset, &external).unwrap();
    std::os::unix::fs::symlink(external, asset).unwrap();
    assert!(validate_package(&output.join(&first.active.variant_id), &manifest).is_err());
}

#[test]
fn reserved_slices_are_guarded_before_generation() {
    let temp = tempfile::tempdir().unwrap();
    let mut value: Value = serde_json::from_str(include_str!("../specimens.json")).unwrap();
    value.as_object_mut().unwrap().remove("preview_policy");
    let family = value["families"][2].clone();
    value["families"] = json!([family]);
    value["families"][0]["font"] =
        json!(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fonts/SourceSans3.ttf"));
    value["families"][0]["sizes"] = json!([15]);
    let path = config(temp.path(), &value);
    let output = temp.path().join("output");
    assert!(publish(&path, &output)
        .unwrap_err()
        .to_string()
        .contains("reserved evaluation slice"));
    assert!(!output.exists());
}

#[test]
fn cli_publishes_and_reports_errors() {
    let temp = tempfile::tempdir().unwrap();
    let path = config(temp.path(), &fixture());
    let output = temp.path().join("output");
    let result = Command::new(env!("CARGO_BIN_EXE_font_specimens"))
        .arg(&path)
        .arg(&output)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert!(output.join("active.json").is_file());
    let result = Command::new(env!("CARGO_BIN_EXE_font_specimens"))
        .arg(&path)
        .output()
        .unwrap();
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("usage:"));
}

#[test]
fn preview_policy_blocks_scope_drift_before_replacing_published_output() {
    let temp = tempfile::tempdir().unwrap();
    let mut value = fixture();
    value["preview_policy"] = json!("preview-policy.json");
    fs::write(
        temp.path().join("preview-policy.json"),
        serde_json::to_vec(&json!({
            "schema_version": "preview-policy-v1", "families": {"roboto": [14]}
        }))
        .unwrap(),
    )
    .unwrap();
    let path = config(temp.path(), &value);
    let output = temp.path().join("output");
    publish(&path, &output).unwrap();
    let active = fs::read(output.join("active.json")).unwrap();
    let published = fs::read(output.join("published.json")).unwrap();
    value["defaults"]["sizes"] = json!([14, 15]);
    config(temp.path(), &value);
    assert!(publish(&path, &output)
        .unwrap_err()
        .to_string()
        .contains("preview policy mismatch"));
    assert_eq!(active, fs::read(output.join("active.json")).unwrap());
    assert_eq!(published, fs::read(output.join("published.json")).unwrap());
    let absent = temp.path().join("unpublished");
    assert!(publish(&path, &absent).is_err());
    assert!(!absent.exists());
}
