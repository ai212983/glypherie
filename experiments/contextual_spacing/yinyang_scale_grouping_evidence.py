#!/usr/bin/env python3
"""Scale-grouping G3 evidence (mechanical/model-coherence only, no optics).

Scores the predeclared G3 candidate (yinyang_scale_grouping, m=1 primary)
against frozen G2 over full forward domains on the 8 frozen captures, plus
analytic synthetics, narrow variant/tau/exponent arms, T3-grid selection
behavior, and replica-stability probes. No training, no target fitting,
no preview/runtime change. Uncertainty is uncertainty_not_certified.
"""

import hashlib
import json
import math
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yinyang_oriented_fields as yf
import yinyang_multiscale_fields as mf
import yinyang_oriented_score as sc
import yinyang_scale_grouping as sg
import yinyangfit_interactive as v1
import yinyangfit_interactive_b2 as b2

DEV = ["um", "og", "AV", "To", "mm", "ll", "NN", "Th", "rt"]
HELDOUT = ["nn", "oo", "HH", "il"]
NARROW_DELTAS = (-6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6)
TAUS = (0.25, 1.0)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def glyph_cover(ds, codepoint):
    cell = ds["cells"][codepoint]
    w, h = cell["width"], cell["height"]
    return (np.asarray(cell["cover"], dtype=np.float64).reshape(h, w),
            (float(cell["left"]), float(cell["top"])))


def forward_domain(ds, left, right, pad):
    """Exact v3.search_domain arithmetic (kept dependency-light here).

    Returns ((lo, hi), None) or (None, reason). A cross-check against
    yinyangfit_interactive_v3.search_domain runs in main() when that
    module imports cleanly.
    """
    left_cell, right_cell = ds["cells"][left], ds["cells"][right]
    spans = {}
    for tag, cell in (("l", left_cell), ("r", right_cell)):
        ox = math.trunc(cell["left"])
        xs = [ox + col for row in range(cell["height"])
              for col in range(cell["width"])
              if cell["cover"][row * cell["width"] + col] > 0.0]
        if not xs:
            return None, "blank_glyph_no_ink"
        spans[tag] = (min(xs), max(xs))
    lo = max(math.floor(spans["l"][0] - spans["r"][1]), 1)
    lox = math.trunc(left_cell["left"] - pad)
    rox = math.trunc(right_cell["left"] - pad)
    loy = math.trunc(left_cell["top"] - pad)
    roy = math.trunc(right_cell["top"] - pad)
    left_w = left_cell["width"] + 2 * pad
    if loy + left_cell["height"] + 2 * pad <= roy or \
            roy + right_cell["height"] + 2 * pad <= loy:
        return None, "row_bands_disjoint"
    hi = lox + left_w - 1 - rox
    if hi < 1:
        return None, "no_forward_step"
    return (lo, hi), None


def bar(h=20, w=64, bars=((20, 22),)):
    img = np.zeros((h, w))
    for x0, x1 in bars:
        img[4:16, x0:x1] = 1.0
    return img


def ring(n=31, r=9.0, wdt=2.0):
    ys, xs = np.mgrid[0:n, 0:n].astype(float)
    return ((np.abs(np.hypot(xs - (n - 1) / 2.0, ys - (n - 1) / 2.0) - r)
             < wdt / 2.0)).astype(float)


def diagonal(n=25):
    img = np.zeros((n, n))
    ys, xs = np.mgrid[0:n, 0:n].astype(float)
    img[np.abs(xs - ys) < 1.0] = 1.0
    return img


def synth_fields(img, banks, kernels):
    return mf.multiscale_glyph_fields(
        img, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
        v1_banks=banks, kernels=kernels)


