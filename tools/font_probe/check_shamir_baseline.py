"""Freeze baseline execution evidence; visual observations do not gate fidelity."""
import argparse
import hashlib
import json
import math
import platform
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import fontTools
import freetype as ft
import numpy as np
import pathops

from check_shamir_model import outline_diagnostics, construction_checks
from compare_shamir_pipeline import CHARS, SIZES
from shamir_model import build_font

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def graph_issues(graph):
    """Check report topology independently of the scheduler implementation."""
    errors = []
    constraints = graph['constraints']
    ids = [c['id'] for c in constraints]
    if len(set(ids)) != len(ids):
        errors.append('duplicate constraint IDs')
    points = {c['point'] for c in constraints}
    order = graph['order']
    if len(order) != len(set(order)) or set(order) != points:
        errors.append('point order does not cover each point exactly once')
    scalar = graph['scalar_order']
    if len(scalar) != len(set(scalar)) or set(scalar) != set(ids):
        errors.append('execution order does not cover each constraint exactly once')
    rank = {cid: i for i, cid in enumerate(scalar)}
    point_rank = {p: i for i, p in enumerate(order)}
    simultaneous=graph.get('execution_phase')=='simultaneous-members'
    if simultaneous and graph.get('scheduler')!='point-representatives/member-equations':
        errors.append('unknown simultaneous member scheduling contract')
    for c in constraints:
        for source in c['sources']:
            if source not in points:
                errors.append(f"constraint {c['id']}: unknown source {source}")
            elif graph.get('scheduler') == 'point' and point_rank.get(source, -1) >= point_rank.get(c['point'], -1):
                errors.append(f"constraint {c['id']}: source point is not complete first")
        for dep in c.get('depends_on', []):
            if dep not in rank or (not simultaneous and rank[dep] >= rank.get(c['id'], -1)):
                errors.append(f"constraint {c['id']}: invalid execution dependency {dep}")
        if simultaneous:
            expected={a['id'] for a in constraints if a['point'] in c['sources']}
            if set(c.get('depends_on',[]))!=expected:
                errors.append(f"constraint {c['id']}: incomplete simultaneous dependency record")
        if not np.all(np.isfinite(c['normal'])) or not np.isfinite(c['value']):
            errors.append(f"constraint {c['id']}: non-finite relation")
    for rejected in graph['rejected']:
        if not rejected.get('reason') or 'constraint' not in rejected:
            errors.append('rejection lacks constraint or reason')
    return errors


def construction_issues(record):
    """Audit the reduced-to-full mapping and segment selection independently."""
    errors = []
    representatives = record.get('representative_points')
    if representatives is None:
        return ['missing representative point mapping']
    if len(representatives) != len(set(representatives)):
        errors.append('duplicate representative point mapping')
    reduced, final = record['reduced_graph'], record['graph']
    if set(reduced['order']) != set(range(len(representatives))):
        errors.append('representative mapping does not cover reduced points')
    if not set(representatives) <= set(final['order']):
        errors.append('representative mapping refers outside final graph')

    def signature(c):
        return (c['point'], c['kind'], tuple(c['sources']), tuple(c['normal']),
                c['value'], c.get('round', True), bool(c.get('metric', False)))

    expected = Counter()
    for c in reduced['constraints']:
        if c.get('default'):
            continue
        local_points = [c['point'], *c['sources']]
        if any(p < 0 or p >= len(representatives) for p in local_points):
            errors.append(f"reduced constraint {c['id']}: invalid representative index")
            continue
        mapped = dict(c, point=representatives[c['point']],
                      sources=[representatives[p] for p in c['sources']])
        expected[signature(mapped)] += 1
    preserved = Counter(signature(c) for c in final['constraints']
                        if c.get('representative_owned') and not c.get('default'))
    for relation, count in (expected - preserved).items():
        errors.append(f'accepted reduced relation missing or changed in final graph: {relation} ({count})')
    if preserved - expected:
        errors.append('final graph claims representative ownership without an accepted reduced relation')
    if final.get('reduced_selected_relation_count') != sum(expected.values()):
        errors.append('final graph misreports accepted reduced relation count')

    # A cycle may replace a candidate under the same ID. Restore candidate
    # provenance from rejection records and count IDs, not copied dictionaries.
    owners = defaultdict(set)
    candidates = reduced['constraints'] + [r['constraint'] for r in reduced['rejected']]
    for c in candidates:
        if c.get('default') or c.get('shared_role_assumption') or 'segment_owner' not in c:
            continue
        owners[c['segment_owner']].add(c['id'])
    for owner, ids in owners.items():
        if len(ids) > 1:
            errors.append(f'segment {owner} enters reduced resolution with multiple dominant relations: {sorted(ids)}')
    dominance = record.get('segment_dominance')
    if dominance is None:
        errors.append('missing segment dominance audit')
    else:
        for entry in dominance.get('rejected', []):
            if (entry.get('reason') != 'superseded segment relation'
                    or 'segment_owner' not in entry.get('constraint', {})):
                errors.append('invalid segment dominance rejection record')
    return errors


