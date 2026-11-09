"""Electric Bubble full-field reproduction (isolated computational experiment).

Question: does replacing the nearest-occupied-sample proxy with the author's
full-support field mechanism remove or reduce bumpy distance responses and
associated skipped/reversing placements? A correct reproduction that still
fails is a successful negative result.

Source: pinned snapshot out/diagnostics/contextual-spacing/yinyang-
alternatives/electricbubble (31ce15a). src/App.js builds ink/whitespace
saliency by SAME convolution, raises combined saliency to power 22,
convolves with the inverse-power electricBubbleKernel, applies the
initialStrength/distDecay nonlinear transform with Number.MIN_VALUE and 50
clips, and derives gradients by [1,-1] SAME convolutions. src/kernels.js
builds the oriented DOG/Gaussian saliency kernels and the 1/r^power bubble
kernel. src/autofit.js scores overlap windows with equidistance,
angle-difference and mean-angle attention (yFactors parsed but never
applied) and walks integer overlap toward desiredInteraction (80 attempts,
0.001 tolerance, no convergence guarantee).

Arm A (proxy): the FROZEN experiments/contextual_spacing/
yinyangfit_interactive.py scorer, imported unchanged.
Arm B (source): this module's port of the construction above, driven at the
author's verbatim numeric defaults. Independently anchored by
out/diagnostics/contextual-spacing/electricbubble-fullfield/js-anchor/
which executes the byte-identical sources under pinned tfjs 0.15.3.
No representation-only arm was run. The multistage source-vs-proxy
comparison does not isolate support representation as a single variable.

Compatibility adapters (explicit, recorded in run manifests):
- Input: delivered Mono (exact 0/1) or Gray (exact p/7) cells replace the
  author's 72 px canvas render. Each glyph canvas keeps the author's 2 px
  slack plus padWidth zeros per side; canvas height is the union of the
  comparison set's physical rows (author: fixed boxHeight). Bearings,
  baselines and advances are preserved; no pixel is scaled or thresholded.
- TF SAME cross-correlation uses pad_before=(K-1)//2, pad_after=(K-1)-
  pad_before per axis (matches tfjs for even kernels; verified against the
  anchor convProbe). tf.conv2d correlates; symmetric kernels hide this but
  the gradient kernels do not, so correlation (not convolution) is used.
- tf.pow with integer-valued exponent follows std::pow semantics (negative
  base yields positive); numpy needs an explicit branch, recorded below.
- Python round() is banker's rounding; the walk uses js_round (floor(x+.5))
  to match Math.round, including the -0-falsy update branch.
- tfjs computes in float32, so Number.MIN_VALUE floors to 0 there. The port
  computes in float64 (floor stays 5e-324); a separately named float32
  diagnostic reruns the pipeline and records divergences. Nonfinite and
  zero fields are retained and reported, never silently repaired.
"""

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "contextual_spacing"))
import yinyangfit_interactive as YI  # noqa: E402  (frozen proxy, arm A)

MODEL_IDENTITY = "electricbubble-fullfield-v1"
EXPERIMENT = Path(__file__).stem

# Author verbatim defaults (App.js constructor, lines 27-56).
AUTHOR_DEFAULTS = {
    "inkSaliency": {"filterSize": 20, "patchSizeX": 75.0, "patchSizeY": 12.0,
                    "valleyPeakRatio": 6.2, "valleyGain": 0.5, "angle": 0.0,
                    "gain": 0.26, "bias": 0.76},
    "whitespaceSaliency": {"filterSize": 20, "patchSizeX": 0.01,
                           "patchSizeY": 27.0, "angle": 1.5708, "gain": 0.2},
    "electricBubble": {"filterSize": 60, "power": 22.0,
                       "initialStrength": 1.0, "distDecay": 2.0},
    "angleDifferenceCoefficient": 6.9,
    "meanAngleCoefficient": 3.8,
    "equidistImportance": 4.7,
    "desiredInteraction": 0.01,
    "yFactors": "1.0, 0.5, 1.0, 0.0",
}
# Adapter geometry: padWidth zeros per side (author: round(ascender/2) of a
# 72 px render). Predetermined 64 px contains the 60 px bubble support so gap
# fields see full context; recorded, never tuned per pair.
ADAPTER_PAD_WIDTH = 64
# Walk constants (autofit.js:7-12,25).
WALK_MAX_ATTEMPTS = 80
WALK_TOLERANCE = 0.001
# Clips (App.js:229-230). 5e-324 underflows to 0 in float32 (author runtime).
MIN_CLIP = 5e-324  # Number.MIN_VALUE
MAX_CLIP = 50.0


