use super::*;

fn gate(j: usize, iv: usize, ov: usize, smooth: bool) -> JointGate {
    JointGate {
        j,
        iv,
        ov,
        prev_line: false,
        seg_line: false,
        smooth,
    }
}

fn flag(checks: &[serde_json::Value], index: usize) -> bool {
    checks[index]["ok"].as_bool().expect("ok diagnostic")
}

#[test]
fn smooth_unmoved_passes_with_zero_allowance() {
    let gates = vec![gate(1, 0, 2, true)];
    let up = vec![[0.0, 0.0], [4.0, 2.0], [10.0, 5.0]];
    let base = vec![[100.0, 50.0], [104.0, 52.0], [110.0, 55.0]];
    let (ok, checks) = rounded_joint_checks(&gates, &up, &up, &up, &base);
    assert!(ok);
    assert_eq!(checks.len(), 1);
    assert!(flag(&checks, 0));
    assert_eq!(checks[0]["allowed"].as_f64().expect("allowed"), 0.0);
    assert_eq!(checks[0]["joint"].as_u64().expect("joint"), 1);
}

#[test]
fn smooth_raw_gate_failure_despite_perfect_rounded() {
    let gates = vec![gate(1, 0, 2, true)];
    let up = vec![[0.0, 0.0], [4.0, 0.0], [9.0, 0.0]];
    let raw = vec![[0.0, 0.0], [4.0, 0.01], [9.0, 0.0]];
    let base = vec![[0.0, 7.0], [4.0, 7.0], [9.0, 7.0]];
    let (ok, checks) = rounded_joint_checks(&gates, &raw, &up, &up, &base);
    assert!(!ok);
    assert_eq!(checks.len(), 1);
    assert!(!flag(&checks, 0));
    assert_eq!(checks[0]["cross_cand"].as_f64().expect("cross_cand"), 0.0);
}

#[test]
fn smooth_rounded_allowance_boundary_inside_passes_outside_fails() {
    let gates = vec![gate(1, 0, 2, true)];
    let up = vec![[0.0, 0.0], [4.0, 2.0], [10.0, 5.0]];
    let raw = vec![[0.0, 0.0], [4.008, 2.004], [10.0, 5.0]];
    let base = vec![[100.0, 50.0], [104.0, 52.0], [110.0, 55.0]];
    let quantum = 1.0 / 128.0;
    let inside = vec![[0.0, 0.0], [4.008 + quantum, 2.004], [10.0, 5.0]];
    let (ok, checks) = rounded_joint_checks(&gates, &raw, &inside, &up, &base);
    assert!(ok);
    assert!(flag(&checks, 0));
    assert!((checks[0]["allowed"].as_f64().expect("allowed") - 5.0 / 128.0).abs() <= 1e-18);
    let outside = vec![[0.0, 0.0], [4.008 + quantum + 1e-9, 2.004], [10.0, 5.0]];
    let (ok, checks) = rounded_joint_checks(&gates, &raw, &outside, &up, &base);
    assert!(!ok);
    assert!(!flag(&checks, 0));
}

#[test]
fn sharp_positive_source_with_divergent_upstream() {
    let gates = vec![gate(1, 0, 2, false)];
    let base = vec![[0.0, 0.0], [4.0, 0.0], [4.0, 4.0]];
    let up = vec![[10.0, 10.0], [14.0, 10.0], [14.0, 6.0]];
    let with_source = vec![[10.0, 10.0], [14.0, 10.0], [14.0, 14.0]];
    let (ok, checks) = rounded_joint_checks(&gates, &up, &with_source, &up, &base);
    assert!(ok);
    assert!(flag(&checks, 0));
    assert_eq!(checks[0]["cross_src"].as_f64().expect("cross_src"), 16.0);
    assert_eq!(checks[0]["cross_up"].as_f64().expect("cross_up"), -16.0);
    let (ok, checks) = rounded_joint_checks(&gates, &up, &up, &up, &base);
    assert!(!ok);
    assert!(!flag(&checks, 0));
}

