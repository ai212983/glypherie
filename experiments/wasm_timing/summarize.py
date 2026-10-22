"""Retain all process-level ratios; bootstrap fresh-process means of paired log ratios."""
import json
import math
import pathlib
import random
import statistics

root = pathlib.Path(__file__).resolve().parents[2]
out = root / "out/diagnostics/wasm-timing-investigation"
groups = {}
sessions = []
for path in sorted(out.glob("*.json")):
    data = json.loads(path.read_text())
    if "rows" not in data or "config" not in data:
        continue
    config = data["config"]
    engine = "browser" if path.name.startswith("browser-") else "node"
    for family in ["Roboto", "SourceSans3"]:
        for case in ["pangram", "disabled", "stress"]:
            rows = [r for r in data["rows"] if r["family"] == family and r["caseName"] == case]
            if not rows:
                continue
            medians = [statistics.median(r["ms"] for r in rows if r["label"] == label) for label in [0, 1]]
            pairs = {}
            for row in rows:
                pairs.setdefault(row["repeat"], {})[row["label"]] = row["ms"]
            log_ratio = statistics.mean(math.log(pair[1] / pair[0]) for pair in pairs.values())
            key = (engine, config["tier"], config["comparison"], family, case)
            groups.setdefault(key, []).append(log_ratio)
            sessions.append({"file": path.name, "family": family, "case": case,
                             "medians_ms": medians, "reduction_percent": 100 * (1 - medians[1] / medians[0]),
                             "mean_paired_log_ratio": log_ratio})

rng = random.Random(20261022)
summary = []
for key, logs in sorted(groups.items()):
    samples = sorted(statistics.mean(rng.choices(logs, k=len(logs))) for _ in range(10000))
    summary.append({"engine": key[0], "tier": key[1], "comparison": key[2], "family": key[3], "case": key[4],
                    "sessions": len(logs), "reduction_percent": 100 * (1 - math.exp(statistics.mean(logs))),
                    "interval_95_percent": [100 * (1 - math.exp(samples[9749])), 100 * (1 - math.exp(samples[249]))],
                    "session_reductions_percent": [100 * (1 - math.exp(x)) for x in logs]})
(out / "summary.json").write_text(json.dumps({"groups": summary, "sessions": sessions}, indent=2) + "\n")
for row in summary:
    print(row["engine"], row["tier"], row["comparison"], row["family"], row["case"], row["sessions"],
          round(row["reduction_percent"], 2), [round(x, 2) for x in row["interval_95_percent"]])
