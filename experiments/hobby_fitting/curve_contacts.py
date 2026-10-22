"""Automatic curve-contact recognition (Hobby section 6).

Recognized class: opposing axis-extrema on true Bezier curves. Two
interior extrema with parallel tangents, the same transverse coordinate
(exact Fraction equality) and strictly inward-opposing normals form a
contact whose midpoint is the exact medial candidate with radius half
the transverse separation. Boundary contact at A/B is geometric normal
by construction (AB perpendicular to both tangents), never an
equal-radii assertion. Each candidate is certified by a strictly
empty-interior disk against every other line/curve primitive (triangle
certificates test edges plus strict center-outside) plus fill evidence:
the open segment starts in ink, proved from exact contour orientation
on the certified substitution; single closed contour required, holes
fail closed. Anything uncertain is rejected with a reason. Only quads
are supported: cubic extrema need square roots, which are not exact in
Fractions.
"""

from fractions import Fraction

import numpy as np

from experiments.hobby_fitting import curve_clearance as cc
from experiments.hobby_fitting import curved_width as cw
from experiments.hobby_fitting.real_outline import parse_commands


def _contour_orientations(commands):
    """Exact per-contour orientation signs from certified substitution.

    Shoelace over the substituted joints in Fractions; each contour
    needs its own sign for the fill-side argument. Returns None when
    substitution is uncertified. Inherits the substitution
    certificate's strength, the same contract as the exact-join gate.
    """
    try:
        rep = cc.certify_substitution(commands)
    except (ArithmeticError, OverflowError, ValueError):
        return None
    if not rep.get("ok"):
        return None
    try:
        polys = cc.build_substituted_commands(commands)
    except ValueError:
        return None
    ori = {}
    cur, ci = [], -1
    for cmd in polys:
        op = cmd.get("op")
        if op == "move_to":
            cur = [(Fraction(cmd["x"]), Fraction(cmd["y"]))]
            ci += 1
        elif op == "line_to":
            cur.append((Fraction(cmd["x"]), Fraction(cmd["y"])))
        elif op == "close":
            s = sum(cur[i][0] * cur[(i + 1) % len(cur)][1]
                    - cur[(i + 1) % len(cur)][0] * cur[i][1]
                    for i in range(len(cur)))
            if s == 0:
                return None
            ori[ci] = 1 if s > 0 else -1
            cur = []
    return ori


def _starts_inside(ext, M, orient):
    """Exact fill-side check: the open segment starts in ink.

    At a smooth axis-extremum the boundary is transverse to the
    segment; contour orientation gives the interior side exactly, so
    a segment leaving toward the interior side starts in fill.
    """
    A = ext["point"]
    if ext["kind"] == "y":
        d = 1 if M[1] > A[1] else (-1 if M[1] < A[1] else 0)
        return d != 0 and d == orient * ext["sign"]
    d = 1 if M[0] > A[0] else (-1 if M[0] < A[0] else 0)
    return d != 0 and d == -orient * ext["sign"]


def _fr2(p):
    return (Fraction(p[0]), Fraction(p[1]))


def _quad_extrema(ctrls):
    """Interior axis-extrema of one quad, exact Fractions.

    Returns [(kind, t, point, tangent_sign)] with kind 'x' (dx/dt=0,
    tangent vertical) or 'y' (dy/dt=0, tangent horizontal).
    """
    P0, C, P1 = [_fr2(p) for p in ctrls]
    out = []
    for kind, coord in (("x", 0), ("y", 1)):
        denom = P0[coord] - 2 * C[coord] + P1[coord]
        if denom == 0:
            continue
        t = (P0[coord] - C[coord]) / denom
        if not 0 < t < 1:
            continue
        mt = Fraction(1) - t
        pt = tuple(mt * mt * P0[i] + 2 * mt * t * C[i] + t * t * P1[i]
                   for i in (0, 1))
        d = tuple(2 * (mt * (C[i] - P0[i]) + t * (P1[i] - C[i])) for i in (0, 1))
        if d[1 - coord] == 0:
            continue
        sign = 1 if d[1 - coord] > 0 else -1
        out.append({"kind": kind, "t": t, "point": pt, "sign": sign})
    return out


