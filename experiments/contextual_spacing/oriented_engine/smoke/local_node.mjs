// Node smoke for the Class-L local-energy WASM surface vs the frozen
// reference adapter (runtime/local_adapter.json).
//
// Usage: node smoke/local_node.mjs LOCAL_ADAPTER_JSON
//
// Instantiates pkg-web from raw bytes (offline file:// worker path) and
// the pkg-nodejs package, then checks on synthetic bars covers: version
// identities, R12 pair/trio gl/both/weak/abstain/bound at 1e-9 with exact
// counts, contribution-map reduction (sum ~= gl), confidence L/R symmetry
// on identical glyphs, and the conditioned R6 agreement at 1e-5.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [adapterPath] = process.argv.slice(2);
if (!adapterPath) {
  console.error("usage: node smoke/local_node.mjs LOCAL_ADAPTER_JSON");
  process.exit(2);
}
const adapter = JSON.parse(readFileSync(adapterPath, "utf8"));
const leaf = new URL("..", import.meta.url).pathname;

let failures = 0;
function check(name, cond, detail = "") {
  if (!cond) {
    failures += 1;
    console.error(`FAIL ${name} ${detail}`);
  } else {
    console.log(`ok ${name}`);
  }
}
function close(got, exp, tol) {
  if (!Number.isFinite(got) || !Number.isFinite(exp)) return got === exp;
  return Math.abs(got - exp) <= tol * Math.max(Math.abs(exp), 1.0);
}

// Synthetic bars covers (match the parity exporter geometry exactly:
// 20x100 ink rows 4..16 cols 20..22; trio adds cols 62..64).
function covers(trio) {
  const c = new Float64Array(20 * 100);
  for (let y = 4; y < 16; y++) {
    for (let x = 20; x < 22; x++) c[y * 100 + x] = 1.0;
    if (trio) for (let x = 62; x < 64; x++) c[y * 100 + x] = 1.0;
  }
  return c;
}

