import unittest
import numpy as np
from repeated_rings import fit


def fixture():
    outer=np.array([[0,0],[0,320],[320,320],[320,0]],float)
    inner=np.array([[80,80],[240,80],[240,240],[80,240]],float)
    p=np.concatenate([outer,inner,outer+[500,400],inner+[500,400],[[1000,0],[1100,0],[1100,50],[1000,50]]])
    return p,[3,7,11,15,19]


class RingTests(unittest.TestCase):
    def test_shared_dimensions_and_unrelated_preserved(self):
        p,ends=fixture(); before=p*.014; before[8:16,0]*=1.1
        q,pairs=fit(p,before,[1]*20,ends,1000,14)
        self.assertEqual(len(pairs),1)
        np.testing.assert_array_equal(q[16:],np.rint(before[16:]*64)/64)
        for a,b in ((slice(0,4),slice(8,12)),(slice(4,8),slice(12,16))):
            np.testing.assert_array_equal(q[a]-q[a].min(0),q[b]-q[b].min(0))

    def test_different_ring_does_not_match(self):
        p,ends=fixture();p[8:16,0]*=1.2
        _,pairs=fit(p,p*.014,[1]*20,ends,1000,14)
        self.assertEqual(pairs,[])

    def test_contour_order_rotation_and_winding(self):
        p,ends=fixture(); q,_=fit(p,p*.014,[1]*20,ends,1000,14)
        ids=np.concatenate([np.roll(np.arange(i,i+4)[::-1],2) for i in (8,12,0,4,16)])
        changed,pairs=fit(p[ids],(p*.014)[ids],[1]*20,ends,1000,14)
        self.assertEqual(len(pairs),1)
        np.testing.assert_array_equal(changed,q[ids])

    def test_three_equivalent_rings_are_held_as_ambiguous(self):
        p,_=fixture();p=np.concatenate([p[:16],p[:8]+[1000,800]])
        _,pairs=fit(p,p*.014,[1]*24,list(range(3,24,4)),1000,14)
        self.assertEqual(pairs,[])

if __name__=='__main__':unittest.main()
