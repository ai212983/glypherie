"""Test preserving narrow exterior notches during shared outline thickening.

Experimental bitmap constraint, using baseline geometry rather than character IDs.
The baseline may itself lose source detail; this is not a general outline-feature
detector. Kept outside the production generator until broader validation.
"""
import hashlib
import json
from pathlib import Path

import freetype as ft
from PIL import Image, ImageDraw

from outline_experiment import ROOT, CHARS, render, diagnose

OUTPUT = ROOT/'tools/font_probe/out/join-experiment'


def ink(g):
    return {(g['left']+x, g['top']+y) for y in range(g['height'])
            for x in range(g['width']) if g['pixels'][y*g['width']+x]}


def notches(g, max_width):
    """Narrow horizontal white runs between ink, connected to exterior in 4-neighbors."""
    black = ink(g)
    x0, y0 = g['left']-1, g['top']-1
    x1, y1 = x0+g['width']+1, y0+g['height']+1
    outside = {(x0, y0)}
    pending = list(outside)
    while pending:
        x, y = pending.pop()
        for p in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if x0 <= p[0] <= x1 and y0 <= p[1] <= y1 and p not in black|outside:
                outside.add(p)
                pending.append(p)
    protected = set()
    for y in range(y0+1, y1):
        x = x0+1
        while x < x1:
            if (x,y) in black:
                x += 1
                continue
            start = x
            while x < x1 and (x,y) not in black:
                x += 1
            run = {(xx,y) for xx in range(start,x)}
            if x-start <= max_width and (start-1,y) in black and (x,y) in black and run <= outside:
                protected |= run
    return protected


def constrain(base, grown, width):
    protected = notches(base, width)
    result = dict(grown, pixels=list(grown['pixels']))
    removed = []
    for i, value in enumerate(result['pixels']):
        p = (result['left']+i%result['width'], result['top']+i//result['width'])
        if value and p in protected:
            result['pixels'][i] = 0
            removed.append(p)
    return result, dict(protected=sorted(protected), removed=sorted(removed))


def make_sheet(rows, source):
    scale, cell, height = 7, 120, 170
    image = Image.new('RGB', (864, len(rows)*height+height+32), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((12,8), 'Roboto 16px / wght 400 / wdth 100 | 7x exact pixels; native group at right', fill='black')
    for row, (label, glyphs) in enumerate(rows):
        y = 32+row*height
        draw.text((12,y), label, fill='black')
        for col,g in enumerate(glyphs):
            x = 12+col*cell
            draw.text((x,y+20), chr(g['codepoint']), fill='black')
            for px,py in ink(g):
                xx,yy = x+(px+2)*scale,y+128+py*scale
                draw.rectangle((xx,yy,xx+scale-1,yy+scale-1), fill='black')
                draw.point((650+col*25+px,y+12+py),fill='black')
    y = 32+len(rows)*height
    draw.text((12,y), 'Source outline at 7x size, unhinted (shape reference)', fill='black')
    for col,g in enumerate(source):
        x = 12+col*cell
        draw.text((x,y+20),chr(g['codepoint']),fill='black')
        for gy in range(g['height']):
            for gx in range(g['width']):
                value = g['pixels'][gy*g['width']+gx]
                if value:
                    draw.point((x+14+g['left']+gx,y+128+g['top']+gy), fill=(255-value,)*3)
    image.save(OUTPUT/'comparison.png')


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    font = ROOT/'tools/font_probe/fonts/Roboto.ttf'
    job = json.loads((ROOT/'tools/font_generator/examples/roboto.json').read_text())
    digest = hashlib.sha256(font.read_bytes()).hexdigest()
    assert digest == job['provenance']['expected_sha256'], 'font checksum mismatch'
    face = ft.Face(str(font))
    face.set_var_design_coords([400,100])
    face.set_pixel_sizes(0,16)
    base = [render(face,c,0,0) for c in CHARS]
    grown = [render(face,c,24,8) for c in CHARS]
    candidates = []
    for width in (1,2):
        pairs = [constrain(a,b,width) for a,b in zip(base,grown)]
        glyphs = [p[0] for p in pairs]
        candidates.append(dict(max_notch_width=width, glyphs=glyphs,
                               changes={c:p[1] for c,p in zip(CHARS,pairs)},
                               diagnostics=diagnose(glyphs)))
    source = []
    face.set_pixel_sizes(0,112)
    for c in CHARS:
        face.load_char(c,ft.FT_LOAD_NO_HINTING|ft.FT_LOAD_NO_BITMAP|ft.FT_LOAD_RENDER)
        s=face.glyph; b=s.bitmap
        buffer = b.buffer
        source.append(dict(codepoint=ord(c),left=s.bitmap_left,top=-s.bitmap_top,
                           width=b.width,height=b.rows,
                           pixels=[buffer[y*b.pitch+x] for y in range(b.rows) for x in range(b.width)]))
    evidence = dict(font_sha256=digest, freetype_version=ft.version(),
                    script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    dependency_sha256=hashlib.sha256((ROOT/'tools/font_probe/outline_experiment.py').read_bytes()).hexdigest(),
                    size_px=16,axes={'wght':400,'wdth':100},growth_26_6=24,shift_26_6=8,
                    baseline=base,grown=grown,candidates=candidates,source_outline_112px=source,
                    limits='Baseline-derived bitmap notches; no glyph-specific rules; no inference of source outline features; spacing unvalidated')
    (OUTPUT/'results.json').write_text(json.dumps(evidence,indent=2)+'\n')
    make_sheet([('A: baseline',base),('B: previous shared thickening',grown),
                ('C: same thickening, preserve 1px exterior notches',candidates[0]['glyphs'])],source)
    for c in candidates:
        print(json.dumps(dict(width=c['max_notch_width'], diagnostics=c['diagnostics'], changes=c['changes'])))


if __name__ == '__main__':
    main()
