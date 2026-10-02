import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright-core";
import { PNG } from "pngjs";
import { build, fixture, hash, png, serve } from "./helpers.js";
import { fontMetadata } from "./helpers.js";

const browserPath = process.env.WEB_TEST_BROWSER ?? "/opt/google/chrome/chrome";
const browserAvailable = await fs.access(browserPath).then(() => true, () => false);

const STUB_WASM = `
const KNOWN = new Set(["text", "width", "height", "size_px", "axes", "hinting", "output_bits",
  "mono_threshold", "gray_gamma", "missing_glyphs", "kerning", "metric_rounding",
  "wrap", "align", "foreground", "background", "palette", "renderer"]);
export default async function init() {
  globalThis.__inits = (globalThis.__inits ?? 0) + 1;
}
export class Font {
  constructor(bytes) {
    if (!(bytes instanceof Uint8Array) || !bytes.length) throw new Error("bad font bytes");
    globalThis.__constructions = (globalThis.__constructions ?? 0) + 1;
    this.bytes = bytes;
  }
  metadata() { return { axes: [] }; }
  render(spec) {
    for (const key of Object.keys(spec)) {
      if (!KNOWN.has(key)) throw "invalid render spec: unknown field " + key;
    }
    // Baseline-only stub build: a candidate request fails visibly, exactly
    // like the production WASM artifact without the preview feature.
    if (spec.renderer === "candidate") throw "candidate rendering requires the candidate Cargo feature";
    if (spec.renderer !== undefined && spec.renderer !== "baseline" && spec.renderer !== "reference") throw "unknown renderer role";
    (globalThis.__renders ??= []).push(JSON.parse(JSON.stringify(spec)));
    const width = spec.width, height = spec.height;
    const pixels = new Uint8Array(width * height * 4);
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;
      pixels[i] = (x + Math.round(spec.size_px)) % 256;
      pixels[i + 1] = (y + Math.round(spec.axes?.wght ?? 0)) % 256;
      pixels[i + 2] = spec.renderer === "reference" ? 138 : 128; pixels[i + 3] = 255;
    }
    return {
      width: () => width,
      height: () => height,
      pixels: () => pixels.slice(),
      layout: () => ({
        lines: spec.text.split("\\n").map(() => ({ height_px: 20 })),
        missing_codepoints: [],
      }),
      free: () => { globalThis.__frees = (globalThis.__frees ?? 0) + 1; },
    };
  }
  free() { globalThis.__freed = (globalThis.__freed ?? 0) + 1; }
}
`;

const ALPHA_TEXT = "Alpha sample\nSecond line";
const NUMBERS_TEXT = "0123456789 .,;:!?+-/()";

function variableMetadata() {
  const metadata = fontMetadata();
  metadata.axes = [
    { tag: "wght", name: "Weight", min: 100, default: 400, max: 900, hidden: false },
    { tag: "wdth", name: "Width", min: 62.5, default: 100, max: 100, hidden: false },
  ];
  return metadata;
}

