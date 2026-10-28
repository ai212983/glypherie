//! Integration tests for straight supporting-cap suppression.
//!
//! Source: TrueType SCANTYPE Rules 5/6 (cap closure needs both borders to
//! continue); pinned FreeType ftraster.c stub test; Hersch 1993 section 7;
//! 26.6 conversion per mono.rs. Native mono::rasterize pairs supply the
//! stubs on/off difference; hand-built rasters isolate span-ownership
//! verdicts. No per-glyph pixel snapshots; tip cases assert exact
//! independent mask parity with the no-stub scan.

use font_generator::{
    mono, probe::FittedCommand, terminal_caps::suppress_certified, Config, MonoDropoutMode,
    MonoRasterSettings,
};

fn mono_pair(stubs: bool) -> Config {
    Config {
        output_bits: 1,
        mono_threshold: 128,
        characters: "a".into(),
        mono_raster: MonoRasterSettings {
            dropout: MonoDropoutMode::Smart,
            include_stubs: stubs,
            font_instructions: false,
        },
        ..Config::default()
    }
}

fn bar(x0: f32, y0: f32, x1: f32, y1: f32) -> Vec<FittedCommand> {
    vec![
        FittedCommand::MoveTo(x0, y0),
        FittedCommand::LineTo(x1, y0),
        FittedCommand::LineTo(x1, y1),
        FittedCommand::LineTo(x0, y1),
        FittedCommand::Close,
    ]
}

fn xform(commands: &[FittedCommand], f: impl Fn(f32, f32) -> (f32, f32)) -> Vec<FittedCommand> {
    commands
        .iter()
        .map(|command| match *command {
            FittedCommand::MoveTo(x, y) => {
                let (nx, ny) = f(x, y);
                FittedCommand::MoveTo(nx, ny)
            }
            FittedCommand::LineTo(x, y) => {
                let (nx, ny) = f(x, y);
                FittedCommand::LineTo(nx, ny)
            }
            FittedCommand::QuadTo(x1, y1, x, y) => {
                let (nx1, ny1) = f(x1, y1);
                let (nx, ny) = f(x, y);
                FittedCommand::QuadTo(nx1, ny1, nx, ny)
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                let (nx1, ny1) = f(x1, y1);
                let (nx2, ny2) = f(x2, y2);
                let (nx, ny) = f(x, y);
                FittedCommand::CurveTo(nx1, ny1, nx2, ny2, nx, ny)
            }
            FittedCommand::Close => FittedCommand::Close,
        })
        .collect()
}

fn native_pair(commands: &[FittedCommand]) -> (Vec<u8>, Vec<u8>, i32, i32, u32, u32) {
    let with = mono::rasterize(commands, &mono_pair(true)).unwrap();
    let without = mono::rasterize(commands, &mono_pair(false)).unwrap();
    assert_eq!(
        (with.left, with.top, with.width, with.height),
        (without.left, without.top, without.width, without.height)
    );
    assert_eq!(with.pixels.len(), without.pixels.len());
    (
        with.pixels,
        without.pixels,
        with.left,
        with.top,
        with.width,
        with.height,
    )
}

fn raster(
    left: i32,
    top: i32,
    width: u32,
    height: u32,
    ink: &[(i32, i32)],
) -> font_generator::probe::RasterOutput {
    let mut pixels = vec![0u8; width as usize * height as usize];
    for (x, y) in ink {
        pixels[((y - top) * width as i32 + (x - left)) as usize] = 1;
    }
    font_generator::probe::RasterOutput {
        pixels,
        coverage: Vec::new(),
        left,
        top,
        width,
        height,
    }
}

#[test]
fn thin_bar_tip_suppressed_to_nostub_mask() {
    // Source: SCANTYPE Rule 6 terminal tip; native FreeType pair.
    let commands = bar(0.375, 0.375, 4.375, 0.75);
    let (with, without, left, top, width, height) = native_pair(&commands);
    let mut rebuilt = raster(left, top, width, height, &[]);
    rebuilt.pixels = with;
    let mut rebuilt_no = raster(left, top, width, height, &[]);
    rebuilt_no.pixels = without.clone();
    let result = suppress_certified(&commands, &commands, &rebuilt, &rebuilt_no).unwrap();
    assert_eq!(result.pixels, without);
}

