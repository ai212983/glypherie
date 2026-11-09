import assert from "node:assert/strict";
import test from "node:test";
import { addScreenText } from "../helpers/screen-tools.ts";
import { bootLibrary, browserAvailable, buildApp, launch, servePrefix } from "../helpers/spa-helpers.ts";

test("Size and Position follow held gestures without saving until release", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  t.after(() => page.close());
  await bootLibrary(page, url);
  await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
  const id = await addScreenText(page, "Live", { x: 150, y: 250 });
  await page.locator(`[data-scene-layer-handle="${id}"]`).click();
  const values = () =>
    page.evaluate(() => ({
      x: Number((document.querySelector("[data-scene-inspector-x]") as HTMLInputElement).value),
      y: Number((document.querySelector("[data-scene-inspector-y]") as HTMLInputElement).value),
      size: Number((document.querySelector("[data-scene-typography-size]") as HTMLInputElement).value),
    }));
  const revision = () => page.locator("[data-screen-workspace]").getAttribute("data-screen-revision");
  const before = await values();
  const firstRevision = await revision();
  const frame = await page.locator(`[data-scene-label-frame="${id}"]`).boundingBox();
  assert.ok(frame);
  const frameX = frame.x + frame.width / 2;
  const frameY = frame.y + frame.height / 2;
  await page.mouse.move(frameX, frameY);
  await page.mouse.down();
  await page.mouse.move(frameX + 24, frameY + 16, { steps: 6 });
  await page.waitForFunction(
    (initial) => {
      const x = Number((document.querySelector("[data-scene-inspector-x]") as HTMLInputElement).value);
      const y = Number((document.querySelector("[data-scene-inspector-y]") as HTMLInputElement).value);
      return x > initial.x && y > initial.y;
    },
    before,
    { timeout: 2000 },
  );
  const moved = await values();
  assert.equal(await revision(), firstRevision, "held dragging must not write to the scene");
  await page.mouse.up();
  await page.waitForFunction(
    (initial) => document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision") !== initial,
    firstRevision,
  );
  assert.deepEqual(await values(), moved, "the inspector must not fall back to the old position on release");

  const handle = page.locator('.moveable-control-box .moveable-control.moveable-direction[data-direction="nw"]');
  const corner = await handle.boundingBox();
  assert.ok(corner);
  const secondRevision = await revision();
  const cornerX = corner.x + corner.width / 2;
  const cornerY = corner.y + corner.height / 2;
  await page.mouse.move(cornerX, cornerY);
  await page.mouse.down();
  await page.mouse.move(cornerX - 24, cornerY - 16, { steps: 6 });
  await page.waitForFunction(
    (initial) => {
      const size = Number((document.querySelector("[data-scene-typography-size]") as HTMLInputElement).value);
      const x = Number((document.querySelector("[data-scene-inspector-x]") as HTMLInputElement).value);
      const y = Number((document.querySelector("[data-scene-inspector-y]") as HTMLInputElement).value);
      return size > initial.size && x < initial.x && y < initial.y;
    },
    moved,
    { timeout: 2000 },
  );
  const resized = await values();
  assert.equal(await revision(), secondRevision, "held resizing must not write to the scene");
  await page.mouse.up();
  await page.waitForFunction(
    (initial) => document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision") !== initial,
    secondRevision,
  );
  assert.equal((await values()).size, resized.size);

  // One undo per gesture: first resize, then drag.
  await page.locator("[data-screen-undo]").click();
  await page.locator("[data-scene-layer-handle]").click();
  assert.deepEqual(await values(), moved);
  await page.locator("[data-screen-undo]").click();
  await page.locator("[data-scene-layer-handle]").click();
  assert.deepEqual(await values(), before);
});

test(
  "held resizing keeps repainting when WASM is slower than pointer input",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    t.after(() => page.close());
    await page.addInitScript(() => {
      const probe = { enabled: false, paints: 0, requests: 0 };
      Object.assign(window, { resizePaintProbe: probe });
      const post = Worker.prototype.postMessage;
      Worker.prototype.postMessage = function (message, options): void {
        if (probe.enabled && message.kind === "render" && message.spec?.text === "shtht") {
          probe.requests += 1;
          // Delay delivery, preserving the real WASM renderer and its geometry.
          setTimeout(() => post.call(this, message, options as StructuredSerializeOptions), 120);
        } else post.call(this, message, options as StructuredSerializeOptions);
      };
      const draw = CanvasRenderingContext2D.prototype.drawImage;
      CanvasRenderingContext2D.prototype.drawImage = function (...args: unknown[]): void {
        if (probe.enabled && this.canvas.closest('[data-scene-label][aria-label="shtht"]')) probe.paints += 1;
        Reflect.apply(draw, this, args);
      };
    });
    await bootLibrary(page, url);
    await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
    const id = await addScreenText(page, "shtht", { x: 129, y: 241 });
    const size = page.locator("[data-scene-typography-size]");
    const beforeSize = await page.locator("[data-screen-workspace]").getAttribute("data-screen-revision");
    await size.fill("103");
    await size.press("Tab");
    await page.waitForFunction(
      (before) => document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision") !== before,
      beforeSize,
    );
    await page.waitForFunction((placementId) => {
      const canvas = document.querySelector(`[data-scene-label="${placementId}"] canvas`);
      return canvas instanceof HTMLCanvasElement && canvas.height > 100;
    }, id);
    await page.locator(`[data-scene-layer-handle="${id}"]`).click();
    const revision = await page.locator("[data-screen-workspace]").getAttribute("data-screen-revision");
    const handle = await page.locator(".moveable-control.moveable-se").boundingBox();
    assert.ok(handle);
    await page.evaluate(() => {
      (window as unknown as { resizePaintProbe: { enabled: boolean } }).resizePaintProbe.enabled = true;
    });
    await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2);
    await page.mouse.down();
    try {
      for (let step = 1; step <= 24; step++) {
        await page.mouse.move(handle.x + handle.width / 2 + step, handle.y + handle.height / 2 + step / 2);
        await page.waitForTimeout(35);
      }
      const probe = await page.evaluate(
        () => (window as unknown as { resizePaintProbe: { paints: number; requests: number } }).resizePaintProbe,
      );
      assert.ok(probe.paints >= 2, `canvas must repaint repeatedly before release: ${JSON.stringify(probe)}`);
      assert.ok(probe.requests < 18, `slow renders must coalesce intermediate sizes: ${JSON.stringify(probe)}`);
      assert.equal(await page.locator("[data-screen-workspace]").getAttribute("data-screen-revision"), revision);
    } finally {
      await page.mouse.up();
    }
  },
);
