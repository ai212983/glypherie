<!-- cspell:words yinyang YinYang yinyangfit argmin multiscale inspectable -->

# YinYang-only control design: probe verdict

Research only. **Parent decision: retain the direct YinYang parameter explorer; do not add the tested strength blend.**
Changing reach/falloff changes the model's preferred spacing, which is expected parameter behavior. It does not
establish a monotone Tightness control or optical usefulness. Muse recommended a per-pair strength experiment (B-P1),
but its synchronized jumps and Gray baseline discontinuity do not resolve the reported usability problem.
Oriented/ratio/multiscale completion (C) needs field-first groundwork before a scalar cost can use it. No endpoint from
any other method is proposed or substituted. Optical status throughout is **pending assessment** per the
[evaluation rules](../evaluation.md#review-and-decision).

**Verified** means recomputed from shipped v3 bytes this session. **Inherited** means taken from the cited audit. Probe:
`experiments/contextual_spacing/yinyang_control_probe.py`, evidence
`out/diagnostics/contextual-spacing/yinyang-control-design/probe.json`, tests
`experiments/contextual_spacing/tests/test_yinyang_control_probe.py` (6 pass). Choice replication verified 344/344
against shipped `spot.default` (86 pairs on each of four tables); `og` reproduces the recorded 9-at-1.1 → 7-at-1.2 skip.

## Source model versus project completion

The upstream YinYangFit JAX model defines no usable control. Verified this session in the pinned source
(`yinyangfit/source/YinYangFit.ipynb`, cells 22–25: distance/orientation maps and pair-agreement visualization, no
scalar cost or optimization) and the packaged engine (`pinned-files/engine/__init__.py:143–152`: penalty fields return
zeros). The [kerning-model audit](yinyangfit-kerning-model.md) owns this gap. Everything that turns fields into a
placement — attention-normalized aggregation, desired-value search, five-candidate argmin — is our completion, named
HYPOTHESIS in the scorer module. A strength blend on top is therefore composition **on** YinYang output, never
completion of its perceptual objective; it must be judged as control honesty, not as model validation.

## (A) Direct tuning: model parameters, not monotone Tightness

At default reach/falloff over all 26 tables (2172 pair-cases, **verified**): 642 pairs (30%) carry a strict interior
extremum; 854 cohesion paths skip more than one step between adjacent grid points; 355 reverse direction (e.g. `og` path
over 0.4–1.8: `10,10,10,10,9,7,8,8,8`). Separately, 1617/2172 (74%) change answer when reach/falloff move at fixed
cohesion: those two knobs define the model's preferred endpoint rather than adjust toward a fixed one. This is their
intended role in a model-parameter editor, not sufficient grounds to reject them. Cohesion cannot promise monotone
tightening, and "Lower/Higher" labels cannot fix branch re-ranking. Keep the parameters editable in the experimental
page; freeze them only when studying a separate fixed-endpoint blend. Optical usefulness remains unassessed.

## (B) Fixed-endpoint strength: composition probe, not adopted

Endpoint fixed at the shipped default (cohesion 1.1, reach/falloff 2.0 — the current YinYang answer, quality assessed
separately). Strength `o` blends each pair from its metric step toward its fixed YinYang-chosen step. Endpoint deltas
are ±1/±2 px. Positive and negative deltas both occur — strength is **not** tightness, and no monotone-optical theorem
is claimed.

- **P1 per-pair rounding** (round each blended step, accumulate whole pixels): per-pair direction is exactly monotone in
  `o` (rounding and the clearance floor are monotone maps; tested). Plateaus, never reversals on the sampled corpus.
  Many ±1 corrections flip near `o = 0.5`, so line totals jump together (worst adjacent line-total change 28 px on the
  `o` grid). Guard clamps fire on 19/76 lines (rounded blend lands on overlap-invalid steps). Gray P1 snaps up to 17
  px/origin just above zero: the explicit Source bypass is exact at zero, but per-pair-rounded sums cannot reproduce
  fractional Source pens. P1 is exactly representable in the maintained whole-pixel advance/adjustment API with integer
  pen ([live-spacing policy](../../crates/generator/API.md#live-spacing-api)).
- **P2 fractional pen** (accumulate continuous steps, round at draw): spreads line-total changes (worst adjacent 4 px).
  The sampled counts of glyph origins that move are mixed: Mono 417 vs 351 events; Gray 1370 vs 1535. Counts alone do
  not measure maximum displacement or perceptual smoothness. Gray P2(0) is Source-exact with no bypass, but P2(1)
  deviates from the absolute endpoint by up to 7 px/origin (correction-delta vs absolute endpoint — the two must never
  be silently interchanged). P2 contradicts the maintained integer-pen policy, so it is diagnostic-only; exact blocker
  cited above.

Interpolation cannot rescue a bad endpoint — endpoint quality and control behavior stay separate assessments. **Parent
judgment: neither tested blend is ready for the UI.** P1's Gray snap is caused by switching from fractional Source
accumulation to per-pair-rounded layout; it is not evidence of instability in the YinYang score. P2 is a different
layout hypothesis, and its correction-delta endpoint is not the old absolute endpoint. Pair corrections are
text-independent; rendered rounded differences can depend on the preceding fractional pen. Changing font size selects a
separate captured table; display magnification does not change layout.

## (C) Oriented/ratio/multiscale: field first, no cost yet

Precise missing pieces (**verified**): ratio estimator `d = (T*f1)/(T*f2)` with angularly masked kernels and `q ≈ 2`,
arc-strength with undeclared overloaded `k`, all lacking origin singularity, zero-denominator, finite-support and
discretization rules; no channel/spatial pooling, normalization, cross-pair selection, or calibration (the manuscript
proposes fitting to designed distances — source imitation, not an optical optimum). Smallest source-backed step,
executed in the probe on synthetic bars: radial-only `r^-2`/`r^-3` ratio field with declared guards and independently
unit-sum-normalized kernels — finite and gap-varying (mid-range e.g. 0.81–2.09 at gap 4), but 31–44% NaN far-field at
support 4, showing the uncovered finite-support regions concretely. The normalization also changes the ratio's distance
scale. This is a radial illustration, not a reproduction of the oriented estimator. It supplies no scalar aggregation
and must not become a cost. **Possible next C step:** one orientation-masked kernel field on a single frozen pair, still
cost-free. No Torch-loss transplant, no training, no invented biology.

## Boundary

The current page retains its three YinYang-derived parameters and Source comparison. This probe authorizes no additional
UI or model change. Further work on the actual oriented estimator must separately declare its unresolved sampling,
denominator and aggregation choices. Strongest objection: a perfectly honest control over a wrong endpoint only makes
wrongness inspectable — currently the endpoint itself has no optical standing, so even B-P1 serves assessment, not
users.

Provenance: scorer `57cff…b68af`, v3 app `61d8b7…a776`, boot default combo `c74`, HEAD per `start.json`. Prior numbers
reused by reference: line totals 422→402→372→375 (`yinyangfit-interactive-orchestration/spacing-jump.json`);
reach/falloff sensitivity mechanism in
[yinyangfit-interactive-control-research](yinyangfit-interactive-control-research.md).
