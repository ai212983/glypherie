"""Free coordinates use Ratio whenever two projected anchors define one."""
import unittest
from shamir_constraints import relation,resolve


class DefaultRatioTests(unittest.TestCase):
    def graph(self,points):
        anchors=[relation('Abs',p,n,value=points[p][axis])
                 for p in (0,1) for axis,n in enumerate(((1,0),(0,1)))]
        return resolve(points,anchors,reference_points=(0,1))

    def x_default(self,graph):
        return next(c for c in graph['constraints'] if c['point']==2 and c['normal']==[1.,0.])

    def test_outside_interval_uses_extrapolating_ratio(self):
        c=self.x_default(self.graph([[0,0],[10,10],[15,5]]))
        self.assertEqual(c['kind'],'Ratio')
        self.assertEqual(c['sources'],[1,0])
        self.assertEqual(c['value'],-.5)

    def test_exact_anchor_uses_ratio_and_only_effective_dependency(self):
        graph=self.graph([[0,0],[10,10],[0,5]])
        c=self.x_default(graph)
        self.assertEqual(c['kind'],'Ratio');self.assertEqual(c['value'],0)
        dependencies=[r for r in graph['constraints'] if r['id'] in c['depends_on']]
        self.assertEqual([r['point'] for r in dependencies],[0])

    def test_degenerate_and_missing_reference_fallbacks_are_explicit(self):
        c=self.x_default(self.graph([[0,0],[0,10],[5,5]]))
        self.assertEqual(c['kind'],'Dist')
        self.assertEqual(c['default_reason'],'no distinct projected reference pair')
        graph=resolve([[0,0]],[])
        self.assertTrue(all(c['default_reason']=='no reference points' for c in graph['constraints']))

if __name__=='__main__':unittest.main()
