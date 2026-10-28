use super::*;
use crate::diagonal_fitting::intervals::Contact;
use geometry::{Portion, PreppedPair, Station};
use std::collections::HashSet;
use std::f64::consts::PI;

fn outline(
    oncurve: Vec<[f64; 2]>,
    offcurve: Vec<[f64; 2]>,
    contours: Vec<Vec<GeomSegment>>,
) -> SourceOutline {
    SourceOutline {
        oncurve,
        offcurve,
        contours,
    }
}

fn portion(pts: &[[f64; 2]], i0: usize, i1: usize, t0: f64, t1: f64) -> Portion {
    Portion {
        contour: 0,
        seg: 0,
        t0,
        t1,
        p0: pts[i0],
        p1: pts[i1],
        i0,
        i1,
        hidden: false,
        unknown: false,
    }
}

fn station(sa: f64, sb: f64, center: [f64; 2]) -> Station {
    Station {
        s: 0.0,
        hit: Contact {
            center,
            qa: center,
            qb: center,
            r: 1.0,
            width: 2.0,
            sa,
            sb,
        },
    }
}

fn prepped(a: Portion, b: Portion, stations: Vec<Station>, arc: f64) -> PreppedPair {
    PreppedPair {
        id: String::from("t"),
        a,
        b,
        normal: [0.0, 1.0],
        stations,
        src_widths: Vec::new(),
        fit_widths: Vec::new(),
        arc,
        span_lo: 0.0,
        span_hi: 1.0,
    }
}

fn anchor(tangent: [f64; 2], length: f64, width: f64, rel: f64) -> AnchorV {
    AnchorV {
        tangent,
        length,
        width,
        rel,
    }
}

fn support(row: &[f64]) -> Vec<usize> {
    let mut out = Vec::new();
    for k in 0..row.len() / 2 {
        if row[2 * k] != 0.0 || row[2 * k + 1] != 0.0 {
            out.push(k);
        }
    }
    out
}

fn close(actual: &[f64], expected: &[f64]) -> bool {
    actual.len() == expected.len()
        && actual
            .iter()
            .zip(expected.iter())
            .all(|(a, e)| (a - e).abs() <= 1e-12)
}

#[test]
fn shape_rows_follow_contour_order_and_quad_control_offset() {
    let on = vec![[0.0, 0.0], [2.0, 0.0], [4.0, 1.0], [6.0, 1.0]];
    let off = vec![[1.0, 1.0], [5.0, 2.0]];
    let mut base = on.clone();
    base.extend(off.iter().copied());
    let raw = outline(
        on,
        off,
        vec![
            vec![GeomSegment::Quad { c: 0, a: 0, b: 1 }],
            vec![GeomSegment::Quad { c: 1, a: 2, b: 3 }],
        ],
    );
    let involved: HashSet<usize> = [0, 1, 2, 3, 4, 5].into_iter().collect();
    let (system, plain) = shape_objective_rows(&raw, 4, &involved, &base, 16.0);
    assert_eq!(system.points, base);
    assert_eq!(plain.len(), 96);
    for (row, constant) in &plain {
        assert_eq!(row.len(), 12);
        assert_eq!(constant.to_bits(), 0.0_f64.to_bits());
        assert!(row.iter().any(|x| *x != 0.0));
    }
    let mut first: HashSet<usize> = HashSet::new();
    for (row, _) in &plain[0..48] {
        assert!(support(row).iter().all(|k| *k == 0 || *k == 1 || *k == 4));
        first.extend(support(row));
    }
    assert_eq!(first, [0, 1, 4].into_iter().collect());
    let mut second: HashSet<usize> = HashSet::new();
    for (row, _) in &plain[48..96] {
        assert!(support(row).iter().all(|k| *k == 2 || *k == 3 || *k == 5));
        second.extend(support(row));
    }
    assert_eq!(second, [2, 3, 5].into_iter().collect());
}

