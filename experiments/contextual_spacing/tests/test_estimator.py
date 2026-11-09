"""Analytic geometry tests and independent, compiled upstream-weight parity.

The C reference consumes captured edge arrays. It does not validate native
FontForge outline-to-envelope parity or establish optical acceptance.
"""

from dataclasses import FrozenInstanceError
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

EXPERIMENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXPERIMENT))
import estimator as e


def rectangle(x=0, y=0, width=100, height=100):
    return [{"op": "move_to", "x": x, "y": y},
            {"op": "line_to", "x": x + width, "y": y},
            {"op": "line_to", "x": x + width, "y": y + height},
            {"op": "line_to", "x": x, "y": y + height},
            {"op": "close"}]


def transform(commands, scale=1, dx=0, dy=0):
    return [{key: (value * scale + (dx if key.startswith("x") else dy)
                   if key in ("x", "y", "x1", "y1", "x2", "y2") else value)
             for key, value in command.items()} for command in commands]


QUADRATIC = [{"op": "move_to", "x": 0, "y": 0},
             {"op": "quad_to", "x1": 200, "y1": 50, "x": 0, "y": 100},
             {"op": "close"}]
CUBIC = [{"op": "move_to", "x": 0, "y": 0},
         {"op": "curve_to", "x1": 300, "y1": 100,
          "x2": 300, "y2": 200, "x": 0, "y": 300},
         {"op": "close"}]


