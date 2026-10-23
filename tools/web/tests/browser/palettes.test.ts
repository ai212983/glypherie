import assert from "node:assert/strict";
import test from "node:test";
import type { Page } from "playwright-core";
import {
  bootLibrary,
  browserAvailable,
  buildApp,
  canvasRendered,
  cardIds,
  createPalettePreset,
  hashParam,
  hashPath,
  launch,
  openNewVariant,
  selectPalettePreset,
  servePrefix,
  setZoom,
} from "../helpers/spa-helpers.ts";

async function grayscaleReady(page: Parameters<typeof hashPath>[0]): Promise<void> {
  await page.waitForFunction(
    () => document.querySelector('main section[aria-label="Grayscale preview"]') !== null,
  );
}

async function presetCanvasRendered(page: Page, id: number): Promise<void> {
  await page.waitForFunction((rowId) => {
    const canvas = document.querySelector(`[data-preset-row="${rowId}"] canvas`);
    return canvas instanceof HTMLCanvasElement && canvas.dataset.rendered === "true";
  }, id);
}

async function presetRatio(page: Page, id: number): Promise<number> {
  return page.evaluate((rowId) => {
    const canvas = document.querySelector(`[data-preset-row="${rowId}"] canvas`);
    if (!(canvas instanceof HTMLCanvasElement) || canvas.width === 0) throw new Error("preset canvas is missing");
    return parseFloat(canvas.style.width) / canvas.width;
  }, id);
}

async function presetPixel(page: Page, id: number, x: number, y: number): Promise<[number, number, number]> {
  return page.evaluate(([rowId, px, py]) => {
    const canvas = document.querySelector(`[data-preset-row="${rowId}"] canvas`);
    if (!(canvas instanceof HTMLCanvasElement)) throw new Error("preset canvas is missing");
    const context = canvas.getContext("2d");
    if (!context) throw new Error("canvas 2d is unavailable");
    const [r, g, b] = context.getImageData(px, py, 1, 1).data;
    return [r ?? -1, g ?? -1, b ?? -1];
  }, [id, x, y] as const);
}

async function framePaper(page: Page): Promise<string> {
  return page.locator("[data-preset-frame]").evaluate((frame) => (frame as HTMLElement).style.backgroundColor);
}

async function mainRatio(page: Page): Promise<number> {
  return page.evaluate(() => {
    const canvas = document.querySelector('main section[aria-label="Grayscale preview"] canvas');
    if (!(canvas instanceof HTMLCanvasElement) || canvas.width === 0) throw new Error("main canvas is missing");
    return parseFloat(canvas.style.width) / canvas.width;
  });
}

async function mainPixel(page: Page, x: number, y: number): Promise<[number, number, number]> {
  return page.evaluate(([px, py]) => {
    const canvas = document.querySelector('main section[aria-label="Grayscale preview"] canvas');
    if (!(canvas instanceof HTMLCanvasElement)) throw new Error("main canvas is missing");
    const context = canvas.getContext("2d");
    if (!context) throw new Error("canvas 2d is unavailable");
    const [r, g, b] = context.getImageData(px, py, 1, 1).data;
    return [r ?? -1, g ?? -1, b ?? -1];
  }, [x, y] as const);
}

async function presetViewport(page: Page, id: number): Promise<string> {
  return page.evaluate((rowId) => {
    const canvas = document.querySelector(`[data-preset-row="${rowId}"] canvas`);
    const viewport = canvas?.parentElement;
    if (!(viewport instanceof HTMLElement)) throw new Error("preset viewport is missing");
    return viewport.style.backgroundColor;
  }, id);
}

async function presetBackingHeight(page: Page, id: number): Promise<number> {
  return page.evaluate((rowId) => {
    const canvas = document.querySelector(`[data-preset-row="${rowId}"] canvas`);
    if (!(canvas instanceof HTMLCanvasElement)) throw new Error("preset canvas is missing");
    return canvas.height;
  }, id);
}

async function presetBottomInk(page: Page, id: number, paper: number): Promise<boolean> {
  return page.evaluate(([rowId, paperValue]) => {
    const canvas = document.querySelector(`[data-preset-row="${rowId}"] canvas`);
    if (!(canvas instanceof HTMLCanvasElement) || canvas.height < 2) throw new Error("preset canvas is missing");
    const context = canvas.getContext("2d");
    if (!context) throw new Error("canvas 2d is unavailable");
    for (const y of [canvas.height - 1, canvas.height - 2]) {
      const data = context.getImageData(0, y, canvas.width, 1).data;
      for (let offset = 0; offset < data.length; offset += 4) {
        if ((data[offset] ?? paperValue) !== paperValue) return true;
      }
    }
    return false;
  }, [id, paper] as const);
}

async function presetInk(page: Page, id: number): Promise<number[]> {
  return page.evaluate((rowId) => {
    const canvas = document.querySelector(`[data-preset-row="${rowId}"] canvas`);
    if (!(canvas instanceof HTMLCanvasElement)) throw new Error("preset canvas is missing");
    const context = canvas.getContext("2d");
    if (!context) throw new Error("canvas 2d is unavailable");
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    const values = new Set<number>();
    for (let offset = 0; offset < data.length; offset += 4) {
      const channel = data[offset];
      if (channel !== undefined) values.add(channel);
    }
    return [...values];
  }, id);
}

test("primary nav switches between fonts and palettes with active state", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);

  const fontsNav = page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Fonts" });
  const palettesNav = page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Palettes" });
  assert.equal(await fontsNav.getAttribute("aria-current"), "page");
  assert.equal(await palettesNav.getAttribute("aria-current"), null);
  assert.equal(await page.locator("[data-global-zoom]").count(), 1, "font pages keep global display controls");
  assert.equal(await page.locator("[data-library-filter]").count(), 1, "font library shows the filter");

  await palettesNav.click();
  await grayscaleReady(page);
  assert.equal(await hashPath(page), "/palettes/");
  assert.equal(await palettesNav.getAttribute("aria-current"), "page");
  assert.equal(await fontsNav.getAttribute("aria-current"), null);
  assert.equal(await page.getByRole("group", { name: "Preview zoom" }).count(), 0, "local zoom removed in favor of global zoom");
  assert.equal(await page.locator("[data-global-zoom]").count(), 1, "palettes shares the global display controls");
  assert.equal(await page.locator("[data-theme-toggle]").count(), 1, "theme control stays on palettes");
  assert.equal(await page.locator("[data-library-filter]").count(), 0, "font filter stays off palettes");

  const order = await page.evaluate(() => {
    const headings = [...document.querySelectorAll("main h2")].map((heading) => heading.textContent);
    return headings;
  });
  assert.equal(order.filter((heading) => heading === "Preview").length, 1);
  assert.equal(order.includes("Sample text"), false);
  assert.ok(order.indexOf("Preview") < order.indexOf("Bit-depth & gray levels"));
  const preview = page.getByRole("group", { name: "Preview", exact: true });
  assert.equal(await preview.locator("canvas").count(), 1);
  assert.equal(await preview.getByRole("textbox", { name: "Sample text", exact: true }).count(), 1);
  assert.equal(await preview.getByRole("combobox", { name: "Preset", exact: true }).count(), 1);
  const titleStyle = (element: HTMLElement): string[] => {
    const style = getComputedStyle(element);
    return [style.fontFamily, style.fontSize, style.fontWeight, style.lineHeight, style.letterSpacing, style.color, style.textTransform];
  };
  const previewStyle = await page.getByRole("heading", { name: "Preview", exact: true }).evaluate(titleStyle);
  assert.equal(previewStyle[1], "10px");
  assert.deepEqual(previewStyle, await page.getByRole("heading", { name: "Presets", exact: true }).evaluate(titleStyle));
  assert.equal(order.includes("Preset parameters"), false);

  await page.goBack();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  assert.equal(await hashPath(page), "/");
  assert.equal(await fontsNav.getAttribute("aria-current"), "page");

  await page.goForward();
  await grayscaleReady(page);
  assert.equal(await hashPath(page), "/palettes/");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: "networkidle" });
  await grayscaleReady(page);
  assert.ok(await fontsNav.isVisible(), "fonts nav stays usable at mobile width");
  assert.ok(await palettesNav.isVisible(), "palettes nav stays usable at mobile width");
  await page.getByRole("link", { name: "Glypherie", exact: true }).click();
  await page.locator("[data-font-card]").first().waitFor();
  assert.equal(await hashPath(page), "/", "brand link returns to the library from palettes");
});

