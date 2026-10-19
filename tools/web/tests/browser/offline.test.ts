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
} from "../helpers/spa-helpers.ts";

test("installed app shell reloads offline beneath the hosting prefix", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await bootLibrary(page, url);
  await page.getByRole("status").filter({ hasText: "Ready for offline use." }).waitFor();
  const names = await cardNames(page);
  const ids = await cardIds(page);
  await openNewVariant(page, ids[0]!);
  await page.waitForFunction(
    (expected) => document.querySelector(".family h2")?.textContent === expected,
    names[0],
  );
  await page.waitForFunction(canvasRendered);
  await page.locator("[data-all-fonts]").click();
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
  await direct.goto(`${url}#/font/${ids[2]}/`, { waitUntil: "domcontentloaded" });
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

test("service worker update waits for the update button before reloading", { skip: !browserAvailable }, async (t) => {
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

  await fs.appendFile(path.join(output, "sw.js"), "\n// Updated service worker for the update prompt test.\n");
  await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.ready;
    await registration.update();
  });
  const update = page.getByRole("button", { name: "Update now" });
  await update.waitFor();
  assert.ok(await page.evaluate(async () => (await navigator.serviceWorker.ready).waiting !== null));
  await Promise.all([
    page.waitForEvent("load"),
    update.click(),
  ]);
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  assert.equal(await page.getByRole("button", { name: "Update now" }).count(), 0);
});
