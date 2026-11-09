// Direct-font label contract: labels referencing a library font with their
// own size and wrap width, never a hidden saved variant. Covers add/update
// validation, reference switches, snapshot round-trips and the font-removal
// pin, against the same in-memory store the worker dispatch uses.
import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test, { after, beforeEach } from "node:test";
import { PGlite } from "@electric-sql/pglite";
import { drizzle } from "drizzle-orm/pglite";
import { createStoreWithSchema, defineGraph, defineNode } from "@nicia-ai/typegraph";
import { createPostgresBackend } from "@nicia-ai/typegraph/adapters/drizzle/postgres";
import { closeDomainForTests, resetDomainForTests } from "../../src/app/domain/node-backend.ts";
import { domainGraph } from "../../src/app/domain/graph.ts";
import { createDomainBackend, type DomainBackend } from "../../src/app/domain/backend.ts";
import {
  addSceneLabel,
  createScene,
  getScene,
  removeSceneLabel,
  restoreSceneSnapshot,
  updateScene,
  updateSceneLabel,
} from "../../src/app/domain/scene-commands.ts";
import type { DomainSceneView, SceneSnapshotInput } from "../../src/app/domain/types.ts";
import { createVariant } from "../../src/app/variants/repository.ts";
import { saveFont, type FontMetadata, type StoredFont } from "../../src/app/fonts/storage.ts";
import { removeFont } from "../../src/app/domain/commands.ts";
import { listOutputProfiles } from "../../src/app/domain/service.ts";
import { linearCurve } from "../../src/app/features/grayscale/response-curve.ts";
import {
  directExportSnapshots,
  directLabelSettings,
  effectiveDirectWeight,
} from "../../src/app/features/screen/direct-label.ts";
import { DEFAULT_CHARACTER_COVERAGE } from "../../src/app/domain/coverage.ts";
import { exportTextStylesToZip } from "../../src/app/domain/font-export.ts";
import { defaultVariantSettings } from "../../src/app/variants/model.ts";

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

function staticMetadata(): FontMetadata {
  return { names: { family: "Static" }, axes: [] };
}

function narrowMetadata(): FontMetadata {
  return {
    names: { family: "Narrow" },
    axes: [{ tag: "wght", name: "Weight", min: 200, default: 400, max: 500, hidden: false }],
  };
}

async function saveFontWith(meta: FontMetadata, seed = 0) {
  return saveFont({
    bytes: fontBytes(seed),
    fileName: `weight-${seed}.ttf`,
    name: `Weight ${seed}`,
    metadata: meta,
    source: "uploaded",
  });
}

const fontBytes = (seed = 0): ArrayBuffer =>
  Uint8Array.from({ length: 64 }, (_, i) => (i * 7 + seed) % 251).buffer as ArrayBuffer;

async function saveFixture(seed = 0) {
  return saveFont({
    bytes: fontBytes(seed),
    fileName: `fixture-${seed}.ttf`,
    name: `Fixture ${seed}`,
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

async function sceneId(): Promise<{ id: string; revision: number; output: string }> {
  const output = await monoId();
  const created = await createScene(backend, { name: "Card", width: 400, height: 300, outputProfileId: output });
  return { id: created.id, revision: created.revision, output };
}

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
      fontId: placement.fontId,
      fontSize: placement.fontSize,
      width: placement.width,
      fontWeight: placement.fontWeight,
      x: placement.x,
      y: placement.y,
      order: placement.order,
    })),
  };
}

