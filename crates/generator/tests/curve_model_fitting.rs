//! Parity tests for the maintained curved-stroke horizontal completion.
//!
//! The focus glyph is the real SourceSans3 `s` at 16px/400 (unhinted
//! source, fitted preferred and fifteen-donor reference from the frozen
//! packet): the harness pins the
//! exact certified-pair count, joint-row count and movement budget from
//! the independent Python capture, then enforces primal ownership (fixed Y,
//! 26.6 X grid, preserved ops) on application and exact preferred-stream
//! preservation on every abstention. Synthetic controls cover the
//! remaining unsupported-stage gates; none of them invent preferred
//! pixels (abstention output must equal the preferred input bit-for-bit).
#![cfg(feature = "candidate")]

use font_generator::diagonal_fitting::{self, curve_model};
use font_generator::probe::FittedCommand;
use serde_json::Value;

const SIZE_PX: f64 = 16.0;

fn packet(index: usize) -> Value {
    serde_json::from_str::<Value>(include_str!("fixtures/curve-model-packet.json")).unwrap()[index]
        .clone()
}

fn attachment_reference(index: usize) -> Value {
    serde_json::from_str::<Value>(include_str!("fixtures/curve-attachment-reference.json")).unwrap()
        ["cases"][index]
        .clone()
}

fn parse_commands(commands: &Value) -> Vec<FittedCommand> {
    commands
        .as_array()
        .unwrap()
        .iter()
        .map(|c| {
            let coord = |key: &str| {
                let value = c[key].as_f64().unwrap() as f32;
                assert_eq!(
                    value.to_bits(),
                    c[format!("{key}_bits")].as_u64().unwrap() as u32
                );
                value
            };
            match c["op"].as_str().unwrap() {
                "move_to" => FittedCommand::MoveTo(coord("x"), coord("y")),
                "line_to" => FittedCommand::LineTo(coord("x"), coord("y")),
                "quad_to" => {
                    FittedCommand::QuadTo(coord("x1"), coord("y1"), coord("x"), coord("y"))
                }
                "curve_to" => FittedCommand::CurveTo(
                    coord("x1"),
                    coord("y1"),
                    coord("x2"),
                    coord("y2"),
                    coord("x"),
                    coord("y"),
                ),
                "close" => FittedCommand::Close,
                op => panic!("unknown op {op}"),
            }
        })
        .collect()
}

fn focus_commands() -> (Vec<FittedCommand>, Vec<FittedCommand>) {
    let p = packet(0);
    (
        parse_commands(&p["source"]),
        parse_commands(&p["preferred"]),
    )
}

fn donor_reference() -> diagonal_fitting::Reference {
    serde_json::from_value(packet(0)["reference"].clone()).unwrap()
}

fn on_coords(commands: &[FittedCommand]) -> Vec<(f32, f32)> {
    commands
        .iter()
        .filter_map(|command| match *command {
            FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => Some((x, y)),
            FittedCommand::QuadTo(_, _, x, y) | FittedCommand::CurveTo(_, _, _, _, x, y) => {
                Some((x, y))
            }
            FittedCommand::Close => None,
        })
        .collect()
}

fn op_tags(commands: &[FittedCommand]) -> Vec<&'static str> {
    commands
        .iter()
        .map(|command| match command {
            FittedCommand::MoveTo(..) => "move_to",
            FittedCommand::LineTo(..) => "line_to",
            FittedCommand::QuadTo(..) => "quad_to",
            FittedCommand::CurveTo(..) => "curve_to",
            FittedCommand::Close => "close",
        })
        .collect()
}

fn global_coords(commands: &[FittedCommand]) -> Vec<(f32, f32)> {
    let mut coords = on_coords(commands);
    for cmd in commands {
        match *cmd {
            FittedCommand::QuadTo(x, y, ..) => coords.push((x, y)),
            FittedCommand::CurveTo(x1, y1, x2, y2, ..) => {
                coords.extend([(x1, y1), (x2, y2)]);
            }
            _ => {}
        }
    }
    coords
}

