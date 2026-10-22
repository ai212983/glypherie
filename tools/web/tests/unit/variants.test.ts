import "fake-indexeddb/auto";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test, { beforeEach } from "node:test";
import { createPalette, updatePalette } from "../../src/app/palettes/repository.ts";
import { linearCurve } from "../../src/app/features/grayscale/response-curve.ts";
import Dexie, { type Table } from "dexie";
import {
  fontDatabase,
  getFont,
  listFonts,
  removeFont,
  saveFont,
  type AxisMetadata,
  type FontMetadata,
  type StoredFont,
} from "../../src/app/fonts/storage.ts";
import type { VariantRow } from "../../src/app/database.ts";
import { TEXT_DEFAULT } from "../../src/app/renderer/render-spec.ts";
import {
  defaultVariantSettings,
  VARIANT_SAMPLE_TEXT_MAX_LENGTH,
  validateVariantSettings,
  VariantStorageError,
} from "../../src/app/variants/model.ts";
import {
  createVariant,
  deleteVariant,
  getVariant,
  listVariants,
  updateVariant,
  type VariantChanges,
} from "../../src/app/variants/repository.ts";

Dexie.dependencies.indexedDB = globalThis.indexedDB;
Dexie.dependencies.IDBKeyRange = globalThis.IDBKeyRange;

const sha256 = (bytes: ArrayBuffer): string =>
  createHash("sha256").update(Buffer.from(bytes)).digest("hex");
const fontBytes = (seed = 0): ArrayBuffer =>
  Uint8Array.from({ length: 64 }, (_, i) => (i * 7 + seed) % 251).buffer as ArrayBuffer;

function metadata(): FontMetadata {
  return {
    names: { family: "Fixture" },
    axes: [{ tag: "wght", name: "Weight", min: 100, default: 400, max: 900, hidden: false }],
  };
}

function metadataWithAxes(axes: AxisMetadata[]): FontMetadata {
  return { names: { family: "Fixture" }, axes };
}

async function saveFixture(seed = 0, meta: FontMetadata = metadata()): Promise<StoredFont> {
  return saveFont({ bytes: fontBytes(seed), fileName: "fixture.ttf", name: "Fixture", metadata: meta, source: "uploaded" });
}

async function assertRejectsCode(
  operation: Promise<unknown>,
  code: VariantStorageError["code"],
): Promise<void> {
  await assert.rejects(
    operation,
    (error) => error instanceof VariantStorageError && error.code === code,
    `expected VariantStorageError ${code}`,
  );
}

beforeEach(async () => {
  await fontDatabase.close();
  await Dexie.delete("font-library");
  assert.equal((await listVariants()).length, 0);
});

test("imported fonts start with no variants; Add creates a default saved variant", async () => {
  const font = await saveFixture();
  assert.deepEqual(await listVariants(font.id), []);
  assert.deepEqual(await listVariants(), []);

  const variant = await createVariant(font.id);
  assert.equal(variant.fontId, font.id);
  assert.equal(variant.name, "Variant 1");
  assert.equal(variant.settingsVersion, 1);
  assert.equal(variant.revision, 1);
  assert.deepEqual(variant.settings, {
    sizePx: 16,
    axes: { wght: 400 },
    letterSpacingPx: 0,
    profile: "mono_1bit",
    paletteId: 0,
    kerning: true,
    stemFitting: "font_hints_first",
    diagonalFitting: false,
    monoRaster: { dropout: "smart", includeStubs: true, fontInstructions: true },
    renderer: "candidate",
    rasterization: "free_type_mono",
  });
  assert.equal(variant.sampleText, TEXT_DEFAULT);
  assert.equal(variant.inheritSampleText, true);
  assert.ok(variant.createdAt > 0);
  assert.equal(variant.updatedAt, variant.createdAt);
  assert.match(variant.id, /^[0-9a-f-]{36}$/);

  assert.deepEqual(await getVariant(variant.id), variant);
  assert.equal(await getVariant("00000000-0000-0000-0000-000000000000"), undefined);
  assert.deepEqual((await listVariants(font.id)).map((entry) => entry.id), [variant.id]);
});

