# Roboto light weight continuity investigation

<!-- cspell:words unhinted SCANTYPE roundoff ctypes thresholding scanline -->

Started 2026-10-02 from the user's report about Roboto 14 px at weights 200 and 100. The failure is reproduced and
localized. Candidate 001.02 implements outline-driven dropout control and coordinated extra-light diagonal widths.
Optical acceptance remains open. Production remains approved 001.01.

## Feature and foundation

The feature is a connected subpixel stroke, including bowl shoulders and attachments to upright stems. The intent is to
retain recognizable connected strokes while preserving counters, anchors, tangents and relative weight.
[Hersch 1993, sections 5–6](../../references/papers/1993-hersch/paper.md) treats placement, width relationships and
continuity together; [Shamir 2003, section 3](../../references/papers/2003-shamir/paper.md) grounds feature
preservation.

[Pinned FreeType source](https://github.com/freetype/freetype/blob/57617782464411201ce7bbc93b086c1b4d7d84a5/src/autofit/aflatin.c)
defines an extra-light axis as a standard width below 5/8 pixel and preserves its original width before minimum-width
fitting, including in monochrome. Local counterparts are
[scale.rs](../../../../tools/generator/vendor/skrifa-baseline/src/outline/autohint/metrics/scale.rs) and
[edges.rs](../../../../tools/generator/vendor/skrifa-baseline/src/outline/autohint/hint/edges.rs).
[probe.rs](../../../../tools/generator/src/probe.rs) subsequently uses Zeno Alpha coverage and threshold 128. This
pipeline does not apply TrueType monochrome scan conversion's dropout control.

## Evidence

Font SHA-256: `d7598e12c5dbef095ff8272cfc55da0250bd07fbdecbac8a530b9b277872a134`. The isolated Rust sweep uses width
100, explicit automatic hinting, threshold 128 and gamma 1 over Latin letters/digits. Its 40 cases cover sizes
14/16/18/20, weights 100/200/250/300/400 and mono/gray. Independent source, upstream reference and approved baseline
captures feed the current `evaluation::evaluate`; its `candidate` field denotes the baseline argument in this report.
This initial capture predates the working candidate. Additional interpreter captures cover the five weights at 14 px
mono.

| Weight at 14 px | Standard X width | Standard Y width | Extra-light axes | Baseline a                 |
| --------------- | ---------------- | ---------------- | ---------------- | -------------------------- |
| 100             | 0.375 px         | 0.391 px         | Both             | Four surviving pixels      |
| 200             | 0.547 px         | 0.531 px         | Both             | Broken shoulder attachment |
| 250             | 0.672 px         | 0.641 px         | Neither          | Connected in this capture  |
| 300             | 0.828 px         | 0.750 px         | Neither          | Connected in this capture  |
| 400             | 1.266 px         | 1.109 px         | Neither          | Connected in this capture  |

Standard widths come from Skrifa's public ahead-of-time metrics API, not an instrumented production just-in-time trace.
Its nonempty extracted widths and actual fitted straight-stem sections corroborate the mechanism.

At weight 200, shoulder pixels `(2, -5)` and `(3, -5)` survive, but attachment `(4, -5)` has coverage **127** against
threshold **128**; upright `(5, -5)` has coverage 188. These are glyph coordinates with a y-down raster baseline.
Shoulder coverage is identical in baseline and upstream. The missing pixel disconnects a source-connected shoulder from
its stem. Location, geometry and web appearance demonstrate damage beyond the component-count diagnostic. The one-unit
miss illustrates sensitivity; it is not grounds to tune the threshold.

At weight 100 the shoulder's X 2/3/4 coverages are 106/104/103. The fitted upright at y-up 3.5 spans X 5.3125–5.6875,
retaining its 0.375 px width. Most isolated stroke coverage cannot reach half a pixel. Baseline a retains four pixels,
upstream three and unhinted source one. Independent interpreter a retains two pixels at weight 100 and eleven at weight
200: switching engines is insufficient under the same raster/conversion policy.

Weight-200 a is connected at the tested 16/18/20 px sizes. At 16 px its X standard reaches 0.625 px and exits the
extra-light branch, while Y remains extra-light. Weight-100 a continues to lose shape through these sizes. These are
witness observations, not general safe-weight recommendations. Gray a remains recognizable in the rebuilt web tester: 26
nonzero pixels at weight 100 and 30 at weight 200, with baseline equal to upstream. Source strokes still contribute
coverage; binary conversion loses them.

## Initial investigation classification

The initial investigation compared approved baseline versus independent reference. The implementation below compares
working candidate 001.02 with approved baseline 001.01.

- **Confirmed existing continuity failure:** a, Roboto 14 px, weight 200, width 100, mono 1-bit. Inspect shoulder
  continuity and bowl shape. This attachment also fails upstream; production promotion did not introduce it.
- **Confirmed existing shape loss:** a, Roboto 14 px, weight 100, width 100, mono 1-bit. Inspect whole-symbol continuity
  and legibility. Four surviving pixels no longer express the source letter.
- **Local thickening against reference:** One diagonal pair changes five quadratic commands in a's lower-right bowl
  attachment. X coordinates stay fixed; Y movements reach 0.391 px at weight 200 and 0.5 px at weight 100. Opposing
  lower slant borders spread with their controls; upper shoulder and upright remain unchanged. Weight 200 regains the
  lower attachment but retains the shoulder break; weight 100 gains an isolated lower-bowl pixel. Anchors and ownership
  do not cover the missing shoulder. This is partial local thickening, not general continuity restoration. There is no
  evidence of a malformed continuous outline.
- **Pending contrast assessment:** Diagonal source/standard transfer assumes a standard fitted width of at least one
  pixel, whereas extra-light rectilinear fitting preserves subpixel widths. The policies disagree. The weight-100 web
  specimen retains substantial w/x/y slants beside nearly absent upright/curved strokes. Assess coordinated optical
  weight and source contrast before correction.
- **Pending broader continuity assessment:** Weight-200 web b/d/o/e show further bowl/curve losses. Full captures and
  topology signals remain available; component counts alone have not classified other symbols as defects.

## Initial investigation scope and validation

The normal preview remains three families at 14/16/18/20 px and configured weight-400 axes. Interactive controls do not
expand published comparison scope. These low-weight findings remain in notes and isolated diagnostics; no out-of-scope
Attention marks or comparison pages were added. Existing accepted Attention records remain unchanged.

All 40 investigation cases passed current Rust evaluator hard invariants. Existing evaluation, production and
independent-reference invariance suites passed: 18 tests. `just preview-build` succeeded. Actual browser captures at
weights 100/200/250 in both profiles had no page errors. Optical inspection used the web tester at 4×.

Local evidence is retained in `out/diagnostics/roboto-light/`: `evaluation.json`, `metrics.json`,
`a-horizontal-sections.json`, per-case captures, interpreter reports, web captures and harnesses `capture.rs`,
`metrics.rs`, `browser.mjs`. Scratch harnesses were removed from source directories. Evaluation SHA-256:
`fc5c286346681112a980fbd8f635926e0d2a345147d75b029230685863a094d9`.

## Candidate model

The feature is an interior filled stroke narrower than one pixel whose ink was lost during binary conversion.
[Hersch 1993 §7](../../references/papers/1993-hersch/paper.md) scans horizontal and vertical interior spans and selects
pixels near their midpoint.
[TrueType SCANTYPE](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#scantype) provides
midpoint-based smart dropout rules and stub handling; the
[scan converter specification](https://learn.microsoft.com/en-us/typography/opentype/spec/ttch01#the-scan-converter)
explains why narrow connected outlines require this stage.

**Project hypothesis:** retain Zeno's ordinary coverage conversion and rescue subpixel nonzero-winding interior spans
that contain no delivered black pixel center. Compute crossings from the fitted line/quadratic/cubic contours in both
scan directions, then take the union of midpoint rescues against the original bitmap. Include stubs; exact midpoint
pixel ties follow the left/bottom convention. This adapts the sourced geometric rule to coverage rendering; it is not
full TrueType scan conversion or a claim of whole-glyph FreeType parity. It does not lower threshold 128, dilate the
bitmap, search phases or recognize glyph names. The raw coverage and fitted outline are untouched by dropout control.
Monotone curve branches use derivative roots and f64 intersection solving; the coincidence bound handles numerical
roundoff of coincident reversed crossings, not optical thickness. Invalid contour winding and excessive work fail
explicitly, rather than silently skipping a correction.

The diagonal source/standard transfer now honors its chosen horizontal standard's extra-light policy. It transfers a
ratio of one when that standard remains subpixel and removes the later dominant-axis pixel floor in this case. Existing
motion, anchors, prepared tangent dependencies, contour ownership, atomic conflicts and rounding separation stay in
force. **Project hypothesis:** subpixel design weight belongs to fitting; binary visibility belongs to dropout control.
This allows light diagonals to become thinner geometrically than 001.01 while rescuing the lost upright and curved ink.

The standard is deliberately shared across straight/curved/mixed diagonals, including shallow ones, as in accepted
001.01. It does not switch reference class with projection direction. At Roboto 16 px weight 200, X exits extra-light
while Y remains extra-light: diagonals follow X, horizontal bars follow Y. Muse flagged this axis difference; it is
retained as a documented source-class hypothesis, rather than claiming identical bar/stem policies. Judge diagonal
contrast against upright stems and bars separately across sizes.

Candidate-only raster dispatch records `coverage_dropout` provenance; the evaluator reproduces that policy from the
stored outline and still rejects modified coverage, pixels, placement or unsupported gray policy. Independent source and
upstream require `coverage`. Gray and disabled candidate paths remain unchanged. Delivered binary topology is reported
separately from hypothetical threshold samples, as a diagnostic without an acceptance score.

## Independent checks and implementation ownership

An isolated ctypes capture sends the approved fitted outlines to FreeType 2.14.3's monochrome outline rasterizer with
smart dropout, with/without stubs and without dropout. At 14 px, weights 100/200, smart-with-stubs a is connected and
retains a counter, supporting the scan-conversion mechanism. It differs from the hybrid coverage result in some pixels;
center fill, 26.6 input conversion and coverage thresholding are different contracts. Raw captures and the harness are
in `out/diagnostics/roboto-light/fix/freetype-mono.json` and `freetype_capture.py`.

The host implemented the raster/diagonal model, evaluator and diagnostics. Muse implemented transformed geometry tests
and the preview role routing/version switch. The host corrected gray routing to use the unchanged production gray target
for every interactive role and corrected the dev preview build dependency. Publication captures keep their independently
specified gray target; baseline/candidate agree within each target.

Muse independently reviewed the raster and extra-light policy. The shared horizontal reference-class concern is disposed
above. Its speculative near-degenerate cubic/winding concern had no failing witness; invalid geometry remains a hard
error, preserving report integrity rather than silently publishing an unassessed fallback. Bounded work and transformed
curve tests remain controls. Muse's implementation turns hit bridge time limits, then resumed in the same sessions;
completed test/review/handoff results were verified by the host.

- Geometry/tests/review session: `01a0fc6f-4c73-76a5-81ab-97474ff99a6b`.
- Preview implementation/handoff session: `01a0fc71-8186-7fbc-968d-ed4318bc2554`.

## Candidate findings and review

The final isolated sweep covers 80 cases: Roboto 14/16/18/20 px, weights 100/200/250/300/400, widths 75/100, mono/gray,
Latin letters/digits. Compare `baseline` and `candidate` in each capture. Earlier raster-only captures are retained
separately under `fix/raster-only/`, so fitting and scan-conversion interventions can be distinguished.

At 14 px width 100, weights 100/200 a has a connected shoulder, bowl and upright in the candidate, with its counter
retained. This is a geometric continuity finding backed by scanline crossings and the web appearance; the ink-count
increase alone is not an optical score. The lower-bowl diagonal target also changes under the extra-light rule. Classify
this as **mixed**: geometric thinning of the lower slant, restored binary shoulder/upright coverage. Inspect continuity,
whole-symbol shape and slant/upright contrast together. The low weights remain outside the published comparison matrix;
inspect them through the web tester using Latest 001.02 versus Approved baseline 001.01.

All 80 sweep cases and all 24 latest-variant published cases pass the current Rust evaluator hard checks. Passing those
checks does not establish optical acceptance or close 001.02. The original investigation accidentally labelled its
40-case sweep as 80; the count above corrects that bookkeeping error. The new 80-case sweep includes both widths.

The published weight-400 matrix has **unchanged fitted outlines and raw coverage** in every baseline/candidate pair; all
gray pairs are identical. Added binary ink comes from thin contour spans, not new point fitting. Agent inspection
classifies these as local raster thickening, asking about optical weight rather than claiming an outline regression.
Most ordinary variations retain the intended stroke/serif roles without a specific unresolved concern. Five cases have
meaningful terminal-weight questions and remain pending in Attention before publication:

| Published scope, mono             | Changed source feature                                                                           | Inspection question                                           |
| --------------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------- |
| Literata 14 Q, wght 400 / opsz 14 | Curved lower-tail end now fills its thin column at raster x=11, y=0/1; outline/tangent unchanged | Does the tail retain its intended lightness against the bowl? |
| Literata 14 x, wght 400 / opsz 14 | Thin terminal/serif coverage becomes binary ink                                                  | Are the terminals too heavy relative to the crossed strokes?  |
| Literata 14 y, wght 400 / opsz 14 | Upper terminal coverage gains binary ink, fork geometry unchanged                                | Do terminal weight and fork contrast remain balanced?         |
| Source Sans 3 16 x, wght 400      | Slant-end boundary coverage gains binary ink, accepted terminal placement unchanged              | Do the ends look flared or too heavy?                         |
| Roboto 18 x, wght 400 / wdth 100  | Both upper/lower slant ends gain corner ink; crossing geometry unchanged                         | Are the terminal ends balanced with the stroke bodies?        |

These are pending assessments, not confirmed regressions. Prior acceptance covered 001.01; it did not freeze these
pixels. Source Sans 3 16 w remains unchanged against baseline and its accepted inner-stroke correction stays reviewed.
Roboto 14 a at weight 400 is also unchanged; the reported low-weight concern remains explicitly reviewable in the
tester. No low-weight Attention entry bypasses the published preview guard.

## Completed validation and disposition

- Full generator suite: 161 tests pass, including disabled independent-reference parity, production routing,
  conservative join guards, publication scope, and 12 transformed dropout geometry tests.
- Candidate diagonal unit tests: 21 pass, including extra-light normal weight/contrast under steep/shallow projections
  and reflections. Run with `cargo test --locked --manifest-path tools/generator/vendor/skrifa-candidate/Cargo.toml
  --lib diagonal`. Its local lock now matches the stable candidate package name; dependency versions are unchanged.
- Production-only generator build (`--no-default-features --features native-io`): evaluation/production/surface checks
  pass; candidate remains unavailable. WASM default 11 and preview 12 tests pass.
- Final web suite: 64 tests pass, including real candidate WASM, low-weight role switching with identical layout, gray
  role identity, published latest selection and Attention scope.
- `just preview-build` succeeds. Actual browser captures through localhost:8903 have no page errors. Visual inspection
  confirms recognizable connected low-weight a and restored text. Compare the same text/axes using the version switch.
  The five regular-weight terminal/tail questions above remain pending optical assessment.

Integration failures were resolved at their cause: straight-control identity excludes the new raster-policy provenance
field while still requiring identical geometry/coverage/pixels; old comparison fixtures explicitly select their intended
baseline/reference pair; the real-WASM browser check now uses the separate candidate-enabled preview artifact. No
connectivity guard, gray identity requirement, or preview scope guard was relaxed.

001.02 is implemented and published for assessment, **not closed or promoted**. Production stays on the separate
approved 001.01 snapshot. Optical acceptance of the light-weight contrast and the marked terminal cases remains the next
action.
