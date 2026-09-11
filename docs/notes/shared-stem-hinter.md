# Shared stems in our geometric hinter

Status: coordinated cases received positive feedback; broader matching under review.
Investigation: 2026-09-08.

## Scope

Transfer the approved stem-width relationship into our point-equation hinter.
Microsoft integration is deferred. Frozen approved VTT images are reference
columns only; candidate fitting uses our solver and requested-size export adapter.
The existing uniform candidate remains the before column.

`shared_stem_hinter.py` consumes source coordinates, numeric feature and constraint
records, and scale. Character and family identities belong to the comparison
runner. `stem_widths.py` owns the geometric matching rule shared with the previous
experiment; the old VTT module is a compatibility import.

## Experimental fitting decisions

- Match detected cardinal stems to adjoining sections with one shared side,
  connected opposite sides, normals within 5 degrees and widths within 20%.
  These are retained experimental applicability limits.
- Round the detected stem width once. Anchor the shared side at its rounded
  mean source coordinate and place the opposite side at that width. Adjoining
  section members receive the same transverse position. This flattens modest
  source taper within the matched section and therefore needs visual review.
- Set these support points' longitudinal coordinates from their rounded source
  positions. This is an explicit local anchoring policy; it does not implement
  font-wide height classes. Report all replaced equations.
- When a released junction alignment previously depended on a point with the
  same absolute line constraint, reverse that relation: the fitted junction
  becomes the parent of the diagonal line. Retain the source projected offset.
- Rebuild dependencies and fit remaining points with the existing equation
  solver. Hold ambiguous stem references, conflicting positions, competing
  diagonal parents, cycles, zero rounded widths and unresolved near-parallel
  equation pairs. The latter uses the existing 1/16 diagnostic boundary.

This stage replaces the affected source-model support equations. It does not
layer changes onto already distorted output coordinates. Later uniform serif and
terminal corrections are omitted in this isolated comparison. Consequently,
source/model and uniform differences are visible rather than attributed solely
to changing one width number. This is our experimental policy, not a port of
Microsoft's paired-diagonal function or a paper-conformance claim.

## Comparison and evidence

Run with an empty output directory:

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/compare_shared_stem_hinter.py
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python -m unittest discover -s tools/font_probe -p test_shared_stem_hinter.py
```

`tools/font_probe/out/shared-stem-hinter-v1/index.html` shows all eight affected
cases, each with smooth source, current uniform candidate, our experiment and
approved VTT reference. Screening covers 881 exported cases: 873 unaffected,
seven changed bitmaps and one identical bitmap. Matches are Roboto M and Source
Sans 3 N, each at 14/16/18/20px. Source Sans 3 18px N is the identical case.

Roboto M at 16/18px loses the prior extrusions and shows no isolated white pixel
at the junction. Diagonal thickness and the bottom join differ from the approved
reference, especially at 20px, so approval of the prior comparison does not carry
over to this candidate.

All eight fitted graphs export through our requested-size TrueType adapter and
pass strict FreeType execution with exact agreement to the solver's 26.6 output.
Source points, contour ends and point flags remain unchanged in exported fonts.
Input/source hashes, per-case equations, support assignments, reversed relations,
point order, coordinates and review fonts are recorded. The exported fonts are
single-exemplar diagnostics; other glyph programs are inherited and are outside
this experiment's validation. Rendering uses the common monochrome scan converter.

Focused tests cover common width placement, input preservation, no-match behavior,
ambiguous references and collapsing stems. The shared geometric matcher and
scheduler retain their existing tests. Next gate: human review of all eight
images. Subsequent work stays in Python until generation and a full specimen
audit are complete; Rust integration is a later decision.

## Coordinated features comparison

`--coordinate` writes `tools/font_probe/out/shared-stem-hinter-v2/`, comparing the
frozen first own-hinter experiment with coordinated features. Applicability stays
at the existing shared-stem boundary: all 881 exported cases are screened, eight
match and change, and 873 remain unaffected. This is not a font-wide rollout.

Within a matching glyph, the experiment additionally fits all detected cardinal
stems using the same policy. A cap corner joins its stem when it is the unique
on-curve point at the same source height and its width is within 20% of the body
width. Larger flares remain separate. The first trial allowed 35% and flattened
Roboto's wider caps; it failed the raster symmetry check and was discarded.

Related diagonal features share the mean detected width when their source widths
and support lengths differ by at most 5%, and their absolute normal components
differ by at most 0.01. Classes use complete pairwise compatibility, avoiding
transitive chains between dissimilar features. The mean replaces their separate
rounded distance targets while preserving signs. These are experimental grouping
limits, not recovered paper rules.

A final geometric symmetry constraint applies only if each source contour has a
unique reversed cyclic correspondence under horizontal reflection, including
matching point flags, with maximum coordinate residual of em/512. Matched fitted
points share mirrored positions and heights about the fitted bounding-box center.
Unmatched or ambiguous outlines remain as solved. This intentionally treats very
small source asymmetries as a symmetry class; visual review must assess that
approximation. It adjusts outline coordinates before scan conversion, without
bitmap patches or character-specific conditions.

Per-case JSON preserves the graph before symmetry, final export graph, width
classes, cap membership, source symmetry residual, correspondence and movement.
Diagnostics measure support widths, side straightness, cap heights and reflection
residual. The gallery runner requires symmetric raster output for source-matched
outlines, in addition to strict native/model agreement and unchanged source
outlines. Source Sans 3 N is not classified as horizontally symmetric.

All eight exports pass. Roboto M at 14/16/18/20px has zero asymmetric bitmap pixels;
the 18px diagonals now share a width target. Source Sans 3 N has matching fitted
stem-body widths (1/1/1/2px) and cap heights (9/10/12/13px) at 14/16/18/20px.
All eight images change from v1. Fuller joins and diagonal weight remain subject
to human review. Twenty-nine focused tests pass, covering cap flare limits,
related-width grouping, reflection correspondence and rejection, support ordering,
input preservation, ambiguity, and existing matcher/compiler behavior.

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/compare_shared_stem_hinter.py --coordinate
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python -m unittest discover -s tools/font_probe -p test_feature_coordination.py
```

