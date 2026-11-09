#!/usr/bin/env python3
"""Independent L reference for native/WASM parity (same component).

Computes Class-L expectations with the frozen Phase-1/2 pilot modules
(numpy side, independent of the Rust FFT path) over: a hand-derived tiny
fixture, synthetic bars (pair/trio, default + wide R/q), and real pairs on
two captures. Writes runtime/local_adapter.json. The Rust parity_local
driver compares against it; the port must reproduce it, not mirror itself.
"""

import hashlib
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parents[1]
RUNTIME = REPO / "out" / "diagnostics" / "contextual-spacing" \
    / "yinyang-normalization-repair" / "runtime"

import yinyang_oriented_fields as yf
import yinyang_multiscale_fields as mf
import yinyang_oriented_score as sc
import yinyang_local_normalization as ln
import yinyangfit_interactive as v1

S2_BANKS, _ = mf.build_multiscale_v1_bank(mf.DEFAULT_PARAMS)
S2_KERNELS = yf.build_oriented_kernels(yf.DEFAULT_PARAMS)
S2_KERNELS_Q3 = yf.build_oriented_kernels(
    yf.OrientedFieldParams(radial_exponent_q=3.0))


def ms_fields(img, kernels=None):
    return mf.multiscale_glyph_fields(
        img, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
        v1_banks=S2_BANKS,
        kernels=S2_KERNELS if kernels is None else kernels)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bars(w=100, x0=20, x1=22, y0=4, y1=16, extra=None):
    img = np.zeros((20, w))
    img[y0:y1, x0:x1] = 1.0
    if extra:
        img[y0:y1, extra[0]:extra[1]] = 1.0
    return img


def tiny_pair():
    def mk(c, d, u2, sup):
        return {"supported": np.asarray(sup, dtype=bool),
                "U2": np.asarray(u2, dtype=float),
                "distance": np.asarray(d, dtype=float),
                "confidence_notebook": np.asarray(c, dtype=float),
                "arc_strength": np.zeros_like(np.asarray(c, dtype=float)),
                "image_shape": (2, 3)}
    lf = mk([[[1.0, 2.0, 0.0], [0.0, 1.0, 1.0]],
             [[1.0, 1.0, 1.0], [2.0, 0.0, 1.0]]],
            [[[1.0] * 3] * 2, [[2.0] * 3] * 2],
            [[[2.0] * 3] * 2, [[2.0] * 3] * 2],
            [[[True] * 3, [True] * 3], [[True] * 3, [True] * 3]])
    rf = mk([[[2.0, 1.0, 1.0], [1.0, 0.0, 2.0]],
             [[0.0, 2.0, 1.0], [1.0, 1.0, 0.0]]],
            [[[1.5] * 3] * 2, [[0.5] * 3] * 2],
            [[[3.0] * 3] * 2, [[3.0] * 3] * 2],
            [[[True] * 3, [True] * 3], [[True] * 3, [True] * 3]])
    return lf, rf


def score_all(lf, rf, lo, ro, origin, shape, lec, radius, strength):
    EL = lec.maps(("a", strength, radius), lf, strength)
    ER = lec.maps(("b", strength, radius), rf, strength)
    # Temporarily override the pilot cache radius via a fresh cache.
    tmp = ln.LocalEnergyCache(radius=radius)
    EL = tmp.maps(("a", strength, radius), lf, strength)
    ER = tmp.maps(("b", strength, radius), rf, strength)
    rec = ln.score_local_energy(lf, rf, lo, ro, origin, shape, EL, ER,
                                ln.TAU_PX, strength)
    chans = ln._per_pair_overlays(lf, rf, lo, ro, origin, shape, strength)
    F = sc.facing_matrix(len(chans))
    bound = 0.0
    for a in range(len(chans)):
        for b in range(len(chans)):
            w = float(F[a, b])
            if w == 0.0:
                continue
            bound += w * float(np.sum(chans[a][2] & chans[b][6]))
    return rec, bound, EL, ER


