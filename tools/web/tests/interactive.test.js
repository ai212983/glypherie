import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  buildInteractive,
  publishInteractive,
  resolveFontFile,
  validateInteractive,
} from "../lib/interactive.js";
import {
  filterKerningPairs,
  formatKerningAdjustment,
  kerningCacheKey,
  logicalBounds,
  pairCodepoints,
  toRenderSpec,
} from "../assets/interactive.js";
import { hash } from "./helpers.js";

const bytes = (text) => Buffer.from(text);

function viewFamily(overrides = {}) {
  return {
    id: "alpha",
    name: "Alpha",
    source_sha256: hash(bytes("font-a")),
    metadata: {
      axes: [
        { tag: "wght", name: "Weight", min: 100, default: 400, max: 900, hidden: false },
        { tag: "opsz", name: "Optical size", min: 8, default: 14, max: 72, hidden: true },
      ],
    },
    sizes: [{
      size_px: 14,
      axes: { wght: 400, opsz: 14 },
      items: [{ id: "reading", profile: "mono_1bit", label: "Reading", text: "Pack my box.\nSecond line" }],
    }],
    ...overrides,
  };
}

const roots = { configDir: "/repo/tools/generator", repoRoot: "/repo" };
const reader = (files) => async (file) => {
  if (!Object.hasOwn(files, file)) throw Object.assign(new Error("missing"), { code: "ENOENT" });
  return files[file];
};

test("publishes hashed font bytes with published defaults and visible axes only", async () => {
  const file = "/repo/fonts/A.ttf";
  const result = await buildInteractive({
    viewFamilies: [viewFamily()],
    configFamilies: [{ id: "alpha", font: "../../fonts/A.ttf" }],
    profiles: [
      { id: "mono_1bit", output_bits: 1, mono_threshold: 200, gray_gamma: 1.0 },
      { id: "gray_3bit", output_bits: 3, mono_threshold: 128, gray_gamma: 2.2 },
    ],
    ...roots,
    readFont: reader({ [file]: bytes("font-a") }),
  });
  assert.equal(result.doc.schema_version, "web-interactive-v1");
  const [entry] = result.doc.families;
  assert.equal(entry.available, true);
  assert.equal(entry.fontUrl, "./interactive-fonts/alpha.ttf");
  assert.equal(entry.default_size_px, 14);
  assert.deepEqual(entry.default_axes, { wght: 400, opsz: 14 });
  assert.equal(entry.sample_text, "Pack my box.\nSecond line");
  assert.deepEqual(entry.axes, [{ tag: "wght", name: "Weight", min: 100, default: 400, max: 900, step: 1 }]);
  assert.deepEqual(entry.render, { hinting: "auto", mono_threshold: 200, gray_gamma: 2.2 });
  assert.deepEqual(result.fonts, [{ target: "interactive-fonts/alpha.ttf", bytes: bytes("font-a") }]);
});

test("marks families unavailable on hash mismatch, missing files, or bad references", async () => {
  const file = "/repo/fonts/A.ttf";
  const read = reader({ [file]: bytes("other-bytes") });
  const cases = [
    [{ id: "alpha", font: "../../fonts/A.ttf" }, "hash mismatch"],
    [{ id: "alpha", font: "../../fonts/missing.ttf" }, "missing file"],
    [{ id: "alpha", font: "../../../etc/passwd" }, "traversal"],
    [{ id: "alpha", font: "/etc/passwd" }, "absolute path"],
    [{ id: "alpha", font: "../../fonts/A.ttc" }, "unsupported extension"],
    [{ id: "alpha" }, "missing reference"],
    [{ id: "other", font: "../../fonts/A.ttf" }, "unconfigured family"],
  ];
  for (const [config, label] of cases) {
    const id = config.id === "other" ? "beta" : "alpha";
    const result = await buildInteractive({
      viewFamilies: [viewFamily({ id })],
      configFamilies: [config],
      profiles: [],
      ...roots,
      readFont: read,
    });
    assert.equal(result.doc.families[0].available, false, label);
    assert.match(result.doc.families[0].reason, /unavailable|not configured/, label);
    assert.deepEqual(result.fonts, [], label);
  }
});

test("rejects unsafe font references without reading", () => {
  assert.equal(resolveFontFile(roots.configDir, roots.repoRoot, "../../fonts/A.ttf"), "/repo/fonts/A.ttf");
  assert.equal(resolveFontFile(roots.configDir, roots.repoRoot, "../../../etc/passwd"), null);
  assert.equal(resolveFontFile(roots.configDir, roots.repoRoot, "/etc/passwd"), null);
  assert.equal(resolveFontFile(roots.configDir, roots.repoRoot, "../../fonts/A.ttc"), null);
  assert.equal(resolveFontFile(roots.configDir, roots.repoRoot, ""), null);
  assert.equal(resolveFontFile(roots.configDir, roots.repoRoot, null), null);
});

