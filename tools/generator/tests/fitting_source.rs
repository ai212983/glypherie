#![cfg(feature = "candidate")]

//! Source-outline capture keeps continuous variation coordinates.
//!
//! Parent-verified FontTools evidence: in-memory instantiated outlines are
//! unrounded continuous coordinates, so the FreeType unscaled integer
//! rounding of gvar deltas must not shape this output.

use font_generator::{fitting_source, Config};
use std::collections::BTreeMap;
use std::path::PathBuf;

fn roboto_flex() -> Vec<u8> {
    std::fs::read(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../fonts/RobotoFlex.ttf"))
        .expect("variable fixture font")
}

fn config_at(size_px: f32, wght: f32) -> Config {
    let mut axes = BTreeMap::new();
    axes.insert("wght".to_string(), wght);
    Config {
        size_px,
        axes,
        ..Default::default()
    }
}

#[test]
fn rejects_empty_font() {
    let config = Config::default();
    assert!(fitting_source::draw(&[], &config, 0).is_err());
}

#[test]
fn rejects_unknown_and_out_of_range_axes() {
    let data = roboto_flex();
    let mut bad_tag = Config::default();
    bad_tag.axes.insert("XXXX".to_string(), 400.0);
    assert!(fitting_source::draw(&data, &bad_tag, 0).is_err());
    let out_of_range = config_at(16.0, 1_000_000.0);
    assert!(fitting_source::draw(&data, &out_of_range, 0).is_err());
}

#[test]
fn rejects_missing_glyph_and_bad_size() {
    let data = roboto_flex();
    let config = config_at(16.0, 300.0);
    assert!(fitting_source::draw(&data, &config, u32::MAX).is_err());
    let mut bad_size = config_at(16.0, 300.0);
    bad_size.size_px = 0.0;
    assert!(fitting_source::draw(&data, &bad_size, 3).is_err());
}

#[test]
fn keeps_continuous_variation_deltas() {
    // RobotoFlex at wght 300 carries fractional gvar deltas (parent
    // FontTools capture shows continuous raw coordinates where the old
    // FreeType unscaled path emitted integer-rounded font units). Inverting
    // the single f64 scale must therefore recover non-integer font units.
    let data = roboto_flex();
    let size = 16.0f64;
    let config = config_at(size as f32, 300.0);
    let units = 2048.0f64;
    let mut seen_fractional = false;
    for glyph_id in 0..256u32 {
        let Ok(parsed) = fitting_source::draw(&data, &config, glyph_id) else {
            continue;
        };
        for point in parsed.oncurve.iter().chain(parsed.offcurve.iter()) {
            for coordinate in point {
                let funit = *coordinate * units / size;
                if funit.fract().abs() > 1e-6 {
                    seen_fractional = true;
                }
            }
        }
        if seen_fractional {
            break;
        }
    }
    assert!(seen_fractional, "expected continuous variation deltas");
}

#[test]
fn capture_is_deterministic() {
    let data = roboto_flex();
    let config = config_at(16.0, 300.0);
    let first = fitting_source::draw(&data, &config, 3).expect("glyph 3");
    let second = fitting_source::draw(&data, &config, 3).expect("glyph 3");
    assert_eq!(first.oncurve, second.oncurve);
    assert_eq!(first.offcurve, second.offcurve);
    assert_eq!(first.contours, second.contours);
}
