import assert from "node:assert/strict";
import test from "node:test";
import {
  cloneKerning, decodeKerning, defaultKerningState, editKerning, encodeKerning,
  isDefaultKerning, isKerningMethod, KERNING_METHODS, normalizeKerning, resolveKerning, selectKerningMethod,
  validateKerningPreference,
} from "../../src/app/kerning/model.ts";

test("historical kerning booleans retain the exact source request", () => {
  for (const enabled of [true, false]) {
    assert.deepEqual(resolveKerning(enabled), { kerning: enabled });
    assert.deepEqual(resolveKerning(normalizeKerning(enabled)), { kerning: enabled });
    assert.equal(decodeKerning(encodeKerning(enabled)), enabled);
  }
  assert.ok(isDefaultKerning(true));
  assert.ok(isDefaultKerning(defaultKerningState()));
  assert.ok(!isDefaultKerning(false));
});

test("historical two-method values migrate without changing their active request", () => {
  const historical = {
    method: "typefacet" as const, source: { enabled: false },
    typefacet: { normalDistanceEm: 0.175, intrusionToleranceEm: 0.025 },
  };
  const migrated = normalizeKerning(historical);
  assert.deepEqual(migrated.hu_hersch, { strength: 1 });
  assert.deepEqual(migrated.fontforge, { strength: 1 });
  assert.deepEqual(migrated.typefacet, { ...defaultKerningState().typefacet, ...historical.typefacet });
  assert.equal(migrated.method, "typefacet");
  assert.deepEqual(resolveKerning(historical), resolveKerning(migrated));
  assert.deepEqual(decodeKerning(JSON.stringify(historical)), migrated);
  assert.deepEqual(resolveKerning({ ...historical, method: "source" }), { kerning: false });
});

test("all compiled methods retain independent settings and only emit their active request", () => {
  const typefacet = editKerning(selectKerningMethod(false, "typefacet"), {
    method: "typefacet", settings: { normalDistanceEm: 0.15, intrusionToleranceEm: 0.025 },
  });
  const state = editKerning(selectKerningMethod(typefacet, "fontforge"), {
    method: "fontforge", settings: { strength: 0.35 },
  });
  assert.deepEqual(Object.keys(KERNING_METHODS), ["source", "typefacet", "hu_hersch", "fontforge"]);
  assert.equal(isKerningMethod("counterspace"), false, "unported Python engines are not working editor options");
  for (const method of Object.keys(KERNING_METHODS)) {
    assert.ok(isKerningMethod(method));
    const selected = selectKerningMethod(state, method);
    assert.deepEqual(decodeKerning(encodeKerning(selected)), selected);
    const inactiveChanged = {
      ...selected,
      ...(method !== "source" ? { source: { enabled: true } } : {}),
      ...(method !== "typefacet" ? { typefacet: { normalDistanceEm: 0.3, intrusionToleranceEm: 0.2 } } : {}),
      ...(method !== "hu_hersch" ? { hu_hersch: { strength: 0.25 } } : {}),
      ...(method !== "fontforge" ? { fontforge: { strength: 0.9 } } : {}),
    };
    assert.deepEqual(resolveKerning(inactiveChanged), resolveKerning(selected), "inactive settings cannot affect request/cache identity");
    assert.equal(selected.fontforge.strength, 0.35);
    assert.equal(selected.typefacet.normalDistanceEm, 0.15);
    if (method !== "fontforge") {
      assert.throws(() => editKerning(selected, { method: "fontforge", settings: { strength: 0.5 } }), /no longer active/);
    }
  }
  assert.deepEqual(resolveKerning(state), { kerning: true, kerning_method: { method: "fontforge", strength: 0.35 } });
  assert.deepEqual(resolveKerning(selectKerningMethod(state, "hu_hersch")), { kerning: true, kerning_method: { method: "hu_hersch", strength: 1 } });
  assert.deepEqual(resolveKerning(selectKerningMethod(state, "source")), { kerning: false });
  const copy = normalizeKerning(state);
  copy.fontforge.strength = 0.6;
  assert.equal(state.fontforge.strength, 0.35);
});

