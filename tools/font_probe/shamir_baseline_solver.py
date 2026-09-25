"""Source-led point solver and requested-size native adapter (B07–B12).

The point DAG follows the recorded Shamir 2003 §3.6 contract. Reference choice,
perpendicular completion, stable ties and original-position cycle completion are
conservative assumptions, recorded by decision IDs. Independence is geometric;
native freedom-vector conditioning does not decide which relations survive.

The size-specific adapter solves the model in float64 and exports cardinal 26.6
positions. This is an explicit translation assumption, not Table I bytecode.
"""
import math
import numpy as np
from shamir_constraints import priority, relation, push_integer
from shamir_point_schedule import schedule
from shamir_prototype import push


# A numerical singularity boundary, rather than a typographic condition cutoff.
DETERMINANT_EPSILON = 32 * np.finfo(float).eps
DECISIONS = ['B07', 'B08', 'B09', 'B10', 'B11', 'B12']


def _freeze_ratio(points, c):
    if c['kind'] != 'Ratio' or c['value'] is not None:
        return
    a, b = c['sources']
    n = np.asarray(c['normal'])
    span = float((points[b] - points[a]) @ n)
    offset = float((points[c['point']] - points[a]) @ n)
    if span == 0:
        c.update(kind='Dist', sources=[a], value=offset, round=False,
                 degenerate_ratio=True, baseline_assumption='B08-degenerate-ratio')
    else:
        c['value'] = offset / span


def _complete(points, chosen, references, first_id):
    references = sorted(set(map(int, references)))
    if any(r < 0 or r >= len(points) for r in references):
        raise ValueError('baseline reference point outside outline')
    for p in range(len(points)):
        group = chosen.setdefault(p, [])
        normals = ([np.array([-group[0]['normal'][1], group[0]['normal'][0]])]
                   if len(group) == 1 else list(np.eye(2)) if not group else [])
        for slot, n in enumerate(normals):
            projection = points @ n
            c = relation('Abs', p, n, value=float(projection[p]), round=False,
                         default=True, id=first_id + 2*p + slot,
                         baseline_assumption='B08-default-completion')
            eligible = [r for r in references if r != p]
            lower = [r for r in eligible if projection[r] <= projection[p]]
            upper = [r for r in eligible if projection[r] >= projection[p]]
            pair = None
            if lower and upper:
                a = max(lower, key=lambda r: projection[r])
                b = min(upper, key=lambda r: projection[r])
                if projection[a] != projection[b]:
                    pair = a, b
            if pair is None and eligible:
                a = min(eligible, key=lambda r: abs(projection[r]-projection[p]))
                distinct = [r for r in eligible if projection[r] != projection[a]]
                if distinct:
                    pair = a, min(distinct, key=lambda r: abs(projection[r]-projection[p]))
            if pair is not None:
                a, b = pair
                c.update(kind='Ratio', sources=[a, b],
                         value=float((projection[p]-projection[a])/(projection[b]-projection[a])))
            elif eligible:
                a = min(eligible, key=lambda r: abs(projection[r]-projection[p]))
                c.update(kind='Dist', sources=[a], value=float(projection[p]-projection[a]),
                         default_reason='no distinct projected reference pair')
            else:
                c['default_reason'] = 'no reference points'
            group.append(c)


def resolve_baseline(points, candidates, reference_points=()):
    points = np.asarray(points, float).reshape(-1, 2)
    if not np.all(np.isfinite(points)):
        raise ValueError('non-finite baseline outline')
    chosen, rejected, warnings = {}, [], []
    prepared = []
    for i, candidate in enumerate(candidates):
        c = dict(candidate, id=i, sources=list(candidate['sources']))
        p, sources = c['point'], c['sources']
        if any(v < 0 or v >= len(points) for v in [p, *sources]):
            raise ValueError('baseline constraint point outside outline')
        n = np.asarray(c['normal'], float)
        if n.shape != (2,) or not np.all(np.isfinite(n)) or not np.linalg.norm(n):
            raise ValueError('invalid baseline projection')
        if abs(np.linalg.norm(n)-1) > 1e-10:
            raise ValueError('baseline projection must be normalized')
        c['normal'] = n.tolist()
        arity = {'Abs': 0, 'PAbs': 0, 'Dist': 1, 'PDist': 1, 'Ratio': 2, 'PRatio': 2}
        if c['kind'] not in arity or len(sources) != arity[c['kind']]:
            raise ValueError('invalid baseline relation or source count')
        _freeze_ratio(points, c)
        if c['value'] is None or not np.isfinite(c['value']):
            raise ValueError('non-finite baseline relation value')
        prepared.append(c)
    for c in sorted(prepared, key=lambda c: (tuple(-x for x in priority(c)), c['id'])):
        group = chosen.setdefault(c['point'], [])
        determinant = (float(np.linalg.det([group[0]['normal'], c['normal']])) if group else 1.)
        if len(group) < 2 and abs(determinant) > DETERMINANT_EPSILON:
            group.append(c)
        else:
            reason = 'two degrees already constrained' if len(group) >= 2 else 'dependent direction at float64 precision'
            rejected.append(dict(constraint=c, reason=reason))
            if any(priority(c) == priority(a) for a in group):
                warnings.append(dict(kind='priority tie', discarded=c['id']))
    _complete(points, chosen, reference_points, len(prepared))
    graph = schedule(points, chosen, rejected, warnings)
    graph.update(baseline_decisions=DECISIONS, direction_policy='geometric-independence',
                 determinant_epsilon=DETERMINANT_EPSILON)
    for c in graph['constraints']:
        if c.get('default_reason') == 'dependency cycle':
            c['baseline_assumption'] = 'B11-cycle-original-position'
    return graph


