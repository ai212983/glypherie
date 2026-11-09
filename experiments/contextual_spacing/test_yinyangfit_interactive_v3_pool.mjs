// Pool-hardening regression gate: two-worker score pool on the candidate
// stage vs the adopted single-worker C2 baseline behavior.
//
// Suites:
//   node test_yinyangfit_interactive_v3_pool.mjs <stageDir> --suite=light
//     Functional gates on short/novel texts: admission, cancel, hidden
//     fields, zero-work controls, injected failures with exact recovery.
//   node test_yinyangfit_interactive_v3_pool.mjs <stageDir> --suite=heavy
//     Full default-text uncached R13: 1 warmup + 2 alternating reps per
//     config (pool vs single-worker baseline page), exact merged results,
//     pixels, memory peaks, aux retirement. Run under the shared fcntl
//     lock (lockrun_heavy.py); closes its browsers; no polling.
//   Either suite also accepts --baseline <dir> (default: adopted C2
//   site-reviewed) and --out <raw.json>.
//
// Offline file:// only, no HTTP. No minutes-scale corpus rescoring.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { resolve, dirname } from "node:path";
import { writeFileSync } from "node:fs";
import { pathToFileURL, fileURLToPath } from "node:url";

const require = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const { chromium } = require("playwright-core");
const root = dirname(fileURLToPath(import.meta.url));
const repo = resolve(root, "../..");

const NOVEL = "abcdefg hijklmn opqrstu vwxyz 0123456789";
const SHORT = "hello world";

function sha(s) {
  return createHash("sha256").update(s).digest("hex");
}

