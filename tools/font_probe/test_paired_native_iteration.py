"""Focused tests for the bounded paired-native-iteration diagnostic.

Each test states an independent expectation (hand computation, FreeType
behavior, recomputation from raw trace data); none mirrors implementation
literals.  Actual FreeType fixtures use few rounds so the suite stays fast;
the full 512-round corpus runs only under the experiment CLI.
"""
import copy
import math
import unittest

import experiment_paired_native_iteration as E

DIAG = 1.0 / 64.0


class AnalyticTests(unittest.TestCase):
    def test_cramer_hand_computed(self):
        # x + y = 3, x - y = 1  ->  (2, 1) by elimination.
        self.assertEqual(E.cramer([1.0, 1.0], 3.0, [1.0, -1.0], 1.0),
                         [2.0, 1.0])

    def test_cramer_oblique_hand_computed(self):
        # 0.6x + 0.8y = 0, -0.8x + 0.6y = 5.  From row1 x = -0.8y/0.6;
        # substituting gives y*(0.64/0.6 + 0.6) = 5, so y = 3, x = -4.
        got = E.cramer([0.6, 0.8], 0.0, [-0.8, 0.6], 5.0)
        self.assertAlmostEqual(got[0], -4.0, places=12)
        self.assertAlmostEqual(got[1], 3.0, places=12)

    def test_cramer_singular_rejected(self):
        with self.assertRaises(E.Reject):
            E.cramer([1.0, 0.0], 1.0, [2.0, 0.0], 2.0)


class FreezeTests(unittest.TestCase):
    def test_abs_negative_tie_goes_away_from_zero(self):
        # value chosen so raw px is exactly -12.5 at scale 1.
        got = E.freeze_rhs({"kind": "Abs", "normal": [1.0, 0.0],
                            "value": -12.5, "round": True}, [], 1.0)
        self.assertEqual(got["b"], -13.0)

    def test_abs_positive_tie_and_default_round_true(self):
        got = E.freeze_rhs({"kind": "Abs", "normal": [0.0, 1.0],
                            "value": 12.5}, [], 1.0)  # no 'round' key
        self.assertEqual(got["b"], 13.0)
        self.assertTrue(got["rounded"])

    def test_abs_unrounded_passthrough(self):
        got = E.freeze_rhs({"kind": "Abs", "normal": [1.0, 0.0],
                            "value": 12.5, "round": False}, [], 1.0)
        self.assertEqual(got["b"], 12.5)

    def test_dist_rounds_only_distance(self):
        # parent (4, 1), normal (1, 0): dot = 4; distance 2.5 -> 3 (away).
        got = E.freeze_rhs({"kind": "Dist", "normal": [1.0, 0.0],
                            "sources": [0], "value": 2.5, "round": True},
                           [[4.0, 1.0]], 1.0)
        self.assertEqual(got["b"], 7.0)
        self.assertEqual(got["parent"], [4.0, 1.0])

    def test_unsupported_kind_rejected_not_invented(self):
        with self.assertRaises(E.Reject):
            E.freeze_rhs({"kind": "Ratio", "normal": [1.0, 0.0],
                          "value": 1.0}, [], 1.0)

    def test_inputs_immutable(self):
        eq = {"kind": "Dist", "normal": [1.0, 0.0], "sources": [0],
              "value": 2.5, "round": True}
        parents = [[4.0, 1.0]]
        before = (copy.deepcopy(eq), copy.deepcopy(parents))
        E.freeze_rhs(eq, parents, 1.0)
        self.assertEqual((eq, parents), before)


