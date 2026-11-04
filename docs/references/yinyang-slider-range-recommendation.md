<!-- cspell:words yinyang xcheck nonfinite ndistinct reflattens -->

# YinYang slider range recommendation

Research note, 2026-11-04. Recommends replacement slider bands for the three YinYang prototype controls. Changes
nothing: defaults stay `1.10 / 2.0 / 2.0`, the frozen scorer is untouched, optical status stays **pending assessment**.
Evidence: `out/diagnostics/contextual-spacing/yinyang-range-study/` (`brackets.json`, `steps.json`, `xcheck.json`) from
driver `experiments/contextual_spacing/yinyang_range_study.py`, which scores through the frozen core (in-band parity
rechecked `True`) across 10 contrasting pairs, 4 primary datasets, and all 13 cases x2 profiles (26 captures). Current
sliders (`0.40..1.80/0.10`, `1..4/0.5`, `1..4/0.5`) are superseded as sampling conveniences, not derived limits.

## Mathematical domain (from the formula, not from sampling)

The kernel is `g / (1 + (r/scale)^q)` with coverage `g` in `[0,1]`. `bubble_l + bubble_r` is therefore in `[0,2]`, and
attention is a product of nonnegative factors (equidistance, opposing-gradient, strengths), so the attention-weighted
mean — the interaction — lives in `[0,2]`. Cohesion is the set-point for that mean, so `[0,2]` is the exact natural
interval, matching the frozen validator. Reach must be positive (division by `scale`); reach `0` is excluded because the
formula divides by it. Falloff `q = 0` is finite but flattens the kernel toward a constant (no selectivity); `q < 0`
stays finite under numpy yet inverts the documented near/far meaning, so it is rejected by policy, not by arithmetic.
Large reach saturates bubbles toward `g`; large `q` approaches a binary near/far step — both stay finite (zero
errors/nonfinite across every bracket), so caps are UX tradeoffs, never validity limits.

## What the brackets measured

Varied one control at a time at defaults `(1.1, 2.0, 2.0)` plus loose `(0.4, 4.0, 1.0)` and tight `(1.8, 1.0, 4.0)`
anchors; 10 pairs x 4 datasets = 40 choice-slots per setting. Adjacent-setting changes (default anchor): reach
`0.25→0.5→1→2→4→6→8→12` moved 5/3/25/25/6/3/5 slots; falloff `0.25→…→16` moved 3/14/16/10/5/2/1/0/3 slots. No hard
saturation: reach `8→12` still moves `HH`/`ll` under defaults (10/40 under the tight anchor); falloff `12→16` still
moves `AV`/`ya`/`nn`. Interaction-span widths explain the ends: reach `0.25` spans shrink to median `0.087` (min
`0.0013`, far below the proposed cohesion step at some columns) versus median `0.50` at reach `2`; reach `12` reflattens
to median `0.068`. Falloff `16` spans stay strong (median `0.96`): the high-`q` tail is live, only sparse. Cost is real:
reach `12` costs ~12x per evaluation vs reach `2` (window radius `6·scale+4` = 76 px). Full-corpus check (260 slots):
`q4→q6` changes 0–3 pairs per capture, with changes in 19/26 captures including 8 px, italic, and script — `q6` is
established live, `q10`/`q12`/`q16` probed finite with decaying activity. The only fallbacks anywhere are rouge-script
`AV` occupied-cell overlap: placement policy, not numerics.

Step sensitivity: exact cohesion switch boundaries (1260 over 400 columns, range `0.017..1.940`, p5 `0.179`, p95
`1.725`) show grid `0.10` misses 60/1660 exact regions (3.6%), `0.05` misses 10/1660 (0.6%, all narrower than `0.05`),
`0.02` misses 1, `0.01` misses none. Dense reach sweeps: step `0.5` skips one measured narrow window (`To` at 3.25–3.5);
`0.25` retains every sampled choice on the quarter-pixel reference. The finer `0.10` comparison used nearest quarter
samples, so it is not independent evidence for behavior between quarter samples. Aligned falloff grids over the
recommended `0.5..10` band: step `1.0` misses choices in 3 of 8 Mono curves; `0.5` misses none of the choices in the
quarter-step reference. These checks cover 12 curves per axis and do not prove finer sampling cannot find more changes.
Current min `0.40` excludes the low-score-end choice in 130/400 columns (32%); min `0.20` in 45/400 (11%); max `1.80`
excludes the top placement in 26/400 (6.5%), max `2.0` in none. Keep all three mappings linear: choice-run widths
already vary `0.25–2+` in linear space and no measurement supports a log scale; uniform steps stay predictable.

## Recommendation

| Control    | Min    | Max     | Step   | Default | Why                                                                                                                                                                                                         |
| ---------- | ------ | ------- | ------ | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cohesion   | `0.00` | `2.00`  | `0.05` | `1.10`  | Full validated interval; excludes zero placements, and `0.05` misses only 0.6% of exact regions (all `<0.05` wide). 41 stops.                                                                               |
| Reach (px) | `0.50` | `6.00`  | `0.25` | `2.0`   | Retains every choice seen in the quarter-pixel reference; above `6` changes become sparser and evaluation more expensive. Values above the old validator band require the explicit range adapter. 23 stops. |
| Falloff    | `0.50` | `10.00` | `0.5`  | `2.0`   | Retains the choices in the quarter-step reference over this band. The parent selected `10` over Muse's initial `8` recommendation for tested upper-tail headroom while keeping 20 slider positions.         |

Retain the existing defaults; this study provides no optical basis for changing them. Rejected: reach max `4` (`4→6`
moves 6–8/40 — live); reach max `8/12` (travel plus ~12x eval cost for ≤5/40 moves per doubling — numeric-entry
territory); falloff max `4` (`q4→q6` moves pairs in 19 of 26 captures — a cap at the user's request would pretend the
response ends where probing shows it continues); falloff max `12/16` (the tail stays finite and active, but changes are
sparse in these probes; leave it available through numeric entry). No saturation knee establishes a unique cutoff at
`10`; this is a measured working-range tradeoff, not a validity bound. Uncertainty: Gray profiles respond weakly to
falloff (several `ndistinct=1` dense curves) — reach and cohesion carry Gray exploration; high-`q` Mono moves are
mechanically verified, optically unassessed.

## Numeric entry and implementation notes

Direct entry must accept at least two decimals and preserve entered precision, validate against guardrails — cohesion
`[0,2]`, reach `[0.25,12]`, falloff `(0,16]`, all probed finite — and report invalid values (`reach ≤ 0`, `q ≤ 0`,
non-finite) with messages, never silent rounding or clamping. Note the scaling implication for whoever builds the grid
(not decided here): 23 reaches x 20 falloffs = 460 geometry columns vs today's 49, with per-column cost growing with
reach (window radius `6·scale+4`). Widening falloff first is cheaper than both at once. Old reports and current grids
keep their identities; this note does not re-derive them.
