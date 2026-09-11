# Bar placement and curved terminal recovery

Status: Whole curved-stroke reconstruction and bar correction visually approved (2026-09-08); integrated into the cumulative Python specimen.

## Observed defects

Roboto 16px `4` retains a pixel below the crossbar's left end. An earlier
contour-order repair restored the corner direction, but the joint fit placed the
bar between grid lines. The recent terminal extension changes only its right end.

Roboto 16px `f` reverses the horizontal relationship between the two upper-cap
endpoints: the lower endpoint projects about 0.52px beyond the upper one. One
endpoint follows the rounded outline width; the other keeps a source-position
completion. At 18px the upper endpoint instead projects above the hook.

## Experimental policy

`tools/font_probe/junction_terminal_fit.py` accepts geometry, scale, current
coordinates, ownership, and generic contour-order repair provenance.

- For a repaired vertical corner, identify the adjacent horizontal bar boundaries
  from repeated source heights. Include contours within the repaired contour's
  bounds, allowing the counter boundary to participate. Require a unique nearby
  boundary, snap each complete boundary to its median's nearest grid line, and
  preserve the source vertical corner extension.
- Recognize short, near-cardinal caps between curves at a source outline extremum.
  Preserve the source offset between their endpoints across the cap. Restore the
  outer endpoint's small offset from its adjacent curve extremum. Blend the
  additional movements through the existing curves, stopping at their nearest
  extrema or line junctions. The two curve anchors must remain within twice the
  cap's source length along its main axis; this excludes ordinary round sides.
- Existing coordinate ownership remains authoritative; conflicts are held.

Thresholds and placement choices are experimental interpretations. They are not
claimed as literal Shamir or Microsoft instructions. The recognition uses no font
family, character, glyph ID, or size lookup. Pixel-size bounds apply uniformly.

## Comparison and validation

Run `tools/font_probe/compare_junction_terminals.py` with the font-probe Python
runtime and `PYTHONPATH=tools/font_probe`. The cumulative input includes the
stem-relative terminal experiment and previous curve improvements. Output is
`tools/font_probe/out/junction-terminals-v1/`.

The 881-case sweep has 814 unaffected cases, 8 coordinate changes with unchanged
bitmaps, 10 changed bitmaps, and 49 upstream rejected cases. The review gallery
contains all 10 changed cases with smooth source and before/after columns:

- Roboto 16 and 18px: `4`, `f`, `r`.
- Source Sans 3 14 and 18px: `7`.
- Source Sans 3 20px: `4`, `7`.

Roboto 16px `4` loses the low left pixel; Roboto 16px `f` loses its hanging cap
pixel, and 18px `f` loses the high tip pixel. Roboto 14px `f` retains its bitmap.
Other inherited shape defects remain subject to specimen review.

All changed panels were inspected. Admission checks cover finite bounded source
displacement, cardinal contour order, white-counter count, native coordinate
agreement, and unchanged advance metrics. These are not complete visual or
outline-topology proofs. The focused suite passes 36 tests, including cap locality,
mirror invariance, ownership conflicts, exclusion of closed round shapes, and
native rendering of the repaired crossbar. Human approval is still required.

## Paired movement revision

The user rejected the first curved-cap result: Roboto 18px `f` lost a top pixel,
while `r` acquired a poor top stroke. The first implementation moved the upper
edge without moving the lower edge. Terminal thickness fell from 1.55px to 0.86px
for `f` at 18px, and from 1.50/1.56px to 0.89/0.88px for `r` at 16/18px.

The revised experiment translates both cap endpoints equally along the thickness
axis, retaining their fitted separation. Local curve interpolation and horizontal
endpoint coordination remain. The independent bar correction is unchanged.
Output is `tools/font_probe/out/junction-terminals-v2/`; the v1 gallery is retained.
The comparison continues to use the pre-v1 cumulative input, avoiding accumulation
of the rejected thinning operation.

