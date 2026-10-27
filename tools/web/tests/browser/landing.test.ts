import assert from "node:assert/strict";
import test from "node:test";
import sampleMatrix from "../../src/app/features/landing/assets/rasterizers/matrix.json" with { type: "json" };
import {
  bootLibrary, browserAvailable, buildApp, cardIds, hashPath, launch, servePrefix, setZoom,
} from "../helpers/spa-helpers.ts";

const defaultCapture = sampleMatrix.cases.find((entry) => entry.family_id === "roboto" && entry.size_px === 16)!;
const [defaultWidth, defaultHeight] = defaultCapture.display_size as [number, number];

test("GitHub stars refresh when returning after starring the repository", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ serviceWorkers: "block" });
  let stars = 0;
  await context.route("https://api.github.com/repos/ai212983/glypherie", (route) =>
    route.fulfill({ json: { stargazers_count: stars } }));
  const page = await context.newPage();
  await page.goto(url);
  await page.getByRole("img", { name: "0 GitHub stars", exact: true }).waitFor();
  stars = 1;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.getByRole("img", { name: "1 GitHub stars", exact: true }).waitFor({ timeout: 2000 });
});

test("GitHub button shows public stars and falls back when counts are unavailable", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  for (const sample of [
    { status: 200, body: { stargazers_count: 0 }, label: "0 GitHub stars", text: "★ 0" },
    { status: 200, body: { stargazers_count: 1270 }, label: "1,270 GitHub stars", text: "★ 1.3K" },
    { status: 404, body: {}, label: "Star on GitHub", text: "★ Star" },
    { status: 403, body: {}, label: "Star on GitHub", text: "★ Star" },
    { status: 200, body: { stargazers_count: -1 }, label: "Star on GitHub", text: "★ Star" },
  ]) {
    const context = await browser.newContext({ serviceWorkers: "block", viewport: { width: 390, height: 844 } });
    let requests = 0;
    await context.route("https://api.github.com/repos/ai212983/glypherie", (route) => {
      requests += 1;
      return route.fulfill({ status: sample.status, contentType: "application/json", body: JSON.stringify(sample.body) });
    });
    const page = await context.newPage();
    const response = page.waitForResponse("https://api.github.com/repos/ai212983/glypherie");
    await page.goto(url);
    await (await response).finished();
    const source = page.getByRole("link", { name: /^GitHub/ });
    assert.equal(await source.getAttribute("href"), "https://github.com/ai212983/glypherie");
    const badge = source.getByRole("img", { name: sample.label, exact: true });
    await badge.waitFor();
    assert.equal(await badge.innerText(), sample.text);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.getByRole("link", { name: "Open font library", exact: false }).click();
    await page.locator("[data-font-card]").first().waitFor();
    await page.getByRole("banner").getByRole("link", { name: "Glypherie", exact: true }).click();
    await badge.waitFor();
    assert.equal(requests, 2, "returning to the homepage refreshes the count");
    await context.close();
  }
});

