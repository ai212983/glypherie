import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import test from "node:test";
import {
  bootLibrary,
  browserAvailable,
  buildApp,
  canvasRendered,
  sourceSnapshot,
  cardIds,
  sourceReady,
  cardNames,
  createPalettePreset,
  fontDir,
  launch,
  mutatedUploadBytes,
  openNewVariant,
  selectPalettePreset,
  servePrefix,
  setZoom,
  tooltipText,
} from "../helpers/spa-helpers.ts";
import type { Locator, Page } from "playwright-core";

type Digest = { hash: number; ink: number };

async function renderedCardIds(page: Page): Promise<string[]> {
  await page.waitForFunction(
    (count) => document.querySelectorAll('[data-source-preview][data-rendered="true"]').length >= count,
    5,
    { timeout: 30000 },
  );
  return cardIds(page);
}

async function previewHeights(page: Page): Promise<number[]> {
  return page.evaluate(() =>
    [...document.querySelectorAll("[data-card-preview]")].map(
      (element) => (element as HTMLElement).getBoundingClientRect().height,
    ),
  );
}

async function digests(page: Page, ids: string[]) {
  return Promise.all(ids.map((id) => sourceSnapshot(page, id)));
}

async function canvasAppearance(page: Page): Promise<{ palette: string | null; inverse: boolean }> {
  return page.evaluate(() => ({
    palette: document.querySelector("[data-canvas-preset]")?.getAttribute("data-value") ?? null,
    inverse: document.querySelector("[data-canvas-inverse]")?.getAttribute("aria-checked") === "true",
  }));
}

async function swatchStyle(swatch: Locator): Promise<{ background: string; color: string }> {
  return swatch.evaluate((element) => {
    const style = getComputedStyle(element);
    return { background: style.backgroundColor, color: style.color };
  });
}

async function waitForSettled(page: Page, ids: string[]) {
  await page.waitForFunction((fontIds) => {
    const sample = document.querySelector("[data-index-text]") as HTMLInputElement | null;
    if (!sample) return false;
    const text = sample.value;
    const zoom = Number(document.querySelector("[data-preview-zoom]")?.getAttribute("data-value"));
    const palette = document.querySelector("[data-canvas-preset]")?.getAttribute("data-value");
    const inverse = document.querySelector("[data-canvas-inverse]")?.getAttribute("aria-checked") === "true";
    const size = Number(document.querySelector("[data-font-size-control]")?.getAttribute("data-value"));
    const sourcesReady = fontIds.every((id) => {
      const preview = document.querySelector(`[data-card-preview="${id}"]`) as HTMLElement | null;
      const source = preview?.querySelector<HTMLElement>("[data-source-preview]");
      if (!source || source.dataset.rendered !== "true") return false;
      const style = getComputedStyle(source);
      return source.textContent === text && parseFloat(style.fontSize) === size * zoom;

    });
    return sourcesReady && [...document.querySelectorAll<HTMLCanvasElement>("[data-library-variant-canvas]")].every((canvas) => {
      if (canvas.dataset.rendered !== "true" || !canvas.dataset.renderKey) return false;
      const rendered = JSON.parse(canvas.dataset.renderKey);
      return rendered.palette === palette && rendered.inverse === inverse && rendered.zoom === zoom;
    });
  }, ids, { timeout: 30000 });
  return digests(page, ids);
}

type RGB = [number, number, number];

async function cardFrame(page: Page, fontId: string): Promise<{ background: string; borderRadius: string; caption: string | null }> {
  return page.evaluate((id) => {
    const frame = document.querySelector(`[data-card-frame="${id}"]`) as HTMLElement | null;
    if (!frame) throw new Error(`card frame ${id} is missing`);
    const style = getComputedStyle(frame);
    return { background: style.backgroundColor, borderRadius: style.borderRadius, caption: frame.textContent };
  }, fontId);
}

async function variantDigest(page: Page, variantId: string): Promise<Digest> {
  return page.evaluate((id) => {
    const canvas = document.querySelector(`[data-library-variant-canvas="${id}"]`) as HTMLCanvasElement | null;
    if (!canvas || canvas.width === 0) return { hash: 0, ink: 0 };
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
  }, variantId);
}

async function cardGeometry(page: Page, fontId: string): Promise<{ width: number; height: number }> {
  return page.locator(`[data-source-preview="${fontId}"]`).evaluate((source) => {
    const box = source.getBoundingClientRect();
    return { width: box.width, height: box.height };
  });
}

const WORKER_STATS_SCRIPT = `
window.__workerStats = { constructed: 0, loads: {}, specs: {}, requests: [], kerningRequests: 0 };
const RealWorker = window.Worker;
window.Worker = function (url, options) {
  window.__workerStats.constructed += 1;
  const worker = new RealWorker(url, options);
  const post = worker.postMessage.bind(worker);
  worker.postMessage = (message, transfer) => {
    if (message && typeof message === "object") {
      if (message.kind === "kerning") window.__workerStats.kerningRequests += 1;
      if (message.kind === "load" && typeof message.fontId === "string") {
        const loads = window.__workerStats.loads;
        loads[message.fontId] = (loads[message.fontId] ?? 0) + 1;
      }
      if (message.kind === "render" && typeof message.fontId === "string" && message.spec) {
        window.__workerStats.specs[message.fontId] = {
          width: message.spec.width,
          sizePx: message.spec.size_px,
          axes: message.spec.axes,
          renderer: message.spec.renderer,
          pipeline: message.spec.pipeline ?? null,
        };
        window.__workerStats.requests.push({
          fontId: message.fontId,
          text: message.spec.text,
          sizePx: message.spec.size_px,
          outputBits: message.spec.output_bits,
          axes: message.spec.axes,
          spacing: message.spec.letter_spacing_px,
          kerning: message.spec.kerning,
          stemFitting: message.spec.stem_fitting ?? null,
          pipeline: message.spec.pipeline ?? null,
          renderer: message.spec.renderer,
          width: message.spec.width,
          palette: message.spec.palette ?? null,
          paper: message.spec.background,
          ink: message.spec.foreground,
        });
      }
    }
    return post(message, transfer);
  };
  return worker;
};
`;

interface RenderRequest {
  fontId: string;
  text: string;
  sizePx: number;
  outputBits: number;
  axes: Record<string, number>;
  spacing: number;
  kerning: boolean;
  stemFitting: string | null;
  pipeline: { fitting: string; rasterization: string } | null;
  renderer?: string;
  width: number;
  palette: number[][] | null;
  paper: number[];
  ink: number[];
}

interface WorkerStats {
  constructed: number;
  kerningRequests: number;
  loads: Record<string, number>;
  specs: Record<string, { width: number; sizePx: number; axes: Record<string, number>; renderer?: string; pipeline: RenderRequest["pipeline"] }>;
  requests: RenderRequest[];
}

async function workerStats(page: Page): Promise<WorkerStats> {
  return page.evaluate(() => (window as unknown as { __workerStats: WorkerStats }).__workerStats);
}

