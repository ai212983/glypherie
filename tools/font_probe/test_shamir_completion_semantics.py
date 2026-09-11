"""Completion semantics for contour-local Ratio defaults (B08) plus native IP check.

Covers assembled/scheduled/evaluated behavior of
shamir_baseline_completion.complete_defaults, not just chosen metadata:
contour-locality, single/equal-span signed offsets, extrapolation (not an
IUP-style shift), oblique perpendicular completion, unrounded no-reference
Abs, and the separately-researched cycle fallback assumption (B11, original
projection + warning).

Microsoft-source note: ValidateInterpolee (lines 620-650) is COMMENTED OUT,
so there is no live child-range check; TTSourceGenerator::Interpolate
(652-684) emits IP with optional rounding and no live ValidateInterpolee.
The Shamir arbitrary-tie rule authorizes choosing constraint removal, NOT
an arbitrary original-position fallback; the cycle fallback here is a
separately researched project assumption, not a paper derivation.

Native IP test: FreeType executes TrueType IP here, not the Microsoft
rasterizer; this is not full VTT conformance. No installed VTT compiler is
required. No glyph-specific geometry correction; fixture char identity ok.
Expectations are hand-computed coordinates, never our Round/compile oracle.
Native source-point t is measured from the source outline before the move.
"""
import tempfile
import unittest
from pathlib import Path

import freetype as ft
import numpy as np
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates

from shamir_baseline_completion import complete_defaults
from shamir_baseline_solver import evaluate_baseline, resolve_baseline
from shamir_constraints import relation
from shamir_point_schedule import schedule
from test_shamir_prototype import fixture


def anchor(chosen, p, x, y):
    # Target-position anchors: refs are fitted destinations, never source.
    chosen.setdefault(p, []).append(
        relation('Abs', p, [1, 0], value=x, round=False, id=2 * p))
    chosen.setdefault(p, []).append(
        relation('Abs', p, [0, 1], value=y, round=False, id=2 * p + 1))


def solved(points, chosen, ref_targets, contours):
    # Points stay the SOURCE outline; refs move only via Abs TARGET anchors.
    points = np.asarray(points, float)
    for p, (x, y) in ref_targets.items():
        anchor(chosen, p, x, y)
    complete_defaults(points, chosen, list(ref_targets), 100, contours)
    rejected, warnings = [], []
    graph = schedule(points, chosen, rejected, warnings)
    fitted, _ = evaluate_baseline(graph, points, 1000, 1000)
    return fitted, graph, rejected, warnings


