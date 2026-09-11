"""Geometric and optimization invariants for the bounded Hobby experiment."""
import itertools
import unittest
import numpy as np
from hobby_prototype import segments, evaluate, features, fit, integer_solve


class HobbyTests(unittest.TestCase):
    def test_quadratic_implied_midpoints_keep_partition(self):
        source = np.array([[0, 0], [1, 2], [3, 2], [4, 0]], float)
        curves = segments(source, [1, 0, 0, 1], [3])
        self.assertEqual(len(curves), 3)
        np.testing.assert_allclose(curves[0][-1] @ source, [2, 2])
        for curve in curves:
            for t in np.linspace(0, 1, 7):
                self.assertAlmostEqual(evaluate(curve, t).sum(), 1)

    def test_opposing_boundaries_detect_white_gap(self):
        source = np.array([[0, 0], [0, 6], [1, 6], [1, 0], [3, 0], [3, 6], [4, 6], [4, 0]], float)
        curves = segments(source, [1]*8, [3, 7])
        _, widths = features(source, curves, 12)
        self.assertTrue(any(f['kind'] == 'white' and abs(f['width']-2) < 1e-8 for f in widths))
        self.assertTrue(any(f['kind'] == 'black' and abs(f['width']-1) < 1e-8 for f in widths))

    def test_integer_solver_matches_small_exhaustive_problem(self):
        a = np.array([[1., 0.], [0., 1.], [2., -2.]])
        b = np.array([.2, 1.8, -2.])
        grid = np.eye(2)
        x, info = integer_solve(a, b, grid)
        score = np.sum((a @ x-b)**2)+12*np.sum((x-info['integers'])**2)
        best = float('inf')
        for z in itertools.product(range(-2, 5), repeat=2):
            candidate = np.linalg.solve(a.T @ a+12*grid, a.T @ b+12*np.array(z))
            best = min(best, np.sum((a @ candidate-b)**2)+12*np.sum((candidate-z)**2))
        self.assertAlmostEqual(score, best, places=9)
        self.assertTrue(info['converged'])

    def test_rectangular_fit_preserves_reflections(self):
        source = np.array([[.2, .1], [.2, 7.8], [1.6, 7.8], [1.6, .1]])
        output, info = fit(source, [1]*4, [3], 12)
        self.assertEqual(info['symmetry_axes'], [0, 1])
        np.testing.assert_allclose(output[0]+output[2], output[1]+output[3], atol=1e-6)
        np.testing.assert_array_equal(source, [[.2, .1], [.2, 7.8], [1.6, 7.8], [1.6, .1]])
        self.assertTrue(np.isfinite(output).all())

    def test_cubic_fails_explicitly(self):
        with self.assertRaisesRegex(ValueError, 'quadratic'):
            fit(np.zeros((4, 2)), [1, 2, 2, 1], [3], 12)

    def test_empty_outline(self):
        output, info = fit(np.zeros((0, 2)), [], [], 12)
        self.assertEqual(output.shape, (0, 2))
        self.assertEqual(info['status'], 'empty outline')


if __name__ == '__main__':
    unittest.main()
