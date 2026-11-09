"""Pinned CounterSpace reuse with delivered or source calibration controls.

The vendored CounterSpace.py is unchanged. The tensorfont 0.0.6 loader only
updates removed API spellings (numpy.float and skimage.util.pad) and redirects
its internal imports into a private package. Neither compatibility edit changes
masking, smoothing, fitting or scoring. This is an offline numerical experiment,
not a renderer: displayed captured bitmap cells are never regenerated.

A separately identified semantic repair puts binary smoothing output into the
byte-intensity domain expected by tensorfont's original concavity operation,
then restores the normalized mask domain and GlyphRendering metadata.
"""
from collections import OrderedDict
from functools import lru_cache, wraps
import hashlib
import importlib.metadata
import importlib.util
import json
import math
from pathlib import Path
import string
import sys
import tempfile
import threading
import types

ROOT = Path(__file__).parent
REFERENCE = ROOT / "reference" / "counterspace" / "CounterSpace.py"
LOCK = ROOT / "counterspace.lock.json"
_FIT_LOCK = threading.RLock()


class CounterSpaceUnavailable(RuntimeError):
    """Explicit optional-dependency, source identity or calibration failure."""


def _verify_reference():
    """Reject stale pin provenance before executing or reusing reference code."""
    try:
        manifest = json.loads(LOCK.read_text())
        for name in ("CounterSpace.py", "LICENSE"):
            actual = hashlib.sha256((REFERENCE.parent / name).read_bytes()).hexdigest()
            if actual != manifest["files"][name]:
                raise CounterSpaceUnavailable("CounterSpace pinned file SHA-256 mismatch: " + name)
        actual = hashlib.sha256((ROOT / "requirements-counterspace.txt").read_bytes()).hexdigest()
        if actual != manifest["requirements_sha256"]:
            raise CounterSpaceUnavailable("CounterSpace pinned requirements SHA-256 mismatch")
        return manifest
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise CounterSpaceUnavailable("CounterSpace pin verification failed: " + str(error)) from error


def _install_intensity_repair(tensorfont, np):
    original = tensorfont.GlyphRendering.reduce_concavity

    @wraps(original)
    def reduce_concavity(rendering, percent):
        # CounterSpace thresholds its smoothed image to 0/1. Tensorfont's
        # original concavity operation instead samples original contours at
        # intensity 30 (its hull uses 0.1). Keep that operation unchanged and
        # convert only its binary input/output domains. Byte-valued images,
        # including the no-smoothing path, continue through the original call.
        if (rendering.size and np.max(rendering) == 1
                and np.all((rendering == 0) | (rendering == 1))):
            byte = tensorfont.GlyphRendering.init_from_numpy(rendering._glyph, np.asarray(rendering) * 255)
            reduced = original(byte, percent)
            return tensorfont.GlyphRendering.init_from_numpy(rendering._glyph, np.asarray(reduced) / 255)
        return original(rendering, percent)

    tensorfont.GlyphRendering.reduce_concavity = reduce_concavity


@lru_cache(maxsize=1)
def _dependencies():
    _verify_reference()
    try:
        import numpy as np
        import scipy
        from fontTools.ttLib import TTFont
        from fontTools.varLib.instancer import instantiateVariableFont
        distribution = importlib.metadata.distribution("tensorfont")
        if distribution.version != "0.0.6":
            raise CounterSpaceUnavailable("CounterSpace requires tensorfont==0.0.6")
        package = Path(distribution.locate_file("tensorfont"))
        name = "_spacing_tensorfont_006"
        spec = importlib.util.spec_from_file_location(name, package / "__init__.py",
                                                     submodule_search_locations=[str(package)])
        tensorfont = importlib.util.module_from_spec(spec)
        sys.modules[name] = tensorfont
        source = (package / "__init__.py").read_text()
        source = source.replace("from skimage.util import pad", "from numpy import pad")
        source = source.replace("np.float)", "float)").replace("from tensorfont.", f"from {name}.")
        exec(compile(source, str(package / "__init__.py"), "exec"), tensorfont.__dict__)
        _install_intensity_repair(tensorfont, np)
        upstream = types.ModuleType("_spacing_counterspace_upstream")
        # Force the command-line tensorfont backend; GlyphsApp is deliberately
        # irrelevant to this standalone capture adapter.
        code = REFERENCE.read_text().replace("from tensorfont import Font,GlyphRendering",
                                             f"from {name} import Font,GlyphRendering")
        exec(compile(code, str(REFERENCE), "exec"), upstream.__dict__)
        return np, scipy, TTFont, instantiateVariableFont, tensorfont, upstream.CounterSpace
    except (ImportError, OSError, AttributeError) as error:
        raise CounterSpaceUnavailable(
            "CounterSpace optional dependencies unavailable; install requirements-counterspace.txt: " + str(error)) from error