async function interactiveFixture(t, { withWasm = true } = {}) {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), "font-interactive-test-"));
  t.after(() => fs.rm(temp, { recursive: true, force: true }));
  const root = path.join(temp, "specimens");
  const output = path.join(temp, "web");
  const image = png();
  const imageHash = hash(image);
  const fontA = Buffer.from("fake-font-alpha");
  const fontB = Buffer.from("fake-font-beta");
  const item = (id, profile) => ({
    id, profile, label: "Reading sample", text: ALPHA_TEXT,
    outcome: "rendered", image: { path: `assets/${imageHash}.png`, sha256: imageHash },
  });
  const family = (id, name, source, metadata, axes, text) => ({
    id, name, source_sha256: source, metadata,
    sizes: [{
      size_px: 16, axes, thumbnail: { width_px: 2, height_px: 2 },
      items: [
        { ...item(`${id}-mono`, "mono_1bit"), text },
        { ...item(`${id}-gray`, "gray_3bit"), text },
      ],
    }],
  });
  const manifest = {
    schema_version: "web-specimens-v1",
    variant: { id: "reference-test", kind: "reference", version: null, generation_sha256: "a".repeat(64), composition_sha256: "b".repeat(64) },
    profiles: [{ id: "mono_1bit", output_bits: 1 }, { id: "gray_3bit", output_bits: 3 }],
    families: [
      family("alpha", "Alpha", hash(fontA), variableMetadata(), { wght: 400, wdth: 100 }, ALPHA_TEXT),
      family("beta", "Beta", hash(fontB), { ...fontMetadata(), axes: [] }, {}, "Beta sample"),
      family("gamma", "Gamma", "d".repeat(64), variableMetadata(), { wght: 400, wdth: 100 }, "Gamma sample"),
    ],
  };
  const packageDir = path.join(root, "reference-test");
  await fs.mkdir(path.join(packageDir, "assets"), { recursive: true });
  await fs.writeFile(path.join(packageDir, "assets", `${imageHash}.png`), image);
  await fs.writeFile(path.join(root, "active.json"), JSON.stringify({
    schema_version: "web-active-v1", variant_id: "reference-test", manifest: "reference-test/manifest.json",
  }));
  await fs.writeFile(path.join(packageDir, "manifest.json"), JSON.stringify(manifest));
  await fs.mkdir(path.join(temp, "fonts"), { recursive: true });
  await fs.writeFile(path.join(temp, "fonts", "A.ttf"), fontA);
  await fs.writeFile(path.join(temp, "fonts", "B.ttf"), fontB);
  const configPath = path.join(temp, "specimens.json");
  await fs.writeFile(configPath, JSON.stringify({
    profiles: [
      { id: "mono_1bit", output_bits: 1, mono_threshold: 200, gray_gamma: 1.0 },
      { id: "gray_3bit", output_bits: 3, mono_threshold: 128, gray_gamma: 2.2 },
    ],
    cards: [
      { id: "reading", title: "Reading sample", content: ALPHA_TEXT },
      { id: "numbers", title: "Numbers and symbols", content: NUMBERS_TEXT },
    ],
    families: [
      { id: "alpha", font: "fonts/A.ttf" },
      { id: "beta", font: "fonts/B.ttf" },
      { id: "gamma", font: "fonts/missing.ttf" },
    ],
  }));
  await build(root, output, { interactiveConfig: configPath, repoRoot: temp });
  if (withWasm) {
    await fs.mkdir(path.join(output, "assets", "wasm"), { recursive: true });
    await fs.writeFile(path.join(output, "assets", "wasm", "font_wasm.js"), STUB_WASM);
  }
  return { root, output };
}

async function launch(t, output) {
  const url = await serve(t, output);
  const browser = await chromium.launch({ executablePath: browserPath, headless: true });
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1100, height: 900 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(url, { waitUntil: "networkidle" });
  return { page, errors };
}

const renders = (page) => page.evaluate(() => globalThis.__renders ?? []);
const canvasBox = (page, family) => page.evaluate((id) => {
  const canvas = document.querySelector(`#interactive-${id} canvas`);
  return { width: canvas.width, height: canvas.height, style: [canvas.style.width, canvas.style.height] };
}, family);

test("one font tester renders the selected family with published ranges", { skip: !browserAvailable }, async (t) => {
  const f = await interactiveFixture(t);
  const { page, errors } = await launch(t, f.output);
  assert.deepEqual(await page.locator("#font-select option").allTextContents(), ["Alpha", "Beta", "Gamma"]);
  assert.equal(await page.locator("#font-select").inputValue(), "alpha");
  assert.equal(await page.locator(".interactive-specimen:visible").count(), 1);
  assert.equal(await page.locator("#interactive-alpha").isVisible(), true);
  await page.waitForFunction(() => document.querySelector("#interactive-alpha canvas")?.dataset.rendered === "true");

  const weight = page.locator("#interactive-alpha-wght");
  assert.equal(await weight.getAttribute("min"), "100");
  assert.equal(await weight.getAttribute("max"), "900");
  assert.equal(await weight.inputValue(), "400");
  const widthAxis = page.locator("#interactive-alpha-wdth");
  assert.equal(await widthAxis.getAttribute("min"), "62.5");
  assert.equal(await widthAxis.getAttribute("step"), "0.1");
  assert.equal(await page.locator("#interactive-alpha [data-size]").inputValue(), "16");
  assert.equal(await page.locator("#interactive-alpha [data-text]").inputValue(), ALPHA_TEXT);
  assert.equal(await page.locator("#interactive-alpha [data-preset]").inputValue(), "reading");

  const all = await renders(page);
  assert.equal(all.length, 1);
  const [first] = all;
  const box = await canvasBox(page, "alpha");
  assert.equal(first.text, ALPHA_TEXT);
  assert.equal(first.size_px, 16);
  assert.deepEqual(first.axes, { wght: 400, wdth: 100 });
  assert.equal(first.hinting, "auto");
  assert.equal(first.output_bits, 1);
  assert.equal(first.mono_threshold, 200);
  assert.equal(first.gray_gamma, 2.2);
  assert.equal(first.wrap, "word");
  assert.equal(first.width, box.width);
  assert.ok(first.height >= 1 && first.height <= 4096);
  assert.equal(box.height, 2 * 20);
  const counts = await page.evaluate(() => ({ inits: globalThis.__inits ?? 0, renders: (globalThis.__renders ?? []).length, frees: globalThis.__frees ?? 0, constructions: globalThis.__constructions ?? 0 }));
  assert.equal(counts.inits, 1);
  assert.equal(counts.frees, counts.renders);
  // Boot and the initial resize observation share one in-flight font load.
  assert.equal(counts.constructions, 1);
  assert.deepEqual(errors, []);
});

