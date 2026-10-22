#!/usr/bin/env python3
"""Static browser optical review of frozen width-only fits on ordinary text.

Frozen donors stay fixed: the fifteen original diagonal glyphs supply the
only reference anchors, and new ASCII captures must reproduce the frozen
captures' geometry, metrics and scan policy for those donors. Delivered
donor fits must reproduce the frozen joins-evaluation width-only arm.
Grid fitting and curved-outline support are separate questions and stay
out of this review.

Paired upstream/width-only text shares one finalized native layout; this
tool never invents advances or renders CSS font text. The exact native
`text-layout` verb is required: layout failures or schema mismatches
fail the run rather than emitting a glyph-only page.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from experiments.hobby_fitting import direct_diagonal_run as run

TOOL_VERSION = "text-review-v1"
FROZEN_CAPTURE_SHA256 = "b902a1ac88a003d763e64e87bb457f2f06e5beba2944041c27618e84e83af9cd"
FROZEN_TOPOLOGY_SHA256 = "dc96413be17493b0a8021895e25b5100f5c26ea66c7dc4df7fa2c57565d10c31"
JOINS_CAPTURE_SHA256 = FROZEN_CAPTURE_SHA256

DONOR_CHARS = "itflInhkyxzvAVW"
DONOR_CODES = {ord(c) for c in DONOR_CHARS}
ASCII_95 = "".join(chr(c) for c in range(0x20, 0x7F))
MODEL_FILE = "experiments/hobby_fitting/direct_diagonal.py"

# Declared before rendering; explicit line breaks, no automatic wrapping.
TEXT_LINES = [
    "We walked by the river before the sky turned grey.",
    "Every morning, Max checks the news and makes tea.",
    "The quick brown fox jumps over the lazy dog.",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "abcdefghijklmnopqrstuvwxyz",
    "0123456789",
    "k v x z y K V X Z Y A W f h i l n t",
]

FONT_PATHS = {
    "Roboto": "fonts/Roboto.ttf",
    "SourceSans3": "fonts/SourceSans3.ttf",
}
SIZES = (12.0, 14.0, 16.0, 18.0, 20.0, 24.0)
WEIGHTS = (300.0, 400.0, 700.0)
HINT_MODES = ("auto_default", "selective_default")

SCAN_KEYS = (
    "raster_policy", "mono_raster", "mono_rasterizer", "mono_threshold",
    "font_scan", "selected_engine", "selective_fitting",
)


def fail(message):
    raise SystemExit("text-review: " + message)


def sha_file(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def load_cases(path):
    with open(path) as handle:
        cases = json.load(handle)
    if isinstance(cases, dict):
        cases = [cases]
    return cases


def assert_frozen_captures(path):
    digest = sha_file(path)
    if digest != FROZEN_CAPTURE_SHA256:
        fail("frozen captures mismatch: %s != %s" % (digest, FROZEN_CAPTURE_SHA256))
    return digest


def donor_records_for(records):
    return [r for r in records if r.get("codepoint") in DONOR_CODES]


def group_key(item):
    return (item["font_sha"], json.dumps(item["axes"], sort_keys=True),
            str(item["size"]), item["hint_mode"])


def model_source_sha256():
    """Hash of the frozen width-only model source."""
    with open(os.path.join(REPO, MODEL_FILE), "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def reference_sha256(reference):
    return hashlib.sha256(
        json.dumps(reference, sort_keys=True).encode()).hexdigest()


def frozen_axes_for(frozen_cases, family, weight):
    """Original frozen case axes; Roboto carries wdth, SourceSans3 does not."""
    found = None
    for case in frozen_cases:
        if case.get("family") != family:
            continue
        axes = dict(case.get("axes", {}))
        if float(axes.get("wght", 0)) != float(weight):
            continue
        if found is None:
            found = axes
        elif found != axes:
            fail("frozen axes vary for %s %s" % (family, weight))
    if found is None:
        fail("no frozen case for %s %s" % (family, weight))
    return found


def joins_lookup(joins_summary):
    """Frozen joins files keyed by full identity, never by basename.

    Weight-specific files carry dedup suffixes (-2, -3), so basenames
    cannot distinguish weights; the summary's own keys are authoritative.
    """
    table = {}
    for entry in joins_summary.get("cases", []):
        key = (entry.get("family"), float(entry.get("size")),
               json.dumps(entry.get("axes", {}), sort_keys=True),
               entry.get("hint_mode"), entry.get("codepoint"))
        table[key] = entry.get("file")
    return table


def layout_text():
    """Exact bytes handed to the native layout worker; no trailing break."""
    return "\n".join(TEXT_LINES)


def build_donor_references(core, items):
    """One reference per group from donor records only."""
    groups = {}
    for item in items:
        groups.setdefault(group_key(item), []).append(item)
    references = {}
    for key, members in groups.items():
        records = [m["record"] for m in members
                   if m["codepoint"] in DONOR_CODES]
        if len(records) != len(DONOR_CHARS):
            fail("group %s has %d donor records, want %d"
                 % (key[1:], len(records), len(DONOR_CHARS)))
        t0 = time.perf_counter()
        references[key] = {
            "reference": core.build_reference(records, members[0]["size"]),
            "runtime_ms": (time.perf_counter() - t0) * 1000.0,
        }
    return references


def check_donor_recapture(frozen_by_key, new_items):
    """New captures must reproduce frozen donor geometry/metrics/policy."""
    mismatches = []
    for item in new_items:
        if item["codepoint"] not in DONOR_CODES:
            continue
        frozen = frozen_by_key.get((group_key(item), item["codepoint"]))
        if frozen is None:
            mismatches.append((item["codepoint"], "missing-frozen-donor"))
            continue
        record = item["record"]
        for field in ("source_commands", "fitted_commands",
                      "advance_26_6", "hinted_advance_width", "hinted_lsb",
                      "hinted_has_overlaps", "side_bearing_deltas_26_6",
                      "left", "top", "width", "height",
                      "pixels", "coverage") + SCAN_KEYS:
            if record.get(field) != frozen.get(field):
                mismatches.append((item["codepoint"], field))
    if mismatches:
        fail("donor recapture mismatch: %s" % mismatches[:12])


def check_donor_delivery(lookup, joins_dir, cell, results):
    """Delivered donor fits must reproduce frozen joins-evaluation.

    The cell carries full family/size/axes/hint identity; lookup resolves
    the frozen file without trusting deduped basenames.
    """
    for code, result in results.items():
        if code not in DONOR_CODES:
            continue
        key = (cell["family"], float(cell["size"]),
               json.dumps(cell["axes"], sort_keys=True),
               cell["hint_mode"], code)
        rel = lookup.get(key)
        if rel is None:
            fail("frozen joins case missing for %s U+%04X"
                 % (key[:4], code))
        path = os.path.join(joins_dir, rel)
        with open(path) as handle:
            frozen = json.load(handle)["arms"]["width_only"]
        if frozen is None:
            fail("frozen joins arm missing: %s" % path)
        if bool(frozen.get("applied")) != bool(result.get("applied")):
            fail("donor U+%04X applied mismatch vs joins-evaluation" % code)
        if (frozen.get("reason") or "") != (result.get("reason") or ""):
            fail("donor U+%04X reason mismatch vs joins-evaluation" % code)
        if frozen.get("candidate_commands") != result.get("candidate_commands"):
            fail("donor U+%04X commands mismatch vs joins-evaluation" % code)
        if frozen.get("pixels") != result.get("pixels"):
            fail("donor U+%04X pixels mismatch vs joins-evaluation" % code)


def capture_ascii(binary, family, size, axes, out_path, font_path):
    proc = subprocess.run(
        [binary, "capture", "--font", font_path,
         "--chars", ASCII_95, "--size", str(size),
         "--axes", json.dumps(axes), "--out", out_path],
        capture_output=True, text=True)
    if proc.returncode != 0:
        fail("ascii capture failed %s %s %s: %s"
             % (family, size, axes, proc.stderr.strip()[-300:]))


def check_layout_mode(mode, hint, records_by_code, extensions):
    """Fail closed unless the native mode honors its own spacing tables.

    Pen positions must accumulate the finalized advances plus one pair
    value each; the reviewer never respaces them independently.
    """
    for key in ("metrics", "advances", "pair_adjustments", "glyphs",
                "lines", "strategy", "extensions"):
        if key not in mode:
            fail("layout mode %s misses %s" % (hint, key))
    if mode.get("extensions") != extensions:
        fail("layout extensions %s != capture %s for %s"
             % (mode.get("extensions"), extensions, hint))
    metrics = mode["metrics"]
    if metrics.get("line_height_px", 0) < 1:
        fail("layout mode %s has no line pitch" % hint)
    advances = {e["codepoint"]: e["advance"] for e in mode["advances"]}
    pairs = {(e["left"], e["right"]): e["adjustment"]
             for e in mode["pair_adjustments"]}
    glyphs = {g["codepoint"]: g for g in mode["glyphs"]}
    if set(glyphs) != set(records_by_code):
        fail("layout glyphs do not cover capture repertoire for %s" % hint)
    for code, record in records_by_code.items():
        glyph = glyphs[code]
        for key in ("left", "top", "width", "height", "glyph_id"):
            if glyph.get(key) != record.get(key):
                fail("layout glyph U+%04X %s != capture for %s"
                     % (code, key, hint))
        if glyph.get("advance") != advances.get(code):
            fail("layout glyph U+%04X advance != advances table" % code)
    lines = mode["lines"]
    if len(lines) != len(TEXT_LINES):
        fail("layout has %d lines, want %d" % (len(lines), len(TEXT_LINES)))
    pitch = metrics["line_height_px"]
    for index, (want, line) in enumerate(zip(TEXT_LINES, lines)):
        if line.get("text") != want:
            fail("layout line %d text mismatch" % index)
        if line.get("baseline") != metrics["ascent_px"] + index * pitch:
            fail("layout line %d breaks native line pitch" % index)
        placements = line.get("placements", [])
        if [p.get("codepoint") for p in placements] != \
                [ord(c) for c in want]:
            fail("layout line %d placements != text" % index)
        for place in placements:
            for key in ("codepoint", "x", "advance", "pair"):
                if key not in place:
                    fail("layout placement misses %s" % key)
            if place.get("x_26_6", 64 * place["x"]) % 64 != 0:
                fail("layout placement U+%04X off whole pixels"
                     % place["codepoint"])
            if place["advance"] != advances.get(place["codepoint"]):
                fail("layout placement advance != advances table")
        if placements:
            if placements[0].get("pair", 0) != 0:
                fail("line-initial pair must be zero")
            for first, second in zip(placements, placements[1:]):
                left = first["codepoint"]
                right = second["codepoint"]
                want_x = first["x"] + advances[left] + \
                    pairs.get((left, right), 0)
                if second["x"] != want_x:
                    fail("layout pen U+%04X does not accumulate "
                         "advance+pair" % right)
                if second["pair"] != pairs.get((left, right), 0):
                    fail("layout pair U+%04X+U+%04X != pair table"
                         % (left, right))


def native_layout(binary, family, size, axes, font_path, scratch,
                  extensions_by_hint, records_by_hint):
    """Finalized native layout for the declared lines; fail closed."""
    text_path = os.path.join(scratch, "lines.txt")
    out_path = os.path.join(scratch, "layout.json")
    with open(text_path, "w") as handle:
        handle.write(layout_text())
    proc = subprocess.run(
        [binary, "text-layout", "--font", font_path,
         "--chars", ASCII_95, "--size", str(size),
         "--axes", json.dumps(axes), "--text-file", text_path,
         "--out", out_path],
        capture_output=True, text=True)
    if proc.returncode != 0:
        fail("native text-layout failed: %s"
             % proc.stderr.strip()[-300:])
    with open(out_path) as handle:
        layout = json.load(handle)
    if os.path.splitext(os.path.basename(font_path))[0] != \
            layout.get("font"):
        fail("layout font %s != %s" % (layout.get("font"), family))
    if float(layout.get("size", 0)) != float(size):
        fail("layout size %s != %s" % (layout.get("size"), size))
    if dict(layout.get("axes", {})) != dict(axes):
        fail("layout axes %s != %s" % (layout.get("axes"), axes))
    modes = layout.get("modes", {})
    for hint in HINT_MODES:
        if hint not in modes:
            fail("layout misses hint mode %s" % hint)
        check_layout_mode(modes[hint], hint, records_by_hint[hint],
                          extensions_by_hint[hint])
    return layout


def union_frame(extents):
    """Smallest shared frame covering every extent (x0, y0, x1, y1)."""
    lo_x = lo_y = hi_x = hi_y = None
    for (x0, y0, x1, y1) in extents:
        if lo_x is None:
            lo_x, lo_y, hi_x, hi_y = x0, y0, x1, y1
        else:
            lo_x = min(lo_x, x0)
            lo_y = min(lo_y, y0)
            hi_x = max(hi_x, x1)
            hi_y = max(hi_y, y1)
    if lo_x is None:
        return {"width": 0, "height": 0, "origin_x": 0, "origin_y": 0}
    return {"width": hi_x - lo_x, "height": hi_y - lo_y,
            "origin_x": -lo_x, "origin_y": -lo_y}


def render_frame(ink, frame):
    """Stamp ink into a shared frame; no clipping, no resampling."""
    canvas = [0] * (frame["width"] * frame["height"])
    for (x0, y0, width, height, pixels) in ink:
        if not width or not height:
            continue
        ox, oy = x0 + frame["origin_x"], y0 + frame["origin_y"]
        for j in range(height):
            for i in range(width):
                if pixels[j * width + i]:
                    canvas[(oy + j) * frame["width"] + ox + i] = 1
    return canvas


def extent_parts(line, tiles):
    # The pen origin anchors every line: leading whitespace must survive
    # and an empty line still holds its native baseline in a paragraph.
    # Genuine negative overhang extends left of the origin as usual.
    extents = [(0, line["baseline"], 0, line["baseline"])]
    ink = []
    for place in line.get("placements", []):
        tile = tiles.get(place["codepoint"])
        if tile is None:
            fail("layout placement U+%04X has no captured tile"
                 % place["codepoint"])
        if tile["width"] and tile["height"]:
            x0 = place["x"] + tile["left"]
            y0 = line["baseline"] + tile["top"]
            extents.append((x0, y0, x0 + tile["width"], y0 + tile["height"]))
            ink.append((x0, y0, tile["width"], tile["height"],
                        tile["pixels"]))
        advance = place.get("advance")
        if advance:
            edge = place["x"] + advance
            extents.append((edge, line["baseline"],
                            edge, line["baseline"]))
    return extents, ink


def compose_line_common(line, up_tiles, wo_tiles):
    """Both arms rendered into one common union frame.

    The candidate box may change; the shared origin and baseline keep
    the pair comparable. Scale stays 1 here; the browser replicates
    integer zoom without resampling.
    """
    up_extents, up_ink = extent_parts(line, up_tiles)
    wo_extents, wo_ink = extent_parts(line, wo_tiles)
    frame = union_frame(up_extents + wo_extents)
    baseline_y = line["baseline"] + frame["origin_y"] \
        if frame["width"] or frame["height"] else 0
    shared = dict(frame, baseline_y=baseline_y)
    return {"frame": shared,
            "upstream": dict(shared, pixels=render_frame(up_ink, frame)),
            "width_only": dict(shared,
                               pixels=render_frame(wo_ink, frame))}


def compose_paragraph(lines, up_tiles, wo_tiles):
    """All declared lines in one shared canvas at native baselines.

    Line pitch and pen origins come from the layout alone; per-line
    cards remain available separately for closer inspection.
    """
    up_extents, wo_extents, up_ink, wo_ink = [], [], [], []
    for line in lines:
        extents, ink = extent_parts(line, up_tiles)
        up_extents.extend(extents)
        up_ink.extend(ink)
        extents, ink = extent_parts(line, wo_tiles)
        wo_extents.extend(extents)
        wo_ink.extend(ink)
    frame = union_frame(up_extents + wo_extents)
    return {"frame": frame,
            "texts": [line.get("text", "") for line in lines],
            "line_baselines": [line["baseline"] + frame["origin_y"]
                               for line in lines],
            "upstream": dict(frame, pixels=render_frame(up_ink, frame)),
            "width_only": dict(frame, pixels=render_frame(wo_ink, frame))}


def ascii_manifest(path, family, size, weight, axes, font_path):
    if not os.path.isfile(path + ".manifest.json"):
        return None
    with open(path + ".manifest.json") as handle:
        manifest = json.load(handle)
    want = {"family": family, "size": size, "weight": weight,
            "axes": axes,
            "chars_sha256": hashlib.sha256(ASCII_95.encode()).hexdigest(),
            "font_sha256": sha_file(font_path)}
    if any(manifest.get(k) != v for k, v in want.items()):
        return None
    if manifest.get("file_sha256") != sha_file(path):
        return None
    return manifest


def ensure_ascii_capture(binary, family, size, weight, axes, ascii_dir,
                         reuse):
    font_path = os.path.join(REPO, FONT_PATHS[family])
    if not os.path.isfile(font_path):
        fail("source font missing: %s" % font_path)
    out_path = os.path.join(ascii_dir, "%s-%d-%d.json"
                            % (family, int(weight), int(size)))
    manifest = ascii_manifest(out_path, family, size, weight, axes,
                              font_path) if reuse else None
    if manifest is None:
        capture_ascii(binary, family, size, axes, out_path, font_path)
        manifest = {"family": family, "size": size, "weight": weight,
                    "axes": axes, "chars": ASCII_95,
                    "chars_sha256": hashlib.sha256(ASCII_95.encode()).hexdigest(),
                    "font_sha256": sha_file(font_path),
                    "file_sha256": sha_file(out_path)}
        with open(out_path + ".manifest.json", "w") as handle:
            json.dump(manifest, handle)
    return out_path, manifest


def fit_cell(core, checker, binary, records, size, reference, scratch,
             cell_filter=None):
    results = {}
    for record in records:
        code = record.get("codepoint")
        if cell_filter is not None and not cell_filter(code):
            continue
        run.check_parity(binary, record, scratch)
        native_axes, owner = run.ownership(record)
        up_commands = record.get("fitted_commands", [])
        upstream = run.arm_pixels(binary, record, up_commands, scratch)
        if core is None:
            results[code] = {"upstream": upstream, "width_only": None,
                             "native_axes": list(native_axes),
                             "ownership": owner}
            continue
        result = core.fit_glyph(
            record.get("source_commands", []), up_commands, size,
            reference, native_axes, grid=False,
            **({"topology_checker": checker} if checker is not None else {}))
        candidate = run.arm_pixels(
            binary, record, result["candidate_commands"], scratch)
        result["pixels"] = candidate["pixels"]
        result["coverage"] = candidate["coverage"]
        result["frame"] = {k: candidate[k]
                           for k in ("left", "top", "width", "height")}
        result["checker"] = "exact_arrangement" if checker is not None \
            else "strict_signature"
        results[code] = {"upstream": upstream, "width_only": result,
                         "native_axes": list(native_axes),
                         "ownership": owner}
    return results


def cell_items(items, family, size, axes, hint):
    return [i for i in items
            if i["family"] == family and float(i["size"]) == float(size)
            and i["axes"] == axes and i["hint_mode"] == hint]


def saved_cell_problems(cell, family, size, weight, axes, hint):
    """Checkable identity/schema/provenance of a persisted hint cell.

    Returns problem strings; empty means the saved fits may be reused
    for recomposition. Fit correctness itself is re-validated against
    the frozen joins afterwards.
    """
    problems = []
    if cell.get("family") != family:
        problems.append("family")
    if float(cell.get("size", 0)) != float(size):
        problems.append("size")
    if float(cell.get("weight", 0)) != float(weight):
        problems.append("weight")
    if dict(cell.get("axes", {})) != dict(axes):
        problems.append("axes")
    if cell.get("hint_mode") != hint:
        problems.append("hint_mode")
    glyphs = cell.get("glyphs", [])
    if sorted(g.get("codepoint") for g in glyphs) != list(range(0x20, 0x7F)):
        problems.append("repertoire")
    layout = cell.get("layout")
    if not isinstance(layout, dict):
        problems.append("layout")
    elif [line.get("text") for line in layout.get("lines", [])] \
            != TEXT_LINES:
        problems.append("layout-text")
    elif cell.get("layout_status", {}).get("status") != "ready":
        problems.append("layout-status")
    reference = cell.get("reference")
    if not isinstance(reference, dict) or \
            cell.get("reference_sha256") != reference_sha256(reference):
        problems.append("reference-hash")
    if not isinstance(cell.get("counts"), dict):
        problems.append("counts")
    return problems


def tiles_for(results, arm):
    """Tile boxes per arm; width-only art nests its box under `frame`."""
    tiles = {}
    for code, entry in results.items():
        art = entry["upstream"] if arm == "upstream" else entry["width_only"]
        if art is None:
            continue
        frame = art.get("frame", art)
        tiles[code] = {"left": frame["left"], "top": frame["top"],
                       "width": frame["width"], "height": frame["height"],
                       "pixels": art["pixels"]}
    return tiles


def process_cell(binary, checker, core, family, size, weight, axes,
                 frozen_items, frozen_by_key,
                 joins_map, joins_dir, ascii_dir, scratch, out, prov):
    """Fit one family/size/weight cell and emit its review JSON."""
    font_path = os.path.join(REPO, FONT_PATHS[family])
    ascii_path, manifest = ensure_ascii_capture(
        binary, family, size, weight, axes, ascii_dir, reuse=True)
    case = load_cases(ascii_path)[0]
    items = list(run.iter_records([case]))
    check_donor_recapture(frozen_by_key, items)
    capture_ref = manifest["file_sha256"]
    extensions = {hint: case["modes"][hint].get("extensions")
                  for hint in HINT_MODES}
    capture_policy = {
        hint: {key: case["modes"][hint].get(key) for key in
               ("extensions", "implementation", "hinting_requested",
                "profile", "target")}
        for hint in HINT_MODES}
    members_by_hint = {}
    for hint in HINT_MODES:
        members = cell_items(items, family, size, axes, hint)
        if not members:
            fail("ascii capture has no %s records" % hint)
        members_by_hint[hint] = members
    records_by_hint = {
        hint: {m["codepoint"]: m["record"] for m in members}
        for hint, members in members_by_hint.items()}
    # Exact native layout; failure here fails the run, never a glyph-only
    # page pretending text is ready.
    layout = native_layout(binary, family, size, axes, font_path, scratch,
                           extensions, records_by_hint)
    cell_files = []
    for hint, members in members_by_hint.items():
        references = build_donor_references(core, members)
        key = next(iter(references))
        reference = references[key]["reference"]
        ref_hash = reference_sha256(reference)
        results = fit_cell(core, checker, binary,
                           [m["record"] for m in members],
                           members[0]["size"], reference, scratch)
        check_donor_delivery(
            joins_map, joins_dir,
            {"family": family, "size": members[0]["size"],
             "axes": axes, "hint_mode": hint},
            {code: entry["width_only"]
             for code, entry in results.items()})
        records_by_code = records_by_hint[hint]
        for code, entry in results.items():
            cand = entry["width_only"]
            if not cand.get("applied") and \
                    cand.get("pixels") != entry["upstream"]["pixels"]:
                fail("U+%04X abstained yet pixels differ" % code)
            for box_key in ("left", "top", "width", "height"):
                if entry["upstream"][box_key] != \
                        records_by_code[code][box_key]:
                    fail("U+%04X upstream box != capture" % code)
        up_tiles = tiles_for(results, "upstream")
        wo_tiles = tiles_for(results, "width_only")
        mode_lines = layout["modes"][hint]["lines"]
        lines = []
        for line in mode_lines:
            composed = compose_line_common(line, up_tiles, wo_tiles)
            lines.append({"text": line["text"], "frame": composed["frame"],
                          "arms": {"upstream": composed["upstream"],
                                   "width_only": composed["width_only"]}})
        paragraph = compose_paragraph(mode_lines, up_tiles, wo_tiles)
        glyph_rows, donor_glyphs = [], []
        counts = {"applied": 0, "abstained": 0, "reasons": {}}
        for m in sorted(members, key=lambda m: m["codepoint"]):
            code, entry = m["codepoint"], results[m["codepoint"]]
            cand = entry["width_only"]
            if cand.get("applied"):
                counts["applied"] += 1
            else:
                counts["abstained"] += 1
                reason = cand.get("reason", "unstated")
                counts["reasons"][reason] = \
                    counts["reasons"].get(reason, 0) + 1
            glyph_rows.append({
                "char": chr(code), "codepoint": code,
                "applied": bool(cand.get("applied")),
                "reason": None if cand.get("applied")
                else cand.get("reason"),
                "native_axes": entry["native_axes"],
                "ownership": entry["ownership"],
                "upstream_commands": m["record"]["fitted_commands"],
                "upstream": {
                    "pixels": entry["upstream"]["pixels"],
                    "coverage": entry["upstream"]["coverage"],
                    "left": entry["upstream"]["left"],
                    "top": entry["upstream"]["top"],
                    "width": entry["upstream"]["width"],
                    "height": entry["upstream"]["height"]},
                "width_only": cand,
                "widths": cand.get("widths")})
            if code in DONOR_CODES:
                donor_glyphs.append({
                    "char": chr(code), "codepoint": code,
                    "applied": bool(cand.get("applied")),
                    "upstream": up_tiles[code],
                    "width_only": wo_tiles.get(code)})
        layout_mode = layout["modes"][hint]
        stem = "%s_%s_%s_%s" % (family, str(size), str(int(weight)), hint)
        filename = "cells/%s.json" % "".join(
            c if c.isalnum() or c in "-_." else "_" for c in stem)
        cell = {"family": family, "size": size, "weight": weight,
                "axes": axes, "hint_mode": hint,
                "harness": prov,
                "layout_status": {
                    "status": "ready",
                    "strategy": layout_mode.get("strategy"),
                    "extensions": layout_mode.get("extensions")},
                "layout": layout_mode,
                "reference": reference,
                "reference_sha256": ref_hash,
                "lines": lines, "paragraph": paragraph,
                "counts": counts, "glyphs": glyph_rows,
                "donor_glyphs": donor_glyphs,
                "capture_policy": capture_policy[hint],
                "capture": capture_ref}
        with open(os.path.join(out, filename), "w") as handle:
            json.dump(cell, handle)
        cell_files.append({"file": filename, "family": family,
                           "size": size, "weight": weight, "axes": axes,
                           "hint_mode": hint, "counts": counts,
                           "reference_sha256": ref_hash,
                           "layout": "ready",
                           "capture": capture_ref})
    return {"family": family, "size": size, "weight": weight,
            "axes": axes, "files": cell_files}


def recompose_saved_cell(path, joins_map, joins_dir, prov):
    """Recompose one validated hint cell with the current compositor.

    Glyph fits, raster art and the native layout are reused untouched;
    only the shared-frame composition is redone, so a compositor fix
    never pays for refitting. Donor fits are re-validated against the
    frozen joins before the rewrite.
    """
    with open(path) as handle:
        cell = json.load(handle)
    problems = saved_cell_problems(
        cell, cell["family"], cell["size"], cell["weight"],
        cell["axes"], cell["hint_mode"])
    if problems:
        fail("saved cell %s invalid: %s" % (path, problems))
    check_donor_delivery(
        joins_map, joins_dir,
        {"family": cell["family"], "size": cell["size"],
         "axes": cell["axes"], "hint_mode": cell["hint_mode"]},
        {g["codepoint"]: g["width_only"]
         for g in cell["glyphs"] if g["codepoint"] in DONOR_CODES})
    results = {}
    for glyph in cell["glyphs"]:
        art = glyph["upstream"]
        frame = glyph["width_only"].get("frame", glyph["width_only"])
        results[glyph["codepoint"]] = {
            "upstream": art,
            "width_only": {"frame": {
                "left": frame["left"],
                "top": frame["top"],
                "width": frame["width"],
                "height": frame["height"]},
                "pixels": glyph["width_only"]["pixels"]},
        }
    up_tiles = tiles_for(results, "upstream")
    wo_tiles = tiles_for(results, "width_only")
    mode_lines = cell["layout"]["lines"]
    lines = []
    for line in mode_lines:
        composed = compose_line_common(line, up_tiles, wo_tiles)
        lines.append({"text": line["text"], "frame": composed["frame"],
                      "arms": {"upstream": composed["upstream"],
                               "width_only": composed["width_only"]}})
    cell["lines"] = lines
    cell["paragraph"] = compose_paragraph(mode_lines, up_tiles, wo_tiles)
    cell["donor_glyphs"] = [
        {"char": glyph["char"], "codepoint": glyph["codepoint"],
         "applied": glyph["applied"],
         "upstream": up_tiles[glyph["codepoint"]],
         "width_only": wo_tiles.get(glyph["codepoint"])}
        for glyph in cell["glyphs"]
        if glyph["codepoint"] in DONOR_CODES]
    cell["harness"] = dict(prov, resumed=True)
    with open(path, "w") as handle:
        json.dump(cell, handle)
    counts = cell["counts"]
    return {"file": os.path.join("cells", os.path.basename(path)),
            "family": cell["family"], "size": cell["size"],
            "weight": cell["weight"], "axes": cell["axes"],
            "hint_mode": cell["hint_mode"], "counts": counts,
            "reference_sha256": cell["reference_sha256"],
            "layout": "ready", "capture": cell["capture"]}


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Text-level width-only review (frozen model)</title>
<link rel="icon" href="data:,">
<style>
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:16px;color:#222;max-width:1200px}
canvas{image-rendering:pixelated;border:1px solid #999;background:#fff}
label{margin-right:12px}
.line{margin:12px 0;padding:8px;border:1px solid #ddd}
.line p{margin:4px 0;font-size:13px}
.row{display:flex;gap:24px;align-items:flex-start;flex-wrap:wrap}
.arm b{display:block;margin-bottom:4px}
table{border-collapse:collapse;font-size:13px;margin-top:8px}
td,th{border:1px solid #ccc;padding:2px 8px;text-align:left}
.note{font-size:13px;color:#555}
.pending{background:#fff8e1;border:1px solid #e0c36a;padding:8px;margin:12px 0}
</style>
</head>
<body>
<h1>Text-level width-only review (frozen model)</h1>
<div id="banner"></div>
<div id="filters"></div>
<div id="cell"></div>
<script>
let DATA = null;
function opt(id, values, current) {
  const sel = document.createElement("select");
  sel.id = id;
  values.forEach(v => { const o = document.createElement("option"); o.value = v; o.textContent = v; sel.appendChild(o); });
  if (values.includes(current)) sel.value = current;
  sel.onchange = render;
  return sel;
}
function radios(id, values, current) {
  const box = document.createElement("span");
  box.id = id;
  values.forEach(v => {
    const lab = document.createElement("label");
    const inp = document.createElement("input");
    inp.type = "radio"; inp.name = id; inp.value = v;
    if (v === current) inp.checked = true;
    inp.onchange = render;
    lab.appendChild(inp);
    lab.appendChild(document.createTextNode(" " + v));
    box.appendChild(lab);
  });
  return box;
}
function radioVal(id) {
  const els = document.querySelectorAll("input[name='" + id + "']");
  for (const e of els) if (e.checked) return e.value;
  return null;
}
function draw(canvas, art, scale) {
  canvas.width = Math.max(art.width, 1) * scale;
  canvas.height = Math.max(art.height, 1) * scale;
  canvas.style.width = canvas.width + "px";
  canvas.style.height = canvas.height + "px";
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (!art.width || !art.height) return;
  const img = ctx.createImageData(art.width, art.height);
  for (let i = 0; i < art.pixels.length; i++) {
    const v = art.pixels[i] ? 0 : 255;
    img.data[4*i] = v; img.data[4*i+1] = v; img.data[4*i+2] = v; img.data[4*i+3] = 255;
  }
  const off = document.createElement("canvas");
  off.width = art.width; off.height = art.height;
  off.getContext("2d").putImageData(img, 0, 0);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(off, 0, 0, canvas.width, canvas.height);
}
function load() {
  fetch("summary.json").then(r => r.json()).then(s => { DATA = s; build(); });
}
function selected(id) { return document.getElementById(id).value; }
function build() {
  const f = document.getElementById("filters");
  f.innerHTML = "";
  const cells = DATA.cells.flatMap(c => c.files);
  const fam = [...new Set(cells.map(c => c.family))];
  const wght = [...new Set(cells.map(c => String(c.weight)))];
  const size = [...new Set(cells.map(c => String(c.size)))];
  const hint = [...new Set(cells.map(c => c.hint_mode))];
  const famD = fam.includes("Roboto") ? "Roboto" : fam[0];
  const wghtD = wght.includes("400") ? "400" : wght[0];
  const sizeD = size.includes("16") ? "16" : size[0];
  const hintD = hint.includes("selective_default") ? "selective_default" : hint[0];
  f.append("family ", opt("fFam", fam, famD),
    " weight ", opt("fWght", wght, wghtD),
    " size ", opt("fSize", size, sizeD),
    " hint ", opt("fHint", hint, hintD),
    " zoom ", opt("fZoom", ["1", "2", "4", "8"], "1"),
    " arms ", radios("fArms", ["side-by-side", "upstream", "width-only"], "side-by-side"));
  const note = document.createElement("p");
  note.className = "note";
  note.textContent = DATA.note;
  f.appendChild(note);
  render();
}
function armVisible(name) {
  const mode = radioVal("fArms");
  return mode === "side-by-side" || mode === name;
}
function showArt(parent, label, art, zoom) {
  const div = document.createElement("div");
  div.className = "arm";
  const b = document.createElement("b");
  b.textContent = label;
  div.appendChild(b);
  const cv = document.createElement("canvas");
  draw(cv, art, zoom);
  div.appendChild(cv);
  parent.appendChild(div);
}
function glyphPair(g) {
  const up = g.upstream, wo = {...g.width_only.frame, pixels: g.width_only.pixels};
  const left = Math.min(0, up.left, wo.left), top = Math.min(0, up.top, wo.top);
  const width = Math.max(0, up.left + up.width, wo.left + wo.width) - left;
  const height = Math.max(0, up.top + up.height, wo.top + wo.height) - top;
  function pad(art) {
    const pixels = new Array(width * height).fill(0);
    for (let y = 0; y < art.height; y++) for (let x = 0; x < art.width; x++) {
      pixels[(art.top - top + y) * width + art.left - left + x] = art.pixels[y * art.width + x];
    }
    return {width, height, pixels};
  }
  return {...g, upstream: pad(up), width_only: pad(wo)};
}
function render() {
  const box = document.getElementById("cell");
  const banner = document.getElementById("banner");
  box.innerHTML = "";
  banner.innerHTML = "";
  const cells = DATA.cells.flatMap(c => c.files);
  const cell = cells.find(c => c.family === selected("fFam") &&
    String(c.weight) === selected("fWght") && String(c.size) === selected("fSize") &&
    c.hint_mode === selected("fHint"));
  if (!cell) { box.textContent = "no cell matches the filters"; return; }
  fetch(cell.file).then(r => r.json()).then(data => {
    const zoom = parseInt(selected("fZoom"), 10);
    if (data.paragraph) {
      const div = document.createElement("div");
      div.className = "line";
      const p = document.createElement("p");
      p.textContent = "paragraph at native baselines " +
        data.paragraph.line_baselines.join(", ");
      div.appendChild(p);
      const row = document.createElement("div");
      row.className = "row";
      if (armVisible("upstream")) showArt(row, "upstream paragraph", data.paragraph.upstream, zoom);
      if (armVisible("width-only")) showArt(row, "width-only paragraph", data.paragraph.width_only, zoom);
      div.appendChild(row);
      box.appendChild(div);
    }
    (data.lines || []).forEach(line => {
      const div = document.createElement("div");
      div.className = "line";
      const p = document.createElement("p");
      p.textContent = line.text;
      div.appendChild(p);
      const row = document.createElement("div");
      row.className = "row";
      if (armVisible("upstream")) showArt(row, "upstream", line.arms.upstream, zoom);
      if (armVisible("width-only")) showArt(row, "width-only", line.arms.width_only, zoom);
      div.appendChild(row);
      box.appendChild(div);
    });
    const counts = document.createElement("p");
    counts.className = "note";
    counts.textContent = "width-only applied " + data.counts.applied +
      ", abstained " + data.counts.abstained +
      " (" + Object.entries(data.counts.reasons).map(([k, v]) => k + ": " + v).join(", ") + ")";
    box.appendChild(counts);
    const table = document.createElement("table");
    const head = document.createElement("tr");
    ["glyph", "codepoint", "decision", "reason", "src/up/cand px"].forEach(h => {
      const th = document.createElement("th"); th.textContent = h; head.appendChild(th);
    });
    table.appendChild(head);
    data.glyphs.forEach(g => {
      const tr = document.createElement("tr");
      const widths = g.widths ?
        g.widths.source.toFixed(3) + " / " + g.widths.upstream.toFixed(3) +
        " / " + g.widths.candidate.toFixed(3) : "";
      [g.char, "U+" + g.codepoint.toString(16).toUpperCase(),
       g.applied ? "applied" : "upstream", g.reason || "", widths].forEach(v => {
        const td = document.createElement("td"); td.textContent = v; tr.appendChild(td);
      });
      table.appendChild(tr);
    });
    box.appendChild(table);
    const donors = document.createElement("div");
    donors.className = "row";
    const controls = new Set([65,73,86,87,102,104,105,107,108,110,116,118,120,121,122]);
    data.glyphs.filter(g => g.applied || controls.has(g.codepoint)).map(glyphPair).forEach(g => {
      const wrap = document.createElement("div");
      wrap.className = "arm";
      const b = document.createElement("b");
      b.textContent = g.char + " U+" + g.codepoint.toString(16).toUpperCase() +
        " (" + (g.applied ? "applied" : "upstream") + ")";
      wrap.appendChild(b);
      const row = document.createElement("div");
      row.className = "row";
      if (armVisible("upstream")) showArt(row, "upstream", g.upstream, zoom);
      if (armVisible("width-only")) showArt(row, "width-only", g.width_only, zoom);
      wrap.appendChild(row);
      donors.appendChild(wrap);
    });
    box.appendChild(donors);
  });
}
load();
</script>
</body>
</html>
"""


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--captures", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--topology-binary", default=None)
    parser.add_argument("--family", default=None)
    parser.add_argument("--size", type=float, default=None)
    parser.add_argument("--weight", type=float, default=None)
    parser.add_argument("--resume", action="store_true",
                        help="reuse validated hint cells for a config only "
                             "after schema/provenance checks, recomposing "
                             "frames with the current compositor")
    args = parser.parse_args(argv)

    binary = run.resolve_adapter(args.adapter)
    run.check_binary(binary)
    topology_binary = args.topology_binary or os.path.join(
        "out", "diagnostics", "direct-diagonal", "exact-topology",
        "bin", "exact_topology")
    if not (os.path.isfile(topology_binary)
            and os.access(topology_binary, os.X_OK)):
        fail("topology binary missing: %s" % topology_binary)
    with open(topology_binary, "rb") as handle:
        topology_sha256 = hashlib.sha256(handle.read()).hexdigest()
    if topology_sha256 != FROZEN_TOPOLOGY_SHA256:
        fail("topology binary mismatch: %s" % topology_sha256)

    import functools
    import importlib
    try:
        core = importlib.import_module(
            "experiments.hobby_fitting.direct_diagonal")
    except ImportError as exc:
        fail("core module unavailable: %s" % exc)
    for name in ("build_reference", "fit_glyph"):
        if not callable(getattr(core, name, None)):
            fail("core module misses %s" % name)
    from experiments.hobby_fitting import exact_topology
    checker = functools.partial(
        exact_topology.compare_commands, binary=topology_binary)

    capture_sha256 = assert_frozen_captures(args.captures)
    frozen_cases = load_cases(args.captures)
    frozen_items = list(run.iter_records(frozen_cases))
    frozen_by_key = {(group_key(i), i["codepoint"]): i["record"]
                     for i in frozen_items}
    base_dir = os.path.dirname(os.path.abspath(args.captures))
    joins_dir = os.path.join(base_dir, "joins-evaluation")
    with open(os.path.join(joins_dir, "summary.json")) as handle:
        joins_summary = json.load(handle)
    if joins_summary.get("capture_sha256") != JOINS_CAPTURE_SHA256:
        fail("joins-evaluation is not built from the frozen captures")
    joins_map = joins_lookup(joins_summary)
    strict_counts = None
    strict_path = os.path.join(base_dir, "evaluation", "summary.json")
    if os.path.isfile(strict_path):
        with open(strict_path) as handle:
            strict_counts = json.load(handle).get("counts")

    if args.family is not None and args.family not in FONT_PATHS:
        fail("unknown family %s (want %s)"
             % (args.family, sorted(FONT_PATHS)))
    families = [args.family] if args.family else sorted(FONT_PATHS)
    sizes = [args.size] if args.size is not None else list(SIZES)
    weights = [args.weight] if args.weight is not None else list(WEIGHTS)

    out = args.out
    os.makedirs(os.path.join(out, "cells"), exist_ok=True)
    ascii_dir = os.path.join(out, "ascii-captures")
    os.makedirs(ascii_dir, exist_ok=True)
    scratch = os.path.join(out, ".scratch")
    os.makedirs(scratch, exist_ok=True)

    with open(binary, "rb") as handle:
        adapter_sha256 = hashlib.sha256(handle.read()).hexdigest()
    prov = {"tool": TOOL_VERSION,
            "model_source": MODEL_FILE,
            "model_source_sha256": model_source_sha256(),
            "topology_binary_sha256": topology_sha256,
            "adapter_sha256": adapter_sha256}
    summary_cells = []
    for family in families:
        for size in sizes:
            for weight in weights:
                axes = frozen_axes_for(frozen_cases, family, weight)
                if args.resume and saved_config_complete(
                        out, family, size, weight, axes):
                    files = []
                    for hint in HINT_MODES:
                        stem = "%s_%s_%s_%s" % (
                            family, str(size), str(int(weight)), hint)
                        name = "".join(
                            c if c.isalnum() or c in "-_." else "_"
                            for c in stem) + ".json"
                        files.append(recompose_saved_cell(
                            os.path.join(out, "cells", name),
                            joins_map, joins_dir, prov))
                    summary_cells.append(
                        {"family": family, "size": size, "weight": weight,
                         "axes": axes, "files": files, "resumed": True})
                    continue
                summary_cells.append(process_cell(
                    binary, checker, core, family, size, weight, axes,
                    frozen_items, frozen_by_key,
                    joins_map, joins_dir,
                    ascii_dir, scratch, out, prov))
    summary = {
        "tool": TOOL_VERSION,
        "captures": args.captures,
        "capture_sha256": capture_sha256,
        "adapter": binary,
        "adapter_sha256": adapter_sha256,
        "topology_binary": topology_binary,
        "topology_binary_sha256": topology_sha256,
        "cgal_version": "6.1.1",
        "model_source": MODEL_FILE,
        "model_source_sha256": prov["model_source_sha256"],
        "frozen_donors": DONOR_CHARS,
        "ascii_repertoire": "U+0020..U+007E",
        "text_lines": TEXT_LINES,
        "joins_counts": joins_summary.get("counts"),
        "strict_baseline_counts": strict_counts,
        "resumed": args.resume,
        "resume_note": "reused hint cells passed identity, repertoire, "
                       "ready-layout, reference-hash and frozen-joins "
                       "checks before recomposition" if args.resume else None,
        "layout_note": "paired arms share one finalized native layout; "
                       "no CSS font text is rendered",
        "note": "Frozen width-only model with exact topology checker. "
                "Grid fitting and curves stay upstream.",
        "cells": summary_cells,
    }
    tmp_summary = os.path.join(out, "summary.json.tmp")
    with open(tmp_summary, "w") as handle:
        json.dump(summary, handle)
    os.replace(tmp_summary, os.path.join(out, "summary.json"))
    tmp_index = os.path.join(out, "index.html.tmp")
    with open(tmp_index, "w") as handle:
        handle.write(INDEX_HTML)
    os.replace(tmp_index, os.path.join(out, "index.html"))
    return summary


def saved_config_complete(out, family, size, weight, axes):
    """Both hint cells present and passing saved-cell checks."""
    for hint in HINT_MODES:
        stem = "%s_%s_%s_%s" % (family, str(size), str(int(weight)), hint)
        name = "".join(
            c if c.isalnum() or c in "-_." else "_" for c in stem) + ".json"
        path = os.path.join(out, "cells", name)
        if not os.path.isfile(path):
            return False
        with open(path) as handle:
            try:
                cell = json.load(handle)
            except ValueError:
                return False
        if saved_cell_problems(cell, family, size, weight, axes, hint):
            return False
    return True


if __name__ == "__main__":
    main()