test("palettes loads directly and drops stale font snapshot params", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(`${url}#/palettes/`, { waitUntil: "networkidle" });
  await grayscaleReady(page);
  assert.equal(await hashPath(page), "/palettes/");

  await page.goto(`${url}#/palettes/?v=1&font=abc&utm=keep`, { waitUntil: "networkidle" });
  await grayscaleReady(page);
  assert.equal(await hashPath(page), "/palettes/");
  assert.equal(await hashParam(page, "v"), null);
  assert.equal(await hashParam(page, "font"), null);
  assert.equal(await hashParam(page, "utm"), "keep");
});

test("preset specimen rows select, edit, and stay local-only", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(`${url}#/palettes/`, { waitUntil: "networkidle" });
  await grayscaleReady(page);

  assert.ok(await page.getByRole("heading", { name: "Presets" }).isVisible(), "preset card carries its title");
  assert.equal(await page.getByLabel("Selected preset").count(), 0, "dropdown selector is gone");
  const sidebar = page.getByRole("complementary", { name: "Grayscale presets" });
  const main = page.getByRole("region", { name: "Grayscale preview" });
  assert.equal(await sidebar.getByRole("textbox", { name: "Sample text", exact: true }).count(), 1, "shared preset sample text lives in the left panel");
  assert.equal(await sidebar.locator("input, textarea, select, [role=slider], [role=combobox]").count(), 1, "sample text is the only editor in the left panel");
  assert.equal(await main.getByRole("textbox", { name: "Sample text", exact: true }).count(), 1, "main specimen keeps its independent sample text");
  const group = page.getByRole("group", { name: "Presets" });
  const mono = group.getByRole("button", { name: /Monochrome/ });
  assert.equal(await mono.getAttribute("aria-pressed"), "true");
  assert.equal(await page.locator('[data-preset-caption="0"]').textContent(), "16 px / 1-bit · 2 levels");
  assert.equal(await page.locator('[data-preset-row="0"] button').count(), 0, "rows carry no nested controls");
  await presetCanvasRendered(page, 0);
  assert.ok((await presetInk(page, 0)).every((value) => value === 0 || value === 255), "mono specimen uses its palette");
  const geometry = await page.evaluate(() => {
    const row = document.querySelector('[data-preset-row="0"]');
    const parent = row?.parentElement;
    if (!(row instanceof HTMLElement) || !(parent instanceof HTMLElement)) throw new Error("preset row is missing");
    return { row: row.getBoundingClientRect().width, parent: parent.getBoundingClientRect().width };
  });
  assert.ok(geometry.row >= geometry.parent, `button fills its row (${geometry.row} vs ${geometry.parent})`);

  await page.getByRole("button", { name: "Add preset" }).click();
  await page.waitForFunction(() => document.querySelector('[data-preset-row="1"]') !== null, null, { timeout: 20000 });
  const custom = group.locator('[data-preset-row="1"]');
  assert.equal(await custom.getAttribute("aria-pressed"), "true", "new presets select immediately");
  assert.equal(await mono.getAttribute("aria-pressed"), "false");
  assert.equal(await page.locator('[data-preset-caption="1"]').textContent(), "16 px / 2-bit · 4 levels");
  await presetCanvasRendered(page, 1);
  assert.deepEqual(
    (await presetInk(page, 1)).sort((a, b) => a - b),
    [0, 85, 170, 255],
    "custom specimen uses its levels",
  );

  const parameters = main.getByRole("group", { name: "Name", exact: true });
  const response = main.getByRole("group", { name: "Bit-depth & gray levels", exact: true });
  assert.equal(await parameters.getByLabel("Name", { exact: true }).count(), 1);
  assert.equal(await parameters.getByRole("spinbutton", { name: "Levels", exact: true }).count(), 0);
  assert.equal(await main.getByRole("spinbutton", { name: "Levels", exact: true }).count(), 0);
  assert.equal(await main.getByRole("radiogroup", { name: "Quantization depth", exact: true }).count(), 1);
  const specimen = main.getByRole("group", { name: "Preview", exact: true });
  assert.equal(await parameters.locator("label").count(), 1, "preset name has only its header label");
  assert.equal(await specimen.locator("canvas").count(), 1, "sample controls and rendered preview share a panel");
  assert.equal(await specimen.getByRole("combobox", { name: "Preset", exact: true }).count(), 1);
  assert.equal(await specimen.getByRole("textbox", { name: "Sample text", exact: true }).count(), 1);
  const presetLabel = await specimen.locator("label").filter({ hasText: /^Preset$/ }).boundingBox();
  const presetSelect = await specimen.getByRole("combobox", { name: "Preset", exact: true }).boundingBox();
  assert.ok(presetLabel && presetSelect && presetSelect.x > presetLabel.x && Math.abs((presetLabel.y + presetLabel.height / 2) - (presetSelect.y + presetSelect.height / 2)) < 1, "Preset label and dropdown share a row");
  assert.equal(await specimen.getByRole("combobox").count(), 2, "preview contains the text preset and font selectors");
  const fieldStyle = (element: HTMLElement): string[] => {
    const field = getComputedStyle(element.parentElement!);
    const input = getComputedStyle(element);
    return [field.borderColor, field.borderRadius, field.backgroundColor, field.padding, field.boxShadow, input.fontFamily, input.fontSize, input.lineHeight, input.padding, input.backgroundColor];
  };
  assert.deepEqual(await specimen.getByRole("textbox", { name: "Sample text", exact: true }).evaluate(fieldStyle), await sidebar.getByRole("textbox", { name: "Sample text", exact: true }).evaluate(fieldStyle), "sample text fields share styling");
  const swatches = response.getByRole("group", { name: "Gray level swatches", exact: true });
  assert.equal(await swatches.getByRole("heading").count(), 0);
  const preview = main.getByRole("group", { name: "Preview", exact: true });
  assert.equal(await main.getByRole("group", { name: "Gray level swatches", exact: true }).count(), 1, "only one ramp remains");
  assert.equal(await preview.locator("canvas").count(), 1, "rendered specimen lives in Preview");
  assert.equal(await preview.evaluate((element) => element.matches('[data-slot="card"]')), true, "preview and controls share the specimen panel");
  assert.equal(await preview.getByRole("group", { name: "Gray level swatches", exact: true }).count(), 0);
  assert.equal(await response.locator("canvas").count(), 0, "palette panel contains no preview");
  assert.equal(await response.getByRole("group", { name: "Gray response graph", exact: true }).count(), 1, "graph and selector share a panel");
  await swatches.getByRole("button", { name: "Select level 1", exact: true }).click();
  const grayValue = response.getByRole("spinbutton", { name: "Gray value", exact: true });
  assert.equal(await grayValue.inputValue(), "170", "swatch selection opens the corresponding gray editor");
  await grayValue.fill("150");
  await page.waitForFunction(
    () => getComputedStyle(document.querySelector('[aria-label="Select level 1"]')!).backgroundColor === "rgb(150, 150, 150)",
    null,
    { timeout: 20000 },
  );
  assert.equal(await swatches.getByRole("button", { name: "Select level 1", exact: true }).evaluate((element) => getComputedStyle(element).backgroundColor), "rgb(150, 150, 150)", "edited gray updates its palette swatch");
  await swatches.getByRole("button", { name: "Select level 2", exact: true }).focus();
  await page.keyboard.press("Space");
  await page.waitForFunction(
    () => {
      const label = [...document.querySelectorAll("label")].find((entry) => entry.textContent === "Gray value");
      const input = label ? document.getElementById(label.htmlFor) : null;
      return input instanceof HTMLInputElement && input.value === "66";
    },
    null,
    { timeout: 20000 },
  );
  assert.equal(await grayValue.inputValue(), "66", "keyboard selection shows the neighboring level shaped by the sparse curve");
  const remove = sidebar.getByRole("button", { name: "Delete preset Grayscale 1", exact: true });
  assert.equal(await remove.locator("svg").count(), 1, "preset row uses a delete icon");
  assert.equal(await custom.locator("button").count(), 0, "delete stays separate from selection");
  const deleteGeometry = await remove.boundingBox();
  const captionGeometry = await page.locator('[data-preset-caption="1"]').boundingBox();
  assert.ok(deleteGeometry && captionGeometry && captionGeometry.x + captionGeometry.width <= deleteGeometry.x, "caption leaves room for the delete icon");
  await main.getByRole("textbox", { name: "Name", exact: true }).fill("Soft proof");
  await page.waitForFunction(
    () => document.querySelector('[data-preset-row="1"]')?.getAttribute("aria-label")?.startsWith("Soft proof,") === true,
    null,
    { timeout: 20000 },
  );
  assert.equal(await group.getByRole("button", { name: /^Soft proof,/ }).getAttribute("aria-pressed"), "true");

  await mono.click();
  assert.equal(await mono.getAttribute("aria-pressed"), "true");
  const renamed = group.getByRole("button", { name: /^Soft proof,/ });
  await renamed.click();
  assert.equal(await renamed.getAttribute("aria-pressed"), "true");
  await mono.focus();
  await page.keyboard.press(" ");
  assert.equal(await mono.getAttribute("aria-pressed"), "true", "keyboard activates the pressed state");
  assert.equal(await renamed.getAttribute("aria-pressed"), "false");
  await renamed.click();

  await response.getByRole("radio", { name: "3-bit · 8 levels", exact: true }).click();
  await page.waitForFunction(
    () => document.querySelector('[data-preset-caption="1"]')?.textContent === "16 px / 3-bit · 8 levels",
    null,
    { timeout: 20000 },
  );
  assert.equal(await page.locator('[data-preset-caption="1"]').textContent(), "16 px / 3-bit · 8 levels");
  await presetCanvasRendered(page, 1);
  const updated = await presetInk(page, 1);
  assert.ok(updated.every((value) => Number.isInteger(value) && value >= 0 && value <= 255));
  assert.ok(updated.some((value) => ![0, 85, 170, 255].includes(value)), "raster follows the new count");

  await response.getByRole("radio", { name: "4-bit · 16 levels", exact: true }).click();
  await page.waitForFunction(
    () => document.querySelector('[data-preset-caption="1"]')?.textContent === "16 px / 4-bit · 16 levels",
    null,
    { timeout: 20000 },
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await swatches.getByRole("button", { name: "Select level 15", exact: true }).focus();
  await page.keyboard.press("Space");
  assert.equal(await grayValue.inputValue(), "0", "last swatch remains reachable at mobile width");
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, "palette controls do not widen the page");
  await page.setViewportSize({ width: 1280, height: 900 });

  await group.getByRole("button", { name: "Delete preset Soft proof", exact: true }).click();
  await page.waitForFunction(() => document.querySelectorAll("[data-preset-row]").length === 1, null, { timeout: 20000 });
  assert.equal(await group.locator("[data-preset-row]").count(), 1);
  assert.equal(await mono.getAttribute("aria-pressed"), "true");

  await page.getByRole("button", { name: "Add preset" }).click();
  await page.waitForFunction(() => document.querySelectorAll("[data-preset-row]").length === 2, null, { timeout: 20000 });
  assert.equal(await group.locator("[data-preset-row]").count(), 2, "second custom preset rows render before reload");
  await main.getByRole("textbox", { name: "Name", exact: true }).fill("Keep this preset");
  await page.waitForFunction(
    () => [...document.querySelectorAll("[data-preset-row]")].some((row) => row.getAttribute("aria-label")?.startsWith("Keep this preset,") === true),
    null,
    { timeout: 20000 },
  );
  await page.getByRole("button", { name: "Add preset" }).click();
  await page.waitForFunction(() => document.querySelectorAll("[data-preset-row]").length === 3, null, { timeout: 20000 });
  await main.getByRole("textbox", { name: "Name", exact: true }).fill("Remove this preset");
  await page.waitForFunction(
    () => [...document.querySelectorAll("[data-preset-row]")].some((row) => row.getAttribute("aria-label")?.startsWith("Remove this preset,") === true),
    null,
    { timeout: 20000 },
  );
  await group.locator('[data-preset-row="2"]').click();
  await group.getByRole("button", { name: "Delete preset Remove this preset", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelectorAll("[data-preset-row]").length === 2, null, { timeout: 20000 });
  await page.waitForFunction(
    () => (document.querySelector('main input[id$="-name"]') as HTMLInputElement | null)?.value === "Keep this preset",
    null,
    { timeout: 20000 },
  );
  assert.equal(await main.getByRole("textbox", { name: "Name", exact: true }).inputValue(), "Keep this preset", "deleting another row preserves the active preset");
  assert.equal(await group.locator("[data-preset-row]").count(), 2);

  await page.reload({ waitUntil: "networkidle" });
  await grayscaleReady(page);
  const reloaded = page.getByRole("group", { name: "Presets" });
  await page.waitForFunction(() => document.querySelectorAll("[data-preset-row]").length === 2, null, { timeout: 20000 });
  assert.equal(await reloaded.locator("[data-preset-row]").count(), 2, "presets persist across reload");
  assert.ok(await reloaded.locator('[data-preset-row][aria-label^="Keep this preset,"]').isVisible());
  assert.equal(await reloaded.getByRole("button", { name: /Monochrome/ }).getAttribute("aria-pressed"), "true");
});

