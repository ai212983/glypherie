"""Focused tests for the YinYang local-normalization repair pilot (mechanical only).

Pins two candidate classes over frozen oriented fields against the predeclared
falsifiers in "YinYang local normalization repair": contact, parallel bars,
mm/ll multiplicity, counters, diagonals, isolated far-energy addition,
interacting extra stroke, duplication/extent/zero-padding/contrast/Gray
invariance, forward-step domain, target 0/unreachable/ties, sparse overlap,
blank/weak abstention, normalized-mass support gate, partial data, and G2
baseline equivalence. Optical acceptance stays pending by policy.
"""
import hashlib
import json
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yinyang_oriented_fields as yf
import yinyang_multiscale_fields as mf
import yinyang_oriented_score as sc
import yinyang_local_normalization as ln
import yinyangfit_interactive as v1

P1 = yf.DEFAULT_PARAMS
INFLUENCE = int(P1.kernel_radius_px) + int(P1.v1_support_halfwidth_px)


def bars(w=140, x0=20, x1=22, y0=4, y1=16, extra=None):
    img = np.zeros((20, w))
    img[y0:y1, x0:x1] = 1.0
    if extra:
        img[y0:y1, extra[0]:extra[1]] = 1.0
    return img


def fields(img, **kw):
    return yf.oriented_fields_for_image(img, P1, **kw)


def energies(f):
    return sc.EnergyCache().energy("e", f)


def local_maps(f, tag="m"):
    return ln.LocalEnergyCache().maps(tag, f)


def on_union(lf, rf, lo, ro, EL=None, ER=None):
    origin, shape = sc.union_canvas(lf["image_shape"], lo,
                                    rf["image_shape"], [ro])
    out = {"g2": sc.score_step(lf, rf, lo, ro, origin, shape, EL, ER)["g2"]}
    out["O"] = ln.score_overlap_cosine(lf, rf, lo, ro, origin, shape)
    return out, origin, shape


def tiny_pair():
    """Independently derived 2-channel fixture with hand-set values."""
    def mk(c, d, u2, sup):
        return {"supported": np.asarray(sup, dtype=bool),
                "U2": np.asarray(u2, dtype=float),
                "distance": np.asarray(d, dtype=float),
                "confidence_notebook": np.asarray(c, dtype=float),
                "arc_strength": np.zeros_like(np.asarray(c, dtype=float)),
                "image_shape": (2, 3)}
    lf = mk([[[1.0, 2.0, 0.0], [0.0, 1.0, 1.0]],
             [[1.0, 1.0, 1.0], [2.0, 0.0, 1.0]]],
            [[[1.0, 1.0, 1.0], [1.0, 1.0, 1.0]],
             [[2.0, 2.0, 2.0], [2.0, 2.0, 2.0]]],
            [[[2.0, 2.0, 2.0], [2.0, 2.0, 2.0]],
             [[2.0, 2.0, 2.0], [2.0, 2.0, 2.0]]],
            [[[True] * 3, [True] * 3], [[True] * 3, [True] * 3]])
    rf = mk([[[2.0, 1.0, 1.0], [1.0, 0.0, 2.0]],
             [[0.0, 2.0, 1.0], [1.0, 1.0, 0.0]]],
            [[[1.5, 1.5, 1.5], [1.5, 1.5, 1.5]],
             [[0.5, 0.5, 0.5], [0.5, 0.5, 0.5]]],
            [[[3.0, 3.0, 3.0], [3.0, 3.0, 3.0]],
             [[3.0, 3.0, 3.0], [3.0, 3.0, 3.0]]],
            [[[True] * 3, [True] * 3], [[True] * 3, [True] * 3]])
    return lf, rf


def spearman(xs, ys):
    rx = np.argsort(np.argsort(xs)).astype(float)
    ry = np.argsort(np.argsort(ys)).astype(float)
    rx -= rx.mean()
    ry -= ry.mean()
    return float(np.dot(rx, ry) / math.sqrt(np.dot(rx, rx) * np.dot(ry, ry)))


class ContactTest(unittest.TestCase):
    def test_touching_step_eligible_finite_nontrivial(self):
        a, b = fields(bars()), fields(bars())
        EA, EB = energies(a), energies(b)
        LA, LB = local_maps(a, "a"), local_maps(b, "b")
        origin, shape = sc.union_canvas(a["image_shape"], (0, 0),
                                        b["image_shape"], [(2, 0)])
        go = ln.score_overlap_cosine(a, b, (0, 0), (2, 0), origin, shape)
        gl = ln.score_local_energy(a, b, (0, 0), (2, 0), origin, shape,
                                   LA, LB)
        for r in (go, gl):
            self.assertFalse(r["abstain"])
            self.assertTrue(math.isfinite(r["g"]) and r["g"] > 0.0)
            self.assertLess(r["g"], ln.G2_BOUND)
            self.assertLess(r["max_term_cosine"], 1.0)
            self.assertGreater(r["both_supported_pairpx"], 0)


class DistanceDiscriminationTest(unittest.TestCase):
    def test_parallel_bars_fall_with_distance(self):
        a, b = fields(bars()), fields(bars())
        EA, EB = energies(a), energies(b)
        LA, LB = local_maps(a, "la"), local_maps(b, "lb")
        steps = list(range(2, 13))
        origin, shape = sc.union_canvas(a["image_shape"], (0, 0),
                                        b["image_shape"],
                                        [(s, 0) for s in steps])
        g2, go, gl = [], [], []
        for s in steps:
            g2.append(sc.score_step(a, b, (0, 0), (s, 0), origin, shape,
                                    EA, EB)["g2"])
            go.append(ln.score_overlap_cosine(a, b, (0, 0), (s, 0),
                                              origin, shape)["g"])
            gl.append(ln.score_local_energy(a, b, (0, 0), (s, 0), origin,
                                            shape, LA, LB)["g"])
        for curve in (g2, go, gl):
            self.assertLessEqual(spearman(steps, curve), -0.9)


