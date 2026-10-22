"""Hersch fixed-direction diagonal constraints with shared Hobby curve controls.

The source border classifier and integer target are reused unchanged.
Hobby (1)-(3), (17), and section 6 supply the distortion/width objective.
Hersch section 6 Figure 25 supplies two parallel borders at integer axis
separation. With upstream Y retained, both those constraints and curve
joint cross products are linear in the remaining X displacements.
"""

import math

import numpy as np

from experiments.hobby_fitting import curved_width as cw
from experiments.hobby_fitting import direct_diagonal as dd
from experiments.hobby_fitting import smooth_curve_fit as scf
from experiments.hobby_fitting.prototype import System, width_weight
from experiments.hobby_fitting.real_outline import check_correspondence, parse_commands


def _abstain(upstream, reason, **extra):
    return dict(candidate_commands=upstream, applied=False, reason=reason, **extra)


def _convex_qp(a, b, g, h, c, lower, bound):
    """Fixed convex least squares, linear constraints, and box bounds.

    SLSQP (Kraft 1988, SciPy reference) supplies the numerical candidate.
    SVD removes redundant equality rows; primal feasibility and the convex
    KKT normal-cone condition are checked independently before delivery.
    """
    from scipy.optimize import Bounds, LinearConstraint, minimize, nnls

    n = a.shape[1]
    norms = np.linalg.norm(g, axis=1)
    nonzero = norms > 0
    if np.any(abs(h[~nonzero]) > 1e-9):
        return None
    g, h = g[nonzero] / norms[nonzero, None], h[nonzero] / norms[nonzero]
    u, singular, vh = np.linalg.svd(g, full_matrices=True)
    rank = int(np.sum(singular > max(g.shape) * singular[0] * np.finfo(float).eps)) if len(singular) else 0
    eq = vh[:rank]
    target = (u[:, :rank].T @ h) / singular[:rank]
    initial = eq.T @ target
    if np.max(abs(g @ initial - h), initial=0) > 1e-8:
        return None
    norms_c = np.linalg.norm(c, axis=1)
    valid = norms_c > 0
    if np.any(lower[~valid] > 1e-9):
        return None
    c, lower = c[valid] / norms_c[valid, None], lower[valid] / norms_c[valid]
    scale = max(1., float(np.linalg.norm(a, 2)))
    aa, bb = a / scale, b / scale
    constraints = [LinearConstraint(eq, target, target)] if rank else []
    if len(c):
        constraints.append(LinearConstraint(c, lower, np.inf))
    result = minimize(lambda x: .5 * float(np.linalg.norm(aa @ x - bb) ** 2),
                      np.clip(initial, -bound, bound), jac=lambda x: aa.T @ (aa @ x - bb),
                      bounds=Bounds(-np.full(n, bound), np.full(n, bound)),
                      constraints=constraints, method='SLSQP',
                      options=dict(ftol=1e-14, maxiter=500))
    x = result.x
    equality_error = float(np.max(abs(g @ x - h), initial=0))
    slack = c @ x - lower
    if (not result.success or not np.isfinite(x).all() or equality_error > 1e-8
            or np.min(slack, initial=0) < -1e-8 or np.max(abs(x), initial=0) > bound + 1e-8):
        return None
    active = [row for row, gap in zip(c, slack) if gap <= 1e-7]
    for i, value in enumerate(x):
        if bound - abs(value) <= 1e-7:
            row = np.zeros(n)
            row[i] = -1 if value > 0 else 1
            active.append(row)
    z = vh[rank:].T
    gradient = aa.T @ (aa @ x - bb)
    projected = z.T @ gradient
    if active and z.shape[1]:
        _, residual = nnls(z.T @ np.asarray(active).T, projected, maxiter=10 * max(1, len(active)))
    else:
        residual = float(np.linalg.norm(projected))
    if residual > 1e-7 * (1 + np.linalg.norm(gradient)):
        return None
    return x, dict(iterations=int(result.nit), equality_error=equality_error,
                   inequality_slack=float(np.min(slack, initial=0)), stationarity_error=float(residual))


