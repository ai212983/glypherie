"""Geometric evidence for the research prototype, not optical acceptance."""

import math
import unittest

import numpy as np
from numpy.testing import assert_allclose

from experiments.hobby_fitting.prototype import (Sample, System, counter_system, curved_system,
                                                  straight_demo, strip_area, strip_pixel, width_weight)


class GeometryTests(unittest.TestCase):
    def test_integrated_normal_displacement_matches_exact_polynomial(self):
        # Independent integral of linear endpoint distances, Hobby (1).
        system = System([(0, 0), (3, 4)], 14)
        system.edge(0, 1)
        normal = np.array([-4/5, 3/5])
        delta = np.array([normal*0.2, normal*-0.3]).ravel()
        measured = sum((row@delta+c)**2 for group, row, c in system.rows
                       if group == 'position')
        expected = 1000/14**3 * 5 * (0.2**2 + 0.2*-0.3 + (-0.3)**2)/3
        self.assertAlmostEqual(measured, expected)

    def test_stretch_and_bend_are_resolved_in_original_edge_frame(self):
        system = System([(0, 0), (0, 4)], 14)
        system.edge(0, 1)
        delta = np.array([0, 0, 0.8, 0.4])
        costs = {g: (r@delta+c)**2 for g, r, c in system.rows if g != 'position'}
        self.assertAlmostEqual(costs['stretch'], 25/14*4*0.1**2)
        self.assertAlmostEqual(costs['bend'], 25/14*4*0.2**2)

    def test_relative_error_preserves_intended_thick_thin_ratio(self):
        system = System([(0, 0), (1, 0), (3, 0), (5, 0)], 14)
        first = system.pair(Sample.vertex(1), Sample.vertex(0), 1)
        second = system.pair(Sample.vertex(3), Sample.vertex(2), 1)
        system.match_width(first, second)
        # Both widths shrink by 20%; equal pixel widths are not required.
        delta = np.array([0, 0, -0.2, 0, 0, 0, -0.4, 0])
        self.assertAlmostEqual(first.error@delta, 0.2)
        self.assertAlmostEqual(second.error@delta, 0.2)
        self.assertAlmostEqual(system.rows[0][1]@delta, 0)

    def test_width_is_twice_radius_not_contact_chord(self):
        system = System([(0, 0), (1, 0)], 14)
        pair = system.pair(Sample.vertex(0), Sample.vertex(1), 1, medial=(0.5, 1))
        self.assertAlmostEqual(pair.width, math.sqrt(5))
        self.assertNotAlmostEqual(pair.width, np.linalg.norm(pair.chord))

    @staticmethod
    def coupled(angle=0, translation=(0, 0), scale=1, matching=True):
        rotation = np.array([[math.cos(angle), -math.sin(angle)],
                             [math.sin(angle), math.cos(angle)]])
        points = np.array([(0, 0), (0, 8), (1.2, 0), (1.2, 8),
                           (3, 0), (3, 8), (4.2, 0), (4.2, 8)])
        system = System(scale*(points@rotation.T)+translation, 14*scale)
        for i in (0, 2, 4, 6):
            system.edge(i, i+1)
        pairs = [system.pair(Sample.vertex(i+2), Sample.vertex(i), 8*scale)
                 for i in (0, 4)]
        for pair in pairs:
            system.preserve_width(pair)
        if matching:
            # Unit-rescaling control, not a new width-selection policy.
            system.match_width(*pairs, width_scale=0.7*scale)
        # Supplied external geometric constraint drives a 20% narrowing. It is
        # deliberately not an automatically selected integer grid target.
        system.add('experiment-drive', 100*pairs[0].error, -20)
        return system, pairs, rotation

    def test_coupling_reduces_unequal_width_change(self):
        errors = []
        for matching in (False, True):
            system, pairs, _ = self.coupled(matching=matching)
            result = system.solve()
            errors.append(abs((pairs[0].error-pairs[1].error)@result['delta']))
        self.assertLess(errors[1], errors[0]/2)

    def test_translation_rotation_and_unit_rescaling_of_geometric_system(self):
        base, _, _ = self.coupled()
        expected = base.solve()['delta'].reshape(-1, 2)
        for angle in (0, math.pi/4, math.atan2(2, 7), math.pi/2):
            for scale in (0.5, 1, 3):
                system, _, rotation = self.coupled(angle, (2.3, -4.7), scale)
                actual = system.solve()['delta'].reshape(-1, 2)
                assert_allclose(actual, scale*expected@rotation.T, atol=2e-12)

    def test_fixed_integer_offsets_use_projection_at_each_orientation(self):
        # Integer-grid fitting itself is not invariant under arbitrary rotation.
        for angle in (0, math.pi/6, math.pi/4, math.atan2(2, 7)):
            result = straight_demo(angle)
            offset = -np.array(result['supplied_offset'])
            normal = np.array([math.cos(angle), math.sin(angle)])
            self.assertAlmostEqual(result['projected_widths'][0], normal@offset, places=4)
            self.assertGreater(result['squared_residuals']['offset-width'], 0)

    def test_printed_orientation_weight_is_weak(self):
        parallel = width_weight(1, 1, (1, 0), (1, 0), 14)
        perpendicular = width_weight(1, 1, (1, 0), (0, 1), 14)
        self.assertAlmostEqual(perpendicular/parallel, math.exp(-(math.pi/18)**2))
        self.assertGreater(perpendicular/parallel, 0.96)

    def test_cubic_constant_normal_shift_matches_straight_integral(self):
        system = System([(0, 0), (0, 2), (0, 4), (0, 6)], 14)
        system.curve(range(4), intervals=16)
        delta = np.tile([0.3, 0], 4)
        measured = sum((row@delta+c)**2 for _, row, c in system.rows)
        self.assertAlmostEqual(measured, 1000/14**3 * 6 * 0.3**2)

    def test_cubic_strain_agrees_with_straight_edge_strain(self):
        # The derivative extension of (2),(3) must reduce to the original
        # formula for a linear cubic. This tests the project adaptation.
        system = System([(0, 0), (0, 2), (0, 4), (0, 6)], 14)
        system.curve(range(4))
        delta = np.array([(0.2*y, 0.1*y) for y in (0, 2, 4, 6)]).ravel()
        costs = {g: sum((r@delta+c)**2 for group, r, c in system.rows if group == g)
                 for g in ('curve-stretch', 'curve-bend')}
        self.assertAlmostEqual(costs['curve-stretch'], 25/14*6*0.1**2)
        self.assertAlmostEqual(costs['curve-bend'], 25/14*6*0.2**2)

    def test_normal_only_curve_fit_exposes_missing_shape_control(self):
        # A negative control prevents quietly treating (33) alone as a
        # complete curve fit. No production movement tolerance is invented.
        normal_only, _ = curved_system(shape=False)
        complete, _ = curved_system(shape=True)
        first, second = normal_only.solve(), complete.solve()
        self.assertLess(first['rank'], first['free_variables'])
        self.assertEqual(second['rank'], second['free_variables'])
        self.assertLess(second['max_movement'], first['max_movement']/10)

    def test_midpoint_curve_quadrature_converges(self):
        costs = []
        for intervals in (8, 32, 256):
            system = System([(0, 0), (1, 2), (3, 2), (4, 0)], 14)
            system.curve(range(4), intervals=intervals, shape=False)
            delta = np.tile([0.2, -0.1], 4)
            costs.append(sum((r@delta+c)**2 for _, r, c in system.rows))
        self.assertLess(abs(costs[1]-costs[2]), abs(costs[0]-costs[2])/8)

    def test_curve_shape_control_retains_supplied_width_adjustment(self):
        # Identical supplied targets: the shape adaptation must not achieve
        # small travel just by refusing the requested narrowing.
        widths = []
        for shape in (False, True):
            system, pairs = curved_system(shape=shape)
            result = system.solve()
            pair = pairs[0]
            width = pair.normal@pair.chord - pair.width*(pair.error@result['delta'])
            target = pair.normal@np.array([1, 0])
            self.assertAlmostEqual(width, target, places=4)
            widths.append(width)
            if shape:
                # Small-motion regime of this fixture, not a universal
                # pixel tolerance or a proposed production guard.
                self.assertLess(result['max_movement'], pair.width/2)
        self.assertAlmostEqual(*widths, places=4)

    def test_curved_coefficients_are_fixed_linear_forms(self):
        system, _ = curved_system()
        a = np.linspace(-0.1, 0.2, system.points.size)
        b = np.linspace(0.3, -0.2, system.points.size)
        curve_rows = [r for g, r, _ in system.rows if g == 'curve-position']
        for row in curve_rows:
            self.assertAlmostEqual(row@(a+b), row@a+row@b)
        result = system.solve()
        self.assertTrue(np.isfinite(result['points']).all())
        self.assertGreater(np.linalg.norm(result['delta']), 0)
        # Source-to-adjusted coordinate copies retain all original controls.
        self.assertEqual(result['points'].shape, (8, 2))

    def test_curved_system_rotates_and_translates_without_axis_special_cases(self):
        source, _ = curved_system()
        angle = math.atan2(3, 5)
        rotation = np.array([[math.cos(angle), -math.sin(angle)],
                             [math.sin(angle), math.cos(angle)]])
        changed = System(source.points@rotation.T + [3.2, -1.3], 14)
        # Only curved geometric residuals here: rotating an integer I would
        # leave the integer lattice, so remove grid rows from both systems.
        source.rows = [r for r in source.rows if not r[0].startswith('offset')]
        for i in (0, 4):
            changed.curve(range(i, i+4))
        displacement = np.tile([0.2, -0.3], 8).reshape(-1, 2)
        source_curves = [r for g, r, c in source.rows if g == 'curve-position']
        changed_curves = [r for g, r, c in changed.rows if g == 'curve-position']
        for first, second in zip(source_curves, changed_curves):
            self.assertAlmostEqual(first@displacement.ravel(),
                                   second@(displacement@rotation.T).ravel())

    def test_counter_and_ink_are_distinct_features_on_shared_walls(self):
        system, pairs = counter_system()
        result = system.solve()
        widths = [np.dot(p.normal, p.chord)-p.width*(p.error@result['delta']) for p in pairs]
        self.assertGreater(widths[2], 3)
        self.assertAlmostEqual(widths[0], widths[1])
        self.assertTrue(all(w > 0 for w in widths))
        self.assertIn('white-width', result['squared_residuals'])
        with self.assertRaises(ValueError):
            system.match_width(pairs[0], pairs[2])

    def test_t_junction_freezes_shared_vertex_without_fake_integer_success(self):
        # Caller owns the shared T vertex; this is input protection, not
        # automatic junction detection or proof of safe arbitrary movement.
        system = System([(0, 0), (-2, 0), (2, 0), (0, -4), (1.2, -4)], 14)
        for i, j in ((0, 1), (0, 2), (0, 3), (3, 4)):
            system.edge(i, j)
        pair = system.pair(Sample.vertex(4), Sample.vertex(3), 1)
        system.offset(pair, (-1, 0))
        result = system.solve(frozen=(0,))
        assert_allclose(result['points'][0], system.points[0], atol=0, rtol=0)
        self.assertTrue(np.isfinite(result['squared_residuals']['bend']))
        # An incompatible, completely frozen width remains an explicit error.
        frozen = system.solve(frozen=tuple(range(5)))
        self.assertGreater(frozen['squared_residuals']['offset-width'], 1000)
        self.assertEqual(frozen['max_movement'], 0)

    def test_counter_with_frozen_inner_wall_still_has_free_ink_adjustment(self):
        system, pairs = counter_system()
        result = system.solve(frozen=(4, 7))
        assert_allclose(result['points'][[4, 7]], system.points[[4, 7]], atol=0, rtol=0)
        widths = [p.normal@p.chord-p.width*(p.error@result['delta']) for p in pairs]
        self.assertAlmostEqual(widths[0], 1, places=4)
        self.assertAlmostEqual(widths[1], 1, places=4)
        self.assertGreater(widths[2], 3)

    def test_degenerate_feature_inputs_are_rejected(self):
        system = System([(0, 0), (0, 0)], 14)
        for operation in (lambda: system.edge(0, 1),
                          lambda: system.curve((0, 0, 0, 0)),
                          lambda: system.pair(Sample.vertex(0), Sample.vertex(1), 1),
                          lambda: system.point(Sample(((0, 0.5),))),
                          lambda: system.point(Sample.vertex(99))):
            with self.assertRaises(ValueError):
                operation()


