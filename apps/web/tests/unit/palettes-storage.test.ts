import "fake-indexeddb/auto";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test, { after, beforeEach } from "node:test";
import Dexie from "dexie";
import { fontDatabase } from "../../src/app/database.ts";
import { kvPut } from "../../src/app/domain/backend.ts";
import { importLegacySnapshot } from "../../src/app/domain/importer.ts";
import { callDomain } from "../../src/app/domain/runtime.ts";
import { getBackend, closeDomainForTests, resetDomainForTests } from "../../src/app/domain/node-backend.ts";
import { readLegacySnapshot } from "../../src/app/legacy-database.ts";
import { getFont, saveFont, type FontMetadata } from "../../src/app/fonts/storage.ts";
import { createPalette, deletePalette, listPalettes, updatePalette } from "../../src/app/palettes/repository.ts";
import { MONOCHROME, resolvePalette } from "../../src/app/palettes/model.ts";
import { PREVIEW_MONO_RASTER } from "../../src/app/renderer/render-spec.ts";
import {
  curveLevels,
  editCurveLevel,
  linearCurve,
  pinCurveLevel,
} from "../../src/app/features/grayscale/response-curve.ts";
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
beforeEach(async () => {
  await resetDomainForTests();
  await fontDatabase.close();
  await Dexie.delete("font-library");
  await fontDatabase.open();
});

after(async () => {
  await closeDomainForTests();
});

test("palette names, depth, fractional curves, slopes and handles survive reopening", async (t) => {
  const { promises: fs } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { default: path } = await import("node:path");
  const { createDomainBackend } = await import("../../src/app/domain/backend.ts");
  const { configureDomain } = await import("../../src/app/domain/node-backend.ts");
  const dir = await fs.mkdtemp(path.join(tmpdir(), "glypherie-domain-"));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const dataDir = path.join(dir, "pgdata");
  await configureDomain(await createDomainBackend({ dataDir }));
  assert.deepEqual(await listPalettes(), [MONOCHROME]);
  const id = await createPalette();
  const curve = pinCurveLevel(editCurveLevel(linearCurve(16), 5, 171), 7);
  await updatePalette(id, { kind: "rename", name: "Paper" });
  // Whole-curve setup carries the revision just read: creation is revision 1,
  // the rename is revision 2, so the replacement lands as revision 3.
  const renamed = (await listPalettes()).find((row) => row.id === id);
  assert.ok(renamed);
  await updatePalette(id, { kind: "replace", curve, expectedRevision: renamed.revision });
  await configureDomain(await createDomainBackend({ dataDir }));
  assert.deepEqual(
    (await listPalettes()).find((row) => row.id === id),
    { id, name: "Paper", curve, revision: renamed.revision + 1 },
  );
  await assert.rejects(updatePalette(0, { kind: "rename", name: "Changed" }), /read-only/);
  await assert.rejects(deletePalette(0), /read-only/);
});

test("deleted palette IDs are never reused", async () => {
  assert.equal(await createPalette(), 1, "first custom preset follows Monochrome (id 0)");
  assert.equal(await createPalette(), 2);
  await deletePalette(1);
  assert.equal(await createPalette(), 3, "a deleted ID stays retired instead of being reissued");
  assert.deepEqual(
    (await listPalettes()).map((preset) => preset.id),
    [0, 2, 3],
  );
});

test("concurrent creations after a delete stay unique and above the live max", async () => {
  assert.equal(await createPalette(), 1);
  await deletePalette(1);
  const ids = await Promise.all([createPalette(), createPalette(), createPalette(), createPalette()]);
  assert.deepEqual(
    [...ids].sort((a, b) => a - b),
    [2, 3, 4, 5],
  );
});

