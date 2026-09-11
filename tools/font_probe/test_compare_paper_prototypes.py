"""Guard physical placement and review-sheet clipping."""
import unittest
from compare_paper_prototypes import pixels, check_bounds


class ReviewGeometryTests(unittest.TestCase):
    def test_bitmap_padding_does_not_change_physical_pixels(self):
        a = dict(left=-1, top=-2, width=2, height=2, pixels=[1, 0, 0, 1])
        b = dict(left=-2, top=-2, width=3, height=2, pixels=[0, 1, 0, 0, 0, 1])
        self.assertEqual(pixels(a), pixels(b))
        self.assertEqual(pixels(a), {(-1, -2), (0, -1)})

    def test_descender_requires_full_scaled_cell(self):
        glyph = dict(left=0, top=3, width=1, height=1, pixels=[1])
        with self.assertRaises(ValueError):
            check_bounds(glyph, 10, 100, 7, (0, 0, 30, 124))
        check_bounds(glyph, 10, 100, 7, (0, 0, 30, 128))

    def test_negative_bearing_is_not_recentered(self):
        glyph = dict(left=-1, top=-1, width=1, height=1, pixels=[1])
        with self.assertRaises(ValueError):
            check_bounds(glyph, 0, 10, 7, (0, 0, 20, 20))


if __name__ == '__main__':
    unittest.main()
