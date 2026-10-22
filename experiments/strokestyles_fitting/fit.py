#!/usr/bin/env python3
"""Opt-in StrokeStyles fitting driver over independent captures.

Default (flag absent) passes every record through byte-identical with no
extractor import and no analysis read. With --enable-strokestyles, each
case couples imported straight diagonals to the font-wide upright
standard from the same font, axes and size; unsupported cases keep the
upstream outline with an explicit reason. Outputs stay under
out/diagnostics/strokestyles-fitting/fitting; existing out/web and
out/specimens are never touched.
"""

import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

DEFAULT_OUT = os.path.join("out", "diagnostics", "strokestyles-fitting",
                           "fitting")

METRIC_KEYS = ("advance_26_6", "hinted_advance_width", "hinted_lsb",
               "hinted_has_overlaps", "side_bearing_deltas_26_6",
               "left", "top", "width", "height")


def _size_of(entry):
    if "size_px" in entry:
        return entry["size_px"]
    return entry.get("size")


def _case_key(font_sha, axes, size):
    return (font_sha, json.dumps(axes, sort_keys=True), float(size))


def _native_axes(record, mode):
    """Owned axes per record; uncertainty reserves, never assumes auto.

    Explicit selective measurements are authoritative. Ordinary auto is
    proven by its engine. A conservative fallback (interpreter engine,
    scan metadata, missing capture) keeps every axis native-owned.
    """
    selective = record.get("selective_fitting")
    if isinstance(selective, dict) and "native_axes" in selective:
        axes = selective["native_axes"]
        return [bool(axes[0]), bool(axes[1])]
    if mode.startswith("native_"):
        return [True, True]
    if record.get("selected_engine") == "auto":
        return [False, False]
    return [True, True]


def _passthrough(record):
    return {"applied": False, "reason": "strokestyles-disabled",
            "candidate_commands": record["fitted_commands"],
            "metrics": {k: record.get(k) for k in METRIC_KEYS}}