test("landing, library and brand links keep distinct destinations under a hosting prefix", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({ serviceWorkers: "block", viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(url);
  await page.locator("[data-landing]").waitFor();
  assert.equal(await hashPath(page), "/");
  assert.equal(await page.locator("main > section").first().getAttribute("aria-labelledby"), "rasterizer-comparison-title", "comparison is the first primary section");
  await setZoom(page, "1");
  assert.equal(await page.locator("h1").count(), 1);
  assert.equal(await page.locator('[data-primary-nav][aria-current="page"]').count(), 0);
  assert.equal(await page.getByRole("heading", { name: "Live specimen", exact: true }).count(), 0);
  const comparison = page.locator("[data-rasterizer-comparison]");
  assert.equal(await page.getByRole("heading", { name: "Compare font converters", exact: true }).count(), 1);
  assert.deepEqual(await comparison.locator("h3").allTextContents(), [
    "Glypherie", "pdfontconv", "Tophat", "LVGL Font Converter", "Adafruit Font Converter",
  ]);
  await page.waitForFunction(({ width, height, count }) => {
    const images = [...document.querySelectorAll<HTMLImageElement>("[data-rasterizer] img")];
    return images.length === count && images.every((image) => image.complete && image.naturalWidth === width && image.naturalHeight === height);
  }, { width: defaultWidth, height: defaultHeight, count: defaultCapture.display_lines.length * 5 });
  const sample = comparison.locator("img").first();
  const lines = comparison.locator("[data-rasterizer-lines]").first();
  assert.ok((await lines.boundingBox())!.height <= 72, "three text lines have no blank lines between them");
  assert.equal((await sample.boundingBox())?.width, defaultWidth, "capture pixels are displayed at native scale");
  assert.equal(await page.locator("[data-global-canvas]").count(), 1);
  assert.equal(await page.locator("[data-global-zoom]").count(), 1);
  await setZoom(page, "2");
  assert.equal((await sample.boundingBox())?.width, defaultWidth * 2, "enlargement uses an integer scale");
  await setZoom(page, "4");
  assert.equal((await sample.boundingBox())?.width, defaultWidth * 4);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false, "enlarged samples scroll inside their frames");
  await setZoom(page, "1");
  const start = page.getByRole("link", { name: "Open font library", exact: false });
  assert.equal(await start.getAttribute("href"), "/preview/fonts/");
  assert.equal(await page.getByRole("banner").getByRole("link", { name: "Glypherie", exact: true }).getAttribute("href"), "/preview/");
  let documentLoads = 0;
  page.on("load", () => { documentLoads += 1; });
  await start.focus();
  await start.press("Enter");
  await page.locator("[data-font-card]").first().waitFor();
  assert.equal(await hashPath(page), "/fonts/");
  assert.equal(await page.locator('[data-primary-nav="fonts"]').getAttribute("aria-current"), "page");
  await page.goBack();
  await page.locator("[data-landing]").waitFor();
  await page.goForward();
  await page.locator("[data-font-card]").first().waitFor();
  assert.equal(documentLoads, 0, "app navigation preserves the document");
  await page.reload();
  await page.locator("[data-font-card]").first().waitFor();
  assert.equal(await hashPath(page), "/fonts/", "library bookmarks survive direct Pages loads");

  const ids = await cardIds(page);
  await page.goto(`${url}?font=${ids[0]}`);
  await page.locator("[data-text]").waitFor();
  await page.locator("[data-text]").fill("Pending preview edit");
  await page.getByRole("banner").getByRole("link", { name: "Glypherie", exact: true }).click();
  await page.locator("[data-landing]").waitFor();
  await page.waitForTimeout(600);
  assert.equal(await hashPath(page), "/", "a pending snapshot cannot return the landing to the editor");
  assert.equal(new URL(page.url()).search, "");
  await page.getByRole("link", { name: "Palettes", exact: true }).click();
  await page.locator('main section[aria-label="Grayscale preview"]').waitFor();
  await page.getByRole("banner").getByRole("link", { name: "Glypherie", exact: true }).click();
  await page.locator("[data-landing]").waitFor();
  assert.equal(await hashPath(page), "/");
  for (const theme of ["light", "dark"]) {
    await page.evaluate((value) => document.documentElement.classList.toggle("dark", value === "dark"), theme);
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await start.isVisible());
    const scrollFrame = comparison.getByRole("region").first();
    assert.equal(await scrollFrame.getAttribute("tabindex"), "0", "samples can be scrolled from the keyboard");
    assert.equal((await sample.boundingBox())?.width, defaultWidth, "mobile keeps native capture scale");
    assert.equal(await scrollFrame.evaluate((element) => element.scrollWidth > element.clientWidth), true, "mobile frames scroll instead of resampling images");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false, `${theme} mobile layout fits the viewport`);
  }
  assert.deepEqual(errors, []);
});

