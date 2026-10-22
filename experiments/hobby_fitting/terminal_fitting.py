# cspell:words oncurve offcurve lstsq subpixel Hobby Hersch Shene Sutherland Hodgman

"""Terminal reference-height constraints inside the width solve.

Isolated continuation of the direct-diagonal width prototype: preserve a
source-horizontal supporting cap edge at its original automatic/native
reference height while the existing source-relative width solve runs.
Hersch sections 5-6 supply reference-line phase and diagonal-width control;
Hobby 3.3 supplies common displacement of important horizontal regions. The
project adaptation recognizes a nonzero horizontal straight source edge, with equal
endpoint heights also present upstream, and retains those upstream Y
coordinates while eligible X coordinates join the existing width coupling.
This retains local horizontal reference edges even below a taller ascender.
Curved extrema, ambiguous heights and nonhorizontal source edges create no
constraints. See docs/hobby-fitting.md ("Terminal reference-height
constraints").
"""

import math
import struct

import numpy as np

from experiments.hobby_fitting import curved_width as _curved_width
from experiments.hobby_fitting import direct_diagonal as _dd
from experiments.hobby_fitting.real_outline import (
    check_correspondence,
    parse_commands,
)


def _round_26_6(value):
    # Nearest 1/64 unit; the delivered native grid shared with direct_diagonal.
    return math.floor(value * 64 + 0.5) / 64


def _f32bits(value):
    return struct.unpack(">I", struct.pack(">f", value))[0]


def _abstain(upstream_commands, reason, **extra):
    # Fail closed: the exact upstream commands, never a candidate.
    result = {"candidate_commands": upstream_commands,
              "applied": False, "reason": reason,
              "caps": [], "cap_vertices": [],
              "uprights": [], "upright_vertices": [],
              "pairs": [], "widths": None}
    result.update(extra)
    return result


def detect_caps(raw_source_commands, original_upstream_commands):
    """Source-horizontal reference edges with one existing fitted height.

    An empty outline is a valid font glyph and carries no caps. Returns
    (caps, lo, hi): each cap pins both endpoint Y coordinates to the
    shared upstream height. Hobby 3.3 identifies horizontal regions locally;
    Hersch 5-6 preserve their reference phase during width fitting. Exactly
    horizontal nonzero source lines qualify only when both upstream endpoint
    heights agree. Control-box planes classify diagnostics, not eligibility:
    another stroke extending higher cannot release an interior reference. The implicit
    closing line carries the same vertex indices as its contour endpoints, so
    it is already welded. Raises on malformed commands.
    """
    raw = parse_commands(raw_source_commands)
    fitted = parse_commands(original_upstream_commands)
    points = raw["oncurve"]
    controls = points + raw["offcurve"]
    up = fitted["oncurve"]
    if not controls:
        return [], None, None
    lo = min(p[1] for p in controls)
    hi = max(p[1] for p in controls)
    caps = []
    seen = set()
    for contour in raw["contours"]:
        for seg in contour:
            if seg[0] != "line":
                continue
            i0, i1 = seg[1], seg[2]
            a, b = points[i0], points[i1]
            if a[0] == b[0] or a[1] != b[1]:
                continue
            if up[i0][1] != up[i1][1]:
                continue
            key = (i0, i1, a[1])
            if key in seen:
                continue
            seen.add(key)
            caps.append({"vertices": (i0, i1),
                         "plane": "min" if a[1] == lo else "max" if a[1] == hi else "interior",
                         "source_y": float(a[1]),
                         "upstream_y": float(up[i0][1])})
    return caps, float(lo), float(hi)


