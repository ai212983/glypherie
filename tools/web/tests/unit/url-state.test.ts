import assert from "node:assert/strict";
import test from "node:test";
import {
  defaultSnapshot,
  encodeHashSearch,
  encodeUrlSnapshot,
  parseLegacyState,
  parseUrlSnapshot,
  type FamilyMeta,
  type FamilySnapshot,
  type GlobalDefaults,
  type PreviewSnapshot,
} from "../../src/app/features/preview/state/snapshot-codec.ts";
import { detailHash, indexHash } from "../../src/app/navigation/router.ts";

const METAS: FamilyMeta[] = [
  {
    id: "alpha",
    defaultSize: 16,
    defaultAxes: { wght: 400, wdth: 100, XOPQ: 96 },
    axes: [
      { tag: "wght", min: 100, max: 900, defaultValue: 400, hidden: false },
      { tag: "wdth", min: 62.5, max: 100, defaultValue: 100, hidden: false },
      { tag: "XOPQ", min: 27, max: 175, defaultValue: 96, hidden: true },
    ],
    sampleText: "Alpha sample\nSecond line",
    presets: [
      { id: "reading", content: "Alpha sample\nSecond line" },
      { id: "numbers", content: "0123456789" },
    ],
    defaultPreset: "reading",
  },
  {
    id: "beta",
    defaultSize: 16,
    defaultAxes: {},
    axes: [],
    sampleText: "Beta sample",
    presets: [
      { id: "reading", content: "Alpha sample\nSecond line" },
      { id: "numbers", content: "0123456789" },
    ],
    defaultPreset: "custom",
  },
];
const DEFAULTS: GlobalDefaults = { font: "alpha", profile: "mono_1bit", zoom: 1 };

function familyOf(snapshot: PreviewSnapshot, id: string): FamilySnapshot {
  const family = snapshot.families[id];
  assert.ok(family, `expected family ${id}`);
  return family;
}

function snapshot(): PreviewSnapshot {
  const value = defaultSnapshot(METAS, DEFAULTS);
  value.font = "beta";
  value.profile = "gray_3bit";
  value.zoom = 3;
  value.pixelAccurate = true;
  value.stemFitting = "upstream_mono";
  value.kerning = false;
  value.families.alpha = {
    size: 24, axes: { wght: 700, wdth: 80, XOPQ: 130 }, spacing: 2,
    preset: "custom", text: "Héllo 🌍\nSecond ß line",
    advancedOpen: true, kerningOpen: true, kerningFilter: "AV",
  };
  value.families.beta = {
    size: 19, axes: {}, spacing: -0.5,
    preset: "numbers", text: "0123456789",
    advancedOpen: false, kerningOpen: false, kerningFilter: "",
  };
  return value;
}

test("encode writes explicit v1 values for every family and preserves unknown params", () => {
  const params = encodeUrlSnapshot(snapshot(), "?utm=keep&profile=mono_1bit&extra=1", ["alpha", "beta"]);
  assert.equal(params.get("utm"), "keep");
  assert.equal(params.get("extra"), "1");
  assert.equal(params.get("v"), "1");
  assert.equal(params.get("font"), "beta");
  assert.equal(params.get("profile"), "gray_3bit");
  assert.equal(params.get("zoom"), "3");
  assert.equal(params.get("exact"), "1");
  assert.equal(params.get("stem"), "upstream_mono");
  assert.equal(params.get("model"), null, "obsolete model is dropped on write");
  assert.equal(params.get("kerning"), "0");
  const familiesParam = params.get("families");
  assert.ok(familiesParam, "families are encoded");
  const families = JSON.parse(familiesParam) as Record<string, FamilySnapshot>;
  assert.deepEqual(Object.keys(families), ["alpha", "beta"]);
  const alpha = families.alpha;
  assert.ok(alpha);
  assert.equal(alpha.text, "Héllo 🌍\nSecond ß line");
  assert.equal(alpha.axes.XOPQ, 130, "hidden axis is explicit");
  const beta = families.beta;
  assert.ok(beta);
  assert.equal(beta.text, "0123456789", "actual text is stored beside its preset");
});

test("parse round-trips every control including inactive families and Unicode text", () => {
  const original = snapshot();
  const search = `?${encodeUrlSnapshot(original, "", ["alpha", "beta"]).toString()}`;
  const parsed = parseUrlSnapshot(search, "#family-beta", METAS, DEFAULTS);
  assert.deepEqual(parsed, original);
});

test("defaults are explicit so another browser's preferences cannot leak in", () => {
  const value = defaultSnapshot(METAS, DEFAULTS);
  const search = `?${encodeUrlSnapshot(value, "", ["alpha", "beta"]).toString()}`;
  const parsed = parseUrlSnapshot(search, "", METAS, { font: "beta", profile: "gray_3bit", zoom: 4 });
  assert.ok(parsed);
  assert.equal(parsed.font, "alpha");
  assert.equal(parsed.profile, "mono_1bit");
  assert.equal(parsed.zoom, 1);
  assert.equal(parsed.pixelAccurate, false);
  assert.equal(parsed.stemFitting, "font_hints_first");
  assert.equal(familyOf(parsed, "alpha").preset, "reading");
  assert.equal(familyOf(parsed, "alpha").text, "Alpha sample\nSecond line");
  assert.equal(familyOf(parsed, "beta").size, 16);
});

