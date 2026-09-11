"""Curve pairing and width links without calibration glyph identities."""
import unittest
import numpy as np
from shamir_geometry import prepare
from shamir_segment_fit import prepared_glyph
from curved_width_links import detect,fit
from curved_pair_support import pairs
from shamir_features import Interior


def oval(x0,y0,x1,y1):
    cx=(x0+x1)/2;cy=(y0+y1)/2
    return [[[x0,cy],[x0,y1],[cx,y1]],[[cx,y1],[x1,y1],[x1,cy]],
            [[x1,cy],[x1,y0],[cx,y0]],[[cx,y0],[x0,y0],[x0,cy]]]


def ring(reverse=False,start=0):
    contours=[oval(0,0,500,500),[s[::-1] for s in oval(100,100,400,440)[::-1]]]
    if reverse:contours=[[s[::-1] for s in c[::-1]] for c in contours]
    contours=[c[start:]+c[:start] for c in contours]
    m=prepare(contours,1000,baseline=True);m['scale']=.014
    return m


class CurvedWidthTests(unittest.TestCase):
    def test_displaced_extrema_are_recognized_in_both_windings_and_starts(self):
        for reverse in (False,True):
            for start in range(4):
                fs=[f for f in detect(ring(reverse,start)) if f['axis']==0]
                self.assertEqual(len(fs),2)
                self.assertTrue(all(f['new'] for f in fs))
                self.assertEqual(sorted(f['width'] for f in fs),[100,100])

    def test_counter_is_never_recognized_as_black_stroke(self):
        m=ring()
        for axis in (0,1):
            for a,b in pairs(m,axis,Interior(m)):
                self.assertNotEqual(a['contour'],b['contour'])

    def test_links_fix_opposing_widths_preserving_outer_and_other_axis(self):
        m=ring();g,mapping,_=prepared_glyph(m);q=np.asarray(g.coordinates)*m['scale']
        fs=[f for f in detect(m) if f['axis']==0]
        outers=[]
        for f in fs:
            a,b=f['points'];pa,pb=m['points'][a],m['points'][b]
            sign=1 if pa['extrema']['0']=='min' else -1
            if sign*(pa['position'][0]-pb['position'][0])>0:a,b=b,a
            outer,inner=mapping[a],mapping[b];outers.append(outer)
            q[inner,0]=q[outer,0]+sign*(2 if sign==1 else 1)
        result,audit=fit(m,q)
        self.assertTrue(audit['links'])
        np.testing.assert_array_equal(result[:,1],q[:,1])
        np.testing.assert_array_equal(result[outers],q[outers])
        self.assertTrue(all(l['after_width_px']==1 for l in audit['links']))

    def test_owned_inner_coordinate_conflict_is_explicit(self):
        m=ring();g,mapping,_=prepared_glyph(m);q=np.asarray(g.coordinates)*m['scale']
        f=next(f for f in detect(m) if f['axis']==0)
        inner=next(mapping[i] for i in f['points'] if m['points'][i]['contour']==1)
        with self.assertRaisesRegex(ValueError,'owned coordinate'):
            fit(m,q,[dict(point=inner,axis=0,value=q[inner,0])])

    def test_subdivision_does_not_change_pairing(self):
        from fontTools.misc.bezierTools import splitQuadraticAtT
        m=ring();contours=[]
        for loop in m['contours']:
            contours.append([part for sid in loop for part in splitQuadraticAtT(*m['segments'][sid]['control'],.5)])
        finer=prepare(contours,1000,baseline=True)
        a=sorted((f['axis'],round(f['width'],8)) for f in detect(m))
        b=sorted((f['axis'],round(f['width'],8)) for f in detect(finer))
        self.assertEqual(a,b)

if __name__=='__main__':unittest.main()