test("every card displays the shared sample in its original source font", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.addInitScript(WORKER_STATS_SCRIPT);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await bootLibrary(page, url);
  const ids = await renderedCardIds(page);
  assert.equal(ids.length, 5);
  for (const id of ids) {
    assert.ok(await sourceReady(page, id), `card ${id} displays its loaded source font`);
  }
  const sourceStyles = await page.locator("[data-source-preview]").evaluateAll((sources) => sources.map((source) => {
    const style = getComputedStyle(source);
    return { family: style.fontFamily, optical: style.fontOpticalSizing, synthesis: style.fontSynthesis, rendering: style.imageRendering };
  }));
  for (const style of sourceStyles) {
    assert.match(style.family, /source-[a-f0-9]{64}/);
    assert.equal(style.optical, "none");
    assert.equal(style.synthesis, "none");
    assert.notEqual(style.rendering, "pixelated");
  }
  assert.equal((await workerStats(page)).requests.length, 0, "source text bypasses native bitmap output");
  assert.equal(await page.locator("[data-card-canvas]").count(), 0);
  assert.deepEqual(errors, []);

  assert.equal(await page.locator("[data-font-license]").count(), 5);
  assert.match(await page.locator("[data-font-license]").first().innerText(), /SIL OFL/);
  assert.equal(await page.locator("[data-font-license]").first().getAttribute("aria-label"), "License: SIL OFL");
  assert.equal(await page.locator('[data-font-info] [data-slot="tooltip-trigger"]').count(), 0, "font info badges have no tooltips");

  const info = page.locator("[data-font-info]");
  assert.equal(await info.count(), 5);
  const italic = page.locator("[data-font-card]").filter({ has: page.locator("[data-font-name]", { hasText: "Roboto Italic" }) });
  assert.match(await italic.locator("[data-font-info]").innerText(), /Style\s+Italic/i);
  const regular = page.locator("[data-font-card]").filter({ has: page.locator("[data-font-name]", { hasText: "Roboto Regular" }) });
  const regularInfo = await regular.locator("[data-font-info]").innerText();
  assert.match(regularInfo, /Kerning\s+YES/i);
  assert.doesNotMatch(regularInfo, /Style/i, "upright fonts omit the optional style box");
  assert.match(regularInfo, /Characters\s+927/i, "shows Roboto’s encoded-character coverage, rather than its 1,326 glyph entries");
  assert.doesNotMatch(regularInfo, /Glyph count/i);

  await page.setViewportSize({ width: 390, height: 844 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert.ok(overflow <= 0, `no horizontal overflow on mobile, got ${overflow}px`);
  const tabbable = await page.evaluate(
    () => document.querySelectorAll("[data-card-preview] [tabindex]").length,
  );
  assert.equal(tabbable, 0, "card previews add no nested tab stops");

  await page.locator("[data-import-font]").setInputFiles({
    name: "no-kerning.otf",
    mimeType: "font/otf",
    buffer: await fs.readFile(path.join(fontDir, "../tools/generator/tests/fixtures/static-cff.otf")),
  });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-info]").length === 6);
  const addedId = (await cardIds(page)).find((id) => !ids.includes(id))!;
  const noKerning = page.locator(`[data-font-info="${addedId}"]`);
  assert.match(await noKerning.innerText(), /Kerning\s+NO/i);
  assert.match(await noKerning.locator("dd").nth(1).getAttribute("class") ?? "", /text-destructive\/80/);
  assert.equal((await workerStats(page)).kerningRequests, 0, "library kerning availability uses metadata without scanning pairs");
});

test("source previews reflow without changing size or axes", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await bootLibrary(page, url);
  const ids = await renderedCardIds(page);
  await page.locator("[data-index-text]").fill("Pack my box with five dozen liquor jugs. ".repeat(12));
  await waitForSettled(page, ids);
  const before = await sourceSnapshot(page, ids[0]!);
  for (const width of [1200, 1024, 390, 2560]) {
    await page.setViewportSize({ width, height: 900 });
    await waitForSettled(page, ids);
    const after = await sourceSnapshot(page, ids[0]!);
    assert.equal(after.size, before.size);
    assert.equal(after.axes, before.axes);
    if (width === 390) assert.ok(after.height > before.height, "narrow source text wraps naturally");
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  }
});

test("sample text and zoom update every card preview", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const ids = await renderedCardIds(page);
  const before = await waitForSettled(page, ids);

  await page.locator("[data-index-text]").fill("Agave grids glint.");
  const afterText = await waitForSettled(page, ids);
  for (const [index, id] of ids.entries()) {
    assert.notDeepEqual(afterText[index], before[index], `card ${id} repaints for new text`);
    assert.ok(await sourceReady(page, id), `card ${id} keeps its source face`);
  }

  const heightsBefore = await previewHeights(page);
  await setZoom(page, "4");
  await page.waitForFunction(
    (value) => document.querySelector("#zoom")?.getAttribute("data-value") === value,
    "4",
  );
  const afterZoom = await waitForSettled(page, ids);
  const heightsAfter = await previewHeights(page);
  for (const [index, id] of ids.entries()) {
    assert.notDeepEqual(afterZoom[index], afterText[index], `card ${id} repaints for zoom`);
    assert.ok(
      heightsAfter[index]! >= heightsBefore[index]!,
      `card ${id} grows with zoom (${heightsBefore[index]} to ${heightsAfter[index]})`,
    );
  }
});

test("long sample wraps and extends cards without page overflow", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const ids = await renderedCardIds(page);
  await waitForSettled(page, ids);

  await page.locator("[data-index-text]").fill("Ag");
  await waitForSettled(page, ids);
  const shortHeights = await previewHeights(page);
  const longSample = `${"Pack my box with five dozen liquor jugs. ".repeat(12)}Tail words finish the paragraph.`;
  await page.locator("[data-index-text]").fill(longSample.slice(0, 2000));
  await page.waitForFunction((previous: number[]) => {
    const previews = [...document.querySelectorAll("[data-card-preview]")] as HTMLElement[];
    return previews.length === previous.length
      && previews.every((preview, index) => preview.getBoundingClientRect().height > previous[index]!);
  }, shortHeights, { timeout: 25000 });
  const longHeights = await previewHeights(page);
  for (const [index, id] of ids.entries()) {
    assert.ok(longHeights[index]! > shortHeights[index]!);
    assert.ok(await sourceReady(page, id));
  }
  const clipped = await page.evaluate(() => {
    const previews = [...document.querySelectorAll("[data-card-preview]")] as HTMLElement[];
    return previews.filter((preview) => preview.scrollHeight - preview.clientHeight > 1).length;
  });
  assert.equal(clipped, 0, "wrapped text is fully contained, never clipped");

  await setZoom(page, "4");
  await waitForSettled(page, ids);
  const zoomedHeights = await previewHeights(page);
  for (const [index, id] of ids.entries()) {
    assert.ok(
      zoomedHeights[index]! >= longHeights[index]!,
      `card ${id} grows further at zoom 4 with long text`,
    );
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await waitForSettled(page, ids);
  const mobile = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert.ok(mobile <= 0, `no horizontal overflow on mobile, got ${mobile}px`);
  const extreme = "Pack my box with five dozen liquor jugs. ".repeat(200).slice(0, 8192);
  await page.locator("[data-index-text]").fill(extreme);
  await waitForSettled(page, ids);
  assert.equal(await page.locator("[data-card-limit]").count(), 0, "source text has no bitmap allocation limit");
  assert.equal(await page.locator("[data-source-preview]").first().textContent(), extreme);

});

