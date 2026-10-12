import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright-core";
import { PNG } from "pngjs";
import { build, serve, webRoot } from "./helpers.js";

const browserPath = process.env.WEB_TEST_BROWSER ?? "/opt/google/chrome/chrome";
const repoRoot = path.resolve(webRoot, "../..");
const wasmDir = process.env.FONT_WASM_PREVIEW_DIR ?? path.join(repoRoot, "tools/wasm/pkg-web-preview");
const wasmJs = path.join(wasmDir, "font_wasm.js");
const wasmBin = path.join(wasmDir, "font_wasm_bg.wasm");
const published = path.join(repoRoot, "out/specimens/published.json");
const ready = await fs.access(browserPath).then(() => true, () => false)
  && await fs.access(wasmJs).then(() => true, () => false)
  && await fs.access(wasmBin).then(() => true, () => false)
  && await fs.access(published).then(() => true, () => false);

const READING_TEXT = "Pack my box with five dozen liquor jugs.\nminimum AVATAR To Wa";
const NUMBERS_TEXT = "08:38 21.5°C 48%\n0123456789 .,;:!?+-/()";
const configuredCards = JSON.parse(await fs.readFile(path.join(repoRoot, "tools/generator/specimens.json"), "utf8")).cards;

async function snapshot(page, family) {
  return page.evaluate((id) => {
    const canvas = document.querySelector(`#interactive-${id} canvas`);
    const context = canvas.getContext("2d");
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let sum = 0;
    let positionSum = 0;
    for (let i = 0; i < data.length; i++) {
      sum = (sum + data[i]) % 4294967296;
      positionSum = (positionSum + (i + 1) * data[i]) % 4294967296;
    }
    return { width: canvas.width, height: canvas.height, style: [canvas.style.width, canvas.style.height], sum, positionSum };
  }, family);
}

test("real WASM negative spacing preserves word gaps across roles and spacing models", { skip: !ready }, async (t) => {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), "font-wasm-word-gap-test-"));
  t.after(() => fs.rm(temp, { recursive: true, force: true }));
  const output = path.join(temp, "web");
  await build(path.join(repoRoot, "out/specimens"), output);
  await fs.mkdir(path.join(output, "assets", "wasm"), { recursive: true });
  await fs.copyFile(wasmJs, path.join(output, "assets", "wasm", "font_wasm.js"));
  await fs.copyFile(wasmBin, path.join(output, "assets", "wasm", "font_wasm_bg.wasm"));
  const url = await serve(t, output);
  const browser = await chromium.launch({ executablePath: browserPath, headless: true });
  t.after(() => browser.close());
  const page = await browser.newPage();
  await page.goto(url, { waitUntil: "networkidle" });
  await page.waitForFunction(() => !document.querySelector("#interactive-roboto [data-size]").disabled);
  const failures = await page.evaluate(async () => {
    // Reuse the UI's versioned renderer URL (same ?v= query as the
    // interactive script) so the probe shares the one initialized module
    // instead of loading a second unversioned copy.
    const script = document.querySelector('script[src*="assets/interactive.js"]')?.getAttribute("src") ?? "";
    const query = script.includes("?") ? script.slice(script.indexOf("?")) : "";
    const wasm = await import(`./assets/wasm/font_wasm.js${query}`);
    const failures = [];
    for (const family of ["roboto", "literata", "source-sans-3"]) {
      const section = document.querySelector(`[data-interactive-family="${family}"]`);
      const bytes = new Uint8Array(await (await fetch(new URL(section.dataset.fontUrl, document.baseURI))).arrayBuffer());
      const font = new wasm.Font(bytes);
      try {
        const axes = JSON.parse(section.dataset.defaultAxes);
        if (family === "roboto") { axes.wght = 641; axes.wdth = 100; }
        for (const renderer of ["baseline", "reference", "candidate"]) {
          for (const output_bits of [1, 3]) {
            const models = output_bits === 1 ? ["auto", "source", "fitted", "projected"] : ["auto"];
            for (const spacing_model of models) {
              // Single-letter words have no internal tracking opportunities.
              // Their pixels must keep neutral origins even with repeated,
              // leading or trailing spaces; the final pen may still track.
              for (const text of ["l l", " l  l "]) {
                const spec = { text, width: 128, height: 32, size_px: 14, axes, renderer, output_bits,
                  spacing_model, hinting: "auto", mono_threshold: 128, gray_gamma: 1,
                  missing_glyphs: "error", kerning: true, metric_rounding: "subpixel", wrap: "clip",
                  align: "left", foreground: [0, 0, 0, 255], background: [255, 255, 255, 255] };
                const neutral = font.render({ ...spec, letter_spacing_px: 0 });
                let base;
                try { base = neutral.pixels(); } finally { neutral.free(); }
                for (const letter_spacing_px of output_bits === 1 ? [-1, -2] : [-0.25, -1, -2]) {
                  const tightened = font.render({ ...spec, letter_spacing_px });
                  try {
                    const pixels = tightened.pixels();
                    let differences = 0;
                    for (let i = 0; i < pixels.length; i++) if (pixels[i] !== base[i]) differences++;
                    if (differences) failures.push({ family, renderer, output_bits, spacing_model, text, letter_spacing_px, differences });
                  } finally { tightened.free(); }
                }
              }
            }
          }
        }
      } finally { font.free(); }
    }
    return failures;
  });
  assert.deepEqual(failures, [], "word-gap preservation compares current glyphs with their own neutral layout");
});

