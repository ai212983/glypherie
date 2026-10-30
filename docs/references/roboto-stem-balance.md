# Roboto stem balance: m/u versus n at 14px under main-page policy

<!-- cspell:words unhinted SCANTYPE aflatin -->

Research finding for iteration 001.03. No renderer change follows from this note. Evidence:
`out/diagnostics/roboto-stem-balance-20261029/` (`stage-captures.json`, `probe-captures.json`, `stem-analysis.json`,
`browser/index.html` with `browser-data.json`, `commands.log`).

## Question

The [recorded limitation](../revisions/001/03-spacing-kerning.md#native-monochrome-scan-conversion) states that Roboto
14px, weight 400, width 100 keeps unequal principal stem widths in `m` and `u` against `n` under font-instructions-first
handling. This investigation reproduces that case under the actual current main-page policy rather than the historical
FontHintsFirst notes: fitting `font_hints_auto`, rasterization `free_type_mono_terminals`, diagonal fitting on, dropout
smart, executed font scan instructions authoritative (`apps/web/src/app/renderer/preview-policy.ts`, `render-spec.ts`).
The landing/matrix resolved defaults enable diagonal fitting; `render-spec.ts` URL omission preserves the historical
diagonal-off default, so the diagonal-on runs here follow the landing default, not the omission path.

## Measured current result

At 12, 14 and 16px, every principal stem of `m`, `n` and `u` is fitted to exactly 1.0px. Representative straight body
rows deliver one ink column per stem; the `u` bowl row is the measured exception (row 6 delivers 1/2, right stem two
columns). The recorded principal-stem inequality does **not** reproduce in these straight-span rows under the current
pipeline.

| Glyph | Raw source stems (font units) | Raw (px @14)             | Automatic X fit | Delivered straight rows |
| ----- | ----------------------------- | ------------------------ | --------------- | ----------------------- |
| `m`   | 186 / 185 / 186               | 1.2715 / 1.2646 / 1.2715 | 1.0 / 1.0 / 1.0 | 1 / 1 / 1               |
| `n`   | 185 / 186                     | 1.2646 / 1.2715          | 1.0 / 1.0       | 1 / 1                   |
| `u`   | 185 / 186                     | 1.2646 / 1.2715          | 1.0 / 1.0       | 1 / 1 (bowl row 6: 1/2) |

Raw geometry comes from genuine f64 source outlines (`fitting_source::draw`); stage widths from the captured command
streams; units use unitsPerEm 2048 read from the font head table. The middle stem of `m` measures 1 unit narrower than
its outer stems (185 vs 186 units, 0.007px at 14px): near-equal, with no universal class tolerance asserted. The
pipeline fits all of them uniformly to 1.0px.

## Which stage changes which relation

- **Raw source**: near-equal, 185–186 units (1.26–1.27px at 14px). The middle stem of `m` measures 1 unit narrower than
  its outer stems.
- **Independent unhinted source** (same axes/size, Zeno Mono): body rows show two-column stems (`m`, `n`) and a
  two-column right stem plus doubled bowl rows (`u`). At 1.27px the unfitted outline straddles the threshold, so grid
  phase alone decides one versus two columns. This is the historical defect mechanism, still visible in this control
  arm.
- **Selective fit**: X is automatic-owned (`native_axes [False, True]`, engine `auto_x_native_y`); delivered X equals
  the automatic commands exactly and delivered Y equals the native commands exactly. The per-coordinate and
  overlay-equality proof is the parent receipt (`out/diagnostics/roboto-stem-balance-20261029/host-stage-identity.json`:
  all 12 entries true against stage capture `88ed6eb0…`); the replay seam is covered by `probe-captures.json`. Every
  near-equal stem snaps to the same 1.0px integer width. Native TrueType instructions own Y only for these glyphs; they
  do not move X.
- **Top alignment**: no top-alignment correction applied to these glyphs (their captures carry no applied top-alignment
  record); geometry unchanged by this stage.
- **Diagonal overlay**: abstained (`reason: width:all-abstained`); straight stems are outside its geometry scope.
  Overlay-off inputs equal delivered outputs byte-identically (commands and pixels under identical frames), so there is
  no stage confusion: donor reference stayed pre-alignment, replay inputs post-alignment, independent reference plain.
- **Scan**: executed font state is authoritative and enabled (`scan_type: 5`, contour mode 5: smart dropout excluding
  stubs, per the OpenType `SCANTYPE` rules), recorded per glyph in `stage-captures.json`. `font_scan.source_sha256`
  there identifies the vendored scan-implementation snapshot (`crates/generator/vendor/skrifa-scan`, a metadata-only
  scan-state snapshot), not the font; the font identity is `provenance.font_sha256`. Integer 1.0px stems center-fill to
  one column. Dropout attribution was not isolated; it would need center-fill/dropout accounting of the delivered stem
  pixels. Remaining extra pixels sit on arch rows (`m`/`n` shoulders) and the `u` bowl rows; the unhinted-source arm
  uses a different frame and placement, so no cross-arm identity or no-damage conclusion follows.

## Why uniformity is the expected outcome here

[Hersch §5](papers/1993-hersch/paper.md#5-basic-grid-constraints): on vertical bars, phase determines discrete width,
and related bars need their phase fixed relative to the grid. [Hersch §6](papers/1993-hersch/paper.md): centering stems
of slightly different widths produces the same rasterization when both consult the same snapping reference (Fig. 23).
The automatic hinter implements exactly this: Skrifa 0.48.0 `autohint/hint/edges.rs` (`align_stem_edges`, `snap_width`)
attributes its stem snapping to the corresponding FreeType `aflatin.c` lines (inspected correspondence; runtime parity
was not verified here). Snapping near-equal stems to one shared fitted width is the sourced standard-width mechanism,
not a per-glyph correction. No project stage needed to repair the recorded relation because the upstream automatic fit
already preserves it once X is automatic-owned.

## X ownership and the correction question

X is automatic-owned here, so the "automatic source-shape mode" question does not meet a native-owned-X barrier on these
stems: a diagonal-shape-06 correction would be ownership-permitted, but the stage abstains on straight-stem geometry and
none is needed. Native-owned Y is retained throughout (arch/bowl Y included), and executed `scan_type 5` forbids
stub-rescue corrections, so any future proposal touching arch/bowl rows must keep native Y and respect stub exclusion,
or explicitly abstain.

## Classification

- **Recorded principal-stem inequality (`m`/`u` vs `n`): not reproduced at 14px straight-span rows under the current
  main-page policy.** Overlay-off and delivered records share identical frames, command bytes and pixel bytes for
  `m`/`n`/`u` (both selective and forced-automatic pipelines; see the receipt linked above), so the current straight-row
  outcome is established at this setting. This is a non-reproduction at one setting, not a global resolved or optical
  verdict.
- **Pending assessment (curve regions; differences reported, no identity claimed):** at 14px, `m` arch row 1 delivers
  `##...##...#` while the forced-automatic arm delivers `##..###..##`; `n` arch row 1 delivers `##...#` in both arms;
  `u` bowl rows deliver `#...##` / `.###.#` in the delivered and forced-automatic arms, while the full-automatic
  FreeType arm delivers `.#####` on the last row (native-Y versus auto-Y bowl placement). The unhinted-source arm uses
  different frames and placement throughout `m`/`n`/`u`, so no cross-arm identity follows. Whether these curve-region
  differences disturb reading rhythm remains an open inspection question.
- **Out of scope disclosure:** `t` was captured but its outline yielded no straight-stem measurement at these rows, so
  no claim about `t` follows; the non-reproduction covers `m`/`u`/`n` principal stems only.
- **Pending assessment:** the uniform 1.27px-to-1.0px thinning itself. Equal treatment preserves the source
  relationship, but whether 1px (rather than 2) is the right standard at 14px is a standard-width optical question this
  lane does not answer. Per-glyph phase shifts, threshold tuning or thickening individual stems are not justified
  responses.

## Best applicable next approach (not authorized)

If optical review ever promotes the pending rows or the 1px standard to a finding, the sourced direction is the shared
standard-width decision of [upright stem consistency](upright-stem-consistency.md) (Shamir §§3.2–3.6 dependency
ordering, Hobby §4 width classes, Hersch §6 shared snapping), applied font-wide rather than to `m`/`u`/`n` alone.
Constraints: native-owned Y stays fixed; executed `scan_type 5` excludes stub rescues; diagonal-shape-06 abstains on
straight stems; no pixel, phase or threshold tuning; no preview or publication change without optical acceptance.
Implementing it needs a new task; this turn only investigates.

## Unresolved questions

1. Is the uniform 1px stem (from 185/186 units) optically correct at 14px, or should the class standard be 2px with a
   size transition nearby? Needs optical assessment across 12/14/16px; tests cannot decide it.
2. Do the `u` bowl-row and arch-shoulder doublings disturb reading rhythm against `n`? Same assessment venue.
3. Captures reflect the dirty working tree at `06c34f7` (parallel lane active); unrelated edits were preserved
   untouched. Re-run after the tree settles if exact-identity evidence is required later.
