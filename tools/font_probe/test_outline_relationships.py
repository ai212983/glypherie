import unittest
import numpy as np
from outline_relationships import reversed_edges, recover_order, curve_correspondence

class ContourRelationships(unittest.TestCase):
    def test_inversion_is_detected_below_displacement_bound(self):
        p=np.array([[0.,2.],[0.,1.],[1.,0.]])
        q=p.copy();q[1,1]=2.5
        self.assertEqual(reversed_edges(p,q,[2],[1]*3)[0]['axis'],1)

    def test_recovery_preserves_metric_and_source_edge_gap(self):
        p=np.array([[0.,2.],[0.,1.],[1.,0.]])
        q=p.copy();q[1,1]=2.5
        cs=[]
        for i in range(3):
            for axis in (0,1):
                cs.append(dict(kind='Abs',point=i,normal=np.eye(2)[axis].tolist(),sources=[],value=float(p[i,axis]),round=False,metric=(i==0)))
        r,claims=recover_order(p,q,[2],[1]*3,{'graph':{'constraints':cs}},1)
        self.assertAlmostEqual(r[0,1],2)
        self.assertAlmostEqual(r[1,1],1)
        self.assertEqual(len(claims),1)

    def test_reflection_pairs_distinct_contours(self):
        p=np.array([[0.,0.],[0.,2.],[1.,2.],[1.,0.],[3.,0.],[3.,2.],[4.,2.],[4.,0.]])
        m=curve_correspondence(p,[3,7],[1]*8,1000)
        self.assertEqual(m['status'],'coordinated')
        self.assertEqual(m['contour_pairs'],[1,0])

    def test_asymmetric_shape_remains_unmatched(self):
        p=np.array([[0.,0.],[0.,2.],[1.,3.],[1.,0.]])
        self.assertEqual(curve_correspondence(p,[3],[1]*4,10)['status'],'not-matched')

if __name__=='__main__':unittest.main()
