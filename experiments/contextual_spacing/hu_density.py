"""Fixed-alphabet density constraints through the existing Hu/Hersch walls.

Hu section 4.4 and US5768490A ground the filtered-wall measure and generic
ideal-space solve. Fixing the mean source origin step over a complete alphabet
is a project constraint, not a density formula prescribed by those sources.
Both arms use the same relative wall geometry, published B/C/D parameters and
retained delivered-reference windows. No current text calibrates a target.
"""

import copy
from dataclasses import asdict
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

from calibration import pair_basis
from estimator import GeometryError, WorkLimitExceeded
import filtered_walls as walls
import hu_hersch as hu


POLICY = "hu-hersch-fixed-alphabet-density-v1"
PARAMETER_REFERENCE = "https://patents.google.com/patent/US5768490A/en"
REPERTOIRES = {
    "lowercase": tuple(range(ord("a"), ord("z") + 1)),
    "uppercase": tuple(range(ord("A"), ord("Z") + 1)),
    "digits": tuple(range(ord("0"), ord("9") + 1)),
}
TARGET_POLICIES = ("source_origin", "source_alphabet")
CANDIDATE_GEOMETRIES = ("bitmap", "fitted_outline", "source")
CONSTRUCTION_POLICIES = ("windowed", "full_outline")
FULL_FITTED_MEASUREMENT = "hu-hersch-patent-full-fitted-walls-v1"
FULL_SOURCE_MEASUREMENT = "hu-hersch-patent-full-source-walls-v1"


def _finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("expected a finite density calibration number")
    return value


def _canonical(value):
    # Invalid nonfinite geometry is hashed but never emitted; its entire class
    # is explicitly unavailable. This keeps diagnostic identities deterministic.
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@lru_cache(maxsize=512)
def _sample_profile(payload, geometry, scale, window, settings, construction_policy="windowed"):
    """Share bounded immutable profiles across the two calibration arms."""
    data = json.loads(payload)
    if construction_policy == "full_outline":
        return hu.full_source_depth_profile(data, scale, window, settings)
    if geometry == "bitmap":
        return hu.depth_profile(data, window, settings)
    return hu.source_depth_profile(data, scale, window, settings)


