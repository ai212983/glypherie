import assert from "node:assert/strict";
import test from "node:test";
import {
  createFixtureRenderer,
  type FixtureScenario,
} from "../../src/app/renderer/fixture-renderer.ts";
import type { RenderPixels } from "../../src/app/renderer/client.ts";
import type { RenderSpec } from "../../src/app/renderer/renderer-types.ts";

function spec({
  text = "A",
  width = 12,
  height = 2,
  size_px = 10,
  axes = {},
  hinting = "auto",
  output_bits = 1,
  mono_threshold = 128,
  gray_gamma = 1,
  missing_glyphs = "error",
  kerning = true,
  metric_rounding = "subpixel",
  wrap = "clip",
  align = "left",
  foreground = [36, 40, 43, 255],
  background = [255, 255, 255, 255],
  palette = undefined,
  letter_spacing_px = 0,
}: Partial<RenderSpec> = {}): RenderSpec {
  return {
    text,
    width,
    height,
    size_px,
    axes,
    hinting,
    output_bits,
    mono_threshold,
    gray_gamma,
    missing_glyphs,
    kerning,
    metric_rounding,
    wrap,
    align,
    foreground,
    background,
    letter_spacing_px,
    ...(palette === undefined ? {} : { palette }),
  };
}

function at(
  pixels: RenderPixels,
  x: number,
  y: number,
): [number, number, number, number] {
  const view = new Uint8Array(pixels.pixels);
  const offset = (y * pixels.width + x) * 4;
  const r = view[offset];
  const g = view[offset + 1];
  const b = view[offset + 2];
  const a = view[offset + 3];
  if (r === undefined || g === undefined || b === undefined || a === undefined) {
    throw new Error(`pixel out of range at (${x}, ${y})`);
  }
  return [r, g, b, a];
}

const WHITE: [number, number, number, number] = [255, 255, 255, 255];
const INK: [number, number, number, number] = [36, 40, 43, 255];

test("equal-length texts produce identical synthetic bands", async () => {
  const renderer = createFixtureRenderer({ latencyMs: 0 });
  const first = await renderer.render("font", 1, spec({ text: "A" }));
  const second = await renderer.render("font", 2, spec({ text: "Z" }));
  assert.deepEqual(
    new Uint8Array(second.pixels.pixels),
    new Uint8Array(first.pixels.pixels),
  );
  renderer.terminate();
});

test("blank text paints only the background and reports no lines", async () => {
  const renderer = createFixtureRenderer({ latencyMs: 0 });
  const result = await renderer.render(
    "font",
    1,
    spec({ text: "", width: 6, height: 2 }),
  );
  assert.equal(result.pixels.width, 6);
  assert.equal(result.pixels.height, 2);
  assert.deepEqual(
    new Uint8Array(result.pixels.pixels),
    new Uint8Array(48).fill(255),
  );
  assert.deepEqual(result.pixels.layout, {
    lines: [],
    missing_codepoints: [],
  });
  renderer.terminate();
});

test("level zero rows leave the background untouched", async () => {
  const renderer = createFixtureRenderer({ latencyMs: 0 });
  const result = await renderer.render(
    "font",
    1,
    spec({ width: 5, height: 1 }),
  );
  assert.deepEqual(
    new Uint8Array(result.pixels.pixels),
    new Uint8Array(20).fill(255),
  );
  assert.deepEqual(result.pixels.layout?.lines, [{ height_px: 24 }]);
  renderer.terminate();
});

test("second band row paints the default foreground", async () => {
  const renderer = createFixtureRenderer({ latencyMs: 0 });
  const result = await renderer.render("font", 1, spec());
  assert.deepEqual(at(result.pixels, 0, 0), WHITE);
  assert.deepEqual(at(result.pixels, 11, 0), WHITE);
  assert.deepEqual(at(result.pixels, 3, 1), WHITE);
  assert.deepEqual(at(result.pixels, 4, 1), INK);
  assert.deepEqual(at(result.pixels, 7, 1), INK);
  assert.deepEqual(at(result.pixels, 8, 1), WHITE);
  assert.deepEqual(result.pixels.layout?.missing_codepoints, []);
  renderer.terminate();
});

