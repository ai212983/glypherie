//! Shared placement for source-certified straight/curve features.
//!
//! Hersch §§5–6 permits paired borders to rotate together; Hobby (17)
//! retains relative widths as soft terms. Hobby §§3.5–3.6 supplies source
//! reflection correspondence and its mismatch-preserving objective. The
//! nearest half-pixel frame phase is a project adaptation: reflection about
//! such an axis maps pixel centers to pixel centers (Hobby §2 center fill).
//! No bitmap, font identity or fitted pixel count participates.
use super::{
    super::crossing::{self, Side},
    AttachedPair,
};
use crate::diagonal_fitting::geometry::{Parsed, Segment};
use std::collections::HashSet;

pub(super) fn parallel_row(pair: &AttachedPair, up: &[[f64; 2]]) -> Option<Vec<f64>> {
    let mut row = vec![0.0; 2 * up.len()];
    for (edge, sign) in [(&pair.a, 1.0), (&pair.b, -1.0)] {
        let dy = up[edge.i1][1] - up[edge.i0][1];
        if dy == 0.0 || !dy.is_finite() {
            return None;
        }
        row[2 * edge.i1] += sign / dy;
        row[2 * edge.i0] -= sign / dy;
    }
    Some(row)
}

pub(super) struct ReflectionPhase {
    frame: [usize; 2],
    pub source_axis: f64,
    pub target: f64,
    pub matches: Vec<(Side, Side, f64)>,
}
impl ReflectionPhase {
    pub fn row(&self, points: usize) -> Vec<f64> {
        let mut row = vec![0.0; 2 * points];
        for v in self.frame {
            row[2 * v] += 0.5;
        }
        row
    }
    pub fn axis(&self, points: &[[f64; 2]]) -> f64 {
        (points[self.frame[0]][0] + points[self.frame[1]][0]) / 2.0
    }
    pub fn certified(&self, points: &[[f64; 2]]) -> bool {
        let lo = points[self.frame[0]][0];
        let hi = points[self.frame[1]][0];
        self.axis(points) == self.target && points.iter().all(|p| lo <= p[0] && p[0] <= hi)
    }
}

fn contour_reflects(parsed: &Parsed, axis: f64, epsilon: f64) -> bool {
    if parsed.contours.len() != 1 {
        return false;
    }
    let edges: Vec<_> = parsed.contours[0]
        .iter()
        .filter(|s| {
            let (a, b) = s.endpoints();
            !(s.is_line() && parsed.oncurve[a] == parsed.oncurve[b])
        })
        .collect();
    if edges.is_empty() {
        return false;
    }
    let distance = |p: [f64; 2], q: [f64; 2]| (q[0] - (2.0 * axis - p[0])).hypot(q[1] - p[1]);
    let mut choices = Vec::new();
    for shift in 0..edges.len() {
        let mut error = 0.0_f64;
        for (i, edge) in edges.iter().enumerate() {
            let other = edges[(shift + edges.len() - i) % edges.len()];
            let (a, b) = edge.endpoints();
            let (c, d) = other.endpoints();
            error = error
                .max(distance(parsed.oncurve[a], parsed.oncurve[d]))
                .max(distance(parsed.oncurve[b], parsed.oncurve[c]));
            match (edge, other) {
                (Segment::Line { .. }, Segment::Line { .. }) => {}
                (Segment::Quad { c: a, .. }, Segment::Quad { c: b, .. }) => {
                    error = error.max(distance(parsed.offcurve[*a], parsed.offcurve[*b]));
                }
                _ => {
                    error = f64::INFINITY;
                    break;
                }
            }
        }
        if error <= epsilon {
            choices.push(error);
        }
    }
    // Multiple traversal correspondences do not certify a unique reflected
    // feature. No best-looking phase or correspondence is chosen.
    choices.len() == 1
}

