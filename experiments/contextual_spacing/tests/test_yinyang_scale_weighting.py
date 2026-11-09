"""Focused tests for the YinYang scale-weighting probe (mechanical only).

Covers the predeclared gates from the owning design section "YinYang scale
weighting revision": weight validation, combination fidelity, one-scale
limit, analytic gain laws vs independent measurement, grating
scale/orientation behavior, global contrast transport, zero weights,
nonfinite input, multiple strokes, pad/support, degree<->pixel dimensional
consistency and Gray p/7 homogeneity. Optical acceptance stays pending by
policy; no weight here is a perceptual recommendation.
"""
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yinyang_multiscale_fields as mf
import yinyang_oriented_fields as yf
import yinyang_scale_weighting as sw

SIGMAS = mf.DEFAULT_PARAMS.scale_sigmas_px
BANKS, _ = mf.build_multiscale_v1_bank(mf.DEFAULT_PARAMS)
KERNELS = yf.build_oriented_kernels(yf.DEFAULT_PARAMS)
GAINS = mf.per_scale_gains([np.asarray(b) for b in BANKS])
ROOT3 = math.sqrt(3.0)


def bars(width=96, x0=10, x1=12):
    img = np.zeros((20, width))
    img[4:16, x0:x1] = 1.0
    return img


def fields_of(image, weights=None, **kw):
    return mf.multiscale_glyph_fields(image, mf.DEFAULT_PARAMS, BANKS,
                                     KERNELS, weights=weights, **kw)


class WeightValidationTest(unittest.TestCase):
    def test_frozen_default_is_uniform(self):
        self.assertEqual(tuple(sw.FROZEN_WEIGHTS), (1.0,) * 5)
        self.assertEqual(tuple(sw.FROZEN_SIGMAS), tuple(SIGMAS))

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            sw.validate_weights((1.0, 1.0), 5)

    def test_negative_raises(self):
        with self.assertRaises(ValueError):
            sw.validate_weights((1.0, -0.5, 1.0, 1.0, 1.0), 5)

    def test_nonfinite_raises(self):
        for bad in (math.nan, math.inf):
            with self.assertRaises(ValueError):
                sw.validate_weights((1.0, bad, 1.0, 1.0, 1.0), 5)

    def test_all_zero_allowed(self):
        self.assertEqual(sw.validate_weights((0.0,) * 5, 5), (0.0,) * 5)

    def test_zero_weights_yield_unsupported_T(self):
        f = fields_of(bars(), weights=(0.0,) * 5)
        self.assertTrue(bool((np.asarray(f["T_combined"]) == 0.0).all()))


