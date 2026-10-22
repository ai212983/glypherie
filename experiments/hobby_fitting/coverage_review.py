#!/usr/bin/env python3
"""Three-arm coverage comparison against the frozen text review.

Loads ASCII captures and native layout from the frozen text-review packet,
checks donor geometry and reference equality, fits the current core
width-only with the recorded checker policy, and rasterizes through the
adapter. Compares upstream, frozen width-only and candidate arms in
ordinary paragraphs and glyphs. Baseline donor checks validate the frozen
packet against joins-evaluation; the candidate may differ intentionally.
"""

import argparse
import collections
import functools
import hashlib
import json
import os
import sys
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from experiments.hobby_fitting import direct_diagonal_run as run
from experiments.hobby_fitting import text_review as review

TOOL_VERSION = "coverage-review-v1"
BASELINE_TOOL = "text-review-v1"
MODEL_FILE = review.MODEL_FILE
# Every module the width-only fit depends on; a resumed cell is valid
# only when all of these match the current checkout.
MODEL_DEPS = (
    "experiments/hobby_fitting/direct_diagonal.py",
    "experiments/hobby_fitting/intervals.py",
    "experiments/hobby_fitting/real_outline.py",
    "experiments/hobby_fitting/prototype.py",
    "experiments/hobby_fitting/exact_topology.py",
    "experiments/hobby_fitting/curve_clearance.py",
)
FROZEN_CAPTURE_SHA256 = review.FROZEN_CAPTURE_SHA256
FROZEN_TOPOLOGY_SHA256 = review.FROZEN_TOPOLOGY_SHA256
FROZEN_MODEL_SHA256 = "fca78942d78a8566766349c4977d29fa1af00449dc08992df83436eedf47cc50"

DONOR_CODES = review.DONOR_CODES
ASCII_95 = review.ASCII_95
HINT_MODES = review.HINT_MODES


def fail(message):
    raise SystemExit("coverage-review: " + message)


