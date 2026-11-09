import { addScreenText } from "../helpers/screen-tools.ts";
// Screen workspace history against the real WASM preview renderer: Back and
// Forward switch the open composition under the same Screen URL, rapid
// keyboard nudges accumulate through the serial mutation queue, duplicate
// labels survive repeated delete/undo/redo, and a peer edit clears stale
// local history instead of letting undo clobber it.
import assert from "node:assert/strict";
import test from "node:test";
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
  await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
  await openNewVariant(page, ids[index]!);
}

async function createComposition(page: Parameters<typeof cardNames>[0], _name: string): Promise<string> {
  // There is no list to create into: the Screen page opens the one implicit
  // default automatically. The name stays at call sites as documentation of
  // what each test then does with the default workspace. Wait for the loaded
  // workspace (revision present) so the bare loading marker is never read.
  await page.locator("[data-screen-workspace][data-screen-revision]").waitFor({ timeout: 20000 });
  const id = await page.locator("[data-screen-workspace][data-screen-revision]").getAttribute("data-screen-workspace");
  assert.ok(id);
  return id;
}

// Selection goes through the label frame: the container spans the remaining
// aperture with pointer events off, and the tight frame is the hit target.
async function selectLabel(page: Parameters<typeof cardNames>[0], id: string): Promise<void> {
  await page.locator(`[data-scene-label-frame="${id}"]`).click();
  await page.locator(`[data-scene-inspector="${id}"]`).waitFor();
}

async function addLabel(page: Parameters<typeof cardNames>[0], text: string): Promise<string> {
  const before = await page.locator("[data-scene-label-container]").count();
  await addScreenText(page, text, { variant: true });
  await page.waitForFunction(
    (count) => document.querySelectorAll("[data-scene-label-container]").length === count + 1,
    before,
    { timeout: 20000 },
  );
  const id = await page.locator("[data-scene-label-container]").last().getAttribute("data-scene-label-container");
  assert.ok(id);
  await page.waitForFunction(
    (placementId) => {
      const viewport = document.querySelector(`[data-scene-label="${placementId}"]`);
      const canvas = viewport?.querySelector("canvas");
      return canvas instanceof HTMLCanvasElement && canvas.dataset.rendered === "true";
    },
    id,
    { timeout: 20000 },
  );
  return id;
}

async function inspectorX(page: Parameters<typeof cardNames>[0]): Promise<number> {
  return Number(await page.locator("[data-scene-inspector-x]").inputValue());
}

// Rendered stage-frame accessible name for the label: the Position panel no
// longer repeats the text, so assertions read the frame with the placement
// id instead of the removed inspector paragraph.
async function frameLabel(page: Parameters<typeof cardNames>[0], id: string): Promise<string | null> {
  return page.locator(`[data-scene-label-frame="${id}"]`).getAttribute("aria-label");
}

// Removal goes through the focused stage frame's Delete key: the right
// panel no longer carries a delete icon.
async function deleteViaFrame(page: Parameters<typeof cardNames>[0], id: string): Promise<void> {
  await page.locator(`[data-scene-label-frame="${id}"]`).focus();
  await page.keyboard.press("Delete");
}

test(
  "back and forward keep the single default composition without selection",
  { skip: !browserAvailable },
  async (t) => {
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
    const id = await createComposition(page, "Default");
    assert.equal(await hashParam(page, "scene"), null);

    // A carrier ?scene= selection normalizes to the default without selection.
    await page.goto(`${url}screen/?scene=${id}`, { waitUntil: "domcontentloaded" });
    await page.locator("[data-screen-workspace][data-screen-revision]").waitFor();
    assert.equal(
      await page.locator("[data-screen-workspace][data-screen-revision]").getAttribute("data-screen-workspace"),
      id,
    );
    assert.equal(await hashPath(page), "/screen/");
    assert.equal(await hashParam(page, "scene"), null);

    // Back and Forward never resurface a selection: the same default renders
    // under the selection-free URL in both directions.
    await page.goBack();
    await page.locator("[data-screen-workspace][data-screen-revision]").waitFor();
    assert.equal(
      await page.locator("[data-screen-workspace][data-screen-revision]").getAttribute("data-screen-workspace"),
      id,
    );
    assert.equal(await hashParam(page, "scene"), null);

    await page.goForward();
    await page.locator("[data-screen-workspace][data-screen-revision]").waitFor();
    assert.equal(
      await page.locator("[data-screen-workspace][data-screen-revision]").getAttribute("data-screen-workspace"),
      id,
    );
    assert.equal(await hashParam(page, "scene"), null);
    assert.deepEqual(errors, []);
  },
);

