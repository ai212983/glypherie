"""Render every numerically checked baseline case with native and enlarged views."""
import argparse
import html
import json
from pathlib import Path

import freetype as ft
from PIL import Image, ImageDraw

from check_shamir_baseline import digest
from compare_paper_prototypes import render, pixels, draw_glyph


def extent(glyphs):
    ink = set().union(*(pixels(g) for g in glyphs))
    if not ink:
        return (0, -1, 1, 1)
    xs, ys = zip(*ink)
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def pair_image(glyphs, label):
    x0, y0, x1, y1 = extent(glyphs)
    scale, pad = 8, 16
    width = max(240, (x1 - x0) * scale + pad * 2)
    image = Image.new('RGB', (width * 2, (y1 - y0) * scale + 76), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((pad, 5), label, fill='black')
    for i, (glyph, title) in enumerate(zip(glyphs, ('Unhinted input', 'Baseline'))):
        draw.text((width * i + pad, 25), title, fill='black')
        draw_glyph(draw, glyph, width * i + pad - x0 * scale, 54 - y0 * scale, scale)
    return image


def native_text(face, text, size, hinted):
    items, cursor = [], 0
    for char in text:
        glyph = render(face, char, size, hinted=hinted)
        items.append((round(cursor), glyph))
        cursor += glyph['advance_26_6'] / 64
    ink = {(x + offset, y) for offset, glyph in items for x, y in pixels(glyph)}
    x0 = min((p[0] for p in ink), default=0)
    y0 = min((p[1] for p in ink), default=0)
    x1 = max((p[0] for p in ink), default=round(cursor)) + 1
    y1 = max((p[1] for p in ink), default=0) + 1
    image = Image.new('RGB', (max(x1, round(cursor)) - min(x0, 0) + 16, y1 - y0 + 16), 'white')
    draw = ImageDraw.Draw(image)
    for offset, glyph in items:
        draw_glyph(draw, glyph, offset - min(x0, 0) + 8, 8 - y0, 1)
    return image


def gallery(report_path):
    report_path = Path(report_path)
    report = json.loads(report_path.read_text())
    if not report['native_execution_passed'] or not report['graph_invariants_passed']:
        raise ValueError('gallery requires passing numerical and graph checks')
    if tuple(report['versions']['freetype']) != ft.version():
        raise ValueError('renderer FreeType differs from verification')
    root = report_path.parent
    for name, sha in report['source_hashes'].items():
        if digest(root / 'sources' / name) != sha:
            raise ValueError(f'changed frozen source: {name}')
    for name, sha in report['paper_hashes'].items():
        if digest(root / 'papers' / name) != sha:
            raise ValueError(f'changed frozen paper: {name}')
    for name in ('render_shamir_baseline.py', 'compare_paper_prototypes.py', 'paper_gridfit.py'):
        if digest(Path(__file__).parent / name) != report['source_hashes'].get(name):
            raise ValueError(f'renderer differs from frozen source: {name}')
    out = root / 'gallery'
    out.mkdir(exist_ok=True)
    if any(out.iterdir()):
        raise ValueError('gallery directory must be empty; preserve earlier image evidence')
    rows, sections = [], []
    text_lines = ('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz',
                  '0123456789 .,;:!?%°+-/()[]"\'=')
    for build in report['builds']:
        source, target = root / build['input'], root / build['output']
        if digest(source) != build['source_sha256'] or digest(target) != build['font_sha256']:
            raise ValueError('font differs from frozen verification')
        faces = [ft.Face(str(source)), ft.Face(str(target))]
        name, size = build['font'], build['size']
        title = f'{name} {size}px'
        section = f'<section><h2>{html.escape(title)}</h2><h3>Native-size text</h3>'
        for line_id, line in enumerate(text_lines):
            for index, (face, label) in enumerate(zip(faces, ('Unhinted input', 'Baseline'))):
                filename = f'{name}-{size}-text-{line_id}-{index}.png'
                image = native_text(face, line, size, bool(index))
                image.save(out / filename)
                section += f'<div class="native"><span>{label}</span><img src="{filename}" width="{image.width}" height="{image.height}" alt="{html.escape(line, quote=True)}"></div>'
        section += '<h3>Individual glyphs (8× pixels)</h3>'
        for case in build['cases']:
            char = case['char']
            glyphs = [render(face, char, size, hinted=bool(i)) for i, face in enumerate(faces)]
            filename = f'{name}-{size}-u{ord(char):04x}.png'
            pair_image(glyphs, f'{title} U+{ord(char):04X} {char!r}').save(out / filename)
            rows.append({'font': name, 'size': size, 'char': char, 'image': filename,
                         'unhinted_pixels': sorted(pixels(glyphs[0])), 'baseline_pixels': sorted(pixels(glyphs[1]))})
            section += f'<figure><img loading="lazy" src="{filename}" alt="U+{ord(char):04X} unhinted input and baseline"></figure>'
        sections.append(section + '</section>')
    readiness = html.escape(report['baseline_readiness'])
    (out / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Shamir baseline review</title>'
        '<style>body{font:16px system-ui;margin:24px}h2{margin-top:40px}.native{display:flex;gap:16px;align-items:center;overflow:auto}'
        '.native span{min-width:130px}.native img{max-width:none;flex-shrink:0}figure{display:inline-block;vertical-align:top;margin:6px;max-width:100%;overflow:auto}'
        'figure img{max-width:none;image-rendering:pixelated}.status{padding:16px;background:#fff4d6}</style>'
        '<h1>Shamir baseline review</h1><p class="status">' + readiness + '</p>'
        '<p>Numerical execution and graph checks passed. Visual assessment and source fidelity are separate conclusions. '
        'Each pair shows unhinted input on the left and the baseline on the right. Native text uses one image pixel per CSS pixel at 100% browser zoom.</p>'
        + ''.join(sections))
    manifest = {'verification_sha256': digest(report_path), 'renderer_sha256': digest(Path(__file__)),
                'cases': rows, 'files': {p.name: digest(p) for p in sorted(out.iterdir()) if p.is_file()}}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'cases': len(rows), 'gallery': str(out / 'index.html')}))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('report', type=Path)
    gallery(parser.parse_args().report)
