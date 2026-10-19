import assert from "node:assert/strict";
import test from "node:test";
import {
  bootDetail,
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
} from "../helpers/spa-helpers.ts";
import type { Page } from "playwright-core";

async function openVariantByName(page: Page, name: string): Promise<void> {
  const names = await cardNames(page);
  const ids = await cardIds(page);
  const index = names.findIndex((entry) => entry === name);
  assert.ok(index >= 0, `catalog has ${name}`);
  await openNewVariant(page, ids[index]!);
  await page.waitForFunction(
    (expected) => document.querySelector(".family h2")?.textContent === expected,
    name,
  );
  await page.waitForFunction(canvasRendered);
}

test("index boots cleanly and the first variant renders through the worker", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  const failed: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 400 && !response.url().endsWith("favicon.ico")) failed.push(response.url());
  });
  await bootLibrary(page, url);
  const names = await cardNames(page);
  await openVariantByName(page, names[0]!);
  const first = await canvasPixels(page);
  assert.ok(first.width > 0 && first.height > 0);
  assert.ok(first.ink > 100, `expected rendered ink, got ${first.ink}`);
  assert.deepEqual(errors, []);
  assert.deepEqual(failed, []);
});

interface ColorChannels {
  space: "rgb" | "oklch";
  values: number[];
}

function channels(color: string): ColorChannels | null {
  const rgb = color.match(/rgba?\(([^)]+)\)/);
  if (rgb?.[1]) return { space: "rgb", values: rgb[1].split(/[,/]/).slice(0, 3).map(Number) };
  const oklch = color.match(/oklch\(([^)]+)\)/);
  if (oklch?.[1]) return { space: "oklch", values: oklch[1].split(/\s+/).slice(0, 3).map(Number) };
  return null;
}

function isDark(color: string): boolean {
  const parsed = channels(color);
  if (!parsed) return false;
  const first = parsed.values[0] ?? NaN;
  return parsed.space === "rgb" ? first < 60 : first < 0.35;
}

function isLight(color: string): boolean {
  const parsed = channels(color);
  if (!parsed) return false;
  const first = parsed.values[0] ?? NaN;
  return parsed.space === "rgb" ? first > 200 : first > 0.8;
}

function isRed(color: string): boolean {
  const parsed = channels(color);
  if (!parsed) return false;
  const [a = NaN, b = NaN, c = NaN] = parsed.values;
  if (parsed.space === "rgb") return a > 150 && a > b;
  return a > 0.4 && a < 0.75 && b > 0.15 && (c < 60 || c > 300);
}

test("controls resolve to visible theme colors", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, colorScheme: "light" });
  await bootLibrary(page, url);
  await openVariantByName(page, (await cardNames(page))[0]!);
  const styles = await page.evaluate(() => {
    const css = (selector: string): { background: string; color: string; border: string } => {
      const element = document.querySelector(selector);
      if (!element) throw new Error(`Missing styled element ${selector}.`);
      const style = getComputedStyle(element);
      return { background: style.backgroundColor, color: style.color, border: style.borderTopColor };
    };
    return {
      reset: css("[data-reset]"),
      remove: css("[data-delete-variant]"),
      size: css("[data-size-px]"),
      panel: css(".interactive-preview"),
    };
  });
  for (const [name, style] of Object.entries({ reset: styles.reset, remove: styles.remove, panel: styles.panel })) {
    assert.notEqual(style.background, "rgba(0, 0, 0, 0)", `${name} has a resolved background`);
    assert.notEqual(style.background, "transparent", `${name} has a resolved background`);
  }
  assert.ok(isDark(styles.reset.background), `default button background is dark, got ${styles.reset.background}`);
  assert.ok(isLight(styles.reset.color), `default button text is light, got ${styles.reset.color}`);
  assert.ok(isRed(styles.remove.background), `destructive button reads red, got ${styles.remove.background}`);
  const sizeBorder = channels(styles.size.border);
  assert.ok(sizeBorder && !(sizeBorder.values[0] === 0 && sizeBorder.values[1] === 0 && sizeBorder.values[2] === 0), "text input shows a border");
});

