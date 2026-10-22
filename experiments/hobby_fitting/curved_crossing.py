"""Bounded joint curved-crossing fit (Hobby sections 3.2, 3.5, 3.6, 6).

Hobby section 3.2 supplies medial width as twice the radius; section 3.6,
(17) couples relative changes preserving intended contrast; section 3.5,
(14)-(16) supplies approximate-reflection correspondence with retained
source mismatch as finite distortion terms with fixed map (Fk at the
parity target); section 6 maps medial contacts through polygonal
intermediates to true Bezier controls and extends distortion to curve
controls. Hersch section 5 supplies grid-compatible symmetry phase.
Hersch section 2 supplies endpoint derivative relationships for smooth
joins. Forsgren, Gill and Wong supplies the equality-and-bound
formulation. Sharp joins keep orientation, nondegeneracy and forward
legs rather than the upstream corner magnitude; only source-smooth
joints keep exact G1 hard.
"""
# cspell:words Forsgren nondegeneracy onmap offmap oncurve offcurve linalg cmat clower lstsq rcond resid cand ctrls

import math
import statistics

import numpy as np

from experiments.hobby_fitting import attached_diagonal as ad
from experiments.hobby_fitting import curve_clearance as cc
from experiments.hobby_fitting import curved_width as cw
from experiments.hobby_fitting import direct_diagonal as dd
from experiments.hobby_fitting import joint_diagonal as jd
from experiments.hobby_fitting import smooth_curve_fit as scf
from experiments.hobby_fitting.prototype import System, width_weight
from experiments.hobby_fitting.real_outline import (
    check_correspondence,
    parse_commands,
)

HEADROOM = dd.HEADROOM
RESERVE_26_6 = 1.0 / 128.0
CROSS_QUANTUM = 1.0 / 4096.0


def _abstain(upstream_commands, reason, **extra):
    result = {"candidate_commands": upstream_commands,
              "applied": False, "reason": reason}
    result.update(extra)
    return result


def _on_grid(value):
    return math.isfinite(value) and value * 64.0 == round(value * 64.0)


def _anchors(reference):
    anchors = reference.get("anchors") if isinstance(reference, dict) else None
    if not anchors:
        return None
    out = []
    for anchor in anchors:
        try:
            tangent = [float(v) for v in anchor["tangent"]]
            length = float(anchor["length"])
            width = float(anchor["source_width"])
            rel = float(anchor["rel"])
        except (KeyError, TypeError, ValueError, ArithmeticError):
            return None
        if len(tangent) != 2 or not all(math.isfinite(v) for v in tangent):
            return None
        if not (math.isfinite(length) and length > 0):
            return None
        if not (math.isfinite(width) and width > 0):
            return None
        if not math.isfinite(rel):
            return None
        out.append({"tangent": tangent, "length": length,
                    "source_width": width, "rel": rel})
    return out or None


def _command_index(commands, parsed):
    onmap, offmap, oi, fi = {}, {}, 0, 0
    for pos, cmd in enumerate(commands):
        op = cmd["op"]
        if op in ("move_to", "line_to"):
            onmap[oi] = (pos, "x")
            oi += 1
        elif op == "quad_to":
            offmap[fi] = (pos, "x1")
            fi += 1
            onmap[oi] = (pos, "x")
            oi += 1
        elif op == "close":
            continue
        else:
            raise ValueError("unsupported-op")
    if oi != len(parsed["oncurve"]) or fi != len(parsed["offcurve"]):
        raise ValueError("index-mismatch")
    return onmap, offmap


def _certified_depth(raw_source_commands):
    # Hobby section 6 polygonal intermediates on exact binary64 input.
    # Deeper dyadic joints of arbitrary fontTools coordinates are not
    # exactly float-representable, so the published joint-exactness
    # demand fails there; depth-zero joints are the input coordinates
    # themselves and certify exactly without touching source curvature.
    for depth in (0,):
        try:
            cert = cc.certify_substitution(raw_source_commands, depth)
        except (ArithmeticError, OverflowError, ValueError):
            continue
        if cert.get("ok"):
            return depth, cert
    return None, {"ok": False, "reason": "uncertified-substitution"}