test("direct labels add with their own size and width, never a style", async () => {
  const scene = await sceneId();
  const font = await saveFixture();
  const placed = await addSceneLabel(
    backend,
    scene.id,
    { text: "Direct", fontId: font.id, fontSize: 24, width: 200, x: 8, y: 8 },
    scene.revision,
  );
  assert.equal(placed.revision, scene.revision + 1);
  assert.equal(placed.placements.length, 1);
  assert.deepEqual(
    [
      placed.placements[0]?.textStyleId,
      placed.placements[0]?.fontId,
      placed.placements[0]?.fontSize,
      placed.placements[0]?.width,
    ],
    [null, font.id, 24, 200],
  );

  // A sibling variant label on the same scene keeps the existing shape with
  // explicit null direct fields.
  const style = await createVariant(font.id, { name: "Body" });
  const both = await addSceneLabel(
    backend,
    placed.id,
    { text: "Styled", textStyleId: style.id, x: 0, y: 0 },
    placed.revision,
  );
  const styled = both.placements.find((placement) => placement.text === "Styled");
  assert.deepEqual(
    [styled?.textStyleId, styled?.fontId, styled?.fontSize, styled?.width],
    [style.id, null, null, null],
  );
});

test("direct label input validates both/neither references and every bound", async () => {
  const scene = await sceneId();
  const font = await saveFixture();
  const style = await createVariant(font.id, { name: "Body" });

  await assert.rejects(
    addSceneLabel(
      backend,
      scene.id,
      { text: "x", textStyleId: style.id, fontId: font.id, fontSize: 16, width: 100, x: 0, y: 0 } as never,
      scene.revision,
    ),
    /either a text style or a direct font/,
  );
  await assert.rejects(
    addSceneLabel(backend, scene.id, { text: "x", x: 0, y: 0 } as never, scene.revision),
    /either a text style or a direct font/,
  );
  await assert.rejects(
    addSceneLabel(
      backend,
      scene.id,
      { text: "x", fontId: "missing-font", fontSize: 16, width: 100, x: 0, y: 0 },
      scene.revision,
    ),
    /does not exist/,
  );
  await assert.rejects(
    addSceneLabel(
      backend,
      scene.id,
      { text: "x", fontId: font.id, fontSize: 0, width: 100, x: 0, y: 0 },
      scene.revision,
    ),
    /sizes must be integers/,
  );
  await assert.rejects(
    addSceneLabel(
      backend,
      scene.id,
      { text: "x", fontId: font.id, fontSize: 513, width: 100, x: 0, y: 0 },
      scene.revision,
    ),
    /sizes must be integers/,
  );
  await assert.rejects(
    addSceneLabel(
      backend,
      scene.id,
      { text: "x", fontId: font.id, fontSize: 16, width: 0, x: 0, y: 0 },
      scene.revision,
    ),
    /widths must be integers/,
  );
  await assert.rejects(
    addSceneLabel(
      backend,
      scene.id,
      { text: "x", fontId: font.id, fontSize: 16, width: 100, x: 0, y: 0 },
      scene.revision + 1,
    ),
    /changed underneath/,
  );
  assert.deepEqual((await getScene(backend, scene.id))?.placements, []);
});

