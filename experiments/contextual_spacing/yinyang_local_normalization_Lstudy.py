#!/usr/bin/env python3
"""Phase-2 Class-L fallback study on ACTUAL MULTISCALE fields.

Frozen 8 captures, full search-v2 forward domains (pad=24), true bearings,
both strengths (notebook primary, manuscript diagnostic). No pool tuning:
R sweeps and q sweeps are characterization, defaults stay R=12 / q=2.
Research only: JSON evidence, no live/engine/page changes.
"""

import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yinyang_oriented_fields as yf
import yinyang_multiscale_fields as mf
import yinyang_oriented_score as sc
import yinyang_local_normalization as ln
import yinyangfit_interactive as v1

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CORPUS = REPO / "out" / "diagnostics" / "contextual-spacing" \
    / "yinyang-normalization-repair" / "corpus"

DEV = ["um", "og"]
HELDOUT = ["AV", "To", "nn", "oo", "HH", "il"]
EXTRA = ["Th", "rt"]
EXTRA_CAPTURES = ["roboto-16-mono", "literata-16-mono"]
R_SWEEP = (6, 12, 24)
Q_SWEEP = (1.0, 3.0)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def glyph_cover(ds, codepoint):
    cell = ds["cells"][codepoint]
    w, h = cell["width"], cell["height"]
    return (np.asarray(cell["cover"], dtype=np.float64).reshape(h, w),
            (float(cell["left"]), float(cell["top"])))


def search_domain(cells, left, right, pad):
    spans = {}
    for tag, cp in (("l", left), ("r", right)):
        cell = cells[cp]
        ox = math.trunc(cell["left"])
        xs = [ox + col for row in range(cell["height"])
              for col in range(cell["width"])
              if cell["cover"][row * cell["width"] + col] > 0.0]
        if not xs:
            return None, "blank_glyph_no_ink"
        spans[tag] = (min(xs), max(xs))
    lo = max(math.floor(spans["l"][0] - spans["r"][1]), 1)
    lc, rc = cells[left], cells[right]
    lox = math.trunc(lc["left"] - pad)
    rox = math.trunc(rc["left"] - pad)
    loy = math.trunc(lc["top"] - pad)
    roy = math.trunc(rc["top"] - pad)
    if loy + lc["height"] + 2 * pad <= roy or \
            roy + rc["height"] + 2 * pad <= loy:
        return None, "row_bands_disjoint"
    hi = lox + lc["width"] + 2 * pad - 1 - rox
    if hi < 1:
        return None, "no_forward_step"
    return (lo, hi), None


def rss_now():
    try:
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except Exception:
        return 0


def score_L_variants(lf, rf, lo, ro, origin, shape, caches, radius,
                     strength):
    LL = caches["L"][radius].maps(("l", strength, radius), lf, strength)
    LR = caches["L"][radius].maps(("r", strength, radius), rf, strength)
    rec = ln.score_local_energy(lf, rf, lo, ro, origin, shape, LL, LR,
                                ln.TAU_PX, strength)
    chans = ln._per_pair_overlays(lf, rf, lo, ro, origin, shape, strength)
    F = sc.facing_matrix(len(chans))
    bound = 0.0
    for a in range(len(chans)):
        for b in range(len(chans)):
            w = float(F[a, b])
            if w == 0.0:
                continue
            both = chans[a][2] & chans[b][6]
            bound += w * float(np.sum(both))
    rec["honest_bound"] = bound
    return rec


