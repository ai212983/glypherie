import unittest
import numpy as np

from shamir_constraints import relation
from shamir_baseline_solver import evaluate_baseline
from shamir_reorientation import Unsupported, orient, prototype, projected_anchors
from test_shamir_segment_conflicts import fixture


class ReorientationTests(unittest.TestCase):
    def test_h_chain_preserves_all_members_and_both_widths(self):
        result = prototype(fixture())
        self.assertEqual(result['removed']['feature'], 'inner')
        self.assertTrue(result['reversed_equations'])
        self.assertLess(result['max_retained_residual_px'], 1e-12)
        self.assertTrue(np.allclose(result['graph']['baseline_execution']['model_points_px'],
                                    [[1, 0], [8, 0], [9, 0], [9, 0]]))

    def test_reverse_signed_half_pixel_keeps_equation(self):
        for value in (.5, -.5, 1.5, -1.5):
            cs = [relation('Abs', 1, [1, 0], value=4),
                  relation('Abs', 1, [0, 1], value=0),
                  relation('PDist', 1, [1, 0], [0], value),
                  relation('Dist', 0, [0, 1], [1], .25, round=False)]
            graph = orient(cs, 2)
            fitted, _ = evaluate_baseline(graph, np.zeros((2, 2)), 1, 1)
            rounded = np.copysign(np.floor(abs(value)+.5), value)
            self.assertAlmostEqual(fitted[0, 0], 4-rounded)
            self.assertAlmostEqual(fitted[0, 1], .25)
            self.assertTrue(any(c['reversed'] and c['kind']=='PDist' for c in graph['constraints']))

    def test_scalar_solvable_whole_point_cycle_is_reported(self):
        cs = [relation('Abs', 0, [1, 0], value=0),
              relation('Dist', 0, [0, 1], [1], 1),
              relation('Abs', 1, [0, 1], value=0),
              relation('Dist', 1, [1, 0], [0], 1)]
        with self.assertRaisesRegex(Unsupported, 'stalled'):
            orient(cs, 2)

    def test_point_renumbering_keeps_fixture_coordinates(self):
        original = fixture()
        for perm in ([3, 2, 1, 0], [1, 3, 0, 2]):
            r = fixture()
            cs = r['graph']['constraints'] + [a['constraint'] for a in r['attachment_resolution']]
            for c in cs:
                c['point'] = perm[c['point']]; c['sources'] = [perm[s] for s in c['sources']]
            fitted = prototype(r)['graph']['baseline_execution']['model_points_px']
            expected = prototype(original)['graph']['baseline_execution']['model_points_px']
            self.assertTrue(np.allclose([fitted[i] for i in perm], expected))

    def test_multiple_conflicts_remain_unsupported(self):
        r = fixture()
        r['graph']['constraints'].append(relation('Abs', 0, [0, 1], value=3))
        with self.assertRaisesRegex(Unsupported, 'single repair'):
            prototype(r)

    def test_frozen_ratio_completes_missing_coordinate(self):
        r = fixture()
        r['graph']['constraints'] = [c for c in r['graph']['constraints']
                                    if not (c['point']==3 and c['normal']==[0., 1.])]
        r['graph']['constraints'].append(relation('Ratio', 3, [0, 1], [0, 1], .5,
                                                 default=True, round=False))
        result = prototype(r)
        self.assertEqual(len(result['restored_defaults']), 1)
        self.assertEqual(result['restored_defaults'][0]['kind'], 'Ratio')
        self.assertLess(result['max_retained_residual_px'], 1e-12)

    def test_conflicting_frozen_completion_is_rejected(self):
        r = fixture()
        r['graph']['constraints'] = [c for c in r['graph']['constraints']
                                    if not (c['point']==3 and c['normal']==[0., 1.])]
        r['graph']['constraints'].extend([
            relation('Abs', 3, [0, 1], value=0, default=True),
            relation('Abs', 0, [1, 0], value=99, default=True)])
        with self.assertRaisesRegex(Unsupported, 'frozen defaults'):
            prototype(r)

    def test_substitution_rounds_each_distance_before_summing(self):
        cs = [relation('Abs', 0, [1, 0], value=.5),
              relation('Dist', 1, [1, 0], [0], .5),
              relation('Dist', 2, [-1, 0], [1], -.5)]
        result = projected_anchors(cs, 1)
        end, = [c for c in result if c['point']==2]
        self.assertEqual(end['value'], 3)
        self.assertEqual(end['derived_from'], [0, 1, 2])
        self.assertFalse(end['round'])

    def test_substitution_does_not_merge_near_parallel_directions(self):
        cs = [relation('Abs', 0, [1, 0], value=1),
              relation('Dist', 1, [1, .00001], [0], 1)]
        self.assertEqual(projected_anchors(cs, 1), [])

    def test_substitution_resolves_partial_coordinate_cycle(self):
        cs = [relation('Abs', 0, [1, 0], value=0),
              relation('Dist', 0, [0, 1], [1], 1),
              relation('Abs', 1, [0, 1], value=0),
              relation('Dist', 1, [1, 0], [0], 1)]
        graph = orient(cs+projected_anchors(cs, 1), 2)
        fitted, _ = evaluate_baseline(graph, np.zeros((2, 2)), 1, 1)
        self.assertTrue(np.allclose(fitted, [[0, 1], [1, 0]]))


if __name__ == '__main__':
    unittest.main()
