"""Isolated SCORE-v2 native ink comparison builder (table lookup only).

Reads the CORRECTED score corpus
(out/diagnostics/contextual-spacing/yinyang-oriented-fields/
score-experiment-corrected/{report,provenance}.json) plus the frozen capture
cells pinned by the stage-1 implementation provenance, validates every pin and
every placement rule independently, and writes a SELF-CONTAINED offline page
under .../yinyang-oriented-fields/visual-comparison/:

  index.html                     self-contained page (inline data + JS)
  manifest.json                  pins, corpus counts, file list
  checks/checks.json             builder validation summary
  checks/expected_choices.json   independent choice oracle for the browser test

No score/field/engine code is imported or re-executed here: the page reuses
stored curve values with the TIE-v2 rule only (absolute deviations, tolerance
1e-9*max(1,m*), lowest step index). No field tensors are embedded (a few glyph
bitmaps x 8 captures only). No apps/crates edits, installs, servers, commits.

Usage:
  python3 experiments/contextual_spacing/yinyang_oriented_score_preview.py OUT [--force]
"""

import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEAF = Path("out/diagnostics/contextual-spacing/yinyang-oriented-fields")
CORRECTED = LEAF / "score-experiment-corrected"
STAGE_PROV = LEAF / "implementation/provenance.json"
RERUN_PROV = LEAF / "score-experiment-corrected/provenance.json"

# Frozen input authority (corrected corpus only; the stale score-experiment
# report is never read).
EXPECT_SCORE_SHA = "207637f0ae6e69a1898f85bdf256d21f8c9cc2f76b3dd4c954d86ed8660dc1ac"
EXPECT_EVIDENCE_SHA = "5124a665cf0d559ebd0dec69541f9f7eef805069c619db397f8cf0f963610cc4"
EXPECT_B2_SHA = "5f6f1aebcd4121df0441029a2171457f166b853b15c4a757e2a1c50780fdfdd7"
EXPECT_B2_MODEL = "yinyangfit-interactive-b2-fullwindow-v1"

SAMPLES = [
    ("roboto-16", "Roboto 16", "roboto-16"),
    ("roboto-24", "Roboto 24", "roboto-24"),
    ("literata-16", "Literata 16", "literata-16"),
    ("literata-24", "Literata 24", "literata-24"),
]
CAPTURE_NAMES = {
    "roboto-16": ("roboto-16-mono", "roboto-16-gray"),
    "roboto-24": ("roboto-24-mono", "roboto-24-gray"),
    "literata-16": ("literata-16-mono", "literata-16-gray"),
    "literata-24": ("literata-24-mono", "literata-24-gray"),
}
PAIRS = ["um", "og", "AV", "To", "nn", "oo", "HH", "il"]
CODEPOINTS = sorted({ord(c) for p in PAIRS for c in p})
CSTAR_GRID = [0.0, 1.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 20.0,
              24.0, 32.0, 48.0, 64.0, 96.0, 128.0]
TIE_TOL_FACTOR = 1e-9
B2_COHESION = 1.10
B2_DELTAS = (-2, -1, 0, 1, 2)
B2_TIE_TOL = 1e-9


class PreviewPinError(SystemExit):
    pass


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pixel_round(value):
    # Native surface invariant for the nonneg pens of a left-aligned pair.
    if value >= 0:
        return math.floor(value + 0.5)
    return math.ceil(value - 0.5)