async function waitEditor(page: Page): Promise<void> {
  await page.waitForFunction(() => document.querySelector("[data-variant-name]") !== null, null, {
    timeout: 20000,
  });
  await page.waitForFunction(canvasRendered, null, { timeout: 20000 });
}

async function waitSaved(page: Page): Promise<void> {
  await page.waitForFunction(
    () => document.querySelector("[data-save-status]")?.textContent?.startsWith("Saved"),
    null,
    { timeout: 20000 },
  );
}

interface VariantRowState {
  revision: number;
  inheritSampleText: boolean;
  paletteId: number;
  profile: string;
}

async function variantRow(page: Page, id: string): Promise<VariantRowState> {
  return page.evaluate(async (variantId): Promise<VariantRowState> => {
    const open = indexedDB.open("font-library");
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      open.onsuccess = () => resolve(open.result);
      open.onerror = () => reject(open.error);
    });
    try {
      const row = await new Promise<{
        revision: number;
        inheritSampleText: boolean;
        settings: { paletteId: number; profile: string };
      }>((resolve, reject) => {
        const fetched = db.transaction("variants", "readonly").objectStore("variants").get(variantId);
        fetched.onsuccess = () => resolve(fetched.result);
        fetched.onerror = () => reject(fetched.error);
      });
      return {
        revision: row.revision,
        inheritSampleText: row.inheritSampleText,
        paletteId: row.settings.paletteId,
        profile: row.settings.profile,
      };
    } finally {
      db.close();
    }
  }, id);
}

