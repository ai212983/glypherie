#!/usr/bin/env python3
"""Bit-checked native output against the frozen preferred packet.

Repeatable 72-cell verification: frozen coverage cells plus ASCII captures
drive a thin Rust example over stdin/stdout JSON lines. Every comparison is
exact except anchor vectors, which use relative tolerance 1e-12.
"""
import argparse
import hashlib
import json
import pathlib
import struct
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "out/diagnostics/direct-diagonal/native-port-verification"
CELLS = ROOT / "out/diagnostics/direct-diagonal/coverage-review/cells"
CAPTURES = ROOT / "out/diagnostics/direct-diagonal/text-review/ascii-captures"
SUMMARY = ROOT / "out/diagnostics/direct-diagonal/coverage-review/summary.json"
DONORS = set(map(ord, "itflInhkyxzvAVW"))
COORDS = ("x", "y", "x1", "y1", "x2", "y2")
REL_TOL = 1e-12
Mismatch = list


def sha256_file(path):
    """Hex digest of a file; stdlib only."""
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def command_bits(commands):
    """Op plus exact f32 bit patterns per coordinate (no float fallback)."""
    return [
        (
            cmd["op"],
            tuple(
                (key, cmd.get(key + "_bits", f32_bits(cmd[key])))
                for key in COORDS
                if key in cmd
            ),
        )
        for cmd in commands
    ]


def f32_bits(value):
    """Bit pattern of a float as an f32, matching the capture convention."""
    return struct.unpack(">I", struct.pack(">f", value))[0]


def close_enough(actual, want):
    """Relative-tolerance equality for anchor scalars and vectors."""
    if isinstance(actual, list):
        return len(actual) == len(want) and all(
            abs(a - b) <= REL_TOL * max(1, abs(b)) for a, b in zip(actual, want)
        )
    if isinstance(actual, (int, float)) and isinstance(want, (int, float)):
        return abs(actual - want) <= REL_TOL * max(1, abs(want))
    return actual == want


