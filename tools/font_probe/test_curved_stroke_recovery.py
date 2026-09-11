"""Whole-stroke geometry and native raster regressions against frozen inputs."""
import unittest
from pathlib import Path
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from audit_terminal_coverage import coords
from curved_stroke_recovery import fit
from compare_paper_prototypes import render,pixels

ROOT=Path(__file__).resolve().parent/'out'

class WholeStrokeTests(unittest.TestCase):
    def data(self,size=18,char='f'):
        path=ROOT/'geometric-candidate-v3'/f'roboto-{size}-candidate.ttf'
        if not path.exists():self.skipTest('frozen specimen unavailable')
        with TTFont(path) as f:
            p,e,t=f['glyf'][f.getBestCmap()[ord(char)]].getCoordinates(f['glyf']);scale=size/f['head'].unitsPerEm
        return np.asarray(p,float),e,t,coords(ft.Face(str(path)),char,size),scale,path

    def test_inner_curve_stays_on_stroke_side(self):
        p,e,t,q,s,_=self.data();out,audit=fit(p,e,t,q,s)
        self.assertLess(q[25,0],q[27,0])
        self.assertGreaterEqual(out[25,0],out[27,0])
        for event in audit:
            if event['kind']!='whole-curved-stroke':continue
            np.testing.assert_array_equal(out[event['attachments']],q[event['attachments']])
            ax=event['thickness_axis']
            np.testing.assert_array_equal(out[event['extrema'],ax],q[event['extrema'],ax])
        np.testing.assert_array_equal(out[:6],q[:6]);np.testing.assert_array_equal(out[28:],q[28:])

    def test_mirror(self):
        p,e,t,q,s,_=self.data();a,_=fit(p,e,t,q,s)
        p[:,0]*=-1;q[:,0]*=-1;b,_=fit(p,e,t,q,s);b[:,0]*=-1
        np.testing.assert_allclose(a,b,atol=1e-9)

    def test_input_and_ownership_preserved(self):
        p,e,t,q,s,_=self.data();before=q.copy();fit(p,e,t,q,s)
        np.testing.assert_array_equal(q,before)
        with self.assertRaisesRegex(ValueError,'owned coordinate'):
            fit(p,e,t,q,s,ownership=[dict(point=25,axis=0)])

    def test_curve_has_continuous_eight_connected_ink(self):
        p,e,t,q,s,path=self.data();out,_=fit(p,e,t,q,s)
        ink=pixels(render(ft.Face(str(path)),'f',18,hinted=True,points=out))
        todo=[next(iter(ink))];seen=set(todo)
        while todo:
            x,y=todo.pop()
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    v=x+dx,y+dy
                    if v in ink and v not in seen:seen.add(v);todo.append(v)
        self.assertEqual(seen,ink)

if __name__=='__main__':unittest.main()
