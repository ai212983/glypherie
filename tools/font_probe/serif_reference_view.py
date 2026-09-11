"""Add a smooth source-outline reference at the comparison's 8x display scale."""
import json
from pathlib import Path
import freetype as ft
from PIL import Image, ImageDraw
from compare_paper_prototypes import render
from compare_shamir_representatives import comparison
from render_shamir_baseline import extent


def reference_comparison(faces, char, size, title):
    glyphs = [render(faces[0], char, size), render(faces[0], char, size, hinted=True),
              render(faces[1], char, size, hinted=True)]
    old = comparison(glyphs, ['Unhinted input', 'Reorientation v2', 'VTT-backed serif experiment'], title)
    return prepend_reference(faces[0], char, size, title, glyphs, old)


def prepend_reference(face, char, size, title, glyphs, old):
    x0, y0, _, _ = extent(glyphs); width = old.width//len(glyphs)
    result = Image.new('RGB', (old.width+width, old.height), 'white')
    result.paste(old, (width, 0))
    draw = ImageDraw.Draw(result)
    draw.text((16, 5), title, fill='black')
    draw.text((16, 26), 'Smooth source outline (8x)', fill='black')
    face.set_pixel_sizes(0, size*8)
    face.load_char(char, ft.FT_LOAD_NO_HINTING | ft.FT_LOAD_NO_BITMAP | ft.FT_LOAD_RENDER | ft.FT_LOAD_TARGET_NORMAL)
    bitmap = face.glyph.bitmap
    if bitmap.width and bitmap.rows:
        coverage = Image.frombytes('L', (abs(bitmap.pitch), bitmap.rows), bytes(bitmap.buffer))
        coverage = coverage.crop((0, 0, bitmap.width, bitmap.rows))
        if bitmap.pitch < 0: coverage = coverage.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        result.paste('black', (16-x0*8+face.glyph.bitmap_left,
                              55-y0*8-face.glyph.bitmap_top), coverage)
    return result


def update(directory):
    report = json.loads((directory/'report.json').read_text())
    for case in report['cases']:
        key, char = case['key'], case['char']; size = int(key.rsplit('-', 1)[1])
        faces = [ft.Face(str(directory/f'{key}-{suffix}.ttf')) for suffix in ('reoriented', 'serif')]
        reference_comparison(faces, char, size, f'{key} {char!r}').save(directory/f'{key}-u{ord(char):04x}.png')
    path = directory/'index.html'; text = path.read_text()
    text = text.replace('Columns: unhinted input, reorientation v2, new serif experiment.',
                        'Columns: smooth source outline at 8x display scale, unhinted pixel input, reorientation v2, new serif experiment.')
    path.write_text(text)


if __name__ == '__main__':
    update(Path(__file__).resolve().parent/'out/vtt-serif-v1')