class GeometryCoverageTest(unittest.TestCase):
    def test_multiplicity_counters_diagonals_finite(self):
        dbl = fields(bars(extra=(30, 32)))
        ring = np.zeros((20, 140))
        ring[4:16, 20:32] = 1.0
        ring[8:12, 23:29] = 0.0
        cnt = fields(ring)
        diag = np.zeros((20, 140))
        for i in range(12):
            diag[4 + i, 20 + i] = 1.0
        dgl = fields(diag)
        b = fields(bars())
        EB = energies(b)
        LB = local_maps(b, "cov-b")
        for f, tag in ((dbl, "dbl"), (cnt, "cnt"), (dgl, "dgl")):
            E = energies(f)
            L = local_maps(f, tag)
            origin, shape = sc.union_canvas(f["image_shape"], (0, 0),
                                            b["image_shape"], [(6, 0)])
            go = ln.score_overlap_cosine(f, b, (0, 0), (6, 0), origin, shape)
            gl = ln.score_local_energy(f, b, (0, 0), (6, 0), origin, shape,
                                       L, LB)
            for r in (go, gl):
                self.assertFalse(r["abstain"], tag)
                self.assertTrue(math.isfinite(r["g"]) and r["g"] > 0.0, tag)

    def test_gray_quantized_levels_finite(self):
        img = np.zeros((20, 140))
        for k in range(8):
            img[4:16, 20 + k * 2:21 + k * 2] = k / 7.0
        f = fields(img)
        E = energies(f)
        L = local_maps(f, "gray")
        origin, shape = sc.union_canvas(f["image_shape"], (0, 0),
                                        f["image_shape"], [(6, 0)])
        go = ln.score_overlap_cosine(f, f, (0, 0), (6, 0), origin, shape)
        self.assertFalse(go["abstain"])
        self.assertLessEqual(go["g"], ln.G2_BOUND)


class FarStemInvarianceTest(unittest.TestCase):
    def test_strict_noncontributing_addition(self):
        pair = bars()
        trio = bars(extra=(110, 112))  # beyond 2x influence of any overlap
        other = bars()
        fa, ft, fb = fields(pair), fields(trio), fields(other)
        EA, ET, EB = energies(fa), energies(ft), energies(fb)
        LA, LT, LB = (local_maps(fa, "fa"), local_maps(ft, "ft"),
                      local_maps(fb, "fb"))
        o2, sh2 = sc.union_canvas(fa["image_shape"], (0, 0),
                                  fb["image_shape"], [(6, 0)])
        o3, sh3 = sc.union_canvas(ft["image_shape"], (0, 0),
                                  fb["image_shape"], [(6, 0)])
        g2p = sc.score_step(fa, fb, (0, 0), (6, 0), o2, sh2, EA, EB)["g2"]
        g2t = sc.score_step(ft, fb, (0, 0), (6, 0), o3, sh3, ET, EB)["g2"]
        # Baseline defect: energy doubling dilutes by exactly 1/sqrt(2).
        self.assertAlmostEqual(g2t / g2p, 1.0 / math.sqrt(2.0), places=9)
        gop = ln.score_overlap_cosine(fa, fb, (0, 0), (6, 0), o2, sh2)
        got = ln.score_overlap_cosine(ft, fb, (0, 0), (6, 0), o3, sh3)
        glp = ln.score_local_energy(fa, fb, (0, 0), (6, 0), o2, sh2, LA, LB)
        glt = ln.score_local_energy(ft, fb, (0, 0), (6, 0), o3, sh3, LT, LB)
        self.assertEqual(gop["both_supported_pairpx"],
                         got["both_supported_pairpx"])
        self.assertLess(abs(got["g"] - gop["g"]) / gop["g"], 1e-9)
        self.assertLess(abs(glt["g"] - glp["g"]) / glp["g"], 1e-2)
        for cand, base in ((got["g"], g2t / g2p), (glt["g"], g2t / g2p)):
            self.assertGreater(cand / (gop["g"] if cand == got["g"]
                                       else glp["g"]), base)

    def test_interacting_stroke_moves_score(self):
        pair = bars()
        trio = bars()
        trio[4:16, 30:32] = 1.0  # inside field-influence range: interacts
        other = bars()
        fa, ft, fb = fields(pair), fields(trio), fields(other)
        LA, LT, LB = (local_maps(fa, "ia"), local_maps(ft, "it"),
                      local_maps(fb, "ib"))
        o, sh = sc.union_canvas(fa["image_shape"], (0, 0),
                                fb["image_shape"], [(6, 0)])
        gop = ln.score_overlap_cosine(fa, fb, (0, 0), (6, 0), o, sh)["g"]
        got = ln.score_overlap_cosine(ft, fb, (0, 0), (6, 0), o, sh)["g"]
        glp = ln.score_local_energy(fa, fb, (0, 0), (6, 0), o, sh,
                                    LA, LB)["g"]
        glt = ln.score_local_energy(ft, fb, (0, 0), (6, 0), o, sh,
                                    LT, LB)["g"]
        self.assertGreater(abs(got - gop) / gop, 0.10)
        self.assertGreater(abs(glt - glp) / glp, 0.10)


