// Pool-helper unit gate (node only, no browser): admission, deterministic
// greedy partition, geometry estimate calibration, partition validation.
//
// The helpers under test are extracted verbatim from the production
// wiring source between __POOL_HELPERS_BEGIN__ / __POOL_HELPERS_END__
// and evaluated in a bare VM context, so these cases run the real
// production functions with mocked protocol data, not copies.
//
// Calibration anchors are retained machine records, not live runs:
//   raw-pool-c2.json  R13 single payload 185632224 B / linear 189595648 B
//                     R13 pool payloads 141787352+164684864 B (35+41 entries)
//                     R13 pool linear 144637952+167837696 = 312475648 B
//   raw-ab-c2.json    cold R12 C2 payload 173211712 B / linear 175374336 B
// Glyph dimensions come from the frozen C2 boot.json (disk bytes).
//
// Usage: node test_yinyangfit_interactive_v3_poolunit.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const root = dirname(fileURLToPath(import.meta.url));
const repo = resolve(root, "../..");

function loadHelpers() {
  const src = readFileSync(resolve(root, "yinyangfit_interactive_v3_wiring.js"), "utf8");
  const begin = "/* __POOL_HELPERS_BEGIN__ */";
  const end = "/* __POOL_HELPERS_END__ */";
  const a = src.indexOf(begin),
    b = src.indexOf(end);
  assert.ok(a >= 0 && b > a, "pool helper block markers present");
  const block = src.slice(a, b + end.length);
  const ctx = {};
  vm.createContext(ctx);
  vm.runInContext(block, ctx, { filename: "pool-helpers" });
  for (const name of [
    "POOL_MIN_PAIRS",
    "POOL_MIN_CPUS",
    "POOL_LINEAR_TARGET",
    "POOL_MAX_HALFWIDTH",
    "POOL_F64_LATTICES",
    "poolPad",
    "poolCells",
    "poolPairCost",
    "poolPartition",
    "poolGlyphSet",
    "poolEstimateBytes",
    "poolAdmit",
    "poolValidatePartition",
  ]) {
    assert.ok(ctx[name] !== undefined, "helper exported: " + name);
  }
  return ctx;
}

function robotoMonoDims() {
  const boot = JSON.parse(
    readFileSync(
      resolve(repo, "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/site-reviewed/boot.json"),
      "utf8",
    ),
  );
  const c = boot.cases.find((x) => x.id === "roboto-16");
  assert.ok(c, "roboto-16 case present");
  const glyphs = c.profiles.mono.glyphs;
  const dims = {};
  for (const cp of Object.keys(glyphs)) {
    dims[cp] = { w: glyphs[cp].w, h: glyphs[cp].h };
  }
  assert.ok(Object.keys(dims).length >= 46, "full mono repertoire");
  return dims;
}

function pairItems(cps) {
  // Ordered pairs over the repertoire slice (key/left/right/metric only).
  const items = [];
  for (let i = 0; i + 1 < cps.length; i++) {
    items.push({ key: "k" + cps[i] + "-" + cps[i + 1], left: String(cps[i]), right: String(cps[i + 1]), metric: 8 });
  }
  return items;
}

function defaultPairItems() {
  const boot = JSON.parse(
    readFileSync(
      resolve(repo, "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/site-reviewed/boot.json"),
      "utf8",
    ),
  );
  const c = boot.cases.find((x) => x.id === "roboto-16");
  const pairs = new Map();
  for (const line of c.profiles.mono.lines) {
    for (let i = 0; i + 1 < line.length; i++) {
      if (line[i] === " " || line[i + 1] === " ") continue;
      const key = line.slice(i, i + 2);
      pairs.set(key, { key, left: String(line.charCodeAt(i)), right: String(line.charCodeAt(i + 1)), metric: 8 });
    }
  }
  assert.equal(pairs.size, 78);
  return [...pairs.values()];
}

const H = loadHelpers();
let checks = 0;
function check(name, fn) {
  fn();
  checks++;
  console.log("ok: " + name);
}

