// Screen labels against the real WASM preview renderer: placing, dragging
// and nudging labels on the native device grid, in-place editing with the
// transparent textarea and renderer caret geometry, undo/redo and reload
// persistence. Nothing here measures browser glyphs; every coordinate comes
// from the committed diagnostics.layout.editing stops.
import assert from "node:assert/strict";
import test from "node:test";
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

async function screenReady(page: Parameters<typeof hashPath>[0]): Promise<void> {
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

async function createComposition(page: Parameters<typeof cardNames>[0], name: string): Promise<void> {
  await page.locator("[data-screen-composition-create-name]").fill(name);
  await page.locator("[data-screen-composition-create]").waitFor();
  await page.waitForFunction(
    () => !((document.querySelector("[data-screen-composition-create]") as HTMLButtonElement | null)?.disabled ?? true),
  );
  await page.locator("[data-screen-composition-create]").click();
  await page.locator("[data-screen-workspace]").waitFor();
}

async function containerIds(page: Parameters<typeof cardNames>[0]): Promise<string[]> {
  return page.locator("[data-scene-label-container]").evaluateAll((elements) =>
    elements.map((element) => element.getAttribute("data-scene-label-container") ?? ""));
}

async function addLabel(page: Parameters<typeof cardNames>[0], text: string): Promise<string> {
  const known = await containerIds(page);
  await page.locator("[data-screen-new-text]").fill(text);
  await page.locator("[data-screen-new-style]").click();
  await page.getByRole("option").first().click();
  await page.locator("[data-screen-add-label]").click();
  await page.waitForFunction((knownIds) => [...document.querySelectorAll("[data-scene-label-container]")]
    .some((element) => {
      const id = element.getAttribute("data-scene-label-container");
      return id !== null && !knownIds.includes(id);
    }), known, { timeout: 20000 });
  const id = (await containerIds(page)).find((value) => value !== "" && !known.includes(value));
  assert.ok(id);
  await waitPainted(page, id);
  return id;
}

async function waitPainted(page: Parameters<typeof cardNames>[0], id: string): Promise<void> {
  await page.waitForFunction((placementId) => {
    const viewport = document.querySelector(`[data-scene-label="${placementId}"]`);
    const canvas = viewport?.querySelector("canvas");
    return canvas instanceof HTMLCanvasElement && canvas.dataset.rendered === "true";
  }, id, { timeout: 20000 });
}

async function labelInk(page: Parameters<typeof cardNames>[0], id: string): Promise<number> {
  return page.evaluate((placementId) => {
    const viewport = document.querySelector(`[data-scene-label="${placementId}"]`);
    const canvas = viewport?.querySelector("canvas");
    if (!(canvas instanceof HTMLCanvasElement)) throw new Error("Label canvas is missing.");
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas 2D context unavailable.");
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let ink = 0;
    for (let i = 3; i < data.length; i += 4) {
      if (data[i] !== 0) ink += 1;
    }
    return ink;
  }, id);
}

async function waitInkChanged(page: Parameters<typeof cardNames>[0], id: string, before: number): Promise<void> {
  await page.waitForFunction(
    ([placementId, ink]) => {
      const viewport = document.querySelector(`[data-scene-label="${placementId}"]`);
      const canvas = viewport?.querySelector("canvas");
      if (!(canvas instanceof HTMLCanvasElement) || canvas.dataset.rendered !== "true") return false;
      const context = canvas.getContext("2d");
      if (!context) return false;
      const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
      let count = 0;
      for (let i = 3; i < data.length; i += 4) {
        if (data[i] !== 0) count += 1;
      }
      return count !== ink;
    },
    [id, before] as const,
    { timeout: 20000 },
  );
}

async function inspectorX(page: Parameters<typeof cardNames>[0]): Promise<number> {
  return Number(await page.locator("[data-scene-inspector-x]").inputValue());
}

async function selectLabel(page: Parameters<typeof cardNames>[0], id: string): Promise<void> {
  // Tight ink frame, not the full-aperture container: containers are
  // click-through so stacked labels resolve by stacking order.
  await page.locator(`[data-scene-label-frame="${id}"]`).click();
  await page.locator(`[data-scene-inspector="${id}"]`).waitFor();
}

// Moveable's lines are the single visible selection outline and render from
// its live drag geometry, so their union bounds are the honest control
// position. Symmetric padding keeps the centers coincident with the frame.
async function dragControlBounds(page: Parameters<typeof cardNames>[0]): Promise<{ x: number; y: number; width: number; height: number }> {
  return page.locator(".moveable-control-box > .moveable-line").evaluateAll((lines) => {
    const boxes = lines.map((line) => line.getBoundingClientRect());
    const x = Math.min(...boxes.map((box) => box.left));
    const y = Math.min(...boxes.map((box) => box.top));
    return { x, y, width: Math.max(...boxes.map((box) => box.right)) - x, height: Math.max(...boxes.map((box) => box.bottom)) - y };
  });
}

async function controlCenter(page: Parameters<typeof cardNames>[0]): Promise<{ x: number; y: number }> {
  const control = await dragControlBounds(page);
  return { x: control.x + control.width / 2, y: control.y + control.height / 2 };
}

async function frameCenter(page: Parameters<typeof cardNames>[0], id: string): Promise<{ x: number; y: number }> {
  const box = await page.locator(`[data-scene-label-frame="${id}"]`).boundingBox();
  assert.ok(box);
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

async function assertAligned(page: Parameters<typeof cardNames>[0], id: string, message: string): Promise<void> {
  const label = await frameCenter(page, id);
  const control = await controlCenter(page);
  assert.ok(Math.abs(control.x - label.x) < 2, `${message}: label=${label.x}, control=${control.x}`);
  assert.ok(Math.abs(control.y - label.y) < 2, `${message}: label=${label.y}, control=${control.y}`);
}

async function settleFrames(page: Parameters<typeof cardNames>[0]): Promise<void> {
  await page.evaluate(() => new Promise<void>((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
  }));
}

test("labels drag on the device grid, nudge by keyboard and undo cleanly", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);
  await ensureStyle(page, url);
  await openScreen(page, url);
  await createComposition(page, "Drag");
  const id = await addLabel(page, "Hi");

  const before = await labelInk(page, id);
  assert.ok(before > 0, "the WASM bitmap carries ink");

  // Pointer drag moves the label; the committed position stays on the native
  // integer grid and the frame follows the pointer.
  await selectLabel(page, id);
  const startX = await inspectorX(page);
  const frame = page.locator(`[data-scene-label-frame="${id}"]`);
  const box = await frame.boundingBox();
  assert.ok(box);
  const frameBefore = await frame.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 60, box.y + box.height / 2, { steps: 8 });
  await assertAligned(page, id, "drag rectangles must share a center");
  await page.evaluate((placementId) => {
    const frame = document.querySelector(`[data-scene-label-frame="${placementId}"]`);
    if (!(frame instanceof HTMLElement) || !frame.parentElement) throw new Error("Missing drag target");
    const expected = frame.getBoundingClientRect().left;
    const positions: number[] = [];
    const sample = (): void => { positions.push(frame.getBoundingClientRect().left); };
    const observer = new MutationObserver(sample);
    observer.observe(frame.parentElement, { attributes: true, attributeFilter: ["style"] });
    let request = requestAnimationFrame(function record() {
      sample();
      request = requestAnimationFrame(record);
    });
    (window as unknown as { releaseProbe: () => { expected: number; positions: number[] } }).releaseProbe = () => {
      observer.disconnect();
      cancelAnimationFrame(request);
      sample();
      return { expected, positions };
    };
  }, id);
  await page.evaluate(() => {
    const selectors = ["[data-screen-device]", "[data-scene-inspector-edit]", "[data-scene-inspector-x]", "[data-screen-new-text]"];
    const disabled: string[] = [];
    const sample = (): void => {
      for (const selector of selectors) {
        if (document.querySelector(selector)?.matches(":disabled")) disabled.push(selector);
      }
    };
    const observer = new MutationObserver(sample);
    observer.observe(document.querySelector("[data-screen-workspace]")!, {
      subtree: true, attributes: true, attributeFilter: ["disabled", "aria-disabled"],
    });
    (window as unknown as { disabledProbe: () => string[] }).disabledProbe = () => {
      observer.disconnect();
      return disabled;
    };
  });
  await page.mouse.up();
  // A queued follow-up interaction while the drag save is still pending: the
  // frame stays usable and a keyboard nudge enqueues behind the drag commit,
  // accumulating through the same serialized queue.
  await frame.click();
  await page.keyboard.press("ArrowRight");
  await page.waitForFunction(
    (start) => Number((document.querySelector("[data-scene-inspector-x]") as HTMLInputElement | null)?.value ?? "x") !== start,
    startX,
    { timeout: 20000 },
  );
  const dragCommitted = await inspectorX(page);
  await page.waitForFunction(
    (x) => Number((document.querySelector("[data-scene-inspector-x]") as HTMLInputElement | null)?.value) === x,
    dragCommitted + 1,
    { timeout: 20000 },
  );
  const afterDrag = await inspectorX(page);
  const disabled = await page.evaluate(() =>
    (window as unknown as { disabledProbe: () => string[] }).disabledProbe());
  assert.deepEqual(disabled, [], "saving a released drag must not flash unrelated controls disabled");
  const release = await page.evaluate(() =>
    (window as unknown as { releaseProbe: () => { expected: number; positions: number[] } }).releaseProbe());
  assert.ok(release.positions.every((x) => Math.abs(x - release.expected) < 2),
    `label must stay at its released position while saving: expected=${release.expected}, observed=${JSON.stringify(release.positions)}`);
  assert.ok(Number.isInteger(afterDrag), `committed x stays integral, got ${afterDrag}`);
  assert.notEqual(afterDrag, startX);
  await settleFrames(page);
  const frameAfter = await frame.boundingBox();
  assert.ok(frameAfter && frameBefore);
  // Regression proof for the reported split outline: after release the
  // Moveable control box stayed ~one drag behind the committed label.
  await assertAligned(page, id, "released rectangles must share a center");
  assert.ok(Math.abs((frameAfter.x - frameBefore.x) - 60) < 4, "the frame tracks the pointer");

  // Exactly one visible selection outline: the label frame draws none of its
  // own, while Moveable renders its live geometry as lines.
  const frameOutline = await page.locator(`[data-scene-label-frame="${id}"]`).evaluate((frame) =>
    getComputedStyle(frame).outlineStyle);
  assert.equal(frameOutline, "none", "the label frame draws no duplicate outline");
  const visibleLines = await page.locator(".moveable-control-box > .moveable-line").evaluateAll((lines) =>
    lines.filter((line) => {
      const box = line.getBoundingClientRect();
      return box.width > 0 && box.height > 0;
    }).length);
  assert.ok(visibleLines > 0, "Moveable draws the single selection outline");

  // A second drag from the committed position stays aligned through release.
  const second = await frame.boundingBox();
  assert.ok(second);
  await page.mouse.move(second.x + second.width / 2, second.y + second.height / 2);
  await page.mouse.down();
  await page.mouse.move(second.x + second.width / 2 - 30, second.y + second.height / 2, { steps: 6 });
  await assertAligned(page, id, "second drag rectangles must share a center");
  await page.mouse.up();
  await page.waitForFunction(
    (x) => Number((document.querySelector("[data-scene-inspector-x]") as HTMLInputElement | null)?.value ?? "x") !== x,
    afterDrag,
    { timeout: 20000 },
  );
  const afterSecondDrag = await inspectorX(page);
  assert.ok(Number.isInteger(afterSecondDrag), `second commit stays integral, got ${afterSecondDrag}`);
  assert.notEqual(afterSecondDrag, afterDrag);
  const secondAfter = await frame.boundingBox();
  assert.ok(second && secondAfter);
  assert.ok(Math.abs((secondAfter.x - second.x) + 30) < 4, "the frame tracks the second pointer drag");
  await settleFrames(page);
  await assertAligned(page, id, "second release rectangles must share a center");

  // Keyboard nudging steps a single device pixel, Shift jumps ten.
  await frame.click();
  const focused = await page.evaluate(() => {
    const active = document.activeElement;
    return active instanceof HTMLElement ? (active.getAttribute("data-scene-label-frame") ?? active.tagName) : null;
  });
  assert.equal(focused, id, "clicking the frame focuses it for keyboard nudging");
  const afterSecond = afterSecondDrag;
  await page.keyboard.press("ArrowRight");
  await page.waitForFunction((x) => Number((document.querySelector("[data-scene-inspector-x]") as HTMLInputElement | null)?.value) === x, afterSecond + 1, { timeout: 20000 });
  await settleFrames(page);
  await assertAligned(page, id, "nudge rectangles must share a center");
  await page.keyboard.press("Shift+ArrowRight");
  await page.waitForFunction((x) => Number((document.querySelector("[data-scene-inspector-x]") as HTMLInputElement | null)?.value) === x, afterSecond + 11, { timeout: 20000 });
  await settleFrames(page);
  await assertAligned(page, id, "shift-nudge rectangles must share a center");

  // Undo walks the nudges back; redo replays one step forward.
  await page.locator("[data-screen-undo]").click();
  await page.locator("[data-scene-inspector]").waitFor({ state: "detached" });
  await selectLabel(page, id);
  await page.waitForFunction((x) => Number((document.querySelector("[data-scene-inspector-x]") as HTMLInputElement | null)?.value) === x, afterSecond + 1, { timeout: 20000 });
  await page.locator("[data-screen-undo]").click();
  await page.locator("[data-scene-inspector]").waitFor({ state: "detached" });
  await selectLabel(page, id);
  await page.waitForFunction((x) => Number((document.querySelector("[data-scene-inspector-x]") as HTMLInputElement | null)?.value) === x, afterSecond, { timeout: 20000 });
  await page.locator("[data-screen-redo]").click();
  await page.locator("[data-scene-inspector]").waitFor({ state: "detached" });
  await selectLabel(page, id);
  await page.waitForFunction((x) => Number((document.querySelector("[data-scene-inspector-x]") as HTMLInputElement | null)?.value) === x, afterSecond + 1, { timeout: 20000 });
  assert.equal(await inspectorX(page), afterSecond + 1);

  // Reload keeps the committed integer position and the typed text.
  await page.reload({ waitUntil: "domcontentloaded" });
  await screenReady(page);
  await page.locator("[data-screen-workspace]").waitFor();
  const containers = page.locator("[data-scene-label-container]");
  await containers.first().waitFor();
  const reloadedId = await containers.first().getAttribute("data-scene-label-container");
  assert.equal(reloadedId, id);
  await waitPainted(page, id);
  await page.locator(`[data-scene-label-frame="${id}"]`).click();
  assert.equal(await inspectorX(page), afterSecond + 1);
  assert.deepEqual(errors, []);
});