test("rapid keyboard nudges accumulate and undo walks them back", { skip: !browserAvailable }, async (t) => {
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
  await createComposition(page, "Nudges");
  const id = await addLabel(page, "Hi");

  await selectLabel(page, id);
  const startX = await inspectorX(page);

  // Five repeats with no waits between: the queue serializes them against
  // the fresh revision instead of replaying one stale coordinate.
  for (let index = 0; index < 5; index++) {
    await page.keyboard.press("ArrowRight");
  }
  await page.waitForFunction(
    (x) => Number((document.querySelector("[data-scene-inspector-x]") as HTMLInputElement | null)?.value) === x,
    startX + 5,
    { timeout: 20000 },
  );

  // Undo steps back one nudge; redo replays it.
  await page.locator("[data-screen-undo]").click();
  await page.locator("[data-scene-inspector]").waitFor({ state: "detached" });
  await selectLabel(page, id);
  await page.waitForFunction(
    (x) => Number((document.querySelector("[data-scene-inspector-x]") as HTMLInputElement | null)?.value) === x,
    startX + 4,
    { timeout: 20000 },
  );
  await page.locator("[data-screen-redo]").click();
  await page.locator("[data-scene-inspector]").waitFor({ state: "detached" });
  await selectLabel(page, id);
  await page.waitForFunction(
    (x) => Number((document.querySelector("[data-scene-inspector-x]") as HTMLInputElement | null)?.value) === x,
    startX + 5,
    { timeout: 20000 },
  );
  assert.equal(await inspectorX(page), startX + 5);
  assert.deepEqual(errors, []);
});

