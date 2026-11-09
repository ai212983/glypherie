import copy
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calibration import pair_basis
from solver import Controls, Solver
from test_solver import capture, rectangle

def calibrated_capture():
    value = capture()
    value['source_calibration'] = dict(schema_version='contextual-spacing-source-calibration-v1', provenance=dict(axes={'wght': 400}, coordinates='unscaled design units'), references=[dict(codepoint=cp, status='available', glyph_id=cp, source_commands=rectangle(0, 0, 200, 500), source_advance_px=advance, source_pair_adjustment_px=kern) for cp, advance, kern in ((110, 5, 0.25), (72, 7, -0.5), (48, 4, 0.125))])
    return value

def with_glyphs(value, codepoints):
    for cp in codepoints:
        glyph = copy.deepcopy(value['glyphs'][1])
        glyph.update(codepoint=cp, glyph_id=cp)
        value['glyphs'].append(glyph)
    return value

class CalibrationTests(unittest.TestCase):

    def test_source_metrics_already_pixels_and_full_reference_kerning(self):
        solver = Solver(calibrated_capture())
        data = solver.calibration_metadata(spacing_model='font_calibrated')
        targets = {key: entry['target_px'] for key, entry in data['classes'].items()}
        self.assertEqual(targets, dict(lowercase=3.25, uppercase=4.5, digits=2.125, mixed=3.875))
        self.assertEqual(data['references']['lowercase']['source_pair_adjustment_px'], 0.25)
        self.assertEqual(data['references']['lowercase']['origin'], 'source_calibration')
        self.assertTrue(data['unicode_version'])
        self.assertEqual(len(solver.glyphs), 5)
        self.assertEqual(solver.generate(controls=Controls(spacing_model='font_calibrated'))['declared_pairs'], 25)
        self.assertEqual(solver.generate(text='nn', controls=Controls(spacing_model='font_calibrated'))['status'], 'unsupported_input')

    def test_classes_share_targets_and_rounded_residual_bounds(self):
        value = with_glyphs(calibrated_capture(), (97, 101, 233))
        solver = Solver(value)
        controls = Controls(preserve_tabular_spacing=False, spacing_model='font_calibrated')
        for text, basis, target in (('ae', 'lowercase', 3.25), ('éa', 'lowercase', 3.25), ('AV', 'uppercase', 4.5), ('Ae', 'mixed', 3.875), ('aV', 'mixed', 3.875), ('01', 'digits', 2.125)):
            pair = solver.pair(*map(ord, text), controls)
            self.assertEqual(pair['calibration_basis'], basis)
            self.assertEqual(pair['target_provenance'], 'font_calibrated')
            self.assertEqual(pair['target_separation_px'], target)
            self.assertLessEqual(abs(pair['target_error_px']), 0.5)

    def test_conservative_latin_and_ascii_numeric_scope(self):
        value = with_glyphs(calibrated_capture(), (97, 233, 945, 1040, 453, 44, 1633))
        solver = Solver(value)
        for text in ('αa', 'АA', 'ǅa', ',A', 'A1', '١1'):
            pair = solver.pair(*map(ord, text), controls=Controls(spacing_model='font_calibrated'))
            self.assertEqual(pair['reason'], 'unsupported_calibration_class', text)
            self.assertIsNone(pair['target_separation_px'])
            self.assertEqual(pair['automatic_adjustment_px'], pair['metric_adjustment_px'])
        self.assertEqual(pair_basis(233, 97), 'lowercase')
        self.assertIsNone(pair_basis(453, 97), 'titlecase is not assigned a Latin anchor')

    def test_full_endpoint_and_calibration_ignore_runtime_kerning(self):
        solver = Solver(calibrated_capture())
        results = [solver.pair(65, 86, Controls(source_kerning=k, spacing_model='font_calibrated')) for k in (0, 0.25, 0.5, 0.75, 1)]
        self.assertEqual({p['target_separation_px'] for p in results}, {4.5})
        self.assertEqual(len({p['automatic_adjustment_px'] for p in results}), 1)
        self.assertNotEqual(results[0]['metric_adjustment_px'], results[-1]['metric_adjustment_px'])
        self.assertNotEqual(solver.pair(65, 86, Controls(0, 0, spacing_model='font_calibrated'))['automatic_adjustment_px'], solver.pair(65, 86, Controls(1, 0, spacing_model='font_calibrated'))['automatic_adjustment_px'])

    def test_tabular_and_fixed_pitch_protections(self):
        value = calibrated_capture()
        value['tabular_digits'] = True
        solver = Solver(value)
        self.assertEqual(solver.pair(48, 49, controls=Controls(spacing_model='font_calibrated'))['reason'], 'source_tabular_digits')
        self.assertEqual(solver.pair(48, 49, Controls(preserve_tabular_spacing=False, spacing_model='font_calibrated'))['calibration_basis'], 'digits')
        value['monospace'] = True
        value['source_calibration']['references'][1]['source_commands'] = rectangle(0, 0, 100000, 500)
        solver = Solver(value)
        self.assertEqual(solver.pair(65, 86, controls=Controls(spacing_model='font_calibrated'))['reason'], 'fixed_pitch')
        self.assertEqual(solver.generate(controls=Controls(spacing_model='font_calibrated'))['calibration']['references']['uppercase']['status'], 'not_evaluated')

    def test_missing_or_invalid_reference_is_class_local_without_constant_fallback(self):
        value = with_glyphs(calibrated_capture(), (97, 101))
        value['source_calibration']['references'][0] = dict(codepoint=110, status='missing_reference_glyph')
        solver = Solver(value)
        for text in ('ae', 'Ae'):
            pair = solver.pair(*map(ord, text), controls=Controls(spacing_model='font_calibrated'))
            self.assertEqual(pair['reason'], 'calibration_unavailable')
            self.assertIsNone(pair['target_separation_px'])
            self.assertIsNone(pair['target_provenance'])
        self.assertIsNone(solver.pair(65, 86, controls=Controls(spacing_model='font_calibrated'))['reason'])
        self.assertEqual(solver.pair(65, 86, controls=Controls(spacing_model='font_calibrated'))['target_separation_px'], 4.5)
        for commands, advance, expected in (([], 5, 'empty_reference_geometry'), (rectangle(0, 0, 200, 500), 1, 'nonpositive_target'), ([dict(op='move_to', x=0, y=0), dict(op='line_to', x=200, y=0)], 5, 'reference_no_shared_bands'), ([dict(op='move_to', x=0, y=0), dict(op='line_to', x=100000, y=100)], 5, 'unrepresentable_reference_geometry')):
            broken = calibrated_capture()
            reference = broken['source_calibration']['references'][1]
            reference.update(source_commands=commands, source_advance_px=advance)
            pair = Solver(broken).pair(65, 86, controls=Controls(spacing_model='font_calibrated'))
            self.assertEqual(pair['calibration_reason'], expected)
            self.assertEqual(pair['automatic_adjustment_px'], pair['metric_adjustment_px'])

    def test_calibration_uses_existing_repertoire_for_legacy_capture(self):
        value = with_glyphs(capture(), (110, 72))
        solver = Solver(value)
        data = solver.calibration_metadata(spacing_model='font_calibrated')
        self.assertEqual(data['references']['uppercase']['origin'], 'capture_repertoire')
        self.assertEqual(data['classes']['uppercase']['target_px'], 2)
        del value['glyphs'][-2]
        self.assertEqual(Solver(value).calibration_metadata(spacing_model='font_calibrated')['classes']['lowercase']['reason'], 'missing_reference_glyph')

    def test_auxiliary_numbers_are_invalid_even_with_optical_disabled(self):
        for field in ('source_advance_px', 'source_pair_adjustment_px'):
            value = calibrated_capture()
            value['source_calibration']['references'][0][field] = math.inf
            with self.assertRaises(ValueError):
                Solver(value)
        value = calibrated_capture()
        value['source_calibration']['references'][0]['source_commands'][0]['x'] = math.nan
        with self.assertRaises(ValueError):
            Solver(value)

    def test_disabled_path_is_lazy_and_history_independent(self):
        value = calibrated_capture()
        solver = Solver(value)
        before = solver.generate(Controls(optical=0, spacing_model='font_calibrated'))
        solver.generate(controls=Controls(spacing_model='font_calibrated'))
        self.assertEqual(before, solver.generate(Controls(optical=0, spacing_model='font_calibrated')))
        self.assertEqual(before['calibration']['references']['uppercase']['status'], 'not_evaluated')
        value['source_calibration']['references'][1]['source_commands'] = rectangle(0, 0, 100000, 500)
        solver = Solver(value)
        self.assertEqual(solver.generate(Controls(optical=0, spacing_model='font_calibrated'))['status'], 'complete')
        self.assertEqual(solver.generate(controls=Controls(spacing_model='font_calibrated'))['status'], 'complete', 'unsupported calibration safely abstains')

    def test_capture_immutability_request_and_cache_independence(self):
        value = calibrated_capture()
        original = copy.deepcopy(value)
        solver = Solver(value)
        full = solver.generate(controls=Controls(spacing_model='font_calibrated'))
        preview = solver.generate(text='AV', controls=Controls(spacing_model='font_calibrated'))
        self.assertEqual(full['calibration'], preview['calibration'])
        self.assertEqual(full, solver.generate(controls=Controls(spacing_model='font_calibrated')))
        self.assertEqual(full, Solver(value).generate(controls=Controls(spacing_model='font_calibrated')))
        metadata = solver.calibration_metadata(spacing_model='font_calibrated')
        metadata['references']['uppercase']['target_px'] = -1
        self.assertEqual(solver.calibration_metadata(spacing_model='font_calibrated')['classes']['uppercase']['target_px'], 4.5)
        self.assertEqual(value, original)
        doubled = copy.deepcopy(value)
        doubled['size_px'] *= 2
        for reference in doubled['source_calibration']['references']:
            reference['source_advance_px'] *= 2
            reference['source_pair_adjustment_px'] *= 2
        self.assertEqual(Solver(doubled).calibration_metadata(spacing_model='font_calibrated')['classes']['uppercase']['target_px'], 9)
        self.assertNotEqual(Solver(doubled).identity, solver.identity)
        varied = copy.deepcopy(value)
        varied['source_calibration']['provenance']['axes']['wght'] = 700
        varied['source_calibration']['references'][1]['source_commands'] = rectangle(0, 0, 250, 500)
        self.assertEqual(Solver(varied).calibration_metadata(spacing_model='font_calibrated')['classes']['uppercase']['target_px'], 4)
        self.assertNotEqual(Solver(varied).identity, solver.identity)
if __name__ == '__main__':
    unittest.main()
