// cspell:words Xteink Picco BOOX boox
// Standalone Screen page: the implicit default composition opens a real
// catalog device, dropdown switching across the whole catalog,
// shell/aperture geometry, and direct-load/reload/history navigation.
import assert from "node:assert/strict";
import test from "node:test";
import {
  bootLibrary,
  browserAvailable,
  buildApp,
  cardIds,
  hashParam,
  hashPath,
  launch,
  servePrefix,
} from "../helpers/spa-helpers.ts";

const DEVICES = [
  { id: "xteink-x4", label: "Xteink X4", width: 480, height: 800 },
  { id: "xteink-x3", label: "Xteink X3", width: 528, height: 792 },
  { id: "inkplate-4-tempera", label: "Inkplate 4 TEMPERA", width: 600, height: 600 },
  { id: "waveshare-esp32-s3-rlcd-4-2", label: "Waveshare ESP32-S3-RLCD-4.2", width: 400, height: 300 },
  { id: "playdate", label: "Playdate", width: 400, height: 240 },
  { id: "boox-picco", label: "BOOX Picco", width: 480, height: 800 },
] as const;

async function screenReady(page: Parameters<typeof hashPath>[0]): Promise<void> {
  await page.waitForFunction(() => document.querySelector("[data-screen-page]") !== null);
}

async function shellGeometry(page: Parameters<typeof hashPath>[0], id: string) {
  return page.evaluate((deviceId) => {
    const preview = document.querySelector(`[data-device-preview="${deviceId}"]`);
    const paper = document.querySelector("[data-screen-aperture]");
    const shell = document.querySelector(`img[data-device-shell="${deviceId}"]`);
    if (!(preview instanceof HTMLElement) || !(paper instanceof HTMLElement) || !(shell instanceof HTMLImageElement)) {
      throw new Error("Screen workspace is missing its aperture or shell.");
    }
    const paperBox = paper.getBoundingClientRect();
    return {
      nativeWidth: preview.getAttribute("data-native-width"),
      nativeHeight: preview.getAttribute("data-native-height"),
      shellComplete: shell.complete,
      shellWidth: shell.naturalWidth,
      paperAspect: paperBox.width / paperBox.height,
      shellWider: shell.getBoundingClientRect().width > paperBox.width,
      paperVisible: paperBox.width > 0 && paperBox.height > 0,
    };
  }, id);
}

test("screen default opens a real device and switches across the catalog", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await bootLibrary(page, url);

  // The default composition opens on a real catalog device regardless of
  // library contents: no empty state stands between Screen and the editor.
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Screen" }).click();
  await screenReady(page);
  assert.equal(await hashPath(page), "/screen/");

  // A real catalog device shows by default, never the responsive specimen.
  const first = DEVICES[0]!;
  await page.locator(`[data-device-preview="${first.id}"]`).waitFor();
  assert.equal(await page.locator("[data-device-preview]").count(), 1);

  await page.getByRole("combobox", { name: "Device" }).click();
  assert.equal(await page.getByRole("option", { name: "Responsive specimen" }).count(), 0);
  for (const device of DEVICES) {
    assert.equal(await page.getByRole("option", { name: device.label, exact: true }).count(), 1);
  }
  await page.keyboard.press("Escape");

  for (const device of DEVICES) {
    await page.getByRole("combobox", { name: "Device" }).click();
    await page.getByRole("option", { name: device.label, exact: true }).click();
    await page.locator(`[data-device-preview="${device.id}"]`).waitFor();
    await page.waitForFunction(
      (deviceId) => {
        const shell = document.querySelector(`img[data-device-shell="${deviceId}"]`);
        return shell instanceof HTMLImageElement && shell.complete && shell.naturalWidth > 0;
      },
      device.id,
      { timeout: 20000 },
    );
    assert.equal(await page.locator("[data-device-preview]").count(), 1, "one device shows at a time");
    const geometry = await shellGeometry(page, device.id);
    assert.equal(geometry.nativeWidth, String(device.width));
    assert.equal(geometry.nativeHeight, String(device.height));
    assert.ok(geometry.paperVisible, "paper screen has a presentation size");
    assert.ok(geometry.shellComplete && geometry.shellWidth > 0, "vector shell artwork loads");
    assert.ok(geometry.shellWider, "shell surrounds the screen");
    assert.ok(
      Math.abs(geometry.paperAspect / (device.width / device.height) - 1) < 0.02,
      `${device.id} aperture keeps the native aspect`,
    );
    const meta = await page.locator("[data-screen-device-meta]").textContent();
    assert.ok(meta?.includes(`${device.width} × ${device.height} px`), `readout names the frame, got: ${meta}`);
  }
  assert.deepEqual(errors, []);
});

