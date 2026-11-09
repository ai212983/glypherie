"""Analytic geometry and independent wall/contact oracles, not optical acceptance."""

from dataclasses import FrozenInstanceError
import math
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import filtered_walls as f


def rectangle(x=0, y=0, width=3, height=4):
    return [dict(op="move_to", x=x, y=y), dict(op="line_to", x=x + width, y=y),
            dict(op="line_to", x=x + width, y=y + height),
            dict(op="line_to", x=x, y=y + height), dict(op="close")]


def bitmap(rows, left=0, top=0):
    return dict(left=left, top=top, width=len(rows[0]) if rows else 0,
                height=len(rows), pixels=[int(c) for row in rows for c in row])


def translated(commands, dx=0, dy=0, scale=1):
    return [{key: (value * scale + (dx if key.startswith("x") else dy)
                   if key in ("x", "y", "x1", "y1", "x2", "y2") else value)
             for key, value in command.items()} for command in commands]


class FilteredWallTests(unittest.TestCase):
    def test_rectangles_area_slope_and_source_bitmap_identity(self):
        source = f.source_profile(rectangle(), 1, (0, 4))
        produced = f.bitmap_profile(bitmap(["111"] * 4, top=-4), (0, 4))
        self.assertEqual(source, produced)
        self.assertEqual(source.bounds, f.Bounds(0, 0, 3, 4))
        self.assertEqual(f.pair_offset(source, source), -3)
        for step in (-2.25, 0, 5.5):
            mean_gap = step + f.pair_offset(source, source)
            self.assertEqual(mean_gap * 4, step * 4 - 12)
        self.assertEqual(f.shared_ink_rows(source, produced), 256)
        with self.assertRaises(FrozenInstanceError):
            source.window = (0, 3)

    def test_linear_filter_matches_independent_quadratic_time_oracle(self):
        rng = random.Random(384)
        for length in (1, 2, 7, 32, 97):
            left = [rng.uniform(-12, 12) for _ in range(length)]
            right = [rng.uniform(-12, 12) for _ in range(length)]
            for dy in (0.125, 1, 2.5):
                actual_l, actual_r = f.filter_45(left, right, dy)
                for i in range(length):
                    self.assertAlmostEqual(actual_l[i], min(v + abs(i-j) * dy
                                                           for j, v in enumerate(left)))
                    self.assertAlmostEqual(actual_r[i], max(v - abs(i-j) * dy
                                                           for j, v in enumerate(right)))

    def test_unit_slope_cavities_and_empty_middle_row(self):
        p = f.bitmap_profile(bitmap(["11111", "10001", "00000", "10001", "11111"]),
                             (-5, 0), samples_per_px=1)
        self.assertEqual(p.left, (0, 0, 5, 0, 0))
        self.assertEqual(p.right, (5, 5, 0, 5, 5))
        self.assertEqual(p.occupied, (True, True, False, True, True))
        self.assertEqual(p.filtered_left, (0, 0, 1, 0, 0))
        self.assertEqual(p.filtered_right, (5, 5, 4, 5, 5))
        deep = f.bitmap_profile(bitmap(["11111", "10000", "10000", "10000", "11111"]),
                                (-5, 0), samples_per_px=1)
        shallow = f.bitmap_profile(bitmap(["11111", "11110", "11110", "11110", "11111"]),
                                   (-5, 0), samples_per_px=1)
        self.assertEqual(deep.filtered_right, (5, 4, 3, 4, 5))
        self.assertEqual(shallow.filtered_right, (5, 4, 4, 4, 5))

    def test_midpoint_full_cells_converge_beyond_row_center_filter(self):
        # Upper row protrudes to x=4, lower row only to x=1. In the continuous
        # cell envelope R(y)=4-distance(y,[-1,0]); lower-row mean is 3.5.
        b = bitmap(["1111", "1000"])
        coarse = f.bitmap_profile(b, (-2, 0), samples_per_px=1)
        fine = f.bitmap_profile(b, (-2, 0), samples_per_px=64)
        finer = f.bitmap_profile(b, (-2, 0), samples_per_px=128)
        self.assertEqual(coarse.filtered_right, (3, 4))
        expected_mean = (3.5 + 4) / 2
        errors = [abs(sum(p.filtered_right) / len(p.ys) - expected_mean)
                  for p in (coarse, fine, finer)]
        self.assertGreater(errors[0], errors[1])
        self.assertGreater(errors[1], errors[2])
        self.assertLess(errors[1], 1/64)

    def test_fixed_window_unequal_heights_preserves_missing_rows(self):
        short = f.source_profile(rectangle(width=2, height=2), 1, (0, 4), 1)
        tall = f.source_profile(rectangle(width=3, height=4), 1, (0, 4), 1)
        self.assertEqual(short.occupied, (True, True, False, False))
        self.assertEqual(short.left, (0, 0, 2, 2))
        self.assertEqual(short.right, (2, 2, 0, 0))
        self.assertEqual(f.shared_ink_rows(short, tall), 2)
        self.assertEqual(len(short.ys), len(tall.ys))
        with self.assertRaises(f.GeometryError):
            f.pair_offset(short, f.source_profile(rectangle(), 1, (0, 3), 1))

    def test_quadratic_bounds_intersections_and_reversal(self):
        q = [dict(op="move_to", x=0, y=0),
             dict(op="quad_to", x1=4, y1=2, x=0, y=4), dict(op="close")]
        reversed_q = [dict(op="move_to", x=0, y=4),
                      dict(op="quad_to", x1=4, y1=2, x=0, y=0), dict(op="close")]
        self.assertEqual(f.source_bounds(q), f.Bounds(0, 0, 2, 4))
        p = f.source_profile(q, 1, (0, 4), 8)
        reverse = f.source_profile(reversed_q, 1, (0, 4), 8)
        for y, l, r, rev in zip(p.ys, p.left, p.right, reverse.right):
            self.assertEqual(l, 0)
            t = y / 4
            self.assertAlmostEqual(r, 8*t*(1-t), places=13)
            self.assertAlmostEqual(r, rev, places=13)

    def test_cubic_internal_extrema_translations_and_scale(self):
        cubic = [dict(op="move_to", x=0, y=0),
                 dict(op="curve_to", x1=3, y1=4, x2=3, y2=4, x=0, y=0),
                 dict(op="close")]
        self.assertEqual(f.source_bounds(cubic), f.Bounds(0, 0, 2.25, 3))
        a = f.source_profile(cubic, 1, (0, 3), 8)
        # Both density and window are transformed, preserving physical samples.
        b = f.source_profile(translated(cubic, dx=-7, dy=11, scale=2),
                             1, (11, 17), 4)
        c = f.source_profile(cubic, 2, (0, 6), 4)
        for la, ra, lb, rb, lc, rc in zip(a.left, a.right, b.left, b.right,
                                        c.left, c.right):
            self.assertAlmostEqual(lb, 2*la - 7)
            self.assertAlmostEqual(rb, 2*ra - 7)
            self.assertAlmostEqual(lc, 2*la)
            self.assertAlmostEqual(rc, 2*ra)
        for aa, bb in zip(a.filtered_right, b.filtered_right):
            self.assertAlmostEqual(bb, 2*aa - 7)

    def test_cubic_both_branches_at_internal_y_extremum(self):
        arch = [dict(op="move_to", x=0, y=0),
                dict(op="curve_to", x1=0, y1=4, x2=3, y2=4, x=3, y=0),
                dict(op="close")]
        self.assertEqual(f.source_bounds(arch), f.Bounds(0, 0, 3, 3))
        profile = f.source_profile(arch, 1, (0, 3), 32)
        for y, left, right in zip(profile.ys, profile.left, profile.right):
            t = (1 - math.sqrt(1 - y/3)) / 2
            expected_left = 9*t*t - 6*t*t*t
            self.assertAlmostEqual(left, expected_left, places=12)
            self.assertAlmostEqual(right, 3-expected_left, places=12)

    def test_clearance_diagonal_contact_and_disjoint_rows(self):
        left = bitmap(["1"], top=0)
        right = bitmap(["1"], top=1)
        # No shared occupied scanline; closed cells nevertheless touch at y=-1.
        self.assertEqual(f.clearance_min_step(left, right), 2)
        self.assertIsNone(f.clearance_min_step(left, bitmap(["1"], top=2)))
        self.assertIsNone(f.clearance_min_step(left, bitmap(["0"])))
        # A window-local measurement must not hide touching ink elsewhere.
        far_left = bitmap(["1", "0", "0", "1"], top=-4)
        far_right = bitmap(["1"], top=0)
        self.assertEqual(f.clearance_min_step(far_left, far_right), 2)

    def test_clearance_brute_force_closed_cells_oracle(self):
        rng = random.Random(412)
        for _ in range(80):
            left = bitmap(["".join(str(rng.randrange(2)) for _ in range(4))
                           for _ in range(3)], left=rng.randrange(-2, 3), top=-2)
            right = bitmap(["".join(str(rng.randrange(2)) for _ in range(4))
                            for _ in range(3)], left=rng.randrange(-2, 3), top=-1)
            def cells(b):
                return [(b["left"] + col, b["top"] + row)
                        for row in range(b["height"]) for col in range(b["width"])
                        if b["pixels"][row*b["width"] + col]]
            lc, rc = cells(left), cells(right)
            bound = f.clearance_min_step(left, right)
            relevant = [(a, b) for a in lc for b in rc if abs(a[1]-b[1]) <= 1]
            oracle = max((a[0]+1-b[0]+1 for a, b in relevant), default=None)
            self.assertEqual(bound, oracle)
            if bound is not None:
                def touch(step):
                    return any(abs(a[0]-b[0]-step) <= 1 and abs(a[1]-b[1]) <= 1
                               for a in lc for b in rc)
                self.assertFalse(touch(bound))
                self.assertTrue(touch(bound - 1))

    def test_no_overlap_clearance_allows_face_corner_and_vertical_contact(self):
        left = bitmap(["1"])
        self.assertEqual(f.clearance_min_step_no_overlap(left, left), 1)
        # No common row: vertical faces or diagonal corners may meet freely.
        self.assertIsNone(f.clearance_min_step_no_overlap(left, bitmap(["1"], top=1)))
        self.assertIsNone(f.clearance_min_step_no_overlap(left, bitmap(["0"])))
        # A hollow row has other disjoint placements, but the monotonic bound
        # deliberately keeps the second glyph beyond the exterior wall.
        self.assertEqual(f.clearance_min_step_no_overlap(bitmap(["1001"]), left), 4)

    def test_no_overlap_bound_matches_independent_cells_and_translation(self):
        rng = random.Random(913)
        for _ in range(80):
            left = bitmap(["".join(str(rng.randrange(2)) for _ in range(5)) for _ in range(4)],
                          left=rng.randrange(-3, 4), top=-3)
            right = bitmap(["".join(str(rng.randrange(2)) for _ in range(4)) for _ in range(3)],
                           left=rng.randrange(-3, 4), top=-2)
            def cells(b):
                return {(b["left"] + col, b["top"] + row)
                        for row in range(b["height"]) for col in range(b["width"])
                        if b["pixels"][row*b["width"] + col]}
            a, b = cells(left), cells(right)
            expected = max((x + 1 - xx for x, y in a for xx, yy in b if y == yy), default=None)
            bound = f.clearance_min_step_no_overlap(left, right)
            self.assertEqual(bound, expected)
            if bound is not None:
                self.assertFalse(a & {(x + bound, y) for x, y in b})
                self.assertTrue(a & {(x + bound - 1, y) for x, y in b})
                self.assertEqual(f.clearance_min_step_no_overlap(dict(left, left=left["left"] + 7), right), bound + 7)
                self.assertEqual(f.clearance_min_step_no_overlap(left, dict(right, left=right["left"] + 7)), bound - 7)

    def test_empty_geometry_and_invalid_or_excessive_input(self):
        empty = f.source_profile([], 1, (0, 1))
        self.assertIsNone(empty.bounds)
        self.assertFalse(any(empty.occupied))
        self.assertIsNone(f.source_bounds([dict(op="move_to", x=1, y=2)]))
        with self.assertRaises(f.GeometryError):
            f.pair_offset(empty, empty)
        for args in (((0, 0), 64), ((1, 0), 64), ((0, math.inf), 64),
                     ((0, 1), 0), ((0, 1), True)):
            with self.assertRaises(f.GeometryError):
                f.source_profile([], 1, *args)
        with self.assertRaises(f.WorkLimitExceeded):
            f.source_profile([], 1, (0, 129))
        for bad in (dict(bitmap(["1"]), left=0.5),
                    dict(bitmap(["1"]), pixels=[True]),
                    dict(bitmap(["1"]), pixels=[])):
            with self.assertRaises(f.GeometryError):
                f.bitmap_profile(bad, (0, 1))
        with self.assertRaises(f.GeometryError):
            f.source_bounds([dict(op="line_to", x=1, y=2)])
        with self.assertRaises(f.UnsupportedGeometry):
            f.source_profile([], 1, (1e15, 1e15+1))
        with patch.object(f, "MAX_SCANLINE_VISITS", 1):
            with self.assertRaises(f.WorkLimitExceeded):
                f.source_profile(rectangle(), 1, (0, 4))
        with patch.object(f, "MAX_BITMAP_PIXELS", 1):
            with self.assertRaises(f.WorkLimitExceeded):
                f.bitmap_profile(bitmap(["11"]), (0, 1))


if __name__ == "__main__":
    unittest.main()