def validate_pins(repo=REPO):
    """Reject on any model/capture pin mismatch. Returns (stage_prov, rerun_prov)."""
    score_py = repo / "experiments/contextual_spacing/yinyang_oriented_score.py"
    evidence_py = repo / "experiments/contextual_spacing/yinyang_oriented_score_evidence.py"
    b2_py = repo / "experiments/contextual_spacing/yinyangfit_interactive_b2.py"
    got = sha256_file(score_py)
    if got != EXPECT_SCORE_SHA:
        raise PreviewPinError("score module drift: %s has %s" % (score_py, got))
    got = sha256_file(evidence_py)
    if got != EXPECT_EVIDENCE_SHA:
        raise PreviewPinError("evidence module drift: %s has %s" % (evidence_py, got))
    got = sha256_file(b2_py)
    if got != EXPECT_B2_SHA:
        raise PreviewPinError("protected B2 drift: %s has %s" % (b2_py, got))
    rerun_prov = json.loads((repo / RERUN_PROV).read_text())
    if rerun_prov.get("score_module_sha256") != EXPECT_SCORE_SHA:
        raise PreviewPinError("rerun provenance score pin mismatch")
    if rerun_prov.get("evidence_module_sha256") != EXPECT_EVIDENCE_SHA:
        raise PreviewPinError("rerun provenance evidence pin mismatch")
    if rerun_prov.get("b2_sha256") != EXPECT_B2_SHA:
        raise PreviewPinError("rerun provenance B2 pin mismatch")
    stage_prov = json.loads((repo / STAGE_PROV).read_text())
    for name in sum([list(v) for v in CAPTURE_NAMES.values()], []):
        cap = stage_prov["captures"][name]
        path = repo / cap["path"]
        got = sha256_file(path)
        if got != cap["sha256"]:
            raise PreviewPinError("capture drift: %s has %s" % (name, got))
    return stage_prov, rerun_prov


def load_capture_cells(path, profile):
    """Minimal native capture reader (independent of the v1 loaders).

    Returns (cells, advances, adjustments): cells[cp] holds bitmap geometry
    plus a cover list; mono covers are 0/1, gray covers are raw 0..7 ints.
    """
    cap = json.loads(Path(path).read_text())
    cells, advances, adjustments = {}, {}, {}
    if profile == "mono":
        if cap.get("schema_version") != "contextual-spacing-capture-v1":
            raise PreviewPinError("unsupported mono capture schema: %s" % path)
        for g in cap["glyphs"]:
            cp = g["codepoint"]
            b = g["bitmap"]
            if len(b["pixels"]) != b["width"] * b["height"]:
                raise PreviewPinError("mono bitmap length mismatch U+%04X" % cp)
            cells[cp] = {
                "width": b["width"], "height": b["height"],
                "left": float(b["left"]), "top": float(b["top"]),
                "cover": [1 if p else 0 for p in b["pixels"]],
            }
            advances[cp] = None
            cells[cp]["advance"] = float(g["finalized_advance_px"])
        for p in cap.get("metric_pairs_on", []):
            adjustments[(p["left"], p["right"])] = float(p["adjustment_px"])
    else:
        if cap.get("schema_version") not in ("contextual-spacing-grayscale-v1",
                                             "contextual-spacing-grayscale-v2"):
            raise PreviewPinError("unsupported grayscale capture schema: %s" % path)
        font = cap["font"]
        for g in font["glyphs"]:
            cp = g["codepoint"]
            if len(g["pixels"]) != g["width"] * g["height"]:
                raise PreviewPinError("gray bitmap length mismatch U+%04X" % cp)
            for v in g["pixels"]:
                if v not in (0, 1, 2, 3, 4, 5, 6, 7):
                    raise PreviewPinError("gray pixel out of 0..7 U+%04X" % cp)
            cells[cp] = {
                "width": g["width"], "height": g["height"],
                "left": float(g["left"]), "top": float(g["top"]),
                "cover": [int(v) for v in g["pixels"]],
            }
            advances[cp] = float(g["advance_26_6"]) / 64.0
        for p in font.get("kerning", []) or []:
            adjustments[(p["left"], p["right"])] = float(p["adjustment_26_6"]) / 64.0
    return cells, advances, adjustments


def source_metric(profile, cells, advances, adjustments, left, right):
    if profile == "mono":
        advance = float(cells[left]["advance"])
    else:
        advance = float(advances[left])
    return pixel_round(advance + float(adjustments.get((left, right), 0.0)))


def tie_pick(deviations):
    """TIE-v2 over a deviation list: (mstar, tie_indices, lowest_pick)."""
    mstar = min(deviations)
    tol = TIE_TOL_FACTOR * max(1.0, mstar)
    idx = [i for i, d in enumerate(deviations) if d <= mstar + tol]
    return mstar, idx, min(idx)


