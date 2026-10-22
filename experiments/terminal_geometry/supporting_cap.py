"""Straight supporting-cap certification for terminal dropout spans.

Source: TrueType SCANTYPE Rules 5/6 (cap closure needs both borders to
continue past the dropout scan line); pinned FreeType ftraster.c profile-pair
stub test (same-contour successor/top-bottom checks); Hersch 1993 section 7
(subpixel interior null-span rescue); 26.6 quantization
(floor(x*64+0.5)) per tools/generator/src/mono.rs.
Project hypothesis (owning design docs/revisions/001/03-spacing-kerning.md):
a straight cap edge that is a supporting line of the WHOLE filled outline,
with both adjacent stroke borders continuing into the filled half-plane and
unambiguous span ownership, is a genuine terminal; curves, interior
junctions and uncertain overlap abstain (keep rescue).
Invariant: edge-level permit is an over-approximation; actual removal needs
the fixed-grid FreeType stubs on/off pixel difference AND attribution here.
Invariant: a certified cap is ELIGIBLE in both the source (unhinted) shape
and the scanner-quantized 26.6 fitted shape at the same contour/edge index
with the same filled side; pixel attribution uses fitted coordinates.
Invariant: input coordinates must satisfy |v| <= 32768 and be finite
(matching tools/generator/src/mono.rs bounds); quantized 26.6 values fit in
+-2097152 and all cross/dot products below 2**45, exact in Python ints and
i64-safe for the Rust port. Malformed input raises ValueError.
Invariant: curve ownership uses the convex hull of control points (the hull
contains the curve); any closed contact between hull and cap/square,
including a single-point touch, abstains. Control-polygon legs alone can
miss curve interior inside the hull.
Limitation: long hull-border caps can certify; attribution still requires
the FreeType diff pixel plus a square meeting only cap/incident edges, and
the owning document records this residual long-border span risk.
"""

from fractions import Fraction
from math import floor, isfinite


BOUND = 32768.0
QBOUND = 2097152


def q26(v):
    # Source: tools/generator/src/mono.rs floor(x*64+0.5) 26.6 conversion.
    return floor(float(v) * 64.0 + 0.5)


def sign(v):
    if v > 0:
        return 1
    if v < 0:
        return -1
    return 0


def cross(ax, ay, bx, by):
    return ax * by - ay * bx


def orient(p, q, r):
    return sign(cross(q[0] - p[0], q[1] - p[1], r[0] - p[0], r[1] - p[1]))


def on_closed_segment(p, a, b):
    if orient(a, b, p) != 0:
        return False
    return (min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= p[1] <= max(a[1], b[1]))


def segments_touch(a, b, c, d):
    # Source: exact orientation-predicate segment intersection.
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    return (o1 == 0 and on_closed_segment(c, a, b)
            or o2 == 0 and on_closed_segment(d, a, b)
            or o3 == 0 and on_closed_segment(a, c, d)
            or o4 == 0 and on_closed_segment(b, c, d))


def convex_hull(points):
    # Source: Andrew monotone chain over control points.
    pts = sorted(set(points))
    if len(pts) <= 1:
        return pts

    def turn(o, a, b):
        return cross(a[0] - o[0], a[1] - o[1], b[0] - o[0], b[1] - o[1])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def point_in_convex_strict(p, hull):
    if len(hull) < 3:
        return False
    s = 0
    n = len(hull)
    for i in range(n):
        o = orient(hull[i], hull[(i + 1) % n], p)
        if o == 0:
            return False
        if s == 0:
            s = o
        elif s != o:
            return False
    return True


def hull_meets_segment(hull, a, b):
    # Invariant: closed contact, including a point touch, counts.
    if not hull:
        return False
    xs = [p[0] for p in hull] + [a[0], b[0]]
    ys = [p[1] for p in hull] + [a[1], b[1]]
    if max(xs[:len(hull)]) < min(a[0], b[0]) or min(xs[:len(hull)]) > max(a[0], b[0]):
        return False
    if max(ys[:len(hull)]) < min(a[1], b[1]) or min(ys[:len(hull)]) > max(a[1], b[1]):
        return False
    n = len(hull)
    if n == 1:
        return on_closed_segment(hull[0], a, b)
    if n == 2:
        return segments_touch(hull[0], hull[1], a, b)
    for i in range(n):
        if segments_touch(hull[i], hull[(i + 1) % n], a, b):
            return True
    return point_in_convex_strict(a, hull) or point_in_convex_strict(b, hull)


