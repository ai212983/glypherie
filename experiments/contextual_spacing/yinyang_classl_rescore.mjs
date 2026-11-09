// Class-L staging helper: drives the PINNED shipping WASM bytes only.
//
// Usage:
//   node yinyang_classl_rescore.mjs check
//   node yinyang_classl_rescore.mjs domains BOOT_JSON CURVE_JSON
//   node yinyang_classl_rescore.mjs rescore BOOT_JSON CASE_ID PROFILE PAIRS_JSON OUT_JSON
//   node yinyang_classl_rescore.mjs peaks BOOT_JSON CASE_ID PROFILE OUT_JSON KIND
//
// PAIRS_JSON maps pair -> {metric}. OUT rescore maps pair ->
// {lo, hi, metric, metric_source, steps}, where each step row is
// [step, valid01, gl, both, weak, abst01, reason, skipped, shortfall,
//  bound, faces, corners, maxcos] in the calibration-curve column
// order. No model change, no new scoring semantics: R12/q2/tau 0.5/
// notebook-primary, frozen normalizer 12, TIE derived downstream,
// never applied here (cstar NaN).
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
const EXPECT_WASM = "c27fe2e2c7d53114fbaace7829c6eec13d06e2ee28039b6a18296207dea7f855";

function loadEngine() {
  // Isolated per-process package pair: the generated Node glue loads
  // `${__dirname}/yinyang_oriented_engine_bg.wasm`, so the WASM must sit
  // beside the required copy. Both files come from the module-relative
  // leaf and the bytes are hash-gated here; a shared temp file (or a
  // TMPDIR without one) can never substitute stale bytes.
  const pairDir = mkdtempSync(join(tmpdir(), `yinyang_classl_rescore_${process.pid}_`));
  const wasmBytes = readFileSync(join(LEAF, "pkg-nodejs", "yinyang_oriented_engine_bg.wasm"));
  if (createHash("sha256").update(wasmBytes).digest("hex") !== EXPECT_WASM) {
    console.error("pinned wasm drift");
    process.exit(1);
  }
  const cjsCopy = join(pairDir, "yinyang_oriented_engine.cjs");
  copyFileSync(join(LEAF, "pkg-nodejs", "yinyang_oriented_engine.js"), cjsCopy);
  writeFileSync(join(pairDir, "yinyang_oriented_engine_bg.wasm"), wasmBytes);
  const mod = createRequire(import.meta.url)(cjsCopy);
  const engine = new mod.YinYangEngine(null);
  const version = JSON.parse(engine.version());
  const want = [
    ["model", "yinyangfit-oriented-engine-v1"],
    ["score_model", "yinyangfit-local-energy-v2"],
    ["search", "yinyangfit-search-v2"],
  ];
  for (const [k, v] of want) {
    if (version[k] !== v) {
      console.error(`identity drift: ${k}=${version[k]}`);
      process.exit(1);
    }
  }
  if (version.frozen_normalization_radius !== 12 || version.params.q !== 2.0 || version.params.radius !== 12) {
    console.error("frozen-param drift");
    process.exit(1);
  }
  return engine;
}

function decodeCover(g, gray) {
  const s = g.cover,
    px = new Float64Array(s.length);
  if (gray) {
    for (let i = 0; i < s.length; i++) px[i] = (s.charCodeAt(i) - 48) / 7;
  } else {
    for (let i = 0; i < s.length; i++) px[i] = s[i] === "1" ? 1 : 0;
  }
  return px;
}

function loadBoot(bootPath) {
  return JSON.parse(readFileSync(bootPath, "utf8"));
}

function profOf(boot, caseId, profile) {
  const kase = boot.cases.find((c) => c.id === caseId);
  if (!kase) {
    console.error(`case ${caseId} not found`);
    process.exit(2);
  }
  return { kase, prof: kase.profiles[profile] };
}

function ensure(engine, ds, sha, gray, glyphs, cp) {
  const g = glyphs[String(cp)];
  const px = decodeCover(g, gray);
  const r = JSON.parse(engine.load_glyph(ds, sha, cp, g.w, g.h, g.left, g.top, px));
  return !!r.recomputed;
}

