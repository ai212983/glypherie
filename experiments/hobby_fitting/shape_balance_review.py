#!/usr/bin/env python3
"""Isolated shape-balance comparison: upstream, preferred width-only, placement.

Reads the frozen border-interval coverage packet and the matching
text-review ASCII captures without rewriting either. The preferred arm
replays the coverage candidate (native-ported width-only) pixels and
commands exactly. The placement arm calls the symmetry module behind
its planned ``fit`` entry point; while that module is unavailable every
placement glyph abstains with the import error recorded and the
preferred commands reproduced bit-for-bit. The curve arm is not wired
here: curved-width fitting stays upstream until its owning module
exists, and no curve result is fabricated.

Hobby section 3.5, (14)-(16), supplies approximate reflection
correspondence; Hersch sections 5-6 supplies grid-compatible
symmetry-center placement.
"""

import argparse
import hashlib
import json
import os
import struct
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

TOOL_VERSION = "shape-balance-review-v1"
BASELINE_TOOL = "coverage-review-v1"
BASELINE_DIR = os.path.join("out", "diagnostics", "direct-diagonal",
                            "coverage-review")
ASCII_DIR = os.path.join("out", "diagnostics", "direct-diagonal",
                         "text-review", "ascii-captures")
DEFAULT_OUT = os.path.join("out", "diagnostics", "shape-balance-review")
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "shape_balance_review.html")

VALID_OPS = ("move_to", "line_to", "quad_to", "curve_to", "close")
PLACEMENT_MODULE = "experiments.hobby_fitting.symmetry_placement"
CURVE_MODULE = "experiments.hobby_fitting.curve_contacts"
ARM_CONTROL = "strict-quantum"
ARM_PHASE = "phase-range"
_ALLOWED_ARMS = (ARM_CONTROL, ARM_PHASE)
SPOT_CODES = (120, 115)
CURVE_DEPS = ("experiments/hobby_fitting/curved_width.py",
              "experiments/hobby_fitting/curve_contacts.py",
              "experiments/hobby_fitting/prototype.py",
              "experiments/hobby_fitting/exact_topology.py",
              "experiments/hobby_fitting/intervals.py",
              "experiments/hobby_fitting/curve_clearance.py")
DEFAULT_TOPOLOGY_BINARY = os.path.join("out", "diagnostics",
                                       "direct-diagonal", "exact-topology",
                                       "bin", "exact_topology")


def fail(message):
    raise SystemExit("shape-balance-review: " + message)


def sha_file(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def sha_json(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True).encode()).hexdigest()


def f32_bits(value):
    return struct.unpack("=I", struct.pack("=f", value))[0]


def is_finite_number(value):
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float)) and value == value \
        and value not in (float("inf"), float("-inf"))


def strict_bool(value):
    return isinstance(value, bool)


def validate_native_axes(native_axes):
    """Native ownership must be exactly two booleans; fail closed."""
    if not isinstance(native_axes, (list, tuple)) or len(native_axes) != 2 \
            or not all(strict_bool(a) for a in native_axes):
        fail("malformed native_axes %r; want [bool, bool]"
             % (native_axes,))
    return (native_axes[0], native_axes[1])


COORD_FIELDS = {"move_to": ("x", "y"), "line_to": ("x", "y"),
                "quad_to": ("x1", "y1", "x", "y"),
                "curve_to": ("x1", "y1", "x2", "y2", "x", "y")}


def valid_coord(cmd, key):
    if not is_finite_number(cmd.get(key)):
        return False
    bits = cmd.get(key + "_bits")
    if not isinstance(bits, int) or isinstance(bits, bool) \
            or not 0 <= bits <= 0xFFFFFFFF:
        return False
    try:
        return f32_bits(float(cmd[key])) == bits
    except (OverflowError, struct.error):
        return False


def valid_command(cmd):
    if not isinstance(cmd, dict):
        return False
    if cmd.get("op") not in VALID_OPS:
        return False
    if cmd.get("op") == "close":
        return True
    return all(valid_coord(cmd, key)
               for key in COORD_FIELDS[cmd["op"]])


def commands_equal(first, second):
    return json.dumps(first, sort_keys=True) == \
        json.dumps(second, sort_keys=True)


def same_skeleton(upstream, candidate):
    if len(upstream) != len(candidate):
        return False
    return all(u.get("op") == c.get("op")
               for u, c in zip(upstream, candidate))


def pinned_axes(native_axes):
    axes = list(native_axes or [False, False])[:2]
    while len(axes) < 2:
        axes.append(False)
    return tuple(bool(a) for a in axes)


X_KEYS = ("x", "x1", "x2")
Y_KEYS = ("y", "y1", "y2")


def respects_pins(upstream, candidate, native_axes):
    """Native-owned coordinates keep exact f32 bits, including signed zero."""
    pin_x, pin_y = pinned_axes(native_axes)
    if not (pin_x or pin_y):
        return True
    if not same_skeleton(upstream, candidate):
        return False
    for u, c in zip(upstream, candidate):
        if u.get("op") == "close":
            continue
        if pin_x and any(c.get(k + "_bits") != u.get(k + "_bits")
                         for k in X_KEYS if k + "_bits" in u):
            return False
        if pin_y and any(c.get(k + "_bits") != u.get(k + "_bits")
                         for k in Y_KEYS if k + "_bits" in u):
            return False
    return True