def _seg_clear(center, r2, a, b):
    """Exact: open segment AB avoids the open disk (touching allowed)."""
    ax, ay = a[0] - center[0], a[1] - center[1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return ax * ax + ay * ay >= r2
    num = ax * dx + ay * dy
    if num >= 0:
        return ax * ax + ay * ay >= r2
    if num <= -L2:
        ex, ey = ax + dx, ay + dy
        return ex * ex + ey * ey >= r2
    return (ax * ax + ay * ay) * L2 - num * num >= r2 * L2


def _subdiv_quad(ctrls, t):
    """Exact de Casteljau split of a quad at t (Fractions)."""
    P0, C, P1 = ctrls
    mt = Fraction(1) - t
    Q0 = tuple(mt * P0[i] + t * C[i] for i in (0, 1))
    Q1 = tuple(mt * C[i] + t * P1[i] for i in (0, 1))
    M = tuple(mt * Q0[i] + t * Q1[i] for i in (0, 1))
    return (P0, Q0, M), (M, Q1, P1)


def _tri_signed2(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _tri_clear(center, r2, tri):
    """Exact: triangle avoids the open disk.

    Edge checks alone are unsound: a disk can sit strictly inside a
    triangle without touching its edges. A convex triangle meeting the
    open disk either puts the disk center inside it or crosses an edge,
    so edges plus a strict center-outside test complete the
    certificate. Degenerate (zero-area) hulls reduce to their edges,
    which already contain the curve.
    """
    if not all(_seg_clear(center, r2, tri[i], tri[(i + 1) % 3])
               for i in range(3)):
        return False
    a, b, c = tri
    if _tri_signed2(a, b, c) == 0:
        return True
    s = [_tri_signed2(a, b, center), _tri_signed2(b, c, center),
         _tri_signed2(c, a, center)]
    if all(v > 0 for v in s) or all(v < 0 for v in s):
        return False
    return True


def _joint_extrema(parsed):
    """Extrema exactly on quad/line joints, exact Fractions.

    A joint is a smooth axis-extremum when both incident legs are
    exactly axis-parallel with the same nonzero transverse sign.
    """
    points = parsed["oncurve"] + parsed["offcurve"]
    no = len(parsed["oncurve"])
    incoming, outgoing = {}, {}

    def leg_point(seg, end):
        if end == "in":
            if seg[0] == "line":
                return points[seg[1]]
            return points[no + seg[1]]
        if seg[0] == "line":
            return points[seg[2]]
        return points[no + seg[1]]

    for contour in parsed["contours"]:
        for seg in contour:
            if seg[0] == "line":
                pen, nxt = seg[1], seg[2]
            elif seg[0] == "quad":
                pen, nxt = seg[2], seg[3]
            else:
                continue
            incoming.setdefault(nxt, []).append((seg, leg_point(seg, "in")))
            outgoing.setdefault(pen, []).append((seg, leg_point(seg, "out")))
    out = []
    for v in set(incoming) & set(outgoing):
        J = _fr2(points[v])
        for s_in, lp_in in incoming[v]:
            for s_out, lp_out in outgoing[v]:
                if s_in[0] not in ("line", "quad"):
                    continue
                if s_out[0] not in ("line", "quad"):
                    continue
                lin = (J[0] - lp_in[0], J[1] - lp_in[1])
                lout = (lp_out[0] - J[0], lp_out[1] - J[1])
                for kind, ax, par in (("y", 1, 0), ("x", 0, 1)):
                    if lin[ax] != 0 or lout[ax] != 0:
                        continue
                    si = 1 if lin[par] > 0 else (-1 if lin[par] < 0 else 0)
                    so = 1 if lout[par] > 0 else (-1 if lout[par] < 0 else 0)
                    if si == 0 or si != so:
                        continue
                    out.append({"kind": kind, "point": J, "sign": si,
                                "joint": v, "in_seg": s_in, "out_seg": s_out})
    return out


def recognize(source_commands):
    """Certified extrema contacts on the source outline.

    Returns (pairs, diagnostics). ``pairs`` feeds ``curved_width.fit``.
    """
    diag = {"candidates": 0, "rejected": {}, "transverse": {}}
    try:
        parsed = parse_commands(source_commands)
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        diag["rejected"]["malformed-commands"] = 1
        return [], diag
    ops = [c.get("op") if isinstance(c, dict) else None
           for c in source_commands]
    if ops.count("move_to") != 1 or not ops or ops[-1] != "close":
        diag["rejected"]["multi-contour-unsupported"] = 1
        return [], diag
    points = parsed["oncurve"] + parsed["offcurve"]
    no = len(parsed["oncurve"])
    curves = cw.curves_of(parsed)
    if any(c["kind"] != "quad" for c in curves):
        diag["rejected"]["cubic-curve-present"] = sum(
            1 for c in curves if c["kind"] != "quad")
        return [], diag
    quads = []
    qi_by_seg, ci_by_seg = {}, {}
    for ci, contour in enumerate(parsed["contours"]):
        for si, seg in enumerate(contour):
            ci_by_seg[seg] = ci
            if seg[0] != "quad":
                continue
            idx = [seg[2], no + seg[1], seg[3]]
            ctrls = [tuple(points[i]) for i in idx]
            qi_by_seg[seg] = len(quads)
            ci_by_seg[seg] = ci
            quads.append({"idx": idx, "float": ctrls,
                          "frac": [_fr2(p) for p in ctrls], "seg": seg,
                          "contour": ci})
    lines = []
    for contour in parsed["contours"]:
        for seg in contour:
            if seg[0] == "line":
                lines.append((_fr2(points[seg[1]]), _fr2(points[seg[2]])))
    orientations = _contour_orientations(source_commands)
    if not orientations:
        diag["rejected"]["uncertified-substitution"] = 1
        return [], diag
    seg_qi = qi_by_seg
    exts = []
    for qi, q in enumerate(quads):
        for ex in _quad_extrema(q["float"]):
            halves = _subdiv_quad(q["frac"], ex["t"])
            exts.append({"kind": ex["kind"], "point": ex["point"],
                         "sign": ex["sign"], "halves": list(halves),
                         "quads": {qi}, "primary": (qi, ex["t"]),
                         "origin": "interior", "contour": q["contour"]})
    diag["interior_extrema"] = len(exts)
    n_joint = 0
    for je in _joint_extrema(parsed):
        incident = []
        for seg, at in ((je["in_seg"], 1.0), (je["out_seg"], 0.0)):
            if seg[0] != "quad" or seg not in seg_qi:
                continue
            incident.append((seg_qi[seg], at))
        if not incident:
            diag["rejected"]["line-line-joint"] = \
                diag["rejected"].get("line-line-joint", 0) + 1
            continue
        n_joint += 1
        halves = [tuple(quads[qi]["frac"]) for qi, _ in incident]
        primary = incident[1] if len(incident) == 2 else incident[0]
        exts.append({"kind": je["kind"], "point": je["point"],
                     "sign": je["sign"], "halves": halves,
                     "quads": {qi for qi, _ in incident},
                     "primary": primary, "origin": "joint",
                     "contour": ci_by_seg[je["in_seg"]]})
    diag["joint_extrema"] = n_joint
    pairs = []
    for transverse, par in (("x", 0), ("y", 1)):
        groups = {}
        for e in exts:
            if (e["kind"] == "y") == (transverse == "x"):
                groups.setdefault(e["point"][par], []).append(e)
        diag["transverse"][transverse] = sum(len(v) for v in groups.values())
        for key, items in groups.items():
            for n in range(len(items)):
                for m in range(n + 1, len(items)):
                    a, b = items[n], items[m]
                    diag["candidates"] += 1
                    if a["sign"] + b["sign"] != 0:
                        diag["rejected"]["tangents-not-opposing"] = \
                            diag["rejected"].get("tangents-not-opposing", 0) + 1
                        continue
                    A, B = a["point"], b["point"]
                    r = abs(A[1 - par] - B[1 - par]) / 2
                    if r <= 0:
                        diag["rejected"]["coincident"] = \
                            diag["rejected"].get("coincident", 0) + 1
                        continue
                    M = tuple((A[i] + B[i]) / 2 for i in (0, 1))
                    r2 = r * r
                    ok, why = _contact_clear(
                        M, r2, quads, lines, a, b)
                    if not ok:
                        diag["rejected"][why] = \
                            diag["rejected"].get(why, 0) + 1
                        continue
                    inside_a = _starts_inside(
                        a, M, orientations.get(a["contour"], 0))
                    inside_b = _starts_inside(
                        b, M, orientations.get(b["contour"], 0))
                    if not (inside_a or inside_b):
                        diag["rejected"]["midpoint-not-ink"] = \
                            diag["rejected"].get("midpoint-not-ink", 0) + 1
                        continue
                    pairs.append(_pair_dict(
                        quads, a, b, M, no))
    return pairs, diag


def _quad_disk_clear(M, r2, ctrl, depth=0):
    """Certify squared distance using the Bernstein convex-hull property.

    The product of two quadratic Bernstein polynomials has coefficients
    sum(C(2,i) C(2,j) dot(P_i-M,P_j-M))/C(4,i+j). Nonnegative
    coefficients certify distance squared minus radius squared >= 0,
    including a tangent contact where a triangle hull is inconclusive.
    Unresolved subdivision at the computational cap abstains.
    """
    from math import comb

    points = [tuple(p[k] - M[k] for k in (0, 1)) for p in ctrl]
    coefficients = []
    for k in range(5):
        value = sum(
            (points[i][0] * points[j][0] + points[i][1] * points[j][1])
            * Fraction(comb(2, i) * comb(2, j), comb(4, k))
            for i in range(3) for j in range(3) if i + j == k)
        coefficients.append(value - r2)
    if min(coefficients) >= 0:
        return True
    if max(coefficients) < 0 or depth >= 12:
        return False
    left, right = _subdiv_quad(ctrl, Fraction(1, 2))
    return (_quad_disk_clear(M, r2, left, depth + 1)
            and _quad_disk_clear(M, r2, right, depth + 1))


def _contact_clear(M, r2, quads, lines, a, b):
    """Strictly empty open disk: every primitive clears or touches."""
    own = a["quads"] | b["quads"]
    for s, e in lines:
        if not _seg_clear(M, r2, s, e):
            return False, "line-contact"
    for n, q in enumerate(quads):
        if n in own:
            continue
        if not _quad_disk_clear(M, r2, tuple(q["frac"])):
            return False, "curve-contact"
    for e in (a, b):
        for tri in e["halves"]:
            if not _quad_disk_clear(M, r2, tri):
                return False, "own-curve-contact"
    return True, "clear"


def _pair_dict(quads, a, b, M, no):
    def speed(qi, t):
        q = quads[qi]
        P0, C, P1 = [_fr2(p) for p in q["float"]]
        mt = 1.0 - float(t)
        t = float(t)
        d = [2 * (mt * (C[i] - float(P0[i])) + t * (float(P1[i]) - C[i]))
             for i in (0, 1)]
        return float(np.linalg.norm(d))

    (qi, ta), (qj, tb) = a["primary"], b["primary"]
    shape = []
    for e in (a, b):
        for qi2 in sorted(e["quads"]):
            ctrl = [int(v) for v in quads[qi2]["idx"]]
            if ctrl not in shape:
                shape.append(ctrl)
    return {"a_ctrl": [int(v) for v in quads[qi]["idx"]],
            "b_ctrl": [int(v) for v in quads[qj]["idx"]],
            "a_t": float(ta), "b_t": float(tb),
            "medial": [float(M[0]), float(M[1])],
            "arc": (speed(qi, ta) + speed(qj, tb)) / 2,
            "shape_ctrl": shape}


def fit_glyph(source_commands, upstream_commands, size_px, reference,
              native_axes=(False, False)):
    """Harness API: automatic recognition then source-relative curve fit."""
    pairs, recog = recognize(source_commands)
    if not pairs:
        return {"candidate_commands": upstream_commands, "applied": False,
                "reason": "no-certified-pairs", "widths": None,
                "recognition": recog,
                "fixed": {"native_axes": list(native_axes[:2])}}
    out = cw.fit(source_commands, upstream_commands, size_px, reference,
                 native_axes, pairs)
    out["recognition"] = recog
    if out.get("widths"):
        for row, p in zip(out["widths"], pairs):
            n = _pair_normal(source_commands, p)
            row["effectibility_x"] = abs(float(n[0])) if n is not None else None
    return out


def _pair_normal(source_commands, p):
    try:
        parsed = parse_commands(source_commands)
        points = parsed["oncurve"] + parsed["offcurve"]
        qa = cw._eval([tuple(points[i]) for i in p["a_ctrl"]], p["a_t"])
        qb = cw._eval([tuple(points[i]) for i in p["b_ctrl"]], p["b_t"])
        d = np.asarray(qb) - np.asarray(qa)
        n = float(np.linalg.norm(d))
        return (d / n).tolist() if n > 0 else None
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return None
