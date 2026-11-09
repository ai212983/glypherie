#!/usr/bin/env python3
"""Independent Python reference for browser-compute parity.

Scores a broad pair corpus at legacy shared points, new slider values,
off-grid typed values and numeric-entry boundary guardrails through the
full-window candidate core (via the versioned adapter), and writes exact
interactions, attention sums, validity and choices. The node compute test
compares the in-page port against its output; the port must reproduce it,
not mirror itself. Regenerations stamp the B2 model identity; the checked-in
v1 corpus in yinyang-live-controls stays the frozen v1 reference.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import yinyangfit_interactive_b2 as yy
import yinyangfit_interactive_v3 as v3
import yinyangfit_interactive_v3_ranges as vr

PAIRS = ["nn", "HH", "ll", "To", "AV", "ef", "ff", "og", "ya", "ri",
         "ac", "Gu"]
DATASETS = [("roboto-16", "mono"), ("roboto-16", "gray"),
            ("literata-16", "mono"), ("rouge-script-20", "gray")]
SETTINGS = [
    # Legacy shared points (fast-path columns).
    (1.0, 1.0), (2.0, 2.0), (3.0, 3.0), (4.0, 4.0), (1.5, 2.5),
    # New slider values.
    (0.5, 2.0), (0.75, 2.0), (2.25, 2.0), (5.75, 2.0), (6.0, 2.0),
    (2.0, 0.5), (2.0, 4.5), (2.0, 8.0), (2.0, 10.0),
    # Off-grid typed values.
    (2.125, 4.2), (1.123, 2.125),
    # Numeric-entry boundary guardrails.
    (0.25, 2.0), (12.0, 2.0), (2.0, 16.0),
]
COHESIONS = [0.0, 1.1, 1.123, 2.0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--captures", type=Path,
                        default=(HERE.parents[1] / "out/diagnostics"
                                 / "contextual-spacing"
                                 / "yinyangfit-interactive-v3/captures"))
    args = parser.parse_args()
    corpus = {"model": yy.MODEL_IDENTITY,
              "implementation": yy.IMPLEMENTATION_SHA256,
              "settings_version": vr.RANGES_VERSION,
              "cohesions": COHESIONS, "entries": [], "skipped": []}
    for case_id, profile in DATASETS:
        dataset = v3.load_case_dataset(case_id, profile, args.captures)
        scorer = yy.PairScorer(dataset)
        repertoire = set(dataset["cells"])
        cells = {}
        for pair in PAIRS:
            left, right = ord(pair[0]), ord(pair[1])
            if left not in repertoire or right not in repertoire:
                corpus["skipped"].append(f"{case_id}-{profile}:{pair}")
                continue
            for codepoint in (left, right):
                if codepoint not in cells:
                    cell = dataset["cells"][codepoint]
                    cells[codepoint] = {
                        "w": cell["width"], "h": cell["height"],
                        "left": cell["left"], "top": cell["top"],
                        "cover": list(cell["cover"])}
            metric = yy.metric_step(dataset, left, right)
            for scale, falloff in SETTINGS:
                geos = [vr.score_geometry(scorer, left, right,
                                          metric + delta, scale, falloff)
                        for delta in yy.CANDIDATE_DELTAS]
                choices = {}
                for cohesion in COHESIONS:
                    evaluation = vr.evaluate_pair(
                        scorer, left, right, cohesion, scale, falloff)
                    choices[str(cohesion)] = {
                        "chosen": evaluation["chosen"],
                        "fallback": evaluation["fallback"],
                        "minimizing": evaluation["minimizing_steps"]}
                corpus["entries"].append({
                    "dataset": f"{case_id}-{profile}",
                    "pair": pair, "metric": metric,
                    "scale": scale, "falloff": falloff,
                    "candidates": [{
                        "step": g["step"], "valid": g["valid"],
                        "reason": g.get("reason"),
                        "interaction": g.get("interaction"),
                        "attention": g.get("attention_sum"),
                    } for g in geos],
                    "choices": choices})
        corpus.setdefault("cells", {})[f"{case_id}-{profile}"] = {
            str(codepoint): cell for codepoint, cell in cells.items()}
        print(f"{case_id}-{profile}: ok", flush=True)
    args.output.write_text(json.dumps(corpus) + "\n")
    print(f"wrote {len(corpus['entries'])} entries, "
          f"{len(corpus['skipped'])} skipped: {corpus['skipped']}")


if __name__ == "__main__":
    main()
