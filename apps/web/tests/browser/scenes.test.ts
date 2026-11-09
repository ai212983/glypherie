import { addScreenText } from "../helpers/screen-tools.ts";
// Compositions on the unified Screen page: saved label work persists across
// reloads, exports a readable Playdate ZIP, structured coverage survives,
// legacy /scenes/ and /scene/<id>/ links keep working, and an open in-place
// draft is held behind the conflict banner instead of being clobbered.
import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import test from "node:test";
import type { BrowserContext } from "playwright-core";
import { unzipSync } from "fflate";
import {
  bootLibrary,
  browserAvailable,
  buildApp,
  captureDomainWorker,
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

async function createComposition(page: Parameters<typeof cardNames>[0], _name: string): Promise<void> {
  // There is no list to create into: the Screen page opens the one implicit
  // default automatically. The name stays at call sites as documentation of
  // what each test then does with the default workspace. Wait for the loaded
  // workspace (revision present) so the bare loading marker is never read.
  await page.locator("[data-screen-workspace][data-screen-revision]").waitFor({ timeout: 20000 });
}

async function defaultId(page: Parameters<typeof cardNames>[0]): Promise<string> {
  // Wait for the loaded workspace before reading: loading/error states carry
  // the bare marker whose value reads as 'true' instead of a scene id.
  await page.locator("[data-screen-workspace][data-screen-revision]").waitFor({ timeout: 20000 });
  const id = await page.locator("[data-screen-workspace][data-screen-revision]").getAttribute("data-screen-workspace");
  assert.ok(id);
  return id;
}

// Raw second-scene seed through the domain worker: the UI no longer creates
// compositions, but stored non-default rows must stay hidden from every route.
async function seedSecondScene(
  page: Parameters<typeof cardNames>[0],
  workerScript: string,
  name: string,
): Promise<string> {
  return page.evaluate(
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
      const profiles = await call<Array<{ id: string }>>("listOutputProfiles", [], 92011);
      const profileId = profiles[0]?.id;
      if (!profileId) throw new Error("No output profile to seed a composition.");
      const created = await call<{ id: string }>(
        "createScene",
        [{ name: sceneName, width: 800, height: 600, outputProfileId: profileId }],
        92012,
      );
      return String(created.id);
    },
    { sceneName: name, workerUrl: workerScript, workerName: "glypherie-domain-v1" },
  );
}

async function addLabel(page: Parameters<typeof cardNames>[0], text: string): Promise<string> {
  await addScreenText(page, text, { variant: true });
  const container = page.locator("[data-scene-label-container]").first();
  await container.waitFor();
  const id = await container.getAttribute("data-scene-label-container");
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

async function waitWorkspace(page: Parameters<typeof cardNames>[0]): Promise<void> {
  await screenReady(page);
  await page.locator("[data-screen-workspace][data-screen-revision]").waitFor();
}

async function workerUrl(page: Parameters<typeof cardNames>[0]): Promise<string> {
  return page.evaluate(() => {
    const urls = (window as unknown as { __sharedWorkerUrls?: unknown }).__sharedWorkerUrls;
    const url = Array.isArray(urls) ? urls.find((entry): entry is string => typeof entry === "string") : undefined;
    if (!url) throw new Error("domain worker URL was not captured; call captureDomainWorker(context) before booting.");
    return url;
  });
}

async function layerIdByText(page: Parameters<typeof cardNames>[0], text: string): Promise<string> {
  const id = await page.evaluate((label) => {
    const rows = [...document.querySelectorAll("[data-scene-layer]")];
    const row = rows.find((entry) => entry.querySelector("[data-scene-layer-text]")?.textContent === label);
    return row?.getAttribute("data-scene-layer") ?? null;
  }, text);
  assert.ok(id, `layers list shows a row for ${JSON.stringify(text)}`);
  return id;
}

async function layerOrder(page: Parameters<typeof cardNames>[0]): Promise<string[]> {
  return page
    .locator("[data-scene-layer-text]")
    .evaluateAll((entries) => entries.map((entry) => entry.textContent ?? ""));
}

async function layerOrderLive(page: Parameters<typeof cardNames>[0]): Promise<string[]> {
  // While a drag is held open the sortable plugin keeps the dragged row in
  // the DOM twice (a fixed-position copy plus its slot), so order probes
  // must ignore the copy and read the live slots only.
  return page.evaluate(() =>
    [...document.querySelectorAll("[data-scene-layer]")]
      .filter((row) => getComputedStyle(row).position !== "fixed")
      .map((row) => row.querySelector("[data-scene-layer-text]")?.textContent ?? ""),
  );
}

async function workspaceRevision(page: Parameters<typeof cardNames>[0]): Promise<string | null> {
  return page.locator("[data-screen-workspace]").getAttribute("data-screen-revision");
}

async function waitWorkspaceRevision(page: Parameters<typeof cardNames>[0], before: string | null): Promise<void> {
  await page.waitForFunction(
    (revision) => document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision") !== revision,
    before,
    { timeout: 15000 },
  );
}

async function waitEnabled(page: Parameters<typeof cardNames>[0], selector: string): Promise<void> {
  // Undo/redo stay disabled while a mutation is queued, a draft is open or
  // the conflict banner waits; the revision bump alone does not prove the
  // queue drained, so wait for the control itself.
  await page.waitForFunction(
    (query) => {
      const button = document.querySelector(query);
      return button instanceof HTMLButtonElement && !button.disabled;
    },
    selector,
    { timeout: 15000 },
  );
}

async function waitLayerText(page: Parameters<typeof cardNames>[0], text: string): Promise<void> {
  // The layers row renders from the saved revision, which lands after the
  // stage container paints, so wait for the row text itself.
  await page.waitForFunction(
    (label) => [...document.querySelectorAll("[data-scene-layer-text]")].some((entry) => entry.textContent === label),
    text,
    { timeout: 15000 },
  );
}

async function waitLayerOrder(page: Parameters<typeof cardNames>[0], expected: string[]): Promise<void> {
  // Drops animate smoothly before dnd-kit removes its transient feedback
  // row, so wait for the settled order rather than asserting mid-animation.
  await page.waitForFunction(
    (want) => {
      const texts = [...document.querySelectorAll("[data-scene-layer-text]")].map((entry) => entry.textContent);
      return texts.length === want.length && texts.every((text, index) => text === want[index]);
    },
    expected,
    { timeout: 20000 },
  );
}

async function blurListDraft(page: Parameters<typeof cardNames>[0]): Promise<void> {
  // The Select tool blurs the draft without selecting another layer.
  await page
    .getByRole("toolbar", { name: "Canvas tools" })
    .getByRole("button", { name: "Select", exact: true })
    .click();
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
  const download = await Promise.all([page.waitForEvent("download", { timeout: 120000 }), zipButton.click()]).then(
    ([event]) => event,
  );
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
  const route = await hashPath(page);
  assert.ok(route.startsWith("/screen/"), `composition stays on the Screen route, got ${route}`);
  assert.deepEqual(errors, []);
});

test(
  "an open in-place draft survives a peer coverage save behind the conflict banner",
  { skip: !browserAvailable },
  async (t) => {
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

    // Tab A holds an uncommitted in-place draft while tab B saves a coverage
    // change. Selection goes through the label frame, the hit target for labels.
    await pageA.locator(`[data-scene-label-frame="${id}"]`).click();
    await pageA.locator(`[data-scene-inspector="${id}"]`).waitFor();
    await pageA.locator(`[data-scene-label-frame="${id}"]`).press("Enter");
    await pageA.locator(`[data-scene-edit-text="${id}"]`).waitFor();
    await pageA.keyboard.type(" dirty");
    await pageB.getByRole("switch", { name: /Greek/i }).click();
    const revisionBeforeB = await pageB.locator("[data-screen-workspace]").getAttribute("data-screen-revision");
    await pageB.locator("[data-screen-save-coverage]").click();
    await pageB.waitForFunction(
      (revision) =>
        document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision") !== revision,
      revisionBeforeB,
      { timeout: 20000 },
    );
    await pageB.locator("[data-screen-workspace]").waitFor();
    await pageA.locator("[data-screen-conflict]").waitFor();

    // The draft is preserved behind the banner, and reloading the saved
    // revision discards it instead of persisting half-typed text.
    assert.equal(await pageA.locator(`[data-scene-edit-text="${id}"]`).inputValue(), "Hi dirty");
    // The reload adopts asynchronously; wait for the revision to advance
    // past the stale pre-reload value instead of asserting mid-flight.
    const revisionBefore = await pageA.locator("[data-screen-workspace]").getAttribute("data-screen-revision");
    await pageA.locator("[data-screen-reload]").click();
    await pageA.waitForFunction(
      (revision) =>
        document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision") !== revision,
      revisionBefore,
      { timeout: 20000 },
    );
    assert.equal(await pageB.getByRole("switch", { name: /Greek/i }).isChecked(), true);
    const draftGone = await pageA.evaluate(
      (placementId) => document.querySelector(`[data-scene-edit-text="${placementId}"]`) === null,
      id,
    );
    assert.equal(draftGone, true);
  },
);

