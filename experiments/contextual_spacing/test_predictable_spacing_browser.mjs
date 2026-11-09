// cspell:words lede
// Real-browser behavior check for the predictable spacing prototype page.
// Loads the offline file:// page at desktop and mobile widths, drives both
// sliders, profile, zoom, all dropdown options, pair inspection, reset and
// rapid sample switches, and requires visible comparison output without
// document overflow. Saves desktop and mobile screenshots.
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve, dirname } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const require = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const { chromium } = require("playwright-core");
const root = dirname(fileURLToPath(import.meta.url));
const directory = resolve(root, process.argv[2] || "../../out/diagnostics/contextual-spacing/predictable-spacing/site");
const boot = JSON.parse(await readFile(resolve(directory, "boot.json"), "utf8"));

const ALLOWED_NOTES = [
  "",
  "Original spacing used at this setting. Steps move in whole pixels, so small adjustments may show no change.",
  "Optical limit reached for at least one gap. Further correction keeps that placement.",
  "Loading sample data.",
];

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  await page.goto(pathToFileURL(resolve(directory, "index.html")).href);
  await page.waitForFunction(
    () => document.getElementById("ps-sample") && document.getElementById("ps-sample").options.length === 13,
    { timeout: 30000 },
  );
  await page.waitForFunction(() => window.PS_TABLES && window.PS_TABLES["roboto-16-mono"], { timeout: 30000 });
  assert.equal(await page.locator("[title]").count(), 0, "no native title tooltips");

  // Default view: short title, instruction, visible comparison.
  assert.equal(await page.locator("h1").textContent(), "Spacing");
  assert.match(await page.locator(".lede").textContent(), /optical correction and letter spacing/);
  const focusTitle = await page.locator("#ps-focus-title").textContent();
  assert.match(focusTitle, /Roboto 16 px/, `default focus is the root default sample: ${focusTitle}`);
  for (const id of ["#ps-original", "#ps-adjusted"]) {
    const size = await page.locator(id).evaluate((c) => [c.width, c.height]);
    assert.ok(size[0] > 0 && size[1] > 0, `${id} renders`);
  }
  // Original and Adjusted share magnification and alignment.
  const origBox = await page.locator("#ps-original").evaluate((c) => [c.width, c.height]);
  const adjBox = await page.locator("#ps-adjusted").evaluate((c) => [c.width, c.height]);
  assert.deepEqual(origBox, adjBox, "Original/Adjusted matched bounds");
  const assertDisplayPixels = async (target, message) => {
    for (const id of ["#ps-original", "#ps-adjusted"]) {
      const pixels = await target.locator(id).evaluate((c) => ({
        bitmapWidth: c.width,
        bitmapHeight: c.height,
        displayedWidth: c.clientWidth,
        displayedHeight: c.clientHeight,
      }));
      assert.equal(pixels.displayedWidth, pixels.bitmapWidth, `${message}: ${id} horizontal scale`);
      assert.equal(pixels.displayedHeight, pixels.bitmapHeight, `${message}: ${id} vertical scale`);
    }
  };
  await assertDisplayPixels(page, "native rendering");

  // Optical slider moves away from Source; reset returns to Source.
  const note0 = await page.locator("#ps-sample-note").textContent();
  assert.ok(ALLOWED_NOTES.includes(note0), `default note allowed: ${note0}`);
  await page.locator("#ps-optical").fill("100");
  await page.waitForFunction(() => document.getElementById("ps-optical-v").textContent === "Full");
  const capFull = await page.locator("#ps-adjusted-cap").textContent();
  assert.equal(capFull, "Adjusted.");
  await page.locator("#ps-letter").fill("4");
  await page.waitForFunction(() => document.getElementById("ps-letter-v").textContent === "+4 px");
  await page.locator("#ps-letter").fill("-2");
  await page.waitForFunction(() => document.getElementById("ps-letter-v").textContent === "-2 px");
  await page.locator("#ps-reset").click();
  await page.waitForFunction(
    () =>
      document.getElementById("ps-optical-v").textContent === "Source" &&
      document.getElementById("ps-letter-v").textContent === "0 px",
  );
  assert.equal(await page.locator("#ps-adjusted-cap").textContent(), "Adjusted (original spacing).");

  // Every dropdown option paints without errors and keeps controls.
  const options = await page.locator("#ps-sample option").evaluateAll((opts) => opts.map((o) => o.value));
  assert.equal(options.length, 13, "all root samples available");
  for (const value of options) {
    await page.locator("#ps-sample").selectOption(value);
    await page.waitForFunction((v) => window.PS_TABLES[v + "-mono"] || window.PS_TABLES[v + "-gray"], value, {
      timeout: 30000,
    });
    const title = await page.locator("#ps-focus-title").textContent();
    assert.ok(title.length > 0, `${value}: focus title paints`);
    for (const id of ["#ps-original", "#ps-adjusted"]) {
      const size = await page.locator(id).evaluate((c) => [c.width, c.height]);
      assert.ok(size[0] > 0 && size[1] > 0, `${value} ${id} renders`);
    }
  }
  // Controls survive dataset switches.
  await page.locator("#ps-optical").fill("50");
  await page.locator("#ps-sample").selectOption("literata-16");
  await page.waitForFunction(
    () =>
      (window.PS_TABLES["literata-16-mono"] || window.PS_TABLES["literata-16-gray"]) &&
      document.getElementById("ps-focus-title").textContent.includes("Literata"),
  );
  assert.equal(await page.locator("#ps-optical").inputValue(), "50", "optical control preserved across samples");

  // Rapid switches paint the latest selection, never stale data.
  await page.locator("#ps-sample").selectOption("roboto-8");
  await page.locator("#ps-sample").selectOption("rouge-script-20");
  await page.locator("#ps-sample").selectOption("literata-20");
  await page.waitForFunction(
    () =>
      (window.PS_TABLES["literata-20-mono"] || window.PS_TABLES["literata-20-gray"]) &&
      document.getElementById("ps-focus-title").textContent.includes("Literata") &&
      document.getElementById("ps-focus-title").textContent.includes("20 px"),
  );
  const rapidTitle = await page.locator("#ps-focus-title").textContent();
  assert.match(rapidTitle, /Literata 20 px/, `rapid switch lands latest: ${rapidTitle}`);

  // Profile, zoom, pair inspection and diagnostics.
  await page.getByLabel("Grayscale").check();
  await page.waitForFunction(() => document.getElementById("ps-focus-title").textContent.includes("grayscale"));
  await page.locator("#ps-zoom").selectOption("2");
  await assertDisplayPixels(page, "zoomed native rendering");
  await page.locator("#ps-zoom").selectOption("1");
  await page.locator("#ps-pairs").evaluate((d) => d.setAttribute("open", ""));
  const pairCount = await page.locator("#ps-pair option").count();
  assert.ok(pairCount > 0, "pair options present");
  const pairNote = await page.locator("#ps-pair-note").textContent();
  assert.ok(pairNote.length > 0, "pair note present");
  await page.locator("#ps-optical").fill("0");
  await page.locator("#ps-letter").fill("0");
  const grayPair = await page.evaluate(() => {
    const b = JSON.parse(document.getElementById("ps-boot").textContent);
    const ds = b.cases.find((c) => c.id === "literata-20").profiles.gray;
    const pairs = window.PS_TABLES["literata-20-gray"].pairs;
    return ds.gaps.flat().find((g) => !g.space && g.metric !== pairs[g.pair].metric)?.pair;
  });
  assert.ok(grayPair, "fixture distinguishes Gray source and endpoint metrics");
  await page.locator("#ps-pair").selectOption(grayPair);
  const checkGrayPair = async (letter) => {
    const results = await page.evaluate(
      ({ name, letter }) => {
        const b = JSON.parse(document.getElementById("ps-boot").textContent);
        const ds = b.cases.find((c) => c.id === "literata-20").profiles.gray;
        const gap = ds.gaps.flat().find((g) => g.pair === name && !g.space);
        const glyphs = [...name].map((ch) => {
          const g = ds.glyphs[String(ch.charCodeAt(0))];
          return { ...g, cover: [...g.cover].map((v) => Number(v) / 7) };
        });
        const expectedSource = Math.floor(gap.frac + 0.5);
        return [
          ["ps-pair-metric", expectedSource],
          ["ps-pair-chosen", expectedSource + letter],
        ].map(([id, step]) => {
          const [left, right] = glyphs;
          const x0 = Math.min(left.left, step + right.left);
          const y0 = Math.min(left.top, right.top);
          const expected = document.createElement("canvas");
          expected.width = Math.max(left.left + left.w, step + right.left + right.w) - x0;
          expected.height = Math.max(left.top + left.h, right.top + right.h) - y0;
          const ctx = expected.getContext("2d");
          ctx.fillStyle = "#fff";
          ctx.fillRect(0, 0, expected.width, expected.height);
          ctx.translate(-x0, -y0);
          PredictableSpacing.drawCell(ctx, "gray", left, 0, 0, 1);
          PredictableSpacing.drawCell(ctx, "gray", right, step, 0, 1);
          const actual = document.getElementById(id);
          return { id, matches: actual.toDataURL() === expected.toDataURL() };
        });
      },
      { name: grayPair, letter },
    );
    results.forEach((r) =>
      assert.ok(r.matches, `${r.id}: Gray source and letter spacing ${letter} render at expected origins`),
    );
  };
  await checkGrayPair(0);
  assert.match(await page.locator("#ps-sample-note").textContent(), /Original spacing used/);
  await page.locator("#ps-letter").fill("4");
  await checkGrayPair(4);
  assert.match(await page.locator("#ps-pair-note").textContent(), /4 px looser than original/);
  await page.locator("#ps-letter").fill("0");
  await page.locator("#ps-diagnostics-box").evaluate((d) => d.setAttribute("open", ""));
  const diagText = await page.locator("#ps-diagnostics").textContent();
  assert.match(diagText, /hu_fitted_full_density_conserved_touch/, "method disclosed");
  assert.ok(errors.length === 0, `no console errors: ${errors.join("; ")}`);

  // No document overflow at desktop width.
  const desktopOverflow = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  assert.ok(
    desktopOverflow.scroll <= desktopOverflow.client,
    `desktop no document overflow: ${JSON.stringify(desktopOverflow)}`,
  );
  await page.screenshot({ path: resolve(directory, "desktop-default.png") });

  // Mobile viewport: comparison renders, page does not overflow.
  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
  mobile.on("pageerror", (error) => errors.push("mobile: " + error.message));
  await mobile.goto(pathToFileURL(resolve(directory, "index.html")).href);
  await mobile.waitForFunction(() => window.PS_TABLES && window.PS_TABLES["roboto-16-mono"], { timeout: 30000 });
  for (const id of ["#ps-original", "#ps-adjusted"]) {
    const size = await mobile.locator(id).evaluate((c) => [c.width, c.height]);
    assert.ok(size[0] > 0 && size[1] > 0, `mobile ${id} renders`);
  }
  const overflow = await mobile.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  assert.ok(overflow.scroll <= overflow.client, `mobile no document overflow: ${JSON.stringify(overflow)}`);
  await mobile.screenshot({ path: resolve(directory, "mobile-check.png") });
  await mobile.close();

  assert.ok(errors.length === 0, `no console errors: ${errors.join("; ")}`);
  await writeFile(
    resolve(directory, "interaction-check.json"),
    JSON.stringify({ status: "passed", samples: options.length }) + "\n",
  );
  console.log(JSON.stringify({ status: "passed", samples: options.length }));
} finally {
  await browser.close();
}
