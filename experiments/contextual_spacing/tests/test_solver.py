import copy
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from solver import COUNTERSPACE_MODELS, HU_DENSITY_MODELS, Controls, Solver, bitmap_commands, pixel_round, hu_density_geometry, hu_clearance_policy
from test_hu_calibration import capture as reference_capture, glyph as reference_glyph
from estimator import UnsupportedGeometry
from test_hu_density import complete_capture as density_capture, glyph as density_glyph


def rectangle(x0, y0, x1, y1):
    return [dict(op="move_to", x=x0, y=y0), dict(op="line_to", x=x1, y=y0),
            dict(op="line_to", x=x1, y=y1), dict(op="line_to", x=x0, y=y1), dict(op="close")]


def capture():
    glyphs = [dict(codepoint=cp, glyph_id=cp, source_commands=rectangle(0, 0, 200, 500),
                   produced_commands=rectangle(0, 0, 2, 5), source_advance_px=4,
                   finalized_advance_px=4, bitmap=dict(left=0, top=-5, width=2, height=5, pixels=[1]*10))
              for cp in (32, 65, 86, 48, 49)]
    glyphs[0].update(source_commands=[], produced_commands=[],
                     bitmap=dict(left=0, top=0, width=0, height=0, pixels=[]))
    return dict(schema_version="contextual-spacing-capture-v1", source_sha256="synthetic",
                size_px=10, units_per_em=1000, monospace=False, tabular_digits=False,
                glyphs=glyphs, source_pairs=[dict(left=65, right=86, adjustment_px=-0.75)],
                metric_pairs_on=[dict(left=65, right=86, adjustment_px=-1)], metric_pairs_off=[])


class CounterSpaceStub:
    """Nonlinear score catches accidental reuse of additive wall diagnostics."""

    def __init__(self, captured, calibration_geometry="delivered"):
        self.capture = copy.deepcopy(captured)
        self.calibration_geometry = calibration_geometry
        self.step = 5
        self.reason = None
        self.metadata_calls = 0
        self.measurements = []
        self.requests = []

    def metadata(self):
        self.metadata_calls += 1
        return dict(status="available", reference="pinned-test-reference", parameters=[1, 2, 3],
                    calibration_geometry=self.calibration_geometry)

    def pair(self, left, right, search_policy="closest_feasible", clearance_min_step=None):
        self.requests.append((left, right, search_policy, clearance_min_step))
        if self.reason:
            return dict(reason=self.reason, detail="unsupported by the reference model")
        step = max(self.step, clearance_min_step) if clearance_min_step is not None else self.step
        return dict(optical_step_px=step, unconstrained_step_px=self.step,
                    target_score=25, realized_score=step ** 2,
                    score_error=step ** 2 - 25, reference_pair="HH",
                    search_outcome="target_bracketed", feasible_candidate_count=8,
                    first_crossing_step_px=6, first_crossing_score=36,
                    closest_feasible_step_px=step, closest_feasible_score=step ** 2,
                    candidate_domain_min_step_px=0, candidate_domain_stop_step_px=10)

    def measure_pair(self, left, right, step):
        self.measurements.append((left, right, step))
        return step ** 2


class HuHerschStub:
    """A cached geometric measurement, independent of runtime blend controls."""

    def __init__(self, captured, samples_per_px=64, reference_geometry="delivered"):
        self.capture = copy.deepcopy(captured)
        self.samples_per_px = samples_per_px
        self.reference_geometry = reference_geometry
        self.step = 5.25
        self.reason = None
        self.metadata_calls = 0
        self.requests = []

    def metadata(self):
        self.metadata_calls += 1
        return dict(status="available", measurement_method="hu-hersch-bounded-walls-v1",
                    samples_per_px=self.samples_per_px, calibration_geometry=self.reference_geometry)

    def pair(self, left, right):
        self.requests.append((left, right))
        result = dict(reference_pair="HH", calibration_basis="uppercase",
                      target_provenance="delivered_reference_hu_hersch",
                      hu_hersch=dict(face_classes=["stem", "curve"],
                                     depth=dict(aperture_ratio=0.5, height_ratio=0.25)))
        if self.reason:
            return dict(result, reason=self.reason, detail="declared reference unavailable")
        return dict(result, optical_step_px=self.step, target_px=3.25,
                    target_area_px2=16.25, offset_px=3.25 - self.step,
                    window_height_px=5, measurement_window_px=[0, 5])


