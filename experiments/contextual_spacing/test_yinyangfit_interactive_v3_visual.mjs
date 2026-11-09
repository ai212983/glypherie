// cspell:words yinyangfit brewer
// Focused whole-text heatmap checks: fixed cool/warm sequential ramps,
// per-layer visibility, hue-plus-opacity transfer, and the preserved
// gains, crops, compositing and paint order.
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
// Display compositing is deterministic source-over on paper white.
const onlyLeft = YYV.compositeLayers([{ rgb: [29, 78, 216], a: 0.5 }]);
const blended = YYV.compositeLayers([
  { rgb: [29, 78, 216], a: 0.5 },
  { rgb: [194, 65, 12], a: 0.5 },
]);
assert.notEqual(blended, onlyLeft, "second layer stays visible in the blend");
assert.equal(
  blended,
  YYV.compositeLayers([
    { rgb: [29, 78, 216], a: 0.5 },
    { rgb: [194, 65, 12], a: 0.5 },
  ]),
  "blend is deterministic",
);
assert.equal(YYV.compositeLayers([]), "rgb(255,255,255)", "empty pixel stays paper white");

// Two fixed sequential ramps (display only), published ColorBrewer
// Blues and YlOrRd 9-class stops, cool reversed to stay faint and warm
// reversed so hotspots read as bright cores.
assert.deepEqual(
  [...YYV.LETTER_RAMP_STOPS],
  ["#08306b", "#08519c", "#2171b5", "#4292c6", "#6baed6", "#9ecae1", "#c6dbef", "#deebf7", "#f7fbff"],
  "cool ramp stops",
);
assert.deepEqual(
  [...YYV.CONTRIB_RAMP_STOPS],
  ["#800026", "#bd0026", "#e31a1c", "#fc4e2a", "#fd8d3c", "#feb24c", "#fed976", "#ffeda0", "#ffffcc"],
  "warm ramp stops",
);
assert.equal(YYV.SLATE_GAIN, 6, "slate gain fixed at 6");
assert.equal(YYV.CONTRIB_GAIN, 4, "interaction gain fixed at 4");
assert.equal(YYV.DEFAULT_LETTER_ALPHA, 0.65, "letter opacity default");
assert.equal(YYV.DEFAULT_CONTRIB_ALPHA, 1, "contribution opacity default");

// Fixed-ramp lookup: clamped endpoints land exactly on the end stops,
// the midpoint lands exactly on the middle stop, between stops the
// lookup interpolates linearly in RGB, and out-of-range clamps.
assert.deepEqual([...YYV.rampRgb(YYV.LETTER_RAMP_STOPS, 0)], [8, 48, 107], "cool weak end is deep blue");
assert.deepEqual([...YYV.rampRgb(YYV.LETTER_RAMP_STOPS, 1)], [247, 251, 255], "cool strong end is pale blue");
assert.deepEqual([...YYV.rampRgb(YYV.CONTRIB_RAMP_STOPS, 0)], [128, 0, 38], "warm weak end is dark red");
assert.deepEqual([...YYV.rampRgb(YYV.CONTRIB_RAMP_STOPS, 1)], [255, 255, 204], "warm strong end is pale yellow");
assert.deepEqual([...YYV.rampRgb(YYV.LETTER_RAMP_STOPS, 0.5)], [107, 174, 214], "cool midpoint is the middle stop");
assert.deepEqual([...YYV.rampRgb(YYV.CONTRIB_RAMP_STOPS, 0.5)], [253, 141, 60], "warm midpoint is the middle stop");
assert.deepEqual([...YYV.rampRgb(YYV.LETTER_RAMP_STOPS, 0.5625)], [133, 188, 220], "cool lookup interpolates linearly");
assert.deepEqual([...YYV.rampRgb(YYV.CONTRIB_RAMP_STOPS, -0.5)], [128, 0, 38], "below range clamps to weak end");
assert.deepEqual([...YYV.rampRgb(YYV.CONTRIB_RAMP_STOPS, 1.5)], [255, 255, 204], "above range clamps to strong end");

// Run frames carry placed ink plus cumulative drift, repeat
// exactly, and never take control inputs.
const rframe = YYV.frameForRuns(
  [
    [1, 7, -9, -1],
    [9, 15, -9, 2],
  ],
  8,
);
assert.ok(rframe.x0 <= 1 - (2 * 8 + YYV.FRAME_MARGIN), "drift margin kept");
assert.ok(rframe.x0 + rframe.w >= 15 + (2 * 8 + YYV.FRAME_MARGIN), "widest drift inside");
assert.deepEqual(
  {
    ...YYV.frameForRuns(
      [
        [1, 7, -9, -1],
        [9, 15, -9, 2],
      ],
      8,
    ),
  },
  { ...rframe },
  "run frame repeats exactly",
);

