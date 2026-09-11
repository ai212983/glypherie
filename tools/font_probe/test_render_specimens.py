import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from contact import contact
from render_specimens import pack, page, install_session


class SpecimenTests(unittest.TestCase):
    def test_board_bit_order_and_gray_polarity(self):
        image = Image.new('L', (8, 1), 255)
        image.putpixel((0, 0), 0)
        self.assertEqual(pack(image, 'waveshare', 1), b'\x80')
        inkplate = pack(image, 'inkplate', 1)
        self.assertEqual(inkplate[:10], b'MDFR\x01\x00\x08\x00\x01\x00')
        self.assertEqual(inkplate[16:], b'\x01')
        self.assertEqual(pack(image, 'inkplate', 3)[16:], b'\x0e\xee\xee\xee')

    def test_rows_are_padded_independently(self):
        image = Image.new('L', (9, 2), 255)
        image.putpixel((8, 0), 0)
        image.putpixel((0, 1), 0)
        self.assertEqual(pack(image, 'waveshare', 1), b'\x00\x80\x80\x00')

    def test_oversize_sample_fails(self):
        generated = {'config': {'size_px': 100, 'output_bits': 1}, 'kerning': [],
                     'glyphs': [{'codepoint': ord(c), 'left': 0, 'top': -200,
                                 'width': 1, 'height': 200, 'pixels': [1] * 200,
                                 'advance_26_6': 64} for c in '23°C']}
        with self.assertRaisesRegex(ValueError, 'exceeds canvas'):
            page({'panel': 'waveshare', 'role': 'ambient_primary', 'id': 'test'}, generated)

    def test_normal_inverse_samples_match_and_binary_stays_binary(self):
        generated = {'config': {'size_px': 100, 'output_bits': 1}, 'kerning': [],
                     'glyphs': [{'codepoint': ord(c), 'left': 0, 'top': -2,
                                 'width': 1, 'height': 2, 'pixels': [1, 1],
                                 'advance_26_6': 128} for c in '23°C']}
        image, _ = page({'panel': 'waveshare', 'role': 'ambient_primary', 'id': 'test'}, generated)
        self.assertEqual(image.size, (400, 300))
        self.assertEqual(set(image.tobytes()), {0, 255})
        for y in range(30, 150):
            for x in range(400):
                self.assertEqual(image.getpixel((x, y)) + image.getpixel((x, y + 150)), 255)

    def test_contact_ignores_stale_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new('L', (10, 10), 255).save(root / 'current.png')
            (root / 'stale.png').write_text('invalid image')
            manifest = {'pages': [{'id': 'current', 'panel': 'waveshare', 'width': 10,
                                    'height': 10, 'png': 'current.png'}]}
            path = root / 'manifest.json'
            path.write_text(json.dumps(manifest))
            self.assertEqual(contact(path, root / 'contact'), ['CONTACT_waveshare_01.png'])

    def test_session_uses_exact_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'current.bin').write_bytes(bytes(15000))
            path = root / 'manifest.json'
            path.write_text(json.dumps({'pages': [
                {'id': name, 'panel': 'waveshare', 'frame': name + '.bin'}
                for name in ['current', 'stale']]}))
            module = root / 'session/calibration.rs'
            install_session(path, module, 'waveshare', ['current'])
            self.assertIn('current.bin', module.read_text())
            self.assertNotIn('stale', module.read_text())
            with self.assertRaises(ValueError):
                install_session(path, module, 'waveshare', ['current'] * 9)


if __name__ == '__main__':
    unittest.main()
