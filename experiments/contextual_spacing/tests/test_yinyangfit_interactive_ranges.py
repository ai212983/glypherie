"""Focused guards for the Class-L settings policy (v3 ranges).

Validates the navigation contract the staged page enforces: exact
finite targets >= 0 with no clamp/snap (including zero and off-grid
values), rejection of non-finite/negative/overflow input, integer
reach in [1, 32], falloff in [0.25, 16], and the TIE-v2 mirror.
"""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yinyangfit_interactive_v3_ranges import (
    FALLOFF_BOUNDS,
    REACH_BOUNDS,
    TARGET_MIN,
    TARGET_SPOT_GRID,
    TARGETS,
    default_controls,
    default_indexes,
    is_fast_geometry,
    make_controls,
    tie_pick,
    validate_numeric,
)


class TargetNumericTest(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(len(TARGETS), 1001)
        self.assertEqual(TARGETS[0], 0.0)
        self.assertEqual(TARGETS[-1], 20.0)
        self.assertAlmostEqual(TARGETS[1] - TARGETS[0], 0.02)
        self.assertEqual(TARGET_SPOT_GRID, [0.0, 1.0, 4.0, 8.0,
                                            12.0, 16.0, 20.0])

    def test_default_is_staged_start(self):
        self.assertEqual(default_controls(),
                         {"target": 8.0, "reach": 12, "falloff": 2.0})
        self.assertEqual(default_indexes(),
                         (TARGETS.index(8.0), 8, 3))

    def test_exact_values_preserved(self):
        # Navigation precision only: off-slider and off-grid values are
        # accepted exactly, never snapped to the 0.02 grid.
        for value in (0.0, 8.0, 8.02, 0.47, 17.59, 20.0, 34.26, 1e308):
            ok, _ = validate_numeric(value, 12, 2.0)
            self.assertTrue(ok, value)
            self.assertEqual(make_controls(value, 12, 2.0)["target"],
                             float(value))

    def test_rejections(self):
        for bad in (-0.5, -1e-9, float("inf"), float("-inf"),
                    float("nan")):
            ok, message = validate_numeric(bad, 12, 2.0)
            self.assertFalse(ok, bad)
            self.assertIn("target", message)
        # Overflow to infinity is rejected as non-finite.
        ok, _ = validate_numeric(1e308 * 10, 12, 2.0)
        self.assertFalse(ok)
        # Non-numbers rejected.
        for bad in ("8", None, True):
            ok, _ = validate_numeric(bad, 12, 2.0)
            self.assertFalse(ok, bad)

    def test_reach_integer_bounds(self):
        ok, _ = validate_numeric(8.0, 4, 2.0)
        self.assertTrue(ok)
        for bad in (3.5, 12.5, 0, 33, 64):
            ok, _ = validate_numeric(8.0, bad, 2.0)
            self.assertFalse(ok, bad)

    def test_falloff_bounds(self):
        ok, _ = validate_numeric(8.0, 12, 0.25)
        self.assertTrue(ok)
        ok, _ = validate_numeric(8.0, 12, 16.0)
        self.assertTrue(ok)
        for bad in (0.24, 16.01, float("nan")):
            ok, _ = validate_numeric(8.0, 12, bad)
            self.assertFalse(ok, bad)

    def test_target_min(self):
        self.assertEqual(TARGET_MIN, 0.0)
        self.assertEqual(REACH_BOUNDS, (1, 32))
        self.assertEqual(FALLOFF_BOUNDS, (0.25, 16.0))

    def test_fast_geometry_only_at_defaults(self):
        self.assertTrue(is_fast_geometry(12, 2.0))
        self.assertFalse(is_fast_geometry(13, 2.0))
        self.assertFalse(is_fast_geometry(12, 2.5))


class TiePickTest(unittest.TestCase):
    def test_lowest_step_wins(self):
        chosen, members, fallback = tie_pick([1.0, 1.0, 2.0], [4, 5, 6],
                                             99)
        self.assertFalse(fallback)
        self.assertEqual(chosen, 4)
        self.assertEqual(members, [4, 5])

    def test_abstained_never_wins(self):
        chosen, _, fallback = tie_pick([None, 0.0], [4, 5], 0)
        self.assertFalse(fallback)
        self.assertEqual(chosen, 5)

    def test_empty_falls_back(self):
        chosen, _, fallback = tie_pick([None, None], [4, 5], 9)
        self.assertTrue(fallback)
        self.assertEqual(chosen, 9)

    def test_tolerance_scales(self):
        # Within m* + 1e-9*max(1, m*) joins the set, however large m*.
        chosen, members, _ = tie_pick([100.0, 100.0 + 5e-8],
                                      [4, 5], 0)
        self.assertEqual(members, [4, 5])
        self.assertEqual(chosen, 4)


if __name__ == "__main__":
    unittest.main()
