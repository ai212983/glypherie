// Centered canvas viewport with fixed pixel rulers: true aperture centering
// on both axes (including fitting content at 25%), pinned ruler paint, one
// scroll origin shared with the rulers, and recentered rotation/body/zoom.
import assert from "node:assert/strict";
import test from "node:test";
import type { Page } from "playwright-core";
import { bootLibrary, browserAvailable, buildApp, launch, servePrefix } from "../helpers/spa-helpers.ts";

async function setZoom(page: Page, label: string): Promise<void> {
  await page.getByRole("combobox", { name: "Zoom" }).click();
  await page.getByRole("option", { name: label, exact: true }).click();
}

async function centers(page: Page) {
  return page.locator("[data-screen-stage-scroll]").evaluate((viewport) => {
    const aperture = document.querySelector("[data-screen-aperture], [data-screen-custom-frame]");
    if (!(viewport instanceof HTMLElement) || !(aperture instanceof HTMLElement)) {
      throw new Error("Viewport is missing its aperture.");
    }
    const view = viewport.getBoundingClientRect();
    const box = aperture.getBoundingClientRect();
    return {
      dx: box.left + box.width / 2 - (view.left + view.width / 2),
      dy: box.top + box.height / 2 - (view.top + view.height / 2),
      viewWidth: view.width,
      viewHeight: view.height,
      apertureWidth: box.width,
      scrollableX: viewport.scrollWidth - viewport.clientWidth,
      scrollableY: viewport.scrollHeight - viewport.clientHeight,
    };
  });
}

async function rulerPaint(page: Page, type: "horizontal" | "vertical"): Promise<number> {
  return page.locator(`[data-pixel-ruler="${type}"] canvas`).evaluate((canvas) => {
    if (!(canvas instanceof HTMLCanvasElement)) throw new Error("Ruler canvas is missing.");
    const data = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data;
    const seen = new Set<string>();
    for (let i = 0; i < data.length; i += 4) seen.add(`${data[i]},${data[i + 1]},${data[i + 2]},${data[i + 3]}`);
    return seen.size;
  });
}

