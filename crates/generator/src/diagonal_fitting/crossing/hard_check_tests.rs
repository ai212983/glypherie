use super::*;

fn flag(checks: &[serde_json::Value], index: usize) -> bool {
    checks[index]["ok"].as_bool().expect("ok diagnostic")
}

fn allowance_of(checks: &[serde_json::Value], index: usize) -> f64 {
    checks[index]["allowance"]
        .as_f64()
        .expect("allowance diagnostic")
}

#[test]
fn raw_and_rounded_gates_both_required() {
    let cols = vec![0usize];
    let up = vec![[4.0, 7.0]];
    let bad_raw = vec![[4.5, 7.0]];
    let at_up = vec![[4.0, 7.0]];
    let (ok, checks) = rounded_hard_checks(&cols, &[(vec![1.0], 0.0)], &bad_raw, &at_up, &up);
    assert!(!ok);
    assert_eq!(checks.len(), 1);
    assert!(!flag(&checks, 0));
    assert!((checks[0]["raw_error"].as_f64().expect("raw_error") - 0.5).abs() <= 1e-15);
    let moved_raw = vec![[4.004, 7.0]];
    let far_cand = vec![[4.02, 7.0]];
    let (ok, checks) =
        rounded_hard_checks(&cols, &[(vec![1.0], 0.004)], &moved_raw, &far_cand, &up);
    assert!(!ok);
    assert_eq!(checks.len(), 1);
    assert!(!flag(&checks, 0));
    assert!(checks[0]["raw_error"].as_f64().expect("raw_error") <= 2e-7);
}

#[test]
fn moved_x_allowance_permits_quantum_unchanged_gets_none() {
    let cols = vec![0usize];
    let up = vec![[8.0, 3.0]];
    let moved = vec![[8.004, 3.0]];
    let (ok, checks) = rounded_hard_checks(&cols, &[(vec![1.0], 0.004)], &moved, &moved, &up);
    assert!(ok);
    assert_eq!(checks.len(), 1);
    assert!(flag(&checks, 0));
    assert!((allowance_of(&checks, 0) - 1.0 / 128.0).abs() <= 1e-18);
    let still = vec![[8.0, 3.0]];
    let drifted = vec![[8.004, 3.0]];
    let (ok, checks) = rounded_hard_checks(&cols, &[(vec![1.0], 0.0)], &still, &drifted, &up);
    assert!(!ok);
    assert_eq!(allowance_of(&checks, 0), 0.0);
    assert!(!flag(&checks, 0));
}

#[test]
fn y_movement_does_not_inflate_allowance() {
    let cols = vec![0usize];
    let up = vec![[8.0, 3.0]];
    let y_only = vec![[8.0, 9.5]];
    let cand = vec![[8.004, 9.5]];
    let (ok, checks) = rounded_hard_checks(&cols, &[(vec![1.0], 0.0)], &y_only, &cand, &up);
    assert!(!ok);
    assert_eq!(allowance_of(&checks, 0), 0.0);
    assert!(!flag(&checks, 0));
    assert_eq!(checks[0]["raw_error"].as_f64().expect("raw_error"), 0.0);
}

#[test]
fn projection_follows_cols_order_ignoring_y() {
    let cols = vec![2usize, 0usize];
    let up = vec![[1.0, 2.0], [5.0, 6.0], [9.0, 1.0]];
    let shifted = vec![[1.5, 200.0], [5.0, -300.0], [9.25, 400.0]];
    let (ok, checks) =
        rounded_hard_checks(&cols, &[(vec![4.0, 1.0], 1.5)], &shifted, &shifted, &up);
    assert!(ok);
    assert!(flag(&checks, 0));
    assert!((allowance_of(&checks, 0) - 5.0 / 128.0).abs() <= 1e-18);
    let (ok, _) = rounded_hard_checks(&cols, &[(vec![4.0, 1.0], 2.25)], &shifted, &shifted, &up);
    assert!(!ok);
}

#[test]
fn signed_nonunit_row_scales_allowance() {
    let cols = vec![0usize, 1usize];
    let up = vec![[2.0, 2.0], [6.0, 8.0]];
    let moved = vec![[2.004, 2.0], [6.0, 8.0]];
    let (ok, checks) =
        rounded_hard_checks(&cols, &[(vec![-3.0, 0.5], -0.012)], &moved, &moved, &up);
    assert!(ok);
    assert!(flag(&checks, 0));
    assert!((allowance_of(&checks, 0) - 3.0 / 128.0).abs() <= 1e-18);
}

