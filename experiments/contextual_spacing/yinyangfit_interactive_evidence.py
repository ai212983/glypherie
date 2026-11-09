#!/usr/bin/env python3
"""Frozen-setting evidence for the nearest-distance interactive experiment.

Evaluates representative settings (defaults plus each control's endpoints) on
delivered Mono and Gray cells at two sizes and two contrasting families.
Writes exact per-candidate costs/choices plus cold/warm ten-pair Python search
timing and traced-allocation peak. Not browser lookup latency; not process
RSS. No training, no optical verdict: unassessed findings stay pending.
"""
import argparse
import json
import platform
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yinyangfit_interactive as yy

PAIRS = ["nn", "HH", "ll", "oo", "OO", "ee", "AV", "vv", "To", "ya"]
WORDS = ["lynx", "Hamburg", "To", "AV"]

FROZEN_SETTINGS = {
    "default": yy.DEFAULT_CONTROLS,
    "cohesion_min": yy.YYControls(cohesion=0.0),
    "cohesion_max": yy.YYControls(cohesion=2.0),
    "scale_min": yy.YYControls(feature_scale=0.5),
    "scale_max": yy.YYControls(feature_scale=4.0),
    "falloff_min": yy.YYControls(proximity_falloff=1.0),
    "falloff_max": yy.YYControls(proximity_falloff=3.0),
}


def load_dataset(spec):
    if spec["profile"] == "mono":
        dataset = yy.load_mono_capture(spec["path"])
    else:
        dataset = yy.load_gray_capture(spec["path"])
    dataset["label"] = spec["label"]
    return dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--mono16", required=True, type=Path)
    parser.add_argument("--mono16b", required=True, type=Path)
    parser.add_argument("--gray16", required=True, type=Path)
    parser.add_argument("--gray16b", required=True, type=Path)
    parser.add_argument("--mono24", required=True, type=Path)
    parser.add_argument("--mono24b", required=True, type=Path)
    parser.add_argument("--gray24", required=True, type=Path)
    parser.add_argument("--gray24b", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must be new")
    specs = [
        {"label": "Roboto-16-mono", "profile": "mono", "path": str(args.mono16)},
        {"label": "Literata-16-mono", "profile": "mono", "path": str(args.mono16b)},
        {"label": "Roboto-16-gray", "profile": "gray", "path": str(args.gray16)},
        {"label": "Literata-16-gray", "profile": "gray", "path": str(args.gray16b)},
        {"label": "Roboto-24-mono", "profile": "mono", "path": str(args.mono24)},
        {"label": "Literata-24-mono", "profile": "mono", "path": str(args.mono24b)},
        {"label": "Roboto-24-gray", "profile": "gray", "path": str(args.gray24)},
        {"label": "Literata-24-gray", "profile": "gray", "path": str(args.gray24b)},
    ]
    tracemalloc.start()
    report = {"model": yy.MODEL_IDENTITY,
              "implementation": yy.IMPLEMENTATION_SHA256,
              "pairs": PAIRS, "words": WORDS,
              "settings": {name: {"cohesion": c.cohesion,
                                  "feature_scale": c.feature_scale,
                                  "proximity_falloff": c.proximity_falloff,
                                  "identity": yy.settings_identity(c)}
                           for name, c in FROZEN_SETTINGS.items()},
              "environment": {"python": platform.python_version(),
                              "machine": platform.machine(),
                              "processor": platform.processor()},
              "datasets": []}
    for spec in specs:
        dataset = load_dataset(spec)
        scorer = PairScorerTimed(dataset)
        entry = {"label": spec["label"], "profile": dataset["profile"],
                 "size_px": dataset["size_px"], "source_path": dataset["source_path"],
                 "settings": {}}
        for name, controls in FROZEN_SETTINGS.items():
            entry["settings"][name] = scorer.run_setting(name, controls)
        entry["timing"] = scorer.timing
        report["datasets"].append(entry)
    # Traced Python allocations only: not process RSS, and excluding the
    # captures and any browser/WASM memory.
    report["resources"] = {"python_peak_bytes": tracemalloc.get_traced_memory()[1],
                           "note": "tracemalloc peak of traced Python allocations; "
                                   "not process RSS; excludes capture and browser"}
    tracemalloc.stop()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "evidence.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = ["# YinYangFit interactive evidence", "",
             f"Implementation `{yy.IMPLEMENTATION_SHA256[:12]}`.", "",
             "| dataset | setting | moved pairs | boundary hits | invalid candidates |",
             "| --- | --- | --- | --- | --- |"]
    for entry in report["datasets"]:
        for name, result in entry["settings"].items():
            pairs = result["pairs"]
            moved = sum(1 for p in pairs if p["chosen"] != p["metric"])
            boundary = sum(1 for p in pairs if p["boundary_hit"])
            invalid = sum(1 for p in pairs for c in p["candidates"] if not c["valid"])
            lines.append(f"| {entry['label']} | {name} | {moved}/{len(pairs)} "
                         f"| {boundary} | {invalid} |")
    warm = [e["timing"] for e in report["datasets"]]
    # Cold: first ten-pair search with a cold glyph cache; warm: a second
    # ten-pair search with the cache warm. Python scorer timing only, not
    # browser precomputed-lookup latency.
    lines += ["",
              "## Timing (this machine, exact workload in evidence.json)",
              "",
              "Ten-pair Python searches per dataset: cold prep runs the default",
              "setting first (cold glyph cache); warm update re-scores the ten",
              "pairs at one changed setting (warm cache). Not browser latency.",
              "",
              "| dataset | cold prep (s) | warm update (s) |",
              "| --- | --- | --- |"]
    for entry in report["datasets"]:
        timing = entry["timing"]
        lines.append(f"| {entry['label']} | {timing['cold_seconds']:.3f} "
                     f"| {timing['warm_seconds']:.3f} |")
    (args.output / "evidence.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"status": "complete",
                      "datasets": len(report["datasets"]),
                      "settings": len(FROZEN_SETTINGS)}))