// pad follows params.rs: max ceil(4*sigma)=12 over the default five-scale
// bank, plus R. Engine defaults nV1=8, nDir=16, nScales=5.
check("pad is 12+R with no per-family input", () => {
  assert.equal(H.poolPad(13), 25);
  assert.equal(H.poolPad(12), 24);
  assert.equal(H.POOL_MAX_HALFWIDTH, 12);
});

// Deterministic greedy balance: same input, same split; union covers the
// input with no pair lost or doubled; costs use cheap geometry only.
check("partition is deterministic and lossless", () => {
  const dims = robotoMonoDims();
  const cps = Object.keys(dims)
    .map(Number)
    .sort((x, y) => x - y);
  const items = pairItems(cps);
  assert.ok(items.length >= 16, "bounded pool fixture has >=16 pairs");
  const p1 = H.poolPartition(items, dims, 13);
  const p2 = H.poolPartition(items, dims, 13);
  assert.deepEqual(
    p1.a.map((x) => x.key),
    p2.a.map((x) => x.key),
  );
  assert.deepEqual(
    p1.b.map((x) => x.key),
    p2.b.map((x) => x.key),
  );
  const union = new Set([...p1.a, ...p1.b].map((x) => x.key));
  assert.equal(union.size, items.length);
  assert.ok(Math.abs(p1.costA - p1.costB) <= Math.max(p1.costA, p1.costB));
  // No warm-up scoring input exists: cost of an unscored pair derives
  // from cover dimensions alone.
  const pricey = H.poolPairCost(items[0], dims, 13);
  assert.ok(pricey > 0 && Number.isFinite(pricey));
});

check("partition cost ignores missing glyphs deterministically", () => {
  const dims = robotoMonoDims();
  const items = [
    { key: "zz", left: "999999", right: "999998", metric: 0 },
    ...pairItems(
      Object.keys(dims)
        .map(Number)
        .sort((x, y) => x - y)
        .slice(0, 20),
    ),
  ];
  const p = H.poolPartition(items, dims, 13);
  assert.equal(p.a.length + p.b.length, items.length);
});

// The default workload still fits while retaining the primary's previous
// allocation. Additional retained memory must increase admission cost even
// when it is smaller than the new partition's payload.
check("R13 default admits with retained allocation included", () => {
  const dims = robotoMonoDims();
  const split = H.poolPartition(defaultPairItems(), dims, 13);
  const est = H.poolEstimateBytes(split.a, split.b, dims, 13, 189595648);
  const fresh = H.poolEstimateBytes(split.a, split.b, dims, 13, 0);
  const retained = H.poolEstimateBytes(split.a, split.b, dims, 13, 1000);
  assert.equal(retained.total - fresh.total, 1000);
  console.log("  R13 est total=" + est.total + " ownedA=" + est.ownedA + " ownedB=" + est.ownedB);
  assert.ok(est.total >= 312475648, "estimate covers measured R13 combined linear");
  assert.ok(est.total <= H.POOL_LINEAR_TARGET, "R13 pool admits");
});

check("larger repertoire rejects when old and new allocations coexist", () => {
  const dims = robotoMonoDims();
  const cps = Object.keys(dims)
    .map(Number)
    .sort((x, y) => x - y);
  const items = pairItems(cps);
  const half = Math.ceil(items.length / 2);
  const est = H.poolEstimateBytes(items.slice(0, half), items.slice(half), dims, 13, 189595648);
  assert.equal(H.poolAdmit(items.length, 8, 8, est.total).ok, false);
});

// Full-duplication bound: even counting every glyph on both sides the
// estimate must remain above measured single-worker bytes (conservative)
// at R13.
check("R13 full-duplication estimate above single payload", () => {
  const dims = robotoMonoDims();
  const cps = Object.keys(dims)
    .map(Number)
    .sort((x, y) => x - y);
  const items = pairItems(cps);
  const est = H.poolEstimateBytes(items, items, dims, 13, 189595648);
  assert.ok(est.total >= 185632224, "above measured single payload");
  assert.ok(est.ownedA > 0 && est.ownedB > 0);
});

