# cspell:words electricbubble equidist fullfield roboto tobytes yinyangfit
"""Focused tests for the Electric Bubble scale adaptation.

Mechanical gates only: parameter identity at r = 1, hand-derived kernel
checks at a non-unit scale, gradient sensitivity, walk/curve identity
against the frozen full-field port at r = 1, integer translation,
determinism and one frozen-pair end-to-end run. Response-shape
verdicts live in the evidence reports, not here.
"""

import math
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments" / "contextual_spacing"))
import electricbubble_fullfield as E
import electricbubble_scale as S
import yinyangfit_interactive as YI

DIAG = ROOT / "out" / "diagnostics" / "contextual-spacing"
CAPTURES = DIAG / "yinyangfit-interactive-v3" / "captures"

# Independently captured anchor kernel sums (js-anchor, original
# execution; see test_electricbubble_fullfield.py).
ANCHOR_KERNEL_SUMS = {
    "inkSaliency": -4.229669076562369,
    "whitespaceSaliency": 1.8294183644964384,
    "electricBubble": 8192.000335814993,
}


def synth_bars():
    def cell(w, h, top, cover):
        return {"width": w, "height": h, "top": top, "left": 0.0,
                "cover": cover}

    return {
        "A": cell(3, 12, 2, [1.0] * (3 * 12)),
        "B": cell(3, 12, 2, [1.0] * (3 * 12)),
    }