def segment_lengths(commands):
    """Straight-segment lengths in command order; None when curved."""
    lengths = []
    pen = start = None
    for cmd in commands:
        op = cmd.get("op")
        if op == "move_to":
            pen = start = (float(cmd["x"]), float(cmd["y"]))
        elif op == "line_to":
            nxt = (float(cmd["x"]), float(cmd["y"]))
            lengths.append(((nxt[0] - pen[0]) ** 2
                            + (nxt[1] - pen[1]) ** 2) ** 0.5)
            pen = nxt
        elif op in ("quad_to", "curve_to"):
            return None
        elif op == "close":
            if pen is not None and start is not None and pen != start:
                lengths.append(((start[0] - pen[0]) ** 2
                                + (start[1] - pen[1]) ** 2) ** 0.5)
            pen = start = None
        else:
            return None
    return lengths


def verify_applied(preferred, commands, native_axes):
    """Fail closed unless the applied result is an exact rigid shift."""
    if not same_skeleton(preferred, commands):
        fail("placement changed the command skeleton")
    if not all(valid_command(c) for c in commands):
        fail("placement returned invalid commands or f32 bits")
    if not respects_pins(preferred, commands, native_axes):
        fail("placement moved native-owned coordinate bits")
    old, new = segment_lengths(preferred), segment_lengths(commands)
    if old is None or new is None or len(old) != len(new):
        fail("placement width check needs straight outlines")
    if max([0.0] + [abs(a - b) for a, b in zip(old, new)]) > 1e-9:
        fail("placement deformed straight-segment lengths")


def max_shift(upstream, candidate):
    # Upstream-to-candidate endpoint displacement only; Hobby's point
    # movement measure, not a distance between whole shapes.
    peak = 0.0
    per_axis = [0.0, 0.0]
    if not same_skeleton(upstream, candidate):
        return peak, per_axis
    for u, c in zip(upstream, candidate):
        if u.get("op") == "close":
            continue
        try:
            dx = abs(float(c["x"]) - float(u["x"]))
            dy = abs(float(c["y"]) - float(u["y"]))
        except (KeyError, TypeError, ValueError):
            return peak, per_axis
        per_axis[0] = max(per_axis[0], dx)
        per_axis[1] = max(per_axis[1], dy)
        peak = max(peak, (dx * dx + dy * dy) ** 0.5)
    return peak, per_axis


def load_placement_module(name=PLACEMENT_MODULE):
    """Import the symmetry module; report absence instead of skipping."""
    import importlib

    try:
        return importlib.import_module(name), None
    except ImportError as exc:
        return None, "%s unavailable: %s" % (name, exc)


def call_placement(module, source_commands, upstream_commands, size_px,
                   native_axes, arm):
    """Invoke fit(); harness errors fail, geometric abstentions replay."""
    if arm not in _ALLOWED_ARMS:
        fail("unknown placement arm %r" % (arm,))
    fit = getattr(module, "fit", None)
    if not callable(fit):
        fail("%s has no fit() entry point" % PLACEMENT_MODULE)
    try:
        result = fit(source_commands, upstream_commands, size_px,
                     tuple(native_axes), arm=arm)
    except Exception as exc:
        fail("fit() raised %s: %s" % (type(exc).__name__, exc))
    if not isinstance(result, dict):
        fail("fit() returned %s" % type(result).__name__)
    for key in ("applied", "reason", "diagnostics"):
        if key not in result:
            fail("fit() misses '%s'" % key)
    if not isinstance(result.get("diagnostics"), dict):
        fail("fit() diagnostics is not a dict")
    if "candidate_commands" in result:
        result = dict(result, commands=result["candidate_commands"])
    elif "commands" not in result:
        fail("fit() misses 'commands'")
    if not isinstance(result["commands"], list):
        fail("fit() commands is not a list")
    return result


def place_glyph(source_commands, preferred_commands, size_px, native_axes,
                module, arm):
    """Placement arm for one glyph; only fit() abstentions replay preferred."""
    pins = validate_native_axes(native_axes)
    base = {"source_axis": None, "shift_px": [0.0, 0.0],
            "peak_shift_px": 0.0, "pinned_axes": list(pins),
            "abstention": None}
    result = call_placement(module, source_commands, preferred_commands,
                            size_px, pins, arm)
    commands = result["commands"]
    diagnostics = dict(base)
    diagnostics.update(result["diagnostics"])
    diagnostics["pinned_axes"] = list(pins)
    diagnostics["placement_arm"] = arm
    if not result.get("applied"):
        if not commands_equal(commands, preferred_commands):
            fail("abstention must return the exact upstream commands")
        diagnostics["abstention"] = result.get("reason") or "abstained"
        return {"candidate_commands": [dict(c) for c in preferred_commands],
                "applied": False, "reason": result.get("reason") or "abstained",
                "diagnostics": diagnostics}
    verify_applied(preferred_commands, commands, pins)
    peak, per_axis = max_shift(preferred_commands, commands)
    diagnostics["peak_shift_px"] = peak
    diagnostics["shift_px"] = per_axis
    return {"candidate_commands": commands, "applied": True,
            "reason": result.get("reason"), "diagnostics": diagnostics}


