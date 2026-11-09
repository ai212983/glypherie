// Domain runtime transport: two-tab notification after the writer closes,
// owner-generation restart, old/new app coexistence, single-tab redeploy
// recovery with the service worker enabled, dedicated-fallback fencing, and
// startup failure with recovery. Every test drives the real runtime path
// (real SharedWorker owner, real PGlite engine, real UI); the raw
// second-client ports below stand in for a second tab's connection, never
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
import { DOMAIN_PROTOCOL_VERSION } from "../../src/app/domain/protocol.ts";
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
  await page.evaluate(
    async ({ workerScript, workerName, font, variantName }) => {
      const ports = (window as unknown as { __sharedWorkerUrls?: unknown }).__sharedWorkerUrls;
      void ports;
      const peer = new SharedWorker(workerScript, { type: "module", name: workerName });
      const port = peer.port;
      port.start();
      port.postMessage({ id: 424242, method: "createVariant", params: [font, { name: variantName }] });
      port.close();
    },
    { workerScript: url, workerName: WORKER_NAME, font: fontId, variantName: name },
  );
}

async function variantAppears(page: Page, fontId: string, name: string): Promise<void> {
  await page.waitForFunction(
    ([font, expected]) =>
      [...document.querySelectorAll(`[data-variant-link][data-variant-font="${font}"]`)].some((link) =>
        (link.getAttribute("aria-label") ?? "").includes(expected),
      ),
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
  mounts: Array<{
    prefix: string;
    root: string | (() => string);
    override?: (relative: string) => Promise<{ bytes: Buffer; mime: string } | null>;
  }>,
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
      const fallback = mounts.map((entry) =>
        path.join(typeof entry.root === "function" ? entry.root() : entry.root, "404.html"),
      );
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
  t.after(
    () =>
      new Promise<void>((resolve) => {
        server.close(() => resolve());
        server.closeAllConnections();
      }),
  );
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
  page.on("pageerror", (error) => {
    problems.push(String(error));
  });
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
  const previous = await buildProtocol(t, "2");
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
  // The previous generation is pinned to protocol 2 (pre-ensureDefault) while the
  // current build speaks the default: no hardcoded default assumptions.
  current = await buildProtocol(t, undefined);
  const page = await context.newPage();
  const problems: string[] = [];
  page.on("pageerror", (error) => {
    problems.push(String(error));
  });
  await page.goto(`${origin}/preview/fonts/`, { waitUntil: "domcontentloaded" });
  await page.locator("[data-library-error]").waitFor({ timeout: 30000 });
  const text = (await page.locator("[data-library-error]").textContent()) ?? "";
  assert.ok(
    text.includes("The background library and this page are different app versions."),
    `the old-owner conflict names the version skew without blaming tabs, got: ${text}`,
  );
  assert.ok(!text.includes("Close other Glypherie tabs"), `the skew copy never asserts other tabs, got: ${text}`);
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
  const origin = await serveMany(t, [
    {
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
    },
  ]);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  t.after(() => context.close());
  const page = await context.newPage();
  const problems: string[] = [];
  page.on("pageerror", (error) => {
    problems.push(String(error));
  });
  await page.goto(`${origin}/preview/fonts/`, { waitUntil: "domcontentloaded" });
  // The version probe rejects: the live owner belongs to an older app
  // generation, so the tab names the pending update instead of running
  // against an owner it cannot understand — without asserting other tabs.
  await page.locator("[data-library-error]").waitFor({ timeout: 30000 });
  const text = (await page.locator("[data-library-error]").textContent()) ?? "";
  assert.ok(
    text.includes("The background library and this page are different app versions."),
    `the stale owner names the version skew, got: ${text}`,
  );
  assert.ok(!text.includes("Close other Glypherie tabs"), `the skew copy never asserts other tabs, got: ${text}`);
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
  second.on("pageerror", (error) => {
    problems.push(String(error));
  });
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
    if ((await second.locator("[data-font-card]").count()) > 0) break;
    const retry = second.locator("[data-library-retry]");
    if ((await retry.count()) > 0) await retry.click();
    await second.waitForTimeout(2000);
  }
  await second.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0, null, {
    timeout: 30000,
  });
  assert.deepEqual(problems, [], "fencing never throws during render");
});

