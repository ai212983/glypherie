#!/usr/bin/env python3
"""Contract tests for the shape-balance review harness (synthetic data only).

Hand-built fixtures pin harness input, composition, provenance, layout and
fail-closed contracts. They never execute the placement model except for
one live entry-point shape check, and never mirror harness internals.
"""

import copy
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from experiments.hobby_fitting import shape_balance_review as review


def move(x, y):
    return {"op": "move_to", "x": x, "y": y,
            "x_bits": review.f32_bits(x), "y_bits": review.f32_bits(y)}


def line(x, y):
    return {"op": "line_to", "x": x, "y": y,
            "x_bits": review.f32_bits(x), "y_bits": review.f32_bits(y)}


UPSTREAM = [move(2.0, 9.0), line(4.0, 0.0), {"op": "close"}]
PREFERRED = [move(2.5, 9.0), line(4.0, 0.0), {"op": "close"}]
SOURCE = [move(2.5, 9.0), line(4.0, 0.0), {"op": "close"}]


class AvailabilityTest(unittest.TestCase):
    def test_missing_module_reports_name(self):
        module, error = review.load_placement_module(
            "experiments.hobby_fitting.no_such_module")
        self.assertIsNone(module)
        self.assertIn("no_such_module", error)

    def test_live_module_exposes_planned_fit_entry(self):
        module, error = review.load_placement_module()
        self.assertIsNone(error)
        self.assertTrue(callable(getattr(module, "fit", None)))
        box = [move(1.0, 1.0), line(3.0, 1.0), line(3.0, 5.0),
               line(1.0, 5.0), {"op": "close"}]
        result = review.call_placement(module, box, box, 16.0, (False, False),
                                    review.ARM_PHASE)
        for key in ("commands", "applied", "reason", "diagnostics"):
            self.assertIn(key, result)

    def test_missing_fit_entry_fails_nonzero(self):
        class Fake:
            pass

        with self.assertRaises(SystemExit):
            review.call_placement(Fake(), SOURCE, PREFERRED, 16.0,
                                  (False, False), review.ARM_PHASE)

    def test_raising_fit_fails_nonzero(self):
        class Fake:
            def fit(self, *args):
                raise RuntimeError("boom")

        with self.assertRaises(SystemExit):
            review.call_placement(Fake(), SOURCE, PREFERRED, 16.0,
                                  (False, False), review.ARM_PHASE)

    def test_malformed_result_fails_nonzero(self):
        for bad in ({"applied": False, "reason": "x"},
                    {"applied": False, "reason": "x",
                     "diagnostics": [], "commands": []},
                    {"applied": False, "reason": "x", "diagnostics": {},
                     "commands": {}}):
            class Fake:
                def __init__(self, result):
                    self._result = result

                def fit(self, *args):
                    return self._result

            with self.assertRaises(SystemExit):
                review.call_placement(Fake(bad), SOURCE, PREFERRED, 16.0,
                                      (False, False), review.ARM_PHASE)


