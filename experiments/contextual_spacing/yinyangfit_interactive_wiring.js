/* DOM wiring for the feasibility page. Depends on YinYangInteractive (app JS). */
(function () {
  "use strict";
  var YY = typeof YinYangInteractive !== "undefined" ? YinYangInteractive : null;
  var data = JSON.parse(document.getElementById("yy-data").textContent);
  if (YY && YY !== null && typeof module !== "undefined" && module.exports) {
    /* node */
  }
  function $(id) {
    return document.getElementById(id);
  }
  var DEFAULT_INDEX = { cohesion: 4, scale: 2, falloff: 2 };

  function initSelect(id, items, labels) {
    var el = $(id);
    el.innerHTML = "";
    items.forEach(function (item, i) {
      var opt = document.createElement("option");
      opt.value = String(i);
      opt.textContent = labels ? labels[i] : String(item);
      el.appendChild(opt);
    });
  }

  function state() {
    return {
      dataset: data.datasets[Number($("yy-dataset").value)],
      ci: Number($("yy-cohesion").value),
      si: Number($("yy-scale").value),
      qi: Number($("yy-falloff").value),
      pair: data.pairs[Number($("yy-pair").value)],
      word: data.words[Number($("yy-word").value)],
      zoom: Number($("yy-zoom").value),
    };
  }

  function cidOf(st) {
    return YY.comboId(st.ci, st.si, st.qi);
  }

  function refreshOutputs() {
    var d = data.controls;
    $("yy-cohesion-v").textContent = String(d.cohesion[Number($("yy-cohesion").value)]);
    $("yy-scale-v").textContent = String(d.feature_scale[Number($("yy-scale").value)]);
    $("yy-falloff-v").textContent = String(d.proximity_falloff[Number($("yy-falloff").value)]);
  }

  function glyphOf(ds, ch) {
    return ds.glyphs[String(ch.charCodeAt(0))];
  }

  function drawPair(canvasId, ds, pairName, step, scale, markOverlaps) {
    var canvas = $(canvasId);
    var ctx = canvas.getContext("2d");
    var left = glyphOf(ds, pairName[0]),
      right = glyphOf(ds, pairName[1]);
    var bounds = YY.pairBounds(left, right, step);
    var off = YY.fitCanvas(canvas, bounds, scale);
    ctx.save();
    ctx.translate(off.dx, off.dy);
    var leftSet = YY.cellSet(left, 0, 0);
    var rightSet = YY.cellSet(right, step, 0);
    var overlaps = {};
    var key;
    for (key in rightSet) if (leftSet[key]) overlaps[key] = true;
    ctx.fillStyle = "#fff";
    ctx.fillRect(
      bounds.x0 * scale,
      bounds.y0 * scale,
      (bounds.x1 - bounds.x0) * scale,
      (bounds.y1 - bounds.y0) * scale,
    );
    YY.drawCell(ctx, ds.profile, left, 0, 0, scale, markOverlaps, overlaps);
    YY.drawCell(ctx, ds.profile, right, step, 0, scale, markOverlaps, overlaps);
    ctx.restore();
    return overlaps;
  }

  function renderPair() {
    var st = state(),
      ds = st.dataset;
    var pairEntry = ds.pairs[st.pair];
    var cid = cidOf(st);
    var entry = pairEntry.table[cid];
    var chosen = YY.chosenStep(pairEntry, cid);
    var combo = data.combos[ciGlobal(st)];
    $("yy-identity").textContent =
      "Setting " +
      combo.identity.slice(0, 12) +
      " (cohesion " +
      combo.cohesion +
      ", scale " +
      combo.feature_scale +
      ", falloff " +
      combo.proximity_falloff +
      ")";
    drawPair("yy-metric1", ds, st.pair, pairEntry.metric, 1, false);
    drawPair("yy-metricN", ds, st.pair, pairEntry.metric, st.zoom, false);
    var overlaps = drawPair("yy-chosen1", ds, st.pair, chosen, 1, true);
    drawPair("yy-chosenN", ds, st.pair, chosen, st.zoom, true);
    $("yy-metric1-cap").textContent = "Metric placement, native size (step " + pairEntry.metric + ").";
    $("yy-chosen1-cap").textContent =
      "Chosen placement, native size (step " + chosen + ", delta " + (chosen - pairEntry.metric) + ").";
    var capN =
      "Chosen placement, magnified." +
      (entry.bd ? " Boundary minimum: the optimum sits at the candidate-domain edge." : "") +
      (entry.fb ? " Fallback: no valid candidate; metric retained." : "");
    $("yy-chosenN-cap").textContent = capN;
    renderTable(pairEntry, entry, chosen);
    renderWord();
  }

  function ciGlobal(st) {
    return st.ci * 16 + st.si * 4 + st.qi;
  }

  function renderTable(pairEntry, entry, chosen) {
    var host = $("yy-table");
    host.innerHTML = "";
    var table = document.createElement("table");
    var head = document.createElement("tr");
    [
      "candidate step",
      "delta vs metric",
      "cost",
      "interaction",
      "attention",
      "disagreement",
      "strength x",
      "distance sum",
      "orientation",
      "overlap",
      "faces",
      "corners",
      "status",
    ].forEach(function (h) {
      var th = document.createElement("th");
      th.textContent = h;
      head.appendChild(th);
    });
    table.appendChild(head);
    pairEntry.steps.forEach(function (step, i) {
      var tr = document.createElement("tr");
      var cells = [
        String(step),
        (step - pairEntry.metric >= 0 ? "+" : "") + (step - pairEntry.metric),
        entry.costs[i] === null ? "n/a" : entry.costs[i].toFixed(4),
        entry.inter[i] === null ? "n/a" : entry.inter[i].toFixed(4),
        entry.att[i] === null ? "n/a" : entry.att[i].toFixed(3),
        entry.fld[i] === null
          ? "n/a"
          : entry.fld[i]
              .map(function (v) {
                return v === null ? "n/a" : v.toFixed(3);
              })
              .join(" / "),
        String(entry.ov[i]),
        String(entry.fa[i]),
        String(entry.co[i]),
        !entry.ok[i] ? "invalid (" + entry.why[i] + ")" : step === chosen ? "chosen" : "evaluated",
      ];
      // fld groups four diagnostics into one column above; expand explicitly:
      var row = [cells[0], cells[1], cells[2], cells[3], cells[4]];
      if (entry.fld[i] === null) {
        row.push("n/a", "n/a", "n/a", "n/a");
      } else {
        entry.fld[i].forEach(function (v) {
          row.push(v === null ? "n/a" : v.toFixed(3));
        });
      }
      row.push(cells[6], cells[7], cells[8], cells[9]);
      row.forEach(function (text) {
        var td = document.createElement("td");
        td.textContent = text;
        tr.appendChild(td);
      });
      if (step === chosen && entry.ok[i]) tr.className = "chosen";
      if (!entry.ok[i]) tr.className = "invalid";
      table.appendChild(tr);
    });
    host.appendChild(table);
    var note = document.createElement("p");
    note.className = "meta";
    note.textContent =
      "Minimizing steps: [" +
      entry.mn.join(", ") +
      "]. " +
      "Ties within 1e-9 of the minimum break toward the metric step. " +
      (entry.bd ? "This setting hits the candidate-domain boundary." : "Interior minimum at this setting.");
    host.appendChild(note);
  }

  function renderWord() {
    var st = state(),
      ds = st.dataset;
    var cid = cidOf(st);
    var steps = YY.pairStepsFor(ds, cid);
    var missing = [];
    var word = st.word,
      i;
    for (i = 0; i + 1 < word.length; i++) {
      if (!steps[word[i] + word[i + 1]]) missing.push(word[i] + word[i + 1]);
    }
    if (missing.length) {
      $("yy-word-gaps").textContent = "Outside evaluated pair set: " + missing.join(", ");
      return;
    }
    var layout = YY.layoutWord(steps, word);
    if (layout.error) {
      $("yy-word-gaps").textContent = layout.error;
      return;
    }
    $("yy-word-gaps").textContent =
      "Experiment gaps (metric -> chosen): " +
      layout.gaps
        .map(function (g) {
          return g.pair + " " + g.metric + "->" + g.chosen;
        })
        .join("  ") +
      " Origins [" +
      layout.origins.join(", ") +
      "].";
    drawWordAt("yy-word1", ds, word, layout.origins, 1);
    drawWordAt("yy-wordN", ds, word, layout.origins, 4);
    renderCapturedWord(ds, word, layout.origins);
  }

  /* Draw one word's glyph cells at the given integer origins. */
  function drawWordAt(canvasId, ds, word, origins, scale) {
    var canvas = $(canvasId);
    var ctx = canvas.getContext("2d");
    var glyphs = [];
    for (var k = 0; k < word.length; k++) glyphs.push(glyphOf(ds, word[k]));
    var x0 = Infinity,
      x1 = -Infinity,
      y0 = Infinity,
      y1 = -Infinity;
    glyphs.forEach(function (g, k) {
      x0 = Math.min(x0, origins[k] + g.left);
      x1 = Math.max(x1, origins[k] + g.left + g.w);
      y0 = Math.min(y0, g.top);
      y1 = Math.max(y1, g.top + g.h);
    });
    canvas.width = Math.max(1, (x1 - x0) * scale);
    canvas.height = Math.max(1, (y1 - y0) * scale);
    ctx.save();
    ctx.translate(-x0 * scale, -y0 * scale);
    ctx.fillStyle = "#fff";
    ctx.fillRect(x0 * scale, y0 * scale, (x1 - x0) * scale, (y1 - y0) * scale);
    glyphs.forEach(function (g, k) {
      YY.drawCell(ctx, ds.profile, g, origins[k], 0, scale, false, null);
    });
    ctx.restore();
  }

  /* Captured-source baseline row: embedded fractional-pen draws, no controls. */
  function renderCapturedWord(ds, word, experimentOrigins) {
    var cw = ds.captured_words ? ds.captured_words[word] : null;
    if (!cw) {
      $("yy-cword-gaps").textContent = "Captured-source baseline unavailable for " + word + ".";
      return;
    }
    $("yy-cword-gaps").textContent =
      "Captured-source draws [" +
      cw.origins.join(", ") +
      "] (per-gap draw steps " +
      cw.draw_steps.join(", ") +
      "). Experiment [" +
      experimentOrigins.join(", ") +
      "].";
    drawWordAt("yy-cword1", ds, word, cw.origins, 1);
    drawWordAt("yy-cwordN", ds, word, cw.origins, 4);
  }

  function refreshDatasetMeta() {
    var ds = state().dataset;
    $("yy-dataset-meta").textContent =
      ds.label + ": " + ds.profile + ", " + ds.size_px + " px, source " + ds.source_path.split("/").slice(-1)[0];
    $("yy-model").textContent =
      "Model " +
      data.model +
      ", implementation " +
      data.implementation.slice(0, 12) +
      ". No training; no optical approval.";
  }

  function refreshAll() {
    refreshOutputs();
    refreshDatasetMeta();
    renderPair();
  }

  function init() {
    initSelect(
      "yy-dataset",
      data.datasets,
      data.datasets.map(function (d) {
        return d.label;
      }),
    );
    initSelect("yy-pair", data.pairs, data.pairs);
    initSelect("yy-word", data.words, data.words);
    ["yy-dataset", "yy-pair", "yy-word", "yy-zoom"].forEach(function (id) {
      $(id).addEventListener("change", refreshAll);
    });
    ["yy-cohesion", "yy-scale", "yy-falloff"].forEach(function (id) {
      $(id).addEventListener("input", refreshAll);
    });
    $("yy-reset").addEventListener("click", function () {
      $("yy-cohesion").value = String(DEFAULT_INDEX.cohesion);
      $("yy-scale").value = String(DEFAULT_INDEX.scale);
      $("yy-falloff").value = String(DEFAULT_INDEX.falloff);
      refreshAll();
    });
    refreshAll();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
