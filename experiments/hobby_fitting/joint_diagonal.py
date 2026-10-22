"""Joint diagonal fit: Hobby (16) symmetry with parity phase plus (17) widths.

Hobby 1993 section 3.5, (14)-(16): approximate reflection with adjustable
map Mbar and per-endpoint residuals; the audit-supported normal (D_y,-D_x)
replaces the stored D-dot form, which measures sliding, not separation.
Hobby 1993 section 3.6/4.2, (17): relative-error coupling with the printed
9-radian weight, preserving intended contrast. Hobby 1993 section 2, Fig. 8:
scan conversion turns on pixels whose centers lie inside; an odd snapped
waist width is deterministic only with its axis on a pixel center, an even
one on a boundary. Hersch 1993 section 5, Figs. 17-18: symmetry-center phase
and centering between extremal points. The parity half and the waist/axis
recognition below are project adaptations; hard (11)-(13) rows are excluded
because they dominate the solve and move absolute widths.
"""
import math
from fractions import Fraction

import numpy as np

from experiments.hobby_fitting import direct_diagonal as dd
from experiments.hobby_fitting.symmetry_placement import axis_interval

EPS_PARITY = 0.25
ALPHA6 = 5e5


def _bounded_equalities(a, b, g, h, bounds):
    """Feasible primal active-set least squares with equality and box limits.

    Forsgren, Gill and Wong (2015), primal feasibility and KKT search:
    equality-nullspace least squares supplies each direction; the first
    blocking bound limits its step, and a negative bound multiplier releases
    that constraint. Unresolved initialization or iteration limits abstain.
    """
    n = len(bounds)
    if not n or not len(g):
        return None
    norms = np.linalg.norm(g, axis=1)
    if np.any(norms == 0):
        return None
    g, h = g / norms[:, None], h / norms
    x = np.linalg.lstsq(g, h, rcond=None)[0]
    tol = 1e-9
    if np.max(np.abs(g @ x - h), initial=0) > tol or np.any(np.abs(x) > bounds + tol):
        return None
    active = []
    for iteration in range(20 * max(1, n)):
        normals = [np.eye(n)[i] * sign for i, sign in active]
        working = np.vstack([g, *normals]) if normals else g
        _, singular, vh = np.linalg.svd(working, full_matrices=True)
        rank = int(np.sum(singular > max(working.shape) * singular[0] * 1e-12))
        z = vh[rank:].T
        p = z @ np.linalg.lstsq(a @ z, b - a @ x, rcond=None)[0] if z.shape[1] else np.zeros(n)
        if np.linalg.norm(p) <= tol:
            gradient = a.T @ (a @ x - b)
            multipliers = np.linalg.lstsq(working.T, -gradient, rcond=None)[0]
            residual = gradient + working.T @ multipliers
            if np.linalg.norm(residual) > tol * (1 + np.linalg.norm(gradient)):
                return None
            bound_multipliers = multipliers[len(g):]
            if not len(bound_multipliers) or min(bound_multipliers) >= -tol * (1 + np.linalg.norm(gradient)):
                if np.max(np.abs(g @ x - h), initial=0) > tol or np.any(np.abs(x) > bounds + tol):
                    return None
                return x, dict(iterations=iteration + 1, active=active,
                               equality_error=float(np.max(np.abs(g @ x - h), initial=0)),
                               stationarity_error=float(np.linalg.norm(residual)))
            del active[int(np.argmin(bound_multipliers))]
            continue
        step, blocking = 1., None
        for i, value in enumerate(p):
            if abs(value) <= tol or any(j == i for j, _ in active):
                continue
            sign = 1 if value > 0 else -1
            distance = (sign * bounds[i] - x[i]) / value
            if distance < step:
                step, blocking = max(0., distance), (i, sign)
        x = x + step * p
        if blocking is not None:
            active.append(blocking)
    return None


