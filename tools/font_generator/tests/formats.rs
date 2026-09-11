//! Original rectangle fixtures exercise both OpenType PostScript outline formats.
use font_generator::{generate, Config, Hinting};

const CFF: &[u8] = include_bytes!("fixtures/static-cff.otf");
const CFF2: &[u8] = include_bytes!("fixtures/variable-cff2.otf");

#[test]
fn cff_and_cff2_generate_empty_and_visible_glyphs() {
    for (data, hinting) in [CFF, CFF2].into_iter().flat_map(|data| {
        [
            Hinting::None,
            Hinting::AutoFallback,
            Hinting::Auto,
            Hinting::Interpreter,
        ]
        .into_iter()
        .map(move |hinting| (data, hinting))
    }) {
        let cfg = Config {
            characters: " A".into(),
            size_px: 20.0,
            hinting,
            output_bits: 1,
            ..Config::default()
        };
        let generated = generate(data, &cfg).unwrap();
        let space = generated.glyphs.iter().find(|g| g.codepoint == 32).unwrap();
        assert!(space.pixels.is_empty());
        assert_eq!(space.advance_26_6, 6 * 64);
        let a = generated.glyphs.iter().find(|g| g.codepoint == 65).unwrap();
        assert_eq!((a.left, a.top, a.width, a.height), (1, -14, 6, 14));
        assert!(a.pixels.iter().all(|&p| p == 1));
        assert_eq!(a.advance_26_6, 12 * 64);
    }
}

#[test]
fn cff2_blend_axis_changes_outline_and_cff_rejects_axis() {
    let mut cfg = Config {
        characters: "A".into(),
        size_px: 20.0,
        hinting: Hinting::None,
        ..Config::default()
    };
    cfg.axes.insert("wght".into(), 100.0);
    let thin = generate(CFF2, &cfg).unwrap();
    cfg.axes.insert("wght".into(), 900.0);
    let thick = generate(CFF2, &cfg).unwrap();
    assert_eq!(thin.glyphs[0].width, 6);
    assert_eq!(thick.glyphs[0].width, 8);
    assert_eq!(thin.glyphs[0].height, thick.glyphs[0].height);
    assert!(generate(CFF, &cfg).is_err());
}
