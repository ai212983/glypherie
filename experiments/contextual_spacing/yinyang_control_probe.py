"""YinYang-only control-design probe (read-only over shipped v3 bytes).

Compares three narrowly differentiated paths toward a useful visual
adjustment governed specifically by YinYang-derived geometry:
  A: direct model-parameter tuning (cohesion/reach/falloff grid behavior);
  B: method-owned Source-to-YinYang strength blend toward a FIXED
     YinYang-computed endpoint (per-pair rounding vs fractional-pen draw);
  C: smallest source-backed oriented/ratio field step (synthetic only).

Reads shipped v3 tables/captures/boot; writes one JSON report. No UI,
scorer, dataset, or model change. Comments note provenance only.
"""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V3 = ROOT / "out" / "diagnostics" / "contextual-spacing" / "yinyangfit-interactive-v3"
SITE = V3 / "site"
DATA = SITE / "data"
CAPTURES = V3 / "captures"
OUTDIR = ROOT / "out" / "diagnostics" / "contextual-spacing" / "yinyang-control-design"

COHESION_GRID = [0.4, 0.6, 0.8, 1.0, 1.1, 1.2, 1.4, 1.6, 1.8]
TIE_TOL = 1e-9
# Fixed YinYang endpoint: shipped default combo c74 (cohesion 1.1,
# reach 2.0, falloff 2.0). Endpoint quality is assessed separately;
# this probe measures control behavior for a fixed endpoint.
ENDPOINT = {"cohesion": 1.1, "feature_scale": 2.0, "proximity_falloff": 2.0}
O_GRID = [round(i * 0.05, 2) for i in range(21)]


def pixel_round(value):
    # Matches yinyangfit_interactive.pixel_round and the native surface
    # invariant (pen+32).div_euclid(64) for nonneg pens.
    if value >= 0:
        return math.floor(value + 0.5)
    return math.ceil(value - 0.5)


def load_table(label):
    # Shipped v3 payload: window.YY_TABLES['label'] = {...};
    text = (DATA / f"{label}.js").read_text()
    start = text.index("= {", text.index(f"YY_TABLES['{label}']")) + 2
    return json.loads(text[start:].strip().rstrip().rstrip(";"))


def choose(steps, inters, oks, target, metric):
    # Mirror of choose_from_costs: the caller passes cost = |interaction -
    # cohesion|, minimized over valid steps with metric-near tie-break.
    scored = [(s, abs(c - target)) for s, c, ok in zip(steps, inters, oks)
              if ok and c is not None and math.isfinite(c)]
    if not scored:
        return None
    best = min(c for _, c in scored)
    mini = [s for s, c in scored if c <= best + TIE_TOL]
    return min(mini, key=lambda s: (abs(s - metric), s - metric))


def sf_index(table):
    # Default reach/falloff (2.0, 2.0) position in the shipped sf grid.
    for i, (r, f) in enumerate(table["sf"]):
        if r == 2.0 and f == 2.0:
            return i
    raise ValueError("default sf combo missing")


def load_capture(label):
    # Read-only delivered advances/adjustments for Source-identity math.
    cap = json.loads((CAPTURES / f"{label}.json").read_text())
    if "glyphs" in cap and isinstance(cap["glyphs"], list) and cap.get("schema_version", "").startswith("contextual-spacing-capture"):
        # Mono capture: finalized whole-pixel advances, px adjustments.
        adv, adj = {}, {}
        for g in cap["glyphs"]:
            adv[g["codepoint"]] = float(g["finalized_advance_px"])
        for p in cap.get("metric_pairs_on", []):
            adj[(p["left"], p["right"])] = float(p["adjustment_px"])
        return {"profile": "mono", "adv": adv, "adj": adj}
    font = cap["font"]
    adv = {g["codepoint"]: float(g["advance_26_6"]) / 64.0 for g in font["glyphs"]}
    ker = font.get("kerning", [])
    adj = {(p["left"], p["right"]): float(p["adjustment_26_6"]) / 64.0
           for p in ker} if isinstance(ker, list) else {}
    return {"profile": "gray", "adv": adv, "adj": adj}


def source_origins(cap, text):
    # Fractional-pen Source draws (Gray-exact; Mono advances are whole so
    # this also equals per-pair-rounded sums there).
    cps = [ord(c) for c in text]
    origins, pen = [0], 0.0
    for left, right in zip(cps, cps[1:]):
        if left == 32 or right == 32 or left not in cap["adv"]:
            pen += float(cap["adv"].get(left, 0.0)) + float(cap["adj"].get((left, right), 0.0))
        else:
            pen += float(cap["adv"][left]) + float(cap["adj"].get((left, right), 0.0))
        origins.append(pixel_round(pen))
    return origins


