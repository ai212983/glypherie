"""Diagnostic decomposition and preservation of fixed-domain boundaries."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from density_probe import (BitmapOracle, DOMAINS, PRESET_IDS, compose, evaluate_capture,
                           load_presets, run_probe, verify_clearance)


def rectangle(width=2, height=4, scale=1):
    return [dict(op="move_to", x=0, y=0), dict(op="line_to", x=width * scale, y=0),
            dict(op="line_to", x=width * scale, y=height * scale),
            dict(op="line_to", x=0, y=height * scale), dict(op="close")]


def capture():
    codepoints = sorted({cp for domain in DOMAINS.values() for pair in domain for cp in pair})
    glyphs = []
    for cp in codepoints:
        height = 4 if chr(cp).islower() else 6 if chr(cp).isupper() else 5
        advance = 4 if cp == ord("a") else 6
        glyphs.append(dict(codepoint=cp, glyph_id=cp, source_commands=rectangle(height=height, scale=100),
            produced_commands=rectangle(height=height), source_advance_px=advance,
            finalized_advance_px=advance,
            bitmap=dict(left=0, top=-height, width=2, height=height, pixels=[1] * (2 * height))))
    return dict(schema_version="contextual-spacing-capture-v1", source_sha256="synthetic-density",
        size_px=10, units_per_em=1000, axes={}, monospace=False, tabular_digits=False,
        glyphs=glyphs, source_pairs=[], metric_pairs_on=[], metric_pairs_off=[])


class DensityProbeTests(unittest.TestCase):
    def test_closed_cell_oracle_distinguishes_overlap_edge_and_corner(self):
        def glyph(left, top):
            return dict(bitmap=dict(left=left, top=top, width=1, height=1, pixels=[1]))
        oracle = BitmapOracle({1: glyph(0, 0), 2: glyph(0, 0), 3: glyph(0, 1)})
        self.assertEqual(oracle.contacts(1, 2, 0)["overlap_pixel_pairs"], 1)
        self.assertEqual(oracle.contacts(1, 2, 1)["edge_pixel_pairs"], 1)
        self.assertEqual(oracle.contacts(1, 3, 1)["corner_pixel_pairs"], 1)
        self.assertTrue(oracle.contacts(1, 3, 2)["contact_free"])
        with self.assertRaises(ValueError):
            oracle.contacts(1, 2, .5)

    def test_touching_is_telemetry_but_overlap_and_same_row_order_are_hard_checks(self):
        def glyph(pixels, top=0):
            return dict(bitmap=dict(left=0, top=top, width=len(pixels), height=1, pixels=pixels))
        oracle = BitmapOracle({1: glyph([1]), 2: glyph([1]), 3: glyph([1], top=1),
                               4: glyph([1, 0, 1]), 5: glyph([0, 1, 0])})
        for right in (2, 3):
            touching = oracle.contacts(1, right, 1)
            self.assertTrue(touching["overlap_free"])
            self.assertTrue(verify_clearance(touching, "no_overlap"))
            with self.assertRaisesRegex(ValueError, "strict"):
                verify_clearance(touching, "strict")
        with self.assertRaisesRegex(ValueError, "no_overlap"):
            verify_clearance(oracle.contacts(1, 2, 0), "no_overlap")
        interlocked = oracle.contacts(4, 5, 0)
        self.assertTrue(interlocked["overlap_free"])
        self.assertFalse(interlocked["same_row_wall_order"])
        with self.assertRaisesRegex(ValueError, "no_overlap"):
            verify_clearance(interlocked, "no_overlap")

    def test_overlap_only_arm_keeps_target_and_rounding_while_strict_control_stays_separate(self):
        value = capture()
        for glyph in value["glyphs"]:
            glyph.update(source_advance_px=2.25, finalized_advance_px=2)
        before = copy.deepcopy(value)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "capture.json"
            path.write_text(json.dumps(value))
            result = evaluate_capture(value, path, "touching", {name: "aaaa" for name in PRESET_IDS}, samples_per_px=2)
        self.assertEqual(value, before)
        strict = result["models"]["bitmap:source_origin"]
        touching = result["models"]["bitmap:source_origin:no_overlap"]
        self.assertEqual(strict["metadata"]["clearance_policy"], "strict")
        self.assertEqual(touching["metadata"]["clearance_policy"], "no_overlap")
        self.assertNotEqual(strict["metadata"]["identity"], touching["metadata"]["identity"])
        for strict_record, touching_record in zip(strict["pair_records"], touching["pair_records"]):
            if not strict_record["captured"]:
                continue
            for key in ("target_px", "offset_px", "optical_step_px"):
                self.assertEqual(strict_record.get(key), touching_record.get(key))
            a, b = strict_record["composition"], touching_record["composition"]
            self.assertEqual(a["rounded_unconstrained_step_px"], b["rounded_unconstrained_step_px"])
            if a["eligible"]:
                self.assertEqual(a["emitted_step_px"], 3)
                self.assertEqual(b["emitted_step_px"], 2)
                self.assertTrue(a["contact_check"]["contact_free"])
                self.assertTrue(b["contact_check"]["overlap_free"])
                self.assertFalse(b["contact_check"]["contact_free"])
        counts = touching["presets"]["lynx-lowercase"]
        self.assertEqual(counts["eligible_optical_occurrences"], 3)
        self.assertEqual(counts["overlap_free_occurrences"], 3)
        self.assertEqual(counts["edge_contact_occurrences"], 3)
        self.assertEqual(counts["overlap_pixel_pairs"], 0)
        self.assertEqual(counts["same_row_ordered_occurrences"], 3)
        self.assertEqual(counts["contact_free_occurrences"], 0)
        self.assertEqual(result["checks"]["bitmap_solver_composition"]["hu_density_conserved_touch"]["status"], "passed")

    def test_rounding_and_clearance_are_separate_and_fallback_is_not_a_solve(self):
        value = capture()
        glyphs = {g["codepoint"]: g for g in value["glyphs"]}
        pair = (ord("a"), ord("b"))
        measured = dict(reason=None, optical_step_px=2.4, offset_px=-2, target_px=.4)
        result = compose(measured, glyphs, pair, 4, 4)
        self.assertEqual(result["rounded_unconstrained_step_px"], 2)
        self.assertAlmostEqual(result["rounding_delta_px"], -.4)
        self.assertEqual(result["clearance_delta_px"], 2)
        self.assertAlmostEqual(result["post_constraint_target_residual_px"], 1.6)
        self.assertTrue(result["eligible"])
        fallback = compose(dict(reason="calibration_unavailable"), glyphs, pair, 4, 7)
        self.assertFalse(fallback["eligible"])
        self.assertEqual(fallback["emitted_step_px"], 4)
        self.assertIsNone(fallback["rounding_delta_px"])
        self.assertIsNone(fallback["clearance_delta_px"])

    def test_fitted_wall_units_and_target_are_separate_from_bitmap_clearance(self):
        value = capture()
        a = next(glyph for glyph in value["glyphs"] if glyph["codepoint"] == ord("a"))
        # Source width is 200 design units -> 2 px. Produced commands already
        # express a 3 px fitted shape; delivered ink remains the 2 px bitmap.
        a["produced_commands"] = rectangle(width=3)
        before = copy.deepcopy(value)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "capture.json"
            path.write_text(json.dumps(value))
            result = evaluate_capture(value, path, "fitted", {name: "ab" for name in PRESET_IDS}, samples_per_px=2)
        self.assertEqual(value, before)
        fitted = result["models"]["fitted_outline:source_origin:no_overlap"]
        bitmap = result["models"]["bitmap:source_origin:no_overlap"]
        source = result["models"]["source:source_origin"]
        fit_lower, bitmap_lower = fitted["classes"]["lowercase"], bitmap["classes"]["lowercase"]
        self.assertAlmostEqual(source["classes"]["lowercase"]["mean_candidate_offset_px"], -2)
        self.assertAlmostEqual(bitmap_lower["mean_candidate_offset_px"], -2)
        self.assertAlmostEqual(fit_lower["mean_candidate_offset_px"], -2 - 1 / 26)
        self.assertAlmostEqual(fit_lower["target_px"], fit_lower["mean_source_step_px"] - 2 - 1 / 26)
        self.assertNotEqual(fit_lower["target_px"], bitmap_lower["target_px"])
        self.assertEqual(fit_lower["conservation_check"]["status"], "passed")
        fit_pair = next(record for record in fitted["pair_records"] if record["pair"] == "ab")
        bitmap_pair = next(record for record in bitmap["pair_records"] if record["pair"] == "ab")
        self.assertEqual(fit_pair["composition"]["emitted_step_px"], 7)
        self.assertEqual(bitmap_pair["composition"]["emitted_step_px"], 6)
        self.assertEqual(fit_pair["composition"]["clearance_min_step_px"], 2)
        self.assertEqual(fit_pair["composition"]["clearance_min_step_px"], bitmap_pair["composition"]["clearance_min_step_px"])
        self.assertTrue(fit_pair["composition"]["contact_check"]["overlap_free"])
        self.assertEqual(result["checks"]["bitmap_solver_composition"]["hu_fitted_density_conserved_touch"]["candidate_geometry"], "fitted_outline")

    def test_fixed_mean_conservation_does_not_claim_held_out_text_conservation(self):
        value = capture()
        before = copy.deepcopy(value)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "capture.json"
            path.write_text(json.dumps(value))
            result = evaluate_capture(value, path, "synthetic", {name: "aaaa" for name in PRESET_IDS}, samples_per_px=2)
        self.assertEqual(value, before)
        self.assertEqual({key: len(domain) for key, domain in DOMAINS.items()},
                         dict(lowercase=676, uppercase=676, digits=100, mixed=1352))
        for geometry in ("source", "bitmap", "fitted_outline"):
            model = result["models"][geometry + ":source_origin"]
            lower = model["classes"]["lowercase"]
            self.assertEqual(lower["declared_pairs"], 676)
            self.assertEqual(lower["conservation_check"]["status"], "passed")
            held_out = model["presets"]["lynx-lowercase"]
            self.assertEqual(held_out["pair_occurrences"], 3)
            self.assertGreater(held_out["continuous_source_step_drift"]["mean_px"], 1)
            self.assertEqual(held_out["clearance_delta"]["mean_px"], 0)
            self.assertEqual(held_out["contact_verified_occurrences"], 3)
        for status in result["checks"]["source_arms_coincide"].values():
            self.assertEqual(status["status"], "passed")

    def test_missing_letter_keeps_declared_domain_and_never_becomes_partial_calibration(self):
        value = capture()
        value["glyphs"] = [glyph for glyph in value["glyphs"] if glyph["codepoint"] != ord("z")]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "capture.json"
            path.write_text(json.dumps(value))
            result = evaluate_capture(value, path, "missing", {name: "aaa" + "z" for name in PRESET_IDS}, samples_per_px=1)
        lower = result["models"]["bitmap:source_origin"]["classes"]["lowercase"]
        self.assertFalse(lower["complete"])
        self.assertEqual(lower["declared_pairs"], 676)
        self.assertEqual(lower["metadata"]["reason"], "missing_calibration_glyph")
        self.assertIsNone(lower["continuous_mean_step_px"])
        self.assertEqual(lower["conservation_check"]["status"], "not_evaluated")
        summary = result["models"]["bitmap:source_origin"]["presets"]["lynx-lowercase"]
        self.assertEqual(summary["eligible_optical_occurrences"], 0)
        self.assertEqual(summary["missing_pair_occurrences"], 1)
        self.assertEqual(summary["captured_pair_occurrences"], 2)

    def test_publication_pins_inputs_requires_seven_presets_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "sample.json"
            source.write_text(json.dumps(capture()))
            presets = root / "presets.json"
            presets.write_text(json.dumps([dict(id=name, text="aaaa") for name in PRESET_IDS]))
            incomplete = root / "incomplete.json"
            incomplete.write_text(json.dumps([dict(id="numbers", text="01")]))
            with self.assertRaisesRegex(ValueError, "missing assessment presets"):
                load_presets(incomplete)
            output = root / "output"
            # Evaluate the real computation once in the conservation test;
            # publication itself is a separate atomic ownership contract.
            font = dict(font="sample", runtime_seconds=0.)
            with patch("density_probe.evaluate_capture", return_value=font), \
                    patch("density_probe.summarize_font", return_value=font):
                result = run_probe(output, [source], presets)
            self.assertEqual(result["status"], "completed_diagnostic")
            self.assertEqual(set(path.name for path in output.iterdir()), {"sample.json", "summary.json", "identities.json"})
            identities = json.loads((output / "identities.json").read_text())
            self.assertIn(str(source.resolve()), identities["captures"])
            self.assertIn("hu_density.py", result["helper_hashes"])
            previous = {path.name: path.read_bytes() for path in output.iterdir()}
            with self.assertRaises(FileExistsError):
                run_probe(output, [source], presets)
            self.assertEqual(previous, {path.name: path.read_bytes() for path in output.iterdir()})
            with self.assertRaisesRegex(ValueError, "distinct"):
                run_probe(root / "duplicate", [source, source], presets)
            self.assertFalse((root / "duplicate").exists())

    def test_changed_inputs_cannot_publish_stale_identities(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "sample.json"
            source.write_text(json.dumps(capture()))
            presets = root / "presets.json"
            presets.write_text(json.dumps([dict(id=name, text="aa") for name in PRESET_IDS]))

            def mutate(*_args):
                source.write_text(source.read_text() + "\n")
                return dict(font="sample", runtime_seconds=0.)

            with patch("density_probe.evaluate_capture", side_effect=mutate), \
                    patch("density_probe.summarize_font", side_effect=lambda value: value):
                with self.assertRaisesRegex(ValueError, "changed during probe"):
                    run_probe(root / "output", [source], presets)
            self.assertFalse((root / "output").exists())
            self.assertFalse(list(root.glob(".output-*")))


if __name__ == "__main__":
    unittest.main()
