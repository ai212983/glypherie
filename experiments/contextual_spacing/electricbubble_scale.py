# cspell:words autofit electricbubble fullfield getrusage maxrss nonfinite ppem PPEM retuned reweighting RUSAGE scurve yinyangfit
"""Electric Bubble scale adaptation (isolated computational experiment).

Question: can a single declared parameter-resizing rule improve
scale consistency and the small-raster response behavior without selecting
per-font, per-size or per-pair settings? The owning design subsection
(`docs/designs/text-layout/contextual-spacing-and-healing.md`, Electric
Bubble scale adaptation) states the rule before this code: reference
measurement is the em at the author's 72 px render (App.js `fontSize: 72`,
`scalingFactor = fontSize / unitsPerEm`), ratio r = ppem / 72, lengths scale
by r, explicit patch covariances by r-squared, other constants unchanged.
This is a partial parameter resize, not a complete scale-normalization proof.

Source: pinned snapshot out/diagnostics/contextual-spacing/yinyang-
alternatives/electricbubble (31ce15a); arm B port is the frozen
experiments/contextual_spacing/electricbubble_fullfield.py, imported
unchanged. This module only derives scaled parameters/kernels and the
filterSize-dependent walk seeding; every other formula is the shared code
path. Resizing supports and explicit covariances without quadrature
reweighting is a partial project adaptation, labelled here and tested by the
experiment evidence, not assumed faithful.
"""

import argparse
import copy
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "contextual_spacing"))
import electricbubble_fullfield as F  # noqa: E402 (frozen arm B port)
import yinyangfit_interactive as YI  # noqa: E402 (frozen proxy, arm A)

MODEL_IDENTITY = "electricbubble-scale-v1"
EXPERIMENT = Path(__file__).stem

# Author render size in px per em (App.js constructor state).
REFERENCE_PPEM = 72.0


def scale_ratio(ppem):
    # Declared reference: author em at 72 px. r == 1 must recover the
    # author's verbatim parameters exactly (mechanical identity gate).
    return float(ppem) / REFERENCE_PPEM


def _even_int(value, minimum=4):
    # Nearest even integer keeps the TF-SAME asymmetric-pad and
    # kernel-center conventions the full-field port verified against real
    # tf.conv2d; evenness is a project adapter policy, recorded here.
    return max(minimum, 2 * int(math.floor(float(value) / 2.0 + 0.5)))


def scaled_params(ppem):
    """Author parameters expressed at the delivered measurement.

    Lengths (filterSize supports) scale by r, covariance (variance) entries
    by r-squared; other constants pass through unchanged, including
    desiredInteraction. No complete unit transport is claimed for that
    numeric target (see owning design).
    """
    r = scale_ratio(ppem)
    p = copy.deepcopy(F.AUTHOR_DEFAULTS)
    ink = p["inkSaliency"]
    ink["filterSize"] = _even_int(F.AUTHOR_DEFAULTS["inkSaliency"]
                                  ["filterSize"] * r)
    ink["patchSizeX"] = (F.AUTHOR_DEFAULTS["inkSaliency"]["patchSizeX"]
                         * r * r)
    ink["patchSizeY"] = (F.AUTHOR_DEFAULTS["inkSaliency"]["patchSizeY"]
                         * r * r)
    ws = p["whitespaceSaliency"]
    ws["filterSize"] = _even_int(F.AUTHOR_DEFAULTS["whitespaceSaliency"]
                                 ["filterSize"] * r)
    ws["patchSizeX"] = (F.AUTHOR_DEFAULTS["whitespaceSaliency"]
                        ["patchSizeX"] * r * r)
    ws["patchSizeY"] = (F.AUTHOR_DEFAULTS["whitespaceSaliency"]
                        ["patchSizeY"] * r * r)
    eb = p["electricBubble"]
    eb["filterSize"] = _even_int(F.AUTHOR_DEFAULTS["electricBubble"]
                                 ["filterSize"] * r)
    return p


