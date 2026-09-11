# Shamir native translation audit

Reviewed: 2026-09-10
Status: Opt-in native sequence experiment; baseline B12 remains an experimental replacement.

The [conformance workflow](shamir-model-conformance.md) owns baseline readiness.
This investigation compares the size-specific equation-to-SCFS adapter with native
TrueType operations before choosing its replacement or retaining a departure.

## Source contract

[Shamir 2003](../reference/fonts/papers/shamir-2003-constraint-based-hinting.pdf),
Table I, calls its mappings *closely corresponding commands*. Section 4.1 translates
each resolved constraint into a small instruction sequence, uses a CVT for font
parameters and preserves dependency order. It does not require one opcode per
relation or specify every graphics-state setting.

| Relation | Table I command | Representable single-operation case |
| --- | --- | --- |
| Abs | MDAP | Round the point's current projection. An arbitrary authored target needs additional instructions. |
| PAbs | MIAP | Position from a CVT entry, subject to the selected state and flags. |
| Dist | MDRP | Preserve the original projected distance. A different authored distance needs additional instructions. |
| PDist | MIRP | Distance from a CVT entry, subject to the selected state and flags. |
| Ratio | IP | Preserve the original projected ratio between references. An arbitrary authored ratio needs additional instructions. |
| PRatio | No mapping | A translation sequence requires an explicit design and verification. |

Microsoft's [instruction specification](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions)
defines these semantics, reference-point updates, projection/freedom vectors,
rounding, CVT cut-in, minimum distance and sign handling. These settings form part
of the translation contract. The pinned [VTT generator](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp)
provides sequence examples in `Link` and `Interpolate`; it consumes selected
points and references rather than deriving our automatic feature graph.

Figure 9 (printed page 144) shows MIRP with flags `0x1D` (`11101`), then ALIGNRP
for the segment's members. Those flags update rp0 to the moved representative,
enable minimum distance and rounding, and select black-distance compensation.
Its omitted initial graphics state prevents recovery of a complete executable
example from that fragment alone.

## Bounded comparison

[Runner](../../tools/font_probe/compare_native_translation.py) and
[tests](../../tools/font_probe/test_native_translation.py) use a synthetic four-point
outline, x/y and oblique projections, and sizes 14/16/20/125. Rounded and unrounded
operations are compared; signed and zero CVT values exercise half-pixel ties.

Each case compares the ideal equation result, the actual SCFS adapter output and
an independently constructed native operation executed by FreeType. References
receive identical declared targets; native execution quantizes those targets
before dependent operations, while the equation solver retains float precision
until export. Native target positions are never copied from the solved result.

The isolated state is RTG, large CVT cut-in, zero single-width cut-in and minimum
distance, with automatic sign flipping disabled. MIRP/MDRP use grey-distance
flags `00100` or `00000`. These choices isolate the relation equation; they are
an explicit test setup rather than recovered Shamir defaults. A separate
MIRP/ALIGNRP check compares Figure 9's flags with the isolated flags to expose
reference propagation.

The output records assemblies, fonts, source/code hashes, interpreter version,
coordinates, exceptions and exact SCFS-export agreement. Exact equality and
one-sixty-fourth-pixel difference are diagnostic categories, not acceptance
thresholds. FreeType executes these instructions; this is not Microsoft rasterizer
output or a VTT autohinter comparison.

## Results

The [114-case report](../../tools/font_probe/out/native-translation-v3/report.json)
records 101 exact matches and 13 differences, each with a maximum coordinate
change of 1/64px. FreeType 2.13.2 reports zero execution errors or SCFS invariant
failures. Nine focused tests pass, including an injected native failure that
verifies a complete failure report and nonzero exit. Artifact and code hashes
were independently checked. The SCFS output agrees exactly with its predicted exported
coordinates. These observations establish a bounded comparison, not instruction
equivalence or a universal error bound.

Two cardinal cases show why final-only quantization differs from native execution:

- Unrounded PDist, x, 16px: the declared reference is 2.6px and the distance is
  1.456px. Solving then quantizing 4.056px gives 4.0625px. Native execution adds
  the separately quantized reference (2.59375px) and CVT distance (1.453125px),
  giving 4.046875px.
- Ratio, y, 16px: the moved upper reference is 4.203125px in native coordinates.
  IP preserves the original one-half ratio, rounding its midpoint to 2.109375px.
  The ideal midpoint of 4.2px is 2.1px, whose final quantization is 2.09375px.

