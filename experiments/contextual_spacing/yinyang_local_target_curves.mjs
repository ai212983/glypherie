// Full-domain Class-L curve exporter for the target-calibration study.
//
// Own driver for the yinyang_local_target study. Reads the frozen page boot
// catalogue (cases/lines/glyphs/preview metrics only), drives the PINNED
// shipping WASM bytes (hash verified by the Python orchestrator, never
// re-pointed here), notebook-primary strength, frozen R12/q2/tau, and writes
// one JSON curve file per dataset. No selection target is applied
// (cstar NaN): every target response is derived downstream from these
// curves through the frozen TIE-v2 rule, so scoring runs exactly once.
//
// Usage: node yinyang_local_target_curves.mjs BOOT_JSON CASE_ID PROFILE OUT_JSON
import { readFileSync, writeFileSync } from "node:fs";
import { copyFileSync, mkdtempSync } from "node:fs";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

// Module-relative engine root: the pinned shipping WASM bytes live
// beside this helper, never at an author-machine absolute path.
const LEAF = join(dirname(fileURLToPath(import.meta.url)), "oriented_engine");
const BOOT = process.argv[2],
  CASE_ID = process.argv[3],
  PROFILE = process.argv[4],
  OUT = process.argv[5];
if (!BOOT || !CASE_ID || !PROFILE || !OUT) {
  console.error("usage: node yinyang_local_target_curves.mjs BOOT_JSON CASE_ID PROFILE OUT_JSON");
  process.exit(2);
}
if (PROFILE !== "mono" && PROFILE !== "gray") {
  console.error("PROFILE must be mono or gray");
  process.exit(2);
}
const gray = PROFILE === "gray";

// Isolated per-process package pair: the generated Node glue loads
// `${__dirname}/yinyang_oriented_engine_bg.wasm`, so the WASM must sit
// beside the required copy. Both files come from the module-relative
// leaf and the bytes are hash-gated here; no shared temp filename is
// used across runs.
const EXPECT_WASM = "c27fe2e2c7d53114fbaace7829c6eec13d06e2ee28039b6a18296207dea7f855";
const pairDir = mkdtempSync(join(tmpdir(), `yinyang_target_curves_${process.pid}_`));
const wasmBytes = readFileSync(join(LEAF, "pkg-nodejs", "yinyang_oriented_engine_bg.wasm"));
if (createHash("sha256").update(wasmBytes).digest("hex") !== EXPECT_WASM) {
  console.error("pinned wasm drift");
  process.exit(1);
}
const cjsCopy = join(pairDir, "yinyang_oriented_engine.cjs");
copyFileSync(join(LEAF, "pkg-nodejs", "yinyang_oriented_engine.js"), cjsCopy);
writeFileSync(join(pairDir, "yinyang_oriented_engine_bg.wasm"), wasmBytes);
const mod = createRequire(import.meta.url)(cjsCopy);

const boot = JSON.parse(readFileSync(BOOT, "utf8"));
const kase = boot.cases.find((c) => c.id === CASE_ID);
if (!kase) {
  console.error(`case ${CASE_ID} not found`);
  process.exit(2);
}
const prof = kase.profiles[PROFILE];
const glyphs = prof.glyphs;
const lines = prof.lines;

const engine = new mod.YinYangEngine(null);
const version = JSON.parse(engine.version());
for (const [k, want] of [
  ["model", "yinyangfit-oriented-engine-v1"],
  ["score_model", "yinyangfit-local-energy-v2"],
  ["search", "yinyangfit-search-v2"],
]) {
  if (version[k] !== want) {
    console.error(`identity drift: ${k}=${version[k]}`);
    process.exit(1);
  }
}
if (version.frozen_normalization_radius !== 12 || version.params.q !== 2.0 || version.params.radius !== 12) {
  console.error("frozen-param drift");
  process.exit(1);
}

const ds = `${CASE_ID}-${PROFILE}`;
const sha = prof.capture_sha256;
const coverOf = (cp) => {
  const g = glyphs[String(cp)];
  const px = new Float64Array(g.cover.length);
  for (let i = 0; i < px.length; i++) {
    px[i] = gray ? Number(g.cover[i]) / 7.0 : g.cover[i] === "1" ? 1.0 : 0.0;
  }
  return { g, px };
};

// Frozen preview metrics per pair (first occurrence wins), spaces excluded.
const previewMetric = new Map();
if (Array.isArray(prof.preview)) {
  for (const line of prof.preview) {
    for (const gap of line.gaps) {
      if (gap.space) continue;
      const pair = gap.pair;
      const key = pair[0] + pair[1];
      if (!previewMetric.has(key)) previewMetric.set(key, gap.metric);
    }
  }
}

const pairs = [];
const seen = new Set();
let nText = 0,
  nSpace = 0;