def hull_meets_square(hull, square):
    # Invariant: closed contact, including a point touch, counts.
    if not hull:
        return False
    (x0, y0), (x1, y1) = square
    for v in hull:
        if x0 <= v[0] <= x1 and y0 <= v[1] <= y1:
            return True
    corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    for c in corners:
        if len(hull) >= 3 and point_in_convex_strict(c, hull):
            return True
    n = len(hull)
    edges = [(hull[i], hull[(i + 1) % n]) for i in range(n)] if n > 2 else \
        [(hull[0], hull[1])] if n == 2 else []
    sq_edges = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
    for h0, h1 in edges:
        for s0, s1 in sq_edges:
            if segments_touch(h0, h1, s0, s1):
                return True
    return False


def validate_commands(commands):
    # Invariant: rejects malformed, non-finite and out-of-range input.
    if not isinstance(commands, list):
        raise ValueError("commands must be a list")
    open_contour = False
    for c in commands:
        if not isinstance(c, dict) or "op" not in c:
            raise ValueError("command must be a dict with op")
        op = c["op"]
        if op == "move_to":
            if open_contour:
                raise ValueError("move_to with open contour")
            need = ("x", "y")
            open_contour = True
        elif op == "line_to":
            need = ("x", "y")
        elif op == "quad_to":
            need = ("x", "y", "x1", "y1")
        elif op == "curve_to":
            need = ("x", "y", "x1", "y1", "x2", "y2")
        elif op == "close":
            if not open_contour:
                raise ValueError("close with no open contour")
            open_contour = False
            continue
        else:
            raise ValueError("unknown op %r" % (op,))
        if not open_contour and op != "move_to":
            raise ValueError("%s with no open contour" % op)
        for k in need:
            v = c.get(k)
            if not isinstance(v, (int, float)) or not isfinite(v):
                raise ValueError("non-finite coordinate %r" % (k,))
            if abs(v) > BOUND:
                raise ValueError("coordinate out of range")
    if open_contour:
        raise ValueError("unclosed contour")


def parse(commands):
    # Source: TrueType glyph outline model (move/line/quad/cubic/close).
    validate_commands(commands)
    contours, cur, struct = [], None, []
    cops = None
    for c in commands:
        op = c["op"]
        if op == "move_to":
            cur = {"points": [(c["x"], c["y"])], "curves": [], "edges": []}
            contours.append(cur)
            cops = ["move_to"]
            struct.append(cops)
        elif op == "line_to":
            p = (c["x"], c["y"])
            cur["edges"].append((cur["points"][-1], p))
            cur["points"].append(p)
            cops.append("line_to")
        elif op == "quad_to":
            p0, p1, p2 = cur["points"][-1], (c["x1"], c["y1"]), (c["x"], c["y"])
            cur["curves"].append((p0, p1, p2))
            cur["points"].append(p2)
            cops.append("quad_to")
        elif op == "curve_to":
            p0 = cur["points"][-1]
            ps = ((c["x1"], c["y1"]), (c["x2"], c["y2"]), (c["x"], c["y"]))
            cur["curves"].append((p0,) + ps)
            cur["points"].append(ps[2])
            cops.append("curve_to")
        elif op == "close":
            if len(cur["points"]) > 1:
                cur["edges"].append((cur["points"][-1], cur["points"][0]))
                cur["points"].append(cur["points"][0])
            cops.append("close")
            cur = None
    return contours, [tuple(s) for s in struct]


def quantize_contours(contours):
    out = []
    for contour in contours:
        qc = {
            "points": [(q26(x), q26(y)) for x, y in contour["points"]],
            "curves": [tuple((q26(x), q26(y)) for x, y in curve)
                       for curve in contour["curves"]],
            "edges": [((q26(ax), q26(ay)), (q26(bx), q26(by)))
                      for (ax, ay), (bx, by) in contour["edges"]],
        }
        for x, y in qc["points"]:
            if abs(x) > QBOUND or abs(y) > QBOUND:
                raise ValueError("quantized coordinate out of range")
        out.append(qc)
    return out


