# Logic provenance ledger

Rule (project memory `constraints.md`, 2026-09-15): every
decision/algorithm/logic needs a reference foundation (VTT,
Shamir 2003, CVT/TrueType spec, Turner-Lemberg, Hersch, scaler
witnesses) unless explicitly specified with a written why.
Parity means parity with sources, not with frozen
source-bitmap-v1. Scoreboard: `tools/font_probe/test_source_parity.py`.

Status key: SOURCED (reference + section cited) / WHY (invented,
explicit written why on record) / NEEDS-WHY (invented, kept on
witness evidence, written why still missing) / UNREVIEWED (not
yet sourced) / REMOVE (contradicts sources; removal sequenced
in Notes).

Stray protocol (tiny monochrome vs VTT defaults): keep VTT/spec
*mechanism* (CVT + cut-in path, anchors, RUTG/RDTG round states,
dropout/scan-conversion controls) and re-calibrate only
*constants* (cut-in distance, bands, minimums) through
tiny-oriented sources (otspec dropout/scan conversion, Shamir
thin-only, Turner-Lemberg standards, monochrome scaler as
witness). A tighter constant inside VTT's default (our 1px
cut-in vs VTT 4px) is calibration, not invention; a new gate
or branch is invention and needs a WHY entry with witness
evidence. Never a per-glyph rule at a font-wide choke point.

Evaluation protocol (2026-09-15): v1 is a tripwire only (the
census diff says *what moved*), never a judge. Verdicts are
absolute against the two witnesses (`oracle2.py`: W =
|autohint XOR native| settledness, C = candidate's worst
standing; UNSETTLED if W > 8, APPROVE if C <= max(2, W),
else REJECT; bands provisional). Full absolute sweep,
ss3-18 production (65 glyphs): 9 APPROVE, ~21 REJECT-flags,
~35 UNSETTLED — the witnesses disagree widely (W 10-30px)
on most glyphs, so settled targets are the minority, and
production ink exceeds both witnesses nearly everywhere a
flag fires: that reads as one global heaviness question,
not per-glyph targets, and none are filed. Settled
establishments to date: ss3-18 `[` thin (W=0, C=0,
APPROVE); ss3-18 o (C=4, W=4, APPROVE).
Twelve-face absolute sweep, production (v21 == v1,
801 glyphs, `/tmp/heavy/`): APPROVE 134, REJECT-flag 220,
UNSETTLED 447. Median C 6-20px tracks median W 3-22px —
witness disagreement dominates, so settled targets stay
the minority everywhere. Median ink bias production-minus-
witnesses is +0..+9px (never negative; roboto-16 +9 and
ss3-18/20 +5/+6 stand out): a mild global heaviness
tendency, recorded as a calibration question, not filed
per glyph. ss3-14 settles most (26/60 APPROVE, medW=3):
fewer pixels leave less room to disagree.
Original-thread probe, literata-16 m/n/p/q (`/tmp/bow_probe.py`,
2026-09-15, current production = arch-probe-v26, one uniform
upper-half region per glyph plus full glyph): m/n are SETTLED
AGAINST us (m W=5 C=35, upper W=5 C=20; n W=3 C=20, upper
W=3 C=10 — margins far from the provisional bands, so no
threshold fragility) and open the first genuine new target
since the cap package; p/q are UNSETTLED everywhere
(W=12..22 full and upper) and close with no established
target. Note the signature differs from the global
heaviness question: our 16px m/n render substantially
LIGHTER than both witnesses (|cand| 40/25 vs 59/39 and
58/38), not heavier — not to be conflated.
Root cause, literata-16 m/n (diagnosed 2026-09-15, all
measured): the curved-link layer narrowed solver-fitted
2.0px arch sides to the unanimous-1px table target (64.4u
cluster, 1.12px design) under the above-14px outright-claim
exception — a v1-parity-era rule whose cited scaler cases
(roboto-16 8, literata-16 O/Q) all probe UNSETTLED
(W=14/17/29: no established target), while m/n settled
against the narrowing (m W=5 C=35, n W=3 C=20). Shipped
outlines are design-fidelity (candidate-unhinted == source
pixel-exact); the source ships ZERO glyph bytecode
(0/1163, 7-byte prep stub), so the witnesses' 2px is raw
scan conversion and the 68 synthesized SCFS programs
(m 1403B, n 885B) narrow it at render time. Fix (v27):
precedence clause with written WHY — links move
solver-untouched widths toward the shared target and widen
fitted ones up to it, but never narrow a width the solver
already widened past design (thin-only preserved for
untouched widths, O/Q widenings apply unchanged, solver
widen-only matched). The 64u cluster vote itself stays
HELD; rejoin wiring stays reverted (ss3 `[`, 62u/1.116px
at 18px, is measurement-identical to the m/n widths yet
settled thin at W=0 — no predicate separates them, so the
scoreboard reopen condition's second half stands
unsatisfied).

