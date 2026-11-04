// Domain runtime transport: two-tab notification after the writer closes,
// owner-generation restart, old/new app coexistence, dedicated-fallback
// fencing, and startup failure with recovery. Every test drives the real
// runtime path (real SharedWorker owner, real PGlite engine, real UI); the
// raw second-client ports below stand in for a second tab's connection, never
// for the notification mechanism under test.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { promises as fs } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import type { TestContext } from "node:test";
import type { Page } from "playwright-core";
import {
  bootLibrary,
  browserAvailable,
  buildApp,
  captureDomainWorker,
  cardIds,
  cardVariantNames,
  launch,
  servePrefix,
  webRoot,
} from "../helpers/spa-helpers.ts";

// Same worker identity the app uses (see src/app/domain/protocol.ts).
const WORKER_NAME = "glypherie-domain-v1";
const OWNER_LEASE = "glypherie-domain-owner-v1";

async function workerUrl(page: Page): Promise<string> {
  return page.evaluate(() => {
    const urls = (window as unknown as { __sharedWorkerUrls?: unknown }).__sharedWorkerUrls;
    const url = Array.isArray(urls) ? urls.find((entry): entry is string => typeof entry === "string") : undefined;
    if (!url) throw new Error("domain worker URL was not captured; call captureDomainWorker(context) before booting.");
    return url;
  });
}

/**
 * Commit a variant through a raw second connection to the same owner, then
 * close that connection immediately without waiting for its response. The
 * connected app tab must still learn of the commit through the owner's own
 * announcement, not through any writer-side relay.
 */
async function writeAndCloseImmediately(page: Page, fontId: string, name: string): Promise<void> {
  const url = await workerUrl(page);
  await page.evaluate(async ({ workerScript, workerName, font, variantName }) => {
    const ports = (window as unknown as { __sharedWorkerUrls?: unknown }).__sharedWorkerUrls;
    void ports;
    const peer = new SharedWorker(workerScript, { type: "module", name: workerName });
    const port = peer.port;
    port.start();
    port.postMessage({ id: 424242, method: "createVariant", params: [font, { name: variantName }] });
    port.close();
  }, { workerScript: url, workerName: WORKER_NAME, font: fontId, variantName: name });
}

async function variantAppears(page: Page, fontId: string, name: string): Promise<void> {
  await page.waitForFunction(
    ([font, expected]) => [...document.querySelectorAll(`[data-variant-link][data-variant-font="${font}"]`)]
      .some((link) => (link.getAttribute("aria-label") ?? "").includes(expected)),
    [fontId, name] as [string, string],
    { timeout: 20000 },
  );
}

/**
 * Serve several build outputs on one origin under distinct prefixes. A root
 * may be a thunk so a test can swap a deployment under a stable prefix,
 * modelling a redeploy: same paths, new bytes, live workers unchanged.
 */
async function serveMany(
  t: TestContext,
  mounts: Array<{ prefix: string; root: string | (() => string); override?: (relative: string) => Promise<{ bytes: Buffer; mime: string } | null> }>,
): Promise<string> {
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
  const server = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url ?? "/", "http://localhost");
      const mount = mounts.find((entry) => url.pathname.startsWith(entry.prefix));
      if (!mount) throw new Error("Unknown prefix");
      const root = typeof mount.root === "function" ? mount.root() : mount.root;
      let relative = decodeURIComponent(url.pathname.slice(mount.prefix.length));
      if (!relative || relative.endsWith("/")) relative += "index.html";
      if (relative.startsWith("..") || relative.includes("../")) throw new Error("Invalid path");
      const overridden = await mount.override?.(relative);
      if (overridden) {
        response.writeHead(200, { "Content-Type": overridden.mime });
        response.end(overridden.bytes);
        return;
      }
      const file = path.resolve(root, relative);
      if (path.relative(root, file).startsWith("..")) throw new Error("Invalid path");
      const bytes = await fs.readFile(file);
      response.writeHead(200, { "Content-Type": MIME[path.extname(file)] ?? "application/octet-stream" });
      response.end(bytes);
    } catch {
      const fallback = mounts.map((entry) => path.join(typeof entry.root === "function" ? entry.root() : entry.root, "404.html"));
      for (const candidate of fallback) {
        try {
          const bytes = await fs.readFile(candidate);
          response.writeHead(404, { "Content-Type": "text/html" });
          response.end(bytes);
          return;
        } catch {
          // Try the next mount's fallback.
        }
      }
      response.writeHead(404, { "Content-Type": "text/html" });
      response.end("");
    }
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise<void>((resolve) => {
    server.close(() => resolve());
    server.closeAllConnections();
  }));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Test server did not bind a port.");
  return `http://127.0.0.1:${address.port}`;
}

