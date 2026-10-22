"""General curved-stroke width prototype (Hobby section 6).

Recognition uses polygonal intermediates for the Voronoi/medial stage only;
final outlines stay quadratic Bezier (Hobby section 6). A certified
substitution bounds the intermediate error; medial samples map back to actual
quadratic controls, and the pair uses the true mapped disk with its mapping
deviation recorded. Every remaining true primitive clears the mapped disk
under the exact quartic Bernstein predicate.

Continuity rows live inside the solve: the G1 cross determinant linearized
with frozen upstream coefficients (Hobby linearity requirement, audit of
(33)) drives smooth joints toward shared tangents while permitting common
rotation; kinked joints keep their upstream defect within a quantization
bound instead of exact direction pins.
"""

from fractions import Fraction
import math
import struct
from functools import lru_cache
from types import SimpleNamespace

import numpy as np

from experiments.hobby_fitting import curve_clearance as cc
from experiments.hobby_fitting import curve_contacts as kc
from experiments.hobby_fitting import curved_width as cw
from experiments.hobby_fitting import exact_topology as topology
from experiments.hobby_fitting.prototype import Sample, System, width_weight
from experiments.hobby_fitting import intervals
from experiments.hobby_fitting.real_outline import (
    check_correspondence,
    loops_parsed,
    parse_commands,
)

HEADROOM = math.sqrt(2.0) / 128.0
DEPTHS = (2, 3, 4)
QUANT = 1.0 / 64.0
ROUND_HALF = 1.0 / 128.0


def _round_26_6(x):
    """Nearest 1/64 unit, ties toward positive infinity (scanner convention)."""
    return math.floor(x * 64 + 0.5) / 64


def _f32bits(x):
    return struct.unpack(">I", struct.pack(">f", x))[0]


def _valid_axes(native_axes):
    try:
        return (len(native_axes) == 2
                and all(type(v) is bool for v in native_axes))
    except TypeError:
        return False


def _eval_quad(ctrls, t):
    mt = 1.0 - t
    return (mt * mt * ctrls[0][0] + 2 * mt * t * ctrls[1][0] + t * t * ctrls[2][0],
            mt * mt * ctrls[0][1] + 2 * mt * t * ctrls[1][1] + t * t * ctrls[2][1])


def _quad_sample(ctrl, t):
    # Quadratic Bernstein correspondence; Hobby (31) is cubic-only in the
    # shared API, the degree-two basis is the same fixed-affine construction.
    if len(ctrl) != 3 or not 0 <= t <= 1:
        raise ValueError("quad sample needs three controls and t in [0,1]")
    return Sample(tuple(zip([int(v) for v in ctrl],
                            ((1 - t) ** 2, 2 * t * (1 - t), t * t))))


def _piece_eps(piece):
    # Parameter-matched quad deviation Q(t)-chord(t) = t(1-t)(2C-P0-P1)
    # peaks at t=1/2: norm(P0-2C+P1)/4.
    p0, c, p1 = piece
    dx = p0[0] - 2 * c[0] + p1[0]
    dy = p0[1] - 2 * c[1] + p1[1]
    return math.hypot(float(dx), float(dy)) / 4


def _substitute(parsed, points, no, depth):
    """Line-only commands plus explicit per-edge (seg, t0, t1) provenance.

    Joints are dyadic points of the true curves; the substitution
    certificate is checked separately by the caller. Every emitted edge,
    including each curve's first piece, carries its own source interval;
    the closing edge carries none and stays a competitor only.
    """
    cmds, edge_list = [], []
    for ci, contour in enumerate(parsed["contours"]):
        pen, pen_idx, start_idx = None, None, None
        for si, seg in enumerate(contour):
            if seg[0] == "line":
                seq = [tuple(points[seg[1]]), tuple(points[seg[2]])]
                key = ("line", ci, si)
                seq_t = [0.0, 1.0]
            elif seg[0] == "quad":
                ctrls = [tuple(points[i]) for i in (seg[2], no + seg[1], seg[3])]
                chains = cc.piece_chains(list(ctrls), depth)
                joints = [chains[0][0]] + [ch[-1] for ch in chains]
                seq = [(float(j[0]), float(j[1])) for j in joints]
                key = ("quad", ci, si,
                       tuple(int(v) for v in (seg[2], no + seg[1], seg[3])))
                n = len(chains)
                seq_t = [k / n for k in range(n + 1)]
            else:
                return None, "cubic-curve-present"
            last_t = seq_t[0]
            for k, pt in enumerate(seq):
                fpt = (float(pt[0]), float(pt[1]))
                if pen is not None and fpt == pen:
                    continue
                idx = sum(1 for c in cmds if c["op"] in ("move_to", "line_to"))
                if pen is None:
                    cmds.append({"op": "move_to", "x": fpt[0], "y": fpt[1]})
                    start_idx = idx
                else:
                    cmds.append({"op": "line_to", "x": fpt[0], "y": fpt[1]})
                    edge_list.append({"v0": pen_idx, "v1": idx, "key": key,
                                      "t0": last_t, "t1": seq_t[k]})
                last_t = seq_t[k]
                pen, pen_idx = fpt, idx
        cmds.append({"op": "close"})
        edge_list.append({"v0": pen_idx, "v1": start_idx, "key": None,
                          "t0": None, "t1": None})
    return (cmds, edge_list), None


def _true_disk_clear(mfr, r2, parsed, points, no, skip=()):
    """Exact disk clearance against true primitives, failing closed.

    The polygonal certificate alone cannot prove the true-curve disk
    empty; each quad runs the exact quartic Bernstein clearance and each
    line the exact segment clearance. Skipped control sets (paired curves
    in the margin check) stay an explicit approximation.
    """
    own = {tuple(sorted(s)) for s in skip}
    for contour in parsed["contours"]:
        for seg in contour:
            if seg[0] == "quad":
                ctrl = [seg[2], no + seg[1], seg[3]]
                if tuple(sorted(ctrl)) in own:
                    continue
                ctrls = tuple((Fraction(points[i][0]), Fraction(points[i][1]))
                                for i in ctrl)
                if not kc._quad_disk_clear(mfr, r2, ctrls):
                    return False, "curve-contact"
            elif seg[0] == "line":
                a = (Fraction(points[seg[1]][0]), Fraction(points[seg[1]][1]))
                b = (Fraction(points[seg[2]][0]), Fraction(points[seg[2]][1]))
                if not kc._seg_clear(mfr, r2, a, b):
                    return False, "line-contact"
    return True, "clear"


