"""Joint diagonal fitting: algebra controls, not optical acceptance.

Every assertion follows the model: Hobby (5) station widths, (17)
anchor rows with the published angular weights, Hersch integer line
separation as normal width over the axis normal component, and
fail-closed abstention with explicit reasons. No pixel counts.
"""

import math
import struct
import unittest

import numpy as np

from experiments.hobby_fitting import direct_diagonal as dd
from experiments.hobby_fitting import real_outline
from experiments.hobby_fitting.prototype import width_weight


def bar_stem(bar_hw=14.0, stem_w=10.0, stem_fit=None, dx=0.0, dy=0.0,
             mirror=False):
    """One slanted bar plus one vertical stem, matched widths."""
    s = lambda v: -v if mirror else v
    src = [{"op": "move_to", "x": s(0) + dx, "y": 0 + dy},
           {"op": "line_to", "x": s(100) + dx, "y": 100 + dy},
           {"op": "line_to", "x": s(100 + bar_hw) + dx, "y": 100 + dy},
           {"op": "line_to", "x": s(bar_hw) + dx, "y": 0 + dy},
           {"op": "close"},
           {"op": "move_to", "x": s(140) + dx, "y": 0 + dy},
           {"op": "line_to", "x": s(140 + stem_w) + dx, "y": 0 + dy},
           {"op": "line_to", "x": s(140 + stem_w) + dx, "y": 100 + dy},
           {"op": "line_to", "x": s(140) + dx, "y": 100 + dy},
           {"op": "close"}]
    fit = [dict(c) for c in src]
    if stem_fit is not None:
        for c in fit:
            if abs(c.get("x", 1e18) - (s(140 + stem_w) + dx)) < 1e-9:
                c["x"] = s(140 + stem_fit) + dx
    return src, fit


def wide_x(stem_w=14.0, stem_fit=12.6):
    src = [{"op": "move_to", "x": 0, "y": 0},
           {"op": "line_to", "x": 100, "y": 100},
           {"op": "line_to", "x": 120, "y": 100},
           {"op": "line_to", "x": 20, "y": 0},
           {"op": "close"},
           {"op": "move_to", "x": 20, "y": 100},
           {"op": "line_to", "x": 120, "y": 0},
           {"op": "line_to", "x": 100, "y": 0},
           {"op": "line_to", "x": 0, "y": 100},
           {"op": "close"},
           {"op": "move_to", "x": 140, "y": 0},
           {"op": "line_to", "x": 140 + stem_w, "y": 0},
           {"op": "line_to", "x": 140 + stem_w, "y": 100},
           {"op": "line_to", "x": 140, "y": 100},
           {"op": "close"}]
    fit = [dict(c) for c in src]
    for c in fit:
        if c.get("x") == 140 + stem_w:
            c["x"] = 140 + stem_fit
    return src, fit


class ReferenceTests(unittest.TestCase):
    def test_anchor_fields_and_vertical_only(self):
        # A horizontal bar is rectilinear but not an upright standard.
        src, fit = bar_stem()
        extra = [{"op": "move_to", "x": 0, "y": 200},
                 {"op": "line_to", "x": 60, "y": 200},
                 {"op": "line_to", "x": 60, "y": 208},
                 {"op": "line_to", "x": 0, "y": 208},
                 {"op": "close"}]
        src = src + extra
        fit = fit + [dict(c) for c in extra]
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        self.assertEqual(ref["n_anchors"], 1)
        anchor = ref["anchors"][0]
        self.assertAlmostEqual(anchor["source_width"], 10.0)
        self.assertAlmostEqual(anchor["fitted_width"], 10.0)
        self.assertAlmostEqual(anchor["rel"], 0.0)
        self.assertGreater(anchor["length"], 0.0)
        self.assertEqual(len(anchor["tangent"]), 2)
        self.assertTrue(anchor["source_ids"].startswith("r0:"))

    def test_anchor_rel_follows_fitted_change(self):
        src, fit = bar_stem(stem_fit=9.0)
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        self.assertAlmostEqual(ref["anchors"][0]["rel"], -0.1)

    def test_empty_reference_abstains(self):
        ref = {"anchors": [], "size_px": 16.0}
        src, fit = bar_stem(stem_fit=9.0)
        out = dd.fit_glyph(src, fit, 16.0, ref)
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "no-reference-anchors")
        self.assertIs(out["candidate_commands"], fit)


