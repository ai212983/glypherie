# Direct arithmetic for paired constraints

Reviewed: 2026-09-10
Status: Isolated native prototype and cardinal graph reference verified; paired graph integration pending

## Finding

Direct arithmetic can express the selected equations, but replacing iteration
alone is insufficient. Rounding each projected target to 26.6 before solving
already loses enough information to move some intersections by several pixels.
The prototype preserves precision through target construction and the solve,
then quantizes the final point once.

This investigation uses the 124 frozen pairs from the
[iteration experiment](shamir-native-paired-vectors.md). It changes no compiler,
selected equation, graph priority or production bitmap. Its
[numeric audit](../../tools/font_probe/out/paired-arithmetic-audit-v1/report.json)
is a host sensitivity calculation, not a native execution or visual result.
Muse and an independent calculation agree on the target and normal precision
results. The [reproduction script](../../tools/font_probe/out/paired-arithmetic-audit-v1/reproduce_sensitivity.py)
reads the frozen cases from the repository root; the report records their hashes.

## Source inventory

| Source | What it establishes | Boundary |
| --- | --- | --- |
| [Shamir 2003](../reference/fonts/papers/shamir-2003-constraint-based-hinting.pdf), §3.2 and §4.1 | Directional point relations; resolved dependencies determine instruction order; shared values use CVT. | The paper provides no general direct-arithmetic lowering for shallow equation pairs. |
| [Microsoft instruction specification](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#arithmetic-and-math-instructions) | Signed 32-bit stack values; arithmetic uses 26.6 conventions; DIV truncates; arithmetic lacks overflow protection. | Higher-precision scale bookkeeping must be supplied by our implementation. |
| [VTT Intersect](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L805-L826) | Emits ISECT or size-conditioned alignment. | This is not a general scalar-equation solver; the earlier ISECT limitation remains. |
| [FreeType 2.13.2 arithmetic instructions](https://github.com/freetype/freetype/blob/VER-2-13-2/src/truetype/ttinterp.c#L2700-L2726) and [arithmetic helpers](https://github.com/freetype/freetype/blob/VER-2-13-2/src/base/ftcalc.c#L157-L210) | DIV computes signed truncation of `64*a/b`; MUL uses rounded `a*b/64`. | Interpreter evidence supports testing this runtime, not a Microsoft rasterizer equivalence claim. |

The bounded source search recovered no Shamir implementation or Microsoft
routine for this exact translation. A direct solve would be our implementation
of an unspecified translation detail, justified by algebraic equivalence to the
selected equations. It would not be a recovered paper implementation.

## Separate the sources of error

Let `A` contain the two selected normal rows and `b` the frozen targets. The
reference is `p = inverse(A) * b`. Each row below changes only the stated input;
the remaining solve uses float64 arithmetic.

| Input change | Within 1/64px of original solution | Maximum coordinate error |
| --- | ---: | ---: |
| Targets rounded to 26.6; original normals | 20/124 | 4.194283px |
| Targets rounded to 26.6; captured GPV normals | 17/124 | 4.742188px |
| Normal components rounded to 14 fractional bits; original targets | 77/124 | 0.270411px |
| Normal components rounded to 20 fractional bits; original targets | 124/124 | 0.009745px |
| Normal components rounded to 24 fractional bits; original targets | 124/124 | 0.000458px |

The 1/64px criterion remains diagnostic. These counts exclude native arithmetic,
parent-coordinate quantization and final output quantization. Higher coefficient
precision alone therefore does not establish an acceptable native translation.
Raw rounded normal components also differ from vectors normalized by FreeType.

For exact `A`, target error obeys
`||delta p||inf <= ||inverse(A)||inf * ||delta b||inf`.
Allowing independent half-LSB target errors of 1/128px yields conservative bounds
from 0.2023 to 7.4688px across these pairs. These bounds are not predictions of
actual error. Exact targets or correlated errors can justify tighter bounds;
failing this loose bound alone does not prove that a pair is inaccurate.

## Candidate arithmetic construction

The normals are compile-time geometry constants. Their inverse can therefore be
computed at compilation without knowing ppem or the eventual point positions.
That avoids calculating a tiny determinant with low-precision runtime arithmetic.
The runtime still evaluates the selected targets from the completed dependencies.

A separate host check rounds inverse-matrix entries, rather than the normals, to
14 fractional bits. With original targets, all 124 pairs stay within 0.000413px of
the original solution. This is coefficient sensitivity evidence only. It supports
investigating precomputed coefficients; it does not select an accumulator format.

For a distance relation, preserve the expression
`b_i = dot(n_i, parent_i) + rounded_distance_i` through the solve. Expand
`inverse(A) * b` into weighted parent coordinates and distance terms, combining
terms that share a parent before evaluation. This algebraic rearrangement can
avoid rounding a projected parent position to 26.6 prematurely. It preserves the
selected distance rounding; it introduces no new grid-fitting rule.

Use Cartesian runtime coordinates for the parent terms and apply the resulting
Cartesian position with cardinal SCFS operations. Capture all inputs before moving
the child. Preserve the resolved dependency order and explicitly establish the
projection/freedom, zone, touched-point and reference-point state.

This construction is a proposed implementation choice. Its treatment of original
coordinates, scaled shared values, signed rounding and current parent coordinates
must be checked against each relation's semantics before a compiler change.

## Range and failure contract

The largest absolute inverse coefficient in this corpus is about 478.001.
Encoding it with 14 fractional bits requires an integer about 7.83 million, which
fits the stack but exceeds a PUSHW immediate. Existing integer materialization
can supply it. This coefficient bound says nothing about product or sum safety.

Every intermediate needs an explicit scale and range: coefficients, weighted
coordinates, sums before cancellation, rescaling and final 26.6 positions.
MUL and DIV apply their specified scale factors even when stack integers encode a
custom format. Large cancelling terms can overflow although their final sum is
small. Verify bounds before each unsafe operation; retain a structured diagnostic
when a bound or accuracy requirement cannot be established.

A scalable program needs bounds over its supported execution domain, or runtime
checks before unsafe arithmetic. Bounds observed only at 14–20px cannot authorize
other sizes. Singular systems, unsupported relations, missing dependencies and
invalid input values remain explicit failures. The present projection/freedom
support gate stays unchanged; a future arithmetic path needs its own justified
support contract rather than silently bypassing that gate.

## Native prototype and decision

The [isolated prototype](../../tools/font_probe/experiment_paired_direct_arithmetic.py)
expands each pair into parent-coordinate and scalar terms, combines shared-parent
coefficients, and encodes coefficients with 14 fractional bits. Native instructions
capture parent coordinates through cardinal GC and perform signed distance rounding.
The scalar inputs and initial parent positions are requested-size fixture setup;
scalable original-coordinate/CVT capture remains outside this experiment.

Products of a coefficient and a 26.6 input accumulate with 14 fractional bits.
Unrounded scalars retain a fractional remainder: its product first has 22 fractional
bits, then is rescaled before accumulation. The final coordinates are rounded once
to 26.6 and applied with cardinal SCFS. The signed rounding follows the selected
model equations; the construction is our documented translation choice.

The [native report](../../tools/font_probe/out/paired-direct-arithmetic-v2/report.json)
separates the original float-parent solution from the solution using the fixture's
26.6 parents and encoded scalar inputs. Both residual and coordinate error must
meet the diagnostic 1/64px threshold.

| Reference for native output | Passing pairs | Maximum coordinate error |
| --- | ---: | ---: |
| Runtime inputs | 124/124 | 0.008185px |
| Original float parents and scalars | 94/124 | 0.351672px |

The [independent verification](../../tools/font_probe/out/paired-direct-arithmetic-v2/independent-verification.json)
reproduces both native pre-final accumulators and final 26.6 coordinates for all
124 pairs exactly. Eighty-one focused checks pass, including signed rounding,
intermediate overflow, missing-input rejection and actual native arithmetic.
Seven synthetic fixtures execute; two deliberately reject singular or overflowing
systems. The corpus has zero rejected cases or unexpected execution failures. The maximum incremental coefficient error is
0.000429px, arithmetic error 0.000081px, and final-rounding error 0.0078125px.
These stage maxima are separate measurements, not an additive worst-case proof.
Parent quantization alone moves the solution by up to 0.351725px; 95 pairs remain
within tolerance before later encoding and output rounding. The corpus has no
changed pixel-rounding decisions for the scalar distances.

Range checks apply to the exact fixture inputs and every emitted intermediate,
including large terms before cancellation and signed rounding additions. This
establishes bounded-fixture safety, not a scalable runtime range guarantee.

Retain the compiler's existing support gate. The arithmetic approach warrants
further investigation, but the 30 original-reference failures remain visible.
The [parent-precision investigation](shamir-native-parent-precision.md) establishes
current 26.6 point coordinates as the native dependency contract. The float-parent
comparison remains a distinct mathematical reference; its differences alone do
not prove native mistranslation. The separate cardinal graph reference now passes
54 complete executions and 528 instruction-prefix checks. Verify oblique movement
and the direct solver in dependent graphs before
integration. Native target capture, graphics state and execution-domain range
checks remain open. Visual review follows source-alignment decisions.

Reproduce from the repository root with a fresh output directory:

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python \
  tools/font_probe/experiment_paired_direct_arithmetic.py \
  --output out/paired-direct-arithmetic-next
```
