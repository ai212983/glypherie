import unittest
import numpy as np
from component_placement import place


class ComponentTests(unittest.TestCase):
    def fixture(self):
        box=np.array([[0,0],[0,100],[100,100],[100,0]],float)
        p=np.concatenate([box,box+[300,250],box*[.5,2]+[600,0]])
        b=np.rint(p*.02*64)/64;b[4:8]+=[1,0]
        return p,b,[1]*12,[3,7,11]

    def test_generic_repetition_and_rigidity(self):
        p,b,t,e=self.fixture();q,r=place(p,b,t,e,1000,20)
        self.assertEqual(r['status'],'placed');self.assertEqual(r['repeated_pairs'],[[0,1]])
        self.assertLess(r['relative_error_after_px'],r['relative_error_before_px'])
        for group in r['components']:
            d=q[group]-b[group];np.testing.assert_array_equal(d,np.tile(d[0],(len(d),1)))
        np.testing.assert_array_equal(r['translations_px'][:2],np.rint(r['translations_px'][:2]))

    def test_reordering_and_reversing_contours(self):
        p,b,t,e=self.fixture();q,_=place(p,b,t,e,1000,20)
        ids=np.concatenate([np.arange(i,i+4)[::-1] for i in (8,0,4)])
        other,_=place(p[ids],b[ids],t,e,1000,20)
        np.testing.assert_allclose(other,q[ids])

    def test_single_component_unchanged(self):
        p,b,t,e=self.fixture();q,r=place(p[:4],b[:4],t[:4],[3],1000,20)
        np.testing.assert_array_equal(q,b[:4]);self.assertEqual(r['status'],'unchanged')

    def test_non_repeated_components_supported(self):
        p,b,t,e=self.fixture();p[4:8]*=[1.2,1]
        _,r=place(p,b,t,e,1000,20)
        self.assertEqual(r['status'],'placed');self.assertEqual(r['repeated_pairs'],[])

if __name__=='__main__':unittest.main()
