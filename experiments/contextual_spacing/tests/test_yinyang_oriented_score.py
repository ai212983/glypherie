"""Focused tests for the YinYang stage-3 SCORE-v2 interpreter (mechanical only).

Pins the score mechanism over frozen fields: variant selection, isolated
normalizers, facing weights, Cauchy bound, symmetry, determinism, embedding
invariance, zero/abstain handling, TIE-v2 and the manual-sum oracle.
Optical acceptance stays pending by policy.
"""
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yinyang_oriented_fields as yf
import yinyang_multiscale_fields as mf
import yinyang_oriented_score as sc
import yinyangfit_interactive as v1

P1 = yf.DEFAULT_PARAMS
REPO = Path(__file__).resolve().parents[3]
V3CAP = (REPO / "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3"
         / "captures")


def bars_fixture(w=48, x0=20, x1=22):
    img = np.zeros((20, w))
    img[4:16, x0:x1] = 1.0
    return img


def stage1_fields(img, **kw):
    return yf.oriented_fields_for_image(img, P1, **kw)


def tiny_fields():
    return {
        "supported": np.ones((2, 2, 3), dtype=bool),
        "U2": np.full((2, 2, 3), 2.0),
        "distance": np.array([[[1.0, 1.0, 1.0], [1.0, 1.0, 1.0]],
                              [[2.0, 2.0, 2.0], [2.0, 2.0, 2.0]]]),
        "confidence_notebook": np.array([[[1.0, 2.0, 0.0], [0.0, 1.0, 1.0]],
                                         [[1.0, 1.0, 1.0], [2.0, 0.0, 1.0]]]),
        "arc_strength": np.zeros((2, 2, 3)),
        "image_shape": (2, 3),
    }


def score_on_union(lf, rf, lo, ro, EL, ER, tau=0.5, strength="notebook"):
    origin, shape = sc.union_canvas(lf["image_shape"], lo,
                                    rf["image_shape"], [ro])
    return sc.score_step(lf, rf, lo, ro, origin, shape, EL, ER, tau,
                         strength)


class FacingMatrixTest(unittest.TestCase):
    def test_sum_is_128(self):
        self.assertAlmostEqual(float(np.sum(sc.facing_matrix(16))), 128.0,
                               places=9)

    def test_diagonal_zero_symmetric_nonneg(self):
        F = sc.facing_matrix(16)
        self.assertTrue(bool(np.all(np.diag(F) == 0.0)))
        self.assertTrue(bool(np.all(F >= 0.0)))
        self.assertTrue(bool(np.allclose(F, F.T)))


class StrengthVariantTest(unittest.TestCase):
    def test_resolve_names(self):
        self.assertEqual(sc.resolve_strength("notebook"),
                         "confidence_notebook")
        self.assertEqual(sc.resolve_strength("manuscript"), "arc_strength")

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            sc.resolve_strength("bogus")

    def test_manuscript_is_U1_d3(self):
        lf = stage1_fields(bars_fixture())
        sup = lf["supported"]
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = lf["arc_strength"][sup] / (
                lf["confidence_notebook"][sup]
                * lf["distance"][sup] ** 2)
        finite = ratio[np.isfinite(ratio)]
        self.assertTrue(finite.size > 0)
        self.assertTrue(bool(np.allclose(finite, 1.0, rtol=1e-9)))

    def test_manuscript_energy_recomputed(self):
        lf = stage1_fields(bars_fixture())
        en = sc.self_energy(lf, "notebook")
        em = sc.self_energy(lf, "manuscript")
        self.assertFalse(bool(np.array_equal(en, em)))
        self.assertTrue(bool(np.all(em >= 0.0)))


