import { addScreenText } from "../helpers/screen-tools.ts";
// Screen direct-font labels against the real WASM preview renderer: adding
// from the Fonts group with no saved variants, live resize through the
// renderer (font size and saved width, never CSS stretching), reload
// persistence, bidirectional conversion with variant labels (handles and
// grey outline follow the kind), the inert plus button, editing, duplicate
// and undo. Nothing here measures browser glyphs; every coordinate comes
// from the committed diagnostics.layout.editing stops.
import assert from "node:assert/strict";
import test from "node:test";
import {
  bootLibrary,
  browserAvailable,
  buildApp,
  cardIds,
  cardNames,
  launch,
  openNewVariant,
  servePrefix,
} from "../helpers/spa-helpers.ts";

async function screenReady(page: Parameters<typeof cardNames>[0]): Promise<void> {
  await page.waitForFunction(() => document.querySelector("[data-screen-page]") !== null);
}

async function openScreen(page: Parameters<typeof cardNames>[0], url: string): Promise<void> {
  await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
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

async function containerIds(page: Parameters<typeof cardNames>[0]): Promise<string[]> {
  return page
    .locator("[data-scene-label-container]")
    .evaluateAll((elements) => elements.map((element) => element.getAttribute("data-scene-label-container") ?? ""));
}

async function waitPainted(page: Parameters<typeof cardNames>[0], id: string): Promise<void> {
  await page.waitForFunction(
    (placementId) => {
      const viewport = document.querySelector(`[data-scene-label="${placementId}"]`);
      const canvas = viewport?.querySelector("canvas");
      return canvas instanceof HTMLCanvasElement && canvas.dataset.rendered === "true";
    },
    id,
    { timeout: 20000 },
  );
}

async function selectOption(page: Parameters<typeof cardNames>[0], trigger: string, name: string): Promise<void> {
  await page.locator(trigger).click();
  await page.getByRole("option", { name, exact: true }).click();
}

async function addDirectLabel(
  page: Parameters<typeof cardNames>[0],
  text: string,
  fontName: string,
  waitForPaint = true,
  // Native device spawn. The default (8, 8) edge spawn keeps boundary
  // clipping coverage; tests exercising full handle geometry spawn interior.
  position?: { x: number; y: number },
): Promise<string> {
  const known = await containerIds(page);
  await addScreenText(page, text, { fontName, ...(position ?? {}) });
  await page.waitForFunction(
    (knownIds) =>
      [...document.querySelectorAll("[data-scene-label-container]")].some((element) => {
        const id = element.getAttribute("data-scene-label-container");
        return id !== null && !knownIds.includes(id);
      }),
    known,
    { timeout: 20000 },
  );
  const id = (await containerIds(page)).find((value) => value !== "" && !known.includes(value));
  assert.ok(id);
  if (waitForPaint) await waitPainted(page, id);
  return id;
}

async function selectLabel(page: Parameters<typeof cardNames>[0], id: string): Promise<void> {
  await page.locator(`[data-scene-label-frame="${id}"]`).click();
  await page.locator(`[data-scene-inspector="${id}"]`).waitFor();
}

// True resize handles only: the selection outline edges share the
// moveable-direction class, so a bare class count would mistake the outline
// for handles.
async function visibleHandleCount(page: Parameters<typeof cardNames>[0]): Promise<number> {
  return page.locator(".moveable-control-box .moveable-control.moveable-direction").evaluateAll(
    (elements) =>
      elements.filter((element) => {
        const box = element.getBoundingClientRect();
        return box.width > 0 && box.height > 0;
      }).length,
  );
}

async function greyOutlineCount(page: Parameters<typeof cardNames>[0]): Promise<number> {
  return page.locator(".moveable-control-box.scene-moveable-variant").count();
}

async function typographyValue(page: Parameters<typeof cardNames>[0], name: string): Promise<string> {
  return page.locator(`[data-scene-typography] [data-scene-typography-${name}]`).inputValue();
}

async function inspectorValue(page: Parameters<typeof cardNames>[0], name: string): Promise<string> {
  return page.locator(`[data-scene-inspector] [data-scene-inspector-${name}]`).inputValue();
}

// Rendered wrap width in CSS px: the label container's inline width reflects
// the saved native wrap width through the presentation scale. Resize and
// reload assertions read this public geometry instead of a width input.
async function wrapWidthCss(page: Parameters<typeof cardNames>[0], id: string): Promise<string> {
  return page.evaluate((placementId) => {
    const container = document.querySelector(`[data-scene-label-container="${placementId}"]`);
    if (!(container instanceof HTMLElement)) throw new Error("missing label container");
    return container.style.width;
  }, id);
}

// Rendered stage-frame accessible name for the label: the Position panel no
// longer repeats the text, so assertions read the frame with the placement
// id instead of the removed inspector paragraph.
async function frameLabel(page: Parameters<typeof cardNames>[0], id: string): Promise<string | null> {
  return page.locator(`[data-scene-label-frame="${id}"]`).getAttribute("aria-label");
}

// Center of one corner resize handle in viewport CSS px. Direction handles
// carry data-direction="nw|ne|sw|se" from the Moveable renderer.
async function handleCenter(page: Parameters<typeof cardNames>[0], dir: string): Promise<{ x: number; y: number }> {
  return page.evaluate((direction) => {
    const handle = document.querySelector(
      `.moveable-control-box .moveable-control.moveable-direction[data-direction="${direction}"]`,
    );
    if (!(handle instanceof HTMLElement)) throw new Error(`missing ${direction} resize handle`);
    const box = handle.getBoundingClientRect();
    if (box.width <= 0 || box.height <= 0) throw new Error(`${direction} resize handle has no size`);
    return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  }, dir);
}

// 3x3 elementFromPoint grid over one handle: every sub-point must resolve to
// the handle itself. A handle clipped by an ancestor overflow context fails
// here even though it still paints.
async function handleHitGrid(
  page: Parameters<typeof cardNames>[0],
  dir: string,
): Promise<{ center: boolean; hits: number }> {
  return page.evaluate((direction) => {
    const handle = document.querySelector(
      `.moveable-control-box .moveable-control.moveable-direction[data-direction="${direction}"]`,
    );
    if (!(handle instanceof HTMLElement)) throw new Error(`missing ${direction} resize handle`);
    const box = handle.getBoundingClientRect();
    let hits = 0;
    for (const fx of [0.2, 0.5, 0.8]) {
      for (const fy of [0.2, 0.5, 0.8]) {
        const top = document.elementFromPoint(box.x + box.width * fx, box.y + box.height * fy);
        if (top === handle || (top instanceof Element && handle.contains(top))) hits += 1;
      }
    }
    const centerTop = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
    return {
      center: centerTop === handle || (centerTop instanceof Element && handle.contains(centerTop)),
      hits,
    };
  }, dir);
}

async function dragHandle(page: Parameters<typeof cardNames>[0], dir: string, dx: number, dy: number): Promise<void> {
  const start = await handleCenter(page, dir);
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(start.x + dx, start.y + dy, { steps: 8 });
  await page.mouse.up();
}

async function frameRect(
  page: Parameters<typeof cardNames>[0],
  id: string,
): Promise<{ x: number; y: number; width: number; height: number }> {
  return page.evaluate((placementId) => {
    const frame = document.querySelector(`[data-scene-label-frame="${placementId}"]`);
    if (!(frame instanceof HTMLElement)) throw new Error("missing label frame");
    const box = frame.getBoundingClientRect();
    return { x: box.x, y: box.y, width: box.width, height: box.height };
  }, id);
}

// The committed ink frame after the asynchronous repaint/release settles:
// polls until two consecutive reads agree, so the measurement reflects the
// real renderer geometry rather than a mid-repaint transient.
async function settledFrameRect(
  page: Parameters<typeof cardNames>[0],
  id: string,
): Promise<{ x: number; y: number; width: number; height: number }> {
  await page.waitForFunction(
    (placementId) => {
      const frame = document.querySelector(`[data-scene-label-frame="${placementId}"]`);
      if (!(frame instanceof HTMLElement)) return false;
      const box = frame.getBoundingClientRect();
      // A release clears the gesture size before the committed repaint lands,
      // so the frame is briefly zero-sized; only real renderer geometry
      // counts as settled.
      if (box.width <= 0 || box.height <= 0) return false;
      const current = [box.x, box.y, box.width, box.height].map((value) => value.toFixed(2)).join(",");
      const store = window as unknown as { __settledFrameRect?: string };
      const settled = store.__settledFrameRect === `${placementId}:${current}`;
      store.__settledFrameRect = `${placementId}:${current}`;
      return settled;
    },
    id,
    { timeout: 20000 },
  );
  return frameRect(page, id);
}

// CSS px per native device px, recovered from the container's inline style
// against the native inspector value. Fresh labels spawn at (8, 8).
async function workspaceRevision(page: Parameters<typeof cardNames>[0]): Promise<string> {
  return (await page.locator("[data-screen-workspace]").getAttribute("data-screen-revision")) ?? "";
}

// The deferred resize save lands on the repaint, after the pending preview
// already shows the released values; wait for the revision to advance so the
// reads below observe the committed save rather than the preview.
async function waitForRevision(page: Parameters<typeof cardNames>[0], before: string): Promise<void> {
  await page.waitForFunction(
    (expected) => document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision") !== expected,
    before,
    { timeout: 20000 },
  );
}

// Opposite ink corner in scene-native device px: the frame rect against the
// container rect, converted by the measured cssScale and rooted at the
// committed native position.
async function anchorNative(
  page: Parameters<typeof cardNames>[0],
  id: string,
  scale: number,
  xNat: number,
  yNat: number,
  fixed: string,
): Promise<{ x: number; y: number }> {
  return page.evaluate(
    ([placementId, cssScale, nativeX, nativeY, fixedCorner]) => {
      const container = document.querySelector(`[data-scene-label-container="${placementId}"]`);
      const frame = document.querySelector(`[data-scene-label-frame="${placementId}"]`);
      if (!(container instanceof HTMLElement) || !(frame instanceof HTMLElement)) {
        throw new Error("missing label geometry");
      }
      const containerBox = container.getBoundingClientRect();
      const frameBox = frame.getBoundingClientRect();
      let cornerX = frameBox.x;
      let cornerY = frameBox.y;
      if (fixedCorner === "se" || fixedCorner === "ne") cornerX = frameBox.x + frameBox.width;
      if (fixedCorner === "se" || fixedCorner === "sw") cornerY = frameBox.y + frameBox.height;
      return {
        x: nativeX + (cornerX - containerBox.x) / cssScale,
        y: nativeY + (cornerY - containerBox.y) / cssScale,
      };
    },
    [id, scale, xNat, yNat, fixed] as const,
  );
}

async function domCssScale(page: Parameters<typeof cardNames>[0], id: string): Promise<number> {
  const left = await page.evaluate((placementId) => {
    const container = document.querySelector(`[data-scene-label-container="${placementId}"]`);
    if (!(container instanceof HTMLElement)) throw new Error("missing label container");
    return container.style.left;
  }, id);
  const x = Number(await inspectorValue(page, "x"));
  assert.ok(x !== 0, "cssScale probe needs a nonzero native x");
  return Number.parseFloat(left) / x;
}

async function deleteLabel(page: Parameters<typeof cardNames>[0], id: string): Promise<void> {
  const before = await containerIds(page);
  assert.ok(before.includes(id));
  // Select through the layers panel: a resized label may hang off-paper,
  // where its frame center is no longer clickable. The frame itself takes
  // keyboard focus without a hit test, so Delete reaches it.
  await page.locator(`[data-scene-layer-handle="${id}"]`).click();
  await page.locator(`[data-scene-inspector="${id}"]`).waitFor();
  await page.locator(`[data-scene-label-frame="${id}"]`).focus();
  await page.keyboard.press("Delete");
  await page.waitForFunction(
    (known) => document.querySelectorAll("[data-scene-label-container]").length === known.length - 1,
    before,
    { timeout: 20000 },
  );
}

// Drags the resize handle nearest the control box's bottom-right corner by a
// CSS pixel delta, the corner Moveable uses for southeast resizing.
async function dragCornerHandle(page: Parameters<typeof cardNames>[0], dx: number, dy: number): Promise<void> {
  const start = await page
    .locator(".moveable-control-box .moveable-control.moveable-direction")
    .evaluateAll((elements) => {
      const centers = elements.map((element) => {
        const box = element.getBoundingClientRect();
        return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
      });
      if (centers.length === 0) throw new Error("a direct label shows resize handles");
      let best = centers[0]!;
      for (const center of centers) {
        if (center.x + center.y > best.x + best.y) best = center;
      }
      return best;
    });
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(start.x + dx, start.y + dy, { steps: 8 });
  await page.mouse.up();
}

async function settleFrames(page: Parameters<typeof cardNames>[0]): Promise<void> {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
      }),
  );
}

