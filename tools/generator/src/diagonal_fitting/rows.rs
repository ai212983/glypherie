//! Hobby edge (1)-(3) and pair-width (4)-(5) residuals.
//!
//! Callers supply their projection arithmetic to preserve signed-zero behavior.

use super::Sample;

pub(super) struct EdgeRows {
    pub(super) sum: Vec<f64>,
    pub(super) diff: Vec<f64>,
    pub(super) stretch: Vec<f64>,
    pub(super) bend: Vec<f64>,
}

/// Straight-edge position, stretch and bend residuals.
pub(super) fn edge_rows(
    points: &[[f64; 2]],
    height: f64,
    i: usize,
    j: usize,
    project: impl Fn(&Sample, [f64; 2], Option<&Sample>) -> Vec<f64>,
) -> Result<EdgeRows, ()> {
    let a = Sample::vertex(i);
    let b = Sample::vertex(j);
    let pa = a.point(points);
    let pb = b.point(points);
    let delta = [pb[0] - pa[0], pb[1] - pa[1]];
    let length = delta[0].hypot(delta[1]);
    if !(length > 0.0) {
        return Err(());
    }
    let tangent = [delta[0] / length, delta[1] / length];
    let normal = [-tangent[1], tangent[0]];
    let alpha1 = 1000.0 / height.powi(3);
    let ri = project(&a, normal, None);
    let rj = project(&b, normal, None);
    let sum: Vec<f64> = ri
        .iter()
        .zip(rj.iter())
        .map(|(x, y)| (x + y) * (alpha1 * length / 4.0).sqrt())
        .collect();
    let diff: Vec<f64> = rj
        .iter()
        .zip(ri.iter())
        .map(|(x, y)| (x - y) * (alpha1 * length / 12.0).sqrt())
        .collect();
    let scale = (25.0 * length / height).sqrt() / length;
    let stretch: Vec<f64> = project(&b, tangent, Some(&a))
        .iter()
        .map(|x| x * scale)
        .collect();
    let bend: Vec<f64> = rj
        .iter()
        .zip(ri.iter())
        .map(|(x, y)| (x - y) * scale)
        .collect();
    Ok(EdgeRows {
        sum,
        diff,
        stretch,
        bend,
    })
}