def load_curve_module(name=CURVE_MODULE):
    """Import the curve kernel; report absence instead of skipping."""
    import importlib

    try:
        return importlib.import_module(name), None
    except ImportError as exc:
        return None, "%s unavailable: %s" % (name, exc)


def check_curve_topology(result):
    """Topology gate must come from the actual kernel verdict."""
    topology = result.get("topology")
    if not isinstance(topology, dict):
        fail("curve result has no kernel topology verdict")
    if not topology.get("supported") or not topology.get("ok"):
        fail("curve topology unsupported or failed: %r" % (topology,))
    return topology


def call_curve(curve_module, source_commands, placement_commands, size_px,
               reference, native_axes):
    """Invoke curve fit_glyph(); errors fail, abstentions replay exactly."""
    fit_glyph = getattr(curve_module, "fit_glyph", None)
    if not callable(fit_glyph):
        fail("%s has no fit_glyph() entry point" % CURVE_MODULE)
    if not isinstance(reference, dict):
        fail("curve reference is not the frozen mode-cell reference")
    try:
        result = fit_glyph(source_commands, placement_commands, size_px,
                           reference, tuple(native_axes))
    except Exception as exc:
        fail("curve fit_glyph() raised %s: %s" % (type(exc).__name__, exc))
    if not isinstance(result, dict):
        fail("curve fit_glyph() returned %s" % type(result).__name__)
    for key in ("candidate_commands", "applied", "reason"):
        if key not in result:
            fail("curve fit_glyph() misses '%s'" % key)
    if not isinstance(result["candidate_commands"], list):
        fail("curve candidate_commands is not a list")
    return result


def curve_glyph(curve_module, source_commands, placement_commands, size_px,
                reference, native_axes):
    """Curve arm for one glyph over the placement commands."""
    pins = validate_native_axes(native_axes)
    result = call_curve(curve_module, source_commands, placement_commands,
                        size_px, reference, pins)
    commands = result["candidate_commands"]
    if not result.get("applied"):
        if not commands_equal(commands, placement_commands):
            fail("curve abstention must return the exact placement commands")
        return {"candidate_commands": [dict(c) for c in placement_commands],
                "applied": False, "reason": result.get("reason"),
                "diagnostics": result.get("diagnostics") or {},
                "recognition": result.get("recognition"),
                "widths": result.get("widths"),
                "topology": result.get("topology")}
    if not same_skeleton(placement_commands, commands):
        fail("curve result changed the command skeleton")
    if not all(valid_command(c) for c in commands):
        fail("curve result has invalid commands or f32 bits")
    if not respects_pins(placement_commands, commands, pins):
        fail("curve result moved native-owned coordinate bits")
    topology = check_curve_topology(result)
    if not isinstance(result.get("widths"), list):
        fail("applied curve result has no widths list")
    return {"candidate_commands": commands, "applied": True,
            "reason": result.get("reason"),
            "diagnostics": result.get("diagnostics") or {},
            "recognition": result.get("recognition"),
            "widths": result.get("widths"), "topology": topology}


def baseline_cell_path(baseline_out, family, size, weight, hint):
    stem = "%s_%s_%s_%s" % (family, str(size), str(int(weight)), hint)
    name = "".join(c if c.isalnum() or c in "-_." else "_" for c in stem) \
        + ".json"
    return os.path.join(baseline_out, "cells", name)


def check_baseline_cell(cell, family, size, weight, hint):
    problems = []
    if cell.get("family") != family:
        problems.append("family")
    if float(cell.get("size", -1)) != float(size):
        problems.append("size")
    if float(cell.get("weight", -1)) != float(weight):
        problems.append("weight")
    if cell.get("hint_mode") != hint:
        problems.append("hint_mode")
    harness = cell.get("harness", {})
    if harness.get("tool") != BASELINE_TOOL:
        problems.append("baseline-tool")
    if not isinstance(cell.get("glyphs"), list):
        problems.append("glyphs")
    if not isinstance(cell.get("layout"), dict):
        problems.append("layout")
    return problems


def select_cells(baseline_out, family=None, size=None, weight=None):
    with open(os.path.join(baseline_out, "summary.json")) as handle:
        summary = json.load(handle)
    if summary.get("tool") != BASELINE_TOOL:
        fail("baseline tool %s != %s"
             % (summary.get("tool"), BASELINE_TOOL))
    cells = []
    for entry in summary.get("cells", []):
        for item in entry.get("files", []):
            if family is not None and item.get("family") != family:
                continue
            if size is not None and float(item.get("size")) != float(size):
                continue
            if weight is not None and \
                    float(item.get("weight")) != float(weight):
                continue
            cells.append(item)
    return summary, cells


def source_lookup(ascii_dir, family, weight, size, hint):
    path = os.path.join(ascii_dir, "%s-%d-%d.json"
                        % (family, int(weight), int(size)))
    if not os.path.isfile(path):
        return {}, {}, None
    with open(path) as handle:
        cases = json.load(handle)
    if isinstance(cases, dict):
        cases = [cases]
    by_code = {}
    records = {}
    for case in cases:
        for mode_name, mode in (case.get("modes") or {}).items():
            for record in mode.get("records", []):
                code = record.get("codepoint")
                if code not in by_code and "source_commands" in record:
                    by_code[code] = record.get("source_commands") or []
                if mode_name == hint and code not in records:
                    records[code] = record
        for record in (case.get("source") or {}).get("records", []):
            code = record.get("codepoint")
            if code not in by_code and "source_commands" in record:
                by_code[code] = record.get("source_commands") or []
    return by_code, records, sha_file(path)


