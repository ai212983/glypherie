"""StrokeStyles-annotated source-relative diagonal fitting (consumer slice).

Consumes structural analysis (spine paths P, width profiles W as medial
radii, connectivity, junctions) annotating the original outline, then
couples straight diagonal normal-width changes to an upstream-fitted
upright standard. Hobby (4)/(5) supply medial width as twice the radius
and the signed projected relative width error; (17) couples related
strokes to an anchor; section 3.2 restricts pairs to open
dominance-interval contacts; section 3.3 motivates the rectilinear
anchor. Sampled polylines annotate the source outline, never replacement
geometry. Residuals are evidence per constraint group, not an acceptance
score. Passing checks do not establish optical acceptance.
"""

import math
import struct

import numpy as np

from experiments.hobby_fitting import intervals
from experiments.hobby_fitting.prototype import Sample, System, width_weight
from experiments.hobby_fitting.real_outline import (
    check_correspondence,
    loops_parsed,
    parse_commands,
)

ANALYSIS_SCHEMA = "extract-record-v2"
STATIONS = 3
# Nearest-26.6 Euclidean rounding reserve (Hobby interval model); also
# the outline quantization basis for mapping and clearance tolerances.
HEADROOM = math.sqrt(2.0) / 128.0


def _finite_array(values, rows=None):
    try:
        arr = np.asarray(values, dtype=float)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(arr).all():
        return None
    if rows is not None and (arr.ndim != 2 or arr.shape != rows):
        return None
    return arr


def _stroke_radii(stroke):
    for key in ("Wv", "Wv_radius"):
        if key in stroke:
            radii = _finite_array(stroke[key])
            if radii is not None and radii.ndim == 1:
                return radii
    return None


def _stroke_widths(stroke):
    for key in ("W", "W_radius"):
        if key in stroke:
            widths = _finite_array(stroke[key])
            if widths is not None and widths.ndim == 1:
                return widths
    return None


def _normalize_stroke(stroke):
    spine = _finite_array(stroke.get("P"), None)
    if spine is None or spine.ndim != 2 or spine.shape[1] != 2:
        return None
    count = spine.shape[0]
    if count < 2:
        return None
    radii = _stroke_radii(stroke)
    if radii is None or len(radii) != count or (radii <= 0).any():
        return None
    widths = _stroke_widths(stroke)
    if widths is None or len(widths) != count - 1:
        return None
    # W/Wv are medial radii; thickness is 2r, never a diameter.
    scale = max(float(radii.max()), 1e-300)
    if (np.abs(widths - radii[:-1]) > 1e-6 * scale).any():
        return None
    full = stroke.get("W_full")
    if full is not None:
        full = _finite_array(full)
        if (full is None or len(full) != count - 1
                or (np.abs(full - 2.0 * widths) > 1e-6 * scale).any()):
            return None
    corners = stroke.get("corner_flags")
    if corners is not None:
        try:
            corners = [int(c) for c in corners]
        except (TypeError, ValueError):
            return None
        if len(corners) != count:
            corners = None
    return {"spine": spine, "radii": radii, "corners": corners}


def _first_present(mapping, keys):
    for key in keys:
        if isinstance(mapping, dict) and key in mapping:
            return mapping[key]
    return None


def validate_analysis(record):
    """Validate an upstream glyph-export record without trusting field names.

    Accepts the pinned runner's suffixed width keys alongside the plain
    upstream names. Anything else reports unsupported, never fabricated.
    """
    if not isinstance(record, dict):
        return {"supported": False, "reason": "unsupported-analysis"}
    provenance = record.get("provenance")
    if not isinstance(provenance, dict):
        return {"supported": False, "reason": "unsupported-analysis-provenance"}
    schema = record.get("schema_version", provenance.get("schema_version"))
    if schema != ANALYSIS_SCHEMA:
        return {"supported": False, "reason": "unsupported-analysis-schema"}
    glyphs = record.get("glyphs")
    if isinstance(glyphs, dict):
        single = None
    elif "strokes" in record:
        glyphs, single = None, record
    else:
        return {"supported": False, "reason": "unsupported-analysis"}
    convention = _first_present(record, ("width_convention",))
    if convention is None and isinstance(provenance, dict):
        convention = provenance.get("width_convention")
    if (convention is not None
            and "radi" not in str(convention).lower()):
        return {"supported": False, "reason": "unsupported-width-convention"}
    frame = provenance.get("coordinate_convention")
    if frame is not None and "y-up" not in str(frame).lower().replace("_", "-"):
        return {"supported": False, "reason": "unsupported-coordinates"}
    out = {}
    source = glyphs if glyphs is not None else {"": single}
    for char, glyph in source.items():
        if not isinstance(glyph, dict):
            return {"supported": False, "reason": "unsupported-analysis",
                    "char": char}
        strokes = glyph.get("strokes")
        if not isinstance(strokes, list) or not strokes:
            return {"supported": False, "reason": "unsupported-analysis",
                    "char": char}
        normalized = []
        for stroke in strokes:
            entry = _normalize_stroke(stroke) if isinstance(stroke, dict) \
                else None
            if entry is None:
                return {"supported": False, "reason": "unsupported-analysis",
                        "char": char}
            normalized.append(entry)
        frame = glyph.get("coordinate_convention")
        if (frame is not None
                and "y-up" not in str(frame).lower().replace("_", "-")):
            return {"supported": False, "reason": "unsupported-coordinates",
                    "char": char}
        connectivity = glyph.get("connectivity")
        if (not isinstance(connectivity, dict)
                or not all(isinstance(connectivity.get(k), list)
                           for k in ("links", "joins", "terminals"))):
            return {"supported": False, "reason": "unsupported-connectivity",
                    "char": char}
        junctions = glyph.get("junctions")
        if junctions is None:
            junctions = record.get("junctions", [])
        if not isinstance(junctions, list):
            return {"supported": False, "reason": "unsupported-analysis",
                    "char": char}
        out[char] = {"strokes": normalized,
                     "connectivity": connectivity,
                     "junctions": junctions}
    upem = _first_present(provenance,
                          ("units_per_em", "upem", "UPM", "unitsPerEm"))
    try:
        upem = float(upem)
    except (TypeError, ValueError):
        return {"supported": False, "reason": "unsupported-analysis"}
    if not math.isfinite(upem) or upem <= 0:
        return {"supported": False, "reason": "unsupported-analysis"}
    return {"supported": True, "glyphs": out, "upem": upem,
            "provenance": provenance}