class GeometryMappingTests(unittest.TestCase):
    def test_edge_point_uses_cut_mapping(self):
        # A foot at portion fraction 0 sits at edge fraction t0,
        # never at the edge start: virtual cuts keep affine mapping.
        side = {"i0": 0, "i1": 1, "t0": 0.25, "t1": 0.75}
        coords = [(0.0, 0.0), (100.0, 0.0)]
        p0 = dd._edge_point(side, 0.0, coords)
        p1 = dd._edge_point(side, 1.0, coords)
        self.assertAlmostEqual(p0[0], 25.0)
        self.assertAlmostEqual(p1[0], 75.0)

    def test_index_map_skips_offcurve(self):
        # parse_commands counts oncurve points only; controls take
        # no oncurve index, so quad/curve advance one step each.
        cmds = [{"op": "move_to", "x": 0, "y": 0},
                {"op": "quad_to", "x1": 1, "y1": 1, "x": 2, "y": 0},
                {"op": "curve_to", "x1": 3, "y1": 1, "x2": 4, "y2": 1,
                 "x": 5, "y": 0},
                {"op": "line_to", "x": 6, "y": 0},
                {"op": "close"}]
        table = dd._index_map(cmds)
        self.assertEqual(table, {0: 0, 1: 1, 2: 2, 3: 3})
        parsed = real_outline.parse_commands(cmds)
        self.assertEqual(len(parsed["oncurve"]), 4)
        self.assertEqual(len(parsed["offcurve"]), 3)

    def test_rect_single_medial_pair(self):
        # A 100x50 rectangle has one certifiable pair: the 100-wide
        # caps cannot clear the 50 height, so forcing two pairs
        # would certify a false medial branch.
        cmds = [{"op": "move_to", "x": 0, "y": 0},
                {"op": "line_to", "x": 100, "y": 0},
                {"op": "line_to", "x": 100, "y": 50},
                {"op": "line_to", "x": 0, "y": 50},
                {"op": "close"}]
        parsed = real_outline.parse_commands(cmds)
        portions, _, loops, _ = dd._split_visible(parsed)
        pairs, _ = dd._recognize(portions, loops)
        self.assertEqual(len(pairs), 1)


class WidthArmTests(unittest.TestCase):
    def test_bar_couples_to_anchor(self):
        src, fit = bar_stem(stem_fit=9.0)
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        out = dd.fit_glyph(src, fit, 16.0, ref, (False, False), False)
        self.assertTrue(out["applied"], out["reason"])
        self.assertEqual(out["reason"], "applied")
        # Target is 9.8995 * 0.9 = 8.9096; the joint solve balances
        # coupling against shape rows, so assert movement toward
        # the target with a residual, never exact arrival.
        self.assertLess(out["widths"]["candidate"],
                        out["widths"]["upstream"])
        self.assertGreater(out["widths"]["candidate"], 8.5)
        self.assertLess(out["validity"]["cost_candidate"],
                        out["validity"]["cost_upstream"])

    def test_weighted_anchor_mean(self):
        # Two anchors at rel -0.1 and -0.3: the achieved diagonal
        # change follows the psi-weighted mean, not either anchor.
        r1 = bar_stem(stem_fit=9.0)
        r2 = bar_stem(stem_fit=7.0, dx=300.0)
        recs = [{"source_commands": s, "fitted_commands": f}
                for s, f in (r1, r2)]
        ref = dd.build_reference(recs, 16.0)
        out = dd.fit_glyph(r1[0], r1[1], 16.0, ref, (False, False),
                           False)
        self.assertTrue(out["applied"], out["reason"])
        pair = out["pairs"][0]
        achieved = pair["candidate_width"] / pair["source_width"] - 1
        tangent = np.array([1.0, 1.0]) / math.sqrt(2.0)
        num, den = 0.0, 0.0
        for anchor in ref["anchors"]:
            psi = width_weight(pair["source_width"],
                               anchor["source_width"], tangent,
                               np.asarray(anchor["tangent"]), 16.0)
            num += anchor["length"] * psi * anchor["rel"]
            den += anchor["length"] * psi
        self.assertAlmostEqual(achieved, num / den, delta=0.05)

    def test_translation_invariance(self):
        src, fit = bar_stem(stem_fit=9.0)
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        out = dd.fit_glyph(src, fit, 16.0, ref, (False, False), False)
        src2, fit2 = bar_stem(stem_fit=9.0, dx=17.5, dy=-3.25)
        ref2 = dd.build_reference([{"source_commands": src2,
                                    "fitted_commands": fit2}], 16.0)
        out2 = dd.fit_glyph(src2, fit2, 16.0, ref2, (False, False),
                            False)
        self.assertTrue(out2["applied"])
        self.assertAlmostEqual(out["widths"]["candidate"],
                               out2["widths"]["candidate"], places=9)

    def test_reflection_applies(self):
        src, fit = bar_stem(stem_fit=9.0, mirror=True)
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        out = dd.fit_glyph(src, fit, 16.0, ref, (False, False), False)
        self.assertTrue(out["applied"], out["reason"])
        self.assertLess(out["widths"]["candidate"],
                        out["widths"]["upstream"])

    def test_native_x_frozen_bit_exact(self):
        src, fit = bar_stem(stem_fit=9.0)
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        out = dd.fit_glyph(src, fit, 16.0, ref, (True, False), False)
        cand = out["candidate_commands"]
        for before, after in zip(fit, cand):
            if "x" in before:
                self.assertEqual(before["x"], after["x"])
        self.assertEqual(out["fixed"]["native_axes"], [True, False])

    def test_fully_frozen_falls_back_exact(self):
        src, fit = bar_stem(stem_fit=9.0)
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        out = dd.fit_glyph(src, fit, 16.0, ref, (True, True), False)
        self.assertFalse(out["applied"])
        self.assertIs(out["candidate_commands"], fit)

    def test_malformed_falls_back(self):
        src, fit = bar_stem(stem_fit=9.0)
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        bad = [dict(c) for c in fit]
        bad[1] = {"op": "quad_to", "x1": 1, "y1": 1, "x": 2, "y": 0}
        out = dd.fit_glyph(src, bad, 16.0, ref)
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "no-correspondence")
        self.assertIs(out["candidate_commands"], bad)


