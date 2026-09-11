"""Bounded ASCII terminal coverage audit using frozen native input coordinates."""
import html
import json
import shutil
from array import array
from pathlib import Path

import freetype as ft
import numpy as np
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables.ttProgram import Program

from check_shamir_baseline import digest
from compare_paper_prototypes import render, pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from shamir_baseline_solver import compile_baseline
from shamir_constraints import relation
from vtt_terminal_links import candidates, program, values

HERE = Path(__file__).resolve().parent


def coords(face, char, size, hinted=True):
    face.set_pixel_sizes(0, size)
    flags = ft.FT_LOAD_NO_BITMAP | (ft.FT_LOAD_PEDANTIC | ft.FT_LOAD_NO_AUTOHINT | ft.FT_LOAD_TARGET_MONO if hinted else ft.FT_LOAD_NO_HINTING)
    face.load_char(char, flags)
    return np.asarray(face.glyph.outline.points, float) / 64


def build(source, target, char, size, roles):
    face = ft.Face(str(source)); before = coords(face, char, size)
    original = coords(face, char, size, False)
    font = TTFont(source); g = font['glyf'][font.getBestCmap()[ord(char)]]
    points, _, _ = g.getCoordinates(font['glyf']); em = font['head'].unitsPerEm
    value = min(values(points, roles, False))
    # Freeze this input's actual gridfit first; the experiment changes only the terminal.
    cs = [dict(relation('Abs', i, np.eye(2)[axis], value=float(p[axis])*em/size, round=False),
               id=2*i+axis, depends_on=[]) for i, p in enumerate(before) for axis in (0, 1)]
    graph = dict(order=list(range(len(points))), constraints=cs, scheduler='point')
    assembly, _ = compile_baseline(graph, points, size, em)
    if 'cvt ' not in font:
        font['cvt '] = newTable('cvt '); font['cvt '].values = array('h')
    index = len(font['cvt '].values); font['cvt '].values.append(value)
    # Both links use the same CVT entry and rounding state.
    assembly = assembly[:-1] + program(roles, [index, index], round_down=True) + assembly[-1:]
    g.program = Program(); g.program.fromAssembly(assembly)
    font['maxp'].maxSizeOfInstructions = max(font['maxp'].maxSizeOfInstructions, len(g.program.getBytecode()))
    font['maxp'].maxStackElements = max(font['maxp'].maxStackElements, 16)
    font.save(target); font.close()
    actual = coords(ft.Face(str(target)), char, size); expected = before.copy()
    scaled = np.floor(value*size/em*64+.5)/64
    for parent, child in [(roles['upper_arm'], roles['top']), (roles['lower_arm'], roles['bottom'])]:
        assert abs(abs(original[child, 1]-original[parent, 1])-scaled) < 1, 'CVT cut-in excludes shared measurement'
        expected[child, 1] = before[parent, 1] + np.sign(original[child, 1]-original[parent, 1])*np.floor(scaled)
    for a, b, children in [(roles['upper_arm'], roles['top'], roles['upper']),
                            (roles['bottom'], roles['lower_arm'], roles['lower']),
                            (roles['top'], roles['bottom'], roles['tip'])]:
        for i in children:
            t = (points[i][1]-points[a][1])/(points[b][1]-points[a][1])
            expected[i, 1] = expected[a, 1] + t*(expected[b, 1]-expected[a, 1])
    error = float(np.max(abs(actual-expected)))
    touched = {roles['top'], roles['bottom'], *roles['upper'], *roles['lower'], *roles['tip']}
    assert error <= 1/64+1e-7
    assert np.array_equal(before[:, 0], actual[:, 0])
    assert all(np.array_equal(before[i], actual[i]) for i in range(len(before)) if i not in touched)
    ext = [float(actual[roles['top'], 1]-actual[roles['upper_arm'], 1]),
           float(actual[roles['lower_arm'], 1]-actual[roles['bottom'], 1])]
    assert ext[0] == ext[1]
    return dict(cvt_fu=value, extensions_px=ext, oracle_error_px=error,
                native_points=actual.tolist(), preserved_unrelated_points=True)


