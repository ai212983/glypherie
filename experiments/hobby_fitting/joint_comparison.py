"""Combine disjoint straight/curved experiment packets without rerunning fits."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from experiments.hobby_fitting import text_review as text


def load(path):
    return json.loads(path.read_text())


def check_provenance(cell):
    for name, expected in cell['provenance'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError('stale input: ' + name)


def combine(diagonal, curves, out):
    dmatrix, cmatrix = load(diagonal / 'matrix.json'), load(curves / 'matrix.json')
    key = lambda c: (c['family'], c['size'], c['weight'], c['hint'])
    if (set(map(key, dmatrix)) != set(map(key, cmatrix))
            or len(dmatrix) != 72 or len(cmatrix) != 72 or len(set(map(key, dmatrix))) != 72):
        raise ValueError('matrix scope mismatch')
    cells = []
    template = Path(__file__).with_suffix('.html')
    for cell in dmatrix:
        directory = cell['directory']
        dpath, cpath = diagonal / directory / 'data.json', curves / directory / 'data.json'
        d, c = load(dpath), load(cpath)
        check_provenance(d)
        check_provenance(c)
        if d['layout'] != c['layout'] or d['probed'] != c['probed'] or len(d['glyphs']) != 95:
            raise ValueError('repertoire or finalized layout mismatch')
        old_tiles, new_tiles, glyphs = {}, {}, []
        for dg, cg in zip(d['glyphs'], c['glyphs']):
            if any(dg[k] != cg[k] for k in ['codepoint', 'source', 'preferred_commands', 'old', 'native_axes']):
                raise ValueError('shared reference mismatch')
            if dg['result']['applied'] and cg['result']['applied']:
                raise ValueError('overlapping model ownership')
            selected = cg if cg['result']['applied'] else dg
            glyphs.append(selected)
            old_tiles[selected['codepoint']] = selected['old']
            new_tiles[selected['codepoint']] = selected['new']
        lines = [dict(text.compose_line_common(line, old_tiles, new_tiles), text=line['text'])
                 for line in d['layout']['lines']]
        merged = dict(d, model='joint', glyphs=glyphs, lines=lines)
        merged['provenance'] = {str(p.resolve().relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in [dpath, cpath, Path(__file__), template,
                                          Path(__file__).parent / 'joint_review_matrix.html']}
        target = out / directory
        target.mkdir(parents=True, exist_ok=True)
        (target / 'data.json').write_text(json.dumps(merged))
        (target / 'index.html').write_text(template.read_text())
        cells.append(dict(cell, counts=dict(probed=95,
                          applied=sum(g['result']['applied'] for g in glyphs),
                          changed=sum(g['changed'] for g in glyphs))))
    (out / 'matrix.json').write_text(json.dumps(cells))
    (out / 'index.html').write_text((Path(__file__).parent / 'joint_review_matrix.html').read_text().replace(
        'Current width fitting compared with the constrained phase experiment.',
        'Current width fitting compared with joint crossing placement and curved-width fitting.'))
    print(json.dumps(dict(cells=len(cells), glyphs=95 * len(cells),
                          applied=sum(c['counts']['applied'] for c in cells),
                          changed=sum(c['counts']['changed'] for c in cells))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('diagonal', type=Path)
    parser.add_argument('curves', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    combine(args.diagonal, args.curves, args.out)
