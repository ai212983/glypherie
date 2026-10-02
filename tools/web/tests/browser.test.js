import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import http from "node:http";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright-core";
import { PNG } from "pngjs";
import { build, fixture, hash, png } from "./helpers.js";

const browserPath = process.env.WEB_TEST_BROWSER ?? "/opt/google/chrome/chrome";
const browserAvailable = await fs.access(browserPath).then(() => true, () => false);

async function serve(t, root) {
  const mime = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".png": "image/png", ".json": "application/json" };
  const server = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url, "http://localhost");
      if (!url.pathname.startsWith("/preview/")) throw new Error("Unknown prefix");
      const relative = decodeURIComponent(url.pathname.slice("/preview/".length)) || "index.html";
      const file = path.resolve(root, relative);
      if (path.relative(root, file).startsWith("..")) throw new Error("Invalid path");
      response.writeHead(200, { "Content-Type": mime[path.extname(file)] ?? "application/octet-stream" });
      response.end(await fs.readFile(file));
    } catch {
      response.writeHead(404);
      response.end();
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise((resolve) => server.close(resolve)));
  return `http://127.0.0.1:${server.address().port}/preview/`;
}

test("HTTP preview supports native pixels, all zoom stops, wrapping, local scrolling, and prefixes", { skip: !browserAvailable }, async (t) => {
  const f = await fixture(t);
  const width = 280;
  const height = 60;
  const bytes = png(Array.from({ length: width * height }, (_, i) => i % 3 ? 255 : 0), width, height);
  const imageHash = hash(bytes);
  const grayPalette = [0, 36, 73, 109, 146, 182, 219, 255];
  const grayBytes = png(Array.from({ length: width * height }, (_, i) => grayPalette[i % grayPalette.length]), width, height);
  const grayHash = hash(grayBytes);
  const group = f.manifest.families[0].sizes[0];
  group.thumbnail = { width_px: width, height_px: height };
  const original = group.items[0];
  group.items = Array.from({ length: 6 }, (_, i) => {
    const sha256 = i % 2 ? grayHash : imageHash;
    return { ...original, id: `sample-${i}`, profile: i % 2 ? "gray_3bit" : "mono_1bit", image: { path: `assets/${sha256}.png`, sha256 } };
  });
  await fs.writeFile(path.join(f.packageDir, "assets", `${imageHash}.png`), bytes);
  await fs.writeFile(path.join(f.packageDir, "assets", `${grayHash}.png`), grayBytes);
  await f.save();
  await build(f.root, f.output);
  const url = await serve(t, f.output);
  const browser = await chromium.launch({ executablePath: browserPath, headless: true });
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1100, height: 900 } });
  const errors = [];
  const failedRequests = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => { if (response.status() >= 400 && !response.url().endsWith("favicon.ico")) failedRequests.push(response.url()); });
  await page.goto(url, { waitUntil: "networkidle" });
  assert.equal(await page.locator(".specimen-card").count(), 6);
  assert.equal(await page.locator(".font-metadata").count(), 1);
  assert.match(await page.locator(".font-metadata").innerText(), /Kerning\s+Yes/);
  assert.match(await page.locator(".font-metadata").innerText(), /Weight \(wght\): 100–900/);
  assert.equal(await page.locator(".specimen-card:visible").count(), 3);
  assert.equal(await page.getByRole("radio", { name: "1-bit", exact: true }).isChecked(), true);
  assert.equal(await page.locator(".variant span").textContent(), "reference");
  assert.equal(await page.locator("#zoom").isEnabled(), true);
  const measure = () => page.evaluate(() => ({
    images: [...document.querySelectorAll(".specimen-card:not([hidden]) img")].map((image) => ({ width: image.getBoundingClientRect().width, height: image.getBoundingClientRect().height, src: image.currentSrc, rendering: getComputedStyle(image).imageRendering, loaded: image.complete && image.naturalWidth > 0 })),
    rows: [...document.querySelectorAll(".specimen-card:not([hidden])")].map((card) => card.getBoundingClientRect().top),
    captionSize: getComputedStyle(document.querySelector("figcaption")).fontSize,
    pageWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
    areas: [...document.querySelectorAll(".specimen-card:not([hidden]) .image-viewport")].map((area) => ({ width: area.clientWidth, scrollWidth: area.scrollWidth, height: area.clientHeight })),
  }));
  for (const [profile, label, palette] of [["mono_1bit", "1-bit", [0, 255]], ["gray_3bit", "3-bit", grayPalette]]) {
    await page.locator(".profile-options label").filter({ hasText: label }).click();
    await page.waitForFunction(() => [...document.querySelectorAll(".specimen-card:not([hidden]) img")].every((image) => image.complete && image.naturalWidth > 0));
    assert.deepEqual(await page.locator(".specimen-card:visible").evaluateAll((cards) => [...new Set(cards.map((card) => card.dataset.profile))]), [profile]);
    assert.equal(await page.locator(".specimen-card:visible").count(), 3);
    const native = await measure();
    assert.ok(native.images.every((i) => i.width === width && i.height === height && i.loaded && i.rendering === "pixelated"));
    for (const [stop, zoom] of [[1, 2], [2, 3], [3, 4], [0, 1]]) {
      await page.locator("#zoom").fill(String(stop));
      const measured = await measure();
      assert.equal(await page.locator("#zoom-value").textContent(), `${zoom}×`);
      assert.equal(await page.locator("#zoom").getAttribute("aria-valuetext"), `${zoom}×`);
      assert.ok(measured.images.every((i) => i.width === width * zoom && i.height === height * zoom));
      assert.equal(measured.captionSize, native.captionSize);
      assert.deepEqual(measured.images.map((i) => i.src), native.images.map((i) => i.src));
      assert.ok(measured.pageWidth <= measured.viewportWidth);
      if (zoom > 1) assert.ok(new Set(measured.rows).size > new Set(native.rows).size);
      const screenshot = PNG.sync.read(await page.locator(".specimen-card:visible .image-viewport").first().screenshot());
      const displayed = new Set();
      for (let y = 2; y < screenshot.height - 20; y++) for (let x = 2; x < screenshot.width - 2; x++) {
        const offset = (y * screenshot.width + x) * 4;
        displayed.add(screenshot.data[offset]);
        assert.equal(screenshot.data[offset], screenshot.data[offset + 1]);
        assert.equal(screenshot.data[offset], screenshot.data[offset + 2]);
      }
      assert.deepEqual([...displayed].sort((a, b) => a - b), palette);
    }
  }
  await page.locator("#zoom").focus();
  await page.keyboard.press("ArrowRight");
  assert.equal(await page.locator("#zoom-value").textContent(), "2×");
  await page.setViewportSize({ width: 360, height: 800 });
  await page.locator("#zoom").fill("3");
  const mobile = await measure();
  assert.ok(mobile.pageWidth <= mobile.viewportWidth);
  assert.ok(mobile.areas.every((a) => a.width < a.scrollWidth && a.height === height * 4));
  await page.locator(".specimen-card:visible .image-viewport").first().evaluate((area) => { area.scrollLeft = 100; });
  assert.equal(await page.locator(".specimen-card:visible .image-viewport").first().evaluate((area) => area.scrollLeft), 100);
  await page.getByRole("radio", { name: "3-bit", exact: true }).focus();
  await page.keyboard.press("ArrowLeft");
  assert.equal(await page.getByRole("radio", { name: "1-bit", exact: true }).isChecked(), true);
  assert.equal(await page.locator("#zoom-value").textContent(), "4×");
  assert.equal(await page.locator('.specimen-card[data-profile="gray_3bit"]:visible').count(), 0);
  await page.locator("#zoom").fill("2");
  await page.reload({ waitUntil: "networkidle" });
  assert.equal(await page.locator("#zoom-value").textContent(), "3×");
  assert.equal(await page.locator("#zoom").getAttribute("aria-valuetext"), "3×");
  assert.ok((await measure()).images.every((i) => i.width === width * 3 && i.height === height * 3));
  assert.deepEqual(errors, []);
  assert.deepEqual(failedRequests, []);

  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 1100, height: 900 } });
  const staticPage = await context.newPage();
  await staticPage.goto(url);
  assert.equal(await staticPage.locator("#zoom").isDisabled(), true);
  assert.equal(await staticPage.getByRole("radio", { name: "1-bit", exact: true }).isDisabled(), true);
  assert.equal(await staticPage.locator(".specimen-card:visible").count(), 3);
  assert.equal((await staticPage.locator("img").first().boundingBox()).width, width);
  await context.close();
});

