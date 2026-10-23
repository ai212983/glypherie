use super::*;

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

#[test]
fn quad_predicate_branches_and_order_use_cand_coords() {
    let raw = outline(
        vec![[70.0, 70.0]; 6],
        vec![[71.0, 71.0]; 3],
        vec![
            vec![
                GeomSegment::Quad { c: 0, a: 0, b: 1 },
                GeomSegment::Line { a: 1, b: 0 },
            ],
            vec![
                GeomSegment::Quad { c: 1, a: 2, b: 3 },
                GeomSegment::Line { a: 3, b: 2 },
            ],
            vec![
                GeomSegment::Quad { c: 2, a: 4, b: 5 },
                GeomSegment::Line { a: 5, b: 4 },
            ],
        ],
    );
    let quads = vec![[0, 6, 1], [2, 7, 3], [4, 8, 5]];
    let involved: HashSet<usize> = [6, 7].into_iter().collect();
    let up: Vec<[f64; 2]> = (0..9)
        .map(|i| [10.0 + i as f64, 20.0 + 2.0 * i as f64])
        .collect();
    let mut cand = up.clone();
    cand[7] = [17.5, 34.0];
    cand[8] = [18.5, 36.0];
    let out = collect_clearance_primitives(&raw, &quads, &involved, &cand, &up);
    assert_eq!(
        out.fixed_curves,
        vec![
            vec![[10.0, 20.0], [16.0, 32.0], [11.0, 22.0]],
            vec![[14.0, 28.0], [18.5, 36.0], [15.0, 30.0]],
        ]
    );
    assert_eq!(
        out.fixed_lines,
        vec![
            ([11.0, 22.0], [10.0, 20.0]),
            ([13.0, 26.0], [12.0, 24.0]),
            ([15.0, 30.0], [14.0, 28.0]),
        ]
    );
    assert!(out.moved_lines.is_empty());
}

#[test]
fn uninvolved_unchanged_quad_fixed() {
    let raw = outline(
        vec![[70.0, 70.0]; 2],
        vec![[71.0, 71.0]],
        vec![vec![
            GeomSegment::Quad { c: 0, a: 0, b: 1 },
            GeomSegment::Line { a: 1, b: 0 },
        ]],
    );
    let quads = vec![[0, 2, 1]];
    let involved: HashSet<usize> = HashSet::new();
    let up = vec![[1.0, 2.0], [5.0, 6.0], [3.0, 9.0]];
    let out = collect_clearance_primitives(&raw, &quads, &involved, &up, &up);
    assert_eq!(
        out.fixed_curves,
        vec![vec![[1.0, 2.0], [3.0, 9.0], [5.0, 6.0]]]
    );
    assert_eq!(out.fixed_lines, vec![([5.0, 6.0], [1.0, 2.0])]);
    assert!(out.moved_lines.is_empty());
}

#[test]
fn lines_two_contours_order_quad_ignored_zero_length() {
    let raw = outline(
        vec![[7.0, 7.0]; 6],
        vec![[7.0, 7.0]],
        vec![
            vec![
                GeomSegment::Line { a: 0, b: 1 },
                GeomSegment::Quad { c: 0, a: 1, b: 2 },
                GeomSegment::Line { a: 1, b: 2 },
            ],
            vec![
                GeomSegment::Line { a: 3, b: 3 },
                GeomSegment::Line { a: 4, b: 5 },
            ],
        ],
    );
    let quads = vec![[1, 6, 2]];
    let involved: HashSet<usize> = [6].into_iter().collect();
    let up = vec![
        [0.0, 0.0],
        [4.0, 0.0],
        [9.0, 1.0],
        [30.0, 30.0],
        [40.0, 40.0],
        [50.0, 50.0],
        [44.0, 41.0],
    ];
    let mut cand = up.clone();
    cand[2] = [9.5, 1.0];
    cand[5] = [50.0, 55.0];
    cand[6] = [44.5, 41.0];
    let out = collect_clearance_primitives(&raw, &quads, &involved, &cand, &up);
    assert!(out.fixed_curves.is_empty());
    assert_eq!(out.fixed_lines, vec![(up[0], up[1]), (up[3], up[3])]);
    assert_eq!(
        out.moved_lines,
        vec![
            ((up[1], up[2]), (cand[1], cand[2])),
            ((up[4], up[5]), (cand[4], cand[5]))
        ]
    );
    for line in out
        .fixed_lines
        .iter()
        .chain(out.moved_lines.iter().flat_map(|(o, n)| [o, n]))
    {
        assert!(line.0 != [7.0, 7.0] && line.1 != [7.0, 7.0]);
    }
}

#[test]
fn y_only_change_moves_full_point_comparison() {
    let raw = outline(
        vec![[0.0, 0.0]; 3],
        Vec::new(),
        vec![vec![
            GeomSegment::Line { a: 0, b: 1 },
            GeomSegment::Line { a: 1, b: 2 },
        ]],
    );
    let up = vec![[0.0, 0.0], [4.0, 0.0], [9.0, 0.0]];
    let mut cand = up.clone();
    cand[2] = [9.0, 0.5];
    let out = collect_clearance_primitives(&raw, &[], &HashSet::new(), &cand, &up);
    assert_eq!(out.fixed_lines, vec![(up[0], up[1])]);
    assert_eq!(out.moved_lines, vec![((up[1], up[2]), (cand[1], cand[2]))]);
}

#[test]
fn moved_orientation_old_up_new_cand() {
    let raw = outline(
        vec![[0.0, 0.0]; 2],
        Vec::new(),
        vec![vec![GeomSegment::Line { a: 0, b: 1 }]],
    );
    let up = vec![[1.0, 2.0], [3.0, 4.0]];
    let cand = vec![[5.0, 6.0], [7.0, 8.0]];
    let out = collect_clearance_primitives(&raw, &[], &HashSet::new(), &cand, &up);
    assert!(out.fixed_lines.is_empty());
    assert_eq!(out.moved_lines, vec![((up[0], up[1]), (cand[0], cand[1]))]);
}

#[test]
fn empty_inputs_yield_empty_primitives() {
    let raw = outline(Vec::new(), Vec::new(), Vec::new());
    let out = collect_clearance_primitives(&raw, &[], &HashSet::new(), &[], &[]);
    assert!(out.fixed_curves.is_empty());
    assert!(out.fixed_lines.is_empty());
    assert!(out.moved_lines.is_empty());
}
