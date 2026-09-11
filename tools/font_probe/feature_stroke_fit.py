"""Source-driven feature stroke fitting prototype (joint integer program).

Driver contract: ``fit(points, ends, flags, scale, groups, features,
current, raster, protected=None, ownership=None)``. Outline plus numeric
``groups``/``features`` (stem/bar kinds only); no glyph identity.
``current`` is a regression cost only; ``raster`` verifies the bitmap.
``protected`` is ``(matrix, rhs)`` over final coords, never relaxed.
``ownership`` maps points/axes to fixed values and is appended to the
protected matrix as explicit hard rows, enforced and validated.
Returns ``dict(status, coords, audit, reason)``: ``ok``/``no-op``/``held``.
One L1 soft term is ONE equality ``x - pos + neg == s`` with nonnegative
auxiliaries (source/current/ratio). Matched widths share one integer
target keyed by (axis, value); per-feature ``target`` wins and a default
target never forces a conflict with supplied P rows. Source symmetry is
validated via 2D outline segment reflected correspondence; supported axes
pair source boundary nodes across the axis with a shared center variable
``a + b == 2*center``. ``scipy.optimize.milp`` with L1 aux weights 3/1/2.
"""

import numpy as np

from scipy.optimize import Bounds, LinearConstraint, milp

W_SOURCE, W_CURRENT, W_RATIO = 3.0, 1.0, 2.0
TOL_LINK = 1e-6
EPS_EDGE = 1e-9
SYM_LINE_MAX, SYM_CENTER_MAX = 0.3, 0.15
MAX_DISPLACE, MAX_OUTER = 2.0, 1.0
_AXIS = {"stem": 0, "bar": 1}


def _held(reason, audit, current):
    audit["reason_held"] = reason
    return {"status": "held", "coords": np.asarray(current, float).copy(),
            "audit": audit, "reason": reason}


def _contours(ends):
    out, start = [], 0
    for end in ends:
        out.append(list(range(start, end + 1)))
        start = end + 1
    return out


