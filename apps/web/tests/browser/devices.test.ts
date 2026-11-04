// Device previews in the current font editor: selector, shell integration,
// fixed native framebuffers, scale modes, persistence and unknown recovery.
import assert from "node:assert/strict";
import test from "node:test";
import {
  bootLibrary,
  browserAvailable,
  buildApp,
  canvasRendered,
  cardIds,
  launch,
  openNewVariant,
  servePrefix,
} from "../helpers/spa-helpers.ts";

const DEVICES = [
  { id: "xteink-x4", label: "Xteink X4", width: 480, height: 800, ppi: 220 },
  { id: "xteink-x3", label: "Xteink X3", width: 528, height: 792, ppi: 259 },
  { id: "inkplate-4-tempera", label: "Inkplate 4 TEMPERA", width: 600, height: 600, ppi: 223.3 },
  { id: "waveshare-esp32-s3-rlcd-4-2", label: "Waveshare ESP32-S3-RLCD-4.2", width: 400, height: 300, ppi: 119.8 },
  { id: "playdate", label: "Playdate", width: 400, height: 240, ppi: 173 },
  { id: "boox-picco", label: "BOOX Picco", width: 480, height: 800, ppi: 235 },
] as const;

test("device selector renders shelled fixed-framebuffer previews", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);
  const id = (await cardIds(page))[0]!;
  await page.goto(`${url}font/${id}/?v=1`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(canvasRendered);
  assert.equal(await page.locator("[data-device-preview]").count(), 0, "specimen stays the default");

  for (const device of DEVICES) {
    await page.getByRole("combobox", { name: "Device" }).click();
    await page.getByRole("option", { name: device.label, exact: true }).click();
    const preview = page.locator(`[data-device-preview="${device.id}"]`);
    await preview.waitFor();
    await page.waitForFunction(
      (deviceId) => (document.querySelector(`[data-device-preview="${deviceId}"] canvas`) as HTMLElement | null)
        ?.dataset.rendered === "true",
      device.id,
      { timeout: 20000 },
    );
    const geometry = await preview.evaluate((element) => {
      const canvas = element.querySelector("canvas") as HTMLCanvasElement | null;
      const shell = element.querySelector("img[data-device-shell]") as HTMLImageElement | null;
      if (!canvas || !shell) throw new Error("Device preview is missing its screen or shell.");
      // The viewport slot spans the full fixed framebuffer; the canvas inside
      // holds only the shown rows.
      const screenBox = (canvas.parentElement as HTMLElement).getBoundingClientRect();
      return {
        nativeWidth: element.getAttribute("data-native-width"),
        nativeHeight: element.getAttribute("data-native-height"),
        backingWidth: canvas.width,
        backingHeight: canvas.height,
        styleWidth: canvas.style.width,
        shellComplete: shell.complete,
        shellWidth: shell.naturalWidth,
        screenAspect: screenBox.width / screenBox.height,
        shellWider: shell.getBoundingClientRect().width > screenBox.width,
      };
    });
    assert.equal(geometry.nativeWidth, String(device.width));
    assert.equal(geometry.nativeHeight, String(device.height));
    assert.equal(geometry.backingWidth % device.width, 0, "backing is an integer multiple of the framebuffer");
    assert.ok(geometry.backingHeight > 0 && geometry.backingHeight <= device.height,
      "backing holds the shown rows within the fixed framebuffer");
    const expectedStyleWidth = (device.width * 96) / device.ppi;
    assert.ok(Math.abs(parseFloat(geometry.styleWidth) - expectedStyleWidth) < 1,
      `actual-size width follows 96/ppi (saw ${geometry.styleWidth})`);
    assert.ok(geometry.shellComplete && geometry.shellWidth > 0, "vector shell artwork loads");
    assert.ok(geometry.shellWider, "shell surrounds the screen");
    assert.ok(
      Math.abs(geometry.screenAspect / (device.width / device.height) - 1) < 0.02,
      "screen keeps the native aspect",
    );
    assert.match(geometry.styleWidth, /px$/, "screen has a CSS presentation size");
  }

  // Scale modes: Actual size uses the unmeasured 96 reference; Pixel 1:1 is exact.
  await page.getByRole("combobox", { name: "Device" }).click();
  await page.getByRole("option", { name: "Xteink X4", exact: true }).click();
  await page.locator('[data-device-preview="xteink-x4"]').waitFor();
  assert.equal(await page.locator("[data-calibration-ruler]").count(), 0);
  await page.getByRole("radio", { name: "Pixel 1:1" }).click();
  const dpr = await page.evaluate(() => window.devicePixelRatio);
  await page.waitForFunction(
    (expected) => {
      const canvas = document.querySelector('[data-device-preview="xteink-x4"] canvas') as HTMLCanvasElement | null;
      return canvas !== null && Math.abs(parseFloat(canvas.style.width) - expected) < 1;
    },
    480 / dpr,
    { timeout: 20000 },
  );
  const oneToOneWidth = await page.locator('[data-device-preview="xteink-x4"] canvas').evaluate(
    (canvas) => parseFloat(canvas.style.width),
  );
  assert.ok(Math.abs(oneToOneWidth - 480 / dpr) < 1, `1:1 maps one device pixel per monitor pixel (saw ${oneToOneWidth})`);
  await page.getByRole("radio", { name: "Actual size" }).click();

  // The selection persists as viewing state, not font state.
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(canvasRendered);
  await page.locator('[data-device-preview="xteink-x4"]').waitFor({ timeout: 20000 });

  // Unknown stored devices recover to the specimen with a notice, and any
  // legacy calibration is dropped while the unknown id stays for the notice.
  await page.evaluate(() => window.localStorage.setItem(
    "font-preview.device",
    JSON.stringify({ device: "paperwhite", scale: "actual", calibration: 96 }),
  ));
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(canvasRendered);
  assert.equal(await page.locator("[data-device-preview]").count(), 0);
  await page.locator("[data-unknown-device]").waitFor();
  assert.deepEqual(
    await page.evaluate(() => JSON.parse(window.localStorage.getItem("font-preview.device") ?? "null")),
    { device: "paperwhite", scale: "actual" },
  );
  assert.deepEqual(errors, []);
});

