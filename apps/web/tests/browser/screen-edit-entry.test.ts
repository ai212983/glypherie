import assert from "node:assert/strict";
import test from "node:test";
import { addScreenText } from "../helpers/screen-tools.ts";
import { bootLibrary, browserAvailable, buildApp, launch, servePrefix } from "../helpers/spa-helpers.ts";

test(
  "double-click editing starts at the clicked renderer caret on either line",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 2 });
    t.after(() => page.close());
    await bootLibrary(page, url);
    await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
    const text = "Alpha beta\nGamma delta";
    const id = await addScreenText(page, text, { x: 80, y: 160 });
    const revision = await page.locator("[data-screen-workspace]").getAttribute("data-screen-revision");
    await page.locator("[data-scene-typography-size]").fill("48");
    await page.locator("[data-scene-typography-size]").press("Tab");
    await page.waitForFunction(
      (before) => document.querySelector("[data-screen-workspace]")?.getAttribute("data-screen-revision") !== before,
      revision,
    );
    await page.waitForFunction((placementId) => {
      const canvas = document.querySelector(`[data-scene-label="${placementId}"] canvas`);
      return canvas instanceof HTMLCanvasElement && canvas.height > 80;
    }, id);
    const frame = page.locator(`[data-scene-label-frame="${id}"]`);
    const editor = page.locator(`[data-scene-edit-text="${id}"]`);
    const selection = () =>
      editor.evaluate((el) => {
        const textarea = el as HTMLTextAreaElement;
        return { start: textarea.selectionStart, end: textarea.selectionEnd };
      });
    // Derive each target from the real renderer overlay, using keyboard input
    // to place a known caret, then re-enter via a double-click at that point.
    for (const expected of [2, 6, 14]) {
      await frame.press("Enter");
      await editor.waitFor();
      for (let i = 0; i < text.length; i++) await editor.press("ArrowLeft");
      for (let i = 0; i < expected; i++) await editor.press("ArrowRight");
      assert.deepEqual(await selection(), { start: expected, end: expected });
      const caret = await page.locator(`[data-scene-edit-caret="${id}"]`).boundingBox();
      assert.ok(caret);
      const point = { x: caret.x + caret.width / 2, y: caret.y + caret.height / 2 };
      await editor.press("Escape");
      await editor.waitFor({ state: "detached" });
      await page.mouse.dblclick(point.x, point.y);
      await editor.waitFor();
      assert.deepEqual(
        await selection(),
        { start: expected, end: expected },
        "double-click must retain its hit location",
      );
      assert.equal(
        await page
          .locator(`[data-scene-edit-caret="${id}"]`)
          .evaluate((element) => getComputedStyle(element).backgroundColor),
        "rgb(0, 0, 0)",
        "the text caret stays black in either theme",
      );
      await page.keyboard.type("!");
      assert.equal(await editor.inputValue(), text.slice(0, expected) + "!" + text.slice(expected));
      await editor.press("Escape");
      await editor.waitFor({ state: "detached" });
      if (expected === 2) await page.getByRole("button", { name: /Switch to (light|dark) mode/ }).click();
    }
    // Pointer entry must not affect the established keyboard entry behavior.
    await frame.press("Enter");
    await editor.waitFor();
    assert.deepEqual(await selection(), { start: text.length, end: text.length });
  },
);
