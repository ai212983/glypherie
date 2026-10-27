# Revision 001

## Starting point

The revision started from upstream Skrifa 0.46.2 with custom fitting developed alongside it. Current registry fitting
uses Skrifa 0.48.0. The vendored 001.02 implementation is a legacy comparison model; its baseline role name does not
confer current approval.

Current working preview identity: `font_hints_auto` fitting with `free_type_mono_terminals` scan conversion; disabling
font hints selects `upstream_mono`. The
[open iteration](03-spacing-kerning.md#selective-native-hints-and-automatic-fitting) owns its scope and assessment.

The `diagonal_fitting` overlay identifies `diagonal-shape-05`. It adopts the
[coupled whole-outline model](03-spacing-kerning.md#coupled-whole-outline-widths), approved on 2026-10-27, with the
preceding `diagonal-shape-04` local attachment and reference-height sequence for unsupported geometry. It is on by
default in new working previews (the pipeline and URL-omission defaults stay off); explicit off is honored. The broader
[curve assessment](03-spacing-kerning.md#local-curved-stroke-widths) remains open. The
[adoption record](../../hobby-fitting.md#approved-fitting-sequence-adoption) owns the preceding sequence;
`diagonal-width-01` remains the width-only comparison.

## Iterations

The separately approved `coupled-outline-01` comparison remains available as the adoption reference. This approval does
not close iteration 001.03.

| Iteration                        | Role and status                | Topics                                                                                                                                                   |
| -------------------------------- | ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [001.03](03-spacing-kerning.md)  | Working candidate; open        | Separate fitting and rasterization stages, shared bitmap layout, spacing, tracking, marks, display scaling, kerning inspection and scalar substitutions. |
| [001.02](02-light-continuity.md) | Legacy comparison model        | Binary continuity, extra-light coordination and shared width transitions.                                                                                |
| [001.01](01-diagonal-weight.md)  | Accepted and closed 2026-10-02 | Diagonal weight, border coverage and terminal shape.                                                                                                     |
