"""Real-outline straight-stroke coupling with an upstream-fitted anchor.

Hobby (4) defines width as twice the medial radius; (5) measures signed
projected relative width error. Contacts are restricted segment-Voronoi
dominance intervals, Hobby (3.2): the pair bisector is affine in the
overlap parameter, split at open foot bounds, positive radius,
competitor projection endpoints and quadratic equality events; only
open interiors are sampled and every disk is rechecked. The pair
representative feeds recognition; every related station couples with
every anchor station, Hobby (17), by arc-length products. Hobby (3.3)
integer adjustment motivates the anchor: source opposite parallel
axis-aligned sides whose fitted boundaries are integral on the same
axis. Anchor and unowned vertices carry fixed upstream displacements;
only related vertices move, bounded by half the source local width.
Curve, corner and multi-contour input abstains; one edge yields one
pair and exact score ties abstain rather than resolve arbitrarily.
Vertex-dominated cells and parabolic branches are unsupported.
"""

import json
import math
import struct

import numpy as np

from experiments.hobby_fitting import intervals
from experiments.hobby_fitting.prototype import Sample, System


def parse_commands(commands):
    """Split TrueType-style commands into contours of indexed segments."""
    oncurve, offcurve = [], []
    contours = []
    current, start = [], None

    def idx(pt):
        oncurve.append((float(pt[0]), float(pt[1])))
        return len(oncurve) - 1

    def cidx(pt):
        offcurve.append((float(pt[0]), float(pt[1])))
        return len(offcurve) - 1

    pen = None
    for cmd in commands:
        op = cmd["op"]
        if op == "move_to":
            if current:
                contours.append(current)
            current = []
            pen = idx((cmd["x"], cmd["y"]))
            start = pen
        elif op == "line_to":
            nxt = idx((cmd["x"], cmd["y"]))
            current.append(("line", pen, nxt))
            pen = nxt
        elif op == "quad_to":
            c = cidx((cmd["x1"], cmd["y1"]))
            nxt = idx((cmd["x"], cmd["y"]))
            current.append(("quad", c, pen, nxt))
            pen = nxt
        elif op == "curve_to":
            c1 = cidx((cmd["x1"], cmd["y1"]))
            c2 = cidx((cmd["x2"], cmd["y2"]))
            nxt = idx((cmd["x"], cmd["y"]))
            current.append(("cubic", c1, c2, pen, nxt))
            pen = nxt
        elif op == "close":
            if pen is not None and start is not None and pen != start:
                current.append(("line", pen, start))
            if current:
                contours.append(current)
            current, pen, start = [], None, None
    if current:
        contours.append(current)
    return {"oncurve": oncurve, "offcurve": offcurve, "contours": contours}


def loops_parsed(parsed, coords=None):
    """Vertex loops; the slice admits straight segments only."""
    oc = coords if coords is not None else parsed["oncurve"]
    loops = []
    for contour in parsed["contours"]:
        loop = []
        for seg in contour:
            if seg[0] != "line":
                return None
            if not loop:
                loop.append(oc[seg[1]])
            loop.append(oc[seg[2]])
        if loop and loop[0] == loop[-1]:
            loop.pop()
        loops.append(loop)
    return loops


def winding_number(pt, loops):
    """Nonzero winding test on straight loops; no curve flattening."""
    x, y = pt
    total = 0
    for loop in loops:
        a = loop[-1]
        for b in loop:
            if (a[1] <= y) != (b[1] <= y):
                xi = a[0] + (y - a[1]) / (b[1] - a[1]) * (b[0] - a[0])
                if xi > x:
                    total += 1 if b[1] > a[1] else -1
            a = b
    return total


def _straight_edges(parsed):
    edges = []
    for ci, contour in enumerate(parsed["contours"]):
        for si, seg in enumerate(contour):
            if seg[0] == "line":
                p0 = parsed["oncurve"][seg[1]]
                p1 = parsed["oncurve"][seg[2]]
                d = (p1[0] - p0[0], p1[1] - p0[1])
                length = math.hypot(*d)
                if length > 0:
                    edges.append({"contour": ci, "seg": si,
                                  "i0": seg[1], "i1": seg[2],
                                  "p0": p0, "p1": p1,
                                  "dir": (d[0] / length, d[1] / length),
                                  "length": length})
    return edges


def _borders(oncurve, contours, skip):
    """Every other straight border with an opaque tag for third contact."""
    others = []
    for ci, contour in enumerate(contours):
        for si, seg in enumerate(contour):
            if (ci, si) in skip or seg[0] != "line":
                continue
            others.append({"seg": (tuple(oncurve[seg[1]]),
                                   tuple(oncurve[seg[2]])),
                           "tag": "edge(%d,%d)" % (ci, si)})
    return others