test("passes config card presets through to each family", async () => {
  const file = "/repo/fonts/A.ttf";
  const cards = [
    { id: "reading", title: "Reading sample", content: "Pack my box.\nSecond line" },
    { id: "numbers", title: "Numbers and symbols", content: "0123456789" },
    { id: "../escape", title: "Bad", content: "x" },
    { id: "empty", title: "Empty", content: "" },
  ];
  const result = await buildInteractive({
    viewFamilies: [viewFamily()],
    configFamilies: [{ id: "alpha", font: "../../fonts/A.ttf" }],
    profiles: [],
    cards,
    ...roots,
    readFont: reader({ [file]: bytes("font-a") }),
  });
  assert.deepEqual(result.doc.families[0].presets, [
    { id: "reading", title: "Reading sample", content: "Pack my box.\nSecond line" },
    { id: "numbers", title: "Numbers and symbols", content: "0123456789" },
  ]);
  assert.equal(result.doc.families[0].default_preset, "reading");
});

test("unmatched sample text falls back to the custom preset", async () => {
  const file = "/repo/fonts/A.ttf";
  const result = await buildInteractive({
    viewFamilies: [viewFamily({ sizes: [{
      size_px: 14, axes: { wght: 400 }, thumbnail: { width_px: 2, height_px: 2 },
      items: [{ id: "other", profile: "mono_1bit", label: "Other", text: "Unlisted words" }],
    }] })],
    configFamilies: [{ id: "alpha", font: "../../fonts/A.ttf" }],
    profiles: [],
    cards: [{ id: "reading", title: "Reading sample", content: "Pack my box." }],
    ...roots,
    readFont: reader({ [file]: bytes("font-a") }),
  });
  assert.equal(result.doc.families[0].sample_text, "Unlisted words");
  assert.equal(result.doc.families[0].default_preset, "custom");
});

test("falls back to default render options without profiles", async () => {
  const file = "/repo/fonts/A.ttf";
  const result = await buildInteractive({
    viewFamilies: [viewFamily()],
    configFamilies: [{ id: "alpha", font: "../../fonts/A.ttf" }],
    profiles: [],
    ...roots,
    readFont: reader({ [file]: bytes("font-a") }),
  });
  assert.deepEqual(result.doc.families[0].render, { hinting: "auto", mono_threshold: 128, gray_gamma: 1.0 });
});

test("maps control state to the exact tools/wasm render request", () => {
  const spec = toRenderSpec({
    text: "Ag", sizePx: 18, axes: { wght: 700 }, profile: "gray_3bit",
    render: { mono_threshold: 200, gray_gamma: 2.2 }, width: 360, height: 120,
  });
  assert.deepEqual(spec, {
    text: "Ag", width: 360, height: 120, size_px: 18, axes: { wght: 700 }, hinting: "auto", output_bits: 3,
    mono_threshold: 200, gray_gamma: 2.2, missing_glyphs: "error", kerning: true, metric_rounding: "subpixel",
    wrap: "word", align: "left", foreground: [36, 40, 43, 255], background: [255, 255, 255, 255],
    letter_spacing_px: 0, spacing_model: "auto", renderer: "baseline",
  });
  assert.equal(toRenderSpec({
    text: "Ag", sizePx: 18, axes: {}, profile: "mono_1bit", width: 360, height: 120, letterSpacingPx: 1.5,
  }).letter_spacing_px, 2);
  assert.equal(toRenderSpec({
    text: "Ag", sizePx: 18, axes: {}, profile: "mono_1bit", width: 360, height: 120, letterSpacingPx: -0.5,
  }).letter_spacing_px, -1);
  assert.equal(toRenderSpec({
    text: "Ag", sizePx: 18, axes: {}, profile: "gray_3bit", width: 360, height: 120, letterSpacingPx: -0.5,
  }).letter_spacing_px, -0.5);
  for (const model of ["auto", "source", "fitted", "projected"]) {
    const options = { text: "AV", sizePx: 14, axes: {}, width: 360, height: 120, spacingModel: model };
    assert.equal(toRenderSpec({ ...options, profile: "mono_1bit" }).spacing_model, model);
    assert.equal(toRenderSpec({ ...options, profile: "gray_3bit" }).spacing_model, "auto");
    assert.equal(toRenderSpec({ ...options, profile: "mono_1bit", kerning: false }).kerning, false);
  }
  assert.equal(toRenderSpec({
    text: "Ag", sizePx: 18, axes: {}, profile: "mono_1bit", width: 360, height: 120, letterSpacingPx: 99,
  }).letter_spacing_px, 4);
  assert.equal(toRenderSpec({
    text: "Ag", sizePx: 18, axes: {}, profile: "mono_1bit", width: 360, height: 120, letterSpacingPx: "bad",
  }).letter_spacing_px, 0);
  const candidate = toRenderSpec({
    text: "Ag", sizePx: 18, axes: { wght: 700 }, profile: "mono_1bit",
    render: { mono_threshold: 200, gray_gamma: 2.2 }, width: 360, height: 120, role: "candidate",
  });
  assert.equal(candidate.renderer, "candidate");
  assert.equal(candidate.output_bits, 1);
  assert.deepEqual([candidate.text, candidate.size_px, candidate.axes],
    [spec.text, spec.size_px, spec.axes]);
  const mono = toRenderSpec({ text: "", sizePx: 16, axes: {}, profile: "mono_1bit", width: 0.4, height: 5000 });
  assert.equal(mono.output_bits, 1);
  assert.equal(mono.width, 1);
  assert.equal(mono.height, 4096);
  assert.equal(mono.text, "");
});