#[test]
fn shape_rows_keep_involved_endpoints_and_skip_uninvolved_cubic_degenerate() {
    let pts = vec![
        [0.0, 0.0],
        [3.0, 0.0],
        [5.0, 1.0],
        [8.0, 1.0],
        [9.0, 2.0],
        [9.0, 2.0],
        [0.0, 5.0],
        [2.0, 5.0],
    ];
    let off = vec![[1.0, 1.0], [2.0, 2.0]];
    let mut base = pts.clone();
    base.extend(off.iter().copied());
    let raw = outline(
        pts,
        off,
        vec![
            vec![GeomSegment::Line { a: 0, b: 1 }],
            vec![GeomSegment::Line { a: 2, b: 3 }],
            vec![GeomSegment::Line { a: 4, b: 5 }],
            vec![GeomSegment::Line { a: 6, b: 7 }],
            vec![GeomSegment::Cubic {
                c1: 0,
                c2: 1,
                a: 0,
                b: 1,
            }],
        ],
    );
    let involved: HashSet<usize> = [0, 3, 4].into_iter().collect();
    let (_, plain) = shape_objective_rows(&raw, 8, &involved, &base, 16.0);
    assert_eq!(plain.len(), 8);
    for (row, constant) in &plain {
        assert_eq!(row.len(), 20);
        assert_eq!(constant.to_bits(), 0.0_f64.to_bits());
        assert!(row.iter().any(|x| *x != 0.0));
    }
    for (row, _) in &plain[0..4] {
        assert!(support(row).iter().all(|k| *k == 0 || *k == 1));
    }
    for (row, _) in &plain[4..8] {
        assert!(support(row).iter().all(|k| *k == 2 || *k == 3));
    }
}

#[test]
fn shape_rows_skip_fully_degenerate_quad() {
    let pts = vec![[1.0, 1.0], [1.0, 1.0]];
    let off = vec![[1.0, 1.0]];
    let mut base = pts.clone();
    base.extend(off.iter().copied());
    let raw = outline(pts, off, vec![vec![GeomSegment::Quad { c: 0, a: 0, b: 1 }]]);
    let involved: HashSet<usize> = [0, 1, 2].into_iter().collect();
    let (_, plain) = shape_objective_rows(&raw, 2, &involved, &base, 16.0);
    assert!(plain.is_empty());
}

#[test]
fn width_rows_are_empty_for_empty_prepared_anchors_or_stations() {
    let pts = vec![[0.0, 0.0], [2.0, 0.0], [0.0, 2.0], [2.0, 2.0]];
    let raw = outline(
        pts.clone(),
        Vec::new(),
        vec![vec![GeomSegment::Line { a: 0, b: 1 }]],
    );
    let involved: HashSet<usize> = [0].into_iter().collect();
    let (system, _) = shape_objective_rows(&raw, 4, &involved, &pts, 16.0);
    let pair = prepped(
        portion(&pts, 0, 1, 0.0, 1.0),
        portion(&pts, 2, 3, 0.0, 1.0),
        vec![station(0.5, 0.5, [1.0, 1.0])],
        1.0,
    );
    let anchors = vec![anchor([1.0, 0.0], 1.0, 2.0, 1.0)];
    assert!(width_objective_rows(&system, &[], &anchors, 16.0).is_empty());
    assert!(width_objective_rows(&system, &[pair], &[], 16.0).is_empty());
    let bare = prepped(
        portion(&pts, 0, 1, 0.0, 1.0),
        portion(&pts, 2, 3, 0.0, 1.0),
        Vec::new(),
        1.0,
    );
    assert!(width_objective_rows(&system, &[bare], &anchors, 16.0).is_empty());
}