class SolverTests(unittest.TestCase):
    def test_metric_endpoints_and_strengths_preserve_bearing_correction(self):
        value = capture()
        value["metric_pairs_off"] = [dict(left=65, right=86, adjustment_px=1)]
        value["metric_pairs_on"] = []
        solver = Solver(value)
        self.assertEqual(solver.pair(65, 86, Controls(0, 0))["automatic_adjustment_px"], 1)
        self.assertEqual(solver.pair(65, 86, Controls(1, 0))["automatic_adjustment_px"], 0)
        self.assertEqual(solver.pair(65, 86, Controls(0.5, 0))["automatic_adjustment_px"], 1)

    def test_unchanged_source_identity_and_signed_source_overlap(self):
        solver = Solver(capture(), produced_geometry="fitted_outline")
        controls = Controls(spacing_model="source_relative")
        self.assertEqual(solver.pair(65, 86, controls)["automatic_adjustment_px"], -1)
        value = capture()
        value["source_pairs"][0]["adjustment_px"] = -5.5
        value["metric_pairs_on"][0]["adjustment_px"] = -6
        pair = Solver(value).pair(65, 86, controls)
        self.assertEqual(pair["source_target_px"], -3.5)
        self.assertEqual(pair["automatic_adjustment_px"], -6)

    def test_bitmap_geometry_retains_actual_output_boundaries(self):
        solver = Solver(capture())
        controls = Controls(spacing_model="source_relative")
        same = solver.pair(65, 86, controls)
        self.assertEqual(same["automatic_adjustment_px"], -1)
        value = capture()
        value["glyphs"][1]["bitmap"]["left"] = 1
        moved = Solver(value).pair(65, 86, controls)
        self.assertEqual(moved["automatic_adjustment_px"], 0)
        self.assertEqual(value["glyphs"][1]["bitmap"]["left"], 1)
        self.assertEqual(bitmap_commands(value["glyphs"][1]["bitmap"], 100)[0]["y"], 400)

    def test_required_advance_and_empty_abstentions(self):
        for field, expected in (("monospace", "fixed_pitch"), ("tabular_digits", "source_tabular_digits")):
            value = capture()
            value[field] = True
            self.assertEqual(Solver(value).pair(48, 49)["reason"], expected)
        self.assertEqual(Solver(capture()).pair(32, 65)["reason"], "empty_geometry")

    def test_tabular_preservation_is_an_explicit_spacing_policy(self):
        value = capture()
        value["tabular_digits"] = True
        next(g for g in value["glyphs"] if g["codepoint"] == 48)["bitmap"]["left"] = 1
        solver = Solver(value)
        preserved = solver.pair(48, 49, Controls(preserve_tabular_spacing=True))
        optical = solver.pair(48, 49, Controls(preserve_tabular_spacing=False, spacing_model="balanced"))
        self.assertEqual(preserved["automatic_adjustment_px"], 0)
        self.assertEqual(preserved["diagnostic"], "source_tabular_digits")
        self.assertEqual(optical["automatic_adjustment_px"], 1)
        self.assertEqual(optical["diagnostic"], "corrected")
        self.assertEqual(value, solver.capture, "policy must not rewrite captured geometry or advances")
        for strength in (0, 1):
            result = solver.generate(Controls(strength, 0, preserve_tabular_spacing=False))
            expected = solver.generate(Controls(strength, 0, preserve_tabular_spacing=True))
            self.assertEqual(result["pairs"], expected["pairs"])
        value["monospace"] = True
        self.assertEqual(Solver(value).pair(48, 49, Controls(preserve_tabular_spacing=False))["diagnostic"], "fixed_pitch")

    def test_pair_diagnostics_distinguish_rounding_from_identity(self):
        value = capture()
        digit = next(g for g in value["glyphs"] if g["codepoint"] == 48)
        digit["source_advance_px"] = 4.25
        solver = Solver(value)
        controls = Controls(spacing_model="source_relative")
        pair = solver.pair(48, 49, controls)
        self.assertEqual(pair["blended_adjustment_px"], 0.25)
        self.assertEqual(pair["diagnostic"], "rounded_unchanged")
        self.assertEqual(solver.pair(49, 48, controls)["diagnostic"], "unchanged")
        self.assertEqual(solver.pair(48, 49, Controls(optical=0))["diagnostic"], "optical_disabled")
        self.assertEqual(solver.pair(32, 49)["diagnostic"], "empty_geometry")

    def test_offsets_apply_once_at_span_gaps_and_space_advances(self):
        solver = Solver(capture())
        result = solver.generate(Controls(0, 0, 1.5, 2.5))
        lines = solver.layout("AA  A\nAV", result)["lines"]
        self.assertEqual([p["x_px"] for p in lines[0]["placements"]], [0, 6, 10, 17, 24])
        self.assertEqual(lines[0]["width_px"], 28)
        self.assertEqual([p["x_px"] for p in lines[1]["placements"]], [0, 6])
        self.assertEqual(lines[1]["width_px"], 10)

    def test_wrap_resets_context_and_terminal_has_no_letter_addition(self):
        solver = Solver(capture())
        result = solver.generate(Controls(0, 0, 2, 0))
        lines = solver.layout("AAA", result, width=10)["lines"]
        self.assertEqual([line["width_px"] for line in lines], [10, 4])
        self.assertEqual(lines[1]["placements"][0]["x_px"], 0)

    def test_preview_full_repeat_prefix_and_request_order_identity(self):
        solver = Solver(capture())
        for model in ("filtered_walls", "font_calibrated", "balanced", "source_relative"):
            controls = Controls(spacing_model=model)
            full = solver.generate(controls)
            self.assertEqual(full["declared_pairs"], 25)
            self.assertIn((65, 65), {(p["left"], p["right"]) for p in full["pairs"]})
            before = copy.deepcopy(full)
            for text in ("AV", "VAV", "AAA", "AV\nVA"):
                preview = solver.generate(controls, text=text)
                pairs = {(p["left"], p["right"]): p for p in full["pairs"]}
                for pair in preview["pairs"]:
                    self.assertEqual(pair, pairs[pair["left"], pair["right"]])
            self.assertEqual(solver.generate(controls), before)
            self.assertEqual(solver.generate(controls), Solver(capture()).generate(controls))

    def test_incomplete_results_do_not_become_layout(self):
        solver = Solver(capture())
        limited = solver.generate(work_limit=2)
        self.assertEqual((limited["status"], limited["completed_pairs"], limited["declared_pairs"]),
                         ("work_limit_exceeded", 2, 25))
        with self.assertRaises(ValueError):
            solver.layout("AV", limited)
        self.assertEqual(solver.generate(cancelled=lambda: True)["status"], "cancelled")
        self.assertEqual(solver.generate(work_limit=25)["status"], "complete")

    def test_disabled_optical_bypasses_optional_geometry_limits(self):
        value = capture()
        value["glyphs"][1]["source_commands"] = [dict(op="move_to", x=0, y=0),
                                                  dict(op="line_to", x=100000, y=100)]
        solver = Solver(value)
        self.assertEqual(solver.generate(Controls(0, 0), text="AA")["status"], "complete")
        self.assertEqual(solver.generate(text="AA")["status"], "complete")
        self.assertEqual(solver.generate(Controls(spacing_model="source_relative"), text="AA")["status"],
                         "unsupported_input")
        value["glyphs"][1]["source_commands"][1]["x"] = math.nan
        with self.assertRaises(ValueError):
            Solver(value)

    def test_fixed_grid_deliberate_spacing_requires_separate_integration(self):
        value = capture()
        value["monospace"] = True
        with self.assertRaises(ValueError):
            Solver(value).generate(Controls(letter_spacing=1))

    def test_rejects_invalid_inputs(self):
        for control in (dict(optical=-0.1), dict(source_kerning=1.1), dict(word_spacing=math.inf),
                        dict(preserve_tabular_spacing=1), dict(preserve_tabular_spacing="false"),
                        dict(spacing_model="unknown"), dict(spacing_model=None),
                        *(dict(target_separation_em=value) for value in (0, -0.1, math.inf, math.nan, True))):
            with self.assertRaises(ValueError):
                Controls(**control)
        for n, expected in ((0.5, 1), (-0.5, -1), (1.5, 2), (-1.5, -2)):
            self.assertEqual(pixel_round(n), expected)
        solver = Solver(capture())
        self.assertEqual(solver.generate(text="\t")["status"], "unsupported_input")
        self.assertEqual(solver.generate(text="A\t")["completed_pairs"], 0)
        with self.assertRaises(ValueError):
            solver.generate(work_limit=-1)
        with self.assertRaises(ValueError):
            solver.layout("AV", solver.generate(text="AA"))

    def test_balanced_common_target_with_different_shapes_and_advances(self):
        value = capture()
        # A diagonal facing side contributes a nonzero envelope term. All pairs
        # nevertheless solve toward the single FontForge-style desired spacing.
        wedge = [dict(op="move_to", x=0, y=0), dict(op="line_to", x=3, y=0),
                 dict(op="line_to", x=1, y=5), dict(op="line_to", x=0, y=5), dict(op="close")]
        value["glyphs"][1]["produced_commands"] = wedge
        value["glyphs"][2]["finalized_advance_px"] = 7
        original = copy.deepcopy(value)
        solver = Solver(value, produced_geometry="fitted_outline")
        for left, right in ((65, 86), (86, 65), (86, 86), (48, 49)):
            pair = solver.pair(left, right, Controls(spacing_model="balanced"))
            self.assertEqual(pair["target_separation_px"], 1.5)
            self.assertIsNone(pair["source_target_px"])
            self.assertLessEqual(abs(pair["target_error_px"]), 0.5)
            self.assertAlmostEqual(pair["realized_separation_px"] - pair["target_separation_px"],
                                   pair["target_error_px"])
        self.assertEqual(value, original)
        self.assertEqual(solver.capture, original)
        self.assertNotEqual(solver.pair(65, 86, Controls(spacing_model="balanced"))["optical_adjustment_px"],
                            solver.pair(86, 65, Controls(spacing_model="balanced"))["optical_adjustment_px"])

    def test_full_balanced_endpoint_ignores_source_kerning(self):
        solver = Solver(capture())
        pairs = [solver.pair(65, 86, Controls(source_kerning=k, spacing_model="balanced")) for k in (0, 0.25, 0.5, 0.75, 1)]
        self.assertEqual({p["automatic_adjustment_px"] for p in pairs}, {-1})
        self.assertEqual({p["target_separation_px"] for p in pairs}, {1.5})
        self.assertNotEqual(pairs[0]["metric_adjustment_px"], pairs[-1]["metric_adjustment_px"])
        partial = solver.pair(65, 86, Controls(0, 0.5, spacing_model="balanced"))
        self.assertEqual(partial["blended_adjustment_px"], -0.25)
        # The residual always describes the final rounded placement relative to
        # the full target, including when optical strength is intermediate.
        self.assertEqual(partial["realized_separation_px"], 2)
        self.assertEqual(partial["target_error_px"], 0.5)

    def test_balanced_placement_covaries_with_delivered_translation(self):
        value = capture()
        controls = Controls(target_separation_em=0.16, spacing_model="balanced")
        original = Solver(value).pair(65, 86, controls)
        value["glyphs"][1]["bitmap"]["left"] += 3
        moved_left = Solver(value).pair(65, 86, controls)
        self.assertAlmostEqual(moved_left["optical_adjustment_px"] - original["optical_adjustment_px"], 3)
        self.assertEqual(moved_left["realized_separation_px"], original["realized_separation_px"])
        value["glyphs"][2]["bitmap"]["left"] -= 2
        moved_both = Solver(value).pair(65, 86, controls)
        self.assertAlmostEqual(moved_both["optical_adjustment_px"] - moved_left["optical_adjustment_px"], 2)
        self.assertEqual(moved_both["realized_separation_px"], original["realized_separation_px"])

    def test_balanced_does_not_require_source_shared_bands(self):
        value = capture()
        value["glyphs"][1]["source_commands"] = rectangle(0, 700, 200, 900)
        solver = Solver(value)
        self.assertIsNone(solver.pair(65, 86, Controls(spacing_model="balanced"))["reason"])
        self.assertEqual(solver.pair(65, 86, Controls(spacing_model="source_relative"))["reason"],
                         "no_shared_bands")
        value["glyphs"][1]["bitmap"]["top"] = -10
        self.assertEqual(Solver(value).pair(65, 86, Controls(spacing_model="balanced"))["reason"], "no_shared_bands")

    def test_control_provenance_distinguishes_models_and_targets(self):
        solver = Solver(capture())
        balanced = solver.generate(Controls(target_separation_em=0.2, spacing_model="balanced"), text="AV")
        source = solver.generate(Controls(spacing_model="source_relative"), text="AV")
        self.assertEqual(balanced["controls"]["spacing_model"], "balanced")
        self.assertEqual(balanced["controls"]["target_separation_em"], 0.2)
        self.assertEqual(source["controls"]["spacing_model"], "source_relative")
        self.assertEqual(balanced["pairs"][0]["target_separation_px"], 2)
        self.assertEqual(source["pairs"][0]["target_separation_px"], source["pairs"][0]["source_target_px"])

    def test_counterspace_optical_zero_and_abstentions_never_import_optional_model(self):
        controls = Controls(spacing_model="counterspace", optical=0)
        with patch("solver.importlib.import_module", side_effect=AssertionError("optional model imported")):
            solver = Solver(capture())
            result = solver.generate(controls)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["counterspace"]["status"], "not_evaluated")
            for left, right in ((65, 86), (32, 65), (48, 49)):
                expected = solver.pair(left, right, Controls(optical=0))
                actual = solver.pair(left, right, controls)
                self.assertEqual(actual["automatic_adjustment_px"], expected["automatic_adjustment_px"])
            self.assertEqual(solver.calibration_metadata(False, "counterspace")["status"], "not_evaluated")
            for field, pair, reason in (("monospace", (65, 86), "fixed_pitch"),
                                        ("tabular_digits", (48, 49), "source_tabular_digits")):
                value = capture()
                value[field] = True
                self.assertEqual(Solver(value).pair(*pair, Controls(spacing_model="counterspace"))["reason"], reason)
            self.assertEqual(solver.pair(32, 65, Controls(spacing_model="counterspace"))["reason"], "empty_geometry")
            self.assertEqual(Solver(capture(), produced_geometry="fitted_outline").pair(
                65, 86, Controls(spacing_model="counterspace"))["reason"], "unsupported_geometry_policy")

    def test_counterspace_full_endpoint_ignores_source_kerning_and_retains_score_units(self):
        model = CounterSpaceStub(capture())
        with patch("solver.importlib.import_module", return_value=SimpleNamespace(CounterSpaceModel=lambda c, **kwargs: model)) as loaded:
            solver = Solver(capture())
            pairs = [solver.pair(65, 86, Controls(source_kerning=k, spacing_model="counterspace"))
                     for k in (0, 0.25, 0.5, 0.75, 1)]
            self.assertEqual(loaded.call_count, 1)
            self.assertEqual({p["resolved_step_px"] for p in pairs}, {5})
            self.assertEqual({p["target_score"] for p in pairs}, {25})
            self.assertEqual({p["score_error"] for p in pairs}, {0})
            self.assertNotEqual(pairs[0]["metric_adjustment_px"], pairs[-1]["metric_adjustment_px"])
            self.assertEqual(model.capture, solver.capture)
            for pair in pairs:
                self.assertIsNone(pair["target_separation_px"])
                self.assertIsNone(pair["realized_separation_px"])
                self.assertIsNone(pair["target_error_px"])
                self.assertEqual(pair["reference_pair"], "HH")
            partial = solver.pair(65, 86, Controls(optical=0.5, spacing_model="counterspace"))
            self.assertEqual(partial["resolved_step_px"], 4)
            self.assertEqual(partial["realized_score"], 16)
            self.assertEqual(partial["score_error"], -9)
            self.assertEqual(model.measurements[-1], (65, 86, 4))

    def test_counterspace_clearance_scores_emitted_step_and_reports_residual(self):
        model = CounterSpaceStub(capture())
        model.step = 1
        with patch("solver.importlib.import_module", return_value=SimpleNamespace(CounterSpaceModel=lambda c, **kwargs: model)):
            pair = Solver(capture()).pair(65, 86, Controls(spacing_model="counterspace_source_first"))
        self.assertEqual(pair["clearance_min_step_px"], 3)
        self.assertEqual(pair["rounded_unconstrained_step_px"], 1)
        self.assertEqual(pair["unconstrained_step_px"], 1)
        self.assertEqual(pair["resolved_step_px"], 3)
        self.assertEqual(pair["clearance_adjustment_px"], 2)
        self.assertEqual(pair["reason"], "clearance_limited")
        self.assertEqual(pair["realized_score"], 9)
        self.assertEqual(pair["score_error"], -16)

    def test_counterspace_model_failure_is_explicit_and_unsupported_pair_falls_back(self):
        controls = Controls(spacing_model="counterspace")
        with patch("solver.importlib.import_module", side_effect=RuntimeError("install optional requirements")):
            with self.assertRaisesRegex(RuntimeError, "install optional requirements"):
                Solver(capture()).generate(controls, text="AV")
        model = CounterSpaceStub(capture())
        model.reason = "unsupported_calibration_class"
        with patch("solver.importlib.import_module", return_value=SimpleNamespace(CounterSpaceModel=lambda c, **kwargs: model)):
            result = Solver(capture()).generate(controls, text="AV")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["pairs"][0]["reason"], "unsupported_calibration_class")
        self.assertEqual(result["pairs"][0]["automatic_adjustment_px"], -1)
        self.assertIsNone(result["pairs"][0]["target_score"])
        self.assertEqual(result["pairs"][0]["calibration_detail"], "unsupported by the reference model")

    def test_counterspace_metadata_identity_and_cache_history_are_reproducible(self):
        model = CounterSpaceStub(capture())
        with patch("solver.importlib.import_module", return_value=SimpleNamespace(CounterSpaceModel=lambda c, **kwargs: model)):
            solver = Solver(capture())
            controls = Controls(spacing_model="counterspace")
            disabled = Controls(optical=0, spacing_model="counterspace")
            before = solver.generate(disabled, text="AV")
            empty_before = solver.generate(controls, text=" A")
            first = solver.generate(controls, text="AV")
            self.assertEqual(first, solver.generate(controls, text="AV"))
            calls = model.metadata_calls
            self.assertEqual(before, solver.generate(disabled, text="AV"))
            self.assertEqual(empty_before, solver.generate(controls, text=" A"))
            self.assertEqual(calls, model.metadata_calls)
            self.assertNotEqual(first["counterspace_analysis_identity"], before["counterspace_analysis_identity"])
            self.assertEqual(first["analysis_identity"], before["analysis_identity"])
            self.assertEqual(solver.layout("AV", first)["lines"][0]["width_px"], 9)

    def test_counterspace_variants_share_geometry_fit_but_keep_policy_identity(self):
        models = []

        def factory(captured, calibration_geometry):
            model = CounterSpaceStub(captured, calibration_geometry)
            models.append(model)
            return model

        with patch("solver.importlib.import_module", return_value=SimpleNamespace(CounterSpaceModel=factory)):
            solver = Solver(capture())
            results = {name: solver.generate(Controls(spacing_model=name), text="AV")
                       for name in COUNTERSPACE_MODELS}
            self.assertEqual([m.calibration_geometry for m in models], ["delivered", "source"])
            self.assertEqual(models[0].requests, [(65, 86, "closest_feasible", 3),
                                                  (65, 86, "first_crossing", None)])
            self.assertEqual(models[1].requests, [(65, 86, "first_crossing", None)])
            self.assertEqual(len({r["counterspace_analysis_identity"] for r in results.values()}), 3)
            for name, (geometry, policy) in COUNTERSPACE_MODELS.items():
                record = results[name]["pairs"][0]
                metadata = results[name]["counterspace"]
                self.assertEqual(record["calibration_geometry"], geometry)
                self.assertEqual(record["search_policy"], policy)
                self.assertEqual(metadata["calibration_geometry"], geometry)
                self.assertEqual(metadata["search_policy"], policy)
                self.assertEqual(record["target_provenance"], geometry + "_reference_counterspace")
                self.assertEqual(record["first_crossing_step_px"], 6)
                self.assertEqual(record["closest_feasible_score"], 25)
                self.assertEqual(record["candidate_domain_stop_step_px"], 10)
                self.assertEqual(record["search_outcome"], "target_bracketed")
                self.assertEqual(record["feasible_candidate_count"], 8)
                # Both endpoints use fixed full reference calibration; source k
                # participates only in the metric part of a partial blend.
                full_steps = {solver.pair(65, 86, Controls(source_kerning=k, spacing_model=name))["resolved_step_px"]
                              for k in (0, 0.5, 1)}
                self.assertEqual(full_steps, {5})

    def test_counterspace_closest_feasible_passes_guard_into_search_and_keeps_blend_guard(self):
        model = CounterSpaceStub(capture())
        model.step = 1
        with patch("solver.importlib.import_module", return_value=SimpleNamespace(CounterSpaceModel=lambda c, **kw: model)):
            solver = Solver(capture())
            result = solver.pair(65, 86, Controls(spacing_model="counterspace"))
            self.assertEqual(model.requests[-1], (65, 86, "closest_feasible", 3))
            self.assertEqual(result["unconstrained_step_px"], 1)
            self.assertEqual(result["resolved_step_px"], 3)
            self.assertEqual(result["rounded_unconstrained_step_px"], 3)
            self.assertEqual(result["clearance_adjustment_px"], 0)
            self.assertEqual(result["realized_score"], 9)
            self.assertEqual(result["closest_feasible_step_px"], 3)
            # A severely negative metric endpoint can still make a partial
            # blend infeasible, so candidate feasibility cannot replace guard.
            value = capture()
            value["source_pairs"][0]["adjustment_px"] = -4
            value["metric_pairs_on"][0]["adjustment_px"] = -4
            partial = Solver(value).pair(65, 86, Controls(optical=0.25, spacing_model="counterspace"))
            self.assertEqual(partial["resolved_step_px"], 3)
            self.assertEqual(partial["rounded_unconstrained_step_px"], 1)
            self.assertEqual(partial["clearance_adjustment_px"], 2)

    def test_all_counterspace_variants_optical_zero_are_lazy_and_no_feasible_is_explicit(self):
        for name in COUNTERSPACE_MODELS:
            with self.subTest(name=name), patch("solver.importlib.import_module", side_effect=AssertionError("imported")):
                result = Solver(capture()).generate(Controls(spacing_model=name, optical=0), text="AV")
                self.assertEqual(result["counterspace"]["status"], "not_evaluated")
                self.assertIsNone(result["pairs"][0]["first_crossing_step_px"])
                self.assertEqual(result["pairs"][0]["automatic_adjustment_px"], -1)
        model = CounterSpaceStub(capture())
        model.reason = "counterspace_no_feasible_candidate"
        with patch("solver.importlib.import_module", return_value=SimpleNamespace(CounterSpaceModel=lambda c, **kw: model)):
            record = Solver(capture()).pair(65, 86, Controls(spacing_model="counterspace"))
        self.assertEqual(record["reason"], "counterspace_no_feasible_candidate")
        self.assertEqual(record["clearance_min_step_px"], 3)
        self.assertIsNone(record["optical_adjustment_px"])
        self.assertEqual(record["automatic_adjustment_px"], -1)
        no_feasible = dict(reason="counterspace_no_feasible_candidate", target_score=25, reference_pair="HH",
                           search_outcome="no_feasible_candidate", feasible_candidate_count=0)
        with patch("solver.importlib.import_module", return_value=SimpleNamespace(CounterSpaceModel=lambda c, **kw: model)), \
                patch.object(model, "pair", return_value=no_feasible):
            record = Solver(capture()).pair(65, 86, Controls(spacing_model="counterspace"))
        self.assertEqual(record["target_score"], 25)
        self.assertEqual(record["reference_pair"], "HH")
        self.assertEqual(record["search_outcome"], "no_feasible_candidate")
        self.assertEqual(record["feasible_candidate_count"], 0)
        self.assertIsNone(record["realized_score"])

    def test_hu_is_default_and_guarded_paths_do_not_load_calibration(self):
        self.assertEqual(Controls().spacing_model, "hu_hersch")
        with patch("solver.importlib.import_module", side_effect=AssertionError("calibration loaded")):
            solver = Solver(capture())
            result = solver.generate(Controls(optical=0))
            self.assertEqual(result["calibration"]["status"], "not_evaluated")
            self.assertEqual(result["hu_hersch"], result["calibration"])
            self.assertEqual(result["pairs"][0]["reason"], "optical_disabled")
            self.assertFalse(any(p["hu_hersch_evaluated"] for p in result["pairs"]))
            for field, pair, reason in (("monospace", (65, 86), "fixed_pitch"),
                                       ("tabular_digits", (48, 49), "source_tabular_digits")):
                value = capture()
                value[field] = True
                actual = Solver(value).pair(*pair)
                self.assertEqual(actual["reason"], reason)
                self.assertFalse(actual["hu_hersch_evaluated"])
            self.assertEqual(solver.pair(32, 65)["reason"], "empty_geometry")
            self.assertEqual(Solver(capture(), produced_geometry="fitted_outline").pair(65, 86)["reason"],
                             "unsupported_geometry_policy")
            self.assertEqual(solver.calibration_metadata(False, "hu_hersch")["status"], "not_evaluated")

    def test_hu_full_endpoint_uses_one_measurement_and_preserves_actual_area_residual(self):
        model = HuHerschStub(capture())
        with patch("solver.importlib.import_module", return_value=SimpleNamespace(HuHerschModel=lambda *a, **k: model)) as loaded:
            solver = Solver(capture())
            with patch.object(sys.modules["solver"].filtered_walls, "clearance_min_step", return_value=3) as clearance:
                pairs = [solver.pair(65, 86, Controls(source_kerning=k)) for k in (0, 0.25, 0.5, 0.75, 1)]
                self.assertEqual(clearance.call_count, 1)
                partial = solver.pair(65, 86, Controls(source_kerning=0, optical=0.5))
            self.assertEqual(loaded.call_count, 1)
            self.assertEqual(model.requests, [(65, 86)])
            self.assertEqual({p["resolved_step_px"] for p in pairs}, {5})
            self.assertEqual({p["unconstrained_step_px"] for p in pairs}, {5.25})
            self.assertEqual({p["target_separation_px"] for p in pairs}, {3.25})
            self.assertEqual({p["realized_separation_px"] for p in pairs}, {3})
            self.assertEqual({p["target_error_px"] for p in pairs}, {-0.25})
            self.assertEqual({p["realized_area_px2"] for p in pairs}, {15})
            self.assertEqual({p["target_error_area_px2"] for p in pairs}, {-1.25})
            self.assertNotEqual(pairs[0]["metric_adjustment_px"], pairs[-1]["metric_adjustment_px"])
            self.assertEqual(partial["resolved_step_px"], 5)
            self.assertEqual(partial["blended_adjustment_px"], 0.625)
            self.assertEqual(partial["hu_hersch"]["face_classes"], ["stem", "curve"])
            self.assertEqual(model.capture, solver.capture)
            # A consumer can edit a returned diagnostic without mutating the
            # cached reference measurement or another control's output.
            pairs[0]["hu_hersch"]["face_classes"].append("changed")
            self.assertEqual(solver.pair(65, 86)["hu_hersch"]["face_classes"], ["stem", "curve"])

    def test_hu_clearance_is_separate_from_target_and_measures_emitted_area(self):
        model = HuHerschStub(capture())
        model.step = 1
        with patch("solver.importlib.import_module", return_value=SimpleNamespace(HuHerschModel=lambda *a, **k: model)):
            pair = Solver(capture()).pair(65, 86)
        self.assertEqual(pair["unconstrained_step_px"], 1)
        self.assertEqual(pair["rounded_unconstrained_step_px"], 1)
        self.assertEqual(pair["clearance_min_step_px"], 3)
        self.assertEqual(pair["clearance_adjustment_px"], 2)
        self.assertEqual(pair["resolved_step_px"], 3)
        self.assertEqual(pair["reason"], "clearance_limited")
        self.assertEqual(pair["realized_separation_px"], 5.25)
        self.assertEqual(pair["target_error_px"], 2)
        self.assertEqual(pair["target_error_area_px2"], 10)

    def test_hu_unavailable_reference_or_unsupported_class_retains_metric_endpoint(self):
        for reason in ("missing_reference_glyph", "unsupported_calibration_class", "no_shared_ink_rows"):
            with self.subTest(reason=reason):
                model = HuHerschStub(capture())
                model.reason = reason
                with patch("solver.importlib.import_module", return_value=SimpleNamespace(HuHerschModel=lambda *a, **k: model)):
                    result = Solver(capture()).generate(text="AV")
                pair = result["pairs"][0]
                self.assertEqual(result["status"], "complete")
                self.assertEqual(pair["automatic_adjustment_px"], -1)
                self.assertIsNone(pair["optical_adjustment_px"])
                self.assertEqual(pair["reason"], reason)
                self.assertEqual(pair["calibration_detail"], "declared reference unavailable")
                self.assertEqual(pair["reference_pair"], "HH")

    def test_hu_optical_zero_identity_is_independent_of_cache_history(self):
        model = HuHerschStub(capture())
        with patch("solver.importlib.import_module", return_value=SimpleNamespace(HuHerschModel=lambda *a, **k: model)):
            solver = Solver(capture())
            disabled = Controls(optical=0)
            before = solver.generate(disabled, text="AV")
            first = solver.generate(text="AV")
            self.assertEqual(first, solver.generate(text="AV"))
            calls = model.metadata_calls
            self.assertEqual(before, solver.generate(disabled, text="AV"))
            self.assertEqual(calls, model.metadata_calls)
            self.assertNotEqual(first["hu_hersch_analysis_identity"], before["hu_hersch_analysis_identity"])
            self.assertEqual(first["analysis_identity"], before["analysis_identity"])
            self.assertEqual(solver.generate(text=" A")["calibration"]["status"], "not_evaluated")