pub(super) fn reflection_phase(
    pairs: &[AttachedPair],
    parsed: &Parsed,
    base: &[[f64; 2]],
    up: &[[f64; 2]],
) -> Option<ReflectionPhase> {
    let no = parsed.oncurve.len();
    if pairs.len() < 2 {
        return None;
    }
    // The existing Hobby border-match tolerance is in source pixel units;
    // it recognizes approximate correspondence, never an ink threshold.
    let epsilon = crossing::EPS_PARITY;
    let lo = (0..no).min_by(|&a, &b| base[a][0].total_cmp(&base[b][0]))?;
    let hi = (0..no).max_by(|&a, &b| base[a][0].total_cmp(&base[b][0]))?;
    if lo == hi || base[lo][1] != base[hi][1] || up[lo][1] != up[hi][1] {
        return None;
    }
    let source_axis = (base[lo][0] + base[hi][0]) / 2.0;
    if base
        .iter()
        .any(|p| p[0] < base[lo][0] || p[0] > base[hi][0])
    {
        return None;
    }
    // Hobby §3.5 matches ordered source outline intervals. A reflection
    // reverses contour traversal; verify corresponding edge kinds and
    // controls, rather than pairing nearby vertices independently.
    if !contour_reflects(parsed, source_axis, epsilon) {
        return None;
    }
    let sides: Vec<_> = pairs
        .iter()
        .flat_map(|p| {
            [&p.a, &p.b].map(|e| Side {
                pair: p.id.clone(),
                p0: e.p0,
                p1: e.p1,
                i0: e.i0,
                i1: e.i1,
                t0: e.t0,
                t1: e.t1,
            })
        })
        .collect();
    let matches = crossing::match_borders(&sides, source_axis, epsilon);
    let key = |a: usize, b: usize| (a.min(b), a.max(b));
    let mut used = HashSet::new();
    for (a, b, _) in &matches {
        if !used.insert(key(a.i0, a.i1)) || !used.insert(key(b.i0, b.i1)) {
            return None;
        }
    }
    if matches.len() * 2 != sides.len()
        || ![lo, hi]
            .iter()
            .all(|v| sides.iter().any(|s| s.i0 == *v || s.i1 == *v))
    {
        return None;
    }
    let axis = (up[lo][0] + up[hi][0]) / 2.0;
    // An equidistant choice has no geometric preference; leave reflection
    // phase unconstrained instead of selecting it by pixel outcome.
    if (2.0 * axis).fract().abs() == 0.5 {
        return None;
    }
    let target = (2.0 * axis + 0.5).floor() / 2.0;
    Some(ReflectionPhase {
        frame: [lo, hi],
        source_axis,
        target,
        matches,
    })
}

