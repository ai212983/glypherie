use font_generator::{
    generate,
    probe::{
        lock_sha256, probe, rasterize, skrifa_version, to_zeno, zeno_version, FittedCommand,
        FittedPen,
    },
    Config, Hinting,
};
use skrifa::outline::OutlinePen;
use std::{fs, path::PathBuf, process::Command};
use zeno::Command as ZenoCommand;

const CFF: &[u8] = include_bytes!("fixtures/static-cff.otf");

fn pen_with_two_contours() -> Vec<FittedCommand> {
    let mut pen = FittedPen::default();
    pen.move_to(1.0, 2.0);
    pen.line_to(3.0, 4.0);
    pen.quad_to(5.0, 6.0, 7.0, 8.0);
    pen.curve_to(9.0, 10.0, 11.0, 12.0, 13.0, 14.0);
    pen.close();
    pen.move_to(20.0, 21.0);
    pen.line_to(22.0, 23.0);
    pen.close();
    pen.into_commands()
}

fn mono_config(characters: &str, hinting: Hinting) -> Config {
    Config {
        size_px: 20.0,
        characters: characters.into(),
        hinting,
        output_bits: 1,
        ..Config::default()
    }
}

fn command_points(command: &FittedCommand) -> Vec<(f32, f32)> {
    match *command {
        FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => vec![(x, y)],
        FittedCommand::QuadTo(x1, y1, x, y) => vec![(x1, y1), (x, y)],
        FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => vec![(x1, y1), (x2, y2), (x, y)],
        FittedCommand::Close => vec![],
    }
}

fn zeno_points(command: &ZenoCommand) -> Vec<(f32, f32)> {
    match *command {
        ZenoCommand::MoveTo(p) | ZenoCommand::LineTo(p) => vec![(p.x, p.y)],
        ZenoCommand::QuadTo(a, b) => vec![(a.x, a.y), (b.x, b.y)],
        ZenoCommand::CurveTo(a, b, c) => vec![(a.x, a.y), (b.x, b.y), (c.x, c.y)],
        ZenoCommand::Close => vec![],
    }
}

#[test]
fn fitted_pen_captures_every_command_kind_in_contour_order() {
    assert_eq!(
        pen_with_two_contours(),
        vec![
            FittedCommand::MoveTo(1.0, 2.0),
            FittedCommand::LineTo(3.0, 4.0),
            FittedCommand::QuadTo(5.0, 6.0, 7.0, 8.0),
            FittedCommand::CurveTo(9.0, 10.0, 11.0, 12.0, 13.0, 14.0),
            FittedCommand::Close,
            FittedCommand::MoveTo(20.0, 21.0),
            FittedCommand::LineTo(22.0, 23.0),
            FittedCommand::Close,
        ]
    );
}

#[test]
fn capture_keeps_device_pixel_origin_baseline_and_exact_f32_bits() {
    let inputs = [0.0f32, -0.0f32, 0.1f32, 1e-40f32, -123.456f32, 16.0f32];
    let mut pen = FittedPen::default();
    pen.move_to(inputs[0], inputs[1]);
    pen.line_to(inputs[2], inputs[3]);
    pen.quad_to(inputs[4], inputs[5], inputs[0], inputs[2]);
    pen.curve_to(
        inputs[1], inputs[3], inputs[4], inputs[5], inputs[0], inputs[1],
    );
    pen.close();
    let commands = pen.into_commands();
    let flat: Vec<f32> = commands
        .iter()
        .flat_map(command_points)
        .flat_map(|(x, y)| [x, y])
        .collect();
    let expected: Vec<f32> = vec![
        inputs[0], inputs[1], inputs[2], inputs[3], inputs[4], inputs[5], inputs[0], inputs[2],
        inputs[1], inputs[3], inputs[4], inputs[5], inputs[0], inputs[1],
    ];
    assert_eq!(flat.len(), expected.len());
    for (actual, wanted) in flat.iter().zip(expected.iter()) {
        assert_eq!(actual.to_bits(), wanted.to_bits());
    }
    assert_eq!(flat[0].to_bits(), 0x00000000);
    assert_eq!(flat[1].to_bits(), (-0.0f32).to_bits());
    let value = serde_json::to_value(&commands).unwrap();
    let entries = value.as_array().unwrap();
    assert_eq!(entries.len(), commands.len());
    assert_eq!(
        entries[0]["op"],
        serde_json::Value::String("move_to".into())
    );
    assert_eq!(
        entries[0]["x_bits"].as_u64().unwrap(),
        inputs[0].to_bits() as u64
    );
    assert_eq!(
        entries[0]["y_bits"].as_u64().unwrap(),
        inputs[1].to_bits() as u64
    );
    assert_eq!(entries[4]["op"], serde_json::Value::String("close".into()));
}