def _round_pixel(value):
    return math.copysign(math.floor(abs(value)+.5), value)


def abs_row_map(constraints):
    """Index Abs/PAbs rows by (point, normal) for extent source lookup."""
    rows = {}
    for c in constraints:
        if c['kind'] in ('Abs', 'PAbs'):
            rows.setdefault((c['point'], tuple(c['normal'])), c)
    return rows


_EXTENT_EPS = 1e-9


def _extent_sense(constraint):
    """'max'/'min' when this row determines a vertical extent, else None.

    Metric bounds follow the construction invariant (Abs on the minimum
    end, Dist on the maximum); explicitly flagged rows carry their own
    direction. Only +y rows participate.
    """
    if list(constraint.get('normal', [])) != [0.0, 1.0]:
        return None
    flag = constraint.get('extent')
    if flag in ('min', 'max'):
        return flag
    if constraint.get('metric_role') != 'glyph-y-bound':
        return None
    # A bare True predates directional flags; fall back to kind inference.
    kind = constraint['kind'].removeprefix('P')
    if kind == 'Abs':
        return 'min'
    if kind == 'Dist':
        return 'max'
    return None


def _is_y_extent(constraint):
    return _extent_sense(constraint) is not None


def _abs_rhs(c, scale):
    """Self-contained right-hand side for an Abs/PAbs row.

    Per-edge outward round states follow the TrueType round-state
    vocabulary (spec RUTG/RDTG via SROUND: tops/rights round up,
    bottoms/lefts round down); minima/maxima here are the +y
    specialization of that rule. No paper parent for the y-extent
    choice itself (see ledger WHY).
    """
    value = float(c['value']) * scale
    if not c.get('round', True):
        return value
    sense = _extent_sense(c)
    if sense == 'max':
        return math.ceil(value - _EXTENT_EPS)
    if sense == 'min':
        # Overshoot suppression, not outward flooring: sub-baseline
        # fractions snap to the zone edge (roboto-14 '0' -0.137px to
        # 0, matching native), while descenders and flats round
        # neutrally like every other row. Flooring overshoots adds a
        # raster row native hinting never renders; features floating
        # above the baseline keep legacy flooring.
        if value <= 0:
            return _round_pixel(value)
        return math.floor(value + _EXTENT_EPS)
    return _round_pixel(value)


def _source_fit(abs_row, scale):
    """(design, fitted) source position for an extent Dist row.

    Reads the source's own Abs row, so sequential, simultaneous, and
    diagnostic builds ceil the same total. Returns (None, None) when
    the source has no Abs row.
    """
    if abs_row is None:
        return None, None
    design = float(abs_row['value']) * scale
    return design, _abs_rhs(abs_row, scale)


def _dist_rhs(c, scale, abs_rows):
    """Right-hand side for a Dist/PDist row.

    Vertical extent rows round the design total outward (maxima ceil,
    minima floor), preserving the raster extent; every other distance
    keeps round-to-nearest. Reversal never commutes with outward rounding
    the way nearest rounding does (orient forbids it for rounded rows).
    Outward sense follows spec RUTG/RDTG (see ``_abs_rhs``); the
    extent-flagged choice itself is ledger WHY.
    """
    value = float(c['value']) * scale
    if not c.get('round', True):
        return value
    sense = _extent_sense(c)
    if sense is None:
        return _round_pixel(value)
    out = math.ceil if sense == 'max' else math.floor
    adjust = -_EXTENT_EPS if sense == 'max' else _EXTENT_EPS
    key = lambda p: (p, tuple(c['normal']))
    if c.get('reversed'):
        # Unreached in production (orient never reverses rounded extent
        # rows); kept exact for the metric case, nearest otherwise.
        if c.get('extent') not in (None, True):
            return _round_pixel(value)
        design_a, fitted_a = _source_fit(abs_rows.get(key(c['point'])), scale)
        if fitted_a is None:
            return _round_pixel(value)
        return fitted_a - math.ceil(design_a - value - _EXTENT_EPS)
    sources = c.get('sources', [])
    if not sources:
        return out(value + adjust)
    design_s, fitted_s = _source_fit(abs_rows.get(key(sources[0])), scale)
    if fitted_s is None:
        return out(value + adjust)
    return out(design_s + value + adjust) - fitted_s


