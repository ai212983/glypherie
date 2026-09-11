# Round-component placement experiment

Status: isolated Python candidate; round-glyph symmetry remains incomplete.

The work order is round glyphs, plus, T and exclamation mark, then percentage.
Percentage placement is explicitly deferred. The approved repeated punctuation
candidate is loaded ahead of the v6 specimen and preserved.

## Method

`round_component_fit` recognizes isolated counter-bearing source components and
checks their sampled filled outlines against horizontal/vertical reflection.
A source-boundary Hausdorff limit of em/64 selects axes worth testing; this is an
experimental raster-scoring applicability bound, not permission to reflect the
source coordinates. The source curves and their relative internal structure
remain intact under a positive axis-aligned affine transform.

Scale and position are solved against current metric/global relationships and
coordinate owners. Candidate dimensions must match the current component within
1/64px. Twenty-five quarter-pixel placement targets are tested. Ranking prefers
less raster reflection mismatch, then 8x supersampled coverage fidelity with a
small displacement penalty. A candidate is retained only when its symmetry score
improves. Already symmetric components keep the exact previous output.

The first scale/position solve could improve Source Sans 3 16px zero's symmetry
by making it narrower and more rectangular. The dimension check excludes that
tradeoff. Metric constraints still prevent most proposed source-curve placements;
these are recorded as holds, not successful symmetry corrections.

## Review and limits

`tools/font_probe/out/round-symmetry-v4/index.html` contains changed rendered
candidates only. Automated exclusions are in `diagnostics.html` and the report.
The useful candidate is Literata 16px lowercase o. Its opposite sides are more
consistent, but weight and roundness require visual review.

O/0/o/8 symmetry is not generally solved by affine placement. Relaxing metric
relationships merely to obtain symmetry is not part of this experiment. Plus,
T and exclamation-mark relationships remain next, and percentage stays last.
No previously accepted punctuation or percentage bitmap is changed.

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/compare_round_symmetry.py
```

The [source-relative stroke balance comparison](source-relative-stroke-balance.md)
contrasts preserving source asymmetry with strict bitmap reflection. The reported
Literata 16px o pixel remains in the balanced candidate; the comparison makes
that limitation explicit.
