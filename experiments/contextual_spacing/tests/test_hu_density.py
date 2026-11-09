"""Fixed-domain constraints and physical-coordinate checks, not optical approval."""
import copy
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hu_density as density
from hu_density import HuDensityModel, REPERTOIRES
from estimator import WorkLimitExceeded


def rectangle(width=2, height=4, x=0, y=0, scale=100):
    return [dict(op="move_to", x=x * scale, y=y * scale),
            dict(op="line_to", x=(x + width) * scale, y=y * scale),
            dict(op="line_to", x=(x + width) * scale, y=(y + height) * scale),
            dict(op="line_to", x=x * scale, y=(y + height) * scale), dict(op="close")]


def complete_capture():
    """Whole fixed ASCII alphabets plus space, with independently simple walls."""
    glyphs = []
    for cp in (32, *range(48, 58), *range(65, 91), *range(97, 123)):
        height = 4 if cp >= 97 else 6
        commands = rectangle(height=height) if cp != 32 else []
        glyphs.append(dict(codepoint=cp, glyph_id=cp, source_commands=commands,
                           produced_commands=rectangle(width=2.5, height=height, scale=1) if cp != 32 else [],
                           source_advance_px=4 if cp >= 97 or cp < 65 else 5, finalized_advance_px=4 if cp >= 97 or cp < 65 else 5,
                           bitmap=dict(left=0, top=-height, width=2, height=height, pixels=[1] * (2 * height)) if cp != 32 else
                           dict(left=0, top=0, width=0, height=0, pixels=[])))
    return dict(schema_version="contextual-spacing-capture-v1", source_sha256="complete-density-fixture",
                units_per_em=1000, size_px=10, axes={}, monospace=False, tabular_digits=False,
                glyphs=glyphs, source_pairs=[], metric_pairs_on=[], metric_pairs_off=[],
                source_metric_quantization=dict(unit_px=1 / 64, rounding="nearest, ties away from zero"))


def glyph(capture, char):
    return next(g for g in capture["glyphs"] if g["codepoint"] == ord(char))


