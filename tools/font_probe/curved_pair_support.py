"""Geometric support for displaced curve extrema (experimental policy)."""
import numpy as np


def support(model, point, axis):
    """Tangent-coordinate interval between adjacent opposite-axis extrema.

    Walking whole monotone arcs makes the interval independent of quadratic
    subdivision. Corners terminate support, even without an extremum.
    """
    other = 1-axis
    loop = model['contours'][point['contour']]
    ids = [model['segments'][s]['start'] for s in loop]
    start = ids.index(point['id']); values = [point['position'][other]]
    for direction in (-1, 1):
        for step in range(1, len(ids)):
            p = model['points'][ids[(start+direction*step) % len(ids)]]
            values.append(p['position'][other])
            if str(other) in p['extrema'] or p['kind'] == 'corner':
                break
    return min(values), max(values)


def pairs(model, axis, interior):
    """Mutual unique nearest ink-connected extrema with shared arc support.

    This replaces an absolute tangent-offset cutoff. It does not infer reflected
    outlines or use glyph identity. Width is the normal projection, not the
    oblique distance between vertically/horizontally displaced extrema.
    """
    points = [p for p in model['points']
              if p['kind'] != 'corner' and str(axis) in p['extrema']]
    choices = {p['id']: [] for p in points}; candidates = []
    eps = model['tolerances']['distance']; other = 1-axis
    cosine = np.cos(model['tolerances']['angle_radians'])
    for i, a in enumerate(points):
        for b in points[i+1:]:
            if a['extrema'][str(axis)] != b['extrema'][str(axis)]: continue
            if np.dot(a['outgoing'], b['outgoing']) > -cosine: continue
            p, q = np.asarray(a['position']), np.asarray(b['position'])
            width = abs(float(q[axis]-p[axis]))
            if width <= eps: continue
            sa, sb = support(model, a, axis), support(model, b, axis)
            if not (sa[0] <= q[other] <= sa[1] and sb[0] <= p[other] <= sb[1]): continue
            if not interior.between(p, q): continue
            candidates.append((a, b))
            choices[a['id']].append((width, b['id']))
            choices[b['id']].append((width, a['id']))
    def nearest(pid, partner):
        values = sorted(choices[pid])
        return (values[0][1] == partner and
                (len(values) == 1 or values[1][0]-values[0][0] > 1e-9))
    return [(a, b) for a, b in candidates
            if nearest(a['id'], b['id']) and nearest(b['id'], a['id'])]
