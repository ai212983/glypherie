import unittest
import itertools

import numpy as np

from experiments.hobby_fitting import joint_diagonal as joint
from experiments.hobby_fitting.prototype import System


class JointResidualTests(unittest.TestCase):
    def test_equality_and_active_bound_have_analytic_solution(self):
        solved = joint._bounded_equalities(np.eye(2), np.array([2., 0.]),
                                           np.array([[1., 1.]]), np.array([1.]),
                                           np.array([.8, .8]))
        self.assertIsNotNone(solved)
        np.testing.assert_allclose(solved[0], [.8, .2], atol=1e-12)

    def test_incompatible_initialization_fails_closed(self):
        solved = joint._bounded_equalities(np.eye(2), np.zeros(2),
                                           np.array([[1., 1.]]), np.array([3.]),
                                           np.ones(2))
        self.assertIsNone(solved)

    def test_bounded_solver_matches_exhaustive_faces(self):
        rng = np.random.default_rng(271828)
        for _ in range(60):
            n = 3
            a, b = rng.normal(size=(5, n)), rng.normal(size=5)
            g, h = rng.normal(size=(1, n)), np.zeros(1)
            bounds = rng.uniform(.1, 1., size=n)
            best = float('inf')
            for face in itertools.product([-1, 0, 1], repeat=n):
                rows = [g[0]] + [np.eye(n)[i] for i, sign in enumerate(face) if sign]
                rhs = [0.] + [sign * bounds[i] for i, sign in enumerate(face) if sign]
                c, d = np.array(rows), np.array(rhs)
                x = np.linalg.lstsq(c, d, rcond=None)[0]
                if np.max(abs(c @ x - d)) > 1e-8:
                    continue
                _, s, vh = np.linalg.svd(c, full_matrices=True)
                z = vh[int(np.sum(s > 1e-10)):].T
                if z.shape[1]:
                    x += z @ np.linalg.lstsq(a @ z, b - a @ x, rcond=None)[0]
                if np.all(abs(x) <= bounds + 1e-8):
                    best = min(best, float(np.sum((a @ x - b) ** 2)))
            solved = joint._bounded_equalities(a, b, g, h, bounds)
            self.assertIsNotNone(solved)
            self.assertAlmostEqual(float(np.sum((a @ solved[0] - b) ** 2)), best, places=8)

    def setUp(self):
        self.points = [(0., 0.), (1., 2.), (4., 0.), (3., 2.)]
        self.sides = [dict(pair=0, p0=self.points[0], p1=self.points[1], i0=0, i1=1),
                      dict(pair=1, p0=self.points[2], p1=self.points[3], i0=2, i1=3)]

    def test_source_displacement_zero_has_no_symmetry_residual(self):
        system = System(self.points, 16.)
        rows = joint._symmetry_rows(system, [(self.sides[0], self.sides[1], 0.)],
                                    2., 4., 16.)
        self.assertEqual(len(rows), 2)
        for row, constant in rows:
            self.assertAlmostEqual(float(row @ np.zeros(8) + constant), 0.)

    def test_rigid_translation_matches_translated_axis(self):
        system = System(self.points, 16.)
        rows = joint._symmetry_rows(system, [(self.sides[0], self.sides[1], 0.)],
                                    2., 5., 16.)
        delta = np.array([.5, 0.] * 4)
        for row, constant in rows:
            self.assertAlmostEqual(float(row @ delta + constant), 0.)


if __name__ == '__main__':
    unittest.main()
