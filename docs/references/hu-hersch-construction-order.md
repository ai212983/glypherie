<!-- cspell:words Hersch Hu Betrisey CRVS LVS -->

# Hu/Hersch construction order and calibration

The [spacing design](../designs/text-layout/contextual-spacing-and-healing.md#fitted-wall-measurement-candidate) defines
the current adaptation; the [iteration](../revisions/001/03-spacing-kerning.md#proposed-optical-pair-spacing-experiment)
owns optical assessment. This audit distinguishes geometric construction from measurement and normalization. It does not
establish a perceptual model or promote a spacing candidate.

## What the sources specify

The [Hersch/Betrisey patent, preferred embodiment and Figures 1–3](https://patents.google.com/patent/US5768490A/en)
transforms grid-fitted outlines in sequence. A removes hidden whitespace; B replaces concave portions with unit-slope
tangents. C limits cavity depth using 0.21 times its vertical aperture and intersects the contour produced by A and B.
An asymmetric cavity uses a connector from the cutoff's departure to the recessed lip. D limits depth from horizontal
extrema using 0.25 times x-height or cap-height. Border areas then determine placement. Constructing on complete
outlines is consistent with this sequence; cropping first can change which extrema bound a cavity.

The patent does not prescribe our fixed `n/H/0` measurement windows or fixed-alphabet normalization. Its designed-pair
target, intelligent rounding and continuous minimum clearance also differ from the current experiment. A correction to
construction order must not be presented as complete patent parity.

[Hersch et al. 1995, pp. 86–88, Figures 18–22](https://lspwww.epfl.ch/publications/typography/ptgogf_95.pdf) describes
four transformations and supplements the generic model with six font-specific stem/curve standards. Those supported
facing elements use stem edges or curve extrema instead of generic transformed borders. The publication does not supply
a general arbitrary-outline classifier. A single shared target therefore represents only part of that system; this fact
does not validate the project's earlier classifier.

[Hu 1998, section 4.4, pp. 88–91](https://lspwww.epfl.ch/publications/typography/sopfbsc.pdf) uses bitmap walls,
opposite-edge substitution on empty scan lines, 45-degree filtering and summed row gaps. It mentions distinct stem/stem
and curve/curve standards and a visual-depth limit. Its illustrated bounding box contains equal-height `ca`; it supplies
no universal unequal-height class window. Neither source establishes that a cosine-weighted body mean should replace the
area integral.

## Construction findings

The current bounded-bay B operation is an explicit sampled-wall adaptation. It does not find original tangent points or
their subsequent contour intersections. Synthetic envelope agreement and sampling convergence establish that
adaptation's arithmetic, rather than author-code parity.

**C can receive obsolete cavity supports.** Current code detects bays on A and reuses them after B. B can remove an
intermediate maximum, merging two cavities. For midpoint coordinates `0.5 … 6.5`, the outward wall `(0, 0, 2, 0, 1,
0, 2)` becomes `(0, 0, 2, 1.5, 1, 1.5, 2)` after B. Raw supports give two openings of height 1; post-B supports give one
opening of height 3. The latter's C cutoff is `2 − 0.21 × 3 = 1.37`, rather than leaving the central value at 1. This is
a reproducible construction-order discrepancy within the sampled model.

**Clipping can invent a cavity lip.** Consider the full outward wall `(5, 5, 4, 3, 2, 1, 1, 2, 3, 4, 5, 5)`. Its opening
runs from `y=2` to `y=10`, with cutoff `5 − 0.21 × 8 = 3.32`. Cropping to `[0, 8]` before construction replaces one lip
with an endpoint at `x=2, y=7`. The resulting asymmetric construction yields 2 at `y=7.5`, instead of 3.32. Denser
sampling cannot restore discarded contour information. Building complete-outline walls before a declared body integral
avoids this particular artifact; the body integration policy remains a project choice.

The asymmetric Fig. 2b connector does not demonstrably omit a vertical plateau: before its first cutoff departure, the
contour is already outside the cutoff. D's signs and pixel units are consistent with the construction. Enlarging the
construction domain must preserve the class body height in D, rather than substitute full glyph height.

## Calibration findings and scope

For facing-wall intercept `c(A,B) = mean(L_B − R_A)`, the experiment defines:

```text
T = mean_domain(d_source) + mean_domain(c)
d_ideal(A,B) = T − c(A,B)
```

This conserves the continuous mean source origin step on the declared complete domain. No arithmetic error was found. It
neither preserves every source pair's modeled gap nor guarantees the same mean in prose after rounding and clearance.
Recalibrating a changed construction can move pairs whose local walls are completely unchanged.

The four-font 16 px lowercase audit reproduces all 2,704 current fitted placements. Post-B cavity detection leaves all
fitted and source lowercase placements unchanged; Literata's bitmap control changes on 27 pairs. Complete-outline
construction followed by the retained body integral changes 12 fitted Literata pairs and 10 Roboto pairs, with no
integer changes in Roboto Flex or Source Sans 3. These are mechanical differences, not optical judgments.

In Literata, local `c`, `a`, `n` and `x` walls are unchanged by the full-outline variant. Its shared target moves from
2.604261 to 2.581834 px because other glyphs change. Consequently, `ca` moves from ideal 8.517686 to 8.495260 px and
rounds from 9 to 8; `en` also rounds down. `nx` remains 11 and `os` remains 10. The flips persist at 32, 64 and 128
samples per pixel, but must be attributed to calibration rather than repaired local cavities.

The separate
[construction-order candidate](../designs/text-layout/contextual-spacing-and-healing.md#construction-order-candidate)
uses a full construction domain, finds C supports after B, and preserves D's body height, the density invariant, signed
rounding and actual bitmap overlap checks. It remains separate from target-policy experiments. This addresses identified
construction limitations without claiming to resolve the remaining perceptual objective. No pair-specific preferred
pixels, free weighting coefficients or altered rounding thresholds follow from this audit.

Detailed probes, synthetic examples, preservation checks and independent source interpretation are retained under
`out/diagnostics/contextual-spacing/wall-construction-audit/`.