async function beginEdit(page: Parameters<typeof cardNames>[0], id: string): Promise<void> {
  await page.locator(`[data-scene-label-frame="${id}"]`).click();
  await page.locator(`[data-scene-inspector="${id}"]`).waitFor();
  await page.locator(`[data-scene-label-frame="${id}"]`).dblclick();
  await page.locator(`[data-scene-edit-text="${id}"]`).waitFor();
}

async function editSelection(page: Parameters<typeof cardNames>[0], id: string): Promise<{ start: number; end: number }> {
  return page.evaluate((placementId) => {
    const textarea = document.querySelector(`[data-scene-edit-text="${placementId}"]`);
    if (!(textarea instanceof HTMLTextAreaElement)) throw new Error("Edit textarea is missing.");
    return { start: textarea.selectionStart, end: textarea.selectionEnd };
  }, id);
}

async function editDirection(page: Parameters<typeof cardNames>[0], id: string): Promise<string | null> {
  return page.evaluate((placementId) => {
    const textarea = document.querySelector(`[data-scene-edit-text="${placementId}"]`);
    if (!(textarea instanceof HTMLTextAreaElement)) throw new Error("Edit textarea is missing.");
    return textarea.selectionDirection;
  }, id);
}

async function editValue(page: Parameters<typeof cardNames>[0], id: string): Promise<string> {
  return page.evaluate((placementId) => {
    const textarea = document.querySelector(`[data-scene-edit-text="${placementId}"]`);
    if (!(textarea instanceof HTMLTextAreaElement)) throw new Error("Edit textarea is missing.");
    return textarea.value;
  }, id);
}

