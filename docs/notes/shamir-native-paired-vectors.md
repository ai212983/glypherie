# Native translation of paired constraints

Reviewed: 2026-09-10
Status: Bounded iteration evaluated; explicit vector rejection retained

## Finding

The current compiler cannot translate 50 source-font cases using its chosen
movement vectors. The selected equations remain intact. The problem is a pair
of almost-parallel equations: moving along one while preserving the other
requires a large displacement for a small change in the measured coordinate.

The [read-only trace](../../tools/font_probe/out/paired-vector-investigation-v1/report.json)
groups the 248 rejected relations from native coverage v2 into 124 point pairs.
It retains both selected constraints, point IDs, source-build hashes, angles and
condition numbers. This is an investigation of the existing graphs, not a new
feature detector or constraint-selection policy.

| Selected relation pair | Point pairs |
| --- | ---: |
| Abs / Dist | 40 |
| Dist / PDist | 28 |
| Dist / Dist | 52 |
| Abs / Abs | 4 |

The acute angles between normals range from 0.120° to 3.320°. The corresponding
two-equation matrices have condition numbers from 34.5 to 956.0. Of these pairs,
120 include a segment-alignment relation; none include default-completion
constraints. Examples include Roboto M shared representatives, apostrophe segment
members, and Literata P. Their identities label evidence only.

## What the sources establish

- [Shamir 2003](../reference/fonts/papers/shamir-2003-constraint-based-hinting.pdf),
  §3.2, defines directional Abs, Dist and Ratio equations. §3.5 links segment
  members to a representative; §4.1 translates the resolved equations into
  ordered instruction sequences. It does not supply a general automatic
  projection/freedom-vector algorithm for nearly parallel equation pairs.
  The web search recovered no author implementation resolving this detail.
