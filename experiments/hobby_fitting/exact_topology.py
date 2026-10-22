"""Exact filled-join verification (CGAL arrangement reference).

Public schema (shared with the test worker):
  analyze_commands(commands, binary=None) -> dict with keys
    supported: bool; reason: str;
    signature: dict or None; details: dict.
  signature keys: filled_components, holes, filled_area ("p/q",
    evidence only), hole_areas (evidence), seam_chains (count),
    pinch_vertices (count), point_contacts (canonical multiset of
    contour-label sides), components (per filled component:
    contours, area evidence, holes count).
  compare_commands(source, upstream, candidate, binary=None) ->
    dict with keys supported, ok, reason, source/upstream/candidate
    (analyses), source_upstream_match (bool), diff (or None).

Straight directed loops only; curves, empty and degenerate inputs
fail closed without invoking the reference. Coordinates travel as
exact rationals from float.as_integer_ratio, never resnapped, so
native off-grid positions keep their bits. The binary default is
out/diagnostics/direct-diagonal/exact-topology/bin/exact_topology;
HOBBY_EXACT_TOPOLOGY_BINARY overrides it.
"""

import json
import math
import os
import subprocess

from experiments.hobby_fitting.real_outline import parse_commands

DEFAULT_BINARY = os.path.join(
    "out", "diagnostics", "direct-diagonal", "exact-topology",
    "bin", "exact_topology")


def _resolve_binary(binary):
    if binary is not None:
        return binary
    return os.environ.get("HOBBY_EXACT_TOPOLOGY_BINARY", DEFAULT_BINARY)


def _rational(value):
    """Exact p/q string; non-finite inputs are unsupported."""
    if not math.isfinite(value):
        return None
    num, den = float(value).as_integer_ratio()
    return "%d/%d" % (num, den)


def _strict_commands(commands):
    """Closed command grammar; anything else fails closed.

    Unknown ops, lines without an open move, closes without opens,
    moves while a contour is open, trailing open contours, missing
    coordinates and non-finite values are all malformed; curved ops
    in valid positions report curves-unsupported instead. The
    permissive outline parser is never trusted for admission.
    """
    if not isinstance(commands, list):
        return "malformed-commands"
    kinds = {"move_to": ("x", "y"), "line_to": ("x", "y"),
             "quad_to": ("x1", "y1", "x", "y"),
             "curve_to": ("x1", "y1", "x2", "y2", "x", "y"),
             "close": ()}
    for cmd in commands:
        if not isinstance(cmd, dict):
            return "malformed-commands"
        if cmd.get("op") not in kinds:
            return "malformed-commands"
        for key in kinds[cmd["op"]]:
            value = cmd.get(key)
            if not isinstance(value, (int, float)):
                return "malformed-commands"
            if not math.isfinite(value):
                return "nonfinite-coordinate"
    open_contour = False
    for cmd in commands:
        op = cmd["op"]
        if op == "move_to":
            if open_contour:
                return "malformed-commands"
            open_contour = True
        elif op == "close":
            if not open_contour:
                return "malformed-commands"
            open_contour = False
        elif not open_contour:
            return "malformed-commands"
    if open_contour:
        return "malformed-commands"
    for cmd in commands:
        if cmd["op"] in ("quad_to", "curve_to"):
            return "curves-unsupported"
    return None


def _directed_edges(commands):
    """Straight directed edges with contour labels, or a reason.

    Exact zero-length edges contribute nothing to winding or area
    and are dropped with a count; anything curved fails closed.
    """
    reason = _strict_commands(commands)
    if reason is not None:
        return None, reason
    try:
        parsed = parse_commands(commands)
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        return None, "malformed-commands"
    edges, dropped = [], 0
    for label, contour in enumerate(parsed["contours"]):
        for seg in contour:
            if seg[0] != "line":
                return None, "curves-unsupported"
            p0 = parsed["oncurve"][seg[1]]
            p1 = parsed["oncurve"][seg[2]]
            if p0[0] == p1[0] and p0[1] == p1[1]:
                dropped += 1
                continue
            box = [_rational(v) for v in (p0[0], p0[1], p1[0], p1[1])]
            if any(v is None for v in box):
                return None, "nonfinite-coordinate"
            edges.append({"coords": box, "contour": label})
    if not edges:
        return None, "degenerate-input"
    return {"edges": edges, "dropped_degenerate": dropped}, None


