"""Delivered-reference relationships, without optical acceptance claims."""

import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hu_hersch as hu
from estimator import UnsupportedGeometry, WorkLimitExceeded
from hu_calibration import HuHerschModel, PARAMETER_REFERENCE, RELATIVE_DEPTH, VISUAL_DEPTH_FACTOR


def rectangle(x0=0, y0=0, x1=2, y1=4):
    return [dict(op="move_to", x=x0 * 100, y=y0 * 100),
            dict(op="line_to", x=x1 * 100, y=y0 * 100),
            dict(op="line_to", x=x1 * 100, y=y1 * 100),
            dict(op="line_to", x=x0 * 100, y=y1 * 100), dict(op="close")]


def capture():
    glyphs = []
    for char in "nHocuvO0abAB":
        upper = char.isupper()
        height = 6 if upper else 4
        glyphs.append(dict(codepoint=ord(char), glyph_id=ord(char),
            source_commands=rectangle(y1=height), produced_commands=[],
            source_advance_px=5 if upper else 4,
            finalized_advance_px=5 if upper else 4,
            bitmap=dict(left=0, top=-height, width=2, height=height, pixels=[1] * (2 * height))))
    return dict(schema_version="contextual-spacing-capture-v1", units_per_em=1000, size_px=10,
                glyphs=glyphs, metric_pairs_on=[], metric_pairs_off=[], source_pairs=[])


def glyph(value, char):
    return next(g for g in value["glyphs"] if g["codepoint"] == ord(char))


