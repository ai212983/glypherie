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

## Iteration lifecycle

Each iteration addresses one specific problem identified by user feedback. Continue fixes, tweaks, experiments, and
validation under the same iteration identity. An iteration closes only when the user and agent agree there are no
further actions for that problem: it is resolved, cannot be fixed, or the remaining work belongs in an agreed follow-up.
Do not infer closure from passing tests, publishing specimens, or changing an implementation approach. The user must
explicitly agree to closure before advancing the iteration. Record the decision and any follow-up scope in the
[iteration record](../../docs/revisions/001/02-light-continuity.md).

## Specimen configuration

[specimens.json](specimens.json) defines the specimen matrix: upstream `reference` and the accepted `iteration-02`.
Roboto, Literata, and Source Sans 3 use ordinary 14/16/18/20 px slices. Both `mono_1bit` and `gray_3bit` profiles are
included. The preview selects 001.02, accepted on 2026-10-02, using the separate approved baseline snapshot.

- `variants` defines renderer iterations. The latest numeric revision and iteration is selected automatically. Each
  variant has an ID, kind, version, renderer role, hinting mode, and extension policy. Automatic fitting supports
  extensions `none` and the accepted `diagonal-01` model. Reference variants use `none`.
- `profiles` defines shared output settings. Profile IDs identify the 1-bit and 3-bit modes; their settings apply
  uniformly across selected families and sizes.
- `characters` defines the drawable repertoire. `cards` supplies IDs, titles, and content for the editable specimen
  cards; newline characters separate lines and spaces use source metrics.
- `defaults` supplies `sizes`, `variants`, and `profiles` to each family.
- `preview_policy` points to [preview-policy.json](preview-policy.json), independently fixing the normal preview's
  families and sizes. Validate effective sizes for every family/variant/profile, including overrides, before rendering
  or publication. Missing/invalid policy or matrix drift fails publication and preserves the existing output.
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

For an explicitly requested preview-matrix change, update the configuration, policy, and guard expectations together.
Font implementation and diagnostic work must preserve this agreed matrix. Broader sweeps use Rust requests/tests or
separate temporary configurations without a preview policy and with isolated output; do not publish them into the normal
`out/specimens/` or `out/web/`.

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

The default config produces 48 profile cases across two variants, with three samples per case. It writes immutable
packages and `active.json` under `out/specimens/`. Canonical render and composition artifacts live in
`out/specimens/canonical/<sha256>.json`.

Supply a configuration and optionally an output directory:

```sh
just specimens tools/generator/specimens.json out/specimens
```

The underlying CLI is independently usable:

```sh
cargo run --locked --manifest-path tools/generator/Cargo.toml --bin font_specimens -- \
  tools/generator/specimens.json out/specimens
```

The library entry point is `specimens::publish(config_path, output_directory)`. Each selected variant produces its own
package. The greatest numeric `revision.iteration` version selects the working package automatically; reference is
selected only when no iteration exists. Versions must be unique positive numeric pairs (for example `001.01`). The
latest configured variant must have render cases. Publication and production approval remain separate.

Samples use canonical linear advances with HarfRust run adjustments, with kerning enabled and optional
ligature/contextual features disabled. Cumulative origins round to native pixels. Composition preserves glyph pixels,
uses maximum ink for overlaps, and adds 8 px white padding. Grayscale previews map ink levels 0–7 to display values
255/219/182/146/109/73/36/0. Detailed layout records live in the composition artifact.

Repeating a generation reuses matching immutable packages and assets. A rendering or composition change creates a new
package. Source/configuration and package validation failures preserve the active pointer. Missing or unsupported render
cases remain explicit manifest items. Concurrent publication is guarded by `out/specimens/.publishing`; a leftover lock
after an interrupted publication requires checking that the publisher has stopped before removing that lock.

## Export glyph comparisons

