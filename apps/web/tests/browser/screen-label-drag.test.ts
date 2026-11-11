import assert from "node:assert/strict";
import test from "node:test";
import { addScreenText } from "../helpers/screen-tools.ts";
import { bootLibrary, browserAvailable, buildApp, launch, servePrefix } from "../helpers/spa-helpers.ts";

test(
  "labels and handles stay clipped to the device canvas without adding scroll overflow",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    t.after(() => page.close());
    await bootLibrary(page, url);
    await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
    const id = await addScreenText(page, "Canvas clipping", { x: 60, y: 160 });
    const dimensions = () =>
      page.evaluate(() => {
        const shell = document.querySelector("[data-device-preview]") as HTMLElement;
        const viewport = document.querySelector("[data-screen-stage-scroll]") as HTMLElement;
        return [shell, viewport].map((el) => [
          el.clientWidth,
          el.clientHeight,
          el.scrollWidth,
          el.scrollHeight,
          el.scrollLeft,
          el.scrollTop,
        ]);
      });
    const before = await dimensions();
    for (const [x, y] of [
      [479, 799],
      [-40, -20],
    ] as const) {
      for (const [axis, value] of [
        ["x", x],
        ["y", y],
      ] as const) {
        const input = page.locator(`[data-scene-inspector-${axis}]`);
        await input.fill(String(value));
        await input.press("Tab");
        await page.waitForFunction(
          (expected) => {
            const container = document.querySelector(`[data-scene-label-container="${expected.id}"]`) as HTMLElement;
            const stage = document.querySelector("[data-scene-stage]") as HTMLElement;
            const scale = stage.getBoundingClientRect().width / 480;
            return (
              Math.abs(parseFloat(container.style[expected.axis === "x" ? "left" : "top"]) - expected.value * scale) <
              0.1
            );
          },
          { id, axis, value },
        );
      }
      await page.locator(".moveable-control-box").waitFor();
      const escaped = await page.evaluate(() => {
        const stage = document.querySelector("[data-scene-stage]")!.getBoundingClientRect();
        const controls = [
          ...document.querySelectorAll(
            ".moveable-control, .moveable-line, [data-scene-label-frame], [data-scene-label-container]",
          ),
        ];
        return controls.flatMap((control) => {
          const box = control.getBoundingClientRect();
          const centerX = box.left + box.width / 2;
          const centerY = box.top + box.height / 2;
          const outside =
            centerX < stage.left || centerX >= stage.right || centerY < stage.top || centerY >= stage.bottom;
          return outside && document.elementsFromPoint(centerX, centerY).includes(control)
            ? [{ x: centerX, y: centerY, className: control.className }]
            : [];
        });
      });
      assert.deepEqual(escaped, [], "selection handles and lines cannot be hit outside the device canvas");
      assert.deepEqual(await dimensions(), before, "off-canvas labels do not expand or scroll the shell or viewport");
      const offsets = await page.locator("[data-scene-stage]").evaluate((stage) => {
        stage.scrollLeft = 10000;
        stage.scrollTop = 10000;
        return [stage.scrollLeft, stage.scrollTop];
      });
      assert.deepEqual(offsets, [0, 0], "the canvas cannot scroll to reveal clipped labels");
    }
  },
);

test(
  "dragging a label selects and moves it in one gesture without changing size",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    t.after(() => page.close());
    await bootLibrary(page, url);
    await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
    const first = await addScreenText(page, "Small label", { x: 60, y: 160 });
    const second = await addScreenText(page, "Large label", { x: 100, y: 300 });
    const sizeInput = page.locator("[data-scene-typography-size]");
    const beforeSize = await page.locator("[data-screen-workspace]").getAttribute("data-screen-revision");
    await sizeInput.fill("99");
    await sizeInput.press("Tab");
    await page.waitForFunction(
      (before) => document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision") !== before,
      beforeSize,
    );
    await page.waitForFunction((id) => {
      const canvas = document.querySelector(`[data-scene-label="${id}"] canvas`);
      return canvas instanceof HTMLCanvasElement && canvas.height > 100;
    }, second);
    // Start with the other label selected. Repeat to exercise both first-drag
    // selection and a drag of an already selected, small label near its handles.
    for (const [id, initialX, initialY, size] of [
      [first, 60, 160, 16],
      [first, null, null, 16],
      [second, 100, 300, 99],
    ] as const) {
      const frame = page.locator(`[data-scene-label-frame="${id}"]`);
      const container = page.locator(`[data-scene-label-container="${id}"]`);
      const wrapWidth = await container.evaluate((element) => (element as HTMLElement).style.width);
      const box = await frame.boundingBox();
      assert.ok(box);
      const revision = await page.locator("[data-screen-workspace]").getAttribute("data-screen-revision");
      const x = initialX ?? Number(await page.locator("[data-scene-inspector-x]").inputValue());
      const y = initialY ?? Number(await page.locator("[data-scene-inspector-y]").inputValue());
      const start = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
      await page.mouse.move(start.x, start.y);
      await page.mouse.down();
      try {
        await page.mouse.move(start.x + 24, start.y + 12, { steps: 6 });
        await page.waitForFunction(
          (initial) => {
            const value = (selector: string) => Number((document.querySelector(selector) as HTMLInputElement)?.value);
            return (
              value("[data-scene-inspector-x]") > initial.x &&
              value("[data-scene-inspector-y]") > initial.y &&
              value("[data-scene-typography-size]") === initial.size
            );
          },
          { x, y, size },
          { timeout: 2000 },
        );
        assert.equal(await frame.getAttribute("aria-selected"), "true");
        assert.equal(await page.locator("[data-screen-workspace]").getAttribute("data-screen-revision"), revision);
      } finally {
        await page.mouse.up();
      }
      await page.waitForFunction(
        (before) => document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision") !== before,
        revision,
      );
      assert.equal(Number(await sizeInput.inputValue()), size, "moving does not change font size");
      assert.equal(await container.evaluate((element) => (element as HTMLElement).style.width), wrapWidth);
    }
    // Figma's selection border also moves the label; corner handles resize.
    for (const edge of [0, 1]) {
      const container = page.locator(`[data-scene-label-container="${second}"]`);
      const wrapWidth = await container.evaluate((element) => (element as HTMLElement).style.width);
      const x = Number(await page.locator("[data-scene-inspector-x]").inputValue());
      const y = Number(await page.locator("[data-scene-inspector-y]").inputValue());
      const revision = await page.locator("[data-screen-workspace]").getAttribute("data-screen-revision");
      const outline = await page.locator(`.moveable-line[data-line-key="render-line-${edge}"]`).boundingBox();
      assert.ok(outline);
      await page.mouse.move(outline.x + outline.width / 2, outline.y + outline.height / 2);
      await page.mouse.down();
      try {
        await page.mouse.move(outline.x + outline.width / 2 + 24, outline.y + outline.height / 2 + 12, { steps: 6 });
        await page.waitForFunction(
          (initial) => {
            const value = (selector: string) => Number((document.querySelector(selector) as HTMLInputElement)?.value);
            return value("[data-scene-inspector-x]") > initial.x && value("[data-scene-inspector-y]") > initial.y;
          },
          { x, y },
          { timeout: 2000 },
        );
        assert.equal(Number(await sizeInput.inputValue()), 99);
      } finally {
        await page.mouse.up();
      }
      await page.waitForFunction(
        (before) => document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision") !== before,
        revision,
      );
      assert.equal(await container.evaluate((element) => (element as HTMLElement).style.width), wrapWidth);
    }
  },
);