def fit(points, ends, flags, scale, groups, features, current, raster,
        protected=None, ownership=None):
    """Joint source-driven stroke fit. See module docstring for contract."""
    p = np.asarray(points, float) * scale
    q0 = np.asarray(current, float)
    n = len(p)
    audit = {"solver": "scipy.optimize.milp", "weights": {
        "source": W_SOURCE, "current": W_CURRENT, "ratio": W_RATIO},
        "ownership": ownership if ownership is not None else {},
        "reason_held": None}
    contours = _contours([int(e) for e in ends])
    # Start gate: bounded orthogonal all-oncurve contours only.
    for ids in contours:
        for k, a in enumerate(ids):
            b = ids[(k + 1) % len(ids)]
            if not (flags[a] & 1 and flags[b] & 1):
                audit["ignored"] = "off-curve point"
                return _held("unsupported-curved", audit, q0)
            d = p[b] - p[a]
            if d[0] != 0.0 and d[1] != 0.0:
                audit["ignored"] = f"diagonal edge {a}-{b}"
                return _held("unsupported-diagonal", audit, q0)
    raw_strokes = [f for f in features if f.get("kind") in _AXIS]
    audit["ignored"] = [f.get("kind") for f in features
                        if f.get("kind") not in _AXIS]
    # Width classes include axis; fake wide dims are not stroke widths.
    strokes = [f for f in raw_strokes
               if float(f.get("length", 0)) >= 2 * float(f.get("width", 0))]
    audit["non_stroke"] = [f.get("kind") for f in raw_strokes
                           if f not in strokes]
    if not strokes:
        return _held("no-stroke-features", audit, q0)
    # Boundaries from source connected feature membership: union only
    # same-axis same-coord groups sharing a point, plus edge-adjacent
    # collinear oncurve chains along the contour.
    pt_groups = {}  # (m, ax) -> set of group ids covering it
    for gi, g in enumerate(groups):
        nrm = np.asarray(g["normal"], float)
        ax = int(np.argmax(abs(nrm)))
        if abs(nrm[ax]) <= 0.999 or not g["members"]:
            continue
        for m in g["members"]:
            pt_groups.setdefault((int(m), ax), set()).add(gi)
    parent = list(range(len(groups)))

    def _find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def _union(i, j):
        ri, rj = _find(i), _find(j)
        if ri != rj:
            parent[ri] = rj
    grp_ax = {}
    for gi, g in enumerate(groups):
        nrm = np.asarray(g["normal"], float)
        ax = int(np.argmax(abs(nrm)))
        grp_ax[gi] = ax if (abs(nrm[ax]) > 0.999 and g["members"]) else None
    for (m, ax), gis in pt_groups.items():
        gis = [g for g in gis if grp_ax.get(g) == ax]
        for i in gis:
            for j in gis[1:]:
                if abs(float(p[m, ax]) - float(p[m, ax])) <= TOL_LINK:
                    _union(i, j)
    # Edge-adjacent collinear oncurve chains: same-axis coord neighbours
    # joined by a cardinal edge extend the union.
    edge_adj = [[] for _ in groups]
    for ids in contours:
        for k, a in enumerate(ids):
            b = ids[(k + 1) % len(ids)]
            d = p[b] - p[a]
            if d[0] == 0.0 and d[1] == 0.0:
                continue
            ax = 0 if d[0] != 0.0 else 1
            perp = 1 - ax
            if abs(float(p[b, perp]) - float(p[a, perp])) <= TOL_LINK:
                ga = [g for g in pt_groups.get((a, perp), ())
                      if grp_ax.get(g) == perp]
                gb = [g for g in pt_groups.get((b, perp), ())
                      if grp_ax.get(g) == perp]
                for i in ga:
                    for j in gb:
                        _union(i, j)
    # One variable per union cluster; unassigned axis coords get
    # independent point vars (never globally merged by scalar value).
    bnd_axis, bnd_src, bnd_members, bnd_groups = [], [], [], []
    cluster_var = {}
    link = {}

    def _new_var(ax, members, grps):
        bnd_axis.append(ax)
        vals = [float(p[m, ax]) for m in members] or [0.0]
        bnd_src.append(sum(vals) / len(vals))
        bnd_members.append(set(members))
        bnd_groups.append(set(grps))
        return len(bnd_src) - 1

    for gi, g in enumerate(groups):
        ax = grp_ax.get(gi)
        if ax is None:
            continue
        r = _find(gi)
        if r in cluster_var:
            bi = cluster_var[r]
            for m in g["members"]:
                bnd_members[bi].add(int(m))
                link[(int(m), ax)] = bi
            bnd_groups[bi].add(gi)
            continue
        ms = set()
        for gj, h in enumerate(groups):
            if _find(gj) == r and grp_ax.get(gj) == ax:
                ms.update(int(m) for m in h["members"])
        grps = [gj for gj in range(len(groups))
                if _find(gj) == r and grp_ax.get(gj) == ax]
        bi = _new_var(ax, ms, grps)
        cluster_var[r] = bi
        for m in ms:
            link[(m, ax)] = bi
    for m in range(n):  # unassigned axis coords: independent point vars.
        if not (flags[m] & 1):
            continue
        for ax in (0, 1):
            if (m, ax) not in link:
                bi = _new_var(ax, [m], [])
                link[(m, ax)] = bi
    nb = len(bnd_src)
    if nb == 0:
        return _held("no-boundaries", audit, q0)

    def _axis_vars(ax):
        return [b for b in range(nb) if bnd_axis[b] == ax]

    # Paired boundaries per feature from its own groups' variables.
    feats = []
    for f in strokes:
        ax = _AXIS[f["kind"]]
        los = sorted({link[(int(m), ax)] for g in f["groups"]
                      for m in groups[g]["members"] if (int(m), ax) in link},
                     key=lambda b: bnd_src[b])
        if len(los) < 2:
            return _held("feature-without-pair", audit, q0)
        feats.append({"kind": f["kind"], "axis": ax,
                      "groups": list(f["groups"]), "lo": los[0],
                      "hi": los[-1], "width": float(f["width"]),
                      "supplied": f.get("target")})
    # Same complete feature side with disjoint visible supports shares a
    # node via the group's members: paired los/hi already route through
    # the union cluster, so disjoint supports of one side use one var.
    wsrc = []
    for f in feats:
        key = (f["axis"], f["width"])
        f["wclass"] = next((wi for wi, w in enumerate(wsrc)
                            if w[0] == key[0] and abs(w[1] - key[1]) <= 1e-6),
                           len(wsrc))
        if f["wclass"] == len(wsrc):
            wsrc.append(key)
    wtarget = [max(1, int(round(w[1]))) for w in wsrc]
    for f in feats:  # per-feature target wins; defaults never fight P rows.
        if f["supplied"] is not None:
            wtarget[f["wclass"]] = int(f["supplied"])

    def _span(feat, axis):
        vals = [float(p[int(m), axis]) for grp in feat["groups"]
                for m in groups[grp]["members"]]
        return min(vals), max(vals)

    # Crossbar proportional placement, derived from source spans.
    ratios = []
    for fi, f in enumerate(feats):
        a = f["axis"]
        c = (bnd_src[f["lo"]] + bnd_src[f["hi"]]) / 2.0
        for gi, g in enumerate(feats):
            if g["axis"] == a:
                continue
            gamn, gamx = _span(g, a)
            if gamx - gamn <= 0 or not gamn < c < gamx:
                continue
            flo, fhi = _span(f, 1 - a)
            glo, ghi = _span(g, 1 - a)
            if max(flo, glo) > min(fhi, ghi):
                continue
            ratios.append({"type": "proportion", "feature": fi,
                           "against": gi, "axis": a,
                           "ratio": (c - gamn) / (gamx - gamn)})
    # Source symmetry via 2D outline segment reflected correspondence.
    def _segments():
        segs = []
        for ids in contours:
            for k, a in enumerate(ids):
                b = ids[(k + 1) % len(ids)]
                segs.append((np.array(p[a], float), np.array(p[b], float)))
        return segs

    def _seg_refl_err(ax, mid):
        segs = _segments()
        worst = 0.0
        for s0, s1 in segs:
            r0 = s0.copy()
            r1 = s1.copy()
            r0[ax] = 2 * mid - s0[ax]
            r1[ax] = 2 * mid - s1[ax]
            best = min(min(max(np.linalg.norm(r0 - t0),
                               np.linalg.norm(r1 - t1)),
                           max(np.linalg.norm(r0 - t1),
                               np.linalg.norm(r1 - t0)))
                       for t0, t1 in segs)
            worst = max(worst, best)
        return worst

    def _pix_refl_mismatch(pix, ax):
        if not pix:
            return 0
        lo = min(c[ax] for c in pix)
        hi = max(c[ax] for c in pix)
        s = lo + hi
        refl = {(s - c[0], c[1]) if ax == 0 else (c[0], s - c[1])
                for c in pix}
        return len(set(pix) ^ refl)

    sym_axes = []
    for ax in (0, 1):
        xs = _axis_vars(ax)
        if not xs:
            continue
        mid = (min(bnd_src[b] for b in xs) + max(bnd_src[b] for b in xs)) / 2
        fc = [(bnd_src[f["lo"]] + bnd_src[f["hi"]]) / 2.0
              for f in feats if f["axis"] == ax]
        paired = all(min(abs((c + d) / 2.0 - mid) for d in fc)
                     <= SYM_CENTER_MAX for c in fc)
        if _seg_refl_err(ax, mid) <= SYM_LINE_MAX and paired:
            sym_axes.append(ax)
    # Current symmetry per axis: actual current bitmap pixel reflection
    # mismatch about the pixel-coordinate center (min+max), mismatch 0.
    def _as_pixset(raw):
        if isinstance(raw, set):
            return {(int(a), int(b)) for a, b in raw}
        arr = np.asarray(raw)
        if arr.ndim == 2 and arr.shape[1] == 2:
            return {(int(a), int(b)) for a, b in arr.tolist()}
        return {(int(a), int(b)) for a, b in set(raw)}
    try:
        cur_pix = _as_pixset(raster(q0))
    except Exception as exc:
        audit["bitmap_match"] = f"raster-error: {exc}"
        audit["raster_symmetry"] = None
        return _held("held-raster-error", audit, q0)
    cur_sym = [ax for ax in (0, 1)
               if _pix_refl_mismatch(cur_pix, ax) == 0]
    audit["raster_symmetry_before"] = {
        ax: _pix_refl_mismatch(cur_pix, ax) for ax in (0, 1)}
    if set(cur_sym) == {0, 1}:
        audit["bitmap_match"] = True
        audit["raster_symmetry"] = {0: 0, 1: 0}
        audit["raster_symmetry_after"] = {0: 0, 1: 0}
        return {"status": "no-op", "coords": q0.copy(),
                "audit": audit, "reason": None}
    audit["relationships"] = [{"type": "symmetry", "axis": a}
                              for a in sym_axes] + ratios
    # Ownership appended as explicit hard rows over final coords.
    own = {}
    if ownership:
        if isinstance(ownership, dict):
            for k, v in ownership.items():
                if isinstance(k, tuple):
                    own[(int(k[0]), int(k[1]))] = float(v)
                elif isinstance(v, dict):
                    for ax, val in v.items():
                        own[(int(k), int(ax))] = float(val)
                else:
                    try:
                        for ax, val in v:
                            own[(int(k), int(ax))] = float(val)
                    except TypeError:
                        pass
        else:
            for row in ownership:
                if isinstance(row, dict):
                    m, ax, val = row["point"], row["axis"], row["value"]
                else:
                    m, ax, val = row
                own[(int(m), int(ax))] = float(val)
    # One joint MILP over all connected features, both axes at once.
    nw, nli, nr = len(wsrc), len(link), len(ratios)
    nsym = len(sym_axes)
    link_items = sorted(link.items())
    li_pos = {k: i for i, (k, _) in enumerate(link_items)}
    N = nb + nw + nsym + 2 * nb + 2 * nli + 2 * nr
    c = np.zeros(N)
    c[nb + nw + nsym:nb + nw + nsym + 2 * nb] = W_SOURCE
    c[nb + nw + nsym + 2 * nb:nb + nw + nsym + 2 * nb + 2 * nli] = W_CURRENT
    c[nb + nw + nsym + 2 * nb + 2 * nli:] = W_RATIO
    rows, lbs, ubs = [], [], []

    def _eq(terms, value):
        row = np.zeros(N)
        for idx, coef in terms:
            row[idx] += coef
        rows.append(row)
        lbs.append(value)
        ubs.append(value)

    integrality = np.zeros(N)
    integrality[:nb + nw] = 1
    lb = np.full(N, -np.inf)
    ub = np.full(N, np.inf)
    lb[nb + nw + nsym:] = 0.0
    for b, s in enumerate(bnd_src):
        lb[b], ub[b] = s - MAX_DISPLACE, s + MAX_DISPLACE
    for ax in (0, 1):
        xs = sorted(_axis_vars(ax), key=lambda b: bnd_src[b])
        if xs:
            for e in (xs[0], xs[-1]):
                lb[e] = max(lb[e], bnd_src[e] - MAX_OUTER)
                ub[e] = min(ub[e], bnd_src[e] + MAX_OUTER)
            for a, b in zip(xs, xs[1:]):  # preserve nonzero cardinal edges.
                row = np.zeros(N)
                row[b] += 1.0
                row[a] -= 1.0
                rows.append(row)
                gap = bnd_src[b] - bnd_src[a]
                if abs(gap) >= EPS_EDGE:
                    if gap > 0:
                        lbs.append(EPS_EDGE)
                    else:
                        lbs.append(-np.inf)
                        lbs[-1] = -np.inf
                        ubs.append(-EPS_EDGE)
                        continue
                    ubs.append(np.inf)
                else:
                    lbs.append(0.0)
                    ubs.append(np.inf)
    for cax in cur_sym:  # current-symmetric axis: pin coords exactly.
        seen = {}
        for (m, ax), b in link.items():
            if ax != cax:
                continue
            v = float(q0[m, ax])
            if b in seen and abs(seen[b] - v) > 1e-9:
                # Split current on a fixed axis is contradictory: hold.
                audit["hard_residual"] = abs(seen[b] - v)
                audit["solver_status"] = "not-run"
                return _held("current-split-conflict", audit, q0)
            seen[b] = v
            lb[b] = ub[b] = v
            integrality[b] = 0  # fixed nodes allow fractional positions.
    for f in feats:  # hard source collinearity pairing + matched widths.
        _eq([(f["hi"], 1.0), (f["lo"], -1.0),
             (nb + f["wclass"], -1.0)], 0.0)
    pinned_axes = set(cur_sym)
    for wi, t in enumerate(wtarget):
        users = [f for f in feats if f["wclass"] == wi]
        if users and all(f["axis"] in pinned_axes for f in users):
            integrality[nb + wi] = 0  # width follows pinned coords.
            continue
        lb[nb + wi] = max(lb[nb + wi], 1.0)
        _eq([(nb + wi, 1.0)], float(t))
    # Supported reflection: paired boundary nodes share a center variable.
    for si, ax in enumerate(sym_axes):
        ci = nb + nw + si
        xs = sorted(_axis_vars(ax), key=lambda b: bnd_src[b])
        for a, b in zip(xs, xs[::-1]):
            if a >= b:
                break
            _eq([(a, 1.0), (b, 1.0), (ci, -2.0)], 0.0)

    def _soft(var, target, aux):  # ONE equality: x - pos + neg == s.
        _eq([(var, 1.0), (aux, -1.0), (aux + 1, 1.0)], target)

    o_src = nb + nw + nsym
    o_cur = o_src + 2 * nb
    for b, s in enumerate(bnd_src):
        _soft(b, s, o_src + 2 * b)
    for i, ((m, ax), b) in enumerate(link_items):
        _soft(b, float(q0[m, ax]), o_cur + 2 * i)
    o_rat = o_cur + 2 * nli
    for j, r in enumerate(ratios):
        g = feats[r["against"]]
        got = sorted({link[(int(m), r["axis"])] for grp in g["groups"]
                      for m in groups[grp]["members"]
                      if (int(m), r["axis"]) in link},
                     key=lambda b: bnd_src[b])
        f, t = feats[r["feature"]], r["ratio"]
        base = [(f["lo"], 0.5), (f["hi"], 0.5),
                (got[0], t - 1.0), (got[-1], -t)]
        _eq(base + [(o_rat + 2 * j, -1.0), (o_rat + 2 * j + 1, 1.0)], 0.0)
    # Protected + ownership rows over final coords; never relaxed.
    n_prot = 0
    amat_rows, rhs_rows = [], []
    if protected is not None:
        amat_rows.append(np.asarray(protected[0], float))
        rhs_rows.append(np.asarray(protected[1], float))
    if own:
        big = np.zeros((len(own), n * 2))
        rhs = np.zeros(len(own))
        for i, ((m, ax), v) in enumerate(sorted(own.items())):
            big[i, 2 * m + ax] = 1.0
            rhs[i] = v
        amat_rows.append(big)
        rhs_rows.append(rhs)
        audit["ownership_rows"] = len(own)
    if amat_rows:
        amat = np.vstack(amat_rows)
        rhs = np.concatenate(rhs_rows)
        for ri in range(amat.shape[0]):
            row, const = np.zeros(N), 0.0
            for m, ax in zip(*np.nonzero(amat[ri].reshape(n, 2))):
                v = amat[ri, 2 * m + ax]
                if (m, ax) in link:
                    row[link[(m, ax)]] += v
                else:
                    const += v * float(p[m, ax])
            if not row.any():
                if abs(const - rhs[ri]) > 1e-9:
                    audit["hard_residual"] = abs(const - rhs[ri])
                    audit["solver_status"] = "not-run"
                    return _held("protected-conflict", audit, q0)
                continue
            rows.append(row)
            lbs.append(rhs[ri] - const)
            ubs.append(rhs[ri] - const)
            n_prot += 1

    def _solve(keep):
        A = np.vstack(rows[:keep]) if keep else np.zeros((0, N))
        return milp(c, integrality=integrality, bounds=Bounds(lb, ub),
                    constraints=LinearConstraint(
                        A, np.array(lbs[:keep], float),
                        np.array(ubs[:keep], float)))

    res = _solve(len(rows))
    audit["solver_status"] = res.status
    if res.status != 0:
        if n_prot and _solve(len(rows) - n_prot).status == 0:
            audit["hard_residual"] = None
            return _held("protected-conflict", audit, q0)
        audit["hard_residual"] = None
        return _held("infeasible", audit, q0)
    x = res.x
    q = p.copy()
    for (m, ax), b in link.items():
        q[m, ax] = x[b]
    for f in feats:
        f["selected"] = float(x[nb + f["wclass"]])
        f["center"] = (float(x[f["lo"]]) + float(x[f["hi"]])) / 2.0
    hard = max([abs(x[f["hi"]] - x[f["lo"]] - x[nb + f["wclass"]])
                for f in feats] + [0.0])
    # Enforce and validate protected/ownership residuals on final coords.
    if amat_rows:
        amat = np.vstack(amat_rows)
        rhs = np.concatenate(rhs_rows)
        hard = max(hard, float(np.max(np.abs(
            amat @ q.reshape(-1) - rhs))))
    audit["hard_residual"] = hard
    # Verify no contour inversion: nonzero cardinal edge signs preserved.
    for ids in contours:
        for k, a in enumerate(ids):
            b = ids[(k + 1) % len(ids)]
            for ax in (0, 1):
                g = float(p[b, ax]) - float(p[a, ax])
                if abs(g) >= EPS_EDGE:
                    got = float(q[b, ax]) - float(q[a, ax])
                    if got == 0.0 or (got > 0) != (g > 0):
                        audit["reason_detail"] = f"inversion {a}-{b}"
                        return _held("contour-inversion", audit, q0)
    audit["boundaries"] = [
        {"axis": bnd_axis[b], "source": bnd_src[b],
         "selected": float(x[b]), "members": sorted(bnd_members[b]),
         "groups": sorted(bnd_groups[b])} for b in range(nb)]
    audit["features"] = [
        {"kind": f["kind"], "groups": f["groups"],
         "source_width": wsrc[f["wclass"]][1], "selected_width": f["selected"],
         "center": f["center"]} for f in feats]
    audit["width_targets"] = [
        {"axis": w[0], "source": w[1], "target": t}
        for w, t in zip(wsrc, wtarget)]
    audit["constraints"] = {"equalities": len(rows),
                            "protected_hard": n_prot,
                            "ratios": len(ratios),
                            "sym_axes": list(sym_axes)}
    try:
        rq, rq0s = _as_pixset(raster(q)), _as_pixset(raster(q0))
        audit["bitmap_match"] = (rq == rq0s)
        after = {ax: _pix_refl_mismatch(rq, ax) for ax in (0, 1)}
        audit["raster_symmetry_after"] = after
        audit["raster_symmetry"] = {ax: after[ax] for ax in sym_axes} \
            if sym_axes else None
    except Exception as exc:
        audit["bitmap_match"] = f"raster-error: {exc}"
        audit["raster_symmetry"] = None
        return _held("held-raster-error", audit, q0)
    if any(after[ax] != 0 for ax in sym_axes):
        audit["reason_detail"] = {ax: after[ax] for ax in sym_axes}
        return _held("held-raster-error", audit, q0)
    if np.array_equal(q, q0):
        return {"status": "no-op", "coords": q0.copy(),
                "audit": audit, "reason": None}
    return {"status": "ok", "coords": q, "audit": audit, "reason": None}