def _half_plane_ok(contours, a, b, side):
    ex, ey = b[0] - a[0], b[1] - a[1]
    for contour in contours:
        for p in contour["points"]:
            if sign(cross(ex, ey, p[0] - a[0], p[1] - a[1])) == -side:
                return False
        for curve in contour["curves"]:
            for p in curve[1:]:
                # Invariant: Bezier convex-hull property keeps this sufficient.
                if sign(cross(ex, ey, p[0] - a[0], p[1] - a[1])) == -side:
                    return False
    return True


def _curve_hulls(contour):
    return [convex_hull(list(curve)) for curve in contour["curves"]]


def _touches_other(contours, hulls, ci, edge_idx, a, b):
    n = len(contours[ci]["edges"])
    for cj, contour in enumerate(contours):
        for ej, (c, d) in enumerate(contour["edges"]):
            if cj == ci and ej in (edge_idx,
                                   (edge_idx - 1) % n, (edge_idx + 1) % n):
                continue
            if segments_touch(a, b, c, d):
                return True
        for hull in hulls[cj]:
            # Invariant: hull contact (incl. point touch) counts as contact.
            if hull_meets_segment(hull, a, b):
                return True
    return False


def classify_edge(contours, hulls, ci, edge_idx):
    """Classify one straight edge; returns (verdict, gates).

    Source: SCANTYPE Rule 6 (both borders continue); FreeType stub profile
    test (same-contour cap); Hersch 1993 section 7 (null-span rescue site).
    The filled side is recorded in gates and never inferred from a pixel.
    """
    edges = contours[ci]["edges"]
    n = len(edges)
    a, b = edges[edge_idx]
    gates = {"filled_side": 0}
    if a == b:
        return "ABSTAIN", dict(gates, nonzero=False)
    gates["nonzero"] = True
    # Project hypothesis: curves anywhere in the cap contour abstain.
    gates["straight_contour"] = not contours[ci]["curves"]
    if not gates["straight_contour"]:
        return "ABSTAIN", gates
    ex, ey = b[0] - a[0], b[1] - a[1]
    prev_far = edges[(edge_idx - 1) % n][0]
    next_far = edges[(edge_idx + 1) % n][1]
    s1 = sign(cross(ex, ey, prev_far[0] - a[0], prev_far[1] - a[1]))
    s2 = sign(cross(ex, ey, next_far[0] - b[0], next_far[1] - b[1]))
    gates["continuation"] = s1 == s2 and s1 != 0
    if not gates["continuation"]:
        return "ABSTAIN", gates
    gates["filled_side"] = s1
    gates["supporting"] = _half_plane_ok(contours, a, b, s1)
    if not gates["supporting"]:
        return "ABSTAIN", gates
    gates["ownership"] = not _touches_other(contours, hulls, ci, edge_idx, a, b)
    if not gates["ownership"]:
        return "ABSTAIN", gates
    return "ELIGIBLE", gates


def certified_caps(source_commands, fitted_commands):
    """Dual certification: ELIGIBLE in source shape and quantized fitted shape.

    Source: source (unhinted) outline; fitted (current) outline scanned at
    26.6 per tools/generator/src/mono.rs. Requires identical op/contour/edge
    identity; any mismatch yields no caps. Returns (quantized, caps, info).
    """
    s_contours, s_struct = parse(source_commands)
    f_contours, f_struct = parse(fitted_commands)
    if s_struct != f_struct:
        return None, [], {"structure_match": False}
    f_quantized = quantize_contours(f_contours)
    s_hulls = [_curve_hulls(c) for c in s_contours]
    f_hulls = [_curve_hulls(c) for c in f_quantized]
    out = []
    for ci, contour in enumerate(s_contours):
        for ei in range(len(contour["edges"])):
            verdict_s, gates_s = classify_edge(s_contours, s_hulls, ci, ei)
            if verdict_s != "ELIGIBLE":
                continue
            verdict_f, gates_f = classify_edge(f_quantized, f_hulls, ci, ei)
            if verdict_f != "ELIGIBLE":
                continue
            # Invariant: filled side must agree across source and fitted runs.
            if gates_s["filled_side"] != gates_f["filled_side"]:
                continue
            a, b = f_quantized[ci]["edges"][ei]
            out.append({"contour": ci, "edge": ei, "a": list(a), "b": list(b),
                        "filled_side": gates_f["filled_side"]})
    return f_quantized, out, {"structure_match": True}