test("direct label resize merges and reference switches preserve identity", async () => {
  const scene = await sceneId();
  const font = await saveFixture();
  const other = await saveFixture(1);
  const style = await createVariant(font.id, { name: "Body" });
  const placed = await addSceneLabel(
    backend,
    scene.id,
    { text: "A", fontId: font.id, fontSize: 16, width: 100, x: 4, y: 5 },
    scene.revision,
  );
  const placementId = placed.placements[0]!.id;
  const labelId = placed.placements[0]!.labelId;

  // Resize merges against the stored triple.
  const resized = await updateSceneLabel(
    backend,
    placed.id,
    placementId,
    { fontSize: 32, width: 220 },
    placed.revision,
  );
  assert.deepEqual(
    [resized.placements[0]?.fontSize, resized.placements[0]?.width, resized.placements[0]?.x],
    [32, 220, 4],
  );
  assert.equal(resized.placements[0]?.id, placementId);
  assert.equal(resized.placements[0]?.labelId, labelId);

  // A font-only switch keeps size and width.
  const switched = await updateSceneLabel(backend, resized.id, placementId, { fontId: other.id }, resized.revision);
  assert.deepEqual(
    [switched.placements[0]?.fontId, switched.placements[0]?.fontSize, switched.placements[0]?.width],
    [other.id, 32, 220],
  );

  // Direct back to a saved variant clears the triple and keeps identity.
  const styled = await updateSceneLabel(
    backend,
    switched.id,
    placementId,
    { textStyleId: style.id },
    switched.revision,
  );
  assert.deepEqual(
    [
      styled.placements[0]?.textStyleId,
      styled.placements[0]?.fontId,
      styled.placements[0]?.fontSize,
      styled.placements[0]?.width,
    ],
    [style.id, null, null, null],
  );
  assert.equal(styled.placements[0]?.id, placementId);

  // Variant back to direct needs the full triple; sizes alone on a variant
  // label fail instead of inventing a reference.
  await assert.rejects(
    updateSceneLabel(backend, styled.id, placementId, { fontSize: 20 }, styled.revision),
    /needs a font reference/,
  );
  await assert.rejects(
    updateSceneLabel(backend, styled.id, placementId, { fontId: other.id }, styled.revision),
    /sizes must be integers/,
  );
  const back = await updateSceneLabel(
    backend,
    styled.id,
    placementId,
    { fontId: other.id, fontSize: 20, width: 120 },
    styled.revision,
  );
  assert.deepEqual(
    [back.placements[0]?.textStyleId, back.placements[0]?.fontId, back.placements[0]?.fontSize],
    [null, other.id, 20],
  );
  assert.equal(back.placements[0]?.id, placementId);

  // Unknown references and stale revisions leave state untouched.
  const before = await getScene(backend, back.id);
  assert.ok(before);
  await assert.rejects(
    updateSceneLabel(backend, back.id, placementId, { fontId: "missing" }, back.revision),
    /does not exist/,
  );
  await assert.rejects(
    updateSceneLabel(backend, back.id, placementId, { textStyleId: "missing" }, back.revision),
    /does not exist/,
  );
  await assert.rejects(
    updateSceneLabel(backend, back.id, placementId, { textStyleId: style.id, fontId: other.id }, back.revision),
    /cannot combine/,
  );
  await assert.rejects(
    updateSceneLabel(backend, back.id, placementId, { width: 40 }, back.revision + 1),
    /changed underneath/,
  );
  assert.deepEqual(await getScene(backend, back.id), before);
});

test("snapshot restore round-trips direct labels and rejects mixed references", async () => {
  const scene = await sceneId();
  const font = await saveFixture();
  const style = await createVariant(font.id, { name: "Body" });
  const one = await addSceneLabel(
    backend,
    scene.id,
    { text: "A", fontId: font.id, fontSize: 16, width: 100, x: 1, y: 2 },
    scene.revision,
  );
  const two = await addSceneLabel(backend, one.id, { text: "B", textStyleId: style.id, x: 3, y: 4 }, one.revision);
  const wanted = snapshotOf(two);

  const changed = await updateSceneLabel(backend, two.id, two.placements[0]!.id, { fontSize: 48 }, two.revision);
  assert.notDeepEqual(
    snapshotOf(changed).placements.map((placement) => [placement.fontSize, placement.width]),
    wanted.placements.map((placement) => [placement.fontSize, placement.width]),
  );
  const restored = await restoreSceneSnapshot(backend, changed.id, changed.revision, wanted);
  assert.deepEqual(
    restored.placements.map((placement) => [
      placement.text,
      placement.textStyleId,
      placement.fontId,
      placement.fontSize,
      placement.width,
    ]),
    wanted.placements.map((placement) => [
      placement.text,
      placement.textStyleId,
      placement.fontId,
      placement.fontSize,
      placement.width,
    ]),
  );
  assert.deepEqual(
    restored.placements.map((placement) => placement.id).sort(),
    changed.placements.map((placement) => placement.id).sort(),
  );

  const badBoth = snapshotOf(restored);
  badBoth.placements[0]!.textStyleId = style.id;
  await assert.rejects(
    restoreSceneSnapshot(backend, restored.id, restored.revision, badBoth),
    /cannot combine a text style/,
  );
  const badSize = snapshotOf(restored);
  badSize.placements[0]!.fontSize = 0;
  await assert.rejects(
    restoreSceneSnapshot(backend, restored.id, restored.revision, badSize),
    /sizes must be integers/,
  );
  const badFont = snapshotOf(restored);
  badFont.placements[0]!.fontId = "missing-font";
  await assert.rejects(restoreSceneSnapshot(backend, restored.id, restored.revision, badFont), /does not exist/);
  assert.deepEqual(await getScene(backend, restored.id), restored);
});

