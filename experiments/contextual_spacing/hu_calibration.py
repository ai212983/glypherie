"""Reference calibration for the bounded Hu/Hersch experiment.

US5768490A processing steps B–D disclose concavity-only slope filtering,
aperture DepthFactor=0.21 and GlobalDepthParameter=0.25. Its generic method
uses the same transformed walls for reference nn/HH and every candidate pair.
The earlier underidentified coefficient fit and classified vertical-border
shortcut are not used. Actual delivered cells and full maintained placements
supply the retained delivered-reference density control. The source-reference
experiment measures designed nn/HH/00 outlines and full source metrics through
the same physical windows, then places delivered cells toward that density.
This is a source-designed-reference adaptation, not author-code parity. Glyph
forms and captured metrics remain untouched.
"""

import copy
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path

from calibration import pair_basis
from estimator import UnsupportedGeometry
import filtered_walls as walls
import hu_hersch as hu


POLICY = "hu-hersch-delivered-published-reference-v2"
SOURCE_POLICY = "hu-hersch-source-designed-reference-v1"
PARAMETER_REFERENCE = "https://patents.google.com/patent/US5768490A/en"
RELATIVE_DEPTH = 0.21
VISUAL_DEPTH_FACTOR = 0.25
REFERENCES = {"lowercase": {"generic": "nn"}, "uppercase": {"generic": "HH"},
              "digits": {"generic": "00"}}


