"""Focused tests for the isolated SCORE-v2 native ink comparison builder.

Mechanical only: pin rejection, TIE-v2 choice math (ties, off-grid targets,
invalid exclusion, fallbacks), placement parity helpers and payload hygiene
(no field tensors, no external references). Browser behavior lives in
test_yinyang_oriented_score_preview_browser.mjs. Optical acceptance stays
pending by policy.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yinyang_oriented_score_preview as pv

REPO = Path(__file__).resolve().parents[3]


class TestChoiceMath(unittest.TestCase):
    def test_tie_pick_exact_tie_reports_both_lowest_first(self):
        mstar, idx, pick = pv.tie_pick([1.0, 1.0, 2.0])
        self.assertEqual(mstar, 1.0)
        self.assertEqual(idx, [0, 1])
        self.assertEqual(pick, 0)

    def test_tie_pick_tolerance_scales_with_mstar(self):
        # Deviations 100.0 and 100.0 + 5e-8: tol = 1e-9*100 = 1e-7, so tied.
        mstar, idx, pick = pv.tie_pick([100.0, 100.0 + 5e-8, 101.0])
        self.assertEqual(idx, [0, 1])
        self.assertEqual(pick, 0)
        # Just outside tolerance: sole winner.
        mstar, idx, pick = pv.tie_pick([100.0, 100.0 + 5e-7, 101.0])
        self.assertEqual(idx, [0])

    def test_oriented_choice_offgrid_target_and_domain_filter(self):
        rows = [(8, 0, 8.0), (9, 1, 5.0), (10, 2, 3.0), (14, 6, 1.0)]
        pick = pv.oriented_choice(rows, 3.7)
        self.assertEqual(pick["step"], 10)
        self.assertEqual(pick["ties"], [10])
        self.assertEqual(abs(pick["delta"]), 2)
        narrow = [(s, d, g) for (s, d, g) in rows if abs(d) <= 2]
        pick = pv.oriented_choice(narrow, 0.0)
        self.assertEqual(pick["step"], 10)
        self.assertTrue(abs(pick["delta"]) == 2)

    def test_oriented_choice_empty_domain_returns_none(self):
        self.assertIsNone(pv.oriented_choice([], 4.0))

    def test_b2_choice_tie_break_toward_metric(self):
        # Equal costs at metric-1 and metric+1: pick is metric-side nearest,
        # i.e. the lower |s - metric| then (s - metric): metric-1 wins.
        by_delta = {d: (10 + d, True, 1.1 + (0.0 if abs(d) == 1 else 0.5))
                    for d in (-2, -1, 0, 1, 2)}
        by_delta[(0)] = (10, True, 5.0)
        chosen, fallback = pv.b2_choice(10, by_delta)
        self.assertEqual(chosen, 9)
        self.assertFalse(fallback)

    def test_b2_choice_no_valid_falls_back_to_metric(self):
        by_delta = {d: (10 + d, False, None) for d in (-2, -1, 0, 1, 2)}
        chosen, fallback = pv.b2_choice(10, by_delta)
        self.assertEqual(chosen, 10)
        self.assertTrue(fallback)

    def test_b2_choice_ignores_nonfinite_interaction(self):
        by_delta = {d: (10 + d, True, float("nan")) for d in (-2, -1, 0, 1, 2)}
        by_delta[1] = (11, True, 1.3)
        chosen, fallback = pv.b2_choice(10, by_delta)
        self.assertEqual(chosen, 11)
        self.assertFalse(fallback)


class TestBuilder(unittest.TestCase):
    def test_pin_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = pv.EXPECT_SCORE_SHA
            pv.EXPECT_SCORE_SHA = "0" * 64
            try:
                with self.assertRaises(pv.PreviewPinError):
                    pv.build(str(Path(tmp) / "x"))
            finally:
                pv.EXPECT_SCORE_SHA = old

    def test_build_outputs_and_hygiene(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "visual-comparison"
            result = pv.build(str(out))
            self.assertTrue((out / "index.html").exists())
            self.assertTrue((out / "manifest.json").exists())
            self.assertTrue((out / "checks" / "expected_choices.json").exists())
            html = (out / "index.html").read_text()
            self.assertNotIn("http://", html)
            self.assertNotIn("https://", html)
            self.assertNotIn('src="', html)
            self.assertNotIn('href="', html.replace("<link", ""))
            self.assertIn("Initial target 4 is a study value", html)
            # No native title tooltips anywhere in the page markup.
            self.assertNotIn(" title=", html)
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual(manifest["corpus"]["valid_steps"], 610)
            self.assertEqual(manifest["corpus"]["invalid_steps"], 222)
            prov = json.loads((REPO / "out/diagnostics/contextual-spacing"
                               / "yinyang-oriented-fields/score-experiment-corrected"
                               / "provenance.json").read_text())
            self.assertEqual(manifest["pins"]["score"],
                             prov["score_module_sha256"])
            # Payload holds a few glyph bitmaps only: no field tensors.
            self.assertLess(result["checks"]["data_bytes"], 300000)
            expected = json.loads(
                (out / "checks" / "expected_choices.json").read_text())
            self.assertEqual(len(expected), 64 * 17 * 2 * 2)


if __name__ == "__main__":
    unittest.main()
