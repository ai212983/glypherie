// cspell:words yinyangfit argmin multiword nonfinite hashlib rotr
/* Exact browser port of the full-window YinYang geometry core
 * (experiments/contextual_spacing/yinyangfit_interactive_b2.py; the v1
 * module stays frozen as the historical reference).
 *
 * Full-window (ARM-B2) support: every query position scores, including
 * on-ink positions at zero distance through the same finite regularized
 * kernel. No on-ink mask anywhere: worker, main-thread fallback and cached
 * columns all share this single path.
 *
 * Kernel: bubble g / (1 + (r/scale)^q); strengths use q+1. Query points are
 * integer ink-plane positions (x = left + col, y = top + row, shared
 * baseline band). Nearest ink uses first-index ties over row-major points,
 * matching numpy argmin. Gradients match numpy.gradient edge_order=1.
 * No interpolation: every reported setting is evaluated, never snapped.
 */
(function (root) {
  "use strict";

  var SECOND_EXPONENT_OFFSET = 1.0;
  var WINDOW_FACTOR = 6.0;
  var WINDOW_MIN = 4;
  var TIE_TOLERANCE = 1e-9;
  var CANDIDATE_DELTAS = [-2, -1, 0, 1, 2];
  var GRADIENT_FLOOR = 1e-6;

  function pixelRound(value) {
    if (value >= 0) return Math.floor(value + 0.5);
    return Math.ceil(value - 0.5);
  }

  /* Ink points in row-major order (row outer, col inner), the same order
   * numpy.nonzero yields, so nearest ties resolve identically. */
  function inkPoints(cell) {
    var xs = [],
      ys = [],
      vs = [];
    for (var row = 0; row < cell.h; row++) {
      for (var col = 0; col < cell.w; col++) {
        var v = cell.cover[row * cell.w + col];
        if (v > 0) {
          xs.push(cell.left + col);
          ys.push(cell.top + row);
          vs.push(v);
        }
      }
    }
    return { x: xs, y: ys, v: vs, n: xs.length };
  }

  function tightBounds(ink) {
    var x0 = Infinity,
      x1 = -Infinity,
      y0 = Infinity,
      y1 = -Infinity;
    for (var i = 0; i < ink.n; i++) {
      if (ink.x[i] < x0) x0 = ink.x[i];
      if (ink.x[i] > x1) x1 = ink.x[i];
      if (ink.y[i] < y0) y0 = ink.y[i];
      if (ink.y[i] > y1) y1 = ink.y[i];
    }
    return [x0, x1, y0, y1];
  }

  /* Brute-force Euclidean nearest; strictly-less keeps the first (row-major)
   * point on ties, as numpy.argmin does. The optional oy shifts the ink in
   * y for display-only multi-line strips; the scorer always passes 0. */
  function nearest(ink, qx, qy, ox, oy) {
    var n = qx.length,
      dist = new Array(n),
      val = new Array(n);
    var shy = oy || 0;
    for (var k = 0; k < n; k++) {
      var best = Infinity,
        bv = 0;
      for (var i = 0; i < ink.n; i++) {
        var dx = qx[k] - (ink.x[i] + ox),
          dy = qy[k] - (ink.y[i] + shy);
        var d2 = dx * dx + dy * dy;
        if (d2 < best) {
          best = d2;
          bv = ink.v[i];
        }
      }
      dist[k] = Math.sqrt(best);
      val[k] = bv;
    }
    return { dist: dist, val: val };
  }

  /* numpy.gradient on a row-major HxW grid, unit spacing, first-order edges:
   * interior central difference over 2, one-sided difference at borders. */
  function gradientOppose(dl, dr, H, W) {
    var out = new Array(H * W);
    for (var iy = 0; iy < H; iy++) {
      for (var ix = 0; ix < W; ix++) {
        var k = iy * W + ix;
        var glx = ix === 0 ? dl[k + 1] - dl[k] : ix === W - 1 ? dl[k] - dl[k - 1] : (dl[k + 1] - dl[k - 1]) / 2;
        var gly = iy === 0 ? dl[k + W] - dl[k] : iy === H - 1 ? dl[k] - dl[k - W] : (dl[k + W] - dl[k - W]) / 2;
        var grx = ix === 0 ? dr[k + 1] - dr[k] : ix === W - 1 ? dr[k] - dr[k - 1] : (dr[k + 1] - dr[k - 1]) / 2;
        var gry = iy === 0 ? dr[k + W] - dr[k] : iy === H - 1 ? dr[k] - dr[k - W] : (dr[k + W] - dr[k - W]) / 2;
        var nl = Math.hypot(glx, gly),
          nr = Math.hypot(grx, gry);
        if (nl > GRADIENT_FLOOR && nr > GRADIENT_FLOOR) {
          out[k] = (1 - ((glx / nl) * (grx / nr) + (gly / nl) * (gry / nr))) / 2;
        } else {
          out[k] = 0.5;
        }
      }
    }
    return out;
  }

  /* Occupied ink cells at an integer origin; left/top truncate toward zero
   * as Python int() does. */
  function occupied(cell, originX) {
    var set = {};
    var left = Math.trunc(cell.left),
      top = Math.trunc(cell.top);
    for (var row = 0; row < cell.h; row++) {
      for (var col = 0; col < cell.w; col++) {
        if (cell.cover[row * cell.w + col] > 0) {
          set[originX + left + col + "," + (top + row)] = 1;
        }
      }
    }
    return set;
  }

  function contactCounts(leftCell, rightCell, offset) {
    var left = occupied(leftCell, 0),
      right = occupied(rightCell, offset);
    var overlaps = 0,
      key;
    for (key in right) {
      if (Object.prototype.hasOwnProperty.call(left, key)) overlaps++;
    }
    if (overlaps) return { overlaps: overlaps, faces: 0, corners: 0 };
    var faces = 0,
      corners = 0;
    var rightKeys = Object.keys(right);
    for (var i = 0; i < rightKeys.length; i++) {
      var parts = rightKeys[i].split(",");
      var x = Number(parts[0]),
        y = Number(parts[1]);
      for (var dx = -1; dx <= 1; dx++) {
        for (var dy = -1; dy <= 1; dy++) {
          if (dx === 0 && dy === 0) continue;
          if (Object.prototype.hasOwnProperty.call(left, x + dx + "," + (y + dy))) {
            if (dx === 0 || dy === 0) faces++;
            else corners++;
          }
        }
      }
    }
    return { overlaps: 0, faces: faces, corners: corners };
  }

  /* Scale-only intermediates: window, nearest distances/values and the
   * opposing-gradient field. Independent of falloff and cohesion, so one
   * evaluation serves every falloff at this scale. Null when the step is
   * unusable before any exponent enters (blank, overlap, no background). */
  function scaleIntermediates(leftInk, rightInk, leftTight, rightTight, metric, step, scale) {
    var offset = step;
    var radius = Math.ceil(WINDOW_FACTOR * scale) + WINDOW_MIN;
    var xmin = Math.floor(Math.min(leftTight[0], rightTight[0] + offset) - radius);
    var xmax = Math.ceil(Math.max(leftTight[1], rightTight[1] + offset) + radius);
    var ymin = Math.floor(Math.min(leftTight[2], rightTight[2]) - radius);
    var ymax = Math.ceil(Math.max(leftTight[3], rightTight[3]) + radius);
    var W = xmax - xmin + 1,
      H = ymax - ymin + 1;
    var n = W * H;
    var qx = new Array(n),
      qy = new Array(n);
    var k = 0;
    for (var iy = 0; iy < H; iy++) {
      for (var ix = 0; ix < W; ix++, k++) {
        qx[k] = xmin + ix;
        qy[k] = ymin + iy;
      }
    }
    var nl = nearest(leftInk, qx, qy, 0);
    var nr = nearest(rightInk, qx, qy, offset);
    var oppose = gradientOppose(nl.dist, nr.dist, H, W);
    var rl = [],
      rr = [],
      gl = [],
      gr = [],
      op = [];
    for (var j = 0; j < n; j++) {
      rl.push(nl.dist[j]);
      rr.push(nr.dist[j]);
      gl.push(nl.val[j]);
      gr.push(nr.val[j]);
      op.push(oppose[j]);
    }
    if (!rl.length) return null;
    return { rl: rl, rr: rr, gl: gl, gr: gr, op: op };
  }

  /* Falloff-dependent finish over cached scale intermediates. */
  function finishGeometry(mid, metric, step, scale, falloff, contact) {
    var rl = mid.rl,
      rr = mid.rr,
      gl = mid.gl,
      gr = mid.gr,
      op = mid.op;
    var n = rl.length;
    var bl = new Array(n),
      br = new Array(n);
    var sl = new Array(n),
      sr = new Array(n);
    var eq = new Array(n);
    var spread = Math.max(scale / 2, GRADIENT_FLOOR);
    var denom2 = 2 * spread * spread;
    var q2 = falloff + SECOND_EXPONENT_OFFSET;
    for (var i = 0; i < n; i++) {
      bl[i] = gl[i] / (1 + Math.pow(rl[i] / scale, falloff));
      br[i] = gr[i] / (1 + Math.pow(rr[i] / scale, falloff));
      sl[i] = gl[i] / (1 + Math.pow(rl[i] / scale, q2));
      sr[i] = gr[i] / (1 + Math.pow(rr[i] / scale, q2));
      var d = rl[i] - rr[i];
      eq[i] = Math.exp(-(d * d) / denom2);
    }
    var attSum = 0;
    var att = new Array(n);
    for (var j = 0; j < n; j++) {
      att[j] = eq[j] * op[j] * (sl[j] * sr[j]);
      attSum += att[j];
    }
    if (!isFinite(attSum) || attSum <= 0) {
      return {
        step: step,
        valid: false,
        reason: "zero_attention",
        metric: metric,
        overlaps: 0,
        faces: contact.faces,
        corners: contact.corners,
      };
    }
    var num = 0,
      dd = 0,
      sp = 0,
      ds = 0,
      or = 0;
    for (var m = 0; m < n; m++) {
      var w = att[m] / attSum;
      num += att[m] * (bl[m] + br[m]);
      dd += w * Math.abs(rl[m] - rr[m]);
      sp += w * sl[m] * sr[m];
      ds += w * (rl[m] + rr[m]);
      or += w * op[m];
    }
    var interaction = num / attSum;
    if (!isFinite(interaction)) {
      return {
        step: step,
        valid: false,
        reason: "nonfinite_score",
        metric: metric,
        overlaps: 0,
        faces: contact.faces,
        corners: contact.corners,
      };
    }
    return {
      step: step,
      valid: true,
      reason: null,
      metric: metric,
      interaction: interaction,
      attention_sum: attSum,
      fields: { distance_disagreement: dd, strength_product: sp, distance_sum: ds, orientation: or },
      overlaps: 0,
      faces: contact.faces,
      corners: contact.corners,
      delta_vs_metric: step - metric,
    };
  }

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
    for (i = 0; i < costs.length; i++) {
      if (!ok[i] || costs[i] === null || costs[i] === undefined) continue;
      if (!isFinite(costs[i])) continue;
      if (costs[i] <= best + TIE_TOLERANCE) min.push(i);
    }
    return min;
  }

  /* One compute session per (sample, profile): decoded glyph cells plus
   * geometry caches. L1 ink is exponent-free; L2 scale intermediates are
   * falloff-free; L3 finished records key on the full triple. */
  function createSession(cells) {
    var ink = {},
      tight = {};
    var l2 = {};
    var l2Order = [];
    var L2_CAP = 400;
    var l2Points = 0;
    var L2_POINTS_CAP = 250000;

    function getInk(cp) {
      if (!ink[cp]) {
        ink[cp] = inkPoints(cells[cp]);
        tight[cp] = tightBounds(ink[cp]);
      }
      return ink[cp];
    }

    function l2Get(pairKey, step, scale) {
      var key = pairKey + "|" + step + "|" + scale;
      var hit = l2[key];
      if (hit !== undefined) return hit;
      return null;
    }

    function l2Put(pairKey, step, scale, mid) {
      var key = pairKey + "|" + step + "|" + scale;
      if (l2[key] === undefined) {
        l2Order.push(key);
      } else if (l2[key]) {
        l2Points -= l2[key].rl.length;
      }
      l2[key] = mid;
      if (mid) l2Points += mid.rl.length;
      while (l2Order.length > L2_CAP || l2Points > L2_POINTS_CAP) {
        var oldest = l2Order.shift();
        if (l2[oldest]) l2Points -= l2[oldest].rl.length;
        delete l2[oldest];
      }
    }

    function scoreStep(pairKey, leftCp, rightCp, metric, step, scale, falloff) {
      var leftCell = cells[leftCp],
        rightCell = cells[rightCp];
      var leftInk = getInk(leftCp),
        rightInk = getInk(rightCp);
      if (!leftInk.n || !rightInk.n) {
        return { step: step, valid: false, reason: "blank_glyph_no_ink", metric: metric };
      }
      var contact = contactCounts(leftCell, rightCell, step);
      if (contact.overlaps > 0) {
        return {
          step: step,
          valid: false,
          reason: "occupied_cell_overlap",
          metric: metric,
          overlaps: contact.overlaps,
          faces: contact.faces,
          corners: contact.corners,
        };
      }
      var mid = l2Get(pairKey, step, scale);
      if (mid === null) {
        mid = scaleIntermediates(leftInk, rightInk, tight[leftCp], tight[rightCp], metric, step, scale);
        l2Put(pairKey, step, scale, mid);
      }
      if (mid === null) {
        return {
          step: step,
          valid: false,
          reason: "no_background_window",
          metric: metric,
          overlaps: 0,
          faces: contact.faces,
          corners: contact.corners,
        };
      }
      return finishGeometry(mid, metric, step, scale, falloff, contact);
    }

    /* Score the five integer candidates of one pair at one setting.
     * Returns shipped-table-shaped geometry plus the shared-rule choice. */
    function scorePair(pairKey, leftCp, rightCp, metric, scale, falloff, cohesion) {
      var geos = CANDIDATE_DELTAS.map(function (delta) {
        return scoreStep(pairKey, leftCp, rightCp, metric, metric + delta, scale, falloff);
      });
      var entry = {
        ok: geos.map(function (g) {
          return g.valid;
        }),
        inter: geos.map(function (g) {
          return g.valid ? g.interaction : null;
        }),
        att: geos.map(function (g) {
          return g.valid ? g.attention_sum : null;
        }),
        why: geos.map(function (g) {
          return g.reason;
        }),
        fld: geos.map(function (g) {
          if (!g.valid) return null;
          return [
            g.fields.distance_disagreement,
            g.fields.strength_product,
            g.fields.distance_sum,
            g.fields.orientation,
          ];
        }),
        ov: geos.map(function (g) {
          return g.overlaps || 0;
        }),
        fa: geos.map(function (g) {
          return g.faces || 0;
        }),
        co: geos.map(function (g) {
          return g.corners || 0;
        }),
      };
      var costs = entry.inter.map(function (v, i) {
        if (!entry.ok[i] || v === null || v === undefined) return null;
        return Math.abs(v - cohesion);
      });
      var steps = CANDIDATE_DELTAS.map(function (d) {
        return metric + d;
      });
      var min = selectIndices(costs, entry.ok);
      var chosen, fallback;
      if (!min.length) {
        chosen = metric;
        fallback = true;
      } else {
        var best = min[0],
          bi;
        for (bi = 1; bi < min.length; bi++) {
          var a = steps[min[bi]],
            b = steps[best];
          if (Math.abs(a - metric) < Math.abs(b - metric) || (Math.abs(a - metric) === Math.abs(b - metric) && a < b)) {
            best = min[bi];
          }
        }
        chosen = steps[best];
        fallback = false;
      }
      return { entry: entry, steps: steps, costs: costs, chosen: chosen, fallback: fallback };
    }

    return {
      scoreStep: scoreStep,
      scorePair: scorePair,
      cacheSizes: function () {
        return { glyphs: Object.keys(ink).length, scaleColumns: l2Order.length, scalePoints: l2Points };
      },
    };
  }

  /* Minimal SHA-256 over UTF-8, for settings identities matching Python
   * hashlib (canonical JSON below must use Python float spellings). */
  function sha256(ascii) {
    var K = [
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98,
      0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
      0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8,
      0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
      0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819,
      0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
      0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
      0xc67178f2,
    ];
    var H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    var bytes = [];
    for (var i = 0; i < ascii.length; i++) bytes.push(ascii.charCodeAt(i) & 255);
    var bitLen = bytes.length * 8;
    bytes.push(0x80);
    while (bytes.length % 64 !== 56) bytes.push(0);
    for (var s = 7; s >= 0; s--) bytes.push((bitLen / Math.pow(2, s * 8)) & 255);
    function rotr(x, n) {
      return (x >>> n) | (x << (32 - n));
    }
    for (var c = 0; c < bytes.length; c += 64) {
      var w = new Array(64);
      for (var t = 0; t < 16; t++) {
        w[t] =
          ((bytes[c + t * 4] << 24) |
            (bytes[c + t * 4 + 1] << 16) |
            (bytes[c + t * 4 + 2] << 8) |
            bytes[c + t * 4 + 3]) >>>
          0;
      }
      for (var u = 16; u < 64; u++) {
        var s0 = (rotr(w[u - 15], 7) ^ rotr(w[u - 15], 18) ^ (w[u - 15] >>> 3)) >>> 0;
        var s1 = (rotr(w[u - 2], 17) ^ rotr(w[u - 2], 19) ^ (w[u - 2] >>> 10)) >>> 0;
        w[u] = (w[u - 16] + s0 + w[u - 7] + s1) >>> 0;
      }
      var a = H[0],
        b = H[1],
        cc = H[2],
        d = H[3];
      var e = H[4],
        f = H[5],
        g = H[6],
        h = H[7];
      for (var v = 0; v < 64; v++) {
        var S1 = (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) >>> 0;
        var ch = ((e & f) ^ (~e & g)) >>> 0;
        var t1 = (h + S1 + ch + K[v] + w[v]) >>> 0;
        var S0 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) >>> 0;
        var mj = ((a & b) ^ (a & cc) ^ (b & cc)) >>> 0;
        var t2 = (S0 + mj) >>> 0;
        h = g;
        g = f;
        f = e;
        e = (d + t1) >>> 0;
        d = cc;
        cc = b;
        b = a;
        a = (t1 + t2) >>> 0;
      }
      H[0] = (H[0] + a) >>> 0;
      H[1] = (H[1] + b) >>> 0;
      H[2] = (H[2] + cc) >>> 0;
      H[3] = (H[3] + d) >>> 0;
      H[4] = (H[4] + e) >>> 0;
      H[5] = (H[5] + f) >>> 0;
      H[6] = (H[6] + g) >>> 0;
      H[7] = (H[7] + h) >>> 0;
    }
    return H.map(function (x) {
      return ("00000000" + x.toString(16)).slice(-8);
    }).join("");
  }

  /* Python json.dumps float spelling for the small magnitudes used here:
   * integral floats keep ".0", others use shortest round-trip digits. */
  function pyFloat(x) {
    if (Number.isInteger(x)) return x.toFixed(1);
    return String(x);
  }

  function settingsIdentity(model, implementation, cohesion, scale, falloff) {
    var canonical =
      '{"controls":{"cohesion":' +
      pyFloat(cohesion) +
      ',"feature_scale":' +
      pyFloat(scale) +
      ',"proximity_falloff":' +
      pyFloat(falloff) +
      '},"implementation":"' +
      implementation +
      '","model":"' +
      model +
      '"}';
    return sha256(canonical);
  }

  /* Single-kernel field component for the live explanation view: the exact
   * bubble expression used in finishGeometry (bl/br with exponent q), at one
   * query distance with one coverage value. Reach is the half-strength
   * distance: fieldStrength(reach, reach, falloff, g) === g / 2. This is a
   * field component only, not the normalized candidate score. */
  function fieldStrength(distance, reach, falloff, coverage) {
    return coverage / (1 + Math.pow(distance / reach, falloff));
  }

  /* Ink-plane extent of one decoded cell (cell.left/top plus ink offsets),
   * the same row-major order inkPoints uses. Null when the cell is blank. */
  function cellExtent(cell) {
    var ink = inkPoints(cell);
    if (!ink.n) return null;
    var b = tightBounds(ink);
    return { x0: b[0], x1: b[1], y0: b[2], y1: b[3] };
  }

  /* Per-letter component fields over a fixed frame, for the spatial blob
   * view. Each frame point takes its nearest ink sample per letter (right
   * letter shifted by the displayed step, Gray keeps delivered p/7
   * coverage) and evaluates the same bubble expression finishGeometry uses
   * for bl/br. Inside-ink points keep their zero-distance strength here,
   * as in the scorer, and the view draws ink opaque on top. */
  function pairFieldGrid(leftCell, rightCell, step, reach, falloff, frame) {
    var leftInk = inkPoints(leftCell),
      rightInk = inkPoints(rightCell);
    var n = frame.w * frame.h;
    var qx = new Array(n),
      qy = new Array(n);
    var k = 0;
    for (var iy = 0; iy < frame.h; iy++) {
      for (var ix = 0; ix < frame.w; ix++, k++) {
        qx[k] = frame.x0 + ix;
        qy[k] = frame.y0 + iy;
      }
    }
    var nl = nearest(leftInk, qx, qy, 0);
    var nr = nearest(rightInk, qx, qy, step);
    var bl = new Array(n),
      br = new Array(n);
    for (var j = 0; j < n; j++) {
      bl[j] = fieldStrength(nl.dist[j], reach, falloff, nl.val[j]);
      br[j] = fieldStrength(nr.dist[j], reach, falloff, nr.val[j]);
    }
    return { bl: bl, br: br, w: frame.w, h: frame.h };
  }

  /* Single-letter component field over a fixed frame, for the multiword
   * excerpt view. Each frame point takes this glyph's nearest ink sample at
   * its drawn origin (Gray keeps delivered p/7 coverage) and evaluates the
   * same bubble expression, including zero-distance points. One grid per
   * drawn glyph; the view composites them for display only, without changing
   * the pairwise scorer. The optional oy carries the strip line offset; the
   * scorer never uses it. */
  function glyphFieldGrid(cell, ox, reach, falloff, frame, oy) {
    var ink = inkPoints(cell);
    var n = frame.w * frame.h;
    var qx = new Array(n),
      qy = new Array(n);
    var k = 0;
    for (var iy = 0; iy < frame.h; iy++) {
      for (var ix = 0; ix < frame.w; ix++, k++) {
        qx[k] = frame.x0 + ix;
        qy[k] = frame.y0 + iy;
      }
    }
    var nr = nearest(ink, qx, qy, ox, oy);
    var f = new Array(n);
    for (var j = 0; j < n; j++) {
      f[j] = fieldStrength(nr.dist[j], reach, falloff, nr.val[j]);
    }
    return { f: f, w: frame.w, h: frame.h };
  }

  var api = {
    TIE_TOLERANCE: TIE_TOLERANCE,
    CANDIDATE_DELTAS: CANDIDATE_DELTAS,
    GRADIENT_FLOOR: GRADIENT_FLOOR,
    fieldStrength: fieldStrength,
    cellExtent: cellExtent,
    pairFieldGrid: pairFieldGrid,
    glyphFieldGrid: glyphFieldGrid,
    pixelRound: pixelRound,
    createSession: createSession,
    scorePairDirect: function (cells, pairKey, leftCp, rightCp, metric, scale, falloff, cohesion) {
      return createSession(cells).scorePair(pairKey, leftCp, rightCp, metric, scale, falloff, cohesion);
    },
    settingsIdentity: settingsIdentity,
    sha256: sha256,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.YYCompute = api;
  }
})(typeof self !== "undefined" ? self : this);
