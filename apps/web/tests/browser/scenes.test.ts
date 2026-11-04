// Scenes: list/create/delete, detail edits with saved coverage, label
// placement with a real bitmap preview, and a readable ZIP download.
// The graph-backed domain service backs every step; this test exercises the
// UI integration, not the storage itself.
import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import test from "node:test";
import { unzipSync } from "fflate";
import type { Page } from "playwright-core";
import {
  bootLibrary,
  browserAvailable,
  buildApp,
  cardIds,
  cardNames,
  hashPath,
  launch,
  openNewVariant,
  servePrefix,
} from "../helpers/spa-helpers.ts";

async function scenesReady(page: Parameters<typeof hashPath>[0]): Promise<void> {
  await page.waitForFunction(() => document.querySelector("[data-scenes-page]") !== null);
}

test("scenes create, persist structured coverage, place labels and export a readable ZIP", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);

  // Saved variants are text styles semantically, so one variant guarantees
  // an exportable style for the scene below.
  const names = await cardNames(page);
  const ids = await cardIds(page);
  const index = names.findIndex((n) => /^Roboto Flex/.test(n));
  assert.ok(index >= 0);
  await page.goto(`${url}fonts/`);
  await openNewVariant(page, ids[index]!);

  // The primary nav reaches the scenes list with an empty library state.
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Scenes" }).click();
  await scenesReady(page);
  assert.equal(await hashPath(page), "/scenes/");
  // The list resolves asynchronously; wait for it to settle either way.
  await page.locator("[data-scenes-empty], [data-scenes-list]").first().waitFor();
  assert.equal(await page.locator("[data-scenes-empty]").count(), 1);

  // Create a scene; the first output profile is preselected once loaded.
  await page.locator("[data-scene-create-name]").fill("HUD");
  await page.locator("[data-scene-create]").waitFor();
  await page.waitForFunction(
    () => !((document.querySelector("[data-scene-create]") as HTMLButtonElement | null)?.disabled ?? true),
  );
  await page.locator("[data-scene-create]").click();
  await page.locator("[data-scene-detail]").waitFor();
  assert.match(await hashPath(page), /^\/scene\//);
  assert.equal(await page.locator("[data-scene-name]").inputValue(), "HUD");

  // Labels use text styles with explicit positions and a bitmap preview.
  await page.locator("[data-scene-new-text]").fill("Hi");
  await page.locator("[data-scene-new-style]").click();
  await page.getByRole("option").first().click();
  await page.locator("[data-scene-add-label]").click();
  const row = page.locator("[data-scene-label-text]");
  await row.waitFor();
  assert.equal(await row.inputValue(), "Hi");
  const labelId = await row.getAttribute("data-scene-label-text");
  assert.ok(labelId);
  await page.locator(`[data-scene-label="${labelId}"]`).waitFor();

  // Export packages every text style: the ZIP is a real archive of fonts.
  // This runs under the default ascii coverage: greek coverage saved below
  // includes a glyph this fixture cannot preserve at this size, and the
  // exporter intentionally aborts the archive on such failures instead of
  // truncating them.
  const downloadEvent = page.waitForEvent("download");
  await page.locator("[data-scene-export-zip]").waitFor();
  await page.waitForFunction(
    () => !((document.querySelector("[data-scene-export-zip]") as HTMLButtonElement | null)?.disabled ?? true),
  );
  await page.locator("[data-scene-export-zip]").click();
  const download = await downloadEvent;
  assert.match(download.suggestedFilename(), /\.zip$/);
  const file = path.join(output, "scene.zip");
  await download.saveAs(file);
  const archive = unzipSync(new Uint8Array(await fs.readFile(file)));
  const entries = Object.keys(archive);
  assert.ok(entries.length >= 1, "ZIP holds at least one bitmap font");
  for (const entry of entries) {
    assert.match(entry, /\.fnt$/);
    assert.ok(archive[entry]!.length > 0, `${entry} is non-empty`);
  }
  await page.locator("[data-scene-export-success]").waitFor();
  assert.deepEqual(errors, []);

  // Structured export coverage survives a reload. The save commits
  // asynchronously on the domain owner, so wait for its round trip before
  // reloading or the teardown can drop the in-flight write.
  await page.locator("[data-coverage-preset='greek']").click();
  await page.locator("[data-scene-save-coverage]").click();
  await page.waitForFunction(
    () => (document.querySelector("[data-scene-save-coverage]") as HTMLButtonElement | null)?.disabled === true,
  );
  await page.waitForFunction(
    () => (document.querySelector("[data-scene-save-coverage]") as HTMLButtonElement | null)?.disabled === false,
  );
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator("[data-scene-detail]").waitFor();
  assert.equal(await page.locator("[data-scene-name]").inputValue(), "HUD");
  assert.equal(await page.locator("[data-coverage-preset='ascii']").getAttribute("aria-checked"), "true");
  assert.equal(await page.locator("[data-coverage-preset='greek']").getAttribute("aria-checked"), "true");
  assert.match(await page.locator("[data-coverage-count]").innerText(), /characters/);

  // Deleting returns the list to empty.
  await page.locator("[data-scene-back]").click();
  await scenesReady(page);
  const card = page.locator("[data-scene-card]");
  await card.first().waitFor();
  const sceneCard = await card.getAttribute("data-scene-card");
  await page.locator(`[data-scene-delete="${sceneCard}"]`).click();
  await page.locator("[data-scenes-empty]").waitFor();
  assert.deepEqual(errors, []);
});

