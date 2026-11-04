import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import test from "node:test";
import { bootLibrary, bootDetail, browserAvailable, buildApp, cardIds, cardNames, launch,
  openNewVariant, servePrefix, createPalettePreset, selectPalettePreset } from "../helpers/spa-helpers.ts";

test("Playdate downloads run through the real worker, include kerning, and recover from export errors", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage();
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await bootLibrary(page, url);
  const names = await cardNames(page);
  const ids = await cardIds(page);
  const index = names.findIndex((n) => /^Roboto Flex/.test(n));
  assert.ok(index >= 0);
  const id = ids[index]!;
  await bootDetail(page, `${url}#/font/${id}/`);
  const button = page.locator("[data-export-playdate]");
  // The default export is full printable ASCII, including the left-overhanging j.
  await button.waitFor({ state: "visible" });
  const count = page.locator("[data-coverage-count]");
  assert.match(await count.innerText(), /95 characters/);
  assert.equal(await page.locator("[data-coverage-missing]").count(), 0);
  // A custom range extends the structured coverage; controls are rejected.
  await page.locator("[data-coverage-custom]").fill("(0x00E9-0x00E9)");
  await page.locator("[data-coverage-add]").click();
  assert.match(await count.innerText(), /96 characters/);
  await page.locator("[data-coverage-remove='0']").click();
  assert.match(await count.innerText(), /95 characters/);
  const downloadEvent = page.waitForEvent("download");
  await button.click();
  const download = await downloadEvent;
  assert.match(download.suggestedFilename(), /\.fnt$/);
  const file = path.join(output, "download.fnt");
  await download.saveAs(file);
  const fnt = await fs.readFile(file, "utf8");
  assert.match(fnt, /^data=iVBOR/m);
  assert.match(fnt, /^U\+006A\t/m);
  assert.match(fnt, /^U\+0041U\+0056\t-\d+/m);
  const data = /^data=(.+)$/m.exec(fnt)![1]!;
  const length = Number(/^datalen=(\d+)$/m.exec(fnt)![1]);
  assert.equal(data.length, length);
  assert.equal(Buffer.from(data, "base64").subarray(1, 4).toString(), "PNG");
  // Control scalars stay outside the export subset with an explicit error. U+000D is a
  // control Roboto Flex actually covers (cmap gid 1), so the availability preflight keeps
  // it and the export window rejects it; U+000A is merely missing from this font.
  await page.locator("[data-coverage-custom]").fill("(0x000D-0x000D)");
  await page.locator("[data-coverage-add]").click();
  await button.click();
  await page.locator("[data-export-error]").waitFor();
  assert.match(await page.locator("[data-export-error]").innerText(), /outside the Playdate/);
  await page.locator("[data-coverage-remove='0']").click();
  // Empty coverage disables the export.
  await page.locator("[data-coverage-preset='ascii']").click();
  assert.match(await count.innerText(), /0 characters/);
  assert.equal(await button.isDisabled(), true);
  await page.locator("[data-coverage-preset='ascii']").click();
  // Saved variants use the same export surface and honor their current settings.
  await page.goto(`${url}fonts/`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  await openNewVariant(page, id);
  const variantDownload = page.waitForEvent("download");
  await page.locator("[data-export-playdate]").click();
  assert.match((await variantDownload).suggestedFilename(), /\.fnt$/);
  const variantUrl = page.url();
  await createPalettePreset(page, url, { name: "Export gray", bits: 3 });
  await page.goto(variantUrl, { waitUntil: "domcontentloaded" });
  await selectPalettePreset(page, "Export gray");
  assert.equal(await page.locator("[data-export-playdate]").isDisabled(), true);
  assert.deepEqual(errors, []);
});
