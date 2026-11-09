#!/usr/bin/env python3
"""SCORE-v2 full-study evidence (mechanical/model-coherence only, no optical claim)."""

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
import yinyangfit_interactive as v1
import yinyangfit_interactive_b2 as b2

FOCUS = ["um", "og", "AV", "To"]
HELDOUT = ["nn", "oo", "HH", "il"]
DELTAS_NARROW = (-2, -1, 0, 1, 2)
DELTAS_BROAD = (-6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6)
TAUS = (0.25, 0.5, 1.0)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def glyph_cover(ds, codepoint):
    cell = ds["cells"][codepoint]
    w, h = cell["width"], cell["height"]
    return (np.asarray(cell["cover"], dtype=np.float64).reshape(h, w),
            (float(cell["left"]), float(cell["top"])))


def rss_now():
    try:
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except Exception:
        return 0


def rss_probe_mode():
    out = {"mode": "rss-probe"}
    t0 = time.perf_counter()
    repo = Path(__file__).resolve().parents[2]
    name, pair = sys.argv[sys.argv.index("--rss-probe") + 1 :][:2]
    prov = json.loads((repo / "out/diagnostics/contextual-spacing"
                       / "yinyang-oriented-fields/implementation"
                       / "provenance.json").read_text())
    cap = prov["captures"][name]
    loader = (v1.load_mono_capture if cap["profile"] == "mono"
              else v1.load_gray_capture)
    ds = loader(str(repo / cap["path"]))
    l, r = ord(pair[0]), ord(pair[1])
    banks, _ = mf.build_multiscale_v1_bank()
    kernels = yf.build_oriented_kernels(yf.DEFAULT_PARAMS)
    lc, lo0 = glyph_cover(ds, l)
    rc, ro0 = glyph_cover(ds, r)
    lf = mf.multiscale_glyph_fields(lc, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
                                    v1_banks=banks, kernels=kernels)
    rf = mf.multiscale_glyph_fields(rc, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
                                    v1_banks=banks, kernels=kernels)
    metric = v1.metric_step(ds, l, r)
    lo = (float(lo0[0]) - int(lf["pad"]), float(lo0[1]) - int(lf["pad"]))
    ro_base = (float(ro0[0]) - int(rf["pad"]), float(ro0[1]) - int(rf["pad"]))
    EL = sc.self_energy(lf, "notebook")
    ER = sc.self_energy(rf, "notebook")
    ls, rs = lf["image_shape"], rf["image_shape"]
    ros = [(ro_base[0] + metric + d, ro_base[1]) for d in DELTAS_BROAD]
    origin, shape = sc.union_canvas(ls, lo, rs, ros)
    n = 0
    for d in DELTAS_NARROW:
        step = metric + d
        if v1.contact_counts(ds["cells"][l], ds["cells"][r], step)[0] > 0:
            continue
        sc.score_step(lf, rf, lo, (ro_base[0] + step, ro_base[1]),
                      origin, shape, EL, ER)
        n += 1
    out.update({"capture": name, "pair": pair, "steps_scored": n,
                "seconds": time.perf_counter() - t0, "ru_maxrss": rss_now(),
                "platform": sys.platform,
                "ru_maxrss_unit": "bytes" if sys.platform == "darwin"
                else "KiB" if sys.platform.startswith("linux")
                else "platform-dependent"})
    print(json.dumps(out))


def bar_image(h=48, w=48, x0=20, x1=22, y0=8, y1=40):
    img = np.zeros((h, w))
    img[y0:y1, x0:x1] = 1.0
    return img


def synth_curve():
    img = np.zeros((25, 25))
    ys, xs = np.mgrid[0:25, 0:25].astype(float)
    img[np.abs(np.hypot(xs - 12, ys - 12) - 6.0) < 0.9] = 1.0
    return img


def synth_diagonal():
    img = np.zeros((21, 21))
    ys, xs = np.mgrid[0:21, 0:21].astype(float)
    img[np.abs(xs - ys) < 1.0] = 1.0
    return img


