import unittest
import numpy as np
from shamir_baseline_completion import complete_defaults


class ContourCompletionTests(unittest.TestCase):
    def complete(self, points, references, contours, chosen=None):
        chosen = {} if chosen is None else chosen
        complete_defaults(np.asarray(points, float), chosen, references, 100, contours)
        return chosen

    def test_contour_neighbors_win_over_geometrically_nearer_remote_points(self):
        result = self.complete([[0,0], [5,4], [10,10], [4,3], [6,5]],
                               [0,2,3,4], [[0,1,2], [3,4]])
        self.assertEqual(result[1][0]['sources'], [0,2])
        self.assertEqual(result[1][0]['value'], .5)

    def test_neighbors_follow_contour_order_including_wrap(self):
        result = self.complete([[5,5], [10,10], [20,20], [0,0]],
                               [1,3], [[0,1,2,3]])
        self.assertEqual(result[0][0]['sources'], [3,1])
        self.assertEqual(result[2][0]['sources'], [1,3])
        self.assertEqual(result[2][0]['value'], -1)

    def test_zero_span_and_single_reference_preserve_signed_offset(self):
        result = self.complete([[2,0], [5,5], [2,10]], [0,2], [[0,1,2]])
        self.assertEqual(result[1][0]['kind'], 'Dist')
        self.assertEqual(result[1][0]['sources'], [0])
        self.assertEqual(result[1][0]['value'], 3)
        result = self.complete([[2,0], [5,5]], [0], [[0,1]])
        self.assertEqual(result[1][0]['default_reason'], 'single contour reference')

    def test_no_reference_contour_remains_independent(self):
        result = self.complete([[0,0], [5,5], [10,10]], [0], [[0], [1,2]])
        self.assertEqual(result[1][0]['kind'], 'Abs')
        self.assertEqual(result[1][0]['sources'], [])
        self.assertEqual(result[1][0]['value'], 5)

    def test_one_constraint_uses_orthogonal_projected_ratio(self):
        c = {'normal': [1.,0.]}
        result = self.complete([[0,0], [7,5], [10,10]], [0,2],
                               [[0,1,2]], {1:[c]})
        self.assertEqual(result[1][1]['normal'], [-0.,1.])
        self.assertEqual(result[1][1]['value'], .5)

    def test_contour_partition_must_cover_each_point_once(self):
        for contours in ([[0]], [[0,1],[1]], [[0,2]]):
            with self.assertRaises(ValueError):
                self.complete([[0,0],[1,1]], [0], contours)


if __name__ == '__main__':
    unittest.main()