def score_real_step(lf, rf, lo, ro, origin, shape, EL, ER, ds_cells, l, r,
                    step, variant, m_list, tau_list, want_b2, b2_scorer):
    overlap, faces, corners = v1.contact_counts(ds_cells[l], ds_cells[r],
                                                step)
    if overlap > 0:
        return {"step": step, "valid": False,
                "reason": "occupied_cell_overlap",
                "faces": faces, "corners": corners}
    rec = {"step": step, "valid": True, "faces": faces, "corners": corners}
    for variant in ("notebook", "manuscript"):
        ELv = EL[variant]
        ERv = ER[variant]
        g2 = sc.score_step(lf, rf, lo, ro, origin, shape, ELv, ERv,
                           sc.TAU_PX, variant)
        rec["g2_%s" % variant] = g2["g2"]
        rec["g2_%s_abstain" % variant] = bool(g2["abstain"])
        for m in m_list:
            s = sg.score_step_scale(lf, rf, lo, ro, origin, shape,
                                    ELv, ERv, sc.TAU_PX, variant, m)
            tag = "m%d" % int(m)
            rec["g3_%s_%s" % (variant, tag)] = s["g3"]
            rec["S_%s" % variant] = s["scale_mean_px"]
            rec["smin_%s" % variant] = s["scale_min_px"]
            rec["smax_%s" % variant] = s["scale_max_px"]
            rec["nearink_%s" % variant] = s["near_ink_share"]
            rec["g3g2_%s_%s" % (variant, tag)] = s["g3_over_g2"]
            rec["floor_%s_%s" % (variant, tag)] = s["floor_share"]
            rec["bothpx_%s" % variant] = s["both_supported_pairpx"]
            rec["abstain_%s_%s" % (variant, tag)] = bool(s["abstain"])
        for tau in tau_list:
            s = sg.score_step_scale(lf, rf, lo, ro, origin, shape,
                                    ELv, ERv, tau, variant, 1.0)
            rec["g3_%s_tau%s" % (variant, str(tau))] = s["g3"]
    if want_b2 is not None:
        brec = want_b2.score_geometry(
            l, r, step, float(v1.DEFAULT_CONTROLS.feature_scale),
            float(v1.DEFAULT_CONTROLS.proximity_falloff))
        rec["b2_valid"] = bool(brec.get("valid"))
        rec["b2_interaction"] = (float(brec["interaction"])
                                 if brec.get("valid") else None)
    return rec


def eligible(rec, variant="notebook", m=1):
    return bool(rec.get("valid")) and not bool(
        rec.get("abstain_%s_m%d" % (variant, int(m))))


def t3_selection(steps, t3):
    elig = [s for s in steps if eligible(s)]
    if not elig:
        return {"t3": t3, "eligible": 0, "chosen": None,
                "reason": "no_eligible_step", "reachable": False}
    vals = [s["g3_notebook_m1"] for s in elig]
    devs = [abs(g - t3) for g in vals]
    idx, mstar = sc.tie_set(devs)
    pick = min(idx)
    span = max(vals) - min(vals)
    return {"t3": t3, "eligible": len(elig), "chosen": elig[pick]["step"],
            "chosen_g3": vals[pick], "mstar": mstar,
            "n_ties": len(idx), "tie_idx": [elig[i]["step"] for i in idx],
            "min_g3": min(vals), "max_g3": max(vals),
            "reachable": bool(min(vals) - 1e-12 <= t3 <= max(vals) + 1e-12),
            "interior": bool(elig[pick]["step"] not in
                             (elig[0]["step"], elig[-1]["step"])),
            "g3_span": span}


