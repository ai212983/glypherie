use font_generator::specimen_config::{load, SpecimenConfig};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{fs, path::Path};

fn document() -> Value {
    let mut value: Value = serde_json::from_str(include_str!("../specimens.json")).unwrap();
    value.as_object_mut().unwrap().remove("preview_policy");
    value.as_object_mut().unwrap().remove("cards");
    value["samples"] = json!([{ "id": "reading", "label": "Reading sample", "text": "A V" }]);
    value["variants"].as_array_mut().unwrap().truncate(1);
    // General selection fixtures exercise legacy manifests without role metadata;
    // explicit approval/candidate contracts have their own checked-in fixture.
    value["variants"][0]
        .as_object_mut()
        .unwrap()
        .remove("renderer");
    value["defaults"]["variants"] = json!(["reference"]);
    value["defaults"]["sizes"] = json!([14, 16, 18, 20]);
    value["families"][2]
        .as_object_mut()
        .unwrap()
        .remove("sizes");
    value
}

#[test]
fn cards_configure_titles_content_and_order_with_fixed_coverage() {
    let temp = tempfile::tempdir().unwrap();
    let mut value = document();
    value.as_object_mut().unwrap().remove("samples");
    value["characters"] = json!("!bA10b");
    value["cards"] = json!([
        {"id": "numbers", "title": "Dashboard", "content": "10!\n01"},
        {"id": "reading", "title": "Reading", "content": "Ab"}
    ]);
    let path = temp.path().join("specimens.json");
    fs::write(&path, serde_json::to_vec(&value).unwrap()).unwrap();
    let loaded = load(&path).unwrap();
    let samples = &loaded.config.samples;
    assert_eq!(
        samples.iter().map(|s| s.id.as_str()).collect::<Vec<_>>(),
        ["numbers", "reading", "coverage"]
    );
    assert_eq!(samples[0].label, "Dashboard");
    assert_eq!(samples[0].text, "10!\n01");
    assert_eq!(samples[2].label, "Character coverage");
    assert_eq!(samples[2].text, "A\nb\n10 !");

    value["cards"] = json!([]);
    fs::write(&path, serde_json::to_vec(&value).unwrap()).unwrap();
    assert_eq!(load(&path).unwrap().config.samples.len(), 1);
}

#[test]
fn cards_reject_invalid_content_duplicates_and_builtin_overrides() {
    for cards in [
        json!([{"id": "reading", "title": "Reading", "content": "☃"}]),
        json!([{"id": "reading", "title": "", "content": "A"}]),
        json!([{"id": "reading", "title": "Reading", "content": "\n "}]),
        json!([{"id": "coverage", "title": "Custom", "content": "A"}]),
        json!([{"id": "changed-symbols", "title": "Custom", "content": "A"}]),
        json!([{"id": "custom", "title": "Character coverage", "content": "A"}]),
        json!([{"id": "custom", "title": "Changed symbols", "content": "A"}]),
        json!([
            {"id": "reading", "title": "Reading", "content": "A"},
            {"id": "reading", "title": "Other", "content": "V"}
        ]),
    ] {
        let mut value = document();
        value.as_object_mut().unwrap().remove("samples");
        value["cards"] = cards;
        assert!(resolve(value).is_err());
    }
    let mut value = document();
    value["cards"] = json!([]);
    assert!(resolve(value)
        .unwrap_err()
        .contains("either cards or legacy samples"));
}

fn resolve(value: Value) -> Result<Vec<font_generator::specimen_config::RenderCase>, String> {
    let config: SpecimenConfig = serde_json::from_value(value).map_err(|e| e.to_string())?;
    config
        .resolve(Path::new("/config"))
        .map_err(|e| e.to_string())
}

