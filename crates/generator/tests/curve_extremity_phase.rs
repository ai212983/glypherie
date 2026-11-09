#![cfg(feature = "candidate")]
//! Smooth-extremity phase diagnostics: mechanism separation, not a sweep.
//!
//! Hersch95 "Displacement" / Fig. 5 (phases from pixel centers; windows
//! 1/16-9/16 and 3/16-11/16 exclude phase 0) and Hobby 1993 section 3.3
//! (tangent-on-boundary) predict that a smooth arc apex sitting exactly on a
//! pixel-center row is the spur-sensitive placement. These hermetic checks
//! separate the two tip mechanisms the review conflated: stub-rescue pixels
//! (appear/disappear with the stub policy at an unchanged outline) versus
//! phase placement (crown width varies with subpixel apex position under an
//! unchanged policy). Exact phase-0 boundary cells are asserted explicitly
//! with their observed scanner convention, never hidden in a tie band.
//! Diagnostics only; no optical verdict.
//!
//! Bulk sweeps live in the out/ diagnostic harness, never in test output.

use font_generator::{mono, probe::FittedCommand, Config, MonoDropoutMode, MonoRasterSettings};

fn arch(half_width: f64, shoulder: f64, apex: f64, base: f64) -> Vec<FittedCommand> {
    let ctl = 2.0 * apex - shoulder;
    vec![
        FittedCommand::MoveTo(-half_width as f32, base as f32),
        FittedCommand::LineTo(-half_width as f32, shoulder as f32),
        FittedCommand::QuadTo(0.0, ctl as f32, half_width as f32, shoulder as f32),
        FittedCommand::LineTo(half_width as f32, base as f32),
        FittedCommand::Close,
    ]
}

fn ring(hw: f64, shoulder: f64, apex: f64, base: f64, wall: f64) -> Vec<FittedCommand> {
    let mut out = arch(hw, shoulder, apex, base);
    // Inner contour winds opposite (nonzero fill keeps the band open).
    let (ihw, ish, iap, ib) = (hw - wall, shoulder - wall, apex - wall, base + wall);
    let ctl = 2.0 * iap - ish;
    out.extend(vec![
        FittedCommand::MoveTo(ihw as f32, ib as f32),
        FittedCommand::LineTo(ihw as f32, ish as f32),
        FittedCommand::QuadTo(0.0, ctl as f32, -(ihw as f32), ish as f32),
        FittedCommand::LineTo(-(ihw as f32), ib as f32),
        FittedCommand::Close,
    ]);
    // Inner traversal (up the right side, back across the top) already
    // winds opposite the outer contour for nonzero fill.
    out
}

fn transform(commands: &[FittedCommand], f: impl Fn(f64, f64) -> (f64, f64)) -> Vec<FittedCommand> {
    commands
        .iter()
        .map(|c| match *c {
            FittedCommand::MoveTo(x, y) => {
                let (a, b) = f(x as f64, y as f64);
                FittedCommand::MoveTo(a as f32, b as f32)
            }
            FittedCommand::LineTo(x, y) => {
                let (a, b) = f(x as f64, y as f64);
                FittedCommand::LineTo(a as f32, b as f32)
            }
            FittedCommand::QuadTo(x1, y1, x, y) => {
                let (a1, b1) = f(x1 as f64, y1 as f64);
                let (a, b) = f(x as f64, y as f64);
                FittedCommand::QuadTo(a1 as f32, b1 as f32, a as f32, b as f32)
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                let (a1, b1) = f(x1 as f64, y1 as f64);
                let (a2, b2) = f(x2 as f64, y2 as f64);
                let (a, b) = f(x as f64, y as f64);
                FittedCommand::CurveTo(
                    a1 as f32, b1 as f32, a2 as f32, b2 as f32, a as f32, b as f32,
                )
            }
            FittedCommand::Close => FittedCommand::Close,
        })
        .collect()
}