class FallbackContractTest(unittest.TestCase):
    def test_geometric_abstention_replays_preferred(self):
        class Fake:
            def fit(self, source, upstream, size_px, native_axes, arm=None):
                return {"commands": list(upstream), "applied": False,
                        "reason": "no-near-reflection", "diagnostics": {}}

        out = review.place_glyph(SOURCE, PREFERRED, 16.0, [False, False],
                                 Fake(), review.ARM_PHASE)
        self.assertFalse(out["applied"])
        self.assertEqual(out["reason"], "no-near-reflection")
        self.assertEqual(out["candidate_commands"], PREFERRED)

    def test_abstention_with_changed_commands_fails(self):
        class Fake:
            def fit(self, source, upstream, size_px, native_axes, arm=None):
                return {"commands": list(UPSTREAM), "applied": False,
                        "reason": "no-near-reflection", "diagnostics": {}}

        with self.assertRaises(SystemExit):
            review.place_glyph(SOURCE, PREFERRED, 16.0, [False, False],
                                 Fake(), review.ARM_PHASE)

    def test_applied_skeleton_change_fails(self):
        class Fake:
            def fit(self, source, upstream, size_px, native_axes, arm=None):
                return {"commands": [move(1.0, 1.0)], "applied": True,
                        "reason": "x", "diagnostics": {}}

        with self.assertRaises(SystemExit):
            review.place_glyph(SOURCE, PREFERRED, 16.0, [False, False],
                                 Fake(), review.ARM_PHASE)

    def test_applied_bad_bits_fail(self):
        bad = [move(2.5, 9.0),
               {"op": "line_to", "x": 4.0, "y": 0.0,
                "x_bits": 1, "y_bits": 0}, {"op": "close"}]

        class Fake:
            def fit(self, source, upstream, size_px, native_axes, arm=None):
                return {"commands": bad, "applied": True, "reason": "x",
                        "diagnostics": {}}

        with self.assertRaises(SystemExit):
            review.place_glyph(SOURCE, PREFERRED, 16.0, [False, False],
                                 Fake(), review.ARM_PHASE)

    def test_applied_bool_coordinate_fails(self):
        bad = [move(2.5, 9.0),
               {"op": "line_to", "x": True, "y": 0.0,
                "x_bits": review.f32_bits(1.0),
                "y_bits": review.f32_bits(0.0)}, {"op": "close"}]

        class Fake:
            def fit(self, source, upstream, size_px, native_axes, arm=None):
                return {"commands": bad, "applied": True, "reason": "x",
                        "diagnostics": {}}

        with self.assertRaises(SystemExit):
            review.place_glyph(SOURCE, PREFERRED, 16.0, [False, False],
                                 Fake(), review.ARM_PHASE)

    def test_signed_zero_pin_change_fails(self):
        pos = move(0.0, 1.0)
        neg = dict(pos, x=-0.0, x_bits=review.f32_bits(-0.0))
        self.assertEqual(pos["x"], neg["x"])
        self.assertNotEqual(pos["x_bits"], neg["x_bits"])
        cand = [neg, line(4.0, 0.0), {"op": "close"}]
        base = [pos, line(4.0, 0.0), {"op": "close"}]

        class Fake:
            def fit(self, source, upstream, size_px, native_axes, arm=None):
                return {"commands": cand, "applied": True, "reason": "x",
                        "diagnostics": {}}

        with self.assertRaises(SystemExit):
            review.place_glyph(base, base, 16.0, [True, False], Fake(),
                               review.ARM_PHASE)

    def test_malformed_native_axes_fail_closed(self):
        class Fake:
            def fit(self, source, upstream, size_px, native_axes, arm=None):
                return {"commands": list(upstream), "applied": False,
                        "reason": "x", "diagnostics": {}}

        for bad_axes in ([0, 1], [False], None, "xy", [False, False, False]):
            with self.assertRaises(SystemExit):
                review.place_glyph(SOURCE, PREFERRED, 16.0, bad_axes, Fake(),
                                   review.ARM_PHASE)

    def test_applied_shift_reports_diagnostics(self):
        moved = [move(3.0, 9.0), line(4.5, 0.0), {"op": "close"}]

        class Fake:
            def fit(self, source, upstream, size_px, native_axes, arm=None):
                return {"commands": moved, "applied": True,
                        "reason": "certified",
                        "diagnostics": {"source_axis": 3.5}}

        out = review.place_glyph(SOURCE, PREFERRED, 16.0, [False, False],
                                 Fake(), review.ARM_PHASE)
        self.assertTrue(out["applied"])
        self.assertEqual(out["candidate_commands"], moved)
        self.assertEqual(out["diagnostics"]["shift_px"], [0.5, 0.0])


