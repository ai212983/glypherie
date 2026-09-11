"""Source-defined epsilon-coordinate classification, separate from matching angles."""
import unittest
import numpy as np

from shamir_geometry import prepare
from shamir_features import recognize,side_is_cardinal


def polygon(points):
    return [[a,b] for a,b in zip(points,points[1:]+points[:1])]


class CardinalGeometryTests(unittest.TestCase):
    def recognized(self,points,baseline=True):
        return recognize(prepare([polygon(points)],1000,baseline=baseline))['features']

    def test_long_slight_slant_is_not_a_stem_in_either_winding(self):
        points=[(0,0),(10,1000),(110,1000),(100,0)]
        for outline in (points,list(reversed(points))):
            with self.subTest(winding=outline):
                features=self.recognized(outline)
                self.assertTrue(any(f['kind']=='slant' for f in features))
                self.assertFalse(any(f['kind']=='stem' for f in features))
        self.assertTrue(any(f['kind']=='stem' for f in self.recognized(points,baseline=False)))

    def test_short_side_within_coordinate_epsilon_is_cardinal(self):
        points=[(0,0),(2,40),(102,40),(100,0)]
        for transform in (lambda p:p,lambda p:p[:,::-1]):
            outline=transform(np.asarray(points)).tolist()
            kind='stem' if outline==np.asarray(points).tolist() else 'bar'
            for winding in (outline,list(reversed(outline))):
                self.assertTrue(any(f['kind']==kind for f in self.recognized(winding)))

    def test_both_sides_must_satisfy_coordinate_epsilon(self):
        points=[(0,0),(0,1000),(110,1000),(100,0)]
        for outline in (points,list(reversed(points))):
            features=self.recognized(outline)
            self.assertFalse(any(f['kind']=='stem' for f in features))
            self.assertTrue(any(f['kind']=='slant' for f in features))

    def test_curve_uses_actual_bounds_instead_of_endpoints_or_control_box(self):
        def check(control,eps):
            model=dict(segments=[dict(control=control)],tolerances=dict(distance=eps))
            return side_is_cardinal(model,dict(segments=[0]),0)
        # Both endpoints have x=0, but the curve reaches x=2.
        self.assertFalse(check([[0,0],[4,50],[0,100]],1.5))
        # The control point lies outside the geometric box; x=2 is below 3.
        self.assertTrue(check([[0,0],[4,50],[0,100]],3))
        self.assertFalse(check([[0,0],[4,50],[0,100]],2))
        self.assertTrue(check([[0,0],[2,100]],2))

    def test_full_broken_side_extent_is_checked(self):
        model=dict(segments=[dict(control=[[0,0],[2,100]]),dict(control=[[2,200],[4,300]])],
                   tolerances=dict(distance=3))
        self.assertFalse(side_is_cardinal(model,dict(segments=[0,1]),0))

    def test_displaced_curve_extrema_measure_the_constraint_projection(self):
        contours=[[[[0,0],[50,400],[100,0]],[[100,0],[0,0]]],
                  [[[95,50],[60,250],[25,50]],[[25,50],[95,50]]]]
        for swap in (False,True):
            loops=[[(np.asarray(c)[:,::-1] if swap else np.asarray(c)).tolist()
                    for c in loop] for loop in contours]
            kind='bow' if swap else 'arc'
            for baseline in (True,False):
                with self.subTest(swap=swap,baseline=baseline):
                    features=recognize(prepare(loops,1000,baseline=baseline))['features']
                    feature=next(f for f in features if f['kind']==kind)
                    self.assertAlmostEqual(feature['width'],50 if baseline else np.hypot(50,10))

    def test_bent_straight_run_uses_actual_boundary_and_keeps_its_knot(self):
        points=[(0,0),(1,500),(0,1000),(100,1000),(100,0)]
        for outline in (points,list(reversed(points))):
            with self.subTest(winding=outline):
                result=recognize(prepare([polygon(outline)],1000,baseline=True))
                stem=next(f for f in result['features'] if f['kind']=='stem')
                self.assertAlmostEqual(stem['width'],99.)
                self.assertAlmostEqual(stem['length'],1000.)
                self.assertEqual(stem['support_intervals'],[[0.,1000.]] if stem['support_direction'][1]>0 else [[-1000.,0.]])

    def test_prepared_slanted_curve_uses_actual_projected_extent(self):
        # At 45 degrees both coordinate derivatives keep their signs, so
        # prepare's x/y-extrema split cannot remove the chord-normal extremum.
        rotation=np.array([[1,-1],[1,1]])/np.sqrt(2)
        loop=[[[0,0],[4.5,5],[0,10]],[[0,10],[20,10]],
              [[20,10],[20,0]],[[20,0],[0,0]]]
        loop=[(np.asarray(c)@rotation.T).tolist() for c in loop]
        model=prepare([loop],1000,baseline=True)
        self.assertEqual(model['segments'][0]['t_range'],[0.,1.])
        self.assertEqual(len(model['segments'][0]['control']),3)
        # Epsilon3: control polygon excursion4.5, actual curve excursion2.25.
        self.assertTrue(any(0 in s['segments'] for s in recognize(model)['sides']))
        experimental=dict(model,baseline=False)
        self.assertFalse(any(0 in s['segments'] for s in recognize(experimental)['sides']))


if __name__=='__main__':unittest.main()
