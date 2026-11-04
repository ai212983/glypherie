// Atomic variant/palette writes: an auxiliary preference failure must reject
// the whole operation, leave graph state and revisions untouched, and allow
// retry with the same expected revision. Fault injection uses a temporary SQL
// trigger on app_kv, so it fails regardless of which Drizzle handle the
// implementation writes through.

import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import { sql } from "drizzle-orm";
import {
  closeDomainForTests,
  getBackend,
  resetDomainForTests,
} from "../../src/app/domain/node-backend.ts";
import { saveFont, type FontMetadata } from "../../src/app/fonts/storage.ts";
import {
  createPalette,
  deletePalette,
  listPalettes,
  updatePalette,
} from "../../src/app/palettes/repository.ts";
import {
  createVariant,
  getVariant,
  listVariants,
  updateVariant,
} from "../../src/app/variants/repository.ts";
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
  return saveFont({
    bytes: fontBytes(seed),
    fileName: "fixture.ttf",
    name: "Fixture",
    metadata: metadata(),
    source: "uploaded",
  });
}

async function rejectPreviewPrefs(): Promise<void> {
  const backend = getBackend();
  await backend.db.execute(
    sql`CREATE OR REPLACE FUNCTION reject_preview_prefs() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'injected preference-write failure'; END; $$ LANGUAGE plpgsql`,
  );
  await backend.db.execute(sql`DROP TRIGGER IF EXISTS reject_preview_prefs ON app_kv`);
  await backend.db.execute(
    sql`CREATE TRIGGER reject_preview_prefs BEFORE INSERT OR UPDATE ON app_kv FOR EACH ROW WHEN (NEW.key LIKE 'preview:%') EXECUTE FUNCTION reject_preview_prefs()`,
  );
}

async function allowPreviewPrefs(): Promise<void> {
  await getBackend().db.execute(sql`DROP TRIGGER IF EXISTS reject_preview_prefs ON app_kv`);
}

async function previewPrefCount(): Promise<number> {
  const result = await getBackend().db.execute(sql`SELECT key FROM app_kv WHERE key LIKE 'preview:%'`);
  return (result.rows as unknown[]).length;
}

test("updateVariant is atomic when preference writes fail", async () => {
  const font = await saveFixture();
  const before = await createVariant(font.id, { name: "Before", sampleText: "before" });
  await rejectPreviewPrefs();
  try {
    await assert.rejects(
      updateVariant(
        before.id,
        { settings: { ...before.settings, sizePx: 23 }, sampleText: "after" },
        before.revision,
      ),
      (error) => error instanceof VariantStorageError && error.code === "unavailable",
    );
    const kept = await getVariant(before.id);
    assert.equal(kept?.revision, before.revision);
    assert.equal(kept?.settings.sizePx, before.settings.sizePx);
    assert.equal(kept?.sampleText, "before");
  } finally {
    await allowPreviewPrefs();
  }
  const retried = await updateVariant(
    before.id,
    { settings: { ...before.settings, sizePx: 23 }, sampleText: "after" },
    before.revision,
  );
  assert.equal(retried.revision, before.revision + 1);
  assert.equal(retried.settings.sizePx, 23);
  assert.equal(retried.sampleText, "after");
});

test("createVariant leaves no nodes or preferences when preference writes fail", async () => {
  const font = await saveFixture();
  await rejectPreviewPrefs();
  try {
    await assert.rejects(
      createVariant(font.id, { name: "Ghost", sampleText: "ghost" }),
      (error) => error instanceof VariantStorageError,
    );
    assert.deepEqual(await listVariants(), []);
    assert.equal(await previewPrefCount(), 0);
  } finally {
    await allowPreviewPrefs();
  }
  const fontKept = await saveFixture(1);
  assert.ok(fontKept.id);
});

