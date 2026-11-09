#!/usr/bin/env python3
# cspell:words roboto
"""Whole-line width evidence across the frozen strength grid (diagnostic).

Recomputes per-line drawn widths from the shipped predictable-spacing tables
at every frozen strength and letter setting (-2, 0, +4 px), recording the
largest adjacent-strength line jump and per-case source/full widths. Run from
the repository root after building the site.
"""
import json
import math
import sys
from pathlib import Path

SITE = Path("out/diagnostics/contextual-spacing/predictable-spacing/site")
OUT = Path("out/diagnostics/contextual-spacing/predictable-spacing")
LETTERS = (-2, 0, 4)


def pixel_round(value):
    return math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)


def auto_step(record, strength):
    if strength == 0 or record["optical_adjustment"] is None:
        return record["metric"]
    blended = (record["metric_adjustment"] * (1 - strength)
               + record["optical_adjustment"] * strength)
    step = record["advance"] + pixel_round(blended)
    if record["minimum"] is not None:
        step = max(step, record["minimum"])
    return step


def table(label):
    src = (SITE / "data" / f"ps-{label}.js").read_text()
    return json.loads(src.split("] = ", 1)[1].rsplit(";", 1)[0])


def main():
    boot = json.loads((SITE / "boot.json").read_text())
    strengths = boot["cases"] and json.loads(
        (SITE / "data" / "ps-roboto-16-mono.js").read_text().split(
            "] = ", 1)[1].rsplit(";", 1)[0])["grid"]["strengths"]
    report = {"strengths": strengths, "letters": list(LETTERS),
              "max_adjacent_jump": 0, "max_adjacent_where": None}
    summary = {}
    for case in boot["cases"]:
        cid = case["id"]
        summary[cid] = {}
        for profile in ("mono", "gray"):
            ds = case["profiles"][profile]
            pairs = table(f"{cid}-{profile}")["pairs"]
            widths = {}
            for strength in strengths:
                for letter in LETTERS:
                    lines = []
                    for line in ds["lines"]:
                        gaps = ds["gaps"][len(lines)]
                        if profile == "mono":
                            origin = 0
                            for gap in gaps:
                                if gap["space"]:
                                    origin += gap["metric"]
                                else:
                                    step = auto_step(pairs[gap["pair"]],
                                                     strength)
                                    origin += step + (letter or 0)
                            lines.append(origin)
                        else:
                            pen = 0.0
                            for gap in gaps:
                                if gap["space"]:
                                    pen += gap["frac"]
                                else:
                                    record = pairs[gap["pair"]]
                                    pen += (gap["frac"]
                                            + (auto_step(record, strength)
                                               - record["metric"])
                                            + (letter or 0))
                            lines.append(pixel_round(pen))
                    widths[f"{strength}/{letter}"] = lines
            for li in range(len(ds["lines"])):
                seq = [widths[f"{s}/0"][li] for s in strengths]
                for before, after, at in zip(seq, seq[1:], strengths[1:]):
                    jump = abs(after - before)
                    if jump > report["max_adjacent_jump"]:
                        report["max_adjacent_jump"] = jump
                        report["max_adjacent_where"] = [cid, profile, li, at]
            summary[cid][profile] = {
                "lines_changed_at_full": sum(
                    1 for li in range(len(ds["lines"]))
                    if widths["1.0/0"][li] != widths["0.0/0"][li]),
                "of_lines": len(ds["lines"]),
                "width_at_source": widths["0.0/0"],
                "width_at_full": widths["1.0/0"]}
    (OUT / "line-width-grid.json").write_text(json.dumps(
        {"strengths": strengths, "letters": list(LETTERS),
         "max_adjacent_jump": report["max_adjacent_jump"],
         "max_adjacent_where": report["max_adjacent_where"]}) + "\n")
    (OUT / "line-width-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"max_adjacent_jump": report["max_adjacent_jump"],
                      "where": report["max_adjacent_where"]}))


if __name__ == "__main__":
    sys.exit(main())
