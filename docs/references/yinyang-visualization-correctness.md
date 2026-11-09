<!-- cspell:words yinyangfit YinYangFit Kosch equidistance argmin argmax reimplementation trunc reweighting Fiset autofit multiscale reweights Nonmonotonic unkearned untable uncomputed yinyang unvalidated -->

# YinYang visualization correctness audit

Read-only audit, 2026-11-03. **Do not implement from this file; parent owns judgment and subsequent implementation.**
Queued UI changes (no ruler/source strip, per-letter colors, editable preview text) remain outstanding and are assessed
only for correctness preconditions.

**Headline: the pixel pipeline is correct; the visual story is misleading.** Every displayed blob pixel faithfully
computes the documented nearest-distance bubble component with true bearings, Gray `p/7` coverage, fixed frames, and the
shared choice rule (all re-verified independently this session). But the blobs are the _unweighted input components_,
while the score that moves the letters lives in the _attention normalization_ the display hides. Blobs that "merge" do
not mean high interaction, and the widest displayed blob footprint in the audited pair belongs to the lowest-scoring
step. The per-letter-colored-field presentation lineage claimed from YinYangFit traces to a conceptual grouping
schematic, not to the upstream field model — whose direct-approximation section ships with explicit unfinished-math
TODOs and no illustration at all.

Evidence labels: **Verified** means run or read this session. **Inherited** means taken from a cited prior audit without
re-verification. **Inference** means a source-backed judgment. Section G timings marked parent-verified were measured by
the parent harness, corroborated here by an independent mechanism check.

## Findings by severity

1. **Misleading (high): blob merge/extent does not track the score.** Roboto 16 Mono `og` at the default setting (reach
   2, falloff 2), steps 7–10, shipped interactions `1.20333 / 1.42101 / 1.17998 / 0.93619`: the attention peak is at
   step 8, but the largest above-threshold blob footprint is at step 10 (widest) and the largest strong-overlap region
   at step 7 (narrowest). Verified in `findings_js.json` (`B1_mergeVsScore`: argmax interaction 8, argmax union area 10,
   argmax overlap 7). Anyone reading touching blobs as "strong grouping / high cohesion" will conclude the opposite of
   the scorer on real data. The unweighted component mean ranks the steps `7, 8, 9, 10` while the attention-normalized
   score ranks them `8, 7, 9, 10` (`findings_py.json`, `P2`), so the displayed quantity cannot even order candidates the
   way the model does.
2. **Lossy (medium): the word-strip composite erases overlap and hides sampled points.** `drawExcerptField`
   (`experiments/contextual_spacing/yinyangfit_interactive_v3_visual.js:291-349`) composites per-glyph fields by
   per-pixel MAX in a single blue, discards levels `<= 0.02`, and covers inside-ink field with opaque ink. On "Pack my
   box" at defaults, 182 frame pixels carry two or more fields above 0.3 (display keeps only the max; the second
   contributor is invisible), and 1326 of 5250 frame pixels the scorer samples are hidden by the display threshold
   (`findings_js.json`, `B2_excerptComposite`). The single-pair view (`drawPairField`, lines 126–187) replaces the seam
   problem with a stronger-field-wins tint boundary — still no overlap rendering. Neither view shows attention.
3. **Correct (verified): the whole pixel pipeline.** Independent brute-force nearest + direct formula recomputation
   matches the shipped helper grids exactly (`maxAbsDiff` 0; half-strength identity holds), Gray coverage stays
   delivered `p/7` through decode and nearest-value lookup, frames are identical across all control settings,
   `candidateRows` agrees with the shipped choice on all 86/86 table pairs, and an independently written numpy
   reimplementation of the full geometry matches scorer and shipped table to 0.0 (`P1`). JS `scoreStep`/`scorePair`
   agree with shipped derivations on sampled pairs (`A5`). The frozen scorer (`57cffdea…`) and page bytes are
   byte-identical to `start.json` (hashes below).