test("method switches retain independent settings and resolve only the active method", () => {
  const sourceOff = normalizeKerning(false);
  const active = selectKerningMethod(sourceOff, "typefacet");
  const edited = editKerning(active, {
    method: "typefacet", settings: { normalDistanceEm: 0.2, intrusionToleranceEm: 0.025 },
  });
  assert.deepEqual(resolveKerning(edited), {
    kerning: true,
    kerning_method: { method: "typefacet", normal_distance_em: 0.2, intrusion_tolerance_em: 0.025, minimum_distance_em: 0, max_x_extrema_overlap_em: 0.1 },
  });
  const restored = selectKerningMethod(edited, "source");
  assert.deepEqual(resolveKerning(restored), { kerning: false });
  assert.deepEqual(selectKerningMethod(restored, "typefacet"), edited);
  assert.deepEqual(sourceOff, normalizeKerning(false), "edits do not mutate the previous state");
  assert.deepEqual(decodeKerning(encodeKerning(restored)), restored, "inactive settings survive encoding");
  assert.throws(() => editKerning(restored, {
    method: "typefacet", settings: { normalDistanceEm: 0.3, intrusionToleranceEm: 0.1 },
  }), /no longer active/);
});

test("kerning settings are copied and malformed active or retained settings are rejected", () => {
  const state = defaultKerningState();
  const copy = cloneKerning(state);
  assert.equal(typeof copy, "object");
  if (typeof copy === "boolean") throw new Error("expected method state");
  copy.source.enabled = false;
  copy.typefacet.normalDistanceEm = 0.3;
  assert.deepEqual(state, defaultKerningState());
  for (const invalid of [
    { ...state, method: "unknown" },
    { ...state, source: { enabled: "true" } },
    { ...state, typefacet: { ...state.typefacet, normalDistanceEm: NaN } },
    { ...state, typefacet: { ...state.typefacet, normalDistanceEm: 0.009 } },
    { ...state, typefacet: { ...state.typefacet, intrusionToleranceEm: 0.501 } },
    { ...state, typefacet: { ...state.typefacet, intrusionToleranceEm: -0.01 } },
    { ...state, typefacet: { ...state.typefacet, minimumDistanceEm: -0.01 } },
    { ...state, typefacet: { ...state.typefacet, minimumDistanceEm: 0.11 } },
    { ...state, typefacet: { ...state.typefacet, minimumDistanceEm: NaN } },
    { ...state, typefacet: { ...state.typefacet, minimumDistanceEm: null } },
    { ...state, typefacet: { ...state.typefacet, maxXExtremaOverlapEm: -0.01 } },
    { ...state, typefacet: { ...state.typefacet, maxXExtremaOverlapEm: 0.501 } },
    { ...state, typefacet: { ...state.typefacet, maxXExtremaOverlapEm: NaN } },
    { ...state, typefacet: { ...state.typefacet, maxXExtremaOverlapEm: null } },
    { ...state, hu_hersch: null },
    { ...state, hu_hersch: { strength: NaN } },
    { ...state, hu_hersch: { strength: -0.01 } },
    { ...state, hu_hersch: { strength: 1.01 } },
    { ...state, hu_hersch: { strength: null } },
    { ...state, hu_hersch: { strength: "0.5" } },
    { ...state, hu_hersch: { strength: 0.5, depth: 0.21 } },
    { ...state, fontforge: null },
    { ...state, fontforge: { strength: NaN } },
    { ...state, fontforge: { strength: -0.01 } },
    { ...state, fontforge: { strength: 1.01 } },
  ]) {
    assert.throws(() => validateKerningPreference(invalid));
    assert.equal(decodeKerning(JSON.stringify(invalid)), null);
  }
  validateKerningPreference({ ...state, typefacet: { normalDistanceEm: 0.01, intrusionToleranceEm: 0 } });
  validateKerningPreference({ ...state, typefacet: { normalDistanceEm: 0.5, intrusionToleranceEm: 0.5 } });
  validateKerningPreference({ ...state, fontforge: { strength: 0 } });
  validateKerningPreference({ ...state, fontforge: { strength: 1 } });
  validateKerningPreference({ ...state, hu_hersch: { strength: 0 } });
  validateKerningPreference({ ...state, hu_hersch: { strength: 1 } });
});

