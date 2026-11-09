#!/usr/bin/env python3
"""Phase-2 corpus study: Class O (primary) vs L (fallback), P diagnostic.

Frozen 8 captures (Roboto/Literata x 16/24 x Mono/Gray), full search-v2
domains, true bearings, both strengths. Research only: JSON evidence, no
live/engine/page changes. See owning design subsection Phase-2 predeclare.
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
import yinyang_oriented_score as sc
import yinyang_local_normalization as ln
import yinyangfit_interactive as v1

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CORPUS = REPO / "out" / "diagnostics" / "contextual-spacing" / \
    "yinyang-normalization-repair" / "corpus"

DEV = ["um", "og"]
HELDOUT = ["AV", "To", "nn", "oo", "HH", "il"]
EXTRA = ["Th", "rt"]
EXTRA_CAPTURES = {"Th": ["roboto-16-mono", "literata-16-mono"],
                  "rt": ["roboto-16-mono", "literata-16-mono"]}
STRENGTHS = ("notebook", "manuscript")


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def glyph_cover(ds, codepoint):
    cell = ds["cells"][codepoint]
    w, h = cell["width"], cell["height"]
    return (np.asarray(cell["cover"], dtype=np.float64).reshape(h, w),
            (float(cell["left"]), float(cell["top"])))


def search_domain(cells, left, right, pad):
    """Local exact implementation of the frozen search-v2 bound.

    lo = max(floor(L1 - R2), 1); hi = last padded-lattice x-overlap step.
    Blank sides and disjoint padded row bands yield no domain.
    """
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


def score_all_variants(lf, rf, lo, ro, origin, shape, caches, strength):
    EL = caches["E"].energy(("e", strength), lf, strength)
    ER = caches["E"].energy(("e", strength), rf, strength)
    LL = caches["L"].maps(("l", strength), lf, strength)
    LR = caches["L"].maps(("r", strength), rf, strength)
    PL = caches["P"].maps(("l", strength), lf, strength)
    PR = caches["P"].maps(("r", strength), rf, strength)
    rec = {}
    g2 = sc.score_step(lf, rf, lo, ro, origin, shape, EL, ER,
                       sc.TAU_PX, strength)
    rec["g2"] = g2["g2"]
    rec["g2_raw"] = g2["raw"]
    rec["g2_both"] = g2["both_supported_pairpx"]
    rec["g2_weak"] = g2["floor_share"]
    rec["g2_abstain"] = bool(g2["raw"] == 0.0
                             and g2["both_supported_pairpx"] == 0)
    go = ln.score_overlap_cosine(lf, rf, lo, ro, origin, shape,
                                 ln.TAU_PX, strength, mode="per-channel")
    goa = ln.score_overlap_cosine(lf, rf, lo, ro, origin, shape,
                                  ln.TAU_PX, strength, mode="all-channel")
    gl = ln.score_local_energy(lf, rf, lo, ro, origin, shape, LL, LR,
                               ln.TAU_PX, strength)
    gp = ln.score_pooled(lf, rf, lo, ro, origin, shape, PL, PR,
                         ln.SOURCED_SIGMAS["tau"], ln.TAU_PX, strength)
    for tag, r in (("go", go), ("goa", goa), ("gl", gl)):
        rec[tag] = r["g"]
        rec[tag + "_both"] = r["both_supported_pairpx"]
        rec[tag + "_maxterm"] = r["max_term_cosine"]
        rec[tag + "_weak"] = r["weak_normalized_share"]
        rec[tag + "_abstain"] = r["abstain"]
    rec["gp"] = gp["g"]
    rec["gp_elbar"] = gp["ELbar"]
    rec["gp_both"] = gp["both_supported_pairpx"]
    rec["gp_weak"] = gp["weak_normalized_share"]
    rec["gp_abstain"] = gp["abstain"]
    conf = ln.confidence_readout(lf, rf, lo, ro, origin, shape, strength)
    rec["mass_L"] = conf["mass_L"]
    rec["mass_R"] = conf["mass_R"]
    rec["support_share"] = conf["support_share"]
    return rec


def main():
    t_start = time.perf_counter()
    if CORPUS.exists():
        raise SystemExit("refusing to reuse output directory: %s" % CORPUS)
    (CORPUS / "arrays").mkdir(parents=True)
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
    report = {"model": ln.MODEL_IDENTITY, "cases": {},
              "uncertainty": "uncertainty_not_certified",
              "timings": {}, "flags": []}
    en_caches = {"E": sc.EnergyCache(), "L": ln.LocalEnergyCache(),
                 "P": ln.PooledEnergyCache(ln.SOURCED_SIGMAS["tau"])}
    field_cache = {}

    def get_fields(name, cp):
        key = (name, cp)
        if key not in field_cache:
            ds, _ = datasets[name]
            img, _ = glyph_cover(ds, cp)
            field_cache[key] = yf.oriented_fields_for_image(img)
        return field_cache[key]

    pairs_by_capture = {}
    for name in datasets:
        pairs_by_capture[name] = list(DEV + HELDOUT)
    for pair, names in EXTRA_CAPTURES.items():
        for name in names:
            pairs_by_capture[name].append(pair)

    # Pass 1: curves over full search-v2 domains.
    for name, pairs in pairs_by_capture.items():
        ds, cap = datasets[name]
        t0 = time.perf_counter()
        for pair in pairs:
            l, r = ord(pair[0]), ord(pair[1])
            case = {"metric": v1.metric_step(ds, l, r)}
            bounds, reason = search_domain(ds["cells"], l, r,
                                           int(yf.stage_pad()))
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
            # Halo: 3 steps past hi must carry no shared support.
            halo = list(range(hiD + 1, hiD + 4))
            oh, shh = sc.union_canvas(
                lf["image_shape"], lo, rf["image_shape"],
                [(ro_base[0] + s, ro_base[1]) for s in steps + halo])
            halo_ok = True
            for s in halo:
                ro = (ro_base[0] + s, ro_base[1])
                hh = ln.score_overlap_cosine(lf, rf, lo, ro, oh, shh)
                if hh["both_supported_pairpx"] != 0:
                    halo_ok = False
            case["halo_both_zero"] = halo_ok
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
                for strength in STRENGTHS:
                    sub = score_all_variants(lf, rf, lo, ro, origin,
                                             shape, en_caches, strength)
                    pre = "nb_" if strength == "notebook" else "ms_"
                    for k, vv in sub.items():
                        rec[pre + k] = vv
                recs.append(rec)
            case["steps"] = recs
            report["cases"].setdefault(name, {})[pair] = case
        report["timings"][name] = {"seconds": time.perf_counter() - t0,
                                   "ru_maxrss": rss_now()}

    # Study seed from O's own dev eligible-step band (notebook primary).
    dev_g = []
    for name in datasets:
        for pair in DEV:
            case = report["cases"][name][pair]
            for rec in case.get("steps", []):
                if rec.get("valid") and not rec.get("nb_go_abstain"):
                    dev_g.append(rec["nb_go"])
    dev_g.sort()
    n = len(dev_g)

    def pct(q):
        return dev_g[min(n - 1, int(q * n))]

    seed = {"p10": pct(0.10), "p50": pct(0.50), "p90": pct(0.90)}
    report["study_seed"] = seed
    cstars = [0.0] + list(sc.CSTAR_GRID) + [seed["p50"]]

    # Pass 2: choices, constructed ties, map-reduce checks on dev.
    for name, pairs in pairs_by_capture.items():
        for pair in pairs:
            case = report["cases"][name][pair]
            if not case.get("domain"):
                continue
            valid = [r for r in case["steps"] if r.get("valid")]
            for variant in ("nb_go", "nb_gl", "nb_gp", "nb_g2"):
                vals = [r[variant] for r in valid
                        if not r.get(variant + "_abstain", False)]
                idx_all = [i for i, r in enumerate(valid)
                           if not r.get(variant + "_abstain", False)]
                ch = {}
                for cstar in cstars:
                    devs = [abs(g - cstar) for g in vals]
                    idx, mstar = sc.tie_set(devs)
                    steps = [valid[idx_all[i]]["step"] for i in idx]
                    ch[str(cstar)] = {"steps": steps, "mstar": mstar,
                                      "disconnected": any(
                                          b - a > 1 for a, b in
                                          zip(sorted(steps), sorted(steps)[1:]))}
                # Constructed tie: C* midway between adjacent valid values.
                if len(vals) >= 2:
                    order = sorted(range(len(vals)), key=lambda i: vals[i])
                    mid = (vals[order[0]] + vals[order[1]]) / 2.0
                    devs = [abs(g - mid) for g in vals]
                    idx, _ = sc.tie_set(devs)
                    steps = [valid[idx_all[i]]["step"] for i in idx]
                    ch["constructed_tie"] = {
                        "steps": steps,
                        "disconnected": any(
                            b - a > 1 for a, b in
                            zip(sorted(steps), sorted(steps)[1:]))}
                case[variant + "_choices"] = ch
    # Map-reduce exactness on all dev valid steps (O per-channel).
    worst = 0.0
    for name in datasets:
        ds, _ = datasets[name]
        for pair in DEV:
            case = report["cases"][name][pair]
            if not case.get("domain"):
                continue
            l, r = ord(pair[0]), ord(pair[1])
            lf, rf = get_fields(name, l), get_fields(name, r)
            _, lo0 = glyph_cover(ds, l)
            _, ro0 = glyph_cover(ds, r)
            lo = (float(lo0[0]) - int(lf["pad"]),
                  float(lo0[1]) - int(lf["pad"]))
            ro_base = (float(ro0[0]) - int(rf["pad"]),
                       float(ro0[1]) - int(rf["pad"]))
            for rec in case["steps"]:
                if not rec.get("valid"):
                    continue
                ro = (ro_base[0] + rec["step"], ro_base[1])
                o, sh = sc.union_canvas(
                    lf["image_shape"], lo, rf["image_shape"], [ro])
                chans = ln._per_pair_overlays(lf, rf, lo, ro, o, sh)
                terms = ln._overlap_terms(chans, ln.TAU_PX)
                F = sc.facing_matrix(len(chans))
                mmap = np.zeros(sh)
                for t in terms:
                    den = math.sqrt(t["ql"] * t["qr"])
                    if not (math.isfinite(den) and den > 0.0):
                        continue
                    kval = np.exp(-((t["dL"][t["both"]] - t["dR"][t["both"]])
                                    ** 2) / (2.0 * ln.TAU_PX ** 2))
                    mmap[t["both"]] += (t["w"] * t["cL"][t["both"]]
                                        * t["cR"][t["both"]] * kval / den)
                diff = abs(float(np.sum(mmap)) - rec["nb_go"])
                worst = max(worst, diff / max(1.0, abs(rec["nb_go"])))
    report["map_reduce_worst_reldiff"] = worst
    report["total_seconds"] = time.perf_counter() - t_start
    report["ru_maxrss"] = rss_now()
    with open(CORPUS / "run_output.json", "w") as fh:
        json.dump(report, fh)
    print("cases=%d steps=%d seed=%s map_reduce_worst=%.3g total_s=%.1f" % (
        sum(len(v) for v in report["cases"].values()),
        sum(len(c.get("steps", [])) for v in report["cases"].values()
            for c in v.values()),
        {k: round(vv, 4) for k, vv in seed.items()}, worst,
        report["total_seconds"]))


if __name__ == "__main__":
    main()
