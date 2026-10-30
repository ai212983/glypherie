import tempfile
from pathlib import Path
import unittest

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

import source_kerning


class SourceKerningChecks(unittest.TestCase):
    def font(self, path):
        names = ['.notdef', 'A', 'V', 'T', 'f', 'i', 'fi']
        builder = FontBuilder(1000, isTTF=True)
        builder.setupGlyphOrder(names)
        builder.setupCharacterMap({ord(ch): ch for ch in 'AVTfi'})
        builder.setupGlyf({name: TTGlyphPen(None).glyph() for name in names})
        builder.setupHorizontalMetrics({name: (600, 0) for name in names})
        builder.setupHorizontalHeader(ascent=800, descent=-200)
        builder.setupOS2()
        builder.setupNameTable({'familyName': 'Kerning fixture', 'styleName': 'Regular'})
        builder.setupPost()
        addOpenTypeFeaturesFromString(builder.font, '''
            feature kern {
                pos A V -125;
                pos A T 125;
                pos T <0 0 -50 0> A <10 0 0 0>;
            } kern;
            feature liga { sub f i by fi; } liga;
        ''')
        builder.save(path)

    def test_source_gpos_sign_scale_no_ligatures_and_no_pairs_across_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'source.ttf'
            self.font(path)
            before = path.read_bytes()
            self.assertEqual(source_kerning.pairs(path, 16, 'AV\nAT\nfi'), {('A', 'V'): -2, ('A', 'T'): 2})
            self.assertEqual(source_kerning.pairs(path, 8, 'AV'), {('A', 'V'): -1})
            self.assertEqual(source_kerning.pairs(path, 16, 'A\nV'), {})
            self.assertEqual(path.read_bytes(), before)

    def test_richer_positioning_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'source.ttf'
            self.font(path)
            with self.assertRaisesRegex(ValueError, 'richer positioning'):
                source_kerning.pairs(path, 16, 'TA')


if __name__ == '__main__':
    unittest.main()
