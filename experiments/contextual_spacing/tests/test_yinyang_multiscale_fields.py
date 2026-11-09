"""Focused tests for the YinYang multiscale field stage (stage 2, cost-free).

Covers numerics and representation only: frozen progression/weights,
per-scale gains, the single-scale limiting case against stage 1, the
weighted-sum combination, masks/diagnostics structure and guardrails.
Optical acceptance stays pending by policy: these tests pin the field
mechanism, not optical quality.
"""
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yinyang_multiscale_fields as mf
import yinyang_oriented_fields as yf

P = mf.DEFAULT_PARAMS
P1 = yf.DEFAULT_PARAMS
REPO = Path(__file__).resolve().parents[3]
V3CAP = (REPO / "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/captures")


def bars_fixture():
    img = np.zeros((20, 16))
    img[4:16, 4:6] = 1.0
    img[4:16, 10:12] = 1.0
    return img


class FrozenParamsTest(unittest.TestCase):
    def test_half_octave_progression_around_baseline(self):
        self.assertEqual(len(P.scale_sigmas_px), 5)
        for got, k in zip(P.scale_sigmas_px, (-2, -1, 0, 1, 2)):
            self.assertAlmostEqual(got, 1.5 * 2.0 ** (k / 2.0), delta=1e-12)
        self.assertAlmostEqual(P.scale_sigmas_px[2], 1.5, delta=1e-12)

    def test_neutral_uniform_default_weights(self):
        self.assertEqual(tuple(P.scale_weights), (1.0,) * 5)

    def test_single_scale_sixteen_directed(self):
        self.assertEqual(P.n_v1_orientations, 8)
        self.assertEqual(P.n_directed, 16)

    def test_support_halfwidths_generalize_stage1_rule(self):
        self.assertEqual(
            [mf.support_halfwidth_for_sigma(s) for s in P.scale_sigmas_px],
            [3, 5, 6, 9, 12])

    def test_stage_pad_is_max_support_plus_radius(self):
        self.assertEqual(mf.stage_pad_multiscale(P), 12 + 12)

    def test_weights_must_cover_every_scale(self):
        with self.assertRaises(ValueError):
            mf.multiscale_glyph_fields(bars_fixture(), P, weights=(1.0, 1.0))


class MultiscaleBankTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.banks, cls.halfwidths = mf.build_multiscale_v1_bank(P)

    def test_bank_count_and_shapes(self):
        self.assertEqual(len(self.banks), 5)
        for bank, w in zip(self.banks, (3, 5, 6, 9, 12)):
            self.assertEqual(np.asarray(bank).shape, (8, 2 * w + 1, 2 * w + 1))

    def test_center_bank_is_stage1_bank(self):
        stage1 = yf.build_v1_bank(P1)
        np.testing.assert_array_equal(np.asarray(self.banks[2]), stage1)

    def test_even_partners_demeaned(self):
        for bank in self.banks:
            for g in np.asarray(bank):
                self.assertAlmostEqual(float(g.imag.sum()), 0.0, delta=1e-12)

    def test_gains_recorded_fine_scales_dominant(self):
        gains = mf.per_scale_gains([np.asarray(b) for b in self.banks])
        self.assertEqual(len(gains), 5)
        for g in gains:
            for key in ("kernel_l1_mean", "kernel_l2_mean", "kernel_peak",
                        "impulse_response_peak"):
                self.assertTrue(np.isfinite(g[key]) and g[key] > 0.0)
        peaks = [g["impulse_response_peak"] for g in gains]
        self.assertGreater(peaks[0], peaks[-1])


class CombinationTest(unittest.TestCase):
    def test_weighted_sum_matches_independent_recompute(self):
        rng = np.random.default_rng(0)
        c = np.abs(rng.normal(size=(5, 8, 9, 11)))
        w = (0.25, 0.5, 1.0, 2.0, 4.0)
        got = mf.combine_scales(c, w)
        want = np.einsum("s,s...", np.asarray(w), c)
        np.testing.assert_allclose(got, want, rtol=0, atol=1e-12)

    def test_single_active_weight_is_exact(self):
        rng = np.random.default_rng(1)
        c = np.abs(rng.normal(size=(5, 8, 9, 11)))
        for s in range(5):
            w = [0.0] * 5
            w[s] = 1.0
            np.testing.assert_array_equal(mf.combine_scales(c, tuple(w)), c[s])

    def test_uniform_weights_sum_all_scales(self):
        rng = np.random.default_rng(2)
        c = np.abs(rng.normal(size=(5, 8, 9, 11)))
        np.testing.assert_allclose(
            mf.combine_scales(c, (1.0,) * 5), c.sum(axis=0), rtol=0, atol=1e-12)


class LimitingCaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank1 = yf.build_v1_bank(P1)
        cls.ker1 = yf.build_oriented_kernels(P1)
        cls.banks, _ = mf.build_multiscale_v1_bank(P)

    def test_center_only_reproduces_stage1(self):
        # Single-active center weight must reproduce stage 1 on the shared
        # original lattice. Tolerances are condition-aware, not tuned looks:
        # the two pipelines pad differently (18 vs 24 px), so their FFTs
        # differ in size and round in the last ulp (measured U1 <= 4.5e-16,
        # d <= 5.2e-13 over 10 trials); support masks agree exactly there.
        img = bars_fixture()
        a = yf.oriented_fields_for_image(img, P1, self.bank1, self.ker1)
        b = mf.multiscale_glyph_fields(
            img, P, self.banks, self.ker1, weights=(0.0, 0.0, 1.0, 0.0, 0.0))
        pa, pb = int(a["pad"]), int(b["pad"])
        for key in ("U1", "U2"):
            np.testing.assert_allclose(
                a[key][:, pa:pa + 20, pa:pa + 16],
                b[key][:, pb:pb + 20, pb:pb + 16], rtol=0, atol=1e-12)
        for key in ("arc_strength", "confidence_notebook"):
            np.testing.assert_allclose(
                a[key][:, pa:pa + 20, pa:pa + 16],
                b[key][:, pb:pb + 20, pb:pb + 16], rtol=0, atol=1e-9)
        with np.errstate(invalid="ignore"):
            dd = np.abs(a["distance"][:, pa:pa + 20, pa:pa + 16]
                        - b["distance"][:, pb:pb + 20, pb:pb + 16])
            both = (a["supported"][:, pa:pa + 20, pa:pa + 16]
                    & b["supported"][:, pb:pb + 20, pb:pb + 16])
            self.assertLess(float(np.nanmax(dd[both])), 1e-9)
        np.testing.assert_array_equal(
            a["supported"][:, pa:pa + 20, pa:pa + 16],
            b["supported"][:, pb:pb + 20, pb:pb + 16])

    def test_fine_only_equals_manual_single_scale(self):
        img = bars_fixture()
        w = (1.0, 0.0, 0.0, 0.0, 0.0)
        b = mf.multiscale_glyph_fields(img, P, self.banks, self.ker1,
                                       weights=w)
        np.testing.assert_array_equal(
            b["T_combined"], b["C_per_scale"][0])
        self.assertTrue(b["supported"].any())


class RepresentationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.banks, _ = mf.build_multiscale_v1_bank(P)
        cls.ker = yf.build_oriented_kernels(P1)

    def test_output_keys_and_no_cost(self):
        f = mf.multiscale_glyph_fields(bars_fixture(), P, self.banks,
                                       self.ker)
        for key in ("C_per_scale", "T_combined", "U1", "U2", "distance",
                    "arc_strength", "confidence_notebook", "supported",
                    "per_scale_gains", "scale_sigmas_px", "scale_weights"):
            self.assertIn(key, f)
        for banned in ("cost", "chosen", "minimizing", "interaction",
                       "score", "placement"):
            self.assertNotIn(banned, f)
        self.assertEqual(f["C_per_scale"].shape[0], 5)
        self.assertEqual(f["T_combined"].shape, (8,) + f["image_shape"])
        self.assertEqual(f["U1"].shape[0], 16)

    def test_pair_diagnostics_reused_no_cost(self):
        bar = np.zeros((20, 12))
        bar[4:16, 4:6] = 1.0
        lf = mf.multiscale_glyph_fields(bar, P, self.banks, self.ker)
        rf = mf.multiscale_glyph_fields(bar, P, self.banks, self.ker)
        lo = (-int(lf["pad"]), -int(lf["pad"]))
        d = mf.pair_diagnostics(lf, rf, lo, lo, P1)
        for banned in ("cost", "chosen", "minimizing", "interaction"):
            self.assertNotIn(banned, d)
            self.assertNotIn(banned, d["pooled"])

    def test_contrast_scaling_distance_invariant_arc_linear(self):
        # d is scale-invariant and strengths scale linearly, on
        # well-supported pixels (min U2 > 1e-6): near the absolute floor the
        # ratio amplifies last-ulp FFT-alignment noise (measured up to ~1e-3
        # there), which is declared behavior, not a defect. Support can only
        # shrink under contrast loss (absolute floor); values stay finite.
        img = bars_fixture()
        f = mf.multiscale_glyph_fields(img, P, self.banks, self.ker)
        fh = mf.multiscale_glyph_fields(0.5 * img, P, self.banks, self.ker)
        self.assertLessEqual(int(fh["supported"].sum()),
                             int(f["supported"].sum()))
        for g in (f, fh):
            with np.errstate(invalid="ignore"):
                self.assertTrue(bool(np.isfinite(
                    g["distance"][g["supported"]]).all()))
        with np.errstate(invalid="ignore"):
            well = (f["supported"][0] & fh["supported"][0]
                    & (np.minimum(f["U2"][0], fh["U2"][0]) > 1e-6))
            self.assertTrue(well.any())
            self.assertLess(float(np.abs(f["distance"][0][well]
                                         - fh["distance"][0][well]).max()),
                            1e-8)
            ratio = (fh["confidence_notebook"][0][well]
                     / np.maximum(f["confidence_notebook"][0][well], 1e-300))
            self.assertLess(float(abs(np.median(ratio) - 0.5)), 1e-9)

    def test_blank_input_unsupported_stable(self):
        f = mf.multiscale_glyph_fields(np.zeros((21, 21)), P)
        self.assertEqual(int(f["supported"].sum()), 0)
        self.assertTrue((f["arc_strength"] == 0.0).all())
        self.assertTrue((f["confidence_notebook"] == 0.0).all())

    def test_determinism(self):
        # Bitwise identity does not hold for d everywhere: last-ulp
        # FFT-alignment noise (~1e-15 absolute) is amplified by the ratio
        # near the absolute floor. Determinism is pinned where it is real:
        # C/T/U to 1e-12, d on well-supported pixels to 1e-8, exact support
        # agreement, finite values elsewhere (measured over 10 trials).
        a = mf.multiscale_glyph_fields(bars_fixture(), P)
        b = mf.multiscale_glyph_fields(bars_fixture(), P)
        for key in ("C_per_scale", "T_combined", "U1", "U2"):
            np.testing.assert_allclose(a[key], b[key], rtol=0, atol=1e-12)
        np.testing.assert_array_equal(a["supported"], b["supported"])
        with np.errstate(invalid="ignore"):
            well = (a["supported"][0] & b["supported"][0]
                    & (np.minimum(a["U2"][0], b["U2"][0]) > 1e-6))
            self.assertTrue(well.any())
            self.assertLess(float(np.abs(a["distance"][0][well]
                                         - b["distance"][0][well]).max()),
                            1e-8)
            self.assertTrue(bool(np.isfinite(
                a["distance"][a["supported"]]).all()))

    def test_translation_consistency(self):
        # Integer co-translation reproduces fields on the shared lattice.
        # Bound 5e-5 carries margin over the measured 1.1e-5 (10 trials):
        # zero-padding boundary effects plus last-ulp alignment noise,
        # summed over five scales.
        wide = np.zeros((20, 64))
        wide[4:16, 20:22] = 1.0
        wide[4:16, 26:28] = 1.0
        fw = mf.multiscale_glyph_fields(wide, P, self.banks, self.ker)
        pw, shift = int(fw["pad"]), 3
        shifted = np.zeros_like(wide)
        shifted[:, shift:] = wide[:, :-shift]
        fsh = mf.multiscale_glyph_fields(shifted, P, self.banks, self.ker)
        with np.errstate(invalid="ignore"):
            a = fw["distance"][:, pw:pw + 20, pw:pw + 64 - shift]
            b = fsh["distance"][:, pw:pw + 20, pw + shift:pw + 64]
            td = np.abs(a - b)
            self.assertLess(float(np.nanmax(td[np.isfinite(td)])), 5e-5)


