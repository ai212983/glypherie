"""Check paired-side semantics and actual Microsoft runtime execution."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
import freetype as ft
import vttcompilepy as vtt
from vtt_mapping import commands
from compare_vtt_compiler import prepare
from audit_terminal_coverage import coords


class VTTMappingTests(unittest.TestCase):
    def setUp(self):
        self.points = [(0,0), (100,100), (120,100), (20,0)]
        self.record = dict(features=[dict(kind='slant',groups=[0,1],points=[0,3],length=140)],
            graph=dict(constraints=[dict(feature='align-0',point=1,sources=[0],normal=[1,-1],kind='Dist'),
                                    dict(feature='align-1',point=2,sources=[3],normal=[1,-1],kind='Dist')]),
            attachment_resolution=[])

    def test_crossed_links_follow_sides_and_use_perpendicular_width(self):
        talk, cvts, mapping = commands(self.points, [1]*4, self.record)
        self.assertEqual(cvts, [14,14])
        self.assertIn('ResXDLink(0,3,1000,2,1,1001)', talk)
        self.assertEqual(mapping['strokes'][0]['sides'], [[0,1],[3,2]])
        self.assertNotIn('Diagonal>', talk)

    def test_each_cvt_uses_its_opposite_parent_child_line(self):
        points = [(0,0),(100,100),(70,100),(20,0)]
        _, cvts, _ = commands(points, [1]*4, self.record)
        self.assertEqual(cvts, [18,21])

    def test_translation_and_missing_endpoints(self):
        first = commands(self.points, [1]*4, self.record)
        shifted = commands(np.array(self.points)+[37,-91], [1]*4, self.record)
        self.assertEqual(first, shifted)
        _, _, mapping = commands(self.points, [1,0,0,1], self.record)
        self.assertFalse(mapping['strokes'])
        self.assertTrue(mapping['warnings'])

    def test_compiler_runtime_outline_and_bytecode(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'source.ttf'
            fb = FontBuilder(1000, isTTF=True)
            fb.setupGlyphOrder(['.notdef','test'])
            pen = TTGlyphPen(None)
            pen.moveTo(self.points[0])
            for p in self.points[1:]: pen.lineTo(p)
            pen.closePath()
            fb.setupGlyf({'.notdef':TTGlyphPen(None).glyph(),'test':pen.glyph()})
            fb.setupHorizontalMetrics({'.notdef':(500,0),'test':(500,0)})
            fb.setupHorizontalHeader(ascent=800,descent=-200)
            fb.setupCharacterMap({65:'test'})
            fb.setupNameTable({'familyName':'Fixture','styleName':'Regular'})
            fb.setupOS2();fb.setupPost();fb.save(source)
            f=prepare(source)
            talk,cvts,_=commands(self.points,[1]*4,self.record)
            f['TSI3'].glyphPrograms['test']=talk
            f['TSI1'].extraPrograms['cvt']+='\n'+ '\n'.join(f'{1000+i}: {value}' for i,value in enumerate(cvts))
            outputs=[]
            for iteration in range(2):
                compiler=vtt.Compiler(f);compiler.compile_all()
                target=Path(directory)/f'compiled-{iteration}.ttf';compiler.save_font(target)
                compiled=compiler.get_ttfont()
                outputs.append(compiled['glyf']['test'].program.getBytecode())
                self.assertEqual(list(compiled['glyf']['test'].coordinates),self.points)
                assembly=compiled['TSI1'].glyphPrograms['test']
                self.assertIn('120',assembly)
                for size in (14,16,18,20):
                    self.assertTrue(np.isfinite(coords(ft.Face(str(target)),'A',size)).all())
            self.assertEqual(*outputs)
