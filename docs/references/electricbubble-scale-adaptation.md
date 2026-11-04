<!-- cspell:words fullfield Kluwer predeclared retuned reweighting yinyang yinyangfit electricbubble ppem covariances Lindeberg tfjs -->

# Electric Bubble scale adaptation

Research only, 2026-11-03. **Result: negative for this partial parameter-resizing rule.** Resizing the declared filter
supports and patch covariances reduces response magnitudes and walk separations, but strict interior extrema roughly
double on identical collision-free domains (core 52 → 77 over 461 shared steps; extended 151 → 306 over 1,285 shared
steps), and only 40 of 130 extended cases select an interior nearest-target candidate on the shared collision-free
domain. Such a selection does not establish that the target is reached. This parameterization does not produce a smooth
spacing signal or establish complete scale normalization. Optical quality throughout is **pending assessment** per the
[evaluation rules](../evaluation.md#review-and-decision). No UI, default, or method change follows; target calibration
was explicitly not performed.

Evidence labels: **Verified** means execution or recomputation from shipped bytes this session. **Inference** means a
source-backed judgment. **Unknown** means not established.

## Rule and why it is general (design-first)

The owning design subsection
([scale adaptation](../designs/text-layout/contextual-spacing-and-healing.md#electric-bubble-scale-adaptation)) was
written before the model code. Reference measurement is the em at the author's render size: `App.js` fixes `fontSize:
72` with `scalingFactor = fontSize / unitsPerEm`
(`out/diagnostics/contextual-spacing/yinyang-alternatives/electricbubble/src/App.js:24-25,93-98`, **Verified** in pinned
snapshot `31ce15a`). The scale ratio is `r = ppem / 72` with `ppem` from the frozen capture's `size_px`. The rule is one
parameter-resizing hypothesis, not a search: filter supports scale by `r`, explicit patch covariance entries by `r²`,
and other constants remain unchanged. Support windows round to the nearest even integer (minimum 4), preserving the
TF-SAME asymmetric-pad and kernel-center conventions the full-field port verified against real `tf.conv2d`. Native
gradient kernels remain unchanged. Their common magnitude factors would cancel in idealized angle ratios, but the
source's additive epsilons prevent general invariance: a host counterexample changes interaction from 4.1783 to 3.4518
when gradients alone double. Agreement on the original fixture is not a proof. Native-grid sampling is retained. The
numeric `desiredInteraction` target stays at 0.01 without a complete unit-transport derivation; its closest candidates
are measured, never retuned. An x-height reference was rejected: the author states no x-height normalization.

The rule is general in using the same declared font-size ratio for every pair. The author's render size grounds that
ratio; scale-normalized operators provide motivation, not a proof for this nonlinear pipeline
([Lindeberg 1998](http://www.diva-portal.org/smash/get/diva2:1392833/FULLTEXT03.pdf)). The inverse-power bubble kernel
still uses native pixel distances, unnormalized convolution sums retain their sampling-density dependence, and the
envelope covariance, clips and gradient epsilons are not transported consistently. This is therefore a partial resize,
not a demonstrated dimensionally complete coordinate normalization. The author's article also distinguishes nearest
distance from evidence contributed by multiple neighboring contour points
([Approximating G-cell activations](https://skosch.github.io/YinYangFit/#approximating-g-cell-activations-with-distance-transforms)).

## What was run (paired domains, frozen inputs)

- **Unchanged baseline:** the frozen full-field port at verbatim author parameters; `roboto-16-mono` 11-pair run reused
  by reference, three further 11-pair core runs executed with the frozen module (port hash in each manifest). The
  130-case extended raw arm is the frozen full-field corpus.
- **Normalized arm:** new `experiments/contextual_spacing/electricbubble_scale.py`, importing the port unchanged; only
  scaled parameters/kernels and the filterSize-dependent walk seeding differ.
- **Synthetics:** parallel, asymmetric and support-multiplicity bar fixtures at small scale and exact 2x
  integer-upsampled geometry (no interpolation policy), steps doubled to preserve physical separation; true
  integer-translation control shifts both glyphs. The adapter rebases the row origin, so its input arrays remain
  identical; no subpixel lattice-phase experiment was performed.
- **Corpus:** Roboto/Literata 16 Mono/Gray × 11 pairs (core), then the cheap 5-pair subset across all 13 captures × 2
  profiles (130 pair-cases). Raw and normalized arms share identical steps, adapter padding, overlap mapping and walk
  rules; extrema count only on the shared valid collision-free mask (host-assessment definition). Target inspection is
  separate from scale: interior versus edge minima, guard effects, walk terminations. No calibration arm was run.

## Measurements (Verified)

| Domain                  | Shared steps | Raw extrema | Scaled extrema | Interior vs 0.01 (raw → scaled)            |
| ----------------------- | ------------ | ----------- | -------------- | ------------------------------------------ |
| Synthetics (6 fixtures) | 66           | 9           | 13             | ranges compress ~5–10x, counts do not fall |
| Core (44 cases)         | 461          | 52          | 77             | 2 → 4                                      |
| Extended (130 cases)    | 1,285        | 151         | 306            | 2 → 40                                     |

Interior counts are nearest-target selections on the shared collision-free mask, not successful target matches. The
initial summary used each arm's unguarded domain (core 5 → 8, extended 6 → 45); the host corrected the analysis and
retained the original summaries under `electricbubble-scale-orchestration/`.

The extended raw count (151) reproduces `host-assessment.json` exactly on identical masks, which corroborates the
analysis code. Scaled extrema are signal, not jitter: core shoulder minima are mostly far above numerical noise, and the
float32 diagnostic agrees to 1.5e-05 worst curve delta with identical walk terminals and identical invalid sets on all
44 core cases. Determinism reruns are byte-identical in results (wall-clock timings vary, as expected). Reference
identity holds: at `r = 1` the scaled rule reproduces author parameters and port fields/curves to 0.0. Integer
translation produces identical rebased arrays (0.0 over 12 steps); this says nothing about subpixel phase. Scaled walks
bracket the target (far-field ~0.0008 below it, near-contact above) and terminate at steps ~15–24 versus raw ~53–67, but
only 6 of 44 scaled walks meet tolerance; the rest limit-cycle at ±1. Cost is negligible and smaller than raw: cold ≤
0.31 s, warm ≤ 0.13 s, traced peak ≤ 7.3 MB (raw ~60 MB).

## Limitations (Unknown unless noted)

- The nonlinear inverse-power-root transform and 50-clip have no scale-transport derivation in the source; they run
  unchanged and their output range is measured, not preserved by argument.
- The envelope entry `1000 * filterSize` mixes a length with a variance, so no dimensionally unique scaling exists; the
  stated choice is one project reading.
- At `r = 0.111` (8 px) supports hit the 4 px quantization floor while covariances shrink 81x, so kernels go spiky on
  the coarse lattice — a declared mechanism, not a tuned excuse.
- Integer co-translation invariance does not cover sub-pixel rasterization phase; delivered cells are frozen and their
  rasterization is untouched by design.
- The js-anchor was not rerun with mapped parameters (its harness takes no parameter override); non-unit grounding rests
  on hand-derived kernel values and `r = 1` anchor parity instead. Complete non-unit scale covariance was not
  established.

## Strongest objection and judgment

The strongest objection is that coarse sampling and the incomplete dimensional mapping may dominate the result. Small
quantized supports and attention reweighting are plausible contributors; their causal shares were not isolated. This
test therefore rejects neither complete scale normalization nor the broader YinYangFit model.

**Falsifiable judgment:** this scaling hypothesis does not improve the measured response properties that block control
(non-monotone responses remain despite nearer target selections), so it must not be adopted as a spacing normalization.
Stop work on this rule variant. No calibration or selector experiment follows automatically. The next product step is
native-size visual assessment of the separate fixed-endpoint control prototype; that does not validate these fields. No
claimed cure and no optical recommendation follow from extrema alone.

Provenance: scale module, evidence driver and focused suite are new under `experiments/contextual_spacing/`; evidence
under `out/diagnostics/contextual-spacing/electricbubble-scale/` with input hashes in `inputs.json`; raw baselines
either reuse `electricbubble-fullfield/` bytes or record the frozen port hash. Focused suites:
`test_electricbubble_scale.py` includes host regressions for epsilon sensitivity and shared-domain target selection;
`test_electricbubble_fullfield.py` remains unmodified.
