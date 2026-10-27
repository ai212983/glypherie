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


if __name__ == '__main__':
    unittest.main()