class RuleTest(unittest.TestCase):
    def test_reference_ratio(self):
        self.assertEqual(S.scale_ratio(72.0), 1.0)
        self.assertAlmostEqual(S.scale_ratio(16.0), 16.0 / 72.0)

    def test_r1_params_exact_identity(self):
        # r = 1 must recover the author's verbatim parameters exactly;
        # any deviation breaks the identity gate, not the rule.
        self.assertEqual(S.scaled_params(72.0), E.AUTHOR_DEFAULTS)

    def test_retained_params_unchanged(self):
        p = S.scaled_params(16.0)
        for key in ("gain", "bias", "angle", "valleyPeakRatio",
                    "valleyGain"):
            self.assertEqual(p["inkSaliency"][key],
                             E.AUTHOR_DEFAULTS["inkSaliency"][key])
        for key in ("angleDifferenceCoefficient", "meanAngleCoefficient",
                    "equidistImportance", "desiredInteraction",
                    "yFactors"):
            self.assertEqual(p[key], E.AUTHOR_DEFAULTS[key])
        eb = p["electricBubble"]
        self.assertEqual(eb["power"], 22.0)
        self.assertEqual(eb["initialStrength"], 1.0)
        self.assertEqual(eb["distDecay"], 2.0)

    def test_lengths_scale_covariances_scale_squared(self):
        p = S.scaled_params(16.0)
        r = 16.0 / 72.0
        self.assertEqual(p["inkSaliency"]["filterSize"], 4)
        self.assertEqual(p["whitespaceSaliency"]["filterSize"], 4)
        self.assertEqual(p["electricBubble"]["filterSize"], 14)
        self.assertAlmostEqual(p["inkSaliency"]["patchSizeX"], 75.0 * r * r)
        self.assertAlmostEqual(p["inkSaliency"]["patchSizeY"], 12.0 * r * r)
        self.assertAlmostEqual(p["whitespaceSaliency"]["patchSizeY"],
                               27.0 * r * r)

    def test_r1_kernels_match_anchor(self):
        kernels = S.scaled_kernels_for_conv(S.scaled_params(72.0))
        for key, want in ANCHOR_KERNEL_SUMS.items():
            self.assertAlmostEqual(float(kernels[key].sum()), want,
                                   delta=1e-6)

    def test_scaled_kernel_hand_values(self):
        # Hand-derived from the builder formulas at 16 px (r = 16/72):
        # at the zero-offset cell exp(0) = 1, so the whitespace Gaussian
        # peak cell equals its gain, and the DOG zero-offset cell equals
        # (peak - valley * valleyGain) * envelope * gain with every
        # unscaled Gaussian equal to 1 there: (1 - 0.5) * 0.26 = 0.13.
        # The bubble center cells keep the author's 2048 exact value for
        # every even support (dist = 0.5 at the four center cells).
        p = S.scaled_params(16.0)
        kernels = S.scaled_kernels_for_conv(p)
        ws = kernels["whitespaceSaliency"]
        hfs = p["whitespaceSaliency"]["filterSize"] / 2
        self.assertEqual(ws[int(hfs), int(hfs)],
                         E.AUTHOR_DEFAULTS["whitespaceSaliency"]["gain"])
        dog = kernels["inkSaliency"]
        hfs = p["inkSaliency"]["filterSize"] / 2
        self.assertAlmostEqual(dog[int(hfs), int(hfs)], 0.13, delta=1e-12)
        bub = kernels["electricBubble"]
        n = p["electricBubble"]["filterSize"]
        for y, x in ((n // 2 - 1, n // 2 - 1), (n // 2 - 1, n // 2),
                     (n // 2, n // 2 - 1), (n // 2, n // 2)):
            self.assertEqual(bub[y, x], 2048.0)

    def test_gradient_common_factor_agrees_on_frozen_fixture(self):
        # The chosen factors agree on this fixture. The source's additive
        # epsilons prevent extending this observation to all field values.
        cells = synth_bars()
        glyph_set = E.GlyphSet(cells)
        fields, _ = E.build_fields(glyph_set)
        left, right = fields["A"], fields["B"]
        base = E.score_at_overlap(left, right, 64)["meanInteraction"]

        class G:
            pass

        def rescaled(factor):
            g = G()
            g.bubble, g.dx, g.dy = (left.bubble, left.dx * factor,
                                    left.dy * factor)
            h = G()
            h.bubble, h.dx, h.dy = (right.bubble, right.dx * factor,
                                    right.dy * factor)
            return g, h

        for factor in (0.25, 2.0):
            g, h = rescaled(factor)
            got = E.score_at_overlap(g, h, 64)["meanInteraction"]
            self.assertAlmostEqual(got, base, delta=1e-12)

    def test_gradient_epsilon_breaks_general_scale_invariance(self):
        from types import SimpleNamespace

        def score(factor):
            left = SimpleNamespace(
                bubble=np.array([[1., 2.]]),
                dx=np.array([[1e-6, 1e-6]]) * factor, dy=np.zeros((1, 2)))
            right = SimpleNamespace(
                bubble=np.array([[2., 4.]]),
                dx=np.array([[-1e-6, 1e-6]]) * factor, dy=np.zeros((1, 2)))
            return E.score_at_overlap(left, right, 2)["meanInteraction"]

        self.assertGreater(abs(score(1) - score(2)), .1)


class IdentityTest(unittest.TestCase):
    def test_r1_fields_match_port(self):
        cells = synth_bars()
        glyph_set = E.GlyphSet(cells)
        ref, _ = E.build_fields(glyph_set)
        got, _ = S.build_scaled_fields(glyph_set, S.scaled_params(72.0))
        for key in ("A", "B"):
            for attr in ("bubble", "dx", "dy"):
                self.assertLess(
                    float(np.max(np.abs(
                        getattr(got[key], attr)
                        - getattr(ref[key], attr)))), 1e-12)

    def test_r1_curve_and_walk_match_port(self):
        cells = synth_bars()
        glyph_set = E.GlyphSet(cells)
        ref_fields, _ = E.build_fields(glyph_set)
        got_fields, _ = S.build_scaled_fields(glyph_set,
                                              S.scaled_params(72.0))
        for overlap in (60, 64, 68):
            want = E.score_at_overlap(ref_fields["A"], ref_fields["B"],
                                      overlap)["meanInteraction"]
            got = E.score_at_overlap(got_fields["A"], got_fields["B"],
                                     overlap)["meanInteraction"]
            self.assertAlmostEqual(got, want, delta=1e-12)
        want_walk = E.walk_search(ref_fields["A"], ref_fields["B"],
                                  glyph_set.pad)
        got_walk = S.scaled_walk_search(got_fields["A"], got_fields["B"],
                                        glyph_set.pad,
                                        S.scaled_params(72.0))
        self.assertEqual(got_walk["distance"], want_walk["distance"])
        self.assertEqual(got_walk["terminal"], want_walk["terminal"])


class PhaseMethodTest(unittest.TestCase):
    def test_rebased_integer_translation_preserves_overlap(self):
        # GlyphSet subtracts the union's top row, making both canvases
        # identical. This tests coordinates, not subpixel sampling phase.
        cells = synth_bars()
        glyph_set = E.GlyphSet(cells)
        shifted = {k: dict(v, top=v["top"] + 1) for k, v in cells.items()}
        shifted_set = E.GlyphSet(shifted)
        for key in cells:
            np.testing.assert_array_equal(glyph_set.canvases[key],
                                          shifted_set.canvases[key])
        for step in (6, 8, 10):
            base = E.step_to_overlap(glyph_set, "A", cells["A"],
                                     cells["B"], step)
            moved = E.step_to_overlap(shifted_set, "A", shifted["A"],
                                      shifted["B"], step)
            self.assertAlmostEqual(moved, base)
        left_only = {**cells, "A": dict(cells["A"], left=1.0)}
        left_set = E.GlyphSet(left_only)
        changed = E.step_to_overlap(left_set, "A", left_only["A"],
                                    cells["B"], 8)
        base = E.step_to_overlap(glyph_set, "A", cells["A"],
                                 cells["B"], 8)
        self.assertNotAlmostEqual(changed, base)

    def test_fields_deterministic(self):
        cells = synth_bars()
        params = S.scaled_params(16.0)
        first = S.build_scaled_fields(E.GlyphSet(cells), params)[0][
            "A"].bubble.tobytes()
        second = S.build_scaled_fields(E.GlyphSet(cells), params)[0][
            "A"].bubble.tobytes()
        self.assertEqual(first, second)


class SharedDomainTest(unittest.TestCase):
    def test_target_selection_excludes_overlap_and_other_arm_invalids(self):
        from electricbubble_scale_evidence import analyze_pair

        def record(values, invalid=()):
            return {
                "pair": "AB",
                "source_curve": [
                    {"step": s, "interaction": v, "valid": s not in invalid,
                     "project_overlap_guard": s == 0}
                    for s, v in enumerate(values)],
                "source_walk": {"terminal": {"status": "fixture"},
                                "terminalStep": 1, "distance": 1},
                "source_exhaustive_guarded": {"chosen": 1},
                "source_exhaustive": {"chosen": 0},
            }

        result = analyze_pair(record([.01, .02, .04, .06]),
                              record([.01, .04, .03, .02], invalid=(2,)), 1)
        self.assertEqual(result["raw_attain"]["feasible"], 2)
        self.assertEqual(result["scaled_attain"]["feasible"], 2)
        self.assertEqual(result["raw_attain"]["closest_steps"], [1])
        self.assertEqual(result["scaled_attain"]["closest_steps"], [3])


class FrozenPairTest(unittest.TestCase):
    def test_scaled_compare_frozen_pair_structure(self):
        dataset, cell_map = E.mono_cells_for_keys(
            str(CAPTURES / "roboto-16-mono.json"), list("og"))
        glyph_set = E.GlyphSet(cell_map)
        params = S.scaled_params(float(dataset["size_px"]))
        fields, _ = S.build_scaled_fields(glyph_set, params)
        metric = YI.metric_step(dataset, ord("o"), ord("g"))
        steps = list(range(metric - 8, metric + 9))
        rec = S.compare_scaled(glyph_set, fields, params, dataset,
                               "o", "g", steps, cell_map)
        self.assertEqual(rec["pair"], "og")
        self.assertEqual(len(rec["source_curve"]), 17)
        self.assertEqual(rec["source_walk"]["target"], 0.01)
        finite = [c for c in rec["source_curve"] if c["valid"]]
        self.assertGreater(len(finite), 0)
        for c in finite:
            self.assertTrue(math.isfinite(c["interaction"]))


if __name__ == "__main__":
    unittest.main()