class EnergyCacheTest(unittest.TestCase):
    def test_stable_and_step_independent(self):
        lf = stage1_fields(bars_fixture())
        cache = sc.EnergyCache()
        e1 = cache.energy(("g", 1), lf, "notebook")
        e2 = cache.energy(("g", 1), lf, "notebook")
        self.assertTrue(bool(np.array_equal(e1, e2)))
        self.assertEqual(e1.shape, (16,))

    def test_blank_zero(self):
        lf = stage1_fields(np.zeros((12, 12)))
        self.assertTrue(bool(np.all(sc.self_energy(lf, "notebook") == 0.0)))

    def test_same_key_different_capture_fields_recomputes(self):
        first = tiny_fields()
        second = dict(first)
        second["confidence_notebook"] = first["confidence_notebook"] * 0.5
        cache = sc.EnergyCache()
        old = cache.energy(("stage2", ord("u")), first)
        actual = cache.energy(("stage2", ord("u")), second)
        np.testing.assert_array_equal(actual, sc.self_energy(second))
        self.assertFalse(np.array_equal(actual, old))

    def test_same_key_changed_support_recomputes(self):
        first = tiny_fields()
        second = dict(first)
        second["supported"] = first["supported"].copy()
        second["supported"][:, 0, 0] = False
        cache = sc.EnergyCache()
        cache.energy("glyph", first)
        np.testing.assert_array_equal(cache.energy("glyph", second),
                                      sc.self_energy(second))


class WeakContributionTest(unittest.TestCase):
    def test_share_uses_normalized_channel_contributions(self):
        c = np.full((16, 1, 4), 10.0)
        c[:2] = 0.1
        fields = {
            "supported": np.ones(c.shape, dtype=bool),
            "U2": np.full(c.shape, 2.0),
            "distance": np.zeros(c.shape),
            "confidence_notebook": c,
            "arc_strength": c.copy(),
            "image_shape": (1, 4),
        }
        fields["U2"][0, 0, 0] = 1e-9
        energy = sc.self_energy(fields)
        got = score_on_union(fields, fields, (0, 0), (0, 0),
                             energy, energy)
        self.assertAlmostEqual(got["g2"], 128.0, places=10)
        # One of four pixels in channel 0 contributes row+column facing
        # mass 16/4 out of total 128, regardless of channel amplitude.
        self.assertAlmostEqual(got["floor_share"], 1.0 / 32.0, places=12)


class ManualSumTest(unittest.TestCase):
    def test_tiny_matches_independent_loop(self):
        tiny = tiny_fields()
        EL = sc.self_energy(tiny, "notebook")
        got = score_on_union(tiny, tiny, (0, 0), (0, 0), EL, EL.copy())
        th = yf.directed_angles(2)
        c = np.where(tiny["supported"], tiny["confidence_notebook"], 0.0)
        d = np.where(tiny["supported"], tiny["distance"], 0.0)
        E = np.array([np.sum(c[i] ** 2) for i in range(2)])
        exp_n = 0.0
        for a in range(2):
            for b in range(2):
                w = math.sin((th[a] - th[b]) / 2.0) ** 2
                den = math.sqrt(E[a] * E[b])
                if w == 0.0 or den <= 0:
                    continue
                for yy in range(2):
                    for xx in range(3):
                        if not (tiny["supported"][a, yy, xx]
                                and tiny["supported"][b, yy, xx]):
                            continue
                        dd = abs(d[a, yy, xx] - d[b, yy, xx])
                        exp_n += (w * c[a, yy, xx] * c[b, yy, xx]
                                  * math.exp(-dd * dd / 0.5) / den)
        self.assertAlmostEqual(got["g2"], exp_n, places=12)