def _waist_from_slabs(parsed):
    """Internal crossing neck, with separated ink spans above and below.

    This restricted feature class applies Hersch center-phase to a waist,
    rather than mistaking a silhouette tip for a thin central stroke.
    Exact critical sections make collinear subdivision immaterial.
    """
    points = [tuple(map(Fraction, p)) for p in parsed['oncurve']]
    levels = sorted({p[1] for p in points})
    edges = [(points[i], points[j]) for contour in parsed['contours']
             for op, i, j in contour if op == 'line' and points[i][1] != points[j][1]]
    slabs = []
    for lo, hi in zip(levels, levels[1:]):
        y = (lo + hi) / 2
        active = [(a, b) for a, b in edges if min(a[1], b[1]) < y < max(a[1], b[1])]
        def cross(a, b, at):
            return a[0] + (at - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
        active.sort(key=lambda edge: cross(*edge, y))
        spans = len(active) // 2 if len(active) % 2 == 0 else 0
        endpoints = []
        if spans == 1:
            for at in (lo, hi):
                xs = sorted(cross(a, b, at) for a, b in active)
                endpoints.append((xs[1] - xs[0], (xs[0] + xs[1]) / 2, at))
        slabs.append((spans, endpoints))
    candidates = []
    i = 0
    while i < len(slabs):
        if slabs[i][0] != 1:
            i += 1
            continue
        start = i
        while i < len(slabs) and slabs[i][0] == 1:
            i += 1
        if start == 0 or i == len(slabs) or min(slabs[start - 1][0], slabs[i][0]) < 2:
            continue
        samples = [point for _, endpoints in slabs[start:i] for point in endpoints]
        best = min(samples)
        if 0 < best[0] < min(samples[0][0], samples[-1][0]):
            candidates.append(best)
    if len(candidates) != 1:
        return None
    width, axis, level = candidates[0]
    return dict(width=float(width), mid=float(axis), level=float(level))


def parity_target(axis, width):
    """Parity-compatible axis position from geometry, never from pixels.

    Returns None when the snapped count is below one: centering on a
    boundary for a sub-half-pixel span guarantees dropout, so the parity
    choice is unsupported rather than defaulted.
    """
    n = int(math.floor(width + 0.5))
    if n < 1:
        return None
    if n % 2:
        base = math.floor(axis - 0.5) + 0.5
        return base if abs(axis - base) <= abs(axis - (base + 1.0)) else base + 1.0
    base = math.floor(axis + 0.5)
    return float(base) if abs(axis - base) <= abs(axis - (base - 1.0)) \
        else float(base - 1.0)


def _reflect(point, axis):
    return (2.0 * axis - point[0], point[1])


def _reencode(o, reversed_match):
    """Same portion re-encoded so p0/p1 follow the matching orientation.

    Coefficients always derive from (i0, i1, t0, t1), so the re-encoding
    is indistinguishable downstream from a contour drawn that way.
    """
    if not reversed_match:
        return dict(o)
    return dict(o, p0=o["p1"], p1=o["p0"], i0=o["i1"], i1=o["i0"],
                t0=1.0 - o.get("t1", 1.0), t1=1.0 - o.get("t0", 0.0))


def _match_borders(sides, axis, epsilon):
    """Segment-to-segment reflection matches under M about the source axis.

    The returned second side is re-encoded to the matching orientation, so
    corresponding coefficient indices always reflect that orientation.
    """
    matches = []
    seen = set()
    for i, s in enumerate(sides):
        rp0, rp1 = _reflect(s["p0"], axis), _reflect(s["p1"], axis)
        best, best_key = None, None
        for j, o in enumerate(sides):
            if i == j or s["pair"] == o["pair"]:
                continue
            for reversed_match in (False, True):
                q0, q1 = (o["p0"], o["p1"]) if not reversed_match else \
                    (o["p1"], o["p0"])
                dist = max(math.hypot(rp0[0] - q0[0], rp0[1] - q0[1]),
                           math.hypot(rp1[0] - q1[0], rp1[1] - q1[1]))
                if best is None or dist < best[0]:
                    best, best_key = (dist, o, reversed_match), j
        if best is None or best[0] > epsilon:
            continue
        key = frozenset((i, best_key))
        if key in seen:
            continue
        seen.add(key)
        matches.append((s, _reencode(best[1], best[2]), best[0]))
    return matches


def _symmetry_rows(system, matches, axis_src, f_k, size_px):
    """Hobby (16) rows about the fixed parity axis, source mismatch retained."""
    rows = []
    for first, second, dist in matches:
        a1 = np.asarray(first["p0"], dtype=float)
        b1 = np.asarray(first["p1"], dtype=float)
        a2 = np.asarray(second["p0"], dtype=float)
        b2 = np.asarray(second["p1"], dtype=float)
        direct = np.array([-(b1[0] - a1[0]), b1[1] - a1[1]]) + (b2 - a2)
        norm = float(np.linalg.norm(direct))
        if norm <= 0:
            continue
        normal = np.array([direct[1], -direct[0]]) / norm
        dab = norm / 2.0
        src = (normal.dot(a2 - np.array([2.0 * axis_src - a1[0], a1[1]])),
               normal.dot(b2 - np.array([2.0 * axis_src - b1[0], b1[1]])))
        cols = []
        for key, default, m in (('t0', 0., src[0]), ('t1', 1., src[1])):
            sample_a = dd._affine_sample(first, first.get(key, default))
            sample_b = dd._affine_sample(second, second.get(key, default))
            row = (system.projected(sample_a, np.array([normal[0], -normal[1]]))
                   + system.projected(sample_b, normal))
            const = float(row @ system.points.ravel() - normal[0] * f_k - m)
            cols.append((row, const))
        factor = math.sqrt(ALPHA6 / size_px ** 3 * dab)
        (ra, ca), (rb, cb) = cols
        rows.append(((ra + rb) * math.sqrt(1.0 / 4.0) * factor,
                     (ca + cb) * math.sqrt(1.0 / 4.0) * factor))
        rows.append(((rb - ra) * math.sqrt(1.0 / 12.0) * factor,
                     (cb - ca) * math.sqrt(1.0 / 12.0) * factor))
    return rows


def _abstain(upstream_commands, reason, **extra):
    result = {"candidate_commands": upstream_commands,
              "applied": False, "reason": reason}
    result.update(extra)
    return result


def fit(source_commands, original_upstream_commands, size_px, reference,
        native_axes=(False, False), epsilon=EPS_PARITY,
        topology_checker=None):
    """One joint solve from the original upstream outline, never a restack.

    Couples Hobby (16) symmetry rows about a fixed parity-compatible axis
    with soft (17) relative-width rows; shape rows hold the outline. Curves
    abstain. Any infeasible gate returns the exact upstream commands.
    """
    if (not isinstance(native_axes, (tuple, list)) or len(native_axes) != 2
            or any(type(v) is not bool for v in native_axes)):
        return _abstain(original_upstream_commands, 'malformed-native-axes')
    if not math.isfinite(size_px) or size_px <= 0 or not math.isfinite(epsilon) or epsilon <= 0:
        return _abstain(original_upstream_commands, 'invalid-geometry-scale')
    try:
        if not dd.check_correspondence(source_commands,
                                       original_upstream_commands):
            return _abstain(original_upstream_commands, "no-correspondence")
        parsed = dd.parse_commands(source_commands)
        fitted = dd.parse_commands(original_upstream_commands)
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        return _abstain(original_upstream_commands, "malformed-commands")
    for contour in parsed["contours"]:
        for seg in contour:
            if seg[0] != "line":
                return _abstain(original_upstream_commands,
                                "curves-unsupported")
    anchors_ref = reference.get("anchors") if isinstance(reference,
                                                         dict) else None
    if not anchors_ref:
        return _abstain(original_upstream_commands, "no-reference-anchors")
    try:
        portions, _, loops, flats = dd._split_visible(parsed)
        pairs, skipped = dd._recognize(portions, loops, ownership="interval")
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        return _abstain(original_upstream_commands, "malformed-commands")
    if flats:
        return _abstain(original_upstream_commands, "curves-unsupported")
    pins = set()
    for pair in dd._upright_pairs(pairs):
        for side in (pair["a"], pair["b"]):
            pins.add(side["i0"])
            pins.add(side["i1"])
    owned = tuple(i for i, on in enumerate(native_axes[:2]) if on)
    try:
        borders = dd._visible_borders(portions)
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        return _abstain(original_upstream_commands, "malformed-commands")
    fitted_coords = fitted["oncurve"]
    prepped, details = [], list(skipped)
    for pair in pairs:
        if dd._upright_pairs([pair]):
            details.append({"pair": (pair["a"]["seg"], pair["b"]["seg"]),
                            "reason": "upright-anchor"})
            continue
        try:
            info, why = dd._prepare_pair(
                pair, borders, loops, loops, flats, flats, fitted_coords,
                size_px, exact_curves=None)
        except (ValueError, ArithmeticError):
            details.append({"pair": (pair["a"]["seg"], pair["b"]["seg"]),
                            "reason": "pair-invalid"})
            continue
        if why is not None:
            details.append({"pair": (pair["a"]["seg"], pair["b"]["seg"]),
                            "reason": why})
            continue
        bound = min(info["src_widths"]) / 2 - dd.HEADROOM
        if not bound >= dd.HEADROOM:
            details.append({"pair": info["id"],
                            "reason": "movement-budget-empty"})
            continue
        info["bound"] = bound
        prepped.append(info)
    if not prepped:
        return _abstain(original_upstream_commands, "all-abstained",
                        skipped=details)
    locus = axis_interval(source_commands, "x")
    if locus is None or locus["cmax"] - locus["cmin"] > epsilon:
        return _abstain(original_upstream_commands, "axis-uncontained",
                        skipped=details)
    waist = _waist_from_slabs(parsed)
    if waist is None:
        return _abstain(original_upstream_commands, "no-waist",
                        skipped=details)
    import statistics
    rel_med = statistics.median(a["rel"] for a in anchors_ref)
    predicted = waist["width"] * (1.0 + rel_med)
    if not predicted > 0:
        return _abstain(original_upstream_commands, "no-waist",
                        skipped=details)
    pair_mean = sum(sum(i["src_widths"]) / len(i["src_widths"])
                    for i in prepped) / len(prepped)
    if parity_target(locus["mid"],
                     pair_mean * (1.0 + rel_med)) != parity_target(
            locus["mid"], predicted):
        return _abstain(original_upstream_commands, "parity-ambiguous",
                        skipped=details)
    axis_src = locus["mid"]
    target = parity_target(axis_src, predicted)
    f_k = 2.0 * target
    waist = dict(waist, predicted=predicted, rel_med=rel_med)
    sides = []
    for info in prepped:
        for side in (info["a"], info["b"]):
            sides.append({"pair": info["id"], "p0": tuple(side["p0"]),
                          "p1": tuple(side["p1"]), "i0": side["i0"],
                          "i1": side["i1"], 't0': side['t0'], 't1': side['t1']})
    matches = _match_borders(sides, axis_src, epsilon)
    if not matches:
        return _abstain(original_upstream_commands, "no-symmetry-matches",
                        skipped=details)
    system, _, fixed, _, var_verts = dd._assemble(
        parsed, fitted_coords, prepped, anchors_ref, size_px, False,
        pins, owned)
    for row, const in _symmetry_rows(system, matches, axis_src, f_k,
                                    size_px):
        system.add("symmetry", row, const)
    soft = [(g, np.asarray(r, dtype=float), float(c))
            for g, r, c in system.rows]
    base = np.asarray(parsed['oncurve'], dtype=float)
    upstream = np.asarray(fitted_coords, dtype=float)
    gaps = (upstream - base).ravel()
    columns = [2 * v for v in sorted(var_verts) if (v, 0) not in fixed]
    if not columns:
        return _abstain(original_upstream_commands, 'no-horizontal-freedom')
    width_rows = [(r, c) for group, r, c in soft if group != 'symmetry']
    phase_rows = [(r, c) for group, r, c in soft if group == 'symmetry']
    a = np.stack([r[columns] for r, _ in width_rows])
    b = np.array([-r @ gaps - c for r, c in width_rows])
    g = np.stack([r[columns] for r, _ in phase_rows])
    h = np.array([-r @ gaps - c for r, c in phase_rows])
    bounds = np.array([min(info['bound'] for info in prepped
                          if column // 2 in {info['a']['i0'], info['a']['i1'],
                                             info['b']['i0'], info['b']['i1']})
                       for column in columns])
    solved = _bounded_equalities(a, b, g, h, bounds)
    if solved is None:
        return _abstain(original_upstream_commands,
                        'phase-bounds-incompatible', skipped=details)
    delta, qp = solved
    flat_delta = np.zeros_like(gaps)
    flat_delta[columns] = delta
    flex = gaps + flat_delta
    deltas = flat_delta.reshape(-1, 2)
    peaks = {}
    for info in prepped:
        verts = {info["a"]["i0"], info["a"]["i1"],
                 info["b"]["i0"], info["b"]["i1"]}
        peaks[info["id"]] = max(
            [float(np.linalg.norm(deltas[v])) for v in verts] + [0.0])
    over = [pid for pid, peak in peaks.items()
            if peak > next(i["bound"] for i in prepped if i["id"] == pid)]
    if over and max(peaks[i['id']] - i['bound'] for i in prepped) > 1e-9:
        return _abstain(original_upstream_commands, 'movement-budget')
    for info in prepped:
        info.setdefault("prefix", 1.0)
        info["peak"] = peaks[info["id"]]
        info["phase_applied"] = False
    table = dd._index_map(original_upstream_commands)
    candidate = [dict(cmd) for cmd in original_upstream_commands]
    flat_up = upstream.ravel()
    flat_cand = (upstream + deltas).ravel()
    for v in sorted(var_verts):
        pos = table.get(v)
        if pos is None:
            continue
        for axis in (0, 1):
            if (v, axis) in fixed:
                continue
            value = float(flat_cand[2 * v + axis])
            if value == float(flat_up[2 * v + axis]):
                continue
            rounded = dd._round_26_6(value)
            key = "x" if axis == 0 else "y"
            candidate[pos][key] = rounded
            if key + "_bits" in candidate[pos]:
                candidate[pos][key + "_bits"] = dd._f32bits(rounded)
    if dd._commands_equal(candidate, original_upstream_commands):
        return _abstain(original_upstream_commands, "no-movement",
                        skipped=details)
    validity = dd._validate(parsed, fitted, original_upstream_commands,
                            candidate, portions, prepped, pins, owned,
                            False, [], flex, source_commands,
                            topology_checker, canonical=False)
    if validity["ok"]:
        table = dd._index_map(candidate)
        inverted = {pos: idx for idx, pos in table.items()}
        for pos, cmd in enumerate(candidate):
            idx = inverted.get(pos)
            if idx is None:
                continue
            for axis in owned:
                key = "x" if axis == 0 else "y"
                if key in cmd and cmd[key + "_bits"] != dd._f32bits(
                        fitted["oncurve"][idx][axis]):
                    validity["ok"] = False
                    validity["stage"] = "pins-bits-changed"
        for v in pins:
            pos = table.get(v)
            if pos is None:
                continue
            for key in ("x", "y"):
                if key in candidate[pos] and candidate[pos][key + "_bits"] != \
                        original_upstream_commands[pos][key + "_bits"]:
                    validity["ok"] = False
                    validity["stage"] = "pins-bits-changed"
    match_rows = [(np.asarray(r, dtype=float), float(c))
                  for g, r, c in system.rows if g == "ink-match"]
    sym_rows = [(np.asarray(r, dtype=float), float(c))
                for g, r, c in system.rows if g == "symmetry"]
    flat_base_up = upstream.ravel() - base.ravel()
    try:
        flat_base_cand = (np.asarray(
            dd.parse_commands(candidate)["oncurve"], dtype=float).ravel()
            - base.ravel())
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        flat_base_cand = None
    costs = {}
    for name, rows in (("match", match_rows), ("symmetry", sym_rows)):
        up = float(sum((float(row @ flat_base_up) + const) ** 2
                       for row, const in rows))
        cand = float(sum((float(row @ flat_base_cand) + const) ** 2
                         for row, const in rows)) \
            if flat_base_cand is not None else None
        costs[name] = (up, cand)
    validity["cost_upstream"] = costs["match"][0]
    validity["cost_candidate"] = costs["match"][1]
    validity["symmetry_upstream"] = costs["symmetry"][0]
    validity["symmetry_candidate"] = costs["symmetry"][1]
    validity["cost_ok"] = (costs["match"][1] is not None
                           and costs["match"][1] < costs["match"][0])
    validity["symmetry_ok"] = (costs["symmetry"][1] is not None
                               and costs["symmetry"][1]
                               < costs["symmetry"][0])
    if not validity["cost_ok"]:
        validity["ok"] = False
        validity["stage"] = "no-cost-decrease"
    elif not validity["symmetry_ok"]:
        validity["ok"] = False
        validity["stage"] = "no-symmetry-decrease"
    achieved = dd._achieved(prepped, candidate, fitted_coords)
    widths = [(p["source_width"], p["upstream_width"],
               p["candidate_width"]) for p in achieved]
    mean = lambda k: sum(w[k] for w in widths) / len(widths)
    diagnostics = {"epsilon": epsilon, "axis_src": axis_src,
                   'qp': qp,
                   "locus": locus, "waist": waist, "parity_target": target,
                   "f_k": f_k, "matches": len(matches),
                   "widths": {"source": mean(0), "upstream": mean(1),
                              "candidate": mean(2)}}
    if not validity["ok"]:
        fallback = dd._achieved(prepped, original_upstream_commands,
                                fitted_coords)
        return {"candidate_commands": original_upstream_commands,
                "applied": False, "reason": "invalid-candidate",
                "validity": validity, "pairs": fallback,
                "skipped": details, "diagnostics": diagnostics,
                "movement": max(peaks.values()) if peaks else 0.0,
                "bound": min(i["bound"] for i in prepped),
                "size_px": size_px}
    return {"candidate_commands": candidate, "applied": True,
            "reason": "applied-joint", "validity": validity,
            "pairs": achieved, "skipped": details,
            "diagnostics": diagnostics,
            "movement": max(peaks.values()) if peaks else 0.0,
            "bound": min(i["bound"] for i in prepped), "size_px": size_px,
            "widths": {"source": mean(0), "upstream": mean(1),
                       "candidate": mean(2)},
            "reference": {"n_anchors": len(anchors_ref),
                          "rel_min": min(a["rel"] for a in anchors_ref),
                          "rel_max": max(a["rel"] for a in anchors_ref)}}