test(
  "direct font labels add without variants, resize through the renderer and persist",
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
    await openScreen(page, url);
    await page.locator("[data-screen-workspace]").waitFor({ timeout: 20000 });

    // No saved variants exist on this fresh profile, yet the Fonts group
    // offers every library font.
    const id = await addDirectLabel(page, "Direct", "Literata");
    await selectLabel(page, id);
    assert.equal(await typographyValue(page, "size"), "16");
    const widthBefore = Number.parseFloat(await wrapWidthCss(page, id));
    assert.ok(widthBefore > 0);

    // Direct labels expose resize handles with no grey override.
    await page.waitForFunction(
      () =>
        [...document.querySelectorAll(".moveable-control-box .moveable-control.moveable-direction")].some(
          (element) => element.getBoundingClientRect().width > 0,
        ),
      undefined,
      { timeout: 20000 },
    );
    assert.ok((await visibleHandleCount(page)) > 0, "direct labels show resize handles");
    assert.equal(await greyOutlineCount(page), 0);

    // The plus button is inert: clicking changes nothing and raises nothing.
    await page.locator("[data-scene-typography-plus]").click();
    await page.locator(`[data-scene-inspector="${id}"]`).waitFor();
    assert.equal(await typographyValue(page, "size"), "16");

    // A corner drag grows the wrap width and the renderer's own font size;
    // the committed paint follows through the real WASM path. The revision
    // baseline predates the gesture (see the corner test).
    const revisionBeforeResize = await workspaceRevision(page);
    await dragCornerHandle(page, 72, 48);
    await page.waitForFunction(
      (before) =>
        Number((document.querySelector("[data-scene-typography-size]") as HTMLInputElement | null)?.value ?? "16") !==
        before,
      16,
      { timeout: 20000 },
    );
    const sizeAfter = Number(await typographyValue(page, "size"));
    const widthAfter = Number.parseFloat(await wrapWidthCss(page, id));
    assert.ok(sizeAfter > 16, `font size grows with resize, got ${sizeAfter}`);
    assert.ok(widthAfter > widthBefore, `saved width grows with resize, got ${widthAfter}`);
    // The save lands on the repaint; wait for the revision before reloading
    // so the reload observes the committed resize rather than racing it.
    await waitForRevision(page, revisionBeforeResize);
    await settleFrames(page);

    // Reload keeps the resized size, width and text.
    await page.reload({ waitUntil: "domcontentloaded" });
    await screenReady(page);
    await page.locator("[data-screen-workspace]").waitFor();
    await waitPainted(page, id);
    await page.locator(`[data-scene-label-frame="${id}"]`).click();
    assert.equal(await typographyValue(page, "size"), String(sizeAfter));
    assert.equal(Number.parseFloat(await wrapWidthCss(page, id)), widthAfter);
    assert.equal(await frameLabel(page, id), "Label Direct. Press Enter to edit.");

    // In-place editing still commits through the native caret path.
    await page.locator(`[data-scene-label-frame="${id}"]`).press("Enter");
    await page.locator(`[data-scene-edit-text="${id}"]`).waitFor();
    await page.keyboard.type("!");
    await page.keyboard.press("ControlOrMeta+Enter");
    await page.waitForFunction(
      (placementId) => document.querySelector(`[data-scene-edit-text="${placementId}"]`) === null,
      id,
    );
    assert.equal(await frameLabel(page, id), "Label Direct!. Press Enter to edit.");
    assert.deepEqual(errors, []);
  },
);

