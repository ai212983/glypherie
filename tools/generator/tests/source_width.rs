//! Integration tests for the straight source-relative width fitter.
//!
//! Source: Hobby (4) width as twice the medial radius, (5) relative
//! projected error, (17) each-i-with-each-j coupling, section 3.2
//! segment-site medial intervals with 157-degree opposition pruning.
//! Invariant: unsupported input returns upstream unchanged; only malformed,
//! non-finite or out-of-range input errors. Anchor and unowned vertices stay
//! bit-identical to upstream; movement stays within half the narrowest
//! coupled source width. No test pins preferred pixel counts.

#![cfg(feature = "candidate")]

use font_generator::{probe::FittedCommand, source_width};

fn line_loop(points: &[(f32, f32)]) -> Vec<FittedCommand> {
    let mut commands = vec![FittedCommand::MoveTo(points[0].0, points[0].1)];
    for point in &points[1..] {
        commands.push(FittedCommand::LineTo(point.0, point.1));
    }
    commands.push(FittedCommand::Close);
    commands
}

fn bar(x0: f32, y0: f32, x1: f32, y1: f32) -> Vec<FittedCommand> {
    line_loop(&[(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
}

fn op_tags(commands: &[FittedCommand]) -> Vec<u8> {
    commands
        .iter()
        .map(|command| match command {
            FittedCommand::MoveTo(..) => 0,
            FittedCommand::LineTo(..) => 1,
            FittedCommand::QuadTo(..) => 2,
            FittedCommand::CurveTo(..) => 3,
            FittedCommand::Close => 4,
        })
        .collect()
}

fn is_finite(commands: &[FittedCommand]) -> bool {
    commands.iter().all(|command| match *command {
        FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => x.is_finite() && y.is_finite(),
        FittedCommand::QuadTo(x1, y1, x, y) => {
            x1.is_finite() && y1.is_finite() && x.is_finite() && y.is_finite()
        }
        FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
            x1.is_finite()
                && y1.is_finite()
                && x2.is_finite()
                && y2.is_finite()
                && x.is_finite()
                && y.is_finite()
        }
        FittedCommand::Close => true,
    })
}

/// L-shaped stem with an attached step; the stem pair is the unique
/// rectilinear anchor when fitted stem boundaries stay integral.
fn stem_step() -> (Vec<FittedCommand>, Vec<FittedCommand>) {
    let source = line_loop(&[
        (0.0, 0.0),
        (6.0, 0.0),
        (6.0, 2.0),
        (2.0, 2.0),
        (2.0, 10.0),
        (0.0, 10.0),
    ]);
    let fitted = line_loop(&[
        (0.0, 0.0),
        (6.0, 0.0),
        (6.0, 2.5),
        (2.0, 2.5),
        (2.0, 10.0),
        (0.0, 10.0),
    ]);
    (source, fitted)
}

#[test]
fn stem_step_couple_applies_with_anchor_fixed() {
    // Source: (5)/(17) couple the step to the rectilinear stem anchor.
    let (source, upstream) = stem_step();
    let fit = source_width::fit(&source, &upstream, 16.0).unwrap();
    assert!(fit.applied);
    assert_eq!(op_tags(&fit.commands), op_tags(&source));
    assert!(is_finite(&fit.commands));
    // Invariant: anchor vertices stay bit-identical to upstream.
    for vertex in [0usize, 3, 4, 5] {
        assert_eq!(fit.commands[vertex], upstream[vertex]);
    }
    // Invariant: every vertex is either fixed or moves within half the
    // narrowest coupled source width (2 units here).
    for (index, command) in fit.commands.iter().enumerate() {
        let (x, y) = match *command {
            FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => (x, y),
            FittedCommand::Close => continue,
            _ => panic!("unexpected command kind"),
        };
        let (ux, uy) = match upstream[index] {
            FittedCommand::MoveTo(ux, uy) | FittedCommand::LineTo(ux, uy) => (ux, uy),
            _ => panic!("upstream/source op mismatch"),
        };
        let moved = ((x - ux).abs().max((y - uy).abs())) as f64;
        assert!(moved <= 1.0, "vertex {index} moved {moved}");
    }
}

#[test]
fn translated_and_scaled_inputs_keep_verdict() {
    // Invariant: the anchor is grid-locked (integral fitted boundaries), so
    // only lattice-preserving transforms keep eligibility; the normalized
    // working frame then keeps recognition independent of placement. Scale
    // changes physical units, so only the verdict and finiteness transfer,
    // never full shape equality.
    let (source, upstream) = stem_step();
    let base = source_width::fit(&source, &upstream, 16.0).unwrap();
    assert!(base.applied);
    let shift = |point: (f32, f32)| (point.0 + 37.0, point.1 - 12.0);
    let map = |commands: &[FittedCommand], f: fn((f32, f32)) -> (f32, f32)| {
        commands
            .iter()
            .map(|command| match command {
                FittedCommand::MoveTo(x, y) => {
                    let (nx, ny) = f((*x, *y));
                    FittedCommand::MoveTo(nx, ny)
                }
                FittedCommand::LineTo(x, y) => {
                    let (nx, ny) = f((*x, *y));
                    FittedCommand::LineTo(nx, ny)
                }
                FittedCommand::Close => FittedCommand::Close,
                FittedCommand::QuadTo(..) | FittedCommand::CurveTo(..) => {
                    panic!("unexpected curve in translation control")
                }
            })
            .collect::<Vec<_>>()
    };
    let shifted_source = map(&source, shift);
    let shifted_upstream = map(&upstream, shift);
    let shifted = source_width::fit(&shifted_source, &shifted_upstream, 16.0).unwrap();
    assert_eq!(shifted.applied, base.applied);
    assert_eq!(op_tags(&shifted.commands), op_tags(&shifted_source));
    for (got, want) in shifted.commands.iter().zip(base.commands.iter()) {
        match (got, want) {
            (
                FittedCommand::MoveTo(gx, gy) | FittedCommand::LineTo(gx, gy),
                FittedCommand::MoveTo(wx, wy) | FittedCommand::LineTo(wx, wy),
            ) => {
                let (ex, ey) = shift((*wx, *wy));
                assert!((gx - ex).abs() <= 1e-6, "translated x drifted");
                assert!((gy - ey).abs() <= 1e-6, "translated y drifted");
            }
            (FittedCommand::Close, FittedCommand::Close) => {}
            _ => panic!("op mismatch after translation"),
        }
    }
    // Scale changes physical units (anchor grid lock, weight scales), so the
    // scaled run is a validity control, not a verdict control: an applied
    // result must stay well-formed, an abstention must pass through.
    let scaled_source = map(&source, |(x, y)| (x * 2.0, y * 2.0));
    let scaled_upstream = map(&upstream, |(x, y)| (x * 2.0, y * 2.0));
    let scaled = source_width::fit(&scaled_source, &scaled_upstream, 16.0 * 2.0).unwrap();
    if scaled.applied {
        assert_eq!(op_tags(&scaled.commands), op_tags(&scaled_source));
        assert!(is_finite(&scaled.commands));
    } else {
        assert_eq!(scaled.commands, scaled_upstream);
    }
}

#[test]
fn rejects_nonfinite_malformed_and_bad_size() {
    // Source: explicit rejection replaces silent misclassification.
    let good = bar(0.0, 0.0, 4.0, 1.0);
    let bad_outlines = [
        vec![FittedCommand::MoveTo(f32::NAN, 0.0), FittedCommand::Close],
        vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(f32::INFINITY, 0.0),
            FittedCommand::Close,
        ],
        vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(40000.0, 0.0),
            FittedCommand::Close,
        ],
        vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::MoveTo(1.0, 1.0),
            FittedCommand::Close,
        ],
        vec![FittedCommand::Close],
        vec![FittedCommand::LineTo(1.0, 0.0)],
        vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(1.0, 0.0),
        ],
    ];
    for bad in &bad_outlines {
        assert!(source_width::fit(bad, &good, 16.0).is_err());
        assert!(source_width::fit(&good, bad, 16.0).is_err());
    }
    for size in [0.0, -1.0, f32::NAN, f32::INFINITY] {
        assert!(source_width::fit(&good, &good, size).is_err());
    }
}

