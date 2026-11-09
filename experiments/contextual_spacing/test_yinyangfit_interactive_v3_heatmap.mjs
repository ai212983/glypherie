// cspell:words yinyangfit brewer
// Layered-heatmap transfer checks: fixed ramp content and provenance
// shape, scalar-coupled hue and opacity, discrete per-pixel paint with
// no cross-pixel smoothing, per-pixel MAX hue correctness, zero/blank
// inputs, and the full visibility matrix with ink last.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const dir = dirname(fileURLToPath(import.meta.url));
function loadGlobal(path, name) {
  const sandbox = {};
  vm.createContext(sandbox);
  vm.runInContext(readFileSync(path, "utf8"), sandbox);
  assert.ok(sandbox[name], `${name} loads from ${path}`);
  return sandbox[name];
}

const YYV = loadGlobal(join(dir, "yinyangfit_interactive_v3_visual.js"), "YYVisual");

function mockPaint(fields, runs, profile, layers, alphas, gains, opts) {
  const ops = [];
  const ctx = {
    setTransform() {},
    clearRect() {},
    set fillStyle(v) {
      ops.push({ style: v });
    },
    fillRect(x, y, w, h) {
      ops[ops.length - 1].rect = [x, y, w, h];
    },
  };
  const canvas = { style: {}, getContext: () => ctx };
  YYV.drawExcerptField(canvas, fields, { x0: 0, y0: 0, w: 4, h: 4 }, runs, profile, layers, alphas, 1, gains, opts);
  return ops;
}

const ALPHAS = { letter: 0.65, contrib: 1 };
const GAINS = { slate: 6, contrib: 4 };
const INK_RUN = [{ ox: 0, oy: 0, cell: { w: 1, h: 1, left: 3, top: 3, cover: [1] } }];

// Fixed ramp content: nine published stops per layer with the expected
// weak/strong character on each end.
assert.equal(YYV.LETTER_RAMP_STOPS.length, 9, "cool ramp has nine stops");
assert.equal(YYV.CONTRIB_RAMP_STOPS.length, 9, "warm ramp has nine stops");
{
  const [r0, g0, b0] = [...YYV.rampRgb(YYV.LETTER_RAMP_STOPS, 0)];
  const [r1, g1, b1] = [...YYV.rampRgb(YYV.LETTER_RAMP_STOPS, 1)];
  assert.ok(b0 > r0 && r0 < 64, "cool weak end is deep blue");
  assert.ok(r1 > 240 && g1 > 240 && b1 > 240, "cool strong end is near-white pale blue");
  const [wr0, wg0, wb0] = [...YYV.rampRgb(YYV.CONTRIB_RAMP_STOPS, 0)];
  const [wr1, wg1, wb1] = [...YYV.rampRgb(YYV.CONTRIB_RAMP_STOPS, 1)];
  assert.ok(wr0 > wb0 && wg0 < 64, "warm weak end is dark red");
  assert.ok(wr1 > 240 && wg1 > 240 && wb1 > 128, "warm strong end is pale yellow");
  // Bright cores: the strong warm end is the brightest lookup output.
  const top = wr1 + wg1 + wb1;
  for (const u of [0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875]) {
    const [r, g, b] = [...YYV.rampRgb(YYV.CONTRIB_RAMP_STOPS, u)];
    assert.ok(r + g + b <= top, `warm ramp brightest at u=1 (u=${u})`);
  }
}

// Scalar couples hue and opacity together: different scalars paint
// different hues, and the stronger scalar paints more opaquely.
{
  const weak = mockPaint([{ x0: 0, y0: 0, w: 1, h: 1, f: [0.1] }], [], "mono", null, ALPHAS, GAINS);
  const strong = mockPaint([{ x0: 0, y0: 0, w: 1, h: 1, f: [0.9] }], [], "mono", null, ALPHAS, GAINS);
  assert.equal(weak.length, 1, "weak scalar paints");
  assert.equal(strong.length, 1, "strong scalar paints");
  assert.notEqual(weak[0].style, strong[0].style, "hue follows the scalar");
  const lum = (s) =>
    s
      .match(/\d+/g)
      .slice(0, 3)
      .map(Number)
      .reduce((a, b) => a + b, 0);
  assert.ok(lum(strong[0].style) > lum(weak[0].style), "stronger scalar paints brighter");
}

