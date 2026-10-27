import importlib.util
import base64
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

spec = importlib.util.spec_from_file_location('landing_samples', Path(__file__).with_name('generate.py'))
samples = importlib.util.module_from_spec(spec)
spec.loader.exec_module(samples)


class _PinnedDownload:
    def __init__(self, data):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._data


class RendererPolicyChecks(unittest.TestCase):
    def default_case(self):
        return {'fitting': 'font_hints_auto', 'rasterization': 'free_type_mono_terminals', 'diagonal_fitting': True, 'dropout': 'smart', 'include_stubs': True, 'font_instructions': True}

    def test_bridge_resolves_shared_working_preview_policy(self):
        declared, policy, fingerprint = samples.resolve_renderer_policy(self.default_case())
        self.assertEqual(declared, self.default_case())
        self.assertEqual(policy['fitting'], 'font_hints_auto')
        self.assertEqual(policy['rasterization'], 'free_type_mono_terminals')
        self.assertEqual(policy['hinting'], 'auto_fallback')
        self.assertEqual(policy['mono_raster'], {'dropout': 'smart', 'include_stubs': True, 'font_instructions': True})
        self.assertRegex(fingerprint, r'^[0-9a-f]{64}$')

    def test_bridge_matches_live_preview_request(self):
        import subprocess
        script = """
import { toRenderSpec } from './tools/web/src/app/renderer/render-spec.ts';
console.log(JSON.stringify(toRenderSpec({text:'AV',sizePx:16,axes:{},profile:'mono_1bit',
    width:300,height:100,rasterization:'free_type_mono',diagonalFitting:true})));
"""
        recorded = json.loads(subprocess.check_output(['node', '--input-type=module', '-e', script], cwd=samples.ROOT, text=True))
        _, policy, _ = samples.resolve_renderer_policy({})
        for key in ['hinting', 'output_bits', 'mono_threshold', 'gray_gamma', 'missing_glyphs', 'metric_rounding', 'mono_raster']:
            self.assertEqual(policy[key], recorded[key])
        self.assertEqual(recorded['pipeline'], {'fitting': policy['fitting'], 'rasterization': policy['rasterization'], 'diagonal_fitting': policy['diagonal_fitting']})

    def test_bridge_rejects_invalid_combinations(self):
        bad = dict(self.default_case(), fitting='source_relative')
        with self.assertRaisesRegex(ValueError, 'Diagonal fitting requires'):
            samples.resolve_renderer_policy(bad)

    def test_bridge_failures_and_forged_output_raise(self):
        import subprocess
        bad_output = json.dumps({'policy': {'fitting': 'x'}, 'fingerprint': 'not-a-digest'})
        with patch.object(subprocess, 'run', return_value=type('Result', (), {'returncode': 0, 'stdout': bad_output, 'stderr': ''})()):
            with self.assertRaisesRegex(ValueError, 'invalid policy or fingerprint'):
                samples.resolve_renderer_policy(self.default_case())
        with patch.object(subprocess, 'run', return_value=type('Result', (), {'returncode': 1, 'stdout': '', 'stderr': 'preview-policy-bridge: boom'})()):
            with self.assertRaisesRegex(ValueError, 'renderer policy rejected'):
                samples.resolve_renderer_policy(self.default_case())

    def test_glypherie_request_keeps_comparison_kerning_policy(self):
        _, policy, _ = samples.resolve_renderer_policy(self.default_case())
        request = samples.glypherie_request('AV', 16, policy)
        self.assertFalse(request['config']['kerning'])
        self.assertEqual(request['letter_spacing_px'], 0)
        self.assertEqual(request['pipeline'], {'fitting': 'font_hints_auto', 'rasterization': 'free_type_mono_terminals', 'diagonal_fitting': True})
        self.assertEqual(request['config']['mono_raster'], policy['mono_raster'])
        self.assertEqual(sorted(request['config']['characters']), sorted(set('AVHIl')))

    def test_omitted_settings_follow_shared_defaults(self):
        # Nothing declared means nothing forwarded: a shared-default change
        # flows to landing without touching Python.
        declared, policy, _ = samples.resolve_renderer_policy({})
        self.assertEqual(declared, {})
        _, explicit_policy, _ = samples.resolve_renderer_policy(self.default_case())
        self.assertEqual(policy, explicit_policy)

    def test_case_renderer_values_win_over_cli(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / 'cases.json'
            config.write_text(json.dumps([
                {'id': 'overridden', 'size_px': 16, 'dropout': 'off'},
                {'id': 'inherited', 'size_px': 16},
            ]))
            with patch.object(sys, 'argv', ['generate.py', '--size', '16', '--dropout', 'simple', '--config', str(config)]):
                cases = samples.cases_from(samples.arguments())
            by_id = {case['id']: case for case in cases}
            self.assertEqual(by_id['overridden']['dropout'], 'off')
            self.assertEqual(by_id['inherited']['dropout'], 'simple')
            with patch.object(sys, 'argv', ['generate.py', '--size', '16']):
                cases = samples.cases_from(samples.arguments())
            self.assertIsNone(cases[0]['dropout'])
            declared, _, _ = samples.resolve_renderer_policy(cases[0])
            self.assertNotIn('dropout', declared)


class SampleChecks(unittest.TestCase):
    def options(self, *args):
        with patch.object(sys, 'argv', ['generate.py', *args]):
            return samples.arguments()

    def test_overlapping_transparent_cells_do_not_erase_previous_ink(self):
        # The second cell overlaps the first but its left column is transparent.
        a = Image.new('L', (2, 1), 255)
        b = Image.new('L', (2, 1))
        b.putpixel((1, 0), 255)
        image = samples.compose({'A': (a, 1, 0, -1), 'B': (b, 1, 0, -1)}, 'AB', (5, 3), 1, [2])
        self.assertEqual([image.getpixel((x, 1)) for x in range(5)], [255, 0, 0, 0, 255])

    def test_negative_bearing_and_native_fractional_pen_are_retained(self):
        glyph = Image.new('L', (1, 1), 255)
        image = samples.compose({'A': (glyph, 1.25, -1, -1)}, 'AAA', (7, 3), 2, [2])
        self.assertEqual([x for x in range(7) if image.getpixel((x, 1)) == 0], [1, 2, 4])

    def test_any_clipped_ink_fails(self):
        glyph = Image.new('L', (2, 1), 255)
        with self.assertRaisesRegex(ValueError, 'clips'):
            samples.compose({'A': (glyph, 2, -1, 0)}, 'A', (2, 2), 0, [1])

    def test_fitted_pair_adjustments_apply_before_the_right_glyph_and_reset_per_line(self):
        glyph = Image.new('L', (1, 1), 255)
        image = samples.compose({'A': (glyph, 3, 0, -1), 'V': (glyph, 3, 0, -1)}, 'AV\nAV', (8, 5), 1, [2, 4], {('A', 'V'): -1})
        for row in [1, 3]:
            self.assertEqual([x for x in range(8) if image.getpixel((x, row)) == 0], [1, 3])

    def test_playdate_decoder_preserves_inset_tracking_and_fitted_pairs(self):
        atlas = Image.new('RGBA', (95, 1), (0, 0, 0, 255))
        buffer = io.BytesIO()
        atlas.save(buffer, format='PNG')
        encoded = base64.b64encode(buffer.getvalue()).decode()
        entries = '\n'.join(f'U+{ord(ch):04X} 4' for ch in samples.ASCII)
        source = f'--metrics={{"baseline":1}}\n--origin_x=1\ndata={encoded}\nwidth=1\nheight=1\ntracking=-1\n{entries}\nU+0041U+0056 -1\n'
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'font.fnt').write_text(source)
            glyphs, pairs = samples.playdate_glyphs(directory)
        self.assertEqual(glyphs['A'][1:], (3, -1, -1))
        self.assertEqual(pairs, {('A', 'V'): -1})

    def test_multi_case_publish_and_incompatible_pipeline_fail_before_work(self):
        with self.assertRaisesRegex(ValueError, 'exactly one case'):
            samples.cases_from(self.options('--size', '16', '--size', '20', '--publish'))
        with self.assertRaisesRegex(ValueError, 'Diagonal fitting requires'):
            samples.cases_from(self.options('--fitting', 'source_relative'))
        cases = samples.cases_from(self.options('--fitting', 'source_relative', '--no-diagonal-fitting'))
        _, policy, _ = samples.resolve_renderer_policy(cases[0])
        self.assertFalse(policy['diagonal_fitting'])

    def test_config_relative_paths_and_independent_axes(self):
        cases = samples.cases_from(self.options('--config', str(samples.SCRIPT / 'cases.example.json')))
        self.assertEqual(len(cases), 3)
        self.assertEqual(cases[0]['axes']['wght'], 300)
        self.assertEqual(cases[1]['axes']['wght'], 400)
        self.assertEqual(Path(cases[2]['font']), samples.ROOT / 'fonts/SourceSans3.ttf')

    def test_duplicate_ids_and_unknown_settings_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / 'cases.json'
            for entries, message in [([{'id': 'x', 'size_px': 16}] * 2, 'unique safe id'), ([{'id': 'x', 'size_px': 16, 'threshhold': 128}], 'unknown settings')]:
                config.write_text(json.dumps(entries))
                with self.assertRaisesRegex(ValueError, message):
                    samples.cases_from(self.options('--config', str(config)))

    def test_instancing_rejects_out_of_range_axes_without_changing_source(self):
        source = samples.ROOT / 'fonts/Roboto.ttf'
        before = source.read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, 'outside the font range'):
                samples.prepare_font(source, {'wght': -100}, Path(temporary) / 'input.ttf')
        self.assertEqual(source.read_bytes(), before)

    def test_failed_publication_keeps_existing_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            destination = directory / 'web'
            destination.mkdir()
            previous = b'previous image'
            (destination / 'repo.png').write_bytes(previous)
            manifest = {'samples': [{'id': tool, 'file': f'{tool}.png', 'display_sha256': samples.sha(b'new image')} for tool in samples.TOOLS]}
            for tool in samples.TOOLS:
                (directory / f'{tool}.png').write_bytes(b'new image')
            (directory / 'adafruit.png').write_bytes(b'corrupted image')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                samples.publish_case(directory, manifest, destination)
            self.assertEqual((destination / 'repo.png').read_bytes(), previous)
            self.assertFalse((destination / 'capture.json').exists())
            (directory / 'adafruit.png').write_bytes(b'new image')
            samples.publish_case(directory, manifest, destination)
            self.assertEqual((destination / 'repo.png').read_bytes(), b'new image')
            self.assertEqual(json.loads((destination / 'capture.json').read_text()), manifest)

    def external_case(self, directory, name, font, digest):
        config = Path(directory) / f'{name}.json'
        config.write_text(json.dumps([{'id': name, 'size_px': 16, 'font': str(font),
            'font_url': 'https://example.test/External.ttf', 'font_sha256': digest}]))
        return self.options('--config', str(config))

    def test_matching_external_cache_avoids_network(self):
        data = b'cached font bytes'
        with tempfile.TemporaryDirectory() as temporary:
            font = Path(temporary) / 'External.ttf'
            font.write_bytes(data)
            with patch.object(samples, 'urlopen', side_effect=AssertionError('network')):
                cases = samples.cases_from(self.external_case(temporary, 'external-16', font, samples.sha(data)))
            self.assertEqual(Path(cases[0]['font']).read_bytes(), data)

    def test_mismatched_download_leaves_cache_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            font = Path(temporary) / 'External.ttf'
            font.write_bytes(b'stale bytes')
            args = self.external_case(temporary, 'external-16', font, samples.sha(b'expected bytes'))
            with patch.object(samples, 'urlopen', return_value=_PinnedDownload(b'other bytes')):
                with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                    samples.cases_from(args)
            self.assertEqual(font.read_bytes(), b'stale bytes')
            missing = Path(temporary) / 'Missing.ttf'
            args = self.external_case(temporary, 'missing-16', missing, samples.sha(b'expected bytes'))
            with patch.object(samples, 'urlopen', return_value=_PinnedDownload(b'other bytes')):
                with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                    samples.cases_from(args)
            self.assertFalse(missing.exists())

    def test_unpinned_or_malformed_digest_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            font = Path(temporary) / 'External.ttf'
            extras = [{'font_url': 'https://example.test/External.ttf'},
                {'font_url': 'https://example.test/External.ttf', 'font_sha256': 'not-a-digest'},
                {'font_url': 'https://example.test/External.ttf', 'font_sha256': 123},
                {'font_sha256': samples.sha(b'expected bytes')}]
            for index, extra in enumerate(extras):
                entry = {'id': f'external-{index}', 'size_px': 16, 'font': str(font), **extra}
                config = Path(temporary) / f'cases-{index}.json'
                config.write_text(json.dumps([entry]))
                with patch.object(samples, 'urlopen', side_effect=AssertionError('network')), \
                        self.assertRaises(ValueError):
                    samples.cases_from(self.options('--config', str(config)))
            self.assertFalse(font.exists())


if __name__ == '__main__':
    unittest.main()