class RepresentationInvarianceTest(unittest.TestCase):
    def test_zero_padding_extent(self):
        a = bars()
        wide = np.zeros((20, 200))
        wide[:, 30:170] = a
        fa, fw = fields(a), fields(wide)
        shift = 30  # ink offset between the two lattices
        EA, EW = energies(fa), energies(fw)
        LA, LW = local_maps(fa, "za"), local_maps(fw, "zw")
        oa, sha = sc.union_canvas(fa["image_shape"], (0, 0),
                                  fa["image_shape"], [(6, 0)])
        ow, shw = sc.union_canvas(fw["image_shape"], (shift, 0),
                                  fw["image_shape"], [(shift + 6, 0)])
        for kind in ("g2", "O", "L"):
            if kind == "g2":
                va = sc.score_step(fa, fa, (0, 0), (6, 0), oa, sha,
                                   EA, EA)["g2"]
                vw = sc.score_step(fw, fw, (shift, 0), (shift + 6, 0), ow,
                                   shw, EW, EW)["g2"]
            elif kind == "O":
                va = ln.score_overlap_cosine(fa, fa, (0, 0), (6, 0), oa,
                                             sha)["g"]
                vw = ln.score_overlap_cosine(fw, fw, (shift, 0),
                                             (shift + 6, 0), ow, shw)["g"]
            else:
                va = ln.score_local_energy(fa, fa, (0, 0), (6, 0), oa, sha,
                                           LA, LA)["g"]
                vw = ln.score_local_energy(fw, fw, (shift, 0),
                                            (shift + 6, 0), ow, shw,
                                            LW, LW)["g"]
            self.assertLess(abs(vw - va) / va, 1e-9, kind)

    def test_score_level_contrast_cancels_on_common_support(self):
        # Score-normalization claim only: scaling strengths with the support
        # mask held fixed cancels exactly. Image-level scaling moves the
        # U2 > eps shell instead (pinned below as recorded mask dropout).
        a = fields(bars())
        b = fields(bars())
        LA, LB = local_maps(a, "ca"), local_maps(b, "cb")
        o, sh = sc.union_canvas(a["image_shape"], (0, 0),
                                b["image_shape"], [(6, 0)])
        base_o = ln.score_overlap_cosine(a, b, (0, 0), (6, 0), o, sh)
        base_l = ln.score_local_energy(a, b, (0, 0), (6, 0), o, sh, LA, LB)
        for alpha in (0.5, 2.0):
            la = dict(a, confidence_notebook=a["confidence_notebook"] * alpha)
            LLa = ln.LocalEnergyCache().maps("cc%d" % alpha, la)
            so = ln.score_overlap_cosine(la, b, (0, 0), (6, 0), o, sh)
            sl = ln.score_local_energy(la, b, (0, 0), (6, 0), o, sh,
                                        LLa, LB)
            self.assertEqual(base_o["both_supported_pairpx"],
                             so["both_supported_pairpx"])
            self.assertLess(abs(so["g"] - base_o["g"]) / base_o["g"], 1e-12)
            self.assertLess(abs(sl["g"] - base_l["g"]) / base_l["g"], 1e-12)

    def test_image_contrast_mask_dropout_recorded(self):
        a = fields(bars())
        dim = fields(bars() * 0.5)
        b = fields(bars())
        o, sh = sc.union_canvas(a["image_shape"], (0, 0),
                                b["image_shape"], [(6, 0)])
        r_full = ln.score_overlap_cosine(a, b, (0, 0), (6, 0), o, sh)
        r_dim = ln.score_overlap_cosine(dim, b, (0, 0), (6, 0), o, sh)
        # The eps shell moves under image scaling: the record must expose
        # the changed support rather than claim common-support invariance.
        self.assertNotEqual(r_full["both_supported_pairpx"],
                            r_dim["both_supported_pairpx"])
        self.assertFalse(r_dim["abstain"])

    def test_left_right_symmetry(self):
        fa, fb = fields(bars()), fields(bars(extra=(34, 36)))
        LA, LB = local_maps(fa, "sa"), local_maps(fb, "sb")
        o, sh = sc.union_canvas(fa["image_shape"], (0, 0),
                                fb["image_shape"], [(6, 0)])
        fwd_o = ln.score_overlap_cosine(fa, fb, (0, 0), (6, 0), o, sh)["g"]
        rev_o = ln.score_overlap_cosine(fb, fa, (6, 0), (0, 0), o, sh)["g"]
        self.assertLess(abs(fwd_o - rev_o) / fwd_o, 1e-12)
        fwd_l = ln.score_local_energy(fa, fb, (0, 0), (6, 0), o, sh,
                                      LA, LB)["g"]
        rev_l = ln.score_local_energy(fb, fa, (6, 0), (0, 0), o, sh,
                                      LB, LA)["g"]
        self.assertLess(abs(fwd_l - rev_l) / fwd_l, 1e-12)


class DomainAndTargetTest(unittest.TestCase):
    def test_forward_domain_shared_steps_stable(self):
        a, b = fields(bars()), fields(bars())
        LA, LB = local_maps(a, "da"), local_maps(b, "db")
        narrow = [4, 5, 6]
        wide = list(range(1, 12))
        on, shn = sc.union_canvas(a["image_shape"], (0, 0),
                                  b["image_shape"], [(s, 0) for s in narrow])
        ow, shw = sc.union_canvas(a["image_shape"], (0, 0),
                                  b["image_shape"], [(s, 0) for s in wide])
        self.assertGreater(narrow[0], 0)
        for s in narrow:
            for fn in (ln.score_overlap_cosine,
                       lambda x, y, lo, ro, o, sh: ln.score_local_energy(
                           x, y, lo, ro, o, sh, LA, LB)):
                vn = fn(a, b, (0, 0), (s, 0), on, shn)["g"]
                vw = fn(a, b, (0, 0), (s, 0), ow, shw)["g"]
                self.assertLess(abs(vw - vn) / vn, 1e-12)

    def test_target_zero_unreachable_ties(self):
        devs = [abs(g - 0.0) for g in (7.9, 1.6, 4.2)]
        picks, mstar = sc.tie_set(devs)
        self.assertEqual(picks, [1])
        far = [abs(g - 1e6) for g in (7.9, 1.6, 4.2)]
        picks_f, _ = sc.tie_set(far)
        self.assertEqual(picks_f, [0])  # closest to unreachable target
        tied = [3.0, 3.0, 5.0]
        picks_t, _ = sc.tie_set(tied)
        self.assertEqual(picks_t, [0, 1])

    def test_partial_data_abstention_excluded(self):
        lf, rf = tiny_pair()
        lf = dict(lf, supported=np.zeros_like(lf["supported"], dtype=bool))
        origin, shape = sc.union_canvas(lf["image_shape"], (0, 0),
                                        rf["image_shape"], [(0, 0)])
        go = ln.score_overlap_cosine(lf, rf, (0, 0), (0, 0), origin, shape)
        self.assertTrue(go["abstain"])
        self.assertEqual(go["g"], 0.0)
        eligible = [s for s, r in (("s0", go),) if not r["abstain"]]
        self.assertEqual(eligible, [])


