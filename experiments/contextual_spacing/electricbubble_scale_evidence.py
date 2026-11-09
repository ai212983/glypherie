# cspell:words dsobj electricbubble feas fullfield inva invb ppem rawmap rdir rfields roboto sfields tobytes yinyangfit
"""Evidence driver for the Electric Bubble scale adaptation experiment.

Reads frozen captures with the frozen full-field port (raw arm) and the
scale wrapper (normalized arm); writes synthetics, paired-domain
comparisons, target-attainability inspection and determinism checks under
out/diagnostics/contextual-spacing/electricbubble-scale/. Response-shape
verdicts belong in the owning report, not here: this driver records
measurements with exact tolerances so numerical jitter is never sold as
bumpiness.
"""

import copy
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "contextual_spacing"))
import electricbubble_fullfield as F  # noqa: E402
import electricbubble_scale as S  # noqa: E402
import yinyangfit_interactive as YI  # noqa: E402

DIAG = ROOT / "out" / "diagnostics" / "contextual-spacing"
OUT = DIAG / "electricbubble-scale"
CAPTURES = DIAG / "yinyangfit-interactive-v3" / "captures"

CORE_PAIRS = ["og", "Th", "rt", "nn", "oo", "HH", "av", "To", "al", "ri",
              "se"]
CORE_DATASETS = ["roboto-16-mono", "roboto-16-gray", "literata-16-mono",
                 "literata-16-gray"]
