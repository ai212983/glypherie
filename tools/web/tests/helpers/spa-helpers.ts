import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import type { TestContext } from "node:test";
import { fileURLToPath } from "node:url";
import { chromium, type Browser, type Page } from "playwright-core";

export const webRoot: string = fileURLToPath(new URL("../..", import.meta.url));
export const repoRoot: string = path.resolve(webRoot, "..", "..");
export const fontDir: string = path.join(repoRoot, "fonts");

export const sha256 = (bytes: Uint8Array | string): string =>
  createHash("sha256").update(bytes).digest("hex");

export async function buildApp(t: TestContext): Promise<string> {
  const output = await fs.mkdtemp(path.join(os.tmpdir(), "font-spa-"));
  t.after(() => fs.rm(output, { recursive: true, force: true }));
  execFileSync("npm", ["run", "build", "--", "--outDir", output], { cwd: webRoot, stdio: "pipe" });
  return output;
}

const MIME: Record<string, string> = {
  ".html": "text/html",
  ".css": "text/css",
  ".js": "text/javascript",
  ".json": "application/json",
  ".wasm": "application/wasm",
  ".ttf": "font/ttf",
  ".otf": "font/otf",
  ".txt": "text/plain",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".webmanifest": "application/manifest+json",
};

export async function servePrefix(t: TestContext, root: string): Promise<string> {
  const server = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url ?? "/", "http://localhost");
      if (!url.pathname.startsWith("/preview/")) throw new Error("Unknown prefix");
      let relative = decodeURIComponent(url.pathname.slice("/preview/".length));
      if (!relative || relative.endsWith("/")) relative += "index.html";
      const file = path.resolve(root, relative);
      if (path.relative(root, file).startsWith("..")) throw new Error("Invalid path");
      const bytes = await fs.readFile(file);
      response.writeHead(200, { "Content-Type": MIME[path.extname(file)] ?? "application/octet-stream" });
      response.end(bytes);
    } catch {
      response.writeHead(404);
      response.end();
    }
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise<void>((resolve) => server.close(() => resolve())));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Test server did not bind a port.");
  return `http://127.0.0.1:${address.port}/preview/`;
}

export const browserPath: string = process.env.WEB_TEST_BROWSER ?? "/opt/google/chrome/chrome";
export const browserAvailable: boolean = await fs.access(browserPath).then(() => true, () => false);

export async function launch(t: TestContext): Promise<Browser> {
  const browser = await chromium.launch({ executablePath: browserPath, headless: true });
  t.after(() => browser.close());
  return browser;
}

export function canvasRendered(): boolean {
  return (document.querySelector(".interactive-canvas") as HTMLElement | null)?.dataset.rendered === "true";
}

export async function canvasPixels(page: Page): Promise<{ width: number; height: number; ink: number }> {
  return page.evaluate(() => {
    const canvas = document.querySelector(".interactive-canvas") as HTMLCanvasElement | null;
    if (!canvas) throw new Error("Preview canvas is missing.");
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas 2D context unavailable.");
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let ink = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (data[i] !== 255 || data[i + 1] !== 255 || data[i + 2] !== 255) ink += 1;
    }
    return { width: canvas.width, height: canvas.height, ink };
  });
}

/**
 * Wait for the library index (font cards) to boot from an empty profile. The
 * font list stays uninitialized until seeding settles, so the first paint
 * already carries the full catalog.
 */
export async function bootLibrary(page: Page, url: string): Promise<void> {
  await page.goto(url, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
}

/** Wait for an unsaved font preview (font switcher plus rendered specimen). */
export async function bootDetail(page: Page, url: string): Promise<void> {
  await page.goto(url, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelectorAll("#font-select option").length > 0);
  await page.waitForFunction(canvasRendered);
}

/** Wait for a saved variant editor plus its rendered specimen. */
export async function bootVariant(page: Page, url: string): Promise<void> {
  await page.goto(url, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelector("[data-variant-editor]") !== null);
  await page.waitForFunction(canvasRendered);
}

export interface HashLocation {
  path: string;
  search: string;
}

/** Current hash route: path plus inner query (font identity lives in the path, never in outer search). */
export async function hashLocation(page: Page): Promise<HashLocation> {
  return page.evaluate(() => {
    const hash = window.location.hash;
    const raw = hash.startsWith("#") ? hash.slice(1) : hash;
    const query = raw.indexOf("?");
    if (query < 0) return { path: raw, search: "" };
    return { path: raw.slice(0, query), search: raw.slice(query + 1) };
  });
}

export async function hashPath(page: Page): Promise<string> {
  return (await hashLocation(page)).path;
}

export async function hashParam(page: Page, key: string): Promise<string | null> {
  return new URLSearchParams((await hashLocation(page)).search).get(key);
}

/** Card display names in library order. */
export async function cardNames(page: Page): Promise<string[]> {
  return page.locator("[data-font-name]").evaluateAll((names) =>
    names.map((name) => name.textContent ?? ""),
  );
}

/** Set a range slider through React's change handling. */
export async function setRange(page: Page, selector: string, value: string): Promise<void> {
  await page.locator(selector).evaluate((element, next) => {
    if (!(element instanceof HTMLInputElement)) throw new Error("Range element is missing.");
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(element, next);
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  }, value);
}

/** Ink pixel count of one card preview canvas (0 when not yet painted). */
export async function cardInk(page: Page, fontId: string): Promise<number> {
  return page.evaluate((id) => {
    const canvas = document.querySelector(`[data-card-canvas="${id}"]`) as HTMLCanvasElement | null;
    if (!canvas || canvas.width === 0) return 0;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas 2D context unavailable.");
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let ink = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (data[i] !== 255 || data[i + 1] !== 255 || data[i + 2] !== 255) ink += 1;
    }
    return ink;
  }, fontId);
}

