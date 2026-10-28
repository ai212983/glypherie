const EPSILON: f64 = 1.0 / 4503599627370496.0;
const ERRBOUND_A: f64 = (3.0 + 16.0 * EPSILON) * EPSILON;

/// Error-filtered orientation sign.
///
/// Source: Shewchuk error-filtered predicates
/// (https://www.cs.cmu.edu/~quake/robust.html); the opposite-sign fast
/// path and the static error bound are exact filters, and anything below
/// the bound abstains. Axis-aligned exact zeros and shared points are
/// decided structurally; other computed zeros abstain.
pub(crate) fn filtered_sign(ax: f64, ay: f64, bx: f64, by: f64, cx: f64, cy: f64) -> Option<i8> {
    if (ax == bx && ay == by) || (ax == cx && ay == cy) || (bx == cx && by == cy) {
        return Some(0);
    }
    if (ay == by && ay == cy) || (ax == bx && ax == cx) {
        return Some(0);
    }
    let acx = ax - cx;
    let bcy = by - cy;
    let acy = ay - cy;
    let bcx = bx - cx;
    let detleft = acx * bcy;
    let detright = acy * bcx;
    let det = detleft - detright;
    if detleft > 0.0 && detright <= 0.0 {
        return Some(1);
    }
    if detleft < 0.0 && detright >= 0.0 {
        return Some(-1);
    }
    if det == 0.0 {
        return None;
    }
    let bound = ERRBOUND_A * (detleft.abs() + detright.abs());
    if det.abs() >= bound {
        return Some(det.signum() as i8);
    }
    None
}
#[cfg(test)]
mod tests {
    use super::filtered_sign;

    #[test]
    fn triangle_orientation_follows_permutation_sign() {
        let p = [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]];
        let cases = [
            ([0, 1, 2], 1),
            ([0, 2, 1], -1),
            ([1, 0, 2], -1),
            ([1, 2, 0], 1),
            ([2, 0, 1], 1),
            ([2, 1, 0], -1),
        ];
        for (perm, expected) in cases {
            let (a, b, c) = (p[perm[0]], p[perm[1]], p[perm[2]]);
            assert_eq!(
                filtered_sign(a[0], a[1], b[0], b[1], c[0], c[1]),
                Some(expected)
            );
        }
    }

    #[test]
    fn structural_zeros_stand_apart_from_unresolved_collinearity() {
        let a = [2.0, 3.0];
        let b = [5.0, 7.0];
        for (p, q, r) in [(a, a, b), (a, b, a), (b, a, a), (a, a, a)] {
            assert_eq!(filtered_sign(p[0], p[1], q[0], q[1], r[0], r[1]), Some(0));
        }
        assert_eq!(filtered_sign(2.0, 3.0, 2.0, 7.0, 2.0, 11.0), Some(0));
        assert_eq!(filtered_sign(2.0, 3.0, 5.0, 3.0, 8.0, 3.0), Some(0));
        assert_eq!(filtered_sign(2.0, 3.0, 5.0, 7.0, 8.0, 11.0), None);
    }
}
