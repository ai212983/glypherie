import assert from "node:assert/strict";
import test from "node:test";
import { paletteCoverage, tintCoverage } from "../../src/app/features/grayscale/gray-levels.ts";

function alphaPixels(alphas: number[]): Uint8ClampedArray {
  const rgba = new Uint8ClampedArray(alphas.length * 4);
  alphas.forEach((alpha, index) => {
    // Grayscale mask lives in alpha only; RGB must not affect the result.
    rgba[index * 4] = 10 + index;
    rgba[index * 4 + 1] = 20 + index;
    rgba[index * 4 + 2] = 30 + index;
    rgba[index * 4 + 3] = alpha;
  });
  return rgba;
}

function grayAt(output: Uint8ClampedArray, index: number): number {
  return output[index * 4] ?? -1;
}

test("uneven palette follows actual values rather than index position", () => {
  const output = paletteCoverage(alphaPixels([128]), [255, 200, 50, 0]);
  assert.equal(grayAt(output, 0), 200);
});

test("equal-count palettes map the same coverage to different entries", () => {
  const uneven = paletteCoverage(alphaPixels([128]), [255, 200, 50, 0]);
  const even = paletteCoverage(alphaPixels([128]), [255, 170, 85, 0]);
  assert.equal(grayAt(uneven, 0), 200);
  assert.equal(grayAt(even, 0), 170);
});

test("nonwhite paper and nonblack ink hold at the endpoints", () => {
  const output = paletteCoverage(alphaPixels([0, 128, 255]), [240, 16]);
  assert.equal(grayAt(output, 0), 240);
  assert.equal(grayAt(output, 2), 16);
  // Blending the actual endpoints puts half coverage at 0.437, just below
  // the 0.438 midpoint, so it takes ink; assuming white/black would put it
  // at 0.498 and wrongly keep paper.
  assert.equal(grayAt(output, 1), 16);
});

test("linear-toe levels split low coverage at their midpoint", () => {
  const output = paletteCoverage(alphaPixels([63, 64]), [10, 5, 0]);
  assert.equal(grayAt(output, 0), 10);
  assert.equal(grayAt(output, 1), 5);
});

test("full 256-entry ramp reaches the last index and quantizes interior", () => {
  const ramp = Array.from({ length: 256 }, (_, index) => 255 - index);
  const output = paletteCoverage(alphaPixels([0, 127, 128, 254, 255]), ramp);
  assert.equal(grayAt(output, 0), 255);
  assert.equal(grayAt(output, 1), 188);
  assert.equal(grayAt(output, 2), 187);
  assert.equal(grayAt(output, 3), 13);
  assert.equal(grayAt(output, 4), 0);
});

test("two-level palette splits half coverage at the midpoint", () => {
  const output = paletteCoverage(alphaPixels([0, 127, 128, 255]), [255, 0]);
  assert.equal(grayAt(output, 0), 255);
  assert.equal(grayAt(output, 1), 255);
  assert.equal(grayAt(output, 2), 0);
  assert.equal(grayAt(output, 3), 0);
});

test("three-level palette keeps its middle entry for half coverage", () => {
  const output = paletteCoverage(alphaPixels([0, 128, 255]), [255, 128, 0]);
  assert.equal(grayAt(output, 0), 255);
  assert.equal(grayAt(output, 1), 128);
  assert.equal(grayAt(output, 2), 0);
});

test("duplicate entries resolve deterministically", () => {
  const levels = [255, 200, 200, 0];
  const first = paletteCoverage(alphaPixels([0, 128, 255]), levels);
  const second = paletteCoverage(alphaPixels([0, 128, 255]), levels);
  assert.deepEqual([...first], [...second]);
  assert.equal(grayAt(first, 0), 255);
  assert.equal(grayAt(first, 1), 200);
  assert.equal(grayAt(first, 2), 0);
});

test("nonmonotonic palettes still select the nearest value", () => {
  const output = paletteCoverage(alphaPixels([0, 128, 255]), [255, 0, 200, 0]);
  assert.equal(grayAt(output, 0), 255);
  assert.equal(grayAt(output, 1), 200);
  assert.equal(grayAt(output, 2), 0);
});

test("reversed palettes blend from their own paper toward ink", () => {
  const output = paletteCoverage(alphaPixels([0, 128, 255]), [0, 50, 200, 255]);
  assert.equal(grayAt(output, 0), 0);
  assert.equal(grayAt(output, 1), 200);
  assert.equal(grayAt(output, 2), 255);
});

test("neutral display pair keeps every quantized byte exact", () => {
  const input = new Uint8ClampedArray([255, 255, 255, 255, 170, 170, 170, 255, 85, 85, 85, 255, 0, 0, 0, 255]);
  const output = tintCoverage(input, [255, 255, 255, 255], [0, 0, 0, 255]);
  assert.deepEqual([...output], [...input]);
  assert.deepEqual([...input], [255, 255, 255, 255, 170, 170, 170, 255, 85, 85, 85, 255, 0, 0, 0, 255]);
});

test("warm display pair maps endpoints exactly and blends interior per channel", () => {
  const output = tintCoverage(
    new Uint8ClampedArray([255, 0, 0, 255, 0, 0, 0, 255, 128, 128, 128, 255]),
    [244, 236, 220, 255],
    [26, 24, 21, 255],
  );
  assert.deepEqual([output[0], output[1], output[2], output[3]], [244, 236, 220, 255]);
  assert.deepEqual([output[4], output[5], output[6], output[7]], [26, 24, 21, 255]);
  assert.deepEqual([output[8], output[9], output[10], output[11]], [135, 130, 121, 255]);
});

test("cool inverse pair reverses paper and ink", () => {
  const output = tintCoverage(
    new Uint8ClampedArray([255, 0, 0, 255, 0, 0, 0, 255]),
    [27, 42, 58, 255],
    [232, 240, 248, 255],
  );
  assert.deepEqual([output[0], output[1], output[2], output[3]], [27, 42, 58, 255]);
  assert.deepEqual([output[4], output[5], output[6], output[7]], [232, 240, 248, 255]);
});

test("tint output is opaque and never mutates its input", () => {
  const input = new Uint8ClampedArray([10, 20, 30, 255, 200, 150, 100, 255]);
  const before = [...input];
  const output = tintCoverage(input, [244, 236, 220, 255], [26, 24, 21, 255]);
  assert.deepEqual([...input], before);
  assert.notEqual(output, input);
  assert.equal(output[3], 255);
  assert.equal(output[7], 255);
});

test("output is opaque, exact palette members, inputs untouched", () => {
  const levels = [255, 200, 50, 0];
  const alphas = Array.from({ length: 256 }, (_, alpha) => alpha);
  const rgba = alphaPixels(alphas);
  const rgbaBefore = [...rgba];
  const output = paletteCoverage(rgba, levels);
  assert.ok(output instanceof Uint8ClampedArray);
  assert.equal(output.length, rgba.length);
  assert.deepEqual([...rgba], rgbaBefore);
  assert.deepEqual([...levels], [255, 200, 50, 0]);
  for (let index = 0; index < alphas.length; index += 1) {
    const gray = grayAt(output, index);
    assert.ok(levels.includes(gray), `alpha ${alphas[index]} gave ${gray}`);
    assert.equal(output[index * 4 + 1], gray);
    assert.equal(output[index * 4 + 2], gray);
    assert.equal(output[index * 4 + 3], 255);
  }
});
