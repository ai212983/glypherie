"""Adversarial tests for certified curve clearance; no pixel verdicts."""

import json
import os
import unittest
from fractions import Fraction

from experiments.hobby_fitting import curve_clearance as cc


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))


def _y_commands():
    path = os.path.join(_repo_root(), "out", "diagnostics",
                        "direct-diagonal", "text-review", "ascii-captures",
                        "Roboto-400-16.json")
    if not os.path.isfile(path):
        raise unittest.SkipTest("y capture fixture absent")
    cap = json.load(open(path))
    recs = cap[0]["modes"]["selective_default"]["records"]
    record = next(r for r in recs if r.get("codepoint") == 121)
    return record["source_commands"], record["fitted_commands"]


def _checker_binary():
    from experiments.hobby_fitting.exact_topology import DEFAULT_BINARY
    path = os.environ.get("HOBBY_EXACT_TOPOLOGY_BINARY", DEFAULT_BINARY)
    if not os.path.isabs(path):
        path = os.path.join(_repo_root(), path)
    if not (os.path.isfile(path) and os.access(path, os.X_OK)):
        raise unittest.SkipTest("exact topology binary absent")
    return path


def seg(a, b):
    return (a, b)


FAR_QUAD = [(10, 10), (12, 14), (14, 10)]
ARCH = [(0, 0), (1, 3), (2, 0)]