const cmd = process.argv[2];
if (cmd === "check") {
  loadEngine();
  console.log(JSON.stringify({ ok: true, wasm: EXPECT_WASM }));
} else if (cmd === "domains") {
  const boot = loadBoot(process.argv[3]);
  const curve = JSON.parse(readFileSync(process.argv[4], "utf8"));
  const { kase, prof } = profOf(boot, curve.case, curve.profile);
  const gray = curve.profile === "gray";
  const engine = loadEngine();
  const ds = `${curve.case}-${curve.profile}`;
  const glyphs = prof.glyphs;
  let checked = 0,
    mismatched = [];
  for (const key of Object.keys(curve.pairs)) {
    const l = key.codePointAt(0),
      r = key.codePointAt(1);
    ensure(engine, ds, prof.capture_sha256, gray, glyphs, l);
    ensure(engine, ds, prof.capture_sha256, gray, glyphs, r);
    const dom = JSON.parse(engine.search_domain(ds, l, r));
    const rec = curve.pairs[key];
    checked++;
    if (dom.lo !== rec.lo || dom.hi !== rec.hi) {
      mismatched.push({ pair: key, curve: [rec.lo, rec.hi], engine: [dom.lo, dom.hi] });
    }
  }
  console.log(JSON.stringify({ checked, mismatched }));
  if (mismatched.length) process.exit(3);
} else if (cmd === "rescore") {
  const boot = loadBoot(process.argv[3]);
  const caseId = process.argv[4],
    profile = process.argv[5];
  const { prof } = profOf(boot, caseId, profile);
  const gray = profile === "gray";
  const want = JSON.parse(readFileSync(process.argv[6], "utf8"));
  const engine = loadEngine();
  const ds = `${caseId}-${profile}`;
  const glyphs = prof.glyphs;
  const out = {};
  for (const key of Object.keys(want)) {
    const l = key.codePointAt(0),
      r = key.codePointAt(1);
    ensure(engine, ds, prof.capture_sha256, gray, glyphs, l);
    ensure(engine, ds, prof.capture_sha256, gray, glyphs, r);
    const dom = JSON.parse(engine.search_domain(ds, l, r));
    let lo, hi, metric, metricSource;
    if ("lo" in dom) {
      lo = dom.lo;
      hi = dom.hi;
      const m = want[key].metric;
      if (m >= lo && m <= hi) {
        metric = m;
        metricSource = "preview";
      } else {
        metric = lo;
        metricSource = "domain_floor";
      }
      const deltas = new Int32Array(hi - lo + 1);
      for (let s = lo; s <= hi; s++) deltas[s - lo] = s - metric;
      const res = JSON.parse(engine.score_pair_local(ds, l, r, metric, deltas, 0.5, 12, "notebook", NaN));
      out[key] = {
        lo,
        hi,
        metric,
        metric_source: metricSource,
        steps: res.steps.map((s) => [
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
        ]),
      };
    } else {
      const m = want[key].metric;
      ensure(engine, ds, prof.capture_sha256, gray, glyphs, l);
      ensure(engine, ds, prof.capture_sha256, gray, glyphs, r);
      const res = JSON.parse(engine.score_pair_local(ds, l, r, m, new Int32Array([0]), 0.5, 12, "notebook", NaN));
      const s = res.steps[0];
      out[key] = {
        lo: null,
        hi: null,
        metric: m,
        metric_source: "metric_only",
        domain_reason: dom.blank ? "blank_glyph_no_ink" : dom.reason || "unknown",
        steps: [
          [
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
          ],
        ],
      };
    }
  }
  writeFileSync(process.argv[7], JSON.stringify(out));
  console.log(JSON.stringify({ pairs: Object.keys(out).length }));
} else if (cmd === "peaks") {
  const boot = loadBoot(process.argv[3]);
  const caseId = process.argv[4],
    profile = process.argv[5];
  const kind = process.argv[7] || "slate";
  const { prof } = profOf(boot, caseId, profile);
  const gray = profile === "gray";
  const engine = loadEngine();
  const ds = `${caseId}-${profile}`;
  const glyphs = prof.glyphs;
  const peaks = {};
  for (const cp of Object.keys(glyphs)) {
    if (glyphs[cp].w === 0 || glyphs[cp].h === 0) {
      peaks[cp] = { peak: 0, w: 0, h: 0 };
      continue;
    }
    ensure(engine, ds, prof.capture_sha256, gray, glyphs, Number(cp));
    const arr = engine.glyph_component(ds, Number(cp), kind, 0, 0);
    const note = JSON.parse(engine.last_component_note());
    let best = 0;
    for (let i = 0; i < arr.length; i++) {
      const v = arr[i];
      if (v > best) best = v;
    }
    peaks[cp] = { peak: best, w: note.width, h: note.height };
  }
  writeFileSync(process.argv[6], JSON.stringify(peaks));
  console.log(JSON.stringify({ codepoints: Object.keys(peaks).length }));
} else {
  console.error("unknown command");
  process.exit(2);
}
