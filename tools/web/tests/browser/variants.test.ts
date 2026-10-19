import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import test from "node:test";
import {
  bootDetail,
  bootLibrary,
  browserAvailable,
  buildApp,
  canvasRendered,
  cardIds,
  cardNames,
  cardVariantIds,
  cardVariantNames,
  fontDir,
  hashPath,
  launch,
  openNewVariant,
  servePrefix,
  setRange,
  sha256,
} from "../helpers/spa-helpers.ts";
import type { Page } from "playwright-core";

async function flexId(page: Page): Promise<{ index: number; id: string }> {
  const names = await cardNames(page);
  const ids = await cardIds(page);
  const index = names.findIndex((name) => /^Roboto Flex/.test(name));
  assert.ok(index >= 0, "catalog has Roboto Flex");
  return { index, id: ids[index]! };
}

async function waitSaved(page: Page): Promise<void> {
  await page.waitForFunction(
    () => document.querySelector("[data-save-status]")?.textContent?.startsWith("Saved"),
    null,
    { timeout: 20000 },
  );
}

async function waitEditor(page: Page): Promise<void> {
  await page.waitForFunction(() => document.querySelector("[data-variant-name]") !== null, null, {
    timeout: 20000,
  });
  await page.waitForFunction(canvasRendered, null, { timeout: 20000 });
}

/** Last bundled font id: SHA-256 of its canonical bytes, the library identity. */
async function lastFontId(): Promise<string> {
  return sha256(await fs.readFile(path.join(fontDir, "SourceSans3.ttf")));
}

test("rapid typing saves the final value and reload shows it", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await bootLibrary(page, url);
  const { id } = await flexId(page);
  await openNewVariant(page, id);
  await waitEditor(page);
  await waitSaved(page);

  await page.locator("[data-variant-name]").click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.locator("[data-variant-name]").pressSequentially("QA variant heavy");
  await page.locator("[data-text]").click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.locator("[data-text]").pressSequentially("heavy");
  await waitSaved(page);
  assert.equal(await page.locator("[data-variant-name]").inputValue(), "QA variant heavy");
  assert.equal(await page.locator("[data-text]").inputValue(), "heavy");

  await page.reload({ waitUntil: "networkidle" });
  await waitEditor(page);
  assert.equal(await page.locator("[data-variant-name]").inputValue(), "QA variant heavy");
  assert.equal(await page.locator("[data-text]").inputValue(), "heavy");
  await waitSaved(page);
  assert.deepEqual(errors, []);
});

test("latest edits survive immediate Back and Forward navigation", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const { id } = await flexId(page);
  await openNewVariant(page, id);
  await waitEditor(page);
  await waitSaved(page);

  await page.locator("[data-text]").click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.locator("[data-text]").pressSequentially("back-forward-probe-value");
  await page.goBack();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  await page.goForward();
  await waitEditor(page);
  assert.equal(await page.locator("[data-text]").inputValue(), "back-forward-probe-value");
  await waitSaved(page);
  assert.equal(await page.locator("[data-text]").inputValue(), "back-forward-probe-value");
});

test("a cross-tab write surfaces a conflict notice with explicit reload", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const first = await context.newPage();
  await bootLibrary(first, url);
  const { id } = await flexId(first);
  const variantId = await openNewVariant(first, id);
  await waitEditor(first);
  await waitSaved(first);

  const second = await context.newPage();
  await second.goto(`${url}#/font/${id}/variant/${variantId}/`, { waitUntil: "networkidle" });
  await waitEditor(second);
  await waitSaved(second);

  // Keep the first tab typing so its debounced save cannot fire yet; the
  // second tab commits a rename mid-typing and the first tab's save then
  // conflicts on its stale revision.
  const text = first.locator("[data-text]");
  await text.click();
  await first.keyboard.press("ControlOrMeta+a");
  const typing = text.pressSequentially("local edit text that keeps arriving", { delay: 40 });
  const secondName = second.locator("[data-variant-name]");
  await secondName.click();
  await second.keyboard.press("ControlOrMeta+a");
  await secondName.pressSequentially("Second tab name");
  await waitSaved(second);
  await typing;
  await first.waitForFunction(() => document.querySelector("[data-variant-error]") !== null, null, {
    timeout: 20000,
  });
  assert.equal(
    await first.locator("[data-variant-error] h2").innerText(),
    "Another tab changed this variant.",
  );
  assert.equal(await first.locator("[data-error-reload]").count(), 1, "reload is the only recovery");
  assert.equal(
    await first.locator("[data-text]").inputValue(),
    "local edit text that keeps arriving",
    "local edits are kept",
  );

  await first.locator("[data-error-reload]").click();
  await first.waitForFunction(
    () => (document.querySelector("[data-variant-name]") as HTMLInputElement)?.value === "Second tab name",
    null,
    { timeout: 20000 },
  );
  assert.equal(await first.locator("[data-variant-name]").inputValue(), "Second tab name");
  await waitSaved(first);
  await context.close();
});

