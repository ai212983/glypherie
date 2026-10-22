"""Whole-outline reflection placement on the pixel grid.

Research prototype, not a renderer path. Two named arms share strict
input validation and exact rigid-placement machinery:

strict-quantum (control)
    Hobby sec 3.5 recognition: vertical map M(x, y) = (2c - x, y),
    Hobby (14), almost matches when every reflected vertex lies within
    epsilon of a source segment. Epsilon is one 26.6 quantum (1/64 px),
    retained as the legacy control rule. No claim is made that
    sub-quantum deviation is unrepresentable intent: normal distances
    through diagonal borders register sub-quantum effects, so this
    epsilon is a control parameter, not an intent boundary.

phase-range (experimental)
    Hersch sec 5 supplies allowed grid phase: a symmetry center sits on
    a pixel center or half-way between two pixels (Fig. 17); horizontal
    centering lies between the extremal points (Fig. 18). For each open
    slab between consecutive vertex-critical coordinates, the spanning
    borders are affine in the sweep coordinate; sorted crossings are
    evaluated at both slab-end limits and paired outer-to-inner, the
    middle crossing standing alone for odd counts. Exactly symmetric
    input gives every pair midpoint equal to the axis, so the min/max
    over all slab ends is the source approximate-axis interval
    [cmin, cmax]. Eligibility needs the rigidly shifted source interval
    inside one half-pixel phase cell [t - 1/4, t + 1/4]; the shift amount
    centers the delivered (upstream) interval midpoint on the same
    target t, so the placed outline not the source estimate lands the
    phase. The shift is 26.6-representable and within the quarter-pixel
    movement bound (nearest half-pixel choice keeps |dx| <= 1/4 by
    construction; quantization cannot exceed it). All asymmetry is
    preserved rigidly; width targets never change; no raster decides
    eligibility.

    Adaptation hypothesis (project, not sourced): sorted outer-to-inner
    pairing stands in for Hobby's sweep correspondence. Counterexamples:
    a slab cutting two unrelated components pairs across components and
    widens the interval toward abstention (fail-safe); affine crossing
    evaluations run in binary64, so containment is a computed check, not
    an exact-arithmetic proof.

The adjusted map M-bar with free axis F_k, Hobby (15), motivates rigid
whole-outline shifts; no (16)-style deformation is used. Scope: straight
non-overlapping closed polygonal outlines where every segment contact is
a shared contour joint (other contact abstains as ambiguous-overlap);
vertical/horizontal whole-outline reflection; rigid translation only on
native-free axes. The slab pairing is not a nonzero-fill
canonicalization: overlapping contours are unsupported, never certified.
Curves abstain. Closed reason set:
applied, applied-phase-range, already-centered, no-near-reflection,
phase-cell-uncontained, upstream-broke-symmetry, upstream-phase-diverged,
native-owned, no-correspondence, malformed-commands, malformed-native-axes,
malformed-arm, empty-outline, curves-unsupported, no-paired-spans,
movement-exceeds-bound, width-check-failed, unrepresentable-shift,
ambiguous-overlap, abstained.
"""

import math
import struct

from experiments.hobby_fitting.real_outline import (
    check_correspondence,
    parse_commands,
)

EPS_REC = 1.0 / 64.0
HALF_GRID = 0.5
CELL_RADIUS = 0.25
MOVE_BOUND = 0.25
_REFINE_HALF_RANGE = 2.0 / 64.0
_REFINE_STEP = EPS_REC / 8.0
_EXTENT_TOL = 1e-12
_GRID_MAX = 16777216.0

ARM_CONTROL = "strict-quantum"
ARM_PHASE = "phase-range"
_ALLOWED_ARMS = (ARM_CONTROL, ARM_PHASE)
_ALLOWED_OPS = ("move_to", "line_to", "quad_to", "curve_to", "close")
_REASONS = ("applied", "applied-phase-range", "already-centered",
            "no-near-reflection", "phase-cell-uncontained",
            "upstream-broke-symmetry", "upstream-phase-diverged",
            "native-owned", "no-correspondence", "malformed-commands",
            "malformed-native-axes", "malformed-arm", "empty-outline",
            "curves-unsupported", "no-paired-spans", "movement-exceeds-bound",
            "width-check-failed", "unrepresentable-shift",
            "ambiguous-overlap", "abstained")


