import assert from "node:assert/strict";
import test from "node:test";
import { addScreenText } from "../helpers/screen-tools.ts";
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

test(
  "Figma layers keep native metadata, assets, resizing and persistent visibility",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    t.after(() => page.close());
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await bootLibrary(page, url);
    const names = await cardNames(page);
    const ids = await cardIds(page);
    const index = names.findIndex((name) => /^Roboto Flex/.test(name));
    assert.ok(index >= 0);
    await openNewVariant(page, ids[index]!);
    await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
    const variant = await addScreenText(page, "Variant", { x: 16, y: 14 });
    const direct = await addScreenText(page, "Direct", { x: 16, y: 52, fontName: "Literata" });
    await page.getByRole("button", { name: "Switch to dark mode" }).click();
    await page.waitForFunction(() =>
      [...document.querySelectorAll("[data-scene-layer-meta]")].every((element) =>
        /\d+×\d+$/.test(element.textContent ?? ""),
      ),
    );
    const row = page.locator(`[data-scene-layer="${direct}"]`);
    assert.match(await row.locator("[data-scene-layer-meta]").innerText(), /^16,52 • \d+×\d+$/);
    const styles = await row.evaluate((element) => {
      const rowStyle = getComputedStyle(element);
      const label = getComputedStyle(element.querySelector("[data-scene-layer-text]")!);
      const metadata = getComputedStyle(element.querySelector("[data-scene-layer-meta]")!);
      const images = [...element.querySelectorAll("img")].map((image) => ({
        complete: image.complete,
        source: image.getAttribute("src"),
        width: image.getBoundingClientRect().width,
        height: image.getBoundingClientRect().height,
      }));
      return {
        background: rowStyle.backgroundColor,
        border: rowStyle.borderTopColor,
        radius: rowStyle.borderRadius,
        padding: rowStyle.padding,
        fontSize: label.fontSize,
        lineHeight: label.lineHeight,
        color: label.color,
        metaFont: metadata.fontSize,
        metaColor: metadata.color,
        images,
      };
    });
    assert.equal(styles.background, "rgb(30, 32, 36)");
    assert.equal(styles.radius, "4px");
    assert.equal(styles.padding, "7px");
    assert.equal(styles.fontSize, "11px");
    assert.equal(styles.lineHeight, "16px");
    assert.equal(styles.color, "rgb(255, 255, 255)");
    assert.equal(styles.metaFont, "9px");
    assert.equal(styles.metaColor, "rgb(73, 71, 63)");
    assert.equal(styles.images.length, 2);
    assert.ok(styles.images.every((image) => image.complete && image.source?.startsWith("/preview/assets/")));
    assert.ok(Math.abs(styles.images[0]!.width - 9.37083) < 0.05);
    assert.ok(Math.abs(styles.images[0]!.height - 6.09375) < 0.05);
    assert.equal(styles.images[1]!.width, 11);
    assert.equal(styles.images[1]!.height, 7.5);
    const separator = page.getByRole("separator", { name: "Resize layers panel" });
    const geometry = await separator.evaluate((element) => ({
      width: element.getBoundingClientRect().width,
      color: getComputedStyle(element).backgroundColor,
      grip: element.querySelector(".scene-pane-splitter-grip")?.getBoundingClientRect().toJSON(),
    }));
    assert.equal(geometry.width, 6);
    assert.equal(geometry.color, "rgb(30, 32, 36)");
    assert.equal(geometry.grip?.width, 2);
    assert.equal(geometry.grip?.height, 24);
    const widthBefore = await page
      .locator("[data-scene-layers]")
      .evaluate((element) => element.getBoundingClientRect().width);
    await separator.focus();
    await page.keyboard.press("ArrowRight");
    await page.waitForFunction(
      (before) => document.querySelector("[data-scene-layers]")!.getBoundingClientRect().width > before,
      widthBefore,
    );

    const visibility = (id: string) => page.locator(`[data-scene-layer-visibility="${id}"]`);
    const frame = (id: string) => page.locator(`[data-scene-label-container="${id}"]`);
    assert.match(await page.locator("[data-scene-export]").innerText(), /Exports all 2 text styles/);
    await visibility(variant).click();
    await frame(variant).waitFor({ state: "detached" });
    assert.equal(await visibility(variant).getAttribute("aria-pressed"), "false");
    assert.match(await page.locator("[data-scene-export]").innerText(), /Exports all 1 text styles/);
    await visibility(direct).click();
    await frame(direct).waitFor({ state: "detached" });
    assert.equal(await page.locator("[data-scene-export-zip]").isDisabled(), true);
    await page.locator("[data-screen-undo]").click();
    await frame(direct).waitFor();
    assert.equal(await visibility(direct).getAttribute("aria-pressed"), "true");
    await page.locator("[data-screen-redo]").click();
    await frame(direct).waitFor({ state: "detached" });
    await page.reload({ waitUntil: "domcontentloaded" });
    await visibility(direct).waitFor();
    assert.equal(await visibility(direct).getAttribute("aria-pressed"), "false");
    assert.equal(await visibility(variant).getAttribute("aria-pressed"), "false");
    assert.equal(await page.locator("[data-scene-label-container]").count(), 0);
    await visibility(variant).click();
    await frame(variant).waitFor();
    await page.locator(`[data-scene-layer-handle="${variant}"]`).dblclick();
    await page.locator(`[data-scene-layer-edit="${variant}"]`).fill("Renamed");
    await page.keyboard.press("ControlOrMeta+Enter");
    await page.waitForFunction(
      (id) => document.querySelector(`[data-scene-layer-text="${id}"]`)?.textContent === "Renamed",
      variant,
    );
    assert.deepEqual(errors, []);
  },
);