def three_arm_frame(arms):
    left = min(a["left"] for a in arms)
    top = min(a["top"] for a in arms)
    right = max(a["left"] + a["width"] for a in arms)
    bottom = max(a["top"] + a["height"] for a in arms)
    return {"left": left, "top": top, "width": right - left,
            "height": bottom - top}


def replay_tile(binary, record, commands, scratch, label, code):
    """Render commands through the captured policy; failures fail."""
    from experiments.hobby_fitting import direct_diagonal_run as run

    try:
        return run.arm_pixels(binary, record, commands, scratch)
    except SystemExit as exc:
        fail("%s raster failed for U+%04X: %s" % (label, code, exc))


def check_replay(art, stored_pixels, stored_frame, label, code):
    if list(art["pixels"]) != list(stored_pixels):
        fail("%s pixels != stored raster for U+%04X" % (label, code))
    for key in ("left", "top", "width", "height"):
        if art.get(key) != (stored_frame or {}).get(key):
            fail("%s frame %s != stored raster for U+%04X"
                 % (label, key, code))


def compose_three(line, up_tiles, pref_tiles, place_tiles):
    """Three arms in one shared union frame under the finalized layout."""
    from experiments.hobby_fitting import text_review as review

    up_extents, up_ink = review.extent_parts(line, up_tiles)
    pref_extents, pref_ink = review.extent_parts(line, pref_tiles)
    place_extents, place_ink = review.extent_parts(line, place_tiles)
    frame = review.union_frame(up_extents + pref_extents + place_extents)
    baseline_y = line["baseline"] + frame["origin_y"] \
        if frame["width"] or frame["height"] else 0
    shared = dict(frame, baseline_y=baseline_y)
    return {"frame": shared,
            "arms": {"upstream": dict(shared,
                                      pixels=review.render_frame(up_ink,
                                                                 frame)),
                     "preferred": dict(shared,
                                       pixels=review.render_frame(pref_ink,
                                                                  frame)),
                     "placement": dict(shared,
                                       pixels=review.render_frame(place_ink,
                                                                  frame))}}


def compose_four(line, up_tiles, pref_tiles, place_tiles, curve_tiles):
    """Four arms in one shared union frame under the finalized layout."""
    from experiments.hobby_fitting import text_review as review

    up_extents, up_ink = review.extent_parts(line, up_tiles)
    pref_extents, pref_ink = review.extent_parts(line, pref_tiles)
    place_extents, place_ink = review.extent_parts(line, place_tiles)
    curve_extents, curve_ink = review.extent_parts(line, curve_tiles)
    frame = review.union_frame(up_extents + pref_extents + place_extents
                               + curve_extents)
    baseline_y = line["baseline"] + frame["origin_y"] \
        if frame["width"] or frame["height"] else 0
    shared = dict(frame, baseline_y=baseline_y)
    return {"frame": shared,
            "arms": {"upstream": dict(shared,
                                      pixels=review.render_frame(up_ink,
                                                                 frame)),
                     "preferred": dict(shared,
                                       pixels=review.render_frame(pref_ink,
                                                                  frame)),
                     "placement": dict(shared,
                                       pixels=review.render_frame(place_ink,
                                                                  frame)),
                     "curves": dict(shared,
                                    pixels=review.render_frame(curve_ink,
                                                               frame))}}


def compose_paragraph_four(lines, up_tiles, pref_tiles, place_tiles,
                           curve_tiles):
    """All lines in one shared canvas at the native baselines."""
    from experiments.hobby_fitting import text_review as review

    extents, inks = [], []
    for tiles in (up_tiles, pref_tiles, place_tiles, curve_tiles):
        arm_extents, arm_ink = [], []
        for line in lines:
            line_extents, line_ink = review.extent_parts(line, tiles)
            arm_extents.extend(line_extents)
            arm_ink.extend(line_ink)
        extents.append(arm_extents)
        inks.append(arm_ink)
    frame = review.union_frame([e for arm in extents for e in arm])
    arms = {}
    for name, ink in zip(("upstream", "preferred", "placement", "curves"),
                         inks):
        arms[name] = dict(frame, pixels=review.render_frame(ink, frame))
    return {"frame": frame,
            "texts": [line.get("text", "") for line in lines],
            "line_baselines": [line["baseline"] + frame["origin_y"]
                               for line in lines],
            **arms}


def compose_paragraph_three(lines, up_tiles, pref_tiles, place_tiles):
    """All lines in one shared canvas at the native baselines."""
    from experiments.hobby_fitting import text_review as review

    up_extents, pref_extents, place_extents = [], [], []
    up_ink, pref_ink, place_ink = [], [], []
    for line in lines:
        extents, ink = review.extent_parts(line, up_tiles)
        up_extents.extend(extents)
        up_ink.extend(ink)
        extents, ink = review.extent_parts(line, pref_tiles)
        pref_extents.extend(extents)
        pref_ink.extend(ink)
        extents, ink = review.extent_parts(line, place_tiles)
        place_extents.extend(extents)
        place_ink.extend(ink)
    frame = review.union_frame(up_extents + pref_extents + place_extents)
    return {"frame": frame,
            "texts": [line.get("text", "") for line in lines],
            "line_baselines": [line["baseline"] + frame["origin_y"]
                               for line in lines],
            "upstream": dict(frame, pixels=review.render_frame(up_ink,
                                                               frame)),
            "preferred": dict(frame, pixels=review.render_frame(pref_ink,
                                                                frame)),
            "placement": dict(frame, pixels=review.render_frame(place_ink,
                                                                frame))}