def detect_uprights(raw_source_commands, original_upstream_commands):
    """Nonzero vertical straight edges with shared upstream X.

    Hersch sections 5-6 keep upright borders on their reference positions
    while diagonals are width-coupled around them: each endpoint keeps its
    original upstream X while Y stays free for the width solve. Only exact
    raw verticals with equal upstream endpoint X qualify; curves and
    slanted edges create no constraints.
    """
    raw = parse_commands(raw_source_commands)
    fitted = parse_commands(original_upstream_commands)
    points = raw["oncurve"]
    up = fitted["oncurve"]
    found, seen = [], set()
    for contour in raw["contours"]:
        for seg in contour:
            if seg[0] != "line":
                continue
            i0, i1 = seg[1], seg[2]
            a, b = points[i0], points[i1]
            if a[1] == b[1] or a[0] != b[0]:
                continue
            if up[i0][0] != up[i1][0]:
                continue
            key = (i0, i1)
            if key in seen:
                continue
            seen.add(key)
            found.append({"vertices": (i0, i1),
                          "source_x": float(a[0]),
                          "upstream_x": float(up[i0][0])})
    return found


def _valid_anchors(anchors):
    # Finite shape values for the (17) coupling; content outside this is a
    # caller error, never a solved guess.
    for anchor in anchors:
        if not isinstance(anchor, dict):
            return False
        width = anchor.get("source_width")
        rel = anchor.get("rel")
        length = anchor.get("length")
        tangent = anchor.get("tangent")
        if (not isinstance(width, (int, float))
                or isinstance(width, bool)
                or not math.isfinite(width) or not width > 0):
            return False
        if (not isinstance(rel, (int, float))
                or isinstance(rel, bool) or not math.isfinite(rel)):
            return False
        if (not isinstance(length, (int, float))
                or isinstance(length, bool)
                or not math.isfinite(length) or not length > 0):
            return False
        try:
            if len(tangent) != 2:
                return False
            tx, ty = tangent[0], tangent[1]
        except (TypeError, IndexError, KeyError):
            return False
        if (not isinstance(tx, (int, float))
                or not isinstance(ty, (int, float))
                or isinstance(tx, bool) or isinstance(ty, bool)
                or not math.isfinite(tx) or not math.isfinite(ty)
                or (tx == 0 and ty == 0)):
            return False
    return True


def _closure_aliases(parsed, points):
    """Explicit closing-endpoint aliases for line/quad/cubic contours.

    parse_commands materializes a closing line when the last endpoint index
    differs from the contour start; when that edge ends at duplicate contour
    start coordinates its start vertex is an encoding artifact, not separate
    geometry. Start and end come from seg[-2]/seg[-1] uniformly so cubic-first
    contours resolve the true start, which a first-line/quad lookup misses.
    """
    weld = {}
    for contour in parsed["contours"]:
        if not contour:
            continue
        first, last = contour[0], contour[-1]
        if first[0] not in ("line", "quad", "cubic"):
            continue
        if last[0] != "line":
            continue
        canon, dup = first[-2], last[-2]
        if last[-1] != canon or dup == canon:
            continue
        if tuple(points[dup]) != tuple(points[canon]):
            continue
        weld[dup] = canon
    return weld


def _weld_constraints(weld, var_verts, fixed, base):
    """Duplicate-canonical equality rows; unresolved ownership abstains.

    An explicit closing endpoint alias is an encoding artifact, not zero
    tangent geometry; Hobby 6 carries shared vertices as one unknown, so each
    alias pair is equated in the source-displacement frame. Only an alias
    that is itself variable, with a non-variable canonical and no fixed axis
    of its own, merges into the emission set; any other variable contact
    abstains rather than splitting the point.
    """
    rows, merged, conflict = [], set(), None
    for dup, canon in weld.items():
        if dup not in var_verts and canon not in var_verts:
            continue
        if (canon not in var_verts and dup in var_verts
                and (dup, 0) not in fixed and (dup, 1) not in fixed):
            for axis in (0, 1):
                row = np.zeros(2 * len(base))
                row[2 * dup + axis] = 1.0
                row[2 * canon + axis] = -1.0
                rows.append((row, float(base[canon][axis]
                                        - base[dup][axis])))
            merged.add(dup)
        else:
            conflict = (dup, canon)
            break
    return rows, merged, conflict


