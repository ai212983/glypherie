#!/usr/bin/env python3
"""Opt-in direct-diagonal evaluation harness (explicit invocation only).

Default run is an identity control: it groups capture records by font,
axes, size and hint mode, renders the upstream arm through the adapter and
writes the review app without importing the core solver or NumPy.
`--enable-direct-diagonals` additionally builds one reference per group and
runs the `width_only` and `grid` arms through the promised core API:

  build_reference(records, size_px) -> dict
  fit_glyph(source_commands, fitted_commands, size_px, reference,
            native_axes=(False, False), grid=False) -> dict

`fit_glyph` always returns `candidate_commands` (exact upstream fallback),
`applied`, `reason`, `widths`, grid targets/residuals, fixed/native axes,
movement, bound and validity. Each hint mode is its own case with its own
source/fitted commands, ownership, scan policy and reference: selective
ownership never leaks onto the automatic baseline. All candidate pixels come
from the adapter's exact recorded policy; a failed mandatory parity aborts
the run.
"""

import argparse
import functools
import hashlib
import json
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

TOOL_VERSION = "direct-diagonal-run-v2"
DEFAULT_ADAPTER = "crates/generator/target/debug/strokestyles-fit-adapter"
BUILD_ADAPTER_CMD = (
    "CARGO_TARGET_DIR=crates/generator/target cargo build --locked --offline "
    "--manifest-path experiments/strokestyles_fitting/native/Cargo.toml"
)

# Native advance/layout metrics copied verbatim from the capture record;
# command count and codepoint ride along as additional fields.
METRIC_KEYS = [
    "advance_26_6",
    "hinted_advance_width",
    "hinted_lsb",
    "hinted_has_overlaps",
    "side_bearing_deltas_26_6",
    "left",
    "top",
    "width",
    "height",
]

MODES = ("width_only", "grid")
HINT_MODES = ("auto_default", "selective_default")


def fail(message):
    raise SystemExit("direct-diagonal-run: " + message)


def resolve_adapter(flag):
    if flag:
        if not os.path.isfile(flag):
            fail("missing --adapter %s; build it with %s" % (flag, BUILD_ADAPTER_CMD))
        return flag
    if os.path.isfile(DEFAULT_ADAPTER):
        return DEFAULT_ADAPTER
    fail("adapter binary not found at %s; build it with %s"
         % (DEFAULT_ADAPTER, BUILD_ADAPTER_CMD))


def run_adapter(binary, *argv):
    proc = subprocess.run([binary] + list(argv), capture_output=True)
    if proc.returncode != 0:
        fail("adapter %s failed: %s"
             % (" ".join(argv), proc.stderr.decode().strip()[-500:]))
    return proc.stdout.decode()


def check_binary(binary):
    proc = subprocess.run([binary, "candidate"], capture_output=True)
    if proc.returncode != 2:
        fail("adapter binary did not respond as expected")


def ownership(record):
    """Native-axis ownership from the record's own capture only."""
    sel = record.get("selective_fitting") or {}
    native = sel.get("native_axes")
    if isinstance(native, list) and len(native) == 2 and all(
        isinstance(v, bool) for v in native
    ):
        return tuple(native), "selective-native-axes"
    engine = record.get("selected_engine")
    if engine == "auto":
        return (False, False), "selected-engine"
    if engine == "interpreter":
        return (True, True), "selected-engine"
    # Unknown engine reserves both axes; the core reports its own abstention.
    return (True, True), "unknown-reserve-both"


def record_metrics(record):
    out = {key: record.get(key) for key in METRIC_KEYS}
    out["n_commands"] = len(record.get("fitted_commands", []))
    out["codepoint"] = record.get("codepoint")
    return out


def load_core(enabled):
    if not enabled:
        return None
    import importlib

    try:
        core = importlib.import_module("experiments.hobby_fitting.direct_diagonal")
    except ImportError as exc:
        fail("core module unavailable: %s" % exc)
    for name in ("build_reference", "fit_glyph"):
        if not callable(getattr(core, name, None)):
            fail("core module misses %s" % name)
    return core


