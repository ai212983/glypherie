# YinYang raster-spacing model repair: cause and recommended general fix

<!-- cspell:words reweighting yinyang heldout Chebyshev thresholding Predeclared predeclared PREDECLARE multiscale nonfinite argmin softmax yinyangfit autofit ppem estimand reimplementation Predeclaration -->

Research only, 2026-11-03. No live-scorer, engine, UI, default, capture, table, or doc change follows. Parent owns
orchestration and final judgment.

**Plain-English cause.** At Roboto 16 Mono `um`, cohesion 1.10 / reach 2 / falloff 2, the tightest candidate (step 6,
touching) scores 1.188 while the one-column-gap step 7 scores 1.551, so the nearest-to-cohesion choice lands on the
touching step — 2 px tighter than metric. The score is an attention-normalized mean over a candidate-dependent
background point set. At step 7, just **9 query points** (one gap column × 9 rows, 0.44% of the background set) carry
**87.8% of the attention mass**; at step 6 those points are on-ink, the mask drops them, the attention denominator
collapses 7.4× (8.02 → 1.08), and the surviving far points score low. Gap-strip exclusion at step 7 reproduces step 6
almost exactly (1.196 vs 1.188): mask membership explains ~93% of the 0.363 bump; reweighting/discretization among the
1965 shared background points explains the residual ~0.026 (~7%). The parent's "gap disappears so the background measure
moves elsewhere" is directionally correct as the dominant mechanism, but the precise story is attention concentration on
9 vanishing points plus denominator collapse — and a smaller second bump mechanism (attention concentration at
non-contact steps, visible at reach/falloff corners) survives the repair below.

**Independent parent check.** The one-line mask replacement reproduces 147 sampled candidate values exactly. Recounting
the recorded default corpus confirms 664 strict interior extrema become zero and 265/2260 choices move. The path code
below counts only adjacent nonzero turns; removing plateaus before counting gives 395 baseline reversals, still zero for
B2. This does not establish correctness across the current slider range: an additional targeted 96-case check (four
pairs, four datasets, six settings including falloff 4/10, reach 6/12, and exact off-grid values) has 34 cases with
interior turns. Roboto 16 Mono `og` already turns at reach 2 / falloff 4. This sample is not a population estimate. A
non-face-contact candidate can change by about 0.068 under B2, so equality away from touching must not be asserted. Raw
host checks are in `out/diagnostics/contextual-spacing/yinyang-model-repair/host-verification.json`.

**Recommendation.** Keep B2 as the next experimental correction for the disappearing-support mechanism, rather than a
complete fix or an optically accepted replacement. Do not integrate anything yet. As the smallest falsifiable next arm,
adopt **ARM-B2: drop the on-ink query mask** — score the same attention-weighted mean over the full query window, with
on-ink points entering at r = 0. It has zero new parameters, leaves validity/metrics/glyphs untouched, changes the score
support, and at default settings removes every strict interior extremum in 2260 valid pair-cases (baseline 664; heldout
confirmed with no retuning) with zero cohesion-path reversals (baseline 385). It repairs `um`, `og`, `Th`, `rt`, and
`nn` alike. Pair it with a **guard only as a diagnostic flag** (report newly-touching choices; do not forbid them — the
enforcing guard moves 21% of corpus choices and is a policy change, not a signal repair). Stop/adoption gates in §8.

Evidence labels: **Verified** = executed or read this session. **Inherited** = cited prior audit without re-verification
here. **Inference** = source-backed judgment. **Unknown** = not established. **Proposed** = ARM behavior/wording for a
change that does not exist yet.

## 1. What was frozen and reproduced (Verified)

- HEAD `240b372bc96027c60d286ef0b7113c4656a40609`; frozen scorer SHA
  `57cffdea02fc0f0fffcbacba5151bfc7f8e8a72320611c3fdb11183915b68baf` (asserted in-repo); v3 compute port hash
  corroborated by the visualization audit (independent numpy/JS agreement to 0.0, Inherited).
