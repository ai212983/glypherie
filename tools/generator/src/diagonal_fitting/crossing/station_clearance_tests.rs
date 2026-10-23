use super::super::intervals::Contact;
use super::*;

fn portion(i0: usize, i1: usize, t0: f64, t1: f64) -> geometry::Portion {
    geometry::Portion {
        contour: 0,
        seg: 0,
        t0,
        t1,
        p0: [0.0, 0.0],
        p1: [0.0, 0.0],
        i0,
        i1,
        hidden: false,
        unknown: false,
    }
}

fn contact(sa: f64, sb: f64) -> geometry::Station {
    geometry::Station {
        s: 0.0,
        hit: Contact {
            center: [0.0, 0.0],
            qa: [0.0, 0.0],
            qb: [0.0, 0.0],
            r: 0.0,
            width: 0.0,
            sa,
            sb,
        },
    }
}

fn pair(
    a: geometry::Portion,
    b: geometry::Portion,
    stations: Vec<geometry::Station>,
) -> geometry::PreppedPair {
    geometry::PreppedPair {
        id: String::from("t"),
        a,
        b,
        normal: [0.0, 1.0],
        stations,
        src_widths: Vec::new(),
        fit_widths: Vec::new(),
        arc: 0.0,
        span_lo: 0.0,
        span_hi: 0.0,
    }
}

fn rect_pair(stations: Vec<geometry::Station>) -> geometry::PreppedPair {
    pair(portion(0, 1, 0.0, 1.0), portion(2, 3, 0.0, 1.0), stations)
}

fn rect_on() -> Vec<[f64; 2]> {
    vec![[0.0, 0.0], [4.0, 0.0], [0.0, 10.0], [4.0, 10.0]]
}

#[test]
fn clear_disk_passes_curve_and_line() {
    let prepared = vec![rect_pair(vec![contact(0.5, 0.5)])];
    let fixed_curves = vec![vec![[100.0, 100.0], [101.0, 102.0], [102.0, 100.0]]];
    let fixed_lines: Vec<ClearanceLine> = vec![([100.0, 0.0], [100.0, 10.0])];
    assert!(station_clearance(&prepared, &rect_on(), &fixed_curves, &fixed_lines).is_ok());
}

#[test]
fn curve_through_center_fails() {
    let prepared = vec![rect_pair(vec![contact(0.5, 0.5)])];
    let fixed_curves = vec![vec![[-10.0, 5.0], [2.0, 5.0], [14.0, 5.0]]];
    assert_eq!(
        station_clearance(&prepared, &rect_on(), &fixed_curves, &[]),
        Err("clearance-station-disk-curve")
    );
}

#[test]
fn line_through_center_fails() {
    let prepared = vec![rect_pair(vec![contact(0.5, 0.5)])];
    let fixed_lines: Vec<ClearanceLine> = vec![([2.0, -10.0], [2.0, 20.0])];
    assert_eq!(
        station_clearance(&prepared, &rect_on(), &[], &fixed_lines),
        Err("clearance-station-disk-line")
    );
}

#[test]
fn tangency_line_passes_curve_fails() {
    let prepared = vec![rect_pair(vec![contact(0.5, 0.5)])];
    let tangent_line: Vec<ClearanceLine> = vec![([-10.0, 10.0], [14.0, 10.0])];
    assert!(station_clearance(&prepared, &rect_on(), &[], &tangent_line).is_ok());
    let tangent_curve = vec![vec![[-10.0, 10.0], [2.0, 10.0], [14.0, 10.0]]];
    assert_eq!(
        station_clearance(&prepared, &rect_on(), &tangent_curve, &[]),
        Err("clearance-station-disk-curve")
    );
}

#[test]
fn curve_failure_precedes_line_within_station() {
    let prepared = vec![rect_pair(vec![contact(0.5, 0.5)])];
    let fixed_curves = vec![vec![[-10.0, 5.0], [2.0, 5.0], [14.0, 5.0]]];
    let fixed_lines: Vec<ClearanceLine> = vec![([2.0, -10.0], [2.0, 20.0])];
    assert_eq!(
        station_clearance(&prepared, &rect_on(), &fixed_curves, &fixed_lines),
        Err("clearance-station-disk-curve")
    );
}

#[test]
fn earlier_station_line_fail_precedes_later_curve_fail() {
    let cand_on = vec![
        [0.0, 0.0],
        [4.0, 0.0],
        [0.0, 10.0],
        [4.0, 10.0],
        [50.0, 50.0],
        [54.0, 50.0],
        [50.0, 60.0],
        [54.0, 60.0],
    ];
    let first = rect_pair(vec![contact(0.0, 0.0), contact(1.0, 1.0)]);
    let second = pair(
        portion(4, 5, 0.0, 1.0),
        portion(6, 7, 0.0, 1.0),
        vec![contact(0.5, 0.5)],
    );
    let fixed_curves = vec![vec![[40.0, 55.0], [52.0, 55.0], [64.0, 55.0]]];
    let fixed_lines: Vec<ClearanceLine> = vec![([6.0, 4.0], [6.0, 6.0])];
    assert_eq!(
        station_clearance(&[first, second], &cand_on, &fixed_curves, &fixed_lines),
        Err("clearance-station-disk-line")
    );
}

#[test]
fn empty_pairs_and_stations_pass() {
    let cand_on = rect_on();
    assert!(station_clearance(&[], &cand_on, &[], &[]).is_ok());
    let prepared = vec![rect_pair(Vec::new())];
    let fixed_curves = vec![vec![[2.0, 5.0], [2.0, 5.0], [2.0, 5.0]]];
    let fixed_lines: Vec<ClearanceLine> = vec![([2.0, -10.0], [2.0, 20.0])];
    assert!(station_clearance(&prepared, &cand_on, &fixed_curves, &fixed_lines).is_ok());
}

