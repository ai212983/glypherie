"""Isolated curved-stroke width prototype (Hobby section 6).

Source derivation: Hobby section 3.2, eq (4)-(5) (medial width as twice the
radius, signed projected relative error); section 3.6, eq (17)
(relative-error coupling preserving contrast); section 6 (medial contacts
map through polygonal intermediates to true Bezier points; distortion
extends to curve controls); eq (31)-(33) (Bernstein basis, midpoint
quadrature, frozen-normal displacement) via the shared ``prototype.System``.
See the equation audit for checked notation and frozen-coefficient
qualifications.

Ownership rule (new feature; old ``direct_diagonal`` untouched): curve
controls of supplied recognized pairs are fitter-movable on non-native
axes; native-owned coordinates stay exact at upstream. No other pin relaxes.
``curve_clearance.compare_commands`` requires candidate curve controls
bit-identical to upstream (its ``curves-moved`` branch), so it cannot
certify a moving-curve candidate; delivery instead uses exact station-disk
(``disk_clear``) and hull-separation certificates, which are weaker than a
full arrangement comparison. Sampled contact measurements are evidence
only, never topology claims.
"""

import math
import struct

import numpy as np

from experiments.hobby_fitting import curve_clearance as cc
from experiments.hobby_fitting import exact_topology as topology
from experiments.hobby_fitting.prototype import Sample, System, width_weight
from experiments.hobby_fitting.real_outline import (
    check_correspondence,
    parse_commands,
)

HEADROOM = math.sqrt(2.0) / 128.0


def _round_26_6(x):
    """Nearest 1/64 unit, ties toward positive infinity (native grid)."""
    return math.floor(x * 64 + 0.5) / 64


def _f32bits(x):
    return struct.unpack(">I", struct.pack(">f", x))[0]


def _valid_axes(native_axes):
    try:
        return (len(native_axes) == 2
                and all(type(v) is bool for v in native_axes))
    except TypeError:
        return False


def _eval(ctrls, t):
    n = len(ctrls) - 1
    p = np.zeros(2)
    for i, c in enumerate(ctrls):
        p += math.comb(n, i) * (1 - t) ** (n - i) * t ** i * np.asarray(c, float)
    return p


def _deriv(ctrls, t):
    n = len(ctrls) - 1
    diffs = [np.asarray(ctrls[i + 1], float) - np.asarray(ctrls[i], float)
             for i in range(n)]
    p = np.zeros(2)
    for i, c in enumerate(diffs):
        p += math.comb(n - 1, i) * (1 - t) ** (n - 1 - i) * t ** i * c
    return n * p


def _unit(v):
    n = float(np.linalg.norm(v))
    if n <= 0:
        raise ValueError("zero tangent")
    return np.asarray(v, float) / n


def _cross(a, b):
    return float(a[0] * b[1] - a[1] * b[0])


def _sample(ctrl, t):
    """Affine correspondence: quadratic Bernstein for quads (Hobby (31)
    is cubic-only in the shared API; the quadratic basis is the same
    construction at degree two), else the shared cubic constructor."""
    if len(ctrl) == 3:
        if not 0 <= t <= 1:
            raise ValueError("t in [0,1] required")
        return Sample(tuple(zip([int(v) for v in ctrl],
                                ((1 - t) ** 2, 2 * t * (1 - t), t * t))))
    return Sample.cubic([int(v) for v in ctrl], t)


