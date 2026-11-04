<!-- cspell:words yinyangfit argmin subpixel equidistance falloff monospace Yinyang microsite Kosch autofit reweighting reweighted nondecreasing electricbubble multiscale predeclared GlyphSeparation autowidth subadditive -->

# YinYangFit interactive control: spacing jump and non-monotonic "Tighter"

Research only, 2026-11-03 (corrected revision). **Decision: keep `yinyangfit-interactive-v1` an exploration; its
cohesion control must not serve as a "Tighter" control in the user tool.** That rejection is structural and supported:
nearest-value selection over the measured interior-extremum signal cannot promise monotone tightening, and the causal
probe below isolates the extremum in candidate-dependent attention reweighting. What is _not_ established is a ban on
all adaptation: a sourced field-integration spacing method, a feasible-branch selector, or an honest source-strength
control are different claims requiring their own evidence. This revision corrects four errors in the first report: a
false synthetic skip, a false universality theorem, a category error between correction strength and tightness, and
primary-source gaps behind the alternatives. Numerical evidence here describes mechanism only; optical status throughout
is **pending assessment** per the [evaluation rules](../evaluation.md#review-and-decision).

Evidence labels: **Verified** means inspected source or recomputed from shipped bytes this session. **Inherited** means
taken from the cited prior audit without re-verification here. **Inference** means a source-backed judgment. **Unknown**
means not established.

## Why the jump is huge, and why "Tighter" can widen

**Verified.** Three independent mechanisms multiply, and the label hides all of them:

1. **The label is a three-way bucket, not a measurement.** `spacingWord()` in
   `experiments/contextual_spacing/yinyangfit_interactive_v3_wiring.js` (lines 366–370) returns `"Standard"` exactly at
   the default cohesion `1.1`, `"Looser"` below, `"Tighter"` above. Grid positions `1.2` through `1.8` all read
   "Tighter", including the two largest adjacent steps (`1.2 → 1.4`, `1.4 → 1.6`). "Standard" is not Source either: at
   the default, Roboto 16 Mono line 3 already carries 23 non-metric pair moves (e.g. `TA:8→6`, `78:9→10`).
2. **Per-pair selection skips and reverses.** The choice rule (`choose_from_costs` in
   `experiments/contextual_spacing/yinyangfit_interactive.py`, lines 413–434) picks the integer step minimizing
   `|interaction − cohesion|` over five candidates, ties toward metric. The recorded curves are non-monotonic, so a
   rising target changes _which branch_ is nearest. Shipped-table values for Roboto 16 Mono at default reach/falloff
   (`out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/site/data/roboto-16-mono.js`, recomputed in
   `.../yinyangfit-interactive-control-research/findings.json`): `og` (metric 8, step 6 invalid by overlap) records
   `1.20333, 1.42101, 1.17998, 0.93619` across steps 7–10, so target `1.1` chooses 9 while target `1.2` chooses 7,
   skipping 8 entirely. `Th` moves 8 → 9 and `rt` moves 5 → 6 as the target rises — a stronger "tighter" set-point
   selecting strictly wider pairs.
3. **Whole-pixel accumulation over many gaps.** Each gap decides independently (`layout_text`, same module, lines
   546–575). Recomputing line totals from the shipped per-pair tables reproduces the orchestration file
   (`.../yinyangfit-interactive-orchestration/spacing-jump.json`) at all nine grid points, e.g. Roboto 16 Mono line 3:
   422 → 402 → 372 → 375 for targets 1.1/1.2/1.4/1.6. Dozens of ±1–2 px moves sum to large line-total jumps, and
   opposing flips cancel or invert: at 1.4 → 1.6, pairs such as `ni:6→7`, `mu:12→13`, `or:7→8` widen while `Mi:13→12`,
   `ef:7→6` narrow, netting +3 px on a "tighter" step. Ink widths in
   `.../yinyangfit-interactive-orchestration/spacing-jump-widths.json` (424/404/374/377 px) track the same shape.
   Line-origin totals describe advance sums, not visible ink width.

The coarse grid amplifies but does not create the effect. A continuous slider would fire the same rank changes, fewer at
once. Grid step `1.2 → 1.4` is twice its neighbors, which schedules two flips together.

## Selection arithmetic, corrected (Q1a)

**Verified — the genuine skip uses real data including its invalid candidate.** For `og` above, verified this session
with the existing `choose_from_costs`: at cohesion 1.1 the costs are `|1.17998 − 1.1| = 0.080` minimal, so 9; at 1.2 the
costs are `|1.20333 − 1.2| = 0.003` minimal, so 7. Rising target, skipped step, reversed direction. Step 6 is absent by
occupied-cell overlap at every cohesion, which compresses the feasible set against the domain edge.

**Corrected — the first report's synthetic demonstration was false and is retained as such.** `findings.json`
`synthetic_bump_skip` (`[1.10, 1.20, 1.42, 1.18, 0.94]`) chooses 6 at 1.1 then 7 at 1.2: one adjacent step, no skip, no
reversal. It is kept unchanged for provenance with a superseding `synthetic_bump_correction` key. Likewise the universal
claim ("any interior extremum forces skips") is false. Counterexample, verified with the same function: steps `[1, 2,
3]`, interactions `[3, 2, 3]`, metric 1, targets 1/1.5/2/2.5/3 yield `2, 2, 2, 1, 1` — monotone, no skip, despite the
interior minimum. **Sufficient demonstrated conditions**, not a theorem: a skip fires when the extremum reorders which
branch is nearest inside the swept target range _and_ the competing branches sit more than one step apart — exactly the
`og` 9 → 7 case over 1.1 → 1.2.

## What creates the bump: causal probe (Q1b)

**Verified — the bump is candidate-dependent attention reweighting, isolated on the unchanged scorer.**
`causal_probe.py` (same directory) imports the pinned module read-only and records per-step intermediates through the
module's own helpers; its grid setup mirrors `_score_geometry_uncached` lines 310–322 for measurement only and is not a
production rule. On shipped Roboto 16 Mono captures at default reach/falloff, recomputation from the captures matches
the shipped tables to 4 dp (e.g. `og` 1.2033/1.4210/1.1800/0.9362), so the probe dissects the same signal the UI selects
over:

- The **unweighted** bubble mean over identical background query sets is monotone decreasing and nearly flat (`og`
  0.1448 → 0.1442 → 0.1429 → 0.1410, −2.6% total; same shape for `Th`, `rt`). No bump exists before weighting.
- The **normalized** interaction swings ±20–35% with an interior maximum at the middle step in all three pairs.
  Numerator and denominator both peak there (`og`: 3.74 → 8.40 → 4.61 → 2.10 and 3.10 → 5.91 → 3.91 → 2.24), so
  attention concentrates at the bump step and weights high-bubble points — weighting, not mere rescaling.
- Factor split: equidistance-only aggregation is monotone for `og` (0.2307 → 0.1854) and `rt`, but retains a smaller
  bump for `Th` (0.1643 → 0.1666 → 0.1637 → 0.1569). Removing the oppose factor keeps the bump for `og` (1.2138 → 1.3560
  → 1.1452 → 0.9133) and `Th`, but removes it for `rt` (1.1814 → 1.1727 → 0.9976 monotone). Thus no one attention factor
  explains all three pairs; opposition is necessary for the observed `rt` bump in this ablation, but not for the other
  two.
- The fixed common-window probe preserves the three real-pair curves (maximum difference below `1.2e-9`), excluding
  window extent as a material explanation in these fixtures. Background counts grow linearly, but counts alone do not
  exclude changes in which points enter the background mask. The synthetic half-pixel probe shifts only the left bar,
  changing physical separation as well as sampling alignment; it is not a pure lattice-phase isolation. Neither mask
  membership nor lattice phase is ruled out by these tests.

**Plausible, source-backed:** the nearest-single-sample proxy discards support multiplicity, so one reweighted query
point can dominate. The author explicitly notes that nearest-point distance omits other nearby contour points that
contribute to grouping-cell activation
([distance-transform section](https://skosch.github.io/YinYangFit/#approximating-g-cell-activations-with-distance-transforms)).
**Unknown:** exact per-query shares of nearest-switching versus background-membership versus gradient discretization;
whether any oriented or multiscale formulation removes the bump on these rasters — our probe implements neither, so it
cannot speak to that. Reach/falloff sensitivity across all 16 shipped settings (`ablation_reach_falloff.json`) moves and
tilts the curve without removing the extremum (16/16 for `og`, `rt`; 12/16 for `Th`); that is parameter sensitivity, not
mechanism isolation, and the probe supersedes it as evidence.

## What the pinned sources actually specify (Q2)

- **Current YinYangFit JAX: no scalar objective exists (Inherited).** Per the
  [kerning-model audit](yinyangfit-kerning-model.md) (verified 2026-11-02, inherited here — live refs not re-fetched
  this session), zero-based cells 22–25 are distance/orientation maps with no pair cost or optimization, and the
  packaged engine's penalty fields return zeros (confirmed in the prior session at
  `out/diagnostics/contextual-spacing/yinyangfit/pinned-files/engine/__init__.py:150`). Its
  [algorithm chapter](https://skosch.github.io/YinYangFit/#models-and-cost-functions) _proposes_ minimizing
  distance-dependent cost fitted against designed distances — source-spacing imitation, not an optical optimum. Our
  attention-normalized aggregation plus exhaustive five-candidate argmin is our completion; JAX specifies no reduction.
- **Electric Bubble (predecessor): normalized interaction plus threshold-following search (Verified).** Directly
  inspected pinned snapshot `out/diagnostics/contextual-spacing/yinyang-alternatives/electricbubble/src/`:
  `autofit.js:67` computes `sum(attention·(leftBubble + rightBubble)) / sum(attention)` — the exact shape our scorer
  borrows — but its search is an 80-attempt overlap walk driven by the rounded residual (lines 25, 75), not exhaustive
  minimization; bubbles come from saliency-raised-to-22 convolved with an inverse-power kernel (`App.js:245–248`,
  `kernels.js:50–64` with a `|| 1` singularity guard); attention multiplies equidistance, gradient-angle, and mean-angle
  factors (lines 36–54); parsed `yFactors` never enter the attention product. No convergence or threshold-crossing
  guarantee is stated anywhere in the file — likely no proof exists, so the predecessor's walk guarantees **Unknown**.
  Our regularized kernel, nearest-sample proxy, strength-product weighting, and omitted vertical factor are disclosed
  departures (module docstring, lines 10–44).
- **Convolution of support versus our proxy.** Electric Bubble convolves full saliency fields with its kernel, so every
  ink point contributes to every bubble value. Our scorer replaces that with the single nearest occupied sample's
  coverage per query point — no integration over support. The interference discussion is context, not validation: the
  article documents
  [destructive interference in V1](https://skosch.github.io/YinYangFit/#destructive-interference-in-v1) and notes
  nonlinear (hyperbolic-ratio) activations can produce _gains_ in the gap despite it, so interior extrema are physically
  plausible in the author's framework. Plausibility does not validate our score reversals as optical: biological
  motivation never establishes that a wider pair is the right answer at a tighter set-point.
- **Historical Torch notebook: a real scalar scorer, but a different model (Inherited).** Per the kerning-model audit,
  its cells 9/13 loss cannot complete the JAX model; importing its reduction would be a cross-model transplant.

A cost with an interior minimum is legitimate; the defect is the _control–signal pairing_. A "tighter" control promises
monotone placement response, while nearest-value selection over a bumpy measured signal cannot keep that promise even
where the underlying field physics is defensible.

## Established alternatives, grounded in primaries (Q3)

- **Source-strength blend (already specified — not a novel follow-up).** The owning design's
  [placement rule](../designs/text-layout/contextual-spacing-and-healing.md#placement-and-ownership) blends metric
  placement toward a selected optical method with strength `o`: `signed_pixel_round(blend(metric, optical, o))`, plus
  the clearance guard. At `o = 0` output is Source-exact; at `o = 1` it is the full method. **Correction strength is not
  tightness, and the first report conflated them.** For fixed endpoints the blend moves each pair toward its own optical
  endpoint `d1`: pairs with `d1 > d0` legitimately widen as `o` rises. Gating "zero per-pair widening under rising
  strength except ±1 px rounding" would reject valid optical endpoints and mistakes a model preference for a control
  invariant. Three separate things need separate names: global density/tightness (a tracking-like offset), source-exact
  amount of optical correction (the `o` blend), and model-shape settings (which method owns the endpoint). The blend's
  own monotonicity is exact and needs no rounding exception: `round` is monotone nondecreasing (`a ≤ b ⇒ round(a) ≤
  round(b)`), `max(·, clearance floor)` likewise, so per-pair output is monotone in `o` with direction set by each
  endpoint's sign — plateaus and dead zones at these sizes, never reversals. A fixed-endpoint blend also never switches
  rank branches by itself; if the underlying shape target moved with `o`, that would be a second, separate two-control
  experiment.
- **Hu/Hersch shared-separation solve.** [Hu 1998, §4.4](https://lspwww.epfl.ch/publications/typography/sopfbsc.pdf)
  filters bitmap walls at ±45° and converts the inter-wall area deficit to a positioning distance by dividing by
  character height (units: pixels on the analyzed bitmap).
  [Hersch et al. 1995, pp. 85–88](https://lspwww.epfl.ch/publications/typography/ptgogf_95.pdf) calibrates a shared
  ideal from designed reference pairs (`nn`, `HH`, mean ideal for mixed case), and
  [Hersch/Betrisey US5768490A](https://patents.google.com/patent/US5768490A/en) adds the aperture construction with
  published relative-depth 0.21 and global height factor 0.25. Our candidate's control path (owning design, Hu/Hersch
  delivered-bitmap candidate): `continuous_step(pair) = shared_target − c(pair)`, blended with metric, signed-rounded,
  clearance-guarded. Rising shared target moves every pair's continuous step 1:1 — no pair-specific extremum exists in
  the construction — and rounding plus clearance floor are monotone maps. So per-pair monotonicity in the density
  control holds by constructional argument (project inference from the primary mechanism, not a published theorem), with
  disclosed branch points only: reference-class switches (`nn`/`HH`/mean), infeasibility fallback to metric,
  fixed-pitch/tabular safeguards.
- **FontForge outline estimator.** [FontForge's docs](https://fontforge.org/docs/ui/dialogs/autowidth.html) state the
  linearity assumption outright ("if you increase the separation by 3 em-units, the optical spacing will also increase
  by 3"), and its default `GlyphSeparation` routine returns an inverse-square-weighted average of per-height separations
  measured at adjacent bounding boxes, in design units; the pinned implementation
  ([autowidth2.c @ `c41bdb9`](https://github.com/fontforge/fontforge/blob/c41bdb922285f35defd1e1385adfd13bde1ab32a/fontforge/autowidth2.c),
  via the [target comparison](optical-pair-spacing-target.md)) rounds the weighted distance, with a `0.15 em` fallback
  when no lookup/font separation exists. Control path: estimate separation `S` at adjacent boxes, apply `kern = desired
  − S`. Same monotonicity argument as above, same disclosed branch points (min/max clamps, fallback, no-shared-band
  pairs). Our use of delivered-bitmap geometry with this estimator is a project adaptation; the linear mechanism is the
  established part.
- **Global density/tracking.** A uniform offset is exactly monotone and exactly pair-blind: a complement for overall
  color, never a fix for pair rhythm.
- **Proper oriented/multiscale perception modeling.** Unavailable as a completed mechanism: JAX has no objective, Torch
  belongs to another model, Electric Bubble's fit is unfinished and its walk has no stated guarantee. Any proposal here
  is new research, not adaptation.

**What the bounded blend experiment would newly establish** — the blend schedule itself is specified, so the novelty is
measurement, not invention: the retained Hu/Hersch endpoint's density, per-pair rounding/clearance residuals, and
plateau structure on the frozen corpus under a separated control — evidence the current corpus does not contain (all
existing tables run the interactive scorer). Its relevance to the YinYangFit request is the control half only: whether a
sourced method can deliver monotone, Source-exact pair-specific control. It says nothing about whether YinYangFit-style
perception is optically right; that stays future research. Strongest objection: the blend can limit the influence of a
wrong endpoint but cannot repair it. With the endpoint fixed, changing strength alone does not switch score branches;
changing model settings as well would be a separate experiment.

## Recommendation and validation gates (Q4)

Keep `yinyangfit-interactive-v1` an exploration. Do not complete or adapt its cohesion control for the user tool: the
failure is the control/signal pairing (nearest-value selection over an attention-reweighted interior-extremum signal,
accumulated independently per gap), now causally isolated rather than merely observed. But this rejects the _current
cohesion-as-monotone-tightness_ — supported — not every adaptation — not established. A practical control fallback is
correction strength against an independently assessed, fixed endpoint: sourced placement owns positions, the blend owns
strength, and optics are assessed independently. This does not repair the interaction scorer. Uniform tracking can
separately control overall density; it is pair-blind, whereas a reference-calibrated shared-target method still makes
pair-dependent placements. Explicit unknowns: optical validity of equal-area targets at 8–20 px; oriented/multiscale
bump behavior; predecessor walk guarantees; whether any threshold-following selector could be monotone on this signal.

**For continuing the requested perceptual-model research**, the next informative comparison is a small reproduction of
the predecessor's full-support field convolution against the current nearest-sample proxy, on frozen synthetic and real
pairs. The
[pinned Electric Bubble field construction](https://github.com/skosch/electricbubble/blob/31ce15a56429b67e2c759fcb625e78db3a17e9d3/src/App.js)
provides an implemented primary reference for that representation. Preserve its aggregation and search as separately
identified reference arms, and measure curves, choices, phase sensitivity and resource use before proposing a new
control. Convolution is not established as a cure: it may retain the bump, and it does not supply the missing current
YinYangFit objective. This comparison would test a model departure rather than merely damp its visible consequences.

**Separate optional control experiment** (requires owner-design update before any code): expose the already-specified
correction-strength control `o` against the retained Hu/Hersch-family endpoint on the frozen 13-case × 2-profile corpus,
with the interaction scorer out of the path. Model and control stay separated. Preserved invariants: Source-exactness at
`o = 0`, occupied-cell non-overlap, fixed-pitch/tabular safeguards, predeclared corpus. Explicit departures: none from
the published methods; the blend schedule is the declared project rule it already is.

**Gates before promoting that control (none tuned per glyph):** (1) per-pair blend output exactly monotone in `o` on the
frozen corpus — provable by the rounding/clearance argument, so zero exceptions; any violation rejects the
implementation, not the endpoint; (2) adjacent-setting line-total changes within an owner-agreed pixel budget (corpus
maximum adjacent jump today is 55 px across blocks; the Roboto 16 Mono block peaks at 41 px, its line 0 1.2 → 1.4 step
alone being 40 px); (3) endpoint optical assessment by the existing rules — mechanical checks plus independent visual
review, recording rounding/clearance residuals and unresolved pairs as pending rather than passing them as ±1 px
exceptions; (4) calibration and held-out texts frozen before scoring. Failure of the endpoint assessment rejects the
endpoint method, not the control.

## Corrections, limitations, provenance

Material corrections to the first report: the synthetic "skip" was a one-step move (kept, corrected); the universality
theorem is replaced by demonstrated sufficient conditions; correction strength ≠ tightness, with gates rewritten
accordingly; Hu/Hersch and FontForge claims now rest on the primary publications and pinned implementation above rather
than the owner design alone; the corpus maximum is 55 px (40 px describes one Roboto 16 transition); the design link now
points at [placement and ownership](../designs/text-layout/contextual-spacing-and-healing.md#placement-and-ownership).
JAX/manuscript facts are inherited from the 2026-11-02 audit, not live re-verified here; Electric Bubble code facts were
re-verified in the pinned snapshot this session. Gray-profile and small-size behavior is described from shipped tables,
not new captures. No glyph exceptions were added and none are proposed: numbers below never license per-pair tuning.

HEAD `240b372bc96027c60d286ef0b7113c4656a40609`; scorer `57cffdea02f...b68baf`, v3 app `61d8b7eb...a776`, wiring
`41c050f6...f42a` — all unchanged, hash re-verified after this research-only session.

Diagnostics (new, isolated; production/UI/data/baseline untouched):
`out/diagnostics/contextual-spacing/yinyangfit-interactive-control-research/causal_probe.py`, `causal_probe.json`,
`findings.json` (original keys preserved; corrections appended as new keys), `ablation_reach_falloff.json`,
`analyze_control.py`. Prior observations used as inputs, not rules:
`.../yinyangfit-interactive-orchestration/spacing-jump.json`, `spacing-jump-widths.json`, and the v3 `site/boot.json` +
`site/data/*.js` tables, plus `.../yinyangfit-interactive-v3/captures/roboto-16-mono.json` for the real-pair probe.
Commands: `python3 .../causal_probe.py`; `python3 .../analyze_control.py` (original run only).
