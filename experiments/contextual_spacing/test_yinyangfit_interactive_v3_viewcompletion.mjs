// View-completion regression (P4): the current subscribed view must be
// notified by completion/release/error/checkpoint events under identity
// and ownership guards, and settle must never paint or error while the
// current view's needed pairs are still running. Deterministic: the
// page runs verbatim production handlers against a script-driven fake
// Worker, so every interleaving below is exact, not timed. No engine,
// no pixels, no host-load dependence.
//
// Fake worker contract: score posts are recorded, never computed. The
// test delivers structurally valid complete curves (posted item metric,
// contiguous integer steps) as progress checkpoints plus terminal
// receipts in a fixed order, then asserts paint/dispatch/error state.
// Fields run hidden (production show-fields gate: zero field posts,
// ink path and ownership identical), so settle gates on ink origins,
// the note, and the shared busy flag only.
//
// Usage: node test_yinyangfit_interactive_v3_viewcompletion.mjs [--out <raw.json>]
// ONLY=<comma list> runs a subset: join, overlap, gray390, invalid,
// supersede, failure, trim, pool, fallback, noeng, stalefallback,
// stalerecover, ackexpiry. SETTLE_MS bounds each wait.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve, dirname, join } from "node:path";
import { writeFileSync, readFileSync } from "node:fs";
import { pathToFileURL, fileURLToPath } from "node:url";

const require = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const { chromium } = require("playwright-core");
const root = dirname(fileURLToPath(import.meta.url));
const repo = resolve(root, "../..");

const STAGE =
  process.env.STAGE ||
  resolve(repo, "out/diagnostics/contextual-spacing/yinyang-update-performance/wave3/recovery-fix/stage");
const ONLY = (process.env.ONLY || "all").split(",");
const SETTLE_MS = Number(process.env.SETTLE_MS || "60000");
const want = (name) => ONLY.includes("all") || ONLY.includes(name);

const FAKE_SRC = `
window.__yyFake = { workers: [], byJob: {}, posted: [] };
window.Worker = function (url) {
  var idx = window.__yyFake.workers.length;
  var w = { __fakeIdx: idx, url: String(url), terminated: false,
    onmessage: null, onerror: null, onmessageerror: null, listeners: {},
    addEventListener: function (t, fn) {
      (this.listeners[t] = this.listeners[t] || []).push(fn);
    },
    postMessage: function (msg) {
      window.__yyFake.posted.push({ worker: idx, msg: msg });
      if ((msg.kind === "score" || msg.kind === "fields") && msg.jobId) {
        window.__yyFake.byJob[msg.jobId] = idx;
      }
      // The pool probe asks the primary for its engine footprint;
      // answer on the same channel like the real worker.
      if (msg.kind === "pool-stats") {
        setTimeout(function () {
          window.__yyFakeDeliver(idx,
            { kind: "pool-stats", wasmLinearBytes: 33554432 });
        }, 0);
      }
    },
    terminate: function () { this.terminated = true; } };
  window.__yyFake.workers.push(w);
  // The real worker announces itself on startup; the pool aux
  // handshake waits for this before dispatching either side.
  setTimeout(function () {
    window.__yyFakeDeliver(idx,
      { kind: "ready", wasmLinearBytes: 33554432 });
  }, 0);
  return w;
};
window.__yyFakeDeliver = function (idx, msg) {
  var w = window.__yyFake.workers[idx];
  if (!w || w.terminated) return "no-worker";
  if (w.onmessage) w.onmessage({ data: msg });
  (w.listeners.message || []).forEach(function (fn) { fn({ data: msg }); });
  return "delivered";
};
`;

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
function synthRec(metric) {
  const steps = [];
  for (let s = 0; s <= 7; s++) steps.push({ step: s, valid: true, gl: 0 });
  return { metric: metric, steps: steps, domain: { lo: 0, hi: 7 } };
}

