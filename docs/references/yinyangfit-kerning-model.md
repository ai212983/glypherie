<!-- cspell:words YinYangFit yinyangfit Kosch JAX Gabor sidebearing sidebearings kerns argmin thresholding nonfinite predeclared -->

# YinYangFit as a raster kerning model

Research only, 2026-11-02. **Yes: a possible model foundation, not a completed optical kerning solution.** Its useful
idea is to score interactions between rendered shapes across orientations/scales, choose pair distances, then encode
those distances as sidebearings and kerns. Kosch explicitly calls the [article provisional][status]. Biological
motivation does not establish perceptual accuracy.

**Verified** below means directly inspected source, not reproduced execution or optical acceptance. **Inference** and
**Proposed** identify our analysis and untested adaptation. Read alongside the [feasibility audit][feasibility] and
[training requirements][training]; their historical experiments are not current model-quality evidence. No code,
dependencies, training, preview or approved baseline changed.

## Concept versus implementation

**Verified:** live Git refs and GitHub commit metadata still identify `master` as
[`609d17e8a6446ec4413a1b02a0768b8214d73333`][head] (2022-11-27), checked today. Freshly read source shows:

- [Current notebook][jax], zero-based cells 22–25: distance/orientation maps and pair-agreement visualization; no scalar
  pair cost, distance optimization, training objective or checkpoint export.
- [Packaged engine][engine]: penalty fields return zeros; its distance-search loop exits after the first candidate.
- [Historical Torch notebook][torch], cells 9 and 13: a real scalar scorer and fitting loss exist. They belong to a
  different model; importing their reduction does not complete the current JAX model.

The [algorithm chapter][models] presents alternatives rather than one finished specification. It proposes minimizing
distance-dependent cost and fitting parameters against designed font distances. That is source-design imitation, not
independent evidence of optimal small-raster spacing. The [pinned manuscript][manuscript] preserves the audited
equations.

## Direct approximation and substantive TODOs

**Verified, author's proposal:** the [direct approximation][direct] pools contrast-weighted V1 complex responses over
scales, retaining orientation. Two angularly masked kernels use radial factors `r^-q` and `r^-(q+1)`, with `q ≈ 2`.
Their ratio `d = (T * f1) / (T * f2)` estimates oriented distance (`*` denotes convolution); another expression
estimates arc strength. Pair fields supply distance disagreement, strength product, distance sum and orientation
relationship.

**Inference:** this preserves more directional/support information than nearest-point distance alone and permits cached
glyph fields. It does not specify how those four quantities produce a calibrated cost. The printed strength equation
also overloads `k` as exponent and strength; its derivation is explicitly unfinished. Origin singularities, zero
denominators, finite support and discretization need declared treatment before reproduction claims.

**Verified:** the [distance-transform alternative][edt] assumes one dominant grouping scale and simplified additive
interactions; it acknowledges nearest-point and orientation limitations. These are modeling compromises, not missing
illustrations.

**Inference:** the consequential gaps are:

- [Aggregation][cost]: channel/spatial pooling, normalization and cross-pair target selection determine the optimum.
  Simply summing activity can bias results by glyph size, stem count or image extent.
- [Pair isolation][isolation] and [feedback][feedback]: separating intrinsic glyph responses from pairing effects and
  approximating competition require explicit nonlinear rules.
- [Calibration][fitting]: the proposed neighboring-distance loss does not supply fitted weights, viewing conditions or
  independent optical targets. A gain/loss balance is not automatically a legibility metric.

Missing explanatory figures are editorial; unspecified aggregation/calibration prevents a usable scorer. Class-kerning
optimization remains future work but does not block evaluating pair distances.

## Sidebearings and kerning

**Verified:** [the decomposition][decomposition] takes chosen horizontal extrema gaps `d_ij` and solves:

`r_i + k_ij + l_j = d_ij`

It minimizes total absolute kern or squared kern. It does not discover good gaps.

