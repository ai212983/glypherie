// Live DPR tracking: successive non-1/fractional transitions propagate
// without resize, stale queries go quiet, and Pixel 1:1 stays exact.
import assert from "node:assert/strict";
import test from "node:test";
import { liveRatioOf, watchLiveRatio } from "../../src/app/renderer/live-ratio.ts";
import { oneToOneCssScale } from "../../src/app/renderer/display-scaling.ts";

interface FakeQuery {
  listeners: Set<() => void>;
}

function harness(initialRatio: number): {
  setRatio: (value: number) => void;
  fire: (query: string) => void;
  listeners: (query: string) => number;
  seen: number[];
  stop: () => void;
} {
  let ratio = initialRatio;
  const queries = new Map<string, FakeQuery>();
  const seen: number[] = [];
  const matchMedia = (query: string) => {
    let entry = queries.get(query);
    if (!entry) {
      entry = { listeners: new Set() };
      queries.set(query, entry);
    }
    const current = entry;
    return {
      addEventListener: (_type: "change", listener: () => void): void => {
        current.listeners.add(listener);
      },
      removeEventListener: (_type: "change", listener: () => void): void => {
        current.listeners.delete(listener);
      },
    };
  };
  const stop = watchLiveRatio({
    current: () => ratio,
    matchMedia,
    onChange: (next) => {
      seen.push(next);
    },
  });
  return {
    setRatio: (value) => {
      ratio = value;
    },
    fire: (query) => {
      for (const listener of [...(queries.get(query)?.listeners ?? [])]) listener();
    },
    listeners: (query) => queries.get(query)?.listeners.size ?? 0,
    seen,
    stop,
  };
}

test("successive fractional DPR changes re-arm without resize", () => {
  const dpr = harness(1);
  assert.deepEqual(dpr.seen, [1]);
  assert.equal(dpr.listeners("(resolution: 1dppx)"), 1);

  // Non-1 transition, stale query retired.
  dpr.setRatio(2);
  dpr.fire("(resolution: 1dppx)");
  assert.deepEqual(dpr.seen, [1, 2]);
  assert.equal(dpr.listeners("(resolution: 2dppx)"), 1);
  assert.equal(dpr.listeners("(resolution: 1dppx)"), 0);

  // Fractional transitions keep re-arming; firing the retired query is quiet.
  dpr.setRatio(1.5);
  dpr.fire("(resolution: 2dppx)");
  assert.deepEqual(dpr.seen, [1, 2, 1.5]);
  dpr.fire("(resolution: 2dppx)");
  assert.deepEqual(dpr.seen, [1, 2, 1.5], "retired queries stay silent");

  dpr.setRatio(1.25);
  dpr.fire("(resolution: 1.5dppx)");
  assert.deepEqual(dpr.seen, [1, 2, 1.5, 1.25]);
  assert.equal(dpr.listeners("(resolution: 1.25dppx)"), 1);
  assert.equal(dpr.listeners("(resolution: 1.5dppx)"), 0);

  // Refiring the live query without a change reports nothing twice.
  dpr.fire("(resolution: 1.25dppx)");
  assert.deepEqual(dpr.seen, [1, 2, 1.5, 1.25]);

  // Every tracked ratio keeps Pixel 1:1 exact: one device px per monitor px.
  assert.deepEqual(
    dpr.seen.map((ratio) => oneToOneCssScale(ratio)),
    [1, 0.5, 1 / 1.5, 1 / 1.25],
  );

  dpr.stop();
  assert.equal(dpr.listeners("(resolution: 1.25dppx)"), 0, "cleanup detaches the live query");
});

test("raw DPR readings sanitize to a positive finite ratio", () => {
  assert.equal(liveRatioOf(2), 2);
  assert.equal(liveRatioOf(1.5), 1.5);
  for (const raw of [0, -1, Number.NaN, Number.POSITIVE_INFINITY, "wide", undefined]) {
    assert.equal(liveRatioOf(raw), 1, `falls back for ${String(raw)}`);
  }
});
