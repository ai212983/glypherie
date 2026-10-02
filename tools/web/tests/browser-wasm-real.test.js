import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright-core";
import { build, serve, webRoot } from "./helpers.js";

const browserPath = process.env.WEB_TEST_BROWSER ?? "/opt/google/chrome/chrome";
const repoRoot = path.resolve(webRoot, "../..");
const wasmDir = process.env.FONT_WASM_WEB_DIR ?? path.join(repoRoot, "tools/wasm/pkg-web");
const wasmJs = path.join(wasmDir, "font_wasm.js");
const wasmBin = path.join(wasmDir, "font_wasm_bg.wasm");
const published = path.join(repoRoot, "out/specimens/published.json");
const ready = await fs.access(browserPath).then(() => true, () => false)
  && await fs.access(wasmJs).then(() => true, () => false)
  && await fs.access(wasmBin).then(() => true, () => false)
  && await fs.access(published).then(() => true, () => false);

const READING_TEXT = "Pack my box with five dozen liquor jugs.\nminimum AVATAR To Wa";
const NUMBERS_TEXT = "08:38 21.5°C 48%\n0123456789 .,;:!?+-/()";

async function snapshot(page, family) {
  return page.evaluate((id) => {
    const canvas = document.querySelector(`#interactive-${id} canvas`);
    const context = canvas.getContext("2d");
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let sum = 0;
    for (let i = 0; i < data.length; i++) sum = (sum + data[i]) % 4294967296;
    return { width: canvas.width, height: canvas.height, style: [canvas.style.width, canvas.style.height], sum };
  }, family);
}

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
  await page.goto(url, { waitUntil: "networkidle" });
  // One tester: only the selected family renders.
  assert.deepEqual(await page.locator("#font-select option").allTextContents(), ["Roboto", "Literata", "Source Sans 3"]);
  assert.equal(await page.locator("#font-select").inputValue(), "roboto");
  assert.equal(await page.locator(".interactive-specimen:visible").count(), 1);
  await page.waitForFunction(() => document.querySelector("#interactive-roboto canvas")?.dataset.rendered === "true");
  assert.equal(await page.locator("#interactive-roboto [data-size]").isEnabled(), true);

  const initial = await snapshot(page, "roboto");
  assert.equal(initial.height, 34);
  assert.equal(await page.locator("#interactive-roboto [data-text]").inputValue(), READING_TEXT);
  assert.equal(await page.locator("#interactive-roboto [data-preset]").inputValue(), "reading");

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