[FreeType's interpreter](https://github.com/freetype/freetype/blob/VER-2-13-2/src/truetype/ttinterp.c)
uses original unscaled projections for the isotropically scaled IP ratio and
fixed-point arithmetic for its moved distance. Oblique cases additionally involve
encoded projection/freedom vectors and incremental movement. Their individual
arithmetic steps remain to be traced; the small observed differences alone do
not settle their cause or acceptability.

The [flag check](../../tools/font_probe/out/native-translation-v3/flag-comparison.json)
shows identical representative positions under the two rounded MIRP variants,
but different follower positions after ALIGNRP: `11101` follows the newly moved
representative; `00100` follows the previous rp0. Reference-state propagation is
therefore part of the required sequence test, even when the first point matches.

## Decision and next boundary

Keep B12 classified as an experimental replacement. The current adapter solves
projected equations and quantizes the final point at one requested size. Native
instructions also quantize intermediate coordinates, distances and vectors and
maintain state across operations. Matching a bounded operation matrix would not
establish complete graph or scalable-program equivalence.

The opt-in [native sequence compiler](../../tools/font_probe/shamir_native_translation.py)
accepts a resolved point graph directly. Calling `compile_native(graph, points)`
returns assembly and a CVT; the production generator continues to use SCFS.
The [comparison runner](../../tools/font_probe/compare_native_sequences.py) exercises
this path independently of the approved bitmap pipeline.

### Native sequence choices

- Preserve the supplied point dependency order and each point's two relations.
  Set reference points explicitly before every relative operation, including
  zero-distance member alignment. This follows the paper's ordered translation;
  Figure 9 supplies the member-alignment example.
- Move along the perpendicular to the other relation's normal. Applying either
  equation then preserves the other projection in exact arithmetic. This is our
  conservative translation of the two-equation model using Microsoft's separate
  projection/freedom semantics. The paper supplies no complete vector-selection
  implementation; fixed-point preservation is measured separately.
- Apply VTT's [AlmostPerpendicular gate](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L347-L356):
  reject projection/freedom pairs with an absolute dot product below 1/16.
  Check ideal and encoded directions. This is an explicit translation support
  limit; it leaves the selected model equations intact. FreeType's interpreter
  also changes its movement calculation below this boundary.
- Use explicit CVT, sign, rounding and reference state. Relative moves update
  rp0 with flags `10100`/`10000`; member alignment sets its own source regardless
  of prior updates. Zero minimum distance and grey-distance compensation continue
  the bounded equation-isolation policy. They remain our experiment settings,
  rather than the full Figure 9 or VTT stroke-colour policy.
- Accept exact signed-16-bit integer font-unit CVT values. Report fractional
  parameters, authored values outside the direct mappings, parameterized ratios,
  and unsupported graph/vector inputs. Reject the whole translation with reasons;
  selecting substitute constraints would change the model.

The emitted program contains no requested-size coordinates. Its constant vectors
require isotropic execution; arbitrary transforms and aspect ratios are outside
this experiment. The finite cut-in policy is also explicit: CVT use can depend on
the native distance at execution time. The bounded fixtures keep that distinction
visible; they do not establish equivalence for every parameter or size.

### Sequence verification

The [sequence report](../../tools/font_probe/out/native-sequences-v3/report.json)
covers eight synthetic graphs at 14/16/18/20/125px, using the same compiled
program across sizes. Literal reference programs are authored separately for
moved anchors, a stem/member chain, coupled and swapped equations, a rotated
frame, interpolation, extrapolation, signed parameters and source rounding.
References use their own CVT entries and never derive instructions from compiler
metadata or solved coordinates.

- All 40 full-outline native/reference comparisons match exactly under strict
  FreeType 2.13.2 execution; there are zero unexpected errors.
- Five cases differ from SCFS, with a maximum coordinate difference of 1/64px.
  This remains a diagnostic, rather than an acceptance tolerance.
- All 160 point/size prefix observations are recorded. The second operation
  changes the first projected coordinate by at most 0.00625px in this matrix.
  The x-first paired case preserves x exactly; rotated projections retain
  small fixed-point residuals. Reversing the paired operation order changes
  output at 14px and 18px despite identical model equations.
- Twenty tests pass across the new sequence and previous operation suites.
  They cover hand-computed results, unsupported mappings and malformed inputs,
  near-perpendicular rejection, a supported oblique pair, input immutability,
  fresh output directories and injected execution failures. Artifact and code
  hashes were independently verified.

This verifies the bounded synthetic compiler experiment. The source-font audit
below tests its current support; arbitrary authored relations and complete
Microsoft rendering-state behavior remain open. The automatic choice of movement
vectors remains a documented interpretation. No production bitmap or baseline
adapter has been replaced, and no new visual specimen is requested.

Investigate missing instruction sequences, parameter quantization and graphics
state against Microsoft/VTT before widening support or replacing baseline B12.

Preparation/extraction and membership tolerances remain separate audit items.
Visual baseline review follows completion of the source-alignment decisions.

## Parameter representation — 2026-09-10

Microsoft stores the [CVT](https://learn.microsoft.com/en-us/typography/opentype/spec/cvt)
as FWORD entries: signed 16-bit integer font units. The interpreter scales these
values to pixel-space fixed point. Its [WCVTF/WCVTP instructions](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#managing-the-control-value-table)
distinguish font-unit values from pixel-unit values; they do not define an
automatic policy for quantizing arbitrary fractional design-space parameters.

Shamir §3.4 gathers frequently occurring feature measurements; §4.1 transfers the
global-size table into the CVT. The paper leaves the general conversion and tie
policy unspecified. Our baseline `shamir_segment_fit.clusters` already rounds
measurements to integer font units before counting them, using Python's nearest,
ties-to-even rule. That is an existing preparation choice, distinct from the
native compiler's refusal to silently round an incoming fractional parameter.
All 3,759 selected parameters in the source-font audit are valid integer CVT
values: 1,776 PAbs and 1,983 PDist. There are no PRatio relations. Fractional
conversion remains an unsupported input, but does not block this corpus.

## Source-font coverage — 2026-09-10

The [coverage runner](../../tools/font_probe/audit_native_font_coverage.py) builds
the baseline directly from original fonts and configuration, then attempts native
translation of every selected graph. It preserves each target's original points,
contours, on-curve flags, advance and bearing through serialization. Accepted
programs execute under strict FreeType; rejected graphs retain their diagnostics.

[Frozen report](../../tools/font_probe/out/native-font-coverage-v2/native-font-coverage-report.json):

| Family, 14/16/18/20px | Executed | Vector rejection | Empty outline |
| --- | ---: | ---: | ---: |
| Roboto | 312 | 8 | 4 |
| Literata | 314 | 6 | 4 |
| Source Sans 3 | 284 | 36 | 4 |
| Total | 910 | 50 | 12 |

All 972 cases are accounted for, with zero unexpected failures. The 50 vector
rejections contain 248 rejected relations; the 12 spaces fail the compiler's
nonempty point-array contract. Thirty-three audit, operation and sequence tests
pass. Input, code, build and native-artifact hashes were independently verified.

Native coordinates match SCFS exactly in 162 executed cases and differ in 748.
The largest difference is 4.359375px in Literata 16px W. These are diagnostic
measurements, not an acceptance tolerance or proof that either output is correct.
The production adapter and approved bitmap pipeline remain unchanged.

### Empty-outline handling — 2026-09-10

Microsoft's [glyf specification](https://learn.microsoft.com/en-us/typography/opentype/spec/glyf#simple-glyph-description)
allows zero-contour glyphs without instructions; spacing is stored separately.
The native compiler now accepts an empty point list or a `(0, 2)` array with an
empty selected graph. It emits no instructions, CVT values or point operations.
Malformed arrays and inconsistent graphs still receive explicit diagnostics.
Phantom-point hinting remains a separate unsupported capability.

The [fresh audit](../../tools/font_probe/out/native-font-coverage-v4/native-font-coverage-report.json)
accepts 922 cases: 910 nonempty programs and 12 verified empty no-ops. Fifty
vector rejections remain; there are zero unexpected failures. All 12 spaces
preserve their stored advance/bearing and their FreeType spacing, and render
blank under strict monochrome settings with embedded bitmaps excluded.

Thirty-eight tests pass, including nonzero-spacing blank fixtures, malformed
empty inputs and the existing native-operation/sequence suite. Comparison with
v2 ([regression evidence](../../tools/font_probe/out/native-font-coverage-v4/regression-verification.json))
verifies that all selected equations and point orders are unchanged, the 910
nonempty programs retain their assembly, CVT, original outlines and native
coordinates, and the 50 vector-rejection diagnostics are identical.

### Decisions and next work

- Retain exact integer CVT validation; this corpus requires no new quantizer.
- Empty graphs have an explicit, verified no-op translation that preserves spacing.
- The [paired-vector investigation](shamir-native-paired-vectors.md) traces all
  50 rejected cases. Unconditional ISECT fallback and the tested fixed-normal
  iteration cannot preserve their equations accurately. Retain the support gate;
  the [direct arithmetic prototype](shamir-native-paired-arithmetic.md) verifies
  all 124 runtime-input pairs. The [parent-precision decision](shamir-native-parent-precision.md)
  establishes current 26.6 coordinates for native dependencies. A separate graph
  reference, scalable target capture and range/state guarantees precede integration.
- Complete translation, graphics-state and preparation decisions before using
  these coordinate differences to evaluate the baseline visually.

Reproduce from the repository root with an empty output directory:

```sh
OPENBLAS_NUM_THREADS=1 PYTHONPATH=tools/font_probe tools/font_probe/.venv/bin/python \
  tools/font_probe/audit_native_font_coverage.py \
  --output tools/font_probe/out/native-font-coverage-v4
```