class ClearanceTests(unittest.TestCase):
    def test_distant_curve_clears(self):
        ok, _ = cc.edge_vs_curve_clear(seg((0, 0), (0, 2)),
                                       seg((0.25, 0), (0.25, 2)), FAR_QUAD)
        self.assertTrue(ok)

    def test_sweep_crossing_fixed_curve_rejected(self):
        ok, reason = cc.edge_vs_curve_clear(
            seg((0, -1), (0, 1)), seg((2, -1), (2, 1)), ARCH)
        self.assertFalse(ok)
        self.assertEqual(reason, "curve-contact")

    def test_hidden_mid_sweep_collision_rejected(self):
        # Endpoints sit clear above/below the bump legs; the swept band
        # still crosses them, which endpoint sampling alone would miss.
        bump = [(0, 0), (1, 1), (2, 0)]
        ok, _ = cc.edge_vs_curve_clear(seg((0.2, 0.1), (1.8, 0.1)),
                                       seg((0.2, 0.4), (1.8, 0.4)), bump)
        self.assertFalse(ok)

    def test_endpoint_tangency_accepted_only_isolated_shared(self):
        old = seg((0, 0), (-2, 1))
        new = seg((0, 0), (-2.25, 0.75))
        ok, _ = cc.edge_vs_curve_clear(old, new, ARCH)
        self.assertTrue(ok)

    def test_endpoint_reversal_to_other_side_rejected(self):
        old = seg((0, 0), (-2, 1))
        new = seg((0, 0), (2, 1))
        ok, reason = cc.edge_vs_curve_clear(old, new, ARCH)
        self.assertFalse(ok)
        self.assertEqual(reason, "ray-reversal")

    def test_ray_collapse_refused(self):
        old = seg((0, 0), (-2, 1))
        new = seg((0, 0), (0, 0))
        ok, reason = cc.edge_vs_curve_clear(old, new, ARCH)
        self.assertFalse(ok)
        self.assertEqual(reason, "ray-collapse")

    def test_curve_endpoint_inside_sweep_not_pinned_refused(self):
        # A curve endpoint inside the sweep that no segment shares is
        # contact, not a pinned joint.
        inside = [(0.25, 0.5), (0.3, 1.0), (0.25, 1.5)]
        ok, reason = cc.edge_vs_curve_clear(seg((0, 0), (0, 2)),
                                            seg((0.5, 0), (0.5, 2)),
                                            inside)
        self.assertFalse(ok)
        self.assertEqual(reason, "curve-contact")

    def test_fitted_y_descender_sweep_clears(self):
        # Actual fitted y: descender straight shares pinned curve-0
        # start; the sweep meets sub-hulls only there (old wedge gate
        # refused this configuration).
        pinned = (3.984375, -0.859375)
        curve = [pinned, (3.875, -1.1875), (3.671875, -1.546875)]
        ok, reason = cc.edge_vs_curve_clear(
            ((7.375, 9.0), pinned), ((7.0, 9.0), pinned),
            curve, depth=4)
        self.assertTrue(ok, reason)

    def test_control_point_change_flips_verdict(self):
        # Same endpoints; only the off-curve control moves into the sweep.
        old, new = seg((0, 0), (0, 2)), seg((0.25, 0), (0.25, 2))
        ok_far, _ = cc.edge_vs_curve_clear(old, new,
                                           [(3, 0), (5, 1), (3, 2)])
        ok_near, _ = cc.edge_vs_curve_clear(old, new,
                                            [(3, 0), (-3, 1), (3, 2)])
        self.assertTrue(ok_far)
        self.assertFalse(ok_near)

    def test_curve_through_sweep_without_shared_endpoint_vetoes(self):
        # No endpoint coincides; the curve body enters the swept band.
        crossing = [(0.3, 1), (0.6, 1.5), (0.9, 1)]
        ok, reason = cc.edge_vs_curve_clear(seg((0, 0), (0, 2)),
                                            seg((0.5, 0), (0.5, 2)),
                                            crossing)
        self.assertFalse(ok)
        self.assertEqual(reason, "curve-contact")

    def test_verdict_translation_and_scale_invariant(self):
        old, new = seg((0, 0), (0, 2)), seg((0.25, 0), (0.25, 2))
        expected = cc.edge_vs_curve_clear(old, new, FAR_QUAD)
        for dx, k in ((37, 1), (-1024, 1), (0, 2)):
            move = lambda p: (p[0] * k + dx, p[1] * k + dx)
            got = cc.edge_vs_curve_clear(
                seg(move((0, 0)), move((0, 2))),
                seg(move((0.25, 0)), move((0.25, 2))),
                [move(p) for p in FAR_QUAD])
            self.assertEqual(got, expected)

    def test_subdivision_monotone(self):
        # A loose hull may abstain; deeper hulls never lose a clearance.
        pinched = [(0.4, -1), (0.45, 0.5), (0.4, 2)]
        shallow = cc.edge_vs_curve_clear(seg((0, 0), (0, 2)),
                                         seg((0.1, 0), (0.1, 2)),
                                         pinched, depth=0)
        deep = cc.edge_vs_curve_clear(seg((0, 0), (0, 2)),
                                      seg((0.1, 0), (0.1, 2)),
                                      pinched, depth=5)
        if shallow[0]:
            self.assertTrue(deep[0])

    def test_cubic_supported(self):
        cubic = [(8, 8), (9, 10), (11, 10), (12, 8)]
        ok, _ = cc.edge_vs_curve_clear(seg((0, 0), (0, 2)),
                                       seg((0.25, 0), (0.25, 2)), cubic)
        self.assertTrue(ok)

    def test_movement_clear_pairs_reports_first_failure(self):
        olds = [seg((0, 0), (0, 2)), seg((0, -1), (0, 1))]
        news = [seg((0.25, 0), (0.25, 2)), seg((2, -1), (2, 1))]
        ok, _ = cc.movement_clear(olds, news, [FAR_QUAD, ARCH])
        self.assertFalse(ok)
        ok, _ = cc.movement_clear(olds[:1], news[:1], [FAR_QUAD])
        self.assertTrue(ok)

    def test_monotone_quad_accepted(self):
        self.assertTrue(cc.is_chord_monotone([(0, 0), (1, 1), (2, 0)]))

    def test_loop_cubic_rejected_nonmonotone(self):
        # Classic self-loop: one leg projects backwards on the chord.
        self.assertFalse(cc.is_chord_monotone(
            [(0, 0), (2, 1), (-1, 1), (1, 0)]))

    def test_degenerate_chord_projection_rejected(self):
        self.assertFalse(cc.is_chord_monotone(
            [(0, 0), (2, 2), (-2, 2), (0, 4)]))
        self.assertFalse(cc.is_chord_monotone([(1, 1), (1, 1), (1, 1)]))

    def test_tangent_touch_meets_only_at_junction(self):
        # C1-joined quads: hulls share the tangent line through the
        # junction but intersect only there; no wedge required.
        left = cc.convex_hull([(0, 0), (1, 0), (2, 1)])
        right = cc.convex_hull([(2, 1), (3, 2), (4, 2)])
        self.assertTrue(cc.hulls_meet_only_at(left, right, (2, 1)))

    def test_crossing_hulls_rejected(self):
        left = cc.convex_hull([(0, 0), (1, 0), (2, 1)])
        over = cc.convex_hull([(1, -1), (1, 1), (3, 0)])
        self.assertFalse(cc.strictly_disjoint(left, over))
        self.assertFalse(cc.hulls_meet_only_at(left, over, (2, 1)))

    def test_substitution_certifies_closed_bump(self):
        cmds = [{"op": "move_to", "x": 0, "y": 0},
                {"op": "line_to", "x": 4, "y": 0},
                {"op": "quad_to", "x1": 5, "y1": 1, "x": 4, "y": 2},
                {"op": "line_to", "x": 0, "y": 4},
                {"op": "close"}]
        rep = cc.certify_substitution(cmds, depth=0)
        self.assertTrue(rep["ok"])
        poly = cc.build_substituted_commands(cmds, depth=0)
        self.assertEqual([c["op"] for c in poly],
                         ["move_to", "line_to", "line_to",
                          "line_to", "close"])
        self.assertEqual((poly[1]["x"], poly[1]["y"]), (4, 0))
        self.assertEqual((poly[-2]["x"], poly[-2]["y"]), (0, 4))

    def test_substitution_rejects_curve_crossing_straight(self):
        cmds = [{"op": "move_to", "x": 0, "y": 0},
                {"op": "line_to", "x": 2, "y": -1},
                {"op": "line_to", "x": 2, "y": 5},
                {"op": "line_to", "x": 4, "y": 5},
                {"op": "quad_to", "x1": 2, "y1": 2, "x": 0, "y": 5},
                {"op": "close"}]
        rep = cc.certify_substitution(cmds, depth=1)
        self.assertFalse(rep["ok"])
        self.assertEqual(rep["reason"], "hull-contact")

    def test_substitution_rejects_loop(self):
        # A self-looping cubic: coarse depth fails monotonicity, while
        # fine pieces are locally monotone but overlap non-adjacently.
        cmds = [{"op": "move_to", "x": 0, "y": 0},
                {"op": "curve_to", "x1": 2, "y1": 1, "x2": -1, "y2": 1,
                 "x": 1, "y": 0},
                {"op": "close"}]
        rep = cc.certify_substitution(cmds, depth=0)
        self.assertFalse(rep["ok"])
        self.assertEqual(rep["reason"], "nonmonotone-piece")
        rep = cc.certify_substitution(cmds, depth=2)
        self.assertFalse(rep["ok"])
        self.assertEqual(rep["reason"], "hull-contact")

    def test_wrapper_refuses_moved_curves_without_checker(self):
        base = [{"op": "move_to", "x": 0, "y": 0},
                {"op": "line_to", "x": 4, "y": 0},
                {"op": "quad_to", "x1": 5, "y1": 1, "x": 4, "y": 2},
                {"op": "line_to", "x": 0, "y": 4},
                {"op": "close"}]
        moved = [dict(c) for c in base]
        moved[2] = dict(moved[2], x1=6)
        verdict = cc.compare_commands(base, base, moved, depth=0)
        self.assertFalse(verdict["supported"])
        self.assertEqual(verdict["reason"], "curves-moved")

    def test_y_contour_zero_certifies_and_keeps_identity(self):
        # Default Roboto y contour 0 (11 quads); assessment 2026-10-21.
        cmds = _y_contour_zero()
        rep = cc.certify_substitution(cmds, depth=0)
        self.assertTrue(rep["ok"])
        poly = cc.build_substituted_commands(cmds, depth=0)
        self.assertEqual([c.get("op") for c in poly],
                         ["move_to"] + ["line_to"] * 15 + ["close"])
        self.assertEqual((poly[0]["x"], poly[0]["y"]),
                         (3.484375, 0.875))
        self.assertTrue(all(c.get("op") != "quad_to" for c in poly))

    def test_wrapper_spoof_implied_start_refused(self):
        # Identical quad dict, but the preceding line moved: the Bezier
        # start point moved, so the curve geometry differs.
        base = [{"op": "move_to", "x": 0, "y": 0},
                {"op": "line_to", "x": 4, "y": 0},
                {"op": "quad_to", "x1": 5, "y1": 1, "x": 4, "y": 2},
                {"op": "line_to", "x": 0, "y": 4},
                {"op": "close"}]
        spoofed = [dict(c) for c in base]
        spoofed[1] = dict(spoofed[1], x=4.5)
        verdict = cc.compare_commands(base, base, spoofed, depth=0)
        self.assertFalse(verdict["supported"])
        self.assertEqual(verdict["reason"], "curves-moved")

    def test_wrapper_signed_zero_distinguished(self):
        # Numeric == yet bit-distinct signed zeros must refuse.
        base = [{"op": "move_to", "x": 0.0, "y": 0.0},
                {"op": "quad_to", "x1": 1.0, "y1": 1.0,
                 "x": 2.0, "y": 0.0},
                {"op": "close"}]
        neg = [dict(c) for c in base]
        neg[0] = dict(neg[0], x=-0.0)
        verdict = cc.compare_commands(base, base, neg, depth=0)
        self.assertFalse(verdict["supported"])
        self.assertEqual(verdict["reason"], "curves-moved")

    def test_wrapper_explicit_bits_mismatch_refused(self):
        base = [{"op": "move_to", "x": 0.0, "y": 0.0},
                {"op": "quad_to", "x1": 1.0, "y1": 1.0,
                 "x1_bits": 4607182418800017408,
                 "x": 2.0, "y": 0.0},
                {"op": "close"}]
        spoofed = [dict(c) for c in base]
        spoofed[1] = dict(spoofed[1], x1_bits=4607182418800017409)
        verdict = cc.compare_commands(base, base, spoofed, depth=0)
        self.assertFalse(verdict["supported"])
        self.assertEqual(verdict["reason"], "curves-moved")

    def test_disk_clear_far_curve(self):
        ok, reason = cc.disk_clear((0, 0), 0.5, FAR_QUAD)
        self.assertTrue(ok)
        self.assertEqual(reason, "clear")

    def test_disk_clear_collision_fails_closed(self):
        ok, reason = cc.disk_clear((1, 1), 1.0, ARCH)
        self.assertFalse(ok)
        self.assertEqual(reason, "disk-too-close")

    def test_disk_clear_touch_is_not_clear(self):
        # Bbox distance exactly equals the radius: strict bound fails.
        ok, _ = cc.disk_clear((0, 0), 1.0, [(1, 0), (2, 0), (3, 0)])
        self.assertFalse(ok)

    def test_disk_clear_budget_exhaustion_fails_closed(self):
        ok, reason = cc.disk_clear((1, 1), 1.0, ARCH, max_depth=0)
        self.assertFalse(ok)
        self.assertEqual(reason, "disk-too-close")
        ok, _ = cc.disk_clear((0, 0), -1.0, ARCH)
        self.assertFalse(ok)

    def test_disk_clear_y_station_clears_source_curve(self):
        # Default-y station-3 disk against the first bowl quad: the old
        # control-hull veto was looseness; the exact disk clears source.
        source, fitted = _y_commands()

        def first_quad(cmds):
            pt = None
            for cmd in cmds:
                op = cmd.get("op")
                if op in ("move_to", "line_to"):
                    pt = (cmd["x"], cmd["y"])
                elif op == "quad_to":
                    return [pt, (cmd["x1"], cmd["y1"]),
                            (cmd["x"], cmd["y"])]
            return None

        ok, reason = cc.disk_clear((3.53, -0.76), 0.611,
                                   first_quad(source))
        self.assertTrue(ok)
        self.assertEqual(reason, "clear")
        # The same disk does not clear fitted geometry: no blanket pass.
        ok, _ = cc.disk_clear((3.53, -0.76), 0.611,
                              first_quad(fitted))
        self.assertFalse(ok)

    def test_y_source_upstream_parity(self):
        source, fitted = _y_commands()
        verdict = cc.compare_commands(source, fitted, fitted, depth=0,
                                      binary=_checker_binary())
        self.assertTrue(verdict["supported"])
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["reason"], "match")

    def test_y_spoof_control_and_start_refused(self):
        import copy
        source, fitted = _y_commands()
        tampered = copy.deepcopy(fitted)
        for cmd in tampered:
            if cmd.get("op") == "quad_to":
                cmd["x1"] = cmd["x1"] + 0.5
                break
        verdict = cc.compare_commands(source, fitted, tampered, depth=0,
                                      binary=_checker_binary())
        self.assertFalse(verdict["supported"])
        self.assertEqual(verdict["reason"], "curves-moved")
        tampered = copy.deepcopy(fitted)
        for pos, cmd in enumerate(tampered):
            nxt = tampered[pos + 1] if pos + 1 < len(tampered) else {}
            if cmd.get("op") == "line_to" and nxt.get("op") in (
                    "quad_to", "curve_to"):
                cmd["x"] = cmd["x"] + 0.5
                break
        verdict = cc.compare_commands(source, fitted, tampered, depth=0,
                                      binary=_checker_binary())
        self.assertFalse(verdict["supported"])
        self.assertEqual(verdict["reason"], "curves-moved")

    def test_closing_edge_collision_certified(self):
        # The implicit closing edge overlaps the quad hull while all
        # explicit lines clear it; without materialization the outline
        # would wrongly certify.
        cmds = [{"op": "move_to", "x": 0, "y": -4},
                {"op": "quad_to", "x1": 2, "y1": 1, "x": 4, "y": 0},
                {"op": "line_to", "x": 6, "y": 2},
                {"op": "close"}]
        rep = cc.certify_substitution(cmds, depth=0)
        self.assertFalse(rep["ok"])
        self.assertEqual(rep["reason"], "hull-contact")
        self.assertEqual(rep["at"], (0, 0, 0))
        self.assertEqual(rep["with"], (0, 2, 0))

    def test_closing_edge_retained_when_clear(self):
        cmds = [{"op": "move_to", "x": 0, "y": 0},
                {"op": "line_to", "x": 4, "y": 0},
                {"op": "line_to", "x": 4, "y": 4},
                {"op": "quad_to", "x1": 2, "y1": 5, "x": 0, "y": 4},
                {"op": "close"}]
        rep = cc.certify_substitution(cmds, depth=0)
        self.assertTrue(rep["ok"])

    def test_wraparound_and_second_contour(self):
        cmds = [{"op": "move_to", "x": 0, "y": 0},
                {"op": "quad_to", "x1": 1, "y1": 3, "x": 4, "y": 2},
                {"op": "line_to", "x": 6, "y": 0},
                {"op": "close"},
                {"op": "move_to", "x": 10, "y": 10},
                {"op": "line_to", "x": 14, "y": 10},
                {"op": "line_to", "x": 14, "y": 14},
                {"op": "line_to", "x": 10, "y": 14},
                {"op": "close"}]
        rep = cc.certify_substitution(cmds, depth=0)
        self.assertTrue(rep["ok"])

    def test_strict_grammar_fails_closed(self):
        open_cmds = [{"op": "move_to", "x": 0, "y": 0},
                     {"op": "line_to", "x": 4, "y": 0},
                     {"op": "quad_to", "x1": 5, "y1": 1,
                      "x": 4, "y": 2}]
        rep = cc.certify_substitution(open_cmds, depth=0)
        self.assertFalse(rep["ok"])
        self.assertEqual(rep["reason"], "malformed-commands")
        doubled = open_cmds[:1] + [{"op": "move_to", "x": 9, "y": 9}]
        self.assertIsNone(cc._control_keys(doubled))
        trailing = open_cmds + [{"op": "close"},
                                {"op": "line_to", "x": 1, "y": 1}]
        self.assertIsNone(cc._control_keys(trailing))

    def test_nonstart_straight_move_allowed(self):
        # A moved straight that starts no curve must pass the pin gate;
        # only curve geometry (with implied starts) is pinned.
        base = [{"op": "move_to", "x": 0, "y": 0},
                {"op": "line_to", "x": 2, "y": 0},
                {"op": "line_to", "x": 4, "y": 0},
                {"op": "quad_to", "x1": 5, "y1": 1, "x": 4, "y": 2},
                {"op": "line_to", "x": 0, "y": 4},
                {"op": "close"}]
        moved = [dict(c) for c in base]
        moved[1] = dict(moved[1], x=2.2)
        verdict = cc.compare_commands(base, base, moved, depth=0)
        self.assertNotEqual(verdict["reason"], "curves-moved")

    def test_exactness_no_float_touch_pass(self):
        # A 1/3-offset sweep toward a dyadic hull stays exact: no
        # float rounding may turn near-touch into clearance.
        third = float(Fraction(1, 3))
        ok, _ = cc.edge_vs_curve_clear(seg((0, 0), (0, 2)),
                                       seg((third, 0), (third, 2)), FAR_QUAD)
        self.assertTrue(ok)


