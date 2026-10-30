"""Crosspoint capture adapter; binary layout and quantization follow pinned upstream.

https://github.com/crosspoint-reader/crosspoint-reader/blob/10709120e66c0e0604aebc4991cc69830fb4c2b2/lib/EpdFont/scripts/fontconvert_sdcard.py
"""
import hashlib
import struct
from urllib.request import urlopen

REVISION = '10709120e66c0e0604aebc4991cc69830fb4c2b2'
SOURCE_URL = f'https://github.com/crosspoint-reader/crosspoint-reader/blob/{REVISION}/lib/EpdFont/scripts/fontconvert_sdcard.py'
RENDERER_URL = f'https://github.com/crosspoint-reader/crosspoint-reader/blob/{REVISION}/lib/GfxRenderer/GlyphBitmap.h'
SOURCES = {
    'fontconvert_sdcard.py': '21441059aa9bf5f429ecddfbf57148022c43e7d5300279b5039a6ea138ee69fb',
    'cpfont_version.py': '97181fc45b1c06fa7781c6a5bf9040978b68a79533855628fe4081d2fa730171',
}


def prepare(cache):
    import freetype
    directory = cache / 'crosspoint'
    directory.mkdir(parents=True, exist_ok=True)
    for name, digest in SOURCES.items():
        path = directory / name
        if not path.exists():
            with urlopen(f'https://raw.githubusercontent.com/crosspoint-reader/crosspoint-reader/{REVISION}/lib/EpdFont/scripts/{name}', timeout=60) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError(f'Crosspoint source checksum mismatch: {name}')
            path.write_bytes(data)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f'Crosspoint source checksum mismatch: {name}')
    source = (directory / 'fontconvert_sdcard.py').read_text()
    original = '    face.set_char_size(size << 6, size << 6, 150, 150)'
    if source.count(original) != 1:
        raise ValueError('Crosspoint source no longer matches the exact-pixel-size adapter')
    # As with Adafruit, normalize only the size API. Keep upstream glyph loading,
    # hinting, 2-bit quantization, metrics and packing intact.
    adapted = source.replace(original, '    face.set_pixel_sizes(0, size)')
    script = directory / 'fontconvert_sdcard_px.py'
    script.write_text(adapted)
    return script, {
        'revision': REVISION,
        'source_sha256': SOURCES,
        'adapter_sha256': hashlib.sha256(adapted.encode()).hexdigest(),
        'adapter': 'set_char_size(points at 150 DPI) replaced with set_pixel_sizes(ppem); all other converter code unchanged.',
        'freetype': '.'.join(map(str, freetype.version())),
        'source_bits': 2,
        'monochrome': 'Firmware BW mode: packed coverage levels 1, 2 and 3 become black; level 0 stays white.',
        'renderer_url': RENDERER_URL,
        'source_kerning': True,
        'ligatures': False,
    }


def _header(data):
    """Validate the container header once for glyph and pair decoding."""
    if len(data) < 64:
        raise ValueError('Crosspoint: truncated cpfont')
    magic, version, flags, styles = struct.unpack_from('<8sHHB19x', data, 0)
    if (magic, version, flags, styles) != (b'CPFONT\0\0', 4, 1, 1):
        raise ValueError('Crosspoint: expected single-style v4 2-bit cpfont')
    style, intervals, count, _, _, _, kern_l, kern_r, classes_l, classes_r, ligatures, start = struct.unpack_from('<B3xIIBhhHHBBBI4x', data, 32)
    if style != 0 or start != 64:
        raise ValueError('Crosspoint: unexpected style or section offset')
    return intervals, count, kern_l, kern_r, classes_l, classes_r, ligatures, start


def glyphs(path):
    """Decode v4 exports, retaining 12.4 advances and baseline-relative bearings.

    Upstream packs four coverage samples per byte, MSB first across rows. The
    firmware BW rule paints every non-white level, preserving monochrome scope.
    Kerning is decoded separately; ligatures remain disabled during composition.
    """
    from PIL import Image
    data = path.read_bytes()
    intervals, count, kern_l, kern_r, classes_l, classes_r, ligatures, start = _header(data)

    def unpack(fmt, offset):
        if offset < 0 or offset + struct.calcsize(fmt) > len(data):
            raise ValueError('Crosspoint: truncated cpfont')
        return struct.unpack_from(fmt, data, offset)

    codepoints = []
    for index in range(intervals):
        first, last, offset = unpack('<III', start + index * 12)
        if first > last or last > 0x10ffff or offset != len(codepoints) or (codepoints and first <= codepoints[-1]) or last - first + 1 > count - len(codepoints):
            raise ValueError('Crosspoint: invalid Unicode intervals')
        codepoints.extend(range(first, last + 1))
    if len(codepoints) != count:
        raise ValueError('Crosspoint: inconsistent glyph count')
    records = start + intervals * 12
    bitmaps = records + count * 16 + (kern_l + kern_r) * 3 + classes_l * classes_r + ligatures * 8
    if bitmaps > len(data):
        raise ValueError('Crosspoint: truncated cpfont')
    result = {}
    bitmap_end = 0
    for index, cp in enumerate(codepoints):
        width, height, advance, left, top, length, offset = unpack('<BBHhhH2xI', records + index * 16)
        if length != (width * height + 3) // 4 or offset != bitmap_end or bitmaps + offset + length > len(data):
            raise ValueError('Crosspoint: invalid glyph bitmap')
        bitmap_end = offset + length
        if not 32 <= cp <= 126:
            continue
        packed = data[bitmaps + offset:bitmaps + offset + length]
        image = Image.new('L', (width, height))
        image.putdata([255 if ((packed[i // 4] >> (6 - 2 * (i % 4))) & 3) != 0 else 0 for i in range(width * height)])
        result[chr(cp)] = (image, advance / 16, left, -top)
    if bitmaps + bitmap_end != len(data) or set(result) != {chr(cp) for cp in range(32, 127)}:
        raise ValueError('Crosspoint: invalid bitmap extent or missing printable ASCII')
    return result


def pairs(path):
    """Read native class kerning exactly as EpdFont::getKerning (signed 4.4).

    https://github.com/crosspoint-reader/crosspoint-reader/blob/10709120e66c0e0604aebc4991cc69830fb4c2b2/lib/EpdFont/EpdFont.cpp
    Validates the container header and kerning extents; call glyphs first to
    validate the glyph section extents.
    """
    data = path.read_bytes()
    intervals, count, kern_l, kern_r, classes_l, classes_r, _, start = _header(data)
    offset = start + intervals * 12 + count * 16
    if offset + (kern_l + kern_r) * 3 + classes_l * classes_r > len(data):
        raise ValueError('Crosspoint: truncated cpfont')

    def read_classes(count, maximum):
        nonlocal offset
        result = {}
        for _ in range(count):
            codepoint, class_id = struct.unpack_from('<HB', data, offset)
            offset += 3
            if codepoint in result or not 1 <= class_id <= maximum:
                raise ValueError('Crosspoint: invalid kerning class')
            result[codepoint] = class_id
        return result

    left = read_classes(kern_l, classes_l)
    right = read_classes(kern_r, classes_r)
    result = {}
    for a, lc in left.items():
        for b, rc in right.items():
            value = struct.unpack_from('<b', data, offset + (lc - 1) * classes_r + rc - 1)[0]
            if value and 32 <= a <= 126 and 32 <= b <= 126:
                result[(chr(a), chr(b))] = value / 16
    return result
