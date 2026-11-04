<!-- cspell:words Hersch Hu IOS PES KAW CRVS LVS BSD CharHeight RelativeDepth VisualDepthFactor VisualDepthLimit MinSpace sidebearing sidebearings -->

# Reassessing filtered-wall optical spacing

Research only. This note revisits the original papers and current experimental implementation after reported Literata
spacing concerns for `jo`, `yd`, `le`, `pi`, `ip`, `te`, `tp`, `OE` and `OR`. It does not change the candidate or
establish optical acceptance. The [earlier audit](filtered-wall-spacing.md) remains the record of the implemented
subset.

## What the original papers actually specify

[Hersch et al. 1995, printed pp. 85–88](https://lspwww.epfl.ch/publications/typography/ptgogf_95.pdf#page=9), including
Figures 18–22, specifies more than slope filtering and equal area:

- Page 86: remove hidden whitespace, limit concavity slope, then limit depth by aperture size and character height.
  Figure 19 gives `ApertureDepth = CavityOpening × RelativeDepth` and `VisualDepth = CharHeight × VisualDepthFactor`.
  Numerical factors are not supplied.
- Pages 86–88: six source-master distances distinguish `HH`, `nn`, `OO`, `oo`, `HO`, `no`. For recognized facing bars
  and curves, replace borders with vertical lines through bar edges or curve extremes and use the corresponding
  tabulated distance, multiplied by height, as ideal area.
- Page 87: `BSD = (CRVS(first) + IOS − LVS(second)) / CharHeight`. Capital, lowercase and mixed heights differ; mixed
  ideal areas and heights are averaged separately.
- Page 88: add minimum clearance and use a frequency-weighted histogram to select a rounding threshold.

These are source-specific spacing relationships, not a requirement that all raw gaps match.

[Hu 1998, §4.4, printed pp. 88–91](https://lspwww.epfl.ch/publications/typography/sopfbsc.pdf#page=94), including
Figures 4.5–4.8, replaces outline transformations with bitmap walls. Missing rows use the opposite bounding-box edge;
±45° filtering precedes summation of inter-wall area. The correction is `(IOS − PES) / CH`. Page 91 explicitly retains
separate `nn` stem and `oo` curve standards, `VisualDepthLimit`, and `MinSpace`. The section does not supply complete
filter/depth pseudocode, numerical defaults, or a classifier for arbitrary outlines. Its examples do not establish a
universal solution for every Latin pair or small binary raster.

## Differences in the current implementation

The following are checkout observations, independent of optical judgment:

| Current mechanism                                                                               | Consequence                                                                                          |
| ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `filtered_walls.filter_45` applies only slope envelopes                                         | No aperture-relative or character-height depth cap is present.                                       |
| `FilteredCalibration` uses source `n`, `H`, `0` bounds                                          | Those bounds define measurement windows; font x-height/cap-height metrics are not used.              |
| `pair_basis` distinguishes case and digits                                                      | Facing bar/curve categories and their six references are absent.                                     |
| Source outlines/metrics establish targets; delivered bitmap cells supply candidate measurements | Rasterization can change the reference geometry itself, producing a density shift across many pairs. |
| Mixed target averages two linear gaps, using the union of reference windows                     | This differs from the original area's and height's separate averaging.                               |
| `pixel_round` uses one fixed threshold                                                          | No font/corpus rounding-histogram policy is implemented.                                             |
| Clearance rejects all closed-cell face and corner contacts                                      | This is a conservative Mono policy, stronger than the paper's grayscale clearance.                   |

The measurement window excludes direct whitespace contributions from ink beyond it. For lowercase, ascenders, descenders
and dots outside source `n` bounds therefore do not enter the area score, although the full bitmap still enters
clearance. The original `CharHeight` serves normalization and depth scaling; this alone does not derive the current
window-clipping policy. Figures illustrate body-height regions but do not completely specify unequal-height bitmap
handling. Changing to per-pair overlap windows would introduce a different, unsupported normalization problem.

## Correcting two explanations

Separable sidebearings are not by themselves evidence of a faulty Hu implementation. The current score satisfies

```text
mean_gap(A, B, d) = d + mean(filtered_left(B)) − mean(filtered_right(A))
```

Hersch's published BSD formula is also additive in the two individual borders. Neither provides a general guarantee of
rich pair interaction. Adding depth caps can improve wall estimates without removing this mathematical property.

Likewise, identical results for `OE` and `OR` do not independently falsify the original model: both can present a right
curve facing a left vertical stem. Hersch groups equivalent facing elements; both originals explicitly de-emphasize
internal glyph detail. Their equal placement may still look wrong, but explaining that observation requires comparing
the source spacing and rendered geometry rather than assuming the papers demand different values.

## Defensible next experiment

Do not replace the current target with another universal constant. First separate measurement, calibration and integer
placement in diagnostics. For each reported pair retain source-designed step, candidate continuous step, rounded step,
clearance adjustment, wall profiles and the reference supplying the target. Compare at native resolution and neighboring
sizes; one pixel is a substantial change at 16 px.

For a closer adaptation of these papers, implement the omitted depth controls and six reference relationships as one
bounded candidate. Recover or explicitly define a geometric facing-element classifier; abstain when classification is
uncertain. The papers do not authorize a letter-name lookup table or tuned exceptions for the reported pairs. Unknown
depth factors must remain disclosed experimental parameters, assessed across held-out fonts and pairs, rather than
optimized against Literata examples. The geometry used for references, measurement windows and mixed-case areas must be
specified consistently before changing the solver.

A separate conservative comparison can apply the improved wall measurement to each pair's own source-designed spacing,
then preserve that relationship through rasterization. This is a project adaptation of source-relative compensation; it
intentionally retains designed pair differences and cannot promise equal mean gaps. It helps identify whether a
regression comes from the measurement or from replacing the source's spacing relationships.

Neither candidate is an established solution merely because it follows more equations. Required falsification includes
equal-facing-element relationships, cavity aperture/depth changes, unequal heights, missing rows, reference sampling
convergence, exact metric identity when disabled, feasible collision clearance and rounding stability. Mechanical
success must be followed by native-size reading assessment, including unreported pairs and other font families.

## Unresolved policy choices

The papers leave depth factors, arbitrary-font classification, unequal-height bitmap windows and modern small Mono
acceptance unresolved. Original six references cover ordinary Latin stem/curve combinations, not every diagonal,
punctuation mark or digit style. Experimental `00` calibration is not established by either source. The
[pair-model investigation](optical-spacing-pair-models.md) evaluates whole-image and pair-dependent alternatives; their
evidence does not establish acceptance for this renderer.
