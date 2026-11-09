# Revision 001

<!-- cspell:words TypeFacet fontforge fullwindow yinyangfit multiscale supremum -->

## Starting point

The revision started from upstream Skrifa 0.46.2 with custom fitting developed alongside it. Current registry fitting
uses Skrifa 0.48.0. The vendored 001.02 implementation is a legacy comparison model; its baseline role name does not
confer current approval.

Current working preview identity: `font_hints_auto` fitting with `free_type_mono_terminals` scan conversion; disabling
font hints selects `upstream_mono`. The
[open iteration](03-spacing-kerning.md#selective-native-hints-and-automatic-fitting) owns its scope and assessment. The
[baseline association](03-spacing-kerning.md#source-defined-baseline-alignment) stage identifies `baseline-align-01`;
its local geometric correction is implemented with optical assessment pending.

The `diagonal_fitting` overlay identifies `diagonal-shape-06`. It routes automatic-axis outlines through the
source-shape stage, which solves the translated raw head profile with the certified standard in the original upstream
budget; the preceding `diagonal-shape-05` sequence (native-Y coupled, shared-border upright, pre-coupled chain) stays
frozen for historical packet replay, and the `diagonal-shape-04` pre-coupled chain still handles unsupported geometry.
It is on by default in new working previews (the pipeline and URL-omission defaults stay off); explicit off is honored.
The broader [curve assessment](03-spacing-kerning.md#local-curved-stroke-widths) remains open. The
[adoption record](../../hobby-fitting.md#approved-fitting-sequence-adoption) owns the preceding sequence;
`diagonal-width-01` remains the width-only comparison.

The working overlay additionally identifies `diagonal-placement-01` when its
[shared stroke-placement stage](../../hobby-fitting.md#shared-stroke-placement) applies. Source-relative widths and
joint border rotation carry eligible curved attachments in one bounded solve; source-certified reflected arms share a
geometric phase. The preceding `diagonal-shape-06` sequence remains frozen for historical replay. Optical assessment of
this extension remains open in the [iteration notes](03-spacing-kerning.md#terminal-reference-heights).

The [source-shape correction](03-spacing-kerning.md#source-shape-correction-approved-with-limits) was optically approved
with limits on 2026-10-29. Iteration 001.03 remains open.

The isolated
[fixed-alphabet spacing experiment](../../designs/text-layout/contextual-spacing-and-healing.md#fixed-alphabet-density-experiment)
identifies `hu_fitted_full_density_conserved_touch` as the construction-order candidate against
`hu_fitted_density_conserved_touch`, its preceding fitted-wall control. `hu_density_conserved_touch` retains the
bitmap-wall control. `hu_density_conserved` retains strict clearance and `hu_alphabet_source_target` retains the source
calibration control. `hu_source_calibrated` and `hu_hersch` retain the preceding shared-target comparisons. Optical
assessment is pending; these opt-in modes do not change the maintained renderer identity above.

The
[complete-cell geometry assessment](../../designs/text-layout/contextual-spacing-and-healing.md#complete-cell-geometry-assessment)
is a separate masked comparison of the full fitted-outline candidate with complete binary-cell measurement. It adds no
selected solver model or approved identity.

The isolated
[TypeFacet density-controlled comparison](../../designs/text-layout/contextual-spacing-and-healing.md#typefacet-density-controlled-comparison)
identifies `typefacet-fixed-lowercase-density-v1` for frozen Literata lowercase assessment. It adds no selectable solver
model or maintained renderer identity; the preceding full fitted-outline model stays control B.

The subsequent
[constrained integer trial](../../designs/text-layout/contextual-spacing-and-healing.md#typefacet-constrained-integer-experiment)
identifies `typefacet-constrained-integer-v1`, with no post-solve normalization. It is a separate opt-in reading
experiment with calibration and optical assessment pending; it does not replace B or add a maintained solver selection.

The
[interchangeable kerning interface](../../designs/text-layout/contextual-spacing-and-healing.md#interchangeable-kerning-methods)
introduces main-editor method selection independently of fitting and rasterization. The current source/bearing method
remains the default. Runtime TypeFacet (`typefacet`), full-outline density-conserving Hu/Hersch (`hu_hersch`) and
FontForge-derived source-relative spacing (`fontforge`) are separate opt-in adapters. Their method-specific calculation
does not change the renderer identity above. Broader optical assessment remains pending.

The isolated
[YinYangFit recovery](../../designs/text-layout/contextual-spacing-and-healing.md#yinyangfit-feasibility-experiment)
identifies `yinyangfit-historical-recovery-v1` for the initialized historical Torch scorer. Executable scoring and a
bounded backward probe are verified. The subsequent `yinyangfit-short-training-v1` identifies three Adam updates with
exact checkpoint replay. The broader `yinyangfit-pair-holdout-v1` completes thirteen training updates and exact final
update replay. Loss decreases on four optimizer-excluded pairs, but all evaluated preferred offsets remain unchanged at
the widest candidate. Calibration, convergence, generalization and optical assessment remain pending. These experiments
add no maintained kerning selection or renderer identity.

The isolated
[YinYangFit recovery](../../designs/text-layout/contextual-spacing-and-healing.md#yinyangfit-feasibility-experiment)
identifies `yinyangfit-historical-recovery-v1` for the initialized historical Torch scorer. Executable scoring and a
bounded backward probe are verified. The subsequent `yinyangfit-short-training-v1` identifies three Adam updates with
exact checkpoint replay. The broader `yinyangfit-pair-holdout-v1` completes thirteen training updates and exact final
update replay. Loss decreases on four optimizer-excluded pairs, but all evaluated preferred offsets remain unchanged at
the widest candidate. Calibration, convergence, generalization and optical assessment remain pending. These experiments
add no maintained kerning selection or renderer identity.

The isolated `yinyangfit-interactive-v1` experiment exposes three global controls (target cohesion, interaction reach,
proximity falloff) over delivered Mono/Gray placements without training, as a nearest-distance probe rather than a
reproduction of YinYangFit's oriented model. Frozen-setting evidence and a self-contained interactive page cover two
families at 16/24 px; all three controls demonstrably move chosen integer steps, endpoints saturate honestly at recorded
domain boundaries, ties anchor at the global valid minimum, and words show a captured-source fractional baseline beside
the experiment layout. The follow-on `yinyangfit-interactive-b2-fullwindow-v1` experimental version scores the full
query window with its own identities and archived v1 reference. No maintained method or default changes. Optical
assessment remains pending.

The v3 sample-gallery page now runs the oriented-engine model
`yinyangfit-oriented-engine-v1` (oriented fields, multiscale combination, SCORE-v2) over all 13 canonical root samples
in both profiles, with target G2, reach and falloff controls and a shipped default-geometry fast path plus exact
on-demand WASM scoring. The historical B2 page and its tables are archived with no active UI option or fallback.
Settings classify as Standard (`q <= 4.2` and `R <= 24`) or Extended (within guardrails, with the compact near-tie
notice); the Extended agreement bound is an empirical maximum over 14 sampled cases, not a proven supremum. No
maintained method or default changes. Optical assessment remains pending.

## Iterations

The separately approved `coupled-outline-01` comparison remains available as the adoption reference. This approval does
not close iteration 001.03.

| Iteration                        | Role and status                | Topics                                                                                                                                                   |
| -------------------------------- | ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [001.03](03-spacing-kerning.md)  | Working candidate; open        | Separate fitting and rasterization stages, shared bitmap layout, spacing, tracking, marks, display scaling, kerning inspection and scalar substitutions. |
| [001.02](02-light-continuity.md) | Legacy comparison model        | Binary continuity, extra-light coordination and shared width transitions.                                                                                |
| [001.01](01-diagonal-weight.md)  | Accepted and closed 2026-10-02 | Diagonal weight, border coverage and terminal shape.                                                                                                     |