def _pair_dominance(a, b, oncurve, contours, loops):
    """Dominance intervals against all other borders, pair excluded."""
    skip = {(a["contour"], a["seg"]), (b["contour"], b["seg"])}
    return intervals.dominance((tuple(a["p0"]), tuple(a["p1"])),
                               (tuple(b["p0"]), tuple(b["p1"])),
                               _borders(oncurve, contours, skip), loops)


def _pair_angle(a, b):
    """Corridor direction angle of a border pair, for head-angle evidence."""
    cor = intervals.corridor((tuple(a["p0"]), tuple(a["p1"])),
                             (tuple(b["p0"]), tuple(b["p1"])))
    if cor is None:
        return None
    return math.atan2(cor["d"][1], cor["d"][0])


def _sample_weights(edge, s):
    return ((edge["i0"], 1 - s), (edge["i1"], s))


def _representative(a, b, oncurve, contours, loops):
    """Longest dominance interval midpoint contact represents the pair.

    Recognition keeps pairs with at least one open interval; the longest
    span is the deterministic geometric representative, never selected
    by output pixels.
    """
    dom = _pair_dominance(a, b, oncurve, contours, loops)
    if dom["status"] != "ok" or not dom["intervals"]:
        return None, dom
    span = max(dom["intervals"], key=lambda s: s["hi"] - s["lo"])
    mid = (span["lo"] + span["hi"]) / 2
    skip = {(a["contour"], a["seg"]), (b["contour"], b["seg"])}
    out = intervals.contact((tuple(a["p0"]), tuple(a["p1"])),
                            (tuple(b["p0"]), tuple(b["p1"])), mid,
                            _borders(oncurve, contours, skip), loops)
    if out["hit"] is None:
        return None, dom
    return out["hit"], dom


def _sample_point(pts, contact):
    (i0, w0), (i1, w1) = contact
    return (pts[i0][0] * w0 + pts[i1][0] * w1,
            pts[i0][1] * w0 + pts[i1][1] * w1)


def _pair_ids(s):
    return {(s["a"]["contour"], s["a"]["seg"]),
            (s["b"]["contour"], s["b"]["seg"])}


def recognize(parsed):
    """Automatic dominance-interval pairing on the straight slice.

    A pair survives only with at least one open dominance interval;
    the longest interval midpoint represents it. Any border shared by
    surviving pairs is ambiguous ownership, never a greedy choice.
    """
    if len(parsed["contours"]) != 1:
        return {"pairs": [], "diagnostics": [], "ambiguous": [],
                "reason": "multi-contour"}
    for contour in parsed["contours"]:
        for seg in contour:
            if seg[0] != "line":
                return {"pairs": [], "diagnostics": [], "ambiguous": [],
                        "reason": "unsupported-curves"}
    oncurve = parsed["oncurve"]
    contours = parsed["contours"]
    loops = loops_parsed(parsed)
    if _proper_crossings(loops) != 0:
        return {"pairs": [], "diagnostics": [], "ambiguous": [],
                "reason": "self-intersecting"}
    edges = _straight_edges(parsed)
    scored = []
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            a, b = edges[i], edges[j]
            if {a["i0"], a["i1"]} & {b["i0"], b["i1"]}:
                continue
            rep, dom = _representative(a, b, oncurve, contours, loops)
            if rep is None:
                continue
            chord = (rep["qa"][0] - rep["qb"][0],
                     rep["qa"][1] - rep["qb"][1])
            dist = math.hypot(*chord)
            if dist == 0:
                continue
            scored.append({"a": a, "b": b, "rep": rep, "dom": dom,
                           "width": rep["width"],
                           "normal": (chord[0] / dist, chord[1] / dist),
                           "ca": _sample_weights(a, rep["sa"]),
                           "cb": _sample_weights(b, rep["sb"])})
    pairs, used, ambiguous = [], set(), []
    for s in scored:
        ids = _pair_ids(s)
        if ids & used:
            ambiguous.append({"edges": sorted(ids)})
            pairs = [p for p in pairs if not (_pair_ids(p) & ids)]
            used = set().union(*[_pair_ids(p) for p in pairs]) if pairs \
                else set()
            continue
        used |= ids
        pairs.append(s)
    diagnostics = [{"width": s["width"],
                    "span": sum(iv["hi"] - iv["lo"]
                               for iv in s["dom"]["intervals"]),
                    "status": s["dom"]["status"],
                    "edge_a": (s["a"]["i0"], s["a"]["i1"]),
                    "edge_b": (s["b"]["i0"], s["b"]["i1"])} for s in scored]
    return {"pairs": pairs, "diagnostics": diagnostics,
            "ambiguous": ambiguous, "reason": None}


