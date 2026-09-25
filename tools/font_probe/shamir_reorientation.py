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
from shamir_baseline_solver import _round_pixel, _is_y_extent


class Unsupported(ValueError):
    """The deliberately bounded construction cannot represent this system."""


def projected_anchors(constraints, scale, width_table=None):
    """Substitute Abs through exactly parallel Dist chains, keeping a proof path.

    Distances carrying a shared width-class target use it (one integer per
    design width, Microsoft CVT analogue); all other distances round
    per segment as before. No near-parallel merging, inferred anchors,
    Ratio inversion or dense solve. Derived values are size-specific
    algebraic consequences, not new hints.
    """
    from stem_width_table import lookup as _table_lookup
    from shamir_baseline_solver import (_abs_rhs, _dist_rhs, _source_fit,
                                        _is_y_extent, abs_row_map)
    derived = []
    extent_abs = abs_row_map(constraints)
    for root, anchor in enumerate(constraints):
        if anchor['kind'] not in ('Abs', 'PAbs'):
            continue
        normal = np.asarray(anchor['normal'])
        def scaled(c):
            if (width_table is not None
                    and c['kind'] in ('Dist', 'PDist')
                    and c.get('value')):
                return _table_lookup(width_table, abs(float(c['value'])))
            value = c['value']*scale
            return _round_pixel(value) if c.get('round', True) else value
        known = {anchor['point']: (_abs_rhs(anchor, scale), [root])}
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
                total = value+delta
                table_hit = (width_table is not None
                             and c['kind'] in ('Dist', 'PDist')
                             and c.get('value'))
                if (_is_y_extent(c) and c.get('round', True)
                        and not table_hit):
                    # The solver ceils vertical extent maxima and floors
                    # minima; the derived anchor must equal that solved
                    # coordinate, not the per-segment nearest accumulation.
                    # The shared width table never fires here (cut-in keeps
                    # extent-scale distances out of stem clusters).
                    if other == b:
                        # Exact when the source Abs is retained; otherwise
                        # the rounded step applies to the accumulated chain
                        # value, matching the solver's source-plus-RHS sum.
                        _, fitted_s = _source_fit(
                            extent_abs.get((a, tuple(c['normal']))), scale)
                        base = (fitted_s if fitted_s is not None
                                else sign*value)
                        total = sign*(base + _dist_rhs(c, scale, extent_abs))
                    else:
                        # Backward arrival: the row's extent RHS steps back
                        # from the chain value, unless an Abs fixes the end.
                        own = extent_abs.get((other, tuple(c['normal'])))
                        if own is not None:
                            total = sign*_abs_rhs(own, scale)
                        else:
                            total = (value - sign*_dist_rhs(c, scale,
                                                           extent_abs))
                known[other] = (total, path+[i]); pending.append(other)
                entry = dict(kind='Abs', point=other, normal=normal.tolist(),
                             sources=[], value=total/scale, round=False,
                             feature='derived-projection', derived_from=path+[i],
                             derivation='same-projection-distance-substitution')
                if (width_table is not None
                        and constraints[i]['kind'] in ('Dist', 'PDist')
                        and constraints[i].get('value')):
                    from stem_width_table import lookup as _table_lookup
                    design = abs(float(constraints[i]['value']))
                    entry['shared_target_px'] = _table_lookup(
                        width_table, design)
                    entry['width_source_index'] = i
                derived.append(entry)
    return derived


def standardize_widths(retained, derived, scale):
    """Supersede retained Dist values with shared width-class targets.

    Microsoft CVT analogue: once a derived anchor uses the shared target,
    the retained distance equation it came through must agree, or the
    oracle check would reject the standardization as inconsistency.
    Only fires for derived anchors marked by the width table; every
    rewrite is recorded. Returns (updated_retained, changes).
    """
    retained = list(retained)
    changes = []
    for entry in derived:
        if 'shared_target_px' not in entry:
            continue
        i = entry['width_source_index']
        original = retained[i]
        units = entry['shared_target_px'] / scale
        if abs(float(original['value']) - units) < 1e-9:
            continue
        retained[i] = dict(original, value=units, width_standardized=True)
        changes.append(dict(index=i, point=original['point'],
                            from_value=float(original['value']),
                            to_value=units,
                            target_px=entry['shared_target_px']))
    return retained, changes


def orient(constraints, count):
    """Solve a point only when two independent relations have complete sources.

    Reversing n.(b-a)=d produces n.(a-b)=-d, including the supplied value's
    rounding flag. Signed half-away rounding commutes with this negation;
    vertical extent rounding does not (a reversed extent row determines the
    minimum end, handled in the shared solver rounding).
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
                    # Rounded vertical extent rows never reverse: outward
                    # rounding is direction-sensitive, and a reversed row
                    # determines the opposite end with the wrong sense.
                    # Unrounded rows commute exactly and still reverse.
                    # The check mirrors the solver predicate (metric role
                    # or extent flag), never a subset of it.
                    if not (_is_y_extent(c) and c.get('round', True)):
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
    width_changes = []
    width_fallback = None
    try:
        graph = orient(retained, count)
    except Unsupported:
        derived = projected_anchors(retained, scale,
                                    record.get('width_table'))
        standardized, width_changes = standardize_widths(
            retained, derived, scale)
        matrix, rhs = equations(standardized, count, scale)
        oracle = solve(matrix, rhs)
        if not oracle['consistent'] or not oracle['unique']:
            width_fallback = ('width standardization breaks closed-loop '
                              'consistency; retaining unstandardized '
                              'derivation')
            width_changes = []
            derived = projected_anchors(retained, scale, None)
            matrix, rhs = equations(retained, count, scale)
            oracle = solve(matrix, rhs)
            if not oracle['consistent'] or not oracle['unique']:
                raise Unsupported('retained equations lack a unique '
                                  'consistent solution')
        else:
            retained = standardized
        graph = orient(retained+derived, count)
    graph['retained_abs_rows'] = [c for c in retained
                                  if c['kind'] in ('Abs', 'PAbs')]
    fitted, metadata = evaluate_baseline(graph, np.zeros((count, 2)), execution['ppem'], execution['em'])
    residual = float(np.max(np.abs(matrix @ fitted.ravel()-rhs)))
    error = float(np.max(np.abs(fitted-np.asarray(oracle['points_px']))))
    if residual > oracle['tolerance_px'] or error > oracle['tolerance_px']:
        raise AssertionError('directed graph violates retained equations or dense oracle')
    graph['baseline_execution'] = metadata
    return dict(graph=graph, removed=removed, retained_equations=retained,
                restored_defaults=completion, derived_equations=derived,
                width_changes=width_changes, width_fallback=width_fallback,
                max_retained_residual_px=residual, max_oracle_difference_px=error,
                reversed_equations=[c['origin'] for c in graph['constraints'] if c['reversed']],
                oracle=oracle)
