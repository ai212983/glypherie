// Native DOM text reference; compare the compact inline font to original bytes.
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
const require = createRequire(resolve("apps/web/package.json"));
const { chromium } = require("playwright-core");
const root = resolve(process.argv[2]);
const data = JSON.parse(await readFile(resolve(root, "page-data.json"), "utf8"));
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1200, height: 1000 }, offline: true });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(pathToFileURL(resolve(root, "index.html")).href);
  await page.locator("#browser-native[data-state=ready]").waitFor();
  assert.equal(await page.locator("#custom-grayscale-details").evaluate((el) => el.open), false);
  let checks = 0,
    zoomChecks = 0;
  for (const [i, font] of data.cases.entries()) {
    const reference = font.browserReference;
    const bytes = Buffer.from(reference.dataUrl.split(",")[1], "base64");
    assert.equal(createHash("sha256").update(bytes).digest("hex"), font.sourceSha256);
    await page.getByLabel("Captured font").selectOption(String(i));
    for (const preset of data.presets) {
      await page.getByLabel("Text preset").selectOption(preset.id);
      await page.locator("#browser-native[data-state=ready]").waitFor();
      const state = await page.locator("#browser-native").evaluate((el) => {
        const s = getComputedStyle(el);
        return {
          text: el.textContent,
          size: s.fontSize,
          kerning: s.fontKerning,
          ligatures: s.fontVariantLigatures,
          letter: s.letterSpacing,
          word: s.wordSpacing,
          variation: s.fontVariationSettings,
          width: el.clientWidth,
          loaded: document.fonts.check(`${s.fontSize} ${s.fontFamily}`),
        };
      });
      assert.equal(state.text, preset.text);
      assert.equal(state.size, `${font.sizePx}px`);
      assert.equal(state.kerning, "auto");
      assert.equal(state.ligatures, "normal");
      assert.equal(state.letter, "normal");
      assert.equal(state.word, "0px");
      assert.equal(state.loaded, true);
      assert.equal(state.width, 280);
      for (const [tag, value] of Object.entries(font.axes)) assert.ok(state.variation.includes(`"${tag}" ${value}`));
      checks++;
    }
    await page.getByLabel("Sample text").fill("office AV ty type lynx tuft frogs\nnormal browser text with wrapping");
    await page.locator("#browser-native[data-state=ready]").waitFor();
    const nativePixels = await page.locator("#browser-native").screenshot();
    for (const zoom of [2, 4, 8]) {
      await page.getByLabel("Enlargement", { exact: true }).selectOption(String(zoom));
      await page.locator("#browser-native[data-state=ready]").waitFor();
      const geometry = await page.evaluate((scale) => {
        const native = document.getElementById("browser-native"),
          large = document.getElementById("browser-enlarged");
        const positions = (el, divisor) => {
          const origin = el.getBoundingClientRect();
          return Array.from({ length: el.firstChild.length }, (_, i) => {
            const r = new Range();
            r.setStart(el.firstChild, i);
            r.setEnd(el.firstChild, i + 1);
            return [...r.getClientRects()].map((b) => [
              (b.x - origin.x) / divisor,
              (b.y - origin.y) / divisor,
              b.width / divisor,
              b.height / divisor,
            ]);
          });
        };
        const a = getComputedStyle(native),
          b = getComputedStyle(large);
        return {
          native: positions(native, 1),
          large: positions(large, scale),
          sameFont: a.fontFamily === b.fontFamily,
          sameSize: a.fontSize === b.fontSize,
          sameAxes: a.fontVariationSettings === b.fontVariationSettings,
          nativeWidth: native.clientWidth,
          largeWidth: large.clientWidth,
          visualWidth: large.getBoundingClientRect().width,
          frameWidth: document.getElementById("browser-zoom-frame").clientWidth,
        };
      }, zoom);
      assert.deepEqual(geometry.large, geometry.native, "Zoom preserves wrapping and fractional glyph placement");
      assert.equal(geometry.sameFont && geometry.sameSize && geometry.sameAxes, true);
      assert.equal(geometry.largeWidth, geometry.nativeWidth);
      assert.equal(geometry.visualWidth, geometry.nativeWidth * zoom);
      assert.equal(geometry.frameWidth, geometry.nativeWidth * zoom);
      assert.deepEqual(
        await page.locator("#browser-native").screenshot(),
        nativePixels,
        "Zoom leaves native pixels unchanged",
      );
      zoomChecks++;
    }
    await page.getByLabel("Enlargement", { exact: true }).selectOption("4");
  }
  // The comparison controls must not inject tracking or optical spacing into DOM text.
  await page.getByLabel("Sample text").fill("office afflict AV ty type");
  await page.locator("#browser-native[data-state=ready]").waitFor();
  // Optional diagnostic panels and construction-control descriptions can reflow. Keep
  // this pixel-invariance check at the same physical raster phase; otherwise
  // moving unchanged DOM text vertically can change browser antialiasing.
  const normalizedReference =
    (await page.locator("#neighbor-review").isVisible()) ||
    (await page.locator(".construction-comparison").count()) > 0;
  const referenceCss = await page.locator("#browser-native").evaluate((el) => el.style.cssText);
  if (normalizedReference) {
    if (await page.locator("#neighbor-review").isVisible())
      await page.locator("#neighbor-review[data-state=ready]").waitFor();
    await page
      .locator("#browser-native")
      .evaluate((el) =>
        Object.assign(el.style, { position: "fixed", top: "0px", left: "0px", zIndex: "999999", background: "white" }),
      );
  }
  const before = await page.locator("#browser-native").screenshot();
  await page.locator("#letter").fill("4");
  await page.locator("#word").fill("3");
  await page.locator("#optical").fill("0");
  await page.locator("#kerning").fill("0");
  await page.locator("#browser-native[data-state=ready]").waitFor();
  if (normalizedReference && (await page.locator("#neighbor-review").isVisible()))
    await page.locator("#neighbor-review[data-state=ready]").waitFor();
  assert.deepEqual(await page.locator("#browser-native").screenshot(), before);
  if (normalizedReference)
    await page.locator("#browser-native").evaluate((el, css) => {
      el.style.cssText = css;
    }, referenceCss);
  let inlineChecks = 0,
    inlinePixelIdentical = 0;
  if (process.argv[3]) {
    await page.goto(pathToFileURL(resolve(process.argv[3])).href);
    await page.locator("#browser-native[data-state=ready]").waitFor();
    const original = data.cases[0];
    await page.evaluate(async (ref) => {
      const face = await new FontFace("IndependentOriginal", `url(${ref.dataUrl})`).load();
      document.fonts.add(face);
    }, original.browserReference);
    for (const preset of data.presets) {
      await page.getByLabel("Text preset").selectOption(preset.id);
      await page.locator("#browser-native[data-state=ready]").waitFor();
      // Same physical pixel position, same native DOM styling; only font resource changes.
      await page.locator("#browser-native").evaluate((el) => {
        el.style.position = "fixed";
        el.style.left = "0";
        el.style.top = "0";
        el.style.background = "white";
        el.style.zIndex = "999";
      });
      const positions = () => {
        const el = document.getElementById("browser-native"),
          text = el.firstChild;
        return Array.from({ length: text.length }, (_, i) => {
          const range = new Range();
          range.setStart(text, i);
          range.setEnd(text, i + 1);
          return [...range.getClientRects()].map((r) => [r.x, r.y, r.width, r.height]);
        });
      };
      const compactPositions = await page.evaluate(positions);
      const compact = await page.locator("#browser-native").screenshot();
      const family = await page.locator("#browser-native").evaluate((el) => {
        const f = el.style.fontFamily;
        el.style.fontFamily = "IndependentOriginal";
        return f;
      });
      const full = await page.locator("#browser-native").screenshot();
      assert.deepEqual(
        await page.evaluate(positions),
        compactPositions,
        `Inline font preserves browser glyph positions and line breaks: ${preset.label}`,
      );
      // Different font resources may trigger different browser antialiasing even
      // with equal contours and placement. Record pixel identity separately.
      if (compact.equals(full)) inlinePixelIdentical++;
      await page.locator("#browser-native").evaluate((el, f) => {
        el.style.fontFamily = f;
      }, family);
      inlineChecks++;
    }
  }
  // A failed source font must display a failure, never silently show fallback text.
  const failed = await browser.newPage({ offline: true });
  await failed.addInitScript(() => {
    globalThis.FontFace = class {
      load() {
        return Promise.reject(new Error("test font failure"));
      }
    };
  });
  await failed.goto(pathToFileURL(resolve(root, "index.html")).href);
  await failed.locator("#browser-native[data-state=failed]").waitFor({ state: "attached" });
  assert.equal(await failed.locator("#browser-native").isVisible(), false);
  assert.match(await failed.locator("#browser-measure").textContent(), /unavailable.*test font failure/);
  await failed.close();
  assert.deepEqual(errors, []);
  const report = {
    status: "passed",
    originalFontIdentities: data.cases.length,
    presetFontChecks: checks,
    zoomChecks,
    referenceControlPixelPhaseNormalized: normalizedReference,
    inlineOriginalLayoutParity: inlineChecks,
    inlineOriginalPixelIdentical: inlinePixelIdentical,
    browserErrors: errors,
  };
  await writeFile(resolve(root, "browser-reference-verification.json"), JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
}