test("in-place editing types against WASM carets, selects by pointer and commits explicitly", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);
  await ensureStyle(page, url);
  await openScreen(page, url);
  await createComposition(page, "Edit");
  const id = await addLabel(page, "Hi");

  // Double-click opens the transparent capture textarea over the WASM paint;
  // the visible caret comes from renderer stops, never browser metrics.
  await beginEdit(page, id);
  const textarea = page.locator(`[data-scene-edit-text="${id}"]`);
  assert.equal(await textarea.evaluate((element) => getComputedStyle(element).color), "rgba(0, 0, 0, 0)");
  assert.equal(await page.evaluate(() => (document.activeElement as HTMLElement | null)?.tagName), "TEXTAREA");
  await page.locator(`[data-scene-edit-caret="${id}"]`).waitFor();
  const caretBefore = await page.locator(`[data-scene-edit-caret="${id}"]`).boundingBox();
  assert.ok(caretBefore && caretBefore.width <= 3, "the overlay caret is a thin mark, not a native caret");

  // Typing repaints the committed bitmap through the real renderer.
  const inkBefore = await labelInk(page, id);
  await page.keyboard.type("!");
  await waitInkChanged(page, id, inkBefore);
  const inkAfter = await labelInk(page, id);
  assert.ok(inkAfter > inkBefore, "typing changes the committed ink");

  // Pointer clicks hit-test renderer caret stops: the far left lands at the
  // text start, the far right at its end.
  const container = page.locator(`[data-scene-label-container="${id}"]`);
  const box = await container.boundingBox();
  assert.ok(box);
  await page.mouse.click(box.x + 2, box.y + box.height / 2);
  assert.deepEqual(await editSelection(page, id), { start: 0, end: 0 });
  await page.mouse.click(box.x + box.width - 2, box.y + box.height / 2);
  assert.deepEqual(await editSelection(page, id), { start: 3, end: 3 });

  // Dragging across the label extends the native textarea selection, which
  // the overlay mirrors as renderer selection rects.
  await page.mouse.move(box.x + 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width - 2, box.y + box.height / 2, { steps: 6 });
  await page.mouse.up();
  assert.deepEqual(await editSelection(page, id), { start: 0, end: 3 });
  assert.ok(await page.locator(`[data-scene-edit-selection="${id}"]`).count() >= 1);

  // Escape discards the draft; the saved text never changed.
  await page.keyboard.press("Escape");
  await page.waitForFunction(
    (placementId) => document.querySelector(`[data-scene-edit-text="${placementId}"]`) === null,
    id,
  );
  await page.locator(`[data-scene-label-frame="${id}"]`).click();
  assert.equal(await page.locator("[data-scene-inspector-text]").textContent(), "Hi");

  // Ctrl+Enter commits through the revisioned store; reload keeps it.
  await beginEdit(page, id);
  await page.keyboard.type("?");
  await page.keyboard.press("ControlOrMeta+Enter");
  await page.waitForFunction(
    (placementId) => document.querySelector(`[data-scene-edit-text="${placementId}"]`) === null,
    id,
  );
  await page.locator(`[data-scene-inspector="${id}"]`).waitFor();
  assert.equal(await page.locator("[data-scene-inspector-text]").textContent(), "Hi?");
  await page.reload({ waitUntil: "domcontentloaded" });
  await screenReady(page);
  await page.locator("[data-screen-workspace]").waitFor();
  await waitPainted(page, id);
  await page.locator(`[data-scene-label-frame="${id}"]`).click();
  assert.equal(await page.locator("[data-scene-inspector-text]").textContent(), "Hi?");
  assert.deepEqual(errors, []);
});

