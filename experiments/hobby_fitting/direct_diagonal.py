"""Direct outline-based diagonal grid fitting (no stroke annotations).

Recognition starts from the filled nonzero-winding boundary: all opposing
straight border portions with open corridor overlap, split at exact
straight intersections, hidden interior ink excluded by certified two-sided
winding. Hobby 3.2 supplies corridor opposition, dominance intervals and
rechecked disks; (4)/(5) supply medial width as twice the radius and the
signed projected relative width error; (17) couples diagonal stations to a
font-wide list of upright anchors through per-anchor rows weighted by arc
products and the published angular weights; 3.4 (10) bounds the grid arm to
nearly constant width (gamma .25). Hersch sections 5-6 and Figure 25 supply
diagonal parallelization plus integer axis separation; VTT DStroke supplies
stationary/floating ownership, parallel borders and matching staircase
phase. Variables are displacements from the upstream fit with source
coefficients substituted into the constants, following the validated
StrokeStyles consumer: geometry residuals vanish at upstream, anchor
relative changes join as ink-match constants. Grid hard rows fix border
parallelism and integer line separation; the constrained joint least
squares runs source shape plus (17) coupling in the nullspace, so shared
vertices carry one unknown and no per-pair moves are ever summed. Integer
line separation between parallel borders is normal width over the axis
normal component, never the contact-chord projection. Residuals are
evidence per constraint group, not an acceptance score. The ideal parallel
constraint is reported separately from its 26.6 representation: fixed
native coordinates can make exact parallelism unrepresentable after
rounding, so rounded achievement carries a two-HEADROOM allowance per
norm difference and phase is reported, never theorem-claimed.
"""

import math
import struct
from fractions import Fraction

import numpy as np

from experiments.hobby_fitting import intervals
from experiments.hobby_fitting.prototype import Sample, System, width_weight
from experiments.hobby_fitting.real_outline import (
    check_correspondence,
    parse_commands,
)

STATION_FRACS = (0.25, 0.5, 0.75)
# Nearest-26.6 Euclidean rounding reserve (Hobby interval model).
HEADROOM = math.sqrt(2.0) / 128.0
# Hobby 3.4 (10), gamma_2 ~ 0.25: width spread <= gamma_2/sqrt(w_max).
# Straight segment-pair bisectors have constant direction, so theta spread is zero.
GRID_SPREAD = 0.25


def _winding_dir(pt, loops, axis, positive):
    """Nonzero winding along one axis ray; straights are exact.

    Coordinates rotate so the ray becomes +x. Reflection may flip
    the sign, but only zero versus nonzero is ever read.
    """
    def move(p):
        x, y = p
        if axis == 1:
            x, y = y, x
        if not positive:
            x = -x
        return (x, y)

    x, y = move(pt)
    total = 0
    for loop in loops:
        moved = [move(p) for p in loop]
        a = moved[-1]
        for b in moved:
            if (a[1] <= y) != (b[1] <= y):
                xi = a[0] + (y - a[1]) / (b[1] - a[1]) * (b[0] - a[0])
                if xi > x:
                    total += 1 if b[1] > a[1] else -1
            a = b
    return total


def _ray_hits_box(pt, box, axis, positive):
    """True when the axis ray from pt enters the bbox (touch counts)."""
    lo_x, lo_y, hi_x, hi_y = box
    x, y = pt
    if axis == 0:
        if y < lo_y or y > hi_y:
            return False
        return hi_x >= x if positive else lo_x <= x
    if x < lo_x or x > hi_x:
        return False
    return hi_y >= y if positive else lo_y <= y


def _certified_winding(pt, straight_loops, curve_flats):
    """Winding valid only along a ray avoiding every curve bbox.

    A ray that never enters a curve's control-hull bbox meets neither
    the true curve nor its flattening, so both contribute zero and the
    count is exact without any subdivision error claim. When every
    axis ray enters some curve bbox the query abstains instead of
    trusting the subdivision.
    """
    for axis in (0, 1):
        for positive in (True, False):
            if any(_ray_hits_box(pt, box, axis, positive)
                   for _, box in curve_flats):
                continue
            loops = list(straight_loops) + [flat for flat, _ in
                                            curve_flats]
            return _winding_dir(pt, loops, axis, positive)
    return None


def _seg_point_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    den = dx * dx + dy * dy
    if den == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / den
    t = max(0.0, min(1.0, t))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def _bbox_point_dist(p, box):
    lo_x, lo_y, hi_x, hi_y = box
    dx = lo_x - p[0] if p[0] < lo_x else (p[0] - hi_x if p[0] > hi_x
                                         else 0.0)
    dy = lo_y - p[1] if p[1] < lo_y else (p[1] - hi_y if p[1] > hi_y
                                         else 0.0)
    return math.hypot(dx, dy)


def _bbox_overlap(a, b):
    return (a[0] <= b[2] and b[0] <= a[2]
            and a[1] <= b[3] and b[1] <= a[3])


def _signed_areas(loops):
    out = []
    for loop in loops:
        n = len(loop)
        out.append(sum(loop[i][0] * loop[(i + 1) % n][1]
                       - loop[(i + 1) % n][0] * loop[i][1]
                       for i in range(n)) / 2)
    return out


def _round_26_6(x):
    """Nearest 1/64 unit, ties toward positive infinity."""
    return math.floor(x * 64 + 0.5) / 64


def _f32bits(x):
    return struct.unpack(">I", struct.pack(">f", x))[0]


def _axis_of(p0, p1):
    if p0[0] == p1[0]:
        return "x"
    if p0[1] == p1[1]:
        return "y"
    return None


def _seg_intersection(p1, p2, p3, p4):
    """Split parameters for a proper crossing or endpoint touch."""
    d = (p2[0] - p1[0]) * (p4[1] - p3[1]) - (p2[1] - p1[1]) * (p4[0] - p3[0])
    if d == 0:
        return None
    t = ((p3[0] - p1[0]) * (p4[1] - p3[1])
         - (p3[1] - p1[1]) * (p4[0] - p3[0])) / d
    u = ((p3[0] - p1[0]) * (p2[1] - p1[1])
         - (p3[1] - p1[1]) * (p2[0] - p1[0])) / d
    if 0 < t < 1 and 0 < u < 1:
        return (t, u)
    if 0 < t < 1 and (u == 0 or u == 1):
        return (t, u)
    if 0 < u < 1 and (t == 0 or t == 1):
        return (t, u)
    return None


def _controls(seg, oncurve, offcurve):
    if seg[0] == "line":
        return [oncurve[seg[1]], oncurve[seg[2]]]
    if seg[0] == "quad":
        return [oncurve[seg[2]], offcurve[seg[1]], oncurve[seg[3]]]
    return [oncurve[seg[3]], offcurve[seg[1]], offcurve[seg[2]],
            oncurve[seg[4]]]


def _flatten_seg(seg, oncurve, offcurve, parts=32):
    pts = _controls(seg, oncurve, offcurve)
    if seg[0] == "line":
        return list(pts)
    out = []
    for i in range(parts + 1):
        t = i / parts
        while len(pts) > 1:
            pts = [[(1 - t) * a[0] + t * b[0], (1 - t) * a[1] + t * b[1]]
                   for a, b in zip(pts, pts[1:])]
        out.append(pts[0])
        pts = _controls(seg, oncurve, offcurve)
    return out


def _curve_box(seg, oncurve, offcurve):
    """Control-hull bbox: an exact superset of the true curve."""
    xs = [p[0] for p in _controls(seg, oncurve, offcurve)]
    ys = [p[1] for p in _controls(seg, oncurve, offcurve)]
    return (min(xs), min(ys), max(xs), max(ys))


