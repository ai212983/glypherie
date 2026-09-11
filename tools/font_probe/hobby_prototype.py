"""Bounded Hobby formulation experiment; independent of native font hints.

Source: Hobby, Generating Automatically-Tuned Bitmaps from Outlines, CSTR 148,
sections 3.1 (eqs 1-3), 3.2 (eq 5), 3.3, 3.5, 4 and 6.
https://telecom.wiki/download/attachments/819301/CSTR%20148.pdf

Implemented: integrated perpendicular displacement, stretching/bending, opposing
black/white boundary widths, tangent grid variables, exact source reflections,
and one joint quadratic objective over original quadratic Bezier control points.
The outline remains quadratic; sampling supplies linear expressions in controls.

Explicit departures: normal-ray opposed boundaries approximate the segment-site
Voronoi medial axis (no axis graph or dual-angle pruning). Font width clustering
is a fixed preprocessing table, not section 4's joint font-wide optimization.
Symmetry is exact coordinate matching, not Hobby's approximate-symmetry matcher.
Diagonal widths use projected integer offset vectors chosen before optimization,
not section 3.4's integer influence zones. Grid supports use analytic extrema and
axis-parallel lines without section 3.3's influence-zone construction. Quadratic
sampling uses section 6's linear mapping principle; section 5.3's encoding and
sparsity reduction are omitted.
The integer solver eliminates continuous variables and performs coordinate descent
from three deterministic starts, instead of LLL reduction / rounded substitution.
This gives a local solution with no global optimality claim. Paper position,
strain and width coefficients are retained; grid/symmetry weights and tolerances
are experiment choices. Cubic outlines explicitly fail. No topology rescue or
pixel corrections are applied. Output is float pixel coordinates, unquantized.
"""
import math
import numpy as np


def segments(source, tags, ends):
    """Bezier coefficients include implied on-curve midpoint semantics."""
    n = len(source)
    if len(tags) != n or (ends and ends[-1] != n - 1):
        raise ValueError('invalid outline indexing')
    if any(t not in (0, 1) for t in tags):
        raise ValueError('Hobby prototype supports quadratic/line outlines only')
    basis = np.eye(n)
    result = []
    start = 0
    for end in ends:
        ids = list(range(start, end + 1)); start = end + 1
        expanded = []
        for k, i in enumerate(ids):
            j = ids[(k + 1) % len(ids)]
            expanded.append((basis[i], tags[i]))
            if tags[i] == tags[j] == 0:
                expanded.append(((basis[i] + basis[j]) / 2, 1))
        first = next(i for i, (_, tag) in enumerate(expanded) if tag == 1)
        expanded = expanded[first:] + expanded[:first]
        expanded.append(expanded[0])
        k = 0
        while k < len(expanded) - 1:
            degree = 1 if expanded[k + 1][1] else 2
            result.append(np.array([item[0] for item in expanded[k:k+degree+1]]))
            k += degree
    return result


def evaluate(segment, t):
    if len(segment) == 2:
        return (1-t)*segment[0] + t*segment[1]
    return (1-t)**2*segment[0] + 2*t*(1-t)*segment[1] + t*t*segment[2]


def flatten(source, curves):
    edges = []
    for curve in curves:
        control = curve @ source
        length = np.linalg.norm(np.diff(control, axis=0), axis=1).sum()
        steps = max(1, math.ceil(length / .4))
        last = evaluate(curve, 0)
        for t in np.linspace(0, 1, steps + 1)[1:]:
            row = evaluate(curve, t)
            if np.linalg.norm((row-last) @ source) > 1e-8:
                edges.append((last, row))
            last = row
    return edges


def inside(point, starts, finishes):
    y = point[1]
    dy = finishes[:, 1] - starts[:, 1]
    active = (np.minimum(starts[:, 1], finishes[:, 1]) <= y) & (y < np.maximum(starts[:, 1], finishes[:, 1]))
    ids = np.flatnonzero(active)
    crossing = starts[ids, 0] + (y-starts[ids, 1])*(finishes[ids, 0]-starts[ids, 0])/dy[ids]
    return np.sign(dy[ids[crossing > point[0]]]).sum() != 0