#[test]
fn checked_in_config_resolves_reference_corpus_and_pinned_fonts() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    let loaded = load(&root.join("specimens.json")).unwrap();
    assert_eq!(loaded.cases.len(), 120);
    assert_eq!(
        loaded.config.preview_policy.as_deref(),
        Some(Path::new("preview-policy.json"))
    );
    for family in [
        "roboto",
        "roboto-italic",
        "roboto-flex",
        "literata",
        "source-sans-3",
    ] {
        let sizes: std::collections::BTreeSet<_> = loaded
            .cases
            .iter()
            .filter(|case| case.family_id == family)
            .map(|case| case.size_px.to_bits())
            .collect();
        assert_eq!(
            sizes,
            [14.0_f32, 16.0, 18.0, 20.0]
                .map(f32::to_bits)
                .into_iter()
                .collect()
        );
    }

    assert_eq!(
        loaded
            .cases
            .iter()
            .filter(|case| case.variant == "reference")
            .count(),
        40
    );
    assert_eq!(
        loaded
            .cases
            .iter()
            .filter(|case| case.variant == "iteration-02")
            .count(),
        40
    );
    assert_eq!(
        loaded
            .cases
            .iter()
            .filter(|case| case.variant == "iteration-03")
            .count(),
        40
    );
    assert_eq!(loaded.config.latest_variant().unwrap(), "iteration-03");
    assert_eq!(
        loaded
            .config
            .variants
            .iter()
            .map(|variant| variant.id.as_str())
            .collect::<Vec<_>>(),
        ["reference", "iteration-02", "iteration-03"]
    );
    assert_eq!(
        loaded.config.variants[1].version.as_deref(),
        Some(font_generator::baseline::VERSION)
    );
    assert_eq!(loaded.config.variants[1].extensions, "diagonal-01");
    assert_eq!(
        loaded.config.variants[1].renderer(),
        font_generator::renderer::RendererRole::Baseline
    );
    assert_eq!(loaded.config.variants[2].version.as_deref(), Some("001.03"));
    assert_eq!(
        loaded.config.variants[2].renderer(),
        font_generator::renderer::RendererRole::Candidate
    );
    for profile in &loaded.config.profiles {
        assert_eq!(profile.mono_threshold, 128);
        assert_eq!(profile.gray_gamma, 1.0);
    }
    for family in &loaded.config.families {
        let data = fs::read(root.join(&family.font)).unwrap();
        assert_eq!(
            format!("{:x}", Sha256::digest(data)),
            family.provenance.expected_sha256
        );
    }
    for case in loaded
        .cases
        .iter()
        .filter(|case| case.family_id == "literata")
    {
        assert_eq!(case.axes["opsz"], case.size_px);
        assert_eq!(case.axes["wght"], 400.0);
    }
}

#[test]
fn families_and_sizes_are_selected_from_config() {
    let mut value = document();
    value["families"].as_array_mut().unwrap().truncate(1);
    value["families"][0]["sizes"] = json!([18]);
    let cases = resolve(value).unwrap();
    assert_eq!(cases.len(), 2);
    assert!(cases
        .iter()
        .all(|case| case.family_id == "roboto" && case.size_px == 18.0));
}

#[test]
fn family_and_size_overrides_replace_inherited_selections() {
    let mut value = document();
    value["families"][0]["profiles"] = json!(["gray_3bit"]);
    value["families"][0]["sizes"] = json!([14, {"size_px": 20, "profiles": ["mono_1bit"]}]);
    let cases = resolve(value).unwrap();
    assert_eq!(cases.len(), 34);
    assert_eq!(cases[0].profile, "gray_3bit");
    assert_eq!(cases[0].size_px, 14.0);
    assert_eq!(cases[1].profile, "mono_1bit");
    assert_eq!(cases[1].size_px, 20.0);
    assert_eq!(cases[2].family_id, "literata");
}

#[test]
fn variants_can_be_selected_per_family_and_size() {
    let mut value = document();
    value["variants"].as_array_mut().unwrap().push(json!({
        "id": "candidate", "kind": "iteration", "version": "001.01",
        "hinting": "auto", "extensions": "none"
    }));
    value["families"][0]["variants"] = json!(["candidate"]);
    value["families"][0]["sizes"] = json!([14, {"size_px": 16, "variants": ["reference"]}]);
    let cases = resolve(value).unwrap();
    assert_eq!(cases.len(), 36);
    assert_eq!(
        cases
            .iter()
            .filter(|case| case.variant == "candidate")
            .count(),
        2
    );
    assert!(cases
        .iter()
        .filter(|case| case.variant == "candidate")
        .all(|case| case.family_id == "roboto" && case.size_px == 14.0));
}

#[test]
fn adding_a_family_requires_only_config_data() {
    let mut value = document();
    let mut family = value["families"][0].clone();
    family["id"] = json!("another-family");
    family["name"] = json!("Another family");
    family["sizes"] = json!([16]);
    value["families"].as_array_mut().unwrap().push(family);
    let cases = resolve(value).unwrap();
    assert_eq!(cases.len(), 42);
    assert_eq!(cases[40].family_id, "another-family");
}

#[test]
fn unknown_and_duplicate_selections_are_rejected() {
    for selection in [
        json!([]),
        json!(["missing"]),
        json!(["mono_1bit", "mono_1bit"]),
    ] {
        let mut value = document();
        value["families"][0]["profiles"] = selection;
        assert!(resolve(value).is_err());
    }
    let mut value = document();
    value["families"][0]["sizes"] = json!([{ "size_px": 14, "variants": ["missing"] }]);
    assert!(resolve(value).unwrap_err().contains("unknown variant"));
}