test(
  "rulers pin around a truly centered aperture and share its scroll origin",
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
    await page.locator("[data-screen-aperture]").waitFor();
    await page.locator('[data-pixel-ruler="horizontal"] canvas').waitFor();
    await page.locator('[data-pixel-ruler="vertical"] canvas').waitFor();

    // Both rulers really paint (not blank canvases) and the corner names the unit.
    assert.ok((await rulerPaint(page, "horizontal")) > 2, "horizontal ruler paints ticks");
    assert.ok((await rulerPaint(page, "vertical")) > 2, "vertical ruler paints ticks");
    assert.equal((await page.locator("[data-canvas-corner]").innerText()).trim(), "px");

    // Full numeric labels sit inside the 22px strip: sample a band the clipped
    // pre-fix placement never reaches (above the tick zone, away from major
    // tick columns) and require real label pixels there on both axes.
    async function labelBandPixels(type: "horizontal" | "vertical"): Promise<number> {
      const scrollPos = Number(
        await page
          .locator("[data-canvas-scroll]")
          .getAttribute(`data-ruler-scroll-${type === "horizontal" ? "x" : "y"}`),
      );
      const unit = Number(await page.locator("[data-canvas-scroll]").getAttribute("data-ruler-unit"));
      const zoom = (await centers(page)).apertureWidth / 480;
      return page.locator(`[data-pixel-ruler="${type}"] canvas`).evaluate(
        (canvas, opts: { scrollPos: number; zoom: number; unit: number; horizontal: boolean }) => {
          if (!(canvas instanceof HTMLCanvasElement)) throw new Error("Ruler canvas is missing.");
          const context = canvas.getContext("2d")!;
          const image = context.getImageData(0, 0, canvas.width, canvas.height).data;
          const cssWidth = canvas.getBoundingClientRect().width;
          const cssHeight = canvas.getBoundingClientRect().height;
          const density = canvas.width / cssWidth;
          // The strip background is the most common pixel; anything else is ink.
          const votes = new Map<string, number>();
          for (let i = 0; i < image.length; i += 28) {
            const key = `${image[i]},${image[i + 1]},${image[i + 2]}`;
            votes.set(key, (votes.get(key) ?? 0) + 1);
          }
          const background = [...votes.entries()].sort((left, right) => right[1] - left[1])[0]?.[0];
          const ink = (x: number, y: number): boolean => {
            const i = (Math.round(y * density) * canvas.width + Math.round(x * density)) * 4;
            return `${image[i]},${image[i + 1]},${image[i + 2]}` !== background;
          };
          let count = 0;
          if (opts.horizontal) {
            for (let y = 9; y <= 11; y += 1) {
              for (let x = 0; x < cssWidth; x += 2) {
                const value = opts.scrollPos + x / opts.zoom;
                if (Math.abs(value - Math.round(value / opts.unit) * opts.unit) * opts.zoom <= 2) continue;
                if (ink(x, y)) count += 1;
              }
            }
          } else {
            for (let x = 6; x <= 11; x += 1) {
              for (let y = 0; y < cssHeight; y += 2) {
                const value = opts.scrollPos + y / opts.zoom;
                if (Math.abs(value - Math.round(value / opts.unit) * opts.unit) * opts.zoom <= 2) continue;
                if (ink(x, y)) count += 1;
              }
            }
          }
          return count;
        },
        { scrollPos, zoom, unit, horizontal: type === "horizontal" },
      );
    }
    assert.ok((await labelBandPixels("horizontal")) >= 5, "horizontal labels sit inside the strip");
    assert.ok((await labelBandPixels("vertical")) >= 5, "vertical labels sit inside the strip");

    // True center at normal size with the body shown, on both axes.
    const atRest = await centers(page);
    assert.ok(Math.abs(atRest.dx) < 1.5, `aperture centered horizontally (${atRest.dx})`);
    assert.ok(Math.abs(atRest.dy) < 1.5, `aperture centered vertically (${atRest.dy})`);

    // Panning moves the single shared origin: ruler scrollPos follows the
    // scrolled pixels divided by the presentation scale (200% overflows both
    // axes so both directions pan; at 100% the content fits horizontally).
    // The origin follows layout and scroll asynchronously, so both the
    // baseline and the post-pan snapshots wait for scroll position and ruler
    // origin to agree they are settled; a first-change wait can catch a stale
    // catch-up instead of the pan.
    async function settledOrigin(): Promise<{ x: number; y: number; rulerX: number }> {
      async function read(): Promise<{ x: number; y: number; rulerX: number }> {
        return page.locator("[data-screen-stage-scroll]").evaluate((el) => {
          if (!(el instanceof HTMLElement)) throw new Error("Viewport is missing.");
          const scroller = document.querySelector("[data-canvas-scroll]");
          return {
            x: el.scrollLeft,
            y: el.scrollTop,
            rulerX: Number(scroller?.getAttribute("data-ruler-scroll-x")),
          };
        });
      }
      let previous = await read();
      for (let attempt = 0; attempt < 30; attempt += 1) {
        await page.waitForTimeout(100);
        const next = await read();
        if (next.x === previous.x && next.y === previous.y && next.rulerX === previous.rulerX) return next;
        previous = next;
      }
      throw new Error(`scroll origin never settled: ${JSON.stringify(previous)}`);
    }
    await setZoom(page, "200%");
    await page.locator('[data-device-body="hidden"]').waitFor();
    const cssScale = (await centers(page)).apertureWidth / 480;
    const before = await settledOrigin();
    const moved = await page.locator("[data-screen-stage-scroll]").evaluate((el) => {
      if (!(el instanceof HTMLElement)) throw new Error("Viewport is missing.");
      el.scrollBy(60, 40);
      return { x: el.scrollLeft, y: el.scrollTop };
    });
    assert.ok(moved.x !== before.x, "the pan actually scrolled");
    const after = await settledOrigin();
    assert.ok(
      Math.abs(after.rulerX - before.rulerX - (after.x - before.x) / cssScale) < 0.05,
      `ruler origin tracks horizontal pan (before=${before.rulerX} after=${after.rulerX} dx=${after.x - before.x})`,
    );

    // Fitting content at 25% centers on both axes (no scroll can hide error).
    await setZoom(page, "25%");
    await page.waitForTimeout(300);
    const fitted = await centers(page);
    assert.equal(fitted.scrollableX, 0, "fitting content scrolls nowhere");
    assert.ok(Math.abs(fitted.dx) < 1.5, `fitting aperture centered horizontally (${fitted.dx})`);
    assert.ok(Math.abs(fitted.dy) < 1.5, `fitting aperture centered vertically (${fitted.dy})`);

    // Zooming back keeps the stage mounted and recenters the aperture.
    await page.locator("[data-scene-stage]").evaluate((el) => {
      (el as HTMLElement).dataset.stayMounted = "1";
    });
    await setZoom(page, "100%");
    await page.locator('[data-device-body="shown"]').waitFor();
    const zoomed = await centers(page);
    assert.ok(Math.abs(zoomed.dx) < 1.5 && Math.abs(zoomed.dy) < 1.5, "aperture recentered at 100%");
    assert.equal(
      await page.locator("[data-scene-stage]").evaluate((el) => (el as HTMLElement).dataset.stayMounted),
      "1",
      "zoom keeps the same stage node",
    );

    // Hiding the body centers the bare canvas on both axes.
    await header.locator("[data-screen-body-toggle]").click();
    await page.locator('[data-device-body="hidden"]').waitFor();
    const bare = await centers(page);
    assert.ok(
      Math.abs(bare.dx) < 1.5 && Math.abs(bare.dy) < 1.5,
      `bare canvas centered dx=${bare.dx} dy=${bare.dy} vw=${bare.viewWidth} vh=${bare.viewHeight} aw=${bare.apertureWidth} sx=${bare.scrollableX} sy=${bare.scrollableY}`,
    );

    // Rotation recenters the oriented canvas on both axes.
    await header.locator("[data-screen-body-toggle]").click();
    await page.locator('[data-device-body="shown"]').waitFor();
    await header.locator("[data-screen-rotate]").click();
    await page.locator('[data-device-rotation="90"]').waitFor();
    const rotated = await centers(page);
    assert.ok(Math.abs(rotated.dx) < 1.5 && Math.abs(rotated.dy) < 1.5, "rotated aperture recentered");

    // A narrow viewport at high zoom scrolls for real and stays reachable.
    await setZoom(page, "400%");
    await page.setViewportSize({ width: 700, height: 500 });
    await page.waitForTimeout(300);
    const narrow = await centers(page);
    assert.ok(narrow.scrollableX > 0 && narrow.scrollableY > 0, "oversized content scrolls on both axes");
    await page.locator("[data-screen-stage-scroll]").evaluate((el) => {
      if (el instanceof HTMLElement) el.scrollTo(el.scrollWidth, el.scrollHeight);
    });
    await page.waitForTimeout(200);
    const reached = await page.locator("[data-screen-stage-scroll]").evaluate((el) => {
      if (!(el instanceof HTMLElement)) throw new Error("Viewport is missing.");
      return {
        x: el.scrollLeft,
        maxX: el.scrollWidth - el.clientWidth,
        y: el.scrollTop,
        maxY: el.scrollHeight - el.clientHeight,
      };
    });
    assert.ok(Math.abs(reached.x - reached.maxX) < 1 && Math.abs(reached.y - reached.maxY) < 1, "edges reachable");
    assert.deepEqual(errors, []);
  },
);