test("index settings survive navigation and reload", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.addInitScript({ content: WORKER_STATS_SCRIPT });
  const page = await context.newPage();
  await bootLibrary(page, url);
  const names = await cardNames(page);
  const ids = await renderedCardIds(page);

  await page.locator("[data-index-text]").fill("Qq Rr Zz");
  await setZoom(page, "3");
  await page.waitForFunction(
    (value) => document.querySelector("#zoom")?.getAttribute("data-value") === value,
    "3",
  );

  assert.deepEqual(
    await page.locator("[data-size-stop]").evaluateAll(
      (items) => items.map((item) => item.getAttribute("data-size-stop")),
    ),
    ["8", "10", "12", "16", "24", "32", "48"],
    "base size offers seven steps in order",
  );
  assert.equal(
    await page.locator("[data-font-size-control]").getAttribute("data-value"),
    "16",
    "base size defaults to 16",
  );
  const atDefault = await waitForSettled(page, ids);
  await page.getByRole("button", { name: "24 px", exact: true }).click();
  const atLarge = await waitForSettled(page, ids);
  for (const [index, id] of ids.entries()) {
    assert.notDeepEqual(atLarge[index], atDefault[index], `card ${id} repaints for base size`);
  }
  assert.equal(await page.locator("#zoom").getAttribute("data-value"), "3", "base size leaves zoom untouched");

  await page.getByRole("combobox", { name: "Canvas preset" }).click();
  await page.getByRole("option", { name: "Warm", exact: true }).click();
  await page.locator("[data-canvas-inverse]").click();
  const settled = await waitForSettled(page, ids);
  const stats = await workerStats(page);
  assert.equal(stats.constructed, 1, "one shared worker serves the app");
  for (const id of ids) {
    assert.equal(stats.loads[id] ?? 0, 0, `source ${id} needs no native load`);
  }
  assert.equal(stats.kerningRequests, 0, "library renders never scan kerning pairs");
  assert.equal(stats.requests.length, 0, "source previews do not call the bitmap renderer");
  const literata = ids[names.findIndex((name) => /^Literata/.test(name))]!;
  assert.match((await sourceSnapshot(page, literata)).axes, /"opsz" 12/);

  await openNewVariant(page, ids[0]!);
  await page.waitForFunction(
    (name) => document.querySelector(".family h2")?.textContent === name,
    names[0],
  );
  assert.notEqual(
    await page.locator("[data-text]").inputValue(),
    "Qq Rr Zz",
    "variant keeps its own saved settings",
  );
  await page.locator('[data-primary-nav="fonts"]').click();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  async function expectLibrarySettings(label: string): Promise<void> {
    assert.equal(await page.locator("[data-index-text]").inputValue(), "Qq Rr Zz", `${label} keeps sample text`);
    assert.equal(await page.locator("#zoom").getAttribute("data-value"), "3", `${label} keeps zoom`);
    assert.equal(
      await page.locator("[data-font-size-control]").getAttribute("data-value"),
      "24",
      `${label} keeps base size`,
    );
    assert.equal(
      await page.locator("[data-canvas-preset]").getAttribute("data-value"),
      "warm-paper",
      `${label} keeps the canvas preset`,
    );
    assert.equal(
      await page.locator("[data-canvas-inverse]").getAttribute("aria-checked"),
      "true",
      `${label} keeps inverse`,
    );
  }
  async function expectFrameCaption(label: string): Promise<void> {
    const frame = await cardFrame(page, ids[0]!);
    assert.ok(frame.caption?.includes("Source"), `${label} frame keeps its caption`);
    assert.ok(
      frame.caption?.includes("24 px"),
      `${label} caption shows the native base size, not zoom-scaled pixels`,
    );
    assert.equal(frame.background, "rgb(26, 24, 21)", `${label} frame follows the inverted paper`);
  }
  await expectLibrarySettings("navigation");
  await expectFrameCaption("navigation");
  const returned = await waitForSettled(page, ids);
  assert.deepEqual(returned, settled, "card previews restore from the shared worker cache");
  const after = await workerStats(page);
  assert.equal(after.constructed, 1, "no second worker across the round trip");
  for (const id of ids) {
    assert.equal(after.loads[id] ?? 0, id === ids[0] ? 1 : 0, `native loading is limited to generated variants`);
  }
  await page.reload();
  await page.locator("[data-index-text]").waitFor();
  await expectLibrarySettings("a reload");
  await expectFrameCaption("a reload");
  await waitForSettled(page, ids);
  assert.deepEqual(await digests(page, ids), settled, "reloaded card previews use the restored settings");

  const reopened = await context.newPage();
  await bootLibrary(reopened, url);
  assert.equal(await reopened.locator("[data-preview-zoom]").getAttribute("data-value"), "3", "a new tab restores library zoom");
  assert.equal(await reopened.locator("[data-index-text]").inputValue(), "Qq Rr Zz", "a new tab restores sample text");
  assert.equal(
    await reopened.locator("[data-font-size-control]").getAttribute("data-value"),
    "24",
    "a new tab restores base size",
  );
  assert.equal(
    await reopened.locator("[data-canvas-preset]").getAttribute("data-value"),
    "warm-paper",
    "a new tab restores the canvas preset",
  );
  assert.equal(
    await reopened.locator("[data-canvas-inverse]").getAttribute("aria-checked"),
    "true",
    "a new tab restores inverse",
  );
  await reopened.locator("[data-index-text]").fill("");
  await reopened.reload();
  await reopened.locator("[data-index-text]").waitFor();
  assert.equal(await reopened.locator("[data-index-text]").inputValue(), "", "an intentionally empty sample stays empty");
  await context.close();
});

test("variant renders from the shared cache without reloading fonts", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const names = await cardNames(page);
  const ids = await renderedCardIds(page);
  await openNewVariant(page, ids[1]!);
  await page.waitForFunction(
    (name) => document.querySelector(".family h2")?.textContent === name,
    names[1],
  );
  await page.waitForFunction(canvasRendered);
  assert.equal(
    await page.locator("text=Loading font into the renderer…").count(),
    0,
    "cached font renders without a loader flash",
  );
  assert.equal(
    await page.evaluate(() => document.querySelectorAll("[data-source-preview]").length),
    0,
    "index canvases unmount on detail",
  );
});

