import assert from "node:assert/strict";
import test from "node:test";
import type { Page } from "playwright-core";
import {
  bootLibrary, browserAvailable, buildApp, cardIds, cardNames, launch, openNewVariant, servePrefix,
} from "../helpers/spa-helpers.ts";

async function assertMetadata(page: Page, title: string, path?: string): Promise<void> {
  await page.waitForFunction((expected) => document.title === expected, title);
  assert.equal(await page.locator("head title").count(), 1);
  for (const selector of ['meta[name="description"]', 'meta[name="robots"]', 'meta[property="og:title"]', 'meta[property="og:description"]', 'meta[property="og:type"]', 'meta[property="og:site_name"]', 'meta[property="og:image"]', 'meta[property="og:image:alt"]', 'meta[name="twitter:card"]']) {
    assert.equal(await page.locator(`head ${selector}`).count(), 1, selector);
  }
  assert.equal(await page.locator('head meta[property="og:title"]').getAttribute("content"), title);
  assert.equal(await page.locator('head meta[property="og:type"]').getAttribute("content"), "website");
  assert.equal(await page.locator('head meta[property="og:site_name"]').getAttribute("content"), "Glypherie");
  assert.equal(await page.locator('head meta[property="og:image"]').getAttribute("content"), "https://example.test/preview/icons/icon-512.png");
  assert.equal(await page.locator('head meta[name="twitter:card"]').getAttribute("content"), "summary");
  const description = await page.locator('head meta[name="description"]').getAttribute("content");
  assert.ok(description);
  assert.equal(await page.locator('head meta[property="og:description"]').getAttribute("content"), description);
  assert.equal(await page.locator('head meta[name="robots"]').getAttribute("content"), path === undefined ? "noindex,follow" : "index,follow");
  assert.equal(await page.locator('head link[rel="canonical"]').count(), path === undefined ? 0 : 1);
  assert.equal(await page.locator('head meta[property="og:url"]').count(), path === undefined ? 0 : 1);
  if (path !== undefined) {
    assert.equal(await page.locator('head link[rel="canonical"]').getAttribute("href"), `https://example.test/preview/${path}`);
    assert.equal(await page.locator('head meta[property="og:url"]').getAttribute("content"), `https://example.test/preview/${path}`);
  }
  assert.equal(await page.locator("h1").count(), 1);
  assert.equal(await page.getByRole("banner").getByRole("heading", { level: 1 }).count(), 0, "brand is separate from the page heading");
}

test("metadata follows navigation, local drafts, reload and recovery without stale tags", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t, "/preview/", "https://example.test/preview/");
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ serviceWorkers: "block" });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));

  for (const [path, title] of [
    ["", "Glypherie — Bitmap fonts for low-resolution displays"],
    ["fonts/", "Font library — Glypherie"],
    ["palettes/", "Palettes — Glypherie"],
  ] as const) {
    const response = await fetch(`${url}${path}`);
    assert.equal(response.status, 200);
    const html = await response.text();
    assert.match(html, new RegExp(`<title data-page-metadata>${title}</title>`));
    assert.ok(html.includes(`href="https://example.test/preview/${path}"`));
    assert.ok(html.includes('property="og:image" content="https://example.test/preview/icons/icon-512.png"'));
    await page.goto(`${url}${path}`);
    await assertMetadata(page, title, path);
  }
  const image = await fetch(`${url}icons/icon-512.png`);
  assert.equal(image.status, 200);
  assert.equal(Buffer.from(await image.arrayBuffer()).subarray(1, 4).toString(), "PNG");

  await bootLibrary(page, url);
  const [id, otherId] = await cardIds(page);
  const [fontName] = await cardNames(page);
  assert.ok(id && otherId && fontName);
  const variantId = await openNewVariant(page, id);
  const variantPath = new URL(page.url()).pathname;
  const name = await page.locator("[data-variant-name]").inputValue();
  await assertMetadata(page, `${name} — ${fontName} — Glypherie`);
  const renamed = 'Metadata <variant> & "quoted"';
  await page.locator("[data-variant-name]").fill(renamed);
  await assertMetadata(page, `${renamed} — ${fontName} — Glypherie`);
  await page.waitForFunction(() => document.querySelector("[data-save-status]")?.textContent === "Saved");
  await page.locator("[data-text]").fill("Private specimen text must stay out of metadata");
  assert.equal(await page.locator("head").innerHTML().then((html) => html.includes("Private specimen text")), false);
  await page.reload();
  await assertMetadata(page, `${renamed} — ${fontName} — Glypherie`);

  await page.getByRole("link", { name: "Palettes", exact: true }).click();
  await assertMetadata(page, "Palettes — Glypherie", "palettes/");
  await page.goBack();
  await assertMetadata(page, `${renamed} — ${fontName} — Glypherie`);
  await page.goForward();
  await assertMetadata(page, "Palettes — Glypherie", "palettes/");

  await page.goto(`${url}font/${id}/?v=1`);
  await assertMetadata(page, `${fontName} — Preview — Glypherie`);
  assert.match(await page.locator('head meta[name="description"]').getAttribute("content") ?? "", /Configure bitmap font/);
  await page.goto(`${url}font/${id}/variant/missing/`);
  await assertMetadata(page, "Variant not found — Glypherie");
  await page.goto(`${url}font/${otherId}/variant/${variantId}/`);
  await assertMetadata(page, "Variant belongs to another font — Glypherie");

  await page.goto(new URL(variantPath, url).href);
  await assertMetadata(page, `${renamed} — ${fontName} — Glypherie`);
  await page.locator(`[data-delete-variant="${variantId}"]`).click();
  await assertMetadata(page, "Font library — Glypherie", "fonts/");
  await page.getByRole("link", { name: "Fonts", exact: true }).click();
  await assertMetadata(page, "Font library — Glypherie", "fonts/");
  await page.goto(`${url}missing-route/`);
  await page.locator("[data-route-notice]").waitFor();
  await assertMetadata(page, "Font library — Glypherie", "fonts/");

  const freshPage = await (await browser.newContext({ serviceWorkers: "block" })).newPage();
  await freshPage.goto(`${url}font/${id}/variant/${variantId}/`);
  await assertMetadata(freshPage, "Variant not found — Glypherie");
  assert.deepEqual(errors, []);
});