class CombinationFidelityTest(unittest.TestCase):
    def test_matches_stage2_and_independent_loop(self):
        f = fields_of(bars())
        w = (0.2, 0.5, 1.0, 1.5, 2.0)
        mine = sw.combine_scales(f["C_per_scale"], w)
        stage2 = mf.combine_scales(f["C_per_scale"], w)
        want = np.tensordot(np.asarray(w), np.asarray(f["C_per_scale"]),
                            axes=(0, 0))
        self.assertLess(float(np.abs(mine - stage2).max()), 1e-15)
        self.assertLess(float(np.abs(mine - want).max()), 1e-15)

    def test_one_scale_limit_reproduces_scale_response(self):
        f = fields_of(bars())
        for i in range(5):
            w = [0.0] * 5
            w[i] = 1.0
            t = sw.combine_scales(f["C_per_scale"], tuple(w))
            self.assertEqual(float(np.abs(t - f["C_per_scale"][i]).max()),
                             0.0)

    def test_center_weight_reproduces_stage1(self):
        # Recorded stage-2 G1 gate: U1 <= ~2.3e-16, d <= ~2.7e-15, support 1.0.
        cover = bars()
        fs1 = yf.oriented_fields_for_image(cover, yf.DEFAULT_PARAMS,
                                           yf.build_v1_bank(yf.DEFAULT_PARAMS),
                                           KERNELS)
        fsc = fields_of(cover, weights=(0.0, 0.0, 1.0, 0.0, 0.0))
        pa, pb = int(fs1["pad"]), int(fsc["pad"])
        h, w = cover.shape
        sl1 = (slice(pa, pa + h), slice(pa, pa + w))
        sl2 = (slice(pb, pb + h), slice(pb, pb + w))
        self.assertLess(float(np.abs(fs1["U1"][(slice(None),) + sl1]
                                    - fsc["U1"][(slice(None),) + sl2]).max()),
                        1e-12)
        both = (fs1["supported"][(slice(None),) + sl1]
                & fsc["supported"][(slice(None),) + sl2])
        # Ratio fidelity is assessed where the denominator is well above the
        # weak-band floor (U2 >= 1e-6); near-floor amplification is a
        # documented property of d = U1/U2, not a weighting defect.
        well = both & (np.asarray(fs1["U2"])[(slice(None),) + sl1] >= 1e-6
                       ) & (np.asarray(fsc["U2"])[(slice(None),) + sl2] >= 1e-6)
        with np.errstate(invalid="ignore"):
            dd = np.abs(fs1["distance"][(slice(None),) + sl1]
                        - fsc["distance"][(slice(None),) + sl2])
            self.assertLess(float(np.nanmax(dd[well])), 1e-9)
        self.assertEqual(
            float((fs1["supported"][(slice(None),) + sl1]
                   == fsc["supported"][(slice(None),) + sl2]).mean()), 1.0)

    def test_ratio_math_untouched_by_weights(self):
        # Independent recompute of d and notebook strength from stored U1/U2.
        f = fields_of(bars(), weights=(0.3, 0.7, 1.0, 1.3, 2.1))
        q = float(yf.DEFAULT_PARAMS.radial_exponent_q)
        eps = float(yf.DEFAULT_PARAMS.denominator_eps)
        u1 = np.asarray(f["U1"])
        u2 = np.asarray(f["U2"])
        sup = np.isfinite(u1) & np.isfinite(u2) & (u2 > eps)
        d = np.full_like(u1, np.nan)
        d[sup] = u1[sup] / u2[sup]
        c = np.zeros_like(u1)
        c[sup] = u1[sup] * d[sup] ** (q - 1.0)
        self.assertTrue(bool(np.array_equal(sup, np.asarray(f["supported"]))))
        with np.errstate(invalid="ignore"):
            self.assertLess(float(np.nanmax(np.abs(d - f["distance"])[sup])),
                            1e-15)
        self.assertLess(float(np.abs(c - f["confidence_notebook"]).max()),
                        1e-12)