def run_case(ds, pair, lf, rf, lo, ro_base, metric, deltas, energy,
             stage_label, tau_list, want_b2, b2_scorer, l, r, *,
             capture_identity):
    ls, rs = lf["image_shape"], rf["image_shape"]
    ros_all = [(ro_base[0] + metric + d, ro_base[1]) for d in deltas]
    origin, shape = sc.union_canvas(ls, lo, rs, ros_all)
    steps = []
    for d in deltas:
        step = metric + d
        overlap, faces, corners = v1.contact_counts(
            ds["cells"][l], ds["cells"][r], step)
        if overlap > 0:
            steps.append({"step": step, "delta": d, "valid": False,
                          "reason": "occupied_cell_overlap",
                          "faces": faces, "corners": corners})
            continue
        ro = (ro_base[0] + step, ro_base[1])
        rec = {"step": step, "delta": d, "valid": True,
               "faces": faces, "corners": corners}
        for variant in ("notebook", "manuscript"):
            EL = energy.energy((capture_identity, stage_label, l), lf, variant)
            ER = energy.energy((capture_identity, stage_label, r), rf, variant)
            key = "g2_" + ("primary" if variant == "notebook" else "a1")
            s = sc.score_step(lf, rf, lo, ro, origin, shape, EL, ER,
                              sc.TAU_PX, variant)
            rec[key] = s["g2"]
            rec[key + "_raw"] = s["raw"]
            rec[key + "_floor_share"] = s["floor_share"]
            rec[key + "_raw_floor_share"] = s["raw_floor_share"]
            rec[key + "_both_pairpx"] = s["both_supported_pairpx"]
            if variant == "notebook" and s["raw"] == 0.0 \
                    and s["both_supported_pairpx"] == 0:
                rec["abstain"] = True
        for tau in tau_list:
            EL = energy.energy((capture_identity, stage_label, l), lf, "notebook")
            ER = energy.energy((capture_identity, stage_label, r), rf, "notebook")
            s = sc.score_step(lf, rf, lo, ro, origin, shape, EL, ER,
                              tau, "notebook")
            rec["g2_tau_%s" % str(tau)] = s["g2"]
        if want_b2 is not None:
            brec = want_b2.score_geometry(
                l, r, step, float(v1.DEFAULT_CONTROLS.feature_scale),
                float(v1.DEFAULT_CONTROLS.proximity_falloff))
            rec["b2_valid"] = bool(brec.get("valid"))
            rec["b2_interaction"] = (float(brec["interaction"])
                                     if brec.get("valid") else None)
        steps.append(rec)
    return steps, (origin, shape)


