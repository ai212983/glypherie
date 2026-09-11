"""Geometric taper recognition and executed cap relationships."""
import tempfile,unittest
from pathlib import Path
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
from shamir_geometry import prepare,from_font
from shamir_templates import recognize_templates,calibration_templates
from shamir_model import build_font
from shamir_segment_fit import prepared_glyph
from test_shamir_features import polygon
from test_shamir_prototype import fixture
from compare_paper_prototypes import render,pixels


class TaperTests(unittest.TestCase):
    def hits(self,points):
        return recognize_templates(prepare([polygon(points)],1000),calibration_templates())

    def test_complete_taper_matches_all_encodings_and_orientations(self):
        taper=np.array([[100,600],[200,600],[180,100],[120,100]],float)
        for angle in (0,.3,np.pi/2,2.4):
            matrix=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
            for reverse in (False,True):
                for start in range(4):
                    points=np.roll(taper@matrix.T,start,axis=0)
                    if reverse:points=points[::-1]
                    hits=self.hits(points)
                    self.assertEqual([h['name'] for h in hits],['TaperedStroke'])
                    hit=hits[0];p=points[hit['points']];n=np.array(hit['frame'][0])
                    self.assertAlmostEqual(float((p[1]-p[0])@n),100)
                    self.assertAlmostEqual(float((p[3]-p[2])@n),60)

    def test_rectangle_short_wedge_and_nonconvex_shape_rejected(self):
        for p in ([[100,600],[200,600],[200,100],[100,100]],
                  [[100,200],[200,200],[180,100],[120,100]],
                  [[100,600],[200,600],[140,300],[120,100]]):
            self.assertFalse(any(h['name']=='TaperedStroke' for h in self.hits(p)))

    def test_tapered_counter_is_not_a_stroke(self):
        outer=polygon([(0,0),(300,0),(300,700),(0,700)])
        hole=polygon([(100,600),(200,600),(180,100),(120,100)])
        hits=recognize_templates(prepare([outer,hole],1000),calibration_templates())
        self.assertFalse(any(h['name']=='TaperedStroke' for h in hits))

    def test_subpixel_collapse_is_reported_without_a_width_floor(self):
        points=[(100,300),(120,300),(115,100),(105,100)]
        hit=next(h for h in self.hits(points) if h['name']=='TaperedStroke')
        self.assertEqual(hit['wide_cap_units'],20)
        self.assertEqual(hit['half_pixel_ppem'],25)
        self.assertIn('may collapse',hit['width_policy'])
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.ttf';output=Path(tmp)/'out.ttf';fixture(source);font=TTFont(source)
            for cmap in font['cmap'].tables:
                if cmap.isUnicode():cmap.cmap[33]='A'
            pen=TTGlyphPen(None);pen.moveTo(points[0])
            for point in points[1:]:pen.lineTo(point)
            pen.closePath();font['glyf']['A']=pen.glyph();font.save(source)
            report=build_font(source,output,'!')
            self.assertTrue(any(h.get('half_pixel_ppem')==25 for h in report['records']['!']['templates']['matches']))
            face=ft.Face(str(output));face.set_pixel_sizes(0,14)
            face.load_char('!',ft.FT_LOAD_NO_BITMAP|ft.FT_LOAD_NO_AUTOHINT|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_PEDANTIC)
            self.assertEqual(np.ptp(np.array(face.glyph.outline.points)[:,0]),0)

    def assert_cap_ratio(self,path,record,size,expected):
        font=TTFont(path);geometry=from_font(font,'!')
        hit=next(h for h in recognize_templates(geometry,calibration_templates()) if h['name']=='TaperedStroke')
        _,mapping,_=prepared_glyph(geometry)
        # Straight taper points retain their order in the final TrueType glyph.
        self.assertTrue(all(s['kind']=='line' for s in geometry['segments'] if s['contour']==geometry['points'][hit['points'][0]]['contour']))
        ids=[mapping[p] for p in hit['points']];n=np.array(hit['frame'][0])
        face=ft.Face(str(path));face.set_pixel_sizes(0,size)
        face.load_char('!',ft.FT_LOAD_NO_BITMAP|ft.FT_LOAD_NO_AUTOHINT|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_PEDANTIC)
        p=np.array(face.glyph.outline.points,float)/64
        wide=float((p[ids[1]]-p[ids[0]])@n);narrow=float((p[ids[3]]-p[ids[2]])@n)
        self.assertGreater(wide,0);self.assertGreater(narrow,0)
        self.assertAlmostEqual(narrow/wide,expected,delta=.035)
        selected=record['graph']['constraints']
        self.assertEqual(sum(c.get('feature')=='TaperedStroke' and c['kind']=='Ratio' for c in selected),2)

    def assert_components(self,path,size,expected):
        remaining=pixels(render(ft.Face(str(path)),'!',size,hinted=True));components=0
        while remaining:
            components+=1;pending=[remaining.pop()]
            while pending:
                x,y=pending.pop()
                neighbors={(x+dx,y+dy) for dx in (-1,0,1) for dy in (-1,0,1)}&remaining
                remaining.difference_update(neighbors);pending.extend(neighbors)
        self.assertEqual(components,expected)

    def test_native_source_taper_full_repertoire(self):
        from compare_shamir_pipeline import CHARS
        root=Path(__file__).parent/'out/shamir-controlled'
        if not (root/'source-sans-3-14-source.ttf').exists():self.skipTest('local calibration source fonts unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('roboto','source-sans-3'):
                for size in (14,16,18,20):
                    with self.subTest(font=name,size=size):
                        output=Path(tmp)/f'{name}-{size}.ttf';report=build_font(root/f'{name}-{size}-source.ttf',output,CHARS)
                        record=report['records']['!'];hit=next(h for h in record['templates']['matches'] if h['name']=='TaperedStroke')
                        self.assert_cap_ratio(output,record,size,hit['narrow_cap_units']/hit['wide_cap_units'])
                        self.assertEqual(len(record['templates']['bindings']),4)
                        self.assertTrue(record['template_ownership'])
                        self.assert_components(output,size,2)

    def test_near_parallel_taper_owns_transverse_basic_features(self):
        taper=np.array([[100,600],[200,600],[195,100],[105,100]])
        for rotation in (np.eye(2),np.array([[0,-1],[1,0]]),-np.eye(2),np.array([[0,1],[-1,0]])):
            with tempfile.TemporaryDirectory() as tmp:
                source=Path(tmp)/'source.ttf';output=Path(tmp)/'out.ttf';fixture(source);font=TTFont(source)
                for cmap in font['cmap'].tables:
                    if cmap.isUnicode():cmap.cmap[33]='A'
                points=taper@rotation.T;pen=TTGlyphPen(None);pen.moveTo(tuple(points[0]))
                for point in points[1:]:pen.lineTo(tuple(point))
                pen.closePath();font['glyf']['A']=pen.glyph();font.save(source);report=build_font(source,output,'!')
                record=report['records']['!']
                self.assertTrue(any(f['kind'] in ('stem','bar') for owner in record['template_ownership'] for f in owner['suppressed_features']))
                for size in (14,16,18,20):self.assert_cap_ratio(output,record,size,.9)

    def test_noncardinal_native_recipe_is_explicitly_unconfigured(self):
        taper=np.array([[100,600],[200,600],[180,100],[120,100]],float)
        for angle in (.1,.7,1.2):
            with self.subTest(angle=angle),tempfile.TemporaryDirectory() as tmp:
                source=Path(tmp)/'source.ttf';output=Path(tmp)/'out.ttf';fixture(source);font=TTFont(source)
                for cmap in font['cmap'].tables:
                    if cmap.isUnicode():cmap.cmap[33]='A'
                matrix=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
                p=np.rint(taper@matrix.T);pen=TTGlyphPen(None);pen.moveTo(tuple(p[0]))
                for point in p[1:]:pen.lineTo(tuple(point))
                pen.closePath();font['glyf']['A']=pen.glyph();font.save(source)
                record=build_font(source,output,'!')['records']['!']
                self.assertTrue(record['templates']['unconfigured'])
                self.assertIn('noncardinal',record['templates']['unconfigured'][0]['reason'])
                self.assertFalse(record['template_ownership'])
                self.assertFalse(any(c.get('feature')=='TaperedStroke' for c in record['graph']['constraints']))

    def test_native_synthetic_taper(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.ttf';output=Path(tmp)/'out.ttf';fixture(source);font=TTFont(source)
            for cmap in font['cmap'].tables:
                if cmap.isUnicode():cmap.cmap[33]='A'
            pen=TTGlyphPen(None);pen.moveTo((100,600));pen.lineTo((200,600));pen.lineTo((180,100));pen.lineTo((120,100));pen.closePath()
            font['glyf']['A']=pen.glyph();font.save(source)
            report=build_font(source,output,'!')
            for size in (14,16,18,20):
                self.assert_cap_ratio(output,report['records']['!'],size,.6)
                self.assert_components(output,size,1)

if __name__=='__main__':unittest.main()
