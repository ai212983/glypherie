"""Independent bounded cardinal native dependency reference.

Predicts native TrueType execution for complete resolved graphs with
positive cardinal X/Y normals, integer font-unit sources, UPM 1000 and one
isotropic ppem. Graphics state matches compile_native preamble
(SZPS[1], SLOOP[1], RTG, SCVTCI[32767], SSWCI[0], SSW[0], SMD[0],
FLIPOFF). All arithmetic is integer, mirroring FreeType 2.13.2 ttinterp.c:

- scale16.16 = FT_DivFix(ppem*64, 1000); initial26.6 = FT_MulFix(FU, scale)
- MDAP rounds the current point; MIAP uses scaled CVT with >32767 cut-in
- MDRP scales the unscaled source difference ONCE via FT_MulFix
- MIRP cut-in compares scaled CVT against the original scaled difference
- IP interpolates with FT_MulDiv over the unscaled source interval and the
  current 26.6 parent interval
- pixel rounding is half away from zero to the 64 grid (RTG, no engine
  compensation in the tested FreeType mono configuration)

Contract: Microsoft TrueType instructions
(https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions);
VTT ordinary IP/Link consumes current native parents; Shamir 2003 3.6
dependency order. This module never imports the native compiler or the
float solver. Only Abs/PAbs/Dist/PDist/Ratio with compiler-supported
semantics; PRatio and anything else is rejected explicitly.
"""

UPM = 1000
CUTIN = 32767
GRID = 64
HALF_GRID = 32
MAX_POINTS = 16
MIN_PPEM = 1
MAX_PPEM = 1000
FU_MIN = -32768
FU_MAX = 32767
COORD_BOUND = 1 << 30
RATIO_TOL = 32 * 2.0**-52  # Matches the compiler source-value validation bound.


class ReferenceError(ValueError):
    """Raised when the graph is outside the bounded reference domain."""


def mulfix(a, b):
    """FT_MulFix: (a*b)/65536 rounded to nearest, ties away from zero."""
    if not isinstance(a, int) or not isinstance(b, int):
        raise ReferenceError("mulfix needs exact integers")
    sign = -1 if (a < 0) ^ (b < 0) else 1
    q = (abs(a) * abs(b) + 0x8000) >> 16
    return -q if sign < 0 else q


def divfix(a, b):
    """FT_DivFix: (a<<16)/b rounded to nearest, ties away from zero."""
    if not isinstance(a, int) or not isinstance(b, int):
        raise ReferenceError("divfix needs exact integers")
    if b == 0:
        raise ReferenceError("divfix division by zero")
    sign = -1 if (a < 0) ^ (b < 0) else 1
    q = ((abs(a) << 16) + (abs(b) >> 1)) // abs(b)
    return -q if sign < 0 else q


def muldiv(a, b, c):
    """FT_MulDiv: (a*b)/c rounded to nearest, ties away from zero."""
    if not isinstance(a, int) or not isinstance(b, int) or not isinstance(c, int):
        raise ReferenceError("muldiv needs exact integers")
    if c == 0:
        raise ReferenceError("muldiv division by zero")
    sign = -1 if ((a < 0) ^ (b < 0) ^ (c < 0)) else 1
    q = (abs(a) * abs(b) + (abs(c) >> 1)) // abs(c)
    return -q if sign < 0 else q


def round_to_grid(v):
    """RTG pixel rounding: half away from zero to multiples of 64."""
    if not isinstance(v, int):
        raise ReferenceError("round_to_grid needs an exact integer")
    if v >= 0:
        return ((v + HALF_GRID) >> 6) << 6
    return -(((abs(v) + HALF_GRID) >> 6) << 6)


def initial_scale(ppem):
    """16.16 interpretation scale, as FreeType derives it."""
    if isinstance(ppem, bool) or not isinstance(ppem, int):
        raise ReferenceError("ppem %r is not an exact integer" % (ppem,))
    if not MIN_PPEM <= ppem <= MAX_PPEM:
        raise ReferenceError("ppem %d out of range [%d, %d]" % (ppem, MIN_PPEM, MAX_PPEM))
    return divfix(ppem * 64, UPM)


def scale_fu(fu, scale):
    """Scale one integer font unit to raw 26.6."""
    v = mulfix(fu, scale)
    if abs(v) > COORD_BOUND:
        raise ReferenceError("scaled coordinate %d exceeds bound" % v)
    return v


def _is_exact_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _check_finite_number(v, what):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ReferenceError("%s %r is not numeric" % (what, v))
    f = float(v)
    if f != f or f in (float("inf"), float("-inf")):
        raise ReferenceError("%s %r is non-finite" % (what, v))
    return f


