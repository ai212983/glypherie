# Monochrome geometry and spacing

<!-- cspell:words HarfBuzz GSUB GPOS ttfautohint unhinted Skia PathOps autofit afloader rekerning SCANCTRL SCANTYPE fpgm maxp VARC thresholded unrepresentable quantizer CGAL Adafruit pdfontconv Tophat -->

Combine native and automatic Mono fitting on independent axes, with each upstream policy retained as a control. Assess
binary continuity, feature balance and reading rhythm with pixel-aligned display and source kerning inspection. The
layout policy is independent of engine choice; fitted outlines need not preserve source coordinates.

## Topics

### Local curved-stroke widths

**Confirmed existing height defect, corrected:** Roboto Flex regular `k`, 16 px, default axes, monochrome with diagonal
fitting enabled. The upper-right source cap is flat below the ascender. Both upstream endpoints are at 9 px, but the
preceding terminal solve raises one to 9.3125 px while the other stays at 9 px. This occurs in both the approved
preceding sequence and the local curve candidate; it is not introduced by the curve-attachment change. The global
control-box cap restriction misses the edge because the left upright extends higher. The
[reference-height model](../../hobby-fitting.md#terminal-reference-height-constraints) now preserves source-horizontal
edges with a shared upstream height throughout the glyph, following Hobby §3.3's horizontal regions and Hersch §§5–6's
separation of grid phase from diagonal width. Width fitting must retain that flat height inside the solve; no pixel or
glyph-specific correction is used. Both delivered cap endpoints now remain at 9 px, matching the independent Python/CGAL
reference. The browser preview confirms that the raised terminal pixel moves down one row while diagonal width
correction remains active.

**Pending assessment, placement and width:** the isolated three-family matrix described below changes 184 outlines and
39 final bitmaps relative to the preceding local-curve candidate, confined to `k x z`. All 2,771 delivered terminal
reference edges retain their upstream heights; there are no increased eight-neighbor ink-component counts. These are
mechanical observations, not optical acceptance. Inspect the changed arm widths, flat-edge placement and joins across
12/14/16/18/20/24 px, weights 300/400/700 and both hint modes in Roboto, Roboto Flex and Source Sans 3, monochrome.
Other glyphs, including the preceding `s` correction, retain their preceding delivery. Eight apparently horizontal edges
in quantized `x`/`y` captures have nonzero slopes in the unrounded source and correctly receive no height constraint.
Evidence and reproducible inputs remain under `out/diagnostics/robotoflex-k-cap-20261022/`.

The [Hobby curved-width model](../../hobby-fitting.md#joint-placement-and-smooth-curve-continuation) measures source
stroke thickness through certified opposing borders, independent of horizontal, vertical or diagonal labels. Whole
straight-to-curve attachment polynomials remain at the preceding fit while interior curve controls can participate in
the source-relative width solve. This replaces the whole-outline exclusion triggered even by tiny vertical terminal
segments. The preserved relationships are source contrast, existing Y alignment and exact attachment geometry; the local
ownership boundary is a project adaptation of Hobby §6 and Hersch §2. Segment length is not an eligibility threshold.

The curve topology certificate omits exact constant lines, which have no directed extent or winding, as in the CGAL
arrangement model. This changes certificate adjacency only: source operators and delivered coordinates are retained,
edges with distinct endpoints remain exact, and source, upstream and candidate still certify independently. A collapsed
upstream terminal therefore cannot hide a real curve contact or force an unrelated interior stroke to abstain.

**Pending assessment, thinning:** Roboto Flex regular at 16 px, all font axes at defaults, monochrome with diagonal
fitting enabled. The middle's three sampled widths change from approximately 1.60 px to 1.30–1.34 px; attachment curves
and all Y coordinates stay fixed. The final bitmap removes two middle pixels. Inspect retained curvature, staircase
continuity and balance against the uprights; this does not establish optical acceptance or full width equalization. At
12 px its delivered `s` remains unchanged; 14/18 px thin locally, while 20 px has both additions and removals and 24 px
adds ink. Those neighboring cases remain pending for shape, placement and retained contrast.

The isolated three-family control matrix covers Roboto, Roboto Flex and Source Sans 3 at 12/14/16/18/20/24 px, weights
300/400/700 and both hint modes. No newly disconnected eight-neighbor ink components are observed. This is a diagnostic
observation, not a continuity proof or acceptance score. Source Sans `h`/`m` in the earlier 12/14 px attachment concerns
retain their preceding bitmaps. Their source-connected attachment polynomials remain fixed; broader optical assessment
of the changed `5 G J S U c s` and mixed-outline cases remains open. The approved baseline, configured publication
matrix and default-off preference retain their existing scope. Retaining Y can limit the achievable correction through
nearly horizontal stroke portions; a joint two-dimensional grid-placement solve is outside this slice.

### Fast-math visual assessment

The [arithmetic experiment](../../hobby-fitting.md#global-fast-math-experiment) changes delivered Mono pixels while
retaining layout in the tested matrix. Classification: confirmed regression in the reviewed appearance. The user reports
that global fast-math negates most diagonal compensation. The separately demonstrated loss of compensated arithmetic
also remains a numerical limitation. At 16 px, weight 400, selective font hints and FreeType Mono, changed Roboto glyphs
are `* 1 2 M S V Y ^ w y`; changed Source Sans glyphs are `# < K S Z k s z`. Inspect their paired shapes and reading
context without interpreting pixel counts as improvement. The review includes both families' existing size/weight,
hint-policy and scanner matrix for broader inspection. Global fast-math is declined. A
[selective solver experiment](../../hobby-fitting.md#selective-solver-arithmetic-experiment) investigates a narrower
arithmetic boundary while preserving strict geometry.

The paired default views show heavier diagonal spans in Roboto `2 M V Y w y` and Source Sans `< Z z`; inspect their
contrast with vertical strokes and continuity through joins. Changes in `* ^ S # K k s` include localized tip, corner or
curve differences, so inspect their retained shape as well as weight. These are visual inspection questions pending user
assessment, not accepted improvements or glyph-specific fitting rules.

### Defined preview palettes

Font previews reference browser-local palette presets, with Monochrome as the default. Presets define 2, 4, 8 or 16
coverage colors. Gray uses the existing upstream Normal automatic fitting and Alpha scan conversion at the selected
output depth; no glyph geometry or layout rule depends on the preset. Coverage indices select the corresponding preset
entry verbatim under the [surface palette contract](../../../tools/wasm/README.md#render-spec-controls). Display
paper/ink tinting is applied to the preset gray codes. This extends the existing quantized coverage representation,
following [scalar quantization](../../references/papers/2006-gallager-quantization/paper.md), rather than introducing a
fitting model. Palette-lab specimens retain their browser mask and nearest-level linear-light quantization; their pixels
are illustrative and need not match the native coverage index quantizer. Mechanical depth and palette membership checks
do not establish optical acceptance. The configured specimen scope and historical renderer roles retain their existing
depths.

### Mono fitting and engine selection

The font-hints-first comparison policy uses registry Skrifa's `Target::Mono` with `Engine::AutoFallback`. The library
chooses the font's interpreter when appropriate and otherwise its automatic hinter. **Automatic Mono** forces
`Engine::Auto(None)` as the second selectable policy. Both consume runtime font bytes in native and WASM rendering. No
font-family, glyph, size or axis exceptions participate in engine selection.

The [upstream engine API](https://docs.rs/skrifa/0.48.0/skrifa/outline/enum.Engine.html) and
[FreeType load-target contract](https://freetype.org/freetype2/docs/reference/ft2-glyph_retrieval.html#ft_load_target_xxx)
supply the foundation. The pinned Skrifa 0.48.0 implementation considers TrueType glyph instructions and font programs;
CFF/CFF2 uses its interpreter. Presence of instructions does not establish their quality for binary output. FreeType
explicitly limits strong small-size monochrome quality to fonts with suitable black-and-white hints. No general Mono
strength or diagonal-balance parameter is exposed by Skrifa.

**Invariant for the upstream comparison policies:** retain whole outlines exactly as the selected upstream hinter
returns them. Both engine policies can feed either the pinned FreeType monochrome scanner or coverage conversion; the
scanner is selected independently. Its captured-outline parity is checked independently; this does not assert
whole-font-renderer equivalence. Capture provenance names the effective policy and resolved engine. Gray retains
upstream Normal automatic fitting. Layout finalizes bitmap metrics from the fitted results (see pair spacing below);
source-coordinate identity is not an optical acceptance criterion.

The previous `vertical_only` strategy combined source X and Smooth Light Y, following
[ttfautohint's Y-only policy](https://freetype.org/ttfautohint/doc/ttfautohint.html#background-and-technical-details).
It avoided the earlier horizontal distortion of A while retaining fractional vertical-stem widths whose binary weight
depends on phase. That custom composition and its topology requirement are removed. `vertical_only` and `vertical-01`
are rejected, not aliases for the new default. Earlier source-X findings below describe that retired policy.

### Pair spacing and kerning

Native diagnostic comparisons select fitting and rasterization independently. Changing only rasterization preserves the
fitted outline, glyph identity, returned metrics and bitmap placement. Changing fitting may legitimately change fitted
metrics; the layout algorithm remains the same. The shared bitmap policy defaults to zero tracking. Explicit extra
tracking uniformly changes advances without minimum-gap corrections, so it remains separate from fitting and scan
conversion. This follows the separation between fitted glyph metrics and pen placement in
[FreeType's metric model](https://freetype.org/freetype2/docs/glyphs/glyphs-3.html). Native diagnostics retain both Mono
scan converters as controls for individual stages. The font preview fixes 1-bit scan conversion to FreeType Mono with
the shared bitmap layout; retired Mono coverage and renderer selections resolve to this current pipeline, including
saved variants. Gray previews also resolve historical settings to the current coverage pipeline. Native historical APIs
retain their original policies. Mono previews follow executed font scan instructions when embedded TrueType fitting
supplies them; otherwise they use smart dropout including short stubs. Font instructions take precedence and may exclude
stubs or disable dropout, as defined by
[SCANCTRL/SCANTYPE](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#scan-conversion-control).
This preview policy also replaces retired manual scan settings in saved variants. Native diagnostic settings remain
independent. Mechanical comparisons establish geometry and layout isolation; they do not establish optical acceptance of
coverage conversion or any combination of stages. The established preview corpus and legacy baseline remain unchanged.

The working pipeline uses one bitmap placement policy for Mono and Gray, shared by the exported strike, native specimens
and the interactive preview. After fitting, each glyph has a bitmap offset, a whole-pixel advance and sparse whole-pixel
pair adjustments; pen positions accumulate in whole pixels. Reference and legacy baseline keep source-linear layout as
independent comparison controls, not as selectable spacing policies.

[FreeType glyph metrics](https://freetype.org/freetype2/docs/glyphs/glyphs-3.html),
[bearing correction](https://github.com/freetype/freetype/blob/57617782464411201ce7bbc93b086c1b4d7d84a5/src/autofit/afloader.c#L422)
and [kerning guidance](https://freetype.org/freetype2/docs/glyphs/glyphs-4.html) distinguish fitted metrics from source
pair positioning. [Hersch §§5–6](../../references/papers/1993-hersch/paper.md) grounds grid placement and source
relationships. [Turner and Lemberg's metric fitting](../../references/papers/2003-turner-lemberg/paper.md) coordinates
advances with fitted edges. Bitmap strikes store dimensions, offsets and advances separately, and BMFont also carries
pair adjustments ([OpenType bitmap metrics](https://learn.microsoft.com/en-us/typography/opentype/spec/ebdt),
[BMFont](https://www.angelcode.com/products/bmfont/doc/file_format.html)); bitmap storage alone does not choose a layout
policy, since [LVGL's format](https://github.com/lvgl/lv_font_conv/blob/master/doc/font_spec.md) supports fractional
advances too, so the integer choice is deliberate.

The advance is the fitter's returned advance when available, otherwise the rounded source advance, with no
glyph-specific fallback. Source-tabular digits retain the common quantized source advance, following FreeType's autofit
loader, which preserves a common rounded advance for equal-width digits and zeroes their bearing deltas; fixed-pitch
fonts use the rounded source advance for every glyph so equal source cells stay equal when hinted advances differ, and
likewise carry no bearing deltas. Source kerning and any available fitted bearing correction are resolved once into an
integer pair adjustment. Captures that supply no bearing deltas contribute no correction, and none is invented.
Candidate automatic-Mono captures now record the fitter's residuals (see
[runtime adoption](#compensated-spacing-runtime-adoption-open-iteration)); independent reference, native, unhinted, Gray
and non-Mono captures still record none. Quantization is to the nearest whole pixel with ties away from zero, so a
negated adjustment quantizes to its negation. Retaining HarfRust's source pair extraction and choosing its pixel
quantization are project adaptations of FreeType's integer bearing correction and grid-fitted kerning, not a claim of
complete FreeType layout parity. The invariant is that the same bitmap pair has the same relative placement irrespective
of preceding text; this does not impose equal white gaps on different pairs, and no optical rekerning or projected-gap
shaping is performed. Signed adjustments and intentional overhang are preserved, with no blank-column floor at neutral
tracking.

Integer strike metrics change line widths and wrapping: eighteen 8 px digit advances total 144 px, compared with
142.3125 px under the former 26.6 source metrics. Subpixel kerning distinctions can disappear after quantization.
Assessment across straight, curved and diagonal pairs, font sizes, axes and both Mono engine policies, plus optical
assessment of the combined policy, remains pending; the revision stays open and no optical acceptance is claimed.

Adapter correction: the live candidate Gray preview previously drew production-target Gray while specimens drew the
candidate's upstream Normal capture. The preview now uses the existing candidate capture so exported, preview and
specimen Gray bitmap metrics agree. Existing fitter and raster implementations are unchanged, but candidate Gray bitmaps
in the live preview are therefore not claimed identical to the old live Gray adapter. The host observed stable prefix
crops in Gray after this change; broader Gray optical assessment remains pending.

The earlier projected-gap experiment reproduced a rounded signed source projected gap at an integer relative origin.
That placement algorithm is removed; its general source/ink geometry remains in the historical role APIs' tracking
guard. On the approved baseline at Roboto 14 px, weight 400, width 100 Mono, projected `AV` had advanced 19 px and `VA`
18 px with zero projected blank columns; independent HarfBuzz source measurements confirmed both source gaps round to
zero. Classification: that advance difference followed the former placement contract, with no demonstrated calculation
error. Perceived diagonal separation remains pending optical assessment.

#### Fitting-bearing compensation investigation

Candidate automatic-Mono captures record the snapshot fitter's left/right bearing-rounding residuals
(`side_bearing_deltas_26_6`); selective fitting carries them with the owner of X metrics, and layout applies source
kerning plus compensation exactly once into whole-pixel pair adjustments. FreeTypeMono and Coverage captures of the same
fitting carry identical residuals: scanner choice changes delivered pixels only, never fitting or layout. Independent
reference, native, unhinted, Gray and non-Mono captures record none, and none is invented.

[FreeType's integer-positioning example](https://freetype.org/freetype2/docs/reference/ft2-glyph_retrieval.html#ft_glyphslotrec)
compares the preceding right residual with the current left residual and adjusts placement by one pixel at its
documented half-pixel boundaries. The
[pinned automatic loader](https://github.com/freetype/freetype/blob/57617782464411201ce7bbc93b086c1b4d7d84a5/src/autofit/afloader.c#L462)
defines each residual as the rounded metric point minus its pre-rounding value, after small-bearing adjustments.
Fixed-pitch glyphs and source-tabular digits have zero residuals.

Skrifa 0.48.0 follows this metric-point fitting sequence, but
[`AdjustedMetrics`](https://docs.rs/skrifa/0.48.0/skrifa/outline/struct.AdjustedMetrics.html) exposes only overlap
state, an optional adjusted left bearing and a rounded advance; the registry automatic path discards the pre-rounding
values, and the integrated snapshot retains them instead. Finished outlines, bitmap bounds and rounded advances cannot
uniquely recover that rounding error. FreeType's embedded interpreter does not provide these automatic-hinting residuals
either.

Independent FreeType 2.14.3 controls demonstrate nonzero automatic-fitting residuals in the sampled fonts and sizes;
captures remain under `out/diagnostics/fitting-compensation-20261026/`. Skrifa scales the space advance through the
rounded-phantom fallback on the empty outline, while FreeType 2.14.3 skips phantom rounding for outline-less glyphs (`if
( slot->outline.n_points == 0 ) goto Hint_Metrics;`, `afloader.c:403-405`); advances agree with identical glyph IDs,
with no integer placement effect at the approved setting. Literata reports 27 unsupported ASCII kern pairs under the
maintained strict shaping error, so its kerning-on tables stay unavailable while kerning-off stays fully supported.
Earlier probe, space and matrix packets stay retained under `out/diagnostics/fitting-compensation-{probe,space,matrix}/`
without maintained regeneration.

#### Compensated-spacing runtime adoption (open iteration)

The compensated-spacing integration is adopted into the maintained runtime as described above. Human approval scope is
exactly the approved proof: Roboto 16 px, wght 400, wdth 100, forced automatic Mono with the FreeTypeMono scanner,
diagonal fitting on, source kerning on, zero tracking. The broader multi-font and multi-size mechanical checks are not
optical acceptance; optical assessment beyond the approved proof remains open, and the iteration stays open.

#### Browser comparison for optical assessment (question, not a verdict)

The isolated review packet under `out/diagnostics/fitting-compensation-review/` freezes the matrix cases with three arms
(original, recovered Skrifa residuals, FreeType-vector substitution on identical glyphs, advances and bitmaps). The
[primary proof-kerning-on packet](../../../out/diagnostics/fitting-compensation-review/www/proof-kerning-on/index.html)
holds the approved-setting sheet, following the ArrowType spacing control strings and proofing corpora (not its UI) at
revision `bfb554a31fdcc7b5c45bdeb60f75b1a2df041c2e`; see the
[rework proposal](../../../out/diagnostics/fitting-compensation-review/rework-proposal.md). Older proof-v1 and
proof-diagonals-on packets stay frozen as diagnostics. In the primary proof, lines identical across arms stay hidden
with context kept; the page is view-only with feedback in chat and no persisted assessments. Decision boundary: canvas
agreement with the packet is a mechanical gate, and no canvas comparison establishes optical improvement or regression.

#### Proposed optical pair-spacing experiment

**Project hypothesis; not adopted:** preserving a source pair's estimated optical separation through fitting may retain
reading rhythm better than rounding source kerning alone. This experiment changes pair placement while retaining fitted
outlines, rasters, bitmap offsets and finalized glyph advances. It is separate from metric-residual recovery.

[FontForge's separation estimator](https://fontforge.org/docs/ui/dialogs/autowidth.html) compares facing outline
envelopes across their shared vertical extent, with bounding boxes adjacent. It averages their separations with weights
proportional to `1 / (separation + em_size / 50)^2`, excluding empty bands; its default band height is `em_size / 100`.
These are upstream heuristics. Pin the implementation and license, retain its parameters without glyph-specific tuning,
and verify estimator parity before assessing rendered output.

Use selected-glyph source and final fitted outlines at the exact axes, scaled to pixels in a common baseline coordinate
system. Let `S` be the envelope estimate at adjacent bounding boxes, `d` the origin separation, `xmax_left` the left
glyph's maximum X and `xmin_right` the right glyph's minimum X. FontForge's linear-translation assumption gives `D(d) =
d + xmin_right - xmax_left + S`. Calculate envelope weights once at adjacent boxes; recomputing them at trial placements
would lose that translation property.

Set `d_source = source_advance_left + source_pair_adjustment`, with the adjustment zero when source kerning is disabled.
Solve `D_fitted(d_required) = D_source(d_source)`, then replace the eligible pair's adjustment with `round(d_required -
finalized_advance_left)`. Apply the existing signed whole-pixel rounding to the adjustment once; rounding the absolute
origin step would change signed half-tie behavior. Do not add source kerning or bearing compensation again. Apply user
tracking through the existing advance operation afterward. Preserving source separation using fitted outlines is a
project adaptation: FontForge's automatic kerning normally targets a chosen common separation. Uniformly re-spacing the
source design is outside this experiment.

Keep current placement for empty glyphs, spaces, pairs without shared valid bands, fixed-pitch fonts and source-tabular
digit pairs; record abstention reasons. Retain unsupported-shaping errors and signed source overlaps. Non-finite
geometry fails explicitly. Classify new intersections or separation concerns under the
[evaluation rules](../../evaluation.md), without adding collision clamps or minimum blank columns.

First compare rectangles, straight and curved envelopes, empty bands and unchanged source geometry against the pinned
estimator. Check translation and scaling before expanding to a font sweep or browser integration; a failed invariant
stops expansion.

The isolated matrix should cover Roboto, Roboto Flex, Source Sans 3 and Literata at 12/14/16/18/20/24 px, weights
300/400/700 and default remaining axes, plus independent optical-size endpoints where present. Include fixed-pitch and
tabular controls, punctuation, supported accented scalars, straight/curved/diagonal pairs, repeated letters and words,
and alternate prefixes. Compare current placement with kerning off/on, recovered-residual placement when available, and
source-relative optical placement. Keep pure automatic, font-hints-auto and diagonal-overlay Mono cases separate. Gray
uses its supported automatic coverage pipeline and fitted geometry.

Retain font and glyph identities, axes, size, pipeline settings, source/fitted envelopes, reference revision, fractional
targets, integer pair tables and abstentions. The experiment may reuse maintained capture and raster APIs; maintained
components must not depend on it. Gates cover estimator parity, translation and scale, unchanged glyph images and
advances, single application of pair adjustments, fixed cells, tracking separation, prefix independence and shared
measurement/wrapping inputs. Quantization and size-transition differences remain evidence, not an acceptance score.

Review source/current/experimental placement through an isolated browser comparison at native and enlarged sizes. Assess
pair balance, punctuation and word boundaries across sizes and axes, keeping default preview behavior, publication scope
and the separate baseline unchanged. Adoption requires optical assessment and one finalized metric table shared by
native preview, WASM, wrapping and export; adapters must reject unrepresentable adjustments explicitly.

#### Fractional source advances and bitmap placement

Roboto Flex at 14 px, default axes, Automatic Mono fitting and zero tracking demonstrates prefix-dependent separation
under the former source layout. Its digits have equal source advances of 506/64 = 7.90625 px and no source digit-pair
adjustments. Source spacing accumulated these fractional advances before rounding each bitmap origin. The last `98` in
`909192939495969798` had origins 127 and 134 px, whereas `09192939495969798` had origins 119 and 127 px. Fitted `9`
occupies columns 1–7 relative to its origin and `8` occupies columns 1–6. Consequently the longer string's pair touched
on several rows; the shorter string retained one blank column. Enabling kerning changed neither result. Native and
served WASM captures agreed.

Classification: confirmed loss of separation and digit-cell consistency under source placement, following the former
layout contract rather than a kerning extraction error. The digit bitmaps did not change with the prefix. Equal source
advances preserve average source width but do not guarantee equal delivered integer steps. The selected hinter returns 8
px advances for every digit; independent FreeType automatic Mono capture also returns 8 px.

Under the adopted bitmap policy, both strings place the final `9`–`8` pair at an 8 px step with the same relative
placement in Mono and Gray and under both Mono engine policies, and the pair does not touch. Exported strike, preview
and specimen placements agree on these integer metrics (mechanical and geometric evidence). Broader optical acceptance
of separation and rhythm across pairs, sizes and axes remains pending.

### Tracking and word separation

[FreeType glyph metrics](https://freetype.org/freetype2/docs/glyphs/glyphs-3.html) and
[BMFont's bitmap format](https://www.angelcode.com/products/bmfont/doc/file_format.html) separate glyph images, advances
and pair adjustments. Hersch's grid-placement model (§5) explains why fractional displacement can change a rasterized
shape's phase. Uniform whole-pixel tracking preserves the glyph bitmaps and their relative pixel-grid phase.

For the explicit pipeline, extra tracking is a signed whole-pixel addition to each finalized advance, including spaces
and the final glyph advance. It applies equally to Mono and Gray; zero is identity. Negative tracking can reduce word
gaps and overlap glyphs. No clearance floor or word-gap refund changes the requested amount. This replaces the protected
spacing behavior for current previews while historical role APIs retain their earlier policy.

Tracked export bakes the same offset into advances and retains the finalized source-kerning and fitted-bearing pair
adjustments exactly once. Signed advances represent this operation without extra pair corrections, including zero or
negative resulting advances. Any future adapter with narrower metric restrictions must explicitly handle or reject
unrepresentable values while preserving preview/export parity. This does not introduce optical rekerning or a guarantee
that a selected tracking value is visually appropriate. Diagnostic comparisons and static publication retain zero
tracking unless explicitly requested.

### Compact marks and stem ownership

Shared stem edges and standards can erase a detached mark's extra source width; independent integer rounding can
exaggerate it.
[Microsoft dot control values](https://learn.microsoft.com/en-us/typography/truetype/from-typeface-to-font-file)
separate X/Y diameters and stem-to-dot whitespace.
[Google Fonts' dot guidance](https://googlefonts.github.io/how-to-hint-variable-fonts/) grounds clearance and
transferred motion; [Shamir §3](../../references/papers/2003-shamir/paper.md) grounds feature ownership and proportional
interpolation. [FreeType width-management notes](https://freetype.org/autohinting/widths.html) explain how independent
rounding exaggerates nearby widths.

The earlier candidate experiment assigned independent dimensions to detached convex quadratic contours, transferred
controls around their hinted centre, and enforced vertical clearance. It changed dot widths and bearings while retaining
the surrounding horizontal fitter. Vertical-only fitting supersedes that experiment: marks now retain source X and
receive upstream Y fitting, without a separate compact-mark owner or one-pixel diameter floor.

Dot/stem balance, tangency, clearance and binary size transitions remain pending assessment under the new policy.
Include `! . : ; ? i j` across the agreed preview, and compare marks with their stems and neighboring letters rather
than judging isolated widths. No prior mark assessment establishes acceptance of the new geometry.

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
[WASM API](../../../tools/wasm/README.md#kerning-pairs).

### Coordinate-selected scalar glyphs

Variable fonts can select different outlines for the same Unicode scalar. OpenType
[required variation alternates](https://learn.microsoft.com/en-us/typography/opentype/spec/features_pt#tag-rvrn) and
[GSUB feature variations](https://learn.microsoft.com/en-us/typography/opentype/spec/gsub#featurevariations-table)
select single substitutions from the requested variation coordinates. Resolve each isolated scalar before drawing; keep
its Unicode identity while outlines, source geometry, advances and pair expectations follow the selected glyph.

The shaper's [built-in metric callback](https://docs.rs/harfrust/0.14.0/harfrust/trait.FontFuncs.html) supplies the
advance before GPOS positioning. Compare the final shaped advance with that value in the same integer domain to detect
standalone positioning, while retaining the renderer's fractional source metrics and rounding policy. This avoids
confusing integer variation-delta rounding with positioning.

The pinned Roboto Flex dollar at 14 px, optical size 14, width 100, other axes at defaults selects nominal glyph 7 at
weight 400 and glyph 602 at weight 700, for slant 0 and -10. Classification: the previous rejection was a confirmed
capability limitation; selecting the required outline resolves it across rendering and kerning inspection. The selected
outline matches independent source capture. This establishes glyph selection and metric consistency, not optical
acceptance. Pair-context substitutions, glyph count/order changes and unrepresentable positioning remain unsupported
under the [generator contract](../../../tools/generator/README.md#supported-input-and-output).

### Symmetry and grid placement

The investigation at Roboto 14 px, weight 400, width 100, Mono threshold 128 distinguished geometric distortion from
placement relative to the grid. The approved baseline and the previous candidate had identical fitted outlines and
pixels; native and browser WASM pixels agreed.

- **A: confirmed geometric imbalance in the previous model.** The source apex is about 0.007 px left of the midpoint
  between the outer feet; upstream Mono automatic fitting increases that offset to 0.383 px, and the project fitter to
  0.516 px. The fitted perpendicular leg widths are about 0.98 and 1.22 px despite nearly equal source widths. Ordinary
  X preparation changes the two slopes differently, then independent leg-width rounding amplifies the difference.
  Dropout adds one pixel at the right foot.
- **o: pending placement assessment.** The previous model places the bowl centre at 3.90625 px. A diagnostic translation
  to 4 px restores binary symmetry at this coordinate without changing widths; dropout adds no pixels here.
- **v: pending grid-phase assessment.** Source, upstream Mono and project outlines share an outer top-span centre of
  3.375 px. A diagnostic translation of 0.125 px restores binary symmetry at this coordinate. Project dropout also adds
  a pixel at the upper-left terminal.

[Hersch's grid-placement discussion](../../references/papers/1993-hersch/paper.md) explains why nearly symmetric
outlines can rasterize asymmetrically at different positions relative to the grid.
[Shamir's feature constraints and conflict resolution](../../references/papers/2003-shamir/paper.md) support coordinated
feature ownership. They do not supply an automatic recipe for identifying and coupling A legs.

Replacing prepared slopes with source slopes alone left an A leg unapplied at 14–16 px within the existing movement
bound. A source-referenced endpoint experiment restored the weight-400 A relationship across 13–20 px but accepted fewer
diagonal constraints in twelve cases across a broader matrix. Coupling related legs would require shared constraints,
anchor priorities and a validated fallback; merely grouping independent equations does not preserve their relationship.
These limits motivate the simpler vertical-only policy rather than further extending the custom horizontal solve.

The candidate preserves source X instead of forcing mirror symmetry or centering individual glyphs. Existing source
phase in o/v remains a separate optical question. Inspect native-size weight, stepping, terminal balance and spacing;
neither a symmetric bitmap nor geometric agreement alone establishes acceptance.

#### Vertical-only candidate findings

Roboto 14 px, weight 400, width 100, Mono threshold 128 retains the source A's outer-apex/feet offset at about -0.008 px
in the capture's fixed-point domain, compared with -0.516 px on the approved baseline. The source offset also survives
at 13/15/16/18/20 px. **Classification: confirmed correction of the excess outer-apex displacement.** This measurement
does not establish complete outline or pixel symmetry, or optical acceptance of the legs, crossbar and joins.

At the same 14 px coordinate, o retains its source outer centre at about 3.992 px and its delivered pixels are
mirror-symmetric. v retains its 3.375 px source centre and remains asymmetric; dropout contributes one pixel at its
upper-right terminal. **Classification: pending optical assessment** of bowl weight and diagonal/terminal balance. The
remaining v phase follows source placement, so horizontal centering would be a separate model change. The remaining A
pixel asymmetry is investigated below. Do not tune origins or thresholds to force these witnesses to mirror.

#### Native-coverage A asymmetry: overlap coverage and phase

Direct native-resolution Zeno coverage of Roboto A at 14 px, weight 400, width 100, Mono threshold 128 produces one
unequal mirrored pixel pair in the third row from the bottom, below the crossbar. Native and browser output agree under
that raster policy. Candidate X coordinates exactly match the source draw, corresponding left/right Y coordinates agree,
and dropout contributes no pixels. Preserving the apex relationship alone therefore does not resolve the coverage
artifact; the 4× candidate raster below addresses it without changing the outline.

The two legs and crossbar are three overlapping filled contours with the same winding direction. The retained Zeno Alpha
raster accumulates signed areas before taking an absolute value and clamping coverage; overlaps inside a pixel can be
counted more than once. At the unequal pair, coverage is 133 on the left and 96 on the right. Threshold 128 turns on
only the left pixel.

Independent polygon clipping with inclusion–exclusion gives filled-union coverage of about 113.88 and 81.07 on the same
0–255 scale; separate scan line integration agrees. Both are below threshold. Removing only internal overlapping edges
preserves the filled shape and its placement, yet rendering that equivalent union through the same Zeno, threshold and
dropout produces 113 and 81. Only the extra left pixel disappears, and the 14 px bitmap becomes mirror-symmetric.
**Classification: confirmed overlap-related coverage artifact in the retained raster pipeline.** This is a raster
limitation, with no demonstrated source-X ownership failure or browser-display cause. It was not introduced by the
vertical-only fitting change; that change retained the raster policy for assessment.

Grid phase is also real: the source outer centre is 4.578125 px, while the bitmap's mirror axis is 4.5 px. A fixed
-0.078125 px diagnostic translation also removes the unequal pixel, but changes placement and conceals the overlap
artifact. Even the filled-union coverage remains unequal; symmetry of the binary result here does not establish exact
source symmetry. The source has small point asymmetries, and the Y fit changes which coverage row straddles the
threshold. Outer-apex alignment, contour symmetry, coverage symmetry and binary symmetry are separate relationships.

This result is scoped to the reported 14 px coordinate. Equivalent-union diagnostics at 13/15/16/18/20 px still yield
asymmetric bitmaps; overlap handling alone is not a general symmetry policy. Optical weight, joins and phase across
sizes remain pending assessment. FreeType's
[overlap flag guidance](https://freetype.org/freetype2/docs/reference/ft2-outline_processing.html#ft_outline_xxx) uses
oversampling to mitigate overlapping-contour artifacts. These findings motivate the general coverage experiment below;
they do not supply a horizontal placement rule or establish optical acceptance across curved contours, counters, winding
and dropout interactions.

#### Overlap-aware raster investigation

FreeType's
[overlap raster](https://github.com/freetype/freetype/blob/57617782464411201ce7bbc93b086c1b4d7d84a5/src/smooth/ftsmooth.c#L317-L436)
scales the already fitted outline by four in each direction, renders antialiased spans, and accumulates reduced coverage
into native pixels. It does not fit at a larger size. Each high-resolution coverage contribution is rounded after
division by 16, and the accumulated result saturates at 255. This is the established mitigation to assess first; the
[overlap flag documentation](https://freetype.org/freetype2/docs/reference/ft2-outline_processing.html#ft_outline_xxx)
does not promise exact filled-area coverage.

**Candidate experiment:** preserve fitted commands, source X, native placement and metrics; change only candidate Mono
coverage. Reduce samples on the global integer pixel grid, threshold once at native resolution, then apply the existing
dropout rules once to the original fitted outline. An isolated Zeno prototype compares FreeType's per-contribution
rounding with averaging all 16 samples before one final rounding. The latter is a project adaptation, not FreeType pixel
parity. The candidate adopts FreeType-style per-contribution rounding; one-round results below remain diagnostic
comparisons. Neither approach changes the fitting size or centers a glyph.

For the reported Roboto A at 14 px, weight 400, width 100, threshold 128, the unequal pair has coverage 115/86 with
FreeType-style reduction and 115/85 with one final rounding, versus the current 133/96. Both remove the extra left pixel
without dropout intervention. A diagnostic 16× reduction gives 114/81, approaching the independently computed
filled-union coverage of 113.88/81.07. Sixteen is a convergence diagnostic, not an adopted setting or an exact
reference. **Classification: demonstrated mitigation of the reported coverage artifact; optical assessment pending.**

The corpus diagnostic holds each fitted outline fixed across five configured families, sizes 14/16/18/20 and 95
characters: 1,900 glyphs, weight 400, Roboto width 100, optical size equal to requested size where applicable, and
Roboto Flex slant zero. One-round 4× reduction changes 547 glyphs, adding 593 pixels and removing 399; FreeType-style
reduction changes 574, adding 664 and removing 359. Native bitmap bounds agree throughout. Neither produces increased
eight-connected ink-component counts or changed four-connected enclosed-background counts in this scope. These counts do
not establish retained joins, counters or optical quality. Both decrease component counts in two cases:

- Source Sans 3 `!`, 14 px, weight 400, Mono: FreeType-style reduction raises coverage at the top of the dot from 116 to
  128, connecting dot and body in the binary image, although the fitted contours retain about 0.578 px of vertical
  separation. Another body cell rises from 127 to 128. **Pending assessment:** detached-mark clearance and dot/body
  balance.
- Source Sans 3 `[`, 16 px, weight 400, Mono: 24 added pixels change three components to one as half-covered cells rise
  from 127 to 128. **Pending assessment:** continuity and stroke weight; the count alone cannot decide whether this
  restores the bracket or makes it too heavy.

Synthetic straight, quadratic, cubic, crossing and hole paths expose important limits. Duplicating a same-winding
contour preserves its nonzero filled set but still changes sampled coverage. For an identical rectangle, one-round 4×
reduction has summed coverage 734 for a single contour and 859 for its duplicate, with three versus four binary pixels;
exact filled area corresponds to about 734.4. At 16× the duplicate still gives 765. **Classification: confirmed residual
coverage limitation.** Finite oversampling mitigates double counting rather than removing it.

Opposite-winding disjoint strips sharing a native pixel also expose cancellation in the current signed-area raster,
despite having no geometric intersection. Their raw coverage vanishes; dropout restores two pixels and conceals the
error in the final Mono image. The 4× prototype separates these strips and recovers coverage before dropout. Conversely,
even a single non-overlapping rectangle changes quantization: summed coverage is 736 currently, 734 with one final
rounding, and 742 with FreeType-style reduction. Exact unchanged pixels on non-overlapping paths are therefore not an
invariant of this proposal. The rounding choice needs general coverage and optical assessment, not selection for the A
witness. The fitted overlap flag is false for that A and both Source Sans 3 cases; relying solely on that flag would
miss relevant behavior. The diagnostic applies reduction uniformly, without claiming every changed glyph contains
overlaps.

An alternative is filled-path normalization before rasterization.
[FontTools overlap removal](https://fonttools.readthedocs.io/en/latest/ttLib/removeOverlaps.html) uses Skia PathOps;
[Skia's Simplify contract](https://github.com/google/skia/blob/main/include/pathops/SkPathOps.h#L52-L65) produces
non-overlapping contours describing the same area and can reduce curve order. A project adaptation would normalize only
the temporary fitted raster path while preserving source commands and metrics, including the intended winding of holes
and disconnected filled components. It would need numerical-failure handling and native/WASM dependency assessment. The
[FontTools implementation](https://github.com/fonttools/fonttools/blob/main/Lib/fontTools/ttLib/removeOverlaps.py) can
alter hinting and bearings when rewriting a font, making that operation unsuitable here. Removing intersections alone
would also be insufficient to address opposite-winding components sharing a pixel.

**Candidate policy:** use the bounded 4× FreeType-style mitigation, retaining proper filled-path normalization as the
alternative when contour-representation invariance is required. FreeType streams into native storage; the project adapts
this storage principle through integer-aligned tiles with at most 1 MiB of high-resolution coverage storage per tile.
Each tile receives the full fitted path so clipping retains winding contributions from outside the tile. Native coverage
and delivered pixels remain native-sized. Validate original coordinates and native bounds before scaling; originally
valid large or translated paths must not fail merely because the temporary raster has greater resolution. The original
dropout work bound remains in effect.

Broader axis behavior, worst-case native/WASM cost and optical assessment of mixed thickening/thinning, mark clearance,
joins and counters remain pending. The approved baseline, independent reference and Gray retain their existing raster
policies. This experiment does not establish contour-representation invariance, general bitmap symmetry or acceptance of
the combined fitting and raster model.

#### Terminal stubs and dropout

Candidate Mono excludes terminal stubs from dropout rescue, following
[TrueType SCANTYPE mode 5, rule 6](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#scantype).
The pinned
[FreeType recognizer](https://github.com/freetype/freetype/blob/57617782464411201ce7bbc93b086c1b4d7d84a5/src/raster/ftraster.c#L2206-L2242)
relates a stub to neighboring contour profiles ending before the next scan line. The project adaptation follows the
actual curve arc joining the filled span's borders: a cap that closes on one side before the next pixel-center scan line
is excluded. Curve extrema determine continuation; coverage, glyph identity and ink connectivity do not. The
coverage-thresholded raster remains a project adaptation rather than TrueType center-fill conversion, and does not adopt
FreeType's overshoot exceptions. Ordinary threshold ink, fitted geometry, placement and metrics are preserved; legacy
baseline and independent reference retain their existing policies.

Roboto Flex regular `x` at the web defaults (16 px, weight 400, width 100, optical size 14, slant zero, Mono) has
identical source and interpreter-fitted outlines, with both upper terminals at 8.21875 px. A vertical scan through the
left cap previously promoted coverage 34/255 to full ink, adding one row to that arm alone. **Classification: confirmed
terminal-shape defect from stub rescue.** The candidate removes that one added pixel and retains the source terminal
height relationship. At optical size 14, the same left-only top-row additions disappear at 14/18/20 px too.

**Pending optical assessment:** Literata `E` at 14/16/18 px and `@` at 14 px, weight 400 and optical size equal to pixel
size, Mono. Terminal removal opens small enclosed white regions at the right serifs of `E` and the right shoulder of
`@`; the principal stroke components remain connected. Source `E` has one contour and `@` has two; the changed regions
are terminal closures rather than missing stroke components. Inspect serif length and attachment, shoulder balance and
counter openness. Broader terminal weight, joins and mark clearance remain pending. Ordinary coverage can erase a tiny
detached contour when all of its potential rescues are stubs; no special mark exemption is introduced. Very complex
contours can also exhaust the bounded dropout work and fail generation rather than bypass stub exclusion. No
glyph-specific correction is permitted.

#### Binary stem weight and source phase

Roboto 14 px, weight 400, width 100, Mono threshold 128 has a two-column middle stem in `m`, right stem in `u` and stem
in `t`, against the normal one-column stems around them. The user identifies the thick stems as the outliers. In `m`,
all three straight outline stems are exactly 1.265625 px wide, yet the delivered pattern is one/two/one columns. The
approved baseline and upstream Mono reference give one-column stems in these witnesses. **Classification: confirmed
binary stem-weight imbalance in the combined vertical-only fitting and binary coverage conversion.** This is not
evidence that the neighboring one-column stems need thickening.

Source and candidate X coordinates match bitwise. Away from shoulders, bowls and crossbars, each affected stem is a
single filled span with these horizontal edges and current coverage values on the 0–255 scale:

| Witness           | Outline X edges      | Width in px | Adjacent column coverage | Delivered columns |
| ----------------- | -------------------- | ----------- | ------------------------ | ----------------- |
| `m` middle, Y 2–3 | 5.5 to 6.765625      | 1.265625    | 128 / 196                | 2                 |
| `u` right, Y 5–6  | 5.484375 to 6.765625 | 1.28125     | 132 / 196                | 2                 |
| `t` stem, Y 5–6   | 1.421875 to 2.6875   | 1.265625    | 148 / 176                | 2                 |

These are outline Y-up intervals; coverage rows are captured in bitmap Y-down coordinates. Dropout contributes no pixels
to any of the three glyphs. Native and browser WASM bitmaps agree. Overlapping contours do not explain these straight
span measurements. The root relationship is grid phase: source X places substantial coverage in two neighboring columns,
and the threshold independently turns both black. The same geometric width can occupy one full column plus weak edge
columns elsewhere. [Hersch §5](../../references/papers/1993-hersch/paper.md#5-basic-grid-constraints) explains this
dependence of discrete bar width on phase; §6 describes preserving related widths through shared constraints.

The 4× raster newly extends the doubled middle stem of `m` downward by four pixels, at bitmap X 5, Y -4 through -1. Its
left edge covers exactly half of that column: analytic coverage is 127.5. Native Zeno yields 127, while both
FreeType-style 4× reduction and one final rounded average yield 128. The latter has eight zero and eight fully covered
high-resolution samples in the witness cell. Thus the per-contribution rounding bias is not necessary for this change;
switching to one final average would retain the two-column stem.

The full `u` and `t` bitmaps are unchanged by 4× reduction. Their corresponding native coverage pairs are already
131/195 and 147/175, both above threshold. These are existing weight-balance defects under vertical-only fitting; the
extra four `m` pixels are a regression associated with the raster change. Removing overlaps or correcting the exact
half-coverage tie would not resolve all three.

This is the specific black-and-white limitation described by
[ttfautohint's smooth-hinting guidance](https://freetype.org/ttfautohint/doc/ttfautohint.html#smooth-hinting):
fractional stem widths that work in antialiased output can alternate between one and two black pixels. Preserving source
X alone does not preserve binary stem weight. A remedy needs a general Mono stem-weight policy assessed against the
normal one-column strokes, joins and the source-related A geometry; per-glyph phase shifts, threshold tuning and
thickening the normal stems are not justified by this finding. No fitting or raster behavior is changed by this
investigation.

##### Main-page source-stem calibration

The [main-page sample selection](../../../tools/web/scripts/landing-samples/main-page.json) targets one native pixel for
principal stems through one global weight coordinate per family and size. The project adaptation measures upper body
sections in `H`, `I` and `l`, bounding the widest reference section in the serialized static source font by one pixel.
All converters receive that same instance; source weight relationships, serif contrast and native converter behavior
remain intact. This controls specimen inputs rather than changing fitting or scan conversion. It does not claim that
every serif, join, diagonal or curved stroke is one pixel wide.

Glypherie delivers one-pixel horizontal body runs in the three reference characters for every selected family and size,
measured in each strike's fitted cap-height frame. The following Mono converter differences remain **pending
assessment**, with native output retained:

| Family        | Size | Axes                      | Converter                    | Witness                         |
| ------------- | ---- | ------------------------- | ---------------------------- | ------------------------------- |
| Roboto        | 12   | `wght=367.07`, `wdth=100` | pdfontconv, Tophat, Adafruit | `H` has one- and two-pixel runs |
| Roboto Italic | 12   | `wght=372.63`, `wdth=100` | pdfontconv, Tophat           | `H` has one- and two-pixel runs |
| Roboto Italic | 20   | `wght=253.69`, `wdth=100` | pdfontconv, Tophat, LVGL     | `H` has one- and two-pixel runs |
| Literata      | 16   | `wght=252.22`, `opsz=16`  | pdfontconv, Tophat           | `H` and `I` have two-pixel runs |

The inspection question is how native fitting and grid placement affect principal stroke weight and continuity against
the shared source. These measurements establish a width difference, not damaged legibility or an optical quality
ranking. No glyph pixels, individual-glyph settings or thresholds are adjusted to remove the differences.

#### Coupled width geometry: research direction

[Hobby's fitting model](../../references/papers/1993-hobby/README.md) addresses the broader orientation problem by
measuring paired boundary displacement along source-derived normals, coupling relative width errors, and including
white-space features. Integer offsets handle diagonal strokes without limiting the model to vertical stems. Related
source widths can change together without erasing intended thick/thin contrast.

The [focused equation audit](../../references/papers/1993-hobby/audit.md) identifies report-version discrepancies before
implementation. An isolated [geometric prototype](../../../experiments/hobby_fitting/README.md) exercises supplied
straight, diagonal, curved and counter relationships. Its sampled curve-strain extension is a project adaptation of the
source's shape measures. Normal displacement alone admits excessive control movement; the shape terms address that
deficiency in the synthetic example. **Pending assessment:** feature recognition, integer target selection, movement
ownership, joins, curve validity and counter preservation across source fonts. The center-fill premise also requires
separate validation against our coverage reduction and binary conversion. These research results do not establish a
remedy for the delivered Roboto glyphs or optical acceptance of a new fitting policy.

#### Upstream Mono assessment

The default **Font hints first** and the **Automatic Mono** control share one replaceable whole-outline boundary. The
[generator API](../../../tools/generator/README.md#working-candidate-fitting) owns the policy/engine contract and the
[comparison tool](../../../experiments/stem_policy_comparison/README.md) owns reproduction commands. The selected font,
size and axis publication scope remains unchanged.

**Confirmed existing weight imbalance remains:** at Roboto 14 px, weight 400, width 100, font-provided instructions
leave source X intact. The straight-span runs remain one/two/one in `m`, one/two in `u` and two in `t`; the italic `m`
remains one/one/two. Removing our source-X composition therefore removes a maintenance liability without resolving these
binary width defects. The instructions are genuinely executed; their availability is not an optical-quality guarantee.

**Confirmed local improvement and opposing limitation:** forced automatic Mono gives one/one/one in Roboto 14 px `m`,
one/one in `u` and one in `t`, but changes the A leg runs at Y 4–6 from one/one to one/two, with a visibly heavier right
leg. The unequal `v` runs at the same Y interval remain two/one in both policies. Neither choice resolves the whole
reported problem. This comparison does not justify per-glyph engine selection or threshold/phase tuning.

**Dependency assessment:** registry Skrifa 0.48.0 and HarfRust 0.14.0 replace their previous pins. Forced automatic Mono
has identical delivered pixels in all 48 isolated glyph controls across Roboto 13–16 px and Roboto Italic, Source Sans
3, Literata and slanted Roboto Flex at 14 px. The upgrade does not itself fix those witnesses. All supplied font files
select their interpreter; several carry only minimal programs. A separately constructed instruction-free source
exercises actual automatic fallback. Broader optical assessment, correct weight at neighboring sizes, diagonal balance,
counters and joins remain pending. User selection of the default engine policy does not establish optical acceptance.

#### Scan-control-only program fallback

Literata at 16 px, optical size 12, weight 400 has equal 93-unit (1.488 px) `i`/`j` stems, yet the interpreter leaves
the outlines unchanged and the raster delivers two pixels against one. Forced automatic Mono fits both stems to two
pixels. The font carries no `fpgm`, a `maxp` maximum of zero, and a seven-byte `prep` program that only pushes scan
settings; upstream still prefers its interpreter for any nonempty `prep`, so automatic fitting is never reached.

[prep](https://learn.microsoft.com/en-us/typography/opentype/spec/prep) programs cannot move glyph-associated outline
points, and
[SCANCTRL/SCANTYPE](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#scan-conversion-control)
only tune scan conversion, which the candidate raster does not consume.
[Simple and composite instruction lengths](https://learn.microsoft.com/en-us/typography/opentype/spec/glyf) identify
real outline programs, and [stem-width normalization](https://freetype.org/autohinting/alignment.html) explains why the
automatic hinter restores the equal stems. This is a deliberate project policy adaptation, not upstream behavior.

The adopted candidate policy uses upstream automatic Mono fitting for TrueType fonts verified to carry no glyph
instruction streams (simple or composite), no `fpgm`, and an absent or scan-control-only `prep`; every other font keeps
upstream engine selection. Upstream's own interpreter preference is unchanged, as are CFF/CFF2/VARC fonts, explicit
engine requests, and the raw font bytes. The decision is font-wide and structural, with no requested-glyph, size, or
name exceptions. The request stays `auto_fallback` while provenance reports the actual engine.

**Classification: confirmed engine-selection defect with demonstrated automatic recovery on the reported stems.**
Optical assessment of stem-weight balance under automatic fitting across pairs, sizes, and axes remains pending; the
revision stays open and no optical acceptance is claimed.

#### Native monochrome scan conversion

Candidate Mono adopts
[FreeType 2.15.0's monochrome scan converter](https://github.com/freetype/freetype/blob/VER-2-15-0/src/raster/ftraster.c)
on the whole Skrifa-fitted outline. Nonzero-winding center fill and two-direction smart dropout, excluding stubs with
upstream overshoot handling, replace the coverage-threshold/dropout approximation. Fitting engines, source geometry,
integer origin and layout policy remain separate. Coordinates cross the scanner's 26.6 boundary by nearest rounding;
ties go towards positive infinity. The default remains uniform smart dropout without stubs; manual dropout and stub
controls expose upstream policies without moving outlines. Raw Zeno coverage remains diagnostic and no longer determines
candidate Mono ink. The earlier overlap-coverage and terminal-stub experiments above describe the superseded raster
model.

The question is whether established monochrome scan conversion restores source-connected thin features without
unacceptable weight, counter or terminal changes. Controls hold captured outlines and grid placement fixed against an
independent full FreeType build at the same release; Gray, baseline and independent-reference paths remain unchanged.
Assessment includes Source Sans 3 weights 200/400/700 at nearby sizes and the existing five-family corpus, with no
publication-matrix expansion. Mechanical parity is required; topology or ink counts alone do not establish acceptance.
StrokeStyles and further width fitting are deferred.

The optional font-instruction policy forwards executed TrueType scan state through a metadata-only snapshot of the same
Skrifa release.
[SCANCTRL/SCANTYPE](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#scan-conversion-control)
supply the state; [FreeType's loader](https://github.com/freetype/freetype/blob/VER-2-15-0/src/truetype/ttgload.c)
supplies the global flag mapping and first-point component-marker semantics. Composite instructions update the final
global state while retaining the component contour markers. Fitting and engine selection remain unchanged. Automatic
fitting does not execute font bytecode and retains the manual fallback; scan-only fonts routed automatically therefore
keep their existing behavior. Reference and Gray continue using registry Skrifa independently. This adopts scan-state
transport, not a new fitting model or complete FreeType driver behavior.

**Assessment scope:** default rendering is unchanged; explicit manual or font policies may add or remove thin-feature
ink without moving outlines or layout. Their optical effect depends on the selected font and size and remains subject to
comparison in the browser. No policy is an optical-quality guarantee, and no broader font-mode acceptance is claimed.

**Confirmed correction, scoped browser assessment:** Source Sans 3 at 16 px, weight 200, Mono regains the
source-connected `e` crossbar attachment and the shortened ends of `x`, `c`, `k` and `w`. The same fitted outlines
produce these features with independent full FreeType; no outline movement or glyph-specific rule is needed. At 12–17 px
the `e` loop returns while the `0` and `8` counter counts remain unchanged across 12–20 px at weight 200. Browser
inspection at 14/16/20 px weight 200 and 16 px weights 400/700 supports this local continuity and terminal correction;
counts alone are not the acceptance basis. Restored ends increase local ink, so this is not a global weight-preservation
claim.

**Existing limitation, unresolved:** Roboto 14 px, weight 400, width 100 still has unequal principal stem widths in `m`
and `u` against `n` under font instructions first. The scanner removes isolated cap pixels but does not regularize those
upstream-fitted widths. Inspect stroke-weight balance rather than treating restored continuity as its resolution.
Literata 16 px, weight 400, optical size 12 keeps equal two-column `i`/`j` body stems in the inspected preview. Roboto
Flex 16 px, weight 400, width 100, optical size 14, slant zero retains readable joins and counters in the inspected
sample; broader optical acceptance, especially other weights and sizes, remains pending. These observations do not close
the iteration or alter the approved comparison baseline.

#### Curve scan precision

Candidate Mono requests FreeType's
[high-precision outline hint](https://freetype.org/freetype2/docs/reference/ft2-outline_processing.html#ft_outline_xxx).
The pinned scanner's
[precision selection and curve subdivision](https://github.com/freetype/freetype/blob/VER-2-15-0/src/raster/ftraster.c#L522-L563)
use finer internal intersections for small bitmaps, retaining ordinary precision when its bitmap-size guard excludes
them. This adopts an upstream scan policy: supplied 26.6 geometry, integer origin, fitting ownership, metrics and
dropout controls retain their meanings. No glyph, row, threshold or placement exception selects the correction.

**Confirmed existing scan-conversion defect, corrected:** Roboto Flex Regular at 16 px, all axes at font defaults, Mono
with diagonal fitting off, has an extra pixel at the lower-right bowl arc of both `q` and `g`. Their shared fitted curve
passes above the pixel center by about 0.013 px. Ordinary-precision subdivision rounds the boundary onto the center,
filling it; high precision keeps it outside. Dropout and stub exclusion do not remove it. Independent full FreeType
reproduces the distinction with the same fitted geometry. The rebuilt browser preview removes the pixel in both glyphs;
the same local correction applies at 15 and 17 px.

**Broader optical assessment pending:** isolated controls cover the five bundled families at 12/14/16/18/20/24 px,
weights 300/400/700 plus Source Sans 3 weight 200, with font hints on and forced automatic fitting. Curve-edge ink can
increase or decrease without outline movement. Roboto Italic weight 300 at 12 px separates the two quotation-mark
strokes; Source Sans 3 weights 200/300 at 20 px separates percent-sign parts. These component increases do not
demonstrate a broken principal stroke. Inspect retained curve weight, counter openness, joins and nearby size
transitions; independent scanner parity does not establish broader optical acceptance. The publication matrix and
separate comparison baseline remain unchanged.

#### Terminal tips and junction continuity

The web preview's automatic-fitting fallback includes terminal stubs; executed font scan instructions still take
precedence. Roboto Flex at the font-default axes (weight 400, width 100, optical size 14, slant zero), 16 px, Mono has a
**confirmed terminal-shape defect** at the lower-right tip of `k`: stub rescue extends the last row by one pixel.
Excluding stubs removes that extension with identical fitted geometry and metrics. The same terminal extension occurs at
12–19, 21–22 and 24 px. This finding does not establish broader optical acceptance of stub exclusion.

**Global stub exclusion is held:** Source Sans 3 ExtraLight (weight 200), 12 px, Mono loses the attachment of the `R`
diagonal leg, a **confirmed continuity regression**. The same policy opens the `6` bowl at 12–13 px and the `9` bowl at
12–15 px; their source-connected bowl attachments need protection. Regular-weight cases retain their ink-component
counts, while terminal and enclosed-white-region changes in Literata and Roboto Flex remain pending optical assessment.
The preview retains its existing policy while join protection is investigated; these broader diagnostic cases do not
expand the published specimen matrix.

The pinned [FreeType stub recognizer](https://github.com/freetype/freetype/blob/VER-2-15-0/src/raster/ftraster.c)
classifies adjacent scan profiles and local extrema, rather than semantic stroke endpoints and junctions. Investigate
source-derived feature ownership and continuation evidence, with the same rule protecting joins and excluding true
terminal tips; bitmap component counts alone cannot supply that classification. Independent full FreeType with simple or
smart dropout, at ordinary or high precision, still disconnects the ExtraLight `R` leg when excluding stubs. These
existing controls do not supply join protection.

[Hobby §3.2](../../references/papers/1993-hobby/paper.md#32-width-control) derives stroke widths and relationships from
the medial axis of the filled shape. A **project hypothesis for investigation** is to distinguish terminal branches from
junctions and closed counter paths in this source geometry, retaining rescues needed by connected strokes while
excluding terminal extensions. Analyze the whole filled shape, including overlaps and holes; contour identity is not
stroke ownership. Feature recognition, geometric tolerance, movement-free raster integration and ambiguous-case fallback
need a separate design before implementation. Retain the current policy when the geometric classification is uncertain.
This is not an adopted modification of the pinned FreeType scanner.

Roboto Flex `1` at the same defaults has a separate **confirmed weight imbalance, unchanged by stub policy**. Upstream
automatic Mono fitting narrows its vertical stem from 1.5 to 1 px while retaining roughly the source thickness in the
slanted head. The [coupled-width research direction](#coupled-width-geometry-research-direction) applies to this
relationship: measure widths across source-derived normals and couple relative width changes, preserving attachment,
direction and intentional contrast. Real-outline feature recognition, ownership and raster assessment remain
prerequisites; the correction below owns the resulting source-relative fitting policy.

The first terminal experiment is deliberately conservative: prove a straight cap is a supporting boundary of the whole
filled shape, with both adjacent stroke borders continuing into the filled half-plane. Apply the TrueType cap-closure
test only to such certified tips; leave curves, interior junctions, holes and ambiguous overlap ownership unchanged.
This supporting-cap eligibility restriction is a project hypothesis grounded in the scan-conversion terminal model, not
a substitute for general medial-axis recognition. Inputs are captured source/fitted outlines and fixed-grid FreeType
scans with stubs included/excluded. Controls include transformed synthetic caps, holes, overlaps and junctions, Roboto
Flex `k` at default axes over 12–24 px, and the Source Sans 3 ExtraLight `R`/`6`/`9` failures. The question is whether
certified terminal suppression removes the reported extension without changing any source-connected junction. Any
required glyph exception, unsupported geometric separator or damaged join rejects the slice. Production adoption
requires independent raster checks and browser assessment; the published preview stays unchanged during the experiment.

#### Supporting-cap correction assessment

The current web preview adopts the supporting-cap correction through the explicit `free_type_mono_terminals` stage;
historical role APIs, the approved baseline, Gray and the published specimen matrix keep their existing policies. The
kernel requires matching source/fitted contour and edge ownership, a whole-outline supporting half-plane,
adjacent-border continuation and a unique finite cap crossing the rescued pixel square. Other boundaries, curve hulls
and uncertain predicates veto suppression. Optional geometry work exhaustion keeps the original scan. This is the
conservative project adaptation described above, rather than a general medial-axis endpoint detector. The maintained
kernel has no dependency on the experiment.

**Confirmed correction, scoped browser assessment:** Roboto Flex at the reported default axes, 16 px, Mono loses the
extra lower-right `k` pixel while its outline, coverage, frame and metrics remain identical. Browser inspection supports
the corrected tip and the retained Source Sans 3 ExtraLight `R`/`6`/`9` attachments at 12 px. The previously
demonstrated join regressions keep the original scan at their affected sizes. No glyph-specific production exception is
used.

The isolated 52-case, 4,888-glyph sweep changes 150 glyphs by removing 217 certified rescue pixels; all hard invariants
pass, and ink-component and enclosed-background counts stay unchanged. Counts establish control evidence only. Changed
straight terminals in Roboto Flex, Literata and Source Sans 3 remain **pending broader optical assessment** for retained
end shape and local weight. Hull-supporting long borders can satisfy the eligibility test: the unique cap-square and
other-boundary gates are conservative controls, not proof of semantic stroke ownership. Inspect their ends, and retain
this as a model limitation rather than claiming general terminal recognition or optical acceptance.

**Existing limitation:** the conservative gate suppresses the `k` extension at 13, 16, 19 and 22 px in the 12–24 px
sweep. Other sizes abstain, including some with the original extension. The terminal-only policy leaves the `1` head
imbalance unchanged; the separate source-relative correction below addresses that relationship. Native/WASM parity,
source-identity validation and reconstruction tests cover the new stage; optical closure remains with this open
iteration.

#### Source-relative straight-stroke correction

The `1` investigation applies [Hobby's coupled-width model](../../hobby-fitting.md#valid-straight-medial-intervals) to
the valid straight portions of the source medial axis. Third-boundary contacts end each portion rather than vetoing the
entire pair or being ignored. Source normals and medial radii define relative width error; all related/anchor sample
pairs carry their own arc-length product from (17). The existing upstream-fitted rectilinear stem supplies the anchor
change, and its shared attachment stays fixed. This is a conservative project adaptation of the source feature model,
not an integer-target search or a glyph-specific correction.

The native correction is isolated behind the explicit `source_relative` fitting policy so original fitting controls and
the approved baseline stay independently available. Curves, multiple contours, conflicting anchors or ownership,
numerical uncertainty and movement/validity failures keep the upstream geometry. Inspect retained head direction,
attachment, intentional contrast and the final Mono bitmap at the reported defaults and neighboring sizes; mechanical
convergence and outline validity alone do not establish optical acceptance. The current working preview adopts this
policy; the iteration remains open.

**Confirmed correction, scoped browser assessment:** Roboto Flex Regular at 16 px and default axes, Mono, loses the
reported upper-left thickening of `1`. Its principal stem, attachment and advances remain fixed. The source-normal head
width proxy decreases from about 1.395 to 1.016 px against a 1 px fitted stem; shape terms retain the upstream placement
while allowing local head taper and direction changes. Browser comparison supports the corrected local weight balance
and retained attachment at 16 px, with nearby-size inspection at 12 and 20 px. This is a width-and-local-shape
correction, not a claim of exact border-direction preservation. The existing `k` correction and the ExtraLight Source
Sans 3 `R`/`6`/`9` joins retain their delivered pixels.

**Assessment limits:** the isolated corpus has 34 geometric applications and 20 changes to visible ink. The additional
Roboto Flex `7` changes affect weight along the leg and its end; browser inspection at 12/16/20 px shows retained
continuity, while broader shape/weight assessment remains pending. Some apostrophe outlines and `1` at 20–23 px change
geometry with unchanged visible ink. Source Sans 3 ExtraLight `L` at 20 px gains only an empty bitmap-frame row, with
unchanged visible ink and advance. All mechanical checks pass and component/counter counts stay unchanged; these facts
are controls rather than optical acceptance. Other axes, curved or conflicting features remain outside the scoped
assessment, and unsupported ownership keeps the upstream fit.

#### Selective native hints and automatic fitting

The working Mono preview uses automatic fitting with an optional **Use font hints** preference. When enabled, native
instructions own the axes they constrain or measure, and automatic fitting supplies the remaining axes. When disabled,
upstream automatic Mono owns both axes. Existing URL and variant settings retain their encoding: `font_hints_first` now
selects this selective preview policy, while `upstream_mono` disables native hints. Historical renderer policies remain
independent controls. The approved baseline and configured publication matrix are unchanged.

[Turner and Lemberg](../../references/papers/2003-turner-lemberg/paper.md) describe independent X/Y feature analysis and
fitting.
[TrueType projection, freedom and interpolation semantics](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions)
provide conservative evidence of native ownership. Coordinate differences alone cannot identify ownership: a hint may
constrain a point without moving it, and UTP can clear touched flags. Executed coordinate measurements reserve their
axes too, preserving dependencies whose results feed another axis. An IUP on an axis without touched points contributes
no ownership. PostScript stem operators and alignment zones supply the corresponding source hint evidence.

**Project adaptation:** combine corresponding command coordinates from the independently captured native and automatic
fits only on demonstrably independent axes. Keep native-controlled coordinates exactly; horizontal metrics follow the
X-axis owner. Explicit native hint disabling, failed execution, point-defined vector dependencies, constrained composite
programs, implicit changes on an unreserved axis, transformed PostScript outlines or incompatible command streams retain
the complete native fit. This is conservative axis fallback, not per-point feature completion. Existing source-relative
straight-stroke correction remains on wholly automatic glyphs, and executed font scan settings remain authoritative.

**Confirmed geometric correction:** Roboto Regular, 16 px, weight 400, width 100 has nearly equal source stems in
`i`/`t`/`f`, but native Y-only instructions leave their X positions uncontrolled and deliver unequal widths. The
selective fit takes automatic X while preserving every native Y coordinate. Independent source/automatic captures and
the current evaluator check reconstruction across Roboto, Roboto Italic, Roboto Flex, Literata and Source Sans 3 at
12/16/20 px; Roboto axis-ownership checks also cover 14/18/24 px. These mechanical checks do not establish optical
acceptance.

**Scoped browser assessment:** Roboto at the reported default axes, 16 px, has equal body stems in `i`/`t`/`f` while
retaining its native dot and hook heights. Inspection at 12 and 20 px supports local continuity and stem balance.
Broader assessment of changed glyphs, weights, counters and spacing remains pending. Fonts with both axes reserved
intentionally retain the native result, even if a remaining optical imbalance exists; semantic feature-level completion
is outside this slice.

#### Source-defined x-height alignment

The current explicit Mono pipelines recover missed source top-zone associations before optional stroke fitting.
[FreeType blue zones](https://freetype.org/autohinting/blues.html) supply shared height references and association
ranges; [Hobby §3.3](../../references/papers/1993-hobby/paper.md#33-fitting-verticals-and-horizontals-to-the-pixel-grid)
supplies interpolation between retained references. Literata's light sloped serifs can miss the automatic hinter's
horizontal direction test, leaving their body tops above the fitted x-height.

The project adaptation captures FreeType's fixed Latin x-height donor set independently of the requested text. The
font's variation-aware x-height seeds source association; agreeing grid-aligned donor tops supply the actual fitted
height, preserving automatic x-height scaling. A straight source top must span at least one pixel and lie wholly inside
the upstream association band. The one-pixel segment requirement is a conservative transposition of upstream edge
eligibility to top regions. A demonstrated excess of at least half a pixel permits a monotone contraction toward the
shared reference. Baseline-crossing curve hulls, lower geometry and X coordinates retain their preceding values.
Overlapping contour bounds, conflicting donors and missing references abstain.

Detached marks follow the corrected body through a source-derived white-distance constraint, adapting
[TrueType relative-distance movement](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#move-direct-relative-point)
and [Shamir §3.2](../../references/papers/2003-shamir/paper.md#32-constraints-and-point-relations). The project
recognizes one isolated mark above one baseline-reaching body with a shared horizontal projection in the source,
preceding fit and corrected outline. Its lower source and fitted extrema must be attained on-curve; multiple marks or
possible owners keep the whole preceding glyph. The original white gap is rounded to the pixel grid and the whole mark
translates relative to the corrected body, preserving its fitted shape. A preceding gap outside the half-pixel
nearest-rounding allowance, a collapsed gap or a collision also keeps the preceding glyph. This does not introduce
component resizing or a glyph-specific offset.

**Confirmed geometric correction; broader optical assessment pending:** Literata at 16 px, `wght=252.22`, `opsz=16`,
starts the `i` and `j` bodies on the same row as `n`, including single-glyph previews. The earlier body-only correction
left the dots fixed and enlarged their white gap from two rows to three, a confirmed placement regression. Relative mark
positioning restores two blank rows from the 1.92 px source gap while retaining dot shape and the corrected body height.
The default axes at 16/20 px and inspected neighboring sizes retain their height decisions. Native-owned axes, Gray,
historical controls, spacing and the separate baseline remain independent. This scoped correction does not establish
optical acceptance across families, weights, counters, serifs or size transitions.

#### Remaining stroke balance

The [joint placement and smooth curve study](../../hobby-fitting.md#joint-placement-and-smooth-curve-continuation) owns
the isolated candidate. Native coordinates and finalized layout remain fixed; the maintained app retains its previous
width-only model. The following Roboto 400/16, width 100, Mono (`free_type_mono`, font hints enabled) findings remain
**pending assessment**:

| Feature | Candidate evidence                                                                                                                       | Inspection question                                                                                                     |
| ------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `s`     | Curved spine and shoulder fitting reduces ink from 29 to 25 pixels with native Y retained; the ink frame widens from 7 to 8 px.          | Does the lighter, wider shape retain the lower bowl, terminals, continuity and spacing in text?                         |
| `x`     | Crossing phase produces a symmetric raster; normal widths rise from about 0.89–0.92 to 1.11–1.15 px, and ink rises from 18 to 23 pixels. | Is the heavier crossing preferable, and does its half-pixel placement preserve reading rhythm and side-bearing balance? |
| `S`     | Curve fitting reduces ink from 32 to 26 pixels; the ink frame widens from 8 to 10 px.                                                    | Does the lighter, wider capital preserve contrast, shape and spacing?                                                   |
| `X`     | Phase moves right by about half a pixel; mean projected width falls from 1.49 to 1.18 px while delivered ink rises from 28 to 32 pixels. | Do the crossing, arm weight and side bearings preserve capital balance?                                                 |

The joint crossing/curve candidate leaves default Roboto `2` unchanged. The existing width fit reduces mean normal width
from 1.056 to 0.867 px, but its straight borders diverge (47.24° and 43.61°), and the lower staircase remains heavy.
Fixed curve-incident endpoints make the parallelism/grid constraints incompatible. The
[attached diagonal continuation](#attached-diagonal-consistency) addresses this separate source feature class.

Other sizes and weights, and the Source Sans control require their own shape and contrast assessment. Mechanical and
independent topology checks establish finite geometric invariants, not optical acceptance. The candidate remains
separate from the maintained renderer and the previous comparisons.

**Confirmed regressions, excluded controls:** the free-Y arm broke Source Sans 400/14 `h` and 300/12 `m`; retaining Y
still broke 300/14 `h` and 400/14 `m`; additionally pinning upright X endpoints still broke 300/12 `h`, in both hint
modes. The review candidate conservatively abstains on outlines containing source vertical straight segments. This
general geometry restriction preserves the existing mixed upright-and-curve output, including those regression cases; it
also leaves default Roboto `c`, `5`, `G`, `J` and `U` unchanged. A broader attachment model remains unresolved.

The final isolated matrix covers 72 cells and 6,840 ASCII glyph cases; 315 geometric fits deliver 218 changed bitmaps.
All native coordinate, retained-axis, movement, layout and independent topology checks pass, as do 387 tests. The
component census finds no new components; this is diagnostic evidence, not a continuity or optical verdict. The scope
exception withholds 258 bitmap changes from the anchored control, including the two demonstrated broken-arch tiles and
256 unassessed changes. Browser inspection confirms the default `s` intervention and symmetric, heavier `x`, and the
retained Source Sans 300/12 `h` attachment. Weight, increased curved ink extents and reading rhythm remain pending.

#### Attached diagonal consistency

The [attached diagonal model](../../hobby-fitting.md#attached-diagonal-and-curve-constraints) shares straight-border and
curve-control variables while preserving existing Y fitting, upright X anchors and finalized layout. Sharp line corners
may rotate without reversing orientation; curve joins retain their upstream signed cross, with zero cross at source
smooth joins. Quadratic curvature and tangent inequalities prevent border alignment from reversing the bowl. The
comparison baseline is the preceding isolated joint candidate, and the maintained app remains separate.

For Roboto 400/16, width 100, Mono with hints enabled, the user **visually accepted `2`** on 2026-10-21 in the
[attached diagonal comparison](https://solitaire.taile005dc.ts.net:8909/) ("looks great"). Ink falls from 30 to 26
pixels; the lower diagonal forms a thinner, more even staircase with the bowl and baseline connected. Y fitting and the
baseline stay fixed. This acceptance covers this default `2` case only.

`5` remains **pending assessment**: upper-stem and bowl pixels redistribute, with net ink unchanged at 28 pixels.
Inspect whether the stem, bowl attachment and top-bar extent preserve shape and contrast.

At 14 px, weight 400, `2` changes from 25 to 23 ink pixels with a visibly continuous diagonal. The 300/12 control
remains unchanged. Source Sans 400/16 `v` redistributes terminal/apex ink without changing its 16-pixel total; terminal
alignment and apex balance remain pending. The broader changed cases include `2`, `5`, `V`, `v`, `W`, `w`, `X`, `x`,
`Y`, `y` and `S`; their own source geometry determines applicability and target widths. They require weight, join and
spacing assessment rather than a universal thinning claim.

The isolated matrix covers the same 72 cells and 6,840 ASCII cases: 206 fits deliver 174 changed bitmaps. All 401 tests
pass, including coordinate-encoding controls and analytic constrained-optimum checks. Native capture replay, coordinate
ownership, movement, layout, source curve certificates and independent exact topology checks pass. The component census
finds no increases; these mechanical checks alone do not establish optical acceptance. Unsupported geometry retains the
preceding candidate. No glyph-specific correction or raster-dependent selection is used; iteration 001.03 remains open.

#### Combined text assessment

The [combined text comparison](https://solitaire.taile005dc.ts.net:8910/) compares the frozen joint/curve and
attached-diagonal result with the maintained width-only baseline using identical native pen positions, advances and pair
adjustments. Browser inspection covers Roboto 300 at 12/16 px, 400 at 12/14/16/20 px and 700 at 12/16 px with hints
enabled, plus 400/700 at 16 px with hints disabled. Source Sans controls cover 300/12, 400/14, 400/16 and 700/14; their
delivered glyph pairs are identical in both hint modes. Ordinary sentences, alphabets, numerals and aligned enlarged
details support retained attachments and readable text in those cases, without a demonstrated new break or collision.
This bounded assessment does not establish acceptance of the entire matrix.

The following shape and contrast tradeoffs remain **pending assessment**:

| Case                                     | Finding and inspection question                                                                                                                                          |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Roboto 400/16, hints on/off, `x`/`X`     | The symmetric crossing remains heavier than the width-only result. Does its weight and placement balance the surrounding text?                                           |
| Roboto 400/20, hints on, `s`             | The upper shoulder is visibly flatter and squarer. Does the changed silhouette retain the intended curved shape?                                                         |
| Roboto 700/12, hints on, `S`             | The wider bold form gains ink, from 37 to 42 pixels. Do its terminals and bowl openings retain suitable contrast?                                                        |
| Source Sans 700/14, both hint modes, `s` | The upper aperture becomes pinched at a diagonal pixel contact, enclosing one white pixel under four-neighbor connectivity. Does it read as an unwanted closed aperture? |

Roboto 300/16 `5` loses a four-neighbor enclosed white pixel in both hint modes; enlarged inspection shows an open lower
bowl with connected ink, consistent with the source's open form. The changed default `5` also retains its bowl and
upright attachment in the inspected text, while its redistributed weight remains part of broader assessment. The Source
Sans 300/12 control stays unchanged, including the earlier upright/curve attachment cases.

Across the full matrix, the combined result changes 386 of 6,840 glyph cases against width-only output. Exact replay of
both input packets and shared layout passes; eight-neighbor ink component counts remain unchanged. These are mechanical
controls, not a verdict on the pending apertures or silhouettes. The isolated comparison preserves the existing model
and previous previews; 18/24 px and the remaining size/weight combinations retain their pending optical status.

#### Source Sans crossing balance

The [source contrast assessment](../../hobby-fitting.md#source-contrast-and-crossing-assessment) compares weight 400
`x`/`X` at 12/14/16/20 px with both hint preferences and Roboto controls. Source Sans delivers identical glyphs in the
two hint modes. Its source is approximately, rather than exactly, reflective: independent unrounded straight-arm
measurements at 16 px give about 1.125 versus 1.186 px for `x` and 1.185 versus 1.245 px for `X`, along the existing
source-normal directions. This small contrast is part of the source evidence; exact bitmap symmetry is not required.

**Confirmed unresolved fitting/raster imbalance, rather than a new combined-candidate regression:** default `x` at 16 px
preserves roughly the source's five-percent arm contrast in the width-only geometry, but acquires an extra top pixel on
only the right arm. The two terminal outlines retain the same height. The original automatic result does not have that
one-sided upper row, and the combined candidate retains the width-only output. Browser inspection confirms the unequal
terminal footprint, so the source's small width difference does not justify accepting the complete raster imbalance as
designed.

The width-only fit also tilts the originally horizontal top caps, moving their ends from Y = 8 to 7.9375–8.03125 px. An
internal axis control retaining its X but restoring automatic Y removes the extra upper row yet still produces unequal
terminal ink. This is a causality control rather than a valid fitted candidate: preserving heights alone does not
resolve the coupled placement and scan-conversion effect.

At 14 px, the lower terminal row of `x` is two pixels on the geometrically thinner left arm and one on the right;
unfitted and automatic output have two on each side there. This is demonstrated local quantization amplification, while
its significance for the complete staircase remains **pending assessment**. At 12 px, `X` also retains a crowded,
asymmetric crossing already present in automatic output; this unchanged concern is not evidence of a new regression. The
16/20 px attached `X` fit makes horizontal arm separations nearly equal while leaving some staircase asymmetry. Its
reduction of the source's small arm contrast remains an optical tradeoff, not a reason to force exact reflection.

**Confirmed representation limitation:** the joint crossing model does not support these curved outlines. The attached
fit abstains on `x` at 14/16/20 px and `X` at 12/14 px because captured source quadratics become exactly collinear. At
16 px `x`, two such curves have nonzero signed curvature in the independently instantiated unrounded source. Their
maximum coordinate discrepancy is about 0.013 px. The existing gate correctly rejects its degenerate input; weakening
that gate would not recover the lost source information or establish a safe crossing correction.

The resulting decision is to pursue source-preserving curved crossing placement before accepting these cases. Retain
unrounded source feature geometry, keep delivered rounding and native coordinates authoritative, and investigate the
shared curve correspondence described by Hobby §6. This is a general geometric continuation, with no glyph exception,
weight adjustment or bitmap-symmetry target. Source precision and crossing placement require separate verification; the
existing app, model and approval scope are unchanged.

The [curved crossing continuation](../../hobby-fitting.md#curved-crossing-prototype) now supplies an isolated candidate
for straight arms with quadratic attachments. Finite source-relative reflection and width terms share one X solve;
automatic/native Y and layout remain fixed. Approximate matches can compromise with shape rather than becoming
incompatible exact equalities. A fork with a separate hook does not qualify as the common four-arm crossing.

**Pending optical assessment:** default Source Sans 400/16 `x` loses the isolated upper-right row while retaining small
source arm contrast. Its unequal terminal footprints remain visible. `X` redistributes the crossing and terminal ink,
with a wider ink extent in the inspected result. The [separate comparison](https://solitaire.taile005dc.ts.net:8912/)
includes enlarged details and ordinary text for assessing weight, crossing shape and spacing. This candidate does not
establish optical acceptance or renderer adoption; the preceding combined result retains its existing review status.

#### Terminal reference heights

The [terminal constraint prototype](../../hobby-fitting.md#terminal-reference-height-constraints) keeps recognized
source-horizontal caps at their original automatic/native heights inside the width solve. It also holds X on recognized
source-vertical attachments, including short uprights sharing diagonal vertices. The preceding curved crossing packet
remains the baseline and the fallback wherever the new feature is unsupported or its cap heights already hold.

**Confirmed terminal-placement correction, with broader optical assessment pending:** default Source Sans 400/16,
monochrome output and hints on/off, removes the two pixels below `A`'s baseline and the extra upper-left row on `y`.
Their recognized feet and upper caps retain Y = 0 and Y = 8 respectively. This is a constrained solve rather than a
coordinate-restoration or bitmap-cleanup pass. The default `x`/`X` crossing output remains unchanged. The intervention
also removes one pixel at `K`'s upper diagonal tip while retaining its top ink height; neighboring diagonal weight and
attachment shape remain review questions.

**Pending assessment:** the default Source Sans `*` and grave accent redistribute ink as cap heights and neighboring
strokes are refitted. Inspect arm balance and the accent's position rather than treating a net pixel reduction as a
quality verdict. The asterisk's lower-right tip now contacts its center diagonally; the grave accent ends in a wider
horizontal pixel step. Their silhouette and weight remain pending. Source Sans 400 at 14/20 px and Roboto 400/16 with
hints disabled also change terminal/diagonal placement; inspect continuity, local weight and retained source contrast in
enlarged glyphs and ordinary text. The 14 px `A`/`y` bitmaps remain unchanged despite constrained geometry; the unequal
`A` foot staircase is an existing pending concern. At 20 px `A` changes while `y` remains visibly unchanged. Roboto
400/16 with hints enabled remains unchanged. The broader weight/size matrix remains pending. Existing unresolved
curve/aperture findings retain their previous status.

The [separate comparison](https://solitaire.taile005dc.ts.net:8913/) preserves the maintained app and every preceding
preview. This prototype does not establish renderer adoption or close iteration 001.03.

The 72-cell matrix evaluates 6,840 ASCII cases, applies 852 geometric fits and changes 291 delivered bitmaps. Native
replay, shared layout, exact retained coordinates, per-pair movement bounds and independent raw/captured topology checks
pass. None of the changed cases adds an eight-neighbor ink component. All 464 tests pass, including the 37 new terminal
tests; malformed inputs and unresolved closure ownership retain the previous result. These are mechanical controls, not
optical acceptance.

**User approval, 2026-10-21:** the terminal comparison at port 8913 is approved for adoption in the main app. This
supersedes the prototype-only disposition for the reviewed fitting sequence. Native implementation and verification
follow the [adoption record](../../hobby-fitting.md#approved-fitting-sequence-adoption); the existing diagonal
preference and unrelated pending findings remain in scope as recorded there. Iteration 001.03 stays open.

### Native adoption verification

The maintained native sequence reproduces every delivered bitmap and frame in the approved comparison: 72 cells and
6,840 ASCII cases, Roboto and Source Sans 3, weights 300/400/700, sizes 12/14/16/18/20/24, hints on/off. The source
adapter uses live font geometry rather than the comparison packets. All 509 generator tests pass, including retained
native coordinates, scanner authority, layout invariance, exact unsupported-input fallback and captured-input replay.
These checks verify adoption of the reviewed output; they do not close the earlier optical findings.

**Acceptable deviations for this monochrome delivery:** four outline records differ at 26.6 rounding without changing
their final pixels or bitmap frames: Roboto 300/14 `x` and Source Sans 3 300/18 `x`, both hint modes. Their source model
and constraints are retained; no coordinate compensation is introduced. A fresh Python/Rust joint-system comparison
agrees to about 1e-15 at the Roboto rounding tie. Roboto 300/18, hints off, `~` conservatively retains its preceding
outline when the native curve solve cannot satisfy its bounded initialization; its delivered bitmap also matches the
reviewed result. That numerical fallback remains a geometry follow-up, rather than a visible regression or a runtime
glyph exception. The default 400/16 outline commands match for both families and hint modes.

Evidence is retained under `out/diagnostics/approved-fitting-native/`: `final-summary.json`, `final-mismatches.json`,
the six family/weight packets, `joint-rounding-analysis.json`, `final-tilde-control/` and `generator-tests-final.log`.
The isolated approved comparison and all earlier previews remain separate. Browser checks confirm the reported `A y s x
X 2` shapes in the production build and a working diagonal toggle.

**Runtime limitation:** the 16 px, weight-400 pangram takes about 3.6–4.4 seconds for Roboto and 6.5–6.8 seconds for
Source Sans 3 in the current WASM build on this host; disabled fitting takes about 26–69 ms. These measurements were
taken during parallel verification and are approximate. Diagonal fitting is on by default in new previews with an
explicit-off toggle; this adoption does not change the fast path without fitting. The measurements are retained in
`wasm-runtime-final.json`.

**Adopted in the main app, 2026-10-21:** native/WASM parity passes for 288 valid render cases and eight rejection
controls across the complete corpus matrix, both fitting policies, both mono raster policies and diagonal fitting
on/off. Four Playdate export cases also match byte-for-byte. The additional default-settings run and seven web state
tests pass; typecheck, production build and formatting checks pass. That adopted comparison is `diagonal-shape-02`; the
[revision index](README.md) identifies the current working candidate.

The [main app](https://solitaire.taile005dc.ts.net:8906/) now serves the verified build. All 33 deployed files match
through local HTTP and Tailscale HTTPS, and the existing persistent backend remains in place. The previous app is backed
up separately; all 394 protected files are preserved, including the frozen approved comparison and preceding preview.
Browser update activation confirms build `261021-1519`. Publication evidence is retained in `wasm-summary.json`,
`deployment-receipt.json` and `publication-verification.json`. The existing diagonal toggle setting and iteration's
unrelated pending findings remain unchanged.
