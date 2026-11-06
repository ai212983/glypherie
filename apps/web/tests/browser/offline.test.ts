import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  bootLibrary,
  bootVariant,
  browserAvailable,
  buildApp,
  canvasRendered,
  cardIds,
  cardNames,
  launch,
  openNewVariant,
  persistentProfile,
  servePrefix,
  tooltipText,
} from "../helpers/spa-helpers.ts";

test("installed app shell reloads offline beneath the hosting prefix", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await bootLibrary(page, url);
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  const names = await cardNames(page);
  const ids = await cardIds(page);
  await openNewVariant(page, ids[0]!);
  await page.waitForFunction(
    (expected) => document.querySelector(".family h2")?.textContent === expected,
    names[0],
  );
  await page.waitForFunction(canvasRendered);
  await page.locator('[data-primary-nav="fonts"]').click();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  await page.waitForFunction(() => navigator.serviceWorker?.controller !== null, null, { timeout: 20000 });

  await context.setOffline(true);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0, null, {
    timeout: 20000,
  });
  assert.deepEqual(await cardNames(page), names);
  await openNewVariant(page, ids[1]!);
  await page.waitForFunction(
    (expected) => document.querySelector(".family h2")?.textContent === expected,
    names[1],
  );
  await page.waitForFunction(canvasRendered, null, { timeout: 20000 });

  const direct = await context.newPage();
  await direct.goto(`${url}font/${ids[2]}/`, { waitUntil: "domcontentloaded" });
  await direct.waitForFunction(
    (expected) => document.querySelector(".family h2")?.textContent === expected,
    names[2],
    { timeout: 20000 },
  );
  await direct.waitForFunction(canvasRendered, null, { timeout: 20000 });
  const catalog = await context.newPage();
  await catalog.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
  await catalog.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0, null, {
    timeout: 20000,
  });
  assert.deepEqual(await cardNames(catalog), names, "catalog boots offline on a fresh page");
  await context.setOffline(false);
  await context.close();
});

test("footer offers a checked update for an explicit click and prompts for background updates", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext();
  t.after(() => context.close());
  const page = await context.newPage();
  await bootLibrary(page, url);
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);

  const footer = page.getByRole("contentinfo");
  const check = footer.getByRole("button", { name: /^Version .*: check for updates$/ });
  await check.click();
  await footer.locator('[data-update-state="current"]').waitFor();
  const originalBuild = await footer.locator("time").getAttribute("datetime");
  let navigations = 0;
  page.on("load", () => { navigations += 1; });

  // A manual check downloads the update and waits: no reload until Update.
  await fs.appendFile(path.join(output, "sw.js"), "\n// Updated service worker for the manual check test.\n");
  await check.click();
  const update = footer.getByRole("button", { name: "Update", exact: true });
  await update.waitFor();
  assert.equal(navigations, 0, "a manual check downloads the update without reloading");
  assert.equal(await check.count(), 0, "the version control becomes the Update action");
  assert.equal(await footer.locator(".site-footer__version-button").innerText(), "Update");
  assert.equal(await footer.locator(".site-footer__updates button:visible").count(), 1, "only one update control is shown");
  assert.equal(await tooltipText(page, update), "Apply downloaded update");
  assert.equal(await footer.getByLabel("Build details").count(), 1, "build details stay while an update is ready");
  assert.equal(await footer.locator("time").getAttribute("datetime"), originalBuild);
  assert.equal(await footer.locator('[data-update-state="ready"]').count(), 1);
  assert.equal(await footer.locator('.site-footer__updates > [role="status"]').innerText(), "");
  assert.equal(await footer.locator("[data-update-success]").count(), 0);
  assert.ok(await page.evaluate(async () => (await navigator.serviceWorker.ready).waiting !== null));
  await Promise.all([
    page.waitForEvent("load"),
    update.click(),
  ]);
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  assert.equal(navigations, 1, "an explicit Update click applies the downloaded worker");
  assert.equal(await footer.getByRole("button", { name: "Update", exact: true }).count(), 0);
  await check.waitFor({ state: "visible" });
  assert.equal(await footer.locator("time").getAttribute("datetime"), originalBuild,
    "a reload keeps the build timestamp embedded in the app");

  // A background detection also waits for the user's Update click.
  await check.click();
  await footer.locator('[data-update-state="current"]').waitFor();
  navigations = 0;
  await fs.appendFile(path.join(output, "sw.js"), "\n// Updated service worker for the background detection test.\n");
  await page.evaluate(async () => { await (await navigator.serviceWorker.ready).update(); });
  await update.waitFor();
  assert.equal(await check.count(), 0, "the version control becomes Update for background updates");
  assert.equal(await footer.locator(".site-footer__version-button").innerText(), "Update");
  assert.equal(await footer.getByLabel("Build details").count(), 1, "build details stay while a background update is ready");
  assert.equal(await footer.locator('.site-footer__updates > [role="status"]').innerText(), "");
  assert.ok(await page.evaluate(async () => (await navigator.serviceWorker.ready).waiting !== null));
  assert.equal(navigations, 0, "background detection waits for the user's Update click");
  await Promise.all([
    page.waitForEvent("load"),
    update.click(),
  ]);
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  assert.equal(navigations, 1, "an explicit Update click applies the background update");
  assert.equal(await page.getByRole("button", { name: "Update", exact: true }).count(), 0);
  await check.waitFor({ state: "visible" });
});

