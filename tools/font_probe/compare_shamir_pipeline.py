"""Controlled comparison of fixed Shamir prototype and source-aware pipeline.

Only the shared scan settings and evaluation repertoire change. Legacy outline
selection remains part of that pipeline; its internal trial renders use the same
dropout-off scan converter as the final outputs. Text uses common source GPOS
kerning plus each method's rendered advances, rounded at placement to pixels.
"""
from contextlib import contextmanager
import argparse
import html
import json
import math
import string
from pathlib import Path

import freetype as ft
import numpy as np
import uharfbuzz as hb
import fontTools
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image, ImageDraw, ImageOps

import paper_gridfit as old
from shamir_prototype import build_font
from stem_gridfit import stems
from source_constraints import source_shape, assess
from compare_paper_prototypes import ROOT, HERE, FLAGS, digest, raw_outline, render, pixels, draw_glyph, check_bounds

CHARS = string.ascii_uppercase + string.ascii_lowercase + string.digits + ' .,;:!?%°+-/()[]"\'='
SIZES = (14, 16, 18, 20)
GROUPS = {'curves': '6gbdpqhmn', 'edges': 'XKkEea', 'punctuation': '.,;:!?%°+-/()[]"\'='}
LINES = ['AVATAR To Wa: minimum 08:38', '21.5°C - 48% + 6 = 27.5 (12/24)',
         '"Read!" Why? [b, d; p: q]']
SOURCES = ('compare_shamir_pipeline.py', 'compare_paper_prototypes.py', 'shamir_prototype.py',
           'paper_gridfit.py', 'stem_gridfit.py', 'bowl_gridfit.py', 'curve_gridfit.py',
           'source_constraints.py', 'calibrate.py')


@contextmanager
def common_legacy_scan():
    """Normalize every legacy render, including its selection trials, then restore."""
    original = old.bitmap
    def normalized(face, char):
        outline = face.glyph.outline._FT_Outline
        outline.flags = (outline.flags & ~FLAGS) | ft.FT_OUTLINE_IGNORE_DROPOUTS
        return original(face, char)
    old.bitmap = normalized
    try:
        yield
    finally:
        old.bitmap = original


def instance(source, destination, axes):
    font = TTFont(source, recalcTimestamp=False)
    if 'fvar' in font:
        values = {a.axisTag: a.defaultValue for a in font['fvar'].axes}
        if set(axes) - set(values):
            raise ValueError('unknown variation axis')
        values.update(axes)
        instantiateVariableFont(font, values, inplace=True)
    elif axes:
        raise ValueError('axes supplied for static font')
    font.save(destination)


