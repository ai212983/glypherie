# YinYang oriented-engine contract (frozen-model runtime)

<!-- cspell:words rustfft bindgen graylevel lnorm lslate yinyang yinyangfit multiscale predeclare nonfinite unphysical pairpx ntaps nonpositive cnorm argmin retargeted autogain supremum -->

Owner leaf: `experiments/contextual_spacing/oriented_engine/`.
Owning design: [contextual spacing](../../../docs/designs/text-layout/contextual-spacing-and-healing.md#yinyang-stage-3-score-v2-hypothesis-experiment)
(stage 1, stage 2, stage 3 sections), frozen sources
`yinyang_oriented_fields.py`, `yinyang_multiscale_fields.py`, `yinyang_oriented_score.py`.
This contract owns the Rust/WASM runtime surface only. It does not change the
reviewed page, its controls, or any maintained crate.

## Model identity

- `model`: `yinyangfit-oriented-engine-v1` (runtime of the frozen stages).
- `score_model` (new, experimental): `yinyangfit-local-energy-v2` (Class-L
  local normalization; see the local-energy section). The v1 G2 scorer is
  retained as a frozen oracle/code history only — no UI selector, no
  fallback, no wiring to the reviewed page. `version()` reports both.
- `search`: `yinyangfit-search-v2` (placement-search policy, versioned
  separately from the model; tables and caches reject other policies).
- Field math is the frozen corrected SCORE-v2 path: stage-2 COMBINED
  `T = sum_s w_s C_s` before the oriented ratio, notebook-primary strength
  `c = U1*d^(q-1)`, manuscript `a = U1*d^(q+1)` diagnostic only.
- Baseline defaults (exact frozen values): `q = 2`, `kappa = 4`,
  `sigmas = [0.75, 1.0606601717798212, 1.5, 2.1213203435596424, 3.0]`,
  uniform weights, `R = 12`, `eps = 1e-12`, `tau = 0.5`, 8 V1 / 16 directed,
  `U2` floor for the weak-band diagnostic `1e-6`, `C*` grid and TIE-v2 rule
  unchanged. G2 score units `[0, 128]` (`G2_BOUND = 128`).

## Local-energy v2 (experimental, not adopted)

- **Frozen mapping.** The normalizer window radius `normalization_radius`
  is frozen at **12**, separately from the field kernel reach `R` and the
  falloff `q`. This separation is a role hypothesis (source-inherited
  reference `R = 12`, not an optical default): local normalization must not
  silently generalize with a user's reach setting. A caller changing field
  `R`/`q` still works across the current guardrails (`R 1..=64`,
  `q 0.25..=32`, `normalization_radius 1..=64`; Standard/Extended/penalty
  field gates unchanged) and is verified by the R/q parity gates — no
  control is disabled silently. If a strong sourced reason ever couples the
  normalizer window to the field reach, that change needs a predeclare and
  the parent's judgment first; corpus gains never retune it.
- **Cache keys.** Per-glyph local-energy maps live inside the glyph entry
  and die with it (structural allocation-identity invalidation on any
  field change). Maps are keyed `(strength, normalization_radius)` inside
  the entry; the entry key already carries dataset, capture SHA,
  codepoint, geometry bytes and the params hash. The params hash mixes
  BOTH model identities, so old cached curves/maps never validate under
  the new identity.
- **Abstain reconciliation (intentional new rule, declared here).** G2
  abstains on no-shared-support only. Class L abstains with an explicit
  reason: `no_shared_support` (empty both-union, same as G2) or
  `zero_local_evidence` (both-supported pixels exist but no eligible
  normalized contribution: all local energies non-positive/nonfinite or
  all strengths zero, including float-underflow cases). A valid zero
  agreement (`gl == 0` with eligible terms, e.g. all `c` products zero
  with healthy energies) is ELIGIBLE, not abstain — selection treats it
  like any other value. Float underflow to zero is value-level
  indistinguishable from genuine zero agreement and rides the same way.
  A finite negative or nonfinite `gl` with scored terms is unphysical
  rounding fallout (`gl >= 0` is the model property: facing weights,
  strengths, and kernel values are all nonnegative) and abstains as
  zero local evidence with `gl` reported 0. The pair-level fallback
  reason follows the per-step evidence reasons, not the gated count,
  so fully guard-skipped support reports zero local evidence rather
  than no shared support. Target 0 / unreachable / near-TIE behave through
  the unchanged TIE-v2 machinery. The search policy (TIE over
  valid-and-not-abstained, `occupied_cell_overlap` > no-support ordering)
  is otherwise preserved.
- **Bound.** `G_L <= sum_ab F(a,b) |both_ab|` (geometry-dependent, from
  the center-inclusive per-pixel term `<= K <= 1`). Checked by
  `check_local_bound`, never by the G2 `[0, 128]` clamp.
- **Confidence.** L/R-symmetric `support_mass_*` (raw strength sums,
  never gl-unit normalized mass) over the support union plus
  `support_share = |union| / |scored domain canvas|`, common-support
  only, `support_weak_mass_*` alongside in the same raw units.
  Informational only — never a selection gate, never reads EL. Unit
  discipline: `support_union_pairpx` counts canvas pixels (support-only);
  `both_supported_pairpx` on steps/maps counts energy-eligible scored
  pair-px (per facing pair). The two never compare. Canvas invariance
  holds for masses and steps on shared steps; `support_share` is
  domain-relative by construction.
- **Numerics.** Local energies are stable nonnegative direct positive
  summation of the center-inclusive disc — same formula, padding, and
  centering as the retired FFT path, no FFT rounding, no clipping, no
  floor. Sums of nonnegative f64 terms in fixed order are nonnegative
  by construction and bitwise identical across build profiles and
  targets; center inclusion holds up to the stated summation bound
  (`ntaps * eps * max`, derived from the tap count). Per-step
  `conditioning_shortfall` and `skipped_nonpositive` are still reported
  (both read 0 on all parity fixtures). `local_energy_direct` (tap-outer
  Complex order) is the independent positive-sum reference: production
  maps agree with it within `2 * ntaps * eps * max` (unit-pinned).
  Well-conditioned agreement with the existing FFT pilot corpus is
  documented, not assumed: R12/R24 notebook at 1e-9, manuscript at
  1e-8 on all shipping profiles. Denominator eps, guards, and formula
  are unchanged — a numerical implementation correction, not new math.
- **Scored-pixel counts.** `both_supported_pairpx` counts support
  overlap gated by positive-finite local energies on both sides
  (pilot parity); support-only overlap minus scored is `skipped`.
  The honest bound stays support-only (matches the reference exporter).
  Pixels with pooled energy below the pinned FFT/direct agreement
  floor (`1e-9`, unit gates) are guard-unstable across implementations:
  the exact-zero rule then includes them on one side only. Parity
  resolves this by mechanism, never by clipping: R12 (frozen default)
  has zero such pixels and agrees at `1e-9` with exact counts; R6
  agrees at `1e-5` (bars, 15 measured guard pair-px) and `3e-5`
  (real curves, worst measured `7.8752e-6` at roboto-16-mono um step
  10 R6 notebook on current bytes — the FFT-era `1.02e-5` is retired),
  with band-aware TIE choice agreement intact. First-pass `max_term_cosine` diagnostics use
  support-only overlap and can diverge from the pilot's gated terms
  exactly where `skipped > 0`; scored sums and maps are gated on both
  sides.
- **Components.** `lnorm` (per-channel `c/sqrt(EL)`, zero-guarded,
  notebook) and `lslate` (per-pixel channel-max of `lnorm`) are explicitly
  local-normalized projections, distinct from raw `cnorm`/`slate`.
  Manuscript strength stays score-path-only.
- **Admitted scope (measured, not inherited).** Parity covers 169
  native steps (184 wasm32, which counts its choice checks) at frozen
  field reach 12, not a whole parameter band: `q = 2` notebook at 1e-9
  and `q = 3` manuscript at 1e-8 conditioned (power amplification,
  same class as the G2 `tol_for_q` precedent); normalizer 6/12/24 with
  6 conditioned (guard-zone mechanism) and 24 clean. Those R6/12/24
  probes varied the NORMALIZER window on frozen field reach 12 — they
  say nothing about field reach 6/24. Field reach values outside 12,
  `q` outside {2, 3}, and normalizer values outside {6, 12, 24} are
  unverified for L — the existing page slider and numeric ranges
  (reach 1..32, falloff 0.25..16) are G2 ranges and do not transfer. The R6 per-curve argmin agreement is an observed
  fixture property, not a selection certificate. The normalizer stays
  fixed at 12: no caller control is removed or silently retargeted,
  and any future reach control wired to L must be re-verified per
  setting. Conditioning flags (`skipped_nonpositive`,
  `conditioning_shortfall`) travel with every step so callers see
  exactly where the verified behavior ends.

## API surface (native and WASM share `lib`)

- `Engine::new(EngineParams)` — validated params (finite, invariant guards;
  invalid input errors, never silently clamps).
- `load_glyph(dataset, capture_sha, codepoint, w, h, left, top, cover)` —
  caller supplies exact capture cover (`0/1` Mono, `p/7` Gray); the engine
  copies the buffer. Replaces any entry whose capture/params/geometry bytes
  differ; key identity is never codepoint-only.
- `R` is the square kernel half-width: taps over `[-R, R]^2` with radial
  `1/r^q` falloff and origin zeroed — never a circular crop or a hard
  Euclidean cutoff. `R` is integer (`1..=64` guard); `q` is real precision
  (`0.25..=32` guard). Bands stay provisional until the config-sweep bench
  lands; defaults are frozen parity.
- `score_pair(dataset, left, right, metric, deltas, tau, strength)` — integer
  steps only; overlap (occupied-cell) steps are invalid with
  `occupied_cell_overlap`; contact allowed with face/corner counts; per-step
  `g2`, `raw`, `floor_share`, `raw_floor_share`, `both_supported_pairpx`,
  plus TIE-v2 `minimizing`/`chosen-lowest-index` selection over supported
  (valid, non-abstained) steps only. Unsupported steps abstain and never win;
  with no supported step the metric is retained with `fallback_reason`
  (`occupied_cell_overlap` or `no_shared_support`).
  Caller deltas are 1..=512 steps. No cohesion, no
  optical default, no B2 fallback.
- `search_domain(dataset, left, right)` — geometry-derived ordered-letter
  domain for `score_pair` deltas (`{lo, hi}` steps ascending with
  `lo = max(ink-order, 1)`, `{blank: true}` for blank sides, `{empty: true}`
  for disjoint padded rows). Search version `yinyangfit-search-v2`
  (see `lib`), also reported in `version()` beside the model.
- `contribution_map(...)` — normalized per-pixel terms summing to the chosen
  step `G2`. `glyph_component(dataset, codepoint, kind, channel, scale)` —
  one requested component over the padded lattice; never bulk-copies all
  16 channels. Kinds: raw `confidence_notebook` / `arc_strength` /
  `distance` / `u1` / `u2` / `supported` / `t_combined` / `c_scale`, plus
  the exact normalized G2 factors `cnorm` (`c/sqrt(E)`, zero where `E` is
  zero/unsupported) and the `slate` projection (`max_o cnorm`, single array
  in `[0,1]`, the parent-preferred glyph context view with per-glyph fixed
  `E`, never per-frame autogain). Raw `c` is unbounded; UI display gain
  stays a fixed global constant from measured corpus peaks.
- `clear_dataset(dataset)`, `clear_all()`, `cache_sizes()`, `cancel()` —
  bounded LRU memory; cancellation flag is polled in score loops.
- WASM (`wasm` feature, `wasm-bindgen`): `YinYangEngine` class with the same
  calls over typed arrays (`Float64Array` cover, `Int32Array` deltas) and
  JSON for scalars. Errors surface as thrown strings. No fetch: the page
  worker instantiates from inlined bytes (`initSync({ module: bytes })`).

## Dynamic params (genuine generalization, tested apart)

- `q`, `kappa`, `R`, per-scale `sigmas`/`weights`, `tau`, `strength` are
  parametric in the formulas. Strength exponents derive from the active `q`
  (`q-1` / `q+1`); the frozen `q = 2` exponents are never reused under a
  custom `q`. Custom configs are validated and covered by dedicated tests
  against an independent reference harness; defaults stay bitwise to the
  frozen corpus agreement bounds.

## Cache and determinism rules

- Field cache key: `(dataset, codepoint, capture_sha, stage, params_hash,
  geometry_hash)`; energy cache key adds `strength_variant` and the field
  allocation identity. Same-input rerun is repeatable within stated
  field-path bounds; cross-padding/perturbation agreement is a measured
  stability bound, not a bitwise claim.
- Eviction is LRU-front with load-only recency (scoring/map reads never
  refresh): while over 512 entries, or over the 256 MiB soft owned-payload
  target with more than the 32-entry keep-floor resident. The target is soft:
  when the most recent 32 entries exceed it, their payload stays resident.
  Accounting covers covers, field lattices, self-energies and materialized
  local-energy maps (length-measured, structural overhead excluded);
  transient caller-held clones are not cache-owned. Oversized singles still
  build. Identity, math, and recency are unchanged by eviction.
- Observables: `cache_sizes` reports `glyphs`/`lru` plus cumulative
  `payload_bytes`, `builds_fields`, `builds_el`, `evictions` (per engine
  instance since construction; clears drop live payload only). These never
  enter params_hash, model identity, tables, or score outputs.
- Gray `p/7` enters linearly at the caller buffer; Source fractional
  accumulation/rounding stays in the page worker, not the engine.

## Validation gates (all must pass; no silent relaxation)

- Native vs frozen Python corrected corpus (142 pairs x 5 steps, both
  strength variants, tau spot checks, full TIE-v2 choice grid, custom q/R
  axes, reference map, slate peaks): default geometry and every Standard
  config (`q <= 4.2` and `R <= 24`, any combination) agree within `1e-9`
  relative `G2` (three-way worst `4.4e-10` on the sampled envelope).
  Extended configs within `q <= 16` / `R <= 32` carry
  `conditioning_reduced_precision`: relative `G2` agreement measured worst
  `5.4e-5` at `q8-R32` over 14 sampled cases (empirical maximum, not a
  proven supremum); TIE-v2 choices agree on all 4046 fixed-grid
  verification points, while 323/799 reference-constructed exact-midpoint
  flips resolve differently, so near-tied placements can move. `q > 16`
  or `R > 32` is held (rejected, never clamped). Any choice drift is
  reported with margin/tie detail, never absorbed. Score values are never
  clamped; nonfinite is reported.
- Frozen oracle fixtures (`score-oracle/`, `reference-review/`) copied
  read-only into the runtime evidence dir; expected values reproduced by
  independent re-derivation where stated (facing sum 128, tiny manual G2).
- Edge gates: blank (valid steps, abstain, TIE-v2 lowest-index pick),
  zero-support abstain, overlap invalid / contact allowed with frozen
  face/corner counts, ties (explicit lowest-index), Gray `p/7` end to end,
  padding/shared-step translation (shared-step G2 identical across sweep
  widths), cache identity (full frame, never codepoint-only) and dataset
  release, cancel responsiveness with buffer safety, contribution-map
  reduction (`sum == G2`), `facing_sum == 128`.
- Near-floor support: `both_supported_pairpx` agrees exactly except
  single-pixel U2-floor flips (observed `<= 30` of `~700k`, G2 unaffected),
  recorded per step, never absorbed into the score.
- Perf gate: TRUE workload of 142 pairs x 5 candidates (cold) plus
  cohesion-only re-derive timing, native and Node WASM; no one-pair timing.
  The byte budget above with the 32-entry keep-floor and 512-entry ceiling
  bounds live payload; `clear_dataset`/`clear_all` drop it.

## Non-goals

No font parsing, no capture generation, no page/UI edits, no B2 scoring, no
training, no optical claims. `uncertainty_not_certified` travels with every
score report.