class NativeFixtureTests(unittest.TestCase):
    @staticmethod
    def frozen_pair(n1, n2, sol, start):
        n = [list(map(float, n1)), list(map(float, n2))]
        b = [n[j][0] * sol[0] + n[j][1] * sol[1] for j in (0, 1)]
        return {"n": n, "b": b,
                "b266": [E.half_away(v * 64) for v in b],
                "start_px": list(map(float, start))}

    def test_cardinal_exact_and_gpv(self):
        frozen = self.frozen_pair([1.0, 0.0], [0.0, 1.0], [3.0, 5.0],
                                  [0.0, 0.0])
        ref, trace, gpv_raw, ana, asm, plen, _fb, nn = E.run_case(
            frozen, rounds=8)
        x0, y0 = trace[0][0] / 64.0, trace[0][1] / 64.0
        self.assertEqual((x0, y0), (3.0, 5.0))  # hand-checked intersection
        self.assertEqual(gpv_raw, [[16384, 0], [0, 16384]])
        # round 1 travels (0,0)->(3,5); round 2 is the first with no move.
        self.assertEqual(ana["first_exact_fixed_round"], 2)
        self.assertEqual(ana["first_small_round"], 2)
        self.assertTrue(ana["acc_original"]["1"])
        self.assertTrue(ana["acc_encoded"]["1"])
        self.assertLess(plen, 65536)

    def test_oblique_gpv_and_own_direction_movement(self):
        frozen = self.frozen_pair([0.6, 0.8], [0.8, -0.6], [4.0, -2.0],
                                  [0.0, 0.0])
        _ref, trace, gpv_raw, ana, _asm, _plen, _fb, _nn = E.run_case(
            frozen, rounds=8)
        # GPV must be near the F2.14-truncated unit normals (few LSB).
        for got, want in zip(gpv_raw, [[9830, 13107], [13107, -9830]]):
            self.assertLess(abs(got[0] - want[0]), 5)
            self.assertLess(abs(got[1] - want[1]), 5)
        # Full first native round must land near the float reference round.
        dx, dy = trace[0][0] / 64.0, trace[0][1] / 64.0
        r0 = E.reference_run(frozen["n"][0], frozen["b"][0],
                             frozen["n"][1], frozen["b"][1],
                             frozen["start_px"], rounds=1)["final"]
        self.assertLessEqual(max(abs(dx - r0[0]), abs(dy - r0[1])), DIAG)

    def test_single_equation_moves_along_own_direction(self):
        # Separate probe: one SCFS step must move along its own normal,
        # i.e. dot(unit displacement, unit normal) ~ 1.
        nx, ny = E.half_away(0.6 * 16384), E.half_away(0.8 * 16384)
        eqs = [{"nx214": nx, "ny214": ny, "b266": 100 * 64}]
        fb, _asm, _plen = E.build_fixture([0, 0], eqs, rounds=1,
                                          use_gpv=False)
        pts = E.run_native(fb)
        dx, dy = pts[0][0] / 64.0, pts[0][1] / 64.0
        step = math.hypot(dx, dy)
        self.assertGreater(step, 50.0)
        nl = math.hypot(nx, ny)
        dot = (dx / step) * (nx / nl) + (dy / step) * (ny / nl)
        self.assertGreater(dot, 0.999)

    def test_push_asm_compact_grouped_and_signed32_fallback(self):
        # In-range operands keep the compact grouped forms.
        self.assertEqual(E.push_asm(1, 2), ["PUSHB[ ]", "1", "2"])
        self.assertEqual(E.push_asm(-1, 300), ["PUSHW[ ]", "-1", "300"])
        # Larger signed32 operands materialize instead of raising.
        self.assertTrue(E.push_asm(40000))
        self.assertTrue(E.push_asm(-50000, 10))
        self.assertTrue(E.push_asm(2 ** 31 - 1))
        # Outside the signed32 safe range is explicitly rejected.
        with self.assertRaises(E.Reject):
            E.push_asm(2 ** 31)
        with self.assertRaises(E.Reject):
            E.push_asm(-2 ** 31 - 1)

    def test_cardinal_large_coordinates_materialize_natively(self):
        # |coord| > 512px forces the push_integer path for b266
        # (600*64 = 38400, -700*64 = -44800); proves stack operand
        # materialization through actual FT execution, not strings.
        frozen = self.frozen_pair([1.0, 0.0], [0.0, 1.0],
                                  [600.0, -700.0], [0.0, 0.0])
        _ref, trace, gpv_raw, ana, _asm, plen, _fb, _nn = E.run_case(
            frozen, rounds=8)
        x0, y0 = trace[0][0] / 64.0, trace[0][1] / 64.0
        self.assertEqual((x0, y0), (600.0, -700.0))
        self.assertEqual(gpv_raw, [[16384, 0], [0, 16384]])
        self.assertTrue(ana["acc_original"]["1"])
        self.assertLess(plen, 65536)

    def test_zero_pair_already_satisfied(self):
        frozen = self.frozen_pair([1.0, 0.0], [0.0, 1.0], [0.0, 0.0],
                                  [0.0, 0.0])
        _ref, trace, _gpv, ana, _asm, _plen, _fb, _nn = E.run_case(
            frozen, rounds=8)
        self.assertEqual((trace[0][0], trace[0][1]), (0, 0))
        self.assertEqual(ana["first_small_round"], 1)


