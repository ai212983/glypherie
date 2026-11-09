"""Interactive nearest-distance pair-spacing experiment (isolated, no training).

Project hypothesis within YinYangFit feasibility work: a specifically sourced
Electric Bubble-inspired nearest-distance probe, not a reproduction of
YinYangFit's oriented model and not proof of its approach. Every rule below
names its primary foundation; adaptations are labeled HYPOTHESIS.

Borrowed shape, with explicit departures:

- Radial factors ``r^-q`` and ``r^-(q+1)`` with ``q ~= 2`` (direct
  approximation,
  https://skosch.github.io/YinYangFit/#a-direct-approximation-model-of-local-grouping).
  DEPARTURE: radial and orientation-blind here. Upstream uses angularly
  masked oriented convolution kernels whose ratio estimates oriented
  distance, plus multiscale V1C responses and multiple contour supports;
  none of that is implemented. No oriented filtering, no ratio distance
  estimator, no multiscale or multi-contour integration.
- Four same-named pair-field diagnostics (distance disagreement, strength
  product, distance sum, orientation relationship) computed over the
  nearest-distance proxy fields. HYPOTHESIS: they record this probe's
  behavior and do not reproduce the upstream oriented quantities.
- Nearest occupied-sample distance and nearest-sample coverage per query
  point (adapted from Electric Bubble ``autofit.js``, the author's browser
  prototype superseded by YinYangFit; see
  docs/references/yinyang-geometric-alternatives.md). LIMITATIONS, disclosed:
  a single nearest sample ignores support multiplicity and orientation, and
  each background point takes its nearest ink sample's coverage with no
  integration over support.
- Regularized power kernel ``g / (1 + (r / scale)^q)``. HYPOTHESIS: disclosed
  regularization replacing the upstream kernels; finite at ``r = 0``, so no
  singularity treatment is claimed.
- Attention-normalized mean interaction
  ``sum(attention * (leftBubble + rightBubble)) / sum(attention)`` and the
  integer search toward a desired value (Electric Bubble desiredInteraction).
  HYPOTHESIS: using this normalization as the aggregation rule. The JAX
  notebook specifies no scalar reduction; this completion is ours.
- Equidistance and opposing-gradient attention factors (Electric Bubble
  article and ``App.js``/``kernels.js``); vertical-position weighting, which
  upstream parses but does not apply, is omitted here too.
- Single-scale evaluation window (upstream distance-transform alternative
  assumes one dominant grouping scale): acknowledged modeling compromise.
- Coverage mapping: binary masks stay ``0/1``; 3-bit Gray coverage is used
  linearly as delivered (0..7 -> 0..1), without thresholding. Display/assumed
  luminance mapping is documented in the evidence report, not in this module.

Controls (three global knobs; the internal field names stay compatible):

- cohesion: desired attention-weighted interaction, the set-point for the
  integer search (HYPOTHESIS, from Electric Bubble desiredInteraction).
- feature_scale: interaction reach / radial knee in pixels, NOT V1
  feature-scale filter weighting across scales. Larger reach weights
  distant ink more; smaller reach localizes the interaction to the gap.
- proximity_falloff: radial decay exponent shape (``q``). Steeper falloff
  weights near ink more sharply; NOT an independently implemented
  crowding penalty.

Only three global controls are exposed; each demonstrably moves chosen integer
placements (see evidence report). Metric placement from the capture is the
named control and the tie-break reference. Glyph bitmaps are never modified;
only whole-pixel origin steps change. Face/corner contact is permitted;
occupied-cell overlap is forbidden. Fixed-pitch/tabular safeguards from the
owning design apply to any adoption; this module scores eligible pairs only.
"""

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

MODEL_IDENTITY = "yinyangfit-interactive-v1"
IMPLEMENTATION_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

# Two stored exponents borrow only the direct approximation's q / q+1
# pairing in role: bubble fields use q, strength fields use q+1.
# DEPARTURE: no oriented kernels and no ratio distance estimator; the
# pairing shapes two radial fields, nothing more.
SECOND_EXPONENT_OFFSET = 1.0
# Attention is evaluated inside a fixed ink-relative window so transparent
# storage padding cannot change scores (CounterSpace bounds-correction
# precedent, adapted). Padding tests add margin beyond this window.
WINDOW_FACTOR = 6.0
WINDOW_MIN = 4
# Exact ties are unlikely in floating point; candidates within this of the
# minimum form the minimizing set, from which the metric-nearest is chosen.
TIE_TOLERANCE = 1e-9
# Candidate integer deltas around the metric step, mirroring the historical
# five-candidate protocol in count only (offsets, not source distances).
CANDIDATE_DELTAS = (-2, -1, 0, 1, 2)
# Gradient norms below this are treated as neutral orientation (0.5).
GRADIENT_FLOOR = 1e-6


