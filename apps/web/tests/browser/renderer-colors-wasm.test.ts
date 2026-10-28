import assert from "node:assert/strict";
import test from "node:test";
import {
  bootLibrary,
  browserAvailable,
  buildApp,
  cardIds,
  openNewVariant,
  canvasRendered,
  launch,
  servePrefix,
} from "../helpers/spa-helpers.ts";

const WORKER_CAPTURE_SCRIPT = `
window.__colorWorker = null;
window.__colorSpecs = {};
const RealWorker = window.Worker;
window.Worker = function (url, options) {
  const worker = new RealWorker(url, options);
  window.__colorWorker = worker;
  const post = worker.postMessage.bind(worker);
  worker.postMessage = (message, transfer) => {
    if (message && typeof message === "object" && message.kind === "render" && message.spec) {
      // Color-contract requests use the general native API, independent of
      // the editor's fitting, scanner and display palette selections.
      const base = { ...message.spec, renderer: "baseline", hinting: "none" };
      for (const key of ["pipeline", "stem_fitting", "mono_raster", "palette"]) delete base[key];
      window.__colorSpecs[message.fontId] = base;
    }
    return post(message, transfer);
  };
  return worker;
};
`;

test("real worker applies singleton ink over transparency exactly", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript({ content: WORKER_CAPTURE_SCRIPT });
  await bootLibrary(page, url);
  const ids = await cardIds(page);
  await openNewVariant(page, ids[0]!);
  await page.waitForFunction(canvasRendered);
  const spec = await page.evaluate((fontId) => {
    const specs = (window as unknown as { __colorSpecs: Record<string, Record<string, unknown>> }).__colorSpecs;
    return specs[fontId] as Record<string, unknown>;
  }, ids[0] as string);
  assert.ok(spec, "a card render spec was captured");

  const summary = await page.evaluate(async ({ fontId, base }) => {
    const worker = (window as unknown as { __colorWorker: Worker }).__colorWorker;
    const result = await new Promise<{ value: { width: number; height: number; pixels: ArrayBuffer } }>(
      (resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("render timeout")), 20000);
        const handler = (event: MessageEvent): void => {
          if (event.data && event.data.seq === 1000001) {
            worker.removeEventListener("message", handler);
            clearTimeout(timer);
            if (event.data.ok) resolve(event.data);
            else reject(new Error(event.data.error));
          }
        };
        worker.addEventListener("message", handler);
        worker.postMessage({
          seq: 1000001,
          kind: "render",
          fontId,
          token: 424242,
          spec: { ...base, text: "Ag", size_px: 16, axes: {}, foreground: [255, 0, 0, 255], background: [0, 0, 0, 0] },
        });
      },
    );
    const view = new Uint8ClampedArray(result.value.pixels);
    let ink = 0;
    let mismatches = 0;
    let background = 0;
    for (let i = 0; i < view.length; i += 4) {
      const a = view[i + 3] as number;
      if (a === 0 && view[i] === 0 && view[i + 1] === 0 && view[i + 2] === 0) {
        background += 1;
      } else if (a === 255 && view[i] === 255 && view[i + 1] === 0 && view[i + 2] === 0) {
        ink += 1;
      } else {
        mismatches += 1;
      }
    }
    return { ink, mismatches, background };
  }, { fontId: ids[0] as string, base: spec });
  assert.ok(summary.ink > 50, `red ink pixels render, got ${summary.ink}`);
  assert.equal(summary.mismatches, 0, "every ink pixel is exactly opaque red");
  assert.ok(summary.background > 0, "transparent background stays untouched");
  assert.deepEqual(errors, []);
  await page.close();
});

