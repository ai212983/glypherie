//! Routing contracts for promotion, not optical scores or frozen glyph snapshots.
use font_generator::{
    generate,
    probe::{rasterize, FittedPen},
    Config, Glyph, Hinting,
};
use skrifa::{
    instance::Size,
    outline::{DrawSettings, Engine, HintingInstance, HintingOptions, SmoothMode, Target},
    FontRef, MetadataProvider,
};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
};

fn font(name: &str) -> Vec<u8> {
    std::fs::read(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../fonts")
            .join(name),
    )
    .unwrap()
}
fn config(name: &str, size: f32, characters: &str) -> Config {
    let mut axes = BTreeMap::from([("wght".into(), 400.0)]);
    if name == "Roboto.ttf" {
        axes.insert("wdth".into(), 100.0);
    }
    if name == "Literata.ttf" {
        axes.insert("opsz".into(), size);
    }
    Config {
        size_px: size,
        axes,
        characters: characters.into(),
        ..Config::default()
    }
}

// Independent registry rendering with the EXISTING production gray target.
// ReferenceRequest uses preserve_linear_metrics=false, whereas production uses
// true. Comparing those unlike targets would invent a promotion regression.
fn upstream_glyphs(data: &[u8], config: &Config) -> Vec<Glyph> {
    let font = FontRef::new(data).unwrap();
    let size = Size::new(config.size_px);
    let location = font
        .axes()
        .location(config.axes.iter().map(|(t, v)| (t.as_str(), *v)));
    let outlines = font.outline_glyphs();
    let target = if config.output_bits == 1 {
        Target::Mono
    } else {
        Target::Smooth {
            mode: SmoothMode::Normal,
            symmetric_rendering: true,
            preserve_linear_metrics: true,
        }
    };
    let engine = match config.hinting {
        Hinting::Auto => Engine::Auto(None),
        Hinting::Interpreter => Engine::Interpreter,
        _ => Engine::AutoFallback,
    };
    let hinting = (config.hinting != Hinting::None).then(|| {
        HintingInstance::new(
            &outlines,
            size,
            &location,
            HintingOptions { engine, target },
        )
        .unwrap()
    });
    let advances = font.glyph_metrics(size, &location);
    config
        .characters
        .chars()
        .collect::<BTreeSet<_>>()
        .into_iter()
        .map(|ch| {
            let gid = font.charmap().map(ch).unwrap();
            let mut pen = FittedPen::default();
            let settings = hinting.as_ref().map_or_else(
                || DrawSettings::unhinted(size, &location),
                |h| DrawSettings::hinted(h, false),
            );
            outlines.get(gid).unwrap().draw(settings, &mut pen).unwrap();
            let bitmap = rasterize(pen.commands(), config).unwrap();
            Glyph {
                codepoint: ch as u32,
                glyph_id: gid.to_u32(),
                advance_26_6: (advances.advance_width(gid).unwrap() * 64.0).round() as i32,
                left: bitmap.left,
                top: bitmap.top,
                width: bitmap.width,
                height: bitmap.height,
                pixels: bitmap.pixels,
            }
        })
        .collect()
}

