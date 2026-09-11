"""Source-alignment working path (NOT a full-faithfulness claim).

Uses Pipeline ONLY for original font job loading, instantiation and
provenance. Calls build_font directly with profile='baseline' and
ppem=size and no search-override context, so first-oncurve
representatives are restored through the existing feature_model
baseline policy. Never calls the Pipeline baseline helper, the
per-key driver, or any fitting/postprocessing stage. No visual
image generation, comparison,
or glyph-specific logic. Unresolved assumptions remain; see readiness.
"""

import argparse
import hashlib
import json
import platform
from pathlib import Path

import fontTools
import freetype as ft
import numpy as np

import source_bitmap_output as output_mod
from build_source_bitmap import FACES, SIZES, Pipeline, _json_default
from check_shamir_baseline import (
    construction_issues,
    coordinate_check,
    decision_metadata_present,
    digest,
    graph_issues,
)
from compare_shamir_pipeline import CHARS
from shamir_model import build_font

HERE = Path(__file__).resolve().parent
READINESS = "source-alignment working baseline; unresolved decisions require review"
PAPER_DIR = HERE.parents[1] / "docs" / "reference" / "fonts" / "papers"
ENABLED_STAGES = ("source-instantiation", "baseline-model", "native-verification")


def _sanitize(value, secrets):
    ordered = sorted(secrets, key=len, reverse=True)
    if isinstance(value, str):
        for secret in ordered:
            if secret:
                value = value.replace(secret, "<path>")
        return value
    if isinstance(value, dict):
        return {k: _sanitize(v, secrets) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v, secrets) for v in value]
    return value


def _secrets(pipeline, output):
    parts = {str(HERE), str(Path(output).resolve()), str(Path.home())}
    work = getattr(pipeline, "work", None)
    if work is not None:
        parts.add(str(work))
    try:
        parts.add(str(Path.cwd()))
    except OSError:
        pass
    return {p for p in parts if p}


def _validate(families, sizes):
    families = tuple(families)
    sizes = tuple(sizes)
    if not families or not sizes:
        raise ValueError("families and sizes must both be non-empty")
    if len(set(families)) != len(families):
        raise ValueError("duplicate families rejected")
    if len(set(sizes)) != len(sizes):
        raise ValueError("duplicate sizes rejected")
    unknown = [f for f in families if f not in FACES]
    if unknown:
        raise ValueError(f"unknown families rejected: {unknown}")
    for size in sizes:
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ValueError(f"invalid size rejected: {size!r}")
    return families, sizes


