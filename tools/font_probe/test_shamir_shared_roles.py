import unittest
import numpy as np
from shamir_constraints import relation
from shamir_baseline_solver import resolve_baseline, evaluate_baseline
from shamir_shared_roles import close_shared_roles


class SharedRoleTests(unittest.TestCase):
    def setUp(self):
        self.points = np.array([[0., 0.], [2., 2.]])
        self.core = [relation('Abs', p, n, value=float(self.points[p] @ np.array(n)), round=False)
                     for p in range(2) for n in ([1, 0], [0, 1])]

    def test_shared_distance_uses_published_priority_over_local_abs(self):
        link = relation('Dist', 0, [0, 1], sources=[1], value=0., round=False, feature='shared')
        parts = close_shared_roles(self.core, [link], {0, 1})
        graph = resolve_baseline(self.points, parts['reduced_candidates'])
        fitted, _ = evaluate_baseline(graph, self.points, 1, 1)
        np.testing.assert_array_equal(fitted, [[0., 2.], [2., 2.]])
        selected = next(c for c in graph['constraints'] if c.get('feature') == 'shared')
        self.assertEqual(selected['shared_role_assumption'], 'B11-representative-role-closure')
        self.assertEqual(parts['late_attachments'], [])
        self.assertNotIn('shared_role_assumption', link)

    def test_shared_cycle_is_resolved_with_rejection_provenance(self):
        links = [relation('Dist', p, [0, 1], sources=[1-p], value=1., round=False,
                          feature=f'shared-{p}') for p in (0, 1)]
        parts = close_shared_roles(self.core, links, {0, 1})
        graph = resolve_baseline(self.points, parts['reduced_candidates'])
        cycles = [r for r in graph['rejected'] if r['reason'] == 'dependency cycle']
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0]['constraint']['feature'], 'shared-1')
        self.assertEqual(cycles[0]['constraint']['shared_role_assumption'], parts['assumption'])
        evaluate_baseline(graph, self.points, 1, 1)

    def test_ordinary_member_stays_late(self):
        link = relation('Dist', 2, [1, 0], sources=[0], value=0., feature='late')
        parts = close_shared_roles(self.core, [link], {0, 1})
        self.assertEqual(parts['late_attachments'], [link])
        self.assertEqual(parts['shared_attachments'], [])
        self.assertEqual(parts['reduced_candidates'], self.core)

    def test_unresolved_member_source_fails(self):
        link = relation('Dist', 2, [1, 0], sources=[3], value=0.)
        with self.assertRaisesRegex(ValueError, 'source is not a representative'):
            close_shared_roles(self.core, [link], {0, 1})
