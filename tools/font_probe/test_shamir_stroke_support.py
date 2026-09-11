"""Stroke length is paired boundary support, independent of side extents."""
import unittest
import numpy as np

from shamir_features import recognize
from shamir_geometry import prepare
from shamir_model import feature_model
from test_shamir_features import polygon


class StrokeSupportTests(unittest.TestCase):
    def test_staggered_subdivision_keeps_identical_support(self):
        simple=[(0,0),(100,0),(100,1000),(0,1000)]
        divided=[(0,0),(100,0)]+[(100,y) for y in range(4,1000,4)]+[(100,1000),(0,1000)]+[(0,y) for y in range(998,0,-4)]
        signatures=[]
        for outline in (simple,divided):
            found=recognize(prepare([polygon(outline)],1000))
            signatures.append(sorted((f['kind'],round(f['width'],6),round(f['length'],6))
                                     for f in found['features'] if 'length' in f))
        self.assertEqual(signatures[0],signatures[1])
        self.assertIn(('stem',100.,1000.),signatures[1])

    def test_offset_sides_measure_their_common_interval(self):
        outline=[(0,0),(100,500),(100,1500),(0,1000)]
        found=recognize(prepare([polygon(outline)],1000))
        stem=next(f for f in found['features'] if f['kind']=='stem')
        self.assertAlmostEqual(stem['length'],500)
        self.assertAlmostEqual(sum(b-a for a,b in stem['support_intervals']),500)
        # Both individual sides are 1000 units long, but only half overlaps.
        for sid in stem['sides']:
            side=found['sides'][sid]
            self.assertAlmostEqual(np.linalg.norm(np.array(side['b'])-side['a']),1000)

    def test_broken_support_excludes_the_gap(self):
        rectangle=np.array([(0,0),(100,0),(100,200),(0,200)])
        found=recognize(prepare([polygon(rectangle),polygon(rectangle+[0,400])],1000))
        stem=next(f for f in found['features'] if f['kind']=='stem')
        self.assertAlmostEqual(stem['length'],400)
        self.assertEqual(len(stem['support_intervals']),2)
        self.assertAlmostEqual(stem['support_intervals'][-1][1]-stem['support_intervals'][0][0],600)

    def test_interval_union_preserves_gap_below_feature_tolerance(self):
        rectangle=np.array([(0,0),(100,0),(100,200),(0,200)])
        found=recognize(prepare([polygon(rectangle),polygon(rectangle+[0,201])],1000))
        stem=next(f for f in found['features'] if f['kind']=='stem')
        self.assertEqual(len(stem['support_intervals']),2)
        self.assertAlmostEqual(stem['length'],400)
        self.assertAlmostEqual(stem['support_intervals'][-1][1]-stem['support_intervals'][0][0],401)

    def test_ladder_uses_pair_length_instead_of_each_side_length(self):
        outlines=[[(0,0),(100,500),(100,1500),(0,1000)],
                  [(200,0),(300,0),(300,1000),(200,1000)],
                  [(400,0),(500,0),(500,1000),(400,1000)]]
        model=feature_model(prepare([polygon(p) for p in outlines],1000))
        stems=[f for f in model['features'] if f['kind']=='stem']
        self.assertEqual(sorted(f['length'] for f in stems),[500,1000,1000])
        self.assertFalse(any(f['kind']=='ladder-x' for f in model['features']))

    def test_equal_regular_strokes_retain_ladder(self):
        rectangle=np.array([(0,0),(100,0),(100,700),(0,700)])
        model=feature_model(prepare([polygon(rectangle+[x,0]) for x in (0,200,400)],1000))
        self.assertEqual([f['length'] for f in model['features'] if f['kind']=='stem'],[700]*3)
        self.assertEqual(sum(f['kind']=='ladder-x' for f in model['features']),2)


if __name__=='__main__':unittest.main()
