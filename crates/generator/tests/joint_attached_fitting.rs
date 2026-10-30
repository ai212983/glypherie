#![cfg(feature = "candidate")]
//! Geometry and ownership gates for the joint and attached diagonal fits.
//!
//! These tests pin the fail-closed contract shared by both models: malformed
//! or out-of-range input is an error, unsupported geometry abstains with the
//! exact upstream commands, and native-owned axes are never moved. Full
//! packet parity runs in the parent-owned fixture harness, not here; no
//! optical claim follows from these mechanical gates.
use font_generator::{
    diagonal_fitting::{attached, joint, Reference},
    probe::FittedCommand,
};

fn empty_reference() -> Reference {
    Reference {
        anchors: vec![],
        size_px: 16.0,
        records: 0,
        n_anchors: 0,
        rel_min: None,
        rel_max: None,
        notes: vec![],
    }
}

fn square() -> Vec<FittedCommand> {
    vec![
        FittedCommand::MoveTo(0.0, 0.0),
        FittedCommand::LineTo(64.0, 0.0),
        FittedCommand::LineTo(64.0, 64.0),
        FittedCommand::LineTo(0.0, 64.0),
        FittedCommand::Close,
    ]
}

fn with_quad() -> Vec<FittedCommand> {
    vec![
        FittedCommand::MoveTo(0.0, 0.0),
        FittedCommand::LineTo(64.0, 0.0),
        FittedCommand::QuadTo(64.0, 64.0, 0.0, 64.0),
        FittedCommand::Close,
    ]
}

#[test]
fn joint_rejects_empty_reference_with_exact_upstream() {
    let outline = square();
    let result = joint::fit(&outline, &outline, 16.0, &empty_reference(), [false, false]).unwrap();
    assert!(!result.applied);
    assert_eq!(result.reason, "no-reference-anchors");
    assert_eq!(result.commands, outline);
}

#[test]
fn joint_rejects_curves_before_reference() {
    let outline = with_quad();
    let result = joint::fit(&outline, &outline, 16.0, &empty_reference(), [false, false]).unwrap();
    assert!(!result.applied);
    assert_eq!(result.reason, "curves-unsupported");
    assert_eq!(result.commands, outline);
}

#[test]
fn joint_rejects_mismatched_correspondence() {
    let a = square();
    let mut b = square();
    b.pop();
    let result = joint::fit(&a, &b, 16.0, &empty_reference(), [false, false]).unwrap();
    assert!(!result.applied);
    assert_eq!(result.reason, "no-correspondence");
    assert_eq!(result.commands, b);
}

#[test]
fn joint_rejects_nonpositive_size() {
    let outline = square();
    assert!(joint::fit(&outline, &outline, 0.0, &empty_reference(), [false, false]).is_err());
    assert!(joint::fit(
        &outline,
        &outline,
        f64::NAN,
        &empty_reference(),
        [false, false]
    )
    .is_err());
}

#[test]
fn attached_honors_native_x_ownership() {
    let outline = square();
    let result =
        attached::fit(&outline, &outline, 16.0, &empty_reference(), [true, false]).unwrap();
    assert!(!result.applied);
    assert_eq!(result.reason, "native-X-owned");
    assert_eq!(result.commands, outline);
}

#[test]
fn attached_rejects_empty_reference_with_exact_upstream() {
    let outline = square();
    let result =
        attached::fit(&outline, &outline, 16.0, &empty_reference(), [false, false]).unwrap();
    assert!(!result.applied);
    assert_eq!(result.reason, "no-reference-anchors");
    assert_eq!(result.commands, outline);
}

#[test]
fn attached_rejects_mismatched_correspondence() {
    let a = square();
    let mut b = square();
    b.pop();
    let result = attached::fit(&a, &b, 16.0, &empty_reference(), [false, false]).unwrap();
    assert!(!result.applied);
    assert_eq!(result.reason, "no-correspondence");
    assert_eq!(result.commands, b);
}

#[test]
fn attached_rejects_nonpositive_size() {
    let outline = square();
    assert!(attached::fit(&outline, &outline, 0.0, &empty_reference(), [false, false]).is_err());
}

fn parse_command(v: &serde_json::Value) -> FittedCommand {
    let get = |k: &str| v[k].as_f64().unwrap() as f32;
    match v["op"].as_str().unwrap() {
        "move_to" => FittedCommand::MoveTo(get("x"), get("y")),
        "line_to" => FittedCommand::LineTo(get("x"), get("y")),
        "quad_to" => FittedCommand::QuadTo(get("x1"), get("y1"), get("x"), get("y")),
        "curve_to" => FittedCommand::CurveTo(
            get("x1"),
            get("y1"),
            get("x2"),
            get("y2"),
            get("x"),
            get("y"),
        ),
        "close" => FittedCommand::Close,
        op => panic!("unknown op {op}"),
    }
}

fn parse_commands(v: &serde_json::Value) -> Vec<FittedCommand> {
    v.as_array().unwrap().iter().map(parse_command).collect()
}

/// Frozen stage-packet parity: the approved joint and attached deliveries
/// must reproduce bit-for-bit from the frozen source, upstream outline and
/// reference anchors. Any rounding-level divergence against the frozen
/// candidate is a diagnosed model mismatch, never adjusted here.
#[test]
fn frozen_stage_cells_reproduce_exactly() {
    let fixture: serde_json::Value =
        serde_json::from_str(include_str!("fixtures/joint-attached-fitting.json")).unwrap();
    let cases = fixture["cases"].as_array().unwrap();
    assert!(!cases.is_empty());
    for case in cases {
        let mode = case["mode"].as_str().unwrap();
        let source = parse_commands(&case["source"]);
        let upstream = parse_commands(&case["upstream"]);
        let reference: font_generator::diagonal_fitting::Reference =
            serde_json::from_value(case["reference"].clone()).unwrap();
        let axes = case["native_axes"].as_array().unwrap();
        let native_axes = [axes[0].as_bool().unwrap(), axes[1].as_bool().unwrap()];
        let size_px = case["size_px"].as_f64().unwrap();
        let result = match mode {
            "joint" => joint::fit(&source, &upstream, size_px, &reference, native_axes),
            "attached" => attached::fit(&source, &upstream, size_px, &reference, native_axes),
            other => panic!("unknown mode {other}"),
        }
        .unwrap();
        let expected = parse_commands(&case["expected"]["candidate"]);
        assert!(
            result.applied,
            "{} {}: abstained with {}",
            mode, case["char"], result.reason
        );
        assert_eq!(result.reason, case["expected"]["reason"].as_str().unwrap());
        assert_eq!(result.commands, expected, "{} {}", mode, case["char"]);
    }
}

#[test]
fn attached_rejects_off_grid_input() {
    // 0.1 px is not a 26.6 quantum: the source grid contract fails closed.
    // A stub anchor carries the fit past the reference gate so the grid
    // gate itself is what abstains.
    let mut reference = empty_reference();
    reference
        .anchors
        .push(font_generator::diagonal_fitting::Anchor {
            source_width: 4.0,
            fitted_width: 4.0,
            rel: 0.0,
            length: 8.0,
            tangent: [0.0, 1.0],
            source_ids: "stub".to_string(),
            cert: None,
        });
    let mut outline = square();
    outline[1] = FittedCommand::LineTo(0.1, 0.0);
    let result = attached::fit(&outline, &outline, 16.0, &reference, [false, false]).unwrap();
    assert!(!result.applied);
    assert_eq!(result.reason, "non-26.6-input");
    assert_eq!(result.commands, outline);
}
