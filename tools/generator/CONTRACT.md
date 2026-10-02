# Specimen generator output contract

The specimen generator publishes a self-contained package of native-resolution PNG specimens and display metadata. This
interface is independent of the generator's implementation language. The web generator consumes the package according to
the [web generator contract](../web/CONTRACT.md).

## Iteration lifecycle

An iteration is dedicated to one specific problem identified by user feedback. Tweaks and validation for that problem
retain the same iteration ID and renderer extension policy. It closes only when user and agent agree no further actions
remain for that problem: resolved, not fixable, or explicitly assigned to an agreed follow-up. The user must explicitly
agree to closure; tests, publication, and a new implementation approach do not imply it. Record the closure decision
before advancing iteration identity. See the [revision guidance](../../docs/revisions/README.md).

## Generation selection

[specimens.json](specimens.json) supplies family sources, sizes, renderer variants, and output profiles. See the
[configuration guide](README.md#specimen-configuration) for inheritance and per-family/per-size overrides.

The `cards` array defines editable specimens using `id`, `title`, and `content`, in display order. Titles become item
labels; content becomes exact sample text and rendered image content. Character coverage is appended automatically from
`characters`; changed symbols are supplied by the comparison export. Both are fixed cards outside this array.

Resolve selections into explicit family/size/variant/profile cases. Publish one package per selected renderer variant,
containing its selected families, size groups, and profile samples. Package coverage is checked against those resolved
cases. The normal preview selects three families at 14/16/18/20 px in both profiles. The checked-in configuration's
`preview_policy` points to `preview-policy.json` (relative to the configuration), with schema `preview-policy-v1` and
`families` mapping family IDs to agreed size arrays. Check exact family coverage and effective size sets separately for
every family/variant/profile, after resolving defaults and overrides. Reject missing/invalid policy, additions,
removals, or changed sizes before rendering or writing output; failed publication preserves existing pointers.

This policy is a scope guard independent of renderer iterations. Change the configuration, policy, and regression
expectations together only when the user's task includes a preview-matrix change. Diagnostic sweeps use Rust
requests/tests or separate temporary configurations with isolated output; they do not change normal preview defaults.
Generic diagnostic configurations may omit `preview_policy`, but the checked-in normal configuration must retain it.

The comparison configuration may supply an `attention` path to an explicit `symbol-attention-v1` annotation file,
resolved relative to that configuration. See the [attention guide](../../docs/evaluation.md#attention-card). Validate
its iteration, unique IDs/cases, inspection types, optional hints and statuses before updating the comparison pointer.
Export pending/confirmed marks as a separate `attention` array, including unchanged cases within the agreed preview
scope. Accepted marks require a recorded disposition and are omitted from that array. Require every rendered mark to
match published and configured family/size/axes/profile cases and symbol coverage; reject diagnostic additions before
publication. Reuse canonical renders only. Their native aligned images are content-addressed within the comparison
package. Do not expand normal specimens, change ordinary statistics or alter fitting decisions.

The configuration's variant ID is a logical name such as `reference`. Published package IDs identify immutable
render/composition snapshots. Iteration versions are unique positive numeric `revision.iteration` pairs, for example
`001.01`; compare both components numerically. The active pointer always selects the latest iteration of the latest
revision, or reference when no iteration exists. The latest configured variant must have render cases. There is no
manual active-variant override. Record resolved selections and variant/profile settings in the canonical render
artifact.

`published.json` records the latest completed generation's logical-variant-to-package mapping using schema
`specimen-publication-v1` and a `variants` object. Derive the current comparison input from the latest revision and
iteration in this mapping. The baseline is the latest iteration of the preceding revision, or reference if none exists.
Retain the previous revision's latest variant in the configuration so it is published for comparison.

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
separate decisions. The web index always shows this latest revision and iteration.

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
select renderer inputs or labels. Export one comparison for the latest revision's latest iteration against the preceding
revision's latest iteration. Fall back to the unique reference only when there is no preceding revision. For revision
001, every iteration compares with reference, including 001.01. Derive labels from package versions. A reference-only
publication exports an empty comparison index. Invalid or ambiguous versions fail publication.

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