#[test]
fn transformed_tips_suppressed() {
    // Source: covariance under translation, reflection and rotation.
    let base = bar(0.375, 0.375, 4.375, 0.75);
    let variants = [
        xform(&base, |x, y| (x + 5.0, y - 3.0)),
        xform(&base, |x, y| (-x, y)),
        xform(&base, |x, y| (-y, x)),
    ];
    for commands in &variants {
        let (with, without, left, top, width, height) = native_pair(commands);
        if with == without {
            continue;
        }
        let mut rebuilt = raster(left, top, width, height, &[]);
        rebuilt.pixels = with.clone();
        let mut rebuilt_no = raster(left, top, width, height, &[]);
        rebuilt_no.pixels = without.clone();
        let result = suppress_certified(commands, commands, &rebuilt, &rebuilt_no).unwrap();
        assert_eq!(result.pixels, without);
    }
}

#[test]
fn junction_gap_preserved() {
    // Source: Rule 6 excludes stubs, not interior junction spans. A notch
    // whose inner edge fails the supporting half-plane keeps its rescue.
    let commands = vec![
        FittedCommand::MoveTo(0.0, 0.0),
        FittedCommand::LineTo(4.0, 0.0),
        FittedCommand::LineTo(4.0, 3.0),
        FittedCommand::LineTo(3.0, 3.0),
        FittedCommand::LineTo(3.0, 1.0),
        FittedCommand::LineTo(1.0, 1.0),
        FittedCommand::LineTo(1.0, 3.0),
        FittedCommand::LineTo(0.0, 3.0),
        FittedCommand::Close,
    ];
    // Hand-built diff at the notch bridge pixel: the bridge edge is
    // interior (outline extends above it), so no certified cap owns it.
    let with = raster(0, -3, 4, 3, &[(1, -1), (2, -1), (1, -2), (2, -2)]);
    let mut without = with.pixels.clone();
    without[(2 * 4 + 1) as usize] = 0;
    without[(2 * 4 + 2) as usize] = 0;
    let no = font_generator::probe::RasterOutput {
        pixels: without,
        coverage: Vec::new(),
        left: 0,
        top: -3,
        width: 4,
        height: 3,
    };
    let result = suppress_certified(&commands, &commands, &with, &no).unwrap();
    assert_eq!(result.pixels, with.pixels);
    assert!(result.removed.is_empty());
}

#[test]
fn curve_hull_contact_preserved() {
    // Source: hull contains the curve; a diff pixel inside the hull but
    // clear of the control-polygon legs keeps its rescue.
    let commands = vec![
        FittedCommand::MoveTo(0.0, 0.0),
        FittedCommand::LineTo(4.0, 0.0),
        FittedCommand::LineTo(4.0, 1.0),
        FittedCommand::LineTo(0.0, 1.0),
        FittedCommand::Close,
        FittedCommand::MoveTo(6.0, -0.5),
        FittedCommand::QuadTo(3.5, 0.5, 6.0, 1.5),
        FittedCommand::Close,
    ];
    let with = raster(0, -2, 7, 4, &[(4, 0), (2, 0), (3, 0)]);
    let mut pixels = with.pixels.clone();
    pixels[(2 * 7 + 4) as usize] = 0;
    let no = font_generator::probe::RasterOutput {
        pixels,
        coverage: Vec::new(),
        left: 0,
        top: -2,
        width: 7,
        height: 4,
    };
    let result = suppress_certified(&commands, &commands, &with, &no).unwrap();
    assert_eq!(result.pixels, with.pixels);
    assert!(result.removed.is_empty());
}

#[test]
fn coincident_cancel_preserved() {
    // Source: coincident reversed contours cancel fill; the shared edge is
    // touched by another contour, so no certified cap exists.
    let mut commands = bar(0.0, 0.0, 4.0, 1.0);
    commands.extend([
        FittedCommand::MoveTo(0.0, 0.0),
        FittedCommand::LineTo(0.0, 1.0),
        FittedCommand::LineTo(4.0, 1.0),
        FittedCommand::LineTo(4.0, 0.0),
        FittedCommand::Close,
    ]);
    let with = raster(0, -1, 4, 1, &[(1, -1), (2, -1)]);
    let mut pixels = with.pixels.clone();
    pixels[1] = 0;
    let no = font_generator::probe::RasterOutput {
        pixels,
        coverage: Vec::new(),
        left: 0,
        top: -1,
        width: 4,
        height: 1,
    };
    let result = suppress_certified(&commands, &commands, &with, &no).unwrap();
    assert_eq!(result.pixels, with.pixels);
    assert!(result.removed.is_empty());
}

