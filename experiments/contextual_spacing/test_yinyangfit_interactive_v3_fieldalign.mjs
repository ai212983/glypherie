// cspell:words bbox cstar multiword yinyang yinyangfit
// Position/alignment regression for the whole-text field view: every shown
// letter must carry its own slate field at its laid-out origin, on every
// line, at every zoom, in both profiles. Red-capable: the wide-displaced
// repeat scenario ("H<8sp>H" layout, no interaction cover) discriminates
// stacking with a wide bound (red: exactly 0 exclusive slate at the later
// letters; green: 770+ source px at bound 150), because the second letter
// sits two reaches past the first letter's field. Crowded multiword
// scenarios use a presence bound (10; observed green floor 22) that still
// catches total-detachment breakages (null lattices, frame clips, dropped
// line offsets, zoom errors) without penalizing shared halos between
// adjacent letters. Pixel evidence only; map values never asserted here.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve, dirname } from "node:path";
import { mkdirSync } from "node:fs";
import { pathToFileURL, fileURLToPath } from "node:url";

const require = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const { chromium } = require("playwright-core");
const root = dirname(fileURLToPath(import.meta.url));
const site = process.argv[2]
  ? resolve(process.argv[2])
  : resolve(root, "../../out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/site-reviewed");
const evidence = process.argv[3]
  ? resolve(process.argv[3])
  : resolve(root, "../../out/diagnostics/contextual-spacing/yinyang-field-placement");
mkdirSync(evidence, { recursive: true });

// In-page pixel analysis on one canvas: ink clusters (opaque dark, mono or
// gray) grouped into bands/column groups, then every slate pixel
// (blue-gray slate role only: b > g >= r, darker than paper; orange and
// ink excluded) attributed to the nearest group whose ink bbox is within a
// (reach + 3) source-px halo. A field stacked at the first origin leaves
// every other group's exclusive zone bare; a registered field fills each
// zone. Counts normalize by the device-pixel unit so zoom 1/2/4 shares one
// bound in source-px units.
const ANALYZE = (canvasId) => {
  const c = document.getElementById(canvasId);
  const W = c.width,
    H = c.height;
  const d = c.getContext("2d").getImageData(0, 0, W, H).data;
  const z = (window.YY_SUMMARY && window.YY_SUMMARY.zoom) || 1;
  const unit = 2 * z;
  const px = (x, y) => (y * W + x) * 4;
  const isInk = (i) => d[i + 3] > 0 && Math.max(d[i], d[i + 1], d[i + 2]) < 100;
  const isSlate = (i) => {
    if (d[i + 3] === 0 || isInk(i)) return false;
    if (!(d[i + 2] > d[i + 1] && d[i + 1] >= d[i])) return false;
    return 255 - d[i + 2] > 12;
  };
  const rowInk = new Array(H).fill(false);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      if (isInk(px(x, y))) {
        rowInk[y] = true;
        break;
      }
    }
  }
  const bands = [];
  let start = -1;
  const bandGap = Math.max(2, Math.round(4 * unit));
  for (let y = 0; y <= H; y++) {
    const ink = y < H && rowInk[y];
    if (ink && start < 0) start = y;
    if (!ink && start >= 0) {
      let gap = 0;
      while (y + gap < H && !rowInk[y + gap]) gap++;
      if (y + gap >= H || gap > bandGap) {
        bands.push([start, y]);
        start = -1;
      }
    }
  }
  const colGap = Math.max(2, Math.round(2 * unit));
  const haloR = Math.round(15 * unit);
  const groups = [];
  for (const [y0, y1] of bands) {
    const colInk = new Array(W).fill(false);
    for (let x = 0; x < W; x++) {
      for (let y = y0; y < y1; y++) {
        if (isInk(px(x, y))) {
          colInk[x] = true;
          break;
        }
      }
    }
    let g0 = -1;
    for (let x = 0; x <= W; x++) {
      const ink = x < W && colInk[x];
      if (ink && g0 < 0) g0 = x;
      if (!ink && g0 >= 0) {
        let x1 = x;
        while (x1 < W && !colInk[x1]) x1++;
        let gap = 0;
        for (let gx = g0; gx < x1; gx++) if (!colInk[gx]) gap++;
        if (x1 >= W || (x1 - x > colGap && gap > colGap)) {
          groups.push([g0, x, y0, y1]);
          g0 = -1;
        }
        x = x1 - 1;
        if (x1 < W && colInk[x1] && g0 < 0) g0 = x1;
      }
    }
    if (g0 >= 0) groups.push([g0, W, y0, y1]);
  }
  const rectDist2 = (x, y, g) => {
    const dx = x < g[0] ? g[0] - x : x >= g[1] ? x - g[1] + 1 : 0;
    const dy = y < g[2] ? g[2] - y : y >= g[3] ? y - g[3] + 1 : 0;
    return dx * dx + dy * dy;
  };
  const halos = new Array(groups.length).fill(0);
  const inks = new Array(groups.length).fill(0);
  for (let k = 0; k < groups.length; k++) {
    const [x0, x1, y0, y1] = groups[k];
    for (let y = y0; y < y1; y++) {
      for (let x = x0; x < x1; x++) if (isInk(px(x, y))) inks[k]++;
    }
  }
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const i = px(x, y);
      if (!isSlate(i)) continue;
      let best = -1,
        bestD = haloR * haloR + 1;
      for (let k = 0; k < groups.length; k++) {
        const dd = rectDist2(x, y, groups[k]);
        if (dd < bestD) {
          bestD = dd;
          best = k;
        }
      }
      if (best >= 0 && bestD <= haloR * haloR) halos[best]++;
    }
  }
  return {
    canvas: canvasId,
    zoom: z,
    unit,
    W,
    H,
    groups: groups.map((g, k) => ({
      x0: g[0],
      x1: g[1],
      y0: g[2],
      y1: g[3],
      ink: inks[k] / (unit * unit),
      halo: halos[k] / (unit * unit),
    })),
  };
};

