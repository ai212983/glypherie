"""Central upright stem fit: geometry-only recentering of a symmetric stem.

fit(points, ends, flags, current, scale) maps current x-coordinates through
a monotone piecewise-affine map over knots [A, L, R, B] while leaving y
exact. No identity selectors (no glyph, family, or size in the API).
"""
import numpy as np

from audit_axis_placement import sample_outline, symmetry_error
from outline_relationships import reversed_edges

TOL_SHARE = 1.0 / 64.0
SYM_MAX = 0.15
OVERLAP_FRAC = 0.15
CENTER_TOL = 0.15
EDGE_MOVE = 1.0
SPAN_MOVE = 1.0
AFTER_SOURCE_MAX = 2.0


def _spans(ends, flags):
    """Yield per-contour spans as index lists [end, ctrls..., end].

    Implied on-curves between consecutive off-curves are marked None and
    resolved by the caller from current coordinates.
    """
    start = 0
    for end in ends:
        ids = list(range(start, end + 1))
        start = end + 1
        on = [i for i in ids if flags[i] & 1]
        if not on:
            continue
        k = ids.index(on[0])
        ids = ids[k:] + ids[:k]
        first = ids[0]
        i = 1
        cur = [first]
        while i < len(ids):
            j = ids[i]
            if flags[j] & 1:
                yield cur + [j]
                cur = [j]
                i += 1
            else:
                nxt = ids[i + 1] if i + 1 < len(ids) else first
                if nxt == first and not (flags[nxt] & 1):
                    yield cur + [j, None]
                    cur = [None, j]
                    i += 1
                elif flags[nxt] & 1:
                    yield cur + [j, nxt]
                    cur = [nxt]
                    i += 2
                else:
                    yield cur + [j, None]
                    cur = [None, j]
                    i += 1
        if cur != [first]:
            yield cur + [first]


def _vertical_runs(p, ends, flags):
    """Exact-x consecutive-oncurve vertical edges grouped per x."""
    runs = {}
    start = 0
    for end in ends:
        ids = list(range(start, end + 1))
        start = end + 1
        for k, a in enumerate(ids):
            b = ids[(k + 1) % len(ids)]
            if not (flags[a] & 1 and flags[b] & 1):
                continue
            if p[a, 0] == p[b, 0] and p[a, 1] != p[b, 1]:
                runs.setdefault(float(p[a, 0]), []).append(
                    (min(p[a, 1], p[b, 1]), max(p[a, 1], p[b, 1])))
    merged = {}
    for x, ivs in runs.items():
        ivs = sorted(ivs)
        out = [list(ivs[0])]
        for lo, hi in ivs[1:]:
            if lo <= out[-1][1]:
                out[-1][1] = max(out[-1][1], hi)
            else:
                out.append([lo, hi])
        merged[x] = out
    return merged


def _overlap(a, b):
    i = j = 0
    total = 0.0
    while i < len(a) and j < len(b):
        lo, hi = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if hi > lo:
            total += hi - lo
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return total


def _poly_xs(span, q):
    """Current x-coords of a span control polygon (implied = midpoint)."""
    out = []
    for k, idx in enumerate(span):
        if idx is not None:
            out.append(float(q[idx, 0]))
            continue
        a, b = span[k - 1], span[k + 1]
        out.append(float((q[a, 0] + q[b, 0]) / 2.0))
    return out


def _confined(xs, knots, tol=1e-9):
    return any(all(knots[i] - tol <= x <= knots[i + 1] + tol for x in xs)
               for i in range(len(knots) - 1))


def _affine_map(x, knots, targets):
    k = np.asarray(knots, float)
    t = np.asarray(targets, float)
    x = min(max(float(x), k[0]), k[-1])
    for i in range(len(k) - 1):
        if x <= k[i + 1] or i == len(k) - 2:
            denom = k[i + 1] - k[i]
            s = (t[i + 1] - t[i]) / denom if denom else 0.0
            return t[i] + s * (x - k[i])
    return t[-1]


