import unittest
import numpy as np
from whole_stroke_widths import select, fit

class WholeSideTests(unittest.TestCase):
    def test_conflicting_anchor_is_explicit(self):
        q, accepted, rejected, rank = select([[1,0],[0,1],[1,0]],[2,3,4],2)
        np.testing.assert_allclose(q,[2,3])
        self.assertEqual(rejected,[2])
        self.assertEqual(rank,2)

    def test_redundant_equation_is_not_a_conflict(self):
        _,_,rejected,rank=select([[1,0],[2,0]],[2,4],2)
        self.assertEqual(rejected,[])
        self.assertEqual(rank,1)

    def test_taper_becomes_whole_side_width_and_releases_anchor(self):
        p=np.array([[0.,0.],[0.,10.],[4.,10.],[2.,0.]])
        cs=[dict(id=2*i+a,kind='Abs',point=i,sources=[],normal=[1-a,a],value=q[a],round=False) for i,q in enumerate(p) for a in (0,1)]
        cs[4]=dict(id=4,kind='Dist',point=2,sources=[0],normal=[1,0],value=4,feature='width-0')
        record=dict(graph=dict(order=list(range(4)),constraints=cs),features=[dict(kind='slant',normal=[1,0],width=3,support_direction=[0,1],support_intervals=[[0,10]])])
        q,audit=fit(p,[3],[1]*4,record,1)
        self.assertAlmostEqual(q[2,0]-q[1,0],3)
        self.assertAlmostEqual(q[3,0]-q[0,0],3)
        self.assertTrue(audit['released_equations'])
        original = np.array([[0.,0.],[0.,10.],[4.,10.],[2.,0.]])
        held, report = fit(p,[3],[1]*4,record,1,protected=True)
        np.testing.assert_allclose(held,original)
        self.assertEqual(report['candidate_status'],'held')
        self.assertEqual(report['released_equations'],[])
        self.assertTrue(report['conflicts'])

    def test_compatible_protected_stroke_is_fitted(self):
        p=np.array([[0.,0.],[0.,10.],[3.,10.],[3.,0.]])
        cs=[dict(id=2*i+a,kind='Abs',point=i,sources=[],normal=[1-a,a],value=q[a],round=False) for i,q in enumerate(p) for a in (0,1)]
        cs[4]=dict(id=4,kind='Dist',point=2,sources=[0],normal=[1,0],value=2,feature='width-0')
        record=dict(graph=dict(order=list(range(4)),constraints=cs),features=[dict(kind='slant',normal=[1,0],width=3,support_direction=[0,1],support_intervals=[[0,10]])])
        q,audit=fit(p,[3],[1]*4,record,1,protected=True)
        np.testing.assert_allclose(q,p,atol=1e-10)
        self.assertEqual(audit['candidate_status'],'fitted')
        self.assertEqual(audit['released_equations'],[])

if __name__=='__main__':unittest.main()
