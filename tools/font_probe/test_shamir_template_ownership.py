"""Template ports inherit existing stroke coordinates; internal shape remains."""
import tempfile
import unittest
from pathlib import Path

import freetype as ft
import numpy as np

from shamir_geometry import prepare
from shamir_model import build_font
from shamir_templates import calibration_templates,instantiate_templates
from test_shamir_features import polygon


class TemplateOwnershipTests(unittest.TestCase):
    def test_port_binds_only_the_existing_projection(self):
        geometry=prepare([polygon([(0,0),(100,0),(100,100),(0,100)])],1000)
        points=np.array([p['position'] for p in geometry['points']])
        template={'corner':dict(sequences=[['LR','LR','LR','LR']],ports=[0],constraints=[
            dict(kind='Abs',point=0,normal=[1,0]),
            dict(kind='Abs',point=0,normal=[0,1]),
            dict(kind='Dist',point=1,sources=[0],normal=[1,0])])}
        groups=[dict(members={0},normal=[-1,0],rep=0)]
        cs,report=instantiate_templates(geometry,{i:i for i in range(4)},points,template,groups)
        self.assertEqual(len(report['bindings']),1)
        self.assertEqual(report['bindings'][0]['point'],0)
        self.assertEqual(report['bindings'][0]['groups'],[0])
        self.assertEqual([(c['point'],c['normal']) for c in cs],[(0,[0.,1.]),(1,[1.,0.])])

    def test_unbound_port_retains_authored_constraint(self):
        geometry=prepare([polygon([(0,0),(100,0),(100,100),(0,100)])],1000)
        points=np.array([p['position'] for p in geometry['points']])
        template={'corner':dict(sequences=[['LR','LR','LR','LR']],ports=[0],constraints=[
            dict(kind='Abs',point=0,normal=[1,0])])}
        cs,report=instantiate_templates(geometry,{i:i for i in range(4)},points,template)
        self.assertEqual(len(cs),1)
        self.assertEqual(report['bindings'],[])

    def test_plain_terminals_use_basic_features(self):
        self.assertNotIn('FlatTerminal',calibration_templates())

    def test_full_repertoire_preserves_stem_ports_in_native_outline(self):
        from compare_shamir_pipeline import CHARS
        sources=Path(__file__).parent/'out/shamir-controlled'
        cases=[('roboto','H',8,9),('literata','m',36,38)]
        if not all((sources/f'{name}-16-source.ttf').exists() for name,_,_,_ in cases):
            self.skipTest('local calibration source fonts unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            for name,char,a,b in cases:
                with self.subTest(font=name,char=char):
                    output=Path(tmp)/f'{name}.ttf'
                    # Keep source contour indexing to isolate template ownership
                    # from the separate overlap-normalization correction.
                    report=build_font(sources/f'{name}-16-source.ttf',output,CHARS,normalize=False)
                    face=ft.Face(str(output));face.set_pixel_sizes(0,16)
                    face.load_char(char,ft.FT_LOAD_NO_BITMAP|ft.FT_LOAD_NO_AUTOHINT|
                                   ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_PEDANTIC)
                    points=face.glyph.outline.points
                    self.assertEqual(points[a][0],points[b][0])
                    if name=='literata':
                        bindings=report['records'][char]['templates']['bindings']
                        self.assertTrue(any(c['point']==b and c['normal']==[1.,0.] for c in bindings))
                        self.assertTrue(any(c.get('feature')=='BracketedFoot'
                                            for c in report['records'][char]['graph']['constraints']))


if __name__=='__main__':unittest.main()
