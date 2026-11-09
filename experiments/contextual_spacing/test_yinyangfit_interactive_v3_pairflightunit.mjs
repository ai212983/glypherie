// Pair-flight unit gate (node only, no browser): the frozen O1 reuse
// oracle (18 traces) run against the real production flight registry
// and pair cache; adversarial registry events; and a worker-VM harness
// proving the reported engine counters match independent boundary
// counts.
//
// Steps and expectations come from the frozen fixtures module itself
// (reuse_fixtures.mjs, predating P2): nothing is transcribed, nothing
// frozen is mutated. Fixture call ids (c1, c2, ...) are positional in
// creation order across need-starts, fail-retries and ack continuations;
// the wrapper maps them onto production call ids in the same order. An
// ack that would implicitly continue still-subscribed keys has no
// production counterpart (production releases on ack; redispatch waits
// for it), so the wrapper fails loudly there instead of guessing: none
// of the 18 frozen traces hit that shape.
//
// Usage: node test_yinyangfit_interactive_v3_pairflightunit.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import vm from "node:vm";

const root = dirname(fileURLToPath(import.meta.url));
const ORACLE = resolve(root, "../../out/diagnostics/contextual-spacing/yinyang-update-performance/wave3/reuse-oracle");

function loadBlock(name) {
  const src = readFileSync(resolve(root, "yinyangfit_interactive_v3_wiring.js"), "utf8");
  const begin = `/* __${name}_BEGIN__ */`;
  const end = `/* __${name}_END__ */`;
  const a = src.indexOf(begin),
    b = src.indexOf(end);
  assert.ok(a >= 0 && b > a, name + " block markers present");
  const ctx = {};
  vm.createContext(ctx);
  vm.runInContext(src.slice(a, b + end.length), ctx, { filename: name });
  return ctx;
}

const P = loadBlock("PAIRCACHE_HELPERS");
const F = loadBlock("FLIGHT_HELPERS");

const SETTING = "test-setting";
const METRIC = "0";
function idKey(name, metric = METRIC) {
  return P.pairIdentityKey(SETTING, name, metric);
}
// Exactly `size` accounted bytes carrying the wrapper metric.
function pubRec(size) {
  assert.ok(size >= 2 && size % 2 === 0, "constructible size " + size);
  return { metric: METRIC, pad: "x".repeat((size - 2) / 2) };
}

let checks = 0;
const queue = [];
function check(name, fn) {
  queue.push([name, fn]);
}
// Realm-safe structural compare: helper-block and worker-harness values
// are built inside vm contexts, whose Array/Object prototypes differ
// from this realm's, so strict deepEqual would reject identical shapes.
function eqDeep(actual, expected, msg) {
  assert.deepEqual(JSON.parse(JSON.stringify(actual)), expected, msg);
}

// ---- oracle conformance ------------------------------------------------

