#!/usr/bin/env python3
# cspell:words yinyangfit
"""Build the predictable spacing-control prototype page (isolated, offline file:// use).

Two separated controls over the 13 canonical root samples in both profiles:
optical correction strength toward the retained Hu/Hersch fitted-outline
density-conserving endpoint, and integer letter spacing at internal span gaps.
The interaction scorer is out of the path. The owning design subsection
"Predictable spacing-control prototype" states the endpoint identity, the
Source/continuous blend before signed rounding, the span-gap tracking policy
and the Gray source-backed adapter; this module implements exactly that.

Endpoint machinery is the retained experiment solver (hu_hersch calibrated
density model with full-outline construction), not a new optical method.
Source at strength zero is an explicit bypass; full strength reproduces the
retained endpoint including its safeguards. Gray reuses the same integer
correction deltas over fractional 26.6 source accumulation because the frozen
Gray captures carry no fitted outlines.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import yinyangfit_interactive as yy
import yinyangfit_interactive_v3 as v3
from solver import Controls, Solver, IMPLEMENTATION_IDENTITY

REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "apps/web/scripts/landing-samples"))
import generate as landing_generate

OUT = REPO / "out/diagnostics/contextual-spacing/predictable-spacing"
CAPTURES = (REPO / "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3"
            / "captures")
MODEL = "predictable-spacing-v4"
SPACING_MODEL = "hu_fitted_full_density_conserved_touch"
STRENGTH_GRID = [round(i / 20, 2) for i in range(21)]
LETTER_MIN, LETTER_MAX = -2, 4
LETTER_FROZEN = (-2, 0, 4)


def pixel_round(value):
    return __import__("math").floor(value + 0.5) if value >= 0 else __import__(
        "math").ceil(value - 0.5)


def compose_step(record, strength):
    """Retained solver composition: blend Source/continuous-optical before
    signed rounding (ties away from zero), then the feasibility floor."""
    if strength == 0 or record["optical_adjustment"] is None:
        return record["metric"]
    blended = (record["metric_adjustment"] * (1 - strength)
               + record["optical_adjustment"] * strength)
    step = record["advance"] + pixel_round(blended)
    if record["minimum"] is not None:
        step = max(step, record["minimum"])
    return step


def endpoint_record(solver, left, right):
    """One ordered pair's retained endpoint composition inputs."""
    result = solver.pair(
        left, right, Controls(spacing_model=SPACING_MODEL, optical=1.0))
    advance = solver.glyphs[left]["finalized_advance_px"]
    metric = result["metric_adjustment_px"]
    optical = result["optical_adjustment_px"]
    return {
        "advance": advance,
        "metric": advance + metric,
        "metric_adjustment": metric,
        "optical_adjustment": optical,
        "minimum": result["clearance_min_step_px"],
        "reason": result["reason"],
    }


def gray_fractional(dataset, left, right):
    # Independent captured-source policy, mirroring the native surface: raw
    # fractional advance plus the full 26.6 pair adjustment, no per-pair
    # rounding. Mono advances are whole pixels, so both policies agree there.
    if dataset["profile"] == "mono":
        advance = float(dataset["cells"][left]["advance_px"])
    else:
        advance = float(dataset["advances"][left])
    return advance + float(dataset["adjustments"].get((left, right), 0.0))