/// Flattened outline loops shared by the fill model and the tie band.
fn flatten(commands: &[FittedCommand]) -> Vec<Vec<(f64, f64)>> {
    let mut loops: Vec<Vec<(f64, f64)>> = Vec::new();
    let mut cur: Vec<(f64, f64)> = Vec::new();
    let mut pen = (0.0, 0.0);
    let mut opened = false;
    for c in commands {
        match *c {
            FittedCommand::MoveTo(x, y) => {
                pen = (x as f64, y as f64);
                cur = vec![pen];
                opened = true;
            }
            FittedCommand::LineTo(x, y) => {
                pen = (x as f64, y as f64);
                cur.push(pen);
            }
            FittedCommand::QuadTo(x1, y1, x, y) => {
                let (c1, p1) = ((x1 as f64, y1 as f64), (x as f64, y as f64));
                let p0 = pen;
                for i in 1..=256 {
                    let t = i as f64 / 256.0;
                    let mt = 1.0 - t;
                    cur.push((
                        mt * mt * p0.0 + 2.0 * mt * t * c1.0 + t * t * p1.0,
                        mt * mt * p0.1 + 2.0 * mt * t * c1.1 + t * t * p1.1,
                    ));
                }
                pen = p1;
            }
            FittedCommand::CurveTo(..) => panic!("sweep uses quads only"),
            FittedCommand::Close => {
                if opened {
                    loops.push(std::mem::take(&mut cur));
                    opened = false;
                }
            }
        }
    }
    loops
}

fn inside_loops(loops: &[Vec<(f64, f64)>], px: f64, py: f64) -> bool {
    let mut odd = false;
    for lp in loops {
        let n = lp.len();
        for i in 0..n {
            let (ax, ay) = lp[i];
            let (bx, by) = lp[(i + 1) % n];
            if (ay > py) != (by > py) {
                let xi = ax + (py - ay) * (bx - ax) / (by - ay);
                if px < xi {
                    odd = !odd;
                }
            }
        }
    }
    odd
}

fn boundary_distance(loops: &[Vec<(f64, f64)>], px: f64, py: f64) -> f64 {
    let mut best = f64::INFINITY;
    for lp in loops {
        let n = lp.len();
        for i in 0..n {
            let (ax, ay) = lp[i];
            let (bx, by) = lp[(i + 1) % n];
            let dx = bx - ax;
            let dy = by - ay;
            let len2 = dx * dx + dy * dy;
            let t = if len2 == 0.0 {
                0.0
            } else {
                ((px - ax) * dx + (py - ay) * dy) / len2
            }
            .clamp(0.0, 1.0);
            let ex = ax + t * dx - px;
            let ey = ay + t * dy - py;
            best = best.min((ex * ex + ey * ey).sqrt());
        }
    }
    best
}

/// From-spec center fill (even-odd; simple contours agree with nonzero fill)
/// plus per-cell distance from the pixel center to the flattened boundary.
/// Independent of the vendored scan converter.
fn center_fill(
    commands: &[FittedCommand],
    left: i32,
    top: i32,
    w: u32,
    h: u32,
) -> (Vec<u8>, Vec<f64>) {
    let loops = flatten(commands);
    let mut out = vec![0u8; (w * h) as usize];
    let mut dist = vec![0.0f64; (w * h) as usize];
    for row in 0..h {
        for col in 0..w {
            // Cell (col,row): x in [left+col, ...), y-down in [top+row, ...).
            let px = left as f64 + col as f64 + 0.5;
            let py_up = -(top as f64 + row as f64 + 0.5);
            if inside_loops(&loops, px, py_up) {
                out[(row * w + col) as usize] = 1;
            }
            dist[(row * w + col) as usize] = boundary_distance(&loops, px, py_up);
        }
    }
    (out, dist)
}

fn config_for(dropout: MonoDropoutMode, stubs: bool) -> Config {
    Config {
        size_px: 48.0,
        output_bits: 1,
        mono_raster: MonoRasterSettings {
            dropout,
            include_stubs: stubs,
            font_instructions: false,
        },
        ..Default::default()
    }
}

/// Extremal run at the shape's extremum in the given direction:
/// top/bottom scan rows, left/right scan columns. Returns
/// (line index, extremal run, next-line run).
fn crown(pixels: &[u8], w: u32, h: u32, side: &str) -> (u32, u32, u32) {
    let run_row = |row: u32| -> u32 {
        (0..w)
            .map(|c| u32::from(pixels[(row * w + c) as usize]))
            .sum()
    };
    let run_col = |col: u32| -> u32 {
        (0..h)
            .map(|r| u32::from(pixels[(r * w + col) as usize]))
            .sum()
    };
    match side {
        "bottom" => {
            for row in (0..h).rev() {
                let run = run_row(row);
                if run > 0 {
                    return (row, run, if row > 0 { run_row(row - 1) } else { 0 });
                }
            }
        }
        "left" => {
            for col in 0..w {
                let run = run_col(col);
                if run > 0 {
                    return (col, run, if col + 1 < w { run_col(col + 1) } else { 0 });
                }
            }
        }
        "right" => {
            for col in (0..w).rev() {
                let run = run_col(col);
                if run > 0 {
                    return (col, run, if col > 0 { run_col(col - 1) } else { 0 });
                }
            }
        }
        _ => {
            for row in 0..h {
                let run = run_row(row);
                if run > 0 {
                    return (row, run, if row + 1 < h { run_row(row + 1) } else { 0 });
                }
            }
        }
    }
    (h, 0, 0)
}