def oriented_choice(step_rows, target):
    """step_rows: [(step, delta, g2)] valid-only. Returns dict or None."""
    if not step_rows:
        return None
    devs = [abs(g - target) for (_, _, g) in step_rows]
    mstar, idx, pick = tie_pick(devs)
    steps = [s for (s, _, _) in step_rows]
    ties = sorted(steps[i] for i in idx)
    chosen = steps[pick]
    delta = [d for (s, d, _) in step_rows if s == chosen][0]
    return {"step": chosen, "delta": delta, "mstar": mstar,
            "ties": ties, "lowest": ties[0]}


def b2_choice(metric, by_delta):
    """Recompute the frozen B2 placement from stored per-step interactions.

    by_delta maps candidate delta (-2..+2) to (step, valid, interaction).
    Cost is |interaction - 1.1| with 1e-9 tolerance and metric-side
    tie-break; no valid candidate falls back to the metric step.
    """
    cands = []
    for d in B2_DELTAS:
        rec = by_delta.get(d)
        if rec is None:
            continue
        step, valid, inter = rec
        if not valid or inter is None or not math.isfinite(inter):
            continue
        cands.append((step, abs(inter - B2_COHESION)))
    if not cands:
        return metric, True
    best = min(c for (_, c) in cands)
    minimizing = sorted(s for (s, c) in cands if c <= best + B2_TIE_TOL)
    chosen = min(minimizing, key=lambda s: (abs(s - metric), s - metric))
    return chosen, False


