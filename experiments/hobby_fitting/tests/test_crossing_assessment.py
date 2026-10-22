"""Analytic controls for diagnostic cross-sections, independent of fitted fonts."""

import unittest

from experiments.hobby_fitting.crossing_assessment import describe, profiles, section


def polygon(points):
    return [dict(op='move_to' if i == 0 else 'line_to', x=x, y=y)
            for i, (x, y) in enumerate(points)] + [dict(op='close')]


class CrossingAssessmentTests(unittest.TestCase):
    def test_sloping_bands_keep_unequal_projected_widths(self):
        commands = polygon([(0, 0), (2, 0), (4, 8), (2, 8)])
        commands += polygon([(9, 0), (10, 0), (8, 8), (7, 8)])
        self.assertEqual(section(commands, 4), [[1, 3], [8, 9]])
        self.assertEqual(describe(section(commands, 4))['ratio'], 2)

    def test_reflection_swaps_width_ratio(self):
        commands = polygon([(0, 0), (2, 0), (4, 8), (2, 8)])
        commands += polygon([(9, 0), (10, 0), (8, 8), (7, 8)])
        reflected = [dict(c, x=10-c['x']) if 'x' in c else c for c in commands]
        self.assertEqual(describe(section(reflected, 4))['ratio'], .5)

    def test_contour_reversal_preserves_nonzero_spans(self):
        points = [(0, 0), (2, 0), (4, 8), (2, 8)]
        self.assertEqual(section(polygon(points), 3), section(polygon(points[::-1]), 3))

    def test_horizontal_boundary_uses_half_open_y_intervals(self):
        commands = polygon([(0, 0), (2, 0), (2, 8), (0, 8)])
        self.assertEqual(section(commands, 8), [])
        self.assertEqual(section(commands, 0), [[0, 2]])

    def test_quadratic_extremum_does_not_leave_open_winding(self):
        commands = [dict(op='move_to', x=0, y=0),
                    dict(op='quad_to', x1=2, y1=8, x=4, y=0), dict(op='close')]
        self.assertEqual(section(commands, 4), [])
        self.assertEqual(section(commands, 3), [[1, 3]])

    def test_quadratic_section_has_analytic_boundary(self):
        commands = [dict(op='move_to', x=0, y=0), dict(op='line_to', x=2, y=0),
                    dict(op='quad_to', x1=6, y1=4, x=2, y=8),
                    dict(op='line_to', x=0, y=8), dict(op='close')]
        self.assertEqual(section(commands, 4), [[0, 4]])

    def test_crossing_union_is_not_two_independent_arms(self):
        commands = polygon([(0, 0), (1, 0), (9, 8), (8, 8)])
        commands += polygon([(8, 0), (9, 0), (1, 8), (0, 8)])
        result = describe(section(commands, 4))
        self.assertEqual(result['spans'], [[4, 5]])
        self.assertNotIn('ratio', result)

    def test_scaled_geometry_retains_ratios_at_normalized_heights(self):
        commands = polygon([(0, 0), (2, 0), (4, 8), (2, 8)])
        commands += polygon([(9, 0), (10, 0), (8, 8), (7, 8)])
        scaled = [{k: v*3 if k in ('x', 'y') else v for k, v in c.items()} for c in commands]
        for a, b in zip(profiles(commands), profiles(scaled)):
            self.assertAlmostEqual(a['geometry']['ratio'], b['geometry']['ratio'])
            self.assertAlmostEqual(a['geometry']['gap']*3, b['geometry']['gap'])