def recognize(source, upstream, size, reference):
    """Certified existing border portions, restricted to curve attachments."""
    parsed = parse_commands(source)
    if len(parsed['contours']) != 1 or any(s[0] not in ('line', 'quad')
                                         for c in parsed['contours'] for s in c):
        return [], ['unsupported-contour']
    curved = {v for c in parsed['contours'] for s in c if s[0] == 'quad' for v in (s[2], s[3])}
    if not curved:
        return [], ['no-curve-attachments']
    portions, _, loops, flats = dd._split_visible(parsed, canonical=True)
    pairs, _ = dd._recognize(portions, loops, ownership='interval')
    borders = dd._visible_borders(portions)
    curves = dd._curve_controls(parsed)
    prepared, skipped = [], []
    for pair in pairs:
        a, b = pair['a'], pair['b']
        if dd._axis_of(a['p0'], a['p1']) is not None or dd._axis_of(b['p0'], b['p1']) is not None:
            continue
        if not {a['i0'], a['i1'], b['i0'], b['i1']} & curved:
            continue
        info, reason = dd._prepare_pair(pair, borders, loops, loops, flats, flats,
                                        parse_commands(upstream)['oncurve'], size,
                                        exact_curves=curves)
        if info is None:
            skipped.append(reason)
            continue
        gate = dd._grid_target(info, reference['anchors'], size)
        if gate is None:
            skipped.append('no-grid-target')
            continue
        info['gate'] = gate
        prepared.append(info)
    return prepared, skipped


