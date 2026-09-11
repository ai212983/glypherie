import unittest
from unittest.mock import patch
from audit_shamir_tolerances import candidates, summary


class ToleranceAuditTests(unittest.TestCase):
    def test_misaligned_extrema_measure_projection_separately_from_chord(self):
        model = dict(em=1000, tolerances=dict(distance=3.,angle_radians=.04),points=[
            dict(id=0,kind='curve',position=[0.,10.],extrema={'1':'max'},outgoing=[1.,0.]),
            dict(id=1,kind='curve',position=[3.,6.],extrema={'1':'max'},outgoing=[-1.,0.])])
        with patch('audit_shamir_tolerances.Interior') as interior:
            interior.return_value.between.return_value=True
            row=candidates(model)[0]
        self.assertEqual(row['projected_width'],4.)
        self.assertEqual(row['euclidean_width'],5.)
        self.assertEqual(row['alignment_em'],.003)

    def test_sweep_is_inclusive_and_reports_ambiguous_matches(self):
        base=dict(font='fixture',char='?',axis=1,alignment_em=.012,
                  projected_width=4.,euclidean_width=5.,euclidean_rounding=5,
                  projected_rounding=4,native_projected_rounding=4)
        rows=[dict(base,points=[0,1]),dict(base,points=[0,2])]
        self.assertEqual(summary(rows,.006)['features'],0)
        result=summary(rows,.012)
        self.assertEqual(result['features'],2)
        self.assertEqual(result['extrema_with_multiple_partners'],1)
        self.assertEqual(result['euclidean_vs_native_rounded_width_changes'],2)

    def test_interior_rejection_remains_independent_of_alignment_bound(self):
        model = dict(em=1000, tolerances=dict(distance=3.,angle_radians=.04),points=[
            dict(id=0,kind='curve',position=[0.,10.],extrema={'1':'max'},outgoing=[1.,0.]),
            dict(id=1,kind='curve',position=[0.,6.],extrema={'1':'max'},outgoing=[-1.,0.])])
        with patch('audit_shamir_tolerances.Interior') as interior:
            interior.return_value.between.return_value=False
            self.assertEqual(candidates(model),[])


if __name__=='__main__':unittest.main()