## Hinting logic

- Width tables + cut-in (`stem_width_table`: clusters,
  `CUT_IN_PX`, lookup cut-in path): SOURCED — CVT architecture
  (otspec CVT + SCVTCI/SSWCI, vendored `docs/reference/fonts/
  specs/`), Turner-Lemberg font-wide standards. Note: our 1.0px
  cut-in is stricter than VTT's 4px default (calibration delta).
- Thin-only sharing, 14px (`curved_width_links` gated branch,
  joint thin-only): SOURCED — Shamir 2003 Sec. 3.5.
- Hold-or-widen (never narrow fitted, both): WHY — protects
  fitted 2px sides feeding bytecode; approved 14px deltas.
  No paper parent (Shamir is thin-only).
- IUP interpolation of untouched points: SOURCED — spec IUP,
  Turner-Lemberg IP.
- Least-squares constraint solving framework
  (`shamir_baseline_solver`, `cross_section_widths.system`):
  SOURCED — Shamir's constraint model. (The rounding of
  right-hand sides is separate, see extent rounding.)
- Extent outward rounding (`_abs_rhs`/`_dist_rhs`,
  `abs_row_map`, extent flags in `shamir_model`,
  `projected_anchors` extent branches): WHY — sourced as
  per-edge outward round states (spec RUTG/RDTG + SROUND
  vocabulary: tops/rights round up, bottoms/lefts round down);
  no paper parent, but ablation (legacy-solver run) regresses
  both witnesses broadly, so the values stand. Code comment
  cites RUTG/RDTG since 2026-09-15 (`_abs_rhs`/`_dist_rhs`).
