"""Certified curve-to-polyline substitution for straight topology checks.

Theorem (substitution): let each curve piece have strictly monotone
projection along its endpoint chord (control differences dot chord all
strictly positive). Then the piece arc is a graph over the chord axis,
hence simple (a graph may still cross its chord); the straight
homotopy arc-to-chord stays inside the piece control hull (Shene
convex-hull property; de Casteljau subdivision yields exact sub-pieces).
If every piece hull meets every other boundary primitive hull in at
most shared incident junctions (exact certificate below), the homotopy
never crosses another boundary, so replacing curves by their joint
polylines preserves the arrangement topology. Source, upstream and
candidate are certified independently; the unchanged straight checker
then compares the three polylines. Curve controls must be bit-identical
upstream-to-candidate. All predicates are exact Fractions; touch beyond
a shared junction, degeneracy, or inexact joints fail closed.
"""

import struct
from fractions import Fraction


def _fr(p):
    return (Fraction(p[0]), Fraction(p[1]))


def orient(a, b, c):
    """Exact orientation sign of (a, b, c): +1, -1, or 0."""
    v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return 1 if v > 0 else (-1 if v < 0 else 0)


def convex_hull(points):
    """Monotone-chain hull over exact Fractions; collinear interiors drop."""
    pts = sorted(set(_fr(p) for p in points))
    if len(pts) <= 2:
        return list(pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _edges(poly):
    n = len(poly)
    return [(poly[i], poly[(i + 1) % n]) for i in range(n)] if n >= 2 else []


def strictly_disjoint(poly_p, poly_q):
    """True only with a strict separating-axis gap; touch fails closed."""
    axes = []
    for poly in (poly_p, poly_q):
        for a, b in _edges(poly):
            n = (a[1] - b[1], b[0] - a[0])
            if n != (Fraction(0), Fraction(0)):
                axes.append(n)
    if not axes:
        return False
    for n in axes:
        ps = [p[0] * n[0] + p[1] * n[1] for p in poly_p]
        qs = [q[0] * n[0] + q[1] * n[1] for q in poly_q]
        if max(ps) < min(qs) or max(qs) < min(ps):
            return True
    return False


def subdivide(ctrls):
    """One exact de Casteljau step at t=1/2; returns (left, right)."""
    level = [_fr(p) for p in ctrls]
    left, right = [level[0]], [level[-1]]
    while len(level) > 1:
        level = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                 for a, b in zip(level, level[1:])]
        left.append(level[0])
        right.append(level[-1])
    return left, list(reversed(right))


def piece_chains(ctrls, depth):
    """Exact dyadic control chains of the 2**depth sub-pieces."""
    pieces = [[_fr(p) for p in ctrls]]
    for _ in range(depth):
        halves = []
        for piece in pieces:
            halves.extend(subdivide(piece))
        pieces = halves
    return pieces


def piece_hulls(ctrls, depth):
    """Control hulls of 2**depth dyadic sub-pieces; depth 0 keeps one."""
    return [convex_hull(piece) for piece in piece_chains(ctrls, depth)]


def swept_hull(seg_old, seg_new):
    """Convex hull of the old/new straight endpoints."""
    return convex_hull([seg_old[0], seg_old[1], seg_new[0], seg_new[1]])


def _on_segment(a, b, p):
    return (orient(a, b, p) == 0
            and min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= p[1] <= max(a[1], b[1]))


def _strictly_outside(pt, poly):
    """Exact segment-aware outside test via fan triangulation."""
    if len(poly) == 1:
        return pt != poly[0]
    if len(poly) == 2:
        a, b = poly
        return not (pt == a or pt == b or _on_segment(a, b, pt))
    v0 = poly[0]
    ccw = orient(poly[0], poly[1], poly[2]) > 0
    for i in range(1, len(poly) - 1):
        tri = (v0, poly[i], poly[i + 1])
        signs = {orient(tri[0], tri[1], pt), orient(tri[1], tri[2], pt),
                 orient(tri[2], tri[0], pt)}
        if ccw and signs <= {0, 1}:
            return False
        if not ccw and signs <= {0, -1}:
            return False
    return True


