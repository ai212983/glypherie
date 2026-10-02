use font_generator::{
    batch::{rasterize_batch, BatchCaseInput, BatchJob, BatchSettings, RawCommand},
    generate,
    probe::{lock_sha256, probe, rasterize, skrifa_checksum, skrifa_version, zeno_version},
    reference::{
        reference, ReferenceRequest, EXTENSIONS_NONE, IMPLEMENTATION_UPSTREAM, PROFILE_GRAY_3BIT,
        PROFILE_MONO_1BIT,
    },
    Config, Hinting,
};
use std::{fs, path::PathBuf, process::Command};

const CFF: &[u8] = include_bytes!("fixtures/static-cff.otf");
const CFF2: &[u8] = include_bytes!("fixtures/variable-cff2.otf");
const SKRIFA_REGISTRY_CHECKSUM: &str =
    "d4febebda507fb889c545a37a135517769d1391941013561292897961d1887d6";

fn roboto() -> Vec<u8> {
    fs::read(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../fonts/Roboto.ttf")).unwrap()
}

fn request(profile: &str, hinting: Hinting, characters: &str) -> ReferenceRequest {
    ReferenceRequest {
        profile: profile.to_string(),
        extensions: String::from("none"),
        settings: Config {
            size_px: 20.0,
            characters: characters.to_string(),
            hinting,
            output_bits: if profile == PROFILE_MONO_1BIT { 1 } else { 3 },
            ..Config::default()
        },
    }
}

fn mode_name(hinting: Hinting) -> &'static str {
    match hinting {
        Hinting::Auto => "auto",
        Hinting::Interpreter => "interpreter",
        Hinting::None => "none",
        Hinting::AutoFallback => "auto_fallback",
    }
}

fn check_identity(report: &font_generator::reference::ReferenceReport) {
    assert_eq!(report.skrifa_version, "0.46.2");
    assert_eq!(report.skrifa_version, skrifa_version());
    assert_eq!(report.skrifa_registry_checksum, SKRIFA_REGISTRY_CHECKSUM);
    assert_eq!(report.skrifa_registry_checksum, skrifa_checksum());
    assert_eq!(report.zeno_version, "0.3.3");
    assert_eq!(report.zeno_version, zeno_version());
    assert_eq!(report.dependency_lock_sha256, lock_sha256());
    assert_eq!(report.implementation, IMPLEMENTATION_UPSTREAM);
    assert_eq!(report.implementation, "upstream");
    assert!(!report.fork);
    assert!(!report.draw_pedantic);
}

