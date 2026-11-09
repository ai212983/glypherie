// Chat-led comparison: Python parity, optional corpus coverage and stable A/B. No server.
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";
const require = createRequire(resolve("apps/web/package.json"));
const { chromium } = require("playwright-core");
const path = resolve(process.argv[2]);
const root = dirname(path);
const expectedData = JSON.parse(await readFile(resolve(root, "review-data.json"), "utf8"));
const fixtures = JSON.parse(await readFile(resolve(root, "verification-fixtures.json"), "utf8"));
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 728, height: 1100 }, offline: true, acceptDownloads: true });
  const errors = [],
    network = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (request) => {
    if (/^https?:/.test(request.url())) network.push(request.url());
  });
  await page.goto(pathToFileURL(path).href);
  await page.waitForFunction(() => !!globalThis.SpacingBlindReview);
  assert.equal(await page.locator("#font option").count(), expectedData.fonts.length);
  assert.equal(await page.locator("#preset option").count(), expectedData.presets.length + 1);
  assert.equal(await page.locator("#preset").inputValue(), "quick");
  assert.equal(await page.locator("#label-a").textContent(), "A");
  assert.equal(await page.locator("#label-b").textContent(), "B");
  assert.equal(await page.locator("#underline").isChecked(), true);
  assert.equal(await page.locator("form").count(), 0);
  assert.equal(await page.locator("#pass, #rating, #download, #next").count(), 0);
  assert.equal(await page.locator("#more").getAttribute("open"), null);
  const initialOrder = await page.evaluate(() => SpacingBlindReview.selection().order);
  // The short default is an exact prefix of a Python-verified full preset.
  const shortChecks = await page.evaluate((fixtures) => {
    const review = SpacingBlindReview,
      text = review.samples[0].text;
    if (text.split(/\s+/).length !== 60 || !review.data.presets[0].text.startsWith(text))
      throw new Error("Unexpected starting excerpt");
    for (const [index, arm] of review.selection().order.entries()) {
      const full = fixtures.find((f) => f.arm === arm && f.preset === "lynx-lowercase" && f.width === 280).expected;
      const expected = full.lines.flatMap((line) => line.placements).filter((p) => p.index < text.length);
      const actual = review.layouts[index].lines.flatMap((line) => line.placements);
      for (let i = 0; i < Math.max(actual.length, expected.length); i++) {
        if (!actual[i] || !expected[i] || Object.keys(expected[i]).some((key) => actual[i][key] !== expected[i][key]))
          throw new Error("Short text differs from authoritative Python placements");
      }
    }
    return 2;
  }, fixtures[0]);
  await page.locator("#more > summary").click();
  let parity = 0,
    canvasChecks = 0,
    wrapDifferences = 0,
    underlineChecks = 0;
  for (let font = 0; font < fixtures.length; font++) {
    // JSON canonicalization deliberately ignores JS object property order.
    parity += await page.evaluate(
      ({ font, fixtures }) => {
        const stable = (value) =>
          JSON.stringify(value, (_key, entry) =>
            entry && !Array.isArray(entry) && typeof entry === "object"
              ? Object.fromEntries(Object.entries(entry).sort(([a], [b]) => a.localeCompare(b)))
              : entry,
          );
        const data = SpacingBlindReview.data;
        for (const fixture of fixtures) {
          const text = data.presets.find((p) => p.id === fixture.preset).text;
          const actual = ContextualSpacing.layout(
            data.fonts[font],
            text,
            4,
            4,
            0,
            0,
            fixture.width,
            false,
            String(fixture.arm),
          );
          if (stable(actual) !== stable(fixture.expected)) throw new Error("Python whole-text placement mismatch");
        }
        return fixtures.length;
      },
      { font, fixtures: fixtures[font] },
    );
    await page.locator("#font").selectOption(String(font));
    for (const preset of expectedData.presets) {
      await page.locator("#preset").selectOption(preset.id);
      canvasChecks += await page.evaluate(() => {
        const review = SpacingBlindReview,
          selection = review.selection(),
          data = review.data,
          font = data.fonts[selection.font];
        const text = review.samples[selection.preset].text;
        for (const [i, side] of ["a", "b"].entries()) {
          const layout = ContextualSpacing.layout(
            font,
            text,
            4,
            4,
            0,
            0,
            selection.width,
            false,
            String(selection.order[i]),
          );
          const expected = document.createElement("canvas");
          ContextualSpacing.paint(expected, font, layout, 1);
          const native = document.getElementById(side + "-native"),
            zoom = document.getElementById(side + "-zoom");
          if (expected.toDataURL() !== native.toDataURL() || native.toDataURL() !== zoom.toDataURL())
            throw new Error("Missing or changed whole-text pixel data");
          if (layout.lines.flatMap((line) => line.placements).length !== [...text].filter((c) => c !== "\n").length)
            throw new Error("Text truncated");
        }
        return 2;
      });
      underlineChecks += await page.evaluate(() => {
        const review = SpacingBlindReview,
          font = review.data.fonts[review.selection().font];
        const lookup = new Map(font.codepoints.map((cp, i) => [cp, i]));
        for (const [i, side] of ["a", "b"].entries()) {
          const expected = review.layouts[i].lines.flatMap((line) =>
            line.placements
              .slice(1)
              .filter((right, j) => {
                const left = line.placements[j];
                const index = lookup.get(left.codepoint) * font.codepoints.length + lookup.get(right.codepoint);
                return font.tables[0][index] !== font.tables[1][index];
              })
              .map((right) => right.index),
          );
          for (const scale of ["native", "zoom"]) {
            const canvas = document.getElementById(side + "-" + scale);
            const overlay = canvas.parentElement.querySelector("svg");
            const actual = [...overlay.querySelectorAll("line")].map((mark) => Number(mark.dataset.pairIndex));
            if (JSON.stringify(expected) !== JSON.stringify(actual))
              throw new Error("Underline does not match varying same-line pair occurrences");
            if (overlay.hasAttribute("hidden")) throw new Error("Underlines unexpectedly hidden");
            const rect = overlay.getBoundingClientRect(),
              ink = canvas.getBoundingClientRect();
            if (rect.width !== ink.width || rect.height !== ink.height)
              throw new Error("Underline overlay changed scale");
            for (const mark of overlay.querySelectorAll("line")) {
              const x1 = Number(mark.getAttribute("x1")),
                x2 = Number(mark.getAttribute("x2")),
                y = Number(mark.getAttribute("y1"));
              if (!(x1 >= 0 && x2 > x1 && x2 <= canvas.width && y > 0 && y < canvas.height))
                throw new Error("Underline outside drawing bounds");
            }
          }
        }
        return 4;
      });
      wrapDifferences += await page.evaluate(() => {
        const [a, b] = SpacingBlindReview.layouts;
        return JSON.stringify(a.lines.map((l) => l.placements.map((p) => p.index))) !==
          JSON.stringify(b.lines.map((l) => l.placements.map((p) => p.index)))
          ? 1
          : 0;
      });
      assert.deepEqual(
        await page.evaluate(() => SpacingBlindReview.selection().order),
        initialOrder,
        "A/B must retain their meaning for chat feedback",
      );
    }
  }
  assert.ok(wrapDifferences > 0, "natural wrapping differences must remain visible");
  await page.locator("#font").selectOption("0");
  await page.locator("#preset").selectOption("lynx-lowercase");
  assert.ok((await page.locator(".pair-underlines line").count()) > 0);
  const beforeToggle = await page.locator("#a-native").evaluate((canvas) => canvas.toDataURL());
  await page.locator("#underline").uncheck();
  assert.equal(await page.locator(".pair-underlines[hidden]").count(), 4);
  assert.equal(
    await page.locator("#a-native").evaluate((canvas) => canvas.toDataURL()),
    beforeToggle,
    "annotations must not change glyph pixels",
  );
  await page.locator("#underline").check();
  for (const width of [390, 728, 1200]) {
    await page.setViewportSize({ width, height: 1100 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "page overflows viewport");
    const frames = await page
      .locator(".native")
      .evaluateAll((nodes) => nodes.map((n) => n.getBoundingClientRect().top));
    if (width > 540) assert.equal(frames[0], frames[1], "native reading panes align");
  }
  for (const scale of ["native", "enlarged"]) {
    await page
      .locator("." + scale)
      .first()
      .evaluate((p) => (p.scrollTop = (p.scrollHeight - p.clientHeight) * 0.37));
    await page.waitForTimeout(150);
    const progress = await page
      .locator("." + scale)
      .evaluateAll((nodes) => nodes.map((p) => p.scrollTop / (p.scrollHeight - p.clientHeight)));
    assert.ok(Math.abs(progress[0] - progress[1]) < 0.01, "reading progress scroll synchronization");
  }
  await page.locator("#method-details > summary").click();
  await page.locator("#reveal").click();
  assert.equal(await page.locator("#methods").isVisible(), true);
  assert.equal(await page.locator("#label-a").textContent(), "A · " + expectedData.arms[initialOrder[0]]);
  assert.deepEqual(await page.evaluate(() => SpacingBlindReview.selection().order), initialOrder);
  assert.deepEqual(errors, []);
  assert.deepEqual(network, []);
  const report = {
    status: "passed",
    fonts: expectedData.fonts.length,
    presets: expectedData.presets.length,
    wholeTextFixtures: parity,
    canvasChecks,
    wrapDifferences,
    responsiveWidths: [390, 728, 1200],
    shortExcerptPythonChecks: shortChecks,
    underlineChecks,
    annotationToggle: true,
    stableLabels: true,
    chatFeedback: true,
    browserErrors: errors,
    networkRequests: network,
  };
  await writeFile(resolve(root, "browser-verification.json"), JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
}
