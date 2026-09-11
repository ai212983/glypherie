import copy
import unittest
from fontTools.ttLib import TTFont
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from shamir_constraints import relation
from shamir_geometry import prepare
from shamir_model import feature_model, constraints_for
from shamir_representative_search import coordinate_representatives


def fixture():
    # An orthogonal stepped outline: shared corners constrain different axes.
    ps=[(65,55),(65,44),(25,44),(25,0),(12,0),(12,100),(73,100),(73,89),(25,89),(25,55)]
    return feature_model(prepare([[[a,b] for a,b in zip(ps,ps[1:]+ps[:1])]],100,baseline=True),baseline=True)


class RepresentativeSearchTests(unittest.TestCase):
    def test_search_preserves_geometry_and_improves_priority_score(self):
        m=fixture();original=m['points'].copy()
        result=coordinate_representatives(m,{'height-flat-min':[0.],'height-flat-max':[100.]},100,constraints_for)
        self.assertLess(result['selected_score'],result['initial_score'])
        self.assertEqual(result['selected_cycles'],0)
        self.assertTrue((m['points']==original).all())
        for g in m['groups']:
            if g['members']:self.assertIn(g['rep'],g['members'])

    def test_bound_and_repeatability(self):
        a,b=fixture(),fixture()
        ra=coordinate_representatives(a,{},100,constraints_for,1)
        self.assertEqual(ra['evaluations'],1);self.assertFalse(ra['changes'])
        self.assertEqual(coordinate_representatives(fixture(),{},100,constraints_for),
                         coordinate_representatives(b,{},100,constraints_for))

    def test_inconsistent_cycle_is_not_claimed_solved_by_selection(self):
        model=dict(points=np.array([[0.,0.],[1.,1.]]),glyph=SimpleNamespace(flags=[1,1]),
                   groups=[dict(rep=i,members={i},normal=[1.,0.]) for i in (0,1)])
        def construct(*args,**kwargs):
            return ([relation('Dist',i,[1,0],[1-i],1) for i in (0,1)]+
                    [relation('Abs',i,[0,1],value=0) for i in (0,1)],[],{0,1})
        result=coordinate_representatives(model,{},1,construct)
        self.assertEqual(result['selected_cycles'],1)
        self.assertFalse(result['changes'])


if __name__=='__main__':unittest.main()