test("sample text inheritance persists while explicit and historical text remain independent", async () => {
  const font = await saveFixture();
  const inherited = await createVariant(font.id);
  const override = await updateVariant(inherited.id, { sampleText: "" }, inherited.revision);
  assert.equal(override.inheritSampleText, false, "empty text is an explicit override");
  const reset = await updateVariant(override.id, { inheritSampleText: true }, override.revision);
  assert.equal((await getVariant(reset.id))?.inheritSampleText, true);
  assert.deepEqual(reset.settings, override.settings, "resetting inheritance preserves settings");

  const explicit = await createVariant(font.id, { sampleText: TEXT_DEFAULT });
  assert.equal(explicit.inheritSampleText, false, "text matching a default is still an override");
  await fontDatabase.variants.update(explicit.id, { inheritSampleText: undefined });
  assert.equal((await getVariant(explicit.id))?.inheritSampleText, false, "historical rows preserve saved text");
  const renamed = await updateVariant(explicit.id, { name: "Historical" }, explicit.revision);
  assert.equal(renamed.inheritSampleText, false);
  assert.equal(renamed.sampleText, TEXT_DEFAULT);

  await assertRejectsCode(createVariant(font.id, { inheritSampleText: "yes" as never }), "invalid-input");
  await assertRejectsCode(updateVariant(reset.id, { inheritSampleText: "yes" as never }, reset.revision), "invalid-input");
});

test("default settings carry hidden axes and static fonts yield axes={}", () => {
  const variable = defaultVariantSettings({
    id: "font",
    name: "F",
    fileName: "f.ttf",
    bytes: new ArrayBuffer(8),
    metadata: metadataWithAxes([
      { tag: "wght", name: "Weight", min: 100, default: 400, max: 900, hidden: false },
      { tag: "opsz", name: null, min: 8, default: 14, max: 144, hidden: true },
    ]),
    source: "uploaded",
    addedAt: 0,
  });
  assert.deepEqual(variable.axes, { wght: 400, opsz: 14 });

  const staticFont = defaultVariantSettings({
    id: "font",
    name: "F",
    fileName: "f.ttf",
    bytes: new ArrayBuffer(8),
    metadata: metadataWithAxes([]),
    source: "uploaded",
    addedAt: 0,
  });
  assert.deepEqual(staticFont.axes, {});
});

test("retired Mono renderer and coverage choices migrate to the current preview pipeline", async () => {
  const font = await saveFixture();
  const base = defaultVariantSettings(font);
  for (const renderer of ["candidate", "baseline", "reference"] as const) {
    const settings = { ...base, rasterization: undefined, renderer, letterSpacingPx: 2 };
    const variant = await createVariant(font.id, { settings });
    const loaded = await getVariant(variant.id);
    assert.equal(loaded?.settings.rasterization, "free_type_mono");
    assert.equal(loaded?.settings.renderer, "candidate");
    assert.equal(loaded?.settings.letterSpacingPx, 2, "saved extra tracking survives the pipeline migration");
  }
  const variant = await createVariant(font.id, { settings: { ...base, rasterization: "coverage", stemFitting: "upstream_mono" } });
  assert.equal((await getVariant(variant.id))?.settings.rasterization, "free_type_mono");
  assert.equal((await getVariant(variant.id))?.settings.stemFitting, "upstream_mono");
});

test("undefined grayscale output falls back to Monochrome without changing font inputs", async () => {
  const font = await saveFixture();
  const settings = { ...defaultVariantSettings(font), profile: "gray_3bit" as const,
    rasterization: undefined, renderer: "reference" as const, letterSpacingPx: 2 };
  const variant = await createVariant(font.id, { settings });
  const loaded = await getVariant(variant.id);
  assert.equal(loaded?.settings.renderer, "candidate");
  assert.equal(loaded?.settings.rasterization, "free_type_mono");
  assert.equal(loaded?.settings.paletteId, 0);
  assert.equal(loaded?.settings.letterSpacingPx, 2);
  assert.deepEqual(loaded?.settings.axes, settings.axes);
});