test("real WASM zoom preserves glyph pixels and repeats every visible canvas texel", { skip: !ready }, async (t) => {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), "font-wasm-zoom-test-"));
  t.after(() => fs.rm(temp, { recursive: true, force: true }));
  const output = path.join(temp, "web");
  await build(path.join(repoRoot, "out/specimens"), output);
  await fs.mkdir(path.join(output, "assets", "wasm"), { recursive: true });
  await fs.copyFile(wasmJs, path.join(output, "assets", "wasm", "font_wasm.js"));
  await fs.copyFile(wasmBin, path.join(output, "assets", "wasm", "font_wasm_bg.wasm"));
  const url = await serve(t, output);
  const browser = await chromium.launch({ executablePath: browserPath, headless: true });
  t.after(() => browser.close());
  // Fractional DPR may resample the canvas again at the compositor. Its
  // backing pixels still obey the exact integer-zoom contract. Compare the
  // current rendering with itself at another zoom, without freezing a glyph.
  for (const deviceScaleFactor of [1, 1.125]) {
    const context = await browser.newContext({ viewport: { width: 1101, height: 900 }, deviceScaleFactor });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/assets/wasm/font_wasm.js*", async (route) => {
      const source = await fs.readFile(wasmJs, "utf8");
      await route.fulfill({ contentType: "text/javascript", body: `${source}\n
const observedZoomRender = Font.prototype.render;
Font.prototype.render = function(spec) {
  const result = observedZoomRender.call(this, spec);
  globalThis.__zoomNative = { spec: structuredClone(spec), width: result.width(),
    height: result.height(), pixels: Array.from(result.pixels()), layout: result.layout() };
  return result;
};` });
    });
    await page.goto(url, { waitUntil: "networkidle" });
    await page.waitForFunction(() => !document.querySelector("#interactive-roboto [data-size]").disabled);
    await page.locator("#interactive-roboto [data-size]").fill("14");
    await page.locator("#interactive-roboto-wght").fill("523");
    await page.locator("#interactive-roboto [data-text]").fill("u");
    for (const [profile, bits] of [["mono_1bit", 1], ["gray_3bit", 3]]) {
      await page.locator(`.profile-options input[value="${profile}"]`).check();
      let nativeGlyph;
      for (const zoom of [1, 2, 3, 4]) {
        await page.locator("#zoom").fill(String(zoom - 1));
        await page.waitForFunction(({ zoom, bits }) => {
          const native = globalThis.__zoomNative;
          const canvas = document.querySelector("#interactive-roboto canvas");
          return native?.spec.text === "u" && native.spec.axes.wght === 523
            && native.spec.output_bits === bits && native.spec.size_px === 14
            && native.width === Math.ceil(canvas.width / zoom)
            && canvas.height === native.layout.lines[0].height_px * zoom;
        }, { zoom, bits });
        const measured = await page.evaluate((zoom) => {
          const native = globalThis.__zoomNative;
          const canvas = document.querySelector("#interactive-roboto canvas");
          const pixels = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
          let mismatches = 0;
          for (let y = 0; y < canvas.height; y++) {
            for (let x = 0; x < canvas.width; x++) {
              const src = (Math.floor(y / zoom) * native.width + Math.floor(x / zoom)) * 4;
              const dst = (y * canvas.width + x) * 4;
              for (let channel = 0; channel < 4; channel++) {
                if (pixels[dst + channel] !== native.pixels[src + channel]) mismatches++;
              }
            }
          }
          const glyph = [];
          for (let y = 0; y < native.height; y++) {
            for (let x = 0; x < native.width; x++) {
              const i = (y * native.width + x) * 4;
              if (native.pixels[i] !== 255) glyph.push([x, y, ...native.pixels.slice(i, i + 4)]);
            }
          }
          return { mismatches, glyph, reportedWidth: native.width, requestedWidth: native.spec.width };
        }, zoom);
        assert.equal(measured.mismatches, 0, `${profile}, DPR ${deviceScaleFactor}, zoom ${zoom}`);
        assert.equal(measured.reportedWidth, measured.requestedWidth);
        assert.ok(measured.glyph.length);
        nativeGlyph ??= measured.glyph;
        assert.deepEqual(measured.glyph, nativeGlyph, "layout width must not alter scalar fitting");
      }
    }
    assert.deepEqual(errors, []);
    await context.close();
  }
});