/// Signed relative-width error using twice the medial radius.
pub(super) fn pair_residual(
    points: &[[f64; 2]],
    a: &Sample,
    b: &Sample,
    arc: f64,
    medial: [f64; 2],
    project: impl Fn(&Sample, [f64; 2], Option<&Sample>) -> Vec<f64>,
) -> Result<(Vec<f64>, f64, [f64; 2]), ()> {
    if !(arc.is_finite() && arc > 0.0) {
        return Err(());
    }
    let pa = a.point(points);
    let pb = b.point(points);
    let chord = [pa[0] - pb[0], pa[1] - pb[1]];
    let distance = chord[0].hypot(chord[1]);
    if !(distance > 0.0) {
        return Err(());
    }
    let width = 2.0 * (pa[0] - medial[0]).hypot(pa[1] - medial[1]);
    let other = 2.0 * (pb[0] - medial[0]).hypot(pb[1] - medial[1]);
    if !(width > 0.0) || (width - other).abs() > 1e-12 + 1e-10 * other.abs() {
        return Err(());
    }
    let normal = [chord[0] / distance, chord[1] / distance];
    let tangent = [-normal[1], normal[0]];
    let mut error = project(a, normal, Some(b));
    for x in error.iter_mut() {
        *x /= -width;
    }
    Ok((error, width, tangent))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn no_projection(_: &Sample, _: [f64; 2], _: Option<&Sample>) -> Vec<f64> {
        panic!("invalid input must fail before projecting");
    }

    fn scripted(script: Vec<Vec<f64>>) -> impl Fn(&Sample, [f64; 2], Option<&Sample>) -> Vec<f64> {
        let script = std::cell::RefCell::new(script.into_iter().rev().collect::<Vec<_>>());
        move |_, _, _| {
            script
                .borrow_mut()
                .pop()
                .expect("projection script exhausted")
        }
    }

    fn project_correspondence(
        point_count: usize,
    ) -> impl Fn(&Sample, [f64; 2], Option<&Sample>) -> Vec<f64> {
        use super::super::basis_row;
        move |a: &Sample, dir: [f64; 2], b: Option<&Sample>| {
            let ba = basis_row(&a.terms, point_count);
            let mut row = vec![0.0; 2 * point_count];
            for (k, w) in ba.iter().enumerate() {
                row[2 * k] = w * dir[0];
                row[2 * k + 1] = w * dir[1];
            }
            if let Some(other) = b {
                let bb = basis_row(&other.terms, point_count);
                for (k, w) in bb.iter().enumerate() {
                    row[2 * k] -= w * dir[0];
                    row[2 * k + 1] -= w * dir[1];
                }
            }
            row
        }
    }

    #[test]
    fn edge_rows_rejects_zero_length_before_projecting() {
        let points = [[1.0, 1.0], [1.0, 1.0]];
        assert!(edge_rows(&points, 10.0, 0, 1, no_projection).is_err());
    }

    #[test]
    fn pair_residual_rejects_invalid_inputs_before_projecting() {
        let points = [[0.0, 0.0], [4.0, 0.0]];
        let a = Sample::vertex(0);
        let b = Sample::vertex(1);
        assert!(pair_residual(&points, &a, &b, 0.0, [2.0, 0.0], no_projection).is_err());
        assert!(pair_residual(&points, &a, &b, f64::INFINITY, [2.0, 0.0], no_projection).is_err());
        assert!(pair_residual(&points, &a, &a, 2.0, [0.0, 0.0], no_projection).is_err());
        assert!(pair_residual(&points, &a, &b, 2.0, [1.0, 0.0], no_projection).is_err());
    }

    #[test]
    fn edge_rows_applies_sourced_scales_in_order() {
        let points = [[0.0, 0.0], [4.0, 0.0]];
        let built = edge_rows(
            &points,
            10.0,
            0,
            1,
            scripted(vec![
                vec![1.0, 2.0, 3.0, 4.0],
                vec![5.0, 6.0, 7.0, 8.0],
                vec![0.5, -0.5, 1.5, -1.5],
            ]),
        )
        .expect("scripted edge must build");
        assert_eq!(built.sum, vec![6.0, 8.0, 10.0, 12.0]);
        let close = |got: &[f64], want: &[f64]| {
            assert_eq!(got.len(), want.len());
            for (g, w) in got.iter().zip(want.iter()) {
                assert!((g - w).abs() < 1e-12, "{g} != {w}");
            }
        };
        close(&built.diff, &[2.309401076758503; 4]);
        close(
            &built.stretch,
            &[
                0.3952847075210474,
                -0.3952847075210474,
                1.1858541225631423,
                -1.1858541225631423,
            ],
        );
        close(&built.bend, &[3.1622776601683795; 4]);
    }

    #[test]
    fn pair_residual_scales_error_by_negative_width() {
        let points = [[0.0, 0.0], [4.0, 0.0]];
        let a = Sample::vertex(0);
        let b = Sample::vertex(1);
        let (error, width, tangent) = pair_residual(
            &points,
            &a,
            &b,
            2.0,
            [2.0, 0.0],
            scripted(vec![vec![8.0, -4.0, 0.0, 0.0]]),
        )
        .expect("scripted pair must build");
        assert_eq!(width, 4.0);
        assert_eq!(tangent[0].to_bits(), (-0.0f64).to_bits());
        assert_eq!(tangent[1], -1.0);
        assert_eq!(&error[0..2], &[-2.0, 1.0]);
        assert_eq!(error[2].to_bits(), (-0.0f64).to_bits());
        assert_eq!(error[3].to_bits(), (-0.0f64).to_bits());
        let shifted: Vec<[f64; 2]> = points.iter().map(|p| [p[0] + 7.5, p[1] - 3.25]).collect();
        let (moved, moved_width, moved_tangent) = pair_residual(
            &shifted,
            &a,
            &b,
            2.0,
            [9.5, -3.25],
            scripted(vec![vec![8.0, -4.0, 0.0, 0.0]]),
        )
        .expect("translated pair must build");
        let bits = |v: &[f64]| v.iter().map(|x| x.to_bits()).collect::<Vec<_>>();
        assert_eq!(moved_width, width);
        assert_eq!(moved_tangent, tangent);
        assert_eq!(bits(&moved), bits(&error));
    }

    #[test]
    fn oblique_edge_rows_carry_nonunit_positional_scale() {
        // Hobby (1)-(3) on a 3-4-5 edge gives nonunit positional residuals.
        let points = [[0.0, 0.0], [3.0, 4.0]];
        let built = edge_rows(&points, 10.0, 0, 1, project_correspondence(points.len()))
            .expect("oblique edge must build");
        let dot = |row: &[f64], d: &[f64]| row.iter().zip(d.iter()).map(|(r, s)| r * s).sum();
        let close = |got: f64, want: f64| assert!((got - want).abs() < 1e-12, "{got} != {want}");
        close(
            dot(&built.sum, &[-0.4, 0.3, -0.4, 0.3]),
            (5.0f64 / 4.0).sqrt(),
        );
        close(
            dot(&built.diff, &[-0.4, 0.3, 0.4, -0.3]),
            -(5.0f64 / 12.0).sqrt(),
        );
        let scale = (12.5f64).sqrt() / 5.0;
        close(dot(&built.stretch, &[0.0, 0.0, 0.6, 0.8]), scale);
        close(dot(&built.bend, &[0.0, 0.0, -0.8, 0.6]), scale);
    }

    #[test]
    fn pair_residual_rejects_coincident_contacts() {
        let points = [[2.0, 3.0]];
        let a = Sample::vertex(0);
        assert!(
            pair_residual(&points, &a, &a, 2.0, [3.5, 3.0], project_correspondence(1)).is_err()
        );
    }

    #[test]
    fn pair_residual_rejects_zero_first_radius() {
        let points = [[0.0, 0.0], [1e-13, 0.0]];
        let a = Sample::vertex(0);
        let b = Sample::vertex(1);
        assert!(
            pair_residual(&points, &a, &b, 2.0, [0.0, 0.0], project_correspondence(2)).is_err()
        );
    }

    #[test]
    fn pair_residual_accepts_exact_absolute_tolerance_boundary() {
        // Doubling 5e-13 is exact, so width is exactly 1e-12: equal to, not
        // above, the absolute radius-symmetry bound.
        let points = [[0.0, 0.0], [5e-13, 0.0]];
        let a = Sample::vertex(0);
        let b = Sample::vertex(1);
        let (error, width, _) = pair_residual(
            &points,
            &a,
            &b,
            2.0,
            [5e-13, 0.0],
            project_correspondence(points.len()),
        )
        .expect("absolute-tolerance boundary pair must build");
        assert_eq!(width, 1e-12);
        assert!(error.iter().all(|x| x.is_finite()));
    }

    #[test]
    fn pair_residual_accepts_near_equal_pair_via_relative_tolerance() {
        // The radius mismatch needs the relative tolerance, beyond the absolute term.
        let points = [[1.0 + 5e-11, 0.0], [1.0, 0.0]];
        let a = Sample::vertex(0);
        let b = Sample::vertex(1);
        let (error, width, _) = pair_residual(
            &points,
            &a,
            &b,
            2.0,
            [0.0, 0.0],
            project_correspondence(points.len()),
        )
        .expect("relative-tolerance pair must build");
        assert!(width > 1.0);
        assert!((width - 2.0).abs() > 1e-12);
        assert!(error.iter().all(|x| x.is_finite()));
    }
}
