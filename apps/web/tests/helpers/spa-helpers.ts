import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import type { TestContext } from "node:test";
import { fileURLToPath } from "node:url";
import { chromium, type Browser, type BrowserContext, type Locator, type Page } from "playwright-core";

export const webRoot: string = fileURLToPath(new URL("../..", import.meta.url));
export const repoRoot: string = path.resolve(webRoot, "..", "..");
export const fontDir: string = path.join(repoRoot, "fonts");

export const sha256 = (bytes: Uint8Array | string): string =>
  createHash("sha256").update(bytes).digest("hex");

export async function buildApp(t: TestContext, base = "/preview/", siteUrl = ""): Promise<string> {
  const output = await fs.mkdtemp(path.join(os.tmpdir(), "font-spa-"));
  t.after(() => fs.rm(output, { recursive: true, force: true }));
  execFileSync("npm", ["run", "build", "--", "--outDir", output], { cwd: webRoot, stdio: "pipe", env: { ...process.env, FONT_PREVIEW_BASE: base, FONT_PREVIEW_SITE_URL: siteUrl } });
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

export async function servePrefix(t: TestContext, root: string, prefix = "/preview/"): Promise<string> {
  const server = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url ?? "/", "http://localhost");
      if (!url.pathname.startsWith(prefix)) throw new Error("Unknown prefix");
      let relative = decodeURIComponent(url.pathname.slice(prefix.length));
      if (!relative || relative.endsWith("/")) relative += "index.html";
      const file = path.resolve(root, relative);
      if (path.relative(root, file).startsWith("..")) throw new Error("Invalid path");
      const bytes = await fs.readFile(file);
      response.writeHead(200, { "Content-Type": MIME[path.extname(file)] ?? "application/octet-stream" });
      response.end(bytes);
    } catch {
      response.writeHead(404, { "Content-Type": "text/html" });
      response.end(await fs.readFile(path.join(root, "404.html")).catch(() => ""));
    }
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise<void>((resolve) => {
    server.close(() => resolve());
    server.closeAllConnections();
  }));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Test server did not bind a port.");
  return `http://127.0.0.1:${address.port}${prefix}`;
}

export const browserPath: string | undefined = process.env.WEB_TEST_BROWSER
  ?? (process.platform === "darwin" ? undefined : "/opt/google/chrome/chrome");
// A standard `playwright-core install chromium` installs both Chromium and its
// headless shell. Let Playwright select the shell on macOS to avoid Dock flashes.
export const browserAvailable: boolean = await fs.access(browserPath ?? chromium.executablePath())
  .then(() => true, () => false);

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
  // domcontentloaded, not networkidle: the shared domain worker's script load
  // never reports completion to the page target, so page-scoped networkidle
  // cannot fire once the owner exists. The waits below prove settledness.
  await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
}

/**
 * Record the domain SharedWorker script URL before the app boots so later
 * page.evaluate calls can open their own port to the same single owner.
 * The domain worker owns PGlite: its script fetch never surfaces in the
 * page's resource timing (see probe), so page-scoped networkidle cannot
 * observe it. Call this on the context before creating pages that need
 * variantState/domainVariant below. Idempotent and independent of page-level
 * worker wrappers (e.g. renderer SPEC_SCRIPT hooks).
 */
export async function captureDomainWorker(context: BrowserContext): Promise<void> {
  await context.addInitScript(() => {
    const holder = window as unknown as { SharedWorker?: unknown; __sharedWorkerUrls?: string[] };
    const Ctor = holder.SharedWorker as unknown as
      | (new (url: string | URL, options?: unknown) => SharedWorker)
      | undefined;
    if (typeof Ctor !== "function" || !Ctor) return;
    if ((Ctor as unknown as { __glypherieCaptured?: boolean }).__glypherieCaptured) return;
    const urls: string[] = [];
    holder.__sharedWorkerUrls = urls;
    function Wrapped(this: unknown, url: string | URL, options?: unknown): SharedWorker {
      try {
        urls.push(String(url));
      } catch {
        // Best-effort capture only.
      }
      return new (Ctor as new (url: string | URL, options?: unknown) => SharedWorker)(url, options);
    }
    Wrapped.prototype = (Ctor as unknown as { prototype: unknown }).prototype;
    (Wrapped as unknown as { __glypherieCaptured?: boolean }).__glypherieCaptured = true;
    holder.SharedWorker = Wrapped as unknown;
  });
}

export interface DomainVariantState {
  revision: number;
  inheritSampleText: boolean;
  paletteId: number;
  profile: string;
}

/**
 * Read one variant through the actual graph storage seam: a fresh port to
 * the same SharedWorker owner the app uses, calling its getVariant command.
 * Never touches the retired Dexie "font-library" database, which no longer
 * receives writes. Throws when the worker URL was not captured (call
 * captureDomainWorker on the context before booting).
 */
