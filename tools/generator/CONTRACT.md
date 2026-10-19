# Specimen generator output contract

<!-- cspell:words fvar kerx vkrn subtables -->

The specimen generator publishes a self-contained package of native-resolution PNG specimens and display metadata,
independent of the generator's implementation language. This document covers only that published interface.

## Generation selection

[specimens.json](specimens.json) supplies family sources, sizes, renderer variants, and output profiles; the
[configuration guide](README.md#specimen-configuration) defines inheritance and overrides. The resolved configuration
yields explicit family/size/variant/profile cases, one published package per selected renderer variant, verified against
those cases.

When configured, `preview_policy` must match the resolved family/size coverage. Missing or invalid policy or coverage
drift fails before rendering or publication and preserves existing pointers.

`published.json` (schema `specimen-publication-v1`) maps logical variants to packages. Iteration versions are unique
numeric `revision.iteration` pairs compared numerically. Renderer roles select the latest candidate newer than the
baseline against that baseline, or baseline against reference when no newer candidate exists. Without renderer roles,
selection uses the latest iteration against the latest iteration of an earlier revision, or reference when none exists.
The active pointer selects the current input of that comparison, or reference when no iteration exists. The selected
variant and comparison baseline must each have render cases.

## Output location and selection

Paths are relative to the repository root:

```text
out/specimens/
  active.json
  published.json
  <variant-id>/
    manifest.json
    assets/
      <image-sha256>.png
```

The generator owns `out/specimens/`. Each package is immutable: changes to source rendering, sample text, composition,
dimensions, or assets create a new package ID; content-addressed images may be reused when their bytes match.

`active.json` uses schema `web-active-v1` with `variant_id` and `manifest` exactly `<variant_id>/manifest.json`. Variant
IDs are single path segments of ASCII letters, digits, hyphens, and underscores.

## Package manifest

`manifest.json` contains these required fields:

| Field                        | Required meaning                                                                                                      |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `schema_version`             | `web-specimens-v1`                                                                                                    |
| `variant.id`                 | Immutable package identity matching the active pointer                                                                |
| `variant.kind`               | `reference` or `iteration`                                                                                            |
| `variant.version`            | Nonempty human-facing version for an iteration; null for a reference                                                  |
| `variant.generation_sha256`  | SHA-256 identity of the underlying canonical render artifact                                                          |
| `variant.composition_sha256` | SHA-256 identity of the sample/layout composition artifact                                                            |
| `profiles`                   | Definitions of the included configured profiles: `mono_1bit` with output bits 1 and/or `gray_3bit` with output bits 3 |
| `families`                   | Ordered family records with a stable `id`, display `name`, original-font `source_sha256`, and `sizes`                 |

Exports include each family's descriptive `metadata`; consumers also accept packages without it. It has these fields:
`names` (nullable `family`, `style`, `full`, `postscript`, `version`, `copyright`, `manufacturer`, `designer`,
`description`, `vendor_url`, `designer_url`, `license`, `license_url`); `axes` (source-ordered `tag`, nullable `name`,
`min`, `default`, `max`, `hidden`); `kerning` (`horizontal`, `vertical`, and `sources` drawn from `GPOS kern`, `GPOS
vkrn`, `kern`, `kerx`); `style` (nullable `slope` of `upright`/`italic`/`oblique`, raw `weight_class` and `width_class`,
`italic_angle` in degrees); `classification` (nullable raw IBM `family_class`, ten-byte `panose`, `monospaced`);
`coverage` (nullable `character_count` and sorted, disjoint, inclusive scalar `ranges`); and `declared_unicode_ranges`
(nullable four OS/2 range words). Definitions follow the OpenType
[name](https://learn.microsoft.com/en-us/typography/opentype/spec/name),
[fvar](https://learn.microsoft.com/en-us/typography/opentype/spec/fvar),
[OS/2](https://learn.microsoft.com/en-us/typography/opentype/spec/os2), and
[kern](https://learn.microsoft.com/en-us/typography/opentype/spec/kern) specifications.

Each family has a nonempty `sizes` array; array order is the intended presentation order. Each size group contains
`size_px`, the resolved `axes` coordinates, a `thumbnail` (`width_px`, `height_px`, shared by every image in the group),
and explicitly ordered `items`, each appearing once per family and size. Each item has a package-wide unique `id`,
`profile`, `label`, exact sample `text`, and `outcome`: `rendered` includes `image.path` of the form
`assets/<image.sha256>.png` with `image.sha256`; `failed` or `unsupported` includes a nonempty `reason`.

## Specimen images

Each PNG is composed at native resolution, its dimensions equal the group's declared thumbnail dimensions. Encoding is
lossless PNG on a white background: black/white pixels for 1-bit specimens, the declared eight display levels for 3-bit.
Failures and unsupported samples appear only through item outcomes and reasons, never as substitute images.

## Glyph comparison export

Comparison inputs and labels derive from [generation selection](#generation-selection) and package versions. A
reference-only publication exports an empty comparison index; invalid or ambiguous versions fail publication.

The exporter publishes:

```text
out/specimens/comparisons/
  index.json
  <id>-<manifest-sha256>/
    manifest.json
    assets/<image-sha256>.png
```

`index.json` uses schema `web-comparisons-v1` with entries containing `id` and `manifest`. Each manifest uses
`web-glyph-comparison-v1`, identifies its two input packages and labels, and contains profiles and families with
ascending size groups, resolved axes, and a shared canvas (`width_px`, `height_px`, `origin_x`, `baseline_y`,
`padding_px`) under one baseline and pen origin.

Each glyph record declares `codepoint`, `character`, and selected `profiles`. Each profile includes `id`, rounded native
`advance_px`, and `previous`, `current`, and `difference` image references (`path`, `sha256`, `reason` null), exported
only when aligned native pixels differ. Difference images use blue `#0060ff` for increased ink and red `#e02020` for
decreased ink; unchanged pixels retain their shade.

Each manifest carries a `statistics` array with one record per profile: `profile`, `same_symbols`, `changed_symbols`,
`average_changed_pixels`, and `median_changed_pixels`. Each drawable character counts once per family/size/profile,
including identical glyphs omitted from image records; a changed pixel is an aligned native pixel whose quantized value
differs, and averages/medians over changed symbols are zero when none changed. Missing glyphs, cases, inputs, or render
reports fail publication with identifying details and leave the existing comparison index unchanged.

## Publication checks

Publishing guarantees: schema versions, pointer/package identity, safe variant IDs, and SHA-256 values agree; family
identities, resolved axes, size groups, and item IDs are unique and complete against the resolved configuration; profile
references and outcome-specific fields are valid; assets exist with matching hashes, native dimensions, and pixel
levels; and every relative path resolves within its package, including through symlinks. A complete, validated package
is published before any pointer or index update; each update is atomic.
