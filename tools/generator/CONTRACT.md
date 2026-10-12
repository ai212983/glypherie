# Specimen generator output contract

<!-- cspell:words fvar kerx vkrn subtables -->

The specimen generator publishes a self-contained package of native-resolution PNG specimens and display metadata. This
interface is independent of the generator's implementation language. The web generator consumes the package according to
the [web generator contract](../web/CONTRACT.md).

## Generation selection

[specimens.json](specimens.json) supplies family sources, sizes, renderer variants, and output profiles. See the
[configuration guide](README.md#specimen-configuration) for inheritance and per-family/per-size overrides.

Resolve the [specimen configuration](README.md#specimen-configuration) into explicit family/size/variant/profile cases.
Publish one package per selected renderer variant and verify its coverage against those cases.

The checked-in configuration's `preview_policy` points to [preview-policy.json](preview-policy.json), using schema
`preview-policy-v1` and a `families` map of agreed size arrays. The configuration and policy own the actual preview
selections. Check exact family coverage and effective sizes for every variant/profile after resolving overrides.
Missing/invalid policy, additions, removals or matrix drift fail before rendering/publication and preserve existing
pointers. Change configuration, policy and guard expectations together only for an explicitly requested scope change.
Broader diagnostic configurations may omit the policy and use isolated output; the normal configuration must retain it.

The configuration's variant ID is a logical name such as `reference`. Published package IDs identify immutable
render/composition snapshots. Iteration versions are unique positive numeric `revision.iteration` pairs, for example
`001.01`; compare both components numerically. The active pointer always selects the latest iteration of the latest
revision, or reference when no iteration exists. The latest configured variant must have render cases. There is no
manual active-variant override. Record resolved selections and variant/profile settings in the canonical render
artifact.

`published.json` records the latest completed generation's logical-variant-to-package mapping using schema
`specimen-publication-v1` and a `variants` object. Derive the current comparison input from the latest revision and
iteration in this mapping. Explicit renderer roles select a working candidate against the approved baseline; with no
newer candidate, select baseline against reference. Versions identify states rather than compile-time features. Retain
the approved baseline and reference variants in the configuration. Older packages without roles retain their historical
previous-revision comparison policy.

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
  canonical/
    <generation-sha256>.json
    <composition-sha256>.json
```

The generator owns `out/specimens/`. Each package is immutable. Changes to source rendering, sample text, composition,
dimensions, or assets create a new package ID. Content-addressed images can be reused when their bytes match.

`active.json` records the automatically selected latest working variant. Publication and production approval are
separate; current approved/candidate identities belong in the
[revision index](../../docs/revisions/001/README.md#iterations).

### Active pointer

```json
{
  "schema_version": "web-active-v1",
  "variant_id": "skrifa-reference-001",
  "manifest": "skrifa-reference-001/manifest.json"
}
```

The manifest path is relative to `out/specimens/` and is exactly `<variant_id>/manifest.json`. Variant IDs are single
path segments containing ASCII letters, digits, hyphens, and underscores. Publish the complete, validated package first,
then update the active pointer atomically.

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

The generation hash identifies the canonical render artifact separately from the exported specimen composition. Full
provenance, geometry, and layout policy remain in the canonical artifacts; the display manifest carries the metadata
needed to present the specimens.

Canonical glyph records preserve Unicode `codepoint` identity and record the actually drawn, coordinate-selected
`glyph_id`. Outlines, source geometry and metrics follow the
[scalar-resolution contract](README.md#supported-input-and-output) for every renderer role; nominal character-map
coverage remains descriptive metadata.

New exports include each family's `metadata`, extracted once from the checksum-verified source bytes with the upstream
Skrifa reader. Older immutable packages can omit this field. Metadata is descriptive and does not affect rendering,
shaping, fitting or preview scope.

- `names`: nullable strings for `family`, `style`, `full`, `postscript`, `version`, `copyright`, `manufacturer`,
  `designer`, `description`, `vendor_url`, `designer_url`, `license` and `license_url`. Prefer English, otherwise the
  first nonempty localized value. Family/style prefer typographic name IDs 16/17, falling back to 1/2. License fields
  are embedded text, not verified provenance or a substitute for the supplied license.
- `axes`: source-ordered records with `tag`, nullable localized `name`, `min`, `default`, `max` and `hidden`. An empty
  list identifies a static font. These describe supported coordinates, separately from each size group's selected axes.
- `kerning`: `horizontal` and `vertical` booleans, with `sources` identifying `GPOS kern`, `GPOS vkrn`, `kern` or
  `kerx`. Detect nonempty positioning lookups under the registered kerning features or populated legacy kerning
  subtables; GPOS presence alone is insufficient. This reports available data, not an assurance that a particular pair
  or script receives an adjustment. Missing kerning tables mean no kerning; malformed tables fail extraction.
- `style`: nullable `slope` (`upright`, `italic`, `oblique`), raw OS/2 `weight_class` and `width_class`, and
  `italic_angle` in degrees. Values describe the font's default instance, not a preview's selected variation
  coordinates.
- `classification`: nullable raw IBM `family_class` (class in the high byte, subclass in the low byte), ten-byte
  `panose`, and `monospaced` from the post table's fixed-pitch declaration. Missing or unspecified classification does
  not authorize guessing from a filename or outlines.
- `coverage`: nullable `character_count` and sorted, disjoint, inclusive `ranges` of Unicode scalar values from the
  renderer's selected nominal character map. Exclude missing glyphs, out-of-range glyph IDs and surrogate codepoints.
  Missing/unsupported Unicode maps and symbol encodings have unknown coverage. This is character mapping coverage, not a
  guarantee of language shaping support.
- `declared_unicode_ranges`: nullable four-word OS/2 range flags, separate from actual character-map coverage.

Definitions follow the OpenType [name](https://learn.microsoft.com/en-us/typography/opentype/spec/name),
[fvar](https://learn.microsoft.com/en-us/typography/opentype/spec/fvar),
[OS/2](https://learn.microsoft.com/en-us/typography/opentype/spec/os2),
[kerning features](https://learn.microsoft.com/en-us/typography/opentype/spec/features_ko) and
[kern](https://learn.microsoft.com/en-us/typography/opentype/spec/kern) specifications, plus Apple's
[kerx](https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6kerx.html) definition.

Each family has a nonempty `sizes` array. Each size group contains:

- `size_px`: requested native rendering size.
- `axes`: actual resolved variation coordinates used for the group.
- `thumbnail`: positive integer `width_px` and `height_px`, shared by every image in the group across samples and output
  profiles.
- `items`: explicitly ordered specimen records.

Each item contains a package-wide unique `id`, `profile`, readable `label`, exact sample `text`, and `outcome`:

- `rendered`: includes `image.path` and `image.sha256`. The path is relative to the manifest directory and has the form
  `assets/<image.sha256>.png`.
- `failed` or `unsupported`: includes a nonempty `reason` describing the problem.

Family and item array order carry the intended presentation order. IDs provide stable references for content and
observations. Each size appears once per family.

### Example

This illustrative excerpt shows one family, size, and sample. The all-zero hashes are placeholders. A complete export
includes every group and profile sample selected by the resolved configuration for this variant.

```json
{
  "schema_version": "web-specimens-v1",
  "variant": {
    "id": "skrifa-reference-001",
    "kind": "reference",
    "version": null,
    "generation_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "composition_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
  },
  "profiles": [
    {"id": "mono_1bit", "output_bits": 1},
    {"id": "gray_3bit", "output_bits": 3}
  ],
  "families": [
    {
      "id": "roboto",
      "name": "Roboto",
      "source_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "sizes": [
        {
          "size_px": 14,
          "axes": {"wght": 400, "wdth": 100},
          "thumbnail": {"width_px": 480, "height_px": 128},
          "items": [
            {
              "id": "roboto-14-mono-reading",
              "profile": "mono_1bit",
              "label": "Reading sample",
              "text": "Pack my box with five dozen liquor jugs.",
              "outcome": "rendered",
              "image": {
                "path": "assets/0000000000000000000000000000000000000000000000000000000000000000.png",
                "sha256": "0000000000000000000000000000000000000000000000000000000000000000"
              }
            }
          ]
        }
      ]
    }
  ]
}
```

## Specimen images

Compose each PNG directly from canonical generated pixels and declared layout metrics at native resolution. Use the
generator's declared spacing policy and record layout limitations in the canonical artifact. Represent failures or
unsupported samples explicitly through their item outcomes and reasons.

Choose one canvas width and height per family/size group. Pad smaller samples with white space. Fit larger samples
through deliberate text wrapping or a larger shared canvas, preserving all sample content and source pixels. Each PNG's
actual dimensions equal the group's declared thumbnail dimensions.

Images contain specimen pixels; labels and captions are supplied as manifest metadata. Use lossless PNG encoding, a
white background, black/white pixels for 1-bit specimens, and the declared eight display levels for 3-bit specimens.

## Glyph comparison export

`comparisons.json` uses schema `comparison-config-v2` and an `id` containing a numeric route ID such as `01`. It cannot
select renderer inputs or labels. Derive them using [generation selection](#generation-selection), with labels from
package versions. A reference-only publication exports an empty comparison index; invalid or ambiguous versions fail
publication.

The comparison exporter reads canonical rendered pixels and publishes:

```text
out/specimens/comparisons/
  index.json
  <id>-<manifest-sha256>/
    manifest.json
    assets/<image-sha256>.png
```

`index.json` uses schema `web-comparisons-v1` with entries containing `id` and `manifest`. Each manifest uses
`web-glyph-comparison-v1`, identifies its two input packages and labels, and contains profiles and families. Each family
contains ascending size groups with resolved axes, a shared canvas, and Unicode glyph records.

- A canvas declares `width_px`, `height_px`, `origin_x`, `baseline_y`, and `padding_px`. Its bounds include both inputs
  across profiles, retaining the same baseline and pen origin for all images.
- Each glyph declares its Unicode `codepoint`, `character`, and selected `profiles`. Each profile includes `id`, rounded
  native `advance_px`, and `previous`, `current`, and `difference` image references using `path` and `sha256`.
- Compare aligned native pixels per size/profile before encoding. Export comparison images only when pixel values
  differ; omit identical profiles and glyphs. Size groups may have an empty `glyphs` array. Missing glyphs, size/profile
  cases, or render reports fail comparison publication with input, family, size, profile, and codepoint details.
- Export a `statistics` array with one record per output profile: `profile`, `same_symbols`, `changed_symbols`,
  `average_changed_pixels`, and `median_changed_pixels`. Count each drawable character once per selected
  family/size/profile, including identical glyphs omitted from the image records. A changed pixel is an aligned native
  pixel whose quantized value differs, regardless of the magnitude of that difference. Average and median use changed
  symbols only; both are zero when no symbols changed. Every counted symbol has both renderer inputs.
- Native 8-bit RGB PNGs retain the configured black/white or eight gray levels. Differences use blue `#0060ff` for
  increased ink and red `#e02020` for decreased ink; unchanged pixels retain their shade.
- Every exported profile has previous, current, and difference images, with `reason` set to null. Missing inputs are
  errors; failed publication leaves the existing comparison index unchanged.
- Validate input identities, font/axis compatibility, bitmap dimensions/levels, and asset integrity. Publish complete
  content-addressed packages before atomically updating the index. Active selection remains unchanged.

## Publication checks

Before publishing, verify:

- Schema versions, pointer/package identity, safe variant IDs, and SHA-256 values.
- Family identities, unique size groups, resolved axes, and unique item IDs.
- Profile definitions, item profile references, and outcome-specific fields.
- Asset existence, content hashes, and native PNG dimensions and pixel levels.
- Relative paths that resolve within the package, including symlink resolution.
- Coverage of the resolved configuration for the exported variant. Missing selected families, groups, or profile samples
  are publication errors; explicit item failures remain available for inspection.
- Complete immutable package publication followed by an atomic pointer update.

The [generator README](README.md) describes the reference rendering policy and configuration. Reserved evaluation slices
remain excluded from ordinary specimen selection. See the [web README](../web/README.md) for tooling.
