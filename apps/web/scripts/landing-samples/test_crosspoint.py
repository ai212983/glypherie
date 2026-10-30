import struct
import tempfile
from pathlib import Path
import unittest

import crosspoint


class CrosspointChecks(unittest.TestCase):
    def fixture(self):
        # Six samples cross a row boundary and end in a partial byte:
        # coverage 0,1,2 / 3,2,1. Space has advance but no bitmap.
        header = struct.pack('<8sHHB19x', b'CPFONT\0\0', 4, 1, 1)
        toc = struct.pack('<B3xIIBhhHHBBBI4x', 0, 1, 95, 20, 15, -5, 0, 0, 0, 0, 0, 64)
        interval = struct.pack('<III', 32, 126, 0)
        records = struct.pack('<BBHhhH2xI', 0, 0, 52, 0, 0, 0, 0)
        records += b''.join(struct.pack('<BBHhhH2xI', 3, 2, 84, -2, 5, 2, i * 2) for i in range(94))
        return header + toc + interval + records + bytes([0b00011011, 0b10010000]) * 94

    def decode(self, data):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'font.cpfont'
            path.write_bytes(data)
            return crosspoint.glyphs(path)

    def decode_pairs(self, data):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'font.cpfont'
            path.write_bytes(bytes(data))
            return crosspoint.pairs(path)

    def test_packed_coverage_row_boundaries_bearings_and_fractional_advances(self):
        glyphs = self.decode(self.fixture())
        self.assertEqual(set(glyphs), {chr(cp) for cp in range(32, 127)})
        image, advance, left, top = glyphs['A']
        self.assertEqual(image.size, (3, 2))
        self.assertEqual(list(image.getdata()), [0, 255, 255, 255, 255, 255])
        self.assertEqual((advance, left, top), (5.25, -2, -5))
        self.assertEqual(glyphs[' '][0].size, (0, 0))
        self.assertEqual(glyphs[' '][1], 3.25)

    def test_rejects_other_versions_and_truncation(self):
        data = self.fixture()
        for truncated in [data[:10], data[:50], data[:-1]]:
            with self.subTest(length=len(truncated)), self.assertRaisesRegex(ValueError, 'truncated|invalid glyph bitmap'):
                self.decode(truncated)
        with self.assertRaisesRegex(ValueError, 'single-style v4'):
            self.decode(data[:8] + struct.pack('<H', 3) + data[10:])

    def test_native_signed_class_kerning_and_zero_default(self):
        data = bytearray(self.fixture())
        # One left class, two right classes, two signed 4.4 matrix entries.
        struct.pack_into('<HHBB', data, 49, 1, 2, 1, 2)
        offset = 76 + 95 * 16
        data[offset:offset] = struct.pack('<HBHBHBbb', ord('A'), 1, ord('V'), 1, ord('T'), 2, -9, 5)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'font.cpfont'
            path.write_bytes(data)
            crosspoint.glyphs(path)
            self.assertEqual(crosspoint.pairs(path), {('A', 'V'): -0.5625, ('A', 'T'): 0.3125})

    def test_pairs_rejects_other_versions_and_truncation_without_glyphs(self):
        data = bytearray(self.fixture())
        struct.pack_into('<H', data, 8, 3)
        with self.assertRaisesRegex(ValueError, 'single-style v4'):
            self.decode_pairs(data)
        for truncated in [self.fixture()[:10], self.fixture()[:50]]:
            with self.subTest(length=len(truncated)), self.assertRaisesRegex(ValueError, 'truncated'):
                self.decode_pairs(truncated)

    def test_pairs_rejects_truncated_class_and_matrix_sections(self):
        data = bytearray(self.fixture())
        struct.pack_into('<HHBB', data, 49, 1, 2, 1, 2)
        offset = 76 + 95 * 16
        data[offset:offset] = struct.pack('<HBHBHBbb', ord('A'), 1, ord('V'), 1, ord('T'), 2, -9, 5)
        with self.assertRaisesRegex(ValueError, 'truncated'):
            self.decode_pairs(bytes(data[:offset + 9 + 1]))
        with self.assertRaisesRegex(ValueError, 'truncated'):
            self.decode_pairs(bytes(data[:offset + 3]))

    def test_pairs_rejects_style_and_section_offset_independently(self):
        for offset, form, value in [(32, '<B', 1), (56, '<I', 65)]:
            with self.subTest(offset=offset):
                data = bytearray(self.fixture())
                struct.pack_into(form, data, offset, value)
                with self.assertRaisesRegex(ValueError, 'style or section offset'):
                    self.decode_pairs(data)

    def test_complete_kerning_matrix_may_end_at_eof(self):
        data = bytearray(self.fixture()[:76])
        struct.pack_into('<HHBB', data, 49, 1, 1, 1, 1)
        data += struct.pack('<BBHhhH2xI', 0, 0, 52, 0, 0, 0, 0) * 95
        data += struct.pack('<HBHBb', ord('A'), 1, ord('V'), 1, -9)
        self.decode(data)
        self.assertEqual(self.decode_pairs(data), {('A', 'V'): -0.5625})

    def test_pairs_rejects_invalid_and_duplicate_class_entries(self):
        for entries in [(('A', 0),), (('A', 2),), (('A', 1), ('A', 1))]:
            with self.subTest(entries=entries):
                data = bytearray(self.fixture())
                struct.pack_into('<HHBB', data, 49, len(entries), 1, 1, 1)
                offset = 76 + 95 * 16
                classes = b''.join(struct.pack('<HB', ord(ch), group) for ch, group in entries)
                data[offset:offset] = classes + struct.pack('<HBb', ord('V'), 1, -9)
                with self.assertRaisesRegex(ValueError, 'invalid kerning class'):
                    self.decode_pairs(data)

    def test_rejects_invalid_intervals_and_bitmap_offsets(self):
        data = bytearray(self.fixture())
        struct.pack_into('<I', data, 72, 1)
        with self.assertRaisesRegex(ValueError, 'Unicode intervals'):
            self.decode(data)
        data = bytearray(self.fixture())
        struct.pack_into('<I', data, 76 + 16 + 12, 10000)
        with self.assertRaisesRegex(ValueError, 'invalid glyph bitmap'):
            self.decode(data)


if __name__ == '__main__':
    unittest.main()