// Run one trace's steps against production helpers; returns observables
// in the oracle's own shape (zero-filled, paints list, first-delivery).
function runTrace(trace) {
  const cache = P.createPairCache(trace.budget);
  const flight = F.createFlight();
  const callOf = new Map();
  const completedOnce = new Set();
  const delivered = new Set();
  const obs = {
    starts: 0,
    completes: 0,
    cacheHits: 0,
    blocked: 0,
    joins: 0,
    droppedInvalid: 0,
    duplicateDone: 0,
    errors: 0,
    recomputed: 0,
    blockedRedispatch: 0,
    paints: [],
    everCompleted: [],
    cached: [],
    accounted: 0,
    overTargetRetained: false,
  };
  let nextOracle = 0;
  syncStats();
  function syncStats() {
    obs.starts = flight.stats.starts;
    obs.joins = flight.stats.joins;
    obs.blocked = flight.stats.blocked;
  }
  function touch(key) {
    return P.pairCacheGet(cache, key, METRIC) !== null;
  }
  for (const step of trace.steps) {
    if (step.op === "need") {
      const absent = step.keys.filter((short) => !touch(idKey(short)) && !flight.running.has(idKey(short)));
      absent.forEach((short) => {
        if (completedOnce.has(short)) obs.recomputed++;
      });
      const res = F.flightNeed(
        flight,
        step.view,
        step.keys.map((k) => idKey(k)),
        touch,
      );
      syncStats();
      if (res.started) callOf.set("c" + ++nextOracle, res.started.callId);
      res.hit.forEach(() => obs.cacheHits++);
    } else if (step.op === "checkpoint") {
      const wcall = callOf.get(step.call);
      if (step.valid === false) {
        obs.droppedInvalid++;
        continue;
      }
      const gate = F.flightCheckpointOwner(flight, wcall, idKey(step.key));
      if (gate !== "ok") {
        if (gate === "dropped") obs.droppedInvalid++;
        continue;
      }
      P.pairCachePut(cache, idKey(step.key), pubRec(step.size || 4));
      F.flightComplete(flight, wcall, idKey(step.key));
      obs.completes++;
      if (!completedOnce.has(step.key)) {
        completedOnce.add(step.key);
        obs.everCompleted.push(step.key);
      }
    } else if (step.op === "done") {
      const wcall = callOf.get(step.call);
      if (!wcall || !flight.calls.has(wcall)) {
        obs.duplicateDone++;
        continue;
      }
      for (const k of step.keys) {
        const r = flight.running.get(idKey(k));
        if (!r || r.owner !== wcall) {
          obs.droppedInvalid++;
          continue;
        }
        P.pairCachePut(cache, idKey(k), pubRec(step.size || 4));
        F.flightComplete(flight, wcall, idKey(k));
        obs.completes++;
        if (!completedOnce.has(k)) {
          completedOnce.add(k);
          obs.everCompleted.push(k);
        }
      }
      flight.calls.delete(wcall);
    } else if (step.op === "detach") {
      F.flightDetach(flight, step.view);
      syncStats();
    } else if (step.op === "ack") {
      const wcall = callOf.get(step.call);
      if (wcall) {
        let subscribed = 0;
        flight.running.forEach((r) => {
          if (r.owner === wcall && Object.keys(r.subs).length) {
            subscribed++;
          }
        });
        assert.equal(subscribed, 0, "ack continuation has no wrapper mapping");
        F.flightAck(flight, wcall);
        callOf.delete(step.call);
      }
    } else if (step.op === "fail" || step.op === "watchdog") {
      const wcall = callOf.get(step.call);
      assert.ok(wcall && flight.calls.has(wcall), "live call to fail");
      const nid = F.flightFail(flight, wcall);
      callOf.delete(step.call);
      if (nid === null) {
        obs.errors++;
        assert.equal(step.retry, null, "terminal fail expected");
        continue;
      }
      assert.equal(step.retry, "c" + ++nextOracle, "bounded retry id");
      callOf.set(step.retry, nid);
      syncStats();
    } else if (step.op === "paint") {
      const pending = step.keys.filter((k) => !touch(idKey(k)));
      assert.deepEqual(pending, step.pending ?? [], "paint pending");
      for (const k of step.keys) {
        if (!touch(idKey(k))) continue;
        delivered.add(step.view + ":" + k);
        const seen = obs.paints.some((p) => p.view === step.view && p.key === k);
        if (!seen) obs.paints.push({ view: step.view, key: k });
      }
    } else if (step.op === "pin") {
      P.pairCacheSetPins(
        cache,
        step.keys.map((k) => idKey(k)),
      );
    } else {
      throw new Error("unknown op " + step.op);
    }
  }
  const snap = P.pairCacheSnapshot(cache);
  obs.accounted = snap.bytes;
  obs.blockedRedispatch = flight.stats.blocked;
  obs.overTargetRetained = snap.overflow;
  obs.cached = [...cache.slots.keys()].map((k) => k.slice((SETTING + "\n@0\n").length));
  return { obs, snap };
}