class SparseAndBlankTest(unittest.TestCase):
    def test_sparse_overlap_saturates_with_evidence(self):
        # Single-pixel both-supported overlap: cosine hits 1.0 by Cauchy.
        # The hazard must be EXPOSED (count + max term), never a silent win.
        lf, rf = tiny_pair()
        sup = np.zeros_like(lf["supported"], dtype=bool)
        sup[:, 0, 0] = True
        lf = dict(lf, supported=sup, U2=np.full_like(lf["U2"], 2.0),
                  distance=np.ones_like(lf["distance"]),
                  confidence_notebook=np.ones_like(
                      lf["confidence_notebook"]))
        rf = dict(rf, supported=sup, U2=np.full_like(rf["U2"], 3.0),
                  distance=np.ones_like(rf["distance"]),
                  confidence_notebook=2.0 * np.ones_like(
                      rf["confidence_notebook"]))
        origin, shape = sc.union_canvas(lf["image_shape"], (0, 0),
                                        rf["image_shape"], [(0, 0)])
        go = ln.score_overlap_cosine(lf, rf, (0, 0), (0, 0), origin, shape)
        self.assertFalse(go["abstain"])
        self.assertAlmostEqual(go["max_term_cosine"], 1.0, places=12)
        self.assertLessEqual(go["both_supported_pairpx"], 256)
        self.assertGreater(go["eligible_terms"], 0)

    def test_blank_abstains(self):
        z = fields(np.zeros((20, 140)))
        EZ = energies(z)
        LZ = local_maps(z, "blank")
        origin, shape = sc.union_canvas(z["image_shape"], (0, 0),
                                        z["image_shape"], [(0, 0)])
        go = ln.score_overlap_cosine(z, z, (0, 0), (0, 0), origin, shape)
        gl = ln.score_local_energy(z, z, (0, 0), (0, 0), origin, shape,
                                   LZ, LZ)
        self.assertTrue(go["abstain"] and gl["abstain"])
        self.assertEqual(go["g"], 0.0)
        self.assertEqual(gl["g"], 0.0)

    def test_weak_field_below_floor_abstains(self):
        w = fields(bars() * 1e-13)
        self.assertEqual(int(w["supported"].sum()), 0)
        EW = energies(w)
        LW = local_maps(w, "weak")
        origin, shape = sc.union_canvas(w["image_shape"], (0, 0),
                                        w["image_shape"], [(0, 0)])
        go = ln.score_overlap_cosine(w, w, (0, 0), (0, 0), origin, shape)
        self.assertTrue(go["abstain"])

    def test_valid_zero_agreement_stays_eligible(self):
        # Disjoint ink placement with healthy energies: every facing-pair
        # product is zero, so gl == 0.0 with eligible terms. This is valid
        # zero agreement (eligible), not missing evidence (abstain).
        lf, rf = tiny_pair()
        n = lf["confidence_notebook"].shape
        idx = np.arange(int(np.prod(n[1:]))).reshape(n[1:])
        lc = np.where(idx % 2 == 0, 1.0, 0.0)
        rc = np.where(idx % 2 == 1, 1.0, 0.0)
        lf = dict(lf, confidence_notebook=np.broadcast_to(
            lc, n).copy())
        rf = dict(rf, confidence_notebook=np.broadcast_to(
            rc, n).copy())
        EL = ln.LocalEnergyCache().maps("zl", lf)
        ER = ln.LocalEnergyCache().maps("zr", rf)
        origin, shape = sc.union_canvas(lf["image_shape"], (0, 0),
                                        rf["image_shape"], [(0, 0)])
        gl = ln.score_local_energy(lf, rf, (0, 0), (0, 0), origin, shape,
                                   EL, ER)
        self.assertFalse(gl["abstain"])
        self.assertEqual(gl["g"], 0.0)
        self.assertGreater(gl["eligible_terms"], 0)
        self.assertGreater(gl["both_supported_pairpx"], 0)

    def test_underflow_to_zero_evidence_abstains(self):
        # c^2 vanishes in f64, so every support pixel is guard-skipped:
        # no eligible local evidence, abstain with g == 0.0.
        tiny = 1e-200
        lf, rf = tiny_pair()
        lf = dict(lf, confidence_notebook=np.full_like(
            lf["confidence_notebook"], tiny))
        rf = dict(rf, confidence_notebook=np.full_like(
            rf["confidence_notebook"], tiny))
        EL = ln.LocalEnergyCache().maps("ul", lf)
        ER = ln.LocalEnergyCache().maps("ur", rf)
        origin, shape = sc.union_canvas(lf["image_shape"], (0, 0),
                                        rf["image_shape"], [(0, 0)])
        gl = ln.score_local_energy(lf, rf, (0, 0), (0, 0), origin, shape,
                                   EL, ER)
        self.assertTrue(gl["abstain"])
        self.assertEqual(gl["g"], 0.0)


class SupportGateTest(unittest.TestCase):
    def test_weak_share_is_normalized_mass(self):
        lf, rf = tiny_pair()
        origin, shape = sc.union_canvas(lf["image_shape"], (0, 0),
                                        rf["image_shape"], [(0, 0)])
        go = ln.score_overlap_cosine(lf, rf, (0, 0), (0, 0), origin, shape)
        self.assertGreaterEqual(go["weak_normalized_share"], 0.0)
        self.assertLessEqual(go["weak_normalized_share"], 1.0)
        # Independent recompute of Class O on the same fixture.
        F = sc.facing_matrix(2)
        expect, weak = 0.0, 0.0
        for a in range(2):
            for b in range(2):
                w = float(F[a, b])
                if w == 0.0:
                    continue
                cL = lf["confidence_notebook"][a]
                cR = rf["confidence_notebook"][b]
                kval = np.exp(-((lf["distance"][a] - rf["distance"][b]) ** 2)
                              / (2.0 * 0.5 * 0.5))
                n = float(np.sum(cL * cR * kval))
                den = math.sqrt(float(np.sum(cL ** 2))
                                * float(np.sum(cR ** 2)))
                t = n / den
                expect += w * t
                floormask = ((lf["U2"][a] < sc.FLOOR_U2)
                             | (rf["U2"][b] < sc.FLOOR_U2))
                weak += w * float(np.sum(cL[floormask] * cR[floormask]
                                         * kval[floormask])) / den
        self.assertAlmostEqual(go["g"], expect, places=12)
        self.assertAlmostEqual(go["weak_normalized_share"], weak / expect,
                               places=12)

    def test_contrast_quantization_reports_mask(self):
        full = np.zeros((20, 140))
        full[4:16, 20:40] = 0.1
        quant = np.round(full * 7.0) / 7.0  # exact p/7 coverage input
        ff, fq = fields(full), fields(quant)
        Lf, Lq = local_maps(ff, "qf"), local_maps(fq, "qq")
        of, shf = sc.union_canvas(ff["image_shape"], (0, 0),
                                  ff["image_shape"], [(6, 0)])
        oq, shq = sc.union_canvas(fq["image_shape"], (0, 0),
                                  fq["image_shape"], [(6, 0)])
        rf_ = ln.score_overlap_cosine(ff, ff, (0, 0), (6, 0), of, shf)
        rq = ln.score_overlap_cosine(fq, fq, (0, 0), (6, 0), oq, shq)
        self.assertIsInstance(rf_["both_supported_pairpx"], int)
        self.assertIsInstance(rq["both_supported_pairpx"], int)
        self.assertFalse(rq["abstain"])


