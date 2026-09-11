# Font legibility improvements

Status: Active — inventory and source alignment; visual review follows
Last-reviewed: 2026-09-10

Finish a general-purpose, non-neural font generator that produces high-quality,
consistent glyphs with minimal manual intervention. Complete Python generation
and human specimen review before considering a Rust port and device integration.
Methodology and papers live in the [font legibility reference](../reference/font-legibility.md);
reproduction commands live in [font_probe](../../tools/font_probe/README.md).

## Scope and current state

Roboto, Source Sans 3, and Literata are calibration targets. Supported families
and sizes enter through configuration. Product face/role assignments remain an
optional follow-up and do not block generator completion.

The [identity-free correction boundary](../reference/font-candidate-pipeline.md)
keeps character IDs, font-family selectors, and per-glyph correction tables outside
the rendering logic. Apply improvements through geometry, shared font measurements,
and explicit stage ownership. Glyph-specific corrections require a future
architecture decision. The current pipeline uses outline fitting before scan
conversion; manual pixel patches remain outside its scope.

- The existing [generator and JSON CLI](../../tools/font_generator/README.md)
  provide configurable bitmaps, metrics, and pair kerning. Their initial format,
  configuration, and reproducibility work is complete. The custom Python hinter
  now has a source-to-bitmap entry point for the calibration matrix.
