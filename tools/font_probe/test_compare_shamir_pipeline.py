"""Tests for comparison controls and text placement, independent of appearance."""
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import freetype as ft
from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from test_shamir_prototype import fixture
from compare_shamir_pipeline import common_legacy_scan, text_positions, old


class ControlledComparisonTests(unittest.TestCase):
    def test_scan_flags_and_exception_restore(self):
        outline=SimpleNamespace(flags=ft.FT_OUTLINE_SMART_DROPOUTS | ft.FT_OUTLINE_INCLUDE_STUBS)
        face=SimpleNamespace(glyph=SimpleNamespace(outline=SimpleNamespace(_FT_Outline=outline)))
        def capture(face,char):return face.glyph.outline._FT_Outline.flags
        with patch.object(old,'bitmap',capture):
            with self.assertRaisesRegex(RuntimeError,'deliberate'):
                with common_legacy_scan():
                    self.assertEqual(old.bitmap(face,'A'),ft.FT_OUTLINE_IGNORE_DROPOUTS)
                    raise RuntimeError('deliberate')
            self.assertIs(old.bitmap,capture)

    def test_source_kerning_uses_rendered_advances(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'font.ttf';fixture(path)
            font=TTFont(path)
            addOpenTypeFeaturesFromString(font,'feature kern { pos A B -100; } kern;')
            font.save(path)
            glyphs={'A':dict(advance_26_6=448),'B':dict(advance_26_6=512)}
            run=text_positions(path.read_bytes(),glyphs,'AB',16)
            kern=sum(p['kerning_26_6'] for p in run['placements'])
            self.assertLess(kern,0)
            self.assertEqual(run['advance_26_6'],448+512+kern)
            self.assertEqual(run['placements'][1]['pen_26_6'],448+kern)
            wider=text_positions(path.read_bytes(),{'A':dict(advance_26_6=512),'B':glyphs['B']},'AB',16)
            self.assertEqual(wider['placements'][1]['x'],run['placements'][1]['x']+1)


if __name__=='__main__':unittest.main()