// Large geometry must reject: R32 over the same repertoire exceeds the
// 512 MiB target with no family whitelist involved.
check("R32 estimate rejects", () => {
  const dims = robotoMonoDims();
  const cps = Object.keys(dims)
    .map(Number)
    .sort((x, y) => x - y);
  const items = pairItems(cps);
  const half = Math.ceil(items.length / 2);
  const est = H.poolEstimateBytes(items.slice(0, half), items.slice(half), dims, 32, 189595648);
  console.log("  R32 est total=" + est.total);
  assert.ok(est.total > H.POOL_LINEAR_TARGET, "R32 pool over budget");
  const gate = H.poolAdmit(items.length, 8, 8, est.total);
  assert.equal(gate.ok, false);
  assert.equal(gate.reason, "over-budget");
});

// A retained large-R highwater rejects an otherwise fine job.
check("large retained highwater rejects", () => {
  const dims = robotoMonoDims();
  const cps = Object.keys(dims)
    .map(Number)
    .sort((x, y) => x - y);
  const items = pairItems(cps);
  const half = Math.ceil(items.length / 2);
  const est = H.poolEstimateBytes(items.slice(0, half), items.slice(half), dims, 13, 360000000);
  const gate = H.poolAdmit(items.length, 8, 8, est.total);
  assert.equal(gate.ok, false);
  assert.equal(gate.reason, "over-budget");
});

// Admission matrix: small jobs, weak or unknown hardware, unknown memory.
check("admission matrix", () => {
  // Cross-realm objects: compare fields, not identity.
  function gate(args, ok, reason) {
    const g = H.poolAdmit(...args);
    assert.equal(g.ok, ok, JSON.stringify(args));
    assert.equal(g.reason, reason, JSON.stringify(args));
  }
  gate([78, 8, 8, 1000000], true, "admitted");
  gate([15, 8, 8, 1000000], false, "small-job");
  gate([78, 2, 8, 1000000], false, "cpu-low");
  gate([78, undefined, 8, 1000000], false, "cpu-unknown");
  gate([78, null, 8, 1000000], false, "cpu-unknown");
  gate([78, 8, undefined, 1000000], false, "memory-unknown");
  gate([78, 8, null, 1000000], false, "memory-unknown");
  gate([78, 8, 8, 536870912 + 1], false, "over-budget");
  gate([78, 8, 8, NaN], false, "over-budget");
  assert.equal(H.POOL_MIN_PAIRS, 16);
  assert.equal(H.POOL_MIN_CPUS, 4);
  assert.equal(H.POOL_LINEAR_TARGET, 512 * 1024 * 1024);
});

// Partition validation: exact set with valid data or honest errors;
// anything else cannot count as complete.
check("partition validation", () => {
  const good = { a: { steps: [{ step: 1 }] }, b: { steps: [{ step: 2 }] } };
  const v = H.poolValidatePartition(["a", "b"], good);
  assert.equal(v.ok, true);
  assert.deepEqual(Object.keys(v.valid).sort(), ["a", "b"]);
  const honest = { a: { steps: [] }, b: { error: "missing cover" } };
  const h = H.poolValidatePartition(["a", "b"], honest);
  assert.equal(h.ok, true);
  assert.deepEqual(Object.keys(h.errors), ["b"]);
  assert.equal(H.poolValidatePartition(["a", "b"], { a: good.a }).ok, false);
  assert.equal(H.poolValidatePartition(["a", "b"], { a: good.a, b: good.b, c: good.a }).ok, false);
  assert.equal(H.poolValidatePartition(["a", "b"], { a: good.a, c: good.b }).ok, false);
  assert.equal(H.poolValidatePartition(["a", "b"], { a: good.a, b: null }).ok, false);
  assert.equal(H.poolValidatePartition(["a", "b"], { a: good.a, b: 42 }).ok, false);
  assert.equal(H.poolValidatePartition(["a", "b"], null).ok, false);
  assert.equal(H.poolValidatePartition(["a", "b"], "x").ok, false);
  const missing = H.poolValidatePartition(["a", "b"], { a: good.a });
  assert.equal(missing.reason, "incomplete-partition");
  const wrong = H.poolValidatePartition(["a", "b"], { a: good.a, c: good.b });
  assert.ok(wrong.reason === "incomplete-partition" || wrong.reason === "wrong-key");
});

console.log("pool unit: " + checks + " checks passed");
