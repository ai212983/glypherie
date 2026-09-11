import unittest
import numpy as np
from feature_coordination import shared_diagonal_widths,reflected_outline


class CoordinationTests(unittest.TestCase):
    def test_shared_class_straddling_pixel_boundary(self):
        fs=[dict(kind='slant',normal=[.9,.4],width=171,length=100),dict(kind='slant',normal=[-.9,.4],width=172,length=100)]
        cs=[dict(id=i,kind='Dist',feature=f'width-{i}',value=v) for i,v in enumerate([169,-173])]
        audit=shared_diagonal_widths(fs,cs)
        self.assertEqual([c['value'] for c in cs],[171.5,-171.5])
        self.assertEqual(len(audit),1)

    def test_unrelated_widths_remain_separate(self):
        fs=[dict(kind='slant',normal=[.9,.4],width=w,length=100) for w in [100,150]]
        self.assertEqual(shared_diagonal_widths(fs,[]),[])

    def test_reflection_requires_contour_and_tags(self):
        p=np.array([[0.,0.],[0.,10.],[4.,10.],[4.,0.]])
        q=p.copy();q[1,0]=.03
        out,audit=reflected_outline(p,q,[3],[1]*4,100)
        self.assertEqual(audit['status'],'coordinated')
        self.assertAlmostEqual(out[1,0]+out[2,0],4)
        _,audit=reflected_outline(p,q,[3],[0,1,1,1],100)
        self.assertEqual(audit['status'],'not-matched')

    def test_intentional_asymmetry_stays(self):
        p=np.array([[0.,0.],[0.,10.],[5.,10.],[4.,0.]])
        out,audit=reflected_outline(p,p,[3],[1]*4,100)
        self.assertEqual(audit['status'],'not-matched')
        self.assertTrue(np.array_equal(out,p))
