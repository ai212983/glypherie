use super::*;

fn outline(
    oncurve: Vec<[f64; 2]>,
    contours: Vec<Vec<GeomSegment>>,
) -> (SourceOutline, Vec<[f64; 2]>) {
    let raw = SourceOutline {
        oncurve,
        offcurve: Vec::new(),
        contours,
    };
    let base = raw.oncurve.clone();
    (raw, base)
}

fn ordered(raw: &SourceOutline, base: &[[f64; 2]]) -> Vec<(usize, Vec<JointOcc>)> {
    let mut out: Vec<(usize, Vec<JointOcc>)> = joints(raw, base).into_iter().collect();
    out.sort_by_key(|(j, _)| *j);
    out
}

fn involved(ix: &[usize]) -> HashSet<usize> {
    ix.iter().copied().collect()
}

fn triangle() -> (SourceOutline, Vec<[f64; 2]>) {
    outline(
        vec![[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]],
        vec![vec![
            GeomSegment::Line { a: 0, b: 1 },
            GeomSegment::Line { a: 1, b: 2 },
            GeomSegment::Line { a: 2, b: 0 },
        ]],
    )
}

#[test]
fn uninvolved_joints_skip_before_degenerate_guard() {
    let (raw, base) = outline(
        vec![[0.0, 0.0], [0.0, 0.0], [1.0, 0.0], [0.0, 1.0]],
        vec![vec![
            GeomSegment::Line { a: 0, b: 1 },
            GeomSegment::Line { a: 1, b: 2 },
            GeomSegment::Line { a: 2, b: 3 },
            GeomSegment::Line { a: 3, b: 0 },
        ]],
    );
    let entries = ordered(&raw, &base);
    assert!(entries
        .iter()
        .any(|(_, occs)| occs.iter().any(|o| o.degenerate)));
    let (hard, gates) = collect_joint_constraints(entries, &base, &involved(&[]), 25.0)
        .ok()
        .expect("uninvolved joints skip");
    assert!(hard.is_empty());
    assert!(gates.is_empty());
}

#[test]
fn smooth_joint_collects_exact_g1_row_with_negated_target() {
    let (raw, base) = triangle();
    let mut entries = ordered(&raw, &base);
    entries.retain(|(j, _)| *j == 1);
    assert_eq!(entries.len(), 1);
    assert_eq!(entries[0].1.len(), 1);
    assert!(entries[0].1[0].smooth && !entries[0].1[0].degenerate);
    let (hard, gates) = collect_joint_constraints(entries.clone(), &base, &involved(&[1]), 25.0)
        .ok()
        .expect("smooth joint collects");
    assert_eq!(hard.len(), 1);
    assert_eq!(hard[0].0, vec![0.0, 1.0, 0.0, -2.0, 0.0, 1.0]);
    assert_eq!(hard[0].1.to_bits(), (-0.0_f64).to_bits());
    assert_eq!(gates.len(), 1);
    assert!((gates[0].j, gates[0].iv, gates[0].ov) == (1, 0, 2));
    assert!(gates[0].prev_line && gates[0].seg_line && gates[0].smooth);
    let bent = vec![[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]];
    let (hard_bent, _) = collect_joint_constraints(entries, &bent, &involved(&[1]), 25.0)
        .ok()
        .expect("bent upstream collects");
    assert_eq!(hard_bent.len(), 1);
    assert_eq!(hard_bent[0].0, vec![-1.0, 0.0, 1.0, -1.0, 0.0, 1.0]);
    assert_eq!(hard_bent[0].1, -1.0);
}

#[test]
fn sharp_joints_record_gates_without_hard_rows() {
    let raw = SourceOutline {
        oncurve: vec![[0.0, 0.0], [2.0, 0.0], [0.0, 2.0]],
        offcurve: vec![[1.0, 1.0]],
        contours: vec![vec![
            GeomSegment::Quad { a: 0, b: 1, c: 0 },
            GeomSegment::Line { a: 1, b: 2 },
            GeomSegment::Line { a: 2, b: 0 },
        ]],
    };
    let base: Vec<[f64; 2]> = raw
        .oncurve
        .iter()
        .chain(raw.offcurve.iter())
        .copied()
        .collect();
    let entries = ordered(&raw, &base);
    assert!(entries
        .iter()
        .all(|(_, occs)| occs.iter().all(|o| !o.smooth)));
    let all: Vec<usize> = (0..base.len()).collect();
    let (hard, gates) = collect_joint_constraints(entries, &base, &involved(&all), 25.0)
        .ok()
        .expect("sharp joints collect");
    assert!(hard.is_empty());
    assert_eq!(gates.len(), 3);
    assert!((gates[0].j, gates[0].prev_line, gates[0].seg_line) == (0, true, false));
    assert!((gates[1].j, gates[1].prev_line, gates[1].seg_line) == (1, false, true));
    assert!(gates.iter().all(|g| !g.smooth));
}

