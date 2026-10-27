import assert from "node:assert/strict";
import test from "node:test";
import {
  canonicalPreviewPolicyJson,
  resolveWorkingPreviewPolicy,
  WORKING_PREVIEW_DEFAULTS,
} from "../../src/app/renderer/preview-policy.ts";
import { fingerprintPreviewPolicy } from "../../scripts/policy-fingerprint.ts";
import { toRenderSpec } from "../../src/app/renderer/render-spec.ts";
import { defaultVariantSettings } from "../../src/app/variants/model.ts";
import { defaultSnapshot } from "../../src/app/features/preview/state/snapshot-codec.ts";

test("defaults resolve the working-preview Mono policy", () => {
  assert.deepEqual(resolveWorkingPreviewPolicy(), {
    fitting: "font_hints_auto",
    rasterization: "free_type_mono_terminals",
    diagonal_fitting: true,
    hinting: "auto_fallback",
    output_bits: 1,
    mono_threshold: 128,
    gray_gamma: 1,
    missing_glyphs: "error",
    metric_rounding: "subpixel",
    mono_raster: { dropout: "smart", include_stubs: true, font_instructions: true },
  });
});

test("omitted settings follow the shared defaults object, not copied literals", () => {
  const policy = resolveWorkingPreviewPolicy();
  assert.equal(policy.fitting, WORKING_PREVIEW_DEFAULTS.fitting);
  assert.equal(policy.rasterization, WORKING_PREVIEW_DEFAULTS.rasterization);
  assert.equal(policy.diagonal_fitting, WORKING_PREVIEW_DEFAULTS.diagonalFitting);
  assert.equal(policy.mono_raster.dropout, WORKING_PREVIEW_DEFAULTS.dropout);
  assert.equal(policy.mono_raster.include_stubs, WORKING_PREVIEW_DEFAULTS.includeStubs);
  assert.equal(policy.mono_raster.font_instructions, WORKING_PREVIEW_DEFAULTS.fontInstructions);
});

test("new previews and variants inherit fitting and diagonal defaults", () => {
  const defaults = WORKING_PREVIEW_DEFAULTS as { fitting: string; diagonalFitting: boolean };
  const saved = { ...defaults };
  try {
    for (const fitting of ["font_hints_auto", "upstream_mono"]) {
      for (const diagonalFitting of [false, true]) {
        Object.assign(defaults, { fitting, diagonalFitting });
        const policy = resolveWorkingPreviewPolicy();
        const variant = defaultVariantSettings({
          id: "fixture", name: "Fixture", fileName: "fixture.ttf", bytes: new ArrayBuffer(0),
          metadata: { names: {}, axes: [] }, source: "uploaded", addedAt: 0,
        });
        const snapshot = defaultSnapshot([], { font: "fixture", profile: "mono_1bit" });
        for (const settings of [variant, snapshot]) {
          const request = toRenderSpec({
            text: "Ag", sizePx: 16, axes: {}, width: 100, height: 40,
            profile: settings.profile, stemFitting: settings.stemFitting,
            diagonalFitting: settings.diagonalFitting, rasterization: settings.rasterization,
          });
          assert.equal(settings.diagonalFitting, policy.diagonal_fitting);
          assert.equal(request.hinting, policy.hinting);
          assert.equal(request.pipeline?.fitting, policy.fitting);
          assert.equal(request.pipeline?.diagonal_fitting ?? false, policy.diagonal_fitting);
        }
      }
    }
  } finally {
    Object.assign(defaults, saved);
  }
});

test("explicit landing overrides stay validated and explicit", () => {
  const policy = resolveWorkingPreviewPolicy({
    fitting: "source_relative",
    rasterization: "free_type_mono",
    diagonalFitting: false,
    dropout: "off",
    includeStubs: false,
    fontInstructions: false,
  });
  assert.equal(policy.fitting, "source_relative");
  assert.equal(policy.rasterization, "free_type_mono");
  assert.equal(policy.diagonal_fitting, false);
  assert.equal(policy.hinting, "auto_fallback");
  assert.deepEqual(policy.mono_raster, { dropout: "off", include_stubs: false, font_instructions: false });
  assert.equal(resolveWorkingPreviewPolicy({ fitting: "upstream_mono" }).hinting, "auto");
});

test("explicit font hints stay on under an automatic-only default", () => {
  const defaults = WORKING_PREVIEW_DEFAULTS as { fitting: string };
  const saved = defaults.fitting;
  try {
    defaults.fitting = "upstream_mono";
    const options = {
      text: "Ag", sizePx: 16, axes: {}, profile: "mono_1bit" as const,
      width: 100, height: 40, rasterization: "free_type_mono" as const,
    };
    assert.equal(toRenderSpec(options).pipeline?.fitting, "upstream_mono");
    const explicit = toRenderSpec({ ...options, stemFitting: "font_hints_first" });
    assert.equal(explicit.pipeline?.fitting, "font_hints_auto");
    assert.equal(explicit.hinting, "auto_fallback");
  } finally {
    defaults.fitting = saved;
  }
});

