"""Tests for the independent cardinal native dependency reference.

Unit scope: malformed/rejected domain, signed rounding ties, source
scaled differences vs rounded originals, original-ratio vs rounded
ratios, multi-hop fractional parent propagation, and the exact native
matrix (reference vs actual FreeType over every fixture x ppem).
Independent hardcoded control values throughout; a deliberate mutant
parent-snapping oracle must fail at least one fractional fixture.
Run: OPENBLAS_NUM_THREADS=1 .venv/bin/python -m unittest
test_native_dependency_reference -v (from tools/font_probe).
"""
import unittest
from pathlib import Path

import shamir_native_dependency_reference as ref
from shamir_native_dependency_reference import ReferenceError

PPEMS = [14, 16, 18, 20, 125, 1000]
SCALE14 = 58720  # FT_DivFix(14*64, 1000)


def cg(cid, point, kind, normal, sources=(), value=0.0, rnd=None):
    c = dict(id=cid, point=point, kind=kind, normal=list(normal),
             sources=list(sources), value=value)
    if rnd is not None:
        c["round"] = rnd
    return c


def graph2(second):
    return dict(order=[0, 1], constraints=[
        cg(1, 0, "PAbs", [1.0, 0.0], value=0, rnd=True),
        cg(2, 0, "Abs", [0.0, 1.0], value=0.0, rnd=False),
    ] + second)


