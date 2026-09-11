"""Compare generator hinting with FreeType mono using one configured font job."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import freetype as ft
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]


def compare(job_path, output):
    job = json.loads(job_path.read_text())
    font = (job_path.parent / job['font']).resolve()
    settings = job['settings']
    digest = hashlib.sha256(font.read_bytes()).hexdigest()
    if digest != job['provenance']['expected_sha256']:
        raise ValueError('font checksum mismatch')
    output.mkdir(parents=True, exist_ok=True)
    job['font'] = os.path.relpath(font, output)
    settings.update(characters='bhmnpu', output_bits=1, mono_threshold=128,
                    kerning=False)
    rows = []
    for mode in ('auto_fallback', 'auto'):
        settings['hinting'] = mode
        path = output / (mode + '.job.json')
        path.write_text(json.dumps(job, indent=2) + '\n')
        artifact = output / (mode + '.json')
        subprocess.run([str(ROOT / 'tools/font_generator/target/release/font_generator'),
                        str(path), str(artifact)], check=True, capture_output=True)
        rows.append((mode, json.loads(artifact.read_text())['generated']['glyphs']))

    face = ft.Face(str(font))
    if face.has_multiple_masters:
        axes = face.get_variation_info().axes
        face.set_var_design_coords([settings['axes'].get(a.tag, a.default) for a in axes])
    size = settings['size_px']
    if size != int(size):
        raise ValueError('comparison requires integer pixel size')
    face.set_pixel_sizes(0, int(size))
    flags = ft.FT_LOAD_RENDER | ft.FT_LOAD_TARGET_MONO | ft.FT_LOAD_MONOCHROME
    glyphs = []
    for char in settings['characters']:
        face.load_char(char, flags)
        g = face.glyph
        b = g.bitmap
        if b.pixel_mode != ft.FT_PIXEL_MODE_MONO or b.pitch < 0:
            raise ValueError('expected positive-pitch mono bitmap')
        buffer = b.buffer
        pixels = [(buffer[y*b.pitch+x//8] >> (7-x%8)) & 1
                  for y in range(b.rows) for x in range(b.width)]
        glyphs.append(dict(codepoint=ord(char), left=g.bitmap_left, top=-g.bitmap_top,
                           width=b.width, height=b.rows, pixels=pixels,
                           advance_26_6=g.advance.x))
    rows.append(('FreeType mono', glyphs))
    evidence = dict(font_sha256=digest, axes=settings['axes'], size_px=size,
                    freetype_version=ft.version(), freetype_load_flags=flags,
                    note='End-to-end path comparison; FreeType mono has no coverage threshold.',
                    rows=[dict(name=name, glyphs=gs) for name, gs in rows])
    (output/'comparison.json').write_text(json.dumps(evidence, indent=2)+'\n')

    # Identical origin and baseline in every cell; draw exact pixels, without smoothing.
    scale = 8
    cell = int(size+5)*scale
    row_height = int(size+9)*scale
    image = Image.new('RGB', (6*cell+24, 3*row_height+50), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((12, 8), f'{font.stem} {size}px | axes {settings["axes"]} | 8x pixels', fill='black')
    for row, (name, gs) in enumerate(rows):
        y = 35+row*row_height
        draw.text((12, y), name, fill='black')
        for col, g in enumerate(gs):
            x = 12+col*cell
            draw.text((x, y+18), chr(g['codepoint']), fill='black')
            baseline = y+35+int(size)*scale
            for gy in range(g['height']):
                for gx in range(g['width']):
                    if g['pixels'][gy*g['width']+gx]:
                        xx=x+(g['left']+gx+1)*scale
                        yy=baseline+(g['top']+gy)*scale
                        draw.rectangle((xx, yy, xx+scale-1, yy+scale-1), fill='black')
        # Native-size group uses equal cell spacing to keep spacing out of this test.
        draw.text((6*cell-185, y), '1x:', fill='black')
        for col, g in enumerate(gs):
            for gy in range(g['height']):
                for gx in range(g['width']):
                    if g['pixels'][gy*g['width']+gx]:
                        draw.point((6*cell-155+col*24+g['left']+gx,
                                    y+int(size)+g['top']+gy), fill='black')
    image.save(output/'comparison.png')
    print(output/'comparison.png')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    compare(args.job.resolve(), args.output.resolve())