test("palette depth edits settle variant autosave without revision drift", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const editor = await context.newPage();
  await bootLibrary(editor, url);
  const fontId = (await cardIds(editor))[0]!;
  const variantId = await openNewVariant(editor, fontId);
  await waitEditor(editor);
  await waitSaved(editor);

  const lab = await context.newPage();
  const { rowId } = await createPalettePreset(lab, url, { name: "Live gray", bits: 2 });
  await selectPalettePreset(editor, "Live gray");
  await waitSaved(editor);
  const picker = editor.getByRole("combobox", { name: "Palette", exact: true });
  assert.match(await picker.innerText(), /2-bit · 4 levels/);
  assert.equal(await picker.locator(".palette-choice-swatches > span").count(), 4);
  await picker.focus();
  await editor.keyboard.press("ArrowDown");
  const option = editor.getByRole("option", { name: "Live gray 2-bit · 4 levels", exact: true });
  assert.ok(await option.isVisible(), "dropdown options expose name, depth and levels");
  assert.deepEqual(await option.locator(".palette-choice-swatches > span").evaluateAll((swatches) =>
    swatches.map((swatch) => getComputedStyle(swatch).backgroundColor)),
  ["rgb(255, 255, 255)", "rgb(170, 170, 170)", "rgb(85, 85, 85)", "rgb(0, 0, 0)"]);
  await editor.waitForFunction(
    () => document.activeElement?.getAttribute("role") === "option",
    null,
    { timeout: 20000 },
  );
  await editor.keyboard.press("Home");
  await editor.waitForFunction(
    () => (document.activeElement?.textContent ?? "").startsWith("Monochrome"),
    null,
    { timeout: 20000 },
  );
  await editor.keyboard.press("l");
  await editor.waitForFunction(
    () => (document.activeElement?.textContent ?? "").startsWith("Live gray"),
    null,
    { timeout: 20000 },
  );
  await editor.keyboard.press("Enter");
  assert.match(await picker.innerText(), /Live gray/, "palette names remain searchable by keyboard");
  assert.match(
    (await editor.locator("[data-variant-paper]").innerText()) ?? "",
    /2-bit/,
    "the editor paints the selected preset depth",
  );

  await lab.getByRole("radio", { name: "4-bit · 16 levels", exact: true }).click();
  await lab.waitForFunction(
    ([id, depth]) => document.querySelector(`[data-preset-caption="${id}"]`)?.textContent?.includes(depth) === true,
    [rowId, "4-bit · 16 levels"] as [number, string],
    { timeout: 20000 },
  );
  await editor.waitForFunction(
    () => document.querySelector("[data-variant-paper]")?.textContent?.includes("4-bit") === true,
    null,
    { timeout: 20000 },
  );
  assert.match(await picker.innerText(), /4-bit · 16 levels/);
  assert.equal(await picker.locator(".palette-choice-swatches > span").count(), 16);
  const settled = await variantRow(editor, variantId);

  await editor.locator("[data-text]").click();
  await editor.keyboard.press("ControlOrMeta+a");
  await editor.locator("[data-text]").pressSequentially("live depth probe");
  await waitSaved(editor);
  const after = await variantRow(editor, variantId);
  assert.equal(after.revision, settled.revision + 1, "one sample edit commits exactly one revision");
  assert.equal(after.inheritSampleText, false, "the explicit text override survives normalization");
  assert.equal(after.profile, "gray_4bit");

  await editor.reload({ waitUntil: "networkidle" });
  await waitEditor(editor);
  assert.equal(await editor.locator("[data-text]").inputValue(), "live depth probe");
  assert.equal(await editor.locator("[data-output-palette] [data-palette-name]").textContent(), "Live gray");
  assert.match((await editor.locator("[data-variant-paper]").innerText()) ?? "", /4-bit/);
  await waitSaved(editor);
  assert.equal(await editor.locator("[data-variant-error]").count(), 0, "no save error is shown");
  const tones = await editor.evaluate(() => {
    const canvas = document.querySelector(".interactive-canvas") as HTMLCanvasElement | null;
    if (!canvas || canvas.width === 0) throw new Error("preview canvas is missing");
    const data = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data;
    const distinct = new Set<number>();
    let ink = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (data[i] !== 255 || data[i + 1] !== 255 || data[i + 2] !== 255) {
        ink += 1;
        if (data[i] !== data[i + 1] || data[i + 1] !== data[i + 2]) return { ink, distinct: [] as number[], tinted: true };
        distinct.add(data[i]!);
      }
    }
    return { ink, distinct: [...distinct], tinted: false };
  });
  assert.ok(tones.ink > 0, "the 4-bit specimen paints");
  assert.equal(tones.tinted, false, "painted texels keep untinted gray tones");
  const levels = Array.from({ length: 16 }, (_, i) => Math.round(255 * (1 - i / 15)));
  assert.ok(tones.distinct.every((value) => levels.includes(value)), "painted texels use only the preset levels");
  await context.close();
});

test("palette deletion falls back another tab to Monochrome with a conflict", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const editor = await context.newPage();
  await bootLibrary(editor, url);
  const fontId = (await cardIds(editor))[0]!;
  const variantId = await openNewVariant(editor, fontId);
  await waitEditor(editor);
  await waitSaved(editor);

  const lab = await context.newPage();
  const { rowId } = await createPalettePreset(lab, url, { name: "Doomed gray", bits: 2 });
  await selectPalettePreset(editor, "Doomed gray");
  await waitSaved(editor);

  // Keep the editor typing so its draft stays dirty; the lab deletes the
  // selected preset mid-typing and the pending save then conflicts on its
  // stale revision instead of resurrecting the preset.
  const text = editor.locator("[data-text]");
  await text.click();
  await editor.keyboard.press("ControlOrMeta+a");
  const typing = text.pressSequentially("edit after delete", { delay: 40 });
  await editor.waitForFunction(
    () => document.querySelector("[data-save-status]")?.textContent?.startsWith("Saving"),
    null,
    { timeout: 20000 },
  );
  await lab.locator(`[data-delete-preset="${rowId}"]`).click();
  await lab.waitForFunction(
    (id) => document.querySelector(`[data-preset-row="${id}"]`) === null,
    rowId,
    { timeout: 20000 },
  );
  await editor.waitForFunction(
    () => document.querySelector("[data-output-palette] [data-palette-name]")?.textContent === "Monochrome",
    null,
    { timeout: 20000 },
  );
  await typing;
  await editor.waitForFunction(() => document.querySelector("[data-variant-error]") !== null, null, {
    timeout: 20000,
  });
  assert.equal(
    await editor.locator("[data-variant-error] h2").innerText(),
    "Another tab changed this variant.",
  );
  await editor.locator("[data-error-reload]").click();
  await editor.waitForFunction(
    () => (document.querySelector("[data-variant-name]") as HTMLInputElement | null) !== null,
    null,
    { timeout: 20000 },
  );
  assert.equal(await editor.locator("[data-output-palette] [data-palette-name]").textContent(), "Monochrome");
  const row = await variantRow(editor, variantId);
  assert.equal(row.paletteId, 0, "no stale write resurrects the removed preset");
  await waitSaved(editor);
  await editor.locator("[data-text]").pressSequentially("clean edit");
  await waitSaved(editor);
  const settled = await variantRow(editor, variantId);
  assert.equal(settled.revision, row.revision + 1, "the clean reloaded draft saves without conflict");
  assert.equal(settled.paletteId, 0);
  await context.close();
});

test("palettes renders while font bootstrap is still pending", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.route("**/*.ttf", () => new Promise(() => {}));
  await page.goto(`${url}#/palettes/`, { waitUntil: "domcontentloaded" });
  await grayscaleReady(page);
  assert.equal(await hashPath(page), "/palettes/");
  assert.equal(await page.locator("[data-font-card]").count(), 0, "no font cards while bootstrap hangs");
  assert.equal(
    await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Palettes" }).getAttribute("aria-current"),
    "page",
  );
});

test("empty-library history navigation leaves palettes for the index", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.route("**/*.ttf", (route) => route.abort());
  await page.goto(`${url}#/palettes/`, { waitUntil: "networkidle" });
  await grayscaleReady(page);
  assert.equal(await page.locator("[data-font-card]").count(), 0, "seed failure settles to an empty library");

  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Fonts" }).click();
  await page.waitForFunction(
    () => document.querySelector("main")?.textContent?.includes("No fonts") === true,
  );
  assert.equal(await hashPath(page), "/");
  assert.equal(await page.locator("main h1").count(), 0, "palettes unmounts on the index route");

  await page.goBack();
  await grayscaleReady(page);
  assert.equal(await hashPath(page), "/palettes/");
});

