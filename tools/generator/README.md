# Font generator

Host-side glyph generation for supported outline fonts. Run commands below from the repository root with Rust/Cargo and
[just](../../justfile) installed. The [generator API](API.md) defines font capabilities, renderer routing and native
layout; the [specimen contract](CONTRACT.md) defines published packages. Use the
[evaluation guide](../../docs/evaluation.md) for assessment and the [revision guide](../../docs/revisions/README.md) for
iteration work.

The default candidate build also requires a C compiler. It builds the vendored FreeType monochrome scanner; no system
FreeType library is needed. Source, license and update requirements are in
[the scanner policy](vendor/freetype-mono/PATCH.md).

## Run

```sh
mkdir -p tools/generator/out
cargo run --locked --manifest-path tools/generator/Cargo.toml -- \
  tools/generator/examples/roboto.json tools/generator/out/roboto-glyphs.json
cargo test --locked --manifest-path tools/generator/Cargo.toml
```

The example uses the existing font in [fonts](../../fonts/README.md). Font paths resolve relative to the job file.
Change its font path, checksum and settings to use another supported font; there are no font-family presets. Create the
output parent directory first. Generation validates inputs before replacing output and protects the font and job file
from overwrite.

Export a Playdate source font with the maintained `font_playdate` adapter (default build; requires the `candidate` and
`native-io` features):

```sh
cargo run --locked --manifest-path tools/generator/Cargo.toml --bin font_playdate -- \
  FONT REQUEST.json OUTPUT.fnt
```

