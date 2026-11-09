#!/usr/bin/env python3
"""Resolve an isolated capture; emit reproducible results and native timings."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import signal
import sys
import time
import tracemalloc

from solver import COUNTERSPACE_MODELS, HU_MODELS, SPACING_MODELS, Controls, Solver


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--text", help="preview pairs/layout; omitted means full N-squared repertoire")
    parser.add_argument("--source-kerning", type=float, default=1)
    parser.add_argument("--optical", type=float, default=1)
    parser.add_argument("--spacing-model", choices=SPACING_MODELS, default="hu_hersch")
    parser.add_argument("--target-separation-em", type=float, default=0.15,
                        help="fixed-target balanced diagnostic only, fraction of em (default: 0.15)")
    parser.add_argument("--letter-spacing", type=float, default=0)
    parser.add_argument("--word-spacing", type=float, default=0)
    parser.add_argument("--preserve-tabular-spacing", action=argparse.BooleanOptionalAction, default=True,
                        help="retain metric placement for source-tabular digit pairs (default: enabled)")
    parser.add_argument("--width", type=float)
    parser.add_argument("--subdivisions", type=int, choices=(100, 200), default=100)
    parser.add_argument("--filtered-samples-per-px", type=int, default=64, help="midpoint samples per pixel (default: 64)")
    parser.add_argument("--geometry", choices=("bitmap", "fitted_outline"), default="bitmap")
    parser.add_argument("--work-limit", type=int, default=10000)
    parser.add_argument("--benchmark", action="store_true", help="repeat with warm geometry cache")
    args = parser.parse_args()
    if args.output.resolve() == args.capture.resolve():
        parser.error("output must not overwrite capture")
    capture = json.loads(args.capture.read_text())
    controls = Controls(args.source_kerning, args.optical, args.letter_spacing, args.word_spacing,
                        preserve_tabular_spacing=args.preserve_tabular_spacing,
                        spacing_model=args.spacing_model, target_separation_em=args.target_separation_em)
    solver = Solver(capture, args.subdivisions, args.geometry, filtered_samples_per_px=args.filtered_samples_per_px)
    interrupted = False

    def cancel(_signal, _frame):
        nonlocal interrupted
        interrupted = True

    signal.signal(signal.SIGINT, cancel)
    tracemalloc.start()
    start = time.perf_counter()
    result = solver.generate(controls, args.text, args.work_limit, lambda: interrupted)
    cold_seconds = time.perf_counter() - start
    peak = tracemalloc.get_traced_memory()[1]
    resources = dict(cold_seconds=cold_seconds, python_peak_bytes=peak,
                     target="native Python diagnostic; excludes capture and browser/WASM")
    if args.benchmark and result["status"] == "complete":
        start = time.perf_counter()
        warm = solver.generate(controls, args.text, args.work_limit, lambda: interrupted)
        resources["warm_seconds"] = time.perf_counter() - start
        if warm != result:
            raise ValueError("warm/cold result mismatch")
        resources["warm_identity"] = True
    tracemalloc.stop()
    if args.text is not None and result["status"] == "complete":
        result["text"] = args.text
        result["layout"] = solver.layout(args.text, result, args.width)
    result["resources"] = resources
    result["capture_path"] = str(args.capture.resolve())
    result["scope"] = {
        "healing": "not enabled: transformation and finite-context research gate remains open",
        "optical_acceptance": "pending browser assessment; mechanical results do not establish quality",
        "reference_parity": ("pinned upstream CounterSpace functions; project raster and integer placement adaptations; see adapter verification"
                             if controls.spacing_model in COUNTERSPACE_MODELS else
                             "analytic geometry, independent filter oracle and sampling convergence; no original Hu implementation parity"
                             if controls.spacing_model in (*HU_MODELS, "filtered_walls") else
                             "bounded native FontForge source-operation parity; see required native reference tests and captures"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    temporary.replace(args.output)
    print(json.dumps(dict(status=result["status"], completed_pairs=result["completed_pairs"],
                          declared_pairs=result["declared_pairs"], controls=asdict(controls))))
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, OSError, RuntimeError) as error:
        print(f"contextual spacing: {error}", file=sys.stderr)
        sys.exit(1)