#[test]
fn inclusive_boundary_passes_just_beyond_fails() {
    let cols = vec![0usize];
    let up = vec![[10.0, 5.0]];
    let raw = vec![[11.0, 5.0]];
    let quantum = 1.0 / 128.0;
    let at_quantum = vec![[11.0 + quantum, 5.0]];
    let (ok, checks) = rounded_hard_checks(&cols, &[(vec![1.0], 1.0)], &raw, &at_quantum, &up);
    assert!(ok);
    assert!(flag(&checks, 0));
    let inside = vec![[11.0 + quantum + 0.5e-9, 5.0]];
    let (ok, _) = rounded_hard_checks(&cols, &[(vec![1.0], 1.0)], &raw, &inside, &up);
    assert!(ok);
    let outside = vec![[11.0 + quantum + 2e-9, 5.0]];
    let (ok, checks) = rounded_hard_checks(&cols, &[(vec![1.0], 1.0)], &raw, &outside, &up);
    assert!(!ok);
    assert!(!flag(&checks, 0));
}

#[test]
fn first_failure_stops_with_prefix() {
    let cols = vec![0usize];
    let same = vec![[3.0, 3.0]];
    let rows = vec![(vec![1.0], 0.0), (vec![1.0], 5.0), (vec![1.0], 0.0)];
    let (ok, checks) = rounded_hard_checks(&cols, &rows, &same, &same, &same);
    assert!(!ok);
    assert_eq!(checks.len(), 2);
    assert!(flag(&checks, 0));
    assert!(!flag(&checks, 1));
    assert_eq!(checks[0]["raw_error"].as_f64().expect("raw_error"), 0.0);
    assert_eq!(checks[1]["raw_error"].as_f64().expect("raw_error"), 5.0);
}

#[test]
fn empty_rows_pass_with_no_checks() {
    let cols = vec![0usize];
    let pts = vec![[1.0, 2.0]];
    let (ok, checks) = rounded_hard_checks(&cols, &[], &pts, &pts, &pts);
    assert!(ok);
    assert!(checks.is_empty());
}

#[test]
fn raw_error_at_inclusive_tolerance_passes() {
    let up = [[0.0, 0.0]];
    let raw = [[2e-7, 0.0]];
    let (ok, checks) = rounded_hard_checks(&[0], &[(vec![1.0], 0.0)], &raw, &up, &up);
    assert!(ok);
    assert_eq!(checks[0]["raw_error"].as_f64(), Some(2e-7));
    let beyond = [[f64::from_bits((2e-7_f64).to_bits() + 1), 0.0]];
    let (ok, _) = rounded_hard_checks(&[0], &[(vec![1.0], 0.0)], &beyond, &up, &up);
    assert!(!ok);
}

#[test]
fn nonunit_norm_and_rounded_error_tolerances_are_inclusive() {
    let up = [[0.0, 0.0]];
    let raw = [[1.5e-7, 0.0]];
    let (ok, checks) = rounded_hard_checks(&[0], &[(vec![2.0], 0.0)], &raw, &up, &up);
    assert!(ok);
    assert_eq!(checks[0]["raw_error"].as_f64(), Some(3e-7));
    let raw = [[2e-7, 0.0]];
    let cand = [[0.007812501, 0.0]];
    let (ok, checks) = rounded_hard_checks(&[0], &[(vec![1.0], 0.0)], &raw, &cand, &up);
    assert!(ok);
    assert_eq!(checks[0]["rounded_error"].as_f64(), Some(0.007812501));
    let beyond = [[f64::from_bits((0.007812501_f64).to_bits() + 1), 0.0]];
    let (ok, _) = rounded_hard_checks(&[0], &[(vec![1.0], 0.0)], &raw, &beyond, &up);
    assert!(!ok);
}

#[test]
fn nonzero_target_scales_raw_error_tolerance() {
    let up = [[0.0, 0.0]];
    let raw = [[1.0000003, 0.0]];
    let cand = [[1.0, 0.0]];
    let (ok, checks) = rounded_hard_checks(&[0], &[(vec![1.0], 1.0)], &raw, &cand, &up);
    assert!(ok);
    let error = checks[0]["raw_error"].as_f64().expect("raw error");
    assert!(error > 2e-7 && error < 4e-7);
    assert_eq!(checks[0]["rounded_error"].as_f64(), Some(0.0));
}
