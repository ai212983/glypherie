// Focused checks for the Class-L staged site (no browser).
// Static: identities, navigation settings, G2-absence, coverage, entry
// shape, TIE spot parity, frozen pre-adoption fixture pins, and the
// current adopted main identity. Engine: pinned-shipping
// WASM parity on samples (bitwise gl/both/abstain), metric identity,
// and contribution-map reduction at shipped defaults.
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { copyFileSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const dir = dirname(fileURLToPath(import.meta.url));
const root = join(dir, "../..");
const stage = resolve(
  root,
  process.argv[2] || "out/diagnostics/contextual-spacing/yinyang-normalization-repair/page-staging",
);
const live = join(root, "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/site-reviewed");
// Frozen pre-adoption fixture: the archived original main. Pre-adoption
// freeze asserts and staged-vs-baseline comparisons read this, never the
// adopted page; active checks against the current main identity follow.
const frozen = join(
  root,
  "out/diagnostics/contextual-spacing/yinyang-normalization-repair/adoption/archive-main-pre-classl",
);
const leaf = join(dir, "oriented_engine");

const boot = JSON.parse(readFileSync(join(stage, "boot.json"), "utf8"));
const manifest = JSON.parse(readFileSync(join(stage, "manifest.json"), "utf8"));

// ---- identities ----
assert.equal(boot.model, "yinyangfit-oriented-engine-v1");
assert.equal(boot.score_model, "yinyangfit-local-energy-v2");
assert.equal(manifest.score_model, "yinyangfit-local-energy-v2");
assert.equal(boot.search_policy, "yinyangfit-search-v2");
assert.equal(boot.settings_version, "v3-settings-2026-11-05-classl");
assert.equal(boot.implementation.wasm_sha256, manifest.implementation.wasm_sha256);
// Embedded page bytes hash to the boot pin (page integrity, any site).
{
  const html = readFileSync(join(stage, "index.html"), "utf8");
  const m = html.match(/id="yy-wasm-b64"[^>]*>([^<]*)</);
  assert.ok(m, "embedded wasm present");
  const embedded = Buffer.from(m[1].replace(/\s+/g, ""), "base64");
  assert.equal(createHash("sha256").update(embedded).digest("hex"), boot.implementation.wasm_sha256);
}
assert.equal(boot.fast_geometry.reach, 12.0);
assert.equal(boot.fast_geometry.falloff, 2.0);
assert.deepEqual(boot.gains, { slate: 6.0, contrib: 4.0 });

// ---- navigation settings ----
assert.equal(boot.controls.target.length, 1001);
assert.equal(boot.controls.target[0], 0.0);
assert.equal(boot.controls.target[boot.controls.target.length - 1], 20.0);
assert.ok(Math.abs(boot.controls.target[1] - boot.controls.target[0] - 0.02) < 1e-9);
assert.deepEqual(boot.default_setting, { target: 8.0, reach: 12, falloff: 2.0 });
assert.deepEqual(boot.numeric, { target: [0.0, null], reach: [1, 32], falloff: [0.25, 16.0] });
assert.ok(boot.controls.reach[0] === 4.0 && boot.controls.reach.at(-1) === 24.0);
assert.ok(boot.controls.falloff[0] === 0.5 && boot.controls.falloff.at(-1) === 10.0);

// ---- staged sources: no G2 reuse, no old oracle wiring ----
const src = {};
for (const n of ["app", "wiring", "worker", "coupling", "visual"]) {
  src[n] = readFileSync(join(dir, `yinyangfit_interactive_v3_${n}.js`), "utf8");
}
const template = readFileSync(join(dir, "yinyangfit_interactive_v3_template.html"), "utf8");
for (const [n, c] of Object.entries(src)) {
  for (const stale of ["score_pair(", "contribution_map(", "entry.inter", ".formatG2("]) {
    assert.ok(!c.includes(stale), `${n} carries G2 residue: ${stale}`);
  }
  assert.ok(!c.includes("title="), `${n} adds native title`);
}
const visible = template.replace(/<script[\s\S]*?<\/script>/g, "");
for (const stale of ["Target score", "G2", "0..128", "C*", "tighter", "Standard", "Extended"]) {
  assert.ok(!visible.includes(stale), `visible flow carries stale wording: ${stale}`);
}
assert.ok(visible.includes("Interaction target"), "target control not labeled");
// Old pair/About sections stay removed; compare + selection stay.
assert.ok(!/About|pair inspector/i.test(visible), "no About/pair sections");
assert.ok(visible.includes("Compare spacing"), "compare section retained");
assert.ok(visible.includes("How spacing is selected"), "selection section retained");
// No-wrap + horizontal scroll retained on the text entry.
const html = readFileSync(join(stage, "index.html"), "utf8");
assert.ok(html.includes('wrap="off"'), "textarea no-wrap retained");

// ---- staged-vs-frozen-baseline identity (pre-adoption record) ----
const liveBoot = JSON.parse(readFileSync(join(frozen, "boot.json"), "utf8"));
assert.equal(boot.cases.length, liveBoot.cases.length);
for (const c of boot.cases) {
  const lc = liveBoot.cases.find((x) => x.id === c.id);
  assert.ok(lc, `${c.id} retained`);
  assert.equal(c.text, lc.text, `${c.id} text`);
  assert.equal(c.text_sha256, lc.text_sha256);
  for (const p of ["mono", "gray"]) {
    assert.equal(c.profiles[p].capture_sha256, lc.profiles[p].capture_sha256, `${c.id} ${p} capture`);
    assert.equal(c.profiles[p].lines.join("\n"), lc.profiles[p].lines.join("\n"));
    assert.deepEqual(c.profiles[p].space_metrics, lc.profiles[p].space_metrics);
    assert.deepEqual(c.profiles[p].captured, lc.profiles[p].captured, `${c.id} ${p} source baseline`);
  }
}
// Pixels verbatim on one dataset; preview re-derived (not copied).
{
  const label = "roboto-16-mono";
  const t = loadTable(label);
  const liveText = readFileSync(join(frozen, "data", `${label}.js`), "utf8");
  const liveTable = JSON.parse(
    JSON.stringify(vm.runInNewContext(`${liveText};window.YY_TABLES[${JSON.stringify(label)}];`, { window: {} })),
  );
  assert.deepEqual(t.advances, liveTable.advances, "source metrics identical");
  assert.deepEqual(t.kern, liveTable.kern || {}, "source kerning identical");
  const kase = boot.cases.find((c) => c.id === "roboto-16");
  const lc = liveBoot.cases.find((c) => c.id === "roboto-16");
  assert.deepEqual(kase.profiles.mono.glyphs, lc.profiles.mono.glyphs, "source pixels identical");
  const stagedFirst = kase.profiles.mono.preview[0].gaps[0].chosen;
  const liveFirst = lc.profiles.mono.preview[0].gaps[0].chosen;
  assert.ok(stagedFirst !== undefined && liveFirst !== undefined);
  const stagedAny = kase.profiles.mono.preview.flatMap((l) => l.gaps.map((g) => g.chosen)).join(",");
  const liveAny = lc.profiles.mono.preview.flatMap((l) => l.gaps.map((g) => g.chosen)).join(",");
  assert.ok(stagedAny !== liveAny, "preview re-derived from Class-L (not copied)");
}

// ---- tables: coverage, shape, model ----
function loadTable(label) {
  const text = readFileSync(join(stage, "data", `${label}.js`), "utf8");
  const sandbox = { window: {} };
  vm.runInNewContext(text, sandbox);
  return JSON.parse(JSON.stringify(sandbox.window.YY_TABLES[label]));
}
assert.equal(boot.cases.length, 13);
const labels = [];
for (const c of boot.cases) for (const p of ["mono", "gray"]) labels.push(`${c.id}-${p}`);
assert.equal(labels.length, 26);
const LS = (() => {
  const sandbox = {};
  sandbox.self = sandbox;
  vm.runInNewContext(readFileSync(join(dir, "yinyangfit_interactive_v3_app.js"), "utf8"), sandbox);
  return sandbox.LetterSpacing;
})();
let pairCount = 0;
for (const label of labels) {
  const t = loadTable(label);
  assert.equal(t.score_model, "yinyangfit-local-energy-v2", `${label} score identity`);
  assert.equal(t.search_policy, "yinyangfit-search-v2");
  assert.equal(t.geometry.normalization_radius, 12);
  assert.equal(t.geometry.reach, 12);
  assert.equal(t.geometry.falloff, 2.0);
  const kase = boot.cases.find((c) => label.startsWith(c.id + "-"));
  const prof = kase.profiles[label.endsWith("mono") ? "mono" : "gray"];
  const need = new Set();
  for (const line of prof.lines)
    for (let i = 0; i + 1 < line.length; i++) {
      if (line[i] !== " " && line[i + 1] !== " ") need.add(line[i] + line[i + 1]);
    }
  for (const fx of ["nn", "HH", "ll"]) {
    if (prof.glyphs[String(fx.codePointAt(0))] && prof.glyphs[String(fx.codePointAt(1))]) need.add(fx);
  }
  for (const name of need) assert.ok(t.pairs[name], `${label} missing ${name}`);
  for (const [name, rec] of Object.entries(t.pairs)) {
    pairCount++;
    assert.equal(rec.steps.length, rec.geo.ok.length, `${label} ${name} shape`);
    for (const k of ["gl", "both", "abst", "why", "areason", "weak", "skip", "short", "bound", "fa", "co"]) {
      assert.equal(rec.geo[k].length, rec.steps.length, `${label} ${name}.${k}`);
    }
    assert.ok(!("inter" in rec.geo || "raw" in rec.geo || "fsh" in rec.geo), `${label} ${name} G2 fields`);
    rec.geo.gl.forEach((v, i) => {
      if (rec.geo.ok[i]) assert.ok(typeof v === "number" && isFinite(v), `${label} ${name}@${i} gl`);
      else assert.equal(v, null);
    });
    assert.equal(rec.search.policy, "yinyangfit-search-v2");
  }
  // TIE spot parity through the staged browser module.
  for (const [name, rec] of Object.entries(t.pairs)) {
    const decided = LS.chosenStep(
      { metric: rec.metric, steps: rec.steps, geo: { d: rec.geo }, search: rec.search },
      "d",
      8.0,
    );
    assert.equal(decided.step, t.spot.default[name], `${label} ${name} default choice`);
  }
  for (const [name, grid] of Object.entries(t.spot.pinned)) {
    const rec = t.pairs[name];
    grid.forEach((want, i) => {
      const target = t.spot.target_grid[i];
      const decided = LS.chosenStep(
        { metric: rec.metric, steps: rec.steps, geo: { d: rec.geo }, search: rec.search },
        "d",
        target,
      );
      assert.equal(decided.step, want, `${label} ${name}@${target}`);
    });
  }
  // Band edges: zero exact, slider end, and far outside all run.
  {
    const t = loadTable("roboto-16-mono");
    for (const target of [0, 20, 34.26]) {
      let fallbacks = 0,
        outside = 0;
      for (const rec of Object.values(t.pairs)) {
        const d = LS.chosenStep(
          { metric: rec.metric, steps: rec.steps, geo: { d: rec.geo }, search: rec.search },
          "d",
          target,
        );
        assert.ok(rec.steps.includes(d.step), `choice in domain @${target}`);
        if (d.fallback) fallbacks++;
        if (d.targetOutside) outside++;
      }
      assert.ok(fallbacks === 0, `no fallbacks @${target} (got ${fallbacks})`);
      if (target === 34.26) assert.ok(outside > 0, "far target flags outside band");
    }
  }
  // Metric identity: preview/metric_step anchors reproduce source metric.
  const metricOf = (a, b) => {
    const adv = t.advances[String(a.codePointAt(0))];
    const adj = t.kern[`${a.codePointAt(0)}/${b.codePointAt(0)}`] || 0;
    return adv + adj >= 0 ? Math.floor(adv + adj + 0.5) : Math.ceil(adv + adj - 0.5);
  };
  for (const [name, rec] of Object.entries(t.pairs)) {
    const src = t.pair_metric_source[name];
    if (src === "metric_step" || src === "preview") {
      assert.equal(rec.metric, metricOf(name[0], name[1]), `${label} ${name} metric (${src})`);
    }
  }
}
assert.equal(pairCount, manifest.table_pairs);

// ---- engine parity on shipping bytes ----
const cjsCopy = join(tmpdir(), `yinyang_classl_stage_test_${process.pid}.cjs`);
copyFileSync(join(leaf, "pkg-nodejs", "yinyang_oriented_engine.js"), cjsCopy);
const mod = createRequire(import.meta.url)(cjsCopy);
const engine = new mod.YinYangEngine(null);
const version = JSON.parse(engine.version());
assert.equal(version.score_model, "yinyangfit-local-energy-v2");
assert.equal(version.frozen_normalization_radius, 12);

function decodeCover(g, gray) {
  const s = g.cover,
    px = new Float64Array(s.length);
  if (gray) for (let i = 0; i < s.length; i++) px[i] = (s.charCodeAt(i) - 48) / 7;
  else for (let i = 0; i < s.length; i++) px[i] = s[i] === "1" ? 1 : 0;
  return px;
}
function ensure(ds, sha, gray, glyphs, cp) {
  const g = glyphs[String(cp)];
  engine.load_glyph(ds, sha, cp, g.w, g.h, g.left, g.top, decodeCover(g, gray));
}
function checkPairs(label, names) {
  const t = loadTable(label);
  const kase = boot.cases.find((c) => label.startsWith(c.id + "-"));
  const profile = label.endsWith("mono") ? "mono" : "gray";
  const prof = kase.profiles[profile];
  const gray = profile === "gray";
  const glyphs = prof.glyphs;
  for (const name of names) {
    const rec = t.pairs[name];
    const l = name.codePointAt(0),
      r = name.codePointAt(1);
    ensure(label, prof.capture_sha256, gray, glyphs, l);
    ensure(label, prof.capture_sha256, gray, glyphs, r);
    const deltas = new Int32Array(rec.steps.map((s) => s - rec.metric));
    const res = JSON.parse(engine.score_pair_local(label, l, r, rec.metric, deltas, 0.5, 12, "notebook", NaN));
    assert.equal(res.steps.length, rec.steps.length, `${label} ${name} step count`);
    res.steps.forEach((s, i) => {
      assert.equal(s.valid, !!rec.geo.ok[i], `${label} ${name}@${s.step} valid`);
      if (rec.geo.ok[i]) {
        assert.equal(s.gl, rec.geo.gl[i], `${label} ${name}@${s.step} gl bitwise`);
        assert.equal(s.both_supported_pairpx, rec.geo.both[i]);
      }
      assert.equal(!!s.abstain, !!rec.geo.abst[i]);
    });
  }
}
// Pinned pairs everywhere (includes the 78 rescored records) + two full datasets.
for (const label of labels) checkPairs(label, ["nn", "HH", "ll"]);
{
  const t = loadTable("roboto-16-mono");
  checkPairs("roboto-16-mono", Object.keys(t.pairs));
  const t2 = loadTable("literata-20-gray");
  checkPairs("literata-20-gray", Object.keys(t2.pairs));
}
// Map reduction at shipped defaults on samples.
for (const [label, name] of [
  ["roboto-16-mono", "um"],
  ["literata-20-gray", "og"],
  ["roboto-16-mono", "nn"],
]) {
  const t = loadTable(label);
  const kase = boot.cases.find((c) => label.startsWith(c.id + "-"));
  const profile = label.endsWith("mono") ? "mono" : "gray";
  const prof = kase.profiles[profile];
  const gray = profile === "gray";
  const rec = t.pairs[name];
  const decided = LS.chosenStep(
    { metric: rec.metric, steps: rec.steps, geo: { d: rec.geo }, search: rec.search },
    "d",
    8.0,
  );
  const l = name.codePointAt(0),
    r = name.codePointAt(1);
  ensure(label, prof.capture_sha256, gray, prof.glyphs, l);
  ensure(label, prof.capture_sha256, gray, prof.glyphs, r);
  const map = engine.contribution_map_local(label, l, r, decided.step, 0.5, 12, "notebook");
  let sum = 0;
  for (let i = 0; i < map.length; i++) sum += map[i];
  const ci = rec.steps.indexOf(decided.step);
  const gl = rec.geo.gl[ci];
  const tol = 1e-9 * Math.max(1, Math.abs(gl));
  assert.ok(Math.abs(sum - gl) <= tol, `${label} ${name} map reduction ${sum} vs ${gl}`);
}

// ---- frozen pre-adoption main freeze (archived original, never the adopted page) ----
import { createHash } from "node:crypto";
const sha = (p) => createHash("sha256").update(readFileSync(p)).digest("hex");
assert.equal(sha(join(frozen, "index.html")), "48cbfd347eaa66f74dc180f0d2e5ff4708594394310df0245b0cfdc1867fe152");
assert.equal(sha(join(frozen, "boot.json")), "497add3a9eec9402537b96d98285793ad4686fb9caa2b056b81faa07d97b6ee6");
// The staged builder never reads the live data tables; pin them frozen too.
const liveDataPins = {
  "literata-12-gray": "e19b58d2e7cf9cb88845e3f2eca3cd84fbbe507be5cad6eead8ad6071bb597c5",
  "literata-12-mono": "86c3452a710bd48ce620c495bea272f0702f262acc6c5f3cb6ff0b9a9c056ec7",
  "literata-16-gray": "85099ca12a43e8e913d720036fb17fe8b58e554c89fa728e2000f8a529ff9911",
  "literata-16-mono": "4373f8b13b60eb1a48e38ff76276c85329d249fd17c9e9ba25bd12cf1bf456c3",
  "literata-20-gray": "cdf11678cc3a360d2653f34c2c8256e00ff22f9d5169e36b7a630e1d41e1433e",
  "literata-20-mono": "598148e25078264c8703340b895c5008eb84d85a21b1d47a2963216cb2ee62a1",
  "literata-8-gray": "909dda93071c4514aa39fcc9d71a894cc9259366a1e3ac8618580d6de88f5dda",
  "literata-8-mono": "9e59974936ee6cb1d6712415ca72c87de11f8835ef768747341d469caeeb041b",
  "roboto-12-gray": "6ddb4d6076ad3536ef7b28d6d301b0290a5fed24becde5b084e6bcbc1dac93e4",
  "roboto-12-mono": "bb2870f05a6cd727353d92a64e324311f148c1454a782e090c5064e4d349862c",
  "roboto-16-gray": "93662c20ee0c3a12d3ebf2c389c4ecd2f747b9f904f67f66e0dd9f695cd20d2e",
  "roboto-16-mono": "355bdd5130fd95e3249d2c53d57c4d38d67621fd75d826f928ff9574a6961a2b",
  "roboto-20-gray": "656ab4d447fedf425345fa69816fc03a4066c619bffb9713db8018cf87db8d60",
  "roboto-20-mono": "64089ab953ab783f1fa69ae47f60d507720d113960e99260d31cb6554ab33181",
  "roboto-8-gray": "2de9f70fa92e9adcf22b8ecc2a6b2555501c33f68a76819d586e1d7ab3422835",
  "roboto-8-mono": "acc36e949e8ffbc1dad4c40f5119b2e317fb120cad0059ce4a79814e4ff75825",
  "roboto-italic-12-gray": "d294bfd005667690c6b7d2a35882d1c2f9e17ea754b4b22e5611da2d4de6473e",
  "roboto-italic-12-mono": "f377b78c5f7241040f16ffdeb321f0e508bc3023cf1503341387806fe4bfcf03",
  "roboto-italic-16-gray": "e1d871ee93383cebe3aec362d764be2d3e92b86bc2d638e0338de3d5563fce32",
  "roboto-italic-16-mono": "21495d1d6c6a396aea863febc6f13f8f03d11207a828449dc1f2bcdd326f95e0",
  "roboto-italic-20-gray": "653b4f793b6f6d1138f970dd5abb81b4c0e7857bed3c1d9f897aa78b25fe4275",
  "roboto-italic-20-mono": "fcf3d730dd7140c897cd25363ed03f9852b0e25e657ba19e4a8fea7831e27590",
  "roboto-italic-8-gray": "f61f5e126bab889e4eedb6a0d23ba865a7ed36d75b93ffb575d97f2b8439685b",
  "roboto-italic-8-mono": "d32640c006325a37ebbe62555719505144b0c2e374f281f52aba1a0651f94aa6",
  "rouge-script-20-gray": "04d772414d7b82c216d59b2b7e69f4fa0f31d74dc7cbbb97fef55b4eff22263f",
  "rouge-script-20-mono": "bb454bc2901df1773ff910727877c81cbef1120785d59a76360ac0b4378eba8d",
};
for (const [label, pin] of Object.entries(liveDataPins)) {
  assert.equal(sha(join(frozen, "data", `${label}.js`)), pin, `frozen data unchanged (${label})`);
}

// ---- current adopted main identity (active page checks) ----
const currentBoot = JSON.parse(readFileSync(join(live, "boot.json"), "utf8"));
assert.equal(currentBoot.model, "yinyangfit-oriented-engine-v1");
assert.equal(currentBoot.score_model, "yinyangfit-local-energy-v2");
assert.equal(currentBoot.search_policy, "yinyangfit-search-v2");
assert.equal(
  currentBoot.implementation.wasm_sha256,
  "c27fe2e2c7d53114fbaace7829c6eec13d06e2ee28039b6a18296207dea7f855",
);
// Adopted layered-heatmap display (display-only; prior active page archived
// under out/diagnostics/contextual-spacing/yinyang-layered-heatmap/adoption/archive).
assert.equal(sha(join(live, "index.html")), "66eef10d80c7c593940824582415c51cc829006103df87e926e289f20654692e");
assert.equal(sha(join(live, "boot.json")), "dde5c65ade42ce1c3c02a59d941f9b1993264f33ebaf8062e5761b425d14f162");
const currentDataPins = {
  "literata-12-gray": "21ac0c459f4edc09c7e14cf6715890e92d6ce06a75c77a811eb7277327e5fd5e",
  "literata-12-mono": "17fed372744f023e50840ffd04bca498abf95b5f6373e8a724b52be2f863fc52",
  "literata-16-gray": "52fbcbe744f4c3df7351920a3216701243c275246ee6ed973d289db8bd99eb4d",
  "literata-16-mono": "1a664995b4703f11d4352a7b9784da03da38f6bbadcdb1c905e7dc8418988127",
  "literata-20-gray": "c31dd7f75ea4ceb24d0ea912d7a30a8e0d4210599b1b2d5b2b76ccad8574f32b",
  "literata-20-mono": "ce7ba033842b99ea6451027a0924a823a98f256a8b3bb23b2ceda5b814d17a06",
  "literata-8-gray": "decebc33e3ee41242cbb52ecadad9d07d12e9a714f9ba0c34b5f066be5ffb8b7",
  "literata-8-mono": "ca13830f1e978e15b3d260c5d0fcd2fa1c6d2fb2f451092dd0783dc263727f15",
  "roboto-12-gray": "8c81eded8fb635d83b4b0d8c89464228ea95b2329fb12ad4c5bdda9f93cc0e51",
  "roboto-12-mono": "27177f2f5ab942744d10efdc56ff832feb51fb3363d95574b8fe086909a95c79",
  "roboto-16-gray": "bed3a6ffa2f0168fec66443a7b18e1bbf25119e81eef4c4281cf870e539ecfce",
  "roboto-16-mono": "d09e46cec69cc30189889ebe48302f10b957f07e52f7f4b3cad19b8dc0b5de44",
  "roboto-20-gray": "dec377abf98f26484f402366505876db9f7545f3e77f378411a445cadbb1197a",
  "roboto-20-mono": "dd8bab30ac069b6bbfa54b527c9a37682426e8f9f1a97b3e99daf5534b8f7a5d",
  "roboto-8-gray": "a9f52f294e2d2068fb2a2838a15567937169d5b389c07ae0d503efb78eac38f0",
  "roboto-8-mono": "a29f35bc689c066998d6db3c43f35bb0066bd05e6726350f4372a505b8512ab2",
  "roboto-italic-12-gray": "df505210877bee6603c4daf38512019f991735ff8b1c81638d39ab6642629eb6",
  "roboto-italic-12-mono": "98649350d7f49abefd59f8a7c2f889d357c2227482363c92f2c0f4c4d5ae4c60",
  "roboto-italic-16-gray": "97e2b1cdb949cf4cd51e6befb640a36de5050be4baffd6bae8cd88fe08c67a8b",
  "roboto-italic-16-mono": "31270c3de6bc5a7df53f44562fa0d200c29cfbc7ccfd70403df1e91728d72796",
  "roboto-italic-20-gray": "7aaaa400cab175ecbecf001615cda60d2950afcde2767212f5906cd9ed44bf32",
  "roboto-italic-20-mono": "1e8bb6e68fd3e3a1df61b14938afe0acb959e521641887db66d6259cc10a5900",
  "roboto-italic-8-gray": "5625823817bb317b3d933792f464566d0b362116e80bb6901a5339caca43632a",
  "roboto-italic-8-mono": "52486c83534613b9132694c3d5019c2e6f822c17b38b81039da47d86b21c0c4c",
  "rouge-script-20-gray": "4052b089c879c60c87314826ee583c57c4f6eb21460cd236130420b75f422468",
  "rouge-script-20-mono": "754e70aead7e28e12ce7cc9445d07ed24dfb3d5f7af0a192daa7d0fe2ea08ded",
};
for (const [label, pin] of Object.entries(currentDataPins)) {
  assert.equal(sha(join(live, "data", `${label}.js`)), pin, `adopted data current (${label})`);
}

console.log(JSON.stringify({ ok: true, datasets: labels.length, pairs: pairCount }));