class HuDensityModel:
    def __init__(self, capture, samples_per_px=64, target_policy="source_origin", candidate_geometry="bitmap",
                 construction_policy="windowed"):
        if target_policy not in TARGET_POLICIES:
            raise ValueError("target_policy must be source_origin or source_alphabet")
        if candidate_geometry not in CANDIDATE_GEOMETRIES:
            raise ValueError("candidate_geometry must be bitmap, fitted_outline or source")
        if construction_policy not in CONSTRUCTION_POLICIES:
            raise ValueError("construction_policy must be windowed or full_outline")
        if construction_policy == "full_outline" and candidate_geometry == "bitmap":
            raise ValueError("full-outline construction requires source or fitted outlines")
        self.capture = copy.deepcopy(capture)
        self.target_policy = target_policy
        self.candidate_geometry = candidate_geometry
        self.construction_policy = construction_policy
        self.settings = hu.Settings(hu.PUBLISHED_RELATIVE_DEPTH, hu.PUBLISHED_VISUAL_DEPTH_FACTOR, samples_per_px)
        size, units = _finite(capture["size_px"]), _finite(capture["units_per_em"])
        if size <= 0 or units <= 0:
            raise ValueError("size and units per em must be positive")
        self.scale = size / units
        self.glyphs = {glyph["codepoint"]: glyph for glyph in self.capture["glyphs"]}
        if len(self.glyphs) != len(self.capture["glyphs"]):
            raise ValueError("duplicate captured glyph")
        self.source_pairs = {}
        self.duplicate_source_pairs = set()
        for pair in self.capture["source_pairs"]:
            key = (pair["left"], pair["right"])
            if key in self.source_pairs:
                self.duplicate_source_pairs.add(key)
            self.source_pairs[key] = pair["adjustment_px"]
        self._profiles = {}
        self._classes = {}
        self._windows = {}
        self._pairs = {}
        self.identity = hashlib.sha256(_canonical(dict(
            capture=self.capture, policy=POLICY, target_policy=target_policy,
            candidate_geometry=candidate_geometry, construction_policy=construction_policy,
            settings=asdict(self.settings))).encode()
            + Path(__file__).read_bytes() + Path(hu.__file__).read_bytes()
            + Path(walls.__file__).read_bytes() + Path(__file__).with_name("estimator.py").read_bytes()
            + Path(__file__).with_name("calibration.py").read_bytes()).hexdigest()

    @property
    def target_provenance(self):
        return "fixed_alphabet_" + self.target_policy + "_hu_hersch" + (
            "_full_outline" if self.construction_policy == "full_outline" else "")

    @property
    def candidate_measurement_method(self):
        if self.construction_policy == "full_outline":
            return FULL_SOURCE_MEASUREMENT if self.candidate_geometry == "source" else FULL_FITTED_MEASUREMENT
        return {"bitmap": hu.POLICY, "source": hu.SOURCE_POLICY,
                "fitted_outline": "hu-hersch-patent-sampled-fitted-pixel-walls-v1"}[self.candidate_geometry]

    @staticmethod
    def _products(basis):
        if basis == "mixed":
            lower, upper = REPERTOIRES["lowercase"], REPERTOIRES["uppercase"]
            return ((lower, upper), (upper, lower))
        repertoire = REPERTOIRES[basis]
        return ((repertoire, repertoire),)

    def _window(self, basis):
        if basis not in self._windows:
            if basis == "mixed":
                lower, upper = self._window("lowercase"), self._window("uppercase")
                result = tuple((a + b) / 2 for a, b in zip(lower, upper)) if lower and upper else None
            else:
                glyph = self.glyphs.get(ord({"lowercase": "n", "uppercase": "H", "digits": "0"}[basis]))
                rows = walls._bitmap_rows(glyph["bitmap"]) if glyph else {}
                result = (-max(rows) - 1., -min(rows) * 1.) if rows else None
            self._windows[basis] = result
        return self._windows[basis]

    def _profile(self, cp, window, geometry):
        key = (cp, tuple(window), geometry)
        if key not in self._profiles:
            glyph = self.glyphs[cp]
            field = {"source": "source_commands", "fitted_outline": "produced_commands", "bitmap": "bitmap"}[geometry]
            scale = self.scale if geometry == "source" else 1.
            self._profiles[key] = _sample_profile(_canonical(glyph[field]), geometry, scale, tuple(window), self.settings,
                                                  self.construction_policy)
        return self._profiles[key]

    @staticmethod
    def _domain(basis, products):
        return dict(kind="both_ordered_cross_products" if basis == "mixed" else "ordered_cartesian_including_repeats",
                    products=[dict(left_codepoints=list(left), right_codepoints=list(right)) for left, right in products],
                    ordered_pairs=sum(len(left) * len(right) for left, right in products))

    @staticmethod
    def _mean_offset(profiles, products, count):
        means = {cp: (math.fsum(profile.filtered_left) / len(profile.ys),
                      math.fsum(profile.filtered_right) / len(profile.ys))
                 for cp, profile in profiles.items()}
        return _finite(math.fsum(len(left) * len(right) * (
            math.fsum(means[cp][0] for cp in right) / len(right)
            - math.fsum(means[cp][1] for cp in left) / len(left))
            for left, right in products) / count)

    def _calibrate(self, basis):
        products = self._products(basis)
        domain = self._domain(basis, products)
        count = domain["ordered_pairs"]
        repertoire = sorted({cp for left, right in products for cp in (*left, *right)})
        record = dict(status="unavailable", reason=None, detail=None, calibration_basis=basis,
            reference_pair="fixed ASCII " + basis + " alphabet", pair_domain=domain,
            repertoire_codepoints=repertoire, pair_count=count, target_policy=self.target_policy,
            candidate_geometry=self.candidate_geometry, measurement_window_px=None, window_height_px=None,
            mean_source_step_px=None, mean_source_offset_px=None, mean_candidate_offset_px=None,
            source_alphabet_target_px=None, source_origin_target_px=None, target_px=None, target_area_px2=None,
            continuous_mean_step_px=None, continuous_mean_origin_residual_px=None, source_offset_diagnostic=None)
        missing = [cp for cp in repertoire if cp not in self.glyphs]
        if missing:
            return dict(record, reason="missing_calibration_glyph", detail="missing fixed codepoints", missing_codepoints=missing)
        try:
            window = self._window(basis)
        except WorkLimitExceeded:
            raise
        except (GeometryError, ValueError, KeyError, TypeError) as error:
            return dict(record, reason="invalid_calibration_geometry", detail=str(error))
        if window is None:
            return dict(record, reason="missing_window_reference", detail="empty delivered n/H/0 window reference")
        record.update(measurement_window_px=list(window), window_height_px=window[1] - window[0])
        try:
            advances = {cp: _finite(self.glyphs[cp]["source_advance_px"]) for cp in repertoire}
            steps = []
            for left, right in products:
                pairs = [(a, b) for a in left for b in right]
                if any(key in self.duplicate_source_pairs for key in pairs):
                    raise ValueError("duplicate source calibration pair")
                kern = math.fsum(_finite(self.source_pairs.get(key, 0.)) for key in pairs)
                steps.append(math.fsum(advances[cp] for cp in left) * len(right) + kern)
            mean_step = _finite(math.fsum(steps) / count)
        except (ValueError, KeyError, TypeError) as error:
            return dict(record, reason="invalid_calibration_source_metric", detail=str(error))
        source_profiles = None
        source_failure = None
        try:
            source_profiles, source_failure = self._domain_profiles(repertoire, products, window, "source")
        except WorkLimitExceeded as error:
            if self.target_policy == "source_alphabet" or self.candidate_geometry == "source":
                raise
            source_failure = dict(reason="work_limit_exceeded", detail=str(error), failed_geometry="source")
        if source_failure and (self.target_policy == "source_alphabet" or self.candidate_geometry == "source"):
            return dict(record, **source_failure)
        if self.candidate_geometry == "source":
            candidate_profiles = source_profiles
        else:
            candidate_profiles, candidate_failure = self._domain_profiles(
                repertoire, products, window, self.candidate_geometry)
            if candidate_failure:
                return dict(record, **candidate_failure)
        source_offset = self._mean_offset(source_profiles, products, count) if source_profiles is not None else None
        candidate_offset = self._mean_offset(candidate_profiles, products, count)
        source_target = _finite(mean_step + source_offset) if source_offset is not None else None
        origin_target = _finite(mean_step + candidate_offset)
        target = source_target if self.target_policy == "source_alphabet" else origin_target
        continuous_step = _finite(target - candidate_offset)
        record.update(source_offset_diagnostic=dict(status="available", reason=None) if source_failure is None else
                      dict(status="unavailable", **source_failure),
                      mean_source_step_px=mean_step, mean_source_offset_px=source_offset,
                      mean_candidate_offset_px=candidate_offset, source_alphabet_target_px=source_target,
                      source_origin_target_px=origin_target, target_px=target,
                      target_area_px2=_finite(target * record["window_height_px"]),
                      continuous_mean_step_px=continuous_step,
                      continuous_mean_origin_residual_px=_finite(continuous_step - mean_step))
        if target <= 0:
            return dict(record, reason="nonpositive_target", detail="fixed-domain target must be positive")
        return dict(record, status="available")

    def _domain_profiles(self, repertoire, products, window, geometry):
        profiles = {}
        for cp in repertoire:
            try:
                profile = self._profile(cp, window, geometry)
            except WorkLimitExceeded:
                raise
            except (GeometryError, ValueError, KeyError, TypeError) as error:
                return None, dict(reason="invalid_calibration_geometry", detail=str(error),
                                  failed_codepoint=cp, failed_geometry=geometry)
            if profile.bounds is None:
                return None, dict(reason="empty_calibration_geometry", detail="empty fixed calibration glyph",
                                  failed_codepoint=cp, failed_geometry=geometry)
            profiles[cp] = profile
        masks = {cp: sum(1 << i for i, ink in enumerate(profile.occupied) if ink)
                 for cp, profile in profiles.items()}
        for left, right in products:
            for a in left:
                for b in right:
                    if not masks[a] & masks[b]:
                        return None, dict(reason="no_shared_calibration_ink_rows",
                                          detail="fixed pair has no shared ink in the common window",
                                          failed_pair=[a, b], failed_geometry=geometry)
        return profiles, None

    def _class(self, basis):
        if basis not in self._classes:
            self._classes[basis] = self._calibrate(basis)
        return self._classes[basis]

    def pair(self, left, right):
        key = (left, right)
        if key not in self._pairs:
            self._pairs[key] = self._pair(left, right)
        return copy.deepcopy(self._pairs[key])

    def _pair(self, left, right):
        basis = pair_basis(left, right)
        if basis is None:
            return dict(reason="unsupported_calibration_class", detail="Latin case or ASCII numeral class required")
        target = self._class(basis)
        provenance = dict(calibration_basis=basis, target_provenance=self.target_provenance,
                          reference_pair=target["reference_pair"])
        if target["status"] != "available":
            return dict(provenance, reason="calibration_unavailable", detail=target["reason"])
        window = tuple(target["measurement_window_px"])
        try:
            profiles = [self._profile(cp, window, self.candidate_geometry) for cp in (left, right)]
        except WorkLimitExceeded:
            raise
        except (GeometryError, ValueError, KeyError, TypeError) as error:
            return dict(provenance, reason="calibration_unavailable", detail="invalid_candidate_geometry: " + str(error))
        if any(profile.bounds is None for profile in profiles):
            return dict(provenance, reason="empty_geometry")
        if not walls.shared_ink_rows(*profiles):
            return dict(provenance, reason="no_shared_ink_rows")
        offset = hu.pair_offset(*profiles)
        return dict(provenance, reason=None, target_px=target["target_px"],
                    target_area_px2=target["target_area_px2"], window_height_px=target["window_height_px"],
                    measurement_window_px=list(window), offset_px=offset,
                    optical_step_px=_finite(target["target_px"] - offset),
                    hu_hersch=dict(measurement_method=self.candidate_measurement_method,
                        candidate_geometry=self.candidate_geometry, target_policy=self.target_policy,
                        calibration_pair_count=target["pair_count"], reference_kind="fixed_complete_ascii_alphabet",
                        depth_settings=asdict(self.settings), parameter_method="published_parameters",
                        parameter_reference=PARAMETER_REFERENCE, source_classification_used=False,
                        fit_status="published_parameters", fit_warnings=[],
                        **(dict(construction_policy="full_outline", cavity_supports="post_B",
                                construction_windows_px=[list(p.construction_window) for p in profiles],
                                global_depth_height_px=target["window_height_px"])
                           if self.construction_policy == "full_outline" else {})))

    def metadata(self, evaluate=True):
        classes = {basis: copy.deepcopy(self._class(basis)) for basis in (*REPERTOIRES, "mixed")} if evaluate else {}
        return dict(policy=POLICY + ("-full-outline" if self.construction_policy == "full_outline" else ""),
            status="available" if evaluate else "not_evaluated", identity=self.identity,
            measurement_method=self.candidate_measurement_method,
            source_measurement_method=FULL_SOURCE_MEASUREMENT if self.construction_policy == "full_outline" else hu.SOURCE_POLICY,
            source_scale_px_per_design_unit=self.scale, candidate_coordinate_scale=self.scale if self.candidate_geometry == "source" else 1.,
            target_policy=self.target_policy, target_provenance=self.target_provenance,
            candidate_geometry=self.candidate_geometry, calibration_geometry="source_and_" + self.candidate_geometry,
            source_metric_quantization=self.capture.get("source_metric_quantization"), samples_per_px=self.settings.samples_per_px,
            parameter_method="published_parameters", parameter_reference=PARAMETER_REFERENCE,
            target_formula="mean(source_step + source_offset)" if self.target_policy == "source_alphabet" else "mean(source_step + candidate_offset)",
            classes=classes, references={}, fit=dict(status="published_parameters", method="published_parameters",
                relative_depth=self.settings.relative_depth, visual_depth_factor=self.settings.visual_depth_factor,
                reference_url=PARAMETER_REFERENCE, coefficient_provenance="US5768490A_published_values",
                fit_pairs=[], evaluated_settings=0, residuals=[], warnings=[]),
            limits=dict(calibration="complete fixed ASCII Cartesian domains; no partial or text-derived repertoire",
                mixed="both ordered cross-products on one averaged n/H endpoint window",
                windows="tight delivered n/H/0 bounds; mixed endpoints averaged",
                coordinates="source design units scaled by size/upm; fitted commands already pixels y-up; bitmap full-cell pixel edges",
                numerals="experimental ASCII 0-9 adaptation", source_metrics="full source kerning independent of runtime strength",
                density="continuous calibration-domain mean only; not arbitrary words or emitted guarded mean",
                source_diagnostic="source-origin requires source metrics and candidate walls; source wall mean is optional",
                reproduction="fixed-alphabet normalization is a project adaptation, not author-code parity"),
            **(dict(construction_policy="full_outline", cavity_supports="post_B",
                    construction_domain="complete outline bounds; body grid extended by whole sample intervals",
                    integration_domain="retained class body window", global_depth_height="class body height")
               if self.construction_policy == "full_outline" else {}))