test("explicit palette entries paint verbatim", async () => {
  const renderer = createFixtureRenderer({ latencyMs: 0 });
  const result = await renderer.render(
    "font",
    1,
    spec({ palette: [[0, 0, 0, 255], [255, 0, 0, 255]] }),
  );
  assert.deepEqual(at(result.pixels, 4, 1), [255, 0, 0, 255]);
  assert.deepEqual(at(result.pixels, 0, 0), WHITE);
  renderer.terminate();
});

test("transparent background stays transparent off band", async () => {
  const renderer = createFixtureRenderer({ latencyMs: 0 });
  const result = await renderer.render(
    "font",
    1,
    spec({ background: [0, 0, 0, 0] }),
  );
  assert.deepEqual(at(result.pixels, 0, 0), [0, 0, 0, 0]);
  assert.deepEqual(at(result.pixels, 4, 1), INK);
  renderer.terminate();
});

test("translucent foreground composites over paper", async () => {
  const renderer = createFixtureRenderer({ latencyMs: 0 });
  const result = await renderer.render(
    "font",
    1,
    spec({ foreground: [255, 0, 0, 128] }),
  );
  assert.deepEqual(at(result.pixels, 4, 1), [255, 127, 127, 255]);
  renderer.terminate();
});

test("multiline text reports one layout entry per line", async () => {
  const renderer = createFixtureRenderer({ latencyMs: 0 });
  const result = await renderer.render(
    "font",
    1,
    spec({ text: "A\nB", height: 30 }),
  );
  assert.deepEqual(result.pixels.layout?.lines, [
    { height_px: 24 },
    { height_px: 24 },
  ]);
  assert.deepEqual(result.pixels.layout?.missing_codepoints, []);
  assert.deepEqual(at(result.pixels, 4, 25), INK);
  renderer.terminate();
});

test("ping resolves for every scenario except unavailable", async () => {
  const cases: Array<{ scenario: FixtureScenario; ok: boolean }> = [
    { scenario: "ok", ok: true },
    { scenario: "missing-glyphs", ok: true },
    { scenario: "error", ok: true },
    { scenario: "unavailable", ok: false },
  ];
  for (const { scenario, ok } of cases) {
    const renderer = createFixtureRenderer({ latencyMs: 0, scenario });
    if (ok) {
      assert.deepEqual(await renderer.ping(), { available: true });
    } else {
      await assert.rejects(renderer.ping(), /unavailable/);
    }
    renderer.terminate();
  }
});

test("render resolves except on the error scenario", async () => {
  const failing: Array<FixtureScenario> = ["error"];
  for (const scenario of ["ok", "missing-glyphs", "error", "unavailable"] as const) {
    const renderer = createFixtureRenderer({ latencyMs: 0, scenario });
    if (failing.includes(scenario)) {
      await assert.rejects(
        renderer.render("font", 1, spec()),
        /Fixture render failure/,
      );
    } else {
      const result = await renderer.render("font", 1, spec());
      assert.equal(result.dropped, false);
      assert.equal(result.token, 1);
    }
    renderer.terminate();
  }
});

test("missing-glyphs scenario lists fixed codepoints only for nonempty text", async () => {
  const renderer = createFixtureRenderer({
    latencyMs: 0,
    scenario: "missing-glyphs",
  });
  const full = await renderer.render("font", 1, spec({ text: "A" }));
  assert.deepEqual(full.pixels.layout?.missing_codepoints, [65, 66]);
  const blank = await renderer.render("font", 2, spec({ text: "" }));
  assert.deepEqual(blank.pixels.layout?.missing_codepoints, []);
  renderer.terminate();
});

