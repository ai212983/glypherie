#![cfg(feature = "candidate")]
//! Native port parity for terminal reference-height constraints.
//!
//! Source: the frozen approved 8913 terminal packet (real `A`/`y` records
//! from `SourceSans3-400-16-selective_default` plus its coverage-review
//! reference cell), embedded in `fixtures/terminal-fitting.json` for
//! hermetic replay. Invariant: supported fits reproduce the approved
//! delivered commands bit-for-bit; anything else returns the exact upstream
//! outline. Synthetic controls cover cap/upright recognition, abstention and
//! finite-input gates. Bitmap parity across the full matrix stays with the
//! parent harness; this file checks delivered commands and geometry.

use font_generator::{
    diagonal_fitting::{
        terminal::{detect_caps, detect_uprights, fit_terminal, parse_raw, RawCommand},
        Anchor, RawOutline, Reference,
    },
    probe::FittedCommand,
};
use serde_json::Value;

fn fixture() -> Value {
    serde_json::from_str(include_str!("fixtures/terminal-fitting.json")).unwrap()
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

fn num(command: &Value, key: &str) -> f64 {
    command[key].as_f64().unwrap()
}

fn parse_raw_commands(commands: &Value) -> Vec<RawCommand> {
    commands
        .as_array()
        .unwrap()
        .iter()
        .map(|command| match command["op"].as_str().unwrap() {
            "move_to" => RawCommand::MoveTo([num(command, "x"), num(command, "y")]),
            "line_to" => RawCommand::LineTo([num(command, "x"), num(command, "y")]),
            "quad_to" => RawCommand::QuadTo(
                [num(command, "x1"), num(command, "y1")],
                [num(command, "x"), num(command, "y")],
            ),
            "curve_to" => RawCommand::CurveTo(
                [num(command, "x1"), num(command, "y1")],
                [num(command, "x2"), num(command, "y2")],
                [num(command, "x"), num(command, "y")],
            ),
            "close" => RawCommand::Close,
            op => panic!("unknown op {op}"),
        })
        .collect()
}

fn reference_of(root: &Value) -> Reference {
    let raw = &root["reference"];
    Reference {
        anchors: raw["anchors"]
            .as_array()
            .unwrap()
            .iter()
            .map(|a| Anchor {
                source_width: a["source_width"].as_f64().unwrap(),
                fitted_width: a["fitted_width"].as_f64().unwrap(),
                rel: a["rel"].as_f64().unwrap(),
                length: a["length"].as_f64().unwrap(),
                tangent: [
                    a["tangent"][0].as_f64().unwrap(),
                    a["tangent"][1].as_f64().unwrap(),
                ],
                source_ids: a["source_ids"].as_str().unwrap().to_string(),
            })
            .collect(),
        size_px: raw["size_px"].as_f64().unwrap(),
        records: raw["records"].as_u64().unwrap() as usize,
        n_anchors: raw["n_anchors"].as_u64().unwrap() as usize,
        rel_min: raw["rel_min"].as_f64(),
        rel_max: raw["rel_max"].as_f64(),
        notes: Vec::new(),
    }
}

fn case_of(
    root: &Value,
    glyph: &str,
) -> (
    RawOutline,
    Vec<FittedCommand>,
    Vec<FittedCommand>,
    [bool; 2],
) {
    let case = &root["cases"][glyph];
    let raw = parse_raw(&parse_raw_commands(&case["raw_source"])).unwrap();
    let source = parse_commands(&case["source"]);
    let upstream = parse_commands(&case["upstream"]);
    let axes = &case["native_axes"];
    (
        raw,
        source,
        upstream,
        [axes[0].as_bool().unwrap(), axes[1].as_bool().unwrap()],
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

fn oncurve_positions(commands: &[FittedCommand]) -> Vec<Option<usize>> {
    let mut table = Vec::new();
    let mut next = 0usize;
    for command in commands {
        match command {
            FittedCommand::MoveTo(..)
            | FittedCommand::LineTo(..)
            | FittedCommand::QuadTo(..)
            | FittedCommand::CurveTo(..) => {
                table.push(Some(next));
                next += 1;
            }
            FittedCommand::Close => table.push(None),
        }
    }
    table
}

fn check_real_glyph(glyph: &str) {
    let root = fixture();
    let size_px = root["size_px"].as_f64().unwrap();
    let reference = reference_of(&root);
    let (raw, source, upstream, axes) = case_of(&root, glyph);
    let expected = &root["cases"][glyph]["expected"];
    let result = fit_terminal(&raw, &source, &upstream, size_px, &reference, axes);
    assert_eq!(result.applied, expected["applied"].as_bool().unwrap());
    assert_eq!(result.reason, expected["reason"].as_str().unwrap());
    let want = parse_commands(&expected["candidate"]);
    assert_eq!(
        result.commands.iter().map(command_bits).collect::<Vec<_>>(),
        want.iter().map(command_bits).collect::<Vec<_>>(),
        "delivered commands match the approved packet for {glyph}"
    );
    let diagnostics = &result.diagnostics;
    let cap_vertices: Vec<usize> = expected["cap_vertices"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_u64().unwrap() as usize)
        .collect();
    assert_eq!(
        diagnostics["cap_vertices"],
        serde_json::json!(cap_vertices),
        "affected cap vertices match for {glyph}"
    );
    let up_vertices: Vec<usize> = expected["upright_vertices"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_u64().unwrap() as usize)
        .collect();
    assert_eq!(
        diagnostics["upright_vertices"],
        serde_json::json!(up_vertices)
    );
    let validity = &diagnostics["validity"];
    assert_eq!(validity["ok"], true);
    assert_eq!(validity["cap_exact"], true);
    assert_eq!(validity["weld_exact"], true);
    assert_eq!(validity["upright_exact"], true);
    assert_eq!(validity["curve_sweep"], serde_json::json!("clear"));
    assert_eq!(validity["cost_ok"], true);
    assert!(
        validity["cost_candidate"].as_f64().unwrap() < validity["cost_upstream"].as_f64().unwrap()
    );
    assert!(diagnostics["movement"].as_f64().unwrap() <= diagnostics["bound"].as_f64().unwrap());
    // Only unpinned vertices may move: caps hold Y, uprights hold X, anchors
    // hold both, native axes hold their axis.
    let fixed: Vec<usize> = diagnostics["fixed"]["anchors"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_u64().unwrap() as usize)
        .collect();
    let positions = oncurve_positions(&upstream);
    for (pos, (got, old)) in result.commands.iter().zip(upstream.iter()).enumerate() {
        if command_bits(got) != command_bits(old) {
            let idx = positions[pos].unwrap();
            assert!(
                !fixed.contains(&idx),
                "moved vertex {idx} must not be pinned for {glyph}"
            );
        }
    }
    // Cap heights and upright X coordinates stay at upstream exactly.
    let up_parsed: Vec<[f64; 2]> = upstream
        .iter()
        .filter_map(|c| match *c {
            FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => Some([x as f64, y as f64]),
            FittedCommand::QuadTo(_, _, x, y) | FittedCommand::CurveTo(_, _, _, _, x, y) => {
                Some([x as f64, y as f64])
            }
            FittedCommand::Close => None,
        })
        .collect();
    let cand_parsed: Vec<[f64; 2]> = result
        .commands
        .iter()
        .filter_map(|c| match *c {
            FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => Some([x as f64, y as f64]),
            FittedCommand::QuadTo(_, _, x, y) | FittedCommand::CurveTo(_, _, _, _, x, y) => {
                Some([x as f64, y as f64])
            }
            FittedCommand::Close => None,
        })
        .collect();
    for &v in &cap_vertices {
        assert_eq!(
            cand_parsed[v][1], up_parsed[v][1],
            "cap Y exact for {glyph}"
        );
    }
    for &v in &up_vertices {
        assert_eq!(
            cand_parsed[v][0], up_parsed[v][0],
            "upright X exact for {glyph}"
        );
    }
    // Coupled narrowing toward the anchor change, not pixel identity.
    let widths = &diagnostics["widths"];
    assert!(widths["candidate"].as_f64().unwrap() < widths["upstream"].as_f64().unwrap());
}

#[test]
fn real_a_reproduces_approved_fit() {
    check_real_glyph("A");
}

#[test]
fn real_y_reproduces_approved_fit() {
    check_real_glyph("y");
}

/// The right-arm cap of k lies below its ascender. Hobby 3.3 preserves
/// local horizontal reference phase even when another feature extends
/// higher. The independent Python/CGAL reference verifies the constrained
/// width solve, rather than a preferred pixel count.
#[test]
fn local_cap_below_ascender_keeps_both_upstream_heights() {
    let packet: Value =
        serde_json::from_str(include_str!("fixtures/local-reference-height.json")).unwrap();
    let raw = parse_raw(&parse_raw_commands(&packet["raw_source"])).unwrap();
    let source = parse_commands(&packet["source"]);
    let upstream = parse_commands(&packet["upstream"]);
    let reference = serde_json::from_value(packet["reference"].clone()).unwrap();
    let result = fit_terminal(&raw, &source, &upstream, 16.0, &reference, [false; 2]);
    assert!(result.applied, "{}", result.reason);
    assert_eq!(result.commands, parse_commands(&packet["expected"]));
    let cap = detect_caps(&raw, &raw)
        .0
        .into_iter()
        .find(|c| c.vertices == (3, 4))
        .unwrap();
    assert_eq!(
        cap.plane,
        font_generator::diagonal_fitting::terminal::Plane::Interior
    );
    let positions = |commands: &[FittedCommand]| {
        commands
            .iter()
            .filter_map(|c| match *c {
                FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => Some((x, y)),
                FittedCommand::QuadTo(_, _, x, y) | FittedCommand::CurveTo(_, _, _, _, x, y) => {
                    Some((x, y))
                }
                FittedCommand::Close => None,
            })
            .collect::<Vec<_>>()
    };
    let up = positions(&upstream);
    let got = positions(&result.commands);
    for v in [3, 4] {
        assert_eq!(got[v].1.to_bits(), up[v].1.to_bits());
    }
    assert_ne!(
        got[3].0, up[3].0,
        "width correction remains active at the retained height"
    );
    let shift = |mut p: RawOutline| {
        for v in p.oncurve.iter_mut().chain(&mut p.offcurve) {
            v[0] += 3.0;
            v[1] += 5.0;
        }
        p
    };
    let transformed = shift(raw.clone());
    let transformed_caps = detect_caps(&transformed, &transformed).0;
    let local = transformed_caps
        .iter()
        .find(|c| c.vertices == cap.vertices)
        .unwrap();
    assert_eq!(local.plane, cap.plane);
    assert_eq!(local.source_y, cap.source_y + 5.0);
}

#[test]
fn flat_reference_edges_keep_original_fitted_heights_below_other_controls() {
    let raw = parse_raw(&[
        RawCommand::MoveTo([0.0, 0.0]),
        RawCommand::LineTo([4.0, 0.0]),
        RawCommand::LineTo([4.0, 4.0]),
        RawCommand::LineTo([0.0, 4.0]),
        RawCommand::Close,
    ])
    .unwrap();
    let mut up = raw.clone();
    for p in &mut up.oncurve {
        p[1] += 2.0;
    }
    let caps = detect_caps(&raw, &up).0;
    assert_eq!(caps.len(), 2);
    assert_eq!(caps[0].source_y, 0.0);
    assert_eq!(caps[0].upstream_y, 2.0);
    assert_eq!(caps[1].source_y, 4.0);
    assert_eq!(caps[1].upstream_y, 6.0);
    up.oncurve[1][1] += 1.0 / 64.0;
    assert_eq!(detect_caps(&raw, &up).0.len(), 1);
    let mut hull = raw.clone();
    hull.offcurve.push([2.0, 5.0]);
    // Hobby 3.3: a different feature above this horizontal region cannot
    // release its fitted height. The control box is diagnostic only.
    let caps = detect_caps(&hull, &raw).0;
    assert_eq!(caps.len(), 2);
    assert_eq!(
        caps[1].plane,
        font_generator::diagonal_fitting::terminal::Plane::Interior
    );
}

#[test]
fn raw_upright_recognition_ignores_slants_and_ambiguous_fitted_positions() {
    let raw = parse_raw(&[
        RawCommand::MoveTo([0.0, 0.0]),
        RawCommand::LineTo([1.0, 2.0]),
        RawCommand::LineTo([1.0, 4.0]),
        RawCommand::Close,
    ])
    .unwrap();
    let mut up = raw.clone();
    assert_eq!(detect_uprights(&raw, &up).len(), 1);
    up.oncurve[2][0] += 1.0 / 64.0;
    assert!(detect_uprights(&raw, &up).is_empty());
}

#[test]
fn native_y_ownership_and_nonfinite_raw_keep_exact_upstream() {
    let fixture = fixture();
    let reference = reference_of(&fixture);
    let (mut raw, source, upstream, _) = case_of(&fixture, "y");
    let held = fit_terminal(&raw, &source, &upstream, 16.0, &reference, [false, true]);
    assert!(!held.applied);
    assert_eq!(held.commands, upstream);
    raw.oncurve[0][0] = f64::NAN;
    let invalid = fit_terminal(&raw, &source, &upstream, 16.0, &reference, [false, false]);
    assert!(!invalid.applied);
    assert_eq!(invalid.commands, upstream);
}