def _combined_topology(raw_source_commands, captured_source_commands):
    # Default gate: the curved-width finite-invariant substitution check over
    # all three outlines (raw, upstream, candidate), adapted to the exact
    # arrangement report the joint validator requires.
    def check(source_commands, fitted_commands, candidate):
        sources = [captured_source_commands]
        if raw_source_commands != captured_source_commands:
            sources.append(raw_source_commands)
        for source in sources:
            gate = _curved_width._substitution_gate(
                source, fitted_commands, candidate)
            if not gate["ok"]:
                verdict = gate["verdict"]
                return {"supported": verdict.get("supported", False),
                        "ok": False, "reason": "default-topology",
                        "verdict": verdict}
        return {"supported": True, "ok": True, "reason": "match"}
    return check


def fit(raw_source_commands, captured_source_commands,
        original_upstream_commands, size_px, reference,
        native_axes=(False, False), topology_checker=None):
    """Pin raw cap edges to upstream heights inside the width solve.

    The width geometry reuses the direct-diagonal helpers exactly: canonical
    visible-split discovery, interval ownership, exact curve-disk clearance,
    upright plus all-curve-endpoint pins and the source-displacement joint
    assembly with grid off. Upstream Y minus source Y fixed rows then hold
    each affected cap vertex at its original upstream height (Hobby 3.3 common
    displacement of horizontal regions) while X joins the (17) coupling. Raw
    nonzero vertical edges with shared upstream X keep that upstream X while
    Y joins the solve (Hersch upright control). The
    constrained solve runs in the source-displacement frame; movement clamps
    through the same uniform scale, emission touches only allowed variable
    vertices with refreshed float bits, and the joint validator plus the
    upstream-fixed curve sweep and the width-cost improvement gate must all
    pass. Any failure returns the original upstream commands for the parent
    to replace with the preceding packet. Advances and layout stay outside
    the fit. Native Y ownership leaves no new constraint, so it abstains, as
    do non-finite or non-positive size, non-finite source controls, mismatched
    closure aliases and conflicting alias ownership.
    """
    try:
        valid_axes = (len(native_axes) == 2
                      and all(type(v) is bool for v in native_axes))
    except TypeError:
        valid_axes = False
    if not valid_axes:
        return _abstain(original_upstream_commands, "malformed-native-axes")
    if bool(native_axes[1]):
        return _abstain(original_upstream_commands, "native-y-owned")
    if (not isinstance(size_px, (int, float))
            or isinstance(size_px, bool)
            or not math.isfinite(size_px) or not size_px > 0):
        return _abstain(original_upstream_commands, "malformed-size")
    try:
        if not check_correspondence(raw_source_commands,
                                    original_upstream_commands):
            return _abstain(original_upstream_commands, "no-correspondence")
        if not check_correspondence(captured_source_commands,
                                    original_upstream_commands):
            return _abstain(original_upstream_commands, "no-correspondence")
        raw_parsed = parse_commands(raw_source_commands)
        parsed = parse_commands(captured_source_commands)
        fitted = parse_commands(original_upstream_commands)
        for pt in (raw_parsed["oncurve"] + raw_parsed["offcurve"]
                   + parsed["oncurve"] + parsed["offcurve"]):
            if not math.isfinite(pt[0]) or not math.isfinite(pt[1]):
                return _abstain(original_upstream_commands,
                                "malformed-commands")
        caps, _, _ = detect_caps(raw_source_commands,
                                 original_upstream_commands)
        uprights = detect_uprights(raw_source_commands,
                                   original_upstream_commands)
        weld = _closure_aliases(parsed,
                                parsed["oncurve"] + parsed["offcurve"])
        up_weld = _closure_aliases(fitted,
                                   fitted["oncurve"] + fitted["offcurve"])
    except (KeyError, TypeError, AttributeError, ArithmeticError,
            ValueError, IndexError):
        return _abstain(original_upstream_commands, "malformed-commands")
    cap_ids = sorted({v for c in caps for v in c["vertices"]})
    up_ids = sorted({v for u in uprights for v in u["vertices"]})
    if set(weld.items()) != set(up_weld.items()):
        return _abstain(original_upstream_commands, "weld-mismatch",
                        caps=caps, cap_vertices=cap_ids,
                        uprights=uprights, upright_vertices=up_ids)
    up_pts = fitted["oncurve"]
    if any(tuple(up_pts[dup]) != tuple(up_pts[canon])
           for dup, canon in weld.items()):
        return _abstain(original_upstream_commands, "weld-mismatch",
                        caps=caps, cap_vertices=cap_ids,
                        uprights=uprights, upright_vertices=up_ids)
    anchors_ref = reference.get("anchors") if isinstance(reference, dict) \
        else None
    if not anchors_ref or not _valid_anchors(anchors_ref):
        return _abstain(original_upstream_commands,
                        "no-reference-anchors" if not anchors_ref
                        else "malformed-anchors",
                        caps=caps, cap_vertices=cap_ids,
                        uprights=uprights, upright_vertices=up_ids)
    try:
        base = np.asarray(parsed["oncurve"], dtype=float)
        upstream = np.asarray(fitted["oncurve"], dtype=float)
        if not np.isfinite(base).all() or not np.isfinite(upstream).all():
            return _abstain(original_upstream_commands, "malformed-commands")
        portions, _, loops, flats = _dd._split_visible(parsed, canonical=True)
        pairs, skipped = _dd._recognize(portions, loops, ownership="interval")
        pins = set()
        for pair in _dd._upright_pairs(pairs):
            for side in (pair["a"], pair["b"]):
                pins.add(side["i0"])
                pins.add(side["i1"])
        for contour in parsed["contours"]:
            for seg in contour:
                if seg[0] == "line":
                    continue
                pins.add(seg[-2])
                pins.add(seg[-1])
        borders = _dd._visible_borders(portions)
        exact_curves = _dd._curve_controls(parsed)
        fitted_coords = fitted["oncurve"]
        prepped, details = [], list(skipped)
        for pair in pairs:
            if _dd._upright_pairs([pair]):
                details.append({"pair": (pair["a"]["seg"], pair["b"]["seg"]),
                                "reason": "upright-anchor"})
                continue
            try:
                info, why = _dd._prepare_pair(
                    pair, borders, loops, loops, flats, flats,
                    fitted_coords, size_px, exact_curves=exact_curves)
            except (ValueError, ArithmeticError):
                details.append({"pair": (pair["a"]["seg"], pair["b"]["seg"]),
                                "reason": "pair-invalid"})
                continue
            if why is not None:
                details.append({"pair": (pair["a"]["seg"], pair["b"]["seg"]),
                                "reason": why})
                continue
            bound = min(info["src_widths"]) / 2 - _dd.HEADROOM
            if not bound >= _dd.HEADROOM:
                details.append({"pair": info["id"],
                                "reason": "movement-budget-empty"})
                continue
            info["bound"] = bound
            prepped.append(info)
        if not prepped:
            return _abstain(original_upstream_commands, "all-abstained",
                            caps=caps, cap_vertices=cap_ids,
                            uprights=uprights, upright_vertices=up_ids,
                            skipped=details,
                            fixed={"anchors": sorted(pins),
                                   "native_axes": list(native_axes[:2])})
        owned = tuple(i for i, on in enumerate(native_axes[:2]) if on)
        system, hard, fixed, gaps, var_verts = _dd._assemble(
            parsed, fitted_coords, prepped, anchors_ref, size_px, False,
            pins, owned)
        affected = sorted({v for c in caps for v in c["vertices"]}
                          & set(var_verts))
        if not affected:
            return _abstain(original_upstream_commands, "cap-not-involved",
                            caps=caps, cap_vertices=cap_ids,
                            uprights=uprights, upright_vertices=up_ids,
                            skipped=details,
                            fixed={"anchors": sorted(pins),
                                   "native_axes": list(native_axes[:2])})
        for edge in uprights:
            for v in edge["vertices"]:
                # Upstream X minus source X keeps the original upright
                # position; Y stays free except where other ownership
                # already fixed it.
                fixed[(v, 0)] = float(gaps[v][0])
        weld_rows, merged, conflict = _weld_constraints(
            weld, var_verts, fixed, base)
        if conflict is not None:
            return _abstain(original_upstream_commands, "weld-conflict",
                            caps=caps, cap_vertices=affected,
                            uprights=uprights, upright_vertices=up_ids,
                            skipped=details,
                            fixed={"anchors": sorted(pins),
                                   "native_axes": list(native_axes[:2])})
        for cap in caps:
            for v in cap["vertices"]:
                # Upstream Y minus source Y keeps the candidate at the
                # original upstream height; X stays free except where other
                # ownership already fixed it.
                fixed[(v, 1)] = float(gaps[v][1])
        soft = [(g, np.asarray(r, dtype=float), float(c))
                for g, r, c in system.rows]
        flex = _dd._solve_constrained(
            soft, [("weld", r, c) for r, c in weld_rows], fixed,
            len(parsed["oncurve"]))
        if flex is None:
            return _abstain(original_upstream_commands,
                            "inconsistent-constraints",
                            caps=caps, cap_vertices=affected,
                            uprights=uprights, upright_vertices=up_ids,
                            skipped=details,
                            fixed={"anchors": sorted(pins),
                                   "native_axes": list(native_axes[:2])})
        deltas = (base + flex.reshape(-1, 2)) - upstream
        if not np.isfinite(flex).all() or not np.isfinite(deltas).all():
            return _abstain(original_upstream_commands,
                            "nonfinite-solution",
                            caps=caps, cap_vertices=affected,
                            uprights=uprights, upright_vertices=up_ids,
                            skipped=details,
                            fixed={"anchors": sorted(pins),
                                   "native_axes": list(native_axes[:2])})
        peaks = {}
        for info in prepped:
            verts = {info["a"]["i0"], info["a"]["i1"],
                     info["b"]["i0"], info["b"]["i1"]}
            peaks[info["id"]] = max(
                [float(np.linalg.norm(deltas[v])) for v in verts] + [0.0])
        over = [pid for pid, peak in peaks.items()
                if peak > next(i["bound"] for i in prepped
                               if i["id"] == pid)]
        if over:
            scale = min(next(i["bound"] for i in prepped if i["id"] == pid)
                        / peaks[pid] for pid in over)
            deltas = deltas * scale
            for info in prepped:
                info["prefix"] = scale
        for info in prepped:
            info.setdefault("prefix", 1.0)
            info["peak"] = peaks[info["id"]]
        table = _dd._index_map(original_upstream_commands)
        candidate = [dict(cmd) for cmd in original_upstream_commands]
        flat_up = upstream.ravel()
        flat_cand = (upstream + deltas).ravel()
        for v in sorted(var_verts | merged):
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
        if _dd._commands_equal(candidate, original_upstream_commands):
            return _abstain(original_upstream_commands, "no-movement",
                            caps=caps, cap_vertices=affected,
                            uprights=uprights, upright_vertices=up_ids,
                            skipped=details,
                            fixed={"anchors": sorted(pins),
                                   "native_axes": list(native_axes[:2])},
                            movement=0.0,
                            bound=min(i["bound"] for i in prepped))
        match_rows = [(np.asarray(r, dtype=float), float(c))
                      for g, r, c in system.rows if g == "ink-match"]
        flat_base_up = upstream.ravel() - base.ravel()
        flat_base_cand = (np.asarray(
            parse_commands(candidate)["oncurve"], dtype=float).ravel()
            - base.ravel())
        cost_upstream = float(sum((float(row @ flat_base_up) + const) ** 2
                                  for row, const in match_rows))
        cost_candidate = float(sum((float(row @ flat_base_cand) + const) ** 2
                                   for row, const in match_rows))
        validity = _dd._validate(
            parsed, fitted, original_upstream_commands, candidate, portions,
            prepped, pins, owned, False, [], flex,
            source_commands=captured_source_commands,
            topology_checker=_combined_topology(raw_source_commands,
                                               captured_source_commands),
            canonical=True)
        validity["cost_upstream"] = cost_upstream
        validity["cost_candidate"] = cost_candidate
        validity["cost_ok"] = cost_candidate < cost_upstream
        if not validity["cost_ok"]:
            validity["ok"] = False
            validity["stage"] = "no-cost-decrease"
        if validity["ok"]:
            sweep_ok, sweep_reason = _dd._curve_sweep_ok(
                parsed, fitted, candidate, _dd._curve_controls(fitted))
            validity["curve_sweep"] = sweep_reason
            if not sweep_ok:
                validity["ok"] = False
                validity["stage"] = sweep_reason
        cap_exact = all(
            candidate[table[v]]["y"] == fitted["oncurve"][v][1]
            for v in cap_ids if table.get(v) is not None)
        validity["cap_exact"] = bool(cap_exact)
        if not cap_exact:
            validity["ok"] = False
            validity["stage"] = "cap-height-moved"
        weld_exact = all(
            table.get(dup) is not None and table.get(canon) is not None
            and candidate[table[dup]]["x"] == candidate[table[canon]]["x"]
            and candidate[table[dup]]["y"] == candidate[table[canon]]["y"]
            for dup, canon in weld.items())
        validity["weld_exact"] = bool(weld_exact)
        if not weld_exact:
            validity["ok"] = False
            validity["stage"] = "weld-split"
        upright_exact = all(
            candidate[table[v]]["x"] == fitted["oncurve"][v][0]
            for u in uprights for v in u["vertices"]
            if table.get(v) is not None)
        validity["upright_exact"] = bool(upright_exact)
        if not upright_exact:
            validity["ok"] = False
            validity["stage"] = "upright-moved"
        if topology_checker is not None and validity["ok"]:
            try:
                extra = topology_checker(raw_source_commands,
                                         original_upstream_commands,
                                         candidate)
            except Exception as exc:
                extra = {"ok": False, "reason": "checker-exception",
                         "error": str(exc)}
            if isinstance(extra, dict):
                extra_ok = (extra.get("ok") is True
                            and extra.get("supported", True) is not False)
            else:
                extra_ok = extra is True
            validity["external_topology"] = extra
            if not extra_ok:
                validity["ok"] = False
                validity["stage"] = "topology-rejected"
        achieved = _dd._achieved(prepped, candidate, fitted_coords)
        widths = [(p["source_width"], p["upstream_width"],
                   p["candidate_width"]) for p in achieved]
        summary = {
            "source": sum(w[0] for w in widths) / len(widths),
            "upstream": sum(w[1] for w in widths) / len(widths),
            "candidate": sum(w[2] for w in widths) / len(widths)}
        if not validity["ok"]:
            fallback = _dd._achieved(prepped, original_upstream_commands,
                                     fitted_coords)
            widths = [(p["source_width"], p["upstream_width"],
                       p["candidate_width"]) for p in fallback]
            return _abstain(
                original_upstream_commands, "invalid-candidate",
                caps=caps, cap_vertices=affected,
                uprights=uprights, upright_vertices=up_ids, pairs=fallback,
                skipped=details, validity=validity,
                fixed={"anchors": sorted(pins),
                       "native_axes": list(native_axes[:2])},
                movement=0.0, bound=min(i["bound"] for i in prepped),
                widths={
                    "source": sum(w[0] for w in widths) / len(widths),
                    "upstream": sum(w[1] for w in widths) / len(widths),
                    "candidate": sum(w[2] for w in widths) / len(widths)},
                attempt={"attempted_commands": candidate,
                         "movement": max(peaks.values()) if peaks else 0.0,
                         "validity": validity})
        return {
            "candidate_commands": candidate,
            "applied": True, "reason": "fitted",
            "caps": caps, "cap_vertices": affected,
            "uprights": uprights, "upright_vertices": up_ids,
            "validity": validity, "pairs": achieved, "skipped": details,
            "fixed": {"anchors": sorted(pins),
                     "native_axes": list(native_axes[:2])},
            "movement": max(peaks.values()) if peaks else 0.0,
            "bound": min(i["bound"] for i in prepped),
            "size_px": size_px,
            "widths": summary,
            "reference": {"n_anchors": len(anchors_ref)}}
    except (KeyError, TypeError, AttributeError, ArithmeticError,
            ValueError, IndexError):
        return _abstain(original_upstream_commands, "malformed-commands")
