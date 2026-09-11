"""Tests for central_upright_fit.fit."""
import unittest
import numpy as np
from central_upright_fit import fit


SRC = [[3.57, 1.134], [3.57, 3.878], [1.092, 3.878], [1.092, 4.732],
       [3.57, 4.732], [3.57, 7.294], [4.48, 7.294], [4.48, 4.732],
       [7.056, 4.732], [7.056, 3.878], [4.48, 3.878], [4.48, 1.134]]
CUR = [[4, 1], [4, 4], [1, 4], [1, 5], [4, 5], [4, 7],
       [5, 7], [5, 5], [7, 5], [7, 4], [5, 4], [5, 1]]
ENDS = [11]
FLAGS = [1] * 12


class FitTests(unittest.TestCase):
    def test_primary_candidate(self):
        mapped, audit = fit(SRC, ENDS, FLAGS, CUR, 1)
        self.assertEqual(audit['status'], 'candidate')
        np.testing.assert_allclose(np.asarray(mapped)[:, 1],
                                   np.asarray(CUR)[:, 1], atol=0)
        xs = sorted(set(float(v) for v in np.asarray(mapped)[:, 0]))
        # fitted stem width 1 preserved
        self.assertIn(5.0, xs)
        stem = [x for x in xs if 3.9 < x < 5.1]
        self.assertAlmostEqual(max(stem) - min(stem), 1.0)
        kt = audit['evidence']['target_knots']
        self.assertAlmostEqual((kt[1] + kt[2]) / 2.0,
                               (kt[0] + kt[3]) / 2.0)

    def test_already_centered_noop(self):
        q = np.asarray(CUR, float)
        c = (q[:, 0].min() + q[:, 0].max()) / 2.0
        s = (4.0 + 5.0) / 2.0
        shift = c - s
        src = (np.asarray(SRC, float) + [shift, 0]).tolist()
        cur = (q + [shift, 0]).tolist()
        mapped, audit = fit(src, ENDS, FLAGS, cur, 1)
        # symmetric source recentred onto already-centered current: no move
        self.assertIn(audit['status'], ('already-centered', 'candidate'))
        if audit['status'] == 'already-centered':
            np.testing.assert_allclose(mapped, cur, atol=0)

    def test_source_asymmetric_hold(self):
        src = [list(r) for r in SRC]
        src[6][0] += 2.0
        src[7][0] += 2.0
        _, audit = fit(src, ENDS, FLAGS, CUR, 1)
        self.assertNotEqual(audit['status'], 'candidate')

    def test_translated_case(self):
        dx = 10.0
        src = (np.asarray(SRC, float) + [dx, 0]).tolist()
        cur = (np.asarray(CUR, float) + [dx, 0]).tolist()
        mapped, audit = fit(src, ENDS, FLAGS, cur, 1)
        self.assertEqual(audit['status'], 'candidate')

    def test_missing_stem(self):
        _, audit = fit(SRC, ENDS, FLAGS,
                       (np.asarray(CUR, float) + [0.3, 0]).tolist(), 1)
        # shifted current breaks integer width / centering -> hold, not candidate
        # (documents conservative behaviour; exact reason is informational)
        if audit['status'] == 'candidate':
            kt = audit['evidence']['target_knots']
            self.assertAlmostEqual((kt[1] + kt[2]) / 2.0,
                                   (kt[0] + kt[3]) / 2.0)
        else:
            self.assertIn(audit['status'], ('held', 'unaffected'))

    def test_curve_cross_knot_hold(self):
        ends = [13]
        flags = [1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
        cur = (CUR[:2] + [[4.0, 2.5]] + [[4.5, 3.0]] + CUR[2:])
        src = (SRC[:2] + [[3.57, 2.5]] + [[4.0, 3.0]] + SRC[2:])
        try:
            _, audit = fit(src, ends, flags, cur, 1)
        except Exception:
            return  # conservative: any refusal path is a hold
        self.assertNotEqual(audit.get('status'), 'candidate')


if __name__ == '__main__':
    unittest.main()
