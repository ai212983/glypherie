import assert from "node:assert/strict";
import test from "node:test";
import { toRenderSpec } from "../../src/app/renderer/render-spec.ts";
import {
  currentPreviewSettings,
  defaultVariantSettings,
  validateVariantSettings,
  type VariantSettings,
} from "../../src/app/variants/model.ts";
import {
  defaultSnapshot,
  encodeHashSearch,
  encodeUrlSnapshot,
  parseUrlSnapshot,
  type FamilyMeta,
  type GlobalDefaults,
} from "../../src/app/features/preview/state/snapshot-codec.ts";
import { playdateRequest } from "../../src/app/features/preview/playdate-export.ts";

const METAS: FamilyMeta[] = [
  {
    id: "alpha",
    defaultSize: 16,
    defaultAxes: {},
    axes: [],
    sampleText: "Alpha",
    presets: [{ id: "reading", content: "Alpha" }],
    defaultPreset: "reading",
  },
];
const DEFAULTS: GlobalDefaults = { font: "alpha", profile: "mono_1bit" };

function monoOptions(diagonalFitting?: boolean) {
  return {
    text: "Ag", sizePx: 16, axes: {}, profile: "mono_1bit" as const,
    width: 200, height: 100, rasterization: "free_type_mono" as const,
    stemFitting: "font_hints_first" as const, diagonalFitting,
  };
}

test("pipeline omits the diagonal flag unless mono 1-bit opts in", () => {
  assert.equal("diagonal_fitting" in toRenderSpec(monoOptions()).pipeline!, false);
  assert.equal("diagonal_fitting" in toRenderSpec(monoOptions(false)).pipeline!, false);
  assert.equal(toRenderSpec(monoOptions(true)).pipeline!.diagonal_fitting, true);
});

test("the diagonal opt-in is independent of the font-hints choice", () => {
  const spec = toRenderSpec({ ...monoOptions(true), stemFitting: "upstream_mono" });
  assert.equal(spec.pipeline!.diagonal_fitting, true);
  assert.equal(spec.pipeline!.fitting, "upstream_mono");
});

test("grayscale never forwards the diagonal flag", () => {
  const spec = toRenderSpec({ ...monoOptions(true), profile: "gray_3bit" });
  assert.equal("diagonal_fitting" in spec.pipeline!, false);
  assert.equal(spec.pipeline!.fitting, "upstream_mono");
});

test("new snapshots default diagonals on and historical links stay off", () => {
  assert.equal(defaultSnapshot(METAS, DEFAULTS).diagonalFitting, true);
  const parsed = parseUrlSnapshot("?v=1&font=alpha", "", METAS, DEFAULTS);
  assert.equal(parsed?.diagonalFitting, false);
});

test("a fresh default snapshot encodes diagonals=1; diagonals=0 stays off", () => {
  const search = `?${encodeUrlSnapshot(defaultSnapshot(METAS, DEFAULTS), "", ["alpha"]).toString()}`;
  assert.match(search, /diagonals=1/);
  const off = parseUrlSnapshot("?v=1&font=alpha&diagonals=0", "", METAS, DEFAULTS);
  assert.equal(off?.diagonalFitting, false);
  const explicit = parseUrlSnapshot("?v=1&font=alpha&diagonals=false", "", METAS, DEFAULTS);
  assert.equal(explicit?.diagonalFitting, false);
});

test("diagonals=1 round-trips through the snapshot codec and stays owned", () => {
  const original = { ...defaultSnapshot(METAS, DEFAULTS), diagonalFitting: true };
  const search = `?${encodeUrlSnapshot(original, "", ["alpha"]).toString()}`;
  assert.match(search, /diagonals=1/);
  assert.deepEqual(parseUrlSnapshot(search, "", METAS, DEFAULTS), original);
  const encoded = encodeUrlSnapshot({ ...original, diagonalFitting: false }, "?diagonals=1&utm=keep");
  assert.equal(encoded.get("diagonals"), null);
  assert.equal(encoded.get("utm"), "keep");
  const hash = encodeHashSearch(original, "");
  assert.equal(hash.get("diagonals"), "1");
  assert.equal(hash.get("font"), null);
});

test("new variants default diagonals on; legacy rows stay off; non-booleans rejected", () => {
  const font = {
    id: "font", name: "F", fileName: "f.ttf", bytes: new ArrayBuffer(8),
    metadata: { names: { family: "F" }, axes: [] }, source: "uploaded" as const, addedAt: 0,
  };
  assert.equal(defaultVariantSettings(font).diagonalFitting, true);
  const legacy = { ...defaultVariantSettings(font) } as Record<string, unknown>;
  delete legacy.diagonalFitting;
  validateVariantSettings(legacy as never, font.metadata);
  assert.equal(legacy.diagonalFitting, false);
  assert.throws(
    () => validateVariantSettings({ ...defaultVariantSettings(font), diagonalFitting: "yes" as never }, font.metadata),
    /diagonalFitting must be a boolean/,
  );
  const normalized = currentPreviewSettings({ ...defaultVariantSettings(font), diagonalFitting: undefined as never });
  assert.equal(normalized.diagonalFitting, false);
  assert.equal(currentPreviewSettings({ ...defaultVariantSettings(font), diagonalFitting: true }).diagonalFitting, true);
});

function exportSettings(diagonalFitting: boolean): VariantSettings {
  return {
    sizePx: 16, axes: {}, letterSpacingPx: 0, profile: "mono_1bit",
    renderer: "candidate", stemFitting: "font_hints_first", diagonalFitting, kerning: true,
    monoRaster: { dropout: "smart", includeStubs: true, fontInstructions: true },
  };
}

test("export carries the same pipeline flag as the preview", () => {
  for (const diagonalFitting of [false, true]) {
    const settings = exportSettings(diagonalFitting);
    const request = playdateRequest(settings, "AV");
    const preview = toRenderSpec({ text: "AV", width: 200, height: 100, sizePx: settings.sizePx,
      axes: settings.axes, profile: settings.profile, rasterization: "free_type_mono",
      stemFitting: settings.stemFitting, diagonalFitting: settings.diagonalFitting,
      letterSpacingPx: settings.letterSpacingPx, kerning: settings.kerning });
    assert.deepEqual(request.pipeline, preview.pipeline);
    assert.equal("diagonal_fitting" in request.pipeline, diagonalFitting);
  }
});
