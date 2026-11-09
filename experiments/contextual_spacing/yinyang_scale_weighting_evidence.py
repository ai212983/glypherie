"""Scale-weighting evidence: gains, gratings, masking, and corpus trajectories.

Reads frozen captures/stages without modification; writes only the NEW
out/diagnostics/contextual-spacing/yinyang-model-completion/scales/ tree.
No placement promotion, no optical claim, no training, no per-glyph tuning.
Notebook normalization stays a deferred evaluation (host disposition);
this driver implements only the source-grounded scale-weighting probe.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yinyang_scale_weighting as sw
import yinyang_multiscale_fields as mf
import yinyang_oriented_fields as yf
import yinyang_oriented_score as sc
import yinyangfit_interactive as v1

PINNED_NOTEBOOK_SHA256 = "63f7be83b90aad5cc1c29be53197d78bafd14dff7fa84c797345390195198a91"
UPSTREAM_HEAD_STATED = "609d17e8a6446ec4413a1b02a0768b8214d73333"
ENGINE_FIELDS_SHA_STATED = "dcdd7c6d5c635d134d8ee44fc694596a1f065f99fbeb266b5bff04af09a20763"
ENGINE_SCORE_SHA_STATED = "1a7466c6e1d85c06dd911c12c0b41a88bcb9f29ecee2b2c7680c56bfb91d68f0"
MAIN_SHA_STATED = "48cbfd347eaa66f74dc180f0d2e5ff4708594394310df0245b0cfdc1867fe152"

DEV_PAIRS = ("um", "og")
HELDOUT_PAIRS = ("AV", "To", "nn", "oo", "HH", "il")
STEP_DELTAS = (-2, -1, 0, 1, 2)
CSTAR_TARGETS = (4.0, 8.0, 16.0)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# Notebook identity is provenance only: the pinned notebook hash is
# recorded alongside the evidence and never enters scoring. The default
# lives inside the repo so the reference is reproducible on any machine;
# pass an explicit path (argv[2] or YINYANG_PINNED_NOTEBOOK) when the
# notebook is checked out elsewhere. A missing file records None and
# keeps the existing mismatch gate below.
NOTEBOOK_DEFAULT = Path("experiments/contextual_spacing/yinyangfit_pinned.ipynb")


def resolve_notebook_path(explicit=None):
    if explicit:
        return Path(explicit)
    env = os.environ.get("YINYANG_PINNED_NOTEBOOK")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / NOTEBOOK_DEFAULT


def glyph_cover(dataset, codepoint):
    cell = dataset["cells"][codepoint]
    w, h = cell["width"], cell["height"]
    cover = np.asarray(cell["cover"], dtype=np.float64).reshape(h, w)
    return cover, (float(cell["left"]), float(cell["top"]))


def main():
    outdir = Path(sys.argv[1])
    if outdir.exists():
        raise SystemExit("refusing to reuse output directory: %s" % outdir)
    (outdir / "arrays").mkdir(parents=True)
    tracemalloc.start()
    t0 = time.perf_counter()

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

    nb_arg = sys.argv[2] if len(sys.argv) > 2 else None
    nb = resolve_notebook_path(nb_arg)
    nb_sha = sha256_file(nb) if nb.is_file() else None
    fields_sha = sha256_file(
        repo / "experiments/contextual_spacing/oriented_engine/src/fields.rs")
    score_sha = sha256_file(
        repo / "experiments/contextual_spacing/oriented_engine/src/score.rs")
    main_sha = sha256_file(repo / "out/diagnostics/contextual-spacing"
                          "/yinyangfit-interactive-v3/site-reviewed/index.html")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo),
                          capture_output=True, text=True,
                          check=True).stdout.strip()

    params = mf.DEFAULT_PARAMS
    s1 = yf.DEFAULT_PARAMS
    banks, halfwidths = mf.build_multiscale_v1_bank(params)
    bank_list = [np.asarray(b) for b in banks]
    kernels = yf.build_oriented_kernels(s1)
    gains = mf.per_scale_gains(bank_list)
    matched = sw.matched_sine_gains(banks, params.scale_sigmas_px)

    arms = {
        "uniform": tuple(params.scale_weights),
        "gain_compensated_matched": sw.gain_compensated_weights(
            (1.0,) * 5, matched, convention="measured", renormalize="sum"),
        "log_gaussian_study_p1.5_b1.0": sw.log_gaussian_scale_weights(
            params.scale_sigmas_px, peak_sigma_px=1.5, bandwidth_oct=1.0,
            normalize="sum"),
    }

    report = {
        "model": sw.MODEL_IDENTITY,
        "implementation_sha256": sw.IMPLEMENTATION_SHA256,
        "stage2_sha256": mf.IMPLEMENTATION_SHA256,
        "stage1_sha256": yf.IMPLEMENTATION_SHA256,
        "score_sha256": hashlib.sha256(
            (repo / "experiments/contextual_spacing/yinyang_oriented_score.py").read_bytes()).hexdigest(),
        "pinned_notebook_sha256": nb_sha,
        "pinned_notebook_match": bool(nb_sha == PINNED_NOTEBOOK_SHA256),
        "upstream_head_stated": UPSTREAM_HEAD_STATED,
        "engine_fields_sha256": {"stated": ENGINE_FIELDS_SHA_STATED,
                               "measured": fields_sha,
                               "match": bool(fields_sha == ENGINE_FIELDS_SHA_STATED)},
        "engine_score_sha256": {"stated": ENGINE_SCORE_SHA_STATED,
                              "measured": score_sha,
                              "match": bool(score_sha == ENGINE_SCORE_SHA_STATED)},
        "repo_head": head,
        "main_sha_stated": MAIN_SHA_STATED,
        "main_page_sha256": main_sha,
        "main_page_matches_stated": bool(main_sha == MAIN_SHA_STATED),
        "sigmas_px": list(params.scale_sigmas_px),
        "arms": {k: list(v) for k, v in arms.items()},
        "matched_sine_gains": list(matched),
        "per_scale_gains": gains,
        "scale_shares_uniform_bars": None,
        "masking_sweep_bars": {},
        "grating_selectivity": {},
        "fft_direct_agreement": {},
        "splits": {"development": list(DEV_PAIRS), "heldout": list(HELDOUT_PAIRS)},
        "step_deltas": list(STEP_DELTAS),
        "cstar_targets": list(CSTAR_TARGETS),
        "captures": {},
        "cases": {},
        "timings": {},
    }
    if not report["pinned_notebook_match"]:
        raise SystemExit("pinned notebook hash mismatch: %s" % nb_sha)

    # --- Grating study: scale/orientation response, FFT vs direct ---
    periods = (3.0, 6.0, 12.0, 24.0)
    for period in periods:
        for theta_deg in (0.0, 45.0, 90.0):
            img = sw.grating_image(period, float(np.deg2rad(theta_deg)),
                                   (64, 64))
            f = mf.multiscale_glyph_fields(img, params, banks, kernels)
            c = np.asarray(f["C_per_scale"])
            key = "p%.1f_t%.0f" % (period, theta_deg)
            report["grating_selectivity"][key] = {
                "per_scale_peak": [float(c[s].max()) for s in range(5)],
                "coarse_scale_ori_max": [float(c[4][o].max())
                                         for o in range(8)],
            }
    img = sw.grating_image(8.0, 0.0, (32, 32))
    bank0 = np.asarray(banks[2][0])
    a = np.asarray(yf.convolve_fft(img, bank0))
    b = np.asarray(yf.convolve_direct(img, bank0))
    report["fft_direct_agreement"] = {
        "max_abs_mag_diff": float(np.abs(np.abs(a) - np.abs(b)).max())}

    # --- Bars: scale shares under each arm + contrast masking sweep ---
    bars = np.zeros((20, 96))
    bars[4:16, 10:12] = 1.0
    fb = mf.multiscale_glyph_fields(bars, params, banks, kernels)
    report["scale_shares_uniform_bars"] = list(
        sw.scale_shares(np.asarray(fb["C_per_scale"]),
                        tuple(params.scale_weights)))
    for name, w in arms.items():
        fw = mf.multiscale_glyph_fields(bars, params, banks, kernels,
                                        weights=w)
        report.setdefault("scale_shares_bars", {})[name] = list(
            sw.scale_shares(np.asarray(fw["C_per_scale"]), w))
    sup0 = np.asarray(fb["supported"])
    for c in (0.5, 3.0 / 7.0, 0.1, 0.01, 1e-3, 1e-6, 1e-9, 1e-12):
        f = mf.multiscale_glyph_fields(c * bars, params, banks, kernels)
        rep = sw.mask_change(sup0, np.asarray(f["supported"]))
        rep.pop("common")
        report["masking_sweep_bars"]["c=%.1e" % c] = rep

    # --- Corpus: source trajectories per arm, both strengths ---
    field_cache = {}
    pair_cache = {}

    def fields_for(ds_key, codepoint, arm):
        key = (ds_key, codepoint, arm)
        hit = field_cache.get(key)
        if hit is None:
            ds = pair_cache[ds_key][0]
            cover, _ = glyph_cover(ds, codepoint)
            hit = mf.multiscale_glyph_fields(
                cover, params, banks, kernels, weights=arms[arm])
            field_cache[key] = hit
        return hit

    t_fields = time.perf_counter()
    for name, (loader, path) in datasets.items():
        ds = loader(str(path))
        pair_cache[name] = (ds, str(path.relative_to(repo)), sha256_file(path))
        report["captures"][name] = {
            "path": str(path.relative_to(repo)),
            "sha256": pair_cache[name][2],
            "size_px": ds["size_px"], "profile": ds["profile"]}
    report["timings"]["captures_and_banks_s"] = time.perf_counter() - t0

    for name in datasets:
        ds = pair_cache[name][0]
        for pair in DEV_PAIRS + HELDOUT_PAIRS:
            l, r = ord(pair[0]), ord(pair[1])
            if l not in ds["cells"] or r not in ds["cells"]:
                report["cases"].setdefault(name, {})[pair] = {
                    "skipped": "missing glyph"}
                continue
            metric = v1.metric_step(ds, l, r)
            lc, lo0 = glyph_cover(ds, l)
            rc, ro0 = glyph_cover(ds, r)
            case = {"metric": metric, "arms": {}}
            for arm in arms:
                lf = fields_for(name, l, arm)
                rf = fields_for(name, r, arm)
                lo = (float(lo0[0]) - int(lf["pad"]),
                      float(lo0[1]) - int(lf["pad"]))
                ro_base = (float(ro0[0]) - int(rf["pad"]),
                           float(ro0[1]) - int(rf["pad"]))
                ls, rs = lf["image_shape"], rf["image_shape"]
                ros_all = [(ro_base[0] + metric + d, ro_base[1])
                           for d in STEP_DELTAS]
                origin, shape = sc.union_canvas(ls, lo, rs, ros_all)
                # Measured scale contributions at the metric step: mean
                # of the per-glyph share vectors (lattices differ by
                # glyph width, so shares average, not arrays).
                sl = sw.scale_shares(np.asarray(lf["C_per_scale"]),
                                     arms[arm])
                sr = sw.scale_shares(np.asarray(rf["C_per_scale"]),
                                     arms[arm])
                shares = tuple((a + b) / 2.0 for a, b in zip(sl, sr))
                steps = []
                for d in STEP_DELTAS:
                    step = metric + d
                    overlap, faces, corners = v1.contact_counts(
                        ds["cells"][l], ds["cells"][r], step)
                    if overlap > 0:
                        steps.append({"step": step, "delta": d,
                                      "valid": False,
                                      "reason": "occupied_cell_overlap",
                                      "faces": faces, "corners": corners})
                        continue
                    ro = (ro_base[0] + step, ro_base[1])
                    rec = {"step": step, "delta": d, "valid": True,
                           "faces": faces, "corners": corners}
                    for variant in ("notebook", "manuscript"):
                        EL = sc.self_energy(lf, variant)
                        ER = sc.self_energy(rf, variant)
                        s = sc.score_step(lf, rf, lo, ro, origin, shape,
                                          EL, ER, sc.TAU_PX, variant)
                        tag = "g2_" + ("primary"
                                       if variant == "notebook" else "a1")
                        rec[tag] = s["g2"]
                        rec[tag + "_floor_share"] = s["floor_share"]
                        rec[tag + "_both_pairpx"] = s["both_supported_pairpx"]
                        if (variant == "notebook" and s["raw"] == 0.0
                                and s["both_supported_pairpx"] == 0):
                            rec["abstain"] = True
                    steps.append(rec)
                narrow = [s for s in steps if s.get("valid")]
                cstars = {}
                for target in CSTAR_TARGETS:
                    for tag in ("g2_primary", "g2_a1"):
                        vals = [s[tag] for s in narrow if tag in s]
                        if not vals:
                            cstars["%s@%s" % (tag, target)] = None
                            continue
                        devs = [abs(g - target) for g in vals]
                        idx, mstar = sc.tie_set(devs)
                        cstars["%s@%s" % (tag, target)] = {
                            "tie_idx": [int(i) for i in idx],
                            "pick_lowest": int(min(idx)),
                            "mstar": float(mstar)}
                case["arms"][arm] = {"scale_shares_metric": list(shares),
                                     "steps": steps, "cstar": cstars,
                                     "flags": ["uncertainty_not_certified"]}
            report["cases"].setdefault(name, {})[pair] = case
    report["timings"]["fields_and_scores_s"] = time.perf_counter() - t_fields
    report["timings"]["total_s"] = time.perf_counter() - t0
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    report["timings"]["tracemalloc_peak_MiB"] = peak / 2.0 ** 20
    report["timings"]["field_cache_entries"] = len(field_cache)

    (outdir / "report.json").write_text(json.dumps(report, indent=1))
    np.save(outdir / "arrays" / "matched_sine_gains.npy", np.asarray(matched))
    np.save(outdir / "arrays" / "scale_shares_uniform_bars.npy",
            np.asarray(report["scale_shares_uniform_bars"]))
    prov = {
        "driver": Path(__file__).name,
        "splits": report["splits"],
        "arms": report["arms"],
        "hashes": {
            "scale_weighting": sw.IMPLEMENTATION_SHA256,
            "multiscale": mf.IMPLEMENTATION_SHA256,
            "stage1": yf.IMPLEMENTATION_SHA256,
            "pinned_notebook": nb_sha,
            "engine_fields_sha256_match": report["engine_fields_sha256"]["match"],
            "engine_score_sha256_match": report["engine_score_sha256"]["match"],
            "repo_head": head,
        },
        "stops": ["nonfinite_or_negative_weights_raise",
                  "all_zero_yields_explicit_unsupported",
                  "ratio_math_untouched_by_weights",
                  "no_per_glyph_tuning_no_target_fitting_no_training",
                  "no_optical_claim",
                  "notebook_normalization_deferred_per_host_disposition"],
    }
    (outdir / "provenance.json").write_text(json.dumps(prov, indent=1))
    print("wrote %s (%d cases)" % (outdir, sum(
        len(v) for v in report["cases"].values())))


if __name__ == "__main__":
    main()
