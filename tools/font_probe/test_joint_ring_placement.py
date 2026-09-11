import unittest
import numpy as np
from joint_ring_placement import place
from repeated_rings import fit


def example():
    outer=np.array([[0,0],[0,320],[320,320],[320,0]],float)
    inner=np.array([[80,80],[240,80],[240,240],[80,240]],float)
    # Two rings on opposite sides of an isolated diagonal separator.
    p=np.concatenate([outer+[0,400],inner+[0,400],outer+[600,0],inner+[600,0],[[250,0],[300,0],[700,750],[650,750]]])
    ends=[3,7,11,15,19];tags=[1]*20
    fitted,pairs=fit(p,p*.014,tags,ends,1000,14)
    return p,fitted,tags,ends,pairs


class PlacementTests(unittest.TestCase):
    def test_rigid_translations_and_relative_error(self):
        p,b,t,e,pairs=example();q,records=place(p,b,t,e,1000,14,pairs)
        self.assertEqual(records[0]['status'],'placed')
        self.assertLessEqual(records[0]['relative_error_after_px'],records[0]['relative_error_before_px'])
        for ids in (slice(0,8),slice(8,16),slice(16,20)):
            d=q[ids]-b[ids];np.testing.assert_allclose(d,np.tile(d[0],(len(d),1)),atol=1e-12)
        for ids in (slice(0,8),slice(8,16)):
            np.testing.assert_allclose(q[ids]-b[ids],np.rint(q[ids]-b[ids]))

    def test_missing_separator_holds(self):
        p,b,t,e,pairs=example();q,r=place(p[:16],b[:16],t[:16],e[:4],1000,14,pairs)
        self.assertEqual(r[0]['status'],'held');np.testing.assert_array_equal(q,b[:16])

    def test_translation_equivariance(self):
        p,b,t,e,pairs=example();q,r=place(p,b,t,e,1000,14,pairs)
        shift=np.array([2,-3]);other,_=place(p+shift/.014,b+shift,t,e,1000,14,pairs)
        np.testing.assert_allclose(other,q+shift)

if __name__=='__main__':unittest.main()
