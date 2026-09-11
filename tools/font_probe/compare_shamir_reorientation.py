"""Freeze and render a bounded reorientation comparison from saved models."""
import argparse
import html
import json
import shutil
from pathlib import Path

import freetype as ft
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.ttProgram import Program
from check_shamir_baseline import coordinate_check, digest, graph_issues
from compare_paper_prototypes import render, pixels
from compare_shamir_representatives import comparison
from shamir_baseline_solver import compile_baseline
from shamir_reorientation import Unsupported, prototype

HERE = Path(__file__).resolve().parent


def run(reference, output, chars, previous=None):
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('output must be empty')
    (output/'sources').mkdir()
    sources = {p.name: digest(p) for p in HERE.glob('*.py')}
    for name in sources:
        shutil.copy2(HERE/name, output/'sources'/name)
    cases = []; figures = []; inputs = {}; regressions = []
    previous_cases = {}
    if previous:
        previous_cases = {(c['key'], c['char']): c for c in json.loads((previous/'report.json').read_text())['cases']
                          if c['status']=='verified'}
    for model_path in sorted(reference.glob('*-model.json')):
        key = model_path.name.removesuffix('-model.json')
        model = json.loads(model_path.read_text())
        for name in (model_path.name, f'{key}-reference.ttf', f'{key}-experiment.ttf', f'{key}-source.ttf'):
            inputs[name] = digest(reference/name)
            shutil.copy2(reference/name, output/name)
        # Keep the normalized outline and native adapter of the frozen experiment.
        font = TTFont(output/f'{key}-experiment.ttf'); cmap = font.getBestCmap()
        supported = []
        for char in dict.fromkeys(chars):
            try:
                result = prototype(model['records'][char])
            except Unsupported as exc:
                cases.append(dict(key=key, char=char, status='unsupported', reason=str(exc)))
                figures.append(f'<p>{key} {html.escape(char)}: unsupported — {html.escape(str(exc))}</p>')
                continue
            g = font['glyf'][cmap[ord(char)]]
            coordinates, _, _ = g.getCoordinates(font['glyf'])
            execution = result['graph']['baseline_execution']
            assembly, _ = compile_baseline(result['graph'], coordinates, execution['ppem'], execution['em'])
            g.program = Program(); g.program.fromAssembly(assembly)
            supported.append((char, result))
        target = output/f'{key}-reoriented.ttf'
        font['maxp'].maxSizeOfInstructions = max(
            len(g.program.getBytecode()) if hasattr(g, 'program') else 0
            for g in (font['glyf'][n] for n in font.getGlyphOrder()))
        font.save(target); font.close()
        faces = [ft.Face(str(output/f'{key}-{suffix}.ttf'))
                 for suffix in ('source', 'reference', 'experiment', 'reoriented')]
        for char, result in supported:
            size = result['graph']['baseline_execution']['ppem']
            native = coordinate_check(faces[-1], char, size, result['graph'])
            issues = graph_issues(result['graph'])
            if not native['passed'] or issues:
                raise AssertionError(f'{key} {char}: native/graph validation failed')
            name = f'{key}-u{ord(char):04x}.png'
            glyphs = [render(f, char, size, hinted=i > 0) for i, f in enumerate(faces)]
            if (key, char) in previous_cases:
                old = previous_cases[key, char]['result']['graph']['baseline_execution']
                same_coordinates = old['model_points_px'] == result['graph']['baseline_execution']['model_points_px']
                old_path = previous/f'{key}-reoriented.ttf'
                same_bitmap = pixels(render(ft.Face(str(old_path)), char, size, hinted=True)) == pixels(glyphs[-1])
                regressions.append(dict(key=key, char=char, same_coordinates=same_coordinates,
                                        same_bitmap=same_bitmap, previous_font_sha256=digest(old_path)))
                if not same_coordinates or not same_bitmap:
                    raise AssertionError(f'previous supported case changed: {key} {char}')
            comparison(glyphs, ['Unhinted input', 'Baseline v6', 'Representative experiment', 'Reorientation prototype'],
                       f'{key} {char!r}').save(output/name)
            cases.append(dict(key=key, char=char, status='verified', native=native, result=result))
            figures.append(f'<figure id="{key}-u{ord(char):04x}"><img src="{name}" alt="{key} {html.escape(char, quote=True)}"></figure>')
    if not cases:
        raise ValueError('no frozen models found')
    assert sources == {name: digest(HERE/name) for name in sources}
    assert inputs == {name: digest(reference/name) for name in inputs}
    if previous and len(regressions) != sum(char in chars for key, char in previous_cases):
        raise AssertionError('previously supported case missing from regression checks')
    report = dict(scope='Restored membership, compatible frozen defaults, unique lowest-priority single repair; whole-point reorientation with exact-projection substitution. Unreviewed prototype.',
                  sources=sources, inputs=inputs, cases=cases,
                  previous_regressions=regressions,
                  outputs={p.name: digest(p) for p in output.glob('*-reoriented.ttf')})
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Dependency reorientation prototype</title>'
        '<style>figure{margin:16px 0}img{max-width:100%;image-rendering:pixelated}</style>'
        '<h1>Dependency reorientation prototype</h1><p>Unpromoted experiment. Columns: unhinted input, baseline v6, '
        'representative experiment, reorientation prototype. Each supported glyph passed retained-equation, whole-point graph '
        'and native-coordinate checks. Unsupported cases have no candidate image. Fonts retain existing programs for other glyphs.</p>'
        + ''.join(figures))
    print('verified', sum(c['status']=='verified' for c in cases), 'unsupported', sum(c['status']=='unsupported' for c in cases))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, default=HERE/'out/shamir-representative-comparison')
    p.add_argument('--output', type=Path, default=HERE/'out/shamir-reorientation-comparison')
    p.add_argument('--chars', default='HFA')
    p.add_argument('--previous', type=Path)
    a = p.parse_args(); run(a.reference, a.output, a.chars, a.previous)