EXTENDED_PAIRS = ["og", "Th", "rt", "nn", "oo"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parity_cells():
    # Same frozen synthetic family as the full-field port tests:
    # parallel bars, asymmetric vertical offset, support multiplicity.
    def cell(w, h, top, cover):
        return {"width": w, "height": h, "top": top, "left": 0.0,
                "cover": cover}

    cells = {"A": cell(3, 12, 2, [1.0] * 36),
             "B": cell(3, 12, 2, [1.0] * 36)}
    cells["C"] = dict(cells["A"])
    cells["D"] = cell(3, 12, 5, [1.0] * 36)
    cov = [0.0] * (7 * 12)
    for r in range(12):
        for c in (0, 1, 4, 5):
            cov[r * 7 + c] = 1.0
    cells["E"] = dict(cells["A"])
    cells["F"] = cell(7, 12, 2, cov)
    return cells


def upscale_cells(cells, factor):
    # Exact integer-grid replication: the same geometry at a multiple of
    # the scale with no interpolation policy intruding. Cover values stay
    # exact; bearings scale with the geometry.
    out = {}
    for key, c in cells.items():
        w, h = c["width"], c["height"]
        cover = []
        for row in range(h):
            band = c["cover"][row * w:(row + 1) * w]
            wide = [v for v in band for _ in range(factor)]
            for _ in range(factor):
                cover.extend(wide)
        out[key] = {"width": w * factor, "height": h * factor,
                    "top": c["top"] * factor,
                    "left": float(c["left"]) * factor, "cover": cover}
    return out


def strict_interior_extrema(values):
    # Host-assessment definition: strict inequalities, no amplitude
    # threshold; equal-valued shoulders are not extrema.
    return sum(1 for i in range(1, len(values) - 1)
               if values[i - 1] < values[i] > values[i + 1]
               or values[i - 1] > values[i] < values[i + 1])


def shoulder_amplitudes(values):
    amps = []
    for i in range(1, len(values) - 1):
        if values[i - 1] < values[i] > values[i + 1] \
                or values[i - 1] > values[i] < values[i + 1]:
            denom = max(abs(values[i - 1]), abs(values[i]),
                        abs(values[i + 1]), 1e-30)
            amps.append(min(abs(values[i - 1] - values[i]),
                            abs(values[i + 1] - values[i])) / denom)
    return amps


def shared_runs(raw_curve, scaled_curve):
    # Identical valid, collision-free step mask for both arms; runs break
    # at invalids exactly as in the host assessment.
    raw = {c["step"]: c for c in raw_curve}
    scaled = {c["step"]: c for c in scaled_curve}
    runs, run = [], []
    for step in sorted(set(raw) & set(scaled)):
        a, b = raw[step], scaled[step]
        if (a["valid"] and b["valid"]
                and not b.get("project_overlap_guard")
                and math.isfinite(a.get("interaction", float("nan")))
                and math.isfinite(b.get("interaction", float("nan")))):
            run.append((a["interaction"], b["interaction"]))
        else:
            if run:
                runs.append(run)
            run = []
    if run:
        runs.append(run)
    return runs


def curve_stats(runs):
    raw_vals = [v for run in runs for v, _ in run]
    scaled_vals = [v for run in runs for _, v in run]
    raw_runs = [[v for v, _ in run] for run in runs]
    scaled_runs = [[v for _, v in run] for run in runs]
    raw_ext = sum(strict_interior_extrema(r) for r in raw_runs)
    scaled_ext = sum(strict_interior_extrema(r) for r in scaled_runs)
    amps = [a for r in scaled_runs for a in shoulder_amplitudes(r)]
    return {"shared_steps": sum(len(r) for r in runs),
            "raw_extrema": raw_ext, "scaled_extrema": scaled_ext,
            "scaled_shoulder_min": min(amps) if amps else None,
            "scaled_shoulders_above_1e-3": sum(a > 1e-3 for a in amps)}


def attainability(curve, metric):
    # Transported author target 0.01 against the measured range: where is
    # the closest approach, interior or domain edge? No fitting here.
    feas = [(c["step"], c["interaction"]) for c in curve
            if c["valid"] and math.isfinite(
                c.get("interaction", float("nan")))]
    if not feas:
        return {"feasible": 0, "target": 0.01, "closest": None,
                "interior": None, "range": [None, None]}
    best = min(abs(v - 0.01) for _, v in feas)
    mini = sorted(s for s, v in feas if abs(abs(v - 0.01) - best) < 1e-9)
    steps = sorted(s for s, _ in feas)
    inside = [s for s in mini if s != steps[0] and s != steps[-1]]
    vals = [v for _, v in feas]
    return {"feasible": len(feas), "target": 0.01, "closest": best,
            "closest_steps": mini, "interior": bool(inside),
            "range": [min(vals), max(vals)], "metric": metric}


def synth_evidence(out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    cells = parity_cells()
    fixtures = {"parallel": ("A", "B"), "asymmetric": ("C", "D"),
                "multiplicity": ("A", "F")}
    record = {"fixtures": {}, "identity": {}, "phase": {},
              "determinism": {}}
    for name, (a, b) in fixtures.items():
        small = {a: cells[a], b: cells[b]}
        large = upscale_cells(small, 2)
        for tag, use, ppem in (("small", small, 16.0), ("large", large,
                                                       32.0)):
            gs = F.GlyphSet(use)
            params = S.scaled_params(ppem)
            sfields, _ = S.build_scaled_fields(gs, params)
            rfields, _ = F.build_fields(gs)
            # Physically corresponding separations: the large fixture is
            # the exact 2x geometry, so its steps are doubled.
            steps = [2 * s for s in range(2, 14)] if tag == "large" \
                else list(range(2, 14))
            raw_curve = F.source_curve(gs, rfields, a, b, use[a], use[b],
                                       steps)
            norm_curve = F.source_curve(gs, sfields, a, b, use[a],
                                        use[b], steps)
            runs = shared_runs(raw_curve, norm_curve)
            stats = curve_stats(runs)
            stats["raw_range"] = [min(c["interaction"] for c in raw_curve
                                      if c["valid"]),
                                  max(c["interaction"] for c in raw_curve
                                      if c["valid"])]
            stats["scaled_range"] = [min(c["interaction"]
                                         for c in norm_curve
                                         if c["valid"]),
                                     max(c["interaction"] for c in norm_curve
                                         if c["valid"])]
            record["fixtures"].setdefault(name, {})[tag] = stats
    # r = 1 identity on the small geometry: scaled rule must reproduce the
    # frozen port exactly (same code path, asserted to 1e-12).
    small = {"A": cells["A"], "B": cells["B"]}
    gs = F.GlyphSet(small)
    sfields, _ = S.build_scaled_fields(gs, S.scaled_params(72.0))
    rfields, _ = F.build_fields(gs)
    deltas = []
    for overlap in range(55, 75):
        want = F.score_at_overlap(rfields["A"], rfields["B"],
                                  overlap)["meanInteraction"]
        got = F.score_at_overlap(sfields["A"], sfields["B"],
                                 overlap)["meanInteraction"]
        deltas.append(abs(got - want))
    record["identity"] = {"overlaps": [55, 74], "max_abs_delta": max(
        deltas)}
    # Integer translation control only: GlyphSet rebases the union rows,
    # so these canvases are identical. This does not change subpixel phase.
    both = {k: dict(v, top=v["top"] + 1) for k, v in small.items()}
    gs0, gs1 = F.GlyphSet(small), F.GlyphSet(both)
    p16 = S.scaled_params(16.0)
    f0, _ = S.build_scaled_fields(gs0, p16)
    f1, _ = S.build_scaled_fields(gs1, p16)
    steps = list(range(2, 14))
    c0 = F.source_curve(gs0, f0, "A", "B", small["A"], small["B"],
                        steps)
    c1 = F.source_curve(gs1, f1, "A", "B", both["A"], both["B"], steps)
    phase_deltas = [abs(x["interaction"] - y["interaction"])
                    for x, y in zip(c0, c1)
                    if x["valid"] and y["valid"]]
    left_only = {**small, "A": dict(small["A"], left=1.0)}
    gs2 = F.GlyphSet(left_only)
    o_base = F.step_to_overlap(gs0, "A", small["A"], small["B"], 8)
    o_left = F.step_to_overlap(gs2, "A", left_only["A"], small["B"], 8)
    record["phase"] = {
        "both_shift_max_abs_delta": max(phase_deltas),
        "both_shift_steps_compared": len(phase_deltas),
        "left_only_overlap_delta": abs(o_left - o_base)}
    # Determinism: identical inputs rerun byte-identical through the
    # scaled path.
    once = S.build_scaled_fields(F.GlyphSet(small), p16)[0][
        "A"].bubble.tobytes()
    twice = S.build_scaled_fields(F.GlyphSet(small), p16)[0][
        "A"].bubble.tobytes()
    record["determinism"] = {"rerun_byte_identical": once == twice}
    (out_dir / "synthetics.json").write_text(json.dumps(record, indent=1)
                                             + "\n")
    return record


def analyze_pair(raw_rec, scaled_rec, metric):
    runs = shared_runs(raw_rec["source_curve"],
                       scaled_rec["source_curve"])
    stats = curve_stats(runs)
    stats["pair"] = raw_rec["pair"]
    stats["metric"] = metric
    raw_by_step = {c["step"]: c for c in raw_rec["source_curve"]}
    scaled_by_step = {c["step"]: c for c in scaled_rec["source_curve"]}
    shared = [s for s in sorted(set(raw_by_step) & set(scaled_by_step))
              if all(c["valid"] and not c.get("project_overlap_guard")
                     and math.isfinite(c.get("interaction", float("nan")))
                     for c in (raw_by_step[s], scaled_by_step[s]))]
    stats["raw_attain"] = attainability([raw_by_step[s] for s in shared], metric)
    stats["scaled_attain"] = attainability([scaled_by_step[s] for s in shared], metric)
    for arm, rec in (("raw", raw_rec), ("scaled", scaled_rec)):
        w = rec["source_walk"]
        stats[f"{arm}_walk"] = {"status": w["terminal"]["status"],
                                "terminalStep": w["terminalStep"],
                                "distance": w["distance"]}
        stats[f"{arm}_guarded_choice"] = rec["source_exhaustive_guarded"][
            "chosen"]
        stats[f"{arm}_unguarded_choice"] = rec["source_exhaustive"][
            "chosen"]
    return stats


def paired_evidence(raw_dir, scaled_dir, datasets, pairs, out_path):
    rows = []
    for dataset in datasets:
        raw = json.loads((Path(raw_dir) / dataset / "comparison.json")
                         .read_text())["results"]
        scaled = json.loads((Path(scaled_dir) / dataset
                             / "comparison.json").read_text())["results"]
        raw_map = {r["pair"]: r for r in raw}
        scaled_map = {r["pair"]: r for r in scaled}
        cap = json.loads((CAPTURES / f"{dataset}.json").read_text())
        for pair in pairs:
            metric = YI.metric_step(cap, ord(pair[0]), ord(pair[1]))
            rows.append({"dataset": dataset,
                         **analyze_pair(raw_map[pair], scaled_map[pair],
                                        metric)})
    agg = {"pair_cases": len(rows),
           "shared_steps": sum(r["shared_steps"] for r in rows),
           "raw_extrema": sum(r["raw_extrema"] for r in rows),
           "scaled_extrema": sum(r["scaled_extrema"] for r in rows),
           "scaled_interior_targets": sum(
               1 for r in rows if r["scaled_attain"]["interior"]),
           "raw_interior_targets": sum(
               1 for r in rows if r["raw_attain"]["interior"])}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"aggregate": agg, "rows": rows},
                                   indent=1) + "\n")
    return agg


