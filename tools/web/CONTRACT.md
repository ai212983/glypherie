# Web output contract

`just web` builds a static site in `out/web/` from the inputs defined by the
[specimen generator contract](../generator/CONTRACT.md). Paths below are relative to the repository root.

## Import and output

- Read `out/specimens/published.json` and package versions to select the latest iteration of the latest revision,
  comparing revision and iteration numbers numerically. The index `/` always shows this package; manual preview
  overrides are not supported. Use `active.json` only for single-package exports without a publication mapping.
- Compare an explicit working candidate with the latest approved baseline, including within the same revision. With no
  newer candidate, compare baseline with the unique reference. Accepted 001.01 therefore compares with reference. Older
  packages without role metadata retain previous-revision selection. Reject missing or stale comparison inputs and
  labels. Do not silently fall back to an older package if latest content is invalid or incomplete.
- Read `out/specimens/comparisons/index.json` to select comparison packages.
- Publish a pointer to the selected latest package in `out/web/content/active.json`. Copy the specimen manifest and
  referenced PNGs into `out/web/content/`, preserving package paths and bytes. Copy comparison manifests and PNGs into
  `out/web/comparison-content/<package-id>/` in the same way.
- Before copying, check JSON schemas, required fields, package identities, paths confined to each package, SHA-256
  checksums, PNG dimensions, and permitted pixel values against the input contract.
- Serve prepared files from `out/web/`. Navigation and asset URLs must work beneath a hosting URL prefix.

## Specimens

- Identify the active package as `reference` or its `variant.version`. Show compact header badges for baseline →
  current, for example `reference → 001.01`, without a separate comparison sentence. Use manifest names and labels for
  families and profiles.
- Preserve manifest family order in the font dropdown. The index shows the selected font's interactive specimen, with no
  published sample rows, size sections, glyph grids, or comparison footer. Exported specimen images and comparison data
  remain available to tooling; standalone symbol comparisons retain their routes.
