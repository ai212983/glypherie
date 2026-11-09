"""The review adapter's geometry and safeguards, not optical acceptance."""
import copy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blind_review import CompleteCellModel, CompleteCellSolver, CONTROL, schedule
import filtered_walls as walls
import hu_hersch as hu
from solver import Controls, Solver
from test_hu_density import complete_capture, glyph


class BlindReviewTests(unittest.TestCase):
    def test_balanced_positions_and_reversed_repeats(self):
        trials = schedule(4, 7, "repeatable")
        self.assertEqual(trials, schedule(4, 7, "repeatable"))
        self.assertEqual(len({(t["font"], t["preset"]) for t in trials}), 28)
        self.assertEqual(sum(t["order"][0] == 0 for t in trials), 14)
        for trial in trials:
            self.assertEqual(sorted(trial["order"]), [0, 1])
            self.assertEqual(list(reversed(trial["order"]))[0], trial["order"][1])

    def test_complete_cells_match_direct_walls_outside_body_before_cropping(self):
        capture = complete_capture()
        # Asymmetric lips, a missing row, negative bearings and ink beyond body.
        bitmap = dict(left=-2, top=-6, width=4, height=8,
                      pixels=[1,1,1,1, 1,0,0,0, 1,0,0,0, 0,0,0,0,
                              1,0,0,0, 1,1,1,0, 0,0,1,0, 0,0,1,0])
        glyph(capture, "a")["bitmap"] = bitmap
        original = copy.deepcopy(capture)
        model = CompleteCellModel(capture, 8)
        profile = model._profile(ord("a"), (0., 4.), "fitted_outline")
        full = walls.bitmap_profile(bitmap, profile.construction_window, 8)
        direct = hu._depth_profile(full, model.settings, body_height=4., post_b_cavities=True)
        start = round((profile.window[0]-profile.construction_window[0])*8)
        for field in ("left", "right", "occupied", "filtered_left", "filtered_right"):
            self.assertEqual(getattr(profile, field), getattr(direct, field)[start:start+len(profile.ys)])
        self.assertEqual(capture, original)

    def test_all_domains_conserve_continuous_source_mean_without_reading_text(self):
        capture = complete_capture()
        model = CompleteCellModel(capture, 8)
        for record in model.metadata()["classes"].values():
            self.assertEqual(record["status"], "available")
            values = [model.pair(a, b)["optical_step_px"] for product in record["pair_domain"]["products"]
                      for a in product["left_codepoints"] for b in product["right_codepoints"]]
            self.assertAlmostEqual(math.fsum(values)/len(values), record["mean_source_step_px"])

    def test_metric_fallbacks_and_optical_zero_are_preserved(self):
        capture = complete_capture()
        capture["tabular_digits"] = True
        cell, control = CompleteCellSolver(capture), Solver(capture)
        cases = [("ab", Controls(spacing_model=CONTROL, optical=0)),
                 ("12", Controls(spacing_model=CONTROL, preserve_tabular_spacing=True)),
                 ("a ", Controls(spacing_model=CONTROL))]
        for pair, controls in cases:
            a, b = map(ord, pair)
            actual, expected = cell.pair(a, b, controls), control.pair(a, b, controls)
            self.assertEqual(actual["automatic_adjustment_px"], expected["automatic_adjustment_px"])
            self.assertEqual(actual["reason"], expected["reason"])
        capture["monospace"] = True
        self.assertEqual(CompleteCellSolver(capture).pair(97, 98, Controls(spacing_model=CONTROL))["reason"], "fixed_pitch")


if __name__ == "__main__":
    unittest.main()