test("a forced owner startup failure surfaces Retry and then recovers", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  let serveBrokenOwner = true;
  const origin = await serveMany(t, [
    {
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
    },
  ]);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  t.after(() => context.close());
  const page = await context.newPage();
  const problems: string[] = [];
  page.on("pageerror", (error) => {
    problems.push(String(error));
  });
  await page.goto(`${origin}/preview/fonts/`, { waitUntil: "domcontentloaded" });
  // A poisoned worker scope fails each boot stage on a short probe instead
  // of burning a full cold-boot budget per stage; the ladder still takes
  // seconds to surface through seeding into the font query.
  await page.locator("[data-library-error]").waitFor({ timeout: 45000 });
  const text = (await page.locator("[data-library-error]").textContent()) ?? "";
  assert.ok(text.includes("Browser storage is unavailable."), `a dead owner reports plainly with retry, got: ${text}`);
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

/**
 * Seed one composition through a raw second port to the single live owner.
 * The port stands in for a second tab's connection; the name is returned so
 * the test can prove the same database answers after the redeploy recovery.
 */
async function seedScene(page: Page, workerScript: string, name: string): Promise<void> {
  await page.evaluate(
    async ({ sceneName, workerUrl, workerName }) => {
      const workerScript = workerUrl as string;
      const call = async <T>(method: string, params: unknown[], id: number): Promise<T> => {
        const peer = new SharedWorker(workerScript, { type: "module", name: workerName as string });
        const port = peer.port;
        try {
          return await new Promise<T>((resolve, reject) => {
            const timer = window.setTimeout(() => reject(new Error(`${method} timed out`)), 30000);
            port.onmessage = (event: MessageEvent) => {
              const data = event.data as {
                id?: unknown;
                ok?: unknown;
                result?: unknown;
                error?: { message?: unknown };
              };
              if (data?.id !== id) return;
              window.clearTimeout(timer);
              if (data.ok) resolve(data.result as T);
              else reject(new Error(typeof data.error?.message === "string" ? data.error.message : `${method} failed`));
            };
            port.start();
            port.postMessage({ id, method, params });
          });
        } finally {
          try {
            port.close();
          } catch {
            // Best-effort teardown only.
          }
        }
      };
      const profiles = await call<Array<{ id: string }>>("listOutputProfiles", [], 91011);
      const profileId = profiles[0]?.id;
      if (!profileId) throw new Error("No output profile to seed a composition.");
      await call("createScene", [{ name: sceneName, width: 800, height: 600, outputProfileId: profileId }], 91012);
    },
    { sceneName: name, workerUrl: workerScript, workerName: WORKER_NAME },
  );
}

/** Entry scripts referenced by one build's index shell (proves page generation). */
async function entryScriptsOf(output: string): Promise<string[]> {
  const html = await fs.readFile(path.join(output, "index.html"), "utf8");
  const names = new Set<string>();
  for (const match of html.matchAll(/assets\/[A-Za-z0-9_.-]+\.js/g)) names.add(match[0]);
  return [...names];
}

/** Raw owner handshake as generation `protocol` (proves worker generation). */
async function handshakeAs(
  page: Page,
  workerScript: string,
  protocol: number,
): Promise<{ ok: unknown; protocol?: unknown; error?: { code?: unknown; message?: unknown } }> {
  return page.evaluate(
    async ({ workerUrl, workerName, version }) => {
      const peer = new SharedWorker(workerUrl as string, { type: "module", name: workerName as string });
      const port = peer.port;
      try {
        return await new Promise<{ ok: unknown; protocol?: unknown; error?: { code?: unknown; message?: unknown } }>(
          (resolve, reject) => {
            const timer = window.setTimeout(() => reject(new Error("__protocol timed out")), 30000);
            port.onmessage = (event: MessageEvent) => {
              const data = event.data as {
                id?: unknown;
                ok?: unknown;
                protocol?: unknown;
                error?: { code?: unknown; message?: unknown };
              };
              if (data?.id !== 91999) return;
              window.clearTimeout(timer);
              resolve({ ok: data.ok, protocol: data.protocol, error: data.error });
            };
            port.start();
            port.postMessage({ id: 91999, method: "__protocol", params: [version] });
          },
        );
      } finally {
        try {
          port.close();
        } catch {
          // Best-effort teardown only.
        }
      }
    },
    { workerUrl: workerScript, workerName: WORKER_NAME, version: protocol },
  );
}

/** Page script URLs currently loaded (proves which deployment the tab runs). */
async function loadedScripts(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    [...document.querySelectorAll("script[src]")].map((entry) => (entry as HTMLScriptElement).src),
  );
}

/**
 * Seeded composition adopted as the implicit default workspace. The Screen
 * page shows no list, so the proof ties the open workspace id to the seeded
 * row id: the same stored data renders without scene selection.
 */