def _f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _f32_bits(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


def _on_grid(value):
    q = value * 64.0
    return q == math.floor(q) and abs(q) <= _GRID_MAX


def _nearest_half(value):
    return math.floor(value * 2.0 + 0.5) / 2.0


def _quantize_64(value):
    return math.floor(value * 64.0 + 0.5) / 64.0


def _is_num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(value)


def _validate_commands(commands):
    """Strict closed grammar: known ops, finite coords, closed contours."""
    if not isinstance(commands, list):
        return "malformed-commands"
    if not commands:
        return "empty-outline"
    expect_move = True
    drew = False
    for cmd in commands:
        if not isinstance(cmd, dict):
            return "malformed-commands"
        op = cmd.get("op")
        if op not in _ALLOWED_OPS:
            return "malformed-commands"
        if op == "move_to":
            if not expect_move:
                return "malformed-commands"
            if not _is_num(cmd.get("x")) or not _is_num(cmd.get("y")):
                return "malformed-commands"
            expect_move = False
            drew = False
        elif op == "close":
            if expect_move or not drew:
                return "malformed-commands"
            for key in ("x", "y", "x1", "y1", "x2", "y2"):
                if key in cmd:
                    return "malformed-commands"
            expect_move = True
        else:
            if expect_move:
                return "malformed-commands"
            if op == "line_to":
                keys = ("x", "y")
            elif op == "quad_to":
                keys = ("x1", "y1", "x", "y")
            else:
                keys = ("x1", "y1", "x2", "y2", "x", "y")
            if any(not _is_num(cmd.get(k)) for k in keys):
                return "malformed-commands"
            drew = True
    if expect_move is False:
        return "malformed-commands"
    return None


def _validate_axes(native_axes):
    """Native ownership is fail-closed: malformed input abstains."""
    if not isinstance(native_axes, (list, tuple)) or len(native_axes) != 2:
        return None
    if not all(isinstance(a, bool) for a in native_axes):
        return None
    return (not native_axes[0], not native_axes[1])


def _segments(parsed):
    """Straight segments as (ia, ib, a, b); None when curved."""
    segs = []
    for contour in parsed["contours"]:
        for seg in contour:
            if seg[0] != "line":
                return None
            segs.append((seg[1], seg[2], parsed["oncurve"][seg[1]],
                         parsed["oncurve"][seg[2]]))
    return segs


def _orient(a, b, c):
    """Exact orientation sign over 26.6-range dyadic coordinates."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _touches(p, a, b):
    return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) \
        and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])


def _has_ambiguous_contact(segments):
    """True when non-joint segment contact forbids the polygon class.

    Restricted class: non-overlapping closed polygonal outlines where
    every segment contact is a shared contour joint. Exact orientation
    over 26.6-range dyadic input; off-grid input is evaluated without
    that guarantee and any positive detection still abstains.
    """
    for ia, ib, (ax, ay), (bx, by) in segments:
        if ia == ib or (ax == bx and ay == by):
            return True
    n = len(segments)
    for i in range(n):
        ia, ib, p1, p2 = segments[i]
        for j in range(i + 1, n):
            ja, jb, p3, p4 = segments[j]
            if ia in (ja, jb) or ib in (ja, jb):
                continue
            o1 = _orient(p1, p2, p3)
            o2 = _orient(p1, p2, p4)
            o3 = _orient(p3, p4, p1)
            o4 = _orient(p3, p4, p2)
            if o1 == 0 and _touches(p3, p1, p2):
                return True
            if o2 == 0 and _touches(p4, p1, p2):
                return True
            if o3 == 0 and _touches(p1, p3, p4):
                return True
            if o4 == 0 and _touches(p2, p3, p4):
                return True
            if ((o1 > 0) != (o2 > 0)) and ((o3 > 0) != (o4 > 0)):
                return True
    return False


def axis_score(points, segments, center, axis):
    """Hobby sec 3.5 match distance for map (14) at one axis position."""
    worst = 0.0
    for x, y in points:
        qx, qy = (2.0 * center - x, y) if axis == "x" else (x, 2.0 * center - y)
        best = math.inf
        for _, _, (ax, ay), (bx, by) in segments:
            dx, dy = bx - ax, by - ay
            den = dx * dx + dy * dy
            if den == 0.0:
                dist = math.hypot(qx - ax, qy - ay)
            else:
                t = ((qx - ax) * dx + (qy - ay) * dy) / den
                t = max(0.0, min(1.0, t))
                dist = math.hypot(qx - (ax + t * dx), qy - (ay + t * dy))
            if dist < best:
                best = dist
        if best > worst:
            worst = best
    return worst


def _candidate_centers(points, axis):
    """Pair midpoints sharing the invariant coordinate, canonical order."""
    inv = 1 if axis == "x" else 0
    mov = 0 if axis == "x" else 1
    cands = set()
    n = len(points)
    for i in range(n):
        for j in range(i + 1, n):
            if points[i][inv] == points[j][inv]:
                cands.add((points[i][mov] + points[j][mov]) / 2.0)
    lo = min(p[mov] for p in points)
    hi = max(p[mov] for p in points)
    if hi - lo > _EXTENT_TOL:
        cands.add((lo + hi) / 2.0)
    return sorted(cands)


def certify(points, segments, axis):
    """Best axis position and its Hobby match distance, deterministic."""
    best = (math.inf, None)
    for c in _candidate_centers(points, axis):
        s = axis_score(points, segments, c, axis)
        if s < best[0]:
            best = (s, c)
    if best[1] is None:
        return None, math.inf
    c0 = best[1]
    steps = int(round(_REFINE_HALF_RANGE / _REFINE_STEP))
    for k in range(-steps, steps + 1):
        c = c0 + k * _REFINE_STEP
        s = axis_score(points, segments, c, axis)
        if s < best[0]:
            best = (s, c)
    return best[1], best[0]


def detect_axis(source_commands, axis="x"):
    """Certified center or None; control-arm recognition only."""
    try:
        parsed = parse_commands(source_commands)
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        return None
    points = [tuple(p) for p in parsed["oncurve"]]
    if len(points) < 3:
        return None
    segments = _segments(parsed)
    if not segments:
        return None
    mov = 0 if axis == "x" else 1
    if max(p[mov] for p in points) - min(p[mov] for p in points) <= _EXTENT_TOL:
        return None
    center, score = certify(points, segments, axis)
    if center is None or score > EPS_REC:
        return None
    return center


def _slab_interval_from_crit(points, segments, axis, crit):
    """Reflection-pair midpoint interval over open-slab end limits.

    Sorted crossings at each slab end pair outer-to-inner; an odd middle
    crossing stands alone. Exactly symmetric input yields the axis at
    every measurement.
    """
    mov = 0 if axis == "x" else 1
    sweep = 1 if axis == "x" else 0
    meas = []
    skipped = 0
    for lo, hi in zip(crit, crit[1:]):
        if not hi > lo:
            continue
        span = []
        for _, _, (ax, ay), (bx, by) in segments:
            u1, v1 = (ax, ay)[sweep], (ax, ay)[mov]
            u2, v2 = (bx, by)[sweep], (bx, by)[mov]
            if u1 == u2:
                continue
            if (u1 <= lo and u2 >= hi) or (u2 <= lo and u1 >= hi):
                span.append((u1, v1, u2, v2))
        if len(span) < 2:
            skipped += 1
            continue
        for end in (lo, hi):
            xs = sorted(v1 + (end - u1) * (v2 - v1) / (u2 - u1)
                       for u1, v1, u2, v2 in span)
            n = len(xs)
            for i in range(n // 2):
                meas.append((xs[i] + xs[n - 1 - i]) / 2.0)
            if n % 2:
                meas.append(xs[n // 2])
    if not meas:
        return None
    return (min(meas), max(meas), len(meas), skipped)


def slab_interval(points, segments, axis):
    """Source approximate-axis interval from slab-end pair midpoints."""
    sweep = 1 if axis == "x" else 0
    crit = sorted({p[sweep] for p in points})
    if len(crit) < 2:
        return None
    return _slab_interval_from_crit(points, segments, axis, crit)


def axis_interval(source_commands, axis="x"):
    """Public slab-interval summary or None for unsupported input."""
    if _validate_commands(source_commands) is not None:
        return None
    try:
        parsed = parse_commands(source_commands)
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        return None
    points = [tuple(p) for p in parsed["oncurve"]]
    segments = _segments(parsed)
    if not segments:
        return None
    got = slab_interval(points, segments, axis)
    if got is None:
        return None
    cmin, cmax, count, skipped = got
    return {"cmin": cmin, "cmax": cmax, "mid": (cmin + cmax) / 2.0,
            "n": count, "skipped_slabs": skipped}


def _shifted(upstream_commands, dx, dy):
    """Rigid shift in f32; untouched axes keep floats and bits verbatim."""
    out = []
    for cmd in upstream_commands:
        if cmd["op"] in ("move_to", "line_to"):
            item = dict(cmd)
            if dx != 0.0:
                nx = _f32(cmd["x"] + dx)
                item["x"] = nx
                item["x_bits"] = _f32_bits(nx)
            if dy != 0.0:
                ny = _f32(cmd["y"] + dy)
                item["y"] = ny
                item["y_bits"] = _f32_bits(ny)
            out.append(item)
        else:
            out.append(dict(cmd))
    return out


def _width_delta(upstream_commands, candidate_commands):
    """Maximum straight-segment length change from stored coordinates."""
    def lengths(commands):
        parsed = parse_commands(commands)
        out = []
        for contour in parsed["contours"]:
            for seg in contour:
                if seg[0] != "line":
                    return None
                a = parsed["oncurve"][seg[1]]
                b = parsed["oncurve"][seg[2]]
                out.append(math.hypot(b[0] - a[0], b[1] - a[1]))
        return out
    old, new = lengths(upstream_commands), lengths(candidate_commands)
    if old is None or new is None or len(old) != len(new) or not old:
        return None
    return max(abs(a - b) for a, b in zip(old, new))


def _place(upstream_commands, dx, dy):
    """Build the shifted candidate; exactness gates fail closed."""
    for cmd in upstream_commands:
        if cmd["op"] not in ("move_to", "line_to"):
            continue
        for pos, delta in ((0, dx), (1, dy)):
            if delta == 0.0:
                continue
            coord = cmd["x"] if pos == 0 else cmd["y"]
            if not _on_grid(coord) or not _on_grid(delta):
                return None, "unrepresentable-shift", None
            if not math.isfinite(_f32(coord + delta)):
                return None, "unrepresentable-shift", None
    candidate = _shifted(upstream_commands, dx, dy)
    width_delta = _width_delta(upstream_commands, candidate)
    if width_delta is None or width_delta != 0.0:
        return None, "width-check-failed", width_delta
    for cmd in candidate:
        if cmd["op"] in ("move_to", "line_to"):
            if _f32(cmd["x"]) != cmd["x"] or _f32(cmd["y"]) != cmd["y"]:
                return None, "width-check-failed", width_delta
    return candidate, None, width_delta


def _common_inputs(source_commands, upstream_commands, native_axes):
    """Strict validation shared by both arms; fail-closed abstention."""
    free = _validate_axes(native_axes)
    if free is None:
        return None, {"commands": upstream_commands,
                      "candidate_commands": upstream_commands,
                      "applied": False, "reason": "malformed-native-axes",
                      "diagnostics": {"arm": None, "axes": {}}}
    bad = _validate_commands(source_commands)
    if bad is None:
        bad = _validate_commands(upstream_commands)
    if bad is not None:
        if bad not in ("malformed-commands", "empty-outline"):
            bad = "malformed-commands"
        return None, {"commands": upstream_commands,
                      "candidate_commands": upstream_commands,
                      "applied": False, "reason": bad,
                      "diagnostics": {"arm": None, "axes": {}}}
    try:
        if not check_correspondence(source_commands, upstream_commands):
            return None, {"commands": upstream_commands,
                          "candidate_commands": upstream_commands,
                          "applied": False, "reason": "no-correspondence",
                          "diagnostics": {"arm": None,
                                          "native_axes": list(native_axes),
                                          "axes": {}}}
        parsed = parse_commands(source_commands)
        up_parsed = parse_commands(upstream_commands)
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        return None, {"commands": upstream_commands,
                      "candidate_commands": upstream_commands,
                      "applied": False, "reason": "malformed-commands",
                      "diagnostics": {"arm": None, "axes": {}}}
    points = [tuple(p) for p in parsed["oncurve"]]
    up_points = [tuple(p) for p in up_parsed["oncurve"]]
    if len(points) < 3:
        return None, {"commands": upstream_commands,
                      "candidate_commands": upstream_commands,
                      "applied": False, "reason": "empty-outline",
                      "diagnostics": {"arm": None, "axes": {}}}
    segments = _segments(parsed)
    up_segments = _segments(up_parsed)
    if segments is None or up_segments is None:
        return None, {"commands": upstream_commands,
                      "candidate_commands": upstream_commands,
                      "applied": False, "reason": "curves-unsupported",
                      "diagnostics": {"arm": None, "axes": {}}}
    if _has_ambiguous_contact(segments) \
            or _has_ambiguous_contact(up_segments):
        return None, {"commands": upstream_commands,
                      "candidate_commands": upstream_commands,
                      "applied": False, "reason": "ambiguous-overlap",
                      "diagnostics": {"arm": None, "axes": {}}}
    return ({"free": free, "points": points, "up_points": up_points,
             "segments": segments, "up_segments": up_segments}, None)


def _fit_control(common, upstream_commands, size_px, native_axes):
    diagnostics = {"arm": ARM_CONTROL, "eps_rec": EPS_REC, "size_px": size_px,
                   "native_axes": list(native_axes), "axes": {}}
    shift = [0.0, 0.0]
    for pos, axis in enumerate(("x", "y")):
        entry = {"free": common["free"][pos]}
        diagnostics["axes"][axis] = entry
        if not common["free"][pos]:
            entry["reason"] = "native-owned"
            continue
        center, score = certify(common["points"], common["segments"], axis)
        entry["c_source"] = center
        entry["score_source"] = score
        if center is None or score > EPS_REC:
            entry["reason"] = "no-near-reflection"
            continue
        up_score = axis_score(common["up_points"], common["up_segments"],
                              center, axis)
        entry["score_upstream"] = up_score
        if up_score > EPS_REC:
            entry["reason"] = "upstream-broke-symmetry"
            continue
        target = _nearest_half(center)
        delta = _quantize_64(target - center)
        entry["target"] = target
        entry["shift"] = delta
        entry["residual"] = (center + delta) - target
        if delta == 0.0:
            entry["reason"] = "already-centered"
            continue
        entry["reason"] = "certified"
        shift[pos] = delta
    if shift == [0.0, 0.0]:
        reasons = [diagnostics["axes"][a].get("reason") for a in ("x", "y")]
        first = next((r for r in reasons if r), "abstained")
        return {"commands": upstream_commands,
                "candidate_commands": upstream_commands,
                "applied": False, "reason": first, "diagnostics": diagnostics}
    candidate, fail, width_delta = _place(upstream_commands, shift[0], shift[1])
    diagnostics["shift"] = shift
    diagnostics["width_delta_max"] = width_delta
    if fail is not None:
        return {"commands": upstream_commands,
                "candidate_commands": upstream_commands,
                "applied": False, "reason": fail, "diagnostics": diagnostics}
    return {"commands": candidate, "candidate_commands": candidate,
            "applied": True, "reason": "applied", "diagnostics": diagnostics}


def _fit_phase_range(common, upstream_commands, size_px, native_axes):
    diagnostics = {"arm": ARM_PHASE, "size_px": size_px,
                   "native_axes": list(native_axes),
                   "cell_radius": CELL_RADIUS, "axes": {}}
    shift = [0.0, 0.0]
    for pos, axis in enumerate(("x", "y")):
        entry = {"free": common["free"][pos]}
        diagnostics["axes"][axis] = entry
        if not common["free"][pos]:
            entry["reason"] = "native-owned"
            continue
        got = slab_interval(common["points"], common["segments"], axis)
        if got is None:
            entry["reason"] = "no-paired-spans"
            continue
        cmin, cmax, count, skipped = got
        entry["cmin"] = cmin
        entry["cmax"] = cmax
        entry["n_pairs"] = count
        entry["skipped_slabs"] = skipped
        entry["interval_mid"] = (cmin + cmax) / 2.0
        up_got = slab_interval(common["up_points"], common["up_segments"],
                               axis)
        if up_got is None:
            entry["reason"] = "upstream-phase-diverged"
            continue
        umin, umax, _, _ = up_got
        entry["upstream_cmin"] = umin
        entry["upstream_cmax"] = umax
        umid = (umin + umax) / 2.0
        target = _nearest_half(umid)
        delta = _quantize_64(target - umid)
        entry["placement_mid"] = umid
        entry["target"] = target
        entry["shift"] = delta
        entry["residual"] = (umid + delta) - target
        if abs(delta) > MOVE_BOUND:
            entry["reason"] = "movement-exceeds-bound"
            continue
        if not (target - CELL_RADIUS <= cmin + delta
                and cmax + delta <= target + CELL_RADIUS):
            entry["reason"] = "phase-cell-uncontained"
            continue
        if not (target - CELL_RADIUS <= umin + delta
                and umax + delta <= target + CELL_RADIUS):
            entry["reason"] = "upstream-phase-diverged"
            continue
        if delta == 0.0:
            entry["reason"] = "already-centered"
            continue
        entry["reason"] = "certified"
        shift[pos] = delta
    if shift == [0.0, 0.0]:
        reasons = [diagnostics["axes"][a].get("reason") for a in ("x", "y")]
        first = next((r for r in reasons if r), "abstained")
        return {"commands": upstream_commands,
                "candidate_commands": upstream_commands,
                "applied": False, "reason": first, "diagnostics": diagnostics}
    candidate, fail, width_delta = _place(upstream_commands, shift[0], shift[1])
    diagnostics["shift"] = shift
    diagnostics["width_delta_max"] = width_delta
    if fail is not None:
        return {"commands": upstream_commands,
                "candidate_commands": upstream_commands,
                "applied": False, "reason": fail, "diagnostics": diagnostics}
    return {"commands": candidate, "candidate_commands": candidate,
            "applied": True, "reason": "applied-phase-range",
            "diagnostics": diagnostics}


def fit(source_commands, upstream_commands, size_px, native_axes=(False, False),
        arm=ARM_CONTROL):
    """Rigid whole-outline placement under certified reflection.

    Arm 'strict-quantum' is the legacy control; arm 'phase-range' is the
    experimental Hersch phase-cell arm. Abstention returns the exact
    upstream commands.
    """
    if arm not in _ALLOWED_ARMS:
        return {"commands": upstream_commands,
                "candidate_commands": upstream_commands,
                "applied": False, "reason": "malformed-arm",
                "diagnostics": {"arm": None, "axes": {}}}
    common, abstention = _common_inputs(source_commands, upstream_commands,
                                        native_axes)
    if abstention is not None:
        return abstention
    if arm == ARM_PHASE:
        return _fit_phase_range(common, upstream_commands, size_px,
                                native_axes)
    return _fit_control(common, upstream_commands, size_px, native_axes)