// Direct weight override on a variable font: the typography panel edits the
// wght axis (never the wrap width), the WASM canvas repaints through the
// real renderer, size and wrap geometry stay put, the second label keeps
// the font default, and undo/redo plus reload preserve the override.
test("direct label weight edits repaint through the renderer and persist", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);
  await openScreen(page, url);
  await page.locator("[data-screen-workspace]").waitFor({ timeout: 20000 });

  const id = await addDirectLabel(page, "Weighty", "Roboto Flex");
  await selectLabel(page, id);
  const weightInput = page.locator(`[data-scene-typography] [data-scene-typography-weight]`);
  const min = Number(await weightInput.getAttribute("min"));
  const max = Number(await weightInput.getAttribute("max"));
  assert.ok(
    Number.isFinite(min) && Number.isFinite(max) && min < max,
    `weight bounds come from the font metadata, got ${min}..${max}`,
  );
  const weightDefault = await weightInput.inputValue();
  assert.ok(
    Number(weightDefault) >= min && Number(weightDefault) <= max,
    `fresh labels show the font default, got ${weightDefault}`,
  );
  assert.notEqual(String(max), weightDefault, "the override target differs from the default");
  const sizeBefore = await typographyValue(page, "size");
  const wrapBefore = await wrapWidthCss(page, id);
  const canvas = page.locator(`[data-scene-label="${id}"] canvas`);
  const rasterBefore = await canvas.evaluate((element) => (element as HTMLCanvasElement).toDataURL());

  // A heavier override repaints without touching size or wrap geometry.
  const revisionBefore = await workspaceRevision(page);
  await weightInput.fill(String(max));
  await weightInput.press("Enter");
  await waitForRevision(page, revisionBefore);
  assert.equal(await weightInput.inputValue(), String(max));
  assert.equal(await typographyValue(page, "size"), sizeBefore);
  assert.equal(await wrapWidthCss(page, id), wrapBefore);
  await page.waitForFunction(
    ({ placementId, before }) => {
      const viewport = document.querySelector(`[data-scene-label="${placementId}"]`);
      const painted = viewport?.querySelector("canvas");
      return (
        painted instanceof HTMLCanvasElement && painted.dataset.rendered === "true" && painted.toDataURL() !== before
      );
    },
    { placementId: id, before: rasterBefore },
    { timeout: 20000 },
  );

  // Undo drops the override, redo restores it; selection clears across the
  // snapshot restore, so each read re-selects the label.
  const revisionAfterWeight = await workspaceRevision(page);
  await page.locator("[data-screen-undo]").click();
  await waitForRevision(page, revisionAfterWeight);
  await page.locator(`[data-scene-label-frame="${id}"]`).click();
  assert.equal(await typographyValue(page, "weight"), weightDefault);
  const revisionAfterUndo = await workspaceRevision(page);
  await page.locator("[data-screen-redo]").click();
  await waitForRevision(page, revisionAfterUndo);
  await page.locator(`[data-scene-label-frame="${id}"]`).click();
  assert.equal(await typographyValue(page, "weight"), String(max));

  // A second label on the same font keeps the default independently.
  const other = await addDirectLabel(page, "Plain", "Roboto Flex");
  await selectLabel(page, other);
  assert.equal(await typographyValue(page, "weight"), weightDefault);

  // Reload persists the override on the first label only.
  await page.reload({ waitUntil: "domcontentloaded" });
  await screenReady(page);
  await page.locator("[data-screen-workspace]").waitFor();
  await waitPainted(page, id);
  await page.locator(`[data-scene-label-frame="${id}"]`).click();
  assert.equal(await typographyValue(page, "weight"), String(max));
  assert.equal(await typographyValue(page, "size"), sizeBefore);
  assert.equal(await wrapWidthCss(page, id), wrapBefore);

  // A variant-backed label shows its saved weight read-only, never editable.
  // ensureStyle reads the library cards, so navigate to the fonts page
  // first: the reload above leaves the workspace on the Screen page.
  await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  await ensureStyle(page, url);
  await openScreen(page, url);
  await page.locator("[data-screen-workspace]").waitFor({ timeout: 20000 });
  const styledId = await addScreenText(page, "Styled", { variant: true });
  await waitPainted(page, styledId);
  await selectLabel(page, styledId);
  const savedWeight = page.locator(`[data-scene-typography] [data-scene-typography-weight]`);
  assert.match(await savedWeight.inputValue(), /^\d+$/, "variant labels show the saved weight");
  assert.notEqual(await savedWeight.getAttribute("readonly"), null, "variant weight stays read-only");
  assert.deepEqual(errors, []);
});