def main():
    outdir = Path(sys.argv[1])
    if outdir.exists():
        raise SystemExit("refusing to reuse output directory: %s" % outdir)
    (outdir / "arrays").mkdir(parents=True)
    repo = Path(__file__).resolve().parents[2]
    t_start = time.perf_counter()
    phase = {}
    prov_path = (repo / "out/diagnostics/contextual-spacing"
                 / "yinyang-oriented-fields/implementation/provenance.json")
    stage_prov = json.loads(prov_path.read_text())
    datasets = {}
    for name, cap in stage_prov["captures"].items():
        p = repo / cap["path"]
        assert sha256_file(p) == cap["sha256"], "capture drift: %s" % name
        loader = (v1.load_mono_capture if cap["profile"] == "mono"
                  else v1.load_gray_capture)
        datasets[name] = (loader(str(p)), cap)

    # Stage-2 pad: max V1 half-support + kernel radius (frozen rule).
    s2_banks, _ = mf.build_multiscale_v1_bank(mf.DEFAULT_PARAMS)
    s2_kernels = yf.build_oriented_kernels(yf.DEFAULT_PARAMS)
    pad = int(np.ceil(4 * max(mf.DEFAULT_PARAMS.scale_sigmas_px))) \
        + int(yf.DEFAULT_PARAMS.kernel_radius_px)
    phase["pad_px"] = pad
    v3check = {"attempted": True, "importable": False, "mismatches": [],
               "note": "unset"}
    try:
        import yinyangfit_interactive_v3 as v3mod
        v3check["importable"] = True
        for name, (ds, cap) in datasets.items():
            for pair in DEV + HELDOUT:
                l, r = ord(pair[0]), ord(pair[1])
                if l not in ds["cells"] or r not in ds["cells"]:
                    continue
                mine, _ = forward_domain(ds, l, r, pad)
                theirs, _ = v3mod.search_domain(ds, l, r, pad)
                if list(mine or []) != list(theirs or []):
                    v3check["mismatches"].append(
                        {"capture": name, "pair": pair,
                         "mine": mine, "theirs": theirs})
        v3check["note"] = "all domains agree" if not v3check[
            "mismatches"] else "MISMATCH"
    except Exception as exc:
        v3check["note"] = "v3 import failed: %s" % exc
    phase["v3_domain_crosscheck"] = v3check

    energy = sc.EnergyCache()
    energy_uses = {"computes": 0, "reuses": 0}

    def get_energy(key, fields, variant):
        before = energy._cache.get((key, str(variant)))
        vec = energy.energy(key, fields, variant)
        if before is not None and before[2] is vec:
            energy_uses["reuses"] += 1
        else:
            energy_uses["computes"] += 1
        return vec

    tracemalloc.start()
    report = {"cases": {}, "synthetics": {}, "robustness": {},
              "t3_grid": list(sg.T3_GRID),
              "uncertainty": "uncertainty_not_certified",
              "flags": [], "timings": {}}
    b2_scorers = {}

    t0 = time.perf_counter()
    field_cache = {}
    n_field_builds = 0
    for name, (ds, cap) in datasets.items():
        if name not in b2_scorers:
            b2_scorers[name] = b2.PairScorer(ds)
        for pair in DEV + HELDOUT:
            l, r = ord(pair[0]), ord(pair[1])
            if l not in ds["cells"] or r not in ds["cells"]:
                report["cases"].setdefault(name, {})[pair] = {
                    "skipped": "missing glyph"}
                continue
            metric = v1.metric_step(ds, l, r)
            keys = []
            for cp in (l, r):
                ck = (cap["sha256"], "stage2", cp)
                if ck not in field_cache:
                    lc, _ = glyph_cover(ds, cp)
                    field_cache[ck] = synth_fields(
                        lc, s2_banks, s2_kernels)
                    n_field_builds += 1
                keys.append(ck)
            lf, rf = field_cache[keys[0]], field_cache[keys[1]]
            assert int(lf["pad"]) == pad and int(rf["pad"]) == pad
            lo = (float(ds["cells"][l]["left"]) - int(lf["pad"]),
                  float(ds["cells"][l]["top"]) - int(lf["pad"]))
            ro_base = (float(ds["cells"][r]["left"]) - int(rf["pad"]),
                       float(ds["cells"][r]["top"]) - int(rf["pad"]))
            (bounds, reason) = forward_domain(ds, l, r, pad)
            if bounds is None:
                report["cases"].setdefault(name, {})[pair] = {
                    "skipped": reason}
                continue
            lo_b, hi_b = bounds
            steps = list(range(lo_b, hi_b + 1))
            ros_all = [(ro_base[0] + s, ro_base[1]) for s in steps]
            origin, shape = sc.union_canvas(lf["image_shape"], lo,
                                            rf["image_shape"], ros_all)
            EL = {v: get_energy((cap["sha256"], "stage2", l), lf, v)
                  for v in ("notebook", "manuscript")}
            ER = {v: get_energy((cap["sha256"], "stage2", r), rf, v)
                  for v in ("notebook", "manuscript")}
            recs = []
            narrow = set(metric + d for d in NARROW_DELTAS) & set(steps)
            for s in steps:
                ro = (ro_base[0] + s, ro_base[1])
                rec = {"step": s, "valid": True}
                overlap, faces, corners = v1.contact_counts(
                    ds["cells"][l], ds["cells"][r], s)
                if overlap > 0:
                    recs.append({"step": s, "valid": False,
                                 "reason": "occupied_cell_overlap",
                                 "faces": faces, "corners": corners})
                    continue
                rec.update({"faces": faces, "corners": corners})
                for variant in ("notebook", "manuscript"):
                    g2 = sc.score_step(lf, rf, lo, ro, origin, shape,
                                       EL[variant], ER[variant],
                                       sc.TAU_PX, variant)
                    rec["g2_" + variant] = g2["g2"]
                    rec["g2raw_" + variant] = g2["raw"]
                    sc1 = sg.score_step_scale(
                        lf, rf, lo, ro, origin, shape,
                        EL[variant], ER[variant],
                        sc.TAU_PX, variant, 1.0)
                    rec["g3_" + variant] = sc1["g3"]
                    for k in ("raw3", "scale_mean_px", "scale_min_px",
                              "scale_max_px", "near_ink_share",
                              "g3_over_g2", "floor_share",
                              "both_supported_pairpx"):
                        rec["%s_%s" % (k, variant)] = sc1[k]
                    rec["abstain_" + variant] = bool(sc1["abstain"])
                    if s in narrow:
                        sc2 = sg.score_step_scale(
                            lf, rf, lo, ro, origin, shape,
                            EL[variant], ER[variant],
                            sc.TAU_PX, variant, 2.0)
                        rec["g3m2_" + variant] = sc2["g3"]
                        for tau in TAUS:
                            st = sg.score_step_scale(
                                lf, rf, lo, ro, origin, shape,
                                EL[variant], ER[variant],
                                tau, variant, 1.0)
                            rec["g3tau%s_%s" % (str(tau), variant)] = st[
                                "g3"]
                        brec = b2_scorers[name].score_geometry(
                            l, r, s,
                            float(v1.DEFAULT_CONTROLS.feature_scale),
                            float(v1.DEFAULT_CONTROLS.proximity_falloff))
                        rec["b2_valid"] = bool(brec.get("valid"))
                        rec["b2_interaction"] = (
                            float(brec["interaction"])
                            if brec.get("valid") else None)
                recs.append(rec)
            t3rec = {str(t): t3_selection(
                [{"step": rc["step"], "valid": rc["valid"],
                  "abstain_notebook_m1": rc.get("abstain_notebook", True),
                  "g3_notebook_m1": rc.get("g3_notebook", 0.0)}
                 for rc in recs], t) for t in sg.T3_GRID}
            g2vals = [(rc["step"], rc["g2_notebook"]) for rc in recs
                      if rc.get("valid") and not rc.get("abstain_notebook",
                                                        True)]
            case_flags = ["uncertainty_not_certified"]
            if any(rc.get("valid") and rc.get("floor_share_notebook", 0)
                   >= 0.01 for rc in recs):
                case_flags.append("hypothesis_flag:floor_share>=1pc")
            near = [rc.get("near_ink_share_notebook", 0.0) for rc in recs
                    if rc.get("valid")]
            if near and max(near) > 0.5:
                case_flags.append("hypothesis_flag:near_ink_dominates")
            report["cases"].setdefault(name, {})[pair] = {
                "metric": metric, "domain": [lo_b, hi_b],
                "n_eligible": sum(1 for rc in recs
                                  if rc.get("valid") and not rc.get(
                                      "abstain_notebook", True)),
                "steps": recs, "t3": t3rec,
                "argmin_g2_step": (min(g2vals, key=lambda t: t[1])[0]
                                   if g2vals else None),
                "b2_note": "narrow steps only; raw deltas, no equivalence",
                "flags": case_flags,
                "canvas_origin": list(origin),
                "canvas_shape": list(shape)}
    phase["main_scoring_seconds"] = time.perf_counter() - t0
    _, trace_peak = tracemalloc.get_traced_memory()
    phase["tracemalloc_peak_main_B"] = trace_peak
    tracemalloc.reset_peak()

    t0 = time.perf_counter()
    syn = {}
    # S1 parallel bars, gap sweep 1..20 (stage-2 fields, integer offsets).
    s1 = []
    for gap in range(1, 21):
        left = bar(bars=((10, 12),))
        right = bar(bars=((12 + gap, 14 + gap),))
        lf = synth_fields(left, s2_banks, s2_kernels)
        rf = synth_fields(right, s2_banks, s2_kernels)
        EL, ER = sc.self_energy(lf, "notebook"), sc.self_energy(
            rf, "notebook")
        lo = (0.0 - lf["pad"], 0.0 - lf["pad"])
        ro = (0.0 - rf["pad"], 0.0 - rf["pad"])
        origin, shape = sc.union_canvas(lf["image_shape"], lo,
                                        rf["image_shape"], [ro])
        out = sg.score_step_scale(lf, rf, lo, ro, origin, shape,
                                  EL, ER, sc.TAU_PX, "notebook", 1.0)
        out2 = sc.score_step(lf, rf, lo, ro, origin, shape, EL, ER,
                             sc.TAU_PX, "notebook")
        s1.append({"gap": gap, "g3": out["g3"], "g2": out2["g2"],
                   "S": out["scale_mean_px"],
                   "smin": out["scale_min_px"],
                   "smax": out["scale_max_px"]})
    syn["parallel_bars_gap_sweep"] = s1
    # S3 far stem: third bar 24px behind the left bar.
    pair_img = (bar(bars=((10, 12),)), bar(bars=((16, 18),)))
    trio_img = (bar(bars=((10, 12),)), bar(bars=((16, 18),)))
    trio_img = (np.maximum(trio_img[0], bar(bars=((34, 36),))[:20, :64]),
                trio_img[1])
    far = []
    for tag, (li, ri) in (("pair", pair_img), ("trio", trio_img)):
        lf = synth_fields(li, s2_banks, s2_kernels)
        rf = synth_fields(ri, s2_banks, s2_kernels)
        EL, ER = sc.self_energy(lf, "notebook"), sc.self_energy(
            rf, "notebook")
        lo = (0.0 - lf["pad"], 0.0 - lf["pad"])
        ro = (0.0 - rf["pad"], 0.0 - rf["pad"])
        origin, shape = sc.union_canvas(lf["image_shape"], lo,
                                        rf["image_shape"], [ro])
        out = sg.score_step_scale(lf, rf, lo, ro, origin, shape,
                                  EL, ER, sc.TAU_PX, "notebook", 1.0)
        out2 = sc.score_step(lf, rf, lo, ro, origin, shape, EL, ER,
                             sc.TAU_PX, "notebook")
        far.append({"case": tag, "g3": out["g3"], "g2": out2["g2"],
                    "S": out["scale_mean_px"],
                    "ratio": out["g3_over_g2"]})
    syn["far_stem"] = far
    # S4/S5/S6/S7 shapes + S8 transport + contrast.
    shapes = {"curve": (ring(), ring()), "diagonal": (diagonal(),
              diagonal()), "counter": (ring(n=41, r=13.0), ring(n=41,
              r=13.0))}
    for sname, (li, ri) in shapes.items():
        lf = synth_fields(li, s2_banks, s2_kernels)
        rf = synth_fields(ri, s2_banks, s2_kernels)
        EL, ER = sc.self_energy(lf, "notebook"), sc.self_energy(
            rf, "notebook")
        lo = (0.0 - lf["pad"], 0.0 - lf["pad"])
        ro = (6.0 - rf["pad"], 0.0 - rf["pad"])
        origin, shape = sc.union_canvas(lf["image_shape"], lo,
                                        rf["image_shape"], [ro])
        out = sg.score_step_scale(lf, rf, lo, ro, origin, shape,
                                  EL, ER, sc.TAU_PX, "notebook", 1.0)
        out2 = sc.score_step(lf, rf, lo, ro, origin, shape, EL, ER,
                             sc.TAU_PX, "notebook")
        syn[sname] = {"g3": out["g3"], "g2": out2["g2"],
                      "S": out["scale_mean_px"]}
    tr = {}
    x2 = np.repeat(np.repeat(bar(), 2, axis=0), 2, axis=1)
    for tag, img in (("x1", bar()), ("x2", x2)):
        lf = synth_fields(img, s2_banks, s2_kernels)
        EL = sc.self_energy(lf, "notebook")
        lo = (0.0 - lf["pad"], 0.0 - lf["pad"])
        ro = (0.0 - lf["pad"], 0.0 - lf["pad"])
        origin, shape = sc.union_canvas(lf["image_shape"], lo,
                                        lf["image_shape"], [ro])
        out = sg.score_step_scale(lf, lf, lo, ro, origin, shape,
                                  EL, EL, sc.TAU_PX, "notebook", 1.0)
        tr[tag] = {"g3": out["g3"], "S": out["scale_mean_px"]}
    syn["transport_2x_nearest"] = tr
    lf = synth_fields(bar(), s2_banks, s2_kernels)
    lf_half = synth_fields(0.5 * bar(), s2_banks, s2_kernels)
    EL, ELh = sc.self_energy(lf, "notebook"), sc.self_energy(
        lf_half, "notebook")
    lo = (0.0 - lf["pad"], 0.0 - lf["pad"])
    origin, shape = sc.union_canvas(lf["image_shape"], lo,
                                    lf["image_shape"], [lo])
    a = sg.score_step_scale(lf, lf, lo, lo, origin, shape, EL, EL,
                            sc.TAU_PX, "notebook", 1.0)
    bp = sg.score_step_scale(lf_half, lf_half, lo, lo, origin, shape,
                             ELh, ELh, sc.TAU_PX, "notebook", 1.0)
    syn["contrast_half_gain"] = {"g3_full": a["g3"], "g3_half": bp["g3"],
                                 "S_full": a["scale_mean_px"],
                                 "S_half": bp["scale_mean_px"]}
    report["synthetics"] = syn
    phase["synthetics_seconds"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    rob = {}
    # R1 pad+8 and R2 1-ulp on two pair-cases, narrow steps.
    for name, pair in (("literata-16-mono", "um"),
                       ("roboto-16-gray", "og")):
        ds, cap = datasets[name]
        l, r = ord(pair[0]), ord(pair[1])
        metric = v1.metric_step(ds, l, r)
        lc, lo0 = glyph_cover(ds, l)
        rc, ro0 = glyph_cover(ds, r)
        lf = synth_fields(lc, s2_banks, s2_kernels)
        rf = synth_fields(rc, s2_banks, s2_kernels)
        lo = (float(lo0[0]) - int(lf["pad"]),
              float(lo0[1]) - int(lf["pad"]))
        ro_base = (float(ro0[0]) - int(rf["pad"]),
                   float(ro0[1]) - int(rf["pad"]))
        (bounds, _) = forward_domain(ds, l, r, pad)
        steps = [s for s in range(bounds[0], bounds[1] + 1)
                 if metric - 6 <= s <= metric + 6]
        ros_all = [(ro_base[0] + s, ro_base[1]) for s in steps]
        origin, shape = sc.union_canvas(lf["image_shape"], lo,
                                        rf["image_shape"], ros_all)
        EL, ER = sc.self_energy(lf, "notebook"), sc.self_energy(
            rf, "notebook")
        base = {}
        for s in steps:
            overlap, _, _ = v1.contact_counts(ds["cells"][l],
                                              ds["cells"][r], s)
            if overlap:
                continue
            ro = (ro_base[0] + s, ro_base[1])
            base[s] = sg.score_step_scale(lf, rf, lo, ro, origin,
                                          shape, EL, ER, sc.TAU_PX,
                                          "notebook", 1.0)
        lf8 = mf.multiscale_glyph_fields(
            lc, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
            v1_banks=s2_banks, kernels=s2_kernels, pad=int(pad) + 8)
        rf8 = mf.multiscale_glyph_fields(
            rc, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
            v1_banks=s2_banks, kernels=s2_kernels, pad=int(pad) + 8)
        lo8 = (float(lo0[0]) - int(lf8["pad"]),
               float(lo0[1]) - int(lf8["pad"]))
        ro8 = (float(ro0[0]) - int(rf8["pad"]),
               float(ro0[1]) - int(rf8["pad"]))
        (b8, _) = forward_domain(ds, l, r, int(pad) + 8)
        EL8, ER8 = sc.self_energy(lf8, "notebook"), sc.self_energy(
            rf8, "notebook")
        dg3, dS, dg2 = [], [], []
        for s in steps:
            if s not in base or not (b8[0] <= s <= b8[1]):
                continue
            overlap, _, _ = v1.contact_counts(ds["cells"][l],
                                              ds["cells"][r], s)
            if overlap:
                continue
            ros8 = [(ro8[0] + q, ro8[1]) for q in steps]
            o8, sh8 = sc.union_canvas(lf8["image_shape"], lo8,
                                      rf8["image_shape"], ros8)
            ro = (ro8[0] + s, ro8[1])
            o = sg.score_step_scale(lf8, rf8, lo8, ro, o8, sh8,
                                    EL8, ER8, sc.TAU_PX, "notebook", 1.0)
            g = sc.score_step(lf8, rf8, lo8, ro, o8, sh8, EL8, ER8,
                              sc.TAU_PX, "notebook")
            b = base[s]
            dg3.append(abs(o["g3"] - b["g3"]))
            dg2.append(abs(g["g2"] - sc.score_step(
                lf, rf, lo, (ro_base[0] + s, ro_base[1]), origin,
                shape, EL, ER, sc.TAU_PX, "notebook")["g2"]))
            if np.isfinite(o["scale_mean_px"]) and np.isfinite(
                    b["scale_mean_px"]):
                dS.append(abs(o["scale_mean_px"] - b["scale_mean_px"]))
        ulp = np.nextafter(lc, np.inf) - lc
        lc_u = lc + ulp
        rc_u = rc + (np.nextafter(rc, np.inf) - rc)
        lfu = synth_fields(lc_u, s2_banks, s2_kernels)
        rfu = synth_fields(rc_u, s2_banks, s2_kernels)
        ELu, ERu = sc.self_energy(lfu, "notebook"), sc.self_energy(
            rfu, "notebook")
        du3, duS = [], []
        for s in steps:
            if s not in base:
                continue
            overlap, _, _ = v1.contact_counts(ds["cells"][l],
                                              ds["cells"][r], s)
            if overlap:
                continue
            ro = (ro_base[0] + s, ro_base[1])
            o = sg.score_step_scale(lfu, rfu, lo, ro, origin, shape,
                                    ELu, ERu, sc.TAU_PX, "notebook",
                                    1.0)
            b = base[s]
            du3.append(abs(o["g3"] - b["g3"]))
            if np.isfinite(o["scale_mean_px"]) and np.isfinite(
                    b["scale_mean_px"]):
                duS.append(abs(o["scale_mean_px"] - b["scale_mean_px"]))
        # R3 map exactness on up to 3 valid narrow steps.
        mapdiffs = []
        for s in [q for q in steps if q in base][:3]:
            ro = (ro_base[0] + s, ro_base[1])
            mp = sg.contribution_map_scale(
                lf, rf, lo, ro, origin, shape, EL, ER, sc.TAU_PX,
                "notebook", 1.0)
            mapdiffs.append(abs(float(np.sum(mp)) - base[s]["g3"]))
        rob["%s/%s" % (name, pair)] = {
            "pad8_max_dg3": max(dg3) if dg3 else None,
            "pad8_max_dg2": max(dg2) if dg2 else None,
            "pad8_max_dS": max(dS) if dS else None,
            "pad8_domain": list(b8),
            "ulp_max_dg3": max(du3) if du3 else None,
            "ulp_max_dS": max(duS) if duS else None,
            "map_max_absdiff": max(mapdiffs) if mapdiffs else None}
    report["robustness"] = rob
    phase["robustness_seconds"] = time.perf_counter() - t0
    report["energy_cache"] = dict(energy_uses)
    report["field_builds"] = n_field_builds

    prov = dict(stage_prov.get("provenance", {}))
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=str(repo)).stdout.strip()
    except Exception:
        head = "unknown"
    (outdir / "provenance.json").write_text(json.dumps(
        {"model": sg.MODEL_IDENTITY,
         "candidate_module_sha256": sha256_file(
             Path(__file__).resolve().parent
             / "yinyang_scale_grouping.py"),
         "evidence_sha256": sha256_file(Path(__file__).resolve()),
         "git_head": head,
         "stage_provenance_implementation_sha256": stage_prov.get(
             "implementation_sha256"),
         "captures": stage_prov.get("captures"),
         "params": {"tau": sc.TAU_PX, "m_primary": 1.0,
                    "t3_grid": list(sg.T3_GRID)}},
        indent=1))
    report["timings"] = phase
    report["timings"]["total_seconds"] = time.perf_counter() - t_start
    try:
        import resource
        report["timings"]["ru_maxrss"] = int(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except Exception:
        pass
    with (outdir / "arrays").joinpath("placeholder.txt").open("w") as fh:
        fh.write("curves live in report.json steps records\n")
    (outdir / "report.json").write_text(json.dumps(report, indent=1,
                                                   default=str))
    print(json.dumps({"cases": sum(len(v) for v in report["cases"].values()),
                      "seconds": round(report["timings"]["total_seconds"],
                                       1)}))


if __name__ == "__main__":
    main()
