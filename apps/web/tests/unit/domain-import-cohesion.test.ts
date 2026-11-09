// Import cohesion: one shared output-profile lookup serves every variant's
// preferences, and concurrent cold-boot imports serialize on the advisory
// lock so exactly one caller reports the import while state stays singular.

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test, { after, beforeEach } from "node:test";
import { kvGet } from "../../src/app/domain/backend.ts";
import { getBackend, closeDomainForTests, resetDomainForTests } from "../../src/app/domain/node-backend.ts";
import { IMPORT_MARKER_KEY, importLegacySnapshot } from "../../src/app/domain/importer.ts";
import type { LegacySnapshot } from "../../src/app/legacy-database.ts";
import { getVariant, listVariants } from "../../src/app/variants/repository.ts";
import { getFont } from "../../src/app/fonts/storage.ts";
import { linearCurve } from "../../src/app/features/grayscale/response-curve.ts";
import { defaultVariantSettings } from "../../src/app/variants/model.ts";
import type { FontMetadata } from "../../src/app/fonts/storage.ts";

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

const sha256 = (bytes: ArrayBuffer): string => createHash("sha256").update(Buffer.from(bytes)).digest("hex");

function snapshot(): LegacySnapshot {
  const bytes = fontBytes(7);
  const fontId = sha256(bytes);
  const base = { fontId, revision: 1, createdAt: 5, updatedAt: 6 };
  return {
    fonts: [
      {
        id: fontId,
        name: "Legacy",
        fileName: "legacy.ttf",
        bytes,
        metadata: metadata(),
        source: "uploaded",
        addedAt: 11,
      },
    ],
    variants: [
      {
        ...base,
        id: "variant-a",
        name: "Legacy A",
        settings: {
          ...defaultVariantSettings({ id: fontId, metadata: metadata() } as never),
          sizePx: 20,
          paletteId: 0,
        },
        sampleText: "Mono",
        inheritSampleText: false,
      },
      {
        ...base,
        id: "variant-b",
        name: "Legacy B",
        settings: {
          ...defaultVariantSettings({ id: fontId, metadata: metadata() } as never),
          sizePx: 20,
          paletteId: 1,
          profile: "gray_2bit",
          rasterization: "coverage",
        },
        sampleText: "Gray",
        inheritSampleText: true,
      },
    ],
    palettes: [
      { id: 0, name: "Monochrome", curve: linearCurve(2) },
      { id: 1, name: "Gray", curve: linearCurve(4) },
    ],
    seedMarker: "seed-rows",
    variantCount: 2,
  };
}

test("every variant keeps its own output profile from the shared lookup", async () => {
  const snap = snapshot();
  const result = await importLegacySnapshot(getBackend(), snap);
  assert.equal(result.skipped, false);

  const monoPref = JSON.parse((await kvGet(getBackend().db, "preview:variant-a")) ?? "{}");
  const grayPref = JSON.parse((await kvGet(getBackend().db, "preview:variant-b")) ?? "{}");
  // Profile ids follow the importer's layout: monochrome keeps its fixed id,
  // legacy palettes map to `palette-<legacy id>`.
  assert.equal(monoPref.outputProfileId, "output-monochrome");
  assert.equal(grayPref.outputProfileId, "palette-1");
  assert.equal(monoPref.sampleText, "Mono");
  assert.equal(grayPref.inheritSampleText, true);
});

test("concurrent imports serialize: one winner, honest loser, singular state", async () => {
  const snap = snapshot();
  const [first, second] = await Promise.all([
    importLegacySnapshot(getBackend(), snap),
    importLegacySnapshot(getBackend(), snap),
  ]);
  const winners = [first, second].filter((result) => !result.skipped);
  const losers = [first, second].filter((result) => result.skipped);
  assert.equal(winners.length, 1);
  assert.equal(losers.length, 1);
  assert.deepEqual(losers[0], { skipped: true, fonts: 0, variants: 0, palettes: 0, skippedVariantIds: [] });

  // Singular state: one font, both variants, one completion marker.
  assert.ok(await getFont(snap.fonts[0]!.id));
  assert.deepEqual((await listVariants()).map((variant) => variant.id).sort(), ["variant-a", "variant-b"]);
  assert.ok(await getVariant("variant-a"));
  assert.ok(await getVariant("variant-b"));
  const marker = JSON.parse((await kvGet(getBackend().db, IMPORT_MARKER_KEY)) ?? "{}");
  assert.equal(marker.status, "complete");

  // The one-time marker still holds afterwards: a late rerun is a no-op and
  // never reapplies legacy rows over the imported state.
  const rerun = await importLegacySnapshot(getBackend(), snap);
  assert.equal(rerun.skipped, true);
});