#[test]
fn duplicate_joint_occurrences_keep_input_order() {
    let (raw, base) = outline(
        vec![[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]],
        vec![
            vec![
                GeomSegment::Line { a: 0, b: 1 },
                GeomSegment::Line { a: 1, b: 2 },
                GeomSegment::Line { a: 2, b: 0 },
            ],
            vec![
                GeomSegment::Line { a: 1, b: 0 },
                GeomSegment::Line { a: 0, b: 2 },
                GeomSegment::Line { a: 2, b: 1 },
            ],
        ],
    );
    let occs = joints(&raw, &base).get(&1).expect("shared joint").clone();
    assert_eq!(occs.len(), 2);
    assert!(occs.iter().all(|o| o.smooth && !o.degenerate));
    let set = involved(&[0, 1, 2]);
    let (hard_both, gates_both) =
        collect_joint_constraints(vec![(1usize, occs.clone())], &base, &set, 25.0)
            .ok()
            .expect("grouped duplicates collect");
    let split = vec![
        (1usize, vec![occs[0].clone()]),
        (1usize, vec![occs[1].clone()]),
    ];
    let (hard_split, gates_split) = collect_joint_constraints(split, &base, &set, 25.0)
        .ok()
        .expect("split duplicates collect");
    assert_eq!(hard_both.len(), 2);
    assert_eq!(hard_both[0].0, vec![0.0, 1.0, 0.0, -2.0, 0.0, 1.0]);
    assert_eq!(hard_both[1].0, vec![0.0, -1.0, 0.0, 2.0, 0.0, -1.0]);
    assert_eq!(hard_split, hard_both);
    assert!((gates_both[0].iv, gates_both[0].ov) == (0, 2));
    assert!((gates_both[1].iv, gates_both[1].ov) == (2, 0));
    assert_eq!(gates_split.len(), gates_both.len());
}

#[test]
fn degenerate_joint_and_degenerate_leg_abort() {
    let (raw, base) = outline(
        vec![[0.0, 0.0], [0.0, 0.0], [1.0, 0.0], [0.0, 1.0]],
        vec![vec![
            GeomSegment::Line { a: 0, b: 1 },
            GeomSegment::Line { a: 1, b: 2 },
            GeomSegment::Line { a: 2, b: 3 },
            GeomSegment::Line { a: 3, b: 0 },
        ]],
    );
    let flat = joints(&raw, &base).get(&1).expect("joint").clone();
    assert!(flat.iter().any(|o| o.degenerate));
    assert!(matches!(
        collect_joint_constraints(vec![(1usize, flat)], &base, &involved(&[1]), 25.0),
        Err(JointAbort::DegenerateJoint)
    ));
    let (raw2, base2) = triangle();
    let smooth = joints(&raw2, &base2).get(&1).expect("joint").clone();
    assert!(smooth.iter().all(|o| o.smooth && !o.degenerate));
    let pinched = vec![[0.0, 0.0], [0.0, 0.0], [2.0, 0.0]];
    assert!(matches!(
        collect_joint_constraints(vec![(1usize, smooth)], &pinched, &involved(&[1]), 25.0),
        Err(JointAbort::DegenerateLeg)
    ));
}

#[test]
fn later_joint_validation_precedes_earlier_row_incompatibility() {
    let (raw, mut up) = outline(
        vec![
            [0.0, 0.0],
            [1.0, 0.0],
            [2.0, 0.0],
            [4.0, 0.0],
            [4.0, 0.0],
            [5.0, 0.0],
            [4.0, 1.0],
        ],
        vec![
            vec![
                GeomSegment::Line { a: 0, b: 1 },
                GeomSegment::Line { a: 1, b: 2 },
                GeomSegment::Line { a: 2, b: 0 },
            ],
            vec![
                GeomSegment::Line { a: 3, b: 4 },
                GeomSegment::Line { a: 4, b: 5 },
                GeomSegment::Line { a: 5, b: 6 },
                GeomSegment::Line { a: 6, b: 3 },
            ],
        ],
    );
    let source_joints = joints(&raw, &up);
    let smooth = source_joints[&1].clone();
    let broken = source_joints[&4].clone();
    assert!(smooth.iter().all(|occ| occ.smooth && !occ.degenerate));
    assert!(broken.iter().any(|occ| occ.degenerate));
    up[2] = [1.0, 1.0];
    let entries = vec![(1usize, smooth), (4usize, broken)];
    assert!(matches!(
        collect_joint_constraints(entries, &up, &involved(&[1, 4]), 25.0),
        Err(JointAbort::DegenerateJoint)
    ));
    let (row, constant) = g1_row(&up, 1, "line", 0, "line", 2, 25.0, true).expect("g1 row");
    let target = -constant;
    assert!(target.abs() > 1e-9);
    let zero = |_: &[f64]| vec![0.0; 2];
    assert!(matches!(
        reduce_joint_rows(&[(row, target)], &zero),
        Err(HardRowAbort::FixedIncompatible)
    ));
}

#[test]
fn reducer_zero_row_threshold_and_keep_rules() {
    let identity = |row: &[f64]| row.to_vec();
    let zero_row = vec![0.0, -0.0, 0.0];
    for target in [0.0, 1e-12, -1e-12, 1e-9, -1e-9] {
        let kept = reduce_joint_rows(&[(zero_row.clone(), target)], &identity)
            .ok()
            .expect("boundary target drops");
        assert!(kept.is_empty());
    }
    let just_above = f64::from_bits(1e-9f64.to_bits() + 1);
    assert!(just_above > 1e-9);
    for target in [just_above, -just_above] {
        assert!(matches!(
            reduce_joint_rows(&[(zero_row.clone(), target)], &identity),
            Err(HardRowAbort::FixedIncompatible)
        ));
    }
    for row in [
        vec![2.5, 0.0],
        vec![0.0, -2.5],
        vec![0.0, 1e-300],
        vec![1.0, -1.0],
    ] {
        let kept = reduce_joint_rows(&[(row.clone(), 100.0)], &identity)
            .ok()
            .expect("nonzero row keeps");
        assert_eq!(kept, vec![(row, 100.0)]);
    }
}
