"""Geometric half-serif experiment backed by VTT type 2/3 relationships.

Project assumptions: paired horizontal bases at outline extrema, thin vertical
ends <= .12em, a following straight stem edge >= .10em; local measured values
instead of a CVT table; two-anchor bracket interpolation. This is not a VTT port.
"""
import numpy as np
from shamir_baseline_solver import _round_pixel


def detect(points, ends, flags, em):
    p = np.asarray(points, float); halves = []; start = 0
    for end in ends:
        contour = list(range(start, end+1)); start = end+1
        on = [i for i in contour if flags[i] & 1]
        def span(a, b, direction):
            result = [a]; pos = contour.index(a)
            while result[-1] != b:
                pos = (pos+direction) % len(contour); result.append(contour[pos])
            return result
        for k, a in enumerate(on):
            b = on[(k+1) % len(on)]
            if len(span(a, b, 1)) != 2 or p[a, 1] != p[b, 1]:
                continue
            if p[a, 1] not in (p[:, 1].min(), p[:, 1].max()) or abs(p[a, 0]-p[b, 0]) < .15*em:
                continue
            pair = []
            for endpoint, direction in ((a, -1), (b, 1)):
                pos = on.index(endpoint); upper = on[(pos+direction) % len(on)]
                if len(span(endpoint, upper, direction)) != 2 or p[endpoint, 0] != p[upper, 0]:
                    break
                thin = p[upper, 1]-p[endpoint, 1]
                if not 0 < abs(thin) <= .12*em:
                    break
                hit = None
                for step in range(2, min(len(on), 16)):
                    stem = on[(pos+step*direction) % len(on)]
                    following = on[(pos+(step+1)*direction) % len(on)]
                    edge = p[following]-p[stem]
                    if len(span(stem, following, direction)) == 2 and np.linalg.norm(edge) >= .10*em:
                        extension = p[endpoint, 0]-p[stem, 0]
                        height = p[stem, 1]-p[endpoint, 1]
                        if abs(edge[1]) > abs(edge[0]) and height*thin > 0 and abs(height) > abs(thin) and 0 < abs(extension) < .2*em:
                            hit = dict(type=2 if edge[0] == 0 else 3, endpoint=endpoint,
                                       upper=upper, stem=stem, following=following,
                                       members=span(endpoint, stem, direction),
                                       extension_fu=float(extension), thin_fu=float(thin), height_fu=float(height))
                        break
                if hit is None:
                    break
                pair.append(hit)
            if len(pair) == 2:
                halves.extend(pair)
    owned = [i for h in halves for i in h['members']]
    if len(owned) != len(set(owned)):
        raise ValueError('overlapping serif role assignments')
    return halves


def fit(points, fitted, halves, scale):
    source = np.asarray(points, float)*scale; out = np.asarray(fitted, float).copy()
    audit = []
    for h in halves:
        endpoint, upper, stem = (h[k] for k in ('endpoint', 'upper', 'stem'))
        old = out[h['members']].copy()
        sign = np.sign(h['thin_fu']); base = out[endpoint, 1]
        extension = _round_pixel(h['extension_fu']*scale)
        thickness = sign*max(1., abs(_round_pixel(h['thin_fu']*scale)))
        out[endpoint, 0] = out[stem, 0]+extension
        out[upper] = [out[endpoint, 0], base+thickness]
        if h['type'] == 2:
            out[stem, 1] = base+sign*max(1., abs(_round_pixel(h['height_fu']*scale)))
        for i in h['members'][2:-1]:
            for axis in (0, 1):
                width = source[stem, axis]-source[upper, axis]
                if width == 0:
                    raise ValueError('degenerate bracket interpolation')
                t = (source[i, axis]-source[upper, axis])/width
                out[i, axis] = out[upper, axis]+t*(out[stem, axis]-out[upper, axis])
        audit.append(dict(h, extension_px=extension, thickness_px=thickness,
                          before=old.tolist(), after=out[h['members']].tolist()))
    return out, audit
