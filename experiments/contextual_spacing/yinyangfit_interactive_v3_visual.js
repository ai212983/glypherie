// cspell:words yinyangfit brewer
/* Layered heatmap visuals for the oriented-engine spacing page.
 *
 * Stateless views over engine outputs the page already renders. The
 * primary view uses exactly two roles on shared source-pixel
 * coordinates: one faint cool layer carrying each shown letter's
 * whole-glyph-normalized amplitude projection (per-pixel max over
 * directed channels of c/sqrt(E), from the engine `slate` component
 * with fixed per-glyph-channel energies, so weak far responses stay
 * weak), and one warm layer for the exact per-query Class-L summands
 * at the pair's chosen step (the engine local contribution map, which
 * sums to the pair's score). The cool layer composites per-letter
 * fields by display-only MAX; the warm layer composites per-pair maps
 * by display-only MAX and is painted under the ink at fixed global
 * gains with clipping, so fields read as background while glyphs stay
 * fully legible. Neither layer enters the scorer or changes any
 * geometry. Gains are fixed global constants from measured corpus
 * peaks, recorded in the page manifest; no per-frame or per-font
 * autogain. Field overlays never touch the Source/Adjusted output
 * canvases. Ramps pair with labels, never color alone: "Letter field"
 * and "Pair contribution", each with its own weak-to-strong legend.
 *
 * Presentation provenance: the two-role split is a project display
 * choice. Any resemblance to YinYangFit's grouping-blob illustrations is
 * presentational: those schematics depict fitted versus poorly fitted
 * words, not computed fields. The plotted fields are the oriented
 * engine's own normalized quantities, not upstream grouping activity.
 * The cool/warm split is a project presentation choice; the ramp
 * sequences follow published sequential-colormap guidance
 * (https://matplotlib.org/stable/users/explain/colors/colormaps.html).
 */
