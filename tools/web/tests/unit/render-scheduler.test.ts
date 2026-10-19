import assert from "node:assert/strict";
import test from "node:test";
import {
  RenderScheduler,
  buildRequestKey,
  type PaintOutcome,
  type RenderJob,
} from "../../src/app/renderer/render-scheduler.ts";
import { toRenderSpec } from "../../src/app/renderer/render-spec.ts";
import type { RenderPixels } from "../../src/app/renderer/client.ts";
import type { RenderSpec } from "../../src/app/renderer/renderer-types.ts";

const flush = (): Promise<void> => new Promise((resolve) => setImmediate(resolve));
const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

function pixels(width: number, height: number, lineHeights: number[], missing: number[] = []): RenderPixels {
  return {
    width,
    height,
    pixels: new ArrayBuffer(width * height * 4),
    layout: {
      lines: lineHeights.map((height_px) => ({ height_px })),
      missing_codepoints: missing,
    },
  };
}

const contentHeight = (data: RenderPixels): number =>
  data.layout?.lines.reduce((sum, line) => sum + (line.height_px || 0), 0) ?? 0;

interface Completed {
  token: number;
  dropped: boolean;
  pixels: RenderPixels;
}

class FakeRenderer {
  tokens = 0;
  calls: Array<{ fontId: string; token: number; spec: RenderSpec }> = [];
  pending = new Map<number, { resolve: (value: Completed) => void; reject: (error: unknown) => void }>();

  nextToken(): number {
    this.tokens += 1;
    return this.tokens;
  }

  render(fontId: string, token: number, spec: RenderSpec): Promise<Completed> {
    this.calls.push({ fontId, token, spec });
    return new Promise<Completed>((resolve, reject) => {
      this.pending.set(token, { resolve, reject });
    });
  }

  complete(token: number, data: RenderPixels, overrides: { dropped?: boolean; token?: number } = {}): void {
    const entry = this.pending.get(token);
    assert.ok(entry, `render token ${token} is pending`);
    this.pending.delete(token);
    entry.resolve({ token: overrides.token ?? token, dropped: overrides.dropped ?? false, pixels: data });
  }

  fail(token: number, error: unknown): void {
    const entry = this.pending.get(token);
    assert.ok(entry, `render token ${token} is pending`);
    this.pending.delete(token);
    entry.reject(error);
  }
}

function baseSpec(text: string): Omit<RenderSpec, "height"> {
  const { height: _height, ...rest } = toRenderSpec({
    text, sizePx: 16, axes: {}, profile: "mono_1bit", width: 60, height: 16,
    role: "candidate", letterSpacingPx: 0, kerning: true, stemFitting: "font_hints_first",
  });
  return rest;
}

function makeJob(
  fake: FakeRenderer,
  key: string,
  paints: PaintOutcome[],
  errors: unknown[],
  overrides: Partial<RenderJob> = {},
): RenderJob {
  const spec = baseSpec(key);
  return {
    key,
    fontId: "font-a",
    estimate: 16,
    cap: 4096,
    specForHeight: (height) => ({ ...spec, height }),
    contentHeight,
    debounceMs: 0,
    immediate: true,
    nextToken: () => fake.nextToken(),
    render: (fontId, token, renderSpec) => fake.render(fontId, token, renderSpec),
    onPaint: (outcome) => { paints.push(outcome); },
    onError: (error) => { errors.push(error); },
    ...overrides,
  };
}

function keyFor(session: number, fontId: string, extra: unknown = null, text = "Ag"): string {
  return buildRequestKey({
    session,
    fontId,
    mode: "normal",
    zoom: 1,
    width: 60,
    extra,
    spec: { ...baseSpec(text), height: 16 },
  });
}

test("request identity covers session, font, mode, geometry and spec", () => {
  const reference = keyFor(1, "font-a");
  assert.equal(keyFor(1, "font-a"), reference);
  assert.notEqual(keyFor(2, "font-a"), reference, "renderer session is part of the key");
  assert.notEqual(keyFor(1, "font-b"), reference, "font id is part of the key");
  assert.notEqual(
    buildRequestKey({ session: 1, fontId: "font-a", mode: "exact", zoom: 1, width: 60, extra: null, spec: { ...baseSpec("Ag"), height: 16 } }),
    reference,
    "display mode is part of the key",
  );
  assert.notEqual(keyFor(1, "font-a", { displayW: 61.5 }), reference, "measured geometry is part of the key");
  assert.notEqual(keyFor(1, "font-a", null, "Agave"), reference, "specimen text is part of the key");
});

test("two passes resolve the full layout height before painting", async () => {
  const fake = new FakeRenderer();
  const paints: PaintOutcome[] = [];
  const errors: unknown[] = [];
  const scheduler = new RenderScheduler();
  scheduler.request(makeJob(fake, "a", paints, errors));
  assert.equal(fake.calls.length, 1);
  assert.equal(fake.calls[0]?.spec.height, 16);
  fake.complete(fake.calls[0]!.token, pixels(60, 16, [40]));
  await flush();
  assert.equal(fake.calls.length, 2, "layout taller than the estimate triggers a second pass");
  assert.equal(fake.calls[1]?.spec.height, 40);
  fake.complete(fake.calls[1]!.token, pixels(60, 40, [40]));
  await flush();
  assert.equal(paints.length, 1);
  assert.deepEqual([paints[0]?.fullHeight, paints[0]?.shown, paints[0]?.truncated], [40, 40, false]);
  assert.deepEqual(errors, []);
});

