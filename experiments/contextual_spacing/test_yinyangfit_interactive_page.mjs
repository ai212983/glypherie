// DOM-free verification of the interactive feasibility page.
// Checks: no native title tooltips, control/identity wiring present, and the
// browser argmin mirror matches every embedded Python choice exactly.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const dir = dirname(fileURLToPath(import.meta.url));
const root = join(dir, "../..");
const site = process.argv[2] || join(root, "out/diagnostics/contextual-spacing/yinyangfit-interactive-v2/site");
const html = readFileSync(join(site, "index.html"), "utf8");
const appJs = readFileSync(join(dir, "yinyangfit_interactive_app.js"), "utf8");
const wiringJs = readFileSync(join(dir, "yinyangfit_interactive_wiring.js"), "utf8");

// No native title tooltips anywhere (page text carries descriptions instead).
assert.ok(!html.includes("title="), "native title attribute found");

// Required controls and wiring hooks.
for (const id of [
  "yy-dataset",
  "yy-cohesion",
  "yy-scale",
  "yy-falloff",
  "yy-pair",
  "yy-word",
  "yy-zoom",
  "yy-reset",
  "yy-identity",
  "yy-metric1",
  "yy-metricN",
  "yy-chosen1",
  "yy-chosenN",
  "yy-table",
  "yy-word1",
  "yy-wordN",
  "yy-word-gaps",
  "yy-cword1",
  "yy-cwordN",
  "yy-cword-gaps",
]) {
  assert.ok(html.includes(`id="${id}"`), `missing element ${id}`);
}

// Control language must not claim upstream semantics.
for (const stale of ["Feature scale", "Spatial scale", "penalizes near ink", "current source spacing"]) {
  assert.ok(!html.includes(stale), `stale control wording: ${stale}`);
}
assert.ok(html.includes("Not an independently implemented"), "falloff departure wording present");
assert.ok(html.includes("Interaction reach"), "reach wording present");
assert.ok(html.includes("no live scorer"), "fixed-grid scope present");

// Embedded data extraction.
const match = html.match(/<script type="application\/json" id="yy-data">([\s\S]*?)<\/script>/);
assert.ok(match, "embedded page data missing");
const data = JSON.parse(match[1]);

// Defaults must sit on evaluated grid points.
const defaults = data.controls.default;
assert.equal(data.controls.cohesion[4], defaults.cohesion);
assert.equal(data.controls.feature_scale[2], defaults.feature_scale);
assert.equal(data.controls.proximity_falloff[2], defaults.proximity_falloff);

// Browser selection mirror.
const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(appJs + "\nthis.YY = this.YinYangInteractive;", sandbox);
const YY = sandbox.YY;

// Independent near-tie fixture (not from any evaluated dataset): the
// global-minimum tolerance set is indices [0, 1]. A moving-best comparison
// would wrongly also admit index 2, which is near index 0 but not near the
// minimum at index 1.
// Spread out of the VM realm: deepStrictEqual rejects cross-realm arrays.
assert.deepEqual([...YY.selectIndices({ costs: [0.9e-9, 0, 1.8e-9], ok: [true, true, true] })], [0, 1]);
// With the minimum itself invalid, the tolerance set re-anchors at the
// remaining global minimum 0.9e-9, which index 2 still meets.
assert.deepEqual([...YY.selectIndices({ costs: [0.9e-9, 0, 1.8e-9], ok: [true, false, true] })], [0, 2]);

let combos = 0,
  pairs = 0,
  boundaryHits = 0,
  invalidSeen = 0,
  words = 0;
