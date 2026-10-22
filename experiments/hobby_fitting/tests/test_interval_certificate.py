"""Sign certificates for Hobby's piece-local segment-site quadratics."""

import unittest

from experiments.hobby_fitting import intervals


class IntervalCertificateTests(unittest.TestCase):
    def test_distant_near_double_root_has_no_local_event(self):
        # For g in [0,1], |a*g*g+b*g| <= |a|+|b| < |c|. A nearly
        # tangent event thousands of pieces away cannot block this piece.
        b, c = -0.0012, 3.06
        a = b * b / (4 * c) * (1 + 1e-12)
        self.assertEqual(intervals._quad_roots(a, b, c), ([], False))
        self.assertEqual(intervals._quad_roots(-a, -b, -c), ([], False))

    def test_local_tangency_and_uncertainty_remain(self):
        self.assertEqual(intervals._quad_roots(1, -1, 0.25), ([0.5], False))
        self.assertEqual(intervals._quad_roots(1, -1, 0.25 + 1e-12),
                         ([], True))
        self.assertEqual(intervals._quad_roots(0, 0, 0), ([], True))
        roots, uncertain = intervals._quad_roots(1, -1, 0.1875)
        self.assertFalse(uncertain)
        self.assertEqual(sorted(roots), [0.25, 0.75])

    def test_bernstein_certificate_when_triangle_bound_cannot_decide(self):
        # c < |a|+|b|, but all Bernstein coefficients are strictly
        # positive. Partition of unity proves positivity on [0,1].
        a, b, c = 0.018, 0.061, 0.0507
        self.assertLess(c, abs(a) + abs(b))
        self.assertEqual(intervals._quad_roots(a, b, c), ([], False))
        self.assertEqual(intervals._quad_roots(-a, -b, -c), ([], False))

    def test_arithmetic_band_at_an_endpoint_is_not_certified(self):
        self.assertEqual(intervals._quad_roots(1, 1e-12, 1e-24),
                         ([], True))

    def test_open_stroke_interval_is_translation_invariant(self):
        verdicts = []
        for shift in (0, 37.5, -1024):
            def point(x, y):
                return x + shift, y + shift

            a = (point(0, 0), point(10, 10))
            b = (point(-1, 1), point(9, 11))
            loop = [a[0], a[1], b[1], b[0]]
            far = point(1000, 1000)
            result = intervals.dominance(
                a, b, [{"seg": (far, far), "tag": "far-point"}], [loop])
            self.assertEqual(result["status"], "ok")
            self.assertTrue(result["intervals"])
            corridor = intervals.corridor(a, b)
            length = corridor["hi"] - corridor["lo"]
            verdicts.append([((p["lo"] - corridor["lo"]) / length,
                              (p["hi"] - corridor["lo"]) / length)
                             for p in result["intervals"]])
        for actual in verdicts[1:]:
            self.assertEqual(len(actual), len(verdicts[0]))
            for expected_span, actual_span in zip(verdicts[0], actual):
                for expected, value in zip(expected_span, actual_span):
                    self.assertAlmostEqual(expected, value, places=12)


if __name__ == "__main__":
    unittest.main()
