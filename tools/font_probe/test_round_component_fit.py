import unittest
import numpy as np
from round_component_fit import fit,mismatch

class RoundPhaseTests(unittest.TestCase):
    def test_reflection_score_ignores_translation(self):
        ink={(4,7),(5,7),(4,8),(5,8)}
        self.assertEqual(mismatch(ink,0),0)
        self.assertEqual(mismatch(ink,1),0)
        self.assertGreater(mismatch(ink|{(6,7)},0),0)

    def test_symmetric_ring_remains_exactly_unchanged(self):
        outer=np.array([[0,2],[0,4],[2,4],[4,4],[4,2],[4,0],[2,0],[0,0]],float)
        inner=(outer-2)*.5+2
        p=np.vstack([outer,inner]);tags=[1,0]*8
        constraints=[dict(kind='Abs',point=i,normal=np.eye(2)[axis].tolist(),sources=[],value=float(p[i,axis]),round=False) for i in range(16) for axis in (0,1)]
        ink={(0,0),(1,0),(0,1),(1,1)}
        q,a=fit(p,p,tags,[7,15],10,10,dict(graph=dict(constraints=constraints)),[],lambda q,ids,factor:ink)
        np.testing.assert_array_equal(q,p)
        self.assertEqual(a[0]['status'],'already-symmetric')

if __name__=='__main__':unittest.main()
