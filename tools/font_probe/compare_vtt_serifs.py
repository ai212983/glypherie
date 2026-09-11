"""Render geometry-driven serif relationships against frozen reorientation v2."""
import json
import shutil
from pathlib import Path
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.ttProgram import Program
from check_shamir_baseline import digest, coordinate_check
from compare_paper_prototypes import render
from compare_shamir_representatives import comparison
from shamir_constraints import relation
from shamir_baseline_solver import compile_baseline
from vtt_serif_experiment import detect, fit
from serif_reference_view import reference_comparison

HERE = Path(__file__).resolve().parent


def run():
    reference = HERE/'out/shamir-reorientation-v2'; output = HERE/'out/vtt-serif-v1'
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()): raise ValueError('output must be empty')
    (output/'sources').mkdir()
    hashes = {p.name: digest(p) for p in HERE.glob('*.py')}
    for name in hashes: shutil.copy2(HERE/name, output/'sources'/name)
    old = json.loads((reference/'report.json').read_text()); cases = []; figures = []; inputs = {}
    for size in (14, 16, 18, 20):
        key = f'literata-{size}'; path = reference/f'{key}-reoriented.ttf'
        inputs[path.name] = digest(path); shutil.copy2(path, output/path.name)
        font = TTFont(path); cmap = font.getBestCmap(); built = []
        for char in 'HFA':
            source, ends, flags = font['glyf'][cmap[ord(char)]].getCoordinates(font['glyf'])
            original = next(c for c in old['cases'] if c['key']==key and c['char']==char)
            before = np.asarray(original['result']['graph']['baseline_execution']['model_points_px'])
            halves = detect(source, ends, flags, font['head'].unitsPerEm)
            if not halves: raise ValueError(f'{key} {char}: no paired serif roles')
            fitted, audit = fit(source, before, halves, size/font['head'].unitsPerEm)
            owned = {i for h in halves for i in h['members']}
            assert all(np.array_equal(fitted[i], before[i]) for i in range(len(source)) if i not in owned)
            assert all(fitted[h['stem'], 0] == before[h['stem'], 0] for h in halves)
            # Explicit coordinate export after the recipe, not a claim that the
            # overwritten old serif equations continue to hold.
            cs = [dict(relation('Abs', i, np.eye(2)[axis], value=float(p[axis])*font['head'].unitsPerEm/size,
                                round=False), id=2*i+axis, depends_on=[])
                  for i, p in enumerate(fitted) for axis in (0, 1)]
            graph = dict(order=list(range(len(source))), constraints=cs, scheduler='point',
                         scalar_order=list(range(len(cs))), rejected=[], warnings=[])
            assembly, graph['baseline_execution'] = compile_baseline(graph, source, size, font['head'].unitsPerEm)
            g = font['glyf'][cmap[ord(char)]]; g.program = Program(); g.program.fromAssembly(assembly)
            built.append((char, graph, audit))
        target = output/f'{key}-serif.ttf'
        font['maxp'].maxSizeOfInstructions = max(len(g.program.getBytecode()) if hasattr(g, 'program') else 0
                                                for g in (font['glyf'][n] for n in font.getGlyphOrder()))
        font.save(target); font.close()
        faces = [ft.Face(str(p)) for p in (path, target)]
        for char, graph, audit in built:
            native = coordinate_check(faces[1], char, size, graph)
            assert native['passed']
            name = f'{key}-u{ord(char):04x}.png'
            glyphs = [render(faces[0], char, size), render(faces[0], char, size, hinted=True),
                      render(faces[1], char, size, hinted=True)]
            reference_comparison(faces, char, size, f'{key} {char!r}').save(output/name)
            cases.append(dict(key=key, char=char, halves=audit, graph=graph, native=native))
            figures.append(f'<figure><img src="{name}" alt="{key} {char}"></figure>')
    assert hashes == {name: digest(HERE/name) for name in hashes}
    assert inputs == {name: digest(reference/name) for name in inputs}
    (output/'report.json').write_text(json.dumps(dict(sources=hashes, inputs=inputs, cases=cases,
        scope='VTT-backed type 2/3 relationships; geometric role detector, local dimensions and bracket interpolation are project assumptions. Not a VTT compiler port. Prior serif/default constraints are replaced within detected spans.'), indent=2)+'\n')
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Serif experiment</title>'
        '<style>img{max-width:100%;image-rendering:pixelated}figure{margin:16px 0}</style><h1>VTT-backed serif experiment</h1>'
        '<p>Columns: smooth source outline at 8x display scale, unhinted pixel input, reorientation v2, new serif experiment. Type 2/3 relationships with local measurements; '
        'geometric detection and bracket interpolation are project assumptions. Visual review pending.</p>'+''.join(figures))
    print('12 native cases verified; output', output.name)


if __name__ == '__main__': run()