test("labels convert both ways with handles and outline following the kind", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.addInitScript(() => {
    const gate = { blocked: false, pending: [] as Array<() => void>, sizes: [] as number[] };
    (window as unknown as { __screenRenderGate: typeof gate }).__screenRenderGate = gate;
    const post = Worker.prototype.postMessage;
    Worker.prototype.postMessage = function (message, options): void {
      const send = (): void => {
        Reflect.apply(post, this, [message, options]);
      };
      if (gate.blocked && message?.kind === "render") {
        gate.sizes.push(message.spec.size_px);
        gate.pending.push(send);
      } else send();
    };
  });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);
  await ensureStyle(page, url);
  await openScreen(page, url);
  await page.locator("[data-screen-workspace]").waitFor({ timeout: 20000 });

  const found = await addScreenText(page, "Convert", { variant: true });
  const styleOption = (await page.locator("[data-scene-inspector-style]").textContent()) ?? "";
  const id: string = found;
  await waitPainted(page, id);
  await selectLabel(page, id);

  // Variant-backed labels drag with a grey outline and no resize handles.
  await page.locator(".moveable-control-box").first().waitFor();
  assert.equal(await visibleHandleCount(page), 0, "variant labels show no resize handles");
  assert.equal(await greyOutlineCount(page), 1, "variant labels use the grey outline");
  const weight = await typographyValue(page, "weight");
  const savedSize = await typographyValue(page, "size");
  const variantRaster = await page
    .locator(`[data-scene-label="${id}"] canvas`)
    .evaluate((canvas) => (canvas as HTMLCanvasElement).toDataURL());
  assert.match(weight, /^\d+$/, `weight shows the saved variant value, got ${weight}`);

  // Switching to a font keeps the painted size and wrap and enables handles.
  await selectOption(page, "[data-scene-inspector-style]", "Literata");
  await page.waitForFunction(
    () =>
      [...document.querySelectorAll(".moveable-control-box .moveable-control.moveable-direction")].some(
        (element) => element.getBoundingClientRect().width > 0,
      ),
    undefined,
    { timeout: 20000 },
  );
  assert.ok((await visibleHandleCount(page)) > 0, "direct labels show resize handles after conversion");
  assert.equal(await greyOutlineCount(page), 0);
  assert.equal(await typographyValue(page, "size"), savedSize);

  // Hold the resize repaint so switching reference exercises the awaiting
  // release window deterministically, rather than racing the real worker.
  await waitPainted(page, id);
  await page.waitForFunction(
    ({ placementId, raster }) => {
      const canvas = document.querySelector(`[data-scene-label="${placementId}"] canvas`);
      return canvas instanceof HTMLCanvasElement && canvas.dataset.rendered === "true" && canvas.toDataURL() !== raster;
    },
    { placementId: id, raster: variantRaster },
  );
  await settledFrameRect(page, id);
  await page.evaluate(() => {
    (window as unknown as { __screenRenderGate: { blocked: boolean } }).__screenRenderGate.blocked = true;
  });
  await dragCornerHandle(page, 48, 32);
  await page.waitForFunction(
    (size) =>
      (window as unknown as { __screenRenderGate: { sizes: number[] } }).__screenRenderGate.sizes.some(
        (held) => held > Number(size),
      ),
    savedSize,
  );

  // Switching back restores the saved variant values, grey outline and no handles.
  // The style re-resolves asynchronously, so the frame transiently unmounts;
  // wait for the grey box itself rather than any handle absence.
  await selectOption(page, "[data-scene-inspector-style]", styleOption);
  await page.evaluate(() => {
    const gate = (
      window as unknown as {
        __screenRenderGate: { blocked: boolean; pending: Array<() => void> };
      }
    ).__screenRenderGate;
    gate.blocked = false;
    for (const send of gate.pending.splice(0)) send();
  });
  await page.waitForFunction(
    ({ placementId, raster }) => {
      const canvas = document.querySelector(`[data-scene-label="${placementId}"] canvas`);
      return canvas instanceof HTMLCanvasElement && canvas.dataset.rendered === "true" && canvas.toDataURL() === raster;
    },
    { placementId: id, raster: variantRaster },
    { timeout: 20000 },
  );
  await page.waitForFunction(
    () => document.querySelector(".moveable-control-box.scene-moveable-variant") !== null,
    undefined,
    { timeout: 20000 },
  );
  assert.equal(await greyOutlineCount(page), 1);
  assert.equal(await typographyValue(page, "weight"), weight);
  assert.equal(await typographyValue(page, "size"), savedSize);

  // Reload keeps the converted-back variant label.
  await page.reload({ waitUntil: "domcontentloaded" });
  await screenReady(page);
  await page.locator("[data-screen-workspace]").waitFor();
  await waitPainted(page, id);
  await page.locator(`[data-scene-label-frame="${id}"]`).click();
  assert.equal(await typographyValue(page, "size"), savedSize);
  assert.equal(await greyOutlineCount(page), 1);
  assert.deepEqual(errors, []);
});

