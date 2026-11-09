import assert from "node:assert/strict";
import test from "node:test";
import {
  PLAYDATE_ASCII,
  playdateCoveredRequest,
  playdateRequest,
  playdateFileName,
  splitPlaydateCoverage,
} from "../../src/app/features/preview/playdate-export.ts";
import { toRenderSpec } from "../../src/app/renderer/render-spec.ts";
import { DEFAULT_CHARACTER_COVERAGE, normalizeCoverage } from "../../src/app/domain/coverage.ts";
import type { VariantSettings } from "../../src/app/variants/model.ts";
import { editKerning, selectKerningMethod } from "../../src/app/kerning/model.ts";
function defaultVariantSettings(): VariantSettings {
  return {
    sizePx: 16,
    axes: {},
    letterSpacingPx: 0,
    profile: "mono_1bit",
    renderer: "candidate",
    stemFitting: "font_hints_first",
    diagonalFitting: false,
    kerning: true,
    monoRaster: { dropout: "smart", includeStubs: true, fontInstructions: true },
  };
}

function asciiCoverage() {
  return DEFAULT_CHARACTER_COVERAGE;
}

test("Playdate export forwards the preview pipeline, quantized tracking, axes and kerning", () => {
  const settings = {
    ...defaultVariantSettings(),
    sizePx: 18,
    axes: { wght: 600 },
    letterSpacingPx: -1.5,
    kerning: false,
    stemFitting: "upstream_mono" as const,
  };
  const request = playdateRequest(
    settings,
    normalizeCoverage({
      presetIds: [],
      extraRanges: [
        { start: 0x20, end: 0x7e },
        { start: 0xe9, end: 0xe9 },
      ],
    }),
  );
  const preview = toRenderSpec({
    text: "AV",
    width: 200,
    height: 100,
    sizePx: settings.sizePx,
    axes: settings.axes,
    profile: settings.profile,
    rasterization: settings.rasterization ?? "free_type_mono",
    stemFitting: settings.stemFitting,
    letterSpacingPx: settings.letterSpacingPx,
    kerning: settings.kerning,
  });
  assert.deepEqual(request.pipeline, preview.pipeline);
  assert.equal(request.pipeline.fitting, "upstream_mono");
  assert.equal(request.letter_spacing_px, -2);
  assert.equal(request.config.characters, `${PLAYDATE_ASCII}é`);
  assert.equal(request.config.size_px, 18);
  assert.equal(request.config.kerning, false);
  assert.deepEqual(request.config.axes, { wght: 600 });
  assert.notEqual(request.config.axes, settings.axes);
  assert.deepEqual(request.config.mono_raster, { dropout: "smart", include_stubs: true, font_instructions: true });
  assert.ok(!("palette" in request.config));
  assert.ok(!("renderer" in request));
  assert.equal(PLAYDATE_ASCII.length, 95);
  assert.equal(PLAYDATE_ASCII.codePointAt(0), 32);
  assert.equal(PLAYDATE_ASCII.codePointAt(94), 126);
});

test("standalone export generates the covered set and keeps missing ranges visible", () => {
  const asciiOnly = [{ start: 0x20, end: 0x7e }];
  const split = splitPlaydateCoverage(normalizeCoverage({ presetIds: ["ascii", "greek"], extraRanges: [] }), asciiOnly);
  assert.deepEqual(split.covered, asciiOnly);
  assert.deepEqual(split.missing, [
    { start: 0x370, end: 0x3ff },
    { start: 0x1f00, end: 0x1fff },
  ]);
  const request = playdateCoveredRequest(
    defaultVariantSettings(),
    normalizeCoverage({ presetIds: ["ascii", "greek"], extraRanges: [] }),
    asciiOnly,
  );
  assert.equal(request.config.characters.length, 95);
});

test("standalone export without font coverage stays unknown instead of empty", () => {
  const split = splitPlaydateCoverage(DEFAULT_CHARACTER_COVERAGE);
  assert.equal(split.missing, null);
  assert.equal(split.supported.length, 1);
  const request = playdateCoveredRequest(defaultVariantSettings(), DEFAULT_CHARACTER_COVERAGE);
  assert.equal(request.config.characters.length, 95);
});

test("standalone 1024 cap applies to the covered set, not the preset union", () => {
  const asciiOnly = [{ start: 0x20, end: 0x7e }];
  const request = playdateCoveredRequest(
    defaultVariantSettings(),
    normalizeCoverage({ presetIds: ["reading"], extraRanges: [] }),
    asciiOnly,
  );
  assert.equal(request.config.characters.length, 95);
  assert.throws(
    () =>
      playdateCoveredRequest(
        defaultVariantSettings(),
        normalizeCoverage({ presetIds: [], extraRanges: [{ start: 0x0a, end: 0x0a }] }),
        asciiOnly,
      ),
    /outside the Playdate export subset|no exportable characters/,
  );
});

test("Playdate export rejects grayscale and creates a portable download filename", () => {
  assert.throws(
    () => playdateRequest({ ...defaultVariantSettings(), profile: "gray_3bit" }, asciiCoverage()),
    /Monochrome/,
  );
  assert.equal(playdateFileName("My Font / Bold", 16), "My-Font-Bold-16px.fnt");
  assert.equal(playdateFileName("../", 12.5), "font-12.5px.fnt");
});

test("Playdate export forwards TypeFacet at the same seam as the live preview", () => {
  const settings = {
    ...defaultVariantSettings(),
    kerning: editKerning(selectKerningMethod(false, "typefacet"), {
      method: "typefacet",
      settings: {
        normalDistanceEm: 0.1,
        intrusionToleranceEm: 0.1,
        minimumDistanceEm: 0.025,
        maxXExtremaOverlapEm: 0.075,
      },
    }),
  };
  const request = playdateRequest(
    settings,
    normalizeCoverage({ presetIds: [], extraRanges: [{ start: 0x20, end: 0x7e }] }),
  );
  assert.equal(request.config.kerning, true);
  assert.deepEqual(request.kerning_method, {
    method: "typefacet",
    normal_distance_em: 0.1,
    intrusion_tolerance_em: 0.1,
    minimum_distance_em: 0.025,
    max_x_extrema_overlap_em: 0.075,
  });
  assert.ok(!Object.hasOwn(request.config, "kerning_method"));
  assert.ok(
    !Object.hasOwn(
      playdateRequest(
        defaultVariantSettings(),
        normalizeCoverage({ presetIds: [], extraRanges: [{ start: 0x41, end: 0x41 }] }),
      ),
      "kerning_method",
    ),
  );
});

test("each additional method shares its preview selection with export", () => {
  for (const kerning of [
    selectKerningMethod(false, "hu_hersch"),
    editKerning(selectKerningMethod(false, "hu_hersch"), {
      method: "hu_hersch",
      settings: { apertureDepthFactor: 0.35, globalDepthFactor: 0.4 },
    }),
    selectKerningMethod(false, "fontforge"),
  ]) {
    const settings = { ...defaultVariantSettings(), kerning };
    const coverage = normalizeCoverage({ presetIds: [], extraRanges: [{ start: 0x20, end: 0x7e }] });
    const exported = playdateRequest(settings, coverage);
    const preview = toRenderSpec({
      text: "nn AV",
      width: 200,
      height: 100,
      sizePx: settings.sizePx,
      axes: settings.axes,
      profile: settings.profile,
      rasterization: "free_type_mono",
      kerning,
    });
    assert.deepEqual(exported.kerning_method, preview.kerning_method);
    assert.equal(exported.config.kerning, preview.kerning);
    assert.ok(!Object.hasOwn(exported.config, "kerning_method"));
  }
});