def features(source, curves, size):
    edges = flatten(source, curves)
    if not edges:
        return edges, []
    starts = np.array([a @ source for a, b in edges])
    finishes = np.array([b @ source for a, b in edges])
    vectors = finishes-starts
    lengths = np.linalg.norm(vectors, axis=1)
    found = []
    for i, (a, b) in enumerate(edges):
        midpoint = (starts[i]+finishes[i])/2
        tangent = vectors[i]/lengths[i]
        normal = np.array([-tangent[1], tangent[0]])
        # Ray-line intersection, nearest boundary on each side; rejected nearest
        # boundaries never permit jumping across an intervening contour.
        denominator = normal[0]*vectors[:, 1]-normal[1]*vectors[:, 0]
        offset = starts-midpoint
        usable = np.abs(denominator) > 1e-9
        distance = np.full(len(edges), np.inf); along = np.full(len(edges), np.inf)
        distance[usable] = (offset[usable, 0]*vectors[usable, 1]-offset[usable, 1]*vectors[usable, 0])/denominator[usable]
        along[usable] = (offset[usable, 0]*normal[1]-offset[usable, 1]*normal[0])/denominator[usable]
        usable &= (along >= 0) & (along <= 1) & (np.abs(distance) > 1e-6)
        for sign in (-1, 1):
            candidates = np.flatnonzero(usable & (distance*sign > 0))
            if not len(candidates):
                continue
            j = min(candidates, key=lambda index: abs(distance[index]))
            width = abs(distance[j])
            if not .15 <= width <= size*.4:
                continue
            # Tangent-opposition heuristic, not the paper's A-P-B medial-circle
            # opposition angle; 146 degrees is borrowed only as a threshold.
            if tangent @ (vectors[j]/lengths[j]) > math.cos(math.radians(146)):
                continue
            other = (1-along[j])*edges[j][0] + along[j]*edges[j][1]
            direction = normal*sign
            kind = 'black' if inside(midpoint+direction*width/2, starts, finishes) else 'white'
            found.append(dict(row=other-(a+b)/2, normal=direction, width=float(width),
                              length=float(lengths[i]/2), kind=kind))
    return edges, found


def measure(source, tags, ends, size):
    _, found = features(np.asarray(source), segments(source, tags, ends), size)
    # Keep axis widths for shared tables; curved oblique widths retain their
    # source value so orientation sampling does not invent common font weights.
    return [dict(source=f['width'], kind=f['kind']) for f in found
            if max(abs(f['normal'])) > .999 and f['kind'] == 'black']


def aggregate_measurements(records):
    if records and isinstance(records[0], list):
        records = [r for group in records for r in group]
    groups = []
    for value in sorted(r['source'] for r in records if r['kind'] == 'black'):
        if groups and abs(value-np.mean(groups[-1])) < .125:
            groups[-1].append(value)
        else:
            groups.append([value])
    return {'widths': [dict(source=float(np.mean(g)), target=max(1, math.floor(np.mean(g)+.5)),
                           kind='black', count=len(g)) for g in groups if len(g) >= 3]}


def axis_supports(source, curves):
    found = []
    for curve in curves:
        p = curve @ source
        for axis in (0, 1):
            if np.ptp(p[:, axis]) < 1e-8:
                found.append((evaluate(curve, .5), axis))
            elif len(curve) == 3:
                denominator = p[0, axis]-2*p[1, axis]+p[2, axis]
                if abs(denominator) > 1e-9:
                    t = (p[0, axis]-p[1, axis])/denominator
                    if 0 <= t <= 1:
                        found.append((evaluate(curve, t), axis))
    # Each geometric support has its own integer variable. Averaging disjoint
    # supports at equal source coordinates would align only their mean.
    unique = {}
    for row, axis in found:
        unique[(axis, tuple(np.round(row, 10)))] = (row, axis)
    return list(unique.values())


def integer_solve(a, b, grid, grid_weight=12):
    """Eliminate real variables exactly, locally optimize reduced integer form."""
    if not len(grid):
        return np.linalg.lstsq(a, b, rcond=None)[0], dict(converged=True, sweeps=0, integers=[])
    g = np.asarray(grid)
    h = a.T @ a + grid_weight*g.T @ g
    rhs = a.T @ b
    base = np.linalg.solve(h, rhs)
    influence = np.linalg.solve(h, grid_weight*g.T)
    q = grid_weight*(np.eye(len(g))-g @ influence)
    q = (q+q.T)/2
    c = -grid_weight*g @ base
    relaxed = np.linalg.lstsq(q, -c, rcond=None)[0]
    best = None
    for z in (np.floor(relaxed), np.floor(relaxed+.5), np.ceil(relaxed)):
        converged = False
        for sweep in range(100):
            changed = False
            for k in range(len(z)):
                if q[k, k] <= 1e-10:
                    continue
                optimum = -(c[k]+q[k] @ z-q[k, k]*z[k])/q[k, k]
                candidate = math.floor(optimum+.5)
                delta = candidate-z[k]
                improvement = 2*delta*(q[k] @ z+c[k])+delta*delta*q[k, k]
                if improvement < -1e-10:
                    z[k] = candidate; changed = True
            if not changed:
                converged = True; break
        score = float(z @ q @ z + 2*c @ z)
        if best is None or score < best[0]:
            best = (score, base+influence @ z, dict(converged=converged, sweeps=sweep+1, integers=z.astype(int).tolist()))
    return best[1], best[2]