class HuDensityTests(unittest.TestCase):
    def test_full_construction_has_its_own_cache_provenance_and_domain_constraint(self):
        value = complete_capture()
        commands = [dict(op="move_to", x=-1, y=0), dict(op="line_to", x=3, y=0),
                    dict(op="quad_to", x1=-1, y1=3, x=3, y=6),
                    dict(op="line_to", x=-1, y=6), dict(op="close")]
        glyph(value, "g")["produced_commands"] = commands
        original = copy.deepcopy(value)
        legacy = HuDensityModel(value, 16, candidate_geometry="fitted_outline")
        candidate = HuDensityModel(value, 16, candidate_geometry="fitted_outline", construction_policy="full_outline")
        before = legacy.pair(ord("a"), ord("b"))
        new = candidate.pair(ord("a"), ord("b"))
        self.assertEqual(legacy.pair(ord("a"), ord("b")), before)
        self.assertNotEqual(new["target_provenance"], before["target_provenance"])
        self.assertNotEqual(candidate.identity, legacy.identity)
        self.assertEqual(new["hu_hersch"]["cavity_supports"], "post_B")
        self.assertEqual(new["hu_hersch"]["construction_policy"], "full_outline")
        self.assertEqual(new["hu_hersch"]["global_depth_height_px"], 4)
        calibration = candidate.metadata()["classes"]["lowercase"]
        mean_step = math.fsum(candidate.pair(a, b)["optical_step_px"]
                             for a in REPERTOIRES["lowercase"] for b in REPERTOIRES["lowercase"]) / 676
        self.assertAlmostEqual(mean_step, calibration["mean_source_step_px"])
        self.assertEqual(candidate.metadata()["measurement_method"], density.FULL_FITTED_MEASUREMENT)
        self.assertEqual(candidate.metadata()["integration_domain"], "retained class body window")
        self.assertEqual(value, original)
        for kwargs in (dict(construction_policy="other"), dict(construction_policy="full_outline")):
            with self.assertRaises(ValueError):
                HuDensityModel(value, **kwargs)

    def setUp(self):
        density._sample_profile.cache_clear()

    def test_source_arms_match_every_ordered_pair_and_conserve_declared_means(self):
        value = complete_capture()
        glyph(value, "a")["source_advance_px"] = 6
        value["source_pairs"] = [dict(left=ord("a"), right=ord("a"), adjustment_px=-.5),
                                 dict(left=ord("a"), right=ord("z"), adjustment_px=.75),
                                 dict(left=ord("A"), right=ord("z"), adjustment_px=-1)]
        models = [HuDensityModel(value, 8, target_policy=p, candidate_geometry="source")
                  for p in ("source_origin", "source_alphabet")]
        metadata = models[0].metadata()
        lower = metadata["classes"]["lowercase"]
        expected = 4 + 2 / 26 + .25 / 676
        self.assertAlmostEqual(lower["mean_source_step_px"], expected)
        self.assertAlmostEqual(lower["target_px"], expected - 2)
        self.assertEqual(lower["pair_count"], 676)
        self.assertEqual(metadata["classes"]["mixed"]["pair_count"], 1352)
        self.assertEqual(metadata["classes"]["digits"]["pair_count"], 100)
        for basis, calibration in metadata["classes"].items():
            pairs = [(a, b) for product in calibration["pair_domain"]["products"]
                     for a in product["left_codepoints"] for b in product["right_codepoints"]]
            required = []
            source_steps = []
            for a, b in pairs:
                first, second = (model.pair(a, b) for model in models)
                for field in ("target_px", "offset_px", "optical_step_px", "target_area_px2", "measurement_window_px"):
                    self.assertEqual(first[field], second[field], (basis, a, b, field))
                required.append(first["optical_step_px"])
                source_steps.append(glyph(value, chr(a))["source_advance_px"] + models[0].source_pairs.get((a, b), 0))
            self.assertEqual(len(required), calibration["pair_count"])
            self.assertAlmostEqual(math.fsum(required) / len(required), math.fsum(source_steps) / len(source_steps))
            self.assertAlmostEqual(calibration["continuous_mean_origin_residual_px"], 0)
        mixed_expected = ((4 + 2 / 26 + 5) / 2) - 1 / 1352
        self.assertAlmostEqual(metadata["classes"]["mixed"]["mean_source_step_px"], mixed_expected)

    def test_density_constraint_and_source_target_are_distinct_on_changed_candidate(self):
        value = complete_capture()
        glyph(value, "a")["bitmap"].update(width=3, pixels=[1] * 12)
        origin = HuDensityModel(value, 8, "source_origin")
        source = HuDensityModel(value, 8, "source_alphabet")
        a = origin.metadata()["classes"]["lowercase"]
        b = source.metadata()["classes"]["lowercase"]
        self.assertAlmostEqual(a["mean_candidate_offset_px"], -2 - 1 / 26)
        self.assertAlmostEqual(a["target_px"], 2 - 1 / 26)
        self.assertAlmostEqual(a["continuous_mean_step_px"], 4)
        self.assertAlmostEqual(b["target_px"], 2)
        self.assertAlmostEqual(b["continuous_mean_origin_residual_px"], 1 / 26)
        self.assertNotEqual(origin.identity, source.identity)
        plain = complete_capture()
        self.assertEqual(HuDensityModel(plain, 8, "source_alphabet").metadata()["classes"]["lowercase"]["target_px"], b["target_px"])
        pairs = [(x, y) for x in REPERTOIRES["lowercase"] for y in REPERTOIRES["lowercase"]]
        self.assertAlmostEqual(math.fsum(origin.pair(*pair)["optical_step_px"] for pair in pairs) / 676, 4)

    def test_missing_invalid_empty_unshared_and_nonpositive_classes_do_not_shrink_domain(self):
        cases = ["missing", "invalid", "empty_source", "empty_bitmap", "unshared", "metric", "nonpositive"]
        for failure in cases:
            with self.subTest(failure=failure):
                value = complete_capture()
                z = glyph(value, "z")
                if failure == "missing":
                    value["glyphs"].remove(z)
                    expected = "missing_calibration_glyph"
                elif failure == "invalid":
                    z["source_commands"] = [dict(op="unsupported")]
                    expected = "invalid_calibration_geometry"
                elif failure == "empty_source":
                    z["source_commands"] = []
                    expected = "empty_calibration_geometry"
                elif failure == "empty_bitmap":
                    z["bitmap"]["pixels"] = [0] * 8
                    expected = "empty_calibration_geometry"
                elif failure == "unshared":
                    z["source_commands"] = rectangle(y=10)
                    expected = "no_shared_calibration_ink_rows"
                elif failure == "metric":
                    z["source_advance_px"] = float("nan")
                    expected = "invalid_calibration_source_metric"
                else:
                    for cp in REPERTOIRES["lowercase"]:
                        glyph(value, chr(cp))["source_advance_px"] = 1
                    expected = "nonpositive_target"
                model = HuDensityModel(value, 8, target_policy="source_alphabet")
                metadata = model.metadata()
                lower = metadata["classes"]["lowercase"]
                self.assertEqual(lower["status"], "unavailable")
                self.assertEqual(lower["reason"], expected)
                self.assertEqual(lower["pair_count"], 676)
                self.assertEqual(len(lower["repertoire_codepoints"]), 26)
                self.assertEqual(metadata["classes"]["uppercase"]["status"], "available")
                self.assertEqual(model.pair(ord("a"), ord("b"))["reason"], "calibration_unavailable")
                json.dumps(metadata, allow_nan=False)

    def test_sparse_pair_errors_are_class_failures_and_work_limits_are_not_suppressed(self):
        for adjustments in ([float("inf")], [1, 2]):
            value = complete_capture()
            value["source_pairs"] = [dict(left=ord("a"), right=ord("z"), adjustment_px=v) for v in adjustments]
            self.assertEqual(HuDensityModel(value, 8).metadata()["classes"]["lowercase"]["reason"], "invalid_calibration_source_metric")
        with patch("hu_density.hu.source_depth_profile", side_effect=WorkLimitExceeded("budget")):
            with self.assertRaisesRegex(WorkLimitExceeded, "budget"):
                HuDensityModel(complete_capture(), 8, target_policy="source_alphabet").metadata()

    def test_source_origin_does_not_require_optional_source_wall_diagnostic(self):
        value = complete_capture()
        glyph(value, "z")["source_commands"] = [dict(op="unsupported")]
        metadata = HuDensityModel(value, 8).metadata()
        lower = metadata["classes"]["lowercase"]
        self.assertEqual(lower["status"], "available")
        self.assertEqual(lower["target_px"], 2)
        self.assertIsNone(lower["mean_source_offset_px"])
        self.assertIsNone(lower["source_alphabet_target_px"])
        self.assertEqual(lower["source_offset_diagnostic"]["status"], "unavailable")
        self.assertEqual(HuDensityModel(value, 8, candidate_geometry="source").metadata()["classes"]["lowercase"]["status"], "unavailable")
        with patch("hu_density.hu.source_depth_profile", side_effect=WorkLimitExceeded("optional budget")):
            density._sample_profile.cache_clear()
            lower = HuDensityModel(complete_capture(), 8).metadata()["classes"]["lowercase"]
            self.assertEqual(lower["status"], "available")
            self.assertEqual(lower["source_offset_diagnostic"]["reason"], "work_limit_exceeded")

    def test_bitmap_fitted_and_source_use_their_declared_physical_units(self):
        value = complete_capture()
        targets = {geometry: HuDensityModel(value, 8, candidate_geometry=geometry).metadata()["classes"]["lowercase"]["target_px"]
                   for geometry in ("bitmap", "fitted_outline", "source")}
        self.assertEqual(targets, dict(bitmap=2, fitted_outline=1.5, source=2))
        original = HuDensityModel(value, 8, candidate_geometry="fitted_outline").pair(ord("a"), ord("b"))
        moved = copy.deepcopy(value)
        for g in moved["glyphs"]:
            for field, dx, dy in (("source_commands", 700, 200), ("produced_commands", 7, 2)):
                for command in g[field]:
                    for key in ("x", "x1", "x2"):
                        if key in command:
                            command[key] += dx
                    for key in ("y", "y1", "y2"):
                        if key in command:
                            command[key] += dy
            g["bitmap"]["left"] += 7
            g["bitmap"]["top"] -= 2
        translated = HuDensityModel(moved, 8, candidate_geometry="fitted_outline").pair(ord("a"), ord("b"))
        self.assertAlmostEqual(original["optical_step_px"], translated["optical_step_px"])
        self.assertAlmostEqual(original["target_px"], translated["target_px"])
        scaled = copy.deepcopy(value)
        scaled["size_px"] *= 2
        for g in scaled["glyphs"]:
            g["source_advance_px"] *= 2
            for command in g["produced_commands"]:
                for key in ("x", "y", "x1", "y1", "x2", "y2"):
                    if key in command:
                        command[key] *= 2
            bitmap = g["bitmap"]
            rows = [bitmap["pixels"][i * bitmap["width"]:(i + 1) * bitmap["width"]] for i in range(bitmap["height"])]
            bitmap.update(left=2 * bitmap["left"], top=2 * bitmap["top"], width=2 * bitmap["width"], height=2 * bitmap["height"],
                          pixels=[v for row in rows for _ in range(2) for v in row for _ in range(2)])
        enlarged = HuDensityModel(scaled, 8, candidate_geometry="fitted_outline").pair(ord("a"), ord("b"))
        self.assertAlmostEqual(enlarged["optical_step_px"], 2 * original["optical_step_px"])
        self.assertAlmostEqual(enlarged["target_px"], 2 * original["target_px"])

    def test_metadata_is_lazy_detached_and_bounded_profiles_are_reused(self):
        value = complete_capture()
        original = copy.deepcopy(value)
        with patch("hu_density.hu.source_depth_profile", side_effect=AssertionError("sampled")):
            metadata = HuDensityModel(value, 8).metadata(False)
        self.assertEqual(metadata["status"], "not_evaluated")
        self.assertEqual(metadata["target_policy"], "source_origin")
        self.assertEqual(metadata["candidate_geometry"], "bitmap")
        self.assertEqual(metadata["source_metric_quantization"], value["source_metric_quantization"])
        first = HuDensityModel(value, 8)
        before = first.metadata()
        info = density._sample_profile.cache_info()
        HuDensityModel(value, 8, "source_alphabet").metadata()
        self.assertEqual(density._sample_profile.cache_info().misses, info.misses)
        self.assertLessEqual(density._sample_profile.cache_info().currsize, 512)
        before["classes"]["lowercase"]["target_px"] = 999
        self.assertEqual(first.metadata()["classes"]["lowercase"]["target_px"], 2)
        self.assertEqual(value, original)
        self.assertEqual(first.pair(32, ord("a"))["reason"], "unsupported_calibration_class")
        for kwargs in (dict(target_policy="other"), dict(candidate_geometry="gray"), dict(samples_per_px=0)):
            with self.assertRaises(ValueError):
                HuDensityModel(value, **kwargs)


if __name__ == "__main__":
    unittest.main()
