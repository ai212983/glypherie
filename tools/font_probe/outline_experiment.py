"""Bounded shared-setting experiment: horizontal outline growth and grid phase.

Uses FreeType mono as a fixed backend, not as a quality oracle. All glyphs receive
the same transform. The diagnostic bands are specific to Roboto 16px, not a general
stroke classifier or an automatic production setting selector.
"""
import ctypes
import hashlib
import itertools
import json
from pathlib import Path

import freetype as ft
from PIL import Image, ImageDraw

from calibrate import topology

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'tools/font_probe/out/outline-experiment'
CHARS = 'bhmnpdq'


def render(face, char, growth, phase):
    face.load_char(char, ft.FT_LOAD_TARGET_MONO | ft.FT_LOAD_NO_BITMAP)
    outline = face.glyph.outline._FT_Outline
    error = ft.FT_Outline_EmboldenXY(ctypes.byref(outline), growth, 0)
    if error:
        raise ft.FT_Exception(error)
    # Recenter horizontal growth, then shift relative to the pixel grid.
    ft.FT_Outline_Translate(ctypes.byref(outline), phase-growth//2, 0)
    face.glyph.render(ft.FT_RENDER_MODE_MONO)
    slot = face.glyph
    b = slot.bitmap
    if b.pitch < 0 or b.pixel_mode != ft.FT_PIXEL_MODE_MONO:
        raise ValueError('expected positive-pitch mono bitmap')
    buf = b.buffer
    return dict(codepoint=ord(char), left=slot.bitmap_left, top=-slot.bitmap_top,
                width=b.width, height=b.rows, advance_26_6=slot.advance.x,
                pixels=[(buf[y*b.pitch+x//8] >> (7-x%8)) & 1
                        for y in range(b.rows) for x in range(b.width)])


def runs(glyph, y):
    row = y-glyph['top']
    width = glyph['width']
    pixels = glyph['pixels'][row*width:(row+1)*width]
    return [len(list(values)) for ink, values in itertools.groupby(pixels) if ink]


def diagnose(glyphs):
    profiles = {}
    topology_ok = True
    penalty = 0
    for char, glyph in zip(CHARS, glyphs):
        ink, holes = topology(glyph, 1)
        expected_holes = 1 if char in 'bpdq' else 0
        topology_ok &= ink == 1 and holes == expected_holes
        # Whole lower straight section for m/n/h; central bowl sides for b/p/d/q.
        band = range(-6, -1) if char in 'hmn' else range(-6, -3)
        widths = [runs(glyph, y) for y in band]
        expected_runs = 3 if char == 'm' else 2
        penalty += sum(abs(len(row)-expected_runs)*10 + sum(abs(w-2) for w in row)
                       for row in widths)
        profiles[char] = dict(ink_components=ink, counters=holes,
                              sampled_y=list(band), run_widths=widths)
    return dict(topology_ok=bool(topology_ok), two_pixel_band_penalty=penalty,
                profiles=profiles)


def sheet(cases, path):
    scale, cell, row_height = 7, 120, 165
    image = Image.new('RGB', (7*cell+24, len(cases)*row_height+35), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((12, 8), 'Roboto 16px / wght 400 / wdth 100 | enlarged 7x; native pixels at right', fill='black')
    for row, case in enumerate(cases):
        y = 32+row*row_height
        label = f"{case['id']} | band penalty {case['diagnostics']['two_pixel_band_penalty']}"
        draw.text((12, y), label, fill='black')
        for col, glyph in enumerate(case['glyphs']):
            x = 12+col*cell
            draw.text((x, y+18), chr(glyph['codepoint']), fill='black')
            for gy in range(glyph['height']):
                for gx in range(glyph['width']):
                    if glyph['pixels'][gy*glyph['width']+gx]:
                        xx=x+(glyph['left']+gx+2)*scale
                        yy=y+125+(glyph['top']+gy)*scale
                        draw.rectangle((xx, yy, xx+scale-1, yy+scale-1), fill='black')
                        draw.point((650+col*25+glyph['left']+gx,
                                    y+12+glyph['top']+gy), fill='black')
    image.save(path)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    job = json.loads((ROOT/'tools/font_generator/examples/roboto.json').read_text())
    font = ROOT/'tools/font_probe/fonts/Roboto.ttf'
    digest = hashlib.sha256(font.read_bytes()).hexdigest()
    if digest != job['provenance']['expected_sha256']:
        raise ValueError('font checksum mismatch')
    face = ft.Face(str(font))
    face.set_var_design_coords([400, 100])
    face.set_pixel_sizes(0, 16)
    cases = []
    for growth in (0, 8, 16, 24, 32):
        for phase in (-24, -16, -8, 0, 8, 16, 24):
            glyphs = [render(face, char, growth, phase) for char in CHARS]
            case = dict(id=f'growth {growth}/64px; shift {phase}/64px',
                        growth_26_6=growth, shift_26_6=phase,
                        glyphs=glyphs, diagnostics=diagnose(glyphs))
            cases.append(case)
    baseline = next(c for c in cases if c['growth_26_6'] == c['shift_26_6'] == 0)
    def ink_set(g):
        return {(g['left']+x, g['top']+y) for y in range(g['height'])
                for x in range(g['width']) if g['pixels'][y*g['width']+x]}
    for case in cases:
        case['changed_pixels'] = sum(len(ink_set(a)^ink_set(b))
                                     for a,b in zip(case['glyphs'], baseline['glyphs']))
    valid = [c for c in cases if c['diagnostics']['topology_ok']]
    rank = lambda c: (c['diagnostics']['two_pixel_band_penalty'], c['changed_pixels'],
                      c['growth_26_6'], abs(c['shift_26_6']))
    ranked = sorted(valid, key=rank)
    alignment = min((c for c in valid if c['growth_26_6']==0), key=rank)
    growth_only = min((c for c in valid if c['shift_26_6']==0), key=rank)
    selected = list({c['id']: c for c in [baseline, alignment, growth_only, ranked[0]]}.values())
    evidence = dict(font_sha256=digest, freetype_version=ft.version(),
                    experiment_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    size_px=16, axes={'wght':400,'wdth':100},
                    order='mono hinting, horizontal outline growth, recenter and shift, mono scan conversion',
                    limits='Roboto-specific two-pixel band diagnostic; no perceptual or source-outline fidelity score; advances unchanged',
                    selected=[c['id'] for c in selected], cases=cases)
    (OUTPUT/'results.json').write_text(json.dumps(evidence, indent=2)+'\n')
    sheet(selected, OUTPUT/'comparison.png')
    print(json.dumps(dict(cases=len(cases), topology_passes=len(valid),
                         selected=[dict(id=c['id'], penalty=c['diagnostics']['two_pixel_band_penalty'],
                                        changed_pixels=c['changed_pixels']) for c in selected]), indent=2))


if __name__ == '__main__':
    main()
