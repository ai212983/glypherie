"""Isolated optical placement; no production renderer imports this module.

The Hu/Hersch candidates retain delivered-reference and source-designed-reference
shared targets and the patent's
bounded cavity-depth model. Its source-preserving comparison measures each
source pair and delivered pair through those same transformations. The earlier filtered-wall comparison adapts
Hu 1998 section 4.4's area measurement and
Hersch 1995 pp. 85–88's reference calibration and clearance principles. The
owning design records common reference windows, numerical sampling, experimental
ASCII 00 calibration and the conservative Mono no-touch adaptation. Existing
FontForge-based font-calibrated, source-relative and fixed-target solvers remain
comparison controls. Metrics retain captured maintained generator composition.
The optional CounterSpace adapter reuses its pinned upstream two-dimensional
score; this module composes placement and never reimplements that algorithm.
"""

import copy
from dataclasses import asdict, dataclass
import hashlib
import importlib
import json
import math
from itertools import product
from pathlib import Path

import estimator
import calibration
import filtered_walls
from calibration import Calibration, FilteredCalibration, pair_basis
from estimator import analyze, separation, UnsupportedGeometry, WorkLimitExceeded

IMPLEMENTATION_IDENTITY = hashlib.sha256(
    Path(__file__).read_bytes() + Path(estimator.__file__).read_bytes() + Path(calibration.__file__).read_bytes() + Path(filtered_walls.__file__).read_bytes()
    + Path(__file__).with_name("hu_hersch.py").read_bytes() + Path(__file__).with_name("hu_calibration.py").read_bytes()
    + Path(__file__).with_name("hu_source_relative.py").read_bytes()
    + Path(__file__).with_name("hu_density.py").read_bytes()).hexdigest()

COUNTERSPACE_MODELS = {
    "counterspace": ("delivered", "closest_feasible"),
    "counterspace_delivered_first": ("delivered", "first_crossing"),
    "counterspace_source_first": ("source", "first_crossing"),
}
HU_SHARED_MODELS = {"hu_hersch": "delivered", "hu_source_calibrated": "source"}
HU_DENSITY_MODELS = {"hu_alphabet_source_target": "source_alphabet", "hu_density_conserved": "source_origin",
                     "hu_density_conserved_touch": "source_origin",
                     "hu_fitted_density_conserved_touch": "source_origin",
                     "hu_fitted_full_density_conserved_touch": "source_origin"}
HU_MODELS = (*HU_SHARED_MODELS, "hu_source_relative", *HU_DENSITY_MODELS)
SPACING_MODELS = (*HU_MODELS, *COUNTERSPACE_MODELS, "filtered_walls", "font_calibrated", "balanced", "source_relative")
HU_HERSCH_DIAGNOSTIC_FIELDS = (
    "reference_pair", "hu_hersch", "target_area_px2", "window_height_px", "measurement_window_px",
    "unconstrained_step_px", "clearance_min_step_px",
)
HU_SOURCE_RELATIVE_DIAGNOSTIC_FIELDS = HU_HERSCH_DIAGNOSTIC_FIELDS + (
    "source_step_px", "source_advance_px", "source_pair_adjustment_px",
    "source_hu_offset_px", "delivered_hu_offset_px", "source_target_px",
)
COUNTERSPACE_SEARCH_FIELDS = (
    "target_crossed", "candidate_count", "search_outcome", "feasible_candidate_count",
    "candidate_domain_min_step_px", "candidate_domain_stop_step_px",
    "first_crossing_step_px", "first_crossing_score", "closest_feasible_step_px", "closest_feasible_score",
)


def hu_clearance_policy(spacing_model):
    return "no_overlap" if spacing_model in ("hu_density_conserved_touch", "hu_fitted_density_conserved_touch",
                                             "hu_fitted_full_density_conserved_touch") else "strict"


def hu_density_geometry(spacing_model):
    return "fitted_outline" if spacing_model in ("hu_fitted_density_conserved_touch",
                                                 "hu_fitted_full_density_conserved_touch") else "bitmap"


def hu_density_construction(spacing_model):
    return "full_outline" if spacing_model == "hu_fitted_full_density_conserved_touch" else "windowed"


def hu_density_measurement(spacing_model):
    if hu_density_construction(spacing_model) == "full_outline":
        return "hu-hersch-patent-full-fitted-walls-v1"
    return ("hu-hersch-patent-sampled-fitted-pixel-walls-v1" if hu_density_geometry(spacing_model) == "fitted_outline"
            else "hu-hersch-patent-bounded-cell-walls-v2")


class UnsupportedText(ValueError):
    pass


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("expected a finite number")
    return value


def pixel_round(value):
    value = finite(value)
    return math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)


