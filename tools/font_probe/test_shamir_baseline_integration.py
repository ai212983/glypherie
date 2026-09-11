import unittest
import numpy as np
from shamir_model import constraints_for,build_font


class BaselineIntegrationTests(unittest.TestCase):
    def test_phantom_can_link_without_voting(self):
        model=dict(points=np.array([[0.,100.]]),extrema={},features=[],groups=[
            dict(rep=0,members={0},normal=[0.,1.],height_lookup='-max')])
        tables={'height-flat-max':[101.], 'height-round-min':[100.]}
        cs,_,_=constraints_for(model,tables,1000,baseline=True)
        self.assertEqual(cs[0]['kind'],'PAbs')
        self.assertEqual(cs[0]['value'],101.)
        self.assertNotIn('height_kind',model['groups'][0])
        old,_,_=constraints_for(model,tables,1000)
        self.assertEqual(old[0]['kind'],'Abs')

    def test_baseline_overrides_rejected_before_loading_font(self):
        for override in ({'scheduler':'point'},{'normalize':False},{'templates':{}}):
            with self.assertRaises(ValueError):
                build_font('unused','unused','a',profile='baseline',ppem=14,**override)
        with self.assertRaises(ValueError):build_font('unused','unused','a',profile='baseline')

    def test_short_ladders_use_unique_adjacent_pairs(self):
        from shamir_geometry import prepare
        from shamir_model import feature_model
        def ladder(heights):
            contours=[]
            for i,h in enumerate(heights):
                x=i*20;points=[(x,0),(x+10,0),(x+10,h),(x,h)]
                contours.append([[a,b] for a,b in zip(points,points[1:]+points[:1])])
            m=feature_model(prepare(contours,100,baseline=True),baseline=True)
            return [f for f in m['features'] if f['kind']=='ladder-x']
        for heights,count in (([15]*3,2),([15]*4,3),([15,15.2,15],2),([15,15.4,15],0)):
            with self.subTest(heights=heights):
                features=ladder(heights)
                self.assertEqual(len(features),count)
                self.assertEqual(len({tuple(f['groups']) for f in features}),count)