test("uploaded fonts preview, empty text restores, unknown glyphs error usefully", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await bootLibrary(page, url);
  const pangram = await page.locator("[data-index-text]").inputValue();
  await renderedCardIds(page);

  const upload = path.join(output, "RobotX.ttf");
  await fs.writeFile(upload, await mutatedUploadBytes(path.join(fontDir, "Roboto.ttf")));
  await page.locator("[data-import-font]").setInputFiles(upload);
  await page.waitForFunction(
    () => document.querySelector("[data-import-status]")?.textContent?.includes("RobotX"),
    null,
    { timeout: 20000 },
  );
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length === 6);
  const allIds = await cardIds(page);
  const robotX = allIds[(await cardNames(page)).findIndex((name) => /RobotX/.test(name))];
  await page.waitForFunction(
    (id) => document.querySelector(`[data-source-preview="${id}"]`)?.getAttribute("data-rendered") === "true",
    robotX,
    { timeout: 30000 },
  );
  assert.ok(await sourceReady(page, robotX!), "uploaded font card paints real ink");

  await page.locator("[data-index-text]").fill("");
  await page.waitForFunction(() => document.querySelectorAll("[data-source-preview]").length === 0);
  assert.equal(await page.locator("[data-font-card]").count(), 6, "cards stay linked with empty sample");
  assert.equal(await page.locator("[data-card-error]").count(), 0, "empty sample errors nothing");
  await page.locator("[data-index-text]").fill(pangram);
  const restored = await cardIds(page);
  await page.waitForFunction(
    (count) => document.querySelectorAll('[data-source-preview][data-rendered="true"]').length >= count,
    restored.length,
    { timeout: 30000 },
  );
  for (const id of restored) {
    assert.ok(await sourceReady(page, id), `card ${id} repaints after restoring the exact sample`);
  }

  await page.locator("[data-index-text]").fill("􏿿􏿿");
  await page.waitForFunction(() => document.querySelectorAll("[data-card-error]").length === 6, null, {
    timeout: 30000,
  });
  assert.equal(
    await page.evaluate(() => document.querySelectorAll("[data-source-preview][data-rendered]").length),
    0,
    "failed renders leave no stale painted canvas",
  );
  await page.locator("[data-index-text]").fill(pangram);
  await page.waitForFunction(
    (count) => document.querySelectorAll('[data-source-preview][data-rendered="true"]').length >= count,
    6,
    { timeout: 30000 },
  );
  assert.equal(await page.locator("[data-card-error]").count(), 0, "errors clear on valid text");
  assert.ok(await sourceReady(page, robotX!), "uploaded card recovers with valid text");
  await context.close();
});

test("canvas appearance presets repaint with exact colors, geometry and persistence", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await bootLibrary(page, url);
  const ids = await renderedCardIds(page);
  await waitForSettled(page, ids);
  const id = ids[0]!;

  assert.equal(await page.locator("[data-site-header] h2", { hasText: "Canvas" }).textContent(), "Canvas");
  const presetLabel = page.locator('[data-site-header] label[for="canvas-preset"]');
  assert.equal(await presetLabel.textContent(), "Canvas preset");
  assert.match(await presetLabel.getAttribute("class") ?? "", /sr-only/, "preset label is sr-only, not duplicated");
  const presetBox = page.getByRole("combobox", { name: "Canvas preset" });
  assert.equal(await page.locator("[data-canvas-inverse]").getAttribute("role"), "switch", "inverse is a switch");
  assert.equal(await tooltipText(page, page.locator("[data-canvas-inverse]")), "Invert canvas colors");
  assert.deepEqual(await canvasAppearance(page), { palette: "black-white", inverse: false });
  const row = await page.evaluate(() => {
    const select = document.querySelector("[data-canvas-preset]")!.getBoundingClientRect();
    const inverse = document.querySelector("[data-canvas-inverse]")!.getBoundingClientRect();
    return { selectTop: select.top, selectBottom: select.bottom, inverseTop: inverse.top, inverseBottom: inverse.bottom };
  });
  assert.ok(row.selectTop < row.inverseBottom && row.inverseTop < row.selectBottom, "preset dropdown and inverse share one row");
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "canvas row does not overflow the page");

  const BLACK: RGB = [0, 0, 0];
  const WHITE: RGB = [255, 255, 255];
  const WARM_PAPER: RGB = [244, 236, 220];
  const WARM_INK: RGB = [26, 24, 21];
  const COOL_PAPER: RGB = [232, 240, 248];
  const COOL_INK: RGB = [27, 42, 58];

  const css = (channels: RGB): string => `rgb(${channels[0]}, ${channels[1]}, ${channels[2]})`;
  async function expectTriggerSwatch(paper: RGB, ink: RGB, label: string): Promise<void> {
    assert.deepEqual(
      await swatchStyle(page.locator("[data-canvas-preset] [data-canvas-swatch]")),
      { background: css(paper), color: css(ink) },
      label,
    );
    const layout = await page.locator("[data-canvas-preset]").evaluate((trigger) => {
      const value = trigger.querySelector("[data-canvas-value]")!;
      const swatch = trigger.querySelector("[data-canvas-swatch]")!;
      const frame = trigger.getBoundingClientRect();
      const box = value.getBoundingClientRect();
      const mark = swatch.getBoundingClientRect();
      return {
        triggerHeight: frame.height,
        valueHeight: box.height,
        valueTop: box.top,
        valueBottom: box.bottom,
        swatchTop: mark.top,
        swatchBottom: mark.bottom,
      };
    });
    assert.ok(layout.valueHeight <= layout.triggerHeight, `${label} value fits the trigger height`);
    assert.ok(
      layout.swatchTop < layout.valueBottom && layout.valueTop < layout.swatchBottom,
      `${label} swatch and name share one row`,
    );
  }
  async function expectSpecimenButton(paper: RGB, ink: RGB, label: string): Promise<void> {
    const expected = { background: css(paper), color: css(ink) };
    await page.waitForFunction(
      ({ fontId, style }) => {
        const button = document.querySelector(
          `[data-card-frame="${fontId}"] [data-add-variant="${fontId}"]`,
        );
        if (!button) return false;
        const computed = getComputedStyle(button);
        return computed.backgroundColor === style.background && computed.color === style.color;
      },
      { fontId: id, style: expected },
      { timeout: 3000 },
    );
    assert.deepEqual(
      await page.locator(`[data-card-frame="${id}"] [data-add-variant="${id}"]`).evaluate((element) => {
        const style = getComputedStyle(element);
        return { background: style.backgroundColor, color: style.color };
      }),
      expected,
      label,
    );
  }
  async function expectOptionSwatches(pairs: Array<{ name: string; paper: RGB; ink: RGB }>, label: string): Promise<void> {
    for (const pair of pairs) {
      assert.deepEqual(
        await swatchStyle(page.getByRole("option", { name: pair.name, exact: true }).locator("[data-canvas-swatch]")),
        { background: css(pair.paper), color: css(pair.ink) },
        `${label} ${pair.name} option swatch`,
      );
    }
  }
  const normal = [
    { name: "Neutral", paper: WHITE, ink: BLACK },
    { name: "Warm", paper: WARM_PAPER, ink: WARM_INK },
    { name: "Cool", paper: COOL_PAPER, ink: COOL_INK },
  ];
  async function expectColors(paper: RGB, ink: RGB, label: string): Promise<void> {
    const snapshot = await sourceSnapshot(page, id);
    assert.equal(snapshot.color, css(ink), `${label} source ink follows the palette`);
    assert.equal((await cardFrame(page, id)).background, css(paper), `${label} source paper follows the palette`);

  }

  const filter = await page.locator(`[data-source-preview="${id}"]`).evaluate(
    (element) => getComputedStyle(element).filter,
  );
  assert.equal(filter, "none", "no CSS filter recolors the canvas");
  await expectTriggerSwatch(WHITE, BLACK, "default Neutral trigger swatch");
  await expectColors(WHITE, BLACK, "default Neutral");
  const geometry = await cardGeometry(page, id);
  const defaultFrame = await cardFrame(page, id);
  assert.ok(defaultFrame.caption?.includes("Source"), "frame captions the base specimen");
  assert.ok(defaultFrame.caption?.includes("16 px"), "frame shows native base size and bit depth");
  assert.equal(defaultFrame.background, "rgb(255, 255, 255)", "frame fills the selected paper");
  assert.equal(defaultFrame.borderRadius, "12px", "frame keeps rounded corners");
  await expectSpecimenButton(WHITE, BLACK, "default Neutral specimen button");

  await presetBox.click();
  await expectOptionSwatches(normal, "normal");
  await page.getByRole("option", { name: "Warm", exact: true }).click();
  await waitForSettled(page, ids);
  assert.deepEqual(await canvasAppearance(page), { palette: "warm-paper", inverse: false });
  await expectColors(WARM_PAPER, WARM_INK, "Warm");
  await expectTriggerSwatch(WARM_PAPER, WARM_INK, "Warm trigger swatch follows polarity");
  const warmFrame = await cardFrame(page, id);
  assert.equal(warmFrame.background, "rgb(244, 236, 220)", "frame follows the Warm paper");
  assert.ok(warmFrame.caption?.includes("16 px"), "caption stays at native base size after preset change");
  await expectSpecimenButton(WARM_PAPER, WARM_INK, "Warm specimen button");
  assert.deepEqual(await cardGeometry(page, id), geometry, "preset keeps card geometry");

  await presetBox.click();
  await page.getByRole("option", { name: "Cool", exact: true }).click();
  await waitForSettled(page, ids);
  assert.deepEqual(await canvasAppearance(page), { palette: "cool-paper", inverse: false }, "dropdown selects a new preset");
  await expectColors(COOL_PAPER, COOL_INK, "Cool");
  await expectTriggerSwatch(COOL_PAPER, COOL_INK, "Cool trigger swatch");
  await expectSpecimenButton(COOL_PAPER, COOL_INK, "Cool specimen button");
  assert.deepEqual(await cardGeometry(page, id), geometry, "preset keeps card geometry");

  await page.locator("[data-canvas-inverse]").focus();
  await page.keyboard.press("Space");
  await waitForSettled(page, ids);
  assert.deepEqual(await canvasAppearance(page), { palette: "cool-paper", inverse: true }, "space toggles the inverse switch");
  await expectColors(COOL_INK, COOL_PAPER, "inverted Cool");
  await expectTriggerSwatch(COOL_INK, COOL_PAPER, "inverted trigger swatch swaps polarity");
  const inverseFrame = await cardFrame(page, id);
  assert.equal(inverseFrame.background, "rgb(27, 42, 58)", "frame follows the inverted paper");
  await expectSpecimenButton(COOL_INK, COOL_PAPER, "inverted specimen button");
  assert.deepEqual(await cardGeometry(page, id), geometry, "inverse keeps card geometry");
  const framedAdd = page.locator(`[data-card-frame="${id}"] [data-add-variant="${id}"]`);
  assert.equal(await framedAdd.count(), 1, "add variant lives inside the frame");
  assert.notEqual(
    await framedAdd.evaluate((element) => getComputedStyle(element).backgroundColor),
    await page.locator(`[data-delete-font="${id}"]`).evaluate((element) => getComputedStyle(element).backgroundColor),
    "specimen action differs from the global destructive button",
  );
  await presetBox.click();
  await expectOptionSwatches(
    normal.map((pair) => ({ name: pair.name, paper: pair.ink, ink: pair.paper })),
    "inverted",
  );
  await page.keyboard.press("Escape");

  await page.locator("[data-theme-toggle]").click();
  await waitForSettled(page, ids);
  await expectColors(COOL_INK, COOL_PAPER, "canvas palette ignores the app theme");

  await page.reload();
  await page.locator("[data-index-text]").waitFor();
  assert.deepEqual(await canvasAppearance(page), { palette: "cool-paper", inverse: true }, "appearance survives a reload");
  await waitForSettled(page, ids);
  await expectColors(COOL_INK, COOL_PAPER, "reloaded canvas keeps the inverted palette");

  await openNewVariant(page, ids[0]!);
  await page.waitForFunction(() => document.querySelector("[data-variant-editor]") !== null);
  await page.locator('[data-primary-nav="fonts"]').click();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  assert.deepEqual(await canvasAppearance(page), { palette: "cool-paper", inverse: true }, "appearance survives navigation");
  await waitForSettled(page, ids);
  await expectColors(COOL_INK, COOL_PAPER, "returned canvas keeps the inverted palette");
  await page.locator("[data-index-text]").fill("");
  await page.waitForFunction(() => document.querySelectorAll("[data-source-preview]").length === 0);
  assert.equal(await framedAdd.count(), 1, "add variant stays framed with an empty sample");
  assert.equal(await page.locator(`[data-add-variant="${id}"]`).count(), 1, "exactly one add button per font");
  assert.ok(await framedAdd.isEnabled(), "add variant stays enabled with an empty sample");
  await page.locator("[data-index-text]").focus();
  for (let tab = 0; tab < 20; tab += 1) {
    if (await framedAdd.evaluate((element) => document.activeElement === element)) break;
    await page.keyboard.press("Tab");
  }
  assert.ok(
    await framedAdd.evaluate((element) => document.activeElement === element),
    "add variant stays keyboard reachable with an empty sample",
  );
  assert.ok(
    await framedAdd.evaluate((element) => element.matches(":focus-visible")),
    "keyboard focus on add variant is visible",
  );
  assert.deepEqual(
    await framedAdd.evaluate((element) => {
      const style = getComputedStyle(element);
      return { style: style.outlineStyle, width: style.outlineWidth };
    }),
    { style: "solid", width: "2px" },
    "keyboard focus shows the specimen ink outline",
  );
  assert.ok((await openNewVariant(page, id)).length > 0, "framed add variant still creates and navigates");
  await context.close();
});