## Broader diagonal-width audit

Run `compare_diagonal_widths.py` with an empty
`tools/font_probe/out/diagonal-widths-v1/` directory. It screens 881 cases,
preserves the eight coordinated exports, and generates 32 paired specimens.
The other 841 cases have no applicable distance replacement. All 32 matches are
Roboto A/V/W/X/Y/v/w/x at 14/16/18/20px; 26 have identical before/after bitmaps.

This comparison changes only shared diagonal distance values in frozen source
equations. The uniform candidate is a separate context column. This isolates the
width policy from later terminal, cap and symmetry changes. Fitting receives
numeric geometry; identities select specimens and frozen comparison inputs only.

All 32 exports pass strict FreeType execution and exact agreement with solver
26.6 coordinates. Original outlines, contour ends and flags remain intact. Input
hashes remain unchanged. Every generated candidate was visually inspected in a
contact sheet, with the six changed cases inspected at full comparison size:

| Roboto case | Visual finding |
| --- | --- |
| 16px V, Y | Diagonals become excessively thin; regression. |
| 18px v, w | Diagonals become excessively thin; regression. |
| 18px A | Right diagonal fills out; improvement candidate, apex still uneven. |
| 20px W | Fuller lower joins; improvement candidate, unequal diagonal weight remains. |

Four-neighbor black-component counts change in all six cases. Corner-touching
diagonal pixels count separately, so these counts are diagnostics rather than
proof of disconnected strokes. Counter counts stay unchanged and no candidate
exceeds the diagnostic 4px source-movement screen. These checks establish
execution consistency, not visual correctness.

The 26 identical cases retain existing quality issues, including thin diagonals
and uneven A/W forms at smaller sizes. Bitmap identity is not visual approval.
The gallery and `report.json` enumerate every generated case, including unchanged
and failed statuses (zero failures). This completes this experiment's specimen
audit; the complete pipeline specimen audit remains open.

Keep broader matching experimental. A useful subsequent investigation is how
averaging detected widths changes rounded distance targets and raster weight.
Any revised policy should be evaluated separately before promotion. Python
generation and full specimen review precede reconsideration of Rust integration.

## Diagonal distance semantics audit

`audit_diagonal_distances.py` writes
`tools/font_probe/out/diagonal-distance-audit/report.json`. It screens all 881
exported cases and inventories every detected slant, including features outside
the width-matching experiment: 104 Literata, 178 Roboto and 144 Source Sans 3
features (426 total). Of these, 402 retain a selected distance constraint.

The detector measures a cross-section between supported sides. The constraint
builder instead projects the separation of the selected representatives onto the
feature normal. These measurements differ in 406 features, by up to 0.419px;
35 cross a rounding boundary (34 retain selected constraints). The 35 comprise
3 Literata, 16 Roboto and 16 Source Sans 3 features. These counts describe a
semantic difference, not 35 proven visual defects. All 108 selected targets that
differ from raw representative distances are PDist font-wide parameter values.

The broad experiment overwrites both Dist and PDist targets with detected width.
For Roboto 16px V/Y this changes rounded targets from 2px to 1px. The same occurs
in 18px v/w. Thinness therefore has a confirmed numerical cause, while acceptable
weight still requires comparison across glyphs. A one-pixel target alone does not
establish a visual defect.

For a cross-section whose points are `rA + tA*uA` and `rB + tB*uB`, using oriented
normal `n`, signed width is
`w = n·(rB-rA) + tB*n·uB - tA*n·uA`.
Consequently a width target is not generally a representative-distance target.
They coincide for parallel sides normal to `n`. With fixed side directions and
sample offsets, a width change can translate as `dNew = dOld + wNew - wOld`.
This identity is a diagnostic, not a complete fitting policy: moving anchors can
change the cross-section offsets, and rounding the resulting distance still does
not guarantee the desired physical width. PDist parameterization also requires
an explicit policy rather than silently replacing a font-wide target.

The next implementation should retain cross-section support locations and side
directions with each width relation, then express the desired cross-section
width through those supports during fitting. First verify unrounded source
reconstruction and representative-choice invariance; then evaluate width rounding
and rendered weight across all three fonts. This remains a proposed experiment.

Reflection diagnostics accompany all 32 existing paired specimens. Roboto 16px V
changes from 0 to 4 differing reflected bitmap pixels; Y changes from 10 to 8.
Roboto 18px A improves from 38 to 20, but remains asymmetric. Roboto 18px W stays
at 46; 14px X/x stay at 24/8. These are bounding-box reflection diagnostics, not
an assumption that every source should be symmetric. Width equivalence and
placement symmetry need separate checks. Preserve this evidence while resolving
width semantics, then trace residual asymmetry through anchors, fitting and
raster placement. The earlier 'improvement candidate' labels are not approval.

The [cross-section prototype](cross-section-width-experiment.md) implements the
next bounded experiment and records its numerical checks and mixed image results.
