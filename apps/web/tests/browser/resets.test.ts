import assert from "node:assert/strict";
import test from "node:test";
import type { Locator, Page } from "playwright-core";
import {
  bootDetail, bootLibrary, browserAvailable, buildApp, canvasRendered, cardIds, cardNames,
  launch, openNewVariant, servePrefix, setRange,
} from "../helpers/spa-helpers.ts";

async function checkHover(page: Page, button: Locator): Promise<void> {
  await page.waitForFunction(() => {
    const status = document.querySelector("[data-save-status]");
    return !status || status.textContent === "Saved";
  });
  assert.equal(await button.isEnabled(), true);
  const background = await button.evaluate((element) => getComputedStyle(element).backgroundColor);
  await button.hover();
  await page.waitForFunction((element) => element?.getAnimations().length === 0, await button.elementHandle());
  assert.equal(await button.evaluate((element) => element.matches(":hover")), true);
  assert.notEqual(await button.evaluate((element) => getComputedStyle(element).backgroundColor), background);
  const contrast = await button.evaluate((element) => {
    const context = document.createElement("canvas").getContext("2d")!;
    const luminance = (color: string): number => {
      context.fillStyle = color;
      context.fillRect(0, 0, 1, 1);
      const linear = [...context.getImageData(0, 0, 1, 1).data].slice(0, 3).map((byte) => {
        const value = byte / 255;
        return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
      });
      return linear[0]! * 0.2126 + linear[1]! * 0.7152 + linear[2]! * 0.0722;
    };
    const style = getComputedStyle(element);
    const icon = luminance(style.color);
    const background = luminance(style.backgroundColor);
    return (Math.max(icon, background) + 0.05) / (Math.min(icon, background) + 0.05);
  });
  assert.ok(contrast >= 3, `hover icon contrast is ${contrast.toFixed(2)}:1`);
  await page.mouse.move(0, 0);
}

test("reset buttons mute at defaults and keep contrasting hover icons in both themes", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  for (const colorScheme of ["light", "dark"] as const) {
    await t.test(colorScheme, async () => {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, colorScheme });
      try {
        await bootLibrary(page, url);
        const names = await cardNames(page);
        const id = (await cardIds(page))[names.findIndex((name) => /^Roboto Flex/.test(name))]!;
        assert.ok(id);
        await openNewVariant(page, id);
        await page.waitForFunction(canvasRendered);
        const specimen = page.getByRole("button", { name: "Reset specimen", exact: true });
        const axis = page.locator('[data-axis-reset="wght"]');
        assert.equal(await specimen.isDisabled(), true);
        assert.equal(await axis.isDisabled(), true);
        assert.ok(await axis.evaluate((element) => Number(getComputedStyle(element).opacity) <= 0.3), "disabled resets are strongly muted");
        await setRange(page, '[data-axis="wght"]', "700");
        assert.equal(await specimen.isDisabled(), true, "variant specimen reset only restores inherited text");
        await checkHover(page, axis);
        await axis.click();
        assert.equal(await axis.isDisabled(), true);
        await page.locator("[data-text]").fill("Local specimen");
        await checkHover(page, specimen);
        await specimen.click();
        assert.equal(await specimen.isDisabled(), true);

        await bootDetail(page, `${url}#/font/${id}/`);
        assert.equal(await specimen.isDisabled(), true);
        await page.locator("[data-size-px]").fill("32");
        assert.equal(await specimen.isEnabled(), true, "unsaved reset also restores font settings");
        await checkHover(page, specimen);
        await specimen.click();
        assert.equal(await specimen.isDisabled(), true);

        await page.goto(`${url}#/palettes/`, { waitUntil: "networkidle" });
        await page.getByRole("button", { name: "Add preset", exact: true }).click();
        const levels = page.getByRole("button", { name: "Reset levels", exact: true });
        await levels.waitFor();
        assert.equal(await levels.isDisabled(), true);
        await page.getByRole("button", { name: "Select level 1", exact: true }).click();
        await page.getByRole("spinbutton", { name: "Gray value", exact: true }).fill("150");
        await page.waitForFunction(() => !document.querySelector<HTMLButtonElement>('[aria-label="Reset levels"]')?.disabled);
        await checkHover(page, levels);
        await levels.click();
        await page.waitForFunction(() => document.querySelector<HTMLButtonElement>('[aria-label="Reset levels"]')?.disabled);
      } finally {
        await page.close();
      }
    });
  }
});
