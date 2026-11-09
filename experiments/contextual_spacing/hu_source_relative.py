"""Source-preserving comparison through the same Hu/Hersch wall transforms.

US5768490A supplies the B/C/D transformations and published depth parameters.
Applying their visual-space measurement to preserve each source-designed pair
through rasterization is a project comparison, not the patent's shared nn/HH
ideal-space solver. Source and delivered geometry use the same physical window
and midpoint grid. The window references supply bounds only, never a target.
"""

import copy
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path

from calibration import pair_basis
import filtered_walls as walls
import hu_hersch as hu


POLICY = "hu-hersch-source-pair-relative-v1"
PARAMETER_REFERENCE = "https://patents.google.com/patent/US5768490A/en"
WINDOW_REFERENCES = {"lowercase": "n", "uppercase": "H", "digits": "0"}


def _finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("expected a finite Hu source-relative number")
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class HuSourceRelativeModel:
    def __init__(self, capture, samples_per_px=64):
        self.capture = json.loads(_canonical(capture))
        self.glyphs = {g["codepoint"]: g for g in self.capture["glyphs"]}
        self.scale = _finite(capture["size_px"]) / _finite(capture["units_per_em"])
        if self.scale <= 0:
            raise ValueError("size and units per em must be positive")
        self.settings = hu.Settings(hu.PUBLISHED_RELATIVE_DEPTH, hu.PUBLISHED_VISUAL_DEPTH_FACTOR, samples_per_px)
        self.source_pairs = {(p["left"], p["right"]): _finite(p["adjustment_px"])
                             for p in capture["source_pairs"]}
        for glyph in self.glyphs.values():
            _finite(glyph["source_advance_px"])
        self._windows = {}
        self._profiles = {}
        self._measurements = {}
        self.identity = hashlib.sha256(_canonical(dict(capture=self.capture,
            settings=asdict(self.settings), policy=POLICY)).encode()
            + Path(__file__).read_bytes() + Path(hu.__file__).read_bytes()
            + Path(walls.__file__).read_bytes()).hexdigest()

    def _window(self, basis):
        if basis in self._windows:
            return self._windows[basis]
        if basis == "mixed":
            lower, upper = (self._window(b) for b in ("lowercase", "uppercase"))
            result = (tuple((a + b) / 2 for a, b in zip(lower, upper))
                      if lower is not None and upper is not None else None)
        else:
            glyph = self.glyphs.get(ord(WINDOW_REFERENCES[basis]))
            rows = walls._bitmap_rows(glyph["bitmap"]) if glyph else {}
            result = (-max(rows) - 1., -min(rows) * 1.) if rows else None
        self._windows[basis] = result
        return result

    def _profile(self, cp, window, source):
        key = (cp, tuple(window), source)
        if key not in self._profiles:
            glyph = self.glyphs[cp]
            self._profiles[key] = (hu.source_depth_profile(glyph["source_commands"], self.scale,
                                                         tuple(window), self.settings) if source else
                                   hu.depth_profile(glyph["bitmap"], tuple(window), self.settings))
        return self._profiles[key]

    def _measure(self, left, right):
        key = (left, right)
        if key in self._measurements:
            return self._measurements[key]
        basis = pair_basis(left, right)
        if basis is None:
            result = dict(reason="unsupported_calibration_class", detail="Latin case or ASCII numeral class required")
        else:
            window = self._window(basis)
            result = dict(reason="calibration_unavailable", calibration_basis=basis,
                          detail="missing or empty delivered window reference")
            if window is not None:
                source = [self._profile(cp, window, True) for cp in key]
                delivered = [self._profile(cp, window, False) for cp in key]
                if any(p.bounds is None for p in (*source, *delivered)):
                    result.update(reason="empty_geometry", detail="source or delivered pair has empty geometry")
                elif not walls.shared_ink_rows(*source) or not walls.shared_ink_rows(*delivered):
                    result.update(reason="no_shared_ink_rows", detail="source or delivered pair has no shared ink rows in the common window")
                else:
                    result = dict(reason=None, calibration_basis=basis,
                        target_provenance="source_pair_hu_hersch",
                        reference_pair=None, measurement_window_px=list(window),
                        window_height_px=window[1] - window[0],
                        source_advance_px=self.glyphs[left]["source_advance_px"],
                        source_pair_adjustment_px=self.source_pairs.get(key, 0.),
                        source_hu_offset_px=hu.pair_offset(*source),
                        delivered_hu_offset_px=hu.pair_offset(*delivered),
                        hu_hersch=dict(measurement_method=POLICY,
                            source_measurement_method=hu.SOURCE_POLICY,
                            delivered_measurement_method=hu.POLICY,
                            depth_settings=asdict(self.settings), parameter_method="published_parameters",
                            parameter_reference=PARAMETER_REFERENCE,
                            source_classification_used=False, facing_reference_kind="generic",
                            fit_status="published_parameters", fit_warnings=[],
                            window_reference_only=True,
                            target_policy="source advance + k * source pair adjustment + source Hu offset"))
        self._measurements[key] = result
        return result

    def pair(self, left, right, source_kerning=1.):
        strength = _finite(source_kerning)
        if not 0 <= strength <= 1:
            raise ValueError("source kerning strength must be in [0, 1]")
        result = copy.deepcopy(self._measure(left, right))
        if result.get("reason"):
            return result
        step = _finite(result["source_advance_px"] + strength * result["source_pair_adjustment_px"])
        target = _finite(step + result["source_hu_offset_px"])
        result.update(source_step_px=step, source_target_px=target, target_px=target,
                      target_area_px2=_finite(target * result["window_height_px"]),
                      offset_px=result["delivered_hu_offset_px"],
                      optical_step_px=_finite(target - result["delivered_hu_offset_px"]))
        result["hu_hersch"].update(source_kerning=strength, source_step_px=step, source_target_px=target,
                                   source_hu_offset_px=result["source_hu_offset_px"],
                                   delivered_hu_offset_px=result["delivered_hu_offset_px"])
        return result

    def metadata(self, evaluate=True):
        parameters = dict(status="published_parameters", method="published_parameters",
            relative_depth=self.settings.relative_depth, visual_depth_factor=self.settings.visual_depth_factor,
            reference_url=PARAMETER_REFERENCE, coefficient_provenance="US5768490A_published_values",
            fit_pairs=[], evaluated_settings=0, residuals=[], warnings=[])
        base = dict(policy=POLICY, measurement_method=POLICY, source_measurement_method=hu.SOURCE_POLICY,
            delivered_measurement_method=hu.POLICY, calibration_geometry="source_and_delivered",
            target_provenance="source_pair_hu_hersch", parameter_method="published_parameters",
            parameter_reference=PARAMETER_REFERENCE, samples_per_px=self.settings.samples_per_px,
            identity=self.identity, source_metric_quantization=self.capture.get("source_metric_quantization"),
            target_policy="source advance + k * source pair adjustment + source Hu offset",
            limits=dict(window_policy="same tight delivered n/H/0 bounds for source and delivered; mixed endpoints averaged",
                window_references="bounds only; no shared target density and no positive reference target requirement",
                source_geometry="continuous Bezier walls on the same midpoint grid as delivered cells; not rerasterized",
                numeral_policy="experimental ASCII 0 body-window extension",
                model_status="source-preserving project comparison; not the patent's shared ideal-space method"))
        if not evaluate:
            return dict(base, status="not_evaluated", fit=None, references={}, classes={})
        references = {}
        for basis, char in WINDOW_REFERENCES.items():
            window = self._window(basis)
            references[basis] = dict(generic=dict(status="available" if window is not None else "unavailable",
                codepoint=ord(char), reference_pair=char * 2, role="window_only",
                reason=None if window is not None else "missing_or_empty_window_reference",
                measurement_window_px=list(window) if window is not None else None,
                window_height_px=window[1] - window[0] if window is not None else None))
        classes = {basis: dict(status="available" if self._window(basis) is not None else "unavailable",
                               measurement_window_px=list(self._window(basis)) if self._window(basis) is not None else None)
                   for basis in (*WINDOW_REFERENCES, "mixed")}
        return dict(base, status="available", fit=parameters, references=references, classes=classes)