test("saved variants render their own specimens in the library", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.addInitScript({ content: WORKER_STATS_SCRIPT });
  const page = await context.newPage();
  await bootLibrary(page, url);
  const names = await cardNames(page);
  const ids = await renderedCardIds(page);
  const fontId = ids[names.findIndex((name) => /^Roboto Regular$/.test(name))]!;

  async function waitSaved(): Promise<void> {
    await page.waitForFunction(
      () => document.querySelector("[data-save-status]")?.textContent === "Saved",
      null,
      { timeout: 15000 },
    );
  }
  async function backToLibrary(variantCanvases: number): Promise<void> {
    await page.locator('[data-primary-nav="fonts"]').click();
    await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
    await waitForSettled(page, ids);
    await page.waitForFunction(
      (count) => document.querySelectorAll('[data-library-variant-canvas][data-rendered="true"]').length === count,
      variantCanvases,
      { timeout: 30000 },
    );
  }

  const first = await openNewVariant(page, fontId);
  await page.locator("[data-variant-name]").fill("Compact");
  await page.locator("[data-text]").fill("Compact specimen AA");
  await page.locator("[data-size-px]").fill("12");
  assert.equal(await page.locator("#rasterization").count(), 0);
  await page.getByRole("combobox", { name: "Fitting", exact: true }).click();
  await page.getByRole("option", { name: "Automatic", exact: true }).click();
  await waitSaved();

  await backToLibrary(1);
  const second = await openNewVariant(page, fontId);
  await page.locator("[data-variant-name]").fill("Soft gray");
  await page.locator("[data-text]").fill("Soft specimen BB");
  await page.locator("[data-size-px]").fill("24");
  const secondUrl = page.url();
  await createPalettePreset(page, url, { name: "Soft gray levels", bits: 3 });
  await page.goto(secondUrl, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelector("[data-variant-name]") !== null, null, {
    timeout: 20000,
  });
  await selectPalettePreset(page, "Soft gray levels");
  await page.locator("[data-kerning]").uncheck();
  await waitSaved();
  await backToLibrary(2);

  const frame = page.locator(`[data-card-frame="${fontId}"]`);
  assert.equal(await frame.locator("[data-variant-link]").count(), 2, "both variant links live in the same frame as Base");
  assert.equal(await frame.locator("[data-library-variant-row]").count(), 2);
  assert.equal(
    await page.locator(`[data-delete-variant="${first}"]`).evaluate((element) => getComputedStyle(element).backgroundColor),
    "rgba(0, 0, 0, 0)",
    "variant delete stays ghost until hovered",
  );
  const tint = page.locator(`[data-library-variant-tint="${second}"]`);
  assert.equal(await tint.evaluate((element) => getComputedStyle(element).opacity), "0", "tint rests invisible");
  const canvasWidthBefore = await page.locator(`[data-library-variant-canvas="${second}"]`).evaluate((element) => (element as HTMLCanvasElement).width);
  const pixelsBefore = await variantDigest(page, second);
  await page.locator(`[data-library-variant-row="${second}"]`).hover();
  assert.equal(await tint.evaluate((element) => getComputedStyle(element).opacity), "1", "row hover reveals the tint");
  assert.notEqual(
    await tint.evaluate((element) => getComputedStyle(element).backgroundColor),
    "rgba(0, 0, 0, 0)",
    "tint carries the ink wash",
  );
  assert.equal(
    await page.locator(`[data-library-variant-canvas="${second}"]`).evaluate((element) => (element as HTMLCanvasElement).width),
    canvasWidthBefore,
    "hover never relayouts the canvas",
  );
  assert.deepEqual(await variantDigest(page, second), pixelsBefore, "hover never repaints bitmap pixels");
  assert.equal(await page.locator(`[data-library-variant-caption="${first}"]`).innerText(), "12 px / 1-bit");
  assert.equal(await page.locator(`[data-library-variant-caption="${second}"]`).innerText(), "24 px / 3-bit");
  assert.equal(await page.locator("[data-library-variant-error]").count(), 0, "variant specimens report no errors");

  const monoDigest = await variantDigest(page, first);
  const grayDigest = await variantDigest(page, second);
  assert.ok(monoDigest.ink > 0 && grayDigest.ink > 0, "each variant paints its own text");
  assert.notDeepEqual(monoDigest, grayDigest, "variant bitmaps stay distinct");
  const grayTones = await page.evaluate((variantId) => {
    const canvas = document.querySelector(`[data-library-variant-canvas="${variantId}"]`) as HTMLCanvasElement;
    const data = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data;
    let mid = 0;
    let ink = 0;
    for (let i = 0; i < data.length; i += 4) {
      const paper = data[i] === 255 && data[i + 1] === 255 && data[i + 2] === 255;
      const solid = data[i] === 0 && data[i + 1] === 0 && data[i + 2] === 0;
      if (!paper && !solid) mid += 1;
      else if (solid) ink += 1;
    }
    return { mid, ink };
  }, second);
  assert.ok(grayTones.ink > 0 && grayTones.mid > 0, "the 3-bit specimen paints intermediate levels, not just paper and ink");

  const stats = await workerStats(page);
  const monoReq = stats.requests.filter(
    (request) => request.fontId === fontId && request.text === "Compact specimen AA" && (request.palette?.length ?? 0) === 2,
  ).at(-1);
  const grayReq = stats.requests.filter(
    (request) => request.fontId === fontId && request.text === "Soft specimen BB" && (request.palette?.length ?? 0) === 8,
  ).at(-1);
  assert.ok(monoReq, "native requests carry the first variant text with its palette");
  assert.ok(grayReq, "native requests carry the second variant text with its palette");
  assert.equal(monoReq!.sizePx, 12);
  assert.equal(monoReq!.outputBits, 1);
  assert.deepEqual(Object.keys(monoReq!.axes).sort(), ["wdth", "wght"]);
  assert.equal(monoReq!.spacing, 0, "stage comparisons use neutral tracking");
  assert.equal(monoReq!.kerning, true);
  assert.equal(monoReq!.stemFitting, null);
  assert.equal(monoReq!.renderer, undefined);
  assert.deepEqual(monoReq!.pipeline, { fitting: "upstream_mono", rasterization: "free_type_mono_terminals" });
  assert.equal(monoReq!.palette!.length, 2, "the mono request carries two palette entries");
  assert.equal(grayReq!.sizePx, 24);
  assert.equal(grayReq!.outputBits, 3);
  assert.deepEqual(Object.keys(grayReq!.axes).sort(), ["wdth", "wght"]);
  assert.equal(grayReq!.spacing, 0);
  assert.equal(grayReq!.kerning, false);
  assert.equal(grayReq!.stemFitting, null);
  assert.equal(grayReq!.renderer, undefined);
  assert.deepEqual(grayReq!.pipeline, { fitting: "upstream_mono", rasterization: "coverage" });
  assert.equal(grayReq!.palette!.length, 8, "the gray request carries eight palette levels");
  assert.deepEqual(grayReq!.palette![0], grayReq!.paper, "gray entry 0 is the paper");
  assert.deepEqual(grayReq!.palette![7], [0, 0, 0, 255], "gray entry 7 is the Neutral ink");

  await page.locator("[data-index-text]").fill("Changed library sample");
  await page.getByRole("button", { name: "32 px", exact: true }).click();
  await waitForSettled(page, ids);
  assert.deepEqual(await variantDigest(page, first), monoDigest, "library text leaves the first bitmap alone");
  assert.deepEqual(await variantDigest(page, second), grayDigest, "library base size leaves the second bitmap alone");
  for (const [variantId, text, size] of [[first, "Compact specimen AA", 12], [second, "Soft specimen BB", 24]] as const) {
    const key = JSON.parse(
      (await page.locator(`[data-library-variant-canvas="${variantId}"]`).getAttribute("data-render-key"))!,
    );
    assert.equal(key.text, text, `variant ${variantId} keeps its saved text`);
    assert.equal(key.size, size, `variant ${variantId} keeps its saved size`);
  }

  await page.getByRole("combobox", { name: "Canvas preset" }).click();
  await page.getByRole("option", { name: "Warm", exact: true }).click();
  await page.locator("[data-canvas-inverse]").click();
  await waitForSettled(page, ids);
  const warmInk: [number, number, number] = [26, 24, 21];
  const warmPaper: [number, number, number] = [244, 236, 220];
  assert.equal((await sourceSnapshot(page, fontId)).color, "rgb(244, 236, 220)");
  assert.equal((await cardFrame(page, fontId)).background, "rgb(26, 24, 21)");
  for (const variantId of [first, second]) {
    const match = await page.evaluate(({ id, paper, ink }) => {
      const canvas = document.querySelector(`[data-library-variant-canvas="${id}"]`) as HTMLCanvasElement;
      const data = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data;
      let paperCount = 0;
      let mid = 0;
      for (let i = 0; i < data.length; i += 4) {
        if (data[i] === paper[0] && data[i + 1] === paper[1] && data[i + 2] === paper[2]) paperCount += 1;
        else mid += 1;
      }
      return { paperCount, mid };
    }, { id: variantId, paper: warmInk, ink: warmPaper });
    assert.ok(match.paperCount > match.mid, `variant ${variantId} keeps the inverted paper dominant`);
    assert.ok(match.mid > 0, `variant ${variantId} still paints ink levels`);
  }
  assert.equal(await page.locator(`[data-library-variant-caption="${first}"]`).innerText(), "12 px / 1-bit");
  assert.equal(await page.locator(`[data-library-variant-caption="${second}"]`).innerText(), "24 px / 3-bit");

  assert.ok(
    (await page.locator(`[data-variant-link="${second}"]`).getAttribute("href"))?.endsWith(`/variant/${second}/`),
    "row link targets its variant route",
  );
  assert.equal(
    await page.locator(`[data-variant-link="${second}"]`).evaluate((element) => getComputedStyle(element).textDecorationLine),
    "none",
    "row link carries no underline",
  );
  await page.locator(`[data-library-variant-canvas="${second}"]`).click();
  await page.waitForFunction(() => document.querySelector("[data-variant-editor]") !== null);
  assert.equal(await page.locator("[data-variant-name]").inputValue(), "Soft gray", "canvas click opens its variant");
  await backToLibrary(2);
  await page.locator(`[data-variant-link="${first}"]`).focus();
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelector("[data-variant-editor]") !== null);
  assert.equal(await page.locator("[data-variant-name]").inputValue(), "Compact", "keyboard opens the focused row");
  await backToLibrary(2);

  const siblingBefore = await variantDigest(page, second);
  await page.locator(`[data-variant-link="${first}"]`).click();
  await page.waitForFunction(() => document.querySelector("[data-variant-editor]") !== null);
  assert.equal(await page.locator("[data-variant-name]").inputValue(), "Compact", "the title opens its own editor");
  await page.locator("[data-text]").fill("");
  await waitSaved();
  await backToLibrary(1);
  assert.equal(await page.locator(`[data-library-variant-canvas="${first}"]`).count(), 0, "an emptied variant unmounts only its bitmap");
  assert.equal(await page.locator(`[data-library-variant-caption="${first}"]`).innerText(), "12 px / 1-bit");
  assert.equal(await page.locator(`[data-variant-link="${first}"]`).getAttribute("aria-label"), "Compact");
  assert.deepEqual(await variantDigest(page, second), siblingBefore, "the sibling bitmap survives emptying its neighbor");

  await page.locator(`[data-delete-variant="${first}"]`).click();
  await page.waitForFunction(
    (variantId) => document.querySelector(`[data-library-variant-row="${variantId}"]`) === null,
    first,
    { timeout: 15000 },
  );
  assert.equal(await page.locator("[data-variant-editor]").count(), 0, "row Delete stays in the library");
  assert.equal(await page.locator(`[data-variant-link="${first}"]`).count(), 0, "the deleted variant link is gone");
  assert.equal(await page.locator(`[data-library-variant-canvas="${first}"]`).count(), 0, "the deleted variant canvas is gone");
  assert.equal(await page.locator(`[data-card-frame="${fontId}"] [data-variant-link]`).count(), 1, "the sibling link remains in the frame");
  assert.ok((await variantDigest(page, second)).ink > 0, "the sibling still renders after the delete");
  assert.equal(await page.locator(`[data-add-variant="${fontId}"]`).count(), 1, "the Add action remains after the delete");
  assert.ok(await sourceReady(page, fontId), "the Base specimen still renders after the delete");
  assert.equal((await cardIds(page)).length, 5, "deleting a variant never removes its font");

  const after = await workerStats(page);
  assert.equal(after.constructed, 1, "one shared worker serves variant specimens");
  for (const id of ids) {
    assert.equal(after.loads[id] ?? 0, id === fontId ? 1 : 0, `only the generated variant font loads natively`);
  }
  assert.equal(after.kerningRequests, 0, "variant specimens never scan kerning pairs");

  await page.reload();
  await page.locator("[data-index-text]").waitFor();
  await waitForSettled(page, ids);
  await page.waitForFunction(
    () => document.querySelectorAll('[data-library-variant-canvas][data-rendered="true"]').length === 1,
    null,
    { timeout: 30000 },
  );
  assert.equal(await page.locator(`[data-library-variant-row="${first}"]`).count(), 0, "the deleted row stays gone after reload");
  assert.equal(await page.locator(`[data-library-variant-caption="${second}"]`).innerText(), "24 px / 3-bit", "the sibling stays saved after reload");
  await context.close();
});