test("switching fonts swaps controls, preserves edits, and idles inactive fonts", { skip: !browserAvailable }, async (t) => {
  const f = await interactiveFixture(t);
  const { page, errors } = await launch(t, f.output);
  await page.waitForFunction(() => document.querySelector("#interactive-alpha canvas")?.dataset.rendered === "true");

  await page.locator("#interactive-alpha [data-text]").fill("Alpha edited");
  await page.waitForFunction(() => (globalThis.__renders ?? []).some((spec) => spec.text === "Alpha edited"));
  await page.locator("#interactive-alpha [data-text]").evaluate((el) => el.blur());
  await page.waitForTimeout(500);
  const alphaCount = (await renders(page)).length;

  await page.locator("#font-select").selectOption("beta");
  await page.waitForFunction(() => document.querySelector("#interactive-beta canvas")?.dataset.rendered === "true");
  assert.equal(await page.locator("#interactive-alpha").isVisible(), false);
  assert.equal(await page.locator("#interactive-beta [data-axis]").count(), 0);
  assert.equal(await page.locator("#interactive-beta [data-size]").inputValue(), "16");
  assert.equal(await page.locator("#interactive-beta [data-text]").inputValue(), "Beta sample");
  assert.equal(await page.locator("#interactive-beta [data-preset]").inputValue(), "custom");
  // Only beta rendered since the switch; alpha stayed idle.
  const betaRenders = (await renders(page)).filter((spec) => spec.text === "Beta sample").length;
  assert.ok(betaRenders >= 1);
  assert.equal((await renders(page)).length, alphaCount + betaRenders);

  await page.locator("#interactive-beta [data-size]").fill("20");
  await page.waitForFunction(() => (globalThis.__renders ?? []).some((spec) => spec.text === "Beta sample" && spec.size_px === 20));
  const freed = await page.evaluate(() => globalThis.__freed ?? 0);
  assert.ok(freed >= 1);

  await page.locator("#font-select").selectOption("alpha");
  await page.waitForFunction(() => (globalThis.__renders ?? []).some((spec) => spec.text === "Alpha edited" && spec.size_px === 16));
  assert.equal(await page.locator("#interactive-alpha [data-text]").inputValue(), "Alpha edited");
  assert.equal(await page.locator("#interactive-alpha [data-preset]").inputValue(), "custom");
  // Every displaced font was released exactly once; only the active one lives.
  const balance = await page.evaluate(() => (globalThis.__constructions ?? 0) - (globalThis.__freed ?? 0));
  assert.equal(balance, 1);
  assert.deepEqual(errors, []);
});

test("zoom magnifies symbols while the canvas fits the laid-out content", { skip: !browserAvailable }, async (t) => {
  const f = await interactiveFixture(t);
  const { page, errors } = await launch(t, f.output);
  await page.waitForFunction(() => document.querySelector("#interactive-alpha canvas")?.dataset.rendered === "true");
  const before = await canvasBox(page, "alpha");
  const specBefore = (await renders(page)).at(-1);
  assert.equal(specBefore.size_px, 16);

  await page.locator("#zoom").fill("1");
  await page.waitForFunction((width) => (globalThis.__renders ?? []).some((spec) => spec.width < width), specBefore.width);
  const specAfter = (await renders(page)).at(-1);
  assert.equal(specAfter.size_px, 16);
  assert.ok(specAfter.width < specBefore.width);
  assert.equal(specAfter.height, specBefore.height);
  const zoomed = await canvasBox(page, "alpha");
  assert.equal(zoomed.width, before.width);
  assert.equal(zoomed.height, before.height * 2);
  // Integer magnification repeats each logical texel: the top-left 2x2
  // canvas block is uniform while the neighboring logical texel differs.
  const block = await page.evaluate(() => [...document.querySelector("#interactive-alpha canvas").getContext("2d").getImageData(0, 0, 3, 1).data]);
  assert.deepEqual(block.slice(0, 4), block.slice(4, 8));
  assert.notDeepEqual(block.slice(0, 4), block.slice(8, 12));

  await page.setViewportSize({ width: 360, height: 800 });
  await page.waitForTimeout(500);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  assert.deepEqual(errors, []);
});