def _box_gap(a, b):
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def recognize(source_commands, depths=DEPTHS, size_px=None):
    """Certified-intermediate curved contacts beyond axis extrema.

    Pairing runs per source-curve pair over the polygonal intermediate;
    every pair keeps its longest-span dominance-interval midpoint (the
    section-3.2 representative), so shared movement is solved jointly
    instead of pruned. Distant seg pairs beyond size_px/4 skip as a work
    bound only.
    """
    diag = {"candidates": 0, "rejected": {}, "depths_tried": []}
    try:
        parsed = parse_commands(source_commands)
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        diag["rejected"]["malformed-commands"] = 1
        return [], diag
    if len(parsed["contours"]) != 1:
        diag["rejected"]["multi-contour-unsupported"] = 1
        return [], diag
    for contour in parsed["contours"]:
        for seg in contour:
            if seg[0] not in ("line", "quad"):
                diag["rejected"]["cubic-curve-present"] = 1
                return [], diag
    points = parsed["oncurve"] + parsed["offcurve"]
    no = len(parsed["oncurve"])
    chosen = None
    for depth in depths:
        diag["depths_tried"].append(depth)
        try:
            cert = cc.certify_substitution(source_commands, depth)
        except (ArithmeticError, OverflowError, ValueError):
            continue
        if cert.get("ok"):
            chosen = depth
            break
    if chosen is None:
        diag["rejected"]["uncertified-substitution"] = 1
        return [], diag
    diag["depth"] = chosen
    built, why = _substitute(parsed, points, no, chosen)
    if built is None:
        diag["rejected"][why or "substitution-failed"] = 1
        return [], diag
    cmds, edge_list = built
    try:
        poly = parse_commands(cmds)
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        diag["rejected"]["malformed-substitution"] = 1
        return [], diag
    oc = poly["oncurve"]
    if len(oc) != sum(1 for c in cmds if c["op"] in ("move_to", "line_to")):
        diag["rejected"]["provenance-mismatch"] = 1
        return [], diag
    eps_global = 0.0
    for contour in parsed["contours"]:
        for seg in contour:
            if seg[0] == "quad":
                ctrls = [tuple(points[i]) for i in
                         (seg[2], no + seg[1], seg[3])]
                fr = [(Fraction(c[0]), Fraction(c[1])) for c in ctrls]
                for piece in _dyadic(fr, chosen):
                    eps_global = max(eps_global, float(_piece_eps(piece)))
    diag["eps_global"] = eps_global
    by_seg = {}
    for e, entry in enumerate(edge_list):
        if entry["key"] is not None and entry["key"][0] == "quad":
            by_seg.setdefault(entry["key"], []).append(e)
    loops = loops_parsed(poly)
    if loops is None:
        diag["rejected"]["no-winding-loops"] = 1
        return [], diag
    boxes = {}
    for key, edges in by_seg.items():
        xs, ys = [], []
        for e in edges:
            for v in (edge_list[e]["v0"], edge_list[e]["v1"]):
                xs.append(oc[v][0])
                ys.append(oc[v][1])
        boxes[key] = (min(xs), min(ys), max(xs), max(ys))
    cap = size_px / 4 if size_px else float("inf")
    seg_keys = sorted(by_seg, key=lambda k: (k[1], k[2]))
    flat = [None] * len(edge_list)
    for e, entry in enumerate(edge_list):
        flat[e] = {"seg": (tuple(oc[entry["v0"]]), tuple(oc[entry["v1"]])),
                   "tag": "e(%d)" % e}
    diag["poly_edges"] = sum(1 for entry in edge_list
                             if entry["key"] is not None)
    pairs = []
    for i in range(len(seg_keys)):
        for j in range(i + 1, len(seg_keys)):
            ka, kb = seg_keys[i], seg_keys[j]
            if _box_gap(boxes[ka], boxes[kb]) > cap:
                diag["rejected"]["work-bound-skip"] = \
                    diag["rejected"].get("work-bound-skip", 0) + 1
                continue
            diag["candidates"] += 1
            best = None
            for ea in by_seg[ka]:
                seg_a = flat[ea]["seg"]
                for eb in by_seg[kb]:
                    seg_b = flat[eb]["seg"]
                    others = [entry for f, entry in enumerate(flat)
                              if f not in (ea, eb)]
                    try:
                        dom = intervals.dominance(seg_a, seg_b, others, loops)
                    except (ArithmeticError, ValueError):
                        continue
                    if dom["status"] != "ok" or not dom["intervals"]:
                        continue
                    span = max(dom["intervals"],
                               key=lambda s: s["hi"] - s["lo"])
                    speed = dom.get("speed") or 0.0
                    width = (span["hi"] - span["lo"]) * speed
                    if best is None or (span["hi"] - span["lo"]
                                        > best[0]["hi"] - best[0]["lo"]):
                        best = (span, seg_a, seg_b, ea, eb, width)
            if best is None:
                diag["rejected"]["no-interval"] = \
                    diag["rejected"].get("no-interval", 0) + 1
                continue
            span, seg_a, seg_b, ea, eb, arc = best
            mid = (span["lo"] + span["hi"]) / 2
            others = [entry for f, entry in enumerate(flat)
                      if f not in (ea, eb)]
            try:
                out = intervals.contact(seg_a, seg_b, mid, others, loops)
            except (ArithmeticError, ValueError):
                diag["rejected"]["contact-error"] = \
                    diag["rejected"].get("contact-error", 0) + 1
                continue
            hit = out["hit"]
            if hit is None:
                diag["rejected"]["contact-failed"] = \
                    diag["rejected"].get("contact-failed", 0) + 1
                continue
            ta = edge_list[ea]["t0"] + hit["sa"] * (
                edge_list[ea]["t1"] - edge_list[ea]["t0"])
            tb = edge_list[eb]["t0"] + hit["sb"] * (
                edge_list[eb]["t1"] - edge_list[eb]["t0"])
            actrl = list(ka[3])
            bctrl = list(kb[3])
            fa = [tuple(points[i]) for i in actrl]
            fb = [tuple(points[i]) for i in bctrl]
            w_poly = float(hit["width"])
            chord = (hit["qa"][0] - hit["qb"][0],
                     hit["qa"][1] - hit["qb"][1])
            dist = math.hypot(*chord)
            if dist <= 0:
                diag["rejected"]["coincident"] = \
                    diag["rejected"].get("coincident", 0) + 1
                continue
            n = [chord[0] / dist, chord[1] / dist]
            m = hit["center"]
            qa = np.asarray(_eval_quad(fa, ta))
            qb = np.asarray(_eval_quad(fb, tb))
            mc = np.asarray(m, float)
            ra = float(np.linalg.norm(qa - mc))
            rb = float(np.linalg.norm(qb - mc))
            shell = 2.0 * eps_global
            if not (abs(ra - w_poly / 2) <= shell
                    and abs(rb - w_poly / 2) <= shell):
                diag["rejected"]["approx-diverged"] = \
                    diag["rejected"].get("approx-diverged", 0) + 1
                continue
            if not w_poly / 2 > shell:
                diag["rejected"]["approx-too-coarse"] = \
                    diag["rejected"].get("approx-too-coarse", 0) + 1
                continue
            if not arc > 0:
                diag["rejected"]["degenerate-arc"] = \
                    diag["rejected"].get("degenerate-arc", 0) + 1
                continue
            mfr = (Fraction(m[0]), Fraction(m[1]))
            rshrink = (Fraction(w_poly) / 2 - Fraction(shell)) ** 2
            clear, why = _true_disk_clear(
                mfr, rshrink, parsed, points, no)
            if not clear:
                diag["rejected"][why] = \
                    diag["rejected"].get(why, 0) + 1
                continue
            # Hobby §6 correspondence carries the full approximation
            # shell. Third boundaries must clear its upper radius before
            # this pair can own the feature; movement uses the lower one.
            rmargin = (Fraction(w_poly) / 2 + Fraction(shell)) ** 2
            clear, why = _true_disk_clear(
                mfr, rmargin, parsed, points, no,
                skip=(actrl, bctrl))
            if not clear:
                diag["rejected"]["third-boundary-tight"] = \
                    diag["rejected"].get("third-boundary-tight", 0) + 1
                continue
            bound = 2.0 * shell
            pairs.append({"a_ctrl": actrl, "b_ctrl": bctrl,
                          "a_t": float(ta), "b_t": float(tb),
                          "medial": [float(m[0]), float(m[1])],
                          "normal": [float(n[0]), float(n[1])],
                          "width_2r": float(w_poly),
                          "radii": [float(ra), float(rb)],
                          "approx_bound": float(bound),
                          "arc": float(arc),
                          "shape_ctrl": [actrl, bctrl]})
    return pairs, diag


