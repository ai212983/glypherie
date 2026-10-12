# Spacing models in the preview

The spacing model chooses where letters are placed. Kerning adds the font's pair-specific adjustments, and **Spacing
(px)** adds tracking. These controls use the selected renderer's glyphs; switching models does not change a glyph's
outline or individual bitmap.

The preview groups the controls under **Spacing and kerning**. Choose the font, size, axes and text first, then compare
models with **Spacing (px)** at zero to see their neutral placement.

A hint beneath the spacing controls explains the selected model. In gray mode it also identifies the source-spacing
behavior and reminds you that your selection is retained for returning to 1-bit mode.

## Available models

| UI choice        | Value       | Placement                                                                                                                        | What it helps compare                                                    |
| ---------------- | ----------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Renderer default | `auto`      | Uses the selected renderer's default model.                                                                                      | Normal behavior of each renderer.                                        |
| Source spacing   | `source`    | Uses source advances and source pair kerning.                                                                                    | The font's original metric relationships applied to the rendered glyphs. |
| Fitted metrics   | `fitted`    | Uses the selected renderer's returned hinted advances and available bearing corrections.                                         | How fitted metrics account for changes made during hinting.              |
| Projected gap    | `projected` | Uses fitted metrics, then adjusts supported pairs to reproduce their rounded source projected gap between delivered ink columns. | Whether source separation survives conversion to an integer pixel grid.  |

An advance is the distance from one glyph's origin to the next origin before pair adjustments. It includes the glyph's
side bearings; it is not the width of the visible ink. Hinting can move that ink while the source advance stays fixed.

**Source spacing** retains those original advances. Origins are rounded when the glyph bitmaps are placed, so their
visible gaps may differ even when their source spacing is similar.

**Fitted metrics** takes the advance returned by hinting when available, falling back to the report's advance otherwise.
Where the selected renderer supplies phantom-point bearing deltas, it also applies FreeType's integer positioning
correction. This coordinates metrics with fitting, but does not directly constrain the visible white gap of a pair.
Renderers without those deltas receive no such correction.

**Projected gap** measures a pair's signed horizontal source gap from the source advance, source kerning and tight
outline extrema. It rounds that distance to a whole-pixel target, then chooses the relative origin that produces that
gap between the fitted glyphs' delivered ink columns. Each pair keeps its own target: this does not give every pair the
same gap or force `AV` and `VA` to be symmetric. Source overlaps can produce negative targets.

Projected placement falls back to fitted placement for spaces, empty or unsupported pairs. Source-declared fixed-pitch
fonts and equal-advance digit pairs bypass the projection correction to retain their metric relationships. Bounds are
horizontal projections, so bowls, diagonals and serif overhangs can make this gap a poor proxy for perceived separation.
Projected spacing remains an experiment requiring visual assessment.

## What Renderer default selects

| Output     | Selected renderer | Effective spacing               |
| ---------- | ----------------- | ------------------------------- |
| 1-bit      | Reference         | Source spacing                  |
| 1-bit      | Approved baseline | Source spacing                  |
| 1-bit      | Working candidate | Projected gap                   |
| 3-bit gray | Any renderer      | Source placement through `auto` |

Explicit spacing models are available only in 1-bit mode. Gray disables the selector and sends `auto`, while retaining
the selected Mono model for switching back. An explicit model in Mono uses the currently selected renderer's own glyphs
and metrics; choosing Projected gap does not select the candidate renderer.

## Kerning and tracking

**Kerning** enables or disables source pair adjustments under every model. Each source adjustment contributes once.
Turning it off removes that contribution; fitted bearing corrections and projected gap corrections can still apply. The
expandable **Kerning pairs** list shows source data independently of this checkbox.

**Spacing (px)** applies a signed offset on top of the chosen neutral model. The UI accepts -2 to +4 px. In Mono it uses
whole-pixel steps, and normally separated letter pairs retain at least one blank column when tracking is nonzero.
Intentional source overlaps, fixed pitch and tabular digit relationships bypass that minimum-gap constraint. Gray uses
fractional steps.

Negative tracking preserves neutral ASCII word gaps while tightening letters within words. Positive tracking widens
letters and spaces. The constraints can make the final tightening smaller than the requested offset; wrapping and
drawing use the same placement rules. Exact semantics belong to the
[tracking API](../tools/generator/README.md#tracking-policy).

## Comparing choices

Use a sample such as `mi li ni Pac quo AV VA` at a fixed size, weight and width. Compare Source spacing, Fitted metrics
and Projected gap at zero tracking, then switch kerning off and on without changing the model. Inspect repeated-letter
rhythm and word boundaries as well as individual pairs. Equal measured gaps alone do not establish optical quality.

Spacing model and kerning preferences are global: changing either applies to every font and is saved across reloads.
Font and renderer switches retain them. Reset restores Renderer default and enabled kerning globally and saves those
defaults; it also restores the active font's existing size, axes, sample text and zero tracking. Invalid saved
preferences use defaults. If browser storage is unavailable, the controls still work during the current page session.

## Sources and implementation

- [FreeType glyph metrics](https://freetype.org/freetype2/docs/glyphs/glyphs-3.html) explains advances and bearings.
- [FreeType kerning](https://freetype.org/freetype2/docs/glyphs/glyphs-4.html) distinguishes pair adjustment from
  advances.
- [FreeType bearing correction](https://freetype.org/freetype2/docs/reference/ft2-glyph_retrieval.html#ft_glyphslotrec)
  documents the correction used with fitted bearing deltas.
- [Hersch 1993, sections 5–6](references/papers/1993-hersch/paper.md) and
  [Shamir 2003, section 3](references/papers/2003-shamir/paper.md) ground placement and geometric relationships. The
  rounded projected-gap model is a project hypothesis, not a prescribed algorithm from those papers.
- [Generator spacing API](../tools/generator/README.md#live-spacing-api) owns numerical contracts;
  [iteration 001.03](revisions/001/03-spacing-kerning.md#pair-spacing-and-kerning) records decisions and pending
  findings.
- [WHATWG Web Storage](https://html.spec.whatwg.org/multipage/webstorage.html#the-localstorage-attribute) and
  [fieldset](https://html.spec.whatwg.org/multipage/form-elements.html#the-fieldset-element) specify the mechanisms used
  for preference persistence and control grouping.
