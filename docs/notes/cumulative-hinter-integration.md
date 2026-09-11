# Cumulative Python hinter integration

Status: unapproved integration experiment; invalid baseline geometry and stage
conflicts remain open.

## Problem and execution model

The v3 adapter selected whole-glyph outputs from independent solvers. It could
reproduce an older broken glyph exactly while claiming a successful check.
Source Sans 3 16px b exposed this: nearly parallel constraints place a point at
153px instead of approximately 6.88px. The serif and terminal stages do not cause
that excursion; it is present in the reoriented equation solution.

The v4 adapter passes upstream geometry and explicit coordinate ownership into
one joint solve. Point and contour-edge soft goals now refer to that upstream
geometry. Owned coordinates join the metric, stem and continuation constraints
as hard equations. Reflection reuses the same upstream geometry and ownership.
The presence of curves or multiple contours no longer selects an older solver.

Coordinates are conservative ownership units for this prototype. They can hold
more tightly than the underlying relationship requires. A future refinement can
express owned distances or interpolation relationships directly. Incompatible
constraints report a hold with its reason; the validated upstream result remains
visible. Invalid upstream geometry is rejected before later fitting.

## Retained improvement map

| Work | Implementation and ownership | Current disposition |
| --- | --- | --- |
| Reorientation | `shamir_reorientation.prototype` | Upstream solve; numerical failures remain here |
| Parent anchors | `shamir_parent_anchor.experiment` | Replacement anchor coordinates owned by parent stage |
| Serif stems | `vtt_serif_experiment` | Recognized member coordinates owned on both axes |
| Opposing terminals | `opposing_terminals` | Outer/member coordinates owned on both axes |
| Shared shorter paired terminals | `vtt_terminal_links`, `geometric_candidate.finish` | Parent, terminal and interpolated member heights owned |
| Coordinated supports | `shared_stem_hinter.fit` | Recognized outer/inner support points owned on both axes; conflicting proposals held |
| Complete stems and terminal filter | `joint_stroke_fit.stem_relations` | Width and side alignment equations in shared hard system |
| Stem continuations | `joint_stroke_fit.continuation_relations` | Selected existing alignment equations in shared hard system |
| Reflection | `joint_stroke_fit.fit` | Same ownership and metrics; already symmetric bitmap guard retained; experimental |
| Outside-in recovery | `outside_in` | Separate experiment; not incorporated in v4 |
| Repeated ring sizes | `repeated_rings` | Separate experiment; matched sizes need ownership relationships before integration |
| Joint ring placement | `joint_ring_placement` | Separate experiment; provisional visual preference, not whole-corpus approval |
| General component placement | `component_placement` | Reported regressions; not adopted |
| Microsoft compiler execution | Previous VTT galleries | Deferred reference only |

This table records integration status, not blanket visual approval. In particular,
the percent experiments have not become cumulative behavior. Their acceptable
and regressed cases must be reconciled through geometry-based applicability and
owned relationships, rather than selecting saved outputs by character.

## Geometry admission and checks

Before a stage's result can become upstream geometry, verify finite coordinates,
unchanged array shape and a maximum absolute source-coordinate displacement of
2 device pixels. The displacement bound is an explicit conservative diagnostic
policy, not a paper constant or proof of visual quality. It rejects excursions;
it never clips coordinates. Geometry within the bound can still be defective.

Stage claims name the point, axis, value and owning stage. A different value for
an already claimed coordinate is a reported conflict. Shared-support proposals
are assembled before acceptance so a failed proposal leaves earlier ownership
intact. Export checks verify both solved coordinates and owned coordinates.

The full run screens 881 available mappings:

- 766 enter the joint solve successfully.
- 66 retain valid upstream geometry after a constraint conflict or admission hold.
- 49 geometric baselines are rejected, including Source Sans 3 16px b and
  16/18px 5. Rejection exposes these defects; it does not repair them.
- All 4,725 exported ownership claims agree within numerical precision; the
  maximum measured error is approximately 0.000000000000002px.
- 24 focused tests pass across geometric, shared-support, joint and ownership
  code. Tests cover conflicting claims, preservation against soft goals,
  nonfinite geometry and rejection without clipping.

Source Sans 3 16px O and 0 now reach reflection and their resulting panels were
inspected. This does not settle their visual quality or top/bottom symmetry.
The source-match tolerance remains unchanged. Whole-specimen visual approval,
including any changes to previously approved images, remains open.

## Review artifact and next repair

```sh
OPENBLAS_NUM_THREADS=1 tools/font_probe/.venv/bin/python tools/font_probe/compare_cumulative_hinter.py
```

Output is `tools/font_probe/out/cumulative-hinter-v4/`. `index.html` contains the
available specimen and explicit rejected-case entries. `changes.html` includes
changed and rejected cases. Per-case JSON contains owners, constraints, holds,
geometry diagnostics and input hashes. Baseline comparisons are reproduction
evidence, not acceptance criteria.

Repair the ill-conditioned upstream equations first, with b and 5 as regression
cases. Then add ring-size and placement relationships to the ownership system,
audit changed cases against the earlier experiment evidence, and investigate
remaining reflection correspondence failures. Earlier v1-v3 integration outputs
are diagnostic history, not approved baselines.

The next [contour-order and curve-reflection experiment](contour-order-and-curve-reflection.md)
repairs local edge inversions and tests sampled correspondence while retaining
existing exact matches. Its results and remaining symmetry gaps are recorded there.