def _dyadic(ctrls, depth):
    pieces = [list(ctrls)]
    for _ in range(depth):
        halves = []
        for piece in pieces:
            level = [list(p) for p in piece]
            left, right = [level[0]], [level[-1]]
            while len(level) > 1:
                level = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                         for a, b in zip(level, level[1:])]
                left.append(level[0])
                right.append(level[-1])
            halves.append(left)
            halves.append(list(reversed(right)))
        pieces = halves
    return pieces


def _seg_end(seg):
    return seg[3] if seg[0] == "quad" else seg[2]


def _seg_start(seg):
    return seg[2] if seg[0] == "quad" else seg[1]


def _zero_seg(seg, points, no):
    if seg[0] == "line":
        return tuple(points[seg[1]]) == tuple(points[seg[2]])
    ctrls = [tuple(points[i]) for i in (seg[2], no + seg[1], seg[3])]
    return ctrls[0] == ctrls[1] == ctrls[2]


def _weld_map(parsed, points):
    """Duplicate-endpoint alias pairs from closure encoding.

    parse_commands materializes a closing line when the last endpoint
    index differs from the first; when that edge is zero-length its start
    vertex duplicates the contour start coordinates. That alias is an
    encoding artifact, not zero-tangent geometry.
    """
    weld = {}
    for contour in parsed["contours"]:
        segs = [s for s in contour if s[0] in ("line", "quad")]
        if not segs:
            continue
        first = _seg_start(segs[0])
        last = segs[-1]
        if (last[0] == "line" and _seg_end(last) == first
                and tuple(points[_seg_start(last)])
                == tuple(points[first])
                and _seg_start(last) != first):
            weld[_seg_start(last)] = first
    return weld


def _joints(parsed, points, no):
    """Joint legs in exact arithmetic; smooth needs cross 0, forward dot.

    The predecessor wraps only on geometrically closed contours; open
    ends carry no joint entry. Zero-length closure aliases are filtered
    from logical joins; genuine internal zero legs stay classified.
    """
    out = {}
    for contour in parsed["contours"]:
        segs = [s for s in contour if s[0] in ("line", "quad")]
        if not segs:
            continue
        closed = _seg_end(segs[-1]) == _seg_start(segs[0])
        logical = segs
        if (closed and segs[-1][0] == "line"
                and _zero_seg(segs[-1], points, no)
                and _seg_end(segs[-1]) == _seg_start(segs[0])):
            logical = segs[:-1]
        if not logical:
            continue
        for k, seg in enumerate(logical):
            if k == 0 and not closed:
                continue
            prev = logical[k - 1]
            j = seg[2] if seg[0] == "quad" else seg[1]
            J = (Fraction(points[j][0]), Fraction(points[j][1]))

            def leg(s, at_joint):
                if s[0] == "quad":
                    c = points[no + s[1]]
                    f = (Fraction(c[0]), Fraction(c[1]))
                else:
                    e = points[s[2] if at_joint == "out" else s[1]]
                    f = (Fraction(e[0]), Fraction(e[1]))
                if at_joint == "out":
                    return (f[0] - J[0], f[1] - J[1])
                return (J[0] - f[0], J[1] - f[1])

            lin, lout = leg(prev, "in"), leg(seg, "out")
            degenerate = not ((lin[0] or lin[1]) and (lout[0] or lout[1]))
            smooth = bool(not degenerate
                          and lin[0] * lout[1] == lin[1] * lout[0]
                          and lin[0] * lout[0] + lin[1] * lout[1] > 0)
            out.setdefault(j, []).append(
                {"prev": prev, "seg": seg, "smooth": smooth,
                 "degenerate": degenerate,
                 "cross": lin[0] * lout[1] - lin[1] * lout[0]})
    return out