def hulls_meet_only_at(poly_p, poly_q, shared):
    """Exact certificate that convex hulls intersect at most at shared.

    No proper edge crossing; every segment contact point is exactly the
    shared junction (collinear opposite-ray tangency allowed); no vertex
    of either hull lies inside or on the other hull except the shared
    junction itself.
    """
    for a, b in _edges(poly_p):
        for c, d in _edges(poly_q):
            o1, o2 = orient(a, b, c), orient(a, b, d)
            o3, o4 = orient(c, d, a), orient(c, d, b)
            if o1 * o2 < 0 and o3 * o4 < 0:
                return False
            for p, u, v in ((c, a, b), (d, a, b),
                            (a, c, d), (b, c, d)):
                if _on_segment(u, v, p) and p != shared:
                    return False
    if not all(_strictly_outside(v, poly_q)
               for v in poly_p if v != shared):
        return False
    return all(_strictly_outside(v, poly_p)
               for v in poly_q if v != shared)


def _contact_only_at(swept, hull, shared):
    return hulls_meet_only_at(swept, hull, shared)


def is_chord_monotone(ctrls):
    """Strictly positive projection of every control leg on the chord.

    The derivative is a positive Bernstein combination of the legs, so
    the arc projection is strictly increasing: the piece is a graph over
    its chord axis, hence simple. A graph may still cross its chord; the
    arc-to-chord interpolation stays a graph homotopy inside the hull.
    Zero chord or any non-positive leg projection fails closed.
    """
    pts = [_fr(p) for p in ctrls]
    chord = (pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])
    if chord == (Fraction(0), Fraction(0)):
        return False
    return all((b[0] - a[0]) * chord[0] + (b[1] - a[1]) * chord[1] > 0
               for a, b in zip(pts, pts[1:]))


def edge_vs_curve_clear(seg_old, seg_new, ctrls, depth=4):
    """Certify one straight sweep against one fixed curve.

    The swept hull contains the linear homotopy of the straight edge.
    Returns (True, reason) for strict separation, or when every
    intersecting sub-hull meets the sweep solely at one pinned point
    that is an endpoint of both segments and a curve endpoint, with
    the remaining old/new rays strictly unreversed (exact dot > 0, so
    the ray neither collapses nor flips during the homotopy). No
    tangent test: the sweep certificate stands on its own. Anything
    else fails closed as curve contact, ray collapse, or reversal.
    """
    old = (_fr(seg_old[0]), _fr(seg_old[1]))
    new = (_fr(seg_new[0]), _fr(seg_new[1]))
    swept = convex_hull([old[0], old[1], new[0], new[1]])
    for hull in piece_hulls(ctrls, depth):
        if strictly_disjoint(swept, hull):
            continue
        pts = [_fr(p) for p in ctrls]
        shared = None
        for end in (pts[0], pts[-1]):
            if (end == old[0] or end == old[1]) and (
                    end == new[0] or end == new[1]):
                shared = end
                break
        if shared is None:
            return False, "curve-contact"
        old_far = old[1] if old[0] == shared else old[0]
        new_far = new[1] if new[0] == shared else new[0]
        dot = ((old_far[0] - shared[0]) * (new_far[0] - shared[0])
               + (old_far[1] - shared[1]) * (new_far[1] - shared[1]))
        if dot == 0:
            return False, "ray-collapse"
        if dot < 0:
            return False, "ray-reversal"
        if not _contact_only_at(swept, hull, shared):
            return False, "curve-contact"
    return True, "clear"


def movement_clear(old_segs, new_segs, curves, depth=4):
    """Certify every straight sweep against every fixed curve."""
    for old, new in zip(old_segs, new_segs):
        for ctrls in curves:
            ok, reason = edge_vs_curve_clear(old, new, ctrls, depth)
            if not ok:
                return False, reason
    return True, "clear"


def _coord_finite(cmd, keys):
    for key in keys:
        value = cmd.get(key) if isinstance(cmd, dict) else None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            return False
    return True


