import unittest
import numpy as np
from shamir_constraints import relation
from shamir_baseline_members import assemble_member_graph, evaluate_member_graph, schedule_member_graph


class MemberPhaseTests(unittest.TestCase):
    def test_late_orthogonal_links_preserve_both_alignments(self):
        points = np.array([[0., 0.], [1.3, 1.7]])
        reduced = [relation('Abs', 0, [1, 0], value=0.),
                   relation('Abs', 0, [0, 1], value=0., default=True),
                   relation('Abs', 1, [0, 1], value=2.),
                   relation('Abs', 1, [1, 0], value=1.3, default=True)]
        attachments = [relation('Dist', 0, [0, 1], sources=[1], value=0., round=False),
                       relation('Dist', 1, [1, 0], sources=[0], value=0., round=False)]
        graph = assemble_member_graph(points, reduced, attachments, [0, 1])
        fitted, _ = evaluate_member_graph(graph, points, 1, 1)
        np.testing.assert_allclose(fitted, [[0., 2.], [0., 2.]])
        self.assertEqual(graph['rejected'], [])
        self.assertFalse(any(c.get('default') for c in graph['constraints']))

    def test_synthetic_representative_anchors_remain_on_free_axes(self):
        points = np.array([[.3, .7]])
        reduced = [relation('Abs', 0, [1, 0], value=.3, default=True, round=False),
                   relation('Abs', 0, [0, 1], value=.7, default=True, round=False)]
        graph = assemble_member_graph(points, reduced, [], [0])
        fitted, _ = evaluate_member_graph(graph, points, 1, 1)
        np.testing.assert_allclose(fitted, points)

    def test_late_distance_preserves_explicit_representative_abs(self):
        points = np.array([[0., 0.], [1., 1.]])
        reduced = [relation('Abs', 0, [1, 0], value=0.),
                   relation('Abs', 0, [0, 1], value=0.),
                   relation('Abs', 1, [1, 0], value=1.),
                   relation('Abs', 1, [0, 1], value=1.)]
        attachment = relation('Dist', 0, [1, 0], sources=[1], value=0., feature='member')
        graph = assemble_member_graph(points, reduced, [attachment])
        self.assertEqual(graph['rejected'][0]['constraint']['feature'], 'member')
        self.assertEqual(graph['rejected'][0]['reason'], 'fixed representative projection')

    def test_late_members_use_ordinary_priorities(self):
        points = np.array([[0., 0.], [1., 1.]])
        reduced = [relation('Abs', 0, [1, 0], value=0.),
                   relation('Abs', 0, [0, 1], value=0.)]
        attachments = [relation('Abs', 1, [1, 0], value=1., feature='local'),
                       relation('Dist', 1, [1, 0], sources=[0], value=0., feature='member')]
        graph = assemble_member_graph(points, reduced, attachments, [0])
        self.assertEqual(graph['rejected'][0]['constraint']['feature'], 'local')
        fitted, _ = evaluate_member_graph(graph, points, 1, 1)
        self.assertEqual(fitted[1, 0], 0.)

    def test_unanchored_equation_cycle_fails_explicitly(self):
        points = np.array([[0., 0.], [1., 1.]])
        constraints = [relation('Dist', p, n, sources=[1-p], value=0.)
                       for p in (0, 1) for n in ([1, 0], [0, 1])]
        graph = assemble_member_graph(points, [], constraints)
        with self.assertRaisesRegex(ValueError, 'underdetermined or contradictory'):
            evaluate_member_graph(graph, points, 1, 1)

    def test_contradictory_equation_cycle_fails_explicitly(self):
        points = np.array([[0., 0.], [1., 1.]])
        constraints = [relation('Dist', p, [1, 0], sources=[1-p], value=1.)
                       for p in (0, 1)]
        constraints += [relation('Abs', p, [0, 1], value=0.) for p in (0, 1)]
        graph = assemble_member_graph(points, [], constraints)
        with self.assertRaisesRegex(ValueError, 'underdetermined or contradictory'):
            evaluate_member_graph(graph, points, 1, 1)