/// Scan/model comparison with the tie band made explicit: cells whose
/// pixel center lies within `TIE_PX` of the flattened boundary are the
/// scanline-through-boundary convention under study (Hersch section 7;
/// vendored sweep comment on center lines), never hidden. Returns the
/// (mismatches-outside-ties, tie count, minimum boundary distance).
fn compare_scan_model(shape: &[FittedCommand]) -> (u32, u32, f64) {
    const TIE_PX: f64 = 0.01;
    let off =
        mono::rasterize(shape, &config_for(MonoDropoutMode::Off, false)).expect("must rasterize");
    let (model, dist) = center_fill(shape, off.left, off.top, off.width, off.height);
    let mut outside = 0u32;
    let mut ties = 0u32;
    let mut min_dist = f64::INFINITY;
    for ((a, b), d) in off.pixels.iter().zip(model.iter()).zip(dist.iter()) {
        min_dist = min_dist.min(*d);
        if *d <= TIE_PX {
            ties += 1;
        } else if a != b {
            outside += 1;
        }
    }
    (outside, ties, min_dist)
}

/// The phase-0 tip on a synthetic smooth apex is stub rescue, not center
/// fill. At apex 22.5 (exactly on a pixel-center row) the dropout-off and
/// stub-free scans agree and carry no tip, while enabling stubs adds the
/// isolated 1 px crown pixel at an unchanged outline. Phase 0 is asserted
/// here explicitly with its observed convention, not banded away.
#[test]
fn phase_zero_tip_is_stub_rescue() {
    let shape = arch(10.3, 20.5, 22.5, 0.0);
    let off = mono::rasterize(&shape, &config_for(MonoDropoutMode::Off, false)).unwrap();
    let plain = mono::rasterize(&shape, &config_for(MonoDropoutMode::Smart, false)).unwrap();
    let working = mono::rasterize(&shape, &config_for(MonoDropoutMode::Smart, true)).unwrap();
    let (row_off, run_off, next_off) = crown(&off.pixels, off.width, off.height, "top");
    let (_, run_plain, _) = crown(&plain.pixels, plain.width, plain.height, "top");
    let (_, run_stub, next_stub) = crown(&working.pixels, working.width, working.height, "top");
    // Both stub-free scans agree and show a full crown, never a spur.
    assert_eq!(
        off.pixels, plain.pixels,
        "dropout-off must equal stub-free scan"
    );
    assert!(
        run_off > 2,
        "stub-free phase-0 crown must be full, got {run_off}"
    );
    // Stubs alone add the isolated tip pixel at the same outline.
    assert_eq!(run_stub, 1, "stub rescue adds the 1 px tip, got {run_stub}");
    assert!(next_stub > run_stub, "tip sits above a wider row");
    // The independent center-fill model agrees with the dropout-off scan
    // outside ties. The phase-0 apex row genuinely touches the tie band
    // (measured minimum center distance ~0.005 px): ties are recorded here
    // explicitly instead of being banded away.
    let (outside, ties, min_dist) = compare_scan_model(&shape);
    assert_eq!(outside, 0, "model must agree outside ties");
    assert!(
        ties > 0,
        "phase-0 boundary cells must be recorded, not banded"
    );
    assert!(
        min_dist <= 0.01,
        "phase-0 apex must touch the tie band, got {min_dist}"
    );
    let _ = (row_off, run_plain, next_off);
}

