import unittest
import numpy as np
from source_relative_balance import fit
from compare_source_balance import strict_reference

class SourceBalanceTests(unittest.TestCase):
    def test_source_asymmetry_is_not_forced_to_zero(self):
        outer=np.array([[0,2],[0,4],[2,4],[4,4],[4,2],[4,0],[2,0],[0,0]],float)
        inner=(outer-2)*.5+2+[.15,0]
        p=np.vstack([outer,inner]);tags=[1,0]*8
        cs=[dict(kind='Abs',point=i,normal=np.eye(2)[axis].tolist(),sources=[],value=float(p[i,axis]),round=False) for i in range(16) for axis in (0,1)]
        q,a=fit(p,p,[7,15],tags,1,100,dict(graph=dict(constraints=cs)))
        self.assertEqual(a['status'],'fitted')
        self.assertGreater(max(abs(r['source_difference_px']) for r in a['profiles']),.2)
        np.testing.assert_allclose(q,p,atol=1e-7)

    def test_strict_bitmap_reference_is_symmetric_and_nonmutating(self):
        g=dict(width=3,height=3,pixels=[1,0,0,1,1,0,0,1,0]);saved=list(g['pixels'])
        out=strict_reference(g);a=np.array(out['pixels']).reshape(3,3)
        np.testing.assert_array_equal(a,a[:,::-1]);np.testing.assert_array_equal(a,a[::-1])
        self.assertEqual(g['pixels'],saved)

if __name__=='__main__':unittest.main()