#[test]
fn curves_multicontour_and_self_intersection_abstain() {
    // Invariant: unsupported geometry returns upstream unchanged.
    let mut curved = bar(0.0, 0.0, 4.0, 1.0);
    curved.insert(2, FittedCommand::QuadTo(2.0, 2.0, 4.0, 1.0));
    let mut two = bar(0.0, 0.0, 2.0, 1.0);
    two.extend(bar(4.0, 0.0, 6.0, 1.0));
    let bowtie = line_loop(&[(0.0, 0.0), (2.0, 2.0), (2.0, 0.0), (0.0, 2.0)]);
    let empty: Vec<FittedCommand> = Vec::new();
    let point = vec![FittedCommand::MoveTo(1.0, 1.0), FittedCommand::Close];
    let doubled = line_loop(&[(0.0, 0.0), (2.0, 0.0), (2.0, 0.0), (2.0, 1.0), (0.0, 1.0)]);
    for outline in [&curved, &two, &bowtie, &empty, &point, &doubled] {
        let fit = source_width::fit(outline, outline, 16.0).unwrap();
        assert!(!fit.applied);
        assert_eq!(fit.commands, *outline);
    }
}

#[test]
fn rotated_stem_has_no_rectilinear_anchor() {
    // Invariant: the anchor needs axis-parallel source sides; rotation
    // removes eligibility without touching the model.
    let (source, upstream) = stem_step();
    let rotate = |commands: &[FittedCommand]| {
        commands
            .iter()
            .map(|command| match command {
                FittedCommand::MoveTo(x, y) => FittedCommand::MoveTo(x - y, x + y),
                FittedCommand::LineTo(x, y) => FittedCommand::LineTo(x - y, x + y),
                FittedCommand::Close => FittedCommand::Close,
                FittedCommand::QuadTo(..) | FittedCommand::CurveTo(..) => {
                    panic!("unexpected curve in rotation control")
                }
            })
            .collect::<Vec<_>>()
    };
    let fit = source_width::fit(&rotate(&source), &rotate(&upstream), 16.0).unwrap();
    assert!(!fit.applied);
    assert_eq!(fit.commands, rotate(&upstream));
}