def _add_quad_shape(system, ctrl, intervals=16):
    """Quadratic form of the (31)-(33) + (2),(3) construction.

    The shared ``System.curve`` implements cubics only; this mirrors its
    algebra exactly with quadratic Bernstein weights and derivative
    weights (-2(1-t), 2(1-t)-2t, 2t). Same group names feed the same
    upstream-gap constant substitution.
    """
    from experiments.hobby_fitting.prototype import Sample as _S
    if len(ctrl) != 3:
        raise ValueError("a quad needs three controls")
    get = system.point
    controls = np.array([get(_S.vertex(i)) for i in ctrl])
    for j in range(intervals):
        t = (j + 0.5) / intervals
        basis = np.array([(1 - t) ** 2, 2 * t * (1 - t), t * t])
        pt = basis @ controls
        _ = pt
        derivative = (np.array([-2 * (1 - t), 2 * (1 - t) - 2 * t, 2 * t])
                      @ controls)
        speed = float(np.linalg.norm(derivative))
        if speed <= 0:
            raise ValueError("zero curve tangent")
        normal = np.array([derivative[1], -derivative[0]]) / speed
        row = sum(float(w) * system.basis(_S.vertex(i))
                  for w, i in zip(basis, ctrl))
        system.add("curve-position", np.outer(row, normal).ravel()
                   * math.sqrt(1000 / system.height ** 3
                               * speed / intervals))
        d_basis = sum(float(w) * system.basis(_S.vertex(i))
                      for w, i in zip([-2 * (1 - t), 2 * (1 - t) - 2 * t,
                                       2 * t], ctrl))
        factor = math.sqrt(25 / system.height * speed / intervals) / speed
        system.add("curve-stretch",
                   np.outer(d_basis, derivative / speed).ravel() * factor)
        system.add("curve-bend",
                   np.outer(d_basis, normal).ravel() * factor)


def curves_of(parsed):
    """True Bezier curves with global control indices into on/offcurve."""
    no = len(parsed["oncurve"])
    out = []
    for contour in parsed["contours"]:
        for seg in contour:
            if seg[0] == "quad":
                out.append({"kind": "quad", "idx": [seg[2], no + seg[1], seg[3]]})
            elif seg[0] == "cubic":
                out.append({"kind": "cubic",
                            "idx": [seg[3], no + seg[1], no + seg[2], seg[4]]})
    return out


def _ctrl_coords(curve, points):
    return [tuple(points[i]) for i in curve["idx"]]


def _flatten(ctrls, depth=4):
    return [_eval(ctrls, k / 2 ** depth) for k in range(2 ** depth + 1)]


def _tangent_at(ctrls, t):
    return _unit(_deriv(ctrls, t))


def measure_contacts(commands, depth=4):
    """Sampled opposing-contact inventory; measurement evidence only.

    For each curve midpoint, the nearest flattened point on another curve
    with strictly antiparallel tangent is reported with its chord width,
    normal and X-effectibility. Chord width is not the medial radius
    (audit of (4)); nothing here certifies topology or opposition.
    """
    parsed = parse_commands(commands)
    points = parsed["oncurve"] + parsed["offcurve"]
    curves = curves_of(parsed)
    flats = []
    for ci, c in enumerate(curves):
        ctrls = _ctrl_coords(c, points)
        try:
            mid_tan = _tangent_at(ctrls, 0.5)
        except ValueError:
            continue
        tans = []
        for k in range(2 ** depth + 1):
            try:
                tans.append(_tangent_at(ctrls, k / 2 ** depth))
            except ValueError:
                tans.append(None)
        flats.append({"curve": ci, "mid_pt": _eval(ctrls, 0.5),
                      "mid_tan": mid_tan, "pts": _flatten(ctrls, depth),
                      "tans": tans})
    contacts = []
    for f in flats:
        best = None
        for g in flats:
            if f["curve"] == g["curve"]:
                continue
            for q, gt in zip(g["pts"], g["tans"]):
                if gt is None:
                    continue
                dot = float(np.dot(f["mid_tan"], gt))
                if dot >= 0:
                    continue
                d = float(np.linalg.norm(np.asarray(q) - f["mid_pt"]))
                if d <= 0:
                    continue
                if best is None or d < best[0]:
                    best = (d, g["curve"], q, dot)
        if best is None:
            continue
        d, j, q, dot = best
        n = (np.asarray(q) - f["mid_pt"]) / d
        contacts.append({"curve": f["curve"], "opposing_curve": j,
                         "chord_width": d, "normal": [float(n[0]), float(n[1])],
                         "effectibility_x": abs(float(n[0])),
                         "antiparallel_dot": dot})
    ws = [c["chord_width"] for c in contacts]
    effs = [c["effectibility_x"] for c in contacts]
    return {"contacts": contacts, "n_curves": len(curves),
            "summary": {"n_measured": len(contacts),
                        "width_min": min(ws) if ws else None,
                        "width_max": max(ws) if ws else None,
                        "eff_x_min": min(effs) if effs else None,
                        "eff_x_max": max(effs) if effs else None}}