test("the identity sequence survives reopening the store", async (t) => {
  const { promises: fs } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { default: path } = await import("node:path");
  const { createDomainBackend } = await import("../../src/app/domain/backend.ts");
  const { configureDomain } = await import("../../src/app/domain/node-backend.ts");
  const dir = await fs.mkdtemp(path.join(tmpdir(), "glypherie-palette-ids-"));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const dataDir = path.join(dir, "pgdata");
  await configureDomain(await createDomainBackend({ dataDir }));
  assert.equal(await createPalette(), 1);
  await deletePalette(1);
  await configureDomain(await createDomainBackend({ dataDir }));
  assert.equal(await createPalette(), 2, "reopening must not reset the sequence to the live max");
  assert.deepEqual(
    (await listPalettes()).map((preset) => preset.id),
    [0, 2],
  );
});

test("import keeps every legacy ID and allocates above the highest one", async () => {
  await fontDatabase.palettes.put({ id: 5, name: "Legacy Five", curve: linearCurve(4) });
  await fontDatabase.palettes.put({ id: 7, name: "Legacy Seven", curve: linearCurve(16) });
  const result = await importLegacySnapshot(getBackend(), await readLegacySnapshot());
  assert.equal(result.skipped, false);
  assert.deepEqual(
    (await listPalettes()).map((preset) => preset.id),
    [0, 5, 7],
  );
  assert.equal((await listPalettes()).find((preset) => preset.id === 7)?.name, "Legacy Seven");
  assert.equal(await createPalette(), 8, "creation continues above the imported range");
  await deletePalette(8);
  assert.equal(await createPalette(), 9, "deleted post-import IDs stay retired too");
});

test("concurrent creations have stable unique IDs and curve edits compose", async () => {
  const ids = await Promise.all([createPalette(), createPalette()]);
  assert.equal(new Set(ids).size, 2);
  await Promise.all([
    updatePalette(ids[0]!, { kind: "setLevel", index: 1, value: 140, depth: 4 }),
    updatePalette(ids[0]!, { kind: "setLevel", index: 2, value: 70, depth: 4 }),
  ]);
  const row = (await listPalettes()).find((row) => row.id === ids[0])!;
  assert.deepEqual(curveLevels(row.curve), [255, 140, 70, 0]);
  await deletePalette(row.id);
  await assert.rejects(updatePalette(row.id, { kind: "rename", name: "Resurrect" }), /deleted/);
  assert.equal(resolvePalette(await listPalettes(), row.id).id, 0);
});

test("only 1–4-bit palettes persist and render with their exact defined entries", async () => {
  const id = await createPalette();
  for (const count of [2, 4, 8, 16]) {
    const live = (await listPalettes()).find((row) => row.id === id);
    assert.ok(live);
    await updatePalette(id, { kind: "replace", curve: linearCurve(count), expectedRevision: live.revision });
    const preset = (await listPalettes()).find((row) => row.id === id)!;
    const palette = presetColors(preset, "black-white", false);
    const spec = toRenderSpec({
      text: "A",
      sizePx: 16,
      axes: {},
      profile: paletteProfile(preset),
      rasterization: count === 2 ? "free_type_mono" : "coverage",
      width: 100,
      height: 100,
      palette,
    });
    assert.equal(spec.output_bits, Math.log2(count));
    assert.deepEqual(
      spec.palette?.map((entry) => entry[0]),
      curveLevels(preset.curve),
    );
    assert.equal(spec.pipeline?.rasterization, count === 2 ? "free_type_mono_terminals" : "coverage");
  }
  for (const count of [3, 32, 256]) {
    const live = (await listPalettes()).find((row) => row.id === id);
    assert.ok(live);
    await assert.rejects(
      updatePalette(id, { kind: "replace", curve: linearCurve(count), expectedRevision: live.revision }),
      /Invalid/,
    );
  }
});

test("deleting a preset falls back referencing variants to Monochrome with a revision bump", async () => {
  const font = await saveFixtureFont();
  const id = await createPalette();
  await updatePalette(id, { kind: "resize", count: 4 });
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
  // Point the style preference at a profile that does not exist.
  await kvPut(
    getBackend().db,
    `preview:${variant.id}`,
    JSON.stringify({
      sampleText: variant.sampleText,
      inheritSampleText: variant.inheritSampleText,
      outputProfileId: "missing-profile",
    }),
  );
  const loaded = await getVariant(variant.id);
  assert.equal(loaded?.settings.paletteId, 0);
  assert.equal(loaded?.settings.profile, "mono_1bit");
});

