"""Calibration constraints and held-out isolation, not optical acceptance."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from typefacet_integer import FAMILIES, reference_error, select, params


def record(normal, intrusion, density, error):
    return dict(parameters=params(normal, intrusion),density_error_px=density,
                reference_errors={"None":error})


class IntegerCalibrationTests(unittest.TestCase):
    def test_reference_error_cannot_buy_global_expansion(self):
        wide = record(.16,.05,.8,0.)
        admissible = record(.10,.10,.005,.5)
        best, feasible = select([wide,admissible])
        self.assertIs(best,admissible)
        self.assertTrue(feasible)

    def test_infeasible_density_is_reported_and_not_hidden(self):
        a,b=record(.16,.05,.8,0.),record(.10,.10,-.1,1.)
        best, feasible = select([a,b])
        self.assertIs(best,b)
        self.assertFalse(feasible)

    def test_families_have_equal_weight_and_held_out_steps_do_not_enter_loss(self):
        targets={p:0. for pairs in FAMILIES.values() for p in pairs}
        for pairs in FAMILIES.values():
            steps=dict(targets,**dict.fromkeys(pairs,2.))
            self.assertAlmostEqual(reference_error(steps,targets),math.sqrt(4/3))
            steps.update(gs=1000.,hi=-1000.)
            self.assertAlmostEqual(reference_error(steps,targets),math.sqrt(4/3))

    def test_equal_scores_use_fixed_parameter_order_not_pair_preferences(self):
        a,b=record(.10,.15,.005,.5),record(.12,.05,.005,.5)
        self.assertIs(select([a,b])[0],b)
        self.assertIs(select([b,a])[0],b)


if __name__ == '__main__':
    unittest.main()