test("identical direct labels survive delete, undo and reload", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);
  await openScreen(page, url);
  await page.locator("[data-screen-workspace]").waitFor({ timeout: 20000 });

  // The panel no longer offers a duplicate icon, so the pair is two normal
  // adds of the same text; undo/redo and reload cover the same history path
  // as the removed duplication setup did.
  const id = await addDirectLabel(page, "Dupe", "Literata");
  const copy = await addDirectLabel(page, "Dupe", "Literata");
  assert.notEqual(copy, id);
  assert.equal(await page.locator("[data-scene-label-container]").count(), 2);

  // Undo drops the duplicate; redo restores it with its size and width under
  // a fresh placement id (snapshot restores never reuse expired ids).
  await page.locator("[data-screen-undo]").click();
  await page.waitForFunction(() => document.querySelectorAll("[data-scene-label-container]").length === 1);
  await page.locator("[data-screen-redo]").click();
  await page.waitForFunction(() => document.querySelectorAll("[data-scene-label-container]").length === 2);
  const revived = (await containerIds(page)).find((value) => value !== "" && value !== id);
  assert.ok(revived);
  const copy2: string = revived;
  await page.locator(`[data-scene-label-frame="${copy2}"]`).click();
  assert.equal(await typographyValue(page, "size"), "16");

  // Text edits commit and survive reload on the duplicate.
  await page.locator(`[data-scene-label-frame="${copy2}"]`).press("Enter");
  await page.locator(`[data-scene-edit-text="${copy2}"]`).waitFor();
  await page.keyboard.type("2");
  await page.keyboard.press("ControlOrMeta+Enter");
  await page.waitForFunction(
    (placementId) => document.querySelector(`[data-scene-edit-text="${placementId}"]`) === null,
    copy2,
  );
  await page.reload({ waitUntil: "domcontentloaded" });
  await screenReady(page);
  await page.locator("[data-screen-workspace]").waitFor();
  await waitPainted(page, copy2);
  await page.locator(`[data-scene-label-frame="${copy2}"]`).click();
  assert.equal(await frameLabel(page, copy2), "Label Dupe2. Press Enter to edit.");
  assert.equal(await typographyValue(page, "size"), "16");
  assert.deepEqual(errors, []);
});

