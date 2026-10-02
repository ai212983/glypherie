# Roboto light weight continuity investigation

<!-- cspell:words unhinted SCANTYPE roundoff ctypes thresholding scanline -->

Started 2026-10-02 from the user's report about Roboto 14 px at weights 200 and 100. Accepted and closed as 001.02:
outline-driven dropout control, coordinated extra-light diagonal widths and fractional shared-width fitting soften the
459/460 transition. Production uses the separate approved 001.02 baseline. The acceptance and promotion record below
supersedes historical open/pending statements; the remaining binary and placement steps are accepted limitations.

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

## Checkpoint candidate findings and review

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

## Checkpoint validation and disposition

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

## Shared width transition experiment (2026-10-02)

Checkpoint commit `d9ba93f` preserves the preceding candidate and the main worktree. The pre-existing dirty
`docs/references/VisualTrueType` submodule remains outside that commit. This follow-up belongs to the still-open 001.02;
committing the checkpoint does not accept or promote it. The web continues comparing candidate with approved 001.01;
isolated captures also compare the experiment with the checkpoint.

### Feature, source and invariant

The feature is the shared width class used by upright stems and diagonal thickness transfer. At Roboto 14 px, width 100,
the scaled X standard changes from 95/64 px at weight 459 to 96/64 px at 460. The source H upright width is 1.5625 px at
both coordinates. The inherited Mono width policy nevertheless rounds its standard from 1 to 2 px; diagonal transfer
reconstructs that rounded standard and nearly doubles its ratio. This is a fitting discontinuity, not a corresponding
source weight change. The checkpoint H grows from 28 to 48 delivered pixels and A from 24 to 46. These counts identify
the witness; the corresponding fitted border separation establishes the thickness jump.

[Pinned FreeType `af_latin_compute_stem_width`](https://github.com/freetype/freetype/blob/57617782464411201ce7bbc93b086c1b4d7d84a5/src/autofit/aflatin.c)
already supplies a smooth horizontal width branch. [Shamir §§3.2–3.4](../../references/papers/2003-shamir/paper.md)
grounds shared feature widths and relative design dimensions. **Project hypothesis:** reuse that inherited smooth
X-width policy for candidate automatic Mono/default-script fitting, including glyphs without diagonal pairs. Retain Mono
and Y snapping, blue zones, existing placement, ownership and tangent rules. Store each standard's actual fitted width
without changing its scaled source value. Diagonals transfer `source thickness × fitted standard / scaled standard`,
then retain the existing dominant-axis projection, rounding bound and motion constraints. The selected class remains the
horizontal standard for shallow and steep diagonals, as documented above. This is an adaptation of the smooth branch,
not FreeType Mono parity; no new optical threshold, phase choice or symbol exception is introduced.

The invariant is coordination with the actual fitted class and preservation of distinct source thicknesses within the
existing projection/rounding margin. Near the first standard, smooth fitting returns its scaled value (subject to the
inherited minimum); the quarter-pixel guard belongs to later diagonal projection. Extra-light fitting and outline-driven
dropout control remain separate geometric and raster responsibilities.

### Evidence and limitations

The isolated current-Rust sweep covers **288 cases**: Roboto sizes 14/16/18/20, weights
100/200/250/300/400/440/450/455/458/459/460/461/465/470/480/500/700/900, widths 75/100, both profiles, Latin
letters/digits. All evaluator hard invariants pass; all 144 grayscale captures have identical baseline/candidate records
and metrics. Another **24 cases** cover the unchanged published family/size/profile matrix with ASCII 33–126 and degree;
all hard invariants pass and all grayscale baseline/candidate records are identical.

At 14 px, width 100, H's first fitted upright changes **1.484375 → 1.500000 px**, replacing the full-pixel width jump.
The diagonal shared ratio is now one at both coordinates. Captured candidate A/V/x/y each retain their delivered ink
population across 459/460; H changes 27→28, I stays 11, a changes 28→31 and n 20→23. These diagnostic populations are
not an optical score or a promise of pixel continuity. H's inherited placement still shifts at the boundary (left border
0.671875→1.0 px and right upright 6.671875→7.5 px); counter spacing changes even though stroke width is gradual. This
experiment addresses width policy only. Binary conversion, placement decisions and Y snapping still have discrete
transitions. The same sweep checks neighboring weights, sizes and condensed width without selecting a threshold to
maximize pixel agreement.

Independent source geometry also explains regular-weight deviations. At Roboto 18 px, the inspected v border's source
normal thickness is 1.433 px, approved baseline 1.933 px, experiment 1.470 px. For w it is 1.290 / 1.622 / 1.324 px.
Literata 16 z is 1.322 / 1.602 / 1.324 px. These are justified thinning toward the source shared-width relationship,
subject to continuity and optical review, rather than proof of damage from fewer pixels. Approved glyph acceptance
remains historical evidence, not a geometry freeze.

### Agent classification before publication