def _waist_on_chords(raw_parsed, raw_points, depth):
    # Shared crossing placement on the certified chord intermediate.
    built, _ = scf._substitute(raw_parsed, raw_points,
                               len(raw_parsed["oncurve"]), depth)
    if built is None:
        return None
    try:
        return jd._waist_from_slabs(parse_commands(built[0]))
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        return None


def _arm_of(normal):
    # Slope sign of the pair tangent orients the two crossing arms.
    tangent = np.array([-normal[1], normal[0]], float)
    if tangent[1] < 0:
        tangent = -tangent
    return "rising" if tangent[0] >= 0 else "falling"


def fit(raw_source_commands, captured_source_commands,
        original_upstream_commands, size_px, reference,
        native_axes=(False, False), topology_checker=None):
    """Joint curved-crossing correction; exact upstream on any gate failure."""
    if (not isinstance(native_axes, (tuple, list)) or len(native_axes) != 2
            or any(type(v) is not bool for v in native_axes)):
        return _abstain(original_upstream_commands, "malformed-native-axes")
    if native_axes[0]:
        return _abstain(original_upstream_commands, "native-X-owned")
    if not math.isfinite(size_px) or size_px <= 0:
        return _abstain(original_upstream_commands, "invalid-geometry-scale")
    try:
        if not check_correspondence(raw_source_commands,
                                    captured_source_commands):
            return _abstain(original_upstream_commands, "no-correspondence")
        if not check_correspondence(raw_source_commands,
                                    original_upstream_commands):
            return _abstain(original_upstream_commands, "no-correspondence")
        raw = parse_commands(raw_source_commands)
        fitted = parse_commands(original_upstream_commands)
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        return _abstain(original_upstream_commands, "malformed-commands")
    if (len(raw["oncurve"]) != len(fitted["oncurve"])
            or len(raw["offcurve"]) != len(fitted["offcurve"])):
        return _abstain(original_upstream_commands, "no-correspondence")
    raw_points = raw["oncurve"] + raw["offcurve"]
    up_points = fitted["oncurve"] + fitted["offcurve"]
    base = np.asarray(raw_points, float)
    up = np.asarray(up_points, float)
    if not np.isfinite(base).all() or not np.isfinite(up).all():
        return _abstain(original_upstream_commands, "malformed-commands")
    for pt in list(fitted["oncurve"]) + list(fitted["offcurve"]):
        if not (_on_grid(pt[0]) and _on_grid(pt[1])):
            return _abstain(original_upstream_commands, "non-26.6-input")
    try:
        captured = parse_commands(captured_source_commands)
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        return _abstain(original_upstream_commands, "malformed-commands")
    if (len(captured["oncurve"]) != len(raw["oncurve"])
            or len(captured["offcurve"]) != len(raw["offcurve"])):
        return _abstain(original_upstream_commands, "no-correspondence")
    cap_points = captured["oncurve"] + captured["offcurve"]
    cap = np.asarray(cap_points, float)
    for pt in cap_points:
        if not (_on_grid(pt[0]) and _on_grid(pt[1])):
            return _abstain(original_upstream_commands, "non-26.6-input")
    anchors = _anchors(reference)
    if anchors is None:
        return _abstain(original_upstream_commands, "no-reference-anchors")
    no = len(raw["oncurve"])
    raw_crosses = []
    for curve in cw.curves_of(raw):
        p0 = np.asarray(raw_points[curve["idx"][0]], float)
        pc = np.asarray(raw_points[curve["idx"][1]], float)
        p1 = np.asarray(raw_points[curve["idx"][2]], float)
        cross = float((pc - p0)[0] * (p1 - pc)[1]
                      - (pc - p0)[1] * (p1 - pc)[0])
        raw_crosses.append({"idx": list(curve["idx"]), "cross": cross})
        if cross == 0.0:
            return _abstain(original_upstream_commands,
                            "source-degenerate-curvature",
                            raw_crosses=raw_crosses)
    cap_crosses = []
    for curve, entry in zip(cw.curves_of(captured), raw_crosses):
        p0 = np.asarray(cap_points[curve["idx"][0]], float)
        pc = np.asarray(cap_points[curve["idx"][1]], float)
        p1 = np.asarray(cap_points[curve["idx"][2]], float)
        cap_crosses.append(float((pc - p0)[0] * (p1 - pc)[1]
                                 - (pc - p0)[1] * (p1 - pc)[0]))
    quantized_zero = [entry["idx"][1] for entry, cross in
                      zip(raw_crosses, cap_crosses)
                      if entry["cross"] != 0.0 and cross == 0.0]
    try:
        prepared, skipped = ad.recognize(raw_source_commands,
                                         original_upstream_commands,
                                         size_px, reference)
    except (KeyError, TypeError, AttributeError, ArithmeticError,
            ValueError):
        return _abstain(original_upstream_commands, "malformed-commands")
    if not prepared:
        return _abstain(original_upstream_commands, "no-attached-diagonals",
                        skipped=skipped,
                        quantized_zero_curves=quantized_zero)
    depth, cert = _certified_depth(raw_source_commands)
    if depth is None:
        return _abstain(original_upstream_commands,
                        "uncertified-substitution", certificate=cert,
                        quantized_zero_curves=quantized_zero)
    waist = _waist_on_chords(raw, raw_points, depth)
    if waist is None:
        return _abstain(original_upstream_commands, "no-waist",
                        skipped=skipped,
                        quantized_zero_curves=quantized_zero)
    # Hobby sections 3.2/3.5: the width contacts and reflected portions
    # must belong to the same crossing region. Both directions on both
    # sides of its waist distinguish four arms from a remote fork/hook.
    level = float(waist["level"])
    above, below = set(), set()
    for info in prepared:
        heights = [float(st["hit"][key][1]) for st in info["stations"]
                   for key in ("qa", "qb")]
        if all(h > level for h in heights):
            above.add(_arm_of(info["normal"]))
        elif all(h < level for h in heights):
            below.add(_arm_of(info["normal"]))
        else:
            return _abstain(original_upstream_commands,
                            "unsupported-crossing-class",
                            waist=waist, arms_above=sorted(above),
                            arms_below=sorted(below),
                            quantized_zero_curves=quantized_zero)
    if above != {"rising", "falling"} or below != {"rising", "falling"}:
        return _abstain(original_upstream_commands,
                        "unsupported-crossing-class",
                        waist=waist, arms_above=sorted(above),
                        arms_below=sorted(below),
                        quantized_zero_curves=quantized_zero)
    rel_med = float(statistics.median(a["rel"] for a in anchors))
    pair_mean = sum(sum(i["src_widths"]) / len(i["src_widths"])
                    for i in prepared) / len(prepared)
    predicted = waist["width"] * (1.0 + rel_med)
    if not predicted > 0:
        return _abstain(original_upstream_commands, "no-waist",
                        skipped=skipped)
    axis_src = float(waist["mid"])
    if jd.parity_target(axis_src, pair_mean * (1.0 + rel_med)) != \
            jd.parity_target(axis_src, predicted):
        return _abstain(original_upstream_commands, "parity-ambiguous",
                        skipped=skipped, waist=waist)
    target = jd.parity_target(axis_src, predicted)
    if target is None:
        return _abstain(original_upstream_commands, "parity-ambiguous",
                        skipped=skipped, waist=waist)
    sides = []
    for info in prepared:
        for side in (info["a"], info["b"]):
            sides.append({"pair": info["id"], "p0": tuple(side["p0"]),
                          "p1": tuple(side["p1"]), "i0": side["i0"],
                          "i1": side["i1"], "t0": side["t0"],
                          "t1": side["t1"]})
    matches = jd._match_borders(sides, axis_src, jd.EPS_PARITY)
    if not matches:
        return _abstain(original_upstream_commands, "no-symmetry-matches",
                        skipped=skipped, waist=waist,
                        quantized_zero_curves=quantized_zero)
    gaps = up - base
    gaps_flat = gaps.ravel()
    flat_up = up.ravel()
    try:
        weld = scf._weld_map(raw, raw_points)
        up_weld = scf._weld_map(fitted, up_points)
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        return _abstain(original_upstream_commands, "malformed-commands")
    if set(weld.items()) != set(up_weld.items()):
        return _abstain(original_upstream_commands, "weld-mismatch")
    for dup, canon in weld.items():
        if tuple(up[dup]) != tuple(up[canon]):
            return _abstain(original_upstream_commands, "weld-mismatch")
    involved = {v for info in prepared for edge in (info["a"], info["b"])
                for v in (edge["i0"], edge["i1"])}
    curves = cw.curves_of(raw)
    while True:
        grown = involved | {i for c in curves if set(c["idx"]) & involved
                            for i in c["idx"]}
        grown |= {weld.get(v, v) for v in tuple(grown)}
        if grown == involved:
            break
        involved = grown
    upright = {v for contour in raw["contours"] for seg in contour
               if seg[0] == "line" and base[seg[1], 0] == base[seg[2], 0]
               and base[seg[1], 1] != base[seg[2], 1]
               for v in (seg[1], seg[2])}
    upright |= {weld.get(v, v) for v in tuple(upright)}
    owned = tuple(i for i, on in enumerate(native_axes[:2]) if on)
    cols = sorted(v for v in involved if v not in upright and v not in weld)
    if not cols:
        return _abstain(original_upstream_commands, "no-free-controls")
    system = System([tuple(p) for p in raw_points], size_px)
    for curve in curves:
        if set(curve["idx"]) & involved:
            cw._add_quad_shape(system, list(curve["idx"]))
    for contour in raw["contours"]:
        for seg in contour:
            if seg[0] == "line" and {seg[1], seg[2]} & involved:
                try:
                    system.edge(seg[1], seg[2])
                except ValueError:
                    pass
    station_sets = []
    for info in prepared:
        station_pairs = []
        try:
            for st in info["stations"]:
                ta = info["a"]["t0"] + (info["a"]["t1"] - info["a"]["t0"]) \
                    * st["hit"]["sa"]
                tb = info["b"]["t0"] + (info["b"]["t1"] - info["b"]["t0"]) \
                    * st["hit"]["sb"]
                station_pairs.append(system.pair(
                    dd._affine_sample(info["a"], ta),
                    dd._affine_sample(info["b"], tb),
                    info["arc"], "ink", medial=st["hit"]["center"]))
        except ValueError:
            station_pairs = None
        station_sets.append(station_pairs)
    shape = []
    for group, row, const in system.rows:
        row = np.asarray(row, float)
        if group in ("curve-position", "curve-stretch", "curve-bend"):
            const = 0.0
        shape.append((row, float(const)))
    pairs_soft = []
    for info, station_pairs in zip(prepared, station_sets):
        if station_pairs is None:
            continue
        for pair, st in zip(station_pairs, info["stations"]):
            for anchor in anchors:
                tangent = np.asarray(pair.tangent, float)
                ref_t = np.asarray(anchor["tangent"], float)
                if float(np.dot(tangent, ref_t)) < 0:
                    tangent = -tangent
                psi = width_weight(pair.width, anchor["source_width"],
                                   tangent, ref_t, size_px)
                w = info["arc"] * anchor["length"] * psi
                scale = math.sqrt(w)
                pairs_soft.append((pair.error * scale,
                                   anchor["rel"] * scale))
    joints = []
    joint_hard = []
    for j, occurrences in scf._joints(raw, base, no).items():
        for occ in occurrences:
            iv = occ["prev"][1] if occ["prev"][0] == "line" \
                else no + occ["prev"][1]
            ov = occ["seg"][2] if occ["seg"][0] == "line" \
                else no + occ["seg"][1]
            if not {j, iv, ov} & involved:
                continue
            if occ["degenerate"]:
                return _abstain(original_upstream_commands,
                                "degenerate-joint")
            if not occ["smooth"]:
                joints.append((j, occ, iv, ov))
                continue
            grow, reason = scf._g1_row(up, j, occ["prev"], occ["seg"], no,
                                       size_px, occ["smooth"])
            if grow is None:
                return _abstain(original_upstream_commands, reason)
            row, constant, _ = grow
            joint_hard.append((np.asarray(row, float), float(constant)))
            joints.append((j, occ, iv, ov))

    def reduce_row(row):
        row = np.asarray(row, float).copy()
        for dup, canon in weld.items():
            row[2 * canon] += row[2 * dup]
        return row[[2 * v for v in cols]]
    soft_gap = [(np.asarray(r, float), float(c)) for r, c in pairs_soft]
    soft_plain = [(np.asarray(r, float), float(c)) for r, c in shape]
    sym = jd._symmetry_rows(system, matches, axis_src, 2.0 * target, size_px)
    if not sym:
        return _abstain(original_upstream_commands, "phase-unconstrained",
                        skipped=skipped, waist=waist)
    for r, c in sym:
        soft_gap.append((np.asarray(r, float), float(c)))
    mat = np.stack([reduce_row(r) for r, _ in soft_gap + soft_plain])
    rhs = np.array([-float(r @ gaps_flat) - c for r, c in soft_gap]
                   + [-c for _, c in soft_plain], float)
    joint = [(np.asarray(r, float), float(c)) for r, c in joint_hard]
    hard = [(r, -c) for r, c in joint]
    mismatch = 0.0
    for first, second, _ in matches:
        mid = sum(base[side[key], 0]
                  for side in (first, second) for key in ("i0", "i1")) / 4.0
        mismatch += mid - axis_src
    mismatch /= len(matches)
    ge = np.stack([reduce_row(r) for r, _ in hard]) if hard \
        else np.zeros((0, len(cols)))
    he = np.array([c for _, c in hard], float) if hard \
        else np.zeros(0)
    keep = np.linalg.norm(ge, axis=1) > 0 if len(he) else np.zeros(0, bool)
    if np.any(np.abs(he[~keep])) > 1e-9 if len(he) else False:
        return _abstain(original_upstream_commands,
                        "fixed-constraints-incompatible")
    inequalities = []
    for curve in curves:
        if not set(curve["idx"]) & involved:
            continue
        p0, ctrl, p1 = curve["idx"]
        su = base[ctrl] - base[p0]
        sv = base[p1] - base[ctrl]
        source_cross = su[0] * sv[1] - su[1] * sv[0]
        if source_cross == 0:
            return _abstain(original_upstream_commands,
                            "source-degenerate-curvature")
        row = np.zeros(2 * len(base))
        row[2 * p0] = up[ctrl, 1] - up[p1, 1]
        row[2 * ctrl] = up[p1, 1] - up[p0, 1]
        row[2 * p1] = up[p0, 1] - up[ctrl, 1]
        row *= 1 if source_cross > 0 else -1
        reserve = sum(abs(reduce_row(row))) * RESERVE_26_6 + CROSS_QUANTUM
        inequalities.append((reduce_row(row),
                             reserve - float(row @ flat_up)))
        for i, j in ((p0, ctrl), (ctrl, p1)):
            for leg in (su, sv):
                leg_row = np.zeros(2 * len(base))
                leg_row[2 * j], leg_row[2 * i] = leg[0], -leg[0]
                value = float(np.dot(up[j] - up[i], leg))
                leg_reserve = sum(abs(reduce_row(leg_row))) \
                    * RESERVE_26_6 + CROSS_QUANTUM
                inequalities.append((reduce_row(leg_row),
                                     leg_reserve - value))
    for j, occ, iv, ov in joints:
        if occ["smooth"]:
            continue
        s_cross, _, _ = scf._cross_of(base, j, occ["prev"], occ["seg"], no)
        one = no + occ["prev"][1] if occ["prev"][0] == "quad" \
            else occ["prev"][1]
        other = no + occ["seg"][1] if occ["seg"][0] == "quad" \
            else occ["seg"][2]
        if s_cross != 0:
            s = 1 if s_cross > 0 else -1
            yi, yj, yo = up[one, 1], up[j, 1], up[other, 1]
            grow = np.zeros(2 * len(base))
            grow[2 * one] = -(yo - yj) * s
            grow[2 * j] = (yo - yi) * s
            grow[2 * other] = -(yj - yi) * s
            here = up[j] - up[one]
            there = up[other] - up[j]
            value = s * (here[0] * there[1] - here[1] * there[0])
            reserve = sum(abs(reduce_row(grow))) * RESERVE_26_6 \
                + CROSS_QUANTUM
            inequalities.append((reduce_row(grow), reserve - value))
        if occ["prev"][0] == "line":
            src_leg = base[j] - base[iv]
            leg_row = np.zeros(2 * len(base))
            leg_row[2 * j] = src_leg[0]
            leg_row[2 * iv] = -src_leg[0]
            value = float(np.dot(up[j] - up[iv], src_leg))
            reserve = sum(abs(reduce_row(leg_row))) * RESERVE_26_6 \
                + CROSS_QUANTUM
            inequalities.append((reduce_row(leg_row), reserve - value))
        if occ["seg"][0] == "line":
            src_leg = base[ov] - base[j]
            leg_row = np.zeros(2 * len(base))
            leg_row[2 * ov] = src_leg[0]
            leg_row[2 * j] = -src_leg[0]
            value = float(np.dot(up[ov] - up[j], src_leg))
            reserve = sum(abs(reduce_row(leg_row))) * RESERVE_26_6 \
                + CROSS_QUANTUM
            inequalities.append((reduce_row(leg_row), reserve - value))
    if not inequalities:
        return _abstain(original_upstream_commands, "no-curve-constraints")
    cmat = np.stack([r for r, _ in inequalities])
    clower = np.array([v for _, v in inequalities], float)
    radius = min(min(i["src_widths"]) / 2.0 for i in prepared)
    bound = radius - HEADROOM
    if not bound > 0:
        return _abstain(original_upstream_commands, "movement-budget-empty",
                        skipped=skipped, waist=waist)
    solved = ad._convex_qp(mat, rhs, ge[keep], he[keep], cmat, clower,
                           bound)
    if solved is None:
        try:
            eq_sol, _, eq_rank, _ = np.linalg.lstsq(
                ge[keep], he[keep], rcond=None)
            eq_resid = ge[keep] @ eq_sol - he[keep] if len(he[keep]) else []
            eq_peak = float(np.abs(eq_sol).max(initial=0))
        except (ValueError, ArithmeticError):
            eq_rank, eq_resid, eq_peak = None, None, None
        return _abstain(original_upstream_commands,
                        "constraints-incompatible", skipped=skipped,
                        waist=waist, parity_target=target,
                        matches=len(matches),
                        n_hard=int(len(he)), n_bound=int(len(cols)),
                        bound=float(bound), radius=float(radius),
                        eq_rank=eq_rank,
                        eq_resid=[float(v) for v in eq_resid]
                        if eq_resid is not None else None,
                        eq_peak=eq_peak,
                        quantized_zero_curves=quantized_zero,
                        size_px=size_px)
    delta, qp = solved
    raw_new = up.copy()
    for v, step in zip(cols, delta):
        raw_new[v, 0] += float(step)
    for dup, canon in weld.items():
        raw_new[dup] = raw_new[canon]
    cand = raw_new.copy()
    for v in cols:
        cand[v, 0] = scf._round_26_6(float(cand[v, 0]))
    for dup, canon in weld.items():
        cand[dup] = cand[canon]
    if float(np.max(np.linalg.norm(cand - up, axis=1), initial=0)) > radius:
        return _abstain(original_upstream_commands,
                        "rounded-movement-budget")
    hard_checks = []
    col_x = [2 * v for v in cols]
    d_raw = (raw_new - up).ravel()[col_x]
    d_cand = (cand - up).ravel()[col_x]
    for (row, _), target_h in zip(hard, he):
        red = reduce_row(row)
        raw_error = abs(float(red @ d_raw - target_h))
        error = abs(float(red @ d_cand - target_h))
        allowance = sum(abs(red[i]) * RESERVE_26_6 for i, v in enumerate(cols)
                        if raw_new[v, 0] != up[v, 0])
        norm = float(np.linalg.norm(red))
        ok = raw_error <= 1e-7 * (1 + abs(target_h)) * (1 + norm) \
            and error <= allowance + 1e-9
        hard_checks.append({"raw_error": raw_error, "rounded_error": error,
                            "allowance": allowance, "ok": bool(ok)})
        if not ok:
            return _abstain(original_upstream_commands,
                            "rounded-hard-constraint",
                            hard_checks=hard_checks)
    continuity = []
    for j, occ, iv, ov in joints:
        raw_cross, _, _ = scf._cross_of(raw_new, j, occ["prev"],
                                        occ["seg"], no)
        old_cross, li_u, lo_u = scf._cross_of(up, j, occ["prev"],
                                              occ["seg"], no)
        cross, li_c, lo_c = scf._cross_of(cand, j, occ["prev"],
                                          occ["seg"], no)
        source_cross, _, _ = scf._cross_of(base, j, occ["prev"],
                                           occ["seg"], no)
        target_cross = 0.0 if occ["smooth"] else old_cross
        moved = tuple((tuple(raw_new[v]) != tuple(up[v]), False)
                      for v in (iv, j, ov))
        allowance = scf._quant_cross_bound(li_u, lo_u, moved)
        ok = bool(np.linalg.norm(li_c) > 0 and np.linalg.norm(lo_c) > 0)
        if occ["smooth"]:
            ok &= abs(raw_cross - target_cross) <= 1e-8 * \
                (1 + abs(target_cross))
            ok &= abs(cross - target_cross) <= allowance + 1e-9
            ok &= bool(float(np.dot(li_c, lo_c)) > 0)
        elif source_cross:
            ok &= bool(cross * source_cross > 0)
        else:
            ok = False
        continuity.append({"joint": int(j), "smooth": bool(occ["smooth"]),
                           "cross_src": float(source_cross),
                           "cross_up": float(old_cross),
                           "cross_cand": float(cross),
                           "allowed": float(allowance), "ok": bool(ok)})
        if not ok:
            return _abstain(original_upstream_commands, "joint-continuity",
                            continuity=continuity)
    moved = {i for i in range(len(base)) if tuple(cand[i]) != tuple(up[i])}
    for curve in curves:
        src_ctrls = [tuple(base[i]) for i in curve["idx"]]
        new_ctrls = [tuple(cand[i]) for i in curve["idx"]]
        ok, why = cw._quad_interval_ok(src_ctrls, new_ctrls)
        if not ok:
            return _abstain(original_upstream_commands, "curve-" + why,
                            curve_indices=curve["idx"],
                            source_controls=src_ctrls,
                            candidate_controls=new_ctrls)
    clear, why = scf._clearance_ok([], cand, raw, moved, up, set())
    if not clear:
        return _abstain(original_upstream_commands, "clearance-" + why)
    if any(cand[v][1] != up[v][1] for v in range(len(base))):
        return _abstain(original_upstream_commands, "y-changed")
    if max(c[1] for c in cand) != max(c[1] for c in up):
        return _abstain(original_upstream_commands, "cap-changed")
    try:
        onmap, offmap = _command_index(original_upstream_commands, fitted)
    except ValueError:
        return _abstain(original_upstream_commands, "malformed-commands")
    candidate = [dict(cmd) for cmd in original_upstream_commands]
    for v in sorted(set(cols) | set(weld)):
        src = weld.get(v, v)
        if src not in cols:
            continue
        new_x = float(cand[src, 0])
        if v < no:
            pos, key = onmap[v]
        else:
            pos, key = offmap[v - no]
        if new_x != float(up[v, 0]):
            candidate[pos][key] = new_x
            candidate[pos][key + "_bits"] = dd._f32bits(new_x)
    if dd._commands_equal(candidate, original_upstream_commands):
        return _abstain(original_upstream_commands, "no-movement",
                        skipped=skipped, waist=waist)
    gate_raw = cw._substitution_gate(raw_source_commands,
                                     original_upstream_commands, candidate)
    if not gate_raw.get("ok"):
        return _abstain(original_upstream_commands, "topology",
                        topology=gate_raw.get("verdict"))
    gate_cap = cw._substitution_gate(captured_source_commands,
                                     original_upstream_commands, candidate)
    if not gate_cap.get("ok"):
        return _abstain(original_upstream_commands, "topology-captured",
                        topology=gate_cap.get("verdict"))
    if topology_checker is not None:
        for label, source_cmds in (("raw", raw_source_commands),
                                   ("captured", captured_source_commands)):
            try:
                report = topology_checker(source_cmds,
                                          original_upstream_commands,
                                          candidate)
            except Exception as exc:
                return _abstain(original_upstream_commands,
                                "checker-exception", error=str(exc))
            if not isinstance(report, dict) or report.get("ok") is not True:
                return _abstain(original_upstream_commands,
                                "checker-rejected", source=label,
                                report=report)
    cand_on = parse_commands(candidate)["oncurve"]
    pairs = []
    for info in prepared:
        normal = info["normal"]
        src, ups, got = [], [], []
        for k, st in enumerate(info["stations"]):
            sa, sb = st["hit"]["sa"], st["hit"]["sb"]
            qa = dd._edge_point(info["a"], sa, cand_on)
            qb = dd._edge_point(info["b"], sb, cand_on)
            got.append(abs((qb[0] - qa[0]) * normal[0]
                           + (qb[1] - qa[1]) * normal[1]))
            src.append(info["src_widths"][k])
            ups.append(info["fit_widths"][k])
        arm = _arm_of(info["normal"])
        pairs.append({"id": info["id"], "arm": arm,
                      "source_width": sum(src) / len(src),
                      "upstream_width": sum(ups) / len(ups),
                      "candidate_width": sum(got) / len(got)})
    arms = {}
    for arm in ("rising", "falling"):
        group = [p for p in pairs if p["arm"] == arm]
        if group:
            arms[arm] = {
                "source": sum(p["source_width"] for p in group)
                / len(group),
                "candidate": sum(p["candidate_width"] for p in group)
                / len(group)}
    movement = max((math.dist(tuple(up[v]), tuple(cand[v]))
                    for v in range(len(base))), default=0.0)
    phase_cand = sum(sum(cand[side[key], 0]
                         for side in (first, second)
                         for key in ("i0", "i1")) / 4.0
                     for first, second, _ in matches) / len(matches)
    phase_up = sum(sum(up[side[key], 0]
                       for side in (first, second)
                       for key in ("i0", "i1")) / 4.0
                   for first, second, _ in matches) / len(matches)
    return {"candidate_commands": candidate, "applied": True,
            "reason": "applied-curved-crossing",
            "pairs": pairs, "arms": arms, "skipped": skipped,
            "diagnostics": {"waist": waist, "parity_target": target,
                            "rel_median": rel_med,
                            "quantized_zero_curves": quantized_zero,
                            "raw_crosses": raw_crosses, "qp": qp,
                            "matches": len(matches),
                            "phase_mid_cand": float(phase_cand),
                            "phase_mid_up": float(phase_up),
                            "phase_residual": float(
                                phase_cand - (target + mismatch)),
                            "certificate": cert},
            "movement": movement, "bound": bound, "radius": radius,
            "hard_checks": hard_checks, "continuity": continuity,
            "size_px": size_px}