for (const line of lines) {
  const ch = [...line];
  for (let i = 0; i + 1 < ch.length; i++) {
    const a = ch[i],
      b = ch[i + 1];
    if (a === " " || b === " ") {
      nSpace++;
      continue;
    }
    nText++;
    const key = a + b;
    if (seen.has(key)) continue;
    if (!(String(a.codePointAt(0)) in glyphs) || !(String(b.codePointAt(0)) in glyphs)) continue;
    seen.add(key);
    pairs.push([a.codePointAt(0), b.codePointAt(0)]);
  }
}

// The glyph LRU holds 32 entries, so big cases churn: ensure-load both
// sides before every domain and scoring call (identical bytes only
// re-touch; evicted glyphs rebuild fields). Reloads are counted.
let nReloads = 0,
  reloadMs = 0;
const ensure = (cp) => {
  const { g, px } = coverOf(cp);
  const t = Date.now();
  const r = JSON.parse(engine.load_glyph(ds, sha, cp, g.w, g.h, g.left, g.top, px));
  reloadMs += Date.now() - t;
  if (r.recomputed) nReloads++;
};
const tLoad0 = Date.now();
{
  const need = new Set();
  for (const [l, r] of pairs) {
    need.add(l);
    need.add(r);
  }
  for (const cp of need) ensure(cp);
}
const loadMs = Date.now() - tLoad0;

const tDom0 = Date.now();
const work = [];
let nNoDomain = 0;
const noDomainReasons = {};
for (const [l, r] of pairs) {
  ensure(l);
  ensure(r);
  const dom = JSON.parse(engine.search_domain(ds, l, r));
  if (!("lo" in dom)) {
    nNoDomain++;
    const why = dom.blank ? "blank" : dom.reason || "unknown";
    noDomainReasons[why] = (noDomainReasons[why] || 0) + 1;
    continue;
  }
  const key = String.fromCodePoint(l) + String.fromCodePoint(r);
  const pm = previewMetric.get(key);
  const metric = pm !== undefined && pm >= dom.lo && pm <= dom.hi ? pm : dom.lo;
  work.push({
    l,
    r,
    lo: dom.lo,
    hi: dom.hi,
    metric,
    metricSource: pm !== undefined && pm >= dom.lo && pm <= dom.hi ? "preview" : "domain_floor",
  });
}
const domainMs = Date.now() - tDom0;

const tScore0 = Date.now();
const pairRecs = {};
let nSteps = 0,
  nValid = 0;
for (const w of work) {
  // Deltas are relative: the engine scores step = metric + d, so the
  // scored window is exactly the absolute search-v2 domain [lo, hi].
  ensure(w.l);
  ensure(w.r);
  const deltas = [];
  for (let s = w.lo; s <= w.hi; s++) deltas.push(s - w.metric);
  const res = JSON.parse(
    engine.score_pair_local(ds, w.l, w.r, w.metric, new Int32Array(deltas), 0.5, 12, "notebook", NaN),
  );
  const steps = res.steps.map((s) => [
    s.step,
    s.valid ? 1 : 0,
    s.gl ?? null,
    s.both_supported_pairpx ?? 0,
    s.weak_normalized_share ?? null,
    s.abstain ? 1 : 0,
    s.abstain_reason ?? null,
    s.skipped_nonpositive ?? 0,
    s.conditioning_shortfall ?? 0,
    s.honest_bound ?? null,
    s.faces ?? 0,
    s.corners ?? 0,
    s.max_term_cosine ?? null,
  ]);
  nSteps += steps.length;
  for (const s of res.steps) if (s.valid) nValid++;
  const key = String.fromCodePoint(w.l) + String.fromCodePoint(w.r);
  pairRecs[key] = { lo: w.lo, hi: w.hi, metric: w.metric, metric_source: w.metricSource, steps };
}
const scoreMs = Date.now() - tScore0;

writeFileSync(
  OUT,
  JSON.stringify({
    case: CASE_ID,
    profile: PROFILE,
    dataset: ds,
    capture_sha256: sha,
    gray,
    normalization_radius: 12,
    tau: 0.5,
    strength: "notebook",
    engine_version: version,
    n_text_pairs: nText,
    n_space_adjacent: nSpace,
    n_unique_pairs: pairs.length,
    n_scored_pairs: work.length,
    n_no_domain: nNoDomain,
    no_domain_reasons: noDomainReasons,
    n_domain_steps: nSteps,
    n_valid_steps: nValid,
    n_reload_recomputes: nReloads,
    ms: { load: loadMs, domain: domainMs, score: scoreMs, reload: reloadMs },
    pairs: pairRecs,
  }),
);
console.log(
  JSON.stringify({ case: CASE_ID, profile: PROFILE, pairs: work.length, steps: nSteps, valid: nValid, ms: scoreMs }),
);