test("real worker applies explicit gray levels verbatim over transparency", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript({ content: WORKER_CAPTURE_SCRIPT });
  await bootLibrary(page, url);
  const ids = await cardIds(page);
  await openNewVariant(page, ids[0]!);
  await page.waitForFunction(canvasRendered);
  const palette = Array.from({ length: 8 }, (_, i) => [20 * i, 200, 30, 32 * i]);
  const summary = await page.evaluate(async ({ fontId, entries }) => {
    const worker = (window as unknown as { __colorWorker: Worker }).__colorWorker;
    const specs = (window as unknown as { __colorSpecs: Record<string, Record<string, unknown>> }).__colorSpecs;
    const base = specs[fontId] as Record<string, unknown>;
    const request: Record<string, unknown> = {
      ...base,
      text: "Ag",
      size_px: 16,
      axes: {},
      output_bits: 3,
      gray_gamma: 2.2,
      foreground: [36, 40, 43, 255],
      background: [0, 0, 0, 0],
      palette: entries,
    };
    delete request.stem_fitting;
    const result = await new Promise<{ value: { width: number; height: number; pixels: ArrayBuffer } }>(
      (resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("render timeout")), 20000);
        const handler = (event: MessageEvent): void => {
          if (event.data && event.data.seq === 1000002) {
            worker.removeEventListener("message", handler);
            clearTimeout(timer);
            if (event.data.ok) resolve(event.data);
            else reject(new Error(event.data.error));
          }
        };
        worker.addEventListener("message", handler);
        worker.postMessage({ seq: 1000002, kind: "render", fontId, token: 424243, spec: request });
      },
    );
    const view = new Uint8ClampedArray(result.value.pixels);
    let mismatches = 0;
    const alphas = new Set<number>();
    for (let i = 0; i < view.length; i += 4) {
      const px: [number, number, number, number] = [view[i] as number, view[i + 1] as number, view[i + 2] as number, view[i + 3] as number];
      if (px[3] === 0) continue;
      alphas.add(px[3]);
      const entry = (entries as number[][]).find((candidate) => candidate[3] === px[3]);
      if (!entry || entry[0] !== px[0] || entry[1] !== px[1] || entry[2] !== px[2]) mismatches += 1;
    }
    return { mismatches, distinctAlphas: [...alphas].sort((a, b) => a - b) };
  }, { fontId: ids[0] as string, entries: palette });
  assert.equal(summary.mismatches, 0, "every pixel matches its coverage level entry exactly");
  assert.ok(
    summary.distinctAlphas.filter((alpha) => alpha > 0).length >= 2,
    `coverage levels vary, got ${summary.distinctAlphas}`,
  );
  assert.deepEqual(errors, []);
  await page.close();
});

test("real worker applies uneven opaque levels verbatim over paper", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript({ content: WORKER_CAPTURE_SCRIPT });
  await bootLibrary(page, url);
  const ids = await cardIds(page);
  await openNewVariant(page, ids[0]!);
  await page.waitForFunction(canvasRendered);
  // Fully opaque yet pairwise distinct entries: no coverage alpha may
  // reshape them, so every pixel must equal one entry byte-for-byte.
  const palette = [
    [70, 130, 180, 255],
    [200, 30, 30, 255], [30, 90, 200, 255], [30, 180, 90, 255], [150, 60, 200, 255],
    [200, 150, 30, 255], [90, 200, 180, 255], [40, 50, 60, 255],
  ];
  const summary = await page.evaluate(async ({ fontId, entries }) => {
    const worker = (window as unknown as { __colorWorker: Worker }).__colorWorker;
    const specs = (window as unknown as { __colorSpecs: Record<string, Record<string, unknown>> }).__colorSpecs;
    const base = specs[fontId] as Record<string, unknown>;
    const request: Record<string, unknown> = {
      ...base,
      text: "Ag",
      size_px: 16,
      axes: {},
      output_bits: 3,
      gray_gamma: 2.2,
      background: entries[0],
      palette: entries,
    };
    delete request.stem_fitting;
    const result = await new Promise<{ value: { width: number; height: number; pixels: ArrayBuffer } }>(
      (resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("render timeout")), 20000);
        const handler = (event: MessageEvent): void => {
          if (event.data && event.data.seq === 1000004) {
            worker.removeEventListener("message", handler);
            clearTimeout(timer);
            if (event.data.ok) resolve(event.data);
            else reject(new Error(event.data.error));
          }
        };
        worker.addEventListener("message", handler);
        worker.postMessage({ seq: 1000004, kind: "render", fontId, token: 424245, spec: request });
      },
    );
    const view = new Uint8ClampedArray(result.value.pixels);
    let ink = 0;
    let paper = 0;
    let mismatches = 0;
    for (let i = 0; i < view.length; i += 4) {
      const px = [view[i] as number, view[i + 1] as number, view[i + 2] as number, view[i + 3] as number];
      const match = (entries as number[][]).findIndex(
        (entry) => entry[0] === px[0] && entry[1] === px[1] && entry[2] === px[2] && entry[3] === px[3],
      );
      if (match < 0) mismatches += 1;
      else if (match === 0) paper += 1;
      else ink += 1;
    }
    return { ink, paper, mismatches };
  }, { fontId: ids[0] as string, entries: palette });
  assert.ok(summary.ink > 50, `uneven ink pixels render, got ${summary.ink}`);
  assert.ok(summary.paper > 0, "zero coverage leaves the paper entry untouched");
  assert.equal(summary.mismatches, 0, "every pixel equals one palette entry exactly");
  assert.deepEqual(errors, []);
  await page.close();
});

