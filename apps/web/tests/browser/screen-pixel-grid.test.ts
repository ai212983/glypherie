// Pixel-grid toggle: enabled strictly above 100% zoom with a remembered
// local preference; one gradient overlay paints native-pixel boundaries
// clipped to the canvas without intercepting gestures or touching the scene.
import assert from "node:assert/strict";
import test from "node:test";
import type { Page } from "playwright-core";
import { addScreenText } from "../helpers/screen-tools.ts";
import { bootLibrary, browserAvailable, buildApp, launch, servePrefix, tooltipText } from "../helpers/spa-helpers.ts";

async function setZoom(page: Page, label: string): Promise<void> {
  await page.getByRole("combobox", { name: "Zoom" }).click();
  await page.getByRole("option", { name: label, exact: true }).click();
}

async function gridEnabled(page: Page): Promise<boolean> {
  return page
    .locator("[data-screen-grid-toggle]")
    .evaluate((toggle) => toggle instanceof HTMLButtonElement && !toggle.disabled);
}

async function waitForGridToggle(page: Page, enabled: boolean): Promise<void> {
  await page.waitForFunction((want) => {
    const toggle = document.querySelector("[data-screen-grid-toggle]");
    return toggle instanceof HTMLButtonElement && !toggle.disabled === want;
  }, enabled);
}

interface PaintDiff {
  fraction: number;
  mean: number;
}

// Real paint comparison of two PNG screenshots: the browser decodes both
// and reports the share of differing pixels plus the mean per-byte
// difference, so the grid must actually paint (not just exist as a node)
// while staying subtle enough to preserve label readability.
async function paintDiff(page: Page, before: Buffer, after: Buffer): Promise<PaintDiff> {
  return page.evaluate(
    async (shots: { before: number[]; after: number[] }): Promise<PaintDiff> => {
      async function pixels(bytes: number[]): Promise<Uint8ClampedArray> {
        const blob = new Blob([new Uint8Array(bytes)], { type: "image/png" });
        const bitmap = await createImageBitmap(blob);
        try {
          const canvas = document.createElement("canvas");
          canvas.width = bitmap.width;
          canvas.height = bitmap.height;
          const context = canvas.getContext("2d", { willReadFrequently: true });
          if (!context) throw new Error("Canvas 2D context unavailable.");
          context.drawImage(bitmap, 0, 0);
          return context.getImageData(0, 0, canvas.width, canvas.height).data;
        } finally {
          bitmap.close();
        }
      }
      const first = await pixels(shots.before);
      const second = await pixels(shots.after);
      if (first.length !== second.length) throw new Error("Screenshot size changed between shots.");
      let changed = 0;
      let total = 0;
      for (let i = 0; i < first.length; i += 4) {
        const delta =
          Math.abs(first[i]! - second[i]!) +
          Math.abs(first[i + 1]! - second[i + 1]!) +
          Math.abs(first[i + 2]! - second[i + 2]!);
        total += delta;
        if (delta > 0) changed += 1;
      }
      return { fraction: changed / (first.length / 4), mean: total / first.length };
    },
    { before: [...before], after: [...after] },
  );
}

async function stageBox(
  page: Page,
  selector: string,
): Promise<{ x: number; y: number; width: number; height: number }> {
  const box = await page.locator(selector).boundingBox();
  assert.ok(box, `${selector} has a bounding box`);
  return box;
}

function near(first: number, second: number, tolerance = 1): boolean {
  return Math.abs(first - second) <= tolerance;
}

