// Pair-cache unit gate (node only, no browser): byte accounting, true
// pair-aware LRU with read-refresh, metric-carrying identity, replace/
// clear/pin semantics, setting isolation, strict complete-curve
// validation, and duplicate-receipt accounting.
//
// The helpers under test are extracted verbatim from the production
// wiring source between __PAIRCACHE_HELPERS_BEGIN__ /
// __PAIRCACHE_HELPERS_END__ and evaluated in a bare VM context, so
// these cases run the real production functions with synthetic
// records, not copies.
//
// Usage: node test_yinyangfit_interactive_v3_paircacheunit.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const root = dirname(fileURLToPath(import.meta.url));

function loadHelpers() {
  const src = readFileSync(resolve(root, "yinyangfit_interactive_v3_wiring.js"), "utf8");
  const begin = "/* __PAIRCACHE_HELPERS_BEGIN__ */";
  const end = "/* __PAIRCACHE_HELPERS_END__ */";
  const a = src.indexOf(begin),
    b = src.indexOf(end);
  assert.ok(a >= 0 && b > a, "pair-cache helper block markers present");
  const block = src.slice(a, b + end.length);
  const ctx = {};
  vm.createContext(ctx);
  vm.runInContext(block, ctx, { filename: "paircache-helpers" });
  for (const name of [
    "PAIR_CACHE_TARGET_BYTES",
    "pairPayloadBytes",
    "pairRecordBytes",
    "pairSettingKey",
    "pairIdentityKey",
    "pairSettingOf",
    "createPairCache",
    "pairCacheGet",
    "pairCachePut",
    "pairCacheEnforce",
    "pairCacheSetPins",
    "pairCacheClearPins",
    "pairCacheSnapshot",
    "validateCheckpointSteps",
  ]) {
    assert.ok(ctx[name] !== undefined, "helper exported: " + name);
  }
  return ctx;
}

const H = loadHelpers();
let checks = 0;
function check(name, fn) {
  fn();
  checks++;
  console.log("ok: " + name);
}

function setting(over = {}) {
  return {
    dataset: "roboto-16-mono",
    font: "f".repeat(64),
    capture: "c".repeat(64),
    source: "s".repeat(64),
    wasm: "w".repeat(64),
    score: "yinyangfit-local-energy-v2",
    search: "yinyangfit-search-v2",
    r: 14,
    q: 2,
    tau: 0.5,
    norm: 12,
    strength: "notebook",
    ...over,
  };
}

const METRIC = 8;

// Small fixed-shape shaped record (metric/steps/entry/search).
function rec(metric = METRIC, lo = 1, hi = 3) {
  const steps = [];
  for (let s = lo; s <= hi; s++) steps.push({ step: s });
  return {
    metric,
    steps,
    entry: { ok: [true, true, true], gl: [0.1, 0.2, 0.3] },
    search: { policy: "yinyangfit-search-v2", lo, hi, domain_reason: null, exhaustive: true },
  };
}

function fullKey(name, metric = METRIC, over) {
  return H.pairIdentityKey(H.pairSettingKey(setting(over)), name, metric);
}

check("initial target is 16MiB accounted curve payload", () => {
  assert.equal(H.PAIR_CACHE_TARGET_BYTES, 16 * 1024 * 1024);
});

check("accounting counts payload only, keys and tags excluded", () => {
  assert.equal(H.pairPayloadBytes(1), 8);
  assert.equal(H.pairPayloadBytes("ab"), 4);
  assert.equal(H.pairPayloadBytes(true), 0);
  assert.equal(H.pairPayloadBytes(null), 0);
  assert.equal(H.pairPayloadBytes(undefined), 0);
  assert.equal(H.pairPayloadBytes({ a: 1 }), 8);
  assert.equal(H.pairPayloadBytes({ a: 1, b: "xy" }), 12);
  assert.equal(H.pairPayloadBytes([1, "ab", null, true]), 12);
  assert.equal(H.pairPayloadBytes({}), 0);
});

check("identity key binds setting, metric and pair", () => {
  const a = fullKey("he", 8);
  const b = fullKey("he", 9);
  const c = fullKey("he", 8, { r: 15 });
  assert.notEqual(a, b, "metric differs -> different identity");
  assert.notEqual(a, c, "setting differs -> different identity");
  assert.equal(H.pairSettingOf(a), H.pairSettingKey(setting()));
});

