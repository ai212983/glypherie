# 001.01 — diagonal weight

<!-- cspell:words XSHIFT -->

2026-10-01. Open; implementation is being tweaked in place. Acceptance pending. Git checkpoint pending.

## Problem and scope

Roboto 14 px 1-bit diagonals looked too heavy in A/V/v/w/x/y/z, followed by X and 16 px N/W/X/Y/Z.

User agreement on 2026-10-01 also includes thin diagonal strokes in Literata 14 px Q's lower tail, x, and y within
001.01. Existing diagonal-weight problems remain in scope even when the candidate is identical to reference. Roboto 16
px t's upright stem belongs to a separate stem-weight problem.

The optional experiment applies to Roboto, Literata, and Source Sans 3 at 14/16/18/20 px, weight 400. Upstream Skrifa
remains the independent reference. The working preview selects `iteration-01` with the current source-relative width
tweak, compared with reference. Earlier captures are observations within the same open iteration. Selection and passing
tests do not close the iteration or establish acceptance. Rasterization, threshold, layout, and 3-bit output remain
unchanged.

## Changes and reasoning

- Pair straight diagonal borders and solve shared endpoints together before final interpolation.
- Match source stroke thickness to font-wide stem widths, then quantize across the dominant direction. The initial
  horizontal-width approach widened X; this avoids increasing weight merely because of a diagonal's projection.
- Preserve axial anchors and supported axial/curve joins. Allow bounded movement along strokes so N-like joins can slide
  along anchored stems; incompatible constraints remain unapplied.
- Add a small geometric margin to prevent rounding a nominal one-pixel stroke below one pixel.

The approach draws on Hersch 1993, Microsoft VTT DStroke, and Shamir 2003. Automatic detection and fitting rules are
project hypotheses. Trial continuation models caused additional breaks and were discarded.

## Findings

The targeted Roboto strokes are thinner and remain connected. Earlier introduced breaks in Roboto 14 px M, Literata 18
px k, and Source Sans 3 16 px K were resolved. The configured corpus gains no disconnected alphabetic glyphs; three
changed % cases still need visual review.

Broader checks found new disconnected strokes in:

- Roboto 20 px W, weight 300.
- Literata 15 px W, weight 400, optical size 15.
- Source Sans 3 20 px y, weight 300.

Tests confirmed determinism, disabled equality with upstream, and unchanged layout/3-bit output. Those checks do not
establish visual acceptance or resolve the broader join failures.

## Decision and next step

Keep the experiment optional and retain the independent reference. Review Roboto 14 px X and 16 px N/W/X/Y/Z for weight
and balance. Correct the diagonal width policy and address the broader join regressions before acceptance. These
corrections remain within 001.01. This iteration addresses the diagonal-weight problem identified by user feedback. It
closes only when user and agent explicitly agree there are no further actions for this problem: resolved, not fixable,
or remaining work assigned to an agreed follow-up. Do not advance iteration identity before that agreement.

## Reported thin strokes: 2026-10-01 review

The review covers the published 1-bit specimens at weight 400, Roboto width 100, and Literata optical size equal to
pixel size. Fresh current-source rendering exactly matches the published candidate for all 1,140 ordinary monochrome
glyph cases. Published candidate generation: `093606378127fe6aee1fdf060699cb9c6be414f81010b4b8473619151702c2a6`.
Reference generation: `77e7d9e03211ae901738175351dff3cf75e50a0a1ba4ebc8acf0de0cb8107cd4`.

| Reported case | Reference ink pixels | Candidate ink pixels | Removed / added pixels | Applied / detected pairs |
| ------------- | -------------------- | -------------------- | ---------------------- | ------------------------ |
| Roboto 18 v   | 28                   | 20                   | 8 / 0                  | 2 / 2                    |
| Roboto 18 w   | 52                   | 38                   | 14 / 0                 | 4 / 4                    |
| Literata 16 z | 28                   | 25                   | 3 / 0                  | 1 / 1                    |
| Literata 18 v | 33                   | 33                   | 0 / 0                  | 0 / 2                    |
| Literata 18 y | 42                   | 42                   | 0 / 0                  | 0 / 2                    |
| Literata 18 z | 37                   | 39                   | 0 / 2                  | 1 / 1                    |

