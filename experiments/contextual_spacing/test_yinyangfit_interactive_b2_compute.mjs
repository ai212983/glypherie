// cspell:words fullwindow yinyang yinyangfit
// B2 browser parity: the in-page port must reproduce the B2 Python corpus.
// Compares per-candidate validity, interaction and attention plus the shared
// choice at four cohesions over default, wide, narrow and off-grid settings.
// Scalar tolerance is 1e-9; any choice mismatch fails and is recorded.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const dir = dirname(fileURLToPath(import.meta.url));
const root = join(dir, "../..");
const corpusPath =
  process.argv[2] || join(root, "out/diagnostics/contextual-spacing/yinyang-full-window/parity-corpus-b2.json");
const corpus = JSON.parse(readFileSync(corpusPath, "utf8"));

assert.equal(corpus.model, "yinyangfit-interactive-b2-fullwindow-v1", "corpus model identity");
assert.ok(corpus.implementation && corpus.implementation.length === 64, "corpus implementation identity");

const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(
  readFileSync(join(dir, "yinyangfit_interactive_v3_compute.js"), "utf8") + "\nthis.YYC = this.YYCompute;",
  sandbox,
);
const YYC = sandbox.YYC;
assert.ok(YYC, "compute module loads");

function pixelRound(value) {
  if (value >= 0) return Math.floor(value + 0.5);
  return Math.ceil(value - 0.5);
}
function metricStep(adv, kern, left, right) {
  const key = left + "/" + right;
  const adj = Object.prototype.hasOwnProperty.call(kern, key) ? kern[key] : 0;
  return pixelRound(adv[String(left)] + adj);
}

const sessions = {};
function sessionFor(dataset) {
  if (!sessions[dataset]) {
    sessions[dataset] = YYC.createSession(corpus.cells[dataset]);
  }
  return sessions[dataset];
}

const TOL = 1e-9;
let scalars = 0,
  choices = 0,
  maxInter = 0,
  maxAtt = 0;
const mismatches = [];
for (const entry of corpus.entries) {
  const session = sessionFor(entry.dataset);
  const left = entry.pair.charCodeAt(0),
    right = entry.pair.charCodeAt(1);
  const adv = corpus.metrics[entry.dataset].advances;
  const kern = corpus.metrics[entry.dataset].kern;
  assert.equal(metricStep(adv, kern, left, right), entry.metric, `${entry.dataset} ${entry.pair}: metric step`);
  for (const [cohesionKey, wantChoice] of Object.entries(entry.choices)) {
    const cohesion = Number(cohesionKey);
    const got = session.scorePair(
      entry.pair,
      String(left),
      String(right),
      entry.metric,
      entry.scale,
      entry.falloff,
      cohesion,
    );
    assert.ok(session.cacheSizes().scalePoints <= 250000, "retained query samples stay bounded at wide reach");
    for (let i = 0; i < entry.candidates.length; i++) {
      const want = entry.candidates[i];
      const inter = got.entry.inter[i];
      scalars++;
      assert.equal(
        got.entry.ok[i],
        want.valid,
        `${entry.dataset} ${entry.pair} ${entry.scale}/${entry.falloff} #${i}: validity`,
      );
      if (want.valid) {
        const dInter = Math.abs(inter - want.interaction);
        const dAtt = Math.abs(got.entry.att[i] - want.attention);
        if (dInter > maxInter) maxInter = dInter;
        if (dAtt > maxAtt) maxAtt = dAtt;
        assert.ok(
          dInter <= TOL,
          `${entry.dataset} ${entry.pair} ${entry.scale}/${entry.falloff} #${i}: interaction ${inter} vs ${want.interaction}`,
        );
        assert.ok(dAtt <= TOL, `${entry.dataset} ${entry.pair} ${entry.scale}/${entry.falloff} #${i}: attention`);
      }
    }
    choices++;
    if (got.chosen !== wantChoice.chosen || got.fallback !== wantChoice.fallback) {
      mismatches.push({
        dataset: entry.dataset,
        pair: entry.pair,
        scale: entry.scale,
        falloff: entry.falloff,
        cohesion,
        js: [got.chosen, got.fallback],
        py: [wantChoice.chosen, wantChoice.fallback],
      });
    }
  }
}
assert.deepEqual(mismatches, [], `${mismatches.length} choice mismatches`);
console.log(
  JSON.stringify({
    status: "passed",
    scalars,
    choices,
    maxInterDiff: maxInter,
    maxAttDiff: maxAtt,
    tolerance: TOL,
    entries: corpus.entries.length,
  }),
);