test("profile selection and keyboard focus are visible", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, colorScheme: "light" });
  await bootLibrary(page, url);
  await openVariantByName(page, (await cardNames(page))[0]!);
  const backgrounds = await page.evaluate(() => {
    const css = (selector: string): string => {
      const element = document.querySelector(selector);
      if (!element) throw new Error(`Missing profile element ${selector}.`);
      return getComputedStyle(element).backgroundColor;
    };
    return {
      checked: css(".profile-options input:checked + span"),
      unchecked: css(".profile-options input:not(:checked) + span"),
    };
  });
  assert.notEqual(backgrounds.checked, backgrounds.unchecked, "selected profile reads differently");
  assert.notEqual(backgrounds.checked, "rgba(0, 0, 0, 0)", "selected profile has a fill");
  await page.locator("h1").click();
  for (let i = 0; i < 60; i += 1) {
    const profile = await page.evaluate(() => document.activeElement?.matches(".profile-options input") ?? false);
    if (profile) break;
    await page.keyboard.press("Tab");
  }
  const focused = await page.evaluate(() => {
    const active = document.activeElement;
    if (!(active instanceof HTMLInputElement)) return null;
    const span = active.parentElement?.querySelector("span");
    return span ? getComputedStyle(span).boxShadow : null;
  });
  assert.ok(focused && focused !== "none", `keyboard focus shows a ring, got ${focused}`);
});

test("kerning pairs are fetched per font, never from another font's cache", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const names = await cardNames(page);
  const roboto = names.find((name) => /^Roboto Regular$/.test(name))!;
  const literata = names.find((name) => /^Literata/.test(name))!;
  await openVariantByName(page, roboto);
  await page.locator("details.font-kerning > summary").click();
  await page.waitForFunction(() => document.querySelector("[data-kerning-count]")?.textContent?.includes("pairs"));
  const robotoPairs = await page.locator("[data-kerning-list]").innerText();
  assert.ok(robotoPairs.length > 0);
  await openVariantByNameFromLibrary(page, literata);
  await page.locator("details.font-kerning > summary").click();
  await page.waitForFunction(() => document.querySelector("[data-kerning-count]")?.textContent?.includes("pairs"));
  const literataPairs = await page.locator("[data-kerning-list]").innerText();
  assert.notEqual(literataPairs, robotoPairs, "each font serves its own pairs");
});

async function openVariantByNameFromLibrary(page: Page, name: string): Promise<void> {
  await page.locator("[data-all-fonts]").click();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  await openVariantByName(page, name);
}

test("renderer role persists in the variant across reloads, not in the URL", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  await openVariantByName(page, (await cardNames(page))[0]!);
  assert.equal(await page.locator("#renderer-role").inputValue(), "candidate");
  await page.locator("#renderer-role").selectOption("baseline");
  await page.waitForFunction(
    () => document.querySelector("[data-save-status]")?.textContent?.startsWith("Saved"),
    null,
    { timeout: 20000 },
  );
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelector("[data-variant-name]") !== null, null, {
    timeout: 20000,
  });
  assert.equal(await page.locator("#renderer-role").inputValue(), "baseline");
  assert.equal(await hashParam(page, "role"), null, "saved renderer choice lives in the database, not the URL");
});

test("font metadata names its actual kerning sources", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  await openVariantByName(page, (await cardNames(page))[0]!);
  const metadata = await page.locator(".font-metadata").innerText();
  assert.match(metadata, /Source kerning available \([^)]+\)/, `names actual sources, got: ${metadata}`);
});

test("preview font switching renders the newly selected font", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const names = await cardNames(page);
  const ids = await cardIds(page);
  await bootDetail(page, `${url}#/font/${ids[0]}/`);
  const before = await canvasPixels(page);
  const flex = names.find((name) => /^Roboto Flex/.test(name))!;
  const flexId = ids[names.findIndex((name) => name === flex)];
  await page.locator("#font-select").selectOption({ label: flex });
  await page.waitForFunction(
    (expected) => document.querySelector(".family h2")?.textContent === expected,
    flex,
  );
  await page.waitForFunction(canvasRendered);
  const after = await canvasPixels(page);
  assert.ok(after.ink > 100);
  assert.notDeepEqual([after.width, after.height], [0, 0]);
  assert.ok(
    after.width !== before.width || after.height !== before.height || after.ink !== before.ink,
    "switching fonts produces new output",
  );
  assert.equal(await hashParam(page, "v"), "1");
  assert.equal(await hashPath(page), `/font/${flexId}/`);
});

test("skip link focuses content without touching the route", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const before = page.url();
  await page.keyboard.press("Tab");
  assert.equal(await page.evaluate(() => document.activeElement?.hasAttribute("data-skip-link") ?? false), true);
  await page.keyboard.press("Enter");
  const focused = await page.evaluate(() => ({
    tag: document.activeElement?.tagName,
    id: document.activeElement?.id,
    hash: window.location.hash,
  }));
  assert.equal(focused.tag, "MAIN");
  assert.equal(focused.id, "main");
  assert.equal(page.url(), before, "skip navigation leaves the route untouched");
});
