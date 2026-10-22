"""Summarize all fresh-browser sessions without dropping unfavorable runs."""
import collections
import json
import math
import os
import pathlib
import random
import statistics as stats

root = pathlib.Path(__file__).resolve().parents[2]
output = pathlib.Path(os.environ.get("SUMMARY_OUTPUT_DIR", root / "out/diagnostics/font-identity-optimization"))
suites = os.environ.get("SUMMARY_SUITES", "fixed-controls,fixed,varied-controls,varied,combined").split(",")
groups = collections.defaultdict(list)
sessions = []
renders = measured = browser_sessions = 0
for suite in suites:
    for path in sorted((output / suite).glob("browser-*.json")):
        browser_sessions += 1
        data = json.loads(path.read_text())
        measured += len(data["rows"])
        renders += len(data["rows"]) + len(data["cold"])
        for family in ["Roboto", "SourceSans3"]:
            for case in sorted({row["caseName"] for row in data["rows"]}):
                rows = [r for r in data["rows"] if r["family"] == family and r["caseName"] == case]
                if not rows:
                    continue
                pairs = collections.defaultdict(dict)
                for row in rows:
                    pairs[row["repeat"]][row["label"]] = row
                key = (suite, data["config"]["comparison"], family, case)
                log_ratio = stats.mean(math.log(v[1]["ms"] / v[0]["ms"]) for v in pairs.values())
                trip = stats.mean(math.log(v[1]["roundTripMs"] / v[0]["roundTripMs"]) for v in pairs.values())
                record = {"file": str(path.relative_to(output)), "log_ratio": log_ratio,
                          "round_trip_log_ratio": trip,
                          "medians_ms": [stats.median(r["ms"] for r in rows if r["label"] == i) for i in [0, 1]],
                          "reduction_percent": 100 * (1 - math.exp(log_ratio))}
                groups[key].append(record)
                sessions.append({"key": key, **record})
rng = random.Random(20261022)
summary = []
for key, rows in sorted(groups.items()):
    logs = [r["log_ratio"] for r in rows]
    bootstrap = sorted(stats.mean(rng.choices(logs, k=len(logs))) for _ in range(10000))
    summary.append({"suite": key[0], "comparison": key[1], "family": key[2], "case": key[3],
                    "sessions": len(rows), "reduction_percent": 100 * (1 - math.exp(stats.mean(logs))),
                    "interval_95_percent": [100 * (1 - math.exp(bootstrap[9749])), 100 * (1 - math.exp(bootstrap[249]))],
                    "round_trip_reduction_percent": 100 * (1 - math.exp(stats.mean(r["round_trip_log_ratio"] for r in rows))),
                    "median_session_reduction_percent": 100 * (1 - math.exp(stats.median(logs))),
                    "median_of_session_medians_ms": [stats.median(r["medians_ms"][i] for r in rows) for i in [0, 1]],
                    "session_reductions_percent": [r["reduction_percent"] for r in rows]})
result = {"browser_sessions": browser_sessions, "render_identity_checks": renders, "measured_renders": measured,
          "groups": summary, "sessions": sessions}
(output / "timing-summary.json").write_text(json.dumps(result, indent=2) + "\n")
for row in summary:
    print(row["suite"], row["comparison"], row["family"], row["case"],
          round(row["reduction_percent"], 2), [round(x, 2) for x in row["interval_95_percent"]],
          [round(x, 2) for x in row["median_of_session_medians_ms"]])
