// Adoption spot checks on the adopted active page (offline file:// only).
//
// Page 1 (adopted site-reviewed, guarded single worker unless noted):
//   S-default    default settle: 0 score calls, layers/maps recorded,
//                pinned working set intact, no errors.
//   S-repaint    target / zoom / opacity / show-fields repaints: zero new
//                engine work each.
//   S-novel      NOVEL R14 computes, default revisit, NOVEL revisit is
//                zero work (cached revisit, no dispatch, no native enter).
//   S-restore    R14 -> R13 -> R14: the return uses the completed prefix
//                (zero new work).
//   S-invalid    invalid draft keeps the last valid view, no errors.
//   S-grayover   gray profile + 390-char text: settles with 0 errors.
//   S-fallback   Worker-disabled SHORT R14 equals the worker path and
//                restores for free (audited via main-thread counters).
// Page 2 (fresh page, audited hook_final.js native receipts, single
// worker): S-trace, one fresh actual reuse count trace with the O1
// pair texts at unknown R14:
//   T1 (18 unique pairs) starts; after merged checkpoints are observed
//   and while work is still running, T2 (20 unique pairs: 10 shared,
//   10 new) takes over. Records needed/cached/joined/new splits and
//   native enter/return per identity: shared-cached never re-enters,
//   shared-in-flight enters once under T1's job, genuinely-new enters
//   exactly once and returns once; final view exact with zero work on
//   revisit.
//
// Usage: node test_yinyangfit_interactive_v3_adoptionspot.mjs [--out <raw.json>]
// ONLY=<comma list> runs a subset (default,trace always available;
// the guard pin check always runs).
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { resolve, dirname, join } from "node:path";
import { writeFileSync, readFileSync } from "node:fs";
import { pathToFileURL, fileURLToPath } from "node:url";

const require = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const { chromium } = require("playwright-core");
const root = dirname(fileURLToPath(import.meta.url));
const repo = resolve(root, "../..");

const ACTIVE = resolve(repo, "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/site-reviewed");
// Versioned test source: byte-identical to the audited review-execution
// helper (native receipt instrumentation only; scoring math untouched).
const HOOK = join(root, "tests", "yinyang_adoption_hook_final.js");
const ADOPTED_PAGE_SHA = "ec216e716d344ece04c74946e039e01d895753a5c5fcffce3909b89875e09258";

const SHORT = "hello world";
const NOVEL = "abcdefg hijklmn opqrstu vwxyz 0123456789";
// O1 reuse-trace texts (pair counts, not char counts).
const T1 = "qzxjkvwpbfgxqzjqkwpvz";
const T2 = "qzxjkvwpbfgQZXJKVWPBF";

function shaFile(p) {
  return createHash("sha256").update(readFileSync(p)).digest("hex");
}
function shaText(s) {
  return createHash("sha256").update(String(s), "utf8").digest("hex");
}
function uniquePairs(text) {
  const set = new Set();
  for (const line of text.split("\n")) {
    for (let i = 0; i + 1 < line.length; i++) {
      if (line[i] === " " || line[i + 1] === " ") continue;
      set.add(line.slice(i, i + 2));
    }
  }
  return [...set].sort();
}
const T1_P = uniquePairs(T1),
  T2_P = uniquePairs(T2);
const T1S = new Set(T1_P),
  T2S = new Set(T2_P);
const SHARED = T2_P.filter((p) => T1S.has(p));
const NEWONLY = T2_P.filter((p) => !T1S.has(p));
assert.equal(T1_P.length, 18, "T1 carries 18 unique pairs");
assert.equal(T2_P.length, 20, "T2 carries 20 unique pairs");
assert.equal(SHARED.length, 10, "T1/T2 share 10 pairs");
assert.equal(NEWONLY.length, 10, "T2 adds 10 new pairs");

const ONLY = (process.env.ONLY || "all").split(",");
const want = (name) => ONLY.includes("all") || ONLY.includes(name);

