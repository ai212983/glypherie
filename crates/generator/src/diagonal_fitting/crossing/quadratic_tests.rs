use super::*;

fn involved(ix: &[usize]) -> HashSet<usize> {
    ix.iter().copied().collect()
}

fn identity(row: &[f64]) -> Vec<f64> {
    row.to_vec()
}

#[test]
fn positive_source_curvature_uses_upstream_y_row() {
    let base = vec![[0.0, 0.0], [0.5, 0.5], [0.0, 1.0]];
    let up = vec![[0.25, 1.5], [0.75, 2.25], [0.5, 0.75]];
    let flat = ravel(&up);
    let (cmat, clower) = quadratic_constraints(
        &[[0, 1, 2]],
        &involved(&[0, 1, 2]),
        &base,
        &up,
        &flat,
        &identity,
    )
    .ok()
    .expect("positive curvature collects");
    assert_eq!(cmat.len(), 5);
    assert_eq!(clower.len(), 5);
    assert_eq!(cmat[0], vec![1.5, 0.0, -0.75, 0.0, -0.75, 0.0]);
    assert_eq!(clower[0], 0.586181640625);
    assert_eq!(cmat[1], vec![-0.5, 0.0, 0.5, 0.0, 0.0, 0.0]);
    assert_eq!(clower[1], -0.616943359375);
    assert_eq!(cmat[2], vec![0.5, 0.0, -0.5, 0.0, 0.0, 0.0]);
    assert_eq!(clower[2], -0.116943359375);
    assert_eq!(cmat[3], vec![0.0, 0.0, -0.5, 0.0, 0.5, 0.0]);
    assert_eq!(clower[3], 0.883056640625);
    assert_eq!(cmat[4], vec![0.0, 0.0, 0.5, 0.0, -0.5, 0.0]);
    assert_eq!(clower[4], 0.633056640625);
}

#[test]
fn negative_source_curvature_flips_sign_against_fitted_legs() {
    let base = vec![[0.0, 0.0], [0.5, 0.5], [1.0, 0.0]];
    let up = vec![[0.0, 1.5], [0.5, 0.5], [1.0, 1.25]];
    let fitted_cross = 0.5 * 0.75 - (-1.0) * 0.5;
    assert!(fitted_cross > 0.0);
    let flat = ravel(&up);
    let (cmat, clower) = quadratic_constraints(
        &[[0, 1, 2]],
        &involved(&[0, 1, 2]),
        &base,
        &up,
        &flat,
        &identity,
    )
    .ok()
    .expect("negative curvature collects");
    assert_eq!(cmat.len(), 5);
    assert_eq!(cmat[0], vec![0.75, 0.0, 0.25, 0.0, -1.0, 0.0]);
    assert_eq!(clower[0], 0.890869140625);
    assert_eq!(cmat[1], vec![-0.5, 0.0, 0.5, 0.0, 0.0, 0.0]);
    assert_eq!(clower[1], 0.258056640625);
}

