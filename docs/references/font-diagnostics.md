# Font diagnostics

Font diagnostics use the same Rust generator and rendering libraries as the specimen workflow. Capture settings and
input identities with each result, then investigate reported differences against the source design and native specimens.

## Capture tools

| Tool                | Output                                                                                                                               |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `font_reference`    | Fitted outline commands, exact floating-point bits, raw coverage, final pixels, metrics, and engine identities for mono or grayscale |
| `font_hint_probe`   | Explicit automatic or interpreter fitting captures for monochrome output                                                             |
| `common_rasterizer` | Coverage and pixels from supplied outline commands with declared rendering settings                                                  |

The [generator README](../../tools/generator/README.md#rendering-settings) describes reference rendering controls. The
reference API keeps upstream rendering independent of optional fitting changes.

## Compare specimens

`font_comparison` exports glyph images and pixel differences aligned to a shared origin and baseline. Its selection and
output are described in the [comparison contract](../../tools/generator/CONTRACT.md#glyph-comparison-export).

`font_specimen_diff` compares two canonical generation artifacts and records changed outlines, pixels, metrics, and
advances. For monochrome glyphs it also reports changes in connected ink components and enclosed white regions:

```sh
cargo run --locked --manifest-path tools/generator/Cargo.toml --bin font_specimen_diff -- \
  REFERENCE_CANONICAL.json PROPOSAL_CANONICAL.json OUTPUT.json
```

The topology calculation uses eight neighbors for ink and four for white regions. A changed count identifies a case for
source and visual review; it does not establish whether the change improves readability.

## Validation and physical evaluation

Run the generator suite from the repository root:

```sh
cargo test --locked --manifest-path tools/generator/Cargo.toml
```

The tests cover supported font formats, rendering controls, reproducibility, source metrics, layout, reference
invariance, and specimen publication. Font identities and variation axes are recorded with the
[font assets](../../fonts/README.md).

[Font evaluation](font-evaluation.md) covers measurement limits and physical reading evaluation.
[Panel frame formats](panel-frame-formats.md) preserves packing conventions and the grayscale verification frame.