test("a blank variant name fails visibly and saves again once fixed", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const { id } = await flexId(page);
  await openNewVariant(page, id);
  await waitEditor(page);
  await waitSaved(page);

  await page.locator("[data-variant-name]").click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.press("Backspace");
  await page.locator("[data-text]").click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.locator("[data-text]").pressSequentially("renamed sample");
  await page.waitForFunction(() => document.querySelector("[data-variant-error]") !== null, null, {
    timeout: 20000,
  });
  assert.equal(
    await page.locator("[data-variant-error] h2").innerText(),
    "This variant could not be saved.",
  );
  assert.equal(await page.locator("[data-error-retry]").count(), 1, "ordinary errors offer retry");

  await page.locator("[data-variant-name]").click();
  await page.locator("[data-variant-name]").pressSequentially("Recovered name");
  await waitSaved(page);
  assert.equal(await page.locator("[data-variant-name]").inputValue(), "Recovered name");
  assert.equal(await page.locator("[data-text]").inputValue(), "renamed sample");

  await page.reload({ waitUntil: "networkidle" });
  await waitEditor(page);
  assert.equal(await page.locator("[data-variant-name]").inputValue(), "Recovered name");
});

test("a cold missing variant route recovers with a working library link", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const probe = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(probe, url);
  const ids = await cardIds(probe);
  await probe.close();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(`${url}#/font/${ids[0]}/variant/00000000-0000-4000-8000-000000000000/`, {
    waitUntil: "networkidle",
  });
  await page.waitForFunction(() => document.querySelector("[data-variant-deleted]") !== null, null, {
    timeout: 20000,
  });
  await page.locator("[data-variant-deleted] [data-all-fonts]").click();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  assert.equal(await hashPath(page), "/");
});

test("denied storage shows a query error with Retry instead of hanging", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.addInitScript(() => {
    window.indexedDB.open = () => {
      throw new Error("IDB denied");
    };
  });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(url, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelector("[data-library-error]") !== null, null, {
    timeout: 20000,
  });
  assert.equal(await page.locator("[data-library-retry]").count(), 1, "a retry is offered");
  const text = (await page.locator("[data-library-error]").textContent()) ?? "";
  assert.ok(
    text.includes("Browser font storage is unavailable in this context."),
    `the supported user message is shown, got: ${text}`,
  );
  assert.ok(!text.includes("IDB denied"), "the underlying cause is not exposed");
  await page.locator("[data-library-retry]").click();
  await page.waitForFunction(() => document.querySelector("[data-library-error]") !== null, null, {
    timeout: 20000,
  });
  assert.deepEqual(errors, [], "query failures never throw during render");
  await context.close();
});

test("delayed seeding still resolves deep links instead of falling back", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const fontId = await lastFontId();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.route("**/*.ttf", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2500));
    await route.continue();
  });
  await page.goto(`${url}#/font/${fontId}/`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("[data-unsaved-preview]") !== null, null, {
    timeout: 30000,
  });
  assert.equal(
    await page.locator(".family h2").innerText(),
    "Source Sans 3",
    "the delayed font renders its preview instead of falling back",
  );
  await page.goto(`${url}#/font/${fontId}/variant/00000000-0000-4000-8000-000000000000/`, {
    waitUntil: "domcontentloaded",
  });
  await page.waitForFunction(() => document.querySelector("[data-variant-deleted]") !== null, null, {
    timeout: 30000,
  });
  assert.equal(await page.locator("[data-font-card]").count(), 0, "no premature library fallback");
});

test("legacy preview Save as variant copies settings without implicit writes", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const { id } = await flexId(page);
  assert.deepEqual(await cardVariantIds(page, id), [], "no variants before the preview loads");

  await bootDetail(page, `${url}#/font/${id}/`);
  await page.locator("[data-size-px]").fill("28");
  await setRange(page, '[data-axis="wght"]', "600");
  await page.locator("[data-text]").click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.locator("[data-text]").pressSequentially("preview copy probe");
  await page.locator("[data-save-variant]").click();
  await waitEditor(page);
  const variantPath = await hashPath(page);
  assert.match(variantPath, new RegExp(`^/font/${id}/variant/[^/]+/$`), "save lands on the new variant route");
  assert.equal(await page.locator("[data-size-px]").inputValue(), "28", "size copies to the saved row");
  assert.equal(await page.locator('[data-axis="wght"]').inputValue(), "600", "axes copy to the saved row");
  assert.equal(await page.locator("[data-text]").inputValue(), "preview copy probe", "text copies to the saved row");
  await waitSaved(page);

  await page.reload({ waitUntil: "networkidle" });
  await waitEditor(page);
  assert.equal(await page.locator("[data-size-px]").inputValue(), "28", "copied settings persist");
  assert.equal(await page.locator("[data-text]").inputValue(), "preview copy probe");

  await page.goto(`${url}#/`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  // The saved-variant list arrives through its own reactive query, so wait
  // for it explicitly instead of assuming it settles with the cards.
  await page.waitForFunction(
    (fontId) => document.querySelectorAll(`[data-variant-link][data-variant-font="${fontId}"]`).length === 1,
    id,
    { timeout: 20000 },
  );
  assert.deepEqual((await cardVariantIds(page, id)).length, 1, "loading the preview created no extra variant");
});

