"""Frozen rounded/unrounded parent placement with the existing serif recipe."""
import json
import shutil
from pathlib import Path
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.ttProgram import Program
from check_shamir_baseline import digest, coordinate_check, graph_issues
from compare_paper_prototypes import render, pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from shamir_constraints import relation
from shamir_baseline_solver import compile_baseline
from shamir_parent_anchor import experiment
from vtt_serif_experiment import detect, fit

HERE = Path(__file__).resolve().parent


def run():
    reference = HERE/'out/shamir-reorientation-v2'; serif = HERE/'out/vtt-serif-v1'
    output = HERE/'out/parent-anchor-v1'; output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()): raise ValueError('output must be empty')
    (output/'sources').mkdir(); hashes = {p.name:digest(p) for p in HERE.glob('*.py')}
    for name in hashes: shutil.copy2(HERE/name, output/'sources'/name)
    records = json.loads((reference/'report.json').read_text())['cases']
    inputs = {}; cases = []; figures = []
    for key in sorted({c['key'] for c in records}):
        size = int(key.rsplit('-',1)[1]); has_serifs = key.startswith('literata-')
        path = (serif/f'{key}-serif.ttf') if has_serifs else reference/f'{key}-reoriented.ttf'
        inputs[path.name] = digest(path); shutil.copy2(path, output/path.name)
        by_char = {c['char']:c for c in records if c['key']==key}; built = {ch:[] for ch in by_char}
        for rounded in (True,False):
            font = TTFont(path); cmap = font.getBestCmap(); em = font['head'].unitsPerEm
            for char, previous in by_char.items():
                g=font['glyf'][cmap[ord(char)]]; points, ends, flags = g.getCoordinates(font['glyf'])
                result = experiment(previous['result'], points, size, em, rounded)
                assert not graph_issues(result['graph'])
                fitted = np.asarray(result['graph']['baseline_execution']['model_points_px'])
                # Repeat the frozen serif policy after changing parent placement.
                audit=[]
                if has_serifs:
                    fitted, audit = fit(points, fitted, detect(points,ends,flags,em), size/em)
                cs=[dict(relation('Abs',i,np.eye(2)[axis],value=float(p[axis])*em/size,round=False),
                         id=2*i+axis,depends_on=[]) for i,p in enumerate(fitted) for axis in (0,1)]
                graph=dict(order=list(range(len(points))),constraints=cs,scheduler='point')
                assembly, graph['baseline_execution']=compile_baseline(graph,points,size,em)
                g.program=Program();g.program.fromAssembly(assembly)
                result.update(export_graph=graph,serif_audit=audit)
                built[char].append(result)
            name=f'{key}-{"rounded" if rounded else "unrounded"}.ttf'
            font['maxp'].maxSizeOfInstructions=max(len(g.program.getBytecode()) if hasattr(g,'program') else 0
                for g in (font['glyf'][n] for n in font.getGlyphOrder()))
            font.save(output/name);font.close()
        faces=[ft.Face(str(p)) for p in (path,output/f'{key}-rounded.ttf',output/f'{key}-unrounded.ttf')]
        for char,variants in built.items():
            glyphs=[render(f,char,size,hinted=True) for f in faces]
            checks=[]
            for i,result in enumerate(variants,1):
                check=coordinate_check(faces[i],char,size,result['export_graph']);assert check['passed']
                same=pixels(glyphs[0])==pixels(glyphs[i]);checks.append(dict(native=check,same_bitmap=same))
                if not result['changes']: assert same, f'unchanged construction altered {key} {char}'
            name=f'{key}-u{ord(char):04x}.png'
            panel=comparison(glyphs,['Current reference','Rounded complementary axis','Unrounded complementary axis'],f'{key} {char!r}')
            prepend_reference(faces[0],char,size,f'{key} {char!r}',glyphs,panel).save(output/name)
            cases.append(dict(key=key,char=char,variants=variants,checks=checks))
            figures.append(f'<figure id="{key}-u{ord(char):04x}"><img src="{name}" alt="{key} {char}"></figure>')
    assert hashes=={name:digest(HERE/name) for name in hashes}
    (output/'report.json').write_text(json.dumps(dict(sources=hashes,inputs=inputs,cases=cases,
        policy='Microsoft-inspired parent-first experiment; not a VTT port. Local oblique Abs sharing a nearer cardinal anchor becomes rounded/unrounded complementary placement. Relative relations retained. Existing serif recipe applied afterward.'),indent=2)+'\n')
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Parent placement experiment</title>'
        '<style>img{max-width:100%;image-rendering:pixelated}figure{margin:16px 0}</style><h1>Parent placement experiment</h1>'
        '<p>Smooth source, current reference, rounded complementary axis, unrounded complementary axis. '
        'Microsoft-inspired construction, not an exact VTT port. Existing serif recipe retained. Both candidates await review.</p>'+''.join(figures))
    print('cases',len(cases),'changed constructions',sum(bool(c['variants'][0]['changes']) for c in cases))


if __name__ == '__main__': run()
