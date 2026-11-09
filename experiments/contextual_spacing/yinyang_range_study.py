#!/usr/bin/env python3
"""Bounded range/step study for YinYang prototype sliders (research only).

Reads the full-window candidate core (yinyangfit_interactive_b2) through the
versioned range adapter (v3_ranges) where needed; changes no maintained code,
UI, model or defaults. Writes evidence JSON under
out/diagnostics/contextual-spacing/yinyang-range-study/.

Probes:
  R1 broad reach/falloff brackets, one-at-a-time at defaults + anchors.
  R2 step sensitivity (cohesion / reach / falloff) incl. exact cohesion
     switch boundaries derived from stored valid interactions.
  R3 cross-check of candidate band edges across all 13 cases x2 profiles.
  R4 numeric/sampling behavior near zero and at large values (timing,
     window growth, validity reasons; invalid overlap is NOT a failure).
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import yinyangfit_interactive_b2 as yy
import yinyangfit_interactive_v3_ranges as vr

REPO = HERE.parents[1]
CAPTURES = (REPO / "out/diagnostics/contextual-spacing"
            / "yinyangfit-interactive-v3" / "captures")

# Contrasting probe pairs (evidence set: straight/curve/diagonal/mixed).
PAIRS = ["nn", "HH", "ll", "oo", "OO", "ee", "AV", "vv", "To", "ya"]

PRIMARY = ["roboto-16-mono", "roboto-16-gray",
           "literata-16-mono", "literata-16-gray"]

REACH_BRACKET = [0.25, 0.5, 1.0, 2.0, 4.0, 6.0, 8.0, 12.0]
FALLOFF_BRACKET = [0.25, 0.5, 1.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 16.0]

# Frozen contrasting anchors: (cohesion, reach, falloff) varied one at a time.
ANCHORS = {
    "default": (1.10, 2.0, 2.0),
    "loose": (0.40, 4.0, 1.0),
    "tight": (1.80, 1.0, 4.0),
}

COHESION_STEPS = [0.10, 0.05, 0.02, 0.01]
REACH_STEPS = [0.5, 0.25, 0.10]
FALLOFF_STEPS = [1.0, 0.5, 0.25, 0.10]


def load_capture(label):
    path = CAPTURES / f"{label}.json"
    if label.endswith("-mono"):
        ds = yy.load_mono_capture(path)
    else:
        ds = yy.load_gray_capture(path)
    ds["label"] = label
    return ds


def present_pairs(dataset, names):
    out = []
    for name in names:
        left, right = ord(name[0]), ord(name[1])
        if left in dataset["cells"] and right in dataset["cells"]:
            out.append(name)
    return out


def evaluate(dataset, scorer, cohesion, scale, falloff, names):
    """Choice + validity summary for one setting over probe pairs."""
    rows = []
    for name in names:
        left, right = ord(name[0]), ord(name[1])
        try:
            rec = vr.evaluate_pair(scorer, left, right, cohesion, scale,
                                   falloff)
        except Exception as exc:  # noqa: BLE001 - record, do not stop
            rows.append({"pair": name, "error": f"{type(exc).__name__}: {exc}"})
            continue
        rows.append({
            "pair": name,
            "metric": rec["metric"],
            "chosen": rec["chosen"],
            "delta": rec["chosen"] - rec["metric"],
            "fallback": rec["fallback"],
            "fallback_reason": rec.get("fallback_reason"),
            "boundary_hit": rec["boundary_hit"],
            "minimizing": rec["minimizing_steps"],
            "valid_steps": [c["step"] for c in rec["candidates"]
                            if c["valid"]],
            "invalid_reasons": sorted({c.get("reason") or "unknown"
                                       for c in rec["candidates"]
                                       if not c["valid"]}),
            "nonfinite_valid": sum(1 for c in rec["candidates"]
                                   if c["valid"] and c.get("cost") is None),
            "interactions": {str(c["step"]): c.get("interaction")
                             for c in rec["candidates"] if c["valid"]},
        })
    return rows


def summarize(rows):
    moves = sum(1 for r in rows if "chosen" in r
                and r["chosen"] != r["metric"])
    fallbacks = sum(1 for r in rows if r.get("fallback"))
    errors = sum(1 for r in rows if "error" in r)
    nonfinite = sum(r.get("nonfinite_valid", 0) for r in rows)
    return {"pairs": len(rows), "moved": moves, "fallbacks": fallbacks,
            "errors": errors, "nonfinite_valid": nonfinite}


def cohesion_boundaries(interactions, metric):
    """Exact switch boundaries of the shared choice rule.

    interactions: {step: value} for valid steps. Returns sorted unique
    boundary midpoints between consecutive sorted-unique values, plus the
    choice interval each region maps to (metric-nearest on ties).
    """
    items = sorted(interactions.items(), key=lambda kv: kv[1])
    bounds = []
    for (s0, v0), (s1, v1) in zip(items, items[1:]):
        if v1 > v0:
            bounds.append(((v0 + v1) / 2.0, s0, s1))
    return bounds


def cohesion_grid_coverage(interactions, metric, step):
    """Which exact choice-regions a uniform cohesion grid hits.

    Grid: multiples of step covering [0, 2]. Compare region coverage:
    exact regions (from boundaries) vs regions containing >=1 grid point.
    Returns (n_regions, n_hit, missed_width_total).
    """
    vals = sorted(set(interactions.values()))
    if len(vals) <= 1:
        return 1, 1, 0.0
    bounds = [(vals[i] + vals[i + 1]) / 2.0 for i in range(len(vals) - 1)]
    lo, hi = 0.0, 2.0
    # region i spans (bounds[i-1], bounds[i]]-ish; use edges for widths.
    edges = [lo] + bounds + [hi]
    # map each region to its chosen step via midpoint probe
    ordered = sorted(interactions.items(), key=lambda kv: kv[1])
    steps_ordered = [s for s, _ in ordered]
    n = len(steps_ordered)
    grid = [round(i * step, 12) for i in range(int(round(2.0 / step)) + 1)]
    hit = 0
    missed_width = 0.0
    for i in range(n):
        a, b = edges[i], edges[i + 1]
        mid = (a + b) / 2.0
        has = any(a <= g <= b or (i == 0 and g <= b)
                  or (i == n - 1 and g >= a) for g in [mid])
        # grid hits region if any grid point falls strictly inside (a, b)
        # or on the region's owning side; approximate by midpoint proximity:
        pts = [g for g in grid if (a < g < b) or g == mid]
        # simpler robust check: region contains a grid point iff
        # ceil(a/step)*step < b (with tolerance)
        k0 = math.ceil((a - 1e-12) / step)
        g0 = k0 * step
        inside = (g0 < b - 1e-12) or (abs(g0 - b) <= 1e-12 and i == n - 1)
        if inside:
            hit += 1
        else:
            missed_width += (b - a)
    return n, hit, missed_width


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("output", type=Path)
    ap.add_argument("--stage", choices=["brackets", "steps", "xcheck", "all"],
                    default="all")
    args = ap.parse_args()
    if args.output.exists():
        ap.error("output must be new")
    t0 = time.time()
    report = {"model": yy.MODEL_IDENTITY,
              "implementation": yy.IMPLEMENTATION_SHA256,
              "ranges_version": vr.RANGES_VERSION,
              "pairs": PAIRS, "primary": PRIMARY,
              "reach_bracket": REACH_BRACKET,
              "falloff_bracket": FALLOFF_BRACKET,
              "anchors": ANCHORS}

    datasets = {label: load_capture(label) for label in PRIMARY}
    scorers = {label: yy.PairScorer(ds) for label, ds in datasets.items()}

    if args.stage in ("brackets", "all"):
        bracket = []
        for anchor_name, (coh, rch, fal) in ANCHORS.items():
            # reach sweep at anchor cohesion/falloff
            for reach in REACH_BRACKET:
                t = time.time()
                per_ds = {}
                for label in PRIMARY:
                    names = present_pairs(datasets[label], PAIRS)
                    rows = evaluate(datasets[label], scorers[label],
                                    coh, reach, fal, names)
                    per_ds[label] = {"summary": summarize(rows),
                                     "rows": rows}
                bracket.append({"sweep": "reach", "anchor": anchor_name,
                                "cohesion": coh, "reach": reach,
                                "falloff": fal,
                                "seconds": round(time.time() - t, 3),
                                "datasets": per_ds})
            # falloff sweep at anchor cohesion/reach
            for falloff in FALLOFF_BRACKET:
                t = time.time()
                per_ds = {}
                for label in PRIMARY:
                    names = present_pairs(datasets[label], PAIRS)
                    rows = evaluate(datasets[label], scorers[label],
                                    coh, rch, falloff, names)
                    per_ds[label] = {"summary": summarize(rows),
                                     "rows": rows}
                bracket.append({"sweep": "falloff", "anchor": anchor_name,
                                "cohesion": coh, "reach": rch,
                                "falloff": falloff,
                                "seconds": round(time.time() - t, 3),
                                "datasets": per_ds})
        report["brackets"] = bracket

    if args.stage in ("steps", "all"):
        # Exact cohesion boundaries on representative geometry columns.
        columns = [(2.0, 2.0), (2.0, 3.0), (2.0, 4.0), (2.0, 6.0),
                   (2.0, 8.0), (1.0, 2.0), (4.0, 2.0), (4.0, 4.0),
                   (1.0, 4.0), (2.0, 10.0)]
        coh_detail = []
        for label in PRIMARY:
            names = present_pairs(datasets[label], PAIRS)
            for (reach, falloff) in columns:
                metric_steps = {}
                for name in names:
                    left, right = ord(name[0]), ord(name[1])
                    metric = yy.metric_step(datasets[label], left, right)
                    geos = []
                    for delta in yy.CANDIDATE_DELTAS:
                        g = vr.score_geometry(scorers[label], left, right,
                                              metric + delta, reach, falloff)
                        geos.append(g)
                    valid = {g["step"]: g["interaction"] for g in geos
                             if g["valid"] and g.get("interaction") is not None
                             and math.isfinite(g["interaction"])}
                    entry = {"pair": name, "metric": metric,
                             "n_valid": len(valid),
                             "interaction_span":
                                 ([min(valid.values()), max(valid.values())]
                                  if valid else None),
                             "boundaries": [
                                 {"at": b, "from_step": s0, "to_step": s1}
                                 for (b, s0, s1) in cohesion_boundaries(
                                     valid, metric)] if valid else [],
                             "grids": []}
                    for st in COHESION_STEPS:
                        if valid:
                            n, hit, missed = cohesion_grid_coverage(
                                valid, metric, st)
                            entry["grids"].append(
                                {"step": st, "regions": n,
                                 "regions_hit": hit,
                                 "regions_missed": n - hit,
                                 "missed_width": round(missed, 4)})
                    coh_detail.append({"dataset": label, "reach": reach,
                                       "falloff": falloff, **entry})
        report["cohesion_geometry"] = coh_detail

        # Reach/falloff step sensitivity: dense reference vs coarse grids.
        sens_pairs = ["nn", "AV", "To", "ya"]
        dense = []
        for label in ["roboto-16-mono", "literata-16-mono",
                      "roboto-16-gray"]:
            names = present_pairs(datasets[label], sens_pairs)
            # dense reach reference 0.25..8 at 0.25 (anchor cohesion/falloff)
            for coh, rch, fal, axis, lo, hi, fine in (
                    (1.10, None, 2.0, "reach", 0.25, 8.0, 0.25),
                    (1.10, 2.0, None, "falloff", 0.25, 12.0, 0.25)):
                for name in names:
                    left, right = ord(name[0]), ord(name[1])
                    curve = []
                    v = lo
                    while v <= hi + 1e-9:
                        if axis == "reach":
                            rows = evaluate(datasets[label], scorers[label],
                                            coh, round(v, 6), fal, [name])
                        else:
                            rows = evaluate(datasets[label], scorers[label],
                                            coh, rch, round(v, 6), [name])
                        r = rows[0]
                        curve.append({"at": round(v, 4),
                                      "chosen": r.get("chosen"),
                                      "delta": r.get("delta"),
                                      "fallback": r.get("fallback", None),
                                      "error": r.get("error")})
                        v = round(v + fine, 10)
                    # distinct choice runs along the curve
                    runs = []
                    for pt in curve:
                        if not runs or runs[-1]["chosen"] != pt["chosen"]:
                            runs.append({"chosen": pt["chosen"],
                                         "first_at": pt["at"]})
                    # coarse-grid recovery: sample curve at grid multiples
                    rec = {}
                    for cst in (REACH_STEPS if axis == "reach"
                                else FALLOFF_STEPS):
                        grid_at = set()
                        v = math.ceil(lo / cst - 1e-9) * cst
                        while v <= hi + 1e-9:
                            # nearest dense sample
                            idx = min(range(len(curve)),
                                      key=lambda i: abs(curve[i]["at"] - v))
                            grid_at.add(curve[idx]["chosen"])
                            v = round(v + cst, 10)
                        curve_vals = {p["chosen"] for p in curve}
                        rec[str(cst)] = {
                            "grid_choices": sorted(grid_at),
                            "curve_choices": sorted(curve_vals),
                            "missed": sorted(curve_vals - grid_at)}
                    dense.append({"dataset": label, "axis": axis, "pair": name,
                                  "anchor": [coh, rch, fal],
                                  "n_distinct": len({p["chosen"]
                                                     for p in curve}),
                                  "runs": runs, "recovery": rec,
                                  "curve": curve})
        report["dense_sensitivity"] = dense

    if args.stage in ("xcheck", "all"):
        labels = sorted(p.stem for p in CAPTURES.glob("*.json"))
        settings = [(0.40, 1.0, 1.0), (1.10, 2.0, 2.0),
                    (1.10, 2.0, 4.0), (1.10, 2.0, 6.0),
                    (1.80, 4.0, 4.0), (1.10, 6.0, 2.0),
                    (1.10, 0.5, 2.0), (1.10, 2.0, 0.5)]
        xc = []
        for label in labels:
            ds = load_capture(label)
            sc = yy.PairScorer(ds)
            names = present_pairs(ds, PAIRS)
            for (coh, rch, fal) in settings:
                rows = evaluate(ds, sc, coh, rch, fal, names)
                xc.append({"dataset": label, "cohesion": coh,
                           "reach": rch, "falloff": fal,
                           "summary": summarize(rows), "rows": rows})
        report["xcheck"] = {"labels": labels,
                            "settings": settings, "rows": xc}

    report["seconds"] = round(time.time() - t0, 1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=1))
    print(f"wrote {args.output} in {report['seconds']}s")


if __name__ == "__main__":
    main()