#[test]
fn default_jobs_select_reviewed_automatic_settings() {
    assert_eq!(Hinting::default(), Hinting::Auto);
    let config: Config = serde_json::from_str(r#"{"size_px":16,"characters":"A"}"#).unwrap();
    assert_eq!(config.hinting, Hinting::Auto);
    assert_eq!(config.output_bits, 1);
    assert_eq!(config.mono_threshold, 128);
}

#[test]
fn role_dispatch_keeps_reference_and_baseline_available_without_candidate() {
    use font_generator::{
        reference::ReferenceRequest,
        renderer::{render, RendererRole},
    };
    let data = include_bytes!("fixtures/static-cff.otf");
    let mut request = ReferenceRequest {
        profile: "mono_1bit".into(),
        extensions: "none".into(),
        settings: Config {
            characters: "A".into(),
            ..Config::default()
        },
    };
    assert!(
        !render(data, &request, RendererRole::Reference)
            .unwrap()
            .fork
    );
    request.extensions = font_generator::baseline::EXTENSIONS_DIAGONAL_01.into();
    assert!(render(data, &request, RendererRole::Baseline).unwrap().fork);
    // The candidate no longer accepts the baseline's diagonal policy.
    let candidate = render(data, &request, RendererRole::Candidate);
    if cfg!(feature = "candidate") {
        assert!(candidate.is_err());
    } else {
        assert!(candidate
            .unwrap_err()
            .to_string()
            .contains("candidate Cargo feature"));
    }
    request.extensions = font_generator::stem_fitting::EXTENSIONS_FONT_HINTS_FIRST.into();
    let candidate = render(data, &request, RendererRole::Candidate);
    if cfg!(feature = "candidate") {
        // Registry-based candidate: no fork identity is reported.
        assert!(!candidate.unwrap().fork);
    } else {
        assert!(candidate
            .unwrap_err()
            .to_string()
            .contains("candidate Cargo feature"));
    }
}

#[test]
fn production_matches_approved_baseline_over_preview_matrix() {
    use font_generator::{
        baseline::{render, EXTENSIONS_DIAGONAL_01},
        reference::ReferenceRequest,
    };
    let repertoire: String = (33u8..=126).map(char::from).chain(['°']).collect();
    for name in ["Roboto.ttf", "Literata.ttf", "SourceSans3.ttf"] {
        let data = font(name);
        for size in [14.0, 16.0, 18.0, 20.0] {
            let settings = config(name, size, &repertoire);
            let request = ReferenceRequest {
                profile: "mono_1bit".into(),
                extensions: EXTENSIONS_DIAGONAL_01.into(),
                settings: settings.clone(),
            };
            let reviewed = render(&data, &request).unwrap();
            for record in reviewed.records {
                // Generate each scalar independently. Some full-corpus pairs
                // need text-run substitutions even with kerning disabled;
                // promotion must not relax that separate capability contract.
                let mut single = settings.clone();
                single.characters = char::from_u32(record.codepoint).unwrap().to_string();
                let produced = match generate(&data, &single) {
                    Ok(produced) => produced,
                    Err(error) => {
                        // Existing text-run capability validation also checks
                        // self-pairs. Retain rejection of required substitutions;
                        // no fitting/outline error may be excused here.
                        assert!(error.to_string().contains("requires substitutions or positioning beyond scalar glyphs and pair kerning"), "{name} {size}: {error}");
                        continue;
                    }
                };
                assert_eq!(produced.metrics, reviewed.metrics, "{name} {size}");
                assert_eq!(
                    produced.glyphs,
                    vec![Glyph {
                        codepoint: record.codepoint,
                        glyph_id: record.glyph_id,
                        advance_26_6: record.advance_26_6,
                        left: record.left,
                        top: record.top,
                        width: record.width,
                        height: record.height,
                        pixels: record.pixels,
                    }],
                    "{name} {size} U+{:04X}",
                    record.codepoint
                );
            }
        }
    }
}

#[test]
fn low_weight_mono_matches_approved_baseline_without_ink_targets() {
    use font_generator::{
        baseline::{render, EXTENSIONS_DIAGONAL_01},
        reference::ReferenceRequest,
    };
    let data = font("Roboto.ttf");
    // Bounded fractional-role witnesses: approved dropout plus the smooth
    // near-1.5px standard must reproduce the approved baseline exactly. No
    // ink totals are asserted, only baseline parity, layout and delivered
    // ink presence for these continuity-sensitive characters.
    for size in [14.0, 16.0, 18.0, 20.0] {
        for weight in [100.0, 200.0, 400.0, 459.0, 460.0, 465.0] {
            for width in [75.0, 100.0] {
                let mut settings = config("Roboto.ttf", size, "aHIAVxyn");
                settings.axes.insert("wght".into(), weight);
                settings.axes.insert("wdth".into(), width);
                let request = ReferenceRequest {
                    profile: "mono_1bit".into(),
                    extensions: EXTENSIONS_DIAGONAL_01.into(),
                    settings: settings.clone(),
                };
                let reviewed = render(&data, &request).unwrap();
                assert_eq!(reviewed.records.len(), 8);
                for record in reviewed.records {
                    let mut single = settings.clone();
                    single.characters = char::from_u32(record.codepoint).unwrap().to_string();
                    let produced = generate(&data, &single).unwrap();
                    let context = format!(
                        "Roboto {size} wght{weight} wdth{width} U+{:04X}",
                        record.codepoint
                    );
                    assert_eq!(produced.metrics, reviewed.metrics, "{context}");
                    assert_eq!(produced.glyphs.len(), 1, "{context}");
                    let glyph = &produced.glyphs[0];
                    assert_eq!(glyph.advance_26_6, record.advance_26_6, "{context}");
                    assert_eq!(
                        (glyph.left, glyph.top, glyph.width, glyph.height),
                        (record.left, record.top, record.width, record.height),
                        "{context}"
                    );
                    assert_eq!(glyph.pixels, record.pixels, "{context}");
                    assert!(glyph.pixels.iter().any(|pixel| *pixel != 0), "{context}");
                }
            }
        }
    }
}

#[test]
fn explicit_engines_and_gray_keep_upstream_production_settings() {
    for name in ["Roboto.ttf", "Literata.ttf", "SourceSans3.ttf"] {
        let data = font(name);
        for size in [14.0, 16.0, 18.0, 20.0] {
            for bits in [1, 2, 3, 4, 8] {
                for mode in [Hinting::None, Hinting::Interpreter, Hinting::Auto] {
                    if bits == 1 && mode == Hinting::Auto {
                        continue;
                    }
                    let mut settings = config(name, size, "AQVwxy09");
                    settings.hinting = mode;
                    settings.output_bits = bits;
                    let actual = generate(&data, &settings).unwrap();
                    assert_eq!(
                        actual.glyphs,
                        upstream_glyphs(&data, &settings),
                        "{name} {size} {bits} {mode:?}"
                    );
                }
            }
        }
    }
}

#[test]
fn explicit_fallback_preserves_the_upstream_font_engine_selection() {
    let cff = include_bytes!("fixtures/static-cff.otf").to_vec();
    for data in [
        font("Roboto.ttf"),
        font("Literata.ttf"),
        font("SourceSans3.ttf"),
        cff,
    ] {
        let outlines = FontRef::new(&data).unwrap().outline_glyphs();
        let selected = if outlines.prefer_interpreter() {
            Hinting::Interpreter
        } else {
            Hinting::Auto
        };
        let settings = Config {
            characters: "A".into(),
            hinting: Hinting::AutoFallback,
            ..Config::default()
        };
        let actual = generate(&data, &settings).unwrap();
        let expected = generate(
            &data,
            &Config {
                hinting: selected,
                ..settings
            },
        )
        .unwrap();
        assert_eq!(actual.glyphs, expected.glyphs);
        assert_eq!(actual.metrics, expected.metrics);
        assert_eq!(actual.kerning, expected.kerning);
    }
}
