"""Late segment-member assembly after the representative point DAG.

Shared-role links enter reduced resolution through shamir_shared_roles; late
ordinary members never redo graph resolution. Explicit reduced equations are
preserved during assembly, and synthetic representative defaults are restored
only on projections still free after late attachments. schedule_member_graph
orders completed representatives and ordinary members topologically, which may
interleave an independent ordinary point among representatives. The simultaneous
evaluator is retained for diagnostics of unsupported shared-role assemblies;
production uses the final point order.
"""
import numpy as np
from shamir_constraints import priority


def assemble_member_graph(points, accepted_reduced, attachments, references=(),
                          contours=None, completion=None):
    from shamir_baseline_solver import DETERMINANT_EPSILON, _freeze_ratio, _complete
    points = np.asarray(points, float).reshape(-1, 2)
    if not np.all(np.isfinite(points)):
        raise ValueError('non-finite member outline')
    candidates = [c for c in accepted_reduced if not c.get('default')] + list(attachments)
    chosen, rejected, warnings = {}, [], []
    prepared = []
    for ident, candidate in enumerate(candidates):
        c = dict(candidate, id=ident, sources=list(candidate['sources']))
        if any(p < 0 or p >= len(points) for p in [c['point'], *c['sources']]):
            raise ValueError('member constraint point outside outline')
        n = np.asarray(c['normal'], float)
        if n.shape != (2,) or not np.all(np.isfinite(n)) or abs(np.linalg.norm(n)-1) > 1e-10:
            raise ValueError('member projection must be finite and normalized')
        arity = {'Abs': 0, 'PAbs': 0, 'Dist': 1, 'PDist': 1, 'Ratio': 2, 'PRatio': 2}
        if c['kind'] not in arity or len(c['sources']) != arity[c['kind']]:
            raise ValueError('invalid member relation or source count')
        _freeze_ratio(points, c)
        if c['value'] is None or not np.isfinite(c['value']):
            raise ValueError('non-finite member relation value')
        prepared.append(c)
    reduced_count = sum(not c.get('default') for c in accepted_reduced)
    for c in prepared[:reduced_count]:
        c['representative_owned'] = True
        chosen.setdefault(c['point'], []).append(c)
    for c in sorted(prepared[reduced_count:], key=lambda c: (tuple(-v for v in priority(c)), c['id'])):
        group = chosen.setdefault(c['point'], [])
        independent = not group or abs(np.linalg.det([group[0]['normal'], c['normal']])) > DETERMINANT_EPSILON
        if len(group) < 2 and independent:
            group.append(c)
        else:
            blocked_by_representative = any(a.get('representative_owned') and abs(np.linalg.det([a['normal'], c['normal']])) <= DETERMINANT_EPSILON for a in group) or (len(group) >= 2 and all(a.get('representative_owned') for a in group))
            reason = 'fixed representative projection' if blocked_by_representative else ('two degrees already constrained' if len(group) >= 2 else 'dependent direction at float64 precision')
            rejected.append(dict(constraint=c, reason=reason))
            if any(priority(c) == priority(a) for a in group):
                warnings.append(dict(kind='priority tie', discarded=c['id']))
    # Keep resolved representative anchors only on axes still free after late
    # attachments. Rebuilding them from the representative pool would introduce
    # new default-reference cycles absent from the reduced point DAG.
    next_id = len(prepared)
    for candidate in accepted_reduced:
        if not candidate.get('default'):
            continue
        group = chosen.setdefault(candidate['point'], [])
        independent = not group or abs(np.linalg.det([group[0]['normal'], candidate['normal']])) > DETERMINANT_EPSILON
        if len(group) < 2 and independent:
            group.append(dict(candidate, id=next_id, sources=list(candidate['sources'])))
            next_id += 1
    if completion is None:
        _complete(points, chosen, references, next_id)
    else:
        completion(points, chosen, references, next_id, contours)
    constraints = [c for p in sorted(chosen) for c in chosen[p]]
    for c in constraints:
        c['depends_on'] = sorted({a['id'] for source in c['sources'] for a in chosen[source]})
    return dict(order=sorted(chosen), scalar_order=[c['id'] for c in constraints],
                constraints=constraints, rejected=rejected, warnings=warnings,
                scheduler='point-representatives/member-equations',
                execution_phase='simultaneous-members',
                baseline_assumption='B11-late-shared-role-equations',
                reduced_selected_relation_count=sum(not c.get('default') for c in accepted_reduced))