def sha_file(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def model_provenance():
    """SHA256 of every module the current fit depends on.

    The study explicitly enables canonical discovery and fixed-curve
    certificates, so their helper is always part of the identity.
    """
    prov = {}
    for rel in MODEL_DEPS:
        prov[rel] = sha_file(os.path.join(REPO, rel))
    return prov


def load_json(path):
    with open(path) as handle:
        return json.load(handle)


def assert_baseline_provenance(summary):
    if summary.get("tool") != BASELINE_TOOL:
        fail("baseline tool %s != %s" % (summary.get("tool"), BASELINE_TOOL))
    for key, want in (("capture_sha256", FROZEN_CAPTURE_SHA256),
                      ("topology_binary_sha256", FROZEN_TOPOLOGY_SHA256),
                      ("model_source_sha256", FROZEN_MODEL_SHA256)):
        if summary.get(key) != want:
            fail("baseline %s mismatch" % key)


def baseline_cell_path(baseline_out, family, size, weight, hint):
    stem = "%s_%s_%s_%s" % (family, str(size), str(int(weight)), hint)
    name = "".join(c if c.isalnum() or c in "-_." else "_" for c in stem) + ".json"
    return os.path.join(baseline_out, "cells", name)


def ascii_capture_path(baseline_out, family, weight, size):
    return os.path.join(baseline_out, "ascii-captures",
                        "%s-%d-%d.json" % (family, int(weight), int(size)))


def pair_ids(result):
    return [p.get("id") for p in (result.get("pairs") or []) if p.get("id")]


def reject_counts(result):
    counts = collections.Counter()
    for entry in (result.get("skipped") or []):
        counts[entry.get("reason", "unstated")] += 1
    return dict(counts)


def pixel_diff(first, second):
    if len(first) != len(second):
        fail("pixel length %d != %d" % (len(first), len(second)))
    return sum(1 for a, b in zip(first, second) if bool(a) != bool(b))


def art_box(art):
    """Tile box for flat upstream art or nested width-only frames."""
    frame = art.get("frame", art)
    if not isinstance(frame, dict) or "pixels" not in art:
        fail("art without frame or pixels")
    for key in ("left", "top", "width", "height"):
        if key not in frame:
            fail("art frame misses %s" % key)
    return (frame["left"], frame["top"], frame["width"],
            frame["height"], art["pixels"])


def framed_diff(first, second):
    """Ink difference over the union box; off-tile counts as empty."""
    def ink(art):
        left, top, width, height, pixels = art_box(art)
        return {(left + i, top + j)
                for j in range(height) for i in range(width)
                if pixels[j * width + i]} if width and height else set()
    return len(ink(first) ^ ink(second))


def pair_detail(pair):
    """Delivered per-pair interval, width and movement evidence.

    Missing keys stay None: synthetic fixtures carry ids only.
    """
    if not isinstance(pair, dict):
        return {"id": None}
    return {
        "id": pair.get("id"),
        "interval": pair.get("interval"),
        "feet": pair.get("feet"),
        "source_width": pair.get("source_width"),
        "upstream_width": pair.get("upstream_width"),
        "candidate_width": pair.get("candidate_width"),
        "bound": pair.get("bound"),
        "peak": pair.get("peak"),
        "prefix": pair.get("prefix"),
        "phase_applied": pair.get("phase_applied"),
    }


def coverage_delta(frozen, candidate, upstream):
    """Activity record for one glyph across the three arms.

    Labels name delivered-vs-rejected coverage activity only; they
    are not optical classifications. A glyphwide applied flag means
    at least one pair was delivered, never whole-stroke coverage.
    """
    frozen_pairs = set(pair_ids(frozen))
    candidate_pairs = set(pair_ids(candidate))
    frozen_applied = bool(frozen.get("applied"))
    candidate_applied = bool(candidate.get("applied"))
    if candidate_applied and not frozen_applied:
        change = "newly-covered"
    elif frozen_applied and not candidate_applied:
        change = "lost"
    else:
        change = "same-decision"
    return {
        "frozen_applied": frozen_applied,
        "candidate_applied": candidate_applied,
        "coverage_change": change,
        "pairs_common": sorted(frozen_pairs & candidate_pairs),
        "pairs_added": sorted(candidate_pairs - frozen_pairs),
        "pairs_removed": sorted(frozen_pairs - candidate_pairs),
        "pairs_frozen": [pair_detail(p) for p in (frozen.get("pairs") or [])],
        "pairs_candidate": [pair_detail(p)
                            for p in (candidate.get("pairs") or [])],
        "candidate_rejected_attempt": bool(candidate.get("attempt")),
        "frozen_rejected": reject_counts(frozen),
        "candidate_rejected": reject_counts(candidate),
        "pixels_up_frozen": framed_diff(upstream, frozen),
        "pixels_up_candidate": framed_diff(upstream, candidate),
        "pixels_frozen_candidate": framed_diff(frozen, candidate),
        "widths_frozen": frozen.get("widths"),
        "widths_candidate": candidate.get("widths"),
    }


def compose_line_three(line, up_tiles, frozen_tiles, cand_tiles):
    """Shared union frame over all three arms; browser replicates zoom."""
    up_extents, up_ink = review.extent_parts(line, up_tiles)
    frozen_extents, frozen_ink = review.extent_parts(line, frozen_tiles)
    cand_extents, cand_ink = review.extent_parts(line, cand_tiles)
    frame = review.union_frame(up_extents + frozen_extents + cand_extents)
    baseline_y = line["baseline"] + frame["origin_y"] \
        if frame["width"] or frame["height"] else 0
    shared = dict(frame, baseline_y=baseline_y)
    return {"frame": shared,
            "upstream": dict(shared, pixels=review.render_frame(up_ink, frame)),
            "frozen": dict(shared, pixels=review.render_frame(frozen_ink, frame)),
            "candidate": dict(shared, pixels=review.render_frame(cand_ink, frame))}


def compose_paragraph_three(lines, up_tiles, frozen_tiles, cand_tiles):
    up_extents, frozen_extents, cand_extents = [], [], []
    up_ink, frozen_ink, cand_ink = [], [], []
    for line in lines:
        extents, ink = review.extent_parts(line, up_tiles)
        up_extents.extend(extents)
        up_ink.extend(ink)
        extents, ink = review.extent_parts(line, frozen_tiles)
        frozen_extents.extend(extents)
        frozen_ink.extend(ink)
        extents, ink = review.extent_parts(line, cand_tiles)
        cand_extents.extend(extents)
        cand_ink.extend(ink)
    frame = review.union_frame(up_extents + frozen_extents + cand_extents)
    return {"frame": frame,
            "texts": [line.get("text", "") for line in lines],
            "line_baselines": [line["baseline"] + frame["origin_y"] for line in lines],
            "upstream": dict(frame, pixels=review.render_frame(up_ink, frame)),
            "frozen": dict(frame, pixels=review.render_frame(frozen_ink, frame)),
            "candidate": dict(frame, pixels=review.render_frame(cand_ink, frame))}


def candidate_tiles(results):
    tiles = {}
    for code, entry in results.items():
        art = entry["candidate"]
        frame = art.get("frame", art)
        tiles[code] = {"left": frame["left"], "top": frame["top"],
                       "width": frame["width"], "height": frame["height"],
                       "pixels": art["pixels"]}
    return tiles


def saved_coverage_problems(cell, family, size, weight, axes, hint,
                             candidate_core_sha, model_dependencies=None):
    """Checkable identity and provenance of a persisted coverage cell.

    Any model-dependency change invalidates the cell: the width-only
    fit reads every module in MODEL_DEPS.
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
    elif [line.get("text") for line in layout.get("lines", [])] != review.TEXT_LINES:
        problems.append("layout-text")
    elif cell.get("layout_status", {}).get("status") != "ready":
        problems.append("layout-status")
    reference = cell.get("reference")
    if not isinstance(reference, dict) or \
            cell.get("reference_sha256") != review.reference_sha256(reference):
        problems.append("reference-hash")
    if cell.get("baseline", {}).get("model_source_sha256") != FROZEN_MODEL_SHA256:
        problems.append("baseline-model")
    if cell.get("candidate_core_sha256") != candidate_core_sha:
        problems.append("candidate-core")
    if model_dependencies is not None and \
            cell.get("model_dependencies") != model_dependencies:
        problems.append("model-dependencies")
    if not isinstance(cell.get("counts"), dict):
        problems.append("counts")
    return problems


def recompose_saved_cell(path, joins_map, joins_dir, prov):
    """Recompose one validated coverage cell with the current compositor.

    Frozen art, candidate art and the native layout are reused untouched;
    only the shared three-arm frames are redone. Frozen donor fits are
    re-validated against the frozen joins before the rewrite.
    """
    cell = load_json(path)
    problems = saved_coverage_problems(
        cell, cell["family"], cell["size"], cell["weight"],
        cell["axes"], cell["hint_mode"], prov["candidate_core_sha256"],
        prov.get("model_dependencies"))
    if problems:
        fail("saved coverage cell %s invalid: %s" % (path, problems))
    review.check_donor_delivery(
        joins_map, joins_dir,
        {"family": cell["family"], "size": cell["size"],
         "axes": cell["axes"], "hint_mode": cell["hint_mode"]},
        {g["codepoint"]: g["frozen"]
         for g in cell["glyphs"] if g["codepoint"] in DONOR_CODES})
    up_tiles, frozen_tiles, cand_tiles = {}, {}, {}
    for glyph in cell["glyphs"]:
        for key, tiles in (("upstream", up_tiles), ("frozen", frozen_tiles),
                           ("candidate", cand_tiles)):
            art = glyph[key]
            frame = art.get("frame", art)
            tiles[glyph["codepoint"]] = {
                "left": frame["left"], "top": frame["top"],
                "width": frame["width"], "height": frame["height"],
                "pixels": art["pixels"]}
    mode_lines = cell["layout"]["lines"]
    lines = []
    for line in mode_lines:
        composed = compose_line_three(line, up_tiles, frozen_tiles, cand_tiles)
        lines.append({"text": line["text"], "frame": composed["frame"],
                      "arms": {"upstream": composed["upstream"],
                               "frozen": composed["frozen"],
                               "candidate": composed["candidate"]}})
    cell["lines"] = lines
    cell["paragraph"] = compose_paragraph_three(mode_lines, up_tiles,
                                                frozen_tiles, cand_tiles)
    cell["harness"] = dict(prov, resumed=True)
    with open(path, "w") as handle:
        json.dump(cell, handle)
    counts = cell["counts"]
    return {"file": os.path.join("cells", os.path.basename(path)),
            "family": cell["family"], "size": cell["size"],
            "weight": cell["weight"], "axes": cell["axes"],
            "hint_mode": cell["hint_mode"], "counts": counts,
            "reference_sha256": cell["reference_sha256"],
            "layout": "ready", "capture": cell["capture"],
            "candidate_core_sha256": cell["candidate_core_sha256"]}


def process_cell(binary, checker, core, family, size, weight, axes,
                 members, baseline_cell, joins_map, joins_dir,
                 scratch, out, prov):
    """Fit one hint cell and emit its three-arm coverage JSON."""
    records_by_code = {m["codepoint"]: m["record"] for m in members}
    baseline_glyphs = {g["codepoint"]: g for g in baseline_cell["glyphs"]}
    if sorted(records_by_code) != list(range(0x20, 0x7F)):
        fail("ascii capture repertoire != ASCII95 for %s %s %s" % (family, size, axes))
    review.check_layout_mode(baseline_cell["layout"], baseline_cell["hint_mode"],
                             records_by_code,
                             baseline_cell["layout"].get("extensions"))
    references = review.build_donor_references(core, members)
    key = next(iter(references))
    reference = references[key]["reference"]
    ref_hash = review.reference_sha256(reference)
    if ref_hash != baseline_cell["reference_sha256"]:
        fail("reference mismatch for %s %s %s" % (family, size, axes))
    study_core = SimpleNamespace(fit_glyph=functools.partial(
        core.fit_glyph, curve_clearance=True))
    results = review.fit_cell(study_core, checker, binary,
                              [m["record"] for m in members],
                              members[0]["size"], reference, scratch)
    glyph_rows, donor_glyphs = [], []
    counts = {"applied": 0, "abstained": 0, "reasons": {},
              "newly_covered": 0, "lost": 0, "pixels_changed": 0}
    for m in sorted(members, key=lambda m: m["codepoint"]):
        code, entry = m["codepoint"], results[m["codepoint"]]
        cand = entry["width_only"]
        base = baseline_glyphs[code]
        if entry["upstream"]["pixels"] != base["upstream"]["pixels"]:
            fail("U+%04X upstream raster != baseline packet" % code)
        for box_key in ("left", "top", "width", "height"):
            if entry["upstream"][box_key] != records_by_code[code][box_key]:
                fail("U+%04X upstream box != capture" % code)
        if not cand.get("applied") and cand.get("pixels") != entry["upstream"]["pixels"]:
            fail("U+%04X abstained yet pixels differ" % code)
        frozen = base["width_only"]
        delta = coverage_delta(frozen, cand, entry["upstream"])
        if cand.get("applied"):
            counts["applied"] += 1
        else:
            counts["abstained"] += 1
            reason = cand.get("reason", "unstated")
            counts["reasons"][reason] = counts["reasons"].get(reason, 0) + 1
        if delta["coverage_change"] == "newly-covered":
            counts["newly_covered"] += 1
        elif delta["coverage_change"] == "lost":
            counts["lost"] += 1
        if delta["pixels_frozen_candidate"]:
            counts["pixels_changed"] += 1
        glyph_rows.append({
            "char": chr(code), "codepoint": code,
            "applied_frozen": bool(frozen.get("applied")),
            "reason_frozen": None if frozen.get("applied") else frozen.get("reason"),
            "applied": bool(cand.get("applied")),
            "reason": None if cand.get("applied") else cand.get("reason"),
            "native_axes": entry["native_axes"],
            "ownership": entry["ownership"],
            "upstream_commands": m["record"]["fitted_commands"],
            "upstream": entry["upstream"],
            "frozen": frozen,
            "candidate": cand,
            "delta": delta})
        if code in DONOR_CODES:
            donor_glyphs.append({"char": chr(code), "codepoint": code,
                                 "applied_frozen": bool(frozen.get("applied")),
                                 "applied": bool(cand.get("applied"))})
    review.check_donor_delivery(
        joins_map, joins_dir,
        {"family": family, "size": members[0]["size"],
         "axes": axes, "hint_mode": members[0]["hint_mode"]},
        {g["codepoint"]: baseline_glyphs[g["codepoint"]]["width_only"]
         for g in members if g["codepoint"] in DONOR_CODES})
    up_tiles = review.tiles_for(results, "upstream")
    frozen_tiles = {}
    cand_tiles = candidate_tiles(
        {code: {"candidate": results[code]["width_only"]} for code in results})
    for glyph in glyph_rows:
        frame = glyph["frozen"].get("frame", glyph["frozen"])
        frozen_tiles[glyph["codepoint"]] = {
            "left": frame["left"], "top": frame["top"],
            "width": frame["width"], "height": frame["height"],
            "pixels": glyph["frozen"]["pixels"]}
    mode_lines = baseline_cell["layout"]["lines"]
    lines = []
    for line in mode_lines:
        composed = compose_line_three(line, up_tiles, frozen_tiles, cand_tiles)
        lines.append({"text": line["text"], "frame": composed["frame"],
                      "arms": {"upstream": composed["upstream"],
                               "frozen": composed["frozen"],
                               "candidate": composed["candidate"]}})
    paragraph = compose_paragraph_three(mode_lines, up_tiles,
                                        frozen_tiles, cand_tiles)
    stem = "%s_%s_%s_%s" % (family, str(size), str(int(weight)),
                            members[0]["hint_mode"])
    filename = "cells/%s.json" % "".join(
        c if c.isalnum() or c in "-_." else "_" for c in stem)
    cell = {"family": family, "size": size, "weight": weight,
            "axes": axes, "hint_mode": members[0]["hint_mode"],
            "harness": prov,
            "baseline": {"tool": BASELINE_TOOL,
                         "model_source_sha256": baseline_cell["harness"].get(
                             "model_source_sha256"),
                         "reference_sha256": baseline_cell["reference_sha256"],
                         "capture": baseline_cell["capture"]},
            "candidate_core_sha256": prov["candidate_core_sha256"],
            "model_dependencies": prov.get("model_dependencies"),
            "layout_status": baseline_cell["layout_status"],
            "layout": baseline_cell["layout"],
            "reference": baseline_cell["reference"],
            "reference_sha256": ref_hash,
            "lines": lines, "paragraph": paragraph,
            "counts": counts, "glyphs": glyph_rows,
            "donor_glyphs": donor_glyphs,
            "capture_policy": baseline_cell.get("capture_policy"),
            "capture": baseline_cell["capture"]}
    with open(os.path.join(out, filename), "w") as handle:
        json.dump(cell, handle)
    return {"file": filename, "family": family, "size": size,
            "weight": weight, "axes": axes,
            "hint_mode": members[0]["hint_mode"], "counts": counts,
            "reference_sha256": ref_hash, "layout": "ready",
            "capture": baseline_cell["capture"],
            "candidate_core_sha256": prov["candidate_core_sha256"]}


def process_config(binary, checker, core, family, size, weight, axes,
                   frozen_by_key, joins_map, joins_dir,
                   baseline_out, scratch, out, prov):
    """Fit both hint cells for one family/size/weight config."""
    ascii_path = ascii_capture_path(baseline_out, family, weight, size)
    if not os.path.isfile(ascii_path):
        fail("baseline ascii capture missing: %s" % ascii_path)
    manifest = review.ascii_manifest(
        ascii_path, family, size, weight, axes,
        os.path.join(REPO, review.FONT_PATHS[family]))
    if manifest is None:
        fail("ascii manifest mismatch for %s %s %s" % (family, size, weight))
    items = list(run.iter_records(review.load_cases(ascii_path)))
    review.check_donor_recapture(frozen_by_key, items)
    files = []
    for hint in HINT_MODES:
        with open(baseline_cell_path(baseline_out, family, size, weight, hint)) as handle:
            baseline_cell = json.load(handle)
        if review.saved_cell_problems(baseline_cell, family, size, weight,
                                      axes, hint):
            fail("baseline cell invalid for %s %s %s %s"
                 % (family, size, weight, hint))
        if baseline_cell["capture"] != manifest["file_sha256"]:
            fail("baseline capture != ascii file for %s %s %s %s"
                 % (family, size, weight, hint))
        members = review.cell_items(items, family, size, axes, hint)
        if not members:
            fail("ascii capture has no %s records" % hint)
        files.append(process_cell(
            binary, checker, core, family, size, weight, axes,
            members, baseline_cell, joins_map, joins_dir,
            scratch, out, prov))
    return {"family": family, "size": size, "weight": weight,
            "axes": axes, "files": files}


def saved_config_complete(out, family, size, weight, axes, candidate_core_sha,
                          model_dependencies=None):
    for hint in HINT_MODES:
        stem = "%s_%s_%s_%s" % (family, str(size), str(int(weight)), hint)
        name = "".join(c if c.isalnum() or c in "-_." else "_" for c in stem) + ".json"
        path = os.path.join(out, "cells", name)
        if not os.path.isfile(path):
            return False
        with open(path) as handle:
            try:
                cell = json.load(handle)
            except ValueError:
                return False
        if saved_coverage_problems(cell, family, size, weight, axes, hint,
                                   candidate_core_sha, model_dependencies):
            return False
    return True


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Border-interval coverage review (three arms)</title>
<link rel="icon" href="data:,">
<style>
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:16px;color:#222;max-width:1400px}
canvas{image-rendering:pixelated;border:1px solid #999;background:#fff}
label{margin-right:12px}
.line{margin:12px 0;padding:8px;border:1px solid #ddd}
.line p{margin:4px 0;font-size:13px}
.row{display:flex;gap:24px;align-items:flex-start;flex-wrap:wrap}
.arm b{display:block;margin-bottom:4px}
table{border-collapse:collapse;font-size:13px;margin-top:8px}
td,th{border:1px solid #ccc;padding:2px 8px;text-align:left}
.note{font-size:13px;color:#555}
</style>
</head>
<body>
<h1>Border-interval coverage review (three arms)</h1>
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
    " arms ", radios("fArms", ["side-by-side", "upstream", "frozen", "candidate"], "side-by-side"));
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
  const up = g.upstream, fr = {...g.frozen.frame, pixels: g.frozen.pixels};
  const cd = {...g.candidate.frame, pixels: g.candidate.pixels};
  const left = Math.min(0, up.left, fr.left, cd.left), top = Math.min(0, up.top, fr.top, cd.top);
  const width = Math.max(0, up.left + up.width, fr.left + fr.width, cd.left + cd.width) - left;
  const height = Math.max(0, up.top + up.height, fr.top + fr.height, cd.top + cd.height) - top;
  function pad(art) {
    const pixels = new Array(width * height).fill(0);
    for (let y = 0; y < art.height; y++) for (let x = 0; x < art.width; x++) {
      pixels[(art.top - top + y) * width + art.left - left + x] = art.pixels[y * art.width + x];
    }
    return {width, height, pixels};
  }
  return {...g, upstream: pad(up), frozen: pad(fr), candidate: pad(cd)};
}
function render() {
  const box = document.getElementById("cell");
  box.innerHTML = "";
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
      if (armVisible("frozen")) showArt(row, "frozen paragraph", data.paragraph.frozen, zoom);
      if (armVisible("candidate")) showArt(row, "candidate paragraph", data.paragraph.candidate, zoom);
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
      if (armVisible("frozen")) showArt(row, "frozen", line.arms.frozen, zoom);
      if (armVisible("candidate")) showArt(row, "candidate", line.arms.candidate, zoom);
      div.appendChild(row);
      box.appendChild(div);
    });
    const counts = document.createElement("p");
    counts.className = "note";
    counts.textContent = "candidate applied " + data.counts.applied +
      ", abstained " + data.counts.abstained +
      ", newly covered " + data.counts.newly_covered +
      ", lost " + data.counts.lost +
      ", pixels changed vs frozen " + data.counts.pixels_changed +
      " (" + Object.entries(data.counts.reasons).map(([k, v]) => k + ": " + v).join(", ") + ")";
    box.appendChild(counts);
    const table = document.createElement("table");
    const head = document.createElement("tr");
    ["glyph", "codepoint", "frozen", "candidate", "coverage", "pairs fz/cand",
     "rejected frozen", "rejected candidate", "px up/fz", "px up/cd",
     "px fz/cd", "widths fz", "widths cd"].forEach(h => {
      const th = document.createElement("th"); th.textContent = h; head.appendChild(th);
    });
    table.appendChild(head);
    data.glyphs.forEach(g => {
      const tr = document.createElement("tr");
      const d = g.delta;
      const pairs = (g.frozen.pairs || []).length + " / " + (g.candidate.pairs || []).length +
        (d.pairs_added.length || d.pairs_removed.length ?
          " (+" + d.pairs_added.length + "/-" + d.pairs_removed.length + ")" : "");
      [g.char, "U+" + g.codepoint.toString(16).toUpperCase(),
       g.applied_frozen ? "applied" : "upstream", g.applied ? "applied" : "upstream",
       d.coverage_change, pairs,
       JSON.stringify(d.frozen_rejected), JSON.stringify(d.candidate_rejected),
       d.pixels_up_frozen, d.pixels_up_candidate, d.pixels_frozen_candidate,
       g.widths_frozen || (d.widths_frozen ? JSON.stringify(d.widths_frozen) : ""),
       g.widths_candidate || (d.widths_candidate ? JSON.stringify(d.widths_candidate) : "")
      ].forEach(v => {
        const td = document.createElement("td"); td.textContent = v; tr.appendChild(td);
      });
      table.appendChild(tr);
    });
    box.appendChild(table);
    const donors = document.createElement("div");
    donors.className = "row";
    const controls = new Set([65,73,86,87,102,104,105,107,108,110,116,118,120,121,122]);
    data.glyphs.filter(g => g.applied || g.applied_frozen || controls.has(g.codepoint)).map(glyphPair).forEach(g => {
      const wrap = document.createElement("div");
      wrap.className = "arm";
      const b = document.createElement("b");
      b.textContent = g.char + " U+" + g.codepoint.toString(16).toUpperCase() +
        " (frozen " + (g.applied_frozen ? "applied" : "upstream") +
        " / candidate " + (g.applied ? "applied" : "upstream") + ")";
      wrap.appendChild(b);
      const row = document.createElement("div");
      row.className = "row";
      if (armVisible("upstream")) showArt(row, "upstream", g.upstream, zoom);
      if (armVisible("frozen")) showArt(row, "frozen", g.frozen, zoom);
      if (armVisible("candidate")) showArt(row, "candidate", g.candidate, zoom);
      wrap.appendChild(row);
      const original = data.glyphs.find(item => item.codepoint === g.codepoint);
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "Border intervals and abstentions";
      details.appendChild(summary);
      const evidence = document.createElement("pre");
      evidence.style = "white-space:pre-wrap;max-width:600px;font-size:12px";
      evidence.textContent = JSON.stringify({
        delivered: original.candidate.applied,
        pairs: (original.candidate.pairs || []).map(p => ({
          id: p.id, interval: p.interval, contact_ranges: p.feet,
          width_source: p.source_width, width_upstream: p.upstream_width,
          width_delivered: p.candidate_width,
          movement_rounded: p.rounded_peak,
          movement_limit_with_rounding: p.bound + Math.SQRT2 / 128
        })),
        abstentions: original.candidate.skipped
      }, null, 2);
      details.appendChild(evidence);
      wrap.appendChild(details);
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
    parser.add_argument("--baseline",
                        default=os.path.join("out", "diagnostics",
                                             "direct-diagonal", "text-review"))
    parser.add_argument("--captures", default=None)
    parser.add_argument("--joins-dir", default=None)
    parser.add_argument("--out",
                        default=os.path.join("out", "diagnostics",
                                             "direct-diagonal", "coverage-review"))
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--topology-binary", default=None)
    parser.add_argument("--family", default=None)
    parser.add_argument("--size", type=float, default=None)
    parser.add_argument("--weight", type=float, default=None)
    parser.add_argument("--resume", action="store_true",
                        help="reuse validated coverage cells for a config only "
                             "after identity, repertoire, reference and "
                             "candidate-core checks, recomposing frames")
    args = parser.parse_args(argv)

    binary = run.resolve_adapter(args.adapter)
    run.check_binary(binary)
    topology_binary = args.topology_binary or os.path.join(
        "out", "diagnostics", "direct-diagonal", "exact-topology",
        "bin", "exact_topology")
    if not (os.path.isfile(topology_binary)
            and os.access(topology_binary, os.X_OK)):
        fail("topology binary missing: %s" % topology_binary)
    if sha_file(topology_binary) != FROZEN_TOPOLOGY_SHA256:
        fail("topology binary mismatch")

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
    from experiments.hobby_fitting import curve_clearance
    checker = functools.partial(
        curve_clearance.compare_commands, binary=topology_binary)

    base_dir = os.path.dirname(os.path.abspath(args.baseline.rstrip("/")))
    captures_path = args.captures or os.path.join(base_dir, "captures.json")
    joins_dir = args.joins_dir or os.path.join(base_dir, "joins-evaluation")
    with open(captures_path, "rb") as handle:
        if hashlib.sha256(handle.read()).hexdigest() != FROZEN_CAPTURE_SHA256:
            fail("frozen captures mismatch")
    frozen_cases = review.load_cases(captures_path)
    frozen_items = list(run.iter_records(frozen_cases))
    frozen_by_key = {(review.group_key(i), i["codepoint"]): i["record"]
                     for i in frozen_items}
    with open(os.path.join(joins_dir, "summary.json")) as handle:
        joins_summary = json.load(handle)
    if joins_summary.get("capture_sha256") != FROZEN_CAPTURE_SHA256:
        fail("joins-evaluation is not built from the frozen captures")
    joins_map = review.joins_lookup(joins_summary)
    baseline_summary = load_json(os.path.join(args.baseline, "summary.json"))
    assert_baseline_provenance(baseline_summary)

    if args.family is not None and args.family not in review.FONT_PATHS:
        fail("unknown family %s (want %s)"
             % (args.family, sorted(review.FONT_PATHS)))
    families = [args.family] if args.family else sorted(review.FONT_PATHS)
    sizes = [args.size] if args.size is not None else list(review.SIZES)
    weights = [args.weight] if args.weight is not None else list(review.WEIGHTS)

    out = args.out
    os.makedirs(os.path.join(out, "cells"), exist_ok=True)
    scratch = os.path.join(out, ".scratch")
    os.makedirs(scratch, exist_ok=True)

    candidate_core_sha = sha_file(os.path.join(REPO, MODEL_FILE))
    model_dependencies = model_provenance()
    prov = {"tool": TOOL_VERSION,
            "baseline": args.baseline,
            "baseline_tool": BASELINE_TOOL,
            "baseline_model_source_sha256": FROZEN_MODEL_SHA256,
            "model_source": MODEL_FILE,
            "candidate_core_sha256": candidate_core_sha,
            "canonical_curve_clearance": True,
            "model_dependencies": model_dependencies,
            "topology_binary_sha256": sha_file(topology_binary),
            "adapter": binary,
            "adapter_sha256": sha_file(binary)}
    summary_cells = []
    for family in families:
        for size in sizes:
            for weight in weights:
                axes = review.frozen_axes_for(frozen_cases, family, weight)
                if args.resume and saved_config_complete(
                        out, family, size, weight, axes, candidate_core_sha,
                        model_dependencies):
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
                summary_cells.append(process_config(
                    binary, checker, core, family, size, weight, axes,
                    frozen_by_key, joins_map, joins_dir,
                    args.baseline, scratch, out, prov))
    totals = {"newly_covered": 0, "lost": 0, "pixels_changed": 0,
              "applied": 0, "abstained": 0}
    for config in summary_cells:
        for entry in config["files"]:
            for key in totals:
                totals[key] += entry["counts"].get(key, 0)
    summary = {
        "tool": TOOL_VERSION,
        "baseline": args.baseline,
        "baseline_tool": BASELINE_TOOL,
        "baseline_capture_sha256": FROZEN_CAPTURE_SHA256,
        "baseline_model_source_sha256": FROZEN_MODEL_SHA256,
        "baseline_topology_sha256": FROZEN_TOPOLOGY_SHA256,
        "captures": captures_path,
        "adapter": binary,
        "adapter_sha256": prov["adapter_sha256"],
        "topology_binary": topology_binary,
        "topology_binary_sha256": prov["topology_binary_sha256"],
        "cgal_version": "6.1.1",
        "model_source": MODEL_FILE,
        "candidate_core_sha256": candidate_core_sha,
        "model_dependencies": model_dependencies,
        "frozen_donors": "".join(sorted(chr(c) for c in DONOR_CODES)),
        "ascii_repertoire": "U+0020..U+007E",
        "text_lines": review.TEXT_LINES,
        "resumed": args.resume,
        "resume_note": "reused coverage cells passed identity, repertoire, "
                       "ready-layout, reference-hash, baseline-model and "
                       "candidate-core checks before recomposition" if args.resume else None,
        "layout_note": "paired arms share one finalized native layout from "
                       "the frozen packet; no CSS font text is rendered",
        "note": "Three-arm border-interval coverage: upstream, frozen "
                "width-only and candidate share one native frame. Frozen "
                "donor checks validate the baseline against joins-evaluation; "
                "candidate differences are intentional. A glyphwide applied "
                "flag records delivered pair intervention, not full-stroke "
                "coverage; rejected attempts stay in skipped/attempt fields.",
        "totals": totals,
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


if __name__ == "__main__":
    main()