async function compositionVisibleInUi(page: Page, origin: string, workerScript: string, name: string): Promise<void> {
  await page.goto(`${origin}/preview/screen/`, { waitUntil: "domcontentloaded" });
  const seeded = await page.evaluate(
    async ({ workerUrl, workerName, sceneName }) => {
      const peer = new SharedWorker(workerUrl as string, { type: "module", name: workerName as string });
      const port = peer.port;
      try {
        return await new Promise<string | null>((resolve, reject) => {
          const timer = window.setTimeout(() => reject(new Error("listScenes timed out")), 30000);
          port.onmessage = (event: MessageEvent) => {
            const data = event.data as { id?: unknown; ok?: unknown; result?: unknown; error?: { message?: unknown } };
            if (data?.id !== 91014) return;
            window.clearTimeout(timer);
            if (data.ok) {
              const scenes = data.result as Array<{ id?: unknown; name?: unknown }>;
              const match = scenes.find((scene) => String(scene.name) === sceneName);
              resolve(match?.id === undefined ? null : String(match.id));
            } else {
              reject(new Error(typeof data.error?.message === "string" ? data.error.message : "listScenes failed"));
            }
          };
          port.start();
          port.postMessage({ id: 91014, method: "listScenes", params: [] });
        });
      } finally {
        try {
          port.close();
        } catch {
          // Best-effort teardown only.
        }
      }
    },
    { workerUrl: workerScript, workerName: WORKER_NAME, sceneName: name },
  );
  assert.ok(seeded !== null, "the seeded composition survives");
  await page.waitForFunction(
    (id) => document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-workspace") === id,
    seeded,
    { timeout: 30000 },
  );
  const adopted = await page.locator("[data-screen-workspace]").getAttribute("data-screen-workspace");
  assert.equal(adopted, seeded, "the Screen page adopts the seeded composition as its default");
}

async function sceneNames(page: Page, workerScript: string): Promise<string[]> {
  return page.evaluate(
    async ({ workerUrl, workerName }) => {
      const peer = new SharedWorker(workerUrl as string, { type: "module", name: workerName as string });
      const port = peer.port;
      try {
        return await new Promise<string[]>((resolve, reject) => {
          const timer = window.setTimeout(() => reject(new Error("listScenes timed out")), 30000);
          port.onmessage = (event: MessageEvent) => {
            const data = event.data as { id?: unknown; ok?: unknown; result?: unknown; error?: { message?: unknown } };
            if (data?.id !== 91013) return;
            window.clearTimeout(timer);
            if (data.ok) {
              const scenes = data.result as Array<{ name?: unknown }>;
              resolve(scenes.map((scene) => String(scene.name)));
            } else {
              reject(new Error(typeof data.error?.message === "string" ? data.error.message : "listScenes failed"));
            }
          };
          port.start();
          port.postMessage({ id: 91013, method: "listScenes", params: [] });
        });
      } finally {
        try {
          port.close();
        } catch {
          // Best-effort teardown only.
        }
      }
    },
    { workerUrl: workerScript, workerName: WORKER_NAME },
  );
}