class HuCalibrationTests(unittest.TestCase):
    def test_reference_uses_delivered_geometry_and_full_maintained_step(self):
        value = capture()
        value["metric_pairs_on"] = [dict(left=ord("n"), right=ord("n"), adjustment_px=1)]
        glyph(value, "n")["source_advance_px"] = 200
        model = HuHerschModel(value, samples_per_px=8)
        result = model.pair(ord("a"), ord("b"))
        self.assertIsNone(result["reason"])
        self.assertEqual(result["optical_step_px"], 5)
        self.assertEqual(result["target_px"], 3)
        self.assertEqual(result["target_area_px2"], 12)
        self.assertEqual(result["reference_pair"], "nn")
        self.assertEqual(result["hu_hersch"]["facing_reference_kind"], "generic")
        self.assertEqual(result["target_provenance"], "delivered_reference_hu_hersch")
        changed = copy.deepcopy(value)
        changed["metric_pairs_off"] = [dict(left=ord("n"), right=ord("n"), adjustment_px=99)]
        self.assertEqual(result, HuHerschModel(changed, 8).pair(ord("a"), ord("b")))

    def test_mixed_averages_areas_and_heights_separately(self):
        model = HuHerschModel(capture(), 8)
        lower = model.pair(ord("a"), ord("b"))
        upper = model.pair(ord("A"), ord("B"))
        mixed = model.pair(ord("A"), ord("b"))
        self.assertEqual(lower["target_px"], 2)
        self.assertEqual(upper["target_px"], 3)
        self.assertEqual(mixed["measurement_window_px"], [0., 5.])
        self.assertEqual(mixed["window_height_px"], 5)
        self.assertEqual(mixed["target_area_px2"], (8 + 18) / 2)
        self.assertEqual(mixed["target_px"], 2.6)
        self.assertNotEqual(mixed["target_px"], (lower["target_px"] + upper["target_px"]) / 2)
        self.assertEqual(mixed["reference_pair"], "nn/HH")
        self.assertEqual(model.pair(ord("a"), ord("B"))["target_area_px2"], mixed["target_area_px2"])

    def test_directed_delivered_coordinates_do_not_change_reference_class(self):
        value = capture()
        b = glyph(value, "b")
        b["bitmap"]["left"] = 1
        b["source_commands"] = rectangle(x0=1, x1=3)
        model = HuHerschModel(value, 8)
        ab, ba = (model.pair(*map(ord, p)) for p in ("ab", "ba"))
        self.assertEqual(ab["reference_pair"], ba["reference_pair"])
        self.assertEqual(ab["target_px"], ba["target_px"])
        self.assertEqual(ab["optical_step_px"], 3)
        self.assertEqual(ba["optical_step_px"], 5)

    def test_missing_base_reference_abstains_only_in_its_class(self):
        for missing, available, unavailable in (("n", "AB", "ab"), ("H", "ab", "AB")):
            value = capture()
            value["glyphs"] = [g for g in value["glyphs"] if g["codepoint"] != ord(missing)]
            model = HuHerschModel(value, 8)
            self.assertEqual(model.pair(*map(ord, unavailable))["reason"], "calibration_unavailable")
            self.assertIsNone(model.pair(*map(ord, available))["reason"])
        value = capture()
        value["glyphs"] = [g for g in value["glyphs"] if chr(g["codepoint"]) not in "couvO"]
        # Published coefficients need no font-specific fitting repertoire or
        # classified curve reference. The matching generic base is sufficient.
        model = HuHerschModel(value, 8)
        self.assertIsNone(model.pair(ord("a"), ord("b"))["reason"])
        self.assertIsNone(model.pair(ord("A"), ord("B"))["reason"])

    def test_empty_reference_does_not_supply_spacing_evidence(self):
        value = capture()
        glyph(value, "n")["bitmap"]["pixels"] = [0] * 8
        model = HuHerschModel(value, 8)
        self.assertEqual(model.pair(ord("a"), ord("b"))["reason"], "calibration_unavailable")
        self.assertIsNone(model.pair(ord("A"), ord("B"))["reason"])
        self.assertEqual(model.metadata()["fit"]["status"], "published_parameters")

    def test_empty_and_disjoint_delivered_ink_abstain(self):
        value = capture()
        glyph(value, "a")["bitmap"]["pixels"] = [0] * 8
        self.assertEqual(HuHerschModel(value, 8).pair(ord("a"), ord("b"))["reason"], "empty_geometry")
        value = capture()
        glyph(value, "a")["bitmap"]["top"] = -8
        self.assertEqual(HuHerschModel(value, 8).pair(ord("a"), ord("b"))["reason"], "no_shared_ink_rows")

    def test_published_parameters_have_no_fictional_optimizer_outcome(self):
        metadata = HuHerschModel(capture(), 8).metadata()
        self.assertEqual((RELATIVE_DEPTH, VISUAL_DEPTH_FACTOR), (0.21, 0.25))
        self.assertEqual(metadata["parameter_method"], "published_parameters")
        self.assertEqual(metadata["parameter_reference"], PARAMETER_REFERENCE)
        self.assertEqual(PARAMETER_REFERENCE, "https://patents.google.com/patent/US5768490A/en")
        parameters = metadata["fit"]
        self.assertEqual(parameters["status"], "published_parameters")
        self.assertEqual(parameters["method"], "published_parameters")
        self.assertEqual(parameters["relative_depth"], 0.21)
        self.assertEqual(parameters["visual_depth_factor"], 0.25)
        self.assertEqual(parameters["fit_pairs"], [])
        self.assertEqual(parameters["evaluated_settings"], 0)
        self.assertEqual(parameters["residuals"], [])
        for fictitious in ("optimizer", "objective", "boundary_axes", "underidentified_axes"):
            self.assertNotIn(fictitious, parameters)

    def test_all_pairs_use_same_filtered_measurement_without_source_classification(self):
        value = capture()
        a = glyph(value, "a")
        a["bitmap"].update(width=3, pixels=[1, 1, 1] + [1, 1, 0] * 3)
        with patch("hu_calibration.hu.classify_face", side_effect=AssertionError("classified shortcut used"), create=True):
            model = HuHerschModel(value, 8)
            result = model.pair(ord("a"), ord("b"))
        settings = hu.Settings(0.21, 0.25, 8)
        reference = hu.depth_profile(glyph(value, "n")["bitmap"], (0., 4.), settings)
        left = hu.depth_profile(a["bitmap"], (0., 4.), settings)
        right = hu.depth_profile(glyph(value, "b")["bitmap"], (0., 4.), settings)
        self.assertEqual(result["target_px"], 4 + hu.pair_offset(reference, reference))
        self.assertEqual(result["offset_px"], hu.pair_offset(left, right))
        self.assertEqual(result["optical_step_px"], result["target_px"] - result["offset_px"])
        self.assertFalse(result["hu_hersch"]["source_classification_used"])
        self.assertEqual(result["hu_hersch"]["facing_reference_kind"], "generic")
        self.assertEqual(result["hu_hersch"]["measurement_method"], hu.POLICY)

    def test_source_outline_changes_cannot_switch_measurement_paths(self):
        value = capture()
        original = HuHerschModel(value, 8).pair(ord("a"), ord("b"))
        glyph(value, "a")["source_commands"] = rectangle(x0=-15, x1=-1, y1=20)
        glyph(value, "b")["source_commands"] = []
        self.assertEqual(original, HuHerschModel(value, 8).pair(ord("a"), ord("b")))

    def test_reference_pair_self_identity_uses_the_same_transformed_walls(self):
        value = capture()
        glyph(value, "n")["bitmap"].update(width=3, pixels=[1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1])
        model = HuHerschModel(value, 8)
        self.assertAlmostEqual(model.pair(ord("n"), ord("n"))["optical_step_px"], 4)
        self.assertEqual(model.pair(ord("n"), ord("n"))["hu_hersch"]["facing_reference_kind"], "generic")

    def test_metadata_is_lazy_stable_and_deterministic(self):
        value = capture()
        original = copy.deepcopy(value)
        model = HuHerschModel(value, 8)
        with patch.object(model, "_fit_depth", side_effect=AssertionError("parameters were evaluated")):
            self.assertEqual(model.metadata(False)["status"], "not_evaluated")
        before = model.metadata()
        for p in ("ab", "AB", "Ab", "00", "ba"):
            model.pair(*map(ord, p))
        self.assertEqual(model.metadata(), before)
        self.assertEqual(before, HuHerschModel(value, 8).metadata())
        self.assertEqual(value, original)
        json.dumps(before, allow_nan=False)
        before["fit"]["relative_depth"] = 999
        self.assertEqual(model.metadata()["fit"]["relative_depth"], 0.21)

    def test_reference_changes_density_not_published_parameters(self):
        value = capture()
        original = HuHerschModel(value, 8).metadata()
        value["metric_pairs_on"] = [dict(left=ord("n"), right=ord("n"), adjustment_px=1),
                                      dict(left=ord("c"), right=ord("u"), adjustment_px=99)]
        changed = HuHerschModel(value, 8).metadata()
        self.assertEqual(original["fit"], changed["fit"])
        self.assertEqual(changed["references"]["lowercase"]["generic"]["target_px"],
                         original["references"]["lowercase"]["generic"]["target_px"] + 1)

    def test_parameter_initialization_allocates_no_search_profiles(self):
        model = HuHerschModel(capture(), 128)
        with patch.object(model, "_profile", side_effect=AssertionError("parameter initialization sampled geometry")):
            model._fit_depth()
        self.assertEqual(model._profiles, {})
        model.metadata()
        self.assertEqual(len(model._profiles), 3)
        self.assertTrue(all(p.settings == hu.Settings(0.21, 0.25, 128) for p in model._profiles.values()))

    def test_transparent_padding_preserves_profiles_references_and_placements(self):
        value = capture()
        padded = copy.deepcopy(value)
        for index, g in enumerate(padded["glyphs"]):
            b = g["bitmap"]
            left, right, top, bottom = index % 3 + 1, index % 2 + 1, index % 4 + 1, 2
            width = b["width"] + left + right
            height = b["height"] + top + bottom
            pixels = [0] * (width * height)
            for y in range(b["height"]):
                for x in range(b["width"]):
                    pixels[(y + top) * width + x + left] = b["pixels"][y * b["width"] + x]
            g["bitmap"] = dict(left=b["left"] - left, top=b["top"] - top,
                               width=width, height=height, pixels=pixels)
        a, b = HuHerschModel(value, 8), HuHerschModel(padded, 8)
        for field in ("fit", "references", "classes"):
            self.assertEqual(a.metadata()[field], b.metadata()[field])
        for p in ("ab", "ba", "AB", "Ab", "00"):
            self.assertEqual(a.pair(*map(ord, p)), b.pair(*map(ord, p)))

    def test_numerals_are_explicit_generic_only_extension(self):
        result = HuHerschModel(capture(), 8).pair(ord("0"), ord("0"))
        self.assertEqual(result["reference_pair"], "00")
        self.assertEqual(result["hu_hersch"]["facing_reference_kind"], "generic")
        self.assertEqual(result["hu_hersch"]["fallback_reason"], "experimental_digits_generic_only")
        self.assertEqual(HuHerschModel(capture(), 8).pair(ord("a"), ord("0"))["reason"],
                         "unsupported_calibration_class")

    def test_settings_validation(self):
        for value in (0, -1, 1025, True, 1.5):
            with self.assertRaises(ValueError):
                HuHerschModel(capture(), value)