@dataclass(frozen=True)
class Controls:
    source_kerning: float = 1.0
    optical: float = 1.0
    letter_spacing: float = 0.0
    word_spacing: float = 0.0
    preserve_tabular_spacing: bool = True
    spacing_model: str = "hu_hersch"
    target_separation_em: float = 0.15

    def __post_init__(self):
        for key in ("source_kerning", "optical", "letter_spacing", "word_spacing"):
            finite(getattr(self, key))
        if type(self.preserve_tabular_spacing) is not bool:
            raise ValueError("preserve_tabular_spacing must be a boolean")
        if self.spacing_model not in SPACING_MODELS:
            raise ValueError("spacing_model must be one of: " + ", ".join(SPACING_MODELS))
        if finite(self.target_separation_em) <= 0:
            raise ValueError("target_separation_em must be positive")
        if not 0 <= self.source_kerning <= 1 or not 0 <= self.optical <= 1:
            raise ValueError("kerning and optical strengths must be in [0, 1]")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def scaled_commands(commands, scale):
    return [dict(op=command["op"], **{
        key: finite(command[key]) * scale
        for key in ("x", "y", "x1", "y1", "x2", "y2") if key in command
    }) for command in commands]


def bitmap_commands(bitmap, scale):
    """Union of delivered ink pixels, using closed row runs; baseline y-up.

    Pixel edges, rather than centers or a thresholded outline, represent the
    delivered binary image. Gray requires its own justified boundary policy.
    """
    width, height = bitmap["width"], bitmap["height"]
    if any(type(value) is not int or value < 0 for value in (width, height)):
        raise ValueError("invalid bitmap dimensions")
    pixels = bitmap["pixels"]
    if len(pixels) != width * height or any(type(p) is not int or p not in (0, 1) for p in pixels):
        raise ValueError("produced ink geometry requires an unpacked 1-bit bitmap")
    left, top = finite(bitmap["left"]), finite(bitmap["top"])
    commands = []
    for row in range(height):
        col = 0
        while col < width:
            if not pixels[row * width + col]:
                col += 1
                continue
            start = col
            while col < width and pixels[row * width + col]:
                col += 1
            x0, x1 = (left + start) * scale, (left + col) * scale
            y0, y1 = (-top - row - 1) * scale, (-top - row) * scale
            commands.extend((dict(op="move_to", x=x0, y=y0), dict(op="line_to", x=x1, y=y0),
                             dict(op="line_to", x=x1, y=y1), dict(op="line_to", x=x0, y=y1),
                             dict(op="close")))
    return commands


