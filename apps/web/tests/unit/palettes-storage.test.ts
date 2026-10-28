import "fake-indexeddb/auto";
import assert from "node:assert/strict";
import test, { beforeEach } from "node:test";
import Dexie from "dexie";
import { fontDatabase } from "../../src/app/database.ts";
import { saveFont, type FontMetadata } from "../../src/app/fonts/storage.ts";
import { createPalette, deletePalette, listPalettes, updatePalette } from "../../src/app/palettes/repository.ts";
import { MONOCHROME, resolvePalette } from "../../src/app/palettes/model.ts";
import { curveLevels, editCurveLevel, linearCurve, pinCurveLevel } from "../../src/app/features/grayscale/response-curve.ts";
import { paletteProfile, presetColors } from "../../src/app/palettes/render.ts";
import { toRenderSpec } from "../../src/app/renderer/render-spec.ts";
import { defaultVariantSettings, VariantStorageError } from "../../src/app/variants/model.ts";
import { createVariant, getVariant, updateVariant } from "../../src/app/variants/repository.ts";

function fixtureMetadata(): FontMetadata {
  return {
    names: { family: "Fixture" },
    axes: [{ tag: "wght", name: "Weight", min: 100, default: 400, max: 900, hidden: false }],
  };
}

async function saveFixtureFont(seed = 0) {
  const bytes = Uint8Array.from({ length: 64 }, (_, i) => (i * 7 + seed) % 251).buffer as ArrayBuffer;
  return saveFont({ bytes, fileName: "fixture.ttf", name: "Fixture", metadata: fixtureMetadata(), source: "uploaded" });
}

Dexie.dependencies.indexedDB = globalThis.indexedDB;
Dexie.dependencies.IDBKeyRange = globalThis.IDBKeyRange;
beforeEach(async () => { fontDatabase.close(); await Dexie.delete("font-library"); });

test("palette names, depth, fractional curves, slopes and handles survive reopening", async () => {
  assert.deepEqual(await listPalettes(), [MONOCHROME]);
  const id = await createPalette();
  const curve = pinCurveLevel(editCurveLevel(linearCurve(16), 5, 171), 7);
  await updatePalette(id, { name: "Paper", curve: () => curve });
  fontDatabase.close();
  assert.deepEqual((await listPalettes()).find((row) => row.id === id), { id, name: "Paper", curve });
  await assert.rejects(updatePalette(0, { name: "Changed" }), /read-only/);
  await assert.rejects(deletePalette(0), /read-only/);
});

test("concurrent creations have stable unique IDs and curve edits compose", async () => {
  const ids = await Promise.all([createPalette(), createPalette()]);
  assert.equal(new Set(ids).size, 2);
  await Promise.all([
    updatePalette(ids[0]!, { curve: (curve) => editCurveLevel(curve, 1, 140) }),
    updatePalette(ids[0]!, { curve: (curve) => editCurveLevel(curve, 2, 70) }),
  ]);
  const row = (await listPalettes()).find((row) => row.id === ids[0])!;
  assert.deepEqual(curveLevels(row.curve), [255, 140, 70, 0]);
  await deletePalette(row.id);
  await assert.rejects(updatePalette(row.id, { name: "Resurrect" }), /deleted/);
  assert.equal(resolvePalette(await listPalettes(), row.id).id, 0);
});

test("only 1–4-bit palettes persist and render with their exact defined entries", async () => {
  const id = await createPalette();
  for (const count of [2, 4, 8, 16]) {
    await updatePalette(id, { curve: () => linearCurve(count) });
    const preset = (await listPalettes()).find((row) => row.id === id)!;
    const palette = presetColors(preset, "black-white", false);
    const spec = toRenderSpec({ text: "A", sizePx: 16, axes: {}, profile: paletteProfile(preset),
      rasterization: count === 2 ? "free_type_mono" : "coverage", width: 100, height: 100, palette });
    assert.equal(spec.output_bits, Math.log2(count));
    assert.deepEqual(spec.palette?.map((entry) => entry[0]), curveLevels(preset.curve));
    assert.equal(spec.pipeline?.rasterization, count === 2 ? "free_type_mono_terminals" : "coverage");
  }
  for (const count of [3, 32, 256]) await assert.rejects(updatePalette(id, { curve: () => linearCurve(count) }), /Invalid/);
});

test("deleting a preset falls back referencing variants to Monochrome with a revision bump", async () => {
  const font = await saveFixtureFont();
  const id = await createPalette();
  await updatePalette(id, { curve: () => linearCurve(4) });
  const base = defaultVariantSettings(font);
  const variant = await createVariant(font.id, {
    settings: { ...base, paletteId: id, profile: "gray_2bit", rasterization: "coverage" },
  });
  assert.equal(variant.settings.paletteId, id);
  assert.equal(variant.settings.profile, "gray_2bit");

  await deletePalette(id);
  const loaded = await getVariant(variant.id);
  assert.equal(loaded?.settings.paletteId, 0);
  assert.equal(loaded?.settings.profile, "mono_1bit");
  assert.equal(loaded?.revision, variant.revision + 1);
  assert.equal(resolvePalette(await listPalettes(), id).id, 0);
});

