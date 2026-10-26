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
  createPalettePreset,
  hashParam,
  hashPath,
  launch,
  openNewVariant,
  selectPalettePreset,
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

test("shared font size control supports presets, custom sizes and persistence across views", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await bootLibrary(page, url);
  const id = (await cardIds(page))[0]!;
  const input = page.getByRole("spinbutton", { name: "Size", exact: true });
  const slider = page.getByRole("slider", { name: "Size", exact: true });
  const stops = [8, 10, 12, 16, 24, 32, 48];
  assert.deepEqual(await page.locator("[data-size-stop]").allTextContents(), stops.map(String));
  await slider.focus();
  await slider.press("Home");
  for (const size of stops) {
    assert.equal(await input.inputValue(), String(size));
    assert.equal(await slider.getAttribute("aria-valuetext"), `${size} pixels`);
    await slider.press("ArrowRight");
  }
  await input.fill("20.5");
  await input.blur();
  assert.equal(await page.locator('[data-size-stop][aria-pressed="true"]').count(), 0);
  assert.equal(await slider.getAttribute("aria-valuetext"), "20.5 pixels");
  await slider.focus();
  await slider.press("ArrowRight");
  assert.equal(await input.inputValue(), "24");
  await input.fill("20.5");
  await slider.focus();
  await slider.press("ArrowLeft");
  assert.equal(await input.inputValue(), "16");
  // Drag to the far end through the actual pointer interaction.
  const track = await page.locator('[data-slot="slider-track"]').boundingBox();
  assert.ok(track);
  await slider.hover();
  await page.mouse.down();
  await page.mouse.move(track.x + track.width, track.y + track.height / 2, { steps: 10 });
  await page.mouse.up();
  assert.equal(await input.inputValue(), "48");
  await input.fill("");
  assert.equal(await input.inputValue(), "", "clearing the input allows replacement without changing the size");
  await input.blur();
  assert.equal(await input.inputValue(), "48");
  await input.fill("999");
  await input.blur();
  assert.equal(await input.inputValue(), "512");
  await input.fill("0");
  await input.blur();
  assert.equal(await input.inputValue(), "1");
  await input.fill("20.5");
  await input.blur();
  await page.reload({ waitUntil: "networkidle" });
  await input.waitFor();
  assert.equal(await input.inputValue(), "20.5");
  await page.waitForFunction((fontId) => {
    const source = document.querySelector(`[data-source-preview="${fontId}"]`);
    const zoom = Number(document.querySelector("[data-preview-zoom]")?.getAttribute("data-value"));
    return source && parseFloat(getComputedStyle(source).fontSize) === 20.5 * zoom;
  }, id);

  await openNewVariant(page, id);
  await page.waitForFunction(canvasRendered);
  await input.fill("18.5");
  await input.blur();
  await page.waitForFunction(() => document.querySelector("[data-save-status]")?.textContent === "Saved");
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(canvasRendered);
  assert.equal(await input.inputValue(), "18.5");
  await slider.press("ArrowRight");
  assert.equal(await input.inputValue(), "24");

  await bootDetail(page, `${url}#/font/${id}/`);
  await input.fill("22.5");
  await input.blur();
  await page.waitForFunction(() => window.location.search.includes("22.5"));
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(canvasRendered);
  assert.equal(await input.inputValue(), "22.5");
  assert.deepEqual(errors, []);
});

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

function isLight(color: string): boolean {
  const parsed = channels(color);
  if (!parsed) return false;
  const first = parsed.values[0] ?? NaN;
  return parsed.space === "rgb" ? first > 200 : first > 0.8;
}

test("controls resolve to visible theme colors", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, colorScheme: "light" });
  await bootLibrary(page, url);
  await openVariantByName(page, (await cardNames(page))[0]!);
  const reset = page.getByRole("button", { name: "Reset specimen", exact: true });
  assert.equal(await reset.isDisabled(), true, "a fresh variant inherits its specimen, so reset starts disabled");
  assert.equal(
    await reset.evaluate((element) => getComputedStyle(element).backgroundColor),
    "rgba(0, 0, 0, 0)",
    "disabled reset stays transparent by design",
  );
  await page.locator("[data-text]").fill("Custom contrast probe");
  assert.equal(await reset.isDisabled(), false, "editing the specimen enables reset");
  await page.waitForFunction(() => {
    const style = getComputedStyle(document.querySelector("[data-reset]")!);
    return style.opacity === "1" && style.backgroundColor !== "rgba(0, 0, 0, 0)";
  });
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
  for (const [name, style] of Object.entries({ reset: styles.reset, panel: styles.panel })) {
    assert.notEqual(style.background, "rgba(0, 0, 0, 0)", `${name} has a resolved background`);
    assert.notEqual(style.background, "transparent", `${name} has a resolved background`);
  }
  assert.ok(isLight(styles.reset.background), `reset background is light neutral, got ${styles.reset.background}`);
  assert.notEqual(styles.reset.color, styles.reset.background, "reset text contrasts its neutral fill");
  assert.notEqual(styles.remove.color, styles.panel.background, "delete icon contrasts with the specimen paper");
  const sizeBorder = channels(styles.size.border);
  assert.ok(sizeBorder && !(sizeBorder.values[0] === 0 && sizeBorder.values[1] === 0 && sizeBorder.values[2] === 0), "text input shows a border");
});