class ScorePropertiesTest(unittest.TestCase):
    def test_cauchy_bound(self):
        a = stage1_fields(bars_fixture())
        b = stage1_fields(bars_fixture(x0=30, x1=32))
        EA, EB = sc.self_energy(a, "notebook"), sc.self_energy(b, "notebook")
        o, sh = sc.union_canvas(a["image_shape"], (0, 0),
                                b["image_shape"], [(6, 0)])
        g = sc.score_step(a, b, (0, 0), (6, 0), o, sh, EA, EB)["g2"]
        self.assertGreaterEqual(g, 0.0)
        self.assertLessEqual(g, 128.0)

    def test_symmetry(self):
        a = stage1_fields(bars_fixture())
        b = stage1_fields(bars_fixture(x0=30, x1=32))
        EA, EB = sc.self_energy(a, "notebook"), sc.self_energy(b, "notebook")
        o, sh = sc.union_canvas(a["image_shape"], (0, 0),
                                b["image_shape"], [(6, 0)])
        fwd = sc.score_step(a, b, (0, 0), (6, 0), o, sh, EA, EB)["g2"]
        rev = sc.score_step(b, a, (6, 0), (0, 0), o, sh, EB, EA)["g2"]
        self.assertLess(abs(fwd - rev) / max(fwd, 1e-300), 1e-9)

    def test_determinism_bitwise(self):
        a = stage1_fields(bars_fixture())
        EA = sc.self_energy(a, "notebook")
        o, sh = sc.union_canvas(a["image_shape"], (0, 0),
                                a["image_shape"], [(0, 0)])
        r1 = sc.score_step(a, a, (0, 0), (0, 0), o, sh, EA, EA)
        r2 = sc.score_step(a, a, (0, 0), (0, 0), o, sh, EA, EA)
        self.assertEqual(r1["g2"], r2["g2"])
        self.assertEqual(r1["raw"], r2["raw"])

    def test_cotranslation_exact(self):
        a = stage1_fields(bars_fixture())
        b = stage1_fields(bars_fixture(x0=30, x1=32))
        EA, EB = sc.self_energy(a, "notebook"), sc.self_energy(b, "notebook")
        o, sh = sc.union_canvas(a["image_shape"], (0, 0),
                                b["image_shape"], [(6, 0)])
        r1 = sc.score_step(a, b, (0, 0), (6, 0), o, sh, EA, EB)["g2"]
        o2, sh2 = sc.union_canvas(a["image_shape"], (3, -2),
                                  b["image_shape"], [(9, -2)])
        r2 = sc.score_step(a, b, (3, -2), (9, -2), o2, sh2, EA, EB)["g2"]
        self.assertEqual(r1, r2)

    def test_domain_widening_shared_steps(self):
        a = stage1_fields(bars_fixture())
        EA = sc.self_energy(a, "notebook")
        narrow = [(s, 0) for s in (-2, -1, 0, 1, 2)]
        broad = [(s, 0) for s in (-6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6)]
        on, shn = sc.union_canvas(a["image_shape"], (0, 0),
                                  a["image_shape"], narrow)
        ob, shb = sc.union_canvas(a["image_shape"], (0, 0),
                                  a["image_shape"], broad)
        for ro in narrow:
            gn = sc.score_step(a, a, (0, 0), ro, on, shn, EA, EA)["g2"]
            gb = sc.score_step(a, a, (0, 0), ro, ob, shb, EA, EA)["g2"]
            self.assertLess(abs(gn - gb) / max(gn, 1e-300), 1e-12)

    def test_mixed_shape_lattices_on_union(self):
        a = stage1_fields(bars_fixture())
        wide = np.zeros((20, 72))
        wide[4:16, 20:22] = 1.0
        wide[4:16, 44:46] = 1.0
        b = stage1_fields(wide)
        self.assertNotEqual(a["image_shape"], b["image_shape"])
        EA, EB = sc.self_energy(a, "notebook"), sc.self_energy(b, "notebook")
        o, sh = sc.union_canvas(a["image_shape"], (0, 0),
                                b["image_shape"], [(8, 0)])
        r = sc.score_step(a, b, (0, 0), (8, 0), o, sh, EA, EB)
        self.assertTrue(math.isfinite(r["g2"]))
        self.assertGreaterEqual(r["g2"], 0.0)
        self.assertLessEqual(r["g2"], 128.0)

    def test_contrast_scale_cancels_on_tiny(self):
        tiny = tiny_fields()
        EL = sc.self_energy(tiny, "notebook")
        half = {k: (v * 0.5 if k == "confidence_notebook" else v)
                for k, v in tiny.items()}
        ELh = sc.self_energy(half, "notebook")
        g1 = score_on_union(tiny, tiny, (0, 0), (0, 0), EL, EL)["g2"]
        g2 = score_on_union(half, half, (0, 0), (0, 0), ELh, ELh)["g2"]
        self.assertAlmostEqual(g1, g2, places=12)


