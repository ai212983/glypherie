"""Independent recovery gates; no optimization or optical acceptance claim.

Light source/loss tests need only Python. Input checks additionally need NumPy
and the setup command's retained corpus. The FreeType oracle uses the locked
environment; it does not import the compatibility-patched tensorfont module.
Full network forwards belong to the bounded recovery CLI, not test discovery.
"""
import ast
import copy
import contextlib
from fractions import Fraction
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yinyangfit_recovery as recovery

try:
    import numpy as np
except ModuleNotFoundError:
    np = None

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "out/diagnostics/contextual-spacing/yinyangfit"
REFERENCE = Path(os.environ.get("YINYANGFIT_REFERENCE", EVIDENCE / "recovery-sources/YinYangFit.ipynb"))
INPUTS = Path(os.environ.get("YINYANGFIT_INPUTS", EVIDENCE / "recovery-inputs-final"))
SOURCES = Path(os.environ.get("YINYANGFIT_SOURCES", EVIDENCE / "recovery-sources"))
SOURCE_HASH = "078e9dda8c5217bc064f1b1b09f03e83fb2be03e7322885594eb2b5d50d59ba6"
DELTAS = [-3, -1, 0, 1, 5]
# Independent inventory read from the pinned notebook, not the adapter's list.
DEFINITIONS = {
    5: ("unit_pgrid", "get_sigmas", "get_v1_filter_bank", "apply_filter_bank"),
    6: ("G_filters",), 7: ("B_G_Direct",), 8: ("G_Targets",),
    9: ("YinYangFit",), 11: ("apply_translations",), 13: ("estimate_min_loss",),
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def rational_cubic(values):
    """Exact normal-equation oracle, independent of Torch's pseudoinverse."""
    xs = [Fraction(v) for v in DELTAS]
    ys = [Fraction(v) for v in values]
    design = [[x**3, x*x, x, Fraction(1)] for x in xs]
    matrix = [[sum(row[i] * row[j] for row in design) for j in range(4)]
              + [sum(row[i] * value for row, value in zip(design, ys))] for i in range(4)]
    for i in range(4):
        pivot = next(j for j in range(i, 4) if matrix[j][i])
        matrix[i], matrix[pivot] = matrix[pivot], matrix[i]
        denominator = matrix[i][i]
        matrix[i] = [v / denominator for v in matrix[i]]
        for j in range(4):
            if i != j:
                multiplier = matrix[j][i]
                matrix[j] = [a - multiplier*b for a, b in zip(matrix[j], matrix[i])]
    return [row[-1] for row in matrix]


class HistoricalSourceAndLossTests(unittest.TestCase):
    def test_selected_definitions_are_original_ast_without_notebook_execution(self):
        if not REFERENCE.is_file():
            self.skipTest("run the YinYangFit input preparation first")
        raw = REFERENCE.read_bytes()
        self.assertEqual(digest(raw), SOURCE_HASH)
        notebook = json.loads(raw)
        expected = []
        for cell, names in DEFINITIONS.items():
            tree = ast.parse("".join(notebook["cells"][cell]["source"]))
            for name in names:
                expected.append(next(node for node in tree.body
                                     if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name))
        actual = recovery.load_source(REFERENCE)
        self.assertEqual(actual.raw_sha256, SOURCE_HASH)
        # Parse both sides in this interpreter. AST schema fields can differ
        # between Python versions even when notebook source bytes are identical.
        self.assertEqual(ast.dump(actual.module, include_attributes=False),
                         ast.dump(ast.Module(body=expected, type_ignores=[]), include_attributes=False))
        self.assertTrue(all(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in actual.module.body))

    def test_changed_notebook_is_rejected_before_execution(self):
        if not REFERENCE.is_file():
            self.skipTest("run the YinYangFit input preparation first")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "changed.ipynb"
            path.write_bytes(REFERENCE.read_bytes() + b"\n")
            with self.assertRaisesRegex(recovery.RecoveryError, "identity"):
                recovery.load_source(path)

    def test_exact_quadratic_risk_is_distinct_from_observed_float_loss(self):
        values = [9, 1, 0, 1, 25]
        coefficients = rational_cubic(values)
        self.assertEqual(coefficients, [0, 1, 0, 0])
        analysis = recovery.loss_analysis(values)
        self.assertEqual(analysis["branch"], "cubic")
        self.assertEqual(analysis["exact_cubic_coefficients"], list(map(str, coefficients)))
        self.assertEqual(analysis["status"], "degenerate_cubic_requires_model_decision")
        # This is the adapter's explicit exact-algebra gate, not an assertion
        # that the original float32 formula throws or returns NaN.

    def test_nondegenerate_cubic_and_categorical_branches(self):
        values = [6.625, 1.875, 1, 2.125, 41.625]  # x^3/8 + x^2 + 1
        coefficients = rational_cubic(values)
        self.assertEqual(coefficients, [Fraction(1, 8), 1, 0, 1])
        actual = recovery.loss_analysis(values)
        self.assertEqual(actual["branch"], "cubic")
        self.assertEqual(actual["status"], "valid_for_original_evaluation")
        self.assertEqual(actual["exact_cubic_coefficients"], list(map(str, coefficients)))
        for values in ([1, 2, 3, 4, 5], [5, 4, 3, 2, 1], [1, 1, 1, 1, 1]):
            with self.subTest(values=values):
                self.assertEqual(recovery.loss_analysis(values)["branch"], "categorical")

    def test_loss_preflight_requires_five_finite_values(self):
        for values in ([1, 2, 3, 4], [1, 2, 3, 4, 5, 6], [1, 2, math.nan, 4, 5],
                       [1, 2, math.inf, 4, 5]):
            with self.subTest(values=values), self.assertRaises(recovery.RecoveryError):
                recovery.loss_analysis(values)

    @unittest.skipUnless(importlib.util.find_spec("torch"), "isolated Torch recovery environment required")
    def test_original_float_loss_observation_keeps_analytical_policy_separate(self):
        if not REFERENCE.is_file():
            self.skipTest("run the YinYangFit input preparation first")
        observation = recovery.observe_original_loss(REFERENCE, [9, 1, 0, 1, 25])
        self.assertEqual(observation["exact_preflight"]["status"], "degenerate_cubic_requires_model_decision")
        self.assertIn("raw_loss", observation)
        self.assertIn("intermediates", observation)
        # A finite float result is permitted: pinverse can generate a tiny
        # nonzero cubic coefficient despite exact mathematical degeneration.

    @unittest.skipUnless(importlib.util.find_spec("torch"), "isolated Torch recovery environment required")
    def test_loss_observation_matches_direct_original_function_execution(self):
        if not REFERENCE.is_file():
            self.skipTest("run the YinYangFit input preparation first")
        import torch

        notebook = json.loads(REFERENCE.read_bytes())
        source = ast.parse("".join(notebook["cells"][13]["source"]))
        function = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == "estimate_min_loss")
        namespace = dict(T=torch, dev=torch.device("cpu"), sample_distance_deltas=DELTAS,
                         ce_criterion=torch.nn.CrossEntropyLoss())
        exec(compile(ast.Module(body=[function], type_ignores=[]), "independent-original-loss", "exec"), namespace)
        for values in ([1, 2, 3, 4, 5], [6.625, 1.875, 1, 2.125, 41.625], [9, 1, 0, 1, 25]):
            with self.subTest(values=values), contextlib.redirect_stdout(io.StringIO()):
                direct = namespace["estimate_min_loss"](torch.tensor([values], dtype=torch.float32))
                observed = recovery.observe_original_loss(REFERENCE, values)
                if torch.isfinite(direct):
                    self.assertEqual(observed["raw_float32_status"], "finite")
                    self.assertEqual(observed["raw_loss"], float(direct))
                else:
                    self.assertEqual(observed["raw_float32_status"], "nonfinite")
        categorical = recovery.observe_original_loss(REFERENCE, [1, 2, 3, 4, 5])
        expected = 3 + math.log(sum(math.exp(-v) for v in [1, 2, 3, 4, 5]))
        self.assertAlmostEqual(categorical["raw_loss"], expected, places=6)

    @unittest.skipUnless(importlib.util.find_spec("torch"), "isolated Torch recovery environment required")
    def test_noise_policy_preserves_reference_draws_without_global_patch(self):
        import torch

        original = torch.randn_like
        example = torch.ones(17, dtype=torch.float64)
        reference = recovery._TorchFacade(torch, "reference_seeded_per_pair")
        disabled = recovery._TorchFacade(torch, "noise_off")
        torch.manual_seed(876)
        expected = original(example)
        torch.manual_seed(876)
        torch.testing.assert_close(reference.randn_like(example), expected, rtol=0, atol=0)
        torch.testing.assert_close(disabled.randn_like(example), torch.zeros_like(example), rtol=0, atol=0)
        self.assertIs(torch.randn_like, original)