class _CapturedGlyph:
    def __init__(self, font, record):
        np = font.np
        bitmap = record["bitmap"]
        factor = font.factor
        self.font = font
        self.name = chr(record["codepoint"])
        pixels = np.asarray(bitmap["pixels"], dtype=float).reshape(bitmap["height"], bitmap["width"])
        rows, columns = np.nonzero(pixels)
        if not rows.size:
            raise ValueError("empty_geometry")
        y0, y1 = int(rows.min()), int(rows.max()) + 1
        x0, x1 = int(columns.min()), int(columns.max()) + 1
        # Tensorfont's ink metrics delimit its reference window and centered
        # analysis matrices. Storage padding is not ink: crop only this private
        # view and compensate the offsets, leaving every absolute ink cell and
        # finalized advance unchanged. This policy applies to every glyph and
        # to delivered scoring under both calibration geometries.
        pixels = pixels[y0:y1, x0:x1]
        self.ink_width = (x1 - x0) * factor
        self.ink_height = (y1 - y0) * factor
        self.width = record["finalized_advance_px"] * factor
        self.lsb = (bitmap["left"] + x0) * factor
        self.rsb = self.width - self.ink_width - self.lsb
        self.tsb = font.ascender_px + (bitmap["top"] + y0) * factor
        self.height = self.ink_height
        cells = np.repeat(np.repeat(pixels, factor, axis=0), factor, axis=1) * 255
        if self.tsb < 0 or self.tsb + self.ink_height > font.full_height_px:
            raise ValueError("captured_bitmap_outside_reference_canvas")
        matrix = np.zeros((font.full_height_px, self.ink_width))
        matrix[self.tsb:self.tsb + self.ink_height, :] = cells
        self._matrix = font.rendering.init_from_numpy(self, matrix)

    @lru_cache(maxsize=4)
    def as_matrix(self, normalize=False, binarize=False):
        matrix = self._matrix
        if normalize or binarize:
            matrix = matrix / 255
        if binarize:
            matrix = matrix.astype(int)
        return self.font.rendering.init_from_numpy(self, matrix)


class _CapturedFont:
    def __init__(self, capture, source_font, factor, tensorfont):
        self.np = __import__("numpy")
        self.rendering = tensorfont.GlyphRendering
        self.factor = factor
        self.scale_factor = factor * capture["size_px"] / capture["units_per_em"]
        self.ascender_px = source_font.ascender_px
        self.full_height_px = source_font.full_height_px
        self.italic_angle = source_font.italic_angle
        self.baseline_ratio = source_font.baseline_ratio
        self.m_width = source_font.m_width
        self._records = {chr(g["codepoint"]): g for g in capture["glyphs"]}
        self.glyphcache = {}
        self._source_font = source_font
        self._metric_adjustments = {(p["left"], p["right"]): p["adjustment_px"]
                                    for p in capture.get("metric_pairs_on", [])}

    def glyph(self, char):
        if char not in self.glyphcache:
            self.glyphcache[char] = _CapturedGlyph(self, self._records[char])
        return self.glyphcache[char]

    def pair_distance(self, left, right, with_kerning=True):
        # Maintained finalized placement is authoritative for delivered reference
        # geometry: include its full kerning/bearing correction exactly once.
        distance = self.glyph(left).rsb + self.glyph(right).lsb
        if with_kerning:
            distance += self._metric_adjustments.get((ord(left), ord(right)), 0.0) * self.factor
        return distance

    @lru_cache(maxsize=4096)
    def minimum_ink_distance(self, left, right):
        return self.np.min(self.glyph(left).as_matrix().right_contour()
                           + self.glyph(right).as_matrix().left_contour())

    def shift_distances(self, left, right, dist):
        # Exact tensorfont placement equations, not a replacement approximation.
        return self._source_font.__class__.shift_distances(self, left, right, dist)


class _BoundedMasks(OrderedDict):
    """Evicting derived masks changes memory use, never upstream arithmetic."""
    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.move_to_end(key)
        while len(self) > 256:
            self.popitem(last=False)


