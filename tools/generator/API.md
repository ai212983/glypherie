# Generator API

<!-- cspell:words fpgm SCANCTRL SCANTYPE Playdate interglyph pdfontconv unrepresentable -->

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
`candidate::generate_bitmap_font_with_tracking(font_bytes, &Config, strategy, letter_spacing_px)` bakes uniform tracking
into those advances; bitmaps, offsets and pair adjustments remain unchanged.

## Playdate font export

`playdate::export(font_bytes, &ExportRequest)` returns a standalone UTF-8 `.fnt` with an embedded PNG image table, glyph
widths and sparse signed pair adjustments, following the
[Playdate source-font format](https://sdk.play.date/Inside%20Playdate.html#_fonts). `ExportRequest` contains `config:
Config`, `pipeline: RenderPipeline` and `letter_spacing_px` (default zero). The candidate feature and 1-bit output are
required. The selected stages, axes, repertoire, scan settings, kerning and uniform tracking produce the same finalized
bitmap metrics as explicit-pipeline preview. Tracking is already included in advances; the consumer must not add it
again. `playdate::encode(&GeneratedFont)` serializes an existing finalized strike without refitting or rounding its
metrics.

The supported export subset has 1–1024 distinct characters within U+0020–U+3FFFF, excluding controls and unsupported
shaping. Missing glyphs fail even with `missing_glyphs: "skip"`. Dimensions and advances are limited to 255 pixels;
advances must be nonnegative integers and pair adjustments must be integers within -128–127 pixels. Cells share the
preview baseline and line height. Every cell shifts right by a common inset covering the leftmost actual ink across the
export, following [pdfontconv](https://github.com/ttencate/pdfontconv/blob/main/main.js); the inset folds into shared
tracking so each pen advance and interglyph step is unchanged. Playdate-reported text bounds include the terminal cell
padding after the final glyph, so measured widths exceed the source advance sums by that padding. Transparent scanner
padding imposes no ink bounds; only actual ink constrains the inset. Ink outside the line cell vertically fails with the
codepoint rather than being clipped or shifted. The image table is limited to 16,777,216 pixels.

Widths plus shared tracking reproduce finalized advances; shared tracking can be negative to retain the common left
inset and right overhangs. Pair adjustments are unchanged. An informational `--origin_x` header records the inset and is
ignored by Playdate; it is omitted when zero so those outputs stay byte-identical. Glyph entries precede pair entries
and use explicit Unicode names. Glyphs and pairs are ordered by codepoint. For equal inputs and implementation, native
and WASM exports are byte-identical. Invalid or unrepresentable data returns an error without a partial font.

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

`surface::PreparedFont::new(Vec<u8>)` owns immutable font bytes. Its `render_text_with_fitting_strategy` and
`render_text_with_pipeline_and_spacing` methods accept the same request, selection and tracking arguments as the
corresponding raw-byte functions, with identical validation and output. `as_bytes()` provides read-only access; there is
no byte-replacement operation. Reuse must preserve validation and output independently of preceding requests, eviction
and the lifetime of other prepared fonts. Raw-byte entry points retain identical output without shared cache state.

Current native preview clients use `surface::render_text_with_pipeline(font_bytes, &TextRenderRequest, RenderPipeline)`.
`RenderPipeline` separates `fitting` (`font_hints_auto`, `font_hints_first`, `source_relative` or `upstream_mono`) from
`rasterization` (`free_type_mono`, `free_type_mono_terminals` or `coverage`). It requires the `candidate` feature.
Optional `diagonal_fitting` defaults to `false`; `true` requires 1-bit FreeType scan conversion with `font_hints_auto`
or `upstream_mono`. Its fixed donor reference is independent of the requested text. Unsupported geometry retains the
preceding fitted outline. The [fitting design](../../docs/hobby-fitting.md#approved-fitting-sequence-adoption) owns the
model and gates. Modified captures identify `diagonal-shape-04` and retain the original upstream outline, donor
reference and unrounded feature source for independent replay; the preference does not change metrics or layout. Fitting
owns engine selection and returned advances; rasterization consumes the fitted outline without changing geometry or
metrics. Both scanners use the same bitmap layout below, with uniform extra tracking defaulting to zero. In 1-bit
output, coverage is Zeno Alpha quantized using `mono_threshold`; FreeType uses the scan controls below. Coverage rejects
non-default `mono_raster` settings. In 2-, 3- or 4-bit output, only automatic fitting (`upstream_mono`) with `coverage`
is valid; this uses Normal fitting. Invalid combinations fail even for blank text. Historical role APIs remain available
with their original fitting, rasterization and layout policies.

Candidate Mono uses Skrifa 0.48.0 `Target::Mono` on runtime font bytes, including user-provided fonts:

| Strategy                     | Extension            | Engine                                                                                                                                    |
| ---------------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `font_hints_first` (default) | `font-hints-01`      | Automatic Mono for verified program-free fonts, otherwise `Engine::AutoFallback`                                                          |
| `upstream_mono`              | `mono-width-01`      | `Engine::Auto(None)`: automatic fitting, ignoring embedded instructions                                                                   |
| `source_relative`            | `source-width-01`    | Font hints first, followed by conservative source-relative straight-stroke fitting on automatic outlines                                  |
| `font_hints_auto`            | `font-hints-auto-01` | Native fitting on controlled axes, automatic fitting on the remaining axes; retains source-relative correction on wholly automatic glyphs |

`font_hints_auto` requires 1-bit output and a FreeType scan stage. TrueType axis ownership records executed point
constraints and coordinate measurements, including zero-distance constraints and dependencies across axes. PostScript
ownership comes from evaluated stem hints and alignment zones. Uncertain execution, implicit native changes or
incompatible command streams retain the native fit. Horizontal metrics follow the X-axis fitting owner; executed font
scan controls remain authoritative when requested. Historical strategies keep their existing behavior. The
[iteration note](../../docs/revisions/001/03-spacing-kerning.md#selective-native-hints-and-automatic-fitting) owns the
model's assumptions and assessment limits.

[Upstream engine selection](https://docs.rs/skrifa/0.48.0/skrifa/outline/enum.Engine.html) considers TrueType glyph
instructions and nonempty `fpgm`/`prep`; CFF/CFF2 uses its interpreter. This selects an engine without assessing hint
quality. On TrueType fonts verified to carry no glyph instruction streams, no `fpgm`, and an absent or scan-control-only
`prep`, `font_hints_first` uses upstream automatic Mono fitting instead of upstream selection; every other font keeps
upstream selection. The request stays `auto_fallback` while each record's `selected_engine` reports the actual engine.
No Mono strength or diagonal-balance controls are exposed. The original two policies use whole upstream-fitted outlines.
The default rasterization is the pinned FreeType 2.15.0 monochrome scanner: nonzero-winding center fill with
two-direction sweeps and upstream overshoot handling. The scanner receives nearest-rounded 26.6 points (ties towards
positive infinity) at the existing integer origin. Candidate Mono ignores `mono_threshold`; raw Zeno Alpha coverage is
diagnostic and does not determine its delivered pixels on the FreeType path. FreeType captures declare `raster_policy:
"free_type_mono"`, `mono_rasterizer` with the scanner version and compiled vendored-source SHA-256, and per-record
effective `mono_raster` settings. FreeType does no font loading, hinting or layout here.

`free_type_mono_terminals` retains the same fitting and layout, then suppresses smart-dropout rescues only at straight
caps certified against both the source and fitted outlines. Ambiguous features keep the original scan; executed font
instructions remain authoritative. It requires 1-bit output. Captures use `raster_policy: "free_type_mono_terminals"`
and include `source_commands` for independent identity checks and raster reproduction. The
[iteration assessment](../../docs/revisions/001/03-spacing-kerning.md#terminal-tips-and-junction-continuity) owns the
model and assessment scope.

`source_relative` requires 1-bit FreeType scan conversion. It preserves returned advances and engine selection;
unsupported or uncertain features retain the upstream outline. Modified records include `source_commands` and
`width_fitting: { size_px, upstream_commands }` so evaluation can verify independent source/input identity and reproduce
the correction. Its policy identifier remains selected when no feature qualifies; `width_fitting` is absent on each
unchanged record. The [source-width model](../../docs/hobby-fitting.md#valid-straight-medial-intervals) owns geometric
eligibility and limits.

Records changed by `diagonal_fitting` additionally carry `diagonal_fitting: { model, size_px, upstream_commands,
native_axes, reference, reason, raw_source? }`. `reference` contains the captured upright anchors; `raw_source` retains
the unrounded feature input when available. Earlier width/selective captures describe `upstream_commands`; the record's
final commands and scan policy reproduce its bitmap.

### Monochrome scan-converter settings

`Config.mono_raster` defaults to `{"dropout":"smart","include_stubs":false,"font_instructions":false}`. `dropout`
accepts `smart`, `simple`, or `off`; `include_stubs` preserves short strokes and has no effect when dropout is `off`.
Absent fields default; unknown modes or fields fail. Non-default settings require candidate Mono, including for blank
requests; legacy generation, independent reference, probes and other output depths reject them.

Opt-in `font_instructions` follows executed TrueType `SCANCTRL` and `SCANTYPE`, including component contour markers,
when the selected engine is the embedded TrueType interpreter. Automatic fitting, CFF/CFF2, variable composite outlines
and disabled hinting retain the manual settings as fallback. Engine selection is unchanged. This path draws with a
pinned metadata-only Skrifa snapshot; fitting algorithms are unchanged, registry Skrifa remains independent for
manual/reference/Gray paths, and captures identify the patch in `implementation` with `fork: true` when it is used.
Per-record `font_scan` contains its source SHA-256, final `enabled` and full 16-bit `scan_type`, and contour-ordered
`contour_modes` (`null` inherits the preceding mode; integers 0–7 mark a new mode). Global invalid scan types disable
dropout; only contour markers truncate to three bits, matching FreeType. Evaluation reconstructs pixels from recorded
settings and scan state, rejecting incompatible state, invalid markers or mismatched source identity. This does not
assert full FreeType driver equivalence.

Candidate Mono accepts at most 65,535 scan-converter points per glyph; invalid geometry or allocation-limit violations
fail explicitly without a coverage fallback. `vertical_only` and `vertical-01` are rejected.

Historical native text clients call `surface::render_text_with_fitting_strategy` with role, tracking and an optional
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

Explicit pipelines share bitmap layout with optional uniform tracking; there is no selectable spacing model.
`surface::render_text_with_pipeline` defaults to zero; `surface::render_text_with_pipeline_and_spacing` accepts the
tracking offset. Historical role APIs retain their layout policies. Baseline `generate()` and independent reference use
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

Offsets are finite, -16 to +16 px, with zero neutral. Explicit-pipeline tracking rounds to whole pixels with half ties
away from zero, for both Mono and Gray. It adds the same signed offset to every finalized glyph advance, including
spaces and the final glyph advance. Zero and negative resulting advances remain signed; per-glyph clamping, minimum-gap
floors and word-gap refunds do not apply. Bitmaps, offsets and finalized pair adjustments remain unchanged. Rendering,
measurement, wrapping and tracked bitmap export use these same adjusted advances; consumers of a tracked strike must not
apply the tracking again. Additional pair corrections are unnecessary in this signed metric representation.

Historical role APIs retain protected tracking: Mono and candidate Gray use whole pixels, while baseline/reference Gray
retain fractional 26.6 offsets. Nonzero Mono tracking preserves a blank column for normally separated source pairs,
except fixed pitch and tabular digits. Negative tracking preserves neutral ASCII word gaps; positive tracking widens
letters and spaces. These historical constraints can limit tightening. Static publication uses zero tracking. Rationale
belongs to the [tracking decision](../../docs/revisions/001/03-spacing-kerning.md#tracking-and-word-separation).