test("scene layers list orders, selects, renames and reorders labels", { skip: !browserAvailable }, async (t) => {
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
  await createComposition(page, "Layered scene");
  // The shared helper returns the first container, so resolve the true
  // placement id from the layers row once the save has landed.
  const addLayerLabel = async (text: string): Promise<string> => {
    await addLabel(page, text);
    await page.waitForFunction(
      (label) => [...document.querySelectorAll("[data-scene-layer-text]")].some((entry) => entry.textContent === label),
      text,
      { timeout: 20000 },
    );
    const id = await page.evaluate((label) => {
      const rows = [...document.querySelectorAll("[data-scene-layer]")];
      const row = rows.find((entry) => entry.querySelector("[data-scene-layer-text]")?.textContent === label);
      return row?.getAttribute("data-scene-layer") ?? null;
    }, text);
    assert.ok(id);
    await page.locator(`[data-scene-label-frame="${id}"]`).waitFor({ timeout: 20000 });
    return id;
  };
  const alpha = await addLayerLabel("Alpha");
  const beta = await addLayerLabel("Beta");
  const gamma = await addLayerLabel("Gamma");

  const layerTexts = (): Promise<string[]> => page.locator("[data-scene-layer-text]").allInnerTexts();
  const revisionOf = (): Promise<string | null> =>
    page.locator("[data-screen-workspace]").getAttribute("data-screen-revision");
  const waitRevision = async (before: string | null): Promise<void> => {
    await page.waitForFunction(
      (revision) =>
        document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision") !== revision,
      before,
      { timeout: 20000 },
    );
  };
  const zIndexOf = (placementId: string): Promise<number> =>
    page.evaluate((id) => {
      const container = document.querySelector(`[data-scene-label-container="${id}"]`);
      return container instanceof HTMLElement ? Number(container.style.zIndex) : Number.NaN;
    }, placementId);

  // Frontmost label leads the list, and every row carries a label icon.
  assert.deepEqual(await layerTexts(), ["Gamma", "Beta", "Alpha"]);
  assert.equal(await page.locator("[data-scene-layer-icon]").count(), 3);

  // List selection syncs with the stage inspector, and back. All three labels
  // stack at the same position, so the stage check uses the topmost frame.
  await page.locator(`[data-scene-layer="${beta}"]`).click();
  await page.locator(`[data-scene-inspector="${beta}"]`).waitFor();
  // Focus (keyboard path) rather than a pointer click: the selected Beta
  // frame's Moveable overlay covers the stacked Gamma frame.
  await page.locator(`[data-scene-label-frame="${gamma}"]`).focus();
  await page.waitForFunction(
    (placementId) =>
      document.querySelector(`[data-scene-layer="${placementId}"]`)?.getAttribute("aria-current") === "true",
    gamma,
    { timeout: 20000 },
  );

  // No step buttons remain: reorder is drag-only, one row-body activator
  // per row.
  assert.equal(await page.locator("[data-scene-layer-up]").count(), 0);
  assert.equal(await page.locator("[data-scene-layer-down]").count(), 0);
  assert.equal(await page.locator("[data-scene-layer-handle]").count(), 3);

  // Keyboard reorder: the back label drags to the front via its row.
  // Overshooting upward clamps to the top, so the landing is deterministic.
  let revision = await revisionOf();
  await page.locator(`[data-scene-layer-handle="${alpha}"]`).focus();
  await page.keyboard.press("Space");
  for (let i = 0; i < 15; i += 1) await page.keyboard.press("ArrowUp");
  await page.keyboard.press("Space");
  await waitRevision(revision);
  await waitLayerOrder(page, ["Alpha", "Gamma", "Beta"]);
  assert.deepEqual(await layerTexts(), ["Alpha", "Gamma", "Beta"]);

  // Pointer drag starts from the row body itself (the text area): the whole
  // row is the activator, matching the reference sortable story. The dragged
  // row follows the pointer while neighbors animate, then the drop persists
  // through the atomic reorder. The travel distance derives from the measured
  // row pitch, crossing two rows.
  revision = await revisionOf();
  const pitch = await page.evaluate(() => {
    const tops = [...document.querySelectorAll("[data-scene-layer]")]
      .map((row) => row.getBoundingClientRect().top)
      .sort((a, b) => a - b);
    return tops.length > 1 ? tops[1]! - tops[0]! : 40;
  });
  await page.locator(`[data-scene-layer="${beta}"]`).scrollIntoViewIfNeeded();
  const betaTextBox = await page.locator(`[data-scene-layer-text="${beta}"]`).boundingBox();
  assert.ok(betaTextBox, "row text exposes a bounding box");
  const grabX = betaTextBox.x + betaTextBox.width / 2;
  const grabY = betaTextBox.y + betaTextBox.height / 2;
  await page.mouse.move(grabX, grabY);
  await page.mouse.down();
  // Sample live while the pointer travels: the dragged copy tracks the
  // pointer through fixed positioning, and neighbors carry glide animations
  // or translate offsets into the opening gap.
  let dragCopyTop: number | null = null;
  let dragCopyOpaque = false;
  let dragCopySolid = false;
  let dragCopyRaised = false;
  let neighborAnimated = false;
  for (let step = 1; step <= 6; step += 1) {
    await page.mouse.move(grabX, grabY - (pitch * 2.5 * step) / 6, { steps: 3 });
    const sample = await page.evaluate(
      () =>
        [...document.querySelectorAll("[data-scene-layer]")].map((row) => {
          const style = getComputedStyle(row);
          return {
            id: row.getAttribute("data-scene-layer"),
            top: row.getBoundingClientRect().top,
            fixed: style.position === "fixed",
            translate: style.translate,
            animating: row.getAnimations().length,
            opacity: style.opacity,
            background: style.backgroundColor,
            shadow: style.boxShadow,
          };
        }),
      beta,
    );
    const copies = sample.filter((row) => row.id === beta && row.fixed);
    if (copies.length > 0) {
      dragCopyTop = copies[0]!.top;
      // The held row stays fully opaque on a solid raised surface, so the
      // release never flashes brightness: the reference interaction feedback.
      dragCopyOpaque = copies[0]!.opacity === "1";
      dragCopySolid = copies[0]!.background !== "rgba(0, 0, 0, 0)" && copies[0]!.background !== "transparent";
      dragCopyRaised = copies[0]!.shadow !== "none";
    }
    if (sample.some((row) => row.id !== beta && (row.animating > 0 || row.translate !== "none"))) {
      neighborAnimated = true;
    }
  }
  console.log(
    `mid-drag beta: copyTop=${dragCopyTop} neighborAnimated=${neighborAnimated} opaque=${dragCopyOpaque} solid=${dragCopySolid} raised=${dragCopyRaised}`,
  );
  assert.ok(dragCopyTop !== null && dragCopyTop < grabY - pitch, "dragged row follows the pointer upward");
  assert.ok(neighborAnimated, "neighboring rows animate into the gap mid-drag");
  assert.ok(dragCopyOpaque, "dragged row stays fully opaque while held");
  assert.ok(dragCopySolid, "dragged row keeps a solid background while held");
  assert.ok(dragCopyRaised, "dragged row carries a raised shadow while held");
  await page.mouse.up();
  await waitRevision(revision);
  await waitLayerOrder(page, ["Beta", "Alpha", "Gamma"]);
  assert.deepEqual(await layerTexts(), ["Beta", "Alpha", "Gamma"]);
  // The stage paints the same visual order.
  const zetas = await Promise.all([zIndexOf(beta), zIndexOf(alpha), zIndexOf(gamma)]);
  assert.ok(zetas[0]! > zetas[1]! && zetas[1]! > zetas[2]!, `stage z-order follows the layers list, got ${zetas}`);

  // Cancellation settles nothing: Escape during a keyboard drag keeps the
  // order and issues no revision.
  revision = await revisionOf();
  await page.locator(`[data-scene-layer-handle="${alpha}"]`).focus();
  await page.keyboard.press("Space");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Escape");
  await page.waitForTimeout(800);
  assert.deepEqual(await layerTexts(), ["Beta", "Alpha", "Gamma"]);
  assert.equal(await revisionOf(), revision);

  // Inline rename commits through the list editor.
  revision = await revisionOf();
  await page.locator(`[data-scene-layer-handle="${beta}"]`).dblclick();
  await page.locator(`[data-scene-layer-edit="${beta}"]`).fill("Beta2");
  await page.keyboard.press("Control+Enter");
  await waitRevision(revision);
  assert.deepEqual(await layerTexts(), ["Beta2", "Alpha", "Gamma"]);

  // Escape discards the draft without a write.
  await page.locator(`[data-scene-layer-handle="${gamma}"]`).dblclick();
  await page.locator(`[data-scene-layer-edit="${gamma}"]`).fill("Gamma dirty");
  revision = await revisionOf();
  await page.keyboard.press("Escape");
  await page.waitForFunction(
    (placementId) => document.querySelector(`[data-scene-layer-edit="${placementId}"]`) === null,
    gamma,
    { timeout: 20000 },
  );
  assert.deepEqual(await layerTexts(), ["Beta2", "Alpha", "Gamma"]);
  assert.equal(await revisionOf(), revision);

  // Order and names survive a reload. The workspace marker renders in the
  // loading state too, so wait for the rows themselves.
  await page.reload({ waitUntil: "domcontentloaded" });
  await waitWorkspace(page);
  await page.waitForFunction(() => document.querySelectorAll("[data-scene-layer-text]").length === 3, null, {
    timeout: 20000,
  });
  assert.deepEqual(await layerTexts(), ["Beta2", "Alpha", "Gamma"]);
  assert.deepEqual(errors, []);
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

test(
  "legacy and selection links open the default and normalize without selection",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    t.after(() => context.close());
    await captureDomainWorker(context);
    const page = await context.newPage();
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    t.after(() => page.close());
    await bootLibrary(page, url);
    await ensureStyle(page, url);
    await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
    await openScreen(page);
    await createComposition(page, "Legacy default");
    await addLabel(page, "Legacy label");
    const adopted = await defaultId(page);

    // A stored non-default row stays hidden: direct and legacy links open the
    // adopted default, never the row they name.
    const other = await seedSecondScene(page, await workerUrl(page), "Hidden scene");
    assert.notEqual(other, adopted);

    await page.goto(`${url}scenes/`, { waitUntil: "domcontentloaded" });
    await waitWorkspace(page);
    assert.equal(await defaultId(page), adopted);
    assert.equal(await hashPath(page), "/screen/");
    assert.equal(await hashParam(page, "scene"), null);
    await waitLayerText(page, "Legacy label");

    await page.goto(`${url}screen/?scene=${other}`, { waitUntil: "domcontentloaded" });
    await waitWorkspace(page);
    assert.equal(await defaultId(page), adopted);
    assert.equal(await hashPath(page), "/screen/");
    assert.equal(await hashParam(page, "scene"), null);

    await page.goto(`${url}scene/${other}/`, { waitUntil: "domcontentloaded" });
    await waitWorkspace(page);
    assert.equal(await defaultId(page), adopted);
    assert.equal(await hashPath(page), "/screen/");
    assert.equal(await hashParam(page, "scene"), null);

    // Unknown selections report the default instead of spinning or 404ing.
    await page.goto(`${url}screen/?scene=missing-scene`, { waitUntil: "domcontentloaded" });
    await waitWorkspace(page);
    assert.equal(await defaultId(page), adopted);
    assert.equal(await hashParam(page, "scene"), null);
    await waitLayerText(page, "Legacy label");

    const pageTitle = await page.title();
    assert.ok(pageTitle.includes("Screen"), `legacy detail keeps the Screen title, got ${pageTitle}`);
    assert.deepEqual(errors, []);
  },
);

test(
  "the default composition persists across reload and stays single across tabs",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    t.after(() => context.close());
    const page = await context.newPage();
    t.after(() => page.close());
    await bootLibrary(page, url);
    await ensureStyle(page, url);
    await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
    await openScreen(page);
    await createComposition(page, "Persistent default");
    await addLabel(page, "Persistent label");
    const adopted = await defaultId(page);

    // Reload keeps the same default id with its content.
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitWorkspace(page);
    assert.equal(await defaultId(page), adopted);
    await waitLayerText(page, "Persistent label");

    // A second tab converges on the same default instead of creating another.
    const peer = await context.newPage();
    t.after(() => peer.close());
    await peer.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
    await waitWorkspace(peer);
    assert.equal(await defaultId(peer), adopted);
    await waitLayerText(peer, "Persistent label");
  },
);