def check_correspondence(source_cmds, fitted_cmds):
    """Identical op sequences contour by contour; identity is the contract."""
    def ops(cmds):
        seq, cur = [], []
        for cmd in cmds:
            if cmd["op"] == "move_to":
                if cur:
                    seq.append(tuple(cur))
                cur = []
            cur.append(cmd["op"])
            if cmd["op"] == "close":
                seq.append(tuple(cur))
                cur = []
        if cur:
            seq.append(tuple(cur))
        return seq
    return ops(source_cmds) == ops(fitted_cmds)


def _axis(edge):
    """Constant axis of a source side; None when not axis-aligned."""
    if edge["p0"][0] == edge["p1"][0]:
        return "x"
    if edge["p0"][1] == edge["p1"][1]:
        return "y"
    return None


def select_anchor(recognition, source_parsed, fitted_coords):
    """Anchor is a proven grid-aligned rectilinear pair, Hobby (3.3).

    Source opposite parallel axis-aligned sides with fitted boundaries
    integral on the same axis. Multiple incompatible anchors abstain;
    the slant is never an anchor by least-disturbance.
    """
    eligible = []
    for cand in recognition["pairs"]:
        a, b = cand["a"], cand["b"]
        if _axis(a) is None or _axis(a) != _axis(b):
            continue
        axis = _axis(a)
        verts = (a["i0"], a["i1"], b["i0"], b["i1"])
        vals = [fitted_coords[v][0 if axis == "x" else 1] for v in verts]
        if not all(float(v).is_integer() for v in vals):
            continue
        eligible.append(cand)
    if not eligible:
        return {"anchor": None, "reason": "no-rectilinear-anchor"}
    if len(eligible) > 1:
        return {"anchor": None, "reason": "multiple-anchors",
                "candidates": len(eligible)}
    cand = eligible[0]
    normal = cand["normal"]
    ws = cand["width"]
    fa = _sample_point(fitted_coords, cand["ca"])
    fb = _sample_point(fitted_coords, cand["cb"])
    # Target anchor error along the source normal, Hobby (5) numerator.
    wf = (fa[0] - fb[0]) * normal[0] + (fa[1] - fb[1]) * normal[1]
    return {"anchor": cand, "ws": ws, "wf": wf, "rel": (wf - ws) / ws,
            "reason": None}


def _oncurve_coords(commands):
    pts = []
    for cmd in commands:
        if cmd["op"] in ("move_to", "line_to"):
            pts.append((float(cmd["x"]), float(cmd["y"])))
        elif cmd["op"] in ("quad_to", "curve_to"):
            pts.append((float(cmd["x"]), float(cmd["y"])))
    return pts


def _proper_crossings(loops):
    """Count proper segment crossings; shared endpoints are not crossings."""
    segs = []
    for loop in loops:
        n = len(loop)
        for i in range(n):
            segs.append((tuple(loop[i]), tuple(loop[(i + 1) % n])))

    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def proper(p1, p2, p3, p4):
        if len({p1, p2, p3, p4}) < 4:
            return False
        o1, o2 = orient(p1, p2, p3), orient(p1, p2, p4)
        o3, o4 = orient(p3, p4, p1), orient(p3, p4, p2)
        return ((o1 > 0) != (o2 > 0)) and ((o3 > 0) != (o4 > 0))
    return sum(1 for i in range(len(segs)) for j in range(i + 1, len(segs))
               if proper(segs[i][0], segs[i][1], segs[j][0], segs[j][1]))


def _signed_areas(loops):
    areas = []
    for loop in loops:
        n = len(loop)
        areas.append(sum(loop[i][0] * loop[(i + 1) % n][1]
                         - loop[(i + 1) % n][0] * loop[i][1]
                         for i in range(n)) / 2)
    return areas


def _round_26_6(x):
    """Nearest 1/64 unit, ties toward positive infinity: scanner convention."""
    return math.floor(x * 64 + 0.5) / 64


def _f32bits(x):
    """Float32 bit pattern matching the capture *_bits convention."""
    return struct.unpack(">I", struct.pack(">f", x))[0]