export async function variantState(page: Page, id: string): Promise<DomainVariantState> {
  return page.evaluate(async (variantId): Promise<DomainVariantState> => {
    const urls = (window as unknown as { __sharedWorkerUrls?: unknown }).__sharedWorkerUrls;
    const workerUrl = Array.isArray(urls) ? urls.find((entry): entry is string => typeof entry === "string") : undefined;
    if (!workerUrl) throw new Error("domain worker URL was not captured; call captureDomainWorker(context) before booting.");
    const shared = new SharedWorker(workerUrl, { type: "module", name: "glypherie-domain-v1" });
    const port = shared.port;
    const callId = Math.floor(Math.random() * 2 ** 31);
    try {
      const result = await new Promise<unknown>((resolve, reject) => {
        const timer = window.setTimeout(() => reject(new Error("domain worker call timed out")), 20000);
        port.onmessage = (event: MessageEvent) => {
          const data = event.data as { id?: unknown; ok?: unknown; result?: unknown; error?: { message?: unknown } };
          if (data?.id !== callId) return;
          window.clearTimeout(timer);
          if (data.ok) resolve(data.result);
          else reject(new Error(typeof data.error?.message === "string" ? data.error.message : "domain call failed"));
        };
        port.onmessageerror = () => {
          window.clearTimeout(timer);
          reject(new Error("domain channel failed"));
        };
        port.start();
        port.postMessage({ id: callId, method: "getVariant", params: [variantId] });
      });
      const variant = result as {
        revision: unknown;
        inheritSampleText?: unknown;
        settings?: { paletteId?: unknown; profile?: unknown };
      } | undefined;
      if (!variant || typeof variant !== "object") throw new Error(`variant ${variantId} is missing`);
      return {
        revision: Number(variant.revision),
        inheritSampleText: variant.inheritSampleText !== false,
        paletteId: typeof variant.settings?.paletteId === "number" ? variant.settings.paletteId : 0,
        profile: typeof variant.settings?.profile === "string" ? variant.settings.profile : "",
      };
    } finally {
      try {
        port.close();
      } catch {
        // Best-effort teardown only.
      }
    }
  }, id);
}

/**
 * Fail only the domain owner (SharedWorker + its dedicated-worker fallback),
 * keeping the renderer worker alive. The retired main-thread indexedDB stub
 * cannot fail the worker-side PGlite engine, so denied-storage coverage uses
 * this instead: domain calls reject with code "unavailable" and the library
 * shows its supported message with a retry.
 */
export async function blockDomainStorage(context: BrowserContext): Promise<void> {
  await context.addInitScript(() => {
    const holder = window as unknown as { SharedWorker?: unknown; Worker?: unknown };
    const isDomainUrl = (url: string | URL): boolean => {
      const text = String(url);
      // Hashed legacy ("worker-<hash>.js"), stable ("domain-worker.js") and
      // dev ("worker.ts") domain entries; never the renderer font-worker.
      return (text.includes("worker-") || text.includes("domain-worker") || text.includes("worker."))
        && !text.includes("font-worker");
    };
    const SharedCtor = holder.SharedWorker as unknown as
      | (new (url: string | URL, options?: unknown) => SharedWorker)
      | undefined;
    if (typeof SharedCtor === "function" && SharedCtor) {
      function BlockedShared(this: unknown, url: string | URL, options?: unknown): SharedWorker {
        if (isDomainUrl(url)) throw new Error("Domain storage is unavailable in this context.");
        return new (SharedCtor as new (url: string | URL, options?: unknown) => SharedWorker)(url, options);
      }
      BlockedShared.prototype = (SharedCtor as unknown as { prototype: unknown }).prototype;
      holder.SharedWorker = BlockedShared as unknown;
    }
    const WorkerCtor = holder.Worker as unknown as
      | (new (url: string | URL, options?: unknown) => Worker)
      | undefined;
    if (typeof WorkerCtor === "function" && WorkerCtor) {
      function BlockedWorker(this: unknown, url: string | URL, options?: unknown): Worker {
        if (isDomainUrl(url)) throw new Error("Domain storage is unavailable in this context.");
        return new (WorkerCtor as new (url: string | URL, options?: unknown) => Worker)(url, options);
      }
      BlockedWorker.prototype = (WorkerCtor as unknown as { prototype: unknown }).prototype;
      holder.Worker = BlockedWorker as unknown;
    }
  });
}

/** Read a hint through the same hover interaction as the app's tooltip triggers. */
export async function tooltipText(page: Page, trigger: Locator): Promise<string> {
  await page.keyboard.press("Escape");
  await trigger.hover();
  const describedBy = await page.waitForFunction((element) => element?.getAttribute("aria-describedby"), await trigger.elementHandle());
  const tooltip = page.locator(`[role="tooltip"][id="${await describedBy.jsonValue()}"]`);
  await tooltip.waitFor({ state: "visible" });
  const content = await tooltip.textContent() ?? "";
  await page.keyboard.press("Escape");
  await page.mouse.move(0, 0, { steps: 5 });
  await tooltip.waitFor({ state: "hidden" });
  return content;
}

