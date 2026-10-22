# font_wasm

<!-- cspell:words rustup bindgen BINDGEN RUSTFLAGS rgba COLR CBDT sbix texel texels fpgm Playdate -->

Browser/Node port of the Rust font renderer. It reuses `generate()` through `font_generator::surface::render_text` with
the legacy skrifa-baseline snapshot: no fitting or model code lives here, so rendering parity with the native path is
the contract.

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

The browser app's `just wasm-build-preview` recipe builds standard WASM SIMD. Direct SIMD build commands:

```sh
WASM_SIMD128=1 tools/wasm/build.sh web preview    # tools/wasm/pkg-web-preview-simd128/
WASM_SIMD128=1 tools/wasm/build.sh nodejs preview # tools/wasm/pkg-nodejs-preview-simd128/
```

`WASM_SIMD128` accepts `0` (the direct script default) or `1`. SIMD packages require a runtime supporting WebAssembly
SIMD. Direct scalar builds keep their existing package names; the browser app defaults to `pkg-web-preview-simd128` (see
[web configuration](../web/README.md#configuration) for a scalar override). The option enables `simd128` across Rust
target dependencies without enabling relaxed SIMD or fast-math. Leave `RUSTFLAGS` and `CARGO_ENCODED_RUSTFLAGS` unset
when using it; additional target flags may use `CARGO_TARGET_WASM32_UNKNOWN_UNKNOWN_RUSTFLAGS`. Build commands never
select a renderer package for the app or publish it.

Verify the Node package:

```sh
node tools/wasm/smoke/render.mjs [font-path]   # needs the nodejs pkg
node tools/wasm/smoke/parity.mjs              # exact native/WASM comparison; needs Cargo
node --check tools/wasm/smoke/render.mjs tools/wasm/examples/hello.mjs
```

The parity harness recomputes native results for 67 cases spanning the shipped fonts, axes, fractional sizes, hinting,
coverage depths, wrapping, clipping, alignment, transparency, palettes, blank text and CFF/CFF2 outlines. It compares
RGBA bytes, layout and metadata with the actual WASM module, without historical pixel snapshots. Roboto Flex cases cover
dollar variation substitutions at weights 400/700, slants 0/-10, mono/gray output and kerning on/off.

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

## Stem-fitting strategies

Candidate 1-bit rendering defaults to **Font hints first**: upstream `Target::Mono` with the shared engine selection
rules, using embedded instructions when selected and otherwise automatic fitting. Optional `stem_fitting:
"font_hints_first" | "upstream_mono"` selects that default explicitly or forces automatic Mono fitting. Both consume the
supplied font bytes directly; no font-specific preparation, names or glyph rules are required. `vertical_only` is
removed and rejected. See the [generator API](../generator/API.md#working-candidate-fitting) for the selection rules.

```js
const result = font.render({
  text: "minimum mut Avo", width: 300, height: 80, size_px: 14,
  renderer: "candidate", output_bits: 1, hinting: "auto_fallback",
  // stem_fitting: "upstream_mono", // optional forced automatic comparison
});
```

Strategy selection controls the effective automatic engine policy; the shared generator records the normalized policy
and actual selected engine. The WASM layer forwards the shared enum and adds no fitting logic. Explicit selection
requires a preview build, candidate role and 1-bit output, including for blank text. Automatic policy inputs `auto` and
`auto_fallback` are accepted; `none`, `interpreter`, unknown names and incompatible role/profile combinations fail. Gray
keeps upstream Normal automatic fitting. Both Mono choices share the pinned FreeType monochrome scanner and candidate
bitmap layout. The shared generator owns scan-converter settings; candidate Mono ignores `mono_threshold`. Scanner
parity does not establish optical acceptance. See the [generator API](../generator/API.md#working-candidate-fitting).

## Monochrome scan controls

Candidate 1-bit rendering accepts optional `mono_raster: { dropout, include_stubs, font_instructions }`. Defaults are
`"smart"`, `false`, and `false`. `dropout` also accepts `"simple"` or `"off"`; `include_stubs` preserves short strokes
and has no effect with dropout off. Opt-in `font_instructions` uses executed TrueType scan settings with embedded
fitting, falling back to the manual settings when unavailable. The
[generator API](../generator/API.md#monochrome-scan-converter-settings) owns scan semantics. Absent fields default;
unknown fields, invalid types or modes fail. Non-default settings require a preview build, candidate role and 1-bit
output, including blank text.

## Kerning pairs

`font.kerning_pairs(size_px, axes)` returns a plain object `{ pairs, skipped_pairs }`. Each pair has Unicode codepoints
`left`, `right` and a signed `adjustment_26_6` in 1/64 pixels. It reads nonzero horizontal source adjustments for
printable ASCII (U+0020 through U+007E), using the same shaper as native generation with kerning enabled and ligatures
disabled. Isolated scalars resolve to their selected glyphs at those axes, including one-to-one variation substitutions.
Missing characters are skipped; `skipped_pairs` counts pairs changing those glyph identities, order or count, or needing
positioning beyond a single left-advance change. Invalid settings and single-character shaping failures throw an error.
This descriptive API draws no outlines and changes no rendering or layout policy; native generation retains its strict
shaping errors. Size and axes use the same validation as rendering, with omitted axes at their font defaults.

## Playdate export

Preview builds expose `font.export_playdate({ config, pipeline, letter_spacing_px })`, returning a JS-owned `Uint8Array`
containing a standalone `.fnt`. `config.characters` explicitly selects the repertoire. The
[generator API](../generator/API.md#playdate-font-export) owns settings, format guarantees and representability limits.
Unknown request, config, pipeline and scan-setting fields fail. Default production builds reject this export.

Verify native/WASM export parity with the Node preview package; optionally set `PLAYDATE_SDK_PATH` to validate every
export with the official compiler:

```sh
tools/wasm/build.sh nodejs preview
node tools/wasm/smoke/playdate.mjs
PLAYDATE_SDK_PATH=/path/to/PlaydateSDK node tools/wasm/smoke/playdate.mjs
```

## Ownership

`Font` and `RenderResult` hold Rust-side memory and must be freed with `.free()` (use `try/finally`). `pixels()` returns
a new JS-owned copy on every call, so freeing the result never invalidates an already returned array. Errors surface as
thrown JS strings carrying the generator message only.

## Input restrictions

Font formats and supported shaping follow the [generator capabilities](../generator/API.md#supported-input-and-output).
Color-font tables (`COLR`, `SVG`, `CBDT`, `sbix`) are rejected by this surface; there is no color-font adapter. Tabs,
combining marks and unsupported shaping remain errors.

- The render spec has no `characters` field: the repertoire always comes from `text`, and unknown spec fields (including
  `characters`) are rejected.

## Render-spec controls

Current preview requests select stages with `pipeline: { fitting: "font_hints_auto", rasterization:
"free_type_mono_terminals" }`. The [generator API](../generator/API.md#working-candidate-fitting) owns stage
combinations and the shared bitmap layout. Explicit pipelines require a preview build; `letter_spacing_px` supplies
uniform whole-pixel tracking to the shared layout. They cannot be combined with `renderer` or `stem_fitting`. Fitting
owns engine selection, including the effective `hinting`. `mono_raster` overrides apply only to the FreeType stages.
Omitting `pipeline` retains the historical role API and its defaults, including the production baseline when `renderer`
is absent. Unknown stages or fields fail deserialization.

Only `text`, `width` and `height` are required. Top-level glyph controls `size_px`, `axes`, `hinting`, `output_bits`,
`mono_threshold`, `gray_gamma`, `kerning`, `metric_rounding` and `missing_glyphs` inherit the
[generator settings and defaults](../generator/README.md#builds-and-settings). The table below covers surface-specific
controls.

| Field               | Default             | Meaning                                                                                                                                                                                                                                                                                                                   |
| ------------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `text`              | (required)          | Source text; lines split on `\n`, `\r\n`, `\r`. Max 8192 characters.                                                                                                                                                                                                                                                      |
| `width`, `height`   | (required)          | Exact canvas size, each 1..=4096.                                                                                                                                                                                                                                                                                         |
| `letter_spacing_px` | 0                   | Signed finite offset, -16..=16; follows the [shared tracking policy](../generator/API.md#tracking-policy).                                                                                                                                                                                                                |
| `spacing_model`     | (retired)           | Removed with the single bitmap policy; passing it is rejected like any other unknown field. Layout follows `renderer`: candidate bitmap placement, baseline/reference source layout.                                                                                                                                      |
| `wrap`              | `"word"`            | `"clip"` (truncate at the edge), `"word"` (wrap at spaces; an overlong word falls back to character breaks), `"char"` (break anywhere).                                                                                                                                                                                   |
| `align`             | `"left"`            | `"left"`, `"center"` (odd remainders truncate), `"right"`.                                                                                                                                                                                                                                                                |
| `foreground`        | `[0,0,0,255]`       | Glyph ink color, RGBA bytes.                                                                                                                                                                                                                                                                                              |
| `background`        | `[255,255,255,255]` | Canvas clear color, RGBA bytes; transparency (`a < 255`) is supported.                                                                                                                                                                                                                                                    |
| `palette`           | none                | Optional explicit color per coverage level: entry `i` is used directly as the source color for level `i`, with exactly `1 << output_bits` entries and no extra coverage scaling. Without it, every nonzero level uses the foreground color with coverage-scaled alpha. These are coverage colors, not color-font support. |

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
| Palette length        | exactly `1 << output_bits`               | error                   |

Empty (or newline-only) text returns a blank background canvas with zero lines, after validating the font bytes, config
settings, axes and palette exactly as a non-empty request would. Text whose glyphs are all skipped under
`missing_glyphs: "skip"` likewise yields a blank canvas, reporting every skipped codepoint in
`layout().missing_codepoints`.

## metadata() shape

A plain JS object (maps serialize as objects with string keys, never `Map`s) containing native `FontMetadata`. Fields
and source-extraction semantics are defined by the [font metadata contract](../generator/CONTRACT.md#package-manifest).

Preview builds require a C compiler; for `wasm32-unknown-unknown`, put Clang with WebAssembly support and `llvm-ar` on
PATH (for Homebrew LLVM on macOS, `PATH="$(brew --prefix llvm)/bin:$PATH" tools/wasm/build.sh web preview`), or set
Cargo's `CC_wasm32_unknown_unknown` and `AR_wasm32_unknown_unknown` overrides. Production builds without `preview` do
not compile the C scanner. Preview packages also contain `LICENSE-FreeType.txt`, which must accompany redistribution of
the renderer.
