"""Exact topology wrapper controls; analytic fixtures, no pixels.

Binary-dependent cases skip when the reference checker is not built;
pure-Python behavior (rational transport, fail-closed inputs, schema)
always runs. Expected values are hand-computed, never fitted.
"""

import os
import unittest

from experiments.hobby_fitting import exact_topology as et


def rect(x0, y0, x1, y1, extra=None):
    cmds = [{"op": "move_to", "x": x0, "y": y0},
            {"op": "line_to", "x": x1, "y": y0},
            {"op": "line_to", "x": x1, "y": y1},
            {"op": "line_to", "x": x0, "y": y1},
            {"op": "close"}]
    return cmds + list(extra or [])


def shifted(cmds, dx, dy):
    out = []
    for cmd in cmds:
        cmd = dict(cmd)
        for key in ("x", "y", "x1", "y1", "x2", "y2"):
            if key in cmd:
                cmd[key] = cmd[key] + (dx if key[0] == "x" else dy)
        out.append(cmd)
    return out


class TransportTests(unittest.TestCase):
    def test_rational_strings_exact(self):
        self.assertEqual(et._rational(3.890625), "249/64")
        self.assertEqual(et._rational(10.0), "10/1")
        self.assertEqual(et._rational(-0.5), "-1/2")
        self.assertIsNone(et._rational(float("inf")))

    def test_curves_unsupported_without_binary(self):
        cmds = [{"op": "move_to", "x": 0, "y": 0},
                {"op": "quad_to", "x1": 1, "y1": 1, "x": 2, "y": 0},
                {"op": "close"}]
        out = et.analyze_commands(cmds, binary="/nonexistent")
        self.assertFalse(out["supported"])
        self.assertEqual(out["reason"], "curves-unsupported")
        self.assertIsNone(out["signature"])

    def test_empty_and_degenerate_unsupported(self):
        out = et.analyze_commands([], binary="/nonexistent")
        self.assertFalse(out["supported"])
        out = et.analyze_commands([{"op": "move_to", "x": 1, "y": 1},
                                   {"op": "close"}],
                                  binary="/nonexistent")
        self.assertFalse(out["supported"])

    def test_missing_binary_fail_closed(self):
        out = et.analyze_commands(rect(0, 0, 10, 5),
                                  binary="/nonexistent-checker")
        self.assertFalse(out["supported"])
        self.assertEqual(out["reason"], "binary-missing")

    def test_open_loop_fails_closed(self):
        # move/line/line with no close is not a closed contour, even
        # though a permissive parser could close it implicitly.
        cmds = [{"op": "move_to", "x": 0, "y": 0},
                {"op": "line_to", "x": 4, "y": 0},
                {"op": "line_to", "x": 4, "y": 4}]
        out = et.analyze_commands(cmds, binary="/nonexistent")
        self.assertFalse(out["supported"])
        self.assertEqual(out["reason"], "malformed-commands")

    def test_grammar_violations_fail_closed(self):
        good = [{"op": "move_to", "x": 0, "y": 0},
                {"op": "line_to", "x": 1, "y": 0},
                {"op": "close"}]
        cases = [
            [{"op": "line_to", "x": 1, "y": 0},
             {"op": "close"}],
            [{"op": "close"}],
            good + [{"op": "line_to", "x": 2, "y": 0}],
            good[:-1] + [{"op": "move_to", "x": 5, "y": 5},
                         {"op": "close"}],
            [{"op": "arc", "x": 1, "y": 0}],
            [{"op": "move_to", "x": float("nan"), "y": 0},
             {"op": "close"}],
        ]
        for cmds in cases:
            out = et.analyze_commands(cmds, binary="/nonexistent")
            self.assertFalse(out["supported"], cmds)
            self.assertIn(out["reason"],
                          ("malformed-commands",
                           "nonfinite-coordinate"))

    def test_compare_unsupported_shape(self):
        out = et.compare_commands([], [], [], binary="/nonexistent")
        self.assertFalse(out["supported"])
        self.assertFalse(out["ok"])
        self.assertIn("source", out)
        self.assertIn("upstream", out)
        self.assertIn("candidate", out)
        self.assertFalse(out["source_upstream_match"])
        self.assertIn("unsupported", out["diff"])


def loop(pts):
    return ([{"op": "move_to", "x": pts[0][0], "y": pts[0][1]}] +
            [{"op": "line_to", "x": x, "y": y} for x, y in pts[1:]] +
            [{"op": "close"}])


