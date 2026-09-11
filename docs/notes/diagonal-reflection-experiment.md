# Coordinated diagonal reflection

This Python experiment extends the joint fitter after the
[stem continuation check](complete-stem-coverage.md). Its output awaits visual
approval before adoption.

## Rule

Find a unique reflected correspondence in each source contour, preserving point
tags and reversed cyclic order. The existing recognition tolerance is em/512.
For matched outlines, solve mirrored point positions together with the existing
hard metrics, complete-stem widths, side alignments and continuation links.
Each pair shares a height and has horizontal positions equidistant from a common
axis. Recognition receives geometry and numeric records rather than glyph identity.

Try five half-pixel axes around the nearest half-pixel source center, spanning
one pixel in either direction. Select the feasible fit with the lowest existing
soft objective; ties prefer proximity to the source center, then the lower axis.
Unmatched outlines and incompatible proposals retain their previous fit.

Source matching tolerance, the bounded axis search and hard reflection are our
experimental choices. This is an extension of the joint fitter, not a claim of
paper or Microsoft conformance. Source positions, edge vectors and diagonal
widths keep their existing soft weights. Reflection can therefore change their
compromise even while protected straight-stem equations remain satisfied.

## Reproduction and coverage

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/audit_complete_stem_coverage.py --reflection
```

The gallery is `tools/font_probe/out/reflection-coverage-v1/changes.html`.
Every panel includes a smooth source reference, the current joint fit and the
reflection candidate. `index.html` contains all rendered pairs; `report.json`
records the full screen.

Of 881 screened cases, 154 enter the comparison: 13 bitmaps change, 138 remain
identical and three retain an earlier conflict. The other 727 are outside the
joint fitter's applicability. Sixteen fits satisfy source reflection recognition;
three of those already have the same bitmap.

Changed Roboto cases:

| Glyph | Sizes in pixels |
| --- | --- |
| M | 14, 16, 18, 20 |
| X | 14, 16, 18, 20 |
| Y | 14, 16, 18 |
| V | 16, 18 |

All thirteen resulting bitmaps have zero horizontal reflection difference and
zero enclosed white regions. Lowercase x remains unchanged: its source outline
falls outside the reflection tolerance. Matching tolerances remain unchanged
for this experiment.

## Review

All thirteen changed panels were visually inspected. X, Y and V now have paired
left/right steps. M has continuous outer stems, but its central join becomes
flatter and its shoulders heavier in some sizes; M14 changes despite already
having a symmetric bitmap. Those shape changes need explicit review rather than
acceptance based on the symmetry metric alone.

All 154 exported pairs pass strict execution and quantized-coordinate agreement.
Ten focused fitter tests pass, including joint reflection with fixed metric
anchors. This establishes the experiment's constraint behavior; overall visual
quality and full generated-specimen approval remain open.

## Preserve already symmetric output

The bitmap guard runs before source reflection matching. It checks exact
left/right ink equality around the current ink bounds, independent of position.
An already symmetric bitmap retains the current fit and reports
`already-symmetric`. The reflection API requires the current rendered ink so
callers cannot accidentally omit this guard.

The same command now writes `tools/font_probe/out/reflection-coverage-v2/`.
The 881-case rerun contains 12 changed bitmaps, 139 identical pairs, three held
conflicts and 727 cases outside the joint fit. Five executed fits select the
new guard, all with zero changed pixels. Roboto M14 retains its previous shape.
The remaining twelve comparison panels are pixel-identical to the reviewed v1
panels, so M16/18/20 retain the visual tradeoffs described above.

All exported pairs pass execution and coordinate checks. The ten focused tests
also verify exact fit preservation for symmetric ink at a translated position
and rejection of a missing bitmap. Documentation links and diff whitespace
checks pass.

The [cumulative Python integration](cumulative-hinter-integration.md) now restores
upstream geometric corrections and coordinated supports around this experiment.
Its full specimen is the next review surface; this isolated gallery remains a
record of the reflection-only comparison.