// drawExcerptField paints the cool letter layer, then the warm
// interaction layer, then ink last through a mock 2d context.
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
  YYV.drawExcerptField(canvas, fields, frame4, runs, profile, layers, alphas, 1, gains, opts);
  return ops;
}
const frame4 = { x0: 0, y0: 0, w: 4, h: 4 };
const oneField = [{ x0: 0, y0: 0, w: 2, h: 2, f: [0.5, 0.5, 0.5, 0.5] }];
const oneRun = [{ ox: 0, oy: 0, cell: { w: 1, h: 1, left: 1, top: 1, cover: [1] } }];
const oneLayer = [{ x0: 0, y0: 0, w: 1, h: 1, c: [0.5] }];
const ALPHAS = { letter: 0.65, contrib: 1 };
const GAINS = { slate: 6, contrib: 4 };
const shown = mockPaint(oneField, oneRun, "mono", oneLayer, ALPHAS, GAINS);
assert.equal(shown.length, 6, "cool quad + warm cell + ink");
assert.ok(
  shown.slice(0, 4).every((o) => o.style.startsWith("rgb(")),
  "cool layer paints blended quads first",
);
assert.ok(shown[4].style.startsWith("rgba("), "warm layer paints second");
assert.equal(shown[5].style, "#161616", "mono ink paints opaque black last");
// Saturated cores land on the pale ramp ends: hand-computed blends.
assert.equal(shown[0].style, "rgb(250,252,255)", "saturated cool core blends pale blue at letter opacity");
assert.equal(shown[4].style, "rgba(255,255,204,1.000)", "saturated warm core is pale yellow at full opacity");
const hidden = mockPaint(oneField, oneRun, "mono", oneLayer, ALPHAS, GAINS, { showFields: false });
assert.equal(hidden.length, 1, "master off paints ink alone");
assert.equal(hidden[0].style, "#161616", "hidden ink stays opaque black");
assert.deepEqual(hidden[0].rect, shown[5].rect, "ink position identical");
// Each sublayer hides alone while the other still paints.
const noLetter = mockPaint(oneField, oneRun, "mono", oneLayer, ALPHAS, GAINS, { showLetter: false });
assert.equal(noLetter.length, 2, "letter off keeps warm plus ink");
assert.ok(noLetter[0].style.startsWith("rgba("), "warm paints without the cool layer");
assert.equal(noLetter[1].style, "#161616", "ink last without the cool layer");
assert.deepEqual(noLetter[1].rect, shown[5].rect, "ink position identical without the cool layer");
const noContrib = mockPaint(oneField, oneRun, "mono", oneLayer, ALPHAS, GAINS, { showContrib: false });
assert.equal(noContrib.length, 5, "contribution off keeps cool quads plus ink");
assert.ok(
  noContrib.slice(0, 4).every((o) => o.style.startsWith("rgb(")),
  "cool paints without the warm layer",
);
assert.equal(noContrib[4].style, "#161616", "ink last without the warm layer");
const neither = mockPaint(oneField, oneRun, "mono", oneLayer, ALPHAS, GAINS, { showLetter: false, showContrib: false });
assert.equal(neither.length, 1, "both sublayers off behaves hidden");
assert.equal(neither[0].style, "#161616", "both-off ink stays opaque black");
assert.deepEqual(neither[0].rect, shown[5].rect, "ink position identical with both off");
const grayRun = [{ ox: 0, oy: 0, cell: { w: 1, h: 1, left: 1, top: 1, cover: [0.5] } }];
const gray = mockPaint(oneField, grayRun, "gray", oneLayer, ALPHAS, GAINS);
assert.equal(
  gray[gray.length - 1].style,
  "rgba(22,22,22,0.500)",
  "gray keeps coverage as source-over alpha, never opaque",
);
// Zero opacity on one ramp hides that ramp while the other still paints.
const zeroLetter = mockPaint(oneField, oneRun, "mono", oneLayer, { letter: 0, contrib: 1 }, GAINS);
assert.equal(zeroLetter.length, 2, "zero letter opacity keeps warm plus ink");
const zeroContrib = mockPaint(oneField, oneRun, "mono", oneLayer, { letter: 0.65, contrib: 0 }, GAINS);
assert.equal(zeroContrib.length, 5, "zero contrib opacity keeps cool plus ink");
const zeroBoth = mockPaint(oneField, oneRun, "mono", oneLayer, { letter: 0, contrib: 0 }, GAINS);
assert.equal(zeroBoth.length, 1, "zero opacity on both paints ink alone");
// Soft letter-field transfer: verified weak tails stay under the paint
// skip, saturated cores stay fully on, opacity scales linearly after
// the curve, interaction and ink untouched. u = clamp(gain * v, 0, 1),
// painted strength = u * u, alpha = strength * userAlpha.
function slateOps(f, letterAlpha = ALPHAS.letter) {
  return mockPaint(
    [{ x0: 0, y0: 0, w: 1, h: 1, f: [f] }],
    [],
    "mono",
    null,
    { letter: letterAlpha, contrib: ALPHAS.contrib },
    GAINS,
  );
}
// Verified weak tail (R8/q8 outer band, v = 0.01877): u = 0.1126, u^2 =
// 0.0127, below the existing 0.02 crop, so nothing paints.
assert.equal(slateOps(0.01877).length, 0, "weak tail suppressed");
// Endpoints and monotonic range through the real renderer.
assert.equal(slateOps(0).length, 0, "zero stays zero");
const strongOps = slateOps(1);
assert.equal(strongOps.length, 1, "saturated core paints");
assert.equal(strongOps[0].style, "rgb(250,252,255)", "u=1 keeps full user alpha on the pale end");
// Red-channel alpha readout against white at the ramp color for the
// same clamped scalar (the ramp itself is pinned to hardcoded stops
// above, so the curve under test stays the transfer, crop and scale).
function slateAlphaAt(style, v) {
  const m = /^rgb\((\d+),\s*(\d+),\s*(\d+)\)$/.exec(style);
  assert.ok(m, `blended cool style ${style}`);
  const u = Math.min(1, v * 6);
  const rampR = YYV.rampRgb(YYV.LETTER_RAMP_STOPS, u)[0];
  return (255 - Number(m[1])) / (255 - rampR);
}
const midAlphas = [0.05, 0.1, 0.2].map((v) => slateAlphaAt(slateOps(v)[0].style, v));
assert.ok(midAlphas[0] < midAlphas[1] && midAlphas[1] < midAlphas[2], "transfer monotonic");
assert.ok(Math.abs(midAlphas[0] - 0.09 * 0.65) < 0.01, "u=0.3 -> 0.09 strength");
assert.ok(Math.abs(midAlphas[1] - 0.36 * 0.65) < 0.01, "u=0.6 -> 0.36 strength");
// User opacity still scales linearly after the curve (u = 0.6 fixed,
// midAlphas[1] above is the 0.65 reference at the same strength).
const half = slateAlphaAt(slateOps(0.1, 0.325)[0].style, 0.1);
assert.ok(Math.abs(half * 2 - midAlphas[1]) < 0.01, "user opacity linear after curve");
// MAX compositing keeps the top lattice (0.2 beats 0.1 at the same pixel).
const maxOps = mockPaint(
  [
    { x0: 0, y0: 0, w: 1, h: 1, f: [0.1] },
    { x0: 0, y0: 0, w: 1, h: 1, f: [0.2] },
  ],
  [],
  "mono",
  null,
  ALPHAS,
  GAINS,
);
assert.equal(maxOps.length, 1, "overlap paints once");
assert.equal(maxOps[0].style, slateOps(0.2)[0].style, "MAX keeps the stronger lattice");
// Warm layer MAX across pairs, same gain and crop as before.
const interOps = mockPaint([], [], "mono", [{ x0: 0, y0: 0, w: 1, h: 1, c: [0.5] }], ALPHAS, GAINS);
assert.deepEqual(
  interOps.map((o) => o.style),
  ["rgba(255,255,204,1.000)"],
  "warm hue and alpha at the clamped scalar",
);
const interMax = mockPaint(
  [],
  [],
  "mono",
  [
    { x0: 0, y0: 0, w: 1, h: 1, c: [0.1] },
    { x0: 0, y0: 0, w: 1, h: 1, c: [0.2] },
  ],
  ALPHAS,
  GAINS,
);
assert.equal(interMax.length, 1, "pair overlap paints once");
assert.equal(
  interMax[0].style,
  mockPaint([], [], "mono", [{ x0: 0, y0: 0, w: 1, h: 1, c: [0.2] }], ALPHAS, GAINS)[0].style,
  "warm MAX keeps the stronger map",
);
console.log("visual checks passed");
