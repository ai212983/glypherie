import assert from "node:assert/strict";
import test from "node:test";
import { presetColors } from "../../src/app/palettes/render.ts";
import type { PalettePreset } from "../../src/app/palettes/model.ts";
import type { GrayCurve } from "../../src/app/features/grayscale/response-curve.ts";
import { sceneLabelPalette, scenePaperCss } from "../../src/app/features/scenes/scene-palette.ts";

const nonlinear: GrayCurve = [
  { value: 0, slope: 0, pinned: true },
  { value: 64, slope: 0, pinned: true },
  { value: 192, slope: 0, pinned: true },
  { value: 255, slope: 0, pinned: true },
];
const preset: PalettePreset = { id: 7, name: "Test", curve: nonlinear };

test("scene labels share the editor paper/ink mapping with only level 0 transparent", () => {
  for (const appearance of ["black-white", "warm-paper", "cool-paper"] as const) {
    for (const inverse of [false, true]) {
      const expected = presetColors(preset, appearance, inverse);
      const actual = sceneLabelPalette(nonlinear, appearance, inverse);
      assert.equal(actual.length, expected.length);
      for (let index = 0; index < expected.length; index += 1) {
        assert.deepEqual(actual[index]!.slice(0, 3), expected[index]!.slice(0, 3));
        assert.equal(actual[index]![3], index === 0 ? 0 : 255);
      }
    }
  }
});

test("inverse swaps the scene paper while level 0 stays transparent", () => {
  assert.equal(scenePaperCss("warm-paper", false), "#f4ecdc");
  assert.equal(scenePaperCss("warm-paper", true), "#1a1815");
  const palette = sceneLabelPalette(nonlinear, "warm-paper", true);
  assert.equal(palette[0]![3], 0);
  assert.ok(palette.slice(1).every((entry) => entry[3] === 255));
  const opaqueInverse = presetColors(preset, "warm-paper", true);
  assert.deepEqual(palette.map((entry) => entry.slice(0, 3)), opaqueInverse.map((entry) => entry.slice(0, 3)));
});
