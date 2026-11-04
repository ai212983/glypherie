// Safe legacy import coverage: byte-identical reruns, failure atomicity and
// interrupted-import recovery, against the real PGlite/TypeGraph store with
// legacy fixtures in fake-indexedDB Dexie.

import "fake-indexeddb/auto";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test, { after, beforeEach, mock } from "node:test";
import Dexie from "dexie";
import { createStore } from "@nicia-ai/typegraph";
import { createPostgresBackend } from "@nicia-ai/typegraph/adapters/drizzle/postgres";
import { fontDatabase } from "../../src/app/database.ts";
import { kvGet, kvPut, readBinary, writeBinaryIfAbsent, type AuxDb } from "../../src/app/domain/backend.ts";
import { domainGraph } from "../../src/app/domain/graph.ts";
import { importLegacySnapshot } from "../../src/app/domain/importer.ts";
import { ensureDomainMigrated } from "../../src/app/domain/migrate.ts";
import { callDomain } from "../../src/app/domain/runtime.ts";
import { getBackend, closeDomainForTests, resetDomainForTests } from "../../src/app/domain/node-backend.ts";
import { readLegacySnapshot, type LegacySnapshot } from "../../src/app/legacy-database.ts";
import { getFont, listFonts } from "../../src/app/fonts/storage.ts";
import { linearCurve } from "../../src/app/features/grayscale/response-curve.ts";
import { getVariant, listVariants, updateVariant } from "../../src/app/variants/repository.ts";
import { defaultVariantSettings } from "../../src/app/variants/model.ts";
import type { FontMetadata } from "../../src/app/fonts/storage.ts";

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

function metadata(): FontMetadata {
  return {
    names: { family: "Fixture" },
    axes: [{ tag: "wght", name: "Weight", min: 100, default: 400, max: 900, hidden: false }],
  };
}

const fontBytes = (seed = 0): ArrayBuffer =>
  Uint8Array.from({ length: 64 }, (_, i) => (i * 7 + seed) % 251).buffer as ArrayBuffer;

const sha256 = (bytes: ArrayBuffer): string =>
  createHash("sha256").update(Buffer.from(bytes)).digest("hex");

async function seedLegacy(): Promise<{ fontId: string; bytes: ArrayBuffer }> {
  const bytes = fontBytes(7);
  const fontId = sha256(bytes);
  await fontDatabase.fonts.add({
    id: fontId,
    name: "Legacy",
    fileName: "legacy.ttf",
    bytes,
    metadata: metadata(),
    source: "uploaded",
    addedAt: 11,
  });
  // put (not add): fake-indexeddb rejects explicit key 0 on a fresh auto-increment
  // store while real IndexedDB accepts it; legacy production rows carry id 0.
  await fontDatabase.palettes.put({ id: 0, name: "Monochrome", curve: linearCurve(2) });
  await fontDatabase.palettes.put({ id: 1, name: "Gray", curve: linearCurve(4) });
  await fontDatabase.variants.add({
    id: "variant-1",
    fontId,
    name: "Legacy V",
    settingsVersion: 1,
    settings: {
      ...defaultVariantSettings({ id: fontId, metadata: metadata() } as never),
      sizePx: 20,
      paletteId: 1,
      profile: "gray_2bit",
      rasterization: "coverage",
    },
    sampleText: "Hello",
    inheritSampleText: false,
    revision: 4,
    createdAt: 5,
    updatedAt: 6,
  });
  await fontDatabase.meta.put({ key: "bundled-fonts", value: "seed-rows" });
  return { fontId, bytes };
}

