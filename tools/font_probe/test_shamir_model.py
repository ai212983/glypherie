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

    def test_v_side_keeps_single_group_with_own_normal(self):
        # B06 regression shape (Source Sans 3 V class): one physical side
        # shared by two features keeps a single group carrying the side's
        # own alignment normal, never a duplicate group with a feature
        # projection normal.
        from shamir_features import recognize
        from shamir_geometry import unit
        chevron = [(0, 700), (150, 0), (300, 700),
                   (250, 700), (150, 200), (50, 700)]
        model = prepare([polygon(chevron)], 1000)
        side_normal = {}
        for sid, side in enumerate(recognize(model)['sides']):
            direction = np.asarray(side['direction'], float)
            normal = unit(np.array([-direction[1], direction[0]]))
            if normal[np.argmax(abs(normal))] < 0:
                normal = -normal
            side_normal[sid] = normal
        groups = [g for g in feature_model(model, baseline=True)['groups']
                  if g['members']]
        by_side = {}
        for group in groups:
            for sid in group.get('source_sides', []) or []:
                by_side.setdefault(sid, []).append(group)
        self.assertTrue(by_side)
        for sid, sharing in by_side.items():
            self.assertEqual(len(sharing), 1,
                             (sid, [g['members'] for g in sharing]))
            dot = abs(float(np.asarray(sharing[0]['normal'])
                            @ side_normal[sid]))
            self.assertGreater(dot, 1 - 1e-12, (sid, sharing[0]['normal']))

    def test_membership_radius_is_live_and_defaults_to_one(self):
        # B06 one-font-unit membership: the radius knob changes attachment
        # (strict growth here), while the default equals an explicit 1.
        # Scope, verified adversarially: these multisets are set by the
        # radius with recognize sides plus height/extrema support; they do
        # not cover the transitive merge loop, collinear merging or rint.
        from test_shamir_features import polygon
        shape = [(0, 0), (100, 0), (100, 5), (60, 5), (60, 6), (60, 7), (0, 7)]
        model = prepare([polygon(shape)], 1000)

        def signature(m):
            return sorted(
                (tuple(sorted(g['members'])),
                 tuple(np.round(np.asarray(g['normal']), 12)))
                for g in m['groups'] if g['members'])

        from shamir_model import feature_model as fm
        narrow = fm(model, baseline=True, membership_fu=0)
        default = fm(model, baseline=True)
        explicit = fm(model, baseline=True, membership_fu=1)
        self.assertEqual(sorted(len(g['members']) for g in narrow['groups']
                                if g['members']), [2, 2, 2, 3, 4])
        self.assertEqual(sorted(len(g['members']) for g in default['groups']
                                if g['members']), [2, 2, 2, 3, 5])
        self.assertEqual(signature(explicit), signature(default))
        self.assertLess(sum(len(g['members']) for g in narrow['groups']),
                        sum(len(g['members']) for g in default['groups']))

    def test_membership_radius_one_keeps_side_uniqueness_on_calibration(self):
        # B06 bound: at the assumed radius no physical side splits into
        # non-parallel groups on any of the 243 calibration outlines.
        # Measured sensitivity for the record: regrouped-vs-radius-1 glyph
        # counts are 30 at 0, 41 at 2, 59 at 3 (side-identity merge keeps
        # same-side uniqueness at every radius; the radius moves attachment
        # extent, not side identity).
        import itertools
        from pathlib import Path
        from fontTools.ttLib import TTFont
        from compare_shamir_pipeline import CHARS
        from shamir_geometry import from_font
        from shamir_model import feature_model as fm
        root = Path(__file__).parent / 'fonts'
        bad = []
        for filename in ('Roboto.ttf', 'Literata.ttf', 'SourceSans3.ttf'):
            font = TTFont(str(root / filename), recalcTimestamp=False)
            for char in CHARS:
                groups = [g for g in fm(from_font(font, char, baseline=True),
                                        baseline=True)['groups'] if g['members']]
                by_side = {}
                for group in groups:
                    for sid in group.get('source_sides', []) or []:
                        by_side.setdefault(sid, []).append(group)
                for sid, sharing in by_side.items():
                    for first, second in itertools.combinations(sharing, 2):
                        dot = abs(float(np.asarray(first['normal'])
                                        @ np.asarray(second['normal'])))
                        if dot <= 1 - 1e-12:
                            bad.append((filename, char, sid))
        self.assertEqual(bad, [], bad[:5])

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