test("footer recovers from a failed check and applies a ready update while offline", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext();
  t.after(() => context.close());
  const page = await context.newPage();
  await bootLibrary(page, url);
  const footer = page.getByRole("contentinfo");
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  const check = footer.getByRole("button", { name: /^Version .*: check for updates$/ });

  // A failed update fetch reports the failure without touching connectivity,
  // and the same control retries successfully once the worker answers again.
  const swPath = path.join(output, "sw.js");
  const swBytes = await fs.readFile(swPath);
  await fs.rm(swPath);
  await check.click();
  await footer.getByRole("status").filter({ hasText: "Couldn’t check for updates." }).waitFor();
  assert.equal(await check.isEnabled(), true, "a failed check stays retryable");
  assert.equal(await page.evaluate(() => navigator.onLine), true, "a failed fetch leaves connectivity alone");
  assert.equal(await footer.getByRole("img", { name: "Offline", exact: true }).count(), 0, "a failed fetch shows no Offline state");
  await fs.writeFile(swPath, swBytes);
  await check.click();
  await footer.locator('[data-update-state="current"]').waitFor();

  // Download an update, then lose connectivity: the merged control keeps the
  // downloaded update actionable.
  await fs.appendFile(swPath, "\n// Updated service worker for the offline apply test.\n");
  let navigations = 0;
  page.on("load", () => { navigations += 1; });
  await check.click();
  const update = footer.getByRole("button", { name: "Update", exact: true });
  await update.waitFor();
  assert.equal(navigations, 0, "the check downloads the update without reloading");
  await context.setOffline(true);
  const offlineDot = footer.getByRole("img", { name: "Offline", exact: true });
  await offlineDot.waitFor();
  assert.equal(await offlineDot.getAttribute("title"), null);
  const hint = await tooltipText(page, offlineDot);
  assert.ok(/offline/i.test(hint) || /local work/i.test(hint), `the offline hint names the state, got: ${hint}`);
  assert.equal(await footer.locator('.site-footer__updates > [role="status"]').innerText(), "");
  assert.equal(await update.isEnabled(), true, "a downloaded update stays actionable offline");
  assert.equal(await check.count(), 0, "the version control becomes Update while offline");
  assert.equal(await footer.locator(".site-footer__version-button").innerText(), "Update");
  assert.equal(await footer.getByLabel("Build details").count(), 1, "build details stay while an update is ready");
  await Promise.all([
    page.waitForEvent("load"),
    update.click(),
  ]);
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0, null, {
    timeout: 20000,
  });
  assert.equal(navigations, 1, "the ready update applies while offline");
  await context.setOffline(false);
  assert.equal(await footer.getByRole("button", { name: "Update", exact: true }).count(), 0);
  await check.waitFor({ state: "visible" });
  await page.waitForFunction(() => !(document.querySelector(".site-footer__version-button") as HTMLButtonElement).disabled);
});

test("footer shows a plain version without update controls when service workers are unavailable", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext();
  t.after(() => context.close());
  await context.addInitScript("delete Navigator.prototype.serviceWorker;");
  const page = await context.newPage();
  const problems: string[] = [];
  page.on("pageerror", (error) => { problems.push(String(error)); });
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") problems.push(message.text());
  });
  await bootLibrary(page, url);
  assert.equal(await page.evaluate(() => "serviceWorker" in navigator), false);
  const footer = page.getByRole("contentinfo");
  await footer.locator('[data-update-state="unsupported"]').waitFor();
  assert.match(await footer.locator("[data-app-version]").innerText(), /^0\.1\.0(?:-dev)?$/);
  assert.equal(await footer.locator("[data-app-version]").evaluate((node) => node.tagName), "SPAN");
  assert.equal(await footer.getByRole("button", { name: /check for updates/i }).count(), 0);
  assert.equal(await footer.getByRole("button", { name: "Update", exact: true }).count(), 0);
  assert.equal(await footer.getByLabel("Build details").count(), 1);
  assert.equal(problems.filter((text) => /service worker/i.test(text)).length, 0, `no service worker warning or crash, got: ${problems.join(" | ")}`);
});

