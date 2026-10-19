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
const cases = [];
for (const [font, size_px, axes] of inputs) {
  for (const stem_fitting of [undefined, "font_hints_first", "upstream_mono"]) {
    cases.push({
      id: String(cases.length), font_file: path.resolve(root, font),
      spec: { text: "mut Avo\nminimum", width: 180, height: 60, size_px, axes,
        hinting: "auto", output_bits: 1, renderer: "candidate",
        ...(stem_fitting ? { stem_fitting } : {}) },
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
  const font = fonts.values().next().value, spec = cases[0].spec;
  const blank = font.render({ ...spec, text: "", stem_fitting: "upstream_mono" });
  blank.free();
  for (const change of [{ renderer: "baseline" }, { output_bits: 3 }, { hinting: "none" },
    { stem_fitting: "strokestyles" }, { stem_fitting: "vertical_only" }]) {
    assert.throws(() => font.render({ ...spec, stem_fitting: "upstream_mono", ...change }));
  }
} finally { for (const font of fonts.values()) font.free(); }
console.log(`Exact native/WASM stem-fitting parity passed for ${cases.length} cases, including capability guards`);
