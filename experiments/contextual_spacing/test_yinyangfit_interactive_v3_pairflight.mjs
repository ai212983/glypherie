// Pair-flight P2 browser gate: shared running-pair work with bounded
// cancellation on the inflight candidate stage assembled through the
// owner builder (same coherent boot/table26, current C27). Offline
// file:// only; no HTTP server, no full 26-corpus regen.
//
// Suites (one browser, sequential pages, every page closed):
//   F-active   frozen active guard + cold SHORT R14 + default R18
//              reference origins/pixels for the equality gate.
//   F-single   guarded single worker: SHORT R14 cold equality, NOVEL
//              R15 subset join (no cancel/restart of shared work,
//              identical re-need is a no-op, restore computes only the
//              remainder), T18 R13->R14->R13 zero-work restore, default
//              R18 short-text-not-behind-tail (old job drains with an
//              ack, never a done), NOVEL R16 blocked-redispatch +
//              ack-expiry recovery, malformed-final injection, tiny
//              budget pins/eviction.
//   F-pool     guarded two-worker pool, one fresh page each (memory
//              backstop): clean default R17; NOVEL R21 mid-flight
//              subset join; default R17 aux loss with bounded recovery.
//   F-fallback Worker-disabled main-thread path: equality
//              (origins+pixels) and zero-work revisits.
//
// Engine truth comes from worker receipts (engineCalls/engineDone per
// job), __yyMainCalls on fallback, and __yyFlightTest starts/joins/
// blocked -- never from scoreCalls alone.
//
// Usage: node test_yinyangfit_interactive_v3_pairflight.mjs [--out <raw.json>]
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
const STAGE = resolve(repo, "out/diagnostics/contextual-spacing/yinyang-update-performance/wave3/inflight/stage");
/* Layered-heatmap adopted: active site-reviewed page is the accepted
 * display-only candidate (was d4a2f4b...; boot/data/WASM pins unchanged;
 * prior page archived under yinyang-layered-heatmap/adoption/archive). */
const FROZEN_PAGE_SHA = "66eef10d80c7c593940824582415c51cc829006103df87e926e289f20654692e";

const SHORT = "hello world";
const NOVEL = "abcdefg hijklmn opqrstu vwxyz 0123456789";
const SUBSET = "abcdefg hijklmn";

// T18 toggle word: every adjacent pair is novel against the default,
// SHORT and NOVEL sets, so the R13/R14 geometry moves on this page and
// the fallback page compute exactly its pairs with zero-work restores.
const KASE18 = JSON.parse(readFileSync(join(STAGE, "boot.json"), "utf8")).cases.find((c) => c.id === "roboto-16");
const T18_AVOID = new Set([...uniquePairs(KASE18.text), ...uniquePairs(SHORT), ...uniquePairs(NOVEL)]);
const T18_ALPHA = Object.keys(KASE18.profiles.mono.glyphs)
  .filter((cp) => {
    const g = KASE18.profiles.mono.glyphs[cp];
    const ch = String.fromCodePoint(Number(cp));
    return g.w > 0 && g.h > 0 && cp !== "32" && /^[a-z0-9]$/.test(ch);
  })
  .map((cp) => String.fromCodePoint(Number(cp)));
let T18 = null;
t18outer: for (const a of T18_ALPHA) {
  let word = a;
  const seen = new Set();
  for (let n = 0; n < 7; n++) {
    const nxt = T18_ALPHA.find((ch) => {
      const p = word[word.length - 1] + ch;
      return !T18_AVOID.has(p) && !seen.has(p);
    });
    if (!nxt) continue t18outer;
    seen.add(word[word.length - 1] + nxt);
    word += nxt;
  }
  T18 = word;
  break t18outer;
}
assert.ok(T18, "T18 toggle word exists");
assert.equal(uniquePairs(T18).length, 7, "T18 word has 7 novel pairs");

