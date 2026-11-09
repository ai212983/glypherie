// Shared DPR sanitizer: the single owner and both consumers agree that only
// positive finite readings pass through, everything else falls back to 1.
import assert from "node:assert/strict";
import test from "node:test";
import { sanitizeDevicePixelRatio } from "../../src/app/renderer/display-scaling.ts";
import { liveRatioOf } from "../../src/app/renderer/live-ratio.ts";
import { resolveMonitorReading } from "../../src/app/features/screen/monitor-info.ts";

test("the shared owner passes positive finite ratios and falls back to 1", () => {
  assert.equal(sanitizeDevicePixelRatio(2), 2);
  assert.equal(sanitizeDevicePixelRatio(1.5), 1.5);
  // Sub-unit positive ratios stay exact: the bound is 0, not 1.
  assert.equal(sanitizeDevicePixelRatio(0.5), 0.5);
  for (const raw of [0, -2, Number.NaN, Number.POSITIVE_INFINITY, "wide", undefined, null, {}]) {
    assert.equal(sanitizeDevicePixelRatio(raw), 1, `falls back for ${String(raw)}`);
  }
});

test("both consumers agree with the shared owner", () => {
  for (const raw of [2, 1.5, 0.5, 0, -1, Number.NaN, "wide", undefined]) {
    const expected = sanitizeDevicePixelRatio(raw);
    assert.equal(liveRatioOf(raw), expected);
    assert.equal(resolveMonitorReading({ screenWidth: 100, screenHeight: 100, devicePixelRatio: raw }).dpr, expected);
  }
});
