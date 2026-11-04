<!-- cspell:words Cozens Kosch Nakatsuru Uchida CounterSpace YinYangFit ResNet counterspace sidebearings multiscale TNC ndarray Hersch Hu gputools underdetermined -->

# Optical pair-spacing models and alternatives

Research only, following reported Literata 16 px spacing concerns. Read this alongside the
[Hu/Hersch reassessment](optical-spacing-perception-reassessment.md), which corrects the interpretation of the original
papers. No implementation or preview behavior changes follow from this note.

## Recommendation

Test a two-dimensional, font-calibrated pair score using CounterSpace as an independent executable reference. Compare it
with the current candidate, metric placement, source-relative placement, and a closer Hersch adaptation. Do not promise
that CounterSpace solves the reported pairs: its author explicitly calls it a research prototype. Whole-shape learned
models are a stronger longer-term direction if the geometric candidates fail, with substantially more training work.

This recommendation preserves the aim of balancing pairs through unchanged glyph placement. Source-relative compensation
remains a useful control; it preserves each pair's own designed relationship and does not accomplish shared perceptual
balance by itself. No universal replacement gap or per-glyph exception is proposed.

## Primary sources

### CounterSpace: an executable two-dimensional reference

Simon Cozens's
[CounterSpace repository](https://github.com/simoncozens/CounterSpace/tree/01b33477225eb5fc7bedf93a090b5cd7dd0c812b) and
[notebook](https://github.com/simoncozens/CounterSpace/blob/01b33477225eb5fc7bedf93a090b5cd7dd0c812b/Spacing_with_countershapes.ipynb)
explicitly describe an unfinished spacing experiment. The
[implementation](https://github.com/simoncozens/CounterSpace/blob/01b33477225eb5fc7bedf93a090b5cd7dd0c812b/CounterSpace.py)
uses a reference-height mask, optional serif smoothing, concavity reduction, a pair-dependent counterspace mask and its
center of mass. Three Gaussian fields weight that space from the center, top and bottom, accounting for italic angle.
Eight bounded parameters are fitted with SciPy TNC against designed reference pairs; default pairs are `HH`, `OO`, `HO`,
`OH`, `EE`, `AV`. Placement searches for the reference's weighted score with minimum-distance bounds. The default raster
x-height is 90 pixels. The
[license](https://github.com/simoncozens/CounterSpace/blob/01b33477225eb5fc7bedf93a090b5cd7dd0c812b/LICENSE) is
Apache-2.0 for code and CC-BY-4.0 for images.

Unlike the current uniform wall average, the pair mask and spatial weights change the quantity being integrated. It
still equalizes a scalar score, masks internal counters and clips to a reference height; it does not automatically
resolve whole-shape or unequal-height concerns. The notebook discusses failures of simpler intermediate formulations.
That is evidence for testing those failure cases, not proof that the finished prototype fails identically.

### Learning to Kern: evidence for whole-shape and font-wide context

[Nakatsuru and Uchida, 2024](https://arxiv.org/html/2402.14313v2), sections 3–6, study pairwise and set-wise spacing
prediction using 2,558 proportional Google Fonts, split by family into training, validation and test sets. Their
set-wise Transformer receives pair embeddings derived from whole-glyph ResNet features and considers all 52 Latin
letters. Section 5 replaces these features with peripheral edge profiles while retaining the Transformer architecture.
Whole-image features perform better on their default-spacing prediction task. This supports investigating information
beyond walls; it does not prove that a particular internal counter causes the reported Literata judgments.

The labels are font-default spacing, not independent perceptual judgments. Images are normalized to a 256-pixel frame;
the reported pixel errors are not errors at our 16 px output size. Section 6 acknowledges limited control of spacing
intent and the need for expert subjective evaluation. No trained weights, small-Mono acceptance or hard collision policy
were verified here. The paper's publication license does not establish a software or model-weight license.

### YinYangFit: a provisional multiscale interaction model

Sebastian Kosch's [YinYangFit article](https://skosch.github.io/YinYangFit/) explicitly labels its account provisional.
It distinguishes texture, perceptual grouping and recognition, and proposes multiscale oriented responses and
pair-interaction costs. Its fitting proposal compares cost at a designed distance with costs at neighboring distances,
rather than requiring an unweighted gap average to match. These are model proposals, not established universal laws of
letter spacing.

There is
[Apache-2.0 reference code](https://github.com/skosch/YinYangFit/tree/609d17e8a6446ec4413a1b02a0768b8214d73333),
including a pair-distance search. Its filter bank uses NumPy and `gputools`/OpenCL; the code and article need separate
reproduction checks. The article's unfinished sections and free parameters make it a more involved first experiment than
CounterSpace. It is relevant as a second pair-interaction reference, not a ready replacement.

## What the current Literata evidence does and does not show

The retained [mechanical probe](../../out/diagnostics/contextual-spacing/perception-research/pair-mechanics.json) uses
the current capture at 16 px, `opsz=16`, `wght=400`, full optical and source kerning, neutral deliberate spacing. It
retains the capture hash and continuous, rounded, metric and emitted steps for all nine reported pairs.

- All nine have zero clearance-induced movement. Explaining their current placement as a collision-clamp problem is
  contradicted by this capture.
- `jo`, `pi`, `te`, `tp`, `OE` and `OR` widen by one pixel relative to metric placement. `yd`, `le` and `ip` retain
  their metric steps. This is a mechanical observation, not an optical verdict or a comparison with every historical
  model.
- `OE` and `OR` receive identical current targets and steps. The original papers permit this shared facing curve/stem
  relationship. Neither different internal forms nor a whole-image model guarantees that their ideal distances differ.
- Missing cavity-depth controls and reference categories are confirmed implementation omissions. Their contribution to
  each reported perceptual problem remains unproven. Neither separability nor x-height clipping alone demonstrates its
  cause.

## Bounded next experiment

1. Reproduce pinned CounterSpace outside maintained components, with isolated dependencies and its original parameters.
   First verify the reference on its own examples. Retain inputs, normalization, masks, parameters, timings and
   failures. Its SciPy dependencies increase experiment cost; they do not preclude offline table generation. A small
   WASM runtime need not run an offline optimizer. Portability and resource costs require measurement before a
   production decision.
2. Evaluate its reference-height and cavity policies before adapting our captures to it. Preserve source axes and scale.
   Keep the maintained rendered bitmaps unchanged. Explicitly identify source calibration geometry and delivered scoring
   geometry; using the same routine does not make those two geometries identical.
3. Fit font-wide parameters from a declared source reference set spanning straight, curved and diagonal forms. Keep the
   reported problem pairs out of fitting. Source spacing supplies style calibration, not a per-pair answer table.
   Fitting eight parameters to a few relative reference constraints can be underdetermined: check sensitivity to
   starting points, parameter bounds and held-out references. Abort an unstable fit rather than selecting one by
   Literata gains.
4. As a project adaptation, score feasible integer placements directly with the fitted pair score. Preserve the existing
   clearance rule initially, so measurement and collision-policy changes are not confounded. Direct integer scoring
   avoids assuming that the nearest rounded continuous solution minimizes a nonlinear perceptual score. Disclose
   infeasible targets, ties, search bounds and residuals. Do not add an unsupported half-pixel correction clamp.
5. Compare native-size words and the supplied presets across several fonts and neighboring sizes. Retain controls that
   separate target replacement, measurement changes and quantization. Require held-out reading assessment before
   replacing the current preview default. Shape transformations and texture healing remain out of scope.

The first experiment answers whether spatially weighted pair geometry improves the observations. It does not claim a
solved perceptual metric. If it cannot distinguish or improve the relevant cases, proceed to a whole-shape learned
scorer or the YinYangFit interaction reference rather than adding letter-specific rules. That larger work needs a
separate decision about training data, optical-size normalization, font-style control and independent assessment.

## Proposals excluded from this recommendation

An arbitrary ±0.5 px correction cap, per-pair intersection windows, and permitting diagonal contact are not derived
repairs for these observations. Intersection windows change normalization; clearance relaxation is irrelevant where the
guard is inactive. Likewise, neither Adobe's public documentation nor the inspected primary sources disclose Adobe's
complete optical-kerning algorithm. No reverse-engineered formula is asserted here. No newer source located in this
search established a validated drop-in solution for our 16 px Mono output.
