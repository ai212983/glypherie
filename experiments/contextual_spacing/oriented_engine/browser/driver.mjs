// Driver for the isolated Class-L browser harness: real headless Chromium
// (playwright-core, same launch shape as apps/web browser tests) against
// a local read-only file server. No app code is touched; the page worker
// instantiates the shipping WASM bytes the page hashed (initSync inline
// bytes, offline), mirroring the main worker's seq/token/error protocol.
//
// Usage: node driver.mjs OUT_JSON
import { createServer } from "node:http";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { createHash } from "node:crypto";

// Package-resolved browser driver: playwright-core comes from the
// workspace web app's pinned install, never an absolute path.
const require = createRequire(new URL("../../../../apps/web/package.json", import.meta.url));
const { chromium } = require("playwright-core");

// Module-relative repo and engine roots: this driver lives at
// experiments/contextual_spacing/oriented_engine/browser/.
const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const LEAF = join(REPO, "experiments/contextual_spacing/oriented_engine");
const OUT = process.argv[2];
if (!OUT) {
  console.error("usage: node driver.mjs OUT_JSON");
  process.exit(2);
}

const ROUTES = [
  ["/w/", join(LEAF, "browser") + "/"],
  ["/pkg/", join(LEAF, "pkg-web") + "/"],
  ["/boot.json", join(REPO, "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/site-reviewed/boot.json")],
];
const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".json": "application/json",
  ".wasm": "application/wasm",
};

const failures = [];
const notes = [];
function fail(s) {
  failures.push(s);
  console.error(`FAIL ${s}`);
}
function note(s) {
  notes.push(s);
  console.log(`ok ${s}`);
}
function close(got, exp, tol) {
  if (!Number.isFinite(got) || !Number.isFinite(exp)) return got === exp;
  return Math.abs(got - exp) <= tol * Math.max(Math.abs(exp), 1.0);
}

const adapter = JSON.parse(
  readFileSync(
    join(REPO, "out/diagnostics/contextual-spacing/yinyang-normalization-repair/runtime/local_adapter.json"),
    "utf8",
  ),
);
const boot = JSON.parse(
  readFileSync(
    join(REPO, "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/site-reviewed/boot.json"),
    "utf8",
  ),
);