def extract_data(repo, stage_prov, report):
    """Build the page payload plus the independent choice oracle."""
    captures = {}
    cases = {}
    expected = {}
    for sample_id, label, _ in SAMPLES:
        mono_name, gray_name = CAPTURE_NAMES[sample_id]
        for cname, profile in ((mono_name, "mono"), (gray_name, "gray")):
            cap = stage_prov["captures"][cname]
            cells, advances, adjustments = load_capture_cells(
                repo / cap["path"], profile)
            for cp in CODEPOINTS:
                if cp not in cells:
                    raise PreviewPinError(
                        "capture %s missing U+%04X" % (cname, cp))
            size = float(cap["size_px"])
            key = "%s-%s" % (sample_id, profile)
            glyphs = {}
            for cp in CODEPOINTS:
                cell = cells[cp]
                if profile == "mono":
                    px = "".join("1" if v else "0" for v in cell["cover"])
                else:
                    px = "".join(str(v) for v in cell["cover"])
                glyphs[str(cp)] = {"w": cell["width"], "h": cell["height"],
                                   "left": cell["left"], "top": cell["top"],
                                   "px": px}
            captures[key] = {"label": label, "size": size,
                             "profile": profile, "sha": cap["sha256"],
                             "glyphs": glyphs}
            cases[key] = {}
            for pair in PAIRS:
                left, right = ord(pair[0]), ord(pair[1])
                c = report["cases"][cname][pair]
                metric = source_metric(profile, cells, advances,
                                       adjustments, left, right)
                if metric != c["metric"]:
                    raise PreviewPinError(
                        "source metric mismatch %s %s: capture %s vs stored %s"
                        % (cname, pair, metric, c["metric"]))
                steps = []
                by_delta = {}
                for s in c["steps"]:
                    valid = bool(s.get("valid"))
                    g2n = s.get("g2_primary") if valid else None
                    g2m = s.get("g2_a1") if valid else None
                    b2i = s.get("b2_interaction")
                    if valid and (g2n is None or not math.isfinite(g2n)):
                        raise PreviewPinError(
                            "missing notebook G2 %s %s d=%s" % (cname, pair, s.get("delta")))
                    steps.append({"delta": s["delta"], "step": s["step"],
                                  "valid": valid,
                                  "g2n": g2n, "g2m": g2m, "b2i": b2i,
                                  "b2v": bool(s.get("b2_valid"))})
                    by_delta[s["delta"]] = (s["step"], bool(s.get("b2_valid")),
                                            b2i if s.get("b2_valid") else None)
                b2step, b2fallback = b2_choice(metric, by_delta)
                if b2step != c["b2_chosen"]:
                    raise PreviewPinError(
                        "B2 choice mismatch %s %s: recomputed %s vs stored %s"
                        % (cname, pair, b2step, c["b2_chosen"]))
                cases[key][pair] = {"metric": metric, "b2": b2step,
                                    "b2fallback": b2fallback, "steps": steps}
                # Narrow/notebook parity against the stored per-C* table.
                narrow = [(s["step"], s["delta"], s["g2n"]) for s in steps
                          if s["valid"] and abs(s["delta"]) <= 2]
                narrow_steps = [s for (s, _, _) in narrow]
                for cstar in CSTAR_GRID:
                    stored = c["cstar"][str(cstar)]
                    if [abs(g - cstar) for (_, _, g) in narrow] != stored["deviations"]:
                        raise PreviewPinError(
                            "narrow deviation drift %s %s C*=%s" % (cname, pair, cstar))
                    if (sorted(narrow_steps[i] for i in stored["tie_idx"])
                            != sorted(narrow_steps[i] for i in
                                      tie_pick(stored["deviations"])[1])):
                        raise PreviewPinError(
                            "narrow tie drift %s %s C*=%s" % (cname, pair, cstar))
                    if narrow_steps[stored["tie_pick_lowest"]] != narrow_steps[
                            tie_pick(stored["deviations"])[2]]:
                        raise PreviewPinError(
                            "narrow pick drift %s %s C*=%s" % (cname, pair, cstar))
                # Independent oracle for the browser parity test.
                for cstar in CSTAR_GRID:
                    for domain in (2, 6):
                        for variant, gk in (("notebook", "g2n"), ("manuscript", "g2m")):
                            rows = [(s["step"], s["delta"], s[gk])
                                    for s in steps
                                    if s["valid"] and abs(s["delta"]) <= domain
                                    and s[gk] is not None
                                    and math.isfinite(s[gk])]
                            pick = oriented_choice(rows, cstar)
                            ekey = "%s|%s|%s|%d|%s" % (key, pair, cstar, domain, variant)
                            if pick is None:
                                expected[ekey] = {"step": None}
                            else:
                                expected[ekey] = {
                                    "step": pick["step"], "delta": pick["delta"],
                                    "mstar": pick["mstar"], "ties": pick["ties"],
                                    "boundary": abs(pick["delta"]) == domain,
                                    "n_valid": len(rows)}
    return captures, cases, expected


