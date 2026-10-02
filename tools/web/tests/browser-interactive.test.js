import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright-core";
import { build, hash, png, serve } from "./helpers.js";
import { fontMetadata } from "./helpers.js";

const browserPath = process.env.WEB_TEST_BROWSER ?? "/opt/google/chrome/chrome";
const browserAvailable = await fs.access(browserPath).then(() => true, () => false);

const STUB_WASM = `
const KNOWN = new Set(["text", "width", "height", "size_px", "axes", "hinting", "output_bits",
  "mono_threshold", "gray_gamma", "missing_glyphs", "kerning", "metric_rounding",
  "wrap", "align", "foreground", "background", "palette"]);
export default async function init() {
  globalThis.__inits = (globalThis.__inits ?? 0) + 1;
}
export class Font {
  constructor(bytes) {
    if (!(bytes instanceof Uint8Array) || !bytes.length) throw new Error("bad font bytes");
    this.bytes = bytes;
  }
  metadata() { return { axes: [] }; }
  render(spec) {
    for (const key of Object.keys(spec)) {
      if (!KNOWN.has(key)) throw "invalid render spec: unknown field " + key;
    }
    (globalThis.__renders ??= []).push(JSON.parse(JSON.stringify(spec)));
    const width = spec.width, height = spec.height;
    const pixels = new Uint8Array(width * height * 4);
    const red = Math.round(spec.size_px) % 256;
    const green = Math.round(spec.axes?.wght ?? 0) % 256;
    for (let i = 0; i < width * height; i++) {
      pixels[i * 4] = red; pixels[i * 4 + 1] = green; pixels[i * 4 + 2] = 128; pixels[i * 4 + 3] = 255;
    }
    return {
      width: () => width,
      height: () => height,
      pixels: () => pixels.slice(),
      layout: () => ({ lines: [], missing_codepoints: [] }),
      free: () => { globalThis.__frees = (globalThis.__frees ?? 0) + 1; },
    };
  }
  free() { globalThis.__freed = (globalThis.__freed ?? 0) + 1; }
}
`;

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
    id, profile, label: "Reading sample", text: "Alpha sample",
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
      family("alpha", "Alpha", hash(fontA), variableMetadata(), { wght: 400, wdth: 100 }, "Alpha sample"),
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
const canvasPixel = (page, family) => page.evaluate((id) => {
  const canvas = document.querySelector(`#interactive-${id} canvas`);
  return [...canvas.getContext("2d").getImageData(0, 0, 1, 1).data];
}, family);

test("interactive controls render through WASM with published ranges and defaults", { skip: !browserAvailable }, async (t) => {
  const f = await interactiveFixture(t);
  const { page, errors } = await launch(t, f.output);
  await page.waitForFunction(() => document.querySelector("#interactive-alpha canvas")?.dataset.rendered === "true");
  await page.waitForFunction(() => document.querySelector("#interactive-beta canvas")?.dataset.rendered === "true");

  const weight = page.locator("#interactive-alpha-wght");
  assert.equal(await weight.getAttribute("min"), "100");
  assert.equal(await weight.getAttribute("max"), "900");
  assert.equal(await weight.inputValue(), "400");
  const widthAxis = page.locator("#interactive-alpha-wdth");
  assert.equal(await widthAxis.getAttribute("min"), "62.5");
  assert.equal(await widthAxis.getAttribute("step"), "0.1");
  assert.equal(await page.locator("#interactive-alpha [data-size]").inputValue(), "16");
  assert.equal(await page.locator("#interactive-beta [data-axis]").count(), 0);

  const all = await renders(page);
  const first = all.find((spec) => spec.text === "Alpha sample");
  assert.deepEqual(first, {
    text: "Alpha sample", width: 720, height: 48, size_px: 16, axes: { wght: 400, wdth: 100 },
    hinting: "auto", output_bits: 1, mono_threshold: 200, gray_gamma: 2.2,
    missing_glyphs: "error", kerning: true, metric_rounding: "subpixel",
    wrap: "word", align: "left", foreground: [36, 40, 43, 255], background: [255, 255, 255, 255],
  });
  assert.deepEqual(await canvasPixel(page, "alpha"), [16, 144, 128, 255]);
  const counts = await page.evaluate(() => ({ inits: globalThis.__inits ?? 0, renders: (globalThis.__renders ?? []).length, frees: globalThis.__frees ?? 0 }));
  assert.equal(counts.inits, 1);
  assert.equal(counts.frees, counts.renders);
  assert.deepEqual(errors, []);
});