def _match_width(measured, curve):
    for c in measured["contacts"]:
        if c["curve"] == curve:
            return c["chord_width"]
    return None


def diagnose_glyph(source_commands, selective_commands, auto_commands,
                   reference, native_axes=(False, True)):
    """Real-glyph feasibility diagnostics across the three geometries.

    Exact command correspondence aligns identical curve indices; reported
    widths are sampled chord measurements, not certified medial values.
    No fitting, no thresholds.
    """
    geos = {"source": source_commands, "selective": selective_commands,
            "auto": auto_commands}
    ops = [[c.get("op") for c in g] for g in geos.values()]
    if not (ops[0] == ops[1] == ops[2]):
        return {"correspondence": False}
    measured = {k: measure_contacts(v) for k, v in geos.items()}
    anchors = (reference.get("anchors") if isinstance(reference, dict)
               else None) or []
    rows = []
    for c in measured["selective"]["contacts"]:
        rows.append({"curve": c["curve"],
                     "opposing_curve": c["opposing_curve"],
                     "normal": c["normal"],
                     "effectibility_x": c["effectibility_x"],
                     "width_source": _match_width(measured["source"],
                                                  c["curve"]),
                     "width_selective": c["chord_width"],
                     "width_auto": _match_width(measured["auto"], c["curve"])})
    return {"correspondence": True, "native_axes": list(native_axes),
            "anchors": [{"source_width": a["source_width"],
                         "fitted_width": a["fitted_width"],
                         "rel": a["rel"]} for a in anchors],
            "measured": {k: v["summary"] for k, v in measured.items()},
            "rows": rows}


def _abstain(upstream_commands, reason, **extra):
    result = {"candidate_commands": upstream_commands, "applied": False,
              "reason": reason, "widths": None}
    result.update(extra)
    return result


def _quad_interval_ok(src_ctrls, cand_ctrls):
    """Entire-interval tangent/curvature certificate for quadratics.

    For a quadratic, cross(d1, d2) equals 4*cross(C-P0, P1-C) at every
    parameter, so the control polygon alone certifies curvature sign
    over the whole interval. d1(t) is a positive combination of the
    two legs, so strict positivity of all four leg dot products keeps
    every candidate tangent within 90 degrees of every source tangent
    over the whole interval. No sampling, no angular threshold.
    """
    (s0, sc, s1), (c0, cc_, c1) = src_ctrls, cand_ctrls
    Us = np.asarray(sc, float) - np.asarray(s0, float)
    Vs = np.asarray(s1, float) - np.asarray(sc, float)
    Uc = np.asarray(cc_, float) - np.asarray(c0, float)
    Vc = np.asarray(c1, float) - np.asarray(cc_, float)
    if any(float(np.linalg.norm(v)) <= 0 for v in (Us, Vs, Uc, Vc)):
        return False, "degenerate-leg"
    ss, cs = _cross(Us, Vs), _cross(Uc, Vc)
    if ss == 0.0 or cs == 0.0:
        return False, "degenerate-curvature"
    if np.sign(cs) != np.sign(ss):
        return False, "curvature-sign"
    for u, v in ((Uc, Us), (Vc, Vs), (Uc, Vs), (Vc, Us)):
        if float(np.dot(u, v)) <= 0:
            return False, "tangent-reversed"
    return True, "clear"