test("palette selection and keyboard focus are visible", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, colorScheme: "light" });
  await bootLibrary(page, url);
  await openVariantByName(page, (await cardNames(page))[0]!);
  const fixedPalette = page.getByRole("group", { name: "Palette", exact: true });
  assert.equal(await fixedPalette.locator("[data-palette-name]").textContent(), "Monochrome");
  assert.match(await fixedPalette.innerText(), /1-bit · 2 levels/);
  assert.equal(await page.getByRole("combobox", { name: "Palette", exact: true }).count(), 0);
  assert.equal(await fixedPalette.locator("svg").count(), 0, "fixed content has no dropdown arrow");
  for (const theme of ["light", "dark"]) {
    await page.evaluate((value) => document.documentElement.classList.toggle("dark", value === "dark"), theme);
    const display = await fixedPalette.evaluate((element) => {
      const style = getComputedStyle(element);
      let opacity = 1;
      for (let node: Element | null = element; node; node = node.parentElement) opacity *= Number(getComputedStyle(node).opacity);
      return { opacity, border: style.borderWidth, shadow: style.boxShadow, background: style.backgroundColor,
        tabIndex: (element as HTMLElement).tabIndex,
        swatches: [...element.querySelectorAll(".palette-choice-swatches > span")].map((swatch) => getComputedStyle(swatch).backgroundColor) };
    });
    assert.deepEqual(display, { opacity: 1, border: "0px", shadow: "none", background: "rgba(0, 0, 0, 0)",
      tabIndex: -1, swatches: ["rgb(255, 255, 255)", "rgb(0, 0, 0)"] }, `${theme} fixed palette preserves swatches without control styling`);
  }
  const variantUrl = page.url();
  await createPalettePreset(page, url, { name: "Grayscale", bits: 2 });
  await page.goto(variantUrl, { waitUntil: "networkidle" });
  await page.waitForFunction(canvasRendered);
  const palette = page.getByRole("combobox", { name: "Palette", exact: true });
  assert.equal(await palette.isEnabled(), true, "adding a palette enables selection");
  await palette.click();
  const checked = page.locator('[role="option"][data-state="checked"]');
  assert.equal(await checked.count(), 1, "one preset reads as selected");
  assert.equal(await checked.locator("[data-palette-name]").textContent(), "Monochrome");
  assert.notEqual(
    await checked.evaluate((element) => getComputedStyle(element).backgroundColor),
    "rgba(0, 0, 0, 0)",
    "the selected preset has a fill",
  );
  await page.keyboard.press("Escape");
  await page.locator("h1").click();
  for (let i = 0; i < 120; i += 1) {
    const focused = await page.evaluate(
      () => document.activeElement?.getAttribute("role") === "combobox"
        && document.activeElement.querySelector("[data-palette-name]")?.textContent === "Monochrome",
    );
    if (focused) break;
    await page.keyboard.press("Tab");
  }
  const ring = await page.evaluate(() => {
    const active = document.activeElement;
    if (!(active instanceof HTMLElement)) return null;
    const style = getComputedStyle(active);
    return [style.boxShadow, style.outlineStyle];
  });
  assert.ok(ring && (ring[0] !== "none" || ring[1] !== "none"), `keyboard focus shows a ring, got ${ring}`);
});

test("kerning toggles persist without listing source pairs", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  await openVariantByName(page, (await cardNames(page))[0]!);
  assert.equal(await page.locator(".font-kerning").count(), 0);
  await page.getByRole("switch", { name: "Kerning", exact: true }).uncheck();
  await page.waitForFunction(() => document.querySelector("[data-save-status]")?.textContent === "Saved");
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(canvasRendered);
  assert.equal(await page.getByRole("switch", { name: "Kerning", exact: true }).isChecked(), false);
});

async function openVariantByNameFromLibrary(page: Page, name: string): Promise<void> {
  await page.locator('[data-primary-nav="fonts"]').click();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  await openVariantByName(page, name);
}