def _finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("expected a finite Hu/Hersch calibration number")
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class HuHerschModel:
    def __init__(self, capture, samples_per_px=64, reference_geometry="delivered"):
        if reference_geometry not in ("delivered", "source"):
            raise ValueError("reference_geometry must be delivered or source")
        self.reference_geometry = reference_geometry
        self.policy = SOURCE_POLICY if reference_geometry == "source" else POLICY
        self.target_provenance = ("source_reference_hu_hersch" if reference_geometry == "source"
                                  else "delivered_reference_hu_hersch")
        self.capture = json.loads(_canonical(capture))
        self.glyphs = {g["codepoint"]: g for g in self.capture["glyphs"]}
        self.scale = _finite(capture["size_px"]) / _finite(capture["units_per_em"])
        if self.scale <= 0:
            raise ValueError("size and units per em must be positive")
        hu.Settings(RELATIVE_DEPTH, VISUAL_DEPTH_FACTOR, samples_per_px)
        self.samples_per_px = samples_per_px
        self.metric_on = {(p["left"], p["right"]): _finite(p["adjustment_px"])
                          for p in capture["metric_pairs_on"]}
        self.source_pairs = {(p["left"], p["right"]): _finite(p["adjustment_px"])
                             for p in capture["source_pairs"]} if reference_geometry == "source" else {}
        for glyph in self.glyphs.values():
            _finite(glyph["source_advance_px"] if reference_geometry == "source" else glyph["finalized_advance_px"])
        self._windows = {}
        self._profiles = {}
        self._references = {}
        self._pairs = {}
        self._fit = None
        self._settings = None
        self.identity = hashlib.sha256(_canonical(dict(capture=self.capture,
            samples_per_px=samples_per_px, policy=self.policy, reference_geometry=reference_geometry,
            relative_depth=RELATIVE_DEPTH, visual_depth_factor=VISUAL_DEPTH_FACTOR)).encode()
            + Path(__file__).read_bytes() + Path(hu.__file__).read_bytes()
            + Path(walls.__file__).read_bytes()).hexdigest()

    def _step(self, text):
        a, b = map(ord, text)
        if self.reference_geometry == "source":
            return self.glyphs[a]["source_advance_px"] + self.source_pairs.get((a, b), 0.)
        return self.glyphs[a]["finalized_advance_px"] + self.metric_on.get((a, b), 0.)

    def _window(self, basis):
        if basis in self._windows:
            return self._windows[basis]
        cp = ord({"lowercase": "n", "uppercase": "H", "digits": "0"}[basis])
        glyph = self.glyphs.get(cp)
        result = None
        if glyph:
            rows = walls._bitmap_rows(glyph["bitmap"])
            if rows:
                result = (-max(rows) - 1., -min(rows) * 1.)
        self._windows[basis] = result
        return result

    def _profile(self, cp, window, source=False):
        key = (cp, tuple(window), source)
        if key not in self._profiles:
            glyph = self.glyphs[cp]
            self._profiles[key] = (hu.source_depth_profile(glyph["source_commands"], self.scale,
                                                         tuple(window), self._settings) if source else
                                   hu.depth_profile(glyph["bitmap"], tuple(window), self._settings))
        return self._profiles[key]

    @staticmethod
    def _offset(a, b):
        return math.fsum(y - x for x, y in zip(a.filtered_right, b.filtered_left)) / len(a.ys)

    def _fit_depth(self):
        """Initialize published parameters lazily; the legacy name is internal.

        The ``fit`` metadata container is retained for the existing preview
        interface. Its method/status explicitly state that no fit is performed.
        """
        if self._settings is None:
            self._settings = hu.Settings(RELATIVE_DEPTH, VISUAL_DEPTH_FACTOR, self.samples_per_px)
            self._fit = dict(status="published_parameters", method="published_parameters",
                relative_depth=RELATIVE_DEPTH, visual_depth_factor=VISUAL_DEPTH_FACTOR,
                reference_url=PARAMETER_REFERENCE,
                source_sections=["Processing step C: DepthFactor", "Processing step D: GlobalDepthParameter"],
                coefficient_provenance="US5768490A_published_values", fit_pairs=[],
                evaluated_settings=0, residuals=[], warnings=[])

    def _reference(self, basis, kind="generic"):
        if kind != "generic":
            raise ValueError("Hu/Hersch uses one generic filtered-wall measurement for every pair")
        if basis in self._references:
            return self._references[basis]
        text = REFERENCES[basis]["generic"]
        result = dict(status="unavailable", reference_pair=text, reason="missing_reference_glyph")
        window = self._window(basis)
        if window and all(ord(c) in self.glyphs for c in text):
            try:
                a, b = [self._profile(ord(c), window, self.reference_geometry == "source") for c in text]
            except UnsupportedGeometry as error:
                if self.reference_geometry != "source":
                    raise
                result.update(reason="unsupported_reference_geometry", detail=str(error))
                self._references[basis] = result
                return result
            offset = self._offset(a, b)
            gap = self._step(text) + offset
            height = window[1] - window[0]
            result.update(reason=None, maintained_step_px=self._step(text), offset_px=offset,
                          measurement_window_px=list(window), window_height_px=height,
                          target_px=gap, target_area_px2=gap * height,
                          measurement_method=hu.SOURCE_POLICY if self.reference_geometry == "source" else hu.POLICY)
            if self.reference_geometry == "source":
                result.pop("maintained_step_px")
                result.update(source_step_px=self._step(text),
                              source_metric_quantization=self.capture.get("source_metric_quantization"))
            if a.bounds is None or b.bounds is None:
                result.update(reason="empty_reference_geometry")
            elif not walls.shared_ink_rows(a, b):
                result.update(reason="no_shared_ink_rows")
            elif gap <= 0:
                result.update(reason="nonpositive_target")
            else:
                result["status"] = "available"
        self._references[basis] = result
        return result

    def _target(self, basis):
        if basis != "mixed":
            return self._reference(basis)
        lower, upper = (self._reference(b) for b in ("lowercase", "uppercase"))
        if any(v["status"] != "available" for v in (lower, upper)):
            return dict(status="unavailable", reason="reference_unavailable", reference_pair=None)
        # Hersch averages areas and heights independently. Averaged endpoints
        # give a common window with exactly that mean height.
        window = [(x + y) / 2 for x, y in zip(lower["measurement_window_px"], upper["measurement_window_px"])]
        height = (lower["window_height_px"] + upper["window_height_px"]) / 2
        area = (lower["target_area_px2"] + upper["target_area_px2"]) / 2
        return dict(status="available", reason=None, reference_pair=lower["reference_pair"] + "/" + upper["reference_pair"],
                    measurement_window_px=window, window_height_px=height, target_area_px2=area, target_px=area / height)

    def pair(self, left, right):
        key = (left, right)
        if key not in self._pairs:
            self._pairs[key] = self._pair(left, right)
        return copy.deepcopy(self._pairs[key])

    def _pair(self, left, right):
        basis = pair_basis(left, right)
        if basis is None:
            return dict(reason="unsupported_calibration_class", detail="Latin case or ASCII numeral class required")
        self._fit_depth()
        target = self._target(basis)
        if target["status"] != "available":
            return dict(reason="calibration_unavailable", detail=target["reason"], calibration_basis=basis)
        window = tuple(target["measurement_window_px"])
        profiles = [self._profile(cp, window) for cp in (left, right)]
        if any(p.bounds is None for p in profiles):
            return dict(reason="empty_geometry", calibration_basis=basis)
        if not walls.shared_ink_rows(*profiles):
            return dict(reason="no_shared_ink_rows", calibration_basis=basis)
        offset = self._offset(*profiles)
        return dict(reason=None, calibration_basis=basis, target_provenance=self.target_provenance,
            reference_pair=target["reference_pair"], target_px=target["target_px"],
            target_area_px2=target["target_area_px2"], window_height_px=target["window_height_px"],
            measurement_window_px=list(window), offset_px=offset,
            optical_step_px=target["target_px"] - offset,
            hu_hersch=dict(facing_classes=[dict(kind="generic", reason="uniform_filtered_wall_measurement")] * 2,
                facing_reference_kind="generic",
                fallback_reason="experimental_digits_generic_only" if basis == "digits" else None,
                depth_settings=asdict(self._settings), parameter_method="published_parameters",
                parameter_reference=PARAMETER_REFERENCE, source_classification_used=False,
                fit_status="published_parameters", fit_warnings=[],
                left_cavities=[asdict(c) for c in profiles[0].right_cavities],
                right_cavities=[asdict(c) for c in profiles[1].left_cavities],
                measurement_method=hu.POLICY, calibration_geometry=self.reference_geometry,
                reference_measurement_method=hu.SOURCE_POLICY if self.reference_geometry == "source" else hu.POLICY))

    def metadata(self, evaluate=True):
        base = dict(policy=self.policy, measurement_method=hu.POLICY,
            calibration_geometry=self.reference_geometry, target_provenance=self.target_provenance,
            parameter_method="published_parameters", parameter_reference=PARAMETER_REFERENCE,
            samples_per_px=self.samples_per_px, identity=self.identity,
            limits=dict(numerals="experimental ASCII 00 generic-only adaptation",
                windows="tight delivered n/H/0 bounds; mixed endpoints, heights and areas averaged separately",
                pair_measurement="one generic filtered-wall model for references and all candidate pairs; no classified border shortcut",
                coefficients="US5768490A DepthFactor 0.21 and GlobalDepthParameter 0.25; no optimizer",
                reproduction="delivered-cell discretization and cavity extraction remain project adaptations, not author-code parity"))
        if self.reference_geometry == "source":
            base.update(source_measurement_method=hu.SOURCE_POLICY,
                        source_metric_quantization=self.capture.get("source_metric_quantization"),
                        target_policy="source reference advance + full source pair adjustment + source Hu offset")
            base["limits"].update(source_geometry="continuous source Bezier walls; same delivered-reference body window",
                                  reproduction="source-designed-reference project adaptation; not author-code parity")
        if not evaluate:
            return dict(base, status="not_evaluated", fit=None, references={}, classes={})
        self._fit_depth()
        references = {basis: {"generic": copy.deepcopy(self._reference(basis))} for basis in REFERENCES}
        classes = {basis: copy.deepcopy(self._target(basis)) for basis in (*REFERENCES, "mixed")}
        return dict(base, status="available", fit=copy.deepcopy(self._fit), references=references, classes=classes)