test("unknown or malformed versions fall back without throwing", () => {
  assert.equal(parseUrlSnapshot("?v=2&font=beta", "", METAS, DEFAULTS), null);
  assert.equal(parseUrlSnapshot("?v=abc", "", METAS, DEFAULTS), null);
  assert.equal(parseUrlSnapshot("?profile=gray_3bit", "", METAS, DEFAULTS), null);
  const parsed = parseUrlSnapshot("?v=1&families=%7Bbroken", "#family-beta", METAS, DEFAULTS);
  assert.ok(parsed);
  assert.equal(parsed.font, "beta", "hash still selects the font");
  assert.equal(familyOf(parsed, "alpha").text, "Alpha sample\nSecond line");
});

test("validation clamps numbers, drops unknown fonts/axes and rejects bad enums", () => {
  const families = JSON.stringify({
    alpha: {
      size: 9999, axes: { wght: 9999, wdth: "bad", NOPE: 1, XOPQ: 10 },
      spacing: 99, preset: "nope", text: 42,
      advancedOpen: "yes", kerningOpen: true, kerningFilter: 7,
    },
    ghost: { size: 20, text: "Ghost" },
  });
  const search = `?v=1&font=ghost&profile=nope&zoom=9&exact=maybe&stem=nope&model=nope&kerning=maybe&families=${encodeURIComponent(families)}`;
  const parsed = parseUrlSnapshot(search, "", METAS, DEFAULTS);
  assert.ok(parsed);
  assert.equal(parsed.font, "alpha");
  assert.equal(parsed.profile, "mono_1bit");
  assert.equal(parsed.zoom, 1);
  assert.equal(parsed.pixelAccurate, false);
  assert.equal(parsed.stemFitting, "font_hints_first");
  assert.equal("spacingModel" in parsed, false);
  assert.equal(parsed.kerning, true);
  const alpha = familyOf(parsed, "alpha");
  assert.equal(alpha.size, 512);
  assert.equal(alpha.axes.wght, 900);
  assert.equal(alpha.axes.wdth, 100);
  assert.equal(alpha.axes.XOPQ, 27);
  assert.equal("NOPE" in alpha.axes, false);
  assert.equal(alpha.spacing, 4);
  assert.equal(alpha.text, "Alpha sample\nSecond line");
  assert.equal(alpha.advancedOpen, false);
  assert.equal(alpha.kerningOpen, true);
  assert.equal(alpha.kerningFilter, "");
  assert.equal("ghost" in parsed.families, false);
});

test("obsolete spacing-model parameters in old links are ignored and dropped", () => {
  const parsed = parseUrlSnapshot("?v=1&font=beta&model=projected&kerning=0", "", METAS, DEFAULTS);
  assert.ok(parsed);
  assert.equal(parsed.font, "beta");
  assert.equal(parsed.kerning, false);
  assert.equal("spacingModel" in parsed, false);
  const encoded = encodeUrlSnapshot(parsed, "?model=fitted&utm=keep", ["alpha", "beta"]);
  assert.equal(encoded.get("model"), null);
  assert.equal(encoded.get("utm"), "keep");
  assert.equal(encoded.get("kerning"), "0");
});

test("legacy profile, zoom and hash selection stay readable", () => {
  assert.deepEqual(
    parseLegacyState("?profile=gray_3bit&zoom=3", "#family-beta", METAS),
    { font: "beta", profile: "gray_3bit", zoom: 3 },
  );
  assert.deepEqual(parseLegacyState("?profile=nope&zoom=9", "#family-ghost", METAS), {});
  assert.deepEqual(parseLegacyState("", "#other", METAS), {});
});

test("minimal font links select known fonts and ignore unknown ones", () => {
  assert.deepEqual(parseLegacyState("?font=beta", "", METAS), { font: "beta" });
  assert.deepEqual(
    parseLegacyState("?font=beta&profile=gray_3bit&zoom=3", "", METAS),
    { font: "beta", profile: "gray_3bit", zoom: 3 },
  );
  assert.deepEqual(parseLegacyState("?font=ghost", "#family-beta", METAS), { font: "beta" });
  assert.deepEqual(parseLegacyState("?font=ghost", "", METAS), {});
});

test("detail links name the font and index links drop snapshot state", () => {
  assert.equal(detailHash("beta"), "#/font/beta/");
  assert.equal(indexHash("?v=1&font=beta&profile=mono_1bit&utm=keep"), "#/?utm=keep");
  assert.equal(indexHash("?v=1&font=beta"), "#/");
  assert.equal(indexHash(""), "#/");
});

test("hash search carries versioned state without the font identity", () => {
  const params = encodeHashSearch(snapshot(), "", ["alpha", "beta"]);
  assert.equal(params.get("v"), "1");
  assert.equal(params.get("font"), null, "the hash path carries the font identity");
  assert.equal(params.get("profile"), "gray_3bit");
  const families = JSON.parse(params.get("families") ?? "{}") as Record<string, FamilySnapshot>;
  assert.deepEqual(Object.keys(families), ["alpha", "beta"]);
});