test(
  "screen stays compact with sparse display details and drops stored calibration",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    t.after(() => context.close());
    const page = await context.newPage();
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    t.after(() => page.close());

    // Seed a legacy calibration before first paint; later writes stay intact.
    await page.addInitScript(() => {
      if (window.localStorage.getItem("font-preview.device") === null) {
        window.localStorage.setItem(
          "font-preview.device",
          JSON.stringify({ device: null, scale: "actual", calibration: 120 }),
        );
      }
    });
    await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
    await screenReady(page);
    await page.locator('[data-device-preview="xteink-x4"]').waitFor();

    // Paper follows the unmeasured 96 reference over PPI.
    const paper = await page.evaluate(() => {
      const element = document.querySelector("[data-screen-aperture]");
      if (!(element instanceof HTMLElement)) throw new Error("Screen workspace is missing its aperture.");
      const box = element.getBoundingClientRect();
      return { width: box.width, height: box.height };
    });
    assert.ok(Math.abs(paper.width - (480 * 96) / 220) < 1, `paper width follows 96/ppi (saw ${paper.width})`);
    assert.ok(Math.abs(paper.height - (800 * 96) / 220) < 1, `paper height follows 96/ppi (saw ${paper.height})`);

    // No calibration slider or ruler remains.
    assert.equal(await page.locator("[data-device-calibration]").count(), 0);
    assert.equal(await page.locator("[data-calibration-ruler]").count(), 0);
    assert.equal(await page.locator("[data-calibration-value]").count(), 0);

    // Display details stay closed without a separate approximate-size note.
    assert.equal(await page.locator("[data-screen-approximate]").count(), 0);
    assert.equal(
      await page.evaluate(
        () => (document.querySelector("details[data-monitor-info]") as HTMLDetailsElement | null)?.open ?? null,
      ),
      false,
      "display details start closed",
    );
    assert.equal(await page.locator("[data-monitor-screen]").isVisible(), false);
    assert.equal(await page.locator("[data-monitor-dpr]").isVisible(), false);
    assert.equal(await page.locator("[data-screen-size]").isVisible(), false);

    // Removed debug fields never render, open or closed.
    for (const selector of [
      "[data-monitor-available]",
      "[data-monitor-viewport]",
      "[data-monitor-pinch]",
      "[data-monitor-backing]",
      "[data-monitor-physical]",
      "[data-monitor-reference]",
    ]) {
      assert.equal(await page.locator(selector).count(), 0, `${selector} is gone`);
    }

    // Keyboard opens the disclosure; it exposes screen size, DPR, and the preview size control.
    await page.locator("details[data-monitor-info] > summary").focus();
    await page.keyboard.press("Enter");
    await page.locator("[data-monitor-dpr]").waitFor();
    assert.equal(
      await page.evaluate(
        () => (document.querySelector("details[data-monitor-info]") as HTMLDetailsElement | null)?.open ?? null,
      ),
      true,
      "display details open from the keyboard",
    );
    const metrics = await page.evaluate(() => {
      const text = (selector: string): string | null => document.querySelector(selector)?.textContent ?? null;
      return {
        dpr: window.devicePixelRatio,
        screen: [window.screen.width, window.screen.height],
        screenText: text("[data-monitor-screen]"),
        dprText: text("[data-monitor-dpr]"),
        fieldCount: document.querySelectorAll(
          "details[data-monitor-info] [data-monitor-screen], details[data-monitor-info] [data-monitor-dpr]",
        ).length,
      };
    });
    assert.equal(metrics.fieldCount, 2, "disclosure holds exactly two fields");
    assert.ok(
      metrics.screenText?.includes(`${metrics.screen[0]} × ${metrics.screen[1]} CSS px`),
      `screen area in CSS px, got: ${metrics.screenText}`,
    );
    assert.ok(metrics.dprText?.includes(String(metrics.dpr)), `live DPR, got: ${metrics.dprText}`);

    // The legacy calibration is cleaned; device/scale survive untouched.
    assert.deepEqual(
      await page.evaluate(() => JSON.parse(window.localStorage.getItem("font-preview.device") ?? "null")),
      { device: null, scale: "actual" },
    );

    // The workspace device selector writes the default composition's device,
    // never the legacy local preference: the editor owns device state now.
    await page.getByRole("combobox", { name: "Device" }).click();
    await page.getByRole("option", { name: "Inkplate 4 TEMPERA", exact: true }).click();
    await page.locator('[data-device-preview="inkplate-4-tempera"]').waitFor();
    assert.deepEqual(
      await page.evaluate(() => JSON.parse(window.localStorage.getItem("font-preview.device") ?? "null")),
      { device: null, scale: "actual" },
    );
    await page.reload({ waitUntil: "domcontentloaded" });
    await screenReady(page);
    await page.locator('[data-device-preview="inkplate-4-tempera"]').waitFor();

    // Reload keeps the cleaned state and the closed disclosure without a note.
    await page.reload({ waitUntil: "domcontentloaded" });
    await screenReady(page);
    await page.locator("details[data-monitor-info]").waitFor();
    assert.equal(await page.locator("[data-screen-approximate]").count(), 0);
    assert.equal(
      await page.evaluate(
        () => (document.querySelector("details[data-monitor-info]") as HTMLDetailsElement | null)?.open ?? null,
      ),
      false,
      "display details stay closed after reload",
    );
    assert.deepEqual(
      await page.evaluate(() => JSON.parse(window.localStorage.getItem("font-preview.device") ?? "null")),
      { device: null, scale: "actual" },
    );

    // A non-1 DPR browser reports its live ratio.
    const scaled = await context.newPage();
    t.after(() => scaled.close());
    await scaled.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
    await screenReady(scaled);
    await scaled.locator("details[data-monitor-info] > summary").click();
    await scaled.evaluate(() => {
      Object.defineProperty(window, "devicePixelRatio", { configurable: true, get: () => 2 });
      window.dispatchEvent(new Event("resize"));
    });
    await scaled.waitForFunction(
      () => document.querySelector("[data-monitor-dpr]")?.textContent?.includes("2") ?? false,
      null,
      { timeout: 20000 },
    );
    assert.deepEqual(errors, []);
  },
);

