"""Independent equations and native adapter boundaries for the source-led profile."""
from pathlib import Path
import tempfile
import unittest
import freetype as ft
import numpy as np
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.ttLib.tables.ttProgram import Program
from shamir_constraints import relation
from shamir_baseline_solver import resolve_baseline, evaluate_baseline, compile_baseline
from test_shamir_prototype import fixture


class BaselineSolverTests(unittest.TestCase):
    def test_independent_near_parallel_lines_survive(self):
        n = np.array([1., .001]); n /= np.linalg.norm(n)
        cs = [relation('Abs', 0, [1,0], value=100, round=False),
              relation('Abs', 0, n, value=101, round=False)]
        graph = resolve_baseline([[0,0]], cs)
        self.assertEqual(graph['rejected'], [])
        fitted, _ = evaluate_baseline(graph, [[0,0]], 16, 1000)
        np.testing.assert_allclose(fitted[0] @ np.array([[1,0],n]).T, [1.6,1.616])
        self.assertGreater(fitted[0,1], 10)

    def test_parallel_rejected_but_metric_priority_preserved(self):
        graph = resolve_baseline([[0,0]], [relation('Abs',0,[1,0],value=10),
            relation('PAbs',0,[1,0],value=20,metric=True)])
        self.assertEqual(graph['rejected'][0]['constraint']['value'],10)
        fitted,_=evaluate_baseline(graph,[[0,0]],100,1000)
        self.assertEqual(fitted[0,0],2)

    def test_signed_rounding_zero_distance_and_original_ratio(self):
        points=[[0,0],[100,0],[25,0],[0,20]]
        cs=[relation('Abs',0,[1,0],value=-50),relation('Abs',1,[1,0],value=250),
            relation('Ratio',2,[1,0],[0,1],None),relation('Dist',3,[1,0],[0],0)]
        graph=resolve_baseline(points,cs)
        fitted,_=evaluate_baseline(graph,points,10,1000)
        np.testing.assert_allclose(fitted[:,0],[-1,3,0,-1])

    def test_explicit_signed_distances_and_ratio_parameters_are_equations(self):
        points=[[0,0],[100,0],[25,0],[50,0]]
        for kind in ('Dist','PDist'):
            graph=resolve_baseline(points,[relation('Abs',0,[1,0],value=200,round=False),
                relation(kind,1,[1,0],[0],-25,round=False)])
            fitted,_=evaluate_baseline(graph,points,20,1000)
            self.assertEqual(fitted[1,0],3.5)
        for kind in ('Ratio','PRatio'):
            graph=resolve_baseline(points,[relation('Abs',0,[1,0],value=0,round=False),
                relation('Abs',1,[1,0],value=100,round=False),
                relation(kind,2,[1,0],[0,1],1.5)])
            fitted,_=evaluate_baseline(graph,points,20,1000)
            self.assertEqual(fitted[2,0],3.)

    def test_cycle_removes_lowest_priority_participating_relation(self):
        graph=resolve_baseline([[0,0],[10,10]],[
            relation('Dist',0,[1,0],[1],-10),relation('PDist',1,[0,1],[0],10)])
        self.assertEqual([r['constraint']['id'] for r in graph['rejected']],[0])
        self.assertEqual(graph['order'],[0,1])
        evaluate_baseline(graph,[[0,0],[10,10]],16,1000)

    def test_unavailable_ratio_and_empty_outline_report_boundaries(self):
        graph=resolve_baseline([[0,0],[0,10],[5,5]],[],[0,1])
        self.assertTrue(any(c.get('default_reason')=='no distinct projected reference pair' for c in graph['constraints']))
        empty=resolve_baseline([],[])
        assembly,meta=compile_baseline(empty,[],16,1000)
        self.assertEqual(meta['native_points_px'],[])
        self.assertIn('IF[ ]',assembly)
        with self.assertRaisesRegex(ValueError,'signed32'):
            evaluate_baseline(resolve_baseline([[0,0]],[relation('Abs',0,[1,0],value=1e12)]),[[0,0]],16,1000)

    def test_native_cardinal_export_and_other_size_gate(self):
        points=[[100,0],[500,0],[500,700],[100,700]]
        n=np.array([1.,.001]);n/=np.linalg.norm(n)
        graph=resolve_baseline(points,[relation('Abs',0,[1,0],value=100,round=False),
            relation('Abs',0,n,value=100.03,round=False)])
        assembly,meta=compile_baseline(graph,points,16,1000)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'baseline.ttf';fixture(path);font=TTFont(path)
            g=font['glyf']['A'];g.coordinates=GlyphCoordinates(points);g.program=Program()
            g.program.fromAssembly(assembly);font['maxp'].maxStackElements=32;font.save(path)
            face=ft.Face(str(path));face.set_pixel_sizes(0,16)
            face.load_char('A',ft.FT_LOAD_NO_BITMAP|ft.FT_LOAD_NO_AUTOHINT|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_PEDANTIC)
            np.testing.assert_array_equal(np.asarray(face.glyph.outline.points)/64,meta['native_points_px'])
            face.set_pixel_sizes(0,18)
            face.load_char('A',ft.FT_LOAD_NO_BITMAP|ft.FT_LOAD_NO_AUTOHINT|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_PEDANTIC)
            hinted=np.asarray(face.glyph.outline.points)
            # Compare with an empty program under identical hinting flags:
            # disabling hinting also changes phantom-point bearing rounding.
            g.program.fromAssembly([]);font.save(path)
            plain=ft.Face(str(path));plain.set_pixel_sizes(0,18)
            plain.load_char('A',ft.FT_LOAD_NO_BITMAP|ft.FT_LOAD_NO_AUTOHINT|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_PEDANTIC)
            np.testing.assert_array_equal(hinted,plain.glyph.outline.points)

    def test_invalid_inputs_fail_explicitly(self):
        for cs in ([relation('Ratio',0,[1,0],[1],.2)],
                   [relation('Abs',0,[1,0],value=float('nan'))],
                   [relation('PRatio',0,[1,0],[1,2],float('inf'))]):
            with self.subTest(cs=cs),self.assertRaises(ValueError):
                resolve_baseline([[0,0],[1,1],[2,2]],cs)
        with self.assertRaises(ValueError):compile_baseline(resolve_baseline([],[]),[],1.5,1000)


