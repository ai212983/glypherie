"""Focused tests for the scale-discounted grouping score G3 (mechanical only).

Pins the new reduction over frozen fields: m=0 identity with SCORE-v2,
hand-computed analytic values, map-score exactness, symmetry, translation,
contrast invariance, abstain/no-zero-win, scale transport of the reduction,
far-stem dilution mechanism on controlled fields, variant selection and the
T3 rule. Optical acceptance stays pending by policy.
"""
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yinyang_oriented_fields as yf
import yinyang_oriented_score as sc
import yinyang_scale_grouping as sg

P1 = yf.DEFAULT_PARAMS


def hand_fields():
    """Two-channel, 1x2 analytic fixture (only the (0,1) pair carries)."""
    sup = np.ones((2, 1, 2), dtype=bool)
    dist = np.array([[[1.0, 2.0]], [[3.0, 2.0]]])
    conf = np.array([[[2.0, 1.0]], [[0.0, 0.0]]])
    conf_r = np.array([[[0.0, 0.0]], [[3.0, 1.0]]])
    base = {"supported": sup, "U2": np.full((2, 1, 2), 2.0),
            "distance": dist, "arc_strength": np.zeros((2, 1, 2)),
            "image_shape": (1, 2)}
    lf = dict(base, confidence_notebook=conf)
    rf = dict(base, confidence_notebook=conf_r)
    return lf, rf


def score_hand(m=1.0, strength="notebook", tau=0.5):
    lf, rf = hand_fields()
    EL = np.array([4.0, 9.0])
    ER = np.array([4.0, 9.0])
    origin, shape = (0, 0), (1, 2)
    return sg.score_step_scale(lf, rf, (0, 0), (0, 0), origin, shape,
                               EL, ER, tau, strength, m)


def bars_img(w=48, bars=((20, 22),)):
    img = np.zeros((20, w))
    for x0, x1 in bars:
        img[4:16, x0:x1] = 1.0
    return img


def stage1(img):
    return yf.oriented_fields_for_image(img, P1)


class IdentityWithG2Test(unittest.TestCase):
    def test_m0_matches_frozen_g2_bitwise(self):
        lf, rf = hand_fields()
        EL = np.array([4.0, 9.0])
        ER = np.array([4.0, 9.0])
        got = score_hand(m=0.0)
        ref = sc.score_step(lf, rf, (0, 0), (0, 0), (0, 0), (1, 2),
                            EL, ER, 0.5, "notebook")
        self.assertEqual(got["g3"], ref["g2"])
        self.assertEqual(got["raw3"], ref["raw"])
        self.assertEqual(got["g2"], ref["g2"])

    def test_m0_identity_excludes_degenerate_zero_distances(self):
        lf, rf = hand_fields()
        lf = dict(lf, distance=np.zeros_like(lf["distance"]))
        rf = dict(rf, distance=np.zeros_like(rf["distance"]))
        energy = np.array([4.0, 9.0])
        got = sg.score_step_scale(lf, rf, (0, 0), (0, 0), (0, 0), (1, 2),
                                  energy, energy, scale_exponent=0.0)
        reference = sc.score_step(lf, rf, (0, 0), (0, 0), (0, 0), (1, 2),
                                  energy, energy)
        self.assertTrue(got["abstain"])
        self.assertEqual(got["g3"], 0.0)
        self.assertGreater(reference["g2"], 0.0)

    def test_m0_matches_g2_on_real_fields(self):
        lf, rf = stage1(bars_img()), stage1(bars_img())
        EL, ER = sc.self_energy(lf), sc.self_energy(rf)
        origin, shape = sc.union_canvas(lf["image_shape"], (0, 0),
                                        rf["image_shape"], [(7, 0)])
        for ro in ((0, 0), (7, 0)):
            got = sg.score_step_scale(lf, rf, (0, 0), ro, origin, shape,
                                      EL, ER, 0.5, "notebook", 0.0)
            ref = sc.score_step(lf, rf, (0, 0), ro, origin, shape,
                                EL, ER, 0.5, "notebook")
            self.assertEqual(got["g3"], ref["g2"])


