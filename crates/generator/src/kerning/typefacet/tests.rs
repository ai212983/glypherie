use super::*;
use serde_json::Value;

fn geometry(value: &Value) -> Vec<GeometryGlyph> {
    value
        .as_array()
        .unwrap()
        .iter()
        .map(|g| GeometryGlyph {
            codepoint: g["codepoint"].as_u64().unwrap() as u32,
            contours: g["contours"]
                .as_array()
                .unwrap()
                .iter()
                .map(|contour| {
                    contour
                        .as_array()
                        .unwrap()
                        .iter()
                        .map(|segment| {
                            let p: Vec<_> = segment
                                .as_array()
                                .unwrap()
                                .iter()
                                .map(|p| Point {
                                    x: p[0].as_f64().unwrap(),
                                    y: p[1].as_f64().unwrap(),
                                })
                                .collect();
                            match p.as_slice() {
                                [a, b] => Segment::Line([*a, *b]),
                                [a, b, c] => Segment::Quad([*a, *b, *c]),
                                [a, b, c, d] => Segment::Cubic([*a, *b, *c, *d]),
                                _ => panic!("invalid fixture segment"),
                            }
                        })
                        .collect()
                })
                .collect(),
        })
        .collect()
}

fn assert_profiles(prepared: &Prepared, source: &Value, names: &Value) {
    let old_min = source["profile_min_y_units"].as_i64().unwrap() as i32;
    for shape in &prepared.shapes {
        let name = names
            .as_array()
            .unwrap()
            .iter()
            .find(|g| g["codepoint"].as_u64() == Some(u64::from(shape.codepoint)))
            .unwrap()["name"]
            .as_str()
            .unwrap();
        let original = &source["profiles"][name];
        if original.is_null() {
            continue;
        }
        for (label, profile) in [
            ("raw", &shape.raw),
            ("minimum", &shape.minimum),
            ("maximum", &shape.maximum),
        ] {
            for (side, values) in [&profile.left, &profile.right].into_iter().enumerate() {
                for (row, value) in values.iter().enumerate() {
                    let original_row = row as i32 + prepared.grid.min - old_min;
                    let expected = if original_row < 0 {
                        None
                    } else {
                        original[label][side][original_row as usize].as_f64()
                    };
                    assert!(
                        match (*value, expected) {
                            (Some(a), Some(b)) => (a - b).abs() < 1e-10,
                            (None, None) => true,
                            _ => false,
                        },
                        "{name}/{label}/{side}/y{} actual{value:?} expected{expected:?}",
                        row as i32 + prepared.grid.min
                    );
                }
            }
        }
    }
}

#[test]
fn original_curve_profiles_constraints_and_predicates() {
    let f: Value =
        serde_json::from_str(include_str!("../../../tests/typefacet/curves.json")).unwrap();
    let glyphs = geometry(&f["glyphs"]);
    let settings: TypefacetSettings = serde_json::from_value(f["settings"].clone()).unwrap();
    let prepared = prepare(
        &glyphs,
        f["units_per_em"].as_u64().unwrap() as u16,
        f["ascender_units"].as_f64().unwrap(),
        &settings,
    )
    .unwrap();
    assert_profiles(&prepared, &f["profiles"], &f["glyphs"]);
    assert!(prepared.codepoints().any(|cp| cp == 945));
    let mut budget = WorkBudget::default();
    for pair in f["pairs"].as_array().unwrap() {
        let constraint = prepared
            .pair(
                pair["left"].as_u64().unwrap() as u32,
                pair["right"].as_u64().unwrap() as u32,
            )
            .unwrap();
        for (label, actual) in [
            ("minimum_units", constraint.minimum_units),
            ("maximum_units", constraint.maximum_units),
            ("extrema_bound_units", constraint.extrema_bound_units),
        ] {
            assert!(
                (actual - pair[label].as_f64().unwrap()).abs() < 1e-10,
                "{label} pair{pair}"
            );
        }
        for trial in pair["trials"].as_array().unwrap() {
            let origin = trial[0].as_f64().unwrap();
            for (within, index) in [(false, 1), (true, 2)] {
                assert_eq!(
                    intrusion(
                        constraint.left,
                        constraint.right,
                        origin,
                        prepared.normal,
                        prepared.tolerance,
                        prepared.grid,
                        prepared.ascender,
                        within,
                        &mut budget
                    )
                    .unwrap(),
                    trial[index].as_bool().unwrap(),
                    "pair{}{} origin{origin} within{within}",
                    pair["left"],
                    pair["right"]
                );
            }
            assert_eq!(
                constraint.admissible(origin, &mut budget).unwrap(),
                trial[3].as_bool().unwrap(),
                "admissible pair{}{} origin{origin}",
                pair["left"],
                pair["right"]
            );
        }
    }
}