def _run_checker(payload, binary):
    """Run the reference binary on plaintext rational input."""
    text = ["%d" % len(payload["edges"])]
    for edge in payload["edges"]:
        text.append(" ".join(edge["coords"] + [str(edge["contour"])]))
    try:
        proc = subprocess.run(
            [binary], input="\n".join(text) + "\n", capture_output=True,
            text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None, "reference-failure: cannot execute binary"
    if proc.returncode != 0:
        return None, "reference-failure: exit %d %s" % (
            proc.returncode, proc.stderr.strip()[:200])
    try:
        report = json.loads(proc.stdout)
    except ValueError:
        return None, "reference-failure: unparsable output"
    if not isinstance(report, dict) or "supported" not in report:
        return None, "reference-failure: malformed report"
    return report, None


def _canonical_contact(contact):
    sides = [tuple(sorted(side)) for side in contact["sides"]]
    return tuple(sorted(sides))


def _signature(report):
    """Comparison-stable invariants; areas are evidence only.

    Seam chains stay diagnostic: internal seams may move under
    harmless resegmentation, so attachment is carried by per-pair
    contact classes, hole boundary labels and the pinch roster.
    """
    contacts = sorted(_canonical_contact(c)
                      for c in report.get("point_contacts", []))
    components = sorted(
        (tuple(sorted(c["contours"])), c["holes"])
        for c in report.get("components", []))
    pinches = sorted(
        (p["degree"],
         tuple(sorted(tuple(sorted(s)) for s in p["components"])))
        for p in report.get("pinch_vertices", []))
    holes = sorted(
        tuple(sorted(h.get("adjacent", [])))
        for h in report.get("holes", []))
    pairs = sorted(
        (tuple(p["pair"]), p["area_components"], p["area_holes"],
         p["edge_components"], p["point_contacts"],
         tuple(p.get("boundary_degrees", [])))
        for p in report.get("pairs", []))
    return {
        "filled_components": len(report.get("components", [])),
        "holes": sum(1 for _ in report.get("holes", [])),
        "filled_area": report.get("total_filled_area"),
        "hole_areas": [h["area"] for h in report.get("holes", [])],
        "seam_chains": len(report.get("seam_chains", [])),
        "pinch_vertices": len(report.get("pinch_vertices", [])),
        "pinch_roster": [{"degree": degree,
                          "components": [list(s) for s in sides]}
                         for degree, sides in pinches],
        "point_contacts": [{"sides": [list(s) for s in sides]}
                           for sides in contacts],
        "hole_boundaries": [list(h) for h in holes],
        "pairs": [{"pair": list(pair), "area_components": ac,
                   "area_holes": ah, "edge_components": ec,
                   "point_contacts": pc, "boundary_degrees": list(bd)}
                  for pair, ac, ah, ec, pc, bd in pairs],
        "components": [{"contours": list(contours), "holes": holes}
                       for contours, holes in components],
    }


def analyze_commands(commands, binary=None):
    """Classify the filled shape of straight directed loops."""
    payload, reason = _directed_edges(commands)
    if reason is not None:
        return {"supported": False, "reason": reason,
                "signature": None, "details": {}}
    path = _resolve_binary(binary)
    if not (os.path.isfile(path) and os.access(path, os.X_OK)):
        return {"supported": False, "reason": "binary-missing",
                "signature": None,
                "details": {"binary": path,
                            "dropped_degenerate":
                            payload["dropped_degenerate"]}}
    report, reason = _run_checker(payload, path)
    if reason is not None:
        return {"supported": False, "reason": reason,
                "signature": None, "details": {"binary": path}}
    if not report.get("supported"):
        return {"supported": False,
                "reason": report.get("reason", "reference-failure"),
                "signature": None, "details": {"binary": path}}
    return {"supported": True, "reason": "classified",
            "signature": _signature(report),
            "details": {"binary": path,
                        "dropped_degenerate":
                        payload["dropped_degenerate"],
                        "filled_area": report.get("total_filled_area"),
                        "pinch": report.get("pinch_vertices", []),
                        "seams": report.get("seam_chains", [])}}


def _structural_key(signature):
    return (
        signature["filled_components"],
        signature["holes"],
        tuple((p["degree"], tuple(tuple(s) for s in p["components"]))
              for p in signature["pinch_roster"]),
        tuple(tuple(tuple(side) for side in c["sides"])
              for c in signature["point_contacts"]),
        tuple((tuple(c["contours"]), c["holes"])
        for c in signature["components"]),
        tuple(tuple(h) for h in signature["hole_boundaries"]),
        tuple((tuple(p["pair"]), p["area_components"],
               p["area_holes"], p["edge_components"],
               p["point_contacts"],
               tuple(p.get("boundary_degrees", [])))
              for p in signature["pairs"]),
    )


def compare_commands(source_commands, upstream_commands,
                     candidate_commands, binary=None):
    """Strict candidate-vs-upstream comparison; source reported."""
    source = analyze_commands(source_commands, binary=binary)
    upstream = analyze_commands(upstream_commands, binary=binary)
    candidate = analyze_commands(candidate_commands, binary=binary)
    if not (source["supported"] and upstream["supported"]
            and candidate["supported"]):
        reasons = {k: v["reason"] for k, v in
                   (("source", source), ("upstream", upstream),
                    ("candidate", candidate)) if not v["supported"]}
        return {"supported": False, "ok": False,
                "reason": "unsupported-input",
                "source": source, "upstream": upstream,
                "candidate": candidate, "source_upstream_match": False,
                "diff": {"unsupported": reasons}}
    source_match = (_structural_key(source["signature"])
                    == _structural_key(upstream["signature"]))
    if (_structural_key(candidate["signature"])
            == _structural_key(upstream["signature"])):
        return {"supported": True, "ok": True, "reason": "match",
                "source": source, "upstream": upstream,
                "candidate": candidate,
                "source_upstream_match": source_match, "diff": None}
    return {"supported": True, "ok": False,
            "reason": "upstream-candidate-mismatch",
            "source": source, "upstream": upstream,
            "candidate": candidate,
            "source_upstream_match": source_match,
            "diff": {"upstream": upstream["signature"],
                     "candidate": candidate["signature"]}}