class AnalyticValuesTest(unittest.TestCase):
    def test_hand_fixture_numbers(self):
        e8 = math.exp(-8.0)
        den = 6.0
        s2 = 6.0 * e8 + 1.0
        s3 = 3.0 * e8 + 0.5
        got = score_hand(m=1.0)
        self.assertAlmostEqual(got["g2"], s2 / den, places=12)
        self.assertAlmostEqual(got["g3"], s3 / den, places=12)
        self.assertAlmostEqual(got["g3_over_g2"], s3 / s2, places=12)
        self.assertAlmostEqual(got["scale_mean_px"], 2.0, places=12)
        self.assertAlmostEqual(got["scale_min_px"], 2.0, places=12)
        self.assertAlmostEqual(got["scale_max_px"], 2.0, places=12)
        self.assertAlmostEqual(got["near_ink_share"], 0.0, places=12)
        self.assertEqual(got["both_supported_pairpx"], 4)
        self.assertFalse(got["abstain"])

    def test_near_ink_share_uses_normalized_score_mass(self):
        shape = (4, 1, 4)
        lc = np.zeros(shape)
        rc = np.zeros(shape)
        lc[0, 0, [0, 2]] = [10.0, 100.0]
        rc[2, 0, [0, 3]] = [10.0, 100.0]
        lc[1, 0, 1] = rc[3, 0, 1] = 1.0
        dl = np.full(shape, 2.0)
        dr = np.full(shape, 2.0)
        dl[0, 0, 0] = dr[2, 0, 0] = 0.5
        def fields(c, d):
            return {"supported": c > 0, "U2": np.full(shape, 2.0),
                    "distance": d, "confidence_notebook": c,
                    "arc_strength": c, "image_shape": (1, 4)}
        lf, rf = fields(lc, dl), fields(rc, dr)
        got = sg.score_step_scale(lf, rf, (0, 0), (0, 0), (0, 0), (1, 4),
                                  sc.self_energy(lf), sc.self_energy(rf))
        normalized_near = (100.0 / 0.5) / 10100.0
        normalized_far = 1.0 / 2.0
        self.assertAlmostEqual(got["near_ink_share"],
                               normalized_near / (normalized_near + normalized_far))
        self.assertAlmostEqual(got["raw_near_ink_share"], 200.0 / 200.5)
        self.assertLess(got["near_ink_share"], 0.5)
        self.assertGreater(got["raw_near_ink_share"], 0.5)

    def test_map_sums_to_score(self):
        lf, rf = hand_fields()
        EL = np.array([4.0, 9.0])
        ER = np.array([4.0, 9.0])
        got = score_hand(m=1.0)
        mp = sg.contribution_map_scale(lf, rf, (0, 0), (0, 0), (0, 0),
                                       (1, 2), EL, ER, 0.5, "notebook", 1.0)
        self.assertAlmostEqual(float(np.sum(mp)), got["g3"], places=12)
        mp2 = sg.contribution_map_scale(lf, rf, (0, 0), (0, 0), (0, 0),
                                        (1, 2), EL, ER, 0.5, "notebook", 2.0)
        got2 = score_hand(m=2.0)
        self.assertAlmostEqual(float(np.sum(mp2)), got2["g3"], places=12)


class InvarianceTest(unittest.TestCase):
    def _bars(self):
        lf, rf = stage1(bars_img()), stage1(bars_img())
        EL, ER = sc.self_energy(lf), sc.self_energy(rf)
        return lf, rf, EL, ER

    def _on_canvas(self, lf, rf, lo, ro):
        origin, shape = sc.union_canvas(lf["image_shape"], lo,
                                        rf["image_shape"], [ro])
        return sg.score_step_scale(lf, rf, lo, ro, origin, shape,
                                   sc.self_energy(lf), sc.self_energy(rf),
                                   0.5, "notebook", 1.0)

    def test_translation(self):
        lf, rf, _, _ = self._bars()
        a = self._on_canvas(lf, rf, (0, 0), (5, 0))
        b = self._on_canvas(lf, rf, (3, -2), (8, -2))
        self.assertEqual(a["g3"], b["g3"])
        self.assertEqual(a["scale_mean_px"], b["scale_mean_px"])

    def test_lr_swap_symmetric(self):
        # L/R swap reorders channel-pair accumulation, so agreement holds
        # within the frozen 1e-9 relative bound, not bitwise.
        lf, rf, _, _ = self._bars()
        a = self._on_canvas(lf, rf, (0, 0), (5, 0))
        b = self._on_canvas(rf, lf, (5, 0), (0, 0))
        self.assertAlmostEqual(a["g3"], b["g3"],
                               delta=1e-9 * max(1.0, abs(b["g3"])))
        self.assertAlmostEqual(a["scale_mean_px"], b["scale_mean_px"],
                               delta=1e-9 * max(1.0, abs(b["scale_mean_px"])))

    def test_contrast_gain(self):
        lf = stage1(bars_img())
        lf2 = stage1(2.5 * bars_img())
        rf = stage1(bars_img())
        EL, ER = sc.self_energy(lf), sc.self_energy(rf)
        EL2 = sc.self_energy(lf2)
        origin, shape = sc.union_canvas(lf["image_shape"], (0, 0),
                                        rf["image_shape"], [(5, 0)])
        a = sg.score_step_scale(lf, rf, (0, 0), (5, 0), origin, shape,
                                EL, ER, 0.5, "notebook", 1.0)
        b = sg.score_step_scale(lf2, rf, (0, 0), (5, 0), origin, shape,
                                EL2, ER, 0.5, "notebook", 1.0)
        self.assertAlmostEqual(a["g3"], b["g3"], delta=1e-9 * max(1, b["g3"]))
        self.assertAlmostEqual(a["scale_mean_px"], b["scale_mean_px"],
                               delta=1e-9)