def _g1_row(upstream, j, prev, seg, no, size_px, smooth):
    """Linearized joint-cross row with frozen upstream coefficients.

    cross(J-I, O-J) linearized at the upstream fit keeps every residual
    linear in control points (Hobby linearity requirement). Smooth joints
    target zero shared-tangent cross, permitting common rotation; other
    joints target the upstream defect, preserving it instead of smoothing.
    """
    up = [tuple(u) for u in upstream]

    def pt(v):
        return up[v]

    J = np.asarray(pt(j), float)
    if prev[0] == "quad":
        I = np.asarray(pt(no + prev[1]), float)
    else:
        I = np.asarray(pt(prev[1]), float)
    if seg[0] == "quad":
        O = np.asarray(pt(no + seg[1]), float)
    else:
        O = np.asarray(pt(seg[2]), float)
    li, lo = J - I, O - J
    ni, no_ = (float(np.linalg.norm(li)), float(np.linalg.norm(lo)))
    cross_up = float(li[0] * lo[1] - li[1] * lo[0])
    if ni <= 0 or no_ <= 0:
        return None, "degenerate-leg"
    row = np.zeros(2 * len(up))
    dJ = np.array([lo[1] + li[1], -(li[0] + lo[0])])
    dI = np.array([-lo[1], lo[0]])
    dO = np.array([-li[1], li[0]])
    iv = prev[1] if prev[0] == "line" else no + prev[1]
    ov = seg[2] if seg[0] == "line" else no + seg[1]
    row[2 * j:2 * j + 2] = dJ
    row[2 * iv:2 * iv + 2] = dI
    row[2 * ov:2 * ov + 2] = dO
    arc = (ni + no_) / 2
    scale = math.sqrt(25 / size_px * arc) / (ni * no_)
    const = cross_up if smooth else 0.0
    return (row * scale, const * scale, {"cross_up": cross_up,
                                 "leg_in": ni, "leg_out": no_}), None


def _quant_cross_bound(leg_in, leg_out, moved):
    """26.6 rounding bound on joint-cross perturbation.

    Only moved coordinates err, at most 1/128 per axis; unmoved legs
    contribute zero. The bilinear cross gains first-order leg-error
    terms plus the second-order product.
    """
    (imx, imy), (jmx, jmy), (omx, omy) = moved
    ein_x = (ROUND_HALF if imx else 0.0) + (ROUND_HALF if jmx else 0.0)
    ein_y = (ROUND_HALF if imy else 0.0) + (ROUND_HALF if jmy else 0.0)
    eout_x = (ROUND_HALF if jmx else 0.0) + (ROUND_HALF if omx else 0.0)
    eout_y = (ROUND_HALF if jmy else 0.0) + (ROUND_HALF if omy else 0.0)
    ax, ay = abs(leg_in[0]), abs(leg_in[1])
    bx, by = abs(leg_out[0]), abs(leg_out[1])
    return (ein_x * by + ein_y * bx + eout_x * ay + eout_y * ax
            + ein_x * eout_y + ein_y * eout_x)


def _scale_to_bound(sol, cols, bound):
    """Clip the peak Euclidean control displacement to the movement bound.

    Both free axes of one control count together; a diagonal move peaks at
    its hypotenuse, not its largest coordinate.
    """
    acc = {}
    for (v, axis), d in zip(cols, sol):
        acc[v] = acc.get(v, 0.0) + float(d) ** 2
    peak = math.sqrt(max(acc.values(), default=0.0))
    if peak > bound:
        return sol * (bound / peak), float(bound)
    return sol, float(peak)


def _cross_of(coords, j, prev, seg, no):
    J = np.asarray(coords[j], float)
    I = np.asarray(coords[no + prev[1] if prev[0] == "quad" else prev[1]],
                   float)
    O = np.asarray(coords[no + seg[1] if seg[0] == "quad" else seg[2]], float)
    li, lo = J - I, O - J
    return float(li[0] * lo[1] - li[1] * lo[0]), li, lo


def _abstain(upstream_commands, reason, **extra):
    result = {"candidate_commands": upstream_commands, "applied": False,
              "reason": reason, "widths": None}
    result.update(extra)
    return result


def _emit(upstream_commands, cand, no):
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


def _topology_gate(source_commands, upstream_commands, candidate):
    try:
        certs = [cc.certify_substitution(cmds)
                 for cmds in (source_commands, upstream_commands, candidate)]
    except (ArithmeticError, OverflowError, ValueError):
        return {"ok": False, "verdict": {"reason": "certify-error"}}
    if not all(c["ok"] for c in certs):
        return {"ok": False,
                "reason": "uncertified-substitution",
                "verdict": {"reason": "uncertified-substitution"}}
    try:
        polys = [cc.build_substituted_commands(cmds)
                 for cmds in (source_commands, upstream_commands, candidate)]
    except ValueError as exc:
        return {"ok": False, "reason": str(exc),
                "verdict": {"reason": str(exc)}}
    verdict = topology.compare_commands(polys[0], polys[1], polys[2])
    if not bool(verdict.get("supported") and verdict.get("ok")):
        return {"ok": False, "reason": "topology-changed",
                "verdict": verdict}
    return {"ok": True, "verdict": verdict}


