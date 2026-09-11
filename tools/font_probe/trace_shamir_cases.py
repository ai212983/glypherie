"""Isolate Shamir x/y hint effects using the saved controlled comparison.

The same font, CVT, repertoire and scan converter are used for every ablation.
This is a causal diagnostic, not a set of replacement rendering candidates.
"""
import argparse
import json
from pathlib import Path

import freetype as ft
import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw

from compare_paper_prototypes import HERE, ROOT, digest, render, pixels, draw_glyph, check_bounds, raw_outline
from shamir_prototype import build_font

GROUPS = {'letters': 'eX', 'punctuation': '.,:;!?', 'related': 'acsvxKWY'}
VARIANTS = [('reference', 'Source shape', 1), ('shamir', 'A: Shamir', 6),
            ('opposed', 'B: opposed sides', 6)]


def axis_program(assembly, keep):
    """Keep setup and the complete block for one coordinate axis."""
    result = []; active = True
    for instruction in assembly:
        if instruction.startswith('SVTCA['):
            active = instruction.startswith(f'SVTCA[{1-keep}]')
        if active:
            result.append(instruction)
    return result


def axis_font(source, target, axis):
    font = TTFont(source, recalcTimestamp=False)
    for glyph in font['glyf'].glyphs.values():
        glyph.expand(font['glyf'])
        if hasattr(glyph, 'program'):
            glyph.program.fromAssembly(axis_program(glyph.program.getAssembly(), axis))
    font.save(target)


def hinted_points(face, char, size):
    face.set_pixel_sizes(0, size)
    face.load_char(char, ft.FT_LOAD_NO_BITMAP | ft.FT_LOAD_TARGET_MONO |
                   ft.FT_LOAD_PEDANTIC | ft.FT_LOAD_NO_AUTOHINT)
    return np.asarray(face.glyph.outline.points, dtype=float).reshape(-1, 2) / 64