test("clearing local cache confirms and resets all Glypherie data without clearing other apps", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage();
  await bootLibrary(page, url);
  await page.getByRole("banner").getByRole("link", { name: "Glypherie", exact: true }).click();
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
  await page.evaluate(async (scope) => {
    localStorage.setItem("font-preview.reset-fixture", "saved settings");
    sessionStorage.setItem("font-preview.reset-fixture", "saved session");
    localStorage.setItem("other-app", "keep");
    sessionStorage.setItem("other-app", "keep");
    const names = await caches.keys();
    const appCache = await caches.open(names.find((name) => name.endsWith(`-${scope}`))!);
    await appCache.put(`${scope}reset-fixture`, new Response("old cached app"));
    const otherCache = await caches.open(`workbox-precache-v2-${scope}other/`);
    await otherCache.put(`${scope}other/fixture`, new Response("keep"));
  }, url);
  const clear = page.getByRole("button", { name: "Delete data", exact: true });
  assert.equal(await clear.getAttribute("data-variant"), "destructive");
  await clear.click();
  const confirmation = page.getByRole("region", { name: "Delete all local data?", exact: true });
  assert.match(await confirmation.innerText(), /imported fonts, saved variants, palettes, settings, and the app cache/);
  assert.equal(await clear.count(), 0, "confirmation replaces the panel content");
  assert.equal(await page.getByRole("button", { name: "Cancel", exact: true }).evaluate((button) => button === document.activeElement), true);
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await clear.waitFor();
  await page.waitForFunction(() => document.activeElement?.textContent?.trim() === "Delete data");
  assert.equal(await page.evaluate(() => localStorage.getItem("font-preview.reset-fixture")), "saved settings", "cancelling keeps stored data");
  assert.equal(await page.evaluate(async () => (await indexedDB.databases()).some((db) => db.name === "font-library")), true);
  await clear.click();
  await page.getByRole("button", { name: "Cancel", exact: true }).press("Escape");
  await clear.waitFor();
  await clear.click();
  await Promise.all([page.waitForEvent("load"), page.getByRole("button", { name: "Delete everything", exact: true }).click()]);
  await page.locator("[data-landing]").waitFor();
  assert.deepEqual(await page.evaluate(async () => ({
    databaseExists: (await indexedDB.databases()).some((db) => db.name === "font-library"),
    preference: localStorage.getItem("font-preview.reset-fixture"),
    session: sessionStorage.getItem("font-preview.reset-fixture"),
    otherPreference: localStorage.getItem("other-app"),
    otherSession: sessionStorage.getItem("other-app"),
    oldCacheEntry: Boolean(await caches.match(new URL("reset-fixture", location.href).href)),
    otherCacheEntry: await (await caches.match(new URL("other/fixture", location.href).href))?.text(),
  })), { databaseExists: false, preference: null, session: null, otherPreference: "keep", otherSession: "keep", oldCacheEntry: false, otherCacheEntry: "keep" });
  await page.getByRole("link", { name: "Open font library", exact: false }).click();
  await page.locator("[data-font-card]").first().waitFor();
});

test("the introduction stays usable when font storage and the renderer are unavailable", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t, "/");
  const url = await servePrefix(t, output, "/");
  const browser = await launch(t);
  const context = await browser.newContext({ serviceWorkers: "block" });
  await context.route("**/*.wasm", (route) => route.abort());
  await context.addInitScript(() => {
    window.indexedDB.open = () => { throw new Error("IDB denied"); };
  });
  const page = await context.newPage();
  await page.goto(`${url}?utm=intro`);
  await page.getByRole("heading", { name: "Bitmap fonts for low-resolution displays." }).waitFor();
  assert.equal(new URL(page.url()).pathname, "/");
  assert.equal(await page.locator("[data-library-error]").count(), 0);
  const start = page.getByRole("link", { name: "Open font library", exact: false });
  assert.equal(await start.getAttribute("href"), "/fonts/?utm=intro");
  await start.click();
  await page.locator("[data-library-error]").waitFor({ timeout: 30000 });
  await page.getByRole("banner").getByRole("link", { name: "Glypherie", exact: true }).click();
  await page.locator("[data-landing]").waitFor();
  assert.equal(new URL(page.url()).pathname, "/");
  assert.equal(new URL(page.url()).searchParams.get("utm"), "intro");
});


