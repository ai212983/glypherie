import assert from "node:assert/strict";
import test from "node:test";
import {
  filterKerningPairs,
  formatKerningAdjustment,
  kerningCacheKey,
  pairCodepoints,
  type KerningPairView,
} from "../../src/app/features/preview/kerning.ts";

test("formats kerning adjustments as signed pixels at 26.6 precision", () => {
  assert.equal(formatKerningAdjustment(-52), "-0.8125 px");
  assert.equal(formatKerningAdjustment(64), "+1 px");
  assert.equal(formatKerningAdjustment(-64), "-1 px");
  assert.equal(formatKerningAdjustment(1), "+0.015625 px");
  assert.equal(pairCodepoints(0x41, 0x56), "U+0041 U+0056");
  assert.equal(pairCodepoints(0x20, 0x7e), "U+0020 U+007E");
});

test("keys kerning cache by size and axes independent of key order", () => {
  assert.equal(kerningCacheKey(16, { wght: 400 }), kerningCacheKey(16, { wght: 400 }));
  assert.notEqual(kerningCacheKey(16, { wght: 400 }), kerningCacheKey(18, { wght: 400 }));
  assert.notEqual(kerningCacheKey(16, { wght: 400 }), kerningCacheKey(16, { wght: 700 }));
  assert.equal(
    kerningCacheKey(16, { wght: 400, wdth: 100 }),
    kerningCacheKey(16, { wdth: 100, wght: 400 }),
  );
});

test("filters kerning pairs by characters or codepoints", () => {
  const pairs: KerningPairView[] = [
    { left: 0x41, right: 0x56, adjustment_26_6: -52 },
    { left: 0x54, right: 0x6f, adjustment_26_6: -20 },
  ];
  assert.equal(filterKerningPairs(pairs, "").length, 2);
  assert.deepEqual(filterKerningPairs(pairs, "AV"), [pairs[0]]);
  assert.deepEqual(filterKerningPairs(pairs, "av"), [pairs[0]]);
  assert.deepEqual(filterKerningPairs(pairs, "0041"), [pairs[0]]);
  assert.deepEqual(filterKerningPairs(pairs, "To"), [pairs[1]]);
  assert.deepEqual(filterKerningPairs(pairs, "zz"), []);
});
