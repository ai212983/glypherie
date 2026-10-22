import assert from "node:assert/strict";
import test from "node:test";
import {
  bootDetail,
  bootLibrary,
  browserAvailable,
  buildApp,
  canvasRendered,
  cardIds,
  createPalettePreset,
  hashParam,
  launch,
  openNewVariant,
  selectPalettePreset,
  servePrefix,
  setZoom,
} from "../helpers/spa-helpers.ts";

// Capture the latest worker render spec's mono_raster: "absent" when the
// key is missing, "unset" before the first render.
const SPEC_SCRIPT = `
window.__lastMonoRaster = "unset";
window.__lastSpec = null;
window.__lastLayout = null;
window.__lastCompletedSpec = null;
window.__lastSeq = null;
const RealWorker = window.Worker;
window.Worker = function (url, options) {
  const worker = new RealWorker(url, options);
  worker.addEventListener("message", (event) => {
    if (event.data?.ok && event.data.value?.layout && event.data.seq === window.__lastSeq) {
      window.__lastLayout = event.data.value.layout;
      window.__lastCompletedSpec = JSON.stringify(window.__lastSpec);
    }
  });
  const post = worker.postMessage.bind(worker);
  worker.postMessage = (message, transfer) => {
    if (message && typeof message === "object" && message.kind === "render" && message.spec) {
      window.__lastSpec = message.spec;
      window.__lastSeq = message.seq;
      window.__lastMonoRaster = "mono_raster" in message.spec
        ? JSON.stringify(message.spec.mono_raster)
        : "absent";
    }
    return post(message, transfer);
  };
  return worker;
};`;

async function lastMonoRaster(page: import("playwright-core").Page): Promise<string> {
  return page.evaluate(() => (window as unknown as { __lastMonoRaster: string }).__lastMonoRaster);
}

async function assertControlLayers(page: import("playwright-core").Page): Promise<void> {
  const ownership = {
    font: ["[data-size-px]", "[data-axis]"],
    fitting: ["#stem-fitting-control"], output: ["#output-mode"],
    layout: ["[data-kerning]"], specimen: ["[data-text]", "[data-preset]", "[data-reset]"],
  };
  for (const [layer, controls] of Object.entries(ownership)) {
    const group = page.locator(`[data-control-layer="${layer}"]`);
    assert.equal(await group.count(), 1);
    for (const selector of controls) {
      assert.ok(await group.locator(selector).count() >= 1, `${selector} belongs to ${layer}`);
    }
  }
  assert.equal(await page.locator('[data-control-layer="display"]').count(), 0);
  assert.equal(await page.locator('[data-site-header] #zoom').count(), 1);
  assert.equal(await page.locator('[data-zoom-reset]').count(), 0);
  for (const selector of ["#mono-dropout", "#mono-stubs", "#mono-scan-font", "#rasterization", "#pixel-accurate", ".font-kerning"]) {
    assert.equal(await page.locator(selector).count(), 0, `${selector} was removed`);
  }
  for (const width of [320, 390, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    assert.ok(await page.locator("[data-global-zoom]").evaluate((element) => {
      const box = element.getBoundingClientRect();
      return box.left >= 0 && box.right <= innerWidth && document.documentElement.scrollWidth <= innerWidth;
    }), `header zoom stays within the page at ${width}px`);
  }
}

const fixedScan = { dropout: "smart", include_stubs: true, font_instructions: true };

test("Automatic fitting has a persistent selective font-hints toggle only for hinted Mono fonts", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage();
  await page.addInitScript(SPEC_SCRIPT);
  await bootLibrary(page, url);
  const roboto = await page.locator('[data-font-card]').filter({ hasText: 'Roboto Regular' }).getAttribute('data-font-card');
  const literata = await page.locator('[data-font-card]').filter({ hasText: 'Literata Regular' }).getAttribute('data-font-card');
  assert.ok(roboto && literata);
  await bootDetail(page, `${url}#/font/${roboto}/?v=1&stem=font_hints_first`);
  assert.equal(await page.getByText('Automatic', { exact: true }).count(), 0);
  assert.equal(await page.getByRole('combobox', { name: 'Fitting', exact: true }).count(), 0);
  const toggle = page.getByRole('switch', { name: 'Use font hints', exact: true });
  assert.equal(await toggle.isChecked(), true);
  await page.waitForFunction(() => (window as any).__lastSpec?.pipeline.fitting === 'font_hints_auto');
  await toggle.focus();
  await page.keyboard.press('Space');
  await page.waitForFunction(() => (window as any).__lastSpec?.pipeline.fitting === 'upstream_mono');
  assert.equal(await hashParam(page,'stem'), 'upstream_mono');
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForFunction(canvasRendered);
  assert.equal(await toggle.isChecked(), false);
  await toggle.click();
  await page.locator('[data-save-variant]').click();
  await page.locator('[data-variant-name]').waitFor();
  await page.waitForFunction(canvasRendered);
  await toggle.waitFor();
  const fittingSection = page.getByRole('region', { name: 'Fitting', exact: true });
  assert.equal(await fittingSection.getByRole('heading', { name: 'Fitting', level: 3 }).count(), 1);
  for (const name of ['Rendering', 'Spacing']) {
    assert.equal(await fittingSection.evaluate((element, siblingName) =>
      Array.from(element.parentElement!.children).some((sibling) =>
        sibling !== element && sibling.querySelector('h3')?.textContent === siblingName), name), true);
  }
  assert.equal(await toggle.isChecked(), true);
  await toggle.click();
  await page.waitForFunction(() => document.querySelector('[data-save-status]')?.textContent === 'Saved');
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForFunction(canvasRendered);
  assert.equal(await toggle.isChecked(), false);
  await bootDetail(page, `${url}#/font/${literata}/?v=1`);
  assert.equal(await toggle.count(), 0);
  assert.equal(await page.getByText('Automatic', { exact: true }).count(), 0);
});