- `um` replication on the frozen scorer, Roboto 16 Mono capture: metric 8; steps 6–10 interactions 1.1882341721625547 /
  1.5509044617315109 / 1.2602921758396037 / 0.9876263670788356 / 0.7813392390566823 (exact match to the brief); costs
  .088/.451/.160/.112/.319 → chosen 6 with boundary hit; step 6 has 9 face + 16 corner contacts and 0 occupied overlap
  (contact permitted); gap column count 0 at step 6 vs 1 at step 7; gap-strip (y −9..−1) attention mass .878 at step 7,
  0.0 at step 6 (no query positions); mean orientation .30878 vs .91814; weighted distance sum 3.5718 vs 2.1768;
  attention totals 1.077 vs 8.022.
- Baseline recomputation matches all 26 shipped v3 tables at the default setting index to 4 dp (checked `01` at sf index
  14 = reach/falloff 2.0/2.0); corpus below recomputes from captures, never from tables.

## 2. Geometry semantics and bug classification (Verified)

- Query points are integer ink-plane lattice points (`x = left + col`, `y = top + row`); ink samples sit on the same
  lattice. `dist == 0` means a query coincides with an ink lattice point — that is the on-ink mask, not an area
  integral. Occupied cells are unit squares on the integer lattice (`contact_counts`/`_occupied`); overlap = shared
  cells (hard failure), face/corner contacts = Chebyshev-adjacent cells (diagnostic, permitted). Touching is not
  occupied overlap — correctly distinguished in code.
- Gray uses delivered `p/7` coverage linearly through the nearest-sample lookup (no thresholding); contact still tests
  `cover > 0`, i.e. binary contact semantics on fractional cells (disclosed modeling choice, unchanged).
- Classification: **objective pathology in the scorer's aggregation**, not a visualization, port, wiring, or UI bug. The
  pixel pipeline is Inherited-verified correct (brute-force agreement to 0.0; 86/86 table agreement); our probes run
  under the frozen scorer's own helpers, so the bump is the model's, not its display.

## 3. Predeclared hypotheses and single-factor verdicts

Predeclared in `PREDECLARE.md` before any repair probe (research-design rule).

- **H1 (support + normalization) — confirmed as the dominant cause (~93%).** Gap-strip-excluded step-7 interaction =
  1.196 vs full step-6 = 1.188 (Verified). Shared-background-point restriction gives 1.171 (step 6) vs 1.197 (step 7):
  residual 0.026 of the 0.363 bump (~7%) from reweighting / gradient discretization among shared points (Verified).
  Nearest-side flip share is 1.6% — nearest-switching is not the driver (Verified).
- **H2 (opposition-gradient discretization as sole cause) — dead for `um`.** Factor split (Verified): equidistance-only
  aggregation is monotone (0.2315 → 0.1623); oppose-only bumps (0.4326 → 0.4608 → …); strength-only bumps;
  oppose-removed (`eq × strength`) still bumps (1.175 → 1.413 → 1.199). No one attention factor is necessary for `um`
  (contrast: in the prior `og/Th/rt` probe, oppose removal killed the `rt` bump — mechanism varies by pair; the common
  root is candidate-dependent support _and_ weights).
- **H3 (query-window extent) — dead.** Fixed union window across steps reproduces all five interactions to 6 dp
  (Verified); far-field weights are ~0. Integer co-translation (+5 px) reproduces to 0.0 (Verified); subpixel phase is
  untestable on frozen integer-lattice cells by design (Unknown).
- **H4 (nearest-single-sample proxy) — open, not tested here.** The 9-point / 88%-mass concentration is consistent with
  missing support integration, but the full-support predecessor still bumps at author params (Inherited negative
  result), so H4 alone is insufficient. No new full-support arm was built (would be an independent design, not a minimal
  repair).
