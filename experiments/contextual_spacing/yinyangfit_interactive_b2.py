# cspell:words fullwindow yinyangfit
"""Full-window candidate scorer for the interactive spacing experiment (ARM-B2).

Experimental model ``yinyangfit-interactive-b2-fullwindow-v1``. Same
nearest-sample fields, window extents, kernel, normalization, tie/fallback,
overlap and contact rules as the frozen
:mod:`yinyangfit_interactive` (``yinyangfit-interactive-v1``, retained
byte-identical as the historical reference); the ONLY change is the query
support: every query position in the window enters the attention-normalized
mean, including positions where ``dist == 0``. The finite regularized kernel
stays finite at ``r = 0``, so no new penalty, threshold or rescaling is added.

Rationale (see ``docs/references/yinyang-model-repair.md``): under the v1
background-only mask the highest-weight gap query points vanish exactly at
contact steps, collapsing the attention denominator and dropping the score;
scoring the full window removes that candidate-dependent support collapse
with zero new parameters or glyph rules. Contact stays permitted and
reported; occupied-cell overlap stays invalid.
"""

import hashlib
import math
from pathlib import Path

import numpy as np

import yinyangfit_interactive as v1

MODEL_IDENTITY = "yinyangfit-interactive-b2-fullwindow-v1"
IMPLEMENTATION_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

# Shared controls, ranges, helpers and policies: re-exported unchanged so the
# v3 catalogue builder and settings adapter keep one call surface. Only the
# geometry core (below) and the two identities differ from v1.
YYControls = v1.YYControls
DEFAULT_CONTROLS = v1.DEFAULT_CONTROLS
CONTROL_GRID = v1.CONTROL_GRID
CANDIDATE_DELTAS = v1.CANDIDATE_DELTAS
TIE_TOLERANCE = v1.TIE_TOLERANCE
WINDOW_FACTOR = v1.WINDOW_FACTOR
WINDOW_MIN = v1.WINDOW_MIN
GRADIENT_FLOOR = v1.GRADIENT_FLOOR
SECOND_EXPONENT_OFFSET = v1.SECOND_EXPONENT_OFFSET
metric_step = v1.metric_step
load_mono_capture = v1.load_mono_capture
load_gray_capture = v1.load_gray_capture
contact_counts = v1.contact_counts
choose_from_costs = v1.choose_from_costs
layout_text = v1.layout_text
captured_source_word_origins = v1.captured_source_word_origins
describe_pair = v1.describe_pair
pixel_round = v1.pixel_round
_nearest = v1._nearest
_opposition = v1._opposition
_fallback_reason = v1._fallback_reason


def settings_identity(controls):
    """Reproducible identity for one evaluated setting under this model."""
    canonical = v1.json.dumps(
        {"model": MODEL_IDENTITY, "implementation": IMPLEMENTATION_SHA256,
         "controls": {"cohesion": float(controls.cohesion),
                      "feature_scale": float(controls.feature_scale),
                      "proximity_falloff": float(controls.proximity_falloff)}},
        sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def layout_text(dataset, scorer, text, controls):
    """Inherited text layout restamped with the B2 settings identity."""
    layout = v1.layout_text(dataset, scorer, text, controls)
    layout["settings"] = settings_identity(controls)
    return layout


class PairScorer(v1.PairScorer):
    """v1 scorer with the full-window aggregation (no on-ink mask).

    Ink analysis, window extents, kernel, normalization, choice rule and
    validity policy are inherited unchanged; only the scored query set
    changes. The geometry cache stays per-instance, so B2 records never
    share a cache entry with v1 records.
    """

    def evaluate_pair(self, left, right, controls):
        """Inherited choice over B2 geometry, stamped with the B2 identity.

        The inherited method stamps the v1 settings hash; restamping here
        keeps every B2 record (geometry, choice and settings) under one
        model identity without duplicating the choice logic.
        """
        record = super().evaluate_pair(left, right, controls)
        record["settings"] = settings_identity(controls)
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
        oppose = _opposition(grid_x.shape, dist_l, dist_r)
        # ARM-B2 full-window support: every query position scores, including
        # on-ink positions (dist == 0), which enter the bubbles at r = 0
        # through the same finite regularized kernel. No mask, no rescaling.
        r_l, r_r = dist_l, dist_r
        g_l, g_r = val_l, val_r
        bubble_l = g_l / (1.0 + (r_l / scale) ** falloff)
        bubble_r = g_r / (1.0 + (r_r / scale) ** falloff)
        strength_l = g_l / (1.0 + (r_l / scale) ** (falloff + SECOND_EXPONENT_OFFSET))
        strength_r = g_r / (1.0 + (r_r / scale) ** (falloff + SECOND_EXPONENT_OFFSET))
        spread = max(scale / 2.0, GRADIENT_FLOOR)
        equidistance = np.exp(-((r_l - r_r) ** 2) / (2.0 * spread * spread))
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