def run_glyph(source_cmds, fitted_cmds, size_px, geometry_reference="upstream",
              stations=3):
    """Couple related strokes to the upstream-fitted rectilinear anchor.

    geometry_reference selects the position-reference adaptation. The
    upstream arm is the proposed post-fit correction; the source arm is
    the negative control. Unknown references are rejected, not guessed.
    stations counts the equal thirds sampled per dominance interval;
    3 is the production count and 6/12 are geometric convergence
    controls, never selected by output pixels.
    """
    if geometry_reference not in ("source", "upstream"):
        raise ValueError("geometry_reference must be source or upstream")
    if not isinstance(stations, int) or stations < 1:
        raise ValueError("stations must be a positive integer")
    if not check_correspondence(source_cmds, fitted_cmds):
        return {"applied": False, "reason": "no-correspondence",
                "geometry_reference": geometry_reference}
    parsed = parse_commands(source_cmds)
    recognition = recognize(parsed)
    if recognition["reason"] is not None:
        return {"applied": False, "reason": recognition["reason"],
                "geometry_reference": geometry_reference,
                "diagnostics": recognition["diagnostics"]}
    if recognition["ambiguous"]:
        return {"applied": False, "reason": "ambiguous-pairing",
                "geometry_reference": geometry_reference,
                "diagnostics": recognition["diagnostics"],
                "ambiguous": recognition["ambiguous"]}
    fitted_coords = _oncurve_coords(fitted_cmds)
    if len(fitted_coords) != len(parsed["oncurve"]):
        return {"applied": False, "reason": "no-correspondence",
                "geometry_reference": geometry_reference}
    anchor_sel = select_anchor(recognition, parsed, fitted_coords)
    if anchor_sel["anchor"] is None:
        return {"applied": False, "reason": anchor_sel["reason"],
                "geometry_reference": geometry_reference,
                "diagnostics": recognition["diagnostics"]}
    anchor = anchor_sel["anchor"]
    anchor_verts = {anchor["a"]["i0"], anchor["a"]["i1"],
                    anchor["b"]["i0"], anchor["b"]["i1"]}
    related = [s for s in recognition["pairs"] if s is not anchor and
               {s["a"]["i0"], s["a"]["i1"], s["b"]["i0"], s["b"]["i1"]}
               & anchor_verts]
    if not related:
        return {"applied": False, "reason": "no-related-pair",
                "geometry_reference": geometry_reference,
                "anchor": {"ws": anchor_sel["ws"], "wf": anchor_sel["wf"],
                           "rel": anchor_sel["rel"]}}
    # System base is all-source; fixed upstream displacements join the
    # constants later, after coupling decides which vertices stay owned.
    base = [list(p) for p in parsed["oncurve"]]
    base_arr = np.asarray(base, dtype=float)
    upstream = np.asarray(fitted_coords, dtype=float)
    system = System(base, size_px)
    for contour in parsed["contours"]:
        for seg in contour:
            if seg[0] == "line":
                system.edge(seg[1], seg[2])
    if geometry_reference == "upstream":
        # Post-fit position reference adaptation of Hobby (1)-(3): all
        # source coefficients stay fixed, but geometry residuals vanish
        # at the upstream fit instead of the unhinted source. Width
        # coupling rows added below keep source-frame zero. Base point
        # constant formula, no mixed geometry in coefficients.
        upstream = np.asarray(fitted_coords, dtype=float)
        shift = (upstream - np.asarray(base, dtype=float)).ravel()
        reshaped = []
        for group, row, const in system.rows:
            if group in ("position", "stretch", "bend"):
                const = const - float(row @ shift)
            reshaped.append((group, row, const))
        system.rows = reshaped
    # Stations are equal thirds of every dominance interval: open
    # interior midpoints with rechecked disks, arc weights from the
    # sub-interval length times the medial speed. Hobby (17) couples
    # every related station with every anchor station, each row
    # weighted by the product of its own arc lengths.
    sub = stations
    fractions = tuple((j + 0.5) / sub for j in range(sub))
    src_loops = loops_parsed(parsed)
    oncurve = parsed["oncurve"]
    contours = parsed["contours"]

    def collect(pair):
        """Sampled stations with arc lengths, or the failing records."""
        hits, failed = [], []
        dom = pair["dom"]
        speed = dom["speed"] or 0.0
        skip = {(pair["a"]["contour"], pair["a"]["seg"]),
                (pair["b"]["contour"], pair["b"]["seg"])}
        seg_a = (tuple(pair["a"]["p0"]), tuple(pair["a"]["p1"]))
        seg_b = (tuple(pair["b"]["p0"]), tuple(pair["b"]["p1"]))
        others = _borders(oncurve, contours, skip)
        for ivl in dom["intervals"]:
            span = ivl["hi"] - ivl["lo"]
            for f in fractions:
                t = ivl["lo"] + f * span
                out = intervals.contact(seg_a, seg_b, t, others, src_loops)
                if out["hit"] is None:
                    failed.append({"t": t, "stage": out["stage"],
                                   "tag": out["tag"]})
                    continue
                arc = span / sub * speed
                if not arc > 0:
                    failed.append({"t": t, "stage": "degenerate-arc",
                                   "tag": None})
                    continue
                hits.append({"hit": out["hit"], "arc": arc, "t": t})
        return hits, failed

    def station_pair(pair, entry):
        hit = entry["hit"]
        return system.pair(Sample(_sample_weights(pair["a"], hit["sa"])),
                           Sample(_sample_weights(pair["b"], hit["sb"])),
                           entry["arc"], kind="ink",
                           medial=hit["center"])

    anchor_hits, anchor_failed = collect(anchor)
    if anchor_failed or not anchor_hits:
        return {"applied": False, "reason": "station-invalid-anchor",
                "geometry_reference": geometry_reference,
                "failed_stations": anchor_failed}
    anchor_pairs = [station_pair(anchor, e) for e in anchor_hits]
    coupled, skipped = [], []
    for rel in related:
        hits, failed = collect(rel)
        if failed or not hits:
            skipped.append({"pair_edges": [(rel["a"]["i0"], rel["a"]["i1"]),
                                           (rel["b"]["i0"], rel["b"]["i1"])],
                            "failed_stations": failed})
            continue
        for entry in hits:
            here = station_pair(rel, entry)
            for anc in anchor_pairs:
                system.match_width(here, anc)
        coupled.append((rel, hits))
    if not coupled:
        return {"applied": False, "reason": "station-invalid-related",
                "geometry_reference": geometry_reference,
                "skipped_related": skipped}
    # Anchor and unowned vertices carry fixed upstream displacements;
    # only coupled related vertices move. The base stays all-source.
    related = [rel for rel, _ in coupled]
    rel_verts = {v for r in related for v in
                 (r["a"]["i0"], r["a"]["i1"], r["b"]["i0"], r["b"]["i1"])}
    owned = anchor_verts | rel_verts
    fixed = {v: (float(upstream[v][0] - base_arr[v][0]),
                 float(upstream[v][1] - base_arr[v][1]))
             for v in range(len(base)) if v in anchor_verts or v not in rel_verts}
    # Narrowest retained sample 2r bounds every move; the unconstrained
    # optimum is scaled from upstream by the feasible prefix, never
    # re-solved under a constraint. Headroom reserves the worst 26.6
    # rounding step so the bound also holds after quantization.
    retained = [e["hit"]["width"] for e in anchor_hits]
    retained += [e["hit"]["width"] for _, hits in coupled for e in hits]
    bound = 0.5 * min(retained)
    solved = system.solve(fixed_displacements=fixed)
    optimum = base_arr + solved["delta"].reshape(-1, 2)
    free = sorted(set(range(len(base))) - set(fixed))
    dev = [math.hypot(optimum[v][0] - upstream[v][0],
                       optimum[v][1] - upstream[v][1]) for v in free]
    maxdev = max(dev) if dev else 0.0
    headroom = math.sqrt(2.0) / 128.0
    available = bound - headroom
    prefix = 1.0 if maxdev == 0 else max(0.0, min(1.0, available / maxdev))
    cand_float = [list(map(float, upstream[v])) for v in range(len(base))]
    for v in free:
        step = prefix * (optimum[v] - upstream[v])
        cand_float[v] = [float(upstream[v][0] + step[0]),
                         float(upstream[v][1] + step[1])]
    movement_float = max([math.hypot(cand_float[v][0] - upstream[v][0],
                                     cand_float[v][1] - upstream[v][1])
                          for v in free]) if free else 0.0
    cand_rounded = [[_round_26_6(x), _round_26_6(y)] for x, y in cand_float]
    rounding = max(math.hypot(c[0] - r[0], c[1] - r[1])
                   for c, r in zip(cand_float, cand_rounded))
    movement = max([math.hypot(cand_rounded[v][0] - fitted_coords[v][0],
                               cand_rounded[v][1] - fitted_coords[v][1])
                    for v in rel_verts]) if rel_verts else 0.0
    vertex_movement = {str(v): math.hypot(
        cand_rounded[v][0] - fitted_coords[v][0],
        cand_rounded[v][1] - fitted_coords[v][1]) for v in sorted(rel_verts)}
    # The weighted width-coupling cost must strictly decrease versus
    # upstream on the quantized output, independent of any pixels.
    match_rows = [(row, const) for group, row, const in system.rows
                  if group == "ink-match"]

    def match_cost(coords):
        flat = (np.asarray(coords, dtype=float) - base_arr).ravel()
        return float(sum((float(row @ flat) + const) ** 2
                         for row, const in match_rows))

    cost_upstream = match_cost(upstream)
    cost_candidate = match_cost(np.asarray(cand_rounded, dtype=float))
    if movement > bound:
        return {"applied": False, "reason": "movement-bound-exceeded",
                "geometry_reference": geometry_reference,
                "movement": movement, "movement_float": movement_float,
                "bound": bound, "vertex_movement": vertex_movement,
                "prefix": prefix, "cost_upstream": cost_upstream,
                "cost_candidate": cost_candidate}
    if not cost_candidate < cost_upstream:
        return {"applied": False, "reason": "no-cost-decrease",
                "geometry_reference": geometry_reference,
                "movement": movement, "movement_float": movement_float,
                "bound": bound, "vertex_movement": vertex_movement,
                "prefix": prefix, "cost_upstream": cost_upstream,
                "cost_candidate": cost_candidate}
    out = [dict(c) for c in source_cmds]
    k = 0
    for cmd in out:
        if cmd["op"] in ("move_to", "line_to"):
            cmd["x"], cmd["y"] = cand_rounded[k]
            k += 1
        elif cmd["op"] in ("quad_to", "curve_to"):
            cmd["x"], cmd["y"] = cand_rounded[k]
            k += 1
    for cmd in out:
        for key in ("x", "y", "x1", "y1", "x2", "y2"):
            if key in cmd:
                cmd[key + "_bits"] = _f32bits(cmd[key])
    cand_parsed = parse_commands(out)
    cand_loops = loops_parsed(cand_parsed, cand_rounded)
    cand_float_loops = loops_parsed(cand_parsed, cand_float)
    src_areas = _signed_areas(src_loops)
    cand_areas = _signed_areas(cand_loops)
    float_areas = _signed_areas(cand_float_loops)
    signs_ok = all((a > 0) == (b > 0) and abs(a) > 0
                   for a, b in zip(src_areas, cand_areas))
    crossings_ok = _proper_crossings(cand_loops) == _proper_crossings(src_loops)
    contained_ok = True
    for i, loop in enumerate(src_loops):
        for j, other in enumerate(src_loops):
            if i != j and winding_number(loop[0], [other]) != 0:
                if winding_number(cand_loops[i][0], [cand_loops[j]]) == 0:
                    contained_ok = False
    validity = {"signs": signs_ok, "crossings": crossings_ok,
                "containment": contained_ok, "rounding": rounding}
    float_ok = (all((a > 0) == (b > 0) and abs(a) > 0
                    for a, b in zip(src_areas, float_areas))
                and _proper_crossings(cand_float_loops)
                == _proper_crossings(src_loops))
    validity_float = {"areas": float_ok, "crossings": float_ok}
    if not (signs_ok and crossings_ok and contained_ok and float_ok):
        return {"applied": False, "reason": "validity-failed",
                "geometry_reference": geometry_reference,
                "validity": validity, "validity_float": validity_float,
                "movement": movement, "bound": bound,
                "candidate_commands": out}
    fit_table = _edges_from_coords(fitted_coords, parsed["contours"])
    cand_table = _edges_from_coords(cand_rounded, parsed["contours"])
    fit_loops = loops_parsed(parsed, fitted_coords)
    cand_loops = loops_parsed(parsed, cand_rounded)
    widths, pair_records = [], []
    for r, hits in coupled:
        ka = (r["a"]["contour"], r["a"]["seg"])
        kb = (r["b"]["contour"], r["b"]["seg"])
        normal = r["normal"]
        a = _sample_point(cand_float, r["ca"])
        b = _sample_point(cand_float, r["cb"])
        w_float = (a[0] - b[0]) * normal[0] + (a[1] - b[1]) * normal[1]
        c = _sample_point(cand_rounded, r["ca"])
        dpt = _sample_point(cand_rounded, r["cb"])
        w_round = (c[0] - dpt[0]) * normal[0] + (c[1] - dpt[1]) * normal[1]
        expected = r["width"] * anchor_sel["wf"] / anchor_sel["ws"]
        wf = _width_in(r, fitted_coords, normal)
        widths.append({"ws": r["width"], "wf_upstream": wf,
                       "expected": expected, "candidate_float": w_float,
                       "candidate_rounded": w_round,
                       "upstream_rel": (wf - r["width"]) / r["width"],
                       "candidate_rel": (w_round - r["width"]) / r["width"],
                       "target_rel": anchor_sel["rel"]})
        stations_ev = []
        for e in hits:
            wf_s, wf_stage = _width_at(fit_table, fit_loops, ka, kb, e["t"])
            wc_s, wc_stage = _width_at(cand_table, cand_loops, ka, kb,
                                       e["t"])
            stations_ev.append({"t": e["t"], "ws": e["hit"]["width"],
                                "wf": wf_s, "wc": wc_s,
                                "wf_stage": wf_stage,
                                "wc_stage": wc_stage})
        pair_records.append({
            "edges": [[r["a"]["i0"], r["a"]["i1"]],
                      [r["b"]["i0"], r["b"]["i1"]]],
            "source_angle": _pair_angle(r["a"], r["b"]),
            "fitted_angle": _angle_of(fit_table[ka], fit_table[kb]),
            "intervals": [{"lo": iv["lo"], "hi": iv["hi"]}
                          for iv in r["dom"]["intervals"]],
            "spans": [{"f0": s["f0"], "f1": s["f1"], "kept": s["kept"],
                       "stage": s["stage"], "tag": s["tag"]}
                      for s in r["dom"]["spans"]],
            "stations": stations_ev})
    anchor_record = {"ws": anchor_sel["ws"], "wf": anchor_sel["wf"],
                     "rel": anchor_sel["rel"],
                     "intervals": [{"lo": iv["lo"], "hi": iv["hi"]}
                                   for iv in anchor["dom"]["intervals"]],
                     "spans": [{"f0": s["f0"], "f1": s["f1"],
                                "kept": s["kept"], "stage": s["stage"],
                                "tag": s["tag"]}
                               for s in anchor["dom"]["spans"]]}
    return {"applied": True, "reason": None, "widths": widths,
            "anchor": anchor_record,
            "pairs": pair_records,
            "movement": movement, "movement_float": movement_float,
            "bound": bound, "validity": validity,
            "validity_float": validity_float,
            "geometry_reference": geometry_reference,
            "fixed": sorted(fixed), "rank": solved["rank"],
            "free_variables": solved["free_variables"],
            "residuals": solved["squared_residuals"],
            "prefix": prefix, "cost_upstream": cost_upstream,
            "cost_candidate": cost_candidate,
            "candidate_commands": out}