/// Real mixed-outline source: tiny vertical terminal segments cannot
/// exclude the interior stroke. Hersch section 2 attachment polynomials
/// and every retained Y remain exact; the independent Python/CGAL result
/// verifies width fitting without declaring a preferred bitmap optically.
#[test]
fn roboto_flex_curve_width_preserves_whole_attachments_and_matches_reference() {
    let p = attachment_reference(2);
    let source = parse_commands(&p["source"]);
    let preferred = parse_commands(&p["preferred"]);
    let reference = serde_json::from_value(p["reference"].clone()).unwrap();
    let fit =
        curve_model::fit_horizontal(&source, &preferred, 16.0, &reference, [false, false]).unwrap();
    assert!(fit.applied, "{}", fit.reason);
    assert_eq!(fit.commands, parse_commands(&p["expected"]));
    assert_eq!(fit.diagnostics["n_pairs"], p["diagnostics"]["n_pairs"]);
    assert_eq!(
        fit.diagnostics["attachment_controls"],
        p["diagnostics"]["attachment_controls"]
    );
    let before = global_coords(&preferred);
    let after = global_coords(&fit.commands);
    assert_eq!(before.len(), after.len());
    for (old, new) in before.iter().zip(&after) {
        assert_eq!(old.1.to_bits(), new.1.to_bits());
    }
    for v in fit.diagnostics["attachment_controls"].as_array().unwrap() {
        let v = v.as_u64().unwrap() as usize;
        assert_eq!(before[v].0.to_bits(), after[v].0.to_bits());
    }
    assert_ne!(after, before);
    for row in fit.diagnostics["pairs"].as_array().unwrap() {
        assert!(row["candidate"].as_f64().unwrap() > 0.0);
    }
    // Native X ownership leaves no movable coordinate; the full upstream
    // stream, including collapsed source-line operators, stays intact.
    let fixed =
        curve_model::fit_horizontal(&source, &preferred, 16.0, &reference, [true, false]).unwrap();
    assert!(!fixed.applied);
    assert_eq!(fixed.commands, preferred);
}

/// Real `s`: certified recognition and movement budget match the approved
/// Python attachment reference exactly; application additionally preserves the primal
/// ownership contract, abstention preserves the preferred stream.
#[test]
fn focus_s_real_path_matches_capture() {
    let (source, preferred) = focus_commands();
    let reference = donor_reference();
    let fit = curve_model::fit_horizontal(&source, &preferred, SIZE_PX, &reference, [false, false])
        .expect("stage runs on real input");
    let diagnostics = &fit.diagnostics;
    assert_eq!(diagnostics["n_pairs"], serde_json::json!(4));
    assert_eq!(
        diagnostics["n_joints"],
        attachment_reference(0)["diagnostics"]["n_joints"]
    );
    let bound = diagnostics["bound"].as_f64().unwrap();
    assert!(
        (bound - 0.47022060570471835).abs() < 1e-12,
        "movement budget matches capture, got {bound}"
    );
    assert!(fit.applied, "certified real curve must fit: {}", fit.reason);
    assert_eq!(
        fit.commands,
        parse_commands(&attachment_reference(0)["expected"])
    );
    assert_eq!(fit.reason, "fitted");
    assert_eq!(fit.commands.len(), preferred.len());
    assert_eq!(op_tags(&fit.commands), op_tags(&preferred));
    let up = on_coords(&preferred);
    let got = on_coords(&fit.commands);
    assert_eq!(got.len(), up.len());
    for ((gx, gy), (_, uy)) in got.iter().zip(up.iter()) {
        assert_eq!(gy, uy, "retained Y stays bit-identical");
        let snapped = (gx * 64.0).round() / 64.0;
        assert_eq!(*gx, snapped, "moved X stays on the 26.6 grid");
    }
    let peak = diagnostics["peak"].as_f64().unwrap();
    assert!(peak <= bound, "peak displacement respects budget");
}

#[test]
fn source_contacts_use_the_exact_quadratic_distance_certificate() {
    let p = packet(1);
    let source = parse_commands(&p["source"]);
    let preferred = parse_commands(&p["preferred"]);
    let reference = serde_json::from_value(p["reference"].clone()).unwrap();
    let fit =
        curve_model::fit_horizontal(&source, &preferred, 14.0, &reference, [false, false]).unwrap();
    assert!(
        fit.applied,
        "certified source contacts must fit: {}",
        fit.reason
    );
    assert_eq!(fit.diagnostics["n_pairs"], p["diagnostics"]["n_pairs"]);
    assert_eq!(
        fit.commands,
        parse_commands(&attachment_reference(1)["expected"])
    );
    assert_eq!(
        fit.diagnostics["n_joints"],
        attachment_reference(1)["diagnostics"]["n_joints"]
    );
    for ((_, y), (_, old_y)) in on_coords(&fit.commands)
        .iter()
        .zip(on_coords(&preferred).iter())
    {
        assert_eq!(y.to_bits(), old_y.to_bits());
    }
    // The prototype bounded solver's primal feasibility band is 1e-9.
    // A mathematically active box side can differ by floating roundoff.
    assert!(
        fit.diagnostics["peak"].as_f64().unwrap()
            <= fit.diagnostics["bound"].as_f64().unwrap() + 1e-9
    );
}

/// Native X owned leaves no free controls on the retained-Y stage.
#[test]
fn native_x_owned_has_no_free_controls() {
    let (source, preferred) = focus_commands();
    let reference = donor_reference();
    let fit = curve_model::fit_horizontal(&source, &preferred, SIZE_PX, &reference, [true, false])
        .expect("stage runs on real input");
    assert!(!fit.applied);
    assert_eq!(fit.reason, "no-free-controls");
    assert_eq!(fit.commands, preferred);
}