#[test]
fn hole_wall_span_preserved() {
    // Source: a wall span between outer and hole contours has no
    // same-contour cap; its diff pixel keeps its rescue.
    let mut commands = bar(0.0, 0.0, 6.0, 6.0);
    commands.extend([
        FittedCommand::MoveTo(4.0, 4.0),
        FittedCommand::LineTo(4.0, 2.0),
        FittedCommand::LineTo(2.0, 2.0),
        FittedCommand::LineTo(2.0, 4.0),
        FittedCommand::Close,
    ]);
    // Diff pixel flanked by the hole edge: other-contour contact abstains.
    let with = raster(0, -6, 6, 6, &[(2, -4), (3, -4), (2, -3), (3, -3)]);
    let mut pixels = with.pixels.clone();
    pixels[(2 * 6 + 2) as usize] = 0;
    let no = font_generator::probe::RasterOutput {
        pixels,
        coverage: Vec::new(),
        left: 0,
        top: -6,
        width: 6,
        height: 6,
    };
    let result = suppress_certified(&commands, &commands, &with, &no).unwrap();
    assert_eq!(result.pixels, with.pixels);
    assert!(result.removed.is_empty());
}

#[test]
fn rejects_invalid_inputs() {
    // Source: explicit rejection replaces silent misclassification.
    let good = bar(0.0, 0.0, 4.0, 1.0);
    let frame = raster(0, -1, 4, 1, &[(1, -1)]);
    let frame2 = raster(0, -1, 4, 1, &[(1, -1)]);
    let bads = [
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
            FittedCommand::LineTo(1.0, 0.0),
        ],
        vec![FittedCommand::LineTo(1.0, 0.0)],
    ];
    for bad in &bads {
        assert!(suppress_certified(bad, &good, &frame, &frame2).is_err());
        assert!(suppress_certified(&good, bad, &frame, &frame2).is_err());
    }
}

#[test]
fn unsupported_structure_returns_clone() {
    // Source: source/fitted topology mismatch is unsupported, not an error.
    let fitted = bar(0.0, 0.0, 4.0, 1.0);
    let source = vec![
        FittedCommand::MoveTo(0.0, 0.0),
        FittedCommand::LineTo(2.0, 0.0),
        FittedCommand::LineTo(4.0, 0.0),
        FittedCommand::LineTo(4.0, 1.0),
        FittedCommand::LineTo(0.0, 1.0),
        FittedCommand::Close,
    ];
    let with = raster(0, -1, 4, 1, &[(1, -1)]);
    let mut pixels = with.pixels.clone();
    pixels[1] = 0;
    let no = font_generator::probe::RasterOutput {
        pixels,
        coverage: Vec::new(),
        left: 0,
        top: -1,
        width: 4,
        height: 1,
    };
    let result = suppress_certified(&source, &fitted, &with, &no).unwrap();
    assert_eq!(result.pixels, with.pixels);
    assert!(result.removed.is_empty());
}

#[test]
fn frame_mismatch_rejected() {
    let commands = bar(0.0, 0.0, 4.0, 1.0);
    let with = raster(0, -1, 4, 1, &[(1, -1)]);
    let no = raster(1, -1, 4, 1, &[(1, -1)]);
    assert!(suppress_certified(&commands, &commands, &with, &no).is_err());
}

#[test]
fn rejects_unbounded_frames_before_indexing_on_wasm() {
    let commands = bar(0.0, 0.0, 4.0, 1.0);
    for (left, top, width, height) in [
        (i32::MAX, 0, 1, 1),
        (0, i32::MIN, 1, 1),
        (0, 0, u32::MAX, u32::MAX),
        (32768, 0, 1, 1),
    ] {
        let frame = font_generator::probe::RasterOutput {
            pixels: vec![],
            coverage: vec![],
            left,
            top,
            width,
            height,
        };
        assert!(suppress_certified(&commands, &commands, &frame, &frame).is_err());
    }
}

#[test]
fn complex_optional_geometry_keeps_the_successful_scan() {
    // A convex outline exposes the quadratic supporting-edge work. The
    // optional classifier must abstain rather than fail an existing raster.
    let count = 4096;
    let mut commands = Vec::new();
    for i in 0..count {
        let angle = std::f32::consts::TAU * i as f32 / count as f32;
        let (x, y) = (16. * angle.cos(), 16. * angle.sin());
        commands.push(if i == 0 {
            FittedCommand::MoveTo(x, y)
        } else {
            FittedCommand::LineTo(x, y)
        });
    }
    commands.push(FittedCommand::Close);
    let with = raster(0, 0, 1, 1, &[(0, 0)]);
    let without = raster(0, 0, 1, 1, &[]);
    let output = suppress_certified(&commands, &commands, &with, &without).unwrap();
    assert_eq!(output.pixels, with.pixels);
}
