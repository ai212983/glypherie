"""Focused tests for the Electric Bubble full-field reproduction.

 Hawking risk: the Python port must track the pinned original execution, not
 just itself. Analytic tests always run; golden values below were captured
 from the independent js-anchor (byte-identical sources under pinned tfjs
 0.15.3) and fail the suite if the port drifts. The frozen proxy scorer is
 asserted unchanged by hash.
"""

import hashlib
import json
import math
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments" / "contextual_spacing"))
import electricbubble_fullfield as E
import yinyangfit_interactive as YI

DIAG = ROOT / "out" / "diagnostics" / "contextual-spacing" \
    / "electricbubble-fullfield"

# Independently captured anchor values (js-anchor, original execution).
ANCHOR_KERNEL_SUMS = {
    "inkSaliency": -4.229669076562369,
    "whitespaceSaliency": 1.8294183644964384,
    "electricBubble": 8192.000335814993,
}
ANCHOR_CONV_PROBE = [
    15.75, 31.5, 34.5, 37.5, 22.5, 20.25, 31.5, 52.5, 57.25, 62.0, 38.25,
    30.75, 49.5, 81.0, 85.75, 90.5, 56.25, 42.75, 42.75, 54.0, 57.0, 60.0,
    49.5, 38.25, 33.75, 41.25, 43.25, 45.25, 38.25, 3.75,
]
# Anchor walk distances on the frozen synthetic pairs (parity/synth_cells).
ANCHOR_SYNTH_WALKS = {"AB": 58, "CD": 58, "EF": 58}
# Anchor mean interactions for synthetic AB bars at overlaps 60..69.
ANCHOR_SYNTH_AB = [
    0.0008003681432455778, 0.0008005587151274085, 0.0008009250741451979,
    0.0008017363143153489, 0.0008043897105380893, 0.0008023664704523981,
    0.0008003675029613078, 0.0008008221047930419, 0.0008017339860089123,
    0.0008045348222367465,
]


def synth_bars():
    def cell(w, h, top, cover):
        return {"width": w, "height": h, "top": top, "left": 0.0,
                "cover": cover}

    return {
        "A": cell(3, 12, 2, [1.0] * (3 * 12)),
        "B": cell(3, 12, 2, [1.0] * (3 * 12)),
    }


class KernelTest(unittest.TestCase):
    def test_bubble_center_exact(self):
        # hfs = 30 - 0.5 = 29.5; center cells sit at dx=dy=+/-0.5, so
        # dist = 0.5 and 0.5**(-22/2) = 2048 exactly (kernels.js:50-64).
        k = E.electric_bubble_kernel(E.AUTHOR_DEFAULTS["electricBubble"])
        self.assertEqual(k.shape, (60, 60))
        for y, x in ((29, 29), (29, 30), (30, 29), (30, 30)):
            self.assertEqual(k[y, x], 2048.0)
        corner = 1.0 / ((2 * 29.5 ** 2) ** 11.0)
        self.assertAlmostEqual(k[0, 0], corner, delta=1e-12)

    def test_kernel_sums_match_anchor(self):
        kernels = E.author_kernels_for_conv()
        names = {"inkSaliency": "inkSaliency",
                 "whitespaceSaliency": "whitespaceSaliency",
                 "electricBubble": "electricBubble"}
        for key, name in names.items():
            self.assertAlmostEqual(float(kernels[key].sum()),
                                   ANCHOR_KERNEL_SUMS[name], delta=1e-6)

    def test_transpose_is_material(self):
        # The App.js transpose must be kept: the ink DOG is anisotropic, so
        # K != K.T. Dropping the transpose would silently change fields.
        raw = E.oriented_dog(E.AUTHOR_DEFAULTS["inkSaliency"])
        self.assertGreater(np.max(np.abs(raw - raw.T)), 1e-3)


class ConvTest(unittest.TestCase):
    def test_same_matches_direct(self):
        rng = np.random.default_rng(7)
        for shape, ks in (((5, 6), (4, 4)), ((7, 5), (3, 3)),
                          ((9, 9), (20, 20))):
            img = rng.normal(size=shape)
            ker = rng.normal(size=ks)
            diff = np.max(np.abs(E.same_correlate(img, ker)
                                - E.direct_correlate(img, ker)))
            self.assertLess(diff, 1e-12)

    def test_same_matches_tfjs_probe(self):
        # Independent tfjs conv2d SAME output captured from the anchor.
        inp = np.array([[float(r * 6 + c) for c in range(6)]
                        for r in range(5)])
        ker = np.array(
            [[1.0 if (r + c) % 3 == 0 else (-0.5 if (r + c) % 3 == 1 else 0.25)
              for c in range(4)] for r in range(4)])
        got = E.same_correlate(inp, ker).reshape(-1)
        want = np.array(ANCHOR_CONV_PROBE)
        self.assertLess(np.max(np.abs(got - want)), 1e-12)

    def test_gradient_sign_convention(self):
        # Correlation (not convolution): a rightward ramp under [1,-1]
        # yields -1 responses; the score is invariant to a global flip, but
        # the adapter convention is pinned here.
        ramp = np.tile(np.arange(6, dtype=np.float64), (3, 1))
        out = E.same_correlate(ramp, np.array([[1.0, -1.0]]))
        self.assertTrue(np.all(out[:, :5] == -1.0))


