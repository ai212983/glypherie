// Detectable monitor math: CSS screen dimensions and DPR resolve with
// explicit units; physical size and true PPI never appear.
import assert from "node:assert/strict";
import test from "node:test";
import { resolveMonitorReading } from "../../src/app/features/screen/monitor-info.ts";

const FULL = {
  screenWidth: 3440,
  screenHeight: 1440,
  devicePixelRatio: 1,
};

test("a full snapshot resolves screen size and DPR", () => {
  const reading = resolveMonitorReading(FULL);
  assert.deepEqual(reading.screen, { width: 3440, height: 1440 });
  assert.equal(reading.dpr, 1);
  assert.ok(!("ppi" in reading) && !("physical" in reading), "no physical density leaks out");
});

test("fractional DPR stays exact", () => {
  const reading = resolveMonitorReading({ ...FULL, devicePixelRatio: 1.5 });
  assert.equal(reading.dpr, 1.5);
  assert.deepEqual(reading.screen, { width: 3440, height: 1440 });
});

test("withheld or malformed metrics degrade to nulls and a DPR of 1", () => {
  const reading = resolveMonitorReading({
    screenWidth: undefined,
    screenHeight: 0,
    devicePixelRatio: 0,
  });
  assert.equal(reading.screen, null);
  assert.equal(reading.dpr, 1);
});