def _exact_intersection(p1, p2, p3, p4):
    """Exact crossing parameters with one transported common point.

    Coordinates are exact rationals of the inputs, so proper
    crossings and endpoint touches decide truly with no tolerance
    merging of unrelated nearby vertices. The proper-crossing point
    is evaluated once from the first edge and shared, keeping one
    geometric identity however it rounds; touches reuse the exact
    input vertex both edges already hold.
    """
    def fr(p):
        return (Fraction(p[0]), Fraction(p[1]))

    a1, a2 = fr(p1), fr(p2)
    b1, b2 = fr(p3), fr(p4)
    den = (a2[0] - a1[0]) * (b2[1] - b1[1]) \
        - (a2[1] - a1[1]) * (b2[0] - b1[0])
    if den == 0:
        return None
    t = ((b1[0] - a1[0]) * (b2[1] - b1[1])
         - (b1[1] - a1[1]) * (b2[0] - b1[0])) / den
    u = ((b1[0] - a1[0]) * (a2[1] - a1[1])
         - (b1[1] - a1[1]) * (a2[0] - a1[0])) / den
    zero, one = Fraction(0), Fraction(1)
    if zero < t < one and zero < u < one:
        point = (float(a1[0] + t * (a2[0] - a1[0])),
                 float(a1[1] + t * (a2[1] - a1[1])))
    elif zero < t < one and (u == zero or u == one):
        point = p3 if u == zero else p4
    elif zero < u < one and (t == zero or t == one):
        point = p1 if t == zero else p2
    else:
        return None
    return t, u, point


def _exact_cut_sites(edges):
    """Canonical split sites keyed by exact parameter.

    One entry per proper crossing or endpoint touch, mirroring the
    legacy adjacency rule; each site's point is transported once so
    geometrically shared vertices compare exactly downstream.
    """
    sites = {k: {} for k in range(len(edges))}
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            a, b = edges[i], edges[j]
            if (a["contour"] == b["contour"]
                    and abs(a["seg"] - b["seg"]) <= 1):
                continue
            hit = _exact_intersection(a["p0"], a["p1"],
                                      b["p0"], b["p1"])
            if hit is None:
                continue
            t, u, point = hit
            if Fraction(0) < t < Fraction(1):
                sites[i][t] = point
            if Fraction(0) < u < Fraction(1):
                sites[j][u] = point
    return sites


def _curve_controls(parsed):
    """Actual Bezier controls per curved segment, contour order.

    Shene's convex-hull property keeps every curve inside its
    controls, so hull bboxes conservatively bound each piece; the
    helper's exact dyadic subdivision tightens them.
    """
    oncurve, offcurve = parsed["oncurve"], parsed["offcurve"]
    out = []
    for contour in parsed["contours"]:
        for seg in contour:
            if seg[0] == "line":
                continue
            out.append(_controls(seg, oncurve, offcurve))
    return out


def _helper():
    """Optional curve-certification dependency; absence or failure
    fails closed instead of breaking straight fitting."""
    try:
        from experiments.hobby_fitting import curve_clearance
        return curve_clearance
    except ImportError:
        return None


def _split_visible(parsed, canonical=False):
    """Straight border portions with certified winding visibility.

    Canonical discovery builds split sites from exact rational
    crossings with one transported common point; the default keeps
    legacy float discovery exactly for the reference control.

    Segments split at exact straight intersections; each portion keeps
    affine correspondence to its original edge endpoints. A portion is
    hidden when both offset sides carry nonzero winding. The sided
    offset is half the portion midpoint's clearance to every other
    boundary, a strict subfraction in caller units, so no fixed pixel
    epsilon decides sidedness. Exact touching (zero clearance) hides
    the portion by arrangement, not by tolerance. Winding queries that
    no certified ray can answer mark the portion unknown, and unknown
    portions never certify pairs.
    """
    oncurve, offcurve = parsed["oncurve"], parsed["offcurve"]
    edges = []
    for ci, contour in enumerate(parsed["contours"]):
        for si, seg in enumerate(contour):
            if seg[0] == "line":
                edges.append({"contour": ci, "seg": si,
                              "i0": seg[1], "i1": seg[2],
                              "p0": oncurve[seg[1]],
                              "p1": oncurve[seg[2]]})
    if canonical:
        sites = _exact_cut_sites(edges)
    else:
        cuts = {k: set() for k in range(len(edges))}
        for i in range(len(edges)):
            for j in range(i + 1, len(edges)):
                a, b = edges[i], edges[j]
                if (a["contour"] == b["contour"]
                        and abs(a["seg"] - b["seg"]) <= 1):
                    continue
                hit = _seg_intersection(a["p0"], a["p1"],
                                        b["p0"], b["p1"])
                if hit is not None:
                    cuts[i].add(hit[0])
                    cuts[j].add(hit[1])
    straight_loops, curve_flats, curve_boxes = [], [], []
    for contour in parsed["contours"]:
        straight = []
        for seg in contour:
            if seg[0] == "line":
                pts = [oncurve[seg[1]], oncurve[seg[2]]]
                straight.extend(pts[:-1] if straight else pts)
            else:
                flat = _flatten_seg(seg, oncurve, offcurve)
                curve_flats.append((flat, _curve_box(seg, oncurve,
                                                     offcurve)))
                curve_boxes.append(curve_flats[-1][1])
                straight.extend(flat[:-1] if straight else flat)
        straight.append(straight[0])
        straight_loops.append(straight)
    portions = []
    for i, edge in enumerate(edges):
        dx = edge["p1"][0] - edge["p0"][0]
        dy = edge["p1"][1] - edge["p0"][1]
        length = math.hypot(dx, dy)
        if length <= 0:
            continue
        if canonical:
            params = sorted(sites[i].keys())
            bounds = [Fraction(0)] + params + [Fraction(1)]
        else:
            params = sorted(t for t in cuts[i] if 0 < t < 1)
            bounds = [0.0] + params + [1.0]
        normal = (-dy / length, dx / length)
        for t0, t1 in zip(bounds, bounds[1:]):
            if t1 - t0 <= 0:
                continue
            if canonical:
                f0, f1 = float(t0), float(t1)
                site = sites[i]
                q0 = site.get(t0, (edge["p0"][0] + dx * f0,
                                   edge["p0"][1] + dy * f0))
                q1 = site.get(t1, (edge["p0"][0] + dx * f1,
                                   edge["p0"][1] + dy * f1))
                t0, t1 = f0, f1
            else:
                q0 = (edge["p0"][0] + dx * t0,
                      edge["p0"][1] + dy * t0)
                q1 = (edge["p0"][0] + dx * t1,
                      edge["p0"][1] + dy * t1)
            mid = ((q0[0] + q1[0]) / 2, (q0[1] + q1[1]) / 2)
            clearance, cause = _portion_clearance(mid, edge, edges,
                                                  curve_boxes)
            unknown_cause = None
            if cause in ("no-clearance", "box-zero"):
                hidden, unknown = False, True
                unknown_cause = cause
            elif cause == "touch":
                hidden, unknown = True, False
            else:
                off = clearance / 2
                sides = [_certified_winding(
                    (mid[0] + normal[0] * off,
                     mid[1] + normal[1] * off),
                    straight_loops, curve_flats),
                    _certified_winding(
                    (mid[0] - normal[0] * off,
                     mid[1] - normal[1] * off),
                    straight_loops, curve_flats)]
                if any(s is None for s in sides):
                    hidden, unknown = False, True
                    unknown_cause = "winding-uncertain"
                else:
                    hidden, unknown = all(s != 0 for s in sides), False
            portions.append({"edge": i, "contour": edge["contour"],
                             "seg": edge["seg"], "t0": t0, "t1": t1,
                             "p0": q0, "p1": q1,
                             "i0": edge["i0"], "i1": edge["i1"],
                             "length": length * (t1 - t0),
                             "hidden": hidden, "unknown": unknown,
                             "unknown_cause": unknown_cause})
    return portions, curve_boxes, straight_loops, curve_flats


def _portion_clearance(mid, edge, edges, curve_boxes):
    """Least distance from a portion midpoint to other boundaries.

    Straight borders use exact point-segment distance; curves use
    bbox distance, a certified lower bound since the curve lies
    inside its control-hull box. A zero bbox distance is only the
    lower bound, never actual contact, so it reports box-zero
    instead of a clearance. The portion's own edge is excluded;
    collinear continuations count at their true along-edge distance.
    """
    best, cause = None, "no-clearance"
    for other in edges:
        if (other["contour"], other["seg"]) == (edge["contour"],
                                                edge["seg"]):
            continue
        dist = _seg_point_dist(mid, other["p0"], other["p1"])
        if best is None or dist < best:
            best, cause = dist, "clear"
    for box in curve_boxes:
        dist = _bbox_point_dist(mid, box)
        if dist == 0.0:
            return 0.0, "box-zero"
        if best is None or dist < best:
            best, cause = dist, "clear"
    if best is None:
        return None, "no-clearance"
    if best == 0.0:
        return 0.0, "touch"
    return best, cause