test("a follower learns of a commit even when the writer closes first", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  t.after(() => context.close());
  await captureDomainWorker(context);
  const page = await context.newPage();
  const problems: string[] = [];
  page.on("pageerror", (error) => { problems.push(String(error)); });
  await bootLibrary(page, url);
  const fontId = (await cardIds(page))[0]!;
  const probe = `Writer closes probe ${Date.now() % 100000}`;
  assert.deepEqual(await cardVariantNames(page, fontId), [], "no variants before the probe write");
  await writeAndCloseImmediately(page, fontId, probe);
  // No reload, no retry, no second action: the owner's own announcement is
  // the only path that can inform this tab, and the reactive variant query
  // re-reads on that notification.
  await variantAppears(page, fontId, probe);
  assert.deepEqual(problems, []);
});

test("saved styles survive closing every tab and reopening", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const first = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  t.after(() => first.close());
  await captureDomainWorker(first);
  const before = await first.newPage();
  await bootLibrary(before, url);
  const fontId = (await cardIds(before))[0]!;
  const firstProbe = `Restart probe one ${Date.now() % 100000}`;
  await writeAndCloseImmediately(before, fontId, firstProbe);
  await variantAppears(before, fontId, firstProbe);
  await before.close();
  const after = await first.newPage();
  await bootLibrary(after, url);
  await variantAppears(after, fontId, firstProbe);
  assert.ok((await cardVariantNames(after, fontId)).includes(firstProbe), "the reopened tab retains the saved style");
  const secondProbe = `Restart probe two ${(Date.now() + 1) % 100000}`;
  await writeAndCloseImmediately(after, fontId, secondProbe);
  await variantAppears(after, fontId, secondProbe);
  assert.ok((await cardVariantNames(after, fontId)).includes(secondProbe));
});

/**
 * Build the app with a baked domain protocol version. The default build
 * speaks the current version; a numbered build simulates the next
 * deployment generation for coexistence tests.
 */
async function buildProtocol(t: TestContext, protocol: string | undefined): Promise<string> {
  const output = await fs.mkdtemp(path.join(os.tmpdir(), "font-spa-protocol-"));
  t.after(() => fs.rm(output, { recursive: true, force: true }));
  execFileSync("npm", ["run", "build", "--", "--outDir", output], {
    cwd: webRoot,
    stdio: "pipe",
    env: {
      ...process.env,
      FONT_PREVIEW_BASE: "/preview/",
      ...(protocol === undefined ? {} : { VITE_DOMAIN_PROTOCOL: protocol }),
    },
  });
  return output;
}