/// A boundary through a pixel center is the exact tie case: with the apex
/// shifted onto a center point, the nearest center distance collapses to
/// flatten tolerance and scan/model still agree outside the band.
#[test]
fn apex_on_center_point_stays_explicit() {
    let shifted: Vec<FittedCommand> = arch(10.3, 20.5, 22.5, 0.0)
        .into_iter()
        .map(|c| match c {
            FittedCommand::MoveTo(x, y) => FittedCommand::MoveTo(x + 0.5, y),
            FittedCommand::LineTo(x, y) => FittedCommand::LineTo(x + 0.5, y),
            FittedCommand::QuadTo(x1, y1, x, y) => FittedCommand::QuadTo(x1 + 0.5, y1, x + 0.5, y),
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                FittedCommand::CurveTo(x1 + 0.5, y1, x2 + 0.5, y2, x + 0.5, y)
            }
            FittedCommand::Close => FittedCommand::Close,
        })
        .collect();
    let (outside, ties, min_dist) = compare_scan_model(&shifted);
    assert_eq!(outside, 0, "center-point contact must agree outside ties");
    assert!(ties > 0, "center-point contact must be recorded as ties");
    assert!(
        min_dist <= 1e-3,
        "apex must touch a pixel center, got {min_dist}"
    );
}

/// Crown width varies with subpixel apex phase under an unchanged policy:
/// the phase mechanism is real on this scanner, whatever the rescue policy
/// does at the boundary. No placement is preferred here.
#[test]
fn crown_width_is_phase_sensitive() {
    let mut runs = Vec::new();
    for apex in [22.0, 22.0625, 22.125, 22.5] {
        let shape = arch(10.3, apex - 2.0, apex, 0.0);
        let out = mono::rasterize(&shape, &config_for(MonoDropoutMode::Off, false)).unwrap();
        let (_, run, _) = crown(&out.pixels, out.width, out.height, "top");
        runs.push(run);
    }
    let distinct: std::collections::BTreeSet<u32> = runs.iter().copied().collect();
    assert!(
        distinct.len() >= 2,
        "crown width must vary with phase, got {runs:?}"
    );
}

/// The real `o` near-boundary case under dropout-off: the independent
/// center-fill model reproduces the maintained scan outside ties on the
/// actual reported outline, with boundary ties recorded at the apex.
#[test]
fn real_o_dropout_off_matches_center_fill() {
    use font_generator::reference::{reference, ReferenceRequest};
    use font_generator::Hinting;
    let data = std::fs::read(format!(
        "{}/../../fonts/RobotoFlex.ttf",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap();
    let source = reference(
        &data,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: "none".into(),
            settings: Config {
                size_px: 48.0,
                axes: [
                    ("wght", 400.0),
                    ("wdth", 100.0),
                    ("slnt", 0.0),
                    ("opsz", 48.0),
                ]
                .into_iter()
                .map(|(k, v)| (k.to_string(), v))
                .collect(),
                characters: "o".into(),
                hinting: Hinting::None,
                output_bits: 1,
                ..Config::default()
            },
        },
    )
    .unwrap();
    assert_eq!(source.records.len(), 1);
    let outline = &source.records[0].fitted_commands;
    let (outside, _, min_dist) = compare_scan_model(outline);
    assert_eq!(outside, 0, "real-o model must agree outside ties");
    // The real `o` source apex sits at phase 0 (pixel-center row) with its
    // nearest center ~0.014 px away: near-boundary but outside the tie band,
    // so agreement outside ties is the whole story here. The observed
    // minimum is pinned as an anchor, not a preference.
    assert!(
        min_dist <= 0.02,
        "real-o must stay near-boundary, got {min_dist}"
    );
}

/// All four sides plus the paired inner boundary share one axis-symmetric
/// rule: dropout-off matches center fill outside ties from phase 0 through
/// the window edge. Phase-0 sides/bottoms are genuine center-row contacts
/// (bottom mirrors, sides rotate the apex onto a center column).
#[test]
fn sides_and_inner_boundary_share_the_rule() {
    let shoulder = |apex: f64| apex - 2.0;
    for apex in [22.0, 22.0625, 22.125, 22.5] {
        let base = arch(10.3, shoulder(apex), apex, 0.0);
        let ring_shape = ring(10.3, shoulder(apex), apex, 0.0, 2.0);
        let variants: Vec<(&str, Vec<FittedCommand>)> = vec![
            ("top", base.clone()),
            ("bottom", transform(&base, |x, y| (x, 44.0 - y))),
            ("left", transform(&base, |x, y| (-y, x))),
            ("right", transform(&base, |x, y| (y, x))),
            ("ring_top", ring_shape),
        ];
        for (side, shape) in &variants {
            let (outside, _, _) = compare_scan_model(shape);
            assert_eq!(
                outside, 0,
                "side {side} apex {apex} must agree outside ties"
            );
        }
    }
}
