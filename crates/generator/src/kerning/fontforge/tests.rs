use super::*;
use crate::{
    mono_spacing::FontSpacingProperties, reference::RasterPolicy, reference::ReferenceRecord, Glyph,
};

fn commands(value: &serde_json::Value) -> Vec<FittedCommand> {
    value
        .as_array()
        .unwrap()
        .iter()
        .map(|c| {
            let n = |key: &str| c[key].as_f64().unwrap() as f32;
            match c["op"].as_str().unwrap() {
                "move_to" => FittedCommand::MoveTo(n("x"), n("y")),
                "line_to" => FittedCommand::LineTo(n("x"), n("y")),
                "quad_to" => FittedCommand::QuadTo(n("x1"), n("y1"), n("x"), n("y")),
                "curve_to" => {
                    FittedCommand::CurveTo(n("x1"), n("y1"), n("x2"), n("y2"), n("x"), n("y"))
                }
                "close" => FittedCommand::Close,
                other => panic!("unknown fixture command {other}"),
            }
        })
        .collect()
}

#[test]
fn matches_independent_original_native_envelopes_and_weighted_pairs() {
    let fixture: serde_json::Value =
        serde_json::from_str(include_str!("../../../tests/fontforge/native.json")).unwrap();
    assert_eq!(
        fixture["native_build_identity"]["revision"],
        "c41bdb922285f35defd1e1385adfd13bde1ab32a"
    );
    for case in fixture["cases"].as_array().unwrap() {
        let em = case["native"]["em_size"].as_u64().unwrap() as u16;
        let mut envelopes = Vec::new();
        for (input, expected) in case["inputs"]
            .as_array()
            .unwrap()
            .iter()
            .zip(case["native"]["glyphs"].as_array().unwrap())
        {
            let label = format!("{} {}", case["font"], input["label"]);
            let actual = analyze(
                &commands(&input["commands"]),
                input["scale"].as_f64().unwrap(),
                em,
            )
            .unwrap()
            .unwrap();
            for (key, value) in [
                ("minx", actual.bounds.minx),
                ("miny", actual.bounds.miny),
                ("maxx", actual.bounds.maxx),
                ("maxy", actual.bounds.maxy),
            ] {
                assert!(
                    (value - expected["bounds"][key].as_f64().unwrap()).abs() < 1e-9,
                    "{label} {key}"
                );
            }
            assert_eq!(
                actual.imin,
                expected["imin_y"].as_i64().unwrap() as i32,
                "{label}"
            );
            assert_eq!(
                actual.imax,
                expected["imax_y"].as_i64().unwrap() as i32,
                "{label}"
            );
            for (i, (a, e)) in actual
                .edges
                .iter()
                .zip(expected["bands"].as_array().unwrap())
                .enumerate()
            {
                let (left, right) = a
                    .map(|(l, r)| (i32::from(l), i32::from(r)))
                    .unwrap_or((32767, -32767));
                assert_eq!(
                    (left, right),
                    (
                        e["left"].as_i64().unwrap() as i32,
                        e["right"].as_i64().unwrap() as i32
                    ),
                    "{label} band {}",
                    i as i32 + actual.imin
                );
            }
            envelopes.push(actual);
        }
        for (i, a) in envelopes.iter().enumerate() {
            for (j, b) in envelopes.iter().enumerate() {
                assert_eq!(
                    separation(a, b, em).unwrap().unwrap_or(0.0),
                    case["native"]["pair_estimates"][i][j].as_f64().unwrap(),
                    "{} pair {i}/{j}",
                    case["font"]
                );
            }
        }
    }
}

fn rectangle(x: f32, y: f32, w: f32, h: f32) -> Vec<FittedCommand> {
    vec![
        FittedCommand::MoveTo(x, y),
        FittedCommand::LineTo(x + w, y),
        FittedCommand::LineTo(x + w, y + h),
        FittedCommand::LineTo(x, y + h),
        FittedCommand::Close,
    ]
}

