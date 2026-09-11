# Stem-relative terminal placement

Status: experimental comparison; visual approval pending.
Reviewed: 2026-09-08

## Cause and experiment

Literata 14 a's tail is unchanged by the source-junction correction. Its outer
stem sits at x=6px while its tip sits at x=8px. The source extension is 1.428px.
The baseline anchors the left outline edge at 1px and rounds the overall ink
width to 7px, placing the tip at 8px. Its unchanged hmtx advance is separate.

The experiment replaces that competing horizontal outline-dimension obligation
with an unrounded source extension from the supporting stem. For this case the
tip moves to x=7.428px before native quantization, shortening the visible tail by
one pixel. The stem, y coordinates, and advance width remain unchanged.

## Geometric scope and explicit choices

`stem_relative_terminals` accepts prepared source geometry, fitted coordinates
and coordinate ownership. Glyph identities remain in the adapter and gallery.

- A vertical straight side must end in a contour excursion that returns across
  its x plane and contains a global horizontal outline extremum.
- The extension and the entire excursion's displacement along the stem must
  each be at most half the supporting side's length. This distinguishes compact
  ends from paths wrapping around the glyph. It is an experimental scope bound.
- The supporting side must be unique for the tip. Both contour traversal orders
  and both horizontal directions are supported. Multiple disjoint terminals can
  be fitted; overlapping movement regions are held.
- The tip uses the source extension without pixel rounding. Additional x
  movement is blended over source control points in the excursion, weighted by
  their outward distance from the support plane and bounded between zero and
  one. Points at or behind the support plane retain their coordinates.
- Only horizontal outline-dimension constraints involving the terminal tip are
  released. Their complete equations appear in the report. Other metric/global
  relationships and existing coordinate ownership remain protected. The native
  adapter verifies the hmtx values are identical after export.

This is a local placement experiment, not a claim that Shamir or Microsoft
specifies this recognizer, blending policy or priority replacement. The baseline
profile and its graph builder remain unchanged.

## Coverage and validation

The 881-case screen produces 41 changed bitmaps, 53 fitted-but-identical bitmaps,
625 unchanged/nonmatching cases, 113 held cases and 49 inherited rejections.
Held cases comprise 67 ownership conflicts, 34 cases without an identified
outline-dimension constraint, four other protected-relationship conflicts, four
overlapping terminal regions, and four point-layout mismatches.

All 41 changed panels were inspected. The effects include shorter tails/feet,
changed bracket ends, crossbar extensions and some lengthened terminals where
source-relative placement requires it. The visual review should assess these
separately; improving a's tail is not blanket approval of those changes.

Thirty focused tests pass, including source-extension preservation, mirrored and
reversed contours, existing-size no-op behavior, and explicit ownership conflicts.
Admitted exports pass coordinate reproduction, source-displacement, cardinal
edge order, counter-count and unchanged-advance checks. These are numerical
checks rather than visual acceptance.

The current column uses the source-junction experiment where exported, followed
by the approved bounded-curve candidate and preceding specimen layers. This
terminal pass does not address the separate upper-arc pixel issue in p.

Review: `tools/font_probe/out/stem-relative-terminals-v1/index.html`.

```sh
OPENBLAS_NUM_THREADS=1 PYTHONPATH=tools/font_probe tools/font_probe/.venv/bin/python tools/font_probe/compare_stem_relative_terminals.py
```
