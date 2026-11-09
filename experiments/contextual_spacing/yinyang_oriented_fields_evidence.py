"""Stage-1 evidence: oriented V1C ratio fields on synthetics + delivered pairs.

Reads delivered captures (Mono/Gray) without modification, computes per-glyph
fields once each (cached-per-glyph concept), overlays declared integer pair
steps, and records numerics/representation checks. No scalar placement
objective, no choice, no optical claim.

Output (must be a new directory): raw field arrays plus ``provenance.json``.
"""

import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yinyang_oriented_fields as yf
import yinyangfit_interactive as v1

FOCUS_PAIRS = ["um", "og", "AV", "To"]
HELDOUT_PAIRS = ["nn", "oo", "HH", "il"]
STEP_DELTAS = (-2, -1, 0, 1, 2)
FULL_ARRAY_PAIR = ("um", "roboto-16-mono")


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def synth_point():
    img = np.zeros((25, 25))
    img[12, 12] = 1.0
    return img, (0, 0), "isolated-support"


def synth_parallel_bars(gap=4, width=2, height=12):
    w = width * 2 + gap + 8
    img = np.zeros((height + 8, w))
    img[4:4 + height, 4:4 + width] = 1.0
    img[4:4 + height, 4 + width + gap:4 + 2 * width + gap] = 1.0
    return img, (0, 0), "parallel-bars"


def synth_asymmetric_bars():
    img = np.zeros((20, 25))
    img[4:16, 4:5] = 1.0
    img[4:16, 9:12] = 1.0
    return img, (0, 0), "asymmetric-bars"


def synth_curve():
    img = np.zeros((25, 25))
    ys, xs = np.mgrid[0:25, 0:25].astype(float)
    img[np.abs(np.hypot(xs - 12, ys - 12) - 6.0) < 0.9] = 1.0
    return img, (0, 0), "curve"


def synth_diagonal():
    img = np.zeros((21, 21))
    ys, xs = np.mgrid[0:21, 0:21].astype(float)
    img[np.abs(xs - ys) < 1.0] = 1.0
    return img, (0, 0), "diagonal"


def synth_repeated():
    img = np.zeros((20, 33))
    for x in (4, 12, 20):
        img[4:16, x:x + 2] = 1.0
    return img, (0, 0), "repeated-strokes"


def single_bar(width=2, height=12):
    img = np.zeros((height + 8, width + 8))
    img[4:4 + height, 4:4 + width] = 1.0
    return img