class HuSourceCalibrationTests(unittest.TestCase):
    def model(self, value=None):
        return HuHerschModel(capture() if value is None else value, 8, reference_geometry="source")

    def test_source_reference_uses_outlines_and_full_source_metrics(self):
        value = capture()
        value["source_metric_quantization"] = "nearest_1_64_px"
        glyph(value, "n")["source_advance_px"] = 3.25
        value["source_pairs"] = [dict(left=ord("n"), right=ord("n"), adjustment_px=.25)]
        value["metric_pairs_on"] = [dict(left=ord("n"), right=ord("n"), adjustment_px=2)]
        result = self.model(value).pair(*map(ord, "ab"))
        self.assertEqual(result["target_px"], 1.5)
        self.assertEqual(result["target_area_px2"], 6)
        self.assertEqual(result["optical_step_px"], 3.5)
        self.assertEqual(result["target_provenance"], "source_reference_hu_hersch")
        metadata = self.model(value).metadata()
        reference = metadata["references"]["lowercase"]["generic"]
        self.assertEqual(reference["source_step_px"], 3.5)
        self.assertNotIn("maintained_step_px", reference)
        self.assertEqual(reference["measurement_method"], hu.SOURCE_POLICY)
        self.assertEqual(metadata["source_metric_quantization"], "nearest_1_64_px")
        self.assertEqual(reference["source_metric_quantization"], "nearest_1_64_px")
        self.assertEqual(metadata["calibration_geometry"], "source")
        self.assertNotEqual(metadata["identity"], HuHerschModel(value, 8).metadata()["identity"])

    def test_source_anchor_changes_target_but_candidate_source_does_not(self):
        value = capture()
        original = self.model(value).pair(*map(ord, "ab"))
        delivered = HuHerschModel(value, 8).pair(*map(ord, "ab"))
        glyph(value, "n")["source_commands"] = rectangle(x1=3)
        changed = self.model(value).pair(*map(ord, "ab"))
        self.assertEqual(changed["target_px"], original["target_px"] - 1)
        self.assertEqual(HuHerschModel(value, 8).pair(*map(ord, "ab")), delivered)
        glyph(value, "a")["source_commands"] = []
        glyph(value, "b")["source_commands"] = rectangle(x0=-10, x1=10, y1=20)
        self.assertEqual(self.model(value).pair(*map(ord, "ab")), changed)

    def test_reference_bitmap_cannot_change_source_target_with_fixed_window(self):
        value = capture()
        source = self.model(value).pair(*map(ord, "ab"))
        delivered = HuHerschModel(value, 8).pair(*map(ord, "ab"))
        glyph(value, "n")["bitmap"]["pixels"] = [1, 0] * 3 + [1, 1]
        changed = self.model(value).pair(*map(ord, "ab"))
        self.assertEqual(changed, source)
        self.assertNotEqual(HuHerschModel(value, 8).pair(*map(ord, "ab"))["target_px"], delivered["target_px"])
        value["metric_pairs_on"] = [dict(left=ord("n"), right=ord("n"), adjustment_px=5)]
        glyph(value, "n")["finalized_advance_px"] = 20
        self.assertEqual(self.model(value).pair(*map(ord, "ab")), source)

    def test_mixed_averages_source_reference_areas_and_heights(self):
        value = capture()
        glyph(value, "n")["source_advance_px"] = 3
        glyph(value, "H")["source_advance_px"] = 6
        model = self.model(value)
        lower, upper, mixed = (model.pair(*map(ord, p)) for p in ("ab", "AB", "Ab"))
        self.assertEqual((lower["target_px"], upper["target_px"]), (1, 4))
        self.assertEqual(mixed["measurement_window_px"], [0., 5.])
        self.assertEqual(mixed["target_area_px2"], (4 + 24) / 2)
        self.assertEqual(mixed["target_px"], 2.8)
        self.assertNotEqual(mixed["target_px"], (lower["target_px"] + upper["target_px"]) / 2)

    def test_missing_empty_disjoint_and_nonpositive_source_references_abstain(self):
        for change, detail in (("missing", "missing_reference_glyph"),
                               ("empty", "empty_reference_geometry"),
                               ("disjoint", "no_shared_ink_rows"),
                               ("nonpositive", "nonpositive_target")):
            with self.subTest(change=change):
                value = capture()
                if change == "missing":
                    value["glyphs"].remove(glyph(value, "n"))
                elif change == "empty":
                    glyph(value, "n")["source_commands"] = []
                elif change == "disjoint":
                    glyph(value, "n")["source_commands"] = rectangle(y0=10, y1=14)
                else:
                    glyph(value, "n")["source_advance_px"] = 2
                model = self.model(value)
                result = model.pair(*map(ord, "ab"))
                self.assertEqual((result["reason"], result["detail"]), ("calibration_unavailable", detail))
                self.assertIsNone(model.pair(*map(ord, "AB"))["reason"])

    def test_unsupported_reference_abstains_and_work_limit_is_not_suppressed(self):
        with patch("hu_calibration.hu.source_depth_profile", side_effect=UnsupportedGeometry("unsupported source")):
            result = self.model().pair(*map(ord, "ab"))
            self.assertEqual(result["detail"], "unsupported_reference_geometry")
        with patch("hu_calibration.hu.source_depth_profile", side_effect=WorkLimitExceeded("source budget")):
            with self.assertRaisesRegex(WorkLimitExceeded, "source budget"):
                self.model().pair(*map(ord, "ab"))

    def test_geometry_selection_and_lazy_metadata(self):
        for geometry in (None, "raster", True, 1):
            with self.assertRaises(ValueError):
                HuHerschModel(capture(), 8, reference_geometry=geometry)
        model = self.model()
        with patch("hu_calibration.hu.source_depth_profile", side_effect=AssertionError("source loaded")):
            metadata = model.metadata(False)
        self.assertEqual(metadata["status"], "not_evaluated")
        self.assertEqual(metadata["calibration_geometry"], "source")
        self.assertEqual(model._profiles, {})


if __name__ == "__main__":
    unittest.main()
