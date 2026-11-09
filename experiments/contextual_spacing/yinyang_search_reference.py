#!/usr/bin/env python3
"""Independent wider-domain reference for search-v1 (implementation evidence).

Scores the reviewer's full padded interval per pair (stdlib oracle rule)
with the frozen scorer core, classifies every step by the declared
ordered-letter rule, and checks the shipped domain curves against the wider
scan on their shared steps. Multiprocessing over datasets; deterministic
(sorted pairs, no randomness).

Reads the shipped tables (rebuild output) and the reviewer's stdlib oracle;
writes per-dataset records plus a summary under
out/diagnostics/contextual-spacing/yinyang-geometry-search/implementation/.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "apps/web/scripts/landing-samples"))
sys.path.insert(0, str(REPO / "out/diagnostics/contextual-spacing"
                       "/yinyang-geometry-search/search-review"))

import yinyangfit_interactive as yy
import yinyangfit_interactive_v3 as v3
import geometry_domain_oracle as oracle

SITE = REPO / "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3"
CSTARS = [0.0, 4.0, 16.0, 128.0]
NOVEL = ["qj", "ya", "ef", "fj", "qu", "zx"]


def ink_spans(cells, left, right):
    out = {}
    for tag, cp in (("l", left), ("r", right)):
        cell = cells[cp]
        ox = math.trunc(cell["left"])
        xs = [ox + col for row in range(cell["height"])
              for col in range(cell["width"])
              if cell["cover"][row * cell["width"] + col] > 0.0]
        out[tag] = (min(xs), max(xs)) if xs else None
    return out


def check_pair(store, dataset, shipped, name, fresh, label):
    left, right = ord(name[0]), ord(name[1])
    cells = dataset["cells"]
    metric = yy.metric_step(dataset, left, right)
    bounds, reason = v3.search_domain(dataset, left, right, store.pad)
    interval = oracle.padded_interval(cells[left], cells[right])
    rec = {"pair": name, "metric": metric}
    if interval is None:
        rec["oracle_interval"] = None
        rec["domain"] = None
        rec["domain_reason"] = reason
        assert bounds is None, f"{name}: oracle empty but search found domain"
        assert reason in ("blank_glyph_no_ink", "row_bands_disjoint"), name
        return rec
    assert bounds is not None, f"{name}: search empty on oracle {interval}"
    lo, hi = bounds
    rec["oracle_interval"] = list(interval)
    rec["domain"] = [lo, hi]
    # Forward ordered restriction (search-v2): our lo excludes the
    # reviewer's reversed-order component and every non-forward step; our
    # hi matches the support-exhaustion end exactly.
    assert lo >= interval[0], f"{name}: domain lo below padded interval"
    assert hi == interval[1], f"{name}: domain hi != padded end"
    assert lo >= 1, f"{name}: domain admits non-forward step"
    rec["excluded_reversed"] = lo - interval[0]
    spans = ink_spans(cells, left, right)
    # Every excluded step is rejected by the order predicate: below 1 it
    # violates forward pen order; from 1 up to the ink bound the right ink
    # stays wholly left of the left ink (reversed order).
    for step in range(interval[0], lo):
        if step < 1:
            rec["excluded_nonforward"] = rec.get("excluded_nonforward", 0) + 1
            continue
        assert spans["r"][1] + step < spans["l"][0], (name, step)
    wide_steps = list(range(interval[0], interval[1] + 1))
    # Bounded halo probe: a few steps past the support-exhaustion end must
    # carry no shared support (both == 0), proving hi is tight per pair.
    halo_steps = list(range(hi + 1, hi + 4))
    wide = v3.score_steps(store, left, right, wide_steps + halo_steps)
    domain_steps = list(range(lo, hi + 1))
    for s, ok, both in zip(halo_steps,
                            wide["geo"]["ok"][-len(halo_steps):],
                            wide["geo"]["both"][-len(halo_steps):]):
        assert both == 0, (label, name, s, ok, both)
    rec["halo_both_zero"] = True
    # Shared-step identity between the wider scan and the domain curves.
    table = {"metric": metric, "steps": domain_steps, "geo": {
        k: [v for s, v in zip(wide_steps, wide["geo"][k]) if lo <= s <= hi]
        for k in wide["geo"]}}
    assert fresh["steps"] == domain_steps, name
    maxdiff = 0.0
    for key in ("inter", "raw", "fsh", "rfsh"):
        for have, want in zip(table["geo"][key], fresh["geo"][key]):
            if have is None and want is None:
                continue
            assert (have is None) == (want is None), (name, key)
            denom = max(1.0, abs(want))
            maxdiff = max(maxdiff, abs(have - want) / denom)
            assert abs(have - want) / denom <= 1e-9, (name, key, have, want)
    for key in ("ok", "both", "abst", "why", "fa", "co"):
        assert table["geo"][key] == fresh["geo"][key], (name, key)
    rec["shared_step_maxreldiff"] = maxdiff
    # Shipped bytes reproduce the fresh domain curves: exact steps, search
    # identity and validity/support/overlap, G2 within the frozen 1e-9
    # relative bound (cross-process last-ulp nondeterminism from threaded
    # BLAS reductions is expected; in-process bitwise holds in parity_spots).
    if shipped is not None and name in shipped:
        st = shipped[name]
        assert st["metric"] == metric, (name, "source baseline changed")
        assert st["steps"] == domain_steps, (name, "shipped steps")
        assert st["search"]["lo"] == lo and st["search"]["hi"] == hi, name
        for key in ("inter", "raw", "fsh", "rfsh"):
            for have, want in zip(st["geo"][key], fresh["geo"][key]):
                if have is None and want is None:
                    continue
                assert (have is not None) and (want is not None), \
                    (label, name, key)
                denom = max(1.0, abs(want))
                assert abs(have - want) / denom <= 1e-9, \
                    (label, name, key, have, want)
        for key in ("ok", "both", "abst", "why", "fa", "co"):
            assert st["geo"][key] == fresh["geo"][key], \
                (label, name, key)
        rec["shipped_maxreldiff"] = max(
            abs(h - w) / max(1.0, abs(w))
            for key in ("inter", "raw", "fsh", "rfsh")
            for h, w in zip(st["geo"][key], fresh["geo"][key])
            if h is not None and w is not None)
    geo = fresh["geo"]
    n_valid = sum(1 for v in geo["ok"] if v)
    n_abst = sum(1 for v in geo["abst"] if v)
    n_holes = sum(1 for ok in geo["ok"] if not ok)
    rec.update({"n_steps": len(domain_steps), "n_valid": n_valid,
                "n_abstain": n_abst, "n_holes": n_holes})
    # Selection at probe targets: supported-or-fallback, never abstain wins.
    picks = {}
    for cstar in CSTARS:
        chosen, detail = v3.derive_choice(fresh, cstar)
        assert chosen >= 1, (name, cstar, chosen, detail["reason"])
        if not detail["fallback"]:
            idx = domain_steps.index(chosen)
            assert geo["ok"][idx] and not geo["abst"][idx], (name, cstar)
        else:
            assert chosen == metric, (name, cstar)
        picks[str(cstar)] = {"chosen": chosen,
                             "fallback": detail["fallback"],
                             "reason": detail["reason"],
                             "target_outside": detail["target_outside"]}
    rec["picks"] = picks
    return rec


def layout_monotonicity(store, tables, text, label):
    """Forward-order gate over the sample text (search-v2).

    Layouts accumulate chosen steps per line. Every letter gap must be a
    strictly positive advance and every origin strictly greater than its
    predecessor — no backward or equal moves at any probe target. A
    violation fails the run: forward pen order is admissibility, not fit.
    """
    out = {}
    for cstar in CSTARS:
        neg, back, gaps = 0, 0, 0
        for line in text.split("\n"):
            origins = [0]
            for a, b in zip(line, line[1:]):
                if a == " " or b == " ":
                    step = yy.metric_step(store.dataset, ord(a), ord(b))
                else:
                    step, _ = v3.derive_choice(tables[a + b], cstar)
                gaps += 1
                assert step >= 1, (label, cstar, a + b, step)
                if step < 1:
                    neg += 1
                origins.append(origins[-1] + step)
                if origins[-1] <= origins[-2]:
                    back += 1
        assert neg == 0 and back == 0, (label, cstar, neg, back, gaps)
        out[str(cstar)] = {"negative_steps": neg, "backward_moves": back,
                           "gaps": gaps}
    return out


def check_dataset(label, tables_dir, texts):
    case_id, profile = label.rsplit("-", 1)
    dataset = v3.load_case_dataset(case_id, profile, SITE / "captures")
    shipped = None
    table_path = tables_dir / f"{label}.js"
    if table_path.is_file():
        raw = table_path.read_text()
        anchor = raw.index("window.YY_TABLES[")
        start = raw.index("{", raw.index("=", anchor))
        shipped = json.loads(raw[start:].rstrip().rstrip(";"))["pairs"]
    store = v3.GlyphFields(dataset)
    cells = dataset["cells"]
    repertoire = set(cells)
    names = sorted({p for p in (shipped or {})}
                   | {n for n in NOVEL
                      if ord(n[0]) in repertoire and ord(n[1]) in repertoire})
    out = {"label": label, "pairs": []}
    tables = {}
    for name in names:
        left, right = ord(name[0]), ord(name[1])
        fresh = v3.score_pair_curves(store, left, right)
        tables[name] = fresh
        rec = {"label": label}
        out["pairs"].append(check_pair(store, dataset, shipped, name, fresh,
                                       label))
    # Sample-text pairs always resolve (they ship, but stay safe offline).
    for line in texts[label].split("\n"):
        for a, b in zip(line, line[1:]):
            if a == " " or b == " " or a + b in tables:
                continue
            tables[a + b] = v3.score_pair_curves(
                store, ord(a), ord(b))
    out["layouts"] = layout_monotonicity(store, tables, texts[label], label)
    return out


def load_texts():
    import generate as landing_generate
    catalogue = json.loads(
        (REPO / "apps/web/scripts/landing-samples/main-page.json")
        .read_text())
    texts = {}
    for entry in catalogue:
        text = entry.get("text") or landing_generate.DEFAULT_TEXT
        for profile in ("mono", "gray"):
            texts[f"{entry['id']}-{profile}"] = text
    return texts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tables", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--only", action="append", default=None)
    args = parser.parse_args()
    labels = sorted(p.stem for p in args.tables.glob("*.js"))
    if args.only:
        labels = [l for l in labels if l in args.only]
    texts = load_texts()
    import multiprocessing as mp
    with mp.Pool(args.jobs) as pool:
        results = pool.starmap(check_dataset,
                               [(l, args.tables, texts) for l in labels])
    summary = {"labels": labels, "datasets": len(results),
               "pairs": sum(len(r["pairs"]) for r in results),
               "policy": v3.SEARCH_POLICY,
               "oracle": "geometry_domain_oracle"}
    args.output.mkdir(parents=True, exist_ok=False)
    for rec in results:
        (args.output / f"{rec['label']}.json").write_text(
            json.dumps(rec, separators=(",", ":")))
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