def fit(source_commands, upstream_commands, size_px, reference,
        native_axes=(False, False), pairs=(), curve_intervals=16, fixed_x=()):
    """Source-relative general curved-width fit; exact upstream on failure."""
    if not _valid_axes(native_axes):
        return _abstain(upstream_commands, "malformed-native-axes")
    try:
        if not check_correspondence(source_commands, upstream_commands):
            return _abstain(upstream_commands, "no-correspondence")
        parsed = parse_commands(source_commands)
        fitted = parse_commands(upstream_commands)
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        return _abstain(upstream_commands, "malformed-commands")
    anchors = (reference.get("anchors") if isinstance(reference, dict)
               else None) or []
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
        weld = _weld_map(parsed, points)
        up_weld = _weld_map(fitted, up)
        if set(weld.items()) != set(up_weld.items()):
            return _abstain(upstream_commands, "weld-mismatch")
        for dup, canon in weld.items():
            if tuple(up[dup]) != tuple(up[canon]):
                return _abstain(upstream_commands, "weld-mismatch")
        fixed_x = set(fixed_x)
        fixed_x.update(weld.get(v, v) for v in tuple(fixed_x))
        owned = tuple(i for i, on in enumerate(native_axes[:2]) if on)
        involved = set()
        for p in pairs:
            involved.update(int(v) for v in p["a_ctrl"])
            involved.update(int(v) for v in p["b_ctrl"])
        joints = _joints(parsed, points, no)
        joint_rows = []
        degenerate_joints = []
        for j, occs in joints.items():
            for occ in occs:
                verts = {j}
                verts.add(occ["prev"][1] if occ["prev"][0] == "line"
                          else no + occ["prev"][1])
                verts.add(occ["seg"][2] if occ["seg"][0] == "line"
                          else no + occ["seg"][1])
                if not verts & involved:
                    continue
                # Hersch section 2: the complete incident polynomial is
                # immutable. A collapsed upstream leg requires no joint
                # equation when no free coordinate can reach this joint.
                if (1 in owned and all(0 in owned or v in fixed_x for v in verts)):
                    continue
                if occ["degenerate"]:
                    degenerate_joints.append((j, occ, verts))
                    involved.update(verts)
                    continue
                grown, res = _g1_row(upstream, j, occ["prev"], occ["seg"],
                                    no, size_px, occ["smooth"])
                if grown is None:
                    return _abstain(upstream_commands, res)
                involved.update(verts)
                joint_rows.append((grown, occ, j))
        if any(not 0 <= v < len(points) for v in involved):
            return _abstain(upstream_commands, "malformed-pairs")
        system = System([tuple(p) for p in points], size_px)
        pair_ctrls = []
        for p in pairs:
            for key in ("a_ctrl", "b_ctrl"):
                ctrl = [int(v) for v in p[key]]
                if ctrl not in pair_ctrls:
                    pair_ctrls.append(ctrl)
            for ctrl in p.get("shape_ctrl", []):
                c = [int(v) for v in ctrl]
                if c not in pair_ctrls:
                    pair_ctrls.append(c)
        for curve in cw.curves_of(parsed):
            ctrl = list(curve['idx'])
            if set(ctrl) & involved and ctrl not in pair_ctrls:
                pair_ctrls.append(ctrl)
        for ctrl in pair_ctrls:
            if len(ctrl) == 3:
                cw._add_quad_shape(system, ctrl, intervals=curve_intervals)
            else:
                system.curve(ctrl, intervals=curve_intervals)
        for contour in parsed['contours']:
            for seg in contour:
                if seg[0] == 'line' and {seg[1], seg[2]} & involved:
                    try:
                        system.edge(seg[1], seg[2])
                    except ValueError:
                        pass
        pair_objs = []
        for p in pairs:
            ta, tb = float(p["a_t"]), float(p["b_t"])
            if not 0 <= ta <= 1 or not 0 <= tb <= 1:
                return _abstain(upstream_commands, "malformed-pairs")
            width_2r = float(p["width_2r"])
            if not width_2r > 0:
                return _abstain(upstream_commands, "malformed-pairs")
            normal = np.asarray(p["normal"], float)
            nn = float(np.linalg.norm(normal))
            if not nn > 0:
                return _abstain(upstream_commands, "malformed-pairs")
            normal = normal / nn
            tangent = np.array([-normal[1], normal[0]])
            sa = _quad_sample(p["a_ctrl"], ta)
            sb = _quad_sample(p["b_ctrl"], tb)
            error = -system.projected(sa, normal, sb) / width_2r
            qa = np.asarray(cw._eval(
                [tuple(points[i]) for i in p["a_ctrl"]], ta))
            qb = np.asarray(cw._eval(
                [tuple(points[i]) for i in p["b_ctrl"]], tb))
            chord = qa - qb
            pair_objs.append((SimpleNamespace(
                a=sa, b=sb, normal=normal, tangent=tangent,
                width=width_2r, length=float(p["arc"]), kind="ink",
                error=np.asarray(error, float), chord=chord), p))
        rows = []
        for group, row, const in system.rows:
            row = np.asarray(row, float)
            if group in ("curve-position", "curve-stretch", "curve-bend"):
                const = 0.0
            rows.append((group, row, float(const)))
        for grow, occ, j in joint_rows:
            row, const, _ = grow
            rows.append(("joint-g1" if occ["smooth"] else "joint-defect",
                         np.asarray(row, float), float(const)))
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
        frozen = set(weld)
        for _, _, verts in degenerate_joints:
            frozen.update(verts)
        cols = [(v, axis) for v in sorted(involved) for axis in (0, 1)
                if axis not in owned and v not in frozen and not (axis == 0 and v in fixed_x)]
        if not cols:
            return _abstain(upstream_commands, "no-free-controls")
        mat = np.stack([r for _, r, _ in rows])
        for dup, canon in weld.items():
            for axis in (0, 1):
                mat[:, canon * 2 + axis] += mat[:, dup * 2 + axis]
        rhs = np.array([-c for _, _, c in rows], float)
        sub = np.column_stack([mat[:, v * 2 + axis] for v, axis in cols])
        widths_2r = [pair.width for pair, _ in pair_objs]
        bound = min(pair.width / 2 - float(p['approx_bound']) / 2
                    for pair, p in pair_objs) - HEADROOM
        if not bound >= HEADROOM:
            return _abstain(upstream_commands, "movement-budget-empty")
        hard_joints = native_axes == (False, True) or native_axes == [False, True]
        if hard_joints:
            from experiments.hobby_fitting.joint_diagonal import _bounded_equalities
            mask = np.array([group in ('joint-g1', 'joint-defect')
                             for group, _, _ in rows])
            g, h = sub[mask], rhs[mask]
            nonzero = np.linalg.norm(g, axis=1) > 1e-12
            if np.any(abs(h[~nonzero]) > 1e-10):
                return _abstain(upstream_commands, 'joint-pins-incompatible')
            solved = _bounded_equalities(sub[~mask], rhs[~mask],
                                          g[nonzero], h[nonzero],
                                          np.full(len(cols), bound)) if np.any(nonzero) else None
            if solved is None:
                return _abstain(upstream_commands, 'joint-bounds-incompatible')
            sol, qp = solved
            peak = float(np.max(abs(sol), initial=0))
        else:
            sol, _, _, _ = np.linalg.lstsq(sub, rhs, rcond=None)
            sol, peak = _scale_to_bound(np.asarray(sol, float), cols, bound)
            qp = None
        sol = np.asarray(sol, float)
        incident = cw._incident_curves(parsed)
        paired = {frozenset({tuple(p["a_ctrl"]), tuple(p["b_ctrl"])})
                  for _, p in pair_objs}

        def attempt(frac):
            # One convex prefix of the least-squares step: the quadratic
            # objective decreases monotonically from upstream, so a
            # smaller prefix trades correction for gate headroom without
            # changing direction. Every gate re-runs on the prefix.
            cand = upstream.copy()
            for (v, axis), d in zip(cols, sol):
                if float(d) == 0.0:
                    continue
                cand[v][axis] = upstream[v][axis] + frac * float(d)
            for dup, canon in weld.items():
                cand[dup][0] = cand[canon][0]
                cand[dup][1] = cand[canon][1]
            raw_cand = cand.copy()
            for v, axis in cols:
                if cand[v][axis] != upstream[v][axis]:
                    cand[v][axis] = _round_26_6(float(cand[v][axis]))
            for dup, canon in weld.items():
                for axis in (0, 1):
                    if axis not in owned:
                        cand[dup][axis] = cand[canon][axis]
            for v in range(len(points)):
                for axis in owned:
                    if cand[v][axis] != upstream[v][axis]:
                        return False, {"reason": "native-violated"}
            for j, occ, verts in degenerate_joints:
                if any(cand[v][0] != upstream[v][0]
                       or cand[v][1] != upstream[v][1] for v in verts):
                    return False, {"reason": "degenerate-joint-moved",
                                   "joint": int(j)}
            continuity = []
            for grow, occ, j in joint_rows:
                cross_c, li_c, lo_c = _cross_of(cand, j, occ["prev"],
                                                occ["seg"], no)
                cross_u, li_u, lo_u = _cross_of(upstream, j, occ["prev"],
                                                occ["seg"], no)
                iv = occ["prev"][1] if occ["prev"][0] == "line" \
                    else no + occ["prev"][1]
                ov = occ["seg"][2] if occ["seg"][0] == "line" \
                    else no + occ["seg"][1]
                moved = (
                    (raw_cand[iv][0] != upstream[iv][0],
                     raw_cand[iv][1] != upstream[iv][1]),
                    (raw_cand[j][0] != upstream[j][0],
                     raw_cand[j][1] != upstream[j][1]),
                    (raw_cand[ov][0] != upstream[ov][0],
                     raw_cand[ov][1] != upstream[ov][1]))
                qb = _quant_cross_bound(li_u, lo_u, moved)
                raw_cross, _, _ = _cross_of(raw_cand, j, occ['prev'], occ['seg'], no)
                raw_target = 0. if occ['smooth'] else cross_u
                raw_ok = abs(raw_cross - raw_target) <= 1e-9 * (1 + abs(raw_target))
                legs_ok = bool(np.linalg.norm(li_c) > 0
                               and np.linalg.norm(lo_c) > 0)
                cross_s, _, _ = _cross_of(base, j, occ["prev"],
                                          occ["seg"], no)
                if occ["smooth"]:
                    fwd = bool(float(np.dot(li_c, lo_c)) > 0)
                    allowed = qb if hard_joints else abs(cross_s - cross_u) + qb
                    defect = abs(cross_c)
                    ok = legs_ok and fwd and defect <= allowed and (raw_ok or not hard_joints)
                else:
                    allowed = abs(cross_s - cross_u) + qb
                    defect = abs(cross_c - cross_u)
                    fwd = bool(float(np.dot(li_c, li_u)) > 0
                               and float(np.dot(lo_c, lo_u)) > 0)
                    sign_ok = bool(cross_u == 0.0
                                   or cross_c * cross_u >= 0)
                    # With native Y fixed the hard joint equation retains
                    # the signed cross exactly before rounding. A sign
                    # change inside its proven 26.6 error envelope is a
                    # representation effect, not an unconstrained rotation.
                    if hard_joints:
                        sign_ok = raw_ok
                    ok = legs_ok and fwd and sign_ok and defect <= allowed
                continuity.append({"joint": int(j),
                                   "smooth": bool(occ["smooth"]),
                                   "cross_up": float(cross_u),
                                   "cross_cand": float(cross_c),
                                   "allowed": float(allowed),
                                   "defect": float(defect),
                                   'raw_cross': float(raw_cross), 'raw_target': float(raw_target),
                                   "legs_ok": legs_ok, "fwd_dot": fwd,
                                   "ok": bool(ok)})
                if not ok:
                    return False, {"reason": "joint-continuity-failed",
                                   "continuity": continuity}
            moved = {v for v in range(len(points))
                     if cand[v][0] != upstream[v][0]
                     or cand[v][1] != upstream[v][1]}
            for v in sorted(moved):
                for ctrl in incident.get(v, []):
                    if len(ctrl) != 3:
                        return False, {"reason": "cubic-interval-uncertified",
                                       "continuity": continuity}
                    ok, why = cw._quad_interval_ok(
                        [tuple(base[i]) for i in ctrl],
                        [tuple(cand[i]) for i in ctrl])
                    if not ok:
                        return False, {"reason": why,
                                       "continuity": continuity,
                                       "interval_ctrl": [int(i)
                                                         for i in ctrl]}
            ok, stage = _clearance_ok(pair_objs, cand, parsed, involved,
                                      upstream, paired)
            if not ok:
                return False, {"reason": "clearance-failed",
                               "clearance_stage": stage,
                               "continuity": continuity}
            out = _emit(upstream_commands, cand, no)
            gate = _topology_gate(source_commands, upstream_commands, out)
            if not gate["ok"]:
                return False, {"reason": gate.get(
                    "reason", "topology-changed"),
                    "topology": gate["verdict"],
                    "continuity": continuity}
            return True, {"cand": cand, "out": out, "continuity": continuity,
                          "topology": gate["verdict"], "frac": frac}

        cand, out, continuity = None, None, None
        verdict, info, gate = None, {"reason": "no-feasible-prefix"}, None
        tried = []
        frac = 1.0
        for _ in range(7):
            tried.append(frac)
            verdict, info = attempt(frac)
            if verdict:
                cand = info["cand"]
                out = info["out"]
                continuity = info["continuity"]
                gate = {"ok": True, "verdict": info["topology"]}
                break
            if hard_joints:
                break
            if info["reason"] == "native-violated":
                break
            identical = True
            probe = upstream.copy()
            for (v, axis), d in zip(cols, sol):
                if float(d) == 0.0:
                    continue
                probe[v][axis] = upstream[v][axis] + frac * float(d)
            for dup, canon in weld.items():
                probe[dup][0] = probe[canon][0]
                probe[dup][1] = probe[canon][1]
            for v, axis in cols:
                if probe[v][axis] != upstream[v][axis]:
                    probe[v][axis] = _round_26_6(float(probe[v][axis]))
            for v in range(len(points)):
                for axis in (0, 1):
                    if probe[v][axis] != upstream[v][axis]:
                        identical = False
            if identical:
                info = {"reason": "no-effective-move",
                        "continuity": info.get("continuity")}
                break
            frac /= 2.0
        if not verdict:
            extra = {"tried_prefixes": tried}
            extra.update({k: v for k, v in info.items()
                          if k in ("continuity", "topology",
                                   "clearance_stage", "interval_ctrl",
                                   "joint")})
            return _abstain(upstream_commands, info["reason"], **extra)
    except (KeyError, TypeError, AttributeError, ArithmeticError,
            ValueError):
        return _abstain(upstream_commands, "malformed-commands")
    widths_out = []
    for pair, p in pair_objs:
        n = np.asarray(pair.normal, float)
        src_w = pair.width
        up_w = float(abs(np.dot(
            np.asarray(cw._eval([tuple(upstream[i]) for i in p["b_ctrl"]],
                                float(p["b_t"])))
            - np.asarray(cw._eval([tuple(upstream[i]) for i in p["a_ctrl"]],
                                  float(p["a_t"]))), n)))
        cand_w = float(abs(np.dot(
            np.asarray(cw._eval([tuple(cand[i]) for i in p["b_ctrl"]],
                                float(p["b_t"])))
            - np.asarray(cw._eval([tuple(cand[i]) for i in p["a_ctrl"]],
                                  float(p["a_t"]))), n)))
        widths_out.append({"source_2r": float(src_w), "upstream": float(up_w),
                           "candidate": float(cand_w),
                           "approx_bound": float(p["approx_bound"]),
                           "radii": [float(v) for v in p["radii"]]})
    return {"candidate_commands": out, "applied": True, "reason": "fitted",
            "widths": widths_out, "continuity": continuity,
            "diagnostics": {"n_pairs": len(pair_objs),
                            'qp': qp,
                            "n_joints": len(joint_rows),
                            "bound": float(bound),
                            "peak": float(peak),
                            "native_axes": list(native_axes[:2])},
            "topology": gate["verdict"]}