def _width_in(rel, coords, normal):
    a = _sample_point(coords, rel["ca"])
    b = _sample_point(coords, rel["cb"])
    return (a[0] - b[0]) * normal[0] + (a[1] - b[1]) * normal[1]


def _edges_from_coords(coords, contours):
    """Edge segments in the given coordinates, same border indexing."""
    table = {}
    for ci, contour in enumerate(contours):
        for si, seg in enumerate(contour):
            if seg[0] != "line":
                return None
            table[(ci, si)] = (tuple(coords[seg[1]]), tuple(coords[seg[2]]))
    return table


def _width_at(table, loops, key_a, key_b, t):
    """Contact 2r in the given coordinates, or the failing stage."""
    others = [{"seg": table[k], "tag": "edge(%d,%d)" % k}
              for k in table if k not in (key_a, key_b)]
    out = intervals.contact(table[key_a], table[key_b], t, others, loops)
    if out["hit"] is None:
        return None, out["stage"]
    return out["hit"]["width"], "clear"


def _angle_of(seg_a, seg_b):
    cor = intervals.corridor(seg_a, seg_b)
    if cor is None:
        return None
    return math.atan2(cor["d"][1], cor["d"][0])


def build_report(captures_path, corpus_path=None):
    """Assemble the width report; I/O lives here, not in run_glyph."""
    with open(captures_path) as fh:
        captures = json.load(fh)
    sizes = {}
    for entry in captures:
        size = entry["size_px"] if "size_px" in entry else entry.get("size")
        src = [r for r in entry["source"]["records"] if r["codepoint"] == 49]
        up = [r for r in entry["upstream"]["records"] if r["codepoint"] == 49]
        if not src or not up:
            continue
        arms = {}
        for arm in ("upstream", "source"):
            arms[arm] = run_glyph(src[0]["fitted_commands"],
                                  up[0]["fitted_commands"], size,
                                  geometry_reference=arm)
        sizes[str(size)] = arms
    convergence = {}
    for size in sorted(sizes, key=int):
        entry = [e for e in captures
                 if str(e.get("size_px", e.get("size"))) == str(size)][0]
        src = [r for r in entry["source"]["records"] if r["codepoint"] == 49]
        up = [r for r in entry["upstream"]["records"] if r["codepoint"] == 49]
        runs = {}
        for count in (3, 6, 12):
            try:
                runs[count] = run_glyph(src[0]["fitted_commands"],
                                       up[0]["fitted_commands"], int(size),
                                       geometry_reference="upstream",
                                       stations=count)
            except Exception as error:  # noqa: BLE001 - study, not product
                runs[count] = {"applied": False,
                               "reason": "error:%s" % type(error).__name__}
        verdict = {"counts": {str(c): {"applied": runs[c]["applied"],
                                       "reason": runs[c]["reason"]}
                              for c in (3, 6, 12)}}
        if all(runs[c]["applied"] for c in (3, 6, 12)):
            diffs = {}
            for a, b in ((3, 6), (6, 12)):
                ca = runs[a]["candidate_commands"]
                cb = runs[b]["candidate_commands"]
                diffs["%d-vs-%d" % (a, b)] = max(
                    abs(ca[i].get(k, 0.0) - cb[i].get(k, 0.0))
                    for i in range(len(ca)) for k in ("x", "y")
                    if k in ca[i] or k in cb[i])
            # Raw geometric agreement between station counts; recorded
            # without any claim about output rounding.
            verdict["max_vertex_diff_px"] = diffs
            verdict["all_applied"] = True
        else:
            verdict["all_applied"] = False
        convergence[str(size)] = verdict
    report = {"scope": "real-outline straight-stroke coupling experiment; "
                       "no production change, no optical acceptance",
              "convergence_3_6_12": convergence,
              "method": {"contacts": "segment-Voronoi medial contacts, "
                                     "Hobby (4)(5)",
                         "anchor": "rectilinear source sides with integral "
                                   "fitted boundaries, Hobby (3.3)",
                         "position": "post-fit reference adaptation of "
                                     "Hobby (1)-(3): geometry residuals "
                                     "vanish at upstream; upstream arm is "
                                     "the proposed candidate, source arm "
                                     "the negative control",
                         "coupling": "relative-error matching, Hobby (17), "
                                     "anchor error fixed from upstream fit",
                         "movement": "candidate relative to upstream after "
                                     "26.6 quantization; half narrowest "
                                     "coupled width (adaptation)"},
              "sizes": sizes}
    if corpus_path is not None:
        report["sweep"] = sweep_corpus(corpus_path)
    return report


