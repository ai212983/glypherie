use font_generator::batch::{
    convert_coord, rasterize_batch, to_fitted, BatchCaseInput, BatchJob, BatchSettings, RawCommand,
};
use font_generator::probe::{rasterize, FittedCommand};
use font_generator::Config;
use std::{fs, process::Command};

fn raw(op: &str, coords: &[i32]) -> RawCommand {
    RawCommand {
        op: op.to_string(),
        coords: coords.to_vec(),
    }
}

fn case(key: &str, commands: Vec<RawCommand>) -> BatchCaseInput {
    BatchCaseInput {
        key: key.to_string(),
        commands,
    }
}

fn mono_settings() -> BatchSettings {
    BatchSettings {
        output_bits: 1,
        mono_threshold: 128,
        gray_gamma: 1.0,
    }
}

fn rect_commands() -> Vec<RawCommand> {
    vec![
        raw("move", &[128, 64]),
        raw("line", &[384, 64]),
        raw("line", &[384, 320]),
        raw("line", &[128, 320]),
        raw("close", &[]),
    ]
}

fn mono_config() -> Config {
    Config {
        output_bits: 1,
        mono_threshold: 128,
        ..Config::default()
    }
}

#[test]
fn integer_26_6_converts_by_exact_division() {
    assert_eq!(convert_coord(64).to_bits(), 1.0f32.to_bits());
    assert_eq!(convert_coord(128).to_bits(), 2.0f32.to_bits());
    assert_eq!(convert_coord(-64).to_bits(), (-1.0f32).to_bits());
    assert_eq!(convert_coord(0).to_bits(), 0.0f32.to_bits());
    assert_eq!(convert_coord(640).to_bits(), 10.0f32.to_bits());
    let fitted = to_fitted(&[raw("move", &[64, 128]), raw("close", &[])]).unwrap();
    assert_eq!(
        fitted,
        vec![FittedCommand::MoveTo(1.0, 2.0), FittedCommand::Close]
    );
    assert_eq!(fitted[0], FittedCommand::MoveTo(1.0, 2.0));
}

#[test]
fn fractional_26_6_converts_by_exact_division() {
    assert_eq!(convert_coord(32).to_bits(), 0.5f32.to_bits());
    assert_eq!(convert_coord(96).to_bits(), 1.5f32.to_bits());
    assert_eq!(convert_coord(1).to_bits(), (1.0f32 / 64.0).to_bits());
    assert_eq!(convert_coord(33).to_bits(), (33.0f32 / 64.0).to_bits());
    assert_eq!(convert_coord(-32).to_bits(), (-0.5f32).to_bits());
    let fitted = to_fitted(&[
        raw("move", &[0, 0]),
        raw("line", &[32, 96]),
        raw("close", &[]),
    ])
    .unwrap();
    match fitted[1] {
        FittedCommand::LineTo(x, y) => {
            assert_eq!(x.to_bits(), 0.5f32.to_bits());
            assert_eq!(y.to_bits(), 1.5f32.to_bits());
        }
        _ => panic!("expected line"),
    }
}

#[test]
fn negative_coordinates_keep_sign_and_bits() {
    let fitted = to_fitted(&[
        raw("move", &[-64, -128]),
        raw("line", &[-32, -1]),
        raw("close", &[]),
    ])
    .unwrap();
    match fitted[0] {
        FittedCommand::MoveTo(x, y) => {
            assert_eq!(x.to_bits(), (-1.0f32).to_bits());
            assert_eq!(y.to_bits(), (-2.0f32).to_bits());
        }
        _ => panic!("expected move"),
    }
    match fitted[1] {
        FittedCommand::LineTo(x, y) => {
            assert_eq!(x.to_bits(), (-0.5f32).to_bits());
            assert_eq!(y.to_bits(), (convert_coord(-1)).to_bits());
        }
        _ => panic!("expected line"),
    }
    let job = BatchJob {
        settings: mono_settings(),
        cases: vec![case(
            "neg",
            vec![
                raw("move", &[-512, -256]),
                raw("line", &[0, -256]),
                raw("line", &[0, 0]),
                raw("line", &[-512, 0]),
                raw("close", &[]),
            ],
        )],
    };
    let output = rasterize_batch(&job).unwrap();
    assert_eq!(output.cases.len(), 1);
    assert!(output.cases[0].pixels.iter().all(|&p| p == 1));
    assert_eq!((output.cases[0].left, output.cases[0].top), (-8, 0));
}

