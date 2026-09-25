# Loop-slack design (orient closed-loop under RTDG rounding)

Status: DEFERRED-STANDING since 2026-09-25 (closed out, no build).
The half-grid RTDG default and rounder alignment were tried and
reverted the same day; production is integer-nearest. Only part 4
(the `geometric()` closure catch) shipped and survives. The
cycle-sum-zeroing search below stays unbuilt until its trigger
fires: any future `closure trip held` outcome or loop-check
failure (v36 regen: none). Unblocks nothing while deferred.

## Problem

`prototype()` demands directed execution (`orient` order +
`evaluate_baseline`) match the dense oracle within 1e-11, over ALL
retained equations including non-tree loop-closing obligations
("Other retained equations remain obligations checked after
construction", `shamir_reorientation.orient` docstring).

Per-segment integer-nearest rounding closes the roboto-14 R loop
(pinned by `test_closed_loop_falls_back_to_unstandardized`). Any
other per-segment rounding (verified: half-grid/RTDG) leaves a
cycle gap (measured: residual 0.5px on plain Dist rows, error
1.0px on ratio-chained points) and trips the check. `correct()`
lets the AssertionError propagate, and `geometric()` does not
catch it, so a rounding change that breaks any loop aborts the
full regen, not just one glyph.

Confirmed fundamental (not fixture staleness): fresh production
roboto-14 R records under half-grid fail `correct()` identically.

## Sourced principle

VTT assigns rounding PER LINK from PER-KNOT attributes, not one
global rule:

- `TTGenerator.cpp TTSourceGenerator::Link`: `Rounding deltaR =
  rthg, parentR, childR` default; non-legacy path rounds "the
  distance according to the child point's rounding method"
  (`deltaR = postRoundFlag ? roff : childR`, with rthg/rthg
  collapsing to rtg and rthg/rtg to rthg); legacy path uses a
  `deltaRounding[parentR][childR]` table.
- Per-knot attributes exist (`attrib[point].round[y]`,
  `parentR`/`childR`), as do RDTG/RUTG directional states and
  the half-grid-aware `defaultMinDistAmount` table.
- Execution is sequential (each MDRP/MIRP moves points against
  current positions); no simultaneous-closure demand exists in
  the spec or VTT. Our 1e-11 check is self-imposed strictness
  beyond hinting, and it stays: the design below keeps it
  green by construction instead of relaxing it.

Spec RTDG ("distances are rounded to the closest half or integer
pixel", vendored truetype-instruction-set-otspec184.md) sets the
rounding granularity; per-link SENSE (down/nearest/up) is the
VTT-sourced degree of freedom this design consumes. The search
procedure itself (below) is invented logic serving our
self-imposed 1e-11 check, so it ships as WHY with oracle gates,
not SOURCED — same escape hatch as the mirror gate.

## Build order (added at implementation): rounder alignment first

Root-causing the R trip showed the gap was narrower than this
design assumed: the failing half was not Dist cycle sums (they
measure 0.000 on R under both roundings) but rounder SKEW —
`equations()`/`evaluate()` had moved to half-grid while
`projected_anchors.scaled()` still derived integer anchors, so
sequential positions using derived rows diverged from the dense
oracle by up to 1px. Aligning every per-segment rounder on
loop-participating paths to the same granularity+sense closed
R with no assignment at all.

Shipped instead of the search below: half-grid RTDG default in
`_dist_rhs` (+ `round_sense` row attribute, default nearest),
`scaled()` honoring the same, slant-replacement targets in
`cross_section_widths` likewise, and the `geometric()` closure
catch (part 4). Joint soft-goals stay integer (lstsq targets,
not obligations). The cycle-sum-zeroing search is DEFERRED
until a loop trip triggers it: no loop in the current
repertoire needs it, and building it now would be speculative
machinery. Trigger: any future `closure trip held` outcome or
loop-check failure — that glyph's cycle analysis then decides
whether the search (specified below) is the fix.

## First gate result (literata-16 single-face regen)

Rounder alignment alone (no assignment) held every invariant:
184 focused tests green including the R-loop test, and the
single-face regen completed with no closure trip. Oracle vs
v27: l APPROVED (C=14→2, W=0); m C=29→12, n C=18→7,
h C=22→4 (all closer, still REJECT-flagged); o unchanged
(unsettled); e C=14→16 (unsettled, ±noise).

Pixel-diff on m shows the widths now match and the remaining
delta is vertical: a pre-existing top-row artifact (row -9,
present identically in v27) from the cap/extent fitting,
plus 4 missing px at row -7. The widths issue and the
top-row artifact are separate mechanisms; this package owns
the first. Without the artifact m lands at C≈4-5 against
W=5 (borderline APPROVE).

## Mechanism (deferred): cycle-sum-zeroing sense assignment

For each fundamental cycle of the executed constraint graph,
assign each adjustable Dist edge a sense {floor, nearest, ceil}
(at RTDG granularity) such that the signed cycle sum is exactly
zero. Non-loop edges keep nearest. A zero-sum assignment ALWAYS
EXISTS: design values sum to zero around any cycle exactly, and
each edge offers floor(d) <= d <= ceil(d), so the achievable-sum
interval (an integer lattice in half-px steps... contiguous at
0.5px granularity) always contains zero. Requirement: every
fundamental cycle contains at least one adjustable Dist edge;
cycles of only exact rows (Ratio, unrounded) cannot drift by
construction and need no assignment.

Search objective: minimize total deviation from nearest subject
to zero cycle sums; ties prefer all-nearest. A zero-sum
assignment always exists (see above), the search is bounded
(2^k per k-edge cycle; loops are small — assert a cap and hold
the glyph if ever exceeded), and a fundamental cycle with no
adjustable Dist edge asserts + holds instead of silently
keeping nearest.

Consequences, all verified by construction rather than hoped:

- Directed execution still satisfies every retained equation:
  the 1e-11 check keeps its exact meaning. No tolerance change.
- Integer-era behavior is the fixed point: loops whose
  nearest assignment already sums to zero (roboto-14 R today)
  get an all-nearest assignment, i.e. zero census delta from
  the assignment machinery itself.
- `[`-class rows keep nearest unless a cycle forces otherwise;
  forced moves are explicit in the data, so the census shows
  exactly what the settled W=0 target stands to lose.
- m/n/h/l rows are not in any nonzero cycle (their failure was
  pure per-segment rounding), so they take plain half-grid
  nearest and render 2px.

## Scope (files)

1. Row schema: a round-sense attribute on Dist/PDist rows
   (default nearest = current behavior when no assignment).
2. `orient`: after order construction, compute fundamental
   cycles over chosen + obligation equations, search the
   sense assignment (2^k per k-edge cycle; loops are small),
   stamp rows.
3. Every per-segment rounder honors the stamped sense, or
   derivation-vs-solver drift returns: `_dist_rhs`,
   `projected_anchors.scaled`, plus `joint_stroke_fit` width
   targets and `cross_section_widths` targets wherever they
   feed loop-participating equations. Full inventory with a
   census-time assertion during the build; any rounder missed
   re-trips R exactly as observed.
4. `geometric()`: catch AssertionError from `correct()` as
   held/unsupported (VTT bail-out pattern precedent already in
   the ledger), so a future uncloseable glyph is visible,
   never a regen abort. Shippable independently; zero behavior
   change while no glyph trips it.
5. Tests: sense-assignment unit tests (zero-sum on a synthetic
   loop, all-nearest fixed point on the R fixture under
   integer rounding, search bound + unadjustable-cycle
   fallback) + the existing R-loop test unchanged +
   the half-grid Dist tests from the reverted attempt.
6. Gates: full unit suite, full 12-face regen, census (expect:
   ~1.5px-class stems move, R loop rows move by assignment),
   dual-witness oracle with the settled targets (`[` W=0 must
   hold 1px; m/n/h/l must flip to APPROVE).

## Alternatives rejected

- Relaxing the 1e-11 check (e.g. 0.5px tolerance): guts a
  load-bearing invariant; forbidden weakening.
- PDist-only half-grid: sourceless cherry-pick; VTT applies
  the link default to both MDRP and MIRP paths.
- Holding R / letting regen crash: coverage regression on a
  shipped glyph for unsettled gain; the census gate exists to
  catch exactly this.
- One unrounded "slack edge" per loop: does not close in
  general (residual equals accumulated tree drift, nonzero).