/** Wait for an unsaved font preview (font switcher plus rendered specimen). */
export async function bootDetail(page: Page, url: string): Promise<void> {
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector('#font-select[data-state]:not(:disabled), #font-select[data-slot="select-display"]') !== null);
  await page.waitForFunction(canvasRendered);
}

/** Wait for a saved variant editor plus its rendered specimen. */
export async function bootVariant(page: Page, url: string): Promise<void> {
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("[data-variant-editor]") !== null);
  await page.waitForFunction(canvasRendered);
}

export interface HashLocation {
  path: string;
  search: string;
}

/** Current app route, relative to the test deployment prefix. */
export async function hashLocation(page: Page): Promise<HashLocation> {
  return page.evaluate(() => ({
    path: window.location.pathname.replace(/^\/preview/, ""),
    search: window.location.search.slice(1),
  }));
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

/** Actual source-font readiness, excluding browser fallback while loading. */
export async function sourceReady(page: Page, fontId: string): Promise<boolean> {
  return page.evaluate((id) => {
    const source = document.querySelector(`[data-source-preview="${id}"]`) as HTMLElement | null;
    if (!source || source.dataset.rendered !== "true") return false;
    return [...document.fonts].some((face) => face.family === `source-${id}` && face.status === "loaded")
      && source.getBoundingClientRect().height > 0;
  }, fontId);
}

/** Browser layout and paint inputs for source-preview change detection. */
export async function sourceSnapshot(page: Page, fontId: string) {
  return page.locator(`[data-source-preview="${fontId}"]`).evaluate((source) => {
    const style = getComputedStyle(source);
    const box = source.getBoundingClientRect();
    return { text: source.textContent, family: style.fontFamily, axes: style.fontVariationSettings,
      size: style.fontSize, color: style.color, width: box.width, height: box.height };
  });
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

/** Choose an explicit display magnification through the shared toolbar. */
export async function setZoom(page: Page, value: string): Promise<void> {
  await page.locator("#zoom").getByRole("radio", { name: `${value}×`, exact: true }).check();
}

export interface PalettePresetSpec {
  name: string;
  bits: 1 | 2 | 3 | 4;
}

/** Create a palette preset through the palette lab UI; returns its row id. */
export async function createPalettePreset(
  page: Page,
  url: string,
  spec: PalettePresetSpec,
): Promise<{ rowId: number }> {
  const levels = 2 ** spec.bits;
  const depthLabel = `${spec.bits}-bit · ${levels} levels`;
  const palettesLink = page.locator('[data-primary-nav="palettes"]');
  if (await palettesLink.count()) await palettesLink.click();
  else await page.goto(`${url}palettes/`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(
    () => document.querySelector('main section[aria-label="Grayscale preview"]') !== null,
    null,
    { timeout: 20000 },
  );
  const before = await page.locator("[data-preset-row]").count();
  await page.getByRole("button", { name: "Add preset" }).click();
  await page.waitForFunction(
    (count) => document.querySelectorAll("[data-preset-row]").length === count + 1,
    before,
    { timeout: 20000 },
  );
  const rowId: number = await page.evaluate(() => {
    const ids = [...document.querySelectorAll("[data-preset-row]")]
      .map((row) => Number(row.getAttribute("data-preset-row")))
      .filter((id) => id !== 0);
    return Math.max(...ids);
  });
  await page.locator(`[data-preset-row="${rowId}"]`).click();
  await page.waitForFunction(
    (id) => document.querySelector(`[data-preset-row="${id}"]`)?.getAttribute("aria-pressed") === "true",
    rowId,
    { timeout: 20000 },
  );
  const depth = page.getByRole("radio", { name: depthLabel, exact: true });
  if ((await depth.getAttribute("data-state")) !== "on") await depth.click();
  await page.waitForFunction(
    ([id, label]) => document.querySelector(`[data-preset-caption="${id}"]`)?.textContent?.includes(label) === true,
    [rowId, depthLabel] as [number, string],
    { timeout: 20000 },
  );
  const nameBox = page
    .getByRole("region", { name: "Grayscale preview" })
    .getByRole("textbox", { name: "Name", exact: true });
  await nameBox.fill(spec.name);
  await nameBox.blur();
  await page.waitForFunction(
    ([id, name]) => document.querySelector(`[data-preset-row="${id}"]`)?.getAttribute("aria-label")?.startsWith(`${name},`) === true,
    [rowId, spec.name] as [number, string],
    { timeout: 20000 },
  );
  return { rowId };
}

/** Select a palette preset through the editor Palette chooser. */
export async function selectPalettePreset(page: Page, name: string): Promise<void> {
  await page.getByRole("combobox", { name: "Palette", exact: true }).click();
  await page.getByRole("option").filter({ has: page.getByText(name, { exact: true }) }).click();
  await page.waitForFunction(
    (expected) => document.querySelector('[data-output-palette] [data-palette-name]')?.textContent === expected,
    name,
    { timeout: 20000 },
  );
}
