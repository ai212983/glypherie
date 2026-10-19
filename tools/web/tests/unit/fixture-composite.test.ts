import assert from "node:assert/strict";
import test from "node:test";
import { compositeSourceOver } from "../../src/app/renderer/fixture-renderer.ts";

test("opaque ink over opaque paper replaces exactly", () => {
  assert.deepEqual(
    compositeSourceOver([200, 30, 30, 255], [255, 255, 255, 255], 1),
    [200, 30, 30, 255],
  );
});

test("explicit entries over transparency apply verbatim", () => {
  assert.deepEqual(
    compositeSourceOver([20, 200, 30, 32], [0, 0, 0, 0], 1),
    [20, 200, 30, 32],
  );
});

test("empty over empty stays blank", () => {
  assert.deepEqual(compositeSourceOver([0, 0, 0, 0], [0, 0, 0, 0], 1), [0, 0, 0, 0]);
});

test("partial ink over opaque paper blends opaque, not translucent", () => {
  assert.deepEqual(
    compositeSourceOver([30, 90, 200, 160], [255, 255, 255, 255], 3 / 7),
    [194, 211, 240, 255],
  );
});

test("partial ink over partial background blends both alphas", () => {
  assert.deepEqual(
    compositeSourceOver([30, 90, 200, 160], [10, 20, 30, 40], 1),
    [28, 84, 186, 175],
  );
});

test("zero coverage leaves the background untouched", () => {
  assert.deepEqual(
    compositeSourceOver([30, 90, 200, 160], [10, 20, 30, 40], 0),
    [10, 20, 30, 40],
  );
});

test("coverage scales source alpha in floating point without pre-rounding", () => {
  // Pre-rounding alpha (1 * 0.5 -> 1 or 0) would give [254, ...] or the
  // background; the floating scale lands on opaque white here.
  assert.deepEqual(
    compositeSourceOver([100, 0, 0, 1], [255, 255, 255, 255], 0.5),
    [255, 255, 255, 255],
  );
});