#[test]
fn band_boundary_empty_and_native_unrepresentable_geometry_abstain() {
    let a = analyze(&rectangle(0., 0., 100., 10.), 1., 1000)
        .unwrap()
        .unwrap();
    let b = analyze(&rectangle(0., 10., 100., 10.), 1., 1000)
        .unwrap()
        .unwrap();
    assert_eq!(a.edges.len(), 3);
    assert_eq!(
        separation(&a, &b, 1000).unwrap(),
        None,
        "upper shared boundary excluded"
    );
    assert!(analyze(&[], 1., 1000).unwrap().is_none());
    assert!(analyze(&rectangle(0., 0., 100., 100.), 1., 199)
        .unwrap()
        .is_none());
    let wide = vec![
        FittedCommand::MoveTo(0., 0.),
        FittedCommand::LineTo(100_000., 100.),
        FittedCommand::LineTo(0., 200.),
        FittedCommand::Close,
    ];
    assert!(analyze(&wide, 1., 1000).unwrap().is_none());
    assert!(analyze(&rectangle(0., 0., 100., 100.), f64::NAN, 1000).is_err());
    assert!(analyze(&rectangle(0., 0., 100., 1_000_000.), 1., 1000).is_err());
}

fn test_glyph(codepoint: u32) -> Glyph {
    Glyph {
        codepoint,
        glyph_id: codepoint,
        advance_26_6: 640,
        left: 0,
        top: 0,
        width: 0,
        height: 0,
        pixels: Vec::new(),
    }
}

fn test_record(codepoint: u32, fitted_commands: Vec<FittedCommand>) -> ReferenceRecord {
    ReferenceRecord {
        side_bearing_deltas_26_6: None,
        raster_policy: RasterPolicy::Coverage,
        mono_rasterizer: None,
        mono_raster: None,
        font_scan: None,
        diagonal_pairs: None,
        codepoint,
        glyph_id: codepoint,
        selected_engine: String::new(),
        target: String::new(),
        smooth_mode: None,
        symmetric_rendering: None,
        preserve_linear_metrics: None,
        draw_pedantic: false,
        skrifa_version: String::new(),
        skrifa_registry_checksum: String::new(),
        zeno_version: String::new(),
        zeno_format: String::new(),
        output_bits: 3,
        mono_threshold: 128,
        gray_gamma: 1.,
        fitted_commands,
        source_commands: None,
        width_fitting: None,
        selective_fitting: None,
        diagonal_fitting: None,
        top_alignment: None,
        baseline_alignment: None,
        extremity_phase: None,
        coverage: vec![],
        coverage_sha256: String::new(),
        left: 0,
        top: 0,
        width: 0,
        height: 0,
        pixels: vec![],
        advance_26_6: 640,
        hinted_has_overlaps: false,
        hinted_lsb: None,
        hinted_advance_width: None,
    }
}

fn resolve_with(
    glyphs: &[Glyph],
    records: &[ReferenceRecord],
    source_commands: &HashMap<u32, Vec<FittedCommand>>,
    source_advances_26_6: &HashMap<u32, i32>,
    advances_26_6: &HashMap<u32, i32>,
    properties: FontSpacingProperties,
    output_bits: u8,
    size_px: f64,
) -> Result<super::super::PairAdjustments, Error> {
    let empty_pairs = HashMap::new();
    let context = super::super::MethodContext {
        glyphs,
        records,
        source_commands,
        source_advances_26_6,
        source_pairs_26_6: &empty_pairs,
        advances_26_6,
        pair_adjustments_26_6: &empty_pairs,
        output_bits,
        units_per_em: 1000,
        size_px,
        ascender_26_6: 0,
        properties,
        source_kerning: false,
    };
    super::resolve(&context, &FontforgeSettings::default())
}

fn spacing_properties(monospace: bool) -> FontSpacingProperties {
    FontSpacingProperties {
        monospace,
        tabular_digits: false,
    }
}