def validate_matrix(cell, records, family, size, weight, hint):
    """Cell identities and capture repertoire must agree exactly."""
    codes = [g.get("codepoint") for g in cell.get("glyphs", [])]
    if set(codes) != set(records):
        fail("cell repertoire != capture repertoire for %s %s %s %s"
             % (family, size, weight, hint))
    if len(codes) != len(set(codes)):
        fail("duplicate codepoints in cell %s %s %s %s"
             % (family, size, weight, hint))


def spot_entry(char, placement_applied, placement_reason, shift_px,
               placement_pixels, preferred_pixels, curve_applied=None,
               curve_reason=None, curve_pixels=None):
    """Geometric-only bitmap identity label; never an optical category."""
    entry = {"char": char, "placement_applied": placement_applied,
             "placement_reason": placement_reason, "shift_px": shift_px,
             "identical_bitmap": list(placement_pixels)
             == list(preferred_pixels)}
    if curve_pixels is not None:
        entry["curves_applied"] = curve_applied
        entry["curves_reason"] = curve_reason
        entry["curves_identical_bitmap"] = list(curve_pixels) \
            == list(preferred_pixels)
    return entry


def process_cell(baseline_out, ascii_dir, out, item, module, prov,
                 binary, scratch, arm, curves=False, curve_module=None):
    from experiments.hobby_fitting import direct_diagonal_run as run

    family, size, weight = item["family"], item["size"], item["weight"]
    hint = item["hint_mode"]
    with open(baseline_cell_path(baseline_out, family, size, weight,
                                 hint)) as handle:
        cell = json.load(handle)
    problems = check_baseline_cell(cell, family, size, weight, hint)
    if problems:
        fail("baseline cell invalid %s %s %s %s: %s"
             % (family, size, weight, hint, ",".join(problems)))
    sources, records, ascii_sha = source_lookup(ascii_dir, family, weight,
                                                size, hint)
    if ascii_sha is None:
        fail("ascii capture missing for %s %s %s" % (family, weight, size))
    validate_matrix(cell, records, family, size, weight, hint)
    if curves and curve_module is None:
        fail("curve arm requested without a loaded kernel")
    if curves and not isinstance(cell.get("reference"), dict):
        fail("curve arm needs the frozen mode-cell reference")
    reference = cell.get("reference")
    glyphs = []
    applied = abstained = 0
    reasons = {}
    curve_applied = curve_abstained = 0
    curve_reasons = {}
    up_tiles, pref_tiles, place_tiles, curve_tiles = {}, {}, {}, {}
    for glyph in cell.get("glyphs", []):
        code = glyph.get("codepoint")
        record = records.get(code)
        native_axes = validate_native_axes(glyph.get("native_axes"))
        upstream_commands = glyph.get("upstream_commands", [])
        preferred = (glyph.get("candidate") or {}).get("candidate_commands",
                                                       [])
        try:
            run.check_parity(binary, record, scratch)
        except SystemExit as exc:
            fail("parity failed for U+%04X: %s" % (code, exc))
        up_art = replay_tile(binary, record, upstream_commands, scratch,
                             "upstream replay", code)
        check_replay(up_art, glyph["upstream"]["pixels"],
                     {k: glyph["upstream"][k]
                      for k in ("left", "top", "width", "height")},
                     "upstream replay", code)
        pref_art = replay_tile(binary, record, preferred, scratch,
                               "preferred replay", code)
        check_replay(pref_art, glyph["candidate"]["pixels"],
                     glyph["candidate"]["frame"], "preferred replay", code)
        source = sources.get(code)
        if source is None:
            fail("no source commands for U+%04X" % code)
        placement = place_glyph(source, preferred, float(size),
                                list(native_axes), module, arm)
        if placement["applied"]:
            art = replay_tile(binary, record,
                              placement["candidate_commands"], scratch,
                              "placement", code)
            placement_frame = {k: art[k]
                               for k in ("left", "top", "width", "height")}
            placement_pixels = art["pixels"]
            applied += 1
        else:
            if not commands_equal(placement["candidate_commands"],
                                  preferred):
                fail("abstention must replay preferred for U+%04X" % code)
            placement_frame = dict(glyph["candidate"]["frame"])
            placement_pixels = glyph["candidate"]["pixels"]
            abstained += 1
        reasons[placement["reason"] or "applied"] = \
            reasons.get(placement["reason"] or "applied", 0) + 1
        upstream_tile = {"left": up_art["left"], "top": up_art["top"],
                         "width": up_art["width"], "height": up_art["height"],
                         "pixels": up_art["pixels"]}
        preferred_frame = {k: pref_art[k]
                           for k in ("left", "top", "width", "height")}
        frame = three_arm_frame([
            {"left": upstream_tile["left"], "top": upstream_tile["top"],
             "width": upstream_tile["width"],
             "height": upstream_tile["height"]},
            {"left": preferred_frame.get("left", 0),
             "top": preferred_frame.get("top", 0),
             "width": preferred_frame.get("width", 0),
             "height": preferred_frame.get("height", 0)},
            {"left": placement_frame.get("left", 0),
             "top": placement_frame.get("top", 0),
             "width": placement_frame.get("width", 0),
             "height": placement_frame.get("height", 0)}])
        up_tiles[code] = upstream_tile
        pref_tiles[code] = dict(preferred_frame,
                                pixels=list(pref_art["pixels"]))
        place_tiles[code] = dict(placement_frame,
                                 pixels=list(placement_pixels))
        entry = {
            "char": glyph.get("char"), "codepoint": code,
            "native_axes": list(native_axes),
            "ownership": glyph.get("ownership"),
            "source_commands": source,
            "upstream_commands": upstream_commands,
            "upstream": upstream_tile,
            "preferred_commands": preferred,
            "preferred": {"frame": preferred_frame,
                          "pixels": list(pref_art["pixels"])},
            "preferred_applied": (glyph.get("candidate") or {}).get(
                "applied", False),
            "preferred_reason": (glyph.get("candidate") or {}).get("reason"),
            "placement_commands": placement["candidate_commands"],
            "placement": {"frame": dict(placement_frame),
                          "pixels": list(placement_pixels)},
            "placement_applied": placement["applied"],
            "placement_reason": placement["reason"],
            "diagnostics": placement["diagnostics"],
            "frame": frame}
        if curves:
            curve = curve_glyph(curve_module, source,
                                placement["candidate_commands"], float(size),
                                reference, list(native_axes))
            if curve["applied"]:
                curve_art = replay_tile(binary, record,
                                        curve["candidate_commands"], scratch,
                                        "curves", code)
                curve_frame = {k: curve_art[k]
                               for k in ("left", "top", "width", "height")}
                curve_pixels = curve_art["pixels"]
                curve_applied += 1
            else:
                if not commands_equal(curve["candidate_commands"],
                                      placement["candidate_commands"]):
                    fail("curve abstention must replay placement for U+%04X"
                         % code)
                curve_frame = dict(placement_frame)
                curve_pixels = list(placement_pixels)
                curve_abstained += 1
            curve_reasons[curve["reason"] or "applied"] = \
                curve_reasons.get(curve["reason"] or "applied", 0) + 1
            curve_tiles[code] = dict(curve_frame,
                                     pixels=list(curve_pixels))
            entry["curve_commands"] = curve["candidate_commands"]
            entry["curves"] = {"frame": dict(curve_frame),
                               "pixels": list(curve_pixels)}
            entry["curve_applied"] = curve["applied"]
            entry["curve_reason"] = curve["reason"]
            entry["curve_diagnostics"] = curve["diagnostics"]
            entry["curve_recognition"] = curve["recognition"]
            entry["curve_widths"] = curve["widths"]
            entry["curve_topology"] = curve["topology"]
            entry["curve_identical_bitmap"] = list(curve_pixels) == list(
                pref_art["pixels"])
            frame = three_arm_frame([
                {"left": frame["left"], "top": frame["top"],
                 "width": frame["width"], "height": frame["height"]},
                {"left": curve_frame.get("left", 0),
                 "top": curve_frame.get("top", 0),
                 "width": curve_frame.get("width", 0),
                 "height": curve_frame.get("height", 0)}])
            entry["frame"] = frame
        glyphs.append(entry)
    layout = cell.get("layout")
    if not isinstance(layout, dict) or not isinstance(
            layout.get("lines"), list):
        fail("baseline cell has no finalized native layout")
    if curves:
        lines = [dict(compose_four(line, up_tiles, pref_tiles, place_tiles,
                                   curve_tiles),
                      text=line.get("text"))
                 for line in layout.get("lines", [])]
        paragraph = compose_paragraph_four(layout.get("lines", []), up_tiles,
                                           pref_tiles, place_tiles,
                                           curve_tiles)
    else:
        lines = [dict(compose_three(line, up_tiles, pref_tiles, place_tiles),
                      text=line.get("text"))
                 for line in layout.get("lines", [])]
        paragraph = compose_paragraph_three(layout.get("lines", []), up_tiles,
                                            pref_tiles, place_tiles)
    by_code = {g["codepoint"]: g for g in glyphs}
    spot = {}
    for code in SPOT_CODES:
        entry = by_code.get(code)
        if entry is None:
            fail("spot glyph U+%04X missing from cell" % code)
        if curves:
            spot[entry["char"]] = spot_entry(
                entry["char"], entry["placement_applied"],
                entry["placement_reason"],
                entry["diagnostics"].get("shift_px", [0.0, 0.0]),
                entry["placement"]["pixels"], entry["preferred"]["pixels"],
                entry["curve_applied"], entry["curve_reason"],
                entry["curves"]["pixels"])
        else:
            spot[entry["char"]] = spot_entry(
                entry["char"], entry["placement_applied"],
                entry["placement_reason"],
                entry["diagnostics"].get("shift_px", [0.0, 0.0]),
                entry["placement"]["pixels"], entry["preferred"]["pixels"])
    out_cell = {
        "family": family, "size": size, "weight": weight,
        "axes": cell.get("axes"), "hint_mode": hint,
        "tool": TOOL_VERSION,
        "baseline": {"tool": BASELINE_TOOL,
                     "file": baseline_cell_path(
                         baseline_out, family, size, weight, hint),
                     "sha256": sha_file(baseline_cell_path(
                         baseline_out, family, size, weight, hint))},
        "ascii_capture_sha256": ascii_sha,
        "layout": cell.get("layout"),
        "layout_sha256": sha_json(cell.get("layout")),
        "repertoire": sorted(g.get("codepoint")
                             for g in cell.get("glyphs", [])),
        "layout_status": cell.get("layout_status"),
        "lines": lines, "paragraph": paragraph,
        "counts": {"applied": applied, "abstained": abstained,
                   "reasons": reasons,
                   **({"curve_applied": curve_applied,
                       "curve_abstained": curve_abstained,
                       "curve_reasons": curve_reasons} if curves else {})},
        "placement_arm": arm,
        "curves_enabled": curves,
        "spot": spot,
        "placement_availability": "available",
        "glyphs": glyphs,
        "provenance": prov,
    }
    out_cell["cell_sha256"] = sha_json(
        {k: v for k, v in out_cell.items() if k != "cell_sha256"})
    return out_cell


