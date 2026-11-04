<!-- cspell:words unhinted TypeFacet FontForge -->

# Bitmap spacing in the preview

The preview uses bitmap placement, with **Kerning method** and **Tracking (px)** controls in **Layout**. Source is the
default. TypeFacet, Hu/Hersch and FontForge-derived source-relative spacing are experimental alternatives with distinct
objectives. Historical reference and baseline APIs retain source-linear layout for diagnostic comparisons. The earlier
comparisons remain on their
[isolated pages](../../../experiments/contextual_spacing/README.md#interactive-comparison-page).

## Bitmap placement

Fitting supplies the glyph outline and, when available, its adjusted advance. Layout finalizes whole-pixel advances and
sparse whole-pixel pair adjustments, shared by preview, native specimens and bitmap export. Changing placement does not
refit the glyph or change its bitmap. The exact rules belong to the
[generator spacing API](../../../crates/generator/API.md#live-spacing-api).

In the Source method, adjusted advances and bearing-rounding residuals serve different purposes. Layout uses the
adjusted advances and applies available residuals as additional pair compensation, exactly once per pair. Candidate
automatic-Mono captures carry the fitter's residuals identically on both scan converters; independent reference, native,
unhinted, Gray and non-Mono captures carry none. The
[fitting-compensation investigation](../../revisions/001/03-spacing-kerning.md#fitting-bearing-compensation-investigation)
explains why bitmap bounds cannot replace residuals.

Whole-pixel pen positions keep a pair's relative placement independent of preceding text. Fixed-pitch cells and
source-tabular digits retain their advance relationships. Signed pair adjustments preserve intentional overhang without
requiring a blank column. Fractional source kerning can disappear when rounded to whole pixels.

## Kerning and tracking

**Source** exposes a **Kerning** switch for source-font pair adjustments at the selected size and axes. Turning it off
removes that contribution independently of any fitting correction. Source pair data is available through the renderer's
inspection API; the editor has no pair inspector.

**TypeFacet** exposes four manual parameters in em units: normal distance for body spacing, intrusion tolerance for
details entering the virtual spacing region, minimum clearance, and maximum horizontal bounding-box overlap. Minimum
clearance cannot exceed normal distance. The sliders retain their values per font variant and can reset together to
defaults. Their [ranges and defaults](../../../crates/generator/API.md#pair-kerning-methods) do not provide automatic
font calibration. Whole-pixel placement means small parameter edits may leave a pair unchanged. The method works with
Mono and grayscale output: it analyzes delivered cells for Mono and fitted curves for Gray. Changing gamma or Gray depth
does not change its spacing geometry. Method switching retains each method's settings, including across profile changes
and reloads.

**Hu/Hersch** uses the fixed full-outline wall construction and a density target calibrated from the complete alphabet
at the selected font instance. Its correction-strength slider blends Source spacing at 0% with the full correction at
100%, which is the default. The geometric model and density target stay fixed. Its target conserves the fixed alphabet's
continuous mean source origin step; it does not guarantee identical visible gaps after integer placement. Calibration
does not depend on the preview text. It measures fitted outlines for Mono and Gray, with reference windows taken from
delivered Mono cells or Gray fitted outlines. Unsupported classes or incomplete calibration retain Source spacing.

**FontForge source-relative** spacing preserves each source pair's estimated contour separation after fitting. Its
strength blends from Source at zero to source-relative compensation at one. It does not equalize all pairs toward a
shared gap; the source design remains the target. Pairs without a shared measurement band retain Source.

The [pair-method interface](../../../crates/generator/API.md#pair-kerning-methods) owns parameters, profile support,
eligibility, fallbacks and placement; the
[design](../../designs/text-layout/contextual-spacing-and-healing.md#interchangeable-kerning-methods) owns each model
and its verification scope. Only the selected method's controls affect rendering. CounterSpace remains an isolated
experiment until its calibration and scoring implementation has a browser runtime.

**Tracking (px)** accepts -2 to +4 px in whole-pixel steps for both Mono and Gray. It adds the same signed offset to
every finalized advance, including spaces and the final glyph advance. Negative tracking can narrow word gaps and
overlap glyphs; the requested amount is not limited by minimum gaps or per-glyph clamps. Bitmaps and pair adjustments
stay unchanged; measurement, wrapping and tracked export use the adjusted advances.

The [tracking API](../../../crates/generator/API.md#tracking-policy) documents the wider native range and historical
tracking protections. Saved variants retain their kerning and tracking settings.

There are no independent word-spacing or line-spacing controls. Fonts exposing an optical-size axis can change their
design and metrics through the axis controls; optical size is not a replacement for pair kerning.

## Assessing spacing

At fixed size and axes, start with zero tracking and compare the methods, or source kerning off and on. Inspect
straight, curved and diagonal neighbors, repeated-letter rhythm, punctuation, digits and word boundaries. Include pairs
with different prefixes to distinguish a pair adjustment from accumulated-position effects. Equal measured white gaps
alone do not establish optical quality.

The [pair-spacing decision](../../revisions/001/03-spacing-kerning.md#pair-spacing-and-kerning) records the adopted
model and pending assessment. The
[optical-spacing design](../../designs/text-layout/contextual-spacing-and-healing.md#optical-spacing-experiment) owns
the isolated Hu/Hersch optical experiment and its CounterSpace, filtered-wall, FontForge and source-preserving
comparisons. Texture healing is deferred.

## Sources

- [FreeType glyph metrics](https://freetype.org/freetype2/docs/glyphs/glyphs-3.html) separates advances, bearings and
  bitmap bounds.
- [FreeType kerning](https://freetype.org/freetype2/docs/glyphs/glyphs-4.html) distinguishes source pair positioning
  from advances.
- [FreeType bearing correction](https://freetype.org/freetype2/docs/reference/ft2-glyph_retrieval.html#ft_glyphslotrec)
  defines integer placement using fitting residuals.
- [Hersch 1993, sections 5–6](../../references/papers/1993-hersch/paper.md) and
  [Shamir 2003, section 3](../../references/papers/2003-shamir/paper.md) ground grid placement and preservation of
  source relationships.