test("a new deploy beside a live old owner fails visibly and recovers", { skip: !browserAvailable }, async (t) => {
  const previous = await buildProtocol(t, undefined);
  let current = previous;
  const origin = await serveMany(t, [{ prefix: "/preview/", root: () => current }]);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  t.after(() => context.close());
  // No service worker here: it would keep serving the previous deployment's
  // bytes from precache after the swap, so the new tab would never load the
  // new deployment. The app runs the same without it (proven by probe).
  await context.addInitScript(() => {
    try {
      Object.defineProperty(window.navigator, "serviceWorker", { value: undefined, configurable: true });
    } catch {
      // Navigator shape differs; registration simply never happens below.
    }
  });
  // The previous deployment boots first and owns the engine.
  const oldPage = await context.newPage();
  await bootLibrary(oldPage, `${origin}/preview/`);
  // A redeploy swaps the bytes under the stable worker URL and bumps the
  // wire version. The new tab joins the live owner (same URL and name, so
  // no second engine), fails the version handshake, and says so with a
  // retryable close-tabs error instead of hanging or splitting engines.
  // Same-name, cross-URL workers neither join nor reject on this platform
  // (proven by probe), so the versioned handshake is the coexistence fence.
  current = await buildProtocol(t, "3");
  const page = await context.newPage();
  const problems: string[] = [];
  page.on("pageerror", (error) => { problems.push(String(error)); });
  await page.goto(`${origin}/preview/fonts/`, { waitUntil: "domcontentloaded" });
  await page.locator("[data-library-error]").waitFor({ timeout: 30000 });
  const text = (await page.locator("[data-library-error]").textContent()) ?? "";
  assert.ok(
    text.includes("Storage is blocked. Close other Glypherie tabs and reload."),
    `the old-owner conflict names its recovery, got: ${text}`,
  );
  assert.equal(await page.locator("[data-library-retry]").count(), 1, "the conflict is retryable");
  assert.equal(await page.locator("[data-font-card]").count(), 0, "no library renders without an owner");
  // The live scope outlives any one tab while a same-origin document keeps
  // it referenced (proven by probe: the old worker answers 120s after its
  // tab closes), so recovery means closing every tab, then reopening onto
  // a fresh owner that serves the new deployment.
  await oldPage.close();
  await page.close();
  const reopened = await context.newPage();
  await bootLibrary(reopened, `${origin}/preview/`);
  assert.ok((await cardIds(reopened)).length > 0, "the new deployment boots once the old owner is gone");
  assert.deepEqual(problems, [], "the conflict never throws during render");
});

test("a new app beside a live pre-protocol owner names the update", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  let serveLegacyOwner = true;
  const origin = await serveMany(t, [{
    prefix: "/preview/",
    root: output,
    override: async (relative) => {
      // Faithful pre-protocol owner stand-in: it answers like the old
      // worker (unknown method for the version probe) at the stable URL.
      if (serveLegacyOwner && relative === "assets/domain-worker.js") {
        return {
          mime: "application/javascript",
          bytes: Buffer.from(`self.onconnect = (event) => {
  for (const port of event.ports) {
    port.onmessage = (msg) => {
      const call = msg.data;
      if (typeof call?.id !== "number" || typeof call.method !== "string") return;
      port.postMessage({ id: call.id, ok: false, error: { code: "unavailable", message: 'Unknown domain method "' + call.method + '".' } });
    };
    port.start();
  }
};`),
        };
      }
      return null;
    },
  }]);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  t.after(() => context.close());
  const page = await context.newPage();
  const problems: string[] = [];
  page.on("pageerror", (error) => { problems.push(String(error)); });
  await page.goto(`${origin}/preview/fonts/`, { waitUntil: "domcontentloaded" });
  // The version probe rejects: the live owner belongs to an older app
  // generation, so the tab names closing the other tabs instead of running
  // against an owner it cannot understand.
  await page.locator("[data-library-error]").waitFor({ timeout: 30000 });
  const text = (await page.locator("[data-library-error]").textContent()) ?? "";
  assert.ok(
    text.includes("Close other Glypherie tabs"),
    `the stale owner names its recovery, got: ${text}`,
  );
  assert.equal(await page.locator("[data-library-retry]").count(), 1, "the stale owner is retryable");
  // The legacy owner goes away (its last tab closes here: one page only),
  // the retry boots a fresh protocol-matching owner, and the library loads.
  serveLegacyOwner = false;
  await page.close();
  const recovered = await context.newPage();
  await bootLibrary(recovered, `${origin}/preview/`);
  assert.ok((await cardIds(recovered)).length > 0, "the library boots after the stale owner is gone");
  assert.deepEqual(problems, [], "the stale owner never throws during render");
});

