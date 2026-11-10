// Device-header zoom and body toggle: zoom presets scale the presentation
// only, off-100% zoom hides the shell and disables the body toggle, and the
// stored body preference survives temporary zoom changes. Zoom and body
// swaps keep the stage on the same ancestor path, so the canvas node and an
// open editing draft survive them.
import assert from "node:assert/strict";
import test from "node:test";
import type { Page } from "playwright-core";
import { addScreenText } from "../helpers/screen-tools.ts";
import { bootLibrary, browserAvailable, buildApp, launch, servePrefix, tooltipText } from "../helpers/spa-helpers.ts";

async function setZoom(page: Page, label: string): Promise<void> {
  await page.getByRole("combobox", { name: "Zoom" }).click();
  await page.getByRole("option", { name: label, exact: true }).click();
}

async function markStable(page: Page): Promise<void> {
  await page.locator("[data-scene-stage]").evaluate((el) => {
    (el as HTMLElement).dataset.stayMounted = "1";
  });
  await page.locator("[data-screen-aperture]").evaluate((el) => {
    (el as HTMLElement).dataset.stayMounted = "1";
  });
}

async function stableTree(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const stage = document.querySelector("[data-scene-stage]");
    const aperture = document.querySelector("[data-screen-aperture]");
    return (
      stage instanceof HTMLElement &&
      aperture instanceof HTMLElement &&
      stage.dataset.stayMounted === "1" &&
      aperture.dataset.stayMounted === "1"
    );
  });
}

test("device and ruler hints remain reachable by pointer and keyboard", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  t.after(() => page.close());
  await bootLibrary(page, url);
  await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
  await page.locator("[data-device-preview]").waitFor();
  page.setDefaultTimeout(3000);
  const header = page.locator("[data-screen-device-header]");
  const zoom = header.getByRole("combobox", { name: "Zoom" });

  async function keyboardHint(expected: string): Promise<void> {
    const describedBy = await page.waitForFunction(() => document.activeElement?.getAttribute("aria-describedby"));
    const hint = page.locator(`[role="tooltip"][id="${await describedBy.jsonValue()}"]`);
    await hint.waitFor({ state: "visible" });
    assert.equal(await hint.textContent(), expected);
    await page.keyboard.press("Escape");
    await hint.waitFor({ state: "hidden" });
  }

  await t.test("zoom hint is on the combobox trigger", async () => {
    assert.equal(await tooltipText(page, zoom), "Zoom the device canvas · currently 100%");
    await header.locator("[data-screen-rotate]").focus();
    await zoom.focus();
    await keyboardHint("Zoom the device canvas · currently 100%");
  });

  await t.test("disabled toggles explain their state without enabling the action", async () => {
    const grid = header.locator("[data-screen-grid-toggle]");
    const gridHelp = header.getByRole("group", { name: "Show grid", exact: true });
    assert.equal(await grid.isDisabled(), true);
    assert.equal(await tooltipText(page, gridHelp), "Grid needs zoom above 100% (currently 100%)");
    await header.locator("[data-screen-body-toggle]").focus();
    await page.keyboard.press("Tab");
    assert.equal(await gridHelp.evaluate((el) => document.activeElement === el), true);
    await keyboardHint("Grid needs zoom above 100% (currently 100%)");
    await gridHelp.click({ force: true });
    assert.equal(await page.locator("[data-scene-pixel-grid]").count(), 0);

    await setZoom(page, "200%");
    const body = header.locator("[data-screen-body-toggle]");
    const bodyHelp = header.getByRole("group", { name: "Show device body", exact: true });
    assert.equal(await body.isDisabled(), true);
    assert.equal(await tooltipText(page, bodyHelp), "Device body is hidden at 200% zoom");
    await zoom.focus();
    await page.keyboard.press("Tab");
    assert.equal(await bodyHelp.evaluate((el) => document.activeElement === el), true);
    await keyboardHint("Device body is hidden at 200% zoom");
    await bodyHelp.click({ force: true });
    assert.equal(await page.locator("[data-device-shell]").count(), 0);
  });

  await t.test("ruler origin help is outside the hidden decoration and keyboard reachable", async () => {
    const corner = page.getByRole("button", { name: "About pixel rulers" });
    await corner.waitFor();
    assert.equal(await corner.evaluate((el) => el.closest('[aria-hidden="true"]') === null), true);
    await header.locator("[data-screen-grid-toggle]").focus();
    await page.keyboard.press("Tab");
    assert.equal(await corner.evaluate((el) => document.activeElement === el), true);
    await keyboardHint("Pixel rulers: origin 0 is the canvas top-left, values are native device pixels.");
    assert.equal(
      await tooltipText(page, corner),
      "Pixel rulers: origin 0 is the canvas top-left, values are native device pixels.",
    );
  });
});