def _parse_yfactors(text):
    # autofit.js:23 parses but never applies; preserved (parse checked).
    return [float(p.strip()) for p in text.split(",")]


Y_FACTORS = _parse_yfactors(AUTHOR_DEFAULTS["yFactors"])


# ---------------------------------------------------------------- kernels
# Exact transcription of src/kernels.js. hfs uses filterSize/2 (NOT -0.5)
# for Gaussians and filterSize/2-0.5 for the bubble kernel; dist==0 maps to
# 1 via `|| 1` (kernels.js:58). Only even filter sizes occur in defaults.

def _rotation_matrix(angle):
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, -s], [s, c]], dtype=np.float64)


def _unscaled_gaussian(filter_size, cov, rot):
    sigma = rot @ cov @ rot.T
    det = sigma[0, 0] * sigma[1, 1] - sigma[0, 1] * sigma[1, 0]
    inv = np.array([[sigma[1, 1], -sigma[0, 1]],
                    [-sigma[1, 0], sigma[0, 0]]]) / det
    sa, sb, sc, sd = inv[0, 0], inv[0, 1], inv[1, 0], inv[1, 1]
    out = np.zeros((filter_size, filter_size), dtype=np.float64)
    hfs = filter_size / 2
    for y in range(filter_size):
        for x in range(filter_size):
            dx, dy = x - hfs, y - hfs
            out[y, x] = math.exp(-(dx * (dx * sa + dy * sc)
                                   + dy * (dx * sb + dy * sd)))
    return out


def oriented_dog(p):
    rot = _rotation_matrix(p["angle"])
    peak = _unscaled_gaussian(p["filterSize"],
                             np.array([[p["patchSizeX"], 0.0],
                                       [0.0, p["patchSizeY"]]]), rot)
    valley = _unscaled_gaussian(
        p["filterSize"], np.array(
            [[p["patchSizeX"] * p["valleyPeakRatio"], 0.0],
             [0.0, p["patchSizeY"] * p["valleyPeakRatio"]]]), rot)
    envelope = _unscaled_gaussian(
        p["filterSize"], np.array([[p["patchSizeX"] / 2, 0.0],
                                   [0.0, 1000 * p["filterSize"]]]), rot)
    return (peak - valley * p["valleyGain"]) * envelope * p["gain"]


def oriented_gaussian(p):
    rot = _rotation_matrix(p["angle"])
    return _unscaled_gaussian(
        p["filterSize"], np.array([[p["patchSizeX"], 0.0],
                                   [0.0, p["patchSizeY"]]]), rot) * p["gain"]


def electric_bubble_kernel(p):
    fs = p["filterSize"]
    out = np.zeros((fs, fs), dtype=np.float64)
    hfs = fs / 2 - 0.5
    halfpower = p["power"] / 2
    for y in range(fs):
        for x in range(fs):
            dx, dy = x - hfs, y - hfs
            dist = (dx * dx + dy * dy) or 1.0
            out[y, x] = 1.0 / (dist ** halfpower)
    return out


def author_kernels_for_conv():
    # App.js:120-153 applies tf.transpose to each builder output before
    # conv2d. The transpose is material (ink DOG covariances are
    # anisotropic), so the correlation kernel is K.T, verified in parity.
    return {"inkSaliency": oriented_dog(
                AUTHOR_DEFAULTS["inkSaliency"]).T,
            "whitespaceSaliency": oriented_gaussian(
                AUTHOR_DEFAULTS["whitespaceSaliency"]).T,
            "electricBubble": electric_bubble_kernel(
                AUTHOR_DEFAULTS["electricBubble"]).T}


