// Exact native/WASM parity for the diagonal opt-in (pipeline.diagonal_fitting).
// Build first: tools/wasm/build.sh nodejs preview
// Run: node tools/wasm/smoke/diagonal_fitting.mjs
// Focused 36-case first pass: DIAGONAL_FOCUS=1 node tools/wasm/smoke/diagonal_fitting.mjs
// Reviewed ASCII corpus: DIAGONAL_CORPUS=1 node tools/wasm/smoke/diagonal_fitting.mjs
// Default settings: DIAGONAL_DEFAULTS=1 node tools/wasm/smoke/diagonal_fitting.mjs
// Standard SIMD package: build with WASM_SIMD128=1; run with DIAGONAL_SIMD128=1.
// Split the matrix into independent processes: DIAGONAL_SHARD=0/6 (through 5/6).
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const require = createRequire(import.meta.url);
let Font;
const previewPackage = process.env.DIAGONAL_SIMD128 === "1"
  ? "../pkg-nodejs-preview-simd128/font_wasm.js" : "../pkg-nodejs-preview/font_wasm.js";
try {
  ({ Font } = require(fileURLToPath(new URL(previewPackage, import.meta.url))));
} catch {
  throw new Error("Missing nodejs preview package; run tools/wasm/build.sh nodejs preview with the selected SIMD setting first.");
}

// Frozen exercise text; export repertoire is its distinct characters.
const corpus = process.env.DIAGONAL_CORPUS === "1";
const defaults = process.env.DIAGONAL_DEFAULTS === "1";
const [shardIndex, shardCount] = (process.env.DIAGONAL_SHARD ?? "0/1").split("/").map(Number);
assert.ok(Number.isInteger(shardIndex) && Number.isInteger(shardCount)
  && shardCount > 0 && shardIndex >= 0 && shardIndex < shardCount, "invalid DIAGONAL_SHARD index/count");
const TEXT = corpus ? Array.from({ length: 95 }, (_, i) => String.fromCodePoint(i + 32)).join(" ")
  : "cC kyxzvAW sX2 M^ We walked by the river.";
const CHARACTERS = [...new Set(TEXT)].join("");
const SIZES = defaults ? [16] : corpus ? [12, 14, 16, 18, 20, 24] : [12, 16, 24];
const WEIGHTS = defaults ? [400] : [300, 400, 700];
const FITTINGS = ["font_hints_auto", "upstream_mono"];
const RASTERS = ["free_type_mono", "free_type_mono_terminals"];
const FONTS = process.env.DIAGONAL_FOCUS === "1" ? ["fonts/Roboto.ttf"] : ["fonts/Roboto.ttf", "fonts/SourceSans3.ttf", "fonts/RobotoFlex.ttf"];
const axesFor = (font, wght) => font.endsWith("Roboto.ttf") ? { wght, wdth: 100 } : { wght };

const cases = [];
let pairCount = 0;
let matrixPair = 0;
for (const font of FONTS) {
  for (const size_px of SIZES) {
    for (const wght of WEIGHTS) {
      for (const fitting of FITTINGS) {
        for (const rasterization of RASTERS) {
          const defaultControl = font.endsWith("Roboto.ttf") && size_px === 16 && wght === 400
            && fitting === "font_hints_auto" && rasterization === "free_type_mono";
          if (matrixPair++ % shardCount !== shardIndex && !defaultControl) continue;
          const base = { text: TEXT, width: corpus ? 800 : 400, height: corpus ? 384 : 160,
            size_px, axes: axesFor(font, wght), output_bits: 1 };
          cases.push({ id: String(cases.length), font_file: path.resolve(root, font),
            spec: { ...base, pipeline: { fitting, rasterization } } });
          cases.push({ id: String(cases.length), font_file: path.resolve(root, font),
            spec: { ...base, pipeline: { fitting, rasterization, diagonal_fitting: true } } });
          pairCount += 1;
        }
      }
    }
  }
}
const invalid = [];
for (const text of [TEXT, ""]) {
  invalid.push(
    { text, width: 400, height: 160, size_px: 16, axes: { wght: 400, wdth: 100 }, output_bits: 3,
      pipeline: { fitting: "font_hints_auto", rasterization: "coverage", diagonal_fitting: true } },
    { text, width: 400, height: 160, size_px: 16, axes: { wght: 400, wdth: 100 }, output_bits: 1,
      pipeline: { fitting: "font_hints_auto", rasterization: "coverage", diagonal_fitting: true } },
    { text, width: 400, height: 160, size_px: 16, axes: { wght: 400, wdth: 100 }, output_bits: 1,
      pipeline: { fitting: "source_relative", rasterization: "free_type_mono", diagonal_fitting: true } },
    { text, width: 400, height: 160, size_px: 16, axes: { wght: 400, wdth: 100 }, output_bits: 1,
      pipeline: { fitting: "font_hints_first", rasterization: "free_type_mono", diagonal_fitting: true } },
  );
}
const invalidStart = cases.length;
for (const spec of invalid) {
  cases.push({ id: String(cases.length), font_file: path.resolve(root, "fonts/Roboto.ttf"), spec });
}