class CompletionSemanticsTests(unittest.TestCase):
    def test_contour_local_no_cross_component(self):
        # Refs 3,4 on contour [3,4] must not leak into contour [0,1,2].
        pts = [[0, 0], [5, 0], [10, 0], [0, 5], [10, 5]]
        refs = {0: (20, 0), 2: (10, 0), 3: (200, 5), 4: (300, 5)}
        fitted, graph, _, _ = solved(pts, {}, refs, [[0, 1, 2], [3, 4]])
        src = [c for c in graph['constraints'] if c['point'] == 1][0]
        self.assertEqual(src['sources'], [0, 2])
        self.assertAlmostEqual(src['value'], 0.5)
        # Original t=.5: (1-.5)*20 + .5*10 = 15; y Dist from ref 0 -> 0.
        self.assertAlmostEqual(fitted[1, 0], 15.0)
        self.assertAlmostEqual(fitted[1, 1], 0.0)

    def test_single_signed_offset(self):
        # Single ref: Dist keeps signed offset (-3): 10-3=7, y 4+0=4.
        fitted, graph, _, _ = solved([[0, 0], [-3, 0]], {}, {0: (10, 4)},
                                     [[0, 1]])
        dist = [c for c in graph['constraints'] if c['point'] == 1
                and np.allclose(c['normal'], [1, 0])][0]
        self.assertEqual((dist['kind'], dist['sources'], dist['value']),
                         ('Dist', [0], -3.0))
        self.assertAlmostEqual(fitted[1, 0], 7.0)
        self.assertAlmostEqual(fitted[1, 1], 4.0)

    def test_equal_span_signed_offset(self):
        # Refs project to same x (span 0): Dist keeps +4 -> 10+4=14.
        # y Ratio t=(1-0)/(9-0)=1/9: 0+t*9=1.
        pts = [[2, 0], [6, 1], [2, 9]]
        fitted, graph, _, _ = solved(pts, {}, {0: (10, 0), 2: (30, 9)},
                                     [[0, 1, 2]])
        dist = [c for c in graph['constraints'] if c['point'] == 1
                and np.allclose(c['normal'], [1, 0])][0]
        self.assertEqual((dist['kind'], dist['sources'], dist['value']),
                         ('Dist', [0], 4.0))
        self.assertAlmostEqual(fitted[1, 0], 14.0)
        self.assertAlmostEqual(fitted[1, 1], 1.0)

    def test_extrapolation_not_iup_shift(self):
        # Contour [1,0] order: sources [1,0], t=(15-10)/(0-10)=-.5.
        pts = [[0, 0], [10, 0], [15, 0]]
        chosen = {}
        fitted, graph, _, _ = solved(pts, chosen, {0: (0, 0), 1: (20, 0)},
                                     [[0, 1, 2]])
        ratio = [c for c in graph['constraints'] if c['point'] == 2
                 and np.allclose(c['normal'], [1, 0])][0]
        self.assertEqual(ratio['kind'], 'Ratio')
        self.assertEqual(ratio['sources'], [1, 0])
        self.assertAlmostEqual(ratio['value'], -0.5)
        # Assert the equation, not a hardcoded 1.5: (1-t)*20 + t*0 = 30.
        t = float(ratio['value'])
        self.assertAlmostEqual((1 - t) * 20.0 + t * 0.0, 30.0)
        self.assertAlmostEqual(fitted[2, 0], 30.0)

    def test_true_oblique_perpendicular_completion(self):
        # Existing oblique x-constraint kept (id 99); completion adds the
        # perpendicular Ratio. Refs anchored in both axes.
        import math
        n = [1 / math.sqrt(2), 1 / math.sqrt(2)]
        chosen = {1: [relation('Abs', 1, n, value=12 / math.sqrt(2),
                               round=False, id=99)]}
        pts = [[0, 0], [7, 5], [10, 0]]
        fitted, graph, _, _ = solved(pts, chosen, {0: (0, 0), 2: (20, 0)},
                                     [[0, 1, 2]])
        group = [c for c in graph['constraints'] if c['point'] == 1]
        self.assertEqual(len(group), 2)
        self.assertEqual(group[0]['id'], 99)
        np.testing.assert_allclose(group[0]['normal'], n)
        ratio = group[1]
        self.assertEqual(ratio['kind'], 'Ratio')
        # Perp source offset (-7+5)/s2 over (-10)/s2 -> t=.2.
        self.assertAlmostEqual(ratio['value'], 0.2)
        # -x+y=-4 combined with x+y=12 -> (8,4).
        self.assertAlmostEqual(fitted[1, 0], 8.0)
        self.assertAlmostEqual(fitted[1, 1], 4.0)

    def test_reduced_no_reference_original_unrounded(self):
        # True reduced path: resolve_baseline with no candidates, no refs.
        pts = [[0.5, 1.5], [2.5, 4.5]]
        graph = resolve_baseline(np.asarray(pts, float), [])
        for c in graph['constraints']:
            self.assertEqual(c['kind'], 'Abs')
        fitted, _ = evaluate_baseline(graph, np.asarray(pts, float),
                                      1000, 1000)
        np.testing.assert_allclose(fitted, pts)

    def test_cycle_fallback_original_projection_warn(self):
        # Whole-point cycle via resolve_baseline: Dist 0<-1 and 1<-0.
        pts = np.array([[0, 0], [10, 0]])
        graph = resolve_baseline(
            pts, [dict(kind='Dist', point=0, normal=[1, 0], sources=[1],
                       value=1.0, round=False),
                  dict(kind='Dist', point=1, normal=[1, 0], sources=[0],
                       value=1.0, round=False)])
        fb = [c for c in graph['constraints']
              if c.get('default_reason') == 'dependency cycle']
        self.assertEqual(len(fb), 1)
        self.assertEqual(fb[0]['kind'], 'Abs')
        self.assertAlmostEqual(fb[0]['value'],
                               float(pts[fb[0]['point']] @ np.array([1, 0])))
        self.assertTrue(any(w.get('kind') == 'cycle removed'
                            for w in graph.get('warnings', [])))
        fitted, _ = evaluate_baseline(graph, pts, 1000, 1000)
        self.assertAlmostEqual(fitted[1, 0], 10.0)
        self.assertAlmostEqual(fitted[0, 0], 11.0)
        self.assertAlmostEqual(fitted[0, 1], 0.0)
        self.assertAlmostEqual(fitted[1, 1], 0.0)


