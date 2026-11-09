<!-- cspell:words yinyang yinyangfit electricbubble fullfield autofit saliency saliencies relu equidistance subpixel argmin reweighting predeclared headlessly roundoff nonfinite Dtype Kosch tfjs ndarray numjs -->

# Electric Bubble full-field reproduction

Research only, 2026-11-03. **Result: negative at unchanged author parameters.** Independent execution of the pinned
source supports the port's numerical reproduction, but the full-field pipeline still has non-monotone distance responses
on delivered bitmap inputs. On identical collision-free placements across 130 pair-cases, the source has 151 strict
interior extrema versus the proxy's 73. Its declared target is below the interaction range tested near metric spacing,
and its walk selects much larger separations outside that tested range. This does not isolate the effect of full-support
integration: saliency, attention, scales and search also differ between the methods. Scale mismatch is a plausible
explanation, not an established cause. Optical quality throughout is **pending assessment** per the
[evaluation rules](../evaluation.md#review-and-decision).

Evidence labels: **Verified** means original-code execution or recomputation from shipped bytes this session.
**Inference** means a source-backed judgment. **Unknown** means not established.

## Formulation (verified in pinned source)

Reference `out/diagnostics/contextual-spacing/yinyang-alternatives/electricbubble` (`31ce15a`), executed headlessly
under pinned `@tensorflow/tfjs 0.15.3`:

- `src/kernels.js:50-64`: `electricBubbleKernel` is `1/(dx²+dy²)^11` (power 22), center cells exactly 2048, `|| 1`
  singularity guard.
- `src/kernels.js:8-47`: anisotropic oriented DOG/Gaussian saliency kernels (`hfs = filterSize/2`, no `-0.5`).
- `src/App.js:179-254`: ink saliency `relu(bias + conv) * raw` (background exactly 0), whitespace saliency plain `conv`,
  combined saliency raised to power 22, support convolution, `initialStrength / min(50, wsc^(-1/22))^2` transform with a
  `Number.MIN_VALUE` floor (0 in float32), `[1,-1]` convolution gradients. Constructor defaults (lines 27–56) are
  preserved verbatim, including `desiredInteraction: 0.01`.
- `src/autofit.js:36-67`: attention is equidistance × angle-difference × mean-angle only; `yFactors` are parsed
  (line 23) and never applied. Interaction is the attention-normalized bubble sum — the shape the proxy borrows. The
  walk (lines 25–80) steps integer overlap by `round(grad) || sign` toward `0.01 ± 0.001`, max 80 attempts, with the
  duplicated `bubble1` bound preserved. No convergence guarantee exists.

## Arms and adapters

- **A (proxy):** frozen `yinyangfit_interactive.py` (sha256 asserted in tests), called unchanged at default
  reach/falloff.
- **B (source):** `experiments/contextual_spacing/electricbubble_fullfield.py`, plus the independent js-anchor that
  executes the byte-identical `kernels.js`/`autofit.js` and `App.js` minus its JSX gallery (render stub only; snapshots
  verified by hash) with delivered cells injected as `glyphData`. No TFJS or YinYangFit objective was invented.
- **C (not run):** no representation-only ablation was implemented. Arm B changes the complete field and attention
  pipeline; the comparison cannot attribute a difference specifically to full-support versus nearest support.

Input adapter (predetermined, recorded): delivered cells at exact `0/1` or `p/7`, author's 2 px canvas slack, union-row
canvas height, `padWidth = 64` (contain the 60 px support). Compatibility record: TF SAME is correlation with
`pad_before = (K-1)//2` (asymmetric for even K); `tf.pow` keeps negative bases positive at integer exponents; the walk
uses half-up rounding with the falsy-`-0` branch; float64 primary with a named float32 rerun.

## Reference parity (verified)

| Stage                        | Check                               | Observed                                     |
| ---------------------------- | ----------------------------------- | -------------------------------------------- |
| Kernels pre-transpose        | port vs builder math                | exact (0.0)                                  |
| Kernels post-transpose       | port vs original execution          | ≤ 5e-9 abs                                   |
| SAME alignment, even kernels | port vs real `tf.conv2d` probe      | 2.8e-14                                      |
| Saliency (ink/whitespace)    | port vs original execution          | ≤ 6e-7                                       |
| Bubble + gradient fields     | port vs original, 6 synthetics      | ≤ 2.2e-5 abs                                 |
| Curves                       | port vs original, 3 synth + 22 real | ≤ 1.1e-8 synth, ≤ 4.2e-4 real (≤ 1e-4 rel)   |
| Walk terminal                | port vs byte-executed walk          | exact on 14/14 (distance, overlap, attempts) |
| Anchor determinism           | node rerun, sha256                  | byte-identical                               |

A rejected FFT convolution path is recorded in code: at ~1e19 dynamic range, float64 FFT roundoff (~1e3) swamps true
far-field outputs (~1e-27); exact direct correlation is used. No NaN/Inf fields occurred in any run (14-glyph core: 0
nonfinite; floor hits ~52% far-field, cap hits near-ink — both retained author behavior, verified in the anchor's
float32 too).

## Comparison evidence (verified)

Frozen pairs `og, Th, rt` plus contrast set `nn, oo, HH, av, To, al, ri, se` (predetermined), Roboto/Literata 16
Mono/Gray core; 5-pair subset (`og, Th, rt, nn, oo`) across all 13 cases × 2 profiles (130 pair-cases); author-scale
synthetic bars (10×44).

- **Response extrema:** over metric ± 8 px, restricted to contiguous steps valid in both arms with no occupied-cell
  overlap, the 130 pair-cases contain 73 proxy extrema and 151 source extrema across 1,285 shared placements. Roboto 16
  Mono contains 10 versus 24 over 11 pairs. Counts use strict neighboring inequalities with no amplitude threshold; 150
  of the 151 source extrema have both shoulders exceeding 0.1% of the local maximum magnitude. These describe response
  shape, not optical quality or the number of control reversals. The original summaries counted each arm's own valid
  domain (75 versus 544), including overlapping source placements; those totals are not a matched-domain comparison.
  `host_assessment.py` and `host-assessment.json` retain the corrected calculation. Author-scale synthetics have smooth
  monotone tails beyond near-contact for parallel and asymmetric bars; the double-bar fixture retains near-contact
  extrema (14.3 → 20.4 → 13.5) before its smooth tail.
- **Selections:** with the author's declared 0.01 target, source-exhaustive picks the domain edge on 8/11 core Mono,
  11/11 core Gray/Literata pairs, 93/130 corpus — the target is below the delivered interaction range (0.15–15 at metric
  ± 8), so these are constrained boundary selections, not evidence of interior target matches. No invented matching
  target was substituted; curves are reported as curves.
- **Walk:** all 130 corpus + 33 core walks end `tolerance_or_attempts` outside the tested metric ±8 domain (e.g. Roboto
  Mono `og` metric 8 → terminal step 58). In-regime author-scale walks converge to tolerance (0.0093 vs 0.01). The
  walk's ±1 steps near tolerance also form limit cycles (synthetic smoke: 79 attempts oscillating before stopping).
- **Pair-step totals** over the 11-pair core list (metric total 86): proxy 86, source-exhaustive 132, guarded 157, walk
  terminals averaging ~59 per pair. This list is not a continuous rendered text, so these sums are diagnostics, not
  measured line widths. The large separations and missed targets prevent treating these outputs as ready for use.
- **Dtype:** float32 rerun agrees with float64 to ~1e-6 on curves with identical walk terminals and identical invalid
  sets (all geometric `slice_out_of_range`, never numerical). `Number.MIN_VALUE` handling is not the failure.

## Resources (verified, exact workload)

Python port, 11-pair core: cold prepare 0.2–1.1 s, warm scoring 0.2–0.5 s, traced peak 61–67 MB, process RSS 184–353 MB.
Original-code anchor on the same workload: ~1 s wall, 233 MB peak RSS. Both easily feasible; cost never gates this
comparison.

## Verdict and next decision

**Restoring the complete predecessor pipeline at unchanged author parameters did not produce a smooth spacing signal on
these inputs.** Independent-source parity and the placement-coordinate mapping support this bounded negative result.
They do not establish that the nearest-support approximation is harmless, or that full-support integration cannot help
after an appropriate adaptation. The two arms differ in several stages and use different feasible sets unless explicitly
restricted as above. Do not adopt this parameterization as a spacing endpoint or reject full YinYangFit from this
predecessor comparison (its JAX model has no scalar objective; this test cannot speak to it).

**Strongest objection:** scale may dominate — the 20/60 px filters accompany 72 px source renders, and the larger
synthetics have smooth tails. Size, shape, padding and sampling have not been independently isolated. A deterministic,
dimensionally sourced scale adaptation would be distinct from fitting parameters to individual glyph outcomes; neither
has been tested here. Any follow-up needs a declared scaling rule and comparison domain before implementation.

**Next decision:** the field-adaptation question remains open. A fixed-endpoint correction-strength control remains a
separate bounded option for predictable interaction, subject to assessing that endpoint; it would not validate either
field model or imply that every pair tightens. This experiment changes no user-facing page or spacing default.

Provenance: HEAD `240b372bc96027c60d286ef0b7113c4656a40609`; proxy
`57cffdea02fc0f0fffcbacba5151bfc7f8e8a72320611c3fdb11183915b68baf`; reference snapshot hashes in
`js-anchor/snapshots.json`. Commands in the
[experiment README](../../experiments/contextual_spacing/README.md#electric-bubble-full-field-reproduction). Focused
suite: `test_electricbubble_fullfield.py` (16 tests); neighboring `test_yinyangfit_interactive.py` still passes
unmodified.