class PlacementArmTest(unittest.TestCase):
    def test_arm_forwarded_to_fit(self):
        seen = {}

        class Fake:
            def fit(self, source, upstream, size_px, native_axes, arm=None):
                seen["arm"] = arm
                return {"commands": list(upstream), "applied": False,
                        "reason": "no-near-reflection", "diagnostics": {}}

        review.place_glyph(SOURCE, PREFERRED, 16.0, [False, False], Fake(),
                           review.ARM_CONTROL)
        self.assertEqual(seen["arm"], review.ARM_CONTROL)

    def test_unknown_arm_fails_nonzero(self):
        class Fake:
            def fit(self, *args, **kwargs):
                return {"commands": [], "applied": False, "reason": "x",
                        "diagnostics": {}}

        with self.assertRaises(SystemExit):
            review.call_placement(Fake(), SOURCE, PREFERRED, 16.0,
                                  (False, False), "no-such-arm")

    def test_spot_entry_marks_identical_bitmap(self):
        same = review.spot_entry("x", True, "applied-phase-range",
                                 [0.046875, 0.0], [0, 1, 1], [0, 1, 1])
        self.assertTrue(same["identical_bitmap"])
        self.assertEqual(same["shift_px"], [0.046875, 0.0])
        changed = review.spot_entry("x", True, "applied-phase-range",
                                    [0.5, 0.0], [0, 1, 1], [0, 0, 1])
        self.assertFalse(changed["identical_bitmap"])