class GainLawTest(unittest.TestCase):
    # Analytic filter-scaling laws, checked against independent measurement:
    # impulse peak ~ sigma^-3, kernel L1 ~ sigma^-1, kernel L2 ~ sigma^-2,
    # matched-sine amplitude ~ sigma^-1 (half-octave steps: sqrt(2), 2, 2.83).
    def test_impulse_peak_sigma_minus3(self):
        peaks = [g["impulse_response_peak"] for g in GAINS]
        for a, b in zip(peaks, peaks[1:]):
            self.assertAlmostEqual(a / b, 2.0 * math.sqrt(2.0), delta=0.06)

    def test_kernel_l1_sigma_minus1(self):
        l1 = [g["kernel_l1_mean"] for g in GAINS]
        for a, b in zip(l1, l1[1:]):
            self.assertAlmostEqual(a / b, math.sqrt(2.0), delta=0.08)

    def test_kernel_l2_sigma_minus2(self):
        l2 = [g["kernel_l2_mean"] for g in GAINS]
        for a, b in zip(l2, l2[1:]):
            self.assertAlmostEqual(a / b, 2.0, delta=0.2)

    def test_matched_sine_sigma_minus1(self):
        # Reference period is fixed at 4*sigma for all scales (declared
        # study choice, not each scale's empirical peak) and the finest
        # support is 3 px wide, so per-step tolerance is wide; the
        # end-to-end ratio below is the load-bearing check.
        gains = sw.matched_sine_gains(BANKS, SIGMAS)
        for a, b in zip(gains, gains[1:]):
            self.assertAlmostEqual(a / b, math.sqrt(2.0), delta=0.12)

    def test_compensation_equalizes_matched_response(self):
        gains = sw.matched_sine_gains(BANKS, SIGMAS)
        w = sw.gain_compensated_weights((1.0,) * 5, gains,
                                        convention="measured",
                                        renormalize="sum")
        self.assertAlmostEqual(sum(w), 5.0, places=12)
        resp = [gains[i] * w[i] for i in range(5)]
        for r in resp:
            self.assertAlmostEqual(r, resp[2], delta=1e-12 * max(1.0, resp[2]))

    def test_compensation_conventions_recorded(self):
        for name in ("impulse_response_peak", "kernel_l1_mean",
                     "kernel_l2_mean", "kernel_peak", "measured"):
            self.assertIn(name, sw.GAIN_CONVENTIONS)
        w = sw.gain_compensated_weights((1.0,) * 5, GAINS,
                                        convention="impulse_response_peak",
                                        renormalize="none")
        peaks = [GAINS[i]["impulse_response_peak"] * w[i] for i in range(5)]
        for p in peaks:
            self.assertAlmostEqual(p, peaks[0], delta=1e-15)

    def test_uniform_weights_favor_fine_scales(self):
        # Disclosed, not corrected: fine:coarse matched gain ~ (sigma ratio)^1.
        gains = sw.matched_sine_gains(BANKS, SIGMAS)
        self.assertAlmostEqual(gains[0] / gains[-1], 4.0, delta=0.2)


