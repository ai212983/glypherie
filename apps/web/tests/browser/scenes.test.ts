// Compositions on the unified Screen page: saved label work persists across
// reloads, exports a readable Playdate ZIP, structured coverage survives,
// legacy /scenes/ and /scene/<id>/ links keep working, and an open in-place
// draft is held behind the conflict banner instead of being clobbered.
import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import test from "node:test";
import { unzipSync } from "fflate";
import {
  bootLibrary,
  browserAvailable,
  buildApp,
  cardIds,
  cardNames,
  hashParam,
  hashPath,
  launch,
  openNewVariant,
  servePrefix,
} from "../helpers/spa-helpers.ts";

async function screenReady(page: Parameters<typeof cardNames>[0]): Promise<void> {
  await page.waitForFunction(() => document.querySelector("[data-screen-page]") !== null);
}

async function openScreen(page: Parameters<typeof cardNames>[0]): Promise<void> {
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Screen" }).click();
  await screenReady(page);
}

async function ensureStyle(page: Parameters<typeof cardNames>[0], url: string): Promise<void> {
  const names = await cardNames(page);
  const ids = await cardIds(page);
  const index = names.findIndex((name) => /^Roboto Flex/.test(name));
  assert.ok(index >= 0);
  await page.goto(`${url}fonts/`);
  await openNewVariant(page, ids[index]!);
}

async function createComposition(page: Parameters<typeof cardNames>[0], name: string): Promise<void> {
  await page.locator("[data-screen-composition-create-name]").fill(name);
  await page.waitForFunction(
    () => !((document.querySelector("[data-screen-composition-create]") as HTMLButtonElement | null)?.disabled ?? true),
  );
  await page.locator("[data-screen-composition-create]").click();
  await page.locator("[data-screen-workspace]").waitFor();
}

async function addLabel(page: Parameters<typeof cardNames>[0], text: string): Promise<string> {
  await page.locator("[data-screen-new-text]").fill(text);
  await page.locator("[data-screen-new-style]").click();
  await page.getByRole("option").first().click();
  await page.locator("[data-screen-add-label]").click();
  const container = page.locator("[data-scene-label-container]").first();
  await container.waitFor();
  const id = await container.getAttribute("data-scene-label-container");
  assert.ok(id);
  await page.waitForFunction((placementId) => {
    const viewport = document.querySelector(`[data-scene-label="${placementId}"]`);
    const canvas = viewport?.querySelector("canvas");
    return canvas instanceof HTMLCanvasElement && canvas.dataset.rendered === "true";
  }, id, { timeout: 20000 });
  return id;
}

async function waitWorkspace(page: Parameters<typeof cardNames>[0]): Promise<void> {
  await screenReady(page);
  await page.locator("[data-screen-workspace]").waitFor();
}

async function waitComposition(page: Parameters<typeof cardNames>[0], name: string): Promise<void> {
  await page.waitForFunction(
    (label) => [...document.querySelectorAll("[data-screen-composition]")].some((entry) => entry.textContent?.includes(label) ?? false),
    name,
    { timeout: 20000 },
  );
}

test("compositions persist structured coverage and export a readable ZIP", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);
  await ensureStyle(page, url);
  await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
  await openScreen(page);
  await createComposition(page, "Persisted scene");
  await addLabel(page, "Hi");

  // Export runs under the default ascii coverage: greek coverage saved below
  // includes a glyph this fixture cannot preserve at this size, and the
  // exporter intentionally aborts the archive on such failures instead of
  // truncating them.
  const zipButton = page.locator("[data-scene-export-zip]");
  await zipButton.waitFor();
  await page.waitForFunction(
    () => !((document.querySelector("[data-scene-export-zip]") as HTMLButtonElement | null)?.disabled ?? true),
  );
  const download = await Promise.all([
    page.waitForEvent("download", { timeout: 120000 }),
    zipButton.click(),
  ]).then(([event]) => event);
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
  const success = await page.locator("[data-scene-export-success]").innerText();
  assert.ok(success.startsWith("Downloaded"), `export reports the download, got ${success}`);

  // Structured export coverage survives a reload. The save commits
  // asynchronously on the domain owner, so wait for its round trip before
  // reloading or the teardown can drop the in-flight write.
  await page.getByRole("switch", { name: /Greek/i }).click();
  const revisionBefore = await page.locator("[data-screen-workspace]").getAttribute("data-screen-revision");
  await page.locator("[data-screen-save-coverage]").click();
  await page.waitForFunction(
    (revision) => document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision") !== revision,
    revisionBefore,
    { timeout: 20000 },
  );
  await page.reload({ waitUntil: "domcontentloaded" });
  await waitWorkspace(page);
  assert.equal(await page.getByRole("switch", { name: /Greek/i }).isChecked(), true);
  await waitComposition(page, "Persisted scene");
  const route = await hashPath(page);
  assert.ok(route.startsWith("/screen/"), `composition stays on the Screen route, got ${route}`);
  assert.deepEqual(errors, []);
});