async function settle(page, expect = {}, timeoutMs = 180000) {
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
  await page.waitForFunction(
    () => {
      const t = document.getElementById("yy-explain-note").textContent;
      return !/Updating fields/.test(t);
    },
    null,
    { timeout: timeoutMs },
  );
}
async function setText(page, text) {
  await page.fill("#yy-text", text);
  await page.dispatchEvent("#yy-text", "input");
  await page.waitForTimeout(450);
}
async function setTextFast(page, text) {
  await page.fill("#yy-text", text);
  await page.dispatchEvent("#yy-text", "input");
}
async function setNumeric(page, id, value) {
  await page.fill(`#${id}`, String(value));
  await page.dispatchEvent(`#${id}`, "change");
}
async function setReachOnce(page, value) {
  await page.evaluate((v) => {
    const el = document.getElementById("yy-reach-n");
    el.value = String(v);
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }, value);
}
async function summary(page) {
  return page.evaluate(() => ({
    summary: window.YY_SUMMARY || null,
    explainNote: document.getElementById("yy-explain-note").textContent,
    busy: document.getElementById("yy-explain-field").getAttribute("aria-busy"),
    textError: document.getElementById("yy-text-e").textContent,
    pc: window.__yyPairCacheTest ? window.__yyPairCacheTest.stats() : null,
    flight: window.__yyFlightTest ? window.__yyFlightTest.stats() : null,
  }));
}
async function assertQuiet(page, errors, where) {
  const s = await summary(page);
  assert.equal(s.busy, null, `${where}: aria-busy cleared`);
  assert.ok(!/Updating fields/.test(s.explainNote), `${where}: fields settled`);
  assert.equal(errors.length, 0, `${where}: no errors (${errors.join("; ")})`);
  return s;
}
async function newPage(browser, dir, { hw = null, hook = false } = {}) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errs = [];
  page.on("console", (m) => {
    if (m.type() === "error") errs.push(m.text());
  });
  page.on("pageerror", (e) => errs.push(String(e)));
  page.on("crash", () => errs.push("PAGE-CRASH"));
  if (hw) {
    await page.addInitScript({
      content: `window.__yyRBHW = { cpus: ${hw.cpus}, mem: ${hw.mem} };`,
    });
  }
  if (hook) await page.addInitScript({ path: HOOK });
  await page.goto(pathToFileURL(join(dir, "index.html")).href);
  return { page, errs };
}
const pairNameOf = (n) => String.fromCharCode(n.left) + String.fromCharCode(n.right);

