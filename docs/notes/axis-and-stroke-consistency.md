# Axis and stroke consistency

Status: Isolated Python experiment; visual review pending.

## Construction

The input is the approved `cumulative-hinter-v7` specimen. The experiment applies
uniform geometry rules in `tools/font_probe/axis_consistency.py`; font family,
glyph identifiers, and size tables are absent from the correction API.

Orthogonal contours with a small coordinate-level lattice are fitted by level,
keeping collinear source boundaries together. Source levels must be approximately
reflection-compatible on both axes. Increasing integer grid levels are selected
jointly with equal opposite offsets. This prevents independent split-stem widths
and checks both upper/lower and left/right balance. Applicability is bounded to
one contour with at most four distinct source levels per axis; the reflection
residual limit is 0.5 device pixels. These are experimental bounds.

Separate vertically stacked components with nearby source centres share a horizontal
pixel phase. Source curves undergo positive affine transformations. Compact round
components preserve source aspect ratio. The search explores nearby integer widths
and half-pixel centres, coordinating odd/even widths through the actual raster
result. Components must have positive dimensions, non-overlapping vertical source
bounds, source centre spread at most 0.15px, and sampled reflection error at most
0.15px. At most three components are admitted; a single component must be slender.

Candidates are ranked by source/current coordinate displacement and ink-area
change. Selected axes must have zero reflection mismatch in the native bitmap.
The bitmap is measured, never edited. Already-symmetric inputs remain exactly
unchanged. Existing coordinate ownership is respected. Source displacement remains
within the existing 2px bound. These choices are experimental interpretations,
not claims of literal paper or Microsoft conformance.

## Evidence and limitations

The full 832-glyph admitted specimen yields 25 candidates, 727 unaffected cases,
73 already-symmetric cases, and 7 holds. The 49 previously unsupported cases remain
outside this specimen. Native exported geometry, raster symmetry, advance metrics,
and white-counter count are verified. Forty-seven focused tests pass, including
collinear-level consistency, component centring, ownership, and exact no-op for
an already-symmetric input. Input source hashes are recorded.

All 25 changed panels were inspected. Plus-sign arm balance and Source Sans 3's
split vertical-stroke widths improve. Exact symmetry is insufficient as a quality
criterion: Literata's narrow tapers become angular and some small dots remain
coarse. These cases require visual review and potentially a better fidelity
objective. The experiment is unpromoted. Effects also reach H, i, and quotation
marks through geometry recognition; all are shown in the review gallery.

Run with the font-probe runtime:

```sh
OPENBLAS_NUM_THREADS=1 PYTHONPATH=tools/font_probe tools/font_probe/.venv/bin/python tools/font_probe/compare_axis_consistency.py
```

The output directory `tools/font_probe/out/axis-consistency-v1/` must be empty.
`index.html` shows every changed admitted case with smooth source and before/after
columns. `diagnostics.html` lists held cases separately; `report.json` records
outcomes and provenance.

## Horizontal phase finishing experiment