The host inspected actual fitted source-feature changes against approved 001.01 before building the preview. X-width
fitting generally thickens the one-pixel upright class at 14/16 and thins the two-pixel class at 18/20, with inherited
placement changes. Diagonal effects follow the shared class and the existing projected rounding guard; some diagonals
therefore keep their outline. Y-only axial witnesses keep their Y geometry. Dropout adds raster ink independently. Mixed
source-feature changes need both continuity/shape and weight/contrast assessment. Pixel totals did not select these
classifications or automatically generate Attention marks.

The exact weight-400 scopes below are pending in Attention. Existing accepted cases are reopened only for these
meaningful changed-feature questions. Unlisted normal variations have no specific unresolved concern from this batch;
this is not blanket optical acceptance.

| Published mono scope              | Agent classification and feature                                                     | Inspection question                                                 |
| --------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------- |
| Roboto 14 H, wght 400 / wdth 100  | Mixed: wider uprights and changed right-stem/counter placement                       | Are stem/bar weight and counter spacing balanced?                   |
| Roboto 14 x, same axes            | Thickening: crossed diagonal bodies spread with the fractional standard              | Is crossing weight balanced with uprights?                          |
| Roboto 16 I, same axes            | Shape/placement: refitted upright shifts horizontally within the same linear advance | Are left/right bearings balanced in text?                           |
| Roboto 18 v/w, same axes          | Thinning: paired slants approach source thickness; junctions remain connected        | Do stroke bodies and lower/inner joins retain shape and weight?     |
| Roboto 18 x, same axes            | Raster thickening with unchanged fitted outline                                      | Are the slant ends still too heavy?                                 |
| Literata 14 Q, wght 400 / opsz 14 | Mixed: bowl width and tail geometry change under the shared class, with dropout ink  | Are tail continuity and tail/bowl contrast balanced?                |
| Literata 14 x/y, same axes        | Mixed: small crossed/fork border changes plus terminal raster thickening             | Do terminal weight, continuity and source contrast remain balanced? |
| Literata 16 y, wght 400 / opsz 16 | Thinning: slant bodies follow fractional class; protected dependencies retained      | Do fork and lower join retain shape and contrast?                   |
| Source Sans 3 16 H, wght 400      | Mixed: wider uprights and horizontal placement shift                                 | Are stem/bar weight and counter spacing balanced?                   |
| Source Sans 3 16 w, same axes     | Shape/placement: inner-stroke X positions change while cap Y remains fixed           | Is inner spacing balanced against the outer strokes?                |
| Source Sans 3 16 x, same axes     | Mixed: small slant-end geometry changes plus raster thickening                       | Are ends, crossing and stroke contrast balanced?                    |

Low-weight continuity and 459/460 placement findings stay in isolated diagnostics and the interactive tester, outside
published Attention scope. All five checkpoint concerns remain pending with updated feature questions; four previously
accepted cases reopen for material thinning/placement changes, and four new representative weight/spacing questions are
recorded. No review annotations affect fitting.

### Contracts, tests and ownership

Muse implemented the fitter and synthetic tests through Muse Code Bridge session `01a0fcb1-e0e9-758a-b9b6-d76b408020f1`;
the host verified the model and owns diagnostics, integration tests, Attention and publication. Muse's subsequent
read-only assertion review agreed that zero-pair identity and the historical +0.4 px width-increase expectation encoded
the replaced integer-width policy. The earlier research consultation was `01a0fca3-afbf-7b0e-ae90-346bb4d636a3`.

Four integration assertions were revised with their causes recorded: H/I/n and unsupported Literata c may change X
geometry, but retain command structure, Y geometry, connectivity and layout; protected Literata k retains its rejected
pairs and its junction contour shape under a uniform X translation; historical v/w/z thickening expectations now compare
to independently captured unhinted source thickness within the sourced projection-rounding and endpoint margin. The
existing conservative join sweep, Literata y/x contrast bounds, parallelism, detection/application contracts and
disabled reference/gray identity requirements are preserved. A new integration witness checks that a zero-pair H takes
the fractional standard at 459/460, independently of the diagonal solver. Synthetic tests cover fractional shared
transfer, distinct source roles, reflections, steep/shallow projections, disabled integer policy and unchanged Y policy.

Captures, source-border measurements, checkpoint binary and temporary harnesses are retained under
`out/diagnostics/weight-transition/`. The experiment is uncommitted pending review; 001.02 remains open and production
continues using the separate approved 001.01 snapshot.

### Experiment validation and disposition

- Full generator suite: **162 tests pass**, including unchanged conservative join guards, independent disabled parity,
  source contrast, production routing and publication scope.
- Candidate unit tests: **22 diagonal tests and the smooth-width policy test pass**. The new synthetic transfer checks
  use the existing quarter-pixel projection bound, converted to normal thickness; no optical test constant was fitted to
  isolated pixel outcomes.
- Preview WASM: **12 tests pass**. The actual candidate-enabled artifact was rebuilt with the current fitter; production
  remains the separate baseline path.
