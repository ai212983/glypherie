import assert from "node:assert/strict";
import test from "node:test";
import { addScreenText } from "../helpers/screen-tools.ts";
import { bootLibrary, browserAvailable, buildApp, launch, servePrefix } from "../helpers/spa-helpers.ts";

test(
  "Screen panels keep stable rows, a docked toolbar and independent scroll positions",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    t.after(() => page.close());
    await bootLibrary(page, url);
    await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
    assert.equal(await page.locator("#main").evaluate((element) => getComputedStyle(element).padding), "0px");
    const deleteButton = page
      .getByRole("toolbar", { name: "Layer actions" })
      .getByRole("button", { name: "Delete selected label" });
    assert.equal(await deleteButton.isDisabled(), true);
    assert.equal(await deleteButton.innerText(), "", "the delete action is icon-only");
    const first = await addScreenText(page, "First");
    const second = await addScreenText(page, "Second", { x: 80, y: 60 });

    await t.test("selecting and deselecting rows preserves every row rectangle", async () => {
      const rectangles = () =>
        page.locator("[data-scene-layer]").evaluateAll((rows) =>
          rows.map((row) => {
            const box = row.getBoundingClientRect();
            return {
              id: row.getAttribute("data-scene-layer"),
              x: box.x,
              y: box.y,
              width: box.width,
              height: box.height,
            };
          }),
        );
      const before = await rectangles();
      await page.locator(`[data-scene-layer-handle="${first}"]`).click();
      assert.deepEqual(await rectangles(), before, "selection must not resize a row or move its neighbors");
      await page.locator(`[data-scene-layer-handle="${second}"]`).click();
      assert.deepEqual(await rectangles(), before);
      await page.locator("[data-scene-stage]").click({ position: { x: 4, y: 4 } });
      assert.deepEqual(await rectangles(), before, "deselection must preserve the same geometry");
    });

    const dock = async () =>
      page.evaluate(() => {
        const stage = document.querySelector("[data-screen-stage-scroll]")!;
        const panel = stage.closest("[data-panel]")!.getBoundingClientRect();
        const tools = document.querySelector("[data-screen-tools]")!.getBoundingClientRect();
        return {
          centerOffset: tools.left + tools.width / 2 - (panel.left + panel.width / 2),
          bottomInset: panel.bottom - tools.bottom,
          panelBottom: panel.bottom,
          footerTop: document.querySelector(".site-footer")!.getBoundingClientRect().top,
        };
      });
    const assertDock = async () => {
      const geometry = await dock();
      assert.ok(geometry.panelBottom <= geometry.footerTop + 1, "central panel must fit above the footer");
      assert.ok(Math.abs(geometry.centerOffset) <= 1, `toolbar must be centered: ${JSON.stringify(geometry)}`);
      assert.ok(
        Math.abs(geometry.bottomInset - 16) <= 1,
        `toolbar must keep its 16px bottom inset: ${JSON.stringify(geometry)}`,
      );
    };
    await t.test("the toolbar stays docked across panel and viewport resizing", async () => {
      await assertDock();
      await page.getByRole("separator", { name: "Resize layers panel" }).focus();
      await page.keyboard.press("ArrowRight");
      await assertDock();
      await page.setViewportSize({ width: 1440, height: 900 });
      await assertDock();
      await page.setViewportSize({ width: 375, height: 800 });
      await assertDock();
      await page.setViewportSize({ width: 1280, height: 800 });
    });

    await t.test("all panels scroll independently while the toolbar stays still", async () => {
      const viewports = page.locator("[data-screen-workspace] [data-slot=scroll-area-viewport]");
      assert.equal(await viewports.count(), 3, "left, center and right each need a React Scroll Area viewport");
      for (let index = 2; index < 16; index++) await addScreenText(page, `Layer ${index}`, { x: 8, y: 8 + index * 20 });
      const positions = () =>
        viewports.evaluateAll((elements) =>
          elements.map((element) => ({ top: element.scrollTop, left: element.scrollLeft })),
        );
      const before = await positions();
      const actionBounds = await page.locator("[data-scene-layer-actions]").boundingBox();
      const left = viewports.nth(0);
      await left.evaluate((element) => (element.scrollTop = element.scrollHeight));
      const afterLeft = await positions();
      assert.deepEqual(
        await page.locator("[data-scene-layer-actions]").boundingBox(),
        actionBounds,
        "layer actions must remain fixed while rows scroll",
      );
      assert.ok(afterLeft[0]!.top > before[0]!.top, "layers must actually overflow and scroll");
      assert.deepEqual(afterLeft.slice(1), before.slice(1), "scrolling layers must leave canvas and inspector still");
      const right = viewports.nth(2);
      await right.evaluate((element) => (element.scrollTop = element.scrollHeight));
      const afterRight = await positions();
      assert.ok(afterRight[2]!.top > afterLeft[2]!.top, "inspector must actually scroll");
      assert.deepEqual(afterRight.slice(0, 2), afterLeft.slice(0, 2));
      await page.locator("[data-screen-device]").click();
      await page.getByRole("option", { name: "Custom…", exact: true }).click();
      await page.locator("[data-screen-width]").fill("1200");
      await page.locator("[data-screen-height]").fill("1200");
      await page.locator("[data-screen-save-dimensions]").click();
      const stage = page.locator("[data-screen-stage-scroll]");
      await page.waitForFunction(() => {
        const element = document.querySelector("[data-screen-stage-scroll]")!;
        return element.scrollHeight > element.clientHeight && element.scrollWidth > element.clientWidth;
      });
      const outside = await positions();
      const geometry = await dock();
      await stage.evaluate((element) => {
        element.scrollTop = element.scrollHeight;
        element.scrollLeft = element.scrollWidth;
      });
      const afterCanvas = await positions();
      assert.ok(afterCanvas[1]!.top > 0 && afterCanvas[1]!.left > 0);
      assert.deepEqual(afterCanvas[0], outside[0]);
      assert.deepEqual(afterCanvas[2], outside[2]);
      const afterDock = await dock();
      assert.equal(afterDock.bottomInset, geometry.bottomInset);
      assert.equal(afterDock.centerOffset, geometry.centerOffset);
      await assertDock();
      assert.equal(
        await page.locator(".app-shell__page").evaluate((element) => element.scrollHeight > element.clientHeight),
        false,
        "the document must not become a fourth scroll surface",
      );
    });
    await t.test("the icon action deletes the selection and Undo restores it", async () => {
      const row = page.locator("[data-scene-layer]").first();
      const id = await row.getAttribute("data-scene-layer");
      assert.ok(id);
      await page.locator(`[data-scene-layer-handle="${id}"]`).click();
      const count = await page.locator("[data-scene-layer]").count();
      assert.equal(await deleteButton.isEnabled(), true);
      await deleteButton.click();
      await page.locator(`[data-scene-layer="${id}"]`).waitFor({ state: "detached" });
      await page.waitForFunction(
        (before) => document.querySelectorAll("[data-scene-layer]").length === before - 1,
        count,
      );
      assert.equal(await page.locator(`[data-scene-label-container="${id}"]`).count(), 0);
      assert.equal(await deleteButton.isDisabled(), true);
      await page.locator("[data-screen-undo]").click();
      await page.waitForFunction((before) => document.querySelectorAll("[data-scene-layer]").length === before, count);
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.locator("[data-scene-layer]").first().waitFor();
      assert.equal(await page.locator("[data-scene-layer]").count(), count);
      assert.equal(await deleteButton.isDisabled(), true);
    });
  },
);
