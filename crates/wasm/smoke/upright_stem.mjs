// Exact native/WASM parity for the Literata upright-stem preview pipeline.
// Build first: crates/wasm/build.sh nodejs preview
// Run: node crates/wasm/smoke/upright_stem.mjs
// Standard SIMD package: build with WASM_SIMD128=1; run with UPRIGHT_STEM_SIMD128=1.
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
const previewPackage = process.env.UPRIGHT_STEM_SIMD128 === "1"
  ? "../pkg-nodejs-preview-simd128/font_wasm.js" : "../pkg-nodejs-preview/font_wasm.js";
try {
  ({ Font } = require(fileURLToPath(new URL(previewPackage, import.meta.url))));
} catch {
  throw new Error("Missing nodejs preview package; run crates/wasm/build.sh nodejs preview with the selected SIMD setting first.");
}

const FONT = "fonts/Literata.ttf";
const fontBytes = fs.readFileSync(path.join(root, FONT));
// Fixture provenance: bytes must match the recorded Literata source.
const specimens = JSON.parse(fs.readFileSync(path.join(root, "crates/generator/specimens.json"), "utf8"));
const recorded = specimens.families.find((family) => family.id === "literata").provenance.expected_sha256;
assert.equal(createHash("sha256").update(fontBytes).digest("hex"), recorded, "Literata bytes match specimens.json");

// Separated t/i/f/l plus ordinary reading context; printable ASCII only.
const TEXT = "t i f l\nminimum milling\nWe walked by the river.";
const SCAN = { dropout: "smart", include_stubs: true, font_instructions: true };
const SIZES = [12, 14, 15, 16, 17, 18, 20];
const WEIGHTS = [300, 400, 700];
const FITTINGS = ["font_hints_auto", "upstream_mono"];
const RASTERS = ["free_type_mono", "free_type_mono_terminals"];
// opsz tracks size_px per the specimen configuration.
const combos = [
  ...SIZES.map((size_px) => ({ size_px, axes: { wght: 400, opsz: size_px } })),
  ...WEIGHTS.filter((wght) => wght !== 400).map((wght) => ({ size_px: 16, axes: { wght, opsz: 16 } })),
];

const cases = [];
for (const { size_px, axes } of combos) {
  for (const fitting of FITTINGS) {
    for (const rasterization of RASTERS) {
      const base = { text: TEXT, width: 400, height: 160, size_px, axes,
        output_bits: 1, mono_raster: SCAN };
      cases.push({ id: String(cases.length), font_file: path.join(root, FONT),
        spec: { ...base, pipeline: { fitting, rasterization } } });
      cases.push({ id: String(cases.length), font_file: path.join(root, FONT),
        spec: { ...base, pipeline: { fitting, rasterization, diagonal_fitting: true } } });
    }
  }
}
assert.equal(cases.length, 72, "matrix covers 9 size/weight combos x 2 fittings x 2 rasters x on/off");
const invalid = [
  { text: TEXT, width: 400, height: 160, size_px: 16, axes: { wght: 400, opsz: 16 },
    output_bits: 1, mono_raster: SCAN,
    pipeline: { fitting: "font_hints_auto", rasterization: "coverage", diagonal_fitting: true } },
  { text: TEXT, width: 400, height: 160, size_px: 16, axes: { wght: 400, opsz: 16 },
    output_bits: 1, mono_raster: SCAN,
    pipeline: { fitting: "source_relative", rasterization: "free_type_mono", diagonal_fitting: true } },
];
const invalidStart = cases.length;
for (const spec of invalid) {
  cases.push({ id: String(cases.length), font_file: path.join(root, FONT), spec });
}

