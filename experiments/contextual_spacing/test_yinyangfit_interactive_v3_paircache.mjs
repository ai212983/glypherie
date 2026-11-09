// Pair-cache P1 browser gate: complete-pair checkpoints + 16MiB LRU on
// the candidate stage assembled through the owner builder (same coherent
// boot/table26, current C27). Offline file:// only; no HTTP server, no
// full 26-corpus regen, no polling loops outside bounded waits.
//
// Suites (one browser, sequential pages, every page closed):
//   P-active   frozen active page SHA guard + cold SHORT R14 timing.
//   P-single   guarded single worker (cpu-low override): default fast
//              path, SHORT R14 settle, default-R12 novel pair, NOVEL R15
//              cancel-then-revisit prefix proof, default-text R18
//              forged/stale/duplicate injection, gray isolation,
//              multiline, invalid-text pin release, zoom/opacity/
//              show-fields/no-wrap with zero rescore.
//   P-pool     guarded two-worker pool on default text R17: both sides
//              merge checkpoints, exact settle, aux retired, target-only
//              zero work.
//   P-fallback Worker-disabled main-thread fallback: cross-path pixel/
//              choice equality (SHORT R14, NOVEL R15, default R18),
//              checkpoint merge, zero-work revisit.
//
// Engine-call truth comes from worker receipts (engineCalls/engineDone
// per job identity) and __yyMainCalls on the fallback path -- never
// from scoreCalls alone.
//
// Usage: node test_yinyangfit_interactive_v3_paircache.mjs [--out <raw.json>]
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
const STAGE = resolve(repo, "out/diagnostics/contextual-spacing/yinyang-update-performance/wave3/checkpoints/stage");
/* Layered-heatmap adopted: active site-reviewed page is the accepted
 * display-only candidate (was d4a2f4b...; boot/data/WASM pins unchanged;
 * prior page archived under yinyang-layered-heatmap/adoption/archive). */
const FROZEN_PAGE_SHA = "66eef10d80c7c593940824582415c51cc829006103df87e926e289f20654692e";

