# Parent precision in native dependency chains

Reviewed: 2026-09-10
Status: Native parent contract and bounded cardinal graph reference verified

## Decision

Native translation consumes the parent's current 26.6 point coordinates after
its preceding operations. Keep the float mathematical reference separately so
its differences remain visible. A hidden higher-precision parent store would
change dependency evaluation and needs a separately justified experiment.

This decision specifies native parity. It does not establish visual quality,
whole-font fidelity, or exact equivalence between the mathematical reference and
the paper's implementation. The compiler and production renderer are unchanged.

## Sources and interpretation

- [Shamir 2003](../reference/fonts/papers/shamir-2003-constraint-based-hinting.pdf),
  §3.6, requires a dependent side to move after its reference side finishes moving.
  §4.1 translates the ordered constraints into instruction sequences. The paper
  does not specify a hidden high-precision coordinate store or an exact internal
  fractional representation. The mathematical equations alone do not settle it.
- [Microsoft's instruction specification](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions)
  represents point coordinates as F26Dot6. GC[0] reads the current point position;
  GC[1] reads the original position. ALIGNRP uses the reference point. The storage
  area can retain arbitrary 32-bit values, but does not automatically provide an
  extra-precision position for native point instructions.
- VTT's [Interpolate](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L652-L684)
  sets the reference-point pair and emits IP. Its
  [Link](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L582-L618)
  emits MDRP or MIRP using the reference point. These inspected paths support
  ordinary native coordinate propagation; they do not establish the behavior of
  every VTT feature.
- FreeType 2.13.2 [GC](https://github.com/freetype/freetype/blob/VER-2-13-2/src/truetype/ttinterp.c#L4224-L4257)
  reads `cur` for current positions and `org` for original positions.
  [ALIGNRP](https://github.com/freetype/freetype/blob/VER-2-13-2/src/truetype/ttinterp.c#L5510-L5554)
  measures between current child and reference coordinates. This is implementation
  evidence for the tested interpreter, not a run of Microsoft's rasterizer.

Together these sources support current 26.6 parent state as the conservative
native contract. They do not require matching our export-only float evaluation.

## Short-chain verification

The [literal probe](../../tools/font_probe/experiment_parent_precision.py) executes
24 independent synthetic fixtures through FreeType 2.13.2. It uses the fractions
1/3, 2/3 and 1/2 with both signs. IP first places a parent between moved endpoints;
subsequent operations consume it. Expectations use exact rational arithmetic,
without the production compiler or the direct-arithmetic prototype.

The [report](../../tools/font_probe/out/parent-precision-v1/report.json) retains
input/helper hashes, native fonts, assembly and point coordinates. All 24 pass:

- IP → ALIGNRP → ALIGNRP propagates the placed parent coordinate exactly.
- IP → MDRP → MDRP adds original distances to the current parent, including
  negative-direction cases.
- IP → GC[0] → multiplication → child placement amplifies the current parent.
  Original-coordinate reads remain distinct and unchanged.
- A deliberate storage variant retains a Q14 approximation of the ideal parent,
  then uses that value for the amplified child. This is a counterexample showing
  that hidden precision changes behavior, not a proposed baseline implementation.

For the positive 1/3 fixture, the placed parent is 21/64px = 0.328125px:

| Child calculation | Native child position |
| --- | ---: |
| Align to placed parent | 0.328125px |
| Add a 1px original distance | 1.328125px |
| Multiply current parent by 20 | 6.5625px |
| Multiply separately stored Q14 parent by 20, then round | 6.671875px |

The mathematical child `20/3` rounds to 6.671875px at export. Matching that result
requires consuming a different parent representation. The exact-half controls
agree across the two representations; the thirds expose the difference.
These are 1000-unit/em, 1000ppem arithmetic fixtures, not scalable-font proof.

## Consequences for our references

[The float evaluator](../../tools/font_probe/shamir_baseline_solver.py) keeps each
solved point in float precision for subsequent dependencies and quantizes at
export. That is a mathematical-reference policy, not a simulation of native point
state. Preserve it and its results under that description.

The [direct-arithmetic experiment](shamir-native-paired-arithmetic.md) passes all
124 pairs against its runtime inputs, but 94 against the float-parent reference.
Those 30 differences alone do not establish a native translation bug. Keep them
reported as cross-reference differences; actual native arithmetic, equation
selection and visual quality still require their respective checks.

## Resolved cardinal graph verification

The independent [integer reference](../../tools/font_probe/shamir_native_dependency_reference.py)
models positive X/Y constraints on complete resolved point graphs. It supports
Abs, PAbs, Dist, PDist and source-derived Ratio with integer font-unit inputs,
UPM 1000, 1–1000 isotropic ppem, at most 16 points and the compiler's explicit
zone-1 graphics state. Unsupported inputs raise errors. It imports neither the
native compiler nor the float evaluator.

The instruction contract comes from Microsoft; the integer details follow
FreeType 2.13.2 [scaling arithmetic](https://github.com/freetype/freetype/blob/VER-2-13-2/src/base/ftcalc.c#L173-L273),
[MDRP](https://github.com/freetype/freetype/blob/VER-2-13-2/src/truetype/ttinterp.c#L5610-L5725)
and [IP](https://github.com/freetype/freetype/blob/VER-2-13-2/src/truetype/ttinterp.c#L6065-L6210).
These distinctions matter:

- Initial coordinates and CVT values use the interpreter's fixed-point scale.
- MDRP scales the source distance once; subtracting two rounded source positions
  can give a different distance.
- IP derives its ratio from unscaled source geometry in this isotropic domain,
  then interpolates between current 26.6 parents.
- MIAP/MIRP apply the existing cut-in and rounding state. The reference models
  that experimental state; this check does not establish it as a paper default.

The [runner](../../tools/font_probe/experiment_native_dependencies.py) executes
nine graphs at 14, 16, 18, 20, 125 and 1000ppem. Five are existing cardinal
fixtures; four add signed thirds, swapped axes, reversed endpoints and dependent
interpolation/alignment/distance chains. Three oblique fixtures are explicitly
outside this reference's domain.

The [report](../../tools/font_probe/out/native-dependencies-v1/report.json) records
54 complete executions, 54 initial no-op checks and 528 instruction-prefix checks:
all agree exactly, with zero errors on FreeType 2.13.2. It retains graph inputs,
font/assembly artifacts, code hashes, predicted states and observed prefix states,
including the current parents available to each child. Compiler metadata only
locates instruction boundaries; it supplies no expected coordinates.

Twenty-six tests cover the native matrix, domain rejection and independent
arithmetic controls. A delayed-rounding counterexample places a parent at 21/64px
and extrapolates it by 20: native execution gives 420/64px; keeping the ideal 1/3px
parent until export gives 427/64px. A separate pixel-snapped-parent mutant also
fails. These controls distinguish parent policies instead of accepting any
self-consistent oracle. Existing compiler tests also pass.

This verifies cardinal dependency propagation. Oblique projection/movement,
the direct paired solver in a dependency graph, scalable target capture and
range/state guarantees remain open. Verify those boundaries before integrating
the direct solver. The compiler, float reference and production rendering are
unchanged; visual review remains paused.

Reproduce the graph check from the repository root with a fresh directory:

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python \
  tools/font_probe/experiment_native_dependencies.py \
  --output tools/font_probe/out/native-dependencies-next
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python -m unittest discover \
  -s tools/font_probe -p test_native_dependency_reference.py
```

Reproduce from the repository root with a fresh output directory:

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python \
  tools/font_probe/experiment_parent_precision.py \
  --output out/parent-precision-next
```
