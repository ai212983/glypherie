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

async function snapshot(page, family) {
  return page.evaluate((id) => {
    const canvas = document.querySelector(`#interactive-${id} canvas`);
    const context = canvas.getContext("2d");
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let sum = 0;
    for (let i = 0; i < data.length; i++) sum = (sum + data[i]) % 4294967296;
    return { width: canvas.width, height: canvas.height, style: canvas.style.width, sum };
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
  await page.waitForFunction(() => document.querySelector("#interactive-roboto canvas")?.dataset.rendered === "true");
  await page.waitForFunction(() => document.querySelector("#interactive-literata canvas")?.dataset.rendered === "true");
  assert.equal(await page.locator("#interactive-roboto [data-size]").isEnabled(), true);

  const initial = await snapshot(page, "roboto");
  assert.equal(initial.height, 48);
  const literataInitial = await snapshot(page, "literata");
  assert.equal(await page.locator("#interactive-literata-opsz").inputValue(), "14");

  await page.locator("#interactive-roboto [data-size]").fill("20");
  await page.waitForFunction(() => document.querySelector("#interactive-roboto canvas").height === 60);
  const sized = await snapshot(page, "roboto");
  assert.notEqual(sized.sum, initial.sum);
  assert.deepEqual(await snapshot(page, "literata"), literataInitial);

  await page.locator("#interactive-roboto-wght").fill("700");
  await page.waitForFunction(() => document.querySelector("#interactive-roboto canvas").height === 60
    && document.querySelector("#interactive-roboto-wght").value === "700");
  await page.waitForTimeout(500);
  const weighted = await snapshot(page, "roboto");
  assert.notEqual(weighted.sum, sized.sum);
  assert.deepEqual(await snapshot(page, "literata"), literataInitial);

  await page.locator('#interactive-roboto [data-text]').fill("Hi there");
  await page.waitForTimeout(800);
  assert.notEqual((await snapshot(page, "roboto")).sum, weighted.sum);

  await page.locator(".profile-options label").filter({ hasText: "3-bit" }).click();
  await page.waitForTimeout(800);
  const gray = await snapshot(page, "roboto");

  await page.locator("#zoom").fill("3");
  await page.waitForFunction(() => document.querySelector("#interactive-roboto canvas").style.width === "2880px");
  assert.deepEqual(await snapshot(page, "roboto"), { ...gray, style: "2880px" });

  await page.locator(".profile-options label").filter({ hasText: "1-bit" }).click();
  await page.waitForTimeout(800);
  await page.locator("#interactive-roboto [data-reset]").click();
  await page.waitForFunction(() => document.querySelector("#interactive-roboto [data-size]").value === "14");
  await page.waitForTimeout(800);
  const reset = await snapshot(page, "roboto");
  assert.equal(reset.sum, initial.sum);
  assert.equal(await page.locator("#interactive-roboto-wght").inputValue(), "400");
  assert.deepEqual(errors, []);
});
