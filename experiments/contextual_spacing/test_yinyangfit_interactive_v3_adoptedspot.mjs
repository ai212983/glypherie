// Adopted-page spot checks (P4 adoption): cold settle, zero-scoring
// controls, cached short-prefix restore, and bounded honest failure —
// all against the adopted active bytes with the real engine.
// Usage: node test_yinyangfit_interactive_v3_adoptedspot.mjs [--out <raw.json>]
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve, dirname } from "node:path";
import { writeFileSync } from "node:fs";
import { pathToFileURL, fileURLToPath } from "node:url";

const require = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const { chromium } = require("playwright-core");
const root = dirname(fileURLToPath(import.meta.url));
const repo = resolve(root, "../..");
const STAGE =
  process.env.STAGE || resolve(repo, "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/site-reviewed");

function hwScript(cpus, mem) {
  return `(() => {
    try { Object.defineProperty(Navigator.prototype, "hardwareConcurrency",
      { get: () => ${cpus}, configurable: true }); } catch (e) {}
    try { Object.defineProperty(Navigator.prototype, "deviceMemory",
      { get: () => ${mem}, configurable: true }); } catch (e) {}
  })();`;
}

const raw = { stage: STAGE, steps: {} };
const browser = await chromium.launch({ headless: true });
try {
  // ---- cold settle + zero-scoring controls ----
  {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errs = [];
    page.on("console", (m) => {
      if (m.type() === "error") errs.push(m.text());
    });
    page.on("pageerror", (e) => errs.push(String(e)));
    await page.addInitScript({ content: hwScript(2, 8) });
    await page.goto(pathToFileURL(resolve(STAGE, "index.html")).href);
    const calm = () =>
      page.evaluate(() => {
        const s = window.YY_SUMMARY;
        if (!(s && s.origins && s.origins.length)) return null;
        const busy = document.getElementById("yy-explain-field").getAttribute("aria-busy");
        const note = document.getElementById("yy-explain-note").textContent;
        return busy === null && note === "" ? s.origins.join("|") : null;
      });
    await page.waitForFunction(
      () => {
        const s = window.YY_SUMMARY;
        if (!(s && s.origins && s.origins.length)) return false;
        const busy = document.getElementById("yy-explain-field").getAttribute("aria-busy");
        return busy === null && document.getElementById("yy-explain-note").textContent === "";
      },
      null,
      { polling: 50, timeout: 180000 },
    );
    const starts = () => page.evaluate(() => window.__yyFlightTest.stats().starts);
    const s0 = await starts();
    // Target outside geometry, zoom, opacity: zero new scoring. The
    // layered heatmap removed the palette text entry; the opacity
    // slider is the surviving cached display control.
    await page.evaluate(() => {
      const el = document.getElementById("yy-spacing-n");
      el.value = "8.013";
      el.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await page.waitForTimeout(800);
    await page.selectOption("#yy-zoom", "2");
    await page.waitForTimeout(800);
    await page.locator("#yy-letter-alpha").fill("40");
    await page.waitForTimeout(800);
    assert.equal(await starts(), s0, "target/zoom/opacity score nothing new");
    // Show/hide fields: ink stays, score starts unchanged.
    await page.uncheck("#yy-show-fields");
    await page.waitForTimeout(800);
    await page.check("#yy-show-fields");
    await page.waitForFunction(
      () => {
        const s = window.YY_SUMMARY;
        return (
          s &&
          s.coupling !== undefined &&
          document.getElementById("yy-explain-field").getAttribute("aria-busy") === null
        );
      },
      null,
      { polling: 50, timeout: 180000 },
    );
    assert.equal(await starts(), s0, "show/hide scores nothing new");
    assert.deepEqual(errs, [], "cold + controls error-free");
    raw.steps.controls = { starts: s0 };
    await page.close();
  }

  // ---- short-prefix restore: computed once, never recomputed ----
  {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errs = [];
    page.on("console", (m) => {
      if (m.type() === "error") errs.push(m.text());
    });
    page.on("pageerror", (e) => errs.push(String(e)));
    await page.addInitScript({ content: hwScript(2, 8) });
    await page.goto(pathToFileURL(resolve(STAGE, "index.html")).href);
    await page.waitForFunction(() => window.YY_SUMMARY && window.YY_SUMMARY.origins, null, { timeout: 180000 });
    const starts = () => page.evaluate(() => window.__yyFlightTest.stats().starts);
    const settle = (want) =>
      page.waitForFunction(
        (w) => {
          const s = window.YY_SUMMARY;
          if (!(s && s.origins && s.origins.length)) return false;
          for (const k of Object.keys(w)) {
            if (s[k] !== w[k]) return false;
          }
          return (
            document.getElementById("yy-explain-field").getAttribute("aria-busy") === null &&
            document.getElementById("yy-explain-note").textContent === ""
          );
        },
        want,
        { polling: 50, timeout: 180000 },
      );
    await page.fill("#yy-text", "hello world");
    await page.waitForTimeout(600);
    await page.evaluate(() => {
      const el = document.getElementById("yy-reach-n");
      el.value = "14";
      el.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await settle({ reach: 14 });
    const c0 = await starts();
    assert.ok(c0 > 0, "short-prefix computed once on the real engine");
    const o1 = await page.evaluate(() => window.YY_SUMMARY.origins.join("|"));
    await page.fill("#yy-text", "hello");
    await page.waitForTimeout(600);
    await settle({ reach: 14 });
    assert.equal(await starts(), c0, "cached prefix restores with zero new calls");
    const o2 = await page.evaluate(() => window.YY_SUMMARY.origins.join("|"));
    assert.ok(o2 && o2 !== o1, "restore paints its own view");
    assert.deepEqual(errs, [], "restore error-free");
    raw.steps.restore = { starts: c0 };
    await page.close();
  }

  // ---- bounded failure on adopted bytes: dead engine ends honest ----
  {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errs = [];
    page.on("pageerror", (e) => errs.push(String(e)));
    page.on("crash", () => errs.push("PAGE-CRASH"));
    await page.addInitScript({
      content: "(() => { try { window.Worker = undefined; } catch (e) {} })();",
    });
    await page.goto(pathToFileURL(resolve(STAGE, "index.html")).href);
    await page.uncheck("#yy-show-fields");
    await page.waitForFunction(() => window.YY_SUMMARY && window.YY_SUMMARY.origins, null, { timeout: 180000 });
    const base = await page.evaluate(() => window.YY_SUMMARY.origins.join("|"));
    await page.evaluate(() => {
      try {
        delete window.YYWasmRT;
      } catch (e) {
        window.YYWasmRT = null;
      }
    });
    const s0 = await page.evaluate(() => window.__yyFlightTest.stats().starts);
    await page.evaluate(() => {
      const el = document.getElementById("yy-reach-n");
      el.value = "14";
      el.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await page.waitForFunction(
      () => /Engine unavailable/.test(document.getElementById("yy-explain-note").textContent),
      null,
      { timeout: 120000 },
    );
    await page.waitForTimeout(1500);
    const st = await page.evaluate(() => window.__yyFlightTest.stats());
    assert.ok(st.starts - s0 <= 2, "bounded attempts, no redispatch loop");
    assert.equal(st.running, 0, "no running keys leaked");
    assert.equal(
      await page.evaluate(() => document.getElementById("yy-explain-field").getAttribute("aria-busy")),
      null,
      "busy cleared on honest error",
    );
    assert.equal(await page.evaluate(() => window.YY_SUMMARY.origins.join("|")), base, "last valid view retained");
    assert.ok(!errs.some((e) => /Maximum call stack|PAGE-CRASH/.test(String(e))), "no recursion crash");
    raw.steps.failure = { extraStarts: st.starts - s0 };
    await page.close();
  }
} finally {
  await browser.close();
}

const outPath = process.argv.includes("--out")
  ? process.argv[process.argv.indexOf("--out") + 1]
  : resolve(
      repo,
      "out/diagnostics/contextual-spacing/yinyang-update-performance/wave3/adoption-p4/raw-adoptedspot.json",
    );
writeFileSync(outPath, JSON.stringify(raw, null, 2) + "\n");
console.log("adoptedspot: cold, zero-work controls, cached restore, bounded failure");
