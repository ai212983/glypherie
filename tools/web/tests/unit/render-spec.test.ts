import assert from "node:assert/strict";
import test from "node:test";
import {
  logicalBounds,
  normalizedSpacing,
  toRenderSpec,
} from "../../src/app/renderer/render-spec.ts";
import type { RGBA } from "../../src/app/renderer/renderer-types.ts";

function baseOptions() {
  return { text: "Ag", sizePx: 18, axes: {}, profile: "mono_1bit" as const, width: 360, height: 120 };
}

test("stem fitting is explicit and restricted to candidate monochrome requests", () => {
  const options = { text: "mut", sizePx: 14, axes: {}, width: 100, height: 40, stemFitting: "upstream_mono" as const };
  assert.equal(toRenderSpec({ ...options, role: "candidate", profile: "mono_1bit" }).stem_fitting, "upstream_mono");
  assert.equal(toRenderSpec({ ...options, role: "candidate", profile: "mono_1bit" }).hinting, "auto");
  assert.equal(toRenderSpec({ ...options, stemFitting: undefined, role: "candidate", profile: "mono_1bit" }).hinting, "auto_fallback");
  assert.equal(toRenderSpec({ ...options, stemFitting: "font_hints_first", role: "candidate", profile: "mono_1bit" }).hinting, "auto_fallback");
  for (const role of ["baseline", "reference"] as const) {
    assert.equal(Object.hasOwn(toRenderSpec({ ...options, role, profile: "mono_1bit" }), "stem_fitting"), false);
  }
  assert.equal(Object.hasOwn(toRenderSpec({ ...options, role: "candidate", profile: "gray_3bit" }), "stem_fitting"), false);
  assert.equal(Object.hasOwn(toRenderSpec({ ...options, stemFitting: undefined, role: "candidate", profile: "mono_1bit" }), "stem_fitting"), false);
});

test("maps control state to the exact tools/wasm render request", () => {
  const spec = toRenderSpec({
    text: "Ag", sizePx: 18, axes: { wght: 700 }, profile: "gray_3bit",
    monoThreshold: 200, grayGamma: 2.2, width: 360, height: 120,
  });
  assert.deepEqual(spec, {
    text: "Ag", width: 360, height: 120, size_px: 18, axes: { wght: 700 }, hinting: "auto", output_bits: 3,
    mono_threshold: 200, gray_gamma: 2.2, missing_glyphs: "error", kerning: true, metric_rounding: "subpixel",
    wrap: "word", align: "left", foreground: [36, 40, 43, 255], background: [255, 255, 255, 255],
    letter_spacing_px: 0, renderer: "baseline",
  });
  assert.equal(toRenderSpec({
    text: "Ag", sizePx: 18, axes: {}, profile: "mono_1bit", width: 360, height: 120, letterSpacingPx: 1.5,
  }).letter_spacing_px, 2);
  assert.equal(toRenderSpec({
    text: "Ag", sizePx: 18, axes: {}, profile: "mono_1bit", width: 360, height: 120, letterSpacingPx: -0.5,
  }).letter_spacing_px, -1);
  assert.equal(toRenderSpec({
    text: "Ag", sizePx: 18, axes: {}, profile: "gray_3bit", width: 360, height: 120, letterSpacingPx: -0.5,
  }).letter_spacing_px, -0.5);
  // No spacing-model field is forwarded any more; kerning still forwards.
  assert.equal("spacing_model" in toRenderSpec({
    text: "AV", sizePx: 14, axes: {}, profile: "mono_1bit", width: 360, height: 120,
  }), false);
  assert.equal(toRenderSpec({
    text: "AV", sizePx: 14, axes: {}, profile: "mono_1bit", width: 360, height: 120, kerning: false,
  }).kerning, false);
  // Candidate Gray tracking is whole-pixel like candidate Mono, while
  // baseline Gray (above) keeps its fractional offset.
  assert.equal(toRenderSpec({
    text: "Ag", sizePx: 18, axes: {}, profile: "gray_3bit", width: 360, height: 120,
    letterSpacingPx: -0.5, role: "candidate",
  }).letter_spacing_px, -1);
  assert.equal(toRenderSpec({
    text: "Ag", sizePx: 18, axes: {}, profile: "mono_1bit", width: 360, height: 120, letterSpacingPx: 99,
  }).letter_spacing_px, 4);
  assert.equal(toRenderSpec({
    text: "Ag", sizePx: 18, axes: {}, profile: "mono_1bit", width: 360, height: 120, letterSpacingPx: "bad",
  }).letter_spacing_px, 0);
  const candidate = toRenderSpec({
    text: "Ag", sizePx: 18, axes: { wght: 700 }, profile: "mono_1bit",
    monoThreshold: 200, grayGamma: 2.2, width: 360, height: 120, role: "candidate",
  });
  assert.equal(candidate.renderer, "candidate");
  assert.equal(candidate.output_bits, 1);
  assert.deepEqual([candidate.text, candidate.size_px, candidate.axes],
    [spec.text, spec.size_px, spec.axes]);
  const mono = toRenderSpec({ text: "", sizePx: 16, axes: {}, profile: "mono_1bit", width: 0.4, height: 5000 });
  assert.equal(mono.output_bits, 1);
  assert.equal(mono.width, 1);
  assert.equal(mono.height, 4096);
  assert.equal(mono.text, "");
});

test("tracking stays whole-pixel for candidate and Mono, fractional for baseline Gray", () => {
  assert.equal(normalizedSpacing(1.5, "mono_1bit", "baseline"), 2);
  assert.equal(normalizedSpacing(-0.5, "gray_3bit", "baseline"), -0.5);
  assert.equal(normalizedSpacing(-0.5, "gray_3bit", "candidate"), -1);
  assert.equal(normalizedSpacing("bad", "mono_1bit"), 0);
  assert.equal(normalizedSpacing(99, "mono_1bit"), 4);
  assert.equal(normalizedSpacing(undefined, "gray_3bit"), 0);
});

