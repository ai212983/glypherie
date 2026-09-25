import unittest
import numpy as np
from cross_section_widths import section, system


class CrossSectionTests(unittest.TestCase):
    def setUp(self):
        self.points = np.array([[0., 0.], [0., 10.], [4., 10.], [2., 0.]])
        self.feature = dict(normal=[1., 0.], support_direction=[0., 1.],
                            support_intervals=[[0., 10.]], width=3., points=[0, 2])

    def test_taper_width_uses_cross_section_not_representative_distance(self):
        weights = section(self.points, [3], [1]*4, self.feature)
        self.assertAlmostEqual(sum(w*self.points[i, 0] for i, w in weights.items()), 3.)
        self.assertEqual(self.points[2, 0]-self.points[0, 0], 4.)

    def test_representative_choice_does_not_change_equation(self):
        a = section(self.points, [3], [1]*4, self.feature)
        b = section(self.points, [3], [1]*4, dict(self.feature, points=[1, 3]))
        self.assertEqual(a, b)

    def test_contour_start_and_direction_preserve_geometric_relation(self):
        original = section(self.points, [3], [1]*4, self.feature)
        for ids in ([2, 3, 0, 1], [3, 2, 1, 0]):
            changed = section(self.points[ids], [3], [1]*4, self.feature)
            self.assertEqual(original, {ids[i]: w for i, w in changed.items()})

    def test_ambiguous_duplicate_contours_are_held(self):
        with self.assertRaisesRegex(ValueError, 'support pairs'):
            section(np.vstack((self.points, self.points)), [3, 7], [1]*8, self.feature)

    def test_matrix_distance_and_ratio_semantics(self):
        graph = dict(constraints=[
            dict(point=0, normal=[1, 0], kind='Abs', sources=[], value=1.2),
            dict(point=0, normal=[0, 1], kind='Abs', sources=[], value=2.),
            dict(point=1, normal=[1, 0], kind='Dist', sources=[0], value=2.6),
            dict(point=1, normal=[0, 1], kind='Ratio', sources=[0, 0], value=.3)])
        matrix, rhs = system(graph, 2, 1)
        np.testing.assert_allclose(np.linalg.solve(matrix, rhs), [1, 2, 4, 2])

    def test_extent_dist_rows_round_outward(self):
        # Roboto-16 I cap: the joint system's hard extent rows must ceil
        # like every other solver, or the joint fit silently undoes the
        # geometric cap.
        graph = dict(constraints=[
            dict(point=0, normal=[1, 0], kind='Abs', sources=[], value=376.,
                 round=False),
            dict(point=0, normal=[0, 1], kind='Abs', sources=[], value=0.,
                 metric=True, metric_role='glyph-y-bound'),
            dict(point=1, normal=[1, 0], kind='Abs', sources=[], value=376.,
                 round=False),
            dict(point=1, normal=[0, 1], kind='Dist', sources=[0],
                 value=1456., metric=True, metric_role='glyph-y-bound')])
        matrix, rhs = system(graph, 2, 16 / 2048)
        solution = np.linalg.solve(matrix, rhs)
        self.assertEqual(solution[1], 0.0)
        self.assertEqual(solution[3], 12.0)


if __name__ == '__main__':
    unittest.main()
