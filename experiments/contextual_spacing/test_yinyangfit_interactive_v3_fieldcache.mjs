// cspell:words yinyang yinyangfit
// Regression for R-RT-01: the letter-field cache must key the display frame.
//
// Drives the actual text-edit call site in real Chromium: two edit histories
// converging on the same final text and settings must paint pixel-identical
// letter fields, with unchanged Source/Adjusted ink. Each history runs on a
// fresh page (empty field cache), mirroring the parent repro. Covers a
// changed frame origin and dimensions (single line) and a multiline frame
// change, on the working page and the editable demo.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve, dirname } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const require = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const { chromium } = require("playwright-core");
const root = dirname(fileURLToPath(import.meta.url));
const site = resolve(
  root,
  process.argv[2] || "../../out/diagnostics/contextual-spacing/yinyang-browser-integration/main/staging/site-full",
);
const demoFile = resolve(
  root,
  "../../out/diagnostics/contextual-spacing/yinyang-editable-preview/yinyang-live-demo.html",
);

const browser = await chromium.launch({ headless: true });
const errors = [];
const sizes = {};
try {
  const readCanvases = ([fieldId, inkIds]) => {
    const shot = (id) => {
      const c = document.getElementById(id);
      return { url: c.toDataURL(), size: [c.width, c.height] };
    };
    return { field: shot(fieldId), ink: Object.fromEntries(inkIds.map((id) => [id, shot(id)])) };
  };
  const settleField = async (target, fieldSel, noteSel) => {
    let prev = null;
    for (let i = 0; i < 30; i++) {
      await target.waitForTimeout(400);
      if (noteSel) {
        const note = await target.locator(noteSel).textContent();
        if (note === "Updating spacing…") continue;
      }
      // Main-page field layers arrive after the ink paint; wait for the
      // summary too. The standalone demo has its own summary instead.
      if (noteSel) {
        const summary = await target.evaluate(() => window.YY_SUMMARY || null);
        if (!summary || summary.pairLayers === undefined) continue;
      }
      const cur = await target.locator(fieldSel).evaluate((c) => c.toDataURL());
      if (cur === prev) return cur;
      prev = cur;
    }
    throw new Error(`field never settled: ${fieldSel}`);
  };
  // One edit history on a fresh page, so the field cache starts empty.
  const runPageHistory = async (steps) => {
    const target = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    target.on("pageerror", (error) => errors.push(error.message));
    try {
      await target.goto(pathToFileURL(resolve(site, "index.html")).href);
      await target.waitForFunction(() => window.YY_TABLES && window.YY_TABLES["roboto-16-mono"], { timeout: 30000 });
      await target.waitForFunction(
        () => document.getElementById("yy-sample-note").textContent !== "Updating spacing…",
        { timeout: 120000 },
      );
      let mid = null;
      for (const [i, text] of steps.entries()) {
        await target.locator("#yy-text").fill(text);
        // Text edits debounce 250ms before the guarded render; the fast
        // path then paints synchronously, so wait for pixel stability.
        await target.waitForTimeout(500);
        await settleField(target, "#yy-explain-field", "#yy-sample-note");
        if (i === 0 && steps.length > 1) {
          mid = await target.evaluate(readCanvases, ["yy-explain-field", ["yy-original", "yy-adjusted"]]);
        }
      }
      const fin = await target.evaluate(readCanvases, ["yy-explain-field", ["yy-original", "yy-adjusted"]]);
      return { mid, fin };
    } finally {
      await target.close();
    }
  };

  const N60 = "n".repeat(60);
  const fresh = await runPageHistory([N60]);
  const reused = await runPageHistory(["nn", N60]);
  assert.ok(reused.mid, "prefix history paints an intermediate frame");
  assert.notDeepEqual(reused.mid.field.size, fresh.fin.field.size, "prefix history must exercise a changed frame size");
  assert.deepEqual(reused.fin.field.size, fresh.fin.field.size, "final field size");
  assert.equal(
    reused.fin.field.url,
    fresh.fin.field.url,
    "same final text paints identical letter fields regardless of history",
  );
  assert.deepEqual(reused.fin.ink, fresh.fin.ink, "main Source/Adjusted ink unchanged");
  sizes.singleLineField = fresh.fin.field.size;

  const TWO = "nnnn\nnnnn";
  const freshTwo = await runPageHistory([TWO]);
  const reusedTwo = await runPageHistory(["nnnn", TWO]);
  assert.notDeepEqual(
    reusedTwo.mid.field.size,
    freshTwo.fin.field.size,
    "line growth must exercise a changed frame size",
  );
  assert.equal(
    reusedTwo.fin.field.url,
    freshTwo.fin.field.url,
    "same multiline text paints identical letter fields regardless of history",
  );
  assert.deepEqual(reusedTwo.fin.ink, freshTwo.fin.ink, "multiline ink unchanged");
  sizes.multilineField = freshTwo.fin.field.size;

  // Editable demo: the same convergence on its own field canvas.
  const runDemoHistory = async (steps) => {
    const target = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    target.on("pageerror", (error) => errors.push("demo: " + error.message));
    try {
      await target.goto(pathToFileURL(demoFile).href);
      await target.waitForFunction(() => window.DEMO_SUMMARY, { timeout: 30000 });
      for (const text of steps) {
        await target.locator("#demo-text").fill(text);
        await target.waitForTimeout(500);
        await settleField(target, "#demo-field", null);
      }
      return await target.evaluate(readCanvases, ["demo-field", ["demo-source", "demo-field-ink"]]);
    } finally {
      await target.close();
    }
  };
  const demoFresh = await runDemoHistory([N60]);
  const demoReused = await runDemoHistory(["nn", N60]);
  assert.equal(demoReused.field.url, demoFresh.field.url, "demo paints identical letter fields regardless of history");
  assert.deepEqual(demoReused.ink, demoFresh.ink, "demo ink unchanged");
  sizes.demoField = demoFresh.field.size;

  console.log(JSON.stringify(sizes));
} finally {
  await browser.close();
}
assert.deepEqual(errors, [], `zero page errors (got ${JSON.stringify(errors)})`);
console.log("field-cache frame identity: fresh and reused histories match");