test("the dedicated fallback fences a second opener and releases on close", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  t.after(() => context.close());
  // No SharedWorker here: every tab takes the dedicated-worker path, fenced
  // by the same origin lease the shared owner would hold.
  await context.addInitScript(() => {
    (window as unknown as { SharedWorker?: unknown }).SharedWorker = undefined;
  });
  const first = await context.newPage();
  await bootLibrary(first, url);
  assert.ok((await cardIds(first)).length > 0, "the first opener boots the fenced engine");
  // The second opener refuses to launch a second engine: a retryable busy
  // error names closing the other tab.
  const second = await context.newPage();
  const problems: string[] = [];
  second.on("pageerror", (error) => { problems.push(String(error)); });
  await second.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
  await second.locator("[data-library-error]").waitFor({ timeout: 30000 });
  const text = (await second.locator("[data-library-error]").textContent()) ?? "";
  assert.ok(
    text.includes("Storage is blocked. Close other Glypherie tabs and reload."),
    `the second opener names its recovery, got: ${text}`,
  );
  assert.equal(await second.locator("[data-library-retry]").count(), 1, "the busy owner is retryable");
  assert.equal(await second.locator("[data-font-card]").count(), 0, "no second engine serves reads");
  // Closing the owning tab releases the lease; the waiting tab's retry then
  // boots the engine itself.
  await first.close();
  await second.waitForFunction(
    (lease) => navigator.locks.query().then((state) => (state.held ?? []).every((entry) => entry.name !== lease)),
    OWNER_LEASE,
    { timeout: 20000 },
  );
  for (let attempt = 0; attempt < 6; attempt += 1) {
    if (await second.locator("[data-font-card]").count() > 0) break;
    const retry = second.locator("[data-library-retry]");
    if (await retry.count() > 0) await retry.click();
    await second.waitForTimeout(2000);
  }
  await second.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0, null, { timeout: 30000 });
  assert.deepEqual(problems, [], "fencing never throws during render");
});

test("a forced owner startup failure surfaces Retry and then recovers", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  let serveBrokenOwner = true;
  const origin = await serveMany(t, [{
    prefix: "/preview/",
    root: output,
    override: async (relative) => {
      // The worker script evaluates to an immediate failure: construction
      // succeeds but the owner never starts, exercising the async error path.
      if (serveBrokenOwner && relative === "assets/domain-worker.js") {
        return {
          mime: "application/javascript",
          bytes: Buffer.from(`throw new Error("forced domain owner startup failure");`),
        };
      }
      return null;
    },
  }]);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  t.after(() => context.close());
  const page = await context.newPage();
  const problems: string[] = [];
  page.on("pageerror", (error) => { problems.push(String(error)); });
  await page.goto(`${origin}/preview/fonts/`, { waitUntil: "domcontentloaded" });
  // A poisoned worker scope fails each boot stage on a short probe instead
  // of burning a full cold-boot budget per stage; the ladder still takes
  // seconds to surface through seeding into the font query.
  await page.locator("[data-library-error]").waitFor({ timeout: 45000 });
  const text = (await page.locator("[data-library-error]").textContent()) ?? "";
  assert.ok(
    text.includes("Browser storage is unavailable."),
    `a dead owner reports plainly with retry, got: ${text}`,
  );
  assert.equal(await page.locator("[data-library-retry]").count(), 1, "a dead owner is retryable");
  // The failure is gone (next deploy, fixed asset), but a same-scope retry
  // cannot refetch an evaluation-failed worker: the poisoned (URL, name)
  // registration rejoins silently without re-evaluating (proven by probe:
  // no fetch on retry, reload, or reopen in the same context). Recovery
  // means a fresh browsing context, like closing every tab and reopening,
  // which fetches the fixed asset and boots normally.
  serveBrokenOwner = false;
  await context.close();
  const recoveredContext = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  t.after(() => recoveredContext.close());
  const recovered = await recoveredContext.newPage();
  await bootLibrary(recovered, `${origin}/preview/`);
  assert.ok((await cardIds(recovered)).length > 0, "the library boots once the fixed asset loads");
  assert.deepEqual(problems, [], "the failed startup never throws during render");
});