Generic horizontal rigid phase only: dx in -0.5/-0.25/0/+0.25/+0.5 px, no y
motion, no stretching, no curve reconstruction, no level remapping. Whole-glyph
shifts first, then one eligible component at a time; all other coordinates
exact. Components come from source geometry (transitive y-overlap groups
counters with their enclosing outline) and qualify on source-coaxial offset
<= 0.15 px plus actual sampled horizontal source reflection max residual
<= 0.15 px (experimental thresholds, not paper claims). Single-component
near-symmetric glyphs qualify the same way. Renders reuse the hinted baseline
flags after a zero-shift exact bitmap/advance gate over all 832 admitted cases
(an unhinted re-render drifts: Literata14 T 1 px, SourceSans16 +3 px,
SourceSans20 +4 px). Acceptance needs zero candidate full-raster x mismatch,
preserved advance/bbox dimensions/counter count, ink area within max(1 px, 5%),
owned point-axis values undisturbed within 1/64, existing cardinal-edge order,
and native agreement within 1/128; rank is least movement, then least ink
change. Ownership/order are read from `upstream_audit` in the corrected
`source-bitmap-constraints-v2` report (v1 stamped all rows with the last
character's audit and must not be used). Percentage cases are evaluated for
coverage but deferred, never promoted. Baseline `source-bitmap-v1` unchanged.

Counts over 832 admitted: 1 accepted for human review (Source Sans 3 14 `!`,
whole -0.25 px, x mismatch 2 -> 0, ink +1), 186 no-change (x symmetry already
zero), 633 held (524 raster mismatch, 94 ownership, 15 bbox; 570 with no
eligible unit), 12 `%` deferred with no effect. Large ink changes are held;
asymmetric cases needing refitting (e.g. Literata `+`, `T`) stay held honestly.

Outputs: `tools/font_probe/out/axis-placement-candidate-v1/` (`changes.html`
accepted only, `index.html` focus +, T, ! gallery of 36 with proposed or
held reason, `diagnostics.html` holds plus deferred coverage) and the corrected
measurement rerun `tools/font_probe/out/axis-placement-audit-v2/`. Nothing is
promoted; parent reviews the single candidate panel.

## Visual approval (2026-09-09)

The user explicitly visually approved the `axis-placement-candidate-v2`
candidate `Source Sans 3 14 !` (`whole@-0.25px`, x mismatch 2 -> 0, ink +1,
export-verified). This approval applies to this candidate only; it is not
integrated yet and no other symmetry candidates are approved. Literata `+`
and `T` asymmetry cases remain under trace (see
`tools/font_probe/out/literata-axis-trace-v1/`).

## Central-upright focus experiment (2026-09-09)

New driver only (`tools/font_probe/compare_central_upright.py`); no kernel
change, no redesign. An experimental context-manager patch routes the
Pipeline's geometric correction through the original
`geometric_candidate.correct(data, center_fit=central_upright_fit.fit)`,
patching the `build_source_bitmap`/`geometric_candidate`/`cumulative_hinter`
aliases (asserted active) and restoring on exit (no recursive patch;
defaults unchanged). Per-call audit
counters live in the wrapper; `fit` carries no identity. Source fonts
execute every run; no checkpoint chain is read.

Confirmed run: Lit 14 plus under the real fixed callback, with the
actual repo `Pipeline.baseline` and patched `cumulative_hinter.prepare`.
Kernel knots `[1,4,5,7]` became `[2,4,5,7]`; early preterminal and the
prepare baseline/upstream x were all
`[4,4,2,2,4,4,5,5,7,7,5,5]`. Joint prepare returned x
`[3.855263,3.855263,1,1.612155,3.836466,3.897243,4.855263,4.855263,7,6.993108,4.979323,4.944862]`.
Shared support unaffected; ownership 0; status `jointfit`. Final bitmap
unchanged.

Hard-constraint source-baseline graph: `{id 6, kind Abs, point 2,
normal [1,0], value 78 font units, metric True, representative_owned
True}` maps to x 1 px; `{id 12, kind Dist, point 8, sources [2], normal
[1,0], value 426 font units, metric True, representative_owned True}`
maps to rounded width 6 px / right x 7. `joint_stroke_fit.fit` protects
every metric and P* constraint (line ~143), so the outer bounds stay
fixed even though upstream changed. This proves the first reset happens
at the joint solver for plus once the callback bug is fixed — not just
rounding, and not a later finish. T 14 held `no-admissible-target`
(curve guard); T 18 was already centered by this detector; this narrow
rule does not correct T's remaining asymmetry. No new candidate
promoted; no full matrix necessary because focus showed no improvement.
Previously approved `!` unchanged; everything here is pending separate
review.

Next: investigate metric classification — distinguish adjustable
glyph-shape bounds vs advance/font metrics before fitting a common
center with compatible pixel-width parity. Do not claim the paper is
erroneous or relax all metrics.

Experimental bounds: overlap .15 glyph height, reflection .15 px, stem max
.25 height, current width exact preserved, positive-affine curve guard.
Tests: 6 `test_central_upright` + 20 export/baseline (`test_build_source_bitmap`,
`test_source_constraints`) pass.

## Shape-bounds experiment v1 (2026-09-09)

Glyph extrema (`metric_role` glyph-x/y-bound) are shape bounds, distinct
from advances; y-bounds, baseline links, P* never replaced. Opt-in
`central_upright_shape` carries source-collinear member targets
(`member_targets` in fit evidence, keyed by source x) through cumulative
`prepare` and `reflect`, replacing only x glyph-bound Abs/Dist equations
(ids 6/12 for Literata plus) with exact px values (`round=False`).
Conflicts with existing owners HOLD with reason; claim-on-temp then
commit, no superseding, no partial mutation. Unknown `metric_role`
holds; missing x-bound endpoint holds all.

Shape-bounds v2 full run `../../tools/font_probe/out/central-upright-shape-bounds-v2`
(2026-09-09): 832 admitted + 49 unchanged exclusions; 10 final `+`
bitmap changes. Five review candidates with x mismatch
driven to 0 (Literata 14/18/20, SourceSans3 16/20). Five held
preservation failures on already-x-symmetric baselines (Roboto
14/16/18, SourceSans3 14/18): candidate exported but NOT reverted, no
promotion, no preservation gate applied. Reporting:
`all-affected.html` shows all 10 with disposition (candidates vs
holds kept separate); `changes.html` shows only the 5 improvements;
`diagnostics.html` links the held panels. Native/bitmap/hmtx/topology
gates still run. Limits: frozen baseline unchanged; experimental bbox
edits are an engineering choice, not paper conformance; main baseline
unaffected. Next: preservation gate, then human approval.

## Both-axis symmetry v2 (2026-09-09)

Isolated final rule, new driver only (`tools/font_probe/both_axis_symmetry.py`,
`tools/font_probe/compare_both_axis_symmetry.py`); starts from the approved
baseline and holds split boundaries instead of forcing collinearity. Generic
orthogonal 4-level rule (engineering interpretation, not a paper claim):
eligible single-contour `+` glyphs fit both axes jointly, preserving font-wide upper-height and bar-width constraints, ownership, and already-symmetric-axis coordinates exactly.
Source vertical-centre offsets of .091/.117/.12 px amplify to half-pixel
under fitting. The experiment corrects that parity conflict; the two holds
below have a separate source-level collinearity problem.

Full run
[`tools/font_probe/out/both-axis-symmetry-v2`](../../tools/font_probe/out/both-axis-symmetry-v2/):
832 admitted + 49 unchanged exclusions; 6 `+` candidates with both-axis
mismatch 0 (Roboto 16, Literata 14/18/20, Source Sans 3 14/18) for human
review in
[`index.html`](../../tools/font_probe/out/both-axis-symmetry-v2/index.html),
2 holds (Source Sans 3 16/20 `+`, fitted-source x-level split: 16 left
1.0/0.0, right 8.0/7.0, upright 3.59375/3.40625, mismatch 6; 20 left
1.0/0.0, right 10.0/9.0, mismatch 8) in
[`diagnostics.html`](../../tools/font_probe/out/both-axis-symmetry-v2/diagnostics.html).
Earlier central-upright-shape-bounds-v2 Source Sans 16/20 plus rows are
untouched under that separate input baseline. Gallery is 3 columns (true
smooth source / current / proposed). 41 tests pass; full verification
passed. No approval, no promotion.
