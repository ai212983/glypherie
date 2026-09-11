# Source-relative stroke balance comparison

Status: isolated diagnostic experiment; none of these changes are adopted.

The question is whether small asymmetries should be preserved as source character
or suppressed at low resolution. The comparison contains a smooth source and
three columns: current rendering, source-relative stroke balance, and strict
bitmap reflection. Current rendering includes the latest lowercase-o phase
experiment where available; that does not imply it has been approved.

## Balanced candidate

`source_relative_balance.fit` operates on a single counter inside a nearly
convex outer contour (at most 1% convex-hull area deficit). Source left/right
boundary discrepancy must be within em/64. These are explicit experimental scope
choices. Concave forms such as A, multiple-loop percentage, and punctuation are
outside this pass.

Seven source cross-sections in each direction locate outer and counter boundaries
using sampled quadratic curves. The fitted left-minus-right stroke thickness
target is the corresponding source difference, rather than zero. Top-minus-bottom
thickness is handled similarly. Corresponding section heights/positions also
receive alignment goals. These soft goals have squared-error weight 16 compared
with weight 1 for retaining each current coordinate.

Current metric/global relationships and previously owned coordinates remain
hard. Outer extrema remain anchored; counter extent remains fixed, while its
placement can change. Source cross-section correspondences are held during the
solve, so this is a linearized relationship model, not an exact analysis of the
final nonlinear curve intersections or discovery of a curved symmetry axis.

## Strict reference

The diagnostic projects current pixels onto horizontal/vertical reflection
orbits around the existing bitmap bounds. Majority wins; ties are filled. It is
explicitly a bitmap-only reference, never exported as a font or applied by the
hinter. Exact reflection may thicken strokes, so it is not automatically better.

## Results and review

The 881-case screen yields 25 comparisons: 15 balanced bitmaps change and ten
remain identical. There are 116 already symmetric cases, 691 outside scope and
49 inherited rejected baselines. Rejections stay out of the visual review.

All fifteen changed panels and the primary Literata 16px o comparison were
inspected. For that o, current and balanced bitmaps are identical: each has two
left/right and two top/bottom mismatched pixels. Strict reflection has zero.
Thus this source-relative model does not remove the reported extra pixel.

Other O/0/o cases show changes to stroke weight and counter positioning. Compare
those changes against the smooth source; symmetry alone is not the acceptance
criterion. The largest measured hard-equation residual is approximately 7e-15px.
Exported coordinates, cardinal-edge order, source displacement and counter count
are checked. Thirty-six focused tests pass, including a source-asymmetric fixture
that remains asymmetric and a nonmutating strict-reference projection.

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/compare_source_balance.py
```

Review: `tools/font_probe/out/source-balance-v2/index.html`. The initial v1 also
matched A; the near-convex boundary scopes v2 to round forms. Approved punctuation
is unchanged. Percentage remains after plus, T and exclamation-mark work.
