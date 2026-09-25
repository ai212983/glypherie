"""Equation diagnostic with restored segment membership; never builds a font.

Scope: retained semantic equations of a frozen graph plus every recorded member
link. Membership is held fixed as an experimental hypothesis. Enumerating single
semantic removals is exhaustive only for one-removal repairs of this equation set;
it is not the paper's directed resolution algorithm or a full candidate rebuild.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from shamir_constraints import priority


def equations(constraints, count, scale):
    from shamir_baseline_solver import _abs_rhs, _dist_rhs, abs_row_map
    matrix = np.zeros((len(constraints), count * 2))
    values = np.zeros(len(constraints))
    abs_rows = abs_row_map(constraints)
    for i, c in enumerate(constraints):
        n = np.asarray(c['normal'], float)
        matrix[i, 2*c['point']:2*c['point']+2] += n
        kind = c['kind'].removeprefix('P')
        if kind == 'Abs':
            values[i] = _abs_rhs(c, scale)
        elif kind == 'Dist':
            a, = c['sources']
            values[i] = _dist_rhs(c, scale, abs_rows)
            matrix[i, 2*a:2*a+2] -= n
        elif kind == 'Ratio':
            a, b = c['sources']
            matrix[i, 2*a:2*a+2] -= (1-c['value'])*n
            matrix[i, 2*b:2*b+2] -= c['value']*n
        else:
            raise ValueError(f'unsupported constraint {kind}')
    return matrix, values


def solve(matrix, values):
    if not np.isfinite(matrix).all() or not np.isfinite(values).all():
        raise ValueError('nonfinite diagnostic equations')
    recovery = None
    try:
        points, _, rank, _ = np.linalg.lstsq(matrix, values, rcond=None)
    except np.linalg.LinAlgError:
        active = np.any(matrix != 0, axis=0)
        if active.all() or not active.any():
            raise
        # Exact zero columns are unconstrained coordinates. Removing them leaves
        # the objective unchanged; zero restores its minimum-norm solution.
        # Keep NumPy's ORIGINAL dimensional cutoff, not the reduced shape's.
        cutoff = np.finfo(float).eps * max(matrix.shape)
        reduced, _, rank, _ = np.linalg.lstsq(matrix[:, active], values, rcond=cutoff)
        points = np.zeros(matrix.shape[1]); points[active] = reduced
        recovery = dict(method='exact-zero-column-reduction', removed_columns=int((~active).sum()), rcond=cutoff)
    residual = float(np.max(np.abs(matrix @ points-values), initial=0))
    # Diagnostic backward-error threshold, explicitly separate from production.
    tolerance = 128*np.finfo(float).eps*max(matrix.shape)*max(
        1., float(np.linalg.norm(matrix, ord=np.inf))*float(np.max(np.abs(points), initial=0)),
        float(np.max(np.abs(values), initial=0)))
    return dict(consistent=bool(residual <= tolerance), unique=int(rank) == matrix.shape[1],
                rank=int(rank), residual_px=residual, tolerance_px=tolerance,
                points_px=points.reshape(-1, 2).tolist(), numerical_recovery=recovery)


def diagnose(record):
    graph = record['graph']; execution = graph['baseline_execution']
    members = [dict(a['constraint']) for a in record['attachment_resolution']]
    # Member provenance is recorded separately, independent of its selected state.
    semantic = [dict(c) for c in graph['constraints']
                if not c.get('default') and not c.get('feature', '').startswith('align-')]
    constraints = members + semantic
    matrix, values = equations(constraints, len(execution['model_points_px']),
                               execution['ppem']/execution['em'])
    full = solve(matrix, values)
    repairs = []
    recoveries = []
    if not full['consistent']:
        for i, c in enumerate(semantic, len(members)):
            result = solve(np.delete(matrix, i, axis=0), np.delete(values, i))
            if result['numerical_recovery']:
                recoveries.append(dict(removed_equation=i, recovery=result['numerical_recovery'],
                                       residual_px=result['residual_px'], consistent=result['consistent']))
            if result['consistent']:
                repairs.append(dict(removed=c, priority=list(priority(c)), solution=result))
    repairs.sort(key=lambda r: r['priority'])
    return dict(ppem=execution['ppem'], membership_hypothesis='all recorded member equations retained',
                equations=constraints, right_hand_sides_px=values.tolist(), full_system=full,
                single_semantic_removals=repairs, numerical_recoveries=recoveries,
                lowest_priority_removals=[r for r in repairs if r['priority'] == repairs[0]['priority']])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('models', type=Path, nargs='+')
    p.add_argument('--chars', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    rows = []
    for path in args.models:
        raw = path.read_bytes(); model = json.loads(raw)
        for char in args.chars:
            rows.append(dict(input=path.name, sha256=hashlib.sha256(raw).hexdigest(),
                             char=char, diagnostic=diagnose(model['records'][char])))
    report = dict(scope=__doc__, cases=rows)
    serialized = json.dumps(report, indent=2)+'\n'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        stream.write(serialized)
    for row in rows:
        d = row['diagnostic']
        print(row['input'], repr(row['char']), 'consistent', d['full_system']['consistent'],
              'repairs', len(d['single_semantic_removals']), 'lowest',
              [(r['removed'].get('feature'), r['removed']['kind'], r['removed']['point'])
               for r in d['lowest_priority_removals']])


if __name__ == '__main__':
    main()