test("visual-line keys, blank drafts and scaled dragging behave", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);
  await ensureStyle(page, url);
  await openScreen(page, url);
  await createComposition(page, "Lines");
  const id = await addLabel(page, "AB");

  // Multiline draft: ArrowUp crosses the explicit line break, Home lands on
  // the visual line start, all from WASM line geometry. The visual moves wait
  // for the draft's repaint so the geometry matches the typed text rather
  // than the previous paint.
  await beginEdit(page, id);
  const linesInkBefore = await labelInk(page, id);
  await page.keyboard.press("End");
  await page.keyboard.press("Enter");
  await page.waitForFunction((placementId) => {
    const caret = document.querySelector(`[data-scene-edit-caret="${placementId}"]`);
    return caret instanceof HTMLElement && Number.parseFloat(caret.style.top) > 0;
  }, id);
  await page.keyboard.type("CDE");
  await waitInkChanged(page, id, linesInkBefore);
  await page.keyboard.press("ArrowUp");
  assert.equal((await editSelection(page, id)).start, 2);
  await page.keyboard.press("Home");
  assert.deepEqual(await editSelection(page, id), { start: 0, end: 0 });
  await page.keyboard.press("ArrowDown");
  assert.equal((await editSelection(page, id)).start, 3);
  await page.keyboard.press("End");
  assert.deepEqual(await editSelection(page, id), { start: 6, end: 6 });
  await page.keyboard.press("ControlOrMeta+Enter");
  await page.waitForFunction(
    (placementId) => document.querySelector(`[data-scene-edit-text="${placementId}"]`) === null,
    id,
  );
  await page.locator(`[data-scene-inspector="${id}"]`).waitFor();
  assert.equal(await page.locator("[data-scene-inspector-text]").textContent(), "AB\nCDE");

  // A newline-only draft keeps renderer geometry: the caret stays visible
  // and typing recovers without an error badge.
  await beginEdit(page, id);
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.press("Enter");
  await page.locator(`[data-scene-edit-caret="${id}"]`).waitFor();
  assert.equal(await page.locator(`[data-scene-label-unavailable="${id}"]`).count(), 0);
  await page.keyboard.type("Z");
  await page.keyboard.press("ControlOrMeta+Enter");
  await page.waitForFunction(
    (placementId) => document.querySelector(`[data-scene-edit-text="${placementId}"]`) === null,
    id,
  );
  assert.equal(await page.locator("[data-scene-inspector-text]").textContent(), "\nZ");
  // The committed text change resized the tight frame; the control geometry
  // follows it.
  await settleFrames(page);
  await assertAligned(page, id, "resized rectangles must share a center");

  // Scaled dragging still commits integer device pixels.
  await page.locator("details[data-monitor-info] > summary").click();
  await page.locator('[data-screen-size] [role="slider"]').focus();
  await page.keyboard.press("End");
  await page.waitForFunction(
    () => document.querySelector("[data-screen-size-value]")?.textContent === "150%",
  );
  await page.locator(`[data-scene-label-frame="${id}"]`).click();
  // The preview scale change repositions every frame; the control follows.
  await settleFrames(page);
  await assertAligned(page, id, "scaled rectangles must share a center");
  const startX = await inspectorX(page);
  const frame = page.locator(`[data-scene-label-frame="${id}"]`);
  const box = await frame.boundingBox();
  assert.ok(box);
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 45, box.y + box.height / 2, { steps: 6 });
  await assertAligned(page, id, "scaled drag rectangles must share a center");
  await page.evaluate((placementId) => {
    const frame = document.querySelector(`[data-scene-label-frame="${placementId}"]`);
    if (!(frame instanceof HTMLElement) || !frame.parentElement) throw new Error("Missing drag target");
    const expected = frame.getBoundingClientRect().left;
    const positions: number[] = [];
    const sample = (): void => { positions.push(frame.getBoundingClientRect().left); };
    const observer = new MutationObserver(sample);
    observer.observe(frame.parentElement, { attributes: true, attributeFilter: ["style"] });
    let request = requestAnimationFrame(function record() {
      sample();
      request = requestAnimationFrame(record);
    });
    (window as unknown as { releaseProbe: () => { expected: number; positions: number[] } }).releaseProbe = () => {
      observer.disconnect();
      cancelAnimationFrame(request);
      sample();
      return { expected, positions };
    };
  }, id);
  await page.evaluate(() => {
    const selectors = ["[data-screen-device]", "[data-scene-inspector-edit]", "[data-scene-inspector-x]", "[data-screen-new-text]"];
    const disabled: string[] = [];
    const sample = (): void => {
      for (const selector of selectors) {
        if (document.querySelector(selector)?.matches(":disabled")) disabled.push(selector);
      }
    };
    const observer = new MutationObserver(sample);
    observer.observe(document.querySelector("[data-screen-workspace]")!, {
      subtree: true, attributes: true, attributeFilter: ["disabled", "aria-disabled"],
    });
    (window as unknown as { scaledDisabledProbe: () => string[] }).scaledDisabledProbe = () => {
      observer.disconnect();
      return disabled;
    };
  });
  await page.mouse.up();
  await page.waitForFunction(
    (start) => Number((document.querySelector("[data-scene-inspector-x]") as HTMLInputElement | null)?.value ?? "x") !== start,
    startX,
    { timeout: 20000 },
  );
  const scaledRelease = await page.evaluate(() =>
    (window as unknown as { releaseProbe: () => { expected: number; positions: number[] } }).releaseProbe());
  assert.ok(scaledRelease.positions.every((x) => Math.abs(x - scaledRelease.expected) < 2),
    `scaled label must stay at its released position while saving: expected=${scaledRelease.expected}, observed=${JSON.stringify(scaledRelease.positions)}`);
  const scaledDisabled = await page.evaluate(() =>
    (window as unknown as { scaledDisabledProbe: () => string[] }).scaledDisabledProbe());
  assert.deepEqual(scaledDisabled, [], "saving a scaled released drag must not flash unrelated controls disabled");
  const scaled = await inspectorX(page);
  assert.ok(Number.isInteger(scaled) && scaled !== startX);
  await settleFrames(page);
  await assertAligned(page, id, "scaled release rectangles must share a center");
  await page.reload({ waitUntil: "domcontentloaded" });
  await screenReady(page);
  await page.locator("[data-screen-workspace]").waitFor();
  await waitPainted(page, id);
  await page.locator(`[data-scene-label-frame="${id}"]`).click();
  assert.equal(await inspectorX(page), scaled);
  assert.equal(await page.locator("[data-scene-inspector-text]").textContent(), "\nZ");
  assert.deepEqual(errors, []);
});

