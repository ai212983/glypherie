import unittest
import numpy as np
from joint_stroke_fit import constrained_fit

class JointFitTests(unittest.TestCase):
    def test_metric_stays_exact_with_conflicting_soft_goal(self):
        q=constrained_fit([[1,0]],[2],[[1,0],[0,1]],[10,3])
        np.testing.assert_allclose(q,[2,3])

    def test_incompatible_metrics_raise(self):
        with self.assertRaisesRegex(ValueError,'incompatible'):
            constrained_fit([[1,0],[1,0]],[1,2],np.eye(2),[0,0])

    def test_soft_conflict_is_compromise_not_silent_discard(self):
        q=constrained_fit([],[],[[1],[1]],[1,3])
        np.testing.assert_allclose(q,[2])

    def test_point_order_does_not_change_fit(self):
        hard=np.array([[1.,0.,0.]])
        goals=np.array([[1.,0.,0.],[0.,1.,0.],[0.,0.,1.],[0.,1.,-1.]])
        target=[0,2,4,0]
        a=constrained_fit(hard,[1],goals,target)
        ids=[2,0,1];b=constrained_fit(hard[:,ids],[1],goals[:,ids],target)
        np.testing.assert_allclose(a[ids],b,atol=1e-10)


class StemSupportTests(unittest.TestCase):
    def test_complete_sides_follow_source_geometry(self):
        from joint_stroke_fit import stem_relations
        p=np.array([[0.,0.],[0.,4.],[0.,8.],[2.,8.],[2.,0.]])
        record=dict(graph=dict(constraints=[dict(id=9,kind='PDist',feature='width-0')]),features=[dict(kind='stem',width=2,length=8,normal=[1,0],points=[0,3])])
        rows,ids,audit=stem_relations(p,[4],record)
        self.assertEqual(ids,[9])
        self.assertEqual(audit[0]['sides'],[[0,1,2],[3,4]])
        np.testing.assert_allclose(np.array(rows) @ p.ravel(),0)
        tilted=p.copy();tilted[1,0]=.2
        self.assertGreater(np.max(abs(np.array(rows) @ tilted.ravel())),.1)

    def test_incomplete_side_does_not_get_protected(self):
        from joint_stroke_fit import stem_relations
        p=np.array([[0.,0.],[1.,4.],[2.,0.]])
        record=dict(graph=dict(constraints=[dict(id=9,kind='Dist',feature='width-0')]),features=[dict(kind='stem',width=2,length=8,normal=[1,0],points=[0,2])])
        rows,ids,audit=stem_relations(p,[2],record)
        self.assertEqual(ids,[])
        self.assertEqual(audit[0]['status'],'held')

class LegacySizeTests(unittest.TestCase):
    def test_no_table_or_anchor_standardizes_nothing(self):
        # Faces above 14px carry neither width table nor cap anchor:
        # standardization must be a no-op returning no changes and
        # leaving hard values untouched (the legacy joint path the
        # driver relies on for 16px+ parity).
        from joint_stroke_fit import standardize_hard_widths
        cs=[dict(id=7,kind='Dist',point=1,sources=[0],normal=[1,0],
                 value=10.0,feature='width-0')]
        record=dict(graph=dict(order=[0,1],constraints=[dict(c) for c in cs]),
                    features=[dict(kind='arc',width=10.0)])
        hard_values=[10.0]
        changes=standardize_hard_widths(record,cs,[0],hard_values,1.0,20.0)
        self.assertEqual(changes,[])
        self.assertEqual(hard_values,[10.0])
        self.assertEqual(cs[0]['value'],10.0)

class TerminalFeatureTests(unittest.TestCase):
    def test_intersecting_bar_identifies_terminal_length(self):
        from joint_stroke_fit import terminal_competitor
        p=np.array([[0.,0.],[8.,0.],[0.,1.],[8.,1.]])
        terminal=dict(kind='stem',width=8,length=1,normal=[1,0],points=[0,1],support_direction=[0,1],support_intervals=[[0,1]])
        bar=dict(kind='bar',width=1,length=8,normal=[0,1],points=[0,2],support_direction=[1,0],support_intervals=[[0,8]])
        self.assertEqual(terminal_competitor(p,terminal,[terminal,bar]),1)
        self.assertIsNone(terminal_competitor(p,bar,[terminal,bar]))
        self.assertIsNone(terminal_competitor(p,terminal,[terminal]))
        distant=dict(bar,support_intervals=[[20,28]])
        self.assertIsNone(terminal_competitor(p,terminal,[terminal,distant]))