class DomainTest(unittest.TestCase):
    def test_pratio_rejected(self):
        g = graph2([cg(3, 1, "PRatio", [1.0, 0.0], sources=[0], value=0.5, rnd=False),
                    cg(4, 1, "Abs", [0.0, 1.0], value=0.0, rnd=False)])
        with self.assertRaises(ReferenceError):
            ref.run(g, [[0, 0], [10, 0]], 14)

    def test_oblique_rejected(self):
        g = graph2([cg(3, 1, "PAbs", [0.6, 0.8], value=10, rnd=True),
                    cg(4, 1, "Abs", [0.0, 1.0], value=0.0, rnd=False)])
        with self.assertRaises(ReferenceError):
            ref.run(g, [[0, 0], [10, 0]], 14)

    def test_negative_cardinal_rejected(self):
        g = graph2([cg(3, 1, "PAbs", [-1.0, 0.0], value=10, rnd=True),
                    cg(4, 1, "Abs", [0.0, 1.0], value=0.0, rnd=False)])
        with self.assertRaises(ReferenceError):
            ref.run(g, [[0, 0], [10, 0]], 14)

    def test_duplicate_ids(self):
        g = graph2([cg(1, 1, "PAbs", [1.0, 0.0], value=10, rnd=True),
                    cg(4, 1, "Abs", [0.0, 1.0], value=0.0, rnd=False)])
        with self.assertRaises(ReferenceError):
            ref.run(g, [[0, 0], [10, 0]], 14)

    def test_bad_order(self):
        g = dict(order=[1, 1], constraints=graph2(
            [cg(3, 1, "PAbs", [1.0, 0.0], value=10, rnd=True),
             cg(4, 1, "Abs", [0.0, 1.0], value=0.0, rnd=False)])["constraints"])
        with self.assertRaises(ReferenceError):
            ref.run(g, [[0, 0], [10, 0]], 14)

    def test_source_after_target(self):
        g = dict(order=[0, 1], constraints=[
            cg(1, 0, "Dist", [1.0, 0.0], sources=[1], value=0.0, rnd=False),
            cg(2, 0, "Abs", [0.0, 1.0], value=0.0, rnd=False),
            cg(3, 1, "PAbs", [1.0, 0.0], value=10, rnd=True),
            cg(4, 1, "Abs", [0.0, 1.0], value=0.0, rnd=False)])
        with self.assertRaises(ReferenceError):
            ref.run(g, [[0, 0], [10, 0]], 14)

    def test_source_out_of_range(self):
        g = graph2([cg(3, 1, "Dist", [1.0, 0.0], sources=[7], value=0.0, rnd=False),
                    cg(4, 1, "Abs", [0.0, 1.0], value=0.0, rnd=False)])
        with self.assertRaises(ReferenceError):
            ref.run(g, [[0, 0], [10, 0]], 14)

    def test_fractional_fu_rejected(self):
        g = graph2([cg(3, 1, "PAbs", [1.0, 0.0], value=10, rnd=True),
                    cg(4, 1, "Abs", [0.0, 1.0], value=0.0, rnd=False)])
        with self.assertRaises(ReferenceError):
            ref.run(g, [[0, 0], [10.5, 0]], 14)

    def test_nonfinite_value(self):
        g = graph2([cg(3, 1, "PAbs", [1.0, 0.0], value=float("inf"), rnd=True),
                    cg(4, 1, "Abs", [0.0, 1.0], value=0.0, rnd=False)])
        with self.assertRaises(ReferenceError):
            ref.run(g, [[0, 0], [10, 0]], 14)

    def test_dist_not_source_derived(self):
        g = graph2([cg(3, 1, "Dist", [1.0, 0.0], sources=[0], value=4.0, rnd=False),
                    cg(4, 1, "Abs", [0.0, 1.0], value=0.0, rnd=False)])
        with self.assertRaises(ReferenceError):
            ref.run(g, [[0, 0], [10, 0]], 14)

    def test_abs_not_source_derived(self):
        g = graph2([cg(3, 1, "Abs", [1.0, 0.0], value=11.0, rnd=False),
                    cg(4, 1, "Abs", [0.0, 1.0], value=0.0, rnd=False)])
        with self.assertRaises(ReferenceError):
            ref.run(g, [[0, 0], [10, 0]], 14)

    def test_rounded_ratio_rejected(self):
        g = dict(order=[0, 1, 2], constraints=[
            cg(1, 0, "PAbs", [1.0, 0.0], value=0, rnd=True),
            cg(2, 0, "Abs", [0.0, 1.0], value=0.0, rnd=False),
            cg(3, 1, "PAbs", [1.0, 0.0], value=300, rnd=True),
            cg(4, 1, "Abs", [0.0, 1.0], value=0.0, rnd=False),
            cg(5, 2, "Ratio", [1.0, 0.0], sources=[0, 1],
               value=100.0 / 300.0, rnd=True),
            cg(6, 2, "Abs", [0.0, 1.0], value=0.0, rnd=False)])
        with self.assertRaises(ReferenceError):
            ref.run(g, [[0, 0], [300, 0], [100, 0]], 14)

    def test_degenerate_ratio_span(self):
        g = dict(order=[0, 1, 2], constraints=[
            cg(1, 0, "PAbs", [1.0, 0.0], value=50, rnd=True),
            cg(2, 0, "Abs", [0.0, 1.0], value=0.0, rnd=False),
            cg(3, 1, "PAbs", [1.0, 0.0], value=50, rnd=True),
            cg(4, 1, "Abs", [0.0, 1.0], value=0.0, rnd=False),
            cg(5, 2, "Ratio", [1.0, 0.0], sources=[0, 1], value=0.0, rnd=False),
            cg(6, 2, "Abs", [0.0, 1.0], value=0.0, rnd=False)])
        with self.assertRaises(ReferenceError):
            ref.run(g, [[50, 0], [50, 0], [50, 0]], 14)

    def test_pdist_fractional_cvt_rejected(self):
        g = graph2([cg(3, 1, "PDist", [1.0, 0.0], sources=[0], value=2.5, rnd=True),
                    cg(4, 1, "Abs", [0.0, 1.0], value=0.0, rnd=False)])
        with self.assertRaises(ReferenceError):
            ref.run(g, [[0, 0], [10, 0]], 14)

    def test_missing_axis(self):
        g = graph2([cg(3, 1, "PAbs", [1.0, 0.0], value=10, rnd=True),
                    cg(4, 1, "PAbs", [1.0, 0.0], value=12, rnd=True)])
        with self.assertRaises(ReferenceError):
            ref.run(g, [[0, 0], [10, 0]], 14)

    def test_ppem_range(self):
        g = graph2([cg(3, 1, "PAbs", [1.0, 0.0], value=10, rnd=True),
                    cg(4, 1, "Abs", [0.0, 1.0], value=0.0, rnd=False)])
        for bad in (0, 1001, 14.5, True):
            with self.assertRaises(ReferenceError):
                ref.run(g, [[0, 0], [10, 0]], bad)

    def test_no_forbidden_imports(self):
        src = Path(__file__).resolve().parent.joinpath(
            "shamir_native_dependency_reference.py").read_text()
        for mod in ("shamir_native_translation", "shamir_baseline_solver",
                    "compare_native", "numpy", "freetype", "fontTools"):
            self.assertNotIn("import %s" % mod, src)


class RoundingTest(unittest.TestCase):
    def test_half_away_ties(self):
        self.assertEqual(ref.round_to_grid(32), 64)
        self.assertEqual(ref.round_to_grid(-32), -64)
        self.assertEqual(ref.round_to_grid(31), 0)
        self.assertEqual(ref.round_to_grid(-31), 0)
        self.assertEqual(ref.round_to_grid(0), 0)
        self.assertEqual(ref.round_to_grid(96), 128)
        self.assertEqual(ref.round_to_grid(-96), -128)
        self.assertEqual(ref.round_to_grid(90), 64)
        self.assertEqual(ref.round_to_grid(269), 256)

    def test_signed_fix_ties(self):
        self.assertEqual(ref.muldiv(1, 1, 2), 1)
        self.assertEqual(ref.muldiv(-1, 1, 2), -1)
        self.assertEqual(ref.muldiv(1, 1, -2), -1)
        self.assertEqual(ref.divfix(1, 2), 32768)
        self.assertEqual(ref.divfix(-1, 2), -32768)
        self.assertEqual(ref.mulfix(1, 32768), 1)
        self.assertEqual(ref.mulfix(-1, 32768), -1)
        self.assertEqual(ref.initial_scale(14), SCALE14)
        self.assertEqual(ref.scale_fu(100, SCALE14), 90)
        self.assertEqual(ref.scale_fu(300, SCALE14), 269)
        self.assertEqual(ref.scale_fu(-4, 524288), -32)


class NativeMatrixTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import numpy as np
        from compare_native_sequences import fixtures as seq_fixtures
        from experiment_native_dependencies import chain_fixtures
        from shamir_native_translation import compile_native
        from shamir_point_schedule import schedule
        cls.items = []
        for key, pts, chosen in list(seq_fixtures()) + list(chain_fixtures()):
            pts = [list(map(float, p)) for p in pts]
            if any(list(c["normal"]) not in ([1.0, 0.0], [0.0, 1.0])
                   for group in chosen.values() for c in group):
                continue
            graph = schedule(np.asarray(pts, float),
                             {k: list(v) for k, v in chosen.items()}, [], [])
            nasm, nmeta = compile_native(graph, pts)
            cls.items.append((key, pts, graph, nasm, list(nmeta["cvt"])))
        assert len(cls.items) == 9, len(cls.items)

    def test_noop_baseline_is_initial(self):
        from compare_native_translation import run_ft_raw
        for key, pts, graph, nasm, cvt in self.items:
            for ppem in PPEMS:
                pred = ref.run(graph, pts, ppem)
                eraw, _, _ = run_ft_raw(pts, [], ppem, cvt or [0])
                self.assertEqual([list(map(int, p)) for p in eraw.tolist()],
                                 pred["initial"], (key, ppem))

    def test_exact_matrix(self):
        from compare_native_translation import run_ft_raw
        for key, pts, graph, nasm, cvt in self.items:
            for ppem in PPEMS:
                pred = ref.run(graph, pts, ppem)
                fraw, _, _ = run_ft_raw(pts, nasm, ppem, cvt or [0])
                self.assertEqual([list(map(int, p)) for p in fraw.tolist()],
                                 pred["final"], (key, ppem))

    def test_thirds_chain_x_controls(self):
        item = [i for i in self.items if i[0] == "thirds-chain-x"][0]
        _, pts, graph, _, _ = item
        pred = ref.run(graph, pts, 14)
        self.assertEqual(pred["initial"][2], [90, 0])
        self.assertEqual(pred["final"],
                         [[0, 0], [256, 0], [85, 0], [85, 45], [149, 45],
                          [117, 45]])

    def test_scaled_once_vs_rounded_originals(self):
        # FU 5->4, ppem 14: MulFix(1) = 1 but init(5)-init(4) = 4-4 = 0.
        g = graph2([cg(3, 1, "PAbs", [1.0, 0.0], value=4, rnd=True),
                    cg(4, 1, "Abs", [0.0, 1.0], value=0.0, rnd=False)])
        pts = [[5, 0], [4, 0]]
        pred = ref.run(g, pts, 14)
        self.assertEqual(pred["initial"], [[4, 0], [4, 0]])
        g2 = dict(order=[0, 1], constraints=[
            cg(1, 0, "PAbs", [1.0, 0.0], value=5, rnd=False),
            cg(2, 0, "Abs", [0.0, 1.0], value=0.0, rnd=False),
            cg(3, 1, "Dist", [1.0, 0.0], sources=[0], value=-1.0, rnd=False),
            cg(4, 1, "Abs", [0.0, 1.0], value=0.0, rnd=False)])
        pred2 = ref.run(g2, pts, 14)
        self.assertEqual(pred2["final"][1][0], 3)  # scaled-once, not 4
        from compare_native_translation import run_ft_raw
        from shamir_native_translation import compile_native
        import numpy as np
        from shamir_point_schedule import schedule
        graph = schedule(np.asarray(pts, float),
                         {0: [dict(c) for c in g2["constraints"] if c["point"] == 0],
                          1: [dict(c) for c in g2["constraints"] if c["point"] == 1]},
                         [], [])
        nasm, nmeta = compile_native(graph, pts)
        fraw, _, _ = run_ft_raw(pts, nasm, 14, list(nmeta["cvt"]) or [0])
        self.assertEqual(int(fraw.tolist()[1][0]), 3)

    def test_original_ratio_vs_rounded_ratio(self):
        # thirds-chain-x ppem 14 P2: source t = 100/300, but rounded
        # originals give 90/269; native IP follows the source interval.
        item = [i for i in self.items if i[0] == "thirds-chain-x"][0]
        _, pts, graph, nasm, cvt = item
        from compare_native_translation import run_ft_raw
        fraw, _, _ = run_ft_raw(pts, nasm, 14, cvt or [0])
        self.assertEqual(int(fraw.tolist()[2][0]), 85)
        naive = round((90.0 / 269.0) * 256.0)
        self.assertNotEqual(naive, 85)

    def test_export_only_parent_rounding_is_distinct(self):
        # Source IP ratio 1/3 followed by 20x extrapolation. Keeping 1/3
        # until export predicts 427; consuming the native parent predicts 420.
        from fractions import Fraction
        from compare_native_translation import run_ft_raw
        from shamir_native_translation import compile_native
        points = [[0, 0], [3, 0], [1, 0], [20, 0]]
        graph = dict(order=[0, 1, 2, 3], constraints=[])
        for p in range(4):
            if p < 2:
                c = cg(2*p, p, "PAbs", [1, 0], value=p, rnd=False)
            else:
                c = cg(2*p, p, "Ratio", [1, 0],
                       sources=[0, 1] if p == 2 else [0, 2],
                       value=1/3 if p == 2 else 20, rnd=False)
            graph["constraints"].extend([c,
                cg(2*p+1, p, "Abs", [0, 1], value=0, rnd=False)])
        pred = ref.run(graph, points, 1000)
        asm, meta = compile_native(graph, points)
        raw, _, _ = run_ft_raw(points, asm, 1000, meta["cvt"])
        self.assertEqual(raw.tolist(), pred["final"])
        self.assertEqual(pred["final"][2][0], 21)
        self.assertEqual(pred["final"][3][0], 420)
        ideal = Fraction(20 * 64, 3)
        export_only = (2 * ideal.numerator + ideal.denominator) // (2 * ideal.denominator)
        self.assertEqual(export_only, 427)
        self.assertNotEqual(pred["final"][3][0], export_only)

    def test_mutant_parent_snapping_fails(self):
        # Mutant oracle: snap every consumed parent current coordinate to
        # the pixel grid. Must disagree with native on a fractional chain.
        item = [i for i in self.items if i[0] == "thirds-chain-x"][0]
        _, pts, graph, nasm, cvt = item
        from compare_native_translation import run_ft_raw
        fraw, _, _ = run_ft_raw(pts, nasm, 14, cvt or [0])
        native = [list(map(int, p)) for p in fraw.tolist()]
        pred = ref.run(graph, pts, 14)
        snapped = [list(p) for p in pred["initial"]]
        fu = [[int(v) for v in p] for p in pts]
        org = [list(p) for p in pred["initial"]]
        scale = pred["scale"]
        cur = [list(p) for p in pred["initial"]]
        for step in pred["steps"]:
            p, ax = step["point"], step["axis"]
            kind = step["kind"]
            pc = (lambda q: ref.round_to_grid(cur[q][ax]))
            if kind == "Abs":
                cur[p][ax] = (ref.round_to_grid(cur[p][ax]) if step["round"]
                              else cur[p][ax])
            elif kind == "PAbs":
                target = ref.scale_fu(
                    next(c["value"] for c in graph["constraints"]
                         if c["id"] == step["constraint_id"]), scale)
                target = int(target)
                if step["round"]:
                    if abs(target - cur[p][ax]) > ref.CUTIN:
                        target = cur[p][ax]
                    target = ref.round_to_grid(target)
                cur[p][ax] = target
            elif kind == "Dist":
                s = step["sources"][0]
                if step["value"] == 0.0 and fu[p][ax] == fu[s][ax]:
                    cur[p][ax] = pc(s)
                else:
                    d = ref.scale_fu(fu[p][ax] - fu[s][ax], scale)
                    if step["round"]:
                        d = ref.round_to_grid(d)
                    cur[p][ax] = pc(s) + d
            elif kind == "PDist":
                s = step["sources"][0]
                target = ref.scale_fu(
                    next(c["value"] for c in graph["constraints"]
                         if c["id"] == step["constraint_id"]), scale)
                target = int(target)
                od = org[p][ax] - org[s][ax]
                if step["round"]:
                    if abs(target - od) > ref.CUTIN:
                        target = od
                    target = ref.round_to_grid(target)
                cur[p][ax] = cur[p][ax] + (target - (cur[p][ax] - pc(s)))
            elif kind == "Ratio":
                a, b = step["sources"]
                old = fu[b][ax] - fu[a][ax]
                og = fu[p][ax] - fu[a][ax]
                cr = pc(b) - pc(a)
                cd = cur[p][ax] - pc(a)
                new = 0 if og == 0 else (og if old == 0
                                        else ref.muldiv(og, cr, old))
                cur[p][ax] = cur[p][ax] + (new - cd)
        self.assertNotEqual(cur, native)


if __name__ == "__main__":
    unittest.main()