def tie_choices(rows, metric):
    # TIE-v2 mirror of the engine's selection rule: deviations over valid
    # eligible (finite-gl, non-abstained) steps; tied set within
    # mstar + 1e-9 * max(1, mstar); lowest step wins; metric on fallback.
    elig = [(r["step"], r["gl"]) for r in rows
            if r.get("valid") and not r.get("abstain")
            and isinstance(r.get("gl"), float)
            and math.isfinite(r["gl"])]
    if not elig:
        base = {"seed_exact": ln.STUDY_SEED_P50 if hasattr(ln, "STUDY_SEED_P50")
                else 0.4697315871728616}
    else:
        gs = sorted(g for _, g in elig)
        by_dev = sorted((abs(g - 0.4697315871728616), g, s)
                        for s, g in elig)
        med = gs[len(gs) // 2]
        base = {"seed_exact": 0.4697315871728616,
                "mid_w": (by_dev[0][1] + by_dev[1][1]) / 2.0
                if len(by_dev) > 1 else by_dev[0][1],
                "mid_lo": (gs[0] + med) / 2.0,
                "mid_hi": (med + gs[-1]) / 2.0}
    targets = dict(base)
    targets.update({"seed_rounded": 0.47, "zero": 0.0, "high": 8.0,
                    "unreachable": (max(g for _, g in elig) + 5.0
                                    if elig else 5.0)})
    out = {}
    for tname, cstar in targets.items():
        if not elig:
            out[tname] = {"chosen": metric, "tied": [], "fallback": True}
            continue
        devs = sorted((abs(g - cstar), s) for s, g in elig)
        mstar = devs[0][0]
        tol = 1e-9 * max(1.0, mstar)
        tied = sorted(s for d, s in devs if d <= mstar + tol)
        out[tname] = {"chosen": tied[0], "tied": tied, "fallback": False}
    return out


def main():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    out = {"score_model": ln.MODEL_IDENTITY,
           "frozen": {"tau": ln.TAU_PX, "floor_u2": ln.FLOOR_U2,
                      "facing_sum": float(np.sum(sc.facing_matrix(16))),
                      "default_radius": ln.RADIUS,
                      "field_sha256": sha256_file(HERE / "yinyang_oriented_fields.py"),
                      "score_sha256": sha256_file(HERE / "yinyang_oriented_score.py"),
                      "pilot_sha256": sha256_file(HERE / "yinyang_local_normalization.py")}}

    # Tiny hand-derived fixture (whole-lattice pool at R=12: EL constant).
    lf, rf = tiny_pair()
    origin, shape = sc.union_canvas(lf["image_shape"], (0, 0),
                                    rf["image_shape"], [(0, 0)])
    lec = ln.LocalEnergyCache()
    rec, bound, EL, ER = score_all(lf, rf, (0, 0), (0, 0), origin, shape,
                                   lec, 12, "notebook")
    out["tiny"] = {"gl": rec["g"], "both": rec["both_supported_pairpx"],
                   "weak": rec["weak_normalized_share"],
                   "maxterm": rec["max_term_cosine"],
                   "abstain": rec["abstain"],
                   "skipped": 0, "bound": bound,
                   "el_uniform_0": bool((EL[0] == EL[0][0, 0]).all()),
                   "el_uniform_1": bool((EL[1] == EL[1][0, 0]).all()),
                   "el_sums": [float(EL[0][0, 0]), float(EL[1][0, 0]),
                               float(ER[0][0, 0]), float(ER[1][0, 0])]}

    # Synthetic bars: pair + far-stem trio, default + wide R/q.
    # Multiscale combined-T fields to match the Rust engine exactly.
    fa = ms_fields(bars())
    fb = ms_fields(bars())
    ft = ms_fields(bars(extra=(62, 64)))
    cfgs = {"R12": (12, 2.0, None), "R24": (24, 2.0, None),
            "R6": (6, 2.0, None), "q3": (12, 3.0, None)}
    built = {(12, 2.0): (fa, fb, ft)}
    out["bars"] = {}
    for tag, (radius, q, _) in cfgs.items():
        if q == 2.0:
            A, B, T = built[(12, 2.0)]
        else:
            # q3 config: multiscale fields with q=3 kernels AND q=3 ratio
            # exponents (the multiscale builder hardcodes the q=2 stage-1
            # exponents, so apply the q=3 notebook/manuscript powers here
            # to mirror the Rust engine, which uses q consistently).
            def q3fields(img):
                f = ms_fields(img, S2_KERNELS_Q3)
                sup = f["supported"]
                d = np.where(sup, f["distance"], 1.0)
                f["confidence_notebook"] = np.where(
                    sup, f["U1"] * d ** 2.0, 0.0)
                f["arc_strength"] = np.where(sup, f["U1"] * d ** 4.0, 0.0)
                return f
            A = q3fields(bars())
            B = q3fields(bars())
            T = q3fields(bars(extra=(62, 64)))
        for name, (L, Rr) in (("pair", (A, B)), ("trio", (T, B))):
            o, sh = sc.union_canvas(L["image_shape"], (0, 0),
                                    Rr["image_shape"], [(6, 0)])
            rec, bound, _, _ = score_all(L, Rr, (0, 0), (6, 0), o, sh,
                                         lec, radius, "notebook")
            recm, _, _, _ = score_all(L, Rr, (0, 0), (6, 0), o, sh,
                                      lec, radius, "manuscript")
            out["bars"].setdefault(tag, {})[name] = {
                "gl": rec["g"], "both": rec["both_supported_pairpx"],
                "weak": rec["weak_normalized_share"],
                "abstain": rec["abstain"], "bound": bound,
                "shortfall": None, "skipped": None,
                "gl_ms": recm["g"]}

    # Real pairs on two captures, metric +- 6 steps.
    prov = json.loads((REPO / "out/diagnostics/contextual-spacing"
                       / "yinyang-oriented-fields/implementation"
                       / "provenance.json").read_text())
    out["real"] = {}
    for name in ("roboto-16-mono", "literata-24-gray"):
        cap = prov["captures"][name]
        p = REPO / cap["path"]
        assert sha256_file(p) == cap["sha256"], "capture drift: %s" % name
        loader = (v1.load_mono_capture if cap["profile"] == "mono"
                  else v1.load_gray_capture)
        ds = loader(str(p))
        for pair in ("um", "og"):
            l, r = ord(pair[0]), ord(pair[1])
            cl, lo0 = ds["cells"][l]["cover"], None
            cell_l, cell_r = ds["cells"][l], ds["cells"][r]
            li = np.asarray(cell_l["cover"], dtype=float).reshape(
                cell_l["height"], cell_l["width"])
            ri = np.asarray(cell_r["cover"], dtype=float).reshape(
                cell_r["height"], cell_r["width"])
            fl = ms_fields(li)
            fr = ms_fields(ri)
            loB = (float(cell_l["left"]) - int(fl["pad"]),
                   float(cell_l["top"]) - int(fl["pad"]))
            roB = (float(cell_r["left"]) - int(fr["pad"]),
                   float(cell_r["top"]) - int(fr["pad"]))
            metric = v1.metric_step(ds, l, r)
            steps = [metric + d for d in range(-6, 7)]
            o, sh = sc.union_canvas(fl["image_shape"], loB,
                                    fr["image_shape"],
                                    [(roB[0] + s, roB[1]) for s in steps])
            rows = []
            rows6 = []
            for s in steps:
                ov, _, _ = v1.contact_counts(
                    ds["cells"][l], ds["cells"][r], s)
                if ov > 0:
                    rows.append({"step": s, "valid": False})
                    rows6.append({"step": s, "valid": False})
                    continue
                rec, bound, _, _ = score_all(
                    fl, fr, loB, (roB[0] + s, roB[1]), o, sh, lec, 12,
                    "notebook")
                rows.append({"step": s, "valid": True, "gl": rec["g"],
                             "both": rec["both_supported_pairpx"],
                             "weak": rec["weak_normalized_share"],
                             "abstain": rec["abstain"],
                             "bound": bound,
                             "shortfall": None})
                rec6, bound6, _, _ = score_all(
                    fl, fr, loB, (roB[0] + s, roB[1]), o, sh, lec, 6,
                    "notebook")
                rows6.append({"step": s, "valid": True,
                              "gl": rec6["g"],
                              "both": rec6["both_supported_pairpx"],
                              "weak": rec6["weak_normalized_share"],
                              "abstain": rec6["abstain"],
                              "bound": bound6,
                              "shortfall": None})
            out["real"].setdefault(name, {})[pair] = {
                "metric": metric, "steps": rows, "steps_R6": rows6,
                "choices": tie_choices(rows, metric),
                "choices_R6": tie_choices(rows6, metric)}
    with open(RUNTIME / "local_adapter.json", "w") as fh:
        json.dump(out, fh)
    print("tiny gl=%.12f bars=%d real=%d" % (
        out["tiny"]["gl"], len(out["bars"]),
        sum(len(v) for v in out["real"].values())))


if __name__ == "__main__":
    main()
