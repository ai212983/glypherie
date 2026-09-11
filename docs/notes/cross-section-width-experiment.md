# Cross-section width experiment

Status: Python prototype; mixed visual results, awaiting review.
Investigation: 2026-09-08.

## Model

The [distance audit](shared-stem-hinter.md#diagonal-distance-semantics-audit)
distinguished detected cross-section widths from representative distances.
`cross_section_widths.py` replaces eligible local diagonal distance equations
with the signed separation of two interpolated source-edge points, projected
onto the source feature normal. It uses geometry alone.

This is a material cross-section: interpolation weights stay attached to the
source edges as their endpoints move. The projection direction stays fixed.
It does not recompute the shortest perpendicular width of a rotated fitted
stroke. Straight on-curve edges must provide one unique pair at the detector's
sample level and width; unresolved matches are held. Font-wide PDist targets
also remain held pending an explicit parameter policy.

Each eligible cross-section uses its own detected width rounded to the nearest
pixel. Related-width averaging is absent from this isolated experiment. The
middle comparison column retains that earlier averaging/substitution experiment;
the left bitmap is the original-equation baseline for measuring changes.

Four-point relations can introduce dependencies beyond the existing point DAG.
The prototype solves the complete linear system simultaneously. All other
selected equations and their rounding remain as recorded. Requested-size SCFS
export uses the existing adapter and common monochrome scan converter. This is
an experimental solver extension, not a new paper-conformance claim.

## Verification and scope

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python -m unittest discover -s tools/font_probe -p test_cross_section_widths.py
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/compare_cross_section_widths.py
```

The runner requires an empty `tools/font_probe/out/cross-section-widths-v1/`.
It inventories all 426 detected slants across the 881-case repertoire: 324 exact
source-section reconstructions and 102 held matches. It renders the same 32
Roboto cases as the prior width comparison, preserving the eight coordinated
exports and the active pipeline. Broader font rendering remains a later gate.

All 32 systems reproduce the original solver before row replacement. Independent
section measurements agree with detected widths within 0.000001 font units.
Source-RHS reconstruction verifies matrix rank and numerical stability; it is
not independent evidence of original hinting-policy correctness. All candidate
equation residuals pass, native coordinates match the quantized solver output,
and source outline points/flags/contours remain unchanged. Maximum matrix condition
number is 11.53 and maximum source movement is 2.13px. Five focused tests cover
taper measurement, representative independence of the section equation, contour
reindexing/reversal, ambiguity and baseline matrix semantics. Representative
independence of the complete anchored fitting system is still unproven.

## Visual audit

All 32 candidate images were inspected together; changed focal cases were also
inspected in full comparison panels. There are 21 changed and 11 identical
bitmaps, with zero execution failures. The report records reflection diagnostics
alongside counters, components, support weights, residuals and input hashes.

- Roboto 16px V remains thin and asymmetric; this is not resolved.
- Roboto 16px Y has fuller areas than direct substitution but uneven weight;
  its reflection difference increases from 10 to 12 against original equations.
- Roboto 18px W becomes more uneven (reflection difference 46 to 76).
- Roboto 18px A is held because its section match is unresolved. Its unchanged
  result is not validation of the new equation.
- Smaller X/x and the other candidates still show mixed weight and symmetry.

Keep this prototype experimental. A correct local cross-section equation does
not establish a suitable rounding policy or preserve the full stroke shape.
Further work must inspect width along the fitted sides and anchor movement,
while retaining the held-support and font-wide-parameter cases explicitly.

## Whole-side priority experiment

Status: rejected after visual audit.

`compare_cross_section_widths.py --whole` writes
`tools/font_probe/out/whole-stroke-widths-v1/`. Its middle column is the frozen
midpoint experiment. `whole_stroke_widths.py` constrains both matched straight
sides to the source feature normal, flattening source taper, and fixes their
separation. Parallel sides then have the same width at both ends. These geometry
equations precede compatible global/metric constraints, then other recorded
equations. Incremental orthogonal resolution reports every incompatible original
equation and its final residual; it does not soften conflicts. Geometry admission
and equal-priority ties follow recorded order, an explicit experimental policy.
PDist targets and unresolved support matches remain held.

All 32 exports pass numerical and native execution checks; 28 bitmaps change and
four remain identical. Three focused tests verify explicit conflict reporting,
redundancy handling and full-side width on a tapered synthetic stroke. The five
cross-section tests also pass. The contact sheet covers every generated candidate;
the focal W comparison was additionally inspected at full size.

Roboto 18px W loses the midpoint wedge, but w and X/x suffer severe deformation.
Maximum source movement reaches 10.85px. Releasing incompatible anchors and other
relations can destroy the glyph despite exact side widths. This falsifies the
blanket geometry-first priority policy. The gallery is labeled rejected and the
active pipeline remains unchanged. No mirror correction was applied; coordinated
placement remains unresolved rather than being claimed by width equality.

A subsequent experiment must protect metric and junction placement, identifying
which side relationships can be preserved together. Incompatible arrangements
should hold the candidate instead of sacrificing those anchors. This result does
not establish that a complete Microsoft-style paired operation would fail: this
prototype implements its own simultaneous priority policy, not VTT's operation.

## Protected whole-side experiment

`compare_cross_section_widths.py --protected` writes
`tools/font_probe/out/protected-stroke-widths-v1/`. It preserves every existing
equation except the local width relations selected for replacement. This protects
metrics, global parameters, junction links and existing side relationships. A
conflict holds the entire candidate and returns the original solver result;
the audit records conflicting geometry rows and their residuals at that result.
The protection is deliberately stronger than preserving metric anchors alone.

All 32 exports reproduce the original bitmaps: 28 candidates are held for
conflicts and four have no matched support. Zero original equations are released.
Strict native checks pass. Four focused tests cover conflict reporting,
redundancy, preservation under incompatible taper, and a compatible synthetic
width change that succeeds with protected equations. Thus the implementation can
apply compatible changes, but these real cases require revising existing
relationships together. Bitmap identity confirms preservation, not visual
approval. Existing symmetry and weight defects remain unresolved.

The next design question is how to resolve a stroke's anchor and junction
relationships jointly. Blanket geometry priority causes deformation; preserving
every old relationship prevents these candidates from changing. Neither result
justifies a new glyph-specific exception or promotion into the active pipeline.

## Joint shape and stroke fit

`compare_cross_section_widths.py --joint` writes
`tools/font_probe/out/joint-stroke-widths-v1/`. The three bitmap columns are
original equations, the midpoint experiment, and the joint candidate.
`joint_stroke_fit.py` solves constrained least squares with all selected metric
and global parameter equations held exactly. Remaining local equations are
replaced by objectives on source positions, contour-edge vectors, and matched
whole-side geometry. Shared points have one coordinate variable, so incident
features are solved together. Every old local equation's changed residual is
reported. Junction shape is encouraged by source fidelity, not enforced exactly.

Squared source-coordinate and edge-vector residuals have weight 1; squared
whole-side alignment and width residuals have weight 4. These numerical weights
are an explicit uncalibrated experiment. Width targets retain nearest-pixel
rounding. Geometry goals are soft, so neither straightness nor target width is
claimed as exact. This optimization is our own model extension, not a faithful
implementation of Shamir or Microsoft. No symmetry correction is applied.

All 32 exports pass; 28 change and four unmatched A cases remain original.
Maximum metric/global residual before export is below 0.00000001px; maximum
source movement is 2.011px. The largest soft geometry residual is 0.552px.
Four tests cover hard-metric preservation, incompatible metrics, explicit soft
compromise and variable-order invariance. Native coordinates match the quantized
solution; exact float constraint satisfaction does not imply exact satisfaction
after 26.6 quantization.

All candidates were inspected in the contact sheet, with focal Y/W/x comparisons
also inspected individually. Large deformations from geometry-first fitting are
absent, but quality remains mixed. Reflection differences improve for 16px Y
(10 to 4), 16px x (22 to 4), and 14px w (16 to 8). They worsen for 16px W
(28 to 48) and 20px W (32 to 38). Y still has an uneven vertical stem and W
remains uneven. These diagnostics are not acceptance. The joint candidate remains
experimental; the active pipeline and the eight coordinated exports are preserved.

## Complete straight stems in the joint fit

`compare_cross_section_widths.py --stems` writes
`tools/font_probe/out/joint-complete-stems-v1/`. The middle column is the previous
joint fit. For detected cardinal stems and bars, contiguous source contour runs
with exactly equal projected coordinates define each side. The selected width
relation and all side-member alignments are held hard together. Incomplete side
support is reported; an incompatible complete proposal retains the previous
joint fit. Diagonal soft goals and objective weights stay unchanged. The fitting
interface receives geometry and numeric records, not character identities.

All 32 exports pass; only Roboto Y at 14/16/18/20px changes from the previous joint
candidate (2/6/7/1 bitmap pixels). Its vertical sides are now straight and retain
the 1/2/2/2px width targets. All four changed panels were visually inspected.
The other 28 bitmaps are identical to the previously reviewed joint candidate;
four unmatched A cases still retain the original equations. No proposal conflicts
occurred. Six tests pass, including complete contiguous-side membership and
incomplete-support handling.

The uneven vertical stem is resolved in this experiment. Arm weight and symmetry
remain mixed; the whole-glyph reflection differences are 10/8/16/0 pixels at the
four sizes. The 20px Y is symmetric by that metric, while the others require
further work. This is a generic cardinal-feature relationship tested within the
bounded 32-case scope, not a corpus-wide rollout or visual approval.

The user subsequently approved the reviewed straight stems. The
[broader coverage audit](complete-stem-coverage.md) preserves that scoped approval
and records additional junction regressions that block general adoption.