check("LRU evicts oldest-first beyond budget, reads refresh", () => {
  const one = H.pairRecordBytes(rec());
  const c = H.createPairCache(one * 3);
  const key = H.pairSettingKey(setting());
  const id = (n) => H.pairIdentityKey(key, n, METRIC);
  ["aa", "bb", "cc", "dd", "ee"].forEach((n) => H.pairCachePut(c, id(n), rec()));
  let snap = H.pairCacheSnapshot(c);
  assert.equal(snap.pairs, 3);
  assert.ok(snap.bytes <= one * 3);
  assert.equal(snap.evicted, 2);
  assert.equal(H.pairCacheGet(c, id("cc"), METRIC).metric, 8);
  assert.equal(H.pairCacheGet(c, id("aa"), METRIC), null);
  H.pairCachePut(c, id("ff"), rec());
  H.pairCachePut(c, id("gg"), rec());
  snap = H.pairCacheSnapshot(c);
  assert.equal(snap.pairs, 3);
  assert.ok(H.pairCacheGet(c, id("cc"), METRIC) !== null, "refreshed record survives beyond-8-settings pressure");
  assert.equal(H.pairCacheGet(c, id("dd"), METRIC), null);
  assert.equal(H.pairCacheGet(c, id("ee"), METRIC), null);
  assert.equal(snap.evicted, 4);
  assert.equal(snap.overflow, false);
});

check("hot hit before ninth insert promotes under true LRU", () => {
  const one = H.pairRecordBytes(rec());
  const c = H.createPairCache(one * 8);
  const keyOf = (r) => H.pairIdentityKey(H.pairSettingKey(setting({ r })), "he", METRIC);
  for (let r = 1; r <= 8; r++) {
    H.pairCachePut(c, keyOf(r), rec());
  }
  assert.equal(H.pairCacheSnapshot(c).pairs, 8);
  assert.ok(H.pairCacheGet(c, keyOf(1), METRIC) !== null);
  H.pairCachePut(c, keyOf(9), rec());
  const snap = H.pairCacheSnapshot(c);
  assert.equal(snap.pairs, 8);
  assert.equal(snap.evicted, 1);
  assert.ok(H.pairCacheGet(c, keyOf(1), METRIC) !== null, "hot-hit oldest survives the ninth insert");
  assert.equal(H.pairCacheGet(c, keyOf(2), METRIC), null, "coldest (never re-read) evicted instead");
  assert.equal(snap.overflow, false);
});

check("capacity probe alone evicts under both FIFO and LRU", () => {
  const one = H.pairRecordBytes(rec());
  const c = H.createPairCache(one * 8);
  const keyOf = (r) => H.pairIdentityKey(H.pairSettingKey(setting({ r })), "he", METRIC);
  for (let r = 1; r <= 9; r++) {
    H.pairCachePut(c, keyOf(r), rec());
  }
  assert.equal(H.pairCacheGet(c, keyOf(1), METRIC), null);
  assert.ok(H.pairCacheGet(c, keyOf(9), METRIC) !== null);
});

check("replace adjusts by delta, no double count or double bytes", () => {
  const c = H.createPairCache(1 << 30);
  const k = fullKey("he");
  H.pairCachePut(c, k, rec(8, 1, 3));
  const afterFirst = H.pairCacheSnapshot(c);
  H.pairCachePut(c, k, rec(8, 1, 3));
  const afterDup = H.pairCacheSnapshot(c);
  assert.equal(afterDup.bytes, afterFirst.bytes);
  assert.equal(afterDup.stored, afterFirst.stored);
  assert.equal(afterDup.pairs, 1);
  H.pairCachePut(c, k, rec(8, 1, 3));
  assert.equal(H.pairCacheSnapshot(c).bytes, afterFirst.bytes);
});