test("device previews work on the saved variant route without touching settings", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);
  const id = (await cardIds(page))[0]!;
  await openNewVariant(page, id);
  await page.waitForFunction(canvasRendered);
  const nameBefore = await page.locator("[data-variant-name]").inputValue();
  await page.waitForFunction(
    () => document.querySelector("[data-save-status]")?.textContent?.startsWith("Saved"),
    null,
    { timeout: 20000 },
  );

  await page.getByRole("combobox", { name: "Device" }).click();
  await page.getByRole("option", { name: "Inkplate 4 TEMPERA", exact: true }).click();
  const preview = page.locator('[data-device-preview="inkplate-4-tempera"]');
  await preview.waitFor();
  await page.waitForFunction(
    (deviceId) => (document.querySelector(`[data-device-preview="${deviceId}"] canvas`) as HTMLElement | null)
      ?.dataset.rendered === "true",
    "inkplate-4-tempera",
    { timeout: 20000 },
  );
  const geometry = await preview.evaluate((element) => {
    const canvas = element.querySelector("canvas") as HTMLCanvasElement | null;
    const shell = element.querySelector("img[data-device-shell]") as HTMLImageElement | null;
    if (!canvas || !shell) throw new Error("Device preview is missing its screen or shell.");
    const screenBox = (canvas.parentElement as HTMLElement).getBoundingClientRect();
    return {
      nativeWidth: element.getAttribute("data-native-width"),
      nativeHeight: element.getAttribute("data-native-height"),
      backingWidth: canvas.width,
      styleWidth: canvas.style.width,
      shellComplete: shell.complete,
      shellWidth: shell.naturalWidth,
      screenAspect: screenBox.width / screenBox.height,
      shellWider: shell.getBoundingClientRect().width > screenBox.width,
    };
  });
  assert.equal(geometry.nativeWidth, "600");
  assert.equal(geometry.nativeHeight, "600");
  assert.equal(geometry.backingWidth % 600, 0, "backing is an integer multiple of the framebuffer");
  const expectedStyleWidth = (600 * 96) / 223.3;
  assert.ok(Math.abs(parseFloat(geometry.styleWidth) - expectedStyleWidth) < 1,
    `actual-size width follows 96/ppi (saw ${geometry.styleWidth})`);
  assert.ok(geometry.shellComplete && geometry.shellWidth > 0, "vector shell artwork loads");
  assert.ok(geometry.shellWider, "shell surrounds the screen");
  assert.ok(Math.abs(geometry.screenAspect / 1 - 1) < 0.02, "screen keeps the square native aspect");

  // Device choice is viewer state: the saved settings stay untouched.
  assert.equal(await page.locator("[data-variant-name]").inputValue(), nameBefore,
    "device selection leaves the saved name alone");
  assert.ok((await page.locator("[data-save-status]").textContent() ?? "").startsWith("Saved"),
    "device selection triggers no variant save");

  // The selection persists across reload on the saved route too.
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(canvasRendered);
  await page.locator('[data-device-preview="inkplate-4-tempera"]').waitFor({ timeout: 20000 });
  assert.equal(await page.locator("[data-variant-name]").inputValue(), nameBefore);
  assert.deepEqual(errors, []);
});