class CurveArmTest(unittest.TestCase):
    REF = {"anchors": []}
    GOOD_TOPOLOGY = {"supported": True, "ok": True}

    def test_missing_kernel_reports_name(self):
        module, error = review.load_curve_module(
            "experiments.hobby_fitting.no_such_curve_module")
        self.assertIsNone(module)
        self.assertIn("no_such_curve_module", error)

    def test_valid_applied_kernel_accepted(self):
        moved = [move(3.0, 9.0), line(4.5, 0.0), {"op": "close"}]

        class Fake:
            def fit_glyph(self, source, upstream, size_px, reference,
                          native_axes=(False, False)):
                return {"candidate_commands": moved, "applied": True,
                        "reason": "fitted",
                        "diagnostics": {"n_pairs": 1},
                        "recognition": {"contacts": 1},
                        "widths": [{"source": 1.0}],
                        "topology": dict(
                            CurveArmTest.GOOD_TOPOLOGY)}

        out = review.curve_glyph(Fake(), SOURCE, PREFERRED, 16.0,
                                 dict(self.REF), [False, False])
        self.assertTrue(out["applied"])
        self.assertEqual(out["candidate_commands"], moved)
        self.assertEqual(out["widths"], [{"source": 1.0}])
        self.assertTrue(out["topology"]["ok"])

    def test_applied_identical_commands_kept_honestly(self):
        class Fake:
            def fit_glyph(self, source, upstream, size_px, reference,
                          native_axes=(False, False)):
                return {"candidate_commands": list(upstream), "applied": True,
                        "reason": "fitted", "diagnostics": {},
                        "recognition": {}, "widths": [],
                        "topology": dict(
                            CurveArmTest.GOOD_TOPOLOGY)}

        out = review.curve_glyph(Fake(), SOURCE, PREFERRED, 16.0,
                                 dict(self.REF), [False, False])
        self.assertTrue(out["applied"])
        self.assertEqual(out["candidate_commands"], PREFERRED)

    def test_geometric_abstention_replays_placement(self):
        class Fake:
            def fit_glyph(self, source, upstream, size_px, reference,
                          native_axes=(False, False)):
                return {"candidate_commands": list(upstream), "applied": False,
                        "reason": "no-certified-pairs", "widths": None,
                        "recognition": {}}

        out = review.curve_glyph(Fake(), SOURCE, PREFERRED, 16.0,
                                 dict(self.REF), [False, False])
        self.assertFalse(out["applied"])
        self.assertEqual(out["candidate_commands"], PREFERRED)

    def test_abstention_changed_commands_fails(self):
        class Fake:
            def fit_glyph(self, source, upstream, size_px, reference,
                          native_axes=(False, False)):
                return {"candidate_commands": list(UPSTREAM), "applied": False,
                        "reason": "no-certified-pairs", "widths": None}

        with self.assertRaises(SystemExit):
            review.curve_glyph(Fake(), SOURCE, PREFERRED, 16.0,
                               dict(self.REF), [False, False])

    def test_bad_topology_fails(self):
        for topology in (None, {}, {"supported": True},
                         {"supported": True, "ok": False},
                         {"supported": False, "ok": True}):
            moved = [move(3.0, 9.0), line(4.5, 0.0), {"op": "close"}]

            class Fake:
                def __init__(self, topo):
                    self._topo = topo

                def fit_glyph(self, source, upstream, size_px, reference,
                              native_axes=(False, False)):
                    return {"candidate_commands": moved, "applied": True,
                            "reason": "fitted", "diagnostics": {},
                            "widths": [], "topology": self._topo}

            with self.assertRaises(SystemExit):
                review.curve_glyph(Fake(topology), SOURCE, PREFERRED, 16.0,
                                   dict(self.REF), [False, False])

    def test_pin_bits_violation_fails(self):
        pos = move(0.0, 1.0)
        neg = dict(pos, x=-0.0, x_bits=review.f32_bits(-0.0))
        cand = [neg, line(4.0, 0.0), {"op": "close"}]
        base = [pos, line(4.0, 0.0), {"op": "close"}]

        class Fake:
            def fit_glyph(self, source, upstream, size_px, reference,
                          native_axes=(False, False)):
                return {"candidate_commands": cand, "applied": True,
                        "reason": "fitted", "diagnostics": {},
                        "widths": [],
                        "topology": dict(CurveArmTest.GOOD_TOPOLOGY)}

        with self.assertRaises(SystemExit):
            review.curve_glyph(Fake(), base, base, 16.0, dict(self.REF),
                               [True, False])

    def test_missing_entry_and_bad_reference_fail(self):
        class Fake:
            pass

        with self.assertRaises(SystemExit):
            review.curve_glyph(Fake(), SOURCE, PREFERRED, 16.0,
                               dict(self.REF), [False, False])

        class Fake2:
            def fit_glyph(self, source, upstream, size_px, reference,
                          native_axes=(False, False)):
                return {"candidate_commands": list(upstream), "applied": False,
                        "reason": "x", "widths": None}

        with self.assertRaises(SystemExit):
            review.curve_glyph(Fake2(), SOURCE, PREFERRED, 16.0, None,
                               [False, False])

    def test_four_arm_composition_shares_union_frame(self):
        line_decl = {"text": "a", "baseline": 10,
                     "placements": [{"codepoint": 97, "x": 0, "advance": 6,
                                     "pair": 0}]}
        tile = {"left": 0, "top": -8, "width": 4, "height": 8,
                "pixels": [1] * 32}
        moved = {"left": 6, "top": -8, "width": 4, "height": 8,
                 "pixels": [1] * 32}
        one = {97: tile}
        composed = review.compose_four(line_decl, one, one, one,
                                       {97: moved})
        arms = composed["arms"]
        self.assertEqual(sorted(arms), ["curves", "placement", "preferred",
                                        "upstream"])
        for arm in arms.values():
            self.assertEqual((arm["width"], arm["height"]),
                             (composed["frame"]["width"],
                              composed["frame"]["height"]))
        self.assertNotEqual(arms["curves"]["pixels"],
                            arms["placement"]["pixels"])
        self.assertEqual(arms["upstream"]["pixels"],
                         arms["placement"]["pixels"])