test("default names sequence per font and renames allow duplicates", async () => {
  const first = await saveFixture(1);
  const second = await saveFixture(2);
  const a = await createVariant(first.id);
  const b = await createVariant(first.id);
  const other = await createVariant(second.id);
  assert.equal(a.name, "Variant 1");
  assert.equal(b.name, "Variant 2");
  assert.equal(other.name, "Variant 1");

  const renamed = await updateVariant(b.id, { name: "Custom" }, b.revision);
  assert.equal(renamed.name, "Custom");
  const duplicate = await updateVariant(a.id, { name: "Custom" }, a.revision);
  assert.equal(duplicate.name, "Custom");

  await deleteVariant(renamed.id);
  // Creation counts inside the transaction: one row remains, so the next
  // default reuses the stable "Variant 2" slot.
  const c = await createVariant(first.id);
  assert.equal(c.name, "Variant 2");
});

test("two variants of one font stay independent", async () => {
  const font = await saveFixture();
  const a = await createVariant(font.id);
  const b = await createVariant(font.id);
  const moved = await updateVariant(
    a.id,
    { settings: { ...a.settings, axes: { wght: 700 }, sizePx: 24 } },
    a.revision,
  );
  assert.equal(moved.revision, 2);
  assert.deepEqual(moved.settings.axes, { wght: 700 });
  assert.deepEqual((await getVariant(b.id))?.settings.axes, { wght: 400 });
  assert.equal((await getVariant(b.id))?.revision, 1);
  assert.equal((await getVariant(b.id))?.settings.sizePx, 16);
});

test("stored settings are copies, not aliases of the caller's objects", async () => {
  const font = await saveFixture();
  const settings = defaultVariantSettings(font);
  const created = await createVariant(font.id, { settings });
  settings.axes["wght"] = 900;
  settings.sizePx = 512;
  const stored = await getVariant(created.id);
  assert.deepEqual(stored?.settings.axes, { wght: 400 });
  assert.equal(stored?.settings.sizePx, 16);
});

test("fonts with disjoint tags and different ranges of one tag work", async () => {
  const narrow = await saveFixture(21, metadataWithAxes([
    { tag: "wght", name: "Weight", min: 200, default: 500, max: 700, hidden: false },
  ]));
  const wide = await saveFixture(22, metadataWithAxes([
    { tag: "wdth", name: "Width", min: 50, default: 100, max: 200, hidden: false },
    { tag: "opsz", name: null, min: 8, default: 14, max: 144, hidden: true },
  ]));
  const narrowVariant = await createVariant(narrow.id);
  const wideVariant = await createVariant(wide.id);
  assert.deepEqual(narrowVariant.settings.axes, { wght: 500 });
  assert.deepEqual(wideVariant.settings.axes, { wdth: 100, opsz: 14 });

  await assertRejectsCode(
    createVariant(wide.id, { settings: narrowVariant.settings }),
    "invalid-settings",
  );
  await assertRejectsCode(
    createVariant(narrow.id, {
      settings: { ...narrowVariant.settings, axes: { wght: 800 } },
    }),
    "invalid-settings",
  );
  const moved = await updateVariant(
    narrowVariant.id,
    { settings: { ...narrowVariant.settings, axes: { wght: 200 } } },
    narrowVariant.revision,
  );
  assert.deepEqual(moved.settings.axes, { wght: 200 });
});