test("direct labels default to the font weight and persist explicit weights", async () => {
  const scene = await sceneId();
  const font = await saveFixture();

  const placed = await addSceneLabel(
    backend,
    scene.id,
    { text: "Default", fontId: font.id, fontSize: 24, width: 200, x: 8, y: 8 },
    scene.revision,
  );
  assert.equal(placed.placements[0]?.fontWeight, null);

  const weighted = await addSceneLabel(
    backend,
    placed.id,
    { text: "Bold", fontId: font.id, fontSize: 24, width: 200, fontWeight: 700, x: 8, y: 32 },
    placed.revision,
  );
  assert.deepEqual(
    weighted.placements.map((placement) => [placement.text, placement.fontWeight]),
    [
      ["Default", null],
      ["Bold", 700],
    ],
  );

  // The snapshot capture carries the stored override alongside size/width.
  const captured = snapshotOf(weighted);
  assert.deepEqual(
    captured.placements.map((placement) => [placement.fontSize, placement.width, placement.fontWeight]),
    [
      [24, 200, null],
      [24, 200, 700],
    ],
  );
  const restored = await restoreSceneSnapshot(backend, weighted.id, weighted.revision, captured);
  assert.deepEqual(
    restored.placements.map((placement) => [placement.text, placement.fontWeight]),
    [
      ["Default", null],
      ["Bold", 700],
    ],
  );
});