test("native arrows, shift and select-all mirror into the overlay", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);
  await ensureStyle(page, url);
  await openScreen(page, url);
  await createComposition(page, "Keys");
  const id = await addLabel(page, "Hi");

  // Seeded collapsed at the text end.
  await beginEdit(page, id);
  assert.deepEqual(await editSelection(page, id), { start: 2, end: 2 });

  // Shift+Left extends natively; the overlay mirrors the range.
  await page.keyboard.press("Shift+ArrowLeft");
  assert.deepEqual(await editSelection(page, id), { start: 1, end: 2 });
  await page.locator(`[data-scene-edit-selection="${id}"]`).first().waitFor();

  // A plain arrow collapses to the focus end and shows the caret overlay.
  await page.keyboard.press("ArrowLeft");
  assert.deepEqual(await editSelection(page, id), { start: 1, end: 1 });
  await page.locator(`[data-scene-edit-caret="${id}"]`).waitFor();

  // Select-all is native; typing replaces the whole range.
  await page.keyboard.press("ControlOrMeta+a");
  assert.deepEqual(await editSelection(page, id), { start: 0, end: 2 });
  await page.keyboard.type("Yo");
  assert.equal(await editValue(page, id), "Yo");
  assert.deepEqual(await editSelection(page, id), { start: 2, end: 2 });

  // Escape discards; the saved text never changed.
  await page.keyboard.press("Escape");
  await page.waitForFunction(
    (placementId) => document.querySelector(`[data-scene-edit-text="${placementId}"]`) === null,
    id,
  );
  await page.locator(`[data-scene-label-frame="${id}"]`).click();
  assert.equal(await page.locator("[data-scene-inspector-text]").textContent(), "Hi");
  assert.deepEqual(errors, []);
});