test("saved settings reject unknown, missing, NaN, and out-of-range axes", async () => {
  const font = await saveFixture();
  const base = defaultVariantSettings(font);
  const badAxes: Record<string, number>[] = [
    { wght: 400, extra: 1 },
    {},
    { wght: Number.NaN },
    { wght: 99 },
    { wght: 901 },
  ];
  for (const axes of badAxes) {
    await assertRejectsCode(
      createVariant(font.id, { settings: { ...base, axes } }),
      "invalid-settings",
    );
  }
  assert.deepEqual(await listVariants(font.id), []);

  const created = await createVariant(font.id);
  for (const axes of badAxes) {
    await assertRejectsCode(
      updateVariant(created.id, { settings: { ...base, axes } }, created.revision),
      "invalid-settings",
    );
  }
  assert.deepEqual((await getVariant(created.id))?.settings.axes, { wght: 400 });
});

test("saved settings validate numeric bounds and enum values", async () => {
  const font = await saveFixture();
  const base = defaultVariantSettings(font);
  const bad = [
    { ...base, sizePx: 0 },
    { ...base, sizePx: 513 },
    { ...base, sizePx: Number.POSITIVE_INFINITY },
    { ...base, letterSpacingPx: -2.5 },
    { ...base, letterSpacingPx: 4.5 },
    { ...base, profile: "hdr" },
    { ...base, kerning: 1 },
    { ...base, stemFitting: "auto" },
    { ...base, monoRaster: { dropout: "cleartype", includeStubs: false, fontInstructions: false } },
    { ...base, monoRaster: { dropout: "smart", includeStubs: "yes", fontInstructions: false } },
    { ...base, monoRaster: { dropout: "smart", includeStubs: false, fontInstructions: "yes" } },
    { ...base, monoRaster: "smart" },
    { ...base, renderer: "preview" },
    { ...base, rasterization: "unknown" },
    { ...base, renderer: "baseline" },
  ];
  for (const settings of bad) {
    await assertRejectsCode(
      createVariant(font.id, { settings: settings as never }),
      "invalid-settings",
    );
  }
  validateVariantSettings({ ...base, rasterization: undefined, sizePx: 1, letterSpacingPx: -2 }, metadata());
  validateVariantSettings({ ...base, rasterization: undefined, sizePx: 512, letterSpacingPx: 4 }, metadata());
  validateVariantSettings({ ...base, letterSpacingPx: -2 }, metadata());
  validateVariantSettings({ ...base, letterSpacingPx: 4 }, metadata());
  validateVariantSettings({ ...base, profile: "gray_3bit", letterSpacingPx: 3 }, metadata());
});

test("nonzero extra tracking round-trips for 1-bit and 3-bit, zero stays the default", async () => {
  const font = await saveFixture();
  const base = defaultVariantSettings(font);
  assert.equal(base.letterSpacingPx, 0);
  const mono = await createVariant(font.id, { settings: { ...base, letterSpacingPx: 2 } });
  assert.equal((await getVariant(mono.id))?.settings.letterSpacingPx, 2);
  const gray = await createVariant(font.id, {
    settings: { ...base, profile: "gray_3bit", letterSpacingPx: -2 },
  });
  assert.equal((await getVariant(gray.id))?.settings.letterSpacingPx, -2);
  const stored = await createVariant(font.id);
  assert.equal((await getVariant(stored.id))?.settings.letterSpacingPx, 0);
});

test("tracking edits survive palette and fitting changes", async () => {
  const paletteId = await createPalette();
  await updatePalette(paletteId, { curve: () => linearCurve(8) });
  const font = await saveFixture();
  const base = defaultVariantSettings(font);
  const created = await createVariant(font.id, { settings: { ...base, letterSpacingPx: 3 } });
  const gray = await updateVariant(
    created.id,
    { settings: { ...created.settings, paletteId, profile: "gray_3bit", stemFitting: "upstream_mono" } },
    created.revision,
  );
  assert.equal(gray.settings.letterSpacingPx, 3);
  assert.equal(gray.settings.profile, "gray_3bit");
  const back = await updateVariant(
    gray.id,
    { settings: { ...gray.settings, paletteId: 0, profile: "mono_1bit", stemFitting: "font_hints_first" } },
    gray.revision,
  );
  assert.equal(back.settings.letterSpacingPx, 3);
  assert.deepEqual((await getVariant(back.id))?.settings, back.settings);
});