def evaluate_baseline(graph, points, ppem, em):
    """Solve §3.2 equations; quantize only at export.

    Both distance kinds use the supplied signed d. Our Ratio value weights the
    second source, equivalent to exchanging t with (1-t) in the paper notation.
    Parameterization changes value sharing, rather than the equation semantics.
    """
    if graph.get('execution_phase')=='simultaneous-members':
        from shamir_baseline_members import evaluate_member_graph
        return evaluate_member_graph(graph,points,ppem,em)
    if not np.isfinite(ppem) or not np.isfinite(em) or ppem <= 0 or em <= 0:
        raise ValueError('baseline requires positive finite ppem and em')
    points = np.asarray(points, float).reshape(-1, 2)
    scale = ppem / em
    fitted = points * scale
    by_point = {}
    for c in graph['constraints']:
        by_point.setdefault(c['point'], []).append(c)
    # Selected rows win; retained-but-unselected rows fill gaps so extent
    # totals match the diagnostic oracle built from the full set.
    abs_rows = abs_row_map(graph['constraints'])
    for key, row in abs_row_map(graph.get('retained_abs_rows', [])).items():
        abs_rows.setdefault(key, row)
    done = set()
    for p in graph['order']:
        group = by_point[p]
        if len(group) != 2:
            raise ValueError('baseline point requires two independent relations')
        values = []
        for c in group:
            kind, n, sources = c['kind'], np.asarray(c['normal']), c['sources']
            if not set(sources).issubset(done):
                raise ValueError('baseline point order precedes a dependency')
            if kind in ('Abs', 'PAbs'):
                value = _abs_rhs(c, scale)
            elif kind in ('Dist', 'PDist'):
                a = sources[0]
                value = float(fitted[a] @ n) + _dist_rhs(c, scale, abs_rows)
            elif kind in ('Ratio', 'PRatio'):
                a, b = sources
                t = float(c['value'])
                value = float(((1-t)*fitted[a] + t*fitted[b]) @ n)
            else:
                raise ValueError(f'unsupported baseline relation {kind}')
            values.append(value)
        matrix = np.asarray([c['normal'] for c in group])
        if abs(float(np.linalg.det(matrix))) <= DETERMINANT_EPSILON:
            raise ValueError('baseline point singular at float64 precision')
        fitted[p] = np.linalg.solve(matrix, values)
        if not np.all(np.isfinite(fitted[p])):
            raise ValueError('non-finite baseline solution')
        done.add(p)
    if done != set(range(len(points))):
        raise ValueError('baseline graph does not cover outline')
    # Nearest26.6 export; half away from zero for reproducible signed ties.
    quantized = np.copysign(np.floor(np.abs(fitted)*64+.5), fitted)
    if np.any(np.abs(quantized) > 2**31-1):
        raise ValueError('baseline solution exceeds signed32 native coordinates')
    metadata = dict(adapter='requested-size-cardinal-scfs', decisions=DECISIONS,
                    ppem=ppem, em=em, model_points_px=fitted.tolist(),
                    native_points_px=(quantized/64).tolist(),
                    max_coordinate_quantization_error_px=float(np.max(np.abs(quantized/64-fitted))) if len(points) else 0.)
    return fitted, metadata


def compile_baseline(graph, points, ppem, em, cvt_id=None):
    """Export only the requested integer ppem; other sizes retain the outline."""
    if not isinstance(ppem, (int, np.integer)) or not 1 <= ppem <= 16384:
        raise ValueError('baseline native adapter supports integer ppem1..16384')
    _, metadata = evaluate_baseline(graph, points, ppem, em)
    # Both axes must match: this adapter supports an isotropic requested size.
    assembly = ['SVTCA[1]', 'MPPEM[ ]'] + push(ppem) + ['EQ[ ]', 'SVTCA[0]', 'MPPEM[ ]'] + push(ppem) + ['EQ[ ]', 'AND[ ]', 'IF[ ]']
    for axis in (0, 1):
        assembly += ['SVTCA[1]' if axis == 0 else 'SVTCA[0]']
        for p, point in enumerate(metadata['native_points_px']):
            assembly += push(p) + push_integer(round(point[axis]*64)) + ['SCFS[ ]']
    assembly += ['EIF[ ]']
    return assembly, metadata
