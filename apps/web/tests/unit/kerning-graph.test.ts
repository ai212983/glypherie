import assert from "node:assert/strict";
import test from "node:test";
import { kerningPreferenceSchema } from "../../src/app/domain/graph.ts";
import { defaultKerningState } from "../../src/app/kerning/model.ts";

function current(method: string): Record<string, unknown> {
  return { ...defaultKerningState(), method } as unknown as Record<string, unknown>;
}

test("domain graph persistence accepts current kerning settings", () => {
  assert.equal(kerningPreferenceSchema.safeParse(true).success, true);
  assert.equal(kerningPreferenceSchema.safeParse(false).success, true);
  for (const method of ["source", "typefacet", "hu_hersch", "fontforge"] as const) {
    const parsed = kerningPreferenceSchema.safeParse(current(method));
    assert.equal(parsed.success, true, `${method} must persist`);
  }
  const omitted = { ...current("hu_hersch"), hu_hersch: {} };
  assert.equal(kerningPreferenceSchema.safeParse(omitted).success, true, "omitted depths keep their defaults");
});

test("domain graph persistence rejects the retired strength blend at admission", () => {
  for (const strength of [0, 0.35, 1, null, "0.35", true]) {
    const hu = { ...current("hu_hersch"), hu_hersch: { strength } };
    assert.equal(
      kerningPreferenceSchema.safeParse(hu).success, false,
      `hu_hersch strength ${String(strength)} must not persist`,
    );
    const retained = { ...current("source"), hu_hersch: { strength } };
    assert.equal(
      kerningPreferenceSchema.safeParse(retained).success, false,
      `retained hu_hersch strength ${String(strength)} must not persist`,
    );
    const forge = { ...current("fontforge"), fontforge: { strength } };
    assert.equal(
      kerningPreferenceSchema.safeParse(forge).success, false,
      `fontforge strength ${String(strength)} must not persist`,
    );
    const retainedForge = { ...current("source"), fontforge: { strength } };
    assert.equal(
      kerningPreferenceSchema.safeParse(retainedForge).success, false,
      `retained fontforge strength ${String(strength)} must not persist`,
    );
  }
  const blended = {
    ...current("hu_hersch"),
    hu_hersch: { apertureDepthFactor: 0.21, globalDepthFactor: 0.25, strength: 1 },
  };
  assert.equal(kerningPreferenceSchema.safeParse(blended).success, false);
});