#[test]
fn sharp_negative_source_with_divergent_upstream() {
    let gates = vec![gate(1, 0, 2, false)];
    let base = vec![[0.0, 0.0], [4.0, 0.0], [4.0, -4.0]];
    let up = vec![[10.0, 10.0], [14.0, 10.0], [14.0, 14.0]];
    let with_source = vec![[10.0, 10.0], [14.0, 10.0], [14.0, 6.0]];
    let (ok, checks) = rounded_joint_checks(&gates, &up, &with_source, &up, &base);
    assert!(ok);
    assert!(flag(&checks, 0));
    assert_eq!(checks[0]["cross_src"].as_f64().expect("cross_src"), -16.0);
    assert_eq!(checks[0]["cross_up"].as_f64().expect("cross_up"), 16.0);
}

#[test]
fn smooth_opposite_tangents_fail_despite_zero_cross() {
    let gates = vec![gate(1, 0, 2, true)];
    let up = vec![[0.0, 0.0], [4.0, 0.0], [9.0, 0.0]];
    let folded = vec![[0.0, 0.0], [4.0, 0.0], [2.0, 0.0]];
    let base = vec![[0.0, 7.0], [4.0, 7.0], [9.0, 7.0]];
    let (ok, checks) = rounded_joint_checks(&gates, &up, &folded, &up, &base);
    assert!(!ok);
    assert!(!flag(&checks, 0));
    assert_eq!(checks[0]["cross_cand"].as_f64().expect("cross_cand"), 0.0);
}

#[test]
fn degenerate_candidate_legs_fail() {
    let gates = vec![gate(1, 0, 2, true)];
    let up = vec![[0.0, 0.0], [4.0, 0.0], [9.0, 0.0]];
    let base = vec![[0.0, 7.0], [4.0, 7.0], [9.0, 7.0]];
    let collapsed_in = vec![[0.0, 0.0], [0.0, 0.0], [9.0, 0.0]];
    let (ok, checks) = rounded_joint_checks(&gates, &up, &collapsed_in, &up, &base);
    assert!(!ok);
    assert!(!flag(&checks, 0));
    let collapsed_out = vec![[0.0, 0.0], [4.0, 0.0], [4.0, 0.0]];
    let (ok, checks) = rounded_joint_checks(&gates, &up, &collapsed_out, &up, &base);
    assert!(!ok);
    assert!(!flag(&checks, 0));
}

#[test]
fn zero_source_sharp_fails_despite_matching_candidate() {
    let gates = vec![gate(1, 0, 2, false)];
    let base = vec![[0.0, 0.0], [4.0, 0.0], [9.0, 0.0]];
    let up = vec![[10.0, 10.0], [14.0, 10.0], [19.0, 10.0]];
    let (ok, checks) = rounded_joint_checks(&gates, &up, &up, &up, &base);
    assert!(!ok);
    assert_eq!(checks.len(), 1);
    assert!(!flag(&checks, 0));
    assert_eq!(checks[0]["cross_src"].as_f64().expect("cross_src"), 0.0);
}

#[test]
fn first_failure_prefix_and_empty() {
    let base = vec![
        [0.0, 0.0],
        [4.0, 0.0],
        [9.0, 0.0],
        [30.0, 30.0],
        [34.0, 30.0],
        [34.0, 34.0],
        [50.0, 50.0],
        [54.0, 50.0],
        [59.0, 50.0],
    ];
    let up = vec![
        [1.0, 5.0],
        [5.0, 5.0],
        [10.0, 5.0],
        [40.0, 40.0],
        [44.0, 40.0],
        [44.0, 36.0],
        [51.0, 55.0],
        [55.0, 55.0],
        [60.0, 55.0],
    ];
    let gates = vec![
        gate(1, 0, 2, true),
        gate(4, 3, 5, false),
        gate(7, 6, 8, true),
    ];
    let (ok, checks) = rounded_joint_checks(&gates, &up, &up, &up, &base);
    assert!(!ok);
    assert_eq!(checks.len(), 2);
    assert!(flag(&checks, 0));
    assert!(!flag(&checks, 1));
    assert_eq!(checks[1]["joint"].as_u64().expect("joint"), 4);
    let (ok, checks) = rounded_joint_checks(&[], &up, &up, &up, &base);
    assert!(ok);
    assert!(checks.is_empty());
}

