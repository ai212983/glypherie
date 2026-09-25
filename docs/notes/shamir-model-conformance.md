# Shamir model conformance and baseline workflow

Status: Active — inventory and source alignment; visual comparison paused
Reviewed: 2026-09-10

## Objective and current status

Build a model that follows the papers as faithfully as available sources allow.
Inventory its rules, research unspecified details, align the implementation, and
verify its operations. Evaluate the fresh baseline visually with the user after
that work, then choose improvements.

The approved Python generator combines `profile="baseline"` with a caller-side
representative search and later experimental fitting stages. That combined output
is a useful comparison reference; visual approval does not establish source
conformance. The source-alignment working path calls the baseline model directly
with first-on-curve representatives and excludes those later fitting stages.

The baseline still contains documented interpretations for extraction, shared
segment roles and default completion. Its size-specific SCFS export substitutes
for the paper's scalable instruction translation. Each retained choice needs a
source comparison, rationale and verification status before baseline acceptance.

This document owns the source audit, decisions and baseline readiness record.
The [implementation plan](../plans/font-legibility-improvements.md) owns broader
pipeline delivery; [font legibility](../reference/font-legibility.md) retains
methodology and reading material.

The [current executable rule inventory](font-pipeline-rule-inventory.md) maps
active rules and thresholds to code, primary sources, interpretations, and the
remaining source-to-code audit queue. The complete-edge trace and earlier
specimens remain diagnostic evidence while source alignment proceeds.

## Current alignment pass — 2026-09-09

The separate [audit entry point](../../tools/font_probe/audit_source_alignment.py)
calls `build_font(profile="baseline")` directly from original instantiated fonts.
It uses the existing first-on-curve representative policy described in §3.5,
followed by the representative graph and member completion. The approved
pipeline's search and later fitting passes remain in the experimental reference.

[Verification evidence](../../tools/font_probe/out/source-alignment-audit-v1/source-alignment-report.json):
12 builds and 972 glyph-size cases passed construction, graph and native checks;
64 focused tests passed. Numerical success establishes execution agreement with
the selected equations. The role/completion follow-up below records the current
decisions. Preparation/extraction, membership tolerances and B12 translation
remain before visual review.
B12 metadata now identifies the adapter as an experimental replacement (decision
metadata version 5); the rendering algorithm has not changed.

## Shared-role and completion decisions — 2026-09-09

The [bounded decision record](shamir-role-completion.md) settles the working
interpretations for B06 representative selection, B08 defaults and B11 shared
roles. Existing equations and reference policies are retained. Shamir specifies
the graph and Ratio operations; the missing shared-role and reference-selection
details remain explicitly identified as our conservative choices.

Verification passed: 77 focused tests and all 972 cases in the original-source
audit. Reduced/final graphs and native-coordinate records match the preceding
audit; links and exact evidence are in the decision record.

The production scheduling boundary now also rejects shared-representative
proposals discarded by late assembly. Such proposals must participate in reduced
priority resolution. The diagnostic assembler remains available separately.
Preparation/extraction, membership tolerances and native translation remain in
the baseline readiness queue. Visual comparison stays paused.

## Native translation comparison — 2026-09-09

The [B12 operation audit](shamir-native-translation.md) compares the SCFS adapter
with the paper's closely corresponding native commands. Of 114 synthetic cases,
101 match exactly and 13 differ by at most 1/64px per coordinate. Separately
quantized native operands explain the worked cardinal cases; individual oblique
traces and coupled graph translation remain open. Figure 9's MIRP/ALIGNRP check
also demonstrates required reference-point propagation.