test("variants keep independent settings and Reset restores font defaults", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const { id } = await flexId(page);
  const firstId = await openNewVariant(page, id);
  await waitEditor(page);
  await waitSaved(page);
  const defaultSize = await page.locator("[data-size-px]").inputValue();
  const defaultWght = await page.locator('[data-axis="wght"]').inputValue();

  await page.locator("[data-size-px]").fill("32");
  await setRange(page, '[data-axis="wght"]', "700");
  await waitSaved(page);

  await page.locator("[data-all-fonts]").click();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  const secondId = await openNewVariant(page, id);
  assert.notEqual(secondId, firstId);
  await waitEditor(page);
  assert.equal(await page.locator("[data-size-px]").inputValue(), defaultSize, "new variants start from font defaults");
  assert.equal(await page.locator('[data-axis="wght"]').inputValue(), defaultWght);

  await page.goto(`${url}#/font/${id}/variant/${firstId}/`, { waitUntil: "networkidle" });
  await waitEditor(page);
  assert.equal(await page.locator("[data-size-px]").inputValue(), "32", "saved edits are per-variant");
  await page.locator("[data-reset]").click();
  await waitSaved(page);
  assert.equal(await page.locator("[data-size-px]").inputValue(), defaultSize, "Reset restores the default size");
  assert.equal(await page.locator('[data-axis="wght"]').inputValue(), defaultWght, "Reset restores default axes");
  assert.equal(
    await page.locator("[data-text]").inputValue(),
    "Pack my box with five dozen liquor jugs.",
    "Reset restores the default sample text",
  );

  await page.reload({ waitUntil: "networkidle" });
  await waitEditor(page);
  assert.equal(await page.locator("[data-size-px]").inputValue(), defaultSize);
  await waitSaved(page);
});

test("font cards are not clickable; variants are real child links", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await bootLibrary(page, url);
  const { id } = await flexId(page);
  assert.deepEqual(await cardVariantIds(page, id), [], "fresh fonts start with zero variants");
  assert.equal(
    await page.locator(`[data-font-card="${id}"] a`).count(),
    0,
    "a font card without variants contains no links",
  );

  let reloaded = false;
  page.once("load", () => { reloaded = true; });
  await page.locator(`[data-font-card="${id}"]`).click({ position: { x: 4, y: 4 } });
  await page.waitForTimeout(500);
  assert.equal(reloaded, false, "clicking the card performs no navigation");
  assert.equal(await page.locator("[data-variant-editor]").count(), 0, "clicking the card opens no editor");

  const variantId = await openNewVariant(page, id);
  await waitEditor(page);
  await page.locator("[data-all-fonts]").click();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  // The saved-variant list arrives through its own reactive query, so wait
  // for the new link explicitly instead of assuming it settles with the cards.
  await page.waitForFunction(
    ([fontId, linkId]) => document.querySelector(
      `[data-variant-link="${linkId}"][data-variant-font="${fontId}"]`,
    ) !== null,
    [id, variantId] as [string, string],
    { timeout: 20000 },
  );
  assert.deepEqual(await cardVariantIds(page, id), [variantId], "the saved variant lists under its font");
  assert.deepEqual(await cardVariantNames(page, id), ["Variant 1"]);

  const link = page.locator(`[data-variant-link="${variantId}"]`);
  assert.ok(((await link.getAttribute("href")) ?? "").includes(`#/font/${id}/variant/${variantId}/`));
  assert.equal(await link.getAttribute("aria-label"), "Variant 1");
  await link.focus();
  await page.keyboard.press("Enter");
  await waitEditor(page);
  assert.equal(await hashPath(page), `/font/${id}/variant/${variantId}/`);

  await page.goBack();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  const [tab] = await Promise.all([
    context.waitForEvent("page"),
    page.locator(`[data-variant-link="${variantId}"]`).click({ modifiers: ["Control"] }),
  ]);
  await tab.waitForFunction(() => document.querySelector("[data-variant-name]") !== null, null, {
    timeout: 20000,
  });
  assert.equal(await hashPath(tab), `/font/${id}/variant/${variantId}/`);
  assert.equal(await page.locator("[data-font-card]").count(), 5, "original tab stays on the catalog");
  await context.close();
});
