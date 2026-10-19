# Bitmap spacing in the preview

There is no spacing-model choice. Placement follows the selected renderer: the working candidate uses one bitmap policy
for 1-bit and 3-bit output, while the reference and legacy baseline keep their source layout as independent comparison
controls. Kerning adds the font's pair-specific adjustments, and **Spacing (px)** adds tracking. Switching renderers
does not change a glyph's outline; the candidate's glyph bitmaps, exported advances and pair adjustments are the same
values in the preview, native specimens and exported strikes.

The preview groups the remaining controls under **Spacing and kerning**. Choose the font, size, axes and text first;
compare renderer roles at **Spacing (px)** zero to see their neutral placement.

## Candidate bitmap placement

After fitting, each glyph is finalized as a bitmap with its bitmap offset, a whole-pixel advance and sparse whole-pixel
pair adjustments:

- The advance is the fitter's returned advance when available, otherwise the rounded source advance. No glyph-specific
  fallback is used.
- Source-tabular digits retain one common whole-pixel advance, and fixed-pitch and tabular pairs carry no fitted bearing
  correction.
- Source kerning, when enabled, and any available fitted bearing correction are each applied once and resolved into the
  pair adjustment. Captures without bearing deltas contribute no correction.
- Values round to the nearest whole pixel, ties away from zero. Signed and negative adjustments keep their direction;
  there is no minimum blank column at neutral tracking, so intentional overhang is preserved.

Because pen positions accumulate in whole pixels, the same pair has the same relative placement regardless of preceding
text. Line widths and wrapping use these integer metrics, so they can differ from the source-linear layout of the
baseline and reference.

## Kerning and tracking

**Kerning** enables or disables source pair adjustments. Turning it off removes that contribution; an available fitting
correction can still apply. The expandable **Kerning pairs** list shows source data independently of this checkbox.

**Spacing (px)** applies a signed offset on top of neutral placement. The UI accepts -2 to +4 px. Mono uses whole-pixel
steps, and the candidate uses whole-pixel steps in Gray as well; baseline and reference Gray keep fractional steps. When
Mono tracking is nonzero, normally separated letter pairs retain at least one blank column. Intentional source overlaps,
fixed pitch and tabular digit relationships bypass that minimum-gap constraint.

Negative tracking preserves neutral ASCII word gaps while tightening letters within words. Positive tracking widens
letters and spaces. The constraints can make the final tightening smaller than the requested offset; wrapping and
drawing use the same placement rules. Exact semantics belong to the
[tracking API](../tools/generator/API.md#tracking-policy).

## Comparing renderers

Use a sample such as `mi li ni Pac quo AV VA` at a fixed size, weight and width. Compare the candidate with baseline and
reference at zero tracking, then switch kerning off and on. Inspect repeated-letter rhythm and word boundaries as well
as individual pairs. Equal measured gaps alone do not establish optical quality.

Kerning preference is global: changing it applies to every font and is saved across reloads. Font and renderer switches
retain it. Reset restores enabled kerning globally and saves that default; it also restores the active font's existing
size, axes, sample text and zero tracking. Invalid saved preferences use defaults. If browser storage is unavailable,
the controls still work during the current page session. Links copied from earlier previews may contain an obsolete
spacing-model parameter; it is ignored and dropped when the URL is next written.

## Sources and implementation

- [FreeType glyph metrics](https://freetype.org/freetype2/docs/glyphs/glyphs-3.html) explains advances and bearings.
- [FreeType kerning](https://freetype.org/freetype2/docs/glyphs/glyphs-4.html) distinguishes pair adjustment from
  advances.
- [FreeType bearing correction](https://freetype.org/freetype2/docs/reference/ft2-glyph_retrieval.html#ft_glyphslotrec)
  documents the correction used with fitted bearing deltas.
- [Hersch 1993, sections 5–6](references/papers/1993-hersch/paper.md) and
  [Shamir 2003, section 3](references/papers/2003-shamir/paper.md) ground placement and geometric relationships.
- [Generator spacing API](../tools/generator/API.md#live-spacing-api) owns numerical contracts;
  [iteration 001.03](revisions/001/03-spacing-kerning.md#pair-spacing-and-kerning) records decisions and pending
  findings.
- [WHATWG Web Storage](https://html.spec.whatwg.org/multipage/webstorage.html#the-localstorage-attribute) and
  [fieldset](https://html.spec.whatwg.org/multipage/form-elements.html#the-fieldset-element) specify the mechanisms used
  for preference persistence and control grouping.
