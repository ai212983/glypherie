import assert from "node:assert/strict";
import test from "node:test";
import {
  bootLibrary,
  browserAvailable,
  buildApp,
  canvasRendered,
  cardIds,
  cardNames,
  launch,
  openNewVariant,
  servePrefix,
} from "../helpers/spa-helpers.ts";
import type { Page } from "playwright-core";

async function isDark(page: Page): Promise<boolean> {
  return page.evaluate(() => document.documentElement.classList.contains("dark"));
}

async function bodyBackground(page: Page): Promise<string> {
  return page.evaluate(() => getComputedStyle(document.documentElement).backgroundColor);
}

async function canvasDigest(page: Page): Promise<{ hash: number; ink: number }> {
  return page.evaluate(() => {
    const canvas = document.querySelector(".interactive-canvas") as HTMLCanvasElement | null;
    if (!canvas) throw new Error("Preview canvas is missing.");
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas 2D context unavailable.");
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let hash = 0x811c9dc5;
    let ink = 0;
    for (let i = 0; i < data.length; i += 1) {
      hash ^= data[i]!;
      hash = Math.imul(hash, 0x01000193);
      if (i % 4 !== 3 && data[i] !== 255) ink += 1;
    }
    return { hash: hash >>> 0, ink };
  });
}

test("OS dark boots dark; toggle switches both ways and persists", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: "dark" });
  const page = await context.newPage();
  await bootLibrary(page, url);
  assert.equal(await isDark(page), true);
  assert.equal(await bodyBackground(page), "rgb(18, 21, 22)");
  assert.equal(await page.locator("[data-theme-toggle]").getAttribute("aria-label"), "Switch to light mode");

  await page.locator("[data-theme-toggle]").click();
  await page.waitForFunction(() => !document.documentElement.classList.contains("dark"));
  assert.equal(await page.locator("[data-theme-toggle]").getAttribute("aria-label"), "Switch to dark mode");

  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  assert.equal(await isDark(page), false, "explicit light choice persists across reload");

  await page.locator("[data-theme-toggle]").click();
  await page.waitForFunction(() => document.documentElement.classList.contains("dark"));
  const names = await cardNames(page);
  const ids = await cardIds(page);
  await openNewVariant(page, ids[0]!);
  await page.waitForFunction(
    (name) => document.querySelector(".family h2")?.textContent === name,
    names[0],
  );
  await page.waitForFunction(canvasRendered);
  assert.equal(await isDark(page), true, "explicit dark choice persists across navigation");
  await context.close();
});

test("follows OS changes until an explicit override", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, colorScheme: "light" });
  await bootLibrary(page, url);
  assert.equal(await isDark(page), false);

  await page.emulateMedia({ colorScheme: "dark" });
  await page.waitForFunction(() => document.documentElement.classList.contains("dark"));
  await page.emulateMedia({ colorScheme: "light" });
  await page.waitForFunction(() => !document.documentElement.classList.contains("dark"));

  await page.locator("[data-theme-toggle]").click();
  await page.waitForFunction(() => document.documentElement.classList.contains("dark"));
  await page.emulateMedia({ colorScheme: "light" });
  await page.waitForTimeout(300);
  assert.equal(await isDark(page), true, "explicit choice ignores later OS changes");
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  assert.equal(await isDark(page), true, "explicit choice persists across reload");
});

test("sticky header, dark chrome, and theme-independent render bytes", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: "dark" });
  const page = await context.newPage();
  await bootLibrary(page, url);
  const names = await cardNames(page);
  const ids = await cardIds(page);
  await openNewVariant(page, ids[0]!);
  await page.waitForFunction(
    (name) => document.querySelector(".family h2")?.textContent === name,
    names[0],
  );
  await page.waitForFunction(canvasRendered);

  const chrome = await page.evaluate(() => {
    const css = (selector: string, property: string): string => {
      const element = document.querySelector(selector);
      if (!element) throw new Error(`Missing chrome element ${selector}.`);
      return getComputedStyle(element)[property as "backgroundColor" | "color" | "borderTopColor"];
    };
    return {
      header: css("[data-site-header]", "backgroundColor"),
      card: css(".interactive-preview", "backgroundColor"),
      pill: css(".profile-options input:checked + span", "backgroundColor"),
      soft: css(".font-metadata", "color"),
    };
  });
  assert.notEqual(chrome.header, "rgba(0, 0, 0, 0)");
  assert.notEqual(chrome.pill, "rgb(33, 107, 89)", "selected profile leaves its light fill in dark mode");
  assert.notEqual(chrome.card, "rgb(255, 255, 255)", "cards leave the light surface in dark mode");
  assert.notEqual(chrome.soft, "rgb(98, 107, 112)", "soft text leaves its light value in dark mode");

  const before = await canvasDigest(page);
  assert.ok(before.ink > 100);
  await page.locator("[data-theme-toggle]").click();
  await page.waitForFunction(() => !document.documentElement.classList.contains("dark"));
  const after = await canvasDigest(page);
  assert.deepEqual(after, before, "UI theme never changes preview bitmap bytes");

  const tall = await page.evaluate(() => document.documentElement.scrollHeight > window.innerHeight + 100);
  assert.ok(tall, "detail page scrolls at desktop height");
  await page.evaluate(() => window.scrollTo(0, 999999));
  const stuck = await page.evaluate(() => document.querySelector("[data-site-header]")?.getBoundingClientRect().top ?? -1);
  assert.equal(stuck, 0, "title header sticks to the viewport top after scrolling");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 999999));
  const mobile = await page.evaluate(() => ({
    top: document.querySelector("[data-site-header]")?.getBoundingClientRect().top ?? -1,
    overflow: document.documentElement.scrollWidth - window.innerWidth,
  }));
  assert.equal(mobile.top, 0, "title header sticks on mobile widths");
  assert.ok(mobile.overflow <= 0, `no horizontal overflow, got ${mobile.overflow}px`);
  await context.close();
});

test("toggle works while bootstrapping and without storage", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: "light" });
  await context.addInitScript(() => {
    Storage.prototype.getItem = () => null;
    Storage.prototype.setItem = () => { throw new Error("storage denied"); };
  });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const booted = bootLibrary(page, url);
  await page.waitForFunction(() => document.querySelector("[data-theme-toggle]") !== null, null, { timeout: 20000 });
  await page.locator("[data-theme-toggle]").click();
  await page.waitForFunction(() => document.documentElement.classList.contains("dark"));
  await booted;
  assert.equal(await isDark(page), true, "in-memory choice survives bootstrap without storage");
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  assert.equal(await isDark(page), false, "reload falls back to the OS preference without storage");
  assert.deepEqual(errors, []);
  await context.close();
});