#[test]
fn duplicate_definitions_and_unsafe_ids_are_rejected() {
    let mut value = document();
    value["families"][1]["id"] = json!("roboto");
    assert!(resolve(value).is_err());
    let mut value = document();
    value["variants"][0]["id"] = json!("../reference");
    assert!(resolve(value).is_err());
    let mut value = document();
    let profile = value["profiles"][0].clone();
    value["profiles"].as_array_mut().unwrap().push(profile);
    assert!(resolve(value).is_err());
}

#[test]
fn invalid_sizes_and_empty_selections_are_rejected() {
    for sizes in [
        json!([]),
        json!([0]),
        json!([513]),
        json!([14, {"size_px": 14}]),
    ] {
        let mut value = document();
        value["families"][0]["sizes"] = sizes;
        assert!(resolve(value).is_err());
    }
    let mut value = document();
    value["families"] = json!([]);
    assert!(resolve(value).is_err());
}

#[test]
fn unknown_fields_and_axis_expressions_are_rejected() {
    let mut value = document();
    value["families"][0]["sizez"] = json!([14]);
    assert!(resolve(value).is_err());
    let mut value = document();
    value["families"][0]["axes"]["wght"] = json!("size_px * 2");
    assert!(resolve(value).is_err());
    let mut value = document();
    value["families"][0]["sizes"] = json!([{ "size_px": 14, "profile": "mono_1bit" }]);
    assert!(resolve(value).is_err());
}

#[test]
fn profile_and_variant_settings_are_checked() {
    let mut value = document();
    value["profiles"][0]["output_bits"] = json!(3);
    assert!(resolve(value).is_err());
    let mut value = document();
    value["profiles"][1]["gray_gamma"] = json!(0);
    assert!(resolve(value).is_err());
    let mut value = document();
    value["variants"][0]["hinting"] = json!("auto_fallback");
    assert!(resolve(value).is_err());
    let mut value = document();
    value["variants"][0]["extensions"] = json!("custom");
    assert!(resolve(value).is_err());
    let mut value = document();
    value["variants"][0]["version"] = json!("001.01");
    assert!(resolve(value).is_err());
}

#[test]
fn samples_require_unique_ids_and_declared_drawable_characters() {
    for characters in [json!(""), json!("A "), json!("A\t")] {
        let mut value = document();
        value["characters"] = characters;
        assert!(resolve(value).is_err());
    }
    for samples in [
        json!([]),
        json!([{"id": "text", "label": "Text", "text": "☃"}]),
        json!([{"id": "text", "label": "", "text": "A"}]),
        json!([{"id": "text", "label": "Text", "text": "\n "}]),
        json!([
            {"id": "text", "label": "Text", "text": "A"},
            {"id": "text", "label": "Other", "text": "V"}
        ]),
    ] {
        let mut value = document();
        value["samples"] = samples;
        assert!(resolve(value).is_err());
    }
    let mut value = document();
    value["characters"] = json!("AV");
    value["samples"] = json!([{"id": "text", "label": "Text", "text": "A V\nVA"}]);
    assert!(resolve(value).is_ok());
}

#[test]
fn latest_variant_must_have_cases_and_versions_must_be_numeric_unique() {
    let mut value = document();
    value["variants"].as_array_mut().unwrap().push(json!({
        "id": "unused", "kind": "iteration", "version": "001.02",
        "hinting": "auto", "extensions": "none"
    }));
    assert!(resolve(value.clone())
        .unwrap_err()
        .contains("at least one render case"));
    value["variants"][1]["version"] = json!("iteration-1");
    assert!(resolve(value.clone()).unwrap_err().contains("numeric"));
    value["variants"][1]["version"] = json!("001.02");
    let duplicate = value["variants"][1].clone();
    value["variants"].as_array_mut().unwrap().push(duplicate);
    value["variants"][2]["id"] = json!("duplicate");
    assert!(resolve(value).unwrap_err().contains("duplicate revision"));
}

#[test]
fn latest_previous_revision_cannot_be_silently_replaced_by_reference() {
    let mut value = document();
    for (id, version) in [("baseline", "001.02"), ("current", "002.01")] {
        value["variants"].as_array_mut().unwrap().push(json!({
            "id": id, "kind": "iteration", "version": version,
            "hinting": "auto", "extensions": "none"
        }));
    }
    value["defaults"]["variants"] = json!(["reference", "current"]);
    assert!(resolve(value).unwrap_err().contains("comparison baseline"));
}