test("comparison previews use the Fonts page colors, inverse mode, zoom and frames", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 });
  await page.goto(url);
  await setZoom(page, "1");
  await page.waitForFunction(() => [...document.querySelectorAll<HTMLImageElement>("[data-rasterizer] img")].every((image) => image.complete && image.naturalWidth > 0));
  const presets = [
    { name: "Warm", paper: [244, 236, 220], ink: [26, 24, 21] },
    { name: "Cool", paper: [232, 240, 248], ink: [27, 42, 58] },
    { name: "Neutral", paper: [255, 255, 255], ink: [0, 0, 0] },
  ];
  for (const preset of presets) {
    await page.getByRole("combobox", { name: "Canvas preset", exact: true }).click();
    await page.getByRole("option", { name: preset.name, exact: true }).click();
    for (const inverse of [false, true]) {
      const toggle = page.getByRole("switch", { name: "Inverse canvas colors" });
      if ((await toggle.getAttribute("aria-checked") === "true") !== inverse) await toggle.click();
      const paper = inverse ? preset.ink : preset.paper;
      const ink = inverse ? preset.paper : preset.ink;
      const expected = [paper.join(","), ink.join(",")].sort();
      await page.waitForFunction((color) => [...document.querySelectorAll("[data-rasterizer-frame]")]
        .every((frame) => getComputedStyle(frame).backgroundColor === color), `rgb(${paper.join(", ")})`);
      for (const sample of await page.locator("[data-rasterizer-lines]").all()) {
        // Check composited colors; source PNGs stay black and white.
        const shot = await sample.screenshot();
        const colors = await page.evaluate(async (base64) => {
          const image = new Image();
          image.src = `data:image/png;base64,${base64}`;
          await image.decode();
          const canvas = document.createElement("canvas");
          canvas.width = image.naturalWidth;
          canvas.height = image.naturalHeight;
          const context = canvas.getContext("2d")!;
          context.drawImage(image, 0, 0);
          const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
          const found = new Set<string>();
          for (let i = 0; i < data.length; i += 4) found.add(`${data[i]},${data[i + 1]},${data[i + 2]}`);
          return [...found].sort();
        }, shot.toString("base64"));
        assert.deepEqual(colors, expected, `${preset.name}, inverse=${inverse}: captured preview uses the shared ink and paper colors`);
      }
    }
  }
  await setZoom(page, "3");
  assert.equal((await page.locator("[data-rasterizer-lines]").first().boundingBox())?.width, defaultWidth * 3, "3× is shared with captured previews");
  const styleOf = (element: Element) => {
    const style = getComputedStyle(element);
    return { background: style.backgroundColor, border: style.borderColor, radius: style.borderRadius, padding: style.padding, shadow: style.boxShadow };
  };
  const frame = await page.locator('[data-rasterizer-frame="pdfontconv"]').evaluate(styleOf);
  await page.getByRole("link", { name: "Fonts", exact: true }).click();
  await page.locator("[data-card-frame]").first().waitFor();
  assert.equal(await page.locator("[data-preview-zoom]").getAttribute("data-value"), "3");
  assert.equal(await page.getByRole("switch", { name: "Inverse canvas colors" }).getAttribute("aria-checked"), "true");
  assert.deepEqual(await page.locator("[data-card-frame]").first().evaluate(styleOf), frame, "landing and Fonts use the identical specimen frame");
  await page.getByRole("banner").getByRole("link", { name: "Glypherie", exact: true }).click();
  await page.reload();
  await page.locator("[data-rasterizer-frame]").first().waitFor();
  assert.equal(await page.locator("[data-preview-zoom]").getAttribute("data-value"), "3");
  assert.deepEqual(await page.locator('[data-rasterizer-frame="pdfontconv"]').evaluate(styleOf), frame, "display preferences survive navigation and reload");
});