test("right-to-left drags keep a backward range that typing replaces", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);
  await ensureStyle(page, url);
  await openScreen(page, url);
  await createComposition(page, "Backwards");
  const id = await addLabel(page, "Hi");

  await beginEdit(page, id);
  // The editing container spans the full aperture, so its edges hit-test
  // the text ends. Dragging end-to-start must keep one backward native
  // range rather than collapsing it.
  const container = page.locator(`[data-scene-label-container="${id}"]`);
  const box = await container.boundingBox();
  assert.ok(box);
  await page.mouse.move(box.x + box.width - 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + 2, box.y + box.height / 2, { steps: 6 });
  await page.mouse.up();
  assert.deepEqual(await editSelection(page, id), { start: 0, end: 2 });
  assert.equal(await editDirection(page, id), "backward");
  await page.locator(`[data-scene-edit-selection="${id}"]`).first().waitFor();

  // Typing replaces the ranged text; the overlay agrees with the native end.
  await page.keyboard.type("Yo");
  assert.equal(await editValue(page, id), "Yo");
  assert.deepEqual(await editSelection(page, id), { start: 2, end: 2 });
  await page.locator(`[data-scene-edit-caret="${id}"]`).waitFor();

  await page.keyboard.press("Escape");
  await page.waitForFunction(
    (placementId) => document.querySelector(`[data-scene-edit-text="${placementId}"]`) === null,
    id,
  );
  await page.locator(`[data-scene-label-frame="${id}"]`).click();
  assert.equal(await page.locator("[data-scene-inspector-text]").textContent(), "Hi");
  assert.deepEqual(errors, []);
});