test("legacy storage validation fills absent scan fields", async () => {
  const font = await saveFixture();
  const legacy = { ...defaultVariantSettings(font) } as Record<string, unknown>;
  delete legacy.monoRaster;
  validateVariantSettings(legacy as never, metadata());
  assert.deepEqual(legacy.monoRaster, { dropout: "smart", includeStubs: false, fontInstructions: false });
});

test("legacy scan settings validate but Mono previews use the fixed policy", async () => {
  const font = await saveFixture();
  const settings = defaultVariantSettings(font);
  // Phase-1 rows carry manual choices but no font-instructions flag.
  const legacy = { ...settings, monoRaster: { dropout: "off", includeStubs: true } as never };
  validateVariantSettings(legacy as never, metadata());
  assert.deepEqual(legacy.monoRaster, { dropout: "off", includeStubs: true, fontInstructions: false });
  const stored = await createVariant(font.id, { settings: legacy as never });
  assert.deepEqual(stored.settings.monoRaster, { dropout: "smart", includeStubs: true, fontInstructions: true });
  assert.deepEqual((await getVariant(stored.id))?.settings.monoRaster, {
    dropout: "smart", includeStubs: true, fontInstructions: true,
  });
});

test("names and sample text have explicit limits", async () => {
  const font = await saveFixture();
  await assertRejectsCode(createVariant(font.id, { name: "   " }), "invalid-input");
  await assertRejectsCode(createVariant(font.id, { name: "x".repeat(121) }), "invalid-input");
  await assertRejectsCode(
    createVariant(font.id, { sampleText: "x".repeat(VARIANT_SAMPLE_TEXT_MAX_LENGTH + 1) }),
    "invalid-input",
  );
  const created = await createVariant(font.id);
  await assertRejectsCode(updateVariant(created.id, { name: "" }, created.revision), "invalid-input");
  await assertRejectsCode(
    updateVariant(created.id, { sampleText: "x".repeat(VARIANT_SAMPLE_TEXT_MAX_LENGTH + 1) }, created.revision),
    "invalid-input",
  );
  assert.deepEqual((await listVariants(font.id)).length, 1);
});

test("creating a variant for a missing font fails without writing", async () => {
  await assertRejectsCode(createVariant("f".repeat(64)), "font-not-found");
  assert.deepEqual(await listVariants(), []);
});

test("revision conflicts reject stale writes, including concurrent ones", async () => {
  const font = await saveFixture();
  const created = await createVariant(font.id);
  await assertRejectsCode(updateVariant(created.id, { name: "Stale" }, created.revision + 1), "conflict");

  const readers = [await getVariant(created.id), await getVariant(created.id)];
  assert.ok(readers[0] && readers[1]);
  const outcomes = await Promise.allSettled([
    updateVariant(created.id, { name: "First writer" }, readers[0].revision),
    updateVariant(created.id, { name: "Second writer" }, readers[1].revision),
  ]);
  const fulfilled = outcomes.filter((outcome) => outcome.status === "fulfilled");
  const rejected = outcomes.filter((outcome) => outcome.status === "rejected");
  assert.equal(fulfilled.length, 1);
  assert.equal(rejected.length, 1);
  const reason = (rejected[0] as PromiseRejectedResult).reason;
  assert.ok(reason instanceof VariantStorageError && reason.code === "conflict");

  const current = await getVariant(created.id);
  assert.ok(current);
  assert.equal(current.revision, created.revision + 1);
  const repaired = await updateVariant(created.id, { name: "Fresh write" }, current.revision);
  assert.equal(repaired.revision, current.revision + 1);
  assert.equal(repaired.name, "Fresh write");
});