test(
  "a redeployed app recovers a single tab with the service worker on and returns seeded data",
  { skip: !browserAvailable },
  async (t) => {
    const previous = await buildProtocol(t, "2");
    let current = previous;
    const origin = await serveMany(t, [{ prefix: "/preview/", root: () => current }]);
    // The service worker stays enabled here: recovery must work through the
    // real precache/update flow, never around it.
    const browser = await launch(t);
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    t.after(() => context.close());
    await captureDomainWorker(context);
    const page = await context.newPage();
    const problems: string[] = [];
    page.on("pageerror", (error) => {
      problems.push(String(error));
    });
    await bootLibrary(page, `${origin}/preview/`);
    await page.evaluate(async () => {
      await navigator.serviceWorker.ready;
    });
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0, null, {
      timeout: 60000,
    });
    await page.waitForFunction(() => navigator.serviceWorker?.controller !== null, null, { timeout: 20000 });
    const probe = `Redeploy probe ${Date.now() % 100000}`;
    await seedScene(page, await workerUrl(page), probe);

    // A redeploy swaps the bytes under the stable worker URL while the old
    // scope is still live. The single tab reloads onto the new deployment.
    current = await buildProtocol(t, undefined);
    await page.reload({ waitUntil: "domcontentloaded" });

    // The redeploy surfaces as a pending app update (explicit Update, never
    // auto-applied) or as a version-skew error that never blames other tabs.
    // Either way the seeded composition must come back on this same database.
    const footer = page.getByRole("contentinfo");
    const update = footer.getByRole("button", { name: "Update", exact: true });
    let updated = false;
    try {
      await update.waitFor({ timeout: 60000 });
      await Promise.all([page.waitForEvent("load"), update.click()]);
      updated = true;
    } catch {
      // No waiting update yet: the tab may already show the skew error.
    }
    await page.waitForFunction(
      () =>
        document.querySelectorAll("[data-font-card]").length > 0 ||
        document.querySelector("[data-library-error]") !== null,
      null,
      { timeout: 90000 },
    );
    if ((await page.locator("[data-library-error]").count()) > 0) {
      const text = (await page.locator("[data-library-error]").textContent()) ?? "";
      assert.ok(
        text.includes("The background library and this page are different app versions."),
        `the skew error names the version without blaming tabs, got: ${text}`,
      );
      assert.ok(!text.includes("Close other Glypherie tabs"), `no other-tabs claim, got: ${text}`);
      // The honest copy's remedies: apply the pending update when one is
      // offered, otherwise restart the browser with no tabs open. Either way
      // the next single tab must boot the new deployment on the same data.
      if (!updated) {
        try {
          await update.waitFor({ timeout: 15000 });
          await Promise.all([page.waitForEvent("load"), update.click()]);
          updated = true;
        } catch {
          // No update offered: fall through to the clean restart below.
        }
      }
      if ((await page.locator("[data-library-error]").count()) > 0) {
        await page.close();
        await new Promise((resolve) => setTimeout(resolve, 8000));
        const reopened = await context.newPage();
        reopened.on("pageerror", (error) => {
          problems.push(String(error));
        });
        await bootLibrary(reopened, `${origin}/preview/`);
        // Generation proof: the tab runs current bytes and the owner answers current.
        // Counts or raw listScenes alone could pass with both sides stale on 2.
        const reopenedCurrent = await entryScriptsOf(current);
        const reopenedPrevious = await entryScriptsOf(previous);
        const reopenedNew = reopenedCurrent.filter((entry) => !reopenedPrevious.includes(entry));
        assert.ok(reopenedNew.length > 0, "the two deployments have distinct entry scripts");
        const reopenedScripts = await loadedScripts(reopened);
        assert.ok(
          reopenedNew.some((entry) => reopenedScripts.some((src) => src.includes(entry))),
          `the reopened tab runs current bytes, got: ${reopenedScripts.join(" ")}`,
        );
        const reopenedHandshake = await handshakeAs(reopened, await workerUrl(reopened), DOMAIN_PROTOCOL_VERSION);
        assert.equal(reopenedHandshake.ok, true, "the recovered owner answers the current generation");
        assert.equal(
          reopenedHandshake.protocol,
          DOMAIN_PROTOCOL_VERSION,
          "the recovered owner reports the current generation",
        );
        const reopenedOld = await handshakeAs(reopened, await workerUrl(reopened), 2);
        assert.equal(reopenedOld.ok, false, "the recovered owner rejects generation 2");
        await compositionVisibleInUi(reopened, origin, await workerUrl(reopened), probe);
        assert.ok(
          (await sceneNames(reopened, await workerUrl(reopened))).includes(probe),
          "the seeded composition survives the page restart onto the new deployment",
        );
        assert.ok(
          await reopened.evaluate(() => navigator.serviceWorker?.controller !== null),
          "the recovered tab is service-worker controlled",
        );
        assert.deepEqual(problems, [], "recovery never throws during render");
        return;
      }
    }
    assert.ok((await cardIds(page)).length > 0, "the redeployed tab boots its library");
    // Same generation proof on the same-tab path: current page bytes plus a
    // generation-4 owner, with the seed read through the Screen UI.
    const sameCurrent = await entryScriptsOf(current);
    const samePrevious = await entryScriptsOf(previous);
    const sameNew = sameCurrent.filter((entry) => !samePrevious.includes(entry));
    assert.ok(sameNew.length > 0, "the two deployments have distinct entry scripts");
    const sameScripts = await loadedScripts(page);
    assert.ok(
      sameNew.some((entry) => sameScripts.some((src) => src.includes(entry))),
      `the redeployed tab runs current bytes, got: ${sameScripts.join(" ")}`,
    );
    const sameHandshake = await handshakeAs(page, await workerUrl(page), DOMAIN_PROTOCOL_VERSION);
    assert.equal(sameHandshake.ok, true, "the same-tab owner answers the current generation");
    assert.equal(sameHandshake.protocol, DOMAIN_PROTOCOL_VERSION, "the same-tab owner reports the current generation");
    const sameOld = await handshakeAs(page, await workerUrl(page), 2);
    assert.equal(sameOld.ok, false, "the same-tab owner rejects generation 2");
    await compositionVisibleInUi(page, origin, await workerUrl(page), probe);
    assert.ok(
      (await sceneNames(page, await workerUrl(page))).includes(probe),
      "the seeded composition survives the redeploy on the same tab",
    );
    assert.ok(
      await page.evaluate(() => navigator.serviceWorker?.controller !== null),
      "the recovered tab is service-worker controlled",
    );
    assert.deepEqual(problems, [], "recovery never throws during render");
  },
);
