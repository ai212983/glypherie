import assert from "node:assert/strict";
import test from "node:test";
import { addScreenText, showScreenCanvas } from "../helpers/screen-tools.ts";
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

test("canvas tools place text in device pixels and remember selected fonts", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  t.after(() => page.close());
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await bootLibrary(page, url);
  await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
  const toolbar = page.getByRole("toolbar", { name: "Canvas tools" });
  await toolbar.waitFor();
  assert.equal(await toolbar.getByRole("button").count(), 2);
  assert.equal(await page.getByRole("heading", { name: "Add label", exact: true }).count(), 0);
  const select = toolbar.getByRole("button", { name: "Select", exact: true });
  const text = toolbar.getByRole("button", { name: "Add text", exact: true });
  assert.equal(await select.getAttribute("aria-pressed"), "true");
  await page.locator("[data-scene-stage]").click();
  assert.equal(await page.locator("[data-scene-label-container]").count(), 0);
  await text.click();
  const placement = page.locator("[data-scene-text-placement]");
  assert.equal(await placement.evaluate((element) => getComputedStyle(element).cursor), "crosshair");
  await placement.click({ button: "right" });
  assert.equal(await page.locator("[data-scene-label-container]").count(), 0);
  await page.keyboard.press("Escape");
  assert.equal(await select.getAttribute("aria-pressed"), "true");
  assert.equal(await placement.count(), 0);

  const first = await addScreenText(page, "First", { x: 80, y: 120 });
  assert.equal(await page.locator("[data-scene-inspector-x]").inputValue(), "80");
  assert.equal(await page.locator("[data-scene-inspector-y]").inputValue(), "120");
  assert.equal(await select.getAttribute("aria-pressed"), "true");
  // Without saved variants, the fallback is the first font in the inspector.
  const reference = page.locator("[data-scene-inspector-style]");
  const defaultFont = await reference.textContent();
  await reference.click();
  assert.equal(await page.getByRole("option").first().textContent(), defaultFont);
  await page.getByRole("option", { name: "Literata", exact: true }).click();
  await page.waitForFunction(() => !document.querySelector("[data-scene-inspector-style]")?.matches(":disabled"));
  await page.locator("[data-scene-stage]").click({ position: { x: 4, y: 4 } });
  assert.equal(await page.locator("[data-scene-inspector]").count(), 0);
  const second = await addScreenText(page, "Second", { x: 140, y: 240 });
  assert.equal(await reference.textContent(), "Literata");
  assert.equal(await page.locator("[data-scene-inspector-x]").inputValue(), "140");
  assert.equal(await page.locator("[data-scene-inspector-y]").inputValue(), "240");

  // The placement layer also wins over existing text and selection controls.
  const frame = page.locator(`[data-scene-label-frame="${second}"]`);
  await text.click();
  await showScreenCanvas(page);
  const box = await frame.boundingBox();
  assert.ok(box);
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  const editor = page.locator("[data-scene-edit-text]");
  await editor.waitFor();
  assert.notEqual(await editor.getAttribute("data-scene-edit-text"), second);
  // Typing directly replaces the selected placeholder.
  await page.waitForFunction(() => {
    const input = document.querySelector("[data-scene-edit-text]") as HTMLTextAreaElement | null;
    return input?.selectionStart === 0 && input.selectionEnd === 4;
  });
  await page.keyboard.type("Over");
  assert.equal(await editor.inputValue(), "Over");
  await editor.press("ControlOrMeta+Enter");
  await editor.waitFor({ state: "detached" });
  assert.equal(await page.locator("[data-scene-label-container]").count(), 3);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator(`[data-scene-label-container="${first}"]`).waitFor();
  await page.locator(`[data-scene-label-container="${second}"]`).waitFor();
  assert.equal(await page.locator("[data-scene-label-container]").count(), 3);
  assert.deepEqual(errors, []);
});

test(
  "new text falls back to the first variant and reuses it after deselection",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    t.after(() => page.close());
    await bootLibrary(page, url);
    const names = await cardNames(page);
    const ids = await cardIds(page);
    const index = names.findIndex((name) => /^Roboto Flex/.test(name));
    assert.ok(index >= 0);
    await openNewVariant(page, ids[index]!);
    await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
    await addScreenText(page, "Variant");
    const reference = page.locator("[data-scene-inspector-style]");
    const variant = await reference.textContent();
    assert.match(variant ?? "", /—/);
    await reference.click();
    assert.equal(await page.getByRole("option").first().textContent(), variant);
    await page.keyboard.press("Escape");
    await page.locator("[data-scene-stage]").click({ position: { x: 4, y: 4 } });
    await addScreenText(page, "Reused", { x: 120, y: 160 });
    assert.equal(await reference.textContent(), variant);
  },
);
