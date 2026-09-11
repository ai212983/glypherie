"""Outline anchors and native tangent preservation around curved extrema."""
import tempfile
import unittest
from pathlib import Path

import freetype as ft

from shamir_geometry import prepare
from shamir_model import build_font,feature_model


class RepresentativeTests(unittest.TestCase):
    def test_curved_extremum_anchors_on_outline_and_keeps_tangent_controls(self):
        geometry=prepare([[
            [(0,0),(100,0)],
            [(100,0),(90,200),(50,200)],
            [(50,200),(10,200),(0,0)],
        ]],1000)
        model=feature_model(geometry)
        groups=[g for g in model['groups'] if g['members']]
        self.assertTrue(any(not model['glyph'].flags[p]&1
                            for g in groups for p in g['members']))
        for group in groups:
            self.assertTrue(model['glyph'].flags[group['rep']]&1)

    def test_native_extremum_tangents_remain_aligned(self):
        from compare_shamir_pipeline import CHARS
        sources=Path(__file__).parent/'out/shamir-controlled'
        cases=[('roboto',18,'t',1,[8,9,10]),
               ('roboto',20,'t',1,[8,9,10]),
               ('literata',16,'e',0,[17,18,19])]
        if not all((sources/f'{family}-{size}-source.ttf').exists()
                   for family,size,*_ in cases):
            self.skipTest('local calibration source fonts unavailable')
        with tempfile.TemporaryDirectory() as temporary:
            for family,size,char,axis,members in cases:
                with self.subTest(font=family,size=size,char=char):
                    target=Path(temporary)/f'{family}-{size}.ttf'
                    build_font(sources/f'{family}-{size}-source.ttf',target,CHARS)
                    face=ft.Face(str(target));face.set_pixel_sizes(0,size)
                    face.load_char(char,ft.FT_LOAD_NO_BITMAP|ft.FT_LOAD_NO_AUTOHINT|
                                   ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_PEDANTIC)
                    coordinates=[face.glyph.outline.points[p][axis] for p in members]
                    # Native vector quantization can leave one 26.6 unit; the
                    # former control anchors separated these tangents by ~1px.
                    self.assertLessEqual(max(coordinates)-min(coordinates),1)


if __name__=='__main__':unittest.main()