class WalkRuleTest(unittest.TestCase):
    def test_js_round_matches_math_round(self):
        cases = {0.5: 1, -0.5: 0, 2.5: 3, -2.5: -2, 0.4999: 0,
                 -0.0092: 0, 67.0: 67}
        for given, want in cases.items():
            self.assertEqual(E.js_round(given), want)

    def test_initial_overlap(self):
        # border = round(64 - 30 - 2) = 32; seed = min(32 + 5 + 30, .8W...).
        self.assertEqual(E.initial_overlap(133, 133, 64), 67)

    def test_guard_arms_differ_by_name(self):
        curve = [
            {"step": 6, "valid": True, "interaction": 0.0105,
             "project_overlap_guard": True},
            {"step": 7, "valid": True, "interaction": 0.5,
             "project_overlap_guard": False},
        ]
        raw = E.choose_by_author_target(curve)
        guarded = E.choose_by_author_target(curve, require_guard=True)
        self.assertEqual(raw["chosen"], 6)
        self.assertEqual(guarded["chosen"], 7)
        self.assertFalse(raw["guard"])
        self.assertTrue(guarded["guard"])


class AdapterTest(unittest.TestCase):
    def test_overlap_step_roundtrip(self):
        cells = synth_bars()
        glyph_set = E.GlyphSet(cells)
        for step in (0, 5, 8, 12):
            overlap = E.step_to_overlap(glyph_set, "A", cells["A"],
                                        cells["B"], step)
            back = E.overlap_to_step(glyph_set, "A", cells["A"], cells["B"],
                                     overlap)
            self.assertAlmostEqual(back, step)

    def test_canvas_layout_matches_author(self):
        # Author: 2 px slack, ink at x = 1 + padWidth (renderRawGlyph).
        cells = synth_bars()
        glyph_set = E.GlyphSet(cells, pad_width=64)
        canvas = glyph_set.canvases["A"]
        self.assertEqual(canvas.shape, (12, 3 + 2 + 128))
        self.assertEqual(canvas[2, 1 + 64], 1.0)
        self.assertEqual(canvas[0, 0], 0.0)

    def test_support_multiplicity_visible(self):
        # Two separated bars must score differently from one merged bar at
        # the same step: the field integrates support, the proxy does not.
        cov = [0.0] * (7 * 12)
        for r in range(12):
            for c in (0, 1, 4, 5):
                cov[r * 7 + c] = 1.0
        cells = {**synth_bars(),
                 "F": {"width": 7, "height": 12, "top": 2, "left": 0.0,
                       "cover": cov}}
        glyph_set = E.GlyphSet(cells)
        fields, _ = E.build_fields(glyph_set)
        single = E.score_at_overlap(fields["A"], fields["B"], 64)
        multi = E.score_at_overlap(fields["A"], fields["F"], 64)
        self.assertTrue(single["finite"] and multi["finite"])
        self.assertGreater(abs(single["meanInteraction"]
                               - multi["meanInteraction"]), 1e-6)

    def test_determinism(self):
        cells = synth_bars()
        first = E.build_fields(E.GlyphSet(cells))[0]["A"].bubble.tobytes()
        second = E.build_fields(E.GlyphSet(cells))[0]["A"].bubble.tobytes()
        self.assertEqual(first, second)


class FrozenProxyTest(unittest.TestCase):
    def test_proxy_module_unchanged(self):
        # Arm A must stay the pinned implementation; any edit breaks parity.
        self.assertEqual(
            YI.IMPLEMENTATION_SHA256,
            "57cffdea02fc0f0fffcbacba5151bfc7f8e8a72320611c3fdb11183915b68baf")
        self.assertEqual(YI.MODEL_IDENTITY, "yinyangfit-interactive-v1")


def parity_synth_cells():
    # Frozen synthetic fixtures (also parity/synth_cells.json): parallel
    # bars, asymmetric vertical offset, support multiplicity.
    cells = synth_bars()
    cells["C"] = dict(cells["A"])
    cells["D"] = {"width": 3, "height": 12, "top": 5, "left": 0.0,
                  "cover": [1.0] * (3 * 12)}
    cov = [0.0] * (7 * 12)
    for r in range(12):
        for c in (0, 1, 4, 5):
            cov[r * 7 + c] = 1.0
    cells["E"] = dict(cells["A"])
    cells["F"] = {"width": 7, "height": 12, "top": 2, "left": 0.0,
                  "cover": cov}
    return cells


class AnchorParityTest(unittest.TestCase):
    def test_synth_curves_match_anchor(self):
        cells = parity_synth_cells()
        glyph_set = E.GlyphSet(cells)
        fields, _ = E.build_fields(glyph_set)
        got = [E.score_at_overlap(fields["A"], fields["B"], o)
               ["meanInteraction"] for o in range(60, 70)]
        for g, w in zip(got, ANCHOR_SYNTH_AB):
            self.assertAlmostEqual(g, w, delta=1e-6)

    def test_synth_walks_match_anchor(self):
        cells = parity_synth_cells()
        glyph_set = E.GlyphSet(cells)
        fields, _ = E.build_fields(glyph_set)
        for pair, want in ANCHOR_SYNTH_WALKS.items():
            got = E.walk_search(fields[pair[0]], fields[pair[1]], 64)
            self.assertEqual(got["distance"], want)


if __name__ == "__main__":
    unittest.main()
