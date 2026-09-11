import ast
import inspect
import unittest
import numpy as np
import opposing_terminals as module


class OpposingTests(unittest.TestCase):
    def setUp(self):
        self.p=np.array([(0,100),(70,100),(80,75),(70,72),(65,90),(50,90),(20,90),
                         (20,10),(50,10),(65,10),(72,25),(82,25),(72,0),(0,0)],float)
        self.flags=np.ones(14,int);self.flags[[4,9]]=0

    def test_detection_is_contour_start_and_winding_independent(self):
        for direction in (1,-1):
            for shift in range(14):
                p=np.roll(self.p[::direction],shift,axis=0)
                flags=np.roll(self.flags[::direction],shift)
                pairs=module.detect(p,[13],flags,100)
                self.assertEqual(len(pairs),1)
                self.assertEqual({tuple(p[r['outer']]) for r in pairs[0]}, {(80,75),(82,25)})

    def test_shared_lengths_and_source_slopes_preserve_unrelated_points(self):
        pair=module.detect(self.p,[13],self.flags,100)[0]
        before=self.p*.1
        for shared in (False,True):
            after,audit=module.fit(self.p,before,pair,.1,shared)
            owned={r['outer'] for r in pair}|{i for r in pair for i in r['members']}
            self.assertTrue(all(np.array_equal(after[i],before[i]) for i in range(14) if i not in owned))
            for r in pair:
                a=after[r['inner']]-after[r['outer']];b=np.array(r['tip_vector'])
                self.assertAlmostEqual(a[0]*b[1]-a[1]*b[0],0)
            if shared:self.assertEqual(audit[0]['length_px'],audit[1]['length_px'])

    def test_rule_api_has_no_identity_or_io(self):
        tree=ast.parse(inspect.getsource(module))
        banned={'char','glyph','codepoint','family','ord','chr','open','eval','exec'}
        for node in ast.walk(tree):
            if isinstance(node,ast.Name):self.assertNotIn(node.id,banned)
            if isinstance(node,ast.Constant) and isinstance(node.value,str):self.assertNotIn(node.value,banned)
        self.assertEqual(list(inspect.signature(module.detect).parameters),['points','ends','flags','em'])


if __name__=='__main__':unittest.main()