const browser = await chromium.launch({ headless: true });
const errors = [];
const report = {};
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(pathToFileURL(resolve(site, "index.html")).href);
  await page.waitForFunction(() => window.YY_TABLES && window.YY_TABLES["roboto-16-mono"], null, { timeout: 30000 });
  const settled = () =>
    page.waitForFunction(
      () =>
        document.getElementById("yy-sample-note").textContent !== "Updating spacing…" &&
        document.getElementById("yy-explain-note").textContent !== "Updating fields…" &&
        window.YY_SUMMARY &&
        window.YY_SUMMARY.pairLayers !== undefined,
      null,
      { timeout: 180000 },
    );
  await settled();
  const analyze = (id) => page.evaluate(ANALYZE, id);
  const fillText = async (text) => {
    await page.locator("#yy-text").fill(text);
    await page.waitForFunction(
      (want) => window.YY_SUMMARY?.text === want && window.YY_SUMMARY.pairLayers !== undefined,
      text,
      { timeout: 180000 },
    );
    await settled();
  };
  // wantGroups null skips the count (fragmented scripts); every resolved
  // group must still carry its own exclusive-zone slate.
  const checkHalos = (res, wantGroups, minHalo, label) => {
    report[label] = res;
    if (wantGroups !== null) {
      assert.equal(res.groups.length, wantGroups, `${label}: ${res.groups.length} letter groups, want ${wantGroups}`);
    }
    for (const [i, g] of res.groups.entries()) {
      assert.ok(
        g.halo >= minHalo,
        `${label} group ${i} [${g.x0},${g.x1})x[${g.y0},${g.y1}): ` +
          `exclusive slate ${g.halo.toFixed(1)}, want >= ${minHalo}`,
      );
    }
  };

  // Wide-displaced repeats, slate only (spaces carry no pairs): the second
  // H sits two reaches past the first letter's field, so exclusive zones
  // are contamination-free. Same codepoint at three origins.
  const WIDE = "H        H\n        H";
  await fillText(WIDE);
  checkHalos(await analyze("yy-explain-field"), 3, 150, "spaced-repeats");
  await page
    .evaluate(() => document.getElementById("yy-explain-field").toDataURL())
    .then(async (url) => {
      const { writeFileSync } = await import("node:fs");
      writeFileSync(resolve(evidence, "field-h-repeats.png"), Buffer.from(url.split(",")[1], "base64"));
    });

  // multiword default with contribution muted: pure letter field at every fragment.
  await page.locator("#yy-text-restore").click();
  await settled();
  await page.locator("#yy-contrib-alpha").fill("0");
  assert.equal(await page.evaluate(() => window.YY_SUMMARY.contribAlpha), 0, "contribution muted");
  checkHalos(await analyze("yy-explain-field"), null, 10, "default-slate-only");
  await page.locator("#yy-contrib-alpha").fill("100");

  // Translating the ink (target move) must translate the fields identically.
  const cstarBefore = await page.locator("#yy-spacing-n").inputValue();
  await page.locator("#yy-spacing-n").fill(String(Math.min(128, Number(cstarBefore) + 8)));
  await page.locator("#yy-spacing-n").press("Enter");
  await settled();
  checkHalos(await analyze("yy-explain-field"), null, 10, "default-after-cstar-move");
  await page.locator("#yy-reset").click();
  await settled();

  // Bearings: italic sample, both profiles.
  await page.locator("#yy-sample").selectOption("roboto-italic-16");
  await settled();
  checkHalos(await analyze("yy-explain-field"), null, 10, "italic-mono");
  await page.locator('input[name="profile"][value="gray"]').check();
  await settled();
  checkHalos(await analyze("yy-explain-field"), null, 10, "italic-gray");
  await page.locator('input[name="profile"][value="mono"]').check();
  await page.locator("#yy-sample").selectOption("roboto-16");
  await settled();

  // Zoom 1/2/4: the same exclusive halos at native scale.
  for (const z of ["1", "2", "4"]) {
    await page.locator("#yy-zoom").selectOption(z);
    const res = await analyze("yy-explain-field");
    assert.equal(res.zoom, Number(z), `zoom ${z} recorded`);
    checkHalos(res, null, 10, `default-zoom-${z}`);
  }
  await page.locator("#yy-zoom").selectOption("1");

  // Unwrapped long line: one repeated codepoint reused at many origins.
  const LONG = "n  ".repeat(20).trimEnd();
  await fillText(LONG);
  checkHalos(await analyze("yy-explain-field"), 20, 150, "long-line");
  await page.locator("#yy-text-restore").click();
  await settled();

  // Cache history: converging edits paint identical fields.
  const shot = () => page.locator("#yy-explain-field").evaluate((c) => c.toDataURL());
  await fillText("H");
  await fillText(WIDE);
  const viaH = await shot();
  await page.goto(pathToFileURL(resolve(site, "index.html")).href);
  await page.waitForFunction(() => window.YY_TABLES && window.YY_TABLES["roboto-16-mono"], null, { timeout: 30000 });
  await settled();
  await fillText(WIDE);
  assert.equal(await shot(), viaH, "converging histories paint identical fields");
  report.historyMatch = true;

  const out = JSON.stringify({ errors, report }, null, 1);
  const { writeFileSync } = await import("node:fs");
  writeFileSync(resolve(evidence, "field-align.json"), out + "\n");
  console.log(
    `groups/halos: ${JSON.stringify(
      Object.fromEntries(
        Object.entries(report)
          .filter(([, v]) => v && v.groups)
          .map(([k, v]) => [k, v.groups.map((g) => Math.round(g.halo))]),
      ),
    )}`,
  );
} finally {
  await browser.close();
}
assert.deepEqual(errors, [], `zero page errors (got ${JSON.stringify(errors)})`);
console.log("field alignment checks passed");