def coordinate_check(face, char, size, graph):
    """Independent simultaneous equation oracle, without the production solver.

    All source coordinates are unknowns in one linear system. This avoids using
    the production point order or accumulating already quantized native anchors.
    SCFS rounds each final coordinate to 26.6: maximum axis error is 1/128px.
    """
    face.set_pixel_sizes(0, size)
    face.load_char(char, ft.FT_LOAD_NO_SCALE | ft.FT_LOAD_NO_HINTING | ft.FT_LOAD_NO_BITMAP)
    original = np.asarray(face.glyph.outline.points, float).reshape(-1, 2)
    count = len(original)
    matrix, values = [], []
    scale = size / face.units_per_EM
    for c in graph['constraints']:
        p, n, kind = c['point'], np.asarray(c['normal']), c['kind']
        row = np.zeros(2 * count)
        row[2*p:2*p+2] = n
        if kind in ('Abs', 'PAbs'):
            value = c['value'] * scale
        elif kind in ('Dist', 'PDist'):
            a = c['sources'][0]
            row[2*a:2*a+2] -= n
            value = float(c['value']) * scale
        elif kind in ('Ratio', 'PRatio'):
            a, b = c['sources']
            t = float(c['value'])
            row[2*a:2*a+2] -= (1-t) * n
            row[2*b:2*b+2] -= t * n
            value = 0
        else:
            raise ValueError(f'unsupported oracle relation: {kind}')
        if c.get('round', True) and kind not in ('Ratio', 'PRatio'):
            value = math.copysign(math.floor(abs(value) + .5), value)
        matrix.append(row)
        values.append(value)
    if len(matrix) != 2 * count:
        raise ValueError('selected equations do not cover two coordinates per native point')
    expected = np.linalg.solve(np.asarray(matrix), np.asarray(values)).reshape(-1, 2) if count else np.empty((0, 2))
    face.load_char(char, ft.FT_LOAD_NO_AUTOHINT | ft.FT_LOAD_PEDANTIC | ft.FT_LOAD_TARGET_MONO | ft.FT_LOAD_NO_BITMAP)
    actual = np.asarray(face.glyph.outline.points, float).reshape(-1, 2) / 64
    error = np.abs(actual - expected)
    maximum = float(error.max()) if count else 0
    return {'passed': bool(np.all(np.isfinite(expected)) and maximum <= 1/128 + 1e-7),
            'max_coordinate_error_px': maximum, 'tolerance_px': 1/128 + 1e-7,
            'expected_points': expected.tolist(), 'actual_points': actual.tolist()}


def decision_metadata_present(build):
    return isinstance(build.get('baseline_decisions'), (dict, list)) and bool(build['baseline_decisions'])


def observation(face, char, size, record):
    # These policies describe the experimental recipes and glyph outcomes. A
    # faithful baseline is allowed to have an unattractive raster or no recipe.
    try:
        return construction_checks(face, char, size, record)
    except (KeyError, ValueError, IndexError, TypeError) as exc:
        return {'available': False, 'reason': f'{type(exc).__name__}: {exc}'}