4. **Correct with a disclosed crop (low): display frame vs scorer window.** The frame is the union over tried steps ±10
   px (`visual.js:78-98`); the scorer samples ±(`ceil(6·scale)+4`) around tight bounds at the evaluated step
   (`v3_compute.js:149-153`). At default reach 2 the scorer window (±16 px) exceeds the frame margin, so the display
   crops sampled background; at reach 12 (±76 px) it shows a small central crop. Verified by code read. Fix by caption
   or by drawing the window boundary, not by rescaling.

## A. Trace: display pixels to model values

| Claim                                                   | Result                                                                                                                                                    | Location                                                             |
| ------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| Nearest distance, first-index ties over row-major ink   | Verified: independent brute-force loops agree exactly (A1)                                                                                                | `v3_compute.js:56-69` vs `yinyangfit_interactive.py:442-446`         |
| Bearing/origin: `x = left + col`, right shifted by step | Verified: same expression both languages; fractional-bearing truncation agrees (`int()` vs `Math.trunc`, P4)                                              | `v3_compute.js:101-114`, `yinyangfit_interactive.py:469-488,491-499` |
| Gray `p/7` nearest coverage                             | Verified: 8 exact levels preserved; on-ink query returns its own cover (A2)                                                                               | `v3_wiring.js:213-215`, `v3_compute.js:486-493`                      |
| Per-field fixed 0..1 alpha scale                        | Verified by read; threshold `> 0.02` hides scorer-sampled points (B2)                                                                                     | `visual.js:154-164,317-328`                                          |
| Fixed frames, fixed intensity                           | Verified: identical frame across reach/falloff/cohesion (A3)                                                                                              | `visual.js:73-98,267-284`                                            |
| Candidate choice mirrors scorer                         | Verified: 86/86 agreement incl. recompute; off-grid reach 12 stays finite (A5)                                                                            | `visual.js:38-71` vs `yinyangfit_interactive.py:413-434`             |
| Background/ink exclusion                                | Faithful in effect: scorer drops on-ink query points; view paints field everywhere but covers ink opaquely, so visible pixels are background-only in both | `yinyangfit_interactive.py:326`, `visual.js:166-181,329-343`         |

## B. The composite does not communicate the interaction

The scorer's discriminating machinery is all in the attention path: strength fields use exponent `q+1` (not the
displayed `q`), equidistance (`spread = scale/2`), opposing gradients, and normalization by `attention_sum`
(`yinyangfit_interactive.py:335-356`). The display shows only the `q`-exponent bubbles `bl/br`. Removing the attention
reweighting flattens the `og` curve to a monotone near-flat line (0.1448 → 0.1410, −2.6%; inherited from the
[control research](yinyangfit-interactive-control-research.md) causal probe, consistent with P2 above), which is exactly
what the blobs depict. The candidate-score dots (`drawCandidateScores`, discrete, no joining curve) are the only element
that shows the actual selection cause; nothing links blob appearance to score ranking. Keep that plot; do not join its
dots with a curve (implies a continuous objective over untested widths).

## C. What the upstream reference actually contains

Pinned revision `609d17e8a6446ec4413a1b02a0768b8214d73333` (2022-11-27), fetched 2026-11-03 from primary raw sources:

- **Colored-blob lineage is presentation only, and it traces to a schematic.** The "saturation of the coloured blobs
  indicates the intensity of grouping" margin note belongs to `grouping_relativity.png` in `introduction.markdown`
  (~L109-112) and `gestalt_dynamics.markdown` (~L306-311): G-cell grouping-activity schematics over fitted vs poorly
  fitted words, not computed model fields. `letter_features_bubbles.png` (`reading_models.markdown` ~L129) is Fiset et
  al. empirical saliency — unrelated to grouping fields or any score.