#[test]
fn monospace_resolve_retains_every_pair_without_analysis() {
    let glyphs = vec![test_glyph(65), test_glyph(66)];
    let actual = resolve_with(
        &glyphs,
        &[],
        &HashMap::new(),
        &HashMap::new(),
        &HashMap::new(),
        spacing_properties(true),
        1,
        16.,
    )
    .unwrap();
    assert_eq!(actual.len(), 4);
    for decision in actual.values() {
        assert_eq!(
            *decision,
            super::super::PairDecision::RetainSource("fixed_pitch")
        );
    }
}

#[test]
fn seed_reasons_cover_whitespace_and_tabular_digits() {
    let glyphs = vec![test_glyph(32), test_glyph(48), test_glyph(49)];
    let actual = resolve_with(
        &glyphs,
        &[],
        &HashMap::new(),
        &HashMap::new(),
        &HashMap::new(),
        FontSpacingProperties {
            monospace: false,
            tabular_digits: true,
        },
        3,
        16.,
    )
    .unwrap();
    assert_eq!(actual.len(), 9);
    for (pair, expected) in [
        ((32, 32), "whitespace"),
        ((32, 48), "whitespace"),
        ((48, 32), "whitespace"),
        ((48, 48), "source_tabular_digits"),
        ((48, 49), "source_tabular_digits"),
        ((49, 48), "source_tabular_digits"),
        ((49, 49), "source_tabular_digits"),
    ] {
        assert_eq!(
            actual[&pair],
            super::super::PairDecision::RetainSource(expected),
            "{pair:?}"
        );
    }
}

#[test]
fn resolve_rejects_unscalable_and_missing_geometry() {
    let glyphs = vec![test_glyph(65)];
    let advances: HashMap<u32, i32> = [(65, 640)].into_iter().collect();
    assert!(
        resolve_with(
            &glyphs,
            &[],
            &HashMap::new(),
            &HashMap::new(),
            &advances,
            spacing_properties(false),
            3,
            0.,
        )
        .is_err(),
        "a zero size must fail the coordinate scale check"
    );
    let outline = rectangle(0., 0., 100., 100.);
    for (present, expected) in [
        (HashMap::new(), "FontForge source outline is missing"),
        (
            [(65, outline)].into_iter().collect(),
            "FontForge fitted outline is missing",
        ),
    ] {
        assert_eq!(
            resolve_with(
                &glyphs,
                &[],
                &present,
                &HashMap::new(),
                &advances,
                spacing_properties(false),
                3,
                16.,
            )
            .unwrap_err()
            .0,
            expected
        );
    }
}

#[test]
fn gray_pairs_apply_full_correction_and_skip_tabular_digits() {
    let glyphs = vec![test_glyph(65), test_glyph(48), test_glyph(49)];
    let outline = rectangle(0., 0., 100., 100.);
    let source_commands: HashMap<u32, Vec<FittedCommand>> =
        [(65, outline.clone()), (48, outline.clone()), (49, outline)]
            .into_iter()
            .collect();
    let records: Vec<_> = [65, 48, 49]
        .into_iter()
        .map(|cp| test_record(cp, source_commands[&cp].clone()))
        .collect();
    let advances: HashMap<u32, i32> = [(65, 640), (48, 640), (49, 640)].into_iter().collect();
    let actual = resolve_with(
        &glyphs,
        &records,
        &source_commands,
        &advances,
        &advances,
        FontSpacingProperties {
            monospace: false,
            tabular_digits: true,
        },
        3,
        16.,
    )
    .unwrap();
    assert_eq!(actual.len(), 9);
    for pair in [(48, 48), (48, 49), (49, 48), (49, 49)] {
        assert_eq!(
            actual[&pair],
            super::super::PairDecision::RetainSource("source_tabular_digits"),
            "{pair:?} must skip solving"
        );
    }
    for pair in [(65, 65), (65, 48), (48, 65)] {
        let super::super::PairDecision::Replace(adjustment) = actual[&pair] else {
            panic!(
                "{pair:?} must carry the full correction, got {:?}",
                actual[&pair]
            );
        };
        assert_eq!(adjustment % 64, 0, "{pair:?} must stay whole-pixel");
    }
}

