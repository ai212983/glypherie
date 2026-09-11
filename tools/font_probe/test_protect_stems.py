import unittest
import freetype as ft

from analyze_features import ROOT,visible_boundary
from outline_experiment import render
from track_features import snapshot
from protect_stems import stem_regions,protected_pixels


class StemProtectionTests(unittest.TestCase):
    def test_solid_parallel_strip_is_protected(self):
        raw=[[(0,0),(2,0),(2,8),(0,8)]]
        region=stem_regions(raw,visible_boundary(raw),16)
        self.assertAlmostEqual(region.area,16)

    def test_counter_is_not_a_stem(self):
        raw=[[(0,0),(6,0),(6,10),(0,10)],[(2,2),(2,8),(4,8),(4,2)]]
        region=stem_regions(raw,visible_boundary(raw),16)
        from shapely.geometry import Point
        self.assertFalse(region.contains(Point(3,5)))

    def test_rejected_d_cut_is_protected(self):
        face=ft.Face(str(ROOT/'tools/font_probe/fonts/Roboto.ttf'))
        face.set_var_design_coords([400,100]);face.set_pixel_sizes(0,16)
        grown=snapshot(face,'d',ft.FT_LOAD_TARGET_MONO,True)
        glyph=render(face,'d',24,8)
        protected=protected_pixels(glyph,stem_regions(grown['raw'],grown['boundary'],16))
        for x,y in ((6,-10),(6,-9)):
            self.assertIn((y-glyph['top'])*glyph['width']+x-glyph['left'],protected)


if __name__=='__main__':unittest.main()