test(
  "layers panel splitter resizes by pointer and keyboard and keeps nested button Enter",
  { skip: !browserAvailable, timeout: 180_000 },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    page.setDefaultTimeout(15000);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    t.after(() => page.close());
    await bootLibrary(page, url);
    await ensureStyle(page, url);
    await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
    await openScreen(page);
    await createComposition(page, "Splitter scene");
    await addLabel(page, "One");
    await waitLayerText(page, "One");
    await addLabel(page, "Two");
    await waitLayerText(page, "Two");
    assert.deepEqual(await layerOrder(page), ["Two", "One"]);

    const panelWidth = (): Promise<number> =>
      page.locator("[data-scene-layers]").evaluate((card) => card.getBoundingClientRect().width);
    const separator = page.getByRole("separator", { name: "Resize layers panel" });

    // Keyboard resizing moves the splitter without a pointer.
    const base = await panelWidth();
    await separator.focus();
    assert.equal(await page.evaluate(() => document.activeElement?.getAttribute("aria-label")), "Resize layers panel");
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("ArrowRight");
    await page.waitForFunction(
      (before) => (document.querySelector("[data-scene-layers]")?.getBoundingClientRect().width ?? 0) !== before,
      base,
      { timeout: 15000 },
    );
    const afterKeys = await panelWidth();
    await page.keyboard.press("ArrowLeft");
    await page.keyboard.press("ArrowLeft");
    await page.keyboard.press("ArrowLeft");
    await page.waitForFunction(
      (width) => (document.querySelector("[data-scene-layers]")?.getBoundingClientRect().width ?? 0) !== width,
      afterKeys,
      { timeout: 15000 },
    );
    const afterKeysBack = await panelWidth();

    // Pointer drag clamps to the panel pixel constraints.
    const box = await separator.boundingBox();
    assert.ok(box, "splitter handle exposes a bounding box");
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 200, box.y + box.height / 2, { steps: 10 });
    await page.mouse.up();
    await page.waitForFunction(
      (width) => (document.querySelector("[data-scene-layers]")?.getBoundingClientRect().width ?? 0) !== width,
      afterKeysBack,
      { timeout: 15000 },
    );
    const afterDrag = await panelWidth();
    console.log(`layers panel widths: base=${base} keys=${afterKeys} keysBack=${afterKeysBack} drag=${afterDrag}`);
    assert.ok(afterDrag >= 199.5 && afterDrag <= 420.5, `dragged panel stays within min/max, got ${afterDrag}`);

    // Narrow viewport: report the real measured widths instead of assuming fit.
    // Runs before the nested-Enter probe so that finding cannot mask these
    // observations; the viewport is restored afterwards.
    await page.setViewportSize({ width: 375, height: 800 });
    await page.waitForTimeout(400);
    const narrow = await page.evaluate(() => {
      const card = document.querySelector("[data-scene-layers]");
      const group = document.querySelector("[data-screen-layers-group]");
      return {
        cardWidth: card?.getBoundingClientRect().width ?? -1,
        groupClient: group?.clientWidth ?? -1,
        groupScroll: group?.scrollWidth ?? -1,
        pageOverflow: document.documentElement.scrollWidth - window.innerWidth,
        rows: document.querySelectorAll("[data-scene-layer]").length,
      };
    });
    console.log(`375px viewport: ${JSON.stringify(narrow)}`);
    assert.equal(narrow.rows, 2, "both layer rows still render at 375px");
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.waitForTimeout(400);

    // Nested Enter: double-click opens editing, so Enter on the
    // focused row body must not open the text editor. The row owns Enter as a
    // keyboard-drag starter; Escape cancels the drag.
    const backId = await layerIdByText(page, "One");
    const revBeforeEnter = await workspaceRevision(page);
    await page.locator(`[data-scene-layer-handle="${backId}"]`).focus();
    await page.keyboard.press("Enter");
    await page.keyboard.press("Escape");
    await page.waitForTimeout(500);
    const editorOpened = await page.locator(`[data-scene-layer-edit="${backId}"]`).count();
    const orderAfterEnter = await layerOrder(page);
    const revAfterEnter = await workspaceRevision(page);
    console.log(
      `nested Enter: editor=${editorOpened} rev=${revBeforeEnter}->${revAfterEnter} order=${JSON.stringify(orderAfterEnter)}`,
    );
    assert.equal(editorOpened, 0, `Enter on the focused row body must not open the text editor (row for ${backId})`);
    assert.deepEqual(orderAfterEnter, ["Two", "One"], "Enter+Escape on the row leaves the order alone");
    assert.equal(revAfterEnter, revBeforeEnter, "cancelled row drag issues no revision");
    assert.deepEqual(errors, []);
  },
);

test(
  "list blur commits once, handles blank and multiline, and undo restores reorder and rename",
  { skip: !browserAvailable, timeout: 180_000 },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    // Explicit context (not browser.newPage) so the peer-conflict step can
    // open a second tab sharing storage and the single domain owner.
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    t.after(() => page.close());
    await bootLibrary(page, url);
    await ensureStyle(page, url);
    await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
    await openScreen(page);
    await createComposition(page, "Layers edit scene");
    await addLabel(page, "Alpha");
    await waitLayerText(page, "Alpha");
    await addLabel(page, "Beta");
    await waitLayerText(page, "Beta");
    await addLabel(page, "Gamma");
    await waitLayerText(page, "Gamma");
    const alpha = await layerIdByText(page, "Alpha");
    const beta = await layerIdByText(page, "Beta");
    const gamma = await layerIdByText(page, "Gamma");
    assert.deepEqual(await layerOrder(page), ["Gamma", "Beta", "Alpha"]);

    // Blur settles the draft exactly once: one revision bump, then silence.
    let rev = await workspaceRevision(page);
    await page.locator(`[data-scene-layer-handle="${beta}"]`).dblclick();
    await page.locator(`[data-scene-layer-edit="${beta}"]`).fill("Beta blur");
    await blurListDraft(page);
    await waitWorkspaceRevision(page, rev);
    rev = await workspaceRevision(page);
    await page.waitForTimeout(800);
    assert.equal(await workspaceRevision(page), rev, "blur commits the draft exactly once");
    assert.deepEqual(await layerOrder(page), ["Gamma", "Beta blur", "Alpha"]);

    // Plain Enter extends the draft instead of committing it.
    await page.locator(`[data-scene-layer-handle="${gamma}"]`).dblclick();
    const gammaEdit = page.locator(`[data-scene-layer-edit="${gamma}"]`);
    await gammaEdit.fill("Gx");
    await page.keyboard.press("End");
    await page.keyboard.press("Enter");
    assert.equal(await gammaEdit.inputValue(), "Gx\n", "plain Enter inserts a newline without committing");
    assert.equal(await workspaceRevision(page), rev, "plain Enter issues no revision");
    await page.keyboard.type("Gy");
    await blurListDraft(page);
    await waitWorkspaceRevision(page, rev);
    rev = await workspaceRevision(page);
    assert.deepEqual(await layerOrder(page), ["Gx\nGy", "Beta blur", "Alpha"]);

    // Blank text is allowed and renders the placeholder row.
    await page.locator(`[data-scene-layer-handle="${alpha}"]`).dblclick();
    await page.locator(`[data-scene-layer-edit="${alpha}"]`).fill("");
    await blurListDraft(page);
    await waitWorkspaceRevision(page, rev);
    rev = await workspaceRevision(page);
    assert.equal(await page.locator(`[data-scene-layer-text="${alpha}"]`).textContent(), "(blank label)");

    // Undo restores a keyboard drag reorder, and redo reapplies it. Each
    // arrow press steps the keyboard drag exactly one row (clamped at the
    // ends), so one press moves the front label back a single row.
    const gx = await layerIdByText(page, "Gx\nGy");
    const orderBeforeStep = await layerOrder(page);
    await page.locator(`[data-scene-layer-handle="${gx}"]`).focus();
    await page.keyboard.press("Space");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Space");
    await waitWorkspaceRevision(page, rev);
    rev = await workspaceRevision(page);
    await waitLayerOrder(page, ["Beta blur", "Gx\nGy", "(blank label)"]);
    const stepped = await layerOrder(page);
    assert.deepEqual(stepped, ["Beta blur", "Gx\nGy", "(blank label)"], "keyboard drag moves the front label back");
    await waitEnabled(page, "[data-screen-undo]");
    await page.locator("[data-screen-undo]").click();
    await waitWorkspaceRevision(page, rev);
    rev = await workspaceRevision(page);
    assert.deepEqual(await layerOrder(page), orderBeforeStep, "undo restores the pre-step order");
    await waitEnabled(page, "[data-screen-redo]");
    await page.locator("[data-screen-redo]").click();
    await waitWorkspaceRevision(page, rev);
    rev = await workspaceRevision(page);
    assert.deepEqual(await layerOrder(page), stepped, "redo reapplies the step");

    // Undo restores a list rename.
    await page.locator(`[data-scene-layer-handle="${beta}"]`).dblclick();
    await page.locator(`[data-scene-layer-edit="${beta}"]`).fill("Beta renamed");
    await blurListDraft(page);
    await waitWorkspaceRevision(page, rev);
    rev = await workspaceRevision(page);
    assert.deepEqual(await layerOrder(page), ["Beta renamed", "Gx\nGy", "(blank label)"]);
    await waitEnabled(page, "[data-screen-undo]");
    await page.locator("[data-screen-undo]").click();
    await waitWorkspaceRevision(page, rev);
    assert.deepEqual(
      await layerOrder(page),
      ["Beta blur", "Gx\nGy", "(blank label)"],
      "undo restores the pre-rename text",
    );

    // A peer tab coverage save keeps the open list draft behind the conflict banner.
    const pageB = await context.newPage();
    pageB.setDefaultTimeout(15000);
    t.after(() => pageB.close());
    await pageB.goto(await page.url(), { waitUntil: "domcontentloaded" });
    await waitWorkspace(pageB);
    await page.locator(`[data-scene-layer-handle="${beta}"]`).dblclick();
    await page.locator(`[data-scene-layer-edit="${beta}"]`).type(" dirty");
    await pageB.getByRole("switch", { name: /Greek/i }).click();
    const revisionBeforeB = await pageB.locator("[data-screen-workspace]").getAttribute("data-screen-revision");
    await pageB.locator("[data-screen-save-coverage]").click();
    await pageB.waitForFunction(
      (revision) =>
        document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision") !== revision,
      revisionBeforeB,
      { timeout: 20000 },
    );
    await page.locator("[data-screen-conflict]").waitFor();
    assert.equal(
      await page.locator(`[data-scene-layer-edit="${beta}"]`).inputValue(),
      "Beta blur dirty",
      "list draft survives the peer coverage save behind the banner",
    );
    const revBeforeReload = await workspaceRevision(page);
    await page.locator("[data-screen-reload]").click();
    await waitWorkspaceRevision(page, revBeforeReload);
    assert.equal(await page.locator(`[data-scene-layer-edit="${beta}"]`).count(), 0, "reload discards the list draft");
    assert.deepEqual(errors, []);
  },
);