test("preset frame follows display settings with independent sample text", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  await page.locator('[data-size-stop="32"]').click();
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Palettes" }).click();
  await grayscaleReady(page);
  await presetCanvasRendered(page, 0);

  assert.equal(await page.locator("[data-preset-frame]").count(), 1, "presets share one frame");
  assert.equal(await page.locator("[data-preset-frame] [data-preset-row]").count(), 1);
  assert.equal(await page.locator('[data-preset-caption="0"]').textContent(), "32 px / 1-bit · 2 levels", "rows use the global base size");
  assert.equal(await framePaper(page), "rgb(255, 255, 255)");

  await setZoom(page, "4");
  await presetCanvasRendered(page, 0);
  assert.equal(await presetRatio(page, 0), 4, "rows render at the global zoom");
  assert.equal(await mainRatio(page), 4, "main preview shares the global zoom");

  await page.getByRole("combobox", { name: "Canvas preset" }).click();
  await page.getByRole("option", { name: "Warm", exact: true }).click();
  await page.waitForFunction(
    () => (document.querySelector("[data-preset-frame]") as HTMLElement | null)?.style.backgroundColor === "rgb(244, 236, 220)",
  );
  assert.deepEqual(await presetPixel(page, 0, 0, 0), [244, 236, 220], "paper pixel uses the warm paper");
  assert.deepEqual(await mainPixel(page, 0, 0), [244, 236, 220], "main preview shares the canvas palette");

  await page.locator("[data-canvas-inverse]").click();
  await page.waitForFunction(
    () => (document.querySelector("[data-preset-frame]") as HTMLElement | null)?.style.backgroundColor === "rgb(26, 24, 21)",
  );
  assert.deepEqual(await presetPixel(page, 0, 0, 0), [26, 24, 21], "inverse swaps the paper pixel");
  assert.equal(await page.locator('[data-preset-caption="0"]').textContent(), "32 px / 1-bit · 2 levels", "captions ignore display settings");

  const mainPreview = page.getByRole("img", { name: /Rasterized text preview/ });
  const mainBefore = await page.getByRole("region", { name: "Grayscale preview" }).getByRole("textbox", { name: "Sample text", exact: true }).inputValue();
  await page.getByRole("complementary", { name: "Grayscale presets" }).getByRole("textbox", { name: "Sample text", exact: true }).fill("Zz 99");
  assert.equal(await page.getByRole("region", { name: "Grayscale preview" }).getByRole("textbox", { name: "Sample text", exact: true }).inputValue(), mainBefore, "preset text leaves main text alone");
  assert.ok((await mainPreview.getAttribute("aria-label"))?.includes(mainBefore), "preset text leaves main preview alone");
  await page.getByRole("region", { name: "Grayscale preview" }).getByRole("textbox", { name: "Sample text", exact: true }).fill("Hello");
  assert.equal(await page.getByRole("complementary", { name: "Grayscale presets" }).getByRole("textbox", { name: "Sample text", exact: true }).inputValue(), "Zz 99", "main text leaves preset text alone");
  assert.ok((await mainPreview.getAttribute("aria-label"))?.includes("Hello"));

  await page.reload({ waitUntil: "networkidle" });
  await grayscaleReady(page);
  assert.equal(await page.getByRole("complementary", { name: "Grayscale presets" }).getByRole("textbox", { name: "Sample text", exact: true }).inputValue(), "Aa 0123", "preset text stays local-only");
  const reloaded = page.getByRole("group", { name: "Presets" });
  assert.equal(await reloaded.locator("[data-preset-row]").count(), 1);
});

test("preview font selector renders bundled fonts in the main preview and preset rows", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
  await page.goto(`${url}#/palettes/`, { waitUntil: "networkidle" });
  await grayscaleReady(page);
  await presetCanvasRendered(page, 0);
  const preview = page.getByRole("group", { name: "Preview", exact: true });
  const selector = preview.getByRole("combobox", { name: "Preview font", exact: true });
  assert.equal((await selector.textContent())?.trim(), "Roboto");
  assert.equal(await selector.evaluate((element) => document.querySelector('section[aria-label="Grayscale preview"] canvas')?.parentElement?.contains(element)), true, "font selector lives inside the colored canvas frame");
  const before = await page.evaluate(() => [...document.querySelectorAll("main canvas")].map((canvas) => (canvas as HTMLCanvasElement).toDataURL()));
  await selector.focus();
  await page.keyboard.press("Space");
  assert.equal(await page.getByRole("option").count(), 5, "selector reuses the five bundled fonts");
  await page.getByRole("option", { name: "Literata", exact: true }).focus();
  await page.keyboard.press("Enter");
  assert.equal((await selector.textContent())?.trim(), "Literata");
  await page.waitForFunction((previous) => [...document.querySelectorAll("main canvas")].every((canvas, index) => (canvas as HTMLCanvasElement).toDataURL() !== previous[index]), before);
  assert.equal(await page.getByRole("alert").count(), 0, "bundled fonts load without a fallback error");
  await selector.click();
  await page.getByRole("option", { name: "Roboto", exact: true }).click();
  await page.waitForFunction((previous) => [...document.querySelectorAll("main canvas")].every((canvas, index) => (canvas as HTMLCanvasElement).toDataURL() === previous[index]), before);
});

test("preset rows and main preview trim to painted ink", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(`${url}#/palettes/`, { waitUntil: "networkidle" });
  await grayscaleReady(page);
  await presetCanvasRendered(page, 0);
  const caps16 = await presetBackingHeight(page, 0);
  assert.ok(caps16 >= 4 && caps16 < 23, `16px caps row trims the full 23px line box (got ${caps16})`);

  await bootLibrary(page, url);
  await page.locator('[data-size-stop="32"]').click();
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Palettes" }).click();
  await grayscaleReady(page);
  await setZoom(page, "1");

  const presetInput = page.getByRole("complementary", { name: "Grayscale presets" }).getByRole("textbox", { name: "Sample text", exact: true });
  await presetInput.fill("Aa 0123");
  await presetCanvasRendered(page, 0);
  const caps = await presetBackingHeight(page, 0);
  assert.ok(caps >= 16 && caps < 46, `caps row trims the full 46px line box (got ${caps})`);

  await presetInput.fill("gjpqy 0123");
  await presetCanvasRendered(page, 0);
  const descenders = await presetBackingHeight(page, 0);
  assert.ok(descenders > caps, `descenders extend the row (${descenders} vs ${caps})`);
  assert.ok(descenders < 70, "descender row stays below the untrimmed line box");
  assert.ok(await presetBottomInk(page, 0, 255), "descender ink survives the trim");

  await setZoom(page, "4");
  await presetCanvasRendered(page, 0);
  const wrapped = await presetBackingHeight(page, 0);
  assert.ok(wrapped > descenders, `narrow zoom wraps instead of clipping (${wrapped} vs ${descenders})`);
  assert.ok(await presetBottomInk(page, 0, 255), "descender ink survives across zoom");

  const mainCanvas = page.locator('main section[aria-label="Grayscale preview"] canvas');
  await page.getByRole("region", { name: "Grayscale preview" }).getByRole("textbox", { name: "Sample text", exact: true }).fill("gjpqy 0123");
  await page.waitForFunction((expected) => {
    const el = document.querySelector('main section[aria-label="Grayscale preview"] canvas');
    return el instanceof HTMLCanvasElement && el.height === expected;
  }, descenders);
  assert.equal(await mainCanvas.evaluate((el) => (el as HTMLCanvasElement).height), descenders, "main uses the same text bounds as the unwrapped preset");
  assert.ok(
    await mainCanvas.evaluate((el) => {
      const viewport = el.parentElement;
      if (!(viewport instanceof HTMLElement)) throw new Error("main viewport is missing");
      return viewport.classList.contains("rounded-lg") && viewport.scrollHeight <= viewport.clientHeight + 1;
    }),
    "main frame and scroll behavior stay intact",
  );
});