test("palette preset persists in the variant across reloads, not in the URL", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  await openVariantByName(page, (await cardNames(page))[0]!);
  assert.equal(await page.locator("#rasterization").count(), 0);
  assert.equal(await page.getByRole("group", { name: "Palette", exact: true }).count(), 1);
  const editorUrl = page.url();
  await createPalettePreset(page, url, { name: "Output gray", bits: 3 });
  await page.goto(editorUrl, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelector("[data-variant-name]") !== null, null, {
    timeout: 20000,
  });
  await selectPalettePreset(page, "Output gray");
  await page.waitForFunction(
    () => document.querySelector("[data-save-status]")?.textContent?.startsWith("Saved"),
    null,
    { timeout: 20000 },
  );
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelector("[data-variant-name]") !== null, null, {
    timeout: 20000,
  });
  assert.equal(await page.locator("[data-output-palette] [data-palette-name]").textContent(), "Output gray");
  assert.equal(await hashParam(page, "palette"), null, "saved palette reference lives in the database, not the URL");
});

test("font metadata shows kerning availability", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const id = (await cardIds(page))[0]!;
  const metadata = page.locator(`[data-font-info="${id}"]`);
  assert.match(await metadata.innerText(), /Kerning\s*YES/i);
  assert.equal(await metadata.getByRole("tooltip").count(), 0);
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
  await page.getByRole("combobox", { name: "Font", exact: true }).click();
  await page.getByRole("option", { name: flex, exact: true }).click();
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

test("specimen dropdown and fitting switches preserve edits, keyboard selection and profile state", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await bootLibrary(page, url);
  await openVariantByName(page, (await cardNames(page))[0]!);

  const preset = page.getByRole("combobox", { name: "Preset", exact: true });
  const text = page.locator("textarea[data-text]");
  await preset.focus();
  await preset.press("Space");
  await page.waitForFunction(() => document.activeElement?.getAttribute("role") === "option");
  assert.equal(await page.getByRole("option", { name: "Custom", exact: true }).count(), 0);
  await page.keyboard.press("End");
  await page.waitForFunction(() => document.activeElement?.textContent === "Alphabet");
  await page.keyboard.press("Enter");
  assert.equal(await preset.evaluate((element) => element === document.activeElement), true);
  assert.equal(await text.inputValue(), "ABCDEFGHIJKLMNOPQRSTUVWXYZ\nabcdefghijklmnopqrstuvwxyz\n0123456789");
  await text.fill("My custom specimen");
  assert.equal(await preset.textContent(), "Custom");
  await preset.click();
  assert.equal(await page.getByRole("option", { name: "Custom", exact: true }).count(), 0);
  await page.getByRole("option", { name: "Pangram", exact: true }).click();
  assert.equal(await preset.textContent(), "Pangram");
  await text.fill("My custom specimen");

  assert.equal(await page.getByRole("combobox", { name: "Fitting", exact: true }).count(), 0, "fitting uses switches, without a combobox");
  const hints = page.getByRole("switch", { name: "Use font hints", exact: true });
  const diagonals = page.getByRole("switch", { name: "Fit diagonal strokes", exact: true });
  assert.equal(await hints.count(), 1, "the hinted mono font offers the hints switch");
  assert.equal(await diagonals.count(), 1, "the mono font offers the diagonal switch");
  assert.equal(await hints.isChecked(), true);
  assert.equal(await diagonals.isChecked(), true, "diagonals default on for new previews");
  await hints.focus();
  await page.keyboard.press("Space");
  await page.waitForFunction(() => document.querySelector("#use-font-hints")?.getAttribute("aria-checked") === "false");
  assert.equal(await hints.isChecked(), false, "space toggles the hints switch");
  await diagonals.click();
  await page.waitForFunction(() => document.querySelector("#fit-diagonal-strokes")?.getAttribute("aria-checked") === "false");
  assert.equal(await diagonals.isChecked(), false, "explicit off stays off");
  const editorUrl = page.url();
  await createPalettePreset(page, url, { name: "Fitting gray", bits: 3 });
  await page.goto(editorUrl, { waitUntil: "networkidle" });
  await page.waitForFunction(canvasRendered, null, { timeout: 20000 });
  await selectPalettePreset(page, "Fitting gray");
  assert.equal(await hints.count(), 0, "grayscale fitting hides the hints switch");
  assert.equal(await diagonals.count(), 0, "grayscale fitting hides the diagonal switch");
  await selectPalettePreset(page, "Monochrome");
  await hints.waitFor();
  assert.equal(await hints.isChecked(), false, "Mono retains its hints choice across profile changes");
  assert.equal(await diagonals.isChecked(), false, "Mono retains its diagonal choice across profile changes");
  assert.equal(await page.locator("select:visible").count(), 0, "all app dropdowns use custom triggers");
  await page.waitForFunction(() => document.querySelector("[data-save-status]")?.textContent === "Saved");
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(canvasRendered);
  assert.equal(await page.getByRole("switch", { name: "Use font hints", exact: true }).isChecked(), false);
  assert.equal(await page.getByRole("switch", { name: "Fit diagonal strokes", exact: true }).isChecked(), false);
  assert.equal(await text.inputValue(), "My custom specimen");
  assert.deepEqual(errors, []);
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