class GratingResponseTest(unittest.TestCase):
    def test_fft_matches_direct_oracle(self):
        img = sw.grating_image(8.0, 0.0, (32, 32))
        bank0 = np.asarray(BANKS[2][0])
        a = yf.convolve_fft(img, bank0)
        b = yf.convolve_direct(img, bank0)
        self.assertLess(float(np.abs(np.abs(a) - np.abs(b)).max()), 1e-9)

    def test_orientation_selective_per_scale(self):
        # Coarse grating: every scale responds more to a matched V1
        # orientation than to the orthogonal one (measured min ratio 1.29).
        img = sw.grating_image(16.0, 0.0, (64, 64))
        f = fields_of(img)
        for s in range(5):
            per_ori = [float(np.asarray(f["C_per_scale"][s][o]).max())
                       for o in range(8)]
            self.assertGreater(max(per_ori) / min(per_ori), 1.15)

    def test_gratings_are_dc_free(self):
        # Axis-aligned exact-period window integrates to zero; oblique
        # phases leave a bounded window remainder (recorded, not asserted).
        img = sw.grating_image(8.0, 0.0, (48, 48))
        self.assertAlmostEqual(float(img.mean()), 0.0, places=12)

    def test_global_contrast_transport(self):
        # T (pre-ratio, no support mask) is exactly homogeneous; the ratio
        # stage is homogeneous only on commonly supported pixels, with the
        # mask change quantified, never absorbed.
        img = sw.grating_image(8.0, 0.3, (48, 48))
        f1 = fields_of(img)
        f2 = fields_of(2.0 * img)
        t1 = np.asarray(f1["T_combined"])
        t2 = np.asarray(f2["T_combined"])
        self.assertTrue(bool(np.allclose(t2, 2.0 * t1, rtol=1e-9,
                                         atol=1e-12)))
        rep = sw.mask_change(np.asarray(f1["supported"]),
                             np.asarray(f2["supported"]))
        common = rep["common"]
        self.assertTrue(bool(np.allclose(
            np.asarray(f2["confidence_notebook"])[common],
            2.0 * np.asarray(f1["confidence_notebook"])[common],
            rtol=1e-6, atol=1e-9)))

    def test_weighted_contrast_transport(self):
        img = sw.grating_image(8.0, 0.3, (48, 48))
        w = (0.2, 0.5, 1.0, 1.5, 2.0)
        f1 = fields_of(img, weights=w)
        f2 = fields_of(2.0 * img, weights=w)
        t1 = np.asarray(f1["T_combined"])
        t2 = np.asarray(f2["T_combined"])
        self.assertTrue(bool(np.allclose(t2, 2.0 * t1, rtol=1e-9,
                                         atol=1e-12)))
        rep = sw.mask_change(np.asarray(f1["supported"]),
                             np.asarray(f2["supported"]))
        common = rep["common"]
        self.assertTrue(bool(np.allclose(
            np.asarray(f2["confidence_notebook"])[common],
            2.0 * np.asarray(f1["confidence_notebook"])[common],
            rtol=1e-6, atol=1e-9)))

    def test_contrast_masking_quantified(self):
        # Support is NOT contrast-invariant: lowering contrast moves pixels
        # below the eps floor (masking). Homogeneity holds only on the
        # common mask; the dropout is the measurement, not a failure.
        img = bars()
        full = fields_of(img)
        sup0 = np.asarray(full["supported"])
        fracs = []
        for c in (0.1, 0.01, 1e-3):
            f = fields_of(c * img)
            sup = np.asarray(f["supported"])
            rep = sw.mask_change(sup0, sup)
            self.assertGreater(rep["dropout"], 0)
            fracs.append(rep["support_scaled"])
            common = rep["common"]
            self.assertTrue(bool(np.allclose(
                np.asarray(f["confidence_notebook"])[common],
                c * np.asarray(full["confidence_notebook"])[common],
                rtol=1e-6, atol=1e-9)))
        for a, b in zip(fracs, fracs[1:]):
            self.assertLess(b, a)

    def test_low_contrast_floor_collapse(self):
        # Near the eps floor the field collapses: support is almost gone at
        # 1e-12 contrast while full contrast is well supported. No global
        # contrast invariant is claimed across this floor.
        img = bars()
        full = fields_of(img)
        tiny = fields_of(1e-12 * img)
        self.assertGreater(float(np.asarray(full["supported"]).mean()), 0.3)
        self.assertLess(float(np.asarray(tiny["supported"]).mean()), 0.01)


class StrokeSupportTest(unittest.TestCase):
    def test_separated_strokes_add(self):
        a = np.zeros((20, 96))
        a[4:16, 10:12] = 1.0
        b = np.zeros((20, 96))
        b[4:16, 60:62] = 1.0
        fa = fields_of(a)
        fb = fields_of(b)
        fab = fields_of(a + b)
        self.assertLess(float(np.abs(np.asarray(fab["T_combined"])
                                    - np.asarray(fa["T_combined"])
                                    - np.asarray(fb["T_combined"])).max()),
                        1e-12)

    def test_pad_plus8_stable(self):
        img = bars()
        fw = fields_of(img)
        pw = int(fw["pad"])
        fc = fields_of(img, pad=pw + 8)
        h, w = img.shape
        A = np.asarray(fw["T_combined"])[:, pw:pw + h, pw:pw + w]
        B = np.asarray(fc["T_combined"])[:, pw + 8:pw + 8 + h, pw + 8:pw + 8 + w]
        self.assertLess(float(np.abs(A - B).max()), 1e-12)

    def test_support_halfwidth_rule(self):
        for s in SIGMAS:
            self.assertEqual(sw.support_halfwidth_for_sigma(s),
                             int(math.ceil(4.0 * s)))

    def test_integer_cotranslation_consistent(self):
        img = bars()
        shift = 3
        moved = np.zeros_like(img)
        moved[:, shift:] = img[:, :-shift]
        f0 = fields_of(img)
        f1 = fields_of(moved)
        pw = int(f0["pad"])
        h, w = img.shape
        A = np.asarray(f0["T_combined"])[:, pw:pw + h, pw:pw + w - shift]
        B = np.asarray(f1["T_combined"])[:, pw:pw + h, pw + shift:pw + w]
        self.assertLess(float(np.abs(A - B).max()), 1e-9)


