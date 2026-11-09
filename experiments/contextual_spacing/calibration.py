"""Source reference density for the isolated optical-spacing solvers.

Hersch et al. 1995 pp. 85–88 ground designed nn/HH references and mixed-case
means. Applying that principle to FontForge's *linear* estimator is a project
adaptation, not Hersch's filtered-area algorithm. ASCII 00 is an experimental
numeral extension of the reference-pair principle; it is not a published digit
spacing prescription. Unicode gating bounds these Latin references explicitly.
"""

import copy
import math
import unicodedata

from estimator import analyze, separation, GeometryError, UnsupportedGeometry, WorkLimitExceeded
import filtered_walls

POLICY = "latin-reference-linear-v1"
REFERENCES = {"lowercase": 110, "uppercase": 72, "digits": 48}


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("expected finite calibration number")
    return value


def pair_basis(left, right):
    if all(48 <= cp <= 57 for cp in (left, right)):
        return "digits"
    categories = [unicodedata.category(chr(cp)) for cp in (left, right)]
    if not all(unicodedata.name(chr(cp), "").startswith("LATIN ") for cp in (left, right)):
        return None
    if categories == ["Ll", "Ll"]:
        return "lowercase"
    if categories == ["Lu", "Lu"]:
        return "uppercase"
    if set(categories) == {"Ll", "Lu"}:
        return "mixed"
    return None


class Calibration:
    def __init__(self, capture, glyphs, source_pairs, em, size, subdivisions):
        self.em, self.size, self.subdivisions = em, size, subdivisions
        self.records = {}
        self.cache = {}
        auxiliary = capture.get("source_calibration")
        if auxiliary is not None:
            if not isinstance(auxiliary, dict) or auxiliary.get("schema_version") != "contextual-spacing-source-calibration-v1":
                raise ValueError("unsupported source calibration schema")
            references = auxiliary.get("references")
            if not isinstance(references, list):
                raise ValueError("source calibration references must be a list")
            for reference in references:
                cp = reference.get("codepoint")
                if type(cp) is not int or cp not in REFERENCES.values() or cp in self.records:
                    raise ValueError("invalid or duplicate calibration reference")
                if not isinstance(reference.get("status"), str) or not reference["status"]:
                    raise ValueError("invalid calibration reference status")
                # Validate all supplied numeric source data before any disabled
                # optical path; representability remains optional and lazy.
                for field in ("source_advance_px", "source_pair_adjustment_px"):
                    if field in reference:
                        finite(reference[field])
                for command in reference.get("source_commands", []):
                    for field in ("x", "y", "x1", "y1", "x2", "y2"):
                        if field in command:
                            finite(command[field])
                if reference["status"] == "available":
                    for field in ("source_advance_px", "source_pair_adjustment_px", "source_commands", "glyph_id"):
                        if field not in reference:
                            raise ValueError(f"missing calibration reference field: {field}")
                self.records[cp] = dict(reference, origin="source_calibration")
        else:
            for cp in REFERENCES.values():
                if cp in glyphs:
                    glyph = glyphs[cp]
                    self.records[cp] = dict(codepoint=cp, status="available", glyph_id=glyph["glyph_id"],
                                            source_commands=glyph["source_commands"],
                                            source_advance_px=glyph["source_advance_px"],
                                            source_pair_adjustment_px=source_pairs.get((cp, cp), 0),
                                            origin="capture_repertoire")
        self.provenance = copy.deepcopy(auxiliary.get("provenance")) if auxiliary else None

    def reference(self, basis, evaluate=True):
        cp = REFERENCES[basis]
        record = self.records.get(cp)
        if evaluate and cp in self.cache:
            return copy.deepcopy(self.cache[cp])
        result = dict(codepoint=cp, status="unavailable", target_px=None,
                      origin=record.get("origin") if record else None,
                      reason=None, detail=None)
        if record is None:
            result.update(reason="missing_reference_glyph", detail=f"missing reference {chr(cp)}")
        elif record["status"] != "available":
            result.update(reason=record["status"], detail=record.get("detail", f"reference {chr(cp)} unavailable"))
        elif not evaluate:
            result.update(status="not_evaluated", reason="optical_disabled")
            return result
        else:
            result.update(glyph_id=record["glyph_id"], source_advance_px=record["source_advance_px"],
                          source_pair_adjustment_px=record["source_pair_adjustment_px"])
            try:
                envelope = analyze(record["source_commands"], self.em, self.subdivisions)
                if envelope.bounds is None:
                    result.update(reason="empty_reference_geometry", detail=f"reference {chr(cp)} has no contour")
                else:
                    estimate = separation(envelope, envelope, self.em)
                    if estimate.estimate is None:
                        result.update(reason="reference_no_shared_bands", detail=f"reference {chr(cp)} has no shared bands")
                    else:
                        # Captured advances/kerns are already pixels (26.6 source
                        # metrics); only the geometric design-unit term scales.
                        target = record["source_advance_px"] + record["source_pair_adjustment_px"]
                        target += (envelope.bounds.minx - envelope.bounds.maxx + estimate.estimate) * self.size / self.em
                        if not math.isfinite(target):
                            result.update(reason="unrepresentable_target", detail="reference target exceeds finite pixel range")
                        elif target <= 0:
                            result.update(reason="nonpositive_target", detail=f"reference {chr(cp)} target is {target} px")
                        else:
                            result.update(status="available", target_px=target)
            except (UnsupportedGeometry, WorkLimitExceeded) as error:
                result.update(reason="unrepresentable_reference_geometry", detail=str(error))
        self.cache[cp] = result
        return copy.deepcopy(result)

    def target(self, basis, evaluate=True):
        if basis != "mixed":
            return self.reference(basis, evaluate)
        lower, upper = (self.reference(key, evaluate) for key in ("lowercase", "uppercase"))
        if lower["status"] == upper["status"] == "available":
            return dict(status="available", target_px=(lower["target_px"] + upper["target_px"]) / 2,
                        reason=None, detail=None)
        unavailable = [(key, value) for key, value in (("lowercase", lower), ("uppercase", upper))
                       if value["status"] != "available"]
        return dict(status="not_evaluated" if all(v["status"] == "not_evaluated" for _, v in unavailable) else "unavailable",
                    target_px=None, reason="reference_unavailable",
                    detail="; ".join(f"{key}: {value['reason']}" for key, value in unavailable))

    def metadata(self, evaluate=True):
        return dict(policy=POLICY, unicode_version=unicodedata.unidata_version,
                    target_provenance="font_calibrated", source_provenance=self.provenance,
                    references={key: self.reference(key, evaluate) for key in REFERENCES},
                    classes={key: self.target(key, evaluate) for key in (*REFERENCES, "mixed")},
                    numeral_policy="experimental ASCII 00 reference extension")


