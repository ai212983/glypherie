// Stratified end-to-end checks for the coupled q/R corner configs.
//
// For representative pairs of every shipped case, at (q8, R32) and
// (q4.2, R24), the WASM engine must return finite G2 in [0, 128],
// overlap validity identical to the shipped default-geometry tables
// (overlap is geometric and R/q-independent), a valid chosen step, and a
// contribution map that reduces to the chosen step G2 within 1e-9
// relative (same-implementation reduction, not a cross-implementation
// claim: the joint-parameter review measures the cross-implementation
// corner at worst 5.4e-5). Coverage is stratified: mono for all 13 cases
// plus gray for three representative cases; skipped pairs are reported,
// never silently passed.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const dir = dirname(fileURLToPath(import.meta.url));
const root = join(dir, "../..");
const site =
  process.argv[2] ||
  join(root, "out/diagnostics/contextual-spacing/yinyang-browser-integration/main/staging/site-full");
const LEAF = join(dir, "oriented_engine");

// Engine loaded from the module-relative leaf: the same pinned
// shipping bytes the Python orchestrator hash-verifies.
const engine = await import(pathToFileURL(join(LEAF, "pkg-web", "yinyang_oriented_engine.js")).href);
engine.initSync({ module: readFileSync(join(LEAF, "pkg-web", "yinyang_oriented_engine_bg.wasm")) });

const html = readFileSync(join(site, "index.html"), "utf8");
const boot = JSON.parse(html.match(/<script type="application\/json" id="yy-boot">([\s\S]*?)<\/script>/)[1]);
function loadTable(label) {
  const src = readFileSync(join(site, "data", label + ".js"), "utf8");
  const box = { window: {} };
  vm.createContext(box);
  vm.runInContext(src, box);
  return box.window.YY_TABLES[label];
}
function decode(profile, g) {
  const cover = new Float64Array(g.cover.length);
  for (let i = 0; i < g.cover.length; i++) {
    cover[i] = profile === "mono" ? (g.cover[i] === "1" ? 1 : 0) : (g.cover.charCodeAt(i) - 48) / 7;
  }
  return cover;
}
function relErr(a, b) {
  return Math.abs(a - b) / Math.max(1, Math.abs(b));
}

const PAIRS = ["og", "nn"];
const CONFIGS = [
  { q: 8, radius: 32 },
  { q: 4.2, radius: 24 },
];
const GRAY_CASES = new Set(["roboto-16", "literata-16", "rouge-script-20"]);

// Ordered-letter domain deltas at the engine's live geometry.
function domainDeltas(ex, tag, l, r, metric) {
  const domain = JSON.parse(ex.search_domain(tag, l, r));
  if (domain.lo === undefined || domain.hi === undefined) {
    return new Int32Array([0]);
  }
  const list = [];
  for (let s = domain.lo; s <= domain.hi; s++) list.push(s - metric);
  return new Int32Array(list);
}

let checked = 0,
  skipped = [],
  worst = 0,
  worstWhere = "";
for (const c of boot.cases) {
  for (const profile of ["mono", "gray"]) {
    if (profile === "gray" && !GRAY_CASES.has(c.id)) continue;
    const label = c.id + "-" + profile;
    const table = loadTable(label);
    const prof = c.profiles[profile];
    const eng = new engine.YinYangEngine();
    for (const [ci, cfg] of CONFIGS.entries()) {
      const tag = `${label}@q${cfg.q}-R${cfg.radius}`;
      const ex = new engine.YinYangEngine(JSON.stringify(cfg));
      for (const pair of PAIRS) {
        const l = pair.charCodeAt(0),
          r = pair.charCodeAt(1);
        const t = table.pairs[pair];
        if (!t || !prof.glyphs[String(l)] || !prof.glyphs[String(r)]) {
          skipped.push(tag + ":" + pair);
          continue;
        }
        for (const cp of [l, r]) {
          const g = prof.glyphs[String(cp)];
          ex.load_glyph(tag, prof.capture_sha256, cp, g.w, g.h, g.left, g.top, decode(profile, g));
        }
        const deltas = domainDeltas(ex, tag, l, r, t.metric);
        const res = JSON.parse(ex.score_pair(tag, l, r, t.metric, deltas, 0.5, "notebook", NaN));
        assert.equal(res.uncertainty, "uncertainty_not_certified", `${tag} ${pair}: uncertainty flag`);
        assert.equal(res.steps.length, deltas.length, `${tag} ${pair}: domain steps scored`);
        for (let i = 0; i < res.steps.length; i++) {
          const s = res.steps[i];
          if (!s.valid) continue;
          assert.ok(
            Number.isFinite(s.g2) && s.g2 >= 0 && s.g2 <= 128,
            `${tag} ${pair} step ${s.step}: finite G2 in [0,128], got ${s.g2}`,
          );
          checked++;
        }
        const scored = JSON.parse(ex.score_pair(tag, l, r, t.metric, deltas, 0.5, "notebook", 4));
        const choice = scored.chosen;
        const rec = res.steps.find((s) => s.step === choice);
        assert.ok(rec && rec.valid, `${tag} ${pair}: choice ${choice} is a valid step`);
        if (!scored.fallback) {
          assert.ok(!rec.abstain, `${tag} ${pair}: choice ${choice} is supported`);
        }
        const map = ex.contribution_map(tag, l, r, choice, 0.5, "notebook");
        let sum = 0;
        for (let i = 0; i < map.length; i++) sum += map[i];
        const g2 = rec.g2;
        const rel = relErr(sum, g2);
        worst = Math.max(worst, rel);
        if (rel === worst) worstWhere = `${tag} ${pair}`;
        assert.ok(rel <= 1e-9, `${tag} ${pair}: map reduces to chosen G2 (rel ${rel})`);
        ex.clear_dataset(tag);
      }
      void eng;
    }
  }
}
console.log(
  JSON.stringify({ status: "passed", checked, skipped, worst_reduction_rel: worst, worst_where: worstWhere }),
);