def focus_sheet(records, chars, title, path):
    index = {r['char']: r for r in records}
    variants = [('reference', 'Source outline', 1), ('ours', 'A: our pipeline', 5), ('shamir', 'B: Shamir', 5)]
    glyphs = [(index[c][key],scale) for c in chars for key,_,scale in variants]
    left_pad = max(12,4-min(g['left']*s for g,s in glyphs))
    right = max(80,4+max((g['left']+g['width'])*s for g,s in glyphs))
    cell = left_pad+right+8; left_margin = 122
    ascent = max(110,10+max(-g['top']*s for g,s in glyphs))
    descent = max(30,10+max((g['top']+g['height'])*s for g,s in glyphs))
    row_height=ascent+descent
    image = Image.new('RGB', (left_margin + cell*len(chars) + 12, 60+3*row_height), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((12, 10), title + ' / same scan settings / 5x pixels', fill='black')
    for col, char in enumerate(chars):
        draw.text((left_margin+col*cell+12, 32), char, fill='black')
    for row, (key, label, scale) in enumerate(variants):
        baseline = 60+row*row_height+ascent
        draw.text((12, baseline-102), label, fill='black')
        for col, char in enumerate(chars):
            glyph = index[char][key]; x = left_margin+col*cell+left_pad
            if key=='shamir' and 'unsupported' in index[char]['diagnostics']['shamir']['status']:
                draw.text((x,baseline-100),'Composite*',fill='#555555')
            check_bounds(glyph, x, baseline, scale,
                         (left_margin+col*cell,60+row*row_height,left_margin+(col+1)*cell,60+(row+1)*row_height))
            draw_glyph(draw, glyph, x, baseline, scale)
    # Height includes the deepest descender, rather than silently cropping it.
    image.save(path)


def text_positions(font_data, glyphs, text, size):
    face = hb.Face(font_data); font = hb.Font(face); font.scale = (size*64, size*64)
    hb.ot_font_set_funcs(font)
    buffer = hb.Buffer(); buffer.add_codepoints([ord(c) for c in text]); buffer.guess_segment_properties()
    hb.shape(font, buffer, {'kern': True, 'liga': False, 'clig': False, 'calt': False})
    if len(buffer.glyph_infos) != len(text):
        raise ValueError('text shaping substituted glyphs; review harness expects individual characters')
    pen = 0; placements = []
    for info, position in zip(buffer.glyph_infos, buffer.glyph_positions):
        char = text[info.cluster]
        if font.get_nominal_glyph(ord(char)) != info.codepoint:
            raise ValueError('unexpected glyph substitution')
        adjustment = position.x_advance - font.get_glyph_h_advance(info.codepoint)
        placements.append(dict(char=char, x=math.floor((pen+position.x_offset)/64+.5),
                               y=-math.floor(position.y_offset/64+.5), pen_26_6=pen,
                               kerning_26_6=adjustment))
        pen += glyphs[char]['advance_26_6'] + adjustment
    return dict(text=text, advance_26_6=pen, placements=placements)


def text_sheet(records, fonts, name, out):
    image = Image.new('RGB', (910, 40 + len(SIZES)*230), 'white'); draw = ImageDraw.Draw(image)
    draw.text((12, 10), name + ' / native pixels / source kerning + actual advances', fill='black')
    unsupported = ''.join(sorted({r['char'] for r in records if 'unsupported' in r['diagnostics']['shamir']['status']}))
    if unsupported:
        draw.text((12,25),'B composite glyphs (component hints may execute): '+unsupported,fill='#555555')
    evidence = []
    for row, size in enumerate(SIZES):
        subset = [r for r in records if r['size']==size]
        for method, key in enumerate(('ours', 'shamir')):
            y = 40+row*230+method*110
            draw.text((12, y), f'{size}px '+('A: our pipeline' if key=='ours' else 'B: Shamir'), fill='black')
            glyphs = {r['char']: r[key] for r in subset}
            for line, text in enumerate(LINES):
                run = text_positions(fonts[size], glyphs, text, size)
                baseline = y+38+line*30
                for p in run['placements']:
                    x = 154+p['x']; glyph = glyphs[p['char']]
                    check_bounds(glyph, x, baseline+p['y'], 1, (144,y+17,900,y+109))
                    draw_glyph(draw,glyph,x,baseline+p['y'],1)
                evidence.append(dict(font=name,size=size,method=key,**run))
    image.save(out/f'{name}-text.png')
    ImageOps.invert(image).save(out/f'{name}-text-inverse.png')
    return evidence


def gallery(out, names):
    # Raster images stay at intrinsic resolution; browsers may scroll horizontally.
    options = ''.join(f'<option>{html.escape(name)}</option>' for name in names)
    document = '''<!doctype html><meta charset="utf-8"><title>Shamir comparison</title>
<style>body{font:16px system-ui;margin:24px;background:#eee;color:#222}header{position:sticky;top:0;background:#eee;padding:12px 0}select{font:inherit;margin-right:16px}img{display:block;image-rendering:pixelated;max-width:none;background:white;margin:16px 0}p{max-width:900px}</style>
<header><b>A: our source-aware pipeline · B: Shamir</b><p>Same instantiated outlines, weight 400, matching optical size, MONO and dropout off. Algorithms fixed; expanded repertoire supplies shared measurements.</p>
<label>Font <select id="font">'''+options+'''</select></label><label>Size <select id="size"><option>14</option><option selected>16</option><option>18</option><option>20</option></select></label>
<label>Group <select id="group"><option value="curves">Bowls and shoulders</option><option value="edges">Diagonals and openings</option><option value="punctuation">Punctuation</option><option value="text">Native text, all sizes</option><option value="text-inverse">Inverse text, all sizes</option></select></label></header>
<p id="caption"></p><img id="sheet" alt="Labelled comparison"><p>Composite* identifies glyphs with no composite-level constraints; component hints may execute. Native text is shown at one image pixel per CSS pixel. Use browser zoom 100%. Structural diagnostics in report.json are review aids, not approval.</p>
<script>const f=document.querySelector('#font'),s=document.querySelector('#size'),g=document.querySelector('#group'),im=document.querySelector('#sheet');function show(){const text=g.value.startsWith('text');s.disabled=text;im.src=f.value+'-'+(text?'':s.value+'-')+g.value+'.png';document.querySelector('#caption').textContent=text?'Source kerning with each method’s actual advances; glyph substitution disabled.':'Rows: source outline, A: our pipeline, B: Shamir. Each column retains its baseline and bearing.';}[f,s,g].forEach(x=>x.addEventListener('change',show));show();</script>'''
    (out/'index.html').write_text(document)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=HERE/'out/shamir-controlled')
    args = parser.parse_args(); out = args.out.resolve(); out.relative_to(ROOT); out.mkdir(parents=True,exist_ok=True)
    hashes = {p:digest(HERE/p) for p in SOURCES}; records=[]; builds=[]; inputs={}; runs=[]
    names = ('roboto','literata','source-sans-3')
    for name in names:
        jobpath = ROOT/f'tools/font_generator/examples/{name}.json'; job=json.loads(jobpath.read_text())
        source=(jobpath.parent/job['font']).resolve()
        if digest(source)!=job['provenance']['expected_sha256']:raise ValueError('font checksum mismatch')
        inputs[name]=dict(font_sha256=digest(source),job_sha256=digest(jobpath)); texts={}
        for size in SIZES:
            axes=dict(job['settings']['axes']);axes['wght']=400
            if 'opsz' in axes:axes['opsz']=min(72,max(7,size))
            native=out/f'{name}-{size}-source.ttf'; hinted=out/f'{name}-{size}-shamir.ttf'
            instance(source,native,axes); build=build_font(native,hinted,size,{},CHARS)
            before=ft.Face(str(native)); after=ft.Face(str(hinted)); before.set_pixel_sizes(0,size)
            widths=[];vertical=[]; outlines={}
            for char in CHARS:
                a,tags,ends=raw_outline(before,char,size);b,bt,be=raw_outline(after,char,size)
                if not np.array_equal(a,b) or tags!=bt or ends!=be:raise ValueError('source outlines differ')
                outlines[char]=(a,tags,ends)
                widths.extend(p['width'] for p in old.pairs(a,tags,ends,size))
                vertical.extend(p['width'] for p in stems(a,tags,ends,size))
            table=old.width_table(widths); stem_table=old.width_table(vertical)
            builds.append(dict(font=name,size=size,axes=axes,source_sha256=digest(native),
                               hinted_sha256=digest(hinted),shamir=build,diagonal_table=table,stem_table=stem_table))
            with common_legacy_scan():
                for char in CHARS:
                    points,tags,ends=outlines[char]
                    baseline,diag=old.generate(before,char,size,table,stem_table,bowls=True,source_aware=True)
                    candidate=render(after,char,size,hinted=True)
                    reference=render(after,char,size*5)
                    shape=source_shape(points,tags,ends,size)
                    records.append(dict(font=name,size=size,char=char,axes=axes,ours=baseline,shamir=candidate,
                        reference=reference,diagnostics=dict(ours=diag,shamir=build['records'][char]),
                        different_pixels=len(pixels(baseline)^pixels(candidate)),
                        structure={k:assess(shape,g) for k,g in [('ours',baseline),('shamir',candidate)]}))
            subset=[r for r in records if r['font']==name and r['size']==size]
            for group,chars in GROUPS.items():focus_sheet(subset,chars,f'{name} {size}px',out/f'{name}-{size}-{group}.png')
            texts[size]=native.read_bytes()
            print(json.dumps(dict(font=name,size=size,cases=len(subset))),flush=True)
        runs.extend(text_sheet([r for r in records if r['font']==name],texts,name,out))
    gallery(out,names)
    if hashes!={p:digest(HERE/p) for p in SOURCES}:raise RuntimeError('source changed during comparison')
    summary=dict(cases=len(records),different=sum(bool(r['different_pixels']) for r in records),
                 flags={k:sum(bool(r['structure'][k]['defect_count']) for r in records) for k in ('ours','shamir')},
                 unsupported_shamir=[dict(font=r['font'],size=r['size'],char=r['char'],status=r['diagnostics']['shamir']['status'])
                    for r in records if 'unsupported' in r['diagnostics']['shamir']['status']])
    report=dict(scope='Fixed algorithms, expanded evaluation repertoire; image approval pending',
                scan='FreeType MONO with all dropout controls disabled for final and internal trial renders',
                source_hashes=hashes,inputs=inputs,characters=CHARS,sizes=SIZES,builds=builds,
                versions=dict(freetype=ft.version(),harfbuzz=hb.version_string(),numpy=np.__version__,fonttools=fontTools.__version__),
                records=records,text_runs=runs,summary=summary)
    (out/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({**summary,'unsupported_shamir':len(summary['unsupported_shamir'])}),flush=True)


if __name__=='__main__':main()
