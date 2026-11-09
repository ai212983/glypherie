"""Protect the calibration experiment against family bias and holdout leakage."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from typefacet_calibrate import FAMILIES, HELD_OUT, REFERENCES, loss, parameters, ranked


class CalibrationIsolationTests(unittest.TestCase):
    def test_families_have_equal_influence_despite_different_sizes(self):
        target = dict.fromkeys(REFERENCES, 0.)
        for family in FAMILIES.values():
            perturbed = dict(target, **dict.fromkeys(family, 2.))
            # A two-pixel error in any one whole family contributes 1 px².
            self.assertEqual(loss(perturbed, target), 1.)

    def test_held_out_measurements_cannot_change_loss_or_selection(self):
        self.assertFalse(set(REFERENCES)&set(HELD_OUT))
        target = dict.fromkeys(REFERENCES, 1.)
        records = [dict(parameters=parameters((0., .1, .1, .1)), steps_px=dict(target)),
                   dict(parameters=parameters((.02, .1, .1, .1)), steps_px=dict.fromkeys(REFERENCES, 2.))]
        expected = [r["parameters"] for r in ranked(records, target)]
        for i, record in enumerate(records):
            record["steps_px"].update(dict.fromkeys(HELD_OUT, 1e6*(-1)**i))
        target.update(dict.fromkeys(HELD_OUT, -1e6))
        self.assertEqual(expected, [r["parameters"] for r in ranked(records, target)])

    def test_omitted_family_has_no_selection_influence(self):
        targets = dict.fromkeys(REFERENCES, 0.)
        perturbed = dict(targets, **dict.fromkeys(FAMILIES["endpoint"], 100.))
        self.assertGreater(loss(perturbed, targets), 0.)
        self.assertEqual(loss(perturbed, targets, "endpoint"), 0.)


if __name__ == "__main__":
    unittest.main()
