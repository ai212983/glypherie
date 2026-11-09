"""True winner/second-best separation for Class-L corpus curves.

For each case and target C*: over eligible steps (valid, non-abstained,
finite g), deviations d = |g - C*|. The tied set uses TIE-v2's own
rule (dev <= mstar + 1e-9 * max(1, mstar), per score.rs tie_set), not
bitwise score equality.
Separation = (min deviation outside the tied set) - (winner deviation);
0 iff a non-tied step is exactly as close (symmetric curve) or a tie
absorbs the runner-up. Roughness = max adjacent-step |dg| over eligible
steps in step order (a fragility comparator, not a stability claim).

Reads the frozen corpus run_Lmultiscale.json; writes runtime/separation.json.
"""
import json
import sys

REPO = sys.argv[1] if len(sys.argv) > 1 else "."
BASE = (REPO + "/out/diagnostics/contextual-spacing"
        "/yinyang-normalization-repair")
CORPUS = json.load(open(BASE + "/corpus/run_Lmultiscale.json"))
TARGETS = {"seed": 0.4697315871728616, "high": 8.0}
# seed is the exact dev eligible-notebook p50 (rounded "0.47" in prose).
# Minimum separation is target-decimal-sensitive: rounded 0.47 gives
# min 4.99e-04, 0.4697 gives 1.01e-04; the median barely moves.

out_cases = []
for ds, pairs in CORPUS["cases"].items():
    for pair, case in pairs.items():
        elig = [(s["step"], s["nb_g"]) for s in case["steps"]
                if s.get("valid") and not s.get("nb_abstain")
                and isinstance(s.get("nb_g"), float)]
        if not elig:
            continue
        gs = [g for _, g in elig]
        entry = {"dataset": ds, "pair": pair, "n_eligible": len(elig)}
        adjacent = [abs(b - a) for a, b in zip(gs, gs[1:])]
        entry["roughness_max_adjacent_dg"] = max(adjacent) if adjacent else 0.0
        for tname, cstar in TARGETS.items():
            devs = sorted((abs(g - cstar), g, st) for st, g in elig)
            d1 = devs[0][0]
            tol = 1e-9 * max(1.0, d1)
            tied = [st for d, g, st in devs if d <= d1 + tol]
            rest = [(d, g, st) for d, g, st in devs if d > d1 + tol]
            d2 = rest[0][0] if rest else d1
            entry[tname] = {"winner_step": devs[0][2], "winner_g": devs[0][1],
                            "winner_dev": d1, "n_tied": len(tied),
                            "tied_steps": tied,
                            "second_dev": d2, "separation": d2 - d1}
        out_cases.append(entry)

summary = {}
for tname in TARGETS:
    seps = sorted(c[tname]["separation"] for c in out_cases)
    ties = sum(1 for c in out_cases if c[tname]["n_tied"] > 1)
    zeros = sum(1 for c in out_cases if c[tname]["separation"] == 0.0)
    rough = sum(1 for c in out_cases
                if c["roughness_max_adjacent_dg"] > c[tname]["separation"])
    n = len(seps)
    summary[tname] = {"n": n, "min": seps[0],
                      "median": seps[n // 2] if n % 2 else
                      0.5 * (seps[n // 2 - 1] + seps[n // 2]),
                      "max": seps[-1], "n_tied_gt1": ties,
                      "n_zero_separation": zeros,
                      "n_roughness_gt_separation": rough}

json.dump({"targets": TARGETS, "cases": out_cases, "summary": summary},
          open(BASE + "/runtime/separation.json", "w"), indent=1)
print(json.dumps(summary, indent=1))
