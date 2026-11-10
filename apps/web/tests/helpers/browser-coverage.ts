import { promises as fs } from "node:fs";
import path from "node:path";
import type { TestContext } from "node:test";
import type { Browser, BrowserContext, Page } from "playwright-core";

// Chromium main-thread collection for the coverage producer. Every export
// is a no-op unless GLYPHERIE_COVERAGE_DIR is set, so normal tests never
// start collection, never patch close paths, and never touch the disk.
const coverageDir = process.env.GLYPHERIE_COVERAGE_DIR;

interface CoverageBuild {
  origin: string;
  root: string;
  prefix: string;
}

const builds: CoverageBuild[] = [];
const wrappedPages = new WeakSet<object>();
const flushedPages = new WeakSet<object>();
const trackedPages = new Set<Page>();
let fileSequence = 0;

export function coverageEnabled(): boolean {
  return typeof coverageDir === "string" && coverageDir.length > 0;
}

/** Remember which temp build directory serves one test server origin. */
export function registerCoverageBuild(origin: string, root: string, prefix: string): void {
  builds.push({ origin, root, prefix });
}

/**
 * A collection failure must fail the producer, never vanish into a passing
 * report. Failures are recorded beside the V8 data; the runner refuses to
 * publish when any are present.
 */
async function recordCollectionFailure(url: string, error: unknown): Promise<void> {
  if (!coverageEnabled()) return;
  fileSequence += 1;
  const name = `failed-${process.pid}-${Date.now().toString(36)}-${fileSequence}.json`;
  const detail = error instanceof Error ? error.message : String(error);
  try {
    await fs.writeFile(path.join(coverageDir!, name), JSON.stringify({ url, error: detail }));
  } catch (writeError) {
    console.error(`[coverage] lost failure record for ${url}: ${detail} (${String(writeError)})`);
  }
}

/** Flush every still-open tracked page; safe to call more than once. */
export async function flushAllTrackedPages(): Promise<void> {
  if (!coverageEnabled()) return;
  for (const page of [...trackedPages]) await flushPage(page);
}

/** Start collection on a fresh page, before any navigation can run. */
async function watchPage(page: Page): Promise<void> {
  if (!coverageEnabled() || wrappedPages.has(page)) return;
  wrappedPages.add(page);
  trackedPages.add(page);
  const originalClose = page.close.bind(page);
  (page as { close: Page["close"] }).close = async (...args) => {
    await flushPage(page);
    return originalClose(...args);
  };
  try {
    await page.coverage.startJSCoverage({ resetOnNavigation: false });
  } catch (error) {
    // Nothing to collect later; record and surface now so the test fails
    // loudly instead of producing a silently partial report.
    flushedPages.add(page);
    await recordCollectionFailure(page.url(), error);
    throw error;
  }
}

/** Stop collection, resolve sourcemaps from the serving build, save raw V8. */
async function flushPage(page: Page): Promise<void> {
  if (!coverageEnabled() || flushedPages.has(page)) return;
  flushedPages.add(page);
  trackedPages.delete(page);
  let entries: Array<{ url: string; functions: unknown[]; source: string }>;
  try {
    entries = (await page.coverage.stopJSCoverage()) as typeof entries;
  } catch (error) {
    // The close proceeds, but the recorded failure blocks publication.
    await recordCollectionFailure(page.url(), error);
    return;
  }
  if (entries.length === 0) return;
  const origin = page.url().startsWith("http") ? new URL(page.url()).origin : "";
  const saved = [];
  for (const entry of entries) {
    const scriptPath = buildFile(origin, entry.url);
    if (!scriptPath) continue;
    const { sourceMap, mapStatus } = await readSourceMap(scriptPath, entry.source);
    saved.push({
      url: entry.url,
      scriptPath,
      source: entry.source,
      sourceMap,
      mapStatus,
      functions: entry.functions,
    });
  }
  if (saved.length === 0) return;
  fileSequence += 1;
  const name = `v8-${process.pid}-${Date.now().toString(36)}-${fileSequence}.json`;
  await fs.writeFile(path.join(coverageDir!, name), JSON.stringify(saved));
}