class ContinuationTests(unittest.TestCase):
    def test_existing_shallow_continuation_in_both_link_directions(self):
        from joint_stroke_fit import continuation_relations
        p=np.array([[0.,0.],[0.,4.],[.1,8.],[2.,8.]])
        n=np.array([4.,-.1]);n/=np.linalg.norm(n)
        stems=[dict(id=1,status='protected',normal=[1,0],sides=[[0,1]])]
        for a,b in [(2,1),(1,2)]:
            c=dict(id=7,kind='Dist',round=False,feature='align-3',point=a,sources=[b],normal=n.tolist(),value=0.)
            found=continuation_relations(p,[3],[1]*4,[c],stems)
            self.assertEqual([x['id'] for x in found],[7])
            self.assertEqual(continuation_relations(p,[3],[1,1,0,1],[c],stems),[])
            self.assertEqual(continuation_relations(p,[3],[1]*4,[dict(c,round=True)],stems),[])

    def test_steep_and_nonadjacent_links_are_excluded(self):
        from joint_stroke_fit import continuation_relations
        p=np.array([[0.,0.],[0.,4.],[4.,8.],[2.,8.]])
        stems=[dict(id=1,status='protected',normal=[1,0],sides=[[0,1]])]
        c=dict(id=7,kind='Dist',round=False,feature='align-3',point=2,sources=[1],normal=[2**-.5,-2**-.5],value=0.)
        self.assertEqual(continuation_relations(p,[3],[1]*4,[c],stems),[])
        c.update(point=2,sources=[0],normal=[1,0])
        self.assertEqual(continuation_relations(p,[3],[1]*4,[c],stems),[])

class ReflectionFitTests(unittest.TestCase):
    def test_reflection_is_solved_with_metric_anchors(self):
        from joint_stroke_fit import fit
        p=np.array([[0.,0.],[0.,10.],[2.6,10.],[2.6,0.]])
        cs=[dict(id=2*i+a,kind='Abs',point=i,sources=[],normal=[1-a,a],value=q[a],metric=(a==0)) for i,q in enumerate(p) for a in (0,1)]
        cs[5]=dict(id=5,kind='Dist',point=2,sources=[1],normal=[1,0],value=2.6,feature='width-0')
        record=dict(graph=dict(order=[0,1,2,3],constraints=cs),features=[dict(kind='slant',normal=[1,0],width=2.6,support_direction=[0,1],support_intervals=[[0,10]])])
        q,audit=fit(p,[3],[1]*4,record,1,reflection_em=100,reflection_ink={(0,0),(1,0),(0,1)})
        self.assertEqual(audit['reflection']['status'],'fitted')
        original,_=fit(p,[3],[1]*4,record,1)
        held,ha=fit(p,[3],[1]*4,record,1,reflection_em=100,reflection_ink={(4,0),(5,0)})
        self.assertEqual(ha['reflection']['status'],'already-symmetric')
        np.testing.assert_array_equal(held,original)
        with self.assertRaisesRegex(ValueError,'current rendered bitmap'):
            fit(p,[3],[1]*4,record,1,reflection_em=100)
        self.assertAlmostEqual(q[0,0]+q[3,0],3)
        self.assertAlmostEqual(q[1,0]+q[2,0],3)
        self.assertAlmostEqual(q[0,1],q[3,1])
        self.assertLess(audit['max_hard_residual_px'],1e-7)

