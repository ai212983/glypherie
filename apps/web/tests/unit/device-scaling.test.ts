// Device presentation math: reference size from the CSS reference density
// over PPI, Pixel 1:1 from the physical pixel grid, integer backing coverage
// in both modes.
import assert from "node:assert/strict";
import test from "node:test";
import {
  CSS_REFERENCE_PX_PER_IN,
  deviceBackingScale,
  oneToOneCssScale,
  referenceSizeCssScale,
} from "../../src/app/renderer/display-scaling.ts";

test("reference size divides the CSS reference density by the device PPI", () => {
  assert.equal(CSS_REFERENCE_PX_PER_IN, 96);
  assert.equal(referenceSizeCssScale(220), 96 / 220);
  assert.equal(referenceSizeCssScale(259), 96 / 259);
  assert.equal(referenceSizeCssScale(96), 1);
});

test("pixel 1:1 maps one device pixel onto one physical monitor pixel", () => {
  assert.equal(oneToOneCssScale(1), 1);
  assert.equal(oneToOneCssScale(2), 0.5);
  assert.equal(oneToOneCssScale(2.5), 1 / 2.5);
});

test("backing stays an integer multiple of the framebuffer", () => {
  assert.equal(deviceBackingScale(96 / 220, 2), Math.max(1, Math.round((96 / 220) * 2)));
  assert.equal(deviceBackingScale(0.5, 2), 1);
  assert.equal(deviceBackingScale(2, 2), 4);
  assert.ok(Number.isInteger(deviceBackingScale(96 / 119.8, 1)));
});

test("invalid densities fall back instead of collapsing the preview", () => {
  assert.equal(referenceSizeCssScale(0), 1);
  assert.equal(referenceSizeCssScale(Number.NaN), 1);
  assert.equal(oneToOneCssScale(0), 1);
  assert.equal(oneToOneCssScale(Number.NaN), 1);
  assert.equal(deviceBackingScale(0, 2), 1);
  assert.equal(deviceBackingScale(Number.NaN, 2), 1);
});