def _parse_contours(commands):
    """Contours as primitive lists plus closed flags; malformed fails.

    Returns (contours, closed) or None. Strict grammar: move while a
    contour is open, any operation after close without a new move, a
    missing close, unknown ops, and bad/non-finite coordinates all fail
    closed. An explicit close materializes the implicit closing edge
    when non-degenerate, so the certificate sees exactly the edges the
    substituted outline and the checker use; wraparound adjacency is
    allowed solely on closed contours.
    """
    contours, closed, starts = [], [], []
    pt, contour_start, open_contour = None, None, False
    coord_keys = {"move_to": ("x", "y"), "line_to": ("x", "y"),
                  "quad_to": ("x1", "y1", "x", "y"),
                  "curve_to": ("x1", "y1", "x2", "y2", "x", "y"),
                  "close": ()}
    for cmd in commands:
        op = cmd.get("op") if isinstance(cmd, dict) else None
        if op not in coord_keys or not _coord_finite(cmd, coord_keys[op]):
            return None
        if op == "move_to":
            if open_contour:
                return None
            contours.append([])
            closed.append(False)
            starts.append((cmd["x"], cmd["y"]))
            pt, contour_start, open_contour = starts[-1], starts[-1], True
        elif op in ("line_to", "quad_to", "curve_to"):
            if not open_contour:
                return None
            if op == "line_to":
                q = (cmd["x"], cmd["y"])
                # The CGAL arrangement reference omits exact zero edges:
                # they have no directed extent or winding. Normalize only
                # certificate primitives; delivered commands stay intact.
                if pt != q:
                    contours[-1].append(("line", pt, q))
                pt = q
            else:
                if op == "quad_to":
                    ctrls = (pt, (cmd["x1"], cmd["y1"]),
                             (cmd["x"], cmd["y"]))
                else:
                    ctrls = (pt, (cmd["x1"], cmd["y1"]),
                             (cmd["x2"], cmd["y2"]), (cmd["x"], cmd["y"]))
                contours[-1].append(("curve", ctrls))
                pt = ctrls[-1]
        elif op == "close":
            if not open_contour:
                return None
            if pt != contour_start:
                contours[-1].append(("line", pt, contour_start))
            closed[-1] = True
            open_contour = False
    if open_contour:
        return None
    return contours, closed


def _prim_hull(points):
    return convex_hull(points)


def certify_substitution(commands, depth=0):
    """Certify curve-to-polyline substitution for one outline.

    Every curve piece at the dyadic depth must be chord-monotone, and
    every piece hull must be strictly disjoint from every other
    primitive hull except incident-adjacent ones sharing exactly their
    junction (hulls_meet_only_at, tangency allowed). Returns a report
    dict; ok False names the first failing check. Joints must also be
    exactly float-representable for the polyline build.
    """
    parsed = _parse_contours(commands)
    if parsed is None:
        return {"ok": False, "reason": "malformed-commands", "depth": depth}
    contours, closed = parsed
    entries = []
    for ci, contour in enumerate(contours):
        for si, prim in enumerate(contour):
            if prim[0] == "line":
                entries.append(("line", ci, si, 0,
                                [_fr(prim[1]), _fr(prim[2])]))
            else:
                chains = piece_chains(list(prim[1]), depth)
                for k, chain in enumerate(chains):
                    entries.append(("curve", ci, si, k, chain))
    last_piece = 2 ** depth - 1

    def adjacent(a, b):
        if a[1] != b[1]:
            return None
        n = len(contours[a[1]])
        wrap_ok = closed[a[1]]
        consecutive = (
            (a[2] == b[2] and abs(a[3] - b[3]) == 1)
            or ((a[2] + 1 == b[2]
                 or (wrap_ok and (a[2] + 1) % n == b[2]))
                and a[3] == (last_piece if a[0] == "curve" else 0)
                and b[3] == 0)
            or ((b[2] + 1 == a[2]
                 or (wrap_ok and (b[2] + 1) % n == a[2]))
                and b[3] == (last_piece if b[0] == "curve" else 0)
                and a[3] == 0))
        if not consecutive:
            return None
        for v in (a[4][0], a[4][-1]):
            if v == b[4][0] or v == b[4][-1]:
                return v
        return None

    joints = []
    for entry in entries:
        if entry[0] != "curve":
            continue
        if not is_chord_monotone(entry[4]):
            return {"ok": False, "reason": "nonmonotone-piece",
                    "depth": depth,
                    "at": (entry[1], entry[2], entry[3])}
        chain = entry[4]
        joints.append(chain[-1])
    for i, entry in enumerate(entries):
        if entry[0] != "curve":
            continue
        hull = convex_hull(entry[4])
        for j, other in enumerate(entries):
            if i == j:
                continue
            other_hull = _prim_hull(other[4])
            if strictly_disjoint(hull, other_hull):
                continue
            shared = adjacent(entry, other)
            if shared is not None and hulls_meet_only_at(
                    hull, other_hull, shared):
                continue
            return {"ok": False, "reason": "hull-contact",
                    "depth": depth,
                    "at": (entry[1], entry[2], entry[3]),
                    "with": (other[1], other[2], other[3])}
    inexact = [j for j in joints if float(j[0]) != j[0]
               or float(j[1]) != j[1]]
    if inexact:
        return {"ok": False, "reason": "joint-inexact", "depth": depth,
                "count": len(inexact)}
    return {"ok": True, "reason": "substitution-certified", "depth": depth,
            "curves": sum(1 for e in entries if e[0] == "curve"),
            "pieces": sum(1 for e in entries if e[0] == "curve")}