test("preview spacing stays consistent across fonts and zoom", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(`${url}#/palettes/`, { waitUntil: "networkidle" });
  await grayscaleReady(page);
  const preview = page.getByRole("region", { name: "Grayscale preview" });
  await preview.getByRole("textbox", { name: "Sample text", exact: true }).fill("Ágj");
  await page.getByRole("complementary", { name: "Grayscale presets" }).getByRole("textbox", { name: "Sample text", exact: true }).fill("Ágj");

  for (const font of ["Roboto", "Roboto Italic", "Roboto Flex", "Literata", "Source Sans 3"]) {
    await preview.getByRole("combobox", { name: "Preview font", exact: true }).click();
    await page.getByRole("option", { name: font, exact: true }).click();
    for (const zoom of ["1", "4"]) {
      await setZoom(page, zoom);
      await page.waitForFunction((expectedZoom) => {
        const canvases = [...document.querySelectorAll("main canvas")];
        return canvases.length === 2 && canvases.every((element) => element instanceof HTMLCanvasElement
          && element.dataset.rendered === "true" && element.height > 0
          && element.getBoundingClientRect().height / element.height === expectedZoom);
      }, Number(zoom));
      const [preset, main] = await page.locator("main canvas").evaluateAll((canvases) => canvases.map((element) => {
        const canvas = element as HTMLCanvasElement;
        const context = canvas.getContext("2d")!;
        const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
        let top = canvas.height;
        let bottom = -1;
        for (let y = 0; y < canvas.height; y += 1) {
          for (let x = 0; x < canvas.width; x += 1) {
            if (pixels[(y * canvas.width + x) * 4] === 255) continue;
            top = Math.min(top, y);
            bottom = Math.max(bottom, y);
          }
        }
        const style = getComputedStyle(canvas);
        const bounds = canvas.getBoundingClientRect();
        const frame = canvas.parentElement!.getBoundingClientRect();
        const header = canvas.previousElementSibling?.getBoundingClientRect();
        return { height: canvas.height, top, bottom: canvas.height - bottom - 1,
          margin: [style.marginTop, style.marginBottom],
          headerGap: header ? bounds.top - header.bottom : 0,
          bottomGap: frame.bottom - bounds.bottom };
      }));
      assert.ok(preset && main);
      assert.equal(main.height, preset.height, `${font} at ${zoom}× shares text bounds`);
      assert.ok(main.top <= 1 && main.bottom <= 1, `${font} fits accent and descender bounds without surplus leading`);
      assert.deepEqual(main.margin, ["32px", "32px"], "vertical spacing stays fixed in screen pixels");
      assert.equal(main.headerGap, 32, "text has breathing room below the header divider");
      assert.equal(main.bottomGap, 33, "bottom uses the vertical spacing plus the frame border");
    }
  }
});

test("preset viewport matches tinted paper on narrow inverse rows", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.goto(`${url}#/palettes/`, { waitUntil: "networkidle" });
  await grayscaleReady(page);
  await presetCanvasRendered(page, 0);

  await page.locator("[data-canvas-inverse]").click();
  await page.waitForFunction(
    () => (document.querySelector("[data-preset-frame]") as HTMLElement | null)?.style.backgroundColor === "rgb(0, 0, 0)",
  );
  await setZoom(page, "4");
  await presetCanvasRendered(page, 0);
  assert.equal(await presetViewport(page, 0), "rgb(0, 0, 0)", "viewport hides the remainder strip");
  assert.deepEqual(await presetPixel(page, 0, 0, 0), [0, 0, 0], "paper pixel matches the viewport");
});

test("main sample text wraps multiline and canvas follows content", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(`${url}#/palettes/`, { waitUntil: "networkidle" });
  await grayscaleReady(page);

  const input = page.getByRole("region", { name: "Grayscale preview" }).getByRole("textbox", { name: "Sample text", exact: true });
  assert.equal(await input.evaluate((el) => el.tagName), "TEXTAREA");
  const canvas = page.locator('main section[aria-label="Grayscale preview"] canvas');
  const canvasHeight = (): Promise<number> => canvas.evaluate((el) => parseFloat((el as HTMLCanvasElement).style.height));
  const viewportFits = (): Promise<boolean> => canvas.evaluate((el) => {
    const viewport = el.parentElement;
    if (!(viewport instanceof HTMLElement)) throw new Error("main viewport is missing");
    return viewport.scrollHeight <= viewport.clientHeight + 1;
  });
  const canvasLabel = (): Promise<string | null> => canvas.getAttribute("aria-label");

  await input.fill("Line one\nLine two\n\nLine four");
  await page.waitForFunction(
    () => document.querySelector('main section[aria-label="Grayscale preview"] canvas')?.getAttribute("aria-label")?.includes("Line two\n\nLine four"),
  );
  assert.ok((await canvasLabel())?.includes("Line two\n\nLine four"), "explicit blank lines survive");

  await input.fill(Array(20).fill("Wrapped line of sample text here").join("\n"));
  await page.waitForFunction(() => {
    const el = document.querySelector('main section[aria-label="Grayscale preview"] canvas');
    return el instanceof HTMLCanvasElement && parseFloat(el.style.height) > 384;
  });
  assert.ok(await viewportFits(), "tall content grows the frame instead of scrolling inside");
  const tall = await canvasHeight();

  await input.fill("Hi");
  await page.waitForFunction((previous) => {
    const el = document.querySelector('main section[aria-label="Grayscale preview"] canvas');
    return el instanceof HTMLCanvasElement && parseFloat(el.style.height) < previous;
  }, tall);
  assert.ok(await viewportFits(), "short content shrinks the frame");
  assert.ok((await canvasHeight()) < 200, "single line stays compact");

  const short = await canvasHeight();
  await input.fill("\nHi\n");
  await page.waitForFunction((previous) => {
    const el = document.querySelector('main section[aria-label="Grayscale preview"] canvas');
    return el instanceof HTMLCanvasElement && parseFloat(el.style.height) > previous;
  }, short);
  assert.ok((await canvasHeight()) > short + 2 * 16 * (34 / 24), "leading and trailing blank lines retain their line boxes");

  await input.fill("");
  await page.waitForFunction(() => {
    const el = document.querySelector('main section[aria-label="Grayscale preview"] canvas');
    return el instanceof HTMLCanvasElement && el.height === 23;
  });
  assert.equal(await canvas.evaluate((el) => {
    const element = el as HTMLCanvasElement;
    const pixels = element.getContext("2d")!.getImageData(0, 0, element.width, element.height).data;
    return pixels.every((value) => value === 255);
  }), true, "empty text retains one blank line without ink");

  await input.fill(`${"word ".repeat(100)}`);
  await page.waitForFunction(
    () => document.querySelector('main section[aria-label="Grayscale preview"] canvas')?.getAttribute("aria-label")?.includes("word word"),
  );
  const wrapped = await canvas.evaluate((el) => {
    if (!(el instanceof HTMLCanvasElement)) throw new Error("main canvas is missing");
    const viewport = el.parentElement;
    if (!(viewport instanceof HTMLElement)) throw new Error("main viewport is missing");
    return { backing: el.width, visible: viewport.clientWidth };
  });
  assert.ok(wrapped.backing <= wrapped.visible, `width wraps instead of overflowing (${wrapped.backing} vs ${wrapped.visible})`);
});

test("a debounced preview write cannot undo navigation to palettes", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const ids = await cardIds(page);
  await page.goto(`${url}#/font/${ids[0]}/`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelector('#font-select[data-state]:not(:disabled)') !== null);
  await page.locator("[data-text]").fill("Palettes race probe");
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Palettes" }).click();
  await grayscaleReady(page);
  await page.waitForTimeout(600);
  assert.equal(await hashPath(page), "/palettes/");
  assert.equal(await hashParam(page, "v"), null);
});