- **The direct-approximation model has no illustration and unfinished math.**
  [`algorithms.markdown`](https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/docs/source/algorithms.markdown)
  (`#direct-approximate-grouping`) specifies radial kernels `f1 = 1/r^k`, `f2 = 1/r^(k+1)` with `k ≈ 2`, ratio distance
  `d = (T*f1)/(T*f2)`, arc strength `k = (T*f1) ⊙ d^(k+1)` (overloaded `k`), and four pair quantities `|dL−dR|`,
  `kL·kR`, `dL+dR`, `(oL, oR)` — then carries `<p class="missing">Explain and illustrate the model, and derive the math.
  Explain the computational benefits.</p>`. No singularity, zero-denominator, finite-support, or discretization rules;
  the cost-function section carries three more missing-illustration/aggregation TODOs and uses the `mm` vs `ll` example
  to show summation cannot work. Our probe's radial, orientation-blind, single-nearest, regularized kernel is a
  disclosed departure (scorer module docstring L9-44), not a reproduction.
- **The normalization shape is borrowed from Electric Bubble, whose selector is a different algorithm.**
  [`autofit.js`](https://raw.githubusercontent.com/skosch/electricbubble/31ce15a56429b67e2c759fcb625e78db3a17e9d3/src/autofit.js)
  computes `sum(attention·(leftBubble+rightBubble))/sum(attention)` — the exact shape our scorer borrows — but its
  search is an 80-attempt residual-following overlap walk (`0.001` tolerance, gradient step), not exhaustive
  five-candidate argmin; `yFactors` are parsed but never applied. Verified from pinned `31ce15a5` source.
- **Defensible vs unsupported claims.** Defensible: "nearest-distance bubble probe inspired by Electric Bubble /
  YinYangFit's radial factors; attention-normalized aggregation; exhaustive integer search toward cohesion."
  Unsupported: any suggestion that blob overlap visualizes grouping strength, perceptual quality, or the upstream
  oriented/ratio/multiscale objective. The page's About box already states the departures correctly; the blob views need
  the same honesty at the point of display (see fix plan).

## D. Control effects (observable, spatial)

- **Reach** is the radial knee (`fieldStrength` half-strength at `distance == reach`, verified A1) _and_ the geometry
  scale: evaluation window `±(ceil(6·scale)+4)` and equidistance `spread = scale/2`. Moving it reweights distant vs
  gap-local ink — visible as blob spread — and resamples the query set. Verified by code read.
- **Falloff** steepens the bubble fade (exponent `q`) _and_ sharpens the attention weights (strength exponent `q+1`
  inside `strength_l·strength_r`). Visible as blob contraction plus re-ranking through attention. Verified.
- **Cohesion** only selects among the five scored candidates (`|interaction − cohesion|`, ties toward metric); geometry
  is cohesion-free. Nonmonotonic by construction: `og` 9 → 7 when cohesion rises 1.1 → 1.2, `Th`/`rt` widening under
  rising cohesion, line totals 422 → 402 → 372 → 375 (inherited,
  [control research](yinyangfit-interactive-control-research.md); corroborated by B1/P2 here). Cohesion letters move;
  only the candidate-score dots show _why_ a width won.
- Minimal truthful design: keep the three knobs, the discrete score dots, and fixed frames; never present cohesion as
  monotone tightness (v3 already uses Lower/Higher, not Tighter — keep it that way).

## E. Smallest correct foundation for the queued UI (no model/endpoint change)

1. Per-letter colors with MAX compositing kept, documented in the legend as "overlap shows the stronger field only;
   brightness is a component, not the score." Never sum fields — a sum would be readable as interaction and is false (B1
   shows footprint and score disagree in ranking).
2. Keep the discrete candidate-score plot as the selection-cause view; add nothing that links blob shape to choice.
3. Optional later layer: one toggle showing the _attention weight_ field per pair/step (the actual hidden machinery),
   computed from the same shipped geometry — display-only, no scorer change. Not required for the queued work.
4. Ruler and Source-blob-strip removal is fidelity-neutral (both are display-only; the ruler carries no model
   information), but update the About/explainer copy that currently says "compare the two strips below," and keep the
   Source/Adjusted ink views — they remain the only placement-effect comparison.