class AbstainTest(unittest.TestCase):
    def test_no_both_supported_abstains(self):
        lf, rf = hand_fields()
        rf = dict(rf, supported=np.zeros_like(rf["supported"]))
        EL = np.array([4.0, 9.0])
        ER = np.array([4.0, 9.0])
        got = sg.score_step_scale(lf, rf, (0, 0), (5, 0), (0, 0), (1, 7),
                                  EL, ER, 0.5, "notebook", 1.0)
        self.assertEqual(got["g3"], 0.0)
        self.assertTrue(got["abstain"])
        self.assertTrue(math.isnan(got["scale_mean_px"]))

    def test_nonpositive_scale_never_zero_wins(self):
        lf, rf = hand_fields()
        lf = dict(lf, distance=np.zeros_like(lf["distance"]))
        rf = dict(rf, distance=np.zeros_like(rf["distance"]))
        EL = np.array([4.0, 9.0])
        ER = np.array([4.0, 9.0])
        got = sg.score_step_scale(lf, rf, (0, 0), (0, 0), (0, 0), (1, 2),
                                  EL, ER, 0.5, "notebook", 1.0)
        self.assertEqual(got["g3"], 0.0)
        self.assertTrue(got["abstain"])


class ReductionSemanticsTest(unittest.TestCase):
    def test_scale_transport_of_reduction(self):
        # dd = 0 throughout, so kval = 1 before and after doubling d.
        sup = np.ones((2, 1, 2), dtype=bool)
        u2 = np.full((2, 1, 2), 2.0)
        dist = np.array([[[1.0, 2.0]], [[0.0, 0.0]]])
        dist_r = np.array([[[0.0, 0.0]], [[1.0, 2.0]]])
        conf = np.array([[[2.0, 1.0]], [[0.0, 0.0]]])
        conf_r = np.array([[[0.0, 0.0]], [[3.0, 1.0]]])

        def mk(d, dr):
            return ({"supported": sup, "U2": u2, "distance": d,
                     "confidence_notebook": conf,
                     "arc_strength": np.zeros((2, 1, 2)),
                     "image_shape": (1, 2)},
                    {"supported": sup, "U2": u2, "distance": dr,
                     "confidence_notebook": conf_r,
                     "arc_strength": np.zeros((2, 1, 2)),
                     "image_shape": (1, 2)})
        EL = ER = np.array([1.0, 1.0])
        lf, rf = mk(dist, dist_r)
        lf2, rf2 = mk(2.0 * dist, 2.0 * dist_r)
        kw = dict(lo=(0, 0), ro=(0, 0), canvas_origin=(0, 0),
                  canvas_shape=(1, 2), EL=EL, ER=ER, tau=0.5,
                  strength="notebook", scale_exponent=1.0)
        base = sg.score_step_scale(lf, rf, **kw)
        got = sg.score_step_scale(lf2, rf2, **kw)
        # base weights 6 @ sigma 1 and 1 @ sigma 2: S = 8/7.
        self.assertAlmostEqual(base["scale_mean_px"], 8.0 / 7.0, places=12)
        self.assertAlmostEqual(got["scale_mean_px"],
                               2.0 * base["scale_mean_px"], places=12)
        self.assertAlmostEqual(got["g3"], base["g3"] / 2.0, places=12)

    def test_far_stem_discount_mechanism(self):
        sup = np.ones((2, 1, 2), dtype=bool)
        u2 = np.full((2, 1, 2), 2.0)
        dist = np.array([[[1.0, 9.0]], [[0.0, 0.0]]])
        dist_r = np.array([[[0.0, 0.0]], [[1.0, 9.0]]])

        def mk(conf, conf_r):
            return ({"supported": sup, "U2": u2, "distance": dist,
                     "confidence_notebook": conf,
                     "arc_strength": np.zeros((2, 1, 2)),
                     "image_shape": (1, 2)},
                    {"supported": sup, "U2": u2, "distance": dist_r,
                     "confidence_notebook": conf_r,
                     "arc_strength": np.zeros((2, 1, 2)),
                     "image_shape": (1, 2)})
        EL = ER = np.array([1.0, 1.0])
        z = np.zeros((2, 1, 2))
        gap_l, gap_r = mk(np.array([[[1.0, 0.0]], [[0.0, 0.0]]]),
                          np.array([[[0.0, 0.0]], [[1.0, 0.0]]]))
        wide_l, wide_r = mk(np.array([[[1.0, 1.0]], [[0.0, 0.0]]]),
                            np.array([[[0.0, 0.0]], [[1.0, 1.0]]]))
        kw = dict(lo=(0, 0), ro=(0, 0), canvas_origin=(0, 0),
                  canvas_shape=(1, 2), EL=EL, ER=ER, tau=0.5,
                  strength="notebook")
        g2_gap = sg.score_step_scale(gap_l, gap_r,
                                     scale_exponent=0.0, **kw)["g3"]
        g2_wide = sg.score_step_scale(wide_l, wide_r,
                                      scale_exponent=0.0, **kw)["g3"]
        g3_gap = sg.score_step_scale(gap_l, gap_r,
                                     scale_exponent=1.0, **kw)["g3"]
        g3_wide = sg.score_step_scale(wide_l, wide_r,
                                      scale_exponent=1.0, **kw)["g3"]
        rel2 = (g2_wide - g2_gap) / g2_gap
        rel3 = (g3_wide - g3_gap) / g3_gap
        self.assertAlmostEqual(rel2, 1.0, places=12)
        self.assertAlmostEqual(rel3, 1.0 / 9.0, places=12)
        self.assertLess(rel3, rel2)


