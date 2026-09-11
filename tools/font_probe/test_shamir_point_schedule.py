import unittest
from shamir_constraints import resolve,relation


class PointSchedulingTests(unittest.TestCase):
    def test_cross_coordinate_cycle_distinguishes_backends(self):
        points=[[0,0],[10,10],[20,20]]
        cs=[relation('Dist',0,[1,0],[1],-10),
            relation('Dist',1,[0,1],[0],10),
            relation('Dist',2,[1,0],[0],20)]
        scalar=resolve(points,cs)
        point=resolve(points,cs,scheduler='point')
        self.assertFalse(any(r['reason']=='dependency cycle' for r in scalar['rejected']))
        removed=[r['constraint']['id'] for r in point['rejected'] if r['reason']=='dependency cycle']
        self.assertEqual(removed,[1])
        self.assertEqual(point['order'],[1,0,2])
        # Both coordinates of each source finish before any dependent point.
        rank={c['id']:i for i,c in enumerate(point['constraints'])}
        for c in point['constraints']:
            self.assertTrue(all(rank[d]<rank[c['id']] for d in c['depends_on']))

    def test_acyclic_relations_are_preserved(self):
        cs=[relation('Abs',0,[1,0],value=0),relation('Dist',1,[1,0],[0],10)]
        a=resolve([[0,0],[10,10]],cs)
        b=resolve([[0,0],[10,10]],cs,scheduler='point')
        key=lambda c:(c['id'],c['kind'],c['sources'],c['value'])
        self.assertEqual(sorted(map(key,a['constraints'])),sorted(map(key,b['constraints'])))
        self.assertEqual(b['order'],[0,1])

    def test_shared_priority_survives_cycle(self):
        cs=[relation('Dist',0,[1,0],[1],-10),relation('PDist',1,[0,1],[0],10)]
        graph=resolve([[0,0],[10,10]],cs,scheduler='point')
        self.assertEqual([r['constraint']['id'] for r in graph['rejected']],[0])

    def test_invalid_backend_fails(self):
        with self.assertRaises(ValueError):resolve([[0,0]],[],scheduler='typo')