After `just specimens`, run `just comparisons`. [comparisons.json](comparisons.json) sets the numeric symbol-route ID
and optional `attention` annotation path, using `comparison-config-v2`. Inputs and labels are derived from
`published.json` and explicit renderer roles: a working candidate versus the approved baseline, or baseline versus
reference when there is no newer candidate. Approved `001.02` currently compares with reference. A future working
version compares with approved `001.02` until the baseline is promoted. A reference-only publication has no comparison.
[attention.json](attention.json) marks cases for the web Attention card, with an internal status, required inspection
type and optional short hint; see the [guide](../../docs/evaluation.md#attention-card). Marks must match published
preview scope, including sizes and axes, and cannot add diagnostic renders. The exporter reuses canonical pixels and
writes aligned glyph/difference PNGs under `out/specimens/comparisons/`, leaving active selection unchanged.

`just preview-build` generates specimens, exports comparisons, and builds the site. `just preview` also serves it. The
[comparison contract](CONTRACT.md#glyph-comparison-export) defines exported content.

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

Mono uses Skrifa `Target::Mono`; grayscale uses the upstream `Smooth/Normal` target defaults described above. Reports
retain actual controls, pinned dependency identities, fitted command f32 bits, raw 8-bit coverage, quantized pixels and
placement. The `reference` API remains upstream-only. The workflow starts with one active upstream specimen variant and
develops optional changes for identified issues. Reference specimen export and the web index are available;
variant-bound issue reporting remains pending. [Font diagnostics](../../docs/references/font-diagnostics.md) describes
the capture and comparison tools provided by this generator.

### Accepted production fitting

The user accepted the current result and requested committing 001.02 on 2026-10-02. In the standard build, `generate`
uses the accepted patched fitter for automatic 1-bit output, with diagonal constraints, fractional shared-width fitting
and outline-driven monochrome dropout enabled. This includes straight, curved and mixed borders and coherent terminal
preparation. The
[acceptance record](../../docs/revisions/001/02-light-continuity.md#acceptance-and-promotion-2026-10-02) defines the
reviewed scope and retains broader diagnostic observations for future investigation.

Default jobs now select `hinting: "auto"`, 1-bit output and threshold 128. Example jobs use these accepted settings.
Explicit `auto_fallback` still honors upstream engine selection: embedded interpretation remains embedded
interpretation; when it selects automatic Mono fitting, the accepted diagonal model applies. Explicit `interpreter` and
`none` modes retain their existing behavior. Gray production targets retain symmetric Normal rendering with linear
metric preservation; they receive no diagonal extension. Advances, kerning, capability validation and output schemas
remain unchanged. Some full-repertoire pairs need unsupported text-run substitutions even with kerning disabled; the
generator continues to reject those requests rather than silently dropping positioning.

Renderer roles are stable across iterations:

- `reference`: independently pinned upstream Skrifa, used by the reference API and binary.
- `baseline`: the approved fitter snapshot in `vendor/skrifa-baseline`, always used by production `generate`.
- `candidate`: working fitter source in `vendor/skrifa-candidate`, available through the optional `candidate` feature.

`baseline::VERSION` records the approved revision and iteration (`001.02`); it selects no conditional compilation.
Specimen variants declare `renderer` separately from `version`. The current published 001.02 package uses `baseline`;
there is no active candidate after closure. A future working version uses `candidate` and compares with the approved
baseline, including work in the same revision. With no newer candidate, the preview shows baseline against reference.
Legacy packages without role metadata keep their historical previous-revision selection. Both Rust and web selection
apply the same rule, and baseline configuration must identify its approved version and fitting policy.

Baseline and candidate have separate source copies, with shared generator, fitting adapter, rasterizer and output code.
Candidate edits cannot change the approved fitting source. On an authorized promotion, replace the baseline's source
snapshot with the accepted candidate, retain its distinct package name, update the approved version metadata, record
acceptance and rerun parity and integration checks. Keep only one approved source snapshot and one working copy;
historical versions remain immutable generated packages and iteration notes. Never copy build outputs.

The index subtitle shows only the active iteration identity. Independent reference comparison remains available through
renderer controls and symbol routes. The remaining binary upright step near weight 465 is an accepted limitation of
001.02; gradual fitted widths do not imply continuous 1-bit optical weight.

The `candidate` feature enables research tooling only. Disabling it leaves production on the same approved baseline:

```sh
cargo build --locked --manifest-path tools/generator/Cargo.toml --no-default-features --bin font_generator
cargo build --locked --manifest-path tools/generator/Cargo.toml --no-default-features --bin font_reference \
  --target-dir out/upstream-reference
```

The reference binary always renders with the registry library, independently of both local fitters. The
[baseline patch policy](vendor/skrifa-baseline/PATCH.md) and [candidate policy](vendor/skrifa-candidate/PATCH.md) record
the pinned base, licenses, sourced model, project hypotheses, maintenance owner and parity checks. `iteration` remains
an API compatibility alias for `candidate`; its name does not choose production behavior.

`iteration::capture` with extensions `none` and `enabled=false` checks the patched library against the independently
renderable registry path. The full ordinary corpus parity test compares commands, metrics, coverage, placement, and
pixels.

Settings are JSON fields within the job's `settings` object. Unknown fields fail.

| Field             | Values / behavior                                                                                              |
| ----------------- | -------------------------------------------------------------------------------------------------------------- |
| `size_px`         | Finite pixels per em, 1–512; default 16                                                                        |
| `characters`      | Required nonempty selection, 1–1024 distinct characters; deduplicated and sorted                               |
| `axes`            | Map of four-byte tags to supported values, e.g. `{"wght":400,"opsz":16}`; default empty                        |
| `hinting`         | `none`, `auto`, `interpreter`, or default `auto_fallback`                                                      |
| `output_bits`     | 1, 2, 3, 4, or 8; default 1                                                                                    |
| `mono_threshold`  | 1–255, default 128; binary ink when coverage reaches the threshold                                             |
| `gray_gamma`      | Finite positive exponent, default 1; gray levels use nearest-level rounding of `(coverage/255)^gamma`          |
| `missing_glyphs`  | Default `error`, or `skip` with explicit missing-codepoint output                                              |
| `kerning`         | Default true; false disables pair adjustments while retaining representability checks                          |
| `metric_rounding` | Default `subpixel` rounds to 1/64px; `pixel` rounds advances and pair adjustments individually to whole pixels |

Mono threshold applies only to 1-bit output, and gamma only to gray output. Each glyph allocation is bounded to 4 Mi
pixels. The examples explicitly choose threshold 96 at 16px as a calibration input; the general default stays 128.

## Calibration inputs

The example jobs use these existing files; fonts are not downloaded by the tool. License/vendor/version information
below was read from their embedded name tables. Historical download URLs are unverified. Source declarations in the jobs
describe that limitation rather than asserting an upstream revision.

| Font          | Embedded version                     | Embedded vendor | Embedded license |
| ------------- | ------------------------------------ | --------------- | ---------------- |
| Roboto        | 3.015;2026                           | Google          | SIL OFL 1.1      |
| Literata      | 3.103;gftools[0.9.29]                | TypeTogether    | SIL OFL 1.1      |
| Source Sans 3 | 3.052;hotconv 1.1.0;makeotfexe 2.6.0 | Adobe           | SIL OFL 1.1      |

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

## Evidence and remaining evaluation

The [font evaluation guide](../../docs/references/font-evaluation.md) records sizing methods, measurement limits, and
physical evaluation. The [panel frame reference](../../docs/references/panel-frame-formats.md) preserves packing and
viewer conventions. Host-rendered specimens require separate evaluation on actual panels and in product layouts.

Phase 1 checks input handling, reproducibility, metrics, quantization, spacing, and focused stroke/counter behavior.
Phase 2 owns broader font/size calibration and physical reading evaluation. Phase 3 owns LVGL table generation and
display integration. Final product font assignments are independent choices.

## Phase 1 validation

The integration suite checks deterministic output at every supported bit depth, axes and rendering controls,
missing/unsupported inputs, linear advances and pair rounding, and CLI checksum/path handling. The OTF fixtures check
exact rectangle bounds and advances; the font fixtures check connected joins and open counters for `bhmnpo08` at 16px
and 32px across the three calibration families.

The example jobs each produce 76 glyphs with no missing characters: Roboto has 354 nonzero pairs, Literata 1266, and
Source Sans 3 782 at the recorded settings. These are host generation checks, not a physical readability result. Run the
commands above against the pinned fonts and dependencies to refresh them.
