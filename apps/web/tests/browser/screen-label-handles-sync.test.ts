import { addScreenText } from "../helpers/screen-tools.ts";
// Focused regression: resized direct-font label border/handle sync across
// deselect -> LEFT layers panel reselect. Compares the actual rendered canvas
// ink with the tight DOM frame, and the tight frame with the Moveable
// handle-implied frame (4px intentional padding). Frame-vs-handles alone can
// pass while both stay stale relative to the label, so the ink comparison is
// the symptom check.
import assert from "node:assert/strict";
import test from "node:test";
import { bootLibrary, browserAvailable, buildApp, cardNames, launch, servePrefix } from "../helpers/spa-helpers.ts";

type ScreenPage = Parameters<typeof cardNames>[0];

async function screenReady(page: ScreenPage): Promise<void> {
  await page.waitForFunction(() => document.querySelector("[data-screen-page]") !== null);
}

async function openScreen(page: ScreenPage, url: string): Promise<void> {
  await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Screen" }).click();
  await screenReady(page);
}

async function containerIds(page: ScreenPage): Promise<string[]> {
  return page
    .locator("[data-scene-label-container]")
    .evaluateAll((elements) => elements.map((element) => element.getAttribute("data-scene-label-container") ?? ""));
}

async function waitPainted(page: ScreenPage, id: string): Promise<void> {
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

async function addDirectLabel(page: ScreenPage, text: string, fontName: string): Promise<string> {
  const known = await containerIds(page);
  await addScreenText(page, text, { fontName });
  await page.waitForFunction(
    (knownIds) =>
      [...document.querySelectorAll("[data-scene-label-container]")].some((element) => {
        const id = element.getAttribute("data-scene-label-container");
        return id !== null && !(knownIds as string[]).includes(id);
      }),
    known,
    { timeout: 20000 },
  );
  const id = (await containerIds(page)).find((value) => value !== "" && !known.includes(value));
  assert.ok(id);
  await waitPainted(page, id);
  return id;
}

// Rendered wrap width in CSS px: the label container's inline width reflects
// the saved native wrap width through the presentation scale. Selection
// stability assertions read this public geometry instead of a width input.
async function wrapWidthCss(page: ScreenPage, id: string): Promise<string> {
  return page.evaluate((placementId) => {
    const container = document.querySelector(`[data-scene-label-container="${placementId}"]`);
    if (!(container instanceof HTMLElement)) throw new Error("missing label container");
    return container.style.width;
  }, id);
}

async function settledFrameRect(page: ScreenPage, id: string) {
  await page.waitForFunction(
    (placementId) => {
      const frame = document.querySelector(`[data-scene-label-frame="${placementId}"]`);
      if (!(frame instanceof HTMLElement)) return false;
      const box = frame.getBoundingClientRect();
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
  return page.evaluate((placementId) => {
    const frame = document.querySelector(`[data-scene-label-frame="${placementId}"]`);
    if (!(frame instanceof HTMLElement)) throw new Error("missing label frame");
    const box = frame.getBoundingClientRect();
    return { x: box.x, y: box.y, width: box.width, height: box.height };
  }, id);
}

async function frameRect(page: ScreenPage, id: string) {
  return page.evaluate((placementId) => {
    const frame = document.querySelector(`[data-scene-label-frame="${placementId}"]`);
    if (!(frame instanceof HTMLElement)) throw new Error("missing label frame");
    const box = frame.getBoundingClientRect();
    return { x: box.x, y: box.y, width: box.width, height: box.height };
  }, id);
}

// Timeout capture: inline style (what React last wrote vs what the release
// cleared), bounding rect, rendered ink and handle-implied frame together, so
// a non-settling frame can be diagnosed instead of timing out silently.
async function frameTimeoutCapture(page: ScreenPage, id: string) {
  const dom = await page.evaluate((placementId) => {
    const frame = document.querySelector(`[data-scene-label-frame="${placementId}"]`);
    if (!(frame instanceof HTMLElement)) return null;
    const box = frame.getBoundingClientRect();
    return {
      inline: {
        width: frame.style.width,
        height: frame.style.height,
        left: frame.style.left,
        top: frame.style.top,
        transform: frame.style.transform,
      },
      rect: { x: box.x, y: box.y, width: box.width, height: box.height },
    };
  }, id);
  const ink = await inkAndFrame(page, id);
  let implied: Awaited<ReturnType<typeof handleImpliedFrame>> | null = null;
  let handleError: string | null = null;
  try {
    implied = await handleImpliedFrame(page);
  } catch (error) {
    handleError = error instanceof Error ? error.message : String(error);
  }
  return { dom, ink, implied, handleError };
}

async function workspaceRevision(page: ScreenPage): Promise<string> {
  return (await page.locator("[data-screen-workspace]").getAttribute("data-screen-revision")) ?? "";
}

async function waitForRevision(page: ScreenPage, before: string): Promise<void> {
  await page.waitForFunction(
    (expected) => document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision") !== expected,
    before,
    { timeout: 20000 },
  );
}

async function handleCenter(page: ScreenPage, dir: string) {
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

// Handle-implied frame from NW/SE corner handles, accounting the intentional
// 4px Moveable padding outward from the tight renderer frame.
async function handleImpliedFrame(page: ScreenPage) {
  const nw = await handleCenter(page, "nw");
  const se = await handleCenter(page, "se");
  const PAD = 4;
  return {
    x: nw.x + PAD,
    y: nw.y + PAD,
    width: se.x - nw.x - PAD * 2,
    height: se.y - nw.y - PAD * 2,
    nw,
    se,
  };
}

// Actual rendered ink bounding box in canvas backing pixels, plus the DOM
// boxes needed to project it into viewport CSS px. Alpha-only: the label
// palette keeps level 0 fully transparent, so non-transparent pixels are ink
// (same rule as the app's own measureInk).
async function inkAndFrame(page: ScreenPage, id: string) {
  return page.evaluate((placementId) => {
    const container = document.querySelector(`[data-scene-label-container="${placementId}"]`);
    const frame = document.querySelector(`[data-scene-label-frame="${placementId}"]`);
    const viewport = document.querySelector(`[data-scene-label="${placementId}"]`);
    const canvas = viewport?.querySelector("canvas");
    if (!(container instanceof HTMLElement)) throw new Error("missing label container");
    if (!(frame instanceof HTMLElement)) throw new Error("missing label frame");
    if (!(canvas instanceof HTMLCanvasElement)) throw new Error("missing label canvas");
    const containerBox = container.getBoundingClientRect();
    const frameBox = frame.getBoundingClientRect();
    const canvasBox = canvas.getBoundingClientRect();
    const context = canvas.getContext("2d", { alpha: true });
    if (!context) throw new Error("canvas 2d unavailable");
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let found = false;
    let bx0 = 0;
    let by0 = 0;
    let bx1 = 0;
    let by1 = 0;
    for (let by = 0; by < canvas.height; by += 1) {
      for (let bx = 0; bx < canvas.width; bx += 1) {
        if (data[(by * canvas.width + bx) * 4 + 3] === 0) continue;
        if (!found) {
          bx0 = bx1 = bx;
          by0 = by1 = by;
          found = true;
        } else {
          if (bx < bx0) bx0 = bx;
          if (bx > bx1) bx1 = bx;
          if (by > by1) by1 = by;
        }
      }
    }
    if (!found) {
      return {
        containerBox: { x: containerBox.x, y: containerBox.y, width: containerBox.width, height: containerBox.height },
        frameBox: { x: frameBox.x, y: frameBox.y, width: frameBox.width, height: frameBox.height },
        canvasBox: { x: canvasBox.x, y: canvasBox.y, width: canvasBox.width, height: canvasBox.height },
        canvasBacking: { width: canvas.width, height: canvas.height },
        inkBacking: null,
        inkCss: null,
      };
    }
    const scaleX = canvasBox.width / canvas.width;
    const scaleY = canvasBox.height / canvas.height;
    const inkCss = {
      x: canvasBox.x + bx0 * scaleX,
      y: canvasBox.y + by0 * scaleY,
      width: (bx1 - bx0 + 1) * scaleX,
      height: (by1 - by0 + 1) * scaleY,
    };
    return {
      containerBox: { x: containerBox.x, y: containerBox.y, width: containerBox.width, height: containerBox.height },
      frameBox: { x: frameBox.x, y: frameBox.y, width: frameBox.width, height: frameBox.height },
      canvasBox: { x: canvasBox.x, y: canvasBox.y, width: canvasBox.width, height: canvasBox.height },
      canvasBacking: { width: canvas.width, height: canvas.height },
      inkBacking: { x: bx0, y: by0, width: bx1 - bx0 + 1, height: by1 - by0 + 1 },
      inkCss,
    };
  }, id);
}

function mismatch(
  actual: { x: number; y: number; width: number; height: number },
  implied: { x: number; y: number; width: number; height: number },
) {
  return {
    dx: implied.x - actual.x,
    dy: implied.y - actual.y,
    dw: implied.width - actual.width,
    dh: implied.height - actual.height,
  };
}

test("resized label border/handles match after left-panel reselection", { skip: !browserAvailable }, async (t) => {
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

  const id = await addDirectLabel(page, "Handles", "Literata");
  await page.locator(`[data-scene-label-frame="${id}"]`).click();
  await page.locator(`[data-scene-inspector="${id}"]`).waitFor();
  await page.waitForFunction(
    () =>
      [...document.querySelectorAll(".moveable-control-box .moveable-control.moveable-direction")].some(
        (element) => element.getBoundingClientRect().width > 0,
      ),
    undefined,
    { timeout: 20000 },
  );

  const typography = async (name: string) =>
    page.locator(`[data-scene-typography] [data-scene-typography-${name}]`).inputValue();
  const sizeBeforeResize = await typography("size");
  const widthBeforeResize = await wrapWidthCss(page, id);

  // Grow through the SE corner handle.
  const revisionBefore = await workspaceRevision(page);
  const start = await page
    .locator(".moveable-control-box .moveable-control.moveable-direction")
    .evaluateAll((elements) => {
      const centers = elements.map((element) => {
        const box = element.getBoundingClientRect();
        return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
      });
      let best = centers[0]!;
      for (const center of centers) {
        if (center.x + center.y > best.x + best.y) best = center;
      }
      return best;
    });
  const inkBeforeDrag = await inkAndFrame(page, id);
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(start.x + 72, start.y + 48, { steps: 8 });
  // Hold the pointer down at the released position so the repaint of the
  // released size lands mid-gesture (the deferred save then commits from
  // the already-measured bounds). Wait on actual canvas ink so live inspector
  // updates alone cannot count as evidence of a renderer repaint.
  let repaintLandedHeld = false;
  const holdStart = Date.now();
  while (Date.now() - holdStart < 10000) {
    const ink = await inkAndFrame(page, id);
    if (
      inkBeforeDrag.inkBacking &&
      ink.inkBacking &&
      (ink.inkBacking.width !== inkBeforeDrag.inkBacking.width ||
        ink.inkBacking.height !== inkBeforeDrag.inkBacking.height)
    ) {
      repaintLandedHeld = true;
      break;
    }
    await page.waitForTimeout(200);
  }
  await page.mouse.up();
  await page.waitForFunction(
    (before) =>
      Number((document.querySelector("[data-scene-typography-size]") as HTMLInputElement | null)?.value ?? "16") !==
      Number(before),
    sizeBeforeResize,
    { timeout: 20000 },
  );
  await waitForRevision(page, revisionBefore);
  const rawFrameWhileSelected = await frameRect(page, id);
  const rawInkWhileSelected = await inkAndFrame(page, id);
  let rawImpliedWhileSelected: Awaited<ReturnType<typeof handleImpliedFrame>> | null = null;
  let rawHandleError: string | null = null;
  try {
    rawImpliedWhileSelected = await handleImpliedFrame(page);
  } catch (error) {
    rawHandleError = error instanceof Error ? error.message : String(error);
  }
  console.log(
    `HOLD_RELEASE_RAW ${JSON.stringify({ repaintLandedHeld, rawFrameWhileSelected, rawInkWhileSelected, rawImpliedWhileSelected, rawHandleError })}`,
  );
  let settledWhileSelected;
  try {
    settledWhileSelected = await settledFrameRect(page, id);
  } catch {
    const capture = await frameTimeoutCapture(page, id);
    console.log(`FRAME_TIMEOUT_CAPTURE ${JSON.stringify({ repaintLandedHeld, ...capture })}`);
    assert.fail(
      `tight frame never settles after hold-release (stale, not slow): ${JSON.stringify({ repaintLandedHeld, ...capture })}`,
    );
  }
  const impliedWhileSelected = await handleImpliedFrame(page);
  const errWhileSelected = mismatch(settledWhileSelected, impliedWhileSelected);
  const inkWhileSelected = await inkAndFrame(page, id);
  const errInkWhileSelected = inkWhileSelected.inkCss
    ? mismatch(inkWhileSelected.frameBox, inkWhileSelected.inkCss)
    : null;
  const sizeAfterResize = await typography("size");
  const widthAfterResize = await wrapWidthCss(page, id);

  // Switch selection elsewhere: deselect to empty paper at a point proven
  // empty via elementFromPoint, so Moveable fully unmounts (selectedId null).
  // Falls back to a second-label switch if no empty paper point resolves.
  let deselected = false;
  const emptyPoint = await page.evaluate(() => {
    const stage = document.querySelector("[data-scene-stage]");
    if (!(stage instanceof HTMLElement)) return null;
    const box = stage.getBoundingClientRect();
    const candidates = [
      { x: box.x + box.width - 6, y: box.y + box.height - 6 },
      { x: box.x + box.width - 6, y: box.y + 6 },
      { x: box.x + 6, y: box.y + box.height - 6 },
    ];
    for (const point of candidates) {
      const top = document.elementFromPoint(point.x, point.y);
      if (
        top &&
        (top === stage ||
          (top instanceof Element && stage.contains(top) && top.closest("[data-scene-label-frame]") === null))
      ) {
        return point;
      }
    }
    return null;
  });
  if (emptyPoint) {
    await page.mouse.click(emptyPoint.x, emptyPoint.y);
    try {
      await page.waitForFunction(() => document.querySelector(".moveable-control-box") === null, undefined, {
        timeout: 5000,
      });
      deselected = true;
    } catch {
      deselected = false;
    }
  }
  let otherId: string | null = null;
  if (!deselected) {
    otherId = await addDirectLabel(page, "Other", "Literata");
    await page.locator(`[data-scene-label-frame="${otherId}"]`).click();
    await page.locator(`[data-scene-inspector="${otherId}"]`).waitFor();
  }
  const sizeAfterDeselect = otherId ? await typography("size").catch(() => "switched") : "deselected";
  await page.locator(`[data-scene-layer-handle="${id}"]`).click();
  await page.locator(`[data-scene-inspector="${id}"]`).waitFor();
  await page.waitForFunction(
    () =>
      [...document.querySelectorAll(".moveable-control-box .moveable-control.moveable-direction")].some(
        (element) => element.getBoundingClientRect().width > 0,
      ),
    undefined,
    { timeout: 20000 },
  );
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
      }),
  );
  const settledAfterReselect = await settledFrameRect(page, id);
  const impliedAfterReselect = await handleImpliedFrame(page);
  const errAfterReselect = mismatch(settledAfterReselect, impliedAfterReselect);
  const inkAfterReselect = await inkAndFrame(page, id);
  const errInkAfterReselect = inkAfterReselect.inkCss
    ? mismatch(inkAfterReselect.frameBox, inkAfterReselect.inkCss)
    : null;
  const sizeAfterReselect = await page.locator(`[data-scene-typography] [data-scene-typography-size]`).inputValue();
  const widthAfterReselect = await wrapWidthCss(page, id);

  const report = {
    frameWhileSelected: settledWhileSelected,
    impliedWhileSelected,
    errWhileSelected,
    inkWhileSelected: {
      backing: inkWhileSelected.inkBacking,
      css: inkWhileSelected.inkCss,
      frame: inkWhileSelected.frameBox,
      err: errInkWhileSelected,
    },
    frameAfterReselect: settledAfterReselect,
    impliedAfterReselect,
    errAfterReselect,
    inkAfterReselect: {
      backing: inkAfterReselect.inkBacking,
      css: inkAfterReselect.inkCss,
      frame: inkAfterReselect.frameBox,
      err: errInkAfterReselect,
    },
    sizeBeforeResize,
    widthBeforeResize,
    repaintLandedHeld,
    sizeAfterResize,
    widthAfterResize,
    deselected,
    sizeAfterDeselect,
    sizeAfterReselect,
    widthAfterReselect,
  };
  await page.evaluate((payload: unknown) => {
    (window as unknown as { __handleSyncReport?: unknown }).__handleSyncReport = payload;
  }, report);
  console.log(`HANDLE_SYNC_REPORT ${JSON.stringify(report)}`);

  const TOL = 2.5;
  assert.ok(inkWhileSelected.inkCss, "resized label paints ink while selected");
  assert.ok(
    errInkWhileSelected &&
      Math.abs(errInkWhileSelected.dx) <= TOL &&
      Math.abs(errInkWhileSelected.dy) <= TOL &&
      Math.abs(errInkWhileSelected.dw) <= TOL &&
      Math.abs(errInkWhileSelected.dh) <= TOL,
    `tight frame matches rendered ink while selected: ${JSON.stringify({ frame: inkWhileSelected.frameBox, ink: inkWhileSelected.inkCss, err: errInkWhileSelected })}`,
  );
  assert.ok(
    Math.abs(errWhileSelected.dx) <= TOL &&
      Math.abs(errWhileSelected.dy) <= TOL &&
      Math.abs(errWhileSelected.dw) <= TOL &&
      Math.abs(errWhileSelected.dh) <= TOL,
    `handles match frame while selected after repaint: ${JSON.stringify({ frame: settledWhileSelected, implied: impliedWhileSelected, err: errWhileSelected })}`,
  );
  assert.equal(sizeAfterReselect, sizeAfterResize, "font size unchanged by selection");
  assert.equal(widthAfterReselect, widthAfterResize, "wrap width unchanged by selection");
  assert.ok(inkAfterReselect.inkCss, "resized label paints ink after LEFT panel reselection");
  assert.ok(
    errInkAfterReselect &&
      Math.abs(errInkAfterReselect.dx) <= TOL &&
      Math.abs(errInkAfterReselect.dy) <= TOL &&
      Math.abs(errInkAfterReselect.dw) <= TOL &&
      Math.abs(errInkAfterReselect.dh) <= TOL,
    `tight frame matches rendered ink after LEFT panel reselection: ${JSON.stringify({ frame: inkAfterReselect.frameBox, ink: inkAfterReselect.inkCss, err: errInkAfterReselect })}`,
  );
  assert.ok(
    Math.abs(errAfterReselect.dx) <= TOL &&
      Math.abs(errAfterReselect.dy) <= TOL &&
      Math.abs(errAfterReselect.dw) <= TOL &&
      Math.abs(errAfterReselect.dh) <= TOL,
    `handles match frame after LEFT panel reselection: ${JSON.stringify({ frame: settledAfterReselect, implied: impliedAfterReselect, err: errAfterReselect })}`,
  );
  assert.deepEqual(errors, []);
});

test("no-op handle click keeps border/handles on the rendered label", { skip: !browserAvailable }, async (t) => {
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

  const id = await addDirectLabel(page, "Noop", "Literata");
  await page.locator(`[data-scene-label-frame="${id}"]`).click();
  await page.locator(`[data-scene-inspector="${id}"]`).waitFor();
  await page.waitForFunction(
    () =>
      [...document.querySelectorAll(".moveable-control-box .moveable-control.moveable-direction")].some(
        (element) => element.getBoundingClientRect().width > 0,
      ),
    undefined,
    { timeout: 20000 },
  );
  const typography = async (name: string) =>
    page.locator(`[data-scene-typography] [data-scene-typography-${name}]`).inputValue();
  const sizeBefore = await typography("size");
  const inkBefore = await inkAndFrame(page, id);
  assert.ok(inkBefore.inkCss, "label paints ink before no-op click");

  // Press and release a corner handle without moving: the release takes
  // the no-gesture path, which must yield to the renderer-owned frame
  // rather than blanking it.
  const center = await handleCenter(page, "se");
  await page.mouse.move(center.x, center.y);
  await page.mouse.down();
  await page.mouse.up();
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
      }),
  );
  // The click landed on the handle, not empty paper: selection persists
  // with visible handles, so the assertions below exercise the release.
  assert.ok(
    (await page.locator(".moveable-control-box .moveable-control.moveable-direction").count()) > 0,
    "handles stay mounted after no-op handle click",
  );
  const settledAfter = await settledFrameRect(page, id);
  const impliedAfter = await handleImpliedFrame(page);
  const inkAfter = await inkAndFrame(page, id);
  console.log(`NOOP_CLICK_REPORT ${JSON.stringify({ settledAfter, impliedAfter, inkAfter })}`);

  const TOL = 2.5;
  assert.equal(await typography("size"), sizeBefore, "font size unchanged by no-op click");
  assert.ok(inkAfter.inkCss, "label paints ink after no-op click");
  const errInk = mismatch(inkAfter.frameBox, inkAfter.inkCss!);
  assert.ok(
    Math.abs(errInk.dx) <= TOL &&
      Math.abs(errInk.dy) <= TOL &&
      Math.abs(errInk.dw) <= TOL &&
      Math.abs(errInk.dh) <= TOL,
    `tight frame matches rendered ink after no-op click: ${JSON.stringify({ frame: inkAfter.frameBox, ink: inkAfter.inkCss, err: errInk })}`,
  );
  const errHandles = mismatch(settledAfter, impliedAfter);
  assert.ok(
    Math.abs(errHandles.dx) <= TOL &&
      Math.abs(errHandles.dy) <= TOL &&
      Math.abs(errHandles.dw) <= TOL &&
      Math.abs(errHandles.dh) <= TOL,
    `handles match frame after no-op click: ${JSON.stringify({ frame: settledAfter, implied: impliedAfter, err: errHandles })}`,
  );
  assert.deepEqual(errors, []);
});
