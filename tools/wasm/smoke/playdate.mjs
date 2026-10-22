// Byte parity with native Rust, plus optional official SDK compilation.
// Build with: tools/wasm/build.sh nodejs preview
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { mkdtempSync, readFileSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const require = createRequire(import.meta.url);
const { Font } = require("../pkg-nodejs-preview/font_wasm.js");
const temp = mkdtempSync(path.join(os.tmpdir(), "playdate-parity-"));
const fontFile = path.join(root, "fonts/Roboto.ttf");
const font = new Font(readFileSync(fontFile));
// Ordinary full printable ASCII, including the left-overhanging j.
const ascii = Array.from({ length: 95 }, (_, i) => String.fromCodePoint(0x20 + i)).join("");
let count = 0;
try {
  const source = path.join(temp, "Source");
  mkdirSync(source);
  writeFileSync(path.join(source, "main.lua"), "function playdate.update() end\n");
  for (const fitting of ["font_hints_first", "upstream_mono"]) {
    for (const rasterization of ["free_type_mono", "free_type_mono_terminals"]) {
      for (const spacing of [-1, 0, 2]) {
        for (const kerning of [false, true]) {
          const request = {
            config: { characters: ascii, size_px: 18, axes: { wght: 600 }, output_bits: 1, kerning,
              mono_raster: { dropout: "smart", include_stubs: true, font_instructions: true } },
            pipeline: { fitting, rasterization }, letter_spacing_px: spacing,
          };
          const requestFile = path.join(temp, "request.json");
          const outputFile = path.join(source, "font.fnt");
          writeFileSync(requestFile, JSON.stringify(request));
          execFileSync("cargo", ["run", "--quiet", "--locked", "--manifest-path", path.join(root, "tools/wasm/Cargo.toml"),
            "--features", "preview", "--example", "playdate_reference", "--", fontFile, requestFile, outputFile], { stdio: "pipe" });
          const wasm = font.export_playdate(request);
          assert.deepEqual(Buffer.from(wasm), readFileSync(outputFile), JSON.stringify(request));
          // Returned bytes remain JS-owned after another export.
          assert.deepEqual(Buffer.from(font.export_playdate(request)), Buffer.from(wasm));
          if (process.env.PLAYDATE_SDK_PATH) {
            execFileSync(path.join(process.env.PLAYDATE_SDK_PATH, "bin/pdc"), ["-sdkpath", process.env.PLAYDATE_SDK_PATH,
              source, path.join(temp, "game.pdx")], { stdio: "pipe" });
          }
          count += 1;
        }
      }
    }
  }
  const config = { characters: "AV", output_bits: 1 };
  const pipeline = { fitting: "font_hints_first", rasterization: "free_type_mono" };
  for (const request of [
    { config, pipeline, unknown: 1 },
    { config: { ...config, unknown: 1 }, pipeline },
    { config, pipeline: { ...pipeline, unknown: 1 } },
    { config: { ...config, mono_raster: { unknown: 1 } }, pipeline },
    { config: { ...config, characters: "AV\n" }, pipeline },
    { config: { ...config, output_bits: 3 }, pipeline },
    { config: { ...config, characters: "" }, pipeline },
    { config: { ...config, characters: Array.from({ length: 1025 }, (_, i) => String.fromCodePoint(0x400 + i)).join("") }, pipeline },
  ]) assert.throws(() => font.export_playdate(request));
  console.log(`${count} native/WASM Playdate exports match byte for byte; invalid requests rejected.${process.env.PLAYDATE_SDK_PATH ? " All compiled with the Playdate SDK." : " SDK compilation skipped (set PLAYDATE_SDK_PATH)."}`);
} finally {
  font.free();
  rmSync(temp, { recursive: true, force: true });
}