#[test]
fn twin_integral_stems_abstain_as_ambiguous() {
    // Invariant: two eligible rectilinear anchors cannot both govern.
    let outline = line_loop(&[
        (0.0, 0.0),
        (8.0, 0.0),
        (8.0, 8.0),
        (6.0, 8.0),
        (6.0, 2.0),
        (2.0, 2.0),
        (2.0, 8.0),
        (0.0, 8.0),
    ]);
    let fit = source_width::fit(&outline, &outline, 16.0).unwrap();
    assert!(!fit.applied);
    assert_eq!(fit.commands, outline);
    assert!(is_finite(&fit.commands));
}

fn fixture_commands(value: &serde_json::Value) -> Option<Vec<FittedCommand>> {
    // Source: capture schema carries op/x/y maps; x_bits only restate f32.
    let array = value.as_array()?;
    let mut commands = Vec::with_capacity(array.len());
    for entry in array {
        let op = entry.get("op")?.as_str()?;
        let num = |key: &str| entry.get(key)?.as_f64().map(|v| v as f32);
        commands.push(match op {
            "move_to" => FittedCommand::MoveTo(num("x")?, num("y")?),
            "line_to" => FittedCommand::LineTo(num("x")?, num("y")?),
            "quad_to" => FittedCommand::QuadTo(num("x1")?, num("y1")?, num("x")?, num("y")?),
            "curve_to" => FittedCommand::CurveTo(
                num("x1")?,
                num("y1")?,
                num("x2")?,
                num("y2")?,
                num("x")?,
                num("y")?,
            ),
            "close" => FittedCommand::Close,
            _ => return None,
        });
    }
    Some(commands)
}

fn fixture_pair(
    font: &str,
    size: f32,
    weight: f32,
    codepoint: u32,
) -> Option<(Vec<FittedCommand>, Vec<FittedCommand>, f32)> {
    // Invariant: the committed captures are an optional assessment input;
    // the suite never requires gitignored fixtures to pass.
    let text = std::fs::read_to_string(format!(
        "{}/../../out/diagnostics/source-feature-work-20261020/source-controls.json",
        env!("CARGO_MANIFEST_DIR")
    ))
    .ok()?;
    let document: serde_json::Value = serde_json::from_str(&text).ok()?;
    for entry in document.as_array()? {
        let entry_font = entry.get("font")?.as_str()?;
        let entry_size = entry.get("size")?.as_f64()? as f32;
        let entry_weight = entry.get("weight")?.as_f64()? as f32;
        if entry_font != font || entry_size != size || entry_weight != weight {
            continue;
        }
        let mut pair = None;
        for side in ["source", "upstream"] {
            let records = entry.get(side)?.get("records")?.as_array()?;
            let record = records.iter().find(|record| {
                record.get("codepoint").and_then(|v| v.as_u64()) == Some(codepoint as u64)
            })?;
            let commands = fixture_commands(record.get("fitted_commands")?)?;
            if side == "source" {
                pair = Some((commands, Vec::new()));
            } else if let Some(slot) = pair.as_mut() {
                slot.1 = commands;
            }
        }
        if let Some((source, upstream)) = pair {
            if !upstream.is_empty() {
                return Some((source, upstream, size));
            }
        }
    }
    None
}

#[test]
fn roboto_flex_stem_fixture_applies() {
    // Assessment only: the canonical straight `1` stem must be recognized;
    // pixel comparison stays with the parent pipeline.
    let Some((source, upstream, size)) = fixture_pair("RobotoFlex", 16.0, 400.0, 49) else {
        return;
    };
    let fit = source_width::fit(&source, &upstream, size).unwrap();
    assert!(fit.applied);
    assert_eq!(op_tags(&fit.commands), op_tags(&source));
    assert!(is_finite(&fit.commands));
    assert_ne!(fit.commands, upstream);
}

#[test]
fn curved_junction_fixtures_stay_upstream() {
    // Invariant: curved R/6/9 keeps interpreter geometry byte for byte.
    let mut checked = 0;
    for (font, codepoint) in [
        ("SourceSans3", 82u32),
        ("SourceSans3", 54u32),
        ("SourceSans3", 57u32),
    ] {
        let Some((source, upstream, size)) = fixture_pair(font, 12.0, 200.0, codepoint) else {
            continue;
        };
        let fit = source_width::fit(&source, &upstream, size).unwrap();
        assert!(!fit.applied, "curved glyph {codepoint} must abstain");
        assert_eq!(fit.commands, upstream);
        checked += 1;
    }
    if fixture_pair("SourceSans3", 12.0, 200.0, 82).is_some() {
        assert!(checked >= 1);
    }
}