test("installed app cold-boots a fresh domain owner offline with persisted state", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  // A persistent profile, not an ephemeral context: IndexedDB plus
  // CacheStorage survive the browser restart below while the SharedWorker
  // owner does not, so the offline boot must start a genuinely fresh
  // worker instead of reusing a warm one.
  const lease = await persistentProfile(t);

  const seed = await (async () => {
    const first = await lease.open();
    try {
      const page = await first.context.newPage();
      await bootLibrary(page, url);
      await page.evaluate(async () => { await navigator.serviceWorker.ready; });
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
      await page.waitForFunction(() => navigator.serviceWorker?.controller !== null, null, { timeout: 20000 });
      const names = await cardNames(page);
      const fontId = (await cardIds(page))[0]!;
      const variantId = await openNewVariant(page, fontId);
      await page.waitForFunction(canvasRendered, null, { timeout: 20000 });
      // The Screen page holds one implicit default composition: switch its
      // device so the offline boot below has durable state to preserve.
      await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => document.querySelector("[data-screen-page]") !== null);
      await page.locator("[data-screen-workspace]").waitFor({ timeout: 20000 });
      await page.getByRole("combobox", { name: "Device" }).click();
      await page.getByRole("option", { name: "Inkplate 4 TEMPERA", exact: true }).click();
      await page.locator('[data-device-preview="inkplate-4-tempera"]').waitFor({ timeout: 20000 });
      // Reload before killing the owner: the device write must be committed
      // to the profile, not just painted, before the restart.
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => document.querySelector("[data-screen-page]") !== null);
      await page.locator('[data-device-preview="inkplate-4-tempera"]').waitFor({ timeout: 20000 });
      const meta = await page.locator("[data-screen-device-meta]").textContent();
      assert.ok(meta?.includes("600 × 600 px"), `the default composition keeps its device, got: ${meta}`);
      // Closing the browser kills the SharedWorker owner; the profile keeps
      // the database and the precached engine for the offline boot below.
      await first.close();
      return { names, fontId, variantId };
    } finally {
      await first.close();
    }
  })();

  const second = await lease.open();
  try {
    await second.context.setOffline(true);
    const page = await second.context.newPage();
    await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0, null, {
      timeout: 30000,
    });
    assert.deepEqual(await cardNames(page), seed.names, "seeded fonts survive a fresh offline boot");
    await bootVariant(page, `${url}font/${seed.fontId}/variant/${seed.variantId}/`);
    await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => document.querySelector("[data-screen-page]") !== null, null, {
      timeout: 30000,
    });
    await page.locator('[data-device-preview="inkplate-4-tempera"]').waitFor({ timeout: 30000 });
    const meta = await page.locator("[data-screen-device-meta]").textContent();
    assert.ok(
      meta?.includes("600 × 600 px"),
      `the default composition device survives a fresh offline boot, got: ${meta}`,
    );
    assert.ok(
      await page.locator("[data-screen-workspace]").getAttribute("data-screen-workspace"),
      "the default composition workspace opens offline",
    );
    await second.context.setOffline(false);
  } finally {
    await second.close();
  }
});

test("a failing persistent-profile body still releases its browser", { skip: !browserAvailable }, async (t) => {
  // The fixture below fails early with a live persistent context through the
  // same lifecycle seam as the cold-boot test. The child runner must report
  // the failure and exit inside a bounded timeout; a leaked headless shell
  // would hold the runner open until the timeout kills it. The fixture runs
  // as a plain node script: a nested `node --test` inside a test worker
  // exits without running anything, while a directly executed test file
  // still runs its tests and reports the failure.
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "font-offline-cleanup-"));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const fixture = path.join(dir, "cleanup-regression.test.ts");
  const helper = new URL("../helpers/spa-helpers.ts", import.meta.url).href;
  await fs.writeFile(fixture, `import test from "node:test";
import { browserAvailable, persistentProfile } from ${JSON.stringify(helper)};
test("fixture fails early with a live persistent context", { skip: !browserAvailable }, async (t) => {
  const lease = await persistentProfile(t, { width: 800, height: 600 });
  await lease.open();
  throw new Error("intentional persistent-context failure");
});
`);
  let status: number | null = 0;
  let signal: string | null = null;
  let output = "";
  try {
    output = execFileSync(process.execPath, [fixture], {
      encoding: "utf8",
      timeout: 60000,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (failure) {
    const typed = failure as { status?: number | null; signal?: string | null; stdout?: unknown; stderr?: unknown };
    status = typed.status ?? null;
    signal = typed.signal ?? null;
    output = `${String(typed.stdout ?? "")}\n${String(typed.stderr ?? "")}`;
  }
  assert.equal(signal, null, "the failed child runner exits without a timeout or signal");
  assert.equal(status, 1, "the fixture fails as intended");
  assert.ok(output.includes("intentional persistent-context failure"), `the child reports its failure, got: ${output.slice(-2000)}`);
});
