//! Mechanical parity guard for the native curved-crossing port.
//!
//! Source: `experiments/hobby_fitting/curved_crossing.py` and its
//! `test_curved_crossing.py` family expectations (applied delivery keeps
//! Y, rounds X to 26.6, preserves substituted topology and stays inside
//! the movement budget; every unsupported input returns upstream
//! unchanged). The real-glyph cases replay the frozen approved packet
//! (`tests/fixtures/curved-crossing-packet.json`, sliced from the
//! reviewed `curved-crossing/review-final` oracle with its capture and
//! coverage-review reference) and require bit-exact commands. Tests
//! never establish optical acceptance.

#![cfg(feature = "candidate")]

use font_generator::diagonal_fitting::crossing;
use font_generator::fitting_source::SourceOutline;
use font_generator::probe::FittedCommand;
use font_generator::{diagonal_fitting, Config};
use serde_json::Value;

fn packet() -> Value {
    serde_json::from_str(include_str!("fixtures/curved-crossing-packet.json")).unwrap()
}

fn number(command: &Value, key: &str) -> f64 {
    command[key]
        .as_f64()
        .unwrap_or_else(|| panic!("missing {key} in {command}"))
}

fn fitted(command: &Value) -> FittedCommand {
    match command["op"].as_str().unwrap() {
        "move_to" => {
            FittedCommand::MoveTo(number(command, "x") as f32, number(command, "y") as f32)
        }
        "line_to" => {
            FittedCommand::LineTo(number(command, "x") as f32, number(command, "y") as f32)
        }
        "quad_to" => FittedCommand::QuadTo(
            number(command, "x1") as f32,
            number(command, "y1") as f32,
            number(command, "x") as f32,
            number(command, "y") as f32,
        ),
        "curve_to" => FittedCommand::CurveTo(
            number(command, "x1") as f32,
            number(command, "y1") as f32,
            number(command, "x2") as f32,
            number(command, "y2") as f32,
            number(command, "x") as f32,
            number(command, "y") as f32,
        ),
        "close" => FittedCommand::Close,
        op => panic!("unknown op {op}"),
    }
}

fn fitted_all(commands: &Value) -> Vec<FittedCommand> {
    commands.as_array().unwrap().iter().map(fitted).collect()
}

/// Parsed-shape JSON mirroring the prototype outline parser: exact f64
/// coordinates, no quantization.
fn raw_outline(commands: &Value) -> SourceOutline {
    let mut oncurve: Vec<[f64; 2]> = Vec::new();
    let mut offcurve: Vec<[f64; 2]> = Vec::new();
    let mut contours: Vec<Value> = Vec::new();
    let mut current: Vec<Value> = Vec::new();
    let mut pen: Option<usize> = None;
    let mut start: Option<usize> = None;
    for command in commands.as_array().unwrap() {
        match command["op"].as_str().unwrap() {
            "move_to" => {
                if !current.is_empty() {
                    contours.push(Value::Array(std::mem::take(&mut current)));
                }
                oncurve.push([number(command, "x"), number(command, "y")]);
                pen = Some(oncurve.len() - 1);
                start = pen;
            }
            "line_to" => {
                oncurve.push([number(command, "x"), number(command, "y")]);
                let next = oncurve.len() - 1;
                let from = pen.expect("line without pen");
                current.push(serde_json::json!({"Line": {"a": from, "b": next}}));
                pen = Some(next);
            }
            "quad_to" => {
                offcurve.push([number(command, "x1"), number(command, "y1")]);
                let control = offcurve.len() - 1;
                oncurve.push([number(command, "x"), number(command, "y")]);
                let next = oncurve.len() - 1;
                let from = pen.expect("quad without pen");
                current.push(serde_json::json!({"Quad": {"c": control, "a": from, "b": next}}));
                pen = Some(next);
            }
            "curve_to" => {
                offcurve.push([number(command, "x1"), number(command, "y1")]);
                let first = offcurve.len() - 1;
                offcurve.push([number(command, "x2"), number(command, "y2")]);
                let second = offcurve.len() - 1;
                oncurve.push([number(command, "x"), number(command, "y")]);
                let next = oncurve.len() - 1;
                let from = pen.expect("curve without pen");
                current.push(serde_json::json!({"Cubic": {
                    "c1": first, "c2": second, "a": from, "b": next
                }}));
                pen = Some(next);
            }
            "close" => {
                if let (Some(p), Some(s)) = (pen, start) {
                    if p != s {
                        current.push(serde_json::json!({"Line": {"a": p, "b": s}}));
                    }
                }
                if !current.is_empty() {
                    contours.push(Value::Array(std::mem::take(&mut current)));
                }
                pen = None;
                start = None;
            }
            op => panic!("unknown op {op}"),
        }
    }
    if !current.is_empty() {
        contours.push(Value::Array(current));
    }
    serde_json::from_value(serde_json::json!({
        "oncurve": oncurve,
        "offcurve": offcurve,
        "contours": contours,
    }))
    .expect("packet raw must parse")
}