def _y_contour_zero():
    # Source contour 0 of default Roboto y (U+0079), ASCII recapture.
    return [
        {"op": "move_to", "x": 3.484375, "y": 0.875},
        {"op": "line_to", "x": 5.828125, "y": 8.453125},
        {"op": "line_to", "x": 7.375, "y": 8.453125},
        {"op": "line_to", "x": 3.984375, "y": -1.3125},
        {"op": "quad_to", "x1": 3.875, "y1": -1.625,
         "x": 3.671875, "y": -1.984375},
        {"op": "quad_to", "x1": 3.484375, "y1": -2.34375,
         "x": 3.1875, "y": -2.671875},
        {"op": "quad_to", "x1": 2.890625, "y1": -3.0,
         "x": 2.46875, "y": -3.203125},
        {"op": "quad_to", "x1": 2.0625, "y1": -3.421875,
         "x": 1.484375, "y": -3.421875},
        {"op": "quad_to", "x1": 1.3125, "y1": -3.421875,
         "x": 1.046875, "y": -3.375},
        {"op": "quad_to", "x1": 0.78125, "y1": -3.328125,
         "x": 0.671875, "y": -3.296875},
        {"op": "line_to", "x": 0.65625, "y": -2.125},
        {"op": "quad_to", "x1": 0.71875, "y1": -2.125,
         "x": 0.859375, "y": -2.140625},
        {"op": "quad_to", "x1": 1.0, "y1": -2.15625,
         "x": 1.046875, "y": -2.15625},
        {"op": "quad_to", "x1": 1.546875, "y1": -2.15625,
         "x": 1.890625, "y": -2.015625},
        {"op": "quad_to", "x1": 2.234375, "y1": -1.890625,
         "x": 2.46875, "y": -1.59375},
        {"op": "quad_to", "x1": 2.703125, "y1": -1.296875,
         "x": 2.875, "y": -0.765625},
        {"op": "close"},
    ]


if __name__ == "__main__":
    unittest.main()