test("omitted palette keeps the established default ink/paper render", () => {
  const spec = toRenderSpec(baseOptions());
  assert.deepEqual(spec.foreground, [36, 40, 43, 255]);
  assert.deepEqual(spec.background, [255, 255, 255, 255]);
  assert.equal("palette" in spec, false);
});

test("a full mono palette passes through verbatim with entry 0 as background", () => {
  const palette: RGBA[] = [[10, 20, 30, 40], [200, 30, 30, 255]];
  const spec = toRenderSpec({ ...baseOptions(), palette });
  assert.deepEqual(spec.palette, [[10, 20, 30, 40], [200, 30, 30, 255]]);
  assert.deepEqual(spec.background, [10, 20, 30, 40]);
  assert.deepEqual(spec.foreground, [36, 40, 43, 255]);
});

test("a full gray palette passes through all eight levels", () => {
  const palette: RGBA[] = Array.from({ length: 8 }, (_, i) => [10 * i, 20 * i, 30 * i, 32 * i] as RGBA);
  const spec = toRenderSpec({ ...baseOptions(), profile: "gray_3bit", palette });
  assert.deepEqual(spec.palette, palette);
  assert.deepEqual(spec.background, [0, 0, 0, 0]);
});

test("the singleton convention is gone: one entry is a length error", () => {
  assert.throws(
    () => toRenderSpec({ ...baseOptions(), palette: [[200, 30, 30, 255]] }),
    /expected exactly 2 entries for profile mono_1bit, got 1/,
  );
});

test("palette length mismatches are rejected per profile", () => {
  assert.throws(() => toRenderSpec({ ...baseOptions(), palette: [] }), /expected exactly 2 entries/);
  assert.throws(
    () => toRenderSpec({ ...baseOptions(), palette: [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]] }),
    /expected exactly 2 entries for profile mono_1bit, got 3/,
  );
  assert.throws(
    () => toRenderSpec({ ...baseOptions(), profile: "gray_3bit", palette: [[1, 2, 3, 4], [5, 6, 7, 8]] }),
    /expected exactly 8 entries for profile gray_3bit, got 2/,
  );
  assert.throws(() => toRenderSpec({ ...baseOptions(), palette: "red" as unknown as RGBA[] }), /expected an array/);
});

test("malformed colors are rejected, including entry 0", () => {
  const bad: unknown[] = [
    [1, 2, 3], [1, 2, 3, 4, 5], "white", null, 42,
    [256, 0, 0, 255], [-1, 0, 0, 255], [0, 0, 0, 1.5], [0, 0, 0, NaN],
    [0, 0, "x", 255], [null, 0, 0, 255], [[0, 0, 0, 0]],
  ];
  for (const entry of bad) {
    assert.throws(
      () => toRenderSpec({ ...baseOptions(), palette: [entry, [200, 30, 30, 255]] as unknown as RGBA[] }),
      /Invalid palette color/,
      `entry 0 ${JSON.stringify(entry)}`,
    );
  }
  assert.throws(() => toRenderSpec({ ...baseOptions(), palette: [[1, 2, 3], [4, 5, 6]] as unknown as RGBA[] }), /Invalid palette color/);
  assert.throws(() => toRenderSpec({ ...baseOptions(), palette: [[300, 0, 0, 0], [0, 0, 0, 0]] }), /Invalid palette color/);
  const grayEntries = Array.from({ length: 8 }, () => [0, 0, 0, 0] as unknown as RGBA);
  grayEntries[5] = [1, 1, 1] as unknown as RGBA;
  assert.throws(
    () => toRenderSpec({ ...baseOptions(), profile: "gray_3bit", palette: grayEntries }),
    /Invalid palette color/,
  );
});

test("entry 0 derives the native background and clones without aliasing", () => {
  const paper: [number, number, number, number] = [10, 20, 30, 40];
  const spec = toRenderSpec({ ...baseOptions(), palette: [paper, [200, 30, 30, 255]] });
  assert.deepEqual(spec.background, [10, 20, 30, 40]);
  paper[0] = 99;
  assert.deepEqual(spec.background, [10, 20, 30, 40]);
  assert.notEqual(spec.background, spec.palette?.[0], "background never aliases entry 0");
});

test("mapping clones palette entries and never aliases inputs", () => {
  const entry: [number, number, number, number] = [200, 30, 30, 255];
  const palette: RGBA[] = [[10, 20, 30, 40], entry];
  const spec = toRenderSpec({ ...baseOptions(), palette });
  assert.notEqual(spec.palette, palette);
  assert.notEqual(spec.palette?.[1], entry);
  entry[0] = 1;
  palette[0] = [9, 9, 9, 9];
  assert.deepEqual(spec.palette, [[10, 20, 30, 40], [200, 30, 30, 255]]);
  const frozen = Object.freeze([[11, 22, 33, 44], [55, 66, 77, 88]]) as unknown as RGBA[];
  assert.deepEqual(toRenderSpec({ ...baseOptions(), palette: frozen }).palette, [[11, 22, 33, 44], [55, 66, 77, 88]]);
});

test("derives shrunken logical bounds for integer magnification", () => {
  assert.equal(logicalBounds(720, 1), 720);
  assert.equal(logicalBounds(721, 2), 361);
  assert.equal(logicalBounds(240, 4), 60);
  assert.equal(logicalBounds(0, 2), 1);
  assert.equal(logicalBounds(9000, 1), 4096);
});
