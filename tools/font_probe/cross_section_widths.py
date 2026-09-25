"""Experimental material cross-section equations; geometry-only inputs.

Samples retain source edge interpolation weights as the outline moves. This is
not an Eulerian section at a fixed world height, or a paper-conformance claim.
"""
import itertools
import numpy as np
from shamir_baseline_solver import _round_pixel


def section(points, ends, flags, feature):
    p = np.asarray(points, float)
    direction = np.asarray(feature['support_direction'])
    normal = np.asarray(feature['normal'])
    levels = [a + (b-a)*t for a, b in feature['support_intervals'] for t in (.2, .5, .8)]
    level = levels[len(levels)//2]
    hits = []
    start = 0
    for end in ends:
        for a in range(start, end+1):
            b = a+1 if a < end else start
            if not (flags[a] & 1 and flags[b] & 1):
                continue
            span = float((p[b]-p[a]) @ direction)
            if abs(span) < 1e-12:
                continue
            t = float((level-p[a] @ direction)/span)
            # Endpoint samples can belong to two edges: hold rather than guess.
            if 1e-9 < t < 1-1e-9:
                weights = {a: 1-t, b: t}
                hits.append((weights, (1-t)*p[a]+t*p[b]))
        start = end+1
    matches = []
    for a, b in itertools.combinations(hits, 2):
        distance = float((b[1]-a[1]) @ normal)
        if abs(abs(distance)-feature['width']) > 1e-6:
            continue
        if distance < 0:
            a, b = b, a
        weights = dict(b[0])
        for i, w in a[0].items():
            weights[i] = weights.get(i, 0)-w
        matches.append(weights)
    if len(matches) != 1:
        raise ValueError(f'cross-section has {len(matches)} unique support pairs')
    return matches[0]


def system(graph, count, scale):
    from shamir_baseline_solver import _abs_rhs, _dist_rhs, abs_row_map
    matrix = np.zeros((count*2, count*2)); rhs = np.zeros(count*2)
    abs_rows = abs_row_map(graph['constraints'])
    for i, c in enumerate(graph['constraints']):
        n = np.asarray(c['normal']); j = 2*c['point']
        matrix[i, j:j+2] += n
        if c['kind'] in ('Ratio', 'PRatio'):
            for a, w in zip(c['sources'], (1-c['value'], c['value'])):
                matrix[i, 2*a:2*a+2] -= w*n
        elif c['kind'] in ('Abs', 'PAbs'):
            for a in c['sources']:
                matrix[i, 2*a:2*a+2] -= n
            rhs[i] = _abs_rhs(c, scale)
        else:
            for a in c['sources']:
                matrix[i, 2*a:2*a+2] -= n
            rhs[i] = _dist_rhs(c, scale, abs_rows)
    return matrix, rhs


def fit(points, ends, flags, record, scale):
    p = np.asarray(points, float)
    matrix, rhs = system(record['graph'], len(p), scale)
    audit = []
    for row, c in enumerate(record['graph']['constraints']):
        name = c.get('feature', '')
        if not name.startswith('width-') or c['kind'] not in ('Dist', 'PDist'):
            continue
        f = record['features'][int(name.removeprefix('width-'))]
        if f['kind'] != 'slant':
            continue
        if c['kind'] == 'PDist':
            audit.append(dict(id=c['id'], status='held', reason='font-wide parameter policy unresolved'))
            continue
        try:
            weights = section(p, ends, flags, f)
        except ValueError as exc:
            audit.append(dict(id=c['id'], status='held', reason=str(exc)))
            continue
        matrix[row] = 0
        for i, w in weights.items():
            matrix[row, 2*i:2*i+2] = w*np.asarray(f['normal'])
        target = _round_pixel(f['width']*scale)
        if target <= 0:
            raise ValueError('rounded cross-section collapses')
        rhs[row] = target
        error = abs(float(matrix[row] @ p.ravel())-f['width'])
        if error > 1e-6:
            raise ValueError('source cross-section reconstruction failed')
        audit.append(dict(id=c['id'], status='replaced', weights=weights,
                          target_px=target, source_error_units=error))
    # Verify source reconstruction with every RHS set to its source measurement.
    # This tests rank/conditioning and assembly, not the original hinting policy.
    source = np.linalg.solve(matrix, matrix @ p.ravel()).reshape(-1, 2)
    source_error = float(np.max(abs(source-p)))
    if source_error > 1e-6:
        raise ValueError('source reconstruction unstable')
    fitted = np.linalg.solve(matrix, rhs).reshape(-1, 2)
    residual = float(np.max(abs(matrix @ fitted.ravel()-rhs)))
    if not np.isfinite(fitted).all() or residual > 1e-8:
        raise ValueError('cross-section solve failed residual check')
    return fitted, dict(relations=audit, source_error_units=source_error,
                        equation_residual_px=residual,
                        condition_number=float(np.linalg.cond(matrix)))


def export_graph(fitted, scale):
    constraints = [dict(id=2*i+axis, kind='Abs', point=i, sources=[],
                        normal=[1-axis, axis], value=float(q[axis]/scale), round=False)
                   for i, q in enumerate(fitted) for axis in (0, 1)]
    return dict(order=list(range(len(fitted))), constraints=constraints)