const raw = { pins: { stage: STAGE, settleMs: SETTLE_MS }, steps: {} };
const browser = await chromium.launch({ headless: true });
try {
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
  async function newPage(hw) {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errs = [];
    page.on("console", (m) => {
      if (m.type() === "error") errs.push(m.text());
    });
    page.on("pageerror", (e) => errs.push(String(e)));
    page.on("crash", () => errs.push("PAGE-CRASH"));
    await page.addInitScript({ content: hwScript(hw.cpus, hw.mem) });
    await page.addInitScript({ content: FAKE_SRC });
    await page.goto(pathToFileURL(join(STAGE, "index.html")).href);
    // Fields hidden: zero field posts; ink/ownership path unchanged.
    await page.uncheck("#yy-show-fields");
    return { page, errs, done: new Set(), seen: new Set() };
  }
  function summaryMatch(page, expect) {
    return page.evaluate((exp) => {
      const s = window.YY_SUMMARY;
      if (!(s && s.origins && s.origins.length)) return null;
      for (const k of Object.keys(exp)) {
        if (s[k] !== exp[k]) return null;
      }
      const busy = document.getElementById("yy-explain-field").getAttribute("aria-busy");
      const note = document.getElementById("yy-explain-note").textContent;
      if (busy !== null || note !== "") return null;
      return s.origins.join("|");
    }, expect);
  }
  async function originsOf(ctx) {
    return ctx.page.evaluate(() => (window.YY_SUMMARY ? window.YY_SUMMARY.origins.join("|") : null));
  }
  async function setText(ctx, text) {
    await ctx.page.fill("#yy-text", text);
    await ctx.page.waitForTimeout(500);
  }
  async function setReachOnce(ctx, value) {
    await ctx.page.evaluate((v) => {
      const el = document.getElementById("yy-reach-n");
      el.value = String(v);
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }, value);
    await ctx.page.waitForTimeout(500);
  }
  async function posted(ctx) {
    // The Worker-disabled fallback page runs the real engine: no fake,
    // no scripted posts, the driver only waits for calm.
    return ctx.page.evaluate(() => (window.__yyFake ? window.__yyFake.posted.slice() : []));
  }
  async function scores(ctx) {
    return (await posted(ctx)).filter((p) => p.msg.kind === "score");
  }
  async function joins(ctx) {
    return ctx.page.evaluate(() => window.__yyFlightTest.stats().joins);
  }
  async function deliver(ctx, workerIdx, msg) {
    return ctx.page.evaluate(([i, m]) => window.__yyFakeDeliver(i, m), [workerIdx, msg]);
  }
  // Mark every currently posted score job seen: superseded
  // redispatches pending from an earlier step can never be mistaken
  // for the next dispatch. Call only when no needed post is pending.
  async function drainPosts(ctx) {
    const ids = await ctx.page.evaluate(() =>
      window.__yyFake ? window.__yyFake.posted.filter((p) => p.msg.kind === "score").map((p) => p.msg.jobId) : [],
    );
    ids.forEach((id) => ctx.seen.add(id));
  }
  // Next score post whose jobId was never returned nor completed:
  // earlier generations' leftover posts can never be mistaken for
  // the current dispatch.
  async function nextPost(ctx) {
    const known = [...ctx.seen, ...ctx.done];
    const post = await ctx.page.waitForFunction(
      (ids) => {
        const all = window.__yyFake.posted.filter((p) => p.msg.kind === "score");
        return all.find((p) => ids.indexOf(p.msg.jobId) < 0) || null;
      },
      known,
      { polling: 25, timeout: SETTLE_MS },
    );
    const value = await post.jsonValue();
    ctx.seen.add(value.msg.jobId);
    return value;
  }
  // Complete one recorded score post with valid curves for names
  // (default: every item it carries). Progress then terminal, the
  // same two receipts the real worker sends. A post whose transport
  // is gone is orphaned like production's dropped receipts: marked
  // done so the view must resolve without it.
  async function completeJob(ctx, post, names) {
    const items = {};
    const byKey = {};
    post.msg.items.forEach((it) => {
      byKey[it.key] = it;
    });
    (names || post.msg.items.map((it) => it.key)).forEach((name) => {
      items[name] = synthRec(byKey[name].metric);
    });
    const w = post.worker;
    const base = { jobId: post.msg.jobId, key: post.msg.key, captureSha: post.msg.captureSha };
    const p = await deliver(ctx, w, { ...base, kind: "progress", checkpoints: items, done: Object.keys(items).length });
    if (p === "no-worker") {
      ctx.done.add(post.msg.jobId);
      return "orphaned";
    }
    assert.equal(p, "delivered", "progress delivered");
    assert.equal(
      await deliver(ctx, w, { kind: "done", jobId: post.msg.jobId, results: items }),
      "delivered",
      "done delivered",
    );
    ctx.done.add(post.msg.jobId);
    return "completed";
  }
  // Drive the fake engine until the view settles: whenever progress
  // stalls waiting on scripted work, complete every unseen score post
  // with valid curves. Deterministic: no sleeps gate the outcome, the
  // bound only caps a genuine hang. changedFrom optionally requires
  // the settled origins to differ from a pre-terminal snapshot, so a
  // stale premature paint cannot satisfy the gate.
  async function driveToSettled(ctx, expect, changedFrom = null) {
    const t0 = Date.now();
    for (;;) {
      const now = await summaryMatch(ctx.page, expect);
      if (now && (changedFrom === null || now !== changedFrom)) return now;
      if (Date.now() - t0 > SETTLE_MS) {
        throw new Error("settle timeout for " + JSON.stringify(expect));
      }
      let progressed = false;
      for (const post of await scores(ctx)) {
        if (!ctx.done.has(post.msg.jobId)) {
          await completeJob(ctx, post);
          progressed = true;
        }
      }
      if (!progressed) {
        await ctx.page.waitForTimeout(200);
      }
    }
  }
  async function errorState(ctx) {
    return ctx.page.evaluate(() => ({
      note: document.getElementById("yy-explain-note").textContent,
      busy: document.getElementById("yy-explain-field").getAttribute("aria-busy"),
      origins: window.YY_SUMMARY ? window.YY_SUMMARY.origins.join("|") : null,
      text: window.YY_SUMMARY ? window.YY_SUMMARY.text : null,
      reach: window.YY_SUMMARY ? window.YY_SUMMARY.reach : null,
    }));
  }
  async function assertCalm(ctx, where) {
    assert.equal(ctx.errs.length, 0, `${where}: no page errors (${ctx.errs.join("; ")})`);
    const s = await errorState(ctx);
    assert.ok(!/unavailable|failed twice/.test(s.note), `${where}: no engine error (${s.note.slice(0, 80)})`);
    assert.equal(s.busy, null, `${where}: busy cleared`);
    return s;
  }

  const A = "Pack my box"; // subset of the default text pairs
  const A2 = "Pack my box qzx"; // shared prefix plus two novel pairs
  const D = "zq xj qv jk fw"; // five pairs disjoint from the default text
  const LONG = "abc ".repeat(98).slice(0, 390);

  // ---- V-join: same needs re-requested mid-flight ----
  if (want("join")) {
    const ctx = await newPage({ cpus: 2, mem: 8 });
    try {
      await driveToSettled(ctx, { target: 8, reach: 12 });
      await setReachOnce(ctx, 14);
      const j0 = await nextPost(ctx);
      assert.ok(j0.msg.items.length > 40, "reach change dispatches the full set");
      const joins0 = await joins(ctx);
      await setText(ctx, A);
      await ctx.page.waitForFunction((b) => window.__yyFlightTest.stats().joins > b, joins0, {
        polling: 25,
        timeout: SETTLE_MS,
      });
      // The second generation joined running work: nothing new may
      // dispatch, and settle must wait, not paint or error.
      assert.equal((await scores(ctx)).length, 1, "join dispatches nothing new");
      const mid = await errorState(ctx);
      assert.equal(mid.busy, "true", "view stays busy while joined work runs");
      assert.ok(!/unavailable|failed twice/.test(mid.note), "no premature paint or error");
      await completeJob(ctx, j0);
      const painted = await driveToSettled(ctx, { reach: 14 }, mid.origins);
      assert.equal(painted.split("|").length, 1, "joined view paints its single line");
      await assertCalm(ctx, "joined completion");
      assert.equal((await scores(ctx)).length, 1, "completion posts no new engine call");
      raw.steps.join = { runningPairs: j0.msg.items.length };
    } finally {
      await ctx.page.close();
    }
  }

  // ---- V-overlap: shared joins, genuinely new dispatches ----
  if (want("overlap")) {
    const ctx = await newPage({ cpus: 2, mem: 8 });
    try {
      await driveToSettled(ctx, { target: 8, reach: 12 });
      await setReachOnce(ctx, 14);
      const j0 = await nextPost(ctx);
      await setText(ctx, A2);
      const j1 = await nextPost(ctx);
      const j1keys = [...j1.msg.items.map((it) => it.key)].sort();
      assert.deepEqual(j1keys, ["qz", "zx"], "overlap dispatches exactly the novel pairs");
      assert.ok(!j1keys.some((k) => uniquePairs(A).includes(k)), "shared pairs join, never redispatch");
      const pre = await originsOf(ctx);
      await completeJob(ctx, j0);
      await ctx.page.waitForTimeout(500);
      const midOv = await errorState(ctx);
      assert.ok(
        !/unavailable|failed twice/.test(midOv.note),
        "stale producer terminal raises no error on the joined view",
      );
      assert.equal(midOv.busy, "true", "joined view still busy on its own work");
      await completeJob(ctx, j1);
      const painted2 = await driveToSettled(ctx, { reach: 14 }, pre);
      assert.equal(painted2.split("|").length, 1, "overlap paints its single line");
      await assertCalm(ctx, "overlap completion");
      assert.equal((await scores(ctx)).length, 2, "exactly two engine calls total");
      raw.steps.overlap = { shared: uniquePairs(A).length, newOnly: j1keys.length };
    } finally {
      await ctx.page.close();
    }
  }

  // ---- V-gray390: the adoption race, load-independent ----
  if (want("gray390")) {
    const ctx = await newPage({ cpus: 2, mem: 8 });
    try {
      await driveToSettled(ctx, { target: 8, reach: 12 });
      await ctx.page.check("input[name=profile][value=gray]");
      await driveToSettled(ctx, { profile: "gray" });
      await setText(ctx, LONG);
      const j1 = await nextPost(ctx);
      assert.equal(j1.msg.items.length, 2, "long gray text needs 2 uncached pairs");
      const joins0 = await joins(ctx);
      await setText(ctx, LONG);
      await ctx.page.waitForFunction((b) => window.__yyFlightTest.stats().joins > b, joins0, {
        polling: 25,
        timeout: SETTLE_MS,
      });
      assert.equal((await scores(ctx)).length, 1, "second reconcile dispatches nothing");
      const mid = await errorState(ctx);
      assert.ok(!/unavailable|failed twice/.test(mid.note), "no premature paint or error");
      await completeJob(ctx, j1);
      await driveToSettled(ctx, { profile: "gray" }, mid.origins);
      await assertCalm(ctx, "gray completion");
      assert.equal((await scores(ctx)).length, 1, "completion posts no new engine call");
      raw.steps.gray390 = { pairs: 2 };
    } finally {
      await ctx.page.close();
    }
  }

  // ---- V-invalid: terminal must not paint a rejected draft ----
  if (want("invalid")) {
    const ctx = await newPage({ cpus: 2, mem: 8 });
    try {
      await driveToSettled(ctx, { target: 8, reach: 12 });
      const base = (await errorState(ctx)).origins;
      await setReachOnce(ctx, 14);
      const j0 = await nextPost(ctx);
      await setText(ctx, "héllo");
      await ctx.page.waitForTimeout(800);
      const s0 = await errorState(ctx);
      assert.equal(s0.origins, base, "invalid draft keeps the last valid view");
      await completeJob(ctx, j0);
      await ctx.page.waitForTimeout(800);
      const s1 = await errorState(ctx);
      assert.equal(s1.origins, base, "stale terminal never paints the invalid draft");
      assert.ok(!/unavailable|failed twice/.test(s1.note), "no error from the orphan terminal");
      assert.equal(ctx.errs.length, 0, "no page errors");
      raw.steps.invalid = { kept: true };
    } finally {
      await ctx.page.close();
    }
  }

  // ---- V-supersede: stale terminal never paints the newer view ----
  if (want("supersede")) {
    const ctx = await newPage({ cpus: 2, mem: 8 });
    try {
      await driveToSettled(ctx, { target: 8, reach: 12 });
      await setReachOnce(ctx, 14);
      const j0 = await nextPost(ctx);
      const staleOrigins = (await errorState(ctx)).origins;
      await setReachOnce(ctx, 15);
      const j1 = await nextPost(ctx);
      await completeJob(ctx, j0);
      await ctx.page.waitForTimeout(800);
      const mid = await errorState(ctx);
      assert.equal(mid.origins, staleOrigins, "stale terminal paints nothing");
      assert.equal(mid.busy, "true", "newer view still busy on its own work");
      assert.ok(!/unavailable|failed twice/.test(mid.note), "stale terminal raises no error");
      await completeJob(ctx, j1);
      await driveToSettled(ctx, { reach: 15 });
      const end = await assertCalm(ctx, "superseding completion");
      assert.notEqual(end.origins, staleOrigins, "newer work paints on completion");
      assert.equal((await scores(ctx)).length, 2, "no duplicate engine call");
      raw.steps.supersede = { kept: true };
    } finally {
      await ctx.page.close();
    }
  }

  // ---- V-failure: genuine validation failures stay bounded ----
  if (want("failure")) {
    const ctx = await newPage({ cpus: 2, mem: 8 });
    try {
      await driveToSettled(ctx, { target: 8, reach: 12 });
      await setReachOnce(ctx, 14);
      const j0f = await nextPost(ctx);
      const bad = {};
      j0f.msg.items.forEach((it) => {
        bad[it.key] = synthRec(9999);
      });
      const w = j0f.worker;
      const jid = j0f.msg.jobId;
      await deliver(ctx, w, {
        kind: "progress",
        jobId: jid,
        key: j0f.msg.key,
        captureSha: j0f.msg.captureSha,
        checkpoints: bad,
        done: 0,
      });
      await deliver(ctx, w, { kind: "done", jobId: jid, results: bad });
      const j1f = await nextPost(ctx);
      await deliver(ctx, j1f.worker, {
        kind: "progress",
        jobId: j1f.msg.jobId,
        key: j1f.msg.key,
        captureSha: j1f.msg.captureSha,
        checkpoints: {},
        done: 0,
      });
      await deliver(ctx, j1f.worker, { kind: "done", jobId: j1f.msg.jobId, results: bad });
      await ctx.page.waitForFunction(
        () => /failed twice/.test(document.getElementById("yy-explain-note").textContent),
        null,
        { timeout: SETTLE_MS },
      );
      await ctx.page.waitForTimeout(1200);
      assert.equal((await scores(ctx)).length, 2, "bounded retry: no third engine call");
      const st = await ctx.page.evaluate(() => window.__yyFlightTest.stats());
      assert.equal(st.running, 0, "no running keys leaked");
      assert.equal(st.calls, 0, "no live calls leaked");
      raw.steps.failure = { bounded: true };
    } finally {
      await ctx.page.close();
    }
  }

  // ---- V-trim: stop-ack releases, current view re-resolves ----
  if (want("trim")) {
    const ctx = await newPage({ cpus: 2, mem: 8 });
    try {
      await driveToSettled(ctx, { target: 8, reach: 12 });
      await setReachOnce(ctx, 14);
      const j0 = await nextPost(ctx);
      await setText(ctx, D);
      const drop = (await posted(ctx)).find((p) => p.msg.kind === "drop");
      assert.ok(drop, "trim posts a drop for unneeded work");
      const j1 = await nextPost(ctx);
      assert.deepEqual(
        [...j1.msg.items.map((it) => it.key)].sort(),
        [...uniquePairs(D)].sort(),
        "current view dispatches its own pairs",
      );
      await deliver(ctx, j0.worker, { kind: "score-stopped", jobId: j0.msg.jobId });
      await ctx.page.waitForTimeout(500);
      const midTrim = await errorState(ctx);
      assert.ok(!/unavailable|failed twice/.test(midTrim.note), "stop-ack raises no error on the waiting view");
      assert.equal(midTrim.busy, "true", "trimmed view still busy on its own work");
      const preD = await originsOf(ctx);
      await completeJob(ctx, j1);
      const paintedD = await driveToSettled(ctx, { reach: 14 }, preD);
      assert.equal(paintedD.split("|").length, 1, "trimmed view paints its single line");
      await assertCalm(ctx, "trimmed completion");
      raw.steps.trim = { kept: true };
    } finally {
      await ctx.page.close();
    }
  }

  // ---- V-pool: two-sided terminal presents once ----
  if (want("pool")) {
    const ctx = await newPage({ cpus: 8, mem: 8 });
    try {
      await driveToSettled(ctx, { target: 8, reach: 12 });
      await setReachOnce(ctx, 17);
      const pa = await nextPost(ctx);
      const pb = await nextPost(ctx);
      const both = [pa, pb];
      assert.ok(both[0].worker !== both[1].worker, "pool engages two executors");
      const prePool = await originsOf(ctx);
      for (const post of both) {
        await completeJob(ctx, post);
      }
      await driveToSettled(ctx, { reach: 17 }, prePool);
      const s = await assertCalm(ctx, "pool completion");
      assert.ok(s.origins && s.origins.length > 0, "pool view paints");
      raw.steps.pool = { parts: both.length };
    } finally {
      await ctx.page.close();
    }
  }

  // ---- V-noeng: dead engine ends honest, never loops or hangs ----
  // Worker disabled AND main-thread WASM deleted: every transport is
  // dead. A dispatch must burn at most two bounded attempts, keep the
  // last valid view, clear busy, and never recurse or repost.
  if (want("noeng")) {
    const nb = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const nErrs = [];
    nb.on("console", (m) => {
      if (m.type() === "error") nErrs.push(m.text());
    });
    nb.on("pageerror", (e) => nErrs.push(String(e)));
    nb.on("crash", () => nErrs.push("PAGE-CRASH"));
    await nb.addInitScript({
      content: "(() => { try { window.Worker = undefined; } catch (e) {} })();",
    });
    await nb.goto(pathToFileURL(join(STAGE, "index.html")).href);
    const nctx = { page: nb, errs: nErrs, done: new Set(), seen: new Set() };
    try {
      await nb.uncheck("#yy-show-fields");
      await driveToSettled(nctx, { target: 8, reach: 12 });
      const base = await originsOf(nctx);
      await nb.evaluate(() => {
        try {
          delete window.YYWasmRT;
        } catch (e) {
          window.YYWasmRT = null;
        }
      });
      const startsBefore = await nb.evaluate(() => window.__yyFlightTest.stats().starts);
      await setReachOnce(nctx, 14);
      await nb.waitForFunction(
        () => /Engine unavailable/.test(document.getElementById("yy-explain-note").textContent),
        null,
        { timeout: SETTLE_MS },
      );
      await nb.waitForTimeout(1500);
      const st = await nb.evaluate(() => window.__yyFlightTest.stats());
      assert.ok(
        st.starts - startsBefore <= 2,
        `bounded attempts, no redispatch loop (starts +${st.starts - startsBefore})`,
      );
      assert.equal(st.running, 0, "no running keys leaked");
      const s = await errorState(nctx);
      assert.equal(s.busy, null, "busy cleared on honest error");
      assert.equal(s.origins, base, "last valid view retained");
      assert.ok(!/failed twice/.test(s.note) || /Engine unavailable/.test(s.note), "honest engine error shown");
      assert.ok(
        !nErrs.some((e) => /Maximum call stack|PAGE-CRASH/.test(e)),
        `no recursion crash (${nErrs.join("; ").slice(0, 200)})`,
      );
      raw.steps.noeng = { extraStarts: st.starts - startsBefore };
    } finally {
      await nb.close();
    }
  }

  // ---- V-stalerecover: stale pool recovery wakes the joined view ----
  // Gen A pool job runs; gen B joins every key (no work of its own);
  // the watchdog recovers the superseded logical. The recovery must
  // wake the current view to redispatch instead of hanging it busy.
  if (want("stalerecover")) {
    const ctx = await newPage({ cpus: 8, mem: 8 });
    try {
      await driveToSettled(ctx, { target: 8, reach: 12 });
      await setReachOnce(ctx, 14);
      const pa0 = await nextPost(ctx);
      const pb0 = await nextPost(ctx);
      assert.ok(pa0.worker !== pb0.worker, "pool engages two executors");
      const joins0 = await joins(ctx);
      const DEF = await ctx.page.evaluate(() => document.getElementById("yy-text").value);
      await setText(ctx, DEF);
      await ctx.page.waitForFunction((b) => window.__yyFlightTest.stats().joins > b, joins0, {
        polling: 25,
        timeout: SETTLE_MS,
      });
      assert.equal((await scores(ctx)).length, 2, "join dispatches nothing new");
      await ctx.page.evaluate(() => window.__yyPoolTest.expireWatchdog());
      const preR = await originsOf(ctx);
      const startsBefore = await ctx.page.evaluate(() => window.__yyFlightTest.stats().starts);
      const paintedR = await driveToSettled(ctx, { reach: 14 }, preR);
      assert.ok(paintedR && paintedR.split("|").length === 3, "joined view paints its full set");
      await assertCalm(ctx, "stale-recovery completion");
      const st = await ctx.page.evaluate(() => window.__yyFlightTest.stats());
      assert.ok(st.starts - startsBefore <= 1, "exactly one bounded recovery dispatch");
      assert.equal(st.running, 0, "no running keys leaked");
      const led = await ctx.page.evaluate(() => (window.__yyPoolJobs || []).map((l) => l.outcome));
      assert.ok(
        led.some((o) => /superseded-during-recovery/.test(o || "")),
        `recovery ledger marks the stale handoff (${led.join(",")})`,
      );
      raw.steps.stalerecover = { kept: true };
    } finally {
      await ctx.page.close();
    }
  }

  // ---- V-ackexpiry: silent transport ends honest, never reposts ----
  // A dispatched job goes silent (no checkpoints, no terminal) with a
  // live engine behind it. Repeated native ack-expiry callbacks must
  // end in an honest error after two strikes — never an unbounded
  // redispatch cycle — while keys the current view no longer needs
  // accrue no failure credit.
  if (want("ackexpiry")) {
    const ctx = await newPage({ cpus: 2, mem: 8 });
    try {
      await driveToSettled(ctx, { target: 8, reach: 12 });
      await setReachOnce(ctx, 14);
      const j0 = await nextPost(ctx);
      assert.ok(j0.msg.items.length > 40, "dispatch runs");
      const starts0 = await ctx.page.evaluate(() => window.__yyFlightTest.stats().starts);
      await ctx.page.evaluate(() => window.__yyFlightTest.expireAcks());
      await ctx.page.waitForTimeout(400);
      const s1 = await errorState(ctx);
      assert.equal(s1.busy, "true", "first silence re-arms the wait, no premature error");
      assert.ok(!/unavailable|failed twice/.test(s1.note), "first silence shows no error");
      await ctx.page.evaluate(() => window.__yyFlightTest.expireAcks());
      await ctx.page.waitForFunction(
        () => /failed twice/.test(document.getElementById("yy-explain-note").textContent),
        null,
        { timeout: SETTLE_MS },
      );
      await ctx.page.waitForTimeout(800);
      const st = await ctx.page.evaluate(() => window.__yyFlightTest.stats());
      assert.equal(st.starts, starts0 + 1, "exactly one bounded redispatch, then honest error");
      assert.equal(st.running, 0, "no running keys leaked");
      assert.equal(st.calls, 0, "no live calls leaked");
      const s2 = await errorState(ctx);
      assert.equal(s2.busy, null, "busy cleared on honest error");
      // Trimmed keys accrue nothing: a superseded silent call expires
      // against a view that no longer needs its keys, so a later view
      // re-needing them dispatches fresh instead of tripping a stale
      // strike. E is disjoint from the default set and D alike.
      const E = "gy pb vm wh dx";
      await drainPosts(ctx);
      await setText(ctx, D);
      const jD = await nextPost(ctx);
      assert.deepEqual(
        [...jD.msg.items.map((it) => it.key)].sort(),
        [...uniquePairs(D)].sort(),
        "superseding view dispatches its own pairs",
      );
      await setText(ctx, E);
      const jE = await nextPost(ctx);
      assert.deepEqual(
        [...jE.msg.items.map((it) => it.key)].sort(),
        [...uniquePairs(E)].sort(),
        "disjoint view dispatches fresh, never exhausted",
      );
      await ctx.page.evaluate(() => window.__yyFlightTest.expireAcks());
      await drainPosts(ctx);
      await setText(ctx, D);
      const preD = await originsOf(ctx);
      const paintedD = await driveToSettled(ctx, { reach: 14 }, preD);
      assert.ok(paintedD, "single strike does not exhaust a later view");
      await assertCalm(ctx, "post-expiry restore");
      raw.steps.ackexpiry = { redispatches: st.starts - starts0 };
    } finally {
      await ctx.page.close();
    }
  }

  // ---- V-stalefallback: stale terminal via main thread wakes current ----
  if (want("stalefallback")) {
    const ctx = await newPage({ cpus: 2, mem: 8 });
    try {
      const SHORT = "hello world";
      await driveToSettled(ctx, { target: 8, reach: 12 });
      await setText(ctx, SHORT);
      await driveToSettled(ctx, { reach: 12 });
      await setReachOnce(ctx, 14);
      const j0 = await nextPost(ctx);
      assert.equal(j0.msg.items.length, 8, "short text dispatches its 8 pairs");
      await setText(ctx, SHORT + " qzx");
      const j1sf = await nextPost(ctx);
      assert.deepEqual(
        [...j1sf.msg.items.map((it) => it.key)].sort(),
        ["qz", "zx"],
        "current view dispatches exactly the novel pairs",
      );
      // Stale producer fails over to the real main-thread engine: its
      // validated curves cache under the original identity while the
      // current view stays busy, then the current view paints exactly
      // once with zero new engine calls of its own.
      await deliver(ctx, j0.worker, { kind: "error", jobId: j0.msg.jobId, message: "injected stale worker failure" });
      const preB = await originsOf(ctx);
      const paintedB = await driveToSettled(ctx, { reach: 14 }, preB);
      assert.notEqual(paintedB, preB, "stale fallback completion paints the current view");
      await assertCalm(ctx, "stale-fallback completion");
      assert.equal(
        (await ctx.page.evaluate(() => window.__yyPairCacheTest.mainCalls())).errors,
        0,
        "main-thread fallback clean",
      );
      raw.steps.stalefallback = { kept: true };
    } finally {
      await ctx.page.close();
    }
  }

  // ---- V-fallback: main-thread path completes, restore is zero work ----
  if (want("fallback")) {
    const fb = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const fErrs = [];
    fb.on("console", (m) => {
      if (m.type() === "error") fErrs.push(m.text());
    });
    fb.on("pageerror", (e) => fErrs.push(String(e)));
    await fb.addInitScript({
      content: "(() => { try { window.Worker = undefined; } catch (e) {} })();",
    });
    await fb.goto(pathToFileURL(join(STAGE, "index.html")).href);
    const fctx = { page: fb, errs: fErrs, done: new Set(), seen: new Set() };
    try {
      await fb.uncheck("#yy-show-fields");
      await driveToSettled(fctx, { target: 8, reach: 12 });
      const SHORT = "hello world";
      await setText(fctx, SHORT);
      await driveToSettled(fctx, { reach: 12 });
      const preFb = await originsOf(fctx);
      await setReachOnce(fctx, 14);
      await driveToSettled(fctx, { reach: 14 }, preFb);
      const s = await errorState(fctx);
      assert.ok(s.origins, "fallback paints");
      assert.equal(fErrs.length, 0, "fallback has no errors");
      const mc = await fb.evaluate(() => window.__yyPairCacheTest.mainCalls());
      assert.equal(mc.errors, 0, "main-thread engine clean");
      assert.equal(mc.calls, mc.returns, "every main-thread call returned");
      const c0 = mc.calls;
      await setText(fctx, SHORT);
      await driveToSettled(fctx, { reach: 14 });
      assert.equal(
        (await fb.evaluate(() => window.__yyPairCacheTest.mainCalls())).calls,
        c0,
        "fallback restore is zero work",
      );
      raw.steps.fallback = { mainCalls: c0 };
    } finally {
      await fb.close();
    }
  }
} finally {
  await browser.close();
}

const outPath = process.argv.includes("--out")
  ? process.argv[process.argv.indexOf("--out") + 1]
  : resolve(
      repo,
      "out/diagnostics/contextual-spacing/yinyang-update-performance/wave3/view-completion-fix/raw-viewcompletion.json",
    );
writeFileSync(outPath, JSON.stringify(raw, null, 2) + "\n");
console.log("viewcompletion: all selected gates passed");
