// Real-browser check for the isolated SCORE-v2 native ink comparison page.
// Loads the offline file:// page, drives all 4 samples x both profiles,
// target slider/typed/reset, diagnostics, zoom and viewports, requires the
// full JS choice parity oracle, native zoom ratios, pixel identity and no
// document overflow. Saves screenshots.
import assert from "node:assert/strict";
import { readFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve, dirname, join } from "node:path";
import { pathToFileURL } from "node:url";

const require = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const { chromium } = require("playwright-core");
const root = dirname(new URL(import.meta.url).pathname);
const directory = resolve(
  root,
  process.argv[2] || "../../out/diagnostics/contextual-spacing/yinyang-oriented-fields/visual-comparison",
);

const expected = JSON.parse(await readFile(join(directory, "checks", "expected_choices.json"), "utf8"));
await mkdir(join(directory, "checks", "screenshots"), { recursive: true });

const SAMPLES = ["roboto-16", "roboto-24", "literata-16", "literata-24"];
const PROFILES = ["mono", "gray"];
const PAIRS = ["um", "og", "AV", "To", "nn", "oo", "HH", "il"];

const browser = await chromium.launch({ headless: true });
const errors = [];
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  await page.goto(pathToFileURL(join(directory, "index.html")).href);
  await page.waitForFunction(() => window.__YY && window.__YYDATA && document.querySelectorAll("canvas").length === 24);

  // Static structure: 8 pair rows x Source/B2/Oriented canvases, no blob UI.
  assert.equal(await page.locator("section.yy-pair").count(), 8);
  assert.equal(await page.locator("canvas").count(), 24);
  assert.equal(await page.locator("#yy-pair-um .yy-badge").count(), 1);
  for (const pair of PAIRS) {
    for (const kind of ["source", "b2", "oriented"]) {
      assert.ok(await page.locator(`#yy-canvas-${pair}-${kind}`).count(), `missing canvas ${pair}/${kind}`);
    }
  }

  // Full choice parity: every oracle entry through the in-page TIE-v2 rule.
  const entries = Object.entries(expected);
  const mismatches = await page.evaluate((items) => {
    const bad = [];
    const norm = (steps) =>
      steps.map((s) => ({
        step: s.step,
        delta: s.delta,
        valid: s.valid,
        g2n: s.g2n,
        g2m: s.g2m,
      }));
    for (const [key, want] of items) {
      const [cap, pair, cstar, domain, variant] = key.split("|");
      const cs = window.__YYDATA.cases[cap][pair];
      const got = window.__YY.choose(norm(cs.steps), variant, Number(domain), Number(cstar));
      const gstep = got.empty ? null : got.step;
      if (gstep !== want.step) {
        bad.push(key + " step");
        continue;
      }
      if (want.step === null) continue;
      if (JSON.stringify(got.ties) !== JSON.stringify(want.ties)) {
        bad.push(key + " ties");
        continue;
      }
      if (got.boundary !== want.boundary) {
        bad.push(key + " boundary");
        continue;
      }
      if (Math.abs(got.mstar - want.mstar) > 1e-12 * Math.max(1, Math.abs(want.mstar))) {
        bad.push(key + " mstar");
      }
      if (bad.length > 12) break;
    }
    return bad;
  }, entries);
  assert.deepEqual(mismatches, [], `choice parity failures: ${mismatches.slice(0, 12)}`);

  // All 4 samples x both profiles render with instant table lookup.
  for (const sample of SAMPLES) {
    await page.selectOption("#yy-sample", sample);
    for (const profile of PROFILES) {
      await page.check(`input[name="yy-profile"][value="${profile}"]`);
      await page.waitForFunction(() => document.querySelectorAll("canvas").length === 24);
      const status = await page.locator("#yy-status").textContent();
      assert.match(status, /Rendered 8 pairs . 3 placements in .* ms \(precomputed table lookup/);
      for (const pair of PAIRS) {
        const note = await page.locator(`#yy-note-${pair}-oriented`).textContent();
        assert.match(note, /Oriented C\*=4/);
      }
      await page.screenshot({ path: join(directory, "checks", "screenshots", `${sample}-${profile}.png`) });
    }
  }
  await page.selectOption("#yy-sample", "roboto-16");
  await page.check('input[name="yy-profile"][value="mono"]');

  // Target slider, off-grid typed entry, invalid entry, reset.
  const before = await page.locator("#yy-note-um-oriented").textContent();
  await page.locator("#yy-target").fill("10");
  const afterSlider = await page.locator("#yy-note-um-oriented").textContent();
  assert.match(afterSlider, /Oriented C\*=10/);
  await page.locator("#yy-target-num").fill("3.7");
  await page.locator("#yy-target-num").dispatchEvent("change");
  const afterTyped = await page.locator("#yy-note-um-oriented").textContent();
  assert.match(afterTyped, /Oriented C\*=3\.7/);
  assert.equal(await page.locator("#yy-target-error").textContent(), "");
  await page.locator("#yy-target-num").fill("abc");
  await page.locator("#yy-target-num").dispatchEvent("change");
  assert.notEqual(await page.locator("#yy-target-error").textContent(), "");
  assert.equal(await page.locator("#yy-note-um-oriented").textContent(), afterTyped);
  await page.locator("#yy-target-num").fill("200");
  await page.locator("#yy-target-num").dispatchEvent("change");
  assert.notEqual(await page.locator("#yy-target-error").textContent(), "");
  await page.click("#yy-reset");
  assert.equal(await page.locator("#yy-target-num").inputValue(), "4");
  assert.equal(await page.locator("#yy-note-um-oriented").textContent(), before);

  // Diagnostic domain + manuscript variant change placements only.
  await page.evaluate(() => {
    document.querySelector("details.yy-diag").open = true;
  });
  await page.check('input[name="yy-domain"][value="6"]');
  const broad = await page.locator("#yy-meta-um").textContent();
  assert.match(broad, /over ±6/);
  await page.check('input[name="yy-variant"][value="manuscript"]');
  const man = await page.locator("#yy-meta-um").textContent();
  assert.match(man, /manuscript variant/);
  await page.screenshot({ path: join(directory, "checks", "screenshots", "roboto-16-mono-broad-manuscript.png") });
  await page.click("#yy-reset");

  // Rapid sample/profile toggling settles on a correct render.
  await page.selectOption("#yy-sample", "literata-24");
  await page.check('input[name="yy-profile"][value="gray"]');
  await page.check('input[name="yy-profile"][value="mono"]');
  await page.selectOption("#yy-sample", "roboto-16");
  await page.check('input[name="yy-profile"][value="gray"]');
  const rapid = await page.locator("#yy-note-To-oriented").textContent();
  assert.match(rapid, /Oriented C\*=4/);
  await page.check('input[name="yy-profile"][value="mono"]');

  // Zoom ratios on ALL canvases, CSS size equals backing store (no shrink),
  // and returning to 1x restores native pixel identity.
  const baseWidths = await page.evaluate(() => [...document.querySelectorAll("canvas")].map((c) => c.width));
  assert.equal(baseWidths.length, 24);
  const baseCss = await page.evaluate(() => [...document.querySelectorAll("canvas")].map((c) => c.style.width));
  for (let i = 0; i < 24; i++) assert.equal(baseCss[i], `${baseWidths[i]}px`);
  for (const z of ["2", "4"]) {
    await page.check(`input[name="yy-zoom"][value="${z}"]`);
    const widths = await page.evaluate(() =>
      [...document.querySelectorAll("canvas")].map((c) => [c.width, c.style.width]),
    );
    for (let i = 0; i < 24; i++) {
      assert.equal(widths[i][0], baseWidths[i] * Number(z), `canvas ${i} backing @${z}x`);
      assert.equal(widths[i][1], `${baseWidths[i] * Number(z)}px`, `canvas ${i} css @${z}x`);
    }
  }
  await page.check('input[name="yy-zoom"][value="1"]');
  const back = await page.evaluate(() => [...document.querySelectorAll("canvas")].map((c) => c.width));
  assert.deepEqual(back, baseWidths);

  // Gray levels are exact p/7 steps on white; mono is pure black on white.
  await page.check('input[name="yy-profile"][value="gray"]');
  const grayOk = await page.evaluate(() => {
    const allowed = new Set([255]);
    for (let p = 1; p <= 7; p++) allowed.add(Math.round(255 * (1 - p / 7)));
    for (const c of document.querySelectorAll("canvas")) {
      const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
      for (let i = 0; i < d.length; i += 4) {
        if (d[i] !== d[i + 1] || d[i] !== d[i + 2] || d[i + 3] !== 255) return false;
        if (!allowed.has(d[i])) return false;
      }
    }
    return true;
  });
  assert.ok(grayOk, "gray canvas pixels must be exact p/7 levels on white");
  await page.check('input[name="yy-profile"][value="mono"]');

  // No document overflow at desktop and mobile widths; inner rows scroll.
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 800 });
    await page.waitForTimeout(100);
    const overflow = await page.evaluate(() => ({ doc: document.documentElement.scrollWidth, win: window.innerWidth }));
    assert.ok(overflow.doc <= overflow.win + 1, `document overflow at ${width}px`);
    if (width === 390) {
      await page.screenshot({ path: join(directory, "checks", "screenshots", "mobile-390.png") });
    }
  }
  assert.deepEqual(errors, []);
  await browser.close();
  console.log(
    `browser checks passed: ${entries.length} parity entries, ` +
      `${SAMPLES.length * PROFILES.length} sample/profile renders, zoom 1x/2x/4x, 1280px + 390px`,
  );
} catch (error) {
  console.error(`BROWSER FAIL: ${error.message}`);
  console.error(`page errors: ${JSON.stringify(errors.slice(0, 8))}`);
  try {
    await browser.close();
  } catch {
    /* already closed */
  }
  process.exit(1);
}
