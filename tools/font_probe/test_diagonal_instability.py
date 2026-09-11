import unittest
import numpy as np
from diagonal_instability import inspect_graph,cardinal_override
from shamir_baseline_solver import evaluate_baseline


def fixture():
    p=np.array([[0.,0.],[2.,0.]])
    cs=[dict(id=0,kind='Abs',point=0,normal=[1,0],sources=[],value=0,round=False),dict(id=1,kind='Abs',point=0,normal=[0,1],sources=[],value=0,round=False)]
    n=np.array([1,.04]);n=n/np.linalg.norm(n)
    cs.extend([dict(id=2,kind='Dist',point=1,normal=n.tolist(),sources=[0],value=float(p[1]@n),feature='width-1'),dict(id=3,kind='Dist',point=1,normal=[1,0],sources=[0],value=2,round=False,feature='align-0')])
    return p,dict(order=[0,1],constraints=cs)


class InstabilityTests(unittest.TestCase):
    def test_safe_pair_unchanged(self):
        p,g=fixture();g['constraints'][3]['normal']=[0,1];g['constraints'][3]['value']=0
        new,report=cardinal_override(g,p);self.assertEqual(report,[]);self.assertEqual(new,g)

    def test_replacement_preserves_width_and_parent_offset(self):
        p,g=fixture();new,report=cardinal_override(g,p);a,_=evaluate_baseline(new,p,16,1000)
        n=np.array(g['constraints'][2]['normal'])
        self.assertAlmostEqual(float((a[1]-a[0])@n),0)
        self.assertAlmostEqual(a[1,1]-a[0,1],0)
        self.assertEqual(report[0]['status'],'overridden');self.assertEqual(g['constraints'][3]['feature'],'align-0')

    def test_non_alignment_is_explicitly_held(self):
        p,g=fixture();g['constraints'][3]['feature']='width-2'
        new,r=cardinal_override(g,p);self.assertEqual(r[0]['status'],'held');self.assertEqual(new,g)

    def test_guard_matches_vtt_boundary(self):
        p,g=fixture();g['constraints'][2]['normal']=[np.sqrt(1-.07**2),.07]
        self.assertEqual(inspect_graph(g),[])
        g['constraints'][2]['normal']=[np.sqrt(1-.05**2),.05]
        self.assertEqual(len(inspect_graph(g)),1)

if __name__=='__main__':unittest.main()
