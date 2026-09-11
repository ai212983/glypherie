"""Boundary normalization invariants independent of glyph-feature selection."""
import tempfile,unittest
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
import freetype as ft
from test_shamir_prototype import fixture
from shamir_boundary import normalize_boundaries
from compare_paper_prototypes import render,pixels


class BoundaryTests(unittest.TestCase):
    def check_contours(self,loops,expected,bearing=100):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.ttf';out=Path(tmp)/'normalized.ttf';fixture(source)
            font=TTFont(source);pen=TTGlyphPen(None)
            for loop in loops:
                pen.moveTo(loop[0])
                for p in loop[1:]:pen.lineTo(p)
                pen.closePath()
            font['glyf']['A']=pen.glyph();font['hmtx'].metrics['A']=(900,bearing);font.save(source)
            before=source.read_bytes();metrics=dict(font['hmtx'].metrics)
            report=normalize_boundaries(font,'A');font.save(out)
            self.assertEqual(font['glyf']['A'].numberOfContours,expected)
            self.assertEqual(font['hmtx'].metrics,metrics)
            self.assertEqual(source.read_bytes(),before)
            a,b=ft.Face(str(source)),ft.Face(str(out))
            for size in (14,16,18,20,128):
                self.assertEqual(pixels(render(a,'A',size)),pixels(render(b,'A',size)))
            self.assertFalse(normalize_boundaries(font,'A')['changed'])

    def test_overlapping_strokes_become_one_boundary(self):
        self.check_contours([[(100,0),(240,0),(240,700),(100,700)],
                             [(220,300),(700,300),(700,440),(220,440)]],1)

    def test_authored_bearing_differs_from_bounds(self):
        self.check_contours([[(100,0),(240,0),(240,700),(100,700)],
                             [(220,300),(700,300),(700,440),(220,440)]],1,bearing=77)

    def test_counter_winding_is_preserved(self):
        self.check_contours([[(100,0),(700,0),(700,700),(100,700)],
                             [(250,150),(250,550),(550,550),(550,150)]],2)

    def test_separate_marks_remain_separate(self):
        self.check_contours([[(100,0),(240,0),(240,500),(100,500)],
                             [(100,600),(240,600),(240,740),(100,740)]],2)

if __name__=='__main__':unittest.main()