Roboto 18 v/w lose roughly 29%/27% of reference ink, leaving predominantly single-pixel diagonal runs. Literata 16 z
also loses diagonal pixels. These are effects of this iteration. Literata 18 v/y have identical fitted outlines,
coverage, and final pixels to the reference: their detected constraints remain unapplied. Literata 18 z retains every
reference ink pixel and adds two. The perceived thinness of these three 18 px Literata glyphs therefore cannot be
attributed to pixel removal by this iteration; their balance still deserves separate source/reference review.

### Pre-tweak width policy diagnosis

[`grid_width`](../../../tools/generator/vendor/skrifa-iteration/src/outline/autohint/hint/diagonal.rs) first measures
perpendicular source thickness, matches a standard stem only within 10%, then rounds to whole pixels. The solve uses
that integer as separation across the dominant axis. For slope `s = dx/dy`, ignoring the small safety margin, an integer
target `n` consequently has perpendicular thickness `n * max(1, |s|) / sqrt(1 + s*s)`. This is smaller than `n` for
non-axial strokes. The margin bounds endpoint rounding loss; it does not preserve source thickness or stroke weight
relative to other letters.

In the reported Roboto 18 v/w cases, the accepted borders have horizontal separation about 1.03 px and perpendicular
thickness about 0.98–1.00 px. Literata 16 z has about 1.03 px horizontal separation and 0.81 px perpendicular thickness.
Literata 18 z instead receives about 2.03 px horizontal separation and 1.68 px perpendicular thickness. These values are
measured from the final fitted straight borders, separately from raster ink counts.

The captured horizontal standard stem widths are 104/64 px for Roboto 18 and 103/64 px for Literata 16. Both round to
two pixels, while the affected diagonal targets use one. The 10% standard-matching window does not bring these diagonals
into the same quantization class as the standard stems.

The size transition is another warning: Roboto v has 24 → 18 ink pixels at 16 px, 28 → 20 at 18 px, and 34 → 41 at 20
px. Its unchanged n control has 22, 44, and 46 pixels respectively. The axial and diagonal width transitions are not
coordinated. Total glyph ink is diagnostic evidence, not an optical acceptance criterion.

