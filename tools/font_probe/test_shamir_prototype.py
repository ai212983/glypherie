"""Tests exercise graph conflicts and executed native font instructions."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from shamir_prototype import build_font, render, features, select_constraints


def fixture(path):
    builder=FontBuilder(1000,isTTF=True);order=['.notdef','A','B']
    builder.setupGlyphOrder(order);builder.setupCharacterMap({65:'A',66:'B'})
    glyphs={}
    for name,width in zip(order,(100,100,110)):
        pen=TTGlyphPen(None);pen.moveTo((103,0));pen.lineTo((103+width,0))
        pen.lineTo((103+width,700));pen.lineTo((103,700));pen.closePath();glyphs[name]=pen.glyph()
    builder.setupGlyf(glyphs);builder.setupHorizontalMetrics({n:(400,103) for n in order})
    builder.setupHorizontalHeader(ascent=800,descent=-200)
    builder.setupNameTable({'familyName':'Test','styleName':'Regular','uniqueFontIdentifier':'Test',
                            'fullName':'Test Regular','psName':'Test-Regular'})
    builder.setupOS2(sTypoAscender=800,sTypoDescender=-200,usWinAscent=800,usWinDescent=200,sCapHeight=700,sxHeight=500)
    builder.setupPost();builder.setupMaxp();builder.save(path)


class ShamirTests(unittest.TestCase):
    def test_composite_executes_component_hints(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.ttf';output=Path(tmp)/'hinted.ttf';fixture(source)
            font=TTFont(source);order=list(font.getGlyphOrder())
            pen=TTGlyphPen(font.getGlyphSet());pen.addComponent('A',(1,0,0,1,0,0))
            font['glyf']['C']=pen.glyph();font.setGlyphOrder(order+['C'])
            font['hmtx'].metrics['C']=(400,103)
            for table in font['cmap'].tables:
                if table.isUnicode():table.cmap[67]='C'
            font.save(source)
            report=build_font(source,output,16,{},'AC')
            self.assertIn('component hints may execute',report['records']['C']['status'])
            a,_=render(output,'A',16);c,_=render(output,'C',16)
            self.assertEqual(a['pixels'],c['pixels'])
            self.assertEqual(c['width'],2)

    def test_opposed_sides_reject_same_facing_overlap(self):
        rectangle=np.array([[0,0],[100,0],[100,700],[0,700]],dtype=float)
        points=np.vstack([rectangle,rectangle+[40,0]])
        old=features(points,[1]*8,[3,7],1000)
        candidate=features(points,[1]*8,[3,7],1000,opposed_sides=True)
        self.assertTrue(any(p['width']==40 for p in old))
        self.assertFalse(any(p['width']==40 for p in candidate))
        self.assertTrue(any(p['width']==100 for p in candidate))
        # Reversing every contour changes winding sign, not opposition.
        reverse=np.vstack([rectangle[::-1],(rectangle+[40,0])[::-1]])
        reversed_pairs=features(reverse,[1]*8,[3,7],1000,opposed_sides=True)
        self.assertEqual(sorted(p['width'] for p in candidate),sorted(p['width'] for p in reversed_pairs))

    def test_detects_ink_stem(self):
        points=np.array([[0,0],[100,0],[100,700],[0,700]],dtype=float)
        pairs=features(points,[1]*4,[3],1000)
        self.assertTrue(any(p['axis']==0 and p['width']==100 for p in pairs))
        # Two independent stems separated by white space must not create an
        # ink-width constraint across the gap, even when it has a plausible width.
        points=np.vstack([points,points+[180,0]])
        pairs=features(points,[1]*8,[3,7],1000)
        self.assertFalse(any(p['width']==80 for p in pairs))

    def test_priority_and_cycle(self):
        constraints=[dict(kind='Abs',point=1,priority=10),
                     dict(kind='PDist',point=1,source=0,priority=30),
                     dict(kind='PDist',point=0,source=1,priority=20)]
        selected,rejected=select_constraints(constraints)
        self.assertEqual([c['point'] for c in selected],[1])
        self.assertEqual({r['reason'] for r in rejected},
                         {'dependency cycle','lower priority or deterministic tie'})

    def test_native_execution_and_shared_width(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.ttf';output=Path(tmp)/'hinted.ttf';fixture(source)
            report=build_font(source,output,16,{},'AB')
            original=TTFont(source);hinted=TTFont(output)
            for name in ('A','B'):
                self.assertEqual(list(original['glyf'][name].coordinates),list(hinted['glyf'][name].coordinates))
                self.assertIn('MIRP', ' '.join(hinted['glyf'][name].program.getAssembly()))
            a,_=render(output,'A',16);b,_=render(output,'B',16)
            self.assertEqual(a['width'],2);self.assertEqual(b['width'],2)
            self.assertEqual(a['pixels'],b['pixels'])
            self.assertEqual(report['records']['A']['features'][0]['width'],100)
            self.assertGreater(report['records']['A']['feature_counts']['straight'],0)
            self.assertEqual(report['records']['A']['feature_counts']['curve'],0)
            self.assertEqual(report['height_zones']['values'],[0,500,700])

    def test_determinism_and_missing_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.ttf';a=Path(tmp)/'a.ttf';b=Path(tmp)/'b.ttf';fixture(source)
            report_a=build_font(source,a,16,{},'AB');report_b=build_font(source,b,16,{},'AB')
            self.assertEqual(a.read_bytes(),b.read_bytes());self.assertEqual(report_a,report_b)
            with self.assertRaisesRegex(ValueError,'missing glyph'):build_font(source,a,16,{},'Z')
            with self.assertRaisesRegex(ValueError,'static font'):build_font(source,a,16,{'wght':400},'A')


if __name__=='__main__':unittest.main()