#[cfg(test)]
mod tests {
    use super::super::Gate;
    use super::*;
    use crate::diagonal_fitting::{geometry::Portion, joint, System};
    fn fixture(offset: f64) -> (Vec<AttachedPair>, Vec<[f64; 2]>, Vec<[f64; 2]>) {
        let base = vec![
            [0., 12.],
            [4.25, 0.],
            [5.75, 0.],
            [10., 12.],
            [8.5, 12.],
            [5.5, 3.],
            [4.5, 3.],
            [1.5, 12.],
        ];
        let up = base.iter().map(|p| [p[0] + offset, p[1]]).collect();
        (pairs(&base), base, up)
    }
    fn outline(base: &[[f64; 2]]) -> Parsed {
        Parsed {
            oncurve: base[..8].to_vec(),
            offcurve: base[8..].to_vec(),
            contours: vec![(0..8)
                .map(|a| Segment::Line { a, b: (a + 1) % 8 })
                .collect()],
        }
    }
    fn pairs(base: &[[f64; 2]]) -> Vec<AttachedPair> {
        let edge = |a, b| Portion {
            contour: 0,
            seg: a,
            t0: 0.,
            t1: 1.,
            p0: base[a],
            p1: base[b],
            i0: a,
            i1: b,
            hidden: false,
            unknown: false,
        };
        [((0, 1), (6, 7)), ((2, 3), (4, 5))]
            .into_iter()
            .enumerate()
            .map(|(i, ((a, b), (c, d)))| AttachedPair {
                id: i.to_string(),
                a: edge(a, b),
                b: edge(c, d),
                normal: [1., 0.],
                stations: vec![],
                src_widths: vec![1.],
                arc: 12.,
                gate: Gate {
                    axis: 0,
                    integer: 1,
                    target: 1.,
                    coupled: 1.,
                    rel: 0.,
                    w_src: 1.,
                    fa: 0.5,
                    fb: 0.5,
                },
            })
            .collect()
    }
    #[test]
    fn shared_slope_retains_rotation_freedom() {
        let (pairs, base, _) = fixture(0.);
        let row = parallel_row(&pairs[0], &base).unwrap();
        let candidate: Vec<_> = base
            .iter()
            .map(|p| [0.6 * p[1] + p[0] * 0.0, p[1]])
            .collect();
        let flat: Vec<_> = candidate.iter().flat_map(|p| *p).collect();
        assert!((super::super::dot(&row, &flat)).abs() < 1e-12);
        // Opposing borders with different slopes must remain constrained.
        let mut bent = flat;
        bent[2 * pairs[0].a.i0] += 1.;
        assert!(super::super::dot(&row, &bent).abs() > 0.01);
    }
    #[test]
    fn phase_is_geometric_translation_and_reflection_covariant() {
        for (offset, target) in [(0.125, 5.), (1.125, 6.), (-0.125, 5.)] {
            let (pairs, base, up) = fixture(offset);
            let phase = reflection_phase(&pairs, &outline(&base), &base, &up).unwrap();
            assert_eq!(phase.target, target);
            let reflected: Vec<_> = base.iter().map(|p| [-p[0], p[1]]).collect();
            let up_reflected: Vec<_> = up.iter().map(|p| [-p[0], p[1]]).collect();
            let other = reflection_phase(
                &self::pairs(&reflected),
                &outline(&reflected),
                &reflected,
                &up_reflected,
            )
            .unwrap();
            assert_eq!(other.target, -target);
        }
    }
    #[test]
    fn reflection_objective_preserves_source_mismatch() {
        let (_, mut base, up) = fixture(0.);
        base[7][0] += 1. / 32.;
        let phase = reflection_phase(&pairs(&base), &outline(&base), &base, &up).unwrap();
        let system = System::new(base.clone(), 16.);
        let rows = joint::symmetry_rows(
            &system,
            &phase.matches,
            phase.source_axis,
            2. * phase.target,
            16.,
        );
        assert!(!rows.is_empty());
        // At the source the displacement is zero even for the deliberately
        // unequal inner borders; reflection is not a demand for equality.
        assert!(rows.iter().all(|(_, constant)| constant.abs() < 1e-10));
    }
    #[test]
    fn phased_solve_and_rounding_retain_deliberate_source_asymmetry() {
        // Hobby (16) keeps the source reflection residual while changing
        // the map's placement. Exercise the upstream-displacement conversion
        // through the real bounded solver and 26.6 delivery, not only rows.
        let (_, mut base, _) = fixture(0.);
        base[7][0] += 0.125;
        let up: Vec<_> = base.iter().map(|p| [p[0] + 0.125, p[1]]).collect();
        let phase = reflection_phase(&pairs(&base), &outline(&base), &base, &up).unwrap();
        let n = base.len();
        let gaps: Vec<_> = up
            .iter()
            .zip(&base)
            .flat_map(|(u, b)| [u[0] - b[0], 0.])
            .collect();
        let mut a = Vec::new();
        let mut b = Vec::new();
        for i in 0..n {
            let mut row = vec![0.; n];
            row[i] = 1.;
            a.push(row);
            b.push(0.);
        }
        for (row, constant) in joint::symmetry_rows(
            &System::new(base.clone(), 16.),
            &phase.matches,
            phase.source_axis,
            2. * phase.target,
            16.,
        ) {
            b.push(-(super::super::dot(&row, &gaps) + constant));
            a.push(row.chunks_exact(2).map(|r| r[0]).collect());
        }
        let frame: Vec<_> = phase.row(n).chunks_exact(2).map(|r| r[0]).collect();
        let (delta, _) = crate::diagonal_fitting::qp::bounded_equalities(
            &a,
            &b,
            &[frame],
            &[phase.target - phase.axis(&up)],
            &vec![0.5; n],
        )
        .unwrap();
        let delivered: Vec<_> = up
            .iter()
            .zip(delta)
            .map(|(p, dx)| [((p[0] + dx) * 64.).round() / 64., p[1]])
            .collect();
        assert!(phase.certified(&delivered));
        let mismatch = |points: &[[f64; 2]], axis: f64| points[4][0] + points[7][0] - 2. * axis;
        assert_eq!(mismatch(&base, phase.source_axis), 0.125);
        assert_eq!(mismatch(&delivered, phase.target), 0.125);
    }
    #[test]
    fn unmatched_curve_control_and_equidistant_phase_abstain() {
        let (pairs, mut base, up) = fixture(0.25);
        assert!(reflection_phase(&pairs, &outline(&base), &base, &up).is_none());
        base.push([9., 6.]);
        let mut source = outline(&base);
        source.contours[0][1] = Segment::Quad { a: 1, b: 2, c: 0 };
        assert!(reflection_phase(&pairs, &source, &base, &base).is_none());
    }
}