test("import preserves every legacy row and reruns as a byte-identical no-op", async () => {
  const { fontId, bytes } = await seedLegacy();
  const first = await importLegacySnapshot(getBackend(), await readLegacySnapshot());
  assert.equal(first.skipped, false);
  assert.deepEqual([first.fonts, first.variants, first.palettes], [1, 1, 2]);
  assert.deepEqual(first.skippedVariantIds, []);

  const font = await getFont(fontId);
  assert.ok(font);
  assert.equal(font.name, "Legacy");
  assert.equal(font.source, "uploaded");
  assert.equal(font.addedAt, 11);
  assert.deepEqual(font.metadata, metadata());
  assert.deepEqual(Buffer.from(font.bytes), Buffer.from(bytes));

  const variant = await getVariant("variant-1");
  assert.ok(variant);
  assert.equal(variant.fontId, fontId);
  assert.equal(variant.revision, 4);
  assert.equal(variant.createdAt, 5);
  assert.equal(variant.sampleText, "Hello");
  assert.equal(variant.inheritSampleText, false);
  assert.equal(variant.settings.sizePx, 20);
  assert.equal(variant.settings.paletteId, 1);
  assert.equal(variant.settings.profile, "gray_2bit");
  assert.equal((await listFonts()).length, 1);
  assert.equal(await callDomain("getSeedMarker", []), "seed-rows");

  const before = await readBinary(getBackend().db, fontId);
  const second = await importLegacySnapshot(getBackend(), await readLegacySnapshot());
  assert.equal(second.skipped, true);
  assert.deepEqual([second.fonts, second.variants, second.palettes], [0, 0, 0]);
  assert.deepEqual(await readBinary(getBackend().db, fontId), before);
  assert.deepEqual(await getVariant("variant-1"), variant);
  assert.deepEqual(await listVariants(), [variant]);
});

test("a failed import writes no marker and leaves no readable partial state", async () => {
  const { fontId } = await seedLegacy();
  const snapshot = await readLegacySnapshot();
  // fontSize passes the policy normalizers but violates the graph schema, so
  // the failure lands mid-transaction, after binaries and before the marker.
  const tampered: LegacySnapshot = {
    ...snapshot,
    variants: snapshot.variants.map((variant) => ({
      ...variant,
      settings: { ...variant.settings, sizePx: -5 },
    })),
  };
  await assert.rejects(importLegacySnapshot(getBackend(), tampered), /fontSize|greater than or equal to 1/i);
  assert.equal(await callDomain("getSeedMarker", []).catch(() => undefined), undefined);
  assert.equal(await kvGet(getBackend().db, "import:legacy:v1"), undefined);
  assert.deepEqual(await listVariants(), []);
  assert.equal(await getFont(fontId), undefined);

  // Fixing the row lets the interrupted import run to completion.
  const repaired = await importLegacySnapshot(getBackend(), snapshot);
  assert.equal(repaired.skipped, false);
  assert.ok(await getVariant("variant-1"));
});

test("tampered legacy bytes fail loudly instead of storing under a wrong id", async () => {
  await seedLegacy();
  const snapshot = await readLegacySnapshot();
  const tampered: LegacySnapshot = {
    ...snapshot,
    fonts: snapshot.fonts.map((font) => ({ ...font, bytes: fontBytes(99) })),
  };
  await assert.rejects(importLegacySnapshot(getBackend(), tampered), /do not match their content id/);
  assert.deepEqual(await listFonts(), []);
});

test("a variant of a missing font fails the whole import atomically", async () => {
  await seedLegacy();
  const snapshot = await readLegacySnapshot();
  const orphaned: LegacySnapshot = {
    ...snapshot,
    variants: snapshot.variants.map((variant) => ({ ...variant, fontId: "0".repeat(64) })),
  };
  // The orphan throws mid-transaction, after fonts and binaries landed: every
  // store must roll back together, leaving no marker and no residue.
  await assert.rejects(importLegacySnapshot(getBackend(), orphaned), /missing font/);
  assert.equal(await kvGet(getBackend().db, "import:legacy:v1"), undefined);
  assert.equal(await kvGet(getBackend().db, "preview:variant-1"), undefined);
  assert.equal(await callDomain("getSeedMarker", []).catch(() => undefined), undefined);
  assert.equal(await readBinary(getBackend().db, snapshot.fonts[0]!.id), undefined);
  assert.deepEqual(await listFonts(), []);
  assert.deepEqual(await listVariants(), []);
  assert.equal(await getVariant("variant-1"), undefined);

  // Repairing the snapshot (the font the variant needs) retries to completion.
  const repaired = await importLegacySnapshot(getBackend(), snapshot);
  assert.equal(repaired.skipped, false);
  assert.deepEqual([repaired.fonts, repaired.variants, repaired.palettes], [1, 1, 2]);
  assert.ok(await getVariant("variant-1"));
});