def scaled_kernels_for_conv(params):
    # Same transpose convention as the full-field port (App.js:120-153):
    # correlation kernels are K.T; material for anisotropic covariances.
    return {"inkSaliency": F.oriented_dog(params["inkSaliency"]).T,
            "whitespaceSaliency": F.oriented_gaussian(
                params["whitespaceSaliency"]).T,
            "electricBubble": F.electric_bubble_kernel(
                params["electricBubble"]).T}


def build_scaled_fields(glyph_set, params, dtype=np.float64):
    kernels = scaled_kernels_for_conv(params)
    return {k: F.GlyphFields(v, kernels, dtype=dtype)
            for k, v in glyph_set.canvases.items()}, kernels


def scaled_initial_overlap(w1, w2, pad_width, params):
    # autofit.js:7,11 seeding with the scaled support in place of the
    # author's verbatim filterSize; the duplicated w1 bound is preserved.
    border = F.js_round(max(1.0, pad_width
                            - params["electricBubble"]["filterSize"]
                            / 2 - 2))
    return F.js_round(min(max(1, border + 5) + 30, w1 * 0.8, w2 * 0.8))


def scaled_walk_search(left, right, pad_width, params):
    # autofit.js:25-80 update rules verbatim; only the seeding support and
    # the (unchanged-value) target source differ from the frozen port.
    # Native gradient kernels are retained. Additive source epsilons mean
    # gradient magnitude factors do not cancel exactly in general.
    w1 = left.bubble.shape[1]
    target = params["desiredInteraction"]
    overlap = scaled_initial_overlap(w1, right.bubble.shape[1], pad_width,
                                     params)
    trace = []
    terminal = None
    for attempt in range(F.WALK_MAX_ATTEMPTS):
        if not (overlap < w1 * 0.9 and overlap < w1 * 0.9
                and overlap >= 1 and overlap < 2 * pad_width):
            terminal = {"status": "bound_exit", "attempt": attempt,
                        "overlap": overlap}
            break
        if overlap > min(w1, right.bubble.shape[1]):
            terminal = {"status": "slice_out_of_range", "attempt": attempt,
                        "overlap": overlap}
            break
        s = F.score_at_overlap(left, right, overlap)
        trace.append({"attempt": attempt, "overlap": overlap,
                      "meanInteraction": s["meanInteraction"],
                      "attentionSum": s["attentionSum"], "finite": s["finite"]})
        if (s["finite"] and abs(s["meanInteraction"] - target)
                < F.WALK_TOLERANCE) or attempt == F.WALK_MAX_ATTEMPTS - 1:
            terminal = {"status": "tolerance_or_attempts",
                        "attempt": attempt, "overlap": overlap}
            break
        grad = s["meanInteraction"] - target
        if math.isnan(grad):
            step = -1
        elif math.isinf(grad):
            step = grad
        else:
            step = F.js_round(grad)
            if step == 0:
                step = 1 if grad > 0 else -1
        overlap -= step
        if (attempt == F.WALK_MAX_ATTEMPTS - 1 or overlap >= w1 * 0.9
                or overlap >= w1 * 0.9 or overlap < 1
                or overlap >= 2 * pad_width):
            terminal = {"status": "quit_pending", "attempt": attempt,
                        "overlap": overlap}
    distance = 2 * pad_width - overlap
    return {"distance": distance, "terminalOverlap": overlap,
            "terminal": terminal, "trace": trace, "target": target}


def compare_scaled(glyph_set, fields, params, dataset, left_ch, right_ch,
                   steps, cell_map):
    # Same physical integer steps, adapter padding and overlap mapping as
    # the raw arm; runs break at invalids (slice bounds, nonfinite score).
    left_cell, right_cell = cell_map[left_ch], cell_map[right_ch]
    scurve = F.source_curve(glyph_set, fields, left_ch, right_ch,
                            left_cell, right_cell, steps)
    walk = scaled_walk_search(fields[left_ch], fields[right_ch],
                              glyph_set.pad, params)
    walk_step = F.overlap_to_step(glyph_set, left_ch, left_cell,
                                  right_cell, walk["terminalOverlap"])
    return {"pair": left_ch + right_ch,
            "source_curve": scurve,
            "source_exhaustive": F.choose_by_author_target(scurve),
            "source_exhaustive_guarded": F.choose_by_author_target(
                scurve, require_guard=True),
            "source_walk": {**walk, "terminalStep": walk_step}}