// Each corner handle resizes through the renderer with the opposite ink
// corner anchored, at the default edge spawn, a non-unit cssScale (Xteink X4,
// 220 PPI, size 100% -> 96/220 CSS px per native px), and across reload.
// Outward drag per corner; the fixed corner is the one opposite the drag.
test("each corner resizes with the opposite ink corner anchored", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);
  await openScreen(page, url);
  await page.locator("[data-screen-workspace]").waitFor({ timeout: 20000 });

  // Large outward drags on distinct texts: span ~2.5-3 exercises differing
  // renderer ink offsets per text and size, which a stretched-rectangle
  // anchor cannot survive. The save below corrects against the repaint's
  // measured frame bounds, so the opposite corner must hold within native
  // integer rounding.
  const corners = [
    { dir: "nw", dx: -48, dy: -32, fixed: "se" },
    { dir: "ne", dx: 48, dy: -32, fixed: "sw" },
    { dir: "sw", dx: -48, dy: 32, fixed: "ne" },
    { dir: "se", dx: 48, dy: 32, fixed: "nw" },
  ] as const;
  // Native rounding is the only error the correction introduces (measured
  // far corners quantize below one native px per paint, plus integer
  // position rounding), so the anchor must hold within 2 native px.
  const assertAnchored = (before: { x: number; y: number }, after: { x: number; y: number }, what: string): void => {
    assert.ok(
      Math.abs(after.x - before.x) <= 2 && Math.abs(after.y - before.y) <= 2,
      `${what} keeps the opposite ink corner within 2 native px, got (${after.x}, ${after.y}) vs (${before.x}, ${before.y})`,
    );
  };

  let scale = 96 / 220;
  for (const [index, corner] of corners.entries()) {
    // Interior spawn keeps every corner handle clear of the clipped canvas
    // edge through the full ±48px drag range below.
    const id = await addDirectLabel(page, `Corner${corner.dir}`, "Literata", true, { x: 160, y: 200 });
    await selectLabel(page, id);

    // The default scene renders at a non-unit scale; pin it from the DOM so
    // the resize math below is exercised at 96/220 rather than 1.
    if (index === 0) {
      scale = await domCssScale(page, id);
      assert.ok(Math.abs(scale - 96 / 220) < 1e-6, `cssScale is 96/220, got ${scale}`);
    }

    // Corner handles resolve through real hit testing: the label spawns
    // interior so deliberate aperture clipping (labels and handles clip at
    // the device canvas edge) never covers the exercised handle. Boundary
    // clipping itself stays covered by the edge-spawn tests.
    const grid = await handleHitGrid(page, corner.dir);
    assert.ok(grid.center, `${corner.dir} handle center resolves to the handle`);
    assert.equal(grid.hits, 9, `${corner.dir} handle is fully hittable, got ${grid.hits}/9`);

    await settledFrameRect(page, id);
    const sizeBefore = Number(await typographyValue(page, "size"));
    const widthBefore = Number.parseFloat(await wrapWidthCss(page, id));
    const xBefore = Number(await inspectorValue(page, "x"));
    const yBefore = Number(await inspectorValue(page, "y"));
    const anchorBefore = await anchorNative(page, id, scale, xBefore, yBefore, corner.fixed);
    // The revision baseline predates the gesture: the corrected save lands
    // within tens of milliseconds of the release.
    const revisionBefore = await workspaceRevision(page);

    await dragHandle(page, corner.dir, corner.dx, corner.dy);
    await page.waitForFunction(
      (expected) =>
        Number((document.querySelector("[data-scene-typography-size]") as HTMLInputElement | null)?.value ?? "16") !==
        expected,
      sizeBefore,
      { timeout: 20000 },
    );
    // The save lands on the repaint; the revision advance proves the commit
    // fired before the reads below.
    await waitForRevision(page, revisionBefore);
    const sizeAfter = Number(await typographyValue(page, "size"));
    const widthAfter = Number.parseFloat(await wrapWidthCss(page, id));
    const xAfter = Number(await inspectorValue(page, "x"));
    const yAfter = Number(await inspectorValue(page, "y"));
    await settledFrameRect(page, id);
    const anchorAfter = await anchorNative(page, id, scale, xAfter, yAfter, corner.fixed);

    assert.ok(sizeAfter > sizeBefore, `${corner.dir} drag grows the renderer font size`);
    assert.ok(widthAfter > widthBefore, `${corner.dir} drag grows the saved wrap width`);
    if (corner.dir.includes("w")) assert.ok(xAfter < xBefore, `${corner.dir} drag moves x left`);
    if (corner.dir.includes("n")) assert.ok(yAfter < yBefore, `${corner.dir} drag moves y up`);
    // No origin assertion on the fixed axis: the correction legitimately
    // shifts the placement origin by the ink-bearing delta while the
    // opposite rendered ink corner stays fixed. The anchor below is the
    // product invariant, not the origin.
    assertAnchored(anchorBefore, anchorAfter, `${corner.dir} drag`);

    // Reload persists the resized size, width and position, and the anchor.
    // Selection goes through the layers panel: large outward drags can
    // leave the label hanging off-paper, where its frame is not clickable.
    await page.reload({ waitUntil: "domcontentloaded" });
    await screenReady(page);
    await page.locator("[data-screen-workspace]").waitFor();
    await waitPainted(page, id);
    await page.locator(`[data-scene-layer-handle="${id}"]`).click();
    await page.locator(`[data-scene-inspector="${id}"]`).waitFor();
    assert.equal(await typographyValue(page, "size"), String(sizeAfter));
    assert.equal(Number.parseFloat(await wrapWidthCss(page, id)), widthAfter);
    assert.equal(await inspectorValue(page, "x"), String(xAfter));
    assert.equal(await inspectorValue(page, "y"), String(yAfter));
    await settledFrameRect(page, id);
    assertAnchored(
      anchorAfter,
      await anchorNative(page, id, scale, xAfter, yAfter, corner.fixed),
      `${corner.dir} reload`,
    );

    await deleteLabel(page, id);
  }
  assert.deepEqual(errors, []);
});

