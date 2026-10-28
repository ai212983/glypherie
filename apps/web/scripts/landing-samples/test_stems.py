from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from PIL import Image
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen

from generate import ROOT, prepare_font
from stems import calibrate, native_widths, source_widths


class StemCalibrationChecks(unittest.TestCase):
    def source_sections(self, contours, y=75):
        class Glyph:
            def draw(self, pen):
                for contour in contours:
                    contour.replay(pen)

        class Font:
            def getGlyphSet(self, location):
                return {ch: Glyph() for ch in 'HIl'}

            def getBestCmap(self):
                return {ord(ch): ch for ch in 'HIl'}

            def __getitem__(self, table):
                return SimpleNamespace(sCapHeight=y / (3 / 4), unitsPerEm=1000)

        return source_widths(Font(), {}, 10)

    def rectangle(self, left, right, reverse=False):
        points = [(left, 0), (right, 0), (right, 100), (left, 100)]
        if reverse:
            points.reverse()
        pen = RecordingPen()
        pen.moveTo(points[0])
        for point in points[1:]:
            pen.lineTo(point)
        pen.closePath()
        return pen

    def test_same_winding_overlaps_measure_the_filled_union(self):
        widths = self.source_sections([self.rectangle(0, 60), self.rectangle(40, 100)])
        self.assertEqual(widths, [1] * 9)

    def test_nested_contours_preserve_nonzero_fill_and_opposite_winding_counters(self):
        for reverse in [False, True]:
            with self.subTest(reverse=reverse):
                outer = self.rectangle(0, 100, reverse=reverse)
                self.assertEqual(self.source_sections([outer, self.rectangle(20, 80, reverse=reverse)]), [1] * 9)
                widths = self.source_sections([outer, self.rectangle(20, 80, reverse=not reverse)])
                self.assertEqual(widths, [.2, .2] * 9)

    def test_touching_contours_form_one_stem(self):
        self.assertEqual(self.source_sections([self.rectangle(0, 40), self.rectangle(40, 100)]), [1] * 9)

    def test_opposite_identical_contours_have_no_filled_section(self):
        with self.assertRaisesRegex(ValueError, 'Cannot measure source stem sections'):
            self.source_sections([self.rectangle(0, 100), self.rectangle(0, 100, reverse=True)])

    def test_curve_endpoints_do_not_drop_a_shared_downward_crossing(self):
        for cubic in [False, True]:
            with self.subTest(cubic=cubic):
                contour = RecordingPen()
                contour.moveTo((0, 0))
                contour.lineTo((0, 100))
                contour.lineTo((100, 100))
                if cubic:
                    contour.curveTo((100, 95), (100, 85), (100, 75))
                else:
                    contour.qCurveTo((100, 90), (100, 75))
                contour.lineTo((100, 0))
                contour.closePath()
                self.assertEqual(self.source_sections([contour]), [1] * 9)

    def test_quadratic_tangency_does_not_split_a_filled_stem(self):
        from math import sqrt
        contour = RecordingPen()
        contour.moveTo((0, 0))
        contour.lineTo((100, 0))
        contour.lineTo((100, 100))
        contour.qCurveTo((50, 50), (0, 100))
        contour.closePath()
        side_width = (1 - 1 / sqrt(3)) / 2
        expected = [1, 1, side_width, side_width] * 3
        measured = self.source_sections([contour])
        self.assertEqual(len(measured), len(expected))
        for actual, wanted in zip(measured, expected, strict=True):
            self.assertAlmostEqual(actual, wanted)

    def test_curved_overlaps_measure_the_filled_union(self):
        for cubic in [False, True]:
            with self.subTest(cubic=cubic):
                contours = []
                for offset in [0, 40]:
                    pen = RecordingPen()
                    pen.moveTo((offset, 0))
                    pen.lineTo((offset + 100, 0))
                    if cubic:
                        pen.curveTo((offset + 120, 32), (offset + 120, 64), (offset + 100, 96))
                    else:
                        pen.qCurveTo((offset + 130, 48), (offset + 100, 96))
                    pen.lineTo((offset, 96))
                    pen.closePath()
                    contours.append(pen)
                expected = [(140 + 60 * t * (1 - t)) / 100 for t in (100 * f / 96 for f in (2 / 3, 3 / 4, 5 / 6))] * 3
                measured = self.source_sections(contours)
                self.assertEqual(len(measured), len(expected))
                for actual, wanted in zip(measured, expected, strict=True):
                    self.assertAlmostEqual(actual, wanted)

    def test_cubic_tangency_does_not_split_a_filled_stem(self):
        from math import sqrt
        contour = RecordingPen()
        contour.moveTo((0, 0))
        contour.lineTo((100, 0))
        contour.lineTo((100, 100))
        contour.curveTo((200 / 3, 68), (100 / 3, 68), (0, 100))
        contour.closePath()
        upper_y = 76 / (3 / 4) * (5 / 6)
        side_width = (1 - sqrt((upper_y - 76) / 24)) / 2
        expected = [1, 1, side_width, side_width] * 3
        measured = self.source_sections([contour], y=76)
        self.assertEqual(len(measured), len(expected))
        for actual, wanted in zip(measured, expected, strict=True):
            self.assertAlmostEqual(actual, wanted)

    def test_calibration_bounds_the_real_static_outline_after_coordinate_rounding(self):
        source = ROOT / 'fonts/Roboto.ttf'
        original = source.read_bytes()
        axes, evidence = calibrate(source, {'wdth': 100}, 12, 1)
        self.assertLessEqual(evidence['maximum_source_width_px'], 1)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'input.ttf'
            prepare_font(source, axes, destination)
            with TTFont(destination) as font:
                self.assertLessEqual(max(source_widths(font, {}, 12)), 1)
        self.assertEqual(source.read_bytes(), original)

    def test_native_width_measurement_is_independent_of_exporter_baseline_translation(self):
        h = Image.new('L', (5, 6))
        for y in range(6):
            h.putpixel((0, y), 255)
            h.putpixel((4, y), 255)
        stem = Image.new('L', (1, 6), 255)
        reference = {'H': (h, 5, 0, -6), 'I': (stem, 2, 0, -6), 'l': (stem, 2, 0, -6)}
        shifted = {ch: (im, advance, left, top + 3) for ch, (im, advance, left, top) in reference.items()}
        evidence = {'cap_height_px': 6}
        self.assertEqual(native_widths(reference, evidence), native_widths(shifted, evidence))
        for result in native_widths(reference, evidence).values():
            self.assertEqual(set(result['run_width_counts_px']), {1})
            self.assertFalse(result['rows_without_ink'])

    def test_calibration_refuses_conflicting_explicit_weight(self):
        with self.assertRaisesRegex(ValueError, 'without an explicit wght'):
            calibrate(ROOT / 'fonts/Roboto.ttf', {'wght': 400}, 16, 1)


if __name__ == '__main__':
    unittest.main()