**Inference/proposed:** fix a gauge because adding a constant to every right bearing and subtracting it from every left
bearing preserves the equations. Define raster extrema, origins, advances, units and rounding consistently; an extrema
gap is not minimum contour clearance. With fixed bearings, only `k_ij = d_ij - r_i - l_j` remains. Integer placement,
contact/overlap policy and omission of small kerns impose additional constraints; dropping kerns loses exact distances.

## Adaptation to delivered rasters

**Proposed:** score the actual delivered glyphs, preserving baseline, bearings, axes, size, quantization and placement
policy. Unpack binary masks to `0/1`; retain grayscale levels without thresholding. Floating filter responses from
binary input are valid measurements, not changes to the exported bitmap. FreeType distinguishes [pixel formats][pixels]
and explains that [coverage and displayed brightness differ][coverage]; specify the actual compositing/display mapping
rather than treating arbitrary gray codes as linear luminance.

**Inference:** use the deployment's legal integer shifts. If fractional positioning is supported, capture each raster
phase through that renderer; interpolating a cached binary image changes the input. Convolution phase tolerance does not
imply invariance to grid placement, hinting or quantization. Padding must prevent wrapping/clipping.

**Verified/inference:** the article relates [scale weights to viewing conditions][scale] and warns that
[isolated-pair grouping differs inside words][context]. Consequently, neither outline-scale normalization nor a good
pair optimum proves transfer across pixel sizes, bit depths, viewing distances or neighboring letters. This is a
candidate for controlled raster-specific calibration, not a universal kerning table.

## Small falsifiable next step

**Proposed, separately authorized experiment:** freeze two contrasting families, 16/24 px, binary/grayscale output,
eight pairs covering stems, rounds, diagonals and overhangs, and short words containing them. Freeze independent
designer-preferred placement ranges and the unchanged baseline before tuning; use separate calibration examples. Declare
one complete sourced cost or stop if its missing rules cannot be justified. Disclose any novel rule as a project
hypothesis.

Enumerate five feasible integer distances per pair; record costs, ties, minima, boundary hits and repeatability. Stop on
nonfinite/constant scores, boundary-only minima, clipping/padding dependence or overlap-policy violations. Reject the
transfer claim if held-out choices miss the predeclared acceptable ranges or word assessments regress. Mechanical
success alone leaves optical status **pending assessment** under the [evaluation rules][evaluation]. No implementation
or training was run.

[status]: https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/docs/source/frontmatter.markdown#L18-L25
[head]: https://github.com/skosch/YinYangFit/tree/609d17e8a6446ec4413a1b02a0768b8214d73333
[jax]: https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/YinYangFit.ipynb
[engine]: https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/engine/__init__.py#L143-L305
[torch]: https://github.com/skosch/YinYangFit/blob/d9c7e2580f2ad4884c45e5081e8e4613b86632cf/YinYangFit.ipynb
[models]: https://skosch.github.io/YinYangFit/#models-and-cost-functions
[manuscript]: https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/docs/source/algorithms.markdown#L1-L492
[direct]: https://skosch.github.io/YinYangFit/#a-direct-approximation-model-of-local-grouping
[edt]: https://skosch.github.io/YinYangFit/#approximating-g-cell-activations-with-distance-transforms
[cost]: https://skosch.github.io/YinYangFit/#designing-a-cost-function
[isolation]: https://skosch.github.io/YinYangFit/#isolating-pairing-effects
[feedback]: https://skosch.github.io/YinYangFit/#modulatory-feedback-to-b-cells
[fitting]: https://skosch.github.io/YinYangFit/#parameter-fitting-via-backpropagation
[decomposition]: https://skosch.github.io/YinYangFit/#deriving-spacing-and-kerning-values
[pixels]: https://freetype.org/freetype2/docs/reference/ft2-basic_types.html#ft_pixel_mode
[coverage]: https://freetype.org/freetype2/docs/reference/ft2-glyph_retrieval.html#ft_render_glyph
[scale]: https://skosch.github.io/YinYangFit/#contrast-sensitivity-to-spatial-frequencies
[context]: https://skosch.github.io/YinYangFit/#challenges-of-grouping
[feasibility]: yinyangfit-feasibility.md
[training]: yinyangfit-training-requirements.md
[evaluation]: ../evaluation.md#review-and-decision