test("quick filter narrows the visible cards", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.addInitScript({ content: WORKER_STATS_SCRIPT });
  const page = await context.newPage();
  await bootLibrary(page, url);
  const ids = await renderedCardIds(page);
  const filter = page.locator("[data-library-filter]");
  assert.equal(await page.locator("[data-font-card]").count(), ids.length);

  async function expectFiltered(term: string): Promise<void> {
    await page.waitForFunction(
      (total) => {
        const cards = document.querySelectorAll("[data-font-card]");
        return cards.length > 0 && cards.length < total;
      },
      ids.length,
      { timeout: 15000 },
    );
    for (const name of await cardNames(page)) {
      assert.ok(name.toLowerCase().includes(term), `visible card matches, got ${name}`);
    }
  }
  async function expectUnfiltered(): Promise<void> {
    await page.waitForFunction(
      (total) => document.querySelectorAll("[data-font-card]").length === total,
      ids.length,
      { timeout: 15000 },
    );
  }

  await filter.fill("  RoBoTo  ");
  await expectFiltered("roboto");
  await filter.fill("Italic roboto");
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length === 1, null, {
    timeout: 15000,
  });
  assert.match((await cardNames(page))[0] ?? "", /italic/i, "multiword query matches one card");
  await filter.fill("");
  await expectUnfiltered();

  await filter.fill("zzz-no-such-font");
  await page.locator("[data-clear-filter]").waitFor();
  assert.match(
    (await page.locator("[data-clear-filter]").evaluate((element) => element.parentElement!.textContent)) ?? "",
    /No matching fonts/,
  );
  await page.locator("[data-clear-filter]").click();
  await expectUnfiltered();
  assert.equal(await filter.inputValue(), "");

  await filter.fill("roboto");
  await expectFiltered("roboto");
  const visibleId = (await cardIds(page))[0]!;
  await openNewVariant(page, visibleId);
  await page.waitForFunction(() => document.querySelector("[data-variant-editor]") !== null);
  await page.locator('[data-primary-nav="fonts"]').click();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  assert.equal(await filter.inputValue(), "roboto", "the filter survives a variant round trip");
  await expectFiltered("roboto");

  await filter.fill("");
  await page.setViewportSize({ width: 390, height: 844 });
  await waitForSettled(page, await cardIds(page));
  assert.ok(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    "no overflow with the filter on mobile",
  );
  const filterBox = await filter.boundingBox();
  assert.ok(filterBox !== null && filterBox.x >= 0 && filterBox.x + filterBox.width <= 390, "the filter fits the mobile header");

  const stats = await workerStats(page);
  assert.equal(stats.constructed, 1, "one shared worker across filtering");
  for (const id of ids) {
    assert.equal(stats.loads[id] ?? 0, id === visibleId ? 1 : 0, `only the opened variant font loads natively`);
  }
  await context.close();
});