// No smoothing across source pixels: a saturated neighbor does not
// leak hue or alpha into an adjacent zero pixel.
{
  const ops = mockPaint([{ x0: 0, y0: 0, w: 2, h: 1, f: [0, 1] }], [], "mono", null, ALPHAS, GAINS);
  assert.equal(ops.length, 1, "zero pixel stays unpainted beside a saturated one");
  assert.equal(ops[0].style, "rgb(250,252,255)", "saturated pixel keeps its own ramp color");
}

// Per-pixel MAX keeps the winning scalar's hue, never an average.
{
  const peak = mockPaint(
    [],
    [],
    "mono",
    [
      { x0: 0, y0: 0, w: 1, h: 1, c: [0.1] },
      { x0: 0, y0: 0, w: 1, h: 1, c: [0.9] },
    ],
    ALPHAS,
    GAINS,
  );
  const alone = mockPaint([], [], "mono", [{ x0: 0, y0: 0, w: 1, h: 1, c: [0.9] }], ALPHAS, GAINS);
  assert.equal(peak.length, 1, "overlap paints once");
  assert.equal(peak[0].style, alone[0].style, "MAX keeps the winning scalar exactly");
}

// Zero and blank inputs paint nothing on the field layers.
assert.equal(
  mockPaint([{ x0: 0, y0: 0, w: 1, h: 1, f: [0] }], [], "mono", null, ALPHAS, GAINS).length,
  0,
  "zero letter field paints nothing",
);
assert.equal(
  mockPaint([], [], "mono", [{ x0: 0, y0: 0, w: 1, h: 1, c: [0] }], ALPHAS, GAINS).length,
  0,
  "zero contribution map paints nothing",
);
assert.equal(mockPaint([null], [], "mono", null, ALPHAS, GAINS).length, 0, "blank letter entry paints nothing");
assert.equal(mockPaint([], [], "mono", [], ALPHAS, GAINS).length, 0, "no inputs paint nothing");

// Full visibility matrix on one pixel: defaults on, each layer alone,
// both off, master off, with ink last at identical positions.
{
  const field = [{ x0: 0, y0: 0, w: 1, h: 1, f: [1] }];
  const layer = [{ x0: 1, y0: 1, w: 1, h: 1, c: [1] }];
  const full = mockPaint(field, INK_RUN, "mono", layer, ALPHAS, GAINS);
  assert.equal(full.length, 3, "default paints cool, warm, ink");
  assert.equal(full[2].style, "#161616", "ink last in the default view");
  const bare = mockPaint(field, INK_RUN, "mono", layer, ALPHAS, GAINS, {});
  assert.deepEqual(
    bare.map((o) => o.style),
    full.map((o) => o.style),
    "empty opts default to both layers on",
  );
  const letterOnly = mockPaint(field, INK_RUN, "mono", layer, ALPHAS, GAINS, { showContrib: false });
  assert.equal(letterOnly.length, 2, "letter alone paints cool plus ink");
  assert.equal(letterOnly[1].style, "#161616", "ink last with letter alone");
  const contribOnly = mockPaint(field, INK_RUN, "mono", layer, ALPHAS, GAINS, { showLetter: false });
  assert.equal(contribOnly.length, 2, "contribution alone paints warm plus ink");
  assert.equal(contribOnly[1].style, "#161616", "ink last with contribution alone");
  const bothOff = mockPaint(field, INK_RUN, "mono", layer, ALPHAS, GAINS, { showLetter: false, showContrib: false });
  assert.deepEqual(
    bothOff.map((o) => o.style),
    ["#161616"],
    "both sublayers off paints ink alone",
  );
  const masterOff = mockPaint(field, INK_RUN, "mono", layer, ALPHAS, GAINS, { showFields: false });
  assert.deepEqual(
    masterOff.map((o) => o.style),
    ["#161616"],
    "master off paints ink alone with choices retained",
  );
  for (const ops of [letterOnly, contribOnly, bothOff, masterOff]) {
    assert.deepEqual(ops[ops.length - 1].rect, full[2].rect, "ink position identical in every visibility state");
  }
}
console.log("heatmap checks passed");