function hwScript(cpus, memGB) {
  // Deterministic hardware identity before page scripts run. "missing"
  // is spelled as an undefined return, matching absent platform data.
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

function spyScript(opts = {}) {
  // Read-only worker census: construction count, post kinds/sizes, and
  // inbound score metadata. Never alters payloads except when the
  // corrupt flag is set for the malformed-partition gate.
  return `(() => {
    window.__yyT = { workers: [], posts: [], inbound: [], captured: {} };
    // Armed from page start: the L13 page runs exactly one pool
    // generation (R12 default is cached), so arming is unambiguous.
    window.__yyCorruptAuxDone = ${opts.corruptAuxDone ? "{armed:true,used:false}" : "null"};
    window.__yyFailSecondWorker = ${opts.failSecondWorker ? "true" : "false"};
    window.__yyNoWorker = ${opts.noWorker ? "true" : "false"};
    if (window.__yyNoWorker) {
      try { window.Worker = undefined; } catch (e) {}
      return;
    }
    const OrigWorker = window.Worker;
    if (!OrigWorker) return;
    function TWorker(url, opts) {
      const idx = window.__yyT.workers.length;
      if (window.__yyFailSecondWorker && idx >= 1) {
        throw new Error("yytest-no-aux");
      }
      const w = new OrigWorker(url, opts);
      window.__yyT.workers.push(w);
      // Wrap the production onmessage handler after assignment through
      // the real IDL setter (never shadow it: a shadow would swallow
      // delivery). Polls briefly; score traffic arrives seconds later.
      const arm = setInterval(() => {
        try {
          const cur = w.onmessage;
          if (typeof cur === "function" && !cur.__yyWrapped) {
            const wrapped = function (e) {
              let data = e.data;
              try {
                window.__yyT.inbound.push({ worker: idx,
                  kind: data && data.kind, jobId: data && data.jobId,
                  linear: data && data.wasmLinearBytes,
                  done: data && data.done, total: data && data.total,
                  nKeys: data && data.results ? Object.keys(data.results).length : undefined });
              } catch (ignore) {}
              if (window.__yyCorruptAuxDone && window.__yyCorruptAuxDone.armed &&
                  !window.__yyCorruptAuxDone.used && idx === 1 &&
                  data && data.kind === "done" && data.results) {
                window.__yyCorruptAuxDone.used = true;
                const keys = Object.keys(data.results);
                const cut = {};
                keys.slice(0, Math.floor(keys.length / 2)).forEach((k) => { cut[k] = data.results[k]; });
                data = Object.assign({}, data, { results: cut });
              }
              try {
                if (data && data.kind === "done" && data.results) {
                  window.__yyT.captured[data.jobId] = JSON.parse(JSON.stringify(data.results));
                }
              } catch (ignore) {}
              return cur.call(w, { data });
            };
            wrapped.__yyWrapped = true;
            w.onmessage = wrapped;
            clearInterval(arm);
          }
        } catch (ignore) {}
      }, 50);
      setTimeout(() => clearInterval(arm), 30000);
      const origPost = w.postMessage.bind(w);
      w.postMessage = (msg, ...rest) => {
        try {
          window.__yyT.posts.push({ worker: idx, kind: msg && msg.kind,
            jobId: msg && msg.jobId,
            nItems: msg && msg.items ? msg.items.length : undefined });
        } catch (ignore) {}
        return origPost(msg, ...rest);
      };
      return w;
    }
    TWorker.prototype = OrigWorker.prototype;
    window.Worker = TWorker;
  })();`;
}

async function newPage(browser, site, opts = {}) {
  // Explicit undefined means "platform data missing", so defaults apply
  // only when the key is absent.
  const cpus = "cpus" in opts ? opts.cpus : 8;
  const memGB = "memGB" in opts ? opts.memGB : 8;
  const spy = opts.spy || {};
  const viewport = opts.viewport || null;
  const page = await browser.newPage(viewport ? { viewport } : { viewport: { width: 1280, height: 800 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String((e && e.message) || e)));
  await page.addInitScript({ content: hwScript(cpus, memGB) });
  await page.addInitScript({ content: spyScript(spy) });
  await page.goto(pathToFileURL(resolve(site, "index.html")).href);
  await page.waitForFunction(() => window.YY_TABLES && window.YY_TABLES["roboto-16-mono"], undefined, {
    timeout: 30000,
  });
  return { page, errors };
}

async function waitFieldsSettled(page, want, timeout = 180000) {
  await page.waitForFunction(
    () => {
      const busy = document.getElementById("yy-explain-field").hasAttribute("aria-busy");
      const note = document.getElementById("yy-explain-note").textContent;
      const s = window.YY_SUMMARY;
      return (
        !busy &&
        note !== "Updating fields…" &&
        note !== "Updating spacing…" &&
        document.getElementById("yy-sample-note").textContent !== "Updating spacing…" &&
        !!(s && s.coupling !== undefined)
      );
    },
    undefined,
    { timeout },
  );
  if (want) {
    await page.waitForFunction(
      (w) => {
        const s = window.YY_SUMMARY;
        return s && Object.keys(w).every((k) => s[k] === w[k]);
      },
      want,
      { timeout },
    );
  }
}

async function setNumeric(page, sel, value) {
  await page.locator(sel).fill(String(value));
  await page.locator(sel).dispatchEvent("change");
}

async function setText(page, text) {
  await page.locator("#yy-text").fill(text);
  // Text applies on a 250 ms debounce; let that render settle before the
  // next control move so score-post counts stay deterministic.
  await page.waitForTimeout(600);
}

async function summary(page) {
  return page.evaluate(() => window.YY_SUMMARY || null);
}

async function poolInfo(page) {
  return page.evaluate(() => ({
    pool: window.__yyPool || null,
    jobs: window.__yyPoolJobs || [],
    test: window.__yyPoolTest ? !!window.__yyPoolTest.expireWatchdog : false,
  }));
}

async function spyState(page) {
  return page.evaluate(() => ({
    workers: window.__yyT ? window.__yyT.workers.length : -1,
    posts: window.__yyT ? window.__yyT.posts : null,
    inbound: window.__yyT ? window.__yyT.inbound : null,
    captured: window.__yyT ? window.__yyT.captured : null,
  }));
}

function scorePosts(posts) {
  return (posts || []).filter((p) => p.kind === "score");
}

async function canvasSha(page, sel) {
  const url = await page.locator(sel).evaluate((c) => c.toDataURL());
  return sha(url);
}

function pairLines(coupling) {
  // Per-pair diagnostic lines sit below the two header lines.
  return (coupling || []).slice(2);
}

function distinctPairs(text) {
  const set = new Set();
  for (const line of text.split("\n")) {
    for (let i = 0; i + 1 < line.length; i++) {
      const a = line[i],
        b = line[i + 1];
      if (a === " " || b === " ") continue;
      set.add(a + b);
    }
  }
  return set;
}

const results = [];
let onlyFilter = null;
async function gate(name, fn) {
  if (onlyFilter && !onlyFilter.includes(name.split(" ")[0])) {
    console.log(`SKIP ${name}`);
    return;
  }
  try {
    await fn();
    results.push([name, "PASS"]);
    console.log(`PASS ${name}`);
  } catch (e) {
    results.push([name, "FAIL", String((e && e.message) || e)]);
    console.log(`FAIL ${name}: ${(e && e.message) || e}`);
  }
}

async function lightSuite(browser, site, raw) {
  assert.ok(
    distinctPairs(NOVEL).size >= 16,
    `novel fixture has >=16 distinct pairs (got ${distinctPairs(NOVEL).size})`,
  );
  assert.ok(distinctPairs(SHORT).size < 16, "short fixture stays below pool size");

  await gate("L1 default load: zero score, aux never created", async () => {
    const { page, errors } = await newPage(browser, site);
    try {
      await waitFieldsSettled(page, { reach: 12 });
      const s = await summary(page);
      assert.equal(s.scoreCalls, 0);
      assert.equal(s.pairLayers, 94);
      const st = await spyState(page);
      assert.equal(st.workers, 1, "primary worker only");
      const pi = await poolInfo(page);
      assert.equal(pi.pool.auxLive, false);
      assert.equal(pi.pool.lastDecision, null);
      assert.equal(pi.jobs.length, 0);
      assert.deepEqual(errors, []);
      raw.l1 = { scoreCalls: s.scoreCalls, pairLayers: s.pairLayers };
    } finally {
      await page.close();
    }
  });

  await gate("L2 gray + 390px: no overflow, zero errors", async () => {
    const { page, errors } = await newPage(browser, site, { viewport: { width: 390, height: 700 } });
    try {
      await waitFieldsSettled(page, { reach: 12 });
      let over = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
      assert.ok(over, "mono 390px no overflow");
      await page.locator('input[name="profile"][value="gray"]').check();
      await waitFieldsSettled(page, { profile: "gray" });
      over = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
      assert.ok(over, "gray 390px no overflow (line scroll retained clean)");
      assert.deepEqual(errors, []);
    } finally {
      await page.close();
    }
  });

  await gate("L3 cached target/opacity/zoom: zero new score jobs", async () => {
    const { page, errors } = await newPage(browser, site);
    try {
      await waitFieldsSettled(page, { reach: 12 });
      const before = (await spyState(page)).posts.length;
      await setNumeric(page, "#yy-spacing-n", "8.5");
      await waitFieldsSettled(page, { target: 8.5 });
      // The layered heatmap removed the palette text entry; the
      // opacity slider is the surviving cached display control.
      await page.locator("#yy-letter-alpha").fill("40");
      for (const z of ["2", "4", "1"]) {
        await page.locator("#yy-zoom").selectOption(z);
      }
      await waitFieldsSettled(page, { reach: 12, target: 8.5 });
      const st = await spyState(page);
      assert.equal(
        scorePosts(st.posts).length,
        scorePosts(st.posts.slice(0, before)).length,
        "no new score jobs from cached controls",
      );
      assert.equal(st.workers, 1, "aux never created just for display");
      assert.deepEqual(errors, []);
      raw.l3 = { posts: st.posts.length };
    } finally {
      await page.close();
    }
  });

  await gate("L4 small job stays single (small-job)", async () => {
    const { page, errors } = await newPage(browser, site);
    try {
      await waitFieldsSettled(page, { reach: 12 });
      await setText(page, SHORT);
      await setNumeric(page, "#yy-reach-n", "13");
      await waitFieldsSettled(page, { reach: 13 });
      const pi = await poolInfo(page);
      assert.equal(pi.pool.lastDecision.admitted, false);
      assert.equal(pi.pool.lastDecision.reason, "small-job");
      const st = await spyState(page);
      assert.equal(st.workers, 1);
      // Uncached short text scores once per geometry (R12 then R13).
      assert.equal(scorePosts(st.posts).length, 2);
      assert.deepEqual(errors, []);
    } finally {
      await page.close();
    }
  });

  // Single-worker R13 baseline over the novel fixture; later recovery
  // gates compare exact origins/coupling against this record.
  await gate("L5 cpu-low forces single; baseline record", async () => {
    const { page, errors } = await newPage(browser, site, { cpus: 2, memGB: 8 });
    try {
      await waitFieldsSettled(page, { reach: 12 });
      await setText(page, NOVEL);
      await setNumeric(page, "#yy-reach-n", "13");
      await waitFieldsSettled(page, { reach: 13 });
      const s = await summary(page);
      const pi = await poolInfo(page);
      assert.equal(pi.pool.lastDecision.reason, "cpu-low");
      const st = await spyState(page);
      assert.equal(st.workers, 1);
      // Uncached novel text scores once per geometry (R12 then R13).
      assert.equal(scorePosts(st.posts).length, 2);
      raw.l5 = { origins: s.origins, pairs: pairLines(s.coupling), ink: await canvasSha(page, "#yy-adjusted") };
      assert.deepEqual(errors, []);
    } finally {
      await page.close();
    }
  });

  await gate("L6 missing memory info stays single", async () => {
    const { page, errors } = await newPage(browser, site, { cpus: 8, memGB: undefined });
    try {
      await waitFieldsSettled(page, { reach: 12 });
      await setText(page, NOVEL);
      await setNumeric(page, "#yy-reach-n", "13");
      await waitFieldsSettled(page, { reach: 13 });
      const pi = await poolInfo(page);
      assert.equal(pi.pool.lastDecision.admitted, false);
      assert.equal(pi.pool.lastDecision.reason, "memory-unknown");
      const st = await spyState(page);
      assert.equal(st.workers, 1);
      const s = await summary(page);
      assert.deepEqual(s.origins, raw.l5.origins, "same geometry either path");
      assert.deepEqual(errors, []);
    } finally {
      await page.close();
    }
  });

  await gate("L7 large estimate stays single (over-budget)", async () => {
    const { page, errors } = await newPage(browser, site, { cpus: 8, memGB: 8 });
    try {
      await waitFieldsSettled(page, { reach: 12 });
      await setNumeric(page, "#yy-reach-n", "24");
      await waitFieldsSettled(page, { reach: 24 }, 420000);
      const pi = await poolInfo(page);
      assert.equal(pi.pool.lastDecision.admitted, false);
      assert.equal(pi.pool.lastDecision.reason, "over-budget");
      const st = await spyState(page);
      assert.equal(st.workers, 1);
      assert.deepEqual(errors, []);
      raw.l7 = { decision: pi.pool.lastDecision };
    } finally {
      await page.close();
    }
  });

  await gate("L8 rapid R13->R14->R12 cancels pool, latest exact", async () => {
    const { page, errors } = await newPage(browser, site);
    try {
      await waitFieldsSettled(page, { reach: 12 });
      await setText(page, NOVEL);
      await setNumeric(page, "#yy-reach-n", "13");
      await page.waitForTimeout(1500);
      await setNumeric(page, "#yy-reach-n", "14");
      await page.waitForTimeout(800);
      await setNumeric(page, "#yy-reach-n", "12");
      await waitFieldsSettled(page, { reach: 12 });
      const s = await summary(page);
      assert.equal(s.reach, 12);
      const busy = await page.evaluate(() => document.getElementById("yy-explain-field").hasAttribute("aria-busy"));
      assert.equal(busy, false, "latest generation busy clear");
      const pi = await poolInfo(page);
      // Supersede retires via trim-drain (settled/trimmed-idle): the
      // abort path that ledgered status "cancelled"
      // (cancelActivePoolJobs) has no callers in current source, and
      // both P3 and P4 wirings retire rapid supersedes as trimmed-idle
      // with zero completions. Either vocabulary proves the same
      // requirement: superseded work never completes or paints.
      const cancelled = pi.jobs.filter((j) => j.status === "cancelled");
      const trimmedIdle = pi.jobs.filter(
        (j) => j.status === "settled" && (j.outcome === "trimmed-idle" || j.outcome === "superseded"),
      );
      assert.ok(cancelled.length + trimmedIdle.length >= 1, "superseded pool jobs cancelled");
      const completed = pi.jobs.filter(
        (j) => j.status === "settled" && (j.outcome === "completed" || j.outcome === "completed-over-target"),
      );
      assert.ok(completed.length <= 1, "at most one pool completion");
      assert.equal(pi.pool.auxLive, false, "aux retired after supersede");
      assert.deepEqual(errors, []);
      raw.l8 = { cancelled: cancelled.length, trimmedIdle: trimmedIdle.length, completed: completed.length };
    } finally {
      await page.close();
    }
  });

  await gate("L9 hidden fields score exact with zero field posts", async () => {
    const { page, errors } = await newPage(browser, site);
    try {
      await waitFieldsSettled(page, { reach: 12 });
      const fieldsBefore = ((await spyState(page)).posts || []).filter((p) => p.kind === "fields").length;
      await page.locator("#yy-show-fields").uncheck();
      await setText(page, NOVEL);
      await setNumeric(page, "#yy-reach-n", "13");
      // Hidden paint carries ink without a field coupling: wait on the
      // score note and placed origins instead of the field summary.
      await page.waitForFunction(
        () => {
          const s = window.YY_SUMMARY;
          return (
            document.getElementById("yy-sample-note").textContent !== "Updating spacing…" &&
            !!(s && s.origins && s.reach === 13)
          );
        },
        undefined,
        { timeout: 180000 },
      );
      const s = await summary(page);
      assert.deepEqual(s.origins, raw.l5.origins, "hidden scores exact");
      const st = await spyState(page);
      const fields = (st.posts || []).filter((p) => p.kind === "fields");
      assert.equal(fields.length, fieldsBefore, "no new field posts while hidden");
      await page.locator("#yy-show-fields").check();
      await waitFieldsSettled(page, { reach: 13 });
      const st2 = await spyState(page);
      assert.ok((st2.posts || []).filter((p) => p.kind === "fields").length >= 1, "reshow computes missing fields");
      assert.deepEqual(errors, []);
    } finally {
      await page.close();
    }
  });

  await gate("L10 target during inflight: one completion, same geometry", async () => {
    const { page, errors } = await newPage(browser, site);
    try {
      await waitFieldsSettled(page, { reach: 12 });
      await setText(page, NOVEL);
      await setNumeric(page, "#yy-reach-n", "13");
      await page.waitForTimeout(1500);
      await setNumeric(page, "#yy-spacing-n", "8.2");
      await waitFieldsSettled(page, { reach: 13, target: 8.2 });
      const s = await summary(page);
      assert.equal(s.reach, 13);
      const pi = await poolInfo(page);
      const completed = pi.jobs.filter(
        (j) => j.status === "settled" && String(j.outcome || "").startsWith("completed"),
      );
      assert.ok(completed.length <= 1, "no duplicate full completion");
      assert.deepEqual(errors, []);
      raw.l10 = { completed: completed.length };
    } finally {
      await page.close();
    }
  });

  // Default-text R13 pool job: the full 78-pair uncached workload stays
  // in flight for tens of seconds, giving fault injection a stable
  // window. R12 default answers from tables, so exactly one pool
  // generation exists on the page.
  async function startPoolJob(page) {
    await setNumeric(page, "#yy-reach-n", "13");
    await page.waitForFunction(
      () => {
        const posts = window.__yyT ? window.__yyT.posts : [];
        return (
          window.__yyPool && window.__yyPool.auxLive === true && posts.filter((p) => p.kind === "score").length >= 2
        );
      },
      undefined,
      { timeout: 60000 },
    );
  }

  // Default-text R13 single baseline; fault gates compare exact
  // origins/coupling against this record.
  await gate("L5b cpu-low default single; baseline record", async () => {
    const { page, errors } = await newPage(browser, site, { cpus: 2, memGB: 8 });
    try {
      await waitFieldsSettled(page, { reach: 12 });
      await setNumeric(page, "#yy-reach-n", "13");
      await waitFieldsSettled(page, { reach: 13 }, 420000);
      const s = await summary(page);
      raw.l5b = { origins: s.origins, pairs: pairLines(s.coupling), ink: await canvasSha(page, "#yy-adjusted") };
      assert.deepEqual(errors, []);
    } finally {
      await page.close();
    }
  });

  await gate("L11 silent aux death: watchdog-gated exact recovery", async () => {
    const { page, errors } = await newPage(browser, site);
    try {
      await waitFieldsSettled(page, { reach: 12 });
      await startPoolJob(page);
      await page.evaluate(() => {
        window.__yyT.workers[1].terminate();
      });
      await page.waitForTimeout(3000);
      let pi = await poolInfo(page);
      let live = pi.jobs.filter((j) => j.status === "pending");
      assert.ok(live.length >= 1, "no premature fallback before watchdog");
      const postsBefore = (await spyState(page)).posts.length;
      await page.evaluate(() => window.__yyPoolTest.expireWatchdog());
      await waitFieldsSettled(page, { reach: 13 });
      const s = await summary(page);
      assert.deepEqual(s.origins, raw.l5b.origins, "recovered origins exact");
      assert.deepEqual(pairLines(s.coupling), raw.l5b.pairs, "recovered pairs exact");
      pi = await poolInfo(page);
      assert.ok(pi.pool.disabled !== null, "pool disabled after fault");
      const outcomes = pi.jobs.map((j) => j.outcome);
      assert.ok(
        outcomes.some((o) => String(o).startsWith("retrying:")),
        `retry recorded separately (${outcomes.join(",")})`,
      );
      const st = await spyState(page);
      assert.ok(st.posts.length > postsBefore, "retry reposted work");
      assert.equal(pi.pool.auxLive, false, "aux retired");
      assert.deepEqual(errors, []);
      raw.l11 = { outcomes };
    } finally {
      await page.close();
    }
  });

  await gate("L12 injected aux error: immediate exact recovery", async () => {
    const { page, errors } = await newPage(browser, site);
    try {
      await waitFieldsSettled(page, { reach: 12 });
      await startPoolJob(page);
      // Genuine worker-side throw: a score job with no items crashes the
      // aux chunk outside any try, raising a trusted worker error event.
      await page.evaluate(() => {
        window.__yyT.workers[1].postMessage({
          kind: "score",
          jobId: "yytest-boom",
          dataset: "d",
          captureSha: "c",
          items: null,
          params: { q: 2, radius: 13 },
        });
      });
      await waitFieldsSettled(page, { reach: 13 });
      const s = await summary(page);
      assert.deepEqual(s.origins, raw.l5b.origins, "recovered origins exact");
      const pi = await poolInfo(page);
      assert.ok(
        String(pi.pool.disabled || "").includes("aux-error"),
        `disabled reason names aux-error (got ${pi.pool.disabled})`,
      );
      assert.deepEqual(errors, []);
    } finally {
      await page.close();
    }
  });

  await gate("L13 malformed partition: no partial paint, exact after retry", async () => {
    const { page, errors } = await newPage(browser, site, { spy: { corruptAuxDone: true } });
    try {
      await waitFieldsSettled(page, { reach: 12 });
      await startPoolJob(page);
      await waitFieldsSettled(page, { reach: 13 }, 420000);
      const s = await summary(page);
      assert.deepEqual(s.origins, raw.l5b.origins, "full set exact after retry");
      const pi = await poolInfo(page);
      const completed = pi.jobs.filter(
        (j) => j.status === "settled" && String(j.outcome || "").startsWith("completed"),
      );
      assert.ok(completed.length <= 1, "no partial completion painted");
      assert.ok(
        pi.jobs.some((j) => String(j.outcome || "").startsWith("retrying:malformed-b")),
        `malformed side retried (${pi.jobs.map((j) => j.outcome).join(",")})`,
      );
      assert.deepEqual(errors, []);
    } finally {
      await page.close();
    }
  });

  await gate("L14 primary failure: main-thread full retry exact", async () => {
    const { page, errors } = await newPage(browser, site);
    try {
      await waitFieldsSettled(page, { reach: 12 });
      await startPoolJob(page);
      await page.evaluate(() => {
        window.__yyT.workers[0].dispatchEvent(new ErrorEvent("error", { message: "yytest primary boom" }));
      });
      // Main-thread full retry is slower than the worker path.
      await waitFieldsSettled(page, { reach: 13 }, 420000);
      const s = await summary(page);
      assert.deepEqual(s.origins, raw.l5b.origins, "retried origins exact");
      const pi = await poolInfo(page);
      assert.ok(
        String(pi.pool.disabled || "").includes("primary-terminated"),
        `disabled names primary (${pi.pool.disabled})`,
      );
      assert.deepEqual(errors, []);
    } finally {
      await page.close();
    }
  });

  await gate("L15 recovery failure: honest error, last view, no loop", async () => {
    const { page, errors } = await newPage(browser, site);
    try {
      await waitFieldsSettled(page, { reach: 12 });
      await startPoolJob(page);
      await page.evaluate(() => {
        window.__yyT.workers[1].terminate();
        window.__yyT.workers[0].terminate();
        try {
          delete window.YYWasmRT;
        } catch (e) {
          window.YYWasmRT = null;
        }
      });
      await page.evaluate(() => window.__yyPoolTest.expireWatchdog());
      await page.waitForTimeout(2000);
      await page.evaluate(() => window.__yyPoolTest.expireRetry());
      await page.waitForFunction(
        () => {
          const t = document.getElementById("yy-sample-note").textContent;
          return t.indexOf("Engine unavailable") >= 0 || t.indexOf("pool retry incomplete") >= 0;
        },
        undefined,
        { timeout: 120000 },
      );
      const busy = await page.evaluate(() => document.getElementById("yy-explain-field").hasAttribute("aria-busy"));
      assert.equal(busy, false, "busy clear on honest error");
      const postsBefore = (await spyState(page)).posts.length;
      await page.waitForTimeout(3000);
      const postsAfter = (await spyState(page)).posts.length;
      assert.equal(postsAfter, postsBefore, "no resolve loop");
      const note = await page.locator("#yy-sample-note").textContent();
      assert.ok(/Engine unavailable|pool retry incomplete/.test(note));
      raw.l15 = { note };
    } finally {
      await page.close();
    }
  });

  await gate("L16 worker disabled: existing fallback unchanged", async () => {
    const { page, errors } = await newPage(browser, site, { spy: { noWorker: true } });
    try {
      await waitFieldsSettled(page, { reach: 12 });
      await setText(page, NOVEL);
      await setNumeric(page, "#yy-reach-n", "13");
      await waitFieldsSettled(page, { reach: 13 }, 240000);
      const s = await summary(page);
      assert.deepEqual(s.origins, raw.l5.origins, "fallback origins exact");
      const pi = await poolInfo(page);
      assert.ok(pi.pool === null || pi.pool.lastDecision === null, "pool never engaged");
      const st = await spyState(page);
      assert.equal(st.workers, 0, "no workers constructed");
      assert.deepEqual(errors, []);
    } finally {
      await page.close();
    }
  });

  await gate("L17 aux spawn failure: single fallback exact", async () => {
    const { page, errors } = await newPage(browser, site, { spy: { failSecondWorker: true } });
    try {
      await waitFieldsSettled(page, { reach: 12 });
      await setText(page, NOVEL);
      await setNumeric(page, "#yy-reach-n", "13");
      await waitFieldsSettled(page, { reach: 13 });
      const s = await summary(page);
      assert.deepEqual(s.origins, raw.l5.origins, "fallback origins exact");
      const pi = await poolInfo(page);
      assert.equal(pi.pool.lastDecision.reason, "aux-spawn-failed");
      assert.deepEqual(errors, []);
    } finally {
      await page.close();
    }
  });
}

function mergeDigest(captured, order) {
  const merged = {};
  for (const [jobId, res] of Object.entries(captured || {})) {
    for (const [k, v] of Object.entries(res)) {
      if (!(k in merged)) merged[k] = v;
    }
  }
  const keys = order || Object.keys(merged).sort();
  let steps = 0;
  for (const k of keys) {
    const r = merged[k];
    if (r && Array.isArray(r.steps)) steps += r.steps.length;
  }
  return { digest: sha(JSON.stringify(keys.map((k) => [k, merged[k] ?? null]))), steps, pairs: keys.length };
}

async function heavyRep(browser, site, config, raw) {
  // Fresh page per rep: cold engine init, default tables, then the real
  // uncached R13 full-preview score job plus its field completion.
  const { page, errors } = await newPage(browser, site, { cpus: 8, memGB: 4 });
  try {
    await waitFieldsSettled(page, { reach: 12 });
    const t0 = Date.now();
    await setNumeric(page, "#yy-reach-n", "13");
    await page.waitForFunction(
      () => document.getElementById("yy-sample-note").textContent !== "Updating spacing…",
      undefined,
      { timeout: 420000 },
    );
    const tInk = Date.now() - t0;
    await waitFieldsSettled(page, { reach: 13 }, 420000);
    const tWall = Date.now() - t0;
    const s = await summary(page);
    const pi = await poolInfo(page);
    const st = await spyState(page);
    const batch = await page.evaluate(() => window.__yyLastBatch || null);
    const scoreMsgs = scorePosts(st.posts);
    // Sorted-key merge digest: both configs share the key order, so any
    // value difference changes the digest.
    const { digest, steps, pairs } = mergeDigest(st.captured, null);
    let peak0 = 0,
      peak1 = 0;
    for (const m of st.inbound || []) {
      if (typeof m.linear === "number") {
        if (m.worker === 0) peak0 = Math.max(peak0, m.linear);
        if (m.worker === 1) peak1 = Math.max(peak1, m.linear);
      }
    }
    const rep = {
      config,
      scoreMs: tInk,
      wallMs: tWall,
      scoreCalls: s.scoreCalls,
      pairs,
      steps,
      digest,
      occurrences: batch ? batch.occurrences : null,
      pairLayers: s.pairLayers,
      originsSha: sha(JSON.stringify(s.origins)),
      pairsSha: sha(JSON.stringify(pairLines(s.coupling))),
      inkSha: await canvasSha(page, "#yy-adjusted"),
      origSha: await canvasSha(page, "#yy-original"),
      fieldSha: await canvasSha(page, "#yy-explain-field"),
      peakPrimary: peak0,
      peakAux: peak1,
      combinedLinear: peak0 + peak1,
      ledger: pi.jobs,
      decision: pi.pool ? pi.pool.lastDecision : null,
      highwater: pi.pool ? pi.pool.highwater : null,
      auxLive: pi.pool ? pi.pool.auxLive : null,
      scorePosts: scoreMsgs.length,
      errors,
    };
    return rep;
  } finally {
    await page.close();
  }
}

async function heavySuite(browser, stage, baseline, raw) {
  const cfgs = ["pool-warmup", "single-warmup", "pool", "single", "single", "pool"];
  const reps = [];
  for (const cfg of cfgs) {
    const site = cfg.startsWith("pool") ? stage : baseline;
    console.log(`heavy rep: ${cfg} on ${cfg.startsWith("pool") ? "stage" : "baseline"}`);
    const rep = await heavyRep(browser, site, cfg, raw);
    console.log(
      `  wall=${rep.wallMs} score=${rep.scoreMs} steps=${rep.steps} ` +
        `pairs=${rep.pairs} layers=${rep.pairLayers} ` +
        `linear=${rep.peakPrimary}+${rep.peakAux} errors=${rep.errors.length}`,
    );
    reps.push(rep);
  }
  raw.reps = reps;
  const measured = reps.filter((r) => !r.config.endsWith("warmup"));
  await gate("H1 exact single vs pool (records/choices/maps/pixels)", async () => {
    const digests = new Set(measured.map((r) => r.digest));
    assert.equal(digests.size, 1, "identical merged score results");
    for (const r of measured) {
      assert.equal(r.steps, 4350, `4350 result steps (${r.config})`);
      assert.equal(r.pairs, 78, `78 scored pairs (${r.config})`);
      assert.equal(r.occurrences, 94, `94 placed occurrences (${r.config})`);
      assert.equal(r.pairLayers, 94, `94 field layers (${r.config})`);
      assert.equal(r.scoreCalls, 78, `78 score calls (${r.config})`);
      assert.deepEqual(r.errors, [], `zero errors (${r.config})`);
    }
    for (const key of ["originsSha", "pairsSha", "inkSha", "origSha", "fieldSha"]) {
      const set = new Set(measured.map((r) => r[key]));
      assert.equal(set.size, 1, `identical ${key}`);
    }
  });
  await gate("H2 pool engaged with bounded memory, aux retired", async () => {
    for (const r of measured.filter((x) => x.config === "pool")) {
      assert.ok(r.decision && r.decision.admitted, `pool admitted (${r.decision && r.decision.reason})`);
      assert.ok(r.combinedLinear <= 512 * 1024 * 1024, `combined linear under target (got ${r.combinedLinear})`);
      assert.equal(r.auxLive, false, "aux retired after complete");
      assert.ok(r.peakAux > 0, "aux actually scored");
    }
    for (const r of measured.filter((x) => x.config === "single")) {
      assert.equal(r.peakAux, 0, "baseline never spawns aux");
    }
  });
  raw.medians = {};
  for (const cfg of ["pool", "single"]) {
    const rs = measured
      .filter((r) => r.config === cfg)
      .map((r) => r.wallMs)
      .sort((a, b) => a - b);
    raw.medians[cfg] = rs;
  }
}

async function main() {
  const args = process.argv.slice(2);
  const suite = (args.find((a) => a.startsWith("--suite=")) || "--suite=light").slice(8);
  const site = resolve(
    args.find((a) => !a.startsWith("--")) ||
      "out/diagnostics/contextual-spacing/yinyang-update-performance/wave2/pool-implementation/stage",
  );
  const baselineArg = args.find((a) => a.startsWith("--baseline="));
  const baseline = resolve(
    baselineArg ? baselineArg.slice(11) : "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/site-reviewed",
  );
  const outArg = args.find((a) => a.startsWith("--out="));
  const out = outArg
    ? resolve(outArg.slice(6))
    : resolve(
        repo,
        "out/diagnostics/contextual-spacing/yinyang-update-performance/wave2/pool-implementation/raw-pool-" +
          suite +
          ".json",
      );
  const onlyArg = args.find((a) => a.startsWith("--only="));
  if (onlyArg) onlyFilter = onlyArg.slice(7).split(",");
  const raw = { suite, site, baseline, started: new Date().toISOString(), reps: [] };
  const browser = await chromium.launch({ headless: true });
  try {
    if (suite === "light") await lightSuite(browser, site, raw);
    else if (suite === "heavy") await heavySuite(browser, site, baseline, raw);
    else throw new Error("unknown suite: " + suite);
  } finally {
    raw.ended = new Date().toISOString();
    writeFileSync(out, JSON.stringify(raw, null, 1) + "\n");
    console.log(`wrote ${out}`);
    await browser.close();
  }
  const fails = results.filter((r) => r[1] !== "PASS");
  console.log(`${results.length - fails.length}/${results.length} gates passed`);
  if (fails.length) {
    for (const f of fails) console.log(`FAILED ${f[0]}: ${f[2] || ""}`);
    process.exit(1);
  }
}

await main();
