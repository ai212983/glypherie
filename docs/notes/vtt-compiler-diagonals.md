# Microsoft VTT compiler diagonal experiment

Investigation: 2026-09-08. Status: inherited stem-width comparison visually approved; broader VTT mapping remains experimental.

## Execution boundary

`compare_vtt_compiler.py` compiles generated VTT Talk with Microsoft's native
compiler at commit `1bd4ed4383f8390b0140e05d330491fcadd3e8e0`, then executes the
resulting TrueType instructions with FreeType in strict monochrome mode. The
[upstream templates and license](../../tools/font_probe/vtt_reference/README.md)
provide the font program, pre-program and initial control values.

This replaces our earlier cardinal-direction approximation with actual VTT
instruction generation and runtime behavior. It is a paired-diagonal experiment;
complete font-wide hint authoring, height calibration and automatic junction
recognition remain outside its scope. Existing Shamir and uniform pipelines keep
their existing behavior.

## Supported source path

The legacy `Diagonal` command calls function 20 through
[DMIRP](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTEngine.cpp#L693).
That definition is absent from the public templates, the repository's Selawik
sample, and the template/demo in the official
[VTT 6.35 Windows package](https://www.microsoft.com/en-us/download/details.aspx?id=103335).
Strict FreeType execution failed with an invalid reference. Non-strict execution
can conceal that failure, so it is unsuitable as evidence.

The experiment instead uses supported `ResXDLink` / `ResYDLink`, routed through
[ResDDLink](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L756)
and [ResDDMIRP](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTEngine.cpp#L1162).
These execute upstream functions 118–120:

- 118 constructs a projection that realizes the requested perpendicular width,
  using twilight points and its own no-solution branch.
- 119 checks the projection/freedom dot product against 1/16; for the near-parallel
  case it touches the child without unstable projected movement.
- 120 coordinates the two ends using the supplied x/y freedom vectors.

The upstream compiler also validates vector compatibility. These commands do
**not** invoke `CalcDiagonalFVMT` or reproduce the legacy `Diagonal` command's
previous-stroke selection algorithm. `Align` and `Smooth` run through the real
compiler, including its state handling and native interpolation.

## Our automatic mapping: assumptions to evaluate

`vtt_mapping.py` receives coordinates, point flags and geometric constraint
records. Its interface has no character, glyph name, family or size argument.

| Choice | Current experiment policy | Evaluation needed |
| --- | --- | --- |
| Paired sides | Slant features and their alignment members; farthest on-curve endpoints per side | Confirm detector's side membership and endpoint coverage |
| Parent endpoints | Opposite corners, so VTT's crossed projection lines follow the two sides | Compare alternative anchoring where supports share junctions |
| Width CVTs | Perpendicular source width for each end, nearest integer font unit | Font-wide width classes and optical calibration |
| Movement axis | X for the more vertical stroke, Y for the more horizontal stroke | Authored junction vectors and supported line-vector commands |
| Ordering | Longest support first, feature index breaks ties | Dependencies and overlapping/shared supports |
| Anchors | Existing explicit cardinal anchor points, plus both axes of each chosen parent; local grid rounding | Global heights, original constraint values and prior movement preservation |
| Interior points | Exact source-collinear on-curve members use `Align`; remaining points use `Smooth` | Curves, junction membership and inherited motion |

Parent anchors are emitted once per axis/point. A later operation can move an
already anchored point. The mapping does not solve a global constraint system or
promise to preserve all earlier widths. These are visible mapping choices, not
claims about Microsoft's automatic hint authoring.

The review font clears existing glyph programs and uses fresh VTT control tables.
Only the exemplar receives this generated program. Unrelated original hint
programs are not mixed with incompatible CVTs. Source outline coordinates,
contour ends and point flags must remain exactly equal.

## Results and validation

The input is all 38 cases flagged by the
[conditioning audit](literata-k-constraint-instability.md), from a screen of 881
exported cases. Twenty-two compile and pass strict native execution:

- Literata `k`: 16, 18px.
- Roboto `M`: 14, 16, 18, 20px.
- Source Sans 3 `N`, `V`, `W`, `w`: 14, 16, 18, 20px.

The other 16 lack mapped paired slants: Literata `P`, Roboto apostrophe, and Source
Sans 3 `b`/`h`, each at 14/16/18/20px. They remain explicit held cases. This set is
coverage of the prior conditioning flags, not all glyphs potentially affected by
VTT hinting.

Literata 16px `k` maximum source-to-fitted displacement is 1.088px; at 18px it is
0.686px. The long extrusion is absent. These diagnostics establish bounded
movement in these examples, not visual acceptance or complete outline fidelity.

Checks cover endpoint/crossed-link ordering, perpendicular CVT units, translation
invariance, missing endpoint rejection, source outline preservation, repeatable
compiled glyph bytes, and strict runtime execution of a synthetic paired stroke
at four sizes. Each compiled real exemplar also checks finite native coordinates,
unchanged source outlines and bytecode reproducibility. Input/template hashes are
recorded. FreeType execution is host proof, not Microsoft rasterizer or board proof.

## Reproduce and review

Install the pinned compiler as described in the template README. With the frozen
representative models and conditioning report available, and an empty output:

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/compare_vtt_compiler.py
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python -m unittest discover -s tools/font_probe -p test_vtt_mapping.py
```

Open `tools/font_probe/out/vtt-compiler-v1/index.html`. Each exemplar includes a
smooth source reference, current uniform output, frozen Shamir output and VTT
execution, with the prior cardinal experiment included where available, generated
commands and compiled assembly. Roboto 14px M retains a plausible outline; Source
Sans 3 20px W has visibly uneven lower tips in VTT execution, so this mapping is
not ready for promotion. Review stroke widths,
junction shape, symmetry and serif preservation before extending the mapping.

## Shared-point dependency comparison

`compare_vtt_dependencies.py` screens all 881 exported uniform-v3 cases using the
same frozen representative outlines. Output is
`tools/font_probe/out/vtt-dependencies-v1/index.html`, with source/before/after
images for every changed program, including identical raster results.

The optional `shared_dependencies=True` mapping mode models each paired link and
its immediate interior alignments as one operation. It reads both coordinates of
its endpoints, writes the selected axis of its children, and conservatively
claims both axes of interior points moved by `Align`. A producer precedes any
other operation reading its written coordinate. Independent ready operations
retain their prior relative order. Parent anchors initialize before all links,
so later initialization cannot reset an already consumed position.

Competing writers and dependency cycles hold the whole glyph's proposed update,
with explicit point-axis ownership and dependency records. Existing output is
retained; constraints are not silently dropped. This policy resolves acyclic
single-writer dependencies only. General conflict resolution remains open.

Results: 656 cases have no paired-slant mapping, 123 programs are unchanged, 48
changed programs produce identical bitmaps, 7 bitmaps change, and 47 proposals
are held for ownership/dependency conflicts. All 55 before/after program pairs
compile and execute with strict FreeType checks and unchanged source outlines.
Changed images are Literata 20px `k`, Roboto 16/18/20px `M`, and Source Sans 3
16/18/20px `y`. The previous compiler gallery remains frozen.

**The Roboto M holes persist at both 16px and 18px.** Stepwise execution of the
previous program showed the left-stem operation introducing the white pixel while
moving a diagonal's previously used parent. Reordering removes that stale-parent
sequence but does not remove the hole. Therefore the earlier causal explanation
was incomplete: sequencing is a real defect, but correcting it is insufficient.
The geometric and pixel-phase behavior of the fitted junction still needs study.
This comparison is not a repair claim or a promoted candidate.

The report counts enclosed white pixels using four-neighbor background
connectivity. This is a diagnostic, not an acceptance rule: intended counters
also count. Scheduler tests cover producer ordering, independent axes, competing
writers and cycles; mapping/compiler tests remain applicable.

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/compare_vtt_dependencies.py
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python -m unittest discover -s tools/font_probe -p 'test_vtt*.py'
```

## Inherited stem width experiment

The optional `stem_widths=True` mapping mode includes detected straight stems as
width references for adjoining slanted sections. It changes width assignment only;
it adds no separate straight-stem movement commands. Shared-point scheduling and
all existing anchors remain fixed to isolate this variable.

`vtt_stem_widths.py` matches a section to a detected stem when they share one side
group, the opposite side groups share an outline point, their normals differ by
at most 5 degrees, and the section width is within 20% of the stem width. These
are explicit experimental limits, not recovered Microsoft authoring rules or a
proof that an intentional taper is absent. Matching sections use one CVT entry
for both ends, derived from the detected stem width. Conflicting candidate widths
are reported and retain the section's independent widths. No font identity, size
or character participates in matching.

For Roboto M, the source already contains a 192-unit straight-stem feature. The
previous slant-only mapping assigned the adjacent section separate 192/164-unit
CVTs. At 16/18px those round to different pixel widths. The resulting open notch
crosses a pixel center and appears as an enclosed white pixel. Dependency ordering
alone cannot correct that width/phase mismatch. Inheriting the detected 192-unit
stem width removes the hole at both sizes.

Reproduce with an empty `tools/font_probe/out/vtt-stem-widths-v1/` directory:

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/compare_vtt_dependencies.py --stem-widths
```

All 881 exported cases are screened: 656 unmapped, 170 unchanged programs, 47 held
for existing dependency conflicts, and 8 compiled before/after pairs. Only Roboto
16/18px M bitmaps change; both lose their enclosed white pixel. Roboto 14/20px M
and Source Sans 3 14/16/18/20px N have identical before/after bitmaps. Every changed
program is shown alongside its smooth source reference. Strict execution and
source-outline preservation pass for all eight pairs; 19 focused VTT tests pass.
The matching tests cover connectivity, direction/width limits, inherited widths
and ambiguous references.

User image approval: 2026-09-08, for the `vtt-stem-widths-v1` comparison. Retain
this inherited-width configuration as the accepted reference for subsequent VTT
mapping experiments. Approval covers the reviewed comparison, including the
Roboto 16/18px M hole correction. The 47 dependency conflicts and broader mapping
coverage remain open; production and Rust integration are separate work.
