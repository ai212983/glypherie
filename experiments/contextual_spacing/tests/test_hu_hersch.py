"""Analytic and independent mathematical tests; no optical-acceptance claim."""

from dataclasses import FrozenInstanceError
import math
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hu_hersch as h
import filtered_walls as f


def bitmap(rows, left=0, top=0):
    return dict(left=left, top=top, width=len(rows[0]) if rows else 0,
                height=len(rows), pixels=[int(c) for row in rows for c in row])


def rectangle(x=0, y=0, width=3, height=4):
    return [dict(op="move_to", x=x, y=y), dict(op="line_to", x=x + width, y=y),
            dict(op="line_to", x=x + width, y=y + height),
            dict(op="line_to", x=x, y=y + height), dict(op="close")]


def oval():
    # Joined quadratic endpoints at each outer x extremum have exact vertical
    # tangents. Reversing contour direction preserves classification.
    return [dict(op="move_to", x=0, y=2),
            dict(op="quad_to", x1=0, y1=4, x=2, y=4),
            dict(op="quad_to", x1=4, y1=4, x=4, y=2),
            dict(op="quad_to", x1=4, y1=0, x=2, y=0),
            dict(op="quad_to", x1=0, y1=0, x=0, y=2), dict(op="close")]


def pad(b, before_x=2, after_x=3, before_y=1, after_y=2):
    width = b["width"] + before_x + after_x
    rows = [[0] * width for _ in range(before_y)]
    for i in range(b["height"]):
        rows.append([0] * before_x + b["pixels"][i*b["width"]:(i+1)*b["width"]] + [0] * after_x)
    rows.extend([[0] * width for _ in range(after_y)])
    return dict(left=b["left"]-before_x, top=b["top"]-before_y, width=width,
                height=len(rows), pixels=[v for row in rows for v in row])


