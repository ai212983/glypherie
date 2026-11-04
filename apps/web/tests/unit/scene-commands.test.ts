// Scene-command contract coverage: the eight scene commands in
// domain/scene-commands.ts against the real in-memory PGlite/TypeGraph store,
// through the same public signatures the worker dispatch uses.

import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import {
  closeDomainForTests,
  resetDomainForTests,
} from "../../src/app/domain/node-backend.ts";
import type { DomainBackend } from "../../src/app/domain/backend.ts";
import {
  addSceneLabel,
  createScene,
  deleteScene,
  getScene,
  listScenes,
  removeSceneLabel,
  restoreSceneSnapshot,
  updateScene,
  updateSceneLabel,
} from "../../src/app/domain/scene-commands.ts";
import type {
  DomainSceneView,
  SceneSnapshotInput,
} from "../../src/app/domain/types.ts";
import { createVariant } from "../../src/app/variants/repository.ts";
import { createPalette, updatePalette } from "../../src/app/palettes/repository.ts";
import { linearCurve } from "../../src/app/features/grayscale/response-curve.ts";
import { saveFont, type FontMetadata } from "../../src/app/fonts/storage.ts";
import { listOutputProfiles } from "../../src/app/domain/service.ts";

let backend: DomainBackend;

beforeEach(async () => {
  backend = await resetDomainForTests();
});

after(async () => {
  await closeDomainForTests();
});

function metadata(): FontMetadata {
  return {
    names: { family: "Fixture" },
    axes: [{ tag: "wght", name: "Weight", min: 100, default: 400, max: 900, hidden: false }],
  };
}

const fontBytes = (seed = 0): ArrayBuffer =>
  Uint8Array.from({ length: 64 }, (_, i) => (i * 7 + seed) % 251).buffer as ArrayBuffer;

async function saveFixture(seed = 0) {
  return saveFont({ bytes: fontBytes(seed), fileName: "fixture.ttf", name: "Fixture", metadata: metadata(), source: "uploaded" });
}

async function monoId(): Promise<string> {
  const profiles = await listOutputProfiles();
  const mono = profiles.find((profile) => profile.name === "Monochrome");
  assert.ok(mono);
  return mono.id;
}

async function styleId(seed = 0): Promise<string> {
  const font = await saveFixture(seed);
  const style = await createVariant(font.id, { name: `Body ${seed}` });
  return style.id;
}

function codeOf(error: unknown): string {
  return (error as { code?: unknown }).code as string;
}

test("scene lifecycle keeps views, order and CAS revisions", async () => {
  const outputId = await monoId();
  const style = await styleId();
  const created = await createScene(backend, { name: "Card", width: 400, height: 300, outputProfileId: outputId });
  assert.equal(created.revision, 1);
  assert.deepEqual(created.placements, []);
  assert.equal(created.outputProfileId, outputId);

  const placed = await addSceneLabel(backend, created.id, { text: "Hello", textStyleId: style, x: 16, y: 12 }, created.revision);
  assert.equal(placed.revision, 2);
  assert.equal(placed.placements[0]?.order, 0);

  const moved = await updateSceneLabel(backend, placed.id, placed.placements[0]!.id, { x: 20, order: 3 }, placed.revision);
  assert.equal(moved.revision, 3);
  assert.equal(moved.placements[0]?.x, 20);

  const second = await addSceneLabel(backend, moved.id, { text: "World", textStyleId: style, x: 0, y: 0 }, moved.revision);
  assert.deepEqual(second.placements.map((placement) => placement.order), [3, 4]);

  const listed = await listScenes(backend);
  assert.equal(listed.length, 1);
  assert.equal(listed[0]?.id, created.id);

  const cleaned = await removeSceneLabel(backend, second.id, second.placements[0]!.id, second.revision);
  assert.equal(cleaned.placements.length, 1);
  assert.equal(cleaned.placements[0]?.text, "World");

  await deleteScene(backend, cleaned.id, cleaned.revision);
  assert.equal(await getScene(backend, cleaned.id), undefined);
  assert.deepEqual(await listScenes(backend), []);
});