test("bit depth selector preserves curves, selection, and preset ownership", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(`${url}#/palettes/`, { waitUntil: "networkidle" });
  const selector = page.getByRole("group", { name: "Bit-depth & gray levels", exact: true });
  const pills = selector.getByRole("radiogroup", { name: "Quantization depth", exact: true });
  const depth = (bits: number) => pills.getByRole("radio", { name: `${bits}-bit · ${2 ** bits} levels`, exact: true });
  assert.equal(await pills.getByRole("radio").count(), 4);
  assert.equal(await depth(1).getAttribute("aria-checked"), "true");
  assert.equal(await depth(1).isDisabled(), true);
  assert.equal(await depth(3).isDisabled(), true, "built-in Monochrome stays read-only");

  await page.getByRole("button", { name: "Add preset" }).click();
  await page.waitForFunction(
    () => document.querySelector('[aria-label="2-bit · 4 levels"]')?.getAttribute("aria-checked") === "true",
    null,
    { timeout: 20000 },
  );
  assert.equal(await depth(2).getAttribute("aria-checked"), "true");
  assert.equal(await selector.getByRole("slider", { name: "Selected gray value", exact: true }).count(), 0, "gray editing uses only the numerical input");
  const reset = selector.getByRole("button", { name: "Reset levels", exact: true });
  assert.equal(await reset.evaluate((button) => !!button.closest('[data-slot="card-header"]')), true, "reset lives in the panel header");
  assert.equal(await reset.textContent(), "", "reset is icon-only");
  assert.equal(await reset.locator("svg").count(), 1);
  assert.equal(await selector.getByText("Quantization depth", { exact: true }).evaluate((element) => element.parentElement?.textContent),
    "Quantization depth", "depth title does not repeat the selected option");
  await depth(2).click();
  assert.equal(await depth(2).getAttribute("aria-checked"), "true", "current depth cannot be deselected");
  await selector.getByRole("button", { name: "Select level 1", exact: true }).click();
  const gray = page.getByRole("spinbutton", { name: "Gray value", exact: true });
  await gray.fill("150");
  await page.waitForFunction(
    () => getComputedStyle(document.querySelector('[aria-label="Select level 1"]')!).backgroundColor === "rgb(150, 150, 150)",
    null,
    { timeout: 20000 },
  );
  await depth(3).click();
  await page.waitForFunction(
    () => document.querySelector('[aria-label="3-bit · 8 levels"]')?.getAttribute("aria-checked") === "true",
    null,
    { timeout: 20000 },
  );
  assert.equal(await depth(3).getAttribute("aria-checked"), "true");
  const desktopWidths = await pills.getByRole("radio").evaluateAll((items) => items.map((item) => item.getBoundingClientRect().width));
  assert.ok(Math.max(...desktopWidths) - Math.min(...desktopWidths) < 1, "all four grid columns have equal width, including the selected item");
  const swatches = selector.getByRole("group", { name: "Gray level swatches", exact: true });
  assert.equal(await swatches.getByRole("heading").count(), 0);
  const values = await swatches.getByRole("button").evaluateAll((buttons) => buttons.map((button) => getComputedStyle(button).backgroundColor));
  assert.deepEqual(values, [255, 207, 163, 125, 89, 56, 26, 0].map((gray) => `rgb(${gray}, ${gray}, ${gray})`), "ramp samples the smooth edited response in graph level order");
  await page.waitForFunction(
    () => {
      const label = [...document.querySelectorAll("label")].find((entry) => entry.textContent === "Gray value");
      const input = label ? document.getElementById(label.htmlFor) : null;
      return input instanceof HTMLInputElement && input.value === "163";
    },
    null,
    { timeout: 20000 },
  );
  assert.equal(await gray.inputValue(), "163", "selected curve position follows the new count");
  assert.deepEqual(await swatches.getByRole("button").evaluateAll((buttons) => buttons.map((button) => button.getAttribute("aria-label"))),
    Array.from({ length: 8 }, (_, index) => `Select level ${index}`), "visual and keyboard order follow increasing level indices");
  async function waitGrayValue(want: string): Promise<void> {
    await page.waitForFunction(
      (expected) => {
        const label = [...document.querySelectorAll("label")].find((entry) => entry.textContent === "Gray value");
        const input = label ? document.getElementById(label.htmlFor) : null;
        return input instanceof HTMLInputElement && input.value === expected;
      },
      want,
      { timeout: 20000 },
    );
  }
  await swatches.getByRole("button").first().click();
  await waitGrayValue("255");
  assert.equal(await gray.inputValue(), "255", "leftmost swatch selects paper, level zero");
  assert.equal(await selector.getByRole("slider", { name: "Level 0 gray value", exact: true }).getAttribute("aria-valuenow"), "255");
  await swatches.getByRole("button").last().click();
  await waitGrayValue("0");
  assert.equal(await gray.inputValue(), "0", "rightmost swatch selects full ink, the final graph level");
  assert.equal(await selector.getByRole("slider", { name: "Level 7 gray value", exact: true }).getAttribute("tabindex"), "0");
  await gray.fill("12");
  await waitGrayValue("12");
  await reset.click();
  await waitGrayValue("0");
  assert.equal(await gray.inputValue(), "0", "header reset restores the selected endpoint");
  assert.deepEqual(await swatches.getByRole("button").evaluateAll((buttons) => buttons.map((button) => getComputedStyle(button).backgroundColor)),
    [255, 219, 182, 146, 109, 73, 36, 0].map((gray) => `rgb(${gray}, ${gray}, ${gray})`), "header reset restores the entire ramp at the current depth");
  await depth(3).focus();
  await page.keyboard.press("ArrowRight");
  await page.waitForFunction(() => document.activeElement?.getAttribute("aria-label") === "4-bit · 16 levels");
  await page.keyboard.press("Space");
  await page.waitForFunction(
    () => document.querySelector('[aria-label="4-bit · 16 levels"]')?.getAttribute("aria-checked") === "true",
    null,
    { timeout: 20000 },
  );
  assert.equal(await depth(4).getAttribute("aria-checked"), "true", "arrow keys and Space select depth");
  assert.equal(await swatches.getByRole("button").count(), 16);
  await depth(1).click();
  await page.waitForFunction(
    () => document.querySelector('[aria-label="1-bit · 2 levels"]')?.getAttribute("aria-checked") === "true",
    null,
    { timeout: 20000 },
  );
  assert.equal(await swatches.getByRole("button").count(), 2);
  assert.equal(await selector.getByText("0b · Paper", { exact: true }).count(), 1);
  assert.equal(await selector.getByText("1b · Full ink", { exact: true }).count(), 1);
  assert.equal(await page.getByRole("spinbutton", { name: "Levels", exact: true }).count(), 0);
  await page.getByRole("button", { name: "Add preset" }).click();
  await page.waitForFunction(
    () => document.querySelector('[aria-label="2-bit · 4 levels"]')?.getAttribute("aria-checked") === "true",
    null,
    { timeout: 20000 },
  );
  assert.equal(await depth(2).getAttribute("aria-checked"), "true");
  await page.locator('[data-preset-row="1"]').click();
  await page.waitForFunction(
    () => document.querySelector('[aria-label="1-bit · 2 levels"]')?.getAttribute("aria-checked") === "true",
    null,
    { timeout: 20000 },
  );
  assert.equal(await depth(1).getAttribute("aria-checked"), "true", "switching presets restores its count");
  await depth(3).click();
  await page.setViewportSize({ width: 390, height: 844 });
  const bounds = await selector.boundingBox();
  assert.ok(bounds && bounds.x >= 0 && bounds.x + bounds.width <= 390, "selector fits a narrow viewport");
  const mobileWidths = await pills.getByRole("radio").evaluateAll((items) => items.map((item) => item.getBoundingClientRect().width));
  assert.ok(Math.max(...mobileWidths) - Math.min(...mobileWidths) < 1, "grid columns stay equal at mobile width");
  const icon = selector.getByRole("heading", { name: "Bit-depth & gray levels", exact: true }).locator('span[aria-hidden="true"]');
  assert.deepEqual(await icon.evaluate((element) => {
    const bounds = element.getBoundingClientRect();
    return [getComputedStyle(element).maskImage.includes("bit-depth"), bounds.width, bounds.height];
  }), [true, 11.25, 11.25]);
  await page.locator('[data-preset-row="0"]').click();
  assert.equal(await depth(1).getAttribute("aria-checked"), "true");
  assert.equal(await depth(2).isDisabled(), true);
});