class GridArmTests(unittest.TestCase):
    def test_integer_line_separation(self):
        # 45-degree bar, normal 1.3, anchor rel +0.1: the coupled
        # normal 1.43 spans 2.02 axis units and rounds to 2, while
        # projecting the normal chord onto x gives 1.01 and rounds
        # to 1. The integer must come from normal over |n_axis|.
        hw = 1.3 * math.sqrt(2.0)
        src = [{"op": "move_to", "x": 0, "y": 0},
               {"op": "line_to", "x": 10, "y": 10},
               {"op": "line_to", "x": 10 + hw, "y": 10},
               {"op": "line_to", "x": hw, "y": 0},
               {"op": "close"},
               {"op": "move_to", "x": 20, "y": 0},
               {"op": "line_to", "x": 21.3, "y": 0},
               {"op": "line_to", "x": 21.3, "y": 10},
               {"op": "line_to", "x": 20, "y": 10},
               {"op": "close"}]
        fit = [dict(c) for c in src]
        for c in fit:
            if c.get("x") == 21.3:
                c["x"] = 21.43
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        out = dd.fit_glyph(src, fit, 16.0, ref, (False, False), True)
        self.assertTrue(out["applied"], out["reason"])
        gate = out["pairs"][0]["grid"]
        self.assertEqual(gate["integer"], 2)
        # The ideal integer is exact; its 26.6 representation carries
        # up to the documented two-HEADROOM allowance per difference.
        self.assertLessEqual(abs(gate["sep_residual"]),
                             2 * dd.HEADROOM + 1e-12)
        for value in out["validity"]["hard_rounded"]:
            self.assertLessEqual(abs(value), 2 * dd.HEADROOM)

    def test_grid_differs_from_width_only(self):
        src, fit = bar_stem(stem_fit=9.0)
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        plain = dd.fit_glyph(src, fit, 16.0, ref, (False, False),
                             False)
        grid = dd.fit_glyph(src, fit, 16.0, ref, (False, False), True)
        self.assertTrue(plain["applied"])
        self.assertTrue(grid["applied"])
        self.assertIsNotNone(grid["pairs"][0]["grid"])
        self.assertIsNone(plain["pairs"][0]["grid"])
        self.assertNotAlmostEqual(plain["widths"]["candidate"],
                                  grid["widths"]["candidate"])

    def test_taper_declines_grid_keeps_width(self):
        # Spread beyond Hobby 3.4 (10) gamma declines the integer
        # arm; the width arm still applies through (17) rows. The
        # reason must say width-only, never claim phase fitting.
        sq = math.sqrt(2.0)
        src = [{"op": "move_to", "x": 0, "y": 0},
               {"op": "line_to", "x": 100, "y": 100},
               {"op": "line_to", "x": 100 + 8 * sq, "y": 100},
               {"op": "line_to", "x": 14.5 * sq, "y": 0},
               {"op": "close"},
               {"op": "move_to", "x": 140, "y": 0},
               {"op": "line_to", "x": 150, "y": 0},
               {"op": "line_to", "x": 150, "y": 100},
               {"op": "line_to", "x": 140, "y": 100},
               {"op": "close"}]
        fit = [dict(c) for c in src]
        for c in fit:
            if c.get("x") == 150:
                c["x"] = 149
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        out = dd.fit_glyph(src, fit, 16.0, ref, (False, False), True)
        self.assertTrue(out["applied"], out["reason"])
        self.assertEqual(out["reason"], "applied-width-only")
        self.assertFalse(out["phase_applied"])
        self.assertIsNone(out["pairs"][0]["grid"])
        self.assertFalse(out["pairs"][0]["phase_applied"])
        self.assertLess(out["widths"]["candidate"],
                        out["widths"]["upstream"])


