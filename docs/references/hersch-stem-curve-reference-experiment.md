<!-- cspell:words Hersch Hu scanlines -->

# Hersch stem/curve reference experiment

The [owning design](../designs/text-layout/contextual-spacing-and-healing.md#stemcurve-reference-experiment) separates
this source-only experiment from the generic filtered-wall model. The initial classification gate is not established; no
delivered spacing mode is adopted.

## Published reference convention

[Hersch et al. 1995, printed pp. 86–88, Figures 21–22](https://lspwww.epfl.ch/publications/typography/ptgogf_95.pdf#page=11)
tabulates six spacing standards from the original master: `nn`/`HH` for facing vertical bars, `oo`/`OO` for facing
curved stems, and `no`/`HO` for a bar and curve. These values are normalized by body height. For these supported
features, borders are vertical lines through the bar edge or the curve's exterior horizontal extremum; the matching
standard replaces the generic ideal space. This does not authorize mixing an extremum-based reference with a filtered
candidate integral.

For source origin step `s`, right border `r` of the left glyph and left border `l` of the right glyph, the linear gap is
`s + l - r`. Its height-normalized ratio is that gap divided by body height. At the same source scale, candidate steps
solve the matching linear border gap directly. This experiment has no rasterization, rounding, clearance or tracking.
The paper does not provide arbitrary-OpenType feature-classification code or a universal density-conservation theorem.

[Hu 1998, section 4.4, printed pp. 88–91](https://lspwww.epfl.ch/publications/typography/sopfbsc.pdf#page=94)
additionally names distinct stem/stem and curve/curve standards. Its structured parametric characters provide
information that an unannotated outline font does not directly expose. A geometric substitute must therefore be
validated independently.

## Explicit adaptation boundaries

Figure 21 gives one mixed-feature standard per case group, not separate `on`/`OH` references. Reusing `no`/`HO` in the
reverse direction is declared as an unordered-class assumption; it need not reconstruct every designed reverse pair.
Mixed capital/lowercase pairs are unsupported in this initial experiment. Future work must keep normalized ratios,
linear pixel gaps and visual areas dimensionally distinct: averaging reference areas and heights is not generally the
same as averaging linear gaps.

The provisional helper chooses the exterior segment crossing body mid-height, then identifies certain exact vertical
segments or nonlinear extrema. That is a project heuristic, not a recovered Hersch classifier. Neither paper supplies a
minimum primitive length, half-body-height threshold, acceptable dropout percentage or universally required ordering of
all six gaps. No such numerical rule is adopted.

## Source-only gate result

The four-family 16 px experiment holds source metrics and outlines fixed. It separately evaluates the retained body
windows and complete source `n`/`H` bounds; no window is selected by observed density. Every available reference
reconstructs its designed source step exactly. That alone does not validate the classifier:

- Roboto and Roboto Flex expose flat outer plateaus on rounded `o`/`O`. Depending on the body window, the helper calls
  them stems or rejects a curve endpoint joined to a line. Four of six intended standards become unavailable despite the
  glyphs being present. Traces rule out floating-point equality as the cause in these anchors.
- Literata `r` is classified from the stem below its shoulder. That makes the source-only solve shorten `rn` by 2.443 px
  and `re`/`ro` by 2.225 px. Selecting a locally vertical primitive does not establish a simple facing bar.
- Unsupported pairs and fallback choices affect aggregate shifts. Diagonals and compound faces remain explicit
  abstentions; they must not be counted as optically balanced pairs.

The same primitive/whole-feature mismatch appears in exact rounded-plateau examples under scale, translation and contour
reversal. It is a geometric limitation of the tested classifier, not a reason to label named glyphs as exceptions. The
six-reference principle remains a foundation for further work; this source probe does not justify bitmap integration.

Detailed source coordinates, classifier reasons, reference gaps, coverage, signed distributions and generic-fallback
composition are retained under `out/diagnostics/contextual-spacing/stem-curve-source/`. Optical acceptance remains
separate from mechanical reference reconstruction and source-density measurements.