def _curve_joints(ctrls, depth):
    """Shared joint polyline across one curve's dyadic pieces.

    Vertices are sub-piece endpoints only; interior controls never
    enter the polyline.
    """
    chains = piece_chains(ctrls, depth)
    return [chains[0][0]] + [chain[-1] for chain in chains]


def _joint_floats(chain):
    return [(float(p[0]), float(p[1])) for p in chain]


def build_substituted_commands(commands, depth=0):
    """Polyline commands with identical contour labels and endpoints.

    Each curve op becomes line_to joints through the exact dyadic chain;
    original endpoints keep their exact float bits. Raises ValueError
    when the outline is malformed or any joint is not exactly
    float-representable.
    """
    report = certify_substitution(commands, depth)
    if not report["ok"]:
        raise ValueError("uncertified-substitution: %s" % report["reason"])
    contours, _ = _parse_contours(commands)
    curve_iter = iter(_curve_joints([_fr(p) for p in prim[1]], depth)
                      for contour in contours for prim in contour
                      if prim[0] == "curve")
    out = []
    for cmd in commands:
        op = cmd.get("op") if isinstance(cmd, dict) else None
        if op in ("quad_to", "curve_to"):
            for joint in _joint_floats(next(curve_iter))[1:]:
                out.append({"op": "line_to", "x": joint[0], "y": joint[1]})
        else:
            out.append(dict(cmd))
    return out


def _coord_bits(cmd, key):
    """Bit identity of one coordinate: IEEE 754 plus stored bits.

    Numeric == cannot distinguish -0.0 from 0.0, and a changed numeric
    beside stale explicit bits must still mismatch, so identity pairs
    the IEEE little-endian double bits with the stored bits value (or
    None when absent). Non-numeric or non-finite values fail closed.
    """
    bits_key = key + "_bits"
    stored = cmd.get(bits_key) if isinstance(cmd, dict) else None
    if isinstance(stored, bool):
        return None
    if not (stored is None or isinstance(stored, int)):
        return None
    value = cmd.get(key) if isinstance(cmd, dict) else None
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    ieee = struct.unpack("<Q", struct.pack("<d", number))[0]
    return (ieee, stored)


def _control_keys(commands):
    """Bit-exact Bezier control geometry per curve op, or None.

    Each key holds the full control tuple including the implied start
    point resolved from the preceding command, so moving a line/move
    start while leaving the quad dict untouched still mismatches.
    """
    keys, current, contour_start, open_contour = [], None, None, False
    for cmd in commands:
        op = cmd.get("op") if isinstance(cmd, dict) else None
        if op == "move_to":
            if open_contour:
                return None
            bits = (_coord_bits(cmd, "x"), _coord_bits(cmd, "y"))
            if any(b is None for b in bits):
                return None
            current, contour_start, open_contour = bits, bits, True
        elif op in ("line_to", "quad_to", "curve_to"):
            if not open_contour or current is None:
                return None
            if op == "line_to":
                names = ("x", "y")
            elif op == "quad_to":
                names = ("x1", "y1", "x", "y")
            else:
                names = ("x1", "y1", "x2", "y2", "x", "y")
            bits = tuple(_coord_bits(cmd, key) for key in names)
            if any(b is None for b in bits):
                return None
            end = (bits[-2], bits[-1])
            if op in ("quad_to", "curve_to"):
                keys.append((current,) + tuple(
                    (bits[i], bits[i + 1])
                    for i in range(0, len(bits), 2)))
            current = end
        elif op == "close":
            if not open_contour:
                return None
            open_contour = False
            current = contour_start
        else:
            return None
    if open_contour:
        return None
    return keys