def match_provenance(provenance, font_sha256, axes):
    """Cache extraction is independent of pixel size; identity is not."""
    if not isinstance(provenance, dict):
        return False, "unsupported-analysis-provenance"
    candidates = [provenance.get(k) for k in
                  ("source_font_sha256", "font_sha256_original",
                   "font_sha256_instantiated")]
    candidates = [c for c in candidates if isinstance(c, str)]
    if not candidates or all(c != font_sha256 for c in candidates):
        return False, "provenance-mismatch-font"
    resolved = _first_present(provenance,
                              ("axes_resolved", "resolved_axes", "axes"))
    if not isinstance(resolved, dict):
        return False, "provenance-mismatch-axes"
    for tag, value in (axes or {}).items():
        try:
            got = float(resolved[tag])
        except (KeyError, TypeError, ValueError):
            return False, "provenance-mismatch-axes"
        if got != float(value):
            return False, "provenance-mismatch-axes"
    return True, None


def _split_runs(spine, radii, corners):
    """Straight spine runs split at imported corners, never averaged.

    Corners come from the upstream corner classification. The export
    carries raw medial disks, not a smoothed path, so each run frame
    is the orthogonal regression line through its samples, which
    centers the offset model exactly on wobbly straight data. Bend
    certification stays endpoint-fixed: chord deviation beyond the
    run's own mapping tolerance abstains as curved-spine, since a
    fitted line would hide the bend. Taper stays supported: station
    widths come from the exact dominance contacts, not the profile
    mean.
    """
    points = [tuple(p) for p in spine.tolist()]
    bounds = [0]
    if corners is not None:
        bounds += [i for i in range(1, len(points) - 1) if corners[i]]
    bounds.append(len(points) - 1)
    out = []
    for a, b in zip(bounds, bounds[1:]):
        if b - a < 1:
            continue
        sample = np.array(points[a:b + 1], dtype=float)
        center = sample.mean(axis=0)
        if b - a < 2:
            delta = sample[-1] - sample[0]
            length = float(np.linalg.norm(delta))
            if length <= 0:
                continue
            tangent = delta / length
        else:
            _, singular, right = np.linalg.svd(sample - center,
                                               full_matrices=False)
            if singular[0] <= 0:
                continue
            tangent = right[0] / np.linalg.norm(right[0])
        normal = np.array([-tangent[1], tangent[0]])
        chord = sample[-1] - sample[0]
        chord_length = float(np.linalg.norm(chord))
        if chord_length <= 0:
            continue
        chord_normal = np.array([-chord[1], chord[0]]) / chord_length
        dev = float(np.abs((sample - sample[0]) @ chord_normal).max())
        seg = radii[a:b + 1]
        gaps = sorted(math.hypot(points[i + 1][0] - points[i][0],
                                  points[i + 1][1] - points[i][1])
                      for i in range(a, b))
        # Recorded sampling density (median interior gap) plus the
        # outline 26.6 quantum; measured per run, never pixel-tuned.
        tol = gaps[len(gaps) // 2] + HEADROOM
        proj = [(points[i][0] - center[0]) * tangent[0]
                + (points[i][1] - center[1]) * tangent[1]
                for i in range(a, b + 1)]
        out.append({"i0": a, "i1": b, "center": center,
                    "tangent": tangent, "normal": normal,
                    "lo": min(proj), "hi": max(proj),
                    "radius": float(seg.mean()),
                    "spread": float(seg.max() - seg.min())
                    / max(float(seg.mean()), 1e-300),
                    "curved": bool(dev > tol),
                    "tol": tol, "dev": float(dev)})
    return out


def _straight_edges(parsed):
    edges = []
    for ci, contour in enumerate(parsed["contours"]):
        for si, seg in enumerate(contour):
            if seg[0] != "line":
                continue
            p0 = parsed["oncurve"][seg[1]]
            p1 = parsed["oncurve"][seg[2]]
            delta = (p1[0] - p0[0], p1[1] - p0[1])
            length = math.hypot(*delta)
            if length > 0:
                edges.append({"contour": ci, "seg": si,
                              "i0": seg[1], "i1": seg[2],
                              "p0": p0, "p1": p1,
                              "dir": (delta[0] / length, delta[1] / length),
                              "length": length})
    return edges


def _axis_of(edge):
    if edge["p0"][0] == edge["p1"][0]:
        return "x"
    if edge["p0"][1] == edge["p1"][1]:
        return "y"
    return None


def _assign_edges(edges, runs):
    """Claim outline edges by imported straight runs, never by pixels.

    Both endpoints must lie on one offset border line and overlap the
    run span, within per-run recorded sampling plus the 26.6 outline
    quantum. No spine-direction gate: the spine comes from raw medial
    disks and carries tilt that exact drawn borders do not share;
    non-pairs are rejected downstream by corridor opposition and open
    dominance-interval clearance instead.
    """
    claims = {}
    for edge in edges:
        key = (edge["contour"], edge["seg"])
        for ri, run in enumerate(runs):
            if run["curved"]:
                continue
            # Run-mean radius at the offset line. Tapered borders
            # miss candidacy here and abstain; widths always come
            # from the dominance contacts, never this check.
            tol = run["tol"]
            mid = run["center"]
            rel0 = np.array(edge["p0"]) - mid
            rel1 = np.array(edge["p1"]) - mid
            da, db = float(np.dot(rel0, run["normal"])), \
                float(np.dot(rel1, run["normal"]))
            if (abs(abs(da) - run["radius"]) > tol
                    or abs(abs(db) - run["radius"]) > tol
                    or da == 0 or db == 0
                    or (da > 0) != (db > 0)):
                continue
            s0, s1 = float(np.dot(rel0, run["tangent"])), \
                float(np.dot(rel1, run["tangent"]))
            if max(s0, s1) <= run["lo"] or min(s0, s1) >= run["hi"]:
                continue
            claims.setdefault(key, []).append(
                {"run": ri, "side": 1 if da > 0 else -1})
    return claims


def _terminal_point(stroke_entry, scale, terminal):
    idx = 0 if terminal == 0 else len(stroke_entry["spine"]) - 1
    return np.array(stroke_entry["spine"][idx], dtype=float) * scale


def _participating_terminals(connectivity):
    """Localize joined/linked stroke terminals; hosts stay unlocalized."""
    out = []
    for link in connectivity.get("links", []):
        if isinstance(link, dict) and "link_stroke" in link \
                and "link_terminal" in link:
            try:
                out.append((int(link["link_stroke"]),
                            int(link["link_terminal"])))
            except (TypeError, ValueError):
                continue
    for join in connectivity.get("joins", []):
        if not isinstance(join, dict):
            continue
        strokes, terminals = join.get("strokes", []), \
            join.get("terminals", [])
        try:
            pairs = list(zip([int(s) for s in strokes],
                             [int(t) for t in terminals]))
        except (TypeError, ValueError):
            continue
        out.extend(pairs)
    return out


def _terminal_sites(strokes, connectivity, scale):
    """Medial sites of joined/linked terminals (center, radius in px)."""
    sites = []
    for stroke_idx, terminal in _participating_terminals(connectivity):
        if not 0 <= stroke_idx < len(strokes):
            continue
        center = _terminal_point(strokes[stroke_idx], scale, terminal)
        local = strokes[stroke_idx]["radii"][0 if terminal == 0 else -1]
        sites.append((center, float(local) * scale, stroke_idx, terminal))
    return sites


def _elbow_sites(strokes, scale):
    """Medial footprints of flagged corners from the stroke profile.

    Uses the validated width profile at the flagged sample, never the
    unscaled corner_radii side channel.
    """
    sites = []
    for si, stroke in enumerate(strokes):
        corners = stroke.get("corners")
        if not corners:
            continue
        spine = stroke["spine"]
        for i in range(len(spine)):
            if corners[i] and 0 < i < len(spine) - 1:
                sites.append((np.array(spine[i], dtype=float) * scale,
                              float(stroke["radii"][i]) * scale, si, i))
    return sites


def _coincident_sites(strokes, connectivity, scale):
    """Unlinked terminals sharing one medial footprint (dropped tips).

    Upstream connectivity drops junctions touching morphological tips,
    so coincident free terminals across strokes are frozen by footprint
    instead of assumed separate.
    """
    ends = []
    for si, stroke in enumerate(strokes):
        for terminal in (0, 1):
            idx = 0 if terminal == 0 else len(stroke["spine"]) - 1
            ends.append((si, terminal,
                         np.array(stroke["spine"][idx], dtype=float) * scale,
                         float(stroke["radii"][idx]) * scale))
    linked = set()
    for stroke_idx, terminal in _participating_terminals(connectivity):
        linked.add((stroke_idx, terminal))
    sites = []
    for a in range(len(ends)):
        for b in range(a + 1, len(ends)):
            if ends[a][0] == ends[b][0]:
                continue
            if (ends[a][0], ends[a][1]) in linked:
                continue
            if (ends[b][0], ends[b][1]) in linked:
                continue
            gap = float(np.linalg.norm(ends[a][2] - ends[b][2]))
            if gap <= ends[a][3] + ends[b][3] + 2 * HEADROOM:
                sites.append((ends[a][2], ends[a][3], ends[a][0],
                              ends[a][1]))
                sites.append((ends[b][2], ends[b][3], ends[b][0],
                              ends[b][1]))
    return sites


def _freeze_sets(edges, claims, runs, strokes, connectivity, scale):
    """Junction-owned vertices from imported grouping (T/Y/L family).

    Multi-stroke and multi-run vertices freeze exactly, as do measured
    medial sites: joined/linked terminals, flagged corner footprints
    and coincident unlinked terminals. Each site covers its own medial
    disk plus the outline 26.6 quantum. Free isolated cap terminals
    keep their vertices.
    """
    frozen, causes = set(), {}
    by_vertex_runs, by_vertex_strokes = {}, {}
    for edge in edges:
        key = (edge["contour"], edge["seg"])
        for claim in claims.get(key, []):
            stroke = runs[claim["run"]]["stroke"]
            for vert in (edge["i0"], edge["i1"]):
                by_vertex_runs.setdefault(vert, set()).add(claim["run"])
                by_vertex_strokes.setdefault(vert, set()).add(stroke)
    for vert, group in by_vertex_strokes.items():
        if len(group) > 1:
            frozen.add(vert)
            causes[vert] = "branch-join"
    for vert, group in by_vertex_runs.items():
        if vert not in frozen and len(group) > 1:
            frozen.add(vert)
            causes[vert] = "fold-corner"
    sites = [(c, r, "junction-clearance")
             for c, r, _, _ in _terminal_sites(strokes, connectivity, scale)]
    sites += [(c, r, "elbow-footprint")
              for c, r, _, _ in _elbow_sites(strokes, scale)]
    sites += [(c, r, "coincident-terminal")
              for c, r, _, _ in _coincident_sites(strokes, connectivity,
                                                 scale)]
    for center, radius, cause in sites:
        limit = radius + HEADROOM
        for edge in edges:
            for vert, pt in ((edge["i0"], edge["p0"]),
                             (edge["i1"], edge["p1"])):
                if vert in frozen:
                    continue
                if math.hypot(pt[0] - center[0], pt[1] - center[1]) <= limit:
                    frozen.add(vert)
                    causes[vert] = cause
    return frozen, causes


def _other_borders(edges, skip):
    others = []
    for edge in edges:
        key = (edge["contour"], edge["seg"])
        if key in skip:
            continue
        others.append({"seg": (tuple(edge["p0"]), tuple(edge["p1"])),
                       "tag": "edge(%d,%d)" % key})
    return others


def _form_pairs(edges, claims, runs):
    """One representative edge per run side; shared edges drop every pair.

    Mirrors the owning single-contour recognizer's ambiguity rule across
    contours: an edge claimed by more than one pair abstains rather than
    resolving arbitrarily.
    """
    by_run_side = {}
    for edge in edges:
        key = (edge["contour"], edge["seg"])
        for claim in claims.get(key, []):
            by_run_side.setdefault((claim["run"], claim["side"]),
                                   []).append(edge)
    pairs, used, ambiguous = [], {}, []
    for run_idx in sorted(range(len(runs))):
        sides = {s: by_run_side.get((run_idx, s), []) for s in (1, -1)}
        if not sides[1] or not sides[-1]:
            if runs[run_idx]["curved"]:
                pairs.append({"run": run_idx, "skipped": "curved-spine"})
            else:
                pairs.append({"run": run_idx, "skipped": "unassigned-run"})
            continue
        run = runs[run_idx]
        if run["curved"]:
            pairs.append({"run": run_idx, "skipped": "curved-spine"})
            continue
        pick = {s: max(sides[s], key=lambda e: e["length"]) for s in (1, -1)}
        keys = {s: (pick[s]["contour"], pick[s]["seg"]) for s in (1, -1)}
        if keys[1] == keys[-1]:
            pairs.append({"run": run_idx, "skipped": "degenerate-pair"})
            continue
        clash = [s for s in (1, -1) if keys[s] in used]
        if clash:
            ambiguous.append({"edges": sorted({str(keys[s]) for s in (1, -1)})})
            pairs = [p for p in pairs
                     if not (p.get("keys") and set(p["keys"]) & set(keys.values()))]
            used = {k: v for k, v in used.items()
                    if k not in set(keys.values())}
            for key in keys.values():
                used.pop(key, None)
            pairs.append({"run": run_idx, "skipped": "ambiguous-pairing"})
            continue
        for s in (1, -1):
            used[keys[s]] = run_idx
        pairs.append({"run": run_idx, "edges": pick,
                      "keys": [keys[1], keys[-1]]})
    return pairs, ambiguous


def _dominance(pair, edges, loops):
    seg_a = (tuple(pair["edges"][1]["p0"]), tuple(pair["edges"][1]["p1"]))
    seg_b = (tuple(pair["edges"][-1]["p0"]), tuple(pair["edges"][-1]["p1"]))
    skip = set(pair["keys"])
    dom = intervals.dominance(seg_a, seg_b,
                              _other_borders(edges, skip), loops)
    pair["dom"] = dom
    return dom


def _medial_anchor(edge_a, edge_b, key_a, key_b, edges, loops):
    """Dominance-clear medial width of a rectilinear candidate (3.2).

    Exact source geometry only; grouping stays with the caller.
    Returns (ws, normal) or None when no open interval survives.
    """
    seg_a = (tuple(edge_a["p0"]), tuple(edge_a["p1"]))
    seg_b = (tuple(edge_b["p0"]), tuple(edge_b["p1"]))
    dom = intervals.dominance(seg_a, seg_b,
                              _other_borders(edges, {key_a, key_b}), loops)
    if dom["status"] != "ok" or not dom["intervals"]:
        return None
    span = max(dom["intervals"], key=lambda s: s["hi"] - s["lo"])
    contact = intervals.contact(seg_a, seg_b,
                                (span["lo"] + span["hi"]) / 2,
                                _other_borders(edges, {key_a, key_b}), loops)
    if contact["hit"] is None:
        return None
    hit = contact["hit"]
    chord = (hit["qa"][0] - hit["qb"][0], hit["qa"][1] - hit["qb"][1])
    dist = math.hypot(*chord)
    if dist <= 0:
        return None
    return hit["width"], (chord[0] / dist, chord[1] / dist), dom


def _anchor_candidates(pairs, runs, parsed, fitted_coords):
    """Rectilinear same-stroke pairs with integral fitted bounds (3.3).

    The slant is never an anchor by least-disturbance; multiple
    incompatible anchors abstain rather than selecting by pixels.
    """
    out = []
    edges_all = _straight_edges(parsed)
    loops_all = loops_parsed(parsed)
    for pair in pairs:
        if "edges" not in pair:
            continue
        edges = [pair["edges"][1], pair["edges"][-1]]
        axes = [_axis_of(e) for e in edges]
        if axes[0] is None or axes[0] != axes[1]:
            continue
        d0, d1 = edges[0]["dir"], edges[1]["dir"]
        if d0[0] * d1[0] + d0[1] * d1[1] >= 0:
            continue
        axis = axes[0]
        verts = (edges[0]["i0"], edges[0]["i1"],
                 edges[1]["i0"], edges[1]["i1"])
        vals = [fitted_coords[v][0 if axis == "x" else 1] for v in verts]
        if not all(float(v).is_integer() for v in vals):
            continue
        keys = pair.get("keys")
        if keys is None:
            continue
        medial = _medial_anchor(edges[0], edges[1], keys[0], keys[1],
                               edges_all, loops_all)
        if medial is None:
            continue
        ws, normal, _ = medial
        a = pair["edges"][1]
        b = pair["edges"][-1]
        fa = tuple(fitted_coords[a["i0"]][d] * 0.5
                   + fitted_coords[a["i1"]][d] * 0.5 for d in (0, 1))
        fb = tuple(fitted_coords[b["i0"]][d] * 0.5
                   + fitted_coords[b["i1"]][d] * 0.5 for d in (0, 1))
        wf = (fa[0] - fb[0]) * normal[0] + (fa[1] - fb[1]) * normal[1]
        out.append({"pair": pair, "axis": axis, "verts": set(verts),
                    "ws": ws, "wf": wf, "rel": (wf - ws) / ws})
    return out


def _solve_coordinates(system, fixed):
    """Least squares with per-coordinate fixed displacements.

    Same fixed-column elimination as System.solve, extended from whole
    points to single axes so native-owned coordinates stay exact.
    """
    for (vert, axis), value in fixed.items():
        if (not isinstance(vert, int) or not 0 <= vert < len(system.points)
                or axis not in (0, 1) or not math.isfinite(value)):
            raise ValueError("invalid fixed coordinate")
    if not system.rows:
        raise ValueError("no residuals")
    matrix = np.array([row for _, row, _ in system.rows])
    constants = np.array([c for _, _, c in system.rows])
    order = sorted(fixed)
    cols = np.array([2 * v + a for v, a in order], dtype=int)
    vals = np.array([fixed[k] for k in order])
    if len(cols):
        constants = constants + matrix[:, cols] @ vals
    free = np.array([2 * i + c for i in range(len(system.points))
                     for c in (0, 1) if (i, c) not in fixed], dtype=int)
    delta = np.zeros(system.points.size)
    for (vert, axis), value in fixed.items():
        delta[2 * vert + axis] = value
    if len(free):
        delta[free], _, rank, singular = np.linalg.lstsq(
            matrix[:, free], -constants, rcond=None)
        condition = (float(singular[0] / singular[-1])
                     if rank == len(free) else None)
    else:
        rank, condition = 0, None
    residuals = matrix @ delta + constants
    costs = {}
    for (group, _, _), value in zip(system.rows, residuals):
        costs[group] = costs.get(group, 0.0) + float(value * value)
    return {"delta": delta, "rank": int(rank),
            "free_variables": len(free), "condition": condition,
            "squared_residuals": costs,
            "max_movement": float(
                np.linalg.norm(delta.reshape(-1, 2), axis=1).max())}


def _orient(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _proper_crossings(loops):
    """Proper segment crossings; shared endpoints are not crossings."""
    segs = []
    for loop in loops:
        for i in range(len(loop)):
            segs.append((tuple(loop[i]), tuple(loop[(i + 1) % len(loop)])))

    def proper(p1, p2, p3, p4):
        if len({p1, p2, p3, p4}) < 4:
            return False
        o1, o2 = _orient(p1, p2, p3), _orient(p1, p2, p4)
        o3, o4 = _orient(p3, p4, p1), _orient(p3, p4, p2)
        return ((o1 > 0) != (o2 > 0)) and ((o3 > 0) != (o4 > 0))
    return sum(1 for i in range(len(segs)) for j in range(i + 1, len(segs))
               if proper(segs[i][0], segs[i][1], segs[j][0], segs[j][1]))


def _signed_areas(loops):
    out = []
    for loop in loops:
        n = len(loop)
        out.append(sum(loop[i][0] * loop[(i + 1) % n][1]
                       - loop[(i + 1) % n][0] * loop[i][1]
                       for i in range(n)) / 2)
    return out


def _winding(pt, loops):
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


def _round_26_6(x):
    """Nearest 1/64 unit, ties toward positive infinity."""
    return math.floor(x * 64 + 0.5) / 64


def _f32bits(x):
    return struct.unpack(">I", struct.pack(">f", x))[0]


def _oncurve_coords(commands):
    pts = []
    for cmd in commands:
        if cmd["op"] in ("move_to", "line_to"):
            pts.append((float(cmd["x"]), float(cmd["y"])))
        elif cmd["op"] in ("quad_to", "curve_to"):
            pts.append((float(cmd["x"]), float(cmd["y"])))
    return pts


def _project_pair(pair, coords, normal):
    a, b = pair["edges"][1], pair["edges"][-1]
    weights_a = ((a["i0"], 1 - pair["sa"]), (a["i1"], pair["sa"]))
    weights_b = ((b["i0"], 1 - pair["sb"]), (b["i1"], pair["sb"]))

    def at(weights):
        return (sum(coords[v][0] * w for v, w in weights),
                sum(coords[v][1] * w for v, w in weights))
    pa, pb = at(weights_a), at(weights_b)
    return (pa[0] - pb[0]) * normal[0] + (pa[1] - pb[1]) * normal[1]


def _coerce_glyph(glyph):
    """Normalized stroke arrays, or None for malformed input."""
    if not isinstance(glyph, dict):
        return None
    strokes = glyph.get("strokes")
    connectivity = glyph.get("connectivity")
    if (not isinstance(strokes, list) or not strokes
            or not isinstance(connectivity, dict)):
        return None
    clean = []
    for stroke in strokes:
        if not isinstance(stroke, dict):
            return None
        spine = _finite_array(stroke.get("spine"))
        radii = _finite_array(stroke.get("radii"))
        if (spine is None or spine.ndim != 2 or spine.shape[1] != 2
                or spine.shape[0] < 2 or radii is None or radii.ndim != 1
                or len(radii) != spine.shape[0] or (radii <= 0).any()):
            return None
        corners = stroke.get("corners")
        if corners is not None:
            try:
                corners = [int(c) for c in corners]
            except (TypeError, ValueError):
                return None
            if len(corners) != spine.shape[0]:
                corners = None
        clean.append({"spine": spine, "radii": radii, "corners": corners})
    return {"strokes": clean, "connectivity": connectivity}


def _contour_loops(parsed):
    """Per-contour vertex loops with straightness; curves stay separate.

    Inter-contour overlap is intended nonzero-winding ink, not a
    self-invalid outline: only self-crossing contours abstain.
    """
    loops, straight, curved_verts = [], [], set()
    for contour in parsed["contours"]:
        ok = all(seg[0] == "line" for seg in contour)
        straight.append(ok)
        if not ok:
            for seg in contour:
                for index in seg[1:]:
                    if isinstance(index, int):
                        curved_verts.add(index)
            loops.append(None)
            continue
        loop = []
        for seg in contour:
            if not loop:
                loop.append(parsed["oncurve"][seg[1]])
            loop.append(parsed["oncurve"][seg[2]])
        if loop and loop[0] == loop[-1]:
            loop.pop()
        loops.append(loop)
    return loops, straight, curved_verts


def _prepare(source_cmds, fitted_cmds, size_px, glyph, upem):
    """Shared per-glyph setup: claims, pairs, anchors, frozen sets."""
    glyph = _coerce_glyph(glyph)
    if glyph is None:
        return {"supported": False, "reason": "unsupported-analysis"}
    if not check_correspondence(source_cmds, fitted_cmds):
        return {"supported": False, "reason": "no-correspondence"}
    parsed = parse_commands(source_cmds)
    if not parsed["contours"]:
        return {"supported": False, "reason": "no-correspondence"}
    loops, straight, curved_verts = _contour_loops(parsed)
    if not any(straight):
        return {"supported": False, "reason": "unsupported-curves"}
    for loop in loops:
        if loop is not None and _proper_crossings([loop]) != 0:
            return {"supported": False, "reason": "crossing"}
    edges = [e for e in _straight_edges(parsed)
             if straight[e["contour"]]]
    loops = [loop for loop in loops if loop is not None]
    if any(not ok for ok in straight):
        # Slice-1 boundary: clearance against curved borders is outside
        # the segment dominance machinery, so straight pairs abstain.
        return {"supported": False, "reason": "unsupported-curves",
                "curved_contours": [i for i, ok in enumerate(straight)
                                    if not ok]}
    scale = size_px / upem
    runs = []
    for si, stroke in enumerate(glyph["strokes"]):
        spine = stroke["spine"] * scale
        radii = stroke["radii"] * scale
        for run in _split_runs(spine, radii, stroke.get("corners")):
            run["stroke"] = si
            runs.append(run)
    if not runs:
        return {"supported": False, "reason": "unsupported-analysis"}
    claims = _assign_edges(edges, runs)
    pairs, ambiguous = _form_pairs(edges, claims, runs)
    for pair in pairs:
        if "edges" in pair:
            _dominance(pair, edges, loops)
    fitted_coords = _oncurve_coords(fitted_cmds)
    if len(fitted_coords) != len(parsed["oncurve"]):
        return {"supported": False, "reason": "no-correspondence"}
    anchors = _anchor_candidates(pairs, runs, parsed, fitted_coords)
    anchor_runs = {a["pair"]["run"] for a in anchors}
    frozen, causes = _freeze_sets(edges, claims, runs,
                                  glyph["strokes"],
                                  glyph["connectivity"], scale)
    for pair in pairs:
        if "edges" not in pair:
            continue
        verts_a = {pair["edges"][1]["i0"], pair["edges"][1]["i1"]}
        verts_b = {pair["edges"][-1]["i0"], pair["edges"][-1]["i1"]}
        for vert in verts_a & verts_b:
            if vert not in frozen:
                frozen.add(vert)
                causes[vert] = "common-tip"
    return {"supported": True, "parsed": parsed, "edges": edges,
            "loops": loops, "runs": runs, "claims": claims,
            "pairs": pairs, "ambiguous": ambiguous, "anchors": anchors,
            "anchor_runs": anchor_runs, "frozen": frozen, "causes": causes,
            "fitted_coords": fitted_coords, "scale": scale}


def describe_glyph(char, source_cmds, fitted_cmds):
    """Source-outline eligibility without stroke grouping.

    Reports straight contours, per-contour self-crossings, ungrouped
    rectilinear pairs with integral fitted bounds (anchor-potential
    evidence only, never a reference), and straight diagonal edges.
    Imported stroke grouping is still required to fit anything.
    """
    if not check_correspondence(source_cmds, fitted_cmds):
        return {"char": char, "eligible": False, "reason": "no-correspondence"}
    parsed = parse_commands(source_cmds)
    loops, straight, _ = _contour_loops(parsed)
    fitted_coords = _oncurve_coords(fitted_cmds)
    if len(fitted_coords) != len(parsed["oncurve"]):
        return {"char": char, "eligible": False, "reason": "no-correspondence"}
    contours = []
    for ci, loop in enumerate(loops):
        contours.append({"straight": straight[ci],
                         "self_crossing": loop is not None
                         and _proper_crossings([loop]) != 0,
                         "edges": sum(1 for seg in parsed["contours"][ci]
                                      if seg[0] == "line")})
    edges = [e for e in _straight_edges(parsed) if straight[e["contour"]]]
    loops_all = [loop for loop in loops if loop is not None]
    potential = []
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            a, b = edges[i], edges[j]
            if a["contour"] != b["contour"]:
                continue
            axis_a, axis_b = _axis_of(a), _axis_of(b)
            if axis_a is None or axis_a != axis_b:
                continue
            if a["dir"][0] * b["dir"][0] + a["dir"][1] * b["dir"][1] >= 0:
                continue
            axis = axis_a
            verts = (a["i0"], a["i1"], b["i0"], b["i1"])
            vals = [fitted_coords[v][0 if axis == "x" else 1]
                    for v in verts]
            if not all(float(v).is_integer() for v in vals):
                continue
            key_a = (a["contour"], a["seg"])
            key_b = (b["contour"], b["seg"])
            medial = _medial_anchor(a, b, key_a, key_b, edges, loops_all)
            if medial is None:
                continue
            ws, normal, _ = medial
            fa = tuple((fitted_coords[a["i0"]][d]
                        + fitted_coords[a["i1"]][d]) / 2 for d in (0, 1))
            fb = tuple((fitted_coords[b["i0"]][d]
                        + fitted_coords[b["i1"]][d]) / 2 for d in (0, 1))
            wf = (fa[0] - fb[0]) * normal[0] + (fa[1] - fb[1]) * normal[1]
            potential.append({"axis": axis, "ws": ws, "wf": wf,
                              "rel": (wf - ws) / ws})
    diagonals = sum(1 for e in edges if _axis_of(e) is None)
    return {"char": char, "eligible": True, "reason": None,
            "contours": contours, "anchor_potential": potential,
            "diagonal_edges": diagonals}


def _pair_class(pair):
    edges = [pair["edges"][1], pair["edges"][-1]]
    axes = [_axis_of(e) for e in edges]
    if axes[0] is not None and axes[0] == axes[1]:
        return "upright"
    return "diagonal"


def build_reference(cases):
    """Font-wide upright standard from automatically recognized anchors.

    Every case carries same-group font, axes and size; no character is
    special-cased. The median relative change is the (17) reference.
    """
    rels, contributors = [], []
    detail = []
    for case in cases:
        try:
            prep = _prepare(case["source_cmds"], case["fitted_cmds"],
                            case["size_px"], case["analysis"], case["upem"])
        except (KeyError, TypeError, ValueError):
            detail.append({"char": case.get("char"), "anchors": 0,
                           "reason": "unsupported-analysis"})
            continue
        if not prep["supported"]:
            detail.append({"char": case.get("char"), "anchors": 0,
                           "reason": prep["reason"]})
            continue
        found = []
        for anchor in prep["anchors"]:
            dom = anchor["pair"].get("dom") or {}
            speed = dom.get("speed") or 0.0
            spans = [iv["hi"] - iv["lo"] for iv in dom.get("intervals", [])]
            arc = max(spans) * speed if spans and speed > 0 else 0.0
            if arc <= 0:
                continue
            tangent = anchor["pair"]["edges"][1]["dir"]
            found.append({"anchor": anchor, "arc": arc, "tangent": tangent})
        if not found:
            detail.append({"char": case.get("char"), "anchors": 0,
                           "reason": "no-upright-anchor"})
            continue
        for entry in found:
            rels.append((entry["anchor"]["rel"], entry))
            contributors.append(case.get("char"))
        detail.append({"char": case.get("char"), "anchors": len(found),
                       "reason": None})
    if not rels:
        return {"supported": False, "reason": "no-upright-reference",
                "detail": detail}
    rels.sort(key=lambda item: item[0])
    median = rels[len(rels) // 2][1]
    widths = sorted(e[1]["anchor"]["ws"] for e in rels)
    lengths = sorted(e[1]["arc"] for e in rels)
    return {"supported": True, "rel": median["anchor"]["rel"],
            "width": widths[len(widths) // 2],
            "length": lengths[len(lengths) // 2],
            "tangent": median["tangent"], "contributors": contributors,
            "spread": [rels[0][0], rels[-1][0]], "detail": detail}


def _collect_stations(pair, edges, loops, system):
    """Third-split stations with rechecked disks (production count 3)."""
    dom = pair.get("dom") or {}
    if dom.get("status") != "ok" or not dom.get("intervals"):
        return None, "no-dominance"
    speed = dom.get("speed") or 0.0
    if not speed > 0:
        return None, "station-invalid"
    seg_a = (tuple(pair["edges"][1]["p0"]), tuple(pair["edges"][1]["p1"]))
    seg_b = (tuple(pair["edges"][-1]["p0"]), tuple(pair["edges"][-1]["p1"]))
    others = _other_borders(edges, set(pair["keys"]))
    hits, failed = [], []
    for ivl in dom["intervals"]:
        span = ivl["hi"] - ivl["lo"]
        for frac in (1 / 6, 1 / 2, 5 / 6):
            out = intervals.contact(seg_a, seg_b, ivl["lo"] + frac * span,
                                    others, loops)
            if out["hit"] is None:
                failed.append({"t": ivl["lo"] + frac * span,
                               "stage": out["stage"], "tag": out["tag"]})
                continue
            arc = span / 3 * speed
            if not arc > 0:
                failed.append({"t": ivl["lo"] + frac * span,
                               "stage": "degenerate-arc", "tag": None})
                continue
            hits.append({"hit": out["hit"], "arc": arc,
                         "t": ivl["lo"] + frac * span})
    if failed or not hits:
        return None, "station-invalid"
    edge_a, edge_b = pair["edges"][1], pair["edges"][-1]
    stationed = []
    for entry in hits:
        hit = entry["hit"]
        sample_a = Sample(((edge_a["i0"], 1 - hit["sa"]),
                           (edge_a["i1"], hit["sa"])))
        sample_b = Sample(((edge_b["i0"], 1 - hit["sb"]),
                           (edge_b["i1"], hit["sb"])))
        stationed.append(system.pair(sample_a, sample_b, entry["arc"],
                                     kind="ink", medial=hit["center"]))
    return {"pairs": stationed, "hits": hits}, None


def run_glyph(char, source_cmds, fitted_cmds, size_px, glyph, upem,
              reference, native_axes=(False, False)):
    """Couple imported straight diagonals to the font-wide upright standard.

    Native-owned coordinates and selected upright anchors stay exactly
    upstream, including after 26.6 quantization. Advances, contour order
    and outline operators are preserved exactly. Unsupported geometry
    keeps the upstream outline with an explicit reason.
    """
    prep = _prepare(source_cmds, fitted_cmds, size_px, glyph, upem)
    if not prep["supported"]:
        return {"applied": False, "reason": prep["reason"], "char": char}
    if not isinstance(reference, dict) or not reference.get("supported"):
        return {"applied": False, "reason": "no-upright-reference",
                "char": char}
    parsed, edges, loops = prep["parsed"], prep["edges"], prep["loops"]
    runs = prep["runs"]
    fitted_coords = prep["fitted_coords"]
    anchor_verts = set()
    for anchor in prep["anchors"]:
        anchor_verts |= anchor["verts"]
    diagonal, skipped = [], []
    for pair in prep["pairs"]:
        if "edges" not in pair:
            skipped.append({"run": pair.get("run"),
                            "reason": pair.get("skipped",
                                               "unsupported-pair")})
            continue
        if pair["run"] in prep["anchor_runs"]:
            continue
        if _pair_class(pair) != "diagonal":
            skipped.append({"run": pair["run"],
                            "reason": "unfitted-upright"})
            continue
        diagonal.append(pair)
    if not diagonal:
        reason = skipped[0]["reason"] if skipped else "no-related-pair"
        return {"applied": False, "reason": reason, "char": char,
                "skipped": skipped,
                "anchors": len(prep["anchors"])}
    base = [list(p) for p in parsed["oncurve"]]
    base_arr = np.asarray(base, dtype=float)
    upstream = np.asarray(fitted_coords, dtype=float)
    system = System(base, size_px)
    for contour in parsed["contours"]:
        for seg in contour:
            if seg[0] == "line":
                system.edge(seg[1], seg[2])
    # Post-fit position reference: source coefficients stay fixed while
    # geometry residuals vanish at the upstream fit (Hobby model-arm
    # adaptation from the owning real-outline experiment).
    shift = (upstream - base_arr).ravel()
    reshaped = []
    for group, row, const in system.rows:
        if group in ("position", "stretch", "bend"):
            const = const - float(row @ shift)
        reshaped.append((group, row, const))
    system.rows = reshaped
    # Scalar (17) adaptation: every related station couples to the
    # font-wide anchor standard by arc-length products; the anchor error
    # joins the constants, never refit coefficients. Tangents meet at
    # the acute angle since spine order carries no orientation.
    ref_tangent = np.asarray(reference["tangent"], dtype=float)
    coupled = []
    for pair in diagonal:
        stations, error = _collect_stations(pair, edges, loops, system)
        if error is not None:
            skipped.append({"run": pair["run"], "reason": error})
            continue
        run_tangent = np.asarray(runs[pair["run"]]["tangent"], dtype=float)
        if float(np.dot(run_tangent, ref_tangent)) < 0:
            run_tangent = -run_tangent
        for station, entry in zip(stations["pairs"], stations["hits"]):
            psi = width_weight(station.width, reference["width"],
                               run_tangent, ref_tangent, size_px)
            weight = entry["arc"] * reference["length"] * psi
            # Hobby (5) error is the negative projected change, so the
            # anchor's relative change enters with a positive constant.
            system.add("ink-match",
                       station.error * math.sqrt(weight),
                       reference["rel"] * math.sqrt(weight))
        pair["stations"] = stations
        coupled.append(pair)
    if not coupled:
        reason = skipped[-1]["reason"] if skipped else "no-related-pair"
        return {"applied": False, "reason": reason, "char": char,
                "skipped": skipped,
                "anchors": len(prep["anchors"])}
    frozen = set(prep["frozen"])
    fixed = {}
    for vert in range(len(base)):
        delta = (float(upstream[vert][0] - base_arr[vert][0]),
                 float(upstream[vert][1] - base_arr[vert][1]))
        if vert in frozen or vert in anchor_verts:
            fixed[(vert, 0)] = delta[0]
            fixed[(vert, 1)] = delta[1]
        else:
            if native_axes[0]:
                fixed[(vert, 0)] = delta[0]
            if len(native_axes) > 1 and native_axes[1]:
                fixed[(vert, 1)] = delta[1]
    for pair in coupled:
        for side in (1, -1):
            edge = pair["edges"][side]
            movable = [v for v in (edge["i0"], edge["i1"])
                       if (v, 0) not in fixed or (v, 1) not in fixed]
            if not movable:
                skipped.append({"run": pair["run"],
                                "reason": "junction-locked"})
    coupled = [p for p in coupled
               if not any(s.get("run") == p["run"] and
                          s.get("reason") == "junction-locked"
                          for s in skipped)]
    if not coupled:
        return {"applied": False, "reason": "junction-locked", "char": char,
                "skipped": skipped,
                "anchors": len(prep["anchors"])}
    related_verts = set()
    for pair in coupled:
        related_verts |= {pair["edges"][1]["i0"], pair["edges"][1]["i1"],
                          pair["edges"][-1]["i0"], pair["edges"][-1]["i1"]}
    retained = []
    for pair in coupled:
        retained.extend(e["hit"]["width"] for e in pair["stations"]["hits"])
    bound = 0.5 * min(retained) - HEADROOM
    if not bound > 0:
        return {"applied": False, "reason": "movement-budget-exhausted",
                "char": char, "bound": bound,
                "anchors": len(prep["anchors"])}
    solved = _solve_coordinates(system, fixed)
    optimum = base_arr + solved["delta"].reshape(-1, 2)
    free = sorted({v for v in range(len(base))
                   if (v, 0) not in fixed or (v, 1) not in fixed})
    dev = [math.hypot(optimum[v][0] - upstream[v][0],
                       optimum[v][1] - upstream[v][1]) for v in free]
    maxdev = max(dev) if dev else 0.0
    prefix = 1.0 if maxdev == 0 else max(0.0, min(1.0, bound / maxdev))
    cand_float = [list(map(float, upstream[v])) for v in range(len(base))]
    for vert in free:
        step = prefix * (optimum[vert] - upstream[vert])
        cand_float[vert] = [float(upstream[vert][0] + step[0]),
                            float(upstream[vert][1] + step[1])]
    cand_rounded = []
    for vert in range(len(base)):
        if (vert, 0) in fixed and (vert, 1) in fixed:
            cand_rounded.append([float(upstream[vert][0]),
                                 float(upstream[vert][1])])
        else:
            cand_rounded.append([
                _round_26_6(cand_float[vert][0])
                if (vert, 0) not in fixed else float(upstream[vert][0]),
                _round_26_6(cand_float[vert][1])
                if (vert, 1) not in fixed else float(upstream[vert][1])])
    movement = max([math.hypot(cand_rounded[v][0] - fitted_coords[v][0],
                               cand_rounded[v][1] - fitted_coords[v][1])
                    for v in related_verts]) if related_verts else 0.0
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
                "char": char, "movement": movement, "bound": bound,
                "prefix": prefix, "cost_upstream": cost_upstream,
                "cost_candidate": cost_candidate}
    if not cost_candidate < cost_upstream:
        return {"applied": False, "reason": "no-cost-decrease",
                "char": char, "movement": movement, "bound": bound,
                "prefix": prefix, "cost_upstream": cost_upstream,
                "cost_candidate": cost_candidate}
    # Project hypothesis over Hobby (5)/(17), not a bound from the paper:
    # stations of one pair aim at a common relative width change, so
    # contradictory achieved values (narrowing one end while widening
    # the other) mark an incoherent pair even when cost, movement and
    # validity gates pass. The bar reuses the movement budget computed
    # above: internal disagreement wider than the allowed absolute
    # motion, normalized by local width, fails closed. This conservative
    # abstention rule has no optical guarantee; wider pairs face the
    # stricter bar because the budget uses the narrowest retained width.
    flat_candidate = (np.asarray(cand_rounded, dtype=float)
                      - base_arr).ravel()
    coherence = []
    for pair in coupled:
        achieved = [float(station.error @ flat_candidate)
                    for station in pair["stations"]["pairs"]]
        spread = max(achieved) - min(achieved)
        ws_rep = pair["stations"]["hits"][0]["hit"]["width"]
        limit = bound / ws_rep
        coherence.append({"run": pair["run"], "spread": spread,
                          "limit": limit, "achieved": achieved})
        if spread > limit:
            return {"applied": False, "reason": "incoherent-stations",
                    "char": char, "movement": movement, "bound": bound,
                    "prefix": prefix, "cost_upstream": cost_upstream,
                    "cost_candidate": cost_candidate,
                    "coherence": coherence,
                    "candidate_commands": [dict(c) for c in fitted_cmds]}
    out = [dict(c) for c in source_cmds]
    index = 0
    for cmd in out:
        if cmd["op"] in ("move_to", "line_to"):
            cmd["x"], cmd["y"] = cand_rounded[index]
            index += 1
        elif cmd["op"] in ("quad_to", "curve_to"):
            cmd["x"], cmd["y"] = cand_rounded[index]
            index += 1
    for cmd in out:
        for key in ("x", "y", "x1", "y1", "x2", "y2"):
            if key in cmd:
                cmd[key + "_bits"] = _f32bits(cmd[key])
    cand_parsed = parse_commands(out)
    cand_loops = loops_parsed(cand_parsed, cand_rounded)
    cand_float_loops = loops_parsed(cand_parsed, cand_float)
    src_areas = _signed_areas(prep["loops"])
    cand_areas = _signed_areas(cand_loops)
    float_areas = _signed_areas(cand_float_loops)
    signs_ok = all((a > 0) == (b > 0) and abs(b) > 0
                   for a, b in zip(src_areas, cand_areas))
    crossings_ok = (_proper_crossings(cand_loops)
                    == _proper_crossings(prep["loops"]))
    contained_ok = True
    for i, loop in enumerate(prep["loops"]):
        for j, other in enumerate(prep["loops"]):
            if i != j and _winding(loop[0], [other]) != 0:
                if _winding(cand_loops[i][0], [cand_loops[j]]) == 0:
                    contained_ok = False
    float_ok = (all((a > 0) == (b > 0) and abs(a) > 0
                    for a, b in zip(src_areas, float_areas))
                and _proper_crossings(cand_float_loops)
                == _proper_crossings(prep["loops"]))
    validity = {"signs": signs_ok, "crossings": crossings_ok,
                "containment": contained_ok, "float": float_ok}
    if not (signs_ok and crossings_ok and contained_ok and float_ok):
        # Fallback keeps the exact upstream outline; an invalid
        # candidate is never emitted.
        return {"applied": False, "reason": "validity-failed", "char": char,
                "validity": validity, "movement": movement, "bound": bound,
                "candidate_commands": [dict(c) for c in fitted_cmds]}
    normal_of = {}
    for pair in coupled:
        hit = pair["stations"]["hits"][0]["hit"]
        chord = (hit["qa"][0] - hit["qb"][0], hit["qa"][1] - hit["qb"][1])
        dist = math.hypot(*chord)
        normal_of[pair["run"]] = (chord[0] / dist, chord[1] / dist)
    widths = []
    for pair in coupled:
        normal = normal_of[pair["run"]]
        pair["sa"] = pair["stations"]["hits"][0]["hit"]["sa"]
        pair["sb"] = pair["stations"]["hits"][0]["hit"]["sb"]
        ws = pair["stations"]["hits"][0]["hit"]["width"]
        wf = _project_pair(pair, fitted_coords, normal)
        wc = _project_pair(pair, cand_rounded, normal)
        widths.append({"run": pair["run"], "ws": ws, "wf_upstream": wf,
                       "expected": ws * (1 + reference["rel"]),
                       "candidate": wc,
                       "upstream_rel": (wf - ws) / ws,
                       "candidate_rel": (wc - ws) / ws,
                       "target_rel": reference["rel"]})
    fixed_points = sorted("%d.%s" % (v, a) for v, a in fixed)
    causes = dict(prep["causes"])
    for vert in anchor_verts:
        causes.setdefault(vert, "anchor")
    for (vert, axis) in fixed:
        if vert not in causes:
            causes[vert] = "native-axis"
    return {"applied": True, "reason": None, "char": char,
            "widths": widths, "reference": {
                "rel": reference["rel"], "width": reference["width"],
                "length": reference["length"],
                "contributors": reference["contributors"]},
            "movement": movement, "bound": bound, "validity": validity,
            "fixed": fixed_points,
            "frozen_causes": {str(v): causes[v]
                              for v in sorted(set(v for v, _ in fixed))},
            "rank": solved["rank"],
            "free_variables": solved["free_variables"],
            "residuals": solved["squared_residuals"],
            "prefix": prefix, "cost_upstream": cost_upstream,
            "cost_candidate": cost_candidate,
            "coherence": coherence,
            "skipped": skipped,
            "anchors": len(prep["anchors"]),
            "native_axes": list(native_axes),
            "candidate_commands": out}
