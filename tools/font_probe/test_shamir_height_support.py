"""Shared heights require segment support; local extrema remain anchored."""
import tempfile
import unittest
from pathlib import Path

import freetype as ft
import numpy as np

from shamir_geometry import prepare
from shamir_model import feature_model,constraints_for,build_font
from shamir_segment_fit import clusters
from test_shamir_features import polygon


class HeightSupportTests(unittest.TestCase):
    def test_sharp_junction_does_not_borrow_flat_height_votes(self):
        # A concave V at height 500 has no horizontal segment at its tip.
        outline=[(0,0),(300,0),(300,800),(200,500),(100,800),(0,800)]
        for points in (outline,outline[::-1]):
            model=feature_model(prepare([polygon(points)],1000))
            p=next(i for i,p in enumerate(model['points']) if list(p)==[200,500])
            group=next(g for g in model['groups'] if p in g['members'] and g['normal']==[0.,1.])
            self.assertNotIn('height_kind',group)
            candidates,_,_=constraints_for(model,{'height-flat-min':[500.]},1000)
            anchor=next(c for c in candidates if c['point']==p and c['normal']==[0.,1.])
            self.assertEqual(anchor['kind'],'Abs')
            self.assertEqual(anchor['value'],500.)

    def test_horizontal_caps_supply_recurring_heights(self):
        model=feature_model(prepare([polygon([(0,0),(100,0),(100,700),(0,700)])],1000))
        samples=[(g['height_kind'],float(model['points'][g['rep'],1]),char)
                 for char in 'abc' for g in model['groups'] if g['members'] and 'height_kind' in g]
        tables=clusters(samples,1000)
        self.assertEqual(tables['height-flat-min'],[0.])
        self.assertEqual(tables['height-flat-max'],[700.])
        candidates,_,_=constraints_for(model,tables,1000)
        self.assertEqual({c['value'] for c in candidates if c['kind']=='PAbs'}, {0.,700.})

    def test_recognized_curved_boundaries_supply_round_heights(self):
        outer=[[[0,100],[0,200],[100,200]],[[100,200],[200,200],[200,100]],
               [[200,100],[200,0],[100,0]],[[100,0],[0,0],[0,100]]]
        inner=(np.array(outer)*.6+40).tolist()
        inner=[segment[::-1] for segment in inner[::-1]]
        model=feature_model(prepare([outer,inner],1000))
        self.assertTrue(any(f['kind']=='arc' for f in model['features']))
        heights={g['height_kind'] for g in model['groups'] if g['members'] and 'height_kind' in g}
        self.assertEqual(heights,{'height-round-min','height-round-max'})

    def test_native_junction_retains_vertical_stem_alignment(self):
        from compare_shamir_pipeline import CHARS
        source=Path(__file__).parent/'out/shamir-controlled/roboto-16-source.ttf'
        if not source.exists():self.skipTest('local calibration source font unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'height.ttf';report=build_font(source,output,CHARS)
            face=ft.Face(str(output));face.set_pixel_sizes(0,16)
            face.load_char('K',ft.FT_LOAD_NO_BITMAP|ft.FT_LOAD_NO_AUTOHINT|
                           ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_PEDANTIC)
            points=face.glyph.outline.points
            self.assertEqual(len({points[i][0] for i in (0,1,9,10)}),1)
            constraints=report['records']['K']['graph']['constraints']
            self.assertTrue(any(c['point']==1 and c.get('feature')=='align-0' for c in constraints))


if __name__=='__main__':unittest.main()
