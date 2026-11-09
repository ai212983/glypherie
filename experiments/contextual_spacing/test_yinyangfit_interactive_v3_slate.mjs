// cspell:words yinyangfit lslate
// Display-projection rationale pin: the letter layer renders the
// whole-glyph-normalized `slate` amplitude projection, never the
// per-query local-contrast `lslate` projection. Same oriented fields,
// same support; the fixed per-glyph denominator keeps weak far-field
// responses weak, while the halo core near ink agrees. Uses the pinned
// shipping WASM bytes. Scoring math is untouched and unasserted here.
import assert from "node:assert/strict";
import { readFileSync, copyFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const dir = dirname(fileURLToPath(import.meta.url));
const ROOT = join(dir, "..", "..");

// Page sources must never request the local-contrast component for
// letter context; worker and main-thread fallback both fetch `slate`.
for (const name of [
  "yinyangfit_interactive_v3_worker.js",
  "yinyangfit_interactive_v3_wiring.js",
  "yinyangfit_interactive_v3_visual.js",
]) {
  const src = readFileSync(join(dir, name), "utf8");
  assert.ok(!src.includes('"lslate"'), `${name} must not reference the lslate component`);
}
const workerSrc = readFileSync(join(dir, "yinyangfit_interactive_v3_worker.js"), "utf8");
assert.ok(workerSrc.includes('"slate", 0, 0'), "worker fetches the whole-glyph slate component");

// Engine-grounded rationale on pinned bytes: far-field maxima are
// strictly smaller under the whole-glyph denominator, halo-core maxima
// agree. Pinned glyphs from the active main boot (roboto-16-mono).
const LEAF = join(ROOT, "experiments", "contextual_spacing", "oriented_engine");
const EXPECT_WASM = "c27fe2e2c7d53114fbaace7829c6eec13d06e2ee28039b6a18296207dea7f855";
const cjsCopy = join(tmpdir(), `slatepin_${process.pid}.cjs`);
copyFileSync(join(LEAF, "pkg-nodejs", "yinyang_oriented_engine.js"), cjsCopy);
const { YinYangEngine } = createRequire(import.meta.url)(cjsCopy);
const engine = new YinYangEngine(null);
const version = JSON.parse(engine.version());
assert.equal(version.model, "yinyangfit-oriented-engine-v1");
assert.equal(version.score_model, "yinyangfit-local-energy-v2");
assert.equal(version.frozen_normalization_radius, 12);

const boot = JSON.parse(
  readFileSync(
    join(ROOT, "out", "diagnostics", "contextual-spacing", "yinyangfit-interactive-v3", "site-reviewed", "boot.json"),
    "utf8",
  ),
);
const prof = boot.cases.find((c) => c.id === "roboto-16").profiles.mono;
const ds = "roboto-16-mono";
for (const cp of [65, 84, 111]) {
  const g = prof.glyphs[String(cp)];
  const cover = new Float64Array(g.cover.length);
  for (let i = 0; i < g.cover.length; i++) {
    cover[i] = g.cover[i] === "1" ? 1 : 0;
  }
  engine.load_glyph(ds, prof.capture_sha256, cp, g.w, g.h, g.left, g.top, cover);
  const slate = Array.from(engine.glyph_component(ds, cp, "slate", 0, 0));
  const lslate = Array.from(engine.glyph_component(ds, cp, "lslate", 0, 0));
  const note = JSON.parse(engine.last_component_note());
  const W = note.width,
    H = note.height;
  const pad = Math.round((W - g.w + (H - g.h)) / 4);
  const ox = Math.trunc(g.left - pad),
    oy = Math.trunc(g.top - pad);
  const ink = [];
  for (let r = 0; r < g.h; r++) {
    for (let c = 0; c < g.w; c++) {
      if (g.cover[r * g.w + c] === "1") ink.push([g.left + c, g.top + r]);
    }
  }
  let outerSlate = 0,
    outerLocal = 0,
    innerSlate = 0,
    innerLocal = 0;
  for (let ly = 0; ly < H; ly++) {
    for (let lx = 0; lx < W; lx++) {
      const i = ly * W + lx;
      if (!Number.isFinite(slate[i]) || !Number.isFinite(lslate[i])) continue;
      const X = ox + lx,
        Y = oy + ly;
      let d = Infinity;
      for (const [ix, iy] of ink) {
        const q = Math.hypot(X - ix, Y - iy);
        if (q < d) d = q;
      }
      if (d >= 14) {
        if (slate[i] > outerSlate) outerSlate = slate[i];
        if (lslate[i] > outerLocal) outerLocal = lslate[i];
      } else if (d <= 3) {
        if (slate[i] > innerSlate) innerSlate = slate[i];
        if (lslate[i] > innerLocal) innerLocal = lslate[i];
      }
    }
  }
  assert.ok(outerSlate < outerLocal, `cp ${cp}: whole-glyph far max ${outerSlate} below local max ${outerLocal}`);
  const rel = Math.abs(innerSlate - innerLocal) / innerLocal;
  assert.ok(rel < 0.15, `cp ${cp}: halo core agrees (slate ${innerSlate}, lslate ${innerLocal})`);
}
console.log("slate projection checks passed");