def load_yi_dataset(capture_path, profile):
    keys = list("og")
    if profile == "mono":
        return F.mono_cells_for_keys(capture_path, keys)[0]
    return F.gray_cells_for_keys(capture_path, keys)[0]


def paired_core(out_path):
    # Raw baseline: the frozen 11-pair roboto-16-mono run is reused by
    # reference; the other three core datasets were run with the frozen
    # full-field module (port hash recorded in their manifests).
    rawmap = {
        "roboto-16-mono":
        DIAG / "electricbubble-fullfield" / "roboto16mono",
        "roboto-16-gray": OUT / "raw-baseline" / "roboto-16-gray",
        "literata-16-mono": OUT / "raw-baseline" / "literata-16-mono",
        "literata-16-gray": OUT / "raw-baseline" / "literata-16-gray",
    }
    rows = []
    for ds, rdir in rawmap.items():
        profile = "gray" if ds.endswith("gray") else "mono"
        raw = json.loads((rdir / "comparison.json").read_text())["results"]
        scaled = json.loads(
            (OUT / "core" / ds / "comparison.json").read_text())["results"]
        raw_map = {r["pair"]: r for r in raw}
        scaled_map = {r["pair"]: r for r in scaled}
        dsobj = load_yi_dataset(str(CAPTURES / f"{ds}.json"), profile)
        for pair in CORE_PAIRS:
            metric = YI.metric_step(dsobj, ord(pair[0]), ord(pair[1]))
            rows.append({"dataset": ds,
                         **analyze_pair(raw_map[pair], scaled_map[pair],
                                        metric)})
    agg = {"pair_cases": len(rows),
           "shared_steps": sum(r["shared_steps"] for r in rows),
           "raw_extrema": sum(r["raw_extrema"] for r in rows),
           "scaled_extrema": sum(r["scaled_extrema"] for r in rows),
           "scaled_interior_targets": sum(
               1 for r in rows if r["scaled_attain"]["interior"]),
           "raw_interior_targets": sum(
               1 for r in rows if r["raw_attain"]["interior"])}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"aggregate": agg, "rows": rows},
                                   indent=1) + "\n")
    return {"aggregate": agg}