#[test]
fn width_rows_interpolate_affine_parameters_and_order_stations_then_anchors() {
    let pts = vec![[0.0, 0.0], [2.0, 0.0], [0.0, 2.0], [2.0, 2.0]];
    let raw = outline(
        pts.clone(),
        Vec::new(),
        vec![vec![GeomSegment::Line { a: 0, b: 1 }]],
    );
    let involved: HashSet<usize> = [0].into_iter().collect();
    let (system, _) = shape_objective_rows(&raw, 4, &involved, &pts, 16.0);
    let prepared = vec![prepped(
        portion(&pts, 0, 1, 0.25, 0.75),
        portion(&pts, 2, 3, 0.25, 0.75),
        vec![station(0.5, 0.5, [1.0, 1.0]), station(0.0, 1.0, [1.0, 1.0])],
        1.0,
    )];
    let anchors = vec![
        anchor([1.0, 0.0], 1.0, 2.0, 1.0),
        anchor([-1.0, 0.0], 1.0, 2.0, -0.5),
    ];
    let soft = width_objective_rows(&system, &prepared, &anchors, 16.0);
    assert_eq!(soft.len(), 4);
    let psi1: f64 = 500.0 / 256.0;
    let s1: f64 = psi1.sqrt();
    let dw: f64 = (5.0_f64.sqrt() - 2.0) / 0.7;
    let psi2: f64 = 500.0 / 256.0 * (-(dw * dw + (0.5_f64.atan() / 9.0).powi(2))).exp();
    let s2: f64 = psi2.sqrt();
    let e1 = vec![0.0, 0.25, 0.0, 0.25, 0.0, -0.25, 0.0, -0.25];
    let e2 = vec![0.15, 0.3, 0.05, 0.1, -0.05, -0.1, -0.15, -0.3];
    let expected = vec![
        (e1.iter().map(|x| x * s1).collect::<Vec<f64>>(), s1),
        (e1.iter().map(|x| x * s1).collect::<Vec<f64>>(), -0.5 * s1),
        (e2.iter().map(|x| x * s2).collect::<Vec<f64>>(), s2),
        (e2.iter().map(|x| x * s2).collect::<Vec<f64>>(), -0.5 * s2),
    ];
    for ((row, constant), (want_row, want_c)) in soft.iter().zip(expected.iter()) {
        assert!(close(row, want_row));
        assert!((constant - want_c).abs() <= 1e-12);
    }
}

#[test]
fn width_rows_keep_diagonal_tangent_and_drop_pair_on_late_station_failure() {
    let pts = vec![[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [4.0, 0.0]];
    let raw = outline(
        pts.clone(),
        Vec::new(),
        vec![vec![GeomSegment::Line { a: 0, b: 1 }]],
    );
    let involved: HashSet<usize> = [0].into_iter().collect();
    let (system, _) = shape_objective_rows(&raw, 4, &involved, &pts, 16.0);
    let dropped = prepped(
        portion(&pts, 0, 1, 0.0, 1.0),
        portion(&pts, 2, 3, 0.0, 1.0),
        vec![station(0.5, 0.5, [2.0, 0.5]), station(1.0, 1.0, [2.0, 0.5])],
        2.0,
    );
    let kept = prepped(
        portion(&pts, 0, 2, 0.25, 0.75),
        portion(&pts, 1, 3, 0.25, 0.75),
        vec![station(0.5, 0.5, [2.0, 0.5])],
        2.0,
    );
    let anchors = vec![
        anchor([-1.0, -2.0], 1.0, 5.0_f64.sqrt(), 2.0),
        anchor([1.0, 2.0], 0.5, 5.0_f64.sqrt(), 0.5),
        anchor([2.0, -1.0], 2.0, 5.0_f64.sqrt(), -1.0),
    ];
    assert!(width_objective_rows(&system, &[dropped], &anchors, 16.0).is_empty());
    let prepared = vec![
        prepped(
            portion(&pts, 0, 1, 0.0, 1.0),
            portion(&pts, 2, 3, 0.0, 1.0),
            vec![station(0.5, 0.5, [2.0, 0.5]), station(1.0, 1.0, [2.0, 0.5])],
            2.0,
        ),
        kept,
    ];
    let soft = width_objective_rows(&system, &prepared, &anchors, 16.0);
    assert_eq!(soft.len(), 3);
    let psi: f64 = 500.0 / 256.0;
    let s1: f64 = (2.0 * 1.0 * psi).sqrt();
    let s2: f64 = (2.0 * 0.5 * psi).sqrt();
    let psi3: f64 = 500.0 / 256.0 * (-((PI / 2.0) / 9.0).powi(2)).exp();
    let s3: f64 = (2.0 * 2.0 * psi3).sqrt();
    let e = vec![0.2, -0.1, -0.2, 0.1, 0.2, -0.1, -0.2, 0.1];
    let expected = vec![
        (e.iter().map(|x| x * s1).collect::<Vec<f64>>(), 2.0 * s1),
        (e.iter().map(|x| x * s2).collect::<Vec<f64>>(), 0.5 * s2),
        (e.iter().map(|x| x * s3).collect::<Vec<f64>>(), -s3),
    ];
    for ((row, constant), (want_row, want_c)) in soft.iter().zip(expected.iter()) {
        assert!(close(row, want_row));
        assert!((constant - want_c).abs() <= 1e-12);
    }
}