test("stale scene revisions conflict and never resurrect", async () => {
  const outputId = await monoId();
  const created = await createScene(backend, { name: "Card", width: 100, height: 100, outputProfileId: outputId });
  await assert.rejects(updateScene(backend, created.id, { name: "Stale" }, created.revision + 1), /changed underneath/);
  await assert.rejects(deleteScene(backend, created.id, created.revision + 1), /changed underneath/);
  const renamed = await updateScene(backend, created.id, { name: "Kept", width: 200 }, created.revision);
  assert.equal(renamed.revision, 2);
  await deleteScene(backend, renamed.id, renamed.revision);
  await assert.rejects(updateScene(backend, renamed.id, { name: "Ghost" }, renamed.revision + 1), /does not exist/);
  await assert.rejects(deleteScene(backend, renamed.id, renamed.revision), /does not exist/);
});

test("scene creation validates every input and leaves no partial scene", async () => {
  const outputId = await monoId();
  await assert.rejects(createScene(backend, { name: "", width: 10, height: 10, outputProfileId: outputId }), /Scene names/);
  await assert.rejects(createScene(backend, { name: "x".repeat(121), width: 10, height: 10, outputProfileId: outputId }), /Scene names/);
  await assert.rejects(createScene(backend, { name: "Bad", width: 0, height: 10, outputProfileId: outputId }), /dimensions/);
  await assert.rejects(createScene(backend, { name: "Bad", width: 10, height: 5000, outputProfileId: outputId }), /dimensions/);
  await assert.rejects(createScene(backend, { name: "Bad", width: 10.5, height: 10, outputProfileId: outputId }), /dimensions/);
  await assert.rejects(
    createScene(backend, { name: "Bad", width: 10, height: 10, outputProfileId: "missing" }),
    /does not exist/,
  );
  await assert.rejects(
    createScene(backend, { name: "Bad", width: 10, height: 10, outputProfileId: outputId, exportCoverage: { presetIds: ["nope" as never], extraRanges: [] } }),
    /Unknown coverage preset/,
  );
  await assert.rejects(
    createScene(backend, undefined as never),
    /needs an input object/,
  );
  assert.deepEqual(await listScenes(backend), []);
});

test("scene patches merge, bump on no-op, and reject without touching state", async () => {
  const outputId = await monoId();
  const created = await createScene(backend, { name: "Card", width: 400, height: 300, outputProfileId: outputId });

  const narrowed = await updateScene(backend, created.id, { width: 200 }, created.revision);
  assert.deepEqual([narrowed.width, narrowed.height, narrowed.revision], [200, 300, 2]);
  const noop = await updateScene(backend, narrowed.id, {}, narrowed.revision);
  assert.equal(noop.revision, 3);
  const explicitUndefined = await updateScene(backend, noop.id, { name: undefined, height: undefined }, noop.revision);
  assert.deepEqual([explicitUndefined.name, explicitUndefined.height, explicitUndefined.revision], ["Card", 300, 4]);

  const before = await getScene(backend, explicitUndefined.id);
  assert.ok(before);
  await assert.rejects(updateScene(backend, before.id, { name: "" }, before.revision), /Scene names/);
  await assert.rejects(updateScene(backend, before.id, { height: 0 }, before.revision), /dimensions/);
  await assert.rejects(
    updateScene(backend, before.id, { exportCoverage: { presetIds: ["nope" as never], extraRanges: [] } }, before.revision),
    /Unknown coverage preset/,
  );
  await assert.rejects(updateScene(backend, before.id, { outputProfileId: "missing" }, before.revision), /does not exist/);
  await assert.rejects(updateScene(backend, "missing-scene", { name: "Ghost" }, 1), /refusing to recreate/);
  await assert.rejects(updateScene(backend, before.id, null as never, before.revision), /need a patch object/);
  await assert.rejects(updateScene(backend, before.id, [] as never, before.revision), /need a patch object/);
  await assert.rejects(
    updateScene(backend, before.id, { name: "Ok" }, Number.NaN),
    /integer expected revision/,
  );
  assert.deepEqual(await getScene(backend, before.id), before);
});