class RasterControls(unittest.TestCase):
    def test_exact_clipping_known_vertical_and_diagonal_areas(self):
        self.assertAlmostEqual(strip_area((1, 0), 0.25, 0.75, 0, 0), 0.5)
        self.assertAlmostEqual(strip_area((1, 1), 0, 1, 0, 0), 0.5)
        self.assertAlmostEqual(strip_area((1, 1), 0, 2, 0, 0), 1)
        self.assertEqual(strip_area((1, 0), 2, 3, 0, 0), 0)

    def test_integer_offset_does_not_transfer_center_fill_guarantee_to_4x(self):
        # Width exactly one and integer offset, with a deterministic half-open
        # boundary convention. This is a model counterexample, not pixel tuning.
        pixels = [strip_pixel((1, 0), 0.5, 1.5, x, 0) for x in (0, 1)]
        self.assertEqual(sum(p['center_fill'] for p in pixels), 1)
        self.assertEqual(sum(p['analytic_4x_ink'] for p in pixels), 2)
        self.assertEqual([p['analytic_4x_coverage'] for p in pixels], [128, 128])
        self.assertEqual(sum(p['exact_area_threshold'] for p in pixels), 0)

    def test_analytic_area_is_conserved_across_cells_for_rational_diagonal(self):
        # Strip 0 <= x+y < 1 cuts unit triangles in the two cells in each
        # two-cell diagonal repeat: total area and center count both one.
        cells = [strip_pixel((1, 1), 0.2, 1.2, x, 0) for x in (-1, 0, 1)]
        self.assertAlmostEqual(sum(p['area'] for p in cells), 1)
        self.assertEqual(sum(p['center_fill'] for p in cells), 1)