def build(outdir, force=False):
    repo = REPO
    outdir = Path(outdir)
    if outdir.exists() and not force:
        raise SystemExit("refusing to reuse output directory: %s (pass --force)" % outdir)

    stage_prov, rerun_prov = validate_pins(repo)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "checks").mkdir(parents=True, exist_ok=True)
    report = json.loads((repo / CORRECTED / "report.json").read_text())
    if sorted(report["cases"].keys()) != sorted(
            sum([list(v) for v in CAPTURE_NAMES.values()], [])):
        raise PreviewPinError("report capture set changed")
    if report["cstar"]["grid"] != list(CSTAR_GRID):
        raise PreviewPinError("C* grid changed")
    if report["cstar"]["tie_candidates"] != [4.0]:
        raise PreviewPinError("C* tie set changed")
    n_valid = sum(1 for caps in report["cases"].values() for c in caps.values()
                  for s in c["steps"] if s.get("valid"))
    n_invalid = sum(1 for caps in report["cases"].values() for c in caps.values()
                    for s in c["steps"] if not s.get("valid"))
    if (n_valid, n_invalid) != (610, 222):
        raise PreviewPinError("valid/invalid step counts changed: %d/%d" % (n_valid, n_invalid))

    captures, cases, expected = extract_data(repo, stage_prov, report)

    data = {"samples": [{"id": s, "label": l} for s, l, _ in SAMPLES],
            "pairs": PAIRS, "captures": captures, "cases": cases,
            "pins": {"score": EXPECT_SCORE_SHA, "evidence": EXPECT_EVIDENCE_SHA,
                     "b2": EXPECT_B2_SHA, "b2_model": EXPECT_B2_MODEL,
                     "stage1": stage_prov.get("implementation_sha256")}}
    data_json = json.dumps(data, separators=(",", ":"), allow_nan=False)
    if "</script" in data_json.lower():
        raise PreviewPinError("unexpected script terminator in payload")
    data_esc = data_json.replace("</", "<\\/").replace("<!--", "<\\!--")

    here = Path(__file__).resolve().parent
    template = (here / "yinyang_oriented_score_preview_template.html").read_text()
    app_js = (here / "yinyang_oriented_score_preview_app.js").read_text()
    prov_line = ("Frozen corrected corpus: 8 captures x 8 pairs = 64 cases, "
                 "610 valid / 222 invalid steps. score %s; evidence %s; "
                 "stage-1 %s; B2 %s; captures pinned in manifest. "
                 "Uncertainty not certified." % (
                     EXPECT_SCORE_SHA[:12], EXPECT_EVIDENCE_SHA[:12],
                     str(stage_prov.get("implementation_sha256"))[:12],
                     EXPECT_B2_SHA[:12]))
    app_js = app_js + "\nwindow.__YYPROV = %s;\n" % json.dumps(prov_line)
    html = template.replace("/*__DATA_JSON__*/null", data_esc)
    html = html.replace("/*__APP_JS__*/", app_js)
    if "__DATA_JSON__" in html or "__APP_JS__" in html:
        raise PreviewPinError("template placeholder mismatch")
    (outdir / "index.html").write_text(html)

    manifest = {
        "tool": "yinyang_oriented_score_preview.py",
        "builder_sha256": sha256_file(here / "yinyang_oriented_score_preview.py"),
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"report": str(CORRECTED / "report.json"),
                   "provenance": str(CORRECTED / "provenance.json"),
                   "stage_provenance": str(STAGE_PROV)},
        "pins": data["pins"],
        "captures": {k: {"sha": v["sha"], "label": v["label"],
                         "size": v["size"], "profile": v["profile"]}
                      for k, v in captures.items()},
        "corpus": {"captures": 8, "pairs": PAIRS, "cases": 64,
                   "valid_steps": n_valid, "invalid_steps": n_invalid,
                   "cstar_grid": CSTAR_GRID,
                   "cstar_global_min": report["cstar"]["global_min"],
                   "cstar_tie_candidates": report["cstar"]["tie_candidates"],
                   "initial_target": 4.0,
                   "initial_target_note": "study value, not a recommendation"},
        "files": ["index.html", "manifest.json",
                  "checks/checks.json", "checks/expected_choices.json"],
    }
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (outdir / "checks" / "expected_choices.json").write_text(
        json.dumps(expected, separators=(",", ":"), allow_nan=False))
    checks = {"pins_ok": True, "cases": 64, "valid_steps": n_valid,
              "invalid_steps": n_invalid,
              "metric_parity": "64/64 source steps from native capture arithmetic",
              "b2_parity": "64/64 B2 choices recomputed (|interaction-1.1|, 1e-9, metric tie-break)",
              "cstar_parity": "64 cases x 17 grid narrow/notebook deviations+ties+pick exact",
              "oracle_entries": len(expected),
              "data_bytes": len(data_json.encode()),
              "html_bytes": len(html.encode())}
    (outdir / "checks" / "checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    return {"outdir": str(outdir), "checks": checks, "manifest": manifest}


def main(argv):
    if len(argv) < 2 or len(argv) > 3:
        raise SystemExit("usage: yinyang_oriented_score_preview.py OUT [--force]")
    force = len(argv) == 3 and argv[2] == "--force"
    if len(argv) == 3 and not force:
        raise SystemExit("usage: yinyang_oriented_score_preview.py OUT [--force]")
    result = build(argv[1], force=force)
    print(json.dumps(result["checks"], indent=2))


if __name__ == "__main__":
    main(sys.argv)
