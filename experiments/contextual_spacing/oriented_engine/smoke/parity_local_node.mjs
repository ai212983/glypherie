// Full wasm32 parity for Class L vs the frozen pilot adapter.
//
// Usage: node smoke/parity_local_node.mjs LOCAL_ADAPTER_JSON PROVENANCE_JSON REPO_ROOT
// Env: MS_TOL (manuscript conditioned gate, default 1e-8),
//      R6_TOL (bars R6 gate, default 1e-5), R6R_TOL (real R6 gate, default 3e-5).
//
// Loads the nodejs package, replicates every parity_local comparison
// (bars synthetic + real capture pairs, R12/R24/R6/q3, both strengths):
// gl/weak/abstain at absolute gates, both exact-or-recorded, bound via
// the flip-linked allowance (both_diff * max_facing_weight). Prints JSON;
// exits nonzero on any failure. Choice checks arrive with the D7
// per-target exporter fields.
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { copyFileSync } from "node:fs";

const [adapterPath, provPath, repoRoot] = process.argv.slice(2);
if (!adapterPath || !provPath || !repoRoot) {
  console.error("usage: node smoke/parity_local_node.mjs LOCAL_ADAPTER_JSON PROVENANCE_JSON REPO_ROOT");
  process.exit(2);
}
const adapter = JSON.parse(readFileSync(adapterPath, "utf8"));
const provenance = JSON.parse(readFileSync(provPath, "utf8"));
const leaf = new URL("..", import.meta.url).pathname;
const G = {
  ms: parseFloat(process.env.MS_TOL ?? "1e-8"),
  r6: parseFloat(process.env.R6_TOL ?? "1e-5"),
  r6r: parseFloat(process.env.R6R_TOL ?? "3e-5"),
};

const cjsCopy = join(tmpdir(), "yinyang_local_parity.cjs");
copyFileSync(join(leaf, "pkg-nodejs", "yinyang_oriented_engine.js"), cjsCopy);
copyFileSync(
  join(leaf, "pkg-nodejs", "yinyang_oriented_engine_bg.wasm"),
  join(tmpdir(), "yinyang_oriented_engine_bg.wasm"),
);
const mod = createRequire(import.meta.url)(cjsCopy);

let failures = [];
let compared = 0;
let worstRel = 0;
let worstShortfall = 0,
  worstShortfallWhere = "";
let maxSkipped = 0,
  maxSkippedWhere = "";
let boundary = [];
let conditioned = [];
function close(got, exp, tol) {
  if (!Number.isFinite(got) || !Number.isFinite(exp)) return got === exp;
  return Math.abs(got - exp) <= tol * Math.max(Math.abs(exp), 1.0);
}
let worstRelWhere = "";
function noteRel(got, exp, wh) {
  const rel = Math.abs(got - exp) / Math.max(Math.abs(exp), 1.0);
  if (rel > worstRel) {
    worstRel = rel;
    worstRelWhere = wh;
  }
}
const MAX_W = 1.0; // max facing weight over the frozen 16-direction bank
const SEED_EXACT = 0.4697315871728616;
function choiceTargets(rows, metric) {
  const elig = rows.filter((st) => st.valid && !st.abstain && Number.isFinite(st.gl)).map((st) => [st.step, st.gl]);
  const targets = [
    ["seed_exact", SEED_EXACT],
    ["seed_rounded", 0.47],
    ["zero", 0.0],
    ["high", 8.0],
  ];
  if (elig.length === 0) {
    targets.push(["unreachable", 5.0]);
  } else {
    const gs = elig.map(([, g]) => g).sort((a, b) => a - b);
    const med = gs[gs.length >> 1];
    const byDev = elig.map(([, g]) => [Math.abs(g - SEED_EXACT), g]).sort((a, b) => a[0] - b[0]);
    const midW = byDev.length > 1 ? (byDev[0][1] + byDev[1][1]) / 2 : byDev[0][1];
    targets.push(["mid_w", midW]);
    targets.push(["mid_lo", (gs[0] + med) / 2]);
    targets.push(["mid_hi", (med + gs[gs.length - 1]) / 2]);
    targets.push(["unreachable", gs[gs.length - 1] + 5.0]);
  }
  return { elig: elig.length > 0, targets };
}

function barCover(trio) {
  const c = new Float64Array(20 * 100);
  for (let y = 4; y < 16; y++) {
    for (let x = 20; x < 22; x++) c[y * 100 + x] = 1.0;
    if (trio) for (let x = 62; x < 64; x++) c[y * 100 + x] = 1.0;
  }
  return c;
}

// One engine per field config (q), like native load_engine_for.
function makeEngine(q) {
  return new mod.YinYangEngine(q === 2 ? null : JSON.stringify({ q }));
}