def disk_clear(center, radius, ctrls, max_depth=8):
    """Certify a station disk avoids a fixed curve.

    Exact Fraction squared distance from the center to each sub-piece
    bbox lower-bounds the true curve distance (curve lies in its hull,
    hull in its bbox); a strict greater-than-radius-squared bound
    prunes the piece, else exact de Casteljau subdivision recurses.
    At most 2**(max_depth+1)-1 bbox evaluations; unresolved proximity
    at the budget fails closed. Source floats stay exact Fractions.
    """
    try:
        if radius < 0:
            return False, "negative-radius"
        point = _fr(center)
        reach = Fraction(radius) ** 2
        chains = [[_fr(p) for p in ctrls]]
    except (ArithmeticError, OverflowError, ValueError, TypeError,
            ZeroDivisionError):
        return False, "malformed-curve"

    def bbox_d2(chain):
        xs = [p[0] for p in chain]
        ys = [p[1] for p in chain]
        dx = (Fraction(0) if min(xs) <= point[0] <= max(xs)
              else min(abs(point[0] - min(xs)),
                       abs(point[0] - max(xs))))
        dy = (Fraction(0) if min(ys) <= point[1] <= max(ys)
              else min(abs(point[1] - min(ys)),
                       abs(point[1] - max(ys))))
        return dx * dx + dy * dy

    def visit(chain, depth):
        if bbox_d2(chain) > reach:
            return True
        if depth >= max_depth:
            return False
        left, right = subdivide(chain)
        return visit(left, depth + 1) and visit(right, depth + 1)

    if visit(chains[0], 0):
        return True, "clear"
    return False, "disk-too-close"


def compare_commands(source_commands, upstream_commands,
                     candidate_commands, depth=0, binary=None):
    """Topology comparison through certified polyline substitution.

    The straight checker is used unmodified on substituted polylines.
    Candidate Bezier control geometry must be bit-identical to upstream,
    including implied start points and signed-zero bits. All three
    geometries certify independently; straight-only outlines delegate
    directly. No result caching: every call re-verifies its inputs.
    The comparison rests on equal finite topological invariants per
    geometry, not on a continuous straight-edge homotopy guarantee --
    the same limitation as the all-straight checker. movement_clear is
    a separate offline sweep helper, not part of this comparison.
    """
    for name, cmds in (("source", source_commands),
                       ("upstream", upstream_commands),
                       ("candidate", candidate_commands)):
        if not isinstance(cmds, list) or not cmds:
            return {"supported": False, "ok": False,
                    "reason": "malformed-%s" % name}
    ops = [[c.get("op") if isinstance(c, dict) else None
            for c in cmds] for cmds in (source_commands, upstream_commands,
                                        candidate_commands)]
    if not (ops[0] == ops[1] == ops[2]):
        return {"supported": False, "ok": False,
                "reason": "command-shape-mismatch"}
    upstream_keys = _control_keys(upstream_commands)
    candidate_keys = _control_keys(candidate_commands)
    if upstream_keys is None or candidate_keys is None:
        return {"supported": False, "ok": False,
                "reason": "malformed-commands"}
    if candidate_keys != upstream_keys:
        return {"supported": False, "ok": False,
                "reason": "curves-moved"}
    from experiments.hobby_fitting import exact_topology as checker
    if not any(op in ("quad_to", "curve_to") for op in ops[0]):
        certs = [{"ok": True, "reason": "no-curves", "depth": depth}] * 3
        polys = [source_commands, upstream_commands, candidate_commands]
    else:
        try:
            certs = [certify_substitution(cmds, depth)
                     for cmds in (source_commands, upstream_commands,
                                  candidate_commands)]
        except (ArithmeticError, OverflowError, ValueError):
            return {"supported": False, "ok": False,
                    "reason": "uncertified-substitution", "certs": []}
        if not all(c["ok"] for c in certs):
            return {"supported": False, "ok": False,
                    "reason": "uncertified-substitution",
                    "certs": certs}
        try:
            polys = [build_substituted_commands(cmds, depth)
                     for cmds in (source_commands, upstream_commands,
                                  candidate_commands)]
        except ValueError as exc:
            return {"supported": False, "ok": False,
                    "reason": str(exc), "certs": certs}
    verdict = checker.compare_commands(polys[0], polys[1], polys[2],
                                       binary=binary)
    verdict["certs"] = certs
    return verdict