def paired_extended(out_path):
    # 5-pair subset across all 13 captures x 2 profiles; the raw arm is
    # the frozen full-field corpus, reused by reference.
    rows = []
    for dataset in sorted(
            (DIAG / "electricbubble-fullfield" / "corpus").iterdir()):
        ds = dataset.name
        profile = "gray" if ds.endswith("gray") else "mono"
        raw = json.loads((dataset / "comparison.json").read_text())[
            "results"]
        scaled = json.loads(
            (OUT / "extended" / ds / "comparison.json").read_text())[
            "results"]
        raw_map = {r["pair"]: r for r in raw}
        scaled_map = {r["pair"]: r for r in scaled}
        dsobj = load_yi_dataset(str(CAPTURES / f"{ds}.json"), profile)
        for pair in EXTENDED_PAIRS:
            metric = YI.metric_step(dsobj, ord(pair[0]), ord(pair[1]))
            rows.append({"dataset": ds,
                         **analyze_pair(raw_map[pair], scaled_map[pair],
                                        metric)})
    agg = {"pair_cases": len(rows),
           "shared_steps": sum(r["shared_steps"] for r in rows),
           "raw_extrema": sum(r["raw_extrema"] for r in rows),
           "scaled_extrema": sum(r["scaled_extrema"] for r in rows),
           "scaled_interior_targets": sum(
               1 for r in rows if r["scaled_attain"]["interior"]),
           "raw_interior_targets": sum(
               1 for r in rows if r["raw_attain"]["interior"])}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"aggregate": agg, "rows": rows},
                                   indent=1) + "\n")
    return {"aggregate": agg}