def _axis_of(normal, cid):
    if not isinstance(normal, (list, tuple)) or len(normal) != 2:
        raise ReferenceError("constraint %d normal is malformed" % cid)
    nx = _check_finite_number(normal[0], "normal x")
    ny = _check_finite_number(normal[1], "normal y")
    if nx == 1.0 and ny == 0.0:
        return 0
    if nx == 0.0 and ny == 1.0:
        return 1
    raise ReferenceError("constraint %d normal %r is noncardinal" % (cid, list(normal)))


def _as_fu(value, what):
    f = _check_finite_number(value, what)
    if isinstance(value, int) and not isinstance(value, bool):
        iv = value
    elif f.is_integer():
        iv = int(f)
    else:
        raise ReferenceError("%s %r is not an integer font unit" % (what, value))
    if not FU_MIN <= iv <= FU_MAX:
        raise ReferenceError("%s %d out of signed-16 range" % (what, iv))
    return iv


def validate(graph, points, ppem):
    """Validate the bounded domain; return normalized (fu, order, grouped)."""
    scale = initial_scale(ppem)
    if not isinstance(points, (list, tuple)):
        raise ReferenceError("points must be a sequence")
    if len(points) > MAX_POINTS:
        raise ReferenceError("too many points (cap %d)" % MAX_POINTS)
    fu = []
    for i, p in enumerate(points):
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise ReferenceError("point %d is malformed" % i)
        fu.append([_as_fu(p[0], "point %d x" % i), _as_fu(p[1], "point %d y" % i)])
    n = len(fu)
    if not isinstance(graph, dict):
        raise ReferenceError("graph must be a dict")
    constraints = graph.get("constraints")
    order = graph.get("order")
    if not isinstance(constraints, (list, tuple)) or not isinstance(order, (list, tuple)):
        raise ReferenceError("graph constraints/order must be sequences")
    if len(order) != n or any(not _is_exact_int(p) for p in order):
        raise ReferenceError("order is not an exact complete permutation")
    order = [int(p) for p in order]
    if sorted(order) != list(range(n)):
        raise ReferenceError("order is not an exact complete permutation")
    seen_ids = set()
    grouped = {}
    for c in constraints:
        if not isinstance(c, dict):
            raise ReferenceError("constraint %r is malformed" % (c,))
        cid = c.get("id")
        if not _is_exact_int(cid):
            raise ReferenceError("constraint IDs must be exact integers")
        cid = int(cid)
        if cid in seen_ids:
            raise ReferenceError("duplicate constraint ID %d" % cid)
        seen_ids.add(cid)
        p = c.get("point")
        if not _is_exact_int(p) or not 0 <= int(p) < n:
            raise ReferenceError("constraint %d point out of range" % cid)
        p = int(p)
        kind = c.get("kind")
        if kind == "PRatio":
            raise ReferenceError("constraint %d PRatio unsupported" % cid)
        if kind not in ("Abs", "PAbs", "Dist", "PDist", "Ratio"):
            raise ReferenceError("constraint %d unknown kind %r" % (cid, kind))
        axis = _axis_of(c.get("normal"), cid)
        arity = {"Abs": 0, "PAbs": 0, "Dist": 1, "PDist": 1, "Ratio": 2}[kind]
        src = c.get("sources", [])
        if not isinstance(src, (list, tuple)) or len(src) != arity:
            raise ReferenceError("constraint %d wrong arity for %s" % (cid, kind))
        sources = []
        for s in src:
            if not _is_exact_int(s) or not 0 <= int(s) < n:
                raise ReferenceError("constraint %d source %r out of range" % (cid, s))
            sources.append(int(s))
        if "round" in c and not isinstance(c["round"], bool):
            raise ReferenceError("constraint %d round flag malformed" % cid)
        if kind == "Ratio":
            if c.get("round", None) is not False:
                raise ReferenceError("constraint %d rounded Ratio unsupported" % cid)
        rnd = bool(c.get("round", True)) if kind != "Ratio" else False
        value = _check_finite_number(c.get("value"), "constraint %d value" % cid)
        if kind in ("PAbs", "PDist"):
            ivalue = _as_fu(c.get("value"), "constraint %d CVT value" % cid)
        else:
            ivalue = None
        if kind == "Abs":
            expected = float(fu[p][axis])
            if abs(value - expected) > RATIO_TOL * max(1.0, abs(expected), abs(value)):
                raise ReferenceError("constraint %d Abs not source-derived" % cid)
        elif kind == "Dist":
            expected = float(fu[p][axis] - fu[sources[0]][axis])
            if abs(value - expected) > RATIO_TOL * max(1.0, abs(expected), abs(value)):
                raise ReferenceError("constraint %d Dist not source-derived" % cid)
        elif kind == "Ratio":
            a, b = sources
            pa, pb, pp = float(fu[a][axis]), float(fu[b][axis]), float(fu[p][axis])
            span = pb - pa
            if a == b or span == 0.0:
                raise ReferenceError("constraint %d Ratio needs distinct span" % cid)
            t = (pp - pa) / span
            if abs(value - t) > RATIO_TOL * max(1.0, abs(t), abs(value)):
                raise ReferenceError("constraint %d Ratio not source-derived" % cid)
        grouped.setdefault(p, []).append({
            "id": cid, "kind": kind, "axis": axis, "sources": sources,
            "round": rnd, "value": value, "ivalue": ivalue,
        })
    if sorted(grouped) != list(range(n)) or any(len(g) != 2 for g in grouped.values()):
        raise ReferenceError("each point needs exactly two constraints")
    for p in range(n):
        axes = sorted(g["axis"] for g in grouped[p])
        if axes != [0, 1]:
            raise ReferenceError("point %d needs exactly one X and one Y constraint" % p)
    completed = set()
    for p in order:
        for g in grouped[p]:
            for s in g["sources"]:
                if s not in completed:
                    raise ReferenceError(
                        "source %d not completed before point %d" % (s, p))
        completed.add(p)
    return fu, order, grouped, scale


