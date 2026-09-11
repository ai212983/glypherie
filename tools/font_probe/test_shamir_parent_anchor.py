import unittest
import numpy as np
from shamir_constraints import relation
from shamir_parent_anchor import replace_anchors, experiment


class ParentAnchorTests(unittest.TestCase):
    def fixture(self):
        points=np.array([[431.,207.],[473.,214.]])
        n=np.array([-1.,6.])/np.sqrt(37)
        cs=[relation('Abs',0,n,value=float(points[0]@n),segment_owner=9),
            relation('Abs',0,[0,1],value=207),
            relation('Dist',1,n,[0],0,round=False,feature='align-9'),
            relation('Abs',1,[1,0],value=473)]
        return points,cs

    def test_both_policies_keep_relative_alignment(self):
        points,cs=self.fixture()
        for rounded,expected in [(True,9.),(False,8.62)]:
            result=experiment(dict(retained_equations=cs),points,20,1000,rounded)
            out=result['graph']['baseline_execution']['model_points_px']
            self.assertAlmostEqual(out[0][0],expected)
            self.assertAlmostEqual(out[0][1],4.)
            self.assertLess(result['residual_px'],1e-12)
            self.assertEqual(len(result['changes']),1)

    def test_font_linked_anchor_is_not_replaced(self):
        points,cs=self.fixture();cs[0]['kind']='PAbs'
        self.assertEqual(replace_anchors(cs,points,False)[1],[])

    def test_requires_side_membership_and_explicit_cardinal_anchor(self):
        points,cs=self.fixture()
        self.assertEqual(replace_anchors(cs[:2],points,False)[1],[])
        cs[1]['default']=True
        self.assertEqual(replace_anchors(cs,points,False)[1],[])

    def test_axis_swap_and_reflection(self):
        points,cs=self.fixture()
        for transform in (np.array([[0,1],[1,0]]),np.array([[-1,0],[0,1]])):
            moved=points@transform.T
            candidates=[dict(c,normal=(np.asarray(c['normal'])@transform.T).tolist()) for c in cs]
            result=experiment(dict(retained_equations=candidates),moved,20,1000,False)
            expected=np.array([8.62,4.])@transform.T
            self.assertTrue(np.allclose(result['graph']['baseline_execution']['model_points_px'][0],expected))


if __name__ == '__main__': unittest.main()
