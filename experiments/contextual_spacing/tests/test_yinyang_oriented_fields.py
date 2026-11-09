"""Focused tests for the YinYang oriented field stage (stage 1, cost-free).

Covers numerics and representation only: V1 complex-response semantics,
source-backed convolution parity, the oriented ratio construction, masks and
pair-diagnostic structure. Optical acceptance stays pending by policy: these
tests pin the field mechanism and its guardrails, not optical quality.
"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yinyang_oriented_fields as yf

P = yf.DEFAULT_PARAMS
REPO = Path(__file__).resolve().parents[3]
V3CAP = (REPO / "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/captures")


def bars_fixture(gap=4):
    img = np.zeros((20, 16))
    img[4:16, 4:6] = 1.0
    img[4:16, 10:12] = 1.0
    return img


class FrozenParamsTest(unittest.TestCase):
    def test_radial_exponent_is_source_value(self):
        self.assertEqual(P.radial_exponent_q, 2.0)

    def test_angular_concentration_is_notebook_width(self):
        self.assertEqual(P.angular_concentration_kappa, 4.0)

    def test_overloaded_k_has_no_single_spelling(self):
        # Upstream `k` names three things; the API must not offer one `k`.
        for field in P.__dataclass_fields__:
            self.assertNotEqual(field, "k")

    def test_single_scale_sixteen_directed(self):
        self.assertEqual(P.n_v1_orientations, 8)
        self.assertEqual(P.n_directed, 16)


class V1BankTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = yf.build_v1_bank(P)

    def test_shape_and_complex(self):
        self.assertEqual(self.bank.shape, (8, 13, 13))
        self.assertTrue(np.iscomplexobj(self.bank))

    def test_even_filter_zero_dc(self):
        for g in self.bank:
            self.assertAlmostEqual(float(g.imag.sum()), 0.0, delta=1e-12)

    def test_orientations_distinct(self):
        flat = self.bank.reshape(8, -1)
        for i in range(8):
            for j in range(i + 1, 8):
                self.assertFalse(np.allclose(flat[i], flat[j]))

    def test_magnitude_is_abs_of_response(self):
        img = bars_fixture()
        s = yf.v1_complex_responses(img, bank=self.bank, params=P)
        c = yf.v1_magnitudes(img, bank=self.bank, params=P)
        np.testing.assert_allclose(c, np.abs(s), rtol=0, atol=1e-12)
        self.assertTrue((c >= 0.0).all())


class ConvolutionOracleTest(unittest.TestCase):
    def test_fft_direct_parity_odd_kernels(self):
        rng = np.random.default_rng(0)
        for shape, kshape in [((20, 16), (25, 25)), ((20, 16), (13, 13))]:
            a, k = rng.random(shape), rng.random(kshape)
            d = float(np.abs(yf.convolve_fft(a, k) - yf.convolve_direct(a, k)).max())
            self.assertLess(d, 1e-12)

    def test_direct_rejects_even_kernels(self):
        with self.assertRaises(ValueError):
            yf.convolve_direct(np.zeros((6, 6)), np.zeros((4, 6)))

    def test_field_convolutions_match_oracle(self):
        img = bars_fixture()
        bank = yf.build_v1_bank(P)
        ker = yf.build_oriented_kernels(P)
        a = yf.oriented_fields_for_image(img, P, bank, ker, method="fft")
        b = yf.oriented_fields_for_image(img, P, bank, ker, method="direct")
        self.assertLess(float(np.abs(a["U1"] - b["U1"]).max()), 1e-12)
        self.assertLess(float(np.abs(a["U2"] - b["U2"]).max()), 1e-12)


class RatioConstructionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h1, cls.h2, cls.m1, cls.m2 = yf.build_oriented_kernels(P)

    def test_origin_singularity_zeroed(self):
        r = P.kernel_radius_px
        self.assertEqual(self.h1[:, r, r].max(), 0.0)
        self.assertEqual(self.h2[:, r, r].max(), 0.0)

    def test_kernel_masses_recorded_positive_finite(self):
        self.assertTrue(np.all(np.isfinite(self.m1)) and (self.m1 > 0).all())
        self.assertTrue(np.all(np.isfinite(self.m2)) and (self.m2 > 0).all())

    def test_point_support_distance_relation(self):
        # Delta input at the convolution stage: (T*f1)/(T*f2) must equal r.
        img = np.zeros((31, 31))
        img[15, 15] = 1.0
        u1 = yf.convolve_fft(img, self.h1[0])
        u2 = yf.convolve_fft(img, self.h2[0])
        with np.errstate(invalid="ignore", divide="ignore"):
            d = np.where(u2 > P.denominator_eps, u1 / u2, np.nan)
        ys, xs = np.mgrid[0:31, 0:31].astype(float)
        r = np.hypot(xs - 15, ys - 15)
        on = (r > 0.5) & (r < 11) & np.isfinite(d)
        self.assertLess(float(np.abs(d[on] - r[on]).max()), 1e-6)

    def test_convolution_stage_linearity(self):
        a = np.zeros((17, 17))
        a[8, 8] = 1.0
        b = np.zeros((17, 17))
        b[8, 9] = 2.0
        lhs = yf.convolve_fft(a + b, self.h1[0])
        rhs = yf.convolve_fft(a, self.h1[0]) + yf.convolve_fft(b, self.h1[0])
        self.assertLess(float(np.abs(lhs - rhs).max()), 1e-12)

    def test_contrast_scaling_distance_invariant_arc_linear(self):
        img = bars_fixture()
        bank = yf.build_v1_bank(P)
        ker = yf.build_oriented_kernels(P)
        f = yf.oriented_fields_for_image(img, P, bank, ker)
        fh = yf.oriented_fields_for_image(0.5 * img, P, bank, ker)
        with np.errstate(invalid="ignore"):
            both = f["supported"][0] & fh["supported"][0]
            self.assertLess(float(np.abs(f["distance"][0][both]
                                         - fh["distance"][0][both]).max()), 1e-12)
            ratio = fh["arc_strength"][0][both] / np.maximum(f["arc_strength"][0][both], 1e-300)
            self.assertLess(float(abs(np.median(ratio) - 0.5)), 1e-12)

    def test_manuscript_vs_notebook_strength_recorded(self):
        img = bars_fixture()
        f = yf.oriented_fields_for_image(img, P)
        with np.errstate(invalid="ignore"):
            sup = f["supported"][0]
            man = f["U1"][0][sup] * f["distance"][0][sup] ** (P.radial_exponent_q + 1.0)
            np.testing.assert_allclose(f["arc_strength"][0][sup], man, rtol=0, atol=1e-12)
            nb = f["U1"][0][sup] * f["distance"][0][sup] ** (P.radial_exponent_q - 1.0)
            np.testing.assert_allclose(f["confidence_notebook"][0][sup], nb, rtol=0, atol=1e-12)
            self.assertFalse(np.allclose(man, nb))

    def test_blank_input_unsupported_stable(self):
        f = yf.oriented_fields_for_image(np.zeros((21, 21)), P)
        self.assertEqual(int(f["supported"].sum()), 0)
        self.assertTrue((f["arc_strength"] == 0.0).all())


class RepresentationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = yf.build_v1_bank(P)
        cls.ker = yf.build_oriented_kernels(P)

    def test_facing_selectivity(self):
        img = np.zeros((20, 12))
        img[4:16, 4:6] = 1.0
        f = yf.oriented_fields_for_image(img, P, self.bank, self.ker)
        pb = int(f["pad"])
        got = float(f["arc_strength"][0, 4 + 6 + pb, 4 + 2 + 3 + pb])
        away = float(f["arc_strength"][8, 4 + 6 + pb, 4 + 2 + 3 + pb])
        self.assertGreater(got / max(away, 1e-300), 20.0)

    def test_rotation_quantizes_to_channels(self):
        img = bars_fixture()
        f = yf.oriented_fields_for_image(img, P, self.bank, self.ker)
        pad = int(f["pad"])
        mid, gc = img.shape[0] // 2 + pad, 8 + pad
        fr = yf.oriented_fields_for_image(np.rot90(img), P, self.bank, self.ker)
        gr, gc_un = mid - pad, gc - pad
        got = float(fr["arc_strength"][12, img.shape[1] - 1 - gc_un + pad, gr + pad])
        want = float(f["arc_strength"][0, mid, gc])
        self.assertLess(abs(got - want), 1e-9)

    def test_translation_consistency(self):
        wide = np.zeros((20, 64))
        wide[4:16, 20:22] = 1.0
        wide[4:16, 26:28] = 1.0
        fw = yf.oriented_fields_for_image(wide, P, self.bank, self.ker)
        pw, shift = int(fw["pad"]), 3
        shifted = np.zeros_like(wide)
        shifted[:, shift:] = wide[:, :-shift]
        fsh = yf.oriented_fields_for_image(shifted, P, self.bank, self.ker)
        with np.errstate(invalid="ignore"):
            a = fw["distance"][:, pw:pw + 20, pw:pw + 64 - shift]
            b = fsh["distance"][:, pw:pw + 20, pw + shift:pw + 64]
            td = np.abs(a - b)
            self.assertLess(float(np.nanmax(td[np.isfinite(td)])), 1e-5)

    def test_multiplicity_integrated(self):
        # Same first-gap geometry; the third stroke's support must add energy
        # at the shared gap center (single-nearest-sample cannot do this).
        two = bars_fixture()
        three = np.zeros((20, 33))
        for x in (4, 12, 20):
            three[4:16, x:x + 2] = 1.0
        f2 = yf.oriented_fields_for_image(two, P, self.bank, self.ker)
        f3 = yf.oriented_fields_for_image(three, P, self.bank, self.ker)
        p2, p3 = int(f2["pad"]), int(f3["pad"])
        got = float(f3["arc_strength"][0, 10 + p3, 8 + p3])
        base = float(f2["arc_strength"][0, 10 + p2, 8 + p2])
        self.assertGreater(got, base)

    def test_padding_converges_beyond_kernel_reach(self):
        # Extra margin past V1 half-support plus kernel radius must change
        # nothing: every original-lattice pixel is then exactly computed.
        img = bars_fixture()
        a = yf.oriented_fields_for_image(img, P, self.bank, self.ker)
        p = int(a["pad"])
        c = yf.oriented_fields_for_image(img, P, self.bank, self.ker, pad=p + 8)
        with np.errstate(invalid="ignore"):
            dd = np.abs(a["distance"][:, p:p + 20, p:p + 16]
                        - c["distance"][:, p + 8:p + 8 + 20, p + 8:p + 8 + 16])
            self.assertLess(float(np.nanmax(dd[np.isfinite(dd)])), 1e-9)

    def test_determinism(self):
        img = bars_fixture()
        a = yf.oriented_fields_for_image(img, P)
        b = yf.oriented_fields_for_image(img, P)
        np.testing.assert_array_equal(np.nan_to_num(a["distance"]), np.nan_to_num(b["distance"]))

    def test_strength_branches_labeled_primary_reference(self):
        # Reconciliation provenance: the executable notebook confidence is
        # the primary reference; the manuscript arc strength is the retained
        # alternate diagnostic. Both recorded, values distinct, neither
        # optically approved.
        img = bars_fixture()
        f = yf.oriented_fields_for_image(img, P, self.bank, self.ker)
        self.assertIn("confidence_notebook", f)
        self.assertIn("arc_strength", f)
        with np.errstate(invalid="ignore"):
            sup = f["supported"][0]
            self.assertTrue(sup.any())
            self.assertFalse(np.allclose(
                np.nan_to_num(f["confidence_notebook"][0][sup]),
                np.nan_to_num(f["arc_strength"][0][sup])))

    def test_even_support_cropped_parity(self):
        # Source reconciliation bound: truncating the symmetric odd support
        # to the even-tap rectangle (offsets -R..R-1, the notebook/oracle
        # sampling) changes well-supported distances only at the measured
        # rim magnitude; the cropped estimator agrees with the full one to
        # that bound on the bars fixture. Locks the finite-support finding
        # without depending on the frozen oracle files.
        img = bars_fixture()
        full = yf.oriented_fields_for_image(img, P, self.bank, self.ker)
        h1, h2, _, _ = self.ker
        ker24 = (h1[:, :24, :24], h2[:, :24, :24], None, None)
        crop = yf.oriented_fields_for_image(img, P, self.bank, ker24)
        p = int(full["pad"])
        with np.errstate(invalid="ignore"):
            a = full["distance"][:, p:p + 20, p:p + 16]
            b = crop["distance"][:, p:p + 20, p:p + 16]
            both = np.isfinite(a) & np.isfinite(b)
            dd = np.abs(a - b)
            self.assertLess(float(np.nanmax(dd[both])), 1.1)
            well = both & (np.minimum(full["U2"][:, p:p + 20, p:p + 16],
                                      crop["U2"][:, p:p + 20, p:p + 16]) > 1e-6)
            self.assertLess(float(np.nanmax(dd[well])), 1.1)


class PairDiagnosticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = yf.build_v1_bank(P)
        cls.ker = yf.build_oriented_kernels(P)

    def _diag(self, left, right, step):
        lf = yf.oriented_fields_for_image(left, P, self.bank, self.ker)
        rf = yf.oriented_fields_for_image(right, P, self.bank, self.ker)
        lo = (-int(lf["pad"]), -int(lf["pad"]))
        ro = (step - int(rf["pad"]), -int(rf["pad"]))
        return yf.pair_diagnostics(lf, rf, lo, ro, P)

    def test_four_quantities_no_cost(self):
        bar = np.zeros((20, 12))
        bar[4:16, 4:6] = 1.0
        d = self._diag(bar, bar, 10)
        for key in ("distance_disagreement", "strength_product", "distance_sum",
                    "orientation_argmax_left", "orientation_argmax_right",
                    "orientation_agreement", "pooled"):
            self.assertIn(key, d)
        for banned in ("cost", "chosen", "minimizing", "interaction"):
            self.assertNotIn(banned, d)
            self.assertNotIn(banned, d["pooled"])

    def test_agreement_range_and_support_fraction(self):
        bar = np.zeros((20, 12))
        bar[4:16, 4:6] = 1.0
        d = self._diag(bar, bar, 10)
        with np.errstate(invalid="ignore"):
            agree = d["orientation_agreement"][np.isfinite(d["orientation_agreement"])]
        self.assertTrue(((agree >= -1.0) & (agree <= 1.0)).all())
        self.assertGreaterEqual(d["pooled"]["both_supported_fraction"], 0.0)
        self.assertLessEqual(d["pooled"]["both_supported_fraction"], 1.0)

    def test_blank_pair_stable(self):
        d = self._diag(np.zeros((9, 9)), np.zeros((9, 9)), 4)
        self.assertEqual(d["pooled"]["both_supported_fraction"], 0.0)


class PairStrengthVariantTest(unittest.TestCase):
    # Gating consumer-semantic fix: pair diagnostics must consume the named
    # strength variant all the way through (notebook primary by default,
    # manuscript only when explicitly selected) and label which ran.
    @classmethod
    def setUpClass(cls):
        cls.bank = yf.build_v1_bank(P)
        cls.ker = yf.build_oriented_kernels(P)

    def _fields(self, img):
        return yf.oriented_fields_for_image(img, P, self.bank, self.ker,
                                           method="direct")

    def test_default_is_notebook_primary_with_identity(self):
        bar = np.zeros((20, 12))
        bar[4:16, 4:6] = 1.0
        lf = self._fields(bar)
        d = yf.pair_diagnostics(lf, lf, (0, 0), (0, 0), P)
        self.assertEqual(d["strength_variant"], "notebook")
        self.assertEqual(d["strength_field"], "confidence_notebook")
        self.assertAlmostEqual(d["strength_exponent"], P.radial_exponent_q - 1.0)
        # Notebook branch consumes the notebook array: pooled total equals the
        # independent notebook product sum on the both-supported mask.
        o = 0
        sup = lf["supported"][o]
        want = float((lf["confidence_notebook"][o][sup]
                      * lf["confidence_notebook"][o][sup]).sum())
        self.assertAlmostEqual(d["pooled"]["strength_product_total"]["0"],
                               want, delta=abs(want) * 1e-9 + 1e-12)

    def test_manuscript_branch_consumes_manuscript_array(self):
        bar = np.zeros((20, 12))
        bar[4:16, 4:6] = 1.0
        lf = self._fields(bar)
        d = yf.pair_diagnostics(lf, lf, (0, 0), (0, 0), P, strength="manuscript")
        self.assertEqual(d["strength_variant"], "manuscript")
        self.assertEqual(d["strength_field"], "arc_strength")
        self.assertAlmostEqual(d["strength_exponent"], P.radial_exponent_q + 1.0)
        o = 0
        sup = lf["supported"][o]
        want = float((lf["arc_strength"][o][sup]
                      * lf["arc_strength"][o][sup]).sum())
        self.assertAlmostEqual(d["pooled"]["strength_product_total"]["0"],
                               want, delta=abs(want) * 1e-9 + 1e-12)

    def test_invalid_variant_raises(self):
        bar = np.zeros((20, 12))
        bar[4:16, 4:6] = 1.0
        lf = self._fields(bar)
        with self.assertRaises(ValueError):
            yf.pair_diagnostics(lf, lf, (0, 0), (0, 0), P, strength="brute")

    def test_cross_branch_distance_identical_strengths_related(self):
        img = np.zeros((20, 20))
        img[5:15, 5:7] = 1.0
        img[5:15, 13:15] = 0.5
        lf = self._fields(img)
        nb = yf.pair_diagnostics(lf, lf, (0, 0), (0, 0), P, strength="notebook")
        ms = yf.pair_diagnostics(lf, lf, (0, 0), (0, 0), P, strength="manuscript")
        np.testing.assert_array_equal(np.nan_to_num(nb["distance_disagreement"]),
                                      np.nan_to_num(ms["distance_disagreement"]))
        np.testing.assert_array_equal(np.nan_to_num(nb["distance_sum"]),
                                      np.nan_to_num(ms["distance_sum"]))
        self.assertEqual(nb["pooled"]["both_supported_fraction"],
                         ms["pooled"]["both_supported_fraction"])
        # Manuscript vs notebook strengths differ by d^2 per side (q = 2):
        # mL.mR = nL.nR . dL^2 . dR^2 wherever both supported. Here both
        # sides share one field, so the ratio must equal d^4 on support.
        o = 0
        d = np.where(lf["supported"][o], lf["distance"][o], np.nan)
        feat = (lf["supported"][o] & np.isfinite(d)
                & (nb["strength_product"][o] != 0))
        self.assertTrue(feat.any())
        ratio = ms["strength_product"][o][feat] / nb["strength_product"][o][feat]
        np.testing.assert_allclose(ratio, d[feat] ** 4.0, rtol=1e-9, atol=0)

    def test_branch_divergent_direction_fixture(self):
        # The bars fixture used by the independent review: orientation-argmax
        # agreement between variants is below 1 (defect was consumer-visible),
        # and each branch argmax equals its own field's independent argmax.
        img = np.zeros((20, 20))
        img[5:15, 5:7] = 1.0
        img[5:15, 13:15] = 0.5
        lf = self._fields(img)
        nb = yf.pair_diagnostics(lf, lf, (0, 0), (0, 0), P, strength="notebook")
        ms = yf.pair_diagnostics(lf, lf, (0, 0), (0, 0), P, strength="manuscript")
        nb_arg = np.nanargmax(np.where(lf["supported"],
                                       lf["confidence_notebook"], -np.inf), axis=0)
        ms_arg = np.nanargmax(np.where(lf["supported"],
                                       lf["arc_strength"], -np.inf), axis=0)
        self.assertLess(float((nb_arg == ms_arg).mean()), 1.0)
        np.testing.assert_array_equal(
            np.nan_to_num(nb["orientation_argmax_left"]), np.nan_to_num(nb_arg))
        np.testing.assert_array_equal(
            np.nan_to_num(ms["orientation_argmax_left"]), np.nan_to_num(ms_arg))

    def test_nonfinite_image_raises_at_boundary(self):
        img = np.zeros((20, 16))
        img[4:16, 4:6] = 1.0
        bad = img.copy()
        bad[3, 3] = np.nan
        with self.assertRaises(ValueError):
            yf.oriented_fields_for_image(bad, P)


class RealGlyphSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import yinyangfit_interactive as v1
        path = V3CAP / "roboto-16-mono.json"
        if not path.exists():
            raise unittest.SkipTest(f"missing retained capture {path}")
        cls.v1 = v1
        cls.ds = v1.load_mono_capture(str(path))

    def test_um_fields_finite_where_supported(self):
        from yinyang_oriented_fields_evidence import glyph_image
        for cp in (ord("u"), ord("m")):
            cover, _ = glyph_image(self.ds, cp)
            f = yf.oriented_fields_for_image(cover, P)
            self.assertTrue(f["supported"].any())
            with np.errstate(invalid="ignore"):
                self.assertTrue(bool(np.isfinite(f["distance"][f["supported"]]).all()))

    def test_um_pair_diag_at_metric(self):
        import yinyang_oriented_fields_evidence as ev
        l, r = ord("u"), ord("m")
        step = self.v1.metric_step(self.ds, l, r)
        lf = yf.oriented_fields_for_image(ev.glyph_image(self.ds, l)[0], P)
        rf = yf.oriented_fields_for_image(ev.glyph_image(self.ds, r)[0], P)
        lo = (-int(lf["pad"]), -int(lf["pad"]))
        ro = (step - int(rf["pad"]), -int(rf["pad"]))
        d = yf.pair_diagnostics(lf, rf, lo, ro, P)
        self.assertGreater(d["pooled"]["both_supported_fraction"], 0.0)


if __name__ == "__main__":
    unittest.main()