def _pair_curves(pairs):
    seen = []
    for p in pairs:
        ctrls = [[int(v) for v in p[key]] for key in ("a_ctrl", "b_ctrl")]
        ctrls += [[int(v) for v in s] for s in p.get("shape_ctrl", [])]
        for ctrl in ctrls:
            if ctrl not in seen:
                seen.append(ctrl)
    return seen


def fit(source_commands, upstream_commands, size_px, reference,
        native_axes=(False, True), pairs=(), curve_intervals=16):
    """Source-relative curved-width fit; exact upstream on any failure.

    ``pairs`` are supplied recognized contacts (cf. ``System``: recognition
    is a caller responsibility): each carries ``a_ctrl``/``b_ctrl`` global
    control indices, ``a_t``/``b_t`` parameters, an exact ``medial`` point
    with equal radii, and an ``arc`` weight. Width is twice the medial
    radius; curves are moved, never replaced.
    """
    if not _valid_axes(native_axes):
        try:
            return _abstain(upstream_commands, "malformed-native-axes")
        except (KeyError, TypeError, AttributeError):
            return {"candidate_commands": upstream_commands, "applied": False,
                    "reason": "malformed-native-axes", "widths": None}
    try:
        if not check_correspondence(source_commands, upstream_commands):
            return _abstain(upstream_commands, "no-correspondence")
        parsed = parse_commands(source_commands)
        fitted = parse_commands(upstream_commands)
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        return _abstain(upstream_commands, "malformed-commands")
    anchors = (reference.get("anchors") if isinstance(reference, dict)
               else None)
    if not anchors:
        return _abstain(upstream_commands, "no-reference-anchors")
    if not pairs:
        return _abstain(upstream_commands, "no-supplied-pairs",
                        fixed={"native_axes": list(native_axes[:2])})
    try:
        no = len(parsed["oncurve"])
        points = parsed["oncurve"] + parsed["offcurve"]
        up = fitted["oncurve"] + fitted["offcurve"]
        if len(up) != len(points):
            return _abstain(upstream_commands, "no-correspondence")
        base = np.asarray(points, float)
        upstream = np.asarray(up, float)
        gaps = upstream - base
        if not np.isfinite(base).all() or not np.isfinite(upstream).all():
            return _abstain(upstream_commands, "malformed-commands")
        owned = tuple(i for i, on in enumerate(native_axes[:2]) if on)
        involved = set()
        for p in pairs:
            involved.update(int(v) for v in p["a_ctrl"])
            involved.update(int(v) for v in p["b_ctrl"])
        if any(not 0 <= v < len(points) for v in involved):
            return _abstain(upstream_commands, "malformed-pairs")
        system = System([tuple(p) for p in points], size_px)
        pair_ctrls = _pair_curves(pairs)
        for ctrl in pair_ctrls:
            if len(ctrl) == 3:
                _add_quad_shape(system, ctrl, intervals=curve_intervals)
            else:
                system.curve(ctrl, intervals=curve_intervals)
        pair_objs = []
        for p in pairs:
            ta, tb = float(p["a_t"]), float(p["b_t"])
            if not 0 <= ta <= 1 or not 0 <= tb <= 1 or not p["arc"] > 0:
                return _abstain(upstream_commands, "malformed-pairs")
            try:
                pair = system.pair(
                    _sample(p["a_ctrl"], ta),
                    _sample(p["b_ctrl"], tb),
                    float(p["arc"]), "ink",
                    medial=np.asarray(p["medial"], float))
            except (ValueError, TypeError):
                return _abstain(upstream_commands, "unequal-medial-radii")
            pair_objs.append((pair, p))
        # Incremental formulation: unknowns are displacements from
        # upstream (delta), candidate = upstream + delta. Shape rows
        # penalize deviation from upstream, so their constant is zero;
        # width rows carry the total: pair.error@(gaps+delta) + anchor
        # relative change. Pins need no gap substitution since delta is
        # zero there by construction (absent columns).
        rows = []
        for group, row, const in system.rows:
            row = np.asarray(row, float)
            if group in ("curve-position", "curve-stretch", "curve-bend"):
                const = 0.0
            rows.append((group, row, float(const)))
        for pair, p in pair_objs:
            err_gap = float(np.asarray(pair.error, float) @ gaps.ravel())
            for a in anchors:
                tangent = np.asarray(pair.tangent, float)
                ref_t = np.asarray(a["tangent"], float)
                if float(np.dot(tangent, ref_t)) < 0:
                    tangent = -tangent
                psi = width_weight(pair.width, a["source_width"], tangent,
                                   ref_t, size_px)
                w = float(p["arc"]) * a["length"] * psi
                rows.append(("ink-match", pair.error * math.sqrt(w),
                             (err_gap + a["rel"]) * math.sqrt(w)))
        cols = [(v, axis) for v in sorted(involved) for axis in (0, 1)
                if axis not in owned]
        if not cols:
            return _abstain(upstream_commands, "all-axes-native")
        mat = np.stack([r for _, r, _ in rows])
        rhs = np.array([-c for _, _, c in rows], float)
        sub = np.column_stack([mat[:, v * 2 + axis] for v, axis in cols])
        sol, _, _, _ = np.linalg.lstsq(sub, rhs, rcond=None)
        widths = [pair.width for pair, _ in pair_objs]
        bound = min(widths) / 2 - HEADROOM
        if not bound >= HEADROOM:
            return _abstain(upstream_commands, "movement-budget-empty")
        peak = max((abs(float(v)) for v in sol), default=0.0)
        if peak > bound:
            sol = sol * (bound / peak)
        cand = upstream.copy()
        for (v, axis), d in zip(cols, sol):
            if float(d) == 0.0:
                continue
            cand[v][axis] = upstream[v][axis] + float(d)
        for v, axis in cols:
            if cand[v][axis] != upstream[v][axis]:
                cand[v][axis] = _round_26_6(float(cand[v][axis]))
        for v in range(len(points)):
            for axis in owned:
                if cand[v][axis] != upstream[v][axis]:
                    return _abstain(upstream_commands, "native-violated")
        if not _joins_preserved(parsed, upstream, cand,
                                _closed_flags(upstream_commands, parsed)):
            return _abstain(upstream_commands, "tangent-join-changed")
        incident = _incident_curves(parsed)
        for v in range(len(points)):
            if all(cand[v][axis] == upstream[v][axis] for axis in (0, 1)):
                continue
            if v not in incident:
                continue
            for ctrl in incident[v]:
                if len(ctrl) != 3:
                    return _abstain(upstream_commands,
                                    "cubic-interval-uncertified")
                ok, why = _quad_interval_ok(
                    [tuple(base[i]) for i in ctrl],
                    [tuple(cand[i]) for i in ctrl])
                if not ok:
                    return _abstain(upstream_commands, why)
        if not _clearance_ok(pair_objs, cand, parsed, involved, upstream):
            return _abstain(upstream_commands, "clearance-failed")
        out = _emit(upstream_commands, cand, no)
        gate = _substitution_gate(source_commands, upstream_commands, out)
        if not gate["ok"]:
            return _abstain(upstream_commands, "topology-changed",
                            topology=gate["verdict"])
    except (KeyError, TypeError, AttributeError, ArithmeticError,
            ValueError):
        return _abstain(upstream_commands, "malformed-commands")
    widths_out = []
    for pair, p in pair_objs:
        n = np.asarray(pair.normal, float)
        src_w = pair.width
        up_w = float(abs(np.dot(
            _eval([tuple(upstream[i]) for i in p["b_ctrl"]], float(p["b_t"]))
            - _eval([tuple(upstream[i]) for i in p["a_ctrl"]], float(p["a_t"])), n)))
        cand_w = float(abs(np.dot(
            _eval([tuple(cand[i]) for i in p["b_ctrl"]], float(p["b_t"]))
            - _eval([tuple(cand[i]) for i in p["a_ctrl"]], float(p["a_t"])), n)))
        widths_out.append({"source": float(src_w), "upstream": float(up_w),
                           "candidate": float(cand_w)})
    return {"candidate_commands": out, "applied": True, "reason": "fitted",
            "widths": widths_out,
            "diagnostics": {"n_pairs": len(pair_objs),
                            "bound": float(bound),
                            "native_axes": list(native_axes[:2])},
            "topology": gate["verdict"]}