test("Hu/Hersch legacy settings migrate to full correction and strength survives independent method edits", () => {
  const base = { ...defaultKerningState(), method: "hu_hersch" as const };
  for (const hu_hersch of [undefined, {}]) {
    const legacy = { ...base, hu_hersch };
    assert.deepEqual(normalizeKerning(legacy).hu_hersch, { strength: 1 });
    assert.deepEqual(resolveKerning(legacy), { kerning: true, kerning_method: { method: "hu_hersch", strength: 1 } });
    assert.deepEqual(decodeKerning(JSON.stringify(legacy)), normalizeKerning(base));
  }
  const active = editKerning(selectKerningMethod(false, "hu_hersch"), {
    method: "hu_hersch", settings: { strength: 0.35 },
  });
  const copy = cloneKerning(active);
  assert.notEqual(typeof copy, "boolean");
  if (typeof copy === "boolean") throw new Error("expected independent settings");
  copy.hu_hersch = { strength: 0.9 };
  assert.equal(active.hu_hersch.strength, 0.35);
  assert.deepEqual(decodeKerning(encodeKerning(active)), active);
  assert.deepEqual(selectKerningMethod(selectKerningMethod(active, "fontforge"), "hu_hersch"), active);
  for (const strength of [0, 0.35, 1]) {
    const edited = editKerning(active, { method: "hu_hersch", settings: { strength } });
    assert.deepEqual(resolveKerning(edited), { kerning: true, kerning_method: { method: "hu_hersch", strength } });
    assert.equal(edited.source.enabled, false, "the inactive Source switch remains independent");
  }
  assert.throws(() => editKerning(selectKerningMethod(active, "source"), {
    method: "hu_hersch", settings: { strength: 0.5 },
  }), /no longer active/);
});


test("new TypeFacet controls survive legacy edits, switching and exact off-step round trips", () => {
  const active = editKerning(selectKerningMethod(true, "typefacet"), {
    method: "typefacet", settings: { normalDistanceEm: 0.0925, intrusionToleranceEm: 0.03125,
      minimumDistanceEm: 0.0175, maxXExtremaOverlapEm: 0.125 },
  });
  const edited = editKerning(active, { method: "typefacet", settings: {
    normalDistanceEm: 0.15, intrusionToleranceEm: 0.03125,
  } });
  assert.equal(edited.typefacet.minimumDistanceEm, 0.0175);
  assert.equal(edited.typefacet.maxXExtremaOverlapEm, 0.125);
  assert.deepEqual(editKerning(active, { method: "typefacet", settings: {
    ...active.typefacet, minimumDistanceEm: undefined, maxXExtremaOverlapEm: undefined,
  } }), active);
  assert.deepEqual(decodeKerning(encodeKerning(active)), active);
  assert.deepEqual(selectKerningMethod(selectKerningMethod(active, "source"), "typefacet"), active);
  assert.deepEqual(resolveKerning(active).kerning_method, { method: "typefacet", normal_distance_em: 0.0925,
    intrusion_tolerance_em: 0.03125, minimum_distance_em: 0.0175, max_x_extrema_overlap_em: 0.125 });
  assert.throws(() => editKerning(active, { method: "typefacet", settings: {
    normalDistanceEm: 0.01, intrusionToleranceEm: 0.03125,
  } }), /minimum clearance/);
  validateKerningPreference({ ...active, typefacet: { ...active.typefacet,
    minimumDistanceEm: active.typefacet.normalDistanceEm, maxXExtremaOverlapEm: 0.5 } });
});