- Web suite: **64 tests pass**, including real preview WASM role switching, unchanged layout, grayscale identity and
  publication/Attention scope. The browser captures 42 baseline/candidate views across weights and the normal matrix
  without page errors; a final Source Sans 3 16 px capture explicitly verifies the requested text, axes and role.
- The preview preserves 72 published cases (24 per renderer role), configured profiles, axes and symbol coverage. `just
  preview-build` succeeds. Agent classification and 13 pending scoped Attention marks precede publication.

The first broad run exhausted a temporary-directory quota; rerunning with workspace temporary files passed. Browser
checks use a shorter cache temporary path because Chromium's Unix socket cannot fit under the longer diagnostic path. A
browser fixture also matched an old render when switching back to a font; its wait now requires a fresh completed
render, retaining the existing font-lifetime assertion. Neither issue changes fitting or relaxes a guard.

The width hypothesis is supported geometrically. The optical goal is **partially addressed**: the synchronized fitted
width cliff at 459/460 is removed, but binary coverage and placement retain a smaller step there and a substantial
upright-column step near 465. Do not treat this as a completed smooth optical-weight solution or promote it from
mechanical results. The experiment remains uncommitted and available for comparison in the web; 001.02 stays open.

## Acceptance and promotion (2026-10-02)

The user assessed the result as "really good result" and requested "lets commit it as 001.02". The current result is
accepted and 001.02 is closed. No further fitting action is required for this accepted iteration. The remaining abrupt
binary upright-column transition near weight 465 and inherited placement steps are accepted limitations of this result,
not claims of perfectly continuous monochrome optical weight. Broader diagnostic observations remain documented; no new
iteration or automatic follow-up is started.

Acceptance covers the current Roboto light-continuity and shared-width result and the published Roboto/Literata/Source
Sans 3 14/16/18/20 px weight-400 matrix, with its configured axes and both output profiles. All 13 pending published
Attention questions are disposed as accepted tradeoffs. Source thickness/contrast, anchors, protected dependencies,
transformed geometry and joins provide the geometric rationale; the user's assessment supplies optical acceptance. Their
recorded dispositions preserve the inspection scope and rationale without freezing future pixels or geometry. The
remaining 465 step had been disclosed before acceptance. Threshold, phase and detector constants are unchanged.

The accepted pre-promotion package is `iteration-02-36b1bdbe6ad665d68a77fddcf094d25ee30ca8218bd0a7a4c561db8d75ec992c`.
Its immutable generated assets and isolated candidate captures preserve the reviewed state. Promotion replaces only the
approved baseline fitter source with this accepted candidate source, retaining the separate `skrifa_baseline` package.
Automatic Mono production uses fractional shared-width fitting and outline-driven dropout; disabled fitting, grayscale,
unhinted and interpreter rendering retain their independent contracts. Dropout is available without the optional
candidate feature. Production never imports the working candidate library. AutoFallback applies dropout only when its
actual automatic engine enables the approved fitting policy.

The active publication now contains reference and approved `iteration-02` baseline; there is no active newer candidate.
Historical 001.01 packages remain generated artifacts rather than a second production fitter. The index subtitle shows
only **001.02**, as explicitly requested. Stable renderer roles and independent reference comparison remain available
through the version control and symbol routes, following the established approval model. The agreed family/size/axis,
profile and symbol matrix is unchanged: 24 cases per active renderer, 48 total after retiring the active candidate role.

Muse implemented the baseline snapshot promotion and production raster routing in the same Bridge session
`01a0fcb1-e0e9-758a-b9b6-d76b408020f1`; the host owns acceptance records, metadata, Attention, index subtitle,
independent parity checks, publication and commit. Promotion witnesses are retained in
`out/diagnostics/promotion-001-02/`, with links to the accepted captures under `weight-transition/`.

### Promotion verification

The approved baseline reproduces all 24 accepted candidate cases exactly: fitted commands, raw coverage, delivered
pixels, placement, advances and metrics. Independent source/reference captures remain unchanged. This is promotion
parity for the accepted state, not a snapshot contract for future model work. Baseline and candidate fitter source trees
are identical while retaining separate packages and provenance.

The full generator suite passes all 163 tests, retaining conservative join guards and reference invariance. The current
Rust evaluator passes hard invariants for all 24 approved cases. Candidate-disabled native checks pass 44 tests,
including production routing, the low-weight/width sweep and synthetic dropout geometry. Production WASM passes 11 tests
and the preview build passes 12; both artifacts build successfully. The web suite passes all 64 tests. An actual browser
capture verifies the sole index subtitle `001.02`, baseline/reference role selection and approved Roboto 14 px rendering
at weights 100/200/459/460/465 without page errors. Publication succeeds with the agreed matrix.

The probe parity test now compares automatic probe output against independent reference, retaining exact interpreter
parity with production. Its old automatic production identity assumed upstream integer widths even for straight H, which
the accepted shared fractional policy intentionally changes. Approved automatic production parity remains checked
separately against the baseline. No conservative join guard or optical threshold is relaxed.
