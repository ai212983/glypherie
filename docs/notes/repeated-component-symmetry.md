# Repeated-component symmetry

Status: isolated Python review candidate; builds on the reviewed v6 specimen.

## Scope and rule

The source-curve check found that the remaining global-reflection mismatches are
not explained solely by discrete sample phase. This experiment therefore starts
with a narrower relationship: translated, repeated source contours arranged
horizontally or vertically. It compares contour points with matching on/off-curve
tags and cyclic order, after removing their centers. Recognition keeps em/512
as its error limit and requires separated source bounds.

`repeated_component_symmetry.fit` receives geometry, the current fit, rendered
ink and coordinate ownership. Ambiguous repeated groups and owned components
are held. Nested counters and diagonally displaced rings are outside this rule.
Already identical component bitmaps at aligned positions remain unchanged.

The candidate uses the shared source shape, rather than averaging distorted
hinted shapes. The current separation is rounded to an integer pixel; both
components receive the same shape and pixel phase. Sixteen quarter-pixel phase
combinations are compared using squared error between monochrome coverage and
an 8x supersampled reference, plus a 0.02-weighted coordinate movement penalty.
Both rasterized components must be identical and have at least one pixel of
clear separation. These choices are experimental raster-fitting policies, not
paper or Microsoft conformance claims.

## Coverage and review

The 881-case screen finds 36 matching cases: 14 change and 22 remain identical.
There are 796 no-matches and 49 inherited rejected baselines. Rejected cases
appear only in `diagnostics.html`, not the visual review page.

| Glyph | Changed font/size cases |
| --- | --- |
| Double quote | Literata 16/18; Roboto 18/20; Source Sans 3 16/18/20 |
| Colon | Literata 18/20; Roboto 14/16/20; Source Sans 3 18/20 |

All fourteen panels were inspected. Quotation marks have consistent shapes and
retain a clear gap. Colon dots match one another, but Literata 18/20 still has
angular dot shapes. Roboto 14/16 dots are short horizontal shapes; repeated
shape equality alone is not a roundness criterion. User review remains required.
The rest of the v6 specimen is unchanged, including the accepted 4/Z changes.
Literata 14px Z terminal quality remains a deferred defect.

The initial v1 averaging prototype could repeat notches and merge quote shapes;
it is superseded by v2. Checks cover source displacement, source edge order,
exported coordinates, preservation of owned components and identical-component
retention. Four new focused tests cover translation, scope, ownership and bitmap
retention. Together with the earlier focused suites, 32 tests pass.

## Reproduction and remaining work

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/compare_component_symmetry.py
```

Output: `tools/font_probe/out/component-symmetry-v2/index.html`. This page shows
every changed rendered candidate with the v6 result and smooth source reference.

This experiment does not settle O/0/o/8, plus signs, T or exclamation-mark local
symmetry. It also does not change percent placement. Those require different
source-relative relationships; this rule remains isolated pending review.

The user approved all rendered v2 punctuation cases. The next experiment is
[round-component placement](round-component-symmetry.md); percentage follows
plus, T and exclamation mark.
