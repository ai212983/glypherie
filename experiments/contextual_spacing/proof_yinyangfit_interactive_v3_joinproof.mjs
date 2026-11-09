// Real-engine join-at-completion proof (P4): with the real WASM engine
// on file://, a view that joins running pairs mid-flight stays busy
// with no premature paint or error, then paints exactly once on the
// producer terminal with zero new engine work. Exactness is shown by
// equality against a cheap direct control (same final setting, no
// join): identical origins and identical ink pixels.
//
// Usage: node proof_yinyangfit_interactive_v3_joinproof.mjs <stageDir> --out <raw.json>
// Profiles: mono then gray. Viewport 390px. Fields hidden (production
// show-fields gate; ink/ownership path unchanged). Closes its browser.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve, dirname } from "node:path";
import { writeFileSync } from "node:fs";
import { pathToFileURL, fileURLToPath } from "node:url";

const require = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const { chromium } = require("playwright-core");
const root = dirname(fileURLToPath(import.meta.url));
const STAGE =
  process.argv[2] ||
  resolve(root, "../../out/diagnostics/contextual-spacing/yinyang-update-performance/wave3/view-completion-fix/stage");

function hwScript(cpus, mem) {
  return `(() => {
    try {
      Object.defineProperty(Navigator.prototype, "hardwareConcurrency",
        { get: () => ${cpus}, configurable: true });
    } catch (e) {}
    try {
      Object.defineProperty(Navigator.prototype, "deviceMemory",
        { get: () => ${mem}, configurable: true });
    } catch (e) {}
  })();`;
}

