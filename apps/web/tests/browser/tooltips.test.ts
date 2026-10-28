import assert from "node:assert/strict";
import test from "node:test";
import type { Locator } from "playwright-core";
import {
  bootLibrary, browserAvailable, buildApp, cardIds, launch, openNewVariant, servePrefix,
} from "../helpers/spa-helpers.ts";

test("obvious actions keep accessible names without tooltips; informative hints remain usable", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, colorScheme: "light" });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await bootLibrary(page, url);

  const accessibleAction = async (action: Locator, name: string | RegExp): Promise<void> => {
    const label = await action.getAttribute("aria-label") ?? "";
    if (typeof name === "string") assert.equal(label, name);
    else assert.match(label, name);
    if (await action.isEnabled()) {
      await action.focus();
      await action.hover();
    }
    assert.notEqual(await action.getAttribute("data-slot"), "tooltip-trigger");
    assert.equal(await action.getAttribute("aria-describedby"), null);
    assert.equal(await page.getByRole("tooltip").count(), 0);
  };

  const theme = page.locator("[data-theme-toggle]");
  await accessibleAction(theme, "Switch to dark mode");
  await theme.click();
  await accessibleAction(theme, "Switch to light mode");
  await accessibleAction(page.locator("[data-canvas-inverse]"), "Inverse canvas colors");
  const ids = await cardIds(page);
  await accessibleAction(page.locator(`[data-delete-font="${ids[0]}"]`), /^Delete font /);
  assert.equal(await page.locator("[title]").count(), 0);

  await openNewVariant(page, ids[0]!);
  await accessibleAction(page.locator("[data-reset]"), "Reset specimen");
  await accessibleAction(page.locator("[data-axis-reset]").first(), /^Reset .+ to default$/);
  const fitting = page.locator("#use-font-hints");
  await fitting.focus();
  await page.getByRole("tooltip", { name: "Uses font hints where available and automatically fits the remaining axes.", exact: true }).waitFor();
  await page.keyboard.press("Escape");
  await page.getByRole("tooltip").waitFor({ state: "hidden" });
  assert.equal(await fitting.evaluate((element) => element === document.activeElement), true, "Escape preserves trigger focus");

  await page.goto(`${url}#/palettes/`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Add preset", exact: true }).click();
  const removePreset = page.getByRole("button", { name: "Delete preset Grayscale 1", exact: true });
  await accessibleAction(removePreset, "Delete preset Grayscale 1");
  assert.equal(await page.locator("[title]").count(), 0);
  await page.setViewportSize({ width: 375, height: 812 });
  const swatch = page.getByRole("group", { name: "Bit-depth & gray levels", exact: true }).getByRole("button", { name: "Select level 1", exact: true });
  await accessibleAction(swatch, "Select level 1");
  await page.keyboard.press("Space");
  assert.equal(await swatch.getAttribute("aria-pressed"), "true", "swatch remains keyboard selectable without a tooltip");
  assert.deepEqual(errors, []);
});
