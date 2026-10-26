#![cfg(feature = "candidate")]
//! Exact parity with frozen diagonal-fit geometry and independent
//! high-precision FreeType rasters, including terminal-cap suppression.
use font_generator::{
    diagonal_fitting, mono,
    probe::{FittedCommand, RasterOutput},
    reference::FontScanState,
    terminal_caps, Config, Hinting, MonoDropoutMode, MonoRasterSettings,
};
use serde_json::Value;
use std::collections::BTreeMap;

fn fixture() -> Value {
    serde_json::from_str(include_str!("fixtures/diagonal-width-port.json")).unwrap()
}

fn coord(command: &Value, key: &str) -> f32 {
    let bits = command[key.to_string() + "_bits"].as_u64().unwrap() as u32;
    let value = f32::from_bits(bits);
    assert_eq!(
        value,
        command[key].as_f64().unwrap() as f32,
        "numeric f32 bits agree for {key}"
    );
    value
}

fn parse_command(command: &Value) -> FittedCommand {
    match command["op"].as_str().unwrap() {
        "move_to" => FittedCommand::MoveTo(coord(command, "x"), coord(command, "y")),
        "line_to" => FittedCommand::LineTo(coord(command, "x"), coord(command, "y")),
        "quad_to" => FittedCommand::QuadTo(
            coord(command, "x1"),
            coord(command, "y1"),
            coord(command, "x"),
            coord(command, "y"),
        ),
        "curve_to" => FittedCommand::CurveTo(
            coord(command, "x1"),
            coord(command, "y1"),
            coord(command, "x2"),
            coord(command, "y2"),
            coord(command, "x"),
            coord(command, "y"),
        ),
        "close" => FittedCommand::Close,
        op => panic!("unknown op {op}"),
    }
}

fn parse_commands(commands: &Value) -> Vec<FittedCommand> {
    commands
        .as_array()
        .unwrap()
        .iter()
        .map(parse_command)
        .collect()
}

fn command_bits(command: &FittedCommand) -> (u8, Vec<u32>) {
    match *command {
        FittedCommand::MoveTo(x, y) => (0, vec![x.to_bits(), y.to_bits()]),
        FittedCommand::LineTo(x, y) => (1, vec![x.to_bits(), y.to_bits()]),
        FittedCommand::QuadTo(x1, y1, x, y) => (
            2,
            vec![x1.to_bits(), y1.to_bits(), x.to_bits(), y.to_bits()],
        ),
        FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => (
            3,
            vec![
                x1.to_bits(),
                y1.to_bits(),
                x2.to_bits(),
                y2.to_bits(),
                x.to_bits(),
                y.to_bits(),
            ],
        ),
        FittedCommand::Close => (4, Vec::new()),
    }
}

fn parse_scan(scan: &Value) -> Option<FontScanState> {
    if scan.is_null() {
        return None;
    }
    Some(FontScanState {
        source_sha256: scan["source_sha256"].as_str().unwrap().to_string(),
        enabled: scan["enabled"].as_bool().unwrap(),
        scan_type: scan["scan_type"].as_u64().unwrap() as u16,
        contour_modes: scan["contour_modes"]
            .as_array()
            .unwrap()
            .iter()
            .map(|mode| mode.as_u64().map(|b| b as u8))
            .collect(),
        hinting_axes: [
            scan["hinting_axes"][0].as_bool().unwrap(),
            scan["hinting_axes"][1].as_bool().unwrap(),
        ],
    })
}

fn config_for(case: &Value) -> Config {
    let hinting = match case["hinting_requested"].as_str().unwrap() {
        "auto" => Hinting::Auto,
        "auto_fallback" => Hinting::AutoFallback,
        other => panic!("unknown hinting_requested {other}"),
    };
    let dropout = match case["mono_raster"]["dropout"].as_str().unwrap() {
        "smart" => MonoDropoutMode::Smart,
        "simple" => MonoDropoutMode::Simple,
        "off" => MonoDropoutMode::Off,
        other => panic!("unknown dropout {other}"),
    };
    let mut axes = BTreeMap::new();
    for (key, value) in case["axes"].as_object().unwrap() {
        axes.insert(key.clone(), value.as_f64().unwrap() as f32);
    }
    Config {
        size_px: case["size_px"].as_f64().unwrap() as f32,
        axes,
        hinting,
        output_bits: 1,
        mono_threshold: 128,
        gray_gamma: 1.0,
        mono_raster: MonoRasterSettings {
            dropout,
            include_stubs: case["mono_raster"]["include_stubs"].as_bool().unwrap(),
            font_instructions: case["mono_raster"]["font_instructions"].as_bool().unwrap(),
        },
        ..Config::default()
    }
}

/// Replay the terminal policy over fitted outlines without rerunning fitting.
fn rasterize_candidate(
    source: &[FittedCommand],
    fitted: &[FittedCommand],
    config: &Config,
    raster_policy: &str,
    font_scan: Option<&FontScanState>,
) -> RasterOutput {
    match raster_policy {
        "free_type_mono_terminals" => {
            let mut output = mono::rasterize(fitted, config).unwrap();
            let mut no_stubs = config.clone();
            no_stubs.mono_raster.include_stubs = false;
            no_stubs.mono_raster.font_instructions = false;
            let without = mono::rasterize(fitted, &no_stubs).unwrap();
            output.pixels = terminal_caps::suppress_certified(source, fitted, &output, &without)
                .unwrap()
                .pixels;
            output
        }
        "free_type_mono" => mono::rasterize_with_scan_state(fitted, config, font_scan).unwrap(),
        other => panic!("unknown raster_policy {other}"),
    }
}