#[test]
fn reference_renders_cff_cff2_and_variable_glyf_under_both_profiles_and_modes() {
    let variable = roboto();
    let inputs: Vec<(&[u8], bool)> = vec![(CFF, false), (CFF2, false), (&variable, true)];
    for (data, variable_axes) in inputs {
        for profile in [PROFILE_MONO_1BIT, PROFILE_GRAY_3BIT] {
            for hinting in [Hinting::Auto, Hinting::Interpreter, Hinting::None] {
                let mut req = request(profile, hinting, "A");
                if variable_axes {
                    req.settings.axes.insert("wght".into(), 400.0);
                }
                let report = reference(data, &req).unwrap();
                assert_eq!(report.profile, profile);
                assert_eq!(report.extensions, EXTENSIONS_NONE);
                assert_eq!(report.hinting_requested, mode_name(hinting));
                assert_eq!(report.size_px, 20.0);
                assert_eq!(report.records.len(), 1);
                let record = &report.records[0];
                assert_eq!(record.codepoint, 65);
                assert_eq!(record.selected_engine, mode_name(hinting));
                assert_eq!(record.output_bits, req.settings.output_bits);
                assert_eq!(record.mono_threshold, req.settings.mono_threshold);
                assert_eq!(record.gray_gamma, req.settings.gray_gamma);
                assert!(!record.fitted_commands.is_empty());
                assert_eq!(record.pixels.len(), (record.width * record.height) as usize);
                assert_eq!(
                    record.coverage.len(),
                    (record.width * record.height) as usize
                );
                assert_eq!(record.coverage.len(), record.pixels.len());
                assert!(!record.pixels.is_empty());
                assert!(record.advance_26_6 > 0);
                assert_eq!(record.skrifa_registry_checksum, SKRIFA_REGISTRY_CHECKSUM);
                assert!(!record.draw_pedantic);
                use sha2::{Digest, Sha256};
                assert_eq!(
                    record.coverage_sha256,
                    format!("{:x}", Sha256::digest(&record.coverage))
                );
                if profile == PROFILE_MONO_1BIT {
                    assert_eq!(report.target, "mono");
                    assert_eq!(record.target, "mono");
                    assert_eq!(report.smooth_mode, None);
                    assert_eq!(record.smooth_mode, None);
                    assert_eq!(report.symmetric_rendering, None);
                    assert_eq!(record.preserve_linear_metrics, None);
                    assert!(record.pixels.iter().all(|&p| p <= 1));
                } else {
                    assert_eq!(report.target, "smooth");
                    assert_eq!(record.target, "smooth");
                    assert_eq!(report.smooth_mode, Some(String::from("normal")));
                    assert_eq!(record.smooth_mode, Some(String::from("normal")));
                    assert_eq!(report.symmetric_rendering, Some(true));
                    assert_eq!(report.preserve_linear_metrics, Some(false));
                    assert_eq!(record.symmetric_rendering, Some(true));
                    assert_eq!(record.preserve_linear_metrics, Some(false));
                    assert!(record.pixels.iter().all(|&p| p <= 7));
                }
                assert!(report.metrics.ascent_26_6 > 0);
                assert!(report.metrics.descent_26_6 < 0);
                check_identity(&report);
                let value = serde_json::to_value(&report).unwrap();
                assert_eq!(
                    value["records"][0]["coverage"].as_array().unwrap().len(),
                    record.coverage.len()
                );
                assert!(
                    value["records"][0]["fitted_commands"]
                        .as_array()
                        .unwrap()
                        .len()
                        > 0
                );
            }
        }
    }
}

#[test]
fn mono_reference_matches_probe_and_generate() {
    for hinting in [Hinting::Auto, Hinting::Interpreter, Hinting::None] {
        let req = request(PROFILE_MONO_1BIT, hinting, "A");
        let report = reference(CFF, &req).unwrap();
        if hinting != Hinting::None {
            let probed = probe(CFF, &req.settings).unwrap();
            assert_eq!(report.records.len(), probed.records.len());
            for (record, mono) in report.records.iter().zip(probed.records.iter()) {
                assert_eq!(record.codepoint, mono.codepoint);
                assert_eq!(record.glyph_id, mono.glyph_id);
                assert_eq!(record.pixels, mono.pixels);
                assert_eq!(
                    (record.left, record.top, record.width, record.height),
                    (mono.left, mono.top, mono.width, mono.height)
                );
                assert_eq!(record.advance_26_6, mono.advance_26_6);
                assert_eq!(record.fitted_commands, mono.fitted_commands);
                assert_eq!(record.selected_engine, mono.selected_engine);
            }
            assert_eq!(report.source_sha256, probed.source_sha256);
            assert_eq!(report.metrics, probed.metrics);
        }
        let generated = generate(CFF, &req.settings).unwrap();
        assert_eq!(report.records.len(), generated.glyphs.len());
        for (record, glyph) in report.records.iter().zip(generated.glyphs.iter()) {
            assert_eq!(record.pixels, glyph.pixels);
            assert_eq!(
                (record.left, record.top, record.width, record.height),
                (glyph.left, glyph.top, glyph.width, glyph.height)
            );
            assert_eq!(record.advance_26_6, glyph.advance_26_6);
        }
    }
}

