// Reset-after-edit ordering for the grayscale page: a reset enqueued behind
// this view's own saves applies on the live row, while another tab's
// concurrent edit makes the reset conflict instead of silently overwriting it
// under a freshly read revision.
import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import { closeDomainForTests, resetDomainForTests } from "../../src/app/domain/node-backend.ts";
import { createOrderedPaletteWrites } from "../../src/app/palettes/ordered-writes.ts";
import { createPalette, listPalettes, updatePalette } from "../../src/app/palettes/repository.ts";
import { curveLevels, linearCurve } from "../../src/app/domain/output-profiles/curve.ts";

beforeEach(async () => {
  await resetDomainForTests();
});

after(async () => {
  await closeDomainForTests();
});

type PaletteRepository = typeof import("../../src/app/palettes/repository.ts");

async function separateFacade(tag: string): Promise<PaletteRepository> {
  return (await import(`../../src/app/palettes/repository.ts?facade=${tag}`)) as PaletteRepository;
}

async function preset(id: number) {
  const row = (await listPalettes()).find((entry) => entry.id === id);
  assert.ok(row, `palette ${id} exists`);
  return row;
}

function writes() {
  return createOrderedPaletteWrites({ listPalettes, updatePalette });
}

test("a reset queued behind this view's level edit applies without conflict", async () => {
  const queue = writes();
  const id = await createPalette();
  const renderRevision = (await preset(id)).revision;
  const snapshot = queue.captureRevision(id, renderRevision);
  const edited = queue.edit(id, () => updatePalette(id, { kind: "setLevel", index: 1, value: 140, depth: 4 }));
  const reset = queue.resetCurve(snapshot);
  await edited;
  await reset;
  assert.deepEqual(curveLevels((await preset(id)).curve), [255, 170, 85, 0]);
});

test("a reset queued behind this view's resize uses the live depth", async () => {
  const queue = writes();
  const id = await createPalette();
  const renderRevision = (await preset(id)).revision;
  const snapshot = queue.captureRevision(id, renderRevision);
  const resized = queue.edit(id, () => updatePalette(id, { kind: "resize", count: 8 }));
  const reset = queue.resetCurve(snapshot);
  await resized;
  await reset;
  assert.deepEqual(curveLevels((await preset(id)).curve), curveLevels(linearCurve(8)));
});

test("a completed local edit can reset before the rendered revision catches up", async () => {
  const queue = writes();
  const id = await createPalette();
  const renderRevision = (await preset(id)).revision;
  const snapshot = queue.captureRevision(id, renderRevision);
  await queue.edit(id, () => updatePalette(id, { kind: "setLevel", index: 1, value: 140, depth: 4 }));
  assert.equal(queue.captureRevision(id, renderRevision), snapshot, "a stale rerender keeps its checkpoint");
  await queue.resetCurve(snapshot);
  assert.deepEqual(curveLevels((await preset(id)).curve), [255, 170, 85, 0]);
});

test("a refreshed revision includes completed local edits in its checkpoint", async () => {
  const queue = writes();
  const id = await createPalette();
  queue.captureRevision(id, (await preset(id)).revision);
  await queue.edit(id, () => updatePalette(id, { kind: "setLevel", index: 1, value: 140, depth: 4 }));
  const snapshot = queue.captureRevision(id, (await preset(id)).revision);
  await queue.resetCurve(snapshot);
  assert.deepEqual(curveLevels((await preset(id)).curve), [255, 170, 85, 0]);
});

test("an external resize still conflicts after a completed local edit and stale rerender", async () => {
  const queue = writes();
  const id = await createPalette();
  const revision = (await preset(id)).revision;
  queue.captureRevision(id, revision);
  await queue.edit(id, () => updatePalette(id, { kind: "setLevel", index: 1, value: 140, depth: 4 }));
  await updatePalette(id, { kind: "resize", count: 8 });
  const before = await preset(id);
  await assert.rejects(queue.resetCurve(queue.captureRevision(id, revision)), /changed underneath/);
  assert.deepEqual(await preset(id), before);
});

test("another tab's concurrent edit makes the reset conflict instead of overwriting it", async () => {
  const queue = writes();
  const external = await separateFacade("reset-conflict");
  const id = await createPalette();
  const renderRevision = (await preset(id)).revision;
  const snapshot = queue.captureRevision(id, renderRevision);
  await external.updatePalette(id, { kind: "setLevel", index: 1, value: 140, depth: 4 });
  await assert.rejects(queue.resetCurve(snapshot), /changed underneath/);
  assert.deepEqual(curveLevels((await preset(id)).curve), [255, 140, 58, 0]);
});

test("a reset after deletion fails as deleted without resurrecting the preset", async () => {
  const queue = writes();
  const id = await createPalette();
  const renderRevision = (await preset(id)).revision;
  const snapshot = queue.captureRevision(id, renderRevision);
  await updatePalette(id, { kind: "rename", name: "Transient" });
  const { deletePalette } = await separateFacade("reset-delete");
  await deletePalette(id);
  await assert.rejects(queue.resetCurve(snapshot), /deleted/);
  assert.ok(!(await listPalettes()).some((entry) => entry.id === id));
});

test("a failed preceding write does not break reset accounting", async () => {
  const queue = writes();
  const id = await createPalette();
  const renderRevision = (await preset(id)).revision;
  const snapshot = queue.captureRevision(id, renderRevision);
  const bad = queue.edit(id, () => updatePalette(id, { kind: "setLevel", index: 9, value: 10, depth: 4 }));
  const reset = queue.resetCurve(snapshot);
  await assert.rejects(bad, /index/);
  await reset;
  assert.deepEqual(curveLevels((await preset(id)).curve), [255, 170, 85, 0]);
});

test("edits on another preset do not disturb reset accounting", async () => {
  const queue = writes();
  const id = await createPalette();
  const other = await createPalette();
  const renderRevision = (await preset(id)).revision;
  const snapshot = queue.captureRevision(id, renderRevision);
  const renamed = queue.edit(other, () => updatePalette(other, { kind: "rename", name: "Other" }));
  const reset = queue.resetCurve(snapshot);
  await renamed;
  await reset;
  assert.deepEqual(curveLevels((await preset(id)).curve), [255, 170, 85, 0]);
  assert.equal((await preset(other)).name, "Other");
});
