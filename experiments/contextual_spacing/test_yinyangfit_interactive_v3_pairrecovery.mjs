// Pair-recovery P3 browser gate: single recovery authority, atomic
// reserve, idempotent pool retry and the terminal-store ownership gate
// on the recovery-fix candidate stage (owner-assembled, same coherent
// boot/table26, current C27). Offline file:// only; no HTTP server, no
// full 26-corpus regen.
//
// Suites (one browser, sequential pages, every page closed):
//   R-guard    frozen active guard + candidate boot/provenance pins.
//   R-smoke    SHORT R14 equality vs active (origins+pixels, actual
//              engine enter/return == 8) + zero-work restore.
//   R-orders-A ack-expiry BEFORE watchdog on a live pool call: the
//              expiry is a proven no-op skip (single authority), then
//              the watchdog drives ONE bounded retry. Audited native
//              enter/return per identity: validated-complete keys never
//              recompute; the retry set is exactly the missing set, once.
//   R-orders-B watchdog BEFORE ack expiry: retry dispatched, then ack
//              expiry releases the live retry mid-flight; repeated
//              timers/errors collapse onto the same bounded retry and
//              the view still converges exactly once per pair.
//   R-blocked  stopping tail + ack expiry: cleanup with no hang, every
//              pair stored exactly once, settled re-need is zero work.
//   R-fallback Worker-disabled main-thread path: equality + zero restore.
//
// Native truth comes from the audited hook_final.js boundary receipts
// (score_pair_local enter/return per identity), reused read-only from
// the frozen review-execution-final evidence; the 60 s production
// clocks are covered by clock_accel.js, which shortens ONLY the two
// 60 s waits to 8 s while the verbatim production callbacks run in
// their original race order. Acceleration is disclosed in raw.clock.
//
// Usage: node test_yinyangfit_interactive_v3_pairrecovery.mjs [--out <raw.json>]
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
const STAGE = resolve(repo, "out/diagnostics/contextual-spacing/yinyang-update-performance/wave3/recovery-fix/stage");
const HOOK = resolve(
  repo,
  "out/diagnostics/contextual-spacing/yinyang-update-performance/wave3/review-execution-final/hook_final.js",
);
const CLOCK = resolve(
  repo,
  "out/diagnostics/contextual-spacing/yinyang-update-performance/wave3/review-execution-final/clock_accel.js",
);
/* Layered-heatmap adopted: active site-reviewed page is the accepted
 * display-only candidate (was d4a2f4b...; boot/data/WASM pins unchanged;
 * prior page archived under yinyang-layered-heatmap/adoption/archive). */
const FROZEN_PAGE_SHA = "66eef10d80c7c593940824582415c51cc829006103df87e926e289f20654692e";
/* P4 view-completion fix (was P3 75221b0e...): settle waits on
 * running keys, stale terminals wake the current view, wholly failed
 * attempts count toward the two-strike bound, and silent ack-expiry
 * counts only keys the current view still needs. */
const EXPECT_WIRING = "d014d43e04877cefedf99259376b4ba4af0a126df09dd6390fa8f23ff2a7b766";
const EXPECT_WORKER = "3b838ad5c1136951ec76be32b89949dc1455dea74cf66a7dfe772f5d2cded349";

const SHORT = "hello world";

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
const SHORT_N = uniquePairs(SHORT).length;
assert.equal(SHORT_N, 8, "SHORT pair count");
// Fast iteration: ONLY=smoke,ordersA,ordersB,blocked,fallback (comma
// list); the guard always runs since later sections need its baseline.
const ONLY = (process.env.ONLY || "all").split(",");
const want = (name) => ONLY.includes("all") || ONLY.includes(name);