const { TRACES } = await import(pathToFileURL(join(ORACLE, "fixtures", "reuse_fixtures.mjs")).href);
assert.equal(TRACES.length, 18, "frozen oracle ships 18 traces");

for (const trace of TRACES) {
  check("oracle " + trace.id + " " + trace.title, () => {
    const { obs } = runTrace(trace);
    for (const k of Object.keys(trace.expect)) {
      assert.deepEqual(obs[k], trace.expect[k], trace.id + " observable " + k);
    }
  });
}

// ---- adversarial registry events ---------------------------------------

check("metric is per-key identity: no hit or join across metrics", () => {
  const cache = P.createPairCache(1 << 20);
  const flight = F.createFlight();
  const ka = P.pairIdentityKey(SETTING, "he", 8);
  const kb = P.pairIdentityKey(SETTING, "he", 9);
  assert.notEqual(ka, kb);
  P.pairCachePut(cache, ka, { metric: 8, steps: [{ step: 1 }], domain: { lo: 1, hi: 1 } });
  let joins = 0;
  const r = F.flightNeed(flight, "v1", [kb], (k) => P.pairCacheGet(cache, k, 9) !== null);
  assert.equal(r.hit.length, 0, "metric-foreign record is an exact miss");
  assert.ok(r.started, "dispatches its own owner, never joins");
  assert.equal(joins, flight.stats.joins);
  assert.equal(flight.stats.starts, 1);
});

check("foreign identity/capture/engine keys never hit", () => {
  const cache = P.createPairCache(1 << 20);
  const mk = (ds, cap, wasm) =>
    P.pairIdentityKey(
      P.pairSettingKey({
        dataset: ds,
        font: "f",
        capture: cap,
        source: "s",
        wasm,
        score: "sc",
        search: "se",
        r: 12,
        q: 2,
        tau: 0.5,
        norm: 12,
        strength: "x",
      }),
      "he",
      8,
    );
  const home = mk("roboto-16-mono", "c1", "w1");
  P.pairCachePut(cache, home, { metric: 8, steps: [{ step: 1 }], domain: { lo: 1, hi: 1 } });
  for (const [why, k] of [
    ["profile", mk("roboto-16-gray", "c2", "w1")],
    ["capture", mk("roboto-16-mono", "cX", "w1")],
    ["engine", mk("roboto-16-mono", "c1", "w2")],
    [
      "geometry",
      P.pairIdentityKey(
        P.pairSettingKey({
          dataset: "roboto-16-mono",
          font: "f",
          capture: "c1",
          source: "s",
          wasm: "w1",
          score: "sc",
          search: "se",
          r: 13,
          q: 2,
          tau: 0.5,
          norm: 12,
          strength: "x",
        }),
        "he",
        8,
      ),
    ],
  ]) {
    assert.equal(P.pairCacheGet(cache, k, 8), null, "no hit: " + why);
  }
  assert.ok(P.pairCacheGet(cache, home, 8) !== null, "home identity hits");
});

check("out-of-order done/ack never release another owner", () => {
  const flight = F.createFlight();
  const r1 = F.flightNeed(flight, "v1", ["a"], () => false);
  const c1 = r1.started.callId;
  // Duplicate done: second terminal receipt counts, changes nothing.
  let dups = 0;
  const doneOnce = (callId) => {
    if (!flight.calls.has(callId)) {
      dups++;
      return;
    }
    F.flightAck(flight, callId);
  };
  doneOnce(c1);
  doneOnce(c1);
  assert.equal(dups, 1);
  // Ack for an unknown or finished call is a silent no-op.
  eqDeep(F.flightAck(flight, c1), []);
  eqDeep(F.flightAck(flight, "k999"), []);
  // A checkpoint for a released owner drops without publishing.
  assert.equal(F.flightCheckpointOwner(flight, c1, "a"), "dropped");
  // A new generation dispatches exactly one new owner for the key.
  const r2 = F.flightNeed(flight, "v2", ["a"], () => false);
  assert.ok(r2.started && r2.started.callId !== c1);
  assert.equal(r2.blocked.length, 0);
});

