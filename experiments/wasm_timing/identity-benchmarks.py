"""Compare sparse-only and shared identity separately, then the combined change."""
import json
import os
import pathlib
import subprocess

root = pathlib.Path(__file__).resolve().parents[2]
output = root / "out/diagnostics/font-identity-optimization"
base = {
    "BASELINE_WEB_PACKAGE": str(output / "pkg-web-sparse"),
    "CANDIDATE_WEB_PACKAGE": str(output / "pkg-web-identity"),
    "REPEATS": "12",
    "WARMUPS": "3",
}
suites = [
    ("fixed-controls", {"ROUNDS": "1", "COMPARISONS": "AA,SS"}),
    ("fixed", {"ROUNDS": "3", "COMPARISONS": "AB"}),
    ("varied-controls", {"ROUNDS": "1", "COMPARISONS": "AA", "VARIED_REQUESTS": "1", "CASE_FILTER": "pangram"}),
    ("varied", {"ROUNDS": "3", "COMPARISONS": "AB", "VARIED_REQUESTS": "1", "CASE_FILTER": "pangram"}),
    ("combined", {"ROUNDS": "3", "COMPARISONS": "AB", "CASE_FILTER": "pangram",
                  "BASELINE_WEB_PACKAGE": str(output / "pkg-web-dense")}),
]
(output / "benchmark-plan.json").write_text(json.dumps({"base": base, "suites": suites}, indent=2) + "\n")
for name, overrides in suites:
    env = {**os.environ, **base, **overrides, "OUTPUT_DIR": str(output / name)}
    # Explicitly clear options that could silently narrow the fixed controls.
    for key in ["VARIED_REQUESTS", "CASE_FILTER"]:
        if key not in overrides:
            env.pop(key, None)
    subprocess.run(["node", "experiments/wasm_timing/browser.cjs"], cwd=root, env=env, check=True)
    print(json.dumps({"suite": name, "status": "passed"}), flush=True)