@dataclass(frozen=True)
class YYControls:
    """Three interpretable global parameters (all sources in module docstring).

    Internal field names stay compatible across evidence and page payloads:
    ``feature_scale`` is the interaction reach (radial knee in pixels), not
    V1 feature-scale filter weighting; ``proximity_falloff`` is the radial
    decay exponent shape, not an independent crowding penalty.
    """

    # Desired attention-weighted interaction (Electric Bubble desiredInteraction).
    # Calibrated so the default sits inside the delivered interaction range
    # (about 0.8-1.5 at metric steps for 16 px Mono); it is a starting point,
    # not an optical claim.
    cohesion: float = 1.10
    # Interaction reach in pixels: the radial knee of the regularized power
    # kernel. Not upstream feature-scale filter weighting across scales.
    feature_scale: float = 2.0
    # Radial decay exponent shape (upstream radial factor uses q ~= 2).
    # Not an independently implemented crowding penalty.
    proximity_falloff: float = 2.0

    def __post_init__(self):
        for key in ("cohesion", "feature_scale", "proximity_falloff"):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{key} must be a number")
            if not math.isfinite(float(value)):
                raise ValueError(f"{key} must be finite")
        if not 0.0 <= float(self.cohesion) <= 2.0:
            raise ValueError("cohesion must be in [0, 2]")
        if not 0.5 <= float(self.feature_scale) <= 4.0:
            raise ValueError("feature_scale must be in [0.5, 4.0] pixels")
        if not 1.0 <= float(self.proximity_falloff) <= 3.0:
            raise ValueError("proximity_falloff must be in [1.0, 3.0]")


DEFAULT_CONTROLS = YYControls()
CONTROL_RANGES = {
    "cohesion": (0.0, 2.0),
    "feature_scale": (0.5, 4.0),
    "proximity_falloff": (1.0, 3.0),
}
# Exact precompute grid used for the interactive page (sliders snap to it, so
# every displayed placement is an exactly evaluated setting, never interpolated).
CONTROL_GRID = {
    "cohesion": [0.40, 0.60, 0.80, 1.00, 1.10, 1.20, 1.40, 1.60, 1.80],
    "feature_scale": [1.0, 1.5, 2.0, 3.0],
    "proximity_falloff": [1.0, 1.5, 2.0, 3.0],
}