#[test]
fn zeno_adapter_applies_exactly_one_y_negation() {
    let captured = pen_with_two_contours();
    let converted = to_zeno(&captured);
    assert_eq!(converted.len(), captured.len());
    for (from, to) in captured.iter().zip(converted.iter()) {
        let a = command_points(from);
        let b = zeno_points(to);
        assert_eq!(a.len(), b.len());
        for ((x, y), (zx, zy)) in a.iter().zip(b.iter()) {
            assert_eq!(zx.to_bits(), x.to_bits());
            assert_eq!(zy.to_bits(), (-y).to_bits());
        }
    }
    let mut pen = FittedPen::default();
    pen.move_to(0.0, 0.0);
    let converted = to_zeno(&pen.into_commands());
    match converted[0] {
        ZenoCommand::MoveTo(p) => {
            assert_eq!(p.x.to_bits(), 0x00000000);
            assert_eq!(p.y.to_bits(), (-0.0f32).to_bits());
        }
        _ => panic!("expected move"),
    }
}

#[test]
fn raster_reports_row_major_pixels_and_zeno_placement() {
    let cfg = mono_config("A", Hinting::Auto);
    let empty = rasterize(&[], &cfg).unwrap();
    assert_eq!(
        (empty.left, empty.top, empty.width, empty.height),
        (0, 0, 0, 0)
    );
    assert!(empty.pixels.is_empty());
    let mut rect = FittedPen::default();
    rect.move_to(2.0, 1.0);
    rect.line_to(6.0, 1.0);
    rect.line_to(6.0, 5.0);
    rect.line_to(2.0, 5.0);
    rect.close();
    let output = rasterize(&rect.into_commands(), &cfg).unwrap();
    assert_eq!(
        (output.left, output.top, output.width, output.height),
        (2, -5, 4, 4)
    );
    assert_eq!(output.pixels.len(), 16);
    assert!(output.pixels.iter().all(|&p| p == 1));
    let mut stacked = FittedPen::default();
    stacked.move_to(0.0, 60.0);
    stacked.line_to(8.0, 60.0);
    stacked.line_to(8.0, 64.0);
    stacked.line_to(0.0, 64.0);
    stacked.close();
    stacked.move_to(0.0, 0.0);
    stacked.line_to(8.0, 0.0);
    stacked.line_to(8.0, 4.0);
    stacked.line_to(0.0, 4.0);
    stacked.close();
    let output = rasterize(&stacked.into_commands(), &cfg).unwrap();
    assert_eq!(
        (output.left, output.top, output.width, output.height),
        (0, -64, 8, 64)
    );
    assert_eq!(output.pixels.len(), 8 * 64);
    for (row, chunk) in output.pixels.chunks_exact(8).enumerate() {
        let inked = row < 4 || row >= 60;
        assert!(
            chunk.iter().all(|&p| p == u8::from(inked)),
            "row {row} inked={inked}"
        );
    }
}