test("scene output swaps replace the default edge", async () => {
  const outputId = await monoId();
  const grayId = await createPalette();
  await updatePalette(grayId, { curve: () => linearCurve(8) });
  const gray = (await listOutputProfiles()).find((profile) => profile.name === `Grayscale ${grayId}`);
  assert.ok(gray);
  const created = await createScene(backend, { name: "Card", width: 100, height: 100, outputProfileId: outputId });
  const swapped = await updateScene(backend, created.id, { outputProfileId: gray.id }, created.revision);
  assert.equal(swapped.outputProfileId, gray.id);
  assert.equal(swapped.revision, 2);
  const back = await updateScene(backend, swapped.id, { outputProfileId: outputId }, swapped.revision);
  assert.equal(back.outputProfileId, outputId);
});

test("label placement validates input and keeps order CAS-guarded", async () => {
  const outputId = await monoId();
  const style = await styleId();
  const created = await createScene(backend, { name: "Card", width: 100, height: 100, outputProfileId: outputId });

  await assert.rejects(
    addSceneLabel(backend, created.id, { text: "x", textStyleId: "missing-style", x: 0, y: 0 }, created.revision),
    /does not exist/,
  );
  await assert.rejects(
    addSceneLabel(backend, created.id, { text: "x", textStyleId: style, x: 1.5, y: 0 }, created.revision),
    /pixel grid/,
  );
  await assert.rejects(
    addSceneLabel(backend, created.id, { text: "x".repeat(8193), textStyleId: style, x: 0, y: 0 }, created.revision),
    /within 8192/,
  );
  await assert.rejects(
    addSceneLabel(backend, created.id, { text: "x", textStyleId: style, x: 0, y: 0 }, created.revision + 1),
    /changed underneath/,
  );
  await assert.rejects(
    addSceneLabel(backend, "missing-scene", { text: "x", textStyleId: style, x: 0, y: 0 }, 1),
    /does not exist/,
  );
  await assert.rejects(
    addSceneLabel(backend, created.id, null as never, created.revision),
    /needs an input object/,
  );
  assert.deepEqual((await getScene(backend, created.id))?.placements, []);

  const placed = await addSceneLabel(backend, created.id, { text: "", textStyleId: style, x: 0, y: -1 }, created.revision);
  assert.equal(placed.placements[0]?.text, "");
  assert.equal(placed.placements[0]?.y, -1);
});

test("label updates cover every field and preserve state on rejection", async () => {
  const outputId = await monoId();
  const first = await styleId(1);
  const second = await styleId(2);
  const created = await createScene(backend, { name: "Card", width: 100, height: 100, outputProfileId: outputId });
  const placed = await addSceneLabel(backend, created.id, { text: "A", textStyleId: first, x: 0, y: 0 }, created.revision);
  const placementId = placed.placements[0]!.id;

  const moved = await updateSceneLabel(
    backend, placed.id, placementId, { text: "B", textStyleId: second, x: -4, y: 7, order: 9 }, placed.revision,
  );
  assert.deepEqual(
    [moved.placements[0]?.text, moved.placements[0]?.textStyleId, moved.placements[0]?.x, moved.placements[0]?.y, moved.placements[0]?.order],
    ["B", second, -4, 7, 9],
  );

  // Single-field moves merge against the stored point.
  const shifted = await updateSceneLabel(backend, moved.id, placementId, { y: 3 }, moved.revision);
  assert.deepEqual([shifted.placements[0]?.x, shifted.placements[0]?.y], [-4, 3]);

  const before = await getScene(backend, shifted.id);
  assert.ok(before);
  await assert.rejects(updateSceneLabel(backend, shifted.id, placementId, { text: "x".repeat(8193) }, shifted.revision), /within 8192/);
  await assert.rejects(updateSceneLabel(backend, shifted.id, placementId, { textStyleId: "missing" }, shifted.revision), /does not exist/);
  await assert.rejects(updateSceneLabel(backend, shifted.id, placementId, { order: 1.5 }, shifted.revision), /stable integer/);
  await assert.rejects(updateSceneLabel(backend, shifted.id, placementId, { order: Number.NaN }, shifted.revision), /stable integer/);
  await assert.rejects(updateSceneLabel(backend, shifted.id, placementId, { x: 0.5 }, shifted.revision), /pixel grid/);
  await assert.rejects(updateSceneLabel(backend, shifted.id, "missing", { x: 1 }, shifted.revision), /does not exist in scene/);
  await assert.rejects(updateSceneLabel(backend, shifted.id, placementId, { x: 1 }, shifted.revision + 1), /changed underneath/);
  await assert.rejects(updateSceneLabel(backend, shifted.id, placementId, null as never, shifted.revision), /need a patch object/);
  await assert.rejects(updateSceneLabel(backend, shifted.id, placementId, { x: 1 }, "2" as never), /integer expected revision/);
  await assert.rejects(removeSceneLabel(backend, shifted.id, placementId, shifted.revision + 1), /changed underneath/);
  assert.deepEqual(await getScene(backend, shifted.id), before);
});

