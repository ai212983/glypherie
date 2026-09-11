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

if __name__=='__main__':unittest.main()