def _load_analyses(analysis_dir):
    """Read cached analyses; extraction stays independent of pixel size."""
    analyses = []
    if not analysis_dir:
        return analyses
    for name in sorted(os.listdir(analysis_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(analysis_dir, name)) as handle:
            record = json.load(handle)
        analyses.append({"file": name, "record": record})
    return analyses


def _match_glyphs(analyses, font_sha, axes):
    """Validate schema and provenance; report unsupported until real."""
    from experiments.strokestyles_fitting import fitting as fit_mod
    glyphs, upem, notes = {}, None, []
    for item in analyses:
        validated = fit_mod.validate_analysis(item["record"])
        if not validated["supported"]:
            notes.append({"file": item["file"],
                          "reason": validated.get("reason")})
            continue
        provenance = validated["provenance"]
        ok, reason = fit_mod.match_provenance(provenance, font_sha, axes)
        if not ok:
            notes.append({"file": item["file"], "reason": reason})
            continue
        upem = validated["upem"]
        for char, glyph in validated["glyphs"].items():
            glyphs[char] = glyph
    return glyphs, upem, notes


def run_enabled(captures, mode, analyses, chars, sizes):
    from experiments.strokestyles_fitting import fitting as fit_mod
    cases = []
    for entry in captures:
        size = _size_of(entry)
        if sizes and float(size) not in sizes:
            continue
        block = entry["modes"][mode]
        font_sha = block.get("source_sha256")
        axes = block.get("axes", {})
        glyphs, upem, notes = _match_glyphs(analyses, font_sha, axes)
        group = []
        for record in block["records"]:
            char = chr(record["codepoint"])
            if chars and char not in chars:
                continue
            source = record.get("source_commands")
            if not isinstance(source, list):
                cases.append({"char": char, "size": size,
                              "family": entry.get("family"),
                              "axes": entry.get("axes"),
                              "applied": False,
                              "reason": "no-source-outline",
                              "candidate_commands":
                                  record.get("fitted_commands")})
                continue
            if char not in glyphs:
                cases.append({"char": char, "size": size,
                              "family": entry.get("family"),
                              "axes": entry.get("axes"),
                              "applied": False,
                              "reason": "unsupported-analysis",
                              "detail": "no matching upstream analysis",
                              "candidate_commands":
                                  record.get("fitted_commands"),
                              "unmatched": notes})
                continue
            group.append({"char": char, "record": record,
                          "source_cmds": source,
                          "fitted_cmds": record["fitted_commands"],
                          "analysis": glyphs[char], "upem": upem})
        reference = fit_mod.build_reference(
            [{"char": g["char"], "source_cmds": g["source_cmds"],
              "fitted_cmds": g["fitted_cmds"], "size_px": float(size),
              "analysis": g["analysis"], "upem": g["upem"]} for g in group])
        for item in group:
            char = item["char"]
            result = fit_mod.run_glyph(
                char, item["source_cmds"], item["fitted_cmds"],
                float(size), item["analysis"], item["upem"], reference,
                _native_axes(item["record"], mode))
            result["size"] = size
            result["mode"] = mode
            result["family"] = entry.get("family")
            result["axes"] = entry.get("axes")
            result["metrics"] = {k: item["record"].get(k)
                                 for k in METRIC_KEYS}
            if not result["applied"]:
                result["candidate_commands"] = item["fitted_cmds"]
            cases.append(result)
    return cases


def run_disabled(captures, mode, chars, sizes):
    cases = []
    for entry in captures:
        size = _size_of(entry)
        if sizes and float(size) not in sizes:
            continue
        for record in entry["modes"][mode]["records"]:
            char = chr(record["codepoint"])
            if chars and char not in chars:
                continue
            result = _passthrough(record)
            result.update({"char": char, "size": size, "mode": mode,
                           "family": entry.get("family"),
                           "axes": entry.get("axes")})
            cases.append(result)
    return cases


def run_eligibility(captures, mode, chars, sizes):
    from experiments.strokestyles_fitting import fitting as fit_mod
    cases = []
    for entry in captures:
        size = _size_of(entry)
        if sizes and float(size) not in sizes:
            continue
        for record in entry["modes"][mode]["records"]:
            char = chr(record["codepoint"])
            if chars and char not in chars:
                continue
            source = record.get("source_commands")
            if not isinstance(source, list):
                cases.append({"char": char, "size": size,
                              "family": entry.get("family"),
                              "axes": entry.get("axes"),
                              "eligible": False,
                              "reason": "no-source-outline"})
                continue
            result = fit_mod.describe_glyph(char, source,
                                            record["fitted_commands"])
            result["size"] = size
            result["mode"] = mode
            result["family"] = entry.get("family")
            result["axes"] = entry.get("axes")
            result["native_axes"] = _native_axes(record, mode)
            cases.append(result)
    return cases


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Opt-in StrokeStyles fitting consumer")
    parser.add_argument("--captures", required=True)
    parser.add_argument("--mode", default="selective_default")
    parser.add_argument("--analysis-dir", default=None)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--enable-strokestyles", action="store_true",
                        default=False)
    parser.add_argument("--eligibility", action="store_true", default=False)
    parser.add_argument("--chars", default=None)
    parser.add_argument("--sizes", default=None)
    args = parser.parse_args(argv)
    with open(args.captures) as handle:
        captures = json.load(handle)
    chars = set(args.chars) if args.chars else None
    sizes = ({float(s) for s in args.sizes.split(",")}
             if args.sizes else None)
    if args.eligibility:
        cases = run_eligibility(captures, args.mode, chars, sizes)
        dest = os.path.join(args.out, "eligibility", args.mode)
        os.makedirs(dest, exist_ok=True)
        for case in cases:
            tag = "%s_%s" % (case.get("family") or "unknown",
                             json.dumps(case.get("axes") or {},
                                        sort_keys=True).replace(" ", ""))
            name = "U+%04X_%s_%s.json" % (ord(case["char"]),
                                          str(case["size"]), tag)
            with open(os.path.join(dest, name), "w") as handle:
                json.dump(case, handle, indent=1, allow_nan=False)
        summary = {"mode": args.mode, "cases": len(cases),
                   "details": cases}
        with open(os.path.join(dest, "summary.json"), "w") as handle:
            json.dump(summary, handle, indent=1, allow_nan=False)
        print(json.dumps(summary, indent=1))
        return 0
    if args.enable_strokestyles:
        analyses = _load_analyses(args.analysis_dir)
        cases = run_enabled(captures, args.mode, analyses, chars, sizes)
    else:
        cases = run_disabled(captures, args.mode, chars, sizes)
    dest = os.path.join(args.out, args.mode)
    os.makedirs(dest, exist_ok=True)
    for case in cases:
        tag = "%s_%s" % (case.get("family") or "unknown",
                         json.dumps(case.get("axes") or {},
                                    sort_keys=True).replace(" ", ""))
        name = "U+%04X_%s_%s.json" % (ord(case["char"]), str(case["size"]),
                                      tag)
        with open(os.path.join(dest, name), "w") as handle:
            json.dump(case, handle, indent=1, allow_nan=False)
    applied = sum(1 for c in cases if c["applied"])
    reasons = {}
    for case in cases:
        if not case["applied"]:
            reasons[case["reason"]] = reasons.get(case["reason"], 0) + 1
    summary = {"mode": args.mode, "enabled": args.enable_strokestyles,
               "cases": len(cases), "applied": applied, "reasons": reasons,
               "files": sorted(os.listdir(dest))}
    with open(os.path.join(dest, "summary.json"), "w") as handle:
        json.dump(summary, handle, indent=1, allow_nan=False)
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