#[test]
fn original_nonzero_minimum_and_extrema_control_profiles_and_predicates() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../tests/typefacet/adjustment-controls.json"
    ))
    .unwrap();
    let glyphs = geometry(&fixture["glyphs"]);
    for case in fixture["cases"].as_array().unwrap() {
        let settings: TypefacetSettings = serde_json::from_value(case["settings"].clone()).unwrap();
        let prepared = prepare(&glyphs, 1000, 800.0, &settings).unwrap();
        assert_profiles(&prepared, &case["profiles"], &fixture["glyphs"]);
        let mut budget = WorkBudget::default();
        for record in case["pairs"].as_array().unwrap() {
            let pair = prepared
                .pair(
                    record["left"].as_u64().unwrap() as u32,
                    record["right"].as_u64().unwrap() as u32,
                )
                .unwrap();
            for (label, actual) in [
                ("minimum_units", pair.minimum_units),
                ("maximum_units", pair.maximum_units),
                ("extrema_bound_units", pair.extrema_bound_units),
            ] {
                assert!(
                    (actual - record[label].as_f64().unwrap()).abs() < 1e-10,
                    "{} {label}: actual{actual} expected{}",
                    case["label"],
                    record[label]
                );
            }
            for trial in record["trials"].as_array().unwrap() {
                let origin = trial[0].as_f64().unwrap();
                for (within, index) in [(false, 1), (true, 2)] {
                    assert_eq!(
                        intrusion(
                            pair.left,
                            pair.right,
                            origin,
                            prepared.normal,
                            prepared.tolerance,
                            prepared.grid,
                            prepared.ascender,
                            within,
                            &mut budget,
                        )
                        .unwrap(),
                        trial[index].as_bool().unwrap(),
                        "{}: {record}, origin{origin}, ascender{within}",
                        case["label"]
                    );
                }
                assert_eq!(
                    pair.admissible(origin, &mut budget).unwrap(),
                    trial[3].as_bool().unwrap(),
                    "{}: {record}, origin{origin}",
                    case["label"]
                );
            }
        }
    }
}

