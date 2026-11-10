// Cross-tab palette race: independent edits from separate facade instances
// must compose through single serialized owner transactions, and stale
// depth/revision edits must fail visibly instead of editing another level.
import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import { closeDomainForTests, resetDomainForTests } from "../../src/app/domain/node-backend.ts";
import { createPalette, listPalettes, updatePalette } from "../../src/app/palettes/repository.ts";
import { MONOCHROME } from "../../src/app/palettes/model.ts";
import { curveLevels, linearCurve } from "../../src/app/domain/output-profiles/curve.ts";

beforeEach(async () => {
  await resetDomainForTests();
});

after(async () => {
  await closeDomainForTests();
});

type PaletteRepository = typeof import("../../src/app/palettes/repository.ts");

async function separateFacades(): Promise<{ a: PaletteRepository; b: PaletteRepository }> {
  // Distinct query specifiers give each simulated tab its own facade module
  // instance. TypeScript cannot resolve query specifiers, so the specifier is
  // built dynamically on purpose; the cast restores the module type.
  const specifier = (tag: string): string => `../../src/app/palettes/repository.ts?facade=${tag}`;
  const a = (await import(specifier("a"))) as PaletteRepository;
  const b = (await import(specifier("b"))) as PaletteRepository;
  return { a, b };
}

async function preset(id: number) {
  const row = (await listPalettes()).find((entry) => entry.id === id);
  assert.ok(row, `palette ${id} exists`);
  return row;
}

test("independent level edits from separate facades compose", async () => {
  const { a, b } = await separateFacades();
  const id = await a.createPalette();
  await Promise.all([
    a.updatePalette(id, { kind: "setLevel", index: 1, value: 140, depth: 4 }),
    b.updatePalette(id, { kind: "setLevel", index: 2, value: 70, depth: 4 }),
  ]);
  assert.deepEqual(curveLevels((await preset(id)).curve), [255, 140, 70, 0]);
});

test("rename and level edits from separate facades compose", async () => {
  const { a, b } = await separateFacades();
  const id = await a.createPalette();
  await Promise.all([
    a.updatePalette(id, { kind: "rename", name: "Warm" }),
    b.updatePalette(id, { kind: "setLevel", index: 1, value: 140, depth: 4 }),
  ]);
  const row = await preset(id);
  assert.equal(row.name, "Warm");
  // editCurveLevel re-fits the response around the pinned handle, so the
  // untouched level moves from 170 to 58 through the shared pure operation.
  assert.deepEqual(curveLevels(row.curve), [255, 140, 58, 0]);
});

test("same-level edits serialize as latest writer wins", async () => {
  const { a, b } = await separateFacades();
  const id = await a.createPalette();
  const before = await preset(id);
  await Promise.all([
    a.updatePalette(id, { kind: "setLevel", index: 1, value: 140, depth: 4 }),
    b.updatePalette(id, { kind: "setLevel", index: 1, value: 150, depth: 4 }),
  ]);
  const row = await preset(id);
  assert.ok([140, 150].includes(curveLevels(row.curve)[1]!), "one serialized write wins");
  assert.equal(row.revision, before.revision + 2);
});

test("a stale depth after a concurrent resize is rejected without editing", async () => {
  const { a, b } = await separateFacades();
  const id = await a.createPalette();
  await a.updatePalette(id, { kind: "resize", count: 8 });
  await assert.rejects(
    b.updatePalette(id, { kind: "setLevel", index: 1, value: 140, depth: 4 }),
    /changed underneath|depth/i,
  );
  const row = await preset(id);
  assert.equal(row.curve.length, 8);
  // The rejected edit left the resized response untouched: same byte levels
  // as a linear 8-level curve (slopes keep resizeCurve's float form).
  assert.deepEqual(curveLevels(row.curve), curveLevels(linearCurve(8)));
});

test("a stale whole-curve replacement is rejected, a fresh one applies", async () => {
  const id = await createPalette();
  const stale = await preset(id);
  await updatePalette(id, { kind: "setLevel", index: 1, value: 140, depth: 4 });
  await assert.rejects(
    updatePalette(id, { kind: "replace", curve: linearCurve(4), expectedRevision: stale.revision }),
    /changed underneath|conflict/i,
  );
  assert.deepEqual(curveLevels((await preset(id)).curve), [255, 140, 58, 0]);
  const live = await preset(id);
  await updatePalette(id, { kind: "replace", curve: linearCurve(4), expectedRevision: live.revision });
  assert.deepEqual(curveLevels((await preset(id)).curve), [255, 170, 85, 0]);
});

test("updating a deleted palette fails without resurrecting it", async () => {
  const { a, b } = await separateFacades();
  const id = await a.createPalette();
  await a.deletePalette(id);
  await assert.rejects(a.updatePalette(id, { kind: "rename", name: "Ghost" }), /deleted/);
  await assert.rejects(b.updatePalette(id, { kind: "setLevel", index: 0, value: 10, depth: 4 }), /deleted/);
  assert.ok(!(await a.listPalettes()).some((entry) => entry.id === id));
});

test("out-of-range edits are rejected without touching state", async () => {
  const id = await createPalette();
  const before = await preset(id);
  await assert.rejects(updatePalette(id, { kind: "setLevel", index: -1, value: 10, depth: 4 }), /index/i);
  await assert.rejects(updatePalette(id, { kind: "setLevel", index: 4, value: 10, depth: 4 }), /index/i);
  await assert.rejects(updatePalette(id, { kind: "setLevel", index: 1, value: Number.NaN, depth: 4 }), /value/i);
  await assert.rejects(updatePalette(id, { kind: "setLevel", index: 1, value: 300, depth: 4 }), /value/i);
  await assert.rejects(updatePalette(id, { kind: "setLevel", index: 1, value: -1, depth: 4 }), /value/i);
  await assert.rejects(updatePalette(id, { kind: "resize", count: 3 }), /depth|count|Invalid/i);
  await assert.rejects(updatePalette(id, { kind: "rename", name: "" }), /non-empty text/);
  await assert.rejects(updatePalette(id, { kind: "rename", name: "x".repeat(121) }), /non-empty text/);
  await assert.rejects(updatePalette(id, { kind: "pinLevel", index: 9, depth: 4 }), /index|changed underneath/i);
  assert.deepEqual(await preset(id), before);
});

test("Monochrome stays read-only for every edit kind", async () => {
  const live = (await listPalettes()).find((entry) => entry.id === MONOCHROME.id);
  assert.ok(live);
  await assert.rejects(updatePalette(0, { kind: "rename", name: "Changed" }), /read-only/);
  await assert.rejects(updatePalette(0, { kind: "setLevel", index: 1, value: 10, depth: 2 }), /read-only/);
  await assert.rejects(updatePalette(0, { kind: "pinLevel", index: 1, depth: 2 }), /read-only/);
  await assert.rejects(updatePalette(0, { kind: "unpinLevel", index: 1, depth: 2 }), /read-only/);
  await assert.rejects(updatePalette(0, { kind: "resize", count: 4 }), /read-only/);
  await assert.rejects(
    updatePalette(0, { kind: "replace", curve: linearCurve(2), expectedRevision: live.revision }),
    /read-only/,
  );
});