def fit(points, ends, flags, current, scale):
    """Recenter a central vertical upright stem. Never raises no-match."""
    p = np.asarray(points, float) * scale
    q = np.asarray(current, float).copy()
    ends = [int(e) for e in ends]
    flags = [int(f) for f in flags]
    audit = dict(status='held', knots=None, width=None, axis=None,
                 reason='', evidence={})
    if not len(ends) or p.shape[0] == 0:
        audit.update(reason='empty-outline')
        return q, audit
    height = float(p[:, 1].max() - p[:, 1].min())
    if height <= 0:
        audit.update(reason='zero-height')
        return q, audit
    xcenter = float(p[:, 0].min() + p[:, 0].max()) / 2.0
    runs = _vertical_runs(p, ends, flags)
    pairs = []
    xs = sorted(runs)
    for i in range(len(xs)):
        for j in range(i + 1, len(xs)):
            ls, rs = xs[i], xs[j]
            ov = _overlap(runs[ls], runs[rs])
            if ov < OVERLAP_FRAC * height:
                continue
            if rs - ls > height / 4.0:
                continue
            if abs((ls + rs) / 2.0 - xcenter) > CENTER_TOL:
                continue
            pairs.append((ov, ls, rs))
    if not pairs:
        audit.update(reason='no-central-upright',
                     evidence=dict(n_runs=len(runs)))
        return q, audit
    pairs.sort(key=lambda t: -t[0])
    if len(pairs) > 1 and pairs[1][0] == pairs[0][0]:
        audit.update(reason='ambiguous-stem',
                     evidence=dict(n_pairs=len(pairs), overlap=pairs[0][0]))
        return q, audit
    _, Ls, Rs = pairs[0]
    axis = (Ls + Rs) / 2.0
    contours = sample_outline(points, ends, flags, scale)
    sym = symmetry_error(contours, 'x', float(axis))
    if sym['max'] > SYM_MAX:
        audit.update(status='unaffected', reason='asymmetric-source',
                     axis=float(axis), evidence=dict(symmetry_max=sym['max']))
        return q, audit
    ls_idx = [i for i in range(len(p)) if p[i, 0] == Ls]
    rs_idx = [i for i in range(len(p)) if p[i, 0] == Rs]
    if not ls_idx or not rs_idx:
        audit.update(reason='stem-side-missing')
        return q, audit
    for side, idx in (('L', ls_idx), ('R', rs_idx)):
        if float(q[idx, 0].max() - q[idx, 0].min()) > TOL_SHARE:
            audit.update(reason='fitted-side-split:%s' % side,
                         axis=float(axis))
            return q, audit
    L = float(q[ls_idx, 0].mean())
    R = float(q[rs_idx, 0].mean())
    A = float(q[:, 0].min())
    B = float(q[:, 0].max())
    if not (L - A > 0 and B - R > 0 and R - L > 0):
        audit.update(reason='nonpositive-flank-or-stem', axis=float(axis))
        return q, audit
    width = int(round(R - L))
    if width < 1 or abs((R - L) - width) >= 1e-9:
        audit.update(reason='stem-width-not-integer', axis=float(axis),
                     evidence=dict(stem_width=float(R - L)))
        return q, audit
    if abs((A + B) / 2.0 - (L + R) / 2.0) <= TOL_SHARE:
        audit.update(status='already-centered', reason='centers-agree',
                     knots=[A, L, R, B], width=width, axis=float(axis))
        return q, audit
    knots = [A, L, R, B]
    outer = B - A
    cands = []
    for Ap in range(int(np.floor(A - EDGE_MOVE)), int(np.ceil(A + EDGE_MOVE)) + 1):
        if abs(Ap - A) > EDGE_MOVE + 1e-9:
            continue
        for Lp in range(int(np.floor(L - EDGE_MOVE)), int(np.ceil(L + EDGE_MOVE)) + 1):
            if abs(Lp - L) > EDGE_MOVE + 1e-9:
                continue
            Rp = Lp + width
            if abs(Rp - R) > EDGE_MOVE + 1e-9:
                continue
            Bp = Lp + Rp - Ap
            if abs(Bp - B) > EDGE_MOVE + 1e-9:
                continue
            if abs((Bp - Ap) - outer) > SPAN_MOVE + 1e-9:
                continue
            if not (Lp - Ap > 0 and Bp - Rp > 0):
                continue
            cands.append([float(Ap), float(Lp), float(Rp), float(Bp)])
    ranked = []
    for kt in sorted(cands):
        mapped = q.copy()
        mapped[:, 0] = [_affine_map(x, knots, kt) for x in q[:, 0]]
        ok = True
        for span in _spans(ends, flags):
            if not _confined(_poly_xs(span, q), knots):
                ok = False
                break
        if not ok:
            continue
        if reversed_edges(p, mapped, ends, flags):
            continue
        if float(np.abs(mapped - p).max()) > AFTER_SOURCE_MAX:
            continue
        ms = float(((mapped - p) ** 2).sum(axis=1).mean())
        mc = float(((mapped - q) ** 2).sum(axis=1).mean())
        ranked.append((ms, mc, kt, mapped))
    if not ranked:
        audit.update(reason='no-admissible-target', knots=knots, width=width,
                     axis=float(axis),
                     evidence=dict(n_targets=len(cands)))
        return q, audit
    ranked.sort(key=lambda t: (t[0], t[1], t[2]))
    _, _, kt, mapped = ranked[0]
    # Source-collinear membership: group each point by its SOURCE x against
    # the source knot set [A_src, Ls, Rs, B_src]; each member takes the
    # corresponding candidate target knot value exactly (no rerounding).
    # Never inferred from mapped coordinates.
    a_src, b_src = float(p[:, 0].min()), float(p[:, 0].max())
    src_knots = [a_src, Ls, Rs, b_src]
    member_targets = {}
    for i in range(len(p)):
        sx = float(p[i, 0])
        for j, sk in enumerate(src_knots):
            if abs(sx - sk) <= TOL_SHARE:
                member_targets[int(i)] = float(kt[j])
                break
    audit.update(status='candidate', reason='recentered', knots=knots,
                 width=width, axis=float((kt[1] + kt[2]) / 2.0),
                 evidence=dict(target_knots=kt,
                               ms_from_source=ranked[0][0],
                               ms_from_current=ranked[0][1],
                               n_targets=len(cands),
                               source_knots=src_knots,
                               member_targets=member_targets))
    return mapped, audit