test("sparse response handles and exact edits use one graph at every depth", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  await page.goto(`${url}#/palettes/`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Add preset" }).click();
  const panel = page.getByRole("group", { name: "Bit-depth & gray levels", exact: true });
  const graph = panel.getByRole("group", { name: "Gray response graph", exact: true });
  const gray = panel.getByRole("spinbutton", { name: "Gray value", exact: true });
  const reset = panel.getByRole("button", { name: "Reset levels", exact: true });
  const point = (i: number) => graph.getByRole("slider", { name: `Level ${i} gray value`, exact: true });
  const values = () => graph.getByRole("slider").evaluateAll((items) => items.map((item) => Number(item.getAttribute("aria-valuenow"))));
  const wantValues = async (expected: number[]): Promise<void> => {
    await page.waitForFunction(
      (want) => JSON.stringify([...document.querySelectorAll('[role="slider"][aria-label$="gray value"]')]
        .map((item) => Number(item.getAttribute("aria-valuenow")))) === JSON.stringify(want),
      expected,
      { timeout: 20000 },
    );
  };
  const waitPin = async (index: number, pinned: boolean): Promise<void> => {
    await page.waitForFunction(
      ([i, state]) => document.querySelector(`[role="slider"][aria-label="Level ${i} gray value"]`)
        ?.getAttribute("data-pinned") === state,
      [index, String(pinned)] as [number, string],
      { timeout: 20000 },
    );
  };
  const waitLevelValue = async (index: number, want: number): Promise<void> => {
    await page.waitForFunction(
      ([i, value]) => Number(document.querySelector(`[role="slider"][aria-label="Level ${i} gray value"]`)
        ?.getAttribute("aria-valuenow")) === value,
      [index, want] as [number, number],
      { timeout: 20000 },
    );
  };
  const linear = (count: number): number[] =>
    Array.from({ length: count }, (_, i) => Math.round(255 * (1 - i / (count - 1))));
  assert.equal(await panel.getByText(/Filled dots are handles/).count(), 0);
  assert.equal(await panel.getByText(/Shift adjusts by 10/).count(), 0);
  assert.equal(await panel.getByText(/Pin all levels to adjust/).count(), 0);
  assert.equal(await panel.getByText(/^(Pinned handle|Follows the curve)$/).count(), 0);
  assert.equal(await panel.getByRole("button", { name: /^(Unpin level|Pin level|Pin all levels)$/ }).count(), 0);

  for (const bits of [1, 2, 3, 4]) {
    await panel.getByRole("radio", { name: `${bits}-bit · ${2 ** bits} levels`, exact: true }).click();
    if (await reset.isEnabled()) await reset.click();
    const count = 2 ** bits;
    const index = Math.floor(count / 2);
    await wantValues(linear(count));
    const initial = await values();
    assert.equal(await graph.getByRole("slider").count(), count);
    assert.equal(await graph.locator('[data-pinned="true"]').count(), 2);
    assert.ok((await graph.locator("path").getAttribute("d"))?.includes(" C "), "graph draws a smooth response");

    // Clicking adds a handle without moving the curve or snapping to the cursor.
    const pathBefore = await graph.locator("path").getAttribute("d");
    await point(index).click();
    await waitPin(index, true);
    assert.deepEqual(await values(), initial);
    assert.equal(await graph.locator("path").getAttribute("d"), pathBefore);
    assert.equal(await point(index).getAttribute("data-pinned"), "true");
    if (count > 2) {
      await point(index).click();
      await waitPin(index, false);
      assert.equal(await point(index).getAttribute("data-pinned"), "false", "clicking a pinned interior level unpins it");
      assert.deepEqual(await values(), initial);
      await point(index).click();
      await waitPin(index, true);
      assert.equal(await point(index).getAttribute("data-pinned"), "true", "clicking again pins it");
    }
    await point(index).press("ArrowUp");
    await waitLevelValue(index, initial[index]! + 1);
    const nudged = await values();
    assert.equal(nudged[index], initial[index]! + 1, "arrow nudge edits by exactly one byte");
    if (count > 2) {
      await gray.fill(String(initial[index]! + 30));
      await waitLevelValue(index, initial[index]! + 30);
      const shaped = await values();
      assert.equal(shaped[index], initial[index]! + 30);
      if (count >= 8) assert.notEqual(shaped[index - 1], initial[index - 1], "a sparse handle shapes adjacent levels");
      await point(index).click();
      await wantValues(initial);
      assert.deepEqual(await values(), initial, "removing the sole interior handle restores the endpoint ramp");
      assert.equal(await point(index).getAttribute("data-pinned"), "false");
    } else {
      await point(index).click();
      await waitPin(index, true);
      assert.equal(await point(index).getAttribute("data-pinned"), "true", "endpoint remains pinned");
      await reset.click();
      await wantValues(linear(count));
    }

    // Pinning every level changes only the handles, then a micro edit changes only one byte.
    const beforePin = await values();
    for (let i = 1; i < count - 1; i += 1) {
      await point(i).click();
      await waitPin(i, true);
    }
    assert.deepEqual(await values(), beforePin);
    assert.equal(await graph.locator('[data-pinned="true"]').count(), count);
    await panel.getByRole("button", { name: `Select level ${index}`, exact: true }).click();
    await point(index).press("ArrowUp");
    await wantValues(beforePin.map((value, i) => i === index ? value + 1 : value));
    assert.deepEqual(await values(), beforePin.map((value, i) => i === index ? value + 1 : value));
    await point(index).press("Shift+ArrowDown");
    await wantValues(beforePin.map((value, i) => i === index ? Math.max(0, value - 9) : value));
    assert.equal((await values())[index], Math.max(0, beforePin[index]! - 9));
    await gray.fill(String(beforePin[index]! + 2));
    await wantValues(beforePin.map((value, i) => i === index ? value + 2 : value));
    assert.deepEqual(await values(), beforePin.map((value, i) => i === index ? value + 2 : value));
  }

  // Keyboard selection moves focus without pinning; Enter/Delete edit handle ownership.
  await reset.click();
  await wantValues(linear(16));
  const beforeKeyboard = await values();
  await point(7).press("Enter");
  await waitPin(7, true);
  assert.equal(await point(7).getAttribute("data-pinned"), "true");
  await point(7).press("Enter");
  await waitPin(7, false);
  assert.equal(await point(7).getAttribute("data-pinned"), "false", "Enter toggles a pinned handle off");
  await point(7).press("Enter");
  await waitPin(7, true);
  await point(7).press("ArrowRight");
  assert.equal(await point(8).evaluate((element) => document.activeElement === element), true);
  assert.equal(await point(8).getAttribute("data-pinned"), "false");
  await point(8).press("Space");
  await waitPin(8, true);
  assert.equal(await point(8).getAttribute("data-pinned"), "true");
  await point(8).press("Delete");
  await waitPin(8, false);
  assert.equal(await point(8).getAttribute("data-pinned"), "false");
  await point(8).press("ArrowLeft");
  await point(7).press("Backspace");
  await waitPin(7, false);
  assert.equal(await point(7).getAttribute("data-pinned"), "false");
  assert.deepEqual(await values(), beforeKeyboard);

  // Pointer capture keeps editing during a drag outside the chart, then releases it.
  if (await reset.isEnabled()) await reset.click();
  await wantValues(linear(16));
  await point(7).click();
  await waitPin(7, true);
  await point(7).scrollIntoViewIfNeeded();
  const box = await point(7).boundingBox();
  assert.ok(box);
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 - 25, { steps: 5 });
  await page.waitForFunction(
    () => Number(document.querySelector('[role="slider"][aria-label="Level 7 gray value"]')?.getAttribute("aria-valuenow")) > 136,
    null,
    { timeout: 20000 },
  );
  assert.ok((await values())[7]! > 136);
  await page.mouse.move(box.x + box.width / 2, -20, { steps: 5 });
  await page.waitForFunction(
    () => document.querySelector('[role="slider"][aria-label="Level 7 gray value"]')?.getAttribute("aria-valuenow") === "255",
    null,
    { timeout: 20000 },
  );
  assert.equal((await values())[7], 255);
  await page.mouse.up();
  assert.equal(await point(7).getAttribute("data-pinned"), "true", "dragging an existing handle does not unpin it");
  const released = await values();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  assert.deepEqual(await values(), released, "released pointer no longer edits");

  // Handles belong to their preset, and built-in Monochrome has no editing controls.
  await page.getByRole("button", { name: "Add preset" }).click();
  await page.waitForFunction(
    () => document.querySelectorAll('[role="group"][aria-label="Gray response graph"] [data-pinned="true"]').length === 2,
    null,
    { timeout: 20000 },
  );
  assert.equal(await graph.locator('[data-pinned="true"]').count(), 2);
  await page.locator('[data-preset-row="1"]').click();
  assert.deepEqual(await values(), released);
  assert.equal(await graph.locator('[data-pinned="true"]').count(), 3);
  await page.locator('[data-preset-row="0"]').click();
  assert.equal(await graph.getByRole("slider").count(), 0);
  assert.equal(await panel.getByRole("button", { name: "Pin all levels", exact: true }).count(), 0);
});