test("direct label weights validate shape, font bounds and axis support", async () => {
  const scene = await sceneId();
  const font = await saveFixture();
  const fixed = await saveFontWith(staticMetadata(), 9);

  for (const weight of [0, 1001, Number.NaN, Number.POSITIVE_INFINITY, "700"]) {
    await assert.rejects(
      addSceneLabel(
        backend,
        scene.id,
        { text: "x", fontId: font.id, fontSize: 16, width: 100, fontWeight: weight as never, x: 0, y: 0 },
        scene.revision,
      ),
      /within 1\.\.1000/,
    );
  }
  await assert.rejects(
    addSceneLabel(
      backend,
      scene.id,
      { text: "x", fontId: font.id, fontSize: 16, width: 100, fontWeight: 950, x: 0, y: 0 },
      scene.revision,
    ),
    /within the font's wght 100\.\.900/,
  );
  // A static font only accepts the absent/default form, never an override.
  await assert.rejects(
    addSceneLabel(
      backend,
      scene.id,
      { text: "x", fontId: fixed.id, fontSize: 16, width: 100, fontWeight: 400, x: 0, y: 0 },
      scene.revision,
    ),
    /need a font with a wght axis/,
  );
  const plain = await addSceneLabel(
    backend,
    scene.id,
    { text: "x", fontId: fixed.id, fontSize: 16, width: 100, x: 0, y: 0 },
    scene.revision,
  );
  assert.equal(plain.placements[0]?.fontWeight, null);
  await assert.rejects(
    updateSceneLabel(backend, plain.id, plain.placements[0]!.id, { fontWeight: 400 }, plain.revision),
    /need a font with a wght axis/,
  );
  assert.deepEqual(await getScene(backend, plain.id), plain);

  // A weight-only patch preserves size, wrap width and position.
  const placed = await addSceneLabel(
    backend,
    plain.id,
    { text: "W", fontId: font.id, fontSize: 16, width: 100, x: 4, y: 5 },
    plain.revision,
  );
  const patched = await updateSceneLabel(
    backend,
    placed.id,
    placed.placements[1]!.id,
    { fontWeight: 500 },
    placed.revision,
  );
  assert.deepEqual(
    [patched.placements[1]?.fontWeight, patched.placements[1]?.fontSize, patched.placements[1]?.width],
    [500, 16, 100],
  );
  assert.deepEqual([patched.placements[1]?.x, patched.placements[1]?.y], [4, 5]);

  await assert.rejects(
    updateSceneLabel(backend, patched.id, patched.placements[1]!.id, { fontWeight: 50 }, patched.revision),
    /within the font's wght/,
  );
  assert.deepEqual(await getScene(backend, patched.id), patched);
  const cleared = await updateSceneLabel(
    backend,
    patched.id,
    patched.placements[1]!.id,
    { fontWeight: null },
    patched.revision,
  );
  assert.equal(cleared.placements[1]?.fontWeight, null);
  assert.deepEqual((await getScene(backend, cleared.id))?.placements[1], cleared.placements[1]);

  // A weight-only patch on a variant label fails instead of mutating the
  // shared style: the variant owns the weight.
  const style = await createVariant(font.id, { name: "Body" });
  const styled = await addSceneLabel(
    backend,
    cleared.id,
    { text: "S", textStyleId: style.id, x: 0, y: 0 },
    cleared.revision,
  );
  const styledPlacement = styled.placements.find((placement) => placement.text === "S")!;
  await assert.rejects(
    updateSceneLabel(backend, styled.id, styledPlacement.id, { fontWeight: 500 }, styled.revision),
    /needs a font reference/,
  );
  const kept = await getScene(backend, styled.id);
  assert.deepEqual(kept?.placements.find((placement) => placement.id === styledPlacement.id)?.textStyleId, style.id);

  // Weight never combines with a style reference on either path.
  await assert.rejects(
    updateSceneLabel(
      backend,
      styled.id,
      styledPlacement.id,
      { textStyleId: style.id, fontWeight: 500 },
      styled.revision,
    ),
    /cannot combine/,
  );
  await assert.rejects(
    addSceneLabel(
      backend,
      styled.id,
      { text: "x", textStyleId: style.id, fontWeight: 500, x: 0, y: 0 } as never,
      styled.revision,
    ),
    /either a text style or a direct font/,
  );
  assert.deepEqual(await getScene(backend, styled.id), styled);
});