test("lifecycle observes construction, calls, tokens and termination", async () => {
  const seen: Array<string> = [];
  const calls: Array<{ fontId: string; token: number; text: string }> = [];
  const renderer = createFixtureRenderer({
    latencyMs: 0,
    events: {
      constructed: () => {
        seen.push("constructed");
      },
      terminated: () => {
        seen.push("terminated");
      },
      renderCalled: (call) => {
        calls.push({ fontId: call.fontId, token: call.token, text: call.text });
      },
      loadCalled: (call) => {
        seen.push(`loaded ${call.fontId}`);
      },
    },
  });
  assert.deepEqual(seen, ["constructed"]);
  assert.equal(renderer.nextToken(), 1);
  assert.equal(renderer.nextToken(), 2);
  await renderer.load("font", new ArrayBuffer(0));
  const result = await renderer.render("font", 3, spec({ text: "Hi" }));
  assert.equal(result.token, 3);
  assert.deepEqual(calls, [{ fontId: "font", token: 3, text: "Hi" }]);
  const metadata = await renderer.inspect(new ArrayBuffer(0));
  assert.equal(metadata.names.family, "Fixture");
  await renderer.unload("font");
  assert.deepEqual(await renderer.kerning("font", 16, {}), {
    pairs: [],
    skipped_pairs: 0,
  });
  renderer.terminate();
  assert.deepEqual(seen, ["constructed", "loaded font", "terminated"]);
  await assert.rejects(renderer.render("font", 4, spec()), /Worker terminated/);
  await assert.rejects(renderer.ping(), /Worker terminated/);
});

test("render reports the request identity and colors", async () => {
  let observed: unknown = null;
  const renderer = createFixtureRenderer({
    latencyMs: 0,
    events: {
      renderCalled: (call) => {
        observed = call;
      },
    },
  });
  await renderer.render(
    "fid",
    9,
    spec({ text: "Hi", palette: [[1, 2, 3, 255]] }),
  );
  assert.deepEqual(observed, {
    fontId: "fid",
    token: 9,
    text: "Hi",
    width: 12,
    height: 2,
    foreground: [36, 40, 43, 255],
    background: [255, 255, 255, 255],
    palette: [[1, 2, 3, 255]],
  });
  renderer.terminate();
});

test("untyped omitted colors fall back to request defaults", async () => {
  let observed: unknown = null;
  const renderer = createFixtureRenderer({
    latencyMs: 0,
    events: {
      renderCalled: (call) => {
        observed = {
          foreground: call.foreground,
          background: call.background,
          palette: call.palette,
        };
      },
    },
  });
  const bare = {
    ...spec(),
    foreground: undefined,
    background: undefined,
    output_bits: undefined,
  } as unknown as RenderSpec;
  const result = await renderer.render("font", 1, bare);
  assert.deepEqual(observed, {
    foreground: [36, 40, 43, 255],
    background: [255, 255, 255, 255],
    palette: null,
  });
  assert.deepEqual(at(result.pixels, 4, 1), INK);
  renderer.terminate();
});

test("blank asymmetric background fills every byte verbatim", async () => {
  const renderer = createFixtureRenderer({ latencyMs: 0 });
  const result = await renderer.render(
    "font",
    1,
    spec({ text: "", width: 2, height: 1, background: [10, 20, 30, 40] }),
  );
  assert.deepEqual(
    new Uint8Array(result.pixels.pixels),
    new Uint8Array([10, 20, 30, 40, 10, 20, 30, 40]),
  );
  renderer.terminate();
});

test("two-bit gray renders hand-computed coverage steps", async () => {
  const renderer = createFixtureRenderer({ latencyMs: 0, lineHeight: 8 });
  const result = await renderer.render(
    "font",
    1,
    spec({
      width: 12,
      height: 4,
      output_bits: 2,
      foreground: [0, 0, 0, 255],
    }),
  );
  assert.deepEqual(at(result.pixels, 4, 0), WHITE);
  assert.deepEqual(at(result.pixels, 4, 1), [170, 170, 170, 255]);
  assert.deepEqual(at(result.pixels, 4, 2), [85, 85, 85, 255]);
  assert.deepEqual(at(result.pixels, 4, 3), [0, 0, 0, 255]);
  renderer.terminate();
});

test("mixed newline styles split lines identically", async () => {
  const renderer = createFixtureRenderer({ latencyMs: 0 });
  const result = await renderer.render(
    "font",
    1,
    spec({ text: "A\r\nB\rC\nD", height: 2 }),
  );
  assert.deepEqual(result.pixels.layout?.lines, [
    { height_px: 24 },
    { height_px: 24 },
    { height_px: 24 },
    { height_px: 24 },
  ]);
  assert.deepEqual(at(result.pixels, 4, 1), INK);
  renderer.terminate();
});

