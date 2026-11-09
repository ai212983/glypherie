// cspell:words yinyang
// Verification for the predictable spacing-control prototype page.
// Checks: concise wording, required controls, catalogue coverage, cover-code
// integrity, captured-baseline parity against raw capture arithmetic, and
// browser/Python composition parity over the shipped tables (frozen strength
// grid for every pair, Source-exact layouts, letter-spacing policy).
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import vm from "node:vm";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const dir = dirname(fileURLToPath(import.meta.url));
const root = join(dir, "../..");
const site = process.argv[2] || join(root, "out/diagnostics/contextual-spacing/predictable-spacing/site");
const html = readFileSync(join(site, "index.html"), "utf8");
const appJs = readFileSync(join(dir, "predictable_spacing_app.js"), "utf8");

// No native title tooltips anywhere.
assert.ok(!html.includes("title="), "native title attribute found");

// Visible-flow wording checks ignore embedded scripts and data.
const visible = html.replace(/<script[\s\S]*?<\/script>/g, "");

// Required controls and regions.
for (const id of [
  "ps-optical",
  "ps-optical-v",
  "ps-letter",
  "ps-letter-v",
  "ps-sample",
  "ps-profile",
  "ps-zoom",
  "ps-reset",
  "ps-focus-title",
  "ps-original",
  "ps-adjusted",
  "ps-original-cap",
  "ps-adjusted-cap",
  "ps-sample-note",
  "ps-pair",
  "ps-pair-metric",
  "ps-pair-chosen",
  "ps-pair-note",
  "ps-diagnostics",
  "ps-pairs",
  "ps-diagnostics-box",
  "ps-about-box",
]) {
  assert.ok(html.includes(`id="${id}"`), `missing element ${id}`);
}

// Pair inspection and diagnostics start collapsed.
for (const id of ["ps-pairs", "ps-diagnostics-box", "ps-about-box"]) {
  const tag = html.match(new RegExp(`<details[^>]*id="${id}"[^>]*>`));
  assert.ok(tag && !tag[0].includes("open"), `${id} must start collapsed`);
}

// Rendered canvases carry no border and never shrink.
assert.ok(/canvas \{[^}]*border: none/.test(html), "canvas border removed");
assert.ok(/canvas \{[^}]*max-width: none/.test(html), "canvas keeps native pixels");

// Concise default flow: no interaction-scorer vocabulary, no optical claims.
for (const stale of [
  "cohesion",
  "reach",
  "falloff",
  "feature_scale",
  "yinyang",
  "YinYang",
  "optimum",
  "candidate-domain",
]) {
  assert.ok(!visible.includes(stale), `stale wording in default flow: ${stale}`);
}
assert.ok(visible.includes("<h1>Spacing</h1>"), "short title present");
assert.ok(visible.includes("Optical correction"), "optical label present");
assert.ok(visible.includes("Letter spacing"), "letter label present");
assert.ok(
  !visible.includes("Tighter") || visible.includes("Letter spacing"),
  "tightness wording stays with the uniform offset control",
);

// Embedded boot data.
const match = html.match(/<script type="application\/json" id="ps-boot">([\s\S]*?)<\/script>/);
assert.ok(match, "embedded boot data missing");
const boot = JSON.parse(match[1]);

const catalogue = JSON.parse(readFileSync(join(root, "apps/web/scripts/landing-samples/main-page.json"), "utf8"));
assert.equal(catalogue.length, 13, "root catalogue holds all 13 cases");
assert.deepEqual(
  boot.cases.map((c) => c.id),
  catalogue.map((c) => c.id),
  "case order follows the root catalogue",
);
assert.equal(boot.model, "predictable-spacing-v4", "prototype model");
assert.equal(boot.spacing_model, "hu_fitted_full_density_conserved_touch", "retained endpoint");
assert.deepEqual(boot.controls.default, { optical: 0, letter: 0 }, "Source default with neutral spacing");
assert.equal(boot.controls.letter_min, -2, "letter range admits tightening");
assert.equal(boot.controls.letter_max, 4, "letter range admits loosening");

// Browser composition mirror.
const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(appJs + "\nthis.PS = this.PredictableSpacing;", sandbox);
const PS = sandbox.PS;

function pixelRound(v) {
  return v >= 0 ? Math.floor(v + 0.5) : Math.ceil(v - 0.5);
}

