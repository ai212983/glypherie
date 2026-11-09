<!-- cspell:words yinyangfit falloff subpixel reweighting argmin -->

# YinYang slider ranges and step sizes

Research + implementation note, 2026-11-03. The v3 gallery page keeps the frozen scorer formula
(`yinyangfit-interactive.py`, SHA `57cf…b68af` unchanged); only the _evaluated settings coverage_ grew, versioned in
`experiments/contextual_spacing/yinyangfit_interactive_v3_ranges.py` (now `v3-grid-2026-11-03-uniform`). Defaults stay
`1.10 / 2.0 / 2.0`. Optical status remains **pending assessment**.

## Chosen grids

Uniform numeric increments: cohesion `0.10`, reach and falloff `0.5`. Visual choices still need not vary monotonically;
the uniform steps only make the controls predictable.

| Control                | Grid                                  | Default | Why                                                                                                                                                                                                                                                                                               |
| ---------------------- | ------------------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Target cohesion        | `0.40 … 1.80` step `0.10` (15 values) | `1.10`  | Uniform fill adds `0.70, 0.90, 1.70` to the previous twelve. Free: cohesion is derived from stored interactions, no new geometry.                                                                                                                                                                 |
| Interaction reach (px) | `1.0 … 4.0` step `0.5` (7 values)     | `2.0`   | `0.5` left off: near-degenerate (3–7 pair moves everywhere). Adds `3.5`, which moves 13 Mono / 3 Gray pairs at `1.10/2.0` on Roboto 16.                                                                                                                                                           |
| Proximity falloff      | `1.0 … 4.0` step `0.5` (7 values)     | `2.0`   | `4.0` admitted on evidence (finite everywhere probed, invalid placements identical to the overlap baseline). Adds `3.5`, which moves 1–2 pairs at the reported `1.10/2.0` on Roboto 16 — a distinct fine-tuning step, not a near-duplicate. `4.0` is the evaluated UI range, not a scoring limit. |

735 combos (`15 × 7 × 7`), up from 432 (144 before that). Combo ids are positional (`c359` is the new default key);
settings identities are stable value triples: 144/144 and 432/432 preserved.

## Slider copy (one line each)

- Cohesion: "The visual closeness to aim for between neighboring letters."
- Reach: "How far letter edges influence a gap; higher values reach farther."
- Falloff: "How quickly that influence fades; higher values focus on nearby edges."

Larger falloff ⇒ more local follows the kernel `g / (1 + (r/scale)^q)` directly. No copy promises monotone tightening;
the single caveat (a step can widen some gaps while tightening others) lives in the header and About note. Level words:
Gentle / Balanced / Standard / Strong (`2.5`) / Sharp / Sharper (`3.5`) / Very sharp (`4.0`).

## Verification (this session)

- Reported case reproduced: Roboto 16 Mono line 3 at `1.10/2.0/3.0` lays out `…, 8→9 (ef), 5→6 (ff), …` per the scorer;
  falloff `4.0` changes 2 pair choices there (mechanical effect — whether it looks better is user judgment).
- Uniform-grid correction: grids are now `15 × 7 × 7` (735 combos, 49 geometry columns); only the 13 new reach/falloff
  `3.5` columns were evaluated fresh, the shared 36 were reused verbatim with old-grid parity rechecked by value
  (144/144 and 432/432 identities preserved). Captured Source baselines untouched (per-pair metric steps equal).
- Suites: focused Python range tests pass; page test checks browser derivations against shipped bytes over the full
  grid; Chromium test passes with zero page errors, including an explicit falloff `3.0 → 3.5 → 4.0` view change,
  keyboard narration, reset-by-value, all 13 samples, and desktop/mobile overflow checks.
- Cost: one-time rebuild 12m48s single-threaded for the 432 grid; the uniform correction re-evaluated only new columns.
  Data `~33 MB` total, lazy-loaded per sample.

## Limits and strongest objection

- Gray profiles saturate: at default reach, falloff steps barely move Gray choices (0–11 pairs); reach and cohesion
  carry Gray exploration instead.
- Whole-pixel steps skip: denser cohesion still lands on the same five integer candidates, so finer parameters do not
  promise smoother visible motion.
- Strongest objection: honest controls over an unassessed endpoint only aid inspection — falloff `4.0` is mechanically
  sound, not optically approved.