class Solver:
    """Completed analyses are reusable across controls, never partial pair tables.

    A solver belongs to one immutable capture and geometry policy. Preview and
    full generation invoke the same pair calculation. Limits count attempted
    ordered pairs; no browser budget is inferred from this diagnostic limit.
    """

    def __init__(self, capture, subdivisions=100, produced_geometry="bitmap", *, filtered_samples_per_px=64):
        # Freeze externally owned dictionaries so cache history cannot mutate inputs.
        self.capture = json.loads(canonical(capture))
        if capture["schema_version"] != "contextual-spacing-capture-v1":
            raise ValueError("unsupported capture schema")
        self.em = finite(capture["units_per_em"])
        self.size = finite(capture["size_px"])
        if min(self.em, self.size) <= 0:
            raise ValueError("size and units per em must be positive")
        if type(subdivisions) is not int or subdivisions not in (100, 200):
            raise ValueError("choose FontForge em/100 or em/200 bands")
        if produced_geometry not in ("bitmap", "fitted_outline"):
            raise ValueError("unsupported produced geometry")
        if type(filtered_samples_per_px) is not int or not 1 <= filtered_samples_per_px <= 1024:
            raise ValueError("filtered_samples_per_px must be an integer in [1, 1024]")
        self.filtered_samples_per_px = filtered_samples_per_px
        self.subdivisions = subdivisions
        self.geometry = produced_geometry
        self.glyphs = {g["codepoint"]: g for g in self.capture["glyphs"]}
        if len(self.glyphs) != len(capture["glyphs"]) or not self.glyphs:
            raise ValueError("repertoire must be nonempty with distinct codepoints")
        for cp, glyph in self.glyphs.items():
            if type(cp) is not int or not 0x20 <= cp <= 0x10FFFF or 0xD800 <= cp <= 0xDFFF:
                raise ValueError("invalid captured scalar")
            finite(glyph["source_advance_px"])
            # Nonfinite coordinates are always errors, including the metric-only
            # path. Optional optical representability is a separate concern.
            for key in ("source_commands", "produced_commands"):
                for command in glyph[key]:
                    for coordinate in ("x", "y", "x1", "y1", "x2", "y2"):
                        if coordinate in command:
                            finite(command[coordinate])
            if pixel_round(glyph["finalized_advance_px"]) != glyph["finalized_advance_px"]:
                raise ValueError("finalized advances must be whole pixels")
        self.source_pairs = self._pairs("source_pairs")
        self.metric_on = self._pairs("metric_pairs_on")
        self.metric_off = self._pairs("metric_pairs_off")
        self._calibration = Calibration(self.capture, self.glyphs, self.source_pairs,
                                        self.em, self.size, self.subdivisions)
        self._filtered_calibration = FilteredCalibration(self._calibration, filtered_samples_per_px)
        self._filtered_profiles = {}
        self._filtered_pairs = {}
        self._envelopes = {}
        self._counterspace = {}
        self._hu_hersch = None
        self._hu_source_calibrated = None
        self._hu_source_relative = None
        self._hu_density = {}
        self._hu_hersch_pairs = {}
        self._hu_hersch_clearances = {}
        self.identity = hashlib.sha256(canonical({
            "capture": self.capture, "subdivisions": subdivisions,
            "produced_geometry": produced_geometry, "solver": "optical-reference-target-v5",
            "filtered_samples_per_px": filtered_samples_per_px,
            "implementation_sha256": IMPLEMENTATION_IDENTITY,
        }).encode()).hexdigest()

    def _pairs(self, key):
        result = {}
        for pair in self.capture[key]:
            identity = (pair["left"], pair["right"])
            if identity in result or any(cp not in self.glyphs for cp in identity):
                raise ValueError("invalid or duplicate captured pair")
            result[identity] = finite(pair["adjustment_px"])
        return result

    def _envelope(self, cp, source):
        key = (cp, source)
        if key not in self._envelopes:
            glyph = self.glyphs[cp]
            if source:
                commands = glyph["source_commands"]
            elif self.geometry == "bitmap":
                commands = bitmap_commands(glyph["bitmap"], self.em / self.size)
            else:
                commands = scaled_commands(glyph["produced_commands"], self.em / self.size)
            self._envelopes[key] = analyze(commands, self.em, self.subdivisions)
        return self._envelopes[key]

    def calibration_metadata(self, evaluate=True, spacing_model="filtered_walls"):
        """Measurement provenance; source-relative pair targets also depend on k."""
        if spacing_model in HU_SHARED_MODELS:
            return (self._hu_hersch_model(HU_SHARED_MODELS[spacing_model]).metadata() if evaluate else
                    dict(status="not_evaluated", measurement_method="hu-hersch-bounded-walls-v1"))
        if spacing_model == "hu_source_relative":
            return (self._hu_source_relative_model().metadata() if evaluate else
                    dict(status="not_evaluated", measurement_method="hu-hersch-source-pair-relative-v1"))
        if spacing_model in HU_DENSITY_MODELS:
            policy = HU_DENSITY_MODELS[spacing_model]
            geometry = hu_density_geometry(spacing_model)
            construction = hu_density_construction(spacing_model)
            metadata = (self._hu_density_model(policy, geometry, construction).metadata() if evaluate else
                    dict(status="not_evaluated", measurement_method=hu_density_measurement(spacing_model),
                         policy="hu-hersch-fixed-alphabet-density-v1", target_policy=policy,
                         candidate_geometry=geometry, target_provenance="fixed_alphabet_" + policy + "_hu_hersch",
                         source_metric_quantization=self.capture.get("source_metric_quantization"),
                         samples_per_px=self.filtered_samples_per_px, classes={}, references={}))
            if construction == "full_outline":
                metadata.update(construction_policy=construction, cavity_supports="post_B")
                if not evaluate:
                    metadata["policy"] += "-full-outline"
                    metadata["target_provenance"] += "_full_outline"
            return dict(metadata, clearance_policy=hu_clearance_policy(spacing_model))
        if spacing_model in COUNTERSPACE_MODELS:
            geometry, search_policy = COUNTERSPACE_MODELS[spacing_model]
            metadata = (self._counterspace_model(geometry).metadata() if evaluate else
                        dict(status="not_evaluated", measurement_method="counterspace-pinned-v1"))
            return dict(metadata, spacing_model=spacing_model, calibration_geometry=geometry, search_policy=search_policy)
        return (self._filtered_calibration if spacing_model == "filtered_walls" else self._calibration).metadata(evaluate)

    def _hu_hersch_model(self, reference_geometry="delivered"):
        # Measurement and reference calibration are evaluated
        # only after optical-zero and placement-preservation guards abstain.
        attribute = "_hu_hersch" if reference_geometry == "delivered" else "_hu_source_calibrated"
        if getattr(self, attribute) is None:
            adapter = importlib.import_module("hu_calibration")
            model = adapter.HuHerschModel(self.capture, samples_per_px=self.filtered_samples_per_px,
                                         reference_geometry=reference_geometry)
            setattr(self, attribute, model)
        return getattr(self, attribute)

    def _hu_source_relative_model(self):
        if self._hu_source_relative is None:
            adapter = importlib.import_module("hu_source_relative")
            self._hu_source_relative = adapter.HuSourceRelativeModel(
                self.capture, samples_per_px=self.filtered_samples_per_px)
        return self._hu_source_relative

    def _hu_density_model(self, target_policy, candidate_geometry="bitmap", construction_policy="windowed"):
        key = target_policy if candidate_geometry == "bitmap" else (target_policy, candidate_geometry)
        if construction_policy != "windowed":
            key = (target_policy, candidate_geometry, construction_policy)
        if key not in self._hu_density:
            adapter = importlib.import_module("hu_density")
            self._hu_density[key] = adapter.HuDensityModel(
                self.capture, samples_per_px=self.filtered_samples_per_px,
                target_policy=target_policy, candidate_geometry=candidate_geometry,
                construction_policy=construction_policy)
        return self._hu_density[key]

    def _counterspace_model(self, calibration_geometry):
        # The pinned upstream implementation and its numerical dependencies are
        # optional: metric-only and all comparison paths never import them.
        if calibration_geometry not in self._counterspace:
            adapter = importlib.import_module("counterspace")
            self._counterspace[calibration_geometry] = adapter.CounterSpaceModel(
                self.capture, calibration_geometry=calibration_geometry)
        return self._counterspace[calibration_geometry]

    def pair(self, left, right, controls=Controls()):
        l, r = self.glyphs[left], self.glyphs[right]
        pair = (left, right)
        source_kern = self.source_pairs.get(pair, 0)
        # Quantize scaled source kerning before adding the already finalized
        # bearing correction; the endpoint table is an independent cross-check.
        metric = pixel_round(source_kern * controls.source_kerning) + self.metric_off.get(pair, 0)
        if controls.source_kerning == 1 and metric != self.metric_on.get(pair, 0):
            raise ValueError("captured metric endpoint disagrees with source/bearing composition")
        result = dict(left=left, right=right, metric_adjustment_px=metric,
                      optical_adjustment_px=None, source_target_px=None,
                      target_separation_px=None, realized_separation_px=None, target_error_px=None,
                      target_provenance=None, calibration_basis=None,
                      calibration_reason=None, calibration_detail=None,
                      blended_adjustment_px=metric, automatic_adjustment_px=metric, reason=None)
        if controls.spacing_model in (*HU_MODELS, "filtered_walls", *COUNTERSPACE_MODELS):
            result.update(measurement_method=("counterspace-pinned-v1" if controls.spacing_model in COUNTERSPACE_MODELS
                                               else "hu-hersch-source-pair-relative-v1" if controls.spacing_model == "hu_source_relative"
                                               else "hu-hersch-bounded-walls-v1" if controls.spacing_model in (*HU_SHARED_MODELS, *HU_DENSITY_MODELS)
                                               else "hu-filtered-walls-midpoint-v1"),
                          measurement_window_px=None, unconstrained_step_px=None,
                          rounded_unconstrained_step_px=None, clearance_min_step_px=None,
                          clearance_adjustment_px=0, clearance_limited=False)
        if controls.spacing_model in (*HU_MODELS, "filtered_walls"):
            result.update(target_area_px2=None, realized_area_px2=None, window_height_px=None)
        if controls.spacing_model in HU_MODELS:
            result.update(reference_pair=None, hu_hersch=None, hu_hersch_evaluated=False,
                          target_error_area_px2=None)
        if controls.spacing_model in HU_DENSITY_MODELS:
            result["clearance_policy"] = hu_clearance_policy(controls.spacing_model)
            result["candidate_geometry"] = hu_density_geometry(controls.spacing_model)
            if result["candidate_geometry"] == "fitted_outline":
                result["measurement_method"] = hu_density_measurement(controls.spacing_model)
            if hu_density_construction(controls.spacing_model) == "full_outline":
                result["construction_policy"] = "full_outline"
        if controls.spacing_model == "hu_source_relative":
            result.update(**dict.fromkeys(HU_SOURCE_RELATIVE_DIAGNOSTIC_FIELDS))
            result["hu_hersch_evaluated"] = False
        if controls.spacing_model in COUNTERSPACE_MODELS:
            geometry, search_policy = COUNTERSPACE_MODELS[controls.spacing_model]
            result.update(target_score=None, realized_score=None, score_error=None, reference_pair=None,
                          counterspace_evaluated=False, calibration_geometry=geometry, search_policy=search_policy,
                          **dict.fromkeys(COUNTERSPACE_SEARCH_FIELDS))
        if controls.optical == 0:
            result["reason"] = "optical_disabled"
        elif self.capture["monospace"]:
            result["reason"] = "fixed_pitch"
        # Equal source digit advances identify tabular forms; aligned number
        # placement is a separate experiment control. This changes only pair
        # placement, not numeral glyph selection (OpenType pnum/tnum), images or
        # finalized advances. The design's numeric-spacing policy owns the choice.
        elif controls.preserve_tabular_spacing and self.capture["tabular_digits"] and all(48 <= cp <= 57 for cp in pair):
            result["reason"] = "source_tabular_digits"
        else:
            empty = lambda glyph: not any(glyph["bitmap"]["pixels"]) if self.geometry == "bitmap" else not glyph["produced_commands"]
            if controls.spacing_model in (*HU_MODELS, "filtered_walls", *COUNTERSPACE_MODELS) and self.geometry != "bitmap":
                result["reason"] = "unsupported_geometry_policy"
            elif controls.spacing_model in (*HU_MODELS, "filtered_walls", "font_calibrated", *COUNTERSPACE_MODELS) and (empty(l) or empty(r)):
                result["reason"] = "empty_geometry"
            elif controls.spacing_model in ("filtered_walls", "font_calibrated"):
                basis = pair_basis(left, right)
                result["calibration_basis"] = basis
                if basis is None:
                    result.update(reason="unsupported_calibration_class",
                                  calibration_reason="unsupported_calibration_class",
                                  calibration_detail="requires Latin Ll/Lu letters or two ASCII digits")
                else:
                    calibrator = self._filtered_calibration if controls.spacing_model == "filtered_walls" else self._calibration
                    calibrated = calibrator.target(basis)
                    if calibrated["status"] != "available":
                        result.update(reason="calibration_unavailable", calibration_reason=calibrated["reason"],
                                      calibration_detail=calibrated["detail"])
            if controls.spacing_model in HU_SHARED_MODELS:
                self._solve_hu_hersch(left, right, controls, result, metric)
            elif controls.spacing_model == "hu_source_relative":
                self._solve_hu_source_relative(left, right, controls, result, metric)
            elif controls.spacing_model in HU_DENSITY_MODELS:
                if result["reason"] is None:
                    measured = self._hu_density_model(HU_DENSITY_MODELS[controls.spacing_model],
                        hu_density_geometry(controls.spacing_model),
                        hu_density_construction(controls.spacing_model)).pair(left, right)
                    self._compose_hu_placement(left, right, controls, result, metric, measured)
            elif controls.spacing_model in COUNTERSPACE_MODELS:
                self._solve_counterspace(left, right, controls, result, metric)
            elif controls.spacing_model == "filtered_walls":
                self._solve_filtered(left, right, controls, result, metric)
            else:
                self._solve_optical(left, right, controls, result, metric)
        # These codes describe computation and quantization, not optical quality.
        if result["reason"] is not None:
            result["diagnostic"] = result["reason"]
        elif result["automatic_adjustment_px"] != metric:
            result["diagnostic"] = "corrected"
        elif result["blended_adjustment_px"] != metric:
            result["diagnostic"] = "rounded_unchanged"
        else:
            result["diagnostic"] = "unchanged"
        result["resolved_step_px"] = l["finalized_advance_px"] + result["automatic_adjustment_px"]
        return result

    def _solve_hu_hersch(self, left, right, controls, result, metric):
        if result["reason"] is not None:
            return
        key = (controls.spacing_model, left, right)
        if key not in self._hu_hersch_pairs:
            self._hu_hersch_pairs[key] = self._hu_hersch_model(
                HU_SHARED_MODELS[controls.spacing_model]).pair(left, right)
        measured = self._hu_hersch_pairs[key]
        self._compose_hu_placement(left, right, controls, result, metric, measured)

    def _solve_hu_source_relative(self, left, right, controls, result, metric):
        if result["reason"] is not None:
            return
        measured = self._hu_source_relative_model().pair(left, right, controls.source_kerning)
        for key in HU_SOURCE_RELATIVE_DIAGNOSTIC_FIELDS:
            if key in measured:
                result[key] = copy.deepcopy(measured[key])
        self._compose_hu_placement(left, right, controls, result, metric, measured)

    def _compose_hu_placement(self, left, right, controls, result, metric, measured):
        pair = (left, right)
        result["hu_hersch_evaluated"] = True
        for key in ("reference_pair", "hu_hersch", "calibration_basis", "target_provenance",
                    "target_area_px2", "window_height_px", "measurement_window_px"):
            if key in measured:
                result[key] = copy.deepcopy(measured[key])
        if measured.get("reason"):
            result.update(reason=measured["reason"], calibration_reason=measured["reason"],
                          calibration_detail=measured.get("detail"))
            return
        advance = self.glyphs[left]["finalized_advance_px"]
        ideal = finite(measured["optical_step_px"])
        target = finite(measured["target_px"])
        offset = finite(measured["offset_px"])
        height = finite(measured["window_height_px"])
        if height <= 0:
            raise ValueError("Hu/Hersch measurement window must have positive height")
        optical = ideal - advance
        blended = metric * (1 - controls.optical) + optical * controls.optical
        rounded_step = advance + pixel_round(blended)
        # Keep the delivered-ink constraint independent from perceived area.
        # It covers the entire bitmap, including rows outside the body window.
        policy = hu_clearance_policy(controls.spacing_model)
        clearance_key = pair if policy == "strict" else (policy, *pair)
        clearance = (filtered_walls.clearance_min_step_no_overlap if policy == "no_overlap"
                     else filtered_walls.clearance_min_step)
        if clearance_key not in self._hu_hersch_clearances:
            self._hu_hersch_clearances[clearance_key] = clearance(
                self.glyphs[left]["bitmap"], self.glyphs[right]["bitmap"])
        minimum = self._hu_hersch_clearances[clearance_key]
        emitted = max(rounded_step, minimum) if minimum is not None else rounded_step
        guard = emitted - rounded_step
        realized = emitted + offset
        target_area = finite(measured["target_area_px2"])
        realized_area = realized * height
        result.update(target_separation_px=target, realized_separation_px=realized,
                      target_error_px=realized - target, target_area_px2=target_area,
                      realized_area_px2=realized_area, target_error_area_px2=realized_area - target_area,
                      optical_adjustment_px=optical, blended_adjustment_px=blended,
                      automatic_adjustment_px=emitted - advance,
                      unconstrained_step_px=ideal, rounded_unconstrained_step_px=rounded_step,
                      clearance_min_step_px=minimum, clearance_adjustment_px=guard,
                      clearance_limited=bool(guard))
        if guard:
            result["reason"] = "clearance_limited"

    def _solve_counterspace(self, left, right, controls, result, metric):
        if result["reason"] is not None:
            return
        geometry, search_policy = COUNTERSPACE_MODELS[controls.spacing_model]
        model = self._counterspace_model(geometry)
        result["counterspace_evaluated"] = True
        minimum = filtered_walls.clearance_min_step(self.glyphs[left]["bitmap"], self.glyphs[right]["bitmap"])
        measured = model.pair(left, right, search_policy=search_policy,
                              clearance_min_step=minimum if search_policy == "closest_feasible" else None)
        result.update({key: measured.get(key) for key in COUNTERSPACE_SEARCH_FIELDS})
        result["clearance_min_step_px"] = minimum
        if measured.get("target_score") is not None:
            result.update(target_score=finite(measured["target_score"]),
                          reference_pair=measured.get("reference_pair"),
                          target_provenance=geometry + "_reference_counterspace")
        if measured.get("reason"):
            result.update(reason=measured["reason"],
                          calibration_reason=measured["reason"],
                          calibration_detail=measured.get("detail"))
            return
        # The adapter owns upstream scoring and the declared first-crossing or
        # project nearest-feasible search. This layer composes that endpoint
        # with the metric blend and retains the closed-cell no-touch policy.
        advance = self.glyphs[left]["finalized_advance_px"]
        optical_step = finite(measured["optical_step_px"])
        optical = optical_step - advance
        blended = metric * (1 - controls.optical) + optical * controls.optical
        rounded_step = advance + pixel_round(blended)
        emitted = max(rounded_step, minimum) if minimum is not None else rounded_step
        guard = emitted - rounded_step
        target_score = finite(measured["target_score"])
        realized_score = finite(model.measure_pair(left, right, emitted))
        result.update(target_provenance=geometry + "_reference_counterspace",
                      target_score=target_score, realized_score=realized_score,
                      score_error=realized_score - target_score,
                      reference_pair=measured["reference_pair"],
                      optical_adjustment_px=optical, blended_adjustment_px=blended,
                      automatic_adjustment_px=emitted - advance,
                      unconstrained_step_px=finite(measured.get("unconstrained_step_px", optical_step)),
                      rounded_unconstrained_step_px=rounded_step,
                      clearance_min_step_px=minimum, clearance_adjustment_px=guard,
                      clearance_limited=bool(guard))
        if guard:
            result["reason"] = "clearance_limited"

    def _solve_filtered(self, left, right, controls, result, metric):
        if result["reason"] is not None:
            return
        if self.geometry != "bitmap":
            result["reason"] = "unsupported_geometry_policy"
            return
        basis = result["calibration_basis"]
        target_data = self._filtered_calibration.target(basis)
        window = tuple(target_data["measurement_window_px"])
        key = (left, right, window)
        if key not in self._filtered_pairs:
            profiles = []
            for cp in (left, right):
                profile_key = (cp, window)
                if profile_key not in self._filtered_profiles:
                    self._filtered_profiles[profile_key] = filtered_walls.bitmap_profile(
                        self.glyphs[cp]["bitmap"], window, self.filtered_samples_per_px)
                profiles.append(self._filtered_profiles[profile_key])
            offset = filtered_walls.pair_offset(*profiles)
            shared = filtered_walls.shared_ink_rows(*profiles)
            minimum = filtered_walls.clearance_min_step(self.glyphs[left]["bitmap"], self.glyphs[right]["bitmap"])
            self._filtered_pairs[key] = (offset, shared, minimum)
        offset, shared, minimum = self._filtered_pairs[key]
        if not shared:
            result["reason"] = "no_shared_ink_rows"
            return
        target = target_data["target_px"]
        height = target_data["window_height_px"]
        advance = self.glyphs[left]["finalized_advance_px"]
        ideal = target - offset
        optical = ideal - advance
        blended = metric * (1 - controls.optical) + optical * controls.optical
        rounded_step = advance + pixel_round(blended)
        # Hersch's clearance principle, adapted to strict closed Mono cells.
        # The bound includes adjacent bitmap rows, hence diagonal corner contact;
        # it preserves left/right wall order and can conservatively reject interlocks.
        emitted = max(rounded_step, minimum) if minimum is not None else rounded_step
        guard = emitted - rounded_step
        realized = emitted + offset
        result.update(measurement_method="hu-filtered-walls-midpoint-v1",
                      target_provenance="font_calibrated", target_separation_px=target,
                      target_area_px2=target * height, realized_area_px2=realized * height,
                      window_height_px=height, measurement_window_px=list(window),
                      optical_adjustment_px=optical, blended_adjustment_px=blended,
                      automatic_adjustment_px=emitted - advance,
                      unconstrained_step_px=ideal, rounded_unconstrained_step_px=rounded_step,
                      clearance_min_step_px=minimum, clearance_adjustment_px=guard,
                      clearance_limited=bool(guard), realized_separation_px=realized,
                      target_error_px=realized - target)
        if guard:
            result["reason"] = "clearance_limited"

    def _solve_optical(self, left, right, controls, result, metric):
        if result["reason"] is not None:
            return
        l = self.glyphs[left]
        source_kern = self.source_pairs.get((left, right), 0)
        pl, pr = self._envelope(left, False), self._envelope(right, False)
        source_relative = controls.spacing_model == "source_relative"
        sources = (self._envelope(left, True), self._envelope(right, True)) if source_relative else ()
        if any(e.bounds is None for e in (pl, pr, *sources)):
            result["reason"] = "empty_geometry"
        else:
            produced_sep = separation(pl, pr, self.em)
            source_sep = separation(*sources, self.em) if source_relative else None
            if produced_sep.estimate is None or (source_relative and source_sep.estimate is None):
                result["reason"] = "no_shared_bands"
            else:
                scale = self.size / self.em
                if source_relative:
                    sl, sr = sources
                    target = l["source_advance_px"] + controls.source_kerning * source_kern
                    target += (sr.bounds.minx - sl.bounds.maxx + source_sep.estimate) * scale
                    result["source_target_px"] = target
                    result["target_provenance"] = "source_relative"
                elif controls.spacing_model == "font_calibrated":
                    target = self._calibration.target(result["calibration_basis"])["target_px"]
                    result["target_provenance"] = "font_calibrated"
                else:
                    # FontForge c41bdb9 autowidth2.c: ak2_figure_kern uses
                    # desired minus measured separation; AutoKern2 defaults
                    # to 15% of the em. One target applies to every eligible
                    # pair; its facing-edge term accounts for shape.
                    target = self.size * controls.target_separation_em
                    result["target_provenance"] = "configured_target"
                facing = (pr.bounds.minx - pl.bounds.maxx + produced_sep.estimate) * scale
                required_step = target - facing
                optical = required_step - l["finalized_advance_px"]
                blended = metric * (1 - controls.optical) + optical * controls.optical
                automatic = pixel_round(blended)
                realized = l["finalized_advance_px"] + automatic + facing
                result.update(target_separation_px=target, optical_adjustment_px=optical,
                              blended_adjustment_px=blended,
                              automatic_adjustment_px=automatic,
                              realized_separation_px=realized, target_error_px=realized - target)

    def generate(self, controls=Controls(), text=None, work_limit=10000, cancelled=lambda: False):
        if self.capture["monospace"] and (controls.letter_spacing != 0 or controls.word_spacing != 0):
            raise ValueError("fixed-grid experiments require neutral deliberate spacing")
        if type(work_limit) is not int or work_limit < 0:
            raise ValueError("work limit must be a nonnegative integer")
        input_reason = None
        if text is None:
            domain = product(sorted(self.glyphs), repeat=2)
            declared = len(self.glyphs) ** 2
        else:
            try:
                self.validate_text(text)
            except UnsupportedText as error:
                input_reason = str(error)
            domain = sorted({(ord(a), ord(b)) for a, b in zip(text, text[1:]) if a != "\n" and b != "\n"})
            declared = len(domain)
        records = []
        status = "unsupported_input" if input_reason else "complete"
        reason = input_reason
        for left, right in domain:
            if input_reason:
                break
            if cancelled():
                status = "cancelled"
                break
            if len(records) >= work_limit:
                status = "work_limit_exceeded"
                break
            try:
                records.append(self.pair(left, right, controls))
            except (UnsupportedGeometry, WorkLimitExceeded) as error:
                status = "work_limit_exceeded" if isinstance(error, WorkLimitExceeded) else "unsupported_input"
                reason = str(error)
                break
        result = dict(schema_version="contextual-spacing-result-v1", analysis_identity=self.identity,
                    controls=asdict(controls), produced_geometry=self.geometry,
                    estimator=dict(subdivisions=self.subdivisions, floor_unit="font design unit",
                                   band_height=math.floor(self.em / self.subdivisions),
                                   reference="FontForge c41bdb922285f35defd1e1385adfd13bde1ab32a",
                                   reference_fp_flags=["-ffp-contract=off", "-fno-fast-math"]),
                    implementation_sha256=IMPLEMENTATION_IDENTITY,
                    work_limits=dict(ordered_pairs=work_limit, commands=estimator.MAX_COMMANDS,
                                     bands=estimator.MAX_BANDS, band_visits=estimator.MAX_BAND_VISITS),
                    status=status, reason=reason, declared_pairs=declared, completed_pairs=len(records),
                    pairs=records, source_identity=self.capture["source_sha256"])
        if controls.spacing_model in ("filtered_walls", "font_calibrated"):
            result["calibration"] = self.calibration_metadata(
                evaluate=controls.optical != 0 and not self.capture["monospace"], spacing_model=controls.spacing_model)
        if controls.spacing_model in HU_MODELS:
            try:
                metadata = self.calibration_metadata(any(p["hu_hersch_evaluated"] for p in records), controls.spacing_model)
            except (UnsupportedGeometry, WorkLimitExceeded) as error:
                # Source-designed reference metadata measures all declared anchors,
                # including classes absent from a text-only pair domain. Their
                # work limits must fail the result just like pair evaluation.
                if controls.spacing_model not in ("hu_source_calibrated", *HU_DENSITY_MODELS):
                    raise
                result.update(status="work_limit_exceeded" if isinstance(error, WorkLimitExceeded) else "unsupported_input",
                              reason=str(error))
                metadata = self.calibration_metadata(False, controls.spacing_model)
            result["hu_hersch"] = metadata
            result["calibration"] = metadata
            result["estimator"] = dict(measurement_method=("hu-hersch-source-pair-relative-v1"
                if controls.spacing_model == "hu_source_relative" else hu_density_measurement(controls.spacing_model)
                if controls.spacing_model in HU_DENSITY_MODELS and hu_density_geometry(controls.spacing_model) == "fitted_outline"
                else "hu-hersch-bounded-walls-v1"),
                                       samples_per_px=self.filtered_samples_per_px,
                                       reference="Hu 1998 section 4.4; Hersch 1995 pp. 85–88",
                                       coordinate_unit="pixel", integration="uniform midpoint",
                                       clearance_policy=(hu_clearance_policy(controls.spacing_model)
                                           if controls.spacing_model in HU_DENSITY_MODELS else
                                           "strict closed-cell wall order including diagonal contacts"))
            result["work_limits"] = dict(ordered_pairs=work_limit, filtered_samples=filtered_walls.MAX_SAMPLES,
                                         filtered_bitmap_pixels=filtered_walls.MAX_BITMAP_PIXELS)
            if controls.spacing_model in ("hu_source_relative", "hu_source_calibrated", *HU_DENSITY_MODELS):
                result["work_limits"].update(commands=estimator.MAX_COMMANDS,
                    filtered_scanline_visits=filtered_walls.MAX_SCANLINE_VISITS)
            if controls.spacing_model in HU_DENSITY_MODELS:
                result["estimator"].update(candidate_geometry=hu_density_geometry(controls.spacing_model),
                                            clearance_geometry="bitmap")
                if hu_density_construction(controls.spacing_model) == "full_outline":
                    result["estimator"].update(construction_policy="full_outline", cavity_supports="post_B")
                result["work_limits"].update(calibration_ordered_pairs=2804, calibration_ascii_glyphs=62)
            result[controls.spacing_model + "_analysis_identity"] = hashlib.sha256(canonical(dict(
                analysis_identity=self.identity, hu_hersch=metadata)).encode()).hexdigest()
        if controls.spacing_model == "filtered_walls":
            result["estimator"] = dict(measurement_method="hu-filtered-walls-midpoint-v1",
                                     samples_per_px=self.filtered_samples_per_px,
                                     reference="Hu 1998 section 4.4; Hersch 1995 pp. 85–88",
                                     coordinate_unit="pixel", integration="uniform midpoint",
                                     window_policy="source reference bounds; mixed union",
                                     clearance_policy="strict closed-cell wall order including diagonal contacts")
            result["work_limits"] = dict(ordered_pairs=work_limit, commands=estimator.MAX_COMMANDS,
                                         filtered_samples=filtered_walls.MAX_SAMPLES,
                                         filtered_scanline_visits=filtered_walls.MAX_SCANLINE_VISITS,
                                         filtered_bitmap_pixels=filtered_walls.MAX_BITMAP_PIXELS)
        if controls.spacing_model in COUNTERSPACE_MODELS:
            # Never initialize the optional model solely for provenance: an
            # optical-zero or fully abstaining run remains dependency-free.
            metadata = self.calibration_metadata(any(p["counterspace_evaluated"] for p in records), controls.spacing_model)
            result["counterspace"] = metadata
            result["calibration"] = metadata
            result["estimator"] = dict(measurement_method="counterspace-pinned-v1",
                                       coordinate_unit="delivered pixel",
                                       score_unit=metadata.get("target_score_units", "CounterSpace weighted score"),
                                       clearance_policy="strict closed-cell wall order including diagonal contacts")
            result["work_limits"] = dict(ordered_pairs=work_limit)
            result["counterspace_analysis_identity"] = hashlib.sha256(canonical(dict(
                analysis_identity=self.identity, counterspace=metadata)).encode()).hexdigest()
        return result

    def validate_text(self, text):
        if not isinstance(text, str):
            raise ValueError("text must be a string")
        absent = {ord(c) for c in text if c != "\n" and ord(c) not in self.glyphs}
        if absent:
            raise UnsupportedText(f"unsupported or uncaptured scalars: {sorted(absent)}")

    def layout(self, text, result, width=None):
        """Return placements used for drawing, measurement and greedy wrapping.

        Ordinary spaces end spans, explicit breaks reset context. Signed widths
        are measured from the finalized terminal pen, with no ink-bound clamp.
        """
        self.validate_text(text)
        if result["status"] != "complete" or result["analysis_identity"] != self.identity:
            raise ValueError("layout requires a completed matching result")
        if width is not None and finite(width) <= 0:
            raise ValueError("wrap width must be positive")
        controls = Controls(**result["controls"])
        pairs = {(p["left"], p["right"]): p for p in result["pairs"]}
        letter, word = pixel_round(controls.letter_spacing), pixel_round(controls.word_spacing)
        lines, placements, pen = [], [], 0

        def finish():
            nonlocal placements, pen
            lines.append(dict(width_px=pen, placements=placements))
            placements, pen = [], 0

        for index, character in enumerate(text):
            if character == "\n":
                finish()
                continue
            cp = ord(character)
            if placements:
                previous = placements[-1]["codepoint"]
                if (previous, cp) not in pairs:
                    raise ValueError("completed result did not cover requested layout pair")
                adjustment = pairs[previous, cp]["automatic_adjustment_px"]
                if previous != 32 and cp != 32:
                    adjustment += letter
            else:
                adjustment = 0
            advance = self.glyphs[cp]["finalized_advance_px"] + (word if cp == 32 else 0)
            # Break before the overflowing scalar; re-resolve line-start context.
            if width is not None and placements and pen + adjustment + advance > width:
                finish()
                adjustment = 0
            origin = pen + adjustment
            placements.append(dict(index=index, codepoint=cp, glyph_id=self.glyphs[cp]["glyph_id"],
                                   variant="original", x_px=origin, advance_px=advance))
            pen = origin + advance
        finish()
        return dict(lines=lines, letter_spacing_px=letter, word_spacing_px=word)