- [Microsoft's instruction specification](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions)
  separates the measured direction (projection) from the movement direction
  (freedom). Our choice of freedom perpendicular to the other equation's normal
  preserves that equation in exact arithmetic. This choice is our interpretation.
- VTT's [AlmostPerpendicular](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L347-L356)
  rejects vector overrides with absolute projection/freedom dot product below
  1/16. This supports retaining our translation guard. It does not establish
  that the selected equations or the glyph are invalid.

For unit normals `a` and `b`, our movement choice has
`abs(dot(a, perpendicular(b))) = abs(det(a, b))`. Reversing the two operations
therefore leaves the small denominator unchanged. Increasing priority, swapping
order, or silently replacing a normal does not supply an equation-preserving
translation. This is a mathematical deduction from the current construction.

## Why ISECT is not a general substitute

Microsoft documents ISECT as intersection of two lines, with an average fallback
for parallel lines. VTT's [Intersect implementation](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L805-L826)
emits that instruction when no size limits are supplied. Neither source maps
arbitrary selected scalar equations into the four required line endpoints.

The actual [FreeType 2.13.2 interpreter](https://github.com/freetype/freetype/blob/VER-2-13-2/src/truetype/ttinterp.c#L5598-L5644)
uses the average when `abs(tan(angle)) <= 1/19`, roughly 3°. Under ideal line
directions, 122 of our 124 rejected pairs fall inside that region. Native endpoint
quantization would need its own check; this count is not a font execution result.

Three independently specified line fixtures verify the behavior in our runtime.
At 1000ppem with 1000 units/em, line A is `(0,0)–(200,0)`, and line B is
`(0,10)–(200,10+rise)`. The fifth point is the ISECT target. Fonts and results are
saved with the trace.

| Rise | Angle | True intersection | FreeType result |
| --- | ---: | --- | --- |
| 2 | 0.573° | (-1000, 0) | (100, 5.5), average |
| 10 | 2.862° | (-200, 0) | (100, 7.5), average |
| 20 | 5.711° | (-100, 0) | (-100, 0), intersection |

Using the average would abandon both selected equations in these examples.
ISECT therefore cannot serve as an unconditional fallback.

## Bounded native iteration experiment

[Stamm, Hitchcock and Duggan, Microsoft: Iteratively solving constraints in a
font-hinting language](https://patents.google.com/patent/US7187382B2) describes
alternating simpler native operations to approximate coupled constraints. Its
worked procedure stops on small position changes or an iteration limit, and
explicitly allows stopping before an accurate solution is reached. It is a
related technical source, not Shamir's missing implementation or evidence of
convergence for our selected pairs.

The [experiment](../../tools/font_probe/experiment_paired_native_iteration.py)
freezes each equation's target and parent positions once. It starts at the original
prepared outline point, quantized to 26.6, and performs 512 full rounds in the
selected order. Each native operation sets projection and freedom to its own
normal, then uses SCFS to reach the frozen projected target. The independent float
reference applies `p += n * (target - dot(n, p)) / dot(n, n)`.

This fixed-normal mapping is our interpretation of the publication's iterative
procedure. The 1000-unit/em, 1000ppem fixture isolates requested-size equations;
it does not implement target capture or dependency execution for a scalable font.
Cramer's rule supplies the independent solution for measurement only. Native
instructions never receive that solution.

The [report](../../tools/font_probe/out/paired-native-iteration-v2/report.json)
contains all 124 corpus pairs and eight synthetic controls, input/code hashes,
fonts, assembly and every full-round native position. GPV captures the actual
FreeType-normalized vectors. A second oracle uses those vectors and the once
quantized targets to separate input encoding from iteration error.

A diagnostic pass requires both maximum equation residual and coordinate error
within 1/64px. This is an experimental threshold, not a source-defined conformance
tolerance. All 132 fixtures execute successfully; numerical inaccuracy is a
measured outcome, distinct from an execution failure.

| Corpus measurement | Round 10 | Round 512 |
| --- | ---: | ---: |
| Float reference accurate against original equations | 16/124 | 16/124 |
| Native accurate against original equations | 14/124 | 14/124 |
| Native accurate against encoded equations | 1/124 | 1/124 |

Of 124 native pairs, 95 reach an unchanged full-round position. Of those, 81
remain inaccurate against the original equations; 76 already reach this false
stopping condition by round 10. The corpus has no period-two tail cycles. Maximum
final coordinate error is 146.266px against the original intersection and
148.066px against the encoded intersection. These are isolated equation-solution
errors, not rendered glyph measurements. Original and encoded accuracy can differ
substantially because shallow intersections amplify input quantization.

In exact arithmetic, after the first round the remaining error contracts by
`cos(angle)^2` per round. Across this corpus that factor is 0.996647–0.999996:
a hundredfold reduction takes approximately 1,400–1,052,000 rounds. This is a
mathematical deduction for the fixed-normal adaptation. Small movement is therefore
an unreliable proxy for accuracy even before native quantization.

The [independent verification](../../tools/font_probe/out/paired-native-iteration-v2/independent-verification.json)
records 19 passing focused tests and reproduces all 124 frozen targets, starts, analytic
solutions and float checkpoints. A separately assembled native probe reproduces
all 512 positions and GPV values for three corpus pairs, including the largest
final-error case. Independent synthetic controls targeting `(2, 3)` produce:

| Angle | Final native position | First unchanged round |
| --- | --- | ---: |
| 90° | (2, 3) | 2 |
| 45° | (2, 2.984375) | 10 |
| 1° | (2.046875, 0) | 2 |
| 0.12° | (2, 0) | 2 |

## Decision and next boundary

Retain explicit rejection for these 50 glyph-size cases. Bounded alternating
projection is unsuitable as their general translation fallback. This result
applies to our fixed-normal adaptation, not every algorithm in Microsoft's
publication. Increasing the iteration cap alone does not resolve fixed-point
stagnation.

The [direct arithmetic investigation](shamir-native-paired-arithmetic.md) finds
that early target quantization remains inaccurate even with an exact solve.
Its isolated native prototype verifies the arithmetic for all 124 pairs using
runtime inputs; 94 also meet the original float-parent reference tolerance.
The [parent-precision decision](shamir-native-parent-precision.md) establishes
current 26.6 state for native dependencies; a separate graph reference precedes
integration. The arithmetic is our implementation of an unspecified translation detail.

The compiler, graph priorities, selected equations and production renderer remain
unchanged. Graphics-state and remaining source-alignment decisions precede visual
comparison.

Reproduce from the repository root, choosing a fresh output directory:

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python \
  tools/font_probe/experiment_paired_native_iteration.py \
  --output out/paired-native-iteration-next
```
