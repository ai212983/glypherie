"""Metric semantics survive conversion of baseline membership to a point link."""
import unittest
import numpy as np
from shamir_model import constraints_for
from shamir_constraints import relation
from shamir_baseline_solver import resolve_baseline, evaluate_baseline


class BaselineMembershipTests(unittest.TestCase):
    def model(self, y=0., normal=(0., 1.)):
        return dict(points=np.array([[0., y], [5.2, y], [2., 4.]]),
                    extrema={}, features=[], groups=[
                        dict(rep=0, members={0, 1}, normal=list(normal))])

    def test_metric_link_wins_over_competing_diagonal(self):
        m = self.model()
        _, links, _ = constraints_for(m, {}, 1, baseline=True)
        self.assertTrue(links[0]['metric'])
        cs = [relation('Abs', 0, [1, 0], value=0, metric=True),
              relation('Abs', 0, [0, 1], value=0, metric=True),
              relation('Abs', 2, [1, 0], value=2),
              relation('Abs', 2, [0, 1], value=4),
              relation('Dist', 1, [1, 0], [0], 5.2, metric=True),
              relation('Dist', 1, [.8, .6], [2], .16, round=False, feature='diagonal'),
              *links]
        graph = resolve_baseline(m['points'], cs)
        fitted, _ = evaluate_baseline(graph, m['points'], 1, 1)
        np.testing.assert_allclose(fitted[1], [5., 0.])
        self.assertTrue(any(r['constraint'].get('feature') == 'diagonal' for r in graph['rejected']))
        # Losing the semantic tag reproduces the endpoint leaving the baseline.
        untagged = [dict(c) for c in cs]
        untagged[-1].pop('metric')
        bad, _ = evaluate_baseline(resolve_baseline(m['points'], untagged), m['points'], 1, 1)
        self.assertGreater(abs(bad[1, 1]), .2)

    def test_local_heights_diagonals_and_experimental_links_stay_local(self):
        for m, baseline in [(self.model(y=2), True), (self.model(normal=(1., 0.)), True),
                            (self.model(), False)]:
            _, links, _ = constraints_for(m, {}, 1, baseline=baseline)
            self.assertNotIn('metric', links[0])

    def test_descender_does_not_hide_baseline_membership(self):
        m = self.model()
        m['points'][2, 1] = -3
        _, links, _ = constraints_for(m, {}, 1, baseline=True)
        self.assertEqual(links[0]['metric_role'], 'baseline')


if __name__ == '__main__':
    unittest.main()