def settings_identity(controls):
    """Reproducible identity for one evaluated setting."""
    canonical = json.dumps(
        {"model": MODEL_IDENTITY, "implementation": IMPLEMENTATION_SHA256,
         "controls": {"cohesion": float(controls.cohesion),
                      "feature_scale": float(controls.feature_scale),
                      "proximity_falloff": float(controls.proximity_falloff)}},
        sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def pixel_round(value):
    if value >= 0:
        return math.floor(value + 0.5)
    return math.ceil(value - 0.5)


def _mono_cells(glyph):
    bitmap = glyph["bitmap"]
    width, height = bitmap["width"], bitmap["height"]
    pixels = bitmap["pixels"]
    if len(pixels) != width * height:
        raise ValueError("mono bitmap length mismatch")
    cover = [1.0 if p else 0.0 for p in pixels]
    return {"width": width, "height": height, "left": float(bitmap["left"]),
            "top": float(bitmap["top"]), "cover": cover,
            "advance_px": float(glyph["finalized_advance_px"])}


def load_mono_capture(path):
    """Delivered Mono cells with maintained metric steps (full kerning on)."""
    capture = json.loads(Path(path).read_text())
    if capture.get("schema_version") != "contextual-spacing-capture-v1":
        raise ValueError("unsupported mono capture schema")
    cells = {}
    for glyph in capture["glyphs"]:
        cells[glyph["codepoint"]] = _mono_cells(glyph)
    adjustments = {}
    for pair in capture.get("metric_pairs_on", []):
        adjustments[(pair["left"], pair["right"])] = float(pair["adjustment_px"])
    return {"profile": "mono", "size_px": float(capture["size_px"]),
            "source_path": str(path), "cells": cells, "adjustments": adjustments}


def load_gray_capture(path):
    """Delivered 3-bit Gray coverage, linear 0..1 mapping (documented assumption)."""
    capture = json.loads(Path(path).read_text())
    if capture.get("schema_version") not in ("contextual-spacing-grayscale-v1",
                                             "contextual-spacing-grayscale-v2"):
        raise ValueError("unsupported grayscale capture schema")
    font = capture["font"]
    cells = {}
    advances = {}
    for glyph in font["glyphs"]:
        pixels = glyph["pixels"]
        if len(pixels) != glyph["width"] * glyph["height"]:
            raise ValueError("gray bitmap length mismatch")
        cells[glyph["codepoint"]] = {
            "width": glyph["width"], "height": glyph["height"],
            "left": float(glyph["left"]), "top": float(glyph["top"]),
            "cover": [p / 7.0 for p in pixels], "advance_px": None}
        advances[glyph["codepoint"]] = float(glyph["advance_26_6"]) / 64.0
    kerning = font.get("kerning", [])
    adjustments = {(p["left"], p["right"]): float(p["adjustment_26_6"]) / 64.0
                   for p in kerning} if isinstance(kerning, list) else {}
    return {"profile": "gray", "size_px": float(font["config"]["size_px"]),
            "source_path": str(path), "cells": cells, "adjustments": adjustments,
            "advances": advances}


def metric_step(dataset, left, right):
    """Current-source placement step for an isolated pair (named control)."""
    if dataset["profile"] == "mono":
        advance = dataset["cells"][left]["advance_px"]
    else:
        advance = dataset["advances"][left]
    adjustment = dataset["adjustments"].get((left, right), 0.0)
    return pixel_round(advance + adjustment)


class PairScorer:
    """Scores integer origin steps for glyph pairs from delivered cells.

    Per-glyph ink analysis is cached per (glyph, scale, falloff); candidate
    scoring is exact brute-force Euclidean distance on small analysis windows.
    No training, no randomness, no cross-pair state: output is a pure function
    of (dataset, pair, step, controls), hence finite, deterministic and
    order-independent.
    """

    def __init__(self, dataset):
        self.dataset = dataset
        self._ink = {}
        self._geometry = {}

    def _ink_analysis(self, codepoint, controls):
        key = (codepoint, float(controls.feature_scale),
               float(controls.proximity_falloff))
        cached = self._ink.get(key)
        if cached is not None:
            return cached
        cell = self.dataset["cells"][codepoint]
        width, height = cell["width"], cell["height"]
        cover = np.asarray(cell["cover"], dtype=np.float64).reshape(height, width)
        rows, cols = np.nonzero(cover > 0.0)
        # Ink-plane coordinates preserve bearings/origins: x = left + col,
        # row band index t = top + row (shared baseline across the pair).
        points = np.column_stack(
            (cell["left"] + cols.astype(np.float64),
             cell["top"] + rows.astype(np.float64)))
        values = cover[rows, cols]
        tight = None
        if len(rows):
            tight = (float(np.min(points[:, 0])), float(np.max(points[:, 0])),
                     float(np.min(points[:, 1])), float(np.max(points[:, 1])))
        analysis = {"points": points, "values": values, "tight": tight,
                    "width": width, "height": height}
        self._ink[key] = analysis
        return analysis

    def score_geometry(self, left, right, step, scale, falloff):
        """Cohesion-free geometry for one integer step (cached).

        Returns the exact interaction and diagnostics without the cohesion
        cost, so one evaluation serves every cohesion set-point. Pure in
        (dataset, pair, step, scale, falloff); the cache only reuses that
        identical computation.
        """
        scale, falloff = float(scale), float(falloff)
        if step != int(step) or not math.isfinite(step):
            raise ValueError("step must be a finite integer")
        step = int(step)
        key = (left, right, step, scale, falloff)
        cached = self._geometry.get(key)
        if cached is not None:
            return cached
        controls = YYControls(cohesion=DEFAULT_CONTROLS.cohesion,
                              feature_scale=scale,
                              proximity_falloff=falloff)
        record = self._score_geometry_uncached(left, right, step, controls)
        self._geometry[key] = record
        return record

    def _score_geometry_uncached(self, left, right, step, controls):
        scale = float(controls.feature_scale)
        falloff = float(controls.proximity_falloff)
        step = int(step)
        left_ink = self._ink_analysis(left, controls)
        right_ink = self._ink_analysis(right, controls)
        if len(left_ink["points"]) == 0 or len(right_ink["points"]) == 0:
            return {"step": step, "valid": False,
                    "reason": "blank_glyph_no_ink",
                    "metric": metric_step(self.dataset, left, right)}
        metric = metric_step(self.dataset, left, right)
        offset = step  # right glyph origin relative to left origin
        overlap, faces, corners = contact_counts(
            self.dataset["cells"][left], self.dataset["cells"][right], offset)
        if overlap > 0:
            return {"step": step, "valid": False,
                    "reason": "occupied_cell_overlap",
                    "metric": metric, "overlaps": overlap,
                    "faces": faces, "corners": corners}
        radius = int(math.ceil(WINDOW_FACTOR * scale)) + WINDOW_MIN
        lo = left_ink["tight"]
        ro = right_ink["tight"]
        # Right ink shifts by the candidate step; rows share the baseline band.
        xmin = math.floor(min(lo[0], ro[0] + offset) - radius)
        xmax = math.ceil(max(lo[1], ro[1] + offset) + radius)
        ymin = math.floor(min(lo[2], ro[2]) - radius)
        ymax = math.ceil(max(lo[3], ro[3]) + radius)
        xs = np.arange(xmin, xmax + 1, dtype=np.float64)
        ys = np.arange(ymin, ymax + 1, dtype=np.float64)
        grid_x, grid_y = np.meshgrid(xs, ys)
        query = np.column_stack((grid_x.ravel(), grid_y.ravel()))
        right_points = right_ink["points"] + np.array([float(offset), 0.0])
        dist_l, val_l = _nearest(left_ink["points"], left_ink["values"], query)
        dist_r, val_r = _nearest(right_points, right_ink["values"], query)
        oppose_full = _opposition(grid_x.shape, dist_l, dist_r)
        on_ink = (dist_l == 0.0) | (dist_r == 0.0)
        back = ~on_ink
        if not np.any(back):
            return {"step": step, "valid": False,
                    "reason": "no_background_window",
                    "metric": metric, "overlaps": 0,
                    "faces": faces, "corners": corners}
        r_l, r_r = dist_l[back], dist_r[back]
        g_l, g_r = val_l[back], val_r[back]
        bubble_l = g_l / (1.0 + (r_l / scale) ** falloff)
        bubble_r = g_r / (1.0 + (r_r / scale) ** falloff)
        strength_l = g_l / (1.0 + (r_l / scale) ** (falloff + SECOND_EXPONENT_OFFSET))
        strength_r = g_r / (1.0 + (r_r / scale) ** (falloff + SECOND_EXPONENT_OFFSET))
        spread = max(scale / 2.0, GRADIENT_FLOOR)
        equidistance = np.exp(-((r_l - r_r) ** 2) / (2.0 * spread * spread))
        oppose = oppose_full[back]
        attention = equidistance * oppose * (strength_l * strength_r)
        attention_sum = float(np.sum(attention))
        if not math.isfinite(attention_sum) or attention_sum <= 0.0:
            return {"step": step, "valid": False,
                    "reason": "zero_attention",
                    "metric": metric, "overlaps": 0,
                    "faces": faces, "corners": corners}
        interaction = float(np.sum(attention * (bubble_l + bubble_r)) / attention_sum)
        weights = attention / attention_sum
        fields = {
            "distance_disagreement": float(np.sum(weights * np.abs(r_l - r_r))),
            "strength_product": float(np.sum(weights * strength_l * strength_r)),
            "distance_sum": float(np.sum(weights * (r_l + r_r))),
            "orientation": float(np.sum(weights * oppose)),
        }
        if not math.isfinite(interaction):
            return {"step": step, "valid": False,
                    "reason": "nonfinite_score",
                    "metric": metric, "overlaps": 0,
                    "faces": faces, "corners": corners}
        return {"step": step, "valid": True,
                "reason": None, "metric": metric,
                "interaction": interaction, "attention_sum": attention_sum,
                "fields": fields, "overlaps": 0,
                "faces": faces, "corners": corners,
                "delta_vs_metric": step - metric}

    def score_step(self, left, right, step, controls):
        """Score one integer origin step; glyph bitmaps are unchanged."""
        cohesion = float(controls.cohesion)
        if step != int(step) or not math.isfinite(step):
            raise ValueError("step must be a finite integer")
        geometry = self.score_geometry(
            left, right, step,
            float(controls.feature_scale),
            float(controls.proximity_falloff))
        record = dict(geometry)
        if record["valid"]:
            record["cost"] = abs(record["interaction"] - cohesion)
        else:
            record["cost"] = None
        return record

    def evaluate_pair(self, left, right, controls):
        """All five candidates: costs, ties, choice, boundary and fallback."""
        metric = metric_step(self.dataset, left, right)
        candidates = [self.score_step(left, right, metric + delta, controls)
                      for delta in CANDIDATE_DELTAS]
        valid = [c for c in candidates if c["valid"]]
        for record in candidates:
            record["finite"] = (record["cost"] is not None
                                and math.isfinite(record["cost"]))
        if not valid:
            return {"pair": [left, right], "metric": metric,
                    "candidates": candidates, "chosen": metric,
                    "minimizing_steps": [],
                    "boundary_hit": False, "fallback": True,
                    "fallback_reason": _fallback_reason(candidates),
                    "settings": settings_identity(controls)}
        steps = [c["step"] for c in candidates]
        chosen, minimizing, boundary_hit = choose_from_costs(
            steps, [c["cost"] for c in candidates],
            [c["valid"] for c in candidates], metric)
        return {"pair": [left, right], "metric": metric,
                "candidates": candidates, "chosen": chosen,
                "minimizing_steps": minimizing,
                "boundary_hit": boundary_hit,
                "fallback": False, "fallback_reason": None,
                "settings": settings_identity(controls)}


def choose_from_costs(steps, costs, valids, metric):
    """Shared integer-choice rule: global valid minimum, then tolerance.

    Anchors at the global minimum over valid candidates, admits every valid
    candidate within TIE_TOLERANCE of it, and breaks ties toward the metric
    step. Used by the scorer and the sample-expansion export so both derive
    identical choices from identical interactions.
    """
    valid_costs = [cost for cost, valid in zip(costs, valids)
                   if valid and cost is not None and math.isfinite(cost)]
    if not valid_costs:
        return None, [], False
    best = min(valid_costs)
    minimizing = sorted(step for step, cost, valid
                        in zip(steps, costs, valids)
                        if valid and cost is not None
                        and math.isfinite(cost)
                        and cost <= best + TIE_TOLERANCE)
    # Deterministic tie-break toward the named metric control.
    chosen = min(minimizing, key=lambda s: (abs(s - metric), s - metric))
    domain = sorted(steps)
    return chosen, minimizing, chosen in (domain[0], domain[-1])


def _fallback_reason(candidates):
    reasons = sorted({c.get("reason") or "unknown" for c in candidates})
    return "+".join(reasons)


def _nearest(points, values, query):
    diff = query[:, None, :] - points[None, :, :]
    dist2 = np.einsum("ijk,ijk->ij", diff, diff)
    index = np.argmin(dist2, axis=1)
    return np.sqrt(dist2[np.arange(len(query)), index]), values[index]


def _opposition(shape, dist_l, dist_r):
    """Opposing-gradient factor in [0, 1]; 0.5 where gradients vanish.

    Completes the Electric Bubble attention triple (equidistance, opposing
    gradients, vertical position) with the first two only; the missing vertical
    factor is disclosed, not silently replaced.
    """
    grad_l_y, grad_l_x = np.gradient(dist_l.reshape(shape))
    grad_r_y, grad_r_x = np.gradient(dist_r.reshape(shape))
    norm_l = np.hypot(grad_l_x, grad_l_y)
    norm_r = np.hypot(grad_r_x, grad_r_y)
    dot = np.zeros(shape)
    ok = (norm_l > GRADIENT_FLOOR) & (norm_r > GRADIENT_FLOOR)
    dot[ok] = ((grad_l_x[ok] / norm_l[ok]) * (grad_r_x[ok] / norm_r[ok])
               + (grad_l_y[ok] / norm_l[ok]) * (grad_r_y[ok] / norm_r[ok]))
    oppose = np.full(shape, 0.5)
    oppose[ok] = (1.0 - dot[ok]) / 2.0
    return oppose.ravel()


def contact_counts(left_cell, right_cell, offset):
    """Exact occupied-cell overlap and face/corner contact at integer step."""
    left = _occupied(left_cell, 0)
    right = _occupied(right_cell, offset)
    overlaps = len(left & right)
    if overlaps:
        faces = corners = 0
    else:
        faces = corners = 0
        for (x, y) in right:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    if (x + dx, y + dy) in left:
                        if dx == 0 or dy == 0:
                            faces += 1
                        else:
                            corners += 1
    return overlaps, faces, corners


def _occupied(cell, origin_x):
    width, height = cell["width"], cell["height"]
    left, top = int(cell["left"]), int(cell["top"])
    cells = set()
    for row in range(height):
        for col in range(width):
            if cell["cover"][row * width + col] > 0.0:
                cells.add((origin_x + left + col, top + row))
    return cells


def _pair_advance_fractional(dataset, left, right):
    # Independent captured-source policy: raw fractional advance plus the
    # full 26.6 pair adjustment, with no per-pair rounding. Mono advances
    # are finalized whole pixels; Gray advances keep 26.6 fractions.
    if dataset["profile"] == "mono":
        advance = float(dataset["cells"][left]["advance_px"])
    else:
        advance = float(dataset["advances"][left])
    return advance + float(dataset["adjustments"].get((left, right), 0.0))


def captured_source_word_origins(dataset, text):
    """Named captured-source word baseline (not the experiment layout).

    Fractional 26.6 pen accumulates advance plus pair adjustment per gap;
    only draw origins round, via pixel_round, matching the native surface
    invariant ``(pen + 32).div_euclid(64)`` for the nonneg pens of a
    left-aligned word starting at 0 (crates/generator/src/surface.rs).
    Grayscale captures use subpixel metric rounding, so these draws differ
    from per-pair rounded sums; Mono advances are whole pixels, so both
    policies agree there. Independent of metric_step and of any scorer.
    """
    codepoints = [ord(c) for c in text]
    for cp in codepoints:
        if cp not in dataset["cells"]:
            raise ValueError(f"codepoint U+{cp:04X} not in captured repertoire")
    if len(codepoints) < 2:
        return {"origins": [0], "pens": [0.0], "gaps": [], "text": text}
    origins = [0]
    pens = [0.0]
    gaps = []
    pen = 0.0
    for left, right in zip(codepoints, codepoints[1:]):
        increment = _pair_advance_fractional(dataset, left, right)
        pen += increment
        pens.append(pen)
        draw = pixel_round(pen)
        gaps.append({"pair": chr(left) + chr(right),
                     "advance_px": increment,
                     "draw_step": draw - origins[-1]})
        origins.append(draw)
    return {"origins": origins, "pens": pens, "gaps": gaps, "text": text}


def layout_text(dataset, scorer, text, controls):
    """Lay out text with independent per-gap decisions (order-independent).

    Experiment candidate policy: cumulative whole-pixel chosen steps, each
    resolved around its metric-rounded pair center. Distinct from the
    captured-source fractional word layout (captured_source_word_origins).
    """
    codepoints = [ord(c) for c in text]
    for cp in codepoints:
        if cp not in dataset["cells"]:
            raise ValueError(f"codepoint U+{cp:04X} not in captured repertoire")
    if len(codepoints) < 2:
        return {"origins": [0], "gaps": [], "text": text,
                "settings": settings_identity(controls)}
    origins = [0]
    gaps = []
    for left, right in zip(codepoints, codepoints[1:]):
        metric = metric_step(dataset, left, right)
        if left == 32 or right == 32:
            # Word space keeps metric advance; no ink on one side to score.
            chosen, detail = metric, {"fallback": True,
                                      "fallback_reason": "space_gap_metric"}
        else:
            detail = scorer.evaluate_pair(left, right, controls)
            chosen = detail["chosen"]
        gaps.append({"pair": [left, right], "metric": metric, "chosen": chosen,
                     "evaluation": detail})
        origins.append(origins[-1] + chosen)
    return {"origins": origins, "gaps": gaps, "text": text,
            "settings": settings_identity(controls)}


def describe_pair(dataset, left, right):
    left_cell = dataset["cells"][left]
    right_cell = dataset["cells"][right]
    return {"pair": chr(left) + chr(right), "codepoints": [left, right],
            "left_advance": left_cell["advance_px"],
            "left_ink": int(sum(1 for v in left_cell["cover"] if v > 0)),
            "right_ink": int(sum(1 for v in right_cell["cover"] if v > 0))}