test(
  "cancelled drags clear feedback and the next drag still reorders",
  { skip: !browserAvailable, timeout: 180_000 },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    page.setDefaultTimeout(15000);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    t.after(() => page.close());
    await bootLibrary(page, url);
    await ensureStyle(page, url);
    await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
    await openScreen(page);
    await createComposition(page, "Cancel scene");
    await addLabel(page, "Alpha");
    await waitLayerText(page, "Alpha");
    await addLabel(page, "Beta");
    await waitLayerText(page, "Beta");
    assert.deepEqual(await layerOrder(page), ["Beta", "Alpha"]);
    const alpha = await layerIdByText(page, "Alpha");

    // Release outside any row: the pointer sensor reports the drop as
    // uncancelled once the drag initialized, so the app may commit the last
    // projected slot instead of cancelling. Either outcome must keep every
    // label and clear the drag copy. The row activator never disables, so the
    // queue drain is observed through the revision: a commit bumps it, a
    // cancellation leaves it alone.
    const revBeforeOutside = await workspaceRevision(page);
    const handleBox = await page.locator(`[data-scene-layer-handle="${alpha}"]`).boundingBox();
    assert.ok(handleBox, "row activator exposes a bounding box");
    await page.locator(`[data-scene-layer-handle="${alpha}"]`).scrollIntoViewIfNeeded();
    await page.mouse.move(handleBox.x + handleBox.width / 2, handleBox.y + handleBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(40, 40, { steps: 5 });
    await page.mouse.up();
    try {
      await page.waitForFunction(
        (rev) => document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision") !== rev,
        revBeforeOutside,
        { timeout: 10000 },
      );
    } catch {
      // No save landed: the drop was a no-op.
    }
    // Animations quiesce after the drop animation (or its absence) finishes.
    await page.waitForFunction(
      () => [...document.querySelectorAll("[data-scene-layer]")].every((row) => row.getAnimations().length === 0),
      null,
      { timeout: 15000 },
    );
    const releasedOrder = await layerOrder(page);
    console.log(`outside release: order=${JSON.stringify(releasedOrder)} rev=${await workspaceRevision(page)}`);
    assert.deepEqual([...releasedOrder].sort(), ["Alpha", "Beta"], "outside release keeps every label");
    const feedback = await page.evaluate(() =>
      [...document.querySelectorAll("[data-scene-layer]")].map((row) => {
        const style = getComputedStyle(row);
        return { fixed: style.position === "fixed", translate: style.translate };
      }),
    );
    assert.ok(
      feedback.every((row) => !row.fixed),
      `outside release leaves no drag copy, got ${JSON.stringify(feedback)}`,
    );

    // The next drag still works after the outside release settles: the last
    // row drags to the front through the keyboard path.
    const settledRevision = await workspaceRevision(page);
    const backText = releasedOrder[releasedOrder.length - 1]!;
    const back = await layerIdByText(page, backText);
    await page.locator(`[data-scene-layer-handle="${back}"]`).focus();
    await page.keyboard.press("Space");
    await page.keyboard.press("ArrowUp");
    await page.keyboard.press("Space");
    await waitWorkspaceRevision(page, settledRevision);
    await waitLayerOrder(page, [backText, releasedOrder[0]!]);
    assert.deepEqual(await layerOrder(page), [backText, releasedOrder[0]!]);
    assert.deepEqual(errors, []);
  },
);

test(
  "peer add during a keyboard drag never moves a different label",
  { skip: !browserAvailable, timeout: 180_000 },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    // Same shared context as the other two-tab tests: one origin, one owner.
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    t.after(() => context.close());
    const pageA = await context.newPage();
    pageA.setDefaultTimeout(15000);
    const errors: string[] = [];
    pageA.on("pageerror", (error) => errors.push(error.message));
    t.after(() => pageA.close());
    await bootLibrary(pageA, url);
    await ensureStyle(pageA, url);
    await pageA.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
    await openScreen(pageA);
    await createComposition(pageA, "Drag race scene");
    await addLabel(pageA, "Alpha");
    await waitLayerText(pageA, "Alpha");
    await addLabel(pageA, "Beta");
    await waitLayerText(pageA, "Beta");
    await addLabel(pageA, "Gamma");
    await waitLayerText(pageA, "Gamma");
    const alpha = await layerIdByText(pageA, "Alpha");
    assert.deepEqual(await layerOrder(pageA), ["Gamma", "Beta", "Alpha"]);

    // Lift Alpha and project it one row up, then hold the drag open.
    await pageA.locator(`[data-scene-layer-handle="${alpha}"]`).focus();
    await pageA.keyboard.press("Space");
    await pageA.keyboard.press("ArrowUp");

    // A peer adds Delta mid-drag; the adoption lands behind the held drag.
    const pageB = await context.newPage();
    pageB.setDefaultTimeout(15000);
    t.after(() => pageB.close());
    await pageB.goto(await pageA.url(), { waitUntil: "domcontentloaded" });
    await waitWorkspace(pageB);
    await addLabel(pageB, "Delta");
    await pageA.waitForFunction(
      () => [...document.querySelectorAll("[data-scene-layer-text]")].some((entry) => entry.textContent === "Delta"),
      null,
      { timeout: 15000 },
    );
    // The held drag survives the adoption: the live slots keep the keyboard
    // projection instead of snapping back, and no label is lost.
    const liveOrder = await layerOrderLive(pageA);
    console.log(`mid-drag live slots: ${JSON.stringify(liveOrder)}`);
    assert.deepEqual([...liveOrder].sort(), ["Alpha", "Beta", "Delta", "Gamma"]);
    // The peer tab shows the true saved base with no drag held open.
    const peerSaved = await layerOrder(pageB);
    assert.deepEqual(peerSaved, ["Delta", "Gamma", "Beta", "Alpha"]);
    const peerRevision = await workspaceRevision(pageA);

    // Drop, then Escape in case the held drag was already cancelled behind the
    // adoption and the Space opened a fresh drag instead of dropping.
    await pageA.keyboard.press("Space");
    await pageA.keyboard.press("Escape");
    // The save roundtrips through the domain owner; wait for it to land
    // instead of racing it. A truly cancelled drop never bumps the revision.
    let committed = false;
    try {
      await pageA.waitForFunction(
        (rev) => document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision") !== rev,
        peerRevision,
        { timeout: 10000 },
      );
      committed = true;
    } catch {
      // No save landed within the bound: the drop was a no-op.
      committed = false;
    }
    // The row activator never disables, so the revision wait above is the
    // queue-drain gate; here the animations only need to quiesce.
    await pageA.waitForFunction(
      () => [...document.querySelectorAll("[data-scene-layer]")].every((row) => row.getAnimations().length === 0),
      null,
      { timeout: 15000 },
    );
    const finalOrder = await layerOrder(pageA);
    console.log(
      `mid-drag peer add: committed=${committed} saved=${JSON.stringify(peerSaved)} final=${JSON.stringify(finalOrder)}`,
    );
    assert.deepEqual([...finalOrder].sort(), ["Alpha", "Beta", "Delta", "Gamma"], "mid-drag peer add loses no label");
    if (committed) {
      const moved = finalOrder.filter((text, index) => peerSaved[index] !== text);
      assert.ok(moved.includes("Alpha"), `only the grabbed label may move, moved=${JSON.stringify(moved)}`);
    } else {
      assert.deepEqual(finalOrder, peerSaved, "a cancelled drop keeps the adopted order");
    }
    assert.deepEqual(errors, []);
  },
);