test("real worker blends partial levels opaque over paper", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript({ content: WORKER_CAPTURE_SCRIPT });
  await bootLibrary(page, url);
  const ids = await cardIds(page);
  await openNewVariant(page, ids[0]!);
  await page.waitForFunction(canvasRendered);
  const palette = Array.from({ length: 8 }, (_, i) => [20 * i, 200, 30, 32 * i]);
  const summary = await page.evaluate(async ({ fontId, entries }) => {
    const worker = (window as unknown as { __colorWorker: Worker }).__colorWorker;
    const specs = (window as unknown as { __colorSpecs: Record<string, Record<string, unknown>> }).__colorSpecs;
    const base = specs[fontId] as Record<string, unknown>;
    const request: Record<string, unknown> = {
      ...base,
      text: "Ag",
      size_px: 16,
      axes: {},
      output_bits: 3,
      gray_gamma: 2.2,
      foreground: [36, 40, 43, 255],
      background: [255, 255, 255, 255],
      palette: entries,
    };
    delete request.stem_fitting;
    const result = await new Promise<{ value: { width: number; height: number; pixels: ArrayBuffer } }>(
      (resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("render timeout")), 20000);
        const handler = (event: MessageEvent): void => {
          if (event.data && event.data.seq === 1000003) {
            worker.removeEventListener("message", handler);
            clearTimeout(timer);
            if (event.data.ok) resolve(event.data);
            else reject(new Error(event.data.error));
          }
        };
        worker.addEventListener("message", handler);
        worker.postMessage({ seq: 1000003, kind: "render", fontId, token: 424244, spec: request });
      },
    );
    const view = new Uint8ClampedArray(result.value.pixels);
    let transparent = 0;
    let levelOne = 0;
    for (let i = 0; i < view.length; i += 4) {
      const px: [number, number, number, number] = [view[i] as number, view[i + 1] as number, view[i + 2] as number, view[i + 3] as number];
      if (px[3] !== 255) transparent += 1;
      // Level 1 entry [20,200,30,32] blended over white: [226,248,227,255].
      if (px[3] === 255
        && Math.abs(px[0] - 226) <= 1 && Math.abs(px[1] - 248) <= 1 && Math.abs(px[2] - 227) <= 1) {
        levelOne += 1;
      }
    }
    return { transparent, levelOne, total: view.length / 4 };
  }, { fontId: ids[0] as string, entries: palette });
  assert.equal(summary.transparent, 0, "partial levels over opaque paper stay opaque");
  assert.ok(summary.levelOne > 0, "level 1 blends toward paper instead of staying translucent");
  assert.deepEqual(errors, []);
  await page.close();
});