test("families render independently and follow profile, zoom, text, and reset", { skip: !browserAvailable }, async (t) => {
  const f = await interactiveFixture(t);
  const { page, errors } = await launch(t, f.output);
  await page.waitForFunction(() => document.querySelector("#interactive-alpha canvas")?.dataset.rendered === "true");
  await page.waitForFunction(() => document.querySelector("#interactive-beta canvas")?.dataset.rendered === "true");
  const betaBefore = await canvasPixel(page, "beta");
  const betaRenders = () => renders(page).then((all) => all.filter((spec) => spec.text === "Beta sample").length);

  await page.locator("#interactive-alpha-wght").fill("700");
  await page.waitForFunction(() => (globalThis.__renders ?? []).some((spec) => spec.text === "Alpha sample" && spec.axes.wght === 700));
  assert.deepEqual(await canvasPixel(page, "alpha"), [16, 188, 128, 255]);
  assert.deepEqual(await canvasPixel(page, "beta"), betaBefore);
  assert.equal(await betaRenders(), 1);

  await page.locator("#interactive-alpha [data-size]").fill("20");
  await page.waitForFunction(() => (globalThis.__renders ?? []).some((spec) => spec.text === "Alpha sample" && spec.size_px === 20));
  assert.deepEqual(await canvasPixel(page, "alpha"), [20, 188, 128, 255]);

  await page.locator('#interactive-alpha [data-text]').fill("Hi there");
  await page.waitForFunction(() => (globalThis.__renders ?? []).some((spec) => spec.text === "Hi there"));
  // Blur fires the text input's change render; settle it before zoom takes focus.
  await page.locator('#interactive-alpha [data-text]').evaluate((el) => el.blur());
  await page.waitForTimeout(500);
  const renderCount = (await renders(page)).length;
  await page.locator("#zoom").fill("3");
  await page.waitForFunction(() => document.querySelector("#interactive-alpha canvas").style.width === "2880px");
  await page.waitForTimeout(500);
  assert.equal((await renders(page)).length, renderCount);

  await page.locator(".profile-options label").filter({ hasText: "3-bit" }).click();
  await page.waitForFunction(() => (globalThis.__renders ?? []).some((spec) => spec.output_bits === 3));

  await page.locator('#interactive-alpha [data-reset]').click();
  await page.waitForFunction(() => (globalThis.__renders ?? []).some((spec) => spec.text === "Alpha sample" && spec.size_px === 16 && spec.axes.wght === 400));
  assert.equal(await page.locator("#interactive-alpha-wght").inputValue(), "400");
  assert.equal(await page.locator("#interactive-alpha [data-size]").inputValue(), "16");
  assert.deepEqual(errors, []);
});

test("unavailable fonts and missing WASM degrade to a concise message", { skip: !browserAvailable }, async (t) => {
  const f = await interactiveFixture(t);
  const { page } = await launch(t, f.output);
  const gamma = page.locator("#interactive-gamma");
  await gamma.locator("[data-status]:visible").waitFor();
  await assert.match(await gamma.locator("[data-status]").textContent(), /unavailable/);
  assert.equal(await gamma.locator("canvas").isHidden(), true);
  assert.equal(await gamma.locator("[data-size]").isDisabled(), true);

  const nowasm = await interactiveFixture(t, { withWasm: false });
  const { page: plain } = await launch(t, nowasm.output);
  await plain.locator("#interactive-alpha [data-status]:visible").waitFor();
  await assert.match(await plain.locator("#interactive-alpha [data-status]").textContent(), /unavailable/);
  assert.equal(await plain.locator("#interactive-alpha [data-size]").isDisabled(), true);
});