class CapConflictRetryTests(unittest.TestCase):
    def test_conflicting_pin_falls_back_to_legacy_joint(self):
        # A cap pin contradicting hard ownership retries without
        # cap treatment instead of discarding the whole joint fit.
        from joint_stroke_fit import fit
        p = np.array([[0., 0.], [0., 10.2]])
        cs = [dict(id=0, kind='Abs', point=0, sources=[],
                   normal=[1, 0], value=0.0),
              dict(id=1, kind='Abs', point=0, sources=[],
                   normal=[0, 1], value=0.0),
              dict(id=2, kind='Abs', point=1, sources=[],
                   normal=[1, 0], value=0.0),
              dict(id=3, kind='Dist', point=1, sources=[0],
                   normal=[0, 1], value=10.2, metric=True,
                   metric_role='glyph-y-bound')]
        record = dict(
            graph=dict(order=[0, 1], constraints=cs), features=[],
            cap_table={'ppem': 1, 'em': 1, 'band_rel': 0.025,
                       'entries': [
                           {'name': 'flat_cap', 'design_units': 10.0,
                            'target_px': 10, 'reason': 'test',
                            'members': 10}]})
        owners = [dict(point=1, axis=1, value=5.0)]
        before = [dict(c) for c in record['graph']['constraints']]
        q, audit = fit(p, [1], [1, 1], record, 1.0,
                       upstream=np.zeros(4),
                       ownership=owners, order_relations=())
        self.assertEqual(audit['candidate_status'], 'joint-fit')
        self.assertTrue(audit['cap_conflict_retry'])
        self.assertEqual(audit['width_standardized'], [])
        self.assertAlmostEqual(q[1, 1], 5.0)
        # The retry restores the shared record, so a later fit on
        # the same record (reflection) solves the legacy system.
        self.assertEqual(record['graph']['constraints'], before)
        q2, audit2 = fit(p, [1], [1, 1], record, 1.0,
                         upstream=np.zeros(4),
                         ownership=owners, order_relations=())
        self.assertEqual(audit2['candidate_status'], 'joint-fit')
        self.assertAlmostEqual(q2[1, 1], 5.0)


class CapRefitTests(unittest.TestCase):
    def test_successful_redirect_repeats_on_same_record(self):
        # A successful cap redirect must not leak into the shared
        # record: the reflection re-fit reuses the same record, and
        # standardized values left behind make the redirect a vacuous
        # no-op (pins lost, apex floating half a pixel high).
        from joint_stroke_fit import fit
        p = np.array([[0., 0.], [0., 10.2]])
        cs = [dict(id=0, kind='Abs', point=0, sources=[],
                   normal=[1, 0], value=0.0),
              dict(id=1, kind='Abs', point=0, sources=[],
                   normal=[0, 1], value=0.0),
              dict(id=2, kind='Abs', point=1, sources=[],
                   normal=[1, 0], value=0.0),
              dict(id=3, kind='Dist', point=1, sources=[0],
                   normal=[0, 1], value=10.2, metric=True,
                   metric_role='glyph-y-bound')]
        record = dict(
            graph=dict(order=[0, 1], constraints=cs), features=[],
            cap_table={'ppem': 1, 'em': 1, 'band_rel': 0.025,
                       'entries': [
                           {'name': 'flat_cap', 'design_units': 10.0,
                            'target_px': 10, 'reason': 'test',
                            'members': 10}]})
        owners = [dict(point=1, axis=1, value=10.0)]
        before = [dict(c) for c in record['graph']['constraints']]
        q, audit = fit(p, [1], [1, 1], record, 1.0,
                       upstream=np.array([0., 0., 0., 11.]),
                       ownership=owners, order_relations=())
        self.assertEqual(audit['candidate_status'], 'joint-fit')
        self.assertTrue(audit['width_standardized'])
        self.assertTrue(audit['cap_point_pins'])
        self.assertAlmostEqual(q[1, 1], 10.0)
        # The success path leaves the shared record alone, so the
        # second fit on the same record reproduces pins and values.
        self.assertEqual(record['graph']['constraints'], before)
        q2, audit2 = fit(p, [1], [1, 1], record, 1.0,
                         upstream=np.array([0., 0., 0., 11.]),
                         ownership=owners, order_relations=())
        self.assertEqual(audit2['width_standardized'],
                         audit['width_standardized'])
        self.assertEqual(audit2['cap_point_pins'],
                         audit['cap_point_pins'])
        np.testing.assert_allclose(q2, q)