class BaselineEquivalenceTest(unittest.TestCase):
    def test_g2_recompute_deterministic_bounded(self):
        a, b = fields(bars()), fields(bars())
        EA, EB = energies(a), energies(b)
        origin, shape = sc.union_canvas(a["image_shape"], (0, 0),
                                        b["image_shape"], [(6, 0)])
        r1 = sc.score_step(a, b, (0, 0), (6, 0), origin, shape, EA, EB)
        r2 = sc.score_step(a, b, (0, 0), (6, 0), origin, shape, EA, EB)
        self.assertEqual(r1["g2"], r2["g2"])
        self.assertGreaterEqual(r1["g2"], 0.0)
        self.assertLessEqual(r1["g2"], ln.G2_BOUND)


class PerChannelVsAllChannelTest(unittest.TestCase):
    def test_invalid_mode_raises(self):
        lf, rf = tiny_pair()
        origin, shape = sc.union_canvas(lf["image_shape"], (0, 0),
                                        rf["image_shape"], [(0, 0)])
        with self.assertRaises(ValueError):
            ln.score_overlap_cosine(lf, rf, (0, 0), (0, 0), origin, shape,
                                    mode="global")

    def test_uniform_fields_flat_both_modes(self):
        def uniform(n_ch=2):
            return {"supported": np.ones((n_ch, 2, 6), dtype=bool),
                    "U2": np.full((n_ch, 2, 6), 2.0),
                    "distance": np.zeros((n_ch, 2, 6)),
                    "confidence_notebook": np.full((n_ch, 2, 6), 2.0),
                    "arc_strength": np.zeros((n_ch, 2, 6)),
                    "image_shape": (2, 6)}
        lf, rf = uniform(), uniform()
        origin, shape = sc.union_canvas(lf["image_shape"], (0, 0),
                                        rf["image_shape"], [(0, 0)])
        rp = ln.score_overlap_cosine(lf, rf, (0, 0), (0, 0), origin, shape,
                                     mode="per-channel")
        ra = ln.score_overlap_cosine(lf, rf, (0, 0), (0, 0), origin, shape,
                                     mode="all-channel")
        w_sum = float(np.sum(sc.facing_matrix(2)))
        self.assertAlmostEqual(rp["g"], w_sum, places=12)
        self.assertAlmostEqual(ra["g"], w_sum, places=12)

    def test_nonuniform_modes_differ_but_bounded(self):
        lf, rf = tiny_pair()
        origin, shape = sc.union_canvas(lf["image_shape"], (0, 0),
                                        rf["image_shape"], [(0, 0)])
        rp = ln.score_overlap_cosine(lf, rf, (0, 0), (0, 0), origin, shape,
                                     mode="per-channel")
        ra = ln.score_overlap_cosine(lf, rf, (0, 0), (0, 0), origin, shape,
                                     mode="all-channel")
        self.assertNotAlmostEqual(rp["g"], ra["g"], places=6)
        for r in (rp, ra):
            self.assertGreaterEqual(r["g"], 0.0)
            self.assertLessEqual(r["g"], ln.G2_BOUND)
        # Independent recompute of the all-channel scalar.
        F = sc.facing_matrix(2)
        n_tot = ql_tot = qr_tot = w_sum = 0.0
        for a in range(2):
            for b in range(2):
                w = float(F[a, b])
                if w == 0.0:
                    continue
                cL = lf["confidence_notebook"][a]
                cR = rf["confidence_notebook"][b]
                kval = np.exp(-((lf["distance"][a] - rf["distance"][b]) ** 2)
                              / 0.5)
                n_tot += w * float(np.sum(cL * cR * kval))
                ql_tot += w * float(np.sum(cL ** 2))
                qr_tot += w * float(np.sum(cR ** 2))
                w_sum += w
        expect = w_sum * n_tot / math.sqrt(ql_tot * qr_tot)
        self.assertAlmostEqual(ra["g"], expect, places=12)


class AreaBiasTest(unittest.TestCase):
    def test_overlap_cosine_area_invariant_pooled_area_biased(self):
        def uniform(width):
            return {"supported": np.ones((2, 2, width), dtype=bool),
                    "U2": np.full((2, 2, width), 2.0),
                    "distance": np.zeros((2, 2, width)),
                    "confidence_notebook": np.full((2, 2, width), 1.5),
                    "arc_strength": np.zeros((2, 2, width)),
                    "image_shape": (2, width)}
        small = uniform(6)
        large = uniform(12)
        outs = sc.union_canvas(small["image_shape"], (0, 0),
                               small["image_shape"], [(0, 0)])
        outl = sc.union_canvas(large["image_shape"], (0, 0),
                               large["image_shape"], [(0, 0)])
        gos = ln.score_overlap_cosine(small, small, (0, 0), (0, 0), *outs)["g"]
        gol = ln.score_overlap_cosine(large, large, (0, 0), (0, 0), *outl)["g"]
        self.assertAlmostEqual(gos, gol, places=12)
        pc = ln.PooledEnergyCache(ln.SOURCED_SIGMAS["tau"])
        ELs, ELl = pc.maps("as", small), pc.maps("al", large)
        gps = ln.score_pooled(small, small, (0, 0), (0, 0), *outs,
                              ELs, ELs, ln.SOURCED_SIGMAS["tau"])["g"]
        gpl = ln.score_pooled(large, large, (0, 0), (0, 0), *outl,
                              ELl, ELl, ln.SOURCED_SIGMAS["tau"])["g"]
        self.assertGreater(gpl / gps, 1.5)  # area bias, not invariance


