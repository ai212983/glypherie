import assert from "node:assert/strict";
import test from "node:test";
import {
  bootLibrary,
  browserAvailable,
  buildApp,
  canvasPixels,
  canvasRendered,
  cardIds,
  cardNames,
  hashParam,
  hashPath,
  launch,
  openNewVariant,
  servePrefix,
  setRange,
} from "../helpers/spa-helpers.ts";

test("back and forward move between catalog and variant with settings kept", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const names = await cardNames(page);
  const ids = await cardIds(page);
  const target = names.findIndex((name) => /^Roboto Flex/.test(name));
  const variantId = await openNewVariant(page, ids[target]!);
  await page.waitForFunction(
    (name) => document.querySelector(".family h2")?.textContent === name,
    names[target],
  );
  await setRange(page, '[data-axis="wght"]', "700");
  await page.waitForFunction(
    () => document.querySelector("[data-save-status]")?.textContent?.startsWith("Saved"),
    null,
    { timeout: 20000 },
  );

  await page.goBack();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length === 5);
  assert.equal(await hashPath(page), "/");

  await page.goForward();
  await page.waitForFunction(() => document.querySelector("[data-variant-name]") !== null, null, {
    timeout: 20000,
  });
  assert.equal(await hashPath(page), `/font/${ids[target]}/variant/${variantId}/`);
  assert.equal(await page.locator('[data-axis="wght"]').inputValue(), "700");
  const rendered = await canvasPixels(page);
  assert.ok(rendered.ink > 100);
});

test("a quick edit survives browser Back and Forward through the database", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const names = await cardNames(page);
  const ids = await cardIds(page);
  const target = names.findIndex((name) => /^Literata/.test(name));
  await openNewVariant(page, ids[target]!);
  await page.waitForFunction(
    (name) => document.querySelector(".family h2")?.textContent === name,
    names[target],
  );
  await page.locator("[data-text]").click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.locator("[data-text]").pressSequentially("kept edit probe");
  await page.goBack();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  await page.goForward();
  await page.waitForFunction(() => document.querySelector("[data-variant-name]") !== null, null, {
    timeout: 20000,
  });
  assert.equal(await page.locator("[data-text]").inputValue(), "kept edit probe");
  assert.equal(await page.locator("[data-variant-error]").count(), 0, "Back never restores stale settings");
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelector("[data-variant-name]") !== null, null, {
    timeout: 20000,
  });
  assert.equal(await page.locator("[data-text]").inputValue(), "kept edit probe");
});

test("hash route wins over a conflicting legacy outer font query", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const names = await cardNames(page);
  const ids = await cardIds(page);
  const first = 0;
  const second = 1;
  await page.goto(`${url}?font=${ids[first]}#/font/${ids[second]}/`, { waitUntil: "networkidle" });
  await page.waitForFunction(
    (name) => document.querySelector(".family h2")?.textContent === name,
    names[second],
  );
  assert.equal(await hashPath(page), `/font/${ids[second]}/`);
});

test("direct hash edits switch variants without a reload", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const ids = await cardIds(page);
  let reloaded = false;
  page.once("load", () => { reloaded = true; });
  const first = await openNewVariant(page, ids[0]!);
  const home = page.getByRole("link", { name: "Glypherie", exact: true });
  assert.equal(await home.getAttribute("href"), "#/");
  await home.focus();
  await home.press("Enter");
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  const second = await openNewVariant(page, ids[0]!);
  assert.notEqual(first, second);
  await page.evaluate(({ font, variant }) => {
    window.location.hash = `#/font/${font}/variant/${variant}/`;
  }, { font: ids[0], variant: first });
  await page.waitForFunction(() => document.querySelector("[data-variant-name]") !== null, null, {
    timeout: 20000,
  });
  assert.equal(await hashPath(page), `/font/${ids[0]}/variant/${first}/`);
  await page.waitForTimeout(300);
  assert.equal(reloaded, false, "hash edits navigate without a document reload");
});

test("a debounced preview write cannot undo navigation to the catalog", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const ids = await cardIds(page);
  await page.goto(`${url}?font=${ids[0]}`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelector('#font-select[data-state]:not(:disabled)') !== null);
  await page.locator("[data-text]").fill("Navigation race probe");
  await page.locator('[data-primary-nav="fonts"]').click();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  await page.waitForTimeout(600);
  assert.equal(await page.locator("[data-font-cards]").count(), 1);
  assert.equal(await hashPath(page), "/");
  assert.equal(await hashParam(page, "v"), null);
});

test("unknown and removed font urls recover visibly on the catalog", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(`${url}#/font/${"0".repeat(64)}/`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  const notice = await page.locator("[data-route-notice]").textContent();
  assert.ok(notice?.includes("not found in this library"), `visible recovery, got: ${notice}`);
  assert.equal(await page.locator("[data-font-card]").count(), 5);

  await page.goto(`${url}?font=${"0".repeat(64)}`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  assert.equal(await page.locator("[data-font-card]").count(), 5);

  await page.goto(`${url}?v=1&font=${"f".repeat(64)}`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  assert.equal(await page.locator("[data-font-card]").count(), 5);

  await page.goto(`${url}#/nope`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  const malformed = await page.locator("[data-route-notice]").textContent();
  assert.ok(malformed?.includes("Page not found"), `malformed route recovery, got: ${malformed}`);
});

test("unknown variant urls recover visibly without creating data", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const ids = await cardIds(page);
  await page.goto(`${url}#/font/${ids[0]}/variant/missing-variant/`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelector("[data-variant-deleted]") !== null, null, {
    timeout: 20000,
  });
  await page.getByRole("link", { name: "Fonts", exact: true }).click();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  assert.equal(await page.locator("[data-variant-link]").count(), 0, "loading a route never creates variants");

  await page.goto(`${url}#/font/${"0".repeat(64)}/variant/whatever/`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  const notice = await page.locator("[data-route-notice]").textContent();
  assert.ok(notice?.includes("not found in this library"), `recovery shown, got: ${notice}`);
  await page.waitForTimeout(1000);
  const settled = await page.locator("[data-route-notice]").textContent();
  assert.ok(
    (settled ?? "").includes("not found in this library"),
    `recovery notice survives paired route events, got: ${settled}`,
  );
  assert.equal(await hashPath(page), "/", "unknown id canonicalizes to the library with its notice");
});

test("variant reload keeps the variant and its saved settings", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const names = await cardNames(page);
  const ids = await cardIds(page);
  const source = names.findIndex((name) => /^Source Sans 3/.test(name));
  const variantId = await openNewVariant(page, ids[source]!);
  await page.waitForFunction(
    (name) => document.querySelector(".family h2")?.textContent === name,
    names[source],
  );
  await page.waitForFunction(canvasRendered);
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelector("[data-variant-name]") !== null, null, {
    timeout: 20000,
  });
  await page.waitForFunction(canvasRendered);
  assert.equal(await page.locator(`#heading-${ids[source]!}`).innerText(), names[source]);
  assert.equal(await hashPath(page), `/font/${ids[source]}/variant/${variantId}/`);
  assert.equal(await hashParam(page, "font"), null, "no redundant font query");
});