function rawCapture(profile, capture) {
  if (profile === "mono") {
    return {
      advances: new Map(capture.glyphs.map((g) => [g.codepoint, g.finalized_advance_px])),
      kern: new Map((capture.metric_pairs_on || []).map((p) => [`${p.left}/${p.right}`, p.adjustment_px])),
    };
  }
  return {
    advances: new Map(capture.font.glyphs.map((g) => [g.codepoint, g.advance_26_6 / 64])),
    kern: new Map((capture.font.kerning || []).map((p) => [`${p.left}/${p.right}`, p.adjustment_26_6 / 64])),
  };
}

function rawOrigins(advances, kern, line) {
  const cps = [...line].map((c) => c.codePointAt(0));
  const origins = [0];
  let pen = 0;
  for (let i = 0; i + 1 < cps.length; i++) {
    assert.ok(advances.has(cps[i]), `missing advance U+${cps[i].toString(16)}`);
    pen += advances.get(cps[i]) + (kern.get(`${cps[i]}/${cps[i + 1]}`) || 0);
    origins.push(pixelRound(pen));
  }
  return origins;
}

const REASONS = new Set([
  "optical_disabled",
  "fixed_pitch",
  "source_tabular_digits",
  "empty_geometry",
  "unsupported_calibration_class",
  "calibration_unavailable",
  "no_shared_ink_rows",
  "clearance_limited",
  null,
  undefined,
]);

let pairs = 0,
  plateaus = 0,
  abstentions = 0,
  guarded = 0;