test("the display canvas grows and shrinks with the laid-out lines", { skip: !browserAvailable }, async (t) => {
  const f = await interactiveFixture(t);
  const { page, errors } = await launch(t, f.output);
  await page.waitForFunction(() => document.querySelector("#interactive-alpha canvas")?.dataset.rendered === "true");
  assert.equal((await canvasBox(page, "alpha")).height, 2 * 20);

  const tall = Array.from({ length: 30 }, (_, i) => `Row ${i}`).join("\n");
  await page.locator("#interactive-alpha [data-text]").fill(tall);
  await page.waitForFunction(() => document.querySelector("#interactive-alpha canvas")?.height === 30 * 20);
  assert.equal((await canvasBox(page, "alpha")).height, 30 * 20);

  await page.locator("#interactive-alpha [data-text]").fill("Short");
  await page.waitForFunction(() => document.querySelector("#interactive-alpha canvas")?.height === 20);
  assert.equal((await canvasBox(page, "alpha")).height, 20);
  assert.deepEqual(errors, []);
});

test("a short request height gets one taller correction pass", { skip: !browserAvailable }, async (t) => {
  const f = await interactiveFixture(t);
  const { page, errors } = await launch(t, f.output);
  await page.waitForFunction(() => document.querySelector("#interactive-alpha canvas")?.dataset.rendered === "true");
  // At 5 px the first-pass estimate (2 lines × 10 px) undershoots the stub
  // layout (2 lines × 20 px), so the same text renders twice, then paints.
  await page.locator("#interactive-alpha [data-size]").fill("5");
  await page.waitForFunction(() => (globalThis.__renders ?? []).filter((spec) => spec.size_px === 5).length === 2);
  const heights = (await renders(page)).filter((spec) => spec.size_px === 5).map((spec) => spec.height);
  assert.deepEqual(heights, [2 * Math.ceil(5 * 2), 2 * 20]);
  assert.deepEqual(errors, []);
});

test("a one-pixel resize at high zoom repaints at the same content height", { skip: !browserAvailable }, async (t) => {
  const f = await interactiveFixture(t);
  const { page, errors } = await launch(t, f.output);
  await page.waitForFunction(() => document.querySelector("#interactive-alpha canvas")?.dataset.rendered === "true");
  await page.locator("#zoom").fill("3");
  await page.waitForTimeout(500);
  const before = await canvasBox(page, "alpha");
  await page.setViewportSize({ width: 1099, height: 900 });
  await page.waitForFunction((width) => {
    const canvas = document.querySelector("#interactive-alpha canvas");
    return canvas.width !== width && canvas.width > 0;
  }, before.width);
  await page.waitForTimeout(500);
  const after = await canvasBox(page, "alpha");
  assert.equal(after.height, before.height);
  assert.ok(after.width < before.width);
  const sum = await page.evaluate(() => {
    const canvas = document.querySelector("#interactive-alpha canvas");
    const data = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
    let total = 0;
    for (let i = 0; i < data.length; i++) total = (total + data[i]) % 4294967296;
    return total;
  });
  assert.ok(sum > 0);
  assert.deepEqual(errors, []);
});