test(
  "undo and redo of stacking changes clear selection before another label action",
  { skip: !browserAvailable },
  async (t) => {
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
    await createComposition(page, "Stacking selection");
    const first = await addLabel(page, "Alpha");
    const second = await addLabel(page, "Beta");
    await selectLabel(page, second);
    await page.locator("[data-scene-inspector-x]").fill("200");
    await page.locator("[data-scene-inspector-x]").press("Enter");
    await page.waitForFunction(
      () => Number((document.querySelector("[data-scene-inspector-x]") as HTMLInputElement | null)?.value) === 200,
    );
    await selectLabel(page, first);
    // Stacking moves through the left Layers panel now that the right panel
    // carries no order icons: a keyboard drag lifts Alpha to the front of
    // the top-first list. Overshooting upward clamps to the top, so the
    // landing is deterministic.
    const revisionBeforeStack = Number(
      await page.locator("[data-screen-workspace]").getAttribute("data-screen-revision"),
    );
    // The X commit above must land before the drag: a reorder cannot start
    // while a save is in flight.
    await page.waitForFunction(
      () => (document.querySelector("[data-screen-undo]") as HTMLButtonElement | null)?.disabled === false,
      null,
      { timeout: 20000 },
    );
    await page.locator(`[data-scene-layer-handle="${first}"]`).focus();
    await page.keyboard.press("Space");
    for (let index = 0; index < 5; index += 1) await page.keyboard.press("ArrowUp");
    await page.keyboard.press("Space");
    await page.waitForFunction(
      (previous) =>
        Number(document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision")) !== previous,
      revisionBeforeStack,
      { timeout: 20000 },
    );
    await page.waitForFunction(
      () =>
        document.querySelectorAll("[data-scene-label-frame]")[1]?.getAttribute("aria-label") ===
        "Label Alpha. Press Enter to edit.",
    );

    const alpha = page.getByRole("button", { name: "Label Alpha. Press Enter to edit.", exact: true });
    const beta = page.getByRole("button", { name: "Label Beta. Press Enter to edit.", exact: true });
    for (const action of ["undo", "redo", "undo"]) {
      // Id-free restores may reassign placement ids, so the identity comes
      // from the mounted inspector itself rather than the pre-restore id.
      await page.locator("[data-scene-inspector]").waitFor();
      const shown = await page.locator("[data-scene-inspector]").getAttribute("data-scene-inspector");
      assert.ok(shown);
      assert.equal(await frameLabel(page, shown), "Label Alpha. Press Enter to edit.");
      const revision = Number(await page.locator("[data-screen-workspace]").getAttribute("data-screen-revision"));
      if (action === "redo") {
        await alpha.focus();
        await page.keyboard.press("ControlOrMeta+Shift+z");
      } else {
        await page.locator(`[data-screen-${action}]`).click();
      }
      await page.waitForFunction(
        (previous) =>
          Number(document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision")) > previous,
        revision,
      );
      assert.equal(
        await page.locator("[data-scene-inspector]").count(),
        0,
        `${action} must drop the selection whose id may now identify another label`,
      );
      assert.equal(await page.locator('[data-scene-label-frame][aria-selected="true"]').count(), 0);
      assert.equal(
        await page.evaluate(() => document.activeElement?.hasAttribute("data-scene-label-frame")),
        false,
        "history replay must release keyboard focus from the reused label id",
      );
      await alpha.click();
      await page.locator("[data-scene-inspector]").waitFor();
      const reshown = await page.locator("[data-scene-inspector]").getAttribute("data-scene-inspector");
      assert.ok(reshown);
      assert.equal(await frameLabel(page, reshown), "Label Alpha. Press Enter to edit.");
    }

    // The Alpha frame is selected and focused after the click above, so
    // Delete reaches it without naming a possibly reassigned id.
    await page.keyboard.press("Delete");
    await alpha.waitFor({ state: "detached" });
    await beta.click();
    await page.locator("[data-scene-inspector]").waitFor();
    const shownBeta = await page.locator("[data-scene-inspector]").getAttribute("data-scene-inspector");
    assert.ok(shownBeta);
    assert.equal(await frameLabel(page, shownBeta), "Label Beta. Press Enter to edit.");
    assert.equal(await page.locator("[data-scene-label-container]").count(), 1);
    assert.deepEqual(errors, []);
  },
);

test("duplicate identical labels survive repeated delete, undo and redo", { skip: !browserAvailable }, async (t) => {
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
  await createComposition(page, "Dupes");
  await addLabel(page, "Same");
  const twin = await addLabel(page, "Same");
  assert.equal(await page.locator("[data-scene-label-container]").count(), 2);

  // The twins share one spot, so select the topmost frame.
  await selectLabel(page, twin);
  await deleteViaFrame(page, twin);
  await page.waitForFunction(() => document.querySelectorAll("[data-scene-label-container]").length === 1);

  // Undo restores both duplicates with their text and grid position intact.
  await page.locator("[data-screen-undo]").click();
  await page.waitForFunction(() => document.querySelectorAll("[data-scene-label-container]").length === 2);
  const topmost = await page.locator("[data-scene-label-container]").last().getAttribute("data-scene-label-container");
  assert.ok(topmost);
  await selectLabel(page, topmost);
  assert.equal(await page.locator("[data-scene-inspector]").getAttribute("data-scene-inspector"), topmost);
  assert.equal(await frameLabel(page, topmost), "Label Same. Press Enter to edit.");
  assert.equal(await page.locator("[data-scene-inspector-x]").inputValue(), "8");

  // A second delete/undo/redo round keeps the same pair.
  await deleteViaFrame(page, topmost);
  await page.waitForFunction(() => document.querySelectorAll("[data-scene-label-container]").length === 1);
  await page.locator("[data-screen-undo]").click();
  await page.waitForFunction(() => document.querySelectorAll("[data-scene-label-container]").length === 2);
  await page.locator("[data-screen-redo]").click();
  await page.waitForFunction(() => document.querySelectorAll("[data-scene-label-container]").length === 1);
  await page.locator("[data-screen-undo]").click();
  await page.waitForFunction(() => document.querySelectorAll("[data-scene-label-container]").length === 2);
  assert.deepEqual(errors, []);
});

test(
  "a peer edit clears stale local history instead of letting undo clobber it",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    t.after(() => context.close());
    const pageA = await context.newPage();
    const pageB = await context.newPage();
    t.after(() => pageA.close());
    t.after(() => pageB.close());
    const errors: string[] = [];
    pageA.on("pageerror", (error) => errors.push(error.message));
    pageB.on("pageerror", (error) => errors.push(error.message));
    await bootLibrary(pageA, url);
    await ensureStyle(pageA, url);
    await pageA.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
    await openScreen(pageA);
    await createComposition(pageA, "Shared");
    await addLabel(pageA, "Hi");
    await pageB.goto(await pageA.url(), { waitUntil: "domcontentloaded" });
    await pageB.locator("[data-screen-workspace]").waitFor();

    // Tab A holds undo history from the label add.
    assert.equal(await pageA.locator("[data-screen-undo]").isDisabled(), false);

    // Tab B saves a coverage change; tab A adopts the remote revision on the next sync.
    await pageB.getByRole("switch", { name: /Greek/i }).click();
    const revisionBeforeB = await pageB.locator("[data-screen-workspace]").getAttribute("data-screen-revision");
    await pageB.locator("[data-screen-save-coverage]").click();
    await pageB.waitForFunction(
      (revision) =>
        document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision") !== revision,
      revisionBeforeB,
      { timeout: 20000 },
    );

    // Adoption drops the stale history, so undo cannot replay a snapshot that
    // predates the peer save; the peer's content survives on both tabs.
    await pageA.waitForFunction(
      () => ((document.querySelector("[data-screen-undo]") as HTMLButtonElement | null)?.disabled ?? false) === true,
      null,
      { timeout: 20000 },
    );
    assert.equal(await pageA.locator("[data-scene-label-container]").count(), 1);
    assert.deepEqual(errors, []);
  },
);
