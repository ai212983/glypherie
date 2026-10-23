use super::*;

fn gate(
    j: usize,
    iv: usize,
    ov: usize,
    prev_line: bool,
    seg_line: bool,
    smooth: bool,
) -> JointGate {
    JointGate {
        j,
        iv,
        ov,
        prev_line,
        seg_line,
        smooth,
    }
}

fn identity(row: &[f64]) -> Vec<f64> {
    row.to_vec()
}

fn append(
    gates: &[JointGate],
    base: &[[f64; 2]],
    up: &[[f64; 2]],
    reduce: &impl Fn(&[f64]) -> Vec<f64>,
    seed_rows: Vec<Vec<f64>>,
    seed_bounds: Vec<f64>,
) -> (Vec<Vec<f64>>, Vec<f64>) {
    let mut cmat = seed_rows;
    let mut clower = seed_bounds;
    append_sharp_joint_constraints(gates, base, up, reduce, &mut cmat, &mut clower);
    (cmat, clower)
}

#[test]
fn smooth_gate_skips_all_rows_despite_line_flags_and_nonzero_cross() {
    let base = vec![[0.0, 0.0], [2.0, 0.5], [3.0, 2.0]];
    let up = vec![[0.0, 1.0], [2.0, 3.0], [5.0, 4.0]];
    let (s_cross, _, _) = cross_of(&base, 1, 0, 2);
    assert!(s_cross != 0.0);
    let (cmat, clower) = append(
        &[gate(1, 0, 2, true, true, true)],
        &base,
        &up,
        &identity,
        vec![vec![1.0, 0.0, 0.0, 0.0, 0.0, 0.0]],
        vec![0.5],
    );
    assert_eq!(cmat, vec![vec![1.0, 0.0, 0.0, 0.0, 0.0, 0.0]]);
    assert_eq!(clower, vec![0.5]);
}

#[test]
fn positive_source_cross_orients_row_from_base_sign_with_upstream_y() {
    let base = vec![[0.0, 0.0], [2.0, 0.5], [3.0, 2.0]];
    let up = vec![[0.0, 1.0], [2.0, 3.0], [5.0, 4.0]];
    let (s_cross, _, _) = cross_of(&base, 1, 0, 2);
    assert_eq!(s_cross, 2.5);
    let (fitted_cross, _, _) = cross_of(&up, 1, 0, 2);
    assert!(fitted_cross < 0.0);
    let (cmat, clower) = append(
        &[gate(1, 0, 2, false, false, false)],
        &base,
        &up,
        &identity,
        Vec::new(),
        Vec::new(),
    );
    assert_eq!(cmat.len(), 1);
    assert_eq!(cmat[0], vec![-1.0, 0.0, 3.0, 0.0, -2.0, 0.0]);
    assert_eq!(clower, vec![4.047119140625]);
}

#[test]
fn negative_source_cross_flips_row_against_opposite_fitted_cross() {
    let base = vec![[0.0, 0.0], [2.0, 0.5], [3.0, -1.0]];
    let up = vec![[1.0, 2.0], [3.0, 1.0], [4.0, 5.0]];
    let (s_cross, _, _) = cross_of(&base, 1, 0, 2);
    assert_eq!(s_cross, -3.5);
    let (fitted_cross, _, _) = cross_of(&up, 1, 0, 2);
    assert!(fitted_cross > 0.0);
    let (cmat, clower) = append(
        &[gate(1, 0, 2, false, false, false)],
        &base,
        &up,
        &identity,
        Vec::new(),
        Vec::new(),
    );
    assert_eq!(cmat.len(), 1);
    assert_eq!(cmat[0], vec![4.0, 0.0, -3.0, 0.0, -1.0, 0.0]);
    assert_eq!(clower, vec![9.062744140625]);
}