test("desktop library scrolls only the font list", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 700 } });
  const page = await context.newPage();
  await bootLibrary(page, url);
  const ids = await renderedCardIds(page);
  await waitForSettled(page, ids);

  const pane = page.locator("[data-library-scroll]");
  const scrollable = await pane.evaluate((element) => element.scrollHeight - element.clientHeight);
  assert.ok(scrollable > 100, "a short desktop pane overflows its font list");
  const pageGeometry = await page.evaluate(() => ({
    height: window.innerHeight,
    documentHeight: document.documentElement.scrollHeight,
    rootHeight: document.querySelector("#root")!.getBoundingClientRect().height,
    rootTop: document.querySelector("#root")!.getBoundingClientRect().top,
    headerHeight: document.querySelector("[data-site-header]")!.getBoundingClientRect().height,
  }));
  assert.ok(pageGeometry.documentHeight <= pageGeometry.height,
    `the desktop page itself never scrolls: ${JSON.stringify(pageGeometry)}`);
  const chrome = await page.evaluate(() => ({
    headerTop: document.querySelector("[data-site-header]")!.getBoundingClientRect().top,
    sidebarTop: document.querySelector(".library-sidebar")!.getBoundingClientRect().top,
  }));
  await pane.evaluate((element) => {
    element.scrollTop = 200;
  });
  assert.ok(await pane.evaluate((element) => element.scrollTop > 0), "the font list scrolls");
  assert.deepEqual(
    await page.evaluate(() => ({
      headerTop: document.querySelector("[data-site-header]")!.getBoundingClientRect().top,
      sidebarTop: document.querySelector(".library-sidebar")!.getBoundingClientRect().top,
    })),
    chrome,
    "header and sidebar stay put while the list scrolls",
  );
  await page.setViewportSize({ width: 1280, height: 360 });
  const sidebar = page.locator(".library-sidebar");
  assert.ok(await sidebar.evaluate((element) => element.scrollHeight > element.clientHeight), "short desktop controls can scroll when needed");
  await page.locator("[data-import-font]").scrollIntoViewIfNeeded();
  assert.ok(await sidebar.evaluate((element) => element.scrollTop > 0), "the import control remains reachable on a short desktop");

  await page.setViewportSize({ width: 390, height: 844 });
  await waitForSettled(page, await cardIds(page));
  assert.ok(
    await page.evaluate(() => document.documentElement.scrollHeight > window.innerHeight),
    "narrow pages keep normal document flow",
  );
  await page.evaluate(() => window.scrollTo(0, 999999));
  assert.equal(await page.locator("[data-site-header]").evaluate((element) => element.getBoundingClientRect().top), 0, "the header stays sticky in narrow document flow");
  await context.close();
});