def sheet(records, chars, title, path):
    index = {r['char']: r for r in records}
    glyphs = [(index[c][key], scale) for c in chars for key, _, scale in VARIANTS]
    padding = max(12, 8-min(g['left']*s for g, s in glyphs))
    cell = padding + max(96, 8+max((g['left']+g['width'])*s for g, s in glyphs)) + 60
    ascent = max(115, 12+max(-g['top']*s for g, s in glyphs))
    descent = max(45, 30+max((g['top']+g['height'])*s for g, s in glyphs))
    height = ascent+descent; margin = 120
    image = Image.new('RGB', (margin+cell*len(chars)+12, 55+height*len(VARIANTS)), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((12, 8), title+' / 6x and native pixels / same dropout-off scan', fill='black')
    for col, c in enumerate(chars):
        draw.text((margin+col*cell+padding, 30), c, fill='black')
    for row, (key, label, scale) in enumerate(VARIANTS):
        top = 55+row*height; baseline = top+ascent
        draw.text((12, top+14), label, fill='black')
        for col, c in enumerate(chars):
            x = margin+col*cell+padding; glyph = index[c][key]
            if key != 'reference' and index[c]['unsupported']:
                draw.text((x, top+12), 'Composite*', fill='#555555')
            check_bounds(glyph, x, baseline, scale, (margin+col*cell, top, margin+(col+1)*cell, top+height))
            draw_glyph(draw, glyph, x, baseline, scale)
            if key != 'reference':
                check_bounds(glyph, x+cell-60, baseline, 1,
                             (margin+col*cell, top, margin+(col+1)*cell, top+height))
                draw_glyph(draw, glyph, x+cell-60, baseline, 1)
    image.save(path)


def gallery(out):
    (out/'index.html').write_text('''<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Shamir focused comparison</title>
<style>body{font:16px system-ui;margin:20px;background:#eee}header{position:sticky;top:0;background:#eee;padding:12px 0}select{font:inherit;margin:8px}img{display:block;max-width:none;image-rendering:pixelated}p{max-width:850px}pre{white-space:pre-wrap}</style>
<header><b>Shamir: e, X and punctuation across all fonts</b><p>Rows show the source shape, A: current Shamir, and B: the proposed opposed-side rule. B requires stroke edges to face opposite directions. Each glyph also appears at native size beside its enlargement.</p>
<label>Font<select id="font"><option>roboto</option><option>literata</option><option>source-sans-3</option></select></label>
<label>Size<select id="size"><option>14</option><option>16</option><option>18</option><option>20</option></select></label>
<label>Group<select id="group"><option value="letters">e and X</option><option value="punctuation">Small punctuation</option><option value="related">Related glyphs</option></select></label></header>
<p>Composite* means component hints may execute, while composite-level constraints are absent.</p>
<img id="sheet" alt="Source shape, current Shamir and proposed improvement"><details><summary>Feature and constraint trace</summary><pre id="trace"></pre></details>
<script>const f=document.querySelector('#font'),s=document.querySelector('#size'),g=document.querySelector('#group');let report;
function show(){document.querySelector('#sheet').src=f.value+'-'+s.value+'-'+g.value+'.png';if(report){const chars=report.groups[g.value];document.querySelector('#trace').textContent=JSON.stringify(report.records.filter(r=>r.font===f.value&&r.size===+s.value&&chars.includes(r.char)).map(r=>({char:r.char,status:r.status,features:r.features,constraints:r.constraints,candidate:r.candidate_diagnostics,changed_pixels:r.changed_pixels.opposed})),null,2)}}
[f,s,g].forEach(x=>x.addEventListener('change',show));show();fetch('report.json').then(r=>r.json()).then(r=>{report=r;show()});</script>''')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=HERE/'out/shamir-controlled')
    parser.add_argument('--out', type=Path, default=HERE/'out/shamir-controlled/focused')
    args = parser.parse_args(); out = args.out.resolve(); out.relative_to(ROOT)
    out.mkdir(parents=True, exist_ok=True)
    report_path = args.baseline/'report.json'; original = json.loads(report_path.read_text())
    records = []; summary = []; builds = []; corpus_changes = []; reviewed = set(''.join(GROUPS.values()))
    saved = {(r['font'], r['size'], r['char']): r for r in original['records']}
    for build in original['builds']:
        name, size = build['font'], build['size']
        native = args.baseline/f'{name}-{size}-source.ttf'
        hinted = args.baseline/f'{name}-{size}-shamir.ttf'
        if digest(native) != build['source_sha256'] or digest(hinted) != build['hinted_sha256']:
            raise ValueError('baseline font hash mismatch')
        default_check=out/f'{name}-{size}-default-check.ttf'
        build_font(native,default_check,size,{},original['characters'])
        if digest(default_check)!=digest(hinted):
            raise ValueError('default prototype changed the saved baseline font')
        paths = {'opposed': out/f'{name}-{size}-opposed.ttf'}
        candidate = build_font(native,paths['opposed'],size,{},original['characters'],opposed_sides=True)
        builds.append(dict(font=name,size=size,report=candidate,font_sha256=digest(paths['opposed'])))
        for axis, key in enumerate(('x_only', 'y_only')):
            paths[key] = out/f'{name}-{size}-{key}.ttf'
            axis_font(hinted, paths[key], axis)
        faces = {key: ft.Face(str(path)) for key, path in paths.items()}
        faces['shamir'] = ft.Face(str(hinted)); faces['unhinted'] = ft.Face(str(native))
        changed = {key: 0 for key in ('opposed', 'x_only', 'y_only', 'unhinted')}
        for char in original['characters']:
            glyphs = {key: render(face, char, size, hinted=key!='unhinted') for key, face in faces.items()}
            if glyphs['shamir'] != saved[name, size, char]['shamir']:
                raise ValueError('current rendering differs from saved baseline')
            changes = {key: len(pixels(glyphs[key]) ^ pixels(glyphs['shamir'])) for key in changed}
            if changes['opposed']:
                corpus_changes.append(dict(font=name,size=size,char=char,changed_pixels=changes['opposed']))
            for key, value in changes.items(): changed[key] += bool(value)
            if char not in reviewed: continue
            source, _, _ = raw_outline(faces['unhinted'], char, size)
            points = hinted_points(faces['shamir'], char, size)
            diagnostic = dict(build['shamir']['records'][char])
            if 'unsupported' in diagnostic['status']:
                diagnostic['status']='unsupported composite-level constraints; component hints may execute'
            constraints = []
            for axis in diagnostic.get('axes', []):
                for constraint in axis['constraints']:
                    ids = list(dict.fromkeys([constraint['point']] + ([constraint['source']] if 'source' in constraint else [])))
                    constraints.append(dict(axis=axis['axis'], **constraint,
                        positions=[dict(point=i,source=source[i].tolist(),hinted=points[i].tolist()) for i in ids]))
            records.append(dict(font=name,size=size,char=char,**glyphs,
                reference=render(faces['unhinted'],char,size*6),status=diagnostic['status'],
                unsupported='unsupported' in diagnostic['status'],features=diagnostic['features'],
                candidate_diagnostics=candidate['records'][char],
                constraints=constraints,rejected=[a['rejected'] for a in diagnostic.get('axes',[])],
                source_points=source.tolist(),hinted_points=points.tolist(),changed_pixels=changes))
        subset = [r for r in records if r['font']==name and r['size']==size]
        for group, chars in GROUPS.items(): sheet(subset,chars,f'{name} {size}px',out/f'{name}-{size}-{group}.png')
        summary.append(dict(font=name,size=size,cases=len(original['characters']),different_from_shamir=changed))
    report = dict(scope='Coordinate-hint ablation; current Shamir preserved; human review pending',
        baseline_report_sha256=digest(report_path),script_sha256=digest(Path(__file__)),
        candidate_source_sha256=digest(HERE/'shamir_prototype.py'),
        freetype_version=ft.version(),groups=GROUPS,summary=summary,builds=builds,
        corpus_changes=corpus_changes,records=records)
    (out/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');gallery(out)
    print(json.dumps(dict(corpus_cases=sum(r['cases'] for r in summary),focused_cases=len(records),summary=summary)))


if __name__ == '__main__': main()