#[test]
fn zero_source_cross_skips_orientation_but_keeps_both_line_legs() {
    let base = vec![[0.0, 0.0], [2.0, 1.0], [1.0, 0.5]];
    let up = vec![[0.5, 1.0], [2.5, 3.0], [1.0, 5.0]];
    let (s_cross, _, _) = cross_of(&base, 1, 0, 2);
    assert_eq!(s_cross, 0.0);
    let (cmat, clower) = append(
        &[gate(1, 0, 2, true, true, false)],
        &base,
        &up,
        &identity,
        Vec::new(),
        Vec::new(),
    );
    assert_eq!(cmat.len(), 2);
    assert_eq!(cmat[0], vec![-2.0, 0.0, 2.0, 0.0, 0.0, 0.0]);
    assert_eq!(cmat[1], vec![0.0, 0.0, 1.0, 0.0, -1.0, 0.0]);
    assert_eq!(clower, vec![-5.968505859375, -0.484130859375]);
}

#[test]
fn gate_order_and_prefix_rows_preserved_with_orientation_prev_seg_sequence() {
    let base = vec![[0.0, 0.0], [1.0, 0.5], [2.0, 0.0], [2.5, -0.25]];
    let up = vec![[0.5, 0.0], [1.0, 2.0], [1.5, 1.0], [3.0, 4.0]];
    let (cross_b, _, _) = cross_of(&base, 2, 1, 3);
    assert_eq!(cross_b, 0.0);
    let (cmat, clower) = append(
        &[
            gate(1, 0, 2, true, false, false),
            gate(2, 1, 3, false, true, false),
        ],
        &base,
        &up,
        &identity,
        vec![vec![0.25, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]],
        vec![1.5],
    );
    assert_eq!(cmat.len(), 4);
    assert_eq!(cmat[0], vec![0.25, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]);
    assert_eq!(cmat[1], vec![-1.0, 0.0, -1.0, 0.0, 2.0, 0.0, 0.0, 0.0]);
    assert_eq!(cmat[2], vec![-1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]);
    assert_eq!(cmat[3], vec![0.0, 0.0, 0.0, 0.0, -0.5, 0.0, 0.5, 0.0]);
    assert_eq!(
        clower,
        vec![1.5, -1.468505859375, -1.484130859375, 0.008056640625]
    );
}

#[test]
fn weld_fold_and_free_x_pins_shape_reserve_with_zero_x_leg_value_from_y() {
    let base = vec![[0.0, 0.0], [4.0, 1.0], [0.0, 0.0]];
    let up = vec![[1.0, 3.0], [5.0, 2.0], [1.0, 3.0]];
    let fold = |row: &[f64]| -> Vec<f64> {
        let mut full = row.to_vec();
        full[0] += full[4];
        vec![full[0], full[2]]
    };
    let (cmat, clower) = append(
        &[gate(1, 0, 2, true, true, false)],
        &base,
        &up,
        &fold,
        Vec::new(),
        Vec::new(),
    );
    assert_eq!(cmat.len(), 2);
    assert_eq!(cmat[0], vec![-4.0, 4.0]);
    assert_eq!(cmat[1], vec![-4.0, 4.0]);
    assert_eq!(clower, vec![-14.937255859375, -14.937255859375]);
    let control_only = |row: &[f64]| vec![fold(row)[1]];
    let (pinned_rows, pinned_bounds) = append(
        &[gate(1, 0, 2, true, true, false)],
        &base,
        &up,
        &control_only,
        Vec::new(),
        Vec::new(),
    );
    assert_eq!(pinned_rows, vec![vec![4.0], vec![4.0]]);
    assert_eq!(pinned_bounds, vec![-14.968505859375, -14.968505859375]);

    let vbase = vec![[3.0, 0.0], [3.0, 2.0], [3.0, 5.0]];
    let vup = vec![[3.5, 1.0], [2.5, 4.0], [3.0, 0.5]];
    let (v_cross, _, _) = cross_of(&vbase, 1, 0, 2);
    assert_eq!(v_cross, 0.0);
    let (vcmat, vclower) = append(
        &[gate(1, 0, 2, true, false, false)],
        &vbase,
        &vup,
        &identity,
        Vec::new(),
        Vec::new(),
    );
    assert_eq!(vcmat.len(), 1);
    assert_eq!(vcmat[0], vec![0.0, 0.0, 0.0, 0.0, 0.0, 0.0]);
    assert_eq!(vcmat[0][0].to_bits(), (-0.0_f64).to_bits());
    assert_eq!(vclower, vec![-5.999755859375]);
}