- **H5 (denominator instability) — partly addressed.** ARM-B1 (fixed denominator `C` = metric-step attention sum) makes
  things _worse_ (discovery extrema 333 → 513; `um` swings to 0.228/2.215/1.260/0.574/0.218) and is **rejected** by the
  predeclared gate (ii). ARM-B2 fixes the _support_ instead: same weights and same per-candidate denominator, but the
  query set no longer vanishes under the candidate. The residual corner bumps (§5) show candidate-dependent _weights_
  still matter — denominator stabilization alone (B1) cannot fix numerator concentration, and support stabilization
  alone (B2) leaves weight-driven wiggles. Both halves of H1/H5 are real; B2 addresses the larger one.

## 4. Repair families (evaluated, not adopted)

- **Family (a): contact/topology safety guard (ARM-A).** Forbids candidates that introduce NEW face contacts vs the
  pair's own metric step. Verified: `um` 6 excluded → 9 chosen; corpus-wide 472/2260 choices move (20.9%), 12 new
  fallbacks, reversals fall 198 → 35 / 187 → 34 but the signal stays bumpy (same interactions on a restricted domain).
  Legitimacy gaps: pairs like `Th` (10 datasets), `HH`, `AV`, `um` (8) routinely select newly-touching steps under the
  current touching-permitted policy — many may be legitimate tight spacing, and Gray contact stays binary on fractional
  cells. Verdict: a policy change with wide blast radius, not a signal repair. A global touch ban would additionally
  break valid source relationships wherever facing features legitimately meet. Proposed use: diagnostic flag only.
- **Family (b): sampling/aggregation correction.** _Rejected:_ unweighted mean (−2.6% range, no selection power;
  silently redefines cohesion); fixed-denominator B1 (worse extrema, §3/H5); gap-strip-restricted scoring (converges to
  a wall-gap method = method substitution, out of scope). _Candidate:_ **ARM-B2 no-mask full-support mean** — delete the
  on-ink mask; on-ink queries enter with r = 0 bubbles; weights, normalization, validity, metrics, glyphs all unchanged.
  Exact formula: with `back ≡ all query points`, `interaction = Σ att·(bl+br) / Σ att` as before. Dimensionality:
  unchanged (same kernel, same units); normalization stays per-candidate but the support no longer collapses. Query
  support: fixed window per step as before (extent already immaterial); zeros/ties: none observed (all baseline-valid
  cases finite under B2 in both profiles); external grounding: Electric Bubble integrates full saliency fields rather
  than masking (adapted shape, not parity — the mask itself is the undisclosed project addition being removed).
  Verified: `um` → monotone 1.6942/1.5470/1.2605/0.9877/0.7813, chosen 9, monotone cohesion path [10,10,10,9,9,8,8,7,6];
  repairs `og/Th/rt/nn` identically; bars/rounds/ diagonals stay monotone; differences generally shrink with separation,
  but non-contact scores can change too (see the independent parent check below); dynamic range preserved (median 0.54
  vs 0.47); 11.7% of choices move with no systematic tightening bias and flat boundary rate. Corners: 85–99% extrema
  reduction with small residuals (§5). Complexity: same O(n) exp/div/sqrt, no new ops, no new cache beyond one geometry
  eval, negligible memory delta — Rust/WASM feasible with the existing numeric core.
- **Family (c): gain/loss separation or admissible-branch selector.** No arm: upstream offers the _idea_ (gain vs
  skeleton-degradation loss, §6) but no formula, so any concrete loss term is a project hypothesis with magic weights —
  exactly what the generality rule forbids. The admissible branch of this family (a selector over sourced assumptions)
  is untestable until the oriented/ratio/multiscale field exists as an independent design. State as follow-up, not
  tested here.

## 5. Corpus, split, and arm metrics (Verified)

- Synthetics (fixed, general geometry; 7 fixtures): parallel / asymmetric / vertically offset bars, bar-vs-diagonal,
  diagonal-vs-diagonal, filled-round discs, double-bar-vs-single (multiplicity). Only double-bar reproduces the bump
  (1.304/1.550/1.260/0.988/0.781 vs `um` 1.188/1.551/1.260/0.988/0.781 — steps 7–10 nearly identical, isolating the
  contact step as the pathology); all others are monotone under both baseline and B2.