function ident(n) {
  return `${n.dataset}|${n.left},${n.right}|${n.metric}|q=${n.q}|r=${n.r}|${n.captureSha}`;
}

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
async function setReachOnce(page, value) {
  await page.evaluate((v) => {
    const el = document.getElementById("yy-reach-n");
    el.value = String(v);
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }, value);
}
async function rState(page) {
  return page.evaluate(() => ({
    workers: window.__yyR.workers.map((w) => ({ idx: w.idx, alive: w.alive })),
    terms: window.__yyR.terms.slice(),
    inbound: window.__yyR.inbound.slice(),
    outbound: window.__yyR.outbound.slice(),
    native: window.__yyR.native.slice(),
    clock: window.__yyClock || null,
    flight: window.__yyFlightTest ? window.__yyFlightTest.stats() : null,
    pc: window.__yyPairCacheTest ? window.__yyPairCacheTest.stats() : null,
    summary: window.YY_SUMMARY || null,
    poolJobs: window.__yyPoolJobs || null,
  }));
}
async function summary(page) {
  return page.evaluate(() => ({
    summary: window.YY_SUMMARY || null,
    explainNote: document.getElementById("yy-explain-note").textContent,
    busy: document.getElementById("yy-explain-field").getAttribute("aria-busy"),
    textError: document.getElementById("yy-text-e").textContent,
    pc: window.__yyPairCacheTest ? window.__yyPairCacheTest.stats() : null,
  }));
}
async function assertQuiet(page, errors, where) {
  const s = await summary(page);
  assert.equal(s.busy, null, `${where}: aria-busy cleared`);
  assert.ok(!/Updating fields/.test(s.explainNote), `${where}: fields settled`);
  assert.equal(errors.length, 0, `${where}: no errors (${errors.join("; ")})`);
  return s;
}
async function hookSelfCheck(page, where) {
  const ok = await page.evaluate(() => document.getElementById("yy-worker-src").textContent.includes("yy-native"));
  assert.ok(ok, `${where}: worker probe patched into embedded source`);
}
function scoreJobs(st) {
  return st.outbound.filter((o) => o.kind === "score");
}
async function newPage(browser, dir, { hw = null, accel = false } = {}) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errs = [];
  page.on("console", (m) => {
    if (m.type() === "error") errs.push(m.text());
  });
  page.on("pageerror", (e) => errs.push(String(e)));
  if (hw) {
    await page.addInitScript({
      content: `window.__yyRBHW = { cpus: ${hw.cpus}, mem: ${hw.mem} };`,
    });
  }
  if (accel) await page.addInitScript({ path: CLOCK });
  await page.addInitScript({ path: HOOK });
  await page.goto(pathToFileURL(join(dir, "index.html")).href);
  return { page, errs };
}
// Kill the aux side of the two live pool sides; returns the kill record
// with a page-clock timestamp marking the kill moment.
async function killAux(page) {
  const cpBase = (await summary(page)).pc.checkpointStored;
  await page.waitForFunction((b) => window.__yyPairCacheTest.stats().checkpointStored > b, cpBase, {
    polling: 25,
    timeout: 120000,
  });
  const keptAtKill = (await summary(page)).pc.checkpointStored - cpBase;
  const kill = await page.evaluate(() => {
    const R = window.__yyR;
    const live = R.outbound
      .filter((o) => o.kind === "score")
      .slice(-2)
      .map((o) => o.jobId);
    const term = R.inbound.some((r) => live.includes(r.jobId) && (r.kind === "done" || r.kind === "score-stopped"));
    if (term || live.length < 2) {
      return { killed: false, workers: R.workers.length, tKill: Date.now() };
    }
    const auxIdx = R.outbound
      .filter((o) => live.includes(o.jobId))
      .map((o) => o.worker)
      .find((i) => i !== 0);
    if (auxIdx === undefined) {
      return { killed: false, workers: R.workers.length, reason: "no-aux", tKill: Date.now() };
    }
    R.workers[auxIdx].ref.terminate();
    return { killed: true, workers: R.workers.length, aux: auxIdx, tKill: Date.now() };
  });
  return { kill, keptAtKill };
}
const pairNameOf = (n) => String.fromCharCode(n.left) + String.fromCharCode(n.right);
// Per-identity recovery invariants, merge-based (not return-based): a
// native return is NOT a merged checkpoint -- the worker returns a pair
// and publishes it at the next chunk-boundary progress post, so a kill
// in between loses it unpublished and the retry legitimately recomputes
// it exactly once. Only checkpoint-POSTED identities (progress cpKeys
// from the pool sides, t <= tSplit) must never re-enter afterwards.
// Post-kill dispatches form one recovery sequence: an identity may
// re-enter across successive jobs (each mid-flight release legitimately
// drops uncheckpointed ownership), but never while another live job
// still owns it, and never after it merged.
//   merged: checkpoint-posted by the pool sides up to the first
//     recovery dispatch. Nothing merges later: post-recovery side
//     drains fail the ownership gate and drop silently.
//   auxNames: aux-side partition (pair names).
//   postIds: every post-kill score job (the whole recovery sequence).
// Asserts: no post-kill enter touches merged; every aux-partition
// returned-but-unmerged identity is recovered; every enter returns in
// its own job; one job computes an identity at most once; a later job
// starts an identity only after the earlier job's terminal
// (done/score-stopped) -- never two live owners on one key. With
// strictOnce (single uninterrupted retry) each identity enters once.
function checkRecoveryIdentities(st, tKill, tSplit, sideIds, auxNames, postIds, where, strictOnce) {
  const merged = new Set();
  for (const r of st.inbound) {
    if (r.kind === "progress" && r.t <= tSplit && sideIds.includes(r.jobId)) {
      for (const k of r.cpKeys || []) merged.add(k);
    }
  }
  const auxSet = new Set(auxNames),
    postSet = new Set(postIds);
  const enters = st.native.filter(
    (n) => n.phase === "enter" && n.t > tKill && (n.jobs || []).some((j) => postSet.has(j)),
  );
  const bad = enters.filter((n) => merged.has(pairNameOf(n)));
  assert.equal(
    bad.length,
    0,
    `${where}: checkpoint-merged identities never recompute ` +
      `(${bad
        .slice(0, 3)
        .map((n) => pairNameOf(n) + "|" + n.metric)
        .join("; ")})`,
  );
  const returned = new Set();
  for (const n of st.native) {
    if (n.phase === "return" && n.t <= tSplit) returned.add(pairNameOf(n));
  }
  const lostUnpublished = [...returned].filter((k) => auxSet.has(k) && !merged.has(k));
  const postNames = new Set(enters.map(pairNameOf));
  for (const k of lostUnpublished) {
    assert.ok(postNames.has(k), `${where}: crash-lost unpublished pair recovered (${k})`);
  }
  // Per (job, identity): entered at most once, and every enter returns
  // in its own job (a cancelled job drains its atomic pair first).
  const byJobIdentity = new Map();
  for (const n of enters) {
    for (const j of n.jobs || []) {
      if (!postSet.has(j)) continue;
      const k = j + "\n" + pairNameOf(n) + "|" + n.metric;
      byJobIdentity.set(k, (byJobIdentity.get(k) || 0) + 1);
    }
  }
  for (const [k, c] of byJobIdentity) {
    assert.ok(c <= 1, `${where}: one job computes an identity once (${k})`);
  }
  const returnsByJobIdentity = new Map();
  for (const n of st.native) {
    if (n.phase !== "return" || n.t <= tKill) continue;
    for (const j of n.jobs || []) {
      if (!postSet.has(j)) continue;
      const k = j + "\n" + pairNameOf(n) + "|" + n.metric;
      returnsByJobIdentity.set(k, (returnsByJobIdentity.get(k) || 0) + 1);
    }
  }
  for (const k of byJobIdentity.keys()) {
    assert.ok((returnsByJobIdentity.get(k) || 0) >= 1, `${where}: every enter returns in its own job (${k})`);
  }
  // Cross-job serialization (relaxed mode): a later job starts an
  // identity only after the earlier job's terminal receipt.
  const terminalT = new Map();
  for (const r of st.inbound) {
    if ((r.kind === "done" || r.kind === "score-stopped") && postSet.has(r.jobId) && !terminalT.has(r.jobId)) {
      terminalT.set(r.jobId, r.t);
    }
  }
  const firstEnter = new Map();
  for (const n of enters) {
    for (const j of n.jobs || []) {
      if (!postSet.has(j)) continue;
      const k = pairNameOf(n) + "|" + n.metric;
      const prev = firstEnter.get(k);
      if (!prev || n.t < prev.t) firstEnter.set(k, { t: n.t, job: j });
    }
  }
  if (strictOnce) {
    const counts = new Map();
    for (const n of enters) {
      const k = pairNameOf(n) + "|" + n.metric;
      counts.set(k, (counts.get(k) || 0) + 1);
    }
    for (const [id, c] of counts) {
      assert.equal(c, 1, `${where}: retried identity entered once (${id})`);
    }
  } else {
    const byIdentity = new Map();
    for (const n of enters) {
      const k = pairNameOf(n) + "|" + n.metric;
      if (!byIdentity.has(k)) byIdentity.set(k, []);
      byIdentity.get(k).push(n);
    }
    for (const [id, list] of byIdentity) {
      list.sort((a, b) => a.t - b.t);
      for (let i = 1; i < list.length; i++) {
        const ej = (list[i - 1].jobs || []).find((j) => postSet.has(j));
        assert.ok(terminalT.has(ej), `${where}: earlier job terminal observed (${id} in ${ej})`);
        assert.ok(list[i].t >= terminalT.get(ej), `${where}: no concurrent duplicate owners (${id})`);
      }
    }
  }
  return { merged: merged.size, lostUnpublished: lostUnpublished.length, retried: firstEnter.size };
}