test("pixel-accurate display preserves native glyphs and physical pixel blocks", { skip: !ready }, async (t) => {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), "font-wasm-screen-test-"));
  t.after(() => fs.rm(temp, { recursive: true, force: true }));
  const output = path.join(temp, "web");
  await build(path.join(repoRoot, "out/specimens"), output);
  await fs.mkdir(path.join(output, "assets", "wasm"), { recursive: true });
  await fs.copyFile(wasmJs, path.join(output, "assets", "wasm", "font_wasm.js"));
  await fs.copyFile(wasmBin, path.join(output, "assets", "wasm", "font_wasm_bg.wasm"));
  const url = await serve(t, output);
  const browser = await chromium.launch({ executablePath: browserPath, headless: true });
  t.after(() => browser.close());
  for (const ratio of [1, 1.125, 1.25, 1.5, 1.75, 2]) {
    const context = await browser.newContext({ viewport: { width: 1101, height: 1100 }, deviceScaleFactor: ratio });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/assets/wasm/font_wasm.js*", async (route) => {
      const source = await fs.readFile(wasmJs, "utf8");
      await route.fulfill({ contentType: "text/javascript", body: `${source}\n
const observedScreenRender = Font.prototype.render;
Font.prototype.render = function(spec) {
  const result = observedScreenRender.call(this, spec);
  globalThis.__screenNative = { spec: structuredClone(spec), width: result.width(),
    height: result.height(), pixels: Array.from(result.pixels()), layout: result.layout() };
  return result;
};` });
    });
    await page.goto(url, { waitUntil: "networkidle" });
    await page.waitForFunction(() => !document.querySelector("#interactive-roboto [data-size]").disabled);
    const mode = page.getByLabel("Pixel-accurate display", { exact: true });
    assert.equal(await mode.isChecked(), false);
    await page.locator("#interactive-roboto [data-size]").fill("14");
    await page.locator("#interactive-roboto-wght").fill("523");
    await page.locator("#interactive-roboto [data-text]").fill("u");
    await page.locator("#zoom").fill("0");
    await page.waitForFunction(() => globalThis.__screenNative?.spec.text === "u"
      && globalThis.__screenNative.spec.axes.wght === 523);
    const read = () => page.evaluate(() => {
      const canvas = document.querySelector("#interactive-roboto canvas");
      const rect = canvas.getBoundingClientRect();
      const native = globalThis.__screenNative;
      const glyph = [];
      for (let y = 0; y < native.height; y++) {
        for (let x = 0; x < native.width; x++) {
          const i = (y * native.width + x) * 4;
          if (native.pixels[i] !== 255) glyph.push([x, y, ...native.pixels.slice(i, i + 4)]);
        }
      }
      return { native, glyph, width: canvas.width, height: canvas.height,
        pixels: Array.from(canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data),
        rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height } };
    });
    const normal = await read();
    await mode.check();
    const verify = async (zoom, gray = false) => {
      const block = Math.max(1, Math.round(zoom * ratio));
      await page.waitForFunction(({ block, gray }) => {
        const native = globalThis.__screenNative;
        const canvas = document.querySelector("#interactive-roboto canvas");
        const viewport = document.querySelector("#interactive-roboto .interactive-viewport");
        const capacity = (viewport.clientWidth - 1) * window.devicePixelRatio - 1;
        return canvas.width <= capacity + 0.01 && canvas.width >= capacity - block - 0.01
          && native.spec.output_bits === (gray ? 3 : 1)
          && canvas.width === native.width * block
          && canvas.height === native.layout.lines[0].height_px * block;
      }, { block, gray }, { timeout: 10000 });
      await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      const state = await read();
      assert.equal(state.native.spec.size_px, 14);
      assert.equal(state.native.spec.axes.wght, 523);
      if (!gray) assert.deepEqual(state.glyph, normal.glyph, "screen compensation must not alter fitted glyph pixels");
      assert.ok(Math.abs(state.rect.width * ratio - state.width) < 0.03);
      assert.ok(Math.abs(state.rect.height * ratio - state.height) < 0.03);
      assert.ok(Math.abs(state.rect.x * ratio - Math.round(state.rect.x * ratio)) < 0.03, JSON.stringify({ ratio, zoom, rect: state.rect }));
      assert.ok(Math.abs(state.rect.y * ratio - Math.round(state.rect.y * ratio)) < 0.03, JSON.stringify({ ratio, zoom, rect: state.rect }));
      for (let y = 0; y < state.height; y++) {
        for (let x = 0; x < state.width; x++) {
          const src = (Math.floor(y / block) * state.native.width + Math.floor(x / block)) * 4;
          const dst = (y * state.width + x) * 4;
          for (let c = 0; c < 4; c++) assert.equal(state.pixels[dst + c], state.native.pixels[src + c]);
        }
      }
      // Use the full viewport so fractional CSS clip coordinates cannot
      // introduce a separate rounding shift in the screenshot crop itself.
      const screenshot = PNG.sync.read(await page.screenshot());
      const left = Math.round(state.rect.x * ratio);
      const top = Math.round(state.rect.y * ratio);
      assert.ok(left >= 0 && top >= 0 && left + state.width <= screenshot.width && top + state.height <= screenshot.height);
      let screenMismatches = 0;
      for (let y = 0; y < state.height; y++) {
        for (let x = 0; x < state.width; x++) {
          const src = (y * state.width + x) * 4;
          const dst = ((top + y) * screenshot.width + left + x) * 4;
          for (let c = 0; c < 4; c++) if (screenshot.data[dst + c] !== state.pixels[src + c]) screenMismatches++;
        }
      }
      if (screenMismatches && process.env.PIXEL_SCREEN_DIAGNOSTICS) {
        const dir = process.env.PIXEL_SCREEN_DIAGNOSTICS;
        const after = await read();
        await fs.writeFile(path.join(dir, `real-${ratio}-${zoom}.json`), JSON.stringify({ ratio, zoom, before: state.rect, after: after.rect, width: state.width, height: state.height, glyph: state.glyph, screenshotWidth: screenshot.width, screenshotHeight: screenshot.height }));
        await fs.writeFile(path.join(dir, `real-${ratio}-${zoom}-screen.png`), PNG.sync.write(screenshot));
        await fs.writeFile(path.join(dir, `real-${ratio}-${zoom}-canvas.png`), PNG.sync.write({ width: state.width, height: state.height, data: Buffer.from(state.pixels) }));
      }
      assert.equal(screenMismatches, 0, `physical screenshot parity at ratio ${ratio}, zoom ${zoom}`);
      assert.equal(await page.locator("#zoom-value").textContent(), `${zoom}×`);
    };
    for (const zoom of [1, 2, 3, 4]) {
      await page.locator("#zoom").fill(String(zoom - 1));
      await verify(zoom);
    }
    if (ratio === 1.125) {
      await page.locator("#zoom").fill("1");
      await page.evaluate(() => {
        document.documentElement.style.fontSize = "17px";
        window.scrollTo(0, 57);
      });
      await verify(2);
      // The extra font-details disclosure makes the narrow layout taller.
      // Fit the entire canvas in the capture; retain every physical-pixel
      // and viewport-bounds assertion below.
      await page.setViewportSize({ width: 501, height: 1800 });
      await verify(2);
      await page.locator('.profile-options input[value="gray_3bit"]').check();
      await verify(2, true);
      await page.locator('.profile-options input[value="mono_1bit"]').check();
      await page.evaluate(() => { document.documentElement.style.fontSize = ""; window.scrollTo(0, 0); });
      await page.setViewportSize({ width: 1101, height: 1100 });
    }
    await mode.uncheck();
    await page.locator("#zoom").fill("0");
    await page.waitForFunction((width) => {
      const canvas = document.querySelector("#interactive-roboto canvas");
      return canvas.width === width && canvas.height === globalThis.__screenNative.layout.lines[0].height_px;
    }, normal.width, { timeout: 10000 });
    const restored = await read();
    assert.deepEqual(restored.pixels, normal.pixels, "disabling compensation must restore the original display path");
    assert.deepEqual([restored.rect.width, restored.rect.height], [normal.rect.width, normal.rect.height],
      "disabling compensation must restore the original CSS extent");
    assert.deepEqual(errors, []);
    await context.close();
  }
});