const native = spawnSync("cargo", ["run", "--release", "--locked", "--quiet", "--manifest-path", "crates/wasm/Cargo.toml",
  "--features", "preview", "--example", "parity_reference"],
{ cwd: root, input: JSON.stringify(cases), encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
assert.equal(native.error, undefined, String(native.error));
assert.equal(native.status, 0, native.stderr);
const expected = JSON.parse(native.stdout);
assert.equal(expected.length, cases.length, "oracle covers every case");

const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
const seen = new Map();
let font = new Font(fontBytes);
try {
  for (let i = 0; i < invalidStart; i += 2) {
    const layouts = [];
    for (const offset of [0, 1]) {
      const entry = cases[i + offset], oracle = expected[i + offset];
      // Every matrix case must succeed natively; error parity is not a pass here.
      assert.equal(oracle.error, undefined, `native ${entry.id}`);
      assert.deepEqual(oracle.metadata, expected[0].metadata, `metadata ${entry.id}`);
      const result = font.render(entry.spec);
      try {
        assert.equal(result.width(), oracle.width, `width ${entry.id}`);
        assert.equal(result.height(), oracle.height, `height ${entry.id}`);
        seen.set(entry.id, sha(result.pixels()));
        assert.equal(seen.get(entry.id), oracle.pixel_sha256, `pixels ${entry.id}`);
        const layout = result.layout();
        assert.deepEqual(layout, oracle.layout, `layout ${entry.id}`);
        layouts.push(layout);
      } finally { result.free(); }
    }
    // Fitting selection leaves finalized metrics untouched.
    assert.deepEqual(layouts[1], layouts[0], `on/off layout ${cases[i + 1].id}`);
  }
  assert.deepEqual(font.metadata(), expected[0].metadata, "wasm metadata matches native");
  // Omitted and explicit false share the serde default.
  const probe = { text: TEXT, width: 400, height: 160, size_px: 16, axes: { wght: 400, opsz: 16 },
    output_bits: 1, mono_raster: SCAN,
    pipeline: { fitting: "font_hints_auto", rasterization: "free_type_mono_terminals" } };
  const omitted = font.render(probe);
  const explicit = font.render({ ...probe, pipeline: { ...probe.pipeline, diagonal_fitting: false } });
  try {
    assert.equal(sha(explicit.pixels()), sha(omitted.pixels()), "omitted/false diagonal flag");
  } finally { omitted.free(); explicit.free(); }
  // Invalid combinations fail on both sides, including the flag with coverage output.
  for (let i = invalidStart; i < cases.length; i++) {
    assert.notEqual(expected[i].error, undefined, `native rejects ${cases[i].id}`);
    assert.throws(() => font.render(cases[i].spec), `wasm rejects ${cases[i].id}`);
  }
} finally { font.free(); }

// Reuse and request order: a fresh instance over the same bytes, reversed,
// must reproduce every recorded hash.
font = new Font(fontBytes);
try {
  for (let i = invalidStart - 1; i >= 0; i--) {
    const entry = cases[i];
    const result = font.render(entry.spec);
    try {
      assert.equal(sha(result.pixels()), seen.get(entry.id), `reordered pixels ${entry.id}`);
    } finally { result.free(); }
  }
} finally { font.free(); }

// Playdate export carries the same pipeline; bytes must match the native export.
const exportChars = [...new Set(TEXT.replace(/\n/g, ""))].join("");
const exportFont = new Font(fontBytes);
try {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "upright-stem-export-"));
  try {
    for (const diagonal_fitting of [false, true]) {
      const request = { config: { characters: exportChars, size_px: 16, axes: { wght: 400, opsz: 16 },
        output_bits: 1, kerning: true, mono_raster: SCAN },
        pipeline: { fitting: "font_hints_auto", rasterization: "free_type_mono_terminals",
          ...(diagonal_fitting ? { diagonal_fitting: true } : {}) },
        letter_spacing_px: 0 };
      const requestFile = path.join(temp, "request.json"), outputFile = path.join(temp, "font.fnt");
      fs.writeFileSync(requestFile, JSON.stringify(request));
      execFileSync("cargo", ["run", "--release", "--quiet", "--locked", "--manifest-path", path.join(root, "crates/wasm/Cargo.toml"),
        "--features", "preview", "--example", "playdate_reference",
        "--", path.join(root, FONT), requestFile, outputFile], { stdio: "pipe" });
      const wasm = exportFont.export_playdate(request);
      assert.deepEqual(Buffer.from(wasm), fs.readFileSync(outputFile), `export diagonal ${diagonal_fitting}`);
    }
  } finally { fs.rmSync(temp, { recursive: true, force: true }); }
} finally { exportFont.free(); }

console.log(`Upright-stem Literata native/WASM parity passed for ${invalidStart} render cases plus export parity.`);