const raw = { pins: {}, clock: { mode: "accelerated-60s-to-8s-disclosed" }, steps: {}, jobs: {} };
let OA1, PA1;

const browser = await chromium.launch({ headless: true });
try {
  // ---- R-guard ----
  {
    assert.equal(shaFile(join(ACTIVE, "index.html")), FROZEN_PAGE_SHA, "active page untouched");
    assert.equal(
      readFileSync(join(STAGE, "boot.json"), "utf8"),
      readFileSync(join(ACTIVE, "boot.json"), "utf8"),
      "candidate boot identical to active boot",
    );
    raw.pins.activePage = FROZEN_PAGE_SHA;
    raw.pins.wiring = shaFile(join(repo, "experiments/contextual_spacing/yinyangfit_interactive_v3_wiring.js"));
    raw.pins.worker = shaFile(join(repo, "experiments/contextual_spacing/yinyangfit_interactive_v3_worker.js"));
    raw.pins.stageProvenance = JSON.parse(readFileSync(join(STAGE, "provenance.json"), "utf8"));
    assert.equal(raw.pins.wiring, EXPECT_WIRING, "recovery wiring pinned");
    assert.equal(raw.pins.worker, EXPECT_WORKER, "worker unchanged from P2");
    const { page, errs } = await newPage(browser, ACTIVE, { accel: true });
    await settle(page, { target: 8, reach: 12 });
    await setText(page, SHORT);
    await settle(page, { reach: 12, text: SHORT });
    const c0 = (await summary(page)).summary.scoreCalls;
    await setReachOnce(page, 14);
    await settle(page, { reach: 14, text: SHORT });
    const s = await assertQuiet(page, errs, "active cold SHORT R14");
    assert.equal(s.summary.scoreCalls, c0 + SHORT_N, "active baseline computes exactly the 8 SHORT pairs");
    OA1 = s.summary.origins.join("|");
    PA1 = await page.evaluate(() => document.getElementById("yy-adjusted").toDataURL());
    raw.steps.activeRef = { origins: OA1.slice(0, 120) };
    await page.close();
  }

  const kase = JSON.parse(readFileSync(join(STAGE, "boot.json"), "utf8")).cases.find((c) => c.id === "roboto-16");
  const DEFAULT_N = uniquePairs(kase.text).length;
  assert.equal(DEFAULT_N, 78, "default text carries 78 pairs");

  // ---- R-smoke: single worker equality + zero-work restore ----
  if (want("smoke")) {
    {
      const { page, errs } = await newPage(browser, STAGE, { hw: { cpus: 2, mem: 8 }, accel: true });
      await hookSelfCheck(page, "smoke");
      await settle(page, { target: 8, reach: 12 });
      await setText(page, SHORT);
      await settle(page, { reach: 12, text: SHORT });
      const n0 = (await rState(page)).native.length;
      await setReachOnce(page, 14);
      await settle(page, { reach: 14, text: SHORT });
      const s = await assertQuiet(page, errs, "smoke SHORT R14");
      assert.equal(s.summary.origins.join("|"), OA1, "candidate choices equal active");
      const px = await page.evaluate(() => document.getElementById("yy-adjusted").toDataURL());
      assert.equal(px, PA1, "candidate pixels equal active");
      const st = await rState(page);
      const winNat = st.native.slice(n0);
      const winEnters = winNat.filter((n) => n.phase === "enter");
      const winReturns = winNat.filter((n) => n.phase === "return");
      assert.equal(winEnters.length, SHORT_N, "entered exactly the 8 pairs");
      assert.equal(winReturns.length, SHORT_N, "returned exactly the 8 pairs");
      assert.equal(winNat.filter((n) => n.phase === "throw").length, 0);
      const o0 = st.outbound.length;
      await setText(page, SHORT);
      await settle(page, { reach: 14, text: SHORT });
      const st2 = await rState(page);
      assert.equal(st2.outbound.length, o0, "settled re-need dispatches nothing");
      raw.steps.smoke = { enters: winEnters.length, returns: winReturns.length, origins: OA1.slice(0, 120) };
      await page.close();
    }
  }

  // ---- R-orders-A: ack-expiry skips the live pool call, then the
  // watchdog drives exactly one bounded retry (default 78, audited). ----
  if (want("orders-A")) {
    {
      const { page, errs } = await newPage(browser, STAGE, { hw: { cpus: 8, mem: 8 }, accel: true });
      try {
        await hookSelfCheck(page, "orders-A");
        await settle(page, { target: 8, reach: 12 });
        const pcBase = (await summary(page)).pc.stored;
        assert.equal((await summary(page)).summary.text, kase.text);
        const clk0 = (await rState(page)).clock;
        assert.ok(clk0 && clk0.targetMs === 60000, "accelerated hooks target the production 60 s clocks");
        await setReachOnce(page, 17);
        const { kill, keptAtKill } = await killAux(page);
        assert.ok(kill.workers >= 2, "pool engaged two workers");
        assert.ok(kill.killed, `aux killed live (${JSON.stringify(kill)})`);
        assert.ok(keptAtKill >= 1, "prefix merged before the kill");
        const stKill = await rState(page);
        const jobsAtKill = scoreJobs(stKill).length;
        // The skip window must be genuine: the pool logical is still live
        // and unsettled here, otherwise the skip proves nothing.
        const liveBefore = await page.evaluate(() => window.__yyPoolTest.current());
        assert.ok(liveBefore, "skip window: pool logical still unsettled");
        assert.ok(stKill.flight.calls > 0, "skip window: pool call live");
        // Ack expiry first: the live pool logical owns recovery, so this
        // must be a proven no-op skip.
        const fBefore = await page.evaluate(() => window.__yyFlightTest.stats());
        const outBefore = stKill.outbound.length;
        await page.evaluate(() => window.__yyFlightTest.expireAcks());
        const fAfter = await page.evaluate(() => window.__yyFlightTest.stats());
        const stSkip = await rState(page);
        assert.equal(fAfter.running, fBefore.running, "ack expiry skips live pool keys");
        assert.equal(fAfter.calls, fBefore.calls, "ack expiry skips live pool call");
        assert.equal(stSkip.outbound.length, outBefore, "skip posts nothing");
        assert.equal(scoreJobs(stSkip).length, jobsAtKill, "skip dispatches nothing");
        // Then the watchdog: the single recovery authority retries exactly
        // the missing set, once. Either the accelerated production clock
        // or the manual hook fires it first; both run the verbatim
        // production callback, and the driver is recorded honestly.
        const wdRet = await page.evaluate(() => window.__yyPoolTest.expireWatchdog());
        await page.waitForFunction(
          (n) => window.__yyR.outbound.filter((o) => o.kind === "score").length > n,
          jobsAtKill,
          { polling: 25, timeout: 60000 },
        );
        const tRec = await page.evaluate(() => Date.now());
        const sidePosts = scoreJobs(stKill).slice(-2);
        const sideIds = sidePosts.map((o) => o.jobId);
        const auxPost = sidePosts.find((o) => o.worker === kill.aux);
        const primaryPost = sidePosts.find((o) => o.worker !== kill.aux);
        assert.ok(auxPost && primaryPost, "both side posts identified");
        await settle(page, { reach: 17, text: kase.text }, 150000);
        const s = await assertQuiet(page, errs, "orders-A recovery");
        const st = await rState(page);
        const jobs = scoreJobs(st);
        // All recovery-driven dispatches (post-kill); the split time is
        // the first of them, so late pre-recovery merges still count.
        const retries = jobs.filter((o) => o.t > kill.tKill);
        const tSplit = Math.min(...retries.map((o) => o.t));
        assert.ok(retries.length >= 1, "one bounded retry dispatched");
        const retryNames = new Set(retries.flatMap((o) => o.names || []));
        const retrySize = [...retryNames].length;
        assert.ok(retrySize > 0 && retrySize < DEFAULT_N, `retry is the missing remainder (${retrySize}/${DEFAULT_N})`);
        assert.equal(
          retries.flatMap((o) => o.names || []).length,
          retrySize,
          "retry posts carry no internal duplicate",
        );
        const inv = checkRecoveryIdentities(
          st,
          kill.tKill,
          tSplit,
          sideIds,
          auxPost.names || [],
          retries.map((o) => o.jobId),
          "orders-A",
          true,
        );
        assert.equal(s.pc.stored - pcBase, DEFAULT_N, "every default pair stored exactly once");
        const outcomes = (st.poolJobs || []).map((l) => l.outcome);
        assert.ok(
          outcomes.some((o) => String(o).startsWith("retrying:")),
          `bounded retry recorded (${outcomes.join(",")})`,
        );
        assert.equal(st.flight.running, 0, "no running keys leaked");
        assert.equal(st.flight.calls, 0, "no live calls leaked");
        // Repeated timers/errors after settle are no-ops.
        const jobsSettled = scoreJobs(await rState(page)).length;
        await page.evaluate(() => window.__yyFlightTest.expireAcks());
        await page.evaluate(() => window.__yyFlightTest.expireAcks());
        await page.evaluate(() => window.__yyPoolTest.expireWatchdog());
        await page.waitForTimeout(1000);
        assert.equal(
          scoreJobs(await rState(page)).length,
          jobsSettled,
          "post-settle recovery triggers dispatch nothing",
        );
        Object.assign(raw.steps, {
          ordersA: {
            keptAtKill,
            retryJobs: retries.map((o) => ({ job: o.jobId, n: o.nItems })),
            retrySize,
            merged: inv.merged,
            lostUnpublished: inv.lostUnpublished,
            retried: inv.retried,
            outcomes,
            recDriver: typeof wdRet === "string" ? "manual-hook" : "accelerated-clock",
            origins: s.summary.origins.join("|").slice(0, 120),
            clockHits: (st.clock || {}).hits ? st.clock.hits.length : null,
          },
        });
        raw.jobs.ordersAOrigins = s.summary.origins.join("|");
      } finally {
        await page.close();
      }
    }
  }

  // ---- R-orders-B: watchdog first, then ack expiry releases the live
  // retry mid-flight; convergence is still exactly-once per pair. ----
  if (want("orders-B")) {
    {
      const { page, errs } = await newPage(browser, STAGE, { hw: { cpus: 8, mem: 8 }, accel: true });
      try {
        await hookSelfCheck(page, "orders-B");
        await settle(page, { target: 8, reach: 12 });
        const pcBase = (await summary(page)).pc.stored;
        await setReachOnce(page, 17);
        const { kill, keptAtKill } = await killAux(page);
        assert.ok(kill.killed, "aux killed live");
        const stKillB = await rState(page);
        const sidePostsB = scoreJobs(stKillB).slice(-2);
        const sideIdsB = sidePostsB.map((o) => o.jobId);
        const auxPostB = sidePostsB.find((o) => o.worker === kill.aux);
        const primaryPostB = sidePostsB.find((o) => o.worker !== kill.aux);
        assert.ok(auxPostB && primaryPostB, "both side posts identified");
        const jobsAtKillB = scoreJobs(stKillB).length;
        // Watchdog first: recovery dispatches the retry. Either the
        // accelerated production clock or the manual hook fires it; the
        // retry set is every post-kill dispatch, whoever drove it.
        const wdRetB = await page.evaluate(() => window.__yyPoolTest.expireWatchdog());
        await page.waitForFunction(
          (n) => window.__yyR.outbound.filter((o) => o.kind === "score").length > n,
          jobsAtKillB,
          { polling: 25, timeout: 60000 },
        );
        const stRetry = await rState(page);
        const retriesB = scoreJobs(stRetry).filter((o) => o.t > kill.tKill);
        assert.ok(retriesB.length >= 1, "recovery dispatched a retry");
        const tSplitB = Math.min(...retriesB.map((o) => o.t));
        const cpRetry0 = stRetry.pc.checkpointStored;
        // Hold the retry in flight: wait for its first merged checkpoint
        // (proof it started), then expire its ack twice mid-flight. The
        // release must not strand keys or duplicate owners.
        await page.waitForFunction((b) => window.__yyPairCacheTest.stats().checkpointStored > b, cpRetry0, {
          polling: 25,
          timeout: 120000,
        });
        const fLive = await page.evaluate(() => window.__yyFlightTest.stats());
        assert.ok(fLive.running > 0 && fLive.calls > 0, "mid-flight window: retry genuinely live at expiry");
        await page.evaluate(() => window.__yyFlightTest.expireAcks());
        await page.waitForTimeout(1500);
        await page.evaluate(() => window.__yyFlightTest.expireAcks());
        await settle(page, { reach: 17, text: kase.text }, 150000);
        const s = await assertQuiet(page, errs, "orders-B recovery");
        const st = await rState(page);
        const invB = checkRecoveryIdentities(
          st,
          kill.tKill,
          tSplitB,
          sideIdsB,
          auxPostB.names || [],
          scoreJobs(st)
            .filter((o) => o.t > kill.tKill)
            .map((o) => o.jobId),
          "orders-B",
          false,
        );
        assert.equal(s.pc.stored - pcBase, DEFAULT_N, "every default pair stored exactly once");
        assert.equal(st.flight.running, 0, "no running keys leaked");
        assert.equal(st.flight.calls, 0, "no live calls leaked");
        const outcomes = (st.poolJobs || []).map((l) => l.outcome);
        raw.steps.ordersB = {
          keptAtKill,
          outcomes,
          merged: invB.merged,
          lostUnpublished: invB.lostUnpublished,
          retried: invB.retried,
          origins: s.summary.origins.join("|").slice(0, 120),
        };
      } finally {
        await page.close();
      }
    }
  }

  // ---- R-blocked: stopping tail + ack expiry cleans up with no hang ----
  if (want("blocked")) {
    {
      const { page, errs } = await newPage(browser, STAGE, { hw: { cpus: 2, mem: 8 }, accel: true });
      try {
        await hookSelfCheck(page, "blocked");
        await settle(page, { target: 8, reach: 12 });
        const pc0 = (await summary(page)).pc.stored;
        const words = kase.text.split(/\s+/).filter((w) => w.length > 1);
        let acc = [];
        for (const w of words) {
          acc.push(w);
          if (uniquePairs(acc.join(" ")).length >= 16) break;
        }
        const SUB = acc.join(" ");
        assert.ok(uniquePairs(SUB).length >= 16, "pool-scale subset assembled");
        await setText(page, kase.text);
        await setReachOnce(page, 20);
        await page.waitForFunction((b) => window.__yyPairCacheTest.stats().checkpointStored > b, pc0, {
          polling: 25,
          timeout: 120000,
        });
        await setText(page, SUB);
        await setTextFast(page, kase.text);
        await page.waitForTimeout(300);
        const fBlocked = await page.evaluate(() => window.__yyFlightTest.stats());
        // Forced lost-ack bound on the stopping tail: the current view
        // re-resolves from validated checkpoints plus one remainder run.
        await page.evaluate(() => window.__yyFlightTest.expireAcks());
        await settle(page, { reach: 20, text: kase.text });
        const s = await assertQuiet(page, errs, "blocked recovery");
        assert.equal((await summary(page)).pc.stored - pc0, DEFAULT_N, "every pair stored exactly once");
        const f1 = await page.evaluate(() => window.__yyFlightTest.stats());
        assert.equal(f1.running, 0, "no running keys leaked");
        assert.equal(f1.calls, 0, "no live calls leaked");
        const scoresBefore = scoreJobs(await rState(page)).length;
        await setText(page, kase.text);
        await settle(page, { reach: 20, text: kase.text });
        assert.equal(scoreJobs(await rState(page)).length, scoresBefore, "settled re-need is zero work");
        raw.steps.blocked = { blockedSeen: fBlocked.blocked, origins: s.summary.origins.join("|").slice(0, 120) };
      } finally {
        await page.close();
      }
    }
  }

  // ---- R-fallback: Worker-disabled path equality + zero restore ----
  if (want("fallback")) {
    {
      const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
      const errs = [];
      page.on("console", (m) => {
        if (m.type() === "error") errs.push(m.text());
      });
      page.on("pageerror", (e) => errs.push(String(e)));
      await page.addInitScript({
        content: "(() => { try { window.Worker = undefined; } catch (e) {} })();",
      });
      await page.goto(pathToFileURL(join(STAGE, "index.html")).href);
      try {
        await settle(page, { target: 8, reach: 12 });
        await setText(page, SHORT);
        await settle(page, { reach: 12, text: SHORT });
        const mcR12 = await page.evaluate(() => window.__yyPairCacheTest.mainCalls());
        await setReachOnce(page, 14);
        await settle(page, { reach: 14, text: SHORT });
        const s = await assertQuiet(page, errs, "fallback SHORT R14");
        assert.equal(
          (await page.evaluate(() => window.__yyPairCacheTest.mainCalls())).calls,
          mcR12.calls + SHORT_N,
          "R14 computes exactly its 8 pairs",
        );
        assert.equal(s.summary.origins.join("|"), OA1, "fallback choices equal");
        const px = await page.evaluate(() => document.getElementById("yy-adjusted").toDataURL());
        assert.equal(px, PA1, "fallback pixels equal");
        const mc = await page.evaluate(() => window.__yyPairCacheTest.mainCalls());
        assert.equal(mc.errors, 0, "fallback main-thread engine clean");
        assert.equal(mc.calls, mc.returns, "every main-thread call returned");
        const c0 = (await summary(page)).summary.scoreCalls;
        await setText(page, SHORT);
        await settle(page, { reach: 14, text: SHORT });
        assert.equal((await summary(page)).summary.scoreCalls, c0, "fallback re-need dispatches nothing");
        const mc2 = await page.evaluate(() => window.__yyPairCacheTest.mainCalls());
        assert.equal(mc2.calls, mc.calls, "fallback restore is zero engine work");
        raw.steps.fallback = { origins: OA1.slice(0, 120), mainCalls: mc2.calls };
      } finally {
        await page.close();
      }
    }
  }

  raw.pins.stage = STAGE;
} finally {
  await browser.close();
}

const outPath = process.argv.includes("--out")
  ? process.argv[process.argv.indexOf("--out") + 1]
  : resolve(repo, "out/diagnostics/contextual-spacing/yinyang-update-performance/wave3/recovery-fix/raw-recovery.json");
writeFileSync(outPath, JSON.stringify(raw, null, 2) + "\n");
console.log("pairrecovery browser: all gates passed");
