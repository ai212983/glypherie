#![cfg(feature = "candidate")]
//! Exact scanner identity against an independent, unmodified FreeType build.
//! These fixtures establish scan conversion parity, not optical acceptance.
use font_generator::{
    batch::{to_fitted, RawCommand},
    mono,
    probe::FittedCommand,
    Config,
};
use serde::Deserialize;
use std::collections::BTreeSet;

#[derive(Deserialize)]
struct Fixture {
    version: String,
    cases: Vec<Case>,
}
#[derive(Deserialize)]
struct Case {
    key: String,
    commands: Vec<RawCommand>,
    pixels: Vec<[i32; 2]>,
}
fn fixtures() -> Fixture {
    serde_json::from_str(include_str!("fixtures/freetype-mono-2.15.0.json")).unwrap()
}
#[test]
fn matches_independent_full_freetype_for_curves_overlap_stubs_and_thin_features() {
    let fixture = fixtures();
    assert_eq!(fixture.version, mono::VERSION);
    for case in fixture.cases {
        let commands = to_fitted(&case.commands).unwrap();
        let actual = mono::rasterize(&commands, &Config::default()).unwrap();
        let pixels: BTreeSet<_> = actual
            .pixels
            .iter()
            .enumerate()
            .filter(|(_, p)| **p != 0)
            .map(|(i, _)| {
                [
                    actual.left + (i % actual.width as usize) as i32,
                    actual.top + (i / actual.width as usize) as i32,
                ]
            })
            .collect();
        assert_eq!(pixels, case.pixels.into_iter().collect(), "{}", case.key);
    }
}
#[test]
fn bounded_arena_handles_large_glyphs_and_simultaneous_calls() {
    let rectangle = vec![
        FittedCommand::MoveTo(0., 0.),
        FittedCommand::LineTo(600., 0.),
        FittedCommand::LineTo(600., 600.),
        FittedCommand::LineTo(0., 600.),
        FittedCommand::Close,
    ];
    // This crosses FreeType 2.15's heap-pool estimate and exercises our arena.
    let output = mono::rasterize(&rectangle, &Config::default()).unwrap();
    assert_eq!((output.width, output.height), (600, 600));
    assert!(output.pixels.iter().all(|p| *p == 1));
    std::thread::scope(|scope| {
        for _ in 0..8 {
            scope.spawn(|| {
                for case in fixtures().cases {
                    let commands = to_fitted(&case.commands).unwrap();
                    let a = mono::rasterize(&commands, &Config::default()).unwrap();
                    let b = mono::rasterize(
                        &commands,
                        &Config {
                            mono_threshold: 255,
                            ..Config::default()
                        },
                    )
                    .unwrap();
                    assert_eq!(
                        a.pixels, b.pixels,
                        "threshold must not choose center-fill ink"
                    );
                    assert_eq!(a.coverage, b.coverage);
                }
            });
        }
    });
}
#[test]
fn rejects_invalid_profiles_geometry_and_unbounded_inputs() {
    let valid = vec![
        FittedCommand::MoveTo(0., 0.),
        FittedCommand::LineTo(1., 1.),
        FittedCommand::Close,
    ];
    assert!(mono::rasterize(
        &valid,
        &Config {
            output_bits: 3,
            ..Config::default()
        }
    )
    .is_err());
    for commands in [
        vec![FittedCommand::LineTo(0., 0.)],
        vec![FittedCommand::Close],
        vec![FittedCommand::MoveTo(f32::NAN, 0.), FittedCommand::Close],
        vec![FittedCommand::MoveTo(40000., 0.), FittedCommand::Close],
        vec![FittedCommand::MoveTo(0., 0.)],
        vec![FittedCommand::MoveTo(0., 0.), FittedCommand::MoveTo(1., 0.)],
    ] {
        assert!(mono::rasterize(&commands, &Config::default()).is_err());
    }
    let mut many = vec![FittedCommand::MoveTo(0., 0.)];
    many.extend(std::iter::repeat_n(FittedCommand::LineTo(1., 1.), 65535));
    many.push(FittedCommand::Close);
    assert!(mono::rasterize(&many, &Config::default()).is_err());
}