5. Legend rule already in code ("colors pair with labels, never color alone") must extend to every new per-letter color.

## F. Editable preview text: blockers

Repertoire is captured ASCII `32–126` per case/profile (26 labels inventoried in `findings_py.json` `P5`); Literata
lacks U+0060 (backtick) in both profiles; no non-ASCII anywhere. Behavior is loud, never silent: unknown codepoints
(including `\n`, `\t`, `é`) raise `ValueError: codepoint U+XXXX not in captured repertoire` (P6 + control-char probe);
word space keeps metric with `space_gap_metric`; novel in-repertoire pairs (e.g. `qj`) score exactly on demand — shipped
tables cover sample-text pairs plus 10 fixed pairs (`nn HH ll oo OO ee AV vv To ya`), the worker path computes the rest
with the identical core. Metric for unkearned pairs is `advance + 0.0`, which is the source policy (no kern entry), not
an assumption. UI must therefore: split lines before scoring (layout is per-line, cumulative whole-pixel origins), gate
input to the 95/94 supported codepoints with the repertoire error surfaced, and route untable pairs through the existing
on-demand path. No new captures or metric policy needed.

## G. Performance vs fidelity

No Rust/WASM port exists (parent judgment stands). Cohesion moves re-derive choices from stored interactions (cheap);
reach/falloff recompute all pairs exactly via worker with chunked main-thread fallback and generation-guarded painting
(`v3_wiring.js:245-482`, verified by read). Parent-measured: reach 12 ~2018 ms, cohesion 1.15 ~9 ms, falloff 4.2 at
reach 12 ~2179 ms; blob painting 4–9 ms. Independent corroboration this session (Node, same core): 86 pairs in 180 ms at
reach 2 (2.1 ms/pair) vs 2218 ms at reach 12 (25.8 ms/pair) — cost grows with window area, matching the parent timings
within 10%. Do not hide wide-reach recompute behind the repaint path; keep the "Updating spacing…" state and never
interpolate uncomputed settings (the builder already guarantees exact evaluation only).

## Provenance and verification status

- HEAD `240b372bc96027c60d286ef0b7113c4656a40609` matches `start.json`; frozen scorer, compute, visual, wiring,
  template, demo, and reviewed page bytes are all byte-identical to `start.json` hashes (verified this session; the
  experiment sources are untracked files with matching content, not modifications). `docs/designs/.../
  contextual-spacing-and-healing.md` content also matches `start.json` despite a dirty-tree `M` flag against HEAD.
- New harness (bounded, no model/page/table bytes touched):
  `out/diagnostics/contextual-spacing/yinyang-visualization-audit/` — `probe_visual.cjs` (shipped page bytes +
  independent brute-force recomputation; run: `node probe_visual.cjs`), `probe_model.py` (independent numpy geometry +
  repertoire/text-mode checks; run: `python3 probe_model.py`), `findings_js.json`, `findings_py.json`.
- Upstream refs fetched 2026-11-03 from pinned revisions `609d17e8` (YinYangFit) and `31ce15a5` (Electric Bubble);
  JAX-manuscript provisional status and Torch-checkpoint gap are inherited from
  [yinyangfit-feasibility.md](yinyangfit-feasibility.md) and [yinyangfit-kerning-model.md](yinyangfit-kerning-model.md),
  not re-fetched here. No commits, pushes, installs, or production changes were made.

## Strongest objection to this audit

The audit verifies the display against the probe's own math, and the probe's math against itself in two languages — but
the probe's score has no optical standing (pending assessment per the evaluation rules), so a perfectly faithful picture
of it is still a picture of an unvalidated number. The most honest minimal UI may be smaller than Section E: score dots
plus ink comparison only, with blobs demoted to a clearly labeled component illustration or removed. Do not let
pixel-exact parity (Sections A/G) substitute for the missing perceptual evidence.