test(
  "screen preview size slider scales shell and aperture, persists, and resets",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    t.after(() => context.close());
    const page = await context.newPage();
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    t.after(() => page.close());
    await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
    await screenReady(page);
    await page.locator('[data-device-preview="xteink-x4"]').waitFor();

    const paperWidth = (): Promise<number> =>
      page.evaluate(() => {
        const element = document.querySelector("[data-screen-aperture]");
        if (!(element instanceof HTMLElement)) throw new Error("Screen workspace is missing its aperture.");
        return element.getBoundingClientRect().width;
      });
    const shellWidth = (): Promise<number> =>
      page.evaluate(() => {
        const element = document.querySelector('img[data-device-shell="xteink-x4"]');
        if (!(element instanceof HTMLImageElement)) throw new Error("Screen workspace is missing its shell.");
        return element.getBoundingClientRect().width;
      });

    // Keyboard opens the disclosure; the size control starts at 100%.
    await page.locator("details[data-monitor-info] > summary").focus();
    await page.keyboard.press("Enter");
    await page.locator("[data-screen-size]").waitFor();
    assert.equal(await page.locator("[data-screen-size-value]").textContent(), "100%");
    const basePaper = await paperWidth();
    const baseShell = await shellWidth();
    assert.ok(Math.abs(basePaper - (480 * 96) / 220) < 1, `paper starts at 96/ppi (saw ${basePaper})`);

    // Keyboard End jumps to the 150% stop; body and paper scale together.
    await page.locator('[data-screen-size] [role="slider"]').focus();
    await page.keyboard.press("End");
    await page.waitForFunction(() => document.querySelector("[data-screen-size-value]")?.textContent === "150%");
    assert.equal(await page.evaluate(() => window.localStorage.getItem("font-preview.screen.size")), "150");
    const grownPaper = await paperWidth();
    const grownShell = await shellWidth();
    assert.ok(Math.abs(grownPaper / basePaper - 1.5) < 0.02, `paper scales by 1.5 (saw ${grownPaper / basePaper})`);
    assert.ok(
      Math.abs(grownShell / baseShell - 1.5) < 0.02,
      `shell scales with the paper (saw ${grownShell / baseShell})`,
    );

    // Arrow steps move a single percent.
    await page.keyboard.press("ArrowLeft");
    await page.waitForFunction(() => document.querySelector("[data-screen-size-value]")?.textContent === "149%");
    assert.ok(Math.abs((await paperWidth()) / basePaper - 1.49) < 0.02, "one arrow step is one percent");

    // Reset returns to 100% and persists the default.
    await page.locator("[data-screen-size-reset]").click();
    await page.waitForFunction(() => document.querySelector("[data-screen-size-value]")?.textContent === "100%");
    assert.equal(await page.evaluate(() => window.localStorage.getItem("font-preview.screen.size")), "100");
    assert.ok(Math.abs((await paperWidth()) - basePaper) < 1, "reset restores the reference size");

    // Device switching keeps the chosen size; the editor preference stays untouched.
    await page.locator('[data-screen-size] [role="slider"]').focus();
    await page.keyboard.press("End");
    await page.waitForFunction(() => document.querySelector("[data-screen-size-value]")?.textContent === "150%");
    await page.getByRole("combobox", { name: "Device" }).click();
    await page.getByRole("option", { name: "Inkplate 4 TEMPERA", exact: true }).click();
    await page.locator('[data-device-preview="inkplate-4-tempera"]').waitFor();
    assert.equal(await page.locator("[data-screen-size-value]").textContent(), "150%");
    const temperaPaper = await paperWidth();
    await page.locator("[data-screen-size-reset]").click();
    await page.waitForFunction(() => document.querySelector("[data-screen-size-value]")?.textContent === "100%");
    const temperaBase = await paperWidth();
    assert.ok(
      Math.abs(temperaPaper / temperaBase - 1.5) < 0.02,
      `switched device keeps the 150% size (saw ${temperaPaper / temperaBase})`,
    );
    assert.equal(await page.evaluate(() => window.localStorage.getItem("font-preview.device")), null);
    await page.locator('[data-screen-size] [role="slider"]').focus();
    await page.keyboard.press("End");
    await page.waitForFunction(() => document.querySelector("[data-screen-size-value]")?.textContent === "150%");

    // Reload and route visits restore the persisted size.
    await page.reload({ waitUntil: "domcontentloaded" });
    await screenReady(page);
    await page.locator("details[data-monitor-info] > summary").click();
    assert.equal(await page.locator("[data-screen-size-value]").textContent(), "150%");
    await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Fonts" }).click();
    await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
    await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Screen" }).click();
    await screenReady(page);
    await page.locator("details[data-monitor-info] > summary").click();
    assert.equal(await page.locator("[data-screen-size-value]").textContent(), "150%");

    // The widest stop never widens the page at mobile width.
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      true,
      "150% preview never widens the page at mobile width",
    );
    assert.deepEqual(errors, []);
  },
);