const raw = { stage: STAGE, profiles: {} };
const browser = await chromium.launch({ headless: true });
try {
  for (const profile of ["mono", "gray"]) {
    const out = (raw.profiles[profile] = {});
    // ---- control: same final setting, no join (cheap: 6 pairs) ----
    {
      const page = await browser.newPage({ viewport: { width: 390, height: 700 } });
      const errs = [];
      page.on("console", (m) => {
        if (m.type() === "error") errs.push(m.text());
      });
      page.on("pageerror", (e) => errs.push(String(e)));
      await page.addInitScript({ content: hwScript(2, 8) });
      await page.goto(pathToFileURL(resolve(STAGE, "index.html")).href);
      await page.uncheck("#yy-show-fields");
      if (profile !== "mono") await page.check(`input[name=profile][value=${profile}]`);
      await page.waitForFunction(() => window.YY_SUMMARY && window.YY_SUMMARY.origins, null, { timeout: 120000 });
      await page.fill("#yy-text", "Pack my box");
      await page.waitForTimeout(600);
      await page.evaluate(() => {
        const el = document.getElementById("yy-reach-n");
        el.value = "14";
        el.dispatchEvent(new Event("change", { bubbles: true }));
      });
      await page.waitForFunction(
        () => {
          const s = window.YY_SUMMARY;
          return (
            s &&
            s.origins &&
            s.origins.length === 1 &&
            s.reach === 14 &&
            document.getElementById("yy-explain-field").getAttribute("aria-busy") === null &&
            document.getElementById("yy-explain-note").textContent === ""
          );
        },
        null,
        { polling: 100, timeout: 300000 },
      );
      out.controlOrigins = await page.evaluate(() => window.YY_SUMMARY.origins.join("|"));
      out.controlPixels = (await page.screenshot()).toString("base64").length;
      out.controlShot = await page.screenshot();
      assert.equal(errs.length, 0, `${profile} control: no errors`);
      await page.close();
    }
    // ---- join: reach change in flight, subset text joins it ----
    {
      const page = await browser.newPage({ viewport: { width: 390, height: 700 } });
      const errs = [];
      page.on("console", (m) => {
        if (m.type() === "error") errs.push(m.text());
      });
      page.on("pageerror", (e) => errs.push(String(e)));
      await page.addInitScript({ content: hwScript(2, 8) });
      await page.goto(pathToFileURL(resolve(STAGE, "index.html")).href);
      await page.uncheck("#yy-show-fields");
      if (profile !== "mono") await page.check(`input[name=profile][value=${profile}]`);
      await page.waitForFunction(() => window.YY_SUMMARY && window.YY_SUMMARY.origins, null, { timeout: 120000 });
      const preOrigins = await page.evaluate(() => window.YY_SUMMARY.origins.join("|"));
      await page.evaluate(() => {
        const el = document.getElementById("yy-reach-n");
        el.value = "14";
        el.dispatchEvent(new Event("change", { bubbles: true }));
      });
      // Wait for the real dispatch: a live running call must exist
      // before the subset text can join it.
      await page.waitForFunction(() => window.__yyFlightTest && window.__yyFlightTest.stats().running > 0, null, {
        polling: 50,
        timeout: 120000,
      });
      const postsBefore = await page.evaluate(() => window.__yyFlightTest.stats().starts);
      const joinsBefore = await page.evaluate(() => window.__yyFlightTest.stats().joins);
      await page.fill("#yy-text", "Pack my box");
      await page.waitForFunction((b) => window.__yyFlightTest.stats().joins > b, joinsBefore, {
        polling: 25,
        timeout: 120000,
      });
      const joins = await page.evaluate(() => window.__yyFlightTest.stats().joins);
      out.joins = joins;
      assert.ok(joins > 0, `${profile}: subset text joined running work`);
      const postsAfterJoin = await page.evaluate(() => window.__yyFlightTest.stats().starts);
      assert.equal(postsAfterJoin, postsBefore, `${profile}: join dispatched no new engine call`);
      await page.waitForTimeout(400);
      const mid = await page.evaluate(() => ({
        note: document.getElementById("yy-explain-note").textContent,
        busy: document.getElementById("yy-explain-field").getAttribute("aria-busy"),
        origins: window.YY_SUMMARY.origins.join("|"),
      }));
      assert.equal(mid.busy, "true", `${profile}: joined view stays busy`);
      assert.ok(!/unavailable|failed twice/.test(mid.note), `${profile}: no premature paint or error`);
      assert.equal(mid.origins, preOrigins, `${profile}: stale view never paints`);
      await page.waitForFunction(
        () => {
          const s = window.YY_SUMMARY;
          return (
            s &&
            s.origins &&
            s.origins.length === 1 &&
            s.reach === 14 &&
            document.getElementById("yy-explain-field").getAttribute("aria-busy") === null &&
            document.getElementById("yy-explain-note").textContent === ""
          );
        },
        null,
        { polling: 100, timeout: 300000 },
      );
      const postsAfter = await page.evaluate(() => window.__yyFlightTest.stats().starts);
      assert.equal(postsAfter, postsBefore, `${profile}: completion posted no new call`);
      out.joinOrigins = await page.evaluate(() => window.YY_SUMMARY.origins.join("|"));
      out.joinShot = await page.screenshot();
      assert.equal(errs.length, 0, `${profile} join: no errors`);
      const st = await page.evaluate(() => window.__yyFlightTest.stats());
      assert.equal(st.running, 0, `${profile}: no running keys leaked`);
      assert.equal(st.calls, 0, `${profile}: no live calls leaked`);
      out.starts = postsAfter;
      await page.close();
    }
    assert.equal(out.joinOrigins, out.controlOrigins, `${profile}: joined paint equals direct paint`);
    assert.equal(Buffer.compare(out.joinShot, out.controlShot), 0, `${profile}: joined pixels equal direct pixels`);
    delete out.joinShot;
    delete out.controlShot;
  }
} finally {
  await browser.close();
}

const outPath = process.argv.includes("--out")
  ? process.argv[process.argv.indexOf("--out") + 1]
  : resolve(
      root,
      "../../out/diagnostics/contextual-spacing/yinyang-update-performance/wave3/view-completion-fix/raw-joinproof.json",
    );
writeFileSync(outPath, JSON.stringify(raw, null, 2) + "\n");
console.log("joinproof: exact join-at-completion in mono+gray at 390px");