The reference foundations distinguish width selection from phase control.
[Hersch §6, Fig. 25](../../references/papers/1993-hersch/paper.md) uses a reference-table horizontal width to make
parallel borders share phase.
[VTT DStroke](../../references/VisualTrueType/doc/VTT%20Language%20Reference/vttlang.md#dstroke) uses a diagonal width
along X or Y and selects diagonal CVT entries by character group. Neither prescribes the experiment's perpendicular
rounding, 10% matching window, or reuse of the integer across a different direction.

### Recommendation and validation limits

Treat the confirmed thinning as a correction within this still-open diagonal-fitting iteration before accepting it.
Coordinate diagonal reference widths, source stroke roles, dominant-axis quantization, and phase within 001.01. Globally
widening every diagonal or adding glyph-specific compensation would also affect the original heavy-stroke cases and
Literata's intentional thick/thin contrast. Existing reference and join controls must remain part of review.

Review Literata 18 v/y separately as reference behavior and unresolved constraint coverage; review z for balance even
though it gains ink. Do not require these glyphs to become uniformly thick merely because they were reported together.

At this pre-tweak investigation stage, all seven existing iteration tests passed. They establish disabled parity,
reproducibility, layout/grayscale invariance, and configured connectivity, but do not gate excessive thinning or
coordinated size transitions. Add source-relative stroke-width and size-transition evidence to the acceptance review;
connectivity alone is insufficient.

Local diagnostic captures, summary, and enlarged comparison image are under
`out/diagnostics/diagonal-weight-2026-10-01/`. Rendering implementation and specimen selection were not changed by this
investigation.

## Current width tweak within 001.01

Transfer the font standard stem's Mono fit ratio to source diagonal thickness, then project onto the dominant control
axis with bounded rounding distortion. The
[patch policy](../../../tools/generator/vendor/skrifa-iteration/PATCH.md#current-00101-width-tweak-source-relative-transfer)
records the source foundation, explicit project hypothesis, and limitations.

The original Roboto 14/16 px fixes remain unchanged against captured pre-tweak witnesses. Roboto 18 v changes from 20 to
37 ink pixels and w from 38 to 66; reference has 28 and 52. Literata 16 z changes from 25 to 31, compared with
reference 28. Before the terminal-curve correction below, Literata 18 v/y/z were unchanged from the earlier state of
this iteration. The increased weight, fractional phase tradeoff, and known broader join failures still require action or
an explicit agreed disposition.

The web index shows `reference → 001.01`, with the current width tweak and the agreed 14/16/18/20 px preview sizes.
Regression tests retain earlier records as data; they do not expose an earlier policy as another iteration. The
iteration remains open. No closure or follow-up decision has been agreed.

## Added diagonal coverage cases: Literata 14 px Q, x, y

On 2026-10-01, the user agreed to include these reported thin strokes in the still-open 001.01. This is scope agreement,
not acceptance of their current appearance or an iteration closure decision.

Initial Rust reference and candidate captures at weight 400 and optical size 14 confirmed identical fitted commands,
coverage, pixels, bitmap bounds, and advances for all three glyphs. These are existing problems with diagonal coverage,
rather than thinning introduced by this experiment.

| Reported case             | Reference ink pixels | Candidate ink pixels | Detected / applied / unapplied pairs |
| ------------------------- | -------------------- | -------------------- | ------------------------------------ |
| Literata 14 Q, lower tail | 40                   | 40                   | 0 / 0 / 0                            |
| Literata 14 x             | 25                   | 25                   | 0 / 0 / 0                            |
| Literata 14 y             | 26                   | 26                   | 2 / 0 / 2                            |

The Rust capture without hinting shows Q's tail is built from quadratic curves. The current detector only pairs adjacent
on-curve straight borders; its one short terminal line does not supply a tail-width pair. Addressing Q therefore needs
source-backed curved-stroke coverage. For x, trace the straight-border eligibility and pairing filters before changing
detection. For y, determine the constraint rejection reason and its relationship to axial anchors and curve joins;
detected-but-unapplied counts alone do not identify the failing guard. Retain Literata's source thick/thin contrast and
join connectivity when assessing any correction.

Captures, a reproducible Rust capture source, and a numerical summary are under
`out/diagnostics/literata-14-qxy-2026-10-01/`. Visual review continues through the existing web specimens and symbol
comparisons. These scope captures preceded the y correction below. Q and x were unresolved at that capture stage; the
coverage implementation below remains within 001.01. Optical acceptance has not been agreed.

## Terminal-curve correction: Literata y

Rust solver traces establish why Literata 14 px y remained unchanged. The curve guard fixed endpoints 18/29 in the first
pair and 32/43/44 in the second. Neither pair had hard X/Y or inter-contour anchors at those endpoints. The first system
contained identical free-coefficient rows with different residual targets; the second also contained a zero row with a
nonzero residual. Both were rejected as inconsistent before movement-limit checks.

Muse reviewed the source foundations and the correction. Its implementation attempt encountered a transport timeout; the
implementation and runtime checks continued locally. The review identified the crucial distinction between terminal
curve joins and continuous curve-to-curve junctions. Broadly releasing curve joins broke Literata k at 14 and 19 px;
those trials were discarded. A source-proximity trial was also discarded.

The current correction retries only inconsistent components. Supported terminal curves become X dependents of the
diagonal endpoint, with the far endpoint stationary. Curves on both sides of the far endpoint, one-control quadratics,
and independent ownership stay protected. Previously successful fitting is unchanged. The
[patch policy](../../../tools/generator/vendor/skrifa-iteration/PATCH.md#current-00101-terminal-curve-correction)
records the VTT XSHIFT/Shamir foundations, explicit project hypotheses, and validation limits.

| Reported case | Reference ink pixels | Candidate ink pixels | Detected / applied / unapplied pairs |
| ------------- | -------------------- | -------------------- | ------------------------------------ |
| Literata 14 y | 26                   | 27                   | 2 / 2 / 0                            |
| Literata 16 y | 30                   | 35                   | 2 / 2 / 0                            |
| Literata 18 y | 42                   | 45                   | 2 / 2 / 0                            |
| Literata 20 y | 50                   | 56                   | 2 / 2 / 0                            |

The two border slopes in each fitted pair agree within 0.01. At 16/18/20 px the heavier stroke's measured perpendicular
width exceeds the thinner stroke by more than half a pixel. At 14 px both meet the existing one-pixel axial minimum;
applying the constraints and adding one ink pixel does not establish that the perceived thinness is resolved.

The normal monochrome corpus has 30 changed glyphs relative to the preceding work within 001.01: 28 Literata and two
Source Sans 3 cases. All Roboto glyphs are unchanged. No additional alphabetic join breaks occur in the normal matrix or
the existing broader size/weight/optical-size regression sweep. The known broader failures from earlier 001.01 remain
outside this correction's scope and still block acceptance.

Q remains outside straight-border detection. The x trace identifies the missing borders: their source vertical spans are
102/106/109/110 units, below the detector's 125-unit minimum. The remaining opposing long borders overlap by −16 or 16
scaled units, below required overlaps of 61 and 67.5. Investigate a reference-founded short-border classifier next; do
not merely lower the threshold for this glyph. Q still requires curved-stroke coverage.

Captures, traces, discarded trial diffs, the final corpus diff, and Muse reports are under
`out/diagnostics/literata-14-y-solver/`. Keep the existing web comparison against reference and the agreed 14/16/18/20
px preview matrix. The y correction is ready for visual review; 001.01 remains open, with no optical acceptance or
closure agreed.

Validation completed: 100 generator tests, 421 vendored library tests, and 31 web tests passed. The library also builds
without the standard library using its existing math feature. Formatting and changed-document spelling checks pass. The
rebuilt web comparison loads all images without browser errors. Published reference reports are identical to the
preceding publication; only the candidate fitting described above changes.

## Q/x coverage and model-first evaluation

The current batch implements general short-border detection for x and a curved-slant model for Q's lower element. Source
chord length replaces the old vertical eligibility span for straight borders. Curved matching uses monotone quadratic
runs, tangent roles, opposite directions, overlap and positive-ink witnesses, selecting X or Y control from geometry.
Each supported component owns its tangent/cap dependencies and retains independent anchors. Prepared controls must first
complete upstream interpolation; a mixture of fitted extrema and raw controls is not a valid spline witness.

A pair requires an independent interior control on at least one side. The trial that admitted two two-control borders
moved Literata 17 px c's cap and broke its join. That geometry lacks this model's supported interior width variable and
is rejected generically. The correction uses no font, glyph, point or raster-row selection. The
[patch policy](../../../tools/generator/vendor/skrifa-iteration/PATCH.md#current-00101-short-and-curved-slant-coverage)
records source foundations, deliberate unsupported cases, explicit project hypotheses and bounded-fit limits.

Muse supplied curved-feature research and a read-only prototype audit. The audit highlighted ownership across axes,
monotonicity, rounding and taper limitations. Its coverage suggestions for single-control curves were not adopted:
independent endpoint tangents require more degrees of freedom. The model retains a representative width rather than
claiming uniform thickness along a curved border.

The user's further direction on 2026-10-01 establishes [model-first evaluation rules](../../evaluation.md), also
recorded in agent memory. Tiny pixel gains or losses do not by themselves imply better or worse output. Prefer
generality, robustness and sourced model logic. The Rust evaluator reports mechanical invariants separately from command
motion, connectivity, counters, coverage sensitivity and detector/solver coverage; it does not produce an acceptance
score. Source normal widths, contrast, tangents, ownership and transformed synthetic geometry remain fitter test
responsibilities. Historical records describe earlier states; do not optimize a new policy merely to match their ink
populations.

Q/x integration witnesses now check feature coverage, layout, connectivity, Q's global extrema and x's parallel borders
and source contrast across 14/16/18/20 px. Previously ink-direction assertions were removed from the width witnesses;
geometric thickness and protected-path identity remain. Passing these checks does not establish optical acceptance or
close 001.01. The agreed preview matrix and independent-reference comparison remain unchanged.

Validation completed: 109 generator tests, 425 vendored library tests and 31 web tests passed. The library also builds
without the standard library using its existing math feature. The evaluator's 24 configured cases pass their hard
invariants. Formatting and changed-document spelling checks pass.

Relative to the preceding y correction within 001.01, the normal monochrome corpus has 52 changed glyph cases: 11
Roboto, 26 Literata and 15 Source Sans 3. This is a description of the model's reach, not a quality score. There are no
additional alphabetic join breaks in the normal matrix or the isolated broader regression sweep. Gray output, advances
and layout remain unchanged, and independent-reference records match the preceding publication. Known broader blockers
from earlier 001.01 remain; this validation does not accept or close the iteration.

The web preview has been rebuilt against reference. Browser checks confirm that Q/x/y pages use the current comparison
package, load their images without errors and retain the agreed four-size matrix on the index. Final evaluation,
captures, corpus differences, source research and validation logs are under `out/diagnostics/literata-qx/`.

## Current finding classification

The user's clarification distinguishes genuine regressions requiring correction from deviations that may be allowed
after assessment. Earlier descriptions of broader "join failures" or "acceptance blockers" were stronger than the
recorded component-count evidence warrants. The observations still require disposition before closure; they do not
automatically require a fitting change. Apply the [evaluation classifications](../../evaluation.md#review-and-decision).

| Finding                                           | Current status                                      | What is established / still needed                                                                                                              |
| ------------------------------------------------- | --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Roboto 20 W, weight 300                           | Pending assessment: suspected join regression       | The captured binary image has more components than reference. Locate the separation and establish whether it damages a source-connected stroke. |
| Literata 15 W, weight 400, optical size 15        | Pending assessment: suspected join regression       | The same topology signal; source/fitted geometry and optical evidence are needed before requiring a fix.                                        |
| Source Sans 3 20 y, weight 300                    | Pending assessment: suspected join regression       | The same topology signal; determine whether the separation is a damaged join or an acceptable rendering tradeoff.                               |
| Roboto 18 v/w and Literata z weight/size behavior | Pending assessment: weight/balance deviation        | Ink differences alone do not establish excessive weight. Judge source-relative thickness, contrast and transitions across sizes.                |
| Literata Q/x/y coverage                           | Implementation complete; optical assessment pending | Feature and geometric checks pass. Resolution of the reported appearance has not been agreed.                                                   |

These outstanding cases are not currently demonstrated hard-contract failures, and none has been explicitly accepted as
an allowable deviation. Existing connectivity guards remain conservative investigation triggers. Historical fixture
names remain unchanged to retain their provenance; their labels do not establish optical damage. Fix a confirmed cause
with a general model, or record an acceptable deviation and its evidence rather than chasing pixel identity.

## Attention queue

The web index now has an Attention card backed by [attention.json](../../../tools/generator/attention.json). Its initial
15 pending cases cover Roboto 18 v/w, Literata 16 z and Literata Q/x/y at the four agreed sizes. The three broader
topology observations remain in the finding table and isolated diagnostics, outside the published review matrix. Each
mark records exact scope and a concise inspection type. The UI groups cases by type and shows only font, symbol, size
and an optional short hint such as "Lower tail" for Q. The card links to the existing symbol comparison routes;
unchanged marked output remains reviewable. Both comparison export and web build reject Attention or ordinary comparison
cases outside the active published family/size/axes/profile scope. Review descriptions are annotations, never fitting
exceptions.

Agents must maintain this queue when recording unresolved findings. An accepted deviation needs a recorded disposition;
tests alone do not remove a pending mark. See the [attention guide](../../evaluation.md#attention-card).

### Agent assessment of the current marks

The initial inspection groups described broad topics rather than the actual interventions. They are replaced following
the user's clarification. This is an agent assessment of the Rust-captured reference/current outlines; no classification
algorithm is added to rendering or evaluation code. Representative normal widths provide geometric evidence, not an
optical verdict or a whole-shape distance. Command positions identify diagnostic witnesses only.

| Cases               | Actual intervention                                                                                                                                                                                                              | Inspection question                                                                          |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Roboto 18 v/w       | All measured diagonal borders widen. v increases about 0.47–0.49 px; w about 0.33–0.54 px.                                                                                                                                       | Has thickening made the diagonals optically too heavy?                                       |
| Literata 16 z       | The diagonal widens about 0.34 px.                                                                                                                                                                                               | Does diagonal weight balance the horizontal strokes?                                         |
| Literata 14/16 Q    | The main tail widens about 0.31/0.36 px and adjoining curves move. At 14, a terminal sample changes by about −0.008 px while the inner sample stays fixed; this small taper change does not describe the main tail intervention. | Has tail thickening added excessive weight or distorted the bowl join?                       |
| Literata 16/18 x    | All four measured borders widen, about 0.21–0.33 / 0.06–0.18 px respectively.                                                                                                                                                    | Has the crossing gained excessive weight while retaining contrast?                           |
| Literata 16 y       | Both diagonals widen, about 0.38 and 0.22 px.                                                                                                                                                                                    | Has the fork/heavy stroke become optically too heavy?                                        |
| Literata 14/20 x    | Some borders narrow and others widen: approximately −0.026…+0.061 / −0.086…+0.138 px.                                                                                                                                            | Do the narrowed parts stay connected and the widened parts retain balanced contrast/weight?  |
| Literata 14/18/20 y | Mixed changes. At 14 the heavy stroke narrows about 0.34 px while the thin one widens 0.11 px; at 18/20 the heavy stroke widens 0.27/0.16 px while the thin one narrows 0.09/0.24 px.                                            | Are thin-stroke joins intact, and are the heavy stroke and thick/thin relationship balanced? |
| Literata 18/20 Q    | Tail samples are unchanged. At 18 the entire outline/raster is identical; at 20 one bowl control moves 1/64 px but the raster is identical.                                                                                      | Assess existing tail thinness, not a tail-weight change introduced here.                     |

The widths use the reported straight-border witnesses from the Rust integration tests. Q uses exact quadratic samples at
shared longitudinal coordinates across the three tail-related border pairs. These samples describe local thickness, not
uniform curved-stroke width. Captured geometry and the diagnostic calculations are recorded in
`out/diagnostics/attention-change-classification.json` and `classify-attention-widths.py`; the latter is a local
measurement script and is not used by publication or fitting. Visual acceptance remains pending. Agents must reassess
the classifications during subsequent work, rather than preserving these groups mechanically.

## Latest user assessment and permitted variation

The user accepted the current appearance except for excessive thickness in Literata 14 px Q's lower tail and x/y
terminals, and Source Sans 3 16 px x/y and w. These six cases remain in the open 001.01 correction batch; the other
reviewed Attention cases are recorded as accepted. That assessment does not dispose of unpublished diagnostic cases.

The user also explicitly permits changes to previously accepted cases and some rendering volatility. Acceptance records
the reviewed state rather than freezing geometry or pixels. General model corrections may alter those cases; the agent
must assess meaningful effects and reopen Attention for substantive concerns, without requesting another review for
every difference. Mechanical contracts remain in force. This supersedes any interpretation of earlier snapshot
preservation as a requirement to keep accepted glyphs unchanged.

## Latest optical-weight correction batch

Complete upstream weak interpolation before straight fitting so dependent terminal shifts preserve prepared spline
offsets. The earlier retry pinned raw controls before their upstream interpolation, changing terminal shape even when
its endpoint-displacement equations passed. A reflected synthetic witness with moved anchors checks the corrected
offsets. This addresses the reported Literata x/y and Source Sans x/y terminal behavior through preparation order.

Use one characteristic diagonal reference for straight and curved features, independently of their X/Y movement axis.
Q's shallow tail had inherited the bar reference solely because it was controlled in Y; the 14 px standards 90 and 51
units transfer very different ratios to the same normal thickness. Shamir's characteristic feature classes and VTT's
separate diagonal-CVT/projection selection ground the explicit shared-reference hypothesis. Curved fits now use a signed
width residual without the extra normal floor or prepared-width ratchet, while retaining the straight model's
rounding-safe dominant-axis minimum.

Source Sans w's inner borders have alternating line and two-control quadratic portions. Match these mixed roles using
the existing extent, angle, overlap, width and ink checks. Preserve line/curve tangents and longitudinal cap
coordinates, but let an exactly transverse cap's thickness follow the width equations. Guard endpoint order during
solving and after rounding. A supported mixed component may contain pure-curve pairs; pure two-control/two-control bows
remain rejected. The earlier two outer pairs are joined by four applied mixed portions. This is source-feature coverage,
not a pixel-population objective. The
[patch policy](../../../tools/generator/vendor/skrifa-iteration/PATCH.md#current-00101-optical-weight-corrections)
records the source foundations, hypotheses and protected unsupported roles.

An unrestricted fractional-width trial caused visible principal-stroke gaps in Literata x/y and Source Sans w, with
additional corpus failures. Removing the rounding margin also produced new breaks. Both trials were discarded without
weakening connectivity guards. Outline dependency constraints alone do not establish raster continuity. Muse's two
read-only consultations informed the diagnosis; source review corrected its mistaken claim that all six features were
X-controlled. A later Muse coding run produced no edits and was stopped. The primary agent completed implementation and
verification, with an independent agent reviewing reference-class and cap-role invariants.

### Agent classification against reference

This is agent assessment of Rust-captured geometry, not a classification algorithm. Representative normal widths
describe corresponding local borders, not uniform whole-stroke thickness or an optical score.

| Case             | Actual intervention                                                                                                                                                               | Attention inspection                     |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| Literata 14 Q    | Main tail sample narrows about 0.40 px, an adjoining terminal sample widens about 0.12 px, and an inner sample narrows about 0.27 px.                                             | Mixed: check joins and weight            |
| Literata 14 x    | Thin diagonal samples widen about 0.05–0.08 px; heavy samples change about ±0.01 px. Terminal controls retain prepared offsets. The final 1-bit bitmap is identical to reference. | Unchanged: check terminal weight         |
| Literata 14 y    | Heavy diagonal narrows about 0.35 px; thin diagonal widens about 0.09 px. Terminal preparation changes shape and placement.                                                       | Mixed: check joins and weight            |
| Source Sans 16 w | Outer and inner chord samples narrow about 0.05–0.27 px. Mixed fitting also controls curved inner portions and cap thickness.                                                     | Thinning: check joins; inner diagonals   |
| Source Sans 16 x | Width samples change about 0.003 px; the substantive correction is terminal placement from coherent preparation.                                                                  | Placement: check terminals               |
| Source Sans 16 y | Main samples narrow about 0.18–0.25 px, with terminal placement changes. One unsupported pair remains unapplied.                                                                  | Thinning: check joins; fork and terminal |

The six corrected cases remain pending optical assessment in Attention, with concise inspection groups and specific
optional hints. Other reviewed marks retain their recorded acceptance. The 624-case alphabetic diagnostic slice has 145
changed fitted outlines versus the preceding reviewed state: 40 Roboto, 52 Literata and 53 Source Sans cases. This
describes reach, not deterioration. Agent assessment and geometric/mechanical checks found no new meaningful concern
requiring every changed accepted case to return to Attention. Their permitted variation does not imply new user approval
of each rendering or acceptance of the six pending cases.

Synthetic tests cover mixed-role rotation/reflection with unequal axis standards, preserved tangents and longitudinal
coordinates, cap order, bounded motion and atomic anchor conflicts. Integration checks preserve disabled parity, layout,
gray output, the protected c/k witnesses and normal/broader connectivity guards. The older snapshot-identity assertion
for accepted Roboto fixes now checks coverage, connectivity, layout and outline structure. Exact identity remains for
explicitly untouched paths. Diagnostics, discarded trials, source consultations and captures are retained under
`out/diagnostics/optical-weight-correction/`. Preview scope and iteration identity remain unchanged; 001.01 is open.

Validation completed: 114 generator tests, 428 vendored library tests and 35 web tests passed. The evaluator's 24
configured cases pass their hard invariants; the library also builds without the standard library using its math
feature. Formatting and changed-document spelling checks pass. The rebuilt browser preview shows six Attention cases in
four inspection groups, retains the agreed three-family/four-size matrix, loads all comparison images and reports no
browser errors. Independent-reference records and candidate gray records are identical to the preceding publication.

Attention clarification: Literata 14 lowercase x has 16 changed fitted commands and changed coverage against reference,
but identical final 1-bit pixels, bitmap placement, dimensions and advance. Its previous "Thickening" label described
subpixel geometry and misleadingly implied a visible weight change. The mark now asks "Unchanged: check terminal weight"
because the user's terminal-weight concern remains unresolved. This is an existing appearance to assess, not evidence of
a visible regression against reference. The ordinary changed-symbol list correctly omits an identical bitmap.
