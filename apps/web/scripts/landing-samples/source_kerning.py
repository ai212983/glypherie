"""Source pair adjustments for comparison formats without imported kerning.

HarfBuzz shapes with kern off/on, retaining the same scalar glyphs and advances:
https://harfbuzz.github.io/shaping-opentype-features.html
Only the first advance may change; richer positioning cannot be represented by
the comparison compositor and must fail rather than silently distort layout.
"""
import uharfbuzz as hb


def pairs(font_path, size, text):
    face = hb.Face(font_path.read_bytes())
    font = hb.Font(face)
    font.scale = (face.upem, face.upem)
    result = {}

    def shape(pair, kerning):
        buffer = hb.Buffer()
        buffer.add_str(pair)
        buffer.guess_segment_properties()
        hb.shape(font, buffer, {'kern': kerning, 'liga': False, 'clig': False, 'calt': False})
        return [g.codepoint for g in buffer.glyph_infos], buffer.glyph_positions

    requested = {pair for line in text.split('\n') for pair in zip(line, line[1:])}
    for left, right in sorted(requested):
        pair = left + right
        ids_off, off = shape(pair, False)
        ids_on, on = shape(pair, True)
        expected = [font.get_nominal_glyph(ord(ch)) for ch in pair]
        if len(off) != 2 or len(on) != 2 or ids_off != expected or ids_on != expected:
            raise ValueError(f'Source kerning requires scalar glyphs: {pair!r}')
        delta = on[0].x_advance - off[0].x_advance
        if any((a.x_offset, a.y_offset, a.y_advance) != (b.x_offset, b.y_offset, b.y_advance)
               for a, b in zip(off, on, strict=True)) or on[1].x_advance != off[1].x_advance:
            raise ValueError(f'Source kerning requires richer positioning: {pair!r}')
        if delta:
            result[(left, right)] = delta * size / face.upem
    return result