def parse_args():
    """CLI: binary required, focus trims to two cells, out sets output."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--focus", action="store_true")
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    return parser.parse_args()


def load_cells():
    """All 72 frozen cells, Roboto 16 400 first for a fast signal."""
    cells = [json.loads(path.read_text()) | {"file": path.name}
             for path in CELLS.glob("*.json")]
    assert len(cells) == 72, len(cells)
    cells.sort(key=lambda cell: (
        0 if (cell["family"], cell["size"], cell["weight"])
        == ("Roboto", 16, 400) else 1,
        cell["family"], cell["size"], cell["weight"], cell["hint_mode"]))
    return cells


def load_records(cell):
    """Capture records for one cell; source commands are required."""
    stem = "%s-%d-%d" % (cell["family"], cell["weight"], cell["size"])
    raw = json.loads((CAPTURES / (stem + ".json")).read_text())
    if isinstance(raw, dict):
        raw = [raw]
    assert len(raw) == 1
    records = sorted(raw[0]["modes"][cell["hint_mode"]]["records"],
                     key=lambda record: record["codepoint"])
    assert all("source_commands" in record for record in records)
    return [dict(record) for record in records]


def select_donors(records):
    """The 15 sorted donor records; codes must match the frozen set."""
    donors = [record for record in records
              if record["codepoint"] in DONORS]
    assert len(records) == 95, len(records)
    assert len(donors) == 15, len(donors)
    assert {record["codepoint"] for record in donors} == DONORS
    return donors


def check_reference(result, cell, totals):
    """Anchor scalars and vectors within tolerance; ids exact."""
    for key in ("n_anchors", "records", "rel_min", "rel_max"):
        actual, want = result["reference"].get(key), cell["reference"].get(key)
        if not close_enough(actual, want):
            totals["reference_mismatches"].append([cell["file"], key, actual, want])
    anchors, expected = result["reference"]["anchors"], cell["reference"]["anchors"]
    if len(anchors) != len(expected):
        return
    for index, (actual, want) in enumerate(zip(anchors, expected)):
        for key in ("source_width", "fitted_width", "rel", "length",
                    "tangent", "source_ids"):
            if not close_enough(actual[key], want[key]):
                totals["reference_mismatches"].append(
                    [cell["file"], index, key, actual[key], want[key]])


def check_glyph(glyph, originals, cell_file, totals):
    """Exact command bits, decision, pair counts and raw raster."""
    want = originals[glyph["codepoint"]]["candidate"]
    key = [cell_file, glyph["codepoint"]]
    if command_bits(glyph["commands"]) != command_bits(want["candidate_commands"]):
        totals["command_mismatches"].append(key)
    if (glyph["applied"], glyph["reason"]) != (want["applied"], want["reason"]):
        totals["decision_mismatches"].append(
            key + [glyph["reason"], want["reason"]])
    actual_pairs = len(glyph["diagnostics"].get("pairs", []))
    if actual_pairs != len(want.get("pairs", [])):
        totals["pair_mismatches"].append(key + [actual_pairs, len(want.get("pairs", []))])
    raster = glyph["raster"]
    frame = {name: raster[name] for name in ("left", "top", "width", "height")}
    if (frame != want["frame"] or raster["pixels"] != want["pixels"]
            or raster["coverage"] != want["coverage"]):
        totals["raster_mismatches"].append(key)
    totals["applied"] += glyph["applied"]
    totals["records"] += 1


def run_cell(process, cell, cells_dir, totals):
    """Validate, launch one request, and check the native reply."""
    records = load_records(cell)
    donors = select_donors(records)
    request = {"size": cell["size"], "donors": donors, "records": records}
    start = time.monotonic()
    process.stdin.write(json.dumps(request) + "\n")
    process.stdin.flush()
    line = process.stdout.readline()
    if not line:
        raise RuntimeError("native process exited %s" % process.poll())
    result = json.loads(line)
    elapsed = time.monotonic() - start
    (cells_dir / cell["file"]).write_text(json.dumps(result))
    check_reference(result, cell, totals)
    originals = {glyph["codepoint"]: glyph for glyph in cell["glyphs"]}
    for glyph in result["results"]:
        check_glyph(glyph, originals, cell["file"], totals)
    totals["cells"] += 1
    totals["timings"].append([cell["file"], elapsed])
    return elapsed


def fresh_totals():
    """Mismatch collectors plus the reported anchor tolerance."""
    return {
        "reference_relative_tolerance": REL_TOL,
        "cells": 0,
        "records": 0,
        "applied": 0,
        "command_mismatches": [],
        "decision_mismatches": [],
        "raster_mismatches": [],
        "reference_mismatches": [],
        "pair_mismatches": [],
        "timings": [],
    }


def main():
    """Drive every cell through one child; any mismatch exits nonzero."""
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "cells").mkdir(exist_ok=True)
    cells = load_cells()
    if args.focus:
        cells = cells[:2]
    provenance = {
        "binary_sha256": sha256_file(args.binary),
        "harness_sha256": sha256_file(__file__),
        "summary_sha256": sha256_file(SUMMARY),
        "cells": [{"file": cell["file"], "capture": cell["capture"]}
                  for cell in cells],
    }
    totals = fresh_totals()
    totals["provenance"] = provenance
    process = subprocess.Popen([args.binary], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, text=True)
    try:
        for cell in cells:
            elapsed = run_cell(process, cell, args.out / "cells", totals)
            (args.out / "native-audit.json").write_text(json.dumps(totals, indent=1))
            print(cell["file"], round(elapsed, 2),
                  {key: len(value) for key, value in totals.items()
                   if key.endswith("mismatches")}, flush=True)
        process.stdin.close()
        assert process.wait() == 0
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()
    if any(totals[key] for key in totals if key.endswith("mismatches")):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