const server = createServer((req, res) => {
  try {
    const url = new URL(req.url ?? "/", "http://localhost");
    for (const [prefix, base] of ROUTES) {
      if (url.pathname.startsWith(prefix)) {
        const rel = decodeURIComponent(url.pathname.slice(prefix.length));
        const file = base.endsWith("/") ? join(base, rel) : base;
        const bytes = readFileSync(file);
        const ext = file.slice(file.lastIndexOf("."));
        res.writeHead(200, { "Content-Type": MIME[ext] ?? "application/octet-stream" });
        res.end(bytes);
        return;
      }
    }
    res.writeHead(404);
    res.end("no route");
  } catch (e) {
    res.writeHead(404);
    res.end(String(e));
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;

const browser = await chromium.launch({
  headless: true,
  // Precise performance.memory numbers instead of 10 MB buckets.
  args: ["--enable-precise-memory-info"],
});
const page = await browser.newPage();
page.setDefaultTimeout(180000);
page.on("console", (m) => {
  if (m.type() === "error") console.error("page:", m.text());
});
await page.goto(`${base}/w/harness.html`);
await page.waitForFunction(() => document.getElementById("status").textContent === "ready");

const call = (msg) => page.evaluate((m) => window.harness.call(m), msg);

const wasmFile = join(LEAF, "pkg-web/yinyang_oriented_engine_bg.wasm");
const wasmHash = createHash("sha256").update(readFileSync(wasmFile)).digest("hex");

// T1: identity — the page fetches, hashes, and hands the worker the
// exact bytes (never round-tripped through node).
const pageHash = await page.evaluate(async () => {
  const res = await fetch("/pkg/yinyang_oriented_engine_bg.wasm");
  if (!res.ok) throw new Error(`wasm fetch: ${res.status}`);
  const buf = await res.arrayBuffer();
  window.__wasmBytes = buf;
  return window.harness.sha256Hex(buf);
});
if (pageHash !== wasmHash) fail(`wasm bytes differ page ${pageHash} vs file ${wasmHash}`);
else note(`wasm bytes pinned ${wasmHash.slice(0, 12)}...`);
await page.evaluate(() => window.harness.start());
const initRes = await page.evaluate(() => {
  const b = window.__wasmBytes;
  window.__wasmBytes = null;
  return window.harness.call({ kind: "init", wasm: b }, [b]);
});
if (!initRes.ok) fail(`init: ${initRes.error}`);
const ver = JSON.parse(initRes.value);
const versionInfo = ver;
if (ver.score_model !== "yinyangfit-local-energy-v2") fail(`score_model ${ver.score_model}`);
else note(`score_model ${ver.score_model}`);
if (ver.frozen_normalization_radius !== 12) fail(`frozen radius ${ver.frozen_normalization_radius}`);
else note("frozen normalizer 12");
const mem0 = await page.evaluate(() => (performance.memory ? performance.memory.usedJSHeapSize : null));

// T2: default score parity on synthetic bars vs the frozen adapter.
const barsResult = await page.evaluate(() => {
  const mk = (trio) => {
    const c = new Float64Array(20 * 100);
    for (let y = 4; y < 16; y++) for (let x = 20; x < 22; x++) c[y * 100 + x] = 1.0;
    if (trio) for (let y = 4; y < 16; y++) for (let x = 62; x < 64; x++) c[y * 100 + x] = 1.0;
    return c;
  };
  return { bar: Array.from(mk(false)), trio: Array.from(mk(true)) };
});
async function loadSynthetic() {
  for (const [cp, cov] of [
    [0x41, barsResult.bar],
    [0x42, barsResult.bar],
    [0x43, barsResult.trio],
  ]) {
    const r = await call({
      kind: "load",
      token: 1,
      key: "bars",
      dataset: "synthetic",
      sha: "adapter-bar",
      cp,
      w: 100,
      h: 20,
      left: 0,
      top: 0,
      cover: cov,
    });
    if (!r.ok) fail(`load bars ${cp}: ${r.error}`);
  }
}
await loadSynthetic();
async function scorePair(key, token, dataset, sha, l, r, metric, deltas, tau, norm, strength, cstar) {
  const res = await call({
    kind: "score",
    token,
    key,
    dataset,
    l,
    r,
    metric,
    deltas,
    tau,
    norm,
    strength,
    cstar: cstar ?? null,
  });
  if (!res.ok) {
    fail(`score ${key}: ${res.error}`);
    return null;
  }
  return JSON.parse(res.value);
}
const expBars = adapter.bars.R12.pair;
const barsScore = await scorePair("bars", 1, "synthetic", "adapter-bar", 0x41, 0x42, 0, [6], 0.5, 12, "notebook", null);
if (barsScore) {
  const s = barsScore.steps[0];
  if (!close(s.gl, expBars.gl, 1e-9)) fail(`bars gl ${s.gl} != ${expBars.gl}`);
  else note(`bars gl parity ${s.gl}`);
  if (s.both_supported_pairpx !== expBars.both) fail(`bars both ${s.both_supported_pairpx} != ${expBars.both}`);
  else note(`bars both exact ${s.both_supported_pairpx}`);
  if (!close(s.honest_bound, expBars.bound, 1e-9)) fail(`bars bound ${s.honest_bound} != ${expBars.bound}`);
  else note("bars bound parity");
}

// T2b: real-pair self-consistency at default (map reduces, bound holds).
const roboto = boot.cases.find((c) => c.id === "roboto-16").profiles.mono;
const glyphs = roboto.glyphs;
async function loadBootPair(key, token, dsTag, a, b) {
  for (const cp of [a, b]) {
    const g = glyphs[String(cp)];
    const r = await call({
      kind: "load",
      token,
      key,
      dataset: dsTag,
      sha: roboto.capture_sha256,
      cp,
      w: g.w,
      h: g.h,
      left: g.left,
      top: g.top,
      coverBits: g.cover,
    });
    if (!r.ok) fail(`load boot ${cp}: ${r.error}`);
  }
}
await loadBootPair("real", 2, "roboto-16-mono", 117, 109);
const umScore = await scorePair(
  "real",
  2,
  "roboto-16-mono",
  roboto.capture_sha256,
  117,
  109,
  0,
  Array.from({ length: 141 }, (_, i) => i),
  0.5,
  12,
  "notebook",
  null,
);
let umValid = [];
if (umScore) {
  for (const s of umScore.steps) {
    if (!(s.valid && !s.abstain)) continue;
    umValid.push(s);
    if (!Number.isFinite(s.gl)) fail(`um step ${s.step}: nonfinite gl`);
    if (s.conditioning_shortfall > 0) fail(`um step ${s.step}: shortfall ${s.conditioning_shortfall}`);
    if (s.skipped_nonpositive > 0) fail(`um step ${s.step}: skipped ${s.skipped_nonpositive}`);
    if (!(s.gl <= s.honest_bound * (1 + 1e-12))) fail(`um step ${s.step}: bound violated`);
  }
  note(`um self-consistency ${umValid.length} valid steps`);
  const mid = umValid[Math.floor(umValid.length / 2)];
  const umSummed = await page.evaluate(
    (st) =>
      window.harness
        .call({
          kind: "map",
          token: 2,
          key: "real",
          dataset: "roboto-16-mono",
          l: 117,
          r: 109,
          step: st,
          tau: 0.5,
          norm: 12,
          strength: "notebook",
        })
        .then((mr) => {
          if (!mr.ok) return { ok: false, error: mr.error };
          const arr = new Float64Array(mr.value.map);
          let sum = 0;
          for (const v of arr) sum += v;
          return { ok: true, sum, length: arr.length };
        }),
    mid.delta,
  );
  if (!umSummed.ok) fail(`um map: ${umSummed.error}`);
  else if (!close(umSummed.sum, mid.gl, 1e-9)) fail(`um map ${umSummed.sum} != gl ${mid.gl}`);
  else note(`um map reduces ${umSummed.sum} (${umSummed.length}px)`);
}

// T3: default full-preview workload (same lines/pairs as bench_preview).
const lines = roboto.lines;
const pairs = [];
{
  const seen = new Set();
  for (const line of lines) {
    const ch = [...line];
    for (let i = 0; i + 1 < ch.length; i++) {
      const [a, b] = [ch[i], ch[i + 1]];
      if (a === " " || b === " ") continue;
      const key = a + b;
      if (seen.has(key)) continue;
      if (!glyphs[String(a.codePointAt(0))] || !glyphs[String(b.codePointAt(0))]) continue;
      seen.add(key);
      pairs.push([a.codePointAt(0), b.codePointAt(0)]);
    }
  }
}
note(`preview pairs ${pairs.length}`);
const mem = async () => page.evaluate(() => (performance.memory ? performance.memory.usedJSHeapSize : null));
const memAfterInit = await mem();

async function loadPairFor(key, token, dsTag, l, r) {
  // Per-pair load: the engine glyph cache is a bounded LRU (bulk preloads
  // evict — same reason bench_preview reloads per pair), so the working
  // set here is exactly the pair being scored.
  for (const cp of [l, r]) {
    const g = glyphs[String(cp)];
    const lr = await call({
      kind: "load",
      token,
      key,
      dataset: dsTag,
      sha: roboto.capture_sha256,
      cp,
      w: g.w,
      h: g.h,
      left: g.left,
      top: g.top,
      coverBits: g.cover,
    });
    if (!lr.ok) return false;
  }
  return true;
}
async function fullPreview(tag, token, normInfo) {
  const deltas = Array.from({ length: 151 }, (_, i) => i);
  const dsTag = `roboto-16-mono-${tag}`;
  // Cold: per-pair load + full-window score, 8 pairs in flight at a time.
  const tCold0 = Date.now();
  let totalSteps = 0,
    totalValid = 0,
    maxGl = 0,
    nLoads = 0;
  const pairSummaries = [];
  for (let i = 0; i < pairs.length; i += 8) {
    for (const [l, r] of pairs.slice(i, i + 8)) {
      if (!(await loadPairFor(`preview-${tag}`, token, dsTag, l, r))) {
        fail(`preview load ${l},${r}`);
        return null;
      }
      nLoads += 2;
    }
    const batch = pairs
      .slice(i, i + 8)
      .map(([l, r]) =>
        scorePair(`preview-${tag}`, token, dsTag, roboto.capture_sha256, l, r, 0, deltas, 0.5, 12, "notebook", null),
      );
    const results = await Promise.all(batch);
    for (let k = 0; k < results.length; k++) {
      const res = results[k];
      if (!res) return null;
      const valid = res.steps.filter((s) => s.valid && !s.abstain);
      totalSteps += res.steps.length;
      totalValid += valid.length;
      for (const s of valid) {
        if (!Number.isFinite(s.gl)) {
          fail(`preview ${tag} nonfinite gl`);
          return null;
        }
        if (s.conditioning_shortfall > 0 || s.skipped_nonpositive > 0) {
          fail(`preview ${tag} conditioning shortfall/skip`);
          return null;
        }
        maxGl = Math.max(maxGl, s.gl);
      }
      pairSummaries.push({
        pair: `${String.fromCodePoint(pairs[i + k][0])}${String.fromCodePoint(pairs[i + k][1])}`,
        n_valid: valid.length,
      });
    }
  }
  const coldS = (Date.now() - tCold0) / 1000;
  // Warm rescore (fields + local maps cached; same per-pair reloads).
  const tWarm0 = Date.now();
  for (let i = 0; i < pairs.length; i += 8) {
    for (const [l, r] of pairs.slice(i, i + 8)) await loadPairFor(`preview-${tag}`, token, dsTag, l, r);
    await Promise.all(
      pairs
        .slice(i, i + 8)
        .map(([l, r]) =>
          scorePair(`preview-${tag}`, token, dsTag, roboto.capture_sha256, l, r, 0, deltas, 0.5, 12, "notebook", null),
        ),
    );
  }
  const warmS = (Date.now() - tWarm0) / 1000;
  // Target re-derive: same cached maps, new cstar (reload pair first).
  // Targets per target-review decision: 8 (project-chosen preview
  // setting, NOT the .47 study seed), plus 0, 16, and one exact custom
  // target (a measured gl, expecting a zero-deviation pick).
  const tTgt0 = Date.now();
  const chosenByTarget = {};
  for (const t of [8.0, 0.0, 16.0]) {
    let sum = 0,
      n = 0;
    for (const [l, r] of pairs.slice(0, 8)) {
      if (!(await loadPairFor(`preview-${tag}`, token, dsTag, l, r))) {
        fail(`target load`);
        return null;
      }
      const res = await scorePair(
        `preview-${tag}`,
        token,
        dsTag,
        roboto.capture_sha256,
        l,
        r,
        0,
        deltas,
        0.5,
        12,
        "notebook",
        t,
      );
      if (!res) return null;
      sum += res.chosen;
      n++;
    }
    chosenByTarget[String(t)] = sum;
    if (n !== 8) {
      fail(`target ${t}: only ${n} pairs`);
      return null;
    }
  }
  const targetS = (Date.now() - tTgt0) / 1000;
  // Maps at one step per pair (sum computed in-page; buffers stay there).
  const tMap0 = Date.now();
  let mapWorst = 0;
  for (const [l, r] of pairs.slice(0, 8)) {
    if (!(await loadPairFor(`preview-${tag}`, token, dsTag, l, r))) {
      fail(`map load`);
      return null;
    }
    const summed = await page.evaluate(
      ([kk, tt, dd, ll, rr]) =>
        window.harness
          .call({
            kind: "map",
            token: tt,
            key: kk,
            dataset: dd,
            l: ll,
            r: rr,
            step: 9,
            tau: 0.5,
            norm: 12,
            strength: "notebook",
          })
          .then((mr) => {
            if (!mr.ok) return { ok: false, error: mr.error };
            const arr = new Float64Array(mr.value.map);
            let sum = 0;
            for (const v of arr) sum += v;
            return { ok: true, sum, length: arr.length };
          }),
      [`preview-${tag}`, token, dsTag, l, r],
    );
    if (!summed.ok) {
      fail(`preview map: ${summed.error}`);
      return null;
    }
    mapWorst = Math.max(mapWorst, summed.length);
  }
  const mapS = (Date.now() - tMap0) / 1000;
  return {
    n_pairs: pairs.length,
    totalSteps,
    totalValid,
    maxGl,
    nLoads,
    coldS,
    warmS,
    targetS,
    targets: chosenByTarget,
    mapS,
    map_pairs: 8,
    pairs: pairSummaries,
    ...normInfo,
  };
}

const memBeforeCold = await mem();
const defaultRun = await fullPreview("default", 10, { field_radius: 12, falloff: 2 });
// Exact custom target: um mid-step gl must pick a zero-deviation step.
let exactCustom = null;
{
  await loadBootPair("exact", 13, "roboto-16-mono-exact", 117, 109);
  const midGl = umValid[Math.floor(umValid.length / 2)].gl;
  const res = await scorePair(
    "exact",
    13,
    "roboto-16-mono-exact",
    roboto.capture_sha256,
    117,
    109,
    0,
    Array.from({ length: 141 }, (_, i) => i),
    0.5,
    12,
    "notebook",
    midGl,
  );
  if (res) {
    const picked = res.steps.find((s) => s.step === res.chosen);
    const dev = picked && picked.gl !== null ? Math.abs(picked.gl - midGl) : null;
    exactCustom = { cstar: midGl, chosen: res.chosen, deviation: dev };
    if (!(dev === 0)) fail(`exact custom target deviation ${dev}`);
    else note(`exact custom target picks zero-deviation step ${res.chosen}`);
  }
}
if (defaultRun)
  note(
    `default preview cold ${defaultRun.coldS.toFixed(1)}s warm ${defaultRun.warmS.toFixed(1)}s maps ${defaultRun.mapS.toFixed(1)}s`,
  );
const memAfterCold = await mem();

// T4: costly corner — same pairs, field R32 / q0.25, normalizer pinned 12.
const cornerInit = await page.evaluate(() =>
  window.harness.call({ kind: "init", wasm: null, params: JSON.stringify({ radius: 32, q: 0.25 }) }),
);
let cornerVer = null;
if (!cornerInit.ok) fail(`corner init: ${cornerInit.error}`);
else {
  cornerVer = JSON.parse(cornerInit.value);
  if (cornerVer.params?.radius !== 32 || cornerVer.params?.q !== 0.25) fail(`corner params ${cornerInit.value}`);
  else note(`corner engine field_R32 q0.25 (v2 identity ${cornerVer.score_model === "yinyangfit-local-energy-v2"})`);
}
const cornerRun = cornerInit.ok ? await fullPreview("corner", 11, { field_radius: 32, falloff: 0.25 }) : null;
if (cornerRun) note(`corner preview cold ${cornerRun.coldS.toFixed(1)}s warm ${cornerRun.warmS.toFixed(1)}s`);
const memAfterCorner = await mem();

// T5: latest-generation cancellation by termination + batching.
let terminatedStale = 0;
{
  // Fire a batch without awaiting, then terminate mid-flight.
  const pending = [];
  for (let i = 0; i < 8; i++) {
    const [l, r] = pairs[i];
    pending.push(
      page
        .evaluate(
          ({ l, r }) => {
            const d = new Int32Array(Array.from({ length: 151 }, (_, k) => k)).buffer;
            return window.harness.call(
              {
                kind: "score",
                token: 12,
                key: "preview-corner",
                dataset: "roboto-16-mono-corner",
                l,
                r,
                metric: 0,
                deltas: d,
                tau: 0.5,
                norm: 12,
                strength: "notebook",
                cstar: null,
              },
              [d],
            );
          },
          { l, r },
        )
        .catch(() => ({ ok: false, error: "terminated" })),
    );
  }
  await new Promise((r) => setTimeout(r, 1500));
  terminatedStale = await page.evaluate(() => window.harness.terminate());
  await Promise.all(pending);
  const staleLeft = await page.evaluate(() => window.harness.pendingCount());
  if (staleLeft !== 0) fail(`stale pending after terminate: ${staleLeft}`);
  else note(`termination dropped ${terminatedStale} in-flight`);
  await page.evaluate(() => window.harness.respawn());
  const re = await page.evaluate(async () => {
    const res = await fetch("/pkg/yinyang_oriented_engine_bg.wasm");
    const b = await res.arrayBuffer();
    return window.harness.call({ kind: "init", wasm: b }, [b]);
  });
  if (!re.ok) fail(`respawn init: ${re.error}`);
  else {
    const ping = await page.evaluate(() => window.harness.call({ kind: "ping" }));
    if (!ping.ok || !ping.value.alive) fail("respawn not alive");
    else note("respawn alive, buffers safe");
  }
  await loadSynthetic();
  const again = await scorePair("bars", 1, "synthetic", "adapter-bar", 0x41, 0x42, 0, [6], 0.5, 12, "notebook", null);
  if (again && !close(again.steps[0].gl, expBars.gl, 1e-9)) fail("post-respawn gl drift");
  else if (again) note("post-respawn gl identical");
}

// T6: worker failure behavior — invalid input is data, worker survives.
// (Calls the worker directly: ok:false here is the EXPECTED outcome,
// not a suite failure — scorePair would misrecord it as one.)
{
  const badRaw = await call({
    kind: "score",
    token: 99,
    key: "bad",
    dataset: "nosuch",
    sha: "x",
    l: 0x99,
    r: 0x9a,
    metric: 0,
    deltas: [0],
    tau: 0.5,
    norm: 12,
    strength: "notebook",
    cstar: null,
  });
  if (badRaw.ok) fail("expected failure for unloaded glyphs");
  else note("invalid input returns error, no crash");
  const ping = await page.evaluate(() => window.harness.call({ kind: "ping" }));
  if (!ping.ok) fail("worker dead after error");
  else note("worker alive after error");
}

const result = {
  wasm_sha256: wasmHash,
  version: versionInfo,
  corner_params: cornerVer ? cornerVer.params : null,
  failures,
  notes,
  default_preview: defaultRun,
  corner_preview: cornerRun,
  exact_custom_target: exactCustom,
  memory_js_heap_bytes: {
    after_init: mem0,
    before_cold: memBeforeCold,
    after_cold: memAfterCold,
    after_corner: memAfterCorner,
  },
  memory_note:
    "performance.memory covers the JS heap only; wasm linear memory is not separately instrumented — native max RSS 194/199 MB is the reference bound.",
  terminated_stale_dropped: terminatedStale,
};
writeFileSync(OUT, JSON.stringify(result, null, 1));
await browser.close();
server.close();
console.log(`browser suite: ${failures.length} failures`);
if (failures.length > 0) process.exit(1);