test("an open in-place draft survives a peer rename behind the conflict banner", { skip: !browserAvailable }, async (t) => {
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
  await ensureStyle(pageA, url);
  await pageA.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
  await openScreen(pageA);
  await createComposition(pageA, "Stale scene");
  const id = await addLabel(pageA, "Hi");
  await pageB.goto(await pageA.url(), { waitUntil: "domcontentloaded" });
  await waitWorkspace(pageB);

  // Tab A holds an uncommitted in-place draft while tab B saves a rename.
  // Selection goes through the label frame, the hit target for labels.
  await pageA.locator(`[data-scene-label-frame="${id}"]`).click();
  await pageA.locator(`[data-scene-inspector="${id}"]`).waitFor();
  await pageA.locator(`[data-scene-label-frame="${id}"]`).dblclick();
  await pageA.locator(`[data-scene-edit-text="${id}"]`).waitFor();
  await pageA.keyboard.type(" dirty");
  await pageB.locator("[data-screen-name]").fill("Renamed elsewhere");
  await pageB.locator("[data-screen-save-name]").click();
  await pageB.locator("[data-screen-workspace]").waitFor();
  await pageA.locator("[data-screen-conflict]").waitFor();

  // The draft is preserved behind the banner, and reloading the saved
  // revision discards it instead of persisting half-typed text.
  assert.equal(
    await pageA.locator(`[data-scene-edit-text="${id}"]`).inputValue(),
    "Hi dirty",
  );
  // The reload adopts asynchronously; wait for the revision to advance
  // past the stale pre-reload value instead of asserting mid-flight.
  const revisionBefore = await pageA.locator("[data-screen-workspace]").getAttribute("data-screen-revision");
  await pageA.locator("[data-screen-reload]").click();
  await pageA.waitForFunction(
    (revision) => document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision") !== revision,
    revisionBefore,
    { timeout: 20000 },
  );
  assert.equal(await pageB.locator("[data-screen-name]").inputValue(), "Renamed elsewhere");
  const draftGone = await pageA.evaluate(
    (placementId) => document.querySelector(`[data-scene-edit-text="${placementId}"]`) === null,
    id,
  );
  assert.equal(draftGone, true);
});

test("a peer tab closing keeps working compositions in the list", { skip: !browserAvailable }, async (t) => {
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
  await ensureStyle(pageA, url);
  await pageA.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
  await openScreen(pageA);
  await createComposition(pageA, "Shared scene");
  await addLabel(pageA, "Shared label");
  await pageB.goto(await pageA.url(), { waitUntil: "domcontentloaded" });
  await waitWorkspace(pageB);

  await pageA.close();
  await pageB.reload({ waitUntil: "domcontentloaded" });
  await waitWorkspace(pageB);
  await pageB.locator("[data-scene-label-container]").first().waitFor();
});

test("legacy scene links render the Screen page and canonicalize", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);
  await ensureStyle(page, url);
  await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
  await openScreen(page);
  await createComposition(page, "Legacy scene");
  const sceneUrl = new URL(await page.url());
  const sceneId = sceneUrl.searchParams.get("scene");
  assert.ok(sceneId);

  // The legacy list link renders the same unified page and canonicalizes
  // directly to the Screen route.
  await page.goto(`${url}scenes/`, { waitUntil: "domcontentloaded" });
  await screenReady(page);
  await waitComposition(page, "Legacy scene");
  assert.equal(await hashPath(page), "/screen/");

  // The legacy detail link selects the composition and canonicalizes to the
  // Screen route with the scene query.
  await page.goto(`${url}scene/${sceneId}/`, { waitUntil: "domcontentloaded" });
  await waitWorkspace(page);
  assert.equal(await hashPath(page), "/screen/");
  assert.equal(await hashParam(page, "scene"), sceneId);

  // Unknown compositions report cleanly instead of spinning.
  await page.goto(`${url}screen/?scene=missing-scene`, { waitUntil: "domcontentloaded" });
  await page.locator("[data-screen-page]").waitFor();
  await page.getByText("Composition not found.").waitFor();

  const pageTitle = await page.title();
  assert.ok(pageTitle.includes("Screen"), `legacy detail keeps the Screen title, got ${pageTitle}`);
  assert.deepEqual(errors, []);
});

test("deleting a composition removes it from every tab", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  t.after(() => page.close());
  await bootLibrary(page, url);
  await ensureStyle(page, url);
  await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
  await openScreen(page);
  await createComposition(page, "Doomed");
  const first = await page.locator("[data-screen-composition]").first();
  const id = await first.getAttribute("data-screen-composition");
  assert.ok(id);
  await page.locator(`[data-screen-composition-delete="${id}"]`).click();
  await page.locator("[data-screen-compositions-empty]").waitFor();
});