test("deleting a line break re-resolves the caret on the merged line", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);
  await ensureStyle(page, url);
  await openScreen(page, url);
  await createComposition(page, "Merge");
  const id = await addLabel(page, "AB");

  // Commit two lines first so the re-edit starts on settled geometry.
  await beginEdit(page, id);
  await page.keyboard.press("End");
  await page.keyboard.press("Enter");
  await page.keyboard.type("CDE");
  await page.keyboard.press("ControlOrMeta+Enter");
  await page.waitForFunction(
    (placementId) => document.querySelector(`[data-scene-edit-text="${placementId}"]`) === null,
    id,
  );
  await page.locator(`[data-scene-inspector="${id}"]`).waitFor();
  assert.equal(await page.locator("[data-scene-inspector-text]").textContent(), "AB\nCDE");

  // Home lands on the second visual line start; Backspace merges the lines.
  await beginEdit(page, id);
  assert.deepEqual(await editSelection(page, id), { start: 6, end: 6 });
  await page.keyboard.press("Home");
  assert.deepEqual(await editSelection(page, id), { start: 3, end: 3 });
  await page.keyboard.press("Backspace");
  assert.deepEqual(await editSelection(page, id), { start: 2, end: 2 });
  // Merging lines keeps the ink count but changes the layout, so the proof
  // of the deletion's repaint is the re-resolved caret on the merged line.
  await page.locator(`[data-scene-edit-caret="${id}"]`).waitFor();
  await page.keyboard.press("Home");
  assert.deepEqual(await editSelection(page, id), { start: 0, end: 0 });
  await page.keyboard.press("End");
  assert.deepEqual(await editSelection(page, id), { start: 5, end: 5 });
  await page.keyboard.press("ControlOrMeta+Enter");
  await page.waitForFunction(
    (placementId) => document.querySelector(`[data-scene-edit-text="${placementId}"]`) === null,
    id,
  );
  await page.locator(`[data-scene-inspector="${id}"]`).waitFor();
  assert.equal(await page.locator("[data-scene-inspector-text]").textContent(), "ABCDE");
  assert.deepEqual(errors, []);
});