class ZeroFallbackTest(unittest.TestCase):
    def test_zero_channel_contributes_zero(self):
        tiny = tiny_fields()
        EL = sc.self_energy(tiny, "notebook")
        EL0 = EL.copy()
        EL0[0] = 0.0
        ER = EL.copy()
        r = score_on_union(tiny, tiny, (0, 0), (0, 0), EL0, ER)
        self.assertTrue(math.isfinite(r["g2"]))
        self.assertGreaterEqual(r["g2"], 0.0)

    def test_all_unsupported_abstains(self):
        blank = stage1_fields(np.zeros((12, 12)))
        Eb = sc.self_energy(blank, "notebook")
        o, sh = sc.union_canvas(blank["image_shape"], (0, 0),
                                blank["image_shape"], [(0, 0)])
        r = sc.score_step(blank, blank, (0, 0), (0, 0), o, sh, Eb, Eb)
        self.assertEqual(r["g2"], 0.0)
        self.assertEqual(r["both_supported_pairpx"], 0)

    def test_no_nan_leaks(self):
        a = stage1_fields(bars_fixture())
        EA = sc.self_energy(a, "notebook")
        o, sh = sc.union_canvas(a["image_shape"], (0, 0),
                                a["image_shape"], [(4, 0)])
        r = sc.score_step(a, a, (0, 0), (4, 0), o, sh, EA, EA)
        for key in ("g2", "raw", "floor_share"):
            self.assertTrue(math.isfinite(r[key]), key)


class TiePolicyTest(unittest.TestCase):
    def test_single_pick_lowest_step(self):
        idx, mstar = sc.tie_set([5.0, 3.0, 3.0, 4.0])
        self.assertEqual(idx, [1, 2])
        self.assertEqual(min(idx), 1)

    def test_tolerance_scales(self):
        idx, mstar = sc.tie_set([10.0, 10.0 + 5e-9])
        self.assertEqual(idx, [0, 1])


class RealGlyphSmokeTest(unittest.TestCase):
    def test_um_roboto16mono_finite(self):
        ds = v1.load_mono_capture(
            str(V3CAP / "roboto-16-mono.json"))
        l, r = ord("u"), ord("m")
        cell = ds["cells"][l]
        w, h = cell["width"], cell["height"]
        lc = np.asarray(cell["cover"], dtype=np.float64).reshape(h, w)
        rc_cell = ds["cells"][r]
        rc = np.asarray(rc_cell["cover"], dtype=np.float64).reshape(
            rc_cell["height"], rc_cell["width"])
        lf = stage1_fields(lc)
        rf = stage1_fields(rc)
        lo = sc.glyph_padded_origin(cell, int(lf["pad"]))
        ro0 = sc.glyph_padded_origin(rc_cell, int(rf["pad"]))
        metric = v1.metric_step(ds, l, r)
        EL, ER = sc.self_energy(lf, "notebook"), sc.self_energy(rf,
                                                                "notebook")
        ros = [(ro0[0] + metric + d, ro0[1]) for d in (-2, -1, 0, 1, 2)]
        o, sh = sc.union_canvas(lf["image_shape"], lo, rf["image_shape"],
                                ros)
        vals = []
        for ro in ros:
            step = int(round(ro[0] - ro0[0]))
            if v1.contact_counts(ds["cells"][l], ds["cells"][r], step)[0] > 0:
                continue
            g = sc.score_step(lf, rf, lo, ro, o, sh, EL, ER)["g2"]
            self.assertTrue(math.isfinite(g))
            vals.append(g)
        self.assertTrue(len(vals) > 0)
        self.assertTrue(all(0.0 <= g <= 128.0 for g in vals))


if __name__ == "__main__":
    unittest.main()