class MulticontourTests(unittest.TestCase):
    def test_crossing_arms_apply_jointly(self):
        src, fit = wide_x()
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        for grid in (False, True):
            out = dd.fit_glyph(src, fit, 16.0, ref, (False, False),
                               grid)
            self.assertTrue(out["applied"], (grid, out["reason"]))
            self.assertEqual(len(out["pairs"]), 4)
            for pair in out["pairs"]:
                self.assertAlmostEqual(pair["source_width"], 14.1421,
                                       places=3)

    def test_exact_tangent_crossing_abstains(self):
        # Near-tangent vertex events are the sibling interval
        # model's documented abstention: no roots are guessed.
        src = [{"op": "move_to", "x": 0, "y": 0},
               {"op": "line_to", "x": 100, "y": 100},
               {"op": "line_to", "x": 114, "y": 100},
               {"op": "line_to", "x": 14, "y": 0},
               {"op": "close"},
               {"op": "move_to", "x": 14, "y": 100},
               {"op": "line_to", "x": 114, "y": 0},
               {"op": "line_to", "x": 100, "y": 0},
               {"op": "line_to", "x": 0, "y": 100},
               {"op": "close"},
               {"op": "move_to", "x": 140, "y": 0},
               {"op": "line_to", "x": 150, "y": 0},
               {"op": "line_to", "x": 150, "y": 100},
               {"op": "line_to", "x": 140, "y": 100},
               {"op": "close"}]
        fit = [dict(c) for c in src]
        for c in fit:
            if c.get("x") == 150:
                c["x"] = 149
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        out = dd.fit_glyph(src, fit, 16.0, ref, (False, False), False)
        self.assertFalse(out["applied"])
        reasons = {s["reason"] for s in out["skipped"]}
        self.assertIn("no-dominance-uncertain-equality", reasons)
        self.assertIs(out["candidate_commands"], fit)

    def test_shared_join_single_unknown(self):
        # A bar sharing the stem's corner vertex solves it once:
        # the joint command carries one fitted coordinate pair.
        src = [{"op": "move_to", "x": 140, "y": 0},
               {"op": "line_to", "x": 240, "y": 100},
               {"op": "line_to", "x": 254, "y": 100},
               {"op": "line_to", "x": 154, "y": 0},
               {"op": "close"},
               {"op": "move_to", "x": 140, "y": 0},
               {"op": "line_to", "x": 150, "y": 0},
               {"op": "line_to", "x": 150, "y": 100},
               {"op": "line_to", "x": 140, "y": 100},
               {"op": "close"}]
        fit = [dict(c) for c in src]
        for c in fit:
            if c.get("x") == 150:
                c["x"] = 149
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        out = dd.fit_glyph(src, fit, 16.0, ref, (False, False), False)
        if out["applied"]:
            table = dd._index_map(fit)
            counts = {}
            for idx, pos in table.items():
                counts[pos] = counts.get(pos, 0) + 1
            self.assertTrue(all(v == 1 for v in counts.values()))
        else:
            self.assertIn(out["reason"],
                          ("all-abstained", "invalid-candidate",
                           "no-cost-decrease"))