def run_ip_program(points, asm_x, asm_y):
    """Execute SCFS anchors + SRP1/SRP2/IP via FreeType; return 26.6 pts."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'ip.ttf'
        fixture(path)
        font = TTFont(path)
        g = font['glyf']['A']
        g.coordinates = GlyphCoordinates(points)
        font['hmtx'].metrics['A'] = (400, 100)  # lsb = source min-x
        prog_asm = (['SVTCA[1]'] + asm_x + ['SVTCA[0]'] + asm_y)
        from fontTools.ttLib.tables.ttProgram import Program
        g.program = Program()
        g.program.fromAssembly(prog_asm)
        font['maxp'].maxStackElements = 32
        font.save(path)
        asm_back = g.program.getAssembly()
        for op in ('SVTCA[1]', 'SCFS[ ]', 'SRP1[ ]', 'SRP2[ ]', 'IP[ ]'):
            self_op = op
            assert any(self_op.split('[')[0] in line for line in asm_back), \
                self_op
        before = (list(g.flags), list(g.endPtsOfContours))
        face = ft.Face(str(path))
        face.set_pixel_sizes(0, 125)  # em 1000 -> 1 font unit = 8 in 26.6
        face.load_char('A', ft.FT_LOAD_NO_BITMAP | ft.FT_LOAD_NO_AUTOHINT
                       | ft.FT_LOAD_TARGET_MONO | ft.FT_LOAD_PEDANTIC)
        return (np.asarray(face.glyph.outline.points).tolist(),
                list(face.glyph.outline.tags),
                list(face.glyph.outline.contours), before)


def scfs(point, value266):
    return ['PUSHW[ ]', str(point), 'PUSHW[ ]', str(value266), 'SCFS[ ]']


def ip_refs(rp1, rp2, target):
    return ['PUSHW[ ]', str(rp1), 'SRP1[ ]', 'PUSHW[ ]', str(rp2), 'SRP2[ ]',
            'PUSHW[ ]', str(target), 'IP[ ]']


def shamir_ratio(a, b, t):
    return (1 - t) * a + t * b


class NativeShamirRatioIPTests(unittest.TestCase):
    # Glyph: p0=(100,10) p1=(300,50) refs; p2=(200,30) inside (t=.5 both
    # axes); p3=(400,70) outside (t=1.5 both axes). 1 unit = 8 in 26.6.
    # t measured on the SOURCE outline before any move.
    POINTS = [(100, 10), (300, 50), (200, 30), (400, 70)]

    def check(self, asm_x, asm_y, exp):
        got, tags, contours, before = run_ip_program(self.POINTS, asm_x,
                                                      asm_y)
        # Low bit is on-curve; higher bits are FreeType touch state.
        self.assertTrue(all(t & 1 for t in tags))
        self.assertEqual(contours, [3])
        self.assertEqual(before, ([1] * 4, [3]))
        for i, (x, y) in exp.items():
            self.assertEqual(got[i], [x, y], f'point {i}')

    def test_cardinal_x_inside_outside_and_reversed(self):
        # Anchors: p0 x 100->0 (0 in 26.6), p1 x stays 300 (2400).
        # p2: t=(200-100)/200=.5 -> 1200. p3: t=1.5 -> 3600.
        anchor = scfs(0, 0) + scfs(1, 2400)
        self.check(anchor + ip_refs(0, 1, 2) + ip_refs(0, 1, 3),
                   scfs(0, 80) + scfs(1, 400),
                   {2: (1200, 240), 3: (3600, 560)})
        self.assertEqual(shamir_ratio(0, 2400, 0.5), 1200)
        self.assertEqual(shamir_ratio(0, 2400, 1.5), 3600)
        # Reversed refs give identical hand-computed positions.
        self.check(anchor + ip_refs(1, 0, 2) + ip_refs(1, 0, 3),
                   scfs(0, 80) + scfs(1, 400),
                   {2: (1200, 240), 3: (3600, 560)})

    def test_cardinal_y_inside_outside_and_reversed(self):
        # Anchors: p0 y 10->0 (0 in 26.6), p1 y stays 50 (400).
        # p2: t=(30-10)/40=.5 -> 200. p3: t=1.5 -> 600.
        anchor = scfs(0, 0) + scfs(1, 400)
        self.check(scfs(0, 800) + scfs(1, 2400),
                   anchor + ip_refs(0, 1, 2) + ip_refs(0, 1, 3),
                   {2: (1600, 200), 3: (3200, 600)})
        self.assertEqual(shamir_ratio(0, 400, 0.5), 200)
        self.assertEqual(shamir_ratio(0, 400, 1.5), 600)
        self.check(scfs(0, 800) + scfs(1, 2400),
                   anchor + ip_refs(1, 0, 2) + ip_refs(1, 0, 3),
                   {2: (1600, 200), 3: (3200, 600)})

    def test_both_refs_move(self):
        # Both refs move: p0 x 100->50 (400), p1 x 300->350 (2800).
        # p2: 400+.5*2400=1600. p3: 400+1.5*2400=4000.
        # y: p0 10->0 (0), p1 50->60 (480): p2: 0+.5*480=240,
        # p3: 0+1.5*480=720.
        self.check(scfs(0, 400) + scfs(1, 2800) + ip_refs(0, 1, 2)
                   + ip_refs(0, 1, 3),
                   scfs(0, 0) + scfs(1, 480) + ip_refs(0, 1, 2)
                   + ip_refs(0, 1, 3),
                   {0: (400, 0), 1: (2800, 480),
                    2: (1600, 240), 3: (4000, 720)})
        self.assertEqual(shamir_ratio(400, 2800, 0.5), 1600)
        self.assertEqual(shamir_ratio(400, 2800, 1.5), 4000)


if __name__ == '__main__':
    unittest.main()
