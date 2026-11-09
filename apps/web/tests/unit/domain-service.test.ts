// Service contract coverage: scenes, placements, CAS revisions and the
// single/batch resolvers, against the real in-memory PGlite/TypeGraph store.

import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import { closeDomainForTests, resetDomainForTests } from "../../src/app/domain/node-backend.ts";
import {
  addSceneLabel,
  createScene,
  deleteScene,
  getScene,
  listOutputProfiles,
  listScenes,
  listTextStyles,
  removeSceneLabel,
  resolveTextStyle,
  resolveTextStyles,
  updateScene,
  updateSceneLabel,
} from "../../src/app/domain/service.ts";
import { createPalette, updatePalette } from "../../src/app/palettes/repository.ts";
import { createVariant } from "../../src/app/variants/repository.ts";
import { saveFont, type FontMetadata } from "../../src/app/fonts/storage.ts";

beforeEach(async () => {
  await resetDomainForTests();
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
  return saveFont({
    bytes: fontBytes(seed),
    fileName: "fixture.ttf",
    name: "Fixture",
    metadata: metadata(),
    source: "uploaded",
  });
}

async function monoId(): Promise<string> {
  const profiles = await listOutputProfiles();
  const mono = profiles.find((profile) => profile.name === "Monochrome");
  assert.ok(mono);
  return mono.id;
}

test("scene views carry placements with stable integer order", async () => {
  const font = await saveFixture();
  const style = await createVariant(font.id, { name: "Body" });
  const outputId = await monoId();
  const created = await createScene({ name: "Card", width: 400, height: 300, outputProfileId: outputId });
  assert.equal(created.revision, 1);
  assert.deepEqual(created.placements, []);
  assert.deepEqual(created.exportCoverage, { presetIds: ["ascii"], extraRanges: [] });

  const placed = await addSceneLabel(
    created.id,
    { text: "Hello", textStyleId: style.id, x: 16, y: 12 },
    created.revision,
  );
  assert.equal(placed.revision, 2);
  assert.equal(placed.placements.length, 1);
  assert.equal(placed.placements[0]?.order, 0);

  const styles = await listTextStyles();
  assert.deepEqual(
    styles.map((entry) => entry.id),
    [style.id],
  );
  assert.equal(styles[0]?.fontId, font.id);
  assert.equal(styles[0]?.fontSize, 16);

  const moved = await updateSceneLabel(placed.id, placed.placements[0]!.id, { x: 20, order: 3 }, placed.revision);
  assert.equal(moved.revision, 3);
  assert.equal(moved.placements[0]?.x, 20);
  assert.equal(moved.placements[0]?.order, 3);

  const second = await addSceneLabel(moved.id, { text: "World", textStyleId: style.id, x: 0, y: 0 }, moved.revision);
  assert.deepEqual(
    second.placements.map((placement) => placement.order),
    [3, 4],
  );

  const cleaned = await removeSceneLabel(second.id, second.placements[0]!.id, second.revision);
  assert.equal(cleaned.placements.length, 1);
  assert.equal(cleaned.placements[0]?.text, "World");

  await deleteScene(cleaned.id, cleaned.revision);
  assert.equal(await getScene(cleaned.id), undefined);
  assert.deepEqual(await listScenes(), []);
});

test("scene CAS rejects stale writes and stale deletes cannot resurrect", async () => {
  const outputId = await monoId();
  const created = await createScene({ name: "Card", width: 400, height: 300, outputProfileId: outputId });
  await assert.rejects(updateScene(created.id, { name: "Stale" }, created.revision + 1), /changed underneath/);
  await assert.rejects(deleteScene(created.id, created.revision + 1), /changed underneath/);
  const renamed = await updateScene(created.id, { name: "Kept", width: 200 }, created.revision);
  assert.equal(renamed.revision, 2);
  assert.equal(renamed.width, 200);
  await deleteScene(renamed.id, renamed.revision);
  await assert.rejects(updateScene(renamed.id, { name: "Ghost" }, renamed.revision + 1), /does not exist/);
});

test("scene creation validates dimensions, coverage and output references", async () => {
  const outputId = await monoId();
  await assert.rejects(createScene({ name: "", width: 10, height: 10, outputProfileId: outputId }), /Scene names/);
  await assert.rejects(createScene({ name: "Bad", width: 0, height: 10, outputProfileId: outputId }), /dimensions/);
  await assert.rejects(
    createScene({ name: "Bad", width: 10, height: 10, outputProfileId: "missing" }),
    /does not exist/,
  );
  await assert.rejects(
    createScene({
      name: "Bad",
      width: 10,
      height: 10,
      outputProfileId: outputId,
      exportCoverage: { presetIds: ["nope" as never], extraRanges: [] },
    }),
    /Unknown coverage preset/,
  );
  const font = await saveFixture();
  const style = await createVariant(font.id);
  const scene = await createScene({ name: "Ok", width: 10, height: 10, outputProfileId: outputId });
  await assert.rejects(
    addSceneLabel(scene.id, { text: "x", textStyleId: "missing-style", x: 0, y: 0 }, scene.revision),
    /does not exist/,
  );
  await assert.rejects(
    addSceneLabel(scene.id, { text: "x", textStyleId: style.id, x: 1.5, y: 0 }, scene.revision),
    /pixel grid/,
  );
});

test("single and batch resolvers agree and keep settings off the graph", async () => {
  const font = await saveFixture();
  const first = await createVariant(font.id, {
    name: "First",
    settings: {
      sizePx: 24,
      axes: { wght: 700 },
      letterSpacingPx: 1,
      profile: "mono_1bit",
      paletteId: 0,
      kerning: false,
      stemFitting: "upstream_mono",
      diagonalFitting: true,
      monoRaster: { dropout: "off", includeStubs: false, fontInstructions: false },
      renderer: "candidate",
      rasterization: "free_type_mono",
    },
  });
  const second = await createVariant(font.id, { name: "Second" });
  const outputId = await monoId();
  const single = await resolveTextStyle(first.id, outputId);
  assert.equal(single.fontId, font.id);
  assert.equal(single.settings.sizePx, 24);
  assert.equal(single.settings.letterSpacingPx, 1);
  assert.equal(single.settings.stemFitting, "upstream_mono");
  assert.equal(single.settings.diagonalFitting, true);
  // Retired pipeline knobs never persist: the resolve follows working policy.
  assert.equal(single.settings.renderer, "candidate");

  const batch = await resolveTextStyles([first.id, second.id], outputId);
  assert.equal(batch.length, 2);
  assert.deepEqual(batch[0], single);
  assert.equal(batch[1]?.settings.sizePx, 16);
  assert.deepEqual(await resolveTextStyles([], outputId), []);

  await assert.rejects(resolveTextStyles([first.id, "missing"], outputId), /does not exist/);
  await assert.rejects(resolveTextStyle("missing", outputId), /does not exist/);
  await assert.rejects(resolveTextStyle(first.id, "missing-profile"), /does not exist/);
});

test("batch resolve derives profile depth from the output curve", async () => {
  const font = await saveFixture();
  const style = await createVariant(font.id);
  const grayId = await createPalette();
  await updatePalette(grayId, { kind: "resize", count: 8 });
  const gray = (await listOutputProfiles()).find((profile) => profile.name === `Grayscale ${grayId}`);
  assert.ok(gray);
  const [resolved] = await resolveTextStyles([style.id], gray.id);
  assert.equal(resolved?.settings.profile, "gray_3bit");
  assert.equal(resolved?.settings.paletteId, grayId);
});

test("label grid accepts zero/negative points and empty text, rejects atomically", async () => {
  const font = await saveFixture();
  const first = await createVariant(font.id, { name: "First" });
  const second = await createVariant(font.id, { name: "Second" });
  const outputId = await monoId();
  const created = await createScene({ name: "Card", width: 400, height: 300, outputProfileId: outputId });

  // Zero and negative coordinates sit on the native pixel grid.
  const placed = await addSceneLabel(created.id, { text: "", textStyleId: first.id, x: 0, y: -12 }, created.revision);
  assert.equal(placed.placements[0]?.text, "");
  assert.equal(placed.placements[0]?.x, 0);
  assert.equal(placed.placements[0]?.y, -12);

  const placementId = placed.placements[0]!.id;
  const moved = await updateSceneLabel(
    placed.id,
    placementId,
    { text: "Hi", textStyleId: second.id, x: -4, y: 0, order: -1 },
    placed.revision,
  );
  assert.equal(moved.revision, placed.revision + 1);
  assert.deepEqual(
    [moved.placements[0]?.text, moved.placements[0]?.textStyleId, moved.placements[0]?.x, moved.placements[0]?.order],
    ["Hi", second.id, -4, -1],
  );

  // Rejected patches must preserve every affected node, edge and revision.
  const before = await getScene(moved.id);
  assert.ok(before);
  await assert.rejects(
    updateSceneLabel(moved.id, placementId, { text: "x".repeat(8193) }, moved.revision),
    /within 8192/,
  );
  await assert.rejects(
    updateSceneLabel(moved.id, placementId, { textStyleId: "missing-style" }, moved.revision),
    /does not exist/,
  );
  await assert.rejects(updateSceneLabel(moved.id, placementId, { order: 1.5 }, moved.revision), /stable integer/);
  await assert.rejects(updateSceneLabel(moved.id, placementId, { x: 1.5 }, moved.revision), /pixel grid/);
  await assert.rejects(
    updateSceneLabel(moved.id, "missing-placement", { x: 1 }, moved.revision),
    /does not exist in scene/,
  );
  await assert.rejects(updateSceneLabel(moved.id, placementId, { x: 1 }, moved.revision + 1), /changed underneath/);
  await assert.rejects(removeSceneLabel(moved.id, placementId, moved.revision + 1), /changed underneath/);
  assert.deepEqual(await getScene(moved.id), before);
});

test("label placements reject foreign scenes and keep deterministic order", async () => {
  const font = await saveFixture();
  const style = await createVariant(font.id);
  const outputId = await monoId();
  const left = await createScene({ name: "Left", width: 100, height: 100, outputProfileId: outputId });
  const right = await createScene({ name: "Right", width: 100, height: 100, outputProfileId: outputId });
  const placed = await addSceneLabel(left.id, { text: "A", textStyleId: style.id, x: 0, y: 0 }, left.revision);
  const placementId = placed.placements[0]!.id;

  await assert.rejects(updateSceneLabel(right.id, placementId, { x: 2 }, right.revision), /does not exist in scene/);
  await assert.rejects(removeSceneLabel(right.id, placementId, right.revision), /does not exist in scene/);

  const second = await addSceneLabel(placed.id, { text: "B", textStyleId: style.id, x: 1, y: 1 }, placed.revision);
  const [firstPlacement, secondPlacement] = second.placements;
  // Equal orders fall back to placement id order, so the view stays stable.
  const tied = await updateSceneLabel(
    second.id,
    secondPlacement!.id,
    { order: firstPlacement!.order },
    second.revision,
  );
  assert.deepEqual(
    tied.placements.map((placement) => placement.id).sort(),
    [firstPlacement!.id, secondPlacement!.id].sort(),
  );
  assert.equal(tied.placements[0]?.order, tied.placements[1]?.order);
});

test("scene patches merge partial dimensions and reject without touching state", async () => {
  const outputId = await monoId();
  const created = await createScene({ name: "Card", width: 400, height: 300, outputProfileId: outputId });

  // Partial dimensions merge against stored values; an empty patch still bumps.
  const narrowed = await updateScene(created.id, { width: 200 }, created.revision);
  assert.deepEqual([narrowed.width, narrowed.height, narrowed.revision], [200, 300, 2]);
  const noop = await updateScene(narrowed.id, {}, narrowed.revision);
  assert.equal(noop.revision, 3);
  const explicitUndefined = await updateScene(noop.id, { name: undefined, width: undefined }, noop.revision);
  assert.deepEqual([explicitUndefined.name, explicitUndefined.width, explicitUndefined.revision], ["Card", 200, 4]);

  const before = await getScene(explicitUndefined.id);
  assert.ok(before);
  await assert.rejects(updateScene(before.id, { name: "" }, before.revision), /Scene names/);
  await assert.rejects(updateScene(before.id, { height: 0 }, before.revision), /dimensions/);
  await assert.rejects(updateScene(before.id, { outputProfileId: "missing" }, before.revision), /does not exist/);
  await assert.rejects(updateScene("missing-scene", { name: "Ghost" }, 1), /refusing to recreate/);
  await assert.rejects(
    updateSceneLabel(before.id, "missing-placement", {}, before.revision),
    /does not exist in scene/,
  );
  assert.deepEqual(await getScene(before.id), before);
});