def line_gaps(table, cap, text):
    # Per-gap blend inputs. Pairs absent from the shipped table keep
    # metric (delta 0); spaces keep metric; endpoint deltas come only
    # from the YinYang-derived table (never another method).
    gaps = []
    cps = [ord(c) for c in text]
    for left, right in zip(cps, cps[1:]):
        pair = chr(left) + chr(right) if left != 32 and right != 32 else None
        m_frac = float(cap["adv"].get(left, 0.0)) + float(cap["adj"].get((left, right), 0.0))
        m_round = pixel_round(m_frac)
        entry = table["pairs"].get(pair) if pair else None
        if entry is None:
            gaps.append({"pair": pair, "m_frac": m_frac, "m_round": m_round,
                         "d1": m_round, "delta": 0, "guard": False})
            continue
        geo = entry["geo"][str(sf_index(table))]
        d1 = choose(entry["steps"], geo["inter"], geo["ok"], ENDPOINT["cohesion"], entry["metric"])
        if d1 is None:
            # Endpoint has no valid step: retain metric, record fallback.
            gaps.append({"pair": pair, "m_frac": m_frac, "m_round": m_round,
                         "d1": m_round, "delta": 0, "guard": False,
                         "endpoint_fallback": True})
            continue
        gaps.append({"pair": pair, "m_frac": m_frac, "m_round": m_round,
                     "d1": d1, "delta": d1 - m_round, "guard": False,
                     "steps": entry["steps"], "ok": geo["ok"]})
    return gaps


def blend_origins(gaps, source, policy, strength, bypass=True):
    # P1 per-pair-round: each gap rounds its own blended step, then whole
    # pixels accumulate (representable in maintained integer-pen layout).
    # P2 fractional-pen: continuous blended steps accumulate fractionally,
    # each glyph rounds at draw (Gray-like; NOT representable in the
    # maintained whole-pixel advance/adjustment API -- experimental only).
    # o=0 is an explicit bypass returning Source exactly.
    if strength == 0 and bypass:
        return list(source)
    if policy == "per_pair":
        # Origins accumulate blended rounded steps from the Source start.
        origins = [source[0]]
        for gap in gaps:
            step = pixel_round(gap["m_frac"] + strength * gap["delta"])
            if "steps" in gap and (step not in gap["steps"] or
                                   not gap["ok"][gap["steps"].index(step)]):
                gap["guard"] = True
                valid = [s for s, ok in zip(gap["steps"], gap["ok"]) if ok]
                step = min(valid, key=lambda s: (abs(s - step), s))
            origins.append(origins[-1] + step)
        return origins
    pen = 0.0
    # Pen is relative to line start; Source fractional pens give absolute.
    pens = [0.0]
    for gap in gaps:
        pens.append(pens[-1] + gap["m_frac"] + strength * gap["delta"])
    base = source[0]
    return [base + pixel_round(p) - pixel_round(0.0) for p in pens]


