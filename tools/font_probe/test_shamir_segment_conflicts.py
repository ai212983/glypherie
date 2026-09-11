import unittest

from audit_shamir_segment_conflicts import diagnose, equations, solve
from shamir_constraints import relation


def fixture():
    # Left anchor, inner edge, outer representative and another outer member.
    cs = [relation('Abs', 0, [1, 0], value=1, metric=True),
          relation('Abs', 1, [1, 0], value=7, feature='inner'),
          relation('PDist', 2, [1, 0], [1], 1, feature='width'),
          relation('Dist', 3, [1, 0], [0], 8, metric=True)]
    cs += [relation('Abs', i, [0, 1], value=0) for i in range(4)]
    member = relation('Dist', 3, [1, 0], [2], 0, round=False, feature='align-outer')
    return dict(graph=dict(constraints=cs, baseline_execution=dict(
        ppem=1, em=1, model_points_px=[[0, 0]]*4)),
        attachment_resolution=[dict(constraint=member, status='rejected')])


class SegmentConflictTests(unittest.TestCase):
    def test_releasing_inner_anchor_preserves_metrics_and_width(self):
        d = diagnose(fixture())
        self.assertFalse(d['full_system']['consistent'])
        self.assertEqual(len(d['single_semantic_removals']), 4)
        best, = d['lowest_priority_removals']
        self.assertEqual(best['removed']['feature'], 'inner')
        self.assertTrue(best['solution']['unique'])
        for p, x in zip(best['solution']['points_px'], [1, 8, 9, 9]):
            self.assertAlmostEqual(p[0], x)

    def test_consistent_system_needs_no_removal(self):
        r = fixture(); r['graph']['constraints'][1]['value'] = 8
        d = diagnose(r)
        self.assertTrue(d['full_system']['consistent'])
        self.assertEqual(d['single_semantic_removals'], [])

    def test_multiple_conflicts_are_not_claimed_as_single_repair(self):
        r = fixture()
        r['graph']['constraints'].append(relation('Abs', 0, [0, 1], value=3))
        d = diagnose(r)
        self.assertFalse(d['full_system']['consistent'])
        self.assertEqual(d['single_semantic_removals'], [])

    def test_underdetermined_solution_is_labelled(self):
        a, b = equations([relation('Abs', 0, [1, 0], value=2)], 1, 1)
        result = solve(a, b)
        self.assertTrue(result['consistent'])
        self.assertFalse(result['unique'])

    def test_offsets_oblique_projection_and_ratio_extrapolation(self):
        cs = [relation('Abs', 0, [1, 0], value=1),
              relation('Abs', 0, [0, 1], value=2),
              relation('Dist', 1, [1, 0], [0], .25, round=False),
              relation('Dist', 1, [1, 1], [0], .75/2**.5, round=False),
              relation('Ratio', 2, [1, 0], [0, 1], 2),
              relation('Ratio', 2, [0, 1], [0, 1], 2)]
        result = solve(*equations(cs, 3, 1))
        self.assertTrue(result['consistent'] and result['unique'])
        for actual, expected in zip(result['points_px'], [[1, 2], [1.25, 2.5], [1.5, 3]]):
            for a, b in zip(actual, expected):
                self.assertAlmostEqual(a, b)


if __name__ == '__main__':
    unittest.main()