- Beneath each main-page family heading, show a compact metadata definition list: kerning availability, supported axes
  with names/tags, ranges and defaults, and available design/pitch classification. Do not display a style field. Read
  the generator's optional `family.metadata`; older packages display unknown metadata. Show an empty axis list as a
  static font and distinguish horizontal from vertical-only kerning. Use registered IBM family classes when specified,
  otherwise interpret PANOSE in its Family Kind context. Omit unspecified/reserved classification values and omit the
  entire classification field when no design or pitch information is known; never infer classification from the
  configured name. Classification mappings follow the
  [IBM specification](https://learn.microsoft.com/en-us/typography/opentype/spec/ibmfc) and
  [PANOSE guide](https://monotype.github.io/panose/pan2.htm).
- A missing publication mapping and active pointer produces an empty state. Invalid or incomplete selected content
  produces an error identifying the selection and problem. Do not silently substitute another package.
- Validate changed counts and pixel statistics against the difference images, counting every symbol even when assets are
  shared. Statistics stay available to tooling through the exported comparison manifests even though the index shows no
  footer.

## Profiles and pixel display

- Show one available output profile at a time, initially 1-bit when available. Switching profiles preserves zoom.
- Provide 1×, 2×, 3×, and 4× zoom. Display exported PNGs at their native dimensions multiplied by the selected zoom,
  using nearest-neighbor scaling and the same image bytes at every zoom level.
- Keep labels and controls at ordinary UI scale. Reserve scaled image dimensions in layout; oversized images scroll
  locally without reducing their scale.
- Persist zoom across reloads. The specimen index starts at 1×; symbol pages have a separate setting, initially 4×.
  Explicit `zoom` URL parameters override stored values.
- Navigation preserves the selected profile and uses the destination's zoom setting.

## Comparisons

- There is no separate `/reviews/` folder or endpoint. Remove obsolete review output on rebuild. All visual
  communication goes through the web index and its symbol pages.
- `/` shows the selected font's interactive specimen. Match comparison inputs by the active package identity. Symbol
  pages stay directly reachable at their stable routes below; the index links none.
- Generate thumbnails and symbol pages only for pixel changes, per size/profile. Retain changed sizes/profiles on each
  symbol page, hide empty thumbnail blocks, and remove stale generated symbol pages on rebuild. Missing comparison
  images or reported missing glyphs fail import and the site build.
- `/<id>/<family-id>/U<HEX>/` groups a symbol by ascending size. Show previous, current, and difference images with the
  exported version labels, shared pen origin, and baseline. Active symbol pages link back to `/`.
- `/<id>/` has no index page or redirect; requests return 404. Symbol pages link directly back to `/`.
- Preserve exported difference colors: blue for added ink, red for removed ink, and the original shade for unchanged
  pixels. An output mode with no changed pixels shows that status on the symbol page.

## Attention

- Comparison manifests may include `attention`, an array of explicitly annotated symbol cases. Each entry has `id`,
  `family_id`, `family_name`, `codepoint`, `character`, `size_px`, `axes`, `status`, `inspection`, `description`,
  `canvas` and `profiles`; profiles use the existing glyph-image contract. Require unique IDs and exact cases, valid
  images and a nonempty inspection type; the per-symbol hint may be empty. Status is `pending` or `confirmed`; accepted
  dispositions remain in generator input.
- Attention cases render on the existing symbol routes with an inspection type and optional short hint beside the
  comparison images. Hide axes/status metadata and diagnostic labels. Labels and hints keep ordinary UI scale; images
  use the existing profile/zoom controls. Preserve URL-prefix support and controls in symbol links.
- Attention membership is independent of pixel differences, so unchanged marked cases still have comparison images and
  symbol pages. Require all comparison and Attention cases to match the active specimen family/size/axes/profile scope;
  reject debug cases at export and web build. Do not generate diagnostic renders for Attention.
- Include marked cases on the existing symbol routes, at stable `attention-<id>` anchors, showing both versions,
  difference, inspection type and optional per-symbol hint. Rebuild removes obsolete marked cases. No separate review
  endpoint is created. Attention is a request for assessment, not automatic rejection or acceptance.

## Interactive specimens

- The index holds one font dropdown and exactly one visible interactive block: a font size input, one slider per
  non-hidden variable axis with published min/default/max, a text preset select, a multi-line sample textarea, and
  reset. Static fonts render no axis inputs. Hidden family sections are acceptable; the user sees one tester.
- The preset select offers the configured card texts (Reading sample, Numbers and symbols) plus Custom, which the page
  selects whenever the textarea no longer matches a preset. Cards come from the generator config through the web
  importer; presets are never hardcoded in page sources. Reset restores the published default size, axes, full sample
  text, and matching preset.
- Controls default to the published first size, axes, and full sample text, and re-render a canvas through the WASM
  renderer with the published source bytes. Each font's size, axes, text, and preset persist across font switches; only
  the active font loads and renders, and inactive fonts are released. The global profile switch and zoom apply to the
  active font.
- Zoom is integer magnification of the rendered glyph pixels: the request keeps the approved size, axes, and hinting
  while shrinking to the logical width for the zoom factor, then scales up with smoothing off. Display width follows the
  parent; display height fits the laid-out content (the sum of the actual result `layout().lines` heights times zoom)
  with at most one correction re-render after a bounded first pass, growing and shrinking with the text. A viewport
  resize remeasures the width and re-renders. Content taller than the native 4096 px render limit shows a concise
  overflow message instead of silent truncation.
- Missing WASM output or font sources leave a concise unavailable message with disabled controls (including textarea and
  select), never a build error. Font bytes publish to `interactive-fonts/` and must hash-match the manifest source;
  paths stay inside the repository and only cover the renderer's supported font types.
- `just wasm-build` builds the renderer and stages `assets/wasm/`; `just preview-build` runs it before the page.

## Verification

Check content validation, byte-for-byte copying, presentation, content states, and browser behavior over HTTP, including
beneath a URL prefix. See [README.md](README.md) for commands.