def dtype_check():
    # float64 primary versus float32 diagnostic on the core: curve
    # agreement, identical walk terminals and identical invalid sets.
    rows = []
    for ds in CORE_DATASETS:
        a = json.loads((OUT / "core" / ds / "comparison.json")
                       .read_text())["results"]
        b = json.loads((OUT / "core-float32" / ds / "comparison.json")
                       .read_text())["results"]
        for ra, rb in zip(a, b):
            ca = {c["step"]: c for c in ra["source_curve"]}
            cb = {c["step"]: c for c in rb["source_curve"]}
            deltas = [abs(ca[s]["interaction"] - cb[s]["interaction"])
                      for s in ca if ca[s]["valid"] and cb[s]["valid"]]
            inva = sorted(s for s in ca if not ca[s]["valid"])
            invb = sorted(s for s in cb if not cb[s]["valid"])
            rows.append({"dataset": ds, "pair": ra["pair"],
                         "max_abs_delta": max(deltas) if deltas else None,
                         "walk_terminal_equal":
                         ra["source_walk"]["terminalStep"]
                         == rb["source_walk"]["terminalStep"],
                         "invalid_sets_equal": inva == invb})
    (OUT / "dtype.json").write_text(json.dumps(rows, indent=1) + "\n")
    worst = max(r["max_abs_delta"] or 0 for r in rows)
    return {"pairs": len(rows),
            "worst_curve_delta": worst,
            "all_terminals_equal": all(r["walk_terminal_equal"]
                                       for r in rows),
            "all_invalid_equal": all(r["invalid_sets_equal"]
                                     for r in rows)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "inputs.json").write_text(json.dumps({
        "scale_module": sha(S.__file__),
        "port_module": sha(F.__file__),
        "proxy_sha256": YI.IMPLEMENTATION_SHA256,
        "start": json.loads((DIAG / "electricbubble-scale-orchestration"
                             / "start.json").read_text())}, indent=1)
        + "\n")
    synth = synth_evidence(OUT / "synthetics")
    core = paired_core(OUT / "core" / "paired.json")
    ext = paired_extended(OUT / "extended" / "paired.json")
    dt = dtype_check()
    print(json.dumps({"core": core["aggregate"],
                      "extended": ext["aggregate"],
                      "dtype": dt}, indent=1))
    print(json.dumps({"synthetics_identity_max_delta":
                      synth["identity"]["max_abs_delta"],
                      "phase_both_shift_max":
                      synth["phase"]["both_shift_max_abs_delta"]},
                     indent=1))


if __name__ == "__main__":
    main()