test("stacked labels select by ink and empty paper deselects", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);
  await ensureStyle(page, url);
  await openScreen(page, url);
  await createComposition(page, "Stack");
  const first = await addLabel(page, "Hi");
  const second = await addLabel(page, "Bye");

  // Move the second label right: its full-aperture container still covers
  // the first label's ink, but their ink no longer overlaps.
  const secondFrame = page.locator(`[data-scene-label-frame="${second}"]`);
  const movedBefore = await secondFrame.boundingBox();
  assert.ok(movedBefore);
  await page.locator("[data-scene-inspector-x]").fill("120");
  await page.locator("[data-scene-inspector-x]").press("Enter");
  await page.waitForFunction(
    ([placementId, beforeX]) => {
      const frame = document.querySelector(`[data-scene-label-frame="${placementId}"]`);
      if (!(frame instanceof HTMLElement)) return false;
      return Math.abs(frame.getBoundingClientRect().x - (beforeX as number)) > 5;
    },
    [second, movedBefore.x] as const,
    { timeout: 20000 },
  );

  // Empty paper clears the selection even with two labels on the screen.
  const stage = page.locator("[data-scene-stage]");
  await stage.scrollIntoViewIfNeeded();
  const stageBox = await stage.boundingBox();
  assert.ok(stageBox);
  await page.mouse.click(stageBox.x + stageBox.width - 8, stageBox.y + stageBox.height - 8);
  await page.waitForFunction(() => document.querySelector("[data-scene-inspector]") === null);

  // The first label's ink sits inside the second label's container box, yet
  // the tight frame selects the first label.
  await page.locator(`[data-scene-label-frame="${first}"]`).click();
  await page.locator(`[data-scene-inspector="${first}"]`).waitFor();

  // And the moved label still selects by its own ink.
  await page.locator(`[data-scene-label-frame="${second}"]`).click();
  await page.locator(`[data-scene-inspector="${second}"]`).waitFor();
  assert.deepEqual(errors, []);
});