class GeometryTests(unittest.TestCase):
    def test_rectangle_closed_bands_and_adjacent_separation(self):
        a = e.analyze(rectangle(), 1000)
        self.assertEqual(a.bounds, e.Bounds(0, 0, 100, 100))
        self.assertEqual((a.imin_y, a.imax_y), (0, 10))
        self.assertEqual(len(a.bands), 11)
        self.assertTrue(all(b.left == b.right == 0 for b in a.bands))
        self.assertEqual(e.separation(a, a, 1000), e.Separation(0, 10))

    def test_native_pair_band_option(self):
        a = e.analyze(rectangle(), 1000, subdivisions=200)
        self.assertEqual(a.band_height, 5)
        self.assertEqual(e.separation(a, a, 1000).shared_bands, 20)
        # Pinned entry points take int chunk_height and default through integer
        # division, so UPEM 2048 must not create 20.48/10.24-unit bands.
        self.assertEqual(e.analyze(rectangle(), 2048).band_height, 20)
        self.assertEqual(e.analyze(rectangle(), 2048, 200).band_height, 10)
        self.assertIsInstance(e.analyze(rectangle(), 2048).band_height, int)
        # Noninteger em is a declared adapter extension, floored by the same rule.
        self.assertEqual(e.analyze(rectangle(), 2048.5).band_height, 20)
        for em, subdivisions in ((99, 100), (199, 200), (0.5, 100)):
            with self.assertRaises(e.GeometryError):
                e.analyze(rectangle(), em, subdivisions)

    def test_line_and_horizontal_only_geometry(self):
        a = e.analyze([{"op": "move_to", "x": 0, "y": 0},
                       {"op": "line_to", "x": 100, "y": 100}], 1000)
        self.assertEqual(a.bands[0].left, 0)
        self.assertEqual(a.bands[0].right, -90)
        h = e.analyze([{"op": "move_to", "x": 0, "y": 0},
                       {"op": "line_to", "x": 100, "y": 0}], 1000)
        self.assertEqual(h.bounds, e.Bounds(0, 0, 100, 0))
        self.assertTrue(all(b.left is None for b in h.bands))
        self.assertEqual(e.separation(h, a, 1000).reason, "no_shared_bands")

    def test_empty_and_move_only(self):
        for commands in ([], [{"op": "move_to", "x": 5, "y": 7}]):
            a = e.analyze(commands, 1000)
            self.assertIsNone(a.bounds)
            self.assertEqual(a.bands, ())
            self.assertEqual(e.separation(a, a, 1000),
                             e.Separation(None, 0, "no_shared_bands"))

    def test_quadratic_true_extremum_and_clipped_endpoint(self):
        a = e.analyze(QUADRATIC, 1000)
        self.assertEqual(a.bounds.maxx, 100)
        self.assertEqual(a.bands[0].right, -64)
        self.assertEqual(a.bands[4].right, 0)
        self.assertEqual(a.bands[5].right, 0)
        self.assertEqual(a.bands[9].right, -64)
        # Native resets cached t after reaching maxy; the touching upper band
        # restarts at that monotonic portion's miny (x=100), not clipped x=0.
        self.assertEqual(a.bands[10].right, 0)

    def test_cubic_true_x_extremum(self):
        a = e.analyze(CUBIC, 1000)
        self.assertEqual(a.bounds.maxx, 225)
        self.assertEqual(a.bands[0].right, -196)
        self.assertEqual(a.bands[14].right, 0)
        self.assertEqual(a.bands[15].right, 0)

    def test_cubic_true_y_extremum_and_horizontal_tangent(self):
        commands = [{"op": "move_to", "x": 0, "y": 0},
                    {"op": "curve_to", "x1": 0, "y1": 300,
                     "x2": 100, "y2": 300, "x": 100, "y": 0}]
        a = e.analyze(commands, 1000)
        self.assertEqual(a.bounds.maxy, 225)
        self.assertEqual((a.imin_y, a.imax_y), (0, 23))
        self.assertIsNone(a.bands[23].left)
        self.assertIsNotNone(a.bands[22].left)

    def test_boundary_touch_and_upper_loop_exclusion(self):
        a = e.analyze(rectangle(height=10), 1000)
        b = e.analyze(rectangle(y=10, height=10), 1000)
        self.assertIsNotNone(a.bands[1].right)
        self.assertIsNotNone(b.bands[0].left)
        # Shared touching band is allocated, but is the upper loop boundary.
        self.assertEqual(e.separation(a, b, 1000).reason, "no_shared_bands")

    def test_disconnected_marks_preserve_empty_bands(self):
        a = e.analyze(rectangle(height=20) + rectangle(y=80, width=30, height=20), 1000)
        self.assertIsNone(a.bands[4].left)
        self.assertEqual(a.bands[8].right, -70)
        # Lower-bound touch of the detached mark contributes band 7 as native.
        self.assertEqual(e.separation(a, a, 1000).shared_bands, 6)

    def test_translation_by_band_lattice_preserves_offsets_and_estimate(self):
        a = e.analyze(QUADRATIC, 1000)
        b = e.analyze(transform(QUADRATIC, dx=-23, dy=20), 1000)
        self.assertEqual([(v.left, v.right) for v in a.bands],
                         [(v.left, v.right) for v in b.bands])
        self.assertEqual(e.separation(a, a, 1000).estimate,
                         e.separation(b, b, 1000).estimate)

    def test_scale_is_subject_to_design_unit_quantization(self):
        # Source floors in design units: scaling is intentionally not exact for
        # arbitrary factors. Assert the declared <=1-unit edge rounding bound.
        a = e.analyze(QUADRATIC, 1000)
        factor = 1.7
        b = e.analyze(transform(QUADRATIC, scale=factor), 1000 * factor)
        self.assertEqual(len(a.bands), len(b.bands))
        for left, right in zip(a.bands, b.bands):
            self.assertLessEqual(abs(right.right - factor * left.right), factor + 1)
        rectangle_a = e.analyze(rectangle(), 1000)
        rectangle_b = e.analyze(transform(rectangle(), scale=factor), 1700)
        self.assertEqual(e.separation(rectangle_a, rectangle_a, 1000).estimate, 0)
        self.assertEqual(e.separation(rectangle_b, rectangle_b, 1700).estimate, 0)

    def test_immutable_records(self):
        a = e.analyze(rectangle(), 1000)
        with self.assertRaises(FrozenInstanceError):
            a.imin_y = 1

    def test_nonfinite_and_invalid_settings_rejected(self):
        for value in (math.inf, -math.inf, math.nan, "12", True, 10 ** 1000):
            with self.subTest(value=str(value)[:20]):
                with self.assertRaises(e.GeometryError):
                    e.analyze(rectangle(), value)
                with self.assertRaises(e.GeometryError):
                    e.analyze([{"op": "move_to", "x": value, "y": 0}], 1000)
        for subdivisions in (0, -1, True, 1.5, 10 ** 1000):
            with self.assertRaises(e.GeometryError):
                e.analyze(rectangle(), 1000, subdivisions)
        with self.assertRaises(e.GeometryError):
            e.analyze(rectangle(), 0)

    def test_malformed_commands(self):
        for commands in ([{"op": "close"}], [{"op": "line_to", "x": 0, "y": 1}],
                         [{"op": "move_to", "x": 0}], [{"op": "unsupported"}], [None]):
            with self.assertRaises(e.GeometryError):
                e.analyze(commands, 1000)

    def test_work_limits_and_short_sentinels(self):
        with patch.object(e, "MAX_COMMANDS", 1), self.assertRaises(e.WorkLimitExceeded):
            e.analyze(rectangle(), 1000)
        with patch.object(e, "MAX_BANDS", 3), self.assertRaises(e.WorkLimitExceeded):
            e.analyze(rectangle(), 1000)
        with patch.object(e, "MAX_BAND_VISITS", 1), self.assertRaises(e.WorkLimitExceeded):
            e.analyze(rectangle(), 1000)
        commands = [{"op": "move_to", "x": 0, "y": 0},
                    {"op": "line_to", "x": 100000, "y": 100}]
        with self.assertRaises(e.UnsupportedGeometry):
            e.analyze(commands, 1000)

    def test_settings_must_match(self):
        a = e.analyze(rectangle(), 1000)
        b = e.analyze(rectangle(), 1000, 200)
        with self.assertRaises(e.GeometryError):
            e.separation(a, b, 1000)
        with self.assertRaises(e.GeometryError):
            e.separation(a, a, 2000)


class UpstreamWeightedParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("cc")
        if compiler is None:
            raise RuntimeError("cc required for independent pinned C estimator parity")
        cls.temp = tempfile.TemporaryDirectory()
        cls.binary = str(Path(cls.temp.name) / "weighted-estimator")
        subprocess.run([compiler, "-std=c99", "-O0", "-ffp-contract=off", "-fno-fast-math",
                        str(EXPERIMENT / "reference" /
                        "weighted_estimator.c"), "-lm", "-o", cls.binary], check=True,
                       capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def reference(self, a, b, em):
        rows = [f"{a.imin_y} {a.imax_y} {b.imin_y} {b.imax_y} {em / 50:.17g}"]
        for glyph in (a, b):
            rows.extend(f"{v.left if v.left is not None else 32767} "
                        f"{v.right if v.right is not None else -32767}" for v in glyph.bands)
        result = subprocess.run([self.binary], input="\n".join(rows), text=True,
                                capture_output=True, check=True)
        return int(result.stdout)

    def test_extracted_function_provenance(self):
        reference = EXPERIMENT / "reference"
        metadata = json.loads((reference / "source.json").read_text())
        text = (reference / "weighted_estimator.c").read_text()
        fn = text[text.index("static int aw2_bbox_separation("):text.index("\n\nint main(")]
        self.assertEqual(hashlib.sha256(fn.encode()).hexdigest(), metadata["function_sha256"])
        self.assertIn("Copyright (C) 2009-2012 by George Williams", text)
        self.assertIn("Redistribution and use in source and binary forms", text)

    def test_shapes_against_unmodified_compiled_weighting(self):
        cases = [[], rectangle(), QUADRATIC, CUBIC,
                 rectangle(height=20) + rectangle(y=80, width=30, height=20),
                 [{"op": "move_to", "x": 10, "y": 0},
                  {"op": "line_to", "x": 130, "y": 120}],
                 rectangle(y=200, height=30)]
        for subdivisions in (100, 200):
            envelopes = [e.analyze(c, 1000, subdivisions) for c in cases]
            for a in envelopes:
                for b in envelopes:
                    with self.subTest(subdivisions=subdivisions, a=a.bounds, b=b.bounds):
                        actual = e.separation(a, b, 1000)
                        self.assertEqual(actual.estimate or 0, self.reference(a, b, 1000))

    def test_random_edge_arrays_and_rounding_against_compiled_weighting(self):
        randomizer = random.Random(18345)
        for case in range(80):
            bands_a = tuple(e.Band(i, randomizer.randrange(100), -randomizer.randrange(100))
                            for i in range(12))
            bands_b = tuple(e.Band(i, None, None) if randomizer.randrange(4) == 0 else
                            e.Band(i, randomizer.randrange(100), -randomizer.randrange(100))
                            for i in range(12))
            a = e.Envelope(e.Bounds(0, 0, 200, 110), 10, 0, 11, bands_a, 1000, 100)
            b = e.Envelope(e.Bounds(0, 0, 200, 110), 10, 0, 11, bands_b, 1000, 100)
            with self.subTest(case=case):
                self.assertEqual(e.separation(a, b, 1000).estimate,
                                 self.reference(a, b, 1000))


if __name__ == "__main__":
    unittest.main()
