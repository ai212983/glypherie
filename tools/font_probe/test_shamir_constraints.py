"""Paper model invariants: coupled directions, dependencies and conflict policy."""
import unittest
import numpy as np
from shamir_constraints import relation,resolve,priority


class ConstraintTests(unittest.TestCase):
    def test_projected_relations_share_degrees_of_freedom(self):
        p=np.array([[0,0],[1,1]],float)
        cs=[relation('PAbs',1,[0,1],value=1),relation('Dist',1,[1,1],[0],1),relation('Abs',1,[1,0],value=1)]
        g=resolve(p,cs)
        selected=[c for c in g['constraints'] if c['point']==1]
        self.assertEqual(len(selected),2);self.assertEqual({c['kind'] for c in selected},{'PAbs','Dist'})
        self.assertEqual(g['order'],[0,1])

    def test_native_near_parallel_fallback_is_rejected(self):
        cs=[relation('PAbs',0,[0,1],value=0),relation('Dist',0,[.03,1],[1],0)]
        g=resolve([[0,0],[1,0]],cs)
        self.assertTrue(any(r['reason']=='dependent or ill-conditioned direction' for r in g['rejected']))
        self.assertEqual(len([c for c in g['constraints'] if c['point']==0]),2)

    def test_default_completes_the_orthogonal_direction(self):
        for normal in ([1,.07],[.07,1],[1,1],[-1,.07]):
            graph=resolve([[1,2]],[relation('Abs',0,normal,value=2)])
            a,b=graph['constraints']
            self.assertAlmostEqual(float(np.dot(a['normal'],b['normal'])),0)
            self.assertTrue(b['default']);self.assertFalse(b['round'])
            # A half-pixel change of the selected target cannot be amplified by
            # an almost-parallel default coordinate.
            matrix=np.array([a['normal'],b['normal']])
            self.assertAlmostEqual(float(np.linalg.norm(np.linalg.solve(matrix,[.5,0]))),.5)

    def test_actual_features_limit_rounding_error_amplification(self):
        graph=resolve([[0,0]],[relation('PAbs',0,[1,.08],value=0),
                               relation('Abs',0,[1,0],value=0)])
        self.assertEqual(len(graph['rejected']),1)
        self.assertEqual(graph['rejected'][0]['constraint']['kind'],'Abs')
        self.assertLessEqual(np.linalg.cond([c['normal'] for c in graph['constraints']]),4)

    def test_ratio_waits_for_both_sources(self):
        g=resolve([[0,0],[1,1],[2,2]],[relation('Ratio',1,[1,0],[0,2],.5)])
        self.assertLess(g['order'].index(0),g['order'].index(1))
        self.assertLess(g['order'].index(2),g['order'].index(1))

    def test_cycles_break_and_warn(self):
        g=resolve([[0,0],[1,1]],[relation('Dist',0,[1,0],[1],-1),relation('Dist',1,[1,0],[0],1)])
        self.assertTrue(any(r['reason']=='dependency cycle' for r in g['rejected']))
        self.assertTrue(g['warnings']);self.assertEqual(len(g['order']),2)

    def test_cross_coordinate_dependencies_survive(self):
        # A whole-point graph sees 0 -> 1 -> 0. Each scalar graph is a chain,
        # including a rotated pair of coordinate axes.
        for angle in (0,.3,1.1):
            u=np.array([np.cos(angle),np.sin(angle)]);v=np.array([-u[1],u[0]])
            cs=[relation('Dist',0,u,[1],0,feature='must-survive-x'),
                relation('Dist',1,v,[0],0,feature='must-survive-y'),
                relation('Abs',0,v,value=1),relation('Abs',1,u,value=2)]
            graph=resolve([[0,0],[1,1]],cs)
            self.assertEqual(graph['rejected'],[])
            self.assertEqual({c.get('feature') for c in graph['constraints'] if c['kind']=='Dist'},
                             {'must-survive-x','must-survive-y'})
            rank={cid:i for i,cid in enumerate(graph['scalar_order'])}
            self.assertTrue(all(rank[d]<rank[c['id']] for c in graph['constraints'] for d in c['depends_on']))
            by_point={p:[c for c in graph['constraints'] if c['point']==p] for p in (0,1)}
            for a,b in by_point.values():
                self.assertEqual(int(np.rint(np.array(a['normal'])*16384) @
                                     np.rint(np.array(b['freedom'])*16384)),0)

    def test_oblique_source_projection_waits_for_both_coordinates(self):
        graph=resolve([[0,0],[1,1]],[relation('Dist',1,[1,1],[0],1)])
        target=next(c for c in graph['constraints'] if c['kind']=='Dist')
        self.assertEqual(set(target['depends_on']),{c['id'] for c in graph['constraints'] if c['point']==0})

    def test_shared_ratio_endpoint_has_one_effective_source(self):
        for t,sources in ((0,[1,2]),(1,[2,1])):
            graph=resolve([[0,0],[20,0],[10,0]],[relation('Abs',1,[1,0],value=20),
                relation('PRatio',0,[1,0],sources,t),relation('Dist',2,[1,0],[0],10)])
            self.assertEqual(graph['rejected'],[])
            target=next(c for c in graph['constraints'] if c['kind']=='PRatio')
            self.assertEqual({next(a['point'] for a in graph['constraints'] if a['id']==d)
                              for d in target['depends_on']},{1})

    def test_original_ratio_endpoint_has_one_effective_source(self):
        for t,sources in ((0,[1,2]),(1,[2,1])):
            graph=resolve([[20,0],[20,0],[10,0]],[relation('Abs',1,[1,0],value=20),
                relation('Ratio',0,[1,0],sources,t),relation('Dist',2,[1,0],[0],-10)])
            self.assertEqual(graph['rejected'],[])
            target=next(c for c in graph['constraints'] if c['kind']=='Ratio')
            self.assertEqual({next(a['point'] for a in graph['constraints'] if a['id']==d)
                              for d in target['depends_on']},{1})

    def test_published_priority_classes(self):
        self.assertGreater(priority(relation('PAbs',0,[1,0])),priority(relation('Dist',0,[1,0],metric=True)))
        self.assertGreater(priority(relation('Dist',0,[1,0],metric=True)),priority(relation('Dist',0,[1,0])))
        self.assertGreater(priority(relation('Ratio',0,[1,0])),priority(relation('Abs',0,[1,0])))

if __name__=='__main__':unittest.main()