def run(output, families=FACES, sizes=SIZES):
    families, sizes = _validate(families, sizes)
    output = Path(output)
    expected_builds = len(families) * len(sizes)
    builds, failures = [], []
    paper_hashes = {}
    pipeline = Pipeline(output)
    pipeline.provenance = {"stages": list(ENABLED_STAGES)}
    secrets = _secrets(pipeline, output)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        pipeline.close()
        raise ValueError("use an empty output directory to preserve frozen evidence")
    try:
        pipeline.note_sources()
        if PAPER_DIR.is_dir():
            for pdf in sorted(PAPER_DIR.glob("*.pdf")):
                display = output_mod.repo_relative(pdf)
                pipeline.use_input(pdf)
                paper_hashes[display] = pipeline.inputs.get(
                    display, hashlib.sha256(pdf.read_bytes()).hexdigest())
        for family in families:
            for size in sizes:
                key = f"{family}-{size}"
                target = output / f"{key}-baseline.ttf"
                build_path = output / f"{key}-build.json"
                try:
                    static_path = pipeline.instantiate(key, family, size)
                    build = build_font(
                        static_path, target, CHARS,
                        profile="baseline", ppem=size,
                    )
                    if not decision_metadata_present(build):
                        raise ValueError("baseline build lacks baseline_decisions metadata")
                    if set(build["records"]) != set(CHARS):
                        raise ValueError("baseline build does not cover requested repertoire")
                    build_path.write_text(
                        json.dumps(_sanitize(build, secrets), indent=2,
                                   default=_json_default) + "\n")
                    face = ft.Face(str(target))
                    cases = []
                    for char, record in build["records"].items():
                        try:
                            topo = {s: graph_issues(record[s]) for s in ("reduced_graph", "graph")}
                            structural = construction_issues(record)
                            native = coordinate_check(face, char, size, record["graph"])
                            rejected = sum(
                                len(record[s].get("rejected", []))
                                for s in ("reduced_graph", "graph"))
                            case_ok = (
                                not any(topo.values()) and not structural
                                and native.get("passed", False))
                            cases.append({
                                "char": char,
                                "graph_issues": topo,
                                "construction_issues": structural,
                                "native_coordinates": {
                                    "passed": bool(native.get("passed", False)),
                                    "max_coordinate_error_px": native.get("max_coordinate_error_px"),
                                    "tolerance_px": native.get("tolerance_px"),
                                },
                                "rejected_constraints": rejected,
                                "passed": bool(case_ok),
                            })
                            if not case_ok:
                                failures.append(_sanitize({
                                    "stage": "case",
                                    "font": family, "size": size, "char": char,
                                    "error": "case verification failed",
                                    "graph_issues": topo,
                                    "construction_issues": structural,
                                    "native_passed": bool(native.get("passed", False)),
                                }, secrets))
                        except Exception as exc:  # noqa: BLE001 - record case, continue
                            cases.append({"char": char, "passed": False,
                                          "error": f"{type(exc).__name__}: {exc}"})
                            failures.append(_sanitize({
                                "stage": "case",
                                "font": family, "size": size, "char": char,
                                "error": f"{type(exc).__name__}: {exc}",
                            }, secrets))
                    builds.append(_sanitize({
                        "font": family, "size": size, "key": key,
                        "output": target.name, "build_json": build_path.name,
                        "input_sha256": digest(static_path),
                        "output_sha256": digest(target),
                        "build_json_sha256": digest(build_path),
                        "baseline_decisions": build.get("baseline_decisions"),
                        "cases": cases,
                        "passed": all(c["passed"] for c in cases),
                    }, secrets))
                except Exception as exc:  # noqa: BLE001 - record and continue
                    failures.append(_sanitize({
                        "stage": "build",
                        "font": family, "size": size,
                        "error": f"{type(exc).__name__}: {exc}",
                    }, secrets))
        try:
            pipeline.verify_inputs_unchanged()
            pipeline.verify_sources()
        except Exception as exc:  # noqa: BLE001 - guard breach is a failure
            failures.append(_sanitize(
                {"stage": "verify", "error": f"{type(exc).__name__}: {exc}"}, secrets))
    except Exception as exc:  # noqa: BLE001 - setup failure must persist a report
        failures.append(_sanitize(
            {"stage": "setup", "error": f"{type(exc).__name__}: {exc}"}, secrets))
    finally:
        if pipeline is not None:
            try:
                pipeline.close()
            except Exception as exc:
                failures.append({"stage": "cleanup", "error": f"{type(exc).__name__}: {exc}"})
            inputs = dict(pipeline.inputs)
        else:
            inputs = {}
        passed = (not failures and len(builds) == expected_builds
                  and all(b["passed"] for b in builds))
        report = _sanitize({
            "config": {
                "policy": "first-oncurve",
                "profile": "baseline",
                "families": list(families),
                "sizes": list(sizes),
                "enabled_stages": list(ENABLED_STAGES),
            },
            "inputs": inputs,
            "provenance": dict(pipeline.provenance),
            "paper_hashes": paper_hashes,
            "builds": builds,
            "failures": failures,
            "counts": {
                "expected_builds": expected_builds,
                "builds": len(builds),
                "cases": sum(len(b["cases"]) for b in builds),
                "failures": len(failures),
            },
            "versions": {
                "python": platform.python_version(),
                "freetype": list(ft.version()),
                "fonttools": fontTools.__version__,
                "numpy": np.__version__,
            },
            "passed": bool(passed),
            "readiness": READINESS,
        }, secrets)
        (output / "source-alignment-report.json").write_text(
            json.dumps(report, indent=2, default=_json_default) + "\n")
    print(json.dumps({"passed": report["passed"], "counts": report["counts"],
                      "failures": len(failures)}, indent=2))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--families", nargs="+", default=list(FACES))
    parser.add_argument("--sizes", nargs="+", type=int, default=list(SIZES))
    args = parser.parse_args(argv)
    result = run(args.output, families=args.families, sizes=args.sizes)
    if not result["passed"]:
        raise SystemExit("source-alignment verification failed; see persisted report")


if __name__ == "__main__":
    main()