fn envelope_for_test(imin: i32, edges: Vec<Option<(i16, i16)>>) -> Envelope {
    Envelope {
        bounds: Bounds {
            minx: 0.,
            miny: 0.,
            maxx: 100.,
            maxy: 100.,
        },
        imin,
        imax: imin + edges.len() as i32 - 1,
        edges,
    }
}

#[test]
fn solve_honors_the_pinned_endpoint_rule() {
    // Constant polynomials carry their value to both endpoints.
    assert_eq!(solve([0., 0., 0., 5e-5], 0., 10., 0.).unwrap(), Some(0.));
    assert_eq!(solve([0., 0., 0., -5e-5], 0., 10., 0.).unwrap(), Some(0.));
    // Exactly on the rule boundary the endpoints do not count as hits.
    assert_eq!(solve([0., 0., 0., 1e-4], 0., 10., 0.).unwrap(), None);
    assert_eq!(solve([0., 0., 0., -1e-4], 0., 10., 0.).unwrap(), None);
    // Far values abstain without bracketing.
    assert_eq!(solve([0., 0., 0., 0.5], 0., 10., 0.).unwrap(), None);
    // The linear fast path pins to the interval.
    assert_eq!(solve([0., 0., 2., 0.], 0., 10., 4.).unwrap(), Some(2.));
    assert_eq!(solve([0., 0., 2., 0.], 0., 10., 40.).unwrap(), None);
    // A genuine cubic must not take the linear path: 3t^3 + 2t - 4 crosses
    // near 0.901, far from the linear -c[3]/c[2] = 2.
    let root = solve([3., 0., 2., 0.], 0., 10., 4.).unwrap().unwrap();
    assert!(
        (root - 0.901).abs() < 0.01,
        "cubic root {root} must not use the linear shortcut"
    );
}

#[test]
fn separation_rejects_a_nonpositive_weight_divisor() {
    // sep = b - a = 0 - 20 = -20 with em 1000 gives divisor -20 + 20 = 0.
    // The trailing band stays empty: the shared top boundary is excluded
    // from the weighted mean by construction.
    let left = envelope_for_test(0, vec![Some((0, 20)), None]);
    let right = envelope_for_test(0, vec![Some((0, 0)), None]);
    assert_eq!(
        separation(&left, &right, 1000).unwrap_err().0,
        "FontForge weight divisor must be positive"
    );
    // A negative divisor fails the same guard.
    let right = envelope_for_test(0, vec![Some((0, -5)), None]);
    assert_eq!(
        separation(&left, &right, 1000).unwrap_err().0,
        "FontForge weight divisor must be positive"
    );
}

#[test]
fn step_encoding_holds_the_integer_placement_range() {
    let (min, max) = (f64::from(i32::MIN / 64), f64::from(i32::MAX / 64));
    assert!(encode_step_adjustment(min, 0).is_ok());
    assert!(encode_step_adjustment(max, 0).is_ok());
    for step in [min - 1., max + 1., f64::NAN] {
        assert_eq!(
            encode_step_adjustment(step, 0).unwrap_err().0,
            "FontForge integer placement range exceeded",
            "step {step} must fail the range guard"
        );
    }
}