@unittest.skipIf(np is None, "NumPy required for retained input verification")
class OriginalDomainInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (INPUTS / "manifest.json").is_file():
            raise unittest.SkipTest("run the YinYangFit input preparation first")
        cls.loaded = recovery.load_inputs(INPUTS)

    def mutation(self, arrays=None, manifest=None, update_identities=True):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        values = {k: v.copy() for k, v in self.loaded["arrays"].items()}
        if arrays:
            arrays(values)
        data = copy.deepcopy(self.loaded["manifest"])
        if manifest:
            manifest(data)
        np.savez(directory / "inputs.npz", **values)
        if update_identities:
            data["inputs_npz_sha256"] = digest((directory / "inputs.npz").read_bytes())
            data["array_identities"] = {
                k: dict(dtype=str(v.dtype), shape=list(v.shape), sha256=digest(v.tobytes())) for k, v in values.items()
            }
        (directory / "manifest.json").write_text(json.dumps(data, allow_nan=False))
        return directory

    def test_complete_fixed_domain_and_normalized_coverage(self):
        arrays, manifest = self.loaded["arrays"], self.loaded["manifest"]
        self.assertEqual(arrays["glyph_images"].shape, (26, 80, 161))
        self.assertEqual(manifest["font"]["requested_x_height_px"], 34)
        self.assertEqual(manifest["font"]["selected_ppem"], 78)
        self.assertNotEqual(manifest["font"]["selected_ppem"], 34)
        self.assertEqual(len(manifest["pairs"]), 676)
        self.assertEqual([p["pair"] for p in manifest["pairs"]], [a+b for a in "abcdefghijklmnopqrstuvwxyz"
                                                               for b in "abcdefghijklmnopqrstuvwxyz"])
        self.assertTrue(np.any((arrays["glyph_images"] > 0) & (arrays["glyph_images"] < 1)))
        self.assertEqual(manifest["inputs_npz_sha256"], self.loaded["npz_sha256"])

    def test_all_candidate_translations_against_independent_integer_equation(self):
        arrays, manifest = self.loaded["arrays"], self.loaded["manifest"]
        widths = arrays["glyph_ink_widths"]
        glyphs = {g["codepoint"]: g for g in manifest["glyphs"]}
        differences = []
        for i, pair in enumerate(manifest["pairs"]):
            a, b = pair["left"], pair["right"]
            w = int(widths[a-97]) + int(widths[b-97])
            minimum = pair["minimum_ink_distance_px"]
            center = int(pair["pair_distance_px"] + minimum)
            self.assertEqual(pair["label_center_px"], center)
            for j, delta in enumerate(DELTAS):
                distance = center + delta
                left = -(math.ceil((w-minimum)/2) + math.ceil(distance/2)) + math.floor(w/4)
                right = math.floor((w-minimum)/2) + math.floor(distance/2) - math.ceil(w/4)
                self.assertEqual(int(arrays["translations_left"][i, j]), left)
                self.assertEqual(int(arrays["translations_right"][i, j]), right)
                candidate = pair["candidates"][j]
                self.assertEqual((candidate["translation_left_px"], candidate["translation_right_px"]), (left, right))
                self.assertEqual(candidate["delta_px"], delta)
                self.assertEqual(candidate["clipping_left"]["nonzero_samples"], 0)
                self.assertEqual(candidate["clipping_right"]["nonzero_samples"], 0)
                ink_step = glyphs[b]["padding_left"] + right - glyphs[a]["padding_left"] - left
                font_step = ink_step + glyphs[a]["lsb_px"] - glyphs[b]["lsb_px"]
                self.assertEqual(candidate["font_origin_step_px"], font_step)
            differences.append(pair["center_origin_step_difference_px"])
        # Original centering/rounding is preserved even where it differs from
        # source advances; this experiment must not silently "correct" labels.
        self.assertTrue(any(v != 0 for v in differences))

    def test_archive_and_manifest_source_mutations_are_rejected(self):
        def image_change(values):
            values["glyph_images"][0, 0, 0] = 0.5
        with self.assertRaisesRegex(recovery.RecoveryError, "identity"):
            recovery.load_inputs(self.mutation(arrays=image_change, update_identities=False))
        mutations = [lambda m: m.update(schema_version="unknown"),
                     lambda m: m.update(status="partial"),
                     lambda m: m["font"].update(requested_x_height_px=16),
                     lambda m: m["source_lock"].update(crimson_revision="0"*40)]
        for change in mutations:
            with self.subTest(change=change), self.assertRaises(recovery.RecoveryError):
                recovery.load_inputs(self.mutation(manifest=change))

    def test_invalid_numerics_and_dtypes_are_rejected_after_valid_hashes(self):
        def change_image(values):
            values["glyph_images"][0, 0, 0] = np.nan
        def change_label(values):
            values["labels"][0] = 3
        def change_dtype(values):
            values["codepoints"] = values["codepoints"].astype(np.float64)
        def overflow_shift(values):
            values["translations_left"][0, 0] = np.iinfo(np.int32).min
        def clip_without_changing_candidate_differences(values):
            values["translations_left"][0] -= 100
            values["translations_right"][0] -= 100
        def collapse(values):
            values["translations_right"][0, 0] = (
                values["translations_right"][0, 2] - values["translations_left"][0, 2]
                + values["translations_left"][0, 0])
        for change in (change_image, change_label, change_dtype, overflow_shift,
                       clip_without_changing_candidate_differences, collapse):
            with self.subTest(change=change), self.assertRaises(recovery.RecoveryError):
                recovery.load_inputs(self.mutation(arrays=change))

    @unittest.skipUnless(importlib.util.find_spec("freetype") and importlib.util.find_spec("fontTools"),
                         "locked FreeType/fontTools recovery environment required")
    def test_glyph_images_against_direct_freetype_oracle(self):
        import freetype
        from fontTools.ttLib import TTFont

        font_path = SOURCES / "CrimsonRoman.otf"
        if not font_path.is_file():
            self.skipTest("locked font source not prepared")
        manifest = self.loaded["manifest"]
        self.assertEqual(digest(font_path.read_bytes()), manifest["source_lock"]["files"]["CrimsonRoman.otf"]["sha256"])
        face = freetype.Face(str(font_path))
        face.set_pixel_sizes(0, face.units_per_EM)
        face.load_char("x", freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_MONO)
        scale = 34 / face.glyph.bitmap.rows
        face.set_pixel_sizes(0, int(face.units_per_EM * scale))
        ascender, descender = int(face.ascender * scale), int(face.descender * scale)
        self.assertEqual((ascender, descender), (58, -22))
        ttfont = TTFont(font_path)
        for i, ch in enumerate("abcdefghijklmnopqrstuvwxyz"):
            face.load_glyph(ttfont.getGlyphID(ch), freetype.FT_LOAD_RENDER)
            slot, glyph = face.glyph, manifest["glyphs"][i]
            bitmap = np.asarray(slot.bitmap.buffer, dtype=np.uint8).reshape(slot.bitmap.rows, slot.bitmap.width)
            self.assertEqual(glyph["glyph_id"], ttfont.getGlyphID(ch))
            self.assertEqual(glyph["ink_width"], bitmap.shape[1])
            top = ascender - slot.bitmap_top
            left = math.ceil((161 - bitmap.shape[1]) / 2)
            frame = np.zeros((ascender-descender, 161), dtype=np.float64)
            frame[top:top+bitmap.shape[0], left:left+bitmap.shape[1]] = bitmap / 255
            np.testing.assert_array_equal(frame.astype(np.float32), self.loaded["arrays"]["glyph_images"][i])
        ttfont.close()

    @unittest.skipUnless(importlib.util.find_spec("uharfbuzz"), "locked HarfBuzz recovery environment required")
    def test_source_pair_metrics_against_raw_coverage_and_harfbuzz_oracles(self):
        import uharfbuzz as hb

        font_path = SOURCES / "CrimsonRoman.otf"
        if not font_path.is_file():
            self.skipTest("locked font source not prepared")
        manifest, arrays = self.loaded["manifest"], self.loaded["arrays"]
        # This pinned CFF input uses upstream's HarfBuzz fallback. Do not
        # silently compare the differently scaled FreeType kerning branch.
        self.assertFalse(manifest["font"]["has_freetype_kerning"])
        hbface = hb.Face(font_path.read_bytes())
        hbfont = hb.Font(hbface)
        scale = hbface.upem * manifest["font"]["scale_factor"]
        hbfont.scale = (scale, scale)
        glyphs = {g["codepoint"]: g for g in manifest["glyphs"]}
        left, right = {}, {}
        for cp, glyph in glyphs.items():
            start = glyph["padding_left"]
            samples = arrays["glyph_images"][cp-97, :, start:start+glyph["ink_width"]]
            # Reconstruct exact 0..255 integer samples before applying the
            # author's cutoff30; float32 normalization could otherwise move
            # a sample exactly at30 across the strict boundary.
            coverage = np.rint(samples.astype(np.float64) * 255).astype(np.uint8)
            mask = coverage > 30
            occupied = np.any(mask, axis=1)
            left[cp] = np.where(occupied, np.argmax(mask, axis=1), 10000)
            right[cp] = np.where(occupied, np.argmax(mask[:, ::-1], axis=1), 10000)
        for pair in manifest["pairs"]:
            advances = []
            for enabled in (True, False):
                buffer = hb.Buffer()
                buffer.add_str(pair["pair"])
                buffer.guess_segment_properties()
                hb.shape(hbfont, buffer, {"kern": enabled})
                advances.append(buffer.glyph_positions[0].x_advance)
            kern = advances[0] - advances[1]
            a, b = pair["left"], pair["right"]
            self.assertEqual(pair["kerning_px"], kern)
            self.assertEqual(pair["pair_distance_px"], glyphs[a]["rsb_px"] + glyphs[b]["lsb_px"] + kern)
            self.assertEqual(pair["minimum_ink_distance_px"], int(np.min(right[a] + left[b])))


if __name__ == "__main__":
    unittest.main()