for (const ds of data.datasets) {
  for (const [name, pair] of Object.entries(ds.pairs)) {
    pairs++;
    assert.equal(pair.steps.length, 5, `${ds.label} ${name}: five candidates`);
    for (const combo of data.combos) {
      combos++;
      const entry = pair.table[combo.id];
      const chosen = YY.chosenStep(pair, combo.id);
      assert.equal(chosen, entry.ch, `${ds.label} ${name} ${combo.id}: browser/Python choice mismatch`);
      if (entry.bd) boundaryHits++;
      invalidSeen += entry.ok.filter(Boolean).length < 5 ? 1 : 0;
      const finite = entry.costs.filter((c) => c !== null);
      assert.ok(finite.every(Number.isFinite), "nonfinite embedded cost");
    }
  }
  // Word layouts resolve through evaluated pairs only.
  const steps = YY.pairStepsFor(ds, data.combos[40].id);
  for (const word of data.words) {
    words++;
    const layout = YY.layoutWord(steps, word);
    assert.ok(!layout.error, `${ds.label} ${word}: ${layout.error}`);
    assert.equal(layout.origins.length, word.length);
    assert.equal(layout.gaps.length, word.length - 1);
    for (let i = 1; i < layout.origins.length; i++)
      assert.equal(layout.origins[i] - layout.origins[i - 1], layout.gaps[i - 1].chosen);
  }
}
// Captured-source baseline: recompute draw origins from the raw captures
// with independent fractional-pen arithmetic (no experiment code), and
// require the embedded baseline to match exactly.
function rawCapturedOrigins(ds, word) {
  const capture = JSON.parse(readFileSync(join(root, ds.source_path), "utf8"));
  const cps = [...word].map((c) => c.codePointAt(0));
  let advances, kern;
  if (ds.profile === "mono") {
    advances = new Map(capture.glyphs.map((g) => [g.codepoint, g.finalized_advance_px]));
    kern = new Map((capture.metric_pairs_on || []).map((p) => [`${p.left}/${p.right}`, p.adjustment_px]));
  } else {
    advances = new Map(capture.font.glyphs.map((g) => [g.codepoint, g.advance_26_6 / 64]));
    kern = new Map((capture.font.kerning || []).map((p) => [`${p.left}/${p.right}`, p.adjustment_26_6 / 64]));
  }
  const origins = [0];
  let pen = 0;
  for (let i = 0; i + 1 < cps.length; i++) {
    assert.ok(advances.has(cps[i]), `missing advance U+${cps[i].toString(16)}`);
    pen += advances.get(cps[i]) + (kern.get(`${cps[i]}/${cps[i + 1]}`) || 0);
    origins.push(Math.floor(pen + 0.5));
  }
  return origins;
}

for (const ds of data.datasets) {
  for (const word of data.words) {
    assert.ok(ds.captured_words[word], `${ds.label} ${word}: baseline embedded`);
    assert.deepEqual(
      ds.captured_words[word].origins,
      rawCapturedOrigins(ds, word),
      `${ds.label} ${word}: baseline vs capture arithmetic`,
    );
  }
  // Delivered Gray coverage reaches the page unrounded: every embedded
  // level is exactly a delivered p/7 code.
  if (ds.profile === "gray") {
    for (const [cp, glyph] of Object.entries(ds.glyphs)) {
      for (const v of glyph.cover) {
        assert.ok(
          Math.abs(v * 7 - Math.round(v * 7)) < 1e-9,
          `${ds.label} U+${Number(cp).toString(16)}: cover not an exact delivered level`,
        );
      }
    }
  }
}

// Candidate origin differences at the default setting: the experiment word
// layout (cumulative integer choices) differs from the captured-source
// baseline on Roboto 24 px Gray Hamburg, which pins the corrected H2 split.
const defaultCombo = data.combos.find(
  (c) =>
    c.cohesion === data.controls.default.cohesion &&
    c.feature_scale === data.controls.default.feature_scale &&
    c.proximity_falloff === data.controls.default.proximity_falloff,
);
assert.ok(defaultCombo, "default combo on grid");
const robotoGray = data.datasets.find((d) => d.label === "Roboto-24-gray");
const defaultSteps = YY.pairStepsFor(robotoGray, defaultCombo.id);
const defaultLayout = YY.layoutWord(defaultSteps, "Hamburg");
assert.ok(!defaultLayout.error, `Hamburg: ${defaultLayout.error}`);
assert.deepEqual(robotoGray.captured_words["Hamburg"].origins, [0, 17, 30, 51, 65, 78, 86]);
assert.notDeepEqual(
  defaultLayout.origins,
  robotoGray.captured_words["Hamburg"].origins,
  "default candidate word layout differs from captured-source baseline",
);

assert.ok(boundaryHits > 0, "expected recorded boundary minima");
assert.ok(invalidSeen > 0, "expected recorded invalid candidates");
console.log(
  JSON.stringify({
    status: "passed",
    datasets: data.datasets.length,
    pairs,
    combos,
    words,
    boundaryHits,
    combosWithInvalid: invalidSeen,
    model: data.model,
    implementation: data.implementation.slice(0, 12),
  }),
);