test("scenes hold dirty drafts across tabs and adopt clean updates", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  // One context, two pages: genuine tab semantics with shared storage, so
  // both tabs reach the same single domain owner (browser.newPage would
  // isolate storage per page and no implementation could share state).
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  t.after(() => context.close());
  const pageA = await context.newPage();
  const pageB = await context.newPage();
  t.after(() => pageA.close());
  t.after(() => pageB.close());
  await bootLibrary(pageA, url);

  const names = await cardNames(pageA);
  const ids = await cardIds(pageA);
  const index = names.findIndex((n) => /^Roboto Flex/.test(n));
  assert.ok(index >= 0);
  await pageA.goto(`${url}fonts/`);
  await openNewVariant(pageA, ids[index]!);

  await pageA.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Scenes" }).click();
  await scenesReady(pageA);
  await pageA.locator("[data-scene-create-name]").fill("Sync");
  await pageA.locator("[data-scene-create]").waitFor();
  await pageA.waitForFunction(
    () => !((document.querySelector("[data-scene-create]") as HTMLButtonElement | null)?.disabled ?? true),
  );
  await pageA.locator("[data-scene-create]").click();
  await pageA.locator("[data-scene-detail]").waitFor();
  const sceneId = (await hashPath(pageA)).match(/^\/scene\/([^/]+)\//)?.[1];
  assert.ok(sceneId);

  await pageA.locator("[data-scene-new-text]").fill("Hi");
  await pageA.locator("[data-scene-new-style]").click();
  await pageA.getByRole("option").first().click();
  await pageA.locator("[data-scene-add-label]").click();
  await pageA.locator("[data-scene-label-text]").waitFor();

  // Same scene in a second tab; both tabs settle on the saved revision.
  await pageB.goto(`${url}scene/${sceneId}/`, { waitUntil: "domcontentloaded" });
  await pageB.locator("[data-scene-detail]").waitFor();
  assert.equal(await pageB.locator("[data-scene-name]").inputValue(), "Sync");

  // Dirty drafts in A: an unsaved name and an unsaved label edit.
  await pageA.locator("[data-scene-name]").fill("Sync-dirty");
  await pageA.locator("[data-scene-label-text]").fill("Hi-dirty");

  // B saves a rename; A must hold its drafts behind the conflict banner.
  await pageB.locator("[data-scene-name]").fill("Sync-remote");
  await pageB.locator("[data-scene-save-name]").click();
  await pageB.waitForFunction(
    () => (document.querySelector("[data-scene-save-name]") as HTMLButtonElement | null)?.disabled === true,
  );
  await pageA.locator("[data-scene-conflict]").waitFor();
  assert.equal(await pageA.locator("[data-scene-name]").inputValue(), "Sync-dirty");
  assert.equal(await pageA.locator("[data-scene-label-text]").inputValue(), "Hi-dirty");

  // Reload discards every draft coherently, including the label row.
  await pageA.locator("[data-scene-reload]").click();
  await pageA.waitForFunction(
    () => (document.querySelector("[data-scene-name]") as HTMLInputElement | null)?.value === "Sync-remote",
  );
  assert.equal(await pageA.locator("[data-scene-conflict]").count(), 0);
  assert.equal(await pageA.locator("[data-scene-label-text]").inputValue(), "Hi");

  // Clean updates adopt without a banner.
  await pageB.locator("[data-scene-name]").fill("Sync-final");
  await pageB.locator("[data-scene-save-name]").click();
  await pageB.waitForFunction(
    () => (document.querySelector("[data-scene-save-name]") as HTMLButtonElement | null)?.disabled === true,
  );
  await pageA.waitForFunction(
    () => (document.querySelector("[data-scene-name]") as HTMLInputElement | null)?.value === "Sync-final",
  );
  assert.equal(await pageA.locator("[data-scene-conflict]").count(), 0);
});

