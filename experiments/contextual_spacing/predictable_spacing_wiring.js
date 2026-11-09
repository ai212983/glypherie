/* cspell:words valuetext
 * DOM wiring for the predictable spacing prototype. */
(function () {
  "use strict";
  var PS = typeof PredictableSpacing !== "undefined" ? PredictableSpacing : null;
  var boot = JSON.parse(document.getElementById("ps-boot").textContent);
  window.PS_TABLES = window.PS_TABLES || {};

  function $(id) {
    return document.getElementById(id);
  }
  function el(tag, text, cls) {
    var n = document.createElement(tag);
    if (text !== undefined && text !== null) n.textContent = text;
    if (cls) n.className = cls;
    return n;
  }

  var state = { caseId: "roboto-16", profile: "mono", zoom: 1, optical: 0, letter: 0, pair: null };
  var pendingTable = {};
  /* Monotonic load generation: only the latest selected sample may paint. */
  var focusSeq = 0;

  function cases() {
    return boot.cases;
  }
  function findCase(id) {
    for (var i = 0; i < boot.cases.length; i++) if (boot.cases[i].id === id) return boot.cases[i];
    return boot.cases[0];
  }
  function datasetOf(c, profile) {
    return c.profiles[profile];
  }
  function tableLabel(c, profile) {
    return c.id + "-" + profile;
  }

  function decodedGlyphs(c, profile) {
    var ds = datasetOf(c, profile);
    if (ds.decoded) return ds.decoded;
    var out = {};
    Object.keys(ds.glyphs).forEach(function (cp) {
      var g = ds.glyphs[cp],
        s = g.cover,
        cover;
      if (profile === "mono") {
        cover = new Array(s.length);
        for (var i = 0; i < s.length; i++) cover[i] = s[i] === "1" ? 1 : 0;
      } else {
        cover = new Array(s.length);
        for (var j = 0; j < s.length; j++) cover[j] = (s.charCodeAt(j) - 48) / 7;
      }
      out[cp] = { w: g.w, h: g.h, left: g.left, top: g.top, cover: cover };
    });
    ds.decoded = out;
    return out;
  }

  function ensureTable(c, profile, done) {
    var label = tableLabel(c, profile);
    if (window.PS_TABLES[label]) {
      done(window.PS_TABLES[label]);
      return;
    }
    if (!pendingTable[label]) {
      pendingTable[label] = [];
      var script = document.createElement("script");
      script.src = "data/ps-" + label + ".js";
      script.onload = function () {
        var list = pendingTable[label];
        delete pendingTable[label];
        list.forEach(function (fn) {
          fn(window.PS_TABLES[label]);
        });
      };
      script.onerror = function () {
        delete pendingTable[label];
        $("ps-sample-note").textContent = "Sample data for " + label + " did not load; showing defaults.";
      };
      document.head.appendChild(script);
    }
    pendingTable[label].push(done);
  }

  /* ---- focused comparison ---- */

  function adjustedOrigins(c, profile, table) {
    var ds = datasetOf(c, profile);
    var gaps = ds.gaps.map(function (line) {
      return line;
    });
    return PS.layoutLines(ds.lines, gaps, table.pairs, profile, state.optical, state.letter);
  }

  function gapStats(c, profile, table) {
    var changed = false,
      guard = false;
    var ds = datasetOf(c, profile);
    ds.gaps.forEach(function (line) {
      line.forEach(function (g) {
        if (g.space) return;
        var rec = table.pairs[g.pair];
        if (!rec) return;
        var step = PS.autoStep(rec, state.optical);
        if (step !== rec.metric) changed = true;
        if (
          state.optical > 0 &&
          rec.minimum !== null &&
          rec.minimum !== undefined &&
          step === rec.minimum &&
          rec.optical_adjustment !== null &&
          rec.advance +
            PS.pixelRound(rec.metric_adjustment * (1 - state.optical) + rec.optical_adjustment * state.optical) <
            rec.minimum
        )
          guard = true;
      });
    });
    if (state.letter !== 0) changed = true;
    return { changed: changed, guard: guard };
  }

  function drawLines(canvas, glyphs, profile, words, lineOrigins, pitch, bounds, scale) {
    var ctx = canvas.getContext("2d");
    var off = PS.fitCanvas(canvas, bounds, scale);
    ctx.save();
    ctx.translate(off.dx, off.dy);
    ctx.fillStyle = "#fff";
    ctx.fillRect(
      bounds.x0 * scale,
      bounds.y0 * scale,
      (bounds.x1 - bounds.x0) * scale,
      (bounds.y1 - bounds.y0) * scale,
    );
    var count = 0;
    words.forEach(function (word, li) {
      var origins = lineOrigins[li];
      for (var k = 0; k < word.length; k++) {
        var g = glyphs[String(word.charCodeAt(k))];
        if (!g) continue;
        count += PS.drawCell(ctx, profile, g, origins[k], li * pitch, scale);
      }
    });
    ctx.restore();
    return count;
  }

  function renderFocus(table) {
    var c = findCase(state.caseId),
      profile = state.profile;
    var ds = datasetOf(c, profile),
      glyphs = decodedGlyphs(c, profile);
    $("ps-focus-title").textContent =
      c.family_label + " " + c.size_px + " px" + (profile === "mono" ? " (black and white)" : " (grayscale)");
    var adjusted = table
      ? adjustedOrigins(c, profile, table)
      : ds.captured.map(function (o) {
          return o.slice();
        });
    var capOrigins = ds.captured;
    var union = (function () {
      var words = ds.lines;
      var b1 = PS.linesBounds(glyphs, words, adjusted, c.line_pitch);
      var b2 = PS.linesBounds(glyphs, words, capOrigins, c.line_pitch);
      return {
        x0: Math.min(b1.x0, b2.x0),
        x1: Math.max(b1.x1, b2.x1),
        y0: Math.min(b1.y0, b2.y0),
        y1: Math.max(b1.y1, b2.y1),
      };
    })();
    var zoom = state.zoom;
    var n0 = drawLines($("ps-original"), glyphs, profile, ds.lines, capOrigins, c.line_pitch, union, zoom);
    var n1 = drawLines($("ps-adjusted"), glyphs, profile, ds.lines, adjusted, c.line_pitch, union, zoom);
    $("ps-original-cap").textContent = "Original" + (n0 ? "" : " (no ink drawn)") + ".";
    var note = $("ps-sample-note");
    if (table) {
      var stats = gapStats(c, profile, table);
      if (!stats.changed) {
        note.textContent =
          "Original spacing used at this setting. " +
          "Steps move in whole pixels, so small adjustments may show no change.";
      } else if (stats.guard) {
        note.textContent = "Optical limit reached for at least one gap. " + "Further correction keeps that placement.";
      } else {
        note.textContent = "";
      }
    } else {
      note.textContent = "Loading sample data.";
    }
    $("ps-adjusted-cap").textContent =
      state.optical === 0 && state.letter === 0 ? "Adjusted (original spacing)." : "Adjusted.";
    renderPair(table, adjusted);
    renderDiagnostics(table, adjusted);
  }

  /* ---- sample selection ---- */

  function sampleLabel(c) {
    return c.family_label + " " + c.size_px + " px";
  }

  function refreshSampleOptions() {
    var sel = $("ps-sample");
    if (!sel.options.length) {
      cases().forEach(function (c) {
        var opt = document.createElement("option");
        opt.value = c.id;
        opt.textContent = sampleLabel(c);
        sel.appendChild(opt);
      });
    }
    sel.value = state.caseId;
  }

  /* ---- pair inspection (collapsed by default) ---- */

  function renderPair(table, adjusted) {
    if (!table) {
      $("ps-pair-note").textContent = "Loading sample data.";
      return;
    }
    var c = findCase(state.caseId),
      profile = state.profile;
    var options = Object.keys(table.pairs).sort();
    var sel = $("ps-pair");
    if (!sel.options.length || sel.dataset.caseId !== state.caseId || sel.dataset.profile !== profile) {
      sel.innerHTML = "";
      options.forEach(function (name) {
        var opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name.split("").join(" + ");
        sel.appendChild(opt);
      });
      sel.dataset.caseId = state.caseId;
      sel.dataset.profile = profile;
    }
    if (options.indexOf(state.pair) < 0) state.pair = options[0];
    sel.value = state.pair;
    var rec = table.pairs[state.pair];
    if (!rec) {
      $("ps-pair-note").textContent = "Pair data is loading.";
      return;
    }
    var ds = datasetOf(c, profile),
      gap;
    ds.gaps.some(function (line) {
      return line.some(function (g) {
        if (g.pair !== state.pair || g.space) return false;
        gap = g;
        return true;
      });
    });
    var original = PS.layoutLines([state.pair], [[gap]], table.pairs, profile, 0, 0)[0][1];
    var step = PS.layoutLines([state.pair], [[gap]], table.pairs, profile, state.optical, state.letter)[0][1];
    var glyphs = decodedGlyphs(c, profile);
    var left = glyphs[String(state.pair.charCodeAt(0))];
    var right = glyphs[String(state.pair.charCodeAt(1))];
    [
      ["ps-pair-metric", original],
      ["ps-pair-chosen", step],
    ].forEach(function (item) {
      var canvas = $(item[0]),
        ctx = canvas.getContext("2d");
      var bounds = {
        x0: Math.min(left.left, item[1] + right.left),
        x1: Math.max(left.left + left.w, item[1] + right.left + right.w),
        y0: Math.min(left.top, right.top),
        y1: Math.max(left.top + left.h, right.top + right.h),
      };
      var off = PS.fitCanvas(canvas, bounds, state.zoom);
      ctx.save();
      ctx.translate(off.dx, off.dy);
      ctx.fillStyle = "#fff";
      ctx.fillRect(
        bounds.x0 * state.zoom,
        bounds.y0 * state.zoom,
        (bounds.x1 - bounds.x0) * state.zoom,
        (bounds.y1 - bounds.y0) * state.zoom,
      );
      PS.drawCell(ctx, profile, left, 0, 0, state.zoom);
      PS.drawCell(ctx, profile, right, item[1], 0, state.zoom);
      ctx.restore();
    });
    var status = $("ps-pair-note"),
      delta = step - original;
    var parts = ["Optical correction " + Math.round(state.optical * 100) + "%"];
    if (rec.optical_adjustment === null || rec.optical_adjustment === undefined) {
      parts.push("no optical correction (" + rec.reason + ")");
    }
    if (state.letter !== 0) {
      parts.push("letter spacing " + (state.letter > 0 ? "+" : "") + state.letter + " px");
    }
    parts.push(
      delta === 0
        ? "same as original"
        : Math.abs(delta) + " px " + (delta < 0 ? "tighter" : "looser") + " than original",
    );
    status.textContent = parts.join(", ") + ".";
  }

  /* ---- diagnostics (collapsed by default) ---- */

  function renderDiagnostics(table, adjusted) {
    var host = $("ps-diagnostics");
    host.innerHTML = "";
    var c = findCase(state.caseId),
      profile = state.profile;
    var ds = datasetOf(c, profile);
    var dl = el("dl", null, "ps-facts");
    [
      ["Model", boot.model],
      ["Method", boot.spacing_model],
      ["Implementation", boot.implementation.slice(0, 12) + " (full hash in manifest)"],
      [
        "Setting",
        "optical " +
          Math.round(state.optical * 100) +
          "%, letter " +
          (state.letter > 0 ? "+" : "") +
          state.letter +
          " px",
      ],
      ["Font file", c.font_file + " sha256:" + c.font_sha256.slice(0, 16) + "..."],
      ["Capture", ds.capture + " sha256:" + ds.capture_sha256.slice(0, 16) + "..."],
      [
        "Sample text",
        "sha256:" +
          c.text_sha256.slice(0, 16) +
          "..." +
          " (" +
          c.text.length +
          " characters, " +
          ds.lines.length +
          " lines)",
      ],
    ].forEach(function (kv) {
      var dt = el("dt", kv[0]),
        dd = el("dd", kv[1]);
      dl.appendChild(dt);
      dl.appendChild(dd);
    });
    host.appendChild(dl);
    if (!table) {
      host.appendChild(el("p", "Loading sample data."));
      return;
    }
    host.appendChild(el("h3", "Endpoint composition before letter spacing"));
    if (profile === "gray") {
      host.appendChild(
        el(
          "p",
          "Grayscale uses corrections from the black-and-white analysis, added to its original fractional placement.",
        ),
      );
    }
    var wrap = el("div", null, "ps-scroll");
    var tbl = document.createElement("table");
    var head = document.createElement("tr");
    ["pair", "endpoint metric", "optical", "clearance floor", "at strength", "status"].forEach(function (h) {
      head.appendChild(el("th", h));
    });
    tbl.appendChild(head);
    Object.keys(table.pairs)
      .sort()
      .forEach(function (name) {
        var rec = table.pairs[name];
        var step = PS.autoStep(rec, state.optical);
        var tr = document.createElement("tr");
        [
          name,
          String(rec.metric),
          rec.optical_adjustment === null || rec.optical_adjustment === undefined
            ? "n/a"
            : (rec.advance + rec.optical_adjustment).toFixed(3),
          rec.minimum === null || rec.minimum === undefined ? "n/a" : String(rec.minimum),
          String(step),
          rec.optical_adjustment === null || rec.optical_adjustment === undefined
            ? "original (" + rec.reason + ")"
            : (step === rec.metric ? "unchanged" : step === rec.minimum ? "limited" : "corrected") +
              (rec.reason === "clearance_limited" ? ", guarded" : ""),
        ].forEach(function (text) {
          tr.appendChild(el("td", text));
        });
        if (step !== rec.metric) tr.className = "chosen";
        tbl.appendChild(tr);
      });
    wrap.appendChild(tbl);
    host.appendChild(wrap);
    host.appendChild(el("h3", "Line origins at this setting"));
    host.appendChild(
      el(
        "p",
        "Adjusted origins per line: " +
          adjusted
            .map(function (o) {
              return "[" + o.join(", ") + "]";
            })
            .join(" / "),
        "ps-mono",
      ),
    );
    host.appendChild(
      el(
        "p",
        "Original origins per line: " +
          ds.captured
            .map(function (o) {
              return "[" + o.join(", ") + "]";
            })
            .join(" / "),
        "ps-mono",
      ),
    );
    host.appendChild(
      el(
        "p",
        "Whole-pixel steps change only at some strengths; " + "intermediate strengths can share a placement.",
        "ps-note",
      ),
    );
  }

  /* ---- controls ---- */

  function opticalWord(value) {
    if (value === 0) return "Source";
    if (value === 1) return "Full";
    return Math.round(value * 100) + "%";
  }

  function refreshControls() {
    $("ps-optical-v").textContent = opticalWord(state.optical);
    $("ps-optical").setAttribute(
      "aria-valuetext",
      "Optical correction " + Math.round(state.optical * 100) + " percent",
    );
    $("ps-letter-v").textContent = (state.letter > 0 ? "+" : "") + state.letter + " px";
    $("ps-letter").setAttribute("aria-valuetext", "Letter spacing " + state.letter + " pixels");
  }

  function refreshFocused() {
    refreshControls();
    refreshSampleOptions();
    var c = findCase(state.caseId);
    var seq = ++focusSeq;
    ensureTable(c, state.profile, function (table) {
      if (seq !== focusSeq) return;
      renderFocus(table);
    });
    renderFocus(window.PS_TABLES[tableLabel(c, state.profile)] || null);
  }

  function initControls() {
    var profile = $("ps-profile");
    ["mono", "gray"].forEach(function (p) {
      var label = el("label", p === "mono" ? "Black and white" : "Grayscale");
      var input = document.createElement("input");
      input.type = "radio";
      input.name = "profile";
      input.value = p;
      if (p === state.profile) input.checked = true;
      input.addEventListener("change", function () {
        state.profile = p;
        refreshFocused();
      });
      label.insertBefore(input, label.firstChild);
      profile.appendChild(label);
    });
    var zoom = $("ps-zoom");
    [
      ["1", "Native size"],
      ["2", "2x"],
      ["4", "4x"],
    ].forEach(function (opt) {
      var o = document.createElement("option");
      o.value = opt[0];
      o.textContent = opt[1];
      zoom.appendChild(o);
    });
    zoom.value = "1";
    zoom.addEventListener("change", function () {
      state.zoom = Number(zoom.value);
      refreshFocused();
    });
    var optical = $("ps-optical"),
      letter = $("ps-letter");
    optical.addEventListener("input", function () {
      state.optical = Number(optical.value) / 100;
      refreshFocused();
    });
    letter.addEventListener("input", function () {
      state.letter = Number(letter.value);
      refreshFocused();
    });
    refreshSampleOptions();
    $("ps-sample").addEventListener("change", function (e) {
      var valid = cases().some(function (c) {
        return c.id === e.target.value;
      });
      if (!valid) {
        e.target.value = state.caseId;
        return;
      }
      state.caseId = e.target.value;
      refreshFocused();
    });
    $("ps-pair").addEventListener("change", function (e) {
      state.pair = e.target.value;
      var c = findCase(state.caseId);
      var table = window.PS_TABLES[tableLabel(c, state.profile)] || null;
      var ds = datasetOf(c, state.profile);
      var adjusted = table
        ? adjustedOrigins(c, state.profile, table)
        : ds.captured.map(function (o) {
            return o.slice();
          });
      renderPair(table, adjusted);
      renderDiagnostics(table, adjusted);
    });
    $("ps-reset").addEventListener("click", function () {
      state.optical = 0;
      state.letter = 0;
      $("ps-optical").value = "0";
      $("ps-letter").value = "0";
      refreshFocused();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initControls();
      refreshFocused();
    });
  } else {
    initControls();
    refreshFocused();
  }
})();