def sweep_corpus(corpus_path):
    """Full corpus sweep; the solve runs only where recognition finds an
    eligible rectilinear anchor with related strokes. All other glyphs
    abstain with their reason; nothing is forced."""
    with open(corpus_path) as fh:
        corpus = json.load(fh)
    tally = {"glyphs": 0, "applied": 0, "reasons": {}, "applied_glyphs": []}
    for entry in corpus:
        src_recs = {r["codepoint"]: r
                    for r in entry.get("source", {}).get("records", [])}
        for record in entry.get("upstream", {}).get("records", []):
            src_rec = src_recs.get(record["codepoint"])
            if src_rec is None:
                continue
            tally["glyphs"] += 1
            size = entry.get("size", 0)
            try:
                result = run_glyph(src_rec["fitted_commands"],
                                   record["fitted_commands"], size,
                                   geometry_reference="upstream")
            except Exception as error:  # noqa: BLE001 - tally, never crash
                reason = "error:%s" % type(error).__name__
                tally["reasons"][reason] = tally["reasons"].get(reason, 0) + 1
                continue
            if result["applied"]:
                tally["applied"] += 1
                tally["applied_glyphs"].append(
                    {"font": entry.get("font"), "size": size,
                     "codepoint": record["codepoint"],
                     "anchor_rel": result["anchor"]["rel"],
                     "widths": [{k: w[k] for k in
                                 ("ws", "wf_upstream", "expected",
                                  "candidate_rounded", "target_rel")}
                                for w in result["widths"]]})
            else:
                reason = result["reason"]
                tally["reasons"][reason] = tally["reasons"].get(reason, 0) + 1
    return tally


if __name__ == "__main__":
    import sys
    report = build_report(sys.argv[1],
                          sys.argv[2] if len(sys.argv) > 3 else None)
    with open(sys.argv[-1], "w") as fh:
        json.dump(report, fh, indent=1)
