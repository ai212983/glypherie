"""Independent native FontForge envelope and pair-estimator parity.

Build reference/build-native.py first. Missing binaries skip this optional suite
unless CONTEXTUAL_SPACING_REQUIRE_NATIVE=1, in which case absence is an error.
The native driver receives original curve commands, constructs native splines,
and calls pinned aw2_findedges and aw2_bbox_separation; it never receives Python
envelopes. This finite synthetic matrix establishes mechanical parity only.
"""

from dataclasses import asdict
import os
from pathlib import Path
import sys
import unittest

EXPERIMENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXPERIMENT))
import estimator as e
from reference.native_capture import NATIVE, capture


def polygon(points):
    return [dict(op="move_to" if i == 0 else "line_to", x=x, y=y)
            for i, (x, y) in enumerate(points)] + [dict(op="close")]


def rectangle(x=0, y=0, width=100, height=100):
    return polygon([(x, y), (x + width, y), (x + width, y + height), (x, y + height)])


def translated(commands, dx, dy):
    return [{key: value + (dx if key.startswith("x") else dy)
             if key in ("x", "x1", "x2", "y", "y1", "y2") else value
             for key, value in command.items()} for command in commands]


QUADRATIC = [dict(op="move_to", x=0, y=0),
             dict(op="quad_to", x1=200, y1=50, x=0, y=100), dict(op="close")]
CUBIC = [dict(op="move_to", x=0, y=0),
         dict(op="curve_to", x1=300, y1=100, x2=300, y2=200, x=0, y=300),
         dict(op="close")]
CASES = {
    "rectangle": rectangle(),
    "negative_coordinates": rectangle(-120, -20, 40, 70),
    "wedge": polygon([(0, 0), (120, 50), (0, 100)]),
    "open_cavity": polygon([(0, 0), (120, 0), (120, 20), (20, 20),
                            (20, 80), (120, 80), (120, 100), (0, 100)]),
    "quadratic_x_extremum": QUADRATIC,
    "quadratic_y_extremum": [dict(op="move_to", x=0, y=0),
                             dict(op="quad_to", x1=50, y1=200, x=100, y=0),
                             dict(op="close")],
    "cubic_x_extremum": CUBIC,
    "cubic_y_extremum": [dict(op="move_to", x=0, y=0),
                         dict(op="curve_to", x1=0, y1=300,
                              x2=100, y2=300, x=100, y=0), dict(op="close")],
    "disconnected_marks": rectangle(height=20) + rectangle(y=80, width=30, height=20),
    "boundary_touch": rectangle(y=100, height=20),
    "no_y_overlap": rectangle(y=500, height=30),
    "horizontal_only": rectangle(height=0),
    "translated_quadratic": translated(QUADRATIC, -23, 20),
    "translated_cubic": translated(CUBIC, 113, -20),
}


class NativeEnvelopeParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not NATIVE.is_file():
            message = "native parity binary missing; run reference/build-native.py"
            if os.environ.get("CONTEXTUAL_SPACING_REQUIRE_NATIVE") == "1":
                raise RuntimeError(message)
            raise unittest.SkipTest(message)

    def assert_native_matrix(self, em_size, subdivisions):
        names = list(CASES)
        native = capture(list(CASES.values()), em_size=em_size, subdivisions=subdivisions)
        self.assertEqual(native["band_height"], em_size // subdivisions)
        envelopes = [e.analyze(commands, em_size, subdivisions) for commands in CASES.values()]
        for name, envelope, reference in zip(names, envelopes, native["glyphs"]):
            with self.subTest(em=em_size, subdivisions=subdivisions, glyph=name):
                self.assertEqual(asdict(envelope.bounds), reference["bounds"])
                self.assertEqual(envelope.imin_y, reference["imin_y"])
                self.assertEqual(envelope.imax_y, reference["imax_y"])
                bands = [dict(index=band.index,
                              left=32767 if band.left is None else band.left,
                              right=-32767 if band.right is None else band.right)
                         for band in envelope.bands]
                self.assertEqual(bands, reference["bands"])
        for i, left in enumerate(envelopes):
            for j, right in enumerate(envelopes):
                with self.subTest(em=em_size, subdivisions=subdivisions,
                                  left=names[i], right=names[j]):
                    actual = e.separation(left, right, em_size)
                    # Explicit adapter abstention replaces native's zero result
                    # when there are no usable bands; retain that distinction.
                    expected = native["pair_estimates"][i][j]
                    self.assertEqual(0 if actual.estimate is None else actual.estimate, expected)
                    if actual.estimate is None:
                        self.assertEqual(actual.reason, "no_shared_bands")

    def test_auto_width_default_bands(self):
        self.assert_native_matrix(1000, 100)

    def test_native_pair_bands(self):
        self.assert_native_matrix(1000, 200)

    def test_2048_integer_auto_width_bands(self):
        self.assert_native_matrix(2048, 100)

    def test_2048_integer_native_pair_bands(self):
        self.assert_native_matrix(2048, 200)

    def test_empty_geometry_abstention(self):
        # Native reports a zero bbox for empty contours; the adapter preserves
        # its explicit absence identity and still abstains from optical use.
        native = capture([[], rectangle()])
        empty = e.analyze([], 1000)
        self.assertIsNone(empty.bounds)
        self.assertEqual(native["pair_estimates"][0], [0, 0])
        self.assertEqual(e.separation(empty, e.analyze(rectangle(), 1000), 1000).reason,
                         "no_shared_bands")


if __name__ == "__main__":
    unittest.main()
