// Node check of the built WASM packages vs the frozen adapter corpus.
//
// Usage: node smoke/parity_node.mjs ADAPTER_DIR REPO_ROOT
//
// Covers the runtime/parity spike scope: default Roboto-16 Mono um/og and
// the exact Gray capture inputs, finite fields, core G2 and TIE-v2 choices
// vs the frozen Python values. Instantiates the *web* package from raw
// bytes (`initSync({ module: bytes })`, the offline file:// worker path: no
// fetch of a .wasm URL), and smoke-checks the nodejs package too.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [adapterDir, repoRoot] = process.argv.slice(2);
if (!adapterDir || !repoRoot) {
  console.error("usage: node smoke/parity_node.mjs ADAPTER_DIR REPO_ROOT");
  process.exit(2);
}
const leaf = new URL("..", import.meta.url).pathname;
const adapter = JSON.parse(readFileSync(join(adapterDir, "adapter.json"), "utf8"));

let failures = 0;
function check(name, cond, detail = "") {
  if (!cond) {
    failures += 1;
    console.error(`FAIL ${name} ${detail}`);
  } else {
    console.log(`ok ${name}`);
  }
}

// Web package from inlined bytes (offline path).
const wasmBytes = readFileSync(join(leaf, "pkg-web", "yinyang_oriented_engine_bg.wasm"));
const web = await import(pathToFileURL(join(leaf, "pkg-web", "yinyang_oriented_engine.js")).href);
web.initSync({ module: wasmBytes });
const engine = new web.YinYangEngine();
console.log("version:", engine.version());

function loadDataset(name) {
  const info = adapter.datasets[name];
  const cap = JSON.parse(readFileSync(join(repoRoot, info.path), "utf8"));
  const byCp = new Map();
  if (Array.isArray(cap.glyphs)) {
    for (const g of cap.glyphs) {
      const b = g.bitmap;
      byCp.set(g.codepoint, {
        w: b.width,
        h: b.height,
        left: b.left,
        top: b.top,
        cover: Float64Array.from(b.pixels.map((p) => (p ? 1 : 0))),
        sha: info.sha256,
      });
    }
  } else {
    for (const g of cap.font.glyphs) {
      byCp.set(g.codepoint, {
        w: g.width,
        h: g.height,
        left: g.left,
        top: g.top,
        cover: Float64Array.from(g.pixels.map((p) => p / 7)),
        sha: info.sha256,
      });
    }
  }
  return byCp;
}

const cases = [
  { dataset: "roboto-16-mono", pair: "um" },
  { dataset: "roboto-16-mono", pair: "og" },
  { dataset: "roboto-16-gray", pair: "um" },
  { dataset: "roboto-16-gray", pair: "og" },
];
for (const { dataset, pair } of cases) {
  const cells = loadDataset(dataset);
  const entry =
    [...adapter.study, ...adapter.novel].find((e) => e.dataset === dataset && e.pair === pair) ??
    adapter.study.find((e) => e.dataset === dataset && e.pair === pair);
  if (!entry) {
    check(`${dataset} ${pair} present`, false);
    continue;
  }
  const l = pair.codePointAt(0);
  const r = pair.codePointAt(1);
  for (const cp of [l, r]) {
    const c = cells.get(cp);
    const out = JSON.parse(engine.load_glyph(dataset, c.sha, cp, c.w, c.h, c.left, c.top, c.cover));
    check(`${dataset} ${pair} U+${cp.toString(16)} loaded`, out.recomputed === true || out.recomputed === false);
  }
  const deltas = Int32Array.from(entry.steps.map((s) => s.delta));
  const res = JSON.parse(engine.score_pair(dataset, l, r, entry.metric, deltas, 0.5, "notebook", 4.0));
  let worst = 0;
  for (let i = 0; i < res.steps.length; i++) {
    const got = res.steps[i];
    const exp = entry.steps[i];
    if (got.valid !== exp.valid) {
      check(`${dataset} ${pair} step ${got.step} valid`, false);
      continue;
    }
    if (!got.valid) continue;
    const rel = Math.abs(got.g2 - exp.g2) / Math.max(1, Math.abs(exp.g2));
    worst = Math.max(worst, rel);
    if (rel > 1e-9) {
      check(`${dataset} ${pair} step ${got.step} g2`, false, `got ${got.g2} want ${exp.g2}`);
    }
  }
  check(`${dataset} ${pair} g2 within 1e-9 (worst ${worst})`, worst <= 1e-9);
  const expChoice = entry.choices["4.0"];
  check(
    `${dataset} ${pair} C*=4 choice`,
    JSON.stringify([...res.minimizing].sort((a, b) => a - b)) ===
      JSON.stringify([...expChoice.minimizing].sort((a, b) => a - b)) &&
      res.chosen === expChoice.chosen &&
      res.fallback === expChoice.fallback,
    JSON.stringify(res.minimizing),
  );
  // Contribution map reduces to the step G2.
  const map = engine.contribution_map(dataset, l, r, entry.metric, 0.5, "notebook");
  const geo = JSON.parse(engine.last_map_geometry());
  let sum = 0;
  for (const v of map) sum += v;
  const stepG2 = res.steps.find((s) => s.step === entry.metric).g2;
  check(
    `${dataset} ${pair} map reduces to G2`,
    Math.abs(sum - stepG2) <= 1e-9 * Math.max(1, Math.abs(stepG2)),
    `sum ${sum} g2 ${stepG2} geo ${geo.width}x${geo.height}`,
  );
  // Slate projection is bounded in [0,1].
  const slate = engine.glyph_component(dataset, l, "slate", 0, 0);
  let ok = true;
  for (const v of slate) {
    if (!(v >= 0 && v <= 1)) {
      ok = false;
      break;
    }
  }
  check(`${dataset} ${pair} slate in [0,1]`, ok);
}

