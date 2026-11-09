"""Focused tests for the target-calibration analysis helpers (synthetic only).

Covers the study's own Python selection/quantile math against brute force:
TIE-v2 mirror choice, tiebreak, fallback, eligibility gating and quantile
indexing. No engine, no captures, no optical claim. Run:
python3 experiments/contextual_spacing/tests/test_yinyang_local_target.py
"""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yinyang_local_target_study import eligible_arrays, pct, tie_choose


def row(step, gl, valid=True, abstain=False, weak=0.0):
    return [step, 1 if valid else 0, gl, 7, weak,
            1 if abstain else 0, "zero_local_evidence" if abstain else None,
            0, 0.0, 10.0, 0, 0, 0.0]


class TestTieChoose(unittest.TestCase):
    def test_picks_nearest(self):
        tied, chosen, fb = tie_choose([3, 4, 5], [1.0, 2.0, 4.0], 2.2, 3)
        self.assertFalse(fb)
        self.assertEqual(chosen, 4)
        self.assertEqual(tied, [4])

    def test_lowest_step_wins_exact_tie(self):
        tied, chosen, fb = tie_choose([3, 4], [1.0, 1.0], 0.0, 3)
        self.assertFalse(fb)
        self.assertEqual(chosen, 3)
        self.assertEqual(tied, [3, 4])

    def test_tie_tolerance_band(self):
        g0, g1 = 1.0, 1.0 + 0.5e-9 * max(1.0, 0.0)
        tied, chosen, fb = tie_choose([3, 4], [g0, g1], 0.0, 3)
        self.assertFalse(fb)
        self.assertEqual(set(tied), {3, 4})
        self.assertEqual(chosen, 3)

    def test_fallback_empty(self):
        tied, chosen, fb = tie_choose([], [], 1.0, 9)
        self.assertTrue(fb)
        self.assertEqual(chosen, 9)
        self.assertEqual(tied, [])

    def test_matches_brute_force(self):
        import random
        rng = random.Random(7)
        for _ in range(200):
            n = rng.randint(1, 12)
            steps = sorted(rng.sample(range(40), n))
            gls = [rng.uniform(0, 9) for _ in range(n)]
            cstar = rng.uniform(-1, 10)
            tied, chosen, fb = tie_choose(steps, gls, cstar, steps[0])
            devs = [abs(g - cstar) for g in gls]
            mstar = min(devs)
            tol = 1e-9 * max(1.0, mstar)
            exp = sorted(s for s, d in zip(steps, devs) if d <= mstar + tol)
            self.assertFalse(fb)
            self.assertEqual(tied, exp)
            self.assertEqual(chosen, min(exp))


class TestEligibleArrays(unittest.TestCase):
    def test_gates_invalid_abstain_nonfinite(self):
        pr = {"metric": 5, "steps": [
            row(5, 1.0), row(6, float("nan")), row(7, 2.0, abstain=True),
            row(8, 3.0, valid=False), row(9, float("inf")), row(10, 0.5)]}
        steps, gls, weaks = eligible_arrays(pr)
        self.assertEqual(steps, [5, 10])
        self.assertEqual(gls, [1.0, 0.5])
        self.assertEqual(weaks, [0.0, 0.0])

    def test_weak_defaults_finite(self):
        pr = {"metric": 5, "steps": [row(5, 1.0, weak=float("nan"))]}
        _, _, weaks = eligible_arrays(pr)
        self.assertEqual(weaks, [0.0])


class TestPct(unittest.TestCase):
    def test_indexing(self):
        vals = [10.0, 20.0, 30.0, 40.0]
        self.assertEqual(pct(vals, 0.0), 10.0)
        self.assertEqual(pct(vals, 0.50), 30.0)
        self.assertEqual(pct(vals, 1.0), 40.0)

    def test_empty_is_nan(self):
        self.assertTrue(math.isnan(pct([], 0.5)))


if __name__ == "__main__":
    unittest.main()