#[test]
fn contour_order_and_multiple_contours_preserved() {
    let commands = vec![
        raw("move", &[64, 128]),
        raw("line", &[192, 256]),
        raw("close", &[]),
        raw("move", &[1280, 1344]),
        raw("line", &[1408, 1472]),
        raw("close", &[]),
    ];
    let fitted = to_fitted(&commands).unwrap();
    assert_eq!(
        fitted,
        vec![
            FittedCommand::MoveTo(1.0, 2.0),
            FittedCommand::LineTo(3.0, 4.0),
            FittedCommand::Close,
            FittedCommand::MoveTo(20.0, 21.0),
            FittedCommand::LineTo(22.0, 23.0),
            FittedCommand::Close,
        ]
    );
    let job = BatchJob {
        settings: mono_settings(),
        cases: vec![case("two", commands)],
    };
    let output = rasterize_batch(&job).unwrap();
    assert_eq!(output.cases[0].fitted_commands, fitted);
}

#[test]
fn quadratic_and_cubic_convert_exactly() {
    let commands = vec![
        raw("move", &[0, 0]),
        raw("quadratic", &[64, 128, 192, 256]),
        raw("cubic", &[320, 384, 448, 512, 576, 640]),
        raw("close", &[]),
    ];
    let fitted = to_fitted(&commands).unwrap();
    assert_eq!(
        fitted,
        vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::QuadTo(1.0, 2.0, 3.0, 4.0),
            FittedCommand::CurveTo(5.0, 6.0, 7.0, 8.0, 9.0, 10.0),
            FittedCommand::Close,
        ]
    );
    let value = serde_json::to_value(&fitted).unwrap();
    assert_eq!(value[1]["op"], serde_json::Value::String("quad_to".into()));
    assert_eq!(
        value[1]["x1_bits"].as_u64().unwrap(),
        1.0f32.to_bits() as u64
    );
    assert_eq!(value[2]["op"], serde_json::Value::String("curve_to".into()));
    assert_eq!(
        value[2]["x_bits"].as_u64().unwrap(),
        9.0f32.to_bits() as u64
    );
    let job = BatchJob {
        settings: mono_settings(),
        cases: vec![case("curves", commands)],
    };
    let output = rasterize_batch(&job).unwrap();
    assert_eq!(output.cases[0].fitted_commands, fitted);
    assert_eq!(
        output.cases[0].pixels.len(),
        (output.cases[0].width * output.cases[0].height) as usize
    );
}

#[test]
fn placement_matches_direct_rasterize_for_rect() {
    let job = BatchJob {
        settings: mono_settings(),
        cases: vec![case("rect", rect_commands())],
    };
    let output = rasterize_batch(&job).unwrap();
    assert_eq!(output.cases.len(), 1);
    let found = &output.cases[0];
    assert_eq!(
        (found.left, found.top, found.width, found.height),
        (2, -5, 4, 4)
    );
    assert_eq!(found.pixels.len(), 16);
    assert!(found.pixels.iter().all(|&p| p == 1));
    let fitted = to_fitted(&rect_commands()).unwrap();
    let direct = rasterize(&fitted, &mono_config()).unwrap();
    assert_eq!(found.pixels, direct.pixels);
    assert_eq!(
        (found.left, found.top, found.width, found.height),
        (direct.left, direct.top, direct.width, direct.height)
    );
    assert_eq!(found.fitted_commands, fitted);
}

#[test]
fn batch_output_is_sorted_by_key() {
    let job = BatchJob {
        settings: mono_settings(),
        cases: vec![
            case("zebra", rect_commands()),
            case("apple", rect_commands()),
            case("mango", vec![]),
        ],
    };
    let output = rasterize_batch(&job).unwrap();
    let keys: Vec<&str> = output.cases.iter().map(|c| c.key.as_str()).collect();
    assert_eq!(keys, vec!["apple", "mango", "zebra"]);
    let encoded = serde_json::to_vec(&output).unwrap();
    let decoded: BatchJob = serde_json::from_slice(
        &serde_json::to_vec(&serde_json::json!({
            "settings": {"output_bits": 1, "mono_threshold": 128, "gray_gamma": 1.0},
            "cases": [
                {"key": "zebra", "commands": []},
                {"key": "apple", "commands": []}
            ]
        }))
        .unwrap(),
    )
    .unwrap();
    assert_eq!(decoded.cases[0].key, "zebra");
    assert_eq!(encoded.len() > 0, true);
}