def _closed_flags(commands, parsed):
    """Per-contour closed flags aligned with parsed contours, or None."""
    groups = []
    cur = None
    for cmd in commands:
        op = cmd.get("op") if isinstance(cmd, dict) else None
        if op == "move_to":
            if cur and any(o != "close" for o in cur):
                groups.append(cur)
            cur = []
        elif op in ("line_to", "quad_to", "curve_to", "close"):
            if cur is None:
                return None
            cur.append(op)
        else:
            return None
    if cur and any(o != "close" for o in cur):
        groups.append(cur)
    if len(groups) != len(parsed["contours"]):
        return None
    return [bool(g) and g[-1] == "close" for g in groups]


def _join_legs(parsed, coords, closed_flags):
    """Incident tangent legs at every join, exact Fractions.

    Each join links consecutive primitives in a contour (plus the
    closing weld on closed contours); legs run from the adjacent
    control point (quad control, line far endpoint) to or from the
    joint. Cubic-adjacent pairings are omitted: with a moved cubic
    the gate abstains earlier, and unmoved cubic legs cannot kink.
    Returns [(joint_idx, in_leg, out_leg, incident)].
    """
    no = len(parsed["oncurve"])
    joins = []
    for contour, closed in zip(parsed["contours"], closed_flags):
        segs = [s for s in contour if s[0] in ("line", "quad")]
        for k, seg in enumerate(segs):
            if k == 0 and not closed:
                continue
            prev = segs[k - 1]
            j = seg[2] if seg[0] == "quad" else seg[1]
            if seg[0] == "quad":
                leg_out, v_out = coords[no + seg[1]], no + seg[1]
            else:
                leg_out, v_out = coords[seg[2]], seg[2]
            if prev[0] == "quad":
                leg_in, v_in = coords[no + prev[1]], no + prev[1]
            else:
                leg_in, v_in = coords[prev[1]], prev[1]
            J = coords[j]
            joins.append((j,
                          (J[0] - leg_in[0], J[1] - leg_in[1]),
                          (leg_out[0] - J[0], leg_out[1] - J[1]),
                          (j, v_in, v_out)))
    return joins


