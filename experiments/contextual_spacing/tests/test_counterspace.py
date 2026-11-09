"""Reference reuse and delivered-cell coordinate evidence; not optical acceptance."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
import warnings
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import counterspace
from filtered_walls import clearance_min_step


def synthetic_capture():
    font_path = counterspace.ROOT.parents[1] / "fonts" / "Literata.ttf"
    if not font_path.is_file():
        raise unittest.SkipTest("repository Literata font unavailable")
    glyphs = [dict(codepoint=ord(char), source_advance_px=8, finalized_advance_px=8,
                   bitmap=dict(left=1, top=-7, width=5, height=7, pixels=[1] * 35))
              for char in "HOnEAVim"]
    return dict(font_path=str(font_path), source_sha256=hashlib.sha256(font_path.read_bytes()).hexdigest(),
                axes=dict(wght=400, opsz=16), size_px=16, units_per_em=2000,
                glyphs=glyphs, source_pairs=[], metric_pairs_on=[])


def padded_bitmap(bitmap, top, bottom, left, right):
    """Change storage bounds while keeping every occupied absolute cell fixed."""
    width = bitmap["width"] + left + right
    rows = [[0] * width for _ in range(top)]
    rows.extend([0] * left + bitmap["pixels"][row * bitmap["width"]:(row + 1) * bitmap["width"]]
                + [0] * right for row in range(bitmap["height"]))
    rows.extend([[0] * width for _ in range(bottom)])
    return dict(left=bitmap["left"] - left, top=bitmap["top"] - top,
                width=width, height=len(rows), pixels=[pixel for row in rows for pixel in row])


class CounterSpaceSearchTests(unittest.TestCase):
    def model(self, scores, target=10):
        # Exact candidate-domain arithmetic gives origins [1, 7). An external
        # score oracle makes nonmonotonicity and ties independently falsifiable.
        model = counterspace.CounterSpaceModel.__new__(counterspace.CounterSpaceModel)
        model._pair_cache = {}
        model._targets = {"HH": target}
        model.factor = 1
        glyph = SimpleNamespace(lsb=0, ink_width=1)
        font = SimpleNamespace(glyph=lambda char: glyph, minimum_ink_distance=lambda l, r: 0)
        model.delivered = SimpleNamespace(font=font, bare_minimum=0, absolute_maximum=6,
                                          reference_pair=lambda l, r: "HH")
        model.measure_pair = lambda left, right, step: scores[step - 1]
        return model

    def test_closest_scans_past_first_crossing_and_keeps_smaller_step_ties(self):
        model = self.model([5, 13, 1, 9, 11, 40])
        first = model.pair(65, 66, search_policy="first_crossing")
        closest = model.pair(65, 66)
        self.assertEqual(first["optical_step_px"], 2)
        self.assertEqual(first["candidate_count"], 2)
        self.assertEqual(closest["optical_step_px"], 4)
        self.assertEqual(closest["candidate_count"], 6)
        self.assertEqual(closest["first_crossing_step_px"], 2)
        self.assertEqual(closest["search_outcome"], "target_bracketed")
        self.assertFalse(closest["target_crossed"], "selected score is below target even though earlier candidates cross")
        guarded = model.pair(65, 66, clearance_min_step=4.1)
        self.assertEqual(guarded["optical_step_px"], 5)
        self.assertEqual(guarded["unconstrained_step_px"], 4)
        self.assertEqual(guarded["feasible_candidate_count"], 2)
        self.assertEqual(guarded["clearance_min_step_px"], 5)

    def test_unreachable_targets_and_empty_feasible_domain_remain_explicit(self):
        model = self.model([1, 4, 3, 2, 5, 0])
        closest = model.pair(65, 66)
        self.assertEqual(closest["optical_step_px"], 5)
        self.assertEqual(closest["search_outcome"], "target_above_feasible_scores")
        self.assertFalse(closest["target_crossed"])
        below = self.model([20, 17, 16, 14, 15, 21]).pair(65, 66)
        self.assertEqual(below["optical_step_px"], 4)
        self.assertEqual(below["search_outcome"], "target_below_feasible_scores")
        for minimum in (7, 8):
            impossible = model.pair(65, 66, clearance_min_step=minimum)
            self.assertEqual(impossible["reason"], "counterspace_no_feasible_candidate")
            self.assertEqual(impossible["feasible_candidate_count"], 0)
            self.assertNotIn("optical_step_px", impossible)

    def test_old_first_crossing_falls_back_to_first_peak_without_crossing(self):
        result = self.model([1, 5, 4, 5, 2, 0]).pair(65, 66, search_policy="first_crossing")
        self.assertEqual(result["optical_step_px"], 2)
        self.assertEqual(result["search_outcome"], "peak_without_crossing")
        self.assertIsNone(result["first_crossing_step_px"])

    def test_policy_validation(self):
        model = self.model([0] * 6)
        with self.assertRaisesRegex(ValueError, "search_policy"):
            model.pair(65, 66, search_policy="invented")
        for invalid in (float("nan"), float("inf"), True):
            with self.assertRaisesRegex(ValueError, "finite"):
                model.pair(65, 66, clearance_min_step=invalid)
        with self.assertRaisesRegex(ValueError, "only"):
            model.pair(65, 66, search_policy="first_crossing", clearance_min_step=1)


class CounterSpacePinTests(unittest.TestCase):
    def test_vendored_files_match_pinned_manifest(self):
        manifest = json.loads(counterspace.LOCK.read_text())
        self.assertEqual(manifest["revision"], "01b33477225eb5fc7bedf93a090b5cd7dd0c812b")
        for name, expected in manifest["files"].items():
            self.assertEqual(hashlib.sha256((counterspace.REFERENCE.parent / name).read_bytes()).hexdigest(), expected)
        self.assertEqual(hashlib.sha256((counterspace.ROOT / "requirements-counterspace.txt").read_bytes()).hexdigest(),
                         manifest["requirements_sha256"])

    def test_runtime_rejects_changed_reference_and_requirements_before_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = root / "reference"
            reference.mkdir()
            for name in ("CounterSpace.py", "LICENSE"):
                shutil.copyfile(counterspace.REFERENCE.parent / name, reference / name)
            shutil.copyfile(counterspace.LOCK, root / "counterspace.lock.json")
            shutil.copyfile(counterspace.ROOT / "requirements-counterspace.txt", root / "requirements-counterspace.txt")
            with patch.multiple(counterspace, ROOT=root, REFERENCE=reference / "CounterSpace.py",
                                LOCK=root / "counterspace.lock.json"):
                counterspace._verify_reference()
                for target in (reference / "CounterSpace.py", reference / "LICENSE",
                               root / "requirements-counterspace.txt"):
                    original = target.read_bytes()
                    target.write_bytes(original + b"\nchanged\n")
                    with self.subTest(file=target.name):
                        with self.assertRaisesRegex(counterspace.CounterSpaceUnavailable, "SHA-256 mismatch"):
                            counterspace._dependencies.__wrapped__()
                    target.write_bytes(original)
                counterspace._verify_reference()


class CounterSpaceNumericalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.dependencies = counterspace._dependencies()
        except counterspace.CounterSpaceUnavailable as error:
            raise unittest.SkipTest(str(error))

    def test_original_tensorfont_masks_match_independent_rectangle_oracle(self):
        np, _, _, _, tensorfont, _ = self.dependencies
        matrix = np.zeros((8, 12))
        matrix[2:6, 4:8] = 1
        glyph = SimpleNamespace(ink_width=12)
        rendering = tensorfont.GlyphRendering.init_from_numpy(glyph, matrix)
        left, right = rendering.mask_ink_to_edge()
        # Tensorfont's actual border convention drops the neighboring outside
        # column as well. Preserve that upstream convention rather than silently
        # fixing its off-by-one behavior in this adapter.
        expected_left = np.zeros_like(matrix)
        expected_right = np.zeros_like(matrix)
        expected_left[2:6, :3] = 1
        expected_right[2:6, 9:] = 1
        np.testing.assert_array_equal(left, expected_left)
        np.testing.assert_array_equal(right, expected_right)

    def test_concavity_reduction_is_intensity_domain_invariant(self):
        np, _, _, _, tensorfont, _ = self.dependencies
        # The same L outline has a real external concavity. Pixel intensities
        # represent the same geometry; the contour operation must not depend on
        # whether upstream smoothing expresses ink as 1 or 255.
        pixels = np.zeros((12, 12))
        pixels[2:10, 2:4] = 1
        pixels[8:10, 2:10] = 1
        glyph = SimpleNamespace(ink_width=12)
        binary = tensorfont.GlyphRendering.init_from_numpy(glyph, pixels)
        byte = tensorfont.GlyphRendering.init_from_numpy(glyph, pixels * 255)
        original_binary, original_byte = binary.copy(), byte.copy()
        reduced_binary = binary.reduce_concavity(1)
        reduced_byte = byte.reduce_concavity(1)
        self.assertGreater(np.count_nonzero(reduced_byte), np.count_nonzero(byte))
        np.testing.assert_array_equal(reduced_binary, reduced_byte / 255)
        self.assertIsInstance(reduced_binary, tensorfont.GlyphRendering)
        self.assertIs(reduced_binary._glyph, glyph)
        self.assertIs(reduced_byte._glyph, glyph)
        np.testing.assert_array_equal(binary, original_binary)
        np.testing.assert_array_equal(byte, original_byte)

    def test_intensity_repair_preserves_byte_and_blank_no_smoothing_paths(self):
        np, _, _, _, tensorfont, _ = self.dependencies
        glyph = SimpleNamespace(ink_width=12)
        original = tensorfont.GlyphRendering.reduce_concavity.__wrapped__
        pixels = np.zeros((12, 12))
        pixels[2:10, 2:4] = 255
        pixels[8:10, 2:10] = 255
        pixels[4:6, 3] = 128  # An existing grayscale path is also unchanged.
        for matrix in (pixels, np.zeros_like(pixels)):
            for percent in (0, 0.5, 1):
                rendering = tensorfont.GlyphRendering.init_from_numpy(glyph, matrix)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    expected = original(rendering, percent)
                    actual = rendering.reduce_concavity(percent)
                np.testing.assert_array_equal(actual, expected)
                self.assertIs(actual._glyph, glyph)

    def test_delivered_cells_expand_exactly_at_baseline_without_rerasterization(self):
        np, _, _, _, tensorfont, _ = self.dependencies
        source_font = SimpleNamespace(ascender_px=12, full_height_px=24, italic_angle=0,
                                      baseline_ratio=0.5, m_width=8)
        record = dict(codepoint=ord("m"), finalized_advance_px=4,
                      bitmap=dict(left=-1, top=-3, width=2, height=2, pixels=[1, 0, 0, 1]))
        capture = dict(size_px=10, units_per_em=1000, glyphs=[record])
        before = copy.deepcopy(capture)
        font = counterspace._CapturedFont(capture, source_font, 2, tensorfont)
        glyph = font.glyph("m")
        expected = np.zeros((24, 4))
        expected[6:8, :2] = 255
        expected[8:10, 2:] = 255
        np.testing.assert_array_equal(glyph.as_matrix(), expected)
        self.assertEqual((glyph.lsb, glyph.rsb, glyph.tsb, glyph.ink_height), (-2, 6, 6, 4))
        self.assertEqual(capture, before)

    def test_padding_outside_canvas_preserves_actual_ink_and_tight_metrics(self):
        np, _, _, _, tensorfont, _ = self.dependencies
        source_font = SimpleNamespace(ascender_px=12, full_height_px=24, italic_angle=0,
                                      baseline_ratio=0.5, m_width=8)
        original = dict(codepoint=ord("m"), finalized_advance_px=4,
                        bitmap=dict(left=-1, top=-3, width=2, height=2, pixels=[1, 0, 0, 1]))
        padded = copy.deepcopy(original)
        padded["bitmap"] = padded_bitmap(original["bitmap"], top=12, bottom=12, left=4, right=7)
        capture = dict(size_px=10, units_per_em=1000, glyphs=[padded])
        before = copy.deepcopy(capture)
        glyph = counterspace._CapturedFont(capture, source_font, 2, tensorfont).glyph("m")
        base = counterspace._CapturedFont(dict(capture, glyphs=[original]), source_font, 2, tensorfont).glyph("m")
        self.assertEqual((glyph.lsb, glyph.rsb, glyph.tsb, glyph.ink_width, glyph.ink_height),
                         (base.lsb, base.rsb, base.tsb, base.ink_width, base.ink_height))
        np.testing.assert_array_equal(glyph.as_matrix(), base.as_matrix())
        self.assertEqual(capture, before)

    def test_true_outside_ink_and_all_blank_storage_remain_explicit(self):
        _, _, _, _, tensorfont, _ = self.dependencies
        source_font = SimpleNamespace(ascender_px=12, full_height_px=24, italic_angle=0,
                                      baseline_ratio=0.5, m_width=8)
        for bitmap, reason in ((dict(left=0, top=-8, width=2, height=2, pixels=[1] * 4),
                                "captured_bitmap_outside_reference_canvas"),
                               (dict(left=0, top=6, width=2, height=2, pixels=[1] * 4),
                                "captured_bitmap_outside_reference_canvas"),
                               (dict(left=-20, top=-20, width=40, height=40, pixels=[0] * 1600),
                                "empty_geometry")):
            capture = dict(size_px=10, units_per_em=1000,
                           glyphs=[dict(codepoint=ord("m"), finalized_advance_px=4, bitmap=bitmap)])
            with self.subTest(reason=reason, top=bitmap["top"]):
                with self.assertRaisesRegex(ValueError, reason):
                    counterspace._CapturedFont(capture, source_font, 2, tensorfont).glyph("m")

    def test_full_model_is_invariant_to_independent_transparent_margins(self):
        np = self.dependencies[0]
        capture = synthetic_capture()
        # n has a blank first storage row; b/d extend above its actual x-height.
        n = next(record for record in capture["glyphs"] if record["codepoint"] == ord("n"))
        n["bitmap"]["pixels"][:5] = [0] * 5
        for char in "bdu":
            glyph = copy.deepcopy(capture["glyphs"][0])
            glyph["codepoint"] = ord(char)
            capture["glyphs"].append(glyph)
        padded = copy.deepcopy(capture)
        for index, glyph in enumerate(padded["glyphs"]):
            glyph["bitmap"] = padded_bitmap(glyph["bitmap"], top=index % 2,
                                             bottom=(index + 1) % 2, left=index % 4 + 1,
                                             right=index % 3 + 1)
        originals = copy.deepcopy(capture), copy.deepcopy(padded)
        base_glyphs = {record["codepoint"]: record for record in capture["glyphs"]}
        padded_glyphs = {record["codepoint"]: record for record in padded["glyphs"]}
        for geometry in ("delivered", "source"):
            with self.subTest(calibration_geometry=geometry):
                base = counterspace.CounterSpaceModel(capture, calibration_geometry=geometry)
                equivalent = counterspace.CounterSpaceModel(padded, calibration_geometry=geometry)
                for field in ("options", "optimizer_results", "reference_scores", "reference_placements"):
                    self.assertEqual(base.metadata()[field], equivalent.metadata()[field], field)
                n_glyph = equivalent.delivered.font.glyph("n")
                self.assertEqual(n_glyph.tsb, equivalent.delivered.font.ascender_px - 6 * equivalent.factor)
                self.assertEqual(n_glyph.ink_height, 6 * equivalent.factor)
                for pair in ("bd", "du", "nn", "HO"):
                    left, right = map(ord, pair)
                    clearance = clearance_min_step(base_glyphs[left]["bitmap"], base_glyphs[right]["bitmap"])
                    self.assertEqual(clearance, clearance_min_step(padded_glyphs[left]["bitmap"], padded_glyphs[right]["bitmap"]))
                    np.testing.assert_array_equal(base.delivered.font.glyph(pair[0]).as_matrix(),
                                                  equivalent.delivered.font.glyph(pair[0]).as_matrix())
                    for step in (8, 9, 10):
                        self.assertEqual(base.measure_pair(left, right, step), equivalent.measure_pair(left, right, step))
                    for policy, minimum in (("first_crossing", None), ("closest_feasible", clearance)):
                        self.assertEqual(base.pair(left, right, search_policy=policy, clearance_min_step=minimum),
                                         equivalent.pair(left, right, search_policy=policy, clearance_min_step=minimum))
        self.assertEqual((capture, padded), originals)

    def test_integer_candidate_search_uses_original_pair_area_and_explicit_score(self):
        np, _, _, _, tensorfont, Engine = self.dependencies
        # Real source fitting and real upstream 2D scoring. Synthetic captured
        # glyphs isolate delivered-cell placement from any renderer differences.
        capture = synthetic_capture()
        model = counterspace.CounterSpaceModel(capture, calibration_geometry="source")
        result = model.pair(ord("H"), ord("O"), search_policy="first_crossing")
        self.assertNotIn("reason", result)
        self.assertEqual(result["optical_step_px"], int(result["optical_step_px"]))
        step = result["optical_step_px"]
        font = model.delivered.font
        distance = step * model.factor + font.glyph("O").lsb - font.glyph("H").lsb - font.glyph("H").ink_width
        upstream = float(np.sum(Engine.pair_area(model.delivered, "H", "O", model.options, dist=distance)))
        self.assertEqual(upstream, result["realized_score"])
        self.assertEqual(upstream, model.measure_pair(ord("H"), ord("O"), step))
        if result["target_crossed"] and result["candidate_count"] > 1:
            self.assertLessEqual(model.measure_pair(ord("H"), ord("O"), step - 1), result["target_score"])
        self.assertEqual(result["reference_pair"], "HH")
        self.assertEqual(model.pair(ord("£"), ord("H"))["reason"], "counterspace_unsupported_scalar")
        self.assertTrue(model.metadata()["optimizer_results"])
        self.assertIn(model.metadata()["fit_status"], ("converged", "upstream_optimizer_did_not_converge"))
        json.dumps(model.metadata(), allow_nan=False)

    def test_delivered_calibration_uses_finalized_full_metric_reference_placements(self):
        np = self.dependencies[0]
        capture = synthetic_capture()
        capture["source_pairs"] = [dict(left=ord("H"), right=ord("H"), adjustment_px=-1)]
        capture["metric_pairs_on"] = [dict(left=ord(pair[0]), right=ord(pair[1]), adjustment_px=adjustment)
                                       for pair, adjustment in (("HH", 2), ("HO", -1), ("AV", -2), ("nn", 1))]
        before = copy.deepcopy(capture)
        model = counterspace.CounterSpaceModel(capture)
        metadata = model.metadata()
        self.assertEqual(metadata["calibration_geometry"], "delivered")
        self.assertIs(model.calibration, model.delivered)
        placements = {record["pair"]: record for record in metadata["reference_placements"]}
        for pair, step in (("HH", 10), ("HO", 7), ("AV", 6), ("nn", 9)):
            self.assertEqual(placements[pair]["origin_step_px"], step)
            self.assertEqual(placements[pair]["pair_adjustment_px"], step - 8)
        for reference in ("HH", "nn"):
            measured = float(np.sum(model.delivered.pair_area(*reference, model.options, reference=reference)))
            self.assertEqual(metadata["reference_scores"][reference], measured)
            self.assertEqual(placements[reference]["score"], measured)
        self.assertEqual(capture, before)
        self.assertEqual(model.delivered.font.pair_distance("H", "H", with_kerning=False), 3 * model.factor)
        self.assertEqual(model.delivered.font.pair_distance("H", "H"), 5 * model.factor)
        source = counterspace.CounterSpaceModel(capture, calibration_geometry="source")
        source_placements = {record["pair"]: record for record in source.metadata()["reference_placements"]}
        self.assertEqual(source_placements["HH"]["origin_step_px"], 7)
        with self.assertRaisesRegex(ValueError, "calibration_geometry"):
            counterspace.CounterSpaceModel(capture, calibration_geometry="invented")


if __name__ == "__main__":
    unittest.main()
