import unittest
from offset_experiment import average,asymmetric
from shapely.geometry import box


class OffsetTests(unittest.TestCase):
    def test_threshold_applies_after_coverage_average(self):
        g=average([{(0,0):255},{(0,0):0},{(0,0):128}])
        self.assertAlmostEqual(g['coverage'][0],383/3)
        self.assertEqual(g['pixels'],[0])

    def test_masks_align_on_absolute_pixel_coordinates(self):
        g=average([{(-1,0):255,(0,0):255},{(0,0):255,(1,0):255}])
        self.assertEqual((g['left'],g['width']),(-1,3))
        self.assertEqual(g['pixels'],[0,1,0])

    def test_reflection_uses_shape_center_not_origin(self):
        self.assertEqual(asymmetric(box(7,9,10,15)),dict(left_right=0,top_bottom=0,rotation_180=0))


if __name__=='__main__':unittest.main()