test("Mono previews follow font instructions with smart short-stroke fallback, including old links and variants", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.addInitScript(SPEC_SCRIPT);
  await bootLibrary(page, url);
  const ids = await cardIds(page);
  await bootDetail(page, `${url}#/font/${ids[0]}/?v=1&raster=coverage&dropout=off&stubs=0&scanfont=0&exact=0`);
  await assertControlLayers(page);
  assert.equal(await lastMonoRaster(page), JSON.stringify(fixedScan));
  for (const key of ["dropout", "stubs", "scanfont", "zoom"]) assert.equal(await hashParam(page, key), null);
  assert.equal(await hashParam(page, "raster"), "free_type_mono");
  const detailUrl = page.url();
  await createPalettePreset(page, url, { name: "Scan gray", bits: 3 });
  await bootDetail(page, detailUrl);
  await selectPalettePreset(page, "Scan gray");
  await page.waitForFunction(() => (window as unknown as { __lastMonoRaster: string }).__lastMonoRaster === "absent");
  await selectPalettePreset(page, "Monochrome");
  await page.waitForFunction(() => (window as unknown as { __lastMonoRaster: string }).__lastMonoRaster.includes('"font_instructions":true'));
  await page.locator("[data-save-variant]").click();
  await page.waitForFunction(() => document.querySelector("[data-variant-name]") !== null);
  await page.waitForFunction(canvasRendered);
  await assertControlLayers(page);
  assert.equal(await lastMonoRaster(page), JSON.stringify(fixedScan));
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(canvasRendered);
  assert.equal(await lastMonoRaster(page), JSON.stringify(fixedScan));
});

test("header zoom is global across routes and tabs, survives reload and never writes font settings or URLs", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await page.addInitScript(SPEC_SCRIPT);
  await bootLibrary(page, url);
  assert.equal(await page.locator("#zoom").getAttribute("data-value"), "2");
  assert.equal(await page.locator('aside #zoom').count(), 0);
  await setZoom(page, "3");
  await page.locator('#zoom input:checked').focus();
  await page.keyboard.press("ArrowRight");
  assert.equal(await page.locator("#zoom").getAttribute("data-value"), "4", "zoom supports arrow keys");
  await page.keyboard.press("ArrowLeft");
  const ids = await cardIds(page);
  await bootDetail(page, `${url}#/font/${ids[0]}/?v=1&zoom=1`);
  assert.equal(await page.locator("#zoom").getAttribute("data-value"), "3", "old links cannot change display preferences");
  assert.equal(await hashParam(page, "zoom"), null);
  const detailUrl = page.url();
  await setZoom(page, "4");
  assert.equal(page.url(), detailUrl);
  await page.locator('[data-primary-nav="fonts"]').click();
  await page.locator("[data-font-card]").first().waitFor();
  assert.equal(await page.locator("#zoom").getAttribute("data-value"), "4");
  await page.goBack();
  await page.waitForFunction(canvasRendered);
  assert.equal(await page.locator("#zoom").getAttribute("data-value"), "4", "Back does not restore old zoom");
  await page.locator('[data-primary-nav="fonts"]').click();
  await page.locator("[data-font-card]").first().waitFor();
  await openNewVariant(page, ids[0]!);
  await page.waitForFunction(canvasRendered);
  assert.equal(await page.locator("#zoom").getAttribute("data-value"), "4");
  const storedRows = () => page.evaluate(() => new Promise<string>((resolve, reject) => {
    const request = indexedDB.open("font-library");
    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      const db = request.result;
      const rows = db.transaction("variants").objectStore("variants").getAll();
      rows.onsuccess = () => { db.close(); resolve(JSON.stringify(rows.result)); };
      rows.onerror = () => { db.close(); reject(rows.error); };
    };
  }));
  const beforeRows = await storedRows();
  const variantUrl = page.url();
  const second = await context.newPage();
  await bootLibrary(second, url);
  assert.equal(await second.locator("#zoom").getAttribute("data-value"), "4");
  await setZoom(second, "3");
  await page.waitForFunction(() => document.querySelector("#zoom")?.getAttribute("data-value") === "3");
  await setZoom(page, "2");
  assert.equal(await page.locator("#zoom").getAttribute("data-value"), "2");
  assert.equal(page.url(), variantUrl);
  assert.equal(await storedRows(), beforeRows, "display changes never autosave a variant");
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(canvasRendered);
  assert.equal(await page.locator("#zoom").getAttribute("data-value"), "2");
  await context.close();
});
