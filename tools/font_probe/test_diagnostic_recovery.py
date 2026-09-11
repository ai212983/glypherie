import json
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from audit_shamir_segment_conflicts import solve


class RecoveryTests(unittest.TestCase):
    def test_captured_finite_system_retains_conflict_and_rank(self):
        data=json.loads((Path(__file__).parent/'testdata/zero-column-lstsq.json').read_text())
        a=np.zeros(data['shape'])
        for i,j,v in data['entries']:a[i,j]=v
        result=solve(a,np.array(data['values']))
        self.assertEqual(result['rank'],55)
        self.assertFalse(result['consistent']);self.assertFalse(result['unique'])
        self.assertAlmostEqual(result['residual_px'],3/11)
        p=np.array(result['points_px']).ravel()
        self.assertTrue(np.all(p[~np.any(a!=0,axis=0)]==0))

    def test_recovery_preserves_original_cutoff_and_zero_coordinates(self):
        a=np.array([[1.,0,0,0],[0,1e-16,0,0]]);b=np.array([2.,1.])
        original=np.linalg.lstsq
        calls=[]
        def fail_once(matrix,values,rcond=None):
            calls.append(rcond)
            if len(calls)==1:raise np.linalg.LinAlgError('injected convergence failure')
            return original(matrix,values,rcond=rcond)
        with patch('numpy.linalg.lstsq',side_effect=fail_once):result=solve(a,b)
        self.assertEqual(calls[1],4*np.finfo(float).eps)
        self.assertEqual(result['rank'],1)
        self.assertEqual(result['points_px'],[[2.,0.],[0.,0.]])
        self.assertFalse(result['consistent'])

    def test_no_zero_columns_propagates_failure(self):
        with patch('numpy.linalg.lstsq',side_effect=np.linalg.LinAlgError('failure')):
            with self.assertRaises(np.linalg.LinAlgError):solve(np.eye(2),np.ones(2))

    def test_nonfinite_is_explicit(self):
        with self.assertRaisesRegex(ValueError,'nonfinite'):solve(np.array([[float('nan'),0]]),np.ones(1))


if __name__=='__main__':unittest.main()
