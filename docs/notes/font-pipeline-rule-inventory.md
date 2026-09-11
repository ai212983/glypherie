# Non-neural Python font pipeline — current executable rule inventory

Scope: the current approved experimental pipeline executed by
[build_source_bitmap.py](../../tools/font_probe/build_source_bitmap.py)
(`STAGE_ORDER`: source-instantiation → baseline-model →
geometric-candidate → cumulative-fit → component-symmetry →
round-symmetry → curved-width-links / source-junctions diamond →
stem-relative-terminals → curved-stroke-recovery → export).
The separate [source-alignment audit](../../tools/font_probe/audit_source_alignment.py)
runs original instantiation → direct baseline construction with first-on-curve
representatives → graph and native-coordinate verification. Later experimental
stages remain in the approved reference. The audit is a working baseline with
unresolved decisions, rather than a completed conformance claim.

Fidelity owner: [shamir-model-conformance.md](shamir-model-conformance.md).
Source review date: 2026-09-09. The tables inventory active rules; source comparisons
are partial. A related citation establishes provenance, not equivalence.
Visual comparisons are paused until the source-alignment gate below is complete.

Provenance is one of exactly four labels: 'specified',
'conservative assumption', 'experimental replacement', 'unresolved'.
Qualified combinations (e.g. "specified concept + conservative
assumption (numeric values)") are allowed. Pipeline first-writer /
newest-wins ownership is an experimental replacement, not conservative
merely because it contains a guard. Guard mechanical validation is
separate from placement policy. Source verification (does the cited
source actually say this) is separate from mapping (does our code
match it).

Audit queue (single list, in order): inventory → source research →
procedure alignment → operation verification → fresh baseline / human
visual comparison.

## Source keys

- [S-SHAMIR] Shamir 2003, §§3.2–3.6 and Table I.
- [S-EXTRACT] Shamir and Rappoport 1996, feature extraction; exact
  definition mappings are recorded in the conformance document (B02/B05).
- [S-MS-TUT] Microsoft TrueType "fixing rasterization issues" tutorial
  (same-edge / enclosing-bound interpolation concept only):
  https://learn.microsoft.com/en-us/typography/truetype/fixing-rasterization-issues
- [S-MS-TTGEN] Microsoft VisualTrueType `TTGenerator.cpp`, pinned main
  commit `1bd4ed4383f8390b0140e05d330491fcadd3e8e0`, verified 2026-09-09:
  zero-distance Link uses MDRP/ALIGNRP (lines 534–543):
  https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L534-L543 ;
  Interpolate emits IP (lines 652–680):
  https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L652-L680 ;
  Shift emits SHP (lines 1025–1047):
  https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L1025-L1047 .
  These support align/link/interpolation semantics only — not automatic
  detection and not our weighted least-squares objective.
- [S-TT-SPEC] TrueType instruction set reference:
  https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions
- [S-LOCAL] Existing notes in `docs/notes/`: vtt-compiler-diagonals,
  curved-stroke-width-links, shared-stem-hinter,
  repeated-component-symmetry, round-component-symmetry,
  stem-relative-terminal-placement, complete-stem-coverage.

## Baseline model (profile="baseline")

| ID | Source (file:function) | Behavior | Provenance / primary source | Rationale, limits |
| --- | --- | --- | --- | --- |
| R-BASE-ASSEMBLY | [shamir_model.py](../../tools/font_probe/shamir_model.py): `build_font` | Builds feature model, constraints, statistics, templates at requested ppem | Specified procedure per [S-SHAMIR] §§3.2–3.6; settings in [shamir_baseline.py](../../tools/font_probe/shamir_baseline.py) | Reproducible entry; numeric settings are assumptions (B01–B13 in conformance) |
| R-BASE-PREP | [shamir_geometry.py](../../tools/font_probe/shamir_geometry.py): `prepare` | Exact collinear-join removal, extrema insertion, Skia nonzero normalization | Specified (remove redundant lines, §3.3) + conservative assumption (0.003em, 0.04rad, normalization substitution; B01) | Modern substitution while 1997 quality algorithm unverified |
| R-BASE-EXTRACT | [shamir_features.py](../../tools/font_probe/shamir_features.py): `recognize` | Epsilon-vertical/horizontal + curved feature extraction, both-side cardinal check | Specified concept ([S-EXTRACT] §3 epsilon features) + conservative assumption (numeric epsilons, B02) | Tilted-side fix in correction pass; chord-strip checks can exclude near-straight curves |
| R-BASE-STATS | [shamir_segment_fit.py](../../tools/font_probe/shamir_segment_fit.py): `clusters`, called by [shamir_model.py](../../tools/font_probe/shamir_model.py): `build_font` (B03) | Exact font-unit counts, ≥6 occurrences kept, 0.01em nearest association | Conservative assumption (threshold from published example, B03) | Repertoire-dependent; affects shared heights/widths |
| R-BASE-REP | [shamir_representative_search.py](../../tools/font_probe/shamir_representative_search.py): `coordinate_representatives` | Bounded (≤256 evals) coordinated choice among existing on-curve members; score = rejected-relation count in priority order, never pixels. Approved-pipeline only: overrides the first-on-curve baseline policy, which itself performs no search | Experimental replacement ([S-SHAMIR] permits first/middle, supplies no search; conformance §coordinated prototype) | Completion assumption; contour-start sensitivity and true-cycle behavior still open |
| R-BASE-PRIORITY | [shamir_constraints.py](../../tools/font_probe/shamir_constraints.py): `priority`, `resolve` | font > metric > relative > absolute; declaration-order ties with warnings; cycle removal | Specified hierarchy (§3.6) + conservative assumption (tie rule, B09) | Baseline-metric membership fix for y0 links (B09 correction) is in baseline |
| R-BASE-SCHED | [shamir_point_schedule.py](../../tools/font_probe/shamir_point_schedule.py): `schedule`; [shamir_constraints.py](../../tools/font_probe/shamir_constraints.py): `resolve` | Priority-sorted insertion with independence test, tie warnings, cycle removal of lowest-priority member; topological point-dependency order emission | Specified procedure ([S-SHAMIR] §§3.5–3.6, B13 — ordered priority graph, not a global weighted optimizer) | Weighted LS/MILP would replace this; not in baseline |
| R-BASE-COMPLETE | [shamir_baseline_completion.py](../../tools/font_probe/shamir_baseline_completion.py): `complete_defaults` | Contour-neighbour Ratio default refs; Ratio extrapolation + perpendicular completion; unrounded Dist for single-ref/zero-span | Conservative assumption with IUP topology precedent (B08); Apple/MS IUP docs select by contour order | One free degree completed; axis-specific IUP touch semantics out of scope |
| R-BASE-MEMBER | [shamir_baseline_members.py](../../tools/font_probe/shamir_baseline_members.py): `assemble_member_graph` | Late ordinary-member attachment after reduced graph; explicit singular failure | Conservative assumption (B11; [role/completion decisions](shamir-role-completion.md)) | Simultaneous final solve is diagnostic only |
| R-BASE-NATIVE | [shamir_baseline_solver.py](../../tools/font_probe/shamir_baseline_solver.py): `compile_baseline`, `_round_pixel`, `evaluate_baseline` | Deliberate requested-size SCFS substitution (not paper Table I procedure): solves both projected equations at requested integer ppem, emits cardinal SCFS; 26.6 quantization; half-away nearest-pixel rounding; independent simultaneous-equation oracle. Graph-equation oracle verifies quantization ≤1/128px; this does NOT verify scalable CVT/TrueType behavior | Experimental replacement as adapter (B12); numeric rounding conservative assumption | Rationale: the deliverable is a bitmap at an explicit size, so solved coordinates can feed scan conversion directly. This remains a translation departure; scalable CVT programs and interpreter-state behavior need separate verification |
| R-BASE-TEMPLATE | [shamir_baseline_templates.py](../../tools/font_probe/shamir_baseline_templates.py) via `constraints_for` | Two published sequence examples, explicit sub-automata, reset traversal; minimal original-offset recipes | Specified examples + conservative assumption (authored recipes, B05; [S-EXTRACT] §4.4, [S-SHAMIR] §3.5) | Full author recipe library unrecovered; unrecognized forms use basic features/defaults |
| R-BASE-DOM | [shamir_segment_dominance.py](../../tools/font_probe/shamir_segment_dominance.py) | One dominant relation per segment before native-point resolution; one-font-unit tangent/control membership | Specified concept + conservative assumption (quantization, B06; §§3.5–3.6) | Shared-role interpretation recorded in [role/completion decisions](shamir-role-completion.md); grouping tolerance remains an assumption |
| R-GRAPH-EQ | [shamir_constraints.py](../../tools/font_probe/shamir_constraints.py): `freeze_ratio`, `ratio_coefficient` | Signed local/shared distances honored; single-coefficient Ratio assumes weights sum to one | Specified + conservative assumption (B07) | Geometry never overwrites authored values |
| R-EXTRACT-CARD | [shamir_features.py](../../tools/font_probe/shamir_features.py): `side_is_cardinal` | Both-side epsilon bounding-box cardinal classification | Specified definition ([S-EXTRACT] §3; correction pass) | First-side-angle-only classification was a confirmed mismatch, now fixed |
| R-EXTRACT-INTERIOR | [shamir_features.py](../../tools/font_probe/shamir_features.py): `Interior` | Analytic line/quadratic intersection partitions for connecting segments; complete support/counter strips | Conservative assumption (B02) | Chord-strip checks can exclude near-straight curved boundaries |
| R-EXTRACT-LADDER | Baseline B04 per conformance | Similar-length consecutive strokes, equal counters; triple windows; epsilon equality | Conservative assumption (B04; [S-EXTRACT] §5, [S-SHAMIR] §3.5) | Twice-width minimum and 10% allowance removed |
| R-NATIVE-COMPILE / R-SOURCE-INST (one rule) | [build_source_bitmap.py](../../tools/font_probe/build_source_bitmap.py): `install`, `stage_font`; `vf` instantiation | Variable-font instantiation from source + checksum gate, no saved statics; per-glyph SCFS compile; outline-preservation + native-prediction gates; maxStack 16 | Conservative assumption (modern preparation + adapter mechanics) | Inputs hashed into provenance; export also checks white-counter preservation |

## Geometric candidate + cumulative fit

| ID | Source (file:function) | Behavior | Provenance / primary source | Rationale, limits |
| --- | --- | --- | --- | --- |
| R-GEO-REORIENT | [shamir_reorientation.py](../../tools/font_probe/shamir_reorientation.py): `prototype` | Reorient distance dependencies with signed values; construct a solution retaining recorded equations; allow a unique lowest-priority single-removal repair, compatible defaults and parallel-chain substitution. | Experimental replacement | Repairs inconsistent segment attachment while checking against an independent equation oracle. Bounded construction can hold. |
| R-GEO-ANCHOR | [shamir_parent_anchor.py](../../tools/font_probe/shamir_parent_anchor.py): `replace_anchors`, `experiment` | Replace an oblique free-side absolute anchor sharing a cardinal anchor with complementary cardinal placement; retain relative equations. | Experimental replacement; Microsoft parent-placement concept only | Avoids unstable projected parent placement. Direction comparison and replacement policy are ours. |
| R-GEO-SERIF | [vtt_serif_experiment.py](../../tools/font_probe/vtt_serif_experiment.py): `detect`, `fit` | Detect geometric serif roles, fit their members, and reject overlap with another owned correction. | Experimental replacement; VTT-inspired ([S-LOCAL]) | Automatic role detection and bounded fitting are project choices; VTT source equivalence needs a separate audit. |
| R-GEO-CTERM | [opposing_terminals.py](../../tools/font_probe/opposing_terminals.py): `detect`, `fit` | Detect opposing outer terminals; round each extension with `floor(length*scale+.5)`, preserve tip direction, interpolate return curves. | Experimental replacement | Default `shared=False` keeps individual lengths; optional averaging is outside the default call. Detection bounds (.1–.4em extension, .15em tip) and pairing are ours. |
| R-GEO-PTERM | [vtt_terminal_links.py](../../tools/font_probe/vtt_terminal_links.py): `candidates`, `values`, `program`; [geometric_candidate.py](../../tools/font_probe/geometric_candidate.py): `finish` | Use the smaller paired source extension as a shared value, floor its scaled length, then interpolate terminal members. | Experimental replacement; source relations inspired by VTT ([S-LOCAL]) | Shorter paired extensions received visual preference. Pair detection, smaller-value choice and floor policy are ours; cut-in and overlap checks bound support. |
| R-GEO-EXPORT | [geometric_candidate.py](../../tools/font_probe/geometric_candidate.py): `finish` | CVT + native assembly emission per verified glyph | Conservative assumption (adapter mechanics) | Only verified glyphs continue downstream |
| R-CUM-PREPARE | [cumulative_hinter.py](../../tools/font_probe/cumulative_hinter.py): `prepare` | Geometric rebuild agreement check, coordinated support, joint fit (`complete_stems=True, continuations=True`) | Experimental replacement (our integration; interpolation concept only from [S-MS-TUT]) | Rejections are explicit, never silent fallback |
| R-CUM-OWN | [cumulative_hinter.py](../../tools/font_probe/cumulative_hinter.py): `claim` | First-writer point×axis ownership; conflicts raise | Experimental replacement (phase-ownership policy; B11 interpretation recorded in [role/completion decisions](shamir-role-completion.md)) | The conflict check enforces our placement policy; passing that check does not establish source conformance |
| R-JOINT-SOLVE | [joint_stroke_fit.py](../../tools/font_probe/joint_stroke_fit.py): `constrained_fit` (docstring) | Hard/goal/target least-squares joint solve. Weights: source point and contour-edge displacement penalties each weight 1; each whole-side width/alignment residual weight 4 (squared factor 2). Explicit experimental choices, neither Shamir nor Microsoft policy | Experimental replacement ([S-SHAMIR] procedure is the ordered priority graph §§3.5–3.6, not a global weighted optimizer) | Hard-metric incompatibility and joint residuals raise |
| R-JOINT-STEM | [joint_stroke_fit.py](../../tools/font_probe/joint_stroke_fit.py): `stem_relations` | Stem relation construction: exact cardinal contour runs per stem/bar side; contiguous-run expansion along the contour while displacement along the side normal stays within 1e-8; both sides need ≥2 points or the constraint is held (`incomplete straight-side support`) | Experimental replacement | Same-side align vs opposite-side Dist/PDist distinction follows [S-SHAMIR] concept; grouping is ours |
| R-JOINT-CONT | [joint_stroke_fit.py](../../tools/font_probe/joint_stroke_fit.py): `continuation_relations` | Continuation relations: one adjoining straight segment within 5° of a protected side (cosine gate `cos(5°) ≤ cosine < 1−1e-12`); preserves an existing unrounded alignment in its own direction; no recursive propagation | Experimental replacement | Near-parallel/degenerate handling is our choice |
| R-JOINT-TCOMP | [joint_stroke_fit.py](../../tools/font_probe/joint_stroke_fit.py): `terminal_competitor` (docstring: "A broad, short pair can be the ends of an intersecting longer bar") | Filters broad short candidate 'stems' (length < width) that are ends of an intersecting longer perpendicular bar (longer, narrower, perpendicular within 1e-8 dot, overlapping bounding boxes); excluded as `excluded-terminal-length`, not fitted as stems | Experimental replacement (our filter) | Not a point-ownership guard; ownership is R-CUM-OWN |
| R-JOINT-FIT | [joint_stroke_fit.py](../../tools/font_probe/joint_stroke_fit.py): `fit` | Orchestrates stem+continuation+reflection fit; honors upstream ownership and order relations | Experimental replacement | Flags `complete_stems`, `continuations`, `curve_reflection` set by caller |
| R-FEAT-COORD | [feature_coordination.py](../../tools/font_probe/feature_coordination.py): `shared_diagonal_widths`, `reflected_outline`, `diagnostics` | Shared diagonal width coordination; source-axis point reflection with per-support outer-height behavior; diagnostics carry reflection residuals | Experimental replacement ([S-LOCAL] background) | Reflection source is ours |
| R-SHARED-STEM | [shared_stem_hinter.py](../../tools/font_probe/shared_stem_hinter.py): `fit`, calling [stem_widths.py](../../tools/font_probe/stem_widths.py): `inherit_widths` | Shared-stem hinter pass (called inside cumulative prepare path); inherits widths across linked strokes; source end-cap corners included only with an exact shared height | Experimental replacement ([S-LOCAL] shared-stem-hinter) | Scoped to shared stems; ownership-gated |
| R-CUM-REFLECT | [cumulative_hinter.py](../../tools/font_probe/cumulative_hinter.py): `reflect` | Ink-driven reflection pass on fitted floats, recompiled like any stage | Experimental replacement (source-reflection rules are ours) | Needs rendered ink; pixel-dependent |
| R-CUM-VALIDATE | [cumulative_hinter.py](../../tools/font_probe/cumulative_hinter.py): `validate_geometry`, `finalize` | Source-vs-fitted geometry validation; final point assembly with upstream audit | Conservative assumption | Failures are explicit rejections |
| R-XSECT | [cross_section_widths.py](../../tools/font_probe/cross_section_widths.py): `section`, `system`, active via [joint_stroke_fit.py](../../tools/font_probe/joint_stroke_fit.py) imports and [build_source_bitmap.py](../../tools/font_probe/build_source_bitmap.py) (`export_graph`, `system` for protected metric/parameter residual gate) | Cross-section width system construction + per-section evaluation; protected metric/parameter residual gate (1/64px) in branch stage | Experimental replacement | Helper module, not optional |

## Symmetry, width, junction, terminal, recovery stages

| ID | Source (file:function) | Behavior | Provenance / primary source | Rationale, limits |
| --- | --- | --- | --- | --- |
| R-COMP-SYM | [repeated_component_symmetry.py](../../tools/font_probe/repeated_component_symmetry.py): `fit` | Repeated-component symmetry; skips owned points (`held-owned`); 1/64px coverage quanta | Experimental replacement ([S-LOCAL] repeated-component-symmetry; sources support symmetry concept only) | Implementation ours |
| R-ROUND-SYM | [round_component_fit.py](../../tools/font_probe/round_component_fit.py): `fit`, conditionally calling [joint_ring_placement.py](../../tools/font_probe/joint_ring_placement.py): `place` | Round-component fit; ownership tolerance 1/128px; span check 1/64px. Subrule: when multiple counter-bearing components exist, `place` preserves source center vectors around the isolated bar; unplaced placements hold (`held-placement`) | Experimental replacement ([S-LOCAL] round-component-symmetry) | Percentage/raster variants are caller options; ring placement is an active subrule via the conditional call path, not a separate stage |
| R-CURVE-WIDTH | [curved_width_links.py](../../tools/font_probe/curved_width_links.py): `detect`, `fit` | Bow/arc width links; optional `reconstruct_curves` | Experimental replacement (approved whole-stroke variant is separate, conformance §correction; [S-LOCAL] curved-stroke-width-links) | Alignment cutoff can discard displaced extrema |
| R-JUNCTION-CLASS | [classify_junctions.py](../../tools/font_probe/classify_junctions.py): `classify` | Junction classification; probe distances 0.02/0.055/0.09em, min arm turn 5° | Conservative assumption (our probe geometry) | Thresholds are ours, not source-prescribed |
| R-JUNCTION-BRANCH | [build_source_bitmap.py](../../tools/font_probe/build_source_bitmap.py): `branch_stage` (junctions=True) | Source-junction diamond branch: builds the ORIGINAL static model (`from_font` on static path, `normalize_boundaries`), sets `model.source_junctions=True`, classifies extrema via `curved_detect`; then calls `curved_width_fit` with `reconstruct_curves=True` — it does not call `junction_terminal_fit` here | Experimental replacement (diamond branch; newest wins per glyph) | Parallel with curved-width branch; both read round-level rendering, never each other's output |
| R-JUNCTION-FIT | [junction_terminal_fit.py](../../tools/font_probe/junction_terminal_fit.py): `fit`, called by [curved_stroke_recovery.py](../../tools/font_probe/curved_stroke_recovery.py): `fit` | Reconstruct local source curve boundaries with retained attachments; validate owned coordinates and edge/target limits. | Experimental replacement | This helper belongs to final curved-stroke recovery, independently of the earlier source-junction branch. |
| R-TERM | [stem_relative_terminals.py](../../tools/font_probe/stem_relative_terminals.py): `detect`, `fit` | Stem-relative terminal placement; 1/64px move gate; overlapping ownership raises | Experimental replacement ([S-LOCAL] stem-relative-terminal-placement; VTT terminal-link background in vtt-compiler-diagonals) | Standalone stage after the diamond |
| R-RECOVERY | [curved_stroke_recovery.py](../../tools/font_probe/curved_stroke_recovery.py): `fit` (calls `local_fit` = `junction_terminal_fit.fit`) | Curved-stroke recovery; anchor gate 1/64px; retains independent bar placement; reuses both fitted curve-height anchors with source width profile | Experimental replacement (approved for 7 cases, conformance §correction) | Invocation of R-JUNCTION-FIT internals is part of this stage |

## Numerical thresholds (all ours unless noted; each links its owner function/file)

| ID | Value | Owner | Provenance |
| --- | --- | --- | --- |
| R-NUM-DIST | 0.003em distance epsilon (B02) | [shamir_features.py](../../tools/font_probe/shamir_features.py): `recognize` | Conservative assumption, no source default |
| R-NUM-ANGLE | 0.04rad angle epsilon (B02) | [shamir_features.py](../../tools/font_probe/shamir_features.py): `recognize` | Conservative assumption |
| R-NUM-ALIGN | 0.012em curved alignment; .024/.048 labeled experiments only | [shamir_features.py](../../tools/font_probe/shamir_features.py): `recognize` | Conservative assumption |
| R-NUM-HEIGHT | ≥6 exact font-unit occurrences kept (B03); 0.01em nearest association | [shamir_segment_fit.py](../../tools/font_probe/shamir_segment_fit.py): `clusters` | Threshold from published example (explicit setting) |
| R-NUM-DET | Determinant boundary 32 machine epsilons (B10) | [shamir_baseline_solver.py](../../tools/font_probe/shamir_baseline_solver.py) | Conservative numerical assumption in the baseline. The condition-number limit 4 in `shamir_constraints.independent` belongs to the experimental solver, not this path |
| R-NUM-ROUND | Half-away ties; native drift gate 1/128px; stage agreement 1/64px | [shamir_baseline_solver.py](../../tools/font_probe/shamir_baseline_solver.py): `_round_pixel`; [cumulative_hinter.py](../../tools/font_probe/cumulative_hinter.py): `validate_geometry`; branch/terminal/recovery stages | Our numeric choices |
| R-NUM-JUNC | Probe distances 0.02/0.055/0.09em; 5° minimum arm turn | [classify_junctions.py](../../tools/font_probe/classify_junctions.py): `classify` | Our probe geometry |
| R-NUM-OWN-TOL | Round ownership tolerance 1/128px; span/coverage gates 1/64px | [round_component_fit.py](../../tools/font_probe/round_component_fit.py): `fit`; [repeated_component_symmetry.py](../../tools/font_probe/repeated_component_symmetry.py): `fit` | Our choices |
| R-NUM-CONT | Continuation cosine gate cos(5°) ≤ cosine < 1−1e-12 | [joint_stroke_fit.py](../../tools/font_probe/joint_stroke_fit.py): `continuation_relations` | Our choice |
| R-NUM-STEMRUN | Contiguous-run normal deviation ≤1e-8; both sides ≥2 points | [joint_stroke_fit.py](../../tools/font_probe/joint_stroke_fit.py): `stem_relations` | Our choice |
| R-NUM-LS | Point/edge displacement weight 1; whole-side residual weight 4 | [joint_stroke_fit.py](../../tools/font_probe/joint_stroke_fit.py): `constrained_fit` (docstring) | Experimental replacement weights, not a source default |

## Priority / ownership policy (ours unless noted)

| ID | Policy | Provenance |
| --- | --- | --- |
| R-POL-HIER | font > metric > relative > absolute; declaration-order ties with warnings (B09) | Specified hierarchy ([S-SHAMIR] §3.6); tie rule ours |
| R-POL-BASELINE-KEEP | Exact horizontal y0 links keep character-metric priority (A-foot correction) | Implements §3.6 baseline priority; no new rounding rule |
| R-POL-OWN | First-writer point×axis ownership wins; cumulative conflicts raise; diamond branches newest-wins per glyph | Experimental replacement; B11 interpretation recorded in [role/completion decisions](shamir-role-completion.md) |
| R-POL-SEARCH | Search budget 256 evals/glyph; geometry-ordered descent; strict improvement; acyclic keeps initial | Our completion assumption |
| R-POL-REJECT | Exceptions are rejections carried as upstream rejections, never silent fallbacks | Our policy |

## Optional / paused experiments (outside the default pipeline)

[central_upright_shape.py](../../tools/font_probe/central_upright_shape.py) / [central_upright_fit.py](../../tools/font_probe/central_upright_fit.py) (require a
`center_fit` callback that `build_source_bitmap` does not pass —
disabled in the active path), [feature_stroke_fit.py](../../tools/font_probe/feature_stroke_fit.py) (paused MILP
draft, weights 3/1/2 — experimental, no candidate),
[both_axis_symmetry.py](../../tools/font_probe/both_axis_symmetry.py), [source_relative_balance.py](../../tools/font_probe/source_relative_balance.py), member-alignment full run
(unpromoted, paused with other visual experiments; verify its summary
before citing), and all
`compare_*` harnesses. [source_constraints.py](../../tools/font_probe/source_constraints.py): `assess`/`select`
(`source_shape`, `counters`) are called only from compare/paper
harnesses ([compare_paper_prototypes.py](../../tools/font_probe/compare_paper_prototypes.py),
[compare_shamir_pipeline.py](../../tools/font_probe/compare_shamir_pipeline.py), [paper_gridfit.py](../../tools/font_probe/paper_gridfit.py)) — file existence
does not make them active; they are outside `build_source_bitmap`
`STAGE_ORDER`. VTT compiler/diagonal/serif notes are background, not
pipeline stages. Native SCFS adapter scope (B12) is narrower than
paper scalable hints by design.

## Important uncovered assumptions (not source-prescribed)

- Geometry thresholds (R-NUM-*) have no published numeric defaults; the
  1996/2003 texts reviewed supply no epsilon numbers. Wider alignment
  settings change output non-monotonically via shared statistics.
- The active joint least-squares solver replaces the paper's ordered
  priority-graph procedure. The separate MILP draft is paused. Weights R-NUM-LS are ours ([S-MS-TTGEN]
  supports align/link/interpolation semantics only, not our objective).
- Ownership, first-writer-wins, diamond newest-wins, and source-reflection
  rules are our experimental replacement integration policy; B11
  shared-role handling is a documented conservative interpretation.
- Coordinated representative search (budget, scoring, descent order) and all
  symmetry/width/junction/terminal/recovery stage internals are our own;
  sources support at most the bare concept (align/width links, symmetry).
- Native SCFS adapter (B12, R-BASE-NATIVE) preserves the final-artifact
  bitmap at one explicit size; it does not reproduce scalable CVT hint
  programs. VTT notes are background only.

## Working-path verification — 2026-09-09

[Source-alignment report](../../tools/font_probe/out/source-alignment-audit-v1/source-alignment-report.json):
12 original-source font builds, 972 glyph-size cases, zero graph/construction/native
failures. Maximum coordinate error: 0.007812500000070166px, within the declared
1/128px plus floating-point allowance. Input and output hashes verified.
The focused suite passed 64 tests. These checks verify the selected equations and
execution; baseline source decisions remain open.

Reproduce from the repository root:

```sh
OPENBLAS_NUM_THREADS=1 PYTHONPATH=tools/font_probe \
  tools/font_probe/.venv/bin/python tools/font_probe/audit_source_alignment.py \
  --output tools/font_probe/out/source-alignment-audit-next
```

The output directory must be fresh. Fonts and graph reports are diagnostic
artifacts; this command produces no visual review gallery. The approved
`build_source_bitmap.py` algorithm remains unchanged.

The [role/completion follow-up](shamir-role-completion.md#verification-results)
passed 77 focused tests and all 972 cases in audit v2. Selected graphs and native
coordinates match v1; the added guard rejects invalid late shared-role proposals.

## Alignment gate and next actions

1. Confirm rule coverage from the executable entry points, including overrides
   and helper policies. Record source sections and code functions separately.
2. Research open decisions in preparation/extraction (B01–B05), segment grouping
   and membership tolerances (B06). The [role/completion decisions](shamir-role-completion.md)
   record B08/B11 interpretations. Retain explicit conservative
   choices only with the research findings and support limits recorded.
3. Use the representative graph procedure directly in the working baseline.
   Keep the source-selection search, weighted solve, symmetry and recovery
   procedures in the experimental reference until individually justified.
4. Verify graph construction, dependency order, equation semantics and native
   quantization. Passing execution checks alone leaves source decisions open.
5. Continue the [B12 native translation audit](shamir-native-translation.md):
   the source-font audit accounts for 972 cases, with 910 nonempty programs,
   12 verified empty no-ops and 50 vector rejections. Shared CVT parameters are
   all supported integers. The [paired-vector investigation](shamir-native-paired-vectors.md)
   records false stagnation in the bounded native iteration experiment; retain
   the 50-case rejection. The [direct arithmetic prototype](shamir-native-paired-arithmetic.md#native-prototype-and-decision)
   passes all 124 runtime-input pairs. The [native parent contract](shamir-native-parent-precision.md)
   uses current 26.6 point state; its cardinal reference passes 54 graph/size cases
   and 528 instruction-prefix checks. Verify oblique movement, direct-solver
   dependencies and scalable target/range/state handling before choosing the adapter.
   Produce the fresh visual baseline once the preceding decisions are settled,
   then evaluate differences and choose improvements with the user.

### Completion policies

The reduced representative graph uses `shamir_baseline_solver._complete`, with
projected-nearest references when supplied and original-coordinate defaults when
none are supplied. Ordinary members later use the contour-neighbour policy in
`shamir_baseline_completion.complete_defaults`. These are distinct choices under
B08; the [decision record](shamir-role-completion.md) explains their source basis
and limitations. Neither is the complete Microsoft IUP procedure. Cycle removal's original-
position fallback is also an assumption, separate from published priority removal.

## Focused complete-edge diagnostic (preserved, concise)

Source Sans 3 16/20px `+` stays straight through baseline, equation
reorientation, geometric corrections, and initial joint fit; reflection
then splits each upright side by 0.2px and each outer arm edge by 1px.
Reflection releases alignment IDs 5, 11, 14, 16, 17 and 22 in both
cases. The least-squares objective prefers the distorted center (4px at
16px, 5px at 20px): score 10.8 versus 12 for the straight alternative.

| ID | Implementation | Provenance | Scope and verification |
| --- | --- | --- | --- |
| R-MEMBER-PRESERVE | [joint_stroke_fit.py](../../tools/font_probe/joint_stroke_fit.py): `select_member_alignments`, opt-in `fit(...preserve_member_alignments=True)` | [S-SHAMIR] §§3.5–3.6 member-distance/alignment relationships; [S-MS-TTGEN] same-edge link semantics. Keeping these as hard equations inside our least-squares solver is an experimental integration choice. | Existing unrounded, zero-distance, source-exact cardinal `align-N` links between on-curve points only. No inferred pairs or identity selection. Font/metric/ownership conflicts hold. Full diagnostic run exists; experiment unpromoted and visual review paused. |

This correction does not establish conformance of the whole solver.

[S-SHAMIR]: ../reference/fonts/papers/shamir-2003-constraint-based-hinting.pdf
[S-EXTRACT]: https://pages.cs.huji.ac.il/sites/www-arir/storage/extraction-typographic-elements.pdf
[S-MS-TUT]: https://learn.microsoft.com/en-us/typography/truetype/fixing-rasterization-issues
[S-MS-TTGEN]: https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp
[S-TT-SPEC]: https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions
[S-LOCAL]: shamir-model-conformance.md
