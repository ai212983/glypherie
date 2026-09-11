# Complete-stem corpus coverage

Status: audited; broader adoption blocked by junction regressions.
Investigation: 2026-09-08.

The user approved straight-stem behavior in the four Y specimens from the
[bounded joint experiment](cross-section-width-experiment.md). This audit checks
the same rule across the 881-case calibration repertoire without expanding the
joint fitter's applicability or changing its algorithm.

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/audit_complete_stem_coverage.py
```

Use an empty `tools/font_probe/out/complete-stem-coverage-v1/`. Each pair compares
the same joint fit with complete cardinal stem/bar protection disabled/enabled.
The smooth source column is a visual reference. The existing uniform candidate
and previously approved coordinated M/N exports are not replaced.

| Outcome | Cases |
| --- | ---: |
| Changed bitmap | 44 |
| Identical bitmap after fitting | 55 |
| Proposal held for conflict | 3 |
| Complete stem detected, outside current joint-fit path | 501 |
| No complete stem support | 278 |

The current joint fitter requires an eligible local diagonal goal. The 501 cases
outside that path therefore remain outside this rule's execution coverage; the
audit does not claim a complete generator rollout. Held cases are Roboto 5 at
16/18/20px and retain their before result exactly.

All 102 rendered pairs pass strict native execution, source-outline preservation,
and agreement with quantized solver coordinates. Protected side straightness is
checked in both fitted and native coordinates. Input hashes remain unchanged.
Six focused joint-fit/support tests pass. None of the changed candidates exceeds
the 4px source-movement diagnostic screen.

## Changed specimens and review

`changes.html` lists all 44 changed pairs; `index.html` includes unchanged and held
pairs. `report.json` includes every screened case and its coverage status.

| Font | Changed glyphs by size |
| --- | --- |
| Literata | 14: N V z; 16: Z z; 18: 4 A M N; 20: 4 N V k x z |
| Roboto | 14: 2 N Y Z k z; 16: 2 M N Q Y Z k z; 18: 2 7 M N Q Y Z z; 20: M Q R Y Z z |
| Source Sans 3 | 20: W |

All 44 changed before/after pairs were inspected. Several N/Y/Z/z examples gain
straighter stems or bars. Changes also propagate into serif, curve and junction
geometry, so straightness alone cannot establish quality.

**Roboto M at 16px and 18px gains an enclosed white pixel region near the right
diagonal/stem junction.** Both before images have zero enclosed white regions;
both after images have one. Visual inspection confirms the holes. These are
regressions of this before/after experiment, even though other M geometry also
changes. Their mechanism has not yet been traced in this pass.

The gallery puts these two cases first. Retain the prior Y approval within its
reviewed scope, but defer broader adoption until the junction regressions are
understood and corrected. The next investigation should trace the shared support
and fitted contour around those holes; changing width or adding pixel patches
would precede establishing the cause.

## Terminal-length selection correction

The user reported an overlong upper bar in Roboto 14px z and requested this
correction before the M-hole investigation. The detected 821-unit horizontal
distance between short vertical terminal edges was being protected as stem
thickness, rounding to 6px. Protecting the upper bar's real thickness alone does
not require that horizontal length constraint.

`terminal_competitor` in `joint_stroke_fit.py` excludes a cardinal pair from
complete-stem protection when its width exceeds its supported length and an
overlapping perpendicular stem/bar has narrower width and longer support, with
support longer than its own width. Support rectangles must overlap in both axes.
This is a geometric selection policy, not a paper-derived threshold or glyph
exception. It changes protection eligibility; it does not remove the detected
feature or discard existing global/metric constraints.

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/audit_complete_stem_coverage.py --terminal-filter
```

`tools/font_probe/out/stem-terminal-filter-v1/changes.html` compares frozen prior
complete-stem exports with the corrected candidate. The 881-case screen yields
six changed pairs, 93 identical pairs and the same three held conflicts; the
remaining applicability counts are unchanged. The six changes are one pixel each:
Roboto Z at 14/16/18px, z at 14/16px and N at 18px. All six panels were inspected.
The extra upper-bar pixel in 14px z is removed. Other changes affect bar endings
or the diagonal/junction in N, and remain available for user review.

All exports pass strict execution and protected-side checks. Seven focused tests
pass, including perpendicular competition, non-overlap and retaining the longer
stroke interpretation. Reviewed Y outputs and M outputs are bitmap-identical to
the previous complete-stem candidate. The M holes remain deferred as requested;
broader adoption is still blocked by that separate issue.

## Stem continuation protection

The user approved the six terminal-filter changes and confirmed the two-link M
diagnostic. `continuation_relations` now recognizes existing unrounded zero-distance
alignments on a directly adjacent on-curve segment that leaves a protected
cardinal side within 5 degrees of its direction. It verifies source alignment,
preserves the continuation's own normal, and selects both link orientations.
All selected continuations enter the hard system together. Recognition uses
geometry and numeric graph records, with no character or family argument.

The 5-degree limit and one-segment extent are explicit experimental applicability
choices. There is no recursive propagation or invented point link. Conflicting
proposals return the previous complete-stem fit and report a held status.

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/audit_complete_stem_coverage.py --continuations
```

`tools/font_probe/out/stem-continuations-v1/changes.html` compares the frozen
terminal-filtered candidate with continuation protection. The 881-case screen
produces four changed pairs, 95 identical pairs and the same three held conflicts.
The remaining 779 cases retain the earlier applicability classification.
Only Roboto M at 14/16/18/20px selects continuation links in the executed joint
fit; each selects both existing side links. This is observed coverage, not a
glyph-specific selector or evidence about unsupported fonts.

All four changed panels were visually inspected. Enclosed white regions change
from 1 to 0 at 16px and 18px, and remain zero at 14px and 20px. No new hole appears
on the opposite side. All 102 rendered pairs pass strict execution and quantized
coordinate agreement; protected stem sides remain straight. Hard-equation
residuals for M are below 0.00000001px before quantization. Nine focused tests
pass, including both link orientations, on-curve and adjacency requirements,
steep-link exclusion, and the earlier stem/terminal checks.

The approved Y and terminal-filter bitmaps remain identical. This closes the
observed M-hole regression in the experiment. The 14px/20px M changes are presented
for review; overall diagonal quality and wider pipeline adoption remain separate
decisions. The previously approved coordinated M/N exports remain frozen.

The next isolated check is [coordinated diagonal reflection](diagonal-reflection-experiment.md).