class HuSourceCalibratedSolverTests(unittest.TestCase):
    def capture(self):
        value = reference_capture()
        value.update(source_sha256="source-designed-reference", monospace=False, tabular_digits=False,
                     source_metric_quantization="nearest_1_64_px")
        return value

    def controls(self, **values):
        return Controls(spacing_model="hu_source_calibrated", **values)

    def test_both_shared_models_have_isolated_measurement_and_adapter_caches(self):
        value = self.capture()
        reference_glyph(value, "n")["source_advance_px"] = 3
        solver = Solver(value, filtered_samples_per_px=8)
        source = solver.pair(*map(ord, "ab"), self.controls())
        delivered = solver.pair(*map(ord, "ab"), Controls())
        self.assertEqual((source["target_separation_px"], delivered["target_separation_px"]), (1, 2))
        self.assertEqual((source["resolved_step_px"], delivered["resolved_step_px"]), (3, 4))
        self.assertEqual(solver.pair(*map(ord, "ab"), self.controls()), source)
        self.assertEqual(solver.pair(*map(ord, "ab"), Controls()), delivered)
        self.assertIsNot(solver._hu_hersch, solver._hu_source_calibrated)
        self.assertEqual(len(solver._hu_hersch_pairs), 2)
        reverse = Solver(value, filtered_samples_per_px=8)
        self.assertEqual(reverse.pair(*map(ord, "ab"), Controls()), delivered)
        self.assertEqual(reverse.pair(*map(ord, "ab"), self.controls()), source)

    def test_full_optical_reference_uses_full_kerning_independent_of_slider(self):
        value = self.capture()
        reference_glyph(value, "n")["source_advance_px"] = 3.25
        value["source_pairs"] = [dict(left=ord("n"), right=ord("n"), adjustment_px=.25),
                                 dict(left=ord("a"), right=ord("b"), adjustment_px=-.75)]
        value["metric_pairs_on"] = [dict(left=ord("a"), right=ord("b"), adjustment_px=-1)]
        solver = Solver(value, filtered_samples_per_px=8)
        records = [solver.pair(*map(ord, "ab"), self.controls(source_kerning=k)) for k in (0, .25, .5, .75, 1)]
        self.assertEqual({p["target_separation_px"] for p in records}, {1.5})
        self.assertEqual({p["unconstrained_step_px"] for p in records}, {3.5})
        self.assertEqual({p["resolved_step_px"] for p in records}, {3})
        self.assertEqual({p["metric_adjustment_px"] for p in records}, {0, -1})
        self.assertEqual(solver.pair(*map(ord, "ab"), self.controls(source_kerning=0, optical=.5))["resolved_step_px"], 4)
        self.assertEqual(solver.pair(*map(ord, "ab"), self.controls(source_kerning=1, optical=.5))["resolved_step_px"], 3)

    def test_rounding_precedes_clearance_and_realized_residual_is_reported(self):
        value = self.capture()
        reference_glyph(value, "n")["source_advance_px"] = 2.5
        record = Solver(value, filtered_samples_per_px=8).pair(*map(ord, "ab"), self.controls())
        self.assertEqual(record["unconstrained_step_px"], 2.5)
        self.assertEqual(record["rounded_unconstrained_step_px"], 2)
        self.assertEqual(record["clearance_min_step_px"], 3)
        self.assertEqual(record["clearance_adjustment_px"], 1)
        self.assertEqual(record["resolved_step_px"], 3)
        self.assertEqual(record["target_separation_px"], .5)
        self.assertEqual(record["realized_separation_px"], 1)
        self.assertEqual(record["target_error_px"], .5)
        self.assertEqual(record["target_error_area_px2"], 2)
        self.assertEqual(record["diagnostic"], "clearance_limited")

    def test_optical_zero_is_dependency_free_and_stable_after_active_cache(self):
        value = self.capture()
        solver = Solver(value, filtered_samples_per_px=8)
        disabled = self.controls(optical=0)
        with patch("solver.importlib.import_module", side_effect=AssertionError("adapter loaded")):
            before = solver.generate(disabled, text="ab")
            for flag, text, reason in (("monospace", "ab", "fixed_pitch"),
                                       ("tabular_digits", "00", "source_tabular_digits")):
                preserved = self.capture()
                preserved[flag] = True
                record = Solver(preserved).pair(*map(ord, text), self.controls())
                self.assertEqual(record["reason"], reason)
        active = solver.generate(self.controls(), text="ab")
        self.assertEqual(active["status"], "complete")
        self.assertEqual(solver.generate(disabled, text="ab"), before)
        self.assertNotEqual(active["hu_source_calibrated_analysis_identity"], before["hu_source_calibrated_analysis_identity"])
        self.assertEqual(active["analysis_identity"], before["analysis_identity"])

    def test_source_reference_failures_retain_metric_and_provenance(self):
        value = self.capture()
        reference_glyph(value, "n")["source_commands"] = []
        solver = Solver(value, filtered_samples_per_px=8)
        result = solver.generate(self.controls(), text="ab")
        self.assertEqual(result["status"], "complete")
        record = result["pairs"][0]
        self.assertEqual(record["reason"], "calibration_unavailable")
        self.assertEqual(record["calibration_detail"], "empty_reference_geometry")
        self.assertEqual(record["automatic_adjustment_px"], record["metric_adjustment_px"])
        self.assertEqual(result["calibration"]["target_provenance"], "source_reference_hu_hersch")
        self.assertEqual(result["calibration"]["source_metric_quantization"], "nearest_1_64_px")
        with patch("hu_calibration.hu.source_depth_profile", side_effect=UnsupportedGeometry("unsupported reference")):
            unsupported = Solver(self.capture(), filtered_samples_per_px=8).generate(self.controls(), text="ab")
        self.assertEqual(unsupported["status"], "complete")
        self.assertEqual(unsupported["pairs"][0]["calibration_detail"], "unsupported_reference_geometry")

    def test_source_command_and_scanline_work_limits_are_declared_and_enforced(self):
        solver = Solver(self.capture(), filtered_samples_per_px=8)
        result = solver.generate(self.controls(), text="ab")
        self.assertIn("commands", result["work_limits"])
        self.assertIn("filtered_scanline_visits", result["work_limits"])
        for target in ("estimator.MAX_COMMANDS", "filtered_walls.MAX_SCANLINE_VISITS"):
            with self.subTest(limit=target), patch(target, 1):
                limited = Solver(self.capture(), filtered_samples_per_px=8).generate(self.controls(), text="ab")
                self.assertEqual(limited["status"], "work_limit_exceeded")
                self.assertEqual(limited["completed_pairs"], 0)
                delivered = Solver(self.capture(), filtered_samples_per_px=8).generate(Controls(), text="ab")
                self.assertEqual(delivered["status"], "complete")
        value = self.capture()
        reference_glyph(value, "H")["source_commands"] *= 3
        with patch("estimator.MAX_COMMANDS", 10):
            metadata_limited = Solver(value, filtered_samples_per_px=8).generate(self.controls(), text="ab")
        self.assertEqual(metadata_limited["status"], "work_limit_exceeded")
        self.assertEqual(metadata_limited["completed_pairs"], 1)
        self.assertEqual(metadata_limited["calibration"]["status"], "not_evaluated")



