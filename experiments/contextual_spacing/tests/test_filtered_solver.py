"""Mechanical checks of the retained filtered-wall comparison, not optical acceptance."""
import copy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from solver import Controls, Solver
from test_calibration import calibrated_capture, with_glyphs
from test_solver import rectangle


def controls(**values):
    values.setdefault("spacing_model", "filtered_walls")
    return Controls(preserve_tabular_spacing=False, **values)


class FilteredSolverTests(unittest.TestCase):
    def test_retained_reference_calibration_and_full_endpoint(self):
        value = calibrated_capture()
        original = copy.deepcopy(value)
        solver = Solver(value)
        self.assertEqual(controls().spacing_model, "filtered_walls")
        metadata = solver.calibration_metadata(spacing_model="filtered_walls")
        self.assertEqual(metadata["measurement_method"], "hu-filtered-walls-midpoint-v1")
        self.assertEqual(metadata["classes"]["uppercase"]["measurement_window_px"], [0, 5])
        self.assertEqual(metadata["classes"]["uppercase"]["target_px"], 4.5)
        self.assertEqual(metadata["classes"]["uppercase"]["target_area_px2"], 22.5)
        pair = solver.pair(65, 86, Controls(spacing_model="filtered_walls"))
        self.assertAlmostEqual(pair["target_error_px"], .5)
        self.assertEqual(pair["realized_area_px2"], pair["realized_separation_px"] * 5)
        self.assertEqual(pair["unconstrained_step_px"], 6.5)
        self.assertEqual(pair["clearance_min_step_px"], 3)
        self.assertFalse(pair["clearance_limited"])
        self.assertEqual(value, original)
        self.assertEqual(solver.capture, original)
        metadata["classes"]["uppercase"]["target_px"] = -1
        self.assertEqual(solver.calibration_metadata(spacing_model="filtered_walls")["classes"]["uppercase"]["target_px"], 4.5)

    def test_different_facing_geometry_reaches_same_measured_target(self):
        value = with_glyphs(calibrated_capture(), (97, 101))
        # A shallow open side has real white area even though its outer bound
        # matches the rectangle; no glyph-specific production rule is involved.
        a = next(g for g in value["glyphs"] if g["codepoint"] == 97)
        a["bitmap"] = dict(left=0, top=-5, width=4, height=5,
                           pixels=[1, 1, 1, 1, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 1])
        solver = Solver(value)
        one, two = (solver.pair(*map(ord, text), controls()) for text in ("ae", "ee"))
        self.assertEqual(one["target_separation_px"], two["target_separation_px"])
        self.assertNotEqual(one["optical_adjustment_px"], two["optical_adjustment_px"])
        for pair in (one, two):
            self.assertLessEqual(abs(pair["target_error_px"]), .5)
            self.assertFalse(pair["clearance_limited"])

    def test_clearance_constraint_reports_infeasible_equalization(self):
        value = calibrated_capture()
        reference = value["source_calibration"]["references"][1]
        reference.update(source_advance_px=2.1, source_pair_adjustment_px=0)
        solver = Solver(value)
        pair = solver.pair(65, 86, Controls(spacing_model="filtered_walls"))
        self.assertAlmostEqual(pair["target_separation_px"], .1)
        self.assertAlmostEqual(pair["unconstrained_step_px"], 2.1)
        self.assertEqual(pair["rounded_unconstrained_step_px"], 2)
        self.assertEqual(pair["resolved_step_px"], 3)
        self.assertEqual(pair["clearance_adjustment_px"], 1)
        self.assertTrue(pair["clearance_limited"])
        self.assertEqual(pair["reason"], "clearance_limited")
        self.assertEqual(pair["diagnostic"], "clearance_limited")
        self.assertAlmostEqual(pair["target_error_px"], .9)
        self.assertAlmostEqual(pair["realized_area_px2"] - pair["target_area_px2"], 4.5)

    def test_positive_blend_guard_and_exact_disabled_identity(self):
        value = calibrated_capture()
        value["source_pairs"][0]["adjustment_px"] = -3
        value["metric_pairs_on"][0]["adjustment_px"] = -3
        solver = Solver(value)
        disabled = solver.pair(65, 86, controls(optical=0))
        partial = solver.pair(65, 86, controls(optical=.01))
        self.assertEqual(disabled["resolved_step_px"], 1)
        self.assertEqual(disabled["automatic_adjustment_px"], disabled["metric_adjustment_px"])
        self.assertFalse(disabled["clearance_limited"])
        self.assertEqual(partial["rounded_unconstrained_step_px"], 1)
        self.assertEqual(partial["resolved_step_px"], 3)
        self.assertTrue(partial["clearance_limited"])

    def test_full_endpoint_ignores_runtime_kerning_and_cache_order(self):
        solver = Solver(calibrated_capture())
        pairs = [solver.pair(65, 86, controls(source_kerning=k)) for k in (0, .25, .5, .75, 1)]
        self.assertEqual(len({p["resolved_step_px"] for p in pairs}), 1)
        self.assertEqual(len({p["target_separation_px"] for p in pairs}), 1)
        self.assertNotEqual(pairs[0]["metric_adjustment_px"], pairs[-1]["metric_adjustment_px"])
        before = solver.generate(controls(optical=0))
        full = solver.generate(controls())
        cached_profiles = len(solver._filtered_profiles)
        for k in (0, .25, .5, .75, 1):
            for o in (0, .25, .5, .75, 1):
                solver.generate(controls(source_kerning=k, optical=o))
        self.assertEqual(full, solver.generate(controls()))
        self.assertEqual(before, solver.generate(controls(optical=0)))
        # Pair/control history reuses completed geometry and never alters text domain.
        self.assertEqual(len(solver._filtered_profiles), cached_profiles)
        self.assertEqual(solver.generate(controls(), text="nn")["status"], "unsupported_input")

    def test_window_shared_with_shorter_glyph_and_contact_covers_outside_it(self):
        value = calibrated_capture()
        left = next(g for g in value["glyphs"] if g["codepoint"] == 65)
        left["bitmap"] = dict(left=0, top=-6, width=5, height=6,
                              pixels=[1]*5 + [1, 1, 0, 0, 0]*5)
        right = next(g for g in value["glyphs"] if g["codepoint"] == 86)
        right["bitmap"] = dict(left=0, top=-6, width=2, height=6, pixels=[1]*12)
        pair = Solver(value).pair(65, 86, Controls(spacing_model="filtered_walls"))
        self.assertEqual(pair["measurement_window_px"], [0, 5])
        self.assertEqual(pair["clearance_min_step_px"], 6, "full bitmap serif outside measurement window still counts")
        right["bitmap"] = dict(left=0, top=-3, width=2, height=3, pixels=[1]*6)
        short = Solver(value).pair(65, 86, Controls(spacing_model="filtered_walls"))
        self.assertEqual(short["measurement_window_px"], pair["measurement_window_px"])
        self.assertEqual(short["window_height_px"], 5)

    def test_fallbacks_and_explicit_outline_policy(self):
        value = with_glyphs(calibrated_capture(), (97, 101, 44))
        solver = Solver(value)
        self.assertEqual(solver.pair(32, 65, Controls(spacing_model="filtered_walls"))["reason"], "empty_geometry")
        self.assertEqual(solver.pair(44, 65, Controls(spacing_model="filtered_walls"))["reason"], "unsupported_calibration_class")
        value["tabular_digits"] = True
        self.assertEqual(Solver(value).pair(48, 49, Controls(spacing_model="filtered_walls"))["reason"], "source_tabular_digits")
        self.assertIsNone(Solver(value).pair(48, 49, controls())["reason"])
        value["source_calibration"]["references"][0] = dict(codepoint=110, status="missing_reference_glyph")
        self.assertEqual(Solver(value).pair(97, 101, Controls(spacing_model="filtered_walls"))["reason"], "calibration_unavailable")
        self.assertEqual(Solver(value, produced_geometry="fitted_outline").pair(65, 86, Controls(spacing_model="filtered_walls"))["reason"], "unsupported_geometry_policy")
        next(g for g in value["glyphs"] if g["codepoint"] == 86)["bitmap"]["top"] = -20
        self.assertEqual(Solver(value).pair(65, 86, Controls(spacing_model="filtered_walls"))["reason"], "no_shared_ink_rows")
        value["monospace"] = True
        self.assertEqual(Solver(value).pair(65, 86, Controls(spacing_model="filtered_walls"))["reason"], "fixed_pitch")

    def test_source_curve_sampling_convergence_and_identity(self):
        value = calibrated_capture()
        # Analytic curved right wall; sampling resolution is a numerical control,
        # never tuned to a preferred integer result.
        value["source_calibration"]["references"][1]["source_commands"] = [
            dict(op="move_to", x=0, y=0), dict(op="line_to", x=200, y=0),
            dict(op="quad_to", x1=100, y1=250, x=200, y=500),
            dict(op="line_to", x=0, y=500), dict(op="close")]
        solvers = [Solver(value, filtered_samples_per_px=n) for n in (32, 64, 128)]
        targets = [s.pair(65, 86, Controls(spacing_model="filtered_walls"))["target_separation_px"] for s in solvers]
        self.assertLess(abs(targets[2] - targets[1]), .001)
        self.assertLessEqual(abs(targets[2] - targets[1]), abs(targets[1] - targets[0]) + 1e-12)
        self.assertEqual(len({s.identity for s in solvers}), 3)
        for invalid in (0, -1, 1.5, True, math.inf, 1025):
            with self.assertRaises(ValueError):
                Solver(value, filtered_samples_per_px=invalid)

    def test_previous_models_keep_their_endpoints(self):
        solver = Solver(calibrated_capture())
        expected = {"font_calibrated": (4.5, 7), "balanced": (1.5, 3), "source_relative": (1.25, 3)}
        for model, (target, step) in expected.items():
            pair = solver.pair(65, 86, controls(spacing_model=model))
            self.assertEqual(pair["target_separation_px"], target)
            self.assertEqual(pair["resolved_step_px"], step)
            self.assertNotIn("clearance_min_step_px", pair)


if __name__ == "__main__":
    unittest.main()
