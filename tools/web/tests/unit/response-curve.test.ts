import assert from "node:assert/strict";
import test from "node:test";
import {
  curveLevels, editCurveLevel, linearCurve, pinAllCurveLevels,
  pinCurveLevel, resizeCurve, unpinCurveLevel,
} from "../../src/app/features/grayscale/response-curve.ts";

test("every depth starts with only paper and ink handles and an exact linear ramp", () => {
  for (const count of [2, 4, 8, 16]) {
    const curve = linearCurve(count);
    assert.deepEqual(curveLevels(curve), Array.from({ length: count }, (_, i) => Math.round(255 * (1 - i / (count - 1)))));
    assert.deepEqual(curve.flatMap((level, i) => level.pinned ? [i] : []), [0, count - 1]);
  }
});

test("curved response and derivatives match independently captured SciPy PCHIP", () => {
  let curve = linearCurve(16);
  for (const [i, gray] of [[0, 240], [15, 12], [4, 200], [10, 60]] as const) curve = editCurveLevel(curve, i, gray);
  // scipy.interpolate.PchipInterpolator([0,4/15,10/15,1],[240,200,60,12]),
  // sampled at i/15; derivative() evaluated independently at the same inputs.
  const expected = [240, 233.6818181818182, 224.48484848484847, 213.04545454545456, 200,
    182.025694714694, 157.55293015772781, 129.84784236843842, 102.1765673861627,
    77.80524125023761, 60, 46.94778057287193, 35.043525871753616, 24.865380884199386, 16.99149059776343, 12];
  const slopes = [-70, -117.95454545454545, -156.36363636363637, -185.22727272727275, -204.54545454545456,
    -326.5183639153836, -399.4992326952589, -423.4880608850806, -398.48484848484856,
    -324.48959549456276, -201.5023019142234, -188.61891843073334, -167.06336013392954,
    -136.8356270238121, -97.93571910038102, -50.36363636363626];
  curve.forEach((level, i) => {
    assert.ok(Math.abs(level.value - expected[i]!) < 1e-10, `gray at ${i}`);
    assert.ok(Math.abs(level.slope - slopes[i]!) < 1e-10, `slope at ${i}`);
  });
});

test("pinning preserves the entire curved response, including unrounded values and slopes", () => {
  const curve = editCurveLevel(linearCurve(16), 6, 200);
  const before = structuredClone(curve);
  const pinned = pinCurveLevel(curve, 9);
  const all = pinAllCurveLevels(curve);
  for (const next of [pinned, all, editCurveLevel(curve, 9, curveLevels(curve)[9]!)]) {
    assert.deepEqual(next.map(({ value, slope }) => [value, slope]), curve.map(({ value, slope }) => [value, slope]));
  }
  assert.deepEqual(curve, before, "source state is immutable");
  assert.equal(pinned[9]?.pinned, true);
  assert.ok(all.every((level) => level.pinned));
});

test("a sparse handle shapes neighboring outputs while pinned values remain exact", () => {
  let curve = editCurveLevel(linearCurve(16), 5, 200);
  curve = pinCurveLevel(curve, 10);
  const before = curveLevels(curve);
  curve = editCurveLevel(curve, 5, 180);
  const after = curveLevels(curve);
  assert.equal(after[5], 180);
  assert.equal(after[0], before[0]);
  assert.equal(after[10], before[10]);
  assert.equal(after[15], before[15]);
  assert.notEqual(after[4], before[4]);
  assert.notEqual(after[6], before[6]);
});

test("pinning all levels allows isolated one-byte adjustments at every depth", () => {
  for (const count of [2, 4, 8, 16]) {
    const curve = pinAllCurveLevels(linearCurve(count));
    const before = curveLevels(curve);
    const index = Math.floor(count / 2);
    const next = before[index]! + 1;
    assert.deepEqual(curveLevels(editCurveLevel(curve, index, next)), before.map((gray, i) => i === index ? next : gray));
  }
});

test("unpinning releases the level to the curve; endpoints and hollow dots cannot be removed", () => {
  const curve = editCurveLevel(linearCurve(16), 6, 200);
  assert.equal(unpinCurveLevel(curve, 0), curve);
  assert.equal(unpinCurveLevel(curve, 15), curve);
  assert.equal(unpinCurveLevel(curve, 7), curve);
  assert.deepEqual(curveLevels(unpinCurveLevel(curve, 6)), curveLevels(linearCurve(16)));
});

test("monotone responses stay bounded, including plateaus and reversed palettes", () => {
  for (const values of [[255, 180, 180, 0], [0, 0, 120, 255], [240, 240, 240, 240], [255, 254, 253, 0]]) {
    let curve = pinAllCurveLevels(linearCurve(4));
    values.forEach((value, i) => { curve = editCurveLevel(curve, i, value); });
    const dense = resizeCurve(curve, 256);
    const direction = Math.sign(values.at(-1)! - values[0]!);
    for (let i = 0; i < dense.length; i += 1) {
      assert.ok(Number.isFinite(dense[i]!.value) && Number.isFinite(dense[i]!.slope));
      assert.ok(dense[i]!.value >= Math.min(...values) - 1e-10 && dense[i]!.value <= Math.max(...values) + 1e-10);
      if (i > 0) assert.ok((dense[i]!.value - dense[i - 1]!.value) * direction >= -1e-10);
    }
  }
});

test("depth changes sample the unrounded response and keep handles within available levels", () => {
  const curve = editCurveLevel(linearCurve(4), 1, 150);
  const before = structuredClone(curve);
  const resized = resizeCurve(curve, 8);
  assert.deepEqual(curveLevels(resized), [255, 207, 163, 125, 89, 56, 26, 0]);
  assert.deepEqual(resized.flatMap((level, i) => level.pinned ? [i] : []), [0, 2, 7]);
  for (const count of [2, 4, 8, 16]) {
    const next = resizeCurve(curve, count);
    assert.equal(next.length, count);
    assert.equal(next[0]?.pinned, true);
    assert.equal(next.at(-1)?.pinned, true);
    assert.equal(curveLevels(next)[0], 255);
    assert.equal(curveLevels(next).at(-1), 0);
  }
  assert.deepEqual(curve, before);
  assert.equal(resizeCurve(curve, 4), curve);
});
