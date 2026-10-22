"""Difference replay over fixed FreeType before/after scans.

Source: out/diagnostics/terminal-stub-correction-20261020/corpus.json
changed entries (raster_policy free_type_mono, mono_rasterizer 2.15.0;
before include_stubs True, after False; same frames) crossed with
out/diagnostics/source-feature-work-20261020/source-controls.json source
(unhinted) outlines matched by font/size/weight/codepoint. Parental oracles:
RobotoFlex k tip extension; SourceSans3 w200 R/6/9 junction failures
(docs/revisions/001/03-spacing-kerning.md terminal-tips).
Writes out/diagnostics/source-feature-work-20261020/terminal-report.json.
Invariant: before/after fitted commands must match index-for-index and share
the source op/contour/edge structure; mismatches yield no caps for the case.
Invariant: removal needs before=1/after=0 AND attribution to exactly one
dually-certified cap; bytes are otherwise preserved verbatim.
"""

import json
import os

from experiments.terminal_geometry.supporting_cap import (
    certified_caps, pixel_square, attribute_pixel,
)

ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
CORPUS = os.path.join(ROOT, "out/diagnostics/terminal-stub-correction-20261020",
                       "corpus.json")
CONTROLS = os.path.join(ROOT, "out/diagnostics/source-feature-work-20261020",
                         "source-controls.json")
DST = os.path.join(ROOT, "out/diagnostics/source-feature-work-20261020",
                   "terminal-report.json")

WITNESS_R69 = {"SourceSans3-12-200.0-R", "SourceSans3-12-200.0-6",
               "SourceSans3-13-200.0-6", "SourceSans3-12-200.0-9",
               "SourceSans3-13-200.0-9", "SourceSans3-14-200.0-9",
               "SourceSans3-15-200.0-9"}


def main():
    with open(CORPUS) as f:
        corpus = json.load(f)
    with open(CONTROLS) as f:
        controls = json.load(f)
    sources = {}
    for ent in controls:
        for r in ent["source"]["records"]:
            sources[(ent["font"], ent["size"], ent.get("weight"),
                     r["codepoint"])] = r["fitted_commands"]
    report = {"summary": {}, "cases": []}
    n_diff = n_removed = n_unhandled = n_gain = 0
    n_no_source = n_struct = n_cmd = n_adv = 0
    witness = {}

    for case in corpus["cases"]:
        font, size, weight = case["font"], case["size"], case.get("weight")
        for g in case["changed"]:
            b, a = g["before"], g["after"]
            key = "%s-%s-%s-%s" % (font, size, weight, g["glyph"])
            entry = {"case": key, "frame": [b["left"], b["top"],
                                            b["width"], b["height"]]}
            if (b["width"], b["height"], b["left"], b["top"]) != \
                    (a["width"], a["height"], a["left"], a["top"]):
                entry["same_frame"] = False
                report["cases"].append(entry)
                continue
            entry["same_frame"] = True
            entry["same_commands"] = b["fitted_commands"] == a["fitted_commands"]
            if not entry["same_commands"]:
                n_cmd += 1
            entry["same_advance"] = b["advance_26_6"] == a["advance_26_6"]
            if not entry["same_advance"]:
                n_adv += 1
            bp, ap = b["pixels"], a["pixels"]
            diff = [i for i in range(len(bp)) if bp[i] == 1 and ap[i] == 0]
            gain = [i for i in range(len(bp)) if bp[i] == 0 and ap[i] == 1]
            n_diff += len(diff)
            n_gain += len(gain)
            entry["gains"] = gain
            src = sources.get((font, size, weight, b["codepoint"]))
            if src is None or not entry["same_commands"]:
                if src is None:
                    n_no_source += 1
                entry["source_match"] = src is not None
                entry["removed"] = []
                entry["unhandled"] = diff
                n_unhandled += len(diff)
                report["cases"].append(entry)
                continue
            entry["source_match"] = True
            quantized, caps, info = certified_caps(src, b["fitted_commands"])
            entry["structure_match"] = info["structure_match"]
            if not info["structure_match"]:
                n_struct += 1
            entry["caps"] = caps
            removed, unhandled = [], []
            for idx in diff:
                i, j = idx % b["width"], idx // b["width"]
                sq = pixel_square(b["left"], b["top"], i, j)
                cap, reason = attribute_pixel(sq, caps, quantized)
                x_ol, y_ol = b["left"] + i, b["top"] + j
                if cap is None:
                    unhandled.append({"x": x_ol, "y": y_ol, "reason": reason})
                else:
                    removed.append({"x": x_ol, "y": y_ol, "cap": cap})
            n_removed += len(removed)
            n_unhandled += len(unhandled)
            entry["removed"] = removed
            entry["unhandled"] = unhandled
            out = list(bp)
            for r in removed:
                out[(r["y"] - b["top"]) * b["width"] + (r["x"] - b["left"])] = 0
            entry["output_matches_after"] = out == ap
            if key in WITNESS_R69:
                witness[key] = {"removed": len(removed),
                                "bytes_preserved": out == bp}
            if key == "RobotoFlex-16-400.0-k":
                witness[key] = {"removed": [(r["x"], r["y"]) for r in removed],
                                "expected": [[7, -1]]}
            report["cases"].append(entry)

    report["summary"] = {"changed_cases": len(report["cases"]),
                         "diff_pixels": n_diff, "removed": n_removed,
                         "unhandled": n_unhandled, "gains": n_gain,
                         "no_source": n_no_source,
                         "structure_mismatches": n_struct,
                         "command_mismatches": n_cmd,
                         "advance_mismatches": n_adv,
                         "witnesses": witness}
    with open(DST, "w") as f:
        json.dump(report, f, indent=1)
    print("cases=%d diff=%d removed=%d unhandled=%d gains=%d witnesses=%s"
          % (len(report["cases"]), n_diff, n_removed, n_unhandled, n_gain,
             json.dumps(witness)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
