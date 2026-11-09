"""Source-reference relationships and safe standalone diagnostic publication."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stem_curve_probe import Experiment, analytic_checks, run_probe, transformed


def rectangle(height=4):
    return [dict(op="move_to", x=0, y=0), dict(op="line_to", x=2, y=0),
            dict(op="line_to", x=2, y=height), dict(op="line_to", x=0, y=height), dict(op="close")]


def oval(height=4):
    return [dict(op="move_to", x=0, y=height / 2),
            dict(op="quad_to", x1=0, y1=height, x=2, y=height),
            dict(op="quad_to", x1=4, y1=height, x=4, y=height / 2),
            dict(op="quad_to", x1=4, y1=0, x=2, y=0),
            dict(op="quad_to", x1=0, y1=0, x=0, y=height / 2), dict(op="close")]


def capture():
    glyphs = []
    for char in "nHoOaeAx":
        height = 6 if char.isupper() else 4
        commands = oval(height) if char in "oOe" else rectangle(height)
        if char == "x":
            commands = [dict(op="move_to", x=0, y=0), dict(op="line_to", x=2, y=0),
                        dict(op="line_to", x=6, y=4), dict(op="line_to", x=4, y=4), dict(op="close")]
        glyphs.append(dict(codepoint=ord(char), source_commands=transformed(commands, 100),
                           source_advance_px=4.5 if char == "a" else 5 if char in "oOe" else 4,
                           bitmap=dict(left=0, top=-height, width=2, height=height, pixels=[1] * (2 * height))))
    return dict(schema_version="contextual-spacing-capture-v1", size_px=10, units_per_em=1000,
                axes={}, glyphs=glyphs, source_pairs=[dict(left=ord("n"), right=ord("o"), adjustment_px=-.25)])


class StemCurveProbeTests(unittest.TestCase):
    def test_six_references_reconstruct_and_mixed_direction_is_explicit(self):
        model = Experiment(capture(), "source_reference_bounds")
        self.assertEqual(len(model.refs), 6)
        for reference in model.refs.values():
            self.assertEqual(reference["status"], "available")
            self.assertEqual(reference["reconstruction_error_px"], 0)
        self.assertEqual(model.refs[("lowercase", "stem_stem")]["source_border_gap_px"], 2)
        self.assertEqual(model.refs[("lowercase", "curve_curve")]["source_border_gap_px"], 1)
        self.assertEqual(model.refs[("lowercase", "mixed")]["source_border_gap_px"], 1.75)
        forward, reverse = (model.pair(*map(ord, pair)) for pair in ("ae", "ea"))
        self.assertEqual(forward["required_step_px"], 3.75)
        self.assertEqual(forward["origin_shift_px"], -.75)
        self.assertEqual(reverse["required_step_px"], 5.75)
        self.assertEqual(reverse["origin_shift_px"], .75)
        self.assertFalse(forward["reverse_mixed_adaptation"])
        self.assertTrue(reverse["reverse_mixed_adaptation"])
        self.assertEqual(analytic_checks()["cases"], 32)

    def test_source_only_bounds_ignore_bitmap_and_preserve_coordinate_relationships(self):
        value = capture()
        with patch("stem_curve_probe.walls._bitmap_rows", side_effect=AssertionError("bitmap used")), \
                patch("stem_curve_probe.walls.bitmap_profile", side_effect=AssertionError("bitmap used")):
            original = Experiment(value, "source_reference_bounds").pair(*map(ord, "ae"))
        translated = copy.deepcopy(value)
        for glyph in translated["glyphs"]:
            glyph["source_commands"] = transformed(glyph["source_commands"], dx=700, dy=-300)
        moved = Experiment(translated, "source_reference_bounds").pair(*map(ord, "ae"))
        self.assertAlmostEqual(moved["source_border_gap_px"], original["source_border_gap_px"])
        self.assertAlmostEqual(moved["required_step_px"], original["required_step_px"])
        scaled = copy.deepcopy(value)
        scaled["size_px"] *= 3
        for glyph in scaled["glyphs"]:
            glyph["source_advance_px"] *= 3
        for pair in scaled["source_pairs"]:
            pair["adjustment_px"] *= 3
        enlarged = Experiment(scaled, "source_reference_bounds").pair(*map(ord, "ae"))
        self.assertAlmostEqual(enlarged["source_border_gap_px"], 3 * original["source_border_gap_px"])
        self.assertAlmostEqual(enlarged["required_step_px"], 3 * original["required_step_px"])

    def test_missing_reference_and_unsupported_pairs_preserve_source_explicitly(self):
        value = capture()
        value["glyphs"] = [glyph for glyph in value["glyphs"] if glyph["codepoint"] != ord("o")]
        model = Experiment(value, "source_reference_bounds")
        missing = model.pair(*map(ord, "ee"))
        self.assertEqual(missing["status"], "abstained")
        self.assertEqual(missing["reference_failure"], "missing_reference_glyph")
        self.assertEqual(missing["required_step_px"], missing["source_step_px"])
        self.assertEqual(missing["origin_shift_px"], 0)
        self.assertEqual(missing["generic_source_only_status"], "solved")
        self.assertEqual(missing["paper_like_composition_status"], "generic_fallback_solved")
        for pair in ("Aa", "ax"):
            unsupported = model.pair(*map(ord, pair))
            self.assertEqual(unsupported["status"], "abstained")
            self.assertEqual(unsupported["required_step_px"], unsupported["source_step_px"])
            self.assertEqual(unsupported["origin_shift_px"], 0)
        summary = model.summarize([tuple(map(ord, pair)) for pair in ("nn", "ee", "Aa", "ax")])
        self.assertEqual(summary["supported_occurrences"], 1)
        self.assertEqual(summary["statuses"], {"solved": 1, "abstained": 3})

    def test_output_is_complete_new_and_pins_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "example.json"
            source.write_text(json.dumps(capture()))
            presets = root / "presets.json"
            presets.write_text(json.dumps([dict(id=name, text="nn oo ae ea ax Aa") for name in
                                          ("lynx-lowercase", "lynx-uppercase", "aaron-abraham")]))
            output = root / "output"
            result = run_probe(output, [source], presets)
            self.assertEqual(result["status"], "completed_source_only")
            self.assertEqual({path.name for path in output.iterdir()}, {"summary.json", "identities.json", "example.json"})
            identities = json.loads((output / "identities.json").read_text())
            self.assertEqual(identities["captures"][str(source.resolve())], hashlib.sha256(source.read_bytes()).hexdigest())
            previous = {path.name: path.read_bytes() for path in output.iterdir()}
            with self.assertRaises(FileExistsError):
                run_probe(output, [source], presets)
            self.assertEqual(previous, {path.name: path.read_bytes() for path in output.iterdir()})
            with self.assertRaisesRegex(ValueError, "distinct"):
                run_probe(root / "duplicate", [source, source], presets)
            self.assertFalse((root / "duplicate").exists())
            reserved = root / "Summary.json"
            reserved.write_text(source.read_text())
            with self.assertRaisesRegex(ValueError, "reserved"):
                run_probe(root / "reserved", [reserved], presets)
            self.assertFalse((root / "reserved").exists())


if __name__ == "__main__":
    unittest.main()