interface SettleFrame {
  box: { x: number; y: number; w: number; h: number };
  visible: boolean;
  canvases: number;
  fixed: number;
  opacities: string[];
  scrollX: number;
  scrollY: number;
  listTop: number;
}

test(
  "pointer reorder release settles the stage without flicker",
  { skip: !browserAvailable, timeout: 180_000 },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    page.setDefaultTimeout(15000);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    t.after(() => page.close());
    await bootLibrary(page, url);
    await ensureStyle(page, url);
    await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
    await openScreen(page);
    await createComposition(page, "Settle scene");
    // Local add: the shared helper's internal waits exceed this test's bound.
    const addSettleLabel = async (text: string): Promise<void> => {
      await addScreenText(page, text, { variant: true });
      await page.waitForFunction(
        (label) =>
          [...document.querySelectorAll("[data-scene-layer-text]")].some((entry) => entry.textContent === label),
        text,
        { timeout: 15000 },
      );
    };
    await addSettleLabel("Alpha");
    await addSettleLabel("Beta");
    assert.deepEqual(await layerOrder(page), ["Beta", "Alpha"]);
    const alpha = await layerIdByText(page, "Alpha");
    const beta = await layerIdByText(page, "Beta");
    for (const id of [alpha, beta]) {
      await page.waitForFunction(
        (placementId) => {
          const viewport = document.querySelector(`[data-scene-label="${placementId}"]`);
          const canvas = viewport?.querySelector("canvas");
          return canvas instanceof HTMLCanvasElement && canvas.dataset.rendered === "true";
        },
        id,
        { timeout: 15000 },
      );
    }

    // The textarea never starts a drag and stays enabled: the row
    // body owns the handle while the editor is mounted, so no ancestor may
    // stamp aria-disabled over the live editor.
    await page.locator(`[data-scene-layer-handle="${beta}"]`).dblclick();
    await page.locator(`[data-scene-layer-edit="${beta}"]`).waitFor();
    const editorState = await page.evaluate((placementId) => {
      const editor = document.querySelector(`[data-scene-layer-edit="${placementId}"]`);
      const row = document.querySelector(`[data-scene-layer="${placementId}"]`);
      return {
        enabled: editor instanceof HTMLTextAreaElement && !editor.disabled,
        blocked: editor?.closest('[aria-disabled="true"]') !== null,
        rowGate: row?.getAttribute("aria-disabled"),
      };
    }, beta);
    assert.equal(editorState.enabled, true, "list editor stays enabled");
    assert.equal(editorState.blocked, false, "no ancestor disables the list editor");
    assert.equal(editorState.rowGate, null, "row carries no aria-disabled gate");
    // A drag started inside the textarea lifts nothing and writes nothing.
    const revBeforeEditDrag = await workspaceRevision(page);
    const editBox = await page.locator(`[data-scene-layer-edit="${beta}"]`).boundingBox();
    assert.ok(editBox, "list editor exposes a bounding box");
    await page.mouse.move(editBox.x + editBox.width / 2, editBox.y + editBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(editBox.x + editBox.width / 2, editBox.y - 60, { steps: 5 });
    const editLifted = await page.evaluate(
      () =>
        [...document.querySelectorAll("[data-scene-layer]")].filter((row) => getComputedStyle(row).position === "fixed")
          .length,
    );
    await page.mouse.up();
    assert.equal(editLifted, 0, "textarea drag lifts no row");
    await page.keyboard.press("Escape");
    await page.waitForFunction(
      (placementId) => document.querySelector(`[data-scene-layer-edit="${placementId}"]`) === null,
      beta,
      { timeout: 15000 },
    );
    assert.equal(await workspaceRevision(page), revBeforeEditDrag, "textarea drag writes no revision");

    // Per-label paint fingerprints plus live element refs: a reorder only
    // changes paint order, so every label canvas bitmap must survive the drop
    // on its original element. Composited stage pixels legitimately change
    // when the top label swaps, so they are not compared.
    const before = await page.evaluate(() => {
      const stage = document.querySelector("[data-scene-stage]");
      const holder = window as unknown as { __settleStage?: Element | null; __settleCanvases?: HTMLCanvasElement[] };
      holder.__settleStage = stage;
      holder.__settleCanvases = [...document.querySelectorAll("[data-scene-label-container] canvas")].filter(
        (node): node is HTMLCanvasElement => node instanceof HTMLCanvasElement,
      );
      const canvases = [...document.querySelectorAll("[data-scene-label-container]")].map((container) => {
        const canvas = container.querySelector("canvas");
        if (!(canvas instanceof HTMLCanvasElement)) throw new Error("label canvas is missing");
        return { id: container.getAttribute("data-scene-label-container"), paint: canvas.toDataURL() };
      });
      const box = stage?.getBoundingClientRect();
      return { canvases, stageBox: { x: box?.x ?? -1, y: box?.y ?? -1, w: box?.width ?? -1, h: box?.height ?? -1 } };
    });

    // Hold the back row first, then sample across the release: the frame
    // window spans the held drop, the settle animation and the saved revision.
    const pitch = await page.evaluate(() => {
      const tops = [...document.querySelectorAll("[data-scene-layer]")]
        .map((row) => row.getBoundingClientRect().top)
        .sort((a, b) => a - b);
      return tops.length > 1 ? tops[1]! - tops[0]! : 40;
    });
    await page.locator(`[data-scene-layer="${alpha}"]`).scrollIntoViewIfNeeded();
    const grabBox = await page.locator(`[data-scene-layer-text="${alpha}"]`).boundingBox();
    assert.ok(grabBox, "row text exposes a bounding box");
    const grabX = grabBox.x + grabBox.width / 2;
    const grabY = grabBox.y + grabBox.height / 2;
    const revision = await workspaceRevision(page);
    await page.mouse.move(grabX, grabY);
    await page.mouse.down();
    await page.mouse.move(grabX, grabY - pitch * 0.75, { steps: 3 });
    const held = await page.evaluate(
      () =>
        [...document.querySelectorAll("[data-scene-layer]")].filter((row) => getComputedStyle(row).position === "fixed")
          .length,
    );
    assert.ok(held >= 1, "back row lifts before the sampled release");
    const sampling = page.evaluate(
      (): Promise<SettleFrame[]> =>
        new Promise((resolve) => {
          const frames: SettleFrame[] = [];
          const tick = (): void => {
            const stage = document.querySelector("[data-scene-stage]");
            const box = stage?.getBoundingClientRect();
            frames.push({
              box: { x: box?.x ?? -1, y: box?.y ?? -1, w: box?.width ?? -1, h: box?.height ?? -1 },
              visible: stage instanceof HTMLElement && stage.offsetParent !== null,
              canvases: document.querySelectorAll("[data-scene-label-container] canvas").length,
              fixed: [...document.querySelectorAll("[data-scene-layer]")].filter(
                (row) => getComputedStyle(row).position === "fixed",
              ).length,
              opacities: [...document.querySelectorAll("[data-scene-layer]")].map(
                (row) => getComputedStyle(row).opacity,
              ),
              scrollX: window.scrollX,
              scrollY: window.scrollY,
              listTop: document.querySelector("[data-scene-layer-list]")?.scrollTop ?? -1,
            });
            if (frames.length < 150) requestAnimationFrame(tick);
            else resolve(frames);
          };
          requestAnimationFrame(tick);
        }),
    );
    await page.mouse.move(grabX, grabY - pitch * 1.5, { steps: 4 });
    await page.mouse.up();
    const frames = await sampling;
    await waitWorkspaceRevision(page, revision);
    await page.waitForFunction(
      () => [...document.querySelectorAll("[data-scene-layer]")].every((row) => row.getAnimations().length === 0),
      null,
      { timeout: 15000 },
    );

    const spread = (values: number[]): number => Math.max(...values) - Math.min(...values);
    console.log(
      `settle frames=${frames.length} fixedMax=${Math.max(...frames.map((frame) => frame.fixed))} ` +
        `stageSpread=${spread(frames.map((frame) => frame.box.w)).toFixed(2)}x${spread(frames.map((frame) => frame.box.h)).toFixed(2)} ` +
        `opacities=${JSON.stringify([...new Set(frames.flatMap((frame) => frame.opacities))])}`,
    );
    assert.equal(frames.length, 150, "sampler spans the drop settle");
    assert.ok(
      frames.every((frame) => frame.visible),
      "stage stays visible across the release",
    );
    assert.ok(
      frames.every((frame) => frame.canvases === before.canvases.length),
      `label canvases survive the release, got ${JSON.stringify(frames.map((frame) => frame.canvases))}`,
    );
    assert.ok(
      spread(frames.map((frame) => frame.box.w)) <= 1 &&
        spread(frames.map((frame) => frame.box.h)) <= 1 &&
        spread(frames.map((frame) => frame.box.x)) <= 1 &&
        spread(frames.map((frame) => frame.box.y)) <= 1,
      "stage geometry holds still across the release",
    );
    assert.ok(
      frames.every((frame) => frame.opacities.every((opacity) => opacity === "1")),
      `no row flashes translucent across the release, got ${JSON.stringify([...new Set(frames.flatMap((frame) => frame.opacities))])}`,
    );
    assert.ok(
      frames.every((frame) => frame.fixed <= 1),
      "at most one drag copy exists mid-flight",
    );
    assert.equal(frames[frames.length - 1]!.fixed, 0, "drag copy clears after the release");
    assert.ok(
      frames.every(
        (frame) =>
          frame.scrollX === frames[0]!.scrollX &&
          frame.scrollY === frames[0]!.scrollY &&
          frame.listTop === frames[0]!.listTop,
      ),
      "no scroll jump across the release",
    );

    await page.waitForFunction(
      (want) =>
        [...document.querySelectorAll("[data-scene-layer-text]")].map((entry) => entry.textContent).join("\0") ===
        want.join("\0"),
      ["Alpha", "Beta"],
      { timeout: 15000 },
    );
    assert.deepEqual(await layerOrder(page), ["Alpha", "Beta"]);
    const after = await page.evaluate(() => {
      const holder = window as unknown as { __settleStage?: Element | null; __settleCanvases?: HTMLCanvasElement[] };
      const canvases = [...document.querySelectorAll("[data-scene-label-container]")].map((container) => {
        const canvas = container.querySelector("canvas");
        if (!(canvas instanceof HTMLCanvasElement)) throw new Error("label canvas is missing");
        return { id: container.getAttribute("data-scene-label-container"), paint: canvas.toDataURL() };
      });
      const stage = document.querySelector("[data-scene-stage]");
      const box = stage?.getBoundingClientRect();
      return {
        canvases,
        sameStage: stage === holder.__settleStage,
        stageCount: document.querySelectorAll("[data-scene-stage]").length,
        canvasesLive: (holder.__settleCanvases ?? []).every((canvas) => canvas.isConnected),
        stageBox: { x: box?.x ?? -1, y: box?.y ?? -1, w: box?.width ?? -1, h: box?.height ?? -1 },
      };
    });
    const byId = (rows: Array<{ id: string | null; paint: string }>): Array<{ id: string | null; paint: string }> =>
      [...rows].sort((a, b) => (a.id ?? "").localeCompare(b.id ?? ""));
    assert.equal(after.stageCount, 1, "release mounts no extra stage");
    assert.equal(after.sameStage, true, "stage element survives the release");
    assert.equal(after.canvasesLive, true, "label canvases keep their DOM identity");
    assert.deepEqual(byId(after.canvases), byId(before.canvases), "label paint is pixel-identical across the reorder");
    for (const key of ["x", "y", "w", "h"] as const) {
      assert.ok(Math.abs(after.stageBox[key] - before.stageBox[key]) <= 1, `stage ${key} holds still after the save`);
    }

    // The next drag still reorders after the sampled release settles.
    const settled = await workspaceRevision(page);
    await page.locator(`[data-scene-layer-handle="${beta}"]`).focus();
    await page.keyboard.press("Space");
    await page.keyboard.press("ArrowUp");
    await page.keyboard.press("Space");
    await waitWorkspaceRevision(page, settled);
    await page.waitForFunction(
      (want) =>
        [...document.querySelectorAll("[data-scene-layer-text]")].map((entry) => entry.textContent).join("\0") ===
        want.join("\0"),
      ["Beta", "Alpha"],
      { timeout: 15000 },
    );
    assert.deepEqual(await layerOrder(page), ["Beta", "Alpha"]);
    assert.deepEqual(errors, []);
  },
);

