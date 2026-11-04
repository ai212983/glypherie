use super::*;

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

#[test]
fn settings_are_strict_and_strength_zero_is_valid() {
    for value in [0., 0.5, 1.] {
        FontforgeSettings { strength: value }.validate().unwrap();
    }
    for value in [-0.1, 1.1, f64::INFINITY, f64::NAN] {
        assert!(FontforgeSettings { strength: value }.validate().is_err());
    }
    assert_eq!(
        serde_json::from_str::<FontforgeSettings>("{}").unwrap(),
        FontforgeSettings::default()
    );
    assert!(serde_json::from_str::<FontforgeSettings>("{\"strength\":1,\"target\":0}").is_err());
}

#[cfg(feature = "candidate")]
#[test]
fn four_font_gray_strength_and_source_kerning_smoke() {
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
            for strength in [0., 0.5, 1.] {
                let start = std::time::Instant::now();
                let actual = candidate::generate_bitmap_font_with_pipeline_and_kerning(
                    data,
                    &config,
                    pipeline,
                    0.,
                    KerningMethod::Fontforge(FontforgeSettings { strength }),
                )
                .unwrap_or_else(|e| {
                    panic!("{name} Gray source={source_enabled} strength={strength}: {e}")
                });
                assert_eq!(
                    source.glyphs, actual.glyphs,
                    "{name}: spacing must not change outlines, bitmap, offsets or advances"
                );
                assert!(actual.kerning.iter().all(|p| p.adjustment_26_6 % 64 == 0));
                if strength == 0. {
                    assert_eq!(
                        source, actual,
                        "{name}: zero must bypass feasibility and all analysis"
                    );
                }
                if strength == 1. {
                    endpoints.push(actual.kerning.clone());
                }
                eprintln!(
                    "FontForge {name} Gray3 source={source_enabled} strength={strength}: {:?}",
                    start.elapsed()
                );
            }
        }
        assert_ne!(
            endpoints[0], endpoints[1],
            "{name}: source-relative endpoint must honor the source-kerning selection"
        );
    }
}