def run():
    output = HERE/'out/terminal-coverage-v1'; output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()): raise ValueError('output must be empty')
    (output/'sources').mkdir()
    hashes = {p.name: digest(p) for p in HERE.glob('*.py')}
    for name in hashes: shutil.copy2(HERE/name, output/'sources'/name)
    inventory = []; inputs = {}; links = []; counts = {}; matched_figures = []
    for source in sorted((HERE/'out/parent-anchor-v1').glob('*-unrounded.ttf')):
        key = source.stem.removesuffix('-unrounded'); size = int(key.rsplit('-', 1)[1])
        inputs[source.name] = digest(source); shutil.copy2(source, output/source.name)
        font = TTFont(source); cmap = font.getBestCmap(); face = ft.Face(str(source))
        figures = []; totals = dict(matched=0, ambiguous=0, near_miss=0, no_match=0, missing=0)
        for code in range(33, 127):
            char = chr(code); row = dict(key=key, char=char, codepoint=code)
            if code not in cmap:
                row['status'] = 'missing'; totals['missing'] += 1; inventory.append(row); continue
            glyph = font['glyf'][cmap[code]]; points, ends, flags = glyph.getCoordinates(font['glyf'])
            rejected = []; hits = candidates(points, flags, ends, rejected)
            status = 'matched' if len(hits)==1 else 'ambiguous' if hits else 'near_miss' if rejected else 'no_match'
            row.update(status=status, matches=hits, rejected_pairs=rejected)
            totals[status] += 1
            if status == 'no_match': inventory.append(row); continue
            glyphs = [render(face, char, size, hinted=True)]; labels = ['Current input']
            if status == 'matched':
                target = output/f'{key}-u{code:04x}-paired.ttf'
                row['validation'] = build(source, target, char, size, hits[0])
                candidate = render(ft.Face(str(target)), char, size, hinted=True)
                row['changed_pixels'] = len(pixels(glyphs[0]) ^ pixels(candidate))
                glyphs.append(candidate); labels.append('Shared smaller / round down')
            else:
                glyphs.append(glyphs[0]); labels.append('Held for recognition review')
            name = f'{key}-u{code:04x}.png'
            panel = comparison(glyphs, labels, f'{key} {char!r} - {status}')
            prepend_reference(face, char, size, f'{key} {char!r}', glyphs, panel).save(output/name)
            explanation = '; '.join(sorted({r['reason'] for r in rejected}))
            figures.append(f'<figure id="u{code:04x}"><img loading="lazy" src="{name}" alt="{html.escape(char, quote=True)}"><figcaption>{status}: {html.escape(explanation)}</figcaption></figure>')
            if status == 'matched':
                matched_figures.append(f'<figure id="{key}-u{code:04x}"><img src="{name}" alt="{key} {char}"></figure>')
            inventory.append(row)
        font.close(); counts[key] = totals
        (output/f'{key}.html').write_text('<!doctype html><meta charset="utf-8"><style>img{max-width:100%}figure{margin:16px 0}</style><a href="index.html">Index</a><h1>'+key+'</h1><p>Smooth source, current input, candidate or held input. Near misses have two horizontal anchors but fail the terminal geometry checks.</p>'+''.join(figures))
        links.append(f'<li><a href="{key}.html">{key}</a>: '+html.escape(str(totals))+'</li>')
        print(key, totals, flush=True)
    assert hashes == {name:digest(HERE/name) for name in hashes}
    assert inputs == {p.name:digest(p) for p in (HERE/'out/parent-anchor-v1').glob('*-unrounded.ttf')}
    (output/'report.json').write_text(json.dumps(dict(repertoire='U+0021–U+007E inclusive (94 printable ASCII glyphs)',
        sources=hashes, inputs=inputs, counts=counts, inventory=inventory,
        limitations=['Only original-winding, right-facing explicit vertical terminal edges with horizontal arm anchors; maximum 20-point bracket walk.',
                     'No match means outside this detector, not proof that no useful pair exists.',
                     'Inputs retain mixed experimental history: parent-anchor corrections cover H/F/A; other glyphs retain inherited rendering.',
                     'Native input coordinates are frozen before applying paired links; this is a transfer audit, not baseline promotion.']), indent=2)+'\n')
    (output/'matches.html').write_text('<!doctype html><meta charset="utf-8"><style>img{max-width:100%}figure{margin:16px 0}</style><a href="index.html">Coverage index</a><h1>All geometric matches</h1><p>Smooth source, current input, paired candidate. Equal extension lengths do not imply fully mirrored curves or pixels.</p>'+''.join(matched_figures))
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><h1>Paired terminal coverage</h1><p><a href="matches.html">Review all eight matches: Literata E and F</a></p><p>94 printable ASCII characters × 3 fonts × 4 sizes. Geometry selects candidates; glyph names do not. Every match and bracketed near miss is shown. Unmatched and missing characters are listed in <a href="report.json">report.json</a>.</p><p>Inputs retain the current experimental fonts: H/F/A have parent-anchor treatment; other glyphs retain inherited rendering. Only matched terminal coordinates change. Recognition covers one right-facing structure and its original winding.</p><ul>'+''.join(links)+'</ul>')


if __name__ == '__main__': run()