An opt-in native graph compiler now exercises coupled relations and dependent
members with explicit graphics state and unsupported-mapping diagnostics. All
40 synthetic executions match independently authored instruction references;
20 tests pass across the operation and sequence suites. The [sequence results](shamir-native-translation.md#sequence-verification)
record finite-precision residuals and operation-order differences.

The [source-font coverage audit](shamir-native-translation.md#source-font-coverage--2026-09-10)
accounts for 972 cases: 910 nonempty programs execute, 12 empty outlines have
verified no-op translations, and 50 reject near-perpendicular movement vectors.
All selected shared parameters fit the integer CVT contract. Thirty-eight tests
pass; successful execution leaves source fidelity open, and native/SCFS coordinate
differences remain diagnostic.

Production B12 remains an experimental replacement. The [paired-vector investigation](shamir-native-paired-vectors.md)
preserves the selected equations. Its bounded native iteration experiment finds
false stagnation and retains the 50-case rejection. The [direct arithmetic investigation](shamir-native-paired-arithmetic.md)
verifies isolated arithmetic for all 124 runtime-input pairs; 30 still exceed the
original float-parent tolerance. The [parent-precision decision](shamir-native-parent-precision.md)
uses current 26.6 point state for native parity. Its independent cardinal reference
passes 54 complete graphs/sizes and 528 instruction-prefix checks. Verify oblique
movement, direct-solver dependencies, scalable target capture, range guarantees
and graphics state before adoption.
Preparation/extraction and membership tolerances remain in the readiness queue.
Visual review stays paused.

## Feature-fitting decision audit

Reviewed: 2026-09-09

- Shamir 2003 §§3.5–3.6, saved paper [shamir-2003-constraint-based-hinting.pdf](../reference/fonts/papers/shamir-2003-constraint-based-hinting.pdf):
  representative per segment, same-side distance/alignment links, opposite-side
  Dist/PDist, topological dependency resolution and priority removal. Supports
  coherent segment fitting; global weighted optimization would replace this procedure.
- Microsoft [fixing rasterization issues](https://learn.microsoft.com/en-us/typography/truetype/fixing-rasterization-issues),
  sections "The trouble with the outlines" and "An interpolation to place the
  crossbar": same-edge links/shifts; interpolate crossbar placement between
  enclosing bounds then link its width. These instructions define local tradeoffs;
  a global weighted solver and whole-glyph reflection need separate justification.
- The current unpublished `feature_stroke_fit.py` draft MILP, L1 weights 3/1/2,
  hard reflection thresholds and outer-bound relaxation are experimental choices,
  not paper/Microsoft requirements. The draft is paused pending source-backed
  design revision and verification. It has produced no review candidate.

## Workflow

### 1. Inventory the complete model

Trace each stage from the paper to code: input and outline preparation, extraction,
measurements, templates, representative selection, constraint construction,
defaults, conflict resolution, scheduling and native instruction generation.
Record every replacement and every implementation of an unspecified detail,
including thresholds, rounding, degeneracies and unsupported cases.

Classify each decision as **specified**, **unresolved**, **conservative assumption**
or **experimental replacement**. A stage can contain several decisions with
different classifications. Treat absence from the text reviewed so far as
unresolved until the research step is complete.

### 2. Research each unresolved decision

Before designing or implementing each new rule — baseline or experiment —
inspect the relevant paper section and Microsoft documentation/source first.
Record the exact source location, the specified behavior, and differences;
consult the implementation source when behavior matters. Classify unspecified
decisions after research and justify the conservative interpretation;
explicitly label experimental departures.

Search online for the authors' related publications, follow-up work, theses,
supplements, source code and technical descriptions. Prefer primary sources.
Record the search date, queries, sources inspected, relevant page/section and
findings for each decision. Distinguish inaccessible material from material that
was inspected and left the question unanswered.

Compare sources by their scope and version. A later improvement can inform an
experiment; it changes the baseline only when it clarifies the target method.
Record conflicting descriptions and the reason for the interpretation chosen.

When this search yields no applicable specification, choose the simplest
conservative implementation consistent with the established rules. Preserve
geometry and published relationships where the method permits, expose unsupported
cases explicitly, and document numerical limits. Visual preference alone cannot
justify replacing a specified procedure or tuning an unresolved detail.

### 3. Implement and verify baseline decisions

Implement the specified procedure and the researched conservative assumptions.
Keep experimental replacements separately selectable, with their decision IDs.
A necessary retained departure needs a concrete scope rationale and an explicit
review outcome; identifying it as an experiment is not a justification.
For each decision, verify equations, dependency behavior, geometry and error
handling using focused examples derived from the source or independent invariants.

Audit both selected and rejected constraints. Test exceptional cases as well as
ordinary ones: cycles, degeneracies, near-parallel directions, duplicate references,
curves, overlaps, component boundaries and finite-precision execution. Review
existing tests for assertions that encode our experimental policy as a requirement.

Numerical failures require tracing back to the source contract and implementation.
Any necessary departure becomes an explicit decision with research and evidence.
Internal renders may help diagnose such failures; aesthetic tuning belongs after
baseline evaluation.

### 4. Freeze and visually evaluate the baseline

The baseline is ready for visual evaluation when:

- Every audited decision has a source-backed implementation or a researched,
  documented conservative assumption with a support boundary.
- Every experimental replacement is excluded or has an explicit reviewed reason
  for retention. The requested-size adapter (B12) remains pending that review.
- Focused fidelity checks and native execution checks pass within justified
  tolerances; remaining limitations are explicit.
- Source, configuration, input-font, output-font and tool-version records identify
  a reproducible baseline and its exact assumption set.

Render that baseline and review it with the user through images first. The initial
calibration set is Roboto, Literata and Source Sans 3 at 14/16/18/20px; these are
integration candidates and calibration targets for a general font pipeline.
Face/role assignments are independent of this work. Board verification comes later.

Provide native-size text, enlarged individual glyphs and clear baseline labels.
Review the full repertoire, with particular attention to stems, joins, curves,
counters, diagonals, punctuation, spacing and consistency between glyphs and sizes.
Confirm findings with individual crops and native pixel or outline evidence.
Record the user's assessment and all identified defects against the frozen build.
Visual defects are valid baseline results; visual approval and fidelity are
separate conclusions.

### 5. Select and evaluate improvements

Use the baseline findings to choose the next aspect with the user. Change one
aspect at a time and compare against the frozen baseline. Each experiment records
its decision ID, hypothesis, algorithm change, affected cases, full-corpus effects,
numerical checks and user evaluation. Preserve the baseline for subsequent
comparisons. Adoption is an explicit decision supported by that evidence.

## Decision record

For each replacement or unspecified detail, maintain one entry here containing:

| Field | Required content |
| --- | --- |
| ID and stage | Stable ID, precise question and affected code |
| Published requirement | Source URL, page/section, rule and interpretation |
| Research | Date, queries, inspected sources, findings and access gaps |
| Current implementation | Algorithm, settings and relationship to the rule |
| Baseline decision | Specified procedure or conservative assumption, rationale and support boundary |
| Verification | Independent expected behavior, tests, artifact bindings and results |
| Evaluation | Expected effects; baseline image findings and later experiment comparisons when available |
| Status | Research pending, implementation pending, verification pending or baseline-ready |

A passing equation test closes an execution question. Closing a fidelity question
also requires the source comparison and disposition of every relevant assumption.
Use precise closure claims; keep unknowns visible.

## Source starting points

The 1996 full text and the supplied 21-page 2003 full text were inspected for this
audit. The related 1997 full algorithm and the author recipe library remain access
gaps; their conservative implementation decisions are recorded below.

- [Shamir 2003, local full text](../reference/fonts/papers/shamir-2003-constraint-based-hinting.pdf)
  ([publisher](https://dl.acm.org/doi/epdf/10.1145/636886.636887)),
  §§3.2–3.6 and Table I: relations, measurements, representative graph,
  priorities, scheduling and instruction translation.
- [Shamir and Rappoport 1996](https://pages.cs.huji.ac.il/sites/www-arir/storage/extraction-typographic-elements.pdf),
  §§3–5: preparation, extraction, complex features and ladders.
- [Related 1997 preparation abstract](https://pages.cs.huji.ac.il/sites/www-arir/storage/quality-abs.html):
  interpenetration correction; the full algorithm remains unverified.
- FreeType 2.13.2 [interpreter](https://github.com/freetype/freetype/blob/VER-2-13-2/src/truetype/ttinterp.c)
  and [CVT scaling](https://github.com/freetype/freetype/blob/VER-2-13-2/src/truetype/ttobjs.c):
  execution evidence, distinct from the target paper's algorithm.

## Research record — 2026-09-08

The supplied 2003 PDF is stored unchanged in the reference papers directory.
Its title, author, 21 pages and publication details were checked; the repository
copy was compared byte-for-byte with the supplied file. §§3.2–3.6, Table I and
§4.1 were reread after the online ACM endpoints returned access challenges.

Research covered these queries (including exact-title and PDF variants):

- B01–B04: `Shamir Rappoport 1997 quality improvement outline fonts interpenetrations`;
  `Quality enhancements of digital outline fonts`; `Geometric modeling in digital
  typography`; `Shamir typographic epsilon`; `Parametric typographic representation
  of typefaces automatic conversion`.
- B05/B06/B13: `Ariel Shamir automatic hinting typographic complex features library
  2003 thesis`; `Shamir Rappoport 1996 extraction typographic elements templates
  representative points`; `Ariel Shamir hinting source code`; `Shamir ParamTT
  LiveType source`; `Parametric typographic representation TR-95-01`.
- B07–B12: `Ariel Shamir 2003 constraint based automatic hinting font pdf`;
  `Shamir Rappoport automatic hinting constraints ratio representative points source
  code`; `636886.636887 pdf`; `Shamir Ratio hinting`; `LiveType TR-97-11`;
  the 2003 title with `topological` and `filetype:pdf`.

Additional inspected sources and findings:

- The [author bibliography](https://pages.cs.huji.ac.il/sites/www-arir/) and
  [quality abstract](https://pages.cs.huji.ac.il/sites/www-arir/storage/quality-abs.html)
  establish preparation scope; the detailed quality algorithm was not recovered.
  The 2003 bibliography dates that work 1998b, while publisher metadata dates the
  same volume/pages 1997. This bibliographic difference does not supply another algorithm.
- The author-uploaded [1998 design paper](https://www.researchgate.net/publication/2506331_Feature-based_design_of_fonts_using_constraints),
  §§4.2–4.3, describes separate X/Y DAGs and designer-guided constraint unification.
  It is a predecessor design system, rather than the target autohinter. Its
  [institutional record](https://cris.huji.ac.il/en/publications/feature-based-design-of-fonts-using-constraints/)
  confirms the publication. Its cited TR-97-11 and the thesis were located
  bibliographically, but full texts were not recovered.
- The [LiveType abstract](https://pages.cs.huji.ac.il/sites/www-arir/storage/livetype-abs.html)
  concerns dynamic design; it supplies no automatic local topology-repair rule.
  TR-95-01 and source-library searches yielded no usable authored hint library.
- The [native instruction specification](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions)
  establishes 26.6 coordinates and cardinal SCFS export semantics. It supports
  adapter verification, rather than defining the paper's hinting choices.

The reopened B06/B08/B11 investigation reread §§3.2, 3.5 and 3.6 and searched
`Shamir 2003 constraint based hinting unconstrained points interpolation
representatives` and primary TrueType interpolation documentation. The
[Apple instruction guide](https://developer.apple.com/fonts/TrueType-Reference-Manual/RM03/Chap3.html)
and [Microsoft IUP specification](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions)
select references by contour order. They provide a documented topology precedent
for B08; the search recovered no author-specific reference-selection algorithm.
IUP shifts outside the projected reference interval, whereas the revised baseline
retains Shamir Ratio extrapolation. This distinction is explicit in B08.

These searches support the explicit assumptions below; inaccessible sources remain
possible sources of further clarification.

## Implemented baseline decisions

Each row records the published rule, the decision after research, its effects and
verification. **B06, B08 and B11 remain open for assumption and image evaluation.**
The frozen v2 numerical results below apply to its earlier decisions. Author-system
equivalence remains unestablished. Settings are reproducibly identified
in [baseline metadata](../../tools/font_probe/shamir_baseline.py). They are
assumptions rather than recovered author defaults wherever indicated.

| ID / source and rule | Baseline decision and rationale | Verification and expected effects |
| --- | --- | --- |
| B01 — 1996 §3; 2003 §3.3: prepare essential outline points and remove redundant lines | Static quadratic input; exact collinear joins removed, including contour seam; exact extrema inserted. Retain Skia nonzero-boundary normalization and authored metrics as an explicit modern preparation substitution while full related algorithm is unavailable. | Source-derived seam/corner/extrema tests plus existing overlap/holes/metrics tests. Real shallow corners survive; normalization can change feature interpretation. |
| B02 — 1996 §§3–4: epsilon features and internal connecting regions | Retain 0.003em distance, 0.04rad angle and 0.012em curved alignment as researched numeric assumptions. Baseline uses analytic line/quadratic intersection partitions to check connecting segments and complete support/counter strips. | Narrow holes and quadratic intrusions missed by sampling are rejected. Tests cover winding and ordinary stems. Chord-strip checks can conservatively exclude approximately straight curved boundaries. |
| B03 — 2003 §3.4/Table II: count recurring typed values, preserve distinct frequent heights | Count feature occurrences at exact integer font-unit values; retain values with at least six occurrences, using the published example as an explicit threshold choice. Associate constraints to nearest same-type value within 0.01em, a separate matching assumption. | Tests preserve 36/37 and the distinct negative baselines in the example; repeated features in one character count. Record measurement samples. Repertoire and threshold affect shared values. Joint Table II transcription and repertoire-monotonicity tests lock the threshold, separation and crossing behavior. |
| B04 — 1996 §5; 2003 §3.5: similar-length consecutive strokes with equal counters | Use the geometric epsilon for length/gap/width equality. Remove the twice-width minimum length and 10% length allowance. Triple windows represent longer ladders; adjacent pairs are deduplicated before statistics. This is a conservative implementation choice. | Source-invariant tests cover short equal strokes, epsilon length variation and unique pairs in four-stroke ladders; native rhythm is an observation, rather than a pass requirement. |
| B05 — 1996 §4.4; 2003 §3.5: sequence/reset automata and predefined reusable constraint recipes | Implement two published sequence examples, explicit sub-automata and reset traversal. Author minimal recipes: first outline point Abs, other matched points and span controls follow original unrounded offsets. This is conservative authored knowledge; the full author library is unavailable. Remove tuned taper/port/width ownership rules. | Reset, wrap, sub-automata and quadratic-span translation tests. Recipe conflicts use ordinary priorities. Unrecognized forms use basic features/defaults and remain outside complex-feature coverage. |
| B06 — 2003 §§3.5–3.6: first/middle representative, dominant constraint, member distances | Choose first on-curve index. A physical extracted side keeps one identity and its own normal across feature participation; feature-pair tolerance does not create duplicate segment groups. Select one dominant relation per segment before resolving native points. Retain one-font-unit tangent/control membership as a coordinate-quantization assumption. Shared-point handling is recorded in B11. | Reopened after Source Sans 3 `V` exposed duplicate groups with different normals for one physical segment. Verify side identity, own-normal attachments and feature relations. Controls remain members; Revised corpus passes; image findings appear below. |
| B07 — 2003 §3.2: six projected equations with supplied parameters | Honor signed local/shared distances and supplied finite local/shared Ratio coefficients; derive ordinary Ratio from geometry only when absent. Single-coefficient Ratio assumes weights sum to one; code weights its second source. Nearest-pixel rounding uses half-away ties, an explicit numeric choice. | Tests exercise authored distances, negative/shared extrapolation, zero offsets and singularities. Removes the unsupported PRatio [0,1] restriction and geometry-overwriting of authored values. |
| B08 — 2003 §3.2: Ratio default; reference selection unspecified | Choose preceding/following representatives on the same native contour, using primary IUP documentation as a topology precedent. Keep Ratio extrapolation and perpendicular completion for one free degree. A single reference or zero projected span uses unrounded Dist preserving the original offset; a contour without references retains its original coordinate. This is an explicit interpretation, not the complete IUP algorithm or recovered author behavior. | Reopened after `G/Q` showed harmful global projected-nearest coupling. Focused tests cover contour isolation, wraparound, extrapolation and degeneracies. Reduced representatives remain the reference set; axis-specific IUP touched-point semantics are outside this assumption. Revised corpus passes; image findings appear below. |
| B09 — 2003 §3.6: font > metric > relative > absolute; arbitrary ties warned | Retain the verified priority hierarchy and deterministic declaration-order tie break. Phantom peak lookup is separate from statistics voting: match same-polarity flat/round global heights, a conservative type-association choice. | Priority and phantom-without-voting tests. A phantom can receive PAbs even when ineligible to contribute height statistics. |
| B10 — 2003 §§3.2/3.6: unique solution for two independent relations | Geometric independence replaces the condition-four selection cutoff. Determinant boundary is 32 machine epsilons; nonfinite or out-of-range execution is explicitly unsupported. | Near-parallel equation/native tests. Large movement remains a legitimate model result for visual evaluation. |
| B11 — 2003 §3.6: reduced representative graph first, then member links | One dominant relation per segment precedes whole-point scheduling. Links targeting existing representatives enter the reduced graph under ordinary priorities and cycle removal; this is an explicit interpretation of overlapping roles. Ordinary members attach afterward and the final graph also follows point dependencies. Original-position cycle completion remains explicit. | Reopened after `F/H/I` exposed alignments lost through early member promotion and immutable synthetic completion. Verify reduced-graph isolation, preserved dominant relations, late attachments and explicit singular-system failure. The final simultaneous solve needs separate assumption review; Revised corpus passes; image findings appear below. |
| B12 — 2003 Table I/§4.1: translate relations into native hints | Experimental translation replacement: solve both projected equations per point at requested integer ppem, then emit cardinal SCFS coordinates. This avoids native freedom-vector conditioning changing model selection. It preserves the model at that size, rather than reproducing scalable CVT instruction programs. | Independent simultaneous-equation oracle, actual FreeType output and wrong-size gate tests. Scope: isotropic axis-aligned requested size; 26.6 coordinate quantization and numeric range are explicit. |
| B13 — 2003 §3.6: resolve conflicts by priorities | Apply priorities and report discarded relationships. No automatic contour-order repair was recovered; retain resulting defects for baseline evaluation. | Audit selected/rejected relationships and inspect complete repertoire. Shape repair belongs to later experiments unless another source establishes a missing rule. |

Code entry points: [model assembly](../../tools/font_probe/shamir_model.py),
[baseline solver](../../tools/font_probe/shamir_baseline_solver.py),
[contour completion](../../tools/font_probe/shamir_baseline_completion.py),
[baseline templates](../../tools/font_probe/shamir_baseline_templates.py),
[independent verification](../../tools/font_probe/check_shamir_baseline.py) and
[baseline image renderer](../../tools/font_probe/render_shamir_baseline.py).

## Reopened conformance review

The user identified `F` middle-arm and `G` upper-terminal tails, uneven `H` stem
weight, an extra `I` bottom pixel, reduced `Q` curvature and asymmetric `V`.
Native traces connected these to side identity (B06), default references (B08)
and shared representative/member construction (B11). Treat these as model-drift
signals requiring source review, rather than immediately applying shape tuning.

The revised `tools/font_probe/out/shamir-baseline-v3/` freezes the changed model,
inputs and decision metadata. All 972 native-coordinate and graph checks pass;
137 focused tests pass. Independent review confirms that selected nondefault
representative relations survive late attachments. Free/default projections can
still move. The frozen source predates a comment-only clarification of that distinction.

The reported cases were traced against v2 with unchanged Roboto 14px input points:

| Case | Result of the revised construction | Remaining review |
| --- | --- | --- |
| F | Middle-arm endpoints now both x6, removing the previous x6/x6.64453 mismatch. | Inspect other sizes/fonts; Literata 20px F still rejects one attachment. |
| H | Right outer endpoints both x8 and inner endpoints both x7; cap reaches y10. | Human evaluation remains pending. |
| I | Right endpoints both x2, removing the previous x2/x2.57031 mismatch. | Human evaluation remains pending. |
| G | Adjacent upper control now uses contour neighbours [24,30], replacing remote [60,0]. | Independent anchors still place originally equal-x points at x8 and x9. |
| Q | Bowl controls follow bowl neighbours instead of the tail; inspected crop regains curvature. | Human evaluation remains pending. |
| V | Both Source Sans 3 slants now share the same physical outer-side group. | Roboto 14px remains asymmetric; Source Sans 3 18/20px still has roughly 55px junction excursions from near-parallel selected equations. |

V demonstrates that fixing side identity alone does not resolve shared-junction
construction. The next source audit must trace its selected width/alignment pair,
representative choice and overlapping roles. G requires review of independent
anchor assignment. Keep both open; introducing a conditioning cutoff or a glyph
patch would be a separate algorithm change. The new contour-reference and final
member-equation assumptions also require evaluation before baseline acceptance.

## Construction audit of Roboto 14px

Scope: G/S/K/J/M, +/X/x/V/v, b/d/g/h/j/m/n/p/q, 1/5 in the frozen v3
report. Numerical equation agreement remains valid; it does not qualify construction.
Research on 2026-09-08 revisited 1996 §§3–4 and verified 2003 §§3.5–3.6.
Queries: `Shamir Rappoport 1996 extraction typographic features epsilon vertical
bounding box hinting pdf`; `Shamir automatic hinting source code 2003 segment
representative constraints`. The [author's 1996 text](https://pages.cs.huji.ac.il/sites/www-arir/storage/extraction-typographic-elements.pdf)
and [author bibliography](https://pages.cs.huji.ac.il/sites/www-arir/) supplied the
published definitions; no implementation resolving shared roles was recovered.

### Confirmed construction mismatches

- **Dominant segment relation is missing (B06/B11).** 2003 §3.6 inserts each
  representative with its dominant segment constraint. `constraints_for()` emits
  an Abs for every group, then adds feature widths; selection operates on native
  points and geometric independence, without resolving segment dominance first.
  In M, dependent group 7 receives cardinal PDist `width-4` and its own tilted
  Abs `segment-7`. Their normals are (1,0) and (0.999517,0.031082).
  Both survive, placing point 11 at y32.205px instead of y8.060px; its member
  point 12 follows. This is an assembly failure preceding numerical solution.
- **Cardinal recognition replaces the stated geometric test (B02).** 1996 §3
  defines epsilon-vertical by endpoint x difference or bounding-box width.
  `recognize()` classifies stems from the first side's angle alone. M's tilted
  sides vary 19 font units in x, exceeding the configured distance epsilon 6.144,
  but pass the 0.04-radian angle test. Matching-angle tolerance is also needed by
  the paper, but it does not replace the vertical/horizontal definition. Combining
  cardinal feature widths with actual tilted side normals exposes this mismatch.

### Unresolved choices and limits

- **Shared-point priority (B11):** late member links cannot displace an accepted
  nondefault representative Abs, even if the link has higher ordinary priority.
  This phase ownership and simultaneous final solve are project replacements for
  an unresolved overlap case, not recovered author behavior. X/x/V/v/1 and 5
  must be traced through segment dominance and role overlap before assigning a
  typographic conditioning threshold. Roboto 5 point 1 moves y4.997 to -1.004px.
- **Curved-top coverage (B02/B03):** b's outer/inner maxima have x634/x588;
  n's have x645/x590. Separations 46/55 exceed the chosen alignment tolerance
  24.576 font units. Independent y1102/y946 anchors then round to 8/6px. The
  paper requires matching extrema within epsilon but supplies no applicable
  numeric default. These are demonstrated setting/coverage failures, not a
  confirmed missing published arc algorithm. Review all reported lowercase
  forms separately; j's terminal/dot behavior is not explained by the b example.
- **K extraction:** upper sides 1/3 match angular tolerance, but baseline
  connecting-segment and full-strip interior checks reject the feature. The
  sampled diagnostic accepts it. Disabling either analytic predicate alone
  still rejects it. Determine geometric rejection versus numerical boundary
  error before changing recognition; missing width control alone is not the cause.
- **G/S/J/j terminals and + symmetry:** independent anchors explain the observed
  movement, but a required missing relationship has not been established.
  The sources reviewed do not establish blanket glyph symmetry constraints.

Correction order: implement source-defined cardinal classification and explicit
segment dominance, with synthetic tests independent of glyph names. Then audit
shared-role priority and K interior rejection. Rebuild the full repertoire and
trace every reported case. Investigate numeric coverage settings separately;
human comparison follows source/assumption review. Preserve v3 and keep renderer
and glyph-specific adjustments outside this correction pass.

## Correction pass and tolerance investigation

The correction pass implements segment dominance, source-defined cardinal
classification for both sides, exact quadratic projection bounds during side
extraction, and actual piecewise-line support for merged straight runs. Roboto K's upper slant now passes the unchanged analytic interior
checks. Near-straight quadratic strip geometry remains a conservative limitation.
Cardinal arc/bow/curve widths now use the same projected measurement in statistics
and constraints; the earlier Euclidean measurement was inconsistent.

Shared links targeting representatives now participate in ordinary reduced-graph
priorities and cycle handling **after** segment dominance. Thus a late phase no
longer protects a local Abs from a higher-priority shared Dist. Ordinary members
attach to completed representatives afterward; the final graph uses point ordering
and fails explicitly on any new cycle. Shared-role interpretation remains an
assumption, while the simultaneous final solver is retained only as a diagnostic.

The corpus checker now verifies that every accepted nondefault reduced relation
survives native-point remapping, including its rounding semantics and ownership.
It also audits segment dominance and dependency provenance. These invariants
complement numerical agreement; they do not establish author-system equivalence.

### Numeric tolerance evidence

A fixed 243-glyph corpus (81 characters in each calibration font) was inspected
at predeclared alignment settings .003/.006/.012/.024/.048/.096em. The primary
1996/2003 sources supplied no numeric epsilon. Before the measurement correction,
65 of 337 eligible pairs at .012em had different rounded Euclidean and projected
widths. For the potential b/n top pairs, projected width is156 units while chord
lengths round to163/165. Correct measurement identity before comparing coverage.

Increasing alignment broadens coverage and also creates competing partners:

| Alignment em | Eligible pairs | Endpoints with multiple partners |
| --- | --- | --- |
| .012 | 337 | 36 |
| .024 | 410 | 40 |
| .048 | 470 | 78 |

These are feature-candidate counts, not accepted glyph quality. Roboto b's top
pair activates at46/2048em; n's at55/2048em. Wider settings remain explicitly
labeled experiments. Baseline stays at .012em pending image review; the
pair-geometry half is now committed-test evidence
(test_arc_bow_widths_match_axis_projection: every recognized arc/bow width
matches its axis projection within 1e-9 on the 243 committed-font outlines). The [audit script](../../tools/font_probe/audit_shamir_tolerances.py) and
[comparison script](../../tools/font_probe/compare_shamir_tolerances.py) record
the corpus and hashes. The latter builds the complete 81-character Roboto 14px
corpus at .012/.024/.048em and labels the wider settings as experiments; its
`tools/font_probe/out/shamir-tolerance-comparison/index.html` shows all reported
cases and native text.

### Verification and experimental results

`tools/font_probe/out/shamir-baseline-v5/` freezes the final corrected sources,
inputs and decisions. All 972 native-coordinate, graph and construction checks
pass; the focused suite has 160 passing tests. Maximum native coordinate error is
1/128px per axis within floating-point tolerance. The earlier v4 snapshot predates
the final quadratic projection-bound correction and remains diagnostic evidence.

The tolerance comparison passes 243 native-coordinate/graph cases. All 337 current
arc/bow measurements in the 243-glyph feature audit match their projected widths.
The .024/.048 settings change 8/5 of 81 Roboto 14px glyphs, respectively. Both settings
retain 94 recorded reduced-graph cycle rejections, also present at .012. These
counts describe this experiment rather than a conformance pass for cycle fallback.

Coverage and output interact through font statistics: h/m/n change at .024
through a new shared round-height value even without their direct top arcs.
At .048 those arcs are detected, but a newly shared inner-height value takes
priority and restores their .012 bitmaps. Thus increasing tolerance is not a
monotonic quality improvement. Keep the default unchanged and inspect candidate
relationships and global-value ownership before selecting a wider setting.

### Baseline membership priority correction

Roboto 14px A's outer right foot was constrained by character width and diagonal
alignment, while its baseline link was emitted as a local Dist and discarded.
The point moved to y-1.136px; the same construction moved it above or below zero
at the other calibration sizes. The correction preserves character-metric
priority on exact horizontal links whose source and target lie on baseline y0.
This implements the baseline priority in 2003 §3.6 without adding a glyph rule.
Local heights, slants and the experimental profile keep their existing priorities.

Synthetic tests reproduce a width/diagonal/baseline conflict, demonstrate failure
when the metric tag is removed, and cover descenders and local-height isolation.
The fix changes which existing constraint survives; it introduces no point repair
or new rounding rule. The v6 snapshot passes all 972 native/construction checks and 163 focused tests.
Both Roboto A right-foot endpoints are at native y0 for 14/16/18/20px. Remaining
visual defects stay separate from this baseline-membership correction.

### Shared-corner research after F regression

Research on 2026-09-08 inspected 2003 §§3.2/3.5/3.6 and Figure 7, the author-uploaded
1998 design paper §4.2, and the original 1997 LiveType SIGGRAPH sketch p.160.
Queries included `Shamir Rappoport representative constraints fonts`,
`LiveType TR-97-11 pdf`, and `Shamir Digital Typography thesis constraints`.
The full TR-97-11 and author implementation were not recovered. The sketch confirms
acyclic graph conversion but supplies no shared-corner algorithm. Figure 7 shows
ordinary point identities; it does not establish duplicated role nodes or resolve
an orthogonal shared-corner cycle. The 1998 paper explicitly describes two
X/Y-oriented DAGs, but its different scope prevents silently treating that as the
specified 2003 scheduler.

A diagnostic using v6 Roboto 14px F geometry and its frozen measurement table changed
only existing segment representatives: middle-arm lower edge from point 1 to point 2,
and baseline edge from point 3 to point 4. Both alternatives belong to the same
original segments. This removes both reduced-graph cycles with the existing point
scheduler and keeps every membership link. At 14/16/18/20ppem the middle tip x pairs
are 6/6, 7/7, 8/8, 10/10; the inner stem x pairs are 2/2, 3/3, 3/3, 4/4. These are model
coordinates from a diagnostic, not a new frozen native-font validation.

This falsifies the claim that F requires a different scheduler. The closest next
experiment is deterministic coordinated choice among existing representatives,
judged by dependency structure before pixel rendering. The paper permits first or
middle representative selection but supplies no coordinated search/tie policy.
Such a policy must remain a documented completion assumption and must be checked
for contour-start sensitivity, true unsatisfiable cycles and general slanted
constraints. A two-direction dependency solver remains a separately labeled,
author-supported predecessor alternative. Production code and v6 are unchanged.

### Coordinated representative prototype

[Prototype](../../tools/font_probe/shamir_representative_search.py) and
[comparison runner](../../tools/font_probe/compare_shamir_representatives.py)
implement a separately scoped experiment. The baseline profile stays unchanged.
Only existing on-curve members can represent their segment. Font statistics and
predefined templates are held fixed before search. Candidate scoring counts
rejected relations in descending published-priority order, then cycle removals;
it never uses ppem, rendered pixels or glyph names. Constraint-count scoring is
an experimental proxy, not a published preservation objective.

The bounded search uses geometry-ordered coordinate descent, pair changes after
a stalled sweep, strict score improvement and at most 256 evaluations per glyph.
Already acyclic constructions retain their initial representatives. This policy
and its bound are explicit completion assumptions, not recovered author defaults.

`tools/font_probe/out/shamir-representative-comparison/` freezes Python sources,
inputs, generated fonts, per-glyph choices and checks. All 972 native-coordinate,
graph and construction cases pass; 166 focused tests pass. Search predictions match
the final reduced graphs for every case. Recorded cycle removals fall 536→4;
177 of 972 bitmaps change. No glyph exhausts the search bound. The residual cycle
occurs in Roboto = at each size; local-search failure is not proof that it is
unavoidable. Roboto 14px F loses both cycles and its middle-arm tail; 5 retains a
visible defect. The gallery includes all cases and native text with three fixed
columns: unhinted input, v6 reference, representative experiment.

**Contour-order independence fails qualification.** A synthetic stepped outline
was tested at every contour start in both windings (20 variants). All become
cycle-free, but three different final priority-score tuples remain. Initial
representatives, declaration ties and search local minima can still affect the
outcome. A separate inconsistent-cycle fixture verifies that search does not
claim to preserve contradictory equations. Keep the experiment unpromoted until
ordering/semantic-equivalence review and human image evaluation are complete.

### H: segment membership conflict diagnostic

The [equation diagnostic](../../tools/font_probe/audit_shamir_segment_conflicts.py)
restores every recorded member link and retains the representative experiment's
selected nondefault semantic equations. It enumerates every single semantic
equation removal, holding membership fixed as an explicit diagnostic hypothesis.
It neither rebuilds discarded candidates nor implements the paper's directed
resolver. Frozen inputs are identified by SHA-256 in
`tools/font_probe/out/shamir-h-conflict-audit/report.json`.

Roboto H has an inconsistent restored system at 14/16/18px. Each has four
single-equation repairs, in increasing published priority: release the local
inner-right Abs, the left character-metric Abs, character width, or global right
stem width. All four yield unique solutions. The lowest-priority repair releases
the inner-right Abs and preserves both widths and every member link:

| Size | Inner right x | Outer right x | Right stem width |
| --- | ---: | ---: | ---: |
| 14 | 8 | 9 | 1 |
| 16 | 8 | 10 | 2 |
| 18 | 9 | 11 | 2 |
| 20 | 11 | 13 | 2 |

Coordinates apply to the whole side. At 20px the restored system is already
consistent and needs no removal. Maximum residual for the selected repairs is
below 2e-14px. Five focused tests cover priority choice, a consistent system,
multiple conflicts without a single repair, underdetermination, nonzero member
offsets, oblique projection and Ratio extrapolation.

At 14px the chain is left x=1, outer minus left=8, outer minus inner=1,
inner x=7, plus equality of the outer endpoints. Releasing inner x=7 gives
inner x=8 and outer x=9. Dropping character width would unnecessarily discard a
higher-priority relation. The v6 bottom distortion and experiment top distortion
both hide this conflict by losing member alignment.

The construction experiment below represents the surviving equations with
the inner edge dependent on the outer edge, preserving the supplied rounded
distance when reversing direction. Section 3.6 supplies the priority ordering
and discusses moving either stem side, but does not specify this complete
dependency-reorientation policy. Segment membership preservation and equation
reorientation remain explicit assumptions requiring investigation and validation.
This diagnostic establishes feasibility for the retained equation set; it does
not qualify a general solver, native hint execution or visual quality. Baseline
fonts and the representative experiment remain unchanged.

Reproduce:

```sh
tools/font_probe/.venv/bin/python tools/font_probe/audit_shamir_segment_conflicts.py \
  tools/font_probe/out/shamir-representative-comparison/roboto-*-model.json \
  --chars H --output tools/font_probe/out/shamir-h-conflict-audit/report.json
```

The output path must be new. The diagnostic writes JSON only.

### Whole-point reorientation prototype

[Prototype](../../tools/font_probe/shamir_reorientation.py) and
[comparison runner](../../tools/font_probe/compare_shamir_reorientation.py)
implement the bounded H experiment separately from the baseline builder.
The input is the diagnostic's retained semantic equations plus restored members.
An inconsistent system requires a unique lowest-priority single-equation repair;
ties and systems requiring more removals are explicitly unsupported.

Each construction step chooses a point with two independent relations whose
sources are complete. Dist/PDist may reverse source and target by negating the
supplied distance, preserving its rounding flag. Ratio retains its original
direction. Redundant equations remain obligations verified after construction.
A stalled whole-point order is unsupported; no replacement anchors or cycle
deletions are introduced. Holding membership fixed, single-removal scope and
the deterministic point/pair order are experimental completion policies.

`tools/font_probe/out/shamir-reorientation-v1/` freezes sources, input models,
fonts, hashes, equations, removed relations, reversed edges and native checks.
The 36-case H/F/A matrix covers three fonts at 14/16/18/20px:

- Roboto and Source Sans 3 H/F: 16 supported cases, all retained-equation,
  whole-point graph and FreeType native-coordinate checks pass. Retained residual
  is zero; maximum dense-oracle coordinate difference is below 1.1e-13px.
- Roboto A: four cases stall under whole-point construction.
- Literata H/F/A and Source Sans 3 A: 16 cases lack a unique solution from this
  retained set. The experiment excludes synthetic default completion, so this
  does not establish a defect in their complete production equation systems.

Roboto H at 14/16/18px releases the inner-right local Abs and reverses the stem
dependency; at 20px no semantic relation is removed. Both stem sides remain
straight. Inspection of the 14/16px H images shows the top/bottom bulges removed;
14px F retains the representative experiment's clean middle terminal. This is
agent inspection, with user visual acceptance pending. The gallery labels all
four columns; unsupported cases have no candidate image. Generated fonts retain
the frozen experiment's existing programs for glyphs outside supported cases.

Five new focused tests exercise H's complete chain, signed half-pixel reversal,
explicit whole-point stalls, point renumbering and unsupported multiple conflicts.
The prototype is unpromoted; successful H execution does not establish a general
dependency-reorientation algorithm or exact author equivalence.

```sh
tools/font_probe/.venv/bin/python tools/font_probe/compare_shamir_reorientation.py \
  --output tools/font_probe/out/shamir-reorientation-v1
```

Use a new output directory for another run.

### Reorientation v2: completion and projected dependencies

User review preferred v1 over the earlier images. The v2 extension freezes
`tools/font_probe/out/shamir-reorientation-v2/` and checks all 16 v1 supported
cases for exactly unchanged model coordinates and rendered pixels, including H.
All 36 H/F/A cases now pass retained-equation, whole-point graph and FreeType
native-coordinate checks. This remains the small diagnostic matrix, not corpus
qualification or a promoted baseline.

The 20 unsupported cases had two distinct causes:

- **16 missing-completion cases:** v1 omitted frozen default equations. Literata
  H at 14px, for example, retained rank 48 for 120 coordinates; its 72 defaults
  complete the system consistently. V2 restores existing defaults only for an
  underdetermined retained system, then requires a unique consistent result.
  Cycle-deletion defaults are excluded. Section 3.2 specifies Ratio for otherwise
  unconstrained points; the frozen contour-reference and original-position
  fallback choices remain B08 interpretations. V2 does not invent new defaults.
- **Four Roboto A dependency stalls:** after the single-relation conflict repair,
  the retained equations already had a unique solution, but a needed projection
  waited for an entire source point to finish.
  On a whole-point stall, v2 substitutes Abs/PAbs through exactly parallel
  Dist/PDist chains, retaining each derivation's equation IDs. It rounds each
  supplied distance before combining values, handles opposite normal signs,
  and preserves unrounded member offsets. It then retries whole-point ordering.
  At 14px the executed derived relation supplies point 7's baseline projection,
  allowing the right diagonal and the remaining points to follow.

The derived anchors are size-specific consequences of retained equations,
not independently chosen positions. Every original retained relation remains an
obligation checked against the final coordinates and a separate dense oracle.
This algebraic substitution preserves the equation solution, but the paper does
not prescribe this scheduler transformation: it remains an explicit completion
assumption. Near-parallel substitution, Ratio inversion and general simultaneous
execution are outside this prototype. Unresolved stalls remain unsupported.

Five additional tests cover frozen Ratio completion, contradictory defaults,
rounding before summation, rejection of near-parallel substitution and a partial
coordinate dependency cycle. Agent image inspection covers Roboto 14px A,
Literata 14px H/F and Source Sans 3 14px A; user review of the new cases is pending.

```sh
tools/font_probe/.venv/bin/python tools/font_probe/compare_shamir_reorientation.py \
  --output tools/font_probe/out/shamir-reorientation-v2 \
  --previous tools/font_probe/out/shamir-reorientation-v1
```

### VTT-backed serif experiment

Microsoft's [SERIF reference](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/doc/VTT%20Language%20Reference/vttlang.html#L827-L876)
and [compiler](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L1665-L1769)
provide a concrete reference for 2003 section 3.5's declarative route. Type 2/3
recipes attach separate serif halves to established vertical/diagonal stems.
Their extension, thickness and height relationships differ from B05 translation.

[Experiment](../../tools/font_probe/vtt_serif_experiment.py) and
[runner](../../tools/font_probe/compare_vtt_serifs.py) freeze
`tools/font_probe/out/vtt-serif-v1/`, with twelve Literata H/F/A cases at four sizes.
Geometric detection identifies eight H halves, two bottom F halves and four A
halves, without glyph identities or native-point lists in the detector. Horizontal
bases must lie at glyph vertical extrema, their ends must be vertical and at most
.12em thick, and a bracket must lead to a straight stem edge at least .10em long.
Paired detection, these thresholds and the bounded traversal are project policies.

The recipe keeps each stem reference's fitted x, positions the serif end using
its signed rounded extension, and gives the serif thickness a one-pixel minimum.
Type 2 also controls bracket height; type 3 retains the diagonal stem reference's
y. Bracket points use their original coordinate proportions between upper-end
and stem anchors. Points outside detected spans remain exactly unchanged.

This is a VTT-backed relationship experiment, not a port of VTT's compiler or
native functions 34–36. It uses each instance's source dimensions instead of a
shared CVT, half-away distance rounding from our adapter, and explicit two-anchor
bracket interpolation rather than verified VTT/IUP equivalence. Existing serif,
template and default constraints within the spans are replaced by this recipe;
their continued satisfaction is not claimed. The general reorientation baseline
and frozen v2 outputs stay unchanged.

Twelve native-coordinate checks pass. Four focused tests cover contour reversal,
paired detection, stem-relative lengths, unchanged outside points, reflection
equivalence and unsupported thick ends. Agent inspection of 14px H shows balanced
overhangs; F and A are rendered for user review. This is not visual acceptance.

```sh
tools/font_probe/.venv/bin/python tools/font_probe/compare_vtt_serifs.py
```

The output directory must be empty. The rightmost gallery column is the new
experiment. Broader recognition, shared values and exact VTT parity remain open.

### Parent placement experiment: Literata 20px F

[Microsoft's diagonal examples](https://learn.microsoft.com/en-us/typography/truetype/italic-hinting-examples)
establish parent points before relative diagonal control, with unrounded placement
in the serif example. [Prototype](../../tools/font_probe/shamir_parent_anchor.py)
and [runner](../../tools/font_probe/compare_parent_anchors.py) compare rounded and
unrounded complementary placement in `tools/font_probe/out/parent-anchor-v1/`.

The geometric predicate selects a local oblique side Abs sharing a representative
with an explicit cardinal Abs/PAbs, when the side projection is closer to that
cardinal axis than its complement. The side must have a retained member link.
Replace only its absolute positioning with source-coordinate placement along the
complementary axis; keep the cardinal anchor and every relative equation. Font
parameter anchors and defaults are excluded. This predicate is a project policy,
not a recovered Microsoft or Shamir algorithm; this is not a VTT Diagonal port.

In the 36-case H/F/A matrix, only Literata 20px F matches. Its lower terminal moves
from (5.752,4) to (9,4) with rounding or (8.62,4) without. Both variants remove the
hook in agent image inspection. The rounded variant collapses the short lower
terminal edge (points 35–36) to zero length; the unrounded variant preserves it.
Their raster images look alike at this size, demonstrating why native-coordinate
and geometry checks must accompany visual review. Prefer the unrounded variant
for further evaluation; neither is promoted.

All 72 candidate native-coordinate checks pass. Retained equations are checked
against an independent dense solve before applying the existing serif recipe.
All other 35 cases retain identical pixels, including accepted 14px F. Four
focused tests cover both policies, relative alignment, excluded font parameters,
required membership/cardinal anchors, axis exchange and reflection. The gallery
shows smooth source, current reference, rounded and unrounded variants.

```sh
tools/font_probe/.venv/bin/python tools/font_probe/compare_parent_anchors.py
```

The output directory must be empty. General coverage and user review remain open.

### Native terminal links experiment

[Prototype](../../tools/font_probe/vtt_terminal_links.py) and
[runner](../../tools/font_probe/compare_terminal_links.py) compare separate and
shared upper/lower terminal extension values for Literata F at 14/16/18/20px.
The input is the unrounded parent-anchor candidate. The arm anchors, every x
coordinate and all points outside the terminal remain fixed.

The [VTT compiler's Link and Interpolate implementations](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L478-L727)
provide the primitives: rounded relative links followed by unrounded interpolation.
The experiment executes native `MIRP[00100]` and `IP`, with round-to-grid,
automatic distance sign, one-pixel CVT cut-in and disabled single-width cut-in.
The [TrueType instruction specification](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions)
defines their execution. The independent interpolation check uses original design
coordinates, matching native IP ratios, rather than rounded scaled coordinates.

Terminal recognition is bounded to one right-facing terminal with adjacent
horizontal arm anchors. Shared values use the rounded arithmetic mean of the
two source measurements: 97 font units in these four inputs. Recognition,
averaging and the cut-in choice are explicit experiment policies; this is not a
recovered VTT SERIF recipe or a general automatic CVT selection algorithm.

All eight native variants match the scalar coordinate oracle within 1/64px
(maximum observed error 0.007103px). Exact preservation checks pass for x and
all points outside the terminal. At 16px, separate values retain the original
bitmap; sharing changes the upper extension from one to two pixels, matching the
lower extension. At 18px both candidates have the same changed bitmap. At 14px
and 20px both retain the input bitmap. Equal extension lengths do not establish
full contour symmetry; source curvature and x placement remain relevant.

The gallery includes a smooth source beside the current reference and both
candidates. User review and broader recognition coverage remain open.

```sh
tools/font_probe/.venv/bin/python tools/font_probe/compare_terminal_links.py
```

Output: `tools/font_probe/out/terminal-links-v1/`; the directory must be empty.
The report records native coordinates, input/source hashes and validation errors.

#### Shorter terminal comparison

User review rejected the longer balanced terminal at 16px and the changed 18px
shape. The next isolated comparison uses the same input and fixed arm anchors:
separate source measurements with native `RDTG` (round distance magnitude down),
versus the smaller source measurement shared between both links with `RTG`.
Native `IP` keeps the bracket points attached to their moved endpoints.
Both policies are experimental design choices, rather than Microsoft prescriptions.

| Size | Round down: upper/lower extension | Smaller value: upper/lower extension |
| --- | --- | --- |
| 14px | 1 / 1px; unchanged bitmap | 1 / 1px; unchanged bitmap |
| 16px | 1 / 1px | 1 / 1px; same bitmap as round down |
| 18px | 1 / 1px | 2 / 2px; retains the longer terminal |
| 20px | 1 / 2px; introduces unequal lengths | 2 / 2px; unchanged bitmap |

All eight native coordinate checks pass within 1/64px (maximum 0.007374px),
including exact preservation of x coordinates and points outside the terminal.
The 20px outcome exposes a limitation of independently flooring measurements;
the 18px outcome shows that a smaller shared source value can still round upward.
User review remains open; neither policy is promoted.

```sh
tools/font_probe/.venv/bin/python tools/font_probe/compare_terminal_links.py --shorter
```

Output: `tools/font_probe/out/terminal-shorter-v1/`, with smooth source references,
native fonts, coordinates and source/input hashes. The output directory must be empty.

#### Shared smaller extension, rounded down

User direction prioritizes visual fidelity over a presumed minimum terminal
length. The `--paired` comparison applies the smaller source measurement to both
native links with `RDTG`, followed by the same bracket interpolation. It compares
this candidate with separately rounded-down measurements and the input reference.
The pairing and rounding choice remains an experimental project policy.

The candidate has one-pixel upper and lower extensions at 14/16/18/20px. Its
14px bitmap stays unchanged; 16px and 18px match the previous round-down candidate.
At 20px the lower extension shortens from two pixels to one, matching the upper.
Eight native coordinate checks pass within 1/64px, including explicit equality
of paired extension lengths and preservation of x and all non-terminal points.
This proves the placement rule for these inputs; visual acceptance remains open.

```sh
tools/font_probe/.venv/bin/python tools/font_probe/compare_terminal_links.py --paired
```

Output: `tools/font_probe/out/terminal-paired-v1/`; the directory must be empty.
The gallery retains smooth references beside all four sizes.

#### Terminal transfer audit

User review prefers the shared smaller value rounded down for F, including 20px.
The [coverage runner](../../tools/font_probe/audit_terminal_coverage.py) scans all
94 non-space printable ASCII characters in Literata, Roboto and Source Sans 3 at
14/16/18/20px: 1,128 font/size/glyph cases, with no missing characters.
Selection uses outline geometry, with no glyph-name conditions.

The detector finds Literata E and F at every size: eight matches, including four
new E cases. No glyph has multiple supported pairs. There are 564 bracketed near
misses and 556 cases outside the detector. Near misses have a downward vertical
edge and horizontal anchors but fail the remaining ordering/position tests;
they are exposed for recognition review and retain the input rendering.
The gallery includes every match and near miss; the JSON inventory includes all
1,128 cases. A compact matches page provides the primary visual comparison.

All eight native coordinate checks pass within 1/64px, with equal one-pixel
extensions and exact preservation of x and unrelated points. E changes by
1/2/3/2 pixels at 14/16/18/20px. Eleven focused tests pass, including contour-start,
translation/scale, multiple-match rejection and near-miss reporting checks.
The current input coordinates are frozen before applying native links and IP.
Input fonts have mixed experimental history: H/F/A include parent-anchor work,
while other glyphs retain their inherited rendering. The comparison isolates the
terminal change without claiming a uniform new baseline for the entire repertoire.

This supports transfer to one additional geometric match, pending E visual review.
It establishes no sans applicability: this detector only covers original-winding,
right-facing explicit vertical terminal edges with horizontal arm anchors, using
a maximum 20-point bracket walk. Other orientations, curved ends, alternate winding
and extended Unicode remain outside the audit. Equal extension lengths also do
not ensure mirrored curves or pixels. Broader recognition requires separate evidence.

```sh
tools/font_probe/.venv/bin/python tools/font_probe/audit_terminal_coverage.py
```

Output: `tools/font_probe/out/terminal-coverage-v1/`; the directory must be empty.
Native fonts, coordinates, input/source hashes and smooth references are retained.

#### Uniform correction scope audit

The scope audit found geometry-based rules applied through identity-limited
runners: reorientation defaulted to H/F/A, serif fitting selected Literata H/F/A,
and parent fitting inherited those records and selected serif fitting by family.
Terminal coverage consequently inherited mixed programs. Older outline experiments
also use named-letter scoring bands (`outline_experiment.py`); offset experiments
select X and related letters for measurement. Those diagnostics and historical
runners are outside the new correction sequence. The current Shamir geometry,
parent, serif and terminal rule implementations contain no identified letter-name
dispatch. This audit establishes the current dependency path, not a claim that
every historical experiment is identity-free.

The [uniform candidate boundary](../reference/font-candidate-pipeline.md) replaces
the mixed chain for further candidate builds. Each available frozen record runs
reorientation, parent placement, serif recognition and paired terminals through
one identity-free entry point. The input adapter strips identity metadata; the
candidate exports only verified mappings. The paper baseline remains separate.

The first full build requests 1,140 cases (95 characters, three fonts, four sizes).
880 pass native coordinate checks. 180 lack a frozen record, 79 have unsupported
retained-equation constructions, and Literata 14px percent encounters a repeatable
NumPy least-squares SVD failure while enumerating single-equation repairs. That
numerical diagnostic failure remains open and is reported as a failure, not a
visual rejection or a supported fallback. These limitations prevent treating the
build as a complete production font.

All eight Literata E/F terminal matches construct. The geometric parent condition
now reaches 16px E, removing its leftward lower-terminal distortion without an
E-specific branch. The terminal remains attached through the shared rule. All
other candidates await review after uniform application of the serif stage.
25 focused tests pass, including four architecture-boundary checks.

#### Opposing outer-arm terminals

User review accepts the uniform candidate's appearance and requests investigation
of balance between upper and lower arm terminals. The E source has different tip
directions: the upper edge slopes downward inward; the lower edge is horizontal.
Independent prior placement steepens the upper tip at 14–18px and reverses its
slope at 20px. The middle-terminal recognizer does not own these outer-arm tips.

[Opposing-terminal geometry](../../tools/font_probe/opposing_terminals.py) detects
top/bottom extrema arms on the same contour, right-facing short tip edges and
curved returns to horizontal arm anchors. Both contour directions are scanned.
Explicit bounds (length .1–.4em, tip edge below .15em, return walk at most 20
points) are project assumptions. Each pair receives either:

- Coordinated placement: each source terminal length rounds to nearest pixel;
  each original tip vector is preserved relative to the positioned outer corner.
- Shared dimensions: mean source length rounds to nearest pixel; both tip edges
  use the mean source magnitude, retaining their individual source directions.

Both variants interpolate the return curves to fixed arm anchors. The outer
corner's existing x coordinate stays fixed. These are explicit coordinate recipes
exported through SCFS, not a claim of native VTT Link/IP parity or recovered paper
logic. Their numeric-policy choice is common to every geometric match.

The [runner](../../tools/font_probe/compare_opposing_terminals.py) scans all 880
verified uniform-candidate mappings. Only Literata E matches, at all four sizes;
there are no ambiguous pairs. The 260 unavailable uniform cases remain outside
this experiment. At 14px the coordinated lengths are 2/3px and shared lengths
2/2px; at 16/18px both are 3/3px and yield identical variant bitmaps; at 20px they
are 3/4px versus 3/3px. Source tip directions remain different by design.

Eight exports pass native coordinate checks within 1/128px, with preservation of
unrelated points and source tip direction within coordinate quantization. Three
new tests cover contour-start/winding independence, paired dimensions, fixed
points and the identity-free rule interface; the four existing boundary tests
also pass. Visual acceptance remains open.

```sh
tools/font_probe/.venv/bin/python tools/font_probe/compare_opposing_terminals.py
```

Output: `tools/font_probe/out/opposing-terminals-v1/`; the directory must be empty.
Each row shows smooth source, uniform candidate, coordinated and shared variants.
The accepted uniform candidate remains unchanged.

#### Coordinated-terminal integration

User review accepts both opposing-terminal variants for the four Literata E sizes.
The coordinated variant is now part of the uniform candidate, preserving separate
source dimensions. Every available outline receives its geometric detector, with
explicit rejection of overlapping correction ownership. The shared-dimension
variant remains an isolated comparison.

`tools/font_probe/out/geometric-candidate-v2/` passes 880 native checks. The
[integration checker](../../tools/font_probe/check_geometric_integration.py)
confirms exact coordinates and pixels against all four reviewed E outputs, and
exact preservation of the other 876 verified cases, including F and prior serif
treatments. Coverage outcomes are unchanged: 180 missing records, 79 unsupported
constructions, and one numerical diagnostic failure. 28 focused tests pass.
`changes.html` displays every changed case against v1 and the smooth source.
The next coverage work remains separate from this verified integration.

#### Numerical diagnostic recovery

Literata 14px percent failed while testing removal of equation 51, a PDist from
point 4 to 28. The finite 57×172 system has 116 exactly zero columns. NumPy 2.5.3
least squares and direct SVD fail on that representation; reducing it to its
56 active columns converges with rank 55 and residual 0.272727px. This isolates
a numerical representation failure, not invalid coordinates. The underlying
LAPACK convergence mechanism has not been identified.

The diagnostic now retries a failed solve only when exact zero columns can be
removed. It restores those unconstrained coordinates to zero (minimum norm),
retains the original matrix-dimension rank cutoff, and computes consistency and
uniqueness against the original system. The
[NumPy least-squares contract](https://numpy.org/doc/stable/reference/generated/numpy.linalg.lstsq.html)
defines that cutoff and minimum-norm behavior. A second convergence failure still
propagates; nonfinite inputs receive an explicit error. Recovery is recorded in
the diagnostic report, including rejected repair trials.

The formerly crashing trial remains inconsistent and is correctly rejected.
Enumeration completes with two valid removals; the existing priority rule selects
the unique lower-priority Abs on point 2 rather than a metric Dist. No new
constraint policy, tolerance relaxation or glyph-specific rule is introduced.

`tools/font_probe/out/geometric-candidate-v3/` verifies 881 candidates. All 880
previously supported cases retain exactly identical coordinates and pixels; only
Literata 14px percent changes status from failed to verified. Its appearance still
requires user review. `numerical-recovery-check.json` retains the diagnostic and
regression evidence. Remaining exclusions are 180 missing records and 79 unsupported
constructions. 27 focused tests pass, including the captured finite matrix,
cutoff/minimum-norm checks, failure propagation and nonfinite-input handling.

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/build_geometric_candidate.py --output tools/font_probe/out/geometric-candidate-v3
```

#### Outside-in stroke experiment

[Outside-in recovery](../../tools/font_probe/outside_in.py) revisits discarded
stroke Dist/PDist relations before uniform construction. The adapter maps reduced
representatives back to native points and selects ink-width feature categories;
the rule receives geometry/equations, with no character or family identity.
When the outer side has a parallel metric constraint and the inner side has one
ordinary parallel Abs, it reverses the stroke relation and releases that Abs.
Font-parameter anchors and ambiguous ownership remain protected. This is an
experimental direction-selection interpretation, not a recovered paper algorithm.

The [runner](../../tools/font_probe/compare_outside_in.py) scans all 881 verified
v3 cases and passes modified records through the existing uniform pipeline.
59 variants preserve their outer metric projection and requested stroke widths
and pass native-coordinate checks; 17 change pixels. 811 cases have no applied
recovery. Eleven recoveries fail the final width invariant after pipeline
processing and are explicitly withheld; their candidate fonts are removed.
These conflicts need investigation before integration, rather than relaxed checks.

Literata 14px percent retains outer x=12px and moves the inner edge from 10px to
11px, restoring a one-pixel right stroke. Its two removed pixels widen the counter.
All verified variants, including unchanged bitmaps, appear beside the smooth
source and current candidate. Three recovery tests and four architecture tests
pass. The reviewed v3 pipeline remains unchanged; visual review is open.

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/compare_outside_in.py
```

Output: `tools/font_probe/out/outside-in-v1/`; the directory must be empty.
The report records every scanned case, recovery, withheld result and input hash.

#### Whole-outline pixel-phase diagnostic

Perpendicular measurement of the outside-in percent shoulder is approximately
1.04px at the troublesome row. Its horizontal interval crosses a second pixel
centre by about 0.024px; this does not establish excessive normal stroke thickness.
The [phase runner](../../tools/font_probe/compare_pixel_phase.py) translates the
entire fitted outline without reshaping, using a 5×5 grid of x/y offsets:
−1/8, −1/32, 0, +1/32 and +1/8px. It covers Literata percent at 14/16/18/20px.
Repertoire selection is diagnostic; no correction rule or font program changes.

All 100 translations preserve the exact native point offsets; all four zero-offset
controls reproduce the input pixels. At 14px, +1/32px in either x or y removes only
the reported pixel (10,−4). At 16px the x shift changes no pixels; at 18px it adds
one pixel, and at 20px it adds one and removes two. Thus placement explains the
reported corner, but a universal shift is not established as visually preferable.
Metrics-relative ink placement intentionally changes in this isolated diagnostic.

```sh
tools/font_probe/.venv/bin/python tools/font_probe/compare_pixel_phase.py
```

Output: `tools/font_probe/out/pixel-phase-v1/`; the directory must be empty. The
gallery retains smooth references, full-glyph offset grids and per-cell pixel
change counts. The report lists every added/removed pixel and input hashes.

### Remaining distortion

The first corrected Roboto build reduces M's maximum displacement from28.326px
to6.151px but does not resolve its shallow junction. Its remaining width and
alignment belong to distinct adjacent segments, not duplicate side identities.
Roboto5 still moves a point about6px: a slant width competes with an Abs on a real
corner extremum. The paper permits phantom extrema anchors. Suppressing those
anchors or imposing a conditioning cutoff therefore requires a separate researched
decision. Baseline acceptance remains suspended; review the complete reported
case set rather than interpreting the closed mismatches as visual approval.

## Frozen v2 verification — prior assumption set

`tools/font_probe/out/shamir-baseline-v2/` contains the frozen source snapshot,
primary paper, input and generated fonts, configuration and decision metadata.
`baseline-verification.json` binds their hashes and tool versions. The independent
oracle solves the full simultaneous linear system, separately from the production
point solver, then compares actual FreeType coordinates.

- 123 tests pass across baseline and experimental coverage.
- All 972 baseline cases pass independent coordinate and graph checks.
- Maximum coordinate error is 1/128px, the expected 26.6 export quantization bound.
- 527 relations are removed to break cycles across both construction stages.
- `gallery/index.html` contains 972 unique enlarged pairs and native text; its
  manifest verifies 1,045 files. Input and baseline labels are explicit.

These results verify execution of the v2 model and adapter. They remain historical
evidence for that exact assumption set; B06/B08/B11 corrections require a new
report and renewed image evaluation before choosing improvements.

The gallery deliberately includes model defects. Source Sans 3 18px `V` has an
uncropped downward spike with maximum outline movement approximately 54.92px.
The `V` trace identifies two slant constraints only 0.925° apart whose rounded
widths become 1px and 2px. Their intersection places one point at approximately
(-10.189, -47.113)px; native export agrees with the independent equation solution.
Roboto and Literata 14px `e` also have imperfect contours. These observations were
checked in individual native-rendered crops; they are not automatic approval of
any assumption or justification for changing the frozen baseline.

The pre-correction `shamir-baseline-v1/` snapshot is retained. Final review found
and corrected duplicate middle ladder relationships for four consecutive strokes;
the v2 test verifies each adjacent pair contributes once to constraints/statistics.

### Controlled point-scheduler comparison

The earlier experimental scalar/point comparison remains in
`tools/font_probe/out/shamir-scheduler-comparison/`. It changed 127 bitmaps and
removed 8 versus 684 relations across both resolution stages. Those variants shared
experimental construction policies; that result does not determine the faithful
baseline's scheduler. The [probe README](../../tools/font_probe/README.md#scheduler-comparison)
retains reproduction commands. Saved preferred fonts and the published comparison
gallery remain separate from the new baseline.
