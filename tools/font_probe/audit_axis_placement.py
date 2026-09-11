"""Axis-placement symmetry diagnostic (measurements only, no corrections).

Reads only the ``source-bitmap-v1`` export: combined ``*-candidate.ttf``
fonts (whose preserved outlines equal the source outlines), per-face
``*-bitmap.json`` final-raster records, and ``report.json`` admitted cases
(status ``retained`` or ``changed``). No earlier checkpoint inputs.

For every admitted case this measures horizontal and vertical reflection
symmetry three ways: sampled actual source outline, sampled fitted
(final native) outline, and current raster mismatch. Detailed rigid-shift
analysis runs for target cases only (see the adapter section).

Geometry helpers below accept coordinates, outlines, scales, sample
arrays and ink sets only: no character, font-family, size or case
identity. All case selection lives in the adapter (``run`` and helpers
marked ADAPTER).

RIGID phase search translates whole outlines (then individual
vertically-separated source-coaxial components) over
-0.5/-0.25/0/+0.25/+0.5 px horizontally only (no y motion) and
re-renders with the same hinted baseline flags, so shape is preserved
by construction and only pixel phase changes. Nothing here is a
correction or promotion: previews are labelled diagnostic, and
unchanged renders are never relabeled as candidates.

Usage from the repository root::

    OPENBLAS_NUM_THREADS=1 PYTHONPATH=tools/font_probe \\
        tools/font_probe/.venv/bin/python tools/font_probe/audit_axis_placement.py
"""

import inspect
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SRC_DIR = HERE / 'out' / 'source-bitmap-v1'
SRC_CONSTRAINTS = HERE / 'out' / 'source-bitmap-constraints-v2'
OUT_NAME = 'axis-placement-audit-v1'
OUT_AUDIT_V2 = 'axis-placement-audit-v2'
OUT_CANDIDATE_V1 = 'axis-placement-candidate-v1'
OUT_CANDIDATE_V2 = 'axis-placement-candidate-v2'

PHASES = (-0.5, -0.25, 0.0, 0.25, 0.5)
SAMPLE_STEP_PX = 0.25

# Experimental bounds for the generic horizontal phase rule (documented,
# not paper claims): component source reflection max residual, component
# coaxial offset from the source axis, ownership tolerance against
# current q, and native-coordinate agreement with the submitted shift.
REFLECTION_MAX_PX = 0.15
COAXIAL_MAX_PX = 0.15
OWNERSHIP_TOL_PX = 1 / 64
NATIVE_TOL_PX = 1 / 128
ORDER_TOL_PX = 1 / 64
EPS = 1e-9


# ---------------------------------------------------------------------------
# Geometry helpers (identity-free: coordinates/outlines/scales/samples only).
# ---------------------------------------------------------------------------

def _emit_line(pos, anchor, far, step):
    length = float(np.linalg.norm(far - anchor))
    count = max(1, int(np.ceil(length / step)))
    for k in range(1, count + 1):
        pos.append(anchor + (far - anchor) * (k / count))


def _emit_quad(pos, anchor, control, far, step):
    approx = float(np.linalg.norm(control - anchor) + np.linalg.norm(far - control))
    count = max(1, int(np.ceil(approx / step)))
    for k in range(1, count + 1):
        t = k / count
        pos.append((1 - t) ** 2 * anchor + 2 * (1 - t) * t * control + t ** 2 * far)


def sample_closed_contour(contour_points, contour_flags, step):
    """Sample one closed TrueType contour, including off-curve interpolation."""
    pts = [np.asarray(p, float) for p in contour_points]
    on = [bool(f & 1) for f in contour_flags]
    n = len(pts)
    seq = []
    for i in range(n):
        seq.append((pts[i], on[i]))
        if not on[i] and not on[(i + 1) % n]:
            seq.append(((pts[i] + pts[(i + 1) % n]) / 2.0, True))
    starts = [i for i, (_, flag) in enumerate(seq) if flag]
    if not starts:
        return np.zeros((0, 2))
    seq = seq[starts[0]:] + seq[:starts[0]]
    pos = [seq[0][0].copy()]
    i = 1
    while i < len(seq):
        point, is_on = seq[i]
        if is_on:
            _emit_line(pos, pos[-1], point, step)
            i += 1
        else:
            far = seq[i + 1][0] if i + 1 < len(seq) else seq[0][0]
            _emit_quad(pos, pos[-1], point, far, step)
            i += 2
    # Closing segment back to the start anchor. (A trailing off-curve
    # node already closed to seq[0] inside the loop; only an on-curve
    # tail leaves the contour open.)
    if seq[-1][1]:
        _emit_line(pos, pos[-1], seq[0][0], step)
    return np.asarray(pos)


def sample_outline(points, ends, flags, scale, step=SAMPLE_STEP_PX):
    """Sampled actual outline in px: one sample array per contour."""
    scaled = np.asarray(points, float) * scale
    contours = []
    start = 0
    for end in ends:
        contours.append(sample_closed_contour(
            scaled[start:end + 1], flags[start:end + 1], step))
        start = end + 1
    return contours


def extent_of(coords):
    """Exact bounding box of coordinate rows: [xmin, ymin, xmax, ymax]."""
    arr = np.asarray(coords, float)
    return [float(arr[:, 0].min()), float(arr[:, 1].min()),
            float(arr[:, 0].max()), float(arr[:, 1].max())]


def boxes_of(coords, ends):
    """Exact per-contour bounding boxes in the same units as coords."""
    arr = np.asarray(coords, float)
    boxes, start = [], 0
    for end in ends:
        boxes.append(extent_of(arr[start:end + 1]))
        start = end + 1
    return boxes


