"""Source-pair compensation and integration; no optical acceptance claims."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hu_hersch as hu
from hu_source_relative import HuSourceRelativeModel
from solver import Controls, Solver, bitmap_commands, pixel_round
from test_hu_calibration import capture as base_capture, glyph, rectangle


def capture():
    value = base_capture()
    value.update(source_sha256="synthetic-source", monospace=False, tabular_digits=False)
    for g in value["glyphs"]:
        g["source_advance_px"] = g["finalized_advance_px"] = 6
    return value


def controls(**values):
    values.setdefault("spacing_model", "hu_source_relative")
    return Controls(**values)


class HuSourceRelativeTests(unittest.TestCase):
    def test_source_equals_delivered_preserves_designed_placement_at_each_strength(self):
        value = capture()
        value["source_pairs"] = [dict(left=ord("a"), right=ord("b"), adjustment_px=-2)]
        value["metric_pairs_on"] = copy.deepcopy(value["source_pairs"])
        solver = Solver(value)
        for strength in (0, .25, .5, .75, 1):
            pair = solver.pair(ord("a"), ord("b"), controls(source_kerning=strength))
            self.assertEqual(pair["source_hu_offset_px"], pair["delivered_hu_offset_px"])
            self.assertEqual(pair["source_step_px"], 6 - 2 * strength)
            self.assertEqual(pair["source_target_px"], 4 - 2 * strength)
            self.assertEqual(pair["unconstrained_step_px"], pair["source_step_px"])
            self.assertEqual(pair["resolved_step_px"], 6 + pixel_round(-2 * strength))
            self.assertEqual(pair["resolved_step_px"], 6 + pair["metric_adjustment_px"])
            self.assertFalse(pair["clearance_limited"])
        self.assertEqual(solver.pair(ord("a"), ord("b"), controls(source_kerning=0))["resolved_step_px"], 6)
        self.assertEqual(solver.pair(ord("a"), ord("b"), controls(source_kerning=1))["resolved_step_px"], 4)

    def test_identical_cell_union_contours_preserve_cavity_profiles(self):
        value = capture()
        a = glyph(value, "a")
        a["bitmap"].update(width=3, pixels=[1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1])
        a["source_commands"] = bitmap_commands(a["bitmap"], 100)
        model = HuSourceRelativeModel(value, 8)
        result = model.pair(ord("a"), ord("b"))
        self.assertEqual(model._profile(ord("a"), (0., 4.), True),
                         model._profile(ord("a"), (0., 4.), False))
        self.assertEqual(result["source_hu_offset_px"], result["delivered_hu_offset_px"])
        self.assertEqual(result["optical_step_px"], 6)

    def test_source_target_and_delivered_offsets_covary_under_translation(self):
        value = capture()
        original = HuSourceRelativeModel(value, 8).pair(ord("a"), ord("b"))
        glyph(value, "b")["source_commands"] = rectangle(x0=3, x1=5)
        source_moved = HuSourceRelativeModel(value, 8).pair(ord("a"), ord("b"))
        self.assertEqual(source_moved["source_target_px"], original["source_target_px"] + 3)
        self.assertEqual(source_moved["optical_step_px"], original["optical_step_px"] + 3)
        glyph(value, "b")["bitmap"]["left"] = -2
        delivered_moved = HuSourceRelativeModel(value, 8).pair(ord("a"), ord("b"))
        self.assertEqual(delivered_moved["source_target_px"], source_moved["source_target_px"])
        self.assertEqual(delivered_moved["optical_step_px"], source_moved["optical_step_px"] + 2)

    def test_uniform_scaling_preserves_source_and_delivered_relationship(self):
        value = capture()
        original = HuSourceRelativeModel(value, 8).pair(ord("a"), ord("b"))
        scaled = copy.deepcopy(value)
        for g in scaled["glyphs"]:
            for command in g["source_commands"]:
                for key in ("x", "y", "x1", "y1", "x2", "y2"):
                    if key in command:
                        command[key] *= 2
            g["source_advance_px"] *= 2
            g["finalized_advance_px"] *= 2
            b = g["bitmap"]
            rows = [b["pixels"][y * b["width"]:(y + 1) * b["width"]] for y in range(b["height"])]
            enlarged = [[pixel for pixel in row for _ in range(2)] for row in rows for _ in range(2)]
            b.update(left=b["left"] * 2, top=b["top"] * 2, width=b["width"] * 2,
                     height=b["height"] * 2, pixels=[pixel for row in enlarged for pixel in row])
        result = HuSourceRelativeModel(scaled, 8).pair(ord("a"), ord("b"))
        for key in ("source_target_px", "source_hu_offset_px", "delivered_hu_offset_px", "optical_step_px", "window_height_px"):
            self.assertAlmostEqual(result[key], original[key] * 2)

    def test_source_shape_changes_only_its_pair_target_without_shared_density(self):
        value = capture()
        before = HuSourceRelativeModel(value, 8)
        ab = before.pair(ord("a"), ord("b"))
        bb = before.pair(ord("b"), ord("b"))
        glyph(value, "a")["source_commands"] = rectangle(x1=4)
        # A tiny reference advance would make a shared reference target
        # negative. Here the reference supplies the window alone.
        glyph(value, "n")["source_advance_px"] = .25
        glyph(value, "n")["finalized_advance_px"] = 1
        after = HuSourceRelativeModel(value, 8)
        changed = after.pair(ord("a"), ord("b"))
        self.assertEqual(changed["source_target_px"], ab["source_target_px"] - 2)
        self.assertEqual(changed["optical_step_px"], ab["optical_step_px"] - 2)
        self.assertEqual(after.pair(ord("b"), ord("b")), bb)

    def test_signed_source_gap_is_measured_then_clearance_applies_separately(self):
        value = capture()
        glyph(value, "a")["source_advance_px"] = 1
        result = Solver(value).pair(ord("a"), ord("b"), controls())
        self.assertEqual(result["source_target_px"], -1)
        self.assertEqual(result["unconstrained_step_px"], 1)
        self.assertEqual(result["resolved_step_px"], 3)
        self.assertEqual(result["reason"], "clearance_limited")
        self.assertEqual(result["target_error_px"], 2)
        self.assertEqual(result["target_error_area_px2"], 8)

    def test_no_arbitrary_correction_cap(self):
        value = capture()
        glyph(value, "b")["bitmap"]["left"] = 5
        result = Solver(value).pair(ord("a"), ord("b"), controls())
        self.assertEqual(result["source_target_px"], 4)
        self.assertEqual(result["optical_adjustment_px"], -5)
        self.assertEqual(result["resolved_step_px"], 1)
        self.assertFalse(result["clearance_limited"])

    def test_source_and_delivered_use_identical_windows_grids_and_settings(self):
        model = HuSourceRelativeModel(capture(), 8)
        result = model.pair(ord("A"), ord("b"))
        window = tuple(result["measurement_window_px"])
        self.assertEqual(window, (0., 5.))
        for cp in (ord("A"), ord("b")):
            source = model._profile(cp, window, True)
            delivered = model._profile(cp, window, False)
            self.assertEqual(source.window, delivered.window)
            self.assertEqual(source.ys, delivered.ys)
            self.assertEqual(source.settings, delivered.settings)
        self.assertEqual(result["target_area_px2"], result["source_target_px"] * 5)

    def test_geometry_cache_is_independent_of_control_order_and_pair_cache_is_scalar(self):
        value = capture()
        value["source_pairs"] = [dict(left=ord("a"), right=ord("b"), adjustment_px=-1.25)]
        model = HuSourceRelativeModel(value, 8)
        one = model.pair(ord("a"), ord("b"), 1)
        cached = dict(model._profiles)
        for strength in (0, .5, .25, .75, 1):
            model.pair(ord("a"), ord("b"), strength)
        self.assertEqual(model._profiles, cached)
        self.assertEqual(len(model._profiles), 4)
        self.assertEqual(len(model._measurements), 1)
        self.assertEqual(one, model.pair(ord("a"), ord("b"), 1))
        self.assertEqual(one, HuSourceRelativeModel(value, 8).pair(ord("a"), ord("b"), 1))
        json.dumps(list(model._measurements.values()), allow_nan=False)
        self.assertFalse(any(isinstance(v, hu.Profile) for record in model._measurements.values() for v in record.values()))

    def test_optical_zero_is_lazy_before_and_after_warm_geometry(self):
        solver = Solver(capture())
        with patch("solver.importlib.import_module", side_effect=AssertionError("optical-zero imported adapter")):
            before = solver.generate(controls(optical=0), text="ab")
        self.assertEqual(before["calibration"]["status"], "not_evaluated")
        solver.pair(ord("a"), ord("b"), controls())
        with patch("hu_source_relative.hu.source_depth_profile", side_effect=AssertionError("optical-zero measured geometry")):
            after = solver.generate(controls(optical=0), text="ab")
        self.assertEqual(before, after)

    def test_placement_safeguards_and_unsupported_policy_remain_lazy(self):
        for field, pair, expected in (("monospace", "ab", "fixed_pitch"),
                                      ("tabular_digits", "00", "source_tabular_digits")):
            value = capture()
            value[field] = True
            with patch("solver.importlib.import_module", side_effect=AssertionError("guard imported adapter")):
                self.assertEqual(Solver(value).pair(*map(ord, pair), controls())["reason"], expected)
        value = capture()
        glyph(value, "a")["bitmap"]["pixels"] = [0] * 8
        self.assertEqual(Solver(value).pair(ord("a"), ord("b"), controls())["reason"], "empty_geometry")
        self.assertEqual(Solver(capture(), produced_geometry="fitted_outline").pair(ord("a"), ord("b"), controls())["reason"],
                         "unsupported_geometry_policy")
        model = HuSourceRelativeModel(capture(), 8)
        self.assertEqual(model.pair(ord("a"), ord("0"))["reason"], "unsupported_calibration_class")

    def test_empty_and_no_shared_rows_at_either_endpoint_abstain(self):
        for source in (True, False):
            for empty in (True, False):
                value = capture()
                a = glyph(value, "a")
                if source:
                    a["source_commands"] = [] if empty else rectangle(y0=8, y1=12)
                else:
                    a["bitmap"].update(pixels=[0] * 8) if empty else a["bitmap"].update(top=-12)
                reason = HuSourceRelativeModel(value, 8).pair(ord("a"), ord("b"))["reason"]
                self.assertEqual(reason, "empty_geometry" if empty else "no_shared_ink_rows")

    def test_missing_window_abstains_only_affected_class(self):
        value = capture()
        value["glyphs"] = [g for g in value["glyphs"] if g["codepoint"] != ord("n")]
        model = HuSourceRelativeModel(value, 8)
        self.assertEqual(model.pair(ord("a"), ord("b"))["reason"], "calibration_unavailable")
        self.assertIsNone(model.pair(ord("A"), ord("B"))["reason"])

    def test_deliberate_tracking_is_added_once_after_source_compensation(self):
        solver = Solver(capture())
        plain = solver.generate(controls(), text="aba")
        tracked = solver.generate(controls(letter_spacing=1.5), text="aba")
        a = solver.layout("aba", plain)["lines"][0]
        b = solver.layout("aba", tracked)["lines"][0]
        self.assertEqual(b["width_px"] - a["width_px"], 4)
        self.assertEqual([p["x_px"] for p in b["placements"]], [0, 8, 16])

    def test_metadata_and_inputs_are_stable_and_provenance_is_explicit(self):
        value = capture()
        original = copy.deepcopy(value)
        model = HuSourceRelativeModel(value, 8)
        self.assertEqual(model.metadata(False)["status"], "not_evaluated")
        self.assertEqual(model._profiles, {})
        before = model.metadata()
        for p in ("ab", "ba", "Ab", "AB", "00"):
            model.pair(*map(ord, p))
        self.assertEqual(before, model.metadata())
        self.assertEqual(value, original)
        self.assertEqual(before["target_provenance"], "source_pair_hu_hersch")
        self.assertEqual(before["fit"]["method"], "published_parameters")
        self.assertEqual(before["references"]["lowercase"]["generic"]["role"], "window_only")
        self.assertIn("k * source pair adjustment", before["target_policy"])
        for strength in (-.1, 1.1, True, float("nan")):
            with self.assertRaises(ValueError):
                model.pair(ord("a"), ord("b"), strength)

    def test_cli_and_matrix_planning_accept_new_comparison_without_changing_default(self):
        self.assertEqual(Controls().spacing_model, "hu_hersch")
        directory = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "capture.json"
            output_path = root / "result.json"
            input_path.write_text(json.dumps(capture()))
            completed = subprocess.run([sys.executable, str(directory / "run.py"), str(input_path), str(output_path),
                "--spacing-model", "hu_source_relative", "--text", "ab"], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(output_path.read_text())["controls"]["spacing_model"], "hu_source_relative")
            spec = importlib.util.spec_from_file_location("hu_relative_matrix_test", directory / "matrix.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            output = root / "matrix"
            with patch.object(module, "requests", return_value=[("synthetic", {})]), patch.object(sys, "argv", ["matrix.py", str(output), "--spacing-model", "hu_source_relative"]):
                self.assertEqual(module.main(), 0)
            self.assertEqual(json.loads((output / "matrix.json").read_text())["controls"]["spacing_model"], "hu_source_relative")


if __name__ == "__main__":
    unittest.main()