class PairScorerTimed:
    def __init__(self, dataset):
        self.scorer = yy.PairScorer(dataset)
        self.dataset = dataset
        self.timing = {}

    def run_setting(self, name, controls):
        start = time.perf_counter()
        pairs = []
        for text in PAIRS:
            left, right = ord(text[0]), ord(text[1])
            evaluation = self.scorer.evaluate_pair(left, right, controls)
            pairs.append({"pair": text, "metric": evaluation["metric"],
                          "chosen": evaluation["chosen"],
                          "delta_vs_metric": evaluation["chosen"] - evaluation["metric"],
                          "boundary_hit": evaluation["boundary_hit"],
                          "fallback": evaluation["fallback"],
                          "fallback_reason": evaluation["fallback_reason"],
                          "minimizing_steps": evaluation["minimizing_steps"],
                          "candidates": evaluation["candidates"]})
        elapsed = time.perf_counter() - start
        if name == "default":
            self.timing["cold_seconds"] = elapsed
            # Warm update: same scorer, cached glyph analysis, one control changed.
            other = yy.YYControls(cohesion=1.2)
            start = time.perf_counter()
            for text in PAIRS:
                self.scorer.evaluate_pair(ord(text[0]), ord(text[1]), other)
            self.timing["warm_seconds"] = time.perf_counter() - start
        words = []
        for word in WORDS:
            try:
                layout = yy.layout_text(self.dataset, self.scorer, word, controls)
            except ValueError as error:
                words.append({"word": word, "error": str(error)})
                continue
            words.append({"word": word, "origins": layout["origins"],
                          "gaps": [{"pair": chr(g["pair"][0]) + chr(g["pair"][1]),
                                    "metric": g["metric"], "chosen": g["chosen"]}
                                   for g in layout["gaps"]]})
        return {"controls_identity": yy.settings_identity(controls),
                "seconds": elapsed, "pairs": pairs, "words": words}


if __name__ == "__main__":
    main()
