import assert from "node:assert/strict";
import test from "node:test";
import { PLAYDATE_ASCII, playdateRequest, playdateFileName } from "../../src/app/features/preview/playdate-export.ts";
import { toRenderSpec } from "../../src/app/renderer/render-spec.ts";
import type { VariantSettings } from "../../src/app/variants/model.ts";
function defaultVariantSettings(): VariantSettings {
  return { sizePx: 16, axes: {}, letterSpacingPx: 0, profile: "mono_1bit", renderer: "candidate",
    stemFitting: "font_hints_first", diagonalFitting: false, kerning: true,
    monoRaster: { dropout: "smart", includeStubs: true, fontInstructions: true } };
}

test("Playdate export forwards the preview pipeline, quantized tracking, axes and kerning", () => {
  const settings = { ...defaultVariantSettings(), sizePx: 18, axes: { wght: 600 }, letterSpacingPx: -1.5,
    kerning: false, stemFitting: "upstream_mono" as const };
  const request = playdateRequest(settings, " AVToé");
  const preview = toRenderSpec({ text: "AV", width: 200, height: 100, sizePx: settings.sizePx,
    axes: settings.axes, profile: settings.profile, rasterization: settings.rasterization ?? "free_type_mono",
    stemFitting: settings.stemFitting, letterSpacingPx: settings.letterSpacingPx, kerning: settings.kerning });
  assert.deepEqual(request.pipeline, preview.pipeline);
  assert.equal(request.pipeline.fitting, "upstream_mono");
  assert.equal(request.letter_spacing_px, -2);
  assert.equal(request.config.characters, " AVToé");
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

test("Playdate export rejects grayscale and creates a portable download filename", () => {
  assert.throws(() => playdateRequest({ ...defaultVariantSettings(), profile: "gray_3bit" }, "AV"), /Monochrome/);
  assert.equal(playdateFileName("My Font / Bold", 16), "My-Font-Bold-16px.fnt");
  assert.equal(playdateFileName("../", 12.5), "font-12.5px.fnt");
});