The 881-case sweep contains 814 unaffected, 6 unchanged bitmaps, 12 changed bitmaps,
and 49 upstream rejected cases. Changes comprise Roboto 14px `r`; Roboto 16/18px
`4`, `f`, `r`; Source Sans 3 14/16/18px `7`; and Source Sans 3 20px `4`, `7`.
All 12 panels were inspected. The 37 focused tests pass, with a new signed cap
thickness regression across both letters at 16/18px. The generator also verifies
native cap separation within 1/64px of the input.

This revision fixes the coordinate-level thinning but remains visually unresolved:
`r` now has a downward tip, also visible on `f` at 18px. Moving the pair according
to the upper curve anchor retains thickness but does not establish good terminal
placement or continuity with the adjacent stroke. This is an experimental result,
not a promoted correction. The next model decision must account for the adjoining
stroke's width and both curve anchors, rather than only the terminal endpoints.

## Whole curved-stroke reconstruction

The next experiment addresses the complete top stroke, starting from the
pre-terminal-warp cumulative input. In Roboto 18px `f`, the inner curve control
point at index 25 lies at x=2.625px while its stem attachment lies at x=4px.
The corresponding source control lies on the outward side of that attachment.
This reversed relationship creates the poor bend independently of the cap issue.

`tools/font_probe/curved_stroke_recovery.py` reconstructs both curve runs from
source coordinates up to their line attachments. Admission requires parallel
attachments at the same source height. Each side retains its fitted stem attachment
and curve-height extremum. Positive affine coordinate maps preserve the source
curve shape within each side. The two cap positions share their fitted horizontal
centre and source horizontal offset. Cap thickness consequently follows the two
reconstructed boundaries and their height anchors, replacing the isolated endpoint
thickness constraint. Ownership conflicts remain explicit.

This is a geometry-based experimental interpretation, not a literal paper or
Microsoft implementation. It uses the source coordinates present in the frozen
font, including their integer coordinate quantization. It reuses the existing cap
recognizer; support is limited to the admitted parallel-attachment construction.

Run `tools/font_probe/compare_curved_stroke_recovery.py` to produce
`tools/font_probe/out/curved-stroke-recovery-v1/`. The shared comparison runner
retains the independent bar correction and validates native stem attachments and
curve-height anchors, in addition to its existing admission checks.

The 881-case sweep contains 822 unaffected, 3 unchanged bitmaps, 7 changed bitmaps,
and 49 upstream rejected cases. Changed cases are Roboto 14px `f`; Roboto 16px
`4`, `f`, `j`; Roboto 18px `4`, `f`; and Source Sans 3 20px `4`.
The `r` construction is outside this rule and retains its pre-experiment rendering.

All changed panels were inspected. Roboto 18px `f` has a continuous bend and no
paired-endpoint downward tip. The user approved the seven-case comparison on
2026-09-08, including the smaller hook of Roboto 14px `f`. This approves the
rendered Python candidate; cumulative integration is verified below.
The earlier endpoint-only candidates remain superseded. Forty-one focused tests pass, including
source-side control placement, fixed attachments and heights, mirror invariance,
ownership/input preservation, and eight-connected native ink for Roboto 18px `f`.


## Cumulative integration

`cumulative_hinter.finalize` applies the approved geometry pass after the saved
curve, symmetry, and stem-relative terminal stages. `cumulative_inputs.py` owns
that explicit checkpoint order and fails if a recorded changed output is missing,
preventing silent fallback to an older rendering. The endpoint-only candidates
are absent from the input chain.

`tools/font_probe/build_cumulative_recovery.py` exports
`tools/font_probe/out/cumulative-hinter-v7/`, including 12 combined face/size fonts,
a complete specimen, the seven-case changes page, diagnostics, and input hashes.
This continues the saved Python checkpoints; earlier stages still require those
artifacts. It is not yet a standalone source-font generator.

All 832 admitted glyphs match the approved cumulative reference in native bitmap
output. Seven contain the approved changes; 825 retain their previous bitmap.
Native coordinates, advance metrics, and white-counter counts are checked. The
49 inherited rejected cases appear only in diagnostics and are excluded from the
exported Unicode maps. They remain unresolved. Forty-three focused tests pass,
including missing-checkpoint and missing-recorded-correction failure cases.