function buildFile(origin: string, url: string): string | undefined {
  const build = builds.find((candidate) => url.startsWith(candidate.origin + candidate.prefix));
  if (!build || !origin || !url.startsWith(origin)) return undefined;
  const relative = decodeURIComponent(url.slice((build.origin + build.prefix).length).split("?")[0] ?? "");
  const file = path.resolve(build.root, relative);
  if (!file.startsWith(path.resolve(build.root) + path.sep)) return undefined;
  return file;
}

type MapStatus = "ok" | "no-comment" | "unreadable";

async function readSourceMap(
  scriptPath: string,
  source: string,
): Promise<{ sourceMap: unknown; mapStatus: MapStatus }> {
  const match = source.match(/\/\/# sourceMappingURL=(\S+)\s*$/);
  const reference = match?.[1];
  // No comment: document shells, inline scripts, and vendor runtimes
  // without maps carry no mapping to lose; they are excluded downstream,
  // never guessed.
  if (!reference) return { sourceMap: undefined, mapStatus: "no-comment" };
  try {
    if (reference.startsWith("data:")) {
      const payload = reference.slice(reference.indexOf(",") + 1);
      const text = reference.includes(";base64")
        ? Buffer.from(payload, "base64").toString("utf8")
        : decodeURIComponent(payload);
      return { sourceMap: JSON.parse(text), mapStatus: "ok" };
    }
    const map = JSON.parse(await fs.readFile(path.resolve(path.dirname(scriptPath), reference), "utf8"));
    return { sourceMap: map, mapStatus: "ok" };
  } catch {
    // A served script that names a sourcemap which cannot be read means the
    // maps the producer depends on are unreliable; the runner rejects these.
    return { sourceMap: undefined, mapStatus: "unreadable" };
  }
}

/** Flush every still-open page of a context (used before context close). */
async function flushContextPages(context: BrowserContext): Promise<void> {
  for (const page of context.pages()) await flushPage(page);
}

/** Wrap page creation and close paths of one context. */
export function trackContextCoverage(context: BrowserContext): void {
  if (!coverageEnabled() || wrappedPages.has(context)) return;
  wrappedPages.add(context);
  const originalNewPage = context.newPage.bind(context);
  (context as { newPage: BrowserContext["newPage"] }).newPage = async () => {
    const page = await originalNewPage();
    await watchPage(page);
    return page;
  };
  const originalClose = context.close.bind(context);
  (context as { close: BrowserContext["close"] }).close = async () => {
    await flushContextPages(context);
    return originalClose();
  };
}

/**
 * Track every page of a browser: collection starts at creation (before
 * navigation) and flushes before page, context, or browser close, so
 * explicit close and reload paths cannot lose data.
 */
export function trackBrowserCoverage(t: TestContext, browser: Browser): void {
  if (!coverageEnabled()) return;
  const originalNewPage = browser.newPage.bind(browser);
  (browser as { newPage: Browser["newPage"] }).newPage = async (...args) => {
    const page = await (originalNewPage as (...a: unknown[]) => Promise<Page>)(...args);
    await watchPage(page);
    return page;
  };
  const originalNewContext = browser.newContext.bind(browser);
  (browser as { newContext: Browser["newContext"] }).newContext = async (...args) => {
    const context = await (originalNewContext as (...a: unknown[]) => Promise<BrowserContext>)(...args);
    trackContextCoverage(context);
    return context;
  };
  const originalClose = browser.close.bind(browser);
  (browser as { close: Browser["close"] }).close = async () => {
    for (const context of browser.contexts()) {
      await flushContextPages(context);
      try {
        await context.close();
      } catch {
        // Already closed on the explicit path; data was flushed first.
      }
    }
    return originalClose();
  };
  t.after(async () => {
    for (const context of browser.contexts()) await flushContextPages(context);
  });
}