test("dimensions ceil fractional inputs and clamp to the valid range", async () => {
  const renderer = createFixtureRenderer({ latencyMs: 0 });
  const fractional = await renderer.render(
    "font",
    1,
    spec({ text: "", width: 11.2, height: 1.5 }),
  );
  assert.equal(fractional.pixels.width, 12);
  assert.equal(fractional.pixels.height, 2);
  assert.deepEqual(
    new Uint8Array(fractional.pixels.pixels),
    new Uint8Array(96).fill(255),
  );
  const tiny = await renderer.render(
    "font",
    2,
    spec({ text: "", width: 0.4, height: 0.4 }),
  );
  assert.equal(tiny.pixels.width, 1);
  assert.equal(tiny.pixels.height, 1);
  assert.deepEqual(new Uint8Array(tiny.pixels.pixels), new Uint8Array(4).fill(255));
  const wide = await renderer.render(
    "font",
    3,
    spec({ text: "", width: 4097, height: 1 }),
  );
  assert.equal(wide.pixels.width, 4096);
  assert.equal(wide.pixels.height, 1);
  assert.deepEqual(at(wide.pixels, 0, 0), WHITE);
  assert.deepEqual(at(wide.pixels, 4095, 0), WHITE);
  const tall = await renderer.render(
    "font",
    4,
    spec({ text: "", width: 1, height: 4097 }),
  );
  assert.equal(tall.pixels.width, 1);
  assert.equal(tall.pixels.height, 4096);
  assert.deepEqual(at(tall.pixels, 0, 0), WHITE);
  assert.deepEqual(at(tall.pixels, 0, 4095), WHITE);
  const zero = await renderer.render(
    "font",
    5,
    spec({ text: "", width: 0, height: 0 }),
  );
  assert.equal(zero.pixels.width, 1);
  assert.equal(zero.pixels.height, 1);
  assert.deepEqual(new Uint8Array(zero.pixels.pixels), new Uint8Array(4).fill(255));
  const negative = await renderer.render(
    "font",
    6,
    spec({ text: "", width: -3, height: -2 }),
  );
  assert.equal(negative.pixels.width, 1);
  assert.equal(negative.pixels.height, 1);
  assert.deepEqual(new Uint8Array(negative.pixels.pixels), new Uint8Array(4).fill(255));
  renderer.terminate();
});

test("custom line height bounds and clips bands", async () => {
  const roomy = createFixtureRenderer({ latencyMs: 0, lineHeight: 4 });
  const painted = await roomy.render("font", 1, spec({ height: 5 }));
  assert.deepEqual(at(painted.pixels, 4, 1), INK);
  assert.deepEqual(at(painted.pixels, 4, 3), WHITE);
  roomy.terminate();
  const stub = createFixtureRenderer({ latencyMs: 0, lineHeight: 1 });
  const blankish = await stub.render("font", 2, spec({ height: 3 }));
  assert.deepEqual(
    new Uint8Array(blankish.pixels.pixels),
    new Uint8Array(144).fill(255),
  );
  stub.terminate();
});

test("size and text length vary ink width", async () => {
  const renderer = createFixtureRenderer({ latencyMs: 0 });
  const small = await renderer.render(
    "font",
    1,
    spec({ width: 30, size_px: 1 }),
  );
  assert.deepEqual(at(small.pixels, 11, 1), INK);
  assert.deepEqual(at(small.pixels, 12, 1), WHITE);
  const large = await renderer.render(
    "font",
    2,
    spec({ width: 30, size_px: 10 }),
  );
  assert.deepEqual(at(large.pixels, 12, 1), INK);
  assert.deepEqual(at(large.pixels, 18, 1), WHITE);
  const long = await renderer.render(
    "font",
    3,
    spec({ width: 30, size_px: 1, text: "ABCDEF" }),
  );
  assert.deepEqual(at(long.pixels, 14, 1), INK);
  assert.deepEqual(at(long.pixels, 15, 1), WHITE);
  const clamped = await renderer.render(
    "font",
    4,
    spec({ width: 30, size_px: 0, text: "AA" }),
  );
  assert.deepEqual(at(clamped.pixels, 12, 1), INK);
  assert.deepEqual(at(clamped.pixels, 13, 1), WHITE);
  renderer.terminate();
});
