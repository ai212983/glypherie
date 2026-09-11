"""Geometry-only terminal placement checks."""
import unittest
import numpy as np
from shamir_geometry import prepare
from shamir_segment_fit import prepared_glyph
from stem_relative_terminals import detect,fit


def model(reverse=False,mirror=False):
    p=np.array([(0,500),(100,500),(100,0),(150,-20),(210,-50),(90,-70),(0,0)],float)
    if mirror:p[:,0]*=-1
    if reverse:p=p[::-1]
    m=prepare([[[a,b] for a,b in zip(p,np.roll(p,-1,axis=0))]],1000,baseline=True)
    m['scale']=.01
    return m


class TerminalTests(unittest.TestCase):
    def test_direction_and_winding_preserve_relative_measurement(self):
        for reverse in (False,True):
            for mirror in (False,True):
                m=model(reverse,mirror);p,h=detect(m)
                self.assertEqual(len(h),1);self.assertEqual(h[0]['extension'],110.)

    def test_source_extension_and_parent_preserved(self):
        m=model();p,h=detect(m);h=h[0];q=p*.01;q[h['tip'],0]=3
        after,audit=fit(m,q)
        self.assertAlmostEqual(audit[0]['after_extension_px'],1.1)
        np.testing.assert_array_equal(after[:,1],q[:,1])
        np.testing.assert_array_equal(after[h['parent']],q[h['parent']])
        self.assertEqual(after[h['tip'],0],2.1)

    def test_owned_terminal_conflict_is_explicit(self):
        m=model();p,h=detect(m);h=h[0];q=p*.01;q[h['tip'],0]=3
        with self.assertRaisesRegex(ValueError,'owned coordinate'):
            fit(m,q,[dict(point=h['tip'],axis=0,value=3)])

    def test_already_source_sized_is_unchanged(self):
        m=model();p,_=detect(m);after,audit=fit(m,p*.01)
        np.testing.assert_array_equal(after,p*.01);self.assertEqual(audit,[])

if __name__=='__main__':unittest.main()