test("screen ruler follows the preview size percentage", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  t.after(() => context.close());
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => page.close());
  await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
  await screenReady(page);
  await page.locator('[data-device-preview="xteink-x4"]').waitFor();

  // Ruler lives inside the closed disclosure, so it starts hidden.
  assert.equal(await page.locator("[data-screen-ruler]").isVisible(), false);
  await page.locator("details[data-monitor-info] > summary").click();
  await page.locator("[data-screen-ruler]").waitFor();
  assert.equal(await page.locator("[data-screen-size-value]").textContent(), "100%");

  // Eleven ticks at every 5 mm, major 10 mm ticks numbered.
  assert.equal(await page.locator("[data-screen-ruler-tick]").count(), 11);
  assert.equal(await page.locator("[data-screen-ruler] text").count(), 6);
  const rulerText = await page.locator("[data-screen-ruler]").textContent();
  assert.ok(rulerText?.includes("5 mm divisions"), `ruler names its divisions, got: ${rulerText}`);
  assert.ok(
    rulerText?.includes("Adjust until the marks match a physical ruler."),
    `ruler carries the matching hint, got: ${rulerText}`,
  );
  assert.equal(
    await page.getByRole("img", { name: "Approximate 50 millimetre ruler with 5 millimetre divisions" }).count(),
    1,
  );

  const tickGap = (from: number, to: number): Promise<number> =>
    page.evaluate(
      ([a, b]) => {
        const left = (mm: number): number => {
          const tick = document.querySelector(`[data-screen-ruler-tick="${mm}"]`);
          if (!(tick instanceof SVGLineElement)) throw new Error(`Ruler is missing its ${mm} mm tick.`);
          return tick.getBoundingClientRect().left;
        };
        return left(b) - left(a);
      },
      [from, to] as [number, number],
    );
  const paperWidth = (): Promise<number> =>
    page.evaluate(() => {
      const element = document.querySelector("[data-screen-aperture]");
      if (!(element instanceof HTMLElement)) throw new Error("Screen workspace is missing its aperture.");
      return element.getBoundingClientRect().width;
    });

  // The 50 mm span follows the 96 CSS reference density at 100%.
  const expectedSpan = (50 / 25.4) * 96;
  const expectedGap = (5 / 25.4) * 96;
  assert.ok(
    Math.abs((await tickGap(0, 50)) - expectedSpan) < 1.5,
    `ruler spans 50 mm at 100% (saw ${await tickGap(0, 50)})`,
  );
  for (let mm = 0; mm < 50; mm += 5) {
    const gap = await tickGap(mm, mm + 5);
    assert.ok(Math.abs(gap - expectedGap) < 1, `5 mm interval ${mm}–${mm + 5} keeps the reference width (saw ${gap})`);
  }

  // 150% scales ruler and paper together.
  const basePaper = await paperWidth();
  await page.locator('[data-screen-size] [role="slider"]').focus();
  await page.keyboard.press("End");
  await page.waitForFunction(() => document.querySelector("[data-screen-size-value]")?.textContent === "150%");
  assert.ok(Math.abs((await tickGap(0, 50)) / expectedSpan - 1.5) < 0.02, "ruler span scales by 1.5");
  assert.ok(Math.abs((await paperWidth()) / basePaper - 1.5) < 0.02, "paper scales with the ruler");

  // Reload restores the persisted size for the ruler too.
  await page.reload({ waitUntil: "domcontentloaded" });
  await screenReady(page);
  await page.locator("details[data-monitor-info] > summary").click();
  assert.equal(await page.locator("[data-screen-size-value]").textContent(), "150%");
  assert.ok(Math.abs((await tickGap(0, 50)) / expectedSpan - 1.5) < 0.02, "reload keeps the 150% ruler span");

  // The widest stop never widens the page nor compresses the ruler at mobile width.
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    true,
    "150% ruler never widens the page at mobile width",
  );
  assert.ok(Math.abs((await tickGap(0, 50)) / expectedSpan - 1.5) < 0.02, "ruler keeps its full span at mobile width");
  assert.deepEqual(errors, []);
});