#[test]
fn gray_reference_matches_upstream_normal_target() {
    use font_generator::probe::FittedPen;
    use skrifa::{
        instance::Size,
        outline::{DrawSettings, Engine, HintingInstance, HintingOptions, SmoothMode, Target},
        FontRef, MetadataProvider,
    };

    let variable = roboto();
    for (data, characters) in [
        (CFF, "A"),
        (CFF2, "A"),
        (variable.as_slice(), "AHIMVWXwxyz"),
    ] {
        for ppem in [14.0, 16.0] {
            for mode in [Hinting::Auto, Hinting::Interpreter, Hinting::None] {
                let mut req = request(PROFILE_GRAY_3BIT, mode, characters);
                req.settings.size_px = ppem;
                let report = reference(data, &req).unwrap();
                let font = FontRef::new(data).unwrap();
                let location = font.axes().location([] as [(&str, f32); 0]);
                let size = Size::new(ppem);
                let outlines = font.outline_glyphs();
                let target: Target = SmoothMode::Normal.into();
                assert_eq!(
                    target,
                    Target::Smooth {
                        mode: SmoothMode::Normal,
                        symmetric_rendering: true,
                        preserve_linear_metrics: false,
                    }
                );
                let engine = match mode {
                    Hinting::Auto => Some(Engine::Auto(None)),
                    Hinting::Interpreter => Some(Engine::Interpreter),
                    Hinting::None => None,
                    Hinting::AutoFallback => unreachable!(),
                };
                let hint = engine.map(|engine| {
                    HintingInstance::new(
                        &outlines,
                        size,
                        &location,
                        HintingOptions { engine, target },
                    )
                    .unwrap()
                });
                for record in &report.records {
                    let gid = font
                        .charmap()
                        .map(char::from_u32(record.codepoint).unwrap())
                        .unwrap();
                    let mut pen = FittedPen::default();
                    let draw = match &hint {
                        Some(h) => DrawSettings::hinted(h, false),
                        None => DrawSettings::unhinted(size, &location),
                    };
                    outlines.get(gid).unwrap().draw(draw, &mut pen).unwrap();
                    assert_eq!(record.fitted_commands, pen.commands());
                    let expected = rasterize(pen.commands(), &req.settings).unwrap();
                    assert_eq!(record.coverage, expected.coverage);
                    assert_eq!(record.pixels, expected.pixels);
                    assert_eq!(
                        (record.left, record.top, record.width, record.height),
                        (expected.left, expected.top, expected.width, expected.height)
                    );
                }
            }
        }
    }
}

#[test]
fn coverage_quantization_matches_declared_policy() {
    let variable = roboto();
    let mut mono = request(PROFILE_MONO_1BIT, Hinting::Auto, "A");
    mono.settings.axes.insert("wght".into(), 400.0);
    mono.settings.mono_threshold = 96;
    let report = reference(&variable, &mono).unwrap();
    let record = &report.records[0];
    assert!(record.coverage.iter().any(|&c| c != 0 && c != 255));
    for (pixel, coverage) in record.pixels.iter().zip(record.coverage.iter()) {
        assert_eq!(*pixel, u8::from(*coverage >= 96));
    }
    mono.settings.mono_threshold = 128;
    let nearest = reference(&variable, &mono).unwrap();
    assert_eq!(record.coverage, nearest.records[0].coverage);
    for (pixel, coverage) in nearest.records[0].pixels.iter().zip(&record.coverage) {
        assert_eq!(*pixel, u8::from(*coverage >= 128));
    }
    let mut linear = request(PROFILE_GRAY_3BIT, Hinting::Auto, "A");
    linear.settings.axes.insert("wght".into(), 400.0);
    linear.settings.gray_gamma = 1.0;
    let linear_report = reference(&variable, &linear).unwrap();
    let linear_record = &linear_report.records[0];
    assert!(linear_record.pixels.iter().all(|&p| p <= 7));
    assert!(linear_record.pixels.iter().any(|&p| p != 0 && p != 7));
    for (pixel, coverage) in linear_record
        .pixels
        .iter()
        .zip(linear_record.coverage.iter())
    {
        let expected = ((*coverage as f32 / 255.0) * 7.0).round() as u8;
        assert_eq!(*pixel, expected);
    }
    let mut adjusted = linear.clone();
    adjusted.settings.gray_gamma = 2.0;
    let adjusted_report = reference(&variable, &adjusted).unwrap();
    let adjusted_record = &adjusted_report.records[0];
    for (pixel, coverage) in adjusted_record
        .pixels
        .iter()
        .zip(adjusted_record.coverage.iter())
    {
        let expected = ((*coverage as f32 / 255.0).powf(2.0) * 7.0).round() as u8;
        assert_eq!(*pixel, expected);
    }
    assert_ne!(linear_record.pixels, adjusted_record.pixels);
    assert_eq!(linear_record.coverage, adjusted_record.coverage);
}

