//! Bounded ASCII-subset kerning display: authentic source pairs at an
//! explicit size/axes coordinate. Display-only; no fitting or layout code is
//! exercised here.
use font_generator::ascii_kerning_pairs;
use std::collections::BTreeMap;
use std::path::Path;

fn font(path: &str) -> Vec<u8> {
    std::fs::read(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .join(path),
    )
    .unwrap_or_else(|error| panic!("fixture {path}: {error}"))
}

const CALIBRATION: [&str; 3] = [
    "fonts/Roboto.ttf",
    "fonts/Literata.ttf",
    "fonts/SourceSans3.ttf",
];

fn pair(pairs: &[font_generator::KerningPair], left: char, right: char) -> Option<i32> {
    pairs
        .iter()
        .find(|p| p.left == left as u32 && p.right == right as u32)
        .map(|p| p.adjustment_26_6)
}

#[test]
fn shipped_fonts_report_authentic_nonzero_ascii_pairs() {
    for path in CALIBRATION {
        let bytes = font(path);
        let table = ascii_kerning_pairs(&bytes, 16.0, &BTreeMap::new()).unwrap();
        assert!(
            !table.pairs.is_empty(),
            "{path} should kern some ASCII pair"
        );
        for p in &table.pairs {
            assert!(
                (0x20..=0x7E).contains(&p.left) && (0x20..=0x7E).contains(&p.right),
                "{path} pair out of ASCII scope"
            );
            assert_ne!(p.adjustment_26_6, 0, "{path} zero pair must be omitted");
        }
        // Witness pair from the iteration notes; all three ship it.
        let av = pair(&table.pairs, 'A', 'V').unwrap_or_else(|| panic!("{path} lacks an AV pair"));
        assert!(av < 0, "{path} AV should tighten, got {av}");
    }
}

#[test]
fn unrepresentable_pairs_are_counted_not_silent() {
    // Literata shapes grave-accent pairs with text-run positioning, which
    // strict generation rejects outright. The display table must report such
    // pairs instead of listing them, without hiding the rest of the subset.
    let bytes = font(CALIBRATION[1]);
    let table = ascii_kerning_pairs(&bytes, 16.0, &BTreeMap::new()).unwrap();
    assert!(
        table.skipped_pairs > 0,
        "expected some omitted contextual pair"
    );
    assert!(
        !table.pairs.is_empty(),
        "omitted pairs must not hide the subset"
    );
    assert!(pair(&table.pairs, 'A', '`').is_none());
    let config = font_generator::Config {
        size_px: 16.0,
        characters: "A`".into(),
        ..font_generator::Config::default()
    };
    assert!(
        font_generator::generate(&bytes, &config).is_err(),
        "display omissions must not relax rendering capability errors"
    );
}

#[test]
fn adjustments_scale_with_size_at_subpixel_precision() {
    let bytes = font(CALIBRATION[0]);
    let small = ascii_kerning_pairs(&bytes, 16.0, &BTreeMap::new()).unwrap();
    let large = ascii_kerning_pairs(&bytes, 32.0, &BTreeMap::new()).unwrap();
    let a = pair(&small.pairs, 'A', 'V').unwrap();
    let b = pair(&large.pairs, 'A', 'V').unwrap();
    assert!(a < 0 && b < 0, "AV keeps its sign across sizes");
    assert!(
        b.abs() > a.abs(),
        "larger size must carry a larger AV adjustment ({a} vs {b})"
    );
    // Linear source scaling through 26.6 rounding: doubling stays within one
    // subpixel step of exact.
    assert!(
        (b - 2 * a).abs() <= 1,
        "AV should scale linearly within 26.6 rounding ({a} vs {b})"
    );
}

#[test]
fn supported_axes_apply_and_invalid_settings_fail_explicitly() {
    let bytes = font(CALIBRATION[0]);
    let meta = font_generator::metadata::extract(&bytes).unwrap();
    if let Some(axis) = meta.axes.first() {
        for value in [axis.min, axis.default, axis.max] {
            let axes = BTreeMap::from([(axis.tag.clone(), value)]);
            let table = ascii_kerning_pairs(&bytes, 16.0, &axes).unwrap();
            assert!(
                !table.pairs.is_empty(),
                "axis {}={value} keeps pairs",
                axis.tag
            );
        }
    }
    let bad_axis = BTreeMap::from([("XXXX".to_string(), 400.0)]);
    assert!(ascii_kerning_pairs(&bytes, 16.0, &bad_axis).is_err());
    let bad_value = BTreeMap::from([("wght".to_string(), f32::NAN)]);
    assert!(ascii_kerning_pairs(&bytes, 16.0, &bad_value).is_err());
    for size in [0.0, -4.0, f32::NAN, f32::INFINITY, 513.0] {
        assert!(
            ascii_kerning_pairs(&bytes, size, &BTreeMap::new()).is_err(),
            "size {size} must fail validation"
        );
    }
    assert!(ascii_kerning_pairs(b"not a font", 16.0, &BTreeMap::new()).is_err());
    assert!(ascii_kerning_pairs(&[], 16.0, &BTreeMap::new()).is_err());
}