def _box(points):
    return (min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points))


def _boxes_separate(a, b):
    return a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1]


@lru_cache(maxsize=1024)
def _clearance_pieces(controls):
    return tuple((tuple(hull), _box(hull)) for hull in cc.piece_hulls(controls, 4))


def _hulls_ok(new_a, new_b, shared):
    """Depth-4 subdivision separation with incident-point exemption.

    Bezier convex-hull containment is sound at any depth; finer pieces
    shed the false overlap of whole control hulls at adjacent curves.
    Incident pairs may meet solely at their shared junction.
    """
    if _boxes_separate(_box(new_a), _box(new_b)):
        return True
    for hp, bp in _clearance_pieces(tuple(tuple(p) for p in new_a)):
        for hq, bq in _clearance_pieces(tuple(tuple(p) for p in new_b)):
            if _boxes_separate(bp, bq):
                continue
            if shared and cc.hulls_meet_only_at(hp, hq, shared):
                continue
            if not cc.strictly_disjoint(hp, hq):
                return False
    return True


def _shared_point(new_a, new_b):
    for p in (new_a[0], new_a[-1]):
        for q in (new_b[0], new_b[-1]):
            if p == q:
                return p
    return None


def _clearance_ok(pair_objs, cand, parsed, involved, upstream, paired):
    """Delivery clearance with subdivision certificates.

    Station disks clear fixed primitives exactly; moved/fixed and
    moved/moved hulls separate at depth 4 with incident-junction
    exemption. Paired curves skip hull separation (their interval is
    width-governed; the exact topology gate covers crossings), and
    swept lines skip incident curves (folding there is blocked by the
    tangent/curvature gate plus the topology gate). All exemptions are
    recorded, none silent.
    """
    pts = parsed["oncurve"] + parsed["offcurve"]
    fixed_curves, moved_curves = [], []
    for c in cw.curves_of(parsed):
        ctrls = [tuple(pts[i]) for i in c["idx"]]
        new = [tuple(cand[i]) for i in c["idx"]]
        if set(c["idx"]) & involved:
            moved_curves.append((c, ctrls, new))
        else:
            fixed_curves.append((c, ctrls, new))
    up = [tuple(u) for u in upstream]
    moved_lines, fixed_lines = [], []
    for contour in parsed["contours"]:
        for seg in contour:
            if seg[0] == "line":
                i, j = seg[1], seg[2]
                old_seg = (tuple(up[i]), tuple(up[j]))
                new_seg = (tuple(cand[i]), tuple(cand[j]))
                (moved_lines if old_seg != new_seg else fixed_lines).append(
                    (i, j, old_seg, new_seg))
    for pair, p in pair_objs:
        qa = cw._eval([tuple(cand[i]) for i in p["a_ctrl"]], float(p["a_t"]))
        qb = cw._eval([tuple(cand[i]) for i in p["b_ctrl"]], float(p["b_t"]))
        center = tuple((np.asarray(qa) + np.asarray(qb)) / 2)
        radius = float(np.linalg.norm(np.asarray(qb) - np.asarray(qa))) / 2
        for _, _, fix_new in fixed_curves:
            ok, _ = cc.disk_clear(center, radius, fix_new)
            if not ok:
                return False, "station-disk-curve"
        for _, _, old_seg, _ in fixed_lines:
            if not cw._seg_open_clear(center, radius, old_seg):
                return False, "station-disk-line"
    live = [(c, n) for c, s, n in moved_curves
            if any(tuple(cand[i]) != tuple(up[i]) for i in c["idx"])]
    for k, (_, new) in enumerate(live):
        for _, _, fix_new in fixed_curves:
            shared = _shared_point(new, fix_new)
            if not _hulls_ok(new, fix_new, shared):
                return False, "moved-fixed-hull"
        for n, (_, other) in enumerate(live):
            if n == k:
                continue
            if frozenset({tuple(live[k][0]["idx"]),
                          tuple(live[n][0]["idx"])}) in paired:
                continue
            shared = _shared_point(new, other)
            if not _hulls_ok(new, other, shared):
                return False, "moved-moved-hull"
    for i, j, old_seg, new_seg in moved_lines:
        for _, _, fix_new in fixed_curves:
            ok, _ = cc.edge_vs_curve_clear(old_seg, new_seg, fix_new)
            if not ok:
                return False, "swept-fixed-curve"
        swept = cc.swept_hull(old_seg, new_seg)
        for c, new in live:
            if i in c["idx"] or j in c["idx"]:
                continue
            for hull in cc.piece_hulls(list(new), 4):
                if not cc.strictly_disjoint(swept, hull):
                    return False, "swept-moved-curve"
    return True, "clear"


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