#[test]
fn reference_rejects_malformed_requests_and_extensions() {
    let mut bad_profile = request(PROFILE_MONO_1BIT, Hinting::Auto, "A");
    bad_profile.profile = String::from("gray_8bit");
    assert!(reference(CFF, &bad_profile).is_err());
    bad_profile.profile.clear();
    assert!(reference(CFF, &bad_profile).is_err());
    for (profile, bits) in [
        (PROFILE_MONO_1BIT, 3u8),
        (PROFILE_MONO_1BIT, 2u8),
        (PROFILE_GRAY_3BIT, 1u8),
        (PROFILE_GRAY_3BIT, 8u8),
    ] {
        let mut req = request(profile, Hinting::Auto, "A");
        req.settings.output_bits = bits;
        assert!(reference(CFF, &req).is_err(), "{profile}/{bits}");
    }
    for extensions in ["enhanced", "", "none ", "NONE", "v1"] {
        let mut req = request(PROFILE_MONO_1BIT, Hinting::Auto, "A");
        req.extensions = extensions.to_string();
        let error = reference(CFF, &req).unwrap_err().to_string();
        assert!(error.contains("extensions"), "{extensions}: {error}");
    }
    for profile in [PROFILE_MONO_1BIT, PROFILE_GRAY_3BIT] {
        let req = request(profile, Hinting::AutoFallback, "A");
        let error = reference(CFF, &req).unwrap_err().to_string();
        assert!(error.contains("explicit"), "{profile}: {error}");
    }
    for gamma in [0.0f32, -1.0, f32::NAN, f32::INFINITY] {
        let mut req = request(PROFILE_GRAY_3BIT, Hinting::Auto, "A");
        req.settings.gray_gamma = gamma;
        assert!(reference(CFF, &req).is_err(), "gamma {gamma}");
    }
    let mut empty = request(PROFILE_MONO_1BIT, Hinting::Auto, "");
    assert!(reference(CFF, &empty).is_err());
    empty.settings.characters = "A".to_string();
    empty.settings.size_px = 0.0;
    assert!(reference(CFF, &empty).is_err());
    assert!(reference(b"", &request(PROFILE_MONO_1BIT, Hinting::Auto, "A")).is_err());
    assert!(reference(
        b"404: Not Found",
        &request(PROFILE_MONO_1BIT, Hinting::Auto, "A")
    )
    .is_err());
    let variable = roboto();
    let mut axis = request(PROFILE_GRAY_3BIT, Hinting::Auto, "A");
    axis.settings.axes.insert("wght".into(), 1000.0);
    assert!(reference(&variable, &axis).is_err());
    axis.settings.axes.insert("wght".into(), 400.0);
    axis.settings.axes.insert("XXXX".into(), 1.0);
    assert!(reference(&variable, &axis).is_err());
    let omitted: ReferenceRequest = serde_json::from_value(serde_json::json!({
        "profile": "mono_1bit",
        "settings": {"size_px": 20.0, "characters": "A", "hinting": "auto", "output_bits": 1}
    }))
    .unwrap();
    assert_eq!(omitted.extensions, "none");
    assert!(reference(CFF, &omitted).is_ok());
    let unknown: Result<ReferenceRequest, _> = serde_json::from_value(serde_json::json!({
        "profile": "mono_1bit",
        "extensions": "none",
        "settings": {"size_px": 20.0, "characters": "A", "hinting": "auto", "output_bits": 1},
        "extra": 1
    }));
    assert!(unknown.is_err());
    let missing: Result<ReferenceRequest, _> = serde_json::from_value(serde_json::json!({
        "extensions": "none",
        "settings": {"size_px": 20.0, "characters": "A", "hinting": "auto", "output_bits": 1}
    }));
    assert!(missing.is_err());
}

