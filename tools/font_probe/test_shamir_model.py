"""Model-level invariants, independent of calibration glyph names."""
import tempfile,unittest
from pathlib import Path
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from shamir_geometry import prepare
from shamir_model import feature_model,build_font
from shamir_templates import recognize_templates,instantiate_templates
from test_shamir_features import polygon
from test_shamir_prototype import fixture
from check_shamir_model import residuals


class ModelTests(unittest.TestCase):
    def test_shared_ratio_native_translation(self):
        from array import array
        from fontTools.ttLib import newTable
        from shamir_constraints import relation,resolve,compile_graph
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'ratio.ttf';fixture(path);font=TTFont(path)
            points=np.array(font['glyf']['A'].coordinates,float)
            cs=[relation('Abs',0,[1,0],value=103),relation('Abs',1,[1,0],value=203),
                relation('PRatio',2,[1,0],[0,1],.25)]
            graph=resolve(points,cs);cvt=[]
            def cvt_id(v):
                v=round(v)
                if v not in cvt:cvt.append(v)
                return cvt.index(v)
            from fontTools.ttLib.tables.ttProgram import Program
            font['glyf']['A'].program=Program()
            font['glyf']['A'].program.fromAssembly(compile_graph(graph,cvt_id))
            font['cvt ']=newTable('cvt ');font['cvt '].values=array('h',cvt)
            font['maxp'].maxStackElements=16;font.save(path)
            face=ft.Face(str(path));self.assertEqual(residuals(face,'A',16,graph,1000),[])

    def test_regular_stems_have_counters_and_ladder(self):
        rect=np.array([[0,0],[100,0],[100,700],[0,700]],float)
        m=feature_model(prepare([polygon(rect+[x,0]) for x in (0,200,400)],1000))
        kinds=[f['kind'] for f in m['features']]
        self.assertEqual(kinds.count('counter-x'),2)
        self.assertGreaterEqual(kinds.count('ladder-x'),2)

    def test_template_recognition_wraps_contour_and_reuses_recipe(self):
        m=prepare([polygon([(0,0),(100,0),(100,100),(0,100)])],1000)
        templates={'corner':dict(sequences=[['LR','LR','LR','LR']],constraints=[dict(kind='Dist',point=1,sources=[0],normal=[1,0])])}
        hits=recognize_templates(m,templates);self.assertEqual(len(hits),1)
        points=np.array([p['position'] for p in m['points']]);cs,report=instantiate_templates(m,{i:i for i in range(4)},points,templates)
        self.assertEqual(len(cs),1);self.assertFalse(report['unconfigured'])
        missing={'corner':dict(sequences=templates['corner']['sequences'])}
        _,report=instantiate_templates(m,{i:i for i in range(4)},points,missing)
        self.assertTrue(report['unconfigured'])

    def test_calibration_near_parallel_artifacts_stay_within_one_pixel(self):
        from compare_shamir_pipeline import CHARS
        from check_shamir_model import outline_diagnostics
        sources=Path(__file__).parent/'out/shamir-controlled'
        cases=[('roboto','a'),('literata','e')]
        if not all((sources/f'{name}-14-source.ttf').exists() for name,_ in cases):
            self.skipTest('local calibration source fonts are unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            for name,char in cases:
                with self.subTest(font=name,char=char):
                    output=Path(tmp)/f'{name}.ttf'
                    build_font(sources/f'{name}-14-source.ttf',output,CHARS)
                    observed=outline_diagnostics(ft.Face(str(output)),char,14)
                    # The unstable default moved the Roboto a point 8.58px.
                    # Test the whole outline, including interpolated controls.
                    self.assertLess(observed['max_movement_px'],1)
                    self.assertLess(observed['bounds_expansion_px'],.8)

    def test_roboto_middle_arm_alignment_survives_native_execution(self):
        from compare_shamir_pipeline import CHARS
        from compare_paper_prototypes import render
        source=Path(__file__).parent/'out/shamir-controlled/roboto-14-source.ttf'
        if not source.exists():self.skipTest('local calibration source font unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'font.ttf';report=build_font(source,output,CHARS,normalize=False)
            alignment=next(a for a in report['records']['F']['attachment_resolution']
                           if a['constraint']['feature']=='align-6')
            self.assertEqual(alignment['status'],'selected')
            c=alignment['constraint'];face=ft.Face(str(output));face.set_pixel_sizes(0,14)
            face.load_char('F',ft.FT_LOAD_NO_BITMAP|ft.FT_LOAD_NO_AUTOHINT|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_PEDANTIC)
            points=face.glyph.outline.points
            self.assertEqual(points[c['point']][0],points[c['sources'][0]][0])
            glyph=render(face,'F',14,hinted=True)
            # The middle arm ends at x=6; the former false cycle left an extra
            # pixel at x=6 in this row. Check native raster output as well as math.
            row=glyph['pixels'][5*glyph['width']:6*glyph['width']]
            self.assertEqual(row,[1,1,1,1,1,0])

    def test_native_model_determinism_and_final_relations(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.ttf';a=Path(tmp)/'a.ttf';b=Path(tmp)/'b.ttf';fixture(source)
            ra=build_font(source,a,'AB');rb=build_font(source,b,'AB')
            self.assertEqual(a.read_bytes(),b.read_bytes());self.assertEqual(ra,rb)
            face=ft.Face(str(a))
            for size in (14,16,18,20):
                for char,r in ra['records'].items():
                    self.assertEqual(residuals(face,char,size,r['graph'],1000),[])
                    self.assertTrue(all(a['status'] in ('selected','rejected') for a in r['attachment_resolution']))
                    selected=r['graph']['constraints'];by_point={}
                    for c in selected:by_point.setdefault(c['point'],[]).append(c)
                    self.assertTrue(all(len(cs)==2 for cs in by_point.values()))
                    order=r['graph']['scalar_order'];rank={cid:i for i,cid in enumerate(order)}
                    self.assertTrue(all(rank[d]<rank[c['id']] for c in selected for d in c['depends_on']))

if __name__=='__main__':unittest.main()