def fit_glyph(source_commands, upstream_commands, size_px, reference,
              native_axes=(False, False), pairs=None, fixed_x=()):
    """Harness API: automatic recognition then source-relative curve fit."""
    if pairs is None:
        pairs, recog = recognize(source_commands)
    else:
        recog = {"supplied": len(pairs)}
    if not pairs:
        return {"candidate_commands": upstream_commands, "applied": False,
                "reason": "no-certified-pairs", "widths": None,
                "recognition": recog,
                "fixed": {"native_axes": list(native_axes[:2])}}
    out = fit(source_commands, upstream_commands, size_px, reference,
              native_axes, pairs, fixed_x=fixed_x)
    out["recognition"] = recog
    if out.get("widths"):
        for row, p in zip(out["widths"], pairs):
            n = _pair_normal(source_commands, p)
            row["effectibility_x"] = abs(float(n[0])) if n is not None else None
    return out


def attachment_controls(parsed):
    """Hersch section 2: retain straight attachments as whole polynomials.

    All straight endpoints and incident quadratic controls stay upstream;
    this local ownership rule has no orientation or length threshold.
    """
    points = parsed['oncurve'] + parsed['offcurve']
    no = len(parsed['oncurve'])
    weld = _weld_map(parsed, points)
    canonical = lambda v: weld.get(v, v)
    endpoints = {canonical(v) for contour in parsed['contours']
                 for seg in contour if seg[0] == 'line'
                 and points[seg[1]] != points[seg[2]]
                 for v in (seg[1], seg[2])}
    frozen = set(endpoints)
    for contour in parsed['contours']:
        for seg in contour:
            if seg[0] == 'quad' and (canonical(seg[2]) in endpoints
                                     or canonical(seg[3]) in endpoints):
                frozen.update((canonical(seg[2]), no + seg[1], canonical(seg[3])))
    frozen.update(dup for dup, canon in weld.items() if canon in frozen)
    return frozen


def fit_horizontal_glyph(source_commands, upstream_commands, size_px, reference,
                         native_axes=(False, False)):
    """Horizontal completion retains the existing native or automatic Y fit.

    Turner/Lemberg §2 separates axis fitting; Hersch §5 treats reference
    heights and curve extrema as grid constraints. Width completion must
    preserve those already-fitted vertical relationships.
    """
    if not _valid_axes(native_axes):
        return _abstain(upstream_commands, 'malformed-native-axes')
    parsed = parse_commands(source_commands)
    fixed_x = attachment_controls(parsed)
    retained = (native_axes[0], True)
    result = fit_glyph(source_commands, upstream_commands, size_px, reference, retained, fixed_x=fixed_x)
    result.setdefault('diagnostics', {})['native_axes'] = list(native_axes)
    result['diagnostics']['retained_upstream_axes'] = list(retained)
    result['diagnostics']['attachment_controls'] = sorted(fixed_x)
    return result