- Real pairs (fixed): `um og rt Th AV To vv nn mm ll oo` — all 11 present in captures (10 frozen in tables, `mm` new);
  Literata omits U+0060 only, which no pair needs.
- Broad corpus: union of the 26 frozen v3 tables = 87 pair names (86 frozen + `mm`), 2260 valid pair-cases analyzed and
  2 missing-or-fallback at baseline; all recomputed from captures. ARM-A separately adds 12 new fallbacks.
- Split: pair names by sha256 first-byte parity → 41 discovery / 46 heldout (`um`, `og` discovery; `rt`, `Th` heldout);
  all 26 datasets of a name stay together; arm selection used discovery only.
- Settings: default (1.10/2.0/2.0) full corpus all arms; corners (1.0,1.0), (1.0,3.0), (4.0,1.0), (4.0,3.0) — in-band,
  on-grid, exact (no interpolation) — discovery baseline vs B2; cohesion-path sweep is arithmetic on cached geometry
  (cheap). Total runtime ~10 min.
- Metrics recorded per arm/pair-case in `results_corpus.json` (+ `results_corners.json`): face/corner contacts at
  chosen, abstentions (2 baseline) and fallback reasons, new A-fallbacks (12), strict interior extrema on the shared
  valid domain, cohesion-path skips and reversals, full chosen paths, boundary hits, finite/nonfinite counts (B2 100%
  finite where baseline valid, both profiles).

| split            | arm               | extrema (per case) | path skips | path reversals |
| ---------------- | ----------------- | ------------------ | ---------- | -------------- |
| discovery (1064) | baseline          | 333 (0.313)        | 449        | 198            |
| discovery        | B1 (rejected)     | 513 (0.482)        | 510        | 148            |
| discovery        | **B2 (proposal)** | **0 (0.000)**      | 235        | **0**          |
| discovery        | A guard           | — (same signal)    | 193        | 35             |
| heldout (1196)   | baseline          | 331 (0.277)        | 477        | 187            |
| heldout          | **B2 (proposal)** | **0 (0.000)**      | 289        | **0**          |

Corners (discovery extrema, baseline → B2): (1.0,1.0) 414 → 50; (1.0,3.0) 433 → 3; (4.0,1.0) 311 → 1; (4.0,3.0) 336
→ 65. Residuals are small-amplitude wiggles at (1.0,1.0) and ~1–2% contact-adjacent inversions plus broad second-step
maxima at (4.0,3.0) — the weight-driven second mechanism B2 does not remove.

## 6. Source foundation (Verified reads + Inherited audits)

