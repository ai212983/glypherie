// Real-page validation for the Class-L staged site over file://.
// No HTTP server, no standalone harness: drives the actual staged
// page (worker + builder paths, offline embedded bytes, captured
// text) in headless Chromium and measures jobs/caches, not timing
// alone. True cached target changes must cause ZERO score jobs;
// zoom/opacity zero score/map rebuild; novel pairs compute only the
// missing pair. Cleans up tabs and browser before exit.
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createRequire } from "node:module";

// Package-resolved browser driver: playwright-core comes from the
// workspace web app's pinned install, never an absolute path.
const require = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const { chromium } = require("playwright-core");

const dir = dirname(fileURLToPath(import.meta.url));
const root = join(dir, "../..");
const stage = resolve(
  root,
  process.argv[2] || "out/diagnostics/contextual-spacing/yinyang-normalization-repair/page-staging",
);
const boot = JSON.parse(readFileSync(join(stage, "boot.json"), "utf8"));
const pageUrl = pathToFileURL(join(stage, "index.html")).href;
const perf = { url: pageUrl, steps: {} };
const errors = [];

function summary(page) {
  return page.evaluate(() => ({
    summary: window.YY_SUMMARY || null,
    batch: window.__yyLastBatch || null,
    sampleNote: document.getElementById("yy-sample-note").textContent,
    explainNote: document.getElementById("yy-explain-note").textContent,
    textError: document.getElementById("yy-text-e").textContent,
  }));
}
async function settle(page, expect = {}, timeoutMs = 180000) {
  // Generation-aware: the expected YY_SUMMARY values must be painted,
  // so a stale pre-action summary never satisfies the wait.
  await page.waitForFunction(
    (exp) => {
      const s = window.YY_SUMMARY;
      if (!(s && s.origins && s.coupling && s.pairLayers !== undefined)) return false;
      for (const k of Object.keys(exp)) {
        if (s[k] !== exp[k]) return false;
      }
      return true;
    },
    expect,
    { timeout: timeoutMs },
  );
  // Field layers paint in a trailing batch; wait for quiescence.
  await page.waitForFunction(
    () => {
      const t = document.getElementById("yy-explain-note").textContent;
      return !/Updating fields/.test(t);
    },
    null,
    { timeout: timeoutMs },
  );
}
async function setNumeric(page, id, value) {
  await page.fill(`#${id}`, String(value));
  await page.dispatchEvent(`#${id}`, "change");
}

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(String(e)));
  const t0 = Date.now();
  await page.goto(pageUrl);
  await settle(page, { target: 8, reach: 12 });
  perf.steps.coldDefaultMs = Date.now() - t0;
  let s = await summary(page);
  assert.equal(s.summary.caseId, "roboto-16");
  assert.equal(s.summary.profile, "mono");
  assert.equal(s.summary.target, 8.0);
  assert.equal(s.summary.reach, 12);
  assert.equal(s.summary.falloff, 2.0);
  assert.ok(s.summary.origins.length > 0, "origins recorded");
  assert.ok(s.summary.pairLayers > 0, "field layers painted");
  assert.ok(s.summary.coupling.length > 1, "coupling diagnostics present");
  assert.ok(
    s.summary.coupling.every((l) => !/MISMATCH/.test(l)),
    "map reduction ok",
  );
  assert.equal(s.sampleNote, "", `sample note clean (got: ${s.sampleNote})`);
  perf.steps.cold = {
    scoreCalls: s.summary.scoreCalls,
    contribHits: s.summary.contribHits,
    contribMisses: s.summary.contribMisses,
    pairLayers: s.summary.pairLayers,
  };
  const origins8 = s.summary.origins.join("|");

  // Target-only 8 -> 12: zero score jobs, choices re-derive.
  await setNumeric(page, "yy-spacing-n", "12");
  await settle(page, { target: 12 });
  s = await summary(page);
  assert.equal(s.summary.target, 12);
  assert.equal(s.summary.scoreCalls, perf.steps.cold.scoreCalls, "target-only causes zero score jobs");
  assert.ok(s.summary.origins.join("|") !== origins8, "choices re-derived");
  perf.steps.targetOnly = { scoreCalls: s.summary.scoreCalls };

  // Exact off-grid value preserved; zero usable; negative rejected.
  await setNumeric(page, "yy-spacing-n", "8.02");
  await settle(page, { target: 8.02 });
  s = await summary(page);
  assert.equal(s.summary.target, 8.02);
  await setNumeric(page, "yy-spacing-n", "0");
  await settle(page, { target: 0 });
  s = await summary(page);
  assert.equal(s.summary.target, 0);
  assert.equal(s.summary.scoreCalls, perf.steps.cold.scoreCalls, "zero target causes zero score jobs");
  await setNumeric(page, "yy-spacing-n", "-1");
  await page.waitForTimeout(400);
  s = await summary(page);
  assert.equal(s.summary.target, 0, "negative rejected, last valid kept");
  const spacingErr = await page.textContent("#yy-spacing-e");
  assert.ok(/finite and >= 0/.test(spacingErr), "rejection message shown");
  // Restore to 8 for the remaining steps.
  await setNumeric(page, "yy-spacing-n", "8");
  await settle(page, { target: 8 });

  // Novel pair: in-repertoire, absent from shipped tables.
  const kase = boot.cases.find((c) => c.id === "roboto-16");
  const glyphs = kase.profiles.mono.glyphs;
  const shipped = new Set(
    Object.keys(
      JSON.parse(
        readFileSync(join(stage, "data", "roboto-16-mono.js"), "utf8")
          .split("=")
          .pop()
          .replace(/;\s*$/, ""),
      ).pairs,
    ),
  );
  const cps = Object.keys(glyphs).filter((cp) => glyphs[cp].w > 0 && glyphs[cp].h > 0 && cp !== "32");
  let novel = null;
  outer: for (const a of cps)
    for (const b of cps) {
      const pair = String.fromCodePoint(Number(a)) + String.fromCodePoint(Number(b));
      if (!shipped.has(pair)) {
        novel = pair;
        break outer;
      }
    }
  assert.ok(novel, "novel pair exists");
  const before = (await summary(page)).summary.scoreCalls;
  await page.fill("#yy-text", novel);
  await page.dispatchEvent("#yy-text", "input");
  await settle(page, { text: novel });
  s = await summary(page);
  assert.equal(
    s.summary.scoreCalls,
    before + 1,
    `novel pair computes only missing (got +${s.summary.scoreCalls - before})`,
  );
  assert.equal(s.textError, "", "novel text parses");
  // Back to sample text: computed cache reuse, zero new jobs.
  await page.fill("#yy-text", kase.text);
  await page.dispatchEvent("#yy-text", "input");
  await settle(page, { text: kase.text });
  s = await summary(page);
  assert.equal(s.summary.scoreCalls, before + 1, "cached text reuses computed pairs");
  // Same novel pair again: previously-missing (computed) set now hits
  // the computed cache, distinguishing missing-compute from cached-hit.
  await page.fill("#yy-text", novel);
  await page.dispatchEvent("#yy-text", "input");
  await settle(page, { text: novel });
  s = await summary(page);
  assert.equal(s.summary.scoreCalls, before + 1, "previously computed pair hits cache");
  await page.fill("#yy-text", kase.text);
  await page.dispatchEvent("#yy-text", "input");
  await settle(page, { text: kase.text });
  perf.steps.novelPair = { pair: novel, scoreCalls: s.summary.scoreCalls };

  // Reach change with a superseding edit: latest generation wins.
  const tReach = Date.now();
  await setNumeric(page, "yy-reach-n", "13");
  await setNumeric(page, "yy-spacing-n", "9");
  await settle(page, { reach: 13, target: 9 });
  perf.steps.reachCancelMs = Date.now() - tReach;
  s = await summary(page);
  assert.equal(s.summary.reach, 13);
  assert.equal(s.summary.target, 9);
  assert.equal(s.textError, "", "no text errors after cancel path");
  perf.steps.reachCancel = { scoreCalls: s.summary.scoreCalls, reach: s.summary.reach, target: s.summary.target };
  // Back to fast geometry.
  await setNumeric(page, "yy-reach-n", "12");
  await setNumeric(page, "yy-spacing-n", "8");
  await settle(page, { reach: 12, target: 8 });

  // One-off falloff move: full geometry rescore, then back to tables.
  const tFall = Date.now();
  const callsBeforeFall = (await summary(page)).summary.scoreCalls;
  await setNumeric(page, "yy-falloff-n", "2.5");
  await settle(page, { falloff: 2.5 });
  s = await summary(page);
  perf.steps.falloff = { ms: Date.now() - tFall, newJobs: s.summary.scoreCalls - callsBeforeFall };
  assert.ok(s.summary.scoreCalls > callsBeforeFall, "off-geometry falloff rescoring happens");
  assert.ok(s.summary.pairLayers > 0, "falloff layers repainted");
  await setNumeric(page, "yy-falloff-n", "2");
  await settle(page, { falloff: 2 });

  // No-wrap: long single lines scroll horizontally, never rewrap.
  const wrap = await page.evaluate(() => ({
    attr: document.getElementById("yy-text").getAttribute("wrap"),
    whiteSpace: getComputedStyle(document.getElementById("yy-text")).whiteSpace,
    overflowX: getComputedStyle(document.getElementById("yy-text")).overflowX,
  }));
  assert.equal(wrap.attr, "off");
  assert.equal(wrap.whiteSpace, "pre");
  assert.equal(wrap.overflowX, "auto");

  // Zoom 2x/4x: zero score/map rebuild.
  const w1 = await page.evaluate(() => document.getElementById("yy-original").width);
  s = await summary(page);
  const callsBeforeZoom = s.summary.scoreCalls,
    missBeforeZoom = s.summary.contribMisses;
  await page.selectOption("#yy-zoom", "2");
  await page.waitForTimeout(600);
  await page.selectOption("#yy-zoom", "4");
  await page.waitForTimeout(600);
  const w4 = await page.evaluate(() => document.getElementById("yy-original").width);
  s = await summary(page);
  assert.equal(w4, w1 * 4, "zoom rescales cached display");
  assert.equal(s.summary.scoreCalls, callsBeforeZoom, "zoom causes zero score jobs");
  assert.equal(s.summary.contribMisses, missBeforeZoom, "zoom causes zero map rebuilds");
  await page.selectOption("#yy-zoom", "1");
  await page.waitForTimeout(600);

  // Opacity: zero score/map rebuild. The layered heatmap removed the
  // palette text entry; the opacity slider is the surviving cached
  // display control.
  const missBeforeColor = (await summary(page)).summary.contribMisses;
  const callsBeforeColor = (await summary(page)).summary.scoreCalls;
  await page.locator("#yy-letter-alpha").fill("40");
  await page.waitForTimeout(600);
  s = await summary(page);
  assert.equal(s.summary.scoreCalls, callsBeforeColor, "opacity causes zero score jobs");
  assert.equal(s.summary.contribMisses, missBeforeColor, "opacity causes zero map rebuilds");

  // Profile switch: gray paints with its own caches, no stale mono.
  await page.check('input[name="profile"][value="gray"]');
  await settle(page, { profile: "gray" });
  s = await summary(page);
  assert.equal(s.summary.profile, "gray");
  assert.ok(s.summary.pairLayers > 0, "gray layers painted");
  perf.steps.gray = { scoreCalls: s.summary.scoreCalls, pairLayers: s.summary.pairLayers };
  await page.check('input[name="profile"][value="mono"]');
  await settle(page, { profile: "mono" });

  // Memory where measurable.
  perf.steps.memory = await page.evaluate(() =>
    performance.memory
      ? {
          usedJSHeapSize: performance.memory.usedJSHeapSize,
          totalJSHeapSize: performance.memory.totalJSHeapSize,
        }
      : null,
  );

  // Multiline + 10-line cap: 12 lines shown as first 10 with a note.
  const long = Array.from({ length: 12 }, () => "ab").join("\n");
  await page.fill("#yy-text", long);
  await page.dispatchEvent("#yy-text", "input");
  await settle(page, { text: long });
  s = await summary(page);
  assert.equal(s.summary.shownLines, 10, "line cap applied");
  assert.ok(/first 10 of 12/.test(s.sampleNote), `cap note shown (got: ${s.sampleNote})`);
  // Tab character: rejected with a named error, last valid view kept.
  await page.fill("#yy-text", "a\tb");
  await page.dispatchEvent("#yy-text", "input");
  await page.waitForTimeout(800);
  s = await summary(page);
  assert.ok(/U\+0009/.test(s.textError), `tab error names codepoint (got: ${s.textError})`);
  assert.equal(s.summary.shownLines, 10, "invalid draft keeps last valid view");
  await page.click("#yy-text-restore");
  await settle(page, { text: kase.text });
  await page.close();

  // Same-engine main-thread fallback: with Worker unavailable the
  // page still reaches ready through the inlined-bytes fallback path.
  const fb = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  fb.on("console", (m) => {
    if (m.type() === "error") errors.push(`fallback: ${m.text()}`);
  });
  fb.on("pageerror", (e) => errors.push(`fallback: ${String(e)}`));
  await fb.addInitScript(() => {
    window.Worker = undefined;
  });
  await fb.goto(pageUrl);
  await settle(fb, { target: 8 });
  let fs = await summary(fb);
  assert.ok(fs.summary.pairLayers > 0, "fallback paints layers");
  assert.ok(
    fs.summary.coupling.every((l) => !/MISMATCH/.test(l)),
    "fallback map reduction ok",
  );
  await setNumeric(fb, "yy-spacing-n", "12");
  await settle(fb, { target: 12 });
  fs = await summary(fb);
  assert.equal(fs.summary.target, 12);
  perf.steps.fallback = { pairLayers: fs.summary.pairLayers, scoreCalls: fs.summary.scoreCalls };
  await fb.close();

  // Mobile viewport: fresh load, no errors, no body overflow.
  const mob = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true });
  mob.on("console", (m) => {
    if (m.type() === "error") errors.push(`mobile: ${m.text()}`);
  });
  mob.on("pageerror", (e) => errors.push(`mobile: ${String(e)}`));
  await mob.goto(pageUrl);
  await settle(mob, { target: 8 });
  const overflow = await mob.evaluate(() => ({
    scrollW: document.documentElement.scrollWidth,
    innerW: window.innerWidth,
  }));
  assert.ok(overflow.scrollW <= overflow.innerW + 1, `mobile body overflow: ${JSON.stringify(overflow)}`);
  perf.steps.mobile = overflow;
  await mob.close();
} finally {
  await browser.close();
}
assert.deepEqual(errors, [], `console/page errors: ${JSON.stringify(errors.slice(0, 5))}`);
mkdirSync(join(stage, "validation"), { recursive: true });
writeFileSync(join(stage, "validation", "perf-browser.json"), JSON.stringify(perf, null, 2) + "\n");
console.log(JSON.stringify({ ok: true, perf }));