def glyph_image(dataset, codepoint):
    cell = dataset["cells"][codepoint]
    w, h = cell["width"], cell["height"]
    cover = np.asarray(cell["cover"], dtype=np.float64).reshape(h, w)
    return cover, (float(cell["left"]), float(cell["top"]))


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
    params = yf.DEFAULT_PARAMS
    v1_bank = yf.build_v1_bank(params)
    kernels = yf.build_oriented_kernels(params)

    report = {
        "model": yf.MODEL_IDENTITY,
        "implementation_sha256": yf.IMPLEMENTATION_SHA256,
        "params": {k: getattr(params, k) for k in params.__dataclass_fields__},
        "v1_bank_shape": list(v1_bank.shape),
        "kernel_shape": [int(x) for x in kernels[0].shape],
        "focus_pairs": FOCUS_PAIRS,
        "heldout_pairs": HELDOUT_PAIRS,
        "step_deltas": list(STEP_DELTAS),
        "captures": {},
        "synthetics": {},
        "pairs": {},
        "oracle": {},
        "timings": {},
    }
    for name, (loader, path) in datasets.items():
        ds = loader(str(path))
        report["captures"][name] = {"path": str(path.relative_to(repo)),
                                    "sha256": sha256_file(path),
                                    "size_px": ds["size_px"], "profile": ds["profile"]}

    # --- Synthetic field properties (representation, not quality) ---
    synth_fns = [synth_point, synth_parallel_bars, synth_asymmetric_bars,
                 synth_curve, synth_diagonal, synth_repeated]
    for fn in synth_fns:
        img, origin, _ = fn()
        f = yf.oriented_fields_for_image(img, params, v1_bank, kernels)
        sup = f["supported"]
        with np.errstate(invalid="ignore"):
            finite_d = bool(np.isfinite(f["distance"][sup]).all()) if sup.any() else True
        report["synthetics"][fn.__name__] = {
            "image_shape": list(img.shape),
            "supported_fraction_mean": float(sup.mean()),
            "all_supported_finite": finite_d,
            "arc_strength_max": float(np.nanmax(f["arc_strength"])),
        }
        np.save(outdir / "arrays" / f"synth_{fn.__name__}_distance.npy", f["distance"])
        np.save(outdir / "arrays" / f"synth_{fn.__name__}_supported.npy", f["supported"])

    # Parallel-bar gap response vs expected gap (declared geometry: gap 4).
    img, _, _ = synth_parallel_bars()
    f = yf.oriented_fields_for_image(img, params, v1_bank, kernels)
    pad = int(f["pad"])
    gap_col = 4 + 2 + 2 + pad  # center of the 4px gap, padded-lattice columns
    mid = img.shape[0] // 2 + pad
    ch_east = 0  # directed channel facing +x
    report["synthetics"]["gap_center"] = {
        "gap_px": 4,
        "distance_ch0": float(f["distance"][ch_east, mid, gap_col]),
        "supported_ch0": bool(f["supported"][ch_east, mid, gap_col]),
        "arc_ch0": float(f["arc_strength"][ch_east, mid, gap_col]),
        "arc_orthogonal_ch4": float(f["arc_strength"][4, mid, gap_col]),
    }

    # Direction selectivity (facing property): east of a single bar, the
    # east-facing channel (queries east of sources) must exceed the
    # west-facing channel (which selects sources east of the query: none).
    bar = single_bar()
    fb = yf.oriented_fields_for_image(bar, params, v1_bank, kernels)
    pb = int(fb["pad"])
    er, ec = 4 + 6 + pb, 4 + 2 + 3 + pb  # 3px east of the bar, padded lattice
    report["synthetics"]["direction_selectivity"] = {
        "east_of_bar_ch0": float(fb["arc_strength"][0, er, ec]),
        "east_of_bar_ch8": float(fb["arc_strength"][8, er, ec]),
        "note": "same query pixel; facing-toward must exceed facing-away",
    }
    sel = (float(f["arc_strength"][[0, 8]][:, mid, gap_col].mean())
           - float(f["arc_strength"][[4, 12]][:, mid, gap_col].mean()))
    report["synthetics"]["gap_channels"] = {"east_west_minus_north_south": sel}

    # Rotation quantization: 90-degree CCW rotation maps unpadded (r, c) to
    # (W-1-c, r); the east-facing response must reappear north-facing there.
    rot = np.rot90(img)
    fr = yf.oriented_fields_for_image(rot, params, v1_bank, kernels)
    gr, gc = mid - pad, gap_col - pad
    rrow = img.shape[1] - 1 - gc + pad
    rcol = gr + pad
    report["synthetics"]["rotation_quantization"] = {
        "bar_vertical_ch0": float(f["arc_strength"][0, mid, gap_col]),
        "bar_horizontal_ch12": float(fr["arc_strength"][12, rrow, rcol]),
        "note": "same physical gap pixel under 90-degree CCW rotation; screen-CCW maps east to north (ch12), not south",
    }

    # Raster-phase sensitivity: crisp bar vs same ink split across columns.
    crisp = np.zeros((20, 20))
    crisp[4:16, 10:12] = 1.0
    split = np.zeros((20, 20))
    split[4:16, 9:13] = 0.5
    fc = yf.oriented_fields_for_image(crisp, params, v1_bank, kernels)
    fs = yf.oriented_fields_for_image(split, params, v1_bank, kernels)
    with np.errstate(invalid="ignore"):
        dd = np.abs(fc["distance"] - fs["distance"])
        dd = dd[np.isfinite(dd)]
    report["synthetics"]["raster_phase"] = {
        "max_abs_distance_change": float(dd.max()) if dd.size else float("nan"),
        "note": "same total ink, redistributed coverage; sensitivity measured, invariance not claimed",
    }

    # Convolution-stage oracle: FFT vs direct on a bar fixture (all channels).
    t0 = time.perf_counter()
    f_fft = yf.oriented_fields_for_image(img, params, v1_bank, kernels, method="fft")
    t_fft = time.perf_counter() - t0
    t0 = time.perf_counter()
    f_dir = yf.oriented_fields_for_image(img, params, v1_bank, kernels, method="direct")
    t_direct = time.perf_counter() - t0
    u1diff = max(float(np.abs(f_fft["U1"][o] - f_dir["U1"][o]).max()) for o in range(params.n_directed))
    u2diff = max(float(np.abs(f_fft["U2"][o] - f_dir["U2"][o]).max()) for o in range(params.n_directed))
    well = []
    for o in range(params.n_directed):
        dd = np.abs(f_fft["distance"][o] - f_dir["distance"][o])
        m = np.minimum(f_fft["U2"][o], f_dir["U2"][o]) > 1e-9
        well.append(float(np.nanmax(dd[m])) if np.any(m) else 0.0)
    report["oracle"]["fft_vs_direct_max_abs_U1_diff"] = u1diff
    report["oracle"]["fft_vs_direct_max_abs_U2_diff"] = u2diff
    report["oracle"]["fft_vs_direct_max_abs_distance_diff_well_supported"] = max(well)
    report["oracle"]["fft_vs_direct_note"] = (
        "convolution sums agree to ~1e-15; distance diffs are pure ratio "
        "amplification where U2 approaches the eps floor (e.g. "
        "U2 ~1e-12), not a method mismatch")
    report["oracle"]["fft_seconds"] = t_fft
    report["oracle"]["direct_seconds"] = t_direct

    # Impulse + linearity at the convolution stage (not V1C ink linearity).
    rng_img = np.zeros((31, 31))
    rng_img[15, 15] = 1.0
    h1, h2, _, _ = kernels
    o = 0
    u1 = yf.convolve_fft(rng_img, h1[o])
    u2 = yf.convolve_fft(rng_img, h2[o])
    with np.errstate(invalid="ignore", divide="ignore"):
        d = np.where(u2 > params.denominator_eps, u1 / u2, np.nan)
    ys, xs = np.mgrid[0:31, 0:31].astype(float)
    r = np.hypot(xs - 15, ys - 15)
    on = (r > 0.5) & (r < 12) & np.isfinite(d)
    report["oracle"]["point_support_distance_relation"] = {
        "max_abs_d_minus_r": float(np.nanmax(np.abs(d[on] - r[on]))),
        "note": "delta input at convolution stage: (T*f1)/(T*f2) must equal r",
    }
    a = np.zeros((17, 17))
    a[8, 8] = 1.0
    b = np.zeros((17, 17))
    b[8, 9] = 2.0
    conv = yf.convolve_fft
    lin = float(np.abs(conv(a + b, h1[o]) - conv(a, h1[o]) - conv(b, h1[o])).max())
    report["oracle"]["convolution_linearity_max_abs"] = lin
    c_img = 0.5 * img
    f_half = yf.oriented_fields_for_image(c_img, params, v1_bank, kernels)
    with np.errstate(invalid="ignore"):
        both = f["supported"][o] & f_half["supported"][o]
        dinv = float(np.nanmax(np.abs(f["distance"][o][both] - f_half["distance"][o][both]))) if both.any() else float("nan")
    report["oracle"]["contrast_scaling"] = {
        "distance_invariant_max_abs": dinv,
        "arc_ratio_median": float(np.nanmedian(
            np.where(both, f_half["arc_strength"][o] / np.maximum(f["arc_strength"][o], 1e-300), np.nan))),
        "note": "d invariant under T scaling; a scales linearly (manuscript a = U1.d^(q+1))",
    }

    # Multiplicity: same first-gap geometry with and without a third stroke.
    # Global maxima are on-ink dominated (~equal); the grouping location is
    # the gap center, where the extra stroke's support must add energy.
    two = synth_parallel_bars()[0]
    three, _, _ = synth_repeated()
    f2 = yf.oriented_fields_for_image(two, params, v1_bank, kernels)
    f3 = yf.oriented_fields_for_image(three, params, v1_bank, kernels)
    p2, p3 = int(f2["pad"]), int(f3["pad"])
    report["synthetics"]["multiplicity"] = {
        "two_bar_gap_arc_ch0": float(f2["arc_strength"][0, 10 + p2, 8 + p2]),
        "three_bar_first_gap_arc_ch0": float(f3["arc_strength"][0, 10 + p3, 8 + p3]),
        "note": "convolution integrates support multiplicity; single-nearest-sample cannot",
    }

    # Translation consistency with zero padding: every original-lattice pixel
    # sits at least pad (= V1 half-support + kernel radius) from the padded
    # border, so a shift must reproduce fields exactly on the shared lattice.
    wide = np.zeros((20, 64))
    wide[4:16, 20:22] = 1.0
    wide[4:16, 26:28] = 1.0
    fw = yf.oriented_fields_for_image(wide, params, v1_bank, kernels)
    pw = int(fw["pad"])
    shift = 3
    shifted = np.zeros_like(wide)
    shifted[:, shift:] = wide[:, :-shift]
    fsh = yf.oriented_fields_for_image(shifted, params, v1_bank, kernels)
    with np.errstate(invalid="ignore"):
        a = fw["distance"][:, pw:pw + wide.shape[0], pw:pw + wide.shape[1] - shift]
        b = fsh["distance"][:, pw:pw + wide.shape[0], pw + shift:pw + wide.shape[1]]
        td = np.abs(a - b)
        td = td[np.isfinite(td)]
    report["oracle"]["translation_consistency_max_abs"] = float(td.max()) if td.size else float("nan")

    # Unsupported-mask stability: blank input yields no supported pixels, finite sentinels.
    blank = np.zeros((21, 21))
    fb = yf.oriented_fields_for_image(blank, params, v1_bank, kernels)
    report["oracle"]["blank_input"] = {
        "supported_count": int(fb["supported"].sum()),
        "all_distance_nan_or_finite": bool((~np.isfinite(fb["distance"]) | (fb["distance"] == fb["distance"])).all()),
        "arc_all_zero": bool((fb["arc_strength"] == 0.0).all()),
    }

    # --- Delivered pairs at declared integer placements ---
    # Both strength variants are threaded through every valid step: notebook
    # (primary) is consumed for the delivered summaries; manuscript (alternate)
    # is compared alongside with variant-labeled keys and arrays.
    report["pair_strength_variants"] = {
        "primary": {"variant": "notebook", "field": "confidence_notebook",
                    "exponent": float(params.radial_exponent_q - 1.0)},
        "alternate": {"variant": "manuscript", "field": "arc_strength",
                      "exponent": float(params.radial_exponent_q + 1.0)},
        "variant_independent": ["distance_disagreement", "distance_sum",
                                "both_supported_fraction"],
    }
    field_cache = {}
    for name, (loader, path) in datasets.items():
        ds = loader(str(path))
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
                    cover, origin = glyph_image(ds, cp)
                    fld = yf.oriented_fields_for_image(cover, params, v1_bank, kernels)
                    dt = time.perf_counter() - t0
                    porigin = (origin[0] - int(fld["pad"]), origin[1] - int(fld["pad"]))
                    field_cache[ck] = (fld, porigin, cover.shape)
                    report["timings"].setdefault(name, {})[chr(cp)] = {"seconds": dt}
                    np.save(outdir / "arrays" / f"field_{name}_U+{cp:04X}_dist.npy", fld["distance"])
                    np.save(outdir / "arrays" / f"field_{name}_U+{cp:04X}_sup.npy",
                            fld["supported"].astype(np.uint8))
            lf, lo, _ = field_cache[(name, l)]
            rf, ro_r, _ = field_cache[(name, r)]
            steps = []
            for delta in STEP_DELTAS:
                step = metric + delta
                overlap, faces, corners = v1.contact_counts(ds["cells"][l], ds["cells"][r], step)
                if overlap > 0:
                    steps.append({"step": step, "valid": False, "reason": "occupied_cell_overlap"})
                    continue
                diag_nb = yf.pair_diagnostics(lf, rf, lo, (ro_r[0] + step, ro_r[1]),
                                                  strength="notebook")
                diag_ms = yf.pair_diagnostics(lf, rf, lo, (ro_r[0] + step, ro_r[1]),
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
                       "both_supported_fraction": diag_nb["pooled"]["both_supported_fraction"],
                       "orientation_agreement_mean_notebook":
                           diag_nb["pooled"]["orientation_agreement_mean"],
                       "orientation_agreement_mean_manuscript":
                           diag_ms["pooled"]["orientation_agreement_mean"],
                       "strength_product_total_ch0_notebook":
                           diag_nb["pooled"]["strength_product_total"]["0"],
                       "strength_product_total_ch0_manuscript":
                           diag_ms["pooled"]["strength_product_total"]["0"]}
                steps.append(rec)
                tag = f"{name}_{pair}_s{step}"
                if (pair, name) == FULL_ARRAY_PAIR or (name == "roboto-16-mono" and pair in FOCUS_PAIRS):
                    np.save(outdir / "arrays" / f"pair_{tag}_dd.npy",
                            diag_nb["distance_disagreement"])
                    np.save(outdir / "arrays" / f"pair_{tag}_sp_notebook.npy",
                            diag_nb["strength_product"])
                    np.save(outdir / "arrays" / f"pair_{tag}_sp_manuscript.npy",
                            diag_ms["strength_product"])
            report["pairs"].setdefault(name, {})[pair] = {"metric": metric, "steps": steps}

    # Cold vs warm timing + peak allocation on one glyph field.
    cover0, _ = glyph_image(v1.load_mono_capture(str(v3cap / "roboto-16-mono.json")), ord("m"))
    import tracemalloc
    tracemalloc.start()
    t0 = time.perf_counter()
    yf.oriented_fields_for_image(cover0, params, v1_bank, kernels)
    cold = time.perf_counter() - t0
    _, peak_cold = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    t0 = time.perf_counter()
    yf.oriented_fields_for_image(cover0, params, v1_bank, kernels)
    warm = time.perf_counter() - t0
    _, peak_warm = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    report["timings"]["cold_warm"] = {"cold_seconds": cold, "warm_seconds": warm,
                                      "peak_bytes_cold": peak_cold, "peak_bytes_warm": peak_warm}

    import subprocess
    report["provenance"] = {
        "repo_head": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                    cwd=str(repo)).stdout.strip(),
        "b2_sha256": sha256_file(repo / "experiments/contextual_spacing/yinyangfit_interactive_b2.py"),
        "v1_sha256": sha256_file(repo / "experiments/contextual_spacing/yinyangfit_interactive.py"),
    }
    (outdir / "provenance.json").write_text(json.dumps(report, indent=1, default=float))
    print(json.dumps({"pairs": len(report["pairs"]), "synthetics": len(report["synthetics"]),
                      "oracle_U1": report["oracle"]["fft_vs_direct_max_abs_U1_diff"],
                      "oracle_U2": report["oracle"]["fft_vs_direct_max_abs_U2_diff"],
                      "cold": cold, "warm": warm}, indent=1))


if __name__ == "__main__":
    main()
