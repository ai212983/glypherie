import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import test from "node:test";
import {
  bootLibrary,
  browserAvailable,
  buildApp,
  canvasRendered,
  cardIds,
  cardNames,
  fontDir,
  hashPath,
  launch,
  mutatedUploadBytes,
  openNewVariant,
  servePrefix,
} from "../helpers/spa-helpers.ts";

test("uploads matching bundled bytes dedup instead of duplicating cards", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await bootLibrary(page, url);

  for (const [file, name] of [["SourceSans3.ttf", "Source Sans 3"], ["Roboto-Italic.ttf", "Roboto Italic"]] as const) {
    await page.locator("[data-import-font]").setInputFiles(path.join(fontDir, file));
    await page.waitForFunction(
      (expected) => document.querySelector("[data-import-status]")?.textContent?.includes(expected),
      `Imported ${name}.`,
    );
    const status = await page.locator("[data-import-status]").textContent();
    assert.match(status ?? "", /Imported/, `${file} announces success on the library`);
    assert.equal(await page.locator("[data-font-card]").count(), 5, `${file} dedups against its bundled twin`);
    assert.equal(await page.locator("[data-variant-editor]").count(), 0, "import creates no variant");
  }

  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  assert.equal((await cardNames(page)).length, 5, "dedup survives reload");
  await context.close();
});

test("new uploads appear in the library, persist, and delete cleanly", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await bootLibrary(page, url);
  const before = await cardNames(page);

  const upload = path.join(output, "RobotX.ttf");
  await fs.writeFile(upload, await mutatedUploadBytes(path.join(fontDir, "Roboto.ttf")));
  await page.locator("[data-import-font]").setInputFiles(upload);
  await page.waitForFunction(
    () => document.querySelector("[data-import-status]")?.textContent?.includes("Imported"),
    null,
    { timeout: 20000 },
  );
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length === 6);
  const names = await cardNames(page);
  assert.ok(names.some((name) => /RobotX/.test(name)), "imported font appears in the library");
  assert.match(await page.locator("[data-import-status]").textContent() ?? "", /Imported RobotX/);

  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length === 6);
  assert.deepEqual(await cardNames(page), names, "upload survives reload");

  const robotX = names.findIndex((name) => /RobotX/.test(name));
  const robotXId = (await cardIds(page))[robotX]!;
  const variantId = await openNewVariant(page, robotXId);
  await page.waitForFunction(canvasRendered);
  assert.equal(await hashPath(page), `/font/${robotXId}/variant/${variantId}/`);
  await page.locator('[data-primary-nav="fonts"]').click();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length === 6);

  await page.locator(`[data-delete-font="${robotXId}"]`).click();
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length === 5);
  assert.deepEqual(await cardNames(page), before, "deletion returns the library to five fonts");
  assert.equal(await hashPath(page), "/", "delete returns to the library route");

  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  assert.deepEqual(await cardNames(page), before, "deletion survives reload");
  await context.close();
});

test("invalid font uploads are rejected and never stored", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await bootLibrary(page, url);

  const invalid = path.join(output, "invalid.ttf");
  await fs.writeFile(invalid, Buffer.from("not a font at all"));
  await page.locator("[data-import-font]").setInputFiles(invalid);
  await page.waitForFunction(() => (document.body.textContent ?? "").includes("Couldn’t import"));
  assert.equal(await page.locator("[data-font-card]").count(), 5);

  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
  assert.equal(await page.locator("[data-font-card]").count(), 5, "invalid font was not stored");
  assert.deepEqual(errors, []);
  await context.close();
});

test("multiple selected fonts import and persist even when one file is invalid", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await bootLibrary(page, url);

  const importCard = page.locator('aside [data-slot="card"]').filter({
    has: page.getByRole("heading", { name: /import fonts/i }),
  });
  assert.equal(await importCard.locator("[data-import-font]").count(), 1, "picker lives in the import card");
  assert.equal(await page.locator("[data-import-font]").evaluate((element) => (element as HTMLInputElement).multiple), true);

  const regular = path.join(output, "RobotX.ttf");
  const invalid = path.join(output, "invalid.ttf");
  const italic = path.join(output, "RobotX-Italic.ttf");
  await Promise.all([
    fs.writeFile(regular, await mutatedUploadBytes(path.join(fontDir, "Roboto.ttf"))),
    fs.writeFile(invalid, Buffer.from("not a font at all")),
    fs.writeFile(italic, await mutatedUploadBytes(path.join(fontDir, "Roboto-Italic.ttf"))),
  ]);
  await page.locator("[data-import-font]").setInputFiles([regular, invalid, italic]);
  await page.waitForFunction(() => {
    const status = document.querySelector("[data-import-status]")?.textContent ?? "";
    return status.includes("Imported RobotX") && status.includes("Couldn’t import invalid.ttf")
      && status.includes("Imported RobotX Italic.");
  });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length === 7);
  const names = await cardNames(page);
  assert.equal(names.filter((name) => /RobotX/.test(name)).length, 2);
  assert.equal(await page.locator("[data-import-font]").inputValue(), "", "selection clears for reuse");
  assert.equal(await page.locator("[data-variant-editor]").count(), 0, "imports stay on the library");

  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length === 7);
  assert.deepEqual(await cardNames(page), names, "both successful imports survive reload");
  await context.close();
});