check("same pair isolated across metric/capture/profile/engine/R/q", () => {
  const base = setting();
  const keys = {
    same: H.pairSettingKey(base),
    otherR: H.pairSettingKey(setting({ r: 15 })),
    otherQ: H.pairSettingKey(setting({ q: 2.5 })),
    otherCapture: H.pairSettingKey(setting({ capture: "d".repeat(64) })),
    otherFont: H.pairSettingKey(setting({ font: "e".repeat(64) })),
    otherSource: H.pairSettingKey(setting({ source: "t".repeat(64) })),
    otherWasm: H.pairSettingKey(setting({ wasm: "v".repeat(64) })),
    otherScore: H.pairSettingKey(setting({ score: "other" })),
    otherProfile: H.pairSettingKey(setting({ dataset: "roboto-16-gray" })),
  };
  for (const [name, k] of Object.entries(keys)) {
    if (name === "same") continue;
    assert.notEqual(k, keys.same, "isolated: " + name);
  }
  assert.equal(H.pairSettingKey(setting()), keys.same);
  const c = H.createPairCache(1 << 30);
  H.pairCachePut(c, H.pairIdentityKey(keys.same, "he", 8), rec(8, 1, 2));
  H.pairCachePut(c, H.pairIdentityKey(keys.otherR, "he", 9), rec(9, 1, 4));
  const a = H.pairCacheGet(c, H.pairIdentityKey(keys.same, "he", 8), 8);
  const b = H.pairCacheGet(c, H.pairIdentityKey(keys.otherR, "he", 9), 9);
  assert.equal(a.metric, 8);
  assert.equal(b.metric, 9);
  assert.equal(b.steps.length, 4);
  assert.equal(H.pairCacheSnapshot(c).pairs, 2);
});

check("metric-foreign reads miss, never serve", () => {
  const c = H.createPairCache(1 << 30);
  const key = H.pairSettingKey(setting());
  H.pairCachePut(c, H.pairIdentityKey(key, "he", 8), rec(8, 1, 2));
  // Same setting+pair, different requested metric: exact miss.
  assert.equal(H.pairCacheGet(c, H.pairIdentityKey(key, "he", 9), 9), null);
  // Stored record still served under its own metric.
  assert.ok(H.pairCacheGet(c, H.pairIdentityKey(key, "he", 8), 8) !== null);
  const snap = H.pairCacheSnapshot(c);
  assert.equal(snap.hits, 1);
  assert.equal(snap.misses, 1);
});

check("pinned working set overruns instead of evicting", () => {
  const one = H.pairRecordBytes(rec());
  const c = H.createPairCache(one * 2);
  const key = H.pairSettingKey(setting());
  const id = (n) => H.pairIdentityKey(key, n, METRIC);
  const names = ["p1", "p2", "p3"];
  H.pairCacheSetPins(c, names.map(id));
  names.forEach((n) => H.pairCachePut(c, id(n), rec()));
  let snap = H.pairCacheSnapshot(c);
  assert.equal(snap.pairs, 3);
  assert.equal(snap.overflow, true);
  assert.equal(snap.pinned, 3);
  H.pairCacheClearPins(c);
  snap = H.pairCacheSnapshot(c);
  assert.equal(snap.pairs, 2);
  assert.equal(snap.overflow, false);
  assert.equal(snap.pinned, 0);
  assert.ok(H.pairCacheGet(c, id("p3"), METRIC) !== null);
  assert.equal(H.pairCacheGet(c, id("p1"), METRIC), null);
});

check("obsolete identities evict before the pinned current view", () => {
  const one = H.pairRecordBytes(rec());
  const c = H.createPairCache(one * 3);
  const oldKey = H.pairSettingKey(setting({ r: 13 }));
  const newKey = H.pairSettingKey(setting({ r: 14 }));
  const oldId = (n) => H.pairIdentityKey(oldKey, n, METRIC);
  const newId = (n) => H.pairIdentityKey(newKey, n, METRIC);
  ["a1", "a2", "a3"].forEach((n) => H.pairCachePut(c, oldId(n), rec()));
  H.pairCacheSetPins(c, ["b1", "b2"].map(newId));
  ["b1", "b2"].forEach((n) => H.pairCachePut(c, newId(n), rec()));
  const snap = H.pairCacheSnapshot(c);
  assert.equal(snap.pairs, 3);
  assert.ok(H.pairCacheGet(c, newId("b1"), METRIC) !== null);
  assert.ok(H.pairCacheGet(c, newId("b2"), METRIC) !== null);
  assert.equal(H.pairCacheGet(c, oldId("a1"), METRIC), null);
  assert.equal(snap.overflow, false);
});

