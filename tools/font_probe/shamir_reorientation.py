"""Unpromoted equation-preserving whole-point reorientation experiment.

Keep recorded membership; accept a consistent retained system or its unique
lowest-priority single-removal repair. Orient Dist edges in either direction,
then find a constructive whole-point order. Restore compatible frozen defaults
for missing coordinates and substitute anchored equal-projection distance chains
on a stall. No cycle deletions, Ratio inversions or baseline builder changes.
"""
from itertools import combinations

import numpy as np
from audit_shamir_segment_conflicts import diagnose, equations, solve
from shamir_baseline_solver import DETERMINANT_EPSILON, evaluate_baseline
from shamir_baseline_solver import _round_pixel


class Unsupported(ValueError):
    """The deliberately bounded construction cannot represent this system."""


def projected_anchors(constraints, scale):
    """Substitute Abs through exactly parallel Dist chains, keeping a proof path.

    Round each supplied distance before summing, never the combined distance.
    No near-parallel merging, inferred anchors, Ratio inversion or dense solve.
    Derived values are size-specific algebraic consequences, not new hints.
    """
    derived = []
    for root, anchor in enumerate(constraints):
        if anchor['kind'] not in ('Abs', 'PAbs'):
            continue
        normal = np.asarray(anchor['normal'])
        def scaled(c):
            value = c['value']*scale
            return _round_pixel(value) if c.get('round', True) else value
        known = {anchor['point']: (scaled(anchor), [root])}
        pending = [anchor['point']]
        while pending:
            point = pending.pop(0)
            value, path = known[point]
            for i, c in enumerate(constraints):
                if c['kind'] not in ('Dist', 'PDist'):
                    continue
                n = np.asarray(c['normal'])
                sign = 1 if np.array_equal(n, normal) else -1 if np.array_equal(n, -normal) else 0
                if not sign:
                    continue
                a, = c['sources']; b = c['point']
                if point == a:
                    other, delta = b, sign*scaled(c)
                elif point == b:
                    other, delta = a, -sign*scaled(c)
                else:
                    continue
                if other in known:
                    continue
                known[other] = (value+delta, path+[i]); pending.append(other)
                derived.append(dict(kind='Abs', point=other, normal=normal.tolist(),
                                    sources=[], value=(value+delta)/scale, round=False,
                                    feature='derived-projection', derived_from=path+[i],
                                    derivation='same-projection-distance-substitution'))
    return derived


def orient(constraints, count):
    """Solve a point only when two independent relations have complete sources.

    Reversing n.(b-a)=d produces n.(a-b)=-d, including the supplied value's
    rounding flag. Signed half-away rounding commutes with this negation.
    Other retained equations remain obligations checked after construction.
    """
    pending = set(range(count)); done = set(); chosen = []; order = []
    while pending:
        progress = False
        for point in sorted(pending):
            ready = []
            for origin, c in enumerate(constraints):
                options = [(c, False)]
                if c['kind'] in ('Dist', 'PDist'):
                    a, = c['sources']
                    options.append((dict(c, point=a, sources=[c['point']], value=-c['value']), True))
                for candidate, reversed_edge in options:
                    if candidate['point'] == point and set(candidate['sources']) <= done:
                        ready.append(dict(candidate, origin=origin, reversed=reversed_edge))
            pair = next((pair for pair in combinations(ready, 2)
                         if abs(np.linalg.det([c['normal'] for c in pair])) > DETERMINANT_EPSILON), None)
            if pair is None:
                continue
            for c in pair:
                chosen.append(dict(c, id=len(chosen)))
            done.add(point); pending.remove(point); order.append(point)
            progress = True
            break
        if not progress:
            raise Unsupported(f'whole-point construction stalled at {sorted(pending)}')
    for c in chosen:
        c['depends_on'] = [a['id'] for a in chosen if a['point'] in c['sources']]
    return dict(order=order, scalar_order=[c['id'] for c in chosen], constraints=chosen,
                scheduler='point', execution_phase='experimental-reorientation',
                rejected=[], warnings=[])


def prototype(record):
    diagnostic = diagnose(record)
    retained = list(diagnostic['equations']); removed = None
    if not diagnostic['full_system']['consistent']:
        repairs = diagnostic['lowest_priority_removals']
        if len(repairs) != 1:
            raise Unsupported(f'expected one lowest-priority single repair; found {len(repairs)}')
        removed = repairs[0]['removed']; retained.remove(removed)
    execution = record['graph']['baseline_execution']
    count = len(execution['model_points_px']); scale = execution['ppem']/execution['em']
    matrix, rhs = equations(retained, count, scale)
    oracle = solve(matrix, rhs)
    completion = []
    if oracle['consistent'] and not oracle['unique']:
        completion = [dict(c) for c in record['graph']['constraints']
                      if c.get('default') and c.get('default_reason') != 'dependency cycle']
        retained += completion
        matrix, rhs = equations(retained, count, scale)
        oracle = solve(matrix, rhs)
    if not oracle['consistent'] or not oracle['unique']:
        raise Unsupported('retained equations and frozen defaults lack a unique consistent solution')
    derived = []
    try:
        graph = orient(retained, count)
    except Unsupported:
        derived = projected_anchors(retained, scale)
        graph = orient(retained+derived, count)
    fitted, metadata = evaluate_baseline(graph, np.zeros((count, 2)), execution['ppem'], execution['em'])
    residual = float(np.max(np.abs(matrix @ fitted.ravel()-rhs)))
    error = float(np.max(np.abs(fitted-np.asarray(oracle['points_px']))))
    if residual > oracle['tolerance_px'] or error > oracle['tolerance_px']:
        raise AssertionError('directed graph violates retained equations or dense oracle')
    graph['baseline_execution'] = metadata
    return dict(graph=graph, removed=removed, retained_equations=retained,
                restored_defaults=completion, derived_equations=derived,
                max_retained_residual_px=residual, max_oracle_difference_px=error,
                reversed_equations=[c['origin'] for c in graph['constraints'] if c['reversed']],
                oracle=oracle)