#[test]
fn batch_equals_direct_rasterize_for_each_case() {
    let quad_case = vec![
        raw("move", &[0, 0]),
        raw("quadratic", &[256, 512, 512, 0]),
        raw("close", &[]),
    ];
    let cubic_case = vec![
        raw("move", &[0, 0]),
        raw("cubic", &[128, 512, 384, 512, 512, 0]),
        raw("close", &[]),
    ];
    let job = BatchJob {
        settings: mono_settings(),
        cases: vec![
            case("quad", quad_case.clone()),
            case("cubic", cubic_case.clone()),
            case("rect", rect_commands()),
        ],
    };
    let output = rasterize_batch(&job).unwrap();
    assert_eq!(output.cases.len(), 3);
    for found in &output.cases {
        let input = job.cases.iter().find(|c| c.key == found.key).unwrap();
        let fitted = to_fitted(&input.commands).unwrap();
        assert_eq!(found.fitted_commands, fitted);
        let direct = rasterize(&fitted, &mono_config()).unwrap();
        assert_eq!(found.pixels, direct.pixels);
        assert_eq!(
            (found.left, found.top, found.width, found.height),
            (direct.left, direct.top, direct.width, direct.height)
        );
    }
}

#[test]
fn invalid_inputs_are_rejected_before_output() {
    let good = rect_commands();
    let mut non_mono = mono_settings();
    non_mono.output_bits = 8;
    assert!(rasterize_batch(&BatchJob {
        settings: non_mono,
        cases: vec![case("a", good.clone())],
    })
    .is_err());
    let mut zero_threshold = mono_settings();
    zero_threshold.mono_threshold = 0;
    assert!(rasterize_batch(&BatchJob {
        settings: zero_threshold,
        cases: vec![case("a", good.clone())],
    })
    .is_err());
    assert!(rasterize_batch(&BatchJob {
        settings: mono_settings(),
        cases: vec![case("a", good.clone()), case("a", good.clone())],
    })
    .is_err());
    assert!(rasterize_batch(&BatchJob {
        settings: mono_settings(),
        cases: vec![case("", good.clone())],
    })
    .is_err());
    assert!(to_fitted(&[raw("arc", &[0, 0])]).is_err());
    assert!(to_fitted(&[raw("move", &[1])]).is_err());
    assert!(to_fitted(&[raw("move", &[0, 0, 0])]).is_err());
    assert!(to_fitted(&[raw("move", &[0, 0]), raw("line", &[1])]).is_err());
    assert!(to_fitted(&[raw("move", &[0, 0]), raw("quadratic", &[1, 2])]).is_err());
    assert!(to_fitted(&[raw("move", &[0, 0]), raw("cubic", &[1, 2, 3, 4])]).is_err());
    assert!(to_fitted(&[raw("move", &[0, 0]), raw("close", &[1])]).is_err());
    assert!(to_fitted(&[raw("line", &[0, 0])]).is_err());
    assert!(to_fitted(&[raw("close", &[])]).is_err());
    assert!(to_fitted(&[raw("move", &[0, 0]), raw("move", &[64, 64])]).is_err());
    assert!(to_fitted(&[raw("move", &[0, 0]), raw("line", &[64, 64])]).is_err());
    assert!(to_fitted(&[raw("move", &[2097153, 0]), raw("close", &[])]).is_err());
    assert!(to_fitted(&[raw("move", &[-2097153, 0]), raw("close", &[])]).is_err());
    assert!(to_fitted(&[raw("move", &[i32::MIN, 0]), raw("close", &[])]).is_err());
    assert!(to_fitted(&[raw("move", &[0, 2097153]), raw("close", &[])]).is_err());
    let over = BatchJob {
        settings: mono_settings(),
        cases: vec![case(
            "over",
            vec![
                raw("move", &[0, 0]),
                raw("line", &[2097153, 0]),
                raw("close", &[]),
            ],
        )],
    };
    assert!(rasterize_batch(&over).is_err());
    let bad_field: Result<BatchJob, _> = serde_json::from_value(serde_json::json!({
        "settings": {"output_bits": 1, "mono_threshold": 128, "gray_gamma": 1.0},
        "cases": [{"key": "a", "commands": [{"op": "move", "coords": [0, 0], "extra": 1}]}]
    }));
    assert!(bad_field.is_err());
    let unknown_top: Result<BatchJob, _> = serde_json::from_value(serde_json::json!({
        "settings": {"output_bits": 1, "mono_threshold": 128, "gray_gamma": 1.0},
        "cases": [],
        "extra": 1
    }));
    assert!(unknown_top.is_err());
    let unknown_setting: Result<BatchJob, _> = serde_json::from_value(serde_json::json!({
        "settings": {"output_bits": 1, "mono_threshold": 128, "gray_gamma": 1.0, "size_px": 16.0},
        "cases": []
    }));
    assert!(unknown_setting.is_err());
}