class DetectionTests(unittest.TestCase):
    def test_near_parallel_flags_are_measured_not_assumed(self):
        deg = math.pi / 180.0
        n = [[1.0, 0.0], [math.cos(deg), math.sin(deg)]]
        sol, start = [10.0, 2.0], [0.0, 0.0]
        b = [n[j][0] * sol[0] + n[j][1] * sol[1] for j in (0, 1)]
        frozen = {"n": n, "b": b,
                  "b266": [E.half_away(v * 64) for v in b],
                  "start_px": list(map(float, start))}
        ref, trace, gpv_raw, ana, _asm, _plen, _fb, _nn = E.run_case(
            frozen, rounds=64)
        pos = [(x / 64.0, y / 64.0) for (x, y) in trace]
        moves = [max(abs(p[0] - q[0]), abs(p[1] - q[1]))
                 for p, q in zip(pos, [start] + pos[:-1])]
        first = next((i + 1 for i, m in enumerate(moves) if m < DIAG), None)
        self.assertEqual(ana["first_small_round"], first)
        if first is not None:
            if first > 1:
                self.assertGreaterEqual(moves[first - 2], DIAG)
            # accuracy flags must match recomputation from the raw trace
            p = pos[first - 1]
            ro, eo = E.res_err(p, n[0], b[0], n[1], b[1],
                               E.cramer(n[0], b[0], n[1], b[1]))
            self.assertEqual(ana["acc_original_at_first_small"],
                             bool(ro <= DIAG and eo <= DIAG))
        # fixed-point / cycle flags must match the integer trace exactly
        seq = [(int(x), int(y)) for (x, y) in trace]
        s0 = (E.half_away(start[0] * 64), E.half_away(start[1] * 64))
        ext = [s0] + seq
        fixed = next((i for i in range(1, len(ext))
                      if ext[i] == ext[i - 1]), None)
        self.assertEqual(ana["first_exact_fixed_round"], fixed)


class ReportTests(unittest.TestCase):
    def test_aggregate_counts(self):
        rows = [
            {"acc_original": {"1": True, "10": True, "100": True,
                              "512": True},
             "acc_encoded": {"1": True, "10": True, "100": True, "512": True},
             "first_small_round": 1, "acc_original_at_first_small": True,
             "acc_encoded_at_first_small": True,
             "first_exact_fixed_round": 1, "tail_period2": False,
             "final_res_original": 0.0, "final_err_original": 0.0,
             "final_res_encoded": 0.0, "final_err_encoded": 0.0,
             "max_res_original": 0.5, "max_err_original": 0.5},
            {"acc_original": {"1": False, "10": False, "100": False,
                              "512": False},
             "acc_encoded": {"1": False, "10": False, "100": False,
                             "512": False},
             "first_small_round": 3, "acc_original_at_first_small": False,
             "acc_encoded_at_first_small": False,
             "first_exact_fixed_round": None, "tail_period2": True,
             "final_res_original": 2.0, "final_err_original": 3.0,
             "final_res_encoded": 2.0, "final_err_encoded": 3.0,
             "max_res_original": 4.0, "max_err_original": 5.0},
        ]
        agg = E.aggregate(rows)
        self.assertEqual(agg["total"], 2)
        self.assertEqual(agg["original_accurate_at_512"], 1)
        self.assertEqual(agg["false_early_original"], 1)
        self.assertEqual(agg["false_early10_original"], 1)
        self.assertEqual(agg["exact_fixed_point"], 1)
        self.assertEqual(agg["tail_period2"], 1)
        self.assertEqual(agg["max_final_err_original"], 3.0)

    def test_fresh_output_guard(self):
        # The guard refuses existing output dirs; the named
        # investigation dir is git-ignored scratch that may not
        # exist on a fresh checkout, so ensure the refusal path
        # itself is what gets exercised.
        from pathlib import Path
        Path("out/paired-vector-investigation-v1").mkdir(
            parents=True, exist_ok=True)
        rc = E.main(["--output", "out/paired-vector-investigation-v1"])
        self.assertEqual(rc, 2)

    def test_synthetic_controls_complete(self):
        syns = E.synthetics()
        self.assertGreaterEqual(len(syns), 6)
        names = [s["name"] for s in syns]
        self.assertEqual(len(set(names)), len(names))
        for s in syns:
            self.assertEqual(len(s["n"]), 2)
            # reference must use the same fixed equations throughout:
            # residuals are non-increasing across checkpoints, and
            # well-conditioned controls reach the intersection.
            b = [s["n"][j][0] * s["sol"][0] + s["n"][j][1] * s["sol"][1]
                 for j in (0, 1)]
            ref = E.reference_run(s["n"][0], b[0], s["n"][1], b[1],
                                  s["start"], rounds=512)
            pts = ([s["start"]] + [ref["checkpoints"][c] for c in (1, 10, 100)]
                   + [ref["final"]])
            # alternating projections provably never increase distance to
            # the fixed intersection.
            dists = [math.hypot(p[0] - s["sol"][0], p[1] - s["sol"][1])
                     for p in pts]
            for a, c in zip(dists, dists[1:]):
                self.assertLessEqual(c, a + 1e-9)
            if not s["name"].startswith("syn-shallow"):
                self.assertLess(dists[-1], 1e-9)  # converged controls
            else:
                # shallow angles contract by ~cos^2(angle) per round, so
                # 512 rounds are not expected to reach the intersection;
                # slow/nonconverged outcome is the measured result.
                self.assertLess(dists[-1], dists[0])


if __name__ == "__main__":
    unittest.main()
