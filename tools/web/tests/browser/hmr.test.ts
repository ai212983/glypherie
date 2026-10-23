import assert from "node:assert/strict";
import net from "node:net";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { createServer, preview, type Plugin, type ViteDevServer } from "vite";
import { bootLibrary, browserAvailable, buildApp, cardIds, launch, openNewVariant, tooltipText, webRoot } from "../helpers/spa-helpers.ts";

async function freePort(): Promise<number> {
  return new Promise<number>((resolve, reject) => {
    const probe = net.createServer();
    probe.on("error", reject);
    probe.listen(0, "127.0.0.1", () => {
      const address = probe.address();
      if (address && typeof address === "object") {
        const port = address.port;
        probe.close(() => resolve(port));
      } else reject(new Error("No local port for the dev server."));
    });
  });
}

test("switching a cached production app to dev retires its worker and preserves variants", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const port = await freePort();
  const configFile = path.join(webRoot, "vite.config.ts");
  const nodeEnv = process.env.NODE_ENV;
  const production = await preview({
    configFile, logLevel: "warn", build: { outDir: output },
    preview: { host: "127.0.0.1", port, strictPort: true },
  });
  if (nodeEnv === undefined) delete process.env.NODE_ENV;
  else process.env.NODE_ENV = nodeEnv;
  t.after(() => production.httpServer.close());
  const url = `http://127.0.0.1:${port}/`;
  const browser = await launch(t);
  const context = await browser.newContext();
  t.after(() => context.close());
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(String(error)));
  page.on("requestfailed", (request) => errors.push(`${request.url()}: ${request.failure()?.errorText}`));
  await bootLibrary(page, url);
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
  const id = (await cardIds(page))[0]!;
  await openNewVariant(page, id);
  await page.locator('[data-variant-name]').fill("Keep through dev recovery");
  await page.waitForFunction(() => document.querySelector('[data-save-status]')?.textContent === "Saved");
  const variantUrl = page.url();
  if ("closeAllConnections" in production.httpServer) production.httpServer.closeAllConnections();
  await new Promise<void>((resolve, reject) => production.httpServer.close((error) => error ? reject(error) : resolve()));

  const development = await createServer({
    configFile, cacheDir: path.join(output, ".vite-dev"), logLevel: "warn",
    server: { host: "127.0.0.1", port, strictPort: true },
  });
  t.after(() => development.close());
  await development.listen();
  // The cached page must be able to recover through its existing update
  // control even though its HTML and scripts never reached the dev server.
  await page.getByRole("button", { name: /^Version .*: check for updates$/ }).click();
  await page.getByRole("button", { name: "Update", exact: true }).click();
  await page.locator('[data-hmr-status="connected"]').waitFor({ timeout: 30000 });
  assert.equal(page.url(), variantUrl);
  assert.equal(await page.locator('[data-variant-name]').inputValue(), "Keep through dev recovery");
  assert.equal(await page.locator('[data-update-state]').count(), 0);
  assert.equal(await page.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).length), 0);
  // An unregistered worker can control the document whose reload overlapped
  // activation; the next navigation must be entirely free of that worker.
  await page.reload({ waitUntil: "networkidle" });
  await page.locator('[data-hmr-status="connected"]').waitFor({ timeout: 30000 });
  assert.equal(await page.evaluate(() => navigator.serviceWorker.controller), null);
  assert.deepEqual(errors, []);
});