def evaluate_member_graph(graph, points, ppem, em):
    """Solve every selected equation; reject singular or inconsistent completion."""
    from shamir_baseline_solver import DECISIONS, _abs_rhs, _dist_rhs, abs_row_map
    if not np.isfinite(ppem) or not np.isfinite(em) or ppem <= 0 or em <= 0:
        raise ValueError('member solver requires positive finite ppem and em')
    points = np.asarray(points, float).reshape(-1, 2)
    size = points.size
    constraints = graph['constraints']
    if len(constraints) != size:
        raise ValueError('member equations must supply two coordinates per point')
    matrix, values = np.zeros((size, size)), np.zeros(size)
    scale = ppem / em
    abs_rows = abs_row_map(constraints)
    for key, row in abs_row_map(graph.get('retained_abs_rows', [])).items():
        abs_rows.setdefault(key, row)
    for row, c in enumerate(constraints):
        n = np.asarray(c['normal'], float)
        p = c['point']
        matrix[row, 2*p:2*p+2] += n
        kind, sources = c['kind'], c['sources']
        if kind in ('Abs', 'PAbs'):
            values[row] = _abs_rhs(c, scale)
        elif kind in ('Dist', 'PDist'):
            values[row] = _dist_rhs(c, scale, abs_rows)
            if sources:
                a = sources[0]
                matrix[row, 2*a:2*a+2] -= n
        elif kind in ('Ratio', 'PRatio'):
            a, b = sources
            t = float(c['value'])
            matrix[row, 2*a:2*a+2] -= (1-t)*n
            matrix[row, 2*b:2*b+2] -= t*n
        else:
            raise ValueError(f'unsupported member relation {kind}')
    try:
        fitted = np.linalg.solve(matrix, values).reshape(-1, 2)
    except np.linalg.LinAlgError as exc:
        raise ValueError('member equations are underdetermined or contradictory') from exc
    if not np.all(np.isfinite(fitted)):
        raise ValueError('non-finite member solution')
    residual = float(np.max(np.abs(matrix @ fitted.ravel()-values))) if size else 0.
    tolerance = 128*np.finfo(float).eps*max(1., float(np.max(np.abs(values))) if size else 0., float(np.max(np.abs(fitted))) if size else 0.)
    if residual > tolerance:
        raise ValueError('member equations fail exact-equation residual check')
    quantized = np.copysign(np.floor(np.abs(fitted)*64+.5), fitted)
    if np.any(np.abs(quantized) > 2**31-1):
        raise ValueError('member solution exceeds signed32 native coordinates')
    metadata = dict(adapter='requested-size-cardinal-scfs', decisions=DECISIONS,
                    execution_phase='simultaneous-members', ppem=ppem, em=em,
                    model_points_px=fitted.tolist(), native_points_px=(quantized/64).tolist(),
                    max_equation_residual_px=residual,
                    max_coordinate_quantization_error_px=float(np.max(np.abs(quantized/64-fitted))) if size else 0.)
    return fitted, metadata


def schedule_member_graph(graph, points, representatives):
    """Order points after every reference they depend on has completed.

    Shared-role candidates must already have participated in reduced resolution.
    A cycle here therefore indicates an unsupported assembly rather than another
    opportunity to discard relations. No selected equation changes in this step.
    """
    count = len(points)
    representatives = set(representatives)
    chosen = {}
    for entry in graph['rejected']:
        proposal = entry['constraint']
        if proposal['point'] in representatives and not proposal.get('default') and not proposal.get('representative_owned'):
            raise ValueError('shared representative relation bypassed reduced resolution')
    for candidate in graph['constraints']:
        c = dict(candidate, sources=list(candidate['sources']))
        p = c['point']
        if not 0 <= p < count or any(not 0 <= s < count for s in c['sources']):
            raise ValueError('member scheduling point outside outline')
        if p in representatives and not c.get('default') and not c.get('representative_owned'):
            raise ValueError('shared representative relation bypassed reduced resolution')
        chosen.setdefault(p, []).append(c)
    if set(chosen) != set(range(count)) or any(len(group) != 2 for group in chosen.values()):
        raise ValueError('member scheduling requires two relations per outline point')
    dependencies = {p: {s for c in group for s in c['sources']} for p, group in chosen.items()}
    pending, order = set(chosen), []
    while pending:
        ready = sorted(p for p in pending if not dependencies[p].intersection(pending))
        if not ready:
            raise ValueError('late member graph contains a dependency cycle after reduced resolution')
        order.extend(ready)
        pending.difference_update(ready)
    constraints = [c for p in order for c in chosen[p]]
    for c in constraints:
        c['depends_on'] = sorted({a['id'] for source in c['sources'] for a in chosen[source]})
    result = dict(graph, order=order, scalar_order=[c['id'] for c in constraints],
                  constraints=constraints, scheduler='point',
                  execution_phase='representatives-then-members',
                  baseline_assumption='B11-representative-role-closure')
    return result