#[test]
fn reference_is_deterministic_and_honors_variation_axes() {
    let variable = roboto();
    let mut req = request(PROFILE_GRAY_3BIT, Hinting::Auto, "AHm");
    req.settings.axes.insert("wght".into(), 400.0);
    let first = serde_json::to_vec(&reference(&variable, &req).unwrap()).unwrap();
    let second = serde_json::to_vec(&reference(&variable, &req).unwrap()).unwrap();
    assert_eq!(first, second);
    let mut mono = request(PROFILE_MONO_1BIT, Hinting::Interpreter, "AHm");
    mono.settings.axes.insert("wght".into(), 400.0);
    let a = serde_json::to_vec(&reference(&variable, &mono).unwrap()).unwrap();
    let b = serde_json::to_vec(&reference(&variable, &mono).unwrap()).unwrap();
    assert_eq!(a, b);
    let mut thin = request(PROFILE_GRAY_3BIT, Hinting::Auto, "Hm");
    thin.settings.axes.insert("wght".into(), 100.0);
    let mut heavy = thin.clone();
    heavy.settings.axes.insert("wght".into(), 900.0);
    let thin_report = reference(&variable, &thin).unwrap();
    let heavy_report = reference(&variable, &heavy).unwrap();
    assert_ne!(
        serde_json::to_vec(&thin_report.records).unwrap(),
        serde_json::to_vec(&heavy_report.records).unwrap()
    );
    let mut cff2_thin = request(PROFILE_MONO_1BIT, Hinting::Auto, "A");
    cff2_thin.settings.axes.insert("wght".into(), 100.0);
    let mut cff2_heavy = request(PROFILE_MONO_1BIT, Hinting::Auto, "A");
    cff2_heavy.settings.axes.insert("wght".into(), 900.0);
    let thin_cff2 = reference(CFF2, &cff2_thin).unwrap();
    let heavy_cff2 = reference(CFF2, &cff2_heavy).unwrap();
    assert_ne!(thin_cff2.records[0].pixels, heavy_cff2.records[0].pixels);
    assert!(reference(CFF, &cff2_thin).is_err());
}

fn rect_commands() -> Vec<RawCommand> {
    for_coord(vec![(128, 64), (384, 64), (384, 320), (128, 320)])
}

fn for_coord(points: Vec<(i32, i32)>) -> Vec<RawCommand> {
    let mut commands = vec![RawCommand {
        op: String::from("move"),
        coords: vec![points[0].0, points[0].1],
    }];
    for (x, y) in points.into_iter().skip(1) {
        commands.push(RawCommand {
            op: String::from("line"),
            coords: vec![x, y],
        });
    }
    commands.push(RawCommand {
        op: String::from("close"),
        coords: vec![],
    });
    commands
}