def saved_cell_valid(path, item, baseline_sha, ascii_sha, ascii_codes,
                     prov):
    """Resume only after identity, schema, repertoire, layout and content."""
    if not os.path.isfile(path):
        return False
    try:
        with open(path) as handle:
            cell = json.load(handle)
    except ValueError:
        return False
    if cell.get("tool") != TOOL_VERSION:
        return False
    for key, want in (("family", item["family"]),
                      ("size", item["size"]), ("weight", item["weight"]),
                      ("hint_mode", item["hint_mode"])):
        if cell.get(key) != want:
            return False
    if not isinstance(cell.get("glyphs"), list) \
            or not isinstance(cell.get("layout"), dict) \
            or not isinstance(cell.get("lines"), list) \
            or not isinstance(cell.get("paragraph"), dict):
        return False
    if (cell.get("baseline") or {}).get("sha256") != baseline_sha:
        return False
    if cell.get("ascii_capture_sha256") != ascii_sha:
        return False
    if cell.get("repertoire") != sorted(ascii_codes):
        return False
    if [g.get("codepoint") for g in cell.get("glyphs", [])] != \
            cell.get("repertoire"):
        return False
    if cell.get("layout_sha256") != sha_json(cell.get("layout")):
        return False
    if (cell.get("provenance") or {}) != prov:
        return False
    digest = cell.get("cell_sha256")
    if digest != sha_json({k: v for k, v in cell.items()
                           if k != "cell_sha256"}):
        return False
    return True


