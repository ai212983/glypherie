<!-- cspell:words Hersch Hu Nakatsuru Uchida Kernagic Letterspacer sidebearings sidebearing Changyuan Parametrisable André Gürtler Seiichi midpoint scanlines Bézier -->

# Filtered-wall spacing

## Question and recommendation

Can a sourced whitespace measurement address the raw FontForge estimator's disproportionate emphasis on near-facing
serifs? Use a bounded Hu–Hersch filtered-wall candidate, retaining the FontForge methods as controls. The
[owning design](../designs/text-layout/contextual-spacing-and-healing.md#filtered-wall-comparison) specifies the
selected numerical, reference-window and clearance policies. This is a placement experiment, without outline
deformation.

The retained Literata 16 px/400, font-default `opsz=12` Mono diagnostic exposes the original proxy's limitation: `01`
and `12` approach the same calibrated score while their average same-row gaps differ substantially. For `12`, about 93%
of the weight comes from seven bands near the baseline, not the whole letter height. `01` has two diagonal contacts at
the tightened placement. These are observations of the retained capture, not universal properties of those pairs.
FontForge's regularized inverse-square weights have no mathematical singularity; their strong local bias and
normalization at adjacent bounding boxes explain the discrepancy. Calibration alone does not validate the measurement or
perception.

## Published foundations

[Hu 1998, §4.4, printed pp. 88–91](https://lspwww.epfl.ch/publications/typography/sopfbsc.pdf) describes leftmost and
rightmost bitmap walls. Empty scanlines use the opposite horizontal bounding-box edge. Concavities are filtered with
±45° lines; the area between filtered walls is compared with an ideal area. Dividing the area difference by character
height gives a horizontal correction. The thesis states linear complexity after rasterization. It also names
`VisualDepthLimit` and `MinSpace`, but does not supply a complete algebraic filtering specification or universal
parameter values.

[Hersch et al. 1995, printed pp. 85–88](https://lspwww.epfl.ch/publications/typography/ptgogf_95.pdf) transforms
outlines to remove visually hidden cavities and limit cavity slope and depth. It calibrates designed reference spacing,
distinguishes stem/curve classes and case, and increases spacing when needed to prevent overlap. Its 0.25-pixel minimum
is a grayscale contour rule; it does not prescribe a one-pixel blank column or forbid diagonal Mono cell contact.

A discrete unit-slope formalization of Hu's wall filtering is:

```text
Lf[i] = min_j(L[j] + abs(y[i] - y[j]))
Rf[i] = max_j(R[j] - abs(y[i] - y[j]))
mean_gap(d) = d + mean(Lf_right - Rf_left)
area(d) = window_height * mean_gap(d)
```

Two sweeps compute each envelope in linear time on a uniform grid. Physical x/y units must agree. The formulas are a
project formalization, not recovered author code. A common class window prevents pair-specific overlap heights from
changing normalization. Source references and produced forms must use the same measurement. Numerical midpoint sampling
of continuous outlines and full pixel cells needs resolution-convergence evidence. This subset omits Hersch's full
cavity-depth and stem/curve model; there is no sourced basis for silently assigning a 0.25-height depth cap. Mixed-case
mean gaps and ASCII `00` calibration remain declared project adaptations.

Equal-area solving can request a placement that touches or overlaps ink. A separately disclosed whole-bitmap clearance
constraint adapts the published minimum-space principle. Its residual must remain visible: unchanged shapes may make an
equal target infeasible. The strict Mono closed-cell rule, including diagonal contacts, is an explicit conservative
project policy rather than an exact reproduction of either paper.

## Other approaches considered

- [HTLetterspacer](https://github.com/huertatipografica/HTLetterspacer/tree/b4ad60bd36284f87edf9f2145d38bbf87b2e9909)
  and its [author tutorial](https://letterspacer.htfonts.com/tutorial/en.html) measure visual sidebearing area inside a
  reference height with configurable cavity depth. This is relevant supporting practice, but individual sidebearing
  fitting does not itself solve pair-specific clearance. The reference is GPL-3.0; no code is copied here.
- [Kernagic](https://github.com/hodefoting/kernagic/tree/30be68c06a7bf6010d26eefd45ee9504d1239f44) explores stem-rhythm
  spacing. Its stem/grid assumptions are less direct for the reported facing-cavity problem. This does not establish
  that it universally fails on curves. The reference is GPL-3.0; no code is copied here.
- [Nakatsuru and Uchida, Learning to Kern, 2024](https://arxiv.org/abs/2402.14313v2) estimates spacing with pairwise
  neural networks and a set-wise Transformer, evaluated on roughly 2,500 Google Fonts. Adopting it requires trained
  weights, an inference/dependency decision and validation on small Mono images. The publication does not establish a
  hard collision guarantee. Machine learning is not inherently nondeterministic or impossible in WASM; those were not
  sufficient reasons to reject it. The untrained geometric method provides the smaller experiment that can be inspected.

## Verification boundary

Analytic rectangles, cavities, missing rows, translated/scaled/reversed curves, unequal heights, an independent
quadratic-time filter oracle, and brute-force bitmap contact checks establish the implemented mathematics. Corpus
sampling convergence and comparison tables establish bounded mechanical behavior. Neither proves Hu parity or optical
acceptance; native-size reading assessment remains necessary.

## Bibliography

- Changyuan Hu. _Synthesis of Parametrisable Fonts by Shape Components_. EPFL thesis 1905, 1998, §4.4.
- Roger D. Hersch, Claude Betrisey, Justin Bur and André Gürtler. _Perceptually Tuned Generation of Grayscale Fonts_.
  IEEE Computer Graphics and Applications 15(6), 1995.
- Kei Nakatsuru and Seiichi Uchida. _Learning to Kern: Set-wise Estimation of Optimal Letter Space_. arXiv:2402.14313v2, 2024.
