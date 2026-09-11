"""Native interpolation precision, including narrow spans and extrapolation."""
from array import array
from pathlib import Path
import tempfile
import unittest

import freetype as ft
import numpy as np
from fontTools.ttLib import TTFont,newTable
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.ttLib.tables.ttProgram import Program
from shamir_constraints import relation,resolve,compile_graph,ratio_coefficient
from shamir_prototype import push
from test_shamir_prototype import fixture


def native(points,candidates,legacy_ip=False):
    """Run the actual native compiler; optional IP demonstrates its old error."""
    graph=resolve(points,candidates);cvt=[]
    def cvt_id(value):
        value=round(value)
        if value not in cvt:cvt.append(value)
        return cvt.index(value)
    assembly=[]
    for c in graph['constraints']:
        if legacy_ip and c['kind']=='Ratio':
            a,b=c['sources']
            assembly+=push(*np.rint(np.array(c['normal'])*16384).astype(int))+['SPVFS[ ]']
            assembly+=push(*np.rint(np.array(c['freedom'])*16384).astype(int))+['SFVFS[ ]']
            assembly+=push(a)+['SRP1[ ]']+push(b)+['SRP2[ ]']+push(c['point'])+['IP[ ]']
        else:assembly+=compile_graph(dict(constraints=[c]),cvt_id)
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'ratio.ttf';fixture(path);font=TTFont(path)
        glyph=font['glyf']['A'];glyph.coordinates=GlyphCoordinates(points)
        glyph.program=Program();glyph.program.fromAssembly(assembly)
        font['cvt ']=newTable('cvt ');font['cvt '].values=array('h',cvt)
        font['maxp'].maxStackElements=32;font.save(path)
        face=ft.Face(str(path));face.set_pixel_sizes(0,16)
        face.load_char('A',ft.FT_LOAD_NO_BITMAP|ft.FT_LOAD_NO_AUTOHINT|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_PEDANTIC)
        return np.array(face.glyph.outline.points)/64,graph


class RatioPrecisionTests(unittest.TestCase):
    def test_narrow_projected_original_span_retains_coefficient(self):
        points=np.array([[103,0],[108,10],[106,7],[103,20]])
        n=np.array([.98,.2]);n/=np.linalg.norm(n)
        t=float((points[2]-points[0])@n/((points[1]-points[0])@n))
        candidates=[relation('Abs',0,n,value=100,round=False),
                    relation('Abs',1,n,value=600,round=False),
                    relation('Ratio',2,n,[0,1],t)]
        actual,graph=native(points,candidates);old,_=native(points,candidates,legacy_ip=True)
        def error(p):return abs(float((p[2]-(1-t)*p[0]-t*p[1])@n))
        self.assertLess(error(actual),.035)
        self.assertGreater(error(old),.2)
        self.assertEqual(next(c for c in graph['constraints'] if c['kind']=='Ratio')['value'],t)

    def test_signed_extrapolation_exceeds_push_word_range(self):
        for t in (-2.5,2.5):
            with self.subTest(t=t):
                points=np.array([[103,0],[113,0],[103+int(t*10),10],[103,20]])
                actual,_=native(points,[relation('Abs',0,[1,0],value=100,round=False),
                    relation('Abs',1,[1,0],value=200,round=False),
                    relation('Ratio',2,[1,0],[0,1],t)])
                self.assertAlmostEqual(actual[2,0],(1-t)*actual[0,0]+t*actual[1,0],delta=.035)

    def test_original_ratio_is_derived_and_shared_ratio_is_authored(self):
        points=[[0,0],[100,0],[25,0]]
        for kind,wanted in [('Ratio',.25),('PRatio',.75)]:
            graph=resolve(points,[relation(kind,2,[1,0],[0,1],.75)])
            self.assertEqual(next(c for c in graph['constraints'] if c['kind']==kind)['value'],wanted)

    def test_zero_span_translates_original_offset_from_first_anchor(self):
        points=np.array([[103,0],[103,10],[113,10],[103,20]])
        actual,graph=native(points,[relation('Abs',0,[1,0],value=200,round=False),
            relation('Abs',1,[1,0],value=600,round=False),relation('Ratio',2,[1,0],[0,1],None)])
        c=next(c for c in graph['constraints'] if c.get('degenerate_ratio'))
        self.assertEqual((c['kind'],c['sources'],c['value']),('Dist',[0],10))
        self.assertAlmostEqual(actual[2,0]-actual[0,0],.16,delta=.02)

    def test_quantized_endpoint_dependencies_match_execution(self):
        points=[[.000001,0],[0,0],[1,0]]
        graph=resolve(points,[relation('Abs',1,[1,0],value=10),
            relation('Ratio',0,[1,0],[1,2],.000001),relation('Dist',2,[1,0],[0],1)])
        self.assertEqual(graph['rejected'],[])
        c=next(c for c in graph['constraints'] if c['kind']=='Ratio')
        self.assertEqual(ratio_coefficient(c),0)
        self.assertEqual({next(a['point'] for a in graph['constraints'] if a['id']==d) for d in c['depends_on']},{1})

    def test_unrepresentable_coefficients_fail_explicitly(self):
        for t in (float('inf'),2**20,-2**20):
            with self.subTest(t=t),self.assertRaises(ValueError):
                ratio_coefficient(relation('Ratio',0,[1,0],[1,2],t))


if __name__=='__main__':unittest.main()