def main():
    boot = json.loads((SITE / "boot.json").read_text())
    labels = sorted({p["label"] for c in boot["cases"] for p in c["profiles"].values()})
    tables = {label: load_table(label) for label in labels}
    caps = {label: load_capture(label) for label in labels}

    # ---- Path A: direct parameter tuning over the shipped grid ----
    path_a = {"pairs": 0, "extrema": 0, "skips": 0, "reversals": 0,
              "sf_sensitive": 0, "skip_examples": [], "reverse_examples": []}
    for label, table in tables.items():
        sfi = sf_index(table)
        for pair, entry in table["pairs"].items():
            path_a["pairs"] += 1
            inter = entry["geo"][str(sfi)]["inter"]
            ok = entry["geo"][str(sfi)]["ok"]
            vals = [c for c, v in zip(inter, ok) if v and math.isfinite(c)]
            for i in range(1, len(vals) - 1):
                if (vals[i] - vals[i - 1]) * (vals[i + 1] - vals[i]) < 0:
                    path_a["extrema"] += 1
                    break
            path = [choose(entry["steps"], entry["geo"][str(sfi)]["inter"],
                           entry["geo"][str(sfi)]["ok"], c, entry["metric"])
                    for c in COHESION_GRID]
            if any(v is None for v in path):
                path_a["no_path"] = path_a.get("no_path", 0) + 1
                continue
            for a, b in zip(path, path[1:]):
                if abs(b - a) > 1:
                    path_a["skips"] += 1
                    if len(path_a["skip_examples"]) < 5:
                        path_a["skip_examples"].append(
                            {"label": label, "pair": pair, "path": path})
                    break
            dirs = [1 if b > a else -1 if b < a else 0
                    for a, b in zip(path, path[1:])]
            nz = [d for d in dirs if d]
            if any(a != b for a, b in zip(nz, nz[1:])):
                path_a["reversals"] += 1
                if len(path_a["reverse_examples"]) < 5:
                    path_a["reverse_examples"].append(
                        {"label": label, "pair": pair, "path": path})
            base = choose(entry["steps"], entry["geo"][str(sfi)]["inter"],
                          entry["geo"][str(sfi)]["ok"], 1.1, entry["metric"])
            others = [choose(entry["steps"], entry["geo"][str(i)]["inter"],
                             entry["geo"][str(i)]["ok"], 1.1, entry["metric"])
                      for i in range(len(table["sf"]))]
            if base is None or any(o is None or o != base for o in others):
                path_a["sf_sensitive"] += 1

    # ---- Path B: fixed-endpoint strength blend ----
    lines, path_b = [], {"o_grid": O_GRID, "cases": {}}
    for case in boot["cases"]:
        for profile, ref in case["profiles"].items():
            label = ref["label"]
            table, cap = tables[label], caps[label]
            for text in case["text"].split("\n"):
                gaps = line_gaps(table, cap, text)
                src = source_origins(cap, text)
                p1 = [blend_origins(gaps, src, "per_pair", o) for o in O_GRID]
                p2 = [blend_origins(gaps, src, "fractional_pen", o) for o in O_GRID]
                totals1 = [o_[-1] - o_[0] for o_ in p1]
                totals2 = [o_[-1] - o_[0] for o_ in p2]
                adj1 = [abs(b - a) for a, b in zip(totals1, totals1[1:])]
                adj2 = [abs(b - a) for a, b in zip(totals2, totals2[1:])]
                lines.append({
                    "label": label, "text": text[:48],
                    "n_gaps": len(gaps),
                    "n_correct": sum(1 for g in gaps if g["delta"]),
                    "deltas": sorted({g["delta"] for g in gaps if g["delta"]}),
                    "p1_max_adjacent": max(adj1) if adj1 else 0,
                    "p2_max_adjacent": max(adj2) if adj2 else 0,
                    "p1_total": totals1[-1] - totals1[0],
                    "p2_total": totals2[-1] - totals2[0],
                    "p1_zero_is_source": p1[0] == src,
                    "p2_zero_is_source": p2[0] == src,
                    "p1_full_is_endpoint": p1[-1] == blend_origins(
                        line_gaps(table, cap, text), src, "per_pair", 1.0),
                    "gray_p1_zero_resid": (max(abs(a - b) for a, b in zip(p1[0], src))
                                           if profile == "gray" else 0),
                    "gray_p2_full_vs_p1": (max(abs(a - b) for a, b in zip(p2[-1], p1[-1]))
                                           if profile == "gray" else 0),
                    "gray_p1_snap_above_zero": (
                        max(abs(a - b) for a, b in zip(
                            blend_origins(gaps, src, "per_pair", 0.0, bypass=False), src))
                        if profile == "gray" else 0),
                    "guard_hits": sum(1 for g in gaps if g["guard"]),
                    "p1_origins_full": p1[-1],
                    "p2_origins_full": p2[-1],
                    "src_origins": src,
                })
    # Flip-threshold histograms on a fine o grid (0.01): per-pair first
    # change for P1 vs per-boundary first change for P2, roboto-16 both
    # profiles as the worked example.
    flip_detail = {}
    for profile in ("mono", "gray"):
        label = f"roboto-16-{profile}"
        table, cap = tables[label], caps[label]
        case = next(c for c in boot["cases"] if c["id"] == "roboto-16")
        fine = [round(i * 0.01, 2) for i in range(101)]
        p1_flips, p2_flips = [], []
        for text in case["text"].split("\n"):
            gaps = line_gaps(table, cap, text)
            src = source_origins(cap, text)
            prev1 = blend_origins(gaps, src, "per_pair", 0.0)
            prev2 = blend_origins(gaps, src, "fractional_pen", 0.0)
            for o in fine[1:]:
                cur1 = blend_origins(gaps, src, "per_pair", o)
                cur2 = blend_origins(gaps, src, "fractional_pen", o)
                p1_flips.append(sum(1 for a, b in zip(cur1, prev1) if a != b))
                p2_flips.append(sum(1 for a, b in zip(cur2, prev2) if a != b))
                prev1, prev2 = cur1, cur2
        hot1 = max(range(100), key=lambda i: p1_flips[i])
        hot2 = max(range(100), key=lambda i: p2_flips[i])
        flip_detail[profile] = {
            "p1_total_events": sum(p1_flips), "p2_total_events": sum(p2_flips),
            "p1_hottest_bin": (fine[hot1 + 1], p1_flips[hot1]),
            "p2_hottest_bin": (fine[hot2 + 1], p2_flips[hot2]),
            "p1_bins_over_10": sum(1 for v in p1_flips if v >= 10),
            "p2_bins_over_10": sum(1 for v in p2_flips if v >= 10),
        }
    path_b["flip_detail_roboto16"] = flip_detail
    widen = sum(1 for ln in lines for d in ln["deltas"] if d > 0)
    narrow = sum(1 for ln in lines for d in ln["deltas"] if d < 0)
    path_b["direction"] = {"widening_pair_kinds": widen,
                           "narrowing_pair_kinds": narrow}
    deltas_all = [d for ln in lines for d in ln["deltas"]]
    path_b["lines"] = lines
    path_b["summary"] = {
        "n_lines": len(lines),
        "worst_p1_adjacent": max(ln["p1_max_adjacent"] for ln in lines),
        "worst_p2_adjacent": max(ln["p2_max_adjacent"] for ln in lines),
        "lines_with_guard": sum(1 for ln in lines if ln["guard_hits"]),
        "delta_values": sorted(set(deltas_all)),
        "gray_max_p1_zero_resid": max((ln["gray_p1_zero_resid"] for ln in lines), default=0),
        "gray_max_p1_snap": max((ln["gray_p1_snap_above_zero"] for ln in lines), default=0),
        "gray_max_p2_full_vs_p1": max((ln["gray_p2_full_vs_p1"] for ln in lines), default=0),
        "all_p1_zero_source": all(ln["p1_zero_is_source"] for ln in lines),
        "all_p2_zero_source": all(ln["p2_zero_is_source"] for ln in lines),
    }

    # ---- Path C: smallest source-backed radial-ratio field step ----
    # Manuscript radial factors r^-q, r^-(q+1), q~2 (direct approximation).
    # Declared guards only: finite center value, finite support radius,
    # zero-denominator mask. Synthetic bars; field-only, no cost invented.
    import numpy as np
    q = 2.0
    R = 4  # small support so a 15-row canvas keeps a valid interior

    def kernel(power):
        k = np.zeros((2 * R + 1, 2 * R + 1))
        for y in range(-R, R + 1):
            for x in range(-R, R + 1):
                r = math.hypot(x, y)
                k[y + R, x + R] = 1.0 / (1.0 + r ** power) if r == 0 else r ** (-power)
        k[R, R] = 1.0  # declared finite-center guard (proxy regularization)
        return k / k.sum()

    def correlate(img, k):
        # Brute-force correlation over the valid interior (no padding
        # policy intrudes; borders are excluded, not wrapped).
        H, W = img.shape
        out = np.full_like(img, np.nan)
        for y in range(R, H - R):
            for x in range(R, W - R):
                out[y, x] = float((img[y - R:y + R + 1, x - R:x + R + 1] * k).sum())
        return out

    k1, k2 = kernel(q), kernel(q + 1.0)
    rows = []
    for gap in (4, 6, 8):
        img = np.zeros((15, 40))
        img[:, 12:15] = 1.0
        img[:, 15 + gap:18 + gap] = 1.0
        f1, f2 = correlate(img, k1), correlate(img, k2)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(np.abs(f2) > 1e-12, f1 / f2, np.nan)
        mid = ratio[R:-R, 12:22]
        rows.append({"gap": gap,
                     "finite_frac": float(np.isfinite(ratio[R:-R, R:-R]).mean()),
                     "mid_range": [float(np.nanmin(mid)), float(np.nanmax(mid))],
                     "mid_varies": bool(np.nanmax(mid) - np.nanmin(mid) > 1e-9)})
    path_c = {"q": q, "support_radius": R,
              "guards": ["finite center k=1.0", f"support radius {R}",
                         "zero-denominator -> NaN mask"],
              "gaps": rows,
              "note": "Field-only: ratio varies finitely on a synthetic gap; "
                      "no aggregation, normalization, cross-pair selection, "
                      "or calibration is supplied (all missing per audit)."}

    OUTDIR.mkdir(parents=True, exist_ok=True)
    report = {"endpoint": ENDPOINT, "cohesion_grid": COHESION_GRID,
              "path_a": path_a, "path_b_summary": path_b["summary"],
              "path_b_flip_detail_roboto16": path_b["flip_detail_roboto16"],
              "path_b_direction": path_b["direction"],
              "path_b_lines": [{k: v for k, v in ln.items()
                                if k not in ("p1_origins_full", "p2_origins_full",
                                             "src_origins")} for ln in lines],
              "path_c": path_c}
    (OUTDIR / "probe.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(path_a, indent=1)[:1200])
    print(json.dumps(path_b["summary"], indent=1))
    print(json.dumps(path_c, indent=1)[:800])


if __name__ == "__main__":
    main()