// Pointer motion along a single axis resizes: a pure-vertical drag on a
// corner handle grows the renderer font size instead of snapping back.
test("paint failures expose the full error and keep label creation usable", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  t.after(() => page.close());
  const message =
    "Renderer could not load the selected font: this complete diagnostic must remain readable beyond the label's narrow ink frame.";
  await page.addInitScript((failure) => {
    const post = Worker.prototype.postMessage;
    Worker.prototype.postMessage = function (message, options): void {
      if (message?.kind === "render" && message.spec.text === "Failure") {
        queueMicrotask(() =>
          this.dispatchEvent(
            new MessageEvent("message", {
              data: { seq: message.seq, ok: false, error: failure },
            }),
          ),
        );
      } else Reflect.apply(post, this, [message, options]);
    };
  }, message);
  await bootLibrary(page, url);
  await openScreen(page, url);
  await page.locator("[data-screen-workspace]").waitFor();
  const id = await addDirectLabel(page, "Failure", "Literata", false);
  const badge = page.locator(`[data-scene-label-unavailable="${id}"]`);
  await page.waitForFunction(
    ({ placementId, failure }) =>
      document.querySelector(`[data-scene-label-unavailable="${placementId}"]`)?.textContent ===
      `Preview failed; text kept: ${failure}`,
    { placementId: id, failure: message },
  );
  assert.equal(await badge.textContent(), `Preview failed; text kept: ${message}`);
  await badge.hover();
  await page.getByRole("tooltip").waitFor();
  assert.equal(await page.getByRole("tooltip").textContent(), `Preview failed; text kept: ${message}`);
  await page.keyboard.press("Escape");
  await badge.focus();
  await page.getByRole("tooltip").waitFor();
  assert.equal(await page.getByRole("tooltip").textContent(), `Preview failed; text kept: ${message}`);

  assert.equal(await page.locator('[data-screen-tool="text"]').isEnabled(), true);
  const second = await addDirectLabel(page, "Still works", "Literata");
  assert.notEqual(second, id);
  assert.deepEqual(new Set(await containerIds(page)), new Set([id, second]));
  await page.reload({ waitUntil: "domcontentloaded" });
  await screenReady(page);
  await page.locator("[data-screen-workspace]").waitFor();
  await page.locator(`[data-scene-label-unavailable="${id}"]`).waitFor();
  assert.deepEqual(new Set(await containerIds(page)), new Set([id, second]));
});

