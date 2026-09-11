# Shamir shared roles and default completion

Reviewed: 2026-09-09
Status: Decisions retained as researched interpretations; numerical verification complete.
Scope: B06 representative roles, B08 completion and B11 shared-role construction.
The [conformance workflow](shamir-model-conformance.md) owns baseline readiness;
[rule inventory](font-pipeline-rule-inventory.md) owns active-stage coverage.

## Source contract

[Shamir 2003](../reference/fonts/papers/shamir-2003-constraint-based-hinting.pdf),
§3.5, uses a segment representative, usually its first or middle point, with
Dist/align links for other members. §3.6 resolves the representative graph using
dependency order and priorities, then attaches ordinary members. The priorities
are font parameters, character metrics, relative relations, then absolute
relations; equal-priority choices issue warnings. §3.2 supplies Ratio defaults;
Table I maps Ratio to TrueType IP.

Microsoft's [IP and IUP specification](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#interpolate-point-by-the-last-relative-stretch)
distinguishes explicit projected interpolation from contour-based untouched-point
completion. IP preserves a point's original relationship to two references.
IUP selects surrounding touched points by contour order and shifts points outside
their original coordinate interval. Its touch state is axis-specific.

Pinned [VTT Interpolate implementation](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L652-L684)
emits IP after selecting reference points and vectors, with optional rounding.
The preceding `ValidateInterpolee` range check is inside a block comment
(lines 620–650); it supplies no live restriction on extrapolation. VTT consumes
authored references here, rather than specifying an automatic reference-selection
algorithm for our graph.

## Decisions

| Decision | Implementation and rationale | Support boundary |
| --- | --- | --- |
| B06 representative | Keep the first on-curve member in the working baseline, with one dominant relation per segment. This is one of the choices described in §3.5; the separate search remains experimental. | Segment grouping and one-font-unit membership tolerances belong to extraction/preparation review. This decision settles representative selection, not every grouping threshold. |
| B11 shared representative | A member link targeting an existing representative enters the reduced graph and receives ordinary priorities and cycle resolution. Reuse the existing point and published relations rather than creating duplicate points or a second solver. | The paper leaves this overlap case unspecified; this is our conservative role interpretation. |
| B11 ordinary member | Attach members after representative resolution. Preserve selected explicit representative equations. Reject attempts to route shared-representative proposals through the late phase, including proposals that would be discarded. | A late construction error is reported; it does not trigger a new conflict policy. The diagnostic simultaneous assembler remains separate from production scheduling. |
| B11 cycle completion | Remove the lowest-priority cyclic relation with a warning; retain the original unrounded projection for the coordinate it leaves free. This introduces no new reference dependency or rounding. | Priority removal follows §3.6. The original-position fallback is our completion assumption, **not** authorized by the paper's arbitrary tie rule. |
| B08 reduced defaults | With no supplied reference pool, preserve each free original projection without rounding. The active reduced caller supplies no pool. | The generic projected-nearest reference option exists, but does not describe the active reduced path. Creating a new reference-selection graph here would require another assumption. |
| B08 ordinary defaults | Choose the preceding and following representatives on the same contour. Preserve the original projected Ratio, including extrapolation; complete a single existing equation in its perpendicular direction. | Contour order is a topology precedent from IUP; the fitted equation follows Ratio/IP. Representatives are our reference pool, not TrueType touched flags. |
| B08 degenerate references | With one reference or zero projected span, preserve the signed source offset from the preceding reference using unrounded Dist. With no reference on the contour, preserve the original coordinate. | IP cannot supply a valid ratio for coincident projected references. This fallback is our deterministic choice, not a claimed IP degenerate-case implementation. |

These policies reuse the existing constraint vocabulary and dependency procedure.
No source found in this pass specifies the missing automatic reference selection
or shared-role policy more precisely. Their numerical behavior can be verified;
author-implementation equivalence remains unestablished.

## Verification contract

- Synthetic shared corners exercise independent directions, relative/absolute
  priority, cycle removal, late-member ordering and preserved source offsets.
- A shared proposal that bypasses reduced resolution must fail whether late
  assembly would select or discard it.
- Completion cases exercise contour isolation, single/equal references,
  extrapolation, free perpendicular projections and original-position fallback.
- Explicit TrueType IP programs provide an independent operation check for
  cardinal interpolation. FreeType executes those programs; this is neither a
  Microsoft rasterizer test nor a complete VTT compiler comparison.
- The original-source numerical audit covers all 972 calibration cases before
  resuming the remaining baseline decisions. Visual review stays paused.

## Verification results

The focused suite passed 77 tests, including 10 completion/native-IP tests and
16 shared-role/member tests. The added scheduling guard checks rejected as well
as selected proposals. Fitting equations, priorities and completion formulas
remain unchanged.

The [full original-source audit](../../tools/font_probe/out/source-alignment-audit-v2/source-alignment-report.json)
passed all 972 cases across 12 builds with zero failures. Maximum coordinate error
was 0.007812500000070166px, within 1/128px plus floating-point allowance. Input and
output hashes verified. [Graph parity](../../tools/font_probe/out/source-alignment-audit-v2/graph-parity.json)
confirms all reduced/final graphs and their native-coordinate records match v1.
This closes the bounded role/completion verification, while preparation/extraction,
membership tolerances and native translation remain in the conformance queue.

## Research record

The saved 2003 paper §§3.2/3.5/3.6 and Table I, Microsoft's IP/IUP specification,
and pinned VTT source above were reread. Queries included `Ariel Shamir automatic
hinting representative points shared constraints default Ratio 2003 source code`
and `Shamir Rappoport LiveType constraints`. The
[author bibliography](https://pages.cs.huji.ac.il/sites/www-arir/) identifies
related design and typography work; this search recovered no additional
shared-role or default-reference implementation. Earlier source searches and
access gaps remain in the conformance document. Absence from this search is not
proof that no unpublished implementation exists.
