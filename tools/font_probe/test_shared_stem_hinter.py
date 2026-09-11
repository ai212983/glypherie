import copy
import unittest
import numpy as np
from shared_stem_hinter import fit,Unsupported


class OwnStemTests(unittest.TestCase):
    def fixture(self):
        points=np.array([(0,100),(0,0),(20,0),(20,50),(18,100)],float)
        constraints=[dict(id=2*i+a,kind='Abs',point=i,normal=np.eye(2)[a].tolist(),sources=[],value=p[a],round=False,depends_on=[]) for i,p in enumerate(points) for a in (0,1)]
        features=[dict(kind='slant',groups=[0,1],points=[0,4],normal=[1,.04],width=19),dict(kind='stem',groups=[0,2],points=[0,2],normal=[1,0],width=20)]
        attachments=[dict(constraint=dict(feature=f'align-{g}',point=i,sources=[j])) for g,i,j in [(0,0,1),(1,4,3),(2,3,2)]]
        return points,dict(features=features,graph=dict(order=list(range(5)),constraints=constraints),attachment_resolution=attachments)

    def test_shared_support_width_and_input_preservation(self):
        p,r=self.fixture();saved=copy.deepcopy(r)
        result,audit=fit(p,r,10,100)
        self.assertTrue(np.allclose(result[[2,3,4],0],2))
        self.assertEqual(audit['supports'][0]['fitted_width'],2)
        self.assertEqual(r,saved)

    def test_no_match_is_unaffected(self):
        p,r=self.fixture();r['features']=r['features'][:1]
        result,audit=fit(p,r,10,100)
        self.assertIsNone(result);self.assertEqual(audit['status'],'unaffected')

    def test_ambiguous_reference_is_held(self):
        p,r=self.fixture();other=copy.deepcopy(r['features'][1]);other['width']=21;r['features'].append(other)
        with self.assertRaisesRegex(Unsupported,'ambiguous'):fit(p,r,10,100)

    def test_collapsing_stem_is_held(self):
        p,r=self.fixture()
        with self.assertRaisesRegex(Unsupported,'zero width'):fit(p,r,1,100)

    def test_diagonal_consumes_fitted_support(self):
        p,r=self.fixture();p=np.vstack([p,[40,20]])
        n=np.array([.7071067811865476,.7071067811865476])
        cs=r['graph']['constraints']
        cs[8].update(kind='Dist',normal=n.tolist(),sources=[5],value=float((p[4]-p[5])@n),round=False,feature='align-99')
        cs.extend([dict(id=10,kind='Abs',point=5,normal=n.tolist(),sources=[],value=float(p[5]@n),round=False),
                   dict(id=11,kind='Abs',point=5,normal=[0,1],sources=[],value=20,round=False)])
        r['graph']['order'].append(5)
        result,audit=fit(p,r,10,100)
        self.assertEqual(len(audit['reversed_alignments']),1)
        self.assertLess(audit['order'].index(4),audit['order'].index(5))
        self.assertAlmostEqual(float((result[5]-result[4])@n),float((p[5]-p[4])@n)*.1)

    def test_end_cap_coordination_preserves_larger_flare(self):
        for cap,expected in [(22,2),(28,2.8)]:
            p,r=self.fixture();p[4,1]=80;p=np.vstack([p,[cap,100]])
            cs=r['graph']['constraints'];cs[9]['value']=80
            cs.extend([dict(id=10+a,kind='Abs',point=5,normal=np.eye(2)[a].tolist(),sources=[],value=p[5,a],round=False) for a in (0,1)])
            r['graph']['order'].append(5)
            result,audit=fit(p,r,10,100,coordinate=True,ends=[5],flags=[1]*6)
            self.assertAlmostEqual(result[5,0],expected)