# ------------------------------------------------------- SAME correlation
# tf.conv2d with stride 1, SAME: total pad K-1 split pad_before=(K-1)//2,
# pad_after=(K-1)-pad_before (asymmetric for even K). Correlation, no flip.

def same_correlate(image, kernel):
    # Exact direct correlation. An FFT path was rejected: the saliency^22
    # convolution reaches ~1e19, where float64 FFT roundoff (~1e3 absolute)
    # swamps true far-field outputs (~1e-27). Direct summation keeps small
    # outputs accurate; sizes here (<= 200x200 vs <= 60x60) stay affordable.
    image = np.asarray(image, dtype=np.float64)
    kernel = np.asarray(kernel, dtype=np.float64)
    pads = [((k - 1) // 2, (k - 1) - (k - 1) // 2) for k in kernel.shape]
    padded = np.pad(image, pads, mode="constant")
    view = np.lib.stride_tricks.sliding_window_view(padded, kernel.shape)
    return np.tensordot(view, kernel, axes=2)


def direct_correlate(image, kernel):
    # Reference implementation for parity tests (no FFT).
    image = np.asarray(image, dtype=np.float64)
    kernel = np.asarray(kernel, dtype=np.float64)
    pads = [((k - 1) // 2, (k - 1) - (k - 1) // 2) for k in kernel.shape]
    padded = np.pad(image, pads, mode="constant")
    out = np.zeros_like(image, dtype=np.float64)
    kh, kw = kernel.shape
    for y in range(image.shape[0]):
        for x in range(image.shape[1]):
            out[y, x] = np.sum(padded[y:y + kh, x:x + kw] * kernel)
    return out


def js_round(x):
    # Math.round: half up, with -0 falsy in the walk update branch.
    return int(math.floor(float(x) + 0.5))


def tf_pow_int22(x):
    # tf.pow semantics for integer-valued exponent: negative bases stay
    # positive (std::pow). numpy float power yields NaN there instead.
    x = np.asarray(x, dtype=np.float64)
    ax = np.abs(x) ** 22.0
    return np.where(x >= 0, x ** 22.0, ax)


# ------------------------------------------------------------- field pipe
# App.js:179-254. Per-glyph bubble + gradient fields from the padded raw
# image. runConv returns [ebc, gx, gy]; gx/gy use [1,-1] SAME correlations.

def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=np.float64)))


class GlyphFields:
    """Full-support author fields for one padded glyph image (arm B)."""

    def __init__(self, raw, kernels, dtype=np.float64):
        raw = np.asarray(raw, dtype=dtype)
        self.raw = raw
        self.dtype = dtype
        self.diag = {}
        with np.errstate(all="ignore"):
            ink = np.maximum(0.0, AUTHOR_DEFAULTS["inkSaliency"]["bias"]
                             + same_correlate(raw, kernels["inkSaliency"]))
            ink = ink * raw  # App.js:180 relu after bias, masked by raw
            ws = same_correlate(raw, kernels["whitespaceSaliency"])
            total = ink + ws
            self.diag["total_saliency_min"] = float(np.min(total))
            self.diag["neg_saliency_frac"] = float(np.mean(total < 0))
            powered = tf_pow_int22(total)
            conv = same_correlate(powered, kernels["electricBubble"])
            floored = np.maximum(MIN_CLIP if dtype == np.float64 else 0.0,
                                 conv)
            self.diag["floor_hits"] = int(np.sum(
                conv <= (MIN_CLIP if dtype == np.float64 else 0.0)))
            inner = np.power(floored, -1.0 / AUTHOR_DEFAULTS[
                "electricBubble"]["power"])
            capped = np.minimum(MAX_CLIP, inner)
            self.diag["cap_hits"] = int(np.sum(inner >= MAX_CLIP))
            bubble4 = (AUTHOR_DEFAULTS["electricBubble"]["initialStrength"]
                       / np.power(capped, AUTHOR_DEFAULTS[
                           "electricBubble"]["distDecay"]))
            bubble = np.asarray(bubble4, dtype=dtype).reshape(raw.shape)
            gx = same_correlate(bubble4, np.array([[1.0, -1.0]]))
            gy = same_correlate(bubble4, np.array([[1.0], [-1.0]]))
            self.ink, self.ws = ink, ws
            self.bubble = np.asarray(bubble, dtype=dtype)
            self.dx = np.asarray(gx.reshape(raw.shape), dtype=dtype)
            self.dy = np.asarray(gy.reshape(raw.shape), dtype=dtype)
            self.diag["nonfinite_bubble"] = int(np.sum(~np.isfinite(
                self.bubble)))
            self.diag["nonfinite_grad"] = int(np.sum(~np.isfinite(
                self.dx)) + np.sum(~np.isfinite(self.dy)))


# ------------------------------------------------------- attention + score
# autofit.js:26-67. Overlap o takes the last o columns of the left field
# and the first o columns of the right field; heights must match.

def score_at_overlap(left, right, overlap):
    p = AUTHOR_DEFAULTS
    w1 = left.bubble.shape[1]
    rb = left.bubble[:, w1 - overlap:]
    lb = right.bubble[:, :overlap]
    rdx = left.dx[:, w1 - overlap:]
    rdy = left.dy[:, w1 - overlap:]
    ldx = right.dx[:, :overlap]
    ldy = right.dy[:, :overlap]
    with np.errstate(all="ignore"):
        avg = (lb + rb) / 2.0
        # 0/0 where both bubbles vanish: source divides too; record below.
        with np.errstate(invalid="ignore", divide="ignore"):
            rel = (lb - rb) ** 2 / (avg ** 2)
        equidist = np.exp(-p["equidistImportance"] * rel)
        num = -((ldy * rdy) + (rdx * ldx))
        den = np.sqrt((rdx ** 2 + rdy ** 2) * (ldx ** 2 + ldy ** 2)
                      + 1e-21)
        cos = num / den
        angle_diff = _sigmoid((cos - 1.0) * p["angleDifferenceCoefficient"])
        ty = rdy - ldy
        tx = rdx - ldx
        sine = np.abs(ty) / np.sqrt(tx ** 2 + ty ** 2 + 1e-21)
        mean_angle = 1.0 + p["meanAngleCoefficient"] * sine
        attention = equidist * angle_diff * mean_angle
        product = attention * (rb + lb)  # tf.pow(..., 1.0) is identity
        denom = float(np.sum(attention))
        numer = float(np.sum(product))
    mean = numer / denom if denom != 0 else float("nan")
    return {"overlap": overlap, "meanInteraction": float(mean),
            "attentionSum": denom, "attentionNumer": numer,
            "zero_rel_frac": float(np.mean(~np.isfinite(rel))),
            "finite": bool(math.isfinite(mean) and math.isfinite(denom)
                           and denom > 0)}


def initial_overlap(w1, w2, pad_width):
    # autofit.js:7,11. maxAttempts/overlap seeding; bubble1 used twice (sic).
    border = js_round(max(1.0, pad_width
                          - AUTHOR_DEFAULTS["electricBubble"]["filterSize"]
                          / 2 - 2))
    return js_round(min(max(1, border + 5) + 30, w1 * 0.8, w2 * 0.8))


def walk_search(left, right, pad_width):
    # autofit.js:25-80 verbatim, including the duplicated bubble1 bound and
    # the `Math.round(grad) || sign` update. Returns raw upstream outputs.
    w1 = left.bubble.shape[1]
    target = AUTHOR_DEFAULTS["desiredInteraction"]
    overlap = initial_overlap(w1, right.bubble.shape[1], pad_width)
    trace = []
    terminal = None
    for attempt in range(WALK_MAX_ATTEMPTS):
        if not (overlap < w1 * 0.9 and overlap < w1 * 0.9
                and overlap >= 1 and overlap < 2 * pad_width):
            terminal = {"status": "bound_exit", "attempt": attempt,
                        "overlap": overlap}
            break
        if overlap > min(w1, right.bubble.shape[1]):
            terminal = {"status": "slice_out_of_range", "attempt": attempt,
                        "overlap": overlap}
            break
        s = score_at_overlap(left, right, overlap)
        trace.append({"attempt": attempt, "overlap": overlap,
                      "meanInteraction": s["meanInteraction"],
                      "attentionSum": s["attentionSum"], "finite": s["finite"]})
        if (s["finite"] and abs(s["meanInteraction"] - target)
                < WALK_TOLERANCE) or attempt == WALK_MAX_ATTEMPTS - 1:
            terminal = {"status": "tolerance_or_attempts",
                        "attempt": attempt, "overlap": overlap}
            break
        grad = s["meanInteraction"] - target
        # Math.round(NaN)=NaN (falsy -> sign branch); Math.round(+/-Inf) is
        # truthy infinite, driving overlap infinite before the bound exit.
        if math.isnan(grad):
            step = -1
        elif math.isinf(grad):
            step = grad
        else:
            step = js_round(grad)
            if step == 0:
                step = 1 if grad > 0 else -1
        overlap -= step
        if (attempt == WALK_MAX_ATTEMPTS - 1 or overlap >= w1 * 0.9
                or overlap >= w1 * 0.9 or overlap < 1
                or overlap >= 2 * pad_width):
            terminal = {"status": "quit_pending", "attempt": attempt,
                        "overlap": overlap}
    distance = 2 * pad_width - overlap
    return {"distance": distance, "terminalOverlap": overlap,
            "terminal": terminal, "trace": trace,
            "target": target}


# ------------------------------------------------------- input adapter
# Delivered cells -> author raw layout. Canvas width keeps the author's
# 2 px slack with ink at x=1+pad; height is the union of the set's physical
# rows (author: fixed boxHeight). Cover values are exact 0/1 or p/7.

class GlyphSet:
    def __init__(self, cells, pad_width=ADAPTER_PAD_WIDTH, dtype=np.float64):
        # cells: {key: {"width","height","left","top","cover"[...]}}.
        self.pad = pad_width
        self.dtype = dtype
        ymin = min(c["top"] for c in cells.values())
        ymax = max(c["top"] + c["height"] for c in cells.values())
        self.height = int(ymax - ymin)
        self.y0 = ymin
        self.canvases = {}
        for key, c in cells.items():
            w = c["width"]
            canvas = np.zeros((self.height, w + 2 + 2 * pad_width),
                              dtype=np.float64)
            cover = np.asarray(c["cover"], dtype=np.float64).reshape(
                c["height"], w)
            canvas[int(c["top"] - ymin):int(c["top"] - ymin) + c["height"],
                   1 + pad_width:1 + pad_width + w] = cover
            self.canvases[key] = canvas
        self.keys = list(cells.keys())

    def canvas_width(self, key):
        return self.canvases[key].shape[1]


def build_fields(glyph_set, dtype=np.float64):
    kernels = author_kernels_for_conv()
    return {k: GlyphFields(v, kernels, dtype=dtype)
            for k, v in glyph_set.canvases.items()}, kernels


def overlap_to_step(glyph_set, left_key, left_cell, right_cell, overlap):
    # Canvas-relative step S = W1 - overlap. Canvas x = physical - bearing
    # + const, so S = s + Lr - Ll and s = S + Ll - Lr.
    w1 = glyph_set.canvas_width(left_key)
    return (w1 - overlap) + float(left_cell["left"]) \
        - float(right_cell["left"])


def step_to_overlap(glyph_set, left_key, left_cell, right_cell, step):
    w1 = glyph_set.canvas_width(left_key)
    return w1 - (float(step) - float(left_cell["left"])
                 + float(right_cell["left"]))


# ------------------------------------------------------- datasets + arms

def mono_cells_for_keys(capture_path, keys):
    dataset = YI.load_mono_capture(capture_path)
    return dataset, {k: dataset["cells"][ord(k)] for k in keys}


def gray_cells_for_keys(capture_path, keys):
    dataset = YI.load_gray_capture(capture_path)
    return dataset, {k: dataset["cells"][ord(k)] for k in keys}


def proxy_curve(dataset, left_ch, right_ch, steps, controls=None):
    # Arm A: frozen scorer, called unchanged, exact fixtures/parameters.
    controls = controls or YI.DEFAULT_CONTROLS
    scorer = YI.PairScorer(dataset)
    left, right = ord(left_ch), ord(right_ch)
    curve = []
    for step in steps:
        rec = scorer.score_step(left, right, step, controls)
        curve.append({"step": int(step), "valid": bool(rec["valid"]),
                      "reason": rec.get("reason"),
                      "interaction": rec.get("interaction"),
                      "cost": rec.get("cost")})
    metric = YI.metric_step(dataset, left, right)
    chosen, minimizing, boundary = YI.choose_from_costs(
        [c["step"] for c in curve], [c["cost"] for c in curve],
        [c["valid"] for c in curve], metric)
    return {"arm": "A_proxy", "metric": metric, "curve": curve,
            "chosen": chosen, "minimizing": minimizing,
            "boundary_hit": boundary}


def source_curve(glyph_set, fields, left_key, right_key, left_cell,
                 right_cell, steps):
    # Arm B probe: author interaction at the same physical integer steps.
    curve = []
    for step in steps:
        overlap = step_to_overlap(glyph_set, left_key, left_cell,
                                  right_cell, step)
        oi = int(round(overlap))
        w1 = glyph_set.canvas_width(left_key)
        w2 = glyph_set.canvas_width(right_key)
        if oi < 1 or oi > min(w1, w2):
            curve.append({"step": int(step), "overlap": overlap,
                          "valid": False, "reason": "slice_out_of_range"})
            continue
        s = score_at_overlap(fields[left_key], fields[right_key], oi)
        overlap_flag, _, _ = YI.contact_counts(left_cell, right_cell,
                                               int(step))
        curve.append({"step": int(step), "overlap": oi,
                      "valid": s["finite"], "reason": None if s["finite"]
                      else "nonfinite_score",
                      "interaction": s["meanInteraction"],
                      "attentionSum": s["attentionSum"],
                      "project_overlap_guard": overlap_flag > 0})
    return curve


def choose_by_author_target(curve, require_guard=False):
    # Source-exhaustive selection against the author's declared
    # desiredInteraction (0.01). The project guard variant additionally
    # requires occupied-cell non-overlap; the source walk has no such guard.
    target = AUTHOR_DEFAULTS["desiredInteraction"]
    feas = [c for c in curve if c["valid"] and math.isfinite(
        c.get("interaction", float("nan")))
        and not (require_guard and c.get("project_overlap_guard"))]
    if not feas:
        return {"chosen": None, "minimizing": [], "target": target,
                "guard": require_guard}
    best = min(abs(c["interaction"] - target) for c in feas)
    mini = sorted(c["step"] for c in feas
                  if abs(abs(c["interaction"] - target) - best) < 1e-9)
    return {"chosen": mini[0], "minimizing": mini, "target": target,
            "guard": require_guard}


def compare_pair(glyph_set, fields, dataset, left_ch, right_ch, steps,
                 cell_map):
    left_cell, right_cell = cell_map[left_ch], cell_map[right_ch]
    proxy = proxy_curve(dataset, left_ch, right_ch, steps)
    scurve = source_curve(glyph_set, fields, left_ch, right_ch, left_cell,
                          right_cell, steps)
    walk = walk_search(fields[left_ch], fields[right_ch], glyph_set.pad)
    walk_step = overlap_to_step(glyph_set, left_ch, left_cell, right_cell,
                                walk["terminalOverlap"])
    return {"pair": left_ch + right_ch,
            "proxy": proxy,
            "source_curve": scurve,
            "source_exhaustive": choose_by_author_target(scurve),
            "source_exhaustive_guarded": choose_by_author_target(
                scurve, require_guard=True),
            "source_walk": {**walk, "terminalStep": walk_step}}


# ------------------------------------------------------- anchor exchange

def anchor_cells_payload(cell_map, pairs, overlaps_per_pair, pad_width,
                         conv_probe=None):
    payload = {"padWidth": pad_width,
               "glyphs": {k: {"width": c["width"], "height": c["height"],
                              "left": float(c["left"]), "top": float(c["top"]),
                              "cover": [float(v) for v in c["cover"]]}
                          for k, c in cell_map.items()},
               "pairs": pairs, "curveOverlaps": overlaps_per_pair}
    if conv_probe is not None:
        payload["convProbe"] = conv_probe
    return payload


def manifest(out_dir, extra):
    sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    info = {"model": MODEL_IDENTITY, "port_sha256": sha,
            "proxy_sha256": YI.IMPLEMENTATION_SHA256,
            "proxy_identity": YI.MODEL_IDENTITY,
            "author_defaults": AUTHOR_DEFAULTS,
            "adapter_pad_width": ADAPTER_PAD_WIDTH,
            "head": "240b372bc96027c60d286ef0b7113c4656a40609"}
    info.update(extra)
    Path(out_dir, "manifest.json").write_text(json.dumps(info, indent=2)
                                              + "\n")
    return info


def _cmd_kernels(args):
    kernels = author_kernels_for_conv()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dump = {k: {"shape": list(v.shape), "data": v.reshape(-1).tolist()}
            for k, v in kernels.items()}
    (out / "kernels.json").write_text(json.dumps(dump))
    direct = electric_bubble_kernel(AUTHOR_DEFAULTS["electricBubble"])
    (out / "bubble_direct.json").write_text(json.dumps(
        {"shape": list(direct.shape), "data": direct.reshape(-1).tolist()}))
    print(f"wrote {out}/kernels.json")


def _cmd_cells(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    keys = list(args.chars)
    if args.profile == "mono":
        dataset, cell_map = mono_cells_for_keys(args.capture, keys)
    else:
        dataset, cell_map = gray_cells_for_keys(args.capture, keys)
    glyph_set = GlyphSet(cell_map)
    pairs = [[a, b] for a, b in zip(keys[::2], keys[1::2])]
    overlaps = []
    for a, b in pairs:
        metric = YI.metric_step(dataset, ord(a), ord(b))
        steps = list(range(metric - 8, metric + 9))
        overlaps.append([int(step_to_overlap(
            glyph_set, a, cell_map[a], cell_map[b], s)) for s in steps])
    payload = anchor_cells_payload(cell_map, pairs, overlaps,
                                   ADAPTER_PAD_WIDTH)
    (out / "cells.json").write_text(json.dumps(payload))
    manifest(out, {"command": "cells", "capture": args.capture,
                   "profile": args.profile, "chars": keys})
    print(f"wrote {out}/cells.json")


def _cmd_compare(args):
    import tracemalloc
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    keys = list(args.chars)
    dtype = np.float32 if args.dtype == "float32" else np.float64
    if args.profile == "mono":
        dataset, cell_map = mono_cells_for_keys(args.capture, keys)
    else:
        dataset, cell_map = gray_cells_for_keys(args.capture, keys)
    tracemalloc.start()
    t0 = time.perf_counter()
    glyph_set = GlyphSet(cell_map)
    fields, _ = build_fields(glyph_set, dtype=dtype)
    cold = time.perf_counter() - t0
    _, traced_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    results = []
    t1 = time.perf_counter()
    for a, b in zip(keys[::2], keys[1::2]):
        metric = YI.metric_step(dataset, ord(a), ord(b))
        steps = list(range(metric - 8, metric + 9))
        results.append(compare_pair(glyph_set, fields, dataset, a, b,
                                    steps, cell_map))
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
                                         "max_rss": rss},
         "dtype": args.dtype}, indent=1))
    manifest(out, {"command": "compare", "capture": args.capture,
                   "profile": args.profile, "chars": keys,
                   "dtype": args.dtype})
    print(f"wrote {out}/comparison.json "
          f"(cold {cold:.1f}s, warm {warm:.1f}s)")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="electricbubble_fullfield")
    sub = ap.add_subparsers(required=True)
    k = sub.add_parser("kernels")
    k.add_argument("out")
    k.set_defaults(fn=_cmd_kernels)
    c = sub.add_parser("cells")
    c.add_argument("out")
    c.add_argument("--capture", required=True)
    c.add_argument("--profile", choices=["mono", "gray"], default="mono")
    c.add_argument("--chars", required=True)
    c.set_defaults(fn=_cmd_cells)
    m = sub.add_parser("compare")
    m.add_argument("out")
    m.add_argument("--capture", required=True)
    m.add_argument("--profile", choices=["mono", "gray"], default="mono")
    m.add_argument("--chars", required=True)
    m.add_argument("--dtype", choices=["float64", "float32"],
                   default="float64")
    m.set_defaults(fn=_cmd_compare)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
