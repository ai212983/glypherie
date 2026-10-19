import assert from "node:assert/strict";
import test from "node:test";
import {
  bootDetail,
  bootLibrary,
  browserAvailable,
  buildApp,
  canvasPixels,
  canvasRendered,
  cardIds,
  cardNames,
  cardVariantIds,
  hashLocation,
  hashParam,
  hashPath,
  launch,
  openNewVariant,
  servePrefix,
} from "../helpers/spa-helpers.ts";

const EXPECTED = [
  { pattern: /^Roboto Regular$/, license: "OFL-Roboto.txt", axes: ["wght", "wdth"] },
  { pattern: /^Roboto Italic$/, license: "OFL-Roboto.txt", axes: ["wght", "wdth"] },
  { pattern: /^Roboto Flex/, license: "OFL-RobotoFlex.txt", axes: ["wght", "GRAD"] },
  { pattern: /^Literata/, license: "OFL-Literata.txt", axes: ["opsz", "wght"] },
  { pattern: /^Source Sans 3/, license: "OFL-SourceSans3.txt", axes: ["wght"] },
];

test("bare root loads the catalog with five font cards and zero variants", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await bootLibrary(page, url);
  const names = await cardNames(page);
  assert.equal(names.length, 5);
  for (const expected of EXPECTED) {
    assert.ok(names.some((name) => expected.pattern.test(name)), `catalog names ${expected.pattern}`);
  }
  assert.deepEqual(await page.locator("[data-font-card]").count(), 5);
  assert.deepEqual(await page.locator("[data-variant-link]").count(), 0, "imported fonts start with no variants");
  assert.deepEqual(await page.locator("[data-add-variant]").count(), 5);
  assert.deepEqual(errors, []);
});

test("Add variant creates a default saved variant and navigates after commit", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const names = await cardNames(page);
  const ids = await cardIds(page);
  const target = names.findIndex((name) => /^Literata/.test(name));
  let reloaded = false;
  page.once("load", () => { reloaded = true; });
  const variantId = await openNewVariant(page, ids[target]!);
  await page.waitForFunction(
    (name) => document.querySelector(".family h2")?.textContent === name,
    names[target],
  );
  await page.waitForFunction(canvasRendered);
  assert.equal(await hashPath(page), `/font/${ids[target]}/variant/${variantId}/`);
  await page.waitForFunction(
    () => document.querySelector("[data-save-status]")?.textContent?.startsWith("Saved"),
    null,
    { timeout: 20000 },
  );
  await page.waitForTimeout(500);
  assert.equal(reloaded, false, "in-app navigation performs no document reload");
  await page.locator("[data-all-fonts]").click();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  assert.deepEqual(await cardVariantIds(page, ids[target]!), [variantId]);
});

for (const expected of EXPECTED) {
  test(`variant editor shows the font with its actual axes and real ink: ${expected.pattern}`, { skip: !browserAvailable }, async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    await bootLibrary(page, url);
    const names = await cardNames(page);
    const ids = await cardIds(page);
    const index = names.findIndex((name) => expected.pattern.test(name));
    assert.ok(index >= 0, `catalog has ${expected.pattern}`);
    const id = ids[index];
    assert.ok(id, "card carries its content id");
    const variantId = await openNewVariant(page, id!);
    await page.waitForFunction(
      (name) => document.querySelector(".family h2")?.textContent === name,
      names[index],
    );
    await page.waitForFunction(canvasRendered);
    const heading = await page.locator(".family h2").innerText();
    assert.equal(heading, names[index]);
    for (const axis of expected.axes) {
      assert.equal(
        await page.locator(`[data-axis="${axis}"]`).count(),
        1,
        `${heading} exposes the ${axis} axis`,
      );
    }
    const license = await page.locator("section.family a[href$='.txt']").allTextContents();
    assert.ok(license.includes(expected.license), `${heading} links ${expected.license}, got ${license}`);
    const first = await canvasPixels(page);
    assert.ok(first.width > 0 && first.height > 0);
    assert.ok(first.ink > 100, `expected rendered ink for ${heading}, got ${first.ink}`);
    const location = await hashLocation(page);
    assert.equal(location.path, `/font/${id}/variant/${variantId}/`);
    assert.equal(new URLSearchParams(location.search).get("v"), null, "saved settings live in the database, not the URL");
    assert.equal(new URL(page.url()).searchParams.get("font"), null, "no outer font query");
  });
}

test("direct first load into each legacy font route shows its unsaved preview", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const probe = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(probe, url);
  const names = await cardNames(probe);
  const ids = await cardIds(probe);
  await probe.close();
  for (const [index, id] of ids.entries()) {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    await bootDetail(page, `${url}#/font/${id}/`);
    assert.equal(await page.locator(".family h2").innerText(), names[index]);
    assert.equal(await page.locator("[data-unsaved-preview]").count(), 1, "legacy routes stay unsaved previews");
    const first = await canvasPixels(page);
    assert.ok(first.ink > 100, `expected rendered ink for ${names[index]}`);
    await page.close();
  }
});

test("legacy query and fragment links migrate to the canonical hash route", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bootLibrary(page, url);
  const names = await cardNames(page);
  const ids = await cardIds(page);
  const literata = names.findIndex((name) => /^Literata/.test(name));
  await bootDetail(page, `${url}?font=${ids[literata]}&profile=gray_3bit`);
  assert.equal(await page.locator(".family h2").innerText(), names[literata]);
  assert.equal(await hashPath(page), `/font/${ids[literata]}/`);
  assert.equal(await hashParam(page, "profile"), "gray_3bit", "legacy profile survives migration");
  assert.equal(new URL(page.url()).searchParams.get("font"), null, "outer font query is cleared");

  await page.goto(`${url}#family-${ids[literata]}`, { waitUntil: "networkidle" });
  await page.waitForFunction(
    (name) => document.querySelector(".family h2")?.textContent === name,
    names[literata],
  );
  assert.equal(await hashPath(page), `/font/${ids[literata]}/`);
});