test("font switches and reference conversions resolve carried weights", async () => {
  const scene = await sceneId();
  const font = await saveFixture();
  const narrow = await saveFontWith(narrowMetadata(), 3);
  const fixed = await saveFontWith(staticMetadata(), 4);
  const placed = await addSceneLabel(
    backend,
    scene.id,
    { text: "A", fontId: font.id, fontSize: 16, width: 100, fontWeight: 700, x: 0, y: 0 },
    scene.revision,
  );
  const placementId = placed.placements[0]!.id;

  // A font switch without a weight keeps the stored override, clamped into
  // the destination axis.
  const clamped = await updateSceneLabel(backend, placed.id, placementId, { fontId: narrow.id }, placed.revision);
  assert.deepEqual([clamped.placements[0]?.fontId, clamped.placements[0]?.fontWeight], [narrow.id, 500]);

  // A switch to a static font clears the override: statics never receive an
  // unsupported coordinate, and an explicit weight there still fails.
  const cleared = await updateSceneLabel(backend, clamped.id, placementId, { fontId: fixed.id }, clamped.revision);
  assert.deepEqual([cleared.placements[0]?.fontId, cleared.placements[0]?.fontWeight], [fixed.id, null]);
  await assert.rejects(
    updateSceneLabel(backend, cleared.id, placementId, { fontId: fixed.id, fontWeight: 400 }, cleared.revision),
    /need a font with a wght axis/,
  );
  assert.deepEqual(await getScene(backend, cleared.id), cleared);

  // A variant-to-direct conversion preserves the style's resolved wght
  // inside the destination support, even when the patch carries no weight.
  const heavy = await createVariant(font.id, {
    name: "Heavy",
    settings: { ...defaultVariantSettings(font as StoredFont), axes: { wght: 800 } },
  });
  const styled = await addSceneLabel(
    backend,
    cleared.id,
    { text: "V", textStyleId: heavy.id, x: 1, y: 1 },
    cleared.revision,
  );
  const variantPlacement = styled.placements.find((placement) => placement.text === "V")!;
  const converted = await updateSceneLabel(
    backend,
    styled.id,
    variantPlacement.id,
    { fontId: narrow.id, fontSize: 20, width: 120 },
    styled.revision,
  );
  assert.equal(converted.placements.find((placement) => placement.id === variantPlacement.id)?.fontWeight, 500);
  const convertedPlacement = converted.placements.find((placement) => placement.id === variantPlacement.id)!;
  assert.deepEqual(
    [convertedPlacement.textStyleId, convertedPlacement.fontId, convertedPlacement.fontSize],
    [null, narrow.id, 20],
  );

  // An explicit conversion weight is strictly validated against the target.
  await assert.rejects(
    updateSceneLabel(
      backend,
      converted.id,
      convertedPlacement.id,
      { fontId: narrow.id, fontSize: 20, width: 120, fontWeight: 800 },
      converted.revision,
    ),
    /within the font's wght 200\.\.500/,
  );
  const toStatic = await updateSceneLabel(
    backend,
    converted.id,
    convertedPlacement.id,
    { fontId: fixed.id, fontSize: 20, width: 120 },
    converted.revision,
  );
  assert.equal(toStatic.placements.find((placement) => placement.id === variantPlacement.id)?.fontWeight, null);

  // Switching back to a variant clears the direct override.
  const back = await updateSceneLabel(
    backend,
    toStatic.id,
    variantPlacement.id,
    { textStyleId: heavy.id },
    toStatic.revision,
  );
  assert.deepEqual(
    [
      back.placements.find((placement) => placement.id === variantPlacement.id)?.textStyleId,
      back.placements.find((placement) => placement.id === variantPlacement.id)?.fontWeight,
    ],
    [heavy.id, null],
  );
});

test("variant settings still require a complete axis set including wght", async () => {
  const font = await saveFixture();
  await assert.rejects(
    createVariant(font.id, {
      name: "NoWeight",
      settings: { ...defaultVariantSettings(font as StoredFont), axes: {} },
    }),
    /axis "wght" must be a finite number/,
  );
});