/** FNV-1a digest plus ink of one card preview canvas for change detection. */
export async function cardDigest(page: Page, fontId: string): Promise<{ hash: number; ink: number }> {
  return page.evaluate((id) => {
    const canvas = document.querySelector(`[data-card-canvas="${id}"]`) as HTMLCanvasElement | null;
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
  }, fontId);
}

/** Card content ids in library order. */
export async function cardIds(page: Page): Promise<string[]> {
  return page.locator("[data-font-card]").evaluateAll((cards) =>
    cards.map((card) => card.getAttribute("data-font-card") ?? ""),
  );
}

/** Saved variant ids of one font in display order. */
export async function cardVariantIds(page: Page, fontId: string): Promise<string[]> {
  return page.locator(`[data-variant-link][data-variant-font="${fontId}"]`).evaluateAll((links) =>
    links.map((link) => link.getAttribute("data-variant-link") ?? ""),
  );
}

/** Saved variant names of one font in display order (the links' accessible names). */
export async function cardVariantNames(page: Page, fontId: string): Promise<string[]> {
  return page.locator(`[data-variant-link][data-variant-font="${fontId}"]`).evaluateAll((links) =>
    links.map((link) => link.getAttribute("aria-label") ?? ""),
  );
}

/**
 * Click Add variant on one font card and wait for its editor. Creation
 * commits before navigation, so the editor's presence implies a saved row;
 * returns the new variant id from the canonical route.
 */
export async function openNewVariant(page: Page, fontId: string): Promise<string> {
  await page.locator(`[data-add-variant="${fontId}"]`).click();
  await page.waitForFunction(() => document.querySelector("[data-variant-editor]") !== null);
  const path = await hashPath(page);
  const match = path.match(/^\/font\/[^/]+\/variant\/([^/]+)\/$/);
  if (!match?.[1]) throw new Error(`Add variant did not land on a variant route, got: ${path}`);
  return match[1];
}

// Distinct-but-valid upload bytes: Roboto with its name-table family reads
// patched to a new string of the same length, so outlines and table layout
// stay intact while the content hash (the library id) changes.
export async function mutatedUploadBytes(sourceFile: string): Promise<Buffer> {
  const bytes = Buffer.from(await fs.readFile(sourceFile));
  const tables = bytes.readUInt16BE(4);
  let nameOffset = -1;
  let nameLength = 0;
  for (let i = 0; i < tables; i += 1) {
    const entry = 12 + i * 16;
    if (bytes.subarray(entry, entry + 4).toString("latin1") === "name") {
      nameOffset = bytes.readUInt32BE(entry + 8);
      nameLength = bytes.readUInt32BE(entry + 12);
      break;
    }
  }
  if (nameOffset < 0) throw new Error("No name table for mutated upload.");
  const needles: Array<[Buffer, Buffer]> = [
    [Buffer.from("Roboto", "latin1"), Buffer.from("RobotX", "latin1")],
    [Buffer.from("Roboto", "utf16le").swap16(), Buffer.from("RobotX", "utf16le").swap16()],
  ];
  let patched = 0;
  for (const [needle, replacement] of needles) {
    for (let at = nameOffset; at + needle.length <= nameOffset + nameLength; at += 1) {
      if (bytes.subarray(at, at + needle.length).equals(needle)) {
        replacement.copy(bytes, at);
        patched += 1;
      }
    }
  }
  if (patched === 0) throw new Error("No family string to patch for mutated upload.");
  return bytes;
}
