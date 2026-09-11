"""A basic side shared across a complex-feature boundary has one owner."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import freetype as ft
import numpy as np
from shamir_geometry import prepare
from shamir_model import build_font
from shamir_segment_fit import prepared_glyph
from shamir_templates import instantiate_templates,template_members
from test_shamir_features import polygon


class TemplateBoundaryTests(unittest.TestCase):
    def test_external_side_binds_internal_point_but_local_side_keeps_recipe(self):
        model=prepare([polygon([(0,0),(100,0),(100,100),(0,100)])],1000)
        glyph,mapping,_=prepared_glyph(model);points=np.asarray(glyph.coordinates,float)
        hit=dict(name='corner',points=[0,1,2])
        template={'corner':dict(constraints=[dict(kind='Abs',point=1,normal=[1,0]),
                                           dict(kind='Abs',point=1,normal=[0,1])])}
        groups=[dict(members={1,3},normal=[1,0]),dict(members={0,1},normal=[0,1])]
        with patch('shamir_templates.recognize_templates',return_value=[hit]):
            cs,report=instantiate_templates(model,mapping,points,template,groups)
        self.assertEqual([(c['point'],c['normal']) for c in cs],[(1,[0.,1.])])
        self.assertEqual(report['bindings'][0]['reason'],'side crosses template boundary')

    def test_existing_width_binds_duplicate_rounding_but_keeps_shape_relations(self):
        model=prepare([polygon([(0,0),(100,0),(100,100),(0,100)])],1000)
        glyph,mapping,_=prepared_glyph(model);points=np.asarray(glyph.coordinates,float)
        hit=dict(name='corner',points=[0,1,2,3])
        recipes=[dict(kind='Dist',point=1,sources=[0],normal=[1,0]),
                 dict(kind='Dist',point=2,sources=[1],normal=[0,1]),
                 dict(kind='Dist',point=3,sources=[0],normal=[1,0],round=False)]
        template={'corner':dict(constraints=recipes)}
        groups=[dict(members={0,3},normal=[1,0]),dict(members={1,2},normal=[1,0])]
        features=[dict(kind='stem',groups=[0,1],normal=[1,0],width=100)]
        with patch('shamir_templates.recognize_templates',return_value=[hit]):
            cs,report=instantiate_templates(model,mapping,points,template,groups,features)
        self.assertEqual([c['point'] for c in cs],[2,3])
        self.assertEqual(report['bindings'][0]['reason'],'existing basic width')
        self.assertEqual(report['bindings'][0]['features'],[0])

    def test_controls_and_skipped_joins_belong_to_contour_span(self):
        model=prepare([polygon([(0,0),(50,0),(100,0),(100,100),(0,100)])],1000)
        # Add a quadratic control to an otherwise straight segment. Ownership
        # follows encoded contour support, independently of point categories.
        model['segments'][0]['control'].insert(1,[25,0])
        glyph,mapping,_=prepared_glyph(model)
        owned=template_members(model,mapping,dict(points=[0,2,3]))
        self.assertEqual(owned,{0,1,2,3,4})
        template={'corner':dict(constraints=[dict(kind='Abs',point=1,normal=[1,0])])}
        group=dict(members={mapping[2],1},normal=[1,0])
        with patch('shamir_templates.recognize_templates',return_value=[dict(name='corner',points=[0,2,3])]):
            cs,report=instantiate_templates(model,mapping,np.asarray(glyph.coordinates,float),template,[group])
        self.assertEqual(len(cs),1);self.assertEqual(report['bindings'],[])

    def test_native_shared_sides_full_repertoire_all_sizes(self):
        from compare_shamir_pipeline import CHARS
        sources=Path(__file__).parent/'out/shamir-controlled'
        if not (sources/'literata-14-source.ttf').exists():self.skipTest('local calibration sources unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            for size in (14,16,18,20):
                output=Path(tmp)/f'literata-{size}.ttf'
                report=build_font(sources/f'literata-{size}-source.ttf',output,CHARS)
                face=ft.Face(str(output));face.set_pixel_sizes(0,size)
                for char,pairs in [('H',[(28,44),(28,45)]),('4',[(22,23)]),('r',[(57,58)])]:
                    with self.subTest(size=size,char=char):
                        face.load_char(char,ft.FT_LOAD_NO_BITMAP|ft.FT_LOAD_NO_AUTOHINT|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_PEDANTIC)
                        points=face.glyph.outline.points
                        for a,b in pairs:self.assertEqual(points[a][0],points[b][0])
                        if size==20:
                            self.assertTrue(any(c.get('feature')=='BracketedFoot' for c in report['records'][char]['graph']['constraints']))


if __name__=='__main__':unittest.main()