def _joins_preserved(parsed, upstream, cand, closed_flags):
    """Exact tangent-direction preservation on all moved joins.

    Every join with a moved incident control keeps both leg directions
    exactly (Fraction cross == 0, forward dot > 0), whether upstream
    was smoothly collinear or merely near-collinear. Unmoved joins
    are bit-identical and need no check. Any violation, degenerate
    leg, or undeterminable contour closure abstains: a kinked smooth
    join (or rotated near-collinear one) must never publish.
    """
    from fractions import Fraction

    def fr(p):
        return (Fraction(p[0]), Fraction(p[1]))

    if closed_flags is None:
        return False
    if len(closed_flags) != len(parsed["contours"]):
        return False
    up = [fr(tuple(u)) for u in upstream]
    new = [fr(tuple(c)) for c in cand]
    old_joins = _join_legs(parsed, up, closed_flags)
    new_joins = _join_legs(parsed, new, closed_flags)
    new_by_joint = {}
    for e in new_joins:
        new_by_joint.setdefault(e[0], []).append(e)
    for j, lin, lout, incident in old_joins:
        if all(tuple(upstream[v]) == tuple(cand[v]) for v in incident):
            continue
        match = [e for e in new_by_joint.get(j, [])
                 if e[3] == incident]
        if not match:
            return False
        _, clin, clout, _ = match[0]
        for a, b in ((lin, clin), (lout, clout)):
            if (a[0] == 0 and a[1] == 0) or (b[0] == 0 and b[1] == 0):
                return False
            if a[0] * b[1] != a[1] * b[0]:
                return False
            if a[0] * b[0] + a[1] * b[1] <= 0:
                return False
    return True