def iter_records(cases):
    for case in cases:
        family = case.get("family")
        size = case.get("size")
        axes = case.get("axes", {})
        font_sha = case.get("source", {}).get("source_sha256")
        src_by_code = {r.get("codepoint"): r for r in case.get("source", {}).get("records", [])}
        for hint in HINT_MODES:
            mode = case.get("modes", {}).get(hint, {})
            by_code = {r.get("codepoint"): r for r in mode.get("records", [])}
            for code in sorted(set(by_code) & set(src_by_code)):
                yield {
                    "family": family, "size": size, "axes": axes,
                    "font_sha": font_sha, "hint_mode": hint,
                    "codepoint": code,
                    "source": src_by_code[code],
                    "record": by_code[code],
                }


def arm_pixels(binary, record, commands, scratch):
    """Render commands through the record's own captured policy."""
    record_path = os.path.join(scratch, "record.json")
    commands_path = os.path.join(scratch, "commands.json")
    with open(record_path, "w") as handle:
        json.dump(record, handle)
    with open(commands_path, "w") as handle:
        json.dump(commands, handle)
    out = run_adapter(
        binary, "candidate", "--record", record_path, "--commands", commands_path,
    )
    return json.loads(out)


def check_parity(binary, record, scratch):
    record_path = os.path.join(scratch, "parity-record.json")
    with open(record_path, "w") as handle:
        json.dump(record, handle)
    report = json.loads(run_adapter(binary, "parity", "--record", record_path))
    if not report.get("match"):
        fail("mandatory parity failed for codepoint %s" % record.get("codepoint"))
    return report


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Direct diagonal review (mechanical metrics only)</title>
<style>
body{font-family:system-ui,sans-serif;margin:16px;color:#222;max-width:1400px}
canvas{image-rendering:pixelated;border:1px solid #999}
label{margin-right:12px}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;align-items:start}
.arm{margin:0;min-width:0}
.arm pre{white-space:pre-wrap;overflow-wrap:anywhere}
.arm .armTitle{min-height:3.5em}
.arm .armTitle .note{display:block}
.cell{display:inline-block;vertical-align:top;margin-right:8px}
summary{cursor:pointer;font-size:13px;color:#333}
table{border-collapse:collapse;font-size:13px}
td,th{border:1px solid #ccc;padding:2px 8px;text-align:left}
.note{font-size:13px;color:#555}
</style>
</head>
<body>
<h1>Direct diagonal review (mechanical metrics only)</h1>
<div id="filters"></div>
<div id="cases"></div>
<script>
let DATA = null;
function opt(id, values, current) {
  const sel = document.createElement("select");
  sel.id = id;
  values.forEach(v => { const o = document.createElement("option"); o.value = v; o.textContent = v; sel.appendChild(o); });
  if (current && values.includes(current)) sel.value = current;
  sel.onchange = render;
  return sel;
}
function draw(canvas, arm, scale) {
  const frame = arm.frame;
  canvas.width = frame.width * scale;
  canvas.height = frame.height * scale;
  canvas.style.width = canvas.width + "px";
  canvas.style.height = canvas.height + "px";
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(frame.width, frame.height);
  for (let i = 0; i < arm.pixels.length; i++) {
    const v = arm.pixels[i] ? 0 : 255;
    img.data[4*i] = v; img.data[4*i+1] = v; img.data[4*i+2] = v; img.data[4*i+3] = 255;
  }
  const off = document.createElement("canvas");
  off.width = frame.width; off.height = frame.height;
  off.getContext("2d").putImageData(img, 0, 0);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(off, 0, 0, canvas.width, canvas.height);
}
function load() {
  fetch("summary.json").then(r => r.json()).then(s => { DATA = s; build(); });
}
function selected(id) { return document.getElementById(id).value; }
function weightOf(c) { return String(c.axes.wght || "?"); }
function matches(c) {
  if (selected("fFam") !== "all" && c.family !== selected("fFam")) return false;
  if (selected("fWght") !== "all" && weightOf(c) !== selected("fWght")) return false;
  if (selected("fSize") !== "all" && String(c.size) !== selected("fSize")) return false;
  if (selected("fGlyph") !== "all" && c.char !== selected("fGlyph")) return false;
  if (selected("fHint") !== "all" && c.hint_mode !== selected("fHint")) return false;
  return true;
}
function pickDefault(values, want) {
  return values.includes(want) ? want : "all";
}
function build() {
  const f = document.getElementById("filters");
  f.innerHTML = "";
  const fam = ["all", ...new Set(DATA.cases.map(c => c.family))];
  const wght = ["all", ...new Set(DATA.cases.map(c => weightOf(c)))];
  const size = ["all", ...new Set(DATA.cases.map(c => String(c.size)))];
  const glyph = ["all", ...new Set(DATA.cases.map(c => c.char))];
  const hint = ["all", "auto_default", "selective_default"];
  f.append("family ", opt("fFam", fam, pickDefault(fam, "Roboto")),
    " weight ", opt("fWght", wght, pickDefault(wght, "400")),
    " size ", opt("fSize", size, pickDefault(size, "16")),
    " glyph ", opt("fGlyph", glyph, pickDefault(glyph, "x")),
    " hint ", opt("fHint", hint, pickDefault(hint, "selective_default")));
  const note = document.createElement("p");
  note.className = "note";
  note.textContent = "Showing at most 120 cases; all filter options remain available.";
  f.appendChild(note);
  render();
}
function render() {
  const box = document.getElementById("cases");
  box.innerHTML = "loading…";
  const wanted = DATA.cases.filter(matches).slice(0, 120);
  Promise.all(wanted.map(c => fetch(c.file).then(r => r.json()))).then(show);
}
function show(cases) {
  const box = document.getElementById("cases");
  box.innerHTML = "";
  function details(name, arm) {
    const det = document.createElement("details");
    const sum = document.createElement("summary");
    sum.textContent = name + " metrics";
    det.appendChild(sum);
    const copy = {};
    for (const k in arm) {
      if (["pixels", "coverage", "frame", "candidate_commands"].includes(k)) continue;
      copy[k] = arm[k];
    }
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(copy, null, 1);
    det.appendChild(pre);
    return det;
  }
  cases.forEach(c => {
    const div = document.createElement("div");
    const head = document.createElement("div");
    head.innerHTML = "<b>" + c.family + " " + c.size + "px " + c.hint_mode +
      " U+" + c.codepoint.toString(16).toUpperCase() + " " + c.char + "</b>" +
      " <span class=note>native " + JSON.stringify(c.native_axes) +
      " via " + c.ownership + "</span>";
    div.appendChild(head);
    const cols = document.createElement("div");
    cols.className = "cols";
    const arms = [["source", c.source], ["upstream", c.arms.upstream],
      ["width_only", c.arms.width_only], ["grid", c.arms.grid]];
    // Shared-baseline cells: pad each arm by its frame offset.
    const tops = arms.filter(([, a]) => a).map(([, a]) => a.frame.top);
    const lefts = arms.filter(([, a]) => a).map(([, a]) => a.frame.left);
    const baseTop = Math.min.apply(null, tops), baseLeft = Math.min.apply(null, lefts);
    arms.forEach(([name, arm]) => {
      if (!arm) return;
      const d = document.createElement("div");
      d.className = "arm";
      const title = document.createElement("div");
      title.className = "armTitle";
      title.innerHTML = "<b>" + name + "</b>";
      if (arm.reason) {
        const status = document.createElement("span");
        status.className = "note";
        status.textContent = arm.reason;
        title.appendChild(status);
      }
      d.appendChild(title);
      [["1x", 1], ["8x", 8]].forEach(([label, s]) => {
        const cell = document.createElement("span");
        cell.className = "cell";
        cell.style.marginTop = ((arm.frame.top - baseTop) * s) + "px";
        cell.style.marginLeft = ((arm.frame.left - baseLeft) * s) + "px";
        const cv = document.createElement("canvas");
        draw(cv, arm, s);
        cell.appendChild(document.createTextNode(label + " "));
        cell.appendChild(cv);
        d.appendChild(cell);
      });
      d.appendChild(details(name, arm));
      cols.appendChild(d);
    });
    div.appendChild(cols);
    box.appendChild(div);
  });
}
load();
</script>
</body>
</html>
"""


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--captures", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--enable-direct-diagonals", action="store_true")
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--mode", default="both",
                        choices=["both", "width_only", "grid"])
    parser.add_argument("--exact-joins", action="store_true")
    parser.add_argument("--topology-binary", default=None)
    args = parser.parse_args(argv)
    with open(args.captures) as handle:
        cases = json.load(handle)
    if isinstance(cases, dict):
        cases = [cases]
    binary = resolve_adapter(args.adapter)
    check_binary(binary)
    if args.exact_joins and not args.enable_direct_diagonals:
        fail("--exact-joins requires --enable-direct-diagonals")
    topology_binary = None
    if args.exact_joins:
        topology_binary = args.topology_binary or os.environ.get(
            "HOBBY_EXACT_TOPOLOGY_BINARY")
        if not topology_binary or not (
            os.path.isfile(topology_binary)
            and os.access(topology_binary, os.X_OK)
        ):
            fail("exact topology binary missing; pass --topology-binary PATH "
                 "or set HOBBY_EXACT_TOPOLOGY_BINARY")
    with open(args.captures, "rb") as handle:
        capture_sha256 = hashlib.sha256(handle.read()).hexdigest()
    topology_sha256 = None
    if topology_binary is not None:
        with open(topology_binary, "rb") as handle:
            topology_sha256 = hashlib.sha256(handle.read()).hexdigest()
    out = args.out
    os.makedirs(os.path.join(out, "cases"), exist_ok=True)
    scratch = os.path.join(out, ".scratch")
    os.makedirs(scratch, exist_ok=True)
    core = load_core(args.enable_direct_diagonals)
    checker = None
    if topology_binary is not None:
        from experiments.hobby_fitting import exact_topology

        checker = functools.partial(
            exact_topology.compare_commands, binary=topology_binary)
    modes = list(MODES) if args.mode == "both" else [args.mode]

    items = sorted(iter_records(cases), key=lambda i: (
        str(i["family"]), str(i["size"]), json.dumps(i["axes"], sort_keys=True),
        i["hint_mode"], i["codepoint"],
    ))
    # Group key: same font SHA, axes, size and hint mode (donors included).
    groups = {}
    for item in items:
        key = (item["font_sha"], json.dumps(item["axes"], sort_keys=True),
               str(item["size"]), item["hint_mode"])
        groups.setdefault(key, []).append(item)

    references = {}
    if core is not None:
        for key, members in groups.items():
            t0 = time.perf_counter()
            records = [m["record"] for m in members]
            references[key] = {
                "reference": core.build_reference(records, members[0]["size"]),
                "runtime_ms": (time.perf_counter() - t0) * 1000.0,
            }

    summary_cases = []
    counts = {m: {"applied": 0, "abstained": 0} for m in MODES}
    counts["upstream"] = {"rendered": 0}
    reasons = {m: {} for m in MODES}
    seen_files = set()

    def unique_name(stem):
        name = stem
        counter = 2
        while name in seen_files:
            name = "%s-%d" % (stem, counter)
            counter += 1
        seen_files.add(name)
        return name + ".json"

    for item in items:
        t0 = time.perf_counter()
        record = item["record"]
        native_axes, owner = ownership(record)
        check_parity(binary, record, scratch)
        up_commands = record.get("fitted_commands", [])
        up_pixels = arm_pixels(binary, record, up_commands, scratch)
        counts["upstream"]["rendered"] += 1
        arms = {"upstream": {
            "pixels": up_pixels["pixels"], "coverage": up_pixels["coverage"],
            "frame": {k: up_pixels[k] for k in ("left", "top", "width", "height")},
        }}
        if core is None:
            for mode in modes:
                arms[mode] = None
        else:
            key = (item["font_sha"], json.dumps(item["axes"], sort_keys=True),
                   str(item["size"]), item["hint_mode"])
            reference = references[key]["reference"]
            for mode in modes:
                fit_kwargs = {}
                if checker is not None:
                    fit_kwargs["topology_checker"] = checker
                result = core.fit_glyph(
                    record.get("source_commands", []), up_commands,
                    item["size"], reference, native_axes,
                    grid=(mode == "grid"), **fit_kwargs,
                )
                cand = arm_pixels(
                    binary, record, result["candidate_commands"], scratch)
                arms[mode] = dict(result)
                arms[mode]["checker"] = (
                    "exact_arrangement" if checker is not None
                    else "strict_signature")
                arms[mode]["pixels"] = cand["pixels"]
                arms[mode]["coverage"] = cand["coverage"]
                arms[mode]["frame"] = {
                    k: cand[k] for k in ("left", "top", "width", "height")
                }
                if result.get("applied"):
                    counts[mode]["applied"] += 1
                else:
                    counts[mode]["abstained"] += 1
                    reason = result.get("reason", "unstated")
                    reasons[mode][reason] = reasons[mode].get(reason, 0) + 1
        src = item["source"]
        case = {
            "family": item["family"], "size": item["size"], "axes": item["axes"],
            "hint_mode": item["hint_mode"],
            "char": chr(item["codepoint"]), "codepoint": item["codepoint"],
            "glyph_id": record.get("glyph_id"),
            "font_sha256": item["font_sha"],
            "native_axes": list(native_axes), "ownership": owner,
            "record_metrics": record_metrics(record),
            "source": {
                "pixels": src.get("pixels"), "coverage": src.get("coverage"),
                "frame": {k: src.get(k) for k in ("left", "top", "width", "height")},
                "label": "independent-source",
            },
            "arms": arms,
            "runtime_ms": (time.perf_counter() - t0) * 1000.0,
        }
        stem = "%s_%s_%s_%s" % (
            item["family"], str(item["size"]), item["hint_mode"],
            "U+%04X" % item["codepoint"],
        )
        stem = "".join(c if c.isalnum() or c in "+-._" else "_" for c in stem)
        filename = unique_name(stem)
        with open(os.path.join(out, "cases", filename), "w") as handle:
            json.dump(case, handle)
        summary_cases.append({
            "file": "cases/" + filename, "family": item["family"],
            "size": item["size"], "axes": item["axes"],
            "hint_mode": item["hint_mode"],
            "char": chr(item["codepoint"]), "codepoint": item["codepoint"],
            "native_axes": case["native_axes"], "ownership": owner,
        })
    summary = {
        "tool": TOOL_VERSION, "captures": args.captures, "mode": args.mode,
        "adapter": binary, "enabled": core is not None,
        "groups": len(groups), "counts": counts, "reasons": reasons,
        "cases": summary_cases,
        "topology_mode": (
            "exact_arrangement" if checker is not None else "strict_signature"),
        "topology_binary": topology_binary,
        "topology_binary_sha256": topology_sha256,
        "cgal_version": "6.1.1",
        "capture_sha256": capture_sha256,
    }
    with open(os.path.join(out, "summary.json"), "w") as handle:
        json.dump(summary, handle)
    with open(os.path.join(out, "index.html"), "w") as handle:
        handle.write(INDEX_HTML)
    return summary


if __name__ == "__main__":
    main()
