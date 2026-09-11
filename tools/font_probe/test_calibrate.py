"""Focused calibration diagnostics and matrix contract tests."""
import json
import unittest
from calibrate import DEFAULT_CONFIG, components, diagnose, matrix, topology


class CalibrationTests(unittest.TestCase):
    def test_complementary_connectivity(self):
        diagonal = [[True, False], [False, True]]
        self.assertEqual(components(diagonal, True), [2])
        self.assertEqual(components(diagonal), [1, 1])

    def test_counter_and_broken_join(self):
        ring = {'width':3, 'height':3, 'pixels':[1,1,1,1,0,1,1,1,1]}
        self.assertEqual(topology(ring,1), (1,1))
        ring['pixels'] = [1,0,1,0,0,0,1,0,1]
        self.assertEqual(topology(ring,1), (4,0))

    def test_gray_projection(self):
        glyph = {'width':3, 'height':1, 'pixels':[7,3,7]}
        self.assertEqual(topology(glyph,3), (2,0))
        glyph['pixels'][1] = 4
        self.assertEqual(topology(glyph,3), (1,0))

    def test_matrix_covers_table_and_threshold_controls(self):
        config = json.loads(DEFAULT_CONFIG.read_text())
        cases = matrix(config,DEFAULT_CONFIG)
        self.assertEqual(len(cases),119)
        self.assertEqual(len({c['id'] for c in cases}),119)
        for case in cases:
            if case['settings']['mono_threshold']==96 and not case.get('diagnostic_probe'):
                self.assertLessEqual(case['settings']['size_px'],20)
                control = dict(case['settings'],mono_threshold=128)
                self.assertTrue(any(c['font']==case['font'] and c['panel']==case['panel'] and c['settings']==control for c in cases))

    def test_x_height_counts_ink_rows(self):
        generated = {'config':{'output_bits':1}, 'kerning':[], 'glyphs':[
            {'codepoint':ord('x'),'width':2,'height':4,'pixels':[0,0,1,0,0,1,0,0]}]}
        self.assertEqual(diagnose(generated)['x_height_px'],2)


if __name__ == '__main__':
    unittest.main()