`REQUEST.json` supplies an `ExportRequest`: `config`, `pipeline` and `letter_spacing_px` as defined in the
[API](API.md#playdate-font-export). The Playdate Font Lab staging script documents its request defaults in
[tools/playdate/README.md](../playdate/README.md).

Each job supplies `font`, `provenance` (source description, license declaration and expected SHA-256), and `settings`. A
checksum mismatch fails generation. Source and license declarations are caller-provided; use `unknown` when unverified.
The generator verifies font bytes, not legal provenance.

For reproduction, retain the job, font, tool source, lockfile and `rustc -vV` output. JSON results record the font
checksum, settings, package version and compiled dependency-lock SHA-256; they omit timestamps and local paths.

### Builds and settings

The default build enables `candidate` and `native-io`. Build production and independent reference without candidate
tooling:

```sh
cargo build --locked --manifest-path tools/generator/Cargo.toml --no-default-features --bin font_generator
cargo build --locked --manifest-path tools/generator/Cargo.toml --no-default-features --bin font_reference \
  --target-dir out/upstream-reference
```

Vendored source, licenses and maintenance requirements belong to the
[baseline patch policy](vendor/skrifa-baseline/PATCH.md).

Settings are JSON fields within the job's `settings` object. Unknown fields fail.

| Field             | Values / behavior                                                                                        |
| ----------------- | -------------------------------------------------------------------------------------------------------- |
| `size_px`         | Finite pixels per em, 1–512; default 16                                                                  |
| `characters`      | Required nonempty selection, 1–1024 distinct characters; deduplicated and sorted                         |
| `axes`            | Map of four-byte tags to supported values, e.g. `{"wght":400,"opsz":16}`; default empty                  |
| `hinting`         | `none`, default `auto`, `interpreter`, or `auto_fallback`                                                |
| `output_bits`     | 1, 2, 3, 4, or 8; default 1                                                                              |
| `mono_threshold`  | 1–255, default 128; binary ink when coverage reaches the threshold                                       |
| `gray_gamma`      | Finite positive exponent, default 1; nearest-level rounding of `(coverage/255)^gamma`                    |
| `missing_glyphs`  | Default `error`, or `skip` with explicit missing-codepoint output                                        |
| `kerning`         | Default true; false disables source pair adjustments while retaining representability checks             |
| `metric_rounding` | Default `subpixel` rounds to 1/64px; `pixel` rounds advances and pair adjustments individually to pixels |
| `mono_raster`     | Optional scan settings; schema and defaults in the [API](API.md#monochrome-scan-converter-settings)      |

Mono threshold applies to coverage-based 1-bit renderers; candidate Mono uses center fill and ignores it. Gamma applies
only to gray output. `mono_raster` dropout correction (`off`/`simple`/`smart`) and short-stroke preservation apply only
to candidate Mono; every other renderer or depth rejects non-default values. Each glyph allocation is bounded to 4 Mi
pixels. Renderer-specific restrictions and candidate integer metrics are defined in the [API](API.md).

## Specimen configuration

[specimens.json](specimens.json) selects fonts, sizes, axes, profiles, variants and cards;
[preview-policy.json](preview-policy.json) owns the agreed publication scope. Renderer identities belong to the
[revision index](../../docs/revisions/001/README.md#iterations).

- `variants` gives each renderer an ID, kind, version, renderer role, hinting mode and extension policy. Automatic
  fitting uses `diagonal-01` for the legacy baseline and `font-hints-01` for the candidate. Reference variants use
  `none`; renderer routes with `none` delegate to that reference.
- `profiles` defines shared output settings for the 1-bit and 3-bit modes, uniformly across selected fonts and sizes.
- `characters` defines the drawable repertoire; `cards` supplies sample IDs, titles and content (see below).
- `defaults` supplies `sizes`, `variants` and `profiles` to each family.
- `preview_policy` points to a `preview-policy-v1` policy with a `families` map of agreed size arrays. Validation
  follows the [selection contract](CONTRACT.md#generation-selection).
- `families` supplies identity, display name, font path, provenance/checksum and axes. Font paths resolve relative to
  the configuration. An axis value is a number or `"size_px"`, binding it to the rendering size.
- Family `sizes`, `variants` or `profiles` arrays replace inherited selections. A size object can override variants or
  profiles for that size alone.

For example, these family fields select grayscale at 14 px and both modes at 20 px:

```json
{
  "variants": ["reference"],
  "profiles": ["gray_3bit"],
  "sizes": [14, {"size_px": 20, "profiles": ["mono_1bit", "gray_3bit"]}]
}
```

Without a preview policy, edit family records and selections to change the matrix. Selections are nonempty and reference
existing IDs; family sizes are unique and within 1–512 px. Each active variant selects at least one case. Reserved
evaluation slices remain excluded from ordinary selection. `specimen_config::load(path)` validates and resolves explicit
family/size/variant/profile cases; export verifies font bytes and axis bounds and records effective coordinates.

### Configure preview cards

Edit `cards` in [specimens.json](specimens.json), for example:

```json
{
  "cards": [
    {
      "id": "reading",
      "title": "Reading sample",
      "content": "Pack my box with five dozen liquor jugs.\nminimum AVATAR To Wa"
    }
  ]
}
```

Array order sets card order in every family, size and mode. IDs are unique; titles and content are nonempty. Content
uses configured `characters` plus spaces and newlines; add new drawable characters to `characters` too.

`Character coverage` is appended from the repertoire (uppercase, lowercase and digits/symbols on separate lines).
`Changed symbols` comes from the comparison export. Their IDs (`coverage`, `changed-symbols`) and titles are reserved;
exclude them from `cards`. Empty `cards` keeps coverage and available changed symbols. Existing inline `samples` (`id`,
`label`, `text`) remain supported; use either `cards` or `samples`.

Regenerate specimens and comparisons after edits with the commands below.

## Generate reference specimens

```sh
just specimens
just specimens tools/generator/specimens.json out/specimens
```

The equivalent CLI is:

```sh
cargo run --locked --manifest-path tools/generator/Cargo.toml --bin font_specimens -- \
  tools/generator/specimens.json out/specimens
```

`specimens::publish(config_path, output_directory)` publishes the selected packages. Selection, output layout and
publication guarantees belong to the [specimen contract](CONTRACT.md); rendering and composition behavior belong to
[the API](API.md#reference-and-specimen-capture).

## Export glyph comparisons

After specimens, run `just comparisons`. [comparisons.json](comparisons.json) uses `comparison-config-v2` and supplies
the numeric symbol-route `id`; inputs and exports follow the [comparison contract](CONTRACT.md#glyph-comparison-export).
Inspect live results with `just preview` (see the [web commands](../web/README.md)).

## Calibration inputs

Font identities, axes, licenses and provenance limits belong to [fonts/README.md](../../fonts/README.md). The generator
does not download fonts. Tests read checked-in calibration fonts and original CFF/CFF2 fixtures. Regenerate those
fixtures with:

```sh
cargo run --locked --manifest-path tools/generator/Cargo.toml --example build_fixtures
```

## Supported input and output

See [font capabilities and bitmap output](API.md#supported-input-and-output).

## Rendering settings

See the [settings table](#builds-and-settings) and [reference capture controls](API.md#reference-and-specimen-capture).

### Legacy production fitting

See [production and reference renderer routing](API.md#renderer-routing).

### Working candidate fitting

See [candidate strategy selection](API.md#working-candidate-fitting).

## Live spacing API

See [layout and exported metrics](API.md#live-spacing-api).

### Tracking policy

See [tracking constraints](API.md#tracking-policy).

## Evaluation

Run the Rust evaluator with the [evaluation commands](../../docs/evaluation.md#usage); panel assessment guidance is in
the [font evaluation guide](../../docs/references/font-evaluation.md).