class WeakTailsTest(unittest.TestCase):
    def test_weak_but_supported_eligible_with_full_weak_share(self):
        lf, rf = tiny_pair()
        for f in (lf, rf):
            f["U2"] = np.full_like(f["U2"], 2e-12)  # above eps, below floor
        origin, shape = sc.union_canvas(lf["image_shape"], (0, 0),
                                        rf["image_shape"], [(0, 0)])
        go = ln.score_overlap_cosine(lf, rf, (0, 0), (0, 0), origin, shape)
        self.assertFalse(go["abstain"])
        self.assertAlmostEqual(go["weak_normalized_share"], 1.0, places=12)

    def test_zero_strength_channel_contributes_nothing(self):
        lf, rf = tiny_pair()
        rf["confidence_notebook"] = np.zeros_like(rf["confidence_notebook"])
        origin, shape = sc.union_canvas(lf["image_shape"], (0, 0),
                                        rf["image_shape"], [(0, 0)])
        for fn in (ln.score_overlap_cosine,
                   lambda a, b, lo, ro, o, sh: ln.score_local_energy(
                       a, b, lo, ro, o, sh,
                       ln.LocalEnergyCache().maps("zl", a),
                       ln.LocalEnergyCache().maps("zr", b))):
            r = fn(lf, rf, (0, 0), (0, 0), origin, shape)
            self.assertTrue(r["abstain"])
            self.assertEqual(r["g"], 0.0)


class SupportDependenceTest(unittest.TestCase):
    def test_overlap_denominator_varies_across_steps(self):
        # Candidate-dependent support is reproduced, NOT declared resolved:
        # nested hand supports give strictly nested per-term energies.
        lf, rf = tiny_pair()
        sup_full = np.ones_like(lf["supported"], dtype=bool)
        sup_half = np.zeros_like(lf["supported"], dtype=bool)
        sup_half[:, :, :1] = True
        origin, shape = sc.union_canvas(lf["image_shape"], (0, 0),
                                        rf["image_shape"], [(0, 0)])
        qls = []
        for sup in (sup_full, sup_half):
            lf = dict(lf, supported=sup)
            lfr = dict(rf, supported=sup)
            chans = ln._per_pair_overlays(lf, lfr, (0, 0), (0, 0),
                                           origin, shape)
            terms = ln._overlap_terms(chans, ln.TAU_PX)
            qls.append(sum(t["ql"] for t in terms))
        self.assertGreater(qls[0], qls[1])
        self.assertGreater(qls[1], 0.0)

    def test_pooled_ebar_varies_across_steps(self):
        a, b = fields(bars()), fields(bars())
        pc = ln.PooledEnergyCache(ln.SOURCED_SIGMAS["tau"])
        ELa, ELb = pc.maps("ea", a), pc.maps("eb", b)
        steps = list(range(2, 13))
        origin, shape = sc.union_canvas(a["image_shape"], (0, 0),
                                        b["image_shape"],
                                        [(s, 0) for s in steps])
        ebars = [ln.score_pooled(a, b, (0, 0), (s, 0), origin, shape,
                                 ELa, ELb,
                                 ln.SOURCED_SIGMAS["tau"])["ELbar"]
                 for s in steps]
        self.assertGreater(max(ebars) - min(ebars), 0.0)

    def test_real_contact_eligible_finite(self):
        # Real-field contact keeps broad support overlap (unlike the
        # oracle's zero-spread synthetic contact, which must abstain).
        a, b = fields(bars()), fields(bars())
        LA, LB = local_maps(a, "rca"), local_maps(b, "rcb")
        pc = ln.PooledEnergyCache(ln.SOURCED_SIGMAS["tau"])
        ELa, ELb = pc.maps("rpa", a), pc.maps("rpb", b)
        origin, shape = sc.union_canvas(a["image_shape"], (0, 0),
                                        b["image_shape"], [(2, 0)])
        go = ln.score_overlap_cosine(a, b, (0, 0), (2, 0), origin, shape)
        gl = ln.score_local_energy(a, b, (0, 0), (2, 0), origin, shape,
                                   LA, LB)
        gp = ln.score_pooled(a, b, (0, 0), (2, 0), origin, shape,
                             ELa, ELb, ln.SOURCED_SIGMAS["tau"])
        for r in (go, gl, gp):
            self.assertFalse(r["abstain"])
            self.assertTrue(math.isfinite(r["g"]) and r["g"] > 0.0)


class CanvasWideningTest(unittest.TestCase):
    def test_wide_canvas_shared_steps_stable_all_classes(self):
        a, b = fields(bars()), fields(bars())
        LA, LB = local_maps(a, "wca"), local_maps(b, "wcb")
        pc = ln.PooledEnergyCache(ln.SOURCED_SIGMAS["tau"])
        ELa, ELb = pc.maps("wpa", a), pc.maps("wpb", b)
        narrow = [4, 5, 6]
        wide = list(range(1, 12))
        on, shn = sc.union_canvas(a["image_shape"], (0, 0),
                                  b["image_shape"], [(s, 0) for s in narrow])
        ow, shw = sc.union_canvas(a["image_shape"], (0, 0),
                                  b["image_shape"], [(s, 0) for s in wide])
        for s in narrow:
            fns = [lambda x, y, lo, ro, o, sh: ln.score_overlap_cosine(
                       x, y, lo, ro, o, sh),
                   lambda x, y, lo, ro, o, sh: ln.score_local_energy(
                       x, y, lo, ro, o, sh, LA, LB),
                   lambda x, y, lo, ro, o, sh: ln.score_pooled(
                       x, y, lo, ro, o, sh, ELa, ELb,
                       ln.SOURCED_SIGMAS["tau"])]
            for fn in fns:
                vn = fn(a, b, (0, 0), (s, 0), on, shn)["g"]
                vw = fn(a, b, (0, 0), (s, 0), ow, shw)["g"]
                self.assertLess(abs(vw - vn) / vn, 1e-12)


