# Residual stem defects: literata-14 6/K/7/Q/R, roboto-14 e/c; literata-16 N

Date: 2026-09-13. Context: the O/Q side fix (shared stem target in
`curved_width_links`, this branch) is verified end-to-end; the spots
below need distinct mechanisms. All evidence is measured, not
inferred: pipeline renders use `compare_paper_prototypes.render`
(`hinted=True`: native bytecode, mono); design widths are 10x
unhinted FreeType divided by 10; the oracle is FreeType autohint mono.

## Closed without code: literata-16 N 1px stems

N stems are 1.1px BY DESIGN (H: 1.6px, same face/size); fitted and
autohint both render 1px. Unifying them to 2px would destroy designed
contrast (thin stems + thick diagonal). No action.

## Fixed this round: roboto-14 e apex doubling

e's apex band HAS an equation (id=7, arc 151u = 1.03px design) that
was an unprotected plain Dist, so its edges floated to solver
rounding (2px ink) although both own rounding and the shared target
are 1px. Fix: arc/bow width rows now solve exactly (protected in
`fit()`), and the withhold is span-based (partial spans share;
`joint_stroke_fit._withholds_table`). Verified: apex row
`.####.` -> `..##..`, rest of glyph unchanged.

## Common finding

The exported fonts carry real per-glyph TrueType programs (SCFS,
precomputed 26.6 positions, ppem-gated; e.g. 6 = 1305 bytes, CVT
`[85, 88]`). `install()` compiles fitted coordinates, so the bytecode
reproduces fitted outlines within 1/128px. Rendering with
`FT_LOAD_NO_HINTING` shows the *stored* (base) outlines and is NOT
representative: e.g. candidate 6 renders 1px upper sides unhinted but
2px through its own programs. Diagnose fitted geometry via
`audit_terminal_coverage.coords(face, char, size, hinted=True)`.

## Open: Q/R upper shoulders, 6 shoulders (diagonal arch coverage)

Q row 1 right, R rows 1-2 right, 6 rows 1-2 render 2px horizontal
runs, but the arch band there runs diagonally: ~1.4px perpendicular
reads as ~2px horizontal. Unhinted design renders show the same 2px
(Q row1, R rows 1-2), so current output is geometrically honest;
autohint thins Q fully to 1px (and shrinks the glyph 12x13 -> 11x11)
and R row 2 only (row 1 stays 2px even in the oracle). No width
equations cover these diagonal runs (Q has one vertical arc row for
the apex only; sides come from the curved branch at mid-height).
Needs arch-band thinning along diagonal runs (parallel-curve offset
or horizontal snapping a la Hersch Fig. 25), same bucket as K arms.

## Open: roboto-14 c upper terminal tip

c row 1 (`.#####`, 5px) vs design 4px (`.####.`) and row 0 fine: the
tip moved right ~1px in joint-fit Abs rounding (stages: joint-fit
only, terminals no-change). Terminal-tip-specific handling needed;
changing global Abs rounding is out of scope. Deferred.

## 6 upper bowl sides: 1px fitted, 2px ink (phase + shoulders)

- Branch audit (`width_audit_curved-width-links`, literata-14 case):
  axis-0 pairs (98u/102u design, 1.37/1.43px) take target 1.0,
  `after_width_px` 1.0. The width is correct; rows 1-2 still show
  `##..##`.
- The pair claims govern the x-extremum rows (mid-side). Rows 1-2 show
  the top-arch shoulders, where the 1.3px-thick arch runs diagonally
  and covers two columns geometrically. A rigid pair phase-snap was
  prototyped and reverted: 6's outers already sit on integer phase
  (`outer_shift_px` 0.0 everywhere), so it cannot help.
- Spec: thin the top-arch band toward the shared target and control
  its phase (arc thickness sharing + Hersch section 5 extremity phase
  control), in `curved-stroke-recovery` or the branch, reusing the
  existing counter-topology and cardinal-inversion guards. Note the
  vertical-arc withhold (`joint_stroke_fit._withholds_table`) protects
  apex *heights*; arch *thickness* rows need sharing instead — the
  current normal-direction predicate conflates the two (see also the
  pinned `test_arc_height_keeps_solver_rounding` case, which enshrines
  2px for a 1.28px apex height).

## K upper-right arm rows 1-2: junction wedge, undetected top bar

- Rows 1-2 (`#....##.`) sit directly under the 2-row bar top, right of
  the junction. The arm proper (id=10 slant row, 96.7u) soft-goals
  1px perpendicular and the mid-arm is fine; the defect is the wedge
  between the bar bottom and the arm top edge.
- K has NO bar feature for its top bar, so no bar-thickness equation
  exists; the bar bottom rounds per-point (zone-alignment gap, same
  family as the `roboto T` case in `_withholds_table`'s docstring).
- Proven geometric target (in-memory outline poke on fitted positions,
  pipeline renderer): shifting arm-top points 56-59 left 0.5px yields
  1px upper arms with bar, junction body (`.#####...`) and lower arm
  intact. Points 56-59 sit near tip feature 1 (slant, 51.7u, pts
  [9, 39]), whose cross-section holds (`section()`:
  "0 unique support pairs" — short taper, no pairs).
- Spec: relax tip pairing in `section()` OR detect the short top bar
  (bar-with-serifs) so its underside takes one consistent rounding;
  arm tip points must join a width equation for either route.

## 7 lower leg: undetected curved stroke (detection gap)

- `recognize()` finds only horizontal bars (89u/189u top bar, curve
  bar); the leg has NO features and the record graph has NO width
  rows for it, so no sharing mechanism can reach it. The leg sides
  are fragmented curve pieces (right edge dirs approx
  [-0.92,-0.39], [-0.60,-0.80], [-0.37,-0.93]; left edge/foot
  [-0.55,-0.83], [-0.99,-0.11]) that never pair.
- Fitted leg horizontal extent is ~0.8-1.1px (correct thinness); rows
  4-5 render 2px after the fitter moved the bend up to +0.44px
  (hinted-vs-unhinted per-point delta for 7). Rows 7-9 are the foot
  serif (structurally wider; taste call).
- Whole-glyph rigid shifts do NOT change 7's rows (translation
  invariant) — phase-snapping cannot fix it; the bend coverage is
  structural.
- Spec: stroke detection for curved diagonal strokes (medial-axis
  direction, cf. StrokeStyles 2022 already in
  `docs/reference/font-legibility.md`), then a width equation +
  phase control as for K. Until then 7 is out of reach of every
  sharing/phase mechanism in the tree.

## Reverted during this work (do not reintroduce without new evidence)

- Singleton-slant shared-target soft-goals (`joint_stroke_fit.fit`):
  pulled Roboto diagonals UP to 2px clusters (Roboto-16 v/w/x,
  +8..+19 ink). Cut-in 1.0px is far too permissive upward.
- Slant pair phase-snap by mean parity: 43 thickened vs 32 thinned
  matrix-wide (e.g. roboto-18 `!` +9 ink); mean-x phase does not
  predict diagonal ink.
- Curved outer phase-snap: provably idempotent everywhere measured
  (all `outer_shift_px` 0.0); no demonstrated production effect.
