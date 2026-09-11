import unittest
import numpy as np
from cumulative_hinter import claim, validate_geometry
from joint_stroke_fit import constrained_fit


class OwnershipTests(unittest.TestCase):
    def test_later_claim_cannot_replace_existing_coordinate(self):
        owners=[]
        claim(owners,[0],[0],np.array([[1.,2.]]),'serif')
        with self.assertRaisesRegex(ValueError,'ownership conflict'):
            claim(owners,[0],[0],np.array([[3.,2.]]),'support')
        self.assertEqual(owners[0]['value'],1.)

    def test_owned_coordinate_survives_competing_soft_goal(self):
        owners=[]
        claim(owners,[0],[0],np.array([[1.,2.]]),'terminal')
        row=np.zeros(2);row[owners[0]['axis']]=1
        q=constrained_fit([row],[owners[0]['value']],np.eye(2),[100.,4.])
        np.testing.assert_allclose(q,[1.,4.])

    def test_extreme_baseline_is_rejected_without_clipping(self):
        source=np.array([[0.,0.],[3.,7.]])
        bad=np.array([[0.,0.],[3.,153.]])
        original=bad.copy()
        with self.assertRaisesRegex(ValueError,'admission bound'):
            validate_geometry(source,bad,'baseline')
        np.testing.assert_array_equal(bad,original)

    def test_nonfinite_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'invalid coordinate'):
            validate_geometry([[0.,0.]],[[float('nan'),0.]],'baseline')

if __name__=='__main__':unittest.main()
