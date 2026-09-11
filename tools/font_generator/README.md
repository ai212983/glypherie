# Font generator

Host-side glyph generation for supported outline fonts. The library produces
bitmaps and metrics independently of LVGL; the command-line adapter writes JSON.
The [plan](../../docs/plans/font-legibility-improvements.md) tracks calibration
and LVGL integration. Evaluation methods live in the
[font legibility reference](../../docs/reference/font-legibility.md).

## Run

From the repository root:

```bash
mkdir -p tools/font_generator/out
cargo +stable run --locked --manifest-path tools/font_generator/Cargo.toml -- \
  tools/font_generator/examples/roboto.json tools/font_generator/out/roboto-glyphs.json
cargo +stable test --locked --manifest-path tools/font_generator/Cargo.toml
```

The example uses the existing font in `tools/font_probe/fonts/`. Font paths resolve
relative to the job file. Supply another supported font by changing the job's
font path, checksum, and settings. The generator contains no font-family presets.
The output destination's parent directory must exist. Generation replaces the
output after input validation; the font and job file are protected from overwrite.

Each job records the font source description, license declaration, expected SHA-256,
and rendering settings. A checksum mismatch fails generation. Metadata declarations
are caller-provided; the generator verifies font bytes, not legal provenance.
Use `unknown` for unverified source or license information.

Output includes the font checksum, generation settings, package version, and SHA-256
of the dependency lockfile compiled into the tool. Keep the job, font, tool source,
lockfile, and `rustc +stable -vV` output with a result intended for reproduction.
Output excludes timestamps and local input paths.

## Supported input and output

Input is a single sfnt TTF/OTF with glyf, CFF, or CFF2 outlines, fixed or variable.
Collections, WOFF/WOFF2, bitmap-only and color fonts require a separate conversion
or adapter. Axis tags and values are checked against the actual font; omitted axes
use font defaults. Missing glyphs either fail the job or are listed as skipped.

The current repertoire supports Latin, Greek, Cyrillic, and common symbols.
Combining marks, control/format characters, and other scripts receive an explicit
unsupported-shaping error. Output represents nominal scalar glyphs and horizontal
pair kerning. Optional ligatures/contextual alternates are disabled; substitutions,
offsets, or pair changes to the right glyph's advance fail rather than being lost.
This API is for glyph tables; a complete text-run shaping adapter is separate work.

The library entry point is `generate(font_bytes, &Config)`. Its output contains
sorted glyphs, skipped codepoints, sorted nonzero kerning pairs, and line metrics.
Pixels are row-major **unpacked** levels from zero (no ink) through
`2^output_bits - 1` (full ink). The `left` and `top` coordinates position the bitmap
relative to a baseline in a y-down coordinate system. Empty glyphs such as spaces
retain their advances. Advances, pair adjustments, ascent, descent, and line gap
use signed 26.6 pixels (divide by 64). Ascent/descent retain the font metric
signs, conventionally positive/negative; line spacing is ascent minus descent plus
line gap. Add a pair adjustment to the left advance.

Glyph outlines are hinted when requested; advances come from variation-aware
linear metrics, with explicit output rounding. Consumers place glyph origins on
the pixel grid; fractional origin rasterization is outside this output contract.
LVGL packing and table generation belong to the later output adapter.

## Rendering settings

Settings are JSON fields within the job's `settings` object. Unknown fields fail.

| Field | Values / behavior |
| --- | --- |
| `size_px` | Finite pixels per em, 1–512; default 16 |
| `characters` | Required nonempty selection, 1–1024 distinct characters; deduplicated and sorted |
| `axes` | Map of four-byte tags to supported values, e.g. `{"wght":400,"opsz":16}`; default empty |
| `hinting` | `none`, `auto`, `interpreter`, or default `auto_fallback` |
| `output_bits` | 1, 2, 3, 4, or 8; default 1 |
| `mono_threshold` | 1–255, default 128; binary ink when coverage reaches the threshold |
| `gray_gamma` | Finite positive exponent, default 1; gray levels use nearest-level rounding of `(coverage/255)^gamma` |
| `missing_glyphs` | Default `error`, or `skip` with explicit missing-codepoint output |
| `kerning` | Default true; false disables pair adjustments while retaining representability checks |
| `metric_rounding` | Default `subpixel` rounds to 1/64px; `pixel` rounds advances and pair adjustments individually to whole pixels |

Mono threshold applies only to 1-bit output, and gamma only to gray output.
Each glyph allocation is bounded to 4 Mi pixels. The examples explicitly choose
threshold 96 at 16px as a calibration input; the general default stays 128.

## Calibration inputs

The example jobs use these existing files; fonts are not downloaded by the tool.
License/vendor/version information below was read from their embedded name tables.
Historical download URLs are unverified. Source declarations in the jobs describe
that limitation rather than asserting an upstream revision.

| Font | Embedded version | Embedded vendor | Embedded license |
| --- | --- | --- | --- |
| Roboto | 3.015;2026 | Google | SIL OFL 1.1 |
| Literata | 3.103;gftools[0.9.29] | TypeTogether | SIL OFL 1.1 |
| Source Sans 3 | 3.052;hotconv 1.1.0;makeotfexe 2.6.0 | Adobe | SIL OFL 1.1 |

The tests also use existing Ark Pixel static and IBM Plex Sans variable fonts to
exercise support beyond the calibration set. Small original CFF/CFF2 fixtures
exercise PostScript outlines and a variable blend; their builder is in
`tests/fixtures/build_fonts.py` (fontTools 4.64.0 was used). Font-specific choices
live in jobs and test inputs. Add a calibration case when a new font exposes a capability gap.

## Evidence and remaining evaluation

The existing [probe](../font_probe/README.md) contains Plex raster/kerning and join
experiments, per-face sizing calculations, and panel specimen generators. The join
experiment motivates a configurable coverage threshold; it does not establish one
threshold for every font. Existing panel viewers display pre-rendered images and
provide no evidence for LVGL table emission or product layouts.

Phase 1 checks input handling, reproducibility, metrics, quantization, spacing,
and focused stroke/counter behavior. Phase 2 owns broader font/size calibration
and physical reading evaluation. Phase 3 owns LVGL table generation and display
integration. Final product font assignments are independent choices.

## Phase 1 validation

The integration suite checks deterministic output at every supported bit depth,
axes and rendering controls, missing/unsupported inputs, linear advances and
pair rounding, and CLI checksum/path handling. The OTF fixtures check exact
rectangle bounds and advances; the font fixtures check connected joins and open
counters for `bhmnpo08` at 16px and 32px across the three calibration families.

The example jobs each produce 76 glyphs with no missing characters: Roboto has
354 nonzero pairs, Literata 1266, and Source Sans 3 782 at the recorded settings.
These are host generation checks, not a physical readability result. Run the
commands above against the pinned fonts and dependencies to refresh them.