#[test]
fn cli_accepts_batch_and_emits_deterministic_json() {
    let binary = env!("CARGO_BIN_EXE_common_rasterizer");
    let temp = std::env::temp_dir().join(format!("common-rasterizer-{}", std::process::id()));
    fs::create_dir_all(&temp).unwrap();
    let input_path = temp.join("input.json");
    let output_path = temp.join("output.json");
    let second_path = temp.join("second.json");
    let input = serde_json::json!({
        "settings": {"output_bits": 1, "mono_threshold": 128, "gray_gamma": 1.0},
        "cases": [
            {"key": "b", "commands": [
                {"op": "move", "coords": [128, 64]},
                {"op": "line", "coords": [384, 64]},
                {"op": "line", "coords": [384, 320]},
                {"op": "line", "coords": [128, 320]},
                {"op": "close", "coords": []}
            ]},
            {"key": "a", "commands": [
                {"op": "move", "coords": [0, 0]},
                {"op": "quadratic", "coords": [256, 512, 512, 0]},
                {"op": "close", "coords": []}
            ]}
        ]
    });
    fs::write(&input_path, serde_json::to_vec(&input).unwrap()).unwrap();
    let result = Command::new(binary)
        .arg(&input_path)
        .arg(&output_path)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let first = fs::read(&output_path).unwrap();
    let value: serde_json::Value = serde_json::from_slice(&first).unwrap();
    assert_eq!(
        value["cases"][0]["key"],
        serde_json::Value::String("a".into())
    );
    assert_eq!(
        value["cases"][1]["key"],
        serde_json::Value::String("b".into())
    );
    assert_eq!(value["cases"][1]["left"].as_i64().unwrap(), 2);
    assert_eq!(value["cases"][1]["top"].as_i64().unwrap(), -5);
    assert_eq!(value["cases"][1]["width"].as_u64().unwrap(), 4);
    assert_eq!(value["cases"][1]["height"].as_u64().unwrap(), 4);
    assert_eq!(value["cases"][1]["pixels"].as_array().unwrap().len(), 16);
    let fitted = &value["cases"][1]["fitted_commands"];
    assert_eq!(fitted[0]["op"], serde_json::Value::String("move_to".into()));
    assert_eq!(
        fitted[0]["x_bits"].as_u64().unwrap(),
        2.0f32.to_bits() as u64
    );
    assert_eq!(
        fitted[0]["y_bits"].as_u64().unwrap(),
        1.0f32.to_bits() as u64
    );
    let rerun = Command::new(binary)
        .arg(&input_path)
        .arg(&second_path)
        .output()
        .unwrap();
    assert!(rerun.status.success());
    assert_eq!(first, fs::read(&second_path).unwrap());
    let _ = fs::remove_dir_all(&temp);
}

#[test]
fn cli_rejects_invalid_without_writing_output() {
    let binary = env!("CARGO_BIN_EXE_common_rasterizer");
    let temp = std::env::temp_dir().join(format!("common-rasterizer-bad-{}", std::process::id()));
    fs::create_dir_all(&temp).unwrap();
    let input_path = temp.join("input.json");
    let output_path = temp.join("output.json");
    let cases = vec![
        serde_json::json!({
            "settings": {"output_bits": 8, "mono_threshold": 128, "gray_gamma": 1.0},
            "cases": [{"key": "a", "commands": []}]
        }),
        serde_json::json!({
            "settings": {"output_bits": 1, "mono_threshold": 128, "gray_gamma": 1.0},
            "cases": [
                {"key": "a", "commands": []},
                {"key": "a", "commands": []}
            ]
        }),
        serde_json::json!({
            "settings": {"output_bits": 1, "mono_threshold": 128, "gray_gamma": 1.0},
            "cases": [{"key": "a", "commands": [{"op": "move", "coords": [0]}]}]
        }),
        serde_json::json!({
            "settings": {"output_bits": 1, "mono_threshold": 128, "gray_gamma": 1.0},
            "cases": [{"key": "a", "commands": [{"op": "arc", "coords": [0, 0]}]}]
        }),
        serde_json::json!({
            "settings": {"output_bits": 1, "mono_threshold": 128, "gray_gamma": 1.0},
            "cases": [{"key": "a", "commands": [{"op": "line", "coords": [0, 0]}]}]
        }),
        serde_json::json!({
            "settings": {"output_bits": 1, "mono_threshold": 128, "gray_gamma": 1.0, "extra": 1},
            "cases": []
        }),
    ];
    for (index, invalid) in cases.iter().enumerate() {
        fs::write(&input_path, serde_json::to_vec(invalid).unwrap()).unwrap();
        let _ = fs::remove_file(&output_path);
        let result = Command::new(binary)
            .arg(&input_path)
            .arg(&output_path)
            .output()
            .unwrap();
        assert!(!result.status.success(), "case {index} unexpectedly passed");
        assert!(
            !output_path.exists(),
            "case {index} wrote output on failure"
        );
    }
    let _ = fs::remove_dir_all(&temp);
}