def _visible_borders(portions):
    """Competitors include uncertain boundaries conservatively.

    Only proven both-sides-nonzero hidden interior seams are
    dropped; unknown portions still bound medial clearance, so
    omitting them would certify against an incomplete boundary set.
    """
    others = []
    for portion in portions:
        if portion["hidden"]:
            continue
        key = (portion["contour"], portion["seg"],
               portion["t0"], portion["t1"])
        others.append({"seg": (tuple(portion["p0"]), tuple(portion["p1"])),
                       "tag": "edge(%d,%d,%.6f,%.6f)" % key,
                       "key": (portion["contour"], portion["seg"],
                               portion["t0"], portion["t1"])})
    return others


def _near_curves(pair, stations, curve_data):
    """True when an uncertified curve may enter the pair's ink zone.

    Curves are tested per segment against their control-hull boxes,
    so a distant curve never rejects a straight pair. Box overlap
    alone does not abstain: when every station's medial disk clears
    the hull box, the curve cannot touch the pair and the pair is
    certified despite the overlap. Curves too close for the disk
    abstain the pair; curve fitting itself stays unsupported.
    """
    xs = [pair["a"]["p0"][0], pair["a"]["p1"][0],
          pair["b"]["p0"][0], pair["b"]["p1"][0]]
    ys = [pair["a"]["p0"][1], pair["a"]["p1"][1],
          pair["b"]["p0"][1], pair["b"]["p1"][1]]
    box = (min(xs), min(ys), max(xs), max(ys))
    for seg, hull in curve_data:
        if not _bbox_overlap(box, hull):
            continue
        clear = True
        for st in stations:
            center = st["hit"]["center"]
            radius = st["hit"]["r"]
            if _bbox_point_dist(center, hull) <= radius:
                clear = False
                break
        if not clear:
            return True
    return False


def _pair_others(a, b, borders):
    """Competitor borders excluding one pair's own portions."""
    return [o for o in borders
            if o["key"] != (a["contour"], a["seg"], a["t0"], a["t1"])
            and o["key"] != (b["contour"], b["seg"], b["t0"], b["t1"])]


def _strict_overlap(first, second):
    """Any remaining contact between certified cores is conflict.

    Trimming already removed the uncertainty neighborhoods, so only
    strictly separated foot ranges keep; overlap or touch fails
    closed as double ownership rather than guessing a boundary.
    """
    return not (first[1] < second[0] or second[1] < first[0])


def _resolve_interval(combos, skipped, borders, loops):
    """Interval-level ownership over certified interval cores.

    Each combo's kept intervals are clipped away from arithmetic
    uncertainty neighborhoods and rechecked; ownership compares the
    trimmed foot ranges with strict separation. Disjoint cores are
    both kept and the joint solver owns shared vertices once, while
    any overlap, touch, or uncertain evaluation drops its combos.
    """
    feet, bad = [], set()
    for pos, combo in enumerate(combos):
        seg_a = (tuple(combo["a"]["p0"]), tuple(combo["a"]["p1"]))
        seg_b = (tuple(combo["b"]["p0"]), tuple(combo["b"]["p1"]))
        others = _pair_others(combo["a"], combo["b"], borders)
        core = intervals.core_intervals(seg_a, seg_b,
                                        combo["dom"]["intervals"],
                                        others, loops)
        ranges = intervals.foot_ranges(seg_a, seg_b, core) \
            if core else None
        if ranges is None:
            bad.add(pos)
            skipped.append({"pair": (combo["a"]["seg"],
                                     combo["b"]["seg"]),
                            "reason": "foot-uncertain"})
            feet.append(None)
            continue
        trimmed = dict(combo["dom"])
        trimmed["intervals"] = core
        combo["dom"] = trimmed
        feet.append(ranges)
    claimants = {}
    for pos, combo in enumerate(combos):
        for side in (combo["a"], combo["b"]):
            key = (side["contour"], side["seg"], side["t0"], side["t1"])
            claimants.setdefault(key, []).append(pos)
    drop = set(bad)
    for key, members in claimants.items():
        for x in range(len(members)):
            for y in range(x + 1, len(members)):
                px, py = members[x], members[y]
                if px in bad or py in bad:
                    continue
                flank = ("a" if (combos[px]["a"]["contour"],
                                 combos[px]["a"]["seg"],
                                 combos[px]["a"]["t0"],
                                 combos[px]["a"]["t1"]) == key else "b")
                other = ("a" if (combos[py]["a"]["contour"],
                                  combos[py]["a"]["seg"],
                                  combos[py]["a"]["t0"],
                                  combos[py]["a"]["t1"]) == key else "b")
                clash = any(_strict_overlap(rx[flank], ry[other])
                            for rx in feet[px] for ry in feet[py])
                if clash:
                    drop.add(px)
                    drop.add(py)
    pairs = []
    for pos, combo in enumerate(combos):
        if pos in drop:
            if pos not in bad:
                skipped.append({"pair": (combo["a"]["seg"],
                                         combo["b"]["seg"]),
                                "reason": "ambiguous-portion"})
            continue
        xs = [combo["a"]["p0"][0], combo["a"]["p1"][0],
              combo["b"]["p0"][0], combo["b"]["p1"][0]]
        ys = [combo["a"]["p0"][1], combo["a"]["p1"][1],
              combo["b"]["p0"][1], combo["b"]["p1"][1]]
        pairs.append({"a": combo["a"], "b": combo["b"],
                      "dom": combo["dom"], "feet": feet[pos],
                      "box": (min(xs), min(ys), max(xs), max(ys))})
    return pairs, skipped


def _recognize(portions, loops, ownership="portion"):
    """Opposing visible border portions with certified ink intervals.

    Every portion pair with open corridor overlap is tested; frame
    opposition and dominance clearance decide. Portion ownership
    drops every pair sharing a whole portion; interval ownership
    drops only provably overlapping contact-foot ranges. Unknown
    winding never certifies: such portions are neither paired nor
    trusted as competitors.
    """
    visible = [p for p in portions
               if not p["hidden"] and not p["unknown"]]
    borders = _visible_borders(portions)
    combos, skipped = [], []
    for i in range(len(visible)):
        for j in range(i + 1, len(visible)):
            a, b = visible[i], visible[j]
            seg_a = (tuple(a["p0"]), tuple(a["p1"]))
            seg_b = (tuple(b["p0"]), tuple(b["p1"]))
            cor = intervals.corridor(seg_a, seg_b)
            if cor is None:
                continue
            frame = intervals.frame(seg_a, seg_b, cor)
            if frame["status"] != "ok":
                skipped.append({"pair": (a["seg"], b["seg"]),
                                "reason": "opposition-" + frame["status"]})
                continue
            others = _pair_others(a, b, borders)
            dom = intervals.dominance(seg_a, seg_b, others, loops)
            if dom["status"] != "ok" or not dom["intervals"]:
                skipped.append({"pair": (a["seg"], b["seg"]),
                                "reason": "no-dominance-" + dom["status"]})
                continue
            combos.append({"a": a, "b": b, "dom": dom})
    if ownership == "interval":
        return _resolve_interval(combos, skipped, borders, loops)
    use = {}
    for combo in combos:
        for side in (combo["a"], combo["b"]):
            key = (side["contour"], side["seg"], side["t0"], side["t1"])
            use[key] = use.get(key, 0) + 1
    pairs = []
    for combo in combos:
        keys = [(combo["a"]["contour"], combo["a"]["seg"],
                 combo["a"]["t0"], combo["a"]["t1"]),
                (combo["b"]["contour"], combo["b"]["seg"],
                 combo["b"]["t0"], combo["b"]["t1"])]
        if any(use[k] > 1 for k in keys):
            skipped.append({"pair": (combo["a"]["seg"], combo["b"]["seg"]),
                            "reason": "ambiguous-portion"})
            continue
        xs = [combo["a"]["p0"][0], combo["a"]["p1"][0],
              combo["b"]["p0"][0], combo["b"]["p1"][0]]
        ys = [combo["a"]["p0"][1], combo["a"]["p1"][1],
              combo["b"]["p0"][1], combo["b"]["p1"][1]]
        pairs.append({"a": combo["a"], "b": combo["b"],
                      "dom": combo["dom"],
                      "box": (min(xs), min(ys), max(xs), max(ys))})
    return pairs, skipped


STATION_FRACS = (0.25, 0.5, 0.75)


