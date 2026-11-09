#!/usr/bin/env python3
"""Plan the design matrix or run a bounded native placement comparison."""

import argparse
from dataclasses import asdict
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys
import time

from solver import SPACING_MODELS, Controls, Solver

ROOT = Path(__file__).resolve().parents[2]
FAMILIES = (("Roboto", None), ("RobotoFlex", (8, 144)),
            ("SourceSans3", None), ("Literata", (7, 72)))
SAMPLE = "AV To Wa fi ffi lmi minimum oo nn é, À. 0123456789\nVAV AVA ToTo"
REFERENCE_CHARACTERS = "HnOocuv"
PIPELINES = {
    "automatic": dict(fitting="upstream_mono", rasterization="free_type_mono", diagonal_fitting=False),
    "selective": dict(fitting="font_hints_auto", rasterization="free_type_mono_terminals", diagonal_fitting=False),
    "overlay": dict(fitting="font_hints_auto", rasterization="free_type_mono_terminals", diagonal_fitting=True),
}


def requests(smoke):
    """Optical-size endpoints are independent of ppem, all other axes default.

    Font asset axis limits are owned by fonts/README.md; native validation checks
    the actual font. Gray is separately unsupported until its boundary is defined.
    """
    for family, endpoints in FAMILIES:
        for size, weight, pipeline in itertools.product(
                (16,) if smoke else (12, 14, 16, 18, 20, 24),
                (400,) if smoke else (300, 400, 700),
                ("overlay",) if smoke else PIPELINES):
            for optical_size in (None,) if smoke or endpoints is None else (None, *endpoints):
                axes = dict(wght=weight)
                if optical_size is not None:
                    axes["opsz"] = optical_size
                identity = f"{family}-{size}-{weight}-{pipeline}-opsz-{optical_size or 'default'}"
                yield identity, dict(font_path=str(ROOT / "fonts" / f"{family}.ttf"), size_px=size,
                                     axes=axes, characters="".join(sorted(set(SAMPLE + REFERENCE_CHARACTERS) - {"\n"})),
                                     pipeline=PIPELINES[pipeline])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--run-smoke", action="store_true", help="run four 16px/400 overlay cases; default plans only")
    parser.add_argument("--spacing-model", choices=SPACING_MODELS, default="hu_hersch",
                        help="optical comparison; hu_density_conserved uses fixed-alphabet source-origin calibration; hu_source_relative preserves each source pair")
    parser.add_argument("--target-separation-em", type=float, default=0.15)
    args = parser.parse_args()
    controls = Controls(spacing_model=args.spacing_model, target_separation_em=args.target_separation_em)
    args.output.mkdir(parents=True, exist_ok=True)
    plan = list(requests(args.run_smoke))
    manifest = dict(schema_version="contextual-spacing-matrix-v1", cases=[],
                    declared_cases=len(plan),
                    controls=asdict(controls),
                    status="complete" if args.run_smoke else "planned",
                    scope="isolated native Mono; full matrix execution awaits reference/resource gate",
                    gray_status="unsupported: coverage-boundary estimator not selected",
                    fixed_pitch_status="synthetic solver control only; real fixed-pitch font sweep pending")
    if args.run_smoke:
        subprocess.run(["cargo", "build", "--locked", "--manifest-path",
                        str(ROOT / "experiments/contextual_spacing/native/Cargo.toml")], check=True)
    binary = ROOT / "experiments/contextual_spacing/native/target/debug/contextual-spacing-capture"
    for identity, request in plan:
        record = dict(id=identity, request=request, status="planned")
        manifest["cases"].append(record)
        if args.run_smoke:
            # Persist the attempted case first. An unexpected solver/input error
            # must leave an incomplete attempt, never the last completed prefix.
            record["status"] = "running"
            manifest["status"] = "incomplete"
            (args.output / "matrix.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
            case = args.output / identity
            case.mkdir(exist_ok=True)
            (case / "request.json").write_text(json.dumps(request, indent=2) + "\n")
            started = time.perf_counter()
            command = subprocess.run([str(binary), str(case / "request.json"), str(case / "capture.json")],
                                     capture_output=True, text=True)
            record["capture_seconds"] = time.perf_counter() - started
            (case / "capture.stderr").write_text(command.stderr)
            if command.returncode:
                record.update(status="capture_failed", returncode=command.returncode)
                manifest["status"] = "incomplete"
            else:
                data = json.loads((case / "capture.json").read_text())
                record["source_sha256"] = data["source_sha256"]
                solver = Solver(data)
                started = time.perf_counter()
                full = solver.generate(controls)
                record["cold_seconds"] = time.perf_counter() - started
                started = time.perf_counter()
                warm = solver.generate(controls)
                record["warm_seconds"] = time.perf_counter() - started
                if full != warm:
                    raise ValueError(f"warm/cold mismatch: {identity}")
                if full["status"] != "complete":
                    (case / "full.json").write_text(json.dumps(full, indent=2, allow_nan=False) + "\n")
                    record.update(status=full["status"], reason=full["reason"],
                                  completed_pairs=full["completed_pairs"], declared_pairs=full["declared_pairs"])
                    (args.output / "matrix.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
                    continue
                preview = solver.generate(controls, text=SAMPLE)
                full_pairs = {(p["left"], p["right"]): p for p in full["pairs"]}
                for pair in preview["pairs"]:
                    if pair != full_pairs[pair["left"], pair["right"]]:
                        raise ValueError(f"preview/full mismatch: {identity}")
                # Independent captured endpoint tables, not a second solver formula.
                for strength, key in ((0, "metric_pairs_off"), (1, "metric_pairs_on")):
                    endpoint = {(p["left"], p["right"]): p["adjustment_px"] for p in data[key]}
                    for pair in solver.generate(Controls(strength, 0, spacing_model=args.spacing_model,
                                                        target_separation_em=args.target_separation_em))["pairs"]:
                        if pair["automatic_adjustment_px"] != endpoint.get((pair["left"], pair["right"]), 0):
                            raise ValueError(f"disabled endpoint mismatch: {identity}")
                preview["text"] = SAMPLE
                preview["layout"] = solver.layout(SAMPLE, preview)
                full_bytes = (json.dumps(full, sort_keys=True, allow_nan=False) + "\n").encode()
                (case / "full.json").write_bytes(full_bytes)
                (case / "preview.json").write_text(json.dumps(preview, indent=2, allow_nan=False) + "\n")
                record.update(status=full["status"], declared_pairs=full["declared_pairs"],
                              completed_pairs=full["completed_pairs"], result_sha256=hashlib.sha256(full_bytes).hexdigest(),
                              warm_identity=True, preview_full_identity=True, metric_endpoints=True,
                              calibration=full.get("calibration"))
                if full["status"] != "complete":
                    manifest["status"] = "incomplete"
        (args.output / "matrix.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    if args.run_smoke and all(c["status"] == "complete" for c in manifest["cases"]):
        manifest["status"] = "complete"
        (args.output / "matrix.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    print(json.dumps(dict(status=manifest["status"], cases=len(manifest["cases"]))))
    return 0 if manifest["status"] in ("complete", "planned") else 2


if __name__ == "__main__":
    sys.exit(main())