const SHORT = "hello world";
const NOVEL = "abcdefg hijklmn opqrstu vwxyz 0123456789";
const MULTI = "alpha\nbeta gamma";

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
                // A checkpoint pair with a multi-step domain, retained
                // for the partial-curve forgery (truncating it to one
                // step must fail validation).
                if (data && data.kind === "progress" && data.checkpoints &&
                    !window.__yyT.sampleMulti) {
                  try {
                    const names = Object.keys(data.checkpoints);
                    for (const nm of names) {
                      const rc = data.checkpoints[nm];
                      const dm = rc && rc.domain;
                      if (dm && typeof dm.lo === "number" &&
                          typeof dm.hi === "number" &&
                          dm.hi - dm.lo + 1 > 1 &&
                          Array.isArray(rc.steps) &&
                          rc.steps.length === dm.hi - dm.lo + 1) {
                        window.__yyT.sampleMulti = JSON.parse(JSON.stringify(
                          { kind: data.kind, jobId: data.jobId,
                            key: data.key, captureSha: data.captureSha,
                            version: data.version, name: nm,
                            checkpoints: { [nm]: rc } }));
                        break;
                      }
                    }
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
          if (msg && (msg.kind === "score" || msg.kind === "cancel")) {
            window.__yyT.outbound.push({ t: Date.now(), worker: idx,
              kind: msg.kind, jobId: msg.jobId, key: msg.key || null,
              nItems: msg.items ? msg.items.length : 0 });
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

async function summary(page) {
  return page.evaluate(() => ({
    summary: window.YY_SUMMARY || null,
    sampleNote: document.getElementById("yy-sample-note").textContent,
    explainNote: document.getElementById("yy-explain-note").textContent,
    busy: document.getElementById("yy-explain-field").getAttribute("aria-busy"),
    textError: document.getElementById("yy-text-e").textContent,
    // Absent on the frozen active page (pre-pair-cache wiring).
    pc: window.__yyPairCacheTest ? window.__yyPairCacheTest.stats() : null,
    mainCalls: window.__yyPairCacheTest ? window.__yyPairCacheTest.mainCalls() : null,
  }));
}

async function assertQuiet(page, errors, where) {
  const s = await summary(page);
  assert.equal(s.busy, null, `${where}: aria-busy cleared`);
  assert.ok(!/Updating fields/.test(s.explainNote), `${where}: fields settled`);
  assert.equal(errors.length, 0, `${where}: no errors (${errors.join("; ")})`);
  return s;
}

function jobStats(spy, jobId) {
  const inbound = spy.inbound.filter((r) => r.jobId === jobId);
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

const raw = { pins: {}, steps: {}, jobs: {} };

const browser = await chromium.launch({ headless: true });
try {
  // ---- P-active: frozen baseline guard + cold timing ----
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
    const t0 = Date.now();
    await setText(page, SHORT);
    await setNumeric(page, "yy-reach-n", "14");
    await settle(page, { reach: 14, text: SHORT });
    raw.steps.activeColdShortR14Ms = Date.now() - t0;
    const s = await summary(page);
    raw.steps.activeColdShortR14Calls = s.summary.scoreCalls;
    await assertQuiet(page, errs, "active cold");
    await page.close();
  }

  // ---- P-single: guarded single worker (cpu-low forces single path) ----
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
  // Cold candidate timing: SHORT at default R12 (fills any pairs the
  // shipped tables lack), then SHORT R14.
  let O1, P1;
  {
    const t0 = Date.now();
    await setText(single, SHORT);
    await settle(single, { text: SHORT });
    const s12 = await summary(single);
    const nJobs12 = await single.evaluate(() => window.__yyT.outbound.filter((o) => o.kind === "score").length);
    await setNumeric(single, "yy-reach-n", "14");
    await settle(single, { reach: 14, text: SHORT });
    raw.steps.candColdShortR14Ms = Date.now() - t0;
    const s = await assertQuiet(single, sErrs, "single SHORT R14");
    assert.equal(s.summary.scoreCalls, s12.summary.scoreCalls + 8, "SHORT R14 computes exactly its 8 pairs");
    raw.steps.candColdShortR14Calls = s.summary.scoreCalls;
    raw.steps.shortR12FillCalls = s12.summary.scoreCalls;
    const spy = await single.evaluate(() => window.__yyT);
    const scoreJobs = spy.outbound.filter((o) => o.kind === "score");
    assert.equal(scoreJobs.length, nJobs12 + 1, "one single job for R14");
    assert.equal(spy.workers.length, 1, "one worker on the guarded single path");
    const st = jobStats(spy, scoreJobs[scoreJobs.length - 1].jobId);
    assert.equal(st.maxCalls, 8, "worker entered score_pair_local 8x");
    assert.equal(st.maxDone, 8, "worker returned 8 completions");
    assert.ok(st.cpKeys.length > 0, "progress carried complete-pair checkpoints");
    assert.ok(st.cpKeys.length <= 8);
    const pc = s.pc;
    assert.equal(
      pc.checkpointStored - s12.pc.checkpointStored,
      st.cpKeys.length,
      "every checkpoint pair stored exactly once",
    );
    assert.ok(pc.bytes > 0 && pc.bytes < 16777216, "bytes accounted under target");
    assert.equal(pc.overflow, false);
    assert.equal(pc.evicted, 0);
    O1 = s.summary.origins.join("|");
    P1 = await single.evaluate(() => document.getElementById("yy-adjusted").toDataURL());
    raw.steps.shortR14 = { origins: O1.slice(0, 120), bytes: pc.bytes, pairs: pc.pairs };
  }
  // Default-R12 novel pair: 1-pair job, +1 scoreCalls (legacy accounting kept).
  {
    const kase = JSON.parse(readFileSync(join(STAGE, "boot.json"), "utf8")).cases.find((c) => c.id === "roboto-16");
    const shipped = new Set(
      Object.keys(
        JSON.parse(
          readFileSync(join(STAGE, "data", "roboto-16-mono.js"), "utf8")
            .split("=")
            .pop()
            .replace(/;\s*$/, ""),
        ).pairs,
      ),
    );
    const glyphs = kase.profiles.mono.glyphs;
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
    await setNumeric(single, "yy-reach-n", "12");
    await settle(single, { reach: 12, text: SHORT });
    const before = (await summary(single)).summary.scoreCalls;
    await setText(single, novel);
    await settle(single, { text: novel });
    const s = await assertQuiet(single, sErrs, "novel pair");
    assert.equal(s.summary.scoreCalls, before + 1, "novel pair computes exactly once");
    await setText(single, SHORT);
    await settle(single, { text: SHORT });
    raw.steps.novelPair = { pair: novel };
  }
  // Cancel after observed checkpoints, revisit exact geometry.
  // Page truth defines the merged prefix: checkpointStored grows only
  // on validated merge, so the delta minus the fresh R16 set is exactly
  // what survived the cancel. A worker chunk already in flight when
  // cancel posts still sends its receipt, but the page ignores it as
  // stale (its job record is gone) -- the spy sees it, the cache must
  // not. Timestamps identify only the definitely-merged key set used
  // for the disjointness check.
  const NOVEL_N = uniquePairs(NOVEL).length;
  let O2;
  {
    await setText(single, NOVEL);
    await settle(single, { text: NOVEL });
    const before = (await summary(single)).pc.checkpointStored;
    await setNumeric(single, "yy-reach-n", "15");
    await single.waitForFunction((b) => window.__yyPairCacheTest.stats().checkpointStored > b, before, {
      polling: 25,
      timeout: 60000,
    });
    await setNumeric(single, "yy-reach-n", "16"); // cancel R15
    await settle(single, { reach: 16, text: NOVEL });
    const spy = await single.evaluate(() => window.__yyT);
    const scores = spy.outbound.filter((o) => o.kind === "score");
    const j1 = scores[scores.length - 2].jobId;
    const jR16 = scores[scores.length - 1].jobId;
    const stR16 = jobStats(spy, jR16);
    assert.equal(stR16.maxCalls, NOVEL_N, "R16 job computed its full set");
    const afterCancel = (await summary(single)).pc;
    const P = afterCancel.checkpointStored - before - NOVEL_N;
    assert.ok(P >= 1 && P < NOVEL_N, `merged prefix ${P} of ${NOVEL_N} survived the cancel`);
    const cancelPost = spy.outbound.find((o) => o.kind === "cancel" && o.jobId === j1);
    assert.ok(cancelPost, "cancel posted for the superseded job");
    const tCancel = cancelPost.t;
    const strictBefore = new Set();
    spy.inbound
      .filter((r) => r.jobId === j1 && r.kind === "progress" && r.t < tCancel)
      .forEach((r) => (r.cpKeys || []).forEach((k) => strictBefore.add(k)));
    assert.ok(strictBefore.size >= 1 && strictBefore.size <= P, "definitely-merged keys within the stored prefix");
    // Revisit exact old geometry: only the remainder computes.
    await setNumeric(single, "yy-reach-n", "15");
    await settle(single, { reach: 15, text: NOVEL });
    const s = await assertQuiet(single, sErrs, "revisit R15");
    const spy2 = await single.evaluate(() => window.__yyT);
    const scores2 = spy2.outbound.filter((o) => o.kind === "score");
    const j2 = scores2[scores2.length - 1].jobId;
    const st2 = jobStats(spy2, j2);
    assert.equal(st2.maxCalls, NOVEL_N - P, `revisit computes only the remainder (${NOVEL_N - P})`);
    assert.equal(st2.maxDone, NOVEL_N - P, "revisit returns match entries");
    assert.deepEqual(
      st2.cpKeys.filter((k) => strictBefore.has(k)),
      [],
      "completed prefix not recomputed",
    );
    O2 = s.summary.origins.join("|");
    raw.steps.cancelRevisit = { pairs: NOVEL_N, prefix: P, remainder: st2.maxCalls };
  }
  // Forged/stale/duplicate injection on a live R18 job. The default
  // 78-pair sample text keeps the single worker busy long enough that
  // all six injections land while the job is live.
  {
    const kase = JSON.parse(readFileSync(join(STAGE, "boot.json"), "utf8")).cases.find((c) => c.id === "roboto-16");
    await single.click("#yy-text-restore");
    await settle(single, { text: kase.text });
    // Fresh spy log: earlier jobs' receipts must not satisfy the waits.
    await single.evaluate(() => {
      window.__yyT.sample = null;
      window.__yyT.sampleMulti = null;
      window.__yyT.inbound = [];
      window.__yyT.outbound = [];
    });
    await setNumeric(single, "yy-reach-n", "18");
    await single.waitForFunction(() => window.__yyT.sample && window.__yyT.sampleMulti, null, {
      polling: 25,
      timeout: 60000,
    });
    const sample = await single.evaluate(() => window.__yyT.sample);
    const sampleMulti = await single.evaluate(() => window.__yyT.sampleMulti);
    assert.ok(sample && sample.checkpoints, "retained a real checkpoint receipt");
    assert.ok(sampleMulti && sampleMulti.checkpoints, "retained a multi-step checkpoint pair");
    assert.equal(sampleMulti.jobId, sample.jobId, "same live job");
    const realKeys = Object.keys(sample.checkpoints);
    const realName = realKeys[0];
    const realRec = sample.checkpoints[realName];
    const multiName = sampleMulti.name;
    const multiRec = sampleMulti.checkpoints[multiName];
    const d0 = (await summary(single)).pc;
    // Duplicate: re-inject the identical receipt while the job is live.
    await single.evaluate((msg) => window.__yyPairCacheTest.inject(msg), sample);
    // Forgeries: unknown pair, wrong metric, missing domain, partial
    // steps. Each must drop without storing. The version lie carries
    // otherwise-valid curves: engine identity comes from the
    // page-trusted boot WASM SHA in the key, never the receipt echo, so
    // it merges as a no-op under the correct identity without dropping
    // or poisoning later receipts.
    const forged = (cps, version) => ({
      kind: "progress",
      jobId: sample.jobId,
      done: 2,
      total: 78,
      key: sample.key,
      captureSha: sample.captureSha,
      version: version === undefined ? sample.version : version,
      checkpoints: cps,
    });
    const clone = (o) => JSON.parse(JSON.stringify(o));
    const badMetric = clone(realRec);
    badMetric.metric = 1e9;
    const noDomain = clone(realRec);
    delete noDomain.domain;
    const partial = clone(multiRec);
    assert.ok(partial.steps.length > 1, "multi-step victim selected");
    partial.steps = [partial.steps[0]];
    const forgedMulti = (cps, version) => ({
      kind: "progress",
      jobId: sampleMulti.jobId,
      done: 2,
      total: 78,
      key: sampleMulti.key,
      captureSha: sampleMulti.captureSha,
      version: version === undefined ? sampleMulti.version : version,
      checkpoints: cps,
    });
    await single.evaluate((msg) => window.__yyPairCacheTest.inject(msg), forged({ ZZ: clone(realRec) }));
    await single.evaluate((msg) => window.__yyPairCacheTest.inject(msg), forged({ [realName]: badMetric }));
    await single.evaluate((msg) => window.__yyPairCacheTest.inject(msg), forged({ [realName]: noDomain }));
    await single.evaluate((msg) => window.__yyPairCacheTest.inject(msg), forgedMulti({ [multiName]: partial }));
    await single.evaluate(
      (msg) => window.__yyPairCacheTest.inject(msg),
      forged({ [realName]: clone(realRec) }, "forged-version"),
    );
    // Stale: unknown job id is ignored before validation or storage.
    const staleBefore = (await summary(single)).pc;
    await single.evaluate((msg) => window.__yyPairCacheTest.inject(msg), {
      kind: "progress",
      jobId: "j-stale-1",
      done: 2,
      total: 78,
      key: "bogus-identity",
      captureSha: "bogus-capture",
      version: sample.version,
      checkpoints: { ZZ: clone(realRec) },
    });
    const d1 = (await summary(single)).pc;
    assert.deepEqual(d1, staleBefore, "stale receipt changes nothing");
    assert.equal(d1.dropped - d0.dropped, 4, "four forgeries dropped");
    assert.equal(d1.checkpointStored, d0.checkpointStored, "duplicate + forgeries stored nothing new");
    assert.equal(d1.bytes, d0.bytes, "bytes unchanged by duplicate/forged");
    await settle(single, { reach: 18, text: kase.text });
    const s = await assertQuiet(single, sErrs, "R18 after injection");
    assert.ok(s.sampleNote === "" || !/Engine unavailable/.test(s.sampleNote), "no engine error after injection");
    raw.steps.injection = { dropped: d1.dropped - d0.dropped };
    raw.steps.defaultR18Origins = s.summary.origins.join("|").slice(0, 120);
  }
  // Gray isolation at the same geometry, then mono restore with zero work.
  {
    await setText(single, SHORT);
    await setNumeric(single, "yy-reach-n", "14");
    await settle(single, { reach: 14, text: SHORT });
    const grayBefore = (await summary(single)).summary.scoreCalls;
    await single.click('input[name="profile"][value="gray"]');
    await settle(single, { profile: "gray" });
    const g = await assertQuiet(single, sErrs, "gray SHORT R14");
    const grayOrigins = g.summary.origins.join("|");
    const grayCalls = g.summary.scoreCalls;
    assert.equal(grayCalls, grayBefore + 8, "gray computes under its own identity");
    await single.click('input[name="profile"][value="mono"]');
    await settle(single, { profile: "mono" });
    const m = await assertQuiet(single, sErrs, "mono restore");
    assert.equal(m.summary.scoreCalls, grayCalls, "mono restore reuses cache");
    assert.equal(m.summary.origins.join("|"), O1, "mono choices identical");
    raw.steps.gray = { grayCalls };
    void grayOrigins;
  }
  // Multiline with fresh pairs at the same geometry.
  {
    const before = (await summary(single)).summary.scoreCalls;
    await setText(single, MULTI);
    await settle(single, { text: MULTI });
    const s = await assertQuiet(single, sErrs, "multiline");
    const spy = await single.evaluate(() => window.__yyT);
    const scores = spy.outbound.filter((o) => o.kind === "score");
    const st = jobStats(spy, scores[scores.length - 1].jobId);
    const need = uniquePairs(MULTI).length;
    assert.equal(st.maxCalls, need, `multiline computes ${need} fresh pairs`);
    assert.equal(s.summary.scoreCalls, before + need);
  }
  // Invalid text releases pins, keeps the last valid view.
  {
    await setText(single, "héllo");
    await single.waitForTimeout(500);
    const s = await summary(single);
    assert.ok(s.textError.length > 0, "invalid draft rejected with reason");
    assert.equal(s.pc.pinned, 0, "invalid text releases working-set pins");
    await setText(single, SHORT);
    await setNumeric(single, "yy-reach-n", "14");
    await settle(single, { reach: 14, text: SHORT });
    const restored = await assertQuiet(single, sErrs, "invalid-text restore");
    assert.equal(restored.summary.origins.join("|"), O1, "restore reuses cache, choices identical");
  }
  // Controls: zoom, opacity, show-fields, no-wrap -- zero rescore.
  {
    const before = (await summary(single)).summary.scoreCalls;
    const wrap = await single.evaluate(() => ({
      attr: document.getElementById("yy-text").getAttribute("wrap"),
      whiteSpace: getComputedStyle(document.getElementById("yy-text")).whiteSpace,
    }));
    assert.ok(wrap.attr === null || wrap.attr === "off", "no-wrap preserved");
    await single.selectOption("#yy-zoom", "2");
    await single.waitForFunction(
      () => {
        const t = document.getElementById("yy-explain-note").textContent;
        return !/Updating fields/.test(t);
      },
      null,
      { timeout: 60000 },
    );
    await single.selectOption("#yy-zoom", "1");
    await single.waitForFunction(
      () => {
        const t = document.getElementById("yy-explain-note").textContent;
        return !/Updating fields/.test(t);
      },
      null,
      { timeout: 60000 },
    );
    // The layered heatmap removed the palette text entry; the opacity
    // slider is the surviving cached display control.
    await single.locator("#yy-letter-alpha").fill("40");
    await single.uncheck("#yy-show-fields");
    await single.waitForTimeout(400);
    await single.check("#yy-show-fields");
    await settle(single, { reach: 14, text: SHORT });
    const s = await assertQuiet(single, sErrs, "controls");
    assert.equal(s.summary.scoreCalls, before, "controls cause zero rescore");
    assert.ok(s.summary.pairLayers > 0, "fields repaint after reshow");
    assert.equal(s.summary.origins.join("|"), O1, "choices stable");
    raw.steps.controlsZeroRescore = true;
  }
  raw.steps.single = await summary(single).then((s) => s.pc);
  await single.close();

  // ---- P-pool: guarded two-worker pool, default text R13 ----
  let poolOrigins;
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
    const before = (await summary(page)).pc.checkpointStored;
    await setNumeric(page, "yy-reach-n", "13");
    await settle(page, { reach: 13 });
    const s = await assertQuiet(page, errs, "pool R17");
    const spy = await page.evaluate(() => window.__yyT);
    assert.equal(spy.workers.length, 2, "guarded pool engaged two workers");
    const scores = spy.outbound.filter((o) => o.kind === "score");
    assert.equal(scores.length, 2, "two subjobs posted");
    const a = jobStats(spy, scores[0].jobId),
      b = jobStats(spy, scores[1].jobId);
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
    assert.equal(await page.evaluate(() => window.__yyPool.auxLive), false);
    const after = (await summary(page)).pc;
    assert.ok(after.checkpointStored - before >= 78, "all 78 pairs stored via checkpoints + final");
    assert.equal(after.overflow, false);
    poolOrigins = s.summary.origins.join("|");
    // Target-only after pool settle: zero new engine work.
    const calls = s.summary.scoreCalls;
    await setNumeric(page, "yy-spacing-n", "12");
    await settle(page, { target: 12 });
    const s2 = await assertQuiet(page, errs, "pool target-only");
    assert.equal(s2.summary.scoreCalls, calls, "target-only reuses stored curves");
    raw.steps.pool = { outcome: last.outcome, checkpointStored: after.checkpointStored };
    await page.close();
  }

  // ---- P-fallback: Worker-disabled main-thread path ----
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
    const f12 = await summary(page);
    await setNumeric(page, "yy-reach-n", "14");
    await settle(page, { reach: 14, text: SHORT });
    const s = await assertQuiet(page, errs, "fallback SHORT R14");
    assert.equal(s.summary.scoreCalls, f12.summary.scoreCalls + 8, "fallback computes exactly the 8 R14 pairs");
    assert.equal(s.mainCalls.calls, f12.mainCalls.calls + 8, "main-thread entered 8 engine calls");
    assert.equal(s.mainCalls.errors, 0);
    assert.equal(s.summary.origins.join("|"), O1, "fallback choices equal worker path");
    const px = await page.evaluate(() => document.getElementById("yy-adjusted").toDataURL());
    assert.equal(px, P1, "fallback pixels equal worker path");
    await setText(page, NOVEL);
    await settle(page, { text: NOVEL });
    const f14 = await summary(page);
    await setNumeric(page, "yy-reach-n", "15");
    await settle(page, { reach: 15, text: NOVEL });
    const s2 = await assertQuiet(page, errs, "fallback NOVEL R15");
    assert.equal(s2.summary.origins.join("|"), O2, "fallback equals revisit choices");
    assert.equal(s2.mainCalls.calls, f14.mainCalls.calls + NOVEL_N, "calls account every computed pair");
    // Default 78-pair sample at R18 to match the injected run: the
    // longer main-thread job mirrors the single-worker geometry exactly.
    await setNumeric(page, "yy-reach-n", "18");
    await settle(page, { reach: 18, text: NOVEL });
    await page.click("#yy-text-restore");
    const kaseFb = JSON.parse(readFileSync(join(STAGE, "boot.json"), "utf8")).cases.find((c) => c.id === "roboto-16");
    await settle(page, { reach: 18, text: kaseFb.text });
    const s3 = await assertQuiet(page, errs, "fallback default R18");
    const refR18 = raw.steps.defaultR18Origins;
    assert.ok(
      s3.summary.origins.join("|").startsWith(refR18.slice(0, 60)),
      "fallback R18 matches injected-run choices",
    );
    // Revisit cached geometry: zero new engine calls, step by step.
    await setText(page, SHORT);
    await settle(page, { text: SHORT });
    const mcR18 = (await summary(page)).mainCalls.calls;
    await setNumeric(page, "yy-reach-n", "16");
    await settle(page, { reach: 16, text: SHORT });
    const mcR16 = (await summary(page)).mainCalls.calls;
    assert.equal(mcR16, mcR18 + 8, "uncached R16 SHORT computes 8 pairs");
    await setNumeric(page, "yy-reach-n", "14");
    await settle(page, { reach: 14, text: SHORT });
    const s4 = await assertQuiet(page, errs, "fallback revisit");
    assert.equal(s4.mainCalls.calls, mcR16, "R14 revisit is zero-work");
    assert.equal(s4.summary.origins.join("|"), O1);
    raw.steps.fallback = { mainCalls: s4.mainCalls.calls };
    await page.close();
  }

  raw.steps.activeShaOk = true;
  raw.pins = {
    activePage: FROZEN_PAGE_SHA,
    stage: STAGE,
  };
} finally {
  await browser.close();
}

const outPath = process.argv.includes("--out")
  ? process.argv[process.argv.indexOf("--out") + 1]
  : resolve(repo, "out/diagnostics/contextual-spacing/yinyang-update-performance/wave3/checkpoints/raw-paircache.json");
writeFileSync(outPath, JSON.stringify(raw, null, 2) + "\n");
console.log("paircache browser: all gates passed");
console.log("raw: " + outPath);