for (const c of boot.cases) {
  assert.ok(c.text && c.text.length > 0, `${c.id}: sample text present`);
  for (const profile of ["mono", "gray"]) {
    const ds = c.profiles[profile];
    assert.ok(ds, `${c.id}: ${profile} profile present`);
    assert.deepEqual(ds.lines, c.text.split("\n"), `${c.id}: lines kept`);
    for (const ch of c.text.replaceAll("\n", "")) {
      assert.ok(
        ds.glyphs[String(ch.codePointAt(0))],
        `${c.id} ${profile}: U+${ch.codePointAt(0).toString(16)} covered`,
      );
    }
    for (const [cp, g] of Object.entries(ds.glyphs)) {
      assert.ok(g.cover.length === g.w * g.h, `${c.id} ${profile} U+${cp}: cover size`);
      for (const code of g.cover) {
        if (profile === "mono") {
          assert.ok(code === "0" || code === "1", "mono code binary");
        } else {
          assert.ok(code >= "0" && code <= "7", "gray code delivered level");
        }
      }
    }
    // Captured baseline matches independent capture arithmetic per line.
    const capture = JSON.parse(readFileSync(join(root, ds.capture), "utf8"));
    // Delivered glyph pixels are invariant: every shipped cell equals the
    // captured bitmap (binary for Mono, exact 0-7 levels for Gray).
    if (profile === "mono") {
      for (const g of capture.glyphs) {
        const shipped = ds.glyphs[String(g.codepoint)];
        assert.ok(shipped, `${c.id} mono U+${g.codepoint}: glyph shipped`);
        assert.deepEqual(
          [shipped.w, shipped.h, shipped.left, shipped.top],
          [g.bitmap.width, g.bitmap.height, g.bitmap.left, g.bitmap.top],
          `${c.id} mono U+${g.codepoint}: cell geometry`,
        );
        assert.equal(
          shipped.cover,
          g.bitmap.pixels.map((v) => (v ? "1" : "0")).join(""),
          `${c.id} mono U+${g.codepoint}: delivered ink`,
        );
      }
    } else {
      for (const g of capture.font.glyphs) {
        const shipped = ds.glyphs[String(g.codepoint)];
        assert.ok(shipped, `${c.id} gray U+${g.codepoint}: glyph shipped`);
        assert.deepEqual(
          [shipped.w, shipped.h, shipped.left, shipped.top],
          [g.width, g.height, g.left, g.top],
          `${c.id} gray U+${g.codepoint}: cell geometry`,
        );
        assert.equal(
          shipped.cover,
          g.pixels.map((v) => String(v)).join(""),
          `${c.id} gray U+${g.codepoint}: delivered levels`,
        );
      }
    }
    const { advances, kern } = rawCapture(profile, capture);
    ds.lines.forEach((line, li) => {
      assert.deepEqual(
        ds.captured[li],
        rawOrigins(advances, kern, line),
        `${c.id} ${profile} line ${li}: baseline vs capture arithmetic`,
      );
    });
    // Shipped table file.
    const label = `${c.id}-${profile}`;
    const tableJs = readFileSync(join(site, "data", `ps-${label}.js`), "utf8");
    const box = {};
    vm.createContext(box);
    box.window = {};
    vm.runInContext(tableJs, box);
    const table = box.window.PS_TABLES[label];
    assert.ok(table, `${label}: table present`);
    // Metric steps agree with the independent capture arithmetic. Mono gap
    // metrics equal the endpoint record metric; Gray gap metrics equal the
    // rounded fractional source step (mono-pipeline rounding may differ).
    for (const lineGaps of ds.gaps) {
      for (const g of lineGaps) {
        if (g.space) continue;
        const rec = table.pairs[g.pair];
        assert.ok(rec, `${label} ${g.pair}: endpoint record present`);
        if (profile === "mono") {
          assert.equal(g.metric, rec.metric, `${label} ${g.pair}: metric step`);
        } else {
          assert.equal(g.metric, pixelRound(g.frac), `${label} ${g.pair}: gray rounded source step`);
        }
      }
    }
    for (const [name, rec] of Object.entries(table.pairs)) {
      pairs++;
      assert.ok(REASONS.has(rec.reason) || typeof rec.reason === "string", `${label} ${name}: recorded reason`);
      if (rec.optical_adjustment === null) {
        abstentions++;
        assert.equal(rec.reason === null, false, `${label} ${name}: abstention reason`);
      }
      if (rec.minimum !== null && rec.minimum !== undefined) guarded++;
      // Frozen grid matches the browser composition exactly.
      const steps = table.grid.steps[name];
      assert.deepEqual(steps.length, table.grid.strengths.length, `${label} ${name}: grid length`);
      table.grid.strengths.forEach((s, i) => {
        assert.equal(PS.autoStep(rec, s), steps[i], `${label} ${name} @${s}: shipped grid vs browser composition`);
      });
      if (new Set(steps).size < steps.length) plateaus++;
      // Endpoint direction monotonicity when only strength changes.
      const dir = rec.optical_adjustment === null ? 0 : rec.advance + rec.optical_adjustment - rec.metric;
      const fine = [];
      for (let i = 0; i <= 100; i++) fine.push(PS.autoStep(rec, i / 100));
      for (let i = 0; i + 1 < fine.length; i++) {
        assert.ok(
          dir >= 0 ? fine[i + 1] >= fine[i] : fine[i + 1] <= fine[i],
          `${label} ${name}: monotone in endpoint direction`,
        );
      }
    }
    // Source layouts reproduce the captured baseline through the mirror.
    // Spread vm-realm arrays into main-realm arrays before comparing.
    ds.lines.forEach((line, li) => {
      const gaps = ds.gaps[li];
      const mono = [...PS.layoutMono(gaps, table.pairs, 0, 0)];
      const gray = [...PS.layoutGray(gaps, table.pairs, 0, 0)];
      const want = ds.captured[li];
      assert.deepEqual(
        profile === "mono" ? mono : gray,
        want,
        `${c.id} ${profile} line ${li}: Source-exact layout at defaults`,
      );
      // Letter spacing applies exactly once per internal gap.
      for (const letter of [-2, 4]) {
        const got = [...(profile === "mono" ? PS.layoutMono : PS.layoutGray)(gaps, table.pairs, 0, letter)];
        let k = 0;
        const pen = [0];
        let frac = 0;
        for (const g of gaps) {
          k++;
          if (g.space) {
            if (profile === "mono") pen.push(pen[k - 1] + g.metric);
            else {
              frac += g.frac;
              pen.push(pixelRound(frac));
            }
          } else {
            if (profile === "mono") pen.push(pen[k - 1] + g.metric + letter);
            else {
              frac += g.frac + letter;
              pen.push(pixelRound(frac));
            }
          }
        }
        assert.deepEqual(got, pen, `${c.id} ${profile} line ${li}: letter applied once, spaces kept`);
      }
    });
  }
}

assert.ok(pairs > 0, "endpoint records present");
assert.ok(plateaus > 0, "expected recorded strength plateaus");
assert.ok(abstentions > 0, "expected recorded abstentions");
console.log(
  JSON.stringify({
    status: "passed",
    cases: boot.cases.length,
    pairs,
    plateaus,
    abstentions,
    guarded,
    model: boot.model,
  }),
);