def run(graph, points, ppem):
    """Execute the independent reference; return initial/steps/final.

    Steps follow the graph constraint list order (grouped schedule order).
    Each step records before/after whole-point state plus the parent
    current/original states consumed. Coordinates are raw 26.6 integers.
    """
    fu, order, grouped, scale = validate(graph, points, ppem)
    n = len(fu)
    org = [[scale_fu(fu[p][0], scale), scale_fu(fu[p][1], scale)] for p in range(n)]
    cur = [list(o) for o in org]
    initial = [list(o) for o in org]
    steps = []
    for p in order:
        for g in grouped[p]:
            before = [list(c) for c in cur]
            src = g["sources"]
            if g["kind"] in ("Dist", "PDist"):
                s = src[0]
                parent_cur = list(cur[s])
                parent_org = list(org[s])
            elif g["kind"] == "Ratio":
                parent_cur = [list(cur[s]) for s in src]
                parent_org = [list(org[s]) for s in src]
            else:
                parent_cur = list(cur[p])
                parent_org = list(org[p])
            apply(g, p, fu, org, cur, scale)
            after = [list(c) for c in cur]
            steps.append({
                "index": len(steps),
                "point": p,
                "constraint_id": g["id"],
                "kind": g["kind"],
                "axis": g["axis"],
                "round": g["round"],
                "sources": list(src),
                "value": g["value"],
                "point_cur_before": list(before[p]),
                "point_org": list(org[p]),
                "parent_cur": parent_cur,
                "parent_org": parent_org,
                "before": before,
                "after": after,
            })
    return {"initial": initial, "steps": steps, "final": [list(c) for c in cur],
            "scale": scale, "ppem": ppem}


def apply(g, p, fu, org, cur, scale):
    """Apply one validated constraint to cur (cardinal axis only)."""
    kind, ax = g["kind"], g["axis"]
    if kind == "Abs":
        if g["round"]:
            cur[p][ax] = round_to_grid(cur[p][ax])
    elif kind == "PAbs":
        cvt = scale_fu(g["ivalue"], scale)
        if g["round"]:
            if abs(cvt - cur[p][ax]) > CUTIN:
                cvt = cur[p][ax]
            cvt = round_to_grid(cvt)
        cur[p][ax] = cvt
    elif kind == "Dist":
        s = g["sources"][0]
        if g["value"] == 0.0 and fu[p][ax] == fu[s][ax]:
            cur[p][ax] = cur[s][ax]  # ALIGNRP: current parent projection
        else:
            org_dist = scale_fu(fu[p][ax] - fu[s][ax], scale)
            distance = round_to_grid(org_dist) if g["round"] else org_dist
            cur[p][ax] = cur[s][ax] + distance
    elif kind == "PDist":
        s = g["sources"][0]
        cvt = scale_fu(g["ivalue"], scale)
        org_dist = org[p][ax] - org[s][ax]
        if g["round"]:
            if abs(cvt - org_dist) > CUTIN:
                cvt = org_dist
            cvt = round_to_grid(cvt)
        cur[p][ax] = cur[p][ax] + (cvt - (cur[p][ax] - cur[s][ax]))
    elif kind == "Ratio":
        a, b = g["sources"]
        old_range = fu[b][ax] - fu[a][ax]
        org_dist = fu[p][ax] - fu[a][ax]
        cur_range = cur[b][ax] - cur[a][ax]
        cur_dist = cur[p][ax] - cur[a][ax]
        if org_dist == 0:
            new_dist = 0
        elif old_range == 0:
            new_dist = org_dist
        else:
            new_dist = muldiv(org_dist, cur_range, old_range)
        cur[p][ax] = cur[p][ax] + (new_dist - cur_dist)
    else:  # pragma: no cover - validate() rejects these
        raise ReferenceError("unsupported kind %r" % (kind,))
    if abs(cur[p][ax]) > COORD_BOUND:
        raise ReferenceError("point %d coordinate exceeds bound" % p)
