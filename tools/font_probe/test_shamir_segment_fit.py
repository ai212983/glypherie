"""Executed constraints and preparation invariants for the segment candidate."""
import tempfile
import unittest
from pathlib import Path
import freetype as ft
import numpy as np
from fontTools.ttLib import TTFont
from shamir_segment_fit import build_font,clusters,prepared_glyph,anchor_curved_strokes
from shamir_geometry import prepare
from test_shamir_prototype import fixture
from compare_paper_prototypes import render


class SegmentFitTests(unittest.TestCase):
    def test_outer_anchor_reorients_width_and_removes_inner_anchor(self):
        constraints=[dict(kind='PAbs',point=1,value=540,priority=40),
                     dict(kind='PAbs',point=0,value=460,priority=40),
                     dict(kind='PDist',point=1,source=0,value=80,priority=30,feature=7),
                     dict(kind='Dist',point=2,source=0,priority=35,round=False),
                     dict(kind='PAbs',point=2,value=460,priority=40),
                     dict(kind='Dist',point=0,source=2,priority=35,round=False)]
        adjusted,changes=anchor_curved_strokes(constraints,[(7,1,0)])
        self.assertEqual(len(changes),1)
        self.assertFalse(any(c['kind']=='PAbs' and c['point']==0 for c in adjusted))
        width=next(c for c in adjusted if c['kind']=='PDist')
        self.assertEqual((width['source'],width['point']),(1,0))
        self.assertFalse(any(c['kind']=='PAbs' and c['point']==2 for c in adjusted))
        from shamir_prototype import select_constraints
        chosen,_=select_constraints(adjusted)
        self.assertEqual(next(c for c in chosen if c['point']==0)['kind'],'PDist')
        self.assertEqual(constraints[2]['source'],0)  # Input diagnostics remain intact.
        untouched,_=anchor_curved_strokes(constraints,[(7,9,0)])
        self.assertEqual(untouched,constraints)

    def test_native_upper_and_lower_curve_widths_survive_height_anchors(self):
        from fontTools.pens.ttGlyphPen import TTGlyphPen
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'source.ttf';out=Path(tmp)/'out.ttf';fixture(src)
            font=TTFont(src);order=list(font.getGlyphOrder())
            for name in ('A','B','C'):
                pen=TTGlyphPen(None)
                pen.moveTo((100,300));pen.qCurveTo((100,540),(200,540))
                pen.qCurveTo((300,540),(300,300));pen.qCurveTo((300,60),(200,60))
                pen.qCurveTo((100,60),(100,300));pen.closePath()
                pen.moveTo((160,300));pen.qCurveTo((160,140),(200,140))
                pen.qCurveTo((240,140),(240,300));pen.qCurveTo((240,460),(200,460))
                pen.qCurveTo((160,460),(160,300));pen.closePath()
                font['glyf'][name]=pen.glyph();font['hmtx'].metrics[name]=(400,100)
            font.setGlyphOrder(order+['C'])
            for table in font['cmap'].tables:
                if table.isUnicode():table.cmap[67]='C'
            font.save(src);report=build_font(src,out,'ABC')
            changes=report['records']['A']['stroke_anchor_changes']
            self.assertEqual(len(changes),2)
            face=ft.Face(str(out));face.set_pixel_sizes(0,14)
            face.load_char('A',ft.FT_LOAD_NO_AUTOHINT|ft.FT_LOAD_PEDANTIC|ft.FT_LOAD_TARGET_MONO)
            points=face.glyph.outline.points
            for change in changes:
                self.assertEqual(abs(points[change['outer']][1]-points[change['inner']][1]),64)

    def test_repeated_points_do_not_create_recurring_measurement(self):
        self.assertEqual(clusters([('stem',100,'A')]*20,1000)['stem'],[])
        self.assertEqual(clusters([('stem',v,c) for v,c in [(100,'A'),(102,'B'),(104,'C')]],1000)['stem'],[102])

    def test_prepared_mapping_and_quantization(self):
        model=prepare([[[[0,0],[45,103],[101,0]],[[101,0],[0,0]]]],1000)
        glyph,mapping,members=prepared_glyph(model)
        for p in model['points']:
            self.assertLessEqual(max(abs(np.array(glyph.coordinates[mapping[p['id']]])-p['position'])),.5)
        for s in model['segments']:
            self.assertEqual(members[s['id']][-1],mapping[s['end']])

    def test_native_local_distance_and_determinism(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'source.ttf';a=Path(tmp)/'a.ttf';b=Path(tmp)/'b.ttf';fixture(src)
            ra=build_font(src,a,'AB');rb=build_font(src,b,'AB')
            self.assertEqual(ra,rb);self.assertEqual(a.read_bytes(),b.read_bytes())
            font=TTFont(a)
            self.assertIn('MDRP',str(font['glyf']['A'].program.getAssembly()))
            face=ft.Face(str(a))
            for size in (14,16,18,20):
                glyph=render(face,'A',size,hinted=True)
                self.assertGreater(sum(glyph['pixels']),0)
                self.assertIn(glyph['width'],(1,2))

    def test_projected_distance_keeps_owned_heights(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'source.ttf';out=Path(tmp)/'out.ttf';fixture(src)
            font=TTFont(src)
            # A slanted parallelogram in three distinct glyphs supplies heights.
            for name in ('A','B','.notdef'):
                g=font['glyf'][name]
                for i,(x,y) in enumerate(g.coordinates):g.coordinates[i]=(x+y*.4,y)
            import copy
            order=list(font.getGlyphOrder())
            font['glyf']['C']=copy.deepcopy(font['glyf']['A'])
            font.setGlyphOrder(order+['C'])
            font['hmtx'].metrics['C']=(400,103)
            for table in font['cmap'].tables:
                if table.isUnicode():table.cmap[67]='C'
            font.save(src);report=build_font(src,out,'ABC')
            self.assertGreater(report['records']['A']['diagonals_applied'],0)
            face=ft.Face(str(out));face.set_pixel_sizes(0,16)
            face.load_char('A',ft.FT_LOAD_NO_AUTOHINT|ft.FT_LOAD_PEDANTIC|ft.FT_LOAD_TARGET_MONO)
            ys=[p[1] for p in face.glyph.outline.points]
            self.assertEqual(min(ys),0);self.assertEqual(max(ys),11*64)


if __name__=='__main__':unittest.main()
