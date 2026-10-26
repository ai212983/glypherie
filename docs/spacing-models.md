<!-- cspell:words unhinted -->

# Bitmap spacing in the preview

The preview uses bitmap placement, with **Kerning** and **Tracking (px)** controls in **Layout**. Historical reference
and baseline APIs retain source-linear layout for diagnostic comparisons. The proposed optical-spacing experiment is not
a preview mode.

## Bitmap placement

Fitting supplies the glyph outline and, when available, its adjusted advance. Layout finalizes whole-pixel advances and
sparse whole-pixel pair adjustments, shared by preview, native specimens and bitmap export. Changing placement does not
refit the glyph or change its bitmap. The exact rules belong to the
[generator spacing API](../tools/generator/API.md#live-spacing-api).

Adjusted advances and bearing-rounding residuals serve different purposes. Layout uses the adjusted advances and applies
available residuals as additional pair compensation, exactly once per pair. Candidate automatic-Mono captures carry the
fitter's residuals identically on both scan converters; independent reference, native, unhinted, Gray and non-Mono
captures carry none. The
[fitting-compensation investigation](revisions/001/03-spacing-kerning.md#fitting-bearing-compensation-investigation)
explains why bitmap bounds cannot replace residuals.

Whole-pixel pen positions keep a pair's relative placement independent of preceding text. Fixed-pitch cells and
source-tabular digits retain their advance relationships. Signed pair adjustments preserve intentional overhang without
requiring a blank column. Fractional source kerning can disappear when rounded to whole pixels.

## Kerning and tracking

**Kerning** enables or disables source-font pair adjustments at the selected size and axes. Turning it off removes that
contribution independently of any fitting correction. Source pair data is available through the renderer's inspection
API; the editor has no pair inspector.

**Tracking (px)** accepts -2 to +4 px in whole-pixel steps for both Mono and Gray. It adds the same signed offset to
every finalized advance, including spaces and the final glyph advance. Negative tracking can narrow word gaps and
overlap glyphs; the requested amount is not limited by minimum gaps or per-glyph clamps. Bitmaps and pair adjustments
stay unchanged; measurement, wrapping and tracked export use the adjusted advances.

The [tracking API](../tools/generator/API.md#tracking-policy) documents the wider native range and historical tracking
protections. Saved variants retain their kerning and tracking settings.

There are no independent word-spacing or line-spacing controls. Fonts exposing an optical-size axis can change their
design and metrics through the axis controls; optical size is not a replacement for pair kerning.

## Assessing spacing

At fixed size and axes, start with zero tracking and compare source kerning off and on. Inspect straight, curved and
diagonal neighbors, repeated-letter rhythm, punctuation, digits and word boundaries. Include pairs with different
prefixes to distinguish a pair adjustment from accumulated-position effects. Equal measured white gaps alone do not
establish optical quality.

The [pair-spacing decision](revisions/001/03-spacing-kerning.md#pair-spacing-and-kerning) records the adopted model and
pending assessment. The
[optical-spacing proposal](revisions/001/03-spacing-kerning.md#proposed-optical-pair-spacing-experiment) defines the
planned source-relative comparison.

## Sources

- [FreeType glyph metrics](https://freetype.org/freetype2/docs/glyphs/glyphs-3.html) separates advances, bearings and
  bitmap bounds.
- [FreeType kerning](https://freetype.org/freetype2/docs/glyphs/glyphs-4.html) distinguishes source pair positioning
  from advances.
- [FreeType bearing correction](https://freetype.org/freetype2/docs/reference/ft2-glyph_retrieval.html#ft_glyphslotrec)
  defines integer placement using fitting residuals.
- [Hersch 1993, sections 5–6](references/papers/1993-hersch/paper.md) and
  [Shamir 2003, section 3](references/papers/2003-shamir/paper.md) ground grid placement and preservation of source
  relationships.
