// Exact native/WASM parity for compensated spacing (automatic-Mono bearing
// residuals resolved once into whole-pixel pair adjustments with source
// kerning). Build first: tools/wasm/build.sh nodejs preview
// Run: node tools/wasm/smoke/fitting_compensation.mjs
// Covers four fonts at 12/16/24 px with kerning on/off, word wrapping under
// compensation, Playdate export parity with kerning on/off, and the Literata
// strict policy (unsupported pairs stay skipped, unsupported text errors).
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
try {
  ({ Font } = require(fileURLToPath(new URL("../pkg-nodejs-preview/font_wasm.js", import.meta.url))));
} catch {
  throw new Error("Missing nodejs preview package; run tools/wasm/build.sh nodejs preview first.");
}

// Witness words carrying nonzero source kern pairs, plus digits/punctuation.
const TEXT = "AT AV AW AY FA FJ LO LT To VA YA 0123456789 .,— Fine river";
const FONTS = [
  ["fonts/Roboto.ttf", (size_px) => ({ wght: 400, wdth: 100 })],
  ["fonts/RobotoFlex.ttf", (size_px) => ({ wght: 400, wdth: 100, opsz: 14, slnt: 0 })],
  ["fonts/SourceSans3.ttf", (size_px) => ({ wght: 400 })],
  ["fonts/Literata.ttf", (size_px) => ({ wght: 400, opsz: size_px })],
];
const SIZES = [12, 16, 24];
const pipeline = { fitting: "upstream_mono", rasterization: "free_type_mono", diagonal_fitting: true };

const cases = [];
for (const [font, axesFor] of FONTS) {
  for (const size_px of SIZES) {
    for (const kerning of [true, false]) {
      cases.push({ id: String(cases.length),
        font_file: path.resolve(root, font),
        spec: { text: TEXT, width: 640, height: 80, size_px, axes: axesFor(size_px),
          output_bits: 1, kerning, pipeline } });
    }
    cases.push({ id: String(cases.length),
      font_file: path.resolve(root, font),
      spec: { text: TEXT, width: 160, height: 240, size_px, axes: axesFor(size_px),
        output_bits: 1, kerning: true, wrap: "word", pipeline } });
  }
}
// One declared expected error: tab needs unsupported text-run shaping, and
// the native message must match the WASM rejection. Every other case below
// must succeed natively; an unrelated native regression fails this smoke.
const TAB_ERROR = "U+0009 requires unsupported text-run shaping";
const expectedErrors = new Map();
expectedErrors.set(String(cases.length), TAB_ERROR);
cases.push({ id: String(cases.length),
  font_file: path.resolve(root, "fonts/Roboto.ttf"),
  spec: { text: "A\tB", width: 200, height: 60, size_px: 16, axes: { wght: 400, wdth: 100 },
    output_bits: 1, pipeline } });

const native = spawnSync("cargo", ["run", "--release", "--locked", "--quiet",
  "--manifest-path", "tools/wasm/Cargo.toml", "--features", "preview",
  "--example", "parity_reference"],
{ cwd: root, input: JSON.stringify(cases), encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
assert.equal(native.error, undefined, String(native.error));
assert.equal(native.status, 0, native.stderr);
const expected = JSON.parse(native.stdout);
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
const fonts = new Map();
try {
  for (let i = 0; i < cases.length; i++) {
    const { font_file, spec } = cases[i], oracle = expected[i];
    if (!fonts.has(font_file)) fonts.set(font_file, new Font(fs.readFileSync(font_file)));
    const font = fonts.get(font_file);
    const declared = expectedErrors.get(cases[i].id);
    if (declared !== undefined) {
      assert.ok(oracle.error !== undefined && oracle.error.includes(declared),
        `native declares tab error ${cases[i].id}: ${oracle.error}`);
      assert.throws(() => font.render(spec),
        (error) => String(error).includes(declared), `wasm tab error ${cases[i].id}`);
      continue;
    }
    assert.equal(oracle.error, undefined, `native must succeed ${cases[i].id}`);
    const result = font.render(spec);
    try {
      assert.equal(sha(result.pixels()), oracle.pixel_sha256, `pixels ${cases[i].id}`);
      assert.deepEqual(result.layout(), oracle.layout, `layout ${cases[i].id}`);
    } finally { result.free(); }
  }
} finally { for (const font of fonts.values()) font.free(); }

// Playdate export parity with kerning on/off under the same pipeline.
const temp = fs.mkdtempSync(path.join(os.tmpdir(), "compensation-export-"));
try {
  for (const [fontFile, axesFor] of [FONTS[0], FONTS[3]]) {
    const exportFont = new Font(fs.readFileSync(path.resolve(root, fontFile)));
    try {
      for (const kerning of [true, false]) {
        const request = { config: { characters: "ATVLYofar -.012", size_px: 16,
          axes: axesFor(16), output_bits: 1, kerning }, pipeline, letter_spacing_px: 0 };
        const requestFile = path.join(temp, "request.json");
        const outputFile = path.join(temp, "font.fnt");
        fs.writeFileSync(requestFile, JSON.stringify(request));
        execFileSync("cargo", ["run", "--release", "--quiet", "--locked", "--manifest-path",
          path.join(root, "tools/wasm/Cargo.toml"), "--features", "preview", "--example",
          "playdate_reference", "--", path.resolve(root, fontFile), requestFile, outputFile],
        { stdio: "pipe" });
        assert.deepEqual(Buffer.from(exportFont.export_playdate(request)),
          fs.readFileSync(outputFile), `${fontFile} kerning=${kerning}`);
      }
    } finally { exportFont.free(); }
  }
} finally { fs.rmSync(temp, { recursive: true, force: true }); }

// Literata descriptive inspection only: the ASCII pair table keeps reporting
// its unsupported pairs as skipped rather than filling them with zeros. This
// asserts the counter, not a render of a specific unsupported pair.
const literata = new Font(fs.readFileSync(path.join(root, "fonts/Literata.ttf")));
try {
  assert.equal(literata.kerning_pairs(16, { wght: 400, opsz: 16 }).skipped_pairs, 27);
} finally { literata.free(); }

console.log(`Compensated-spacing native/WASM parity passed for ${cases.length} render cases plus export parity.`);