#[test]
fn probe_records_explicit_engine_evidence() {
    for (hinting, name) in [
        (Hinting::Auto, "auto"),
        (Hinting::Interpreter, "interpreter"),
    ] {
        let report = probe(CFF, &mono_config("A", hinting)).unwrap();
        assert_eq!(report.records.len(), 1);
        let record = &report.records[0];
        assert_eq!(record.codepoint, 65);
        assert_eq!(record.selected_engine, name);
        assert_eq!(report.hinting_requested, name);
        assert_eq!(record.target, "mono");
        assert!(!record.draw_hinted);
        assert_eq!(record.skrifa_version, "0.48.0");
        assert_eq!(record.zeno_version, "0.3.3");
        assert_eq!(report.skrifa_version, skrifa_version());
        assert_eq!(report.zeno_version, zeno_version());
        assert_eq!(record.zeno_format, "alpha");
        assert_eq!(record.output_bits, 1);
        assert!(!record.fitted_commands.is_empty());
        assert!(!record.pixels.is_empty());
        assert_eq!(record.pixels.len(), (record.width * record.height) as usize);
        assert!(record.advance_26_6 > 0);
        assert!(!report.dependency_lock_sha256.is_empty());
        assert_eq!(report.dependency_lock_sha256, lock_sha256());
        let value = serde_json::to_value(&report).unwrap();
        let recorded = &value["records"][0];
        assert_eq!(
            recorded["selected_engine"],
            serde_json::Value::String(name.into())
        );
        assert!(recorded.get("hinted_has_overlaps").unwrap().is_boolean());
        assert!(recorded.get("hinted_lsb").is_some());
        assert!(recorded.get("hinted_advance_width").is_some());
        let entries = recorded["fitted_commands"].as_array().unwrap();
        assert_eq!(entries.len(), record.fitted_commands.len());
        for (entry, command) in entries.iter().zip(record.fitted_commands.iter()) {
            let expected: Vec<u32> = command_points(command)
                .iter()
                .flat_map(|(x, y)| [x.to_bits(), y.to_bits()])
                .collect();
            let mut actual = Vec::new();
            for key in [
                "x_bits", "y_bits", "x1_bits", "y1_bits", "x2_bits", "y2_bits",
            ] {
                if let Some(bits) = entry.get(key) {
                    actual.push(bits.as_u64().unwrap() as u32);
                }
            }
            let mut ordered = Vec::new();
            match command {
                FittedCommand::MoveTo(..) | FittedCommand::LineTo(..) => {
                    ordered = actual;
                }
                FittedCommand::QuadTo(..) => {
                    ordered = vec![actual[2], actual[3], actual[0], actual[1]];
                }
                FittedCommand::CurveTo(..) => {
                    ordered = vec![
                        actual[4], actual[5], actual[2], actual[3], actual[0], actual[1],
                    ];
                }
                FittedCommand::Close => {}
            }
            assert_eq!(ordered, expected);
        }
    }
    assert!(probe(CFF, &mono_config("A", Hinting::None)).is_err());
    assert!(probe(CFF, &mono_config("A", Hinting::AutoFallback)).is_err());
}

