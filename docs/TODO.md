# TODO

<!-- cspell:words AVAVAV VAVAVA -->

## Evaluate a contour-based spacing model

### Issue

At Roboto 14 px, weight 400, width 100, Mono with projected spacing and zero tracking, `AV` has a 19 px layout advance
and `VA` 18 px. Both visible ink spans are 18 px. The extra pixel is the leading margin of fitted `A`, rather than a
larger internal projected gap. The investigation and assessment remain in
[iteration 001.03](revisions/001/03-spacing-kerning.md#pair-spacing-and-kerning).

The broader concern is that the current model measures outermost horizontal edges, which can occur at different heights.
Equal projected gaps can therefore hide different perceived spacing between diagonals, curves or serifs. Equalizing the
total widths of `AV` and `VA` is not the improvement target.

### Suggested experiment

Adapt
[FontForge's optical-spacing method](https://fontforge.org/docs/ui/dialogs/autowidth.html#the-python-glyphseparationhook):
measure separation between facing contours across their shared height, using a weighted average that gives closer
portions more influence.

**Project hypothesis:** use that measure to preserve each pair's original optical separation after fitting. Unlike
automatic kerning toward a common spacing value, derive the target separately from each pair's source placement,
including enabled source kerning. Choose the integer placement whose fitted separation best matches that target.

FontForge's weighting is heuristic, and adapting it to small binary glyphs needs assessment. Whole-pixel placement still
forces compromises; this method does not guarantee optical quality or symmetric pair widths.

### Tasks

- [ ] Assess internal rhythm in `AVAVAV`, `VAVAVA` and words containing these pairs at native size, separating outside
      margins from pair spacing.
- [ ] Investigate facing contours and establish a consistent measurement scale for source outlines and delivered ink.
      Document sampling, weighting and cases where the measure is unavailable before changing behavior.
- [ ] Prototype a general placement policy preserving the source optical target. Avoid glyph-specific kerning edits,
      family/size exceptions and parameters selected to equalize `AV` and `VA`.
- [ ] Preserve the [shared spacing contracts](../tools/generator/README.md#live-spacing-api), including single kerning
      application and existing fallback behavior.
- [ ] Compare straight, curved and diagonal pairs across fonts, sizes and axes. Use geometric checks and visual review
      under the [evaluation rules](evaluation.md); classify findings in the affected iteration before requesting review.
      Keep broader diagnostics isolated and retain the agreed preview scope and approved baseline.
