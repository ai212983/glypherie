import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import http from "node:http";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright-core";
import { build, fixture } from "./helpers.js";

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

test("index shows one interactive specimen per family and keeps controls across profiles", { skip: !browserAvailable }, async (t) => {
  const f = await fixture(t);
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
  // Published sample rows, size sections, glyph grids, and comparison
  // statistics no longer render on the index; glyph routes stay standalone.
  assert.equal(await page.locator(".specimen-card").count(), 0);
  assert.equal(await page.locator(".size-group").count(), 0);
  assert.equal(await page.locator(".page-footer").count(), 0);
  assert.equal(await page.locator(".font-metadata").count(), 1);
  assert.match(await page.locator(".font-metadata").innerText(), /Kerning\s+Yes/);
  assert.match(await page.locator(".font-metadata").innerText(), /Weight \(wght\): 100–900/);
  assert.equal(await page.locator(".interactive-specimen").count(), 1);
  assert.deepEqual(await page.locator("#font-select option").allTextContents(), ["Fixture font"]);
  assert.equal(await page.locator("#font-select").inputValue(), "fixture");
  assert.equal(await page.getByRole("radio", { name: "1-bit", exact: true }).isChecked(), true);
  assert.equal(await page.locator(".variant span").textContent(), "reference");
  assert.equal(await page.locator("#zoom").isEnabled(), true);
  // The fixture font has no configured source, so its block is disabled.
  await page.locator("#interactive-fixture [data-status]:visible").waitFor();
  assert.equal(await page.locator("#interactive-fixture [data-size]").isDisabled(), true);
  assert.equal(await page.locator("#interactive-fixture [data-text]").isDisabled(), true);
  assert.equal(await page.locator("#interactive-fixture [data-preset]").isDisabled(), true);

  await page.locator(".profile-options label").filter({ hasText: "3-bit" }).click();
  assert.equal(await page.locator(".family:visible").count(), 1);
  assert.equal(await page.locator("#family-fixture").isVisible(), true);
  assert.equal(await page.locator(".interactive-specimen:visible").count(), 1);
  await page.locator(".profile-options label").filter({ hasText: "1-bit" }).click();
  assert.equal(await page.locator(".family:visible").count(), 1);

  await page.locator("#zoom").fill("3");
  assert.equal(await page.locator("#zoom-value").textContent(), "4×");
  assert.equal(await page.locator("#zoom").getAttribute("aria-valuetext"), "4×");
  await page.reload({ waitUntil: "networkidle" });
  assert.equal(await page.locator("#zoom-value").textContent(), "4×");
  assert.equal(await page.locator(".family:visible").count(), 1);
  assert.deepEqual(errors, []);
  assert.deepEqual(failedRequests, []);

  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 1100, height: 900 } });
  const staticPage = await context.newPage();
  await staticPage.goto(url);
  assert.equal(await staticPage.locator("#zoom").isDisabled(), true);
  assert.equal(await staticPage.getByRole("radio", { name: "1-bit", exact: true }).isDisabled(), true);
  assert.equal(await staticPage.locator(".interactive-specimen").count(), 1);
  assert.equal(await staticPage.locator(".specimen-card").count(), 0);
  await context.close();
});

test("output mode switching keeps every interactive family visible", { skip: !browserAvailable }, async (t) => {
  const f = await fixture(t);
  const second = structuredClone(f.manifest.families[0]);
  second.id = "second";
  second.name = "Second font";
  for (const group of second.sizes) for (const item of group.items) item.id += "-second";
  f.manifest.families.push(second);
  await f.save();
  await build(f.root, f.output);
  const url = await serve(t, f.output);
  const browser = await chromium.launch({ executablePath: browserPath, headless: true });
  t.after(() => browser.close());
  const page = await browser.newPage();
  await page.goto(url, { waitUntil: "networkidle" });
  assert.deepEqual(await page.locator("#font-select option").allTextContents(), ["Fixture font", "Second font"]);
  assert.equal(await page.locator(".family:visible").count(), 1);
  assert.equal(await page.locator("#family-fixture").isVisible(), true);
  assert.equal(await page.locator(".interactive-specimen:visible").count(), 1);
  await page.locator("#font-select").selectOption("second");
  assert.equal(await page.locator("#family-second").isVisible(), true);
  assert.equal(await page.locator("#family-fixture").isVisible(), false);
  await page.locator(".profile-options label").filter({ hasText: "3-bit" }).click();
  assert.equal(await page.locator(".family:visible").count(), 1);
  assert.equal(await page.locator("#family-second").isVisible(), true);
  assert.equal(await page.locator(".interactive-specimen:visible").count(), 1);
});

test("a family anchor preselects that font on load and hash change", { skip: !browserAvailable }, async (t) => {
  const f = await fixture(t);
  const second = structuredClone(f.manifest.families[0]);
  second.id = "second";
  second.name = "Second font";
  for (const group of second.sizes) for (const item of group.items) item.id += "-second";
  f.manifest.families.push(second);
  await f.save();
  await build(f.root, f.output);
  const url = await serve(t, f.output);
  const browser = await chromium.launch({ executablePath: browserPath, headless: true });
  t.after(() => browser.close());
  const page = await browser.newPage();
  await page.goto(`${url}#family-second`, { waitUntil: "networkidle" });
  assert.equal(await page.locator("#font-select").inputValue(), "second");
  assert.equal(await page.locator(".family:visible").count(), 1);
  assert.equal(await page.locator("#family-second").isVisible(), true);
  await page.evaluate(() => { location.hash = "#family-fixture"; });
  await page.waitForFunction(() => document.querySelector("#font-select").value === "fixture");
  assert.equal(await page.locator("#family-fixture").isVisible(), true);
  assert.equal(await page.locator(".family:visible").count(), 1);
});