fn glyph(
    packet: &Value,
    codepoint: &str,
) -> (SourceOutline, Vec<FittedCommand>, Vec<FittedCommand>) {
    let entry = &packet["glyphs"][codepoint];
    (
        raw_outline(&entry["raw_source"]),
        fitted_all(&entry["source"]),
        fitted_all(&entry["upstream"]),
    )
}

fn reference(packet: &Value) -> diagonal_fitting::Reference {
    serde_json::from_value(packet["reference"].clone()).expect("packet reference must parse")
}

fn native_axes(packet: &Value, codepoint: &str) -> [bool; 2] {
    let axes = packet["glyphs"][codepoint]["native_axes"]
        .as_array()
        .unwrap();
    [axes[0].as_bool().unwrap(), axes[1].as_bool().unwrap()]
}

fn expected(packet: &Value, codepoint: &str) -> (bool, String, Vec<FittedCommand>) {
    let entry = &packet["glyphs"][codepoint];
    (
        entry["expected_applied"].as_bool().unwrap(),
        entry["expected_reason"].as_str().unwrap().to_string(),
        fitted_all(&entry["expected_commands"]),
    )
}

/// Exact command identity: op plus every coordinate bit pattern.
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

fn on_grid(value: f32) -> bool {
    let scaled = value as f64 * 64.0;
    scaled == scaled.round()
}

/// Y coordinates and op structure must survive X-only movement intact.
fn assert_y_and_ops_equal(upstream: &[FittedCommand], candidate: &[FittedCommand]) {
    assert_eq!(upstream.len(), candidate.len());
    for (old, new) in upstream.iter().zip(candidate.iter()) {
        match (old, new) {
            (FittedCommand::MoveTo(_, oy), FittedCommand::MoveTo(_, y))
            | (FittedCommand::LineTo(_, oy), FittedCommand::LineTo(_, y)) => {
                assert_eq!(oy, y, "Y moved");
            }
            (FittedCommand::QuadTo(_, oy1, _, oy), FittedCommand::QuadTo(_, y1, _, y)) => {
                assert_eq!((oy1, oy), (y1, y), "Y moved");
            }
            (
                FittedCommand::CurveTo(_, oy1, _, oy2, _, oy),
                FittedCommand::CurveTo(_, y1, _, y2, _, y),
            ) => {
                assert_eq!((oy1, oy2, oy), (y1, y2, y), "Y moved");
            }
            (FittedCommand::Close, FittedCommand::Close) => {}
            _ => panic!("op changed: {old:?} -> {new:?}"),
        }
    }
}

const CLOSED_REASONS: &[&str] = &[
    "native-X-owned",
    "no-correspondence",
    "malformed-commands",
    "non-26.6-input",
    "no-reference-anchors",
    "no-attached-diagonals",
    "uncertified-substitution",
    "no-waist",
    "parity-ambiguous",
    "unsupported-crossing-class",
    "no-symmetry-matches",
    "phase-unconstrained",
    "no-free-controls",
    "weld-mismatch",
    "degenerate-joint",
    "degenerate-leg",
    "source-degenerate-curvature",
    "fixed-constraints-incompatible",
    "movement-budget-empty",
    "no-curve-constraints",
    "constraints-incompatible",
    "rounded-movement-budget",
    "rounded-hard-constraint",
    "joint-continuity",
    "curve-degenerate-leg",
    "curve-degenerate-curvature",
    "curve-curvature-sign",
    "curve-tangent-reversed",
    "clearance-station-disk-curve",
    "clearance-station-disk-line",
    "clearance-swept-fixed-curve",
    "y-changed",
    "cap-changed",
    "no-movement",
    "topology",
    "topology-captured",
    "oversize-outline",
];

#[test]
fn rejects_nonpositive_size() {
    let packet = packet();
    let (raw, source, upstream) = glyph(&packet, "120");
    let reference = reference(&packet);
    let result = crossing::fit(&raw, &source, &upstream, 0.0, &reference, [false, false]);
    assert!(result.is_err(), "nonpositive size must be an error");
}

#[test]
fn native_x_owned_abstains_exact() {
    // Synthetic outline: correspondence and grid hold, so only the
    // native-X ownership gate can fire.
    let packet = packet();
    let (raw, _, _) = glyph(&packet, "120");
    let reference = reference(&packet);
    let line: Vec<FittedCommand> = vec![
        FittedCommand::MoveTo(0.0, 0.0),
        FittedCommand::LineTo(64.0, 64.0),
        FittedCommand::Close,
    ];
    let result = crossing::fit(&raw, &line, &line, 16.0, &reference, [true, false]).unwrap();
    assert!(!result.applied);
    assert_eq!(result.reason, "native-X-owned");
    assert_eq!(result.commands, line);
}

#[test]
fn mismatched_correspondence_abstains_exact() {
    let packet = packet();
    let (raw, _, _) = glyph(&packet, "120");
    let reference = reference(&packet);
    let source = vec![
        FittedCommand::MoveTo(0.0, 0.0),
        FittedCommand::LineTo(64.0, 64.0),
        FittedCommand::Close,
    ];
    let upstream = vec![
        FittedCommand::MoveTo(0.0, 0.0),
        FittedCommand::QuadTo(32.0, 0.0, 64.0, 64.0),
        FittedCommand::Close,
    ];
    let result = crossing::fit(&raw, &source, &upstream, 16.0, &reference, [false, false]).unwrap();
    assert!(!result.applied);
    assert_eq!(result.reason, "no-correspondence");
    assert_eq!(result.commands, upstream);
}