test("snapshot restore round-trips weights and rejects invalid ones", async () => {
  const scene = await sceneId();
  const font = await saveFixture();
  const one = await addSceneLabel(
    backend,
    scene.id,
    { text: "A", fontId: font.id, fontSize: 16, width: 100, fontWeight: 700, x: 0, y: 0 },
    scene.revision,
  );
  const two = await addSceneLabel(
    backend,
    one.id,
    { text: "B", fontId: font.id, fontSize: 16, width: 100, x: 1, y: 1 },
    one.revision,
  );
  const wanted = snapshotOf(two);
  assert.deepEqual(
    wanted.placements.map((placement) => placement.fontWeight),
    [700, null],
  );

  const changed = await updateSceneLabel(backend, two.id, two.placements[0]!.id, { fontWeight: 400 }, two.revision);
  assert.notDeepEqual(
    snapshotOf(changed).placements.map((placement) => placement.fontWeight),
    [700, null],
  );
  const restored = await restoreSceneSnapshot(backend, changed.id, changed.revision, wanted);
  assert.deepEqual(
    restored.placements.map((placement) => placement.fontWeight),
    [700, null],
  );

  // The default and an explicit same-value override render identically.
  const curve = linearCurve(2);
  assert.deepEqual(
    directLabelSettings(font as StoredFont, 16, curve, null),
    directLabelSettings(font as StoredFont, 16, curve, 400),
  );

  const badWeight = snapshotOf(restored);
  badWeight.placements[0]!.fontWeight = 950;
  await assert.rejects(
    restoreSceneSnapshot(backend, restored.id, restored.revision, badWeight),
    /within the font's wght/,
  );
  const badShape = snapshotOf(restored);
  badShape.placements[0]!.fontWeight = Number.NaN;
  await assert.rejects(restoreSceneSnapshot(backend, restored.id, restored.revision, badShape), /within 1\.\.1000/);
  // Snapshots predating the weight field omit it and restore as the default.
  const legacy = snapshotOf(restored);
  for (const placement of legacy.placements) delete (placement as unknown as Record<string, unknown>).fontWeight;
  const fromLegacy = await restoreSceneSnapshot(backend, restored.id, restored.revision, legacy);
  assert.deepEqual(
    fromLegacy.placements.map((placement) => placement.fontWeight),
    [null, null],
  );
  assert.deepEqual(await getScene(backend, fromLegacy.id), fromLegacy);
});

test("export separates same font and size labels by effective weight", async () => {
  const font = await saveFontWith(metadata(), 7);
  const stored = font as StoredFont;
  const curve = linearCurve(2);
  const placements = [
    { fontId: font.id, fontSize: 16, fontWeight: 700 },
    { fontId: font.id, fontSize: 16, fontWeight: null },
    { fontId: font.id, fontSize: 16, fontWeight: 400 },
  ];
  const snapshots = directExportSnapshots(placements, new Map([[font.id, stored]]), curve);
  // The default and the explicit same-value override share one entry keyed by
  // the effective weight; the differing weight exports distinctly.
  assert.equal(snapshots.length, 2);
  assert.deepEqual(
    snapshots.map((snapshot) => snapshot.id),
    [`direct:${font.id}:16:700`, `direct:${font.id}:16:400`],
  );
  assert.deepEqual(
    snapshots.map((snapshot) => snapshot.settings.axes.wght),
    [700, 400],
  );
  assert.equal(effectiveDirectWeight(stored, null), 400);
  assert.equal(effectiveDirectWeight(stored, 400), 400);
  assert.equal(effectiveDirectWeight({ ...stored, metadata: staticMetadata() }, 700), null);

  const requests: { fontId: string; axes: Record<string, number> }[] = [];
  const result = await exportTextStylesToZip(
    {
      textStyleIds: [],
      outputProfileId: "mono",
      coverage: DEFAULT_CHARACTER_COVERAGE,
      format: "playdate",
      extraSnapshots: snapshots,
    },
    {
      resolveTextStyles: async () => [],
      fontCoverage: async () => null,
      ensureFontReady: async () => {},
      exportPlaydate: async (fontId, request) => {
        requests.push({ fontId, axes: { ...(request.config.axes as Record<string, number>) } });
        return new TextEncoder().encode(`fnt:${fontId}`).buffer;
      },
    },
  );
  assert.equal(requests.length, 2);
  assert.deepEqual(
    requests.map((request) => request.axes.wght ?? Number.NaN).sort((left, right) => left - right),
    [400, 700],
  );
  assert.equal(result.files.length, 2);
  assert.notEqual(result.files[0], result.files[1]);
});