def fit(source_commands, upstream_commands, size_px, reference,
        native_axes=(False, False), topology_checker=None):
    """One bounded solve from original upstream; unsupported results abstain."""
    if not scf._valid_axes(native_axes):
        return _abstain(upstream_commands, 'malformed-native-axes')
    if native_axes[0]:
        return _abstain(upstream_commands, 'native-X-owned')
    try:
        if not math.isfinite(size_px) or size_px <= 0 or not check_correspondence(source_commands, upstream_commands):
            return _abstain(upstream_commands, 'no-correspondence')
        if not isinstance(reference, dict) or not reference.get('anchors'):
            return _abstain(upstream_commands, 'no-reference-anchors')
        parsed, fitted = map(parse_commands, (source_commands, upstream_commands))
        base = np.asarray(parsed['oncurve'] + parsed['offcurve'], float)
        up = np.asarray(fitted['oncurve'] + fitted['offcurve'], float)
        if base.shape != up.shape or not np.isfinite(base).all() or not np.isfinite(up).all():
            return _abstain(upstream_commands, 'malformed-coordinates')
        if np.any(base * 64 != np.rint(base * 64)) or np.any(up * 64 != np.rint(up * 64)):
            return _abstain(upstream_commands, 'non-26.6-input')
        no = len(parsed['oncurve'])
        prepared, skipped = recognize(source_commands, upstream_commands, size_px, reference)
        if not prepared:
            return _abstain(upstream_commands, 'no-attached-diagonals', skipped=skipped)
        weld = scf._weld_map(parsed, base)
        if weld != scf._weld_map(fitted, up) or any(tuple(up[d]) != tuple(up[c]) for d, c in weld.items()):
            return _abstain(upstream_commands, 'weld-mismatch')
        involved = {v for info in prepared for edge in (info['a'], info['b'])
                    for v in (edge['i0'], edge['i1'])}
        curves = cw.curves_of(parsed)
        # A shared curve chain carries its controls together; a remote straight
        # anchor is not released merely because an incident edge is regularized.
        while True:
            grown = involved | {i for c in curves if set(c['idx']) & involved for i in c['idx']}
            grown |= {weld.get(i, i) for i in grown}
            if grown == involved:
                break
            involved = grown
        upright = {v for c in parsed['contours'] for s in c
                   if s[0] == 'line' and base[s[1], 0] == base[s[2], 0]
                   and base[s[1], 1] != base[s[2], 1] for v in (s[1], s[2])}
        upright |= {weld.get(v, v) for v in tuple(upright)}
        cols = sorted(v for v in involved if v not in upright and v not in weld)
        if not cols:
            return _abstain(upstream_commands, 'no-free-controls')
        system = System(base, size_px)
        for c in curves:
            if set(c['idx']) & involved:
                cw._add_quad_shape(system, c['idx'])
        for contour in parsed['contours']:
            for s in contour:
                if s[0] == 'line' and {s[1], s[2]} & involved and tuple(base[s[1]]) != tuple(base[s[2]]):
                    system.edge(s[1], s[2])
        # Variables are upstream displacements. Source directions remain frozen,
        # while the distortion residual vanishes at the upstream fit.
        objective = [(np.asarray(row), 0.) for group, row, constant in system.rows]
        gaps = (up - base).ravel()
        hard = []
        for info in prepared:
            a, b, n, gate = info['a'], info['b'], info['normal'], info['gate']
            for edge in (a, b):
                row = system.projected(dd._affine_sample(edge, edge['t1']), n,
                                       dd._affine_sample(edge, edge['t0']))
                hard.append(('parallel', row, float(row @ up.ravel())))
            ta = a['t0'] + (a['t1'] - a['t0']) * gate['fa']
            tb = b['t0'] + (b['t1'] - b['t0']) * gate['fb']
            row = system.projected(dd._affine_sample(b, tb), n, dd._affine_sample(a, ta))
            hard.append(('separation', row, float(row @ up.ravel() - gate['target'])))
            for station in info['stations']:
                hit = station['hit']
                ta = a['t0'] + (a['t1'] - a['t0']) * hit['sa']
                tb = b['t0'] + (b['t1'] - b['t0']) * hit['sb']
                pair = system.pair(dd._affine_sample(a, ta), dd._affine_sample(b, tb),
                                   info['arc'], 'ink', medial=hit['center'])
                for anchor in reference['anchors']:
                    tangent = dd._acute(pair.tangent, anchor['tangent'])
                    weight = info['arc'] * anchor['length'] * width_weight(
                        pair.width, anchor['source_width'], tangent, anchor['tangent'], size_px)
                    scale = math.sqrt(weight)
                    objective.append((pair.error * scale,
                                      float(pair.error @ gaps + anchor['rel']) * scale))
        joints = []
        for j, occurrences in scf._joints(parsed, base, no).items():
            for occ in occurrences:
                iv = occ['prev'][1] if occ['prev'][0] == 'line' else no + occ['prev'][1]
                ov = occ['seg'][2] if occ['seg'][0] == 'line' else no + occ['seg'][1]
                if not {j, iv, ov} & involved:
                    continue
                if occ['degenerate']:
                    return _abstain(upstream_commands, 'degenerate-joint')
                curved_join = occ['prev'][0] == 'quad' or occ['seg'][0] == 'quad'
                # Hersch's border rotation changes angular line-line corners.
                # Their orientation is checked below; curve joins and collinear
                # subdivision joints retain exact tangent/cross constraints.
                constrained = curved_join or occ['smooth']
                if constrained:
                    grow, reason = scf._g1_row(up, j, occ['prev'], occ['seg'], no, size_px, occ['smooth'])
                    if grow is None:
                        return _abstain(upstream_commands, reason)
                    row, constant, _ = grow
                    hard.append(('joint', row, constant))
                joints.append((j, occ, iv, ov, constrained))
        def reduce_row(row):
            row = np.asarray(row).copy()
            for duplicate, canonical in weld.items():
                row[2 * canonical] += row[2 * duplicate]
            return row[[2 * v for v in cols]]
        mat = np.array([reduce_row(r) for r, c in objective])
        rhs = np.array([-c for r, c in objective])
        g = np.array([reduce_row(r) for _, r, c in hard])
        h = np.array([-c for _, r, c in hard])
        active = np.linalg.norm(g, axis=1) > 0
        if np.any(abs(h[~active]) > 1e-9):
            return _abstain(upstream_commands, 'fixed-constraints-incompatible')
        radius = min(min(p['src_widths']) / 2 for p in prepared)
        bound = radius - dd.HEADROOM
        if bound <= 0:
            return _abstain(upstream_commands, 'movement-budget-empty')
        inequalities = []
        # Hersch section 2's quadratic derivatives: the signed curvature is
        # cross(C-P0,P1-C), linear in X when Y is fixed. The four source-leg
        # dot products certify forward tangents over the entire interval.
        # One 26.6 product quantum plus the exact X-rounding reserve makes
        # each strict sign representable without a curvature threshold.
        for curve in curves:
            if not set(curve['idx']) & involved:
                continue
            p0, ctrl, p1 = curve['idx']
            su, sv = base[ctrl] - base[p0], base[p1] - base[ctrl]
            source_cross = su[0] * sv[1] - su[1] * sv[0]
            if source_cross == 0:
                return _abstain(upstream_commands, 'source-degenerate-curvature')
            row = np.zeros(2 * len(base))
            row[2 * p0] = up[ctrl, 1] - up[p1, 1]
            row[2 * ctrl] = up[p1, 1] - up[p0, 1]
            row[2 * p1] = up[p0, 1] - up[ctrl, 1]
            row *= 1 if source_cross > 0 else -1
            reserve = sum(abs(reduce_row(row))) / 128 + 1 / 4096
            inequalities.append((reduce_row(row), reserve - float(row @ up.ravel())))
            for i, j in ((p0, ctrl), (ctrl, p1)):
                for source_leg in (su, sv):
                    row = np.zeros(2 * len(base))
                    row[2 * j], row[2 * i] = source_leg[0], -source_leg[0]
                    value = float(np.dot(up[j] - up[i], source_leg))
                    reserve = sum(abs(reduce_row(row))) / 128 + 1 / 4096
                    inequalities.append((reduce_row(row), reserve - value))
        inequality_matrix = np.array([row for row, value in inequalities])
        inequality_lower = np.array([value for row, value in inequalities])
        solved = _convex_qp(mat, rhs, g[active], h[active], inequality_matrix, inequality_lower, bound)
        if solved is None:
            return _abstain(upstream_commands, 'constraints-incompatible')
        delta, qp = solved
        raw = up.copy()
        for v, displacement in zip(cols, delta):
            raw[v, 0] += displacement
        for duplicate, canonical in weld.items():
            raw[duplicate] = raw[canonical]
        cand = raw.copy()
        for v in cols:
            cand[v, 0] = scf._round_26_6(float(cand[v, 0]))
        for duplicate, canonical in weld.items():
            cand[duplicate] = cand[canonical]
        if np.max(np.linalg.norm(cand - up, axis=1), initial=0) > radius:
            return _abstain(upstream_commands, 'rounded-movement-budget')
        hard_checks = []
        for kind, row, constant in hard:
            raw_error = abs(float(row @ (raw - up).ravel() + constant))
            error = abs(float(row @ (cand - up).ravel() + constant))
            allowance = sum(abs(row[2 * v]) / 128 for v in range(len(base)) if raw[v, 0] != up[v, 0])
            ok = raw_error <= 1e-8 * (1 + abs(constant)) and error <= allowance + 1e-9
            hard_checks.append(dict(kind=kind, raw_error=raw_error, rounded_error=error,
                                    allowance=allowance, ok=bool(ok)))
            if not ok:
                return _abstain(upstream_commands, 'rounded-hard-constraint', hard_checks=hard_checks)
        continuity = []
        for j, occ, iv, ov, constrained in joints:
            raw_cross, li, lo = scf._cross_of(raw, j, occ['prev'], occ['seg'], no)
            old_cross, old_li, old_lo = scf._cross_of(up, j, occ['prev'], occ['seg'], no)
            cross, new_li, new_lo = scf._cross_of(cand, j, occ['prev'], occ['seg'], no)
            source_cross, _, _ = scf._cross_of(base, j, occ['prev'], occ['seg'], no)
            target = 0. if occ['smooth'] else old_cross
            moved = tuple((raw[v, 0] != up[v, 0], False) for v in (iv, j, ov))
            allowance = scf._quant_cross_bound(li, lo, moved)
            ok = bool(np.linalg.norm(new_li) > 0 and np.linalg.norm(new_lo) > 0)
            if constrained:
                ok &= abs(raw_cross - target) <= 1e-8 * (1 + abs(target)) and abs(cross - target) <= allowance + 1e-9
                ok &= bool(float(np.dot(new_li, old_li)) > 0 and float(np.dot(new_lo, old_lo)) > 0)
                if occ['smooth']:
                    ok &= bool(float(np.dot(new_li, new_lo)) > 0)
            elif source_cross:
                ok &= cross * source_cross > 0
            continuity.append(dict(joint=j, constrained=constrained, smooth=occ['smooth'],
                                   raw_cross=raw_cross, raw_target=target if constrained else None,
                                   source_cross=source_cross, cross_up=old_cross,
                                   cross_cand=cross, allowed=allowance, ok=bool(ok)))
            if not ok:
                return _abstain(upstream_commands, 'joint-continuity', continuity=continuity)
        moved = {i for i in range(len(base)) if tuple(cand[i]) != tuple(up[i])}
        for c in curves:
            if set(c['idx']) & moved:
                ok, reason = cw._quad_interval_ok([tuple(base[i]) for i in c['idx']],
                                                 [tuple(cand[i]) for i in c['idx']])
                if not ok:
                    return _abstain(upstream_commands, 'curve-' + reason,
                                    curve_indices=c['idx'],
                                    source_controls=[tuple(base[i]) for i in c['idx']],
                                    upstream_controls=[tuple(up[i]) for i in c['idx']],
                                    candidate_controls=[tuple(cand[i]) for i in c['idx']])
        clear, reason = scf._clearance_ok([], cand, parsed, moved, up, set())
        if not clear:
            return _abstain(upstream_commands, 'clearance-' + reason)
        commands = scf._emit(upstream_commands, cand, no)
        gate = (topology_checker(source_commands, upstream_commands, commands) if topology_checker
                else scf._topology_gate(source_commands, upstream_commands, commands))
        if not gate.get('ok'):
            return _abstain(upstream_commands, 'topology', topology=gate)
        if dd._commands_equal(commands, upstream_commands):
            return _abstain(upstream_commands, 'no-movement')
        return dict(candidate_commands=commands, applied=True, reason='attached-grid',
                    diagnostics=dict(native_axes=list(native_axes), retained_upstream_axes=[native_axes[0], True],
                                     upright_x_pins=sorted(upright), qp=qp),
                    bound=bound, radius=radius,
                    movement=float(np.max(np.linalg.norm(cand - up, axis=1))),
                    hard_checks=hard_checks, continuity=continuity, topology=gate,
                    pairs=[dict(id=p['id'], source_width=sum(p['src_widths']) / len(p['src_widths']),
                                normal=list(p['normal']), gate=p['gate']) for p in prepared], skipped=skipped)
    except (KeyError, TypeError, ValueError, ArithmeticError, IndexError) as error:
        return _abstain(upstream_commands, 'unsupported-input', detail=str(error))