test("deletePalette keeps profile, references and revisions when preference writes fail", async () => {
  const font = await saveFixture();
  const id = await createPalette();
  const variant = await createVariant(font.id);
  const withGray = await updateVariant(
    variant.id,
    { settings: { ...variant.settings, paletteId: id, profile: "gray_2bit", rasterization: "coverage" } },
    variant.revision,
  );
  await rejectPreviewPrefs();
  try {
    await assert.rejects(deletePalette(id));
    assert.ok((await listPalettes()).some((preset) => preset.id === id));
    const kept = await getVariant(variant.id);
    assert.equal(kept?.settings.paletteId, id);
    assert.equal(kept?.revision, withGray.revision);
  } finally {
    await allowPreviewPrefs();
  }
  await deletePalette(id);
  const loaded = await getVariant(variant.id);
  assert.equal(loaded?.settings.paletteId, 0);
});

test("variant update shape validation rejects without touching state", async () => {
  const font = await saveFixture();
  const before = await createVariant(font.id, { name: "Shape" });
  await assert.rejects(updateVariant(before.id, null as never, before.revision), /changes object/);
  await assert.rejects(updateVariant(before.id, [] as never, before.revision), /changes object/);
  await assert.rejects(updateVariant(before.id, { name: "Ok" }, 1.5), /integer expected revision/);
  await assert.rejects(updateVariant(before.id, { name: "  " }, before.revision), /variant name/i);
  const kept = await getVariant(before.id);
  assert.equal(kept?.revision, before.revision);
  assert.equal(kept?.name, "Shape");
});

test("sample-only updates pin the inherit flag explicitly", async () => {
  const font = await saveFixture();
  const before = await createVariant(font.id, { name: "Sample" });
  const flagged = await updateVariant(before.id, { inheritSampleText: true }, before.revision);
  assert.equal(flagged.inheritSampleText, true);
  assert.equal(flagged.sampleText, "Pack my box with five dozen liquor jugs.");
  const replaced = await updateVariant(flagged.id, { sampleText: "custom" }, flagged.revision);
  assert.equal(replaced.sampleText, "custom");
  assert.equal(replaced.inheritSampleText, false);
});

test("fitting flags persist through the split entities", async () => {
  const font = await saveFixture();
  const before = await createVariant(font.id, { name: "Fit" });
  const updated = await updateVariant(
    before.id,
    {
      settings: {
        ...before.settings,
        stemFitting: "upstream_mono",
        diagonalFitting: true,
      },
    },
    before.revision,
  );
  assert.equal(updated.settings.stemFitting, "upstream_mono");
  assert.equal(updated.settings.diagonalFitting, true);
  assert.equal((await getVariant(before.id))?.settings.diagonalFitting, true);
});

test("creation wires an explicit name, settings, sample and palette", async () => {
  const font = await saveFixture();
  const id = await createPalette();
  const created = await createVariant(font.id, {
    name: "Full",
    settings: { ...((await createVariant(font.id, { name: "Template" })).settings), paletteId: id, profile: "gray_2bit", rasterization: "coverage" },
    sampleText: "hello",
    inheritSampleText: true,
  });
  assert.equal(created.name, "Full");
  assert.equal(created.settings.paletteId, id);
  assert.equal(created.settings.profile, "gray_2bit");
  assert.equal(created.sampleText, "hello");
  assert.equal(created.inheritSampleText, true);
});

test("palette validation rejects bad presets without touching state", async () => {
  const id = await createPalette();
  const before = (await listPalettes()).find((preset) => preset.id === id);
  assert.ok(before);
  await assert.rejects(updatePalette(id, { name: "" }), /non-empty text/);
  await assert.rejects(updatePalette(id, { name: "x".repeat(121) }), /non-empty text/);
  await assert.rejects(
    updatePalette(id, { curve: () => [{ value: 0, slope: 1, pinned: true }] as never }),
    /Invalid palette preset/,
  );
  await assert.rejects(deletePalette(999999), /deleted/);
  const kept = (await listPalettes()).find((preset) => preset.id === id);
  assert.deepEqual(kept, before);
  await deletePalette(id);
});