test("a fault after every store wrote still rolls back binaries, graph, prefs and markers", async () => {
  const backend = getBackend();
  await assert.rejects(
    backend.db.transaction(async (txDb) => {
      const tx = txDb as unknown as AuxDb;
      await writeBinaryIfAbsent(tx, "ab".repeat(32), new Uint8Array([1, 2, 3]));
      const txStore = createStore(
        domainGraph,
        createPostgresBackend(txDb as never, { vector: false, fulltext: false }),
      );
      await txStore.transaction(async (graphTx) => {
        await graphTx.nodes.Font.create(
          { name: "Doomed", fileName: "doomed.ttf", metadata: metadata() as never, source: "uploaded", addedAt: 1 },
          { id: "ab".repeat(32) },
        );
      });
      await kvPut(tx, "preview:doomed", JSON.stringify({ sampleText: "x" }));
      await kvPut(tx, "import:legacy:v1", JSON.stringify({ status: "complete" }));
      // Prove the writes landed before the fault: all four stores read back
      // inside the same transaction.
      assert.ok(await readBinary(tx, "ab".repeat(32)));
      assert.equal(await kvGet(tx, "preview:doomed"), JSON.stringify({ sampleText: "x" }));
      const seen = await txStore.nodes.Font.getById("ab".repeat(32) as never).catch(() => undefined);
      assert.ok(seen);
      throw new Error("injected fault after every store wrote");
    }),
    /injected fault/,
  );
  // After the abort none of the four stores shows the import.
  assert.equal(await readBinary(backend.db, "ab".repeat(32)), undefined);
  assert.equal(await kvGet(backend.db, "preview:doomed"), undefined);
  assert.equal(await kvGet(backend.db, "import:legacy:v1"), undefined);
  assert.deepEqual(await listFonts(), []);
});

test("a completed import never reapplies legacy changes over newer domain edits", async () => {
  await seedLegacy();
  const first = await importLegacySnapshot(getBackend(), await readLegacySnapshot());
  assert.equal(first.skipped, false);

  // A newer domain edit lands after the import.
  const style = await getVariant("variant-1");
  assert.ok(style);
  const edited = await updateVariant(style.id, { name: "Edited after import" }, style.revision);
  assert.equal(edited.name, "Edited after import");

  // Legacy gains a row afterwards (new snapshot, new fingerprint).
  const fontId = (await readLegacySnapshot()).fonts[0]!.id;
  await fontDatabase.variants.add({
    id: "variant-2",
    fontId,
    name: "Legacy latecomer",
    settingsVersion: 1,
    settings: {
      ...defaultVariantSettings({ id: fontId, metadata: metadata() } as never),
      sizePx: 20,
    },
    sampleText: "Late",
    inheritSampleText: false,
    revision: 1,
    createdAt: 7,
    updatedAt: 8,
  });
  const rerun = await importLegacySnapshot(getBackend(), await readLegacySnapshot());
  assert.equal(rerun.skipped, true);
  // The domain edit survives and the late legacy row never materializes.
  assert.equal((await getVariant("variant-1"))?.name, "Edited after import");
  assert.equal(await getVariant("variant-2"), undefined);
  assert.deepEqual((await listVariants()).map((variant) => variant.id), ["variant-1"]);
});

test("migration surfaces storage failures and retries instead of importing nothing", async () => {
  await seedLegacy();
  const failure = mock.method(fontDatabase, "transaction", async () => {
    throw new Error("legacy storage blew up");
  });
  try {
    await assert.rejects(ensureDomainMigrated(), /legacy storage blew up/);
  } finally {
    failure.mock.restore();
  }
  // No marker was written for the failed probe; the retry imports for real.
  assert.equal(await kvGet(getBackend().db, "import:legacy:v1"), undefined);
  assert.deepEqual(await ensureDomainMigrated(), { imported: true });
  assert.ok(await getVariant("variant-1"));
  // Already imported: the completion marker makes the next boot a no-op.
  assert.deepEqual(await ensureDomainMigrated(), { imported: false });
  assert.ok(await getVariant("variant-1"));
});
