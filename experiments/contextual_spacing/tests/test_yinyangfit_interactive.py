"""Focused tests for the isolated YinYangFit-inspired interactive experiment.

No maintained renderer, preview or baseline is touched; fixtures are the
existing delivered captures. Optical acceptance stays pending by policy.
"""
import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yinyangfit_interactive as yy

REPO = Path(__file__).resolve().parents[3]
MONO_ROBOTO = (REPO / "out/diagnostics/contextual-spacing/preset-preview"
               / "captures/Roboto/capture.json")
GRAY_ROBOTO = (REPO / "out/diagnostics/contextual-spacing/hu-source-relative-grayscale"
               / "captures/Roboto.json")
GRAY24_ROBOTO = (REPO / "out/diagnostics/contextual-spacing/yinyangfit-interactive"
                 / "captures24/Roboto-24-gray.json")
GRAY24_LITERATA = (REPO / "out/diagnostics/contextual-spacing/yinyangfit-interactive"
                   / "captures24/Literata-24-gray.json")


class InteractiveScorerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path in (MONO_ROBOTO, GRAY_ROBOTO):
            if not path.exists():
                raise unittest.SkipTest(f"missing retained capture {path}")
        cls.mono = yy.load_mono_capture(str(MONO_ROBOTO))
        cls.gray = yy.load_gray_capture(str(GRAY_ROBOTO))
        cls.scorer = yy.PairScorer(cls.mono)

    def test_deterministic_repeat_evaluation(self):
        first = self.scorer.evaluate_pair(ord("n"), ord("n"), yy.DEFAULT_CONTROLS)
        second = self.scorer.evaluate_pair(ord("n"), ord("n"), yy.DEFAULT_CONTROLS)
        self.assertEqual(first, second)

    def test_finite_nonconstant_costs(self):
        evaluation = self.scorer.evaluate_pair(ord("A"), ord("V"), yy.DEFAULT_CONTROLS)
        costs = [c["cost"] for c in evaluation["candidates"] if c["valid"]]
        self.assertGreaterEqual(len(costs), 2)
        for cost in costs:
            self.assertTrue(math.isfinite(cost))
        self.assertGreater(max(costs) - min(costs), 0.0)

    def test_padding_safe_storage_margins(self):
        """Transparent storage margins around both cells change nothing."""
        dataset = {"profile": "mono", "size_px": 16.0, "source_path": "test",
                   "cells": {}, "adjustments": dict(self.mono["adjustments"])}
        for codepoint in (ord("n"), ord("o")):
            cell = self.mono["cells"][codepoint]
            width, height = cell["width"] + 6, cell["height"] + 6
            padded = [0.0] * (width * height)
            for row in range(cell["height"]):
                for col in range(cell["width"]):
                    padded[(row + 3) * width + col + 3] = cell["cover"][row * cell["width"] + col]
            dataset["cells"][codepoint] = {"width": width, "height": height,
                                           "left": cell["left"] - 3, "top": cell["top"] - 3,
                                           "cover": padded, "advance_px": cell["advance_px"]}
        padded_scorer = yy.PairScorer(dataset)
        plain = self.scorer.evaluate_pair(ord("n"), ord("o"), yy.DEFAULT_CONTROLS)
        repadded = padded_scorer.evaluate_pair(ord("n"), ord("o"), yy.DEFAULT_CONTROLS)
        self.assertEqual(plain["chosen"], repadded["chosen"])
        for a, b in zip(plain["candidates"], repadded["candidates"]):
            self.assertEqual(a["valid"], b["valid"])
            if a["valid"]:
                self.assertAlmostEqual(a["cost"], b["cost"], places=12)

    def test_order_independence(self):
        forward = yy.layout_text(self.mono, self.scorer, "lynx",
                                 yy.DEFAULT_CONTROLS)
        strains = ["ly", "yn", "nx"]
        for gap, strain in zip(forward["gaps"], strains):
            direct = self.scorer.evaluate_pair(ord(strain[0]), ord(strain[1]),
                                               yy.DEFAULT_CONTROLS)
            self.assertEqual(gap["chosen"], direct["chosen"])
        backward = yy.layout_text(self.mono, self.scorer, "xnyl",
                                  yy.DEFAULT_CONTROLS)
        by_pair = {(g["pair"][0], g["pair"][1]): g["chosen"] for g in backward["gaps"]}
        self.assertEqual(by_pair[(ord("n"), ord("y"))],
                         self.scorer.evaluate_pair(ord("n"), ord("y"),
                                                   yy.DEFAULT_CONTROLS)["chosen"])

    def test_overlap_guard_invalid_and_recorded(self):
        evaluation = self.scorer.evaluate_pair(ord("o"), ord("o"), yy.DEFAULT_CONTROLS)
        blocked = [c for c in evaluation["candidates"] if not c["valid"]]
        self.assertTrue(blocked)
        for record in blocked:
            self.assertIsNone(record["cost"])
            self.assertIn(record["reason"],
                          ("occupied_cell_overlap", "zero_attention", "nonfinite_score",
                           "no_background_window", "blank_glyph_no_ink"))
        self.assertTrue(evaluation["fallback"] or evaluation["chosen"] is not None)

    def test_cohesion_moves_placements(self):
        pairs = [(ord(a), ord(b)) for a, b in
                 ("nn", "oo", "AV", "To", "HH", "ll", "ya", "rd")]
        loose = [self.scorer.evaluate_pair(l, r, yy.YYControls(cohesion=0.4))["chosen"]
                 for l, r in pairs]
        tight = [self.scorer.evaluate_pair(l, r, yy.YYControls(cohesion=1.8))["chosen"]
                 for l, r in pairs]
        self.assertTrue(any(a != b for a, b in zip(loose, tight)),
                        "cohesion endpoints must move at least one pair")

    def test_scale_and_falloff_move_placements(self):
        pairs = [(ord(a), ord(b)) for a, b in
                 ("nn", "oo", "AV", "To", "HH", "ll", "ya", "rd", "ca", "os")]
        base = [self.scorer.evaluate_pair(l, r, yy.DEFAULT_CONTROLS)["chosen"]
                for l, r in pairs]
        scaled = [self.scorer.evaluate_pair(
            l, r, yy.YYControls(feature_scale=1.0))["chosen"] for l, r in pairs]
        sloped = [self.scorer.evaluate_pair(
            l, r, yy.YYControls(proximity_falloff=3.0))["chosen"] for l, r in pairs]
        self.assertTrue(any(a != b for a, b in zip(base, scaled)),
                        "feature_scale must move at least one pair")
        self.assertTrue(any(a != b for a, b in zip(base, sloped)),
                        "proximity_falloff must move at least one pair")

    def test_settings_identity_stable_and_sensitive(self):
        controls = yy.DEFAULT_CONTROLS
        self.assertEqual(yy.settings_identity(controls), yy.settings_identity(controls))
        other = yy.YYControls(cohesion=1.2)
        self.assertNotEqual(yy.settings_identity(controls), yy.settings_identity(other))

    def test_gray_uses_coverage_without_threshold(self):
        scorer = yy.PairScorer(self.gray)
        evaluation = scorer.evaluate_pair(ord("A"), ord("V"), yy.DEFAULT_CONTROLS)
        valid = [c for c in evaluation["candidates"] if c["valid"]]
        self.assertTrue(valid)
        for record in valid:
            self.assertTrue(math.isfinite(record["cost"]))
        # Fringe coverage participates: gray overlap fires where mono stays clear.
        gray_blocked = [c for c in evaluation["candidates"]
                        if c["reason"] == "occupied_cell_overlap"]
        mono = self.scorer.evaluate_pair(ord("A"), ord("V"), yy.DEFAULT_CONTROLS)
        mono_blocked = [c for c in mono["candidates"]
                        if c["reason"] == "occupied_cell_overlap"]
        self.assertGreaterEqual(len(gray_blocked), len(mono_blocked))

    def test_boundary_and_tie_records_present(self):
        for pair in ("nn", "AV", "To"):
            evaluation = self.scorer.evaluate_pair(
                ord(pair[0]), ord(pair[1]), yy.DEFAULT_CONTROLS)
            self.assertIn("boundary_hit", evaluation)
            self.assertIn("minimizing_steps", evaluation)
            self.assertTrue(evaluation["minimizing_steps"])
            self.assertIn(evaluation["chosen"], evaluation["minimizing_steps"])
            for record in evaluation["candidates"]:
                self.assertIn("finite", record)
                if record["valid"]:
                    self.assertIn("interaction", record)
                    self.assertIn("attention_sum", record)
                    self.assertIn("fields", record)
                    self.assertEqual(set(record["fields"]),
                                     {"distance_disagreement", "strength_product",
                                      "distance_sum", "orientation"})

    def test_minimizing_set_uses_global_minimum_tolerance(self):
        """Near-tie minimizing set anchors at the global minimum.

        Costs [0.9e-9, 0, 1.8e-9]: index 2 is near index 0 but outside
        tolerance of the minimum, so the set is [step0, step1] and the
        metric-nearest of those wins. Guards the Python side of the
        browser parity contract (see the near-tie fixture in
        test_yinyangfit_interactive_page.mjs).
        """
        metric = yy.metric_step(self.mono, ord("n"), ord("n"))
        costs = [0.9e-9, 0.0, 1.8e-9, None, 5.0]

        class StubScorer(yy.PairScorer):
            def score_step(self, left, right, step, controls):
                index = step - (metric - 2)
                cost = costs[index]
                return {"step": step,
                        "cost": cost,
                        "valid": cost is not None,
                        "reason": None if cost is not None else "zero_attention",
                        "metric": metric}

        evaluation = StubScorer(self.mono).evaluate_pair(
            ord("n"), ord("n"), yy.DEFAULT_CONTROLS)
        self.assertEqual(evaluation["minimizing_steps"],
                         [metric - 2, metric - 1])
        self.assertEqual(evaluation["chosen"], metric - 1)

    @staticmethod
    def _raw_gray_origins(path, text):
        """Independent capture arithmetic, bypassing the experiment module.

        Fractional 26.6 pen accumulates advance plus pair adjustment per
        gap; only draw origins round (floor(x + 0.5) for the nonneg pens
        of a left-aligned word). Mirrors the native surface invariant in
        crates/generator/src/surface.rs.
        """
        capture = json.loads(Path(path).read_text())
        font = capture["font"]
        advances = {glyph["codepoint"]: glyph["advance_26_6"] / 64.0
                    for glyph in font["glyphs"]}
        kerning = {(pair["left"], pair["right"]): pair["adjustment_26_6"] / 64.0
                   for pair in font.get("kerning", [])}
        codepoints = [ord(c) for c in text]
        origins, pen = [0], 0.0
        for left, right in zip(codepoints, codepoints[1:]):
            pen += advances[left] + kerning.get((left, right), 0.0)
            origins.append(math.floor(pen + 0.5))
        return origins

    def test_captured_source_baseline_matches_capture_arithmetic(self):
        """Captured-source draws come from capture arithmetic, pinned.

        Expected vectors are the independently verified draw origins for
        Hamburg (fractional 26.6 accumulation with 26.6 kerning, rounded
        for draw), not a self-comparison against another module output.
        """
        for path, expected in ((GRAY24_ROBOTO, [0, 17, 30, 51, 65, 78, 86]),
                               (GRAY24_LITERATA, [0, 20, 33, 55, 70, 85, 96])):
            if not Path(path).exists():
                raise unittest.SkipTest(f"missing retained capture {path}")
            dataset = yy.load_gray_capture(str(path))
            baseline = yy.captured_source_word_origins(dataset, "Hamburg")
            self.assertEqual(baseline["origins"],
                             self._raw_gray_origins(str(path), "Hamburg"))
            self.assertEqual(baseline["origins"], expected)

    def test_gray_metric_sums_differ_from_captured_draws(self):
        """metric_step rounds each pair; the baseline accumulates fractionally.

        Documents the corrected H2 distinction on Roboto 24 px Gray
        Hamburg: integer-pair sums versus captured-source draw origins.
        """
        if not GRAY24_ROBOTO.exists():
            raise unittest.SkipTest(f"missing retained capture {GRAY24_ROBOTO}")
        dataset = yy.load_gray_capture(str(GRAY24_ROBOTO))
        codepoints = [ord(c) for c in "Hamburg"]
        sums, total = [0], 0
        for left, right in zip(codepoints, codepoints[1:]):
            total += yy.metric_step(dataset, left, right)
            sums.append(total)
        self.assertEqual(sums, [0, 17, 30, 51, 64, 77, 85])
        baseline = yy.captured_source_word_origins(dataset, "Hamburg")
        self.assertEqual(baseline["origins"], [0, 17, 30, 51, 65, 78, 86])
        self.assertNotEqual(sums, baseline["origins"])

    def test_experiment_word_layout_differs_from_captured_baseline(self):
        """Candidate origins are cumulative integer choices, not draws."""
        if not GRAY24_ROBOTO.exists():
            raise unittest.SkipTest(f"missing retained capture {GRAY24_ROBOTO}")
        dataset = yy.load_gray_capture(str(GRAY24_ROBOTO))
        scorer = yy.PairScorer(dataset)
        candidate = yy.layout_text(dataset, scorer, "Hamburg",
                                   yy.DEFAULT_CONTROLS)
        baseline = yy.captured_source_word_origins(dataset, "Hamburg")
        self.assertNotEqual(candidate["origins"], baseline["origins"])
        for gap in candidate["gaps"]:
            self.assertIsInstance(gap["chosen"], int)
            self.assertEqual(gap["metric"], yy.metric_step(
                dataset, gap["pair"][0], gap["pair"][1]))

    def test_mono_captured_matches_integer_sums(self):
        """Mono advances are whole pixels, so both policies agree."""
        codepoints = [ord(c) for c in "lynx"]
        sums, total = [0], 0
        for left, right in zip(codepoints, codepoints[1:]):
            total += yy.metric_step(self.mono, left, right)
            sums.append(total)
        baseline = yy.captured_source_word_origins(self.mono, "lynx")
        self.assertEqual(baseline["origins"], sums)

    def test_invalid_controls_rejected(self):
        with self.assertRaises(ValueError):
            yy.YYControls(cohesion=float("nan"))
        with self.assertRaises(ValueError):
            yy.YYControls(feature_scale=99.0)
        with self.assertRaises(ValueError):
            yy.YYControls(proximity_falloff=0.0)


if __name__ == "__main__":
    unittest.main()
