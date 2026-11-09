// Boundary and malformed-input coverage for the owner-held palette edits:
// every conjunct of the level/curve validators and both inclusive edges of
// the numeric ranges. Each case pins behavior the concurrent suites do not
// exercise (0/255 values, end indexes, 120-char names, single-defect
// replacement curves).
import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import { closeDomainForTests, resetDomainForTests } from "../../src/app/domain/node-backend.ts";
import { callDomain } from "../../src/app/domain/runtime.ts";
import { createPalette, listPalettes, updatePalette } from "../../src/app/palettes/repository.ts";
import { curveLevels, linearCurve } from "../../src/app/features/grayscale/response-curve.ts";
import type { GrayCurve } from "../../src/app/features/grayscale/response-curve.ts";

beforeEach(async () => {
  await resetDomainForTests();
});

after(async () => {
  await closeDomainForTests();
});

test("level values accept both inclusive 8-bit edges", async () => {
  const id = await createPalette();
  await updatePalette(id, { kind: "setLevel", index: 1, value: 0, depth: 4 });
  await updatePalette(id, { kind: "setLevel", index: 2, value: 255, depth: 4 });
  const row = (await listPalettes()).find((preset) => preset.id === id)!;
  assert.equal(curveLevels(row.curve)[1], 0);
});

test("level indexes accept both ends of the depth range", async () => {
  const id = await createPalette();
  await updatePalette(id, { kind: "setLevel", index: 0, value: 250, depth: 4 });
  await updatePalette(id, { kind: "setLevel", index: 3, value: 5, depth: 4 });
  const row = (await listPalettes()).find((preset) => preset.id === id)!;
  assert.equal(curveLevels(row.curve)[0], 250);
  assert.equal(curveLevels(row.curve)[3], 5);
});

test("a 120-character name is the longest accepted rename", async () => {
  const id = await createPalette();
  const name = "n".repeat(120);
  await updatePalette(id, { kind: "rename", name });
  assert.equal((await listPalettes()).find((preset) => preset.id === id)!.name, name);
});

test("replacement rejects one out-of-range value without touching state", async () => {
  const id = await createPalette();
  const before = (await listPalettes()).find((preset) => preset.id === id)!;
  const badValues: GrayCurve[] = [
    linearCurve(4).map((level, i) => (i === 1 ? { ...level, value: 300 } : level)),
    linearCurve(4).map((level, i) => (i === 2 ? { ...level, slope: Number.POSITIVE_INFINITY } : level)),
  ];
  for (const curve of badValues) {
    await assert.rejects(
      updatePalette(id, { kind: "replace", curve, expectedRevision: before.revision }),
      /Invalid palette preset/,
    );
  }
  assert.deepEqual(await listPalettes().then((rows) => rows.find((preset) => preset.id === id)), before);
});

test("replacement rejects a single unpinned end without touching state", async () => {
  const id = await createPalette();
  const before = (await listPalettes()).find((preset) => preset.id === id)!;
  const firstUnpinned = linearCurve(4).map((level, i) => (i === 0 ? { ...level, pinned: false } : level));
  const lastLoose = linearCurve(4).map((level, i) => (i === 3 ? { ...level, pinned: false } : level));
  for (const curve of [firstUnpinned, lastLoose]) {
    await assert.rejects(
      updatePalette(id, { kind: "replace", curve, expectedRevision: before.revision }),
      /Invalid palette preset/,
    );
  }
  assert.deepEqual(await listPalettes().then((rows) => rows.find((preset) => preset.id === id)), before);
});

test("replacement rejects null entries as invalid presets", async () => {
  const id = await createPalette();
  const before = (await listPalettes()).find((preset) => preset.id === id)!;
  const firstNull = linearCurve(4).map((level, i) => (i === 0 ? (null as never) : level));
  const lastNull = linearCurve(4).map((level, i) => (i === 3 ? (null as never) : level));
  for (const curve of [firstNull, lastNull]) {
    await assert.rejects(
      updatePalette(id, { kind: "replace", curve, expectedRevision: before.revision }),
      /Invalid palette preset/,
    );
  }
  assert.deepEqual(await listPalettes().then((rows) => rows.find((preset) => preset.id === id)), before);
});

test("malformed edits and unknown kinds fail without touching state", async () => {
  const id = await createPalette();
  const before = (await listPalettes()).find((preset) => preset.id === id)!;
  for (const edit of [null, undefined, 42, "rename", [], { kind: 7 }, {}]) {
    await assert.rejects(
      callDomain("updatePalette", [id, edit]),
      (error: unknown) => (error as { code?: unknown }).code === "invalid-input",
    );
  }
  await assert.rejects(callDomain("updatePalette", [id, { kind: "recolor" }]), /Unknown palette edit/);
  assert.deepEqual(await listPalettes().then((rows) => rows.find((preset) => preset.id === id)), before);
});

test("level guards reject non-integer depth and out-of-range indexes", async () => {
  const id = await createPalette();
  const before = (await listPalettes()).find((preset) => preset.id === id)!;
  for (const depth of ["4", 4.5, Number.NaN, undefined]) {
    await assert.rejects(
      callDomain("updatePalette", [id, { kind: "setLevel", index: 1, value: 10, depth }]),
      /integer expected depth/,
    );
    await assert.rejects(
      callDomain("updatePalette", [id, { kind: "pinLevel", index: 1, depth }]),
      /integer expected depth/,
    );
  }
  for (const index of [-1, 4, 1.5, "1", Number.NaN]) {
    await assert.rejects(callDomain("updatePalette", [id, { kind: "pinLevel", index, depth: 4 }]), /index/);
    await assert.rejects(callDomain("updatePalette", [id, { kind: "unpinLevel", index, depth: 4 }]), /index/);
  }
  for (const value of ["10", Number.NaN, Number.POSITIVE_INFINITY, -1, 256]) {
    await assert.rejects(callDomain("updatePalette", [id, { kind: "setLevel", index: 1, value, depth: 4 }]), /value/);
  }
  await assert.rejects(callDomain("updatePalette", [id, { kind: "rename", name: 7 }]), /non-empty text/);
  for (const count of [3, 0, "8", Number.NaN]) {
    await assert.rejects(callDomain("updatePalette", [id, { kind: "resize", count }]), /depths must be/);
  }
  await assert.rejects(
    callDomain("updatePalette", [id, { kind: "replace", curve: linearCurve(4), expectedRevision: "1" }]),
    /integer expected revision/,
  );
  assert.deepEqual(await listPalettes().then((rows) => rows.find((preset) => preset.id === id)), before);
});

test("replacement rejects non-array curves with an invalid-input error", async () => {
  const id = await createPalette();
  const before = (await listPalettes()).find((preset) => preset.id === id)!;
  for (const curve of [undefined, null, {}, "invalid"]) {
    await assert.rejects(
      callDomain("updatePalette", [id, { kind: "replace", curve, expectedRevision: before.revision }]),
      (error: unknown) => (error as { code?: unknown }).code === "invalid-input",
    );
  }
  assert.deepEqual(await listPalettes().then((rows) => rows.find((preset) => preset.id === id)), before);
});
