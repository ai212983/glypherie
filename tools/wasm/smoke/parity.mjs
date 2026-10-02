// Build tools/wasm/build.sh nodejs first, then run this from any directory.
// Compare the actual WASM module with freshly computed native output. Exact
// identity is the port contract, not an optical acceptance score.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const require = createRequire(import.meta.url);
const { Font } = require(fileURLToPath(new URL("../pkg-nodejs/font_wasm.js", import.meta.url)));
const cases = [];
function add(font, extra = {}) {
  cases.push({
    id: `case-${cases.length + 1}`, font_file: path.join(root, font),
    spec: { text: "AV To Qxy", width: 160, height: 80, ...extra },
  });
}

for (const font of ["Roboto", "Literata", "SourceSans3"]) {
  for (const size_px of [14, 20, 31.5]) {
    for (const output_bits of [1, 3, 8]) {
      const axes = { wght: 700 };
      if (font === "Roboto") axes.wdth = 80;
      if (font === "Literata") axes.opsz = size_px;
      add(`fonts/${font}.ttf`, { size_px, output_bits, axes });
    }
  }
}
for (const hinting of ["none", "auto", "interpreter", "auto_fallback"]) {
  for (const output_bits of [1, 3]) {
    add("fonts/Roboto.ttf", {
      hinting, output_bits, size_px: 18,
      foreground: [23, 48, 149, 200], background: [33, 27, 90, 40],
    });
  }
}
for (const wrap of ["clip", "word", "char"]) {
  for (const align of ["left", "center", "right"]) {
    add("fonts/Literata.ttf", {
      wrap, align, text: " AV AV ToTo\r\nQxy\nАБ Ω ", width: 45, height: 50,
      axes: { wght: 400, opsz: 16 }, output_bits: 3,
    });
  }
}
add("fonts/Roboto.ttf", { text: "", output_bits: 3, foreground: [1, 2, 3, 255], background: [0, 0, 0, 0] });
add("fonts/Roboto.ttf", { text: "\n\n" });
add("fonts/Roboto.ttf", { text: "\u0378", missing_glyphs: "skip" });
for (const font of ["static-cff.otf", "variable-cff2.otf"]) {
  add(`tools/generator/tests/fixtures/${font}`, { text: "A", hinting: "none", output_bits: 3 });
}
add("fonts/Roboto.ttf", { text: "A", output_bits: 3, foreground: [20, 30, 40, 255], background: [0, 0, 0, 0] });
add("fonts/Roboto.ttf", {
  text: "A", output_bits: 2, background: [35, 46, 57, 60],
  palette: [[0, 0, 0, 0], [123, 45, 67, 255], [1, 34, 89, 128], [29, 13, 63, 255]],
});

const native = spawnSync("cargo", [
  "run", "--locked", "--quiet", "--manifest-path", "tools/wasm/Cargo.toml", "--example", "parity_reference",
], { cwd: root, input: JSON.stringify(cases), encoding: "utf8", maxBuffer: 16 * 1024 * 1024 });
assert.equal(native.error, undefined, String(native.error));
assert.equal(native.status, 0, native.stderr);
const expected = JSON.parse(native.stdout);
assert.equal(expected.length, cases.length);
const fonts = new Map();
try {
  for (let i = 0; i < cases.length; i++) {
    const { id, font_file, spec } = cases[i];
    const reference = expected[i];
    assert.equal(reference.id, id);
    if (!fonts.has(font_file)) fonts.set(font_file, new Font(fs.readFileSync(font_file)));
    const font = fonts.get(font_file);
    if (reference.error) {
      assert.throws(() => font.render(spec), (error) => String(error) === reference.error, id);
      continue;
    }
    const result = font.render(spec);
    let copied;
    try {
      assert.equal(result.width(), reference.width, id);
      assert.equal(result.height(), reference.height, id);
      copied = result.pixels();
      assert.equal(createHash("sha256").update(copied).digest("hex"), reference.pixel_sha256, `${id} pixels`);
      assert.deepEqual(result.layout(), reference.layout, `${id} layout`);
      assert.deepEqual(font.metadata(), reference.metadata, `${id} metadata`);
    } finally {
      result.free();
    }
    // JS copies remain usable after Rust memory is freed.
    assert.equal(createHash("sha256").update(copied).digest("hex"), reference.pixel_sha256, `${id} ownership`);
  }
  console.log(`Native/WASM parity: ${cases.length}/${cases.length} exact RGBA, layout and metadata cases.`);
} finally {
  for (const font of fonts.values()) font.free();
}
