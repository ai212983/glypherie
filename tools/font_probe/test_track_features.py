import unittest

import freetype as ft
from shapely.geometry import box

from analyze_features import ROOT, detect
from outline_experiment import render
from track_features import predict, snapshot, match_features, pocket, bitmap_shape, survival


class TrackingTests(unittest.TestCase):
    def test_segment_prediction_tracks_translation(self):
        source=[[(0,0),(3,0),(3,3),(0,3)]]
        target=[[(x+0.4,y-0.7) for x,y in source[0]]]
        error,p= predict((1.5,0),source,target)
        self.assertEqual(error,0)
        self.assertAlmostEqual(p[0],1.9)
        self.assertAlmostEqual(p[1],-0.7)

    def test_topology_mismatch_is_explicit(self):
        with self.assertRaises(ValueError):
            predict((0,0),[[(0,0),(1,0),(0,1)]],[[(0,0),(1,0)]])

    def test_void_metric_distinguishes_filled_partial_and_preserved(self):
        region=box(0,0,1,1)
        self.assertEqual(survival(region,region),0)
        self.assertEqual(survival(region,box(0,0,0.5,1)),0.5)
        self.assertEqual(survival(region,box(2,2,3,3)),1)

    def test_reviewed_upper_joins_survive_hinting_but_close_in_bitmap(self):
        face=ft.Face(str(ROOT/'tools/font_probe/fonts/Roboto.ttf'))
        face.set_var_design_coords([400,100]);face.set_pixel_sizes(0,16)
        for char in 'bhd':
            with self.subTest(char=char):
                source=snapshot(face,char,ft.FT_LOAD_NO_HINTING)
                hinted=snapshot(face,char,ft.FT_LOAD_TARGET_MONO)
                features=detect(source['boundary'])
                upper=min(features,key=lambda f:f['point'][1])
                match=match_features([upper],source,hinted)[0]
                self.assertIsNotNone(match['feature'])
                region=pocket(match['feature'],hinted['boundary'])
                self.assertGreater(region.area,0.1)
                self.assertLess(survival(region,bitmap_shape(render(face,char,0,0))),0.05)

    def test_matching_does_not_assume_a_disappeared_feature_survives(self):
        shape=[[(0,0),(3,0),(3,1),(1,1),(1,3),(0,3)]]
        convex=[[(0,0),(3,0),(3,1),(3,2),(3,3),(0,3)]]
        src=dict(raw=shape,boundary=shape,tags=[1]*6,ends=[5])
        dst=dict(raw=convex,boundary=convex,tags=[1]*6,ends=[5])
        match=match_features(detect(shape),src,dst)[0]
        self.assertIsNone(match['feature'])


if __name__=='__main__':unittest.main()