test("real WASM renders respond to size, axes, text, profile, zoom, and reset", { skip: !ready }, async (t) => {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), "font-wasm-real-test-"));
  t.after(() => fs.rm(temp, { recursive: true, force: true }));
  const output = path.join(temp, "web");
  await build(path.join(repoRoot, "out/specimens"), output);
  await fs.mkdir(path.join(output, "assets", "wasm"), { recursive: true });
  await fs.copyFile(wasmJs, path.join(output, "assets", "wasm", "font_wasm.js"));
  await fs.copyFile(wasmBin, path.join(output, "assets", "wasm", "font_wasm_bg.wasm"));
  const url = await serve(t, output);
  const browser = await chromium.launch({ executablePath: browserPath, headless: true });
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1100, height: 900 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  // Observe requests while retaining the actual compiled WASM renderer.
  // A new candidate can start from the approved source and render identically;
  // role routing must not require a pixel difference between those models.
  await page.route("**/assets/wasm/font_wasm.js*", async (route) => {
    const source = await fs.readFile(wasmJs, "utf8");
    await route.fulfill({ contentType: "text/javascript", body: `${source}\n
const observedRender = Font.prototype.render;
Font.prototype.render = function(spec) {
  (globalThis.__wasmRequests ??= []).push(structuredClone(spec));
  const result = observedRender.call(this, spec);
  (globalThis.__wasmLayouts ??= []).push(result.layout());
  return result;
};` });
  });
  await page.goto(url, { waitUntil: "networkidle" });
  // One tester: only the selected family renders.
  assert.deepEqual(await page.locator("#font-select option").allTextContents(), ["Roboto", "Literata", "Source Sans 3", "Roboto Italic", "Roboto Flex"]);
  assert.equal(await page.locator("#font-select").inputValue(), "roboto");
  assert.equal(await page.locator(".interactive-specimen:visible").count(), 1);
  await page.waitForFunction(() => document.querySelector("#interactive-roboto canvas")?.dataset.rendered === "true");
  assert.equal(await page.locator("#interactive-roboto [data-size]").isEnabled(), true);

  const initial = await snapshot(page, "roboto");
  assert.equal(initial.height, 34);
  assert.equal(await page.locator("#interactive-roboto [data-text]").inputValue(), READING_TEXT);
  assert.equal(await page.locator("#interactive-roboto [data-preset]").inputValue(), "reading");

  // Live candidate/baseline routing at the reported axes, followed by gray
  // identity. Compare the same content/layout; no frozen pixel snapshots.
  if (await page.locator('input[name="renderer-role"][value="candidate"]').count()) {
    await page.locator("#interactive-roboto [data-text]").fill("a a a\nabcdefg hmnopqrsuvwxyz");
    for (const weight of [100, 200]) {
      await page.locator("#interactive-roboto-wght").fill(String(weight));
      await page.locator('input[name="renderer-role"][value="baseline"]').check();
      await page.waitForTimeout(800);
      const baseline = await snapshot(page, "roboto");
      await page.locator('input[name="renderer-role"][value="candidate"]').check();
      await page.waitForTimeout(800);
      const candidate = await snapshot(page, "roboto");
      assert.deepEqual([candidate.width, candidate.height], [baseline.width, baseline.height]);
      const requests = await page.evaluate(() => globalThis.__wasmRequests);
      const baselineRequest = requests.findLast((spec) => spec.renderer === "baseline");
      const candidateRequest = requests.at(-1);
      assert.equal(candidateRequest.renderer, "candidate");
      assert.deepEqual(candidateRequest, { ...baselineRequest, renderer: "candidate" });
    }
    await page.locator('.profile-options input[value="gray_3bit"]').check();
    await page.waitForTimeout(800);
    const candidateGray = await snapshot(page, "roboto");
    await page.locator('input[name="renderer-role"][value="baseline"]').check();
    await page.waitForTimeout(800);
    assert.deepEqual(await snapshot(page, "roboto"), candidateGray);
    await page.locator('input[name="renderer-role"][value="candidate"]').check();
    await page.locator('.profile-options input[value="mono_1bit"]').check();
    await page.locator("#interactive-roboto [data-reset]").click();
    await page.waitForTimeout(800);
    assert.deepEqual(await snapshot(page, "roboto"), initial);
  }

  // Switching swaps metadata and controls; switching back restores the
  // exact render while the idle family stays untouched.
  await page.locator("#font-select").selectOption("literata");
  await page.waitForFunction(() => document.querySelector("#interactive-literata canvas")?.dataset.rendered === "true");
  assert.equal(await page.locator("#interactive-literata-opsz").inputValue(), "14");
  assert.equal(await page.locator("#interactive-roboto").isVisible(), false);
  const literataInitial = await snapshot(page, "literata");
  await page.locator("#font-select").selectOption("roboto");
  await page.waitForTimeout(800);
  assert.deepEqual(await snapshot(page, "roboto"), initial);
  assert.equal(await page.locator("#interactive-roboto [data-text]").inputValue(), READING_TEXT);

  await page.locator("#interactive-roboto [data-preset]").selectOption("numbers");
  await page.waitForTimeout(800);
  assert.equal(await page.locator("#interactive-roboto [data-text]").inputValue(), NUMBERS_TEXT);
  const numbers = await snapshot(page, "roboto");
  assert.notEqual(numbers.sum, initial.sum);
  assert.deepEqual(await snapshot(page, "literata"), literataInitial);

  // Published pair presets reach the actual renderer at the user's axes;
  // switching renderer roles preserves the same text, size and axes.
  await page.locator("#interactive-roboto-wght").fill("536");
  for (const id of ["spacing-pairs", "spacing-rhythm"]) {
    await page.locator("#interactive-roboto [data-preset]").selectOption(id);
    await page.waitForTimeout(800);
    assert.equal(await page.locator("#interactive-roboto [data-text]").inputValue(), configuredCards.find((card) => card.id === id).content);
    assert.equal(await page.locator("#interactive-roboto canvas").getAttribute("data-rendered"), "true");
    assert.equal(await page.locator("#interactive-roboto [data-status]").isHidden(), true);
    for (const role of ["baseline", "candidate"]) {
      await page.locator(`input[name="renderer-role"][value="${role}"]`).check();
      await page.waitForTimeout(800);
      const request = await page.evaluate(() => globalThis.__wasmRequests.at(-1));
      assert.equal(request.renderer, role);
      assert.equal(request.text, configuredCards.find((card) => card.id === id).content);
      assert.equal(await page.locator("#interactive-roboto-wght").inputValue(), "536");
    }
  }
  // Signed tracking reaches real WASM, including spaces and kerned pairs.
  await page.locator("#interactive-roboto [data-text]").fill("mi li ni AV VA");
  await page.waitForTimeout(800);
  const neutralTracking = await snapshot(page, "roboto");
  const neutralLayout = await page.evaluate(() => globalThis.__wasmLayouts.at(-1));
  assert.equal(await page.locator("#interactive-roboto [data-spacing]").inputValue(), "0");
  await page.locator("#interactive-roboto [data-spacing]").fill("1");
  await page.waitForFunction(() => globalThis.__wasmRequests.at(-1).letter_spacing_px === 1);
  const widerLayout = await page.evaluate(() => globalThis.__wasmLayouts.at(-1));
  assert.equal(widerLayout.lines[0].width_26_6 - neutralLayout.lines[0].width_26_6, "mi li ni AV VA".length * 64);
  assert.notEqual((await snapshot(page, "roboto")).positionSum, neutralTracking.positionSum);
  assert.equal(await page.locator("#interactive-roboto [data-spacing-number]").inputValue(), "1");
  for (const role of ["baseline", "candidate"]) {
    await page.locator(`input[name="renderer-role"][value="${role}"]`).check();
    await page.waitForTimeout(800);
    assert.equal(await page.evaluate(() => globalThis.__wasmRequests.at(-1).letter_spacing_px), 1);
  }
  await page.locator("#interactive-roboto [data-spacing-number]").fill("-0.5");
  await page.waitForFunction(() => globalThis.__wasmRequests.at(-1).letter_spacing_px === -1);
  assert.equal(await page.locator("#interactive-roboto [data-spacing-number]").inputValue(), "-1");
  await page.locator("#interactive-roboto [data-spacing]").fill("0");
  await page.waitForFunction(() => globalThis.__wasmRequests.at(-1).letter_spacing_px === 0);
  assert.deepEqual(await snapshot(page, "roboto"), neutralTracking);
  // At the reported axes, the preset puts in and ac after earlier glyphs.
  // Inspect delivered columns, not ink totals, to verify the new constraint.
  await page.locator("#interactive-roboto-wght").fill("641");
  await page.locator("#interactive-roboto [data-preset]").selectOption("spacing-pairs");
  await page.locator("#interactive-roboto [data-spacing-number]").fill("-0.5");
  await page.waitForFunction(() => globalThis.__wasmRequests.at(-1).axes.wght === 641 && globalThis.__wasmRequests.at(-1).letter_spacing_px === -1);
  const columns = await page.locator("#interactive-roboto canvas").evaluate((canvas) => {
    const data = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
    const lineHeight = canvas.height / 7;
    return [0, 2].map((line) => {
      const spans = [];
      for (let x = 0; x < canvas.width; x++) {
        let ink = false;
        for (let y = line * lineHeight; y < (line + 1) * lineHeight; y++) {
          if (data[(y * canvas.width + x) * 4] < 250) { ink = true; break; }
        }
        if (ink) {
          if (!spans.length || x > spans.at(-1)[1] + 1) spans.push([x, x]);
          else spans.at(-1)[1] = x;
        }
      }
      return spans;
    });
  });
  assert.equal(columns[0].length, 12);
  for (const i of [0, 2, 4, 6, 8, 10]) assert.equal(columns[0][i + 1][0] - columns[0][i][1] - 1, 1);
  assert.equal(columns[1][2][0] - columns[1][1][1] - 1, 1); // ac inside Pac
  await page.locator("#interactive-roboto [data-spacing]").fill("0");
  await page.waitForFunction(() => globalThis.__wasmRequests.at(-1).letter_spacing_px === 0);
  // Interchange spacing while keeping the actual glyph renderer and axes.
  for (const model of ["source", "fitted", "projected", "auto"]) {
    await page.locator("#interactive-roboto [data-spacing-model]").selectOption(model);
    await page.waitForFunction((name) => globalThis.__wasmRequests.at(-1).spacing_model === name, model);
    const request = await page.evaluate(() => globalThis.__wasmRequests.at(-1));
    assert.equal(request.renderer, "candidate");
    assert.equal(request.axes.wght, 641);
    assert.equal(request.text, configuredCards.find((card) => card.id === "spacing-pairs").content);
    assert.equal(await page.locator("#interactive-roboto [data-status]").isHidden(), true);
  }
  await page.locator("#interactive-roboto [data-kerning]").uncheck();
  await page.waitForFunction(() => globalThis.__wasmRequests.at(-1).kerning === false);
  await page.locator("#interactive-roboto [data-kerning]").check();
  await page.waitForFunction(() => globalThis.__wasmRequests.at(-1).kerning === true);
  await page.locator("#interactive-roboto-wght").fill("400");

  await page.locator("#interactive-roboto [data-text]").fill("Custom\nmultiline edit");
  await page.waitForTimeout(800);
  assert.equal(await page.locator("#interactive-roboto [data-preset]").inputValue(), "custom");
  assert.notEqual((await snapshot(page, "roboto")).sum, numbers.sum);

  // A long single paragraph wraps to the laid-out line count: the canvas
  // grows past the two-line height within the same display width.
  await page.locator("#interactive-roboto [data-text]").fill("minimum AVATAR To Wa ".repeat(30));
  await page.waitForTimeout(800);
  const wrapped = await snapshot(page, "roboto");
  assert.equal(wrapped.width, initial.width);
  assert.ok(wrapped.height > initial.height);
  assert.ok(wrapped.height <= 4096);
  assert.notEqual(wrapped.sum, numbers.sum);

  // Narrowing the viewport wraps the same text into more lines, so the
  // canvas grows taller without widening the page.
  await page.setViewportSize({ width: 500, height: 900 });
  await page.waitForFunction((height) => document.querySelector("#interactive-roboto canvas").height > height, wrapped.height);
  const narrow = await snapshot(page, "roboto");
  assert.ok(narrow.height > wrapped.height);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  await page.setViewportSize({ width: 1100, height: 900 });
  await page.waitForTimeout(800);

  await page.locator("#interactive-roboto [data-text]").fill("Custom\nmultiline edit");
  await page.waitForTimeout(800);
  await page.locator("#interactive-roboto [data-size]").fill("20");
  await page.waitForFunction((before) => {
    const canvas = document.querySelector("#interactive-roboto canvas");
    const data = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
    let sum = 0;
    for (let i = 0; i < data.length; i++) sum = (sum + data[i]) % 4294967296;
    return sum !== before;
  }, wrapped.sum);
  const sized = await snapshot(page, "roboto");
  assert.deepEqual(await snapshot(page, "literata"), literataInitial);

  await page.locator("#interactive-roboto-wght").fill("700");
  await page.waitForTimeout(800);
  const weighted = await snapshot(page, "roboto");
  assert.notEqual(weighted.sum, sized.sum);
  assert.deepEqual(await snapshot(page, "literata"), literataInitial);

  await page.locator("#interactive-roboto [data-text]").evaluate((el) => el.blur());
  await page.waitForTimeout(500);

  await page.locator(".profile-options label").filter({ hasText: "3-bit" }).click();
  await page.waitForTimeout(800);
  const gray = await snapshot(page, "roboto");
  assert.notEqual(gray.sum, weighted.sum);

  // Zoom magnifies the same request: the display width stays fixed while the
  // content height scales with zoom, the size input is retained, and the
  // magnified pixels differ.
  await page.locator("#zoom").fill("3");
  await page.waitForTimeout(800);
  const zoomed = await snapshot(page, "roboto");
  assert.equal(zoomed.width, gray.width);
  assert.equal(zoomed.height, gray.height * 4);
  assert.equal(zoomed.style[0], gray.style[0]);
  assert.notEqual(zoomed.sum, gray.sum);
  assert.equal(await page.locator("#interactive-roboto [data-size]").inputValue(), "20");

  await page.locator(".profile-options label").filter({ hasText: "1-bit" }).click();
  await page.waitForTimeout(800);
  await page.locator("#interactive-roboto [data-reset]").click();
  await page.waitForFunction(() => document.querySelector("#interactive-roboto [data-size]").value === "14");
  await page.waitForTimeout(800);
  const reset = await snapshot(page, "roboto");
  assert.equal(reset.height, initial.height * 4);
  assert.equal(await page.locator("#interactive-roboto-wght").inputValue(), "400");
  assert.equal(await page.locator("#interactive-roboto [data-text]").inputValue(), READING_TEXT);
  assert.equal(await page.locator("#interactive-roboto [data-preset]").inputValue(), "reading");

  // Text taller than the native 4096px limit reports a concise overflow
  // status instead of silently truncating.
  await page.locator("#zoom").fill("0");
  await page.waitForTimeout(800);
  await page.locator("#interactive-roboto [data-text]").fill(Array.from({ length: 400 }, () => "Overflow row").join("\n"));
  await page.waitForFunction(() => document.querySelector("#interactive-roboto canvas").height === 4096);
  assert.match(await page.locator("#interactive-roboto [data-status]").textContent(), /too long/);
  assert.deepEqual(errors, []);
});
