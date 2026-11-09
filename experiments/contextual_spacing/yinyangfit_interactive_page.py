#!/usr/bin/env python3
"""Export a self-contained interactive feasibility page (offline file:// use).

Precomputes the exact candidate table for every CONTROL_GRID setting, so each
slider position shows an exactly evaluated setting (sliders snap to the grid;
nothing is interpolated). The browser recomputes only the argmin over embedded
costs; a node check requires it to match the embedded Python choice everywhere.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yinyangfit_interactive as yy
from yinyangfit_interactive_evidence import PAIRS, WORDS

GRID = yy.CONTROL_GRID


def combo_list():
    combos = []
    for cohesion in GRID["cohesion"]:
        for scale in GRID["feature_scale"]:
            for falloff in GRID["proximity_falloff"]:
                combos.append(yy.YYControls(cohesion=cohesion, feature_scale=scale,
                                           proximity_falloff=falloff))
    return combos


def round4(value):
    return None if value is None else round(float(value), 4)


def build_page_data(specs):
    combos = combo_list()
    combo_ids = [f"c{i}" for i in range(len(combos))]
    word_pairs = []
    for word in WORDS:
        for left, right in zip(word, word[1:]):
            pair = left + right
            if pair not in PAIRS and pair not in word_pairs:
                word_pairs.append(pair)
    all_pairs = PAIRS + word_pairs
    data = {"model": yy.MODEL_IDENTITY, "implementation": yy.IMPLEMENTATION_SHA256,
            "controls": {"cohesion": GRID["cohesion"],
                         "feature_scale": GRID["feature_scale"],
                         "proximity_falloff": GRID["proximity_falloff"],
                         "default": {"cohesion": float(yy.DEFAULT_CONTROLS.cohesion),
                                     "feature_scale": float(yy.DEFAULT_CONTROLS.feature_scale),
                                     "proximity_falloff": float(yy.DEFAULT_CONTROLS.proximity_falloff)}},
            "combos": [{"id": cid, "cohesion": float(c.cohesion),
                        "feature_scale": float(c.feature_scale),
                        "proximity_falloff": float(c.proximity_falloff),
                        "identity": yy.settings_identity(c)}
                       for cid, c in zip(combo_ids, combos)],
            "pairs": PAIRS, "words": WORDS, "datasets": []}
    for spec in specs:
        dataset = (yy.load_mono_capture(spec["path"]) if spec["profile"] == "mono"
                   else yy.load_gray_capture(spec["path"]))
        scorer = yy.PairScorer(dataset)
        glyphs = {}
        for text in PAIRS + WORDS:
            for char in text:
                codepoint = ord(char)
                if codepoint in glyphs or codepoint not in dataset["cells"]:
                    continue
                cell = dataset["cells"][codepoint]
                glyphs[str(codepoint)] = {
                    "w": cell["width"], "h": cell["height"],
                    "left": cell["left"], "top": cell["top"],
                    # Exact delivered levels: Gray codes map p/7 without
                    # rounding, so the browser draws the captured coverage.
                    "cover": [float(v) for v in cell["cover"]]}
        pairs = {}
        for text in all_pairs:
            left, right = ord(text[0]), ord(text[1])
            table = {}
            for cid, controls in zip(combo_ids, combos):
                evaluation = scorer.evaluate_pair(left, right, controls)
                table[cid] = {
                    "ch": evaluation["chosen"], "mn": evaluation["minimizing_steps"],
                    "bd": evaluation["boundary_hit"], "fb": evaluation["fallback"],
                    # Full precision: the browser redoes the argmin bit-exactly.
                    "costs": [None if c["cost"] is None else float(c["cost"])
                              for c in evaluation["candidates"]],
                    "inter": [round4(c.get("interaction")) for c in evaluation["candidates"]],
                    "att": [round4(c.get("attention_sum")) for c in evaluation["candidates"]],
                    "ov": [c.get("overlaps", 0) for c in evaluation["candidates"]],
                    "fa": [c.get("faces", 0) for c in evaluation["candidates"]],
                    "co": [c.get("corners", 0) for c in evaluation["candidates"]],
                    "ok": [c["valid"] for c in evaluation["candidates"]],
                    "why": [c.get("reason") for c in evaluation["candidates"]],
                    "fld": [[round4(v) for v in
                             (c.get("fields", {}).get("distance_disagreement"),
                              c.get("fields", {}).get("strength_product"),
                              c.get("fields", {}).get("distance_sum"),
                              c.get("fields", {}).get("orientation"))]
                            if c["valid"] else None for c in evaluation["candidates"]],
                }
            metric = yy.metric_step(dataset, left, right)
            pairs[text] = {"codepoints": [left, right], "metric": metric,
                           "steps": [metric + delta for delta in yy.CANDIDATE_DELTAS],
                           "table": table}
        captured_words = {}
        for word in WORDS:
            try:
                baseline = yy.captured_source_word_origins(dataset, word)
            except ValueError:
                continue
            captured_words[word] = {
                "origins": baseline["origins"],
                "draw_steps": [gap["draw_step"] for gap in baseline["gaps"]],
                "increments_px": [gap["advance_px"] for gap in baseline["gaps"]],
            }
        data["datasets"].append({"label": spec["label"], "profile": dataset["profile"],
                                 "size_px": dataset["size_px"],
                                 "source_path": dataset["source_path"],
                                 "glyphs": glyphs, "pairs": pairs,
                                 "captured_words": captured_words})
        print(f"built {spec['label']}: {len(pairs)} pairs x {len(combos)} settings")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--spec", action="append", nargs=3, required=True,
                        metavar=("LABEL", "PROFILE", "PATH"),
                        help="repeatable: label mono|gray capture-path")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must be new")
    specs = [{"label": label, "profile": profile, "path": path}
             for label, profile, path in args.spec]
    for spec in specs:
        if spec["profile"] not in ("mono", "gray"):
            parser.error("profile must be mono or gray")
    data = build_page_data(specs)
    root = Path(__file__).resolve().parent
    template = (root / "yinyangfit_interactive_template.html").read_text()
    app_js = (root / "yinyangfit_interactive_app.js").read_text()
    wiring_js = (root / "yinyangfit_interactive_wiring.js").read_text()
    if "title=" in template or "title=" in wiring_js or "title=" in app_js:
        raise ValueError("native title tooltips are forbidden; use page text")
    payload = json.dumps(data, separators=(",", ":"), allow_nan=False)
    page = template.replace("__YY_DATA__", payload)
    page = page.replace("__YY_APP_JS__", app_js)
    page = page.replace("__YY_WIRING_JS__", wiring_js)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "page-data.json").write_text(json.dumps(data, indent=2) + "\n")
    (args.output / "index.html").write_text(page)
    manifest = {"model": data["model"], "implementation": data["implementation"],
                "datasets": [d["label"] for d in data["datasets"]],
                "pairs": data["pairs"], "words": data["words"],
                "combos": len(data["combos"]),
                "page_bytes": len(page.encode()),
                "data_bytes": len(payload.encode())}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