class ExtentRoundingTests(unittest.TestCase):
    def test_y_extent_bounds_round_outward(self):
        # Roboto-16 I: cap 1456u = 11.375px. Native bytecode rounds the top
        # to 12, keeping 12 raster rows; nearest would give 11.
        pts = [[376,1456],[376,0]]
        cs = [relation('Abs',1,[0,1],value=0,metric=True,metric_role='glyph-y-bound'),
              relation('Dist',0,[0,1],[1],1456,metric=True,metric_role='glyph-y-bound'),
              relation('Abs',0,[1,0],value=376,round=False),
              relation('Abs',1,[1,0],value=376,round=False)]
        fitted, _ = evaluate_baseline(resolve_baseline(pts,cs),pts,16,2048)
        self.assertEqual(fitted[1,1],0.0)
        self.assertEqual(fitted[0,1],12.0)

    def test_interior_y_keeps_nearest(self):
        pts = [[376,1456],[376,0]]
        cs = [relation('Abs',1,[0,1],value=0,round=False),
              relation('Dist',0,[0,1],[1],1456),
              relation('Abs',0,[1,0],value=376,round=False),
              relation('Abs',1,[1,0],value=376,round=False)]
        fitted, _ = evaluate_baseline(resolve_baseline(pts,cs),pts,16,2048)
        self.assertEqual(fitted[0,1],11.0)

    def test_thin_stem_up_exception(self):
        # 93u horizontal @16px/1000em = 1.488px (frac .488, in the
        # up-band) ceils to 2px; the exception class gate keeps the
        # settled 62u bracket member (1.116px @18px) at 1px.
        from shamir_baseline_solver import _thin_stem_up
        self.assertTrue(_thin_stem_up(93, [1, 0], 1.488))
        self.assertTrue(_thin_stem_up(93.0, [-1, 0], 1.488))
        self.assertFalse(_thin_stem_up(62, [1, 0], 1.116))
        self.assertFalse(_thin_stem_up(93, [1, 0], 1.302))
        self.assertFalse(_thin_stem_up(93, [1, 0], 1.674))
        self.assertFalse(_thin_stem_up(92, [1, 0], 1.472))
        self.assertFalse(_thin_stem_up(93, [0, 1], 1.488))
        self.assertFalse(_thin_stem_up(93, None, 1.488))

    def test_thin_stem_up_moves_dist_rhs(self):
        # End to end through evaluate_baseline: the 93u arch-side
        # fixture resolves 2px, the 62u bracket fixture stays 1px.
        for value, size, want in ((93, 16, 2.0), (62, 18, 1.0)):
            pts = [[value, 0], [0, 0]]
            cs = [relation('Abs', 1, [0, 1], value=0, round=False),
                  relation('Dist', 0, [1, 0], [1], value),
                  relation('Abs', 0, [0, 1], value=0, round=False),
                  relation('Abs', 1, [1, 0], value=0, round=False)]
            fitted, _ = evaluate_baseline(
                resolve_baseline(pts, cs), pts, size, 1000)
            self.assertEqual(fitted[0, 0], want)

    def test_metric_bound_max_rounds_nearest(self):
        # literata-16 h/l ascender bound (766u = 12.256px at
        # 16px/1000em): metric-inferred maxima take the
        # SROUND-threshold-5/8 cutpoint (12), while an explicit
        # extent flag keeps the outward ceiling (13).
        for extra, want in (({}, 12.0), ({'extent': 'max'}, 13.0)):
            pts = [[0, 766], [0, 0]]
            cs = [relation('PAbs', 1, [0, 1], value=0, extent='min'),
                  relation('Dist', 0, [0, 1], [1], 766, metric=True,
                           metric_role='glyph-y-bound', **extra),
                  relation('Abs', 0, [1, 0], value=0, round=False),
                  relation('Abs', 1, [1, 0], value=0, round=False)]
            fitted, _ = evaluate_baseline(
                resolve_baseline(pts, cs), pts, 16, 1000)
            self.assertEqual(fitted[0, 1], want)

    def test_sround_58_cutpoint(self):
        # Up iff the fraction reaches 3/8: the I-cap pin
        # (11.375) rounds up, the h/l bound (12.256) down.
        from shamir_baseline_solver import _sround_58
        self.assertEqual(_sround_58(11.375), 12.0)
        self.assertEqual(_sround_58(12.256), 12.0)
        self.assertEqual(_sround_58(1.374), 1.0)
        self.assertEqual(_sround_58(1.375), 2.0)
        self.assertEqual(_sround_58(8.336), 8.0)

    def test_extent_flag_directions(self):
        # Shared rows carry min/max explicitly instead of metric roles.
        pts = [[376,1456],[376,0]]
        cs = [relation('PAbs',1,[0,1],value=0,extent='min'),
              relation('PDist',0,[0,1],[1],1456,extent='max'),
              relation('Abs',0,[1,0],value=376,round=False),
              relation('Abs',1,[1,0],value=376,round=False)]
        fitted, _ = evaluate_baseline(resolve_baseline(pts,cs),pts,16,2048)
        self.assertEqual(fitted[1,1],0.0)
        self.assertEqual(fitted[0,1],12.0)

    def test_sub_baseline_overshoot_suppressed(self):
        # Roboto-14 '0': bottom overshoot -20u = -0.137px. Flooring
        # adds a raster row native hinting never renders; nearest
        # snaps it to the zone edge (0). Native bottom is exactly 0.
        pts = [[376,0],[376,-20]]
        cs = [relation('PAbs',1,[0,1],value=-20,extent='min'),
              relation('Abs',1,[1,0],value=376,round=False),
              relation('Abs',0,[1,0],value=376,round=False)]
        fitted, _ = evaluate_baseline(resolve_baseline(pts,cs),pts,14,2048)
        self.assertEqual(fitted[1,1],0.0)

    def test_reversed_extent_falls_back_to_nearest(self):
        # Ablation pin for the orient non-reversal ban: a forced
        # reversed extent row cannot keep outward sense (it would
        # determine the opposite end), so the solver falls back to
        # nearest (11, not the outward 12). orient must stall
        # rather than emit such a row (see
        # test_rounded_extent_dist_never_reverses).
        from shamir_baseline_solver import _dist_rhs, abs_row_map
        cs = [relation('Abs', 0, [1, 0], value=0),
              relation('Abs', 0, [0, 1], value=0),
              relation('Abs', 1, [1, 0], value=5),
              relation('Dist', 0, [0, 1], [1], 11.375,
                       metric_role='glyph-y-bound')]
        rev = dict(cs[3], point=1, sources=[0], value=-11.375,
                   reversed=True)
        abs_rows = abs_row_map([c for c in cs if c['kind'] == 'Abs'])
        self.assertEqual(_dist_rhs(rev, 1.0, abs_rows), -11.0)

    def test_positive_minimum_keeps_floor(self):
        # Features floating above the baseline keep legacy flooring.
        pts = [[376,80],[376,0]]
        cs = [relation('PAbs',1,[0,1],value=80,extent='min'),
              relation('Abs',1,[1,0],value=376,round=False),
              relation('Abs',0,[1,0],value=376,round=False)]
        fitted, _ = evaluate_baseline(resolve_baseline(pts,cs),pts,14,2048)
        self.assertEqual(fitted[1,1],0.0)


if __name__=='__main__':unittest.main()