test("screen monitor info stays readable at mobile width", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  t.after(() => page.close());
  await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
  await screenReady(page);
  await page.locator('[data-device-preview="xteink-x4"]').waitFor();
  await page.locator("[data-monitor-info]").waitFor();
  const paper = await page.evaluate(() => {
    const element = document.querySelector("[data-screen-aperture]");
    if (!(element instanceof HTMLElement)) throw new Error("Screen aperture is missing.");
    return element.getBoundingClientRect().width;
  });
  assert.ok(paper > 0, "paper keeps a presentation size at mobile width");
  assert.equal(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    true,
    "monitor info never widens the page at mobile width",
  );
  await page.locator("details[data-monitor-info] > summary").click();
  await page.locator("[data-monitor-dpr]").waitFor();
  assert.equal(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    true,
    "open display details never widen the page at mobile width",
  );
});

test(
  "screen loads directly and keeps navigation state across reload and history",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    t.after(() => page.close());

    await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
    await screenReady(page);
    assert.equal(await hashPath(page), "/screen/");
    assert.equal(await page.title(), "Screen — Glypherie");
    assert.equal(await page.locator("main h1").count(), 1);

    await page.goto(`${url}screen/?v=1&font=abc&utm=keep`, { waitUntil: "domcontentloaded" });
    await screenReady(page);
    assert.equal(await hashPath(page), "/screen/");
    assert.equal(await hashParam(page, "v"), null);
    assert.equal(await hashParam(page, "font"), null);
    assert.equal(await hashParam(page, "utm"), "keep");
    const first = DEVICES[0]!;
    await page.locator(`[data-device-preview="${first.id}"]`).waitFor();

    const nav = page.getByRole("navigation", { name: "Primary" });
    const screenNav = nav.getByRole("link", { name: "Screen" });
    const fontsNav = nav.getByRole("link", { name: "Fonts" });
    const palettesNav = nav.getByRole("link", { name: "Palettes" });
    assert.equal(await screenNav.getAttribute("aria-current"), "page");
    assert.equal(await fontsNav.getAttribute("aria-current"), null);
    assert.equal(await palettesNav.getAttribute("aria-current"), null);
    assert.equal(
      await screenNav.getAttribute("href"),
      "/preview/screen/?utm=keep",
      "section links keep foreign params",
    );

    await page.reload({ waitUntil: "domcontentloaded" });
    await screenReady(page);
    assert.equal(await hashPath(page), "/screen/");
    await page.locator(`[data-device-preview="${first.id}"]`).waitFor();

    await fontsNav.click();
    await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
    assert.equal(await hashPath(page), "/fonts/");
    assert.equal(await fontsNav.getAttribute("aria-current"), "page");

    await page.goBack();
    await screenReady(page);
    assert.equal(await hashPath(page), "/screen/");
    assert.equal(await screenNav.getAttribute("aria-current"), "page");
    await page.locator(`[data-device-preview="${first.id}"]`).waitFor();

    await page.goForward();
    await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
    assert.equal(await hashPath(page), "/fonts/");

    await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
    await screenReady(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload({ waitUntil: "domcontentloaded" });
    await screenReady(page);
    assert.ok(await screenNav.isVisible(), "screen nav stays usable at mobile width");
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      true,
      "screen page does not widen at mobile width",
    );

    await nav.getByRole("link", { name: "Fonts" }).click();
    await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0);
    const cardCount = (await cardIds(page)).length;
    assert.ok(cardCount > 0, "font library still boots after screen navigation");
  },
);
