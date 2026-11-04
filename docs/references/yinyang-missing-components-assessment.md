# YinYangFit missing components: assessment

<!-- cspell:words Multiscale multiscale unvalidated inspectable yinyangfit -->

Research only, 2026-11-04. No code, scorer, UI, default, or calibration change. **Verified** = freshly read primary
source this session. **Inference** = analysis. **Unknown** = not established. Parent's framing stands: parts were left
out of the initial simplified model; later work repaired that approximation rather than completing YinYangFit.

## 1. The four omissions are real, and two are coupled

**Verified** in the pinned manuscript's [direct-approximation steps][direct]: V1 complex responses are summed over
scales, convolved with orientation-masked filter pairs using radial kernels `f1 = 1/r^k`, `f2 = 1/r^(k+1)` (`k ≈ 2`),
then combined as oriented distance `d = (T∗f1)/(T∗f2)` and arc strength `k = (T∗f1) ⊙ d^(k+1)`. Pair grouping uses four
quantities: `|dL−dR|`, `kL·kR`, `dL+dR`, and the orientation pair `(oL, oR)`.

1. **Oriented kernels — missing.** Upstream convolves scale-summed V1C tensors with angularly masked filters; B2 applies
   radial kernels to nearest-sample distances plus a post-hoc gradient-opposition factor — not direction-blind, but no
   filter bank. **Lost:** direction-selective support.
2. **Ratio estimator — missing, coupled to (1).** The ratio converts oriented convolutions into distance and strength;
   without (1) there is nothing to take the ratio of. **Lost:** distance grounded in pooled directional evidence.
3. **Multiscale responses — missing.** Upstream [V1C modeling][v1] builds a width×height×scales×orientations tensor with
   scale weighting for contrast sensitivity. B2's `feature_scale` is an interaction reach (radial knee and window
   radius); `proximity_falloff` is decay shape. Neither weights scales, and bitmap enlargement is resampling, not
   multiscale filtering. **Lost:** scale-dependent grouping (small vs. large structure competing).
4. **Multiple contour support — missing as representation, misstated as rendering.** All ink, holes, and strokes are
   rendered in the raster. What is missing: each query reads one nearest ink sample with that sample's coverage, so
   support multiplicity is never integrated. **Inference:** convolution itself integrates multiplicity, so no separate
   vector-contour parser is needed; the fix is filtering, not outlining.

The [distance-transform alternative][edt] is the closest upstream cousin: it assumes one dominant grouping scale and
additive interactions, and explicitly notes nearest-point and orientation limits. B2's single-scale window is the same
class of compromise, disclosed in the scorer docstring.

**Inherited implementation evidence, current JAX vs. historical Torch:** the pinned JAX notebook (cells 22–25) shows
maps with no scalar cost or training objective, and the packaged engine's penalty fields are stubs — consistent with the
[kerning-model audit][audit]. The historical Torch notebook has a real scalar loss, but it belongs to a different model;
porting it does not complete the JAX design.

## 2. Why they were omitted

**Verified** from the scorer docstring: the fast no-training probe was an explicit simplification ("disclosed
departure"), borrowing only the `q` / `q+1` pairing in radial form. Later arms repaired that probe's aggregation; no
oriented-field rebuild was authorized. No deeper causal history is claimed.

## 3. Should we add them? Order and smallest step

**Parent judgment:** implement in stages. First test orientation-masked ratio fields with a single-scale V1C input and
no scalar placement score on synthetic bars, curves and multiple-stroke shapes plus frozen `um`, `og`, `AV` and `To`
pairs in Mono and Gray. Then add multiscale V1C responses and scale weighting. Finally declare and test the scalar
reduction separately. Training is not required to compute the filters; fixed or user-controlled weights remain possible
project hypotheses needing evaluation. Prior Electric Bubble full-support and scale studies are **exclusions of those
variants**, not proof the oriented model fails.

Existing preliminary no-training experiment: radial-only `r^-2` / `r^-3` ratio on synthetic bars with declared guards
(piloted in [control design][controls]: finite, gap-varying, 31–44% far-field NaN at support 4). Explicit TODOs: origin
singularities, zero denominators, support/discretization rules; overloaded `k`; channel/spatial pooling, normalization,
cross-pair selection; calibration against designed distances is source imitation, not an optical optimum.

**Success/stop:** require finite values where the ratio is supported, explicit unsupported regions, independently
checked fields, predictable bar-distance responses, padding safety and integer co-translation consistency. Measure
raster-phase sensitivity rather than promise subpixel invariance. Stop if the available fields cannot distinguish the
tested geometry or numerical support artifacts dominate. A field-only pilot has no placement minima to assess; later
scalar and optical checks need their own declared criteria. **Rust/WASM:** cached glyph-field convolution is feasible
but strictly larger than the current kernel; cost it only after the field pilot passes. No claim these additions fix
`um`/corner residuals or optical quality.

**Strongest objection:** an honest oriented field over a still-unvalidated placement rule only makes wrongness
inspectable — the endpoint has no optical standing yet.

**Parent recommendation:** retain B2 as the comparison while developing the oriented fields across contrasting inputs.
Judge any scalar cost as a new hypothesis, not an upstream-prescribed completion. This assessment does not authorize
implementation or replacement of the live model. [direct]:
https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/docs/source/algorithms.markdown [v1]:
https://skosch.github.io/YinYangFit/#modelling-activations-of-v1-cells [edt]:
https://skosch.github.io/YinYangFit/#approximating-g-cell-activations-with-distance-transforms [audit]:
yinyangfit-kerning-model.md [controls]: yinyang-only-control-design.md
