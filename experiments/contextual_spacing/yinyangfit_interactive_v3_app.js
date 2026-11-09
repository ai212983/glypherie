/* Letter-spacing sample viewer: browser logic (no deps).
 *
 * Pure functions live on LetterSpacing (usable without a DOM). Canvas
 * drawing uses 2d only. Costs are derived in the browser as
 * |score - target| over shipped or WASM-computed exact Class-L curves,
 * and the choice mirrors the engine TIE-v2 rule exactly: the minimizing
 * set holds every valid step within m* + 1e-9*max(1, m*), and the
 * single pick is the lowest step index (never metric-nearest). The
 * 1e-9*max(1, m*) tolerance and lowest-index pick match the engine
 * (`score.rs` tie_set plus pick); an absolute 1e-9 tolerance would
 * diverge from the engine at large scores.
 */
(function (root) {
  "use strict";
  var TIE_TOLERANCE = 1e-9;

  function sfIndex(si, qi, nq) {
    return si * nq + qi;
  }
  function comboId(ci, sfi, nsf) {
    return "c" + (ci * nsf + sfi);
  }

  /* Mirror of the engine TIE-v2 minimizing set: the global minimum over
   * valid candidates, then every valid candidate within m* +
   * 1e-9*max(1, m*) of it. Two passes: a moving best with tolerance
   * would admit later entries only near an early non-minimum. */
  function selectIndices(costs, ok) {
    var best = Infinity,
      min = [],
      i;
    for (i = 0; i < costs.length; i++) {
      if (!ok[i] || costs[i] === null || costs[i] === undefined) continue;
      if (!isFinite(costs[i])) continue;
      if (costs[i] < best) best = costs[i];
    }
    if (!isFinite(best)) return min;
    var tol = TIE_TOLERANCE * Math.max(1, best);
    for (i = 0; i < costs.length; i++) {
      if (!ok[i] || costs[i] === null || costs[i] === undefined) continue;
      if (!isFinite(costs[i])) continue;
      if (costs[i] <= best + tol) min.push(i);
    }
    return min;
  }

  function eligibleFor(entry, i) {
    var v = entry.gl[i];
    return !!entry.ok[i] && !(entry.abst && entry.abst[i]) && v !== null && v !== undefined && isFinite(v);
  }

  function costsFor(entry, target) {
    return entry.gl.map(function (v, i) {
      if (!eligibleFor(entry, i)) return null;
      return Math.abs(v - target);
    });
  }

  /* Browser mirror of the search-v2 choice: TIE-v2 over supported (valid,
   * non-abstained) steps only; abstained steps never win, even at target 0.
   * With no supported step the metric (Source) is retained with a reason.
   * `search` carries the pair domain reason (blank/disjoint) when present. */
  function chosenStep(pairTable, sfi, target) {
    var entry = pairTable.geo[String(sfi)];
    var search = pairTable.search || null;
    var costs = costsFor(entry, target);
    var supported = entry.ok.map(function (_, i) {
      return eligibleFor(entry, i);
    });
    var min = selectIndices(costs, supported);
    var steps = pairTable.steps,
      metric = pairTable.metric;
    var seen = [],
      si;
    for (si = 0; si < supported.length; si++) {
      if (supported[si]) seen.push(entry.gl[si]);
    }
    var attainable = seen.length ? [Math.min.apply(null, seen), Math.max.apply(null, seen)] : null;
    var targetOutside = attainable !== null && (target < attainable[0] || target > attainable[1]);
    if (!min.length) {
      var reason =
        search &&
        (search.domain_reason === "blank_glyph_no_ink" ||
          search.domain_reason === "row_bands_disjoint" ||
          search.domain_reason === "no_forward_step")
          ? search.domain_reason
          : entry.ok.some(function (v) {
                return v;
              })
            ? "no_shared_support"
            : "occupied_cell_overlap";
      return {
        step: pairTable.metric,
        fallback: true,
        minimizing: [],
        targetOutside: targetOutside,
        reason: reason,
        attainable: attainable,
      };
    }
    /* TIE-v2 single pick: the lowest step index in the minimizing set. */
    var best = min[0],
      bi;
    for (bi = 1; bi < min.length; bi++) {
      if (steps[min[bi]] < steps[best]) best = min[bi];
    }
    return {
      step: steps[best],
      fallback: false,
      minimizing: min.map(function (i) {
        return steps[i];
      }),
      targetOutside: targetOutside,
      reason: null,
      attainable: attainable,
    };
  }

  /* Editable preview-text policy (shared by the page and the demo).
   * An entered newline is the only line break: lines split before scoring
   * and never re-wrap, so a long single line stays single and scrolls
   * horizontally instead of shrinking. Every character survives: spaces
   * keep their metric word advance exactly as the scorer layout does, so
   * runs of spaces, trailing spaces and blank lines are never collapsed
   * or recomposed. At most MAX_LINES lines are shown, with a visible
   * capped note instead of silent truncation. */
  var MAX_LINES = 10;

  function wrapPreviewText(text) {
    var lines = String(text).split("\n");
    var capped = lines.length > MAX_LINES;
    return { lines: capped ? lines.slice(0, MAX_LINES) : lines, capped: capped, total: lines.length };
  }

  /* Repertoire gate for preview text. Newlines split lines; every other
   * character must be a captured scalar of the dataset. Tab, carriage
   * return, non-ASCII and other missing codepoints report the offending
   * codepoint so the UI can name it; the draft is never altered here. */
  function validatePreviewText(text, hasGlyph) {
    var t = String(text);
    for (var i = 0; i < t.length;) {
      var cp = t.codePointAt(i);
      var ch = String.fromCodePoint(cp);
      i += ch.length;
      if (ch === "\n") continue;
      if (!hasGlyph(cp)) {
        return { ok: false, codepoint: cp, char: ch };
      }
    }
    return { ok: true, codepoint: -1, char: "" };
  }

  function formatCodepoint(cp) {
    var h = cp.toString(16).toUpperCase();
    while (h.length < 4) h = "0" + h;
    return "U+" + h;
  }

  /* Unique non-space adjacent pairs per line: the scoring set for text. */
  function textPairs(lines) {
    var found = {},
      out = [];
    lines.forEach(function (line) {
      for (var i = 0; i + 1 < line.length; i++) {
        var a = line[i],
          b = line[i + 1];
        if (a === " " || b === " ") continue;
        var key = a + b;
        if (!found[key]) {
          found[key] = true;
          out.push(key);
        }
      }
    });
    return out;
  }

  /* Browser mirror of the Python metric_step: whole-pixel source advance
   * plus the captured pair-kerning adjustment (missing entries mean no
   * adjustment, as captured), rounded the same way. Advances and kern come
   * from the shipped per-dataset metrics; space pairs use this same rule. */
  function metricStep(advances, kern, leftCp, rightCp) {
    var adv = advances[leftCp];
    var adj = kern[leftCp + "/" + rightCp] || 0;
    var step = adv + adj;
    if (step >= 0) return Math.floor(step + 0.5);
    return Math.ceil(step - 0.5);
  }

  /* Browser mirror of captured_source_word_origins for one line: the
   * fractional 26.6 pen accumulates advance plus pair adjustment per gap
   * and only draw origins round, matching the native surface invariant for
   * nonneg pens of a left-aligned word starting at 0. Space gaps advance
   * the same way; no pair is scored here. */
  function capturedOrigins(advances, kern, line) {
    var origins = [0],
      pen = 0;
    for (var i = 0; i + 1 < line.length; i++) {
      var leftCp = line.charCodeAt(i),
        rightCp = line.charCodeAt(i + 1);
      pen += advances[leftCp] + (kern[leftCp + "/" + rightCp] || 0);
      var draw = pen >= 0 ? Math.floor(pen + 0.5) : Math.ceil(pen - 0.5);
      origins.push(draw);
    }
    return origins;
  }

  /* Per-line layouts from per-gap chosen steps. Space gaps always keep
   * their metric advance (no ink on one side to score); spaceMetrics maps
   * "a "/" b" pairs to those fixed advances. Returns {lines} plus the first
   * pair missing from the evaluated set, if any. */
  function layoutLines(pairSteps, spaceMetrics, lines) {
    var out = [],
      missing = [];
    for (var li = 0; li < lines.length; li++) {
      var word = lines[li],
        origins = [0],
        gaps = [],
        i;
      for (i = 0; i + 1 < word.length; i++) {
        var a = word[i],
          b = word[i + 1],
          key = a + b;
        if (a === " " || b === " ") {
          var fixed = spaceMetrics[key];
          if (fixed === undefined) {
            missing.push(key);
            break;
          }
          origins.push(origins[i] + fixed);
          gaps.push({ pair: key, metric: fixed, chosen: fixed, space: true });
          continue;
        }
        var step = pairSteps[key];
        if (step === undefined) {
          missing.push(key);
          break;
        }
        origins.push(origins[i] + step.step);
        gaps.push({ pair: key, metric: step.metric, chosen: step.step });
      }
      out.push({ origins: origins, gaps: gaps });
    }
    return missing.length ? { error: missing[0], lines: out } : { lines: out };
  }

  function pairStepsFor(table, sfi, target) {
    var out = {},
      name;
    for (name in table.pairs) {
      if (!Object.prototype.hasOwnProperty.call(table.pairs, name)) continue;
      var entry = table.pairs[name];
      var decided = chosenStep(entry, sfi, target);
      out[name] = { metric: entry.metric, step: decided.step, fallback: decided.fallback };
    }
    return out;
  }

  function coverageColor(profile, value) {
    if (profile === "mono") return value > 0 ? "#161616" : null;
    var level = Math.round(255 - value * 255);
    return "rgb(" + level + "," + level + "," + level + ")";
  }

  /* Draw one glyph cell at an integer origin; returns drawn pixel count. */
  function drawCell(ctx, profile, glyph, originX, originY, scale) {
    var count = 0;
    for (var row = 0; row < glyph.h; row++) {
      for (var col = 0; col < glyph.w; col++) {
        var value = glyph.cover[row * glyph.w + col];
        if (!(value > 0)) continue;
        var x = originX + glyph.left + col,
          y = originY + glyph.top + row;
        var color = coverageColor(profile, value);
        if (color === null) continue;
        ctx.fillStyle = color;
        ctx.fillRect(x * scale, y * scale, scale, scale);
        count++;
      }
    }
    return count;
  }

  /* Union bounds across every placed cell of the given per-line origins. */
  function linesBounds(glyphs, words, lineOrigins, pitch) {
    var x0 = Infinity,
      x1 = -Infinity,
      y0 = Infinity,
      y1 = -Infinity,
      any = false;
    lineOrigins.forEach(function (origins, li) {
      var word = words[li];
      for (var k = 0; k < word.length; k++) {
        var g = glyphs[String(word.charCodeAt(k))];
        if (!g) continue;
        var ox = origins[k],
          oy = li * pitch;
        for (var row = 0; row < g.h; row++) {
          for (var col = 0; col < g.w; col++) {
            if (!(g.cover[row * g.w + col] > 0)) continue;
            any = true;
            var x = ox + g.left + col,
              y = oy + g.top + row;
            if (x < x0) x0 = x;
            if (x + 1 > x1) x1 = x + 1;
            if (y < y0) y0 = y;
            if (y + 1 > y1) y1 = y + 1;
          }
        }
      }
    });
    if (!any) return { x0: 0, x1: 1, y0: 0, y1: 1 };
    return { x0: x0, x1: x1, y0: y0, y1: y1 };
  }

  function fitCanvas(canvas, bounds, scale) {
    canvas.width = Math.max(1, Math.ceil((bounds.x1 - bounds.x0) * scale));
    canvas.height = Math.max(1, Math.ceil((bounds.y1 - bounds.y0) * scale));
    return { dx: -bounds.x0 * scale, dy: -bounds.y0 * scale };
  }

  var api = {
    TIE_TOLERANCE: TIE_TOLERANCE,
    MAX_LINES: MAX_LINES,
    wrapPreviewText: wrapPreviewText,
    validatePreviewText: validatePreviewText,
    formatCodepoint: formatCodepoint,
    textPairs: textPairs,
    metricStep: metricStep,
    capturedOrigins: capturedOrigins,
    sfIndex: sfIndex,
    comboId: comboId,
    selectIndices: selectIndices,
    costsFor: costsFor,
    chosenStep: chosenStep,
    layoutLines: layoutLines,
    pairStepsFor: pairStepsFor,
    coverageColor: coverageColor,
    drawCell: drawCell,
    linesBounds: linesBounds,
    fitCanvas: fitCanvas,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.LetterSpacing = api;
  }
})(typeof self !== "undefined" ? self : this);