test(
  "pixel grid toggles above 100% zoom and paints a bounded subtle overlay",
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
    const gridToggle = header.locator("[data-screen-grid-toggle]");

    // At 100% the toggle is disabled, unpressed, and no overlay exists.
    assert.equal(await gridToggle.isEnabled(), false);
    assert.equal(await gridToggle.getAttribute("aria-pressed"), "false");
    assert.equal(await gridToggle.getAttribute("aria-label"), "Show grid");
    assert.equal(await page.locator("[data-scene-pixel-grid]").count(), 0);

    // 25% stays disabled with no grid.
    await setZoom(page, "25%");
    await waitForGridToggle(page, false);
    assert.equal(await page.locator("[data-scene-pixel-grid]").count(), 0);

    // Above 100% the toggle enables with an accurate hint.
    await setZoom(page, "200%");
    await waitForGridToggle(page, true);
    assert.equal(await tooltipText(page, gridToggle), "Show the grid (8 px cells)");

    // The toggle flips with a real visible active state, not just metadata.
    const idleBackground = await gridToggle.evaluate((toggle) => getComputedStyle(toggle).backgroundColor);
    const idleBorder = await gridToggle.evaluate((toggle) => getComputedStyle(toggle).borderColor);
    await gridToggle.click();
    await page.locator("[data-scene-pixel-grid]").waitFor();
    assert.equal(await gridToggle.getAttribute("aria-pressed"), "true");
    assert.equal(await gridToggle.getAttribute("aria-label"), "Hide grid");
    // Read off-hover: the pointer stays on the button after the click and the
    // shared hover wash would pollute the pressed-state comparison.
    await page.mouse.move(0, 0, { steps: 5 });
    await page.waitForTimeout(300);
    const pressedBackground = await gridToggle.evaluate((toggle) => getComputedStyle(toggle).backgroundColor);
    const pressedBorder = await gridToggle.evaluate((toggle) => getComputedStyle(toggle).borderColor);
    assert.notEqual(pressedBackground, idleBackground, "pressed grid toggle reads active");
    assert.notEqual(pressedBorder, idleBorder, "pressed grid toggle border reads active");

    // The overlay is one gradient pair at the stage origin, clipped exactly to
    // the logical canvas, never intercepting gestures or assistive tech.
    const overlayStyle = await page.locator("[data-scene-pixel-grid]").evaluate((overlay) => {
      if (!(overlay instanceof HTMLElement)) throw new Error("Grid overlay is missing.");
      const computed = getComputedStyle(overlay);
      return {
        image: computed.backgroundImage,
        pointerEvents: computed.pointerEvents,
        hidden: overlay.getAttribute("aria-hidden"),
        tabbable: overlay.tabIndex,
      };
    });
    assert.ok(overlayStyle.image.includes("repeating-linear-gradient"), "gradient overlay paints from CSS");
    assert.equal(overlayStyle.image.match(/repeating-linear-gradient/g)?.length, 2, "one gradient per axis");
    assert.equal(overlayStyle.pointerEvents, "none");
    assert.equal(overlayStyle.hidden, "true");
    assert.equal(overlayStyle.tabbable, -1);
    const stage = await stageBox(page, "[data-scene-stage]");
    const overlay = await stageBox(page, "[data-scene-pixel-grid]");
    for (const edge of ["x", "y", "width", "height"] as const) {
      assert.ok(
        near(overlay[edge], stage[edge]),
        `grid ${edge} matches the stage (${overlay[edge]} vs ${stage[edge]})`,
      );
    }
    // The grid step is 8 native device px: the rendered CSS pitch equals eight
    // times the measured presentation scale (stage width over native width).
    const nativeWidth = Number(
      (await page.locator("[data-scene-stage]").getAttribute("aria-label"))?.match(/Scene canvas, (\d+) by/)?.[1],
    );
    assert.ok(Number.isInteger(nativeWidth) && nativeWidth > 0, "stage names its native width");
    const expectedPitch = (8 * stage.width) / nativeWidth;
    const renderedPitch = Math.max(...[...overlayStyle.image.matchAll(/([\d.]+)px/g)].map((match) => Number(match[1])));
    assert.ok(
      near(renderedPitch, expectedPitch, 0.05),
      `grid step is 8 native px (rendered ${renderedPitch}px vs expected ${expectedPitch}px)`,
    );

    // The grid actually paints pixels, yet stays subtle over the paper.
    const gridOnShot = await page.locator("[data-scene-stage]").screenshot();
    await gridToggle.click();
    await page.locator("[data-scene-pixel-grid]").waitFor({ state: "detached" });
    const gridOntoOff = await paintDiff(page, gridOnShot, await page.locator("[data-scene-stage]").screenshot());
    assert.ok(gridOntoOff.fraction > 0.01, `grid paints pixels (fraction ${gridOntoOff.fraction})`);
    assert.ok(gridOntoOff.mean < 40, `grid stays subtle (mean ${gridOntoOff.mean})`);
    await gridToggle.click();
    await page.locator("[data-scene-pixel-grid]").waitFor();

    // Toggling changes no saved revision, no scroll position and no stage node.
    const revision = await page.locator("[data-screen-workspace]").getAttribute("data-screen-revision");
    const scrollBefore = await page.locator("[data-screen-stage-scroll]").evaluate((el) => {
      if (!(el instanceof HTMLElement)) throw new Error("Stage scroller is missing.");
      return { x: el.scrollLeft, y: el.scrollTop };
    });
    await page.locator("[data-scene-stage]").evaluate((el) => {
      (el as HTMLElement).dataset.stayMounted = "1";
    });
    await gridToggle.click();
    await page.locator("[data-scene-pixel-grid]").waitFor({ state: "detached" });
    await gridToggle.click();
    await page.locator("[data-scene-pixel-grid]").waitFor();
    assert.equal(await page.locator("[data-screen-workspace]").getAttribute("data-screen-revision"), revision);
    assert.deepEqual(
      await page.locator("[data-screen-stage-scroll]").evaluate((el) => {
        if (!(el instanceof HTMLElement)) throw new Error("Stage scroller is missing.");
        return { x: el.scrollLeft, y: el.scrollTop };
      }),
      scrollBefore,
    );
    assert.equal(
      await page.locator("[data-scene-stage]").evaluate((el) => (el as HTMLElement).dataset.stayMounted),
      "1",
      "toggling keeps the same stage node",
    );

    // Keyboard toggles the grid too.
    await gridToggle.focus();
    await page.keyboard.press("Space");
    await page.locator("[data-scene-pixel-grid]").waitFor({ state: "detached" });
    assert.equal(await gridToggle.getAttribute("aria-pressed"), "false");
    await page.keyboard.press("Enter");
    await page.locator("[data-scene-pixel-grid]").waitFor();
    assert.equal(await gridToggle.getAttribute("aria-pressed"), "true");

    // Gestures pass through the overlay: adding, selecting and editing labels
    // all work with the grid on, and handles render above it.
    const id = await addScreenText(page, "Grid probe", { x: 24, y: 32 });
    assert.equal(await page.locator("[data-scene-pixel-grid]").count(), 1, "grid survives label adds");
    await page.locator(`[data-scene-label-frame="${id}"]`).click();
    assert.equal(await page.locator(`[data-scene-label-frame="${id}"]`).getAttribute("aria-selected"), "true");
    await page.locator(".moveable-control-box").waitFor();
    await page.locator(`[data-scene-label-frame="${id}"]`).press("Enter");
    const editor = page.locator(`[data-scene-edit-text="${id}"]`);
    await editor.waitFor();
    await editor.press("Escape");
    await editor.waitFor({ state: "detached" });

    // The overlay tracks panning: it moves exactly with the stage, never with
    // the viewport.
    const pan = await page.locator("[data-screen-stage-scroll]").evaluate((el) => {
      if (!(el instanceof HTMLElement)) throw new Error("Stage scroller is missing.");
      el.scrollBy(60, 40);
      return { x: el.scrollLeft, y: el.scrollTop };
    });
    assert.ok(pan.x > 0 && pan.y > 0, "the pan actually scrolled");
    const pannedStage = await stageBox(page, "[data-scene-stage]");
    const pannedOverlay = await stageBox(page, "[data-scene-pixel-grid]");
    for (const edge of ["x", "y", "width", "height"] as const) {
      assert.ok(
        near(pannedOverlay[edge], pannedStage[edge]),
        `panned grid ${edge} matches the stage (${pannedOverlay[edge]} vs ${pannedStage[edge]})`,
      );
    }

    // Dropping to 100% hides the grid and disables the toggle while the
    // preference survives; returning above 100% restores the grid untouched.
    await setZoom(page, "100%");
    await waitForGridToggle(page, false);
    assert.equal(await page.locator("[data-scene-pixel-grid]").count(), 0);
    assert.equal(await gridToggle.getAttribute("aria-pressed"), "false");
    await setZoom(page, "200%");
    await page.locator("[data-scene-pixel-grid]").waitFor();
    assert.equal(await gridToggle.getAttribute("aria-pressed"), "true");

    // 400% keeps the overlay bounded to the stage, rotation keeps it on the
    // oriented canvas, and custom screens keep the toggle live.
    await setZoom(page, "400%");
    await page.locator("[data-scene-pixel-grid]").waitFor();
    const zoomedStage = await stageBox(page, "[data-scene-stage]");
    const zoomedOverlay = await stageBox(page, "[data-scene-pixel-grid]");
    for (const edge of ["x", "y", "width", "height"] as const) {
      assert.ok(
        near(zoomedOverlay[edge], zoomedStage[edge], 1.5),
        `400% grid ${edge} matches the stage (${zoomedOverlay[edge]} vs ${zoomedStage[edge]})`,
      );
    }
    await header.locator("[data-screen-rotate]").click();
    await page.locator('[data-device-rotation="90"]').waitFor();
    const rotatedStage = await stageBox(page, "[data-scene-stage]");
    const rotatedOverlay = await stageBox(page, "[data-scene-pixel-grid]");
    for (const edge of ["x", "y", "width", "height"] as const) {
      assert.ok(
        near(rotatedOverlay[edge], rotatedStage[edge], 1.5),
        `rotated grid ${edge} matches the stage (${rotatedOverlay[edge]} vs ${rotatedStage[edge]})`,
      );
    }
    await header.getByRole("combobox", { name: "Device" }).click();
    await page.getByRole("option", { name: "Custom…", exact: true }).click();
    await page.locator("[data-screen-custom-frame]").waitFor();
    assert.equal(await gridEnabled(page), true, "custom screens keep the grid toggle live above 100%");
    const customStage = await stageBox(page, "[data-scene-stage]");
    const customOverlay = await stageBox(page, "[data-scene-pixel-grid]");
    for (const edge of ["x", "y", "width", "height"] as const) {
      assert.ok(
        near(customOverlay[edge], customStage[edge], 1.5),
        `custom grid ${edge} matches the stage (${customOverlay[edge]} vs ${customStage[edge]})`,
      );
    }

    // A narrow 390px viewport keeps the grid toggle reachable and operable.
    await page.setViewportSize({ width: 390, height: 900 });
    await page.waitForTimeout(300);
    const toggleBox = await gridToggle.boundingBox();
    assert.ok(toggleBox, "grid toggle has a bounding box at 390px");
    assert.ok(toggleBox.x >= 0 && toggleBox.x + toggleBox.width <= 390, "grid toggle stays reachable at 390px");
    await gridToggle.click();
    await page.locator("[data-scene-pixel-grid]").waitFor({ state: "detached" });
    assert.equal(await gridToggle.getAttribute("aria-pressed"), "false");
    await gridToggle.click();
    await page.locator("[data-scene-pixel-grid]").waitFor();
    assert.deepEqual(errors, []);
  },
);

test("pixel grid toggle reads active in the dark theme", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, colorScheme: "dark" });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);
  await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
  const header = page.locator("[data-screen-center-panel] > [data-screen-device-header]");
  await header.waitFor();
  await page.locator("[data-device-preview]").waitFor();
  const gridToggle = header.locator("[data-screen-grid-toggle]");

  await setZoom(page, "200%");
  await waitForGridToggle(page, true);
  const idleBackground = await gridToggle.evaluate((toggle) => getComputedStyle(toggle).backgroundColor);
  await gridToggle.click();
  await page.locator("[data-scene-pixel-grid]").waitFor();
  assert.equal(await gridToggle.getAttribute("aria-pressed"), "true");
  await page.mouse.move(0, 0, { steps: 5 });
  await page.waitForTimeout(300);
  const pressedBackground = await gridToggle.evaluate((toggle) => getComputedStyle(toggle).backgroundColor);
  assert.notEqual(pressedBackground, idleBackground, "pressed grid toggle reads active in the dark theme");
  assert.deepEqual(errors, []);
});