class FilteredCalibration:
    """Hu wall-area adaptation using one source-defined window per class.

    Hersch designed reference pairs ground the calibration principle. Source
    reference bounds and the mixed normalized-gap mean are project adaptations;
    ASCII 00 remains experimental. The same wall sampler measures both endpoints.
    """

    def __init__(self, original, samples_per_px=64):
        self.original = original
        self.records = original.records
        self.scale = original.size / original.em
        self.samples_per_px = samples_per_px
        self.cache = {}

    def reference(self, basis, evaluate=True):
        cp = REFERENCES[basis]
        record = self.records.get(cp)
        if evaluate and basis in self.cache:
            return copy.deepcopy(self.cache[basis])
        result = dict(codepoint=cp, status="unavailable", target_px=None,
                      target_area_px2=None, window_height_px=None, measurement_window_px=None,
                      origin=record.get("origin") if record else None, reason=None, detail=None)
        if record is None:
            result.update(reason="missing_reference_glyph", detail=f"missing reference {chr(cp)}")
        elif record["status"] != "available":
            result.update(reason=record["status"], detail=record.get("detail", f"reference {chr(cp)} unavailable"))
        elif not evaluate:
            result.update(status="not_evaluated", reason="optical_disabled")
            return result
        else:
            result.update(glyph_id=record["glyph_id"], source_advance_px=record["source_advance_px"],
                          source_pair_adjustment_px=record["source_pair_adjustment_px"])
            try:
                bounds = filtered_walls.source_bounds(record["source_commands"], self.scale)
                if bounds is None or bounds.maxy <= bounds.miny:
                    result.update(reason="empty_reference_geometry", detail=f"reference {chr(cp)} has no area")
                else:
                    window = (bounds.miny, bounds.maxy)
                    profile = filtered_walls.source_profile(record["source_commands"], self.scale, window,
                                                            self.samples_per_px)
                    if not filtered_walls.shared_ink_rows(profile, profile):
                        result.update(reason="reference_no_shared_rows", detail=f"reference {chr(cp)} has no occupied rows")
                    else:
                        target = record["source_advance_px"] + record["source_pair_adjustment_px"]
                        target += filtered_walls.pair_offset(profile, profile)
                        height = window[1] - window[0]
                        result.update(measurement_window_px=list(window), window_height_px=height)
                        if not math.isfinite(target):
                            result.update(reason="unrepresentable_target", detail="reference target exceeds finite pixel range")
                        elif target <= 0:
                            result.update(reason="nonpositive_target", detail=f"reference {chr(cp)} target is {target} px")
                        else:
                            result.update(status="available", target_px=target, target_area_px2=target * height)
            except GeometryError as error:
                result.update(reason="unrepresentable_reference_geometry", detail=str(error))
        self.cache[basis] = result
        return copy.deepcopy(result)

    def target(self, basis, evaluate=True):
        if basis != "mixed":
            return self.reference(basis, evaluate)
        lower, upper = (self.reference(key, evaluate) for key in ("lowercase", "uppercase"))
        if lower["status"] == upper["status"] == "available":
            target = (lower["target_px"] + upper["target_px"]) / 2
            window = [min(lower["measurement_window_px"][0], upper["measurement_window_px"][0]),
                      max(lower["measurement_window_px"][1], upper["measurement_window_px"][1])]
            height = window[1] - window[0]
            return dict(status="available", target_px=target, target_area_px2=target * height,
                        measurement_window_px=window, window_height_px=height, reason=None, detail=None)
        missing = [(key, value) for key, value in (("lowercase", lower), ("uppercase", upper))
                   if value["status"] != "available"]
        return dict(status="not_evaluated" if all(v["status"] == "not_evaluated" for _, v in missing) else "unavailable",
                    target_px=None, target_area_px2=None, measurement_window_px=None, window_height_px=None,
                    reason="reference_unavailable", detail="; ".join(f"{key}: {v['reason']}" for key, v in missing))

    def metadata(self, evaluate=True):
        return dict(policy="latin-reference-filtered-wall-v1", unicode_version=unicodedata.unidata_version,
                    measurement_method="hu-filtered-walls-midpoint-v1", samples_per_px=self.samples_per_px,
                    target_provenance="font_calibrated", source_provenance=copy.deepcopy(self.original.provenance),
                    window_policy="source reference bounds; mixed union",
                    references={key: self.reference(key, evaluate) for key in REFERENCES},
                    classes={key: self.target(key, evaluate) for key in (*REFERENCES, "mixed")},
                    numeral_policy="experimental ASCII 00 reference extension")