test("output mode switching hides unavailable groups and families", { skip: !browserAvailable }, async (t) => {
  const f = await fixture(t);
  const group = f.manifest.families[0].sizes[0];
  const monoOnly = structuredClone(group);
  monoOnly.size_px = 14;
  monoOnly.items = [monoOnly.items[0]];
  monoOnly.items[0].id = "mono-only";
  f.manifest.families[0].sizes.push(monoOnly);
  const grayFamily = structuredClone(f.manifest.families[0]);
  grayFamily.id = "gray-family";
  grayFamily.name = "Gray family";
  grayFamily.sizes = [structuredClone(group)];
  grayFamily.sizes[0].items = [grayFamily.sizes[0].items[1]];
  const grayItem = grayFamily.sizes[0].items[0];
  grayItem.id = "gray-only";
  grayItem.outcome = "unsupported";
  grayItem.reason = "Sample needs investigation.";
  delete grayItem.image;
  f.manifest.families.push(grayFamily);
  await f.save();
  await build(f.root, f.output);
  const url = await serve(t, f.output);
  const browser = await chromium.launch({ executablePath: browserPath, headless: true });
  t.after(() => browser.close());
  const page = await browser.newPage();
  await page.goto(url, { waitUntil: "networkidle" });
  assert.equal(await page.locator(".family:visible").count(), 1);
  assert.equal(await page.locator(".size-group:visible").count(), 2);
  assert.equal(await page.getByRole("navigation", { name: "Font families" }).count(), 0);
  await page.locator(".profile-options label").filter({ hasText: "3-bit" }).click();
  assert.equal(await page.locator(".family:visible").count(), 2);
  assert.equal(await page.locator(".size-group:visible").count(), 2);
  assert.equal(await page.locator('[data-item-id="mono-only"]').isVisible(), false);
  assert.equal(await page.locator(".sample-failure:visible").textContent().then((text) => text.includes("Sample needs investigation.")), true);
});