const started = performance.now();
const native = spawnSync("cargo", ["run", "--release", "--locked", "--quiet", "--manifest-path", "tools/wasm/Cargo.toml",
  "--features", "preview", "--example", "parity_reference"],
{ cwd: root, input: JSON.stringify(cases), encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
assert.equal(native.error, undefined, String(native.error));
assert.equal(native.status, 0, native.stderr);
const expected = JSON.parse(native.stdout);
const oracleMs = performance.now() - started;

const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
const fonts = new Map();
const changed = [];
let wasmMs = 0;
try {
  const begin = performance.now();
  for (let i = 0; i < pairCount * 2; i += 2) {
    const off = cases[i], on = cases[i + 1];
    const file = off.font_file;
    if (!fonts.has(file)) fonts.set(file, new Font(fs.readFileSync(file)));
    const font = fonts.get(file);
    const layouts = [];
    for (const [entry, oracle] of [[off, expected[i]], [on, expected[i + 1]]]) {
      assert.equal(oracle.error, undefined, `native ${entry.id}`);
      const result = font.render(entry.spec);
      try {
        assert.equal(sha(result.pixels()), oracle.pixel_sha256, `pixels ${entry.id}`);
        const layout = result.layout();
        assert.deepEqual(layout, oracle.layout, `layout ${entry.id}`);
        layouts.push(layout);
      } finally { result.free(); }
    }
    // Shared bitmap layout is metric policy: identical advances with/without fitting.
    assert.deepEqual(layouts[1], layouts[0], `on/off layout ${on.id}`);
    if (off.spec.size_px === 16 && off.spec.axes.wght === 400 && off.font_file.endsWith("Roboto.ttf")) {
      changed.push([expected[i].pixel_sha256, expected[i + 1].pixel_sha256]);
    }
  }
  // Omitted and explicit false are the same serde default.
  const probe = { text: TEXT, width: 400, height: 160, size_px: 16, axes: { wght: 400, wdth: 100 },
    output_bits: 1, pipeline: { fitting: "font_hints_auto", rasterization: "free_type_mono_terminals" } };
  const font = fonts.get(path.resolve(root, "fonts/Roboto.ttf"));
  for (const fitting of FITTINGS) {
    for (const rasterization of RASTERS) {
      const spec = { ...probe, pipeline: { fitting, rasterization } };
      const omitted = font.render(spec), explicit = font.render({ ...spec,
        pipeline: { ...spec.pipeline, diagonal_fitting: false } });
      try {
        assert.equal(sha(explicit.pixels()), sha(omitted.pixels()), `omitted/false ${fitting}/${rasterization}`);
      } finally { omitted.free(); explicit.free(); }
    }
  }
  // Invalid combinations fail natively and in WASM, including blank text.
  for (let i = invalidStart; i < cases.length; i++) {
    assert.notEqual(expected[i].error, undefined, `native rejects ${cases[i].id}`);
    assert.throws(() => font.render(cases[i].spec), `wasm rejects ${cases[i].id}`);
  }
  for (const text of [TEXT, ""]) {
    for (const diagonal_fitting of ["yes", 1, null]) {
      assert.throws(() => font.render({ ...probe, text,
        pipeline: { fitting: "font_hints_auto", rasterization: "free_type_mono", diagonal_fitting } }));
    }
    assert.throws(() => font.render({ ...probe, text, pipeline: undefined,
      renderer: "candidate", diagonal_fitting: true }));
  }
  wasmMs = performance.now() - begin;
} finally { for (const font of fonts.values()) font.free(); }
// At least one default 400/16 native pair must change, proving a live path.
assert.ok(changed.some(([a, b]) => a !== b), "diagonal fitting changed no default Roboto 400/16 output");

// Playdate export forwards the flag; parity follows the existing export smoke style.
const exportShas = [];
let exportMs = 0;
// Every shard covers render routing; one covers the shared export route.
if (shardIndex === 0) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "diagonal-export-"));
  const exportFont = new Font(fs.readFileSync(path.join(root, "fonts/Roboto.ttf")));
  try {
    const begin = performance.now();
    for (const fitting of FITTINGS) {
      for (const diagonal_fitting of [false, true]) {
        const request = { config: { characters: CHARACTERS, size_px: 16, axes: { wght: 400, wdth: 100 },
          output_bits: 1, kerning: true,
          mono_raster: { dropout: "smart", include_stubs: true, font_instructions: true } },
          pipeline: { fitting, rasterization: "free_type_mono_terminals", ...(diagonal_fitting ? { diagonal_fitting: true } : {}) },
          letter_spacing_px: 0 };
        const requestFile = path.join(temp, "request.json"), outputFile = path.join(temp, "font.fnt");
        fs.writeFileSync(requestFile, JSON.stringify(request));
        execFileSync("cargo", ["run", "--release", "--quiet", "--locked", "--manifest-path", path.join(root, "tools/wasm/Cargo.toml"),
          "--features", "preview", "--example", "playdate_reference",
          "--", path.join(root, "fonts/Roboto.ttf"), requestFile, outputFile], { stdio: "pipe" });
        const wasm = exportFont.export_playdate(request);
        assert.deepEqual(Buffer.from(wasm), fs.readFileSync(outputFile), JSON.stringify(request.pipeline));
        exportShas.push(sha(wasm));
      }
    }
    const gray = { config: { characters: CHARACTERS, size_px: 16, axes: {}, output_bits: 3, kerning: true },
      pipeline: { fitting: "font_hints_auto", rasterization: "coverage", diagonal_fitting: true }, letter_spacing_px: 0 };
    assert.throws(() => exportFont.export_playdate(gray), "gray export rejects the flag");
    exportMs = performance.now() - begin;
  } finally { exportFont.free(); fs.rmSync(temp, { recursive: true, force: true }); }
}

console.log(JSON.stringify({ cases: cases.length, corpus, defaults, shard: [shardIndex, shardCount], focus: process.env.DIAGONAL_FOCUS === "1",
  defaultChangedPairs: changed.filter(([a, b]) => a !== b).length, exportShas,
  ms: { oracle: Math.round(oracleMs), wasm: Math.round(wasmMs), export: Math.round(exportMs) } }));
console.log(`Diagonal opt-in native/WASM parity passed for ${cases.length} render cases${exportShas.length ? " plus export parity" : ""}.`);