test("presets, custom edits, and reset work on the selected family", { skip: !browserAvailable }, async (t) => {
  const f = await interactiveFixture(t);
  const { page, errors } = await launch(t, f.output);
  await page.waitForFunction(() => document.querySelector("#interactive-alpha canvas")?.dataset.rendered === "true");

  await page.locator("#interactive-alpha [data-preset]").selectOption("numbers");
  await page.waitForFunction((expected) => (globalThis.__renders ?? []).some((spec) => spec.text === expected), NUMBERS_TEXT);
  assert.equal(await page.locator("#interactive-alpha [data-text]").inputValue(), NUMBERS_TEXT);

  await page.locator("#interactive-alpha [data-text]").fill("Line one\nLine two");
  await page.waitForFunction(() => (globalThis.__renders ?? []).some((spec) => spec.text === "Line one\nLine two"));
  await page.waitForFunction(() => document.querySelector("#interactive-alpha [data-preset]").value === "custom");
  assert.equal(await page.locator("#interactive-alpha [data-preset]").inputValue(), "custom");

  await page.locator(".profile-options label").filter({ hasText: "3-bit" }).click();
  await page.waitForFunction(() => (globalThis.__renders ?? []).some((spec) => spec.output_bits === 3));

  await page.locator("#interactive-alpha [data-reset]").click();
  await page.waitForFunction((expected) => (globalThis.__renders ?? []).some((spec) => spec.text === expected && spec.size_px === 16), ALPHA_TEXT);
  assert.equal(await page.locator("#interactive-alpha [data-text]").inputValue(), ALPHA_TEXT);
  assert.equal(await page.locator("#interactive-alpha [data-preset]").inputValue(), "reading");
  assert.deepEqual(errors, []);
});

test("the version role forwards with unchanged controls and the canvas reacts", { skip: !browserAvailable }, async (t) => {
  const f = await interactiveFixture(t);
  const { page, errors } = await launch(t, f.output);
  await page.waitForFunction(() => document.querySelector("#interactive-alpha canvas")?.dataset.rendered === "true");
  // The fixture publication has no comparison pair, so the page ships no
  // Version switch; inject the same switch shape to drive the live role
  // path (the published page renders this switch from versionRoles).
  await page.evaluate(() => {
    const fieldset = document.createElement("fieldset");
    fieldset.id = "renderer-role";
    for (const role of ["baseline", "reference", "candidate"]) {
      const input = document.createElement("input");
      input.type = "radio"; input.name = "renderer-role"; input.value = role;
      if (role === "baseline") input.checked = true;
      fieldset.append(input);
    }
    document.body.prepend(fieldset);
  });
  const sum = () => page.evaluate(() => {
    const canvas = document.querySelector("#interactive-alpha canvas");
    const data = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
    let total = 0;
    for (let i = 0; i < data.length; i++) total = (total + data[i]) % 4294967296;
    return total;
  });
  const baselineSpec = (await renders(page)).at(-1);
  assert.equal(baselineSpec.renderer, "baseline");
  const baselineSum = await sum();

  await page.evaluate(() => { document.querySelector('input[name="renderer-role"][value="reference"]').checked = true; });
  await page.locator("#interactive-alpha [data-size]").fill("16");
  await page.waitForFunction(() => (globalThis.__renders ?? []).some((spec) => spec.renderer === "reference"));
  const referenceSpec = (await renders(page)).at(-1);
  assert.equal(referenceSpec.renderer, "reference");
  assert.deepEqual(
    [referenceSpec.text, referenceSpec.size_px, referenceSpec.axes, referenceSpec.output_bits],
    [baselineSpec.text, baselineSpec.size_px, baselineSpec.axes, baselineSpec.output_bits],
  );
  assert.notEqual(await sum(), baselineSum);

  await page.evaluate(() => { document.querySelector('input[name="renderer-role"][value="candidate"]').checked = true; });
  const count = (await renders(page)).length;
  await page.locator("#interactive-alpha [data-size]").fill("16");
  await page.locator("#interactive-alpha [data-status]:visible").waitFor();
  await assert.match(await page.locator("#interactive-alpha [data-status]").textContent(), /unavailable/);
  assert.equal((await renders(page)).length, count);
  assert.deepEqual(errors, []);
});