def _longest_kept(dom):
    spans = dom.get("intervals") or []
    if not spans:
        return None
    return max(spans, key=lambda iv: iv["hi"] - iv["lo"])


def _station_contacts(seg_a, seg_b, dom, others, loops):
    """Certified width stations over the longest kept interval.

    Stations sit strictly inside one open dominance interval, so only
    open interval interiors are sampled; every sampled disk is
    rechecked with full competitor clearance. A missing contact
    abstains the pair instead of interpolating across the gap. For
    straight pairs center and radius are affine, so symmetric
    stations reproduce the center value exactly.
    """
    span = _longest_kept(dom)
    if span is None or not span["hi"] > span["lo"]:
        return None
    out = []
    for frac in STATION_FRACS:
        s = span["lo"] + (span["hi"] - span["lo"]) * frac
        seen = intervals.contact(seg_a, seg_b, s, others, loops)
        if seen.get("status") != "ok" or seen.get("hit") is None:
            return None
        out.append({"s": s, "hit": seen["hit"]})
    return out


def _index_map(commands):
    """Oncurve index to owning command, mirroring parse_commands.

    parse_commands counts oncurve points only; offcurve controls take
    no oncurve index, so quad and curve commands advance one step.
    """
    table = {}
    n = 0
    for pos, cmd in enumerate(commands):
        if cmd["op"] in ("move_to", "line_to", "quad_to", "curve_to"):
            table[n] = pos
            n += 1
    return table


def _edge_point(side, frac, coords):
    """Portion-fraction point: edge fraction t0+(t1-t0)*frac.

    Virtual cut parameters keep exact affine correspondence to the
    original edge endpoints; ignoring the cuts would misplace every
    interior station foot.
    """
    t = side["t0"] + (side["t1"] - side["t0"]) * frac
    p0 = coords[side["i0"]]
    p1 = coords[side["i1"]]
    return (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)


def _affine_sample(side, t):
    """Fixed affine correspondence to original edge endpoints."""
    return Sample(((side["i0"], 1.0 - t), (side["i1"], t)))


def _upright_pairs(pairs):
    """Vertical rectilinear opposing pairs; exact equality decides.

    Uniform scaling maps equal design coordinates through the same
    float operation, so design-vertical stays bit-exact vertical.
    Horizontal bars (serifs, caps) are excluded from the standard:
    they are not the upright reference even when rectilinear.
    """
    out = []
    for pair in pairs:
        a, b = pair["a"], pair["b"]
        if _axis_of(a["p0"], a["p1"]) == "x" and \
                _axis_of(b["p0"], b["p1"]) == "x":
            out.append(pair)
    return out


def _others_for(pair, borders):
    return _pair_others(pair["a"], pair["b"], borders)


def build_reference(records, size_px):
    """Font-wide upright anchor list from source and fitted pairs.

    The caller groups records by font, axes, size and hint mode. Each
    vertical rectilinear pair contributes its source width, fitted
    width measured directly on the fitted outline through exact op
    correspondence, relative change, arc length, tangent and source
    identity. No medians across different features: the fit couples
    every diagonal station to every anchor through its own (17) row.
    No analysis files or glyph names are read.
    """
    anchors = []
    notes = []
    seen = 0
    for num, record in enumerate(records):
        try:
            src_cmds = record["source_commands"]
            fit_cmds = record["fitted_commands"]
        except (KeyError, TypeError, AttributeError):
            notes.append({"record": num, "reason": "missing-commands"})
            continue
        if not check_correspondence(src_cmds, fit_cmds):
            notes.append({"record": num, "reason": "no-correspondence"})
            continue
        seen += 1
        parsed = parse_commands(src_cmds)
        fitted = parse_commands(fit_cmds)["oncurve"]
        portions, _, loops, _ = _split_visible(parsed)
        pairs, _ = _recognize(portions, loops)
        borders = _visible_borders(portions)
        for pair in _upright_pairs(pairs):
            a, b = pair["a"], pair["b"]
            seg_a = (tuple(a["p0"]), tuple(a["p1"]))
            seg_b = (tuple(b["p0"]), tuple(b["p1"]))
            cor = intervals.corridor(seg_a, seg_b)
            if cor is None:
                continue
            stations = _station_contacts(seg_a, seg_b, pair["dom"],
                                         _others_for(pair, borders),
                                         loops)
            if stations is None:
                notes.append({"record": num,
                              "reason": "unmeasurable-anchor"})
                continue
            src = [st["hit"]["width"] for st in stations]
            fit = []
            for st in stations:
                qa = _edge_point(a, st["hit"]["sa"], fitted)
                qb = _edge_point(b, st["hit"]["sb"], fitted)
                fit.append(abs(qb[0] - qa[0]))
            src_mean = sum(src) / len(src)
            fit_mean = sum(fit) / len(fit)
            if not src_mean > 0:
                continue
            span = _longest_kept(pair["dom"])
            anchors.append({
                "source_width": src_mean,
                "fitted_width": fit_mean,
                "rel": fit_mean / src_mean - 1.0,
                "length": span["hi"] - span["lo"],
                "tangent": list(cor["d"]),
                "source_ids": "r%d:c%da(%d,%.4f,%.4f)/b(%d,%.4f,%.4f)"
                % (num, a["contour"], a["seg"], a["t0"], a["t1"],
                   b["seg"], b["t0"], b["t1"])})
    rels = [an["rel"] for an in anchors]
    return {"anchors": anchors, "size_px": size_px,
            "records": seen, "n_anchors": len(anchors),
            "rel_min": min(rels) if rels else None,
            "rel_max": max(rels) if rels else None,
            "notes": notes}


def _inked(center, straight_loops, curve_flats):
    """Ink test at a station center: nonzero, certified, or neither.

    White (counter) pairs need an explicit separate black/white
    model, so only ink pairs proceed; uncertified queries abstain
    rather than guessing the fill.
    """
    w = _certified_winding(center, straight_loops, curve_flats)
    if w is None:
        return None
    return w != 0