def apply_cstar(valid_g2, cstar):
    devs = [abs(g - cstar) for g in valid_g2]
    idx, mstar = sc.tie_set(devs)
    pick = min(idx) if len(idx) == 1 else idx
    single = min(idx)
    return {"deviations": devs, "mstar": mstar, "tie_idx": idx,
            "tie_pick_lowest": single, "sole": pick if len(idx) == 1 else None}


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

    t0 = time.perf_counter()
    s1_bank = yf.build_v1_bank(yf.DEFAULT_PARAMS)
    s1_kernels = yf.build_oriented_kernels(yf.DEFAULT_PARAMS)
    s2_banks, _ = mf.build_multiscale_v1_bank(mf.DEFAULT_PARAMS)
    s2_kernels = yf.build_oriented_kernels(yf.DEFAULT_PARAMS)
    phase["banks_seconds"] = time.perf_counter() - t0

    energy = sc.EnergyCache()
    tracemalloc.start()
    report = {"cases": {}, "synthetics": {}, "validation": {},
              "cstar": {"grid": list(sc.CSTAR_GRID)},
              "uncertainty": "uncertainty_not_certified",
              "flags": [], "timings": {}}
    b2_scorers = {}

    t0 = time.perf_counter()
    for name, (ds, cap) in datasets.items():
        if name not in b2_scorers:
            b2_scorers[name] = b2.PairScorer(ds)
        for pair in FOCUS + HELDOUT:
            l, r = ord(pair[0]), ord(pair[1])
            if l not in ds["cells"] or r not in ds["cells"]:
                report["cases"].setdefault(name, {})[pair] = {
                    "skipped": "missing glyph"}
                continue
            metric = v1.metric_step(ds, l, r)
            lc, lo0 = glyph_cover(ds, l)
            rc, ro0 = glyph_cover(ds, r)
            lf = mf.multiscale_glyph_fields(
                lc, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
                v1_banks=s2_banks, kernels=s2_kernels)
            rf = mf.multiscale_glyph_fields(
                rc, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
                v1_banks=s2_banks, kernels=s2_kernels)
            lo = (float(lo0[0]) - int(lf["pad"]),
                  float(lo0[1]) - int(lf["pad"]))
            ro_base = (float(ro0[0]) - int(rf["pad"]),
                       float(ro0[1]) - int(rf["pad"]))
            steps, (origin, shape) = run_case(
                ds, pair, lf, rf, lo, ro_base, metric, DELTAS_BROAD,
                energy, "stage2", (0.25, 1.0), b2_scorers[name],
                b2_scorers[name], l, r, capture_identity=cap["sha256"])
            for rec in steps:
                if rec.get("valid"):
                    rec["g2_tau_0.5"] = rec["g2_primary"]
            narrow = [s for s in steps if s.get("valid")
                      and s["delta"] in DELTAS_NARROW]
            g2n = [s["g2_primary"] for s in narrow]
            cstar_case = {}
            for cstar in sc.CSTAR_GRID:
                cstar_case[str(cstar)] = apply_cstar(g2n, cstar) if g2n else None
            try:
                b2choice = b2_scorers[name].evaluate_pair(
                    l, r, v1.DEFAULT_CONTROLS)
                b2_step = b2choice.get("chosen")
            except Exception as exc:
                b2_step = "error:%s" % exc
            case_flags = ["uncertainty_not_certified"]
            if any(s.get("valid") and s["g2_primary_floor_share"] >= 0.01
                   for s in steps):
                case_flags.append("hypothesis_flag:floor_share>=1pc")
            if narrow and (max(g2n) - min(g2n)) < 1e-9:
                case_flags.append("hypothesis_flag:flat_narrow_curve")
            if any(s.get("abstain") for s in narrow):
                case_flags.append("hypothesis_flag:abstain_step")
            report["cases"].setdefault(name, {})[pair] = {
                "metric": metric, "narrow_g2": g2n,
                "steps": steps, "cstar": cstar_case,
                "b2_chosen": b2_step, "flags": case_flags,
                "canvas_origin": list(origin), "canvas_shape": list(shape)}
    phase["main_scoring_seconds"] = time.perf_counter() - t0
    _, trace_peak = tracemalloc.get_traced_memory()
    phase["tracemalloc_peak_main_B"] = trace_peak
    tracemalloc.reset_peak()

    t0 = time.perf_counter()
    reg = {}
    for name, (ds, cap) in datasets.items():
        for pair in FOCUS + HELDOUT:
            l, r = ord(pair[0]), ord(pair[1])
            if l not in ds["cells"] or r not in ds["cells"]:
                continue
            metric = v1.metric_step(ds, l, r)
            lc, lo0 = glyph_cover(ds, l)
            rc, ro0 = glyph_cover(ds, r)
            lf = yf.oriented_fields_for_image(lc, yf.DEFAULT_PARAMS,
                                              s1_bank, s1_kernels)
            rf = yf.oriented_fields_for_image(rc, yf.DEFAULT_PARAMS,
                                              s1_bank, s1_kernels)
            lo = (float(lo0[0]) - int(lf["pad"]),
                  float(lo0[1]) - int(lf["pad"]))
            ro_base = (float(ro0[0]) - int(rf["pad"]),
                       float(ro0[1]) - int(rf["pad"]))
            steps, _ = run_case(ds, pair, lf, rf, lo, ro_base, metric,
                                DELTAS_NARROW, energy, "stage1", (),
                                None, None, l, r,
                                capture_identity=cap["sha256"])
            reg.setdefault(name, {})[pair] = [
                {"step": s["step"], "g2": s.get("g2_primary"),
                 "floor_share": s.get("g2_primary_floor_share"),
                 "valid": s.get("valid")} for s in steps]
    report["stage1_regression"] = reg
    phase["stage1_regression_seconds"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    syn = {}
    bar = bar_image()
    s2bar = mf.multiscale_glyph_fields(
        bar, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
        v1_banks=s2_banks, kernels=s2_kernels)
    Ebar = sc.self_energy(s2bar, "notebook")
    union0 = sc.union_canvas(s2bar["image_shape"], (-18, -18),
                             s2bar["image_shape"], [(8 - 18, -18)])
    syn["self_contained_shapes"] = bool(np.all(np.isfinite(Ebar)))
    dbl = np.zeros((48, 72))
    dbl[8:40, 20:22] = 1.0
    dbl[8:40, 44:46] = 1.0
    s2dbl = mf.multiscale_glyph_fields(
        dbl, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
        v1_banks=s2_banks, kernels=s2_kernels)
    Edbl = sc.self_energy(s2dbl, "notebook")
    Ld = mf.multiscale_glyph_fields(
        bar_image(), weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
        v1_banks=s2_banks, kernels=s2_kernels)
    lo_d = (-int(Ld["pad"]), -int(Ld["pad"]))
    for tag, Lf, EL in (("single", Ld, sc.self_energy(Ld, "notebook")),
                        ("double", s2dbl, Edbl)):
        lo_tag = (-int(Lf["pad"]), -int(Lf["pad"]))
        ros = (8 - int(Lf["pad"]), -int(Lf["pad"]))
        o, sh = sc.union_canvas(Lf["image_shape"], lo_tag,
                                s2bar["image_shape"], [ros])
        s = sc.score_step(Lf, s2bar, lo_tag, ros, o, sh, EL, Ebar)
        syn["dilution_%s_g2" % tag] = s["g2"]
    syn["dilution_ratio_double_over_single"] = (
        syn["dilution_double_g2"] / max(syn["dilution_single_g2"], 1e-300))
    syn["dilution_E_ratio"] = float(np.sum(Edbl) / max(np.sum(Ebar), 1e-300))
    narrow_img = bar_image(x0=20, x1=22)
    wide_img = bar_image(x0=18, x1=24)
    Ln = mf.multiscale_glyph_fields(
        narrow_img, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
        v1_banks=s2_banks, kernels=s2_kernels)
    Lw = mf.multiscale_glyph_fields(
        wide_img, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
        v1_banks=s2_banks, kernels=s2_kernels)
    Ebar_n = sc.self_energy(Ln, "notebook")
    o, sh = sc.union_canvas(Ln["image_shape"], (-int(Ln["pad"]), -int(Ln["pad"])),
                            s2bar["image_shape"], [(8 - int(Ln["pad"]),
                                                    -int(Ln["pad"]))])
    gn = sc.score_step(Ln, s2bar, (-int(Ln["pad"]), -int(Ln["pad"])),
                       (8 - int(Ln["pad"]), -int(Ln["pad"])), o, sh,
                       Ebar_n, Ebar)["g2"]
    gw = sc.score_step(Lw, s2bar, (-int(Lw["pad"]), -int(Lw["pad"])),
                       (8 - int(Lw["pad"]), -int(Lw["pad"])), o, sh,
                       sc.self_energy(Lw, "notebook"), Ebar)["g2"]
    syn["mass_narrow_g2"] = gn
    syn["mass_wide_g2"] = gw
    rep = np.zeros((20, 33))
    for x in (4, 12, 20):
        rep[4:16, x:x + 2] = 1.0
    single = np.zeros((20, 16))
    single[4:16, 4:6] = 1.0
    k_results = {}
    for tag, builder in (("stage1", yf.oriented_fields_for_image),):
        if tag == "stage1":
            Lr = builder(rep, yf.DEFAULT_PARAMS, s1_bank, s1_kernels)
            Rr = builder(single, yf.DEFAULT_PARAMS, s1_bank, s1_kernels)
        ELr = sc.self_energy(Lr, "notebook")
        ERr = sc.self_energy(Rr, "notebook")
        pr = int(Lr["pad"])
        ros = [(dx - pr, -pr) for dx in range(25)]
        o, sh = sc.union_canvas(Lr["image_shape"], (-pr, -pr),
                                Rr["image_shape"], ros)
        curve = [sc.score_step(Lr, Rr, (-pr, -pr), ro, o, sh, ELr, ERr)["g2"]
                 for ro in ros]
        turns = sum(1 for i in range(1, len(curve) - 1)
                    if (curve[i] - curve[i - 1])
                    * (curve[i + 1] - curve[i]) < 0)
        k_results[tag] = {"curve": curve, "turns": turns}
    syn["k_curve"] = k_results
    for tag, img in (("curve", synth_curve()), ("diagonal", synth_diagonal())):
        F = mf.multiscale_glyph_fields(
            img, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
            v1_banks=s2_banks, kernels=s2_kernels)
        o, sh = sc.union_canvas(F["image_shape"], (-int(F["pad"]), -int(F["pad"])),
                                s2bar["image_shape"], [(4 - int(F["pad"]),
                                                        -int(F["pad"]))])
        syn["shape_%s_g2" % tag] = sc.score_step(
            F, s2bar, (-int(F["pad"]), -int(F["pad"])),
            (4 - int(F["pad"]), -int(F["pad"])), o, sh,
            sc.self_energy(F, "notebook"), Ebar)["g2"]
    report["synthetics"] = syn
    phase["synthetics_seconds"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    val = {}
    Fmat = sc.facing_matrix(16)
    val["facing_sum"] = float(np.sum(Fmat))
    val["facing_sum_is_128"] = bool(abs(float(np.sum(Fmat)) - 128.0) < 1e-9)
    tiny = {
        "supported": np.ones((2, 2, 3), dtype=bool),
        "U2": np.full((2, 2, 3), 2.0),
        "distance": np.array([[[1.0, 1.0, 1.0], [1.0, 1.0, 1.0]],
                              [[2.0, 2.0, 2.0], [2.0, 2.0, 2.0]]]),
        "confidence_notebook": np.array([[[1.0, 2.0, 0.0], [0.0, 1.0, 1.0]],
                                         [[1.0, 1.0, 1.0], [2.0, 0.0, 1.0]]]),
        "arc_strength": np.zeros((2, 2, 3)),
        "image_shape": (2, 3),
    }
    tiny["supported"][0, 1, 2] = False
    tiny["confidence_notebook"][0, 1, 2] = 0.0
    ELt = sc.self_energy(tiny, "notebook")
    ERt = ELt.copy()
    o, sh = sc.union_canvas((2, 3), (0, 0), (2, 3), [(0, 0)])
    got = sc.score_step(tiny, tiny, (0, 0), (0, 0), o, sh, ELt, ERt,
                        0.5, "notebook")
    th = yf.directed_angles(2)
    exp_raw = 0.0
    exp_n = 0.0
    c = np.where(tiny["supported"], tiny["confidence_notebook"], 0.0)
    d = np.where(tiny["supported"], tiny["distance"], 0.0)
    E = np.array([np.sum(c[i] ** 2) for i in range(2)])
    for a in range(2):
        for b_ in range(2):
            w = math.sin((th[a] - th[b_]) / 2.0) ** 2
            den = math.sqrt(E[a] * E[b_])
            if w == 0.0 or den <= 0:
                continue
            for yy in range(2):
                for xx in range(3):
                    if not (tiny["supported"][a, yy, xx]
                            and tiny["supported"][b_, yy, xx]):
                        continue
                    dd = abs(d[a, yy, xx] - d[b_, yy, xx])
                    t = (c[a, yy, xx] * c[b_, yy, xx]
                         * math.exp(-dd * dd / 0.5))
                    exp_raw += w * t
                    exp_n += w * t / den
    val["tiny_manual_g2"] = got["g2"]
    val["tiny_manual_expected"] = exp_n
    val["tiny_manual_match"] = bool(abs(got["g2"] - exp_n) < 1e-12
                                    and abs(got["raw"] - exp_raw) < 1e-9)
    blank = np.zeros((12, 12))
    Fb = mf.multiscale_glyph_fields(
        blank, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
        v1_banks=s2_banks, kernels=s2_kernels)
    Eb = sc.self_energy(Fb, "notebook")
    val["blank_E_is_zero"] = bool(np.all(Eb == 0.0))
    o, sh = sc.union_canvas(Fb["image_shape"], (0, 0), Fb["image_shape"], [(0, 0)])
    sb = sc.score_step(Fb, Fb, (0, 0), (0, 0), o, sh, Eb, Eb)
    val["blank_g2_zero_abstain"] = bool(sb["g2"] == 0.0
                                        and sb["both_supported_pairpx"] == 0)
    all_g2 = [s["g2_primary"] for cap in report["cases"].values()
              for case in cap.values() if isinstance(case, dict)
              for s in case.get("steps", []) if s.get("valid")]
    val["cauchy_min"] = float(min(all_g2)) if all_g2 else None
    val["cauchy_max"] = float(max(all_g2)) if all_g2 else None
    val["cauchy_bound_ok"] = bool(all(0.0 <= g <= 128.0 for g in all_g2))
    val["any_nan"] = bool(any(math.isnan(g) for g in all_g2))
    try:
        from_nan = [s for cap in report["cases"].values()
                    for case in cap.values() if isinstance(case, dict)
                    for s in case.get("steps", [])]
        val["n_steps_total"] = len(from_nan)
    except Exception:
        val["n_steps_total"] = None
    ds0, cap0 = datasets["roboto-16-mono"]
    l0, r0 = ord("u"), ord("m")
    lc0, lo00 = glyph_cover(ds0, l0)
    rc0, ro00 = glyph_cover(ds0, r0)
    lf0 = mf.multiscale_glyph_fields(
        lc0, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
        v1_banks=s2_banks, kernels=s2_kernels)
    rf0 = mf.multiscale_glyph_fields(
        rc0, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
        v1_banks=s2_banks, kernels=s2_kernels)
    lo0p = (float(lo00[0]) - int(lf0["pad"]), float(lo00[1]) - int(lf0["pad"]))
    ro0p = (float(ro00[0]) - int(rf0["pad"]), float(ro00[1]) - int(rf0["pad"]))
    m0 = v1.metric_step(ds0, l0, r0)
    ro_m = (ro0p[0] + m0, ro0p[1])
    EL0 = sc.self_energy(lf0, "notebook")
    ER0 = sc.self_energy(rf0, "notebook")
    o, sh = sc.union_canvas(lf0["image_shape"], lo0p, rf0["image_shape"], [ro_m])
    a = sc.score_step(lf0, rf0, lo0p, ro_m, o, sh, EL0, ER0)
    b = sc.score_step(rf0, lf0, ro_m, lo0p, o, sh, ER0, EL0)
    val["symmetry_rel_diff"] = abs(a["g2"] - b["g2"]) / max(a["g2"], 1e-300)
    val["symmetry_ok_le_1e9"] = bool(val["symmetry_rel_diff"] <= 1e-9)
    c2 = sc.score_step(lf0, rf0, lo0p, ro_m, o, sh, EL0, ER0)
    val["determinism_bitwise"] = bool(
        c2["g2"] == a["g2"] and c2["raw"] == a["raw"])
    loS = (lo0p[0] + 3, lo0p[1] - 2)
    roS = (ro_m[0] + 3, ro_m[1] - 2)
    oS, shS = sc.union_canvas(lf0["image_shape"], loS, rf0["image_shape"], [roS])
    tS = sc.score_step(lf0, rf0, loS, roS, oS, shS, EL0, ER0)
    val["cotranslation_rel_diff"] = (
        abs(tS["g2"] - a["g2"]) / max(a["g2"], 1e-300))
    bar1 = bar_image()
    Fb1 = mf.multiscale_glyph_fields(
        bar1, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
        v1_banks=s2_banks, kernels=s2_kernels)
    FbH = mf.multiscale_glyph_fields(
        0.5 * bar1, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
        v1_banks=s2_banks, kernels=s2_kernels)
    sup_agree = float(np.mean(Fb1["supported"] == FbH["supported"]))
    EL1 = sc.self_energy(Fb1, "notebook")
    ELH = sc.self_energy(FbH, "notebook")
    o, sh = sc.union_canvas(Fb1["image_shape"], (0, 0),
                            Fb1["image_shape"], [(0, 0)])
    g1 = sc.score_step(Fb1, Fb1, (0, 0), (0, 0), o, sh, EL1, EL1)["g2"]
    gh = sc.score_step(FbH, FbH, (0, 0), (0, 0), o, sh, ELH, ELH)["g2"]
    val["contrast_support_agree"] = sup_agree
    val["contrast_g2_ratio_half_over_full"] = gh / max(g1, 1e-300)
    try:
        bad = sc.resolve_strength("bogus")
        val["variant_rejects_invalid"] = False
    except ValueError:
        val["variant_rejects_invalid"] = True
    ELm = sc.self_energy(lf0, "manuscript")
    val["a1_E_differs"] = bool(not np.array_equal(ELm, EL0))
    e1 = energy.energy(("stage2", l0), lf0, "notebook")
    e2 = energy.energy(("stage2", l0), lf0, "notebook")
    val["energy_cache_stable"] = bool(np.array_equal(e1, e2))
    report["validation"] = val
    phase["validation_seconds"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    strat = {}
    glyphs_r16 = sorted({ord(c) for p in FOCUS + HELDOUT for c in p
                         if ord(c) in ds0["cells"]})
    for cp in glyphs_r16:
        img, _ = glyph_cover(ds0, cp)
        ff = yf.oriented_fields_for_image(img, yf.DEFAULT_PARAMS, s1_bank,
                                          s1_kernels)
        fd = yf.oriented_fields_for_image(img, yf.DEFAULT_PARAMS, s1_bank,
                                          s1_kernels, method="direct")
        both = ff["supported"] & fd["supported"]
        with np.errstate(invalid="ignore"):
            dd = np.abs(ff["distance"][both] - fd["distance"][both])
        well = (np.minimum(ff["U2"][both], fd["U2"][both]) > 1e-9) \
            if np.any(both) else np.array([], dtype=bool)
        strat["U+%04X" % cp] = {
            "max_abs_d_well": float(np.nanmax(dd[well])) if np.any(well) else 0.0,
            "support_agree": float(np.mean(ff["supported"] == fd["supported"]))}
    other_names = [n for n in datasets if n != "roboto-16-mono"]
    for name in other_names:
        ds, _ = datasets[name]
        img, _ = glyph_cover(ds, ord("m") if ord("m") in ds["cells"]
                             else sorted(ds["cells"])[0])
        ff = yf.oriented_fields_for_image(img, yf.DEFAULT_PARAMS, s1_bank,
                                          s1_kernels)
        fd = yf.oriented_fields_for_image(img, yf.DEFAULT_PARAMS, s1_bank,
                                          s1_kernels, method="direct")
        strat[name + "_sample_support_agree"] = float(
            np.mean(ff["supported"] == fd["supported"]))
    s2names = ["roboto-16-mono", "literata-16-mono"]
    for name in s2names:
        ds, _ = datasets[name]
        for cp in [ord("u"), ord("m")]:
            if cp not in ds["cells"]:
                continue
            img, _ = glyph_cover(ds, cp)
            ff = mf.multiscale_glyph_fields(
                img, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
                v1_banks=s2_banks, kernels=s2_kernels)
            fd = mf.multiscale_glyph_fields(
                img, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
                v1_banks=s2_banks, kernels=s2_kernels, method="direct")
            strat["%s_stage2_U+%04X_support_agree" % (name, cp)] = float(
                np.mean(ff["supported"] == fd["supported"]))
    report["stratified_direct_fft"] = strat
    report["stratified_limits"] = (
        "direct-vs-FFT on stage-1 roboto-16-mono full repertoire + one glyph "
        "per other capture, stage-2 on u/m x mono16; remaining fields FFT-only")
    phase["stratified_seconds"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    padchk = {}
    for name, pair in (("roboto-16-mono", "um"), ("literata-16-gray", "AV")):
        ds, _ = datasets[name]
        l, r = ord(pair[0]), ord(pair[1])
        metric = v1.metric_step(ds, l, r)
        lc, lo0 = glyph_cover(ds, l)
        rc, ro0 = glyph_cover(ds, r)
        lf = mf.multiscale_glyph_fields(
            lc, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
            v1_banks=s2_banks, kernels=s2_kernels)
        rf = mf.multiscale_glyph_fields(
            rc, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
            v1_banks=s2_banks, kernels=s2_kernels)
        lfP = mf.multiscale_glyph_fields(
            lc, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
            v1_banks=s2_banks, kernels=s2_kernels,
            pad=int(lf["pad"]) + 8)
        rfP = mf.multiscale_glyph_fields(
            rc, weights=tuple(mf.DEFAULT_PARAMS.scale_weights),
            v1_banks=s2_banks, kernels=s2_kernels,
            pad=int(rf["pad"]) + 8)
        lo = (float(lo0[0]) - int(lf["pad"]), float(lo0[1]) - int(lf["pad"]))
        ro_b = (float(ro0[0]) - int(rf["pad"]), float(ro0[1]) - int(rf["pad"]))
        loP = (float(lo0[0]) - int(lfP["pad"]), float(lo0[1]) - int(lfP["pad"]))
        roP_b = (float(ro0[0]) - int(rfP["pad"]), float(ro0[1]) - int(rfP["pad"]))
        EL = sc.self_energy(lf, "notebook")
        ER = sc.self_energy(rf, "notebook")
        ELP = sc.self_energy(lfP, "notebook")
        ERP = sc.self_energy(rfP, "notebook")
        diffs = []
        for d in DELTAS_NARROW:
            step = metric + d
            if v1.contact_counts(ds["cells"][l], ds["cells"][r], step)[0] > 0:
                continue
            ro = (ro_b[0] + step, ro_b[1])
            roP = (roP_b[0] + step, roP_b[1])
            o, sh = sc.union_canvas(lf["image_shape"], lo, rf["image_shape"], [ro])
            oP, shP = sc.union_canvas(lfP["image_shape"], loP,
                                      rfP["image_shape"], [roP])
            a = sc.score_step(lf, rf, lo, ro, o, sh, EL, ER)["g2"]
            b = sc.score_step(lfP, rfP, loP, roP, oP, shP, ELP, ERP)["g2"]
            diffs.append(abs(a - b) / max(a, 1e-300))
        padchk["%s_%s_max_rel" % (name, pair)] = max(diffs) if diffs else None
    report["pad_stability"] = padchk
    invchk = {}
    for name, pair in (("roboto-16-mono", "um"), ("roboto-16-mono", "AV"),
                       ("literata-24-gray", "To")):
        case = report["cases"][name][pair]
        steps = [s for s in case["steps"] if s.get("valid")
                 and s["delta"] in DELTAS_NARROW]
        invchk["%s_%s_shared_steps" % (name, pair)] = len(steps)
    report["union_invariance_note"] = (
        "fixed union over +-6 is embedding-only (summand exactly 0 outside "
        "both-supported pixels); shared-step values agree with a +-2-only "
        "union within 1e-12 relative (reduction order, not bitwise); "
        "sample counts above")
    phase["stability_seconds"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    J = {}
    for cstar in sc.CSTAR_GRID:
        tot = 0.0
        cover = 0
        n = 0
        for cap in report["cases"].values():
            for case in cap.values():
                if not isinstance(case, dict) or not case.get("narrow_g2"):
                    continue
                g2n = case["narrow_g2"]
                tot += min(abs(g - cstar) for g in g2n)
                if min(g2n) <= cstar <= max(g2n):
                    cover += 1
                n += 1
        J[str(cstar)] = {"objective_sum_min_dev": tot, "coverage": cover,
                         "n_cases": n}
    report["cstar"]["global_objective"] = J
    jvals = [(v["objective_sum_min_dev"], float(k)) for k, v in J.items()]
    jmin = min(j for j, _ in jvals)
    jtol = 1e-9 * max(1.0, jmin)
    cands = sorted(k for j, k in jvals if j <= jmin + jtol)
    report["cstar"]["global_min"] = jmin
    report["cstar"]["tie_candidates"] = cands
    report["cstar"]["tie_proposal_lowest"] = min(cands)
    report["cstar"]["target_default"] = None
    report["cstar"]["note"] = ("baseline-only comparison proposal, never an "
                               "optical anchor; no fitting to metrics")
    phase["cstar_seconds"] = time.perf_counter() - t0

    phase["total_seconds"] = time.perf_counter() - t_start
    phase["ru_maxrss_end"] = rss_now()
    phase["platform"] = sys.platform
    phase["ru_maxrss_unit"] = ("bytes" if sys.platform == "darwin"
                               else "KiB" if sys.platform.startswith("linux")
                               else "platform-dependent")
    _, trace_peak = tracemalloc.get_traced_memory()
    phase["tracemalloc_peak_B"] = trace_peak
    tracemalloc.stop()
    report["timings"] = phase
    (outdir / "report.json").write_text(json.dumps(report, indent=1))
    prov = {
        "score_module_sha256": sha256_file(
            Path(__file__).resolve().parent / "yinyang_oriented_score.py"),
        "evidence_module_sha256": sha256_file(Path(__file__).resolve()),
        "field_stage1_sha256": yf.IMPLEMENTATION_SHA256,
        "field_stage2_sha256": mf.IMPLEMENTATION_SHA256,
        "field_stage2_model": mf.MODEL_IDENTITY,
        "b2_sha256": sha256_file(
            Path(__file__).resolve().parent / "yinyangfit_interactive_b2.py"),
        "stage_provenance": stage_prov.get("implementation_sha256"),
        "params": {"tau": sc.TAU_PX, "q": 2.0, "kappa": 4.0,
                   "n_directed": 16, "cstar_grid": list(sc.CSTAR_GRID)},
        "repo_head": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=str(repo)).stdout.strip(),
        "oracle_leaf": "score-oracle/ frozen; compared only after freezing",
    }
    (outdir / "provenance.json").write_text(json.dumps(prov, indent=1))
    print("cases=64 synthetics=1 validation=1 cstar_grid=%d seconds=%.1f" % (
        len(sc.CSTAR_GRID), phase["total_seconds"]))
    print("uncertainty=uncertainty_not_certified floor>=1pc_is_hypothesis_flag")


if __name__ == "__main__":
    if "--rss-probe" in sys.argv:
        rss_probe_mode()
    else:
        main()
