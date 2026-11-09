"""Stage-2 evidence: multiscale direct-path V1C fields on synthetics + pairs.

Reads delivered captures (Mono/Gray) without modification, computes
per-glyph multiscale fields once each (cached-per-glyph concept), overlays
declared integer pair steps, and records the falsifiable gates from the
owning design section "YinYang multiscale field stage". No scalar placement
objective, no choice, no optical claim. B2 interaction is reported
alongside as a diagnostic only (different model; no score parity asserted).

Output (must be a new directory): raw field arrays plus ``provenance.json``.
"""

import hashlib
import json
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yinyang_multiscale_fields as mf
import yinyang_oriented_fields as yf
import yinyang_oriented_fields_evidence as ev
import yinyangfit_interactive as v1
import yinyangfit_interactive_b2 as b2

FOCUS_PAIRS = ["um", "og", "AV", "To"]
HELDOUT_PAIRS = ["nn", "oo", "HH", "il"]
STEP_DELTAS = (-2, -1, 0, 1, 2)
FULL_ARRAY_PAIR = ("um", "roboto-16-mono")
WELL = 1e-6


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    outdir = Path(sys.argv[1])
    if outdir.exists():
        raise SystemExit(f"refusing to reuse output directory: {outdir}")
    (outdir / "arrays").mkdir(parents=True)

    repo = Path(__file__).resolve().parents[2]
    v3cap = repo / "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/captures"
    c24 = repo / "out/diagnostics/contextual-spacing/yinyangfit-interactive/captures24"
    datasets = {
        "roboto-16-mono": (v1.load_mono_capture, v3cap / "roboto-16-mono.json"),
        "literata-16-mono": (v1.load_mono_capture, v3cap / "literata-16-mono.json"),
        "roboto-24-mono": (v1.load_mono_capture, c24 / "Roboto-24-mono.json"),
        "literata-24-mono": (v1.load_mono_capture, c24 / "Literata-24-mono.json"),
        "roboto-16-gray": (v1.load_gray_capture, v3cap / "roboto-16-gray.json"),
        "literata-16-gray": (v1.load_gray_capture, v3cap / "literata-16-gray.json"),
        "roboto-24-gray": (v1.load_gray_capture, c24 / "Roboto-24-gray.json"),
        "literata-24-gray": (v1.load_gray_capture, c24 / "Literata-24-gray.json"),
    }
    params = mf.DEFAULT_PARAMS
    s1 = yf.DEFAULT_PARAMS
    banks, halfwidths = mf.build_multiscale_v1_bank(params)
    bank1 = yf.build_v1_bank(s1)
    kernels = yf.build_oriented_kernels(s1)

    report = {
        "model": mf.MODEL_IDENTITY,
        "implementation_sha256": mf.IMPLEMENTATION_SHA256,
        "stage1_implementation_sha256": yf.IMPLEMENTATION_SHA256,
        "params": {"scale_sigmas_px": list(params.scale_sigmas_px),
                   "scale_weights": list(params.scale_weights),
                   "n_v1_orientations": params.n_v1_orientations,
                   "n_directed": params.n_directed,
                   "stage1": {k: getattr(s1, k) for k in s1.__dataclass_fields__}},
        "per_scale_gains": mf.per_scale_gains([np.asarray(b) for b in banks]),
        "per_scale_halfwidths": list(halfwidths),
        "stage_pad": int(mf.stage_pad_multiscale(params)),
        "focus_pairs": FOCUS_PAIRS,
        "heldout_pairs": HELDOUT_PAIRS,
        "step_deltas": list(STEP_DELTAS),
        "captures": {},
        "synthetics": {},
        "pairs": {},
        "b2_diagnostic": {},
        "gates": {},
        "timings": {},
    }
    for name, (loader, path) in datasets.items():
        ds = loader(str(path))
        report["captures"][name] = {"path": str(path.relative_to(repo)),
                                    "sha256": sha256_file(path),
                                    "size_px": ds["size_px"], "profile": ds["profile"]}

    # --- Gate G3: per-scale gains recorded, fine-scale dominance disclosed ---
    peaks = [g["impulse_response_peak"]
             for g in report["per_scale_gains"]]
    report["gates"]["gains_recorded_fine_dominant"] = {
        "impulse_peaks": peaks,
        "fine_gt_coarse": bool(peaks[0] > peaks[-1]),
        "note": ("uniform weights emphasize fine scales by peak gain; "
                 "disclosed, not corrected")}

    # --- Synthetics: finite values where supported, explicit unsupported ---
    synth_fns = [ev.synth_point, ev.synth_parallel_bars,
                 ev.synth_asymmetric_bars, ev.synth_curve,
                 ev.synth_diagonal, ev.synth_repeated]
    for fn in synth_fns:
        img, _, _ = fn()
        f = mf.multiscale_glyph_fields(img, params, banks, kernels)
        sup = f["supported"]
        with np.errstate(invalid="ignore"):
            finite_d = bool(np.isfinite(f["distance"][sup]).all()) if sup.any() else True
        report["synthetics"][fn.__name__] = {
            "image_shape": list(img.shape),
            "supported_fraction_mean": float(sup.mean()),
            "all_supported_finite": finite_d,
            "primary_conf_max": float(np.nanmax(f["confidence_notebook"])),
        }
        np.save(outdir / "arrays" / f"synth_{fn.__name__}_distance.npy",
                f["distance"])
        np.save(outdir / "arrays" / f"synth_{fn.__name__}_supported.npy",
                f["supported"].astype(np.uint8))

    # --- Gate G2: weighted sum matches an independent recompute ---
    img, _, _ = ev.synth_parallel_bars()
    f0 = mf.multiscale_glyph_fields(img, params, banks, kernels)
    want = np.tensordot(np.asarray(params.scale_weights, dtype=np.float64),
                        f0["C_per_scale"], axes=(0, 0))
    report["gates"]["weighted_sum_independent"] = {
        "max_abs_diff_vs_tensordot": float(
            np.abs(f0["T_combined"] - want).max())}

    # --- Gate G1: single-active-center reproduces stage 1 (real glyph) ---
    ds_m = v1.load_mono_capture(
        str(v3cap / "roboto-16-mono.json"))
    cover_m, origin_m = ev.glyph_image(ds_m, ord("m"))
    fs1 = yf.oriented_fields_for_image(cover_m, s1, bank1, kernels)
    fsc = mf.multiscale_glyph_fields(cover_m, params, banks, kernels,
                                     weights=(0.0, 0.0, 1.0, 0.0, 0.0))
    pa, pb = int(fs1["pad"]), int(fsc["pad"])
    lat = lambda f, p: (f["U1"][:, p:p + cover_m.shape[0], p:p + cover_m.shape[1]],
                        f["distance"][:, p:p + cover_m.shape[0], p:p + cover_m.shape[1]],
                        f["supported"][:, p:p + cover_m.shape[0], p:p + cover_m.shape[1]])
    U1a, da, sa = lat(fs1, pa)
    U1b, db, sb = lat(fsc, pb)
    with np.errstate(invalid="ignore"):
        both = sa & sb
        report["gates"]["single_scale_limit"] = {
            "max_abs_U1_diff": float(np.abs(U1a - U1b).max()),
            "max_abs_d_diff": float(np.nanmax(np.abs(da - db)[both])),
            "support_agreement": float((sa == sb).mean())}

    # --- Padding convergence + co-translation (multiscale) ---
    wide = np.zeros((20, 64))
    wide[4:16, 20:22] = 1.0
    wide[4:16, 26:28] = 1.0
    fw = mf.multiscale_glyph_fields(wide, params, banks, kernels)
    pw = int(fw["pad"])
    fc = mf.multiscale_glyph_fields(wide, params, banks, kernels, pad=pw + 8)
    with np.errstate(invalid="ignore"):
        dd = np.abs(fw["distance"][:, pw:pw + 20, pw:pw + 64]
                    - fc["distance"][:, pw + 8:pw + 8 + 20, pw + 8:pw + 8 + 64])
        report["gates"]["padding_convergence"] = {
            "max_abs_d_diff": float(np.nanmax(dd[np.isfinite(dd)]))}
    shift = 3
    shifted = np.zeros_like(wide)
    shifted[:, shift:] = wide[:, :-shift]
    fsh = mf.multiscale_glyph_fields(shifted, params, banks, kernels)
    with np.errstate(invalid="ignore"):
        a = fw["distance"][:, pw:pw + 20, pw:pw + 64 - shift]
        b = fsh["distance"][:, pw:pw + 20, pw + shift:pw + 64]
        td = np.abs(a - b)
        report["gates"]["cotranslation_consistency"] = {
            "max_abs_d_diff": float(np.nanmax(td[np.isfinite(td)]))}

    # --- Fractional-phase sensitivity (measured, not invariant) ---
    crisp = np.zeros((20, 20))
    crisp[4:16, 10:12] = 1.0
    split = np.zeros((20, 20))
    split[4:16, 9:13] = 0.5
    fcr = mf.multiscale_glyph_fields(crisp, params, banks, kernels)
    fsp = mf.multiscale_glyph_fields(split, params, banks, kernels)
    with np.errstate(invalid="ignore"):
        both = (fcr["supported"][0] & fsp["supported"][0]
                & (np.minimum(fcr["U2"][0], fsp["U2"][0]) > WELL))
        report["gates"]["fractional_phase"] = {
            "max_abs_distance_change_well_supported":
                float(np.abs(fcr["distance"][0][both]
                             - fsp["distance"][0][both]).max())
                if both.any() else float("nan"),
            "note": ("same total ink, redistributed coverage; sensitivity "
                     "measured, invariance not claimed")}

    # --- Contrast gain: Gray vs Mono on u/m (d invariant, strength scales) ---
    # Mono and Gray captures differ by fringe columns; compare on the
    # ink-coordinate overlap (tops/heights match; lefts are integral).
    ds_g = v1.load_gray_capture(str(v3cap / "roboto-16-gray.json"))
    cg = {}
    for cp in (ord("u"), ord("m")):
        cm, gm = ds_m["cells"][cp], ds_g["cells"][cp]
        assert float(cm["top"]) == float(gm["top"])
        assert cm["height"] == gm["height"]
        assert float(cm["left"]).is_integer() and float(gm["left"]).is_integer()
        cov_m, _ = ev.glyph_image(ds_m, cp)
        cov_g, _ = ev.glyph_image(ds_g, cp)
        fm = mf.multiscale_glyph_fields(cov_m, params, banks, kernels)
        fg = mf.multiscale_glyph_fields(cov_g, params, banks, kernels)
        pm, pg = int(fm["pad"]), int(fg["pad"])
        x0 = int(max(cm["left"], gm["left"]))
        x1 = int(min(cm["left"] + cm["width"], gm["left"] + gm["width"]))
        sl_m = slice(pm + (x0 - int(cm["left"])), pm + (x1 - int(cm["left"])))
        sl_g = slice(pg + (x0 - int(gm["left"])), pg + (x1 - int(gm["left"])))
        rows = slice(pm, pm + cm["height"])
        with np.errstate(invalid="ignore"):
            dm = fm["distance"][0][rows, sl_m]
            dg = fg["distance"][0][rows, sl_g]
            sm = fm["supported"][0][rows, sl_m]
            sg = fg["supported"][0][rows, sl_g]
            um = fm["U2"][0][rows, sl_m]
            ug = fg["U2"][0][rows, sl_g]
            well = sm & sg & (np.minimum(um, ug) > WELL)
            dinv = float(np.abs(dm[well] - dg[well]).max()) if well.any() else float("nan")
            r = (fg["confidence_notebook"][0][rows, sl_g][well]
                 / np.maximum(fm["confidence_notebook"][0][rows, sl_m][well], 1e-300))
            cg[chr(cp)] = {
                "overlap_cols": [x0, x1],
                "well_supported": int(well.sum()),
                "max_abs_d_diff": dinv,
                "strength_ratio_median": float(np.median(r)) if well.any() else float("nan"),
                "mono_support_frac": float(fm["supported"].mean()),
                "gray_support_frac": float(fg["supported"].mean())}
    report["gates"]["contrast_gain_gray_vs_mono"] = cg

    # --- Delivered pairs at declared integer placements + B2 diagnostic ---
    # Both strength variants are threaded through every valid step: notebook
    # (primary) is consumed for the delivered summaries; manuscript (alternate)
    # is compared alongside with variant-labeled keys and arrays.
    report["pair_strength_variants"] = {
        "primary": {"variant": "notebook", "field": "confidence_notebook",
                    "exponent": float(yf.DEFAULT_PARAMS.radial_exponent_q - 1.0)},
        "alternate": {"variant": "manuscript", "field": "arc_strength",
                      "exponent": float(yf.DEFAULT_PARAMS.radial_exponent_q + 1.0)},
        "variant_independent": ["distance_disagreement", "distance_sum",
                                "both_supported_fraction"],
    }
    scorer_cache = {}
    field_cache = {}
    for name, (loader, path) in datasets.items():
        ds = loader(str(path))
        if name == "roboto-16-mono":
            scorer_cache[name] = b2.PairScorer(ds)
        for pair in FOCUS_PAIRS + HELDOUT_PAIRS:
            l, r = ord(pair[0]), ord(pair[1])
            if l not in ds["cells"] or r not in ds["cells"]:
                report["pairs"].setdefault(name, {})[pair] = {"skipped": "missing glyph"}
                continue
            metric = v1.metric_step(ds, l, r)
            for key, cp in ((l, l), (r, r)):
                ck = (name, cp)
                if ck not in field_cache:
                    t0 = time.perf_counter()
                    cover, origin = ev.glyph_image(ds, cp)
                    fld = mf.multiscale_glyph_fields(cover, params, banks, kernels)
                    dt = time.perf_counter() - t0
                    porigin = (origin[0] - int(fld["pad"]), origin[1] - int(fld["pad"]))
                    field_cache[ck] = (fld, porigin, cover.shape)
                    report["timings"].setdefault(name, {})[chr(cp)] = {"seconds": dt}
                    np.save(outdir / "arrays" / f"field_{name}_U+{cp:04X}_dist.npy",
                            fld["distance"])
                    np.save(outdir / "arrays" / f"field_{name}_U+{cp:04X}_sup.npy",
                            fld["supported"].astype(np.uint8))
            lf, lo, _ = field_cache[(name, l)]
            rf, ro_r, _ = field_cache[(name, r)]
            steps = []
            for delta in STEP_DELTAS:
                step = metric + delta
                overlap, faces, corners = v1.contact_counts(
                    ds["cells"][l], ds["cells"][r], step)
                if overlap > 0:
                    steps.append({"step": step, "valid": False,
                                  "reason": "occupied_cell_overlap"})
                    continue
                diag_nb = mf.pair_diagnostics(lf, rf, lo, (ro_r[0] + step, ro_r[1]), s1,
                                                  strength="notebook")
                diag_ms = mf.pair_diagnostics(lf, rf, lo, (ro_r[0] + step, ro_r[1]), s1,
                                                  strength="manuscript")
                for _key in ("distance_disagreement", "distance_sum"):
                    _a, _b = diag_nb[_key], diag_ms[_key]
                    if not np.array_equal(np.nan_to_num(_a), np.nan_to_num(_b)):
                        raise AssertionError(
                            "variant-independent pair array differs: %s" % _key)
                if not (diag_nb["pooled"]["both_supported_fraction"]
                        == diag_ms["pooled"]["both_supported_fraction"]):
                    raise AssertionError("variant-independent support fraction differs")
                rec = {"step": step, "valid": True, "faces": faces, "corners": corners,
                       "strength_primary": diag_nb["strength_variant"],
                       "strength_alternate": diag_ms["strength_variant"],
                       "both_supported_fraction":
                           diag_nb["pooled"]["both_supported_fraction"],
                       "orientation_agreement_mean_notebook":
                           diag_nb["pooled"]["orientation_agreement_mean"],
                       "orientation_agreement_mean_manuscript":
                           diag_ms["pooled"]["orientation_agreement_mean"],
                       "strength_product_total_ch0_notebook":
                           diag_nb["pooled"]["strength_product_total"]["0"],
                       "strength_product_total_ch0_manuscript":
                           diag_ms["pooled"]["strength_product_total"]["0"]}
                if name in scorer_cache:
                    brec = scorer_cache[name].score_geometry(
                        l, r, step, float(v1.DEFAULT_CONTROLS.feature_scale),
                        float(v1.DEFAULT_CONTROLS.proximity_falloff))
                    bfields = brec.get("fields", {}) if brec.get("valid") else {}
                    report["b2_diagnostic"].setdefault(pair, {})[str(step)] = {
                        "b2_valid": bool(brec.get("valid")),
                        "b2_interaction": brec.get("interaction"),
                        "b2_fields": bfields,
                        "note": ("nearest-sample B2 vs oriented-convolution "
                                 "stage 2; different models, no parity asserted")}
                steps.append(rec)
                tag = f"{name}_{pair}_s{step}"
                if (pair, name) == FULL_ARRAY_PAIR or (
                        name == "roboto-16-mono" and pair in FOCUS_PAIRS):
                    np.save(outdir / "arrays" / f"pair_{tag}_dd.npy",
                            diag_nb["distance_disagreement"])
                    np.save(outdir / "arrays" / f"pair_{tag}_sp_notebook.npy",
                            diag_nb["strength_product"])
                    np.save(outdir / "arrays" / f"pair_{tag}_sp_manuscript.npy",
                            diag_ms["strength_product"])
            report["pairs"].setdefault(name, {})[pair] = {"metric": metric, "steps": steps}

    # --- Determinism (condition-aware) + cold/warm timing on actual work ---
    cover0, _ = ev.glyph_image(ds_m, ord("m"))
    fa = mf.multiscale_glyph_fields(cover0, params, banks, kernels)
    fb = mf.multiscale_glyph_fields(cover0, params, banks, kernels)
    with np.errstate(invalid="ignore"):
        well = (fa["supported"][0] & fb["supported"][0]
                & (np.minimum(fa["U2"][0], fb["U2"][0]) > WELL))
        report["gates"]["determinism"] = {
            "max_abs_C_diff": float(np.abs(fa["C_per_scale"] - fb["C_per_scale"]).max()),
            "max_abs_U_diff": float(max(np.abs(fa["U1"] - fb["U1"]).max(),
                                        np.abs(fa["U2"] - fb["U2"]).max())),
            "max_abs_d_diff_well": float(
                np.abs(fa["distance"][0][well] - fb["distance"][0][well]).max())
            if well.any() else float("nan"),
            "support_agreement": float((fa["supported"] == fb["supported"]).mean())}
    tracemalloc.start()
    t0 = time.perf_counter()
    mf.multiscale_glyph_fields(cover0, params, banks, kernels)
    cold = time.perf_counter() - t0
    _, peak_cold = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    t0 = time.perf_counter()
    mf.multiscale_glyph_fields(cover0, params, banks, kernels)
    warm = time.perf_counter() - t0
    _, peak_warm = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    report["timings"]["cold_warm"] = {"cold_seconds": cold, "warm_seconds": warm,
                                      "peak_bytes_cold": peak_cold,
                                      "peak_bytes_warm": peak_warm}

    import subprocess
    report["provenance"] = {
        "repo_head": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=str(repo)).stdout.strip(),
        "b2_sha256": sha256_file(
            repo / "experiments/contextual_spacing/yinyangfit_interactive_b2.py"),
        "v1_sha256": sha256_file(
            repo / "experiments/contextual_spacing/yinyangfit_interactive.py"),
        "frozen_v1_capture_note": "captures read-only; see captures SHAs",
        "stage1_reconciliation": "out/diagnostics/contextual-spacing/yinyang-oriented-fields/reconciliation/reconciliation.json",
    }
    (outdir / "provenance.json").write_text(json.dumps(report, indent=1, default=float))
    print(json.dumps({"pairs": len(report["pairs"]), "synthetics": len(report["synthetics"]),
                      "g1_U1": report["gates"]["single_scale_limit"]["max_abs_U1_diff"],
                      "g2": report["gates"]["weighted_sum_independent"][
                          "max_abs_diff_vs_tensordot"],
                      "cold": cold, "warm": warm}, indent=1))


if __name__ == "__main__":
    main()
