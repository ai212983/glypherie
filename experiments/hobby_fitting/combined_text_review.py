"""Compose frozen combined fits against the width-only baseline for text review."""

# cspell:words Roboto

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.hobby_fitting import joint_review, text_review


def load(path):
    return json.loads(path.read_text())


def build(combined, joint, out):
    matrix = load(combined / 'matrix.json')
    expected = {(f, s, w, h) for f in ('Roboto', 'SourceSans3')
                for s in (12, 14, 16, 18, 20, 24) for w in (300, 400, 700)
                for h in ('selective_default', 'auto_default')}
    key = lambda c: (c['family'], c['size'], c['weight'], c['hint'])
    if len(matrix) != 72 or set(map(key, matrix)) != expected:
        raise ValueError('combined matrix scope mismatch')
    if len(load(joint / 'matrix.json')) != 72 or set(map(key, load(joint / 'matrix.json'))) != expected:
        raise ValueError('joint matrix scope mismatch')
    if out.exists():
        raise ValueError('output already exists; retain frozen review packets')
    out.mkdir(parents=True)
    hashes, cells, audit = {}, [], []

    def digest(path):
        name = str(path.resolve().relative_to(ROOT))
        if name not in hashes:
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return hashes[name]

    def provenance(data):
        for name, sha in data['provenance'].items():
            if digest(ROOT / name) != sha:
                raise ValueError('stale source or packet: ' + name)

    for entry in matrix:
        name = entry['directory']
        final_path, prior_path = combined / name / 'data.json', joint / name / 'data.json'
        final, prior = load(final_path), load(prior_path)
        provenance(final)
        provenance(prior)
        if key(final) != key(entry) or key(prior) != key(entry):
            raise ValueError('case identity mismatch')
        if final['layout'] != prior['layout']:
            raise ValueError('native layout mismatch')
        codes = list(range(32, 127))
        if any(d['probed'] != codes or [g['codepoint'] for g in d['glyphs']] != codes
               for d in (final, prior)):
            raise ValueError('incomplete ASCII repertoire')
        baseline_tiles, joint_tiles, candidate_tiles, glyphs = {}, {}, {}, []
        for g, p in zip(final['glyphs'], prior['glyphs']):
            if (g['source'] != p['source'] or g['native_axes'] != p['native_axes']
                    or g['preferred_commands'] != p['commands'] or g['old'] != p['new']):
                raise ValueError('joint-to-attached chain mismatch')
            for tile in (p['old'], p['new'], g['new']):
                if (len(tile['pixels']) != tile['width'] * tile['height']
                        or any(v not in (0, 1) for v in tile['pixels'])):
                    raise ValueError('invalid captured bitmap')
            code = g['codepoint']
            baseline_tiles[code], joint_tiles[code], candidate_tiles[code] = p['old'], p['new'], g['new']
            changed = joint_review.ink(p['old']) != joint_review.ink(g['new'])
            glyphs.append(dict(char=g['char'], codepoint=code, old=p['old'], new=g['new'],
                               source=g['source'], baseline_commands=p['preferred_commands'],
                               commands=g['commands'], changed=changed,
                               joint_applied=p['result']['applied'], attached_applied=g['result']['applied']))
        lines = []
        for i, line in enumerate(final['layout']['lines']):
            replay = dict(text_review.compose_line_common(line, joint_tiles, candidate_tiles), text=line['text'])
            if replay != final['lines'][i]:
                raise ValueError('final text replay mismatch')
            replay = dict(text_review.compose_line_common(line, baseline_tiles, joint_tiles), text=line['text'])
            if replay != prior['lines'][i]:
                raise ValueError('baseline text replay mismatch')
            pair = text_review.compose_line_common(line, baseline_tiles, candidate_tiles)
            lines.append(dict(text=line['text'], frame=pair['frame'],
                              baseline=pair['upstream']['pixels'], candidate=pair['width_only']['pixels']))
        changes = [dict(char=g['char'], old_ink=sum(g['old']['pixels']), new_ink=sum(g['new']['pixels']),
                        old_width=g['old']['width'], new_width=g['new']['width'])
                   for g in glyphs if g['changed']]
        data = dict(family=final['family'], size=final['size'], weight=final['weight'], hint=final['hint'],
                    lines=lines, glyphs=glyphs, changes=changes,
                    layout_sha256=hashlib.sha256(json.dumps(final['layout'], sort_keys=True).encode()).hexdigest(),
                    inputs={str(p.relative_to(ROOT)): digest(p) for p in (final_path, prior_path)})
        target = out / name
        target.mkdir()
        (target / 'data.json').write_text(json.dumps(data, separators=(',', ':')))
        cells.append(dict(family=final['family'], size=final['size'], weight=final['weight'],
                          hint=final['hint'], directory=name, changes=len(changes)))
        audit.append(dict(cell=name, changes=changes))
    template = Path(__file__).with_suffix('.html')
    (out / 'index.html').write_bytes(template.read_bytes())
    (out / 'matrix.json').write_text(json.dumps(cells))
    for path in (Path(__file__), template, combined / 'matrix.json', joint / 'matrix.json',
                 Path(text_review.__file__), Path(joint_review.__file__)):
        digest(path)
    report = dict(cells=len(cells), glyphs=95 * len(cells),
                  changed=sum(c['changes'] for c in cells), native_layout_identical=True,
                  baseline_text_replayed=True, candidate_text_replayed=True,
                  classification='diagnostic changes; optical findings recorded separately',
                  provenance=hashes, cases=audit)
    (out / 'audit.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k not in ('provenance', 'cases')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--combined', type=Path, default=ROOT / 'out/diagnostics/attached-diagonal/review')
    parser.add_argument('--joint', type=Path, default=ROOT / 'out/diagnostics/shape-balance-next/review')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    build(args.combined.resolve(), args.joint.resolve(), args.out.resolve())