class VariableRqTest(unittest.TestCase):
    def test_local_radius_sweep_finite(self):
        a, b = fields(bars()), fields(bars())
        origin, shape = sc.union_canvas(a["image_shape"], (0, 0),
                                        b["image_shape"], [(6, 0)])
        for radius in (6, 12, 24):
            cache = ln.LocalEnergyCache(radius=radius)
            self.assertEqual(cache.radius, radius)
            LA, LB = cache.maps("va", a), cache.maps("vb", b)
            self.assertEqual(LA.shape, a["confidence_notebook"].shape)
            r = ln.score_local_energy(a, b, (0, 0), (6, 0), origin, shape,
                                      LA, LB)
            self.assertFalse(r["abstain"])
            self.assertTrue(math.isfinite(r["g"]) and r["g"] > 0.0)

    def test_exponent_sweep_finite(self):
        for q in (1.0, 2.0, 3.0):
            params = yf.OrientedFieldParams(radial_exponent_q=q)
            a = yf.oriented_fields_for_image(bars(), params)
            b = yf.oriented_fields_for_image(bars(), params)
            origin, shape = sc.union_canvas(a["image_shape"], (0, 0),
                                            b["image_shape"], [(6, 0)])
            LA = ln.LocalEnergyCache().maps("qa%d" % q, a)
            LB = ln.LocalEnergyCache().maps("qb%d" % q, b)
            go = ln.score_overlap_cosine(a, b, (0, 0), (6, 0), origin, shape)
            gl = ln.score_local_energy(a, b, (0, 0), (6, 0), origin, shape,
                                       LA, LB)
            for r in (go, gl):
                self.assertFalse(r["abstain"])
                self.assertTrue(math.isfinite(r["g"]))

    def test_support_frame_derived_from_params(self):
        self.assertEqual(yf.stage_pad(),
                         int(P1.v1_support_halfwidth_px)
                         + int(P1.kernel_radius_px))
        self.assertEqual(yf.stage_pad(), 18)
        # Multiscale frame: largest V1 halfwidth over the frozen H-SCALES
        # set plus kernel radius (NOT the single-scale 18px). The function
        # already includes the kernel radius: 12 + 12 = 24.
        self.assertEqual(mf.stage_pad_multiscale(), 24)


class SourceOriginTest(unittest.TestCase):
    def test_bearing_origins_score_like_zero_origins(self):
        a, b = fields(bars()), fields(bars())
        LA, LB = local_maps(a, "soa"), local_maps(b, "sob")
        pad = int(a["pad"])
        lo = sc.glyph_padded_origin({"left": 3.0, "top": -9.0}, pad)
        ro = sc.glyph_padded_origin({"left": 9.0, "top": -9.0}, pad)
        o, sh = sc.union_canvas(a["image_shape"], lo, b["image_shape"], [ro])
        o0, sh0 = sc.union_canvas(a["image_shape"], (0, 0),
                                  b["image_shape"], [(6, 0)])
        go = ln.score_overlap_cosine(a, b, lo, ro, o, sh)["g"]
        go0 = ln.score_overlap_cosine(a, b, (0, 0), (6, 0), o0, sh0)["g"]
        self.assertLess(abs(go - go0) / go0, 1e-12)
        gl = ln.score_local_energy(a, b, lo, ro, o, sh, LA, LB)["g"]
        gl0 = ln.score_local_energy(a, b, (0, 0), (6, 0), o0, sh0,
                                    LA, LB)["g"]
        self.assertLess(abs(gl - gl0) / gl0, 1e-12)


class ConfidenceSymmetryTest(unittest.TestCase):
    def test_identical_inputs_symmetric_masses(self):
        a = fields(bars())
        origin, shape = sc.union_canvas(a["image_shape"], (0, 0),
                                        a["image_shape"], [(6, 0)])
        c = ln.confidence_readout(a, a, (0, 0), (6, 0), origin, shape)
        # Exact-arithmetic identity; float summation order leaves ulp noise.
        self.assertLess(abs(c["mass_L"] - c["mass_R"]) / c["mass_L"], 1e-12)
        self.assertLess(abs(c["weak_mass_L"] - c["weak_mass_R"])
                        / max(1.0, c["weak_mass_L"]), 1e-12)
        self.assertAlmostEqual(c["support_share"],
                               c["both_supported_pairpx"] / c["domain_pairpx"],
                               places=15)
        self.assertGreater(c["mass_L"], 0.0)

    def test_domain_widening_shrinks_share_honestly(self):
        a, b = fields(bars()), fields(bars())
        narrow = [4, 5, 6]
        wide = list(range(1, 12))
        on, shn = sc.union_canvas(a["image_shape"], (0, 0),
                                  b["image_shape"], [(s, 0) for s in narrow])
        ow, shw = sc.union_canvas(a["image_shape"], (0, 0),
                                  b["image_shape"], [(s, 0) for s in wide])
        cn = ln.confidence_readout(a, b, (0, 0), (6, 0), on, shn)
        cw = ln.confidence_readout(a, b, (0, 0), (6, 0), ow, shw)
        self.assertEqual(cn["both_supported_pairpx"],
                         cw["both_supported_pairpx"])
        self.assertGreater(cn["support_share"], cw["support_share"])
        self.assertAlmostEqual(cn["mass_L"], cw["mass_L"], places=9)


class RealCaptureDomainTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repo = Path(__file__).resolve().parents[3]
        prov = json.loads((repo / "out/diagnostics/contextual-spacing"
                           / "yinyang-oriented-fields/implementation"
                           / "provenance.json").read_text())
        cap = prov["captures"]["roboto-16-mono"]
        path = repo / cap["path"]
        assert (hashlib.sha256(path.read_bytes()).hexdigest()
                == cap["sha256"]), "capture drift"
        cls.ds = v1.load_mono_capture(str(path))
        cls.cells = cls.ds["cells"]

    def test_um_domain_forward_and_tight(self):
        cells, l, r = self.cells, ord("u"), ord("m")
        ox = math.trunc(cells[l]["left"])
        xs = [ox + c for row in range(cells[l]["height"])
              for c in range(cells[l]["width"])
              if cells[l]["cover"][row * cells[l]["width"] + c] > 0.0]
        oxr = math.trunc(cells[r]["left"])
        xsr = [oxr + c for row in range(cells[r]["height"])
               for c in range(cells[r]["width"])
               if cells[r]["cover"][row * cells[r]["width"] + c] > 0.0]
        lo = max(math.floor(min(xs) - max(xsr)), 1)
        self.assertGreaterEqual(lo, 1)
        pad = int(yf.stage_pad())
        hi = (math.trunc(cells[l]["left"] - pad)
              + cells[l]["width"] + 2 * pad - 1
              - math.trunc(cells[r]["left"] - pad))
        self.assertGreater(hi, lo)
        # Excluded steps below lo are reversed-order or non-forward.
        for s in range(lo - 3, lo):
            if s < 1:
                continue
            self.assertLess(max(xsr) + s, min(xs))

    def test_um_contact_eligible_finite_bounded(self):
        ds = self.ds
        l, r = ord("u"), ord("m")
        cell = ds["cells"][l]
        img = np.asarray(cell["cover"],
                         dtype=np.float64).reshape(cell["height"],
                                                   cell["width"])
        cellr = ds["cells"][r]
        imgr = np.asarray(cellr["cover"],
                           dtype=np.float64).reshape(cellr["height"],
                                                     cellr["width"])
        lf = yf.oriented_fields_for_image(img)
        rf = yf.oriented_fields_for_image(imgr)
        lo = (float(cell["left"]) - int(lf["pad"]),
              float(cell["top"]) - int(lf["pad"]))
        ro_base = (float(cellr["left"]) - int(rf["pad"]),
                   float(cellr["top"]) - int(rf["pad"]))
        steps = [s for s in range(1, 45)
                 if v1.contact_counts(ds["cells"][l],
                                      ds["cells"][r], s)[0] == 0]
        contact = [s for s in range(1, 45)
                   if v1.contact_counts(ds["cells"][l],
                                        ds["cells"][r], s)[1] > 0
                   and v1.contact_counts(ds["cells"][l],
                                         ds["cells"][r], s)[0] == 0]
        self.assertGreater(len(contact), 0)
        LA = ln.LocalEnergyCache().maps("du", lf)
        LB = ln.LocalEnergyCache().maps("dm", rf)
        origin, shape = sc.union_canvas(
            lf["image_shape"], lo, rf["image_shape"],
            [(ro_base[0] + s, ro_base[1]) for s in steps])
        for s in contact[:3]:
            ro = (ro_base[0] + s, ro_base[1])
            go = ln.score_overlap_cosine(lf, rf, lo, ro, origin, shape)
            gl = ln.score_local_energy(lf, rf, lo, ro, origin, shape,
                                       LA, LB)
            for rec in (go, gl):
                self.assertFalse(rec["abstain"], s)
                self.assertTrue(math.isfinite(rec["g"]) and rec["g"] > 0.0)
                self.assertLess(rec["max_term_cosine"], 1.0, s)


class MultiscaleLocalEnergyTest(unittest.TestCase):
    def test_multiscale_L_eligible_bounded_map_reduces(self):
        img = np.zeros((20, 140))
        img[4:16, 20:22] = 1.0
        banks, _ = mf.build_multiscale_v1_bank(mf.DEFAULT_PARAMS)
        kernels = yf.build_oriented_kernels(yf.DEFAULT_PARAMS)
        lf = mf.multiscale_glyph_fields(
            img, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
            v1_banks=banks, kernels=kernels)
        rf = mf.multiscale_glyph_fields(
            img, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
            v1_banks=banks, kernels=kernels)
        self.assertEqual(int(lf["pad"]), 24)
        LA = ln.LocalEnergyCache().maps("ml", lf)
        LB = ln.LocalEnergyCache().maps("mr", rf)
        origin, shape = sc.union_canvas(lf["image_shape"], (0, 0),
                                        rf["image_shape"], [(6, 0)])
        rec = ln.score_local_energy(lf, rf, (0, 0), (6, 0), origin, shape,
                                    LA, LB)
        self.assertFalse(rec["abstain"])
        self.assertTrue(math.isfinite(rec["g"]) and rec["g"] > 0.0)
        # Honest geometry-dependent bound: per-pixel term <= K <= 1, so
        # G_L <= sum_ab w_ab |both_ab| (loose by construction, verified).
        chans = ln._per_pair_overlays(lf, rf, (0, 0), (6, 0),
                                       origin, shape)
        F = sc.facing_matrix(len(chans))
        bound = sum(float(F[a, b]) * float(np.sum(chans[a][2] & chans[b][6]))
                    for a in range(len(chans)) for b in range(len(chans))
                    if float(F[a, b]) > 0.0)
        self.assertLessEqual(rec["g"], bound)
        # Map reduces exactly to the score.
        ELc = [ln._embed_float(LA[o], (0, 0), origin, shape)
               for o in range(len(chans))]
        ERc = [ln._embed_float(LB[o], (6, 0), origin, shape)
               for o in range(len(chans))]
        mmap = np.zeros(shape)
        for a in range(len(chans)):
            for b in range(len(chans)):
                w = float(F[a, b])
                if w == 0.0:
                    continue
                both = chans[a][2] & chans[b][6] & (ELc[a] > 0.0) & \
                    np.isfinite(ELc[a]) & (ERc[b] > 0.0) & \
                    np.isfinite(ERc[b])
                if not np.any(both):
                    continue
                kval = np.exp(-((chans[a][1][both] - chans[b][5][both])
                                ** 2) / (2.0 * ln.TAU_PX ** 2))
                mmap[both] += (w * chans[a][0][both] * chans[b][4][both]
                               * kval / np.sqrt(ELc[a][both] * ERc[b][both]))
        self.assertAlmostEqual(float(np.sum(mmap)), rec["g"], places=9)


class LocalEnergyCacheTest(unittest.TestCase):
    def test_radius_inherits_kernel_support(self):
        self.assertEqual(ln.LocalEnergyCache().radius, ln.RADIUS)
        self.assertEqual(ln.RADIUS, 12)

    def test_stable_and_recomputes_on_change(self):
        f = fields(bars())
        cache = ln.LocalEnergyCache()
        m1 = cache.maps("k", f)
        m2 = cache.maps("k", f)
        self.assertIs(m1, m2)
        g = fields(bars(extra=(40, 42)))
        m3 = cache.maps("k", g)
        self.assertIsNot(m1, m3)


if __name__ == "__main__":
    unittest.main()