#[test]
fn batch_supports_gray_3bit_with_coverage_and_keeps_mono_stable() {
    let gray = BatchJob {
        settings: BatchSettings {
            output_bits: 3,
            mono_threshold: 128,
            gray_gamma: 1.0,
        },
        cases: vec![
            BatchCaseInput {
                key: String::from("b"),
                commands: rect_commands(),
            },
            BatchCaseInput {
                key: String::from("a"),
                commands: rect_commands(),
            },
        ],
    };
    let output = rasterize_batch(&gray).unwrap();
    assert_eq!(output.output_bits, 3);
    let keys: Vec<&str> = output.cases.iter().map(|c| c.key.as_str()).collect();
    assert_eq!(keys, vec!["a", "b"]);
    for case in &output.cases {
        assert_eq!(
            (case.left, case.top, case.width, case.height),
            (2, -5, 4, 4)
        );
        assert_eq!(case.pixels.len(), 16);
        assert_eq!(case.coverage.len(), 16);
        assert!(case.pixels.iter().all(|&p| p == 7));
        assert!(case.coverage.iter().all(|&c| c == 255));
    }
    let fitted = font_generator::batch::to_fitted(&rect_commands()).unwrap();
    let direct = rasterize(
        &fitted,
        &Config {
            output_bits: 3,
            mono_threshold: 128,
            gray_gamma: 1.0,
            ..Config::default()
        },
    )
    .unwrap();
    assert_eq!(output.cases[0].pixels, direct.pixels);
    assert_eq!(output.cases[0].coverage, direct.coverage);
    let mono = BatchJob {
        settings: BatchSettings {
            output_bits: 1,
            mono_threshold: 128,
            gray_gamma: 1.0,
        },
        cases: vec![BatchCaseInput {
            key: String::from("rect"),
            commands: rect_commands(),
        }],
    };
    let mono_output = rasterize_batch(&mono).unwrap();
    assert!(mono_output.cases[0].pixels.iter().all(|&p| p == 1));
    assert!(mono_output.cases[0].coverage.iter().all(|&c| c == 255));
    assert_eq!(mono_output.cases[0].pixels.len(), 16);
    for bits in [2u8, 4, 8] {
        let rejected = BatchJob {
            settings: BatchSettings {
                output_bits: bits,
                mono_threshold: 128,
                gray_gamma: 1.0,
            },
            cases: vec![BatchCaseInput {
                key: String::from("a"),
                commands: rect_commands(),
            }],
        };
        assert!(rasterize_batch(&rejected).is_err(), "bits {bits}");
    }
}

fn scratch(name: &str) -> PathBuf {
    let path = std::env::temp_dir().join(format!("font-reference-{}-{name}", std::process::id()));
    fs::create_dir_all(&path).unwrap();
    path
}

fn checksum(data: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    format!("{:x}", Sha256::digest(data))
}

fn reference_job(profile: &str, hinting: &str, bits: u8, checksum: &str) -> serde_json::Value {
    serde_json::json!({
        "font": "font.otf",
        "provenance": {"source": "repository fixture", "license": "unknown", "expected_sha256": checksum},
        "profile": profile,
        "settings": {"size_px": 20.0, "characters": "A", "hinting": hinting, "output_bits": bits}
    })
}

