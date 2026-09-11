import unittest
import numpy as np
from repeated_component_symmetry import fit

class RepetitionTests(unittest.TestCase):
    def setUp(self):
        self.p=np.array([[0.,0.],[0.,2.],[1.,2.],[1.,0.],[3.,0.],[3.,2.],[4.,2.],[4.,0.]])
    def test_repeat_uses_translation_not_glyph_identity(self):
        q=self.p.copy();q[4:,0]+=.2;q[5,0]+=.1
        out,a=fit(self.p,q,[3,7],[1]*8,10,1,set())
        self.assertEqual(a[0]['status'],'coordinated')
        np.testing.assert_allclose(out[4:]-out[:4],np.tile([3,0],(4,1)))
    def test_diagonal_repetition_is_outside_scope(self):
        p=self.p.copy();p[4:,1]+=3
        out,a=fit(p,p,[3,7],[1]*8,10,1,set())
        self.assertEqual(a,[]);np.testing.assert_array_equal(out,p)
    def test_owned_component_is_preserved(self):
        out,a=fit(self.p,self.p,[3,7],[1]*8,10,1,set(),[dict(point=0)])
        self.assertEqual(a[0]['status'],'held-owned');np.testing.assert_array_equal(out,self.p)
    def test_identical_component_bitmaps_are_preserved(self):
        ink={(0,-1),(0,-2),(3,-1),(3,-2)}
        out,a=fit(self.p,self.p,[3,7],[1]*8,10,1,ink)
        self.assertEqual(a[0]['status'],'already-repeated');np.testing.assert_array_equal(out,self.p)

if __name__=='__main__':unittest.main()
