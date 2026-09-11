"""A physical segment keeps its identity and direction across features."""
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fontTools.ttLib import TTFont

from shamir_boundary import normalize_boundaries
from shamir_geometry import prepare,from_font,unit
from shamir_model import feature_model


def polygon(points):
    return [[a,b] for a,b in zip(points,points[1:]+points[:1])]


class SideIdentityTests(unittest.TestCase):
    def test_shared_side_uses_own_direction_independent_of_feature_order(self):
        contours=[polygon([(x,0),(x+rise,300),(x+rise+20,300)])
                  for x,rise in ((0,100),(200,105),(400,110))]
        geometry=prepare(contours,1000,baseline=True)
        sides=[dict(id=i,segments=[3*i],direction=unit(np.array([rise,300])).tolist())
               for i,rise in enumerate((100,105,110))]
        features=[dict(kind='slant',sides=pair,width=100.) for pair in ([0,2],[1,2])]
        for ordering in (features,list(reversed(features))):
            with self.subTest(order=ordering),patch('shamir_model.recognize',return_value=dict(sides=sides,features=ordering)):
                model=feature_model(geometry,baseline=True)
            shared=[(i,g) for i,g in enumerate(model['groups'])
                    if g['members'] and 2 in g.get('source_sides',[])]
            self.assertEqual(len(shared),1)
            group_id,group=shared[0]
            direction=np.asarray(sides[2]['direction'])
            self.assertAlmostEqual(float(direction@group['normal']),0.)
            slants=[f for f in model['features'] if f['kind']=='slant']
            self.assertEqual(len(slants),2)
            self.assertTrue(all(f['groups'][1]==group_id for f in slants))
            # Widths retain each feature's own projection; side alignment does
            # not silently replace the cross-stroke measurement direction.
            for feature,source in zip(slants,ordering):
                d=np.asarray(sides[source['sides'][0]]['direction'])
                np.testing.assert_allclose(feature['normal'],[-d[1],d[0]])

    def test_source_sans_v_shared_side_has_one_group(self):
        source=Path(__file__).parent/'out/shamir-controlled/source-sans-3-14-source.ttf'
        if not source.exists():self.skipTest('local calibration source font unavailable')
        font=TTFont(source);normalize_boundaries(font,'V')
        model=feature_model(from_font(font,'V',baseline=True),baseline=True)
        shared=[(i,g) for i,g in enumerate(model['groups']) if g['members']=={16,17}]
        self.assertEqual(len(shared),1)
        group_id,group=shared[0]
        self.assertIn(6,group['source_sides'])
        self.assertEqual(sum(group_id in f['groups'] for f in model['features'] if f['kind']=='slant'),2)
        a,b=model['points'][[16,17]]
        self.assertAlmostEqual(float((b-a)@group['normal']),0.)
        source_sides=[sid for g in model['groups'] if g['members'] for sid in g.get('source_sides',[])]
        self.assertEqual(len(source_sides),len(set(source_sides)))


if __name__=='__main__':unittest.main()
