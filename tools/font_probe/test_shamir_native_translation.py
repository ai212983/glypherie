"""Tests for native translation: exact FT vs literal references (owned by this task)."""
import copy
import io
import json
import math
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

import numpy as np

import compare_native_sequences as R
from compare_native_translation import run_ft_raw
from shamir_constraints import relation
from shamir_native_translation import UnsupportedNativeTranslation, compile_native
from shamir_point_schedule import schedule

X = [1.0, 0.0]
Y = [0.0, 1.0]
N = [0.6, 0.8]
N2 = [-0.8, 0.6]
PPEMS = [14, 16, 18, 20, 125]
CARD_HAND = {20: dict(x0=4, y0=2, x1=9, y1=6, x2=5, x3=4)}


class TestNativeRef(unittest.TestCase):
    def graphs(self):
        return [(k, p, c) for k, p, c in R.fixtures()]

    def test_exact_ref_all_fixtures_sizes(self):
        for key, pts, chosen in self.graphs():
            pts = [list(map(float, p)) for p in pts]
            g = schedule(np.asarray(pts, float), {k: list(v) for k, v in chosen.items()}, [], [])
            nasm, nmeta = compile_native(g, pts)
            rasm, rcvt = R.REFS[key]()
            # CVT layout/dedup is intentionally not compared: only the
            # executed coordinates must match exactly.
            for ppem in PPEMS:
                nraw, _, _ = run_ft_raw(pts, nasm, ppem, list(nmeta["cvt"]) or [0])
                rraw, _, _ = run_ft_raw(pts, rasm, ppem, list(rcvt) or [0])
                self.assertTrue(np.array_equal(np.asarray(nraw), np.asarray(rraw)),
                                (key, ppem, nraw, rraw))

    def test_cardinal_hand_expected(self):
        key, pts, chosen = next(t for t in self.graphs() if t[0] == "cardinal-chain")
        pts = [list(map(float, p)) for p in pts]
        g = schedule(np.asarray(pts, float), {k: list(v) for k, v in chosen.items()}, [], [])
        nasm, nmeta = compile_native(g, pts)
        raw, _, _ = run_ft_raw(pts, nasm, 20, list(nmeta["cvt"]) or [0])
        px = (np.asarray(raw, float) / 64.0).tolist()
        e = CARD_HAND[20]
        self.assertAlmostEqual(px[0][0], e["x0"])
        self.assertAlmostEqual(px[0][1], e["y0"])
        self.assertAlmostEqual(px[1][0], e["x1"])
        self.assertAlmostEqual(px[1][1], e["y1"])
        self.assertAlmostEqual(px[2][0], e["x2"])
        self.assertAlmostEqual(px[3][0], e["x3"])
        for p in range(4):
            for axis in (0, 1):
                self.assertEqual(raw[p][axis] % 1, 0)

    def test_ratio_signed_source_hand(self):
        for key, ppem, idx, axis, val in [("ratio-mid", 20, 2, 0, 8.0),
                                          ("ratio-extrapolation", 20, 3, 1, 16.0),
                                          ("signed", 125, 0, 0, -1.0),
                                          ("signed", 125, 1, 0, -2.0)]:
            _, pts, chosen = next(t for t in self.graphs() if t[0] == key)
            pts = [list(map(float, p)) for p in pts]
            g = schedule(np.asarray(pts, float), {k: list(v) for k, v in chosen.items()}, [], [])
            nasm, nmeta = compile_native(g, pts)
            raw, _, _ = run_ft_raw(pts, nasm, ppem, list(nmeta["cvt"]) or [0])
            self.assertAlmostEqual(float(np.asarray(raw)[idx][axis]) / 64.0, val, msg=(key, ppem))

    def test_source_round_hand(self):
        _, pts, chosen = next(t for t in self.graphs() if t[0] == "source-round")
        pts = [list(map(float, p)) for p in pts]
        g = schedule(np.asarray(pts, float), {k: list(v) for k, v in chosen.items()}, [], [])
        nasm, nmeta = compile_native(g, pts)
        raw, _, _ = run_ft_raw(pts, nasm, 20, list(nmeta["cvt"]) or [0])
        px = (np.asarray(raw, float) / 64.0).tolist()
        self.assertEqual(px, [[2.0, 0.0], [10.0, 4.0], [6.0, 2.0], [2.0, 14.0]])

    def test_order_difference_reported(self):
        _, p2, c2 = next(t for t in self.graphs() if t[0] == "paired")
        _, p3, c3 = next(t for t in self.graphs() if t[0] == "swapped-order")
        p2 = [list(map(float, p)) for p in p2]
        p3 = [list(map(float, p)) for p in p3]
        g2 = schedule(np.asarray(p2, float), {k: list(v) for k, v in c2.items()}, [], [])
        g3 = schedule(np.asarray(p3, float), {k: list(v) for k, v in c3.items()}, [], [])
        a2, _ = compile_native(g2, p2)
        a3, _ = compile_native(g3, p3)
        self.assertNotEqual(a2, a3)
        r2, _ = R.REFS["paired"]()
        r3, _ = R.REFS["swapped-order"]()
        self.assertNotEqual(r2, r3)

    def test_unsupported(self):
        pts = [[100, 0], [500, 200], [300, 100], [100, 700]]
        P = np.asarray(pts, float)

        def mk(pt, n1, n2, k1, v1, k2, v2, s1=(), s2=(), r1=False, r2=False, id1=1, id2=2):
            ch = {}
            for i in range(4):
                if i == pt:
                    continue
                ch[i] = [relation("Abs", i, list(X), value=float(P[i][0]), round=False, id=100 + 2 * i),
                         relation("Abs", i, list(Y), value=float(P[i][1]), round=False, id=101 + 2 * i)]
            ch[pt] = [relation(k1, pt, list(n1), sources=list(s1), value=v1, round=r1, id=id1),
                      relation(k2, pt, list(n2), sources=list(s2), value=v2, round=r2, id=id2)]
            return schedule(P, ch, [], [])

        with self.assertRaises(UnsupportedNativeTranslation):
            compile_native(mk(2, X, Y, "Abs", 9999.0, "Abs", 100.0), pts)
        with self.assertRaises(UnsupportedNativeTranslation):
            compile_native(mk(2, X, Y, "PAbs", 3.5, "Abs", 100.0), pts)
        with self.assertRaises(UnsupportedNativeTranslation):
            compile_native(mk(2, X, Y, "Dist", 1.0, "Abs", 100.0, s1=[0]), pts)
        with self.assertRaises(UnsupportedNativeTranslation):
            compile_native(mk(2, X, Y, "PRatio", 0.5, "Abs", 100.0, s1=[0, 1]), pts)
        with self.assertRaises(UnsupportedNativeTranslation):
            compile_native(mk(2, X, Y, "Ratio", 0.25, "Abs", 100.0, s1=[0, 1], r1=False), pts)
        g = mk(2, X, Y, "Abs", 300.0, "Abs", 100.0)
        bad = dict(g)
        bad["constraints"] = [dict(c, id=1) for c in bad["constraints"]]
        with self.assertRaises(UnsupportedNativeTranslation):
            compile_native(bad, pts)
        bad2 = dict(g)
        bad2["order"] = [0, 1, 2]
        with self.assertRaises(UnsupportedNativeTranslation):
            compile_native(bad2, pts)
        bad3 = dict(g)
        bad3["constraints"] = [dict(c) for c in bad3["constraints"]]
        bad3["constraints"][0] = dict(bad3["constraints"][0], point=9)
        with self.assertRaises(UnsupportedNativeTranslation):
            compile_native(bad3, pts)

    def test_near_parallel(self):
        pts = [[100, 0], [500, 200], [300, 100], [100, 700]]
        P = np.asarray(pts, float)

        def pair(second):
            ch = {}
            for i in range(4):
                if i == 2:
                    continue
                ch[i] = [relation("Abs", i, list(X), value=float(P[i][0]), round=False, id=100 + 2 * i),
                         relation("Abs", i, list(Y), value=float(P[i][1]), round=False, id=101 + 2 * i)]
            n = list(second)
            ch[2] = [relation("Abs", 2, list(X), value=float(P[2][0]), round=False, id=1),
                     relation("Abs", 2, n, value=float(P[2] @ np.asarray(n)), round=False, id=2)]
            return schedule(P, ch, [], [])

        n_reject = [0.99995, math.sqrt(1 - 0.99995 ** 2)]
        with self.assertRaises(UnsupportedNativeTranslation):
            compile_native(pair(n_reject), pts)
        n_ok = [0.95, math.sqrt(1 - 0.95 ** 2)]
        compile_native(pair(n_ok), pts)

    def test_malformed_graphs(self):
        pts = [[100, 0], [500, 200], [300, 100], [100, 700]]
        P = np.asarray(pts, float)

        def base():
            ch = {}
            for i in range(4):
                ch[i] = [relation("Abs", i, list(X), value=float(P[i][0]), round=False, id=100 + 2 * i),
                         relation("Abs", i, list(Y), value=float(P[i][1]), round=False, id=101 + 2 * i)]
            return schedule(P, ch, [], [])

        def mutated(index, **kw):
            g = base()
            cons = [dict(c) for c in g["constraints"]]
            cons[index] = dict(cons[index], **kw)
            return dict(g, constraints=cons)

        with self.assertRaises(UnsupportedNativeTranslation):
            compile_native(mutated(0, sources=None), pts)
        with self.assertRaises(UnsupportedNativeTranslation):
            compile_native(mutated(0, kind="NoSuchOp"), pts)
        with self.assertRaises(UnsupportedNativeTranslation):
            compile_native(mutated(0, point=2.5), pts)

    def test_immutable(self):
        _, pts, chosen = next(t for t in self.graphs() if t[0] == "source-round")
        pts = [list(map(float, p)) for p in pts]
        g = schedule(np.asarray(pts, float), {k: list(v) for k, v in chosen.items()}, [], [])
        sg, sp = copy.deepcopy(g), copy.deepcopy(pts)
        compile_native(g, pts)
        self.assertEqual(g, sg)
        self.assertEqual(pts, sp)

    def test_injected_ft_exception(self):
        with mock.patch.object(R, "run_ft_raw", side_effect=RuntimeError("injected FT boom")):
            with tempfile.TemporaryDirectory() as t:
                with self.assertRaises(SystemExit) as cm:
                    with redirect_stdout(io.StringIO()):
                        with mock.patch("sys.argv", ["prog", "--output", t + "/fresh"]):
                            R.main()
                self.assertNotEqual(cm.exception.code, 0)
                with open(t + "/fresh/report.json") as f:
                    rep = json.load(f)
                self.assertEqual(rep["actual_cases"], 40)
                self.assertEqual(rep["required_cases"], 40)
                self.assertTrue(rep["unexpected_errors"])
                self.assertFalse(rep["verification_passed"])

    def test_empty_outline_noop(self):
        for pts in ([], np.zeros((0, 2))):
            g = {"constraints": [], "order": []}
            sg = copy.deepcopy(g)
            sp = copy.deepcopy(
                pts if isinstance(pts, list) else np.asarray(pts).tolist())
            asm, meta = compile_native(
                g, pts if isinstance(pts, list) else np.zeros((0, 2)))
            self.assertEqual(asm, [])
            self.assertEqual(list(meta.get("cvt", None)), [])
            self.assertEqual(list(meta.get("operations", None)), [])
            self.assertTrue(meta.get("empty_outline"))
            self.assertIn("no-op", str(meta.get("status")))
            self.assertIn("hmtx", str(meta.get("status")))
            self.assertTrue(any("glyf" in str(s)
                                for s in meta.get("cited_sources", [])))
            self.assertEqual(g, sg)
            self.assertEqual(
                (pts if isinstance(pts, list)
                 else np.asarray(pts).tolist()), sp)

    def test_empty_outline_malformed_rejected(self):
        g = {"constraints": [], "order": []}
        for bad in (None, np.zeros((0, 3)), np.zeros((2, 0)),
                    [[0.0, 0.0], [1.0]],
                    [[float("inf"), 0.0]], [[float("nan"), 0.0]]):
            with self.assertRaises(UnsupportedNativeTranslation, msg=repr(bad)):
                compile_native(copy.deepcopy(g), bad)
        # Nonempty points with an empty graph are inconsistent.
        with self.assertRaises(UnsupportedNativeTranslation):
            compile_native(copy.deepcopy(g), [[0.0, 0.0]])

    def test_empty_outline_graph_mismatch_rejected(self):
        pts = []
        bad_order = {"constraints": [], "order": [0]}
        with self.assertRaises(UnsupportedNativeTranslation):
            compile_native(bad_order, pts)
        bad_cons = {"constraints": [{"id": 0, "point": 0, "kind": "Abs",
                                     "normal": [1, 0], "sources": [],
                                     "value": 0.0}],
                    "order": []}
        with self.assertRaises(UnsupportedNativeTranslation):
            compile_native(bad_cons, pts)

    def test_refuses_nonempty_output(self):
        with tempfile.TemporaryDirectory() as t:
            d = os.path.join(t, "out")
            os.mkdir(d)
            with open(os.path.join(d, "sentinel.txt"), "w") as f:
                f.write("x")
            with mock.patch("sys.argv", ["prog", "--output", d]):
                with self.assertRaises(SystemExit) as cm:
                    R.main()
            self.assertIn("refusing to overwrite", str(cm.exception.code))


if __name__ == "__main__":
    unittest.main()