check("two subscribers: detaching one keeps the owner live", () => {
  const flight = F.createFlight();
  const r1 = F.flightNeed(flight, "v1", ["a", "b"], () => false);
  assert.ok(r1.started);
  const r2 = F.flightNeed(flight, "v2", ["a"], () => false);
  eqDeep(r2.joined, ["a"]);
  assert.deepEqual(r2.started, null);
  const stopped = F.flightDetach(flight, "v1");
  eqDeep(stopped, ["b"], "only the unsubscribed key stops");
  assert.equal(flight.running.get("a").stopping, false);
  assert.equal(flight.running.get("a").subs.v2, true);
  assert.equal(flight.running.get("b").stopping, true);
});

check("unknown pair validation fails without identity", () => {
  const item = { key: "he", metric: 8 };
  const good = { metric: 8, steps: [{ step: 4 }, { step: 5 }], domain: { lo: 4, hi: 5 } };
  assert.equal(P.validateCheckpointSteps(item, good), true);
  assert.equal(P.validateCheckpointSteps(null, good), false);
});

// ---- worker true-boundary counters (independent prototype) -------------

function loadWorker() {
  const src = readFileSync(resolve(root, "yinyangfit_interactive_v3_worker.js"), "utf8");
  const body = src.replace(/^__YY_WASM_GLUE__\s*/, "void 0;");
  const outbox = [];
  const counts = { entries: 0, returns: 0, throws: 0, loads: 0, domains: 0 };
  const behavior = { throwOn: new Set(), missingCovers: new Set(), blankOn: new Set(), slowMs: 0 };
  const engine = {
    // Frozen score identity the worker asserts before scoring.
    version() {
      return '{"score_model":"yinyangfit-local-energy-v2",' + '"frozen_normalization_radius":12}';
    },
    load_glyph(ds, sha, cp) {
      counts.loads++;
      if (behavior.missingCovers.has(String(cp))) {
        throw new Error("no pixels for U+" + cp);
      }
      return true;
    },
    search_domain() {
      counts.domains++;
      return JSON.stringify({ lo: 1, hi: 3 });
    },
    score_pair_local(ds, l, r) {
      counts.entries++;
      if (behavior.slowMs > 0) {
        const t0 = Date.now();
        while (Date.now() - t0 < behavior.slowMs);
      }
      if (behavior.throwOn.has(l + ":" + r)) {
        counts.throws++;
        throw new Error("engine boom");
      }
      counts.returns++;
      return JSON.stringify({ steps: [{ step: 1 }, { step: 2 }, { step: 3 }] });
    },
    cache_sizes() {
      return { glyphs: 0, domains: 0 };
    },
    glyph_component() {
      return null;
    },
    contribution_map_local() {
      return JSON.stringify({ rows: [] });
    },
    last_component_note() {
      return "";
    },
    last_map_geometry() {
      return "";
    },
  };
  const self = {
    YYWasmRT: {
      YinYangEngine: function () {
        return engine;
      },
      initSync() {
        return {};
      },
    },
    postMessage(msg) {
      outbox.push(msg);
    },
    onmessage: null,
  };
  const sandbox = {
    self,
    setTimeout,
    clearTimeout,
    JSON,
    Object,
    Math,
    Float64Array,
    Int32Array,
    Array,
    Error,
    String,
    Number,
    Boolean,
    isFinite,
  };
  vm.createContext(sandbox);
  vm.runInContext(body, sandbox, { filename: "worker-under-test" });
  // Alias the bare `self`/`setTimeout` reads onto the sandbox holder.
  return {
    self,
    outbox,
    counts,
    behavior,
    engine,
    post(data) {
      self.onmessage({ data });
    },
  };
}