class HuHerschTests(unittest.TestCase):
    def test_full_construction_finds_c_apertures_on_the_post_b_contour(self):
        # US5768490A: C intersects the result of A+B. B removes the middle
        # lip here, so its two raw unit-height openings merge into one of 3.
        ys = tuple(i+.5 for i in range(7))
        right = (0., 0., 2., 0., 1., 0., 2.)
        raw = f.Profile(f.Bounds(-1, 0, 2, 7), (0, 7), ys, (-1.,)*7, right,
                        (True,)*7, (-1.,)*7, right)
        settings = h.Settings(.21, 10, 1)
        old = h._depth_profile(raw, settings)
        new = h._depth_profile(raw, settings, post_b_cavities=True)
        self.assertEqual(new.slope_right, (0., 0., 2., 1.5, 1., 1.5, 2.))
        self.assertEqual(old.filtered_right[4], 1.)
        self.assertAlmostEqual(new.filtered_right[4], 2-.21*3)
        self.assertEqual([c.opening_px for c in new.right_cavities], [3])

    def test_full_outline_construction_keeps_missing_lip_before_body_integral(self):
        # Continuous R(y)=3-2y+y²/2 has lips at y=0/4. Cropping at 3
        # invents a recessed endpoint lip; constructing first retains both.
        commands = [dict(op="move_to", x=-1, y=0), dict(op="line_to", x=3, y=0),
                    dict(op="quad_to", x1=-1, y1=2, x=3, y=4),
                    dict(op="line_to", x=-1, y=4), dict(op="close")]
        errors = []
        for density in (32, 64, 128, 256):
            settings = h.Settings(.21, 10, density)
            full = h.full_source_depth_profile(commands, 1, (0, 3), settings)
            legacy = h.source_depth_profile(commands, 1, (0, 3), settings)
            self.assertEqual(full.ys, legacy.ys)
            self.assertEqual(full.left, legacy.left)
            self.assertEqual(full.right, legacy.right)
            self.assertEqual(full.window, (0, 3))
            self.assertEqual(full.construction_window, (0, 4))
            self.assertGreater(full.filtered_right[-1], legacy.filtered_right[-1])
            # Each sampled lip is at dy/2, with its bay edge at dy.
            # R(dy/2)=3-dy+dy²/8; the aperture is 4-2dy.
            dy = 1/density
            sampled_cutoff = 3-dy+dy*dy/8 - .21*(4-2*dy)
            self.assertAlmostEqual(full.filtered_right[2*density], sampled_cutoff)
            errors.append(abs(full.filtered_right[2*density] - 2.16))
        self.assertLess(errors[-1], errors[0])
        self.assertLess(errors[-1], 1/256)

    def test_full_construction_keeps_body_height_in_d_and_preserves_grid_phase(self):
        # A tall monotone triangle has full right extreme x=10. Body height
        # 4 gives D cutoff 10-.25*4=9, not the full-height cutoff of 5.
        triangle = [dict(op="move_to", x=0, y=0), dict(op="line_to", x=10, y=20),
                    dict(op="line_to", x=0, y=20), dict(op="close")]
        profile = h.full_source_depth_profile(triangle, 1, (0, 4), h.Settings(.21, .25, 8))
        self.assertTrue(all(x == 9 for x in profile.filtered_right))
        self.assertEqual(profile.construction_window, (0, 20))
        window = (.13, 2.87)
        a = h.full_source_depth_profile(triangle, 1, window, h.Settings(.21, .25, 24))
        body = f.source_profile(triangle, 1, window, 24)
        self.assertEqual(a.ys, body.ys)
        moved = [{key: 3*value+(7 if key.startswith("x") else -5)
                  if key in ("x", "y", "x1", "y1", "x2", "y2") else value
                  for key, value in command.items()} for command in triangle]
        b = h.full_source_depth_profile(moved, 1, tuple(3*y-5 for y in window), h.Settings(.21, .25, 8))
        for left, right in zip(a.filtered_right, b.filtered_right):
            self.assertAlmostEqual(3*left+7, right)

    def test_full_construction_limits_do_not_silently_fall_back_to_cropped_walls(self):
        with self.assertRaisesRegex(f.WorkLimitExceeded, "full-outline construction"):
            h.full_source_depth_profile(rectangle(height=1000), 1, (0, 4), h.Settings(.21, .25, 64))
        empty = h.full_source_depth_profile([], 1, (0, 4), h.Settings(.21, .25))
        self.assertIsNone(empty.bounds)
        self.assertFalse(any(empty.occupied))
        with self.assertRaises(f.GeometryError):
            h.full_source_depth_profile(rectangle(), 1, (0, 4), None)

    def test_source_and_bitmap_rectangles_share_exact_profile_and_grid(self):
        settings = h.Settings(h.PUBLISHED_RELATIVE_DEPTH, h.PUBLISHED_VISUAL_DEPTH_FACTOR)
        source = h.source_depth_profile(rectangle(), 1, (0, 4), settings)
        delivered = h.depth_profile(bitmap(["111"]*4, top=-4), (0, 4), settings)
        self.assertEqual(source, delivered)
        self.assertEqual(h.pair_offset(source, delivered), -3)
        with patch.object(f, "bitmap_profile", side_effect=AssertionError("must not rasterize source")):
            self.assertEqual(h.source_depth_profile(rectangle(), 1, (0, 4), settings), source)

    def test_source_quadratic_raw_walls_are_continuous_and_global_cap_converges(self):
        commands = [dict(op="move_to", x=0, y=0),
                    dict(op="quad_to", x1=4, y1=2, x=0, y=4), dict(op="close")]
        expected_mean = 1+math.sqrt(2)/3
        errors = []
        for density in (8, 16, 32, 64, 128):
            p = h.source_depth_profile(commands, 1, (0, 4), h.Settings(.21, .25, density))
            for y, raw, filtered in zip(p.ys, p.right, p.filtered_right):
                self.assertAlmostEqual(raw, 2*y-y*y/2)
                self.assertAlmostEqual(filtered, max(1, raw))
            errors.append(abs(math.fsum(p.filtered_right)/len(p.ys)-expected_mean))
        self.assertLess(errors[-1], errors[0])
        self.assertLess(errors[-1], 1e-5)

    def test_source_bounded_cavity_sampling_converges_to_analytic_area(self):
        # R(y)=3-2*y+y*y/2: continuous lips at x=3,y=0/4, unit-slope
        # envelope 3-min(y,4-y), patent cutoff 3-.21*4=2.16. The midpoint
        # bay detector approximates the source lip positions as density grows.
        commands = [dict(op="move_to", x=0, y=0), dict(op="line_to", x=3, y=0),
                    dict(op="quad_to", x1=-1, y1=2, x=3, y=4),
                    dict(op="line_to", x=0, y=4), dict(op="close")]
        expected_mean = 2.16+.84*.84/4
        errors = []
        for density in (32, 64, 128, 256, 512):
            p = h.source_depth_profile(commands, 1, (0, 4), h.Settings(.21, .25, density))
            self.assertEqual(len(p.right_cavities), 1)
            self.assertTrue(all(a >= b for a, b in zip(p.filtered_right, p.right)))
            errors.append(abs(math.fsum(p.filtered_right)/len(p.ys)-expected_mean))
        self.assertLess(errors[-1], errors[0])
        self.assertLess(errors[-1], .003)

    def test_source_translation_scale_and_contour_direction(self):
        commands = oval()
        p = h.source_depth_profile(commands, 1, (0, 4), h.Settings(.21, .25, 32))
        transformed = [{key: value*2 + (7 if key.startswith("x") else -3)
                        if key in ("x", "y", "x1", "y1", "x2", "y2") else value
                        for key, value in command.items()} for command in commands]
        q = h.source_depth_profile(transformed, 1, (-3, 5), h.Settings(.21, .25, 16))
        for a, b in zip(p.filtered_left, q.filtered_left):
            self.assertAlmostEqual(b, 2*a+7)
        for a, b in zip(p.filtered_right, q.filtered_right):
            self.assertAlmostEqual(b, 2*a+7)
        forward = [dict(op="move_to", x=0, y=0),
                   dict(op="quad_to", x1=4, y1=2, x=0, y=4), dict(op="close")]
        reverse = [dict(op="move_to", x=0, y=4),
                   dict(op="quad_to", x1=4, y1=2, x=0, y=0), dict(op="close")]
        a = h.source_depth_profile(forward, 1, (0, 4), h.Settings(.21, .25))
        b = h.source_depth_profile(reverse, 1, (0, 4), h.Settings(.21, .25))
        for x, y in zip(a.filtered_right, b.filtered_right):
            self.assertAlmostEqual(x, y)

    def test_source_empty_invalid_and_work_limits(self):
        settings = h.Settings(.21, .25)
        p = h.source_depth_profile([], 1, (0, 4), settings)
        self.assertIsNone(p.bounds)
        self.assertFalse(any(p.occupied))
        for scale in (0, -1, math.inf, True):
            with self.assertRaises(f.GeometryError):
                h.source_depth_profile(rectangle(), scale, (0, 4), settings)
        with self.assertRaises(f.GeometryError):
            h.source_depth_profile(rectangle(), 1, (0, 4), None)
        with self.assertRaises(f.GeometryError):
            h.source_depth_profile([dict(op="move_to", x=math.nan, y=0)], 1, (0, 4), settings)
        with self.assertRaises(f.WorkLimitExceeded):
            h.source_depth_profile(rectangle(), 1, (0, 129), settings)
        with patch.object(f, "MAX_SCANLINE_VISITS", 1):
            with self.assertRaises(f.WorkLimitExceeded):
                h.source_depth_profile(rectangle(), 1, (0, 4), settings)

    def test_rectangles_have_exact_area_slope_and_immutable_profiles(self):
        p = h.depth_profile(bitmap(["111"] * 4, top=-4), (0, 4), h.Settings(.25, .5))
        self.assertEqual(p.filtered_left, (0,) * 256)
        self.assertEqual(p.filtered_right, (3,) * 256)
        self.assertEqual(p.left_cavities, ())
        self.assertEqual(p.right_cavities, ())
        self.assertEqual(h.pair_offset(p, p), -3)
        for step in (-2.5, 0, 5.125):
            self.assertEqual((step + h.pair_offset(p, p))*4, step*4-12)
        with self.assertRaises(FrozenInstanceError):
            p.window = (0, 3)

    def test_upper_hull_matches_independent_all_supporting_lines_oracle(self):
        rng = random.Random(4902)
        for length in (2, 3, 8, 21):
            xs = [rng.randrange(-7, 8) for _ in range(length)]
            hull = h._upper_hull(enumerate(xs))
            for i, raw in enumerate(xs):
                supporting = []
                for a in range(length):
                    for b in range(a+1, length):
                        line = lambda y: xs[a] + (y-a)*(xs[b]-xs[a])/(b-a)
                        if all(line(y) >= x - 1e-12 for y, x in enumerate(xs)):
                            supporting.append(line(i))
                expected = min(supporting)
                segment = next((a, b) for a, b in zip(hull, hull[1:]) if a[0] <= i <= b[0])
                a, b = segment
                actual = a[1] + (i-a[0])*(b[1]-a[1])/(b[0]-a[0])
                self.assertAlmostEqual(actual, expected)
                self.assertGreaterEqual(actual + 1e-12, raw)

    def test_aperture_uses_exact_cell_mouth_and_changes_with_opening(self):
        narrow = h.depth_profile(bitmap(["111111", "100000", "100000", "111111"], top=-4),
                                 (0, 4), h.Settings(.25, 10))
        wide = h.depth_profile(bitmap(["111111", "100000", "100000", "100000", "100000", "111111"], top=-6),
                               (0, 6), h.Settings(.25, 10))
        self.assertEqual([c.opening_px for c in narrow.right_cavities], [2])
        self.assertEqual([c.opening_px for c in wide.right_cavities], [4])
        self.assertEqual(narrow.right_cavities[0].aperture_depth_px, .5)
        self.assertEqual(wide.right_cavities[0].aperture_depth_px, 1)
        self.assertEqual(min(narrow.filtered_right), 5.5)
        self.assertEqual(min(wide.filtered_right), 5)
        # A depth cap is a lower bound on the outward wall, not subtraction
        # from the already 45-degree-smoothed wall.
        self.assertLess(min(wide.slope_right), min(wide.filtered_right))

    def test_global_depth_limits_diagonal_even_without_a_hull_cavity(self):
        b = bitmap(["1000", "1100", "1110", "1111"], top=-4)
        open_profile = h.depth_profile(b, (0, 4), h.Settings(10, 10))
        limited = h.depth_profile(b, (0, 4), h.Settings(10, .125))
        # Staircase cells can have tiny hull cavities, but the outermost first
        # row is on the hull. Its global clamp is independent of aperture cap.
        first_row = [i for i, y in enumerate(limited.ys) if y > 3]
        self.assertTrue(all(limited.filtered_right[i] >= 3.5 for i in first_row))
        self.assertLess(min(open_profile.filtered_right), min(limited.filtered_right))

    def test_bounded_concavity_filter_matches_independent_quadratic_oracle(self):
        b = bitmap(["11111", "11000", "10000", "00000", "11111"], top=-5)
        p = h.depth_profile(b, (0, 5), h.Settings(.2, .3, 8))
        # This single bounded bay has equal lips x=5 at y=1 and y=4.
        # Compare against all raw point cones plus exact cell-edge lip cones.
        for i, y in enumerate(p.ys):
            if 1 <= y <= 4:
                slope = max(5-abs(y-1), 5-abs(y-4),
                            *(x-abs(y-z) for x, z in zip(p.right, p.ys) if 1 <= z <= 4))
                expected = max(slope, 5-.2*3, p.bounds.maxx-1.5)
            else:
                slope = p.right[i]
                expected = max(slope, p.bounds.maxx-1.5)
            self.assertAlmostEqual(p.slope_right[i], slope)
            self.assertAlmostEqual(p.filtered_right[i], expected)

    def test_convex_and_monotone_walls_are_not_globally_slope_limited(self):
        ys = (.5, 1.5, 2.5, 3.5)
        ramp = (1., 3., 5., 7.)
        self.assertEqual(h.concavity_filter_45(ys, ramp, (0, 4)), ramp)
        _, old_global = f.filter_45((0,)*4, ramp, 1)
        self.assertNotEqual(old_global, ramp)
        dome = (3., 4., 4., 3.)
        self.assertEqual(h.concavity_filter_45(ys, dome, (0, 4)), dome)
        _, cavities = h.aperture_filter(ys, ramp, ramp, (0, 4), .21)
        self.assertEqual(cavities, ())

    def test_patent_c_uses_exterior_lip_cutoff_and_asymmetric_connector(self):
        ys = tuple(i+.5 for i in range(8))
        raw = (10., 9., 8., 7., 6., 5., 4., 8.)
        slope = h.concavity_filter_45(ys, raw, (0, 8))
        actual, cavities = h.aperture_filter(ys, raw, slope, (0, 8), .21)
        self.assertEqual(len(cavities), 1)
        self.assertEqual(cavities[0].opening_px, 6)
        cutoff = 10-.21*6
        departure = 1+(10-cutoff)
        expected = cutoff + (4.5-departure)*(8-cutoff)/(7-departure)
        self.assertAlmostEqual(actual[4], expected)
        old_parallel_chord = 10+(4.5-1)*(8-10)/6-.21*6
        self.assertGreater(actual[4], old_parallel_chord)
        reverse_raw = tuple(reversed(raw))
        reverse_slope = h.concavity_filter_45(ys, reverse_raw, (0, 8))
        reverse, _ = h.aperture_filter(ys, reverse_raw, reverse_slope, (0, 8), .21)
        for a, b in zip(actual, reversed(reverse)):
            self.assertAlmostEqual(a, b)

    def test_patent_c_symmetric_cutoff_and_sampling_convergence(self):
        b = bitmap(["111111", "100000", "100000", "100000", "100000", "111111"], top=-6)
        means = []
        for density in (8, 16, 32, 64, 128):
            p = h.depth_profile(b, (0, 6), h.Settings(.21, 10, density))
            self.assertEqual([v.opening_px for v in p.right_cavities], [4])
            self.assertGreaterEqual(min(p.filtered_right), 6-.21*4)
            means.append(math.fsum(p.filtered_right)/len(p.ys))
        # Integral of lips (2*6), plus two slope-limited ramps of length .84,
        # plus central cutoff plateau across the four-pixel aperture.
        expected = (12 + 4*(6-.84) + .84*.84)/6
        errors = [abs(v-expected) for v in means]
        self.assertLess(errors[-1], errors[0])
        self.assertLess(errors[-1], 1e-5)

    def test_padding_translation_and_uniform_replication(self):
        b = bitmap(["11111", "10000", "10000", "11111"], left=-2, top=-4)
        settings = h.Settings(.25, .5, 16)
        p = h.depth_profile(b, (0, 4), settings)
        self.assertEqual(p, h.depth_profile(pad(b), (0, 4), settings))
        shifted = dict(b, left=b["left"]+7, top=b["top"]-3)
        q = h.depth_profile(shifted, (3, 7), settings)
        for a, v in zip(p.filtered_right, q.filtered_right):
            self.assertAlmostEqual(v, a+7)
        factor = 2
        rows = []
        for y in range(b["height"]):
            row = "".join(str(x)*factor for x in b["pixels"][y*b["width"]:(y+1)*b["width"]])
            rows.extend([row]*factor)
        scaled = h.depth_profile(bitmap(rows, left=-4, top=-8), (0, 8), h.Settings(.25, .5, 8))
        for a, v in zip(p.filtered_right, scaled.filtered_right):
            self.assertAlmostEqual(v, 2*a)
        self.assertEqual([v.opening_px for v in scaled.right_cavities], [4])

    def test_data_derived_bounds_disable_both_caps(self):
        b = bitmap(["11111", "10000", "00000", "10000", "11111"], top=-5)
        limits = h.depth_limits(b, (0, 5), 16)
        p = h.depth_profile(b, (0, 5), h.Settings(limits["relative_depth_upper"],
                                              limits["visual_depth_factor_upper"], 16))
        self.assertEqual(p.filtered_left, p.slope_left)
        self.assertEqual(p.filtered_right, p.slope_right)
        self.assertGreater(limits["cavity_count"], 0)

    def test_exact_source_stems_curves_and_unknown_diagonals(self):
        for side in ("left", "right"):
            self.assertEqual(h.classify_face(rectangle(), 1, (0, 4), side)["kind"], "stem")
            self.assertEqual(h.classify_face(oval(), 1, (0, 4), side)["kind"], "curve")
        diagonal = [dict(op="move_to", x=0, y=0), dict(op="line_to", x=2, y=0),
                    dict(op="line_to", x=6, y=4), dict(op="line_to", x=4, y=4), dict(op="close")]
        self.assertEqual(h.classify_face(diagonal, 1, (0, 4), "right")["kind"], "generic")
        # Open bowl's right-facing inner arc has an inward x extremum; it must
        # not be called a closed outer curve merely because it is a Bezier.
        open_bowl = [dict(op="move_to", x=4, y=0), dict(op="quad_to", x1=0, y1=2, x=4, y=4),
                     dict(op="line_to", x=3, y=4), dict(op="quad_to", x1=-1, y1=2, x=3, y=0), dict(op="close")]
        self.assertEqual(h.classify_face(open_bowl, 1, (0, 4), "right")["kind"], "generic")

    def test_curve_interior_extrema_reverse_and_source_scale(self):
        q = [dict(op="move_to", x=0, y=0), dict(op="quad_to", x1=4, y1=2, x=0, y=4), dict(op="close")]
        reverse = [dict(op="move_to", x=0, y=4), dict(op="quad_to", x1=4, y1=2, x=0, y=0), dict(op="close")]
        for commands in (q, reverse):
            face = h.classify_face(commands, 1, (0, 4), "right")
            self.assertEqual(face["kind"], "curve")
            self.assertEqual(face["source_support_x_px"], 2)
            scaled = h.classify_face(commands, 3, (0, 12), "right")
            self.assertEqual(scaled["kind"], face["kind"])
            self.assertEqual(scaled["source_support_x_px"], 6)

    def test_delivered_edges_use_delivered_geometry_not_source_coordinates(self):
        p = h.depth_profile(bitmap(["0110", "1111", "1111", "0110"], left=7, top=-4),
                            (0, 4), h.Settings(.25, .5))
        for side, expected in (("left", 7), ("right", 11)):
            for kind in ("stem", "curve"):
                self.assertEqual(h.delivered_face(p, side, dict(kind=kind, source_support_x_px=1000)), expected)
        self.assertIsNone(h.delivered_face(p, "left", dict(kind="generic")))

    def test_invalid_empty_and_excessive_inputs(self):
        for a, b in ((-1, 0), (0, -1), (math.inf, 1), (1, math.nan), (True, 0)):
            with self.assertRaises(f.GeometryError):
                h.Settings(a, b)
        for samples in (0, 1025, 1.5, True):
            with self.assertRaises(f.GeometryError):
                h.Settings(0, 0, samples)
        empty = h.depth_profile(bitmap([]), (0, 4), h.Settings(0, 0))
        self.assertIsNone(empty.bounds)
        self.assertIsNone(h.delivered_face(empty, "right", dict(kind="curve")))
        with self.assertRaises(f.GeometryError):
            h.depth_profile(bitmap(["1"]), (0, 1), None)
        with self.assertRaises(f.WorkLimitExceeded):
            h.depth_profile(bitmap(["1"]), (0, 129), h.Settings(0, 0))
        with self.assertRaises(f.GeometryError):
            h.classify_face(rectangle(), 1, (0, 4), "up")


if __name__ == "__main__":
    unittest.main()