class MemberSchedulingTests(unittest.TestCase):
    def test_point_order_preserves_equations_and_native_quantization(self):
        from shamir_baseline_solver import resolve_baseline, evaluate_baseline
        points = np.array([[.4, .6], [2.3, 2.7], [1.2, 1.6]])
        core = [relation('Abs', p, n, value=float(points[p] @ np.array(n)))
                for p in (0, 1) for n in ([1, 0], [0, 1])]
        reduced = resolve_baseline(points[:2], core)
        links = [relation('Dist', 2, [1, 0], sources=[0], value=.8, round=False),
                 relation('Dist', 2, [0, 1], sources=[1], value=-1.1, round=False)]
        graph = assemble_member_graph(points, reduced['constraints'], links, [0, 1])
        simultaneous, before = evaluate_member_graph(graph, points, 1, 1)
        scheduled = schedule_member_graph(graph, points, {0, 1})
        fitted, after = evaluate_baseline(scheduled, points, 1, 1)
        np.testing.assert_allclose(fitted, simultaneous)
        self.assertEqual(before['native_points_px'], after['native_points_px'])
        self.assertEqual(scheduled['scheduler'], 'point')
        self.assertEqual(scheduled['rejected'], graph['rejected'])
        self.assertGreater(scheduled['order'].index(2), scheduled['order'].index(0))
        self.assertGreater(scheduled['order'].index(2), scheduled['order'].index(1))

    def test_late_cycle_fails_without_discarding_constraints(self):
        points = np.array([[0., 0.], [1., 1.]])
        links = [relation('Dist', p, [1, 0], sources=[1-p], value=0.) for p in (0, 1)]
        graph = assemble_member_graph(points, [], links)
        before = list(graph['rejected'])
        with self.assertRaisesRegex(ValueError, 'dependency cycle after reduced resolution'):
            schedule_member_graph(graph, points, set())
        self.assertEqual(graph['rejected'], before)

    def test_unresolved_shared_role_fails(self):
        points = np.array([[0., 0.]])
        graph = assemble_member_graph(points, [], [relation('Abs', 0, [1, 0], value=0.)])
        with self.assertRaisesRegex(ValueError, 'bypassed reduced resolution'):
            schedule_member_graph(graph, points, {0})

    def test_rejected_late_rep_link_fails_at_schedule_boundary(self):
        points = np.array([[0., 0.], [1., 1.]])
        reduced = [relation('Abs', 0, [1, 0], value=0.),
                   relation('Abs', 0, [0, 1], value=0.),
                   relation('Abs', 1, [1, 0], value=1.),
                   relation('Abs', 1, [0, 1], value=1.)]
        attachment = relation('Dist', 0, [1, 0], sources=[1], value=0., feature='member')
        graph = assemble_member_graph(points, reduced, [attachment])
        self.assertEqual(graph['rejected'][0]['reason'], 'fixed representative projection')
        with self.assertRaisesRegex(ValueError, 'bypassed reduced resolution'):
            schedule_member_graph(graph, points, {0, 1})

    def test_valid_shared_close_preserves_ordinary_priority_and_refs(self):
        from shamir_baseline_solver import resolve_baseline
        from shamir_shared_roles import close_shared_roles
        points = np.array([[0., 0.], [2., 2.], [3., 1.]])
        core = [relation('Abs', p, n, value=float(points[p] @ np.array(n)), round=False)
                for p in (0, 1) for n in ([1, 0], [0, 1])]
        shared = relation('Dist', 0, [0, 1], sources=[1], value=0., round=False, feature='shared')
        late = relation('Dist', 2, [1, 0], sources=[0], value=1., round=False, feature='late')
        parts = close_shared_roles(core, [shared, late], {0, 1})
        resolved = resolve_baseline(points[:2], parts['reduced_candidates'])
        graph = assemble_member_graph(points, resolved['constraints'], parts['late_attachments'], [0, 1])
        scheduled = schedule_member_graph(graph, points, {0, 1})
        member_eqs = [c for c in scheduled['constraints'] if c['point'] == 2]
        self.assertEqual(len(member_eqs), 2)
        self.assertTrue(all(c.get('feature') == 'late' or c.get('default') for c in member_eqs))
        self.assertLess(scheduled['order'].index(0), scheduled['order'].index(2))

    def test_shared_corner_with_two_independent_non_cardinal_constraints(self):
        from shamir_baseline_solver import resolve_baseline
        from shamir_shared_roles import close_shared_roles
        points = np.array([[0., 0.], [2., 0.]])
        diag = [1 / np.sqrt(2), 1 / np.sqrt(2)]
        anti = [1 / np.sqrt(2), -1 / np.sqrt(2)]
        core = [relation('Abs', 0, [1, 0], value=1., round=False),
                relation('Abs', 0, [0, 1], value=0., round=False),
                relation('Abs', 1, [1, 0], value=2., round=False),
                relation('Abs', 1, [0, 1], value=0., round=False)]
        links = [relation('Dist', 1, diag, sources=[0],
                          value=float((points[1] - points[0]) @ np.array(diag)), round=False),
                 relation('Dist', 1, anti, sources=[0],
                          value=float((points[1] - points[0]) @ np.array(anti)), round=False)]
        parts = close_shared_roles(core, links, {0, 1})
        resolved = resolve_baseline(points, parts['reduced_candidates'])
        self.assertEqual(parts['late_attachments'], [])
        self.assertEqual(len([c for c in resolved['constraints'] if c['point'] == 1]), 2)
        from shamir_baseline_solver import evaluate_baseline
        fitted, _ = evaluate_baseline(resolved, points, 1, 1)
        np.testing.assert_allclose(fitted, [[1., 0.], [3., 0.]], atol=1e-12)
        self.assertTrue(all(c['kind'] == 'Dist' for c in resolved['constraints'] if c['point'] == 1))