for (const tag of ["R12", "R24", "R6", "q3"]) {
  const radius = tag === "R6" ? 6 : tag === "R24" ? 24 : 12;
  const strengths = ["notebook", "manuscript"];
  const engine = makeEngine(tag === "q3" ? 3 : 2);
  engine.load_glyph("synthetic", "adapter-bar", 0x41, 100, 20, 0, 0, barCover(false));
  engine.load_glyph("synthetic", "adapter-bar", 0x42, 100, 20, 0, 0, barCover(false));
  engine.load_glyph("synthetic", "adapter-bar", 0x43, 100, 20, 0, 0, barCover(true));
  for (const name of ["pair", "trio"]) {
    const left = name === "pair" ? 0x41 : 0x43;
    const exp = adapter.bars[tag][name];
    for (const strength of strengths) {
      const res = JSON.parse(
        engine.score_pair_local("synthetic", left, 0x42, 0, new Int32Array([6]), 0.5, radius, strength, null),
      );
      const s = res.steps[0];
      const expGl = strength === "manuscript" ? exp.gl_ms : exp.gl;
      const wh = `bars ${tag} ${name} ${strength} gl`;
      compared++;
      const tol = strength === "manuscript" ? (tag === "R6" ? 1e-6 : G.ms) : tag === "R6" ? G.r6 : 1e-9;
      if (strength === "manuscript" || tag === "R6") conditioned.push(wh);
      if (!close(s.gl, expGl, tol)) failures.push(`${wh}: gl ${s.gl} != ${expGl} (tol ${tol})`);
      else noteRel(s.gl, expGl, wh);
      if (strength === "notebook") {
        let bothDiff = 0;
        if (s.both_supported_pairpx !== exp.both) {
          bothDiff = Math.abs(s.both_supported_pairpx - exp.both);
          if (bothDiff <= 64) boundary.push(`${wh}: diff ${bothDiff}`);
          else failures.push(`${wh}: both ${s.both_supported_pairpx} != ${exp.both}`);
        }
        // Weak rides the R6 mechanism gate (wasm32 moves it at 1.3e-6).
        const weakTol = tag === "R6" ? 1e-5 : 1e-9;
        if (!close(s.weak_normalized_share, exp.weak, weakTol))
          failures.push(`${wh}: weak ${s.weak_normalized_share} != ${exp.weak} (tol ${weakTol})`);
        if (s.abstain !== exp.abstain) failures.push(`${wh}: abstain mismatch`);
        const allow = bothDiff * MAX_W + 1e-9;
        if (!(Number.isFinite(s.honest_bound) && Math.abs(s.honest_bound - exp.bound) <= allow))
          failures.push(`${wh}: bound ${s.honest_bound} != ${exp.bound} (allowance ${allow})`);
      }
    }
  }
}