class CheckerTests(unittest.TestCase):
    def setUp(self):
        path = et._resolve_binary(None)
        if not (os.path.isfile(path) and os.access(path, os.X_OK)):
            self.skipTest("exact-topology binary not built")
        self.binary = path

    def test_rect_signature(self):
        out = et.analyze_commands(rect(0, 0, 100, 50),
                                  binary=self.binary)
        self.assertTrue(out["supported"], out["reason"])
        sig = out["signature"]
        self.assertEqual(sig["filled_components"], 1)
        self.assertEqual(sig["holes"], 0)
        self.assertEqual(sig["filled_area"], "5000/1")
        self.assertEqual(sig["seam_chains"], 0)
        self.assertEqual(sig["pinch_vertices"], 0)
        self.assertEqual(sig["point_contacts"], [])
        self.assertEqual(sig["components"],
                         [{"contours": [0], "holes": 0}])

    def test_rect_with_hole(self):
        hole = [{"op": "move_to", "x": 20, "y": 10},
                {"op": "line_to", "x": 20, "y": 40},
                {"op": "line_to", "x": 80, "y": 40},
                {"op": "line_to", "x": 80, "y": 10},
                {"op": "close"}]
        out = et.analyze_commands(rect(0, 0, 100, 50, hole),
                                  binary=self.binary)
        self.assertTrue(out["supported"], out["reason"])
        sig = out["signature"]
        self.assertEqual(sig["filled_components"], 1)
        self.assertEqual(sig["holes"], 1)
        self.assertEqual(sig["filled_area"], "3200/1")
        self.assertEqual(sig["hole_areas"], ["1800/1"])

    def test_segmentation_churn_invisible(self):
        # Splitting every edge at its midpoint changes segments but
        # not the filled shape; the signature must not move.
        plain = rect(0, 0, 100, 50)
        split = [{"op": "move_to", "x": 0, "y": 0},
                 {"op": "line_to", "x": 50, "y": 0},
                 {"op": "line_to", "x": 100, "y": 0},
                 {"op": "line_to", "x": 100, "y": 25},
                 {"op": "line_to", "x": 100, "y": 50},
                 {"op": "line_to", "x": 50, "y": 50},
                 {"op": "line_to", "x": 0, "y": 50},
                 {"op": "line_to", "x": 0, "y": 25},
                 {"op": "close"}]
        first = et.analyze_commands(plain, binary=self.binary)
        second = et.analyze_commands(split, binary=self.binary)
        self.assertTrue(first["supported"] and second["supported"])
        self.assertEqual(et._structural_key(first["signature"]),
                         et._structural_key(second["signature"]))

    def test_point_touch_two_components(self):
        # Two rects meeting at exactly one point: separate filled
        # components joined by one classified point contact.
        second = [{"op": "move_to", "x": 100, "y": 50},
                  {"op": "line_to", "x": 200, "y": 50},
                  {"op": "line_to", "x": 200, "y": 100},
                  {"op": "line_to", "x": 100, "y": 100},
                  {"op": "close"}]
        out = et.analyze_commands(rect(0, 0, 100, 50, second),
                                  binary=self.binary)
        self.assertTrue(out["supported"], out["reason"])
        sig = out["signature"]
        self.assertEqual(sig["filled_components"], 2)
        self.assertEqual(len(sig["point_contacts"]), 1)
        sides = sig["point_contacts"][0]["sides"]
        self.assertEqual(sorted(map(sorted, sides)), [[0], [1]])

    def test_subpixel_gap_not_a_touch(self):
        # The same rects separated by 1/64 px: two components and no
        # point contact, distinguished exactly from the touch above.
        second = [{"op": "move_to", "x": 100.015625, "y": 50},
                  {"op": "line_to", "x": 200, "y": 50},
                  {"op": "line_to", "x": 200, "y": 100},
                  {"op": "line_to", "x": 100.015625, "y": 100},
                  {"op": "close"}]
        out = et.analyze_commands(rect(0, 0, 100, 50, second),
                                  binary=self.binary)
        self.assertTrue(out["supported"], out["reason"])
        sig = out["signature"]
        self.assertEqual(sig["filled_components"], 2)
        self.assertEqual(sig["point_contacts"], [])

    def test_coincident_opposite_cancel(self):
        # Two identical contours in opposite directions cancel to
        # zero fill; nothing is reported as a component.
        fwd = rect(0, 0, 100, 50)
        rev = [{"op": "move_to", "x": 0, "y": 0},
               {"op": "line_to", "x": 0, "y": 50},
               {"op": "line_to", "x": 100, "y": 50},
               {"op": "line_to", "x": 100, "y": 0},
               {"op": "close"}]
        out = et.analyze_commands(fwd + rev, binary=self.binary)
        self.assertTrue(out["supported"], out["reason"])
        sig = out["signature"]
        self.assertEqual(sig["filled_components"], 0)
        self.assertEqual(sig["filled_area"], "0/1")

    def test_compare_moved_vertex_ok(self):
        # A small shift preserving structure compares equal; the
        # reference decides joins, not coordinate identity.
        base = rect(0, 0, 100, 50)
        moved = shifted(base, 0.5, -0.25)
        out = et.compare_commands(base, base, moved,
                                  binary=self.binary)
        self.assertTrue(out["supported"], out["reason"])
        self.assertTrue(out["ok"], out["diff"])
        self.assertTrue(out["source_upstream_match"])

    def test_compare_detached_join_fails(self):
        # Detaching the touching rects opens the point contact and
        # must fail the candidate-vs-upstream comparison.
        touch = rect(0, 0, 100, 50) + [
            {"op": "move_to", "x": 100, "y": 50},
            {"op": "line_to", "x": 200, "y": 50},
            {"op": "line_to", "x": 200, "y": 100},
            {"op": "line_to", "x": 100, "y": 100},
            {"op": "close"}]
        gap = rect(0, 0, 100, 50) + [
            {"op": "move_to", "x": 101, "y": 50},
            {"op": "line_to", "x": 200, "y": 50},
            {"op": "line_to", "x": 200, "y": 100},
            {"op": "line_to", "x": 101, "y": 100},
            {"op": "close"}]
        out = et.compare_commands(touch, touch, gap,
                                  binary=self.binary)
        self.assertTrue(out["supported"], out["reason"])
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "upstream-candidate-mismatch")
        self.assertTrue(out["source_upstream_match"])
        self.assertIsNotNone(out["diff"])


    def test_covered_point_touch_loss_fails(self):
        # Two CCW lobes point-touching at (2,2) under a covering
        # rect: the union is one component either way, so only the
        # per-pair intersection-boundary singularity (degree 4 at
        # the touch, none once the upper lobe shifts away on a
        # cancelling spike) distinguishes the candidate.
        source_a = loop([(0, 0), (2, 0), (2, 2), (2, 2), (4, 2),
                         (4, 4), (2, 4), (2, 2), (2, 2), (0, 2)])
        candidate_a = loop([(0, 0), (2, 0), (2, 2),
                            (2.125, 2.125), (4.125, 2.125),
                            (4.125, 4.125), (2.125, 4.125),
                            (2.125, 2.125), (2, 2), (0, 2)])
        cover = rect(-1, -1, 6, 6)
        source, candidate = source_a + cover, candidate_a + cover
        up = et.analyze_commands(source, binary=self.binary)
        down = et.analyze_commands(candidate, binary=self.binary)
        self.assertTrue(up["supported"], up["reason"])
        self.assertTrue(down["supported"], down["reason"])
        for sig in (up["signature"], down["signature"]):
            self.assertEqual(sig["filled_components"], 1)
            self.assertEqual(sig["holes"], 0)
        up_pair = [p for p in up["signature"]["pairs"]
                   if p["pair"] == [0, 1]][0]
        down_pair = [p for p in down["signature"]["pairs"]
                     if p["pair"] == [0, 1]][0]
        for pair in (up_pair, down_pair):
            self.assertEqual(pair["area_components"], 2)
            self.assertEqual(pair["edge_components"], 0)
            self.assertEqual(pair["point_contacts"], 0)
        self.assertEqual(up_pair["boundary_degrees"], [4])
        self.assertEqual(down_pair["boundary_degrees"], [])
        out = et.compare_commands(source, source, candidate,
                                  binary=self.binary)
        self.assertTrue(out["supported"], out["reason"])
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "upstream-candidate-mismatch")
        self.assertTrue(out["source_upstream_match"])
        self.assertIsNotNone(out["diff"])


if __name__ == "__main__":
    unittest.main()