interface RejectFrame {
  relLayers: number;
  relStage: number;
  statusH: number;
  winX: number;
  winY: number;
  listTop: number;
  stageLeft: number;
}

/**
 * Gate the domain SharedWorker transport so reorder calls fail exactly like
 * a pre-reorder owner (unavailable unknown-method), while every other
 * command passes through to the real owner. Installed after
 * captureDomainWorker so URL capture keeps working; the flag toggles live.
 */
async function gateReorderRejection(page: Parameters<typeof cardNames>[0]): Promise<void> {
  await page.evaluate(() => {
    (window as unknown as { __glypherieRejectReorder?: boolean }).__glypherieRejectReorder = true;
  });
}

async function ungateReorderRejection(page: Parameters<typeof cardNames>[0]): Promise<void> {
  await page.evaluate(() => {
    (window as unknown as { __glypherieRejectReorder?: boolean }).__glypherieRejectReorder = false;
  });
}

test("repeat failed saves keep workspace geometry stable", { skip: !browserAvailable, timeout: 180_000 }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  page.setDefaultTimeout(15000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await installMethodFailureSeam(page.context());
  await bootLibrary(page, url);
  await ensureStyle(page, url);
  await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
  await openScreen(page);
  await createComposition(page, "Stable error scene");
  await addLabel(page, "Alpha");
  await waitLayerText(page, "Alpha");

  // The inline status region reserves its line even with no failure, so a
  // later alert inserts text without moving the layers or the stage.
  assert.equal(await page.locator("[data-screen-workspace-status]").count(), 1, "status region stays mounted");
  const reserved = await page.locator("[data-screen-workspace-status]").boundingBox();
  assert.ok(reserved && reserved.height >= 15, `status region reserves a line, got ${JSON.stringify(reserved)}`);

  // Viewport tops move when any scroller moves, so the flicker signal is
  // the workspace-relative offset (immune to scrolling) plus the scroll
  // positions themselves (a repeated failure must scroll nothing).
  const frame = (): Promise<Record<string, number | boolean>> =>
    page.evaluate(() => {
      const el = (query: string): Element | null => document.querySelector(query);
      const top = (query: string): number => el(query)?.getBoundingClientRect().top ?? -9999;
      const scrollers: number[] = [];
      let node: Element | null = el("[data-screen-workspace]");
      while (node) {
        if (node.scrollTop !== undefined && node.scrollTop !== 0) scrollers.push(node.scrollTop);
        node = node.parentElement;
      }
      scrollers.push(window.scrollY);
      return {
        relLayers: top("[data-screen-layers-group]") - top("[data-screen-workspace]"),
        relStage: top("[data-screen-stage-scroll]") - top("[data-screen-workspace]"),
        statusH: el("[data-screen-workspace-status]")?.getBoundingClientRect().height ?? -1,
        scrolled: scrollers.some((value) => value !== 0),
        scrollSum: scrollers.reduce((a, b) => a + b, 0),
      };
    });
  const calm = await frame();

  // A failing save surfaces the alert; repeating the same failure must not
  // remove and reinsert it (no banner toggle, no jump, no scroll).
  await armMethodFailure(page, "addSceneLabel");
  await page.locator('[data-screen-tool="text"]').click();
  await page.locator("[data-scene-text-placement]").click({ position: { x: 4, y: 4 } });
  await page.locator("[data-screen-workspace-error]").waitFor();
  const first = await frame();
  await page.locator("[data-scene-text-placement]").click({ position: { x: 4, y: 4 } });
  await page.waitForTimeout(400);
  const second = await frame();
  console.log(
    `stable-error frames: calm=${JSON.stringify(calm)} first=${JSON.stringify(first)} second=${JSON.stringify(second)}`,
  );
  for (const key of ["relLayers", "relStage", "statusH"] as const) {
    assert.ok(Math.abs(Number(first[key]) - Number(calm[key])) <= 1, `${key} holds still when the alert appears`);
    assert.ok(
      Math.abs(Number(second[key]) - Number(first[key])) <= 1,
      `${key} holds still across the repeated failure`,
    );
  }
  assert.equal(second.scrolled, calm.scrolled, "the repeated failure scrolls nothing new");
  assert.ok(
    Math.abs(Number(second.scrollSum) - Number(calm.scrollSum)) <= 1,
    "no scroll jump across the repeated failure",
  );

  // A later success clears the alert without shifting the workspace either.
  await clearMethodFailure(page);
  await addScreenText(page, "Beta", { variant: true });
  await waitLayerText(page, "Beta");
  await page.waitForFunction(() => document.querySelector("[data-screen-workspace-error]") === null, null, {
    timeout: 15000,
  });
  const cleared = await frame();
  console.log(`stable-error cleared: first=${JSON.stringify(first)} cleared=${JSON.stringify(cleared)}`);
  for (const key of ["relLayers", "relStage", "statusH"] as const) {
    assert.ok(Math.abs(Number(cleared[key]) - Number(first[key])) <= 1, `${key} holds still when the alert clears`);
  }
  assert.deepEqual(errors, []);
});