function shaFile(p) {
  return createHash("sha256").update(readFileSync(p)).digest("hex");
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

function hwScript(cpus, memGB) {
  const cpusSrc = cpus === undefined || cpus === null ? "undefined" : String(cpus);
  const memSrc = memGB === undefined || memGB === null ? "undefined" : String(memGB);
  return `(() => {
    try {
      Object.defineProperty(Navigator.prototype, "hardwareConcurrency",
        { get: () => ${cpusSrc}, configurable: true });
    } catch (e) {}
    try {
      Object.defineProperty(Navigator.prototype, "deviceMemory",
        { get: () => ${memSrc}, configurable: true });
    } catch (e) {}
  })();`;
}

// Read-only worker census: construction count, inbound receipts with
// worker-side engine-call counts and checkpoint keys, outbound score
// identities. Never alters payloads.
function spyScript(extra = "") {
  return `(() => {
    window.__yyT = { workers: [], inbound: [], outbound: [], sample: null };
    ${extra}
    const OrigWorker = window.Worker;
    if (!OrigWorker) return;
    function TWorker(url, opts) {
      const idx = window.__yyT.workers.length;
      const w = new OrigWorker(url, opts);
      window.__yyT.workers.push(w);
      const arm = setInterval(() => {
        try {
          const cur = w.onmessage;
          if (typeof cur === "function" && !cur.__yyWrapped) {
            const wrapped = function (e) {
              const data = e.data;
              try {
                const rec = { t: Date.now(), worker: idx,
                  kind: data && data.kind,
                  jobId: data && data.jobId, key: data && data.key,
                  done: data && data.done, total: data && data.total,
                  engineCalls: data && data.engineCalls,
                  engineDone: data && data.engineDone,
                  nKeys: data && data.results ?
                    Object.keys(data.results).length : undefined,
                  doneKeys: data && data.results ?
                    Object.keys(data.results) : undefined,
                  cpKeys: data && data.checkpoints ?
                    Object.keys(data.checkpoints) : undefined };
                window.__yyT.inbound.push(rec);
                if (data && data.kind === "progress" && data.checkpoints &&
                    Object.keys(data.checkpoints).length > 0 &&
                    !window.__yyT.sample) {
                  try {
                    window.__yyT.sample =
                      JSON.parse(JSON.stringify({ kind: data.kind,
                        jobId: data.jobId, key: data.key,
                        captureSha: data.captureSha, version: data.version,
                        checkpoints: data.checkpoints }));
                  } catch (ignore) {}
                }
              } catch (ignore) {}
              return cur.call(w, { data });
            };
            wrapped.__yyWrapped = true;
            w.onmessage = wrapped;
            clearInterval(arm);
          }
        } catch (ignore) {}
      }, 25);
      setTimeout(() => clearInterval(arm), 30000);
      const origPost = w.postMessage.bind(w);
      w.postMessage = (msg, ...rest) => {
        try {
          if (msg && (msg.kind === "score" || msg.kind === "cancel" ||
              msg.kind === "drop")) {
            window.__yyT.outbound.push({ t: Date.now(), worker: idx,
              kind: msg.kind, jobId: msg.jobId, key: msg.key || null,
              nItems: msg.items ? msg.items.length : 0,
              names: msg.items ? msg.items.map((i) => i.key) : undefined,
              dropKeys: msg.keys || undefined });
          }
        } catch (ignore) {}
        return origPost(msg, ...rest);
      };
      return w;
    }
    TWorker.prototype = OrigWorker.prototype;
    window.Worker = TWorker;
  })();`;
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

async function setNumeric(page, id, value) {
  await page.fill(`#${id}`, String(value));
  await page.dispatchEvent(`#${id}`, "change");
}

async function setText(page, text) {
  await page.fill("#yy-text", text);
  await page.dispatchEvent("#yy-text", "input");
  // Let the 250ms text debounce render before any geometry change, so
  // job-counting sections observe exactly one job per setting.
  await page.waitForTimeout(450);
}

// Fill + input event without waiting: the caller catches the job live.
async function setTextFast(page, text) {
  await page.fill("#yy-text", text);
  await page.dispatchEvent("#yy-text", "input");
}

async function summary(page) {
  return page.evaluate(() => ({
    summary: window.YY_SUMMARY || null,
    explainNote: document.getElementById("yy-explain-note").textContent,
    busy: document.getElementById("yy-explain-field").getAttribute("aria-busy"),
    textError: document.getElementById("yy-text-e").textContent,
    pc: window.__yyPairCacheTest ? window.__yyPairCacheTest.stats() : null,
    mainCalls: window.__yyPairCacheTest ? window.__yyPairCacheTest.mainCalls() : null,
    flight: window.__yyFlightTest ? window.__yyFlightTest.stats() : null,
  }));
}

async function flightStats(page) {
  return page.evaluate(() => window.__yyFlightTest.stats());
}

async function spy(page) {
  return page.evaluate(() => window.__yyT);
}

async function resetSpy(page) {
  await page.evaluate(() => {
    window.__yyT.sample = null;
    window.__yyT.inbound = [];
    window.__yyT.outbound = [];
  });
}

async function assertQuiet(page, errors, where) {
  const s = await summary(page);
  assert.equal(s.busy, null, `${where}: aria-busy cleared`);
  assert.ok(!/Updating fields/.test(s.explainNote), `${where}: fields settled`);
  assert.equal(errors.length, 0, `${where}: no errors (${errors.join("; ")})`);
  return s;
}

function jobStats(spyObj, jobId) {
  const inbound = spyObj.inbound.filter((r) => r.jobId === jobId);
  let maxCalls = 0,
    maxDone = 0;
  const cpKeys = new Set();
  for (const r of inbound) {
    if (typeof r.engineCalls === "number") maxCalls = Math.max(maxCalls, r.engineCalls);
    if (typeof r.engineDone === "number") maxDone = Math.max(maxDone, r.engineDone);
    (r.cpKeys || []).forEach((k) => cpKeys.add(k));
  }
  return { maxCalls, maxDone, cpKeys: [...cpKeys].sort(), inbound: inbound.length };
}

function scoreJobs(spyObj) {
  return spyObj.outbound.filter((o) => o.kind === "score");
}

function terminalFor(spyObj, jobId) {
  const recs = spyObj.inbound.filter((r) => r.jobId === jobId && (r.kind === "done" || r.kind === "score-stopped"));
  return recs.length ? recs[recs.length - 1].kind : null;
}

const raw = { pins: {}, steps: {}, jobs: {} };
const NOVEL_N = uniquePairs(NOVEL).length;
const SUBSET_N = uniquePairs(SUBSET).length;
const T18_N = uniquePairs(T18).length;

const browser = await chromium.launch({ headless: true });
try {
  // ---- F-active: frozen baseline guard + cold timing + references ----
  let OA1, PA1, OA2;
  {
    assert.equal(shaFile(join(ACTIVE, "index.html")), FROZEN_PAGE_SHA, "active page untouched");
    assert.equal(
      readFileSync(join(STAGE, "boot.json"), "utf8"),
      readFileSync(join(ACTIVE, "boot.json"), "utf8"),
      "candidate boot identical to active boot",
    );
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errs = [];
    page.on("console", (m) => {
      if (m.type() === "error") errs.push(m.text());
    });
    page.on("pageerror", (e) => errs.push(String(e)));
    await page.goto(pathToFileURL(join(ACTIVE, "index.html")).href);
    await settle(page, { target: 8, reach: 12 });
    let t0 = Date.now();
    await setText(page, SHORT);
    await setNumeric(page, "yy-reach-n", "14");
    await settle(page, { reach: 14, text: SHORT });
    raw.steps.activeColdShortR14Ms = Date.now() - t0;
    let s = await summary(page);
    raw.steps.activeColdShortR14Calls = s.summary.scoreCalls;
    OA1 = s.summary.origins.join("|");
    PA1 = await page.evaluate(() => document.getElementById("yy-adjusted").toDataURL());
    await assertQuiet(page, errs, "active cold");
    // Default-text R18 reference for the equality gate.
    const kase = JSON.parse(readFileSync(join(ACTIVE, "boot.json"), "utf8")).cases.find((c) => c.id === "roboto-16");
    t0 = Date.now();
    await page.click("#yy-text-restore");
    await settle(page, { text: kase.text });
    await setNumeric(page, "yy-reach-n", "18");
    await settle(page, { reach: 18 });
    raw.steps.activeDefaultR18Ms = Date.now() - t0;
    s = await summary(page);
    OA2 = s.summary.origins.join("|");
    raw.steps.activeDefaultR18Calls = s.summary.scoreCalls;
    raw.steps.activeDefaultR18Origins = OA2.slice(0, 120);
    await assertQuiet(page, errs, "active default R18");
    await page.close();
  }

  // ---- F-single: guarded single worker (cpu-low forces single path) ----
  const single = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const sErrs = [];
  single.on("console", (m) => {
    if (m.type() === "error") sErrs.push(m.text());
  });
  single.on("pageerror", (e) => sErrs.push(String(e)));
  await single.addInitScript({ content: hwScript(2, 8) + "\n" + spyScript() });
  await single.goto(pathToFileURL(join(STAGE, "index.html")).href);
  await settle(single, { target: 8, reach: 12 });
  {
    const s = await summary(single);
    assert.equal(s.summary.scoreCalls, 0, "default fast path scores nothing");
    assert.equal(s.pc.pairs, 0, "shipped tables never enter the curve LRU");
    assert.equal(s.pc.pinned, 78, "default working set pinned");
  }
  let O1, P1;
  // Cold candidate timing, same procedure as active: default settle,
  // SHORT at R12, then SHORT R14. Fresh page => equally settled inputs.
  {
    const t0 = Date.now();
    await setText(single, SHORT);
    await settle(single, { text: SHORT });
    const s12 = await summary(single);
    await setNumeric(single, "yy-reach-n", "14");
    await settle(single, { reach: 14, text: SHORT });
    raw.steps.candColdShortR14Ms = Date.now() - t0;
    raw.steps.shortR12FillCalls = s12.summary.scoreCalls;
    const s = await assertQuiet(single, sErrs, "single SHORT R14");
    assert.equal(s.summary.scoreCalls, s12.summary.scoreCalls + 8, "SHORT R14 computes exactly its 8 pairs");
    raw.steps.candColdShortR14Calls = s.summary.scoreCalls;
    const spyObj = await spy(single);
    const jobs = scoreJobs(spyObj);
    const st = jobStats(spyObj, jobs[jobs.length - 1].jobId);
    assert.equal(spyObj.workers.length, 1, "one worker on the guarded single path");
    assert.equal(st.maxCalls, 8, "worker entered score_pair_local 8x");
    assert.equal(st.maxDone, 8, "worker returned 8 completions");
    O1 = s.summary.origins.join("|");
    P1 = await single.evaluate(() => document.getElementById("yy-adjusted").toDataURL());
    assert.equal(O1, OA1, "candidate choices equal active baseline");
    assert.equal(P1, PA1, "candidate pixels equal active baseline");
    raw.steps.shortR14Equality = true;
  }
  // Subset join mid-flight: shared work is never cancelled or
  // restarted; the subset dispatches nothing new; identical re-need is
  // a no-op; restoring NOVEL computes only the remainder.
  let NOV_R15;
  {
    // Settle NOVEL at the current reach first, so the R15 move below
    // dispatches exactly one job to catch live.
    await setText(single, NOVEL);
    await settle(single, { reach: 14, text: NOVEL });
    await resetSpy(single);
    const f0 = await flightStats(single);
    const pc0 = (await summary(single)).pc.stored;
    await setNumeric(single, "yy-reach-n", "15");
    // Catch the long NOVEL job live: first checkpoint merged, job open.
    await single.waitForFunction((b) => window.__yyPairCacheTest.stats().checkpointStored > b, pc0, {
      polling: 25,
      timeout: 60000,
    });
    const cancelsBefore = (await spy(single)).outbound.filter((o) => o.kind === "cancel").length;
    const scoresBefore = scoreJobs(await spy(single)).length;
    await setTextFast(single, SUBSET);
    await setTextFast(single, SUBSET); // identical re-need while running
    await settle(single, { reach: 15, text: SUBSET });
    const s = await assertQuiet(single, sErrs, "subset join");
    const spyObj = await spy(single);
    const f1 = await flightStats(single);
    assert.equal(
      spyObj.outbound.filter((o) => o.kind === "cancel").length,
      cancelsBefore,
      "subset switch posts no cancel",
    );
    assert.equal(scoreJobs(spyObj).length, scoresBefore, "only the NOVEL job dispatched; the subset joins it");
    assert.ok(f1.joins > f0.joins, "subset keys joined running work");
    assert.equal(f1.starts, f0.starts + 1, "only the R15 job started; the subset joins it");
    const SUB_R15 = s.summary.origins.join("|");
    assert.ok(SUB_R15.length > 0, "subset paints from shared work");
    raw.steps.subsetJoin = { joins: f1.joins - f0.joins, origins: SUB_R15.slice(0, 120) };
    // Restore NOVEL: only the remainder dispatches; the shared prefix
    // (merged before and during the subset view) never recomputes.
    const pc1 = (await summary(single)).pc.stored;
    await setText(single, NOVEL);
    await settle(single, { reach: 15, text: NOVEL });
    const s2 = await assertQuiet(single, sErrs, "NOVEL restore");
    const spy2 = await spy(single);
    const jobs2 = scoreJobs(spy2);
    const jRestore = jobs2[jobs2.length - 1].jobId;
    const stRestore = jobStats(spy2, jRestore);
    const mergedPrefix = pc1 - pc0;
    assert.ok(mergedPrefix >= SUBSET_N, `shared prefix merged (${mergedPrefix} >= ${SUBSET_N})`);
    assert.equal(stRestore.maxCalls, NOVEL_N - mergedPrefix, "restore dispatches only the remainder");
    assert.equal(stRestore.maxDone, NOVEL_N - mergedPrefix);
    const pc2 = (await summary(single)).pc.stored;
    assert.equal(pc2 - pc0, NOVEL_N, "every NOVEL pair stored exactly once");
    NOV_R15 = s2.summary.origins.join("|");
    raw.steps.novelRestore = { pairs: NOVEL_N, prefix: mergedPrefix };
    void SUB_R15;
  }
  // T18 geometry toggle. The text change itself computes the fresh
  // set at the current reach; the R13 move then computes its own fresh
  // set once, and both revisits are zero work with identical choices.
  let T18_R13;
  {
    // Back to R14 first (NOVEL is cached there): the text change then
    // computes the fresh T18 set exactly once at R14.
    await setNumeric(single, "yy-reach-n", "14");
    await settle(single, { reach: 14 });
    await setText(single, T18);
    await settle(single, { reach: 14, text: T18 });
    await setNumeric(single, "yy-reach-n", "13");
    await settle(single, { reach: 13, text: T18 });
    const cold = await assertQuiet(single, sErrs, "T18 R13 cold");
    T18_R13 = cold.summary.origins.join("|");
    const callsR13 = cold.summary.scoreCalls;
    await setNumeric(single, "yy-reach-n", "14");
    await settle(single, { reach: 14, text: T18 });
    const r14 = await assertQuiet(single, sErrs, "T18 R14 revisit");
    assert.equal(r14.summary.scoreCalls, callsR13, "R14 reuses the text-change computation");
    await setNumeric(single, "yy-reach-n", "13");
    await settle(single, { reach: 13, text: T18 });
    const back = await assertQuiet(single, sErrs, "T18 R13 restore");
    assert.equal(back.summary.scoreCalls, callsR13, "R13 restore reuses its completed prefix");
    assert.equal(back.summary.origins.join("|"), T18_R13, "restored choices identical");
    raw.steps.t18 = { pairs: T18_N };
  }
  // Cold default R18 (full compute) proves baseline equality; then a
  // fresh slow job at R19 is trimmed mid-flight by a disjoint short
  // text. The trimmed tail drains with an ack and never a done, the
  // short view settles on exactly its own pairs, and revisiting the
  // default computes only the unmerged remainder with identical
  // choices -- no cancelled-but-duplicated work anywhere.
  {
    const kase = JSON.parse(readFileSync(join(STAGE, "boot.json"), "utf8")).cases.find((c) => c.id === "roboto-16");
    const dfltPairs = new Set(uniquePairs(kase.text));
    const glyphs = kase.profiles.mono.glyphs;
    const alpha = Object.keys(glyphs)
      .filter((cp) => glyphs[cp].w > 0 && glyphs[cp].h > 0 && cp !== "32")
      .map((cp) => String.fromCodePoint(Number(cp)));
    let SHORT2 = null;
    outer: for (const a of alpha) {
      let word = a;
      const seen = new Set();
      for (let n = 0; n < 7; n++) {
        const nxt = alpha.find((ch) => {
          const p = word[word.length - 1] + ch;
          return !dfltPairs.has(p) && !seen.has(p);
        });
        if (!nxt) continue outer;
        seen.add(word[word.length - 1] + nxt);
        word += nxt;
      }
      SHORT2 = word;
      break outer;
    }
    assert.ok(SHORT2, "disjoint short word exists");
    const SHORT2_N = uniquePairs(SHORT2).length;
    assert.equal(SHORT2_N, 7, "short word has 7 novel pairs");
    // Phase A: cold default R18. The reach move computes the tiny
    // T18 set first, then the text change dispatches the full 78-pair
    // job alone -- the only runner, so its progress is J1's.
    await resetSpy(single);
    let t0 = Date.now();
    await setNumeric(single, "yy-reach-n", "18");
    await setText(single, kase.text);
    const j1 = scoreJobs(await spy(single)).slice(-1)[0].jobId;
    await single.waitForFunction(
      (id) => window.__yyT.inbound.some((r) => r.jobId === id && r.kind === "progress" && (r.cpKeys || []).length > 0),
      j1,
      { polling: 25, timeout: 60000 },
    );
    await settle(single, { reach: 18, text: kase.text });
    const cold18 = await assertQuiet(single, sErrs, "default R18 cold");
    raw.steps.candColdDefaultR18Ms = Date.now() - t0;
    raw.steps.candColdDefaultR18Calls = cold18.summary.scoreCalls;
    assert.equal(cold18.summary.origins.join("|"), OA2, "default R18 choices equal active baseline");
    raw.steps.defaultR18Equality = true;
    // Phase B: a fresh slow job at R19, trimmed mid-flight.
    await resetSpy(single);
    await setNumeric(single, "yy-reach-n", "19");
    // Baseline after the R19 dispatch is posted: only the SHORT2
    // dispatch below may add an owner.
    const f0 = await flightStats(single);
    const pcB0 = (await summary(single)).pc.stored;
    const j2 = scoreJobs(await spy(single)).slice(-1)[0].jobId;
    await single.waitForFunction(
      (id) => window.__yyT.inbound.some((r) => r.jobId === id && r.kind === "progress" && (r.cpKeys || []).length > 0),
      j2,
      { polling: 25, timeout: 60000 },
    );
    await setTextFast(single, SHORT2);
    await settle(single, { reach: 19, text: SHORT2 });
    const s = await assertQuiet(single, sErrs, "short text ahead of tail");
    const spyObj = await spy(single);
    const f1 = await flightStats(single);
    const jShort = scoreJobs(spyObj).slice(-1)[0].jobId;
    assert.notEqual(jShort, j2, "short view dispatches its own job");
    const stShort = jobStats(spyObj, jShort);
    assert.equal(stShort.maxCalls, SHORT2_N, "short job computes its full set");
    assert.equal(stShort.maxDone, SHORT2_N);
    assert.equal(f1.starts - f0.starts, 1, "exactly one new owner dispatched");
    assert.equal(terminalFor(spyObj, j2), "score-stopped", "trimmed tail drains with an ack, never a done");
    assert.equal(
      spyObj.inbound.filter((r) => r.jobId === j2 && r.kind === "done").length,
      0,
      "no done from the trimmed job",
    );
    // Global store counter minus SHORT2's own 7: what J2 merged.
    const prefix = (await summary(single)).pc.stored - pcB0 - SHORT2_N;
    assert.ok(prefix >= 1 && prefix < 78, `merged prefix ${prefix} of 78`);
    // Revisit: only the unmerged remainder computes, with identical
    // choices; a second revisit is zero work.
    await setText(single, kase.text);
    await settle(single, { reach: 19, text: kase.text });
    const back19 = await assertQuiet(single, sErrs, "default R19 restore");
    const spyR = await spy(single);
    const jRestore = scoreJobs(spyR).slice(-1)[0].jobId;
    const stRestore = jobStats(spyR, jRestore);
    assert.equal(stRestore.maxCalls, 78 - prefix, "restore computes the remainder");
    assert.equal(stRestore.maxDone, 78 - prefix);
    const OR19 = back19.summary.origins.join("|");
    const callsRestored = back19.summary.scoreCalls;
    await setText(single, kase.text);
    await settle(single, { reach: 19, text: kase.text });
    const again = await assertQuiet(single, sErrs, "default R19 re-revisit");
    assert.equal(again.summary.scoreCalls, callsRestored, "second revisit is free");
    assert.equal(again.summary.origins.join("|"), OR19, "choices stable");
    raw.steps.shortAheadOfTail = {
      pairs: SHORT2_N,
      word: SHORT2,
      prefix,
      restoreOrigins: OR19.slice(0, 120),
    };
    raw.jobs.shortTailTerminal = terminalFor(spyObj, j2);
  }
  // Blocked redispatch + ack-expiry recovery: detach a long tail, ask
  // for it back before the stop acknowledgement arrives (blocked, no
  // second owner), then force the lost-ack bound. The view still
  // settles with every pair stored exactly once and no leaked owners.
  {
    const kase = JSON.parse(readFileSync(join(STAGE, "boot.json"), "utf8")).cases.find((c) => c.id === "roboto-16");
    const words = kase.text.split(/\s+/).filter((w) => w.length > 1);
    let acc = [];
    for (const w of words) {
      acc.push(w);
      if (uniquePairs(acc.join(" ")).length >= 16) break;
    }
    const SUB20 = acc.join(" ");
    const SUB20_N = uniquePairs(SUB20).length;
    assert.ok(SUB20_N >= 16, "pool-scale subset assembled");
    await resetSpy(single);
    const f0 = await flightStats(single);
    const pc0 = (await summary(single)).pc.stored;
    await setText(single, kase.text);
    await setNumeric(single, "yy-reach-n", "20");
    await single.waitForFunction((b) => window.__yyPairCacheTest.stats().checkpointStored > b, pc0, {
      polling: 25,
      timeout: 60000,
    });
    // Full setText waits out the debounce, so the subset reconcile has
    // detached the tail before the restore input lands one debounce
    // later -- far sooner than the 60-pair tail can drain.
    await setText(single, SUB20);
    // Back before the stop acknowledgement: the tail is stopping, so
    // the same keys block instead of double-running.
    await setTextFast(single, kase.text);
    await single.waitForTimeout(300);
    const fBlocked = await flightStats(single);
    assert.ok(fBlocked.blocked > f0.blocked, "same-key redispatch waits");
    // Force the lost-ack bound: ownership releases, the current view
    // re-resolves from validated checkpoints plus one remainder run.
    await single.evaluate(() => window.__yyFlightTest.expireAcks());
    await settle(single, { reach: 20, text: kase.text });
    const s = await assertQuiet(single, sErrs, "ack-expiry recovery");
    const f1 = await flightStats(single);
    const pc1 = (await summary(single)).pc.stored;
    assert.equal(pc1 - pc0, 78, "every pair stored exactly once");
    assert.equal(f1.running, 0, "no running keys leaked");
    assert.equal(f1.calls, 0, "no live calls leaked");
    assert.equal(f1.gens, 1, "one current generation remains");
    // Settled state is stable: identical re-need dispatches nothing.
    const scoresBefore = scoreJobs(await spy(single)).length;
    await setText(single, kase.text);
    await settle(single, { reach: 20, text: kase.text });
    assert.equal(scoreJobs(await spy(single)).length, scoresBefore, "settled re-need is zero work");
    raw.steps.ackExpiry = { subset: SUB20_N, blocked: fBlocked.blocked - f0.blocked };
  }
  // Malformed final: a forged done for the live job carries a partial
  // curve for a real pair (strict final validation drops it and marks
  // one failure-gate strike) plus an unknown pair (dropped). Nothing
  // is stored, and the view still recovers to a complete settle.
  {
    const kase = JSON.parse(readFileSync(join(STAGE, "boot.json"), "utf8")).cases.find((c) => c.id === "roboto-16");
    await resetSpy(single);
    const pc0 = (await summary(single)).pc.stored;
    const f0 = await flightStats(single);
    await setText(single, kase.text);
    await setNumeric(single, "yy-reach-n", "22");
    await single.waitForFunction(() => window.__yyT.sample, null, { polling: 25, timeout: 60000 });
    const sample = await single.evaluate(() => window.__yyT.sample);
    const j1 = sample.jobId;
    const realName = Object.keys(sample.checkpoints)[0];
    const realRec = sample.checkpoints[realName];
    const clone = (o) => JSON.parse(JSON.stringify(o));
    const partial = clone(realRec);
    partial.steps = [partial.steps[0]];
    const d0 = (await summary(single)).pc;
    await single.evaluate((msg) => window.__yyPairCacheTest.inject(msg), {
      kind: "done",
      jobId: j1,
      key: sample.key,
      captureSha: sample.captureSha,
      version: sample.version,
      results: {
        [realName]: partial,
        ZZ: clone(realRec),
      },
    });
    const d1 = (await summary(single)).pc;
    assert.equal(d1.checkpointStored, d0.checkpointStored, "forged final stores nothing new");
    assert.equal(d1.dropped - d0.dropped, 2, "partial + unknown dropped");
    assert.equal(d1.bytes, d0.bytes, "bytes unchanged by forged final");
    await settle(single, { reach: 22, text: kase.text });
    const s = await assertQuiet(single, sErrs, "malformed-final recovery");
    const pc1 = (await summary(single)).pc.stored;
    const fPost = await flightStats(single);
    assert.equal(fPost.fails - f0.fails, 1, "partial final marks one strike");
    assert.equal(pc1 - pc0, 78, "recovery stores every pair exactly once");
    const f1 = await flightStats(single);
    assert.equal(f1.running, 0, "no running keys leaked");
    raw.steps.malformedFinal = {
      dropped: d1.dropped - d0.dropped,
      fails: f1.fails - f0.fails,
    };
    raw.steps.defaultR22Origins = s.summary.origins.join("|").slice(0, 120);
  }
  // Tiny budget: the pinned working set is retained and reported over
  // target; obsolete records evict first once pins release; restore
  // recomputes exactly the evicted set with identical choices.
  {
    await setText(single, SHORT);
    await setNumeric(single, "yy-reach-n", "14");
    await settle(single, { reach: 14, text: SHORT });
    const full = await assertQuiet(single, sErrs, "pre-budget settle");
    assert.equal(full.summary.origins.join("|"), O1, "pre-budget choices stable");
    const B = (await summary(single)).pc.bytes;
    const pairsBefore = (await summary(single)).pc.pairs;
    assert.ok(B > 0, "accounted bytes non-zero");
    // Budget far below the pinned working set: everything unpinned
    // evicts, the 8 pinned SHORT pairs are retained and reported over
    // target instead of recomputed, evicted or looped on.
    const over = await single.evaluate(() => window.__yyFlightTest.setBudget(100));
    assert.equal(over.overflow, true, "pinned set retained over target");
    assert.equal(over.pairs, 8, "only the pinned working set survives");
    assert.ok(over.evicted >= pairsBefore - 8, "obsolete records evicted first");
    assert.equal((await summary(single)).summary.origins.join("|"), O1);
    await setText(single, "héllo");
    await single.waitForTimeout(500);
    const inv = await summary(single);
    assert.equal(inv.pc.pinned, 0, "invalid text releases pins");
    const emptied = await single.evaluate(() => window.__yyFlightTest.setBudget(0));
    assert.equal(emptied.pairs, 0, "released records evict");
    assert.equal(emptied.bytes, 0);
    // The stale summary already matches, so settle alone cannot gate
    // the debounced restore: wait for the new job and its terminal
    // receipt explicitly.
    const jobsBefore = scoreJobs(await spy(single)).length;
    await setText(single, SHORT);
    await single.waitForFunction(
      (n) => window.__yyT.outbound.filter((o) => o.kind === "score").length > n,
      jobsBefore,
      { polling: 25, timeout: 60000 },
    );
    const jRestore = scoreJobs(await spy(single)).slice(-1)[0].jobId;
    await single.waitForFunction(
      (id) => window.__yyT.inbound.some((r) => r.jobId === id && (r.kind === "done" || r.kind === "score-stopped")),
      jRestore,
      { polling: 25, timeout: 120000 },
    );
    await settle(single, { reach: 14, text: SHORT });
    const s = await assertQuiet(single, sErrs, "budget restore");
    const spyObj = await spy(single);
    const jLast = scoreJobs(spyObj).slice(-1)[0].jobId;
    assert.equal(jLast, jRestore, "restore job is the latest dispatch");
    const st = jobStats(spyObj, jLast);
    assert.equal(st.maxCalls, 8, "restore recomputes exactly the evicted set");
    assert.equal(s.summary.origins.join("|"), O1, "choices identical after eviction");
    const reset = await single.evaluate(() => window.__yyFlightTest.resetBudget());
    assert.equal(reset.overflow, false, "budget restored");
    raw.steps.tinyBudget = { bytes: B, pairs: pairsBefore };
  }
  raw.steps.single = await summary(single).then((s) => s.pc);
  await single.close();

  // ---- F-pool: guarded two-worker pool, default text ----
  let OP1;
  {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errs = [];
    page.on("console", (m) => {
      if (m.type() === "error") errs.push(m.text());
    });
    page.on("pageerror", (e) => errs.push(String(e)));
    await page.addInitScript({ content: hwScript(8, 8) + "\n" + spyScript() });
    await page.goto(pathToFileURL(join(STAGE, "index.html")).href);
    await settle(page, { target: 8, reach: 12 });
    const kase = JSON.parse(readFileSync(join(STAGE, "boot.json"), "utf8")).cases.find((c) => c.id === "roboto-16");
    const before = (await summary(page)).pc.stored;
    // Fresh page: the sample text is already loaded (the restore button
    // only unhides after a manual edit), so assert and move the reach.
    assert.equal((await summary(page)).summary.text, kase.text);
    await setNumeric(page, "yy-reach-n", "17");
    await settle(page, { reach: 17 });
    const s = await assertQuiet(page, errs, "pool R17");
    const spyObj = await page.evaluate(() => window.__yyT);
    assert.equal(spyObj.workers.length, 2, "guarded pool engaged two workers");
    const jobs = scoreJobs(spyObj);
    assert.equal(jobs.length, 2, "two subjobs posted");
    const a = jobStats(spyObj, jobs[0].jobId),
      b = jobStats(spyObj, jobs[1].jobId);
    assert.ok(a.cpKeys.length > 0 && b.cpKeys.length > 0, "both sides merged checkpoints before done");
    assert.equal(a.maxCalls, 39, "pool side A entered 39 calls");
    assert.equal(b.maxCalls, 39, "pool side B entered 39 calls");
    assert.equal(a.maxCalls, a.maxDone, "side A returns match entries");
    assert.equal(b.maxCalls, b.maxDone, "side B returns match entries");
    const disjoint = a.cpKeys.filter((k) => b.cpKeys.includes(k));
    assert.deepEqual(disjoint, [], "sides computed disjoint pair sets");
    const ledger = await page.evaluate(() => window.__yyPoolJobs);
    const last = ledger[ledger.length - 1];
    assert.equal(last.outcome, "completed", "pool ledger completed");
    assert.equal(await page.evaluate(() => window.__yyPoolTest.current()), null, "aux retired");
    const after = (await summary(page)).pc;
    assert.ok(after.stored - before >= 78, "all 78 pairs stored via checkpoints + final");
    assert.equal(after.overflow, false);
    OP1 = s.summary.origins.join("|");
    // Target-only after pool settle: zero new engine work.
    const calls = s.summary.scoreCalls;
    await setNumeric(page, "yy-spacing-n", "12");
    await settle(page, { target: 12 });
    const s2 = await assertQuiet(page, errs, "pool target-only");
    assert.equal(s2.summary.scoreCalls, calls, "target-only reuses stored curves");
    raw.steps.poolClean = { outcome: last.outcome };
    raw.steps.poolOrigins = OP1.slice(0, 120);
    await page.close();
  }

  // ---- F-pool overlap: shared work joins a live pool job ----
  // Fresh page: the NOVEL R21 pool job is the first pool-scale
  // dispatch, so it is admitted (later pool-scale jobs on a filled
  // page trip the 512MiB backstop and correctly run single). The
  // running 31-pair pool sides. Remainder math is timing-independent:
  // timestamped receipts split what merged before the restore dispatch
  // from the restore set itself, so late checkpoints cannot skew it.
  {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errs = [];
    page.on("console", (m) => {
      if (m.type() === "error") errs.push(m.text());
    });
    page.on("pageerror", (e) => errs.push(String(e)));
    await page.addInitScript({ content: hwScript(8, 8) + "\n" + spyScript() });
    await page.goto(pathToFileURL(join(STAGE, "index.html")).href);
    await settle(page, { target: 8, reach: 12 });
    await resetSpy(page);
    const f0 = await flightStats(page);
    const pc0 = (await summary(page)).pc.stored;
    // Back-to-back inputs: the reach change reconciles first (the
    // text debounce lands on the new reach), so only the R21 pool job
    // ever dispatches. Pool admission probes asynchronously, so wait
    // for both sides to post.
    await setTextFast(page, NOVEL);
    await setNumeric(page, "yy-reach-n", "21");
    await page.waitForFunction(() => window.__yyT.outbound.filter((o) => o.kind === "score").length >= 2, null, {
      polling: 25,
      timeout: 60000,
    });
    const posted = await spy(page);
    assert.equal(posted.workers.length, 2, "pool engaged for the overlap job");
    assert.equal(scoreJobs(posted).length, 2, "only the R21 pool job dispatched");
    const sideJobs = scoreJobs(posted).slice(-2);
    assert.equal(sideJobs.length, 2, "two pool sides dispatched");
    const sideIds = new Set(sideJobs.map((j) => j.jobId));
    await page.waitForFunction(
      (ids) =>
        window.__yyT.inbound.some((r) => ids.includes(r.jobId) && r.kind === "progress" && (r.cpKeys || []).length > 0),
      [...sideIds],
      { polling: 25, timeout: 120000 },
    );
    const cancels0 = (await spy(page)).outbound.filter((o) => o.kind === "cancel").length;
    const scores0 = scoreJobs(await spy(page)).length;
    await setTextFast(page, SUBSET);
    await settle(page, { reach: 21, text: SUBSET });
    await assertQuiet(page, errs, "pool subset join");
    const spyMid = await spy(page);
    const fMid = await flightStats(page);
    assert.equal(spyMid.outbound.filter((o) => o.kind === "cancel").length, cancels0, "pool switch posts no cancel");
    assert.equal(scoreJobs(spyMid).length, scores0, "subset joins running pool work, dispatches nothing");
    assert.ok(fMid.joins > f0.joins, "subset keys joined pool work");
    const sa = jobStats(spyMid, sideJobs[0].jobId),
      sb = jobStats(spyMid, sideJobs[1].jobId);
    assert.ok(sa.cpKeys.length > 0 && sb.cpKeys.length > 0, "both pool sides merged checkpoints before done");
    // The 12-pair view settled, so its prefix merged; the detached
    // tail stops merging (stopping receipts drop silently and stripped
    // dones return nothing new), freezing the store until restore.
    // Only this page's R21 identity ever stores: the job count above
    // proves no stillborn R12 dispatch exists.
    const pcMid = (await summary(page)).pc.stored;
    const prefix = pcMid - pc0;
    assert.ok(prefix >= SUBSET_N, "subset prefix merged from shared work");
    const tRestore = Date.now();
    await setTextFast(page, NOVEL);
    await settle(page, { reach: 21, text: NOVEL });
    const sRestore = await assertQuiet(page, errs, "pool full restore");
    const spyEnd = await spy(page);
    const newJobs = scoreJobs(spyEnd).filter((o) => o.t >= tRestore);
    let restoredCalls = 0,
      restoredDone = 0;
    for (const j of newJobs) {
      const st = jobStats(spyEnd, j.jobId);
      restoredCalls += st.maxCalls;
      restoredDone += st.maxDone;
    }
    assert.equal(restoredCalls, NOVEL_N - prefix, "restore dispatches only the remainder");
    assert.equal(restoredDone, restoredCalls, "remainder returns match entries");
    const pcEnd = (await summary(page)).pc.stored;
    assert.equal(pcEnd - pc0, NOVEL_N, "every pair stored exactly once");
    const fEnd = await flightStats(page);
    assert.equal(fEnd.running, 0, "no running keys leaked");
    raw.steps.poolOverlap = {
      subset: SUBSET_N,
      joins: fMid.joins - f0.joins,
      prefix,
      origins: sRestore.summary.origins.join("|").slice(0, 120),
    };
    await page.close();
  }

  // ---- F-pool aux loss: validated prefix survives, bounded recovery ----
  // Fresh page so the default-scale pool job is admitted; the aux is
  // the non-primary recipient of the two pool side posts. If the job
  // already drained, the skip is recorded instead of killing idle work.
  {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errs = [];
    page.on("console", (m) => {
      if (m.type() === "error") errs.push(m.text());
    });
    page.on("pageerror", (e) => errs.push(String(e)));
    await page.addInitScript({ content: hwScript(8, 8) + "\n" + spyScript() });
    await page.goto(pathToFileURL(join(STAGE, "index.html")).href);
    await settle(page, { target: 8, reach: 12 });
    const kase = JSON.parse(readFileSync(join(STAGE, "boot.json"), "utf8")).cases.find((c) => c.id === "roboto-16");
    await resetSpy(page);
    const pcL0full = (await summary(page)).pc;
    const pcL0 = pcL0full.stored;
    const pcL0stored = pcL0full.stored;
    await setNumeric(page, "yy-reach-n", "17");
    await page.waitForFunction((b) => window.__yyPairCacheTest.stats().checkpointStored > b, pcL0, {
      polling: 25,
      timeout: 120000,
    });
    const keptAtKill = (await summary(page)).pc.stored - pcL0;
    const kill = await page.evaluate(() => {
      const T = window.__yyT;
      const live = T.outbound
        .filter((o) => o.kind === "score")
        .slice(-2)
        .map((o) => o.jobId);
      const term = T.inbound.some((r) => live.includes(r.jobId) && (r.kind === "done" || r.kind === "score-stopped"));
      if (term) return { killed: false, workers: T.workers.length };
      const auxIdx = T.outbound
        .filter((o) => live.includes(o.jobId))
        .map((o) => o.worker)
        .find((i) => i !== 0);
      if (auxIdx === undefined) {
        return { killed: false, workers: T.workers.length, reason: "no-aux" };
      }
      T.workers[auxIdx].terminate();
      return { killed: true, workers: T.workers.length, aux: auxIdx };
    });
    assert.ok(kill.workers >= 2, "a pool aux existed");
    await settle(page, { reach: 17, text: kase.text });
    await assertQuiet(page, errs, "pool aux-loss recovery");
    // Fresh stores, not checkpoints: a tail pair may legitimately
    // merge through the final receipt only. Silent worker death is
    // detected by the inactivity watchdog (terminate() never fires
    // onerror), and that bounded path is what this exercises.
    const pcL1 = (await summary(page)).pc;
    assert.equal(pcL1.stored - pcL0stored, 78, "recovery stores every pair exactly once");
    const ledger2 = await page.evaluate(() => window.__yyPoolJobs);
    const last2 = ledger2[ledger2.length - 1];
    if (kill.killed) {
      assert.ok(keptAtKill >= 1, "prefix merged before the kill");
      assert.ok(
        last2.outcome === "recovered-complete" || String(last2.outcome).startsWith("retrying:"),
        `bounded recovery recorded (${last2.outcome})`,
      );
    } else {
      assert.equal(last2.outcome, "completed", "undisturbed job completes");
    }
    const fEnd = await flightStats(page);
    assert.equal(fEnd.running, 0, "no running keys leaked");
    const retryJobs = scoreJobs(await spy(page))
      .slice(2)
      .map((o) => ({ job: o.jobId, n: o.nItems }));
    raw.steps.poolAuxLoss = {
      killed: kill.killed,
      keptAtKill,
      outcome: last2.outcome,
      workers: kill.workers,
      reason: kill.reason || kill.aux !== undefined ? "aux-" + kill.aux : null,
      retries: retryJobs,
    };
    await page.close();
  }

  // ---- F-fallback: Worker-disabled main-thread path ----
  {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errs = [];
    page.on("console", (m) => {
      if (m.type() === "error") errs.push(m.text());
    });
    page.on("pageerror", (e) => errs.push(String(e)));
    await page.addInitScript({ content: "(() => { try { window.Worker = undefined; } catch (e) {} })();" });
    await page.goto(pathToFileURL(join(STAGE, "index.html")).href);
    await settle(page, { target: 8, reach: 12 });
    await setText(page, SHORT);
    await settle(page, { text: SHORT });
    const mcR12 = (await summary(page)).mainCalls.calls;
    await setNumeric(page, "yy-reach-n", "14");
    await settle(page, { reach: 14, text: SHORT });
    const s = await assertQuiet(page, errs, "fallback SHORT R14");
    assert.equal(s.mainCalls.calls, mcR12 + 8, "main thread entered 8 engine calls");
    assert.equal(s.mainCalls.errors, 0);
    assert.equal(s.summary.origins.join("|"), O1, "fallback choices equal worker path");
    const px = await page.evaluate(() => document.getElementById("yy-adjusted").toDataURL());
    assert.equal(px, P1, "fallback pixels equal worker path");
    // T18 toggle on the fallback path: the text change computes the
    // fresh set at R14, R13 computes its own set once, both revisits
    // are zero work with single-path-identical choices.
    await setText(page, T18);
    await settle(page, { reach: 14, text: T18 });
    await setNumeric(page, "yy-reach-n", "13");
    await settle(page, { reach: 13, text: T18 });
    const r13 = await assertQuiet(page, errs, "fallback T18 R13");
    assert.equal(r13.summary.origins.join("|"), T18_R13, "fallback matches single-path choices");
    const c13 = r13.summary.scoreCalls;
    await setNumeric(page, "yy-reach-n", "14");
    await settle(page, { reach: 14, text: T18 });
    const r14b = await assertQuiet(page, errs, "fallback T18 R14");
    assert.equal(r14b.summary.scoreCalls, c13, "R14 reuses its computation");
    await setNumeric(page, "yy-reach-n", "13");
    await settle(page, { reach: 13, text: T18 });
    const back = await assertQuiet(page, errs, "fallback T18 restore");
    assert.equal(back.summary.origins.join("|"), T18_R13);
    const mcAfter = (await summary(page)).mainCalls.calls;
    assert.equal(back.summary.scoreCalls, c13, "R13 restore is free");
    raw.steps.fallback = { mainCalls: mcAfter };
    await page.close();
  }

  raw.steps.activeShaOk = true;
  raw.pins = {
    activePage: FROZEN_PAGE_SHA,
    stage: STAGE,
    wiring: "8b99dd65d8c8104a1d2afb278d8d4f7dade1e4a678669a4c0e7904d64a4d91a2",
    worker: "3b838ad5c1136951ec76be32b89949dc1455dea74cf66a7dfe772f5d2cded349",
  };
} finally {
  await browser.close();
}

const outPath = process.argv.includes("--out")
  ? process.argv[process.argv.indexOf("--out") + 1]
  : resolve(repo, "out/diagnostics/contextual-spacing/yinyang-update-performance/wave3/inflight/raw-inflight.json");
writeFileSync(outPath, JSON.stringify(raw, null, 2) + "\n");
console.log("pairflight browser: all gates passed");
console.log("raw: " + outPath);