- Non-extent Dist rounding (integer-nearest in `_dist_rhs`):
  SOURCED-VOCABULARY (spec default round_state is round to
  grid; MS hinting tutorial: "The default setting is 'round
  to grid'"), production state since the v27 revert of
  2026-09-25. The 1px stems behind four settled-against
  glyphs (literata-16 m W=5 C=29, n W=3 C=18, h W=2 C=22,
  l W=0 C=14: shared 93u = 1.488px rounds to 1px while raw
  scan conversion covers 2px) stay 1px under it. History:
  half-grid tried and reverted 2026-09-25 (0.5px cycle gap
  in the roboto-14 R closed loop, tripping prototype's
  directed-vs-dense check
  (`test_closed_loop_falls_back_to_unstandardized`,
  residual 0.5 on plain Dist rows) — integer rounding is
  what closes that loop, and `correct()` lets the
  AssertionError propagate (regen crash). Confirmed
  fundamental (not fixture staleness): fresh production
  roboto-14 R records under half-grid also fail `correct()`
  with the same AssertionError, which `geometric()` does
  not catch (full-regen abort). A PDist-only scope was
  rejected as sourceless (VTT applies the default to both
  MDRP/MIRP paths).
- SROUND-threshold-5/8 for non-extent Dist (cutpoint 3/8,
  round up iff frac >= 3/8): TRIED as v30, VETOED
  2026-09-25, production reverted to integer-nearest above.
  Targets improved (m C=29→12, n 18→7, h 22→4) but nothing
  flipped to APPROVE; costs were gate-recognized losses:
  settled roboto-14 `[` APPROVE lost, roboto-20 `[` newly
  flagged, production coverage dropped. VALUE REFILED
  2026-09-25 (was: fit to 4 settled points): the cutpoint
  is published. ttfautohint docs (Lemberg, v1.6 §2.3.5):
  "Normally, ttfautohint rounds the x height to the pixel
  grid, with a slight preference for rounding up (to use
  the terminology of TrueType's 'Super Round' bytecode
  instruction, the threshold is 5/8px)". Spec SROUND adds
  the threshold then truncates, so 5/8 = round up iff frac
  >= 3/8 — exactly the v30 rule; spec section "Super
  ROUND", MS OpenType 1.9.1 instruction set (verified
  against the live spec 2026-09-25). SCOPE LIMITS:
  documented for x-heights, NOT stem widths (ttfautohint
  snaps stems to standard widths instead); transfer to
  horizontal stem Dist rows is project inference. Its WHY
  (small-size legibility: keep thin features from
  vanishing) matches the m/n/h/l complaint. Counter-
  practice: VTT/MS move the 1→2px transition per font per
  size via delta exceptions (MS tutorial "Functions and
  delta hints" DeltaC; VTT "Fixing rasterization issues":
  "we can override at what size a 1 pixel stem becomes 2
  pixels") — default rounding + targeted overrides, not a
  global cutpoint shift. Next: targeted up-exceptions on
  the integer default (VTT shape, ttfautohint rationale).
- Targeted up-exception (93u horizontal class, `_thin_stem_up`
  in `_dist_rhs` + `projected_anchors` + cross-section
  targets, closure-catch diagnostic): TRIED as v31,
  2026-09-25. Premise probe: zero 93u rows on any roboto or
  ss3 face (R loop + all settled witnesses untouched by
  construction); literata-14/18/20 93u rows sit outside the
  [3/8, 1/2) band (no-ops); only literata-16 fires (22 rows
  on 17 glyphs). Full-regen census vs v27: status moves 0;
  pixel moves exactly the predicted 15 literata-16 glyphs,
  zero elsewhere (roboto-18 o / roboto-20 6 show 1/64px
  native_points wobble with identical pixels — regen
  instability across runs, pre-existing, pixels unaffected).
  Oracle (48 cases, v27 control rerun): settled +
  evidence + all 36 watch cases byte-identical; only the 4
  target lines move, all closer (m C 29→11, n 18→6, h
  22→4, l 14→3), still REJECT-flagged on the documented
  top-row artifact (separate mechanism). No settled loss,
  no new flag, no coverage drop — the v30 vetoes do not
  recur. Status: WHY + oracle-gated; class key is
  design-units-only, so a future face holding 93u rows that
  must stay down narrows it (premise probe is the
  instrument). Shipped 2026-09-25 (eabdb0b).
- Same-glyph overshoot collapse (`_flat_top_collapse` in the
  joint substitution Abs branch, v32): TRIED 2026-09-25.
  An extent-max Abs row within 3% above the glyph's own
  rounded flat top takes the flat's integer instead of the
  outward ceiling. Rule sourced (GF VTT variable guide:
  overshoot CVTs forced equal to flat CVTs at small sizes;
  MS VTT autohinting guide: round cap made equal to square
  cap); the 3% number is WHY (covers observed 2.76%,
  excludes 5.5%+ gaps), oracle-gated. A font-wide flat-x
  vote was measured and REJECTED first: literata's biggest
  sub-cap cluster is 557u (82 members, not the 507 flat)
  and ss3 shows a four-way near-tie (478/490/510/522) —
  plurality would crown the wrong line, and zones are
  designer-declared, not histogram-recoverable. The
  same-glyph shape needs no vote and protects settled
  ss3-18 'o' structurally (round crown, no flat in glyph).
  Full-regen census vs v31: status moves 0; pixel moves
  only literata-14 r, literata-16 m/n, literata-18 p,
  literata-20 n/p; roboto/ss3 zero. Oracle: m/n flip to
  APPROVE (C 11→5, 6→3); settled, evidence, and all 36
  watch cases byte-identical; lit14 r improves (C 6→4);
  lit18 p / lit20 n/p drift ±2-4px inside UNSETTLED
  territory (witnesses disagree W=13-38 there). h/l do NOT
  move: their residue is shoulders/phase, not tops — a
  separate mechanism, queued next. Ship decision pending.
- Metric-inferred maxima take SROUND-5/8 (`_sround_58` in
  `_metric_bound_rhs`, v33): TRIED 2026-09-25, HELD —
  DO NOT SHIP as-is. Two committed pins force the shape:
  roboto-16 I cap 1456u = 11.375 rounds UP to 12 (native
  bytecode keeps 12 rows; test_y_extent_bounds_round_outward)
  while literata-16 h/l ascender bound 766u = 12.256 rounds
  DOWN to 12 (both witnesses) — plain nearest and bare ceil
  each fail one pin, 3/8 is the only sourced step in range.
  Explicit extent flags keep ceil; two joint fixtures moved
  to straddling-class entries to keep redirect mechanics live
  (same retry/no-leak assertions). Oracle: all four targets
  APPROVE (h C 4→1, l C 3→0) plus ~10 more flips, settled +
  evidence identical — BUT 4 coverage holds (roboto-20
  7/T/Z, literata-14 %) via the geometric gate ("rebuild
  differs from candidate") and 1 borderline flip
  (roboto-14 ( APPROVE→REJECT, W=8 split witnesses).
  Mechanism: solver/render skew — the emitted bytecode still
  rounds these rows up while the solver predicts down; the
  gate is correct to hold. Witnesses split on 7/T/Z tops
  (native 14 vs autohint 15), so neither value is
  witness-wrong, but prediction must equal render. % holds
  via shared-table cascade with no direct flip of its own.
  Unblocks only via compiler alignment (emit matching round
  states for 5/8 rows; gate to zero holds) or revert to v32.
- Shared tables into the bake (`Pipeline.stage_geometry`,
  v34): SHIPPED candidate. The holds were never solver-vs-
  hints: no bytecode emission exists (SCFS bakes solver values
  verbatim), and prepare-vs-solver agree to 0.008px tableless.
  The skew was bake-tableless vs prepare-tabled: geometric()
  built plain Geometry (dropping the record's width_table)
  while prepare() re-wraps TabledGeometry, diverging ~2px
  wherever table-driven derivations differ. The bake now
  carries the record's table (shared values determined before
  solving everywhere: ttfautohint global-first, VTT CVT-first;
  the TabledGeometry docstring sanctions stage-owned
  construction). Full-regen census vs v33: zero pixel moves
  on rendered glyphs; all 12 status moves are
  upstream-rejected → retained (the 4 v33 holds plus 8 more:
  roboto-14 A, roboto-16 [, literata-14 h, ss3-14 v, ss3-16
  F/v, ss3-18 v, ss3-20 v). Oracle: battery identical to v33
  (4/4 targets APPROVE, settled + evidence held) except the
  restored literata-14 h now rendering (C=15 UNSETTLED,
  W=11); restored 7/T/Z/A/[/%/F all UNSETTLED (witnesses
  disagree); ss3-v improved vs v32 (C 20→5, 26→15, 32→15)
  where it was already REJECT-flagged. Single adverse event
  carried from v33: roboto-14 ( APPROVE→REJECT (C 8→10,
  W=8 split witnesses, visual wash at the top row, indirect
  shared-cluster cascade). Coverage 796→808 retained vs
  v27-era. Ship decision pending.
  REVERTED to v32 (39f450c) 2026-09-25: no source breaks the
  7/T/Z tie (native 14 vs autohint 15 — the witnesses
  themselves disagree; no third source adjudicates flat-cap
  frac .22), and the planned option-C narrowing proved
  circular (entry stamps must precede the stage-2 compile but
  tables postdate it). One sourced architectural hint for the
  future, not a rescue: published autohinters determine
  shared values BEFORE per-glyph solving (ttfautohint
  two-step: global analysis of standard widths/heights from
  'o' first, then per-glyph; VTT CVT-first workflow; Shamir
  single simultaneous solve) — our bake-then-reconcile order
  is inverted, which is why agreement failures are possible
  at all. Stage-agreement hardening (+ ascender zones, with
  h/l inside) is the queued project.
- Bake-time cap-entry normalization (v35): REJECTED,
  reverted to v34 uncommitted 2026-09-25. Hypothesis was a
  bake-vs-joint skew behind literata S baking 12 rows vs
  C/G/O/Q 11 (identical crown rows). Instrumented run
  disproved it: bake table and joint redirect agree exactly
  (all five crowns redirect to the entry integer, no
  conflict-retries). The normalize rewrote the shared vote
  instead of mirroring anything: S pixels unchanged on all
  faces while 53/57 moved glyphs drifted FARTHER from
  settled, knocking settled-exact capitals off by up to
  47px (literata-20 X/A/M/H). Oracle battery 48/48
  identical — it cannot see exact→drifted, so a zero-drift
  guard on settled-exact glyphs is queued. Standing result:
  no bake/joint skew exists; the S excess lives
  downstream of the entry pin (see crown-plateau pins).
- Crown-plateau pins (`_pin_crown_plateau`, v36):
  SHIPPED 2026-09-25 (e6483fd). The S excess is a
  floating raster peak: the entry redirect pins one Abs
  row per crown, but literata-16 S's peak (pts 45-47,
  11.53px) sits off the redirected row (pt 51) under pure
  Ratio governance and lights a stray 1px top row. Design
  ties at the plateau (five points at exactly 12.0px
  pre-fit) take the same entry integer through the existing
  ResYAnchor pin path (sourced: VTT anchors attach points,
  plural, to CVT entries). Dust is float-noise cover only
  (1e-6, ledger dust class); contour-size guard carried
  over from the Abs redirect; points with protected
  vertical rows and glyphs with no pinned crown are
  untouched by construction. Full-regen census vs v34: 0
  status moves, sole pixel mover literata-16 S (h 12→11,
  top [1,6,7]→[6,7,7]). Oracle: S evidence REJECT-flag→
  APPROVE (C 9→7, W=8), rest byte-identical. Pinned by 5
  new CrownPlateauTests.
- Cap anchors, pulls, redirects
  (`vote_cap_anchor`, `_cap_redirect`, `_cap_abs_redirect`):
  REPLACED 2026-09-15 with cap heights as ordinary CVT
  entries (`build_cap_table`: voted flat_cap line; spec
  Fig 1-12 shape) consumed through one nearest-entry lookup
  (`_cap_table_lookup`), pins kept as the VTT ResYAnchor
  attachment pattern. v26 regen is pixel- AND
  decision-identical to v1 (0-delta census, 0 differing
  standardize/pin records repertoire-wide): mechanism
  unified, values preserved.
- Cap-CVT rejected variants (evidence over plan): round
  entries dropped (measured overshoots 8-20u sit inside
  flat bands with identical integers; the one round-only
  redirect, ss3-18 `°`, was REJECTED); soft-pull deletion
  rejected 6x on settled glyphs (literata-16 P/S,
  roboto-14 j, ss3-14 8, ss3-20 9/O) so pulls stay as WHY
  load-bearing corrections (the IUP-contradiction theory
  stands refuted); per-row bands without glyph stand-down
  rejected 2x on tall brackets (ss3-14 `(`/`)`, settled)
  so stand-down stays as zone attachment (any entry band),
  which also approved ss3-14 `f`/`l`. Ascender entries
  deferred: the above-band vote is punctuation-contaminated
  (ss3-14: 724u/160 brackets-parens) while ascender tops
  (722-734u) overlap tall punctuation (682-730u) — no
  height threshold splits them; ascender treatment waits
  on stroke-terminal analysis. x-height/numbers/baseline
  entries omitted (no bespoke treatment exists for those
  rows). Pinned by CapTableTests, rewritten substitution
  tests, restored CapSoftPullTests.
- Standardization framework (shared targets into hard rows):
  SOURCED-pattern (CVT value assignment), project-calibrated.
- Joint widen-only + vertical-span skip at 16+
  (`standardize_hard_widths` opted-out branch): WHY — per-point
  three-way evidence (ss3-18 0/o, roboto-16 8) + dual-witness
  oracle; no axis split exists in any source. Accepted under
  the rule's escape hatch, open to challenge.
- Mirror gate (`mirror_phase_ok`): WHY — no direct source
  parent (neither Shamir nor VTT has a symmetry gate; nearest
  analogue is VTT re-centering the median after asymmetric
  linking, TTEngine.cpp:1218, which repairs rather than gates).
  Kept on witness evidence: ablation without it loses a
  column on roboto-20 T (both witnesses 22→34/10→20 prefer
  the gate) and adds 11px on ss3-18 T; neutral elsewhere.
  Docstring cites the median analogue as weak kin since
  2026-09-15 (`mirror_phase_ok`).
- Curved claim-all at 16+ (opt-out claims shared target):
  REMOVE — contradicts Shamir thin-only with no source backing;
  kept only for v1 parity, which no longer outranks sources.
  Depends on the single-width classification landing first
  (scoreboard OPEN item): once 64u-class sides take the 2px
  main by rule, claim-all has no remaining function. Then
  16px curved takes the same gated branch as 14px.
  Confirmed 2026-09-15: no live rejoin target exists (see
  64u entry), so claim-all keeps its v1-parity hold; a
  font-wide floor stays rejected (77-to-17).
- Stem roles (`stem_roles.role_of`, `zones_for_face`):
  DRAFT — SOURCED-pattern on VTT link color (`TheColor`,
  TTFont.cpp:145; consumed per-link as a flag,
  TTGenerator.cpp:736). Second role axis color does not
  cover: zone attachment (stood on/hung from baseline+cap
  zones = anchored, else floating). Not consumed anywhere:
  no behavior change, no census/oracle needed. Wiring into
  `lookup`/standardize is the scoreboard OPEN item below.
  Calibration (zone list without x-height, overshoot-scale
  tolerance) is provisional WHY. Two predicates tried at
  wiring (span-cover, endpoint-touch): each fired only on
  ss3-18/20 `[`, REJECTED under absolute judgment
  (candidate 14/21px from settled W=0 witnesses);
  production wiring reverted. Infra retained (pure, tested)
  for the withholds/caps sequence, which genuinely needs
  roles. Pinned by `test_stem_roles` (12 tests).
- 64u unanimous-1px classes at 16+
  (`cluster_widths` splitting 64u from the main):
  premise CORRECTED 2026-09-15 (was REMOVE): the v19/v20
  regen gates proved the assumed split of n/m/p into thin
  classes does not occur — a role gate wired through
  standardize fired exactly twice repertoire-wide (ss3-18/20
  `[`), both dual-witness rejections, while n/m/p already
  render main-width in v1 via legacy paths. The thin
  classes hold only foundry-thin strokes, i.e. clustering
  is correct as-is. Status: HELD (no change); rejoin rule
  pinned at unit level (`rejoin_main` + link-layer
  scoreboard test), production wiring reverted, reopen per
  the scoreboard's reopen condition.
- Withholds (`_withholds_table`): NEEDS-WHY — exact-equality
  span test retained, with the why now written: a 1px
  cut-in band was tried (arch-probe-v22, 2026-09-15) and
  reverted (v23, 0-delta census). The band's 3 deltas: one
  REJECT under absolute judgment (ss3-14 `-` kept a 2px
  solver hyphen; both witnesses hold 1px — absolute-px
  bands are category-wrong on small glyphs, where a
  thickness-vs-height mismatch is bearings-scale, not a
  span) and two UNSETTLED (roboto-16/20 `1`, witnesses
  disagree W=14/9). No observed case needs absorption
  beyond the existing 1e-6 dust tolerance, so no band of
  any shape stands today; a future band must be relative,
  motivated by an observed mis-shared span, and
  oracle-gated. The predicted role-straddle never
  materialized (o held throughout; p is absent from the
  repertoire), so no role axis was added. Pinned by
  `WithholdSpanTests` (6 tests).
- Zero-twin pins: WHY — sourced pattern is VTT anchors
  (ResXAnchor/ResYAnchor attach points to CVT entries).
- Abs-redirect block: folded into the cap-CVT replacement
  above (entry integers via `_cap_abs_redirect`, contour-size
  guard carried over unchanged).
- Orient non-reversal ban: WHY — solver-robustness scaffolding
  (direction-sensitive outward rounding cannot commute with
  reversal; no paper parent, same class as reflection re-fit
  on the VTT bail-out pattern). Ablation 2026-09-15: ban
  holds by design (orient stalls); forced-reversed extent row
  falls back to nearest (11, not outward 12), so lifting the
  ban silently downgrades extent rounding. Pinned by
  `test_rounded_extent_dist_never_reverses` (stall) +
  `test_reversed_extent_falls_back_to_nearest` (downgrade).
- Reflection re-fit, conflict retry: WHY — solver-robustness
  scaffolding, on the VTT bail-out pattern (fpgm 118 bails
  where no solution exists); numerics, not hinting decisions.

## Not hinting logic (out of scope)

- Driver staging, audits, reports (`build_source_bitmap`,
  `source_bitmap_output`): scaffolding.
- `vtt_*` experiments, `compare_*` harnesses: reference
  tooling, not shipped logic.
- `docs/reference/VisualTrueType` submodule (1bd4ed4),
  `docs/reference/fonts/{papers,specs}`: vendored references.