const raw = { pins: {}, steps: {} };
const browser = await chromium.launch({ headless: true });
try {
  // ---- guard: adopted page pin ----
  assert.equal(shaFile(join(ACTIVE, "index.html")), ADOPTED_PAGE_SHA, "adopted active page is the accepted P3 stage");
  raw.pins.activePage = ADOPTED_PAGE_SHA;

  // ---- Spot pages (fresh page per group; the P2 pattern bounds page
  // lifetime and memory): A = default/repaint, B = novel/restore/
  // invalid, C = grayoverflow/shortbase. ----
  const kase = JSON.parse(readFileSync(join(ACTIVE, "boot.json"), "utf8")).cases.find((c) => c.id === "roboto-16");
  async function freshSpot() {
    const r = await newPage(browser, ACTIVE, { hw: { cpus: 2, mem: 8 }, hook: true });
    await settle(r.page, { target: 8, reach: 12 });
    return r;
  }
  let OA1, OA1px;
  let page, errs;
  // Group A.
  ({ page, errs } = await freshSpot());
  try {
    if (want("default")) {
      const s = await assertQuiet(page, errs, "default settle");
      assert.equal(s.summary.scoreCalls, 0, "default settles with 0 score");
      assert.equal(s.summary.pairLayers, 94, "default paints 94 field layers");
      assert.equal(s.summary.contribMisses, 78, "default computes 78 maps");
      assert.equal(s.pc.pinned, 78, "default working set pinned");
      raw.steps.default = {
        score: s.summary.scoreCalls,
        layers: s.summary.pairLayers,
        pinned: s.pc.pinned,
        contribHits: s.summary.contribHits,
        contribMisses: s.summary.contribMisses,
        origins: s.summary.origins.join("|").slice(0, 120),
      };
    }

    if (want("repaint")) {
      const c0 = (await summary(page)).summary.scoreCalls;
      await setNumeric(page, "yy-spacing-n", "12");
      await settle(page, { target: 12 });
      await assertQuiet(page, errs, "target repaint");
      assert.equal((await summary(page)).summary.scoreCalls, c0, "target repaints zero");
      await page.selectOption("#yy-zoom", "2");
      await settle(page, { target: 12 });
      await assertQuiet(page, errs, "zoom repaint");
      assert.equal((await summary(page)).summary.scoreCalls, c0, "zoom repaints zero");
      // The layered heatmap removed the palette text entry; the
      // opacity slider is the surviving cached display control.
      await page.locator("#yy-contrib-alpha").fill("50");
      await settle(page, { target: 12 });
      await assertQuiet(page, errs, "opacity repaint");
      assert.equal((await summary(page)).summary.scoreCalls, c0, "opacity repaints zero");
      // Hidden fields: ink repaints alone with zero engine work. The
      // summary then carries origins but no layer fields by design
      // (wiring deletes stale pairLayers/coupling at ink paint; they
      // return with the field paint), so the full settle predicate
      // cannot apply while hidden -- assert the documented shape.
      await page.uncheck("#yy-show-fields");
      await page.waitForFunction(
        () => {
          const s = window.YY_SUMMARY;
          return !!(s && s.origins && s.target === 12 && s.pairLayers === undefined && s.coupling === undefined);
        },
        null,
        { timeout: 180000 },
      );
      await page.waitForFunction(
        () => {
          const t = document.getElementById("yy-explain-note").textContent;
          return !/Updating fields/.test(t);
        },
        null,
        { timeout: 180000 },
      );
      const hid = await summary(page);
      assert.equal(hid.busy, null, "fields-hidden settles busy");
      assert.equal(errs.length, 0, "fields-hidden raises no errors");
      assert.equal(hid.summary.scoreCalls, c0, "hide-fields repaints zero");
      raw.steps.repaintHiddenShape = {
        origins: hid.summary.origins.join("|").slice(0, 60),
        layersAbsent: hid.summary.pairLayers === undefined,
        couplingAbsent: hid.summary.coupling === undefined,
      };
      await page.check("#yy-show-fields");
      await settle(page, { target: 12 });
      const s = await assertQuiet(page, errs, "fields-shown repaint");
      assert.equal(s.summary.scoreCalls, c0, "show-fields repaints zero");
      await setNumeric(page, "yy-spacing-n", "8");
      await settle(page, { target: 8 });
      raw.steps.repaint = { delta: (await summary(page)).summary.scoreCalls - c0 };
    }
  } finally {
    await page.close();
  }

  // Group B.
  ({ page, errs } = await freshSpot());
  try {
    const NOVEL_N = uniquePairs(NOVEL).length;
    if (want("novel")) {
      await setText(page, NOVEL);
      await settle(page, { text: NOVEL });
      const sN = await assertQuiet(page, errs, "novel compute");
      assert.ok(sN.summary.scoreCalls > 0, "novel text computes");
      await setText(page, kase.text);
      await settle(page, { text: kase.text });
      const cD = (await summary(page)).summary.scoreCalls;
      const fD = (await page.evaluate(() => window.__yyFlightTest.stats())).starts;
      const nD = await page.evaluate(() => window.__yyR.native.length);
      await setText(page, NOVEL);
      await settle(page, { text: NOVEL });
      const sR = await assertQuiet(page, errs, "novel cached revisit");
      assert.equal(sR.summary.scoreCalls, cD, "cached revisit dispatches nothing");
      const stR = await page.evaluate(() => ({
        starts: window.__yyFlightTest.stats().starts,
        native: window.__yyR.native.length,
      }));
      assert.equal(stR.starts, fD, "cached revisit starts no flight");
      assert.equal(stR.native, nD, "cached revisit enters no native pair");
      raw.steps.novel = { pairs: NOVEL_N, firstDelta: sN.summary.scoreCalls - 0 };
    }

    if (want("restore")) {
      await setText(page, NOVEL);
      await settle(page, { reach: 12, text: NOVEL });
      await setReachOnce(page, 14);
      await settle(page, { reach: 14, text: NOVEL });
      const c14 = (await summary(page)).summary.scoreCalls;
      await setReachOnce(page, 13);
      await settle(page, { reach: 13, text: NOVEL });
      const c13 = (await summary(page)).summary.scoreCalls;
      assert.ok(c13 > c14, "old geometry computes its fresh set");
      await setReachOnce(page, 14);
      await settle(page, { reach: 14, text: NOVEL });
      const s = await assertQuiet(page, errs, "geometry restore");
      assert.equal(s.summary.scoreCalls, c13, "restore uses the completed prefix");
      raw.steps.restore = { r14delta: c14, r13delta: c13 - c14 };
    }

    if (want("invalid")) {
      const before = (await summary(page)).summary.origins.join("|");
      await setText(page, "héllo");
      await page.waitForTimeout(800);
      const s = await summary(page);
      assert.equal(s.busy, null, "invalid draft settles busy");
      assert.equal(s.summary.origins.join("|"), before, "invalid draft keeps the view");
      assert.equal(errs.length, 0, "invalid draft raises no errors");
      raw.steps.invalid = { kept: true };
      await setText(page, NOVEL);
      await settle(page, { text: NOVEL });
    }
  } finally {
    await page.close();
  }

  // Group C.
  ({ page, errs } = await freshSpot());
  try {
    if (want("grayoverflow")) {
      await page.check("input[name=profile][value=gray]");
      await settle(page);
      const long = "abc ".repeat(98).slice(0, 390);
      assert.equal(long.length, 390, "overflow text is 390 chars");
      const c0 = (await summary(page)).summary.scoreCalls;
      await setText(page, long);
      try {
        await settle(page, { text: long }, 240000);
      } catch (e) {
        const stuck = await page
          .evaluate(() => {
            const y = window.YY_SUMMARY;
            const R = window.__yyR || { native: [], inbound: [], outbound: [] };
            const nat = R.native.filter((n) => n.phase === "enter" || n.phase === "return");
            return y
              ? {
                  textLen: y.text && y.text.length,
                  calls: y.scoreCalls,
                  note: document.getElementById("yy-explain-note").textContent.slice(0, 80),
                  flight: window.__yyFlightTest.stats(),
                  batches: (window.__yyFieldBatches || []).map((b) => b.id + ":" + b.status).slice(-6),
                  nativeEnters: nat.filter((n) => n.phase === "enter").length,
                  nativeReturns: nat.filter((n) => n.phase === "return").length,
                  nativeJobs: [...new Set(nat.flatMap((n) => n.jobs || []))],
                  inboundKinds: R.inbound.map((r) => r.kind + ":" + r.jobId),
                  outboundScores: R.outbound.filter((o) => o.kind === "score").map((o) => o.jobId + "x" + o.nItems),
                  cpStored: window.__yyPairCacheTest.stats().checkpointStored,
                  pcStored: window.__yyPairCacheTest.stats().stored,
                  pcDropped: window.__yyPairCacheTest.stats().dropped,
                  sampleKeys: R.sample ? Object.keys(R.sample.checkpoints || {}) : null,
                }
              : null;
          })
          .catch((e2) => ({ dead: String(e2).slice(0, 100) }));
        console.log("GRAY-STUCK " + JSON.stringify(stuck));
        console.log("GRAY-ERRS " + JSON.stringify(errs).slice(0, 300));
        throw e;
      }
      const s = await assertQuiet(page, errs, "gray 390-char overflow");
      assert.ok(s.summary.origins.length > 0, "overflow paints");
      raw.steps.grayoverflow = { delta: s.summary.scoreCalls - c0, origins: s.summary.origins.join("|").slice(0, 120) };
      await page.check("input[name=profile][value=mono]");
      await settle(page);
    }

    if (want("shortbase")) {
      await setText(page, SHORT);
      await settle(page, { reach: 12, text: SHORT });
      await setReachOnce(page, 14);
      await settle(page, { reach: 14, text: SHORT });
      const s = await assertQuiet(page, errs, "SHORT R14 baseline");
      OA1 = s.summary.origins.join("|");
      const px = await page.evaluate(() => document.getElementById("yy-adjusted").toDataURL());
      OA1px = px;
      raw.steps.shortbase = { origins: OA1.slice(0, 120), pixelsLen: px.length, pixelsSha: shaText(px) };
    }
  } finally {
    await page.close();
  }

  if (want("fallback")) {
    const fb = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const fErrs = [];
    fb.on("console", (m) => {
      if (m.type() === "error") fErrs.push(m.text());
    });
    fb.on("pageerror", (e) => fErrs.push(String(e)));
    fb.on("crash", () => fErrs.push("PAGE-CRASH"));
    await fb.addInitScript({
      content: "(() => { try { window.Worker = undefined; } catch (e) {} })();",
    });
    await fb.goto(pathToFileURL(join(ACTIVE, "index.html")).href);
    try {
      await settle(fb, { target: 8, reach: 12 });
      await setText(fb, SHORT);
      await settle(fb, { reach: 12, text: SHORT });
      await setReachOnce(fb, 14);
      await settle(fb, { reach: 14, text: SHORT });
      const s = await summary(fb);
      assert.equal(s.busy, null, "fallback settles");
      assert.equal(fErrs.length, 0, "fallback has no errors");
      const fbOrigins = s.summary.origins.join("|");
      const fbPx = await fb.evaluate(() => document.getElementById("yy-adjusted").toDataURL());
      if (OA1 !== undefined) {
        assert.equal(fbOrigins, OA1, "fallback choices equal worker path");
        assert.equal(shaText(fbPx), shaText(OA1px), "fallback pixels equal worker path");
      }
      const mc = await fb.evaluate(() => window.__yyPairCacheTest.mainCalls());
      assert.equal(mc.errors, 0, "main-thread engine clean");
      assert.equal(mc.calls, mc.returns, "every main-thread call returned");
      raw.steps.fallback = {
        mainCalls: mc.calls,
        originsMatch: OA1 !== undefined ? fbOrigins === OA1 : null,
        pixelsMatch: OA1px !== undefined ? shaText(fbPx) === shaText(OA1px) : null,
        pixelsLen: fbPx.length,
      };
    } finally {
      await fb.close();
    }
  }

  // ---- Page 2: fresh reuse-count trace (audited native receipts) ----
  if (want("trace")) {
    const { page: tp, errs: tErrs } = await newPage(browser, ACTIVE, { hw: { cpus: 2, mem: 8 }, hook: true });
    try {
      const hooked = await tp.evaluate(() =>
        document.getElementById("yy-worker-src").textContent.includes("yy-native"),
      );
      assert.ok(hooked, "trace: worker probe patched");
      await settle(tp, { target: 8, reach: 12 });
      const tkase = JSON.parse(readFileSync(join(ACTIVE, "boot.json"), "utf8")).cases.find((c) => c.id === "roboto-16");
      await setReachOnce(tp, 14);
      await settle(tp, { reach: 14, text: tkase.text });
      const pcBase = (await summary(tp)).pc.stored;
      const nBase = await tp.evaluate(() => window.__yyR.native.length);
      const fBase = await tp.evaluate(() => window.__yyFlightTest.stats());
      const tPreT1 = await tp.evaluate(() => Date.now());
      await setTextFast(tp, T1);
      // Wait for merged checkpoints while work is still running.
      await tp.waitForFunction((b) => window.__yyPairCacheTest.stats().checkpointStored > b, pcBase, {
        polling: 25,
        timeout: 120000,
      });
      await tp.waitForFunction(() => window.__yyFlightTest.stats().running > 0, null, { polling: 25, timeout: 60000 });
      const stSwitch = await tp.evaluate(() => ({
        flight: window.__yyFlightTest.stats(),
        stored: window.__yyPairCacheTest.stats().stored,
        native: window.__yyR.native.length,
        outbound: window.__yyR.outbound.slice(),
        inbound: window.__yyR.inbound.slice(),
      }));
      const tSwitch = await tp.evaluate(() => Date.now());
      const t1Jobs = stSwitch.outbound.filter((o) => o.kind === "score" && o.t > tPreT1);
      assert.equal(t1Jobs.length, 1, "T1 dispatches exactly one job (single worker)");
      const t1Id = t1Jobs[0].jobId;
      const mergedT1 = new Set();
      for (const r of stSwitch.inbound) {
        if (r.kind === "progress" && r.jobId === t1Id) {
          for (const k of r.cpKeys || []) mergedT1.add(k);
        }
      }
      await setTextFast(tp, T2);
      await settle(tp, { reach: 14, text: T2 });
      const s = await assertQuiet(tp, tErrs, "T2 reuse trace");
      const st = await tp.evaluate(() => ({
        flight: window.__yyFlightTest.stats(),
        outbound: window.__yyR.outbound.slice(),
        inbound: window.__yyR.inbound.slice(),
        native: window.__yyR.native.slice(),
        stored: window.__yyPairCacheTest.stats().stored,
      }));
      const t2Jobs = st.outbound.filter((o) => o.kind === "score" && o.t > tSwitch);
      assert.ok(t2Jobs.length >= 1, "T2 dispatches its missing set");
      const t2Names = new Set(t2Jobs.flatMap((o) => o.names || []));
      assert.deepEqual([...t2Names].sort(), NEWONLY.slice().sort(), "T2 dispatches exactly the 10 genuinely new pairs");
      const t2Ids = new Set(t2Jobs.map((o) => o.jobId));
      const postNative = st.native.filter((n) => n.t > tSwitch);
      const postEnters = postNative.filter((n) => n.phase === "enter");
      // Shared-cached never re-enters. A shared pair already entered by
      // T1 pre-switch never re-enters either: T1's job still owns it
      // (joined by the new view) and its checkpoint merges from there.
      // Only a shared pair neither entered nor merged pre-switch enters
      // post-switch, exactly once, under T1's continuing job.
      const preEnters = new Set(st.native.filter((n) => n.phase === "enter" && n.t <= tSwitch).map(pairNameOf));
      for (const p of SHARED) {
        const peer = postEnters.filter((n) => pairNameOf(n) === p);
        if (mergedT1.has(p) || preEnters.has(p)) {
          assert.equal(peer.length, 0, `shared pair never re-enters (${p})`);
        } else {
          assert.equal(peer.length, 1, `unstarted shared pair enters once (${p})`);
          assert.ok((peer[0].jobs || []).includes(t1Id), `unstarted shared pair computed by T1's job (${p})`);
          assert.ok(!(peer[0].jobs || []).some((j) => t2Ids.has(j)), `unstarted shared pair not in T2's job (${p})`);
        }
      }
      for (const p of NEWONLY) {
        const peer = postEnters.filter((n) => pairNameOf(n) === p);
        assert.equal(peer.length, 1, `new pair enters exactly once (${p})`);
        const rets = postNative.filter((n) => n.phase === "return" && pairNameOf(n) === p);
        assert.equal(rets.length, 1, `new pair returns exactly once (${p})`);
      }
      // T1's old job: terminal kind disclosed; its late checkpoints merge
      // under the original lease without painting the new view.
      const t1Terms = st.inbound.filter((r) => r.jobId === t1Id && (r.kind === "done" || r.kind === "score-stopped"));
      const t1LateMerged = st.inbound
        .filter((r) => r.jobId === t1Id && r.kind === "progress" && r.t > tSwitch)
        .flatMap((r) => r.cpKeys || []);
      // Pending-vs-completed split, labeled clearly: shared pairs join
      // T1's running work at T2-reconcile time; merged ones never join.
      // Expected joins = shared minus merged-as-of-first-T2-dispatch.
      const t2First = Math.min(...t2Jobs.map((o) => o.t));
      const mergedAtT2 = new Set();
      for (const r of st.inbound) {
        if (r.kind === "progress" && r.jobId === t1Id && r.t <= t2First) {
          for (const k of r.cpKeys || []) mergedAtT2.add(k);
        }
      }
      const expectedJoins = SHARED.filter((p) => !mergedAtT2.has(p)).length;
      const joinsTotal = st.flight.joins - fBase.joins;
      assert.equal(joinsTotal, expectedJoins, `shared pending joins running work (${joinsTotal} == ${expectedJoins})`);
      assert.ok(mergedAtT2.size >= mergedT1.size, "merge set only grows");
      // Final view exact: full T2 set stored, zero work on revisit.
      const cBefore = s.summary.scoreCalls;
      const nBefore = st.native.length;
      await setText(tp, T2);
      await settle(tp, { reach: 14, text: T2 });
      const s2 = await assertQuiet(tp, tErrs, "T2 revisit");
      assert.equal(s2.summary.scoreCalls, cBefore, "T2 revisit is zero work");
      const st2 = await tp.evaluate(() => window.__yyR.native.length);
      assert.equal(st2, nBefore, "T2 revisit enters nothing");
      assert.equal(s2.summary.origins.join("|"), s.summary.origins.join("|"), "revisit choices identical");
      raw.steps.trace = {
        needed: T2_P.length,
        shared: SHARED.length,
        newOnly: NEWONLY.length,
        mergedAtSwitch: mergedT1.size,
        mergedAtT2Dispatch: mergedAtT2.size,
        joinsSharedPending: joinsTotal,
        joinsExpected: expectedJoins,
        t1Job: t1Id,
        t1Terminal: t1Terms.map((r) => r.kind),
        t1LateMerged: t1LateMerged.length,
        t2Jobs: t2Jobs.map((o) => ({ job: o.jobId, n: o.nItems })),
        storedDelta: st.stored - pcBase,
        origins: s.summary.origins.join("|").slice(0, 120),
      };
      raw.jobs = raw.jobs || {};
      raw.jobs.traceOrigins = s.summary.origins.join("|");
    } finally {
      await tp.close();
    }
  }

  raw.pins.stage = ACTIVE;
} finally {
  await browser.close();
}

const outPath = process.argv.includes("--out")
  ? process.argv[process.argv.indexOf("--out") + 1]
  : resolve(repo, "out/diagnostics/contextual-spacing/yinyang-update-performance/wave3/adoption/raw-adoption.json");
writeFileSync(outPath, JSON.stringify(raw, null, 2) + "\n");
console.log("adoption spots: all gates passed");