#[test]
fn preview_policy_rejects_effective_matrix_drift_in_defaults_and_overrides() {
    let temp = tempfile::tempdir().unwrap();
    fs::write(
        temp.path().join("preview-policy.json"),
        include_bytes!("../preview-policy.json"),
    )
    .unwrap();
    let original: Value = serde_json::from_str(include_str!("../specimens.json")).unwrap();
    let path = temp.path().join("specimens.json");
    for edit in 0..6 {
        let mut value = original.clone();
        match edit {
            0 => value["defaults"]["sizes"] = json!([14, 15, 16, 18, 20]),
            1 => value["families"][0]["sizes"] = json!([14, 16, 17, 18, 20]),
            2 => value["families"][1]["sizes"] = json!([14, 16, 20]),
            3 => {
                value["defaults"]["sizes"] = json!([
                    14, 16, 18, 20, {"size_px": 19, "variants": ["iteration-02"], "profiles": ["mono_1bit"]}
                ])
            }
            // Aggregate family sizes remain unchanged; the latest variant loses 18 px.
            4 => {
                value["defaults"]["sizes"] = json!([
                    14, 16, {"size_px": 18, "variants": ["reference"]}, 20
                ])
            }
            5 => {
                value["families"].as_array_mut().unwrap().pop();
            }
            _ => unreachable!(),
        }
        fs::write(&path, serde_json::to_vec(&value).unwrap()).unwrap();
        let error = load(&path).unwrap_err().to_string();
        assert!(
            error.contains("preview policy mismatch"),
            "mutation {edit}: {error}"
        );
    }
}

#[test]
fn missing_or_invalid_preview_policy_is_an_error_and_diagnostics_stay_independent() {
    let temp = tempfile::tempdir().unwrap();
    let value: Value = serde_json::from_str(include_str!("../specimens.json")).unwrap();
    let path = temp.path().join("specimens.json");
    fs::write(&path, serde_json::to_vec(&value).unwrap()).unwrap();
    assert!(load(&path)
        .unwrap_err()
        .to_string()
        .contains("cannot read preview policy"));
    let mut policy: Value = serde_json::from_str(include_str!("../preview-policy.json")).unwrap();
    for invalid in [
        json!([]),
        json!([14, 14, 16, 18, 20]),
        json!([0, 16, 18, 20]),
    ] {
        policy["families"]["roboto"] = invalid;
        fs::write(
            temp.path().join("preview-policy.json"),
            serde_json::to_vec(&policy).unwrap(),
        )
        .unwrap();
        assert!(load(&path)
            .unwrap_err()
            .to_string()
            .contains("invalid preview policy sizes"));
    }
    // A temporary diagnostic selection can exercise intermediate sizes independently.
    let mut diagnostic = document();
    diagnostic["families"].as_array_mut().unwrap().truncate(1);
    diagnostic["defaults"]["sizes"] = json!([14, 15, 16, 17, 18, 19, 20]);
    fs::write(&path, serde_json::to_vec(&diagnostic).unwrap()).unwrap();
    assert_eq!(load(&path).unwrap().cases.len(), 14);
}

#[test]
fn stable_renderer_roles_distinguish_approval_from_working_version_metadata() {
    let mut current: Value = serde_json::from_str(include_str!("../specimens.json")).unwrap();
    // Resolve role validation independently of the filesystem preview-policy
    // fixture; matrix protection is exercised separately with actual files.
    current.as_object_mut().unwrap().remove("preview_policy");
    assert!(resolve(current.clone()).is_ok());
    assert_eq!(current["variants"][0]["renderer"], "reference");
    assert_eq!(current["variants"][1]["renderer"], "baseline");
    for field in ["version", "extensions", "renderer"] {
        let mut invalid = current.clone();
        invalid["variants"][1][field] = json!(match field {
            "version" => "100.500",
            "extensions" => "none",
            _ => "reference",
        });
        assert!(resolve(invalid).is_err(), "baseline drift: {field}");
    }
    let mut working = current.clone();
    let mut candidate = current["variants"][1].clone();
    candidate["id"] = json!("working");
    candidate["renderer"] = json!("candidate");
    candidate["version"] = json!("100.500");
    working["variants"].as_array_mut().unwrap().push(candidate);
    working["defaults"]["variants"] = json!([current["variants"][1]["id"], "working"]);
    assert!(resolve(working).is_ok());
    current["variants"][1]["renderer"] = json!("candidate");
    assert!(resolve(current).unwrap_err().contains("approved baseline"));
}