test(
  "device zoom hides the shell off-100% and preserves the body preference",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    t.after(() => page.close());
    await bootLibrary(page, url);
    await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
    const header = page.locator("[data-screen-center-panel] > [data-screen-device-header]");
    await header.waitFor();
    await page.locator("[data-device-preview]").waitFor();

    const zoom = header.getByRole("combobox", { name: "Zoom" });
    const bodyToggle = header.locator("[data-screen-body-toggle]");
    assert.equal(await zoom.innerText(), "100%");
    assert.equal(await bodyToggle.isEnabled(), true);
    assert.equal(await bodyToggle.getAttribute("aria-label"), "Hide device body");
    assert.equal(await page.locator('[data-device-body="shown"]').count(), 1);
    const apertureBox = await page.locator("[data-screen-aperture]").boundingBox();
    assert.ok(apertureBox && apertureBox.width > 0);

    // Zooming off 100% hides the shell artwork and its bezel footprint, shows
    // only the scaled canvas in the same wrapper, and disables the toggle.
    await setZoom(page, "200%");
    await page.locator('[data-device-body="hidden"]').waitFor();
    assert.equal(await page.locator("[data-device-preview]").count(), 1);
    assert.equal(await page.locator("[data-device-shell]").count(), 0);
    assert.equal(await bodyToggle.isEnabled(), false);
    assert.equal(
      await page.locator("[data-scene-stage]").getAttribute("aria-label"),
      "Scene canvas, 480 by 800 pixels",
    );
    assert.equal(await header.locator("[data-screen-resolution]").innerText(), "480 × 800 px");
    const zoomedBox = await page.locator("[data-screen-aperture]").boundingBox();
    assert.ok(zoomedBox);
    assert.ok(Math.abs(zoomedBox.width / apertureBox.width - 2) < 0.02, "the canvas scales with the zoom preset");

    // Returning to 100% restores the shell; the body preference was preserved.
    await setZoom(page, "100%");
    await page.locator('[data-device-body="shown"]').waitFor();
    assert.equal(await page.locator("[data-device-shell]").count(), 1);
    assert.equal(await bodyToggle.isEnabled(), true);
    assert.equal(await bodyToggle.getAttribute("aria-label"), "Hide device body");

    // Toggling the body off at 100% hides the shell but keeps the toggle live.
    await bodyToggle.click();
    await page.locator('[data-device-body="hidden"]').waitFor();
    assert.equal(await page.locator("[data-device-shell]").count(), 0);
    assert.equal(await bodyToggle.isEnabled(), true);
    assert.equal(await bodyToggle.getAttribute("aria-label"), "Show device body");

    // A zoom excursion while hidden keeps the shell hidden and the toggle
    // disabled, then restores the off preference at 100%.
    await setZoom(page, "50%");
    assert.equal(await page.locator("[data-device-shell]").count(), 0);
    assert.equal(await bodyToggle.isEnabled(), false);
    await setZoom(page, "100%");
    await page.locator('[data-device-body="hidden"]').waitFor();
    assert.equal(await page.locator("[data-device-shell]").count(), 0);
    assert.equal(await bodyToggle.getAttribute("aria-label"), "Show device body");
    await bodyToggle.click();
    await page.locator('[data-device-body="shown"]').waitFor();

    // The right-side controls stay reachable while the left metadata overflows:
    // shrink the viewport, then drive zoom purely from the header controls.
    await page.setViewportSize({ width: 700, height: 900 });
    await setZoom(page, "200%");
    await page.locator('[data-device-body="hidden"]').waitFor();
    assert.equal(await page.locator("[data-device-shell]").count(), 0);
    assert.equal(await bodyToggle.isEnabled(), false);
    await setZoom(page, "100%");
    await page.locator('[data-device-body="shown"]').waitFor();

    // Custom screens have no body, so the toggle stays disabled there.
    await header.getByRole("combobox", { name: "Device" }).click();
    await page.getByRole("option", { name: "Custom…", exact: true }).click();
    await page.locator("[data-screen-custom-frame]").waitFor();
    assert.equal(await bodyToggle.isEnabled(), false);
    assert.deepEqual(errors, []);
  },
);

test(
  "zoom and body swaps keep the stage mounted and preserve an editing draft",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    t.after(() => page.close());
    await bootLibrary(page, url);
    await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
    await page.locator("[data-device-preview]").waitFor();
    const header = page.locator("[data-screen-center-panel] > [data-screen-device-header]");
    const bodyToggle = header.locator("[data-screen-body-toggle]");

    // The canvas and aperture nodes survive zoom and body visibility swaps.
    await markStable(page);
    await setZoom(page, "200%");
    await page.locator('[data-device-body="hidden"]').waitFor();
    assert.ok(await stableTree(page), "zooming off 100% keeps the same stage node");
    await setZoom(page, "100%");
    await page.locator('[data-device-body="shown"]').waitFor();
    assert.ok(await stableTree(page), "zooming back keeps the same stage node");
    await bodyToggle.click();
    await page.locator('[data-device-body="hidden"]').waitFor();
    assert.ok(await stableTree(page), "toggling the body off keeps the same stage node");
    await bodyToggle.click();
    await page.locator('[data-device-body="shown"]').waitFor();
    assert.ok(await stableTree(page), "toggling the body on keeps the same stage node");

    // An uncommitted draft is never silently discarded by a zoom change: the
    // blur persists it through the store and the stage node stays the same.
    const id = await addScreenText(page, "Draft probe", { x: 24, y: 32 });
    await page.locator(`[data-scene-label-frame="${id}"]`).click();
    await page.locator(`[data-scene-label-frame="${id}"]`).press("Enter");
    const editor = page.locator(`[data-scene-edit-text="${id}"]`);
    await editor.waitFor();
    await editor.fill("Draft probe kept");
    await markStable(page);
    await setZoom(page, "150%");
    await page.locator('[data-device-body="hidden"]').waitFor();
    await editor.waitFor({ state: "detached" });
    assert.ok(await stableTree(page), "the zoom swap keeps the same stage node");
    await page.locator(`[data-scene-label-frame="${id}"]`).click();
    await page.locator(`[data-scene-label-frame="${id}"]`).press("Enter");
    await page.locator(`[data-scene-edit-text="${id}"]`).waitFor();
    assert.equal(await page.locator(`[data-scene-edit-text="${id}"]`).inputValue(), "Draft probe kept");
    assert.deepEqual(errors, []);
  },
);