- Pinned algorithms page `609d17e8` (fetched full text this session): penalty `c(d) = l(d) + g(d)` minimized by argmin
  over integer `d`; tracking a _deviation from a target value_ (our cohesion rule's shape) is explicitly offered;
  gain-vs-loss hybrid (family c idea) is offered with **no formula**; aggregation options (mean/max/softmax/local-max)
  are an open TODO list, so no upstream rule prescribes or forbids B2's full-support mean; the `mm` vs `ll` passage
  warns summation over the image cannot work — consistent with support/normalization being load-bearing.
  Direct-approximation model (`f1 = 1/r^k`, `f2 = 1/r^(k+1)`, ratio distance, four pair quantities) ships with an
  explicit unfinished-math TODO; our probe implements none of the oriented machinery (disclosed departure, unchanged).
- YinYangFit JAX (Inherited from `yinyangfit-kerning-model.md`): zero-based cells 22–25 are distance/orientation maps
  with no scalar objective; packaged engine penalty fields return zeros. Restoring an oriented/ratio field is an
  independent new design, not an automatic fix.
- Electric Bubble `31ce15a` (pinned `autofit.js` read this session): `sum(attention·(leftBubble + rightBubble)) /
  sum(attention)` is the exact borrowed shape, but its search is an 80-attempt residual walk toward `desiredInteraction`
  (default 0.01, read in `App.js:54`), not exhaustive argmin; `yFactors` parsed but never applied. Our regularized
  kernel, nearest-sample proxy, strength-product weighting, omitted vertical factor, and exhaustive five-candidate
  search stay disclosed departures. Full-field and scale follow-ups are Inherited negatives: full support still bumps at
  author params; the partial `r = ppem/72` resize doubles extrema.

## 7. Tradeoffs, unknowns, and strongest objections

- B2 changes the estimand (background-only → full-window mean). Defense: the background-only estimand was never sourced
  either. B2 changes the sampling domain, including non-contact scores, and remains a project hypothesis, only a smaller
  one than its rivals.
- Corner residuals prove a second mechanism (attention concentration at non-contact steps). B2 is a large partial
  repair, not a complete theory.
- B2 shifts tight-step values upward, so the cohesion numeric band (and any downstream threshold calibrated to baseline
  ranges) must be re-examined; its _role_ (desired interaction) is unchanged and no new knob is added.
- 265/2260 moved choices (11.7%) need optical assessment before any adoption; residual-pixel deltas are not quality
  claims. Guard-as-flag would report newly-touching selections without moving them.
- Unknown: subpixel lattice phase; Gray optical behavior of moved endpoints; whether the oriented/ratio/multiscale model
  would remove corner residuals.

## 8. Stops, gates, and control inventory

- STOP: no live integration, no default/UI/capture/table change, no training, no gain/loss penalty with fitted weights,
  no oriented-field rebuild inside this arm. B2 stays a labeled proposal in `out/...` + this report.
- Adoption gates (all required): (i) heldout confirmation already recorded here with no retuning; (ii) optical
  assessment of a sample of the 265 moved endpoints; (iii) explicit decision on the cohesion numeric band; (iv) guard
  disposition (flag vs enforce) with optical review of flagged pairs; (v) regression run of the existing browser parity
  tests against any reimplementation.
- Controls retaining meaning/range: reach and falloff keep their kernel/window semantics and bands under B2; candidate
  policy, tie rule, boundary reporting, overlap invalidity, Gray `p/7` coverage, and captured-source fractional word
  baselines are untouched. Only cohesion's numeric band needs re-examination (its role does not change). No new user
  knob is proposed, and no Hu/Hersch strength-blend diversion is involved.

## 9. Deliverables (exact paths)

- Report: `docs/references/yinyang-model-repair.md` (this file).
- Predeclaration: `out/diagnostics/contextual-spacing/yinyang-model-repair/PREDECLARE.md`.
- Harness (read-only against the frozen scorer; concise comments only): `probe_um.py` (replication), `probe_ablate.py`
  (factor split), `probe_decompose.py` (mask/window/translation controls), `probe_bars.py` + `probe_b2synth.py` (7
  general synthetics, baseline vs B2), `run_corpus.py` (26 datasets × 87 pairs × baseline/A/B1/B2 + cohesion paths),
  `run_corners.py` (4 corners, discovery), `make_html.py` (HTML generator reading actual records).
- Raw records: `results_corpus.json` (2260 valid pair-cases with per-step baseline/B1/B2 interactions, contacts,
  extrema, paths), `results_corners.json`, `MANIFEST.md` (start/end hashes: frozen scorer `57cffdea…68baf` and v3
  compute bytes identical; HEAD unchanged; zero tracked files edited).
- Comparison page (self-contained, labeled proposal):
  `out/diagnostics/contextual-spacing/yinyang-model-repair/comparison.html` — real `um` ink at steps 6/7 (whole pixels),
  baseline-vs-B2 curves for `um`, `og`, `Th`, cost tables, cohesion paths, corpus summary. Values verified against
  `results_corpus.json` (script-parse + value check this session).

Work finished as research, not implementation. No optical approval given or implied.