fn bytes(value: &Value) -> Vec<u8> {
    value
        .as_array()
        .unwrap()
        .iter()
        .map(|b| b.as_u64().unwrap() as u8)
        .collect()
}

#[test]
fn fixture_covers_both_families_and_modes() {
    let root = fixture();
    let cases = root["cases"].as_array().unwrap();
    assert_eq!(cases.len(), 45, "self-contained golden case count");
    let mut ids: Vec<&str> = cases
        .iter()
        .map(|case| case["id"].as_str().unwrap())
        .collect();
    ids.sort_unstable();
    ids.dedup();
    assert_eq!(ids.len(), 45, "case ids are unique");
    let expected_cells: [(&str, f64, f64, &str, usize); 12] = [
        ("Roboto", 16.0, 400.0, "auto_default", 9),
        ("Roboto", 16.0, 400.0, "selective_default", 9),
        ("SourceSans3", 16.0, 400.0, "auto_default", 9),
        ("SourceSans3", 16.0, 400.0, "selective_default", 9),
        ("Roboto", 20.0, 400.0, "auto_default", 2),
        ("Roboto", 14.0, 400.0, "auto_default", 1),
        ("Roboto", 14.0, 400.0, "selective_default", 1),
        ("Roboto", 16.0, 300.0, "selective_default", 1),
        ("Roboto", 18.0, 300.0, "auto_default", 1),
        ("Roboto", 20.0, 400.0, "selective_default", 1),
        ("Roboto", 24.0, 300.0, "auto_default", 1),
        ("Roboto", 24.0, 300.0, "selective_default", 1),
    ];
    for (family, size, weight, hint_mode, count) in expected_cells {
        let cell_cases: Vec<&Value> = cases
            .iter()
            .filter(|case| {
                case["family"] == family
                    && case["size_px"] == size
                    && case["weight"] == weight
                    && case["hint_mode"] == hint_mode
            })
            .collect();
        assert_eq!(cell_cases.len(), count, "per-cell case count");
    }
    assert!(
        cases.iter().any(|case| case["codepoint"] == 0x34
            && case["family"] == "Roboto"
            && case["size_px"] == 20.0),
        "lost Roboto 20 U+0034 case is present"
    );
    assert!(
        cases
            .iter()
            .any(|case| case["char"] == "y" && case["expected"]["applied"].as_bool().unwrap()),
        "expected applied y prevents pass by all fallback"
    );
    assert!(
        cases
            .iter()
            .any(|case| case["char"] == "W" && case["expected"]["applied"].as_bool().unwrap()),
        "expected applied W prevents pass by all fallback"
    );
    assert!(
        cases.iter().any(
            |case| case["codepoint"] == 0x34 && !case["expected"]["applied"].as_bool().unwrap()
        ),
        "invalid-candidate U+0034 falls back to upstream"
    );
}

#[test]
fn diagonal_width_port_parity() {
    let root = fixture();
    let references = root["references"].as_object().unwrap();
    assert_eq!(references.len(), 12, "one shared reference per cell");
    for case in root["cases"].as_array().unwrap() {
        let id = case["id"].as_str().unwrap();
        let source = parse_commands(&case["source"]);
        let upstream = parse_commands(&case["upstream"]);
        let reference: diagonal_fitting::Reference =
            serde_json::from_value(references[case["cell"].as_str().unwrap()].clone())
                .unwrap_or_else(|err| panic!("{id}: reference parses: {err}"));
        let native_axes = [
            case["native_axes"][0].as_bool().unwrap(),
            case["native_axes"][1].as_bool().unwrap(),
        ];
        let fit = match diagonal_fitting::fit(
            &source,
            &upstream,
            case["size_px"].as_f64().unwrap(),
            &reference,
            native_axes,
        ) {
            Ok(fit) => fit,
            Err(err) => panic!("{id}: fit errors: {err}"),
        };
        let expected = &case["expected"];
        assert_eq!(
            fit.applied,
            expected["applied"].as_bool().unwrap(),
            "{id}: applied"
        );
        assert_eq!(
            fit.reason,
            expected["reason"].as_str().unwrap(),
            "{id}: reason"
        );
        let got: Vec<(u8, Vec<u32>)> = fit.commands.iter().map(command_bits).collect();
        let want: Vec<(u8, Vec<u32>)> = parse_commands(&expected["commands"])
            .iter()
            .map(command_bits)
            .collect();
        assert_eq!(got, want, "{id}: exact command bits");
        let config = config_for(case);
        let scan = parse_scan(&case["font_scan"]);
        let raster = rasterize_candidate(
            &upstream,
            &fit.commands,
            &config,
            case["raster_policy"].as_str().unwrap(),
            scan.as_ref(),
        );
        assert_eq!(raster.pixels, bytes(&expected["pixels"]), "{id}: pixels");
        assert_eq!(
            raster.coverage,
            bytes(&expected["coverage"]),
            "{id}: coverage"
        );
        let frame = &expected["frame"];
        assert_eq!(
            raster.left,
            frame["left"].as_i64().unwrap() as i32,
            "{id}: left"
        );
        assert_eq!(
            raster.top,
            frame["top"].as_i64().unwrap() as i32,
            "{id}: top"
        );
        assert_eq!(
            raster.width,
            frame["width"].as_u64().unwrap() as u32,
            "{id}: width"
        );
        assert_eq!(
            raster.height,
            frame["height"].as_u64().unwrap() as u32,
            "{id}: height"
        );
    }
}
