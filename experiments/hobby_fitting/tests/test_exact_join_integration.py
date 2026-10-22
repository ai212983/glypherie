"""Delivery controls for the opt-in exact arrangement gate.

The reference changes topology validation only. The fitter still owns
width targets, exact native coordinates and exact-upstream abstention.
"""
import unittest
from experiments.hobby_fitting import direct_diagonal as dd
from experiments.hobby_fitting import exact_topology as et
from experiments.hobby_fitting.tests.test_direct_diagonal import bar_stem


class ExactJoinDelivery(unittest.TestCase):
    def setUp(self):
        self.source, self.upstream = bar_stem(stem_fit=9.0)
        self.reference = dd.build_reference([{
            "source_commands": self.source,
            "fitted_commands": self.upstream,
        }], 16.0)

    def fit(self, checker, native=(False, False)):
        return dd.fit_glyph(self.source, self.upstream, 16.0,
                            self.reference, native, False,
                            topology_checker=checker)

    def test_reference_leaves_fitting_objective_unchanged(self):
        strict = self.fit(None)
        exact = self.fit(et.compare_commands)
        self.assertTrue(strict["applied"], strict["reason"])
        self.assertTrue(exact["applied"], exact["reason"])
        self.assertEqual(exact["candidate_commands"], strict["candidate_commands"])
        self.assertEqual(exact["validity"]["topology_mode"], "exact_arrangement")
        self.assertTrue(exact["validity"]["exact_topology"]["supported"])

    def test_declined_reference_delivers_exact_upstream(self):
        output = self.fit(lambda *_: {"supported": True, "ok": False,
                                     "reason": "attachment-changed"})
        self.assertFalse(output["applied"])
        self.assertIs(output["candidate_commands"], self.upstream)
        self.assertEqual(output["movement"], 0.0)
        self.assertFalse(output["phase_applied"])
        self.assertFalse(output["validity"]["topology"])

    def test_reference_exception_abstains(self):
        def broken(*_):
            raise RuntimeError("unavailable reference")
        output = self.fit(broken)
        self.assertFalse(output["applied"])
        self.assertIs(output["candidate_commands"], self.upstream)
        self.assertEqual(output["validity"]["exact_topology"]["reason"],
                         "checker-exception")

    def test_reference_cannot_move_native_owned_axes(self):
        output = self.fit(lambda *_: {"supported": True, "ok": True},
                          native=(True, True))
        self.assertFalse(output["applied"])
        self.assertIs(output["candidate_commands"], self.upstream)


if __name__ == "__main__":
    unittest.main()