PLACEMENT_DEPS = ("experiments/hobby_fitting/symmetry_placement.py",
                  "experiments/hobby_fitting/real_outline.py")


def module_provenance():
    prov = {}
    for rel in PLACEMENT_DEPS:
        path = os.path.join(REPO, rel)
        if not os.path.isfile(path):
            fail("placement dependency missing: %s" % rel)
        prov[rel] = sha_file(path)
    return prov


def curve_provenance(topology_binary):
    prov = {}
    for rel in CURVE_DEPS:
        path = os.path.join(REPO, rel)
        if not os.path.isfile(path):
            fail("curve dependency missing: %s" % rel)
        prov[rel] = sha_file(path)
    if not os.path.isfile(topology_binary):
        fail("topology binary missing: %s" % topology_binary)
    prov["topology_binary"] = topology_binary
    prov["topology_binary_sha256"] = sha_file(topology_binary)
    return prov


def baseline_identity(baseline_out):
    """Reference, donor, capture-policy and raster-policy identity."""
    with open(os.path.join(baseline_out, "summary.json")) as handle:
        summary = json.load(handle)
    identity = {}
    for key in ("baseline_capture_sha256", "baseline_model_source_sha256",
                "baseline_topology_sha256", "adapter_sha256",
                "topology_binary_sha256", "frozen_donors",
                "ascii_repertoire", "text_lines", "layout_note"):
        if key in summary:
            identity[key] = summary[key]
    return summary, identity


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default=BASELINE_DIR)
    parser.add_argument("--ascii-dir", default=ASCII_DIR)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--family", default=None)
    parser.add_argument("--size", type=float, default=None)
    parser.add_argument("--weight", type=float, default=None)
    parser.add_argument("--focus", action="store_true",
                        help="run only default Roboto 400/16 both hint modes")
    parser.add_argument("--placement-arm",
                        choices=[ARM_CONTROL, ARM_PHASE], default=ARM_PHASE,
                        help="symmetry placement arm; strict-quantum keeps "
                             "the legacy control")
    parser.add_argument("--curves", action="store_true",
                        help="experimental fourth curve arm; default off, "
                             "never published from this harness")
    parser.add_argument("--topology-binary", default=None)
    parser.add_argument("--resume", action="store_true",
                        help="reuse saved cells only after complete "
                             "provenance validation")
    args = parser.parse_args(argv)

    focus = {"family": "Roboto", "weight": "400", "size": "16"}
    if args.focus:
        args.family, args.size, args.weight = "Roboto", 16.0, 400.0

    summary, baseline_id = baseline_identity(args.baseline)
    if summary.get("tool") != BASELINE_TOOL:
        fail("baseline tool %s != %s"
             % (summary.get("tool"), BASELINE_TOOL))
    _, items = select_cells(args.baseline, args.family, args.size,
                            args.weight)
    if not items:
        fail("no baseline cells match the filters")
    module, module_error = load_placement_module()
    if module_error is not None:
        fail(module_error)
    curve_module = None
    if args.curves:
        curve_module, curve_error = load_curve_module()
        if curve_error is not None:
            fail(curve_error)
        topology_binary = os.path.abspath(
            args.topology_binary or os.environ.get(
                "HOBBY_EXACT_TOPOLOGY_BINARY", DEFAULT_TOPOLOGY_BINARY))
        os.environ["HOBBY_EXACT_TOPOLOGY_BINARY"] = topology_binary
    binary = None
    if args.adapter:
        if not os.path.isfile(args.adapter):
            fail("missing --adapter %s" % args.adapter)
        binary = args.adapter
    else:
        default_adapter = os.path.join(
            REPO, "tools/generator/target/debug/strokestyles-fit-adapter")
        if not os.path.isfile(default_adapter):
            fail("default adapter missing: %s" % default_adapter)
        binary = default_adapter
    prov = {"tool": TOOL_VERSION, "baseline_tool": BASELINE_TOOL,
            "baseline_summary_sha256": sha_file(
                os.path.join(args.baseline, "summary.json")),
            "baseline_identity": baseline_id,
            "review_source_sha256": sha_file(os.path.join(
                REPO, "experiments/hobby_fitting/shape_balance_review.py")),
            "review_html_sha256": sha_file(TEMPLATE),
            "placement_module": PLACEMENT_MODULE,
            "placement_arm": args.placement_arm,
            "placement_dependencies": module_provenance(),
            "composition_dependencies": {
                rel: sha_file(os.path.join(REPO, rel)) for rel in (
                    "experiments/hobby_fitting/text_review.py",
                    "experiments/hobby_fitting/direct_diagonal_run.py")},
            "curves_enabled": args.curves,
            **({"curve_module": CURVE_MODULE,
                "curve_dependencies": curve_provenance(topology_binary)}
               if args.curves else {}),
            "adapter_resolved": binary,
            "adapter_sha256": sha_file(binary)}
    os.makedirs(os.path.join(args.out, "cells"), exist_ok=True)
    scratch = os.path.join(args.out, "scratch")
    os.makedirs(scratch, exist_ok=True)
    files = []
    out_spot = {}
    for item in sorted(items, key=lambda c: (c["family"], c["size"],
                                             c["weight"], c["hint_mode"])):
        stem = "%s_%s_%s_%s" % (item["family"], str(item["size"]),
                                str(int(item["weight"])), item["hint_mode"])
        name = "".join(c if c.isalnum() or c in "-_." else "_" for c in stem) \
            + ".json"
        baseline_sha = sha_file(baseline_cell_path(
            args.baseline, item["family"], item["size"], item["weight"],
            item["hint_mode"]))
        _, records, ascii_sha = source_lookup(
            args.ascii_dir, item["family"], item["weight"], item["size"],
            item["hint_mode"])
        if ascii_sha is None:
            fail("ascii capture missing for %s %s %s"
                 % (item["family"], item["weight"], item["size"]))
        path = os.path.join(args.out, "cells", name)
        if args.resume and saved_cell_valid(path, item, baseline_sha,
                                            ascii_sha,
                                            sorted(records), prov):
            with open(path) as handle:
                out_cell = json.load(handle)
        else:
            out_cell = process_cell(args.baseline, args.ascii_dir, args.out,
                                    item, module, prov, binary, scratch,
                                    args.placement_arm, args.curves,
                                    curve_module)
            with open(path, "w") as handle:
                json.dump(out_cell, handle)
        files.append({"file": "cells/" + name, "family": item["family"],
                      "size": item["size"], "weight": item["weight"],
                      "axes": out_cell.get("axes"),
                      "hint_mode": item["hint_mode"],
                      "counts": out_cell["counts"]})
        out_spot["cells/" + name] = out_cell.get("spot", {})
    summary_out = {
        "tool": TOOL_VERSION, "baseline": args.baseline,
        "baseline_tool": BASELINE_TOOL,
        "note": ("Experimental review: upstream, preferred width-only, "
                "experimental placement" + (", experimental curves"
                                            if args.curves else "") +
                " in equal frames. Assessment pending: "
                "no automatic semantic classification is derived from count "
                "metrics. Unchanged glyphs keep the upstream label honestly."),
        "assessment": "pending",
        "placement_availability": "available",
        "placement_arm": args.placement_arm,
        "curves_enabled": args.curves,
        "focus": focus,
        "provenance": prov,
        "cells": files,
        "spot": {entry["file"]: out_spot[entry["file"]]
                 for entry in files},
    }
    with open(os.path.join(args.out, "summary.json"), "w") as handle:
        json.dump(summary_out, handle, indent=1)
    with open(TEMPLATE) as handle:
        template = handle.read()
    with open(os.path.join(args.out, "index.html"), "w") as handle:
        handle.write(template)
    print("wrote %d cells to %s (placement live)" % (len(files), args.out))


if __name__ == "__main__":
    main()
