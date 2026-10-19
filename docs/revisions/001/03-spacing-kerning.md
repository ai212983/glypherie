# Monochrome geometry and spacing

<!-- cspell:words HarfBuzz GSUB GPOS ttfautohint unhinted Skia PathOps autofit rekerning -->

Use unmodified upstream Mono fitting with font instructions first and automatic fitting as an explicit control. Assess
binary continuity, feature balance and reading rhythm with pixel-aligned display and source kerning inspection. Source
layout is independent of engine choice; fitted outlines need not preserve source coordinates.

## Topics

### Mono fitting and engine selection

The default candidate uses registry Skrifa's `Target::Mono` with `Engine::AutoFallback`. The library chooses the font's
interpreter when appropriate and otherwise its automatic hinter. **Automatic Mono** forces `Engine::Auto(None)` as the
second selectable policy. Both consume runtime font bytes in native and WASM rendering. No font-family, glyph, size or
axis exceptions participate in engine selection.

The [upstream engine API](https://docs.rs/skrifa/0.48.0/skrifa/outline/enum.Engine.html) and
[FreeType load-target contract](https://freetype.org/freetype2/docs/reference/ft2-glyph_retrieval.html#ft_load_target_xxx)
supply the foundation. The pinned Skrifa 0.48.0 implementation considers TrueType glyph instructions and font programs;
CFF/CFF2 uses its interpreter. Presence of instructions does not establish their quality for binary output. FreeType
explicitly limits strong small-size monochrome quality to fonts with suitable black-and-white hints. No general Mono
strength or diagonal-balance parameter is exposed by Skrifa.

**Invariant:** retain whole outlines exactly as the selected upstream hinter returns them. Both engine policies feed the
same overlap-aware coverage reduction, threshold and dropout raster. This is upstream fitting under the project raster,
not byte-identical FreeType Mono rendering. Capture provenance names the effective policy and resolved engine. Gray
retains upstream Normal automatic fitting. Layout finalizes bitmap metrics from the fitted results (see pair spacing
below); source-coordinate identity is not an optical acceptance criterion.

The previous `vertical_only` strategy combined source X and Smooth Light Y, following
[ttfautohint's Y-only policy](https://freetype.org/ttfautohint/doc/ttfautohint.html#background-and-technical-details).
It avoided the earlier horizontal distortion of A while retaining fractional vertical-stem widths whose binary weight
depends on phase. That custom composition and its topology requirement are removed. `vertical_only` and `vertical-01`
are rejected, not aliases for the new default. Earlier source-X findings below describe that retired policy.

### Pair spacing and kerning

The working candidate uses one bitmap placement policy for Mono and Gray, shared by the exported strike, native
specimens and the interactive preview. After fitting, each glyph has a bitmap offset, a whole-pixel advance and sparse
whole-pixel pair adjustments; pen positions accumulate in whole pixels. Reference and legacy baseline keep source-linear
layout as independent comparison controls, not as selectable spacing policies.

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
integer pair adjustment. Captures that supply no bearing deltas contribute no correction, and none is invented: current
captures record no such deltas. Quantization is to the nearest whole pixel with ties away from zero, so a negated
adjustment quantizes to its negation. Retaining HarfRust's source pair extraction and choosing its pixel quantization
are project adaptations of FreeType's integer bearing correction and grid-fitted kerning, not a claim of complete
FreeType layout parity. The invariant is that the same bitmap pair has the same relative placement irrespective of
preceding text; this does not impose equal white gaps on different pairs, and no optical rekerning or projected-gap
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
That placement algorithm is removed; only its general source/ink geometry remains, as the explicit-tracking
minimum-clearance guard below. On the approved baseline at Roboto 14 px, weight 400, width 100 Mono, projected `AV` had
advanced 19 px and `VA` 18 px with zero projected blank columns; independent HarfBuzz source measurements confirmed both
source gaps round to zero. Classification: that advance difference followed the former placement contract, with no
demonstrated calculation error. Perceived diagonal separation remains pending optical assessment.

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

Fractional tracking changes Mono rounding phase; tightening letters and spaces can compress word boundaries twice.
[OpenType horizontal metrics](https://learn.microsoft.com/en-us/typography/opentype/spec/hmtx) supply source advances
and bearings. Preserve neutral word separation and intentional overlaps.

The adopted user policy uses whole-pixel Mono tracking, and whole-pixel candidate Gray tracking, with at least one blank
column for normally separated Mono pairs under nonzero tracking, preserving fixed pitch, tabular digits and source
zero/negative gaps. Baseline and reference Gray retain fractional tracking. Negative tracking preserves neutral ASCII
word gaps; positive tracking widens letters and spaces. These are explicit layout choices, not sourced optical optima.

The [tracking constraints](../../../tools/generator/README.md#tracking-policy) make line-width changes non-additive. A
one-column floor does not establish optical correctness for curved or diagonal pairs; Roboto 14 px, weight 641, width
100 is an isolated spacing witness.

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
[WASM API](../../../tools/wasm/README.md#kerning-pairs). The
[inspection interface](../../../tools/web/CONTRACT.md#specimens) distinguishes an unavailable API, absent font kerning
and extraction failure; inspection failure does not block glyph rendering.

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