#[test]
fn mono_pairs_apply_full_correction_without_cell_overlap() {
    let glyph = |codepoint: u32| Glyph {
        codepoint,
        glyph_id: codepoint,
        advance_26_6: 640,
        left: 0,
        top: 0,
        width: 2,
        height: 2,
        pixels: vec![1, 1, 1, 1],
    };
    let glyphs = vec![glyph(65), glyph(66)];
    let outline = rectangle(0., 0., 100., 100.);
    let source_commands: HashMap<u32, Vec<FittedCommand>> =
        [(65, outline.clone()), (66, outline)].into_iter().collect();
    let records: Vec<_> = [65, 66]
        .into_iter()
        .map(|cp| test_record(cp, source_commands[&cp].clone()))
        .collect();
    let advances: HashMap<u32, i32> = [(65, 640), (66, 640)].into_iter().collect();
    let actual = resolve_with(
        &glyphs,
        &records,
        &source_commands,
        &advances,
        &advances,
        spacing_properties(false),
        1,
        16.,
    )
    .unwrap();
    assert_eq!(actual.len(), 4);
    for (pair, decision) in &actual {
        let super::super::PairDecision::Replace(adjustment) = decision else {
            panic!("{pair:?} must carry the full correction, got {decision:?}");
        };
        assert_eq!(adjustment % 64, 0, "{pair:?} must stay whole-pixel");
    }
}

#[test]
fn settings_reject_strength_and_unknown_fields() {
    FontforgeSettings::default().validate().unwrap();
    assert_eq!(
        serde_json::from_str::<FontforgeSettings>("{}").unwrap(),
        FontforgeSettings::default()
    );
    for rejected in [
        "{\"strength\":0}",
        "{\"strength\":0.5}",
        "{\"strength\":1}",
        "{\"strength\":null}",
        "{\"strength\":\"1\"}",
        "{\"strength\":1,\"target\":0}",
        "{\"target\":0}",
    ] {
        assert!(
            serde_json::from_str::<FontforgeSettings>(rejected).is_err(),
            "{rejected} must not parse"
        );
    }
}

#[cfg(feature = "candidate")]
#[test]
fn four_font_gray_source_kerning_smoke() {
    use crate::{
        candidate,
        renderer::{Rasterization, RenderPipeline},
        stem_fitting::StemFittingStrategy,
        Config, KerningMethod,
    };
    let pipeline = RenderPipeline {
        fitting: StemFittingStrategy::UpstreamMono,
        rasterization: Rasterization::Coverage,
        diagonal_fitting: false,
    };
    for (name, data) in [
        (
            "Literata",
            include_bytes!("../../../../../fonts/Literata.ttf").as_slice(),
        ),
        (
            "Roboto",
            include_bytes!("../../../../../fonts/Roboto.ttf").as_slice(),
        ),
        (
            "RobotoFlex",
            include_bytes!("../../../../../fonts/RobotoFlex.ttf").as_slice(),
        ),
        (
            "SourceSans3",
            include_bytes!("../../../../../fonts/SourceSans3.ttf").as_slice(),
        ),
    ] {
        let mut endpoints = Vec::new();
        for source_enabled in [false, true] {
            let config = Config {
                characters: "AVTo caenrios".into(),
                size_px: 16.,
                output_bits: 3,
                kerning: source_enabled,
                ..Config::default()
            };
            let source = candidate::generate_bitmap_font_with_pipeline_and_kerning(
                data,
                &config,
                pipeline,
                0.,
                KerningMethod::Source,
            )
            .unwrap();
            let start = std::time::Instant::now();
            let actual = candidate::generate_bitmap_font_with_pipeline_and_kerning(
                data,
                &config,
                pipeline,
                0.,
                KerningMethod::Fontforge(FontforgeSettings::default()),
            )
            .unwrap_or_else(|e| panic!("{name} Gray source={source_enabled}: {e}"));
            assert_eq!(
                source.glyphs, actual.glyphs,
                "{name}: spacing must not change outlines, bitmap, offsets or advances"
            );
            assert!(actual.kerning.iter().all(|p| p.adjustment_26_6 % 64 == 0));
            assert_ne!(
                source, actual,
                "{name}: the full correction must move at least one pair"
            );
            endpoints.push(actual.kerning.clone());
            eprintln!(
                "FontForge {name} Gray3 source={source_enabled}: {:?}",
                start.elapsed()
            );
        }
        assert_ne!(
            endpoints[0], endpoints[1],
            "{name}: source-relative endpoint must honor the source-kerning selection"
        );
    }
}
