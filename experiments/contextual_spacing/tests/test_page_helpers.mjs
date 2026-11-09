// Geometric controls for the diagnostic UI; no spacing-model calculations.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
const context = vm.createContext({});
vm.runInContext(readFileSync(new URL("../page.js", import.meta.url), "utf8"), context);
const { contactPixels, sourceLinearMono, layoutGrayscale, paint } = context.ContextualSpacing;
const bitmap = (pixels, width, left = 0, top = 0) => ({ pixels, width, height: pixels.length / width, left, top });
const dot = bitmap([1], 1);
assert.equal(contactPixels(dot, dot, 0).overlaps, 1);
assert.equal(contactPixels(dot, dot, 1).faces, 1);
assert.equal(contactPixels(dot, bitmap([1], 1, 0, 1), 1).corners, 1);
assert.equal(contactPixels(dot, dot, 2).pixels.length, 0);

// Independent exhaustive cell-pair oracle, unlike the UI's neighbor lookup.
let comparisons = 0;
for (let mask = 1; mask < 64; mask++)
  for (const step of [-2, 0, 1, 3]) {
    const a = bitmap(
      Array.from({ length: 6 }, (_, i) => (mask >> i) & 1),
      3,
      -2,
      1,
    );
    const b = bitmap(
      Array.from({ length: 6 }, (_, i) => (mask >> (5 - i)) & 1),
      2,
      1,
      -1,
    );
    const expected = { overlaps: 0, faces: 0, corners: 0 };
    for (let i = 0; i < a.pixels.length; i++)
      if (a.pixels[i])
        for (let j = 0; j < b.pixels.length; j++)
          if (b.pixels[j]) {
            const dx = Math.abs(a.left + (i % a.width) - (step + b.left + (j % b.width)));
            const dy = Math.abs(a.top + Math.floor(i / a.width) - (b.top + Math.floor(j / b.width)));
            if (dx === 0 && dy === 0) expected.overlaps++;
            else if (dx + dy === 1) expected.faces++;
            else if (dx === 1 && dy === 1) expected.corners++;
          }
    const actual = contactPixels(a, b, step);
    for (const key of Object.keys(expected)) assert.equal(actual[key], expected[key]);
    comparisons++;
  }
const original = {
  glyphs: [{ codepoint: 65, glyphId: 1, advancePx: 10, bitmap: dot }],
  sizePx: 16,
  metricsAscent: 8,
  metricsDescent: -2,
  sourceLayout: {
    spacingPolicy: "source_linear_26_6",
    advancesPx: { 65: 8.25 },
    pairAdjustmentsPx: { "65,65": -0.125 },
  },
};
const source = sourceLinearMono(original);
assert.equal(source.glyphs[0].advancePx, 8.25);
assert.equal(original.glyphs[0].advancePx, 10);
assert.equal(source.glyphs[0].bitmap, original.glyphs[0].bitmap, "reference reuses the exact binary cells");
const positions = layoutGrayscale(source, "AAA", 280);
assert.equal(positions.lines[0].placements[1].x_px, 8.125);
assert.equal(positions.lines[0].placements[2].x_px, 16.25);
const draws = [];
const ctx = {
  fillStyle: "",
  fillRect(x, y, w, h) {
    if (this.fillStyle === "black") draws.push([x, y, w, h]);
  },
};
paint(
  {
    style: {},
    getContext() {
      return ctx;
    },
  },
  source,
  positions,
  1,
);
assert.deepEqual(
  draws.map((draw) => draw[0]),
  [0, 8, 16],
  "only accumulated draw origins snap to integer pixels",
);
console.log(
  JSON.stringify({
    status: "passed",
    contactOracleComparisons: comparisons,
    sourceBitmapIdentity: true,
    fractionalAccumulation: true,
  }),
);