test("dev footer tracks real HMR connection independently of network status", { skip: !browserAvailable }, async (t) => {
  const cacheDir = await mkdtemp(path.join(os.tmpdir(), "font-hmr-cache-"));
  t.after(() => rm(cacheDir, { recursive: true, force: true }));
  // Test-only transform: stamping a revision into the maintained footer
  // source exercises the real transform + Fast Refresh pipeline without
  // editing maintained source at runtime.
  let revision = 1;
  const footerRevision: Plugin = {
    name: "hmr-footer-test-revision",
    enforce: "pre",
    transform(code: string, id: string): string | null {
      const file = id.split("?")[0] ?? id;
      if (!file.endsWith("src/app/shell/SiteFooter.tsx")) return null;
      return code.replace("Dev server ·", `Dev server r${revision} ·`);
    },
  };
  let server: ViteDevServer | undefined;
  t.after(async () => { await server?.close(); });
  server = await createServer({
    configFile: path.join(webRoot, "vite.config.ts"),
    cacheDir,
    logLevel: "warn",
    plugins: [footerRevision],
    server: { host: "127.0.0.1", port: await freePort(), strictPort: true },
  });
  await server.listen();
  const url = `http://127.0.0.1:${server.config.server.port}/`;

  const browser = await launch(t);
  const context = await browser.newContext();
  t.after(() => context.close());
  const page = await context.newPage();
  let navigations = 0;
  page.on("load", () => { navigations += 1; });
  const footer = page.getByRole("contentinfo");
  await page.addInitScript(() => {
    const seen = new Map<object, Set<boolean>>();
    const originalAdd = document.addEventListener.bind(document);
    const originalRemove = document.removeEventListener.bind(document);
    const captureOf = (options: unknown): boolean =>
      typeof options === "boolean" ? options : ((options as { capture?: boolean } | null)?.capture ?? false);
    document.addEventListener = ((
      type: string,
      listener: EventListenerOrEventListenerObject | null,
      options?: boolean | AddEventListenerOptions,
    ): void => {
      if (type === "pointerdown" && listener !== null) {
        const key = listener as object;
        if (!seen.has(key)) seen.set(key, new Set<boolean>());
        seen.get(key)?.add(captureOf(options));
      }
      originalAdd(type, listener as EventListener, options as AddEventListenerOptions);
    }) as typeof document.addEventListener;
    document.removeEventListener = ((
      type: string,
      listener: EventListenerOrEventListenerObject | null,
      options?: boolean | EventListenerOptions,
    ): void => {
      if (type === "pointerdown" && listener !== null) {
        const flags = seen.get(listener as object);
        if (flags) {
          flags.delete(captureOf(options));
          if (flags.size === 0) seen.delete(listener as object);
        }
      }
      originalRemove(type, listener as EventListener, options as EventListenerOptions);
    }) as typeof document.removeEventListener;
    const count = (): number => {
      let total = 0;
      seen.forEach((flags) => {
        total += flags.size;
      });
      return total;
    };
    (window as unknown as { __pointerdownCount?: () => number }).__pointerdownCount = count;
  });
  const pointerListenerCount = (): Promise<number> =>
    page.evaluate(
      () => (window as unknown as { __pointerdownCount?: () => number }).__pointerdownCount?.() ?? -1,
    );

  await page.goto(url, { waitUntil: "domcontentloaded" });
  // The initial ws:connect fires before React subscribes; the ping/pong
  // handshake must still report the live connection after mount.
  await footer.locator('[data-hmr-status="connected"]').waitFor({ timeout: 30000 });
  assert.match(await footer.locator(".site-footer__development").innerText(), /Dev server r1 · Live updates · Connected/);
  const hmrDot = footer.getByRole("img", { name: "Live updates connected", exact: true });
  assert.equal(await hmrDot.getAttribute("title"), null);
  assert.match(await tooltipText(page, hmrDot), /applies edits automatically/);
  assert.equal(await footer.locator("[data-connection]").count(), 0, "dev has no network dot");
  assert.equal(await footer.locator("[data-update-state]").count(), 0, "dev has no update controls");
  assert.equal(await footer.getByRole("button", { name: /check for updates|^Update$/ }).count(), 0);
  assert.equal(await page.evaluate(() => navigator.serviceWorker?.controller ?? null), null);

  // Faking offline with the websocket alive must not move the HMR status.
  await page.evaluate(() => {
    Object.defineProperty(window.navigator, "onLine", { configurable: true, get: () => false });
    window.dispatchEvent(new Event("offline"));
  });
  await footer.locator('[data-hmr-status="connected"]').waitFor({ timeout: 20000 });
  assert.equal(await footer.locator("[data-connection]").count(), 0);
  await page.evaluate(() => {
    delete (window.navigator as unknown as { onLine?: boolean }).onLine;
    window.dispatchEvent(new Event("online"));
  });

  // A real footer module update must preserve UI state and the document.
  await footer.locator("summary").click();
  await footer.locator(".site-footer__info").waitFor({ state: "visible" });
  await page.evaluate(() => {
    (window as unknown as { __hmrProbe?: string }).__hmrProbe = "kept";
  });
  navigations = 0;
  revision = 2;
  const footerFile = path.join(webRoot, "src", "app", "shell", "SiteFooter.tsx");
  const modules = server.moduleGraph.getModulesByFile(footerFile);
  const target = [...(modules ?? [])][0];
  assert.ok(target, "SiteFooter module is loaded");
  const pointerListenersReady = await pointerListenerCount();
  await server.reloadModule(target);
  await footer.locator(".site-footer__development", { hasText: "Dev server r2" }).waitFor({ timeout: 20000 });
  assert.match(
    await footer.locator(".site-footer__development").innerText(),
    /Dev server r2 · Live updates · Connected/,
  );
  assert.equal(await page.evaluate(() => (window as unknown as { __hmrProbe?: string }).__hmrProbe), "kept");
  assert.equal(await footer.locator(".site-footer__info").isVisible(), true);
  assert.equal(await footer.locator('[data-hmr-status="connected"]').count(), 1);
  assert.equal(navigations, 0, "update applied without reloading");
  assert.equal(
    await pointerListenerCount(),
    pointerListenersReady,
    "settled HMR accumulates no document pointerdown registrations",
  );

  // Dropping the dev server socket reports a disconnected HMR status, proving
  // the re-subscribed listeners from the refreshed module still work.
  await server.close();
  server = undefined;
  await footer.locator('[data-hmr-status="disconnected"]').waitFor({ timeout: 20000 });
  assert.match(await footer.locator(".site-footer__development").innerText(), /Dev server r2 · Live updates · Disconnected/);
  const downDot = footer.getByRole("img", { name: "Live updates disconnected", exact: true });
  assert.match(await tooltipText(page, downDot), /reconnects automatically/);
});