test("one pass paints when the layout fits; overflow reports instead of clipping", async () => {
  const fake = new FakeRenderer();
  const paints: PaintOutcome[] = [];
  const errors: unknown[] = [];
  const scheduler = new RenderScheduler();
  scheduler.request(makeJob(fake, "a", paints, errors, { estimate: 32, cap: 100 }));
  fake.complete(fake.calls[0]!.token, pixels(60, 32, [20]));
  await flush();
  assert.equal(fake.calls.length, 1, "fitting layout needs no second pass");
  assert.equal(paints.length, 1);
  assert.deepEqual([paints[0]?.fullHeight, paints[0]?.shown, paints[0]?.truncated], [20, 20, false]);

  const tallPaints: PaintOutcome[] = [];
  scheduler.request(makeJob(fake, "b", tallPaints, errors, { estimate: 32, cap: 100 }));
  fake.complete(fake.calls[1]!.token, pixels(60, 32, [5000]));
  await flush();
  assert.equal(fake.calls[2]?.spec.height, 100, "second pass requests the capped height");
  fake.complete(fake.calls[2]!.token, pixels(60, 100, [5000]));
  await flush();
  assert.equal(tallPaints.length, 1);
  assert.deepEqual([tallPaints[0]?.fullHeight, tallPaints[0]?.shown, tallPaints[0]?.truncated], [5000, 100, true]);
});

test("identical keys paint once; re-requests while disabled paint again", async () => {
  const fake = new FakeRenderer();
  const paints: PaintOutcome[] = [];
  const errors: unknown[] = [];
  const scheduler = new RenderScheduler();
  const job = makeJob(fake, "a", paints, errors);
  scheduler.request(job);
  scheduler.request({ ...job });
  assert.equal(fake.calls.length, 1, "duplicate key while running starts no second render");
  fake.complete(fake.calls[0]!.token, pixels(60, 16, [10]));
  await flush();
  assert.equal(paints.length, 1);
  scheduler.request({ ...job });
  assert.equal(fake.calls.length, 1, "painted key does not re-render");

  scheduler.cancel();
  scheduler.request({ ...job });
  assert.equal(fake.calls.length, 2, "disabling clears the painted identity");
  fake.complete(fake.calls[1]!.token, pixels(60, 16, [10]));
  await flush();
  assert.equal(paints.length, 2);
});

test("A -> B -> A with debounce paints only the final specimen", async () => {
  const fake = new FakeRenderer();
  const paints: PaintOutcome[] = [];
  const errors: unknown[] = [];
  const scheduler = new RenderScheduler();
  scheduler.request(makeJob(fake, "a", paints, errors, { debounceMs: 20, immediate: false }));
  scheduler.request(makeJob(fake, "b", paints, errors, { debounceMs: 20, immediate: false }));
  scheduler.request(makeJob(fake, "a", paints, errors, { debounceMs: 20, immediate: false }));
  assert.equal(fake.calls.length, 0, "nothing renders before the debounce expires");
  await sleep(60);
  assert.equal(fake.calls.length, 1);
  assert.equal(fake.calls[0]?.spec.text, "a");
  fake.complete(fake.calls[0]!.token, pixels(60, 16, [10]));
  await flush();
  assert.equal(paints.length, 1);
  assert.deepEqual(errors, []);
});

test("a same-key rerender while debounced preserves the debounce", async () => {
  const fake = new FakeRenderer();
  const paints: PaintOutcome[] = [];
  const errors: unknown[] = [];
  const scheduler = new RenderScheduler();
  // A long debounce with repeated identical requests: none may fire early.
  scheduler.request(makeJob(fake, "a", paints, errors, { debounceMs: 5000, immediate: false }));
  for (let i = 0; i < 4; i += 1) {
    scheduler.request(makeJob(fake, "a", paints, errors, { debounceMs: 5000, immediate: true }));
  }
  await sleep(100);
  assert.equal(fake.calls.length, 0, "rerenders must not bypass the pending debounce");
  scheduler.cancel();
  // The scheduler stays functional: an immediate request renders at once.
  scheduler.request(makeJob(fake, "a", paints, errors));
  assert.equal(fake.calls.length, 1);
  fake.complete(fake.calls[0]!.token, pixels(60, 16, [10]));
  await flush();
  assert.equal(paints.length, 1);
  assert.deepEqual(errors, []);
});

test("a newer immediate request invalidates a pending debounce", async () => {
  const fake = new FakeRenderer();
  const paints: PaintOutcome[] = [];
  const errors: unknown[] = [];
  const scheduler = new RenderScheduler();
  scheduler.request(makeJob(fake, "a", paints, errors, { debounceMs: 40, immediate: false }));
  await sleep(5);
  scheduler.request(makeJob(fake, "b", paints, errors));
  await sleep(60);
  assert.equal(fake.calls.length, 1, "the stale debounced request never renders");
  assert.equal(fake.calls[0]?.spec.text, "b");
  fake.complete(fake.calls[0]!.token, pixels(60, 16, [10]));
  await flush();
  assert.equal(paints.length, 1);
});

