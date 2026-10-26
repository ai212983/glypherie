import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import test from "node:test";
import {
  bootLibrary,
  browserAvailable,
  buildApp,
  canvasRendered,
  cardIds,
  cardNames,
  launch,
  openNewVariant,
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
  await page.reload({ waitUntil: "networkidle" });
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
  await catalog.goto(url, { waitUntil: "domcontentloaded" });
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
  await page.reload({ waitUntil: "networkidle" });
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
  assert.equal(await check.count(), 1, "the version control stays while an update is ready");
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
  assert.equal(await check.count(), 1, "the version control stays while a background update is ready");
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

  // Download an update, then lose connectivity: checking disables, but the
  // downloaded update stays actionable.
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
  assert.equal(await check.isDisabled(), true, "checks disable while offline");
  assert.equal(await update.isEnabled(), true, "a downloaded update stays actionable offline");
  assert.equal(await check.count(), 1, "the version control stays while an update is ready");
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
