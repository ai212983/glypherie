import { promises as fs } from "node:fs";
import path from "node:path";
import type { TestContext } from "node:test";
import type { Browser, BrowserContext, Page } from "playwright-core";

// Collection and close wrappers are enabled by GLYPHERIE_COVERAGE_DIR. Build registrations are
// retained independently.
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
const pageStarts = new WeakMap<Page, Promise<void>>();
const pageFlushes = new WeakMap<Page, Promise<void>>();
let fileSequence = 0;

export function coverageEnabled(): boolean {
  return typeof coverageDir === "string" && coverageDir.length > 0;
}

// Register the on-disk build serving origin + prefix so script URLs can resolve to sourcemaps after
// navigation.
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

function watchPage(page: Page): Promise<void> {
  if (!coverageEnabled()) return Promise.resolve();
  const pending = pageStarts.get(page);
  if (pending) return pending;
  wrappedPages.add(page);
  trackedPages.add(page);
  const originalClose = page.close.bind(page);
  (page as { close: Page["close"] }).close = async (...args) => {
    await flushPage(page);
    return originalClose(...args);
  };
  // Event-created pages have no awaiting caller, so a failed start is
  // recorded for the runner (which refuses to publish) instead of thrown.
  const start = (async () => {
    try {
      await page.coverage.startJSCoverage({ resetOnNavigation: false });
    } catch (error) {
      flushedPages.add(page);
      await recordCollectionFailure(page.url(), error);
      trackedPages.delete(page);
    }
  })();
  pageStarts.set(page, start);
  return start;
}

function flushPage(page: Page): Promise<void> {
  if (!coverageEnabled()) return Promise.resolve();
  const pending = pageFlushes.get(page);
  if (pending) return pending;
  const flush = collectPage(page).finally(() => trackedPages.delete(page));
  pageFlushes.set(page, flush);
  return flush;
}

async function collectPage(page: Page): Promise<void> {
  // The page event and newPage wrapper share startup; teardown must join it
  // and the entire flush, including any failure record, before closing.
  await pageStarts.get(page);
  if (!coverageEnabled() || flushedPages.has(page)) return;
  flushedPages.add(page);
  let entries: Array<{ url: string; functions: unknown[]; source: string }>;
  try {
    entries = (await page.coverage.stopJSCoverage()) as typeof entries;
  } catch (error) {
    await recordCollectionFailure(page.url(), error);
    return;
  }
  if (entries.length === 0) return;
  const saved = [];
  for (const entry of entries) {
    const scriptPath = buildFile(entry.url);
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

function buildFile(url: string): string | undefined {
  const build = builds.find((candidate) => url.startsWith(candidate.origin + candidate.prefix));
  if (!build) return undefined;
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

async function flushContextPages(context: BrowserContext): Promise<void> {
  for (const page of context.pages()) await flushPage(page);
}

export function trackContextCoverage(context: BrowserContext): void {
  if (!coverageEnabled() || wrappedPages.has(context)) return;
  wrappedPages.add(context);
  // Pages that predate tracking (persistent profiles) start late and miss
  // earlier scripts, but still capture everything after this point.
  for (const page of context.pages()) void watchPage(page);
  // Popups arrive here after navigation may have started. Start collection
  // as soon as Playwright exposes them; wrapped newPage calls join startup.
  context.on("page", (page) => {
    void watchPage(page);
  });
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

// Wrapped newPage methods start collection before navigation; pre-existing
// pages and context "page" events (popups, target=_blank links) join through
// the context tracker. Page, context and browser close wrappers flush them
// before teardown.
export function trackBrowserCoverage(t: TestContext, browser: Browser): void {
  if (!coverageEnabled()) return;
  // Contexts (and their pages) that predate tracking join now; later ones
  // join through the wrapped newContext below.
  for (const context of browser.contexts()) trackContextCoverage(context);
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
        // Data was flushed above; continue browser teardown if context cleanup fails.
      }
    }
    return originalClose();
  };
  t.after(async () => {
    for (const context of browser.contexts()) await flushContextPages(context);
  });
}
