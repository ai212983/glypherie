import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import test from "node:test";
import {
  bootLibrary,
  browserAvailable,
  buildApp,
  canvasRendered,
  cardDigest,
  cardIds,
  cardInk,
  cardNames,
  fontDir,
  launch,
  mutatedUploadBytes,
  openNewVariant,
  servePrefix,
  setRange,
} from "../helpers/spa-helpers.ts";
import type { Page } from "playwright-core";

type Digest = { hash: number; ink: number };

async function renderedCardIds(page: Page): Promise<string[]> {
  await page.waitForFunction(
    (count) => document.querySelectorAll('[data-card-canvas][data-rendered="true"]').length >= count,
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

async function digests(page: Page, ids: string[]): Promise<Digest[]> {
  return Promise.all(ids.map((id) => cardDigest(page, id)));
}

async function waitForSettled(page: Page, ids: string[]): Promise<Digest[]> {
  await page.waitForFunction((fontIds) => {
    const text = (document.querySelector("[data-index-text]") as HTMLInputElement).value;
    const zoom = Number((document.querySelector("[data-index-zoom]") as HTMLInputElement).value);
    return fontIds.every((id) => {
      const preview = document.querySelector(`[data-card-preview="${id}"]`) as HTMLElement | null;
      const canvas = preview?.querySelector("canvas");
      if (!preview || canvas?.dataset.rendered !== "true" || !canvas.dataset.renderKey) return false;
      const rendered = JSON.parse(canvas.dataset.renderKey);
      return rendered.font === id && rendered.text === text && rendered.zoom === zoom
        && rendered.width === Math.ceil(preview.clientWidth / zoom);
    });
  }, ids, { timeout: 30000 });
  return digests(page, ids);
}

const WORKER_STATS_SCRIPT = `
window.__workerStats = { constructed: 0, loads: {}, specs: {} };
const RealWorker = window.Worker;
window.Worker = function (url, options) {
  window.__workerStats.constructed += 1;
  const worker = new RealWorker(url, options);
  const post = worker.postMessage.bind(worker);
  worker.postMessage = (message, transfer) => {
    if (message && typeof message === "object") {
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
        };
      }
    }
    return post(message, transfer);
  };
  return worker;
};
`;

interface WorkerStats {
  constructed: number;
  loads: Record<string, number>;
  specs: Record<string, { width: number; sizePx: number; axes: Record<string, number>; renderer: string }>;
}

async function workerStats(page: Page): Promise<WorkerStats> {
  return page.evaluate(() => (window as unknown as { __workerStats: WorkerStats }).__workerStats);
}

test("every card renders the shared sample with real ink", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await bootLibrary(page, url);
  const ids = await renderedCardIds(page);
  assert.equal(ids.length, 5);
  for (const id of ids) {
    const ink = await cardInk(page, id);
    assert.ok(ink > 100, `card ${id} paints real ink, got ${ink}`);
  }
  assert.deepEqual(errors, []);

  await page.setViewportSize({ width: 390, height: 844 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert.ok(overflow <= 0, `no horizontal overflow on mobile, got ${overflow}px`);
  const tabbable = await page.evaluate(
    () => document.querySelectorAll("[data-card-preview] [tabindex]").length,
  );
  assert.equal(tabbable, 0, "card previews add no nested tab stops");
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
    assert.ok(afterText[index]!.ink > 0, `card ${id} paints ink for new text`);
  }

  const heightsBefore = await previewHeights(page);
  await setRange(page, "[data-index-zoom]", "4");
  await page.waitForFunction(
    (value) => document.querySelector("#index-zoom-value")?.textContent === value,
    "4×",
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
  const fullHeights = await page.evaluate(() => {
    const canvases = [...document.querySelectorAll("[data-card-canvas]")] as HTMLCanvasElement[];
    return canvases.map((canvas) => ({
      height: canvas.height,
      full: Number(canvas.dataset.fullHeight ?? -1),
    }));
  });
  for (const [index, id] of ids.entries()) {
    assert.ok(
      longHeights[index]! > shortHeights[index]!,
      `card ${id} extends for wrapped text (${shortHeights[index]} to ${longHeights[index]})`,
    );
    assert.ok((await cardInk(page, id)) > 100, `card ${id} paints the long sample`);
    assert.ok(
      fullHeights[index]!.height >= fullHeights[index]!.full && fullHeights[index]!.full > 0,
      `card ${id} buffer holds the full laid-out height`,
    );
  }
  const clipped = await page.evaluate(() => {
    const previews = [...document.querySelectorAll("[data-card-preview]")] as HTMLElement[];
    return previews.filter((preview) => preview.scrollHeight - preview.clientHeight > 1).length;
  });
  assert.equal(clipped, 0, "wrapped text is fully contained, never clipped");

  await setRange(page, "[data-index-zoom]", "4");
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
  assert.equal(await page.evaluate(() => [...document.querySelectorAll<HTMLCanvasElement>("[data-card-canvas]")]
    .every((canvas) => canvas.height >= Number(canvas.dataset.fullHeight) * 4)), true,
  "mobile previews contain the full wrapped layout at zoom 4");
  await page.locator("[data-index-text]").fill("Pack my box with five dozen liquor jugs. ".repeat(200));
  await waitForSettled(page, ids);
  assert.equal(await page.locator("[data-card-limit]").count(), ids.length,
    "the renderer's allocation limit is reported rather than silently clipping an extreme sample");
});

test("index settings survive a detail round trip on one shared worker", { skip: !browserAvailable }, async (t) => {
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
  await setRange(page, "[data-index-zoom]", "3");
  await page.waitForFunction(
    (value) => document.querySelector("#index-zoom-value")?.textContent === value,
    "3×",
  );
  const settled = await waitForSettled(page, ids);
  const stats = await workerStats(page);
  assert.equal(stats.constructed, 1, "one shared worker serves the app");
  for (const id of ids) {
    assert.equal(stats.loads[id], 1, `font ${id} loads exactly once`);
  }
  const roboto = ids[names.findIndex((name) => /^Roboto Regular$/.test(name))];
  assert.equal(stats.specs[roboto!]!.sizePx, 16, "cards render at the constant request size");
  assert.deepEqual(
    Object.keys(stats.specs[roboto!]!.axes).sort(),
    ["wdth", "wght"],
    "card spec carries the font metadata default axes",
  );
  assert.equal(stats.specs[roboto!]!.renderer, "candidate");
  const previewWidth = await page.evaluate(() => {
    const preview = document.querySelector("[data-card-preview]") as HTMLElement | null;
    return preview?.getBoundingClientRect().width ?? 0;
  });
  assert.ok(
    Math.abs(stats.specs[roboto!]!.width * 3 - previewWidth) <= 3,
    `card spec wraps at the zoom-scaled logical width (spec ${stats.specs[roboto!]!.width}, container ${previewWidth})`,
  );
  const literata = ids[names.findIndex((name) => /^Literata/.test(name))];
  assert.ok("opsz" in (stats.specs[literata!]!.axes), "Literata card spec carries its optical axis");

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
  await page.locator("[data-all-fonts]").click();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  assert.equal(await page.locator("[data-index-text]").inputValue(), "Qq Rr Zz");
  assert.equal(await page.locator("#index-zoom-value").textContent(), "3×");
  const returned = await waitForSettled(page, ids);
  assert.deepEqual(returned, settled, "card previews restore from the shared worker cache");
  const after = await workerStats(page);
  assert.equal(after.constructed, 1, "no second worker across the round trip");
  for (const id of ids) {
    assert.equal(after.loads[id], 1, `font ${id} never reloads across the round trip`);
  }
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
    await page.evaluate(() => document.querySelectorAll("[data-card-canvas]").length),
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
    (id) => document.querySelector(`[data-card-canvas="${id}"]`)?.getAttribute("data-rendered") === "true",
    robotX,
    { timeout: 30000 },
  );
  assert.ok((await cardInk(page, robotX!)) > 100, "uploaded font card paints real ink");

  await page.locator("[data-index-text]").fill("");
  await page.waitForFunction(() => document.querySelectorAll("[data-card-canvas]").length === 0);
  assert.equal(await page.locator("[data-font-card]").count(), 6, "cards stay linked with empty sample");
  assert.equal(await page.locator("[data-card-error]").count(), 0, "empty sample errors nothing");
  await page.locator("[data-index-text]").fill(pangram);
  const restored = await cardIds(page);
  await page.waitForFunction(
    (count) => document.querySelectorAll('[data-card-canvas][data-rendered="true"]').length >= count,
    restored.length,
    { timeout: 30000 },
  );
  for (const id of restored) {
    assert.ok((await cardInk(page, id)) > 100, `card ${id} repaints after restoring the exact sample`);
  }

  await page.locator("[data-index-text]").fill("􏿿􏿿");
  await page.waitForFunction(() => document.querySelectorAll("[data-card-error]").length === 6, null, {
    timeout: 30000,
  });
  assert.equal(
    await page.evaluate(() => document.querySelectorAll("[data-card-canvas][data-rendered]").length),
    0,
    "failed renders leave no stale painted canvas",
  );
  await page.locator("[data-index-text]").fill(pangram);
  await page.waitForFunction(
    (count) => document.querySelectorAll('[data-card-canvas][data-rendered="true"]').length >= count,
    6,
    { timeout: 30000 },
  );
  assert.equal(await page.locator("[data-card-error]").count(), 0, "errors clear on valid text");
  assert.ok((await cardInk(page, robotX!)) > 100, "uploaded card recovers with valid text");
  await context.close();
});