async function exercise(pkgDir, label, init) {
  let mod;
  if (init === "bytes") {
    mod = await import(pathToFileURL(join(leaf, pkgDir, "yinyang_oriented_engine.js")).href);
    mod.initSync({ module: readFileSync(join(leaf, pkgDir, "yinyang_oriented_engine_bg.wasm")) });
  } else {
    // wasm-bindgen nodejs output is CJS; the repo root is type: module,
    // so load it through a .cjs copy (same bytes, no rebuild).
    const { createRequire } = await import("node:module");
    const { tmpdir } = await import("node:os");
    const { copyFileSync } = await import("node:fs");
    const cjsCopy = join(tmpdir(), `yinyang_local_${label}.cjs`);
    copyFileSync(join(leaf, pkgDir, "yinyang_oriented_engine.js"), cjsCopy);
    copyFileSync(
      join(leaf, pkgDir, "yinyang_oriented_engine_bg.wasm"),
      join(tmpdir(), "yinyang_oriented_engine_bg.wasm"),
    );
    // The nodejs target initializes synchronously on require.
    mod = createRequire(import.meta.url)(cjsCopy);
  }
  const engine = new mod.YinYangEngine();
  const ver = JSON.parse(engine.version());
  check(`${label} version local identity`, ver.score_model === "yinyangfit-local-energy-v2", ver.score_model);
  check(`${label} version keeps G2 identity`, typeof ver.model === "string" && ver.model.length > 0, ver.model);
  check(`${label} frozen radius`, ver.frozen_normalization_radius === 12, ver.frozen_normalization_radius);

  const bar = covers(false),
    trio = covers(true);
  engine.load_glyph("synthetic", "adapter-bar", 0x41, 100, 20, 0, 0, bar);
  engine.load_glyph("synthetic", "adapter-bar", 0x42, 100, 20, 0, 0, bar);
  engine.load_glyph("synthetic", "adapter-bar", 0x43, 100, 20, 0, 0, trio);
  const I32 = (a) => new Int32Array(a);

  for (const [name, left, tag] of [
    ["pair", 0x41, "R12"],
    ["trio", 0x43, "R12"],
  ]) {
    const exp = adapter.bars[tag][name];
    const res = JSON.parse(engine.score_pair_local("synthetic", left, 0x42, 0, I32([6]), 0.5, 12, "notebook", NaN));
    const s = res.steps[0];
    check(`${label} ${tag} ${name} gl`, close(s.gl, exp.gl, 1e-9), `${s.gl} vs ${exp.gl}`);
    check(
      `${label} ${tag} ${name} both exact`,
      s.both_supported_pairpx === exp.both,
      `${s.both_supported_pairpx} vs ${exp.both}`,
    );
    check(
      `${label} ${tag} ${name} weak`,
      close(s.weak_normalized_share, exp.weak, 1e-9),
      `${s.weak_normalized_share} vs ${exp.weak}`,
    );
    check(`${label} ${tag} ${name} abstain`, s.abstain === exp.abstain);
    check(`${label} ${tag} ${name} bound`, close(s.honest_bound, exp.bound, 1e-9), `${s.honest_bound} vs ${exp.bound}`);
    check(`${label} ${tag} ${name} uncertainty`, res.uncertainty === "uncertainty_not_certified");
  }

  // Contribution map reduces to the step score.
  const res12 = JSON.parse(engine.score_pair_local("synthetic", 0x41, 0x42, 0, I32([6]), 0.5, 12, "notebook", NaN));
  const map = engine.contribution_map_local("synthetic", 0x41, 0x42, 6, 0.5, 12, "notebook");
  const geo = JSON.parse(engine.last_map_geometry());
  check(`${label} map geometry`, map.length === geo.width * geo.height, `${map.length} vs ${geo.width}x${geo.height}`);
  let sum = 0;
  for (const v of map) sum += v;
  check(`${label} map reduces to gl`, close(sum, res12.steps[0].gl, 1e-9), `${sum} vs ${res12.steps[0].gl}`);

  // Confidence is L/R symmetric on identical glyphs (up to fp
  // summation order; the native readout has the same property).
  const conf = JSON.parse(engine.confidence_pair("synthetic", 0x41, 0x41, 0, "notebook"));
  check(
    `${label} confidence symmetry`,
    close(conf.support_mass_l, conf.support_mass_r, 1e-12) &&
      close(conf.support_weak_mass_l, conf.support_weak_mass_r, 1e-12),
    `${conf.support_mass_l} vs ${conf.support_mass_r}`,
  );
  check(`${label} confidence share range`, conf.support_share > 0 && conf.support_share <= 1, conf.support_share);

  // Conditioned R6 path agrees at the derived gate.
  const exp6 = adapter.bars.R6.pair;
  const res6 = JSON.parse(engine.score_pair_local("synthetic", 0x41, 0x42, 0, I32([6]), 0.5, 6, "notebook", NaN));
  check(`${label} R6 gl conditioned`, close(res6.steps[0].gl, exp6.gl, 1e-5), `${res6.steps[0].gl} vs ${exp6.gl}`);

  // Locally-normalized component projection is served on the padded
  // glyph lattice (pad 24 each side: 148x68 here).
  const comp = engine.glyph_component("synthetic", 0x41, "lnorm", 0, 0);
  const note = JSON.parse(engine.last_component_note());
  check(
    `${label} lnorm component`,
    comp.length === note.width * note.height && note.width === 148 && note.height === 68,
    `${comp.length} ${note.width}x${note.height}`,
  );

  // Abstain paths through the same core: a blank glyph abstains with
  // no_shared_support at step and pair level (cstar 0 exercises the
  // all-abstain fallback). Exact gl==0 is pinned natively and in the
  // pilot (V1 responses bleed through covers, so covers cannot express
  // it); here the sparse pair proves eligible routing with finite gl.
  engine.load_glyph("synthetic", "adapter-bar", 0x60, 10, 10, 0, 0, new Float64Array(100));
  const blank = JSON.parse(engine.score_pair_local("synthetic", 0x60, 0x41, 0, I32([0]), 0.5, 12, "notebook", 0.0));
  check(
    `${label} blank abstains no-shared-support`,
    blank.steps[0].abstain === true &&
      blank.steps[0].abstain_reason === "no_shared_support" &&
      blank.fallback === true &&
      blank.fallback_reason === "no_shared_support",
    JSON.stringify(blank.steps[0]),
  );
  const pa = new Float64Array(400);
  pa[10 * 20 + 10] = 1.0;
  const pb = new Float64Array(400);
  pb[10 * 20 + 16] = 1.0;
  engine.load_glyph("synthetic", "adapter-bar", 0x61, 20, 20, 0, 0, pa);
  engine.load_glyph("synthetic", "adapter-bar", 0x62, 20, 20, 0, 0, pb);
  const vz = JSON.parse(engine.score_pair_local("synthetic", 0x61, 0x62, 0, I32([0]), 0.5, 12, "notebook", 0.0));
  check(
    `${label} sparse agreement eligible`,
    vz.steps[0].abstain === false && Number.isFinite(vz.steps[0].gl) && vz.steps[0].both_supported_pairpx > 0,
    JSON.stringify(vz.steps[0]),
  );
}

await exercise("pkg-web", "web", "bytes");
await exercise("pkg-nodejs", "node", "default");
if (failures > 0) {
  console.error(`${failures} failures`);
  process.exit(1);
}
console.log("local-energy WASM smoke passes on web and nodejs packages.");
