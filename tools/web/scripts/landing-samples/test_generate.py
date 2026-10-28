import importlib.util
import base64
import io
import json
import os
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


class CasesFromCharacterization(unittest.TestCase):
    def options(self, *args):
        with patch.object(sys, 'argv', ['generate.py', *args]):
            return samples.arguments()

    def cases_with(self, entries, *args):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / 'cases.json'
            config.write_text(json.dumps(entries))
            return samples.cases_from(self.options(*args, '--config', str(config)))

    def test_cli_axis_parsing_yields_floats_and_rejects_duplicates(self):
        cases = samples.cases_from(self.options('--size', '16', '--axis', 'wght=400'))
        self.assertEqual(cases[0]['axes'], {'wght': 400.0})
        with self.assertRaisesRegex(ValueError, 'Duplicate axis wght'):
            samples.cases_from(self.options('--size', '16', '--axis', 'wght=400', '--axis', 'wght=300'))

    def test_malformed_cli_axis_values_fail(self):
        with self.assertRaises(ValueError):
            samples.cases_from(self.options('--size', '16', '--axis', 'wght'))
        with self.assertRaises(ValueError):
            samples.cases_from(self.options('--size', '16', '--axis', 'wght=lots'))

    def test_config_shape_rejections(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / 'cases.json'
            config.write_text(json.dumps([]))
            with self.assertRaisesRegex(ValueError, 'nonempty array'):
                samples.cases_from(self.options('--config', str(config)))
            config.write_text(json.dumps({'id': 'x'}))
            with self.assertRaisesRegex(ValueError, 'nonempty array'):
                samples.cases_from(self.options('--config', str(config)))
            for entries, message in [([42], 'unknown settings'),
                    ([{'id': 'x', 'size_px': 16, 'threshhold': 128}], 'unknown settings'),
                    ([{'size_px': 16}], 'unique safe id')]:
                config.write_text(json.dumps(entries))
                with self.assertRaisesRegex(ValueError, message):
                    samples.cases_from(self.options('--config', str(config)))
            for bad_id in ['', ' bad', '-x', 'x!', 123, None]:
                config.write_text(json.dumps([{'id': bad_id, 'size_px': 16}]))
                with self.assertRaisesRegex(ValueError, 'unique safe id'):
                    samples.cases_from(self.options('--config', str(config)))

    def test_scalar_bounds_reject_out_of_range_and_wrong_types(self):
        bad = [
            ({'size_px': 3}, 'size_px must be an integer'),
            ({'size_px': 97}, 'size_px must be an integer'),
            ({'size_px': '16'}, 'size_px must be an integer'),
            ({'size_px': 16.0}, 'size_px must be an integer'),
            ({'size_px': None}, 'size_px must be an integer'),
            ({'threshold': 0}, 'threshold must be an integer'),
            ({'threshold': 255}, 'threshold must be an integer'),
            ({'threshold': '128'}, 'threshold must be an integer'),
            ({'threshold': 128.0}, 'threshold must be an integer'),
            ({'stem_target_px': 0.4}, 'stem_target_px must be in'),
            ({'stem_target_px': 4.1}, 'stem_target_px must be in'),
            ({'stem_target_px': '1'}, 'stem_target_px must be in'),
            ({'width': 63}, 'width must be 64'),
            ({'width': 16385}, 'width must be 64'),
            ({'width': '2400'}, 'width must be 64'),
            ({'line_step': 0}, 'line_step must be 1'),
            ({'line_step': 1025}, 'line_step must be 1'),
            ({'line_step': '48'}, 'line_step must be 1'),
        ]
        for override, message in bad:
            with self.subTest(override=override):
                entry = {'id': 'x', 'size_px': 16, **override}
                with self.assertRaisesRegex(ValueError, message):
                    self.cases_with([entry])

    def test_bool_is_not_accepted_as_number(self):
        for override, message in [
            ({'size_px': True}, 'size_px must be an integer'),
            ({'threshold': True}, 'threshold must be an integer'),
            ({'width': True}, 'width must be 64'),
            ({'line_step': True}, 'line_step must be 1'),
            ({'stem_target_px': True}, 'stem_target_px must be in'),
            ({'axes': {'wght': True}}, 'axes must map'),
        ]:
            with self.subTest(override=override):
                with self.assertRaisesRegex(ValueError, message):
                    self.cases_with([{'id': 'x', 'size_px': 16, **override}])

    def test_text_rules(self):
        for text in ['', '   ', '\n', 'h\xe9llo', 'a\tb', 'a' * 8193]:
            with self.subTest(text=text[:8]):
                with self.assertRaisesRegex(ValueError, 'Text must contain printable ASCII'):
                    self.cases_with([{'id': 'x', 'size_px': 16, 'text': text}])

    def test_axes_rules(self):
        for axes in [['wght'], {'wgh': 400}, {'wghtx': 400}, {'wght': '400'},
                     {'wght': float('nan')}, {'wght': float('inf')}, {'wght': None}]:
            with self.subTest(axes=repr(axes)):
                with self.assertRaisesRegex(ValueError, 'axes must map'):
                    self.cases_with([{'id': 'x', 'size_px': 16, 'axes': axes}])

    def test_family_rules(self):
        for override, message in [
            ({'family_id': 'ABC'}, 'family_id must be a safe lowercase'),
            ({'family_id': 'a_b'}, 'family_id must be a safe lowercase'),
            ({'family_id': ''}, 'family_id must be a safe lowercase'),
            ({'family_id': 7}, 'family_id must be a safe lowercase'),
            ({'family_label': ''}, 'family_label must be a nonempty string'),
            ({'family_label': '   '}, 'family_label must be a nonempty string'),
            ({'family_label': 7}, 'family_label must be a nonempty string'),
        ]:
            with self.subTest(override=override):
                with self.assertRaisesRegex(ValueError, message):
                    self.cases_with([{'id': 'x', 'size_px': 16, **override}])

    def test_canvas_area_limit(self):
        with self.assertRaisesRegex(ValueError, 'Uncropped canvas exceeds'):
            self.cases_with([{'id': 'big', 'size_px': 96, 'width': 16384, 'text': 'a\nb\nc'}])

    def test_boolean_pipeline_flags_reject_non_bool(self):
        for key in ['diagonal_fitting', 'include_stubs', 'font_instructions']:
            for value in [1, 0, 'yes']:
                with self.subTest(key=key, value=value):
                    with self.assertRaisesRegex(ValueError, f'{key} must be boolean'):
                        self.cases_with([{'id': 'x', 'size_px': 16, key: value}])

    def test_pipeline_enum_settings_reject_unknown_values(self):
        for override in [{'fitting': 'nope'}, {'rasterization': 'nope'}, {'dropout': 'nope'}]:
            with self.subTest(override=override):
                with tempfile.TemporaryDirectory() as temporary:
                    config = Path(temporary) / 'cases.json'
                    config.write_text(json.dumps([{'id': 'x', 'size_px': 16, **override}]))
                    with patch.object(samples, 'resolve_renderer_policy') as policy, \
                            self.assertRaises(ValueError) as raised:
                        samples.cases_from(self.options('--config', str(config)))
                self.assertEqual(str(raised.exception), 'Invalid Glypherie pipeline or scan settings')
                policy.assert_not_called()

    def test_font_location_errors_come_before_scalar_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = str(Path(temporary) / 'Missing.ttf')
            with patch.object(samples, 'urlopen', side_effect=AssertionError('network')):
                with self.assertRaisesRegex(ValueError, 'Font not found'):
                    self.cases_with([{'id': 'x', 'size_px': 999, 'font': missing}])
                with self.assertRaisesRegex(ValueError, 'http'):
                    self.cases_with([{'id': 'x', 'size_px': 16, 'font': missing,
                        'font_url': 'ftp://example.test/F.ttf', 'font_sha256': samples.sha(b'd')}])
                with self.assertRaisesRegex(ValueError, 'requires a pinned'):
                    self.cases_with([{'id': 'x', 'size_px': 16, 'font': missing,
                        'font_url': 'https://example.test/F.ttf'}])
            font = Path(temporary) / 'Local.ttf'
            font.write_bytes(b'local bytes')
            with patch.object(samples, 'urlopen', side_effect=AssertionError('network')):
                with self.assertRaisesRegex(ValueError, 'Font identity mismatch'):
                    self.cases_with([{'id': 'x', 'size_px': 16, 'font': str(font),
                        'font_sha256': samples.sha(b'other bytes')}])

    def test_pinned_download_runs_before_scalar_validation(self):
        data = b'pinned font bytes'
        with tempfile.TemporaryDirectory() as temporary:
            font = Path(temporary) / 'Pinned.ttf'
            args = self.options('--config', str(self._config(temporary, [{'id': 'x', 'size_px': 999,
                'font': str(font), 'font_url': 'https://example.test/P.ttf',
                'font_sha256': samples.sha(data)}])))
            seen = []
            def fake_urlopen(url, timeout=120):
                seen.append(url)
                return _PinnedDownload(data)
            with patch.object(samples, 'urlopen', fake_urlopen):
                with self.assertRaisesRegex(ValueError, 'size_px must be an integer'):
                    samples.cases_from(args)
            self.assertEqual(seen, ['https://example.test/P.ttf'])
            self.assertEqual(font.read_bytes(), data)

    def _config(self, directory, entries):
        config = Path(directory) / 'cases.json'
        config.write_text(json.dumps(entries))
        return str(config)

    def test_ids_register_before_font_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = str(Path(temporary) / 'Missing.ttf')
            entries = [{'id': 'same', 'size_px': 16},
                       {'id': 'same', 'size_px': 16, 'font': missing}]
            with patch.object(samples, 'urlopen', side_effect=AssertionError('network')):
                with self.assertRaisesRegex(ValueError, 'unique safe id'):
                    self.cases_with(entries)

    def test_policy_check_runs_before_later_entries(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = str(Path(temporary) / 'Missing.ttf')
            entries = [{'id': 'a', 'size_px': 16, 'fitting': 'source_relative'},
                       {'id': 'b', 'size_px': 16, 'font': missing}]
            with patch.object(samples, 'urlopen', side_effect=AssertionError('network')):
                with self.assertRaisesRegex(ValueError, 'Diagonal fitting requires'):
                    self.cases_with(entries)

    def test_earlier_download_side_effect_survives_later_failure(self):
        data = b'first font bytes'
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / 'First.ttf'
            entries = [{'id': 'first', 'size_px': 16, 'font': str(first),
                        'font_url': 'https://example.test/First.ttf',
                        'font_sha256': samples.sha(data)},
                       {'id': 'second', 'size_px': 999}]
            config = Path(temporary) / 'cases.json'
            config.write_text(json.dumps(entries))
            with patch.object(samples, 'urlopen', return_value=_PinnedDownload(data)):
                with self.assertRaisesRegex(ValueError, 'size_px must be an integer'):
                    samples.cases_from(self.options('--config', str(config)))
            self.assertEqual(first.read_bytes(), data)

    def test_successful_pinned_download_is_used(self):
        data = b'downloaded font bytes'
        with tempfile.TemporaryDirectory() as temporary:
            font = Path(temporary) / 'Pinned.ttf'
            entries = [{'id': 'pinned', 'size_px': 16, 'font': str(font),
                        'font_url': 'https://example.test/P.ttf', 'font_sha256': samples.sha(data)}]
            config = Path(temporary) / 'cases.json'
            config.write_text(json.dumps(entries))
            with patch.object(samples, 'urlopen', return_value=_PinnedDownload(data)):
                cases = samples.cases_from(self.options('--config', str(config)))
            self.assertEqual(Path(cases[0]['font']).read_bytes(), data)

    def test_digest_only_cache_hit_avoids_network(self):
        data = b'local digest bytes'
        with tempfile.TemporaryDirectory() as temporary:
            font = Path(temporary) / 'Local.ttf'
            font.write_bytes(data)
            entries = [{'id': 'local', 'size_px': 16, 'font': str(font),
                        'font_sha256': samples.sha(data)}]
            config = Path(temporary) / 'cases.json'
            config.write_text(json.dumps(entries))
            with patch.object(samples, 'urlopen', side_effect=AssertionError('network')):
                cases = samples.cases_from(self.options('--config', str(config)))
            self.assertEqual(Path(cases[0]['font']).read_bytes(), data)

    def test_cli_and_config_precedence(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / 'cases.json'
            config.write_text(json.dumps([
                {'id': 'overridden', 'size_px': 20, 'threshold': 100},
                {'id': 'inherited', 'size_px': 16},
            ]))
            cases = samples.cases_from(self.options(
                '--threshold', '200', '--config', str(config)))
            by_id = {case['id']: case for case in cases}
            self.assertEqual(by_id['overridden']['threshold'], 100)
            self.assertEqual(by_id['inherited']['threshold'], 200)
            self.assertEqual(by_id['overridden']['size_px'], 20)
            absolute = samples.ROOT / 'fonts/SourceSans3.ttf'
            config.write_text(json.dumps([{'id': 'abs', 'size_px': 16, 'font': str(absolute)}]))
            cases = samples.cases_from(self.options('--config', str(config)))
            self.assertEqual(cases[0]['font'], str(absolute.resolve()))

    def test_default_axes_object_is_shared_across_cases(self):
        cases = samples.cases_from(self.options('--size', '16', '--size', '20'))
        self.assertIs(cases[0]['axes'], cases[1]['axes'])
        self.assertIsNot(cases[0], cases[1])

    def test_publish_requires_exactly_one_case(self):
        with self.assertRaisesRegex(ValueError, 'exactly one case'):
            samples.cases_from(self.options('--size', '16', '--size', '20', '--publish'))
        cases = samples.cases_from(self.options('--size', '16', '--publish'))
        self.assertEqual(len(cases), 1)

    def test_config_relative_font_resolves_against_config_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            nested = Path(temporary) / 'a' / 'b'
            nested.mkdir(parents=True)
            (nested / 'nearby.ttf').write_bytes(b'font bytes')
            (nested / 'cases.json').write_text(json.dumps([{'id': 'rel', 'size_px': 16, 'font': 'nearby.ttf'}]))
            previous = os.getcwd()
            os.chdir(temporary)
            try:
                with patch.object(samples, 'resolve_renderer_policy', return_value=None) as policy, \
                        patch.object(samples, 'urlopen', side_effect=AssertionError('network')):
                    cases = samples.cases_from(self.options('--config', str(nested / 'cases.json')))
            finally:
                os.chdir(previous)
        self.assertEqual(cases[0]['font'], str((nested / 'nearby.ttf').resolve()))
        policy.assert_called_once_with(cases[0])


class CasesFromBoundaries(unittest.TestCase):
    def options(self, *args):
        with patch.object(sys, 'argv', ['generate.py', *args]):
            return samples.arguments()

    def valid_cases(self, entries, *args):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / 'cases.json'
            config.write_text(json.dumps(entries))
            with patch.object(samples, 'resolve_renderer_policy', return_value=None) as policy:
                cases = samples.cases_from(self.options(*args, '--config', str(config)))
        return cases, policy

    def test_accepted_numeric_endpoints(self):
        points = [('size_px', 4), ('size_px', 96), ('threshold', 1), ('threshold', 254),
            ('width', 64), ('width', 16384), ('line_step', 1), ('line_step', 1024),
            ('stem_target_px', 0.5), ('stem_target_px', 4)]
        for field, value in points:
            with self.subTest(field=field, value=value):
                entry = {'id': 'edge', 'size_px': 16}
                entry[field] = value
                cases, policy = self.valid_cases([entry])
                self.assertEqual(cases[0][field], value)
                policy.assert_called_once_with(cases[0])

    def test_accepted_maximum_text_length(self):
        text = 'b' * 8192
        cases, policy = self.valid_cases([{'id': 'long', 'size_px': 16, 'text': text}])
        self.assertEqual(cases[0]['text'], text)
        policy.assert_called_once_with(cases[0])

    def test_exact_canvas_area_accepted_and_above_rejected(self):
        text = '\n'.join(['a'] * 6)
        cases, policy = self.valid_cases([{'id': 'exact', 'size_px': 4, 'width': 16384, 'text': text, 'line_step': 200}])
        self.assertEqual((cases[0]['size_px'], cases[0]['width'], cases[0]['line_step']), (4, 16384, 200))
        policy.assert_called_once_with(cases[0])
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / 'cases.json'
            config.write_text(json.dumps([{'id': 'over', 'size_px': 4, 'width': 16384, 'text': text, 'line_step': 201}]))
            with patch.object(samples, 'resolve_renderer_policy') as policy:
                with self.assertRaisesRegex(ValueError, 'Uncropped canvas exceeds'):
                    samples.cases_from(self.options('--config', str(config)))
                policy.assert_not_called()

    def test_explicit_valid_settings_reach_policy(self):
        entry = {'id': 'explicit', 'size_px': 16, 'fitting': 'font_hints_auto',
            'rasterization': 'free_type_mono_terminals', 'dropout': 'smart',
            'diagonal_fitting': True, 'include_stubs': True, 'font_instructions': True}
        cases, policy = self.valid_cases([entry])
        sent = policy.call_args[0][0]
        for key in ['fitting', 'rasterization', 'dropout', 'diagonal_fitting', 'include_stubs', 'font_instructions']:
            self.assertEqual(sent[key], entry[key])
        self.assertEqual(sent, cases[0])

    def test_text_file_read_and_precedence(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'sample.txt'
            source.write_text('file line one\nfile line two')
            cases, _ = self.valid_cases([{'id': 'file', 'size_px': 16}], '--text-file', str(source))
            self.assertEqual(cases[0]['text'], 'file line one\nfile line two')
            cases, _ = self.valid_cases([{'id': 'file', 'size_px': 16}], '--text-file', str(source), '--text', 'cli text')
            self.assertEqual(cases[0]['text'], 'file line one\nfile line two')
            cases, _ = self.valid_cases([{'id': 'entry', 'size_px': 16, 'text': 'config text'}], '--text-file', str(source))
            self.assertEqual(cases[0]['text'], 'config text')

    def test_missing_size_and_null_scalars_rejected(self):
        rejects = [({'id': 'nosize'}, 'size_px must be an integer'),
            ({'id': 'x', 'size_px': 16, 'text': None}, 'Text must contain printable ASCII'),
            ({'id': 'x', 'size_px': 16, 'threshold': None}, 'threshold must be an integer'),
            ({'id': 'x', 'size_px': 16, 'width': None}, 'width must be 64')]
        for entry, message in rejects:
            with self.subTest(entry=entry):
                with tempfile.TemporaryDirectory() as temporary:
                    config = Path(temporary) / 'cases.json'
                    config.write_text(json.dumps([entry]))
                    with self.assertRaisesRegex(ValueError, message):
                        samples.cases_from(self.options('--config', str(config)))

    def test_stem_nan_and_infinity_rejected(self):
        for value in [float('nan'), float('inf'), float('-inf')]:
            with self.subTest(value=value):
                with tempfile.TemporaryDirectory() as temporary:
                    config = Path(temporary) / 'cases.json'
                    config.write_text(json.dumps([{'id': 'x', 'size_px': 16, 'stem_target_px': value}]))
                    with self.assertRaisesRegex(ValueError, 'stem_target_px must be in'):
                        samples.cases_from(self.options('--config', str(config)))


if __name__ == '__main__':
    unittest.main()