test("the published page offers the latest role against the approved baseline", async (t) => {
  // Truecolor 4x2 comparison tile: every pixel must come from the mono
  // palette (plus red/blue for differences) with full alpha.
  const tile = (color) => {
    const data = Buffer.alloc(4 * 2 * 4);
    for (let i = 0; i < 4 * 2; i++) { data[i * 4] = 255; data[i * 4 + 1] = 255; data[i * 4 + 2] = 255; data[i * 4 + 3] = 255; }
    if (color) { data[0] = color[0]; data[1] = color[1]; data[2] = color[2]; }
    return PNG.sync.write({ width: 4, height: 2, data }, { colorType: 2, bitDepth: 8 });
  };
  const f = await fixture(t);
  const iterId = "iteration-01-pkg";
  await fs.cp(f.packageDir, path.join(f.root, iterId), { recursive: true });
  const manifest = JSON.parse(await fs.readFile(path.join(f.root, iterId, "manifest.json"), "utf8"));
  manifest.variant = {
    ...manifest.variant, id: iterId, kind: "iteration", version: "001.01", renderer: "baseline",
    generation_sha256: "e".repeat(64), composition_sha256: "f".repeat(64),
  };
  await fs.writeFile(path.join(f.root, iterId, "manifest.json"), JSON.stringify(manifest));
  await fs.writeFile(path.join(f.root, "published.json"), JSON.stringify({
    schema_version: "specimen-publication-v1",
    variants: { reference: f.pointer.variant_id, "iteration-01": iterId },
  }));
  const images = {
    previous: tile(null),
    current: tile([0, 0, 0]),
    difference: tile([224, 32, 32]),
  };
  const asset = (bytes) => ({ path: `assets/${hash(bytes)}.png`, sha256: hash(bytes) });
  const comparison = {
    schema_version: "web-glyph-comparison-v1",
    id: "01",
    previous: { package_id: f.pointer.variant_id, label: "Reference", generation_sha256: "a".repeat(64) },
    current: { package_id: iterId, label: "001.01", generation_sha256: "e".repeat(64) },
    profiles: [{ id: "mono_1bit", output_bits: 1 }],
    families: [{
      id: "fixture", name: "Fixture font",
      sizes: [{
        size_px: 16, axes: { wght: 400 },
        canvas: { width_px: 4, height_px: 2, origin_x: 0, baseline_y: 1, padding_px: 0 },
        glyphs: [{
          codepoint: 65, character: "A",
          profiles: [{
            id: "mono_1bit", advance_px: 8,
            previous: asset(images.previous), current: asset(images.current),
            difference: asset(images.difference), reason: null,
          }],
        }],
      }],
    }],
  };
  const comparisonBytes = Buffer.from(JSON.stringify(comparison));
  const comparisonDir = path.join(f.root, "comparisons", `01-${hash(comparisonBytes)}`);
  await fs.mkdir(path.join(comparisonDir, "assets"), { recursive: true });
  await fs.writeFile(path.join(comparisonDir, "manifest.json"), comparisonBytes);
  for (const bytes of Object.values(images)) {
    await fs.writeFile(path.join(comparisonDir, `assets/${hash(bytes)}.png`), bytes);
  }
  await fs.writeFile(path.join(f.root, "comparisons", "index.json"), JSON.stringify({
    schema_version: "web-comparisons-v1",
    comparisons: [{ id: "01", manifest: `01-${hash(comparisonBytes)}/manifest.json` }],
  }));
  const html = await build(f.root, f.output);
  assert.match(html, /id="renderer-role"/);
  assert.match(html, /value="baseline" checked/);
  assert.match(html, /Latest approved baseline 001\.01/);
  assert.match(html, /value="reference"/);
  assert.match(html, /<span>Reference<\/span>/);
});

test("unavailable fonts and missing WASM degrade to a concise message", { skip: !browserAvailable }, async (t) => {
  const f = await interactiveFixture(t);
  const { page } = await launch(t, f.output);
  await page.waitForFunction(() => document.querySelector("#interactive-alpha canvas")?.dataset.rendered === "true");
  await page.locator("#font-select").selectOption("gamma");
  const gamma = page.locator("#interactive-gamma");
  await gamma.locator("[data-status]:visible").waitFor();
  await assert.match(await gamma.locator("[data-status]").textContent(), /unavailable/);
  assert.equal(await gamma.locator("canvas").isHidden(), true);
  assert.equal(await gamma.locator("[data-size]").isDisabled(), true);
  assert.equal(await gamma.locator("[data-text]").isDisabled(), true);
  assert.equal(await gamma.locator("[data-preset]").isDisabled(), true);

  const nowasm = await interactiveFixture(t, { withWasm: false });
  const { page: plain } = await launch(t, nowasm.output);
  await plain.locator("#interactive-alpha [data-status]:visible").waitFor();
  await assert.match(await plain.locator("#interactive-alpha [data-status]").textContent(), /unavailable/);
  assert.equal(await plain.locator("#interactive-alpha [data-size]").isDisabled(), true);
  assert.equal(await plain.locator("#interactive-alpha [data-text]").isDisabled(), true);
  assert.equal(await plain.locator("#interactive-alpha [data-preset]").isDisabled(), true);
});