#[test]
fn subrange_portion_fractions_map() {
    let cand_on = vec![[0.0, 0.0], [8.0, 0.0], [0.0, 10.0], [8.0, 10.0]];
    let fixed_curves = vec![vec![[100.0, 100.0], [101.0, 102.0], [102.0, 100.0]]];
    let first = vec![pair(
        portion(0, 1, 0.25, 0.75),
        portion(2, 3, 0.0, 1.0),
        vec![contact(0.0, 0.5)],
    )];
    let left: Vec<ClearanceLine> = vec![([-3.0, 4.0], [-3.0, 6.0])];
    assert!(station_clearance(&first, &cand_on, &fixed_curves, &left).is_ok());
    let second = vec![pair(
        portion(0, 1, 0.25, 0.75),
        portion(2, 3, 0.0, 1.0),
        vec![contact(1.0, 0.5)],
    )];
    let right: Vec<ClearanceLine> = vec![([11.0, 4.0], [11.0, 6.0])];
    assert!(station_clearance(&second, &cand_on, &fixed_curves, &right).is_ok());
}

#[test]
fn kernel_interior_projection_axis_and_diagonal() {
    assert!(seg_open_clear([5.0, 3.0], 3.0, ([0.0, 0.0], [10.0, 0.0])));
    assert!(!seg_open_clear([5.0, 3.0], 4.0, ([0.0, 0.0], [10.0, 0.0])));
    assert!(seg_open_clear([-1.0, 7.0], 5.0, ([0.0, 0.0], [6.0, 8.0])));
    assert!(!seg_open_clear([-1.0, 7.0], 6.0, ([0.0, 0.0], [6.0, 8.0])));
}

#[test]
fn kernel_clamps_both_ends_including_reverse() {
    assert!(seg_open_clear([6.0, 0.0], 2.0, ([0.0, 0.0], [4.0, 0.0])));
    assert!(!seg_open_clear([6.0, 0.0], 3.0, ([0.0, 0.0], [4.0, 0.0])));
    assert!(seg_open_clear([-3.0, 4.0], 5.0, ([0.0, 0.0], [4.0, 0.0])));
    assert!(!seg_open_clear([-3.0, 4.0], 6.0, ([0.0, 0.0], [4.0, 0.0])));
    assert!(seg_open_clear([6.0, 0.0], 2.0, ([4.0, 0.0], [0.0, 0.0])));
    assert!(!seg_open_clear([-3.0, 4.0], 6.0, ([4.0, 0.0], [0.0, 0.0])));
}

#[test]
fn kernel_degenerate_point_three_four_five() {
    assert!(seg_open_clear([4.0, 5.0], 5.0, ([1.0, 1.0], [1.0, 1.0])));
    assert!(!seg_open_clear([4.0, 5.0], 6.0, ([1.0, 1.0], [1.0, 1.0])));
    assert!(seg_open_clear([4.0, 5.0], 4.0, ([1.0, 1.0], [1.0, 1.0])));
}

#[test]
fn kernel_degenerate_point_translated_three_four_five() {
    let point = ([1.0, -2.0], [1.0, -2.0]);
    assert!(seg_open_clear([4.0, 2.0], 5.0, point));
    assert!(!seg_open_clear(
        [4.0, 2.0],
        f64::from_bits(5f64.to_bits() + 1),
        point
    ));
    assert!(seg_open_clear([4.0, 2.0], 4.0, point));
    assert!(!seg_open_clear([4.0, 2.0], 6.0, point));
}

#[test]
fn kernel_zero_negative_nonfinite_radius() {
    assert!(seg_open_clear([5.0, 0.0], 0.0, ([0.0, 0.0], [10.0, 0.0])));
    assert!(seg_open_clear([5.0, 3.0], 0.0, ([0.0, 0.0], [10.0, 0.0])));
    assert!(!seg_open_clear([5.0, 3.0], -1.0, ([0.0, 0.0], [10.0, 0.0])));
    assert!(!seg_open_clear(
        [5.0, 3.0],
        f64::NAN,
        ([0.0, 0.0], [10.0, 0.0])
    ));
    assert!(!seg_open_clear(
        [5.0, 3.0],
        f64::INFINITY,
        ([0.0, 0.0], [10.0, 0.0])
    ));
}

#[test]
fn kernel_invalid_inputs_fail_independently() {
    let seg = ([0.0, 0.0], [10.0, 0.0]);
    assert!(!seg_open_clear([f64::NAN, 0.0], 1.0, seg));
    assert!(!seg_open_clear([0.0, f64::INFINITY], 1.0, seg));
    assert!(!seg_open_clear(
        [5.0, 3.0],
        1.0,
        ([f64::NAN, 0.0], [10.0, 0.0])
    ));
    assert!(!seg_open_clear(
        [5.0, 3.0],
        1.0,
        ([0.0, 0.0], [10.0, f64::NAN])
    ));
    assert!(seg_open_clear([5.0, 3.0], 1.0, seg));
}

#[test]
fn kernel_translation_invariance() {
    assert!(seg_open_clear(
        [999.0, -693.0],
        5.0,
        ([1000.0, -700.0], [1006.0, -692.0])
    ));
    assert!(!seg_open_clear(
        [999.0, -693.0],
        6.0,
        ([1000.0, -700.0], [1006.0, -692.0])
    ));
}