test(
  "repeat rejected pointer drops keep workspace geometry stable",
  { skip: !browserAvailable, timeout: 180_000 },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    t.after(() => context.close());
    // URL capture first, then the reorder gate around whatever constructor it
    // installed; every non-reorder command still reaches the real owner.
    await captureDomainWorker(context);
    await context.addInitScript(() => {
      const holder = window as unknown as {
        SharedWorker?: new (url: string | URL, options?: unknown) => SharedWorker;
      };
      const Inner = holder.SharedWorker as unknown as
        | (new (url: string | URL, options?: unknown) => SharedWorker)
        | undefined;
      if (typeof Inner !== "function" || !Inner) return;
      function Gated(url: string | URL, options?: unknown): SharedWorker {
        const worker = new (Inner as new (url: string | URL, options?: unknown) => SharedWorker)(url, options);
        const realPort = worker.port;
        const handlers: { message?: ((event: MessageEvent) => void) | null } = {};
        const proxy = {
          postMessage(message: unknown): void {
            const flagged = (window as unknown as { __glypherieRejectReorder?: boolean }).__glypherieRejectReorder;
            const call = message as { id?: unknown; method?: unknown } | null;
            if (flagged === true && call !== null && typeof call === "object" && call.method === "reorderSceneLabels") {
              const id = call.id;
              window.setTimeout(() => {
                handlers.message?.({
                  data: {
                    id,
                    ok: false,
                    error: { code: "unavailable", message: 'Unknown domain method "reorderSceneLabels".' },
                  },
                } as MessageEvent);
              }, 60);
              return;
            }
            realPort.postMessage(message as never);
          },
          start(): void {
            realPort.start();
          },
          close(): void {
            try {
              realPort.close();
            } catch {
              // Best-effort teardown only.
            }
          },
          set onmessage(next: ((event: MessageEvent) => void) | null) {
            handlers.message = next;
            realPort.onmessage = (event) => handlers.message?.(event);
          },
          get onmessage(): ((event: MessageEvent) => void) | null {
            return handlers.message ?? null;
          },
          set onmessageerror(next: MessagePort["onmessageerror"]) {
            realPort.onmessageerror = next;
          },
          get onmessageerror(): MessagePort["onmessageerror"] {
            return realPort.onmessageerror;
          },
        };
        Object.defineProperty(worker, "port", { value: proxy, configurable: true });
        return worker;
      }
      Gated.prototype = Inner.prototype;
      holder.SharedWorker = Gated as unknown as typeof Inner;
    });
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    t.after(() => page.close());
    await bootLibrary(page, url);
    await ensureStyle(page, url);
    await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
    await openScreen(page);
    await createComposition(page, "Rejected drop scene");
    await addLabel(page, "Alpha");
    await waitLayerText(page, "Alpha");
    await addLabel(page, "Beta");
    await waitLayerText(page, "Beta");
    assert.deepEqual(await layerOrder(page), ["Beta", "Alpha"]);
    const alpha = await layerIdByText(page, "Alpha");

    const sampleReject = (): Promise<RejectFrame[]> =>
      page.evaluate(
        (): Promise<RejectFrame[]> =>
          new Promise((resolve) => {
            const frames: RejectFrame[] = [];
            const top = (query: string): number => document.querySelector(query)?.getBoundingClientRect().top ?? -9999;
            const tick = (): void => {
              const base = top("[data-screen-workspace]");
              frames.push({
                relLayers: top("[data-screen-layers-group]") - base,
                relStage: top("[data-screen-stage-scroll]") - base,
                statusH: document.querySelector("[data-screen-workspace-status]")?.getBoundingClientRect().height ?? -1,
                winX: window.scrollX,
                winY: window.scrollY,
                listTop: document.querySelector("[data-scene-layer-list]")?.scrollTop ?? -1,
                stageLeft: document.querySelector("[data-screen-stage-scroll]")?.scrollLeft ?? -1,
              });
              if (frames.length < 150) requestAnimationFrame(tick);
              else resolve(frames);
            };
            requestAnimationFrame(tick);
          }),
      );

    // Aim before sampling: scrolling the row into view must not pollute the
    // frame-by-frame scroll record. The drop itself uses only mouse movement.
    const aimBackToFront = async (): Promise<{ grabX: number; grabY: number; pitch: number }> => {
      const pitch = await page.evaluate(() => {
        const tops = [...document.querySelectorAll("[data-scene-layer]")]
          .map((row) => row.getBoundingClientRect().top)
          .sort((a, b) => a - b);
        return tops.length > 1 ? tops[1]! - tops[0]! : 40;
      });
      await page.locator(`[data-scene-layer="${alpha}"]`).scrollIntoViewIfNeeded();
      const box = await page.locator(`[data-scene-layer-text="${alpha}"]`).boundingBox();
      assert.ok(box, "row text exposes a bounding box");
      return { grabX: box.x + box.width / 2, grabY: box.y + box.height / 2, pitch };
    };

    // One pointer drop of the back row toward the front through the real
    // sortable sensors, sampled frame-by-frame across the async rejection.
    const dropBackToFront = async (aim: { grabX: number; grabY: number; pitch: number }): Promise<void> => {
      await page.mouse.move(aim.grabX, aim.grabY);
      await page.mouse.down();
      await page.mouse.move(aim.grabX, aim.grabY - aim.pitch * 1.5, { steps: 4 });
      await page.mouse.up();
    };

    const assertStill = (frames: RejectFrame[], label: string): void => {
      const spread = (values: number[]): number => Math.max(...values) - Math.min(...values);
      console.log(
        `${label}: frames=${frames.length} ` +
          `relLayers=${spread(frames.map((frame) => frame.relLayers)).toFixed(2)} ` +
          `relStage=${spread(frames.map((frame) => frame.relStage)).toFixed(2)} ` +
          `statusH=${spread(frames.map((frame) => frame.statusH)).toFixed(2)}`,
      );
      assert.equal(frames.length, 150, "sampler spans the drop and rejection");
      assert.ok(spread(frames.map((frame) => frame.relLayers)) <= 1, `${label}: layers hold still`);
      assert.ok(spread(frames.map((frame) => frame.relStage)) <= 1, `${label}: stage holds still`);
      assert.ok(spread(frames.map((frame) => frame.statusH)) <= 1, `${label}: status keeps its line`);
      assert.ok(
        frames.every((frame) => frame.winX === frames[0]!.winX && frame.winY === frames[0]!.winY),
        `${label}: no window scroll jump`,
      );
      assert.ok(
        frames.every((frame) => frame.listTop === frames[0]!.listTop),
        `${label}: layers list does not scroll`,
      );
      assert.ok(
        frames.every((frame) => frame.stageLeft === frames[0]!.stageLeft),
        `${label}: stage does not scroll`,
      );
    };

    await gateReorderRejection(page);
    const revision = await workspaceRevision(page);
    const firstAim = await aimBackToFront();
    const sampling = sampleReject();
    await dropBackToFront(firstAim);
    const firstFrames = await sampling;
    // The gated transport answers exactly like a pre-reorder owner; the
    // runtime maps it to the stale-owner app-version recovery, never raw internals.
    await page.locator("[data-screen-workspace-error]").waitFor();
    const alert = await page.locator("[data-screen-workspace-error]").innerText();
    assert.ok(
      alert.includes("different app versions") && alert.includes("Apply the pending app update"),
      `rejected drop names the app-version recovery, got ${alert}`,
    );
    assert.ok(!alert.includes("Unknown domain method"), `rejected drop hides internals, got ${alert}`);
    // The save is rejected: the optimistic order rolls back, no revision.
    await page.waitForFunction(
      (want) =>
        [...document.querySelectorAll("[data-scene-layer-text]")].map((entry) => entry.textContent).join("\0") ===
        want.join("\0"),
      ["Beta", "Alpha"],
      { timeout: 15000 },
    );
    assert.deepEqual(await layerOrder(page), ["Beta", "Alpha"]);
    assert.equal(await workspaceRevision(page), revision);
    const alertText = alert;
    assertStill(firstFrames, "first rejected drop");

    // Repeat the same failing drop while the mapped alert stays visible: the
    // message is reused in place, geometry and scroll hold still throughout.
    const secondAim = await aimBackToFront();
    const resampling = sampleReject();
    await dropBackToFront(secondAim);
    const secondFrames = await resampling;
    await page.waitForTimeout(500);
    assert.equal(
      await page.locator("[data-screen-workspace-error]").innerText(),
      alertText,
      "repeat failure reuses the alert",
    );
    assert.deepEqual(await layerOrder(page), ["Beta", "Alpha"]);
    assert.equal(await workspaceRevision(page), revision);
    assertStill(secondFrames, "repeated rejected drop");

    // The gate lifts: the same drop now commits, clears the alert, and keeps
    // the workspace-relative geometry it held while failing.
    await ungateReorderRejection(page);
    await dropBackToFront(await aimBackToFront());
    await waitWorkspaceRevision(page, revision);
    await waitLayerOrder(page, ["Alpha", "Beta"]);
    assert.deepEqual(await layerOrder(page), ["Alpha", "Beta"]);
    await page.waitForFunction(() => document.querySelector("[data-screen-workspace-error]") === null, null, {
      timeout: 15000,
    });
    const settled = await page.evaluate(() => {
      const top = (query: string): number => document.querySelector(query)?.getBoundingClientRect().top ?? -9999;
      return {
        relLayers: top("[data-screen-layers-group]") - top("[data-screen-workspace]"),
        relStage: top("[data-screen-stage-scroll]") - top("[data-screen-workspace]"),
        statusH: document.querySelector("[data-screen-workspace-status]")?.getBoundingClientRect().height ?? -1,
      };
    });
    for (const key of ["relLayers", "relStage", "statusH"] as const) {
      const before = firstFrames[0]![key];
      assert.ok(Math.abs(settled[key] - before) <= 1, `${key} holds still from rejection into success`);
    }
    assert.deepEqual(errors, []);
  },
);

