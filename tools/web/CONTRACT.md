# Web output contract

`just web` builds a static site in `out/web/` from the inputs defined by the
[specimen generator contract](../generator/CONTRACT.md). Paths below are relative to the repository root.

## Import and output

- Select the active package and renderer comparison using the
  [generator selection rules](../generator/CONTRACT.md#generation-selection). Read `out/specimens/published.json`; use
  `active.json` only for single-package exports without that mapping. Reject missing/stale comparison inputs or labels
  and invalid/incomplete latest content rather than selecting an older package.
- Read `out/specimens/comparisons/index.json` to select comparison packages.
- Publish a pointer to the selected latest package in `out/web/content/active.json`. Copy the specimen manifest and
  referenced PNGs into `out/web/content/`, preserving package paths and bytes. Copy comparison manifests and PNGs into
  `out/web/comparison-content/<package-id>/` in the same way.
- Before copying, validate imported packages against the
  [generator publication checks](../generator/CONTRACT.md#publication-checks).
- Serve prepared files from `out/web/`. Navigation and asset URLs must work beneath a hosting URL prefix.

## Specimens

- The index subtitle shows only the active iteration identity, or `reference`; omit comparison names and arrows. Use
  manifest names and labels for families and profiles.
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
- Below metadata, provide a native collapsed Kerning pairs section with a filter and signed pixel values. Populate it
  lazily through the [WASM kerning-pair API](../wasm/README.md#kerning-pairs); convert its 26.6 adjustments to pixels
  and display reported omissions. Refresh on size/axes/Reset, including hidden default axes, and bound the per-family
  cache to sixteen coordinates. Keep extraction independent of other rendering controls. Show unavailable/extraction
  errors locally without breaking the preview. A loaded renderer missing the inspection API identifies that renderer and
  suggests reloading; it does not report missing font kerning.
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
- Preserve the [exported difference colors](../generator/CONTRACT.md#glyph-comparison-export). An output mode with no
  changed pixels shows that status on the symbol page.

## Interactive specimens

- The index holds one font dropdown and exactly one visible interactive block: a font size input, one slider per
  non-hidden variable axis with published min/default/max, a text preset select, a multi-line sample textarea, and
  reset. Static fonts render no axis inputs. Hidden family sections are acceptable; the user sees one tester.
- The preset select offers the configured card texts (including reading, numbers, spacing pairs and spacing rhythm) plus
  Custom, which the page selects whenever the textarea no longer matches a preset. Cards come from the generator config
  through the web importer; presets are never hardcoded in page sources. Reset restores the published default size,
  axes, full sample text, and matching preset.
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
- Show **Display scale** beside Zoom using `window.devicePixelRatio`, separately from bitmap zoom. Display four decimal
  places, with the exact ratio and browser/display-scaling explanation in its tooltip. Update on display-ratio changes.
- The optional pixel-accurate display toggle (main page only, off by default until saved, persisted in localStorage)
  shows integer physical screen pixels per font pixel instead: M is the requested zoom times the device-pixel ratio
  rounded to the nearest whole pixel (at least one); the native request width is the available CSS content width floored
  through that mapping, after deducting a reserved end gutter of one CSS pixel plus one device pixel at right/bottom,
  applied before measurement. The canvas backing holds exactly M device pixels per source pixel. Its layout box uses
  integer backing dimensions; a CSS scale of 1/DPR makes the visible extent backing/DPR without fractional paint-size
  snapping. The viewport reserves that visible height plus the gutter. Its layout origin first moves inward to a whole
  CSS pixel to accommodate browser canvas-paint snapping, then its transformed origin moves inward to a whole device
  pixel. The two bounded shifts fit within the gutter, keeping overflow hidden without clipping the first row/column.
  Offsets are cleared before each measurement to prevent accumulation; scroll, resize and layout changes realign the
  image. The request keeps the same size, axes, hinting, spacing, and kerning; only bounded width/height change. The
  native height cap is the renderer pixel bound at that width, the 4096 px side limit, and the 16384 px backing limit
  divided by M, with the same overflow message beyond it. Mode, ratio, magnification, and CSS width join the repaint
  key. The normal path above is byte-for-byte unchanged when the toggle is off.
- Missing WASM output or font sources leave a concise unavailable message with disabled controls (including textarea and
  select), never a build error. Font bytes publish to `interactive-fonts/` and must hash-match the manifest source;
  paths stay inside the repository and only cover the renderer's supported font types.
- `just wasm-build` builds the renderer and stages `assets/wasm/`; `just preview-build` runs it before the page.
- Version both scripts and their shared display-scaling helper with one deterministic content hash of those sources plus
  the staged renderer bytes. Static helper imports resolve to the versioned helper URL, and the WASM JavaScript/binary
  URLs share the script version query. Identical rebuilds retain the version; changed bytes invalidate it. Missing
  staged WASM contributes fixed markers and preserves the unavailable state.

## Verification

Check content validation, byte-for-byte copying, presentation, content states, and browser behavior over HTTP, including
beneath a URL prefix. See [README.md](README.md) for commands.

## Interactive spacing

Each family has synchronized range and number inputs for `letter_spacing_px`, from -2 to +4 with zero default. Mono uses
step 1; gray uses step 0.25. Profile changes update the step and show the normalized value. Numerical normalization,
pair floors and word-boundary behavior follow the [shared tracking policy](../generator/README.md#tracking-policy).

The setting persists across renderer/family changes; Reset restores zero. Unavailable rendering disables both controls.
Clearing or partially typing a number retains the last valid value. Static published cards use neutral tracking.

Each family has a Spacing model selector for `auto`, `source`, `fitted` and `projected`, plus an enabled-by-default
Kerning checkbox. Group the spacing offset, model selector and kerning checkbox in a fieldset labeled **Spacing and
kerning**. Model and kerning preferences are global across families; save them in localStorage and restore before the
first render. Synchronize all family controls whenever either preference changes; accept only known model values and
boolean kerning values. Missing/invalid values use `auto` and enabled kerning. Unavailable storage leaves the current
page controls usable. Forward `spacing_model` and `kerning` through the
[WASM controls](../wasm/README.md#render-spec-controls). Preserve these settings across renderer changes. Gray disables
the selector, forwards `auto` and retains the selection for returning to Mono. Reset restores and saves `auto` and
enabled kerning globally, and restores the active family's zero offset. Unavailable rendering disables the controls. A
comparison guide lives in [Spacing models](../../docs/spacing-models.md); numerical behavior belongs to the
[spacing API](../generator/README.md#live-spacing-api).

Show a short visible description of the selected spacing model beneath its controls, linked to the selector through
`aria-describedby`. Update it on selection, preference restoration, font/renderer/profile changes and Reset. Explain the
renderer-dependent default; in Gray, also state that source spacing applies while the selected model is retained for
Mono. Keep the selector's accessible name separate from its description, following
[W3C ARIA1](https://www.w3.org/WAI/WCAG22/Techniques/aria/ARIA1.html).