#[test]
fn reference_binary_emits_schema_v2_and_honors_protections() {
    let binary = env!("CARGO_BIN_EXE_font_reference");
    let temp = scratch("schema");
    fs::write(temp.join("font.otf"), CFF).unwrap();
    let digest = checksum(CFF);
    let job_path = temp.join("job.json");
    let output_path = temp.join("output.json");
    let second_path = temp.join("second.json");
    fs::write(
        &job_path,
        serde_json::to_vec(&reference_job(PROFILE_MONO_1BIT, "auto", 1, &digest)).unwrap(),
    )
    .unwrap();
    let result = Command::new(binary)
        .arg(&job_path)
        .arg(&output_path)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let artifact: serde_json::Value =
        serde_json::from_slice(&fs::read(&output_path).unwrap()).unwrap();
    assert_eq!(artifact["schema_version"], serde_json::Value::from(2u64));
    assert!(!artifact["generator_version"].as_str().unwrap().is_empty());
    assert_eq!(
        artifact["dependency_lock_sha256"],
        serde_json::Value::String(lock_sha256())
    );
    assert_eq!(
        artifact["provenance"]["expected_sha256"],
        serde_json::Value::String(digest.clone())
    );
    assert_eq!(
        artifact["generated"]["profile"],
        serde_json::Value::String(String::from("mono_1bit"))
    );
    assert_eq!(
        artifact["generated"]["extensions"],
        serde_json::Value::String(String::from("none"))
    );
    assert_eq!(
        artifact["generated"]["hinting_requested"],
        serde_json::Value::String(String::from("auto"))
    );
    assert_eq!(
        artifact["generated"]["target"],
        serde_json::Value::String(String::from("mono"))
    );
    assert_eq!(
        artifact["generated"]["implementation"],
        serde_json::Value::String(String::from("upstream"))
    );
    assert_eq!(
        artifact["generated"]["fork"],
        serde_json::Value::Bool(false)
    );
    assert_eq!(
        artifact["generated"]["skrifa_registry_checksum"],
        serde_json::Value::String(String::from(SKRIFA_REGISTRY_CHECKSUM))
    );
    let record = &artifact["generated"]["records"][0];
    assert_eq!(
        record["selected_engine"],
        serde_json::Value::String(String::from("auto"))
    );
    assert_eq!(
        record["target"],
        serde_json::Value::String(String::from("mono"))
    );
    assert!(record["coverage"].as_array().unwrap().len() > 0);
    assert_eq!(
        record["coverage"].as_array().unwrap().len(),
        record["pixels"].as_array().unwrap().len()
    );
    assert!(record["fitted_commands"].as_array().unwrap().len() > 0);
    assert_eq!(
        record["fitted_commands"][0]["op"],
        serde_json::Value::String(String::from("move_to"))
    );
    assert!(record["fitted_commands"][0]
        .get("x_bits")
        .unwrap()
        .is_number());
    assert!(record.get("hinted_has_overlaps").unwrap().is_boolean());
    assert!(record.get("hinted_lsb").is_some());
    assert!(record.get("hinted_advance_width").is_some());
    let rerun = Command::new(binary)
        .arg(&job_path)
        .arg(&second_path)
        .output()
        .unwrap();
    assert!(rerun.status.success());
    assert_eq!(
        fs::read(&output_path).unwrap(),
        fs::read(&second_path).unwrap()
    );
    let gray_job = serde_json::json!({
        "font": "font.otf",
        "provenance": {"source": "repository fixture", "license": "unknown", "expected_sha256": digest},
        "profile": "gray_3bit",
        "settings": {"size_px": 20.0, "characters": "A", "hinting": "none", "output_bits": 3}
    });
    fs::write(&job_path, serde_json::to_vec(&gray_job).unwrap()).unwrap();
    let gray = Command::new(binary)
        .arg(&job_path)
        .arg(&output_path)
        .output()
        .unwrap();
    assert!(
        gray.status.success(),
        "{}",
        String::from_utf8_lossy(&gray.stderr)
    );
    let gray_artifact: serde_json::Value =
        serde_json::from_slice(&fs::read(&output_path).unwrap()).unwrap();
    assert_eq!(
        gray_artifact["generated"]["profile"],
        serde_json::Value::String(String::from("gray_3bit"))
    );
    assert_eq!(
        gray_artifact["generated"]["records"][0]["selected_engine"],
        serde_json::Value::String(String::from("none"))
    );
    assert_eq!(
        gray_artifact["generated"]["records"][0]["target"],
        serde_json::Value::String(String::from("smooth"))
    );
    assert_eq!(
        gray_artifact["generated"]["smooth_mode"],
        serde_json::Value::String(String::from("normal"))
    );
    assert_eq!(
        gray_artifact["generated"]["symmetric_rendering"],
        serde_json::Value::Bool(true)
    );
    assert_eq!(
        gray_artifact["generated"]["preserve_linear_metrics"],
        serde_json::Value::Bool(false)
    );
    for pixel in gray_artifact["generated"]["records"][0]["pixels"]
        .as_array()
        .unwrap()
    {
        assert!(pixel.as_u64().unwrap() <= 7);
    }
    let _ = fs::remove_dir_all(&temp);
}