def manifest(out_dir, extra):
    sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    info = {"model": MODEL_IDENTITY,
            "scale_sha256": sha,
            "port_sha256": hashlib.sha256(
                Path(F.__file__).read_bytes()).hexdigest(),
            "proxy_sha256": YI.IMPLEMENTATION_SHA256,
            "proxy_identity": YI.MODEL_IDENTITY,
            "reference_ppem": REFERENCE_PPEM,
            "adapter_pad_width": F.ADAPTER_PAD_WIDTH,
            "head": "240b372bc96027c60d286ef0b7113c4656a40609"}
    info.update(extra)
    Path(out_dir, "manifest.json").write_text(json.dumps(info, indent=2)
                                              + "\n")
    return info


def _load_cells(args):
    if args.profile == "mono":
        return F.mono_cells_for_keys(args.capture, list(args.chars))
    return F.gray_cells_for_keys(args.capture, list(args.chars))


def _cmd_compare(args):
    import tracemalloc
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dataset, cell_map = _load_cells(args)
    import numpy as _np
    dtype = _np.float32 if args.dtype == "float32" else _np.float64
    ppem = float(dataset.get("size_px", args.size_px or REFERENCE_PPEM))
    params = scaled_params(ppem)
    r = scale_ratio(ppem)
    tracemalloc.start()
    t0 = time.perf_counter()
    glyph_set = F.GlyphSet(cell_map)
    fields, _ = build_scaled_fields(glyph_set, params, dtype=dtype)
    cold = time.perf_counter() - t0
    _, traced_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    keys = list(args.chars)
    results = []
    t1 = time.perf_counter()
    for a, b in zip(keys[::2], keys[1::2]):
        metric = YI.metric_step(dataset, ord(a), ord(b))
        steps = list(range(metric - 8, metric + 9))
        results.append(compare_scaled(glyph_set, fields, params, dataset,
                                      a, b, steps, cell_map))
    warm = time.perf_counter() - t1
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except Exception:
        rss = None
    (out / "comparison.json").write_text(json.dumps(
        {"results": results, "timings": {"cold_prepare_s": cold,
                                         "warm_pairs_s": warm,
                                         "traced_peak_bytes": traced_peak,
                                         "max_rss": rss}}, indent=1))
    manifest(out, {"command": "compare", "capture": args.capture,
                   "profile": args.profile, "chars": keys,
                   "dtype": args.dtype,
                   "ppem": ppem, "scale_ratio": r, "scaled_params": params})
    print(f"wrote {out}/comparison.json (r={r:.4f}, "
          f"cold {cold:.1f}s, warm {warm:.1f}s)")


def _cmd_kernels(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ppem = float(args.size_px)
    params = scaled_params(ppem)
    kernels = scaled_kernels_for_conv(params)
    dump = {k: {"shape": list(v.shape), "data": v.reshape(-1).tolist()}
            for k, v in kernels.items()}
    (out / "kernels.json").write_text(json.dumps(dump))
    manifest(out, {"command": "kernels", "ppem": ppem,
                   "scale_ratio": scale_ratio(ppem),
                   "scaled_params": params})
    print(f"wrote {out}/kernels.json (r={scale_ratio(ppem):.4f})")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="electricbubble_scale")
    sub = ap.add_subparsers(required=True)
    m = sub.add_parser("compare")
    m.add_argument("out")
    m.add_argument("--capture", required=True)
    m.add_argument("--profile", choices=["mono", "gray"], default="mono")
    m.add_argument("--chars", required=True)
    m.add_argument("--size-px", type=float, default=None)
    m.add_argument("--dtype", choices=["float64", "float32"],
                   default="float64")
    m.set_defaults(fn=_cmd_compare)
    k = sub.add_parser("kernels")
    k.add_argument("out")
    k.add_argument("--size-px", type=float, required=True)
    k.set_defaults(fn=_cmd_kernels)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