# CapSoftPullTests were briefly removed with the behavior, then
# restored: deleting pulls was rejected 6x on settled glyphs,
# so they stay as WHY load-bearing soft-goal corrections (see
# ``_cap_soft_pulls``). Tall-glyph stand-down now reads zone
# attachment (any entry band) instead of the cap-only rule.
class CapSoftPullTests(unittest.TestCase):
    def table(self, mode=1456.0, target=10):
        return {'ppem': 14, 'em': 2048, 'band_rel': 0.025,
                'entries': [{'name': 'flat_cap',
                             'design_units': mode,
                             'target_px': target, 'reason': 'test',
                             'members': 175}]}

    def test_arch_shoulder_below_band_joins(self):
        # Roboto 14px '0' shoulder: designed below the cap band but
        # lifted into the window upstream; its soft goal retargets.
        from joint_stroke_fit import _cap_soft_pulls
        record = {'cap_table': self.table()}
        reference = [0., 9., 0., 10.5, 0., 0.]
        targets = list(reference)
        design = np.array([[0., 1300.], [0., 1435.], [0., 0.]])
        pulled = _cap_soft_pulls(record, reference, [2], targets,
                                 design, [1, 0, 1])
        self.assertEqual(pulled, [1])
        self.assertEqual(targets[3], 10.0)

    def test_taller_top_above_band_keeps_goal(self):
        # Roboto 14px 'f': lifted into the window but designed above
        # the cap band, so it keeps natural rounding (native 11).
        from joint_stroke_fit import _cap_soft_pulls
        record = {'cap_table': self.table()}
        reference = [0., 9., 0., 10.7, 0., 0.]
        targets = list(reference)
        design = np.array([[0., 1300.], [0., 1557.], [0., 0.]])
        pulled = _cap_soft_pulls(record, reference, [2], targets,
                                 design, [1, 1, 1])
        self.assertEqual(pulled, [])
        self.assertEqual(targets[3], 10.7)

    def test_flat_cut_top_keeps_goal(self):
        # Slash terminal: in-window and in-band by design, but cut
        # flat (on-curve neighbor at the same design height).
        from joint_stroke_fit import _cap_soft_pulls
        record = {'cap_table': self.table()}
        reference = [0., 10.5, 0., 10.5, 0., 0.]
        targets = list(reference)
        design = np.array([[0., 1456.], [0., 1456.], [0., 0.]])
        pulled = _cap_soft_pulls(record, reference, [2], targets,
                                 design, [1, 1, 1])
        self.assertEqual(pulled, [])
        self.assertEqual(targets[1], 10.5)

    def test_flat_above_mode_still_pulls(self):
        # A serif top cut flat but designed past the mode was lifted
        # over the anchor; it pulls down with the crown.
        from joint_stroke_fit import _cap_soft_pulls
        record = {'cap_table': self.table(656.0, 9)}
        reference = [0., 9., 0., 9.6, 0., 9.6, 0., 0.]
        targets = list(reference)
        design = np.array([[0., 400.], [0., 660.], [0., 660.],
                           [0., 0.]])
        pulled = _cap_soft_pulls(record, reference, [3], targets,
                                 design, [1, 1, 1, 1])
        self.assertEqual(sorted(pulled), [1, 2])
        self.assertEqual(targets[3], 9.0)
        self.assertEqual(targets[5], 9.0)

    def test_dot_contour_keeps_goal(self):
        # A short contour (tittle) in the window never joins.
        from joint_stroke_fit import _cap_soft_pulls
        record = {'cap_table': self.table()}
        reference = [0., 10.3, 0., 11.0]
        targets = list(reference)
        design = np.array([[0., 1500.], [0., 1600.]])
        pulled = _cap_soft_pulls(record, reference, [1], targets,
                                 design, [1, 1])
        self.assertEqual(pulled, [])