def eligible_caps(commands):
    """Single-shape eligibility (synthetic tests only, not replay)."""
    contours, _ = parse(commands)
    quantized = quantize_contours(contours)
    hulls = [_curve_hulls(c) for c in quantized]
    out = []
    for ci, contour in enumerate(quantized):
        for ei in range(len(contour["edges"])):
            verdict, gates = classify_edge(quantized, hulls, ci, ei)
            if verdict == "ELIGIBLE":
                a, b = contour["edges"][ei]
                out.append({"contour": ci, "edge": ei, "a": list(a),
                            "b": list(b), "filled_side": gates["filled_side"]})
    return quantized, out


def clip_positive_length(a, b, square):
    """Strict finite-segment/square intersection: positive clipped length.

    Source: Liang-Barsky clipping against the closed unit pixel square;
    exact Fraction arithmetic in 26.6 integer space. A single-point graze
    yields no association.
    """
    (x0, y0), (x1, y1) = square
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    if dx == 0 and dy == 0:
        return x0 < a[0] < x1 and y0 < a[1] < y1
    t0, t1 = Fraction(0), Fraction(1)
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]),
                 (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0:
                return False
        else:
            t = Fraction(q, p)
            if p < 0:
                if t > t0:
                    t0 = t
            else:
                if t < t1:
                    t1 = t
            if t0 > t1:
                return False
    return t0 < t1


def segment_meets_square_closed(a, b, square):
    """Closed segment/square contact, including a single-point touch."""
    if clip_positive_length(a, b, square):
        return True
    (x0, y0), (x1, y1) = square
    for p in (a, b):
        if x0 <= p[0] <= x1 and y0 <= p[1] <= y1:
            return True
    for c in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        if on_closed_segment(c, a, b):
            return True
    return False


def pixel_square(left, top, i, j):
    """Unit pixel square in 26.6 y-up space.

    Source: bitmap row j covers y-down [top+j, top+j+1); y-up negates to
    [-(top+j)-1, -(top+j)].
    """
    x0 = q26(left + i)
    x1 = q26(left + i + 1)
    yhi = -q26(top + j)
    ylo = yhi - 64
    return (x0, ylo), (x1, yhi)


def attribute_pixel(square, caps, quantized):
    """Attribute a changed pixel square to exactly one certified cap.

    Source: geometric span ownership (cap contour only, incident wedge
    allowed); abstains on multiple, other-contour, same-contour-nonincident
    or curve-hull contact, where zero-touch ambiguity also abstains.
    Returns (cap, reason).
    """
    hits = [c for c in caps
            if clip_positive_length(tuple(c["a"]), tuple(c["b"]), square)]
    if len(hits) != 1:
        return None, ("none" if not hits else "multiple")
    cap = hits[0]
    n = len(quantized[cap["contour"]]["edges"])
    allowed = {cap["edge"], (cap["edge"] - 1) % n, (cap["edge"] + 1) % n}
    for ci, contour in enumerate(quantized):
        for ei, (c, d) in enumerate(contour["edges"]):
            if ci == cap["contour"] and ei in allowed:
                continue
            # Invariant: any closed contact, incl. point touch, abstains.
            if segment_meets_square_closed(c, d, square):
                return None, "other-contour" if ci != cap["contour"] \
                    else "same-contour-nonincident"
        for curve in contour["curves"]:
            # Invariant: hull contact (incl. point touch) counts as contact.
            if hull_meets_square(convex_hull(list(curve)), square):
                return None, "curve"
    return cap, "certified"