test("a second database connection sees repository writes", async (t) => {
  class SecondConnection extends Dexie {
    fonts!: Table<StoredFont, string>;
    meta!: Table<{ key: string; value: string }, string>;
    variants!: Table<VariantRow, string>;
    constructor() {
      super("font-library");
      this.version(1).stores({ fonts: "id, addedAt, source", meta: "key" });
      this.version(2).stores({ fonts: "id, addedAt, source", meta: "key", variants: "id, fontId" });
    }
  }
  const peer = new SecondConnection();
  t.after(() => peer.close());
  const font = await saveFixture();
  const created = await createVariant(font.id);
  const seen = await peer.variants.get(created.id);
  assert.equal(seen?.fontId, font.id);
  assert.equal(seen?.revision, 1);
  await peer.close();
});

test("competing same-revision writes through two connections leave one conflict", async (t) => {
  class PeerDatabase extends Dexie {
    fonts!: Table<StoredFont, string>;
    meta!: Table<{ key: string; value: string }, string>;
    variants!: Table<VariantRow, string>;
    constructor() {
      super("font-library");
      this.version(1).stores({ fonts: "id, addedAt, source", meta: "key" });
      this.version(2).stores({ fonts: "id, addedAt, source", meta: "key", variants: "id, fontId" });
    }
  }
  const peer = new PeerDatabase();
  t.after(() => peer.close());
  const font = await saveFixture();
  const created = await createVariant(font.id);
  assert.equal(created.revision, 1);

  // Raw peer transaction with the repository's read-compare-write semantics;
  // the repository API intentionally stays singleton, so the second writer
  // path is spelled out here instead of through a second repository.
  const peerWrite = peer.transaction("rw", [peer.fonts, peer.variants], async () => {
    const existing = await peer.variants.get(created.id);
    if (!existing) throw new VariantStorageError("not-found", `Variant "${created.id}" does not exist.`);
    if (existing.revision !== created.revision) {
      throw new VariantStorageError(
        "conflict",
        `Variant "${created.id}" changed underneath this edit (expected revision ${created.revision}, found ${existing.revision}).`,
      );
    }
    const next: VariantRow = {
      ...existing,
      name: "Peer writer",
      revision: existing.revision + 1,
      updatedAt: Date.now(),
    };
    await peer.variants.put(next);
    return next;
  });
  const repositoryWrite = updateVariant(created.id, { name: "Repository writer" }, created.revision);
  const outcomes = await Promise.allSettled([peerWrite, repositoryWrite]);
  const fulfilled = outcomes.filter((outcome) => outcome.status === "fulfilled");
  const rejected = outcomes.filter((outcome) => outcome.status === "rejected");
  assert.equal(fulfilled.length, 1);
  assert.equal(rejected.length, 1);
  const reason = (rejected[0] as PromiseRejectedResult).reason;
  assert.ok(reason instanceof VariantStorageError && reason.code === "conflict");

  const current = await getVariant(created.id);
  assert.equal(current?.revision, 2);
  await peer.close();
});

test("parent and identity stay immutable through updates", async () => {
  const font = await saveFixture();
  const created = await createVariant(font.id);
  const changes = { name: "Renamed", fontId: "0".repeat(64), id: "other" } as unknown as VariantChanges;
  const updated = await updateVariant(created.id, changes, created.revision);
  assert.equal(updated.id, created.id);
  assert.equal(updated.fontId, font.id);
  assert.equal(updated.name, "Renamed");
  assert.deepEqual((await listVariants("0".repeat(64))), []);
});

test("deleting a variant removes only that variant", async () => {
  const font = await saveFixture();
  const a = await createVariant(font.id);
  const b = await createVariant(font.id);
  await deleteVariant(a.id);
  assert.equal(await getVariant(a.id), undefined);
  assert.deepEqual((await listVariants(font.id)).map((entry) => entry.id), [b.id]);

  await assertRejectsCode(deleteVariant(a.id), "not-found");
  await assertRejectsCode(deleteVariant(b.id, b.revision + 1), "conflict");
  const renamed = await updateVariant(b.id, { name: "Kept" }, b.revision);
  await deleteVariant(b.id, renamed.revision);
  assert.deepEqual(await listVariants(font.id), []);
});

