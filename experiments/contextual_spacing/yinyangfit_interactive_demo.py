#!/usr/bin/env python3
# cspell:words figcaption inputmode minmax roboto Roboto Segoe yinyangfit
"""Build the self-contained editable YinYang demo.

Embeds the unchanged compute engine, the shared visualization module and
the shared app text helpers plus the full captured ASCII repertoire,
advances and pair kerning for one sample (Roboto 16, Mono and Gray) from
the reviewed v3 page. No network, no worker; each shown gap runs the same
scorePair path as the page, with the same wrap/validate/metric helpers.
The previous fixed-excerpt demo stays untouched as a backup.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SITE = (REPO / "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3"
        / "site-reviewed/index.html")
OUT_DIR = (REPO / "out/diagnostics/contextual-spacing/yinyang-editable-preview")

CASE_ID = "roboto-16"
DEMO_TEXT = "AV To og qj\nPack my box"

DEMO_CSS = """
html,body{background:transparent;margin:0;padding:0}
body{font-family:var(--font-sans,system-ui,-apple-system,"Segoe UI",sans-serif);
color:var(--foreground,#161616);line-height:1.45;font-size:.9rem}
h1{font-size:1.15rem;margin:.25rem 0}
p{margin:.3rem 0;max-width:44rem}
.yy-chain{color:var(--muted-foreground,#444)}
.controls{display:flex;flex-wrap:wrap;gap:.6rem 1.25rem;margin:.5rem 0}
.control{display:flex;flex-direction:column;gap:.15rem;min-width:min(100%,12rem);flex:1 1 12rem}
.control label{font-weight:600;font-size:.85rem}
.control output{font-weight:600}
input[type=range]{display:block;width:100%;max-width:100%;min-width:0;box-sizing:border-box;margin:0}
textarea{font:inherit;width:100%;box-sizing:border-box;padding:.3rem .5rem;background:transparent;
color:var(--foreground,#161616);border:1px solid var(--border,#737373);resize:vertical}
button{font:inherit;padding:.3rem .6rem;background:var(--foreground,#161616);
color:var(--background,#fff);border:1px solid var(--foreground,#161616);cursor:pointer}
button.secondary{background:transparent;color:var(--foreground,#161616)}
.precise{display:flex;align-items:baseline;gap:.4rem;font-size:.8rem;color:var(--muted-foreground,#444)}
.precise input{font:inherit;width:5.5rem;padding:.1rem .35rem;background:transparent;
color:var(--foreground,#161616);border:1px solid var(--border,#737373)}
.views{display:grid;gap:.75rem;grid-template-columns:repeat(auto-fit,minmax(min(100%,17rem),1fr))}
figure{margin:0;min-width:0;overflow-x:auto;max-width:100%}
canvas{border:none;background:white;display:block;height:auto}
canvas.yy-ink{width:auto;max-width:none}
canvas.yy-strip{image-rendering:pixelated}

figcaption{font-size:.8rem;color:var(--muted-foreground,#444);margin-top:.15rem}
.yy-note{font-size:.8rem;color:var(--muted-foreground,#444)}
.yy-error{font-size:.8rem;color:#b00020}
.yy-error:empty{display:none}
.yy-legend{font-size:.8rem;color:var(--muted-foreground,#444)}
details{margin-top:.5rem}
"""

DEMO_JS = """
(function () {
"use strict";
var LETTER_CAP = 32, LEGEND_CAP = 24, PITCH = DEMO_PITCH;
var decoded = { mono: {}, gray: {} };
function decode(profile, g) {
  if (profile === "mono") {
    return { w: g.w, h: g.h, left: g.left, top: g.top,
      cover: Array.prototype.map.call(g.cover, function (s) {
        return s === "1" ? 1 : 0; }) };
  }
  return { w: g.w, h: g.h, left: g.left, top: g.top,
    cover: Array.prototype.map.call(g.cover, function (s) {
      return (s.charCodeAt(0) - 48) / 7; }) };
}
Object.keys(DEMO_CELLS.mono).forEach(function (cp) {
  decoded.mono[cp] = decode("mono", DEMO_CELLS.mono[cp]); });
Object.keys(DEMO_CELLS.gray).forEach(function (cp) {
  decoded.gray[cp] = decode("gray", DEMO_CELLS.gray[cp]); });
var sessions = {};
function sessionFor(profile) {
  if (!sessions[profile]) {
    sessions[profile] = YYCompute.createSession(decoded[profile]);
  }
  return sessions[profile];
}
var state = { cohesion: 1.1, reach: 2, falloff: 2, profile: "mono",
  text: DEMO_TEXT };
function $(id) { return document.getElementById(id); }
function hasGlyph(cp) {
  return Object.prototype.hasOwnProperty.call(decoded[state.profile],
    String(cp));
}
function formatCp(cp) {
  var h = cp.toString(16).toUpperCase();
  while (h.length < 4) h = "0" + h;
  return "U+" + h;
}
function errorMessage(cp) {
  if (cp === 9) return "tabs are not supported (U+0009); use line breaks.";
  if (cp === 13) {
    return "carriage returns are not supported (U+000D); use line breaks.";
  }
  return "character (" + formatCp(cp) + ") is outside the captured " +
    state.profile + " repertoire.";
}
var gridCache = {}, gridOrder = [];
function fieldFor(cell, cp, ox, oy, frame) {
  // The grid samples frame-relative query points, so the display frame
  // joins the cache identity alongside the drawn origin and controls.
  var key = cp + "|" + ox + "|" + oy + "|" + state.reach + "|" +
    state.falloff + "|" + frame.x0 + "|" + frame.y0 + "|" + frame.w +
    "|" + frame.h;
  if (gridCache[key]) return gridCache[key];
  var grid = YYCompute.glyphFieldGrid(cell, ox, state.reach,
    state.falloff, frame, oy);
  gridCache[key] = grid;
  gridOrder.push(key);
  while (gridOrder.length > 96) delete gridCache[gridOrder.shift()];
  return grid;
}
function drawInk(canvasId, lines, originsPerLine, profile) {
  var glyphs = decoded[profile];
  var bounds = LetterSpacing.linesBounds(glyphs, lines, originsPerLine,
    PITCH);
  var canvas = $(canvasId), ctx = canvas.getContext("2d");
  var off = LetterSpacing.fitCanvas(canvas, bounds, 1);
  ctx.save();
  ctx.translate(off.dx, off.dy);
  ctx.fillStyle = "#fff";
  ctx.fillRect(bounds.x0, bounds.y0, bounds.x1 - bounds.x0,
    bounds.y1 - bounds.y0);
  lines.forEach(function (word, li) {
    var origins = originsPerLine[li];
    for (var k = 0; k < word.length; k++) {
      var g = glyphs[String(word.charCodeAt(k))];
      if (!g) continue;
      LetterSpacing.drawCell(ctx, profile, g, origins[k], li * PITCH, 1);
    }
  });
  ctx.restore();
}
function paint() {
  var text = state.text;
  var check = LetterSpacing.validatePreviewText(text, hasGlyph);
  if (!check.ok) {
    $("demo-text-e").textContent =
      "Preview text not applied: " + errorMessage(check.codepoint);
    $("demo-note").textContent =
      "Showing the last valid text \\u2014 fix the preview text to update.";
    return;
  }
  $("demo-text-e").textContent = "";
  var wrapped = LetterSpacing.wrapPreviewText(text);
  var lines = wrapped.lines;
  var adv = DEMO_METRICS[state.profile].advances;
  var kern = DEMO_METRICS[state.profile].kern;
  var session = sessionFor(state.profile);
  var needed = LetterSpacing.textPairs(lines);
  var pairSteps = {}, metricOf = {};
  needed.forEach(function (name) {
    var left = name.charCodeAt(0), right = name.charCodeAt(1);
    var metric = LetterSpacing.metricStep(adv, kern, left, right);
    metricOf[name] = metric;
    var out = session.scorePair(name, String(left), String(right),
      metric, state.reach, state.falloff, state.cohesion);
    pairSteps[name] = { metric: metric, step: out.chosen,
      fallback: out.fallback };
  });
  var spaceMetrics = {};
  lines.forEach(function (line) {
    for (var i = 0; i + 1 < line.length; i++) {
      var a = line[i], b = line[i + 1];
      if (a === " " || b === " ") {
        spaceMetrics[a + b] = LetterSpacing.metricStep(adv, kern,
          a.charCodeAt(0), b.charCodeAt(0));
      }
    }
  });
  var layout = LetterSpacing.layoutLines(pairSteps, spaceMetrics, lines);
  if (layout.error) {
    $("demo-note").textContent =
      "Pair data is missing for this text; keeping the last valid view.";
    return;
  }
  var expOrigins = layout.lines.map(function (l) { return l.origins; });
  var capOrigins = lines.map(function (line) {
    return LetterSpacing.capturedOrigins(adv, kern, line);
  });
  drawInk("demo-source", lines, capOrigins, state.profile);
  drawInk("demo-field-ink", lines, expOrigins, state.profile);
  /* Letter strip: first LETTER_CAP letters at placed origins. */
  var glyphs = decoded[state.profile];
  var runs = [], index = 0, total = 0;
  for (var li = 0; li < lines.length; li++) {
    var origins = expOrigins[li], oy = li * PITCH;
    for (var k = 0; k < lines[li].length; k++) {
      var ch = lines[li][k];
      if (ch === " ") continue;
      total++;
      if (runs.length >= LETTER_CAP) { index++; continue; }
      var g = glyphs[String(ch.charCodeAt(0))];
      if (!g) { index++; continue; }
      var ext = YYCompute.cellExtent(g);
      if (!ext) { index++; continue; }
      runs.push({ cell: g, ox: origins[k], oy: oy, ext: ext,
        colorIndex: index, ch: ch, li: li, k: k });
      index++;
    }
  }
  var capLines = capOrigins;
  var bounds = runs.map(function (run) {
    var ox = capLines[run.li][run.k];
    return [ox + run.ext.x0, ox + run.ext.x1 + 1,
            run.oy + run.ext.y0, run.oy + run.ext.y1 + 1];
  });
  var frame = YYVisual.frameForRuns(bounds, runs.length);
  var grids = runs.map(function (run) {
    return fieldFor(run.cell, String(run.ch.charCodeAt(0)), run.ox,
      run.oy, frame);
  });
  YYVisual.drawExcerptField($("demo-field"), grids, frame, runs,
    state.profile);
  var legend = $("demo-legend");
  legend.innerHTML = "";
  legend.appendChild(document.createTextNode("Letter fields: "));
  runs.slice(0, LEGEND_CAP).forEach(function (run) {
    var s = document.createElement("span");
    s.textContent = run.ch;
    s.style.color = YYVisual.letterColor(run.colorIndex);
    s.style.fontWeight = "700";
    legend.appendChild(s);
  });
  if (runs.length > LEGEND_CAP) {
    legend.appendChild(document.createTextNode(
      "\\u2026+" + (runs.length - LEGEND_CAP) + " more"));
  }
  if (!runs.length) {
    legend.appendChild(document.createTextNode("(no letters shown)"));
  }
  legend.appendChild(document.createTextNode(
    " \\u2014 colors mark letters, never scores."));
  var at = {};
  runs.forEach(function (run) { at[run.li + ":" + run.k] = true; });
  var changed = [];
  for (var q = 0; q < lines.length; q++) {
    for (var m = 0; m + 1 < lines[q].length; m++) {
      var pair = lines[q][m] + lines[q][m + 1];
      if (pair.indexOf(" ") >= 0) continue;
      if (!at[q + ":" + m] || !at[q + ":" + (m + 1)]) continue;
      var d = pairSteps[pair].step - metricOf[pair];
      if (d !== 0) changed.push(pair + " " + (d > 0 ? "+" : "") + d);
    }
  }
  var cap = $("demo-field-cap");
  cap.textContent = total > runs.length ?
    "Letter fields: first " + runs.length + " of " + total +
      " letters as placed." :
    "Letter fields as placed" +
      (runs.length ? ": \\u201c" + runs.map(function (r) {
        return r.ch; }).join("") + "\\u201d." : ".");
  var note = (changed.length ? "Changed here: " + changed.join(" \\u00b7 ") + ". "
    : "Same as Source here. ") +
    "Reach spreads every blob; falloff sharpens the fade; cohesion moves " +
    "letters to their chosen widths. Scored exactly on demand with the " +
    "same engine as the page.";
  if (wrapped.capped) {
    note += " Showing the first " + LetterSpacing.MAX_LINES + " of " +
      wrapped.total + " wrapped lines.";
  }
  $("demo-note").textContent = note;
  window.DEMO_SUMMARY = { choices: pairSteps, lines: lines.length,
    cohesion: state.cohesion, reach: state.reach, falloff: state.falloff,
    profile: state.profile };
}
var paintTimer = null;
function schedule() {
  if (paintTimer) clearTimeout(paintTimer);
  paintTimer = setTimeout(function () { paintTimer = null; paint(); }, 150);
}
function bindRange(id, numId, key, parse) {
  $(id).addEventListener("input", function (e) {
    state[key] = parseFloat(e.target.value);
    $(numId).value = e.target.value;
    schedule();
  });
  $(numId).addEventListener("change", function (e) {
    var v = parseFloat(e.target.value);
    if (!isFinite(v)) return;
    if (key === "cohesion" && (v < 0 || v > 2)) return;
    if (key === "reach" && (v < 0.25 || v > 12)) return;
    if (key === "falloff" && !(v > 0 && v <= 16)) return;
    state[key] = v;
    paint();
  });
}
$("demo-text").value = state.text;
$("demo-text").addEventListener("input", function (e) {
  state.text = e.target.value;
  $("demo-restore").hidden = (e.target.value === DEMO_TEXT);
  schedule();
});
$("demo-restore").addEventListener("click", function () {
  state.text = DEMO_TEXT;
  $("demo-text").value = DEMO_TEXT;
  $("demo-restore").hidden = true;
  paint();
});
document.querySelectorAll('input[name="demo-profile"]').forEach(
  function (input) {
    input.addEventListener("change", function () {
      state.profile = document.querySelector(
        'input[name="demo-profile"]:checked').value;
      paint();
    });
  });
bindRange("demo-c-in", "demo-c-num", "cohesion");
bindRange("demo-r-in", "demo-r-num", "reach");
bindRange("demo-f-in", "demo-f-num", "falloff");
paint();
})();
"""


def load_table(label):
    data_path = SITE.parent / f"data/{label}.js"
    return json.loads(re.search(r"= (\{.*\});\s*$", data_path.read_text(),
                               re.S).group(1))


def main():
    boot = json.loads(re.search(
        r'<script type="application/json" id="yy-boot">(.*?)</script>',
        SITE.read_text(), re.S).group(1))
    case = next(c for c in boot["cases"] if c["id"] == CASE_ID)
    assert case["line_pitch"] > 0, "demo needs the line pitch"
    cells, metrics = {}, {}
    for profile in ("mono", "gray"):
        packed = case["profiles"][profile]["glyphs"]
        table = load_table(f"{CASE_ID}-{profile}")
        # Full captured repertoire: every cell the dataset ships.
        cells[profile] = {cp: packed[cp] for cp in sorted(packed)}
        metrics[profile] = {"advances": table["advances"],
                            "kern": table["kern"]}
        for ch in DEMO_TEXT:
            if ch != "\n":
                assert str(ord(ch)) in cells[profile], \
                    f"demo default outside {profile} repertoire: U+{ord(ch):04X}"
    app_js = (HERE / "yinyangfit_interactive_v3_app.js").read_text()
    compute_js = (HERE / "yinyangfit_interactive_v3_compute.js").read_text()
    visual_js = (HERE / "yinyangfit_interactive_v3_visual.js").read_text()
    for name, content in (("app", app_js), ("compute", compute_js),
                          ("visual", visual_js)):
        if "title=" in content:
            raise ValueError(f"native title tooltips forbidden ({name})")
        if "</script" in content:
            raise ValueError("embedded source cannot carry raw terminator")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    page = ("<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<title>YinYang editable preview: Roboto 16</title>\n"
            "<style>" + DEMO_CSS + "</style>\n</head>\n<body>\n"
            "<h1>How the three knobs change this text</h1>\n"
            "<p class=\"yy-chain\">The preview text, drawn as placed: "
            "each shown letter carries its own fading field in its own color, "
            "blended where they overlap for display only. Darker means stronger; "
            "the dark shapes are the actual ink. Reach spreads every blob; "
            "falloff sharpens the fade. Cohesion moves letters to their chosen "
            "widths. Blobs show components, not the final score: gaps are "
            "still scored one pair at a time, so the blended overlap is not "
            "the objective. Every number below is computed live for Roboto 16, "
            "the same engine as the page.</p>\n"
            "<div class=\"controls\">\n"
            "<div class=\"control\"><label for=\"demo-text\">Preview text</label>\n"
            "<textarea id=\"demo-text\" rows=\"3\" spellcheck=\"false\"></textarea>\n"
            "<p class=\"yy-error\" id=\"demo-text-e\" role=\"status\"></p>\n"
            "<p><button id=\"demo-restore\" type=\"button\" class=\"secondary\" "
            "hidden>Restore sample text</button></p></div>\n"
            "<div class=\"control\"><label for=\"demo-c-in\">Target cohesion "
            "<output id=\"demo-c\"></output></label>\n"
            "<input type=\"range\" id=\"demo-c-in\" min=\"0\" max=\"2\" step=\"0.05\" value=\"1.1\">\n"
            "<p class=\"precise\"><label for=\"demo-c-num\">Exact</label>\n"
            "<input id=\"demo-c-num\" value=\"1.1\" inputmode=\"decimal\"></p></div>\n"
            "<div class=\"control\"><label for=\"demo-r-in\">Interaction reach "
            "<output id=\"demo-r\"></output></label>\n"
            "<input type=\"range\" id=\"demo-r-in\" min=\"0.5\" max=\"6\" step=\"0.25\" value=\"2\">\n"
            "<p class=\"precise\"><label for=\"demo-r-num\">Exact px</label>\n"
            "<input id=\"demo-r-num\" value=\"2\" inputmode=\"decimal\"></p></div>\n"
            "<div class=\"control\"><label for=\"demo-f-in\">Proximity falloff "
            "<output id=\"demo-f\"></output></label>\n"
            "<input type=\"range\" id=\"demo-f-in\" min=\"0.5\" max=\"10\" step=\"0.5\" value=\"2\">\n"
            "<p class=\"precise\"><label for=\"demo-f-num\">Exact</label>\n"
            "<input id=\"demo-f-num\" value=\"2\" inputmode=\"decimal\"></p></div>\n"
            "<div class=\"control\"><span id=\"demo-profile-label\">Look</span>\n"
            "<label><input type=\"radio\" name=\"demo-profile\" value=\"mono\" "
            "checked>Black and white</label>\n"
            "<label><input type=\"radio\" name=\"demo-profile\" value=\"gray\">"
            "Grayscale</label></div>\n"
            "</div>\n"
            "<div class=\"views\">\n"
            "<figure><canvas id=\"demo-source\" class=\"yy-ink\"></canvas>\n"
            "<figcaption>Source.</figcaption></figure>\n"
            "<figure><canvas id=\"demo-field-ink\" class=\"yy-ink\"></canvas>\n"
            "<figcaption>Adjusted.</figcaption></figure>\n"
            "</div>\n"
            "<figure><canvas id=\"demo-field\" class=\"yy-strip\"></canvas>\n"
            "<figcaption id=\"demo-field-cap\">Letter fields.</figcaption></figure>\n"
            "<p class=\"yy-legend\" id=\"demo-legend\"></p>\n"
            "<p class=\"yy-note\" id=\"demo-note\" role=\"status\"></p>\n"
            "<details><summary>About this demo</summary>\n"
            "<p class=\"yy-note\">Each blob is one letter field g / (1 + (distance / "
            "reach)^falloff) at its drawn position; Gray g is delivered coverage at "
            "each letter's nearest ink. Each shown letter keeps its own hue by "
            "position, blended where they overlap by standard alpha compositing "
            "for display only; scoring stays one pair at a time, attention-weighting "
            "the fields with steeper strength fields, equidistance and "
            "opposing-gradient factors, then normalizing, so the blended overlap is "
            "not the objective. Per-letter hues are a project display choice; any "
            "resemblance to YinYangFit's grouping-blob illustrations is "
            "presentational. Ink cells draw opaque on top; the score "
            "evaluates the full window, with inside-ink points contributing at "
            "zero distance. Neither cohesion nor field brightness "
            "measures optical quality.</p>\n"
            "</details>\n"
            "<script>\n" + app_js + "\n</script>\n"
            "<script>\n" + compute_js + "\n</script>\n"
            "<script>\n" + visual_js + "\n</script>\n"
            "<script>\nvar DEMO_CELLS = " + json.dumps(cells) + ";\n"
            "var DEMO_TEXT = " + json.dumps(DEMO_TEXT) + ";\n"
            "var DEMO_METRICS = " + json.dumps(metrics) + ";\n"
            "var DEMO_PITCH = " + json.dumps(case["line_pitch"]) + ";\n"
            + DEMO_JS + "\n</script>\n"
            "</body>\n</html>\n")
    out = OUT_DIR / "yinyang-live-demo.html"
    out.write_text(page)
    print(str(out))


if __name__ == "__main__":
    sys.exit(main())