class FlatTopCollapseTests(unittest.TestCase):
    def rows(self, apex, flat=507.0, flat_round=True, apex_std=False):
        flat_row = dict(id=0, kind='PAbs', point=1, sources=[],
                        normal=[0, 1], value=flat, round=flat_round)
        apex_row = dict(id=1, kind='PAbs', point=2, sources=[],
                        normal=[0, 1], value=apex, extent='max')
        if apex_std:
            apex_row['width_standardized'] = True
        return apex_row, [flat_row, apex_row]

    def test_arch_apex_collapses_to_flat_integer(self):
        # literata-16 m: arch 521u over stem-flat 507u at
        # 16px/1000em takes 8, not the outward 9.
        from joint_stroke_fit import _flat_top_collapse
        apex, cs = self.rows(521.0)
        self.assertEqual(_flat_top_collapse(apex, cs, 0.016), 8)

    def test_no_flat_keeps_ceiling(self):
        # Round crowns without a same-glyph flat (ss3-18 'o'
        # shape) are untouched by construction.
        from joint_stroke_fit import _flat_top_collapse
        apex = dict(id=1, kind='PAbs', point=2, sources=[],
                    normal=[0, 1], value=521.0, extent='max')
        self.assertIsNone(_flat_top_collapse(apex, [apex], 0.016))

    def test_beyond_band_keeps_ceiling(self):
        from joint_stroke_fit import _flat_top_collapse
        apex, cs = self.rows(600.0)
        self.assertIsNone(_flat_top_collapse(apex, cs, 0.016))

    def test_noop_collapse_abstains(self):
        # Apex already ceilings to the flat integer: no record.
        from joint_stroke_fit import _flat_top_collapse
        apex, cs = self.rows(495.0, flat=490.0)
        self.assertIsNone(_flat_top_collapse(apex, cs, 0.016))

    def test_standardized_and_unrounded_guards(self):
        from joint_stroke_fit import _flat_top_collapse
        apex, cs = self.rows(521.0, apex_std=True)
        self.assertIsNone(_flat_top_collapse(apex, cs, 0.016))
        apex2, cs2 = self.rows(521.0, flat_round=False)
        self.assertIsNone(_flat_top_collapse(apex2, cs2, 0.016))
        plain = dict(id=1, kind='PAbs', point=2, sources=[],
                     normal=[0, 1], value=521.0)
        self.assertIsNone(_flat_top_collapse(plain, cs2, 0.016))


class WithholdSpanTests(unittest.TestCase):
    # Pins exact-equality span semantics (relative 1e-6 dust
    # tolerance). A 1px cut-in band was tried
    # (arch-probe-v22, 2026-09-15) and reverted: it withheld
    # ss3-14 `-` (bearings-scale mismatch, not a span),
    # REJECTED with both witnesses holding the 1px hyphen,
    # and no observed case needs absorption beyond dust.
    # Near-full spans share here by design; see
    # ``_withholds_table`` for the reopen terms.
    YRANGE = 1496.0

    def arc(self, value, vertical=True):
        normal = [0.0, 1.0] if vertical else [1.0, 0.0]
        return (dict(kind='Dist', point=1, sources=[0],
                     normal=normal, value=value),
                dict(kind='arc'))

    def extent(self, value):
        return dict(kind='Dist', point=0, sources=[1],
                    normal=[0.0, 1.0], value=value,
                    metric_role='glyph-y-bound')

    def test_arc_exact_full_withholds(self):
        from joint_stroke_fit import _withholds_table
        c, f = self.arc(self.YRANGE)
        self.assertTrue(_withholds_table(c, f, self.YRANGE))

    def test_arc_near_full_shares(self):
        # 96u short of full: shares (the v22 band withheld
        # this; oracle rejected the only live instance).
        from joint_stroke_fit import _withholds_table
        c, f = self.arc(self.YRANGE - 96.0)
        self.assertFalse(_withholds_table(c, f, self.YRANGE))

    def test_arc_partial_shares(self):
        from joint_stroke_fit import _withholds_table
        c, f = self.arc(151.0)
        self.assertFalse(_withholds_table(c, f, self.YRANGE))

    def test_arc_horizontal_shares(self):
        from joint_stroke_fit import _withholds_table
        c, f = self.arc(self.YRANGE, vertical=False)
        self.assertFalse(_withholds_table(c, f, self.YRANGE))

    def test_extent_full_withholds_partial_shares(self):
        from joint_stroke_fit import _withholds_table
        f = dict(kind='stem')
        self.assertTrue(_withholds_table(
            self.extent(self.YRANGE), f, self.YRANGE))
        self.assertFalse(_withholds_table(
            self.extent(self.YRANGE - 46.0), f, self.YRANGE))
        self.assertFalse(_withholds_table(
            self.extent(1000.0), f, self.YRANGE))

    def test_plain_stem_never_withholds(self):
        from joint_stroke_fit import _withholds_table
        c = dict(kind='Dist', point=0, sources=[1],
                 normal=[0.0, 1.0], value=self.YRANGE)
        self.assertFalse(_withholds_table(
            c, dict(kind='stem'), self.YRANGE))


if __name__=='__main__':unittest.main()
