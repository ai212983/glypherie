/* Isolated SCORE-v2 native ink comparison (table lookup only, no engine).
 *
 * Renders Source / B2 / Oriented placements of frozen precomputed pair cases.
 * All choice arithmetic mirrors TIE-v2 exactly:
 *   deviations d(s) = |G2(s) - C*| over valid steps in the chosen domain,
 *   tolerance tol = 1e-9 * max(1, m*), minimizing set within m* + tol,
 *   single pick = lowest step index. Boundary picks are labeled, never
 *   silently widened. Coordinates: integer steps shift the right glyph origin
 *   relative to the left origin; y uses native top bearings (shared baseline
 *   band), so the visible gap change is the step change.
 */
(function () {
  "use strict";

  var DATA = window.__YYDATA;
  var TIE_TOL_FACTOR = 1e-9;
  var TARGET_MIN = 0;
  var TARGET_MAX = 128;

  var state = {
    sample: "roboto-16",
    profile: "mono",
    target: 4,
    domain: 2,
    variant: "notebook",
    zoom: 1,
  };

  function capKey() {
    return state.sample + "-" + state.profile;
  }

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function fmtDelta(d) {
    return (d >= 0 ? "+" : "") + d;
  }

  /* Lowest-step-index TIE-v2 pick over stored curve values (no engine). */
  function choose(steps, variant, domain, target) {
    var rows = [];
    for (var i = 0; i < steps.length; i++) {
      var s = steps[i];
      if (!s.valid) continue;
      if (Math.abs(s.delta) > domain) continue;
      var g = variant === "notebook" ? s.g2n : s.g2m;
      if (g === null || g === undefined || !isFinite(g)) continue;
      rows.push({ step: s.step, delta: s.delta, g: g });
    }
    if (rows.length === 0) return { empty: true };
    var devs = rows.map(function (r) {
      return Math.abs(r.g - target);
    });
    var mstar = Math.min.apply(null, devs);
    var tol = TIE_TOL_FACTOR * Math.max(1, mstar);
    var ties = [];
    for (var k = 0; k < rows.length; k++) {
      if (devs[k] <= mstar + tol) ties.push(rows[k].step);
    }
    ties.sort(function (a, b) {
      return a - b;
    });
    var pick = rows[0];
    for (var j = 0; j < rows.length; j++) {
      if (rows[j].step === ties[0]) {
        pick = rows[j];
        break;
      }
    }
    return {
      step: pick.step,
      delta: pick.delta,
      mstar: mstar,
      ties: ties,
      boundary: Math.abs(pick.delta) === domain,
    };
  }

  function frameFor(L, R, steps, sourceStep, b2Step) {
    var lo = [L.left, L.top];
    var ros = [
      [sourceStep + R.left, R.top],
      [b2Step + R.left, R.top],
    ];
    for (var i = 0; i < steps.length; i++) {
      var s = steps[i];
      if (!s.valid) continue;
      ros.push([s.step + R.left, R.top]);
    }
    var xs = [lo[0], lo[0] + L.w];
    var ys = [lo[1], lo[1] + L.h];
    for (var k = 0; k < ros.length; k++) {
      xs.push(ros[k][0], ros[k][0] + R.w);
      ys.push(ros[k][1], ros[k][1] + R.h);
    }
    var fx = Math.min.apply(null, xs);
    var fy = Math.min.apply(null, ys);
    return {
      x: fx,
      y: fy,
      w: Math.max.apply(null, xs) - fx,
      h: Math.max.apply(null, ys) - fy,
    };
  }

  function grayValue(p) {
    return Math.round(255 * (1 - p / 7));
  }

  function drawGlyph(ctx, G, ox, fx, fy, zoom, gray) {
    var w = G.w,
      px = G.px;
    var n = px.length;
    if (!gray) {
      ctx.fillStyle = "#000";
      for (var i = 0; i < n; i++) {
        if (px[i] === "1") {
          var x0 = i % w,
            y0 = (i / w) | 0;
          ctx.fillRect((ox + G.left + x0 - fx) * zoom, (G.top + y0 - fy) * zoom, zoom, zoom);
        }
      }
      return;
    }
    for (var level = 1; level <= 7; level++) {
      var ch = String(level);
      var v = grayValue(level);
      var drew = false;
      for (var j = 0; j < n; j++) {
        if (px[j] === ch) {
          if (!drew) {
            ctx.fillStyle = "rgb(" + v + "," + v + "," + v + ")";
            drew = true;
          }
          var gx = j % w,
            gy = (j / w) | 0;
          ctx.fillRect((ox + G.left + gx - fx) * zoom, (G.top + gy - fy) * zoom, zoom, zoom);
        }
      }
    }
  }

  function drawCanvas(canvas, L, R, step, frame, zoom, gray) {
    var W = Math.max(1, frame.w * zoom),
      H = Math.max(1, frame.h * zoom);
    canvas.width = W;
    canvas.height = H;
    canvas.style.width = W + "px";
    canvas.style.height = H + "px";
    var ctx = canvas.getContext("2d");
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, W, H);
    drawGlyph(ctx, L, 0, frame.x, frame.y, zoom, gray);
    drawGlyph(ctx, R, step, frame.x, frame.y, zoom, gray);
  }

  function pairLabel(pair) {
    return esc(pair[0]) + " + " + esc(pair[1]);
  }

  function buildRows() {
    var host = document.getElementById("yy-rows");
    host.textContent = "";
    DATA.pairs.forEach(function (pair, idx) {
      var sec = document.createElement("section");
      sec.className = "yy-pair";
      sec.id = "yy-pair-" + pair;
      var head = document.createElement("div");
      head.className = "yy-pairhead";
      var h = document.createElement("h2");
      h.innerHTML = pairLabel(pair);
      head.appendChild(h);
      if (pair === "um") {
        var badge = document.createElement("span");
        badge.className = "yy-badge";
        badge.textContent = "starting pair";
        head.appendChild(badge);
      }
      var meta = document.createElement("p");
      meta.className = "yy-meta";
      meta.id = "yy-meta-" + pair;
      head.appendChild(meta);
      sec.appendChild(head);
      var scroller = document.createElement("div");
      scroller.className = "yy-rowscroll";
      var cols = document.createElement("div");
      cols.className = "yy-cols";
      ["source", "b2", "oriented"].forEach(function (kind) {
        var fig = document.createElement("figure");
        fig.className = "yy-col";
        var cap = document.createElement("figcaption");
        var title = document.createElement("div");
        title.className = "yy-coltitle";
        title.textContent = kind === "source" ? "Source" : kind === "b2" ? "Current (B2)" : "Oriented model";
        var canvas = document.createElement("canvas");
        canvas.id = "yy-canvas-" + pair + "-" + kind;
        var note = document.createElement("div");
        note.className = "yy-colnote";
        note.id = "yy-note-" + pair + "-" + kind;
        cap.appendChild(title);
        fig.appendChild(canvas);
        fig.appendChild(cap);
        fig.appendChild(note);
        cols.appendChild(fig);
      });
      scroller.appendChild(cols);
      sec.appendChild(scroller);
      host.appendChild(sec);
    });
  }

  function renderAll() {
    var t0 = window.performance && performance.now ? performance.now() : 0;
    var ck = capKey();
    var glyphs = DATA.captures[ck].glyphs;
    var gray = state.profile === "gray";
    DATA.pairs.forEach(function (pair) {
      var cs = DATA.cases[ck][pair];
      var L = glyphs[String(pair.charCodeAt(0))];
      var R = glyphs[String(pair.charCodeAt(1))];
      var frame = frameFor(L, R, cs.steps, cs.metric, cs.b2);
      var picked = choose(cs.steps, state.variant, state.domain, state.target);
      drawCanvas(document.getElementById("yy-canvas-" + pair + "-source"), L, R, cs.metric, frame, state.zoom, gray);
      drawCanvas(document.getElementById("yy-canvas-" + pair + "-b2"), L, R, cs.b2, frame, state.zoom, gray);
      var noteNodes = {
        source: document.getElementById("yy-note-" + pair + "-source"),
        b2: document.getElementById("yy-note-" + pair + "-b2"),
        oriented: document.getElementById("yy-note-" + pair + "-oriented"),
      };
      noteNodes.source.textContent = "Source \u00b7 step " + cs.metric;
      var b2d = cs.b2 - cs.metric;
      var b2txt = "B2 1.1/2/2 \u00b7 step " + cs.b2 + " (\u0394" + fmtDelta(b2d) + ")";
      if (Math.abs(b2d) === 2) b2txt += " \u00b7 Search limit";
      if (cs.b2fallback) b2txt += " \u00b7 fallback to source";
      noteNodes.b2.textContent = b2txt;
      if (picked.empty) {
        drawCanvas(
          document.getElementById("yy-canvas-" + pair + "-oriented"),
          L,
          R,
          cs.metric,
          frame,
          state.zoom,
          gray,
        );
        noteNodes.oriented.textContent = "Oriented \u00b7 no valid step in \u00b1" + state.domain + " (Search limit)";
      } else {
        drawCanvas(
          document.getElementById("yy-canvas-" + pair + "-oriented"),
          L,
          R,
          picked.step,
          frame,
          state.zoom,
          gray,
        );
        var otxt =
          "Oriented C*=" +
          trimNum(state.target) +
          " \u2192 step " +
          picked.step +
          " (\u0394" +
          fmtDelta(picked.delta) +
          ")";
        if (picked.ties.length > 1) {
          otxt += " \u00b7 tie: steps " + picked.ties.join(", ") + " (lowest shown)";
        }
        if (picked.boundary) otxt += " \u00b7 Search limit";
        noteNodes.oriented.textContent = otxt;
      }
      var validN = 0,
        gmin = Infinity,
        gmax = -Infinity;
      cs.steps.forEach(function (s) {
        if (!s.valid || Math.abs(s.delta) > state.domain) return;
        var g = state.variant === "notebook" ? s.g2n : s.g2m;
        if (g === null || g === undefined || !isFinite(g)) return;
        validN++;
        if (g < gmin) gmin = g;
        if (g > gmax) gmax = g;
      });
      var meta = document.getElementById("yy-meta-" + pair);
      meta.textContent =
        "G2 " +
        (validN ? trimNum(gmin) + "\u2013" + trimNum(gmax) : "n/a") +
        " over \u00b1" +
        state.domain +
        " \u00b7 valid " +
        validN +
        "/" +
        cs.steps.length +
        " steps \u00b7 " +
        (state.variant === "notebook" ? "notebook strength" : "manuscript variant");
    });
    var t1 = window.performance && performance.now ? performance.now() : 0;
    var status = document.getElementById("yy-status");
    status.textContent =
      "Rendered 8 pairs \u00d7 3 placements in " + (t1 - t0).toFixed(1) + " ms (precomputed table lookup; no engine).";
  }

  function trimNum(x) {
    if (!isFinite(x)) return "n/a";
    var s = String(Math.round(x * 1000) / 1000);
    return s;
  }

  function setTargetFromSlider() {
    var slider = document.getElementById("yy-target");
    state.target = parseFloat(slider.value);
    var num = document.getElementById("yy-target-num");
    num.value = String(state.target);
    num.removeAttribute("aria-invalid");
    document.getElementById("yy-target-error").textContent = "";
    renderAll();
  }

  function setTargetFromNumber() {
    var num = document.getElementById("yy-target-num");
    var err = document.getElementById("yy-target-error");
    var raw = num.value.trim();
    if (raw === "") {
      num.setAttribute("aria-invalid", "true");
      err.textContent = "Enter a number in 0..128; placement unchanged.";
      return;
    }
    var v = Number(raw);
    if (!isFinite(v) || v < TARGET_MIN || v > TARGET_MAX) {
      num.setAttribute("aria-invalid", "true");
      err.textContent = "Enter a number in 0..128; placement unchanged.";
      return;
    }
    state.target = v;
    num.removeAttribute("aria-invalid");
    err.textContent = "";
    var slider = document.getElementById("yy-target");
    var clamped = Math.min(TARGET_MAX, Math.max(TARGET_MIN, v));
    slider.value = String(Math.round(clamped * 10) / 10);
    renderAll();
  }

  function resetStudy() {
    state.target = 4;
    state.domain = 2;
    state.variant = "notebook";
    document.getElementById("yy-target").value = "4";
    document.getElementById("yy-target-num").value = "4";
    document.getElementById("yy-target-num").removeAttribute("aria-invalid");
    document.getElementById("yy-target-error").textContent = "";
    document.querySelector('input[name="yy-domain"][value="2"]').checked = true;
    document.querySelector('input[name="yy-variant"][value="notebook"]').checked = true;
    renderAll();
  }

  function wire() {
    document.getElementById("yy-sample").addEventListener("change", function (e) {
      state.sample = e.target.value;
      renderAll();
    });
    var profiles = document.querySelectorAll('input[name="yy-profile"]');
    profiles.forEach(function (r) {
      r.addEventListener("change", function (e) {
        state.profile = e.target.value;
        renderAll();
      });
    });
    document.getElementById("yy-target").addEventListener("input", setTargetFromSlider);
    document.getElementById("yy-target-num").addEventListener("change", setTargetFromNumber);
    document.getElementById("yy-reset").addEventListener("click", resetStudy);
    var zooms = document.querySelectorAll('input[name="yy-zoom"]');
    zooms.forEach(function (r) {
      r.addEventListener("change", function (e) {
        state.zoom = parseInt(e.target.value, 10);
        renderAll();
      });
    });
    var domains = document.querySelectorAll('input[name="yy-domain"]');
    domains.forEach(function (r) {
      r.addEventListener("change", function (e) {
        state.domain = parseInt(e.target.value, 10);
        renderAll();
      });
    });
    var variants = document.querySelectorAll('input[name="yy-variant"]');
    variants.forEach(function (r) {
      r.addEventListener("change", function (e) {
        state.variant = e.target.value;
        renderAll();
      });
    });
  }

  window.__YY = { choose: choose, state: state, renderAll: renderAll };

  buildRows();
  wire();
  renderAll();
})();
