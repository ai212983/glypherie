# Generator API

<!-- cspell:words fpgm -->

This interface covers native generation, renderer selection and layout consumed by the WASM and specimen adapters.
[Setup, commands and settings defaults](README.md) are separate from the [published specimen contract](CONTRACT.md).
Renderer identities and model decisions belong to the [revision index](../../docs/revisions/001/README.md#iterations).

## Supported input and output

Input is one sfnt TTF/OTF with glyf, CFF or CFF2 outlines, fixed or variable. Collections, WOFF/WOFF2, bitmap-only and
color fonts require a separate adapter or conversion. Axis tags and values are checked against the font; omitted axes
use its defaults. Missing glyphs either fail or are listed as skipped, according to settings.

The repertoire supports Latin, Greek, Cyrillic and common symbols. Combining marks, control/format characters and other
scripts fail with unsupported-shaping errors. HarfRust resolves each isolated scalar at the requested axes. One-to-one
substitutions, including
[required variation alternates](https://learn.microsoft.com/en-us/typography/opentype/spec/features_pt#tag-rvrn), select
the glyph used for outlines, geometry, advances and kerning. `codepoint` retains Unicode identity; `glyph_id` records
the glyph drawn and can differ from the nominal character map.

Optional ligatures/contextual alternates are disabled. Each scalar must produce exactly one non-missing glyph without
positioning. Offsets, vertical advances and standalone horizontal advance adjustments fail; the latter are checked
against the shaper's own metric before positioning or pixel rounding, preserving fractional linear source metrics. Pairs
must preserve the isolated glyph IDs, order and count; only a left-advance adjustment is representable.
Context-dependent substitutions, offsets and right-advance changes fail. Complete text-run shaping requires a separate
adapter.

`generate(font_bytes, &Config)` returns sorted glyphs, skipped codepoints, sorted nonzero kerning pairs and line
metrics. Pixels are row-major **unpacked** levels from zero (no ink) to `2^output_bits - 1` (full ink). `left` and `top`
locate the bitmap relative to a baseline in y-down coordinates; empty glyphs retain advances. Advances, pair
adjustments, ascent, descent and line gap use signed 26.6 pixels (divide by 64). Ascent/descent retain font signs,
conventionally positive ascent and negative descent; line spacing is ascent minus descent plus line gap. Add pair
adjustments to the left advance.

Outlines are hinted as requested; `generate` uses variation-aware linear advances with explicit output rounding.
Consumers place origins on the pixel grid; fractional-origin rasterization and LVGL packing are outside this interface.

With the `candidate` feature, `candidate::generate_bitmap_font(font_bytes, &Config, strategy)` exports 1-bit or 3-bit
strikes with candidate bitmaps/offsets, whole-pixel advances and sparse whole-pixel pair adjustments. Other depths fail.
The `*_26_6` fields still encode pixels in multiples of 64. Consumers accumulate these metrics according to the
[spacing contract](#live-spacing-api); the optional strategy affects Mono and is ignored for Gray strikes.

## Renderer routing

`generate` uses the separate `vendor/skrifa-baseline` snapshot for automatic Mono fitting. Independent reference capture
uses registry Skrifa. The optional `candidate` feature exposes registry-backed fitting; disabling it leaves production
on the baseline. Versions are metadata, not per-iteration Cargo features. `iteration` remains a compatibility alias for
`candidate`, not a production renderer selector.

For production `auto_fallback`, embedded interpretation remains embedded and selected automatic Mono uses the legacy
custom policy. Explicit `interpreter` and `none` preserve those paths. Gray production uses symmetric Normal rendering
with linear metric preservation. The [baseline patch policy](vendor/skrifa-baseline/PATCH.md) owns its maintenance
rules.

### Working candidate fitting

Candidate Mono uses registry Skrifa 0.48.0 `Target::Mono` on runtime font bytes, including user-provided fonts:

| Strategy                     | Extension       | Engine                                                                                               |
| ---------------------------- | --------------- | ---------------------------------------------------------------------------------------------------- |
| `font_hints_first` (default) | `font-hints-01` | `Engine::AutoFallback`: interpreter when upstream `prefer_interpreter()` requests it, otherwise auto |
| `upstream_mono`              | `mono-width-01` | `Engine::Auto(None)`: automatic fitting, ignoring embedded instructions                              |

[Upstream engine selection](https://docs.rs/skrifa/0.48.0/skrifa/outline/enum.Engine.html) considers TrueType glyph
instructions and nonempty `fpgm`/`prep`; CFF/CFF2 uses its interpreter. This selects an engine without assessing hint
quality. No Mono strength or diagonal-balance controls are exposed. Both policies use whole upstream-fitted outlines
with the same candidate overlap-coverage, threshold and dropout raster; upstream outline identity does not promise
FreeType raster identity. `vertical_only` and `vertical-01` are rejected.

Native text clients call `surface::render_text_with_fitting_strategy` with role, tracking and an optional
`StemFittingStrategy`; omission selects `FontHintsFirst`. Selection normalizes effective hinting to `auto_fallback` for
font hints first or `auto` for forced auto. Candidate automatic inputs `auto`/`auto_fallback` are accepted; `none` and
`interpreter` fail. Explicit strategies require the candidate feature, candidate role and 1-bit output, even for blank
text. Incompatible requests fail. Capture `hinting_requested` records the effective policy; each record's
`selected_engine` reports `interpreter` or `auto`. Gray retains upstream Normal automatic fitting without a Mono
strategy selector. The independent reference requires an explicit engine.

## Reference and specimen capture

`reference::reference(font_bytes, &ReferenceRequest)` captures independently of production `generate` and job defaults.
The `font_reference JOB.json OUTPUT.json` adapter accepts `font`, `provenance`, `settings`, `profile` (`mono_1bit` or
`gray_3bit`) and optional `extensions` (default `none`). Select hinting explicitly as `auto`, `interpreter` or `none`,
with matching output bits 1 or 3. `auto_fallback`, unknown fields, mismatched targets and unsupported extensions fail.

Configured reference specimens use Skrifa 0.48.0 `Engine::Auto(None)`, extensions `none` and Zeno 0.3.3 Alpha coverage:
Mono uses `Target::Mono`, threshold 128; Gray uses `SmoothMode::Normal.into()` (symmetric rendering true, preserve
linear metrics false), gamma 1 and `round(7 * coverage / 255)`. Engine/target selection follows the pinned
[Fontations harness](https://github.com/googlefonts/fontations/blob/f886c9069b08eaddcb1caced3a44b0d8291a159a/fauntlet/src/font/mod.rs)
and
[Skrifa target settings](https://github.com/googlefonts/fontations/blob/f886c9069b08eaddcb1caced3a44b0d8291a159a/skrifa/src/outline/hint.rs).
[Nearest-level quantization](../../docs/references/papers/2006-gallager-quantization/) (§3.2.1, p. 65) converts
coverage; this adapted reference differs from default `AutoFallback` and
[TrueType monochrome scan conversion](https://learn.microsoft.com/en-us/typography/opentype/spec/ttch01#the-scan-converter).
Panel tone mapping is separate.

Reports retain controls, dependency identities, fitted-command f32 bits, raw coverage, quantized pixels and placement.
Reference, baseline, candidate and diagnostic capture resolve the same selected glyph IDs at the requested axes, with
renderer-specific fitting and advance policies. See the [diagnostics guide](../../docs/references/font-diagnostics.md).

Specimens use selected-renderer layout with HarfRust run adjustments, kerning enabled and optional ligature/contextual
features disabled. Candidate uses bitmap placement; reference/baseline use source-linear layout. Published images follow
the [specimen output contract](CONTRACT.md#specimen-images).

## Live spacing API

Layout follows renderer role; there is no selectable spacing model. Baseline `generate()` and independent reference use
fractional source advances and kerning, accumulated in 26.6 and rounded only when drawing. Their source-layout captures
are diagnostic controls.

Candidate Mono and Gray use the same bitmap policy in exported strikes, native specimens and preview:

- Each advance is finalized in whole pixels from the fitter's returned advance, or the rounded source advance when
  unavailable. Source-tabular digits (equal advances for all ten digits at the exact axes) retain the common quantized
  source advance. Fixed-pitch fonts and tabular digits carry no fitted bearing deltas.
- Source kerning and available fitted bearing corrections resolve once into sparse whole-pixel pair adjustments.
  Captures without bearing deltas contribute no correction. Disabling kerning removes the source contribution; fitting
  correction may still apply. `ascii_kerning_pairs` describes source data independently.
- Values round to nearest whole pixels, ties away from zero, preserving signed symmetry. Neutral tracking has no
  blank-column floor; intentional overhang remains. Integer pen accumulation gives each pair the same relative placement
  regardless of preceding text; line widths and wrapping use these metrics.

`layout_spacing::SpacingEngine::place` consumes finalized advances, pair kerning and bearing deltas, returning the glyph
origin and next pen. Native layout, interactive drawing, specimens and wrapping share that operation; exported candidate
metrics are exactly their inputs.

### Tracking policy

Offsets are finite, -16 to +16 px, with zero neutral. Mono and candidate Gray tracking round to whole pixels with half
ties away from zero; baseline/reference Gray retain fractional 26.6 offsets. Nonzero Mono tracking preserves at least
one delivered blank column for pairs with a positive rounded source gap. Source zero/negative gaps, declared fixed pitch
and tabular digit pairs bypass that floor.

Negative tracking preserves neutral ASCII word boundaries: spaces retain neutral advances and entry to the first space
cancels the preceding letter's negative trailing step once. Leading/repeated spaces need no extra cancellation. Positive
tracking widens letters and spaces. Spaces keep positive advances; the final glyph's trailing offset contributes to line
advance. Measurement, wrapping and rendering share constrained placement, so tightening can be less than requested.
Shapes remain unchanged; static publication uses neutral tracking. Rationale belongs to the
[tracking decision](../../docs/revisions/001/03-spacing-kerning.md#tracking-and-word-separation).
