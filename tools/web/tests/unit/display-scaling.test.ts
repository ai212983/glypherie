import assert from "node:assert/strict";
import test from "node:test";
import {
  backingSize,
  cssSize,
  devicePhase,
  effectiveZoom,
  formatEffectiveZoom,
  magnification,
  nativeHeightCap,
  nativeWidthFor,
  snapTranslation,
} from "../../src/app/renderer/display-scaling.ts";

test("magnification rounds requested zoom in physical pixels, at least one", () => {
  assert.equal(magnification(1, 1), 1);
  assert.equal(magnification(2, 1), 2);
  assert.equal(magnification(4, 2), 8);
  // Fractional ratios from real compositing environments.
  assert.equal(magnification(1, 1.125), 1);
  assert.equal(magnification(2, 1.125), 2);
  assert.equal(magnification(3, 1.125), 3);
  assert.equal(magnification(4, 1.125), 5);
  assert.equal(magnification(2, 1.5), 3);
  assert.equal(magnification(1, 2), 2);
  // Degenerate inputs stay safe instead of throwing.
  assert.equal(magnification(0, 1), 1);
  assert.equal(magnification(2, 0), 2);
  assert.equal(magnification(NaN, 1.25), 1);
});

test("effective zoom is the achieved CSS magnification", () => {
  assert.equal(effectiveZoom(2, 1), 2);
  assert.ok(Math.abs(effectiveZoom(2, 1.125) - 2 / 1.125) < 1e-12);
  assert.ok(Math.abs(effectiveZoom(1, 1.125) - 1 / 1.125) < 1e-12);
  assert.equal(effectiveZoom(0, 1), 1);
});

test("native width floors to avoid a partial trailing block", () => {
  assert.equal(nativeWidthFor(1000, 2, 1.125), Math.floor((1000 * 1.125) / 2));
  assert.equal(nativeWidthFor(720, 1, 1), 720);
  // floor, not ceil/round: 721 CSS px at 2x holds 360 whole source px.
  assert.equal(nativeWidthFor(721, 2, 1), 360);
  assert.equal(nativeWidthFor(0, 2, 1), 1);
  assert.equal(nativeWidthFor(-5, 2, 1), 1);
  assert.equal(nativeWidthFor(100000, 1, 2), 4096);
});

test("native height cap respects renderer and browser backing limits", () => {
  assert.equal(nativeHeightCap(100, 1), 4096);
  assert.equal(nativeHeightCap(100, 2), 4096);
  // Browser backing limit binds for large magnifications.
  assert.equal(nativeHeightCap(100, 8), Math.floor(16384 / 8));
  assert.equal(nativeHeightCap(100, 5), Math.floor(16384 / 5));
  // Renderer texel bound binds for very wide requests.
  assert.equal(nativeHeightCap(4096, 1), Math.min(4096, Math.floor(16777216 / 4096)));
});

test("backing and CSS sizes convert through the device ratio", () => {
  assert.deepEqual(backingSize(360, 40, 2), { width: 720, height: 80 });
  assert.equal(cssSize(720, 1.125), 640);
  assert.equal(cssSize(720, 1), 720);
});

test("grid snapping shifts inside the viewport by less than one device pixel", () => {
  assert.deepEqual(snapTranslation(100, 50, 1), { dx: 0, dy: 0 });
  const ratio = 1.125;
  const { dx, dy } = snapTranslation(100.3, 50.7, ratio);
  // Ceil-snap: non-negative and strictly inside one device pixel, so the
  // first painted row/column is never pushed past the viewport origin.
  assert.ok(dx >= 0 && dx < 1 / ratio, `dx=${dx}`);
  assert.ok(dy >= 0 && dy < 1 / ratio, `dy=${dy}`);
  // Reapplying the translation lands on the next whole physical pixel.
  assert.equal(devicePhase(100.3 + dx, ratio) < 1e-9, true);
  assert.equal(devicePhase(50.7 + dy, ratio) < 1e-9, true);
  assert.deepEqual(snapTranslation(100, 50, 0), { dx: 0, dy: 0 });
});

test("effective zoom formats compactly", () => {
  assert.equal(formatEffectiveZoom(1), "1×");
  assert.equal(formatEffectiveZoom(2), "2×");
  assert.equal(formatEffectiveZoom(2 / 1.125), "1.78×");
  assert.equal(formatEffectiveZoom(1 / 1.125), "0.89×");
  assert.equal(formatEffectiveZoom(NaN), "1×");
});