test("placements reject foreign scenes and removal drops orphans", async () => {
  const outputId = await monoId();
  const style = await styleId();
  const left = await createScene(backend, { name: "Left", width: 100, height: 100, outputProfileId: outputId });
  const right = await createScene(backend, { name: "Right", width: 100, height: 100, outputProfileId: outputId });
  const placed = await addSceneLabel(backend, left.id, { text: "A", textStyleId: style, x: 0, y: 0 }, left.revision);
  const placementId = placed.placements[0]!.id;

  await assert.rejects(updateSceneLabel(backend, right.id, placementId, { x: 2 }, right.revision), /does not exist in scene/);
  await assert.rejects(removeSceneLabel(backend, right.id, placementId, right.revision), /does not exist in scene/);
  await assert.rejects(removeSceneLabel(backend, placed.id, "missing", placed.revision), /does not exist in scene/);
  try {
    await updateScene(backend, placed.id, { name: "Nope" }, placed.revision + 1);
    assert.fail("stale scene update must conflict");
  } catch (error) {
    assert.equal(codeOf(error), "conflict");
  }

  const cleaned = await removeSceneLabel(backend, placed.id, placementId, placed.revision);
  assert.deepEqual(cleaned.placements, []);
  await assert.rejects(removeSceneLabel(backend, cleaned.id, placementId, cleaned.revision), /does not exist in scene/);
});

function snapshotOf(view: DomainSceneView): SceneSnapshotInput {
  return {
    name: view.name,
    width: view.width,
    height: view.height,
    deviceId: view.deviceId,
    outputProfileId: view.outputProfileId,
    exportCoverage: view.exportCoverage,
    placements: view.placements.map((placement) => ({
      text: placement.text,
      textStyleId: placement.textStyleId,
      x: placement.x,
      y: placement.y,
      order: placement.order,
    })),
  };
}

function contentOf(view: DomainSceneView): unknown {
  return {
    ...snapshotOf(view),
    placements: snapshotOf(view).placements
      .map((placement) => ({ ...placement }))
      .sort((a, b) => a.order - b.order || a.x - b.x || (a.text < b.text ? -1 : 1)),
  };
}

test("snapshot restore replaces whole content atomically under one revision", async () => {
  const outputId = await monoId();
  const style = await styleId();
  const created = await createScene(backend, { name: "Card", width: 400, height: 300, outputProfileId: outputId });
  const before = await addSceneLabel(backend, created.id, { text: "A", textStyleId: style, x: 1, y: 2 }, created.revision);
  const wanted = snapshotOf(before);

  const changed = await updateSceneLabel(backend, before.id, before.placements[0]!.id, { text: "B", x: 9 }, before.revision);
  assert.notDeepEqual(contentOf(changed), contentOf(before));

  const restored = await restoreSceneSnapshot(backend, changed.id, changed.revision, wanted);
  assert.deepEqual(contentOf(restored), contentOf(before));
  assert.equal(restored.revision, changed.revision + 1);

  // Scalars restore through the same command.
  const renamed = snapshotOf(restored);
  renamed.name = "Renamed";
  renamed.width = 200;
  const renamedView = await restoreSceneSnapshot(backend, restored.id, restored.revision, renamed);
  assert.equal(renamedView.name, "Renamed");
  assert.equal(renamedView.width, 200);
});

