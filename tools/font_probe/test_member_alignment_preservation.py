import unittest
import numpy as np
from joint_stroke_fit import fit, select_member_alignments


def _link(id, point, source, normal, value=0., round=False, feature='align-0', kind='Dist'):
    return dict(id=id, kind=kind, point=point, sources=[source], normal=list(normal),
                value=value, round=round, feature=feature)


def _record(extra=()):
    p = np.array([[0., 0.], [0., 10.]])
    cs = [dict(id=0, kind='Abs', point=0, sources=[], normal=[1, 0], value=0., metric=True),
          dict(id=1, kind='Abs', point=0, sources=[], normal=[0, 1], value=0., metric=True),
          dict(id=2, kind='Abs', point=1, sources=[], normal=[0, 1], value=10., metric=True),
          _link(3, 1, 0, [1, 0]),
          *[dict(c) for c in extra]]
    return p, dict(graph=dict(order=[0, 1], constraints=cs), features=[])


class SelectionTests(unittest.TestCase):
    def test_exact_link_selected_and_variants_skipped(self):
        p = np.array([[0., 0.], [0., 10.], [3., 10.]])
        flags = [1, 1, 1]
        good = _link(3, 1, 0, [1, 0])
        cases = [dict(good, id=10, round=True), dict(good, id=11, value=0.5),
                 dict(good, id=12, normal=[2 ** -.5, 2 ** -.5]),
                 dict(good, id=13, feature='width-0'),
                 dict(good, id=14, kind='PDist'),
                 dict(good, id=15, point=2),
                 dict(good, id=16, point=99)]
        sel, skipped = select_member_alignments(p, flags, [good] + cases)
        self.assertEqual(sel, [3])
        reasons = {s['id']: s['reason'] for s in skipped}
        self.assertEqual(set(reasons), {10, 11, 12, 13, 14, 15, 16})
        self.assertEqual(reasons[16], 'index-out-of-range')
        sel, skipped = select_member_alignments(p, [1, 0, 1], [good])
        self.assertEqual(sel, [])
        self.assertEqual(skipped[0]['reason'], 'off-curve-endpoint')


class PreservationTests(unittest.TestCase):
    def test_same_side_forced_together_other_side_free(self):
        p, record = _record()
        upstream = np.array([[0., 0.], [7., 10.]])
        free, _ = fit(p, [1], [1, 1], record, 1, upstream=upstream)
        self.assertAlmostEqual(free[1, 0], 7.)
        q, audit = fit(p, [1], [1, 1], record, 1, upstream=upstream,
                       preserve_member_alignments=True)
        self.assertAlmostEqual(q[1, 0], q[0, 0])
        self.assertAlmostEqual(q[1, 1], 10., msg='no global coordinate weld')
        self.assertIn(3, audit['protected_ids'])
        self.assertEqual(audit['experimental_status'], 'member-alignment-preservation')
        self.assertEqual([m['id'] for m in audit['member_alignment_relations']], [3])

    def test_default_behavior_unchanged(self):
        p, record = _record()
        upstream = np.array([[0., 0.], [7., 10.]])
        default, _ = fit(p, [1], [1, 1], record, 1, upstream=upstream)
        explicit, audit = fit(p, [1], [1, 1], record, 1, upstream=upstream,
                              preserve_member_alignments=False)
        np.testing.assert_array_equal(default, explicit)
        self.assertNotIn('member_alignment_relations', audit)
        self.assertNotIn(3, audit['protected_ids'] if 'protected_ids' in audit else [])

    def test_incompatible_ownership_raises(self):
        p, record = _record()
        upstream = np.array([[0., 0.], [7., 10.]])
        with self.assertRaisesRegex(ValueError, 'incompatible|residual'):
            fit(p, [1], [1, 1], record, 1, upstream=upstream,
                ownership=[dict(point=1, axis=0, value=5.)],
                preserve_member_alignments=True)


class BarUndersideTests(unittest.TestCase):
    """Roboto T shape: followers sag without preservation, stay flat with it."""

    def _bar_record(self):
        p = np.array([[0., 0.], [5., 0.], [9., 0.], [0., 10.]])
        cs = [dict(id=0, kind='Abs', point=0, sources=[], normal=[1, 0],
                   value=0., metric=True),
              dict(id=1, kind='Abs', point=0, sources=[], normal=[0, 1],
                   value=0., metric=True),
              dict(id=2, kind='Abs', point=3, sources=[], normal=[1, 0],
                   value=0., metric=True),
              dict(id=3, kind='PDist', point=3, sources=[0], normal=[0, 1],
                   value=10.),
              _link(4, 1, 0, [0, 1], feature='align-2'),
              _link(5, 2, 0, [0, 1], feature='align-2')]
        return p, dict(graph=dict(order=[0, 1, 2, 3], constraints=cs),
                       features=[])

    def test_followers_sag_without_preservation(self):
        p, record = self._bar_record()
        upstream = np.array([[0., 0.], [5., 2.], [9., 3.], [0., 10.]])
        q, _ = fit(p, [3], [1, 1, 1, 1], record, 1, upstream=upstream)
        self.assertGreater(q[1, 1], 0.5)
        self.assertGreater(q[2, 1], 0.5)
        self.assertNotAlmostEqual(q[1, 1], q[2, 1])

    def test_whole_underside_flat_with_preservation(self):
        p, record = self._bar_record()
        upstream = np.array([[0., 0.], [5., 2.], [9., 3.], [0., 10.]])
        q, audit = fit(p, [3], [1, 1, 1, 1], record, 1, upstream=upstream,
                       preserve_member_alignments=True)
        self.assertAlmostEqual(q[1, 1], q[0, 1])
        self.assertAlmostEqual(q[2, 1], q[0, 1])
        self.assertAlmostEqual(q[3, 1], 10.)
        self.assertIn(4, audit['protected_ids'])
        self.assertIn(5, audit['protected_ids'])


if __name__ == '__main__':
    unittest.main()