def fit(source, tags, ends, size, font_measurements=None):
    source = np.asarray(source, dtype=float)
    if not np.isfinite(source).all() or size <= 0:
        raise ValueError('finite outline and positive size required')
    curves = segments(source, tags, ends)
    if not len(source):
        return source.copy(), dict(status='empty outline', converged=True)
    edges, widths = features(source, curves, size)
    n = len(source); rows = []; targets = []; labels = []
    def vector(row, direction):
        return (row[:, None]*np.asarray(direction)[None, :]).reshape(-1)
    def add(row, target, weight, label):
        rows.append(row*math.sqrt(weight)); targets.append(target*math.sqrt(weight)); labels.append(label)
    # Tiny null-space regularizer for controls that sampling does not determine.
    for row, target in zip(np.eye(2*n), source.reshape(-1)):
        add(row, target, 1e-6, 'regularizer')
    for a, b in edges:
        delta = (b-a) @ source; length = np.linalg.norm(delta)
        tangent = delta/length; normal = np.array([-tangent[1], tangent[0]])
        average = vector((a+b)/2, normal); difference = vector(b-a, normal)
        add(average, average @ source.reshape(-1), 1000/size**3*length, 'position')
        add(difference, difference @ source.reshape(-1), 1000/size**3*length/12, 'position')
        for direction, label in ((tangent, 'stretch'), (normal, 'bend')):
            row = vector(b-a, direction)
            add(row, row @ source.reshape(-1), 25/size/length, label)
    table = (font_measurements or {}).get('widths', [])
    for feature in widths:
        target = feature['width']; normal = feature['normal']
        if feature['kind'] == 'black' and max(abs(normal)) > .999 and table:
            match = min(table, key=lambda r: abs(r['source']-target))
            if abs(match['source']-target) < .125:
                target = match['target']
        elif feature['kind'] == 'black' and .2 < min(abs(normal)) and feature['width'] < size*.2:
            # Integer offset projection for oblique paired boundaries; choose
            # minimal tangential component then closeness to original width.
            options = [(np.array([x, y]), x*normal[0]+y*normal[1]) for x in range(-4, 5) for y in range(-4, 5)]
            options = [(v, w) for v, w in options if w > .25 and abs(w-target) < .35]
            if options:
                _, target = min(options, key=lambda item: (item[1]-target)**2 + .03*(item[0] @ np.array([-normal[1], normal[0]]))**2)
        add(vector(feature['row'], normal), target, 50/size*feature['length']/feature['width']**2, feature['kind']+'_width')
    grid = [vector(row, np.eye(2)[axis]) for row, axis in axis_supports(source, curves)]
    symmetries = []
    for axis in (0, 1):
        centre = (source[:, axis].min()+source[:, axis].max())/2
        reflected = source.copy(); reflected[:, axis] = 2*centre-reflected[:, axis]
        matches = []
        for point, tag in zip(reflected, tags):
            distances = np.linalg.norm(source-point, axis=1)
            candidates = [i for i in np.flatnonzero(distances < 1e-7) if tags[i] == tag]
            if not candidates:
                break
            matches.append(candidates[0])
        if len(matches) == n:
            symmetries.append(axis)
            # Difference of pair midpoints preserves symmetry with a free axis.
            reference = np.eye(n)[0]+np.eye(n)[matches[0]]
            for i, j in enumerate(matches):
                row = np.eye(n)[i]+np.eye(n)[j]-reference
                add(vector(row, np.eye(2)[axis]), 0, 12, 'symmetry')
    a = np.array(rows); b = np.array(targets)
    result, solver = integer_solve(a, b, grid)
    residual = a @ result-b
    terms = {label: float(np.sum(residual[np.array(labels)==label]**2)) for label in sorted(set(labels))}
    fitted = result.reshape(-1, 2)
    return fitted, dict(status='experimental Hobby subset', solver='reduced quadratic integer coordinate descent',
        **solver, grid_supports=len(grid), black_widths=sum(f['kind']=='black' for f in widths),
        white_widths=sum(f['kind']=='white' for f in widths), symmetry_axes=symmetries,
        objective_terms=terms, max_displacement_px=float(np.max(np.linalg.norm(fitted-source, axis=1))),
        grid_residual_px=float(np.max(np.abs(np.array(grid) @ result-np.array(solver['integers'])))) if grid else 0)