fn synthetic_preferred(commands: Vec<FittedCommand>) -> Vec<FittedCommand> {
    commands
}

/// A single attachment curve has no opposing curved stroke to fit.
#[test]
fn upright_source_preserves_preferred() {
    let source = vec![
        FittedCommand::MoveTo(0.0, 0.0),
        FittedCommand::LineTo(0.0, 4.0),
        FittedCommand::QuadTo(2.0, 5.0, 4.0, 4.0),
        FittedCommand::LineTo(4.0, 0.0),
        FittedCommand::Close,
    ];
    let preferred = synthetic_preferred(source.clone());
    let reference = donor_reference();
    let fit = curve_model::fit_horizontal(&source, &preferred, SIZE_PX, &reference, [false, false])
        .expect("stage runs");
    assert!(!fit.applied);
    assert_eq!(fit.reason, "no-certified-pairs");
    assert_eq!(fit.commands, preferred);
}

/// Multi-contour, cubic and correspondence failures preserve the stream.
#[test]
fn unsupported_geometry_preserves_preferred() {
    let reference = donor_reference();
    let two = vec![
        FittedCommand::MoveTo(0.0, 0.0),
        FittedCommand::LineTo(1.0, 0.0),
        FittedCommand::Close,
        FittedCommand::MoveTo(2.0, 0.0),
        FittedCommand::LineTo(3.0, 0.0),
        FittedCommand::Close,
    ];
    let fit = curve_model::fit_horizontal(&two, &two.clone(), SIZE_PX, &reference, [false, false])
        .expect("stage runs");
    assert!(!fit.applied);
    assert_eq!(fit.reason, "no-certified-pairs");
    assert_eq!(fit.commands, two);

    let cubic = vec![
        FittedCommand::MoveTo(0.0, 0.0),
        FittedCommand::CurveTo(1.0, 0.0, 2.0, 1.0, 3.0, 1.0),
        FittedCommand::Close,
    ];
    let fit =
        curve_model::fit_horizontal(&cubic, &cubic.clone(), SIZE_PX, &reference, [false, false])
            .expect("stage runs");
    assert!(!fit.applied);
    assert_eq!(fit.reason, "cubic-curve-present");
    assert_eq!(fit.commands, cubic);

    let mismatched = vec![
        FittedCommand::MoveTo(0.0, 0.0),
        FittedCommand::LineTo(2.0, 0.0),
        FittedCommand::Close,
    ];
    let longer = vec![
        FittedCommand::MoveTo(0.0, 0.0),
        FittedCommand::LineTo(2.0, 0.0),
        FittedCommand::LineTo(2.0, 2.0),
        FittedCommand::Close,
    ];
    let fit =
        curve_model::fit_horizontal(&mismatched, &longer, SIZE_PX, &reference, [false, false])
            .expect("stage runs");
    assert!(!fit.applied);
    assert_eq!(fit.reason, "no-correspondence");
    assert_eq!(fit.commands, longer);
}

/// Straight-only outlines certify no curve pairs.
#[test]
fn straight_only_has_no_certified_pairs() {
    let square = vec![
        FittedCommand::MoveTo(0.0, 0.0),
        FittedCommand::LineTo(4.0, 0.0),
        FittedCommand::LineTo(4.0, 4.0),
        FittedCommand::LineTo(0.0, 4.0),
        FittedCommand::Close,
    ];
    let reference = donor_reference();
    let fit = curve_model::fit_horizontal(
        &square,
        &square.clone(),
        SIZE_PX,
        &reference,
        [false, false],
    )
    .expect("stage runs");
    assert!(!fit.applied);
    assert_eq!(fit.reason, "no-certified-pairs");
    assert_eq!(fit.commands, square);
}

/// Empty references and non-finite sizes are contract errors, not fits.
#[test]
fn empty_reference_and_bad_size_fail_closed() {
    let square = vec![
        FittedCommand::MoveTo(0.0, 0.0),
        FittedCommand::LineTo(4.0, 0.0),
        FittedCommand::LineTo(4.0, 4.0),
        FittedCommand::Close,
    ];
    let empty = diagonal_fitting::Reference {
        anchors: Vec::new(),
        size_px: SIZE_PX,
        records: 0,
        n_anchors: 0,
        rel_min: None,
        rel_max: None,
        notes: Vec::new(),
    };
    let fit =
        curve_model::fit_horizontal(&square, &square.clone(), SIZE_PX, &empty, [false, false])
            .expect("stage runs");
    assert!(!fit.applied);
    assert_eq!(fit.reason, "no-reference-anchors");
    assert_eq!(fit.commands, square);

    let reference = donor_reference();
    assert!(
        curve_model::fit_horizontal(&square, &square, 0.0, &reference, [false, false]).is_err()
    );
    assert!(
        curve_model::fit_horizontal(&square, &square, f64::NAN, &reference, [false, false])
            .is_err()
    );
}