def _incident_curves(parsed):
    """All quad/cubic control sets incident to each moved vertex."""
    no = len(parsed["oncurve"])
    incident = {}
    for contour in parsed["contours"]:
        for seg in contour:
            if seg[0] == "quad":
                ctrl = [seg[2], no + seg[1], seg[3]]
                for v in ctrl:
                    incident.setdefault(v, []).append(ctrl)
            elif seg[0] == "cubic":
                ctrl = [seg[3], no + seg[1], no + seg[2], seg[4]]
                for v in ctrl:
                    incident.setdefault(v, []).append(ctrl)
    return incident


def _segments(parsed, coords):
    """Line segments (including closure) as endpoint pairs."""
    segs = []
    for contour in parsed["contours"]:
        for seg in contour:
            if seg[0] == "line":
                segs.append(((seg[1], tuple(coords[seg[1]])),
                             (seg[2], tuple(coords[seg[2]]))))
    return segs


def _hull_pair_ok(new, other):
    for hp in cc.piece_hulls(list(new), 2):
        for hq in cc.piece_hulls(list(other), 2):
            if _shares_endpoint(new, other):
                if not cc.hulls_meet_only_at(
                        hp, hq, _shared_point(new, other)):
                    return False
            elif not cc.strictly_disjoint(hp, hq):
                return False
    return True


def _shares_endpoint(a, b):
    return any(p == q for p in (a[0], a[-1]) for q in (b[0], b[-1]))


def _shared_point(a, b):
    for p in (a[0], a[-1]):
        for q in (b[0], b[-1]):
            if p == q:
                return p
    raise ValueError("no shared endpoint")


def _clearance_ok(pair_objs, cand, parsed, involved, upstream):
    """All primitive interactions: disks, hulls, swept lines.

    Station disks clear every fixed curve and fixed line; moved-curve
    hulls separate from fixed-curve hulls and from each other
    (moved/moved); swept moved lines clear fixed curves via
    edge_vs_curve_clear and separate from moved-curve hulls. Closure
    lines are included through the parsed contours.
    """
    pts = parsed["oncurve"] + parsed["offcurve"]
    fixed_curves = []
    moved_curves = []
    for c in curves_of(parsed):
        ctrls = [tuple(pts[i]) for i in c["idx"]]
        new = [tuple(cand[i]) for i in c["idx"]]
        if set(c["idx"]) & involved:
            moved_curves.append((c, ctrls, new))
        else:
            fixed_curves.append((c, ctrls, new))
    up = [tuple(u) for u in upstream]
    moved_lines, fixed_lines = [], []
    for (i, _), (j, _) in _segments(parsed, up):
        new = (tuple(cand[i]), tuple(cand[j]))
        old_seg = (tuple(up[i]), tuple(up[j]))
        (moved_lines if old_seg != new else fixed_lines).append(
            (i, j, old_seg, new))
    for pair, p in pair_objs:
        qa = _eval([tuple(cand[i]) for i in p["a_ctrl"]], float(p["a_t"]))
        qb = _eval([tuple(cand[i]) for i in p["b_ctrl"]], float(p["b_t"]))
        center = tuple((np.asarray(qa) + np.asarray(qb)) / 2)
        radius = float(np.linalg.norm(np.asarray(qb) - np.asarray(qa))) / 2
        for _, _, fix_new in fixed_curves:
            ok, _ = cc.disk_clear(center, radius, fix_new)
            if not ok:
                return False
        for _, _, old_seg, _ in fixed_lines:
            if not _seg_open_clear(center, radius, old_seg):
                return False
    live = [(c, n) for c, s, n in moved_curves
            if any(tuple(cand[i]) != tuple(up[i]) for i in c["idx"])]
    for k, (_, new) in enumerate(live):
        for _, _, fix_new in fixed_curves:
            if not _hull_pair_ok(new, fix_new):
                return False
        for n, (_, other) in enumerate(live):
            if n != k and not _hull_pair_ok(new, other):
                return False
    for i, j, old_seg, new_seg in moved_lines:
        for _, _, fix_new in fixed_curves:
            ok, _ = cc.edge_vs_curve_clear(old_seg, new_seg, fix_new)
            if not ok:
                return False
        from fractions import Fraction

        def fr(p):
            return (Fraction(p[0]), Fraction(p[1]))

        swept = cc.convex_hull([fr(old_seg[0]), fr(old_seg[1]),
                                fr(new_seg[0]), fr(new_seg[1])])
        for c, new in live:
            shared = [fr(tuple(cand[v])) for v in (i, j) if v in c["idx"]]
            for hull in cc.piece_hulls(list(new), 2):
                if cc.strictly_disjoint(swept, hull):
                    continue
                if not shared or not all(
                        cc.hulls_meet_only_at(swept, hull, s)
                        for s in shared):
                    return False
    return True