test("pre-weight persisted rows reopen compatibly with default weight", async (t) => {
  const directory = await fs.mkdtemp(path.join(tmpdir(), "glypherie-direct-weight-"));
  t.after(() => fs.rm(directory, { recursive: true, force: true }));
  const dataDir = path.join(directory, "pgdata");

  // The exact previous Label schema: same graph id and every other node/edge,
  // minus the weight field. Seeded through the old admission, then reopened
  // through the current backend.
  const legacyLabel = defineNode("Label", {
    schema: domainGraph.nodes.Label.type.schema.omit({ fontWeight: true }),
  });
  const legacyGraph = defineGraph({
    id: domainGraph.id,
    nodes: { ...domainGraph.nodes, Label: { type: legacyLabel } },
    edges: domainGraph.edges,
  });
  const stamp = Date.now();
  let legacySceneId = "";
  let legacyFontId = "";
  const previous = new PGlite({ dataDir });
  try {
    const db = drizzle({ client: previous });
    const [store] = await createStoreWithSchema(
      legacyGraph,
      createPostgresBackend(db, { vector: false, fulltext: false }),
    );
    const font = await store.nodes.Font.create({
      name: "Reopen",
      fileName: "reopen.ttf",
      metadata: metadata(),
      source: "uploaded",
      addedAt: stamp,
    } as never);
    const profile = await store.nodes.OutputProfile.create({
      name: "Monochrome",
      curve: linearCurve(2).map((level) => ({ ...level })),
      revision: 1,
      createdAt: stamp,
      updatedAt: stamp,
    } as never);
    const scene = await store.nodes.Scene.create({
      name: "Card",
      width: 400,
      height: 300,
      deviceId: null,
      exportCoverage: { presetIds: ["ascii"], extraRanges: [] },
      revision: 1,
      createdAt: stamp,
      updatedAt: stamp,
    } as never);
    await store.edges.defaultOutput.create(scene, profile, {} as never);
    const label = await store.nodes.Label.create({
      text: "Old",
      fontId: String(font.id),
      fontSize: 16,
      width: 100,
    } as never);
    await store.edges.places.create(scene, label, { x: 2, y: 2, order: 0 } as never);
    legacySceneId = String(scene.id);
    legacyFontId = String(font.id);
  } finally {
    await previous.close();
  }

  // The current backend admits the older persisted schema without a
  // migration error or an incompatible-schema reset: the scene, font and row
  // survive, and the absent weight reads back as the font default.
  const reader = await createDomainBackend({ dataDir });
  t.after(() => reader.close().catch(() => undefined));
  const reopened = await getScene(reader, legacySceneId);
  assert.ok(reopened);
  assert.equal(reopened.name, "Card");
  assert.deepEqual(
    reopened.placements.map((placement) => [placement.text, placement.fontSize, placement.width, placement.fontWeight]),
    [["Old", 16, 100, null]],
  );

  // The reopened row accepts a weight, which persists across another reopen.
  const weighted = await updateSceneLabel(
    reader,
    reopened.id,
    reopened.placements[0]!.id,
    { fontWeight: 700 },
    reopened.revision,
  );
  assert.equal(weighted.placements[0]?.fontWeight, 700);
  await reader.flush();
  await reader.close();
  const reread = await createDomainBackend({ dataDir });
  t.after(() => reread.close().catch(() => undefined));
  const again = await getScene(reread, legacySceneId);
  assert.deepEqual(
    again?.placements.map((placement) => [placement.fontId, placement.fontWeight]),
    [[legacyFontId, 700]],
  );
});

test("removeFont refuses fonts backing direct labels and allows them after removal", async () => {
  const scene = await sceneId();
  const font = await saveFixture();
  const placed = await addSceneLabel(
    backend,
    scene.id,
    { text: "A", fontId: font.id, fontSize: 16, width: 100, x: 0, y: 0 },
    scene.revision,
  );
  await assert.rejects(removeFont(backend, font.id), /used by direct labels in Card/);

  const cleaned = await removeSceneLabel(backend, placed.id, placed.placements[0]!.id, placed.revision);
  assert.deepEqual(cleaned.placements, []);
  await removeFont(backend, font.id);

  // Renaming the scene still works after the direct label cycle.
  const renamed = await updateScene(backend, cleaned.id, { name: "Kept" }, cleaned.revision);
  assert.equal(renamed.name, "Kept");
});