def _prepare_pair(pair, borders, loops, straights, flats, curves,
                  fitted_coords, size_px, exact_curves=None):
    """Certified stations and source frame for one diagonal pair."""
    a, b = pair["a"], pair["b"]
    if _axis_of(a["p0"], a["p1"]) is not None or \
            _axis_of(b["p0"], b["p1"]) is not None:
        return None, "rectilinear-side"
    seg_a = (tuple(a["p0"]), tuple(a["p1"]))
    seg_b = (tuple(b["p0"]), tuple(b["p1"]))
    cor = intervals.corridor(seg_a, seg_b)
    if cor is None:
        return None, "no-corridor"
    direction = cor["d"]
    if direction[0] == 0.0 or direction[1] == 0.0:
        return None, "axis-degenerate"
    stations = _station_contacts(seg_a, seg_b, pair["dom"],
                                 _others_for(pair, borders), loops)
    if stations is None:
        return None, "station-uncertified"
    if exact_curves is not None:
        helper = _helper()
        if helper is None or not hasattr(helper, "disk_clear"):
            return None, "curve-helper-unavailable"
        try:
            clear = all(helper.disk_clear(
                tuple(st["hit"]["center"]), st["hit"]["r"],
                ctrls)[0]
                for st in stations for ctrls in exact_curves)
        except Exception:
            return None, "curve-helper-unavailable"
        if not clear:
            return None, "curved-neighbor"
    elif _near_curves(pair, stations, curves):
        return None, "curved-neighbor"
    mid = stations[len(stations) // 2]["hit"]
    normal = cor["u"]
    side = ((mid["qb"][0] - mid["qa"][0]) * normal[0]
            + (mid["qb"][1] - mid["qa"][1]) * normal[1])
    if side == 0.0:
        return None, "degenerate-projection"
    orient = 1.0 if side > 0 else -1.0
    normal = (normal[0] * orient, normal[1] * orient)
    ink = _inked(mid["center"], straights, flats)
    if ink is None:
        return None, "winding-uncertain-center"
    if not ink:
        return None, "white-pair"
    src_widths = [st["hit"]["width"] for st in stations]
    fit_a = [_edge_point(a, st["hit"]["sa"], fitted_coords)
             for st in stations]
    fit_b = [_edge_point(b, st["hit"]["sb"], fitted_coords)
             for st in stations]
    fit_widths = [abs((qb[0] - qa[0]) * normal[0]
                      + (qb[1] - qa[1]) * normal[1])
                  for qa, qb in zip(fit_a, fit_b)]
    span = _longest_kept(pair["dom"])
    return {"id": "a(%d,%d,%.6f,%.6f)/b(%d,%d,%.6f,%.6f)" % (
                a["contour"], a["seg"], a["t0"], a["t1"],
                b["contour"], b["seg"], b["t0"], b["t1"]),
            "a": a, "b": b, "direction": direction, "normal": normal,
            "stations": stations, "src_widths": src_widths,
            "fit_widths": fit_widths,
            "arc": (span["hi"] - span["lo"]) / len(stations),
            "interval": span}, None


def _acute(tangent, other):
    """Acute meeting angle: spine order carries no orientation."""
    if float(np.dot(tangent, other)) < 0:
        return -np.asarray(tangent, dtype=float)
    return np.asarray(tangent, dtype=float)


def _eliminate(rows, fixed, nvars):
    """Per-coordinate fixed-column elimination (System.solve form)."""
    free = np.array([2 * i + c for i in range(nvars)
                     for c in (0, 1) if (i, c) not in fixed], dtype=int)
    if not rows:
        return (np.zeros((0, 2 * nvars)), np.zeros(0), free)
    matrix = np.array([row for _, row, _ in rows])
    constants = np.array([c for _, _, c in rows])
    order = sorted(fixed)
    cols = np.array([2 * v + a for v, a in order], dtype=int)
    vals = np.array([fixed[k] for k in order])
    if len(cols):
        constants = constants + matrix[:, cols] @ vals
    return matrix, constants, free


def _solve_constrained(soft, hard, fixed, nvars):
    """Exact hard rows via SVD particular plus nullspace least squares.

    The particular solution carries the hard constraints; source
    shape and (17) coupling run in the nullspace. Rank follows the
    NumPy singular-value convention; a hard residual outside the
    relative band means inconsistent constraints, never a guess.
    Without hard rows this is plain minimum-norm least squares.
    """
    soft_m, soft_c, free = _eliminate(soft, fixed, nvars)
    hard_m, hard_c, _ = _eliminate(hard, fixed, nvars)
    loose = np.zeros(2 * nvars)
    for (v, axis), value in fixed.items():
        loose[2 * v + axis] = value
    if hard_m.shape[0]:
        mat = hard_m[:, free]
        rhs = -hard_c
        eye = np.finfo(float).eps
        if not len(free):
            particular = np.zeros(0)
            resid = float(np.linalg.norm(rhs, np.inf))
            rank = 0
            null = np.zeros((0, 0))
        else:
            # Full Vt: the economy factor drops the nullspace when
            # the hard rows underdetermine the free variables.
            U, sig, Vt = np.linalg.svd(mat, full_matrices=True)
            rank = int((sig > sig[0] * max(mat.shape) * eye).sum()) \
                if sig[0] > 0 else 0
            coef = (U[:, :rank].T @ rhs) / sig[:rank]
            particular = Vt[:rank].T @ coef
            resid = float(np.linalg.norm(mat @ particular - rhs, np.inf))
            null = Vt[rank:].T
        if resid > 1e-9 * max(1.0, float(np.linalg.norm(rhs, np.inf))):
            return None
        if null.shape[1]:
            want = -soft_c - soft_m[:, free] @ particular
            alpha, _, _, _ = np.linalg.lstsq(soft_m[:, free] @ null,
                                             want, rcond=None)
            free_x = particular + null @ alpha
        else:
            free_x = particular
    else:
        if not len(free):
            free_x = np.zeros(0)
        else:
            free_x, _, _, _ = np.linalg.lstsq(soft_m[:, free], -soft_c,
                                              rcond=None)
    loose[free] = free_x
    return loose


def _assemble(parsed, fitted_coords, prepped, anchors_ref, size_px,
              grid, pins, native_axes):
    """Joint system: source shape, (17) anchor rows, grid hard rows.

    Coefficients come from the source outline with the upstream gap
    substituted into geometry constants, so shape residuals vanish at
    upstream. Every diagonal station couples to every reference
    anchor through its own (17) row weighted by arc products and the
    published angular weights. Grid hard rows fix border parallelism
    and integer line separation per pair. Pins hold anchors and
    native-owned components at their upstream gap.
    """
    nvars = len(parsed["oncurve"])
    system = System([tuple(p) for p in parsed["oncurve"]], size_px)
    var_verts = set()
    for info in prepped:
        var_verts.add(info["a"]["i0"])
        var_verts.add(info["a"]["i1"])
        var_verts.add(info["b"]["i0"])
        var_verts.add(info["b"]["i1"])
    ring = set()
    for contour in parsed["contours"]:
        for seg in contour:
            if seg[0] != "line":
                continue
            if seg[1] in var_verts or seg[2] in var_verts:
                ring.add((seg[1], seg[2]))
    for (i, j) in sorted(ring):
        try:
            system.edge(i, j)
        except ValueError:
            continue
    base = np.asarray(parsed["oncurve"], dtype=float)
    upstream = np.asarray(fitted_coords, dtype=float)
    shift = (upstream - base).ravel()
    reshaped = []
    for group, row, const in system.rows:
        if group in ("position", "stretch", "bend"):
            const = const - float(np.asarray(row) @ shift)
        reshaped.append((group, row, const))
    system.rows = reshaped
    pairs = []
    for info in prepped:
        station_pairs = []
        try:
            for st in info["stations"]:
                ta = info["a"]["t0"] + (info["a"]["t1"]
                                        - info["a"]["t0"]) * st["hit"]["sa"]
                tb = info["b"]["t0"] + (info["b"]["t1"]
                                        - info["b"]["t0"]) * st["hit"]["sb"]
                station_pairs.append(system.pair(
                    _affine_sample(info["a"], ta),
                    _affine_sample(info["b"], tb),
                    info["arc"], "ink", medial=st["hit"]["center"]))
        except ValueError:
            station_pairs = None
        pairs.append(station_pairs)
    for info, station_pairs in zip(prepped, pairs):
        if station_pairs is None:
            continue
        info["pairs"] = station_pairs
        for pair, st in zip(station_pairs, info["stations"]):
            for anchor in anchors_ref:
                run_tangent = np.asarray(pair.tangent, dtype=float)
                ref_tangent = np.asarray(anchor["tangent"], dtype=float)
                if float(np.dot(run_tangent, ref_tangent)) < 0:
                    run_tangent = -run_tangent
                psi = width_weight(pair.width, anchor["source_width"],
                                   run_tangent, ref_tangent, size_px)
                weight = info["arc"] * anchor["length"] * psi
                system.add("ink-match", pair.error * math.sqrt(weight),
                           anchor["rel"] * math.sqrt(weight))
    hard = []
    for info, station_pairs in zip(prepped, pairs):
        info["grid_rows"] = []
        if station_pairs is None:
            continue
        if not grid:
            continue
        gate = _grid_target(info, anchors_ref, size_px)
        if gate is None:
            continue
        info["gate"] = gate
        n = info["normal"]
        a, b = info["a"], info["b"]
        rows = [
            (system.projected(_affine_sample(a, a["t1"]), n,
                              _affine_sample(a, a["t0"])), 0.0),
            (system.projected(_affine_sample(b, b["t1"]), n,
                              _affine_sample(b, b["t0"])), 0.0),
        ]
        ta = a["t0"] + (a["t1"] - a["t0"]) * gate["fa"]
        tb = b["t0"] + (b["t1"] - b["t0"]) * gate["fb"]
        rows.append((system.projected(_affine_sample(b, tb), n,
                                      _affine_sample(a, ta)),
                     gate["w_src"] - gate["target"]))
        info["grid_rows"] = rows
        hard.extend(rows)
    fixed = {}
    gaps = (upstream - base)
    for v in pins:
        fixed[(v, 0)] = float(gaps[v][0])
        fixed[(v, 1)] = float(gaps[v][1])
    for v in var_verts:
        for axis in native_axes:
            fixed[(v, axis)] = float(gaps[v][axis])
    far = set()
    for contour in parsed["contours"]:
        for seg in contour:
            if seg[0] != "line":
                continue
            if seg[1] in var_verts and seg[2] not in var_verts:
                far.add(seg[2])
            if seg[2] in var_verts and seg[1] not in var_verts:
                far.add(seg[1])
    for v in far:
        for axis in (0, 1):
            if (v, axis) not in fixed:
                fixed[(v, axis)] = float(gaps[v][axis])
    return system, hard, fixed, gaps, var_verts


def _grid_target(info, anchors_ref, size_px):
    """Integer line separation from the coupled normal width.

    The weighted anchor mean gives the coupled relative change; the
    integer counts axis units of line separation, so the normal
    target divides by the axis normal component. Line separation
    between parallel borders is normal width over that component,
    never the contact-chord projection. The axis rule keeps the
    component above sqrt(2)/2 by construction.
    """
    widths = info["src_widths"]
    mean = sum(widths) / len(widths)
    if max(widths) - min(widths) > GRID_SPREAD / math.sqrt(max(widths)):
        return None
    direction = info["direction"]
    axis = 0 if abs(direction[1]) >= abs(direction[0]) else 1
    n_axis = info["normal"][axis]
    if n_axis == 0.0:
        return None
    num, den = 0.0, 0.0
    for anchor in anchors_ref:
        tangent = _acute(info["direction"], anchor["tangent"])
        psi = width_weight(mean, anchor["source_width"], tangent,
                           _acute(anchor["tangent"], info["direction"]),
                           size_px)
        w = anchor["length"] * psi
        num += w * anchor["rel"]
        den += w
    if den == 0.0:
        return None
    coupled = mean * (1.0 + num / den)
    # Deterministic nearest integer, ties to even (Python round).
    integer = int(round(coupled / abs(n_axis)))
    if integer <= 0:
        return None
    mid = info["stations"][len(info["stations"]) // 2]["hit"]
    return {"axis": ("x" if axis == 0 else "y"),
            "integer": integer,
            "target": integer * abs(n_axis),
            "coupled": coupled,
            "rel": num / den,
            "w_src": (info["normal"][0] * (mid["qb"][0] - mid["qa"][0])
                      + info["normal"][1] * (mid["qb"][1] - mid["qa"][1])),
            "fa": mid["sa"], "fb": mid["sb"]}


def _abstain(fitted_commands, reason, **extra):
    """Fail closed: the exact upstream commands, never a candidate."""
    result = {"candidate_commands": fitted_commands,
              "applied": False, "reason": reason,
              "pairs": [], "widths": None, "phase_applied": False}
    result.update(extra)
    return result


def _commands_equal(first, second):
    """Exact per-command equality; applied needs actual change."""
    if len(first) != len(second):
        return False
    return all(a == b for a, b in zip(first, second))


def _loops_points(parsed):
    """Vertex loops for orientation; curves share one flattening."""
    oncurve, offcurve = parsed["oncurve"], parsed["offcurve"]
    loops = []
    for contour in parsed["contours"]:
        loop = []
        for seg in contour:
            pts = _flatten_seg(seg, oncurve, offcurve)
            loop.extend(pts[:-1] if loop else pts)
        loop.append(loop[0])
        loops.append(loop)
    return loops


def _curve_sweep_ok(parsed, fitted, candidate, ctrls):
    """Swept straight-border homotopy against fixed curves.

    Hersch moves only straight borders while curves stay fixed, so
    only changed straight segments sweep; pinned and untouched
    geometry is bit-identical and needs no homotopy. The helper
    certifies each sweep against every fixed curve; its absence or
    failure fails closed.
    """
    helper = _helper()
    if helper is None or not hasattr(helper, "movement_clear"):
        return False, "curve-helper-unavailable"
    try:
        up = fitted["oncurve"]
        cand = parse_commands(candidate)["oncurve"]
        old_segs, new_segs = [], []
        for contour in parsed["contours"]:
            for seg in contour:
                if seg[0] != "line":
                    continue
                old = (tuple(up[seg[1]]), tuple(up[seg[2]]))
                new = (tuple(cand[seg[1]]), tuple(cand[seg[2]]))
                if old != new:
                    old_segs.append(old)
                    new_segs.append(new)
        ok, reason = helper.movement_clear(old_segs, new_segs, ctrls)
        return (True, "clear") if ok else (False, reason)
    except Exception:
        return False, "curve-helper-unavailable"


def fit_glyph(source_commands, fitted_commands, size_px, reference,
              native_axes=(False, False), grid=False, topology_checker=None,
              curve_clearance=False):
    """Fit diagonal pairs of one glyph; exact upstream on abstention.

    The joint system couples every diagonal station to every
    reference anchor through (17) rows while source shape rows hold
    the outline; shared vertices carry one unknown. Grid mode adds
    hard parallel and integer-separation rows per pair. Native-owned
    components and upright anchors stay at upstream exactly. The
    candidate rounds moved coordinates to 26.6 and must preserve
    orientation signs, upstream portion topology and station ink, or
    the exact upstream commands return with the validity evidence.
    Curve mode is opt-in: canonical discovery, exact disk clearance
    against fixed curves, swept homotopy and a harness-supplied
    curve-capable topology wrapper, with no sampled fallback.
    """
    try:
        if not check_correspondence(source_commands, fitted_commands):
            return _abstain(fitted_commands, "no-correspondence")
        parsed = parse_commands(source_commands)
        fitted = parse_commands(fitted_commands)
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        return _abstain(fitted_commands, "malformed-commands")
    anchors_ref = reference.get("anchors") if isinstance(reference,
                                                         dict) else None
    if not anchors_ref:
        return _abstain(fitted_commands, "no-reference-anchors")
    try:
        portions, _, loops, flats = _split_visible(
            parsed, canonical=curve_clearance)
        # Diagonal fitting owns shared borders at interval resolution;
        # upright discovery in build_reference keeps portion ownership
        # so frozen reference anchors cannot change with this slice.
        pairs, skipped = _recognize(portions, loops,
                                    ownership="interval")
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        return _abstain(fitted_commands, "malformed-commands")
    straights = loops
    curves = flats
    exact_curves = _curve_controls(parsed) if curve_clearance else None
    pins = set()
    for pair in _upright_pairs(pairs):
        for side in (pair["a"], pair["b"]):
            pins.add(side["i0"])
            pins.add(side["i1"])
    # An oncurve endpoint incident to any curve is owned by that
    # curve as well; moving it would deform a region this slice
    # cannot certify, so it stays at upstream like an anchor.
    for contour in parsed["contours"]:
        for seg in contour:
            if seg[0] == "line":
                continue
            pins.add(seg[-2])
            pins.add(seg[-1])
    owned = tuple(i for i, on in enumerate(native_axes[:2]) if on)
    borders = _visible_borders(portions)
    fitted_coords = fitted["oncurve"]
    prepped, details = [], list(skipped)
    for pair in pairs:
        if _upright_pairs([pair]):
            details.append({"pair": (pair["a"]["seg"], pair["b"]["seg"]),
                            "reason": "upright-anchor"})
            continue
        try:
            info, why = _prepare_pair(pair, borders, loops, straights,
                                      flats, curves, fitted_coords,
                                      size_px,
                                      exact_curves=exact_curves)
        except (ValueError, ArithmeticError):
            details.append({"pair": (pair["a"]["seg"], pair["b"]["seg"]),
                            "reason": "pair-invalid"})
            continue
        if why is not None:
            details.append({"pair": (pair["a"]["seg"], pair["b"]["seg"]),
                            "reason": why})
            continue
        bound = min(info["src_widths"]) / 2 - HEADROOM
        if not bound >= HEADROOM:
            details.append({"pair": info["id"],
                            "reason": "movement-budget-empty"})
            continue
        info["bound"] = bound
        info["feet"] = pair.get("feet")
        prepped.append(info)
    if not prepped:
        return _abstain(fitted_commands, "all-abstained",
                        skipped=details,
                        fixed={"anchors": sorted(pins),
                               "native_axes": list(native_axes[:2])})
    if curve_clearance and topology_checker is None:
        return _abstain(fitted_commands, "no-curve-topology",
                        skipped=details,
                        fixed={"anchors": sorted(pins),
                               "native_axes": list(native_axes[:2])})
    system, hard, fixed, gaps, var_verts = _assemble(
        parsed, fitted_coords, prepped, anchors_ref, size_px, grid,
        pins, owned)
    soft = [(g, np.asarray(r, dtype=float), float(c))
            for g, r, c in system.rows]
    hard_all = [(np.asarray(r, dtype=float), float(c)) for r, c in hard]
    flex = _solve_constrained(soft,
                              [("hard", r, c) for r, c in hard_all],
                              fixed, len(parsed["oncurve"]))
    declined = []
    if flex is None:
        if grid and hard_all:
            declined = [info["id"] for info in prepped
                        if info.get("grid_rows")]
            for info in prepped:
                info["grid_rows"] = []
                info.pop("gate", None)
            hard_all = []
            flex = _solve_constrained(
                soft, [], fixed, len(parsed["oncurve"]))
            details.append({"reason": "grid-infeasible",
                            "declined": list(declined)})
        if flex is None:
            return _abstain(fitted_commands, "inconsistent-constraints",
                            skipped=details,
                            fixed={"anchors": sorted(pins),
                                   "native_axes": list(native_axes[:2])})
    base = np.asarray(parsed["oncurve"], dtype=float)
    upstream = np.asarray(fitted_coords, dtype=float)
    gaps = upstream - base
    deltas = (base + flex.reshape(-1, 2)) - upstream
    peaks = {}
    for info in prepped:
        verts = {info["a"]["i0"], info["a"]["i1"],
                 info["b"]["i0"], info["b"]["i1"]}
        peaks[info["id"]] = max(
            [float(np.linalg.norm(deltas[v])) for v in verts] + [0.0])
    over = [pid for pid, peak in peaks.items()
            if peak > next(i["bound"] for i in prepped
                           if i["id"] == pid)]
    if over and not grid:
        scale = min(next(i["bound"] for i in prepped if i["id"] == pid)
                    / peaks[pid] for pid in over)
        deltas = deltas * scale
        for info in prepped:
            info["prefix"] = scale
    elif over:
        dropped = [info for info in prepped
                   if info["id"] in over and info.get("grid_rows")]
        if dropped:
            for info in dropped:
                declined.append(info["id"])
                info["grid_rows"] = []
                info.pop("gate", None)
                details.append({"pair": info["id"],
                                "reason": "grid-over-budget"})
            hard_all = [(r, c) for info in prepped
                        for r, c in info.get("grid_rows", [])]
            flex = _solve_constrained(
                soft, [("hard", r, c) for r, c in hard_all],
                fixed, len(parsed["oncurve"]))
            if flex is None:
                return _abstain(fitted_commands,
                                "inconsistent-constraints",
                                skipped=details,
                                fixed={"anchors": sorted(pins),
                                       "native_axes": list(native_axes[:2])})
            deltas = (base + flex.reshape(-1, 2)) - upstream
            for info in prepped:
                verts = {info["a"]["i0"], info["a"]["i1"],
                         info["b"]["i0"], info["b"]["i1"]}
                peaks[info["id"]] = max(
                    [float(np.linalg.norm(deltas[v])) for v in verts]
                    + [0.0])
            over = [pid for pid, peak in peaks.items()
                    if peak > next(i["bound"] for i in prepped
                                   if i["id"] == pid)]
        if over:
            return _abstain(fitted_commands, "movement-budget",
                            skipped=details + [{"pair": pid,
                                                "reason": "over-budget"}
                                               for pid in over],
                            fixed={"anchors": sorted(pins),
                                   "native_axes": list(native_axes[:2])})
    for info in prepped:
        info.setdefault("prefix", 1.0)
        info["peak"] = peaks[info["id"]]
    table = _index_map(fitted_commands)
    candidate = [dict(cmd) for cmd in fitted_commands]
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
            rounded = _round_26_6(value)
            key = "x" if axis == 0 else "y"
            candidate[pos][key] = rounded
            if key + "_bits" in candidate[pos]:
                candidate[pos][key + "_bits"] = _f32bits(rounded)
    if _commands_equal(candidate, fitted_commands):
        fallback = _achieved(prepped, fitted_commands, fitted_coords)
        widths = [(p["source_width"], p["upstream_width"],
                   p["candidate_width"]) for p in fallback]
        return {
            "candidate_commands": fitted_commands,
            "applied": False, "reason": "no-movement",
            "validity": {"ok": True, "stage": "zero-change"},
            "pairs": fallback, "skipped": details,
            "declined_grid": declined,
            "phase_applied": False,
            "fixed": {"anchors": sorted(pins),
                      "native_axes": list(native_axes[:2])},
            "movement": 0.0,
            "bound": min(i["bound"] for i in prepped),
            "size_px": size_px, "grid": grid,
            "widths": {
                "source": sum(w[0] for w in widths) / len(widths),
                "upstream": sum(w[1] for w in widths) / len(widths),
                "candidate": sum(w[2] for w in widths) / len(widths)},
            "reference": {"n_anchors": len(anchors_ref),
                          "rel_min": min(a["rel"] for a in anchors_ref),
                          "rel_max": max(a["rel"] for a in anchors_ref)}}
    validity = _validate(parsed, fitted, fitted_commands, candidate,
                         portions, prepped, pins, owned, grid,
                         hard_all, flex, source_commands, topology_checker,
                         canonical=curve_clearance)
    if curve_clearance and validity["ok"]:
        # The sweep runs upstream to candidate, so it certifies
        # against the actual fitted fixed curves; source controls
        # remain the right reference for source station recognition.
        sweep_ok, sweep_reason = _curve_sweep_ok(
            parsed, fitted, candidate, _curve_controls(fitted))
        validity["curve_sweep"] = sweep_reason
        if not sweep_ok:
            validity["ok"] = False
            validity["stage"] = sweep_reason
    match_rows = [(np.asarray(r, dtype=float), float(c))
                  for g, r, c in system.rows if g == "ink-match"]
    flat_base_up = upstream.ravel() - base.ravel()
    try:
        flat_base_cand = (np.asarray(parse_commands(candidate)["oncurve"],
                                     dtype=float).ravel()
                          - base.ravel())
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        flat_base_cand = None
    cost_upstream = float(sum((float(row @ flat_base_up) + const) ** 2
                              for row, const in match_rows))
    cost_candidate = float(sum((float(row @ flat_base_cand) + const) ** 2
                               for row, const in match_rows)) \
        if flat_base_cand is not None else None
    validity["cost_upstream"] = cost_upstream
    validity["cost_candidate"] = cost_candidate
    if not grid:
        validity["cost_ok"] = (cost_candidate is not None
                               and cost_candidate < cost_upstream)
        if not validity["cost_ok"]:
            validity["ok"] = False
            validity["stage"] = "no-cost-decrease"
    hard_ok = bool(validity.get("hard_rounded_ok"))
    for info in prepped:
        info["phase_applied"] = bool(
            grid and info.get("gate") is not None
            and info.get("grid_rows") and hard_ok)
    phase_any = any(info["phase_applied"] for info in prepped)
    achieved = _achieved(prepped, candidate, fitted_coords)
    widths = [(p["source_width"], p["upstream_width"],
               p["candidate_width"]) for p in achieved]
    if not validity["ok"]:
        fallback = _achieved(prepped, fitted_commands, fitted_coords)
        for entry in fallback:
            entry["phase_applied"] = False
        widths = [(p["source_width"], p["upstream_width"],
                   p["candidate_width"]) for p in fallback]
        tried = [(p["source_width"], p["upstream_width"],
                  p["candidate_width"]) for p in achieved]
        attempt = {"attempted_commands": candidate,
                   "movement": max(peaks.values()) if peaks else 0.0,
                   "widths": {
                       "source": sum(w[0] for w in tried) / len(tried),
                       "upstream": sum(w[1] for w in tried) / len(tried),
                       "candidate": sum(w[2] for w in tried)
                       / len(tried)},
                   "pairs": achieved,
                   "validity": validity}
        result = {
            "candidate_commands": fitted_commands,
            "applied": False, "reason": "invalid-candidate",
            "validity": validity, "pairs": fallback,
            "skipped": details, "declined_grid": declined,
            "phase_applied": False, "attempt": attempt,
            "fixed": {"anchors": sorted(pins),
                      "native_axes": list(native_axes[:2])},
            "movement": 0.0,
            "bound": min(i["bound"] for i in prepped),
            "size_px": size_px, "grid": grid,
            "widths": {
                "source": sum(w[0] for w in widths) / len(widths),
                "upstream": sum(w[1] for w in widths) / len(widths),
                "candidate": sum(w[2] for w in widths) / len(widths)},
            "reference": {
                "n_anchors": len(anchors_ref),
                "rel_min": min(a["rel"] for a in anchors_ref),
                "rel_max": max(a["rel"] for a in anchors_ref)}}
        return result
    reason = "applied"
    if grid and not phase_any:
        reason = "applied-width-only"
    result = {
        "candidate_commands": candidate,
        "applied": True,
        "reason": reason,
        "validity": validity, "pairs": achieved, "skipped": details,
        "declined_grid": declined,
        "phase_applied": phase_any if grid else False,
        "fixed": {"anchors": sorted(pins),
                  "native_axes": list(native_axes[:2])},
        "movement": max(peaks.values()) if peaks else 0.0,
        "bound": min(i["bound"] for i in prepped),
        "size_px": size_px, "grid": grid,
        "widths": {
            "source": sum(w[0] for w in widths) / len(widths),
            "upstream": sum(w[1] for w in widths) / len(widths),
            "candidate": sum(w[2] for w in widths) / len(widths)},
        "reference": {"n_anchors": len(anchors_ref),
                      "rel_min": min(a["rel"] for a in anchors_ref),
                      "rel_max": max(a["rel"] for a in anchors_ref)}}
    return result


def _topology_signature(portions):
    return tuple((p["contour"], p["seg"], p["hidden"]) for p in portions)


def _validate(parsed, fitted, fitted_commands, candidate, portions,
              prepped, pins, owned, grid, hard_all, flex,
              source_commands=None, topology_checker=None,
              canonical=False):
    """Post-rounding gates; any failure rejects the whole glyph."""
    try:
        cand = parse_commands(candidate)
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        return {"ok": False, "stage": "unparseable-candidate"}
    evidence = {}
    evidence["ops"] = check_correspondence(fitted_commands, candidate)
    before = _signed_areas(_loops_points(fitted))
    after = _signed_areas(_loops_points(cand))
    evidence["orientation"] = [
        (1 if b > 0 else (-1 if b < 0 else 0))
        == (1 if a > 0 else (-1 if a < 0 else 0))
        for a, b in zip(before, after)]
    up = fitted
    cand_portions, _, _, cand_flats = _split_visible(
        cand, canonical=canonical)
    up_portions, _, up_loops, up_flats = _split_visible(
        up, canonical=canonical)
    split_match = (_topology_signature(cand_portions)
                   == _topology_signature(up_portions))
    evidence["split_topology"] = split_match
    evidence["topology_mode"] = "strict_signature"
    evidence["topology"] = split_match
    if topology_checker is not None:
        # The isolated exact arrangement replaces only the split-signature
        # gate. Ownership, correspondence, movement and ink checks stay joint.
        evidence["topology_mode"] = "exact_arrangement"
        try:
            report = topology_checker(source_commands, fitted_commands,
                                      candidate)
        except Exception as exc:
            report = {"supported": False, "ok": False,
                      "reason": "checker-exception", "error": str(exc)}
        evidence["exact_topology"] = report
        evidence["topology"] = (isinstance(report, dict)
                                and report.get("supported") is True
                                and report.get("ok") is True)
    table = _index_map(candidate)
    exact = True
    for v in pins:
        pos = table.get(v)
        if pos is None:
            continue
        if candidate[pos]["x"] != fitted["oncurve"][v][0] or \
                candidate[pos]["y"] != fitted["oncurve"][v][1]:
            exact = False
    inverted = {pos: idx for idx, pos in table.items()}
    for pos, cmd in enumerate(candidate):
        idx = inverted.get(pos)
        if idx is None:
            continue
        for axis in owned:
            key = "x" if axis == 0 else "y"
            if key in cmd and cmd[key] != fitted["oncurve"][idx][axis]:
                exact = False
    evidence["pins_exact"] = exact
    centers = True
    for info in prepped:
        mid = info["stations"][len(info["stations"]) // 2]["hit"]
        qa = _edge_point(info["a"], mid["sa"],
                         cand["oncurve"])
        qb = _edge_point(info["b"], mid["sb"],
                         cand["oncurve"])
        center = ((qa[0] + qb[0]) / 2, (qa[1] + qb[1]) / 2)
        wc = _certified_winding(center, _loops_points(cand),
                                cand_flats)
        ua = _edge_point(info["a"], mid["sa"], fitted["oncurve"])
        ub = _edge_point(info["b"], mid["sb"], fitted["oncurve"])
        ucenter = ((ua[0] + ub[0]) / 2, (ua[1] + ub[1]) / 2)
        wu = _certified_winding(ucenter, _loops_points(up), up_flats)
        if wc is None or wu is None or wc == 0 or wc != wu:
            centers = False
    evidence["centers_inked"] = centers
    peak_ok = True
    for info in prepped:
        verts = {info["a"]["i0"], info["a"]["i1"],
                 info["b"]["i0"], info["b"]["i1"]}
        peak = 0.0
        for v in verts:
            pos = table.get(v)
            if pos is None:
                continue
            peak = max(peak, math.hypot(
                candidate[pos]["x"] - fitted["oncurve"][v][0],
                candidate[pos]["y"] - fitted["oncurve"][v][1]))
        info["rounded_peak"] = peak
        if not peak <= info["bound"] + HEADROOM:
            peak_ok = False
    evidence["movement_ok"] = peak_ok
    hard_ideal, hard_rounded = [], []
    if grid and hard_all:
        cand_coords = np.asarray(cand["oncurve"], dtype=float)
        base = np.asarray(parsed["oncurve"], dtype=float)
        flat_ideal = np.asarray(flex, dtype=float).ravel() \
            if flex is not None else None
        flat_round = (cand_coords - base).ravel()
        for row, const in hard_all:
            ideal = float(np.asarray(row) @ flat_ideal + const) \
                if flat_ideal is not None else None
            hard_ideal.append(ideal)
            hard_rounded.append(float(np.asarray(row) @ flat_round
                                      + const))
        evidence["hard_rounded_ok"] = all(
            abs(v) <= 2 * HEADROOM for v in hard_rounded)
    else:
        evidence["hard_rounded_ok"] = True
    evidence["hard_ideal"] = hard_ideal
    evidence["hard_rounded"] = hard_rounded
    ok = (evidence["ops"] and all(evidence["orientation"])
          and evidence["topology"] and evidence["pins_exact"]
          and evidence["centers_inked"] and evidence["movement_ok"]
          and evidence["hard_rounded_ok"])
    return {"ok": ok, **evidence}


def _achieved(prepped, candidate, fitted_coords):
    """Measured post-rounding widths, separations and residuals."""
    cand = parse_commands(candidate)["oncurve"]
    out = []
    for info in prepped:
        normal = info["normal"]
        src, ups, got = [], [], []
        for k, st in enumerate(info["stations"]):
            sa, sb = st["hit"]["sa"], st["hit"]["sb"]
            qa = _edge_point(info["a"], sa, cand)
            qb = _edge_point(info["b"], sb, cand)
            got.append(abs((qb[0] - qa[0]) * normal[0]
                           + (qb[1] - qa[1]) * normal[1]))
            src.append(info["src_widths"][k])
            ups.append(info["fit_widths"][k])
        entry = {"id": info["id"], "interval": info["interval"],
                 "feet": info.get("feet"),
                 "stations": info["stations"] and
                 [st["s"] for st in info["stations"]],
                 "source_width": sum(src) / len(src),
                 "upstream_width": sum(ups) / len(ups),
                 "candidate_width": sum(got) / len(got),
                 "bound": info["bound"], "prefix": info["prefix"],
                 "peak": info["peak"],
                 "rounded_peak": info.get("rounded_peak"),
                 "phase_applied": bool(info.get("phase_applied")),
                 "grid": None}
        gate = info.get("gate")
        if gate is not None:
            n = normal
            axis = 0 if gate["axis"] == "x" else 1
            mid = info["stations"][len(info["stations"]) // 2]["hit"]
            qa = _edge_point(info["a"], mid["sa"], cand)
            qb = _edge_point(info["b"], mid["sb"], cand)
            width = abs((qb[0] - qa[0]) * n[0]
                        + (qb[1] - qa[1]) * n[1])
            entry["grid"] = {
                "axis": gate["axis"], "integer": gate["integer"],
                "coupled": gate["coupled"], "rel": gate["rel"],
                "achieved_sep": width / abs(n[axis]),
                "sep_residual": width / abs(n[axis]) - gate["integer"],
                "target_width": gate["target"]}
        out.append(entry)
    return out