// Real capture pairs.
for (const [dsName, pairs] of Object.entries(adapter.real)) {
  const info = provenance.captures[dsName];
  const capPath = resolve(repoRoot, info.path);
  const bytes = readFileSync(capPath);
  const actual = createHash("sha256").update(bytes).digest("hex");
  if (actual !== info.sha256) {
    failures.push(`${dsName}: capture drift`);
    continue;
  }
  const text = bytes.toString("utf8");
  const cap = JSON.parse(text);
  // Same branch as Rust load_capture: mono v1 has a top-level glyph
  // list with bitmap cells, gray has font.glyphs (pixels 0..7 -> /7).
  let glyphs, gray;
  if (text.includes('"contextual-spacing-capture-v1"')) {
    gray = false;
    glyphs = new Map(
      cap.glyphs.map((g) => [
        g.codepoint,
        {
          width: g.bitmap.width,
          height: g.bitmap.height,
          left: g.bitmap.left,
          top: g.bitmap.top,
          pixels: g.bitmap.pixels,
        },
      ]),
    );
  } else {
    gray = true;
    glyphs = new Map(cap.font.glyphs.map((g) => [g.codepoint, g]));
  }
  const coverOf = (cp) => {
    const g = glyphs.get(cp);
    const px = new Float64Array(g.width * g.height);
    for (let i = 0; i < px.length; i++) px[i] = gray ? g.pixels[i] / 7.0 : g.pixels[i] > 0 ? 1.0 : 0.0;
    return { g, px };
  };
  for (const [pair, cell] of Object.entries(pairs)) {
    const l = pair.codePointAt(0),
      r = pair.codePointAt(1);
    const metric = cell.metric;
    for (const pass of [
      { key: "steps", radius: 12 },
      { key: "steps_R6", radius: 6 },
    ]) {
      const engine = makeEngine(2);
      const A = coverOf(l),
        B = coverOf(r);
      engine.load_glyph(dsName, info.sha256, l, A.g.width, A.g.height, A.g.left, A.g.top, A.px);
      engine.load_glyph(dsName, info.sha256, r, B.g.width, B.g.height, B.g.left, B.g.top, B.px);
      const r6vals = [],
        r6exp = [];
      for (const st of cell[pass.key]) {
        const wh = `${dsName} ${pair} step ${st.step} R${pass.radius === 6 ? 6 : 12}`;
        const delta = st.step - metric;
        const res = JSON.parse(
          engine.score_pair_local(dsName, l, r, metric, new Int32Array([delta]), 0.5, pass.radius, "notebook", null),
        );
        const s = res.steps[0];
        compared++;
        if (s.valid !== st.valid) {
          failures.push(`${wh}: valid ${s.valid} != ${st.valid}`);
          continue;
        }
        if (!s.valid) continue;
        const tol = pass.radius === 6 ? G.r6r : 1e-9;
        if (pass.radius === 6) conditioned.push(`${wh} gl`);
        if (!close(s.gl, st.gl, tol)) failures.push(`${wh}: gl ${s.gl} != ${st.gl} (tol ${tol})`);
        else noteRel(s.gl, st.gl, wh);
        let bothDiff = 0;
        if (s.both_supported_pairpx !== st.both) {
          bothDiff = Math.abs(s.both_supported_pairpx - st.both);
          const capN = pass.radius === 6 ? 1024 : 64;
          if (bothDiff <= capN) boundary.push(`${wh}: diff ${bothDiff}`);
          else failures.push(`${wh}: both ${s.both_supported_pairpx} != ${st.both}`);
        }
        if (s.abstain !== st.abstain) failures.push(`${wh}: abstain mismatch`);
        if (pass.key === "steps") {
          const allow = bothDiff * MAX_W + 1e-9;
          if (!(Number.isFinite(s.honest_bound) && Math.abs(s.honest_bound - st.bound) <= allow))
            failures.push(`${wh}: bound ${s.honest_bound} != ${st.bound} (allowance ${allow})`);
          if (st.weak !== null && st.weak !== undefined && !close(s.weak_normalized_share ?? NaN, st.weak, 1e-9))
            failures.push(`${wh}: weak ${s.weak_normalized_share} != ${st.weak}`);
        }
        if (pass.key === "steps_R6" && s.valid && !s.abstain && Number.isFinite(s.gl) && Number.isFinite(st.gl)) {
          r6vals.push([st.step, s.gl]);
          r6exp.push([st.step, st.gl]);
        }
        if (s.conditioning_shortfall > worstShortfall) {
          worstShortfall = s.conditioning_shortfall;
          worstShortfallWhere = wh;
        }
        if ((s.skipped_nonpositive ?? 0) > maxSkipped) {
          maxSkipped = s.skipped_nonpositive;
          maxSkippedWhere = wh;
        }
      }
      // Raw-gl argmin parity over the wide window (observed fixture
      // property, not a selection certificate).
      if (pass.key === "steps_R6" && r6vals.length > 0) {
        const argmin = (a) => a.reduce((m, v) => (v[1] < m[1] ? v : m))[0];
        if (argmin(r6vals) !== argmin(r6exp))
          failures.push(`${dsName} ${pair} R6 argmin ${argmin(r6vals)} != ${argmin(r6exp)}`);
      }
      // True target-choice parity through the real selection path
      // (TIE-faithful: a pick inside the other side's tied band agrees).
      {
        const ckey = pass.key === "steps" ? "choices" : "choices_R6";
        const { elig, targets } = choiceTargets(cell[pass.key], metric);
        void elig;
        const allDeltas = new Int32Array(cell[pass.key].map((st) => st.step - metric));
        for (const [tname, cstar] of targets) {
          const res = JSON.parse(
            engine.score_pair_local(dsName, l, r, metric, allDeltas, 0.5, pass.radius, "notebook", cstar),
          );
          const exp = cell[ckey][tname];
          compared++;
          const tiebreakOk = Math.min(...res.minimizing) === res.chosen;
          const ok = res.fallback === exp.fallback && (res.fallback || (exp.tied.includes(res.chosen) && tiebreakOk));
          if (ok && !res.fallback && res.chosen !== exp.chosen)
            boundary.push(
              `${dsName} ${pair} ${pass.key} choice/${tname}: ` +
                `flip within tied band (wasm32 ${res.chosen} vs ref ${exp.chosen})`,
            );
          if (!ok)
            failures.push(
              `${dsName} ${pair} ${pass.key} choice/${tname}: ` +
                `chosen ${res.chosen} band ${JSON.stringify(res.minimizing)} fallback ${res.fallback} ` +
                `!= ${exp.chosen} ${JSON.stringify(exp.tied)} ${exp.fallback}`,
            );
        }
      }
    }
  }
}

console.log(
  JSON.stringify({
    pass: failures.length === 0,
    failures,
    compared_steps: compared,
    worst_rel: worstRel,
    worst_rel_where: worstRelWhere,
    worst_shortfall: worstShortfall,
    worst_shortfall_where: worstShortfallWhere,
    max_skipped_nonpositive: maxSkipped,
    max_skipped_where: maxSkippedWhere,
    conditioned,
    boundary_notes: boundary,
    gates: G,
  }),
);
if (failures.length > 0) process.exit(1);