#[test]
fn sequential_quads_emit_ordered_five_row_blocks() {
    let base = vec![
        [0.0, 0.0],
        [0.5, 0.5],
        [0.0, 1.0],
        [2.0, 0.0],
        [2.5, 0.5],
        [2.0, 1.0],
    ];
    let up = vec![
        [0.25, 1.5],
        [0.75, 2.25],
        [0.5, 0.75],
        [2.25, 1.5],
        [2.75, 2.25],
        [2.5, 0.75],
    ];
    let flat = ravel(&up);
    let all: Vec<usize> = (0..6).collect();
    let (cmat, clower) = quadratic_constraints(
        &[[0, 1, 2], [3, 4, 5]],
        &involved(&all),
        &base,
        &up,
        &flat,
        &identity,
    )
    .ok()
    .expect("two quads collect");
    assert_eq!(cmat.len(), 10);
    assert_eq!(clower.len(), 10);
    assert_eq!(
        cmat[0],
        vec![1.5, 0.0, -0.75, 0.0, -0.75, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    );
    assert_eq!(
        cmat[5],
        vec![0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.5, 0.0, -0.75, 0.0, -0.75, 0.0]
    );
    assert_eq!(clower[5], clower[0]);
    assert_eq!(
        cmat[6],
        vec![0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.5, 0.0, 0.5, 0.0, 0.0, 0.0]
    );
    assert_eq!(clower[6], -0.616943359375);
    assert_eq!(
        cmat[9],
        vec![0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.0, -0.5, 0.0]
    );
    assert_eq!(clower[9], 0.633056640625);
}

#[test]
fn uninvolved_quads_skip_before_degenerate_guard() {
    let base = vec![
        [0.0, 0.0],
        [0.5, 0.5],
        [0.0, 1.0],
        [4.0, 0.0],
        [4.5, 0.5],
        [4.0, 1.0],
        [6.0, 0.0],
        [6.5, 0.5],
        [7.0, 1.0],
    ];
    let up = vec![
        [0.25, 1.5],
        [0.75, 2.25],
        [0.5, 0.75],
        [4.25, 1.5],
        [4.75, 2.25],
        [4.5, 0.75],
        [6.0, 0.0],
        [6.5, 0.5],
        [7.0, 1.0],
    ];
    let flat = ravel(&up);
    let quads = [[0, 1, 2], [3, 4, 5], [6, 7, 8]];
    let expected_rows = vec![
        vec![
            1.5, 0.0, -0.75, 0.0, -0.75, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.0,
        ],
        vec![
            -0.5, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0,
        ],
        vec![
            0.5, 0.0, -0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0,
        ],
        vec![
            0.0, 0.0, -0.5, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0,
        ],
        vec![
            0.0, 0.0, 0.5, 0.0, -0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0,
        ],
    ];
    let expected_lower = vec![
        0.586181640625,
        -0.616943359375,
        -0.116943359375,
        0.883056640625,
        0.633056640625,
    ];
    for sole in [0usize, 1, 2] {
        let (cmat, clower) =
            quadratic_constraints(&quads, &involved(&[sole]), &base, &up, &flat, &identity)
                .ok()
                .expect("sole index selects quad");
        assert_eq!(cmat, expected_rows);
        assert_eq!(clower, expected_lower);
    }
}

#[test]
fn degenerate_curvature_aborts_after_prior_valid_quad() {
    let base = vec![
        [0.0, 0.0],
        [0.5, 0.5],
        [0.0, 1.0],
        [2.0, 0.0],
        [2.5, 0.5],
        [3.0, 1.0],
    ];
    let up = vec![
        [0.25, 1.5],
        [0.75, 2.25],
        [0.5, 0.75],
        [2.0, 0.0],
        [2.5, 0.5],
        [3.0, 1.0],
    ];
    let flat = ravel(&up);
    let all: Vec<usize> = (0..6).collect();
    assert!(matches!(
        quadratic_constraints(
            &[[0, 1, 2], [3, 4, 5]],
            &involved(&all),
            &base,
            &up,
            &flat,
            &identity
        ),
        Err(QuadraticAbort::DegenerateCurvature)
    ));
    assert!(matches!(
        quadratic_constraints(&[[3, 4, 5]], &involved(&all), &base, &up, &flat, &identity),
        Err(QuadraticAbort::DegenerateCurvature)
    ));
    let neg_zero = (-0.0f64) * 0.0 - 0.0 * 1.0;
    assert!(neg_zero == 0.0);
    assert_eq!(neg_zero.to_bits(), (-0.0f64).to_bits());
    let signed_base = vec![[0.0, 0.0], [-0.0, 0.0], [1.0, 0.0]];
    let signed_up = vec![[0.0, 0.0], [0.5, 0.0], [1.0, 0.0]];
    let signed_flat = ravel(&signed_up);
    assert!(matches!(
        quadratic_constraints(
            &[[0, 1, 2]],
            &involved(&[0, 1, 2]),
            &signed_base,
            &signed_up,
            &signed_flat,
            &identity
        ),
        Err(QuadraticAbort::DegenerateCurvature)
    ));
}

#[test]
fn reserve_follows_reduction_while_value_uses_full_upstream() {
    let base = vec![[0.0, 0.0], [0.5, 0.5], [0.0, 1.0]];
    let up = vec![[0.25, 1.5], [0.75, 2.25], [0.5, 0.75]];
    let flat = ravel(&up);
    let control_only = |row: &[f64]| vec![row[2]];
    let (cmat, clower) = quadratic_constraints(
        &[[0, 1, 2]],
        &involved(&[0, 1, 2]),
        &base,
        &up,
        &flat,
        &control_only,
    )
    .ok()
    .expect("fixed endpoints leave the control free");
    assert_eq!(cmat.len(), 5);
    assert_eq!(
        cmat,
        vec![vec![-0.75], vec![0.5], vec![-0.5], vec![-0.5], vec![0.5]]
    );
    assert_eq!(
        clower,
        vec![
            0.568603515625,
            -0.620849609375,
            -0.120849609375,
            0.879150390625,
            0.629150390625
        ]
    );
}

#[test]
fn zero_x_legs_keep_y_value_and_tiny_cross_proceeds() {
    let base = vec![
        [1.0, 0.0],
        [1.0, 0.5],
        [1.5, 0.75],
        [2.0, 0.0],
        [2.5, 0.5],
        [3.0, 1.000000001],
    ];
    let up = vec![
        [1.25, 0.75],
        [1.5, 2.25],
        [1.75, 1.5],
        [2.0, 0.0],
        [2.5, 0.5],
        [3.0, 1.0],
    ];
    let flat = ravel(&up);
    let all: Vec<usize> = (0..6).collect();
    let (cmat, clower) = quadratic_constraints(
        &[[0, 1, 2], [3, 4, 5]],
        &involved(&all),
        &base,
        &up,
        &flat,
        &identity,
    )
    .ok()
    .expect("zero-x legs and tiny cross collect");
    assert_eq!(cmat.len(), 10);
    assert_eq!(clower.len(), 10);
    assert_eq!(
        cmat[0],
        vec![-0.75, 0.0, -0.75, 0.0, 1.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    );
    assert_eq!(clower[0], -0.538818359375);
    assert_eq!(cmat[1], vec![0.0; 12]);
    assert_eq!(clower[1], -0.749755859375);
    assert_eq!(
        cmat[2],
        vec![-0.5, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    );
    assert_eq!(clower[2], -0.491943359375);
    assert_eq!(cmat[3], vec![0.0; 12]);
    assert_eq!(clower[3], 0.375244140625);
    assert_eq!(
        cmat[4],
        vec![0.0, 0.0, -0.5, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    );
    assert_eq!(clower[4], 0.070556640625);
}
