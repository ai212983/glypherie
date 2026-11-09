/* YinYangFit-inspired interactive feasibility page: browser logic (no deps).
 *
 * Pure functions (usable without a DOM) are attached to YinYangInteractive.
 * Rendering uses canvas 2d only. Sliders snap to exactly evaluated grid points;
 * the browser only redoes the argmin over embedded costs.
 */
(function (root) {
  "use strict";
  var TIE_TOLERANCE = 1e-9;

  function comboId(ci, si, qi) {
    return "c" + (ci * 16 + si * 4 + qi);
  }

  /* Mirror of the Python minimizing-set rule: the global minimum over valid
   * candidates, then every valid candidate within tolerance of it; the choice
   * among them is metric-nearest. Two passes: a moving best with tolerance
   * would admit later entries that are only near an early non-minimum.
   * Returns array indices. */
  function selectIndices(entry) {
    var best = Infinity,
      min = [],
      i;
    for (i = 0; i < entry.costs.length; i++) {
      if (!entry.ok[i]) continue;
      if (entry.costs[i] < best) best = entry.costs[i];
    }
    if (!isFinite(best)) return min;
    for (i = 0; i < entry.costs.length; i++) {
      if (!entry.ok[i]) continue;
      if (entry.costs[i] <= best + TIE_TOLERANCE) min.push(i);
    }
    return min;
  }

  function chosenStep(pairEntry, cid) {
    var entry = pairEntry.table[cid];
    if (entry.fb) return entry.ch;
    var min = selectIndices(entry);
    if (!min.length) return entry.ch;
    var steps = pairEntry.steps;
    var metric = pairEntry.metric;
    var best = min[0],
      bi;
    for (bi = 1; bi < min.length; bi++) {
      var a = steps[min[bi]],
        b = steps[best];
      if (Math.abs(a - metric) < Math.abs(b - metric) || (Math.abs(a - metric) === Math.abs(b - metric) && a < b))
        best = min[bi];
    }
    return steps[best];
  }

  /* Word layout from per-gap chosen steps; space gaps keep metric advances.
   * glyphs: {cp: {adv}} advances in whole pixels for the pair domain. */
  function layoutWord(pairSteps, word) {
    var origins = [0],
      gaps = [],
      i;
    for (i = 0; i + 1 < word.length; i++) {
      var key = word[i] + word[i + 1];
      var step = pairSteps[key];
      if (step === undefined) return { error: "pair outside evaluated set: " + key };
      origins.push(origins[i] + step.step);
      gaps.push({ pair: key, metric: step.metric, chosen: step.step });
    }
    return { origins: origins, gaps: gaps };
  }

  function pairStepsFor(dataset, cid) {
    var out = {},
      name;
    for (name in dataset.pairs) {
      if (!Object.prototype.hasOwnProperty.call(dataset.pairs, name)) continue;
      var pairEntry = dataset.pairs[name];
      out[name] = { metric: pairEntry.metric, step: chosenStep(pairEntry, cid) };
    }
    return out;
  }

  function coverageColor(profile, value) {
    if (profile === "mono") return value > 0 ? "#161616" : null;
    var level = Math.round(255 - value * 255);
    return "rgb(" + level + "," + level + "," + level + ")";
  }

  /* Draw one glyph cell at integer origin; returns drawn pixel count. */
  function drawCell(ctx, profile, glyph, originX, originY, scale, markOverlaps, overlapSet) {
    var count = 0;
    for (var row = 0; row < glyph.h; row++) {
      for (var col = 0; col < glyph.w; col++) {
        var value = glyph.cover[row * glyph.w + col];
        if (!(value > 0)) continue;
        var x = originX + glyph.left + col,
          y = originY + glyph.top + row;
        var key = x + "," + y;
        if (markOverlaps && overlapSet && overlapSet[key]) {
          ctx.fillStyle = "#b3261e";
        } else {
          var color = coverageColor(profile, value);
          if (color === null) continue;
          ctx.fillStyle = color;
        }
        ctx.fillRect(x * scale, y * scale, scale, scale);
        count++;
      }
    }
    return count;
  }

  function cellSet(glyph, originX, originY) {
    var set = {};
    for (var row = 0; row < glyph.h; row++)
      for (var col = 0; col < glyph.w; col++)
        if (glyph.cover[row * glyph.w + col] > 0)
          set[originX + glyph.left + col + "," + (originY + glyph.top + row)] = true;
    return set;
  }

  /* Composite bounds for a pair at a step, in cell units. */
  function pairBounds(leftGlyph, rightGlyph, step) {
    var xs = [
      leftGlyph.left,
      leftGlyph.left + leftGlyph.w,
      step + rightGlyph.left,
      step + rightGlyph.left + rightGlyph.w,
    ];
    var ys = [leftGlyph.top, leftGlyph.top + leftGlyph.h, rightGlyph.top, rightGlyph.top + rightGlyph.h];
    return {
      x0: Math.min.apply(null, xs),
      x1: Math.max.apply(null, xs),
      y0: Math.min.apply(null, ys),
      y1: Math.max.apply(null, ys),
    };
  }

  function fitCanvas(canvas, bounds, scale) {
    canvas.width = Math.max(1, (bounds.x1 - bounds.x0) * scale);
    canvas.height = Math.max(1, (bounds.y1 - bounds.y0) * scale);
    return { dx: -bounds.x0 * scale, dy: -bounds.y0 * scale };
  }

  var api = {
    TIE_TOLERANCE: TIE_TOLERANCE,
    comboId: comboId,
    selectIndices: selectIndices,
    chosenStep: chosenStep,
    layoutWord: layoutWord,
    pairStepsFor: pairStepsFor,
    coverageColor: coverageColor,
    drawCell: drawCell,
    cellSet: cellSet,
    pairBounds: pairBounds,
    fitCanvas: fitCanvas,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.YinYangInteractive = api;
  }
})(typeof self !== "undefined" ? self : this);