function items(names) {
  return names.map((name, i) => ({ key: name, left: String(100 + i), right: String(200 + i), metric: 8 }));
}
function coversOf(list) {
  const covers = {};
  list.forEach((it) => {
    covers[it.left] = { w: 1, h: 1, left: 0, top: 0, cover: [1] };
    covers[it.right] = { w: 1, h: 1, left: 0, top: 0, cover: [1] };
  });
  return covers;
}
async function waitFor(outbox, pred, timeoutMs = 15000) {
  const t0 = Date.now();
  for (;;) {
    const hit = outbox.find(pred);
    if (hit) return hit;
    if (Date.now() - t0 > timeoutMs) throw new Error("worker wait timeout");
    await new Promise((r) => setTimeout(r, 10));
  }
}

check("worker counters match independent boundary counts (clean)", async () => {
  const w = loadWorker();
  const list = items(["a", "b", "c", "d", "e"]);
  w.post({ kind: "init", params: {}, glyphs: {}, covers: coversOf(list) });
  await waitFor(w.outbox, (m) => m.kind === "ready");
  w.post({
    kind: "score",
    jobId: "j1",
    dataset: "d",
    captureSha: "c",
    key: "k",
    glyphs: coversOf(list),
    params: {},
    items: list,
  });
  const done = await waitFor(w.outbox, (m) => m.kind === "done" && m.jobId === "j1");
  assert.equal(done.engineCalls, 5);
  assert.equal(done.engineDone, 5);
  assert.equal(done.engineThrows || 0, 0);
  assert.equal(done.preCallErrors || 0, 0);
  eqDeep(w.counts, { entries: 5, returns: 5, throws: 0, loads: 10, domains: 5 });
  assert.equal(Object.keys(done.results).length, 5);
});

check("worker pre-call failures never enter the engine", async () => {
  const w = loadWorker();
  const list = items(["a", "b", "c"]);
  w.behavior.missingCovers.add(list[1].left);
  w.post({ kind: "init", params: {}, glyphs: {}, covers: coversOf(list) });
  await waitFor(w.outbox, (m) => m.kind === "ready");
  w.post({
    kind: "score",
    jobId: "j1",
    dataset: "d",
    captureSha: "c",
    key: "k",
    glyphs: coversOf(list),
    params: {},
    items: list,
  });
  const done = await waitFor(w.outbox, (m) => m.kind === "done" && m.jobId === "j1");
  assert.equal(done.engineCalls, 2, "only prepared pairs enter");
  assert.equal(done.engineDone, 2);
  assert.equal(done.preCallErrors, 1);
  assert.equal(w.counts.entries, 2);
  assert.ok(done.results.b.error, "honest error record rides the final");
});

check("worker engine throw counts at the boundary", async () => {
  const w = loadWorker();
  const list = items(["a", "b", "c"]);
  w.behavior.throwOn.add(list[1].left + ":" + list[1].right);
  w.post({ kind: "init", params: {}, glyphs: {}, covers: coversOf(list) });
  await waitFor(w.outbox, (m) => m.kind === "ready");
  w.post({
    kind: "score",
    jobId: "j1",
    dataset: "d",
    captureSha: "c",
    key: "k",
    glyphs: coversOf(list),
    params: {},
    items: list,
  });
  const done = await waitFor(w.outbox, (m) => m.kind === "done" && m.jobId === "j1");
  assert.equal(done.engineCalls, 3);
  assert.equal(done.engineDone, 2);
  assert.equal(done.engineThrows, 1);
  assert.deepEqual([w.counts.entries, w.counts.returns, w.counts.throws], [3, 2, 1]);
  assert.ok(done.results.b.error);
});