class FixedDisplacementTests(unittest.TestCase):
    @staticmethod
    def two_stems():
        system = System([(0, 0), (2, 0), (0, 8), (2, 8)], 14)
        system.edge(0, 1)
        system.edge(2, 3)
        bottom = system.pair(Sample.vertex(0), Sample.vertex(1), 8)
        top = system.pair(Sample.vertex(2), Sample.vertex(3), 8)
        system.match_width(bottom, top)
        return system, bottom, top

    def test_fixed_rejects_nonfinite_bad_index_and_frozen_overlap(self):
        system, _, _ = self.two_stems()
        with self.assertRaises(ValueError):
            system.solve(fixed_displacements={0: (float('inf'), 0)})
        with self.assertRaises(ValueError):
            system.solve(fixed_displacements={0: (0, float('nan'))})
        with self.assertRaises(ValueError):
            system.solve(fixed_displacements={9: (0.1, 0)})
        with self.assertRaises(ValueError):
            system.solve(frozen=(0,), fixed_displacements={0: (0.1, 0)})

    def test_fixed_pins_vertex_and_transfers_known_narrowing(self):
        # Top pair fixed 20% narrower; the free pair follows the coupling.
        system, bottom, top = self.two_stems()
        assert_allclose(top.error @ np.zeros(8), 0.0, atol=1e-12)
        fixed = {2: (0.2, 0.0), 3: (-0.2, 0.0)}
        result = system.solve(fixed_displacements=fixed)
        delta = result['delta'].reshape(-1, 2)
        assert_allclose(delta[2], (0.2, 0.0), atol=1e-12)
        assert_allclose(delta[3], (-0.2, 0.0), atol=1e-12)
        moved = (np.asarray([(0, 0), (2, 0), (0, 8), (2, 8)]) + delta)
        bottom_width = moved[1][0] - moved[0][0]
        self.assertAlmostEqual(bottom_width, 1.6, delta=0.1)

    def test_fixed_translation_invariance(self):
        system, _, _ = self.two_stems()
        fixed = {2: (0.2, 0.0), 3: (-0.2, 0.0)}
        expected = system.solve(
            fixed_displacements=fixed)['delta'].reshape(-1, 2)
        shift = np.array([2.3, -4.7])
        moved = System((np.asarray([(0, 0), (2, 0), (0, 8), (2, 8)])
                        + shift).tolist(), 14)
        moved.edge(0, 1)
        moved.edge(2, 3)
        bottom = moved.pair(Sample.vertex(0), Sample.vertex(1), 8)
        top = moved.pair(Sample.vertex(2), Sample.vertex(3), 8)
        moved.match_width(bottom, top)
        actual = moved.solve(
            fixed_displacements=fixed)['delta'].reshape(-1, 2)
        assert_allclose(actual, expected, atol=1e-12)

    def test_fixed_rotation90_grid_preserving(self):
        # Quarter turns map the integer grid onto itself, unlike general
        # angles, so the coupled system rotates exactly with the input.
        system, _, _ = self.two_stems()
        fixed = {2: (0.2, 0.0), 3: (-0.2, 0.0)}
        expected = system.solve(
            fixed_displacements=fixed)['delta'].reshape(-1, 2)
        points = np.array([(0, 0), (2, 0), (0, 8), (2, 8)], dtype=float)
        rotation = np.array([[0, -1], [1, 0]])
        rotated = System((points@rotation.T).tolist(), 14)
        rotated.edge(0, 1)
        rotated.edge(2, 3)
        bottom = rotated.pair(Sample.vertex(0), Sample.vertex(1), 8)
        top = rotated.pair(Sample.vertex(2), Sample.vertex(3), 8)
        rotated.match_width(bottom, top)
        fixed_rot = {i: tuple(rotation@v)
                     for i, v in fixed.items()}
        actual = rotated.solve(
            fixed_displacements=fixed_rot)['delta'].reshape(-1, 2)
        assert_allclose(actual, expected@rotation.T, atol=1e-12)

    def test_fixed_scaled_units_with_explicit_quantum(self):
        # Doubling coordinates and H keeps relative errors; the 0.7 pixel
        # width scale is explicit, so it doubles too. Not a tuned gate.
        system, _, _ = self.two_stems()
        fixed = {2: (0.2, 0.0), 3: (-0.2, 0.0)}
        expected = system.solve(
            fixed_displacements=fixed)['delta'].reshape(-1, 2)
        points = 2 * np.array([(0, 0), (2, 0), (0, 8), (2, 8)], dtype=float)
        doubled = System(points.tolist(), 14 * 2)
        doubled.edge(0, 1)
        doubled.edge(2, 3)
        bottom = doubled.pair(Sample.vertex(0), Sample.vertex(1), 8 * 2)
        top = doubled.pair(Sample.vertex(2), Sample.vertex(3), 8 * 2)
        doubled.match_width(bottom, top, width_scale=0.7 * 2)
        fixed_doubled = {i: (2 * v[0], 2 * v[1]) for i, v in fixed.items()}
        actual = doubled.solve(
            fixed_displacements=fixed_doubled)['delta'].reshape(-1, 2)
        assert_allclose(actual, 2 * expected, atol=1e-9)


if __name__ == '__main__':
    unittest.main()