test("snapshot restore rejects stale revisions and invalid content without partial changes", async () => {
  const outputId = await monoId();
  const style = await styleId();
  const created = await createScene(backend, { name: "Card", width: 100, height: 100, outputProfileId: outputId });
  const placed = await addSceneLabel(backend, created.id, { text: "A", textStyleId: style, x: 0, y: 0 }, created.revision);
  const wanted = snapshotOf(placed);

  await assert.rejects(restoreSceneSnapshot(backend, placed.id, placed.revision + 1, wanted), /changed underneath/);
  await assert.rejects(restoreSceneSnapshot(backend, placed.id, "2" as never, wanted), /integer expected revision/);
  assert.deepEqual(await getScene(backend, placed.id), placed);

  const badStyle = snapshotOf(placed);
  badStyle.placements[0]!.textStyleId = "missing-style";
  await assert.rejects(restoreSceneSnapshot(backend, placed.id, placed.revision, badStyle), /does not exist/);
  const badName = snapshotOf(placed);
  badName.name = "";
  await assert.rejects(restoreSceneSnapshot(backend, placed.id, placed.revision, badName), /Scene names/);
  const badPoint = snapshotOf(placed);
  badPoint.placements[0]!.x = 1.5;
  await assert.rejects(restoreSceneSnapshot(backend, placed.id, placed.revision, badPoint), /pixel grid/);
  assert.deepEqual(await getScene(backend, placed.id), placed);

  await deleteScene(backend, placed.id, placed.revision);
  await assert.rejects(restoreSceneSnapshot(backend, placed.id, placed.revision, wanted), /does not exist/);
  assert.equal(await getScene(backend, placed.id), undefined);
});

test("snapshot restore keeps duplicate identical labels over repeated cycles", async () => {
  const outputId = await monoId();
  const style = await styleId();
  const created = await createScene(backend, { name: "Dupes", width: 100, height: 100, outputProfileId: outputId });
  const one = await addSceneLabel(backend, created.id, { text: "Same", textStyleId: style, x: 4, y: 5 }, created.revision);
  const two = await addSceneLabel(backend, one.id, { text: "Same", textStyleId: style, x: 4, y: 5 }, one.revision);
  assert.equal(two.placements.length, 2);
  const full = snapshotOf(two);
  const empty: SceneSnapshotInput = { ...snapshotOf(two), placements: [] };

  const cleared = await restoreSceneSnapshot(backend, two.id, two.revision, empty);
  assert.deepEqual(cleared.placements, []);
  const back = await restoreSceneSnapshot(backend, cleared.id, cleared.revision, full);
  assert.deepEqual(contentOf(back), contentOf(two));
  // A second delete/restore round still returns the same multiset: expired
  // placement ids never confuse the content-ordered match.
  const clearedAgain = await restoreSceneSnapshot(backend, back.id, back.revision, { ...snapshotOf(back), placements: [] });
  assert.deepEqual(clearedAgain.placements, []);
  const backAgain = await restoreSceneSnapshot(backend, clearedAgain.id, clearedAgain.revision, full);
  assert.deepEqual(contentOf(backAgain), contentOf(two));
});

test("scene list orders by name then id and skips missing scenes", async () => {
  const outputId = await monoId();
  const beta = await createScene(backend, { name: "Beta", width: 10, height: 10, outputProfileId: outputId });
  const alpha = await createScene(backend, { name: "Alpha", width: 10, height: 10, outputProfileId: outputId });
  const listed = await listScenes(backend);
  assert.deepEqual(listed.map((scene) => scene.id), [alpha.id, beta.id]);
  assert.equal(await getScene(backend, "missing"), undefined);
});

test("scene device selection defaults to custom and persists through updates", async () => {
  const outputId = await monoId();
  const custom = await createScene(backend, { name: "Custom", width: 400, height: 300, outputProfileId: outputId });
  assert.equal(custom.deviceId, null);

  const attached = await createScene(backend, {
    name: "Device", width: 480, height: 800, deviceId: "xteink-x4", outputProfileId: outputId,
  });
  assert.equal(attached.deviceId, "xteink-x4");

  const detached = await updateScene(backend, attached.id, { deviceId: null }, attached.revision);
  assert.equal(detached.deviceId, null);
  const reattached = await updateScene(backend, detached.id, { deviceId: "playdate", width: 400, height: 240 }, detached.revision);
  assert.deepEqual([reattached.deviceId, reattached.width, reattached.height], ["playdate", 400, 240]);

  await assert.rejects(updateScene(backend, reattached.id, { deviceId: "" }, reattached.revision), /device ids/);
  await assert.rejects(
    createScene(backend, { name: "Bad", width: 10, height: 10, deviceId: "x".repeat(81), outputProfileId: outputId }),
    /device ids/,
  );
  assert.deepEqual(await getScene(backend, reattached.id), reattached);
});