check("validation accepts complete curves only", () => {
  const item = { key: "he", metric: 8 };
  const good = { metric: 8, steps: [{ step: 6 }, { step: 7 }, { step: 8 }], domain: { lo: 6, hi: 8 } };
  assert.equal(H.validateCheckpointSteps(item, good), true);
  const blank = { metric: 8, steps: [{ step: 0 }], domain: { blank: true } };
  assert.equal(H.validateCheckpointSteps(item, blank), true);
  const empty = { metric: 8, steps: [{ step: 0 }], domain: { empty: true, reason: "row_bands_disjoint" } };
  assert.equal(H.validateCheckpointSteps(item, empty), true);
  const single = { metric: 8, steps: [{ step: 6 }], domain: { lo: 6, hi: 6 } };
  assert.equal(H.validateCheckpointSteps(item, single), true);
  const bad = [
    [{ metric: 9, steps: [{ step: 8 }], domain: { lo: 8, hi: 8 } }, "metric-foreign"],
    [{ metric: 8, steps: [{ step: 8 }], domain: { lo: 7, hi: 8 } }, "partial curve"],
    [{ metric: 8, steps: [], domain: { lo: 8, hi: 8 } }, "empty steps"],
    [{ metric: 8, domain: { lo: 8, hi: 8 } }, "missing steps"],
    [{ metric: 8, steps: [{ step: 8 }], domain: null }, "missing domain"],
    [{ metric: 8, steps: [{ step: 8 }], domain: {} }, "foreign domain"],
    [{ metric: 8, steps: [{ step: NaN }], domain: { lo: 8, hi: 8 } }, "non-finite step"],
    [{ metric: 8, steps: [null], domain: { lo: 8, hi: 8 } }, "null step"],
    [{ metric: 8, error: "missing cover" }, "error record"],
    [null, "null record"],
    ["x", "non-object record"],
  ];
  for (const [r, why] of bad) {
    assert.equal(H.validateCheckpointSteps(item, r), false, why);
  }
  assert.equal(H.validateCheckpointSteps(null, good), false);
  assert.equal(H.validateCheckpointSteps(undefined, good), false);
});

check("validation rejects non-contiguous curves", () => {
  const item = { key: "he", metric: 8 };
  const lo = 6,
    hi = 8;
  const dom = () => ({ lo, hi });
  const cases = [
    ["duplicate step", [{ step: 6 }, { step: 6 }, { step: 8 }]],
    ["unsorted steps", [{ step: 6 }, { step: 8 }, { step: 7 }]],
    ["fractional step", [{ step: 6 }, { step: 7.5 }, { step: 8 }]],
    ["out-of-domain step", [{ step: 6 }, { step: 7 }, { step: 9 }]],
    ["truncated full-length domain", [{ step: 6 }, { step: 7 }]],
    ["non-integer bounds", null, { lo: 6.5, hi: 8 }],
    ["inverted bounds", null, { lo: 8, hi: 6 }],
  ];
  for (const [why, steps, domain] of cases) {
    const rec = { metric: 8, steps: steps || [{ step: 6 }, { step: 7 }, { step: 8 }], domain: domain || dom() };
    assert.equal(H.validateCheckpointSteps(item, rec), false, why);
  }
  // Null shaped fields (abstain/overlap) on an exact domain still pass.
  assert.equal(
    H.validateCheckpointSteps(item, {
      metric: 8,
      steps: [{ step: 6, valid: false, gl: null }, { step: 7 }, { step: 8, overlap: true, gl: null }],
      domain: { lo: 6, hi: 8 },
    }),
    true,
  );
});

check("snapshot exposes bounded counters, no history", () => {
  const c = H.createPairCache(1 << 20);
  const snap = H.pairCacheSnapshot(c);
  assert.deepEqual(
    Object.keys(snap).sort(),
    [
      "bytes",
      "checkpointStored",
      "dropped",
      "evicted",
      "evictedBytes",
      "hits",
      "misses",
      "overflow",
      "pairs",
      "pinned",
      "settings",
      "stored",
    ].sort(),
  );
  assert.equal(typeof snap.bytes, "number");
  assert.equal(snap.pairs, 0);
});

console.log("paircache unit: " + checks + " checks passed");