#[test]
fn original_literata_profiles_and_every_selected_predicate() {
    let f: Value =
        serde_json::from_str(include_str!("../../../tests/typefacet/literata.json")).unwrap();
    let input: Value = serde_json::from_str(include_str!(
        "../../../tests/typefacet/literata-geometry.json"
    ))
    .unwrap();
    let glyphs = geometry(&input["glyphs"]);
    for key in ["profiles", "numerical_profiles"] {
        let p = &f[key];
        let settings = TypefacetSettings {
            normal_distance_em: p["parameters"]["max_distance_ems"].as_f64().unwrap(),
            intrusion_tolerance_em: p["parameters"]["intrusion_tolerance_ems"].as_f64().unwrap(),
            ..TypefacetSettings::default()
        };
        let prepared = prepare(
            &glyphs,
            input["units_per_em"].as_u64().unwrap() as u16,
            input["ascender_units"].as_f64().unwrap(),
            &settings,
        )
        .unwrap();
        assert_profiles(&prepared, p, &input["glyphs"]);
    }
    let trials = &f["predicate_trials"];
    let settings = TypefacetSettings {
        normal_distance_em: trials["normal_distance_em"].as_f64().unwrap(),
        intrusion_tolerance_em: trials["intrusion_tolerance_em"].as_f64().unwrap(),
        ..TypefacetSettings::default()
    };
    let prepared = prepare(
        &glyphs,
        input["units_per_em"].as_u64().unwrap() as u16,
        input["ascender_units"].as_f64().unwrap(),
        &settings,
    )
    .unwrap();
    let mut budget = WorkBudget::default();
    for left in 97..=122 {
        for right in 97..=122 {
            let pair = prepared.pair(left, right).unwrap();
            let record = trials["pairs"][((left - 97) * 26 + right - 97) as usize]
                .as_array()
                .unwrap();
            let first = record[0].as_i64().unwrap();
            for (i, expected) in record[1..].iter().enumerate() {
                let origin = (first + i as i64) as f64 * 62.5;
                let min = origin >= pair.minimum_units;
                let cap = origin >= pair.extrema_bound_units;
                let full = min
                    && cap
                    && intrusion(
                        pair.left,
                        pair.right,
                        origin,
                        prepared.normal,
                        prepared.tolerance,
                        prepared.grid,
                        prepared.ascender,
                        false,
                        &mut budget,
                    )
                    .unwrap();
                let asc = min
                    && cap
                    && intrusion(
                        pair.left,
                        pair.right,
                        origin,
                        prepared.normal,
                        prepared.tolerance,
                        prepared.grid,
                        prepared.ascender,
                        true,
                        &mut budget,
                    )
                    .unwrap();
                let actual = u64::from(min)
                    | (u64::from(cap) << 1)
                    | (u64::from(full) << 2)
                    | (u64::from(asc) << 3);
                assert_eq!(
                    actual,
                    expected.as_u64().unwrap(),
                    "{left}/{right}/{origin}"
                );
            }
        }
    }
}

#[test]
fn python_two_decimal_rounding() {
    for (x, y) in [
        (0.15, 0.1),
        (1.15, 1.1),
        (0.25, 0.3),
        (93.65, 93.7),
        (31.25, 31.3),
        (46.25, 46.3),
        (93.75, 93.8),
        (0.05, 0.1),
        (0.35, 0.3),
    ] {
        assert_eq!(python_round_tenth(x), y);
        assert_eq!(python_round_tenth(-x), -y);
    }
}

#[test]
fn invalid_geometry_limits_and_unsupported_reference_case() {
    let point = |x, y| Point { x, y };
    let parallel = GeometryGlyph {
        codepoint: 945,
        contours: vec![vec![
            Segment::Quad([point(0., 0.), point(0., 250.), point(0., 500.)]),
            Segment::Line([point(0., 500.), point(250., 500.)]),
            Segment::Line([point(250., 500.), point(250., 0.)]),
            Segment::Line([point(250., 0.), point(0., 0.)]),
        ]],
    };
    assert!(prepare(&[parallel], 1000, 800., &Default::default())
        .err()
        .unwrap()
        .to_string()
        .contains("parallel"));
    let open = GeometryGlyph {
        codepoint: 945,
        contours: vec![vec![Segment::Line([point(0., 0.), point(10., 10.)])]],
    };
    assert!(prepare(&[open], 1000, 800., &Default::default()).is_err());
    let empty = GeometryGlyph {
        codepoint: 945,
        contours: vec![],
    };
    assert!(prepare(&[empty.clone()], 1000, 800., &Default::default())
        .unwrap()
        .pair(945, 945)
        .is_none());
    assert!(prepare(&vec![empty; 1025], 1000, 800., &Default::default()).is_err());
    let contour = vec![
        Segment::Line([point(0., 0.), point(0., 20000.)]),
        Segment::Line([point(0., 20000.), point(100., 20000.)]),
        Segment::Line([point(100., 20000.), point(100., 0.)]),
        Segment::Line([point(100., 0.), point(0., 0.)]),
    ];
    let many: Vec<_> = (0..100)
        .map(|codepoint| GeometryGlyph {
            codepoint,
            contours: vec![contour.clone()],
        })
        .collect();
    assert!(prepare(&many, 1000, 800., &Default::default())
        .err()
        .unwrap()
        .to_string()
        .contains("memory"));
    assert!(prepare(&[], 16, 800., &Default::default()).is_err());
    let mut budget = WorkBudget { visits: MAX_WORK };
    assert!(budget.charge(1).is_err());
}
