# Monochrome spacing and kerning

<!-- cspell:words HarfBuzz -->

Coordinate monochrome spacing and compact-mark dimensions; support assessment with pixel-aligned display and source
kerning inspection.

## Topics

### Pair spacing and kerning

Fitted metrics and integer origins can lose source separation. Preserve signed pair relationships and kerning, including
AV/VA asymmetry, without changing glyph shapes.

[FreeType glyph metrics](https://freetype.org/freetype2/docs/glyphs/glyphs-3.html),
[bearing correction](https://github.com/freetype/freetype/blob/57617782464411201ce7bbc93b086c1b4d7d84a5/src/autofit/afloader.c#L422)
and [kerning guidance](https://freetype.org/freetype2/docs/glyphs/glyphs-4.html) distinguish fitted metrics from source
pair positioning. [Hersch §§5–6](../../references/papers/1993-hersch/paper.md) grounds grid placement and source
relationships. Bearing correction alone can give unequal fitted gaps to similarly spaced source stems.

**Project hypothesis:** reproduce the rounded signed source projected gap with an integer relative origin:

`floor(source advance(left) + source kern + source min x(right) − source max x(left) + 0.5)`

Use true curve extrema and apply kerning once. Common translation preserves the gap; source-declared fixed pitch and
variation-aware equal-advance digit pairs preserve metric relationships. Spaces, empty glyphs and unsupported pairs fall
back to fitted placement.

Projected gaps are the candidate Mono default. Each [spacing policy](../../spacing-models.md) uses its renderer's own
glyphs and metrics; native drawing and wrapping share the
[placement API](../../../tools/generator/README.md#live-spacing-api).

Projected extrema can misrepresent bowls, diagonals and serif overhangs. Pending: separation and rhythm in Roboto 14 px,
weight 400, width 100 Mono `mi/li/ni`, `Pac`, `quo` and `VA` versus `AV`. Weight 536 is an isolated facing-stem gap
witness.

For Roboto 14 px, weight 400, width 100 Mono at zero tracking, projected `AV` advances 19 px and `VA` 18 px on both
candidate and baseline. Both ink spans are 18 px with zero projected blank columns: fitted `A` has a one-pixel left
margin and `V` none. `AV` retains that leading margin; the internal margin of `A` in `VA` is absorbed by pair placement.
The difference persists with kerning disabled. Independent HarfBuzz source measurements confirm that both source gaps
round to zero; native and preview WASM output agree. Classification: the advance difference follows the placement
contract, with no demonstrated calculation error. Perceived diagonal separation remains pending optical assessment;
equal projected gaps do not resolve that question.

The [spacing TODO](../../TODO.md#evaluate-a-contour-based-spacing-model) describes a proposed general-model experiment.

### Tracking and word separation

Fractional tracking changes Mono rounding phase; tightening letters and spaces can compress word boundaries twice.
[OpenType horizontal metrics](https://learn.microsoft.com/en-us/typography/opentype/spec/hmtx) supply source advances
and bearings. Preserve neutral word separation and intentional overlaps.

The adopted user policy uses whole-pixel Mono tracking with at least one blank column for normally separated pairs,
preserving fixed pitch, tabular digits and source zero/negative gaps. Negative tracking preserves neutral ASCII word
gaps; positive tracking widens letters and spaces. These are explicit layout choices, not sourced optical optima.

The [tracking constraints](../../../tools/generator/README.md#tracking-policy) make line-width changes non-additive. A
one-column floor does not establish optical correctness for curved or diagonal pairs; Roboto 14 px, weight 641, width
100 is an isolated spacing witness.

### Compact marks and stem ownership

Shared stem edges and standards can erase a detached mark's extra source width; independent integer rounding can
exaggerate it. Preserve independent dimensions, source-control proportions, inherited placement, tangency and clearance.

[Microsoft dot control values](https://learn.microsoft.com/en-us/typography/truetype/from-typeface-to-font-file)
separate X/Y diameters and stem-to-dot whitespace.
[Google Fonts' dot guidance](https://googlefonts.github.io/how-to-hint-variable-fonts/) grounds clearance and
transferred motion; [Shamir §3](../../references/papers/2003-shamir/paper.md) grounds feature ownership and proportional
interpolation. [FreeType width-management notes](https://freetype.org/autohinting/widths.html) explain how independent
rounding exaggerates nearby widths.
[VTT control-value inheritance](https://github.com/microsoft/VisualTrueType/blob/main/doc/VTT_Control_Program/VTTControlProgram.md)
coordinates related features without prescribing shared dot/stem widths or an automatic cut-in.

**Project hypothesis:** detached, convex, entirely quadratic filled contours own their dimensions and final point
positions. Require curved intervals, non-reversing tangent joins and supporting control cages; exclude nested,
overlapping or touching cages and points owned by diagonal fitting.

Use true extrema at the requested source scale before style/x-height rescaling. X diameter keeps its natural fractional
span; Y diameter rounds to whole pixels, both with a one-pixel floor. Fractional X avoids exaggerating dot width against
gradually fitted stems.

Transfer controls proportionally around the ordinarily hinted center, preserving tangency. Source-separated contours
with overlapping X projection require one pixel of vertical clearance. Conflicts restore ordinary fitting in both axes
and recheck neighboring marks. Exterior marks contribute to bearing/advance deltas; interior marks preserve them.

Applies only to candidate Mono/default-script automatic fitting; ineligible contours use ordinary fitting.

#### Pending mark findings

Compared with 001.02; Mono, weight 400, Roboto width 100, Literata optical size equal to pixel size:

| Scope                                                                   | Feature relationship and inspection                                                                       |
| ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Roboto 14, `i`                                                          | Unchanged shape despite independent diameter. Inspect dot/stem and `i/j` balance with `mi/li/ni` spacing. |
| Roboto 18, `! . : ? i j`                                                | Wider marks: weight and curved proportions.                                                               |
| Literata 14, `i j`                                                      | Wider dots: weight and stem contrast.                                                                     |
| Literata 16, `;`                                                        | Narrower upper mark, unchanged lower tail: shape and contrast.                                            |
| Literata 20, `j`                                                        | Narrower outer dot rows, unchanged body: silhouette, continuity and balance with `i`.                     |
| Source Sans 3 16, `! . : ?`; 18, `. : ; ? i`                            | Wider marks: weight, proportions and dot/stem balance.                                                    |
| Roboto 16/20, `i j`; Literata 16/18, `j`; Source Sans 3 14/16/20, `i j` | Unchanged cropped shapes, possible bearing/origin changes: alignment and spacing rhythm.                  |

Isolated Roboto 14 px, width 100, weights 534–536 and 641 probe dot/stem balance and binary height. Assess optical
centering, binary size/weight steps and aspect-ratio changes from vertical quantization.

### Preview display scaling

Fractional browser composition can make equal native stems appear unequal.
[devicePixelRatio](https://developer.mozilla.org/en-US/docs/Web/API/Window/devicePixelRatio) distinguishes CSS and
physical pixels; [CSS image rendering](https://drafts.csswg.org/css-images-3/#the-image-rendering) permits fractional
resampling.

The optional [display policy](../../../tools/web/CONTRACT.md#interactive-specimens) shows each native pixel as an equal
integer block of physical pixels, aligning canvas origins and extents.
[Chromium paint snapping](https://chromium.googlesource.com/chromium/src/+/main/third_party/blink/renderer/core/paint/html_canvas_painter.cc)
makes alignment necessary beyond backing-resolution changes.

Controlled fractional composition reproduces unequal stems; the user's cause and other compositors are unassessed.

### Source-kerning inspection

Expose authentic source pair adjustments independently of experimental spacing through the
[WASM API](../../../tools/wasm/README.md#kerning-pairs). The
[inspection interface](../../../tools/web/CONTRACT.md#specimens) distinguishes an unavailable API, absent font kerning
and extraction failure; inspection failure does not block glyph rendering.