check("worker cancel acks with executed proof, never dones", async () => {
  const w = loadWorker();
  // Slow engine: the cancel must land mid-flight, not after a drain.
  w.behavior.slowMs = 25;
  const list = items(["a", "b", "c", "d", "e", "f", "g", "h"]);
  w.post({ kind: "init", params: {}, glyphs: {}, covers: coversOf(list) });
  await waitFor(w.outbox, (m) => m.kind === "ready");
  w.post({
    kind: "score",
    jobId: "j1",
    dataset: "d",
    captureSha: "c",
    key: "k",
    glyphs: coversOf(list),
    params: {},
    items: list,
  });
  await waitFor(w.outbox, (m) => m.kind === "progress" && m.jobId === "j1");
  w.post({ kind: "cancel", jobId: "j1" });
  const ack = await waitFor(w.outbox, (m) => m.kind === "score-stopped" && m.jobId === "j1");
  assert.notEqual(ack.reason, "unknown-job", "cancel hit a live job");
  assert.ok(Array.isArray(ack.executedKeys));
  assert.equal(ack.executedCalls, ack.executedKeys.length);
  assert.ok(ack.executedKeys.length >= 2, "in-flight chunk completed");
  assert.ok(!w.outbox.some((m) => m.kind === "done" && m.jobId === "j1"), "no done after cancel");
  assert.equal(w.counts.entries, ack.executedCalls);
});

check("worker drop trims queued pairs at the chunk boundary", async () => {
  const w = loadWorker();
  // Slow engine: the drop must land after one chunk, before the drain.
  w.behavior.slowMs = 25;
  const list = items(["a", "b", "c", "d", "e", "f"]);
  w.post({ kind: "init", params: {}, glyphs: {}, covers: coversOf(list) });
  await waitFor(w.outbox, (m) => m.kind === "ready");
  w.post({
    kind: "score",
    jobId: "j1",
    dataset: "d",
    captureSha: "c",
    key: "k",
    glyphs: coversOf(list),
    params: {},
    items: list,
  });
  await waitFor(w.outbox, (m) => m.kind === "progress" && m.jobId === "j1" && m.done >= 2);
  w.post({ kind: "drop", jobId: "j1", keys: list.slice(2).map((it) => it.key) });
  const end = await waitFor(w.outbox, (m) => (m.kind === "done" || m.kind === "score-stopped") && m.jobId === "j1");
  const got = end.kind === "done" ? Object.keys(end.results) : end.executedKeys;
  eqDeep(got.sort(), ["a", "b"], "only started pairs completed");
  assert.ok(w.counts.entries <= 2, "trimmed pairs never entered");
});

check("worker done strips finished pairs dropped mid-flight", async () => {
  const w = loadWorker();
  // The drop lands after the first chunk fully merged: pair a already
  // executed, but the page excluded it, so the done receipt must not
  // return it (the exact-set check excludes posted drops).
  w.behavior.slowMs = 25;
  const list = items(["a", "b", "c", "d"]);
  w.post({ kind: "init", params: {}, glyphs: {}, covers: coversOf(list) });
  await waitFor(w.outbox, (m) => m.kind === "ready");
  w.post({
    kind: "score",
    jobId: "j1",
    dataset: "d",
    captureSha: "c",
    key: "k",
    glyphs: coversOf(list),
    params: {},
    items: list,
  });
  await waitFor(w.outbox, (m) => m.kind === "progress" && m.jobId === "j1" && m.done >= 2);
  w.post({ kind: "drop", jobId: "j1", keys: ["a"] });
  const end = await waitFor(w.outbox, (m) => (m.kind === "done" || m.kind === "score-stopped") && m.jobId === "j1");
  assert.equal(end.kind, "done", "wanted remainder completes with done");
  eqDeep(Object.keys(end.results).sort(), ["b", "c", "d"], "dropped-but-finished pair stripped from done");
});

for (const [name, fn] of queue) {
  await fn();
  checks++;
  console.log("ok: " + name);
}
console.log("pairflight unit: " + checks + " checks passed");
