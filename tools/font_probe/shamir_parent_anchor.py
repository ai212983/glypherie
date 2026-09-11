"""Microsoft-inspired parent placement experiment, not a Diagonal/VTT port.

For a free side's oblique Abs sharing a point with an explicit cardinal anchor,
replace its absolute placement with complementary cardinal placement when the
oblique projection is closer to the existing axis. Keep all relative equations.
Rounded and unrounded complementary placement are separate experimental policies.
"""
import numpy as np
from audit_shamir_segment_conflicts import equations, solve
from shamir_constraints import relation
from shamir_reorientation import orient, projected_anchors, Unsupported
from shamir_baseline_solver import evaluate_baseline


def replace_anchors(constraints, points, rounded):
    result = []; changes = []
    for c in constraints:
        n = np.asarray(c['normal']); replacement = None
        if c['kind']=='Abs' and not c.get('default') and 'segment_owner' in c and np.all(n != 0):
            for a in constraints:
                if a['point'] != c['point'] or a['kind'] not in ('Abs','PAbs') or a.get('default'):
                    continue
                an = np.asarray(a['normal'])
                if np.count_nonzero(an) != 1:
                    continue
                axis = int(np.argmax(abs(an))); other = 1-axis
                if abs(n[axis]) <= abs(n[other]):
                    continue
                if not any(x.get('feature')==f"align-{c['segment_owner']}" for x in constraints):
                    continue
                replacement = relation('Abs', c['point'], np.eye(2)[other],
                                       value=float(points[c['point']][other]), round=rounded,
                                       feature='complementary-parent-anchor')
                changes.append(dict(original=c, replacement=replacement, cardinal_anchor=a))
                break
        result.append(replacement if replacement is not None else dict(c))
    return result, changes


def experiment(previous, points, size, em, rounded):
    retained, changes = replace_anchors(previous['retained_equations'], points, rounded)
    matrix, rhs = equations(retained, len(points), size/em)
    oracle = solve(matrix, rhs)
    if not oracle['consistent'] or not oracle['unique']:
        raise Unsupported('parent placement does not produce a unique consistent retained system')
    try:
        graph = orient(retained, len(points))
    except Unsupported:
        graph = orient(retained+projected_anchors(retained, size/em), len(points))
    fitted, metadata = evaluate_baseline(graph, points, size, em)
    residual = float(np.max(abs(matrix@fitted.ravel()-rhs)))
    delta = float(np.max(abs(fitted-np.asarray(oracle['points_px']))))
    if max(residual, delta) > oracle['tolerance_px']:
        raise AssertionError('directed solution differs from retained equations')
    graph['baseline_execution'] = metadata
    return dict(graph=graph, changes=changes, retained_equations=retained,
                residual_px=residual, oracle_delta_px=delta, rounded=rounded)