class CounterSpaceModel:
    def __init__(self, capture, calibration_geometry="delivered"):
        if calibration_geometry not in ("delivered", "source"):
            raise ValueError("calibration_geometry must be delivered or source")
        self.calibration_geometry = calibration_geometry
        # Validate on each model too: dependency imports may already be cached.
        _verify_reference()
        self.capture = capture
        self._pair_cache = {}
        self._score_cache = {}
        self._temporary = tempfile.TemporaryDirectory(prefix="spacing-counterspace-")
        np, scipy, TTFont, instantiate, tensorfont, Engine = _dependencies()
        self.np = np
        source = Path(capture["font_path"])
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != capture["source_sha256"]:
            raise CounterSpaceUnavailable("CounterSpace source font missing or SHA-256 does not match capture")
        font = TTFont(source)
        axes = dict(capture.get("axes", {}))
        if "fvar" in font:
            axes = {axis.axisTag: axes.get(axis.axisTag, axis.defaultValue) for axis in font["fvar"].axes}
            font = instantiate(font, axes, inplace=False)
        elif axes:
            raise CounterSpaceUnavailable("capture declares variation axes for a static font")
        instance = Path(self._temporary.name) / "source-instance.ttf"
        font.recalcTimestamp = False
        font.save(instance)
        self.instance_sha256 = hashlib.sha256(instance.read_bytes()).hexdigest()
        self.axes = axes
        # Integer cell expansion avoids filtering or changing captured forms.
        # Analysis is close to the upstream 90px x-height, in explicitly declared
        # physical units: one delivered pixel equals factor analysis pixels.
        probe = tensorfont.Font(str(instance), 90)
        source_xheight_px = 90 / probe.scale_factor * capture["size_px"] / capture["units_per_em"]
        self.factor = max(1, math.ceil(90 / source_xheight_px))
        xheight = source_xheight_px * self.factor
        self.source = Engine(str(instance), x_height_in_pixels=xheight,
                             key_pairs=["HH", "OO", "HO", "OH", "EE", "AV"])
        self.source.full_height_px = self.source.font.full_height_px
        self.key_pairs = list(self.source.key_pairs)
        # Calibration placements are capture-authoritative source metrics. The
        # upstream font remains the calibration rasterizer, never display output.
        glyphs = {g["codepoint"]: g for g in capture["glyphs"]}
        adjustments = {(p["left"], p["right"]): p["adjustment_px"] for p in capture["source_pairs"]}
        def pair_distance(left, right, with_kerning=True):
            key = (ord(left), ord(right))
            if ord(left) not in glyphs:
                raise CounterSpaceUnavailable("missing source calibration pair: " + left + right)
            step = glyphs[ord(left)]["source_advance_px"]
            if with_kerning:
                step += adjustments.get(key, 0.0)
            return (step * self.factor + self.source.font.glyph(right).lsb
                    - self.source.font.glyph(left).lsb - self.source.font.glyph(left).ink_width)
        self.source.font.pair_distance = pair_distance
        # The candidate and control share original upstream initialization and
        # measurement code. Only their calibration backend differs.
        self.delivered = Engine(str(instance), x_height_in_pixels=xheight,
                                key_pairs=list(self.key_pairs))
        self.delivered.font = _CapturedFont(capture, self.source.font, self.factor, tensorfont)
        if calibration_geometry == "delivered" and "m" in self.delivered.font._records:
            self.delivered.font.m_width = self.delivered.font._records["m"]["finalized_advance_px"] * self.factor
        self.delivered._lshifted_counters = _BoundedMasks()
        self.delivered._rshifted_counters = _BoundedMasks()
        self.calibration = self.delivered if calibration_geometry == "delivered" else self.source
        optimizer_results = []
        minimize = scipy.optimize.minimize
        def observed_minimize(*args, **kwargs):
            result = minimize(*args, **kwargs)
            optimizer_results.append({"success": bool(result.success), "status": int(result.status),
                                      "message": str(result.message), "objective": float(result.fun),
                                      "evaluations": int(result.nfev)})
            return result
        with _FIT_LOCK:
            scipy.optimize.minimize = observed_minimize
            try:
                options = self.calibration.determine_parameters()
            finally:
                scipy.optimize.minimize = minimize
        if not options or not all(math.isfinite(float(v)) for v in options.values()):
            raise CounterSpaceUnavailable("CounterSpace returned nonfinite fit parameters")
        self.fit = optimizer_results
        self.options = {k: float(v) for k, v in options.items()}
        self.source.options = self.options
        self.delivered.options = self.options
        self._targets = {}
        reference_placements = []
        for reference in self.key_pairs + ["nn"]:
            window_reference = self.calibration.reference_pair(*reference)
            score = float(np.sum(self.calibration.pair_area(*reference, self.options, reference=window_reference)))
            if not math.isfinite(score) or score <= 0:
                raise CounterSpaceUnavailable("invalid CounterSpace reference score: " + reference)
            l, r = reference
            lg, rg = self.calibration.font.glyph(l), self.calibration.font.glyph(r)
            bbox_distance = self.calibration.font.pair_distance(l, r)
            origin_step = (bbox_distance + lg.lsb + lg.ink_width - rg.lsb) / self.factor
            advance_key = "finalized_advance_px" if calibration_geometry == "delivered" else "source_advance_px"
            advance = glyphs[ord(l)][advance_key]
            reference_placements.append(dict(pair=reference, window_reference=window_reference, origin_step_px=float(origin_step),
                                             advance_px=float(advance), pair_adjustment_px=float(origin_step - advance),
                                             bbox_distance_analysis_px=float(bbox_distance), score=score))
            if reference in ("HH", "nn"):
                self._targets[reference] = score
        self._metadata = {
            "model": "counterspace-pinned-captured-cells-v4",
            "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "tensorfont_source_sha256": hashlib.sha256(Path(tensorfont.__file__).read_bytes()).hexdigest(),
            "dependency_versions": {name: importlib.metadata.version(name) for name in
                                    ("numpy", "scipy", "tensorfont", "scikit-image", "freetype-py", "fonttools")},
            "upstream": json.loads(LOCK.read_text()), "axes": self.axes,
            "source_sha256": capture["source_sha256"], "instance_sha256": self.instance_sha256,
            "analysis_pixels_per_delivered_pixel": self.factor,
            "calibration_geometry": calibration_geometry,
            "calibration_geometry_description": (
                "captured maintained 1-bit reference cells and finalized advance plus full metric-on pair adjustment"
                if calibration_geometry == "delivered" else
                "upstream tensorfont grayscale raster of axis-instantiated source; capture source pair metrics"),
            "reference_placements": reference_placements,
            "delivered_geometry": "captured maintained 1-bit cells, tight nonzero ink bounds and exact integer nearest-cell expansion; baseline y-down",
            "ink_bounds_policy": "tight-nonzero-captured-cells-v1: analysis-only crop with compensated offsets; storage padding is excluded from ink metrics and reference windows",
            "intensity_policy": "binary-concavity-byte-domain-v1: original tensorfont concavity reduction receives binary smoothed ink as 0/255, then returns 0/1 with GlyphRendering metadata; byte and blank paths unchanged",
            "target_score_units": "upstream Gaussian-weighted analysis-cell area, not a distance",
            "key_pairs": self.key_pairs, "options": self.options, "optimizer_results": self.fit,
            "fit_status": "converged" if all(r["success"] for r in self.fit) else "upstream_optimizer_did_not_converge",
            "reference_scores": self._targets,
            "candidate_policy": "bounded whole-pixel origins; closest feasible score with smaller-step ties by default; original first crossing retained as control",
            "default_search_policy": "closest_feasible",
            "upstream_bare_minimum_design_units": 50,
            "upstream_serif_smoothing_analysis_pixels": 2,
        }

    def metadata(self):
        return json.loads(json.dumps(self._metadata, allow_nan=False))

    def measure_pair(self, left, right, step):
        key = (left, right, float(step))
        if key not in self._score_cache:
            l, r = chr(left), chr(right)
            font = self.delivered.font
            dist = step * self.factor + font.glyph(r).lsb - font.glyph(l).lsb - font.glyph(l).ink_width
            area = self.delivered.pair_area(l, r, self.options, dist=dist)
            score = float(self.np.sum(area))
            if not math.isfinite(score):
                raise ValueError("counterspace_nonfinite_score")
            self._score_cache[key] = score
        return self._score_cache[key]

    def pair(self, left, right, search_policy="closest_feasible", clearance_min_step=None):
        if search_policy not in ("closest_feasible", "first_crossing"):
            raise ValueError("search_policy must be closest_feasible or first_crossing")
        if clearance_min_step is not None:
            if (isinstance(clearance_min_step, bool) or not isinstance(clearance_min_step, (int, float))
                    or not math.isfinite(clearance_min_step)):
                raise ValueError("clearance_min_step must be finite")
            if search_policy != "closest_feasible":
                raise ValueError("clearance_min_step applies only to closest_feasible search")
        minimum = math.ceil(clearance_min_step) if clearance_min_step is not None else None
        key = (left, right, search_policy, minimum)
        if key in self._pair_cache:
            return dict(self._pair_cache[key])
        l, r = chr(left), chr(right)
        if l not in string.ascii_letters + string.digits or r not in string.ascii_letters + string.digits:
            return {"reason": "counterspace_unsupported_scalar"}
        try:
            font = self.delivered.font
            lg, rg = font.glyph(l), font.glyph(r)
            reference = self.delivered.reference_pair(l, r)
            target = self._targets[reference]
            min_dist = -int(font.minimum_ink_distance(l, r)) + int(self.delivered.bare_minimum)
            # Domain and origin conversion are the original upstream bounds.
            # Closest search deliberately scans the entire bounded domain: the
            # spatially weighted score need not be monotonic with translation.
            origin_offset = lg.lsb + lg.ink_width - rg.lsb
            first = math.ceil((min_dist + origin_offset) / self.factor)
            stop = math.ceil((self.delivered.absolute_maximum + origin_offset) / self.factor)
            candidates = []
            for step in range(first, stop):
                score = self.measure_pair(left, right, step)
                candidates.append((step, score))
                if search_policy == "first_crossing" and score > target:
                    break
            if not candidates:
                raise ValueError("counterspace_empty_search")
            first_crossing = next((candidate for candidate in candidates if candidate[1] > target), None)
            closest = min(candidates, key=lambda item: (abs(item[1] - target), item[0]))
            feasible = [candidate for candidate in candidates if minimum is None or candidate[0] >= minimum]
            if not feasible:
                result = {"reason": "counterspace_no_feasible_candidate", "search_policy": search_policy,
                          "search_outcome": "no_feasible_candidate", "target_score": target,
                          "reference_pair": reference, "candidate_count": len(candidates),
                          "feasible_candidate_count": 0, "clearance_min_step_px": minimum,
                          "candidate_domain_min_step_px": first, "candidate_domain_stop_step_px": stop}
                self._pair_cache[key] = result
                return dict(result)
            if search_policy == "first_crossing":
                # Exact old control: first strict target crossing; if none,
                # select its first maximum score, not the nearest score.
                step, score = first_crossing or max(candidates, key=lambda item: item[1])
                unconstrained_step = step
                outcome = "first_crossing" if first_crossing else "peak_without_crossing"
                closest_feasible = None
            else:
                closest_feasible = min(feasible, key=lambda item: (abs(item[1] - target), item[0]))
                step, score = closest_feasible
                unconstrained_step = closest[0]
                min_score = min(candidate[1] for candidate in feasible)
                max_score = max(candidate[1] for candidate in feasible)
                outcome = ("target_below_feasible_scores" if target < min_score else
                           "target_above_feasible_scores" if target > max_score else "target_bracketed")
            result = {"optical_step_px": float(step), "unconstrained_step_px": float(unconstrained_step),
                      "target_score": target, "realized_score": score,
                      "score_error": score - target, "reference_pair": reference,
                      "target_crossed": score > target, "candidate_count": len(candidates),
                      "search_policy": search_policy, "search_outcome": outcome,
                      "feasible_candidate_count": len(feasible), "clearance_min_step_px": minimum,
                      "candidate_domain_min_step_px": first, "candidate_domain_stop_step_px": stop,
                      "first_crossing_step_px": first_crossing[0] if first_crossing else None,
                      "first_crossing_score": first_crossing[1] if first_crossing else None,
                      "closest_feasible_step_px": closest_feasible[0] if closest_feasible else None,
                      "closest_feasible_score": closest_feasible[1] if closest_feasible else None}
            self._pair_cache[key] = result
            return dict(result)
        except (ValueError, KeyError) as error:
            if str(error) in ("empty_geometry", "captured_bitmap_outside_reference_canvas"):
                return {"reason": str(error)}
            raise CounterSpaceUnavailable("CounterSpace scoring failed: " + str(error)) from error