test("formats kerning adjustments as signed pixels at 26.6 precision", () => {
  assert.equal(formatKerningAdjustment(-52), "-0.8125 px");
  assert.equal(formatKerningAdjustment(64), "+1 px");
  assert.equal(formatKerningAdjustment(-64), "-1 px");
  assert.equal(formatKerningAdjustment(1), "+0.015625 px");
  assert.equal(pairCodepoints(0x41, 0x56), "U+0041 U+0056");
  assert.equal(pairCodepoints(0x20, 0x7e), "U+0020 U+007E");
});

test("keys kerning cache by size and axes independent of key order", () => {
  assert.equal(kerningCacheKey(16, { wght: 400 }), kerningCacheKey(16, { wght: 400 }));
  assert.notEqual(kerningCacheKey(16, { wght: 400 }), kerningCacheKey(18, { wght: 400 }));
  assert.notEqual(kerningCacheKey(16, { wght: 400 }), kerningCacheKey(16, { wght: 700 }));
  assert.equal(
    kerningCacheKey(16, { wght: 400, wdth: 100 }),
    kerningCacheKey(16, { wdth: 100, wght: 400 }),
  );
});

test("filters kerning pairs by characters or codepoints", () => {
  const pairs = [
    { left: 0x41, right: 0x56, adjustment_26_6: -52 },
    { left: 0x54, right: 0x6f, adjustment_26_6: -20 },
  ];
  assert.equal(filterKerningPairs(pairs, "").length, 2);
  assert.deepEqual(filterKerningPairs(pairs, "AV"), [pairs[0]]);
  assert.deepEqual(filterKerningPairs(pairs, "av"), [pairs[0]]);
  assert.deepEqual(filterKerningPairs(pairs, "0041"), [pairs[0]]);
  assert.deepEqual(filterKerningPairs(pairs, "To"), [pairs[1]]);
  assert.deepEqual(filterKerningPairs(pairs, "zz"), []);
});

test("derives shrunken logical bounds for integer magnification", () => {
  assert.equal(logicalBounds(720, 1), 720);
  assert.equal(logicalBounds(721, 2), 361);
  assert.equal(logicalBounds(240, 4), 60);
  assert.equal(logicalBounds(0, 2), 1);
  assert.equal(logicalBounds(9000, 1), 4096);
});

test("publishes interactive.json and font bytes, rejecting invalid documents", async (t) => {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), "font-interactive-test-"));
  t.after(() => fs.rm(temp, { recursive: true, force: true }));
  const file = "/repo/fonts/A.ttf";
  const result = await buildInteractive({
    viewFamilies: [viewFamily()],
    configFamilies: [{ id: "alpha", font: "../../fonts/A.ttf" }],
    profiles: [],
    ...roots,
    readFont: reader({ [file]: bytes("font-a") }),
  });
  await publishInteractive(result, temp);
  const doc = JSON.parse(await fs.readFile(path.join(temp, "interactive.json"), "utf8"));
  validateInteractive(doc);
  assert.deepEqual(await fs.readFile(path.join(temp, "interactive-fonts/alpha.ttf")), bytes("font-a"));
  assert.throws(() => validateInteractive({ schema_version: "other", families: [] }), /format/);
  assert.throws(() => validateInteractive({
    schema_version: "web-interactive-v1",
    families: [{ id: "alpha", available: true, presets: [], default_preset: "custom" }],
  }), /source/);
  assert.throws(() => validateInteractive({
    schema_version: "web-interactive-v1",
    families: [{ id: "alpha", available: false }],
  }), /Invalid interactive/);
});
