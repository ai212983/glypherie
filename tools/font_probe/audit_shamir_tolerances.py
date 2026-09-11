"""Read-only sensitivity audit of curved-extremum alignment assumptions.

Enumerate all otherwise-eligible arc/bow pairs once, then report activation at a
fixed geometric series of em-relative bounds. No rendering or threshold selection
is performed. Measurements expose projected-versus-Euclidean and integer-rounding
inconsistencies before any numerical setting is promoted.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import numpy as np
from fontTools.ttLib import TTFont
from compare_shamir_pipeline import CHARS
from shamir_boundary import normalize_boundaries
from shamir_geometry import from_font
from shamir_features import Interior, recognize

BOUNDS = (.003, .006, .012, .024, .048, .096)


def candidates(model):
    interior = Interior(model)
    rows = []
    for axis in (0, 1):
        extrema = [p for p in model['points'] if p['kind'] != 'corner' and str(axis) in p['extrema']]
        for i, a in enumerate(extrema):
            p = np.asarray(a['position'])
            for b in extrema[i+1:]:
                q = np.asarray(b['position'])
                if a['extrema'][str(axis)] != b['extrema'][str(axis)]:
                    continue
                if np.dot(a['outgoing'], b['outgoing']) > -np.cos(model['tolerances']['angle_radians']):
                    continue
                distance = float(np.linalg.norm(p-q))
                if distance <= model['tolerances']['distance'] or not interior.between(p, q):
                    continue
                projected = float(abs(p[axis]-q[axis]))
                rounded_projected = float(abs(np.rint(p[axis])-np.rint(q[axis])))
                rows.append(dict(axis=axis, polarity=a['extrema'][str(axis)], points=[a['id'], b['id']],
                                 positions=[p.tolist(),q.tolist()], alignment_em=float(abs(p[1-axis]-q[1-axis])/model['em']),
                                 projected_width=projected, euclidean_width=distance,
                                 native_projected_width=rounded_projected,
                                 euclidean_rounding=round(distance), projected_rounding=round(projected),
                                 native_projected_rounding=round(rounded_projected)))
    return rows


def summary(rows, bound):
    selected = [r for r in rows if r['alignment_em'] <= bound]
    degree = Counter((r['font'], r['char'], r['axis'], p) for r in selected for p in r['points'])
    return dict(bound_em=bound, features=len(selected), glyphs=len({(r['font'],r['char']) for r in selected}),
                by_font=dict(Counter(r['font'] for r in selected)),
                extrema_with_multiple_partners=sum(n>1 for n in degree.values()),
                euclidean_vs_native_rounded_width_changes=sum(r['euclidean_rounding'] != r['native_projected_rounding'] for r in selected),
                rounding_order_changes=sum(r['projected_rounding'] != r['native_projected_rounding'] for r in selected),
                maximum_euclidean_width_excess=max((r['euclidean_width']-r['projected_width'] for r in selected),default=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, default=Path(__file__).parent/'out/shamir-baseline-v3/inputs')
    parser.add_argument('--output', type=Path, default=Path(__file__).parent/'out/shamir-tolerance-audit.json')
    args = parser.parse_args()
    source_paths = [Path(__file__).parent/name for name in ('audit_shamir_tolerances.py', 'shamir_geometry.py', 'shamir_features.py', 'shamir_boundary.py')]
    sources = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    rows=[];inputs={}; measurement_checks=[]; fonts=('roboto','literata','source-sans-3')
    for family in fonts:
        path=args.inputs/f'{family}-14-source.ttf'; inputs[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
        font=TTFont(path,recalcTimestamp=False)
        normalize_boundaries(font,CHARS)
        for char in CHARS:
            model=from_font(font,char,baseline=True)
            rows.extend(dict(r,font=family,char=char,em=model['em']) for r in candidates(model))
            for feature in recognize(model)['features']:
                if feature['kind'] not in ('arc','bow'):continue
                a,b=[np.asarray(model['points'][p]['position']) for p in feature['points']]
                expected=float(abs(a[feature['axis']]-b[feature['axis']]))
                measurement_checks.append(dict(font=family,char=char,points=feature['points'],recorded_width=feature['width'],projected_width=expected,passed=abs(feature['width']-expected)<1e-9))
    if sources != {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}:
        raise RuntimeError('audit source changed during execution; rerun for consistent evidence')
    report=dict(sources=sources, scope='81 characters x 3 families, 14px optical-size instances; recognition only',
                inputs=inputs, measurement_checks=measurement_checks, current_projected_measurements_passed=all(c['passed'] for c in measurement_checks), bounds=list(BOUNDS), summaries=[summary(rows,b) for b in BOUNDS], candidates=rows)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['summaries'],indent=2))


if __name__=='__main__':main()
