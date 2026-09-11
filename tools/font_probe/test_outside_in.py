import unittest
from geometric_candidate import Geometry
from outside_in import recover


class RecoveryTests(unittest.TestCase):
    def fixture(self,protected=False):
        cs=({'kind':'Dist','point':1,'normal':[1,0],'sources':[0],'value':11,'metric':True,'id':0},
            {'kind':'PAbs' if protected else 'Abs','point':2,'normal':[1,0],'sources':[],'value':10,'id':1})
        d=Geometry(((0,0),(12,0),(10,0)),(2,),(1,1,1),14,1000,cs,())
        return d,dict(kind='Dist',point=1,normal=[1,0],sources=[2],value=80,feature='width-4')

    def test_reverses_distance_and_releases_only_ordinary_anchor(self):
        d,w=self.fixture();after,changes,held=recover(d,[w])
        self.assertEqual(after.constraints[0],d.constraints[0])
        self.assertEqual(after.constraints[1]['sources'],[1])
        self.assertEqual(after.constraints[1]['point'],2)
        self.assertEqual(after.constraints[1]['value'],-80)
        self.assertEqual(len(changes),1);self.assertEqual(held,[])

    def test_font_parameter_is_not_displaced(self):
        d,w=self.fixture(True);after,changes,held=recover(d,[w])
        self.assertEqual(after,d);self.assertEqual(changes,[]);self.assertEqual(len(held),1)

    def test_unanchored_outer_side_does_not_trigger(self):
        from dataclasses import replace
        d,w=self.fixture();d=replace(d,constraints=d.constraints[1:])
        after,changes,held=recover(d,[w]);self.assertEqual(after,d);self.assertEqual(changes,[])


if __name__=='__main__':unittest.main()
