"""Export/presentation boundary for the source-to-bitmap pipeline.

``build_source_bitmap.py`` owns fitting and the generation pipeline; this
module owns everything after the final render is verified: per-face
bitmap/metric JSON records, native-scale and enlarged PNG specimens, and
the per-glyph HTML panels that reference them. It takes coordinates,
bitmap dictionaries and metric tuples only: no character, font-family or
size exception tables.
"""

import json
import platform
from pathlib import Path

import freetype as ft
import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
ENLARGE = 8


def repo_relative(path):
    """Reusable repo-relative display path for a generation input."""
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(resolved)


def environment():
    """Tool versions that produced an export (no local paths)."""
    import fontTools
    versions = {
        'python': platform.python_version(),
        'freetype': list(ft.version()),
        'fonttools': fontTools.__version__,
        'numpy': np.__version__,
        'pillow': Image.__version__,
    }
    return versions


def glyph_record(char, size, glyph, native_points, advance_hmtx):
    """One reviewable record from the exact final render of a glyph.

    ``glyph`` is the ``bitmap()`` dictionary from the exported font,
    ``native_points`` the verified native coordinates, ``advance_hmtx``
    the ``(advanceWidth, leftSideBearing)`` tuple from the exported font.
    """
    from compare_paper_prototypes import pixels
    ink = sorted(pixels(glyph))
    return {
        'char': char,
        'codepoint': glyph['codepoint'],
        'size': size,
        'width': glyph['width'],
        'height': glyph['height'],
        'left': glyph['left'],
        'top': glyph['top'],
        'advance_26_6': glyph['advance_26_6'],
        'advance_hmtx': list(advance_hmtx),
        'pixels': list(glyph['pixels']),
        'ink': [list(p) for p in ink],
        'native_points_px': np.asarray(native_points, float).tolist(),
    }


def write_face_json(output, key, size, records):
    """Write ``{key}-bitmap.json``; return its repo-relative display path."""
    path = Path(output) / f'{key}-bitmap.json'
    path.write_text(json.dumps(
        {'key': key, 'size': size, 'glyphs': records}, indent=1) + '\n')
    return path


def write_specimens(output, key, char, glyph):
    """Native-scale and nearest-neighbor enlarged PNGs for one glyph.

    Returns ``(native_name, large_name)`` relative to the output root.
    Blank (zero-area) renders get a 1x1 white placeholder so every
    admitted glyph stays reviewable.
    """
    code = f'u{ord(char):04x}'
    native_name = f'img/{key}-{code}-native.png'
    large_name = f'img/{key}-{code}-x{ENLARGE}.png'
    width, height = max(1, glyph['width']), max(1, glyph['height'])
    image = Image.new('1', (width, height), 1)
    for i, value in enumerate(glyph['pixels']):
        if value and glyph['width'] and glyph['height']:
            image.putpixel((i % glyph['width'], i // glyph['width']), 0)
    native = image.convert('L')
    native.save(Path(output) / native_name)
    native.resize((width * ENLARGE, height * ENLARGE),
                  Image.NEAREST).save(Path(output) / large_name)
    return native_name, large_name


def panel_html(key, char, status, delta, record, native_name, large_name):
    """Per-glyph HTML section with reviewable specimens and metrics."""
    import html as html_mod
    code = f'u{ord(char):04x}'
    return (
        f'<section id="{key}-{code}"><h2>{html_mod.escape(key)} '
        f'{html_mod.escape(char)}</h2>'
        f'<p>{status}; {delta} pixels from pre-recovery input. '
        f'advance {record["advance_hmtx"][0]}/{record["advance_26_6"]} '
        f'bearings ({record["left"]},{record["top"]}) '
        f'{record["width"]}x{record["height"]}.</p>'
        f'<img src="{native_name}" alt="{html_mod.escape(char)} native"> '
        f'<img src="{large_name}" alt="{html_mod.escape(char)} enlarged '
        f'x{ENLARGE}" width="{max(1, record["width"]) * ENLARGE}" '
        f'height="{max(1, record["height"]) * ENLARGE}"></section>')


def check_face_agreement(face_json, ttf_path):
    """Re-render the exported TTF and compare every exported record.

    Returns a list of ``(char, problem)`` pairs; empty means the JSON
    agrees with the font it was exported from.
    """
    from audit_terminal_coverage import coords
    from compare_paper_prototypes import render
    data = json.loads(Path(face_json).read_text())
    size = data['size']
    problems = []
    face = ft.Face(str(ttf_path))
    with TTFont(str(ttf_path)) as font:
        cmap = font.getBestCmap()
        for char, record in data['glyphs'].items():
            fresh = render(ft.Face(str(ttf_path)), char, size, hinted=True)
            for field in ('codepoint', 'width', 'height', 'left', 'top',
                          'advance_26_6', 'pixels'):
                if fresh[field] != record[field]:
                    problems.append((char, f'{field} drift'))
            advance = list(font['hmtx'][cmap[ord(char)]])
            if advance != record['advance_hmtx']:
                problems.append((char, 'advance drift'))
            actual = coords(face, char, size)
            if np.max(abs(actual - np.asarray(record['native_points_px']))) > 1e-9:
                problems.append((char, 'native coordinate drift'))
    return problems