// Nodejs package smoke (CJS via createRequire; the repo root is type: module).
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { copyFileSync } from "node:fs";
const require = createRequire(import.meta.url);
// wasm-bindgen nodejs output is CJS; the repo root is type: module, so load
// it through a .cjs copy (same bytes, no rebuild).
const cjsCopy = join(tmpdir(), "yinyang_oriented_engine.cjs");
copyFileSync(join(leaf, "pkg-nodejs", "yinyang_oriented_engine.js"), cjsCopy);
copyFileSync(
  join(leaf, "pkg-nodejs", "yinyang_oriented_engine_bg.wasm"),
  join(tmpdir(), "yinyang_oriented_engine_bg.wasm"),
);
const nodeMod = require(cjsCopy);
const engine2 = new nodeMod.YinYangEngine();
check("nodejs package constructs", JSON.parse(engine2.version()).model === "yinyangfit-oriented-engine-v1");

// Full-workload Node timing (TIMED=1): cold load+score of every adapter
// pair, then warm rescore. Reports wall seconds for the UI perf picture.
if (process.env.TIMED === "1" && failures === 0) {
  const tEngine = new web.YinYangEngine();
  const all = [...adapter.study, ...adapter.novel];
  const deltas = Int32Array.from([-2, -1, 0, 1, 2]);
  let loadMs = 0;
  let scoreMs = 0;
  let warmMs = 0;
  let steps = 0;
  // Per-pair load + cold score + immediate warm rescore (fields cached).
  for (const e of all) {
    const cells = loadDataset(e.dataset);
    const l = e.pair.codePointAt(0);
    const r = e.pair.codePointAt(1);
    let t = performance.now();
    for (const cp of [l, r]) {
      const c = cells.get(cp);
      tEngine.load_glyph(e.dataset, c.sha, cp, c.w, c.h, c.left, c.top, c.cover);
    }
    loadMs += performance.now() - t;
    t = performance.now();
    const res = JSON.parse(tEngine.score_pair(e.dataset, l, r, e.metric, deltas, 0.5, "notebook", null));
    scoreMs += performance.now() - t;
    t = performance.now();
    tEngine.score_pair(e.dataset, l, r, e.metric, deltas, 0.5, "notebook", null);
    warmMs += performance.now() - t;
    steps += res.steps.length;
  }
  console.log(
    JSON.stringify({
      timed_pairs: all.length,
      timed_steps: steps,
      cold_load_s: loadMs / 1000,
      cold_score_s: scoreMs / 1000,
      warm_rescore_s: warmMs / 1000,
    }),
  );
}

console.log(failures === 0 ? "PASS" : `FAILURES: ${failures}`);
process.exit(failures === 0 ? 0 : 1);