test("scenes survive a peer tab closing: the shared owner keeps serving", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  // Same shared context as the two-tab test above: one origin, one owner.
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  t.after(() => context.close());
  const pageA = await context.newPage();
  const pageB = await context.newPage();
  t.after(() => pageA.close());
  t.after(() => pageB.close());
  await bootLibrary(pageA, url);

  await pageA.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Scenes" }).click();
  await scenesReady(pageA);
  await pageA.locator("[data-scene-create-name]").fill("Handover");
  await pageA.locator("[data-scene-create]").waitFor();
  await pageA.waitForFunction(
    () => !((document.querySelector("[data-scene-create]") as HTMLButtonElement | null)?.disabled ?? true),
  );
  await pageA.locator("[data-scene-create]").click();
  await pageA.locator("[data-scene-detail]").waitFor();

  // The second tab reads through the same owner before the first tab closes.
  await pageB.goto(`${url}scenes/`, { waitUntil: "domcontentloaded" });
  await scenesReady(pageB);
  await pageB.locator("[data-scene-card]").first().waitFor();
  const sceneNames = (page: Page): Promise<string[]> =>
    page.locator("[data-scene-open]").evaluateAll((links) => links.map((link) => link.textContent ?? ""));
  assert.deepEqual(await sceneNames(pageB), ["Handover"]);

  // Closing the first tab must not take the owner down with it: the survivor
  // keeps writing and reads back both scenes after a reload.
  await pageA.close();
  await pageB.locator("[data-scene-create-name]").fill("After-handover");
  await pageB.waitForFunction(
    () => !((document.querySelector("[data-scene-create]") as HTMLButtonElement | null)?.disabled ?? true),
  );
  await pageB.locator("[data-scene-create]").click();
  await pageB.locator("[data-scene-detail]").waitFor();
  await pageB.goto(`${url}scenes/`, { waitUntil: "domcontentloaded" });
  await scenesReady(pageB);
  await pageB.locator("[data-scene-card]").first().waitFor();
  assert.deepEqual((await sceneNames(pageB)).sort(), ["After-handover", "Handover"]);
});

test("scenes load directly with published metadata and keep navigation state", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage();
  t.after(() => page.close());

  await page.goto(`${url}scenes/`, { waitUntil: "domcontentloaded" });
  await scenesReady(page);
  assert.equal(await hashPath(page), "/scenes/");
  assert.equal(await page.title(), "Scenes — Glypherie");
  assert.equal(await page.locator("main h1").count(), 1);

  const nav = page.getByRole("navigation", { name: "Primary" });
  assert.equal(await nav.getByRole("link", { name: "Scenes" }).getAttribute("aria-current"), "page");
  await nav.getByRole("link", { name: "Fonts" }).click();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  await nav.getByRole("link", { name: "Scenes" }).click();
  await scenesReady(page);
  assert.equal(await hashPath(page), "/scenes/");
});