test(
  "rejected drop keeps workspace geometry stable at 375px",
  { skip: !browserAvailable, timeout: 180_000 },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const context = await browser.newContext({ viewport: { width: 375, height: 800 } });
    t.after(() => context.close());
    // Same reorder gate as the wide-viewport rejection test: reorder calls
    // fail like a pre-reorder owner while every other command passes through.
    await captureDomainWorker(context);
    await context.addInitScript(() => {
      const holder = window as unknown as {
        SharedWorker?: new (url: string | URL, options?: unknown) => SharedWorker;
      };
      const Inner = holder.SharedWorker as unknown as
        | (new (url: string | URL, options?: unknown) => SharedWorker)
        | undefined;
      if (typeof Inner !== "function" || !Inner) return;
      function Gated(url: string | URL, options?: unknown): SharedWorker {
        const worker = new (Inner as new (url: string | URL, options?: unknown) => SharedWorker)(url, options);
        const realPort = worker.port;
        const handlers: { message?: ((event: MessageEvent) => void) | null } = {};
        const proxy = {
          postMessage(message: unknown): void {
            const flagged = (window as unknown as { __glypherieRejectReorder?: boolean }).__glypherieRejectReorder;
            const call = message as { id?: unknown; method?: unknown } | null;
            if (flagged === true && call !== null && typeof call === "object" && call.method === "reorderSceneLabels") {
              const id = call.id;
              window.setTimeout(() => {
                handlers.message?.({
                  data: {
                    id,
                    ok: false,
                    error: { code: "unavailable", message: 'Unknown domain method "reorderSceneLabels".' },
                  },
                } as MessageEvent);
              }, 60);
              return;
            }
            realPort.postMessage(message as never);
          },
          start(): void {
            realPort.start();
          },
          close(): void {
            try {
              realPort.close();
            } catch {
              // Best-effort teardown only.
            }
          },
          set onmessage(next: ((event: MessageEvent) => void) | null) {
            handlers.message = next;
            realPort.onmessage = (event) => handlers.message?.(event);
          },
          get onmessage(): ((event: MessageEvent) => void) | null {
            return handlers.message ?? null;
          },
          set onmessageerror(next: MessagePort["onmessageerror"]) {
            realPort.onmessageerror = next;
          },
          get onmessageerror(): MessagePort["onmessageerror"] {
            return realPort.onmessageerror;
          },
        };
        Object.defineProperty(worker, "port", { value: proxy, configurable: true });
        return worker;
      }
      Gated.prototype = Inner.prototype;
      holder.SharedWorker = Gated as unknown as typeof Inner;
    });
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    t.after(() => page.close());
    await bootLibrary(page, url);
    await ensureStyle(page, url);
    await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
    await openScreen(page);
    await createComposition(page, "Narrow rejected drop scene");
    await addLabel(page, "Alpha");
    await waitLayerText(page, "Alpha");
    await addLabel(page, "Beta");
    await waitLayerText(page, "Beta");
    assert.deepEqual(await layerOrder(page), ["Beta", "Alpha"]);
    const alpha = await layerIdByText(page, "Alpha");

    const frame = (): Promise<{ relLayers: number; relStage: number; statusH: number; winY: number }> =>
      page.evaluate(() => {
        const top = (query: string): number => document.querySelector(query)?.getBoundingClientRect().top ?? -9999;
        const base = top("[data-screen-workspace]");
        return {
          relLayers: top("[data-screen-layers-group]") - base,
          relStage: top("[data-screen-stage-scroll]") - base,
          statusH: document.querySelector("[data-screen-workspace-status]")?.getBoundingClientRect().height ?? -1,
          winY: window.scrollY,
        };
      });
    const aim = async (): Promise<{ grabX: number; grabY: number; pitch: number }> => {
      const pitch = await page.evaluate(() => {
        const tops = [...document.querySelectorAll("[data-scene-layer]")]
          .map((row) => row.getBoundingClientRect().top)
          .sort((a, b) => a - b);
        return tops.length > 1 ? tops[1]! - tops[0]! : 40;
      });
      await page.locator(`[data-scene-layer="${alpha}"]`).scrollIntoViewIfNeeded();
      const box = await page.locator(`[data-scene-layer-text="${alpha}"]`).boundingBox();
      assert.ok(box, "row text exposes a bounding box");
      return { grabX: box.x + box.width / 2, grabY: box.y + box.height / 2, pitch };
    };
    const drop = async (point: { grabX: number; grabY: number; pitch: number }): Promise<void> => {
      await page.mouse.move(point.grabX, point.grabY);
      await page.mouse.down();
      await page.mouse.move(point.grabX, point.grabY - point.pitch * 1.5, { steps: 4 });
      await page.mouse.up();
    };

    const calm = await frame();
    await gateReorderRejection(page);
    const revision = await workspaceRevision(page);
    await drop(await aim());
    await page.locator("[data-screen-workspace-error]").waitFor();
    const alert = await page.locator("[data-screen-workspace-error]").innerText();
    assert.ok(
      alert.includes("different app versions") && alert.includes("Apply the pending app update"),
      `rejected drop names the app-version recovery, got ${alert}`,
    );
    assert.ok(!alert.includes("Unknown domain method"), `rejected drop hides internals, got ${alert}`);
    await page.waitForFunction(
      () => [...document.querySelectorAll("[data-scene-layer]")].every((row) => row.getAnimations().length === 0),
      null,
      { timeout: 15000 },
    );
    const first = await frame();
    console.log(`narrow-375 calm=${JSON.stringify(calm)} first=${JSON.stringify(first)} alertLen=${alert.length}`);

    // Repeat while visible: same message, no geometry or scroll movement.
    await drop(await aim());
    await page.waitForTimeout(500);
    assert.equal(
      await page.locator("[data-screen-workspace-error]").innerText(),
      alert,
      "repeat failure reuses the alert",
    );
    assert.deepEqual(await layerOrder(page), ["Beta", "Alpha"]);
    assert.equal(await workspaceRevision(page), revision);
    const second = await frame();
    console.log(`narrow-375 second=${JSON.stringify(second)}`);

    // Lift the gate: the same drop commits, clears the alert, holds geometry.
    await ungateReorderRejection(page);
    await drop(await aim());
    await waitWorkspaceRevision(page, revision);
    await waitLayerOrder(page, ["Alpha", "Beta"]);
    await page.waitForFunction(() => document.querySelector("[data-screen-workspace-error]") === null, null, {
      timeout: 15000,
    });
    const settled = await frame();
    console.log(`narrow-375 settled=${JSON.stringify(settled)}`);

    for (const key of ["relLayers", "relStage", "statusH"] as const) {
      assert.ok(
        Math.abs(first[key] - calm[key]) <= 1,
        `375px: ${key} holds still on first error (calm=${calm[key]}, first=${first[key]})`,
      );
      assert.ok(
        Math.abs(second[key] - first[key]) <= 1,
        `375px: ${key} holds still on repeat (first=${first[key]}, second=${second[key]})`,
      );
      assert.ok(
        Math.abs(settled[key] - first[key]) <= 1,
        `375px: ${key} holds still into success (first=${first[key]}, settled=${settled[key]})`,
      );
    }
    assert.ok(Math.abs(second.winY - first.winY) <= 1, "375px: repeat failure scrolls nothing");
    assert.deepEqual(errors, []);
  },
);

// SharedWorker seam for default-composition failure probes: while
// window.__failDomainMethod names a command every matching call rejects once
// it reaches the app, while the handshake and every other command pass
// through to the live owner. The test arms and clears the flag; the seam
// never fires on its own.
async function armMethodFailure(page: Parameters<typeof cardNames>[0], method: string): Promise<void> {
  await page.evaluate((name) => {
    (window as unknown as { __failDomainMethod?: string | null }).__failDomainMethod = name;
  }, method);
}

async function clearMethodFailure(page: Parameters<typeof cardNames>[0]): Promise<void> {
  await page.evaluate(() => {
    (window as unknown as { __failDomainMethod?: string | null }).__failDomainMethod = null;
  });
}

async function installMethodFailureSeam(context: BrowserContext): Promise<void> {
  await context.addInitScript(() => {
    const holder = window as unknown as {
      SharedWorker?: unknown;
      __failDomainMethod?: string | null;
    };
    const Ctor = holder.SharedWorker as unknown as
      | (new (url: string | URL, options?: unknown) => SharedWorker)
      | undefined;
    if (typeof Ctor !== "function" || !Ctor) return;
    function Wrapped(this: unknown, url: string | URL, options?: unknown): SharedWorker {
      const worker = new (Ctor as new (url: string | URL, options?: unknown) => SharedWorker)(url, options);
      try {
        const port = worker.port;
        const send = port.postMessage.bind(port);
        port.postMessage = (message: unknown) => {
          const call = message as { id?: unknown; method?: unknown } | null;
          if (
            holder.__failDomainMethod != null &&
            call !== null &&
            typeof call === "object" &&
            call.method === holder.__failDomainMethod &&
            typeof call.id === "number"
          ) {
            const id = call.id;
            window.setTimeout(() => {
              try {
                port.onmessage?.({
                  data: {
                    id,
                    ok: false,
                    error: { code: "unavailable", message: `Simulated ${String(holder.__failDomainMethod)} failure.` },
                  },
                } as MessageEvent);
              } catch {
                // Test seam only; the app treats this as a rejected read.
              }
            }, 0);
            return;
          }
          send(message as never);
        };
      } catch {
        // Exotic ports pass through unwrapped; the probe simply never fires.
      }
      return worker;
    }
    Wrapped.prototype = (Ctor as unknown as { prototype: unknown }).prototype;
    holder.SharedWorker = Wrapped as unknown;
  });
}

test(
  "a failed default ensure shows Retry and recovers without losing saved work",
  { skip: !browserAvailable, timeout: 180_000 },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    t.after(() => context.close());

    // Seed one saved composition before any failure is injected.
    const seed = await context.newPage();
    t.after(() => seed.close());
    await bootLibrary(seed, url);
    await ensureStyle(seed, url);
    await seed.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
    await openScreen(seed);
    await createComposition(seed, "Kept scene");
    await addLabel(seed, "Kept label");
    await waitLayerText(seed, "Kept label");
    await seed.close();

    // Every ensureDefaultScene call fails while the flag holds; the handshake
    // still succeeds, so this is a read failure after a live owner, not a dead one.
    await installMethodFailureSeam(context);
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    t.after(() => page.close());
    await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
    await armMethodFailure(page, "ensureDefaultScene");
    await openScreen(page);

    // The failed ensure must surface an actionable error with Retry, never a
    // permanent spinner or a half-opened workspace.
    await page.locator("[data-screen-default-error]").waitFor({ timeout: 15000 });
    assert.equal(await page.locator("[data-screen-workspace]").count(), 0, "a failed ensure opens no workspace");
    await clearMethodFailure(page);
    await page.locator("[data-screen-default-retry]").click();
    await waitWorkspace(page);
    // Recovery adopts the seeded composition with its content intact.
    await waitLayerText(page, "Kept label");
    assert.deepEqual(errors, []);
  },
);

test(
  "a failed composition refresh keeps the loaded workspace and recovers on retry",
  { skip: !browserAvailable, timeout: 180_000 },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    t.after(() => context.close());
    await installMethodFailureSeam(context);
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    t.after(() => page.close());
    await bootLibrary(page, url);
    await ensureStyle(page, url);
    await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
    await openScreen(page);
    await createComposition(page, "Kept workspace");
    await addLabel(page, "Kept label");
    await waitLayerText(page, "Kept label");
    const revision = await workspaceRevision(page);

    // Fail the refresh behind a real write: a second tab saves coverage (the
    // commit succeeds and announces) while every getScene re-read on this tab
    // rejects, including the notification reload the commit itself triggers.
    const peer = await context.newPage();
    t.after(() => peer.close());
    await peer.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
    await waitWorkspace(peer);
    await armMethodFailure(page, "getScene");
    await peer.getByRole("switch", { name: /Greek/i }).click();
    await peer.locator("[data-screen-save-coverage]").click();

    // Loaded content survives the failed refresh: the label stays with an
    // actionable error, never a wiped workspace.
    await page.locator("[data-screen-workspace-error]").waitFor({ timeout: 15000 });
    await waitLayerText(page, "Kept label");
    assert.equal(await page.locator("[data-screen-workspace]").count(), 1, "a failed refresh keeps the workspace");
    await clearMethodFailure(page);
    await page.locator("[data-screen-workspace-retry]").click();
    await waitWorkspaceRevision(page, revision);
    assert.equal(await page.getByRole("switch", { name: /Greek/i }).isChecked(), true);
    await waitLayerText(page, "Kept label");
    assert.deepEqual(errors, []);
  },
);