class HuDensitySolverTests(unittest.TestCase):
    def test_fitted_walls_use_pixel_commands_and_keep_bitmap_control_cache_separate(self):
        value = density_capture()
        density_glyph(value, "a")["produced_commands"] = rectangle(0, 0, 4, 4)
        solver = Solver(value, filtered_samples_per_px=8)
        old = Controls(spacing_model="hu_density_conserved_touch")
        new = Controls(spacing_model="hu_fitted_density_conserved_touch")
        before = solver.pair(ord("a"), ord("b"), old)
        record = solver.pair(ord("a"), ord("b"), new)
        # 25 fitted right walls are 2.5 px wide and one is 4 px wide.
        expected_target = 4 - (25 * 2.5 + 4) / 26
        self.assertAlmostEqual(record["target_separation_px"], expected_target)
        self.assertAlmostEqual(record["unconstrained_step_px"], expected_target + 4)
        self.assertEqual(record["resolved_step_px"], 5)
        self.assertEqual(before["resolved_step_px"], 4)
        self.assertEqual(solver.pair(ord("a"), ord("b"), old), before)
        self.assertEqual(record["candidate_geometry"], "fitted_outline")
        self.assertEqual(record["clearance_policy"], "no_overlap")
        self.assertEqual(record["measurement_method"], "hu-hersch-patent-sampled-fitted-pixel-walls-v1")
        result = solver.generate(new, text="ab")
        self.assertEqual(result["calibration"]["candidate_geometry"], "fitted_outline")
        self.assertEqual(result["estimator"]["candidate_geometry"], "fitted_outline")
        self.assertEqual(result["estimator"]["clearance_geometry"], "bitmap")
        self.assertEqual(solver.capture, value)

    def test_fitted_measurement_does_not_replace_delivered_bitmap_overlap_floor(self):
        value = density_capture()
        for glyph in value["glyphs"]:
            if 97 <= glyph["codepoint"] <= 122:
                glyph["source_advance_px"] = 1.25
                glyph["produced_commands"] = rectangle(0, 0, 1, 4)
        record = Solver(value, filtered_samples_per_px=8).pair(
            ord("a"), ord("b"), Controls(spacing_model="hu_fitted_density_conserved_touch"))
        self.assertEqual(record["unconstrained_step_px"], 1.25)
        self.assertEqual(record["rounded_unconstrained_step_px"], 1)
        self.assertEqual(record["clearance_min_step_px"], 2)
        self.assertEqual(record["resolved_step_px"], 2)
        self.assertEqual(record["clearance_adjustment_px"], 1)
        self.assertEqual(record["reason"], "clearance_limited")

    def test_unavailable_fitted_calibration_does_not_silently_measure_bitmap(self):
        value = density_capture()
        density_glyph(value, "z")["produced_commands"] = []
        solver = Solver(value, filtered_samples_per_px=8)
        bitmap = solver.pair(ord("a"), ord("b"), Controls(spacing_model="hu_density_conserved_touch"))
        fitted = solver.pair(ord("a"), ord("b"), Controls(spacing_model="hu_fitted_density_conserved_touch"))
        self.assertIsNotNone(bitmap["unconstrained_step_px"])
        self.assertIsNone(fitted["unconstrained_step_px"])
        self.assertEqual(fitted["reason"], "calibration_unavailable")
        self.assertEqual(fitted["automatic_adjustment_px"], fitted["metric_adjustment_px"])
        self.assertEqual(fitted["candidate_geometry"], "fitted_outline")
        metadata = solver.calibration_metadata(spacing_model="hu_fitted_density_conserved_touch")
        self.assertEqual(metadata["classes"]["lowercase"]["status"], "unavailable")

    def test_named_modes_have_fixed_full_kerning_calibration_and_independent_caches(self):
        value = density_capture()
        density_glyph(value, "a")["bitmap"].update(width=3, pixels=[1] * 12)
        value["source_pairs"] = [dict(left=ord("a"), right=ord("b"), adjustment_px=-.75)]
        value["metric_pairs_on"] = [dict(left=ord("a"), right=ord("b"), adjustment_px=-1)]
        solver = Solver(value, filtered_samples_per_px=8)
        endpoints = {}
        for name, policy in HU_DENSITY_MODELS.items():
            controls = [Controls(spacing_model=name, source_kerning=k, preserve_tabular_spacing=False)
                        for k in (0, .25, .5, .75, 1)]
            records = [solver.pair(ord("a"), ord("b"), control) for control in controls]
            self.assertEqual(len({record["target_separation_px"] for record in records}), 1)
            self.assertEqual(len({record["resolved_step_px"] for record in records}), 1)
            self.assertEqual({record["metric_adjustment_px"] for record in records}, {0, -1})
            a = solver.generate(controls[0], text="ab")
            b = solver.generate(controls[-1], text="zz")
            self.assertEqual(a["calibration"], b["calibration"])
            self.assertEqual(a["calibration"]["target_policy"], policy)
            self.assertEqual(a["calibration"]["candidate_geometry"], hu_density_geometry(name))
            self.assertEqual(a["work_limits"]["calibration_ordered_pairs"], 2804)
            self.assertIn("commands", a["work_limits"])
            self.assertIn("filtered_scanline_visits", a["work_limits"])
            endpoints[name] = records[0]["target_separation_px"]
        self.assertEqual(len(set(endpoints.values())), 3)
        self.assertEqual(endpoints["hu_density_conserved"], endpoints["hu_density_conserved_touch"])
        self.assertEqual(set(solver._hu_density), {"source_origin", "source_alphabet", ("source_origin", "fitted_outline"),
                                                 ("source_origin", "fitted_outline", "full_outline")})
        self.assertEqual(Controls().spacing_model, "hu_hersch")

    def test_zero_and_preservation_guards_do_not_load_density_and_remain_stable(self):
        for name in HU_DENSITY_MODELS:
            value = density_capture()
            solver = Solver(value, filtered_samples_per_px=8)
            disabled = Controls(spacing_model=name, optical=0)
            with patch("solver.importlib.import_module", side_effect=AssertionError("density loaded")):
                before = solver.generate(disabled, text="ab")
                self.assertEqual(before["calibration"]["target_policy"], HU_DENSITY_MODELS[name])
                self.assertEqual(before["calibration"]["source_metric_quantization"], value["source_metric_quantization"])
                for flag, pair, reason in (("monospace", "ab", "fixed_pitch"),
                                           ("tabular_digits", "01", "source_tabular_digits")):
                    guarded = density_capture()
                    guarded[flag] = True
                    record = Solver(guarded).pair(*map(ord, pair), Controls(spacing_model=name))
                    self.assertEqual(record["reason"], reason)
                    self.assertFalse(record["hu_hersch_evaluated"])
                unsupported = Solver(value, produced_geometry="fitted_outline").pair(ord("a"), ord("b"), Controls(spacing_model=name))
                self.assertEqual(unsupported["reason"], "unsupported_geometry_policy")
                self.assertEqual(solver.pair(32, ord("a"), Controls(spacing_model=name))["reason"], "empty_geometry")
            active = solver.generate(Controls(spacing_model=name), text="ab")
            self.assertEqual(active["status"], "complete")
            self.assertEqual(solver.generate(disabled, text="ab"), before)
            self.assertNotEqual(active[name + "_analysis_identity"], before[name + "_analysis_identity"])

    def test_continuous_mean_constraint_does_not_claim_post_guard_identity(self):
        value = density_capture()
        for glyph in value["glyphs"]:
            if 97 <= glyph["codepoint"] <= 122:
                glyph["source_advance_px"] = 2.25
                glyph["produced_commands"] = rectangle(0, 0, 2, 4)
        solver = Solver(value, filtered_samples_per_px=8)
        for name in HU_DENSITY_MODELS:
            record = solver.pair(ord("a"), ord("b"), Controls(spacing_model=name))
            self.assertEqual(record["unconstrained_step_px"], 2.25)
            self.assertEqual(record["rounded_unconstrained_step_px"], 2)
            touching = hu_clearance_policy(name) == "no_overlap"
            self.assertEqual(record["clearance_min_step_px"], 2 if touching else 3)
            self.assertEqual(record["clearance_adjustment_px"], 0 if touching else 1)
            self.assertEqual(record["resolved_step_px"], 2 if touching else 3)
            self.assertEqual(record["target_separation_px"], .25)
            self.assertEqual(record["realized_separation_px"], 0 if touching else 1)
            self.assertEqual(record["target_error_px"], -.25 if touching else .75)
            calibration = solver.calibration_metadata(spacing_model=name)["classes"]["lowercase"]
            self.assertEqual(calibration["continuous_mean_origin_residual_px"], 0)
            self.assertEqual(record["diagnostic"], "corrected" if touching else "clearance_limited")

    def test_touch_policy_is_a_constraint_after_blending_with_independent_cache_identity(self):
        value = density_capture()
        for glyph in value["glyphs"]:
            if 97 <= glyph["codepoint"] <= 122:
                glyph["source_advance_px"] = 2.25
        solver = Solver(value, filtered_samples_per_px=8)
        strict_name, touch_name = "hu_density_conserved", "hu_density_conserved_touch"
        strict_controls, touch_controls = Controls(spacing_model=strict_name), Controls(spacing_model=touch_name)
        before = solver.pair(ord("a"), ord("b"), strict_controls)
        touch = solver.pair(ord("a"), ord("b"), touch_controls)
        self.assertEqual(solver.pair(ord("a"), ord("b"), strict_controls), before)
        self.assertEqual(touch["unconstrained_step_px"], before["unconstrained_step_px"])
        self.assertEqual(touch["target_separation_px"], before["target_separation_px"])
        self.assertEqual(touch["clearance_policy"], "no_overlap")
        self.assertEqual(before["clearance_policy"], "strict")
        for strength in (.25, .5, .75):
            control = Controls(spacing_model=touch_name, optical=strength)
            record = solver.pair(ord("a"), ord("b"), control)
            expected = 4 + pixel_round((2.25 - 4) * strength)
            self.assertEqual(record["resolved_step_px"], max(expected, 2))
        disabled = solver.pair(ord("a"), ord("b"), Controls(spacing_model=touch_name, optical=0))
        self.assertEqual(disabled["resolved_step_px"], 4)
        a = solver.generate(strict_controls, text="ab")
        b = solver.generate(touch_controls, text="ab")
        self.assertEqual(a["calibration"]["classes"], b["calibration"]["classes"])
        self.assertNotEqual(a[strict_name + "_analysis_identity"], b[touch_name + "_analysis_identity"])
        self.assertEqual(b["estimator"]["clearance_policy"], "no_overlap")

    def test_missing_alphabet_abstains_and_required_limits_fail_the_result(self):
        value = density_capture()
        value["glyphs"] = [g for g in value["glyphs"] if g["codepoint"] != ord("z")]
        for name in HU_DENSITY_MODELS:
            result = Solver(value, filtered_samples_per_px=8).generate(Controls(spacing_model=name), text="ab")
            self.assertEqual(result["status"], "complete")
            record = result["pairs"][0]
            self.assertEqual(record["reason"], "calibration_unavailable")
            self.assertEqual(record["calibration_detail"], "missing_calibration_glyph")
            self.assertEqual(record["automatic_adjustment_px"], record["metric_adjustment_px"])
            self.assertEqual(result["calibration"]["classes"]["lowercase"]["pair_count"], 676)
        import hu_density
        hu_density._sample_profile.cache_clear()
        with patch("estimator.MAX_COMMANDS", 1):
            required = Solver(density_capture(), filtered_samples_per_px=8).generate(
                Controls(spacing_model="hu_alphabet_source_target"), text="ab")
            optional = Solver(density_capture(), filtered_samples_per_px=8).generate(
                Controls(spacing_model="hu_density_conserved"), text="ab")
        self.assertEqual(required["status"], "work_limit_exceeded")
        self.assertEqual(optional["status"], "complete")
        self.assertEqual(optional["calibration"]["classes"]["lowercase"]["source_offset_diagnostic"]["reason"], "work_limit_exceeded")


if __name__ == "__main__":
    unittest.main()