def group_vertical(boxes, axis_center, tol=1e-9):
    """Group contours into vertically-separated components.

    Contours whose y-intervals overlap (transitively, so counters stay
    with their outer contour) belong to one component; y-disjoint
    contour sets are the vertically-separated units the per-component
    phase search moves individually. Each component reports its box,
    internal y-gaps, and coaxial offset of its x-center from the given
    source axis center.
    Returns a list of dicts with contour indices, box, y-gaps and
    coaxial offset, sorted bottom-up.
    """
    parent = list(range(len(boxes)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        parent[find(a)] = find(b)

    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if boxes[i][1] <= boxes[j][3] + tol and boxes[j][1] <= boxes[i][3] + tol:
                union(i, j)
    groups = {}
    for i in range(len(boxes)):
        groups.setdefault(find(i), []).append(i)
    components = []
    for members in groups.values():
        xs = [boxes[i][0] for i in members] + [boxes[i][2] for i in members]
        ys = [boxes[i][1] for i in members] + [boxes[i][3] for i in members]
        spans = sorted((boxes[i][1], boxes[i][3]) for i in members)
        gaps = [spans[k + 1][0] - spans[k][1] for k in range(len(spans) - 1)]
        box = [min(xs), min(ys), max(xs), max(ys)]
        components.append(dict(contours=sorted(members), box=box,
                               y_gaps=[float(g) for g in gaps],
                               coaxial_offset=round((box[0] + box[2]) / 2.0
                                                    - axis_center, 4)))
    return sorted(components, key=lambda c: (c['box'][1], c['box'][0]))


def reflect_array(coords, axis, center):
    """Mirror coordinate rows about a vertical (axis 'x') or horizontal axis."""
    arr = np.asarray(coords, float).copy()
    column = 0 if axis == 'x' else 1
    arr[:, column] = 2.0 * center - arr[:, column]
    return arr


def symmetry_error(contours, axis, center, chunk=256):
    """Distance of axis-reflected samples to the nearest outline segment.

    Translation-invariant for whole-outline moves about their own
    center; pixel-phase effects appear only in the raster measurement.
    """
    full = np.concatenate([c for c in contours if len(c)], axis=0) \
        if any(len(c) for c in contours) else np.zeros((0, 2))
    if not len(full):
        return dict(n=0, max=0.0, mean=0.0, rms=0.0)
    mirrored = reflect_array(full, axis, center)
    segs_a, segs_b = [], []
    for contour in contours:
        if len(contour) < 2:
            continue
        segs_a.append(contour)
        segs_b.append(np.roll(contour, -1, axis=0))
    node_a = np.concatenate(segs_a, axis=0)
    node_b = np.concatenate(segs_b, axis=0)
    edge = node_b - node_a
    denom = np.einsum('ij,ij->i', edge, edge)
    denom[denom == 0.0] = 1.0
    best = np.full(len(mirrored), np.inf)
    for lo in range(0, len(mirrored), chunk):
        block = mirrored[lo:lo + chunk]
        param = np.einsum('rsj,sj->rs', block[:, None, :] - node_a[None, :, :],
                          edge) / denom
        param = np.clip(param, 0.0, 1.0)
        proj = node_a[None, :, :] + param[:, :, None] * edge[None, :, :]
        dist = np.linalg.norm(block[:, None, :] - proj, axis=2)
        best[lo:lo + chunk] = dist.min(axis=1)
    return dict(n=int(len(full)), max=float(best.max()),
                mean=float(best.mean()), rms=float(np.sqrt((best ** 2).mean())))


def stroke_levels(contours, axis, band=0.1):
    """Orthogonal stroke coordinate levels from near-axis-parallel tangents.

    For a vertical mirror axis ('x') this clusters the x positions of
    near-vertical outline runs (vertical stems); for 'y' the y positions
    of near-horizontal runs. Returns cluster centers with span and weight.
    """
    column = 0 if axis == 'x' else 1
    values = []
    for contour in contours:
        if len(contour) < 3:
            continue
        delta = np.diff(np.vstack([contour, contour[:1]]), axis=0)
        if axis == 'x':
            pick = np.abs(delta[:, 1]) > np.abs(delta[:, 0])
        else:
            pick = np.abs(delta[:, 0]) > np.abs(delta[:, 1])
        values.extend(contour[pick][:, column].tolist())
    values = sorted(values)
    clusters = []
    for value in values:
        if clusters and value - clusters[-1]['values'][-1] <= band:
            clusters[-1]['values'].append(value)
        else:
            clusters.append({'values': [value]})
    return [dict(center=round(float(np.mean(c['values'])), 3),
                 span=round(float(max(c['values']) - min(c['values'])), 3),
                 weight=len(c['values'])) for c in clusters]


def mirror_ink(ink, axis, center):
    """Mirror an integer pixel set about an axis center (involution)."""
    out = set()
    for x, y in ink:
        if axis == 'x':
            out.add((int(np.floor(2.0 * center - x - 1.0 + 0.5)), y))
        else:
            out.add((x, int(np.floor(2.0 * center - y - 1.0 + 0.5))))
    return out


def ink_mismatch(ink, axis, center):
    """Raster symmetry mismatch between an ink set and its mirror."""
    mirrored = mirror_ink(ink, axis, center)
    diff = ink ^ mirrored
    rate = len(diff) / max(1, len(ink | mirrored))
    return dict(mismatch=len(diff), ink=len(ink), rate=round(rate, 4))


def ink_box_of(ink):
    """Edge bounding box of an integer pixel set (max edge = max + 1)."""
    ink = list(ink)
    if not ink:
        return None
    xs = [p[0] for p in ink]
    ys = [p[1] for p in ink]
    return [min(xs), min(ys), max(xs) + 1, max(ys) + 1]


def ink_axis_center(box, axis):
    """Pixel-span mirror center in ink space: (lo + hi + 1) / 2.

    Ink-space centers (bitmap coordinates) must be used for raster
    mirroring; outline-space centers live in a different frame
    (notably y-up vs y-down) and would fake asymmetry on one axis.
    """
    column = (0, 2) if axis == 'x' else (1, 3)
    return (box[column[0]] + box[column[1]]) / 2.0


def shift_coords(coords, delta_x, delta_y):
    """Rigid translation of coordinate rows; shape preserved by construction."""
    return np.asarray(coords, float) + np.array([delta_x, delta_y])


def assert_geometry_identity_free():
    """ADAPTER guard: geometry helpers take no glyph/font/case identity."""
    forbidden = {'char', 'character', 'font', 'family', 'face', 'size',
                 'ppem', 'key', 'glyph', 'case'}
    geometry = [sample_closed_contour, sample_outline, extent_of, boxes_of,
                group_vertical, reflect_array, symmetry_error, stroke_levels,
                mirror_ink, ink_mismatch, shift_coords, ink_box_of,
                ink_axis_center, _emit_line, _emit_quad,
                _whole_eligible, _candidate_units, _order_preserved_hold]
    offenders = []
    for func in geometry:
        params = set(inspect.signature(func).parameters)
        clash = params & forbidden
        if clash:
            offenders.append((func.__name__, sorted(clash)))
    if offenders:
        raise ValueError(f'geometry helpers take identity: {offenders}')


# ---------------------------------------------------------------------------
# Report adapter (case selection lives here only).
# ---------------------------------------------------------------------------

# ADAPTER: the only place target identity is selected.
TARGET_CHARS = ('+', 'T', '!')
TARGET_FOCUS_AXES = {'T': ('x',), '+': ('x', 'y'), '!': ('x',)}
ADMITTED_STATUSES = ('retained', 'changed')

# Constraint provenance: ``build_source_bitmap.Pipeline.export`` stores the
# finalize audit on the report row (``audit``) and the cumulative audit
# carrying ``ownership`` and ``order_relations`` alongside it
# (``upstream_audit``). The candidate rule below reads ownership/order
# from ``upstream_audit`` only. A past export bug stamped every row with
# the last character's audit (stale loop variable); it was fixed to a
# per-character lookup and the constraints report regenerated as
# ``source-bitmap-constraints-v2`` (v1 is unusable for ownership work).
OWNERSHIP_RECOVERY = {
    'cause': ("Pipeline.export stores the finalize() audit "
              "({'stage', 'operations'}) on the report row under 'audit'; "
              "the cumulative audit ({'ownership', 'order_relations', "
              "'geometric_stages', ...}) rides alongside as "
              "'upstream_audit'."),
    'minimal_change': ("In build_source_bitmap.py export(): stamp "
                       "`upstream_audit=deepcopy(live[char]['audit'])` "
                       "per character (never a leftover loop binding)."),
    'fields_read_from_upstream_audit': ['ownership', 'order_relations'],
}


def _admitted_cases(report):
    """ADAPTER: admitted cases from the source-bitmap-v1 report."""
    return [c for c in report['cases'] if c.get('status') in ADMITTED_STATUSES]


def _is_target(key, char, _report):
    """ADAPTER: target predicate (+, T, ! across all faces/sizes)."""
    return char in TARGET_CHARS


def _axis_center(box, axis):
    column = (0, 2) if axis == 'x' else (1, 3)
    return (box[column[0]] + box[column[1]]) / 2.0


def _measure_axes(source_contours, fitted_contours, source_box, fitted_box,
                  ink, axes=('x', 'y')):
    """ADAPTER: generic both-axes measurement for one admitted case."""
    box = ink_box_of(ink)
    row = {}
    for axis in axes:
        source_center = _axis_center(source_box, axis)
        fitted_center = _axis_center(fitted_box, axis)
        raster_center = ink_axis_center(box, axis) if box else 0.0
        row[axis] = dict(
            source_center=round(source_center, 4),
            fitted_center=round(fitted_center, 4),
            raster_center=round(raster_center, 4),
            axis_phase=round(raster_center % 1.0, 4),
            source_outline=symmetry_error(source_contours, axis, source_center),
            fitted_outline=symmetry_error(fitted_contours, axis, fitted_center),
            raster=ink_mismatch(ink, axis, raster_center) if box
            else dict(mismatch=0, ink=0, rate=0.0),
        )
    return row


def _render_shifted(face, char, size, fitted, delta, hinted=True):
    """ADAPTER: re-render rigid-shifted fitted points (shape preserved).

    Uses the same hinted baseline flags as the source-bitmap export: an
    unhinted re-render changes the zero-shift bitmap (parent finding:
    Literata14 T 1px, SourceSans16 +3px, SourceSans20 +4px), while
    hinted=True reproduces the stored records exactly.
    """
    from compare_paper_prototypes import render, pixels
    glyph = render(face, char, size,
                   points=shift_coords(fitted, *delta), hinted=hinted)
    return glyph, pixels(glyph)


def _counters(ink, fitted, source_px):
    """ADAPTER: ink/counter metrics for a rendered phase."""
    from compare_diagonal_widths import metrics
    info = metrics(ink, np.asarray(fitted, float), np.asarray(source_px, float))
    return dict(ink=len(ink), white_counters=info['white_counters'],
                bbox=info['bbox'])


def _trial_deltas():
    """ADAPTER: horizontal-only rigid trial shifts (no y motion)."""
    return [(dx, 0.0) for dx in PHASES]


def _phase_grid_search(face, char, size, fitted, source_px, axis,
                       point_ids=None):
    """ADAPTER: rigid horizontal phase search; returns baseline, trials, best.

    ``point_ids`` restricts the shift to one component (others exact);
    None shifts the whole outline. Renders reuse the hinted baseline
    flags so only pixel phase varies.
    """
    base_glyph, base_ink = _render_shifted(face, char, size, fitted, (0.0, 0.0))
    base_box = ink_box_of(base_ink)
    base_center = ink_axis_center(base_box, axis) if base_box else 0.0
    baseline = dict(raster=ink_mismatch(base_ink, axis, base_center),
                    counters=_counters(base_ink, fitted, source_px))
    trials = []
    ids = None if point_ids is None else list(point_ids)
    for delta_x, delta_y in _trial_deltas():
        moved = np.asarray(fitted, float).copy()
        shift = np.array([delta_x, delta_y])
        moved[ids if ids is not None else slice(None)] += shift
        glyph, ink = _render_shifted(face, char, size, moved, (0.0, 0.0))
        trial_box = ink_box_of(ink)
        moved_center = ink_axis_center(trial_box, axis) if trial_box else 0.0
        mismatch = ink_mismatch(ink, axis, moved_center)
        trials.append(dict(delta=[delta_x, delta_y],
                           raster=mismatch,
                           counters=_counters(ink, moved, source_px)))
    order = sorted(trials, key=lambda t: (t['raster']['mismatch'],
                                          abs(t['delta'][0]) + abs(t['delta'][1]),
                                          abs(t['counters']['ink']
                                              - baseline['counters']['ink'])))
    best = order[0]
    improved = best['raster']['mismatch'] < baseline['raster']['mismatch']
    eliminated = improved and best['raster']['mismatch'] == 0
    return dict(axis=axis, baseline=baseline, best=best,
                improved=improved, eliminated=eliminated,
                n_trials=len(trials),
                best_ink_delta=best['counters']['ink'] - baseline['counters']['ink'],
                best_counter_delta=(best['counters']['white_counters']
                                    - baseline['counters']['white_counters']))


def _target_detail(face, char, size, fitted, source_px, source_box,
                   fitted_box, source_contours, fitted_contours,
                   components, axes):
    """ADAPTER: target-only detail (extents, levels, boxes, phase search)."""
    detail = dict(
        source_extent=[round(v, 3) for v in source_box],
        fitted_extent=[round(v, 3) for v in fitted_box],
        stroke_levels={axis: stroke_levels(source_contours, axis)
                       for axis in ('x', 'y')},
        components=components,
        axes={},
    )
    for axis in axes:
        entry = dict(
            whole=_phase_grid_search(face, char, size, fitted, source_px, axis))
        comp_results = []
        # Per-component point ids ride on components (attached by the
        # adapter in run()); geometry helpers never see case identity.
        for index, comp in enumerate(components):
            comp_results.append(dict(
                component=index, contours=comp['contours'],
                result=_phase_grid_search(
                    face, char, size, fitted, source_px, axis,
                    point_ids=comp['point_ids'])))
        entry['components'] = comp_results
        detail['axes'][axis] = entry
    return detail


def _is_deferred(char):
    """ADAPTER: percentage output stays baseline: evaluate, never promote."""
    return char == '%'


def _component_point_ids(ends):
    """ADAPTER: point index ranges per contour."""
    ids, start = [], 0
    for end in ends:
        ids.append(list(range(start, end + 1)))
        start = end + 1
    return ids


def _eligible_components(source_px, ends, source_contours, axis_center):
    """ADAPTER: source-coaxial, source-symmetric x components.

    Counter contours group with their enclosing outline through the
    transitive y-overlap in ``group_vertical``. A component qualifies
    when its box x-center is within COAXIAL_MAX_PX of the source axis
    and its actual sampled horizontal source reflection max residual is
    within REFLECTION_MAX_PX (experimental thresholds, not paper
    claims). Single-component near-symmetric glyphs qualify the same
    way (their offset is zero by construction).
    """
    boxes = boxes_of(np.asarray(source_px, float), list(ends))
    qualified = []
    for comp in group_vertical(boxes, float(axis_center)):
        if abs(comp['coaxial_offset']) > COAXIAL_MAX_PX + EPS:
            continue
        samples = [source_contours[i] for i in comp['contours']
                   if i < len(source_contours) and len(source_contours[i])]
        if not samples:
            continue
        center = (comp['box'][0] + comp['box'][2]) / 2.0
        residual = symmetry_error(samples, 'x', center)['max']
        if residual > REFLECTION_MAX_PX + EPS:
            continue
        qualified.append(dict(comp, reflection_max=round(residual, 4)))
    return qualified


def _whole_eligible(source_contours, axis_center):
    """Whole-outline eligibility from actual sampled source reflection.

    The whole glyph shifts only when the full sampled source outline
    reflected about its own x-center has max residual within
    REFLECTION_MAX_PX. Asymmetric sources never get a whole-shift unit;
    their components qualify separately via ``_eligible_components``.
    Identity-free: sample arrays and a center only.
    """
    samples = [c for c in source_contours if len(c)]
    if not samples:
        return False, None
    residual = symmetry_error(samples, 'x', float(axis_center))['max']
    return residual <= REFLECTION_MAX_PX + EPS, round(residual, 4)


def _candidate_units(source_px, ends, source_contours, axis_center):
    """Shift units for the candidate rule (identity-free).

    Returns (units, eligible, whole_eligible, whole_reflection_max):
    ``units`` holds ('whole', None) only when the whole sampled source
    qualifies, plus one entry per source-coaxial, source-symmetric
    component. Each component entry carries its sorted point ids.
    """
    whole_ok, whole_residual = _whole_eligible(source_contours, axis_center)
    eligible = _eligible_components(source_px, ends, source_contours,
                                    axis_center)
    by_contour = _component_point_ids(list(ends))
    units = [('whole', None)] if whole_ok else []
    for comp in eligible:
        ids = sorted(i for c in comp['contours'] for i in by_contour[c])
        units.append((f"component@{','.join(str(c) for c in comp['contours'])}",
                      ids))
    return units, eligible, whole_ok, whole_residual


def _order_preserved_hold(candidate, current, order_relations):
    """ADAPTER-adjacent hold: per-relation differences stay at current values.

    For each relation (a, b, axis) the candidate difference
    ``candidate[b,axis]-candidate[a,axis]`` must equal the CURRENT
    difference within ORDER_TOL_PX. This preserves the existing relation
    conservatively; it never forces the historical source ``value``.
    Returns (held, worst_px, relation_or_None). Identity-free: arrays
    and relation rows only.
    """
    worst = 0.0
    cand = np.asarray(candidate, float)
    cur = np.asarray(current, float)
    for rel in order_relations or ():
        axis = int(rel['axis'])
        before = float(cur[int(rel['b']), axis] - cur[int(rel['a']), axis])
        after = float(cand[int(rel['b']), axis] - cand[int(rel['a']), axis])
        move = abs(after - before)
        worst = max(worst, move)
        if move > ORDER_TOL_PX + EPS:
            return True, round(worst, 4), dict(a=int(rel['a']),
                                               b=int(rel['b']), axis=axis,
                                               move_px=round(move, 4))
    return False, round(worst, 4), None


def _ownership_hold(candidate, current, ownership):
    """ADAPTER: owned point-axis values stay within rounding of current q.

    Any trial moving an owned coordinate on its owned axis beyond
    OWNERSHIP_TOL_PX is held, never bypassed. Returns (held, worst_px).
    """
    worst = 0.0
    for entry in ownership or ():
        move = abs(float(candidate[int(entry['point']), int(entry['axis'])])
                   - float(current[int(entry['point']), int(entry['axis'])]))
        worst = max(worst, move)
        if move > OWNERSHIP_TOL_PX + EPS:
            return True, round(worst, 4)
    return False, round(worst, 4)


def _ownership_sanity(current, ownership):
    """ADAPTER diagnostic: recorded audit values vs current q (not a gate)."""
    worst = 0.0
    for entry in ownership or ():
        worst = max(worst, abs(float(current[int(entry['point']),
                                             int(entry['axis'])])
                               - float(entry['value'])))
    return round(worst, 4)


def _order_hold(source_px, candidate, ends, flags):
    """ADAPTER: existing cardinal-edge check; rigid moves preserve order."""
    from outline_relationships import reversed_edges
    return bool(reversed_edges(np.asarray(source_px, float),
                               np.asarray(candidate, float),
                               list(ends), list(flags)))


def _evaluate_case(face, char, size, fitted, source_px, ends, flags,
                   source_contours, upstream):
    """ADAPTER: generic horizontal candidate rule with protections.

    The whole glyph shifts only when its sampled source reflection
    qualifies; otherwise one eligible component at a time; all other
    coordinates exact. Acceptance needs zero candidate full-raster
    x mismatch, preserved advance, preserved raster bbox dimensions,
    preserved white-counter count, ink area within max(1px, 5%) of
    current, owned values within rounding, per-relation differences at
    their current values, and no cardinal edge inversion. Ranking is
    least movement, then least ink change. Selection here is
    unverified: run_candidate() exports the selected coordinates with
    the real compile adapter and only keeps rows whose actual export
    agrees. Holds record the first blocking protection honestly.
    """
    current = np.asarray(fitted, float)
    _, base_ink = _render_shifted(face, char, size, current, (0.0, 0.0))
    base_box = ink_box_of(base_ink)
    base_center = ink_axis_center(base_box, 'x') if base_box else 0.0
    base_mm = ink_mismatch(base_ink, 'x', base_center)['mismatch'] if base_box else None
    base_info = _counters(base_ink, current, source_px)
    base_dims = [base_info['bbox'][2] - base_info['bbox'][0],
                 base_info['bbox'][3] - base_info['bbox'][1]]
    ownership = (upstream or {}).get('ownership', ()) or ()
    order_relations = (upstream or {}).get('order_relations', ()) or ()
    diag = dict(baseline_mismatch=base_mm, baseline_ink=int(base_info['ink']),
                baseline_counters=int(base_info['white_counters']),
                ownership_entries=len(ownership),
                ownership_audit_vs_current_px=_ownership_sanity(current, ownership),
                order_relations=len(order_relations))
    deferred = _is_deferred(char)
    if not base_box:
        return dict(status='deferred' if deferred else 'held',
                    reason='deferred-percentage' if deferred else 'empty raster',
                    unit=None, dx=0.0, **diag)
    if base_mm == 0:
        return dict(status='deferred' if deferred else 'no-change',
                    reason='deferred-percentage' if deferred else 'x symmetry already zero',
                    unit=None, dx=0.0, **diag)
    source_box = extent_of(np.asarray(source_px, float))
    source_center = (source_box[0] + source_box[2]) / 2.0
    units, eligible, whole_ok, whole_residual = _candidate_units(
        source_px, ends, source_contours, source_center)
    diag['eligible_units'] = [u for u, _ in units]
    diag['whole_eligible'] = whole_ok
    diag['whole_reflection_max_px'] = whole_residual
    accepted, holds = [], []
    for unit, ids in units:
        for dx, dy in _trial_deltas():
            if dx == 0.0:
                continue
            moved = current.copy()
            moved[ids if ids is not None else slice(None)] += np.array([dx, dy])
            hold, worst = _ownership_hold(moved, current, ownership)
            if hold:
                holds.append(f'{unit}@{dx}: ownership move {worst}px')
                continue
            if _order_hold(source_px, moved, ends, flags):
                holds.append(f'{unit}@{dx}: cardinal edge inversion')
                continue
            order_hold, worst, rel = _order_preserved_hold(
                moved, current, order_relations)
            if order_hold:
                holds.append(
                    f"{unit}@{dx}: order relation drift "
                    f"a{rel['a']}->b{rel['b']} axis{rel['axis']} "
                    f"{rel['move_px']}px")
                continue
            _, ink = _render_shifted(face, char, size, moved, (0.0, 0.0))
            box = ink_box_of(ink)
            center = ink_axis_center(box, 'x') if box else 0.0
            mm = ink_mismatch(ink, 'x', center)['mismatch'] if box else None
            if mm != 0:
                holds.append(f'{unit}@{dx}: raster x mismatch {mm}')
                continue
            info = _counters(ink, moved, source_px)
            if [info['bbox'][2] - info['bbox'][0],
                    info['bbox'][3] - info['bbox'][1]] != base_dims:
                holds.append(f'{unit}@{dx}: raster bbox dimensions changed')
                continue
            if info['white_counters'] != base_info['white_counters']:
                holds.append(f'{unit}@{dx}: counter topology changes')
                continue
            ink_delta = int(info['ink']) - int(base_info['ink'])
            if abs(ink_delta) > max(1, 0.05 * base_info['ink']):
                holds.append(f'{unit}@{dx}: ink area {ink_delta:+d}px')
                continue
            accepted.append(dict(unit=unit, dx=dx, ink_delta=ink_delta,
                                 white_counters=int(info['white_counters']),
                                 point_ids=ids))
    accepted.sort(key=lambda a: (abs(a['dx']), abs(a['ink_delta'])))
    if deferred:
        best = accepted[0] if accepted else None
        return dict(status='deferred', reason='deferred-percentage',
                    unit=best['unit'] if best else None,
                    dx=best['dx'] if best else 0.0,
                    ink_delta=best['ink_delta'] if best else 0,
                    would_accept=best is not None, n_holds=len(holds),
                    first_holds=holds[:4], **diag)
    if not accepted:
        return dict(status='held',
                    reason=holds[0] if holds else 'no eligible unit',
                    unit=None, dx=0.0, n_holds=len(holds),
                    first_holds=holds[:4], **diag)
    best = accepted[0]
    return dict(status='accepted', reason='human review', unit=best['unit'],
                dx=best['dx'], ink_delta=best['ink_delta'],
                white_counters=best['white_counters'],
                point_ids=best['point_ids'], n_holds=len(holds),
                first_holds=holds[:4], **diag)


def _preview_png(face, char, size, key, fitted, moved, tag, out_path):
    """ADAPTER: focused source/current/proposed diagnostic preview.

    Diagnostic only: reuses the existing smooth-reference/comparison
    helpers; never a correction or promotion. ``moved`` holds the full
    proposed coordinates (whole or single-component shift).
    """
    from compare_shamir_representatives import comparison
    from serif_reference_view import prepend_reference
    current, _ = _render_shifted(face, char, size, fitted, (0.0, 0.0))
    proposed, _ = _render_shifted(face, char, size, moved, (0.0, 0.0))
    # comparison() and prepend_reference() both draw the title at the
    # same offset: pass identical short titles so the overdraw is exact.
    title = f'{key} {char!r} diagnostic'
    panel = comparison(
        [current, proposed],
        ['Current hinted', f'Proposed {tag}'],
        title)
    prepend_reference(face, char, size, title, [current, proposed],
                      panel).save(out_path)


def _preview_exported_png(face, char, size, key, fitted, tag, out_path,
                          exported_face):
    """ADAPTER: preview the actual exported candidate glyph.

    Unlike ``_preview_png`` (which re-renders proposed coordinates),
    this draws the render of the real exported font, so the preview is
    evidence of what the compile adapter actually produced.
    """
    from compare_paper_prototypes import render
    from compare_shamir_representatives import comparison
    from serif_reference_view import prepend_reference
    current, _ = _render_shifted(face, char, size, fitted, (0.0, 0.0))
    proposed = render(exported_face, char, size, hinted=True)
    title = f'{key} {char!r} diagnostic'
    panel = comparison(
        [current, proposed],
        ['Current hinted', f'Exported {tag}'],
        title)
    prepend_reference(face, char, size, title, [current, proposed],
                      panel).save(out_path)


def _verify_candidate_export(ref_path, char, size, outline_points, em,
                             moved, selected_glyph, selected_ink,
                             base_info, base_dims, target_path):
    """ADAPTER: export selected coordinates and verify actual agreement.

    Compiles ``moved`` with the real compile adapter
    (``compare_diagonal_widths.build`` over ``export_graph``) into
    ``target_path``, then checks the ACTUAL export: returned native
    coordinates within NATIVE_TOL_PX of the selected coordinates,
    rendered bitmap exactly equal to the selected moved raster
    (``selected_ink``), hmtx and hinted advance unchanged, and the
    same zero-mismatch / counter-topology / bbox-dimension gates
    (against the current ``base_info``/``base_dims``) recomputed from
    the actual export. A compile failure is an honest hold, never a
    pass. Returns a dict with ``verified`` plus exact evidence (or the
    hold reason).
    """
    from fontTools.ttLib import TTFont
    from compare_diagonal_widths import build
    from compare_paper_prototypes import pixels
    from cross_section_widths import export_graph
    moved = np.asarray(moved, float)
    with TTFont(str(ref_path)) as font:
        base_hmtx = font['hmtx'][font.getBestCmap()[ord(char)]]
    try:
        exported_glyph, actual = build(
            str(ref_path), char, size, np.asarray(outline_points, float),
            export_graph(moved, size / em), str(target_path))
    except Exception as exc:
        return dict(verified=False,
                    reason=f'export compile failed: {exc}')
    drift = float(np.max(abs(np.asarray(actual, float) - moved)))
    exported_ink = pixels(exported_glyph)
    evidence = dict(native_drift_px=round(drift, 4),
                    bitmap_exact=exported_ink == set(selected_ink),
                    bitmap_delta=len(exported_ink ^ set(selected_ink)),
                    advance_unchanged=(exported_glyph['advance_26_6']
                                       == selected_glyph['advance_26_6']),
                    exported_advance_26_6=exported_glyph['advance_26_6'])
    with TTFont(str(target_path)) as font:
        evidence['hmtx_unchanged'] = (
            font['hmtx'][font.getBestCmap()[ord(char)]] == base_hmtx)
    box = ink_box_of(exported_ink)
    evidence['raster_mismatch'] = (
        ink_mismatch(exported_ink, 'x', ink_axis_center(box, 'x'))['mismatch']
        if box else None)
    # Counter/bbox gates depend on the ink only; points are unused there.
    info = _counters(exported_ink, np.asarray(actual, float),
                     np.asarray(actual, float))
    evidence['white_counters'] = int(info['white_counters'])
    evidence['bbox_dims'] = [info['bbox'][2] - info['bbox'][0],
                             info['bbox'][3] - info['bbox'][1]]
    if drift > NATIVE_TOL_PX + EPS:
        return dict(evidence, verified=False,
                    reason=f'export native drift {drift:.4f}px')
    if not evidence['bitmap_exact']:
        return dict(evidence, verified=False,
                    reason=f"export bitmap differs "
                           f"({evidence['bitmap_delta']}px)")
    if not evidence['advance_unchanged'] or not evidence['hmtx_unchanged']:
        return dict(evidence, verified=False,
                    reason='export advance/hmtx changed')
    if evidence['raster_mismatch'] != 0:
        return dict(evidence, verified=False,
                    reason=f"export raster x mismatch "
                           f"{evidence['raster_mismatch']}")
    if evidence['white_counters'] != base_info['white_counters']:
        return dict(evidence, verified=False,
                    reason='export counter topology changes')
    if evidence['bbox_dims'] != base_dims:
        return dict(evidence, verified=False,
                    reason='export raster bbox dimensions changed')
    evidence['export_font'] = Path(target_path).name
    return dict(evidence, verified=True, reason='export agrees')


def _load_inputs(src_dir):
    """ADAPTER: admitted cases, faces, bitmap records and source outlines."""
    import freetype as ft
    from fontTools.ttLib import TTFont
    report = json.loads((src_dir / 'report.json').read_text())
    admitted = _admitted_cases(report)
    faces, records, outlines = {}, {}, {}
    for face_file in sorted(src_dir.glob('*-candidate.ttf')):
        key = face_file.stem.removesuffix('-candidate')
        size = int(key.rsplit('-', 1)[1])
        faces[key] = ft.Face(str(face_file))
        data = json.loads((src_dir / f'{key}-bitmap.json').read_text())
        records[key] = {g['char']: g for g in data['glyphs'].values()} \
            if isinstance(data['glyphs'], dict) \
            else {g['char']: g for g in data['glyphs']}
        with TTFont(str(face_file)) as font:
            em = font['head'].unitsPerEm
            cmap = font.getBestCmap()
            for char, record in records[key].items():
                name = cmap[ord(char)]
                points, ends, flags = font['glyf'][name].getCoordinates(font['glyf'])
                outlines[(key, char)] = (np.asarray(points, float),
                                         list(ends), list(flags), em, size)
    return report, admitted, faces, records, outlines


def _verify_zero_shift(faces, records, outlines, admitted):
    """ADAPTER: hinted zero-shift re-render equals every stored record.

    Runs before any phase evaluation: the fitted coordinates re-rendered
    with the baseline hinted flags must reproduce the stored ink bitmap
    and advance exactly for all admitted cases.
    """
    bad = []
    for case in admitted:
        key, char = case['key'], case['char']
        if (key, char) not in outlines:
            bad.append((key, char, 'missing outline'))
            continue
        record = records[key][char]
        fitted = np.asarray(record['native_points_px'], float)
        glyph, ink = _render_shifted(faces[key], char, int(key.rsplit('-', 1)[1]),
                                     fitted, (0.0, 0.0))
        if ink != {(x, y) for x, y in record['ink']}:
            bad.append((key, char, 'ink'))
        elif glyph['advance_26_6'] != record['advance_26_6']:
            bad.append((key, char, 'advance'))
    if bad:
        raise ValueError(f'zero-shift parity failed for {len(bad)} cases: {bad[:8]}')
    return len(admitted)


def _fresh_output(output, default_name):
    output = Path(output) if output else HERE / 'out' / default_name
    if output.resolve().is_relative_to((HERE / 'out').resolve()) is False:
        raise ValueError('output must live under tools/font_probe/out')
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('output must be empty')
    (output / 'img').mkdir(exist_ok=True)
    return output


def run(output=None, src=None):
    """ADAPTER: run the diagnostic; own only the new output directory."""
    from check_shamir_baseline import digest
    assert_geometry_identity_free()
    src_dir = Path(src) if src else SRC_CONSTRAINTS
    output = _fresh_output(output, OUT_AUDIT_V2)

    report, admitted, faces, records, outlines = _load_inputs(src_dir)
    _verify_zero_shift(faces, records, outlines, admitted)

    generic, targets, previews = [], [], []
    for case in admitted:
        key, char = case['key'], case['char']
        if (key, char) not in outlines:
            continue
        points, ends, flags, em, size = outlines[(key, char)]
        scale = size / em
        record = records[key][char]
        fitted = np.asarray(record['native_points_px'], float)
        source_px = points * scale
        source_contours = sample_outline(points, ends, flags, scale)
        fitted_contours = sample_outline(
            fitted / scale, ends, flags, scale)
        source_box = extent_of(source_px)
        fitted_box = extent_of(fitted)
        ink = {(x, y) for x, y in record['ink']}
        row = dict(key=key, char=char, size=size, status=case.get('status'),
                   axes=_measure_axes(source_contours, fitted_contours,
                                      source_box, fitted_box, ink))
        generic.append(row)
        if not _is_target(key, char, report):
            continue
        boxes = boxes_of(source_px, ends)
        components = group_vertical(
            boxes, (source_box[0] + source_box[2]) / 2.0)
        # Attach point ids per component for the per-component search.
        point_ids, start = [], 0
        for end in ends:
            point_ids.append(list(range(start, end + 1)))
            start = end + 1
        for comp in components:
            comp['point_ids'] = sorted(i for c in comp['contours']
                                       for i in point_ids[c])
        face = faces[key]
        focus = TARGET_FOCUS_AXES[char]
        detail = _target_detail(face, char, size, fitted, source_px,
                                source_box, fitted_box, source_contours,
                                fitted_contours, components, focus)
        best = detail['axes'][focus[0]]['whole']['best']['delta']
        stem = f'{key}-u{ord(char):04x}'
        _preview_png(face, char, size, key, fitted,
                     shift_coords(fitted, *best), f'rigid {best}',
                     output / 'img' / f'{stem}.png')
        previews.append(f'{stem}.png')
        targets.append(dict(key=key, char=char, size=size,
                            status=case.get('status'),
                            focus_axes=list(focus),
                            generic=row['axes'], detail=detail,
                            preview=f'img/{stem}.png'))

    ownership_fields = dict(
        row_keys=sorted({k for c in admitted for k in c}),
        audit_keys=sorted({k for c in admitted
                           for k in (c.get('audit') or {})}),
        upstream_keys=sorted({k for c in admitted
                              for k in (c.get('upstream_audit') or {})}),
        note=('row audit holds the finalize audit '
              "({'stage', 'operations'}); the cumulative audit with "
              'ownership/order_relations rides alongside as upstream_audit.'),
    )
    payload = dict(
        summary=dict(admitted=len(generic), targets=len(targets),
                     focus={c: list(TARGET_FOCUS_AXES[c]) for c in TARGET_CHARS},
                     note=('Target axes (T x-only; + x/y; ! x-diagnostic) '
                           'are diagnostic focus only. Generic both-axes '
                           'measurements cover all admitted glyphs; '
                           'horizontal-only phase grids reuse the hinted '
                           'baseline flags. Intentional asymmetry is not '
                           'relabeled. Previews are diagnostic, never '
                           'candidates.')),
        inputs={str(src_dir.relative_to(HERE)) + '/report.json':
                digest(src_dir / 'report.json')},
        ownership_fields=ownership_fields,
        ownership_recovery=OWNERSHIP_RECOVERY,
        targets=targets,
        generic=generic,
    )
    (output / 'report.json').write_text(json.dumps(payload, indent=1) + '\n')
    _write_summary(output, targets)
    _write_index(output, targets)
    print(f'admitted={len(generic)} targets={len(targets)} -> {output}')
    return payload


def run_candidate(output=None, src=None):
    """ADAPTER: generic horizontal candidate pass over all admitted cases.

    Reads ownership/order from the constraints report only. Accepted
    rows are for human review, never promotions; percentage cases are
    evaluated for coverage but deferred, never promoted. A selected
    candidate is accepted only when its ACTUAL compile-adapter export
    agrees (native coordinates, exact bitmap, advance/hmtx, and the
    symmetry/counter/bbox gates); compile failures and drift hold.
    """
    import freetype as ft
    from collections import Counter
    from check_shamir_baseline import digest
    assert_geometry_identity_free()
    src_dir = Path(src) if src else SRC_CONSTRAINTS
    output = _fresh_output(output, OUT_CANDIDATE_V2)

    report, admitted, faces, records, outlines = _load_inputs(src_dir)
    _verify_zero_shift(faces, records, outlines, admitted)

    cases, accepted, focus = [], [], []
    for case in admitted:
        key, char = case['key'], case['char']
        if (key, char) not in outlines:
            continue
        points, ends, flags, em, size = outlines[(key, char)]
        scale = size / em
        record = records[key][char]
        fitted = np.asarray(record['native_points_px'], float)
        source_px = points * scale
        source_contours = sample_outline(points, ends, flags, scale)
        result = _evaluate_case(faces[key], char, size, fitted, source_px,
                                ends, flags, source_contours,
                                case.get('upstream_audit'))
        row = dict(key=key, char=char, size=size,
                   upstream=case.get('status'), **result)
        cases.append(row)
        if result['status'] == 'accepted':
            moved = fitted.copy()
            ids = result['point_ids']
            moved[ids if ids is not None else slice(None)] += np.array([result['dx'], 0.0])
            tag = f"{result['unit']}@{result['dx']:+g}px"
            stem = f'{key}-u{ord(char):04x}'
            _, base_ink = _render_shifted(
                faces[key], char, size, fitted, (0.0, 0.0))
            moved_glyph, moved_ink = _render_shifted(
                faces[key], char, size, moved, (0.0, 0.0))
            base_info = _counters(base_ink, fitted, source_px)
            base_dims = [base_info['bbox'][2] - base_info['bbox'][0],
                         base_info['bbox'][3] - base_info['bbox'][1]]
            target_path = output / f'{stem}-axis-candidate.ttf'
            proof = _verify_candidate_export(
                src_dir / f'{key}-candidate.ttf', char, size, points, em,
                moved, moved_glyph, moved_ink, base_info, base_dims,
                target_path)
            if not proof['verified']:
                if target_path.exists():
                    target_path.unlink()
                holds = row.get('first_holds', [])
                row.update(status='held',
                           reason=f"export hold: {proof['reason']}",
                           n_holds=row.get('n_holds', 0) + 1,
                           first_holds=[f"export hold: {proof['reason']}"]
                           + holds[:3])
                row['export_hold'] = {k: v for k, v in proof.items()
                                      if k != 'verified'}
                row.pop('point_ids', None)
            else:
                exported_face = ft.Face(str(target_path))
                _preview_exported_png(faces[key], char, size, key, fitted,
                                      tag, output / 'img' / f'{stem}.png',
                                      exported_face)
                row['preview'] = f'img/{stem}.png'
                row['tag'] = tag
                row['export_verified'] = True
                row['export_proof'] = {k: v for k, v in proof.items()
                                       if k != 'verified'}
                accepted.append(row)
        if _is_target(key, char, report):
            focus.append(row)

    counts = dict(Counter(r['status'] for r in cases))
    payload = dict(
        summary=dict(admitted=len(cases), counts=counts,
                     focus=len(focus), accepted=len(accepted),
                     note=('Generic horizontal rigid phase only '
                           '(dx in [-0.5..0.5], no y motion). The whole '
                           'glyph shifts only when its sampled source '
                           'reflection qualifies; components qualify '
                           'separately. Accepted rows are for human review, '
                           'never promotions, and each carries export_proof '
                           'from its actual compile-adapter export (exact '
                           'bitmap, native/advance/hmtx agreement, previews '
                           'draw the exported glyph). Percentage cases are '
                           'evaluated but deferred. Source qualification '
                           'and area bounds are conservative experimental '
                           'policy, not paper claims. Large ink changes, '
                           'order-relation drift, and export failures '
                           'are held.')),
        inputs={str(src_dir.relative_to(HERE)) + '/report.json':
                digest(src_dir / 'report.json')},
        rule=dict(deltas=list(PHASES), dy=0.0,
                  reflection_max_px=REFLECTION_MAX_PX,
                  coaxial_max_px=COAXIAL_MAX_PX,
                  ownership_tol_px=OWNERSHIP_TOL_PX,
                  native_tol_px=NATIVE_TOL_PX,
                  order_tol_px=ORDER_TOL_PX,
                  whole_needs_source_symmetry=True,
                  order_preserved_at_current=True,
                  export_verified=True,
                  rank='least movement, then least ink change'),
        ownership_recovery=OWNERSHIP_RECOVERY,
        cases=cases,
    )
    (output / 'report.json').write_text(json.dumps(payload, indent=1,
                                                   default=_json_default) + '\n')
    _write_candidate_changes(output, accepted)
    _write_candidate_index(output, focus)
    _write_candidate_diagnostics(output, counts, cases)
    print(f'admitted={len(cases)} accepted={len(accepted)} '
          f'focus={len(focus)} -> {output}')
    return payload


def _json_default(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    return str(value)


def _candidate_head(title):
    return ('<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}'
            'img{max-width:100%}</style>'
            f'<h1>{title}</h1><p><a href="index.html">Focus gallery</a> · '
            '<a href="changes.html">Accepted for human review</a> · '
            '<a href="diagnostics.html">Holds and deferred</a></p>')


def _write_candidate_changes(output, accepted):
    """ADAPTER: accepted-for-human-review candidates only."""
    import html as html_mod
    parts = [_candidate_head('Axis-placement candidates (human review only)')]
    if not accepted:
        parts.append('<p>No accepted candidates. All other cases are '
                     'no-change, held, or deferred; see diagnostics.</p>')
    for row in sorted(accepted, key=lambda r: (r['char'], r['key'])):
        parts.append(
            f'<section><h2>{html_mod.escape(row["key"])} '
            f'{html_mod.escape(row["char"])} [{html_mod.escape(row["tag"])}] '
            f'ink {row["ink_delta"]:+d}px</h2>'
            f'<img src="{row["preview"]}" loading="lazy"></section>')
    (output / 'changes.html').write_text(''.join(parts))


def _write_candidate_index(output, focus):
    """ADAPTER: focus gallery (+, T, !): preview if eligible, reason else."""
    import html as html_mod
    parts = [_candidate_head('Axis-placement focus gallery (+, T, !)'),
             '<p>Smooth source outline, current hinted raster, proposed '
             'hinted raster if eligible; otherwise the no-change/held '
             'reason. Nothing here is promoted.</p>']
    for row in sorted(focus, key=lambda r: (r['char'], r['key'])):
        head = (f'<section><h2>{html_mod.escape(row["key"])} '
                f'{html_mod.escape(row["char"])} '
                f'[{html_mod.escape(row["status"])}]</h2>')
        if row['status'] == 'accepted':
            parts.append(head + f'<p>{html_mod.escape(row["tag"])}; ink '
                         f'{row["ink_delta"]:+d}px; counters '
                         f'{row["white_counters"]}.</p>'
                         f'<img src="{row["preview"]}" loading="lazy"></section>')
        else:
            parts.append(head + f'<p>No proposal: '
                         f'{html_mod.escape(str(row.get("reason", "")))} '
                         f'(baseline x mismatch {row.get("baseline_mismatch")}, '
                         f'ink {row.get("baseline_ink")}).</p></section>')
    (output / 'index.html').write_text(''.join(parts))


def _write_candidate_diagnostics(output, counts, cases):
    """ADAPTER: coverage counts, holds, and deferred-percentage effects."""
    import html as html_mod
    lines = ['<p>Coverage over all admitted cases: '
             + html_mod.escape(json.dumps(counts)) + '</p>']
    held = [r for r in cases if r['status'] == 'held']
    lines.append(f'<h2>Held ({len(held)})</h2><ul>')
    for row in sorted(held, key=lambda r: (r['char'], r['key'])):
        lines.append(f'<li>{html_mod.escape(row["key"])} '
                     f'{html_mod.escape(row["char"])}: '
                     f'{html_mod.escape(str(row.get("reason", "")))} '
                     f'(baseline x mismatch {row.get("baseline_mismatch")})</li>')
    lines.append('</ul>')
    deferred = [r for r in cases if r['status'] == 'deferred']
    lines.append(f'<h2>Deferred percentage ({len(deferred)})</h2>'
                 '<p>Evaluated for coverage only; percentage output stays '
                 'baseline. Effects below carry the deferred label and were '
                 'never promoted.</p><ul>')
    for row in sorted(deferred, key=lambda r: (r['key'], r['char'])):
        effect = (f"{row.get('unit')}@{row.get('dx')}" if row.get('would_accept')
                  else 'no effect')
        lines.append(f'<li>deferred {html_mod.escape(row["key"])} '
                     f'{html_mod.escape(row["char"])}: {html_mod.escape(effect)} '
                     f'(baseline x mismatch {row.get("baseline_mismatch")})</li>')
    lines.append('</ul>')
    (output / 'diagnostics.html').write_text(
        _candidate_head('Axis-placement diagnostics') + ''.join(lines))


def _fmt_err(entry):
    src = entry['source_outline']
    fit = entry['fitted_outline']
    return (f"src max/mean {src['max']:.3f}/{src['mean']:.3f} "
            f"fit max/mean {fit['max']:.3f}/{fit['mean']:.3f} "
            f"raster {entry['raster']['mismatch']}px"
            f" ({entry['raster']['rate']:.2%})")


def _write_summary(output, targets):
    """ADAPTER: compact plain-text 36-case summary."""
    lines = ['# Axis-placement audit: 36 target cases (diagnostic, no corrections)',
             '# T x-only; + x/y; ! x diagnostic-focus. Whole-outline rigid phases first;',
             '# per-component best reported as c<index>@<dx>,0 (horizontal only).',
             '# raster mm uses ink-space centers; outline errors use outline-space centers.',
             '# "raster Npx" = current hinted raster vs its own center;',
             '# "base Mpx" = hinted fitted re-render vs its own center (phase-search baseline).',
             '# Each trial mirrors about its own ink center: the search isolates pixel-phase',
             '# faithfulness; internal shape asymmetry correctly reports no-gain.',
             '']
    for item in sorted(targets, key=lambda t: (t['char'], t['key'])):
        detail, char = item['detail'], item['char']
        lines.append(
            f"== {item['key']} {char!r} [{item['status']}] "
            f"src_ext {detail['source_extent']} fit_ext {detail['fitted_extent']}")
        for axis in item['focus_axes']:
            entry = item['generic'][axis]
            whole = detail['axes'][axis]['whole']
            comps = detail['axes'][axis]['components']
            comp_best = min(comps, key=lambda c: (
                c['result']['best']['raster']['mismatch'],
                abs(c['result']['best']['delta'][0])
                + abs(c['result']['best']['delta'][1]))) if comps else None
            line = (f"  {axis}: {_fmt_err(entry)} | "
                    f"whole best {whole['best']['delta']} -> "
                    f"{whole['best']['raster']['mismatch']}px "
                    f"(base {whole['baseline']['raster']['mismatch']}px; "
                    f"ink {whole['best_ink_delta']:+d}, "
                    f"ctr {whole['best_counter_delta']:+d}; "
                    f"{'ELIMINATED' if whole['eliminated'] else 'improved' if whole['improved'] else 'no-gain'})")
            if comp_best is not None:
                line += (f" | comp c{comp_best['component']}@"
                         f"{comp_best['result']['best']['delta']} -> "
                         f"{comp_best['result']['best']['raster']['mismatch']}px")
            lines.append(line)
        levels = '; '.join(
            f"{axis}:{[c['center'] for c in detail['stroke_levels'][axis][:8]]}"
            for axis in ('x', 'y'))
        boxes = [(c['contours'], c['box'], c['coaxial_offset'])
                 for c in detail['components']]
        lines.append(f'  levels {levels} | comps(contours,box,coax) {boxes}')
    (output / 'summary.txt').write_text('\n'.join(lines) + '\n')


def _write_index(output, targets):
    import html as html_mod
    parts = ['<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}'
             'img{max-width:100%}</style>'
             '<h1>Axis-placement audit (diagnostic only)</h1>'
             '<p>Smooth source outline, current hinted raster, best rigid '
             'phase (unhinted). No corrections, no promotions; unchanged '
             'renders are not candidates.</p>']
    for item in sorted(targets, key=lambda t: (t['char'], t['key'])):
        parts.append(
            f'<section><h2>{html_mod.escape(item["key"])} '
            f'{html_mod.escape(item["char"])}</h2>'
            f'<img src="{item["preview"]}" loading="lazy"></section>')
    (output / 'index.html').write_text(''.join(parts))


if __name__ == '__main__':
    run()