#[test]
fn off_grid_input_abstains_exact() {
    // Packet captures nudged off the 26.6 grid; counts still match raw.
    let packet = packet();
    let (raw, source, _) = glyph(&packet, "120");
    let reference = reference(&packet);
    let mut upstream = source.clone();
    let mut nudged = false;
    for command in &mut upstream {
        if let FittedCommand::LineTo(x, _) = command {
            *x += 0.01;
            nudged = true;
            break;
        }
    }
    assert!(nudged);
    let result = crossing::fit(&raw, &source, &upstream, 16.0, &reference, [false, false]).unwrap();
    assert!(!result.applied);
    assert_eq!(result.reason, "non-26.6-input");
    assert_eq!(result.commands, upstream);
}

/// Strict oracle parity for one approved glyph: applied delivery must
/// match the frozen candidate bit-for-bit; abstention must keep the
/// exact upstream with a closed reason.
fn check_strict_case(codepoint: &str) {
    let packet = packet();
    let (raw, source, upstream) = glyph(&packet, codepoint);
    let reference = reference(&packet);
    let axes = native_axes(&packet, codepoint);
    let (expected_applied, expected_reason, expected_commands) = expected(&packet, codepoint);
    let size = packet["meta"]["size"].as_f64().unwrap();
    let result = crossing::fit(&raw, &source, &upstream, size, &reference, axes).unwrap();
    assert_eq!(result.applied, expected_applied, "reason={}", result.reason);
    if !expected_applied {
        assert_eq!(result.commands, upstream);
        assert!(
            CLOSED_REASONS.contains(&result.reason.as_str()),
            "unknown abstain reason {}",
            result.reason
        );
        return;
    }
    assert_eq!(result.reason, expected_reason);
    let actual: Vec<(u8, Vec<u32>)> = result.commands.iter().map(command_bits).collect();
    let wanted: Vec<(u8, Vec<u32>)> = expected_commands.iter().map(command_bits).collect();
    assert_eq!(actual, wanted, "candidate diverges from the frozen oracle");
    // Mechanical guards behind the strict identity.
    assert_y_and_ops_equal(&upstream, &result.commands);
    for command in &result.commands {
        match *command {
            FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => {
                assert!(on_grid(x) && on_grid(y));
            }
            FittedCommand::QuadTo(x1, y1, x, y) => {
                assert!(on_grid(x1) && on_grid(y1) && on_grid(x) && on_grid(y));
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                assert!(
                    on_grid(x1)
                        && on_grid(y1)
                        && on_grid(x2)
                        && on_grid(y2)
                        && on_grid(x)
                        && on_grid(y)
                );
            }
            FittedCommand::Close => {}
        }
    }
    let movement = result.diagnostics["movement"].as_f64().unwrap();
    let radius = result.diagnostics["radius"].as_f64().unwrap();
    assert!(movement.is_finite() && radius.is_finite() && radius > 0.0);
    assert!(
        movement <= radius,
        "movement {movement} exceeds radius {radius}"
    );
    assert!(result.diagnostics["parity_target"]
        .as_f64()
        .unwrap()
        .is_finite());
    assert!(result.diagnostics["matches"].as_u64().unwrap() >= 1);
    let arms = result.diagnostics["arms"].as_object().unwrap();
    assert!(arms.contains_key("rising") && arms.contains_key("falling"));
    // Source contrast is preserved, never forced symmetric.
    let rising = &arms["rising"];
    let falling = &arms["falling"];
    let src_ratio = rising["source"].as_f64().unwrap() / falling["source"].as_f64().unwrap();
    let cand_ratio = rising["candidate"].as_f64().unwrap() / falling["candidate"].as_f64().unwrap();
    assert!(
        (cand_ratio - src_ratio).abs() < (1.0 - src_ratio).abs(),
        "candidate ratio {cand_ratio} drifted from source {src_ratio}"
    );
    let _ = Config::default();
}

#[test]
fn real_source_sans_x_matches_oracle() {
    check_strict_case("120");
}

#[test]
fn real_source_sans_upper_x_matches_oracle() {
    check_strict_case("88");
}

#[test]
fn native_y_owned_still_applies_when_supported() {
    // Native Y ownership never blocks the X-only solve.
    let packet = packet();
    let (raw, source, upstream) = glyph(&packet, "120");
    let reference = reference(&packet);
    let plain = crossing::fit(&raw, &source, &upstream, 16.0, &reference, [false, false]).unwrap();
    let owned = crossing::fit(&raw, &source, &upstream, 16.0, &reference, [false, true]).unwrap();
    assert_eq!(plain.applied, owned.applied);
    if owned.applied {
        assert_eq!(owned.commands, plain.commands);
    } else {
        assert_eq!(owned.commands, upstream);
    }
}