def run(output):
    if ft.version() != (2, 13, 2):
        raise ValueError('native equation oracle requires FreeType 2.13.2')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('use an empty output directory to preserve frozen evidence')
    source_files = sorted(HERE.glob('*.py'))
    hashes = {p.name: digest(p) for p in source_files}
    snapshot = output / 'sources'
    snapshot.mkdir()
    for path in source_files:
        shutil.copy2(path, snapshot / path.name)
    papers = output / 'papers'
    papers.mkdir()
    paper_files = sorted((HERE.parents[1] / 'docs/reference/fonts/papers').glob('*.pdf'))
    if not paper_files:
        raise ValueError('baseline verification requires the recovered primary paper PDF')
    paper_hashes = {p.name: digest(p) for p in paper_files}
    for path in paper_files:
        shutil.copy2(path, papers / path.name)
    inputs = output / 'inputs'
    inputs.mkdir()
    config = {'profile': 'baseline', 'characters': CHARS, 'sizes': list(SIZES),
              'families': ['roboto', 'literata', 'source-sans-3'],
              'native_coordinate_tolerance_px': 1/128 + 1e-7,
              'native_load': 'NO_AUTOHINT|PEDANTIC|TARGET_MONO|NO_BITMAP'}
    builds, failures = [], []
    for family in config['families']:
        for size in SIZES:
            name = f'{family}-{size}'
            source = HERE / f'out/shamir-controlled/{name}-source.ttf'
            target = output / f'{name}.ttf'
            try:
                source_hash = digest(source)
                frozen_input = inputs / source.name
                shutil.copy2(source, frozen_input)
                build = build_font(frozen_input, target, CHARS, profile='baseline', ppem=size)
                if not decision_metadata_present(build):
                    raise ValueError('baseline build lacks baseline_decisions metadata')
                if set(build['records']) != set(CHARS):
                    raise ValueError('baseline build does not cover requested repertoire')
                face = ft.Face(str(target))
                cases = []
                for char, record in build['records'].items():
                    issues = {stage: graph_issues(record[stage]) for stage in ('reduced_graph', 'graph')}
                    issues['construction'] = construction_issues(record)
                    cases.append({'char': char, 'graph_issues': issues,
                                  'native_coordinates': coordinate_check(face, char, size, record['graph']),
                                  'geometry': outline_diagnostics(face, char, size),
                                  'rejected': {s: record[s]['rejected'] for s in ('reduced_graph', 'graph')}})
                if digest(source) != source_hash or digest(frozen_input) != source_hash:
                    raise ValueError('input changed during verification')
                builds.append({'font': family, 'size': size, 'source_sha256': source_hash,
                               'font_sha256': digest(target), 'input': f'inputs/{source.name}',
                               'output': target.name, 'cases': cases,
                               'observations': {c: observation(face, c, size, build['records'][c]) for c in ('m', '!')},
                               'build': build})
            except Exception as exc:
                failures.append({'font': family, 'size': size, 'error': f'{type(exc).__name__}: {exc}',
                                 'input': f'inputs/{source.name}',
                                 'source_sha256': digest(inputs / source.name) if (inputs / source.name).exists() else None,
                                 'output': target.name, 'font_sha256': digest(target) if target.exists() else None})
    if hashes != {p.name: digest(p) for p in sorted(HERE.glob('*.py'))}:
        failures.append({'error': 'source changed during verification'})
    if paper_hashes != {p.name: digest(p) for p in paper_files}:
        failures.append({'error': 'primary source PDF changed during verification'})
    native_ok = not failures and all(c['native_coordinates']['passed'] for b in builds for c in b['cases'])
    graph_ok = not failures and all(not any(c['graph_issues'].values()) for b in builds for c in b['cases'])
    report = {'config': config, 'config_sha256': hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(), 'source_hashes': hashes, 'paper_hashes': paper_hashes, 'builds': builds, 'failures': failures,
              'versions': {'python': platform.python_version(), 'freetype': ft.version(),
                           'fonttools': fontTools.__version__, 'pathops': pathops.__version__, 'numpy': np.__version__},
              'native_execution_passed': native_ok, 'graph_invariants_passed': graph_ok,
              'baseline_readiness': 'decision review required; numerical success alone does not establish fidelity'}
    (output / 'baseline-verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'native_execution_passed': native_ok, 'graph_invariants_passed': graph_ok,
                      'cases': sum(len(b['cases']) for b in builds), 'failures': failures}, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    result = run(parser.parse_args().output)
    if not result['native_execution_passed'] or not result['graph_invariants_passed']:
        raise SystemExit('baseline verification failed; see frozen report')