- The consolidated pipeline reproduces the 832 admitted glyphs in
  [Cumulative Python v7](../notes/bar-and-curved-terminal-recovery.md#cumulative-integration)
  directly from source fonts. Another 49 cases are unresolved and excluded.
  Reproduction establishes regression parity, not complete visual acceptance
  of the repertoire.
- The [axis-consistency experiment](../notes/axis-and-stroke-consistency.md) remains
  unapproved: improved symmetry can damage taper and dot shape. Keep it separate
  from the approved cumulative reference until its fidelity problems are resolved.
- VTT integration remains deferred. The [learned bitmap-quality experiment](learned-bitmap-quality.md)
  is independent research, with no dependency in this completion sequence.

The [conformance workflow](../notes/shamir-model-conformance.md) owns paper fidelity,
source investigation, and documented interpretations or replacements. Research
unspecified behavior and implement conservative completions. Preserve the paper
baseline separately from approved experimental improvements. Verify numerical
execution before image review; inspect images before board verification. Phase 2
next work follows the [source-first prerequisite](../notes/shamir-model-conformance.md#2-research-each-unresolved-decision);
the unpublished feature-fit draft is paused per the conformance audit.

## 1. Consolidate source-to-bitmap generation

**Status: Done 2026-09-09.** One executable Python pipeline regenerates the
approved outputs from source files and settings, with regression checks and
explicit unresolved cases.

- [x] Inventory the stages and settings that produced the approved cumulative
  reference. Make their order, inputs, ownership, and failure behavior explicit.
- [x] Replace saved-font/checkpoint dependencies with executable stages from source
  font loading and variable-font instantiation through outline preparation,
  feature detection, fitting, scan conversion, and bitmap/metric output.
- [x] Keep frozen specimens as test references only. Preserve the 832 admitted
  outputs pixel for pixel, including advances and other exported metrics; trace
  differences instead of absorbing them into updated references.
- [x] Preserve explicit diagnostics for the 49 unresolved cases. Missing inputs
  and stage failures must remain visible rather than selecting older renderings.
- [x] Verify deterministic output from source fonts, configuration, and a documented
  environment in a clean run without historical generated artifacts.

Entry point `tools/font_probe/build_source_bitmap.py` writes
`tools/font_probe/out/source-bitmap-v1/` from the three source fonts plus
`tools/font_generator/examples/*.json` configuration. Curved-width and
source-junction experiments run as parallel branches from round-level output
with explicit newest-wins merges. The parity test against the frozen
`cumulative-hinter-v7` checks 832 admitted bitmaps, advances, and native
coordinates plus the identical 49 excluded cases. Axis-consistency and
endpoint-only cap variants stay out of the pipeline. Regression checks live
in `tools/font_probe/test_build_source_bitmap.py`.

Verification: a fresh full run with Python file reads and FreeType font opens
guarded against historical output access reproduced the approved matrix. All 55
focused checks passed, including bitmap, metric, coordinate, exclusion, and
export agreement checks. This establishes reproduction, not new visual approval.

Each face exports `*-candidate.ttf`, `*-bitmap.json` (pixels, width/height,
bearings, advances, native coordinates from the final render, with a test
that re-renders the TTF to confirm agreement), per-glyph HTML with
native-scale and enlarged PNG specimens under `img/`, and `report.json`
with repo-relative input hashes and tool versions. Calibration covers sizes
14/16/18/20 only; other sizes, weights, and families are untested and the
calibration table below labels test cases, not shipping choices.

## 2. Inventory and align the Python model

The [rule inventory](../notes/font-pipeline-rule-inventory.md) owns the mapping
from active code to paper sections, Microsoft source, and project choices.
The [conformance workflow](../notes/shamir-model-conformance.md) owns alignment
and readiness. Visual defect investigations resume after this phase.

- [ ] Inventory every active stage, including preparation, extraction, parameter
  sharing, representative selection, graph resolution, completion, fitting,
  ownership, native translation, and numerical thresholds.
- [ ] Verify each source citation against the actual operation. Separate specified
  behavior, conservative choices for researched gaps, experimental replacements,
  and unresolved decisions. Record a concrete reason for each retained departure.
- [ ] Align the working baseline with the source procedure. Use the paper's
  representative graph, dependency order and conflict priorities. Keep the
  approved experimental pipeline as comparison evidence.
- [ ] Verify operations and graph construction independently of rendered
  appearance. Document assumptions and remaining support limits before declaring
  the baseline ready.
- [ ] Generate a fresh specimen from the aligned baseline and review it with the
  user. Then decide which aspects merit improvement, showing all affected glyphs.

The [working audit](../notes/font-pipeline-rule-inventory.md#working-path-verification--2026-09-09)
uses first-on-curve representatives directly. It passed graph/construction/native
checks for 972 cases across 12 builds; the role/completion follow-up passed
77 focused tests with identical selected graphs and native coordinates. The approved
pipeline's representative search, weighted fitting, symmetry and recovery stages
remain experimental. The [shared-role and completion decisions](../notes/shamir-role-completion.md)
retain researched conservative policies. Preparation/extraction, membership
tolerances and requested-size SCFS translation remain before visual evaluation.
The [native translation comparison](../notes/shamir-native-translation.md) records
114 operation cases and the MIRP/member reference-state check. B12 remains a
departure. The opt-in native compiler accepts 922 of 972 source-font cases,
including 12 verified empty no-ops; 50 reject near-perpendicular vectors. Shared
parameters fit the integer CVT contract. The [paired-vector investigation](../notes/shamir-native-paired-vectors.md)
records a completed native iteration experiment: shallow pairs stagnate before
accuracy, so the 50-case rejection remains. The [direct arithmetic investigation](../notes/shamir-native-paired-arithmetic.md)
verifies the isolated prototype: all 124 pairs meet runtime-input accuracy, while
94 meet the original float-parent reference. The [parent-precision decision](../notes/shamir-native-parent-precision.md)
uses current 26.6 coordinates for native dependencies and retains the float reference.
The cardinal graph reference passes 54 graph/size cases and 528 instruction-prefix
checks. Verify oblique movement and direct-solver dependencies before integration;
scalable target capture, execution-domain range checks and graphics state remain open.
Preserve the equations.

The member-alignment and symmetry specimens remain diagnostic evidence.
Their visual comparison, including `Z`, is paused during source alignment.

**Complete when:** every active baseline decision has source evidence or a
researched, justified interpretation; retained departures have explicit reasons;
operation checks pass; and the user has evaluated the fresh baseline specimen.

## 3. Resolve excluded cases and define support

- [ ] Group the 49 excluded cases by construction, ownership, solver, or scan
  conversion failure. Fix causes through the same geometric API.
- [ ] Expand regression coverage with each recovered group and review its output.
- [ ] Define supported static/variable formats, axes, repertoire, missing-glyph
  behavior, metrics, kerning, and shaping boundaries for the finalized backend.
- [ ] Document any remaining unsupported construction and its explicit error or
  fallback policy. Track exclusions as unresolved coverage, not successful renders.

**Complete when:** every requested case has a verified rendering or a documented
support decision, and the remaining limitations are reviewed.

## 4. Audit the complete generated specimen

- [ ] Review every admitted glyph at native size and enlarged, then inspect text
  runs for spacing, kerning, clipping, wrapping, and ambiguous characters.
- [ ] Cover normal/inverse output, nearby sizes, supported weights/axes, and families
  beyond the three calibration targets. Include source outlines for fidelity review.
- [ ] Run structural and consistency diagnostics for widths, joins, counters,
  continuity, symmetry where appropriate, and cross-glyph relationships. Keep host
  measurements separate from human judgments.
- [ ] Review labelled images with the user, record coverage and residual defects,
  regenerate after corrections, and freeze the accepted Python reference.

**Human gate:** approve the complete tested specimen and its documented limits.
Passing numerical checks or reproducing earlier pixels does not satisfy this gate.

## 5. Package and extract the Python tool

Repository extraction may accompany consolidation; finalize its public interface
against the accepted Python reference.

- [ ] Move generator code, tests, research, and generator-specific plans into a
  separate repository. Choose the final technical name and destination when
  extracting. Keep Meditamer integration documentation and generated assets here.
- [ ] Provide a documented CLI for source fonts, sizes, variable axes, repertoire,
  rendering settings, and deterministic bitmap/metric exports.
- [ ] Record font provenance, licenses, checksums, tool versions, and settings.
  Separate reusable generation from specimen viewers and output adapters.
- [ ] Verify installation and source-to-bitmap generation in a clean environment;
  publish supported behavior, limitations, and reproduction commands.

**Complete when:** the standalone Python tool reproduces the accepted specimen
without Meditamer code or historical experiment artifacts.

## 6. Consider Rust and integrate generated assets

Begin after Python completion and full image approval.

- [ ] Decide whether a Rust port provides sufficient benefit. If pursued, use the
  Python reference for bitmap and metric parity across the supported test matrix.
- [ ] Implement an LVGL output adapter for bitmaps, character mappings, metrics,
  kerning, fallbacks, and bit depths; validate tables and representative layouts.
- [ ] Verify approved settings on Inkplate and Waveshare using normal/inverse text,
  intended distances, lighting, and relevant refresh modes. Record physical results
  separately from host and image evidence.
- [ ] Measure generated-table size, firmware size, and memory use. Read the
  [DRAM budget](../reference/dram/dram-budget.md) before changing buffers/statics.
- [ ] Retain the separate crash-screen BDF generator. Remove replaced assets after
  their consumers migrate and document the supported integration workflow.

**Complete when:** generated assets render correctly through LVGL and the target
panel paths, with host, image, build, and board evidence recorded.

## Calibration sizes

Pixels per em from the specimen generator. Column names label test cases;
shipping choices remain separate. Test ambient viewing at 80–100cm and reading
at 40–50cm. The [sizing script](../../tools/font_probe/sizes.py) uses measured
x-height/em ratios of 0.531 (Roboto), 0.510 (Literata), and 0.490 (Source Sans 3).

| Panel | Face | Ambient primary | Ambient secondary | Heading | Body | Caption |
| --- | --- | --- | --- | --- | --- | --- |
| Inkplate | Roboto | 122 | 70 | 44 | 34 | 28 |
| Inkplate | Literata | 126 | 72 | 46 | 36 | 30 |
| Inkplate | Source Sans 3 | 132 | 76 | 48 | 38 | 32 |
| Waveshare | Roboto | 64 | 36 | 24 | 18 | 16 |
| Waveshare | Literata | 68 | 38 | 24 | 20 | 16 |
| Waveshare | Source Sans 3 | 70 | 40 | 26 | 20 | 16 |

## Device specimen settings

Regenerate these integration specimens after Python glyph calibration:

- Weight 400 for the three calibration faces. Literata's optical size follows
  pixel size, clamped to its supported range of 7–72.
- The earlier coverage-threshold recipe (96 at sizes up to 20px, otherwise 128)
  belongs to the existing generator's specimens. Establish scan-conversion settings
  from the finalized backend rather than treating that recipe as approved policy.
- Inkplate specimens cover binary and eight-level gray; Waveshare uses binary.
  Production Inkplate interaction is binary. The [display refresh reference](../reference/display-refresh.md)
  owns mode transitions and baseline recovery.

## Optional follow-up: product typography

Choose product fonts and sizes, tune layouts, and migrate consumers after generator
and integration work. Track those choices separately from algorithm completion.