class CompositionTest(unittest.TestCase):
    def test_translated_glyph_changes_frame_and_text(self):
        line_decl = {"text": "ab", "baseline": 10,
                     "placements": [{"codepoint": 97, "x": 0, "advance": 6,
                                     "pair": 0},
                                    {"codepoint": 98, "x": 6, "advance": 6,
                                     "pair": 0}]}
        tile_a = {"left": 0, "top": -8, "width": 4, "height": 8,
                  "pixels": [1] * 32}
        tile_b = {"left": 0, "top": -8, "width": 4, "height": 8,
                  "pixels": [1] * 32}
        moved_b = {"left": 6, "top": -8, "width": 4, "height": 8,
                   "pixels": [1] * 32}
        up = {97: tile_a, 98: tile_b}
        composed = review.compose_three(line_decl, up, up,
                                        {97: tile_a, 98: moved_b})
        arms = composed["arms"]
        for arm in ("upstream", "preferred", "placement"):
            self.assertEqual(arms[arm]["width"], 16)
        self.assertNotEqual(arms["placement"]["pixels"],
                            arms["preferred"]["pixels"])
        self.assertEqual(arms["upstream"]["pixels"],
                         arms["preferred"]["pixels"])
        for arm in ("upstream", "preferred", "placement"):
            self.assertEqual((arms[arm]["width"], arms[arm]["height"]),
                             (composed["frame"]["width"],
                              composed["frame"]["height"]))

    def test_paragraph_shares_one_frame(self):
        line_decl = {"text": "a", "baseline": 10,
                     "placements": [{"codepoint": 97, "x": 0, "advance": 6,
                                     "pair": 0}]}
        tile = {"left": 0, "top": -8, "width": 4, "height": 8,
                "pixels": [1] * 32}
        moved = {"left": 2, "top": -8, "width": 4, "height": 8,
                 "pixels": [1] * 32}
        para = review.compose_paragraph_three([line_decl], {97: tile},
                                              {97: tile}, {97: moved})
        self.assertEqual(para["line_baselines"], [10 + para["frame"]["origin_y"]])
        for arm in ("upstream", "preferred", "placement"):
            self.assertEqual(len(para[arm]["pixels"]),
                             para["frame"]["width"] * para["frame"]["height"])
        self.assertNotEqual(para["placement"]["pixels"],
                            para["preferred"]["pixels"])


class MatrixProvenanceTest(unittest.TestCase):
    def test_baseline_tool_and_identity(self):
        cell = {"family": "Roboto", "size": 16.0, "weight": 400.0,
                "hint_mode": "selective_default", "glyphs": [],
                "layout": {}, "harness": {"tool": "coverage-review-v1"}}
        self.assertEqual(review.check_baseline_cell(
            cell, "Roboto", 16.0, 400.0, "selective_default"), [])
        foreign = copy.deepcopy(cell)
        foreign["harness"] = {"tool": "other"}
        self.assertIn("baseline-tool", review.check_baseline_cell(
            foreign, "Roboto", 16.0, 400.0, "selective_default"))

    def test_resume_validates_identity_and_content(self):
        import tempfile
        import json

        item = {"family": "Roboto", "size": 16.0, "weight": 400.0,
                "hint_mode": "selective_default"}
        layout = {"lines": []}
        base = {"tool": "shape-balance-review-v1", "family": "Roboto",
                "size": 16.0, "weight": 400.0,
                "hint_mode": "selective_default",
                "glyphs": [{"codepoint": 97}], "lines": [], "paragraph": {},
                "layout": layout,
                "layout_sha256": review.sha_json(layout),
                "repertoire": [97],
                "baseline": {"sha256": "b"}, "ascii_capture_sha256": "a",
                "provenance": {"tool": "shape-balance-review-v1"}}
        base["cell_sha256"] = review.sha_json(
            {k: v for k, v in base.items() if k != "cell_sha256"})
        prov = {"tool": "shape-balance-review-v1"}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cell.json")
            with open(path, "w") as handle:
                json.dump(base, handle)
            self.assertTrue(review.saved_cell_valid(
                path, item, "b", "a", [97], prov))
            self.assertFalse(review.saved_cell_valid(
                path, item, "other", "a", [97], prov))
            self.assertFalse(review.saved_cell_valid(
                path, item, "b", "a", [97, 98], prov))
            tampered = copy.deepcopy(base)
            tampered["layout"] = {"lines": [{"text": "x"}]}
            with open(path, "w") as handle:
                json.dump(tampered, handle)
            self.assertFalse(review.saved_cell_valid(
                path, item, "b", "a", [97], prov))


if __name__ == "__main__":
    unittest.main()