class ViewingGeometryTest(unittest.TestCase):
    def test_cpd_identity(self):
        self.assertAlmostEqual(sw.cpd_for_period_px(8.0, 40.0), 5.0)
        self.assertAlmostEqual(sw.cpd_for_period_px(8.0, 80.0),
                               2.0 * sw.cpd_for_period_px(8.0, 40.0))

    def test_period_roundtrip(self):
        self.assertAlmostEqual(sw.period_px_for_cpd(5.0, 40.0), 8.0)
        self.assertAlmostEqual(
            sw.cpd_for_period_px(sw.period_px_for_cpd(5.0, 40.0), 40.0), 5.0)

    def test_missing_ppd_raises(self):
        for bad in (None, 0.0, -3.0, math.nan, math.inf):
            with self.assertRaises(ValueError):
                sw.require_pixels_per_degree(bad)

    def test_no_universal_default(self):
        self.assertFalse(hasattr(sw, "DEFAULT_PIXELS_PER_DEGREE"))
        self.assertFalse(hasattr(sw, "DEFAULT_PERCEPTUAL_WEIGHTS"))


class GrayProfileTest(unittest.TestCase):
    def test_p7_coverage_homogeneity(self):
        # Exact p/7 input scales the pre-ratio combination, but does NOT
        # mandate identical downstream support: the mask change is measured
        # (host normalization disposition), never assumed away.
        img = bars()
        f1 = fields_of(img)
        p = 3.0 / 7.0
        f2 = fields_of(p * img)
        t1 = np.asarray(f1["T_combined"])
        t2 = np.asarray(f2["T_combined"])
        # Absolute floor: near-zero far-field pixels carry only fp rounding.
        self.assertTrue(bool(np.allclose(t2, p * t1, rtol=1e-9,
                                         atol=1e-12)))
        rep = sw.mask_change(np.asarray(f1["supported"]),
                             np.asarray(f2["supported"]))
        self.assertLess(rep["support_scaled"], rep["support_full"])
        common = rep["common"]
        self.assertTrue(bool(np.allclose(
            np.asarray(f2["confidence_notebook"])[common],
            p * np.asarray(f1["confidence_notebook"])[common],
            rtol=1e-6, atol=1e-9)))


class StudyWeightsTest(unittest.TestCase):
    def test_log_gaussian_peak_and_normalization(self):
        w = sw.log_gaussian_scale_weights(SIGMAS, peak_sigma_px=1.5,
                                          bandwidth_oct=1.0, normalize="sum")
        self.assertAlmostEqual(sum(w), 5.0, places=12)
        self.assertEqual(int(np.argmax(np.asarray(w))), 2)
        for v in w:
            self.assertTrue(math.isfinite(v) and v > 0.0)

    def test_log_gaussian_rejects_bad_params(self):
        with self.assertRaises(ValueError):
            sw.log_gaussian_scale_weights(SIGMAS, peak_sigma_px=0.0,
                                          bandwidth_oct=1.0)
        with self.assertRaises(ValueError):
            sw.log_gaussian_scale_weights(SIGMAS, peak_sigma_px=1.5,
                                          bandwidth_oct=0.0)

    def test_engine_shape_gate(self):
        # Engine consumes one weight per sigma; ratio math lives downstream.
        self.assertEqual(len(sw.FROZEN_WEIGHTS), len(sw.FROZEN_SIGMAS))
        checked = sw.validate_weights(sw.FROZEN_WEIGHTS,
                                      len(sw.FROZEN_SIGMAS))
        self.assertEqual(len(checked), len(sw.FROZEN_SIGMAS))


if __name__ == "__main__":
    unittest.main()
