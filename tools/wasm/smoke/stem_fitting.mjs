// Build `tools/wasm/build.sh nodejs preview` first. Optional arguments are
// additional font paths, exercising runtime font bytes outside the fixtures.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const require = createRequire(import.meta.url);
const { Font } = require(fileURLToPath(new URL("../pkg-nodejs-preview/font_wasm.js", import.meta.url)));
const inputs = [
  ...[13, 14, 15, 16].map(size_px => ["fonts/Roboto.ttf", size_px, { wght: 400, wdth: 100 }]),
  ["fonts/Roboto-Italic.ttf", 14, { wght: 400, wdth: 100 }],
  ["fonts/SourceSans3.ttf", 14, { wght: 400 }],
  ["fonts/Literata.ttf", 14, { wght: 400, opsz: 14 }],
  ["fonts/RobotoFlex.ttf", 14, { wght: 400, wdth: 100, opsz: 14, slnt: -10 }],
  ...process.argv.slice(2).map(font => [path.resolve(font), 14, {}]),
];
for (const size of [12, 14, 16, 18, 20]) {
  for (const weight of [200, 400, 700]) inputs.push(["fonts/SourceSans3.ttf", size, { wght: weight }]);
}
for (const font of ["static-cff.otf", "variable-cff2.otf"]) {
  inputs.push([`tools/generator/tests/fixtures/${font}`, 16, {}, "A"]);
}
inputs.push(["fonts/Roboto.ttf", 512, { wght: 400, wdth: 100 }, "Ax"]);
const cases = [];
for (const [font, size_px, axes, text = "mut Avo xckwe\nminimum"] of inputs) {
  for (const fitting of ["font_hints_first", "upstream_mono", "source_relative", "font_hints_auto"]) {
    for (const rasterization of ["free_type_mono", "free_type_mono_terminals", "coverage"]) {
      if (["source_relative", "font_hints_auto"].includes(fitting) && rasterization === "coverage") continue;
      cases.push({
        id: String(cases.length), font_file: path.resolve(root, font),
        spec: { text, width: size_px > 128 ? 1024 : 180, height: size_px > 128 ? 768 : 60, size_px, axes,
          output_bits: 1, pipeline: { fitting, rasterization } },
      });
    }
  }
  cases.push({
    id: String(cases.length), font_file: path.resolve(root, font),
    spec: { text, width: size_px > 128 ? 1024 : 180, height: size_px > 128 ? 768 : 60, size_px, axes,
      output_bits: 3, pipeline: { fitting: "upstream_mono", rasterization: "coverage" } },
  });
  for (const stem_fitting of [undefined, "font_hints_first", "upstream_mono"]) {
    cases.push({
      id: String(cases.length), font_file: path.resolve(root, font),
      spec: { text, width: size_px > 128 ? 1024 : 180, height: size_px > 128 ? 768 : 60, size_px, axes,
        hinting: "auto", output_bits: 1, renderer: "candidate",
        ...(stem_fitting ? { stem_fitting } : {}) },
    });
  }
  for (const mono_raster of [
    ...["off", "simple", "smart"].flatMap(dropout =>
      [false, true].map(include_stubs => ({ dropout, include_stubs }))),
    { font_instructions: true },
  ]) {
    cases.push({
      id: String(cases.length), font_file: path.resolve(root, font),
      spec: { text, width: size_px > 128 ? 1024 : 180, height: size_px > 128 ? 768 : 60, size_px, axes,
        hinting: "auto", output_bits: 1, renderer: "candidate", mono_raster },
    });
  }
}
const native = spawnSync("cargo", ["run", "--locked", "--quiet", "--manifest-path", "tools/wasm/Cargo.toml",
  "--features", "preview", "--example", "parity_reference"],
{ cwd: root, input: JSON.stringify(cases), encoding: "utf8", maxBuffer: 16 * 1024 * 1024 });
assert.equal(native.error, undefined, String(native.error));
assert.equal(native.status, 0, native.stderr);
const expected = JSON.parse(native.stdout);
const fonts = new Map();
try {
  for (let i = 0; i < cases.length; i++) {
    const { font_file, spec } = cases[i];
    if (!fonts.has(font_file)) fonts.set(font_file, new Font(fs.readFileSync(font_file)));
    const font = fonts.get(font_file), oracle = expected[i];
    assert.equal(oracle.error, undefined);
    const result = font.render(spec);
    try {
      assert.equal(createHash("sha256").update(result.pixels()).digest("hex"), oracle.pixel_sha256, `pixels ${i}`);
      assert.deepEqual(result.layout(), oracle.layout, `layout ${i}`);
    } finally { result.free(); }
  }
  const font = fonts.values().next().value, spec = cases.find(entry => entry.spec.renderer === "candidate").spec;
  const blank = font.render({ ...spec, text: "", stem_fitting: "upstream_mono" });
  blank.free();
  for (const change of [{ renderer: "baseline" }, { output_bits: 3 }, { hinting: "none" },
    { stem_fitting: "strokestyles" }, { stem_fitting: "vertical_only" }]) {
    assert.throws(() => font.render({ ...spec, stem_fitting: "upstream_mono", ...change }));
  }
  for (const mono_raster of [{ font_instructions: "yes" }, { dropout: "invalid" }, { include_stubs: 1 }]) {
    assert.throws(() => font.render({ ...spec, mono_raster }));
  }
  assert.throws(() => font.render({ ...spec, renderer: "baseline", mono_raster: { font_instructions: true } }));
  const stages = { ...spec, pipeline: { fitting: "font_hints_first", rasterization: "free_type_mono" } };
  delete stages.renderer;
  for (const text of ["", "AV"]) {
    for (const change of [{ renderer: "candidate" }, { stem_fitting: "upstream_mono" },
      { pipeline: { fitting: "font_hints_first", rasterization: "unknown" } },
      { pipeline: { fitting: "font_hints_first", rasterization: "coverage", extra: true } }]) {
      assert.throws(() => font.render({ ...stages, text, ...change }));
    }
  }
  // Uniform tracking is forwarded on the separated pipeline: every advance,
  // including spaces and the final glyph advance, keeps the whole-pixel step.
  for (const text of ["AV", "A V"]) {
    const neutral = font.render({ ...stages, text });
    const tracked = font.render({ ...stages, text, letter_spacing_px: 1 });
    try {
      assert.equal(tracked.layout().lines[0].width_26_6 - neutral.layout().lines[0].width_26_6,
        text.length * 64);
    } finally { neutral.free(); tracked.free(); }
  }
} finally { for (const font of fonts.values()) font.free(); }
console.log(`Exact native/WASM fitting and scan-policy parity passed for ${cases.length} cases, including capability guards`);