def _seg_open_clear(center, radius, seg):
    """Exact: fixed segment avoids the open station disk (touch allowed)."""
    from fractions import Fraction

    def fr(p):
        return (Fraction(p[0]), Fraction(p[1]))

    M, r2 = fr(center), Fraction(radius) ** 2
    a, b = fr(seg[0]), fr(seg[1])
    ax, ay = a[0] - M[0], a[1] - M[1]
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


def _substitution_gate(source_commands, upstream_commands, candidate):
    """Finite-invariant gate on certified polyline substitutions.

    Each shape certifies independently via certify_substitution; the
    existing exact checker compares the three substituted outlines, so
    moved curves are allowed (unlike compare_commands' bit-identity
    guard, which is not called). Matching finite invariants is the
    delivery contract, as in the existing checker; it is not a homotopy
    or optical claim.
    """
    try:
        certs = [cc.certify_substitution(cmds)
                 for cmds in (source_commands, upstream_commands, candidate)]
    except (ArithmeticError, OverflowError, ValueError):
        return {"ok": False, "verdict": {"reason": "certify-error"}}
    if not all(c["ok"] for c in certs):
        return {"ok": False,
                "verdict": {"reason": "uncertified-substitution",
                            "certs": certs}}
    try:
        polys = [cc.build_substituted_commands(cmds)
                 for cmds in (source_commands, upstream_commands, candidate)]
    except ValueError as exc:
        return {"ok": False, "verdict": {"reason": str(exc)}}
    verdict = topology.compare_commands(polys[0], polys[1], polys[2])
    return {"ok": bool(verdict.get("supported") and verdict.get("ok")),
            "verdict": verdict}


def _emit(upstream_commands, cand, no):
    """Rebuild commands, preserving ops/order; refresh float32 bits."""
    out = [dict(c) for c in upstream_commands]
    vals_on = [tuple(cand[i]) for i in range(no)]
    vals_off = [tuple(cand[i]) for i in range(no, len(cand))]
    on_iter, off_iter = iter(vals_on), iter(vals_off)
    for c in out:
        op = c.get("op")
        if op in ("move_to", "line_to"):
            pairs = [(next(on_iter), ("x", "y"))]
        elif op == "quad_to":
            pairs = [(next(off_iter), ("x1", "y1")),
                     (next(on_iter), ("x", "y"))]
        elif op == "curve_to":
            pairs = [(next(off_iter), ("x1", "y1")),
                     (next(off_iter), ("x2", "y2")),
                     (next(on_iter), ("x", "y"))]
        else:
            continue
        for pt, keys in pairs:
            for key in keys:
                c[key] = float(pt[keys.index(key)])
                if key + "_bits" in c:
                    c[key + "_bits"] = _f32bits(c[key])
    return out