def build_case(entry, captures):
    case_id = entry["id"]
    text = entry.get("text") or landing_generate.DEFAULT_TEXT
    font_path = (REPO / "apps/web/scripts/landing-samples"
                 / entry["font"]).resolve()
    if not font_path.is_file():
        raise ValueError(f"missing font for {case_id}: {font_path}")
    if entry.get("font_url"):
        if v3.sha_file(font_path) != entry["font_sha256"]:
            raise ValueError(f"pinned font identity mismatch for {case_id}")
    case = {"id": case_id, "family_id": entry["family_id"],
            "family_label": entry["family_label"],
            "size_px": entry["size_px"], "axes": entry["axes"],
            "font_file": font_path.name,
            "font_sha256": v3.sha_file(font_path), "text": text,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "line_pitch": int(3 * entry["size_px"]),
            "profiles": {}, "tables": {}}
    mono_capture = json.loads(
        (captures / f"{case_id}-mono.json").read_text())
    solver = Solver(mono_capture)
    for profile in ("mono", "gray"):
        dataset = v3.load_case_dataset(case_id, profile, captures)
        repertoire = set(dataset["cells"])
        missing = {c for c in text if c != "\n" and ord(c) not in repertoire}
        if missing:
            raise ValueError(
                f"{case_id} {profile}: sample text outside repertoire: "
                + " ".join(f"U+{ord(c):04X}" for c in sorted(missing)))
        glyphs = v3.pack_glyphs(dataset)
        lines = text.split("\n")
        captured = [yy.captured_source_word_origins(dataset, line)["origins"]
                    for line in lines]
        gaps, pairs = [], {}
        for line in lines:
            line_gaps = []
            for left_ch, right_ch in zip(line, line[1:]):
                left, right = ord(left_ch), ord(right_ch)
                space = left == 32 or right == 32
                metric = yy.metric_step(dataset, left, right)
                frac = gray_fractional(dataset, left, right)
                name = left_ch + right_ch
                if not space and name not in pairs:
                    record = endpoint_record(solver, left, right)
                    if profile == "mono" and record["metric"] != metric:
                        raise ValueError(
                            f"{case_id} {name}: solver/yy metric mismatch "
                            f"{record['metric']} vs {metric}")
                    pairs[name] = record
                line_gaps.append({"pair": name, "space": space,
                                  "metric": metric, "frac": frac})
            gaps.append(line_gaps)
        grid_steps = {name: [compose_step(rec, s) for s in STRENGTH_GRID]
                      for name, rec in pairs.items()}
        case["profiles"][profile] = {
            "label": dataset["label"], "capture": dataset["capture_path"],
            "capture_sha256": v3.sha_file(REPO / dataset["capture_path"]),
            "source_sha256": v3.capture_source_sha(dataset["capture_path"]),
            "glyphs": glyphs, "lines": lines, "captured": captured,
            "gaps": gaps}
        case["tables"][profile] = {
            "label": dataset["label"], "profile": profile,
            "size_px": dataset["size_px"], "pairs": pairs,
            "grid": {"strengths": STRENGTH_GRID, "steps": grid_steps}}
    return case, solver.identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cases", type=Path,
                        default=REPO / "apps/web/scripts/landing-samples/main-page.json")
    parser.add_argument("--captures", type=Path, default=CAPTURES)
    parser.add_argument("--only", action="append", default=None,
                        help="restrict to these case ids (debugging)")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must be new")
    catalogue = json.loads(args.cases.read_text())
    if len(catalogue) != 13:
        raise ValueError("root catalogue must hold all 13 cases")
    if args.only:
        catalogue = [e for e in catalogue if e["id"] in args.only]
        if not catalogue:
            raise ValueError("no catalogue entries match --only")
    boot = {"model": MODEL, "spacing_model": SPACING_MODEL,
            "implementation": IMPLEMENTATION_IDENTITY,
            "solver_module": hashlib.sha256(
                (HERE / "solver.py").read_bytes()).hexdigest(),
            "scorer_module": yy.IMPLEMENTATION_SHA256,
            "controls": {"letter_min": LETTER_MIN, "letter_max": LETTER_MAX,
                         "default": {"optical": 0.0, "letter": 0}},
            "cases": []}
    tables_out, identities = {}, set()
    started = time.time()
    for entry in catalogue:
        case, identity = build_case(entry, args.captures)
        identities.add(identity)
        tables = case.pop("tables")
        for profile, table in tables.items():
            tables_out[f"{case['id']}-{profile}"] = table
        boot["cases"].append(case)
        print(f"built {case['id']}: "
              f"{len(tables['mono']['pairs'])} pairs", flush=True)
    template = (HERE / "predictable_spacing_template.html").read_text()
    app_js = (HERE / "predictable_spacing_app.js").read_text()
    wiring_js = (HERE / "predictable_spacing_wiring.js").read_text()
    for name, content in (("template", template), ("app", app_js),
                          ("wiring", wiring_js)):
        if "title=" in content:
            raise ValueError(f"native title tooltips forbidden ({name})")
    payload = json.dumps(boot, separators=(",", ":"), allow_nan=False)
    page = template.replace("__PS_BOOT__", payload)
    page = page.replace("__PS_APP_JS__", app_js)
    page = page.replace("__PS_WIRING_JS__", wiring_js)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "index.html").write_text(page)
    data_dir = args.output / "data"
    data_dir.mkdir()
    for label, table in tables_out.items():
        (data_dir / f"ps-{label}.js").write_text(
            "window.PS_TABLES = window.PS_TABLES || {};\n"
            f"window.PS_TABLES[{label!r}] = "
            + json.dumps(table, separators=(",", ":"), allow_nan=False)
            + ";\n")
    manifest = {"model": boot["model"], "spacing_model": SPACING_MODEL,
                "implementation": IMPLEMENTATION_IDENTITY,
                "cases": [c["id"] for c in boot["cases"]],
                "datasets": sorted(tables_out),
                "analysis_identities": sorted(identities),
                "seconds": round(time.time() - started, 1),
                "page_bytes": len(page.encode())}
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n")
    (args.output / "boot.json").write_text(json.dumps(boot, indent=2) + "\n")
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
