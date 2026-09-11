"""Frozen-input regressions and geometry invariance for local recovery."""
import unittest
from pathlib import Path
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from junction_terminal_fit import fit
from audit_terminal_coverage import coords
from compare_paper_prototypes import render,pixels

ROOT=Path(__file__).resolve().parent/'out'

class JunctionTests(unittest.TestCase):
    def data(self,size,char):
        path=ROOT/'geometric-candidate-v3'/f'roboto-{size}-candidate.ttf'
        if not path.exists():self.skipTest('frozen local specimen unavailable')
        with TTFont(path) as f:
            p,e,t=f['glyf'][f.getBestCmap()[ord(char)]].getCoordinates(f['glyf']);scale=size/f['head'].unitsPerEm
        return np.asarray(p,float),e,t,coords(ft.Face(str(path)),char,size),scale,path

    def test_cap_source_vector_and_locality(self):
        p,e,t,q,s,path=self.data(16,'f');out,audit=fit(p,e,t,q,s)
        self.assertAlmostEqual(out[17,0]-out[16,0],(p[17,0]-p[16,0])*s)
        np.testing.assert_array_equal(out[:12],q[:12]);np.testing.assert_array_equal(out[22:],q[22:])
        self.assertTrue(audit)

    def test_cap_thickness_preserved(self):
        for size,char in [(16,'f'),(18,'f'),(16,'r'),(18,'r')]:
            with self.subTest(size=size,char=char):
                p,e,t,q,s,_=self.data(size,char);out,audit=fit(p,e,t,q,s)
                caps=[a for a in audit if a['kind']=='curved-cap']
                self.assertTrue(caps)
                for cap in caps:
                    a,b=cap['endpoints'];axis=cap['thickness_axis']
                    self.assertAlmostEqual(out[b,axis]-out[a,axis],q[b,axis]-q[a,axis])

    def test_horizontal_mirror(self):
        p,e,t,q,s,_=self.data(16,'f');a,_=fit(p,e,t,q,s)
        p[:,0]*=-1;q[:,0]*=-1;b,_=fit(p,e,t,q,s);b[:,0]*=-1
        np.testing.assert_allclose(a,b,atol=1e-9)

    def test_closed_round_is_not_a_cap(self):
        p,e,t,q,s,_=self.data(16,'O');out,audit=fit(p,e,t,q,s)
        np.testing.assert_array_equal(out,q);self.assertEqual(audit,[])

    def test_owned_cap_held(self):
        p,e,t,q,s,_=self.data(16,'f')
        with self.assertRaisesRegex(ValueError,'owned coordinate'):
            fit(p,e,t,q,s,ownership=[dict(point=17,axis=0)])

    def test_small_existing_hook_bitmap_retained(self):
        p,e,t,q,s,path=self.data(14,'f');out,_=fit(p,e,t,q,s);face=ft.Face(str(path))
        self.assertEqual(pixels(render(face,'f',14,hinted=True)),pixels(render(face,'f',14,hinted=True,points=out)))

    def test_repaired_bar_grid_and_corner(self):
        p,e,t,q,s,_=self.data(16,'4')
        path=ROOT/'cumulative-hinter-v6/roboto-16-u0034-current.ttf'
        q=coords(ft.Face(str(path)),'4',16)
        out,audit=fit(p,e,t,q,s,order=[dict(a=6,b=7,axis=1)])
        self.assertEqual(out[6,1],3);self.assertEqual(out[0,1],4)
        self.assertAlmostEqual(out[7,1]-out[6,1],(p[7,1]-p[6,1])*s)
        ink=pixels(render(ft.Face(str(path)),'4',16,hinted=True,points=out))
        self.assertNotIn((0,-3),ink);self.assertIn((0,-4),ink)

if __name__=='__main__':unittest.main()
