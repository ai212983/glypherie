import assert from "node:assert/strict";
import type { Page } from "playwright-core";

// Exercise the same click-to-place flow as the editor, at native device
// coordinates regardless of the current presentation scale.
export async function addScreenText(
  page: Page,
  text: string,
  options: { x?: number; y?: number; fontName?: string; variant?: boolean } = {},
): Promise<string> {
  const known = await page
    .locator("[data-scene-label-container]")
    .evaluateAll((elements) => elements.map((element) => element.getAttribute("data-scene-label-container")));
  await page.locator('[data-screen-tool="text"]').click();
  const stage = page.locator("[data-scene-stage]");
  await showScreenCanvas(page);
  // Center the requested native point in the canvas viewport, rather than
  // clicking a clipped part of the canvas underneath a ruler or toolbar.
  await stage.evaluate(
    (canvas, native) => {
      const viewport = canvas.closest<HTMLElement>("[data-screen-stage-scroll]");
      if (!viewport) return;
      const bounds = canvas.getBoundingClientRect();
      const width = Number(canvas.getAttribute("aria-label")?.match(/Scene canvas, (\d+) by/)?.[1]);
      const scale = bounds.width / width;
      const visible = viewport.getBoundingClientRect();
      const toolbar = document.querySelector("[data-screen-tools]")?.getBoundingClientRect();
      const bottom = Math.min(visible.bottom, toolbar?.top ?? visible.bottom);
      viewport.scrollLeft += bounds.left + native.x * scale - (visible.left + visible.width / 2);
      viewport.scrollTop += bounds.top + native.y * scale - (visible.top + bottom) / 2;
    },
    { x: options.x ?? 8, y: options.y ?? 8 },
  );
  const bounds = await stage.boundingBox();
  const label = await stage.getAttribute("aria-label");
  const width = Number(label?.match(/Scene canvas, (\d+) by/)?.[1]);
  assert.ok(bounds && width > 0);
  const scale = bounds.width / width;
  const point = { x: bounds.x + (options.x ?? 8) * scale, y: bounds.y + (options.y ?? 8) * scale };
  const hit = await page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.outerHTML.slice(0, 500), point);
  assert.ok(hit?.includes("data-scene-text-placement"), `placement click hits ${hit}; point=${JSON.stringify(point)}`);
  await page.mouse.click(point.x, point.y);
  const editor = page.locator("[data-scene-edit-text]");
  await editor.waitFor();
  const id = await editor.getAttribute("data-scene-edit-text");
  assert.ok(id && !known.includes(id));
  await editor.fill(text);
  await editor.press("ControlOrMeta+Enter");
  await editor.waitFor({ state: "detached" });
  if (options.fontName || options.variant) {
    const reference = page.locator("[data-scene-inspector-style]");
    const current = (await reference.textContent()) ?? "";
    if (!((options.fontName && current === options.fontName) || (options.variant && /—/.test(current)))) {
      await reference.click();
      const choice = options.fontName
        ? page.getByRole("option", { name: options.fontName, exact: true })
        : page.getByRole("option").filter({ hasText: /—/ }).first();
      await choice.click();
      await page.waitForFunction(() => !document.querySelector("[data-scene-inspector-style]")?.matches(":disabled"));
      // Radix keeps the modal pointer lock until its close animation ends.
      await page.waitForFunction(() => !document.body.hasAttribute("data-scroll-locked"));
    }
  }
  await showScreenCanvas(page);
  return id;
}

// Scroll the page, preserving the device shell's own clipping and scroll
// position. Centering a nested stage with scrollIntoView would scroll the
// shell itself and clip its selection handles.
export async function showScreenCanvas(page: Page): Promise<void> {
  await page.locator("[data-scene-stage]").evaluate((stage) => {
    const scroller = stage.closest(".app-shell__page") ?? document.scrollingElement;
    if (!scroller) return;
    const headerBottom = document.querySelector(".site-header")?.getBoundingClientRect().bottom ?? 0;
    scroller.scrollTop += stage.getBoundingClientRect().top - headerBottom - 32;
  });
}