#[test]
fn probe_matches_independent_reference_and_unchanged_interpreter_output() {
    use font_generator::reference::{reference, ReferenceRequest};
    for hinting in [Hinting::Auto, Hinting::Interpreter] {
        let cfg = mono_config("A", hinting);
        let report = probe(CFF, &cfg).unwrap();
        let reference = reference(
            CFF,
            &ReferenceRequest {
                profile: "mono_1bit".into(),
                extensions: "none".into(),
                settings: cfg.clone(),
            },
        )
        .unwrap();
        assert_eq!(report.records.len(), reference.records.len());
        for (record, expected) in report.records.iter().zip(&reference.records) {
            assert_eq!(record.codepoint, expected.codepoint);
            assert_eq!(record.glyph_id, expected.glyph_id);
            assert_eq!(record.fitted_commands, expected.fitted_commands);
            assert_eq!(record.pixels, expected.pixels);
            assert_eq!(
                (record.left, record.top, record.width, record.height),
                (expected.left, expected.top, expected.width, expected.height)
            );
            assert_eq!(record.advance_26_6, expected.advance_26_6);
        }
        assert_eq!(report.metrics, reference.metrics);
        // Automatic production uses the approved fitter and dropout policy;
        // the probe remains independent upstream evidence. Interpreter output
        // retains its production/reference identity contract.
        if hinting != Hinting::Interpreter {
            continue;
        }
        let generated = generate(CFF, &cfg).unwrap();
        assert_eq!(report.records.len(), generated.glyphs.len());
        for (record, glyph) in report.records.iter().zip(generated.glyphs.iter()) {
            assert_eq!(record.codepoint, glyph.codepoint);
            assert_eq!(record.glyph_id, glyph.glyph_id);
            assert_eq!(record.pixels, glyph.pixels);
            assert_eq!(
                (record.left, record.top, record.width, record.height),
                (glyph.left, glyph.top, glyph.width, glyph.height)
            );
            assert_eq!(record.advance_26_6, glyph.advance_26_6);
        }
        assert_eq!(report.source_sha256, generated.source_sha256);
        assert_eq!(report.metrics, generated.metrics);
    }
    let roboto = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../fonts/Roboto.ttf");
    let bytes = fs::read(&roboto).unwrap();
    let cfg = Config {
        size_px: 16.0,
        characters: "H".into(),
        hinting: Hinting::Auto,
        ..Config::default()
    };
    let report = probe(&bytes, &cfg).unwrap();
    let reference = reference(
        &bytes,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: "none".into(),
            settings: cfg,
        },
    )
    .unwrap();
    assert_eq!(
        report.records[0].fitted_commands,
        reference.records[0].fitted_commands
    );
    assert_eq!(report.records[0].pixels, reference.records[0].pixels);
    assert_eq!(
        (
            report.records[0].left,
            report.records[0].top,
            report.records[0].width,
            report.records[0].height
        ),
        (
            reference.records[0].left,
            reference.records[0].top,
            reference.records[0].width,
            reference.records[0].height
        )
    );
    assert_eq!(
        report.records[0].advance_26_6,
        reference.records[0].advance_26_6
    );
    assert_eq!(report.metrics, reference.metrics);
}

#[test]
fn hint_probe_binary_accepts_explicit_jobs_and_rejects_fallback() {
    let binary = env!("CARGO_BIN_EXE_font_hint_probe");
    let temp = std::env::temp_dir().join(format!("hint-probe-tests-{}", std::process::id()));
    fs::create_dir_all(&temp).unwrap();
    fs::write(temp.join("font.otf"), CFF).unwrap();
    let checksum = {
        use sha2::Digest;
        format!("{:x}", sha2::Sha256::digest(CFF))
    };
    let job = serde_json::json!({
        "font": "font.otf",
        "provenance": {"source": "repository fixture", "license": "unknown", "expected_sha256": checksum},
        "settings": {"size_px": 20.0, "characters": "A", "hinting": "auto", "output_bits": 1}
    });
    let job_path = temp.join("job.json");
    let output_path = temp.join("output.json");
    fs::write(&job_path, serde_json::to_vec(&job).unwrap()).unwrap();
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
    assert_eq!(
        artifact["generated"]["records"][0]["selected_engine"],
        serde_json::Value::String("auto".into())
    );
    assert_eq!(
        artifact["generated"]["records"][0]["target"],
        serde_json::Value::String("mono".into())
    );
    let fallback = serde_json::json!({
        "font": "font.otf",
        "provenance": {"source": "repository fixture", "license": "unknown", "expected_sha256": checksum},
        "settings": {"size_px": 20.0, "characters": "A", "hinting": "auto_fallback", "output_bits": 1}
    });
    fs::write(&job_path, serde_json::to_vec(&fallback).unwrap()).unwrap();
    let rejected = Command::new(binary)
        .arg(&job_path)
        .arg(&output_path)
        .output()
        .unwrap();
    assert!(!rejected.status.success());
    assert!(String::from_utf8_lossy(&rejected.stderr).contains("explicit"));
    let _ = fs::remove_dir_all(&temp);
}

#[test]
fn probe_rejects_non_mono_output_bits() {
    for bits in [2u8, 3, 4, 8] {
        let mut cfg = mono_config("A", Hinting::Auto);
        cfg.output_bits = bits;
        assert!(probe(CFF, &cfg).is_err());
        let mut gray = mono_config("A", Hinting::Interpreter);
        gray.output_bits = bits;
        assert!(probe(CFF, &gray).is_err());
    }
}