class BitsTests(unittest.TestCase):
    def test_moved_bits_valid_f32(self):
        src, fit = bar_stem(stem_fit=9.0)
        for c in fit:
            for key in ("x", "y"):
                if key in c:
                    c[key + "_bits"] = dd._f32bits(c[key])
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        out = dd.fit_glyph(src, fit, 16.0, ref, (False, False), False)
        self.assertTrue(out["applied"])
        for before, after in zip(fit, out["candidate_commands"]):
            for key in ("x", "y"):
                if key not in before:
                    continue
                if after[key] != before[key]:
                    packed = struct.pack(">f", after[key])
                    self.assertEqual(after[key + "_bits"],
                                     struct.unpack(">I", packed)[0])
                    self.assertEqual(after[key] % (1 / 64), 0.0)
                else:
                    self.assertEqual(after[key + "_bits"],
                                     before[key + "_bits"])


def far_curve_contour():
    # Control box x[-50,150] y[-200,25] overlaps the rect while the
    # true curve passes near y=-87, far from every rect portion: a
    # zero bbox distance with no actual contact anywhere.
    return [{"op": "move_to", "x": -50, "y": 25},
            {"op": "quad_to", "x1": 50, "y1": -200,
             "x": 150, "y": 25},
            {"op": "line_to", "x": 150, "y": 60},
            {"op": "line_to", "x": -50, "y": 60},
            {"op": "close"}]


class ConstrainedSolveTests(unittest.TestCase):
    def test_underdetermined_keeps_full_nullspace(self):
        # Two unknowns, one hard row x = 0, one soft row y = 3:
        # the nullspace must carry y to 3, not pin it at zero.
        import numpy as np
        soft = [("soft", np.array([0.0, 1.0]), -3.0)]
        hard = [("hard", np.array([1.0, 0.0]), 0.0)]
        solved = dd._solve_constrained(soft, hard, {}, 1)
        self.assertAlmostEqual(solved[0], 0.0, places=9)
        self.assertAlmostEqual(solved[1], 3.0, places=9)

    def test_overdetermined_hard_still_exact(self):
        # More hard rows than variables: the particular solution
        # satisfies them exactly and soft rows only share leftovers.
        import numpy as np
        soft = [("soft", np.array([1.0, 1.0]), -1.0)]
        hard = [("hard", np.array([1.0, 0.0]), 0.0),
                ("hard", np.array([0.0, 1.0]), 0.0),
                ("hard", np.array([1.0, 1.0]), 0.0)]
        solved = dd._solve_constrained(soft, hard, {}, 1)
        self.assertAlmostEqual(solved[0], 0.0, places=9)
        self.assertAlmostEqual(solved[1], 0.0, places=9)


class InvalidReportingTests(unittest.TestCase):
    def test_rejected_attempt_resets_phase_and_movement(self):
        # A rejected grid candidate (hard rows fine, another gate
        # fails) must deliver fallback pairs with no phase claim and
        # zero movement, while the attempt retains its measure.
        from unittest import mock
        src, fit = bar_stem(stem_fit=9.0)
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        real = dd._validate

        def forced(*args, **kwargs):
            validity = real(*args, **kwargs)
            return dict(validity, ok=False, stage="forced-topology",
                        topology=False)

        with mock.patch.object(dd, "_validate", forced):
            out = dd.fit_glyph(src, fit, 16.0, ref, (False, False),
                               True)
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "invalid-candidate")
        self.assertIs(out["candidate_commands"], fit)
        self.assertTrue(all(p["phase_applied"] is False
                            for p in out["pairs"]))
        self.assertEqual(out["movement"], 0.0)
        self.assertAlmostEqual(out["widths"]["candidate"],
                               out["widths"]["upstream"])
        attempt = out["attempt"]
        self.assertGreater(attempt["movement"], 0.0)
        self.assertFalse(dd._commands_equal(
            attempt["attempted_commands"], fit))
        self.assertNotEqual(attempt["widths"]["candidate"],
                            out["widths"]["candidate"])


