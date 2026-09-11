# Literata 16px k: constraint instability

Investigation: 2026-09-08. Production rendering unchanged.

## Confirmed mechanism

The lower diagonal is already extruded in baseline v1. The defect persists in
v6, representative comparison and uniform-v3. In the frozen representative model,
point 6 has a rounded width relation to point 23 and an unrounded alignment to
point 4. The normals differ by 3.1524 degrees modulo sign; determinant magnitude
is 0.05499245 and the two-equation condition number is 36.3411.

| Controlled calculation | Point 6, pixels |
| --- | --- |
| Original constraints and anchors | (6.368, 1.040) |
| Round width only, original anchors | (12.0713, -5.0612) |
| Move anchors only, original width | (10.5612, -3.9882) |
| Both, as implemented | (16.2645, -10.0894) |

The width rounds from 1.45928753px to 1px. Point 5 follows through interpolation,
extending the curve. The native output agrees within 26.6 quantization. This is
an unstable geometric construction, not floating-point inaccuracy.

The width belongs to `width-1` / segment 2; point 6 is also a member of segment 0.
`shamir_shared_roles.py` promotes that membership alignment into the representative
graph under B11. Both selected relative equations survive because they are
mathematically independent. B10 explicitly removed a former condition-number
cutoff in favor of mathematical independence; the conformance document already
records large Source Sans 3 V excursions. Accordingly, this is also an unresolved
model-quality issue that was knowingly left for visual review, then inadequately
tracked through later experiments. Native/model agreement never established
acceptable glyph geometry.

## Shamir 2003

[Paper](../reference/fonts/papers/shamir-2003-constraint-based-hinting.pdf),
§§3.2, 3.5–3.6: directional constraints, representative/dominant segment relations,
late member attachment and priority/cycle resolution support the broad structure.
The inspected sections give no quantitative near-parallel rejection threshold or
replacement policy for this shared representative/member situation. B10 and B11
remain explicit implementation choices. A stable movement policy must be recorded
as such rather than asserted to be recovered Shamir behavior.

## Microsoft source

Inspected VisualTrueType commit `1bd4ed4383f8390b0140e05d330491fcadd3e8e0`.

- [AlmostPerpendicular](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L355)
  rejects checked vector overrides when the absolute projection/freedom dot
  product is below 1/16. Keeping the alignment while enforcing our width would
  move along the alignment tangent. Its equivalent dot product is 0.05499245,
  below that boundary. This is an equivalent-geometry comparison, not a claim
  that every automatic VTT diagonal path invokes that guard.
- [CalcDiagonalFVMT](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L2224)
  selects movement direction using prior strokes/alignments, neighboring geometry,
  touched axes and smoothing state. It even discusses an Arial K junction as an
  example. That example is explanatory; the conditions operate on geometry/state.
- [Diagonal generation](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L1265)
  uses paired stroke endpoints, dual projection and staged links. It does not
  simply intersect two fixed source-normal equations for every child point.
- [ISECT specification](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#moves-point-p-to-the-intersection-of-two-lines)
  defines a fallback for parallel lines. It does not supply a documented
  near-parallel replacement for our construction.

## Recommended correction investigation

First expose unstable constructions as explicit failures with the implicated
relations; this detects the problem rather than repairing it. Then construct a
bounded comparison of VTT's movement-direction policy for the actual stroke and
junction, carrying its state and paired-endpoint semantics. A stable direction
may require relaxing the competing alignment, which must be reported explicitly.
Porting only the 1/16 guard or always choosing x/y would not reproduce VTT.

Validate source geometry, rounded feature widths and movement sensitivity as well
as native/model equality. Screen the full corpus before claiming repair: a
source-to-fitted point-displacement screen above 4px found 34 of 881 uniform-v3
cases, but their individual causes remain unclassified. That screen is diagnostic,
not a proposed four-pixel clipping or acceptance rule.

## Conditioning and explicit cardinal experiment

`compare_diagonal_instability.py` scans the 881 uniform-v3 exported cases against
their frozen representative graphs. Output is
`tools/font_probe/out/diagonal-instability-v1/`, including all candidate images,
held-case reasons, per-point released/replacement equations and input hashes.

`diagonal_instability.py` reports normalized determinant magnitudes below 1/16.
This is the projection/freedom dot magnitude for enforcing one relation while
moving tangentially to the other. There are 38 flagged cases; 24 are held and 14
receive an isolated override experiment. These statuses are diagnostic outputs;
the existing baseline and uniform generators are unchanged.

The VTT previous-alignment branch would preserve the problematic movement line.
The experiment therefore does **not** claim to port that branch or all of VTT.
It explicitly chooses x/y movement along the larger width-normal component,
releases the competing unrounded segment alignment, and preserves the original
parent-to-child offset on the other axis. Both relations depend on the same
width parent, which is processed first. The width equation and its rounding remain
unchanged; downstream constraints are reevaluated in dependency order. Restrict
this experiment to one width plus one unrounded alignment; hold all other unsafe
combinations. There is no identity-based rule or displacement clipping.

The paired-endpoint, CVT and full touched-state logic of VTT Diagonal remains
unimplemented here. This is a bounded causal comparison of an explicit cardinal
movement policy, not a faithful whole-command replacement. Later uniform
corrections are omitted to isolate the frozen-model change. The gallery separately
shows the actual current uniform candidate for context.

Results: Literata k at 16/18px and Source Sans 3 V/W/w at 14/16/18/20px receive the
experiment. Literata 16px k maximum point movement falls from 14.893px to 1.634px;
the long extrusion disappears. Source Sans 3 18/20px V movements fall from roughly
55px to less than 0.8px. These are geometric diagnostics pending human review.
Four unit tests cover safe/unsafe directions, unsupported combinations and width/
parent-offset preservation. Frozen-model reproduction is checked before each
experimental evaluation. Rendered coordinates use the common monochrome rasterizer;
no new TrueType instruction program is claimed or promoted.

Reproduce with an empty output directory:

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/compare_diagonal_instability.py
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python -m unittest discover -s tools/font_probe -p test_diagonal_instability.py
```

The follow-up [native VTT compiler experiment](vtt-compiler-diagonals.md) executes
supported paired-diagonal commands and documents the remaining mapping choices.