test("stale drafts conflict after a palette deletion instead of resurrecting it", async () => {
  const font = await saveFixtureFont();
  const id = await createPalette();
  const base = defaultVariantSettings(font);
  const variant = await createVariant(font.id, { settings: { ...base, paletteId: id } });
  const stale = await getVariant(variant.id);
  assert.ok(stale);

  await deletePalette(id);
  await assert.rejects(
    updateVariant(variant.id, { name: "Stale write" }, stale!.revision),
    (error) => error instanceof VariantStorageError && error.code === "conflict",
  );
  const current = await getVariant(variant.id);
  assert.ok(current);
  const repaired = await updateVariant(
    variant.id,
    { settings: { ...current!.settings, paletteId: id } },
    current!.revision,
  );
  assert.equal(repaired.settings.paletteId, 0, "a removed palette normalizes to Monochrome, never stored");
  assert.equal(repaired.settings.profile, "mono_1bit");
});

test("reads normalize unknown palette references to Monochrome", async () => {
  const font = await saveFixtureFont();
  const variant = await createVariant(font.id);
  await fontDatabase.variants.update(variant.id, {
    settings: { ...variant.settings, paletteId: 999, profile: "gray_4bit" },
  } as never);
  const loaded = await getVariant(variant.id);
  assert.equal(loaded?.settings.paletteId, 0);
  assert.equal(loaded?.settings.profile, "mono_1bit");
});

test("variant writes normalize a stale profile to the preset live depth", async () => {
  const font = await saveFixtureFont();
  const id = await createPalette();
  await updatePalette(id, { curve: () => linearCurve(4) });
  const base = defaultVariantSettings(font);
  const variant = await createVariant(font.id, { settings: { ...base, paletteId: id } });
  assert.equal(variant.settings.profile, "gray_2bit");

  // Another tab edits the palette depth; the variant row keeps its revision.
  await updatePalette(id, { curve: () => linearCurve(16) });
  const clean = await getVariant(variant.id);
  assert.equal(clean?.revision, variant.revision);
  assert.equal(clean?.settings.profile, "gray_4bit");

  // A draft holding the stale profile still saves, normalizing to the live depth.
  const saved = await updateVariant(
    variant.id,
    { sampleText: "depth probe", settings: variant.settings },
    variant.revision,
  );
  assert.equal(saved.settings.profile, "gray_4bit");
  assert.equal(saved.revision, variant.revision + 1);
});

test("font settings keep a stable palette ID and follow the preset's live depth", async () => {
  const font = await saveFixtureFont();
  const id = await createPalette();
  await updatePalette(id, { name: "Deep", curve: () => linearCurve(16) });
  const base = defaultVariantSettings(font);
  const variant = await createVariant(font.id, { settings: { ...base, paletteId: id } });
  assert.equal(variant.settings.profile, "gray_4bit");
  fontDatabase.close();
  assert.equal((await getVariant(variant.id))?.settings.paletteId, id);
  assert.equal((await getVariant(variant.id))?.settings.profile, "gray_4bit");

  await updatePalette(id, { curve: () => linearCurve(4) });
  assert.equal((await getVariant(variant.id))?.settings.paletteId, id);
  assert.equal((await getVariant(variant.id))?.settings.profile, "gray_2bit");
});

test("v2 upgrades retain fonts and variants, seed Monochrome and migrate undefined output", async () => {
  const legacy = new Dexie("font-library");
  legacy.version(2).stores({ fonts: "id, addedAt, source", meta: "key", variants: "id, fontId" });
  await legacy.table("fonts").put({ id: "font", bytes: new ArrayBuffer(12) });
  await legacy.table("meta").put({ key: "seed", value: "kept" });
  await legacy.table("variants").put({ id: "variant", fontId: "font", settings: { profile: "gray_3bit", sizePx: 20, axes: {} } });
  legacy.close();
  assert.deepEqual(await listPalettes(), [MONOCHROME]);
  assert.equal((await fontDatabase.fonts.get("font"))?.bytes.byteLength, 12);
  assert.equal((await fontDatabase.meta.get("seed"))?.value, "kept");
  const row = await fontDatabase.variants.get("variant");
  assert.equal(row?.settings.paletteId, 0);
  assert.equal(row?.settings.profile, "mono_1bit");
  assert.equal(row?.settings.sizePx, 20);
});
