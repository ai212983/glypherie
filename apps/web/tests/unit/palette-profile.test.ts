// Shared curve-length profile rule: the single owner and its thin wrappers
// agree on every depth, keeping the established 3-bit gray fallback.
import assert from "node:assert/strict";
import test from "node:test";
import { profileForCurve, profileForCurveLength, type PalettePreset } from "../../src/app/palettes/model.ts";
import { paletteProfile } from "../../src/app/palettes/render.ts";
import { curveProfile } from "../../src/app/domain/variant-plan.ts";
import { directLabelProfile } from "../../src/app/features/screen/direct-label.ts";
import { linearCurve } from "../../src/app/features/grayscale/response-curve.ts";
import { MONOCHROME } from "../../src/app/palettes/model.ts";

function preset(length: number): PalettePreset {
  return { ...MONOCHROME, curve: linearCurve(length) };
}

test("the shared owner maps depths with the gray fallback", () => {
  assert.equal(profileForCurveLength(2), "mono_1bit");
  assert.equal(profileForCurveLength(4), "gray_2bit");
  assert.equal(profileForCurveLength(16), "gray_4bit");
  for (const length of [0, 1, 3, 8, 32, Number.NaN]) {
    assert.equal(profileForCurveLength(length), "gray_3bit");
  }
  assert.equal(profileForCurve(linearCurve(2)), "mono_1bit");
  assert.equal(profileForCurve(linearCurve(8)), "gray_3bit");
});

test("every consumer wrapper agrees with the shared owner", () => {
  for (const length of [2, 4, 8, 16, 3]) {
    const curve = linearCurve(length);
    const expected = profileForCurve(curve);
    assert.equal(paletteProfile(preset(length)), expected);
    assert.equal(curveProfile(curve), expected);
    assert.equal(directLabelProfile(curve), expected);
  }
});
