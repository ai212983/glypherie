// Node smoke test for the font_wasm browser-WASM port (host-executed).
//
// Build first (host-owned; wasm-bindgen CLI required):
//   tools/wasm/build.sh nodejs
//
// Run from the repository root:
//   node tools/wasm/smoke/render.mjs [font-path]
//
// The optional font-path argument (or FONT_WASM_FIXTURE) overrides the
// built-in resolution order below. This script only needs the `nodejs`
// pkg output; the `web` output is exercised by smoke.html instead.
//
// Exit status is 0 on success, 1 on the first failed assertion.
import { createRequire } from "node:module";
import { throws } from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
// wasm-bindgen `--target nodejs` emits CommonJS; require keeps this ESM
// script independent of the pkg's module format.
const { Font } = require(path.join(here, "..", "pkg-nodejs", "font_wasm.js"));

function assert(cond, message) {
  if (!cond) {
    console.error(`FAIL: ${message}`);
    process.exit(1);
  }
  console.log(`ok: ${message}`);
}

function resolveFont() {
  const candidates = [
    process.argv[2],
    process.env.FONT_WASM_FIXTURE,
    path.join(here, "fonts", "Roboto.ttf"),
    path.join(here, "..", "..", "..", "fonts", "Roboto.ttf"),
    path.join(
      here,
      "..",
      "..",
      "generator",
      "tests",
      "fixtures",
      "static-cff.otf",
    ),
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  console.error(`no fixture font found; tried: ${candidates.join(", ")}`);
  process.exit(1);
}

const fontPath = resolveFont();
console.log(`font: ${fontPath}`);
const bytes = new Uint8Array(fs.readFileSync(fontPath));

const font = new Font(bytes);
try {
  const meta = font.metadata();
  assert(typeof meta === "object" && meta !== null, "metadata() is a plain object");
  assert("names" in meta && "axes" in meta, "metadata has names/axes keys");
  assert(!(meta.names instanceof Map), "metadata names use an ordinary object");

  const spec = JSON.parse(
    fs.readFileSync(path.join(here, "spec.json"), "utf8"),
  );
  for (const extra of [{ characters: "A" }, { fontSize: 16 }]) {
    throws(
      () => {
        const unexpected = font.render({ ...spec, ...extra });
        unexpected.free();
      },
      (error) => String(error).includes("unknown field"),
    );
  }
  for (const invalid of [
    { text: "", size_px: 0 },
    { text: "", axes: { NOPE: 1 } },
    { text: "", palette: [] },
    { foreground: [-1, 0, 0, 255] },
    { width: -1 },
  ]) {
    throws(() => {
      const unexpected = font.render({ ...spec, ...invalid });
      unexpected.free();
    });
  }
  const result = font.render(spec);
  try {
    const w = result.width();
    const h = result.height();
    assert(w === spec.width && h === spec.height, `canvas is ${w}x${h}`);
    const pixels = result.pixels();
    assert(
      pixels.length === w * h * 4,
      `pixels length ${pixels.length} == w*h*4`,
    );
    assert(result.line_count() >= 1, "at least one laid-out line");
    const layout = result.layout();
    assert(
      typeof layout === "object" && Array.isArray(layout.lines),
      "layout() exposes lines",
    );
    assert(
      layout.lines.length === result.line_count(),
      "layout lines match line_count()",
    );
    const inked = pixels.some((v, i) => v !== spec.background[i % 4]);
    assert(inked, "rendered text differs from the background");
  } finally {
    result.free();
  }
} finally {
  font.free();
}
console.log("smoke: PASS");