test("variant writes normalize a stale profile to the preset live depth", async () => {
  const font = await saveFixtureFont();
  const id = await createPalette();
  await updatePalette(id, { kind: "resize", count: 4 });
  const base = defaultVariantSettings(font);
  const variant = await createVariant(font.id, { settings: { ...base, paletteId: id } });
  assert.equal(variant.settings.profile, "gray_2bit");

  // Another tab edits the palette depth; the variant row keeps its revision.
  await updatePalette(id, { kind: "resize", count: 16 });
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
  await updatePalette(id, { kind: "rename", name: "Deep" });
  await updatePalette(id, { kind: "resize", count: 16 });
  const base = defaultVariantSettings(font);
  const variant = await createVariant(font.id, { settings: { ...base, paletteId: id } });
  assert.equal(variant.settings.profile, "gray_4bit");
  assert.equal((await getVariant(variant.id))?.settings.paletteId, id);
  assert.equal((await getVariant(variant.id))?.settings.profile, "gray_4bit");

  await updatePalette(id, { kind: "resize", count: 4 });
  assert.equal((await getVariant(variant.id))?.settings.paletteId, id);
  assert.equal((await getVariant(variant.id))?.settings.profile, "gray_2bit");
});

test("importing a legacy library without custom palettes still starts custom IDs at 1", async () => {
  const result = await importLegacySnapshot(getBackend(), await readLegacySnapshot());
  assert.equal(result.skipped, false);
  assert.deepEqual(
    (await listPalettes()).map((preset) => preset.id),
    [0],
  );
  assert.equal(await createPalette(), 1, "an import holding only Monochrome must not consume ID 1");
});

test("legacy rows import with Monochrome fallback and the seed marker preserved", async () => {
  const bytes = new Uint8Array(12).buffer as ArrayBuffer;
  const fontId = createHash("sha256").update(Buffer.from(bytes)).digest("hex");
  await fontDatabase.fonts.put({
    id: fontId,
    name: "Legacy",
    fileName: "legacy.ttf",
    bytes,
    metadata: fixtureMetadata(),
    source: "uploaded",
    addedAt: 7,
  });
  await fontDatabase.meta.put({ key: "bundled-fonts", value: "kept-seed" });
  // Legacy rows without a palette reference resolve to Monochrome on import.
  await fontDatabase.variants.put({
    id: "variant",
    fontId: fontId,
    name: "Legacy V",
    settingsVersion: 1,
    settings: {
      sizePx: 20,
      axes: { wght: 400 },
      letterSpacingPx: 0,
      profile: "mono_1bit",
      kerning: true,
      stemFitting: "font_hints_first",
      diagonalFitting: false,
      monoRaster: { ...PREVIEW_MONO_RASTER },
      renderer: "candidate",
      rasterization: "free_type_mono",
    },
    sampleText: "Hi",
    revision: 3,
    createdAt: 1,
    updatedAt: 2,
  });
  const result = await importLegacySnapshot(getBackend(), await readLegacySnapshot());
  assert.equal(result.skipped, false);
  // The legacy Monochrome preset row maps onto the seeded graph profile.
  assert.deepEqual([result.fonts, result.variants, result.palettes], [1, 1, 1]);
  assert.deepEqual(await listPalettes(), [MONOCHROME]);
  assert.equal((await getFont(fontId))?.bytes.byteLength, 12);
  assert.equal(await callDomain("getSeedMarker", []), "kept-seed");
  const row = await getVariant("variant");
  assert.equal(row?.revision, 3);
  assert.equal(row?.fontId, fontId);
  assert.equal(row?.settings.paletteId, 0);
  assert.equal(row?.settings.profile, "mono_1bit");
  assert.equal(row?.settings.sizePx, 20);
  assert.equal(row?.sampleText, "Hi");
});