test("landing switches all converter samples across families and native sizes", { skip: !browserAvailable }, async (t) => {
  assert.deepEqual(sampleMatrix.families.map((family) => family.id), ["roboto", "roboto-italic", "literata", "rouge-script"]);
  assert.deepEqual(sampleMatrix.sizes, [8, 12, 16, 20]);
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(url);
  await setZoom(page, "1");
  const comparison = page.locator("[data-rasterizer-comparison]");
  const sizeControls = page.getByRole("radiogroup", { name: "Sample font size" });
  for (const family of sampleMatrix.families) {
    await page.getByRole("combobox", { name: "Sample font family", exact: true }).click();
    await page.getByRole("option", { name: family.label, exact: true }).click();
    const sizes = family.id === "rouge-script" ? [20] : [8, 12, 16, 20];
    assert.deepEqual(sampleMatrix.cases.filter((entry) => entry.family_id === family.id).map((entry) => entry.size_px), sizes);
    await sizeControls.getByRole("radio").first().waitFor({ state: "visible" });
    assert.equal(await sizeControls.getByRole("radio").count(), sizes.length);
    for (const size of sizes) {
      const selected = sizeControls.getByRole("radio", { name: `${size} pixels`, exact: true });
      await selected.click();
      assert.equal(await selected.getAttribute("aria-checked"), "true");
      // Clicking the selected size cannot leave the preview without a selection.
      await selected.click();
      assert.equal(await selected.getAttribute("aria-checked"), "true");
      assert.equal(await comparison.getAttribute("data-family"), family.id);
      assert.equal(await comparison.getAttribute("data-size"), String(size));
      const capture = sampleMatrix.cases.find((entry) => entry.family_id === family.id && entry.size_px === size)!;
      assert.equal(capture.display_lines.length, family.id === "rouge-script" ? 2 : 3);
      await page.waitForFunction(({ width, height, count }) => {
        const images = [...document.querySelectorAll<HTMLImageElement>("[data-rasterizer] img")];
        return images.length === count && images.every((image) => image.complete && image.naturalWidth === width && image.naturalHeight === height);
      }, { width: capture.display_size[0]!, height: capture.display_size[1]!, count: capture.display_lines.length * 5 });
      assert.equal(await comparison.locator("figure").count(), 5);
      assert.equal((await comparison.locator("img").first().boundingBox())?.width, capture.display_size[0]);
      assert.match(await comparison.locator("img").first().getAttribute("alt") ?? "", new RegExp(`${family.label} · ${size} px`));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    }
  }
  await page.getByRole("combobox", { name: "Sample font family", exact: true }).click();
  await page.getByRole("option", { name: "Roboto", exact: true }).click();
  await sizeControls.getByRole("radio", { name: "8 pixels", exact: true }).click();
  await page.getByRole("combobox", { name: "Sample font family", exact: true }).click();
  await page.getByRole("option", { name: "Rouge Script", exact: true }).click();
  assert.equal(await comparison.getAttribute("data-size"), "20", "unsupported size switches to a configured size");
  assert.equal(await sizeControls.getByRole("radio", { name: "20 pixels", exact: true }).getAttribute("aria-checked"), "true");
  await page.getByRole("combobox", { name: "Sample font family", exact: true }).click();
  await page.getByRole("option", { name: "Roboto", exact: true }).click();
  const eight = sizeControls.getByRole("radio", { name: "8 pixels", exact: true });
  await eight.click();
  await eight.focus();
  await page.keyboard.press("ArrowRight");
  await page.waitForFunction(() => document.querySelector('[aria-label="12 pixels"]')?.getAttribute("aria-checked") === "true");
  assert.equal(await sizeControls.getByRole("radio", { name: "12 pixels", exact: true }).getAttribute("aria-checked"), "true");
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, "controls wrap on narrow screens");
  const chevron = page.getByRole("combobox", { name: "Sample font family", exact: true }).locator("img");
  assert.deepEqual(await chevron.evaluate((image) => ({ width: image.getBoundingClientRect().width, height: image.getBoundingClientRect().height })), { width: 19.5, height: 19.5 });
});