test("removing a font deletes its variants atomically and keeps others", async () => {
  const first = await saveFixture(31);
  const second = await saveFixture(32);
  const doomed = [await createVariant(first.id), await createVariant(first.id)];
  const kept = await createVariant(second.id);

  await removeFont(first.id);
  assert.equal(await getFont(first.id), undefined);
  assert.deepEqual(await listVariants(first.id), []);
  for (const variant of doomed) {
    assert.equal(await getVariant(variant.id), undefined);
  }
  assert.deepEqual(await getVariant(kept.id), kept);
  assert.deepEqual((await listFonts()).map((font) => font.id), [second.id]);
});

test("a stale update cannot resurrect a deleted variant", async () => {
  const font = await saveFixture();
  const created = await createVariant(font.id);
  await deleteVariant(created.id);
  await assertRejectsCode(
    updateVariant(created.id, { name: "Ghost" }, created.revision),
    "not-found",
  );
  assert.equal(await getVariant(created.id), undefined);
  assert.deepEqual(await listVariants(font.id), []);
});

test("a stale update after removeFont cascade cannot resurrect the variant", async () => {
  const font = await saveFixture(61);
  const created = await createVariant(font.id);
  await removeFont(font.id);
  assert.equal(await getFont(font.id), undefined);
  await assertRejectsCode(
    updateVariant(created.id, { name: "Ghost" }, created.revision),
    "not-found",
  );
  assert.equal(await getVariant(created.id), undefined);
  assert.deepEqual(await listVariants(font.id), []);
  assert.deepEqual(await listVariants(), []);
});

test("settings writes never copy or alter font binaries", async () => {
  const font = await saveFixture(41);
  const before = sha256(font.bytes.slice(0));
  const created = await createVariant(font.id);
  await updateVariant(
    created.id,
    { settings: { ...created.settings, sizePx: 32, axes: { wght: 900 } } },
    created.revision,
  );
  const after = await getFont(font.id);
  assert.ok(after);
  assert.equal(sha256(after.bytes.slice(0)), before);
  assert.deepEqual(after.metadata, font.metadata);
});

test("v1 databases upgrade with fonts and seed marker retained, variants empty", async (t) => {
  class LegacyDatabase extends Dexie {
    fonts!: Table<StoredFont, string>;
    meta!: Table<{ key: string; value: string }, string>;
    constructor() {
      super("font-library");
      this.version(1).stores({ fonts: "id, addedAt, source", meta: "key" });
    }
  }
  // beforeEach leaves an empty v2 database behind via its listVariants check;
  // drop it so this test builds a genuine v1 database from scratch.
  await fontDatabase.close();
  await Dexie.delete("font-library");

  const legacy = new LegacyDatabase();
  t.after(() => legacy.close());
  await legacy.open();
  assert.equal(legacy.verno, 1);
  const bytes = fontBytes(51);
  const id = sha256(bytes);
  await legacy.fonts.add({
    id,
    name: "Legacy",
    fileName: "legacy.ttf",
    bytes,
    metadata: metadata(),
    source: "uploaded",
    addedAt: 123,
  });
  await legacy.meta.put({ key: "bundled-fonts", value: "legacy-marker" });
  await legacy.close();

  await fontDatabase.open();
  assert.equal(fontDatabase.verno, 3);
  const fonts = await listFonts();
  assert.deepEqual(fonts.map((font) => font.id), [id]);
  assert.deepEqual(Buffer.from(fonts[0]?.bytes ?? new ArrayBuffer(0)), Buffer.from(bytes));
  assert.equal((await fontDatabase.meta.get("bundled-fonts"))?.value, "legacy-marker");
  assert.deepEqual(await listVariants(), []);

  const variant = await createVariant(id);
  assert.equal(variant.fontId, id);
  assert.equal(variant.name, "Variant 1");
});
