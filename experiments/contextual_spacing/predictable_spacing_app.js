/* Predictable spacing prototype: browser logic (no deps).
 *
 * Pure functions live on PredictableSpacing (usable without a DOM). The
 * optical control blends each pair's Source adjustment with its continuous
 * optical adjustment before signed rounding, then applies the shipped
 * feasibility floor; letter spacing adds once per internal span gap.
 */
(function (root) {
  "use strict";

  function pixelRound(value) {
    return value >= 0 ? Math.floor(value + 0.5) : Math.ceil(value - 0.5);
  }

  /* Retained composition: explicit bypass at zero or abstention, otherwise
   * blend-then-round plus the clearance floor. Matches the solver and the
   * maintained Hu/Hersch strength blend. */
  function autoStep(rec, strength) {
    if (strength === 0 || rec.optical_adjustment === null || rec.optical_adjustment === undefined) return rec.metric;
    var blended = rec.metric_adjustment * (1 - strength) + rec.optical_adjustment * strength;
    var step = rec.advance + pixelRound(blended);
    if (rec.minimum !== null && rec.minimum !== undefined) {
      if (step < rec.minimum) step = rec.minimum;
    }
    return step;
  }

  /* Mono origins accumulate whole-pixel steps. Letter spacing applies once
   * per internal span gap; space gaps and line ends keep metric advances. */
  function layoutMono(gaps, pairs, strength, letter) {
    var origins = [0],
      i,
      g,
      step;
    for (i = 0; i < gaps.length; i++) {
      g = gaps[i];
      step = g.space ? g.metric : autoStep(pairs[g.pair], strength);
      if (!g.space && letter) step += letter;
      origins.push(origins[i] + step);
    }
    return origins;
  }

  /* Gray draws round a fractional 26.6 pen; only draw origins round. The
   * integer correction delta comes from the retained endpoint composition
   * (automatic minus the endpoint's own metric), so Source at zero stays
   * exact by bypass even where Gray's rounded metric differs by rounding. */
  function layoutGray(gaps, pairs, strength, letter) {
    var origins = [0],
      pen = 0,
      i,
      g,
      rec,
      step;
    for (i = 0; i < gaps.length; i++) {
      g = gaps[i];
      if (g.space) {
        pen += g.frac;
      } else {
        rec = pairs[g.pair];
        step = autoStep(rec, strength);
        pen += g.frac + (step - rec.metric);
        if (letter) pen += letter;
      }
      origins.push(pixelRound(pen));
    }
    return origins;
  }

  function layoutLines(lines, gaps, pairs, profile, strength, letter) {
    var layout = profile === "mono" ? layoutMono : layoutGray;
    return lines.map(function (_, li) {
      return layout(gaps[li], pairs, strength, letter);
    });
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
    pixelRound: pixelRound,
    autoStep: autoStep,
    layoutMono: layoutMono,
    layoutGray: layoutGray,
    layoutLines: layoutLines,
    coverageColor: coverageColor,
    drawCell: drawCell,
    linesBounds: linesBounds,
    fitCanvas: fitCanvas,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.PredictableSpacing = api;
  }
})(typeof self !== "undefined" ? self : this);