test("vertical-only drags resize through the renderer", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);
  await openScreen(page, url);
  await page.locator("[data-screen-workspace]").waitFor({ timeout: 20000 });

  const id = await addDirectLabel(page, "Vertical", "Literata");
  await selectLabel(page, id);
  const sizeBefore = Number(await typographyValue(page, "size"));
  const widthBefore = Number.parseFloat(await wrapWidthCss(page, id));
  // The baseline predates the gesture: the corrected save lands within tens
  // of milliseconds of the release, so a post-drag baseline would already
  // contain it.
  const revisionBeforeResize = await workspaceRevision(page);

  await dragHandle(page, "se", 0, 72);
  await page.waitForFunction(
    (expected) =>
      Number((document.querySelector("[data-scene-typography-size]") as HTMLInputElement | null)?.value ?? "16") !==
      expected,
    sizeBefore,
    { timeout: 20000 },
  );
  const sizeAfter = Number(await typographyValue(page, "size"));
  const widthAfter = Number.parseFloat(await wrapWidthCss(page, id));
  assert.ok(sizeAfter > sizeBefore, `vertical-only drag grows the font size, got ${sizeAfter}`);
  assert.ok(widthAfter >= widthBefore, "vertical-only drag never shrinks the saved width");
  await waitForRevision(page, revisionBeforeResize);

  await page.reload({ waitUntil: "domcontentloaded" });
  await screenReady(page);
  await page.locator("[data-screen-workspace]").waitFor();
  await waitPainted(page, id);
  await page.locator(`[data-scene-label-frame="${id}"]`).click();
  assert.equal(await typographyValue(page, "size"), String(sizeAfter));
  assert.equal(Number.parseFloat(await wrapWidthCss(page, id)), widthAfter);
  assert.deepEqual(errors, []);
});

// Shrinking clamps at the domain minimum instead of rejecting: an inward drag
// far past the label commits size/width >= 1 and keeps a painted label.
test("shrinking clamps at the minimum and stays painted", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);
  await openScreen(page, url);
  await page.locator("[data-screen-workspace]").waitFor({ timeout: 20000 });

  const id = await addDirectLabel(page, "Shrink", "Literata");
  await selectLabel(page, id);
  const sizeBefore = Number(await typographyValue(page, "size"));
  // The baseline predates the gesture (see the vertical test).
  const revisionBeforeResize = await workspaceRevision(page);

  await dragHandle(page, "se", -160, -160);
  await page.waitForFunction(
    (expected) =>
      Number((document.querySelector("[data-scene-typography-size]") as HTMLInputElement | null)?.value ?? "16") !==
      expected,
    sizeBefore,
    { timeout: 20000 },
  );
  const sizeAfter = Number(await typographyValue(page, "size"));
  const widthAfter = Number.parseFloat(await wrapWidthCss(page, id));
  assert.ok(sizeAfter < sizeBefore, `inward drag shrinks the font size, got ${sizeAfter}`);
  assert.ok(sizeAfter >= 1, "font size clamps at the domain minimum");
  assert.ok(widthAfter >= 1, "saved width clamps at the domain minimum");
  await waitPainted(page, id);
  await waitForRevision(page, revisionBeforeResize);

  await page.reload({ waitUntil: "domcontentloaded" });
  await screenReady(page);
  await page.locator("[data-screen-workspace]").waitFor();
  await waitPainted(page, id);
  await page.locator(`[data-scene-label-frame="${id}"]`).click();
  assert.equal(await typographyValue(page, "size"), String(sizeAfter));
  assert.equal(Number.parseFloat(await wrapWidthCss(page, id)), widthAfter);
  assert.deepEqual(errors, []);
});
