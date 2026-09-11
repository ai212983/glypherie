"""Geometry and feature invariants independent of calibration letter names."""
import unittest
import numpy as np
from shamir_geometry import prepare,at,OutlinePen
from shamir_features import recognize


def polygon(points):return [[points[i],points[(i+1)%len(points)]] for i in range(len(points))]


class RecognitionTests(unittest.TestCase):
    def test_broken_sides_keep_gaps_out_of_support(self):
        lower=np.array([[0,0],[100,0],[100,200],[0,200]],float)
        m=prepare([polygon(lower),polygon(lower+[0,400]),polygon(lower+[50,200])],1000)
        found=recognize(m)
        self.assertTrue(any(len(s['segments'])>1 for s in found['sides']))
        # A disjoint parallel feature can share a line without filling its gap.
        self.assertFalse(any(abs(f['width']-50)<1e-6 for f in found['features']))

    def test_analytic_inside_on_curve_extremum_scanline(self):
        from shamir_features import Interior
        m=prepare([[[[0,50],[0,100],[50,100]],[[50,100],[100,100],[100,50]],
                    [[100,50],[100,0],[50,0]],[[50,0],[0,0],[0,50]]]],1000)
        interior=Interior(m)
        self.assertTrue(interior.contains(np.array([50,50])))
        self.assertFalse(interior.contains(np.array([-1,50])))
        self.assertFalse(interior.contains(np.array([50,100])))

    def test_inflection_at_quadratic_join(self):
        model=prepare([[[[-100,-100],[-50,0],[0,0]],[[0,0],[50,0],[100,100]],
                        [[100,100],[-100,-100]]]],1000)
        point=next(p for p in model['points'] if p['position']==[0.,0.])
        self.assertIn('I',point['categories'])

    def test_components_and_implicit_quadratic_points(self):
        class Component:
            def draw(self,pen):
                # An all-off-curve TrueType contour: BasePen inserts its on-curve midpoints.
                pen.qCurveTo((0,0),(100,0),(100,100),(0,100),None)
                pen.closePath()
        pen=OutlinePen({'dot':Component()})
        pen.addComponent('dot',(1,0,0,1,250,400))
        model=prepare(pen.contours,1000)
        positions=np.array([p['position'] for p in model['points']])
        self.assertEqual(len(model['contours']),1)
        np.testing.assert_allclose(positions.min(axis=0),[250,400])
        np.testing.assert_allclose(positions.max(axis=0),[350,500])
        self.assertTrue(all(s['kind']=='quadratic' for s in model['segments']))

    def test_extremum_subdivision_preserves_curve(self):
        original=[[0,0],[50,100],[100,0]]
        model=prepare([[original,[[100,0],[0,0]]]],1000)
        self.assertEqual(sum(p['inserted'] for p in model['points']),1)
        for segment in model['segments'][:2]:
            lo,hi=segment['t_range']
            for t in np.linspace(0,1,11):np.testing.assert_allclose(at(segment['control'],t),at(original,lo+t*(hi-lo)),atol=1e-10)
        top=next(p for p in model['points'] if p['inserted'])
        self.assertEqual(top['extrema']['1'],'max')

    def test_rotation_and_winding_keep_stroke_width(self):
        rectangle=np.array([[0,0],[100,0],[100,700],[0,700]],float)
        for angle in (0,.55):
            rot=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
            widths=[]
            for points in (rectangle,rectangle[::-1]):
                model=prepare([polygon(points@rot.T)],1000)
                widths.append(sorted(round(f['width'],6) for f in recognize(model)['features']))
            self.assertEqual(widths[0],widths[1]);self.assertIn(100,widths[0])
            if angle:self.assertTrue(any(f['kind']=='slant' for f in recognize(model)['features']))

    def test_white_space_is_not_a_stroke(self):
        rectangle=np.array([[0,0],[100,0],[100,700],[0,700]],float)
        model=prepare([polygon(rectangle),polygon(rectangle+[180,0])],1000)
        self.assertFalse(any(abs(f['width']-80)<1e-6 for f in recognize(model)['features']))

    def test_contiguous_segments_keep_membership(self):
        model=prepare([polygon([(0,0),(100,0),(100,350),(100,700),(0,700)])],1000)
        found=recognize(model)
        self.assertTrue(any(len(s['segments'])==2 for s in found['sides']))
        self.assertEqual(sum(f['kind']=='stem' for f in found['features']),1)


if __name__=='__main__':unittest.main()