#[test]
fn smooth_raw_tolerance_is_inclusive() {
    let up = [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]];
    let raw = [[0.0, 0.0], [1.0, 0.0], [2.0, 1e-8]];
    let gates = [gate(1, 0, 2, true)];
    let (ok, _) = rounded_joint_checks(&gates, &raw, &up, &up, &up);
    assert!(ok);
    let beyond = [
        [0.0, 0.0],
        [1.0, 0.0],
        [2.0, f64::from_bits((1e-8_f64).to_bits() + 1)],
    ];
    let (ok, _) = rounded_joint_checks(&gates, &beyond, &up, &up, &up);
    assert!(!ok);
}

#[test]
fn smooth_rounded_tolerance_is_inclusive_without_allowance() {
    let up = [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]];
    let cand = [[0.0, 0.0], [1.0, 0.0], [2.0, 1e-9]];
    let gates = [gate(1, 0, 2, true)];
    let (ok, checks) = rounded_joint_checks(&gates, &up, &cand, &up, &up);
    assert!(ok);
    assert_eq!(checks[0]["allowed"].as_f64(), Some(0.0));
    let beyond = [
        [0.0, 0.0],
        [1.0, 0.0],
        [2.0, f64::from_bits((1e-9_f64).to_bits() + 1)],
    ];
    let (ok, _) = rounded_joint_checks(&gates, &up, &beyond, &up, &up);
    assert!(!ok);
}

#[test]
fn movement_detection_compares_full_points_with_x_only_perturbation_flags() {
    let up = [[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]];
    let raw = [[0.0, 0.0], [1.0, 1.0000000001], [2.0, 2.0]];
    let (ok, checks) = rounded_joint_checks(&[gate(1, 0, 2, true)], &raw, &up, &up, &up);
    assert!(ok);
    assert_eq!(checks[0]["allowed"].as_f64(), Some(0.015625));
}

#[test]
fn sharp_source_rejects_collinear_candidate_with_nondegenerate_legs() {
    let base = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]];
    let cand = [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]];
    let (ok, checks) = rounded_joint_checks(&[gate(1, 0, 2, false)], &cand, &cand, &cand, &base);
    assert!(!ok);
    assert_eq!(checks[0]["cross_cand"].as_f64(), Some(0.0));
    assert_eq!(checks[0]["cross_src"].as_f64(), Some(1.0));
}

#[test]
fn rounding_to_perpendicular_legs_requires_strictly_positive_forward_dot() {
    let up = [[0.0, 0.0], [0.0, 0.015625], [0.0, 0.03125]];
    let raw = [
        [0.00781249, 0.0],
        [0.00781251, 0.015625],
        [0.00781249, 0.03125],
    ];
    let cand = raw.map(|p| [round_26_6(p[0]), p[1]]);
    assert_eq!(cand, [[0.0, 0.0], [0.015625, 0.015625], [0.0, 0.03125]]);
    let (ok, checks) = rounded_joint_checks(&[gate(1, 0, 2, true)], &raw, &cand, &up, &up);
    assert!(!ok);
    assert_eq!(checks[0]["cross_cand"].as_f64(), Some(0.00048828125));
    assert_eq!(checks[0]["allowed"].as_f64(), Some(0.00048828125));
}

#[test]
fn underflowed_signed_cross_product_remains_rejected() {
    let scale = f64::from_bits(486_u64 << 52);
    let base = [[0.0, 0.0], [scale, 0.0], [scale, scale]];
    let cand = [[0.0, 0.0], [0.015625, 0.0], [0.015625, 0.015625]];
    let (ok, checks) = rounded_joint_checks(&[gate(1, 0, 2, false)], &cand, &cand, &cand, &base);
    assert!(!ok);
    assert_eq!(checks[0]["cross_src"].as_f64(), Some(f64::from_bits(1)));
    assert_eq!(checks[0]["cross_cand"].as_f64(), Some(0.000244140625));
}
