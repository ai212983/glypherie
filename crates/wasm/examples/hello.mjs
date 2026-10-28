// Minimal Node example: render "Hello" to a raw RGBA file (host-executed).
//
// Build first: crates/wasm/build.sh nodejs
// Run from the repository root:
//   node crates/wasm/examples/hello.mjs [font-path] [out-path]
//
// Expected console output (Roboto at 16 px):
//   wrote hello.rgba (96x32, 12288 bytes)
//   lines: 1, missing: 0
//
// The output is raw row-major RGBA with no header (width*height*4 bytes).
// Decode it without new dependencies, e.g. with Python + Pillow:
//   from PIL import Image
//   Image.frombytes("RGBA", (96, 32), open("hello.rgba","rb").read()).show()
// or with ImageMagick:
//   magick -size 96x32 -depth 8 rgba:hello.rgba hello.png
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const { Font } = require(path.join(here, "..", "pkg-nodejs", "font_wasm.js"));

const fontPath =
  process.argv[2] ??
  path.join(here, "..", "..", "..", "fonts", "Roboto.ttf");
const outPath = process.argv[3] ?? path.join(process.cwd(), "hello.rgba");

const font = new Font(new Uint8Array(fs.readFileSync(fontPath)));
try {
  const result = font.render({ text: "Hello", width: 96, height: 32 });
  try {
    fs.writeFileSync(outPath, Buffer.from(result.pixels()));
    console.log(
      `wrote ${outPath} (${result.width()}x${result.height()}, ${result.pixels().length} bytes)`,
    );
    console.log(
      `lines: ${result.line_count()}, missing: ${result.layout().missing_codepoints.length}`,
    );
  } finally {
    result.free();
  }
} finally {
  font.free();
}