test("header Canvas controls follow every preview and stay usable at narrow widths", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await bootLibrary(page, url);
  const ids = await renderedCardIds(page);
  assert.equal(await page.locator("aside [data-canvas-preset]").count(), 0);
  assert.equal(await page.locator("[data-site-header] [data-global-canvas]").count(), 1);
  async function checkHeader(): Promise<void> {
    for (const width of [320, 640, 768, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      assert.ok(await page.evaluate(() => {
        const elements = ["[data-global-canvas]", "[data-global-zoom]", "[data-theme-toggle]"];
        return document.documentElement.scrollWidth <= innerWidth && elements.every((selector) => {
          const box = document.querySelector(selector)!.getBoundingClientRect();
          return box.width > 0 && box.left >= 0 && box.right <= innerWidth;
        });
      }), `header controls fit at ${width}px`);
    }
  }
  await checkHeader();
  await page.getByRole("combobox", { name: "Canvas preset" }).click();
  await page.getByRole("option", { name: "Warm", exact: true }).click();
  await page.locator("[data-canvas-inverse]").click();
  await page.goto(`${url}#/font/${ids[0]}/?v=1`, { waitUntil: "networkidle" });
  await page.waitForFunction(canvasRendered);
  assert.deepEqual(await canvasAppearance(page), { palette: "warm-paper", inverse: true });
  await page.waitForFunction(() => {
    const canvas = document.querySelector(".interactive-canvas") as HTMLCanvasElement;
    if (canvas.dataset.rendered !== "true") return false;
    const pixels = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data;
    let ink = 0;
    for (let offset = 0; offset < pixels.length; offset += 4) {
      const paper = pixels[offset] === 26 && pixels[offset + 1] === 24 && pixels[offset + 2] === 21;
      const mark = pixels[offset] === 244 && pixels[offset + 1] === 236 && pixels[offset + 2] === 220;
      if (!paper && !mark) return false;
      if (mark) ink += 1;
    }
    return ink > 100;
  });
  await checkHeader();
  await page.locator("[data-save-variant]").click();
  await page.locator("[data-variant-name]").waitFor();
  await page.waitForFunction(canvasRendered);
  await checkHeader();
  await page.getByRole("combobox", { name: "Canvas preset" }).click();
  await page.getByRole("option", { name: "Cool", exact: true }).click();
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(canvasRendered);
  assert.deepEqual(await canvasAppearance(page), { palette: "cool-paper", inverse: true });
  const second = await context.newPage();
  await bootLibrary(second, url);
  assert.deepEqual(await canvasAppearance(second), { palette: "cool-paper", inverse: true });
  await second.locator("[data-canvas-inverse]").click();
  await page.waitForFunction(() => document.querySelector("[data-canvas-inverse]")?.getAttribute("aria-checked") === "false");
  await context.close();
});

 test("source fonts never flash a fallback and release faces when cards unmount", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.addInitScript(() => {
    const w = window as unknown as { releaseSource: (() => void)[] };
    w.releaseSource = [];
    const load = FontFace.prototype.load;
    FontFace.prototype.load = function () {
      if (!this.family.startsWith("source-")) return load.call(this);
      return new Promise<FontFace>((resolve, reject) => {
        load.call(this).then((face) => { w.releaseSource.push(() => resolve(face)); }, reject);
      });
    };
  });
  await bootLibrary(page, url);
  await page.waitForFunction(() => (window as unknown as { releaseSource: unknown[] }).releaseSource.length === 5);
  assert.equal(await page.locator("[data-source-preview]").count(), 0, "no fallback text is shown while FontFace loads");
  await page.locator("[data-library-filter]").fill("italic");
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length === 1);
  const release = () => page.evaluate(() => (window as unknown as { releaseSource: (() => void)[] }).releaseSource.splice(0).forEach((resume) => resume()));
  await release();
  await page.waitForFunction(() => document.querySelectorAll("[data-source-preview]").length === 1);
  assert.equal(await page.evaluate(() => [...document.fonts].filter((face) => face.family.startsWith("source-")).length), 1,
    "late font completions cannot register unmounted cards");
  await page.locator("[data-library-filter]").fill("");
  await page.waitForFunction(() => (window as unknown as { releaseSource: unknown[] }).releaseSource.length === 4);
  await release();
  await renderedCardIds(page);
  assert.equal(await page.evaluate(() => [...document.fonts].filter((face) => face.family.startsWith("source-")).length), 5);
});