class CurveSafetyTests(unittest.TestCase):
    def test_box_zero_marks_unknown_not_hidden(self):
        # A portion midpoint inside a curve's control-hull box has
        # only a lower-bound clearance of zero, never actual contact:
        # it must abstain as unknown with cause, not hide as if the
        # winding seam were proven.
        cmds = [{"op": "move_to", "x": 0, "y": 0},
                {"op": "line_to", "x": 100, "y": 0},
                {"op": "line_to", "x": 100, "y": 50},
                {"op": "line_to", "x": 0, "y": 50},
                {"op": "close"}] + far_curve_contour()
        parsed = real_outline.parse_commands(cmds)
        portions, _, _, _ = dd._split_visible(parsed)
        causes = {p["unknown_cause"] for p in portions
                  if p["unknown"]}
        self.assertIn("box-zero", causes)
        for p in portions:
            if p["unknown_cause"] == "box-zero":
                self.assertFalse(p["hidden"])

    def test_unknown_counts_as_competitor(self):
        # Uncertain boundaries still bound medial clearance: they
        # appear in the competitor set, never silently dropped.
        cmds = [{"op": "move_to", "x": 0, "y": 0},
                {"op": "line_to", "x": 100, "y": 0},
                {"op": "line_to", "x": 100, "y": 50},
                {"op": "line_to", "x": 0, "y": 50},
                {"op": "close"}] + far_curve_contour()
        parsed = real_outline.parse_commands(cmds)
        portions, _, _, _ = dd._split_visible(parsed)
        borders = dd._visible_borders(portions)
        keys = {o["key"] for o in borders}
        seen = 0
        for p in portions:
            if p["unknown"]:
                seen += 1
                key = (p["contour"], p["seg"], p["t0"], p["t1"])
                self.assertIn(key, keys)
        self.assertGreater(seen, 0)

    def test_curve_incident_endpoint_stays_fitted(self):
        # A straight edge meeting a curve shares its endpoint with
        # an uncertifiable region: the joint stays at upstream even
        # when the diagonal pair otherwise applies.
        src = [{"op": "move_to", "x": 0, "y": 0},
               {"op": "line_to", "x": 100, "y": 100},
               {"op": "line_to", "x": 114, "y": 100},
               {"op": "quad_to", "x1": 60, "y1": 40,
                "x": 14, "y": 0},
               {"op": "close"},
               {"op": "move_to", "x": 140, "y": 0},
               {"op": "line_to", "x": 150, "y": 0},
               {"op": "line_to", "x": 150, "y": 100},
               {"op": "line_to", "x": 140, "y": 100},
               {"op": "close"}]
        fit = [dict(c) for c in src]
        for c in fit:
            if c.get("x") == 150:
                c["x"] = 149
        ref = dd.build_reference([{"source_commands": src,
                                   "fitted_commands": fit}], 16.0)
        out = dd.fit_glyph(src, fit, 16.0, ref, (False, False), False)
        parsed = real_outline.parse_commands(src)
        curved = set()
        for contour in parsed["contours"]:
            for seg in contour:
                if seg[0] != "line":
                    curved.add(seg[-2])
                    curved.add(seg[-1])
        # The freeze set itself must own every curve-incident vertex,
        # whether or not a pair applied around it.
        self.assertTrue(curved <= set(out["fixed"]["anchors"]))
        cand = out["candidate_commands"]
        table = dd._index_map(fit)
        for v in curved:
            pos = table.get(v)
            if pos is None:
                continue
            self.assertEqual(cand[pos]["x"], fit[pos]["x"])
            self.assertEqual(cand[pos]["y"], fit[pos]["y"])




class IntegerIntervalSourceTests(unittest.TestCase):
    def test_hobby_width_spread_scales_as_inverse_sqrt(self):
        # Hobby (10): gamma_2/sqrt(w_max), not a percentage of mean width.
        # The straight bisector has zero direction spread. Wide and narrow
        # analytic intervals distinguish the two formulas without any glyphs.
        q = math.sqrt(0.5)
        def gate(lo, hi, rel):
            info = {"src_widths": [lo, hi], "direction": (q, q),
                    "normal": (-q, q), "stations": [{"hit": {
                        "qa": (0., 0.), "qb": (-q, q), "sa": .5, "sb": .5}}]}
            anchors = [{"length": 1., "source_width": (lo + hi) / 2,
                        "rel": rel, "tangent": (0., 1.)}]
            return dd._grid_target(info, anchors, 16.)
        self.assertIsNone(gate(3.8, 4., 0.))  # .2 > .25/sqrt(4)
        self.assertIsNotNone(gate(.2, .5, 2.))  # .3 < .25/sqrt(.5)


if __name__ == "__main__":
    unittest.main()
