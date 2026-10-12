# Font generator

Host-side glyph generation for supported outline fonts. The library produces bitmaps and metrics independently of LVGL;
the command-line adapter writes JSON. Recommended sizes and evaluation methods live in the
[font evaluation guide](../../docs/references/font-evaluation.md); research sources are listed in the
[research corpus](../../docs/references/papers/CORPUS.md).

Skrifa fits glyph outlines; HarfRust supplies shaping and positioning within the supported repertoire. Zeno rasterizes
the fitted outlines. The Rust generator owns metric and layout policy, coverage quantization, and bitmap composition as
separate stages.

The [specimen output contract](CONTRACT.md) defines the active pointer, manifest, native PNG assets, and publication
checks for the web workflow.

Workflow and iteration writing follow the [revision guide](../../docs/revisions/README.md); assessment follows the
[evaluation guide](../../docs/evaluation.md).

## Specimen configuration

[specimens.json](specimens.json) selects source fonts, sizes, axes, profiles, renderer variants and cards.
[preview-policy.json](preview-policy.json) records the agreed publication scope. The
[revision index](../../docs/revisions/001/README.md#iterations) records approved/candidate identities.

- `variants` gives each renderer an ID, kind, version, renderer role, hinting mode and extension policy. Automatic
  fitting supports extensions `none` and the accepted `diagonal-01` model. Reference variants use `none`.
- `profiles` defines shared output settings. Profile IDs identify the 1-bit and 3-bit modes; their settings apply
  uniformly across selected families and sizes.
- `characters` defines the drawable repertoire. `cards` supplies IDs, titles, and content for the editable specimen
  cards; newline characters separate lines and spaces use source metrics.
- `defaults` supplies `sizes`, `variants`, and `profiles` to each family.
- `preview_policy` points to the publication-scope policy; validation is defined by the
  [output contract](CONTRACT.md#generation-selection).
- `families` supplies identity, display name, font path, provenance/checksum, and variation axes. Font paths resolve
  relative to the configuration file. An axis value is a number or `"size_px"`, which binds it to the selected rendering
  size.
- A family can supply its own `sizes`, `variants`, or `profiles` arrays. A supplied array replaces the inherited
  selection. Within `sizes`, an object can override variants or profiles for that size alone.

For example, these fields on a family select two sizes, grayscale at 14 px, and both output modes at 20 px:

```json
{
  "variants": ["reference"],
  "profiles": ["gray_3bit"],
  "sizes": [
    14,
    {"size_px": 20, "profiles": ["mono_1bit", "gray_3bit"]}
  ]
}
```

The [output contract](CONTRACT.md#generation-selection) defines scope changes and isolated diagnostic configurations.

For configurations without a preview policy, add or remove family records and edit their selections to change the
matrix. Selections are nonempty and reference defined IDs; sizes are unique within a family and fall within 1–512 px.
Each active variant selects at least one case. Reserved evaluation slices remain excluded from ordinary specimen
selection.

`specimen_config::load(path)` parses, validates, and resolves the configuration into explicit
family/size/variant/profile cases. The exporter verifies font bytes and font-specific axis bounds and records complete
effective coordinates.

### Configure preview cards

Edit the `cards` array in [specimens.json](specimens.json) to add, remove, reorder, or change the main-page sample
cards:

```json
{
  "cards": [
    {
      "id": "reading",
      "title": "Reading sample",
      "content": "Pack my box with five dozen liquor jugs.\nminimum AVATAR To Wa"
    },
    {
      "id": "numbers",
      "title": "Numbers and symbols",
      "content": "08:38 21.5°C 48%\n0123456789 .,;:!?+-/()"
    }
  ]
}
```

Array order controls the card order in every family, size, and output mode. IDs must be unique. Titles and content must
be nonempty, and content must use the configured `characters` plus spaces and newlines. Add any new drawable characters
to `characters` as well.

`Character coverage` is appended automatically from the drawable repertoire, with uppercase, lowercase, and
digits/symbols on separate lines. `Changed symbols` comes from the glyph comparison export. Their IDs (`coverage` and
`changed-symbols`) and titles are reserved; neither belongs in `cards`. An empty `cards` array keeps coverage and any
available changed symbols.

Run `just preview-build` after editing to regenerate the specimen images, comparisons, and website. The legacy inline
`samples` format (`id`, `label`, `text`) remains supported for existing configurations; use either `cards` or `samples`.

## Generate reference specimens

The reference is **upstream autohint + nearest coverage conversion**: pinned Skrifa 0.46.2, `Engine::Auto(None)`,
extensions `none`, and Zeno 0.3.3 Alpha rasterization. Mono uses `Target::Mono` and threshold 128. Grayscale uses
`SmoothMode::Normal.into()` (symmetric rendering true, preserve linear metrics false), gamma 1, and `round(7 * coverage
/ 255)` for eight uniform coverage levels.

Automatic hinting and target selection follow the pinned [Fontations harness][reference-harness]; normal-target fields
follow [Skrifa's implementation][reference-settings]. Output conversion follows
[nearest-level quantization][reference-quantization] (§3.2.1, p. 65), minimizing squared coverage error for the declared
levels. This is an adapted upstream reference, distinct from Skrifa's default engine (`AutoFallback`) and
[TrueType monochrome scan conversion][reference-scan]. Display/panel tone mapping is separate from coverage
quantization; the preview palette below represents stored levels.

[reference-harness]: https://github.com/googlefonts/fontations/blob/f886c9069b08eaddcb1caced3a44b0d8291a159a/fauntlet/src/font/mod.rs
[reference-settings]: https://github.com/googlefonts/fontations/blob/f886c9069b08eaddcb1caced3a44b0d8291a159a/skrifa/src/outline/hint.rs
[reference-quantization]: ../../docs/references/papers/2006-gallager-quantization/
[reference-scan]: https://learn.microsoft.com/en-us/typography/opentype/spec/ttch01#the-scan-converter

From the repository root, with Cargo and just installed:

```sh
just specimens
```

Packages and canonical artifacts use the [output layout](CONTRACT.md#output-location-and-selection).

Supply a configuration and optionally an output directory:

```sh
just specimens tools/generator/specimens.json out/specimens
```

The underlying CLI is independently usable:

```sh
cargo run --locked --manifest-path tools/generator/Cargo.toml --bin font_specimens -- \
  tools/generator/specimens.json out/specimens
```

The library entry point is `specimens::publish(config_path, output_directory)`. Package selection, validation and
publication guarantees are defined by the [output contract](CONTRACT.md).

Samples use the selected renderer's spacing policy with HarfRust run adjustments, kerning enabled and optional
ligature/contextual features disabled. Cumulative origins round to native pixels. Composition preserves glyph pixels,
uses maximum ink for overlaps, and adds 8 px white padding. Grayscale previews map ink levels 0–7 to display values
255/219/182/146/109/73/36/0. Detailed layout records live in the composition artifact.

## Export glyph comparisons

After `just specimens`, run `just comparisons`. [comparisons.json](comparisons.json) supplies the symbol-route ID.
Inputs, exported images and statistics follow the [comparison contract](CONTRACT.md#glyph-comparison-export).

`just preview-build` runs specimen generation, comparison export, WASM staging and the site build; `just preview` also
serves the result.

## Run

From the repository root:

```bash
mkdir -p tools/generator/out
cargo +stable run --locked --manifest-path tools/generator/Cargo.toml -- \
  tools/generator/examples/roboto.json tools/generator/out/roboto-glyphs.json
cargo +stable test --locked --manifest-path tools/generator/Cargo.toml
```

The example uses the existing font in [fonts](../../fonts/README.md). Font paths resolve relative to the job file.
Supply another supported font by changing the job's font path, checksum, and settings. The generator contains no
font-family presets. The output destination's parent directory must exist. Generation replaces the output after input
validation; the font and job file are protected from overwrite.

Each job records the font source description, license declaration, expected SHA-256, and rendering settings. A checksum
mismatch fails generation. Metadata declarations are caller-provided; the generator verifies font bytes, not legal
provenance. Use `unknown` for unverified source or license information.

Output includes the font checksum, generation settings, package version, and SHA-256 of the dependency lockfile compiled
into the tool. Keep the job, font, tool source, lockfile, and `rustc +stable -vV` output with a result intended for
reproduction. Output excludes timestamps and local input paths.

## Supported input and output

Input is a single sfnt TTF/OTF with glyf, CFF, or CFF2 outlines, fixed or variable. Collections, WOFF/WOFF2, bitmap-only
and color fonts require a separate conversion or adapter. Axis tags and values are checked against the actual font;
omitted axes use font defaults. Missing glyphs either fail the job or are listed as skipped.

The current repertoire supports Latin, Greek, Cyrillic, and common symbols. Combining marks, control/format characters,
and other scripts receive an explicit unsupported-shaping error. Output represents nominal scalar glyphs and horizontal
pair kerning. Optional ligatures/contextual alternates are disabled; substitutions, offsets, or pair changes to the
right glyph's advance fail rather than being lost. This API is for glyph tables; a complete text-run shaping adapter is
separate work.

The library entry point is `generate(font_bytes, &Config)`. Its output contains sorted glyphs, skipped codepoints,
sorted nonzero kerning pairs, and line metrics. Pixels are row-major **unpacked** levels from zero (no ink) through
`2^output_bits - 1` (full ink). The `left` and `top` coordinates position the bitmap relative to a baseline in a y-down
coordinate system. Empty glyphs such as spaces retain their advances. Advances, pair adjustments, ascent, descent, and
line gap use signed 26.6 pixels (divide by 64). Ascent/descent retain the font metric signs, conventionally
positive/negative; line spacing is ascent minus descent plus line gap. Add a pair adjustment to the left advance.

Glyph outlines are hinted when requested; advances come from variation-aware linear metrics, with explicit output
rounding. Consumers place glyph origins on the pixel grid; fractional origin rasterization is outside this output
contract. LVGL packing and table generation belong to the later output adapter.

## Rendering settings

The separate `reference::reference(font_bytes, &ReferenceRequest)` API and `font_reference JOB.json OUTPUT.json` binary
provide upstream-only reference capture independently of the production `generate` API and job defaults. A reference job
uses the usual `font`, `provenance`, and `settings` fields plus `profile` (`mono_1bit` or `gray_3bit`) and optional
`extensions` (default `none`). Set `settings.hinting` explicitly to `auto`, `interpreter`, or `none`, with matching
`settings.output_bits` 1 or 3. `auto_fallback`, unknown fields, mismatched targets, and unsupported extensions are
rejected.

Reference profiles use the targets described in [Generate reference specimens](#generate-reference-specimens). Reports
retain controls, dependency identities, fitted command f32 bits, raw coverage, quantized pixels and placement. The
[diagnostics guide](../../docs/references/font-diagnostics.md) describes capture and comparison tools.

### Accepted production fitting

Production `generate` uses the separate approved `vendor/skrifa-baseline` snapshot for automatic 1-bit fitting. The
independent `reference` API/binary uses registry Skrifa. The optional `candidate` feature exposes working
`vendor/skrifa-candidate` tooling; disabling it leaves production on the same baseline. Versions are metadata, not
per-iteration Cargo features. The [revision index](../../docs/revisions/001/README.md#iterations) owns current
approved/candidate identities.

Keep one approved baseline snapshot and one working candidate copy, sharing generator, raster and output code. Promotion
requires explicit user acceptance and authorization: replace the baseline snapshot and update its version metadata. Keep
baseline and candidate source hashes separate. Review and closure follow the
[iteration lifecycle](../../docs/revisions/README.md#iteration-lifecycle).

Explicit `auto_fallback` honors engine selection: embedded interpretation remains embedded; selected automatic Mono
fitting uses the approved policy. Explicit `interpreter` and `none` preserve their paths. Gray production uses symmetric
Normal rendering with linear metric preservation. Accepted model changes and limitations are recorded in
[diagonal fitting](../../docs/revisions/001/01-diagonal-weight.md) and
[light continuity](../../docs/revisions/001/02-light-continuity.md). Working model decisions belong in the
[iteration index](../../docs/revisions/001/README.md#iterations).

Candidate capture declares `advance_policy: "hinted"` and may supply `side_bearing_deltas_26_6`; linear reports omit
these additions. Native/interactive placement uses the [shared spacing API](#live-spacing-api). `iteration` remains a
compatibility alias for `candidate`; its name does not select production behavior.

Build production and independent reference without candidate tooling:

```sh
cargo build --locked --manifest-path tools/generator/Cargo.toml --no-default-features --bin font_generator
cargo build --locked --manifest-path tools/generator/Cargo.toml --no-default-features --bin font_reference \
  --target-dir out/upstream-reference
```

Vendored base, licenses and maintenance details belong to the [baseline patch policy](vendor/skrifa-baseline/PATCH.md)
and [candidate policy](vendor/skrifa-candidate/PATCH.md).

Settings are JSON fields within the job's `settings` object. Unknown fields fail.

| Field             | Values / behavior                                                                                              |
| ----------------- | -------------------------------------------------------------------------------------------------------------- |
| `size_px`         | Finite pixels per em, 1–512; default 16                                                                        |
| `characters`      | Required nonempty selection, 1–1024 distinct characters; deduplicated and sorted                               |
| `axes`            | Map of four-byte tags to supported values, e.g. `{"wght":400,"opsz":16}`; default empty                        |
| `hinting`         | `none`, default `auto`, `interpreter`, or `auto_fallback`                                                      |
| `output_bits`     | 1, 2, 3, 4, or 8; default 1                                                                                    |
| `mono_threshold`  | 1–255, default 128; binary ink when coverage reaches the threshold                                             |
| `gray_gamma`      | Finite positive exponent, default 1; gray levels use nearest-level rounding of `(coverage/255)^gamma`          |
| `missing_glyphs`  | Default `error`, or `skip` with explicit missing-codepoint output                                              |
| `kerning`         | Default true; false disables pair adjustments while retaining representability checks                          |
| `metric_rounding` | Default `subpixel` rounds to 1/64px; `pixel` rounds advances and pair adjustments individually to whole pixels |

Mono threshold applies only to 1-bit output, and gamma only to gray output. Each glyph allocation is bounded to 4 Mi
pixels.

## Calibration inputs

Calibration fonts and their identities, axes, embedded license declarations and provenance limits are documented in
[fonts/README.md](../../fonts/README.md). The generator does not download fonts.

The calibration fonts also exercise variable-font generation in tests. Small original CFF/CFF2 fixtures exercise
PostScript outlines, a variable blend, and rejection of variation axes on static fonts. Their Rust builder is in
`examples/build_fixtures.rs`, using the pinned `write-fonts` dev dependency. Regenerate the checked-in fixtures from the
repository root with:

```sh
cargo run --locked --manifest-path tools/generator/Cargo.toml --example build_fixtures
```

The builder uses original rectangle outlines and fixed timestamps for deterministic output. Normal tests read the
checked-in fonts directly. Font-specific choices live in jobs and test inputs. Add a calibration case when a new font
exposes a capability gap.

## Live spacing API

`surface::render_text_with_spacing_model` accepts `layout_spacing::SpacingModel::{Auto, Source, Fitted, Projected}` and
a signed pixel offset. Explicit models require 1-bit output and use the selected renderer's own glyphs/metrics. `Auto`
selects that role's default policy. The placement algorithms, source foundations and unresolved optical questions are
recorded in [pair spacing](../../docs/revisions/001/03-spacing-kerning.md#pair-spacing-and-kerning).

The [spacing models guide](../../docs/spacing-models.md) explains the choices and their interaction with kerning and
tracking in the preview.

`layout_spacing::SpacingEngine` accepts immutable source/fitted metrics, source kerning, available bearing deltas,
optional source/ink geometry and tracking. Its `place` operation returns a glyph origin and next pen. Native layout,
interactive drawing and wrapping share that operation. Disabling kerning removes source pair adjustment; model-specific
bearing or gap correction may still apply.

### Tracking policy

Offsets are finite, from -16 to +16 px, with zero neutral. Mono rounds to whole pixels with half ties away from zero;
gray retains fractional 26.6 offsets. For nonzero Mono tracking, pairs with a positive rounded source gap retain at
least one delivered blank column. Source zero/negative gaps, declared fixed pitch and tabular digit pairs bypass the
floor.

Negative tracking preserves the selected model's neutral ASCII word boundary: spaces keep their neutral advance and
entry to the first space cancels the preceding letter's negative trailing step once. Leading/repeated spaces need no
extra cancellation. Positive tracking widens letters and spaces. Spaces retain a positive advance. The final glyph's
trailing offset still contributes to line advance.

Measurement, wrapping and rendering use the same constrained placement. Line-width changes can be smaller than the
requested tightening; glyph shapes stay unchanged. The policy's problem and rationale belong in the
[tracking decision](../../docs/revisions/001/03-spacing-kerning.md#tracking-and-word-separation). Static publication
uses neutral tracking and renderer-default spacing.

## Evaluation

Use the [evaluation guide](../../docs/evaluation.md) for geometric/optical assessment and the Rust evaluator command.
Host specimens also require reading assessment on the intended panels and in product layouts; sizing and physical
evaluation are covered by the [font evaluation guide](../../docs/references/font-evaluation.md).
