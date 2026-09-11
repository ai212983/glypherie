"""Read-only audit of cross-section widths versus representative distances."""
import json
from collections import Counter
from pathlib import Path

import freetype as ft
import numpy as np
from fontTools.ttLib import TTFont

from check_shamir_baseline import digest
from compare_paper_prototypes import pixels, render
from shamir_baseline_solver import _round_pixel

HERE = Path(__file__).resolve().parent


def run():
    rows, inputs = [], {}
    glyphs = 0
    for uniform in sorted((HERE / 'out/geometric-candidate-v3').glob('*-candidate.ttf')):
        key = uniform.stem.removesuffix('-candidate')
        size = int(key.rsplit('-', 1)[1])
        ref = HERE / 'out/shamir-representative-comparison' / f'{key}-experiment.ttf'
        model_path = ref.with_name(f'{key}-model.json')
        for path in (uniform, ref, model_path):
            inputs[str(path.relative_to(HERE))] = digest(path)
        records = json.loads(model_path.read_text())['records']
        with TTFont(uniform) as repertoire, TTFont(ref) as font:
            scale = size / font['head'].unitsPerEm
            for code in sorted(repertoire.getBestCmap()):
                glyphs += 1
                char = chr(code)
                record = records[char]
                points = np.asarray(font['glyf'][font.getBestCmap()[code]].getCoordinates(font['glyf'])[0], float)
                for i, feature in enumerate(record['features']):
                    if feature['kind'] != 'slant':
                        continue
                    a, b = feature['points']
                    projection = abs(float((points[b] - points[a]) @ feature['normal']))
                    width = feature['width']
                    selected = [c for c in record['graph']['constraints']
                                if c.get('feature') == f'width-{i}' and c['kind'] in ('Dist', 'PDist')]
                    rows.append(dict(key=key, char=char, feature=i,
                                     width_px=width * scale,
                                     representative_distance_px=projection * scale,
                                     offset_px=(projection - width) * scale,
                                     rounded_width=_round_pixel(width * scale),
                                     rounded_distance=_round_pixel(projection * scale),
                                     selected=[dict(id=c['id'], kind=c['kind'],
                                                    target_px=c['value'] * scale,
                                                    rounded_target=_round_pixel(c['value'] * scale)
                                                    if c.get('round', True) else c['value'] * scale)
                                               for c in selected]))
    # Width sharing does not guarantee reflection. Measure every existing pair,
    # including unchanged specimens. This metric alone does not demand symmetry
    # from intentionally asymmetric source outlines.
    comparison = HERE / 'out/diagonal-widths-v1'
    report_path = comparison / 'report.json'
    inputs[str(report_path.relative_to(HERE))] = digest(report_path)
    symmetry = []
    for case in json.loads(report_path.read_text())['cases']:
        if case['status'] not in ('changed', 'same-bitmap'):
            continue
        key, char = case['key'], case['char']
        row = dict(key=key, char=char)
        for version in ('before', 'after'):
            path = comparison / f'{key}-u{ord(char):04x}-{version}.ttf'
            inputs[str(path.relative_to(HERE))] = digest(path)
            ink = pixels(render(ft.Face(str(path)), char, int(key.rsplit('-', 1)[1]), hinted=True))
            xs = [x for x, _ in ink]
            axis2 = min(xs) + max(xs)
            row[version] = len(ink ^ {(axis2 - x, y) for x, y in ink})
        symmetry.append(row)
    summary = dict(screened_glyphs=glyphs, detected_slants=len(rows),
                   by_family=dict(Counter(r['key'].rsplit('-', 1)[0] for r in rows)),
                   selected_slants=sum(bool(r['selected']) for r in rows),
                   distinct_measurements=sum(abs(r['offset_px']) > 1e-9 for r in rows),
                   different_rounded_measurements=sum(r['rounded_width'] != r['rounded_distance'] for r in rows),
                   max_absolute_offset_px=max(abs(r['offset_px']) for r in rows))
    assert all(digest(HERE / name) == sha for name, sha in inputs.items())
    output = HERE / 'out/diagonal-distance-audit'
    output.mkdir(exist_ok=True)
    (output / 'report.json').write_text(json.dumps(dict(summary=summary, features=rows,
                                                      raster_reflection=symmetry, inputs=inputs,
                                                      script_sha256=digest(Path(__file__))), indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    run()