def main():
    t_start = time.perf_counter()
    CORPUS.mkdir(parents=True, exist_ok=True)
    prov = json.loads((REPO / "out/diagnostics/contextual-spacing"
                       / "yinyang-oriented-fields/implementation"
                       / "provenance.json").read_text())
    datasets = {}
    for name, cap in prov["captures"].items():
        p = REPO / cap["path"]
        assert sha256_file(p) == cap["sha256"], "capture drift: %s" % name
        loader = (v1.load_mono_capture if cap["profile"] == "mono"
                  else v1.load_gray_capture)
        datasets[name] = (loader(str(p)), cap)
    report = {"model": ln.MODEL_IDENTITY + "+L-multiscale",
              "pad": int(mf.stage_pad_multiscale()),
              "default_radius": ln.RADIUS,
              "uncertainty": "uncertainty_not_certified",
              "cases": {}, "timings": {}}
    s2_banks, _ = mf.build_multiscale_v1_bank(mf.DEFAULT_PARAMS)
    s2_kernels = yf.build_oriented_kernels(yf.DEFAULT_PARAMS)
    en = {"E": sc.EnergyCache(),
          "L": {r: ln.LocalEnergyCache(radius=r) for r in R_SWEEP}}
    fields = {}

    def get_fields(name, cp, q=None):
        key = (name, cp, q)
        if key not in fields:
            ds, _ = datasets[name]
            img, _ = glyph_cover(ds, cp)
            if q is None:
                fields[key] = mf.multiscale_glyph_fields(
                    img, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
                    v1_banks=s2_banks, kernels=s2_kernels)
            else:
                params = yf.OrientedFieldParams(radial_exponent_q=q)
                fields[key] = yf.oriented_fields_for_image(img, params)
        return fields[key]

    pairs = list(DEV + HELDOUT)
    pairs_by_capture = {name: list(pairs) for name in datasets}
    for pair in EXTRA:
        for name in EXTRA_CAPTURES:
            pairs_by_capture[name].append(pair)
    # Pass 1: default (R=12, frozen q=2) multiscale curves, both strengths.
    for name in datasets:
        ds, _ = datasets[name]
        t0 = time.perf_counter()
        for pair in pairs_by_capture[name]:
            l, r = ord(pair[0]), ord(pair[1])
            case = {"metric": v1.metric_step(ds, l, r)}
            bounds, reason = search_domain(
                ds["cells"], l, r, int(mf.stage_pad_multiscale()))
            if bounds is None:
                case["domain"] = None
                case["domain_reason"] = reason
                report["cases"].setdefault(name, {})[pair] = case
                continue
            loD, hiD = bounds
            case["domain"] = [loD, hiD]
            lf, rf = get_fields(name, l), get_fields(name, r)
            _, lo0 = glyph_cover(ds, l)
            _, ro0 = glyph_cover(ds, r)
            lo = (float(lo0[0]) - int(lf["pad"]),
                  float(lo0[1]) - int(lf["pad"]))
            ro_base = (float(ro0[0]) - int(rf["pad"]),
                       float(ro0[1]) - int(rf["pad"]))
            steps = list(range(loD, hiD + 1))
            origin, shape = sc.union_canvas(
                lf["image_shape"], lo, rf["image_shape"],
                [(ro_base[0] + s, ro_base[1]) for s in steps])
            halo = list(range(hiD + 1, hiD + 4))
            oh, shh = sc.union_canvas(
                lf["image_shape"], lo, rf["image_shape"],
                [(ro_base[0] + s, ro_base[1]) for s in steps + halo])
            halo_ok = True
            for s in halo:
                ro = (ro_base[0] + s, ro_base[1])
                hh = ln.score_local_energy(
                    lf, rf, lo, ro, oh, shh,
                    en["L"][12].maps(("lh", "notebook", 12), lf),
                    en["L"][12].maps(("rh", "notebook", 12), rf))
                if not hh["abstain"]:
                    halo_ok = False
            case["halo_abstains"] = halo_ok
            recs = []
            for s in steps:
                ov, faces, corners = v1.contact_counts(
                    ds["cells"][l], ds["cells"][r], s)
                if ov > 0:
                    recs.append({"step": s, "valid": False,
                                 "reason": "occupied_cell_overlap",
                                 "faces": faces, "corners": corners})
                    continue
                ro = (ro_base[0] + s, ro_base[1])
                rec = {"step": s, "valid": True,
                       "faces": faces, "corners": corners}
                EL = en["E"].energy((name, l, "notebook"), lf, "notebook")
                ER = en["E"].energy((name, r, "notebook"), rf, "notebook")
                g2 = sc.score_step(lf, rf, lo, ro, origin, shape, EL, ER)
                rec["g2"] = g2["g2"]
                rec["g2_abstain"] = bool(
                    g2["raw"] == 0.0 and g2["both_supported_pairpx"] == 0)
                gl = score_L_variants(lf, rf, lo, ro, origin, shape, en,
                                      12, "notebook")
                for k in ("g", "both_supported_pairpx", "max_term_cosine",
                          "weak_normalized_share", "abstain",
                          "honest_bound"):
                    rec["nb_" + k] = gl[k]
                glm = score_L_variants(lf, rf, lo, ro, origin, shape, en,
                                       12, "manuscript")
                rec["ms_g"] = glm["g"]
                rec["ms_abstain"] = glm["abstain"]
                conf = ln.confidence_readout(lf, rf, lo, ro, origin, shape)
                rec["mass_L"] = conf["mass_L"]
                rec["mass_R"] = conf["mass_R"]
                rec["support_share"] = conf["support_share"]
                recs.append(rec)
            case["steps"] = recs
            report["cases"].setdefault(name, {})[pair] = case
        report["timings"][name] = {"seconds": time.perf_counter() - t0,
                                   "ru_maxrss": rss_now()}

    # Study seed from L dev band (notebook), then choices.
    dev_g = []
    for name in datasets:
        for pair in DEV:
            for rec in report["cases"][name][pair].get("steps", []):
                if rec.get("valid") and not rec.get("nb_abstain"):
                    dev_g.append(rec["nb_g"])
    dev_g.sort()
    n = len(dev_g)

    def pct(q):
        return dev_g[min(n - 1, int(q * n))]

    seed = {"p10": pct(0.10), "p50": pct(0.50), "p90": pct(0.90),
            "max": dev_g[-1]}
    report["study_seed"] = seed
    cstars = [0.0] + list(sc.CSTAR_GRID) + [seed["p50"]]
    for name in datasets:
        for pair in pairs_by_capture[name]:
            case = report["cases"][name][pair]
            if not case.get("domain"):
                continue
            valid = [r for r in case["steps"] if r.get("valid")]
            for variant, akey in (("nb_g", "nb_abstain"),
                                  ("g2", "g2_abstain")):
                vals = [r[variant] for r in valid
                        if not r.get(akey, False)]
                idx_all = [i for i, r in enumerate(valid)
                           if not r.get(akey, False)]
                ch = {}
                for cstar in cstars:
                    dev = [abs(g - cstar) for g in vals]
                    idx, mstar = sc.tie_set(dev)
                    steps = [valid[idx_all[i]]["step"] for i in idx]
                    ch[str(cstar)] = {
                        "steps": steps, "mstar": mstar,
                        "disconnected": any(
                            b - a > 1 for a, b in
                            zip(sorted(steps), sorted(steps)[1:]))}
                case[variant + "_choices"] = ch

    # R sweeps + q sweeps on dev pairs: choice-shift decomposition.
    report["sweeps"] = {}
    for name in datasets:
        ds, _ = datasets[name]
        for pair in DEV:
            case = report["cases"][name][pair]
            if not case.get("domain"):
                continue
            l, r = ord(pair[0]), ord(pair[1])
            _, lo0 = glyph_cover(ds, l)
            _, ro0 = glyph_cover(ds, r)
            entry = {}
            for cfg, getf in [("R%d" % rr, None) for rr in R_SWEEP] + \
                    [("q%.1f" % qq, qq) for qq in Q_SWEEP]:
                if cfg.startswith("R"):
                    rr = int(cfg[1:])
                    lf, rf = get_fields(name, l), get_fields(name, r)
                    lo = (float(lo0[0]) - int(lf["pad"]),
                          float(lo0[1]) - int(lf["pad"]))
                    ro_base = (float(ro0[0]) - int(rf["pad"]),
                               float(ro0[1]) - int(rf["pad"]))
                    steps = [rec["step"] for rec in case["steps"]
                             if rec.get("valid")]
                    origin, shape = sc.union_canvas(
                        lf["image_shape"], lo, rf["image_shape"],
                        [(ro_base[0] + s, ro_base[1]) for s in steps])
                    vals = []
                    for s in steps:
                        ro = (ro_base[0] + s, ro_base[1])
                        vals.append(score_L_variants(
                            lf, rf, lo, ro, origin, shape, en, rr,
                            "notebook")["g"])
                else:
                    lf, rf = get_fields(name, l, getf), get_fields(
                        name, r, getf)
                    lo = (float(lo0[0]) - int(lf["pad"]),
                          float(lo0[1]) - int(lf["pad"]))
                    ro_base = (float(ro0[0]) - int(rf["pad"]),
                               float(ro0[1]) - int(rf["pad"]))
                    steps = [rec["step"] for rec in case["steps"]
                             if rec.get("valid")]
                    origin, shape = sc.union_canvas(
                        lf["image_shape"], lo, rf["image_shape"],
                        [(ro_base[0] + s, ro_base[1]) for s in steps])
                    vals = []
                    for s in steps:
                        ro = (ro_base[0] + s, ro_base[1])
                        vals.append(score_L_variants(
                            lf, rf, lo, ro, origin, shape, en, 12,
                            "notebook")["g"])
                dev = [abs(g - seed["p50"]) for g in vals]
                idx, _ = sc.tie_set(dev)
                entry[cfg] = {"choice": steps[idx[0]], "n_tied": len(idx)}
            entry["window_shift_R12_R6"] = \
                entry["R6"]["choice"] != entry["R12"]["choice"]
            entry["window_shift_R12_R24"] = \
                entry["R24"]["choice"] != entry["R12"]["choice"]
            entry["field_shift_q2_q1"] = \
                entry["q1.0"]["choice"] != entry["R12"]["choice"]
            entry["field_shift_q2_q3"] = \
                entry["q3.0"]["choice"] != entry["R12"]["choice"]
            report["sweeps"].setdefault(name, {})[pair] = entry

    # Map-reduce exactness for L on dev steps + determinism + contrast.
    worst = 0.0
    name0 = "roboto-16-mono"
    ds0, _ = datasets[name0]
    lf0 = get_fields(name0, ord("u"))
    rf0 = get_fields(name0, ord("m"))
    _, lo0 = glyph_cover(ds0, ord("u"))
    _, ro0 = glyph_cover(ds0, ord("m"))
    lo = (float(lo0[0]) - int(lf0["pad"]),
          float(lo0[1]) - int(lf0["pad"]))
    ro_base = (float(ro0[0]) - int(rf0["pad"]),
               float(ro0[1]) - int(rf0["pad"]))
    LL = en["L"][12].maps(("m", "notebook", 12), lf0)
    LR = en["L"][12].maps(("m", "notebook", 12), rf0)
    o, sh = sc.union_canvas(lf0["image_shape"], lo, rf0["image_shape"],
                            [(ro_base[0] + 8, ro_base[1])])
    ro = (ro_base[0] + 8, ro_base[1])
    r1 = ln.score_local_energy(lf0, rf0, lo, ro, o, sh, LL, LR)
    r2 = ln.score_local_energy(lf0, rf0, lo, ro, o, sh, LL, LR)
    report["determinism_bitwise"] = (r1["g"] == r2["g"])
    chans = ln._per_pair_overlays(lf0, rf0, lo, ro, o, sh)
    ELc = [ln._embed_float(LL[a], lo, o, sh) for a in range(len(chans))]
    ERc = [ln._embed_float(LR[b], ro, o, sh) for b in range(len(chans))]
    F = sc.facing_matrix(len(chans))
    mmap = np.zeros(sh)
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
            kval = np.exp(-((chans[a][1][both] - chans[b][5][both]) ** 2)
                          / (2.0 * ln.TAU_PX ** 2))
            mmap[both] += (w * chans[a][0][both] * chans[b][4][both]
                           * kval / np.sqrt(ELc[a][both] * ERc[b][both]))
    report["map_reduce_reldiff"] = abs(float(np.sum(mmap)) - r1["g"]) / \
        max(1.0, abs(r1["g"]))
    # Score-level contrast (fixed support): scale strengths x2.
    lfS = dict(lf0, confidence_notebook=lf0["confidence_notebook"] * 2.0)
    LS = ln.LocalEnergyCache(radius=12).maps(("cs", "notebook", 12), lfS)
    rS = ln.score_local_energy(lfS, rf0, lo, ro, o, sh, LS, LR)
    report["score_contrast_reldiff"] = abs(rS["g"] - r1["g"]) / r1["g"]
    report["total_seconds"] = time.perf_counter() - t_start
    report["ru_maxrss"] = rss_now()
    with open(CORPUS / "run_Lmultiscale.json", "w") as fh:
        json.dump(report, fh)
    print("cases=%d seed=%s map_reduce=%.3g contrast=%.3g total_s=%.1f"
          % (sum(len(v) for v in report["cases"].values()),
             {k: round(vv, 4) for k, vv in seed.items()},
             report["map_reduce_reldiff"],
             report["score_contrast_reldiff"],
             report["total_seconds"]))


if __name__ == "__main__":
    main()