(function (root) {
  "use strict";

  /* Two fixed sequential ramps (display only). Each maps the clamped
   * scalar to hue AND opacity; no field values are added or rescaled.
   * Stops are the published 9-class ColorBrewer sequences (Cynthia A.
   * Brewer and Mark Harrower, colorbrewer2.org, free for all uses with
   * attribution; the same sequences ship as Matplotlib's Blues and
   * YlOrRd under BSD-3-Clause), declared here as a fixed lookup with no
   * dependency. The cool letter ramp runs Blues reversed (deep blue at
   * 0, near-white pale blue at 1) so the whole-glyph layer stays faint
   * while strengthening with intensity. The warm contribution ramp runs
   * YlOrRd reversed (dark red at 0, pale yellow at 1) so pair hotspots
   * read as bright cores. rampRgb interpolates linearly between
   * adjacent stops; no smoothing across source pixels. */
  var LETTER_RAMP_STOPS = [
    "#08306b",
    "#08519c",
    "#2171b5",
    "#4292c6",
    "#6baed6",
    "#9ecae1",
    "#c6dbef",
    "#deebf7",
    "#f7fbff",
  ];
  var CONTRIB_RAMP_STOPS = [
    "#800026",
    "#bd0026",
    "#e31a1c",
    "#fc4e2a",
    "#fd8d3c",
    "#feb24c",
    "#fed976",
    "#ffeda0",
    "#ffffcc",
  ];
  /* Default layer opacity (display only): letter at 0.65; contribution
   * fully opaque. Fixed global gains from measured corpus peaks
   * (display only, never rescale any exact sum). */
  var DEFAULT_LETTER_ALPHA = 0.65;
  var DEFAULT_CONTRIB_ALPHA = 1;
  var SLATE_GAIN = 6.0;
  var CONTRIB_GAIN = 4.0;
  /* Paint-time skips for visually negligible pixels only: slate below
   * BASE_CROP and interaction alpha below INTERACT_MIN_ALPHA are not
   * painted. The scorer and the diagnostics sums never see these crops. */
  var BASE_CROP = 0.02;
  var INTERACT_MIN_ALPHA = 0.01;

  function hexRgb(hex) {
    return [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)];
  }

  /* Fixed-ramp lookup: clamped scalar 0..1 to an [r,g,b] triple by
   * linear interpolation between adjacent stops. Pure, so the scalar
   * endpoints and ordering are unit-testable. */
  function rampRgb(stops, u) {
    if (!(u > 0)) return hexRgb(stops[0]);
    if (!(u < 1)) return hexRgb(stops[stops.length - 1]);
    var p = u * (stops.length - 1);
    var i = Math.floor(p),
      t = p - i;
    var a = hexRgb(stops[i]),
      b = hexRgb(stops[i + 1]);
    return [
      Math.round(a[0] + (b[0] - a[0]) * t),
      Math.round(a[1] + (b[1] - a[1]) * t),
      Math.round(a[2] + (b[2] - a[2]) * t),
    ];
  }

  /* Standard source-over compositing of display layers over white, one
   * opaque color per pixel. Layers are [{rgb:[r,g,b], a:0..1}] in paint
   * order; the result is display only and never enters the scorer. Pure
   * (no canvas) so the overlap contribution is unit-testable. */
  function compositeLayers(layers) {
    var r = 255,
      g = 255,
      b = 255,
      i;
    for (i = 0; i < layers.length; i++) {
      var a = layers[i].a;
      if (!(a > 0)) continue;
      if (a > 1) a = 1;
      var c = layers[i].rgb;
      r = c[0] * a + r * (1 - a);
      g = c[1] * a + g * (1 - a);
      b = c[2] * a + b * (1 - a);
    }
    r = Math.round(r);
    g = Math.round(g);
    b = Math.round(b);
    return "rgb(" + r + "," + g + "," + b + ")";
  }
  /* Fixed frame margin in source pixels: the frame covers every tried
   * width (metric +/- 2) plus this margin, and never changes with the
   * controls, so extent changes stay visible instead of rescaling away. */
  var FRAME_MARGIN = 10;

  function setupCanvas(canvas, w, h) {
    var ratio = 2;
    canvas.width = w * ratio;
    canvas.height = h * ratio;
    canvas.style.width = "100%";
    canvas.style.height = "auto";
    var ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, w, h);
    return ctx;
  }

  /* Fixed display frame for shown letter runs with per-line vertical
   * offsets: union of the placed ink bounds, expanded horizontally by the
   * cumulative tried-width drift (each of the G gaps can move its
   * followers by up to 2 px) plus the fixed margin, vertically by the
   * margin only. Independent of all three controls, so slider moves never
   * recenter or rescale the view. Runs carry {x0, x1, y0, y1} ink bounds
   * and the gap count covers the shown adjacencies. */
  function frameForRuns(bounds, gaps) {
    var xs = [0],
      ys = [0],
      i;
    for (i = 0; i < bounds.length; i++) {
      xs.push(bounds[i][0], bounds[i][1]);
      ys.push(bounds[i][2], bounds[i][3]);
    }
    var drift = 2 * gaps + FRAME_MARGIN;
    var x0 = Math.floor(Math.min.apply(null, xs)) - drift;
    var x1 = Math.ceil(Math.max.apply(null, xs)) + drift;
    var y0 = Math.floor(Math.min.apply(null, ys)) - FRAME_MARGIN;
    var y1 = Math.ceil(Math.max.apply(null, ys)) + FRAME_MARGIN;
    return { x0: x0, y0: y0, w: x1 - x0, h: y1 - y0 };
  }

  /* Shown letters in exactly two roles. The cool letter layer takes the
   * engine `slate` crops (already intersected with the display frame by
   * the worker) and keeps the per-pixel MAXIMUM scalar; overlapping
   * letters never sum and never rainbow. The warm contribution layer
   * takes exact per-query Class-L contribution maps (layers[p].c over
   * that pair's scored canvas, placed at true origins) and keeps the
   * per-pixel MAXIMUM across pairs: display only, defines no new score.
   * Paint order is white, then cool, then warm, then ink last at true
   * origins: both field layers sit behind the text. Mono ink stays
   * opaque black; gray ink keeps delivered coverage as source-over
   * alpha, so partial coverage still shows fields through.
   * With an integer zoom every source pixel paints zoom-by-
   * zoom CSS pixels, padding included, so CSS dimensions scale exactly
   * with the zoom and wide views scroll horizontally instead of shrinking
   * glyphs. Without a zoom the frame auto-fits a fixed CSS width
   * (standalone demo path). Runs carry {cell, ox, oy}; slate grids carry
   * {x0, y0, w, h, f}; layers carry {x0, y0, w, h, c}. alphas carries
   * the per-layer opacity ({letter, contrib}); letter alpha is the
   * squared clamped strength times letter opacity, interaction alpha is
   * min(1, contribution * contribGain) times contrib opacity. Each
   * layer's hue comes from its own fixed ramp at the same clamped
   * scalar. opts carries showFields (master) plus showLetter and
   * showContrib; any hidden layer paints nothing while the ink below
   * paints at identical positions. Returns the integer zoom. */
  function drawExcerptField(canvas, fields, frame, runs, profile, layers, alphas, zoom, gains, opts) {
    var showFields = !opts || opts.showFields !== false;
    var showLetter = !opts || opts.showLetter !== false;
    var showContrib = !opts || opts.showContrib !== false;
    var PAD_X = 10,
      PAD_TOP = 8,
      PAD_B = 8;
    var slateGain = (gains && gains.slate) || SLATE_GAIN;
    var contribGain = (gains && gains.contrib) || CONTRIB_GAIN;
    var z, W, H;
    if (zoom) {
      z = zoom;
      W = (frame.w + PAD_X * 2) * z;
      H = (frame.h + PAD_TOP + PAD_B) * z;
    } else {
      z = Math.min(Math.floor(340 / frame.w), Math.floor(220 / frame.h));
      if (!(z >= 1)) z = 1;
      if (z > 8) z = 8;
      W = PAD_X * 2 + frame.w * z;
      H = PAD_TOP + frame.h * z + PAD_B;
    }
    var ctx = setupCanvas(canvas, W, H);
    canvas.style.width = W + "px";
    function PX(x) {
      return zoom ? (PAD_X + (x - frame.x0)) * z : PAD_X + (x - frame.x0) * z;
    }
    function PY(y) {
      return zoom ? (PAD_TOP + (y - frame.y0)) * z : PAD_TOP + (y - frame.y0) * z;
    }
    /* Per-layer opacity (display only). */
    var letterA = alphas && isFinite(alphas.letter) ? alphas.letter : DEFAULT_LETTER_ALPHA;
    var contribA = alphas && isFinite(alphas.contrib) ? alphas.contrib : DEFAULT_CONTRIB_ALPHA;
    var n = frame.w * frame.h,
      j,
      k;
    /* Hidden layers paint nothing: empty inputs skip both field loops
     * while the ink below paints at identical positions. */
    if (!showFields || !showLetter) fields = [];
    if (!showFields || !showContrib) layers = null;
    /* Cool letter layer: per-pixel MAX scalar across letter lattices.
     * Each lattice is glyph-local (origin at trunc(left - pad)); adding the
     * run's laid-out origin puts it in placed frame coords, the same
     * translation the ink painted last uses. */
    var slatePeak = new Array(n);
    for (j = 0; j < n; j++) slatePeak[j] = 0;
    for (k = 0; k < fields.length; k++) {
      var F = fields[k];
      if (!F) continue;
      var org = runs && runs[k];
      var dx = org ? org.ox : 0,
        dy = org ? org.oy || 0 : 0;
      var fvals = F.f;
      for (var ly = 0; ly < F.h; ly++) {
        for (var lx = 0; lx < F.w; lx++) {
          var v = fvals[ly * F.w + lx];
          var qx = F.x0 + dx + lx,
            qy = F.y0 + dy + ly;
          if (qx < frame.x0 || qy < frame.y0 || qx >= frame.x0 + frame.w || qy >= frame.y0 + frame.h) continue;
          var fi = (qy - frame.y0) * frame.w + (qx - frame.x0);
          if (v > slatePeak[fi]) slatePeak[fi] = v;
        }
      }
    }
    for (j = 0; j < n; j++) {
      var best = slatePeak[j] * slateGain;
      if (best > 1) best = 1;
      /* Fixed soft display curve on the letter layer only: squaring the
       * clamped strength fades verified weak tails below the existing
       * crop while saturated cores stay fully on. Opacity below still
       * scales linearly; hue follows the same clamped scalar on the
       * fixed cool ramp. Interaction, ink and scoring untouched. */
      var strength = best * best;
      if (!(strength > BASE_CROP)) continue;
      var fa = strength * letterA;
      if (!(fa > 0)) continue;
      ctx.fillStyle = compositeLayers([{ rgb: rampRgb(LETTER_RAMP_STOPS, best), a: fa }]);
      var fx = frame.x0 + (j % frame.w),
        fy = frame.y0 + ((j / frame.w) | 0);
      ctx.fillRect(PX(fx), PY(fy), z, z);
    }
    /* Warm contribution layer: per-pixel MAXIMUM across pair layers,
     * painted once under the ink at fixed gain with clipping. Hue
     * follows the same clamped scalar on the fixed warm ramp; paint
     * skips visually negligible alpha; exact per-pair sums stay in the
     * diagnostics, unaffected. */
    if (layers) {
      var peak = new Array(n);
      for (var q = 0; q < n; q++) peak[q] = 0;
      for (var p = 0; p < layers.length; p++) {
        var L = layers[p];
        for (var ly2 = 0; ly2 < L.h; ly2++) {
          for (var lx2 = 0; lx2 < L.w; lx2++) {
            var c = L.c[ly2 * L.w + lx2];
            var qx2 = L.x0 + lx2,
              qy2 = L.y0 + ly2;
            if (qx2 < frame.x0 || qy2 < frame.y0 || qx2 >= frame.x0 + frame.w || qy2 >= frame.y0 + frame.h) continue;
            var fi2 = (qy2 - frame.y0) * frame.w + (qx2 - frame.x0);
            if (c > peak[fi2]) peak[fi2] = c;
          }
        }
      }
      for (var m = 0; m < n; m++) {
        var raw = peak[m] * contribGain;
        if (raw > 1) raw = 1;
        var alpha = raw * contribA;
        if (!(alpha >= INTERACT_MIN_ALPHA)) continue;
        var mx = frame.x0 + (m % frame.w),
          my = frame.y0 + ((m / frame.w) | 0);
        var wc = rampRgb(CONTRIB_RAMP_STOPS, raw);
        ctx.fillStyle = "rgba(" + wc[0] + "," + wc[1] + "," + wc[2] + "," + alpha.toFixed(3) + ")";
        ctx.fillRect(PX(mx), PY(my), z, z);
      }
    }
    /* Ink last at true origins: mono stays opaque black regardless of the
     * layer ramps; gray keeps delivered coverage as source-over alpha,
     * so fields show through partial coverage instead of being scrubbed. */
    for (var r = 0; r < runs.length; r++) {
      var g = runs[r].cell,
        ox0 = runs[r].ox,
        oy0 = runs[r].oy || 0;
      for (var row = 0; row < g.h; row++) {
        for (var col = 0; col < g.w; col++) {
          var cv = g.cover[row * g.w + col];
          if (!(cv > 0)) continue;
          if (profile === "mono") ctx.fillStyle = "#161616";
          else ctx.fillStyle = "rgba(22,22,22," + cv.toFixed(3) + ")";
          ctx.fillRect(PX(ox0 + g.left + col), PY(oy0 + g.top + row), z, z);
        }
      }
    }
    return { zoom: z };
  }

  var api = {
    LETTER_RAMP_STOPS: LETTER_RAMP_STOPS,
    CONTRIB_RAMP_STOPS: CONTRIB_RAMP_STOPS,
    DEFAULT_LETTER_ALPHA: DEFAULT_LETTER_ALPHA,
    DEFAULT_CONTRIB_ALPHA: DEFAULT_CONTRIB_ALPHA,
    SLATE_GAIN: SLATE_GAIN,
    CONTRIB_GAIN: CONTRIB_GAIN,
    BASE_CROP: BASE_CROP,
    INTERACT_MIN_ALPHA: INTERACT_MIN_ALPHA,
    rampRgb: rampRgb,
    hexRgb: hexRgb,
    FRAME_MARGIN: FRAME_MARGIN,
    compositeLayers: compositeLayers,
    frameForRuns: frameForRuns,
    drawExcerptField: drawExcerptField,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.YYVisual = api;
  }
})(typeof self !== "undefined" ? self : this);