class InputValidationTest(unittest.TestCase):
    # Owning-boundary gates: nonfinite/negative weights and nonfinite images
    # raise before silent clipping or support drop. All-zero weights stay the
    # legitimate explicit-unsupported vector.
    def test_combine_scales_rejects_bad_weights(self):
        rng = np.random.default_rng(3)
        c = np.abs(rng.normal(size=(5, 8, 4, 4))) + 0.25
        for bad in ((1.0, 1.0, -1.0, 1.0, 1.0),
                    (1.0, 1.0, float("nan"), 1.0, 1.0),
                    (1.0, 1.0, float("inf"), 1.0, 1.0)):
            with self.assertRaises(ValueError):
                mf.combine_scales(c, bad)

    def test_multiscale_rejects_bad_weights(self):
        img = bars_fixture()
        for bad in ((1.0, 1.0, -1.0, 1.0, 1.0),
                    (float("nan"), 1.0, 1.0, 1.0, 1.0)):
            with self.assertRaises(ValueError):
                mf.multiscale_glyph_fields(img, weights=bad)

    def test_all_zero_weights_explicit_unsupported(self):
        f = mf.multiscale_glyph_fields(bars_fixture(),
                                       weights=(0.0, 0.0, 0.0, 0.0, 0.0))
        self.assertEqual(int(f["supported"].sum()), 0)
        self.assertTrue(bool(np.isfinite(np.nan_to_num(f["U1"])).all()))

    def test_nonfinite_image_raises_at_boundary(self):
        bad = bars_fixture()
        bad[3, 3] = np.nan
        with self.assertRaises(ValueError):
            mf.multiscale_glyph_fields(bad)
        with self.assertRaises(ValueError):
            yf.oriented_fields_for_image(bad)


class RealGlyphSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import yinyangfit_interactive as v1
        path = V3CAP / "roboto-16-mono.json"
        if not path.exists():
            raise unittest.SkipTest(f"missing retained capture {path}")
        cls.ds = v1.load_mono_capture(str(path))

    def test_um_fields_finite_where_supported(self):
        from yinyang_oriented_fields_evidence import glyph_image
        banks, _ = mf.build_multiscale_v1_bank(P)
        for cp in (ord("u"), ord("m")):
            cover, _ = glyph_image(self.ds, cp)
            f = mf.multiscale_glyph_fields(cover, P, v1_banks=banks)
            self.assertTrue(f["supported"].any())
            with np.errstate(invalid="ignore"):
                self.assertTrue(bool(np.isfinite(
                    f["distance"][f["supported"]]).all()))


if __name__ == "__main__":
    unittest.main()