test("the diagonal overlay needs automatic fitting", () => {
  for (const fitting of ["font_hints_first", "source_relative"]) {
    assert.throws(
      () => resolveWorkingPreviewPolicy({ fitting, diagonalFitting: true }),
      /Diagonal fitting requires/,
    );
  }
  assert.equal(
    resolveWorkingPreviewPolicy({ fitting: "source_relative", diagonalFitting: false }).fitting,
    "source_relative",
  );
});

test("unknown pipeline or scan settings fail", () => {
  assert.throws(() => resolveWorkingPreviewPolicy({ fitting: "cleartype" }), /unknown fitting/);
  assert.throws(() => resolveWorkingPreviewPolicy({ rasterization: "coverage" }), /unknown rasterization/);
  assert.throws(() => resolveWorkingPreviewPolicy({ dropout: "cleartype" }), /unknown dropout/);
  assert.throws(() => resolveWorkingPreviewPolicy({ includeStubs: "yes" as never }), /include_stubs/);
  assert.throws(() => resolveWorkingPreviewPolicy({ fontInstructions: 1 as never }), /font_instructions/);
  assert.throws(() => resolveWorkingPreviewPolicy({ diagonalFitting: 1 as never }), /diagonal_fitting/);
});

test("fingerprints are deterministic over key order and sensitive to content", () => {
  const policy = resolveWorkingPreviewPolicy();
  const reordered = {
    mono_raster: { font_instructions: true, include_stubs: true, dropout: "smart" as const },
    diagonal_fitting: true,
    rasterization: "free_type_mono_terminals" as const,
    fitting: "font_hints_auto" as const,
    hinting: "auto_fallback" as const,
    output_bits: 1 as const,
    mono_threshold: 128 as const,
    gray_gamma: 1 as const,
    missing_glyphs: "error" as const,
    metric_rounding: "subpixel" as const,
  };
  assert.equal(canonicalPreviewPolicyJson(reordered), canonicalPreviewPolicyJson(policy));
  const fingerprint = fingerprintPreviewPolicy(policy);
  assert.match(fingerprint, /^[0-9a-f]{64}$/);
  assert.equal(fingerprintPreviewPolicy(resolveWorkingPreviewPolicy()), fingerprint);
  assert.notEqual(
    fingerprintPreviewPolicy({ ...policy, diagonal_fitting: false }),
    fingerprint,
    "one flipped flag changes the fingerprint",
  );
});

test("the live separated Mono request follows the shared policy", () => {
  const policy = resolveWorkingPreviewPolicy();
  const spec = toRenderSpec({
    text: "Ag", sizePx: 18, axes: {}, profile: "mono_1bit", width: 360, height: 120,
    rasterization: "free_type_mono",
  });
  // URL omission stays diagonal-off, independently of new-preview defaults.
  assert.deepEqual(spec.pipeline, { fitting: policy.fitting, rasterization: policy.rasterization });
  assert.equal(spec.hinting, policy.hinting);
  assert.deepEqual(spec.mono_raster, policy.mono_raster);
  const on = toRenderSpec({
    text: "Ag", sizePx: 18, axes: {}, profile: "mono_1bit", width: 360, height: 120,
    rasterization: "free_type_mono", diagonalFitting: true,
  });
  assert.deepEqual(on.pipeline, {
    fitting: policy.fitting,
    rasterization: policy.rasterization,
    diagonal_fitting: true,
  });
  const off = toRenderSpec({
    text: "Ag", sizePx: 18, axes: {}, profile: "mono_1bit", width: 360, height: 120,
    rasterization: "free_type_mono", diagonalFitting: false,
  });
  assert.deepEqual(off.pipeline, { fitting: policy.fitting, rasterization: policy.rasterization });
  assert.deepEqual(off.mono_raster, policy.mono_raster);
  const forced = toRenderSpec({
    text: "Ag", sizePx: 18, axes: {}, profile: "mono_1bit", width: 360, height: 120,
    rasterization: "free_type_mono", stemFitting: "upstream_mono",
  });
  const forcedPolicy = resolveWorkingPreviewPolicy({ fitting: "upstream_mono", diagonalFitting: false });
  assert.equal(forced.hinting, forcedPolicy.hinting);
  assert.deepEqual(forced.pipeline?.fitting, forcedPolicy.fitting);
});

test("historical and Gray paths bypass the shared Mono policy", () => {
  const base = { text: "Ag", sizePx: 18, axes: {}, width: 360, height: 120 };
  for (const role of ["baseline", "reference", "candidate"] as const) {
    const spec = toRenderSpec({ ...base, role, profile: "mono_1bit" });
    assert.equal("pipeline" in spec, false, `${role} keeps its historical role path`);
  }
  const gray = toRenderSpec({ ...base, profile: "gray_3bit", rasterization: "free_type_mono" });
  assert.deepEqual(gray.pipeline, { fitting: "upstream_mono", rasterization: "coverage" });
  assert.equal("mono_raster" in gray, false);
  const manual = toRenderSpec({
    ...base, role: "candidate", profile: "mono_1bit",
    monoRaster: { dropout: "off", includeStubs: false, fontInstructions: false },
  });
  assert.deepEqual(manual.mono_raster, { dropout: "off", include_stubs: false, font_instructions: false });
});