#[test]
fn reference_binary_rejects_bad_jobs_without_clobbering_output() {
    let binary = env!("CARGO_BIN_EXE_font_reference");
    let temp = scratch("reject");
    fs::write(temp.join("font.otf"), CFF).unwrap();
    let digest = checksum(CFF);
    let job_path = temp.join("job.json");
    let output_path = temp.join("output.json");
    fs::write(
        &job_path,
        serde_json::to_vec(&reference_job(PROFILE_MONO_1BIT, "auto", 1, &digest)).unwrap(),
    )
    .unwrap();
    assert!(Command::new(binary)
        .arg(&job_path)
        .arg(&output_path)
        .output()
        .unwrap()
        .status
        .success());
    let good = fs::read(&output_path).unwrap();
    let mut cases: Vec<(serde_json::Value, &str)> = vec![
        (
            reference_job(PROFILE_MONO_1BIT, "auto_fallback", 1, &digest),
            "explicit",
        ),
        (reference_job("mono_8bit", "auto", 1, &digest), "profile"),
        (
            reference_job(PROFILE_MONO_1BIT, "auto", 3, &digest),
            "output_bits",
        ),
        (
            reference_job(PROFILE_GRAY_3BIT, "interpreter", 3, "wrong"),
            "checksum",
        ),
        (
            serde_json::json!({
                "font": "font.otf",
                "provenance": {"source": "repository fixture", "license": "unknown", "expected_sha256": digest},
                "profile": "mono_1bit",
                "extensions": "enhanced",
                "settings": {"size_px": 20.0, "characters": "A", "hinting": "auto", "output_bits": 1}
            }),
            "extensions",
        ),
        (
            serde_json::json!({
                "font": "font.otf",
                "provenance": {"source": "", "license": "unknown", "expected_sha256": digest},
                "profile": "mono_1bit",
                "settings": {"size_px": 20.0, "characters": "A", "hinting": "auto", "output_bits": 1}
            }),
            "provenance",
        ),
        (
            serde_json::json!({
                "font": "missing.otf",
                "provenance": {"source": "repository fixture", "license": "unknown", "expected_sha256": digest},
                "profile": "mono_1bit",
                "settings": {"size_px": 20.0, "characters": "A", "hinting": "auto", "output_bits": 1}
            }),
            "cannot read font",
        ),
    ];
    for (job, needle) in cases.drain(..) {
        fs::write(&job_path, serde_json::to_vec(&job).unwrap()).unwrap();
        let result = Command::new(binary)
            .arg(&job_path)
            .arg(&output_path)
            .output()
            .unwrap();
        assert!(!result.status.success(), "job unexpectedly passed: {job}");
        assert!(
            String::from_utf8_lossy(&result.stderr).contains(needle),
            "missing {needle:?}: {}",
            String::from_utf8_lossy(&result.stderr)
        );
        assert_eq!(fs::read(&output_path).unwrap(), good);
    }
    fs::write(
        &job_path,
        serde_json::to_vec(&reference_job(PROFILE_MONO_1BIT, "auto", 1, &digest)).unwrap(),
    )
    .unwrap();
    for target in [job_path.clone(), temp.join("font.otf")] {
        let result = Command::new(binary)
            .arg(&job_path)
            .arg(&target)
            .output()
            .unwrap();
        assert!(!result.status.success());
        assert!(String::from_utf8_lossy(&result.stderr).contains("output must differ"));
    }
    let _ = fs::remove_dir_all(&temp);
}