test("out-of-order completions keep only the latest result", async () => {
  const fake = new FakeRenderer();
  const paints: PaintOutcome[] = [];
  const errors: unknown[] = [];
  const scheduler = new RenderScheduler();
  scheduler.request(makeJob(fake, "a", paints, errors));
  scheduler.request(makeJob(fake, "b", paints, errors));
  assert.equal(fake.calls.length, 2);
  fake.complete(fake.calls[1]!.token, pixels(60, 16, [12]));
  await flush();
  assert.equal(paints.length, 1);
  fake.complete(fake.calls[0]!.token, pixels(60, 16, [11]));
  await flush();
  assert.equal(paints.length, 1, "the superseded completion is dropped");
  assert.equal(paints[0]?.fullHeight, 12);
  assert.deepEqual(errors, []);
});

test("a superseded second pass never paints", async () => {
  const fake = new FakeRenderer();
  const paints: PaintOutcome[] = [];
  const errors: unknown[] = [];
  const scheduler = new RenderScheduler();
  scheduler.request(makeJob(fake, "a", paints, errors));
  fake.complete(fake.calls[0]!.token, pixels(60, 16, [40]));
  await flush();
  assert.equal(fake.calls.length, 2, "second pass for A is in flight");
  scheduler.request(makeJob(fake, "b", paints, errors));
  fake.complete(fake.calls[1]!.token, pixels(60, 40, [40]));
  await flush();
  assert.equal(paints.length, 0, "A's second pass is dropped after B supersedes it");
  fake.complete(fake.calls[2]!.token, pixels(60, 16, [9]));
  await flush();
  assert.equal(paints.length, 1);
});

test("recovery with identical inputs renders again after a failure", async () => {
  const fake = new FakeRenderer();
  const paints: PaintOutcome[] = [];
  const errors: unknown[] = [];
  const scheduler = new RenderScheduler();
  scheduler.request(makeJob(fake, "a", paints, errors));
  fake.complete(fake.calls[0]!.token, pixels(60, 16, [10]));
  await flush();
  assert.equal(paints.length, 1);
  scheduler.request(makeJob(fake, "b", paints, errors));
  fake.fail(fake.calls[1]!.token, new Error("B failed"));
  await flush();
  assert.equal(errors.length, 1);
  scheduler.request(makeJob(fake, "a", paints, errors));
  assert.equal(fake.calls.length, 3, "the failed key forgot the painted identity");
  fake.complete(fake.calls[2]!.token, pixels(60, 16, [10]));
  await flush();
  assert.equal(paints.length, 2);
});

test("stale failures stay silent; current failures surface once", async () => {
  const fake = new FakeRenderer();
  const paints: PaintOutcome[] = [];
  const errors: unknown[] = [];
  const scheduler = new RenderScheduler();
  scheduler.request(makeJob(fake, "a", paints, errors));
  scheduler.request(makeJob(fake, "b", paints, errors));
  fake.fail(fake.calls[0]!.token, new Error("A failed"));
  await flush();
  assert.deepEqual(errors, [], "the superseded error is swallowed");
  fake.fail(fake.calls[1]!.token, new Error("B failed"));
  await flush();
  assert.equal(errors.length, 1);
  assert.match(String(errors[0]), /B failed/);
  assert.deepEqual(paints, []);
});

test("worker-flagged drops and token mismatches never paint", async () => {
  const fake = new FakeRenderer();
  const paints: PaintOutcome[] = [];
  const errors: unknown[] = [];
  const scheduler = new RenderScheduler();
  scheduler.request(makeJob(fake, "a", paints, errors));
  fake.complete(fake.calls[0]!.token, pixels(60, 16, [10]), { dropped: true });
  await flush();
  assert.deepEqual(paints, []);
  scheduler.request(makeJob(fake, "b", paints, errors));
  fake.complete(fake.calls[1]!.token, pixels(60, 16, [10]), { token: 999 });
  await flush();
  assert.deepEqual(paints, []);
  assert.deepEqual(errors, []);
});

test("distinct consumers of one font stay independent", async () => {
  const fake = new FakeRenderer();
  const paintsA: PaintOutcome[] = [];
  const paintsB: PaintOutcome[] = [];
  const errors: unknown[] = [];
  const first = new RenderScheduler();
  const second = new RenderScheduler();
  first.request(makeJob(fake, "a", paintsA, errors));
  second.request(makeJob(fake, "a", paintsB, errors));
  assert.equal(fake.calls.length, 2, "each consumer issues its own render");
  fake.complete(fake.calls[1]!.token, pixels(60, 16, [7]));
  await flush();
  assert.equal(paintsB.length, 1);
  assert.equal(paintsA.length, 0);
  fake.complete(fake.calls[0]!.token, pixels(60, 16, [8]));
  await flush();
  assert.equal(paintsA.length, 1);
});
