"""Bounded geometry-only both-axis symmetry experiment; bitmap measured, never edited."""

import itertools

import numpy as np

RESIDUAL_PX = 0.15
MAX_EDGE_MOVE_PX = 1.0
MAX_SPAN_CHANGE_PX = 1.0
MAX_SOURCE_DISP_PX = 2.0
EQ_TOL = 1e-7
NATIVE_TOL = 1 / 64


def mismatch(ink, axes):
    if not ink:
        return 0
    result = 0
    for axis in axes:
        lo = min(v[axis] for v in ink)
        hi = max(v[axis] for v in ink)
        reflected = {tuple(lo + hi - v[j] if j == axis else v[j] for j in (0, 1))
                     for v in ink}
        result += len(ink ^ reflected)
    return result


def _levels_ok(values):
    v = np.asarray(sorted(values), float)
    if len(v) != 4 or np.min(np.diff(v)) <= 1e-8:
        return None
    residual = abs((v[0] + v[3]) - (v[1] + v[2])) / 2.0
    if residual > RESIDUAL_PX + 1e-9:
        return None
    return v


def _applies(points, ends, flags, scale):
    if len(ends) != 1:
        return None
    n = ends[0] + 1
    if n < 8 or any(not (flags[i] & 1) for i in range(n)):
        return None
    p = np.asarray(points, float) * scale
    d = p - np.roll(p, 1, axis=0)
    if not bool(np.all(np.min(abs(d), axis=1) < 1e-8)):
        return None
    levels = [np.unique(p[:, ax]) for ax in (0, 1)]
    checked = [_levels_ok(v) for v in levels]
    if any(v is None for v in checked):
        return None
    return p, checked


def _symmetric_targets(center_current):
    """Integer symmetric 4-level targets; inner width must be integer."""
    c = np.asarray(center_current, float)
    if len(c) != 4:
        return
    inner = c[2] - c[1]
    if abs(inner - round(inner)) > 1e-9 or round(inner) < 1:
        return
    inner = int(round(inner))
    lo, hi = c[0], c[3]
    span0 = hi - lo
    for outer_lo in range(int(np.floor(lo)) - 1, int(np.ceil(lo)) + 2):
        for span in (int(round(span0)) - 1, int(round(span0)), int(round(span0)) + 1):
            if span < 1 or abs(span - span0) > MAX_SPAN_CHANGE_PX + 1e-9:
                continue
            grid = np.array([outer_lo, outer_lo + (span - inner) / 2.0,
                             outer_lo + (span + inner) / 2.0, outer_lo + span])
            if np.any(grid != np.round(grid)):
                continue
            if not bool(np.all(grid[1:] - grid[:-1] > 0)):
                continue
            if np.any(np.abs(grid - c) > MAX_EDGE_MOVE_PX + 1e-9):
                continue
            if abs((grid[0] + grid[3]) - (grid[1] + grid[2])) / 2.0 > 1e-9:
                continue
            yield grid


def _labels(p, vals, ax):
    return np.argmin(abs(p[:, ax, None] - vals[None, :]), axis=1)


def candidates(points, ends, flags, current, scale, fixed_axes=()):
    gated = _applies(points, ends, flags, scale)
    if gated is None:
        return
    p, _ = gated
    q = np.asarray(current, float)
    if np.max(abs(q - p)) > MAX_SOURCE_DISP_PX + 1e-9:
        return
    per_axis = []
    for ax in (0, 1):
        if ax in tuple(fixed_axes or ()):
            continue
        vals = np.unique(p[:, ax])
        lab = _labels(p, vals, ax)
        if len(vals) != 4:
            return
        # Fitted source-level collinearity: each source level maps to one
        # current center; positive ordering of levels preserved.
        centers = np.array([np.mean(q[lab == j, ax]) if
                            float(np.ptp(q[lab == j, ax])) <= 1e-7 else np.nan
                            for j in range(4)])
        if not bool(np.all(np.isfinite(centers)) and np.all(np.diff(centers) > 0)):
            return
        grids = list(_symmetric_targets(centers))
        if not grids:
            return
        per_axis.append((ax, lab, grids))
    if not per_axis:
        return
    for combo in itertools.product(*[g for _, _, g in per_axis]):
        after = q.copy()
        for (ax, lab, _), grid in zip(per_axis, combo):
            after[:, ax] = grid[lab]
        yield after, dict(kind='both-axis-levels', axes=[ax for ax, _, _ in per_axis])


def _eq_ok(after, protected):
    if protected is None:
        return True
    rows, values = protected
    rows = np.asarray(rows, float)
    values = np.asarray(values, float)
    pred = rows @ np.asarray(after, float).reshape(-1)
    return bool(np.all(np.abs(pred - values) <= EQ_TOL))


def _ownership_ok(after, ownership):
    for o in ownership or ():
        if abs(float(after[o['point'], o['axis']]) - float(o['value'])) > NATIVE_TOL:
            return False
    return True


def fit(points, ends, flags, current, scale, raster, ownership=(), protected=None):
    q = np.asarray(current, float)
    if _applies(points, ends, flags, scale) is None:
        before = raster(q)
        return q, dict(status='no-eligible-geometry', kind='both-axis-levels',
                       axes=[0, 1], trials=0, blocked=0, block_reasons=[],
                       x_mismatch=mismatch(before, [0]),
                       y_mismatch=mismatch(before, [1]))
    before = raster(q)
    mmx = mismatch(before, [0])
    mmy = mismatch(before, [1])
    if mmx == 0 and mmy == 0:
        return q, dict(status='already-symmetric', kind='both-axis-levels',
                       axes=[0, 1], trials=0, x_mismatch=0, y_mismatch=0)
    fixed = [ax for ax, mm in ((0, mmx), (1, mmy)) if mm == 0]
    best, count, blocked, reasons = None, 0, 0, []
    for after, audit in candidates(points, ends, flags, q, scale, fixed_axes=fixed):
        count += 1
        if np.max(abs(after - np.asarray(points, float) * scale)) > \
                MAX_SOURCE_DISP_PX + 1e-9:
            blocked += 1
            reasons.append('source-displacement')
            continue
        if not _ownership_ok(after, ownership):
            blocked += 1
            reasons.append('protected-ownership')
            continue
        if not _eq_ok(after, protected):
            blocked += 1
            reasons.append('protected-equation')
            continue
        ink = raster(after)
        if mismatch(ink, [0, 1]):
            blocked += 1
            reasons.append('native-raster')
            continue
        loss = float(.5 * np.mean((after - q) ** 2)
                     + .5 * np.mean((after - np.asarray(points, float) * scale) ** 2))
        area = abs(len(ink) - len(before)) / max(1, len(before))
        score = (loss, area)
        if best is None or score < best[0]:
            best = (score, after, dict(audit, score=loss + area,
                                       before_mismatch=mmx + mmy,
                                       after_mismatch=0))
    if best:
        return best[1], dict(best[2], status='candidate', trials=count,
                             blocked=blocked, block_reasons=reasons)
    if count:
        return q, dict(status='held', kind='both-axis-levels',
                       axes=[0, 1], trials=count, blocked=blocked,
                       block_reasons=reasons, x_mismatch=mmx, y_mismatch=mmy)
    return q, dict(status='held', kind='both-axis-levels',
                   axes=[0, 1], trials=count, blocked=blocked,
                   block_reasons=reasons, x_mismatch=mmx, y_mismatch=mmy)
