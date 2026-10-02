# font_wasm

<!-- cspell:words rustup bindgen BINDGEN rgba COLR CBDT sbix texel texels -->

Browser/Node port of the approved Rust font renderer. It reuses `generate()` through
`font_generator::surface::render_text` with the approved skrifa-baseline snapshot: no fitting or model code lives here,
so rendering parity with the native path is the contract.

## Build

Prerequisites:

- Rust target `wasm32-unknown-unknown` (`rustup target add wasm32-unknown-unknown`)
- `wasm-bindgen` CLI (`cargo install wasm-bindgen-cli --locked`; the version must match the crate's `wasm-bindgen`
  dependency)

```sh
tools/wasm/build.sh web      # browser ESM -> tools/wasm/pkg-web/
tools/wasm/build.sh nodejs   # Node (smoke + examples) -> tools/wasm/pkg-nodejs/
tools/wasm/build.sh bundler  # bundler pipeline -> tools/wasm/pkg-bundler/
```

Each target writes an isolated package directory (`font_wasm.js` + `font_wasm_bg.wasm`, plus `.d.ts`), so a Node build
never overwrites the web artifact. `WASM_BINDGEN` may point at a specific `wasm-bindgen` binary (the version must match
the crate's `wasm-bindgen` dependency, currently 0.2.129); the script uses `cargo --locked` throughout and prefers a
preinstalled `wasm32-unknown-unknown` std, falling back to the documented system-source `RUSTC_BOOTSTRAP=1 ... -Z
build-std=std,panic_abort` build when only the library sources are present. Generated `pkg-*/` and `target/` directories
are git-ignored.

Verify the Node package:

```sh
node tools/wasm/smoke/render.mjs [font-path]   # needs the nodejs pkg
node tools/wasm/smoke/parity.mjs              # exact native/WASM comparison; needs Cargo
node --check tools/wasm/smoke/render.mjs tools/wasm/examples/hello.mjs
```

The parity harness recomputes native results for 51 cases spanning the shipped fonts, axes, fractional sizes, hinting,
coverage depths, wrapping, clipping, alignment, transparency, palettes, blank text and CFF/CFF2 outlines. It compares
RGBA bytes, layout and metadata with the actual WASM module, without historical pixel snapshots.

## Usage

```js
import init, { Font } from "./pkg-web/font_wasm.js";
await init(); // web target only; the nodejs target loads synchronously
const font = new Font(bytes); // bytes: Uint8Array (copied); throws if invalid
try {
  const meta = font.metadata(); // plain JS object, see below
  const result = font.render({ text: "Hello", width: 200, height: 60 });
  try {
    const rgba = result.pixels(); // fresh Uint8Array copy, w*h*4 bytes
    canvas.getContext("2d").putImageData(
      new ImageData(new Uint8ClampedArray(rgba.buffer), result.width(), result.height()),
      0, 0,
    );
  } finally {
    result.free();
  }
} finally {
  font.free();
}
```

## Ownership

`Font` and `RenderResult` hold Rust-side memory and must be freed with `.free()` (use `try/finally`). `pixels()` returns
a new JS-owned copy on every call, so freeing the result never invalidates an already returned array. Errors surface as
thrown JS strings carrying the generator message only.

## Input restrictions

- Single sfnt TTF/OTF outline fonts (`glyf`/`CFF`/`CFF2`). Font collections, WOFF/WOFF2 and bitmap-only fonts are
  rejected (convert first).
- Color fonts (`COLR`/`SVG`/`CBDT`/`sbix` tables) are rejected; there is no color-font output adapter.
- Supported scripts: Latin, Greek, Cyrillic and Common symbols, plus pair kerning representable as advance adjustments.
  Combining marks, controls and format characters (including tab) and other scripts are hard errors. There is no complex
  shaping: no ligatures, contextual alternates, or mark positioning.
- The render spec has no `characters` field: the repertoire always comes from `text`, and unknown spec fields (including
  `characters`) are rejected.

## Render-spec controls

Only `text`, `width` and `height` are required; everything else has a default.

| Field             | Default             | Meaning                                                                                                                                                                                                                                                                                                                   |
| ----------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `text`            | (required)          | Source text; lines split on `\n`, `\r\n`, `\r`. Max 8192 characters.                                                                                                                                                                                                                                                      |
| `width`, `height` | (required)          | Exact canvas size, each 1..=4096.                                                                                                                                                                                                                                                                                         |
| `size_px`         | 16                  | Glyph size, 1..=512.                                                                                                                                                                                                                                                                                                      |
| `axes`            | `{}`                | Plain object of variation axis values, e.g. `{ wght: 700 }`. Unknown or out-of-range axes are errors.                                                                                                                                                                                                                     |
| `hinting`         | `"auto"`            | `"none"`, `"auto"`, `"interpreter"`, `"auto_fallback"`.                                                                                                                                                                                                                                                                   |
| `output_bits`     | 1                   | Coverage bit depth: 1, 2, 3, 4 or 8 bits per texel.                                                                                                                                                                                                                                                                       |
| `mono_threshold`  | 128                 | 1-bit quantization cutoff, 1..=255.                                                                                                                                                                                                                                                                                       |
| `gray_gamma`      | 1.0                 | Gray coverage gamma; finite and positive.                                                                                                                                                                                                                                                                                 |
| `kerning`         | true                | Pair-kerning adjustments.                                                                                                                                                                                                                                                                                                 |
| `metric_rounding` | `"subpixel"`        | `"subpixel"` or `"pixel"`.                                                                                                                                                                                                                                                                                                |
| `missing_glyphs`  | `"error"`           | `"error"` fails on uncovered codepoints; `"skip"` omits them and reports them in `layout().missing_codepoints`.                                                                                                                                                                                                           |
| `wrap`            | `"word"`            | `"clip"` (truncate at the edge), `"word"` (wrap at spaces; an overlong word falls back to character breaks), `"char"` (break anywhere).                                                                                                                                                                                   |
| `align`           | `"left"`            | `"left"`, `"center"` (odd remainders truncate), `"right"`.                                                                                                                                                                                                                                                                |
| `foreground`      | `[0,0,0,255]`       | Glyph ink color, RGBA bytes.                                                                                                                                                                                                                                                                                              |
| `background`      | `[255,255,255,255]` | Canvas clear color, RGBA bytes; transparency (`a < 255`) is supported.                                                                                                                                                                                                                                                    |
| `palette`         | none                | Optional explicit color per coverage level: entry `i` is used directly as the source color for level `i`, with exactly `1 << output_bits` entries and no extra coverage scaling. Without it, every nonzero level uses the foreground color with coverage-scaled alpha. These are coverage colors, not color-font support. |

Alpha: each nonzero coverage level `v` (of `levels = 1 << output_bits`) composites once with source alpha `sa`: by
default `sa = foreground.a * v / (levels - 1)` over the constant foreground RGB; with an explicit palette `sa` is the
entry's own alpha. Standard source-over blends it onto the canvas texel (`out_a = sa + da * (1 - sa)`, `out_rgb =
(src_rgb * sa + dst_rgb * da * (1 - sa)) / out_a`), starting from the background. Level 0 texels are skipped, so
untouched texels keep the background exactly, including its alpha. Overlapping glyphs blend in draw order (lines
top-to-bottom, glyphs left-to-right); rendering the same input twice yields identical bytes.

## Allocation limits

| Input                 | Limit                                    | On excess               |
| --------------------- | ---------------------------------------- | ----------------------- |
| Canvas width / height | 1..=4096 each, at most 16_777_216 texels | error before allocation |
| Text length           | 8192 characters                          | error                   |
| Distinct characters   | 1024                                     | error                   |
| `size_px`             | 1..=512                                  | error                   |
| Palette length        | exactly `1 << output_bits`               | error                   |

Empty (or newline-only) text returns a blank background canvas with zero lines, after validating the font bytes, config
settings, axes and palette exactly as a non-empty request would. Text whose glyphs are all skipped under
`missing_glyphs: "skip"` likewise yields a blank canvas, reporting every skipped codepoint in
`layout().missing_codepoints`.

## metadata() shape

A plain JS object (maps serialize as objects with string keys, never `Map`s) with the native `FontMetadata` fields:
`names`, `axes`, `kerning`, `style`, `classification`, `coverage`, `declared_unicode_ranges`. Descriptive source
information only; it carries no rendered pixels.