class VariantAndTargetTest(unittest.TestCase):
    def test_bad_variant_raises(self):
        lf, rf = hand_fields()
        EL = np.array([4.0, 9.0])
        with self.assertRaises(ValueError):
            sg.score_step_scale(lf, rf, (0, 0), (0, 0), (0, 0), (1, 2),
                                EL, EL, 0.5, "quarto", 1.0)

    def test_bad_exponent_or_tau_raise(self):
        lf, rf = hand_fields()
        EL = np.array([4.0, 9.0])
        for bad in (dict(scale_exponent=-1.0), dict(tau=0.0),
                    dict(tau=float("nan"))):
            with self.assertRaises(ValueError):
                sg.score_step_scale(lf, rf, (0, 0), (0, 0), (0, 0), (1, 2),
                                    EL, EL, **bad)

    def test_manuscript_variant_differs_by_construction(self):
        lf, rf = hand_fields()
        arc = np.array([[[5.0, 7.0]], [[0.0, 0.0]]])
        arc_r = np.array([[[0.0, 0.0]], [[5.0, 7.0]]])
        lf = dict(lf, arc_strength=arc)
        rf = dict(rf, arc_strength=arc_r)
        EL = ER = np.array([1.0, 1.0])
        nb = sg.score_step_scale(lf, rf, (0, 0), (0, 0), (0, 0), (1, 2),
                                 EL, ER, 0.5, "notebook", 1.0)["g3"]
        ms = sg.score_step_scale(lf, rf, (0, 0), (0, 0), (0, 0), (1, 2),
                                 EL, ER, 0.5, "manuscript", 1.0)["g3"]
        self.assertNotEqual(nb, ms)

    def test_t3_rule(self):
        rec = sg.apply_t3([1.0, 0.4, 0.4 + 1e-12, 2.0], 0.4)
        self.assertEqual(rec["tie_pick_lowest"], 1)
        self.assertEqual(rec["tie_idx"], [1, 2])
        with self.assertRaises(ValueError):
            sg.apply_t3([1.0], float("nan"))


if __name__ == "__main__":
    unittest.main()
