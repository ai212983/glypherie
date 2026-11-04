// Graph integrity coverage: independent split entities, required-edge
// atomicity, stale-edit rejection after deletion, and reference guards.

import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import { closeDomainForTests, resetDomainForTests } from "../../src/app/domain/node-backend.ts";
import { getDomainVersion } from "../../src/app/domain/events.ts";
import { addSceneLabel, createScene, listOutputProfiles } from "../../src/app/domain/service.ts";
import { getFont, listFonts, removeFont, saveFont, type FontMetadata } from "../../src/app/fonts/storage.ts";
import {
  createPalette,
  deletePalette,
  listPalettes,
  updatePalette,
} from "../../src/app/palettes/repository.ts";
import {
  createVariant,
  deleteVariant,
  getVariant,
  listVariants,
  updateVariant,
} from "../../src/app/variants/repository.ts";
import { FontStorageError } from "../../src/app/fonts/storage.ts";
import { VariantStorageError } from "../../src/app/variants/model.ts";

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
  return saveFont({ bytes: fontBytes(seed), fileName: "fixture.ttf", name: "Fixture", metadata: metadata(), source: "uploaded" });
}

async function monoId(): Promise<string> {
  const mono = (await listOutputProfiles()).find((profile) => profile.name === "Monochrome");
  assert.ok(mono);
  return mono.id;
}

test("split variants stay independent: no shared-edit coupling", async () => {
  const font = await saveFixture();
  const first = await createVariant(font.id, { name: "First" });
  const second = await createVariant(font.id, { name: "Second" });
  const updated = await updateVariant(
    first.id,
    { settings: { ...first.settings, sizePx: 32, letterSpacingPx: 2 } },
    first.revision,
  );
  assert.equal(updated.revision, 2);
  const untouched = await getVariant(second.id);
  assert.equal(untouched?.revision, 1);
  assert.equal(untouched?.settings.sizePx, 16);
  assert.equal(untouched?.settings.letterSpacingPx, 0);
  // Renaming one style never renames its sibling.
  await updateVariant(first.id, { name: "Renamed" }, updated.revision);
  assert.equal((await getVariant(second.id))?.name, "Second");
});

test("variant writes are atomic: invalid settings keep every revision", async () => {
  const font = await saveFixture();
  const created = await createVariant(font.id);
  const version = getDomainVersion();
  await assert.rejects(
    updateVariant(created.id, { settings: { ...created.settings, sizePx: 9999 } }, created.revision),
    (error) => error instanceof VariantStorageError && error.code === "invalid-settings",
  );
  const current = await getVariant(created.id);
  assert.equal(current?.revision, created.revision);
  assert.equal(current?.settings.sizePx, 16);
  assert.equal(getDomainVersion(), version, "failed writes never bump the version");
});

test("creating a variant cannot leave a partial graph behind", async () => {
  await assert.rejects(
    createVariant("0".repeat(64)),
    (error) => error instanceof VariantStorageError && error.code === "font-not-found",
  );
  assert.deepEqual(await listVariants(), []);
  assert.deepEqual(await listFonts(), []);
});

test("deleting a variant used by a scene label is refused, then allowed after unplacing", async () => {
  const font = await saveFixture();
  const style = await createVariant(font.id);
  const scene = await createScene({ name: "Card", width: 100, height: 100, outputProfileId: await monoId() });
  const placed = await addSceneLabel(scene.id, { text: "Hi", textStyleId: style.id, x: 0, y: 0 }, scene.revision);
  await assert.rejects(
    deleteVariant(style.id),
    (error) => error instanceof VariantStorageError && error.code === "referenced",
  );
  const { removeSceneLabel } = await import("../../src/app/domain/service.ts");
  const cleaned = await removeSceneLabel(placed.id, placed.placements[0]!.id, placed.revision);
  await deleteVariant(style.id);
  assert.equal(await getVariant(style.id), undefined);
  assert.equal(cleaned.placements.length, 0);
});

test("removeFont cascades split entities but refuses fonts behind scene labels", async () => {
  const font = await saveFixture();
  const style = await createVariant(font.id);
  await removeFont(font.id);
  assert.equal(await getFont(font.id), undefined);
  assert.equal(await getVariant(style.id), undefined);
  assert.deepEqual(await listVariants(font.id), []);

  const kept = await saveFixture(5);
  const keptStyle = await createVariant(kept.id);
  const scene = await createScene({ name: "Card", width: 100, height: 100, outputProfileId: await monoId() });
  await addSceneLabel(scene.id, { text: "Hi", textStyleId: keptStyle.id, x: 0, y: 0 }, scene.revision);
  await assert.rejects(
    removeFont(kept.id),
    (error) => error instanceof FontStorageError && error.code === "referenced",
  );
  assert.ok(await getFont(kept.id));
});

test("palette deletion repoints preferences and bumps revisions, scene defaults block it", async () => {
  const font = await saveFixture();
  const id = await createPalette();
  const variant = await createVariant(font.id);
  const withGray = await updateVariant(
    variant.id,
    { settings: { ...variant.settings, paletteId: id, profile: "gray_2bit", rasterization: "coverage" } },
    variant.revision,
  );
  assert.equal(withGray.settings.profile, "gray_2bit");

  const scene = await createScene({ name: "Card", width: 100, height: 100, outputProfileId: await monoId() });
  const gray = (await listPalettes()).find((preset) => preset.id === id);
  assert.ok(gray);
  const service = await import("../../src/app/domain/service.ts");
  const grayNode = (await service.listOutputProfiles()).find((profile) => profile.name === `Grayscale ${id}`);
  assert.ok(grayNode);
  await service.updateScene(scene.id, { outputProfileId: grayNode.id }, scene.revision);
  await assert.rejects(deletePalette(id), /scene default|referenced/i);

  const live = await service.getScene(scene.id);
  assert.ok(live);
  await service.deleteScene(live.id, live.revision);
  await deletePalette(id);
  const loaded = await getVariant(variant.id);
  assert.equal(loaded?.settings.paletteId, 0);
  assert.equal(loaded?.revision, withGray.revision + 1);
});
