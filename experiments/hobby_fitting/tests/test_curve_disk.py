import unittest
from fractions import Fraction as F

from experiments.hobby_fitting import curve_contacts, curved_width


class CurveDiskTests(unittest.TestCase):
    def test_quadratic_tangency_and_interior_penetration(self):
        center = (F(0), F(0))
        tangent = [(F(-2), F(1)), (F(0), F(1)), (F(2), F(1))]
        crossing = [(F(-2), F(2)), (F(0), F(-2)), (F(2), F(2))]
        self.assertTrue(curve_contacts._quad_disk_clear(center, F(1), tangent))
        self.assertFalse(curve_contacts._quad_disk_clear(center, F(1), crossing))

    def test_segment_interior_distance_compares_radius(self):
        center = (F(0), F(3, 5))
        radius = F(3, 5)
        for height, clear in [(F(1, 2), False), (F(0), True), (F(-1), True)]:
            segment = ((F(-1), height), (F(1), height))
            with self.subTest(height=height):
                self.assertEqual(curve_contacts._seg_clear(
                    center, radius ** 2, *segment), clear)
                self.assertEqual(curved_width._seg_open_clear(
                    center, radius, segment), clear)

    def test_quad_clears_where_triangle_hull_abstains(self):
        # Control vertex on the disk boundary: the hull edge meets the
        # open disk at its endpoint, so the triangle certificate abstains
        # while the quartic Bernstein certificate clears. Sampled minimum
        # distance squared is 0.25 against r^2 0.16: genuinely clear.
        center = (F(0), F(0))
        ctrl = ((F(-2), F(1)), (F(0), F(0)), (F(2), F(1)))
        self.assertFalse(curve_contacts._tri_clear(
            center, F(2, 5) ** 2, ctrl))
        self.assertTrue(curve_contacts._quad_disk_clear(
            center, F(2, 5) ** 2, ctrl))

    def test_quad_clears_with_center_inside_control_triangle(self):
        # Disk center strictly inside the control triangle forces hull
        # abstention (center-outside test), yet the curve stays clear:
        # sampled minimum distance squared is ~0.392 against r^2 0.25.
        center = (F(0), F(0))
        ctrl = ((F(-2), F(1)), (F(2), F(1)), (F(0), F(-1)))
        self.assertFalse(curve_contacts._tri_clear(
            center, F(1, 2) ** 2, ctrl))
        self.assertTrue(curve_contacts._quad_disk_clear(
            center, F(1, 2) ** 2, ctrl))

    def test_crossing_segment_rejected_under_rigid_transforms(self):
        for dx, dy in [(F(0), F(0)), (F(100), F(-200))]:
            for scale in [F(1, 8), F(1), F(32)]:
                center = (dx, dy + scale * F(3, 5))
                radius = scale * F(3, 5)
                segment = ((dx - scale, dy + scale / 2),
                           (dx + scale, dy + scale / 2))
                self.assertFalse(curve_contacts._seg_clear(
                    center, radius ** 2, *segment))
                self.assertFalse(curved_width._seg_open_clear(
                    center, radius, segment))


if __name__ == '__main__':
    unittest.main()
