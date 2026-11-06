# Contextual spacing and texture healing

<!-- cspell:words scanlines FontForge AutoWidth AutoKern rint Monaspace Hu pnum tnum titlecase CounterSpace Cozens tensorfont nonfinite yinyangfit yinyang electricbubble fullfield fullwindow TFJS dtypes dtype thresholding ppem predeclared retuned reweighting multiscale RGBA argmin Mises directionalized heldout Schwarz -->

**Status: isolated optical-spacing experiment; texture healing deferred.** The
[experiment commands](../../../experiments/contextual_spacing/README.md) capture source and produced geometry and
compare metric placement, Hu/Hersch optical spacing and retained CounterSpace/filtered-wall/FontForge comparisons. The
[spacing guide](../../guides/text-layout/spacing-models.md) describes current behavior;
[revision 001.03](../../revisions/001/03-spacing-kerning.md#pair-spacing-and-kerning) records assessment and adoption.

## Purpose and scope

Improve reading rhythm and the distribution of ink and whitespace while preserving the typeface's identity. The system
should support fonts whose source files supply ordinary glyphs without contextual healing alternates.

The current work is placement-only:

- **Optical spacing** places unchanged glyph forms toward shared targets calibrated from designed reference pairs,
  aiming for coherent ink/paper balance across eligible pair classes.
- **Source-preserving compensation** retains each source pair's estimated separation after fitting and rendering. It
  remains a comparison method rather than the optical-balance target.

Equal estimated separation does not require equal bounding-box gaps: facing curves, diagonals and open spaces affect the
estimate. Whole-pixel placement limits equality. A shared target also does not establish perceived balance by itself;
native-size assessment must test the estimator and the chosen overall density.

Texture healing, which can redistribute ink or change forms contextually, is deferred. Its lifecycle and research gate
below describe future work and are outside the current implementation scope.

Visual weight belongs to glyph production: the policy that selects the font instance, fits shapes and rasterizes them.
Healing variants use that same policy and retain the selected weight, contrast and character identity. The generated
result consists of glyph forms, placements and context rules. Future export formats follow this model.

## Sources and candidate methods

The [target research](../../references/optical-pair-spacing-target.md) compares shared-target methods and their
limitations, including reference-pair density calibration and filtered measurement walls.

| Source                                                                                                                                                                                      | Contribution                                                                                                                                                                              |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [FreeType metrics](https://freetype.org/freetype2/docs/glyphs/glyphs-3.html) and [kerning](https://freetype.org/freetype2/docs/glyphs/glyphs-4.html)                                        | Distinguish images, bearings, advances and pair positioning; explain interactions between neighboring adjustments.                                                                        |
| [FontForge AutoKern](https://fontforge.org/docs/ui/dialogs/autowidth.html)                                                                                                                  | Estimate optical separation from facing outline edges and adjust pair placement to a requested shared separation.                                                                         |
| [Hersch et al., 1995](https://lspwww.epfl.ch/publications/typography/ptgogf_95.pdf), pp. 85–88, and [Hu, 1998](https://lspwww.epfl.ch/publications/typography/sopfbsc.pdf), §4.4, pp. 88–91 | Estimate perceived space using transformed outlines or filtered image boundaries, including open cavities such as `c`. These are alternatives if the first estimator proves insufficient. |
| [Monaspace](https://monaspace.githubnext.com/#texture-healing) and its [technical guide](https://github.com/githubnext/monaspace/blob/main/docs/Texture%20Healing.md)                       | Demonstrate contextual redistribution with designed alternate glyphs while preserving the monospace grid. Automatic synthesis for ordinary fonts remains our research question.           |
| [Hersch §§5–6](../../references/papers/1993-hersch/paper.md), [Shamir §3](../../references/papers/2003-shamir/paper.md) and [Hobby](../../references/papers/1993-hobby/paper.md)            | Ground geometric relationships, feature intent and constrained fitting.                                                                                                                   |

Measuring delivered bitmap boundaries with FontForge's outline estimator is a project adaptation. The shared-target
mechanism is established; its limitations motivate the filtered-wall candidate below. Perceived balance requires the
experiments below. Optical assessment follows the [evaluation rules](../../evaluation.md).

## Text units and controls

Initial experiments use the current
[supported scalar repertoire](../../../crates/generator/API.md#supported-input-and-output): lookup resolves each
supported character to one source glyph at the selected axes. Each generated variant retains that character and source
glyph identity, plus its own variant identity. This lineage supplies its source metrics and target. A richer shaping
adapter would define its spacing units and source mapping before extending this scope.

For these experiments, a text span is a run of supported characters separated by ordinary spaces (`U+0020`) or explicit
line breaks. Punctuation stays inside its span. The proposed controls are:

| Control                          | Meaning                                                                                                          |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Source kerning strength, `k`     | Scale source kerning in metric placement and the source-preserving comparison. Full optical balance replaces it. |
| Optical correction strength, `o` | Blend current metric placement (`0`) toward the selected optical method (`1`).                                   |
| Target separation                | Font-calibrated by pair class; a configured em target applies only to the fixed-target diagnostic.               |
| Letter spacing                   | Add separation between adjacent glyphs inside a span.                                                            |
| Word spacing                     | Add separation to each ordinary space advance, including repeated spaces.                                        |

Letter spacing applies at internal span gaps; span ends retain their ordinary terminal advance. Explicit line breaks
reset context. Richer word segmentation, other separators, control ranges and migration from today's uniform tracking
are integration decisions. Existing saved tracking keeps the policy described in the spacing guide until that migration
is agreed.

## Placement and ownership

The spacing module resolves automatic pair placement. The placement stage owns the deliberate user offsets:

```text
automatic_adjustment = signed_pixel_round(blend(metric_adjustment(k), optical_adjustment(k), o))
resolved_step = finalized_advance_left + automatic_adjustment + user_offset
```

The metric alternative follows the existing source-kerning and bearing-compensation policy, including its quantization.
The final blend rounds the signed adjustment. Deliberate offsets are resolved to the chosen output grid once by the
placement stage. With optical correction and healing disabled and deliberate offsets zero, the result reproduces the
current metric policy at the existing source-kerning endpoints. Continuous strengths can produce plateaus in whole-pixel
output.

For a span gap, `user_offset` is letter spacing. A space receives the word-spacing addition in its advance. The
placement stage applies each offset once. Healing reads the resulting available room and evaluates candidates against
the requested relationship, including that offset.

Drawing, measurement and wrapping consume the same resolved forms and positions. Fixed-grid experiments preserve
required cell advances; source-tabular digit pairs retain metric placement when tabular preservation is requested.
Initial fixed-grid controls use neutral deliberate spacing; combined spacing controls are an integration decision.

## Glyph production and contextual healing

The experimental lifecycle has a finite candidate set:

1. **Produce originals.** Glyph production returns the original forms, metrics and actual output geometry. Analysis
   records their source relationships, facing edges, counters and relevant stroke relationships.
2. **Propose candidates.** Healing derives candidates from those originals and a declared context. Every proposal names
   its source glyph, coordinate system and application stage. Shape changes enter glyph production before fitting;
   ink-position changes use the output-grid policy. The candidate set is fixed before selection.
3. **Produce and measure candidates.** Glyph production applies the same appearance policy to every candidate. Analysis
   measures the forms actually delivered, including their resulting metrics and boundaries.
4. **Resolve the context.** The resolver selects compatible candidates and automatic placements using these
   measurements. It checks dependent changes as a group. An invalid group falls back to its original forms and metric
   placement, with the reason recorded. Original forms remain candidates throughout selection.
5. **Finalize placement.** The placement stage adds the deliberate offsets and returns the resolved result. Caches
   retain the selected variant identities and the measurements used to place them.

In `lmi`, for example, the middle `m` may receive room from both sides. Resolution must choose one compatible form for
that occurrence and account for the space assigned to each neighbor.

The [healing research gate](#healing-research-gate) defines the experimental policy. During resolution, identical inputs
within the declared context select the same forms. Pair-only optical placement depends only on the two glyphs in the
pair.

Initial healing specimens use explicit line breaks and unwrapped spans. Placement-only experiments exercise wrapping.
Combining healing with wrapping requires a finite line-boundary policy that resolves the effect of a break on selected
forms and line width before integration.

## Optical-spacing experiment

**Question:** can unchanged glyph forms placed toward font-calibrated separation targets produce coherent reading rhythm
and ink/paper balance? The experiment retains glyph images, bitmap offsets and finalized advances, changing only
relative origins. Source-preserving compensation and a fixed-target diagnostic supply separate comparison controls.

### Hu/Hersch delivered-bitmap candidate

The selected `hu_hersch` candidate follows [Hu §4.4](https://lspwww.epfl.ch/publications/typography/sopfbsc.pdf) and
[Hersch et al., pp. 85–88](https://lspwww.epfl.ch/publications/typography/ptgogf_95.pdf), including the depth controls
and reference relationships omitted from the earlier filtered-wall comparison. The
[reassessment](../../references/optical-spacing-perception-reassessment.md) distinguishes those omissions from
established causes of the reported optical failures. CounterSpace remains a comparison; its development is paused.

Analysis uses unchanged delivered binary pixel cells, tight nonzero bounds and common physical x/y units. Reference
placement uses finalized advances plus full maintained metric pair adjustments, independently of the runtime kerning
slider. Lowercase and uppercase body windows come from delivered `n` and `H` bounds. Mixed-case window endpoints and
ideal areas are averaged separately, retaining Hersch's mean height rather than the earlier union window. The
body-window choice is a declared adaptation where the papers leave arbitrary-font bitmap handling unspecified.

The wall construction follows the additional detail in
[Hersch and Betrisey, US5768490A](https://patents.google.com/patent/US5768490A/en), transformations A–D. Concavity
filtering must preserve convex exterior portions. Aperture depth uses the most exterior cavity lip and a vertical
cutoff, with a connector to an inset second lip; a parallel offset from a convex-hull chord is different. The raster
realization and its remaining approximations belong to the [source note](../../references/hu-hersch-delivered-model.md).

The patent supplies relative depth **0.21** and global height factor **0.25**. These published parameters replace the
previous fit against `cu`, `ov`, `vu`, whose zero aperture factor closed cavities. There is no per-font coefficient
optimizer. Delivered reference geometry still calibrates density: every eligible pair uses the same transformed-wall
measurement as its `nn` or `HH` reference, without switching to a separate stem/curve extremum measurement. Mixed-case
areas and heights remain separately averaged. The patent's generic construction grounds this path; the six-class
shortcut described in the 1995 paper is not used by this candidate. ASCII `00` remains an experimental numeral
extension. Missing reference geometry and unsupported categories retain metric placement.

The solver applies the full continuous optical correction to supported pairs, rounds the adjustment to whole pixels and
applies the existing separately disclosed full-bitmap clearance bound; unsupported pairs retain Source. Tracking remains
a subsequent deliberate offset. Diagnostics retain filtered area, equivalent mean gap, reference mechanism, selected
depth factors, ideal/rounded/emitted steps and clearance residuals. The old comparison methods retain their calculations
and the maintained renderer remains outside this experiment.

Reported pairs remain optical assessment cases, including `cc`, `zz`, `ff`, `bd`/`du`, `jo`, `yd`, `le`, `pi`, `ip`,
`te`, `tp`, `OE`, `OR` and numerals. Assess those failures alongside unseen words, other families and neighboring sizes.
Correct depth algebra and code tests do not establish perceived balance. Promote the candidate only with its unresolved
optical findings stated alongside the comparison.

### Source-designed shared density candidate

`hu_source_calibrated` keeps a shared target while moving the density anchor from finalized bitmap metrics to the font's
source-designed reference spacing. The `nn`/`HH` principle comes from
[Hersch and Betrisey's ideal optical space](https://patents.google.com/patent/US5768490A/en); using continuous source
references with delivered candidate cells is an explicit project adaptation, not a claim of author-code parity.

For each reference class, measure source outlines at full source advance and full source pair kerning:

```text
shared_target = source_reference_step + source_reference_filtered_wall_offset
required_delivered_step = shared_target - delivered_pair_filtered_wall_offset
```

The target is independent of requested text and the runtime kerning slider. Mixed classes retain separate means of
reference areas and heights; ASCII `00` remains experimental. Source and delivered measurements use the same retained
physical window and published depth coefficients. The window still comes from delivered reference bounds, so the
candidate removes bitmap-metric density bias without claiming complete independence from reference rasterization.
Missing, unsupported, empty, unshared or non-positive source references abstain with provenance; no bitmap-density or
fixed-em fallback applies.

Delivered cells still determine candidate whitespace and full-bitmap clearance. The calibrated target enters the
continuous solve before the existing signed rounding and clearance guard. There is no hard-coded negative tracking,
corpus-average fit or glyph-specific adjustment. Source metrics retain their captured 1/64 px precision.

`hu_hersch` remains the raster-reference control. Native inspection must assess the new shared target's overall density
as well as pair uniformity. A designed `nn` reference need not equal the average spacing of natural text, and integer
placement or clearance can prevent reaching its target. Assess word separation after letter density; this candidate does
not automatically calibrate word spacing.

### Fixed-alphabet density experiment

This experiment retains the generic Hu/Hersch wall measurement while separating relative pair balance from overall
density. The filtered-wall foundation remains
[Hu section 4.4](https://lspwww.epfl.ch/publications/typography/sopfbsc.pdf) and
[Hersch's generic ideal-space solve](https://patents.google.com/patent/US5768490A/en). Conserving the source mean origin
step over a declared alphabet is an explicit project constraint grounded in source advances and pair positioning; the
normalization below is a project adaptation, not a formula prescribed by those papers.

Calibration uses complete fixed ASCII repertoires: `a–z`, `A–Z` and experimental `0–9`. Each same-case class uses its
full ordered Cartesian pair set, including repeated glyphs. Mixed case uses both ordered uppercase/lowercase products in
one common window. Missing or invalid calibration glyphs make that class unavailable; the captured or requested text
must not silently choose a smaller alphabet. Source steps always include full source pair kerning, independent of the
runtime kerning slider.

For source step `d_source` and wall intercept `c`, compare two targets over the fixed calibration pair set:

```text
source_alphabet_target = mean(d_source + c_source)
source_origin_target = mean(d_source + c_candidate)
continuous_candidate_step(pair) = target - c_candidate(pair)
```

The first arm isolates replacement of the single `nn`/`HH` density anchor. The second conserves the unrounded mean
origin step on its calibration domain while retaining the same relative generic wall balancing. It does not conserve
every word, arbitrary text distributions or the final rounded/clearance-constrained mean. These limitations remain
visible in diagnostics. Neither arm uses a fitted target offset, current-text average or negative tracking default.

The isolated probe first verifies that both arms coincide on source outlines and conserve their calibration-domain mean
there. Delivered bitmap cells then supply candidate walls, with fitted outlines as a separate measurement control;
actual bitmap cells supply clearance in either case. Existing blend, signed adjustment rounding, strict full-bitmap
clearance, fixed-pitch/tabular safeguards and optical-zero identity remain unchanged. Residuals introduced by rounding
and clearance, and any infeasible source-width budget, must be reported separately from continuous conservation.

Native assessment uses the four-family 16 px scope, all seven presets and the normal browser-font reference. Calibration
inputs remain fixed while held-out text is evaluated. Equal mean origin steps or equal wall scores do not establish
perceived balance. A supported probe may proceed to separately named comparison candidates; existing modes, renderer
settings and previous artifacts remain controls until optical assessment.

#### Touching-clearance candidate

The user permits glyph pixels to touch. `hu_density_conserved_touch` therefore retains the density target, wall
measurement and signed rounding of `hu_density_conserved`, but replaces its strict no-touch floor with a same-row
non-overlap bound. With row endpoints expressed as pixel-cell edges:

```text
minimum_step = max(right_edge_left_glyph[row] - left_edge_right_glyph[row])
```

Only rows occupied by both glyphs constrain this bound; without shared rows there is no bound. The condition keeps the
right glyph's ink beyond the left glyph's ink on shared rows, allowing face and corner contact while forbidding
occupied-cell overlap. It deliberately excludes putting a glyph inside another's counter. Adjacent-row overhangs and
vertical edge contact are permitted; subtracting one pixel from the old adjacent-row floor would impose a different,
more restrictive policy.

This is a declared Mono adaptation of
[Hu's minimum-space safeguard](https://lspwww.epfl.ch/publications/typography/sopfbsc.pdf), not a claim of author-code
parity. The [patent's continuous contour clearance](https://patents.google.com/patent/US5768490A/en) does not require a
blank pixel column after binary scan conversion. Contact is a diagnostic, not an automatic optical failure;
occupied-cell overlap remains a hard failure for eligible automatic placements. Optical-zero, fixed-pitch and tabular
safeguards retain metric placement, and deliberate tracking remains a later user offset.

The strict model remains a separate control. Candidate identities and pair metadata name the clearance policy; target
calibration stays independent of that policy. Compare unchanged bitmaps across the existing four fonts and seven presets
with zero tracking. This amendment can release clearance-limited pairs such as `al`; pairs already selected by the wall
model and rounding, including `ri` and `ig`, need separate assessment.

#### Fitted-wall measurement candidate

`hu_fitted_density_conserved_touch` tests whether measuring the retained grid-fitted outlines reduces the influence of
binary cell staircases on the Hu/Hersch walls. It adapts the
[outline-based ideal-space construction](https://patents.google.com/patent/US5768490A/en); applying it to this
renderer's fitted commands while displaying binary cells is a project experiment, not independent-reference parity. The
control is the bitmap-measured `hu_density_conserved_touch` candidate.

The model uses `produced_commands` in their existing pixel coordinates, with scale one, and the same delivered
`n`/`H`/`0` body windows, wall parameters and fixed calibration domains. It recalculates `mean(d_source + c_fitted)`
using the unchanged source-origin calibration formula; it does not reuse the bitmap target's numerical value. Shared
targets remain independent of the reading text and runtime kerning control. Source geometry and source-relative
objectives do not replace this shared-target rule.

Only measurement changes. Both columns display the identical captured bitmaps and apply the same full-bitmap no-overlap
bound, signed adjustment rounding, metric blending and placement safeguards. No outline is rasterized again. Missing or
invalid fitted measurement geometry retains the existing unavailable-calibration fallback; it must not silently use
bitmap walls. Model caches, metadata and analysis identities distinguish measurement geometry from clearance geometry.

Assess the four families at 16 px across all seven presets, against the normal browser reference. In Literata, `se` and
`ri` are expected to tighten while `al` retains its touching-permitted step; `en` and `os` remain unresolved. These are
placement predictions, not proof of equal perception. In particular, a narrower `ri` does not make its actual stem gap
equal to `ig`. This candidate does not add centered source-relative calibration or change integer rounding.

#### Construction-order candidate

`hu_fitted_full_density_conserved_touch` implements the
[source-backed construction-order correction](../../references/hu-hersch-construction-order.md) as a separate opt-in
candidate. Its control is `hu_fitted_density_conserved_touch`; neither changes the maintained renderer or glyph images.
The complete fitted outline supplies the construction domain. The body midpoint grid is extended by whole sample
intervals to include full ink bounds, retaining its original samples exactly. After the bounded 45-degree stage, cavity
supports are found again on the transformed wall. Aperture and global depth caps are applied before the arrays are
cropped to the declared class measurement window. The global cap still uses class body height, not full ink height.

The target is recalculated over the same complete fixed alphabets using the existing source-origin density rule. Signed
adjustment rounding, actual bitmap overlap protection, metric blending, tracking and preservation safeguards are
unchanged. Work limits fail explicitly rather than substituting cropped construction. Cached profiles and model metadata
distinguish the construction policy and its source/fitted measurement identity.

This remains a bounded-bay sampled adaptation, not a recovery of original tangent code or a published rule for our fixed
integration windows. Assess complete texts at zero tracking across the retained four fonts and seven presets. The audit
predicts Literata `ca` and `en` tighten through a calibration change, while `al` stays at 8 px and `nx`/`os` remain
unresolved. Those outcomes do not establish optical acceptance or justify changing the target policy.

#### Complete-cell geometry assessment

The isolated complete-cell ablation compares the full fitted-outline candidate above with exact rectangles covering the
delivered binary ink. Both arms construct complete walls, apply the same B/C/D transformations with post-B cavity
supports, and integrate the same class body window. Each geometry recalibrates its own fixed-alphabet source-origin
target; transplanting a filtered-outline target onto raw bitmap gaps is excluded. The existing signed rounding,
full-bitmap overlap bound and metric fallbacks remain unchanged.

This tests measurement representation, not a new perceptual objective. The two arms display identical captured glyphs at
full strength and zero tracking, retaining all four families and seven presets for optional exploration. Assessment
starts with one short Literata lowercase passage at native size, with enlarged inspection available. The user gives
feedback in chat rather than completing ratings for every sample. A/B meanings stay fixed across selections so chat
feedback remains unambiguous; method disclosure is optional. This informal assessment replaces the earlier
counterbalanced repeated-rating protocol and does not claim its order-effect controls. Retain natural wrapping and
distinguish overall preference, local concerns and uncertainty in the discussion. A repeatable preference supports
further assessment, not automatic promotion. If representation replacement provides no repeatable benefit, the
unresolved pair-dependent objective needs separate research.

#### TypeFacet feasibility experiment

The
[TypeFacet audit](../../references/yinyang-geometric-alternatives.md#typefacet-autokern-strongest-limited-experiment)
identifies an implemented outline-inflation and pair-intrusion selector. First run the pinned application and bundled
dependencies in its original Python 2 runtime on declared UFO fixtures, retaining full profile and output-kerning
evidence. Preserve upstream rounding, integer division and missing-row behavior; compatibility edits cannot silently
become reference behavior. Check curves, disjoint vertical ranges, components and coordinate scaling before a port.

Then compare continuous source contours and exact delivered-cell rectangles for frozen Literata 400/16, `opsz=16`, in
design units. Freeze one author-documented parameter configuration before examining held-out problem pairs and record
its residuals against the author's straight/curve reference families. This is an uncalibrated diagnostic configuration,
not an automatic font fitter. Keep `rd`, `ri`, `ca`, `os`, `bd`, `du`, `ff`, `cc` and `zz` outside parameter selection.
No parameter or coordinate search may select settings by improvements to those pairs.

The displayed glyphs, source metrics and existing control remain fixed. A cell adapter must retain units, bearings and
baseline, apply the existing whole-pixel placement policy and independently check occupied-cell non-overlap and facing
wall order. Record reference errors, unit sensitivity and source-relative width drift before deciding whether any
reading preview is justified. Reference fidelity is a mechanical gate, not optical acceptance. If meaningful choices
require an unspecified automatic calibration or unstable coordinate policy, report that limit rather than publishing a
new default or a manually tightened comparison.

The next calibration probe uses the manual's endpoint (`TT tt fT rf`), body (`NN nn`), intrusion (`AA OO oo`) and
overhang (`VA Ta LT`) families. A single global parameter vector fits these families with equal family weight; no
reported problem pair participates. Direct cell calibration uses fixed full maintained metric steps on the captured
reference pairs. A separate source-outline fit uses full source-designed steps to diagnose transfer. This least-squares
automation is a project hypothesis adapting the manual's reference-guided tuning and
[CounterSpace's squared-error prototype fitting](https://github.com/simoncozens/CounterSpace/blob/01b33477225eb5fc7bedf93a090b5cd7dd0c812b/CounterSpace.py#L224-L278),
not an upstream TypeFacet automatic fitter. The targets and equal family weighting are project choices. Neither
objective includes the preview passage, held-out pairs, rounding outcomes or alphabet width drift.

Freeze the bounded grid and refinement rule before fitting. Keep precision and tracking fixed; do not use coordinate
scale or per-category rules as fitting variables. Retain all evaluated reference residuals, grid boundaries and
near-optimal alternatives before examining held-out results. Test reference-fit sensitivity to omitted families,
precision and doubled coordinates. Reproduce selected settings through the full original UFO path. Only a stable
calibration with understood reference tradeoffs justifies a short reading comparison; otherwise record the ambiguity
without choosing parameters by desirable held-out pixel changes.

#### TypeFacet density-controlled comparison

The next isolated reading test separates TypeFacet's redistribution from its absolute density. Freeze the direct-cell
fit from the preceding calibration: minimum .055 em, maximum .17 em, intrusion .05625 em, extrema overlap .0375 em and
precision .005 em. Reuse the verified original output and unchanged Literata 400/16 cells; do not fit again.

For the complete fixed ASCII lowercase Cartesian domain `D` (676 pairs), compute `shift = mean_D(source designed step) -
mean_D(raw TypeFacet step)` and add that shift to every raw step before retained signed adjustment rounding and the
bitmap non-overlap safeguard. This reuses the
[fixed-alphabet project constraint](../../references/fixed-alphabet-spacing-density.md), not an upstream TypeFacet
formula. Preview text and user tracking do not enter normalization. Report rounding and safeguard drift separately; the
continuous identity does not promise equal word widths or an exact emitted mean. The upstream minimum distance
participates in the raw selector but is not a hard clearance rule after centering; touching is permitted, with
occupied-cell overlap and same-row wall inversion still forbidden.

Compare one short Literata passage against the unchanged full fitted-outline control B. The candidate changes only ASCII
lowercase pairs; all other pairs retain B. Preserve all seven presets for optional exploration, zoom and subtle
varying-pair underlines, with feedback in chat. This is an explicitly bounded single-font test, not a replacement for
the earlier four-font comparison. Keep A as this candidate and B as the preceding control throughout. Retain raw,
normalized, rounded and emitted steps, verify B's table/glyph identity against its retained page, and independently
check all candidate outcomes and Python/browser placements. Refitting or broader adoption requires a repeatable reading
benefit; pending `ca`, `nx` and other local concerns do not become glyph exceptions.

#### TypeFacet constrained integer experiment

After the `gs`/`hi` investigation, remove post-solve normalization entirely. Reuse the frozen Literata cells and pinned
original Python 2 profile/predicate implementation. Test zero additional minimum distance, zero tracking, .1 em extrema
overlap and .005 em precision. The two fitted variables are normal distance and intrusion tolerance, using the manual's
parameter roles. This is a project adaptation of its minimum-admissible-advance selector to integer pixels, not upstream
output parity or a change to the maintained rounding policy.

For each pair, enumerate a bounded interval of integer origins. Require the original zero-radius minimum profile and
extrema-overlap bounds, both original intrusion predicates (full and ascender-restricted), plus actual bitmap
non-overlap and same-row wall order. Select the smallest admissible integer, without assuming predicate monotonicity or
applying a later correction. Retain every tested candidate and refusal; a missing feasible position fails the parameter
trial. Placement quantization moves to the pixel domain: compare the unrounded zero-radius profile contact rather than
rounding it in font units first. At 1000 UPM/16 px a one-pixel contact is 62.5 font units; rounding that to 63 would
introduce an extra pixel in a strict integer search. Retain upstream profile construction and disclose its own
coordinate rounding.

Fit only lowercase, with source-designed `tt rf` endpoint, `nn` body and `oo` intrusion reference steps. Constrain the
emitted mean over all 676 fixed lowercase pairs to the source mean within one retained source-metric quantum (1/64 px);
this is a calibration tolerance, not an optical tolerance. Minimize equal-family reference error within that band, and
report the closest attainable density if no trial meets it. `gs`, `hi` and the other reported pairs do not enter the
local reference loss. The fixed alphabet density constraint still uses its complete declared domain, independent of
prose.

Freeze the bounded grid and two local refinement steps before evaluation. Record all settings, feasibility, density,
reference residuals and near-equal fits. Check emitted integer predicates independently, including all smaller
candidates, and verify unchanged captured geometry. Use analytic fixtures and a cold original-code replay. No
post-rounding shift, guard displacement, letter exception or rounding-threshold search is allowed. Prepare another short
A/B reading page only if feasibility and held-out assessment justify it; retain B and all prior pages otherwise.

#### Interchangeable kerning methods

The main Glypherie editor selects a method independently of fitting, rasterization and deliberate tracking. Preserve its
current source-kerning and fitted-bearing behavior as the default. A maintained Rust method module resolves completed
pair adjustments after bitmap metric finalization and before tracking or shared layout. Native preview, WASM and
Playdate export use that same calculation. The existing layout engine knows neither method parameters nor profile
construction.

Use closed, typed method selection. Each adapter owns preparation, measurement units, calibration and placement
selection; its result is a completed replacement table. An explicit zero removes a preceding source adjustment, while an
abstention retains it. Compute the complete result before applying any replacements. TypeFacet's smallest-admissible
search, Hu/Hersch's analytic wall-gap solve and CounterSpace's bounded score search do not share a universal scoring,
rounding, blending or clearance interface. Share geometry and feasibility helpers only where their meanings coincide.

Plan analysis before capture. Keep the requested output repertoire and pair-shaping domain separate from auxiliary
calibration captures, using the same font instance and rendering pipeline. A fixed calibration alphabet cannot be chosen
from the reading text or added to the exported strike. In particular, auxiliary Latin references must not create
cross-script pairs absent from the request. Calibration uses its prescribed full source kerning independently of the
runtime source-kerning setting. Missing references retain Source for the affected class rather than silently choosing a
different density target.

The TypeFacet core consumes closed line, quadratic and cubic contours in font units and returns prepared pair
constraints plus an admissibility predicate for a requested origin. It has no bitmap, output-depth, Unicode eligibility,
advance, size or placement-grid dependency. Preserve the pinned
[profile and intrusion implementation](https://github.com/charlesmchen/typefacet/blob/8c6db26d0c599ece16f3704696811275120a4044/python/src-main/autokern/Autokern.py),
including curve offsets, orientation, endpoint circles, 16-part curve sampling, the effective one-decimal geometry
rounding override and full/ascender predicates. Independent original curve captures own parity; profile agreement is
separate from final pixel placement.

TypeFacet's geometry adapters provide the real variation. Mono supplies exact delivered binary row-run rectangles; Gray
supplies its own fitted outline commands before coverage quantization. Gamma, output depth and coverage threshold never
define Gray analysis geometry, and no second rasterization is needed. Normalize only quadratic curves proved exactly
equal to their endpoint line segment, with all controls collinear and inside that segment. The
[Bezier endpoint and convex-hull properties](https://people.eecs.ku.edu/~jrmiller/Courses/IntroToCurvesAndSurfaces/BezierCurveProperties.html)
justify this analysis-only representation change. It handles line-like curves created by fitting, for which the original
quadratic offset fails on parallel tangents. Use exact dyadic arithmetic without a geometric tolerance; retain curved,
overshooting and already supported cubic representations. Rendered commands and pixels are unchanged.

TypeFacet's placement adapter selects the smallest admissible origin on the existing whole-pixel bitmap layout grid, for
both Mono and Gray. Minimum-distance profile inflation and the horizontal extrema overlap cap are manual parameters,
defaulting to zero and .1 em respectively; .005 em profile precision stays fixed. There is no later normalization, blend
or guard displacement. Binary-cell feasibility additionally forbids occupied-cell overlap and same-row wall inversion
while allowing face/corner contact. Gray uses geometric profile bounds, without applying a binary-pixel rule to
antialiased coverage. Tracking remains a later deliberate layout setting.

TypeFacet eligibility belongs to placement, with no ASCII or case filter. Use captured scalars already admitted by the
shared shaping contract; whitespace, empty geometry, fixed-pitch fonts and source-tabular digit pairs retain the current
method. Keep work and allocation explicitly bounded. The method remains selectable across all explicit pipeline output
depths; historical renderer roles retain their existing entry contracts.

TypeFacet controls are manual normal distance, intrusion tolerance, minimum clearance and maximum horizontal extrema
overlap, initialized from the
[author's parameter guidance](https://charlesmchen.github.io/typefacet/topics/autokern/typefacet-autokern-manual.html).
Minimum clearance supplies the original minimum-distance inflated profile; the maximum overlap parameter supplies the
original extrema bound. Minimum clearance cannot exceed normal distance. Historical two-parameter settings inherit zero
minimum clearance and .1 em maximum overlap, preserving their calculation. These parameters do not bypass the
independent delivered-cell feasibility check or replace the original powered intrusion balance. The Literata fit and its
89 retained tuples remain experiment evidence, not an automatic fitter or universal runtime preset. Other methods enter
through their own adapters and retain their own geometry, target and feasibility policies.

The explicit Hu/Hersch adapter adopts `hu_fitted_full_density_conserved_touch` from the isolated experiment. It
constructs the cavity-limited wall on the complete fitted outline before measuring the class body window. The
[construction-order note](../../references/hu-hersch-construction-order.md) and
[US5768490A](https://patents.google.com/patent/US5768490A/en) ground concavity-only 45-degree filtering, aperture depth
and global depth of class height. The two depth controls default to the published `.21` and `.25`; each accepts finite
`0..=1` as a fraction of its geometric basis (cavity aperture height, class body height). This range is a project
control bound, not a published limit or a guarantee of horizontal containment. Both the candidate walls and the density
calibration use the selected values; class body height remains the global cap basis. The declared sampling policy stays
fixed; this adapter adds no per-font optimizer, work-limit knobs or glyph exceptions. The complete fixed alphabet's mean
source origin step anchors the analytic solve. Density conservation is the project's constraint, not a claim that Hu
prescribes that calibration. Lowercase, uppercase, digits and the two ordered mixed-case products have separate declared
domains. Unavailable domains and unsupported classes retain Source. Previous local spacing concerns remain pending
optical assessment; port fidelity cannot resolve them.

The full Hu/Hersch correction always applies to supported pairs; there is no Source blend. Retired `strength` values in
saved settings and URLs are rejected at the admission boundary, so no saved blend can load as new defaults. Depth
choices change targets and walls but no advances, glyph images or bearing offsets.

Mono retains the experiment's tight delivered `n`/`H`/`0` body windows. Gray derives those windows from fitted reference
outlines, making its analysis independent of gamma and coverage quantization. This Gray adaptation has separate
mechanical and optical assessment scope. Latin cased scalars can use the corresponding fixed ASCII class calibration;
that does not establish a reference density for other scripts. Proportional ASCII digits retain their experimental
class, while source-tabular digits remain protected.

The FontForge-derived adapter is explicitly source-relative. Preserve the pinned
[AutoKern envelope estimator](https://github.com/fontforge/fontforge/blob/c41bdb922285f35defd1e1385adfd13bde1ab32a/fontforge/autowidth2.c)
in font units, including band flooring, upper-band exclusion, inverse-square weights and nearest-even separation
rounding. Match each source pair's measured separation after fitting; the full analytic correction always applies to
supported pairs, with no Source blend and no clearance or shared-target control. Undefined shared-band measurements
abstain instead of treating absence as zero separation. This is a different objective from Hu/Hersch's shared class
density; neither can substitute for the other behind one generic target control.

The two analytic adapters permit face and corner contact. Mono feasibility uses delivered binary same-row walls to
forbid occupied-cell overlap and wall-order inversion. Gray uses a certified conservative continuous same-row bound on
raw fitted outlines, without converting coverage to binary cells. It can retain a wider integer bound when interval
refinement cannot certify the tighter one; it does not guarantee minimal Gray clearance. These are declared project
placement adaptations, not claims that FontForge or Hu specifies a discrete blank-pixel policy. Each adapter owns when
its bound participates in its solve; abstentions retain Source without a new feasibility intervention.

The editor stores selected method and retained per-method settings as one controlled value, migrating the historical
kerning boolean to the current method. Derive active controls and render configuration from that value; reject stale
edits rather than maintaining parallel selected-control and selected-table state. This follows the
[single-source-of-truth state guidance](https://react.dev/learn/choosing-the-state-structure). Keep method controls
explicit and typed; a closed selection and one composition point suffice for the actual methods. Method switching
retains inactive settings, which cannot affect active render identity. Saved variants, unsaved preview state, copied
URLs and export must preserve the same active selection. The specimen-text Reset retains its existing meaning.

Any prepared-analysis identity must distinguish font bytes, axes, size, pipeline and geometry policy, method semantics
and active settings, and the calibration recipe/domain. It must not vary with inactive method controls or the supplied
reading text's frequencies. A bounded prepared result may be cached without changing those relationships.

The closed catalog contains implemented runtime adapters, not historical experiment names. A saved valid method whose
current rendering profile is unsupported must remain selected and report that limitation; it must not silently become
Source. CounterSpace remains a separate runtime-port task: the existing Python calibration and nonlinear score search
cannot be represented by another method's analytic target or by retained font-specific tables.

Before adoption, check the port against independently captured original profiles, selected/rejected integer positions
and analytic fixtures, including half-font-unit contact, absent rows and restricted-height predicates. Check source
identity, native/WASM parity, text-independent pair results, work limits, tracking exactly once, unchanged glyphs,
preview/export parity, state migration and control switching. Mechanical parity establishes implementation fidelity;
manual parameter suitability and optical acceptance across other fonts remain separate assessments.

#### YinYangFit feasibility experiment

The authorized recovery experiment uses only the historical Torch notebook at `d9c7e25`, as specified in the
[training requirements audit](../../references/yinyangfit-training-requirements.md). Recover its original-domain Crimson
lowercase inputs and five candidate translations, recording pinned sources, compatibility changes and the complete
676-pair input manifest. First compare finite, varying scores for fixed `nn`, `oo` and `av` pairs, test repeatability
and save/load identity, and measure resource use. Preserve the stochastic reference; any deterministic evaluation arm
must be separately named and disclosed. Inspect both loss branches, including degenerate cubic fits, without
substituting a new objective. A bounded gradient census may follow successful forward checks, with no optimizer updates
in this recovery stage. Stop on nonfinite scores or gradients, unexplained input differences, invalid candidate
translations or unsuitable resource use. Keep all artifacts isolated; no captured-bitmap adaptation, training run or
editor/preview change follows from recovery alone.

The authorized short training experiment follows that recovery with three main Adam updates, in fixed `nn`, `oo`, `av`
order, using the historical learning rate `0.0011`, batch size one, five candidates and unchanged hybrid loss. This
small deterministic schedule is an optimizer/replay probe, not the original shuffled 676-pair training run. Preserve the
original Gaussian draws during training through a recorded, continuing RNG stream; separately evaluate the same fixed
pairs without noise before and after training, restoring training RNG state around evaluation. Checkpoint weights,
optimizer, all RNG state, position and source/input/fixed-tensor identities after each main update. Replay the final two
updates from the first checkpoint and require identical final parameters, optimizer and RNG state. Count these two
replay updates separately from the three main updates. Stop before an update on nonfinite costs, loss or gradients, a
degenerate cubic, a nonfinite/out-of-domain selected minimum, or unexpected gradient reachability; stop afterward on
invalid parameters or optimizer state. Never replace the objective, skip a failing pair, tune the learning rate or claim
improvement from losses on different pairs. Fixed before/after scores, target rank and target cross-entropy are
diagnostics of source-spacing imitation only. Keep the run resource-bounded and isolated from previews; three updates
cannot establish convergence or optical quality.

The broader pair-identity trial freezes its
[split and protocol](../../../experiments/contextual_spacing/reference/yinyangfit-recovery/pair-trial.lock.json) before
scoring. Thirteen unique training pairs cover every lowercase scalar once, selected by a deterministic alphabet
permutation that excludes the recorded diagnostic pairs and their reversals. Train from fresh initialization for one
pass; retain the original Adam settings, Gaussian training noise, full input geometry and numerical stops. Separately
evaluate four fixed training pairs and the held-out `ca`, `nx`, `os`, `se` pairs before and after, preserving training
state. These are targeted within-font pair holdouts, with shared glyphs and incomplete role coverage; they cannot
establish font, glyph, role, size or script generalization. The alphabet sample is not a prose-frequency distribution.
No held-out result may choose settings, seed, schedule or a retry. Retain full cost vectors, target cross-entropy,
rank/ties, complete minimizing-offset sets and cost spread; lower loss alone is not successful distance selection.
Checkpoint after each update and replay the last update from its preceding checkpoint, recording thirteen main and one
replay executions separately. Bound the run to the declared resource budget. This is a source-spacing imitation
experiment; no outline/raster adaptation or preview change follows.

The next isolated reference is [YinYangFit](https://github.com/skosch/YinYangFit), whose
[model discussion](https://skosch.github.io/YinYangFit/#models-and-cost-functions) proposes spatial interaction costs
and fitting against designed pair placements. First reproduce a pinned executable scoring path, including its objective
and parameter provenance. A feature visualization or constant penalty is insufficient to select spacing. Missing
objective or fitting code must be reported as an incomplete reference, not filled with an invented aggregation rule.

Only after that gate may the reference be adapted to unchanged captured binary glyphs at feasible integer positions.
Keep face/corner contact permitted, occupied-cell overlap forbidden, fixed-pitch/tabular safeguards explicit and
reported problem pairs outside calibration. Assess source-relative width drift and held-out behavior before preparing
another reading comparison. The full fitted-outline model remains the control; this feasibility work does not change the
renderer, solver selection or existing previews.

#### YinYangFit interactive spacing feasibility

The isolated `yinyangfit-interactive-v1` experiment tests whether interpretable global controls can move delivered
raster pair spacing without model training. It scores the actual delivered Mono cells (binary `0/1`) and Gray cells
(linear 3-bit coverage, no thresholding) at whole-pixel origin steps around the maintained metric placement, keeping
glyph bitmaps unchanged. Face/corner contact is permitted; occupied-cell overlap is forbidden and recorded. This is a
nearest-distance probe within YinYangFit feasibility work, not a reproduction of YinYangFit's oriented model: no
oriented convolution kernels, no ratio distance estimator, no multiscale V1C responses and no multiple contour support
are implemented. The single-nearest-sample rule ignores support multiplicity and orientation; the regularized power
kernel, the attention-normalized aggregation and the integer search toward a desired value are explicit project
hypotheses sourced from Electric Bubble's browser prototype, while the JAX revision defines no scalar reduction.

The three global controls are target cohesion (hypothesis set-point), interaction reach in pixels (radial knee; the
stored field keeps the compatible name `feature_scale`, which is not V1 feature-scale filter weighting) and proximity
falloff (radial decay shape, not an independent crowding penalty). Only settings whose effects are demonstrated are
retained; endpoint saturation, boundary minima, ties and invalid placements are recorded, not hidden. Ties anchor at the
global valid minimum, then admit every valid candidate within tolerance, in both the scorer and the page mirror. Word
layouts distinguish metric-rounded pair search centers, the experiment's cumulative whole-pixel layout and a named
captured-source fractional word baseline shown beside it; Gray word draws accumulate fractionally and round only for
drawing, so the experiment layout does not retain captured Gray spacing.

Evidence and the self-contained interactive page stay under
`out/diagnostics/contextual-spacing/yinyangfit-interactive-v2/` (the initial `yinyangfit-interactive/` outputs are
retained unchanged); commands are in the
[experiment README](../../../experiments/contextual_spacing/README.md#yinyangfit-interactive-spacing-feasibility).
Optical assessment remains pending; this adds no maintained kerning method or renderer identity.

A v3 sample-gallery page under `out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/` keeps the same model and
integer policies while presenting all 13 canonical root samples in both profiles with a concise end-user flow (three
visible model-parameter controls with one selected sample, shared profile/magnification; pair inspection, candidate
table and method note collapsed). Multi-line root texts lay out per line with space gaps at metric; Literata captures
omit U+0060, which the font cannot shape as an isolated scalar and no sample text needs. User scope for this page is
only YinYang-derived model controls; alternate spacing methods are separate references, not substitutes here. Slider
bands follow the measured working-range recommendation (cohesion `0.00 … 2.00` step `0.05`, reach `0.50 … 6.00` px step
`0.25`, falloff `0.50 … 10.00` step `0.50`, defaults `1.10/2.0/2.0`); each control also takes direct numeric entry with
full requested precision, validated against evaluated guardrails (cohesion `[0, 2]`, reach `[0.25, 12]` px, falloff `(0,
16]`), keeping the last valid render on invalid input with no silent clamping. Cohesion steps cost no new geometry (the
browser derives choices from stored interactions); shipped reach/falloff columns are an exactly evaluated fast path and
arbitrary entered values are computed exactly in the page through a port of the unchanged geometry core, never
interpolated or snapped. The evaluated grid and the numeric guardrails are versioned separately from the frozen scorer
formula (`yinyangfit_interactive.py` unchanged). Slider copy states what each parameter compares in plain language; the
single experiment-level caveat (a control step can widen some gaps while tightening others) lives in the header and
About note, not in the per-control explanation.

A live field view attached to the v3 page shows the entered preview text at the current setting in exactly two roles on
one shared source-pixel grid: a single muted slate context layer carrying every shown letter's own fading field
(per-letter bubble components from the same kernel, combined by per-pixel maximum so overlaps never sum), with actual
ink drawn opaque on top at true bearings; and a contrasting orange pair-interaction layer showing the computed coupling
contribution at the displayed separation. The orange value at each query point is the normalized attention weight times
the summed bubbles at the pair's chosen step, over the full scorer window including on-ink positions; each shown pair's
orange values sum to that pair's interaction score, and overlapping pair layers combine by display-only maximum, which
defines no new score. Brightness uses one fixed global gain with clipping as display only; the orange layer paints over
the ink so the on-ink part of the coupling stays visible. The layers are components, not the final score: gaps are still
scored one pair at a time, and neither cohesion nor layer brightness measures optical quality. The two-role split is a
project display choice; any resemblance to YinYangFit's grouping-blob illustrations is presentational — those schematics
depict fitted versus poorly fitted words, not computed fields. Two editable RGBA controls (letter field, interaction)
recolor the layers with zero score or map rebuild work, each paired with a visible 0–100% opacity slider editing the
same alpha its RGBA row carries (typed alpha keeps full precision; the thumb shows the nearest step); the palette
survives sample, profile, text, control and zoom changes and is not persisted. No ruler, scale caption or duplicate
Source blob strip is shown; the Source-vs-Adjusted main ink comparison is retained one disclosure away. Single-pair
blobs and the actual five candidate scores with the cohesion target line stay available in the collapsed pair inspector.
Cohesion moves the letters and fields to the chosen separation while reach/falloff reshape both layers. Frame and tint
scale stay fixed across slider moves. No overlay alters the Source/Adjusted output canvases.

The preview text is user-editable (multiline), seeded from the selected sample and preserved across sample, profile and
control changes until restored to the sample text. It drives the main ink preview and the letter fields alike. An
entered line break is the only line break: lines split before scoring and never re-wrap, so long lines stay on one line
and scroll inside the view; at most 10 lines are shown, with a visible note when text is capped and never silent
truncation. Stacked lines share one general display leading of 1.25em rounded up (20 px at 16 px) in every view —
display spacing only, not scorer geometry, and lines never spread apart to avoid field overlap. Only the captured
repertoire (ASCII 32–126 per case and profile; Literata omits U+0060) is accepted: tab, carriage return, non-ASCII and
other missing codepoints are rejected with the offending codepoint named, the draft preserved, and the last valid paint
clearly marked as not yet updated. Whitespace pairs keep their metric word advance and never enter the scorer; empty or
space-only text settles with no ink and an explanatory note. Novel in-repertoire pairs score through the unchanged
geometry core with the source advance and pair-kerning policy (a missing kerning entry means no adjustment, as
captured); the per-setting cache is keyed by the covered pair set so new pairs compute exactly on demand and completed
pairs are reused without recomputing the sample text.

A separate full-window experimental version, identified as `yinyangfit-interactive-b2-fullwindow-v1`, keeps every
control, range, policy and display rule above while scoring each candidate over the full query window instead of
excluding on-ink query positions: occupied ink cells contribute through the same finite regularized kernel at zero
distance rather than being masked out of the attention-normalized mean. This removes the candidate-dependent support
collapse behind the disappearing-gap choice without adding parameters, penalties or glyph rules; contact stays permitted
and reported, overlap stays invalid, and the v1 model, tables and pages are retained unchanged as the historical
reference. Default-corpus evidence and the [model-repair analysis](../../references/yinyang-model-repair.md) hold the
pre-change behavior; optical assessment of the moved endpoints and of the residual wider-control behavior remains
pending, and no maintained method, default or publication selection changes.

#### YinYang oriented field stage

Stage 1 of the staged proposal in
[yinyang-missing-components-assessment](../../references/yinyang-missing-components-assessment.md#3-should-we-add-them-order-and-smallest-step):
directional filters plus the ratio estimator with a single-scale V1C input. Multiscale filtering (stage 2) and a
separately specified/evaluated placement score (stage 3) are out of scope here. No scalar placement objective, no pair
argmin, no cohesion retuning, no training, no live/UI/model/default change. Glyphs, source bearings/advances/native
placements and Gray `p/7` coverage stay exact; the existing B2 scorer stays the comparison and is unchanged.

**Source foundation (verified this session from pinned sources).** The manuscript's
[direct-approximation steps](https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/docs/source/algorithms.markdown)
define the reproduced chain: (1) V1 complex responses summed over scales, (2) orientation-masked filter pairs with
radial kernels `f1 = 1/r^q`, `f2 = 1/r^(q+1)` (`q ≈ 2`), convolved per letter, (3) oriented distance `d = (T∗f1)/(T∗f2)`
and arc strength `a = (T∗f1) ⊙ d^(q+1)` (manuscript `k`; renamed here because `k` is overloaded), (4) pair overlay of
`|dL−dR|`, `aL·aR`, `dL+dR` and the orientation pair `(oL, oR)`. V1 semantics come from the same page: complex response
`S = F^{-1}(F(I)·F(G))` with a quadrature bank, and complex magnitude `C = |S|`. The pinned notebook
(`YinYangFit.ipynb`, cells 15/19) fixes executable details adopted here: radial exponent `k = 2`, von Mises angular
masks (width 4) doubled to directed orientations, filter origin set to zero, FFT convolution with ReLU, `distances =
f/d` where the denominator is nonzero (sentinel otherwise), and `confidences = f·(f/d)^(k−1)`. Notebook cells 22–25 show
maps with no scalar cost and the packaged engine's penalty fields are stubs, so this stage produces fields only.
Upstream `k` names three different things (radial exponent, arc strength, von Mises concentration/filter length); this
stage uses `q` (radial), `a` (arc strength) and `κ` (angular concentration) everywhere. The hyperbolic-ratio `(k_{s,γ},
β)` activation and divisive normalization are not inputs to the direct-approximation chain and stay deferred.

**Project adaptations (each a named, falsifiable hypothesis).** A1: single frozen scale replaces the scale sum
(contrast-sensitivity weighting is stage 2); V1 input is therefore one quadrature bank at Gaussian sigma `s = 1.5` px, 8
undirected orientations, support half-width 6 px, using the manuscript's derivative-of-Gaussian quadrature pair with the
even filter demeaned to zero DC. A2: phase-coherence, directionalized normalization and ring excitatory/inhibitory
shaping are omitted; `T = C` directly. A3: kernels are raw truncated (support radius `R = 12` px) with per-channel
truncation mass recorded; no independent unit-normalization of numerator/denominator (the earlier radial probe showed
that changes the distance scale). A4: fields are computed on a zero-padded lattice with margin `pad = 6 + 12` (V1
half-support plus kernel radius), so every delivered-lattice pixel is exactly integrated and further margin is verified
to change nothing; lattice positions outside the delivered box remain padding-influenced. A5: directed pair channels map
undirected V1 responses `B(o) = C(o mod 8)` onto 16 directed angular masks; pair diagnostics are reported per directed
channel with strength-weighted pooled summaries, not reduced to one cost. A6: Gray coverage enters linearly (`p/7`) with
no thresholding. Falsification: point-support distance-relation failure, convolution-vs-direct-oracle mismatch,
unsupported-mask instability, or pad non-convergence each fail the stage.

**Frozen stage-1 declaration.** `q = 2.0`, `κ = 4.0`, `s = 1.5` px, 8 V1 orientations / 16 directed channels, `R = 12`
px, origin-zeroed radial kernels, zero padding, denominator floor `ε = 1e-12` (below it: unsupported, NaN with mask 0),
and explicit pair strength-variant selection (`strength="notebook"` primary default, `strength="manuscript"` alternate
only when named; the returned mapping carries variant identity). Query grid is the integer pixel lattice; no subpixel
interpolation. Sampling, truncation, padding and normalization are as above; raster-phase sensitivity is measured,
subpixel invariance is not claimed. Workload: synthetic isolated support / parallel bars / asymmetric bars / curves /
diagonals / repeated strokes, plus delivered Roboto and Literata 16/24 px Mono/Gray; focus pairs `um og AV To` at source
`±2` legal integer placements (contact allowed, overlap excluded) and predeclared heldout contrasting pairs `nn oo HH
il` (stem/curve/uppercase/detached-dot coverage). Success: finite values where supported, explicit unsupported regions,
independently checked fields, predictable bar responses, padding safety, integer co-translation consistency. No
universal-monotonicity or cost-free-minimum requirement. Determinism scope: same-input rerun is bitwise identical
(verified); cross-padding (`pad+8`) and 1-ulp perturbation agreement are stability measurements with stated bounds, not
determinism claims. Rust/WASM caching advice only after evidence (`yinyang-oriented-fields/evidence` owns timings);
reviewer owns `out/.../reference-review/` and it is not touched here.

**Evidence and commands.** Implementation `experiments/contextual_spacing/yinyang_oriented_fields.py` (NumPy only),
evidence `yinyang_oriented_fields_evidence.py`, tests `tests/test_yinyang_oriented_fields.py`; arrays and provenance
under `out/diagnostics/contextual-spacing/yinyang-oriented-fields/implementation/`. Commands are in the
[experiment README](../../../experiments/contextual_spacing/README.md#yinyang-oriented-field-stage).

**Stage-1 source clarifications (reconciliation outcome).** Strength-primary rule: the executable notebook
`confidences = U1·d^(q−1)` (cells 15/19) is the PRIMARY reference; the manuscript `a = U1·d^(q+1)` is retained
explicitly as the alternate diagnostic. Both branches stay in the API with these labels; neither is optically approved
and no manuscript-typo claim is made. Finite-support finding: writer masks/radials agree with the frozen oracle exactly
on common taps (max 7.8e−16) under one fixed channel permutation, and the estimator reproduces the oracle to ≤2.7e−10
with matched even support; full-support residuals (≤1.1 px on bars, ≤3.9 px worst on sparse two-point stimuli, at
far-field pixels) are the writer's symmetric `+12` rim alone — a declared finite-support choice, not a semantic
difference (the oracle even support is asymmetric with a half-tap bias). Gap-center distance is non-monotone in gap
width (2/4/6/8 px → 1.99/1.74/2.07/2.90 px): values recorded, no universal monotonicity claimed. Reviewer wording
qualification: the finite von Mises opposite-half response is a minimum, never an exact null (measured selectivity
2981×, nonzero); oracle numerics preserved, prose qualified here only.

#### YinYang multiscale field stage (stage 2)

Stage 2 of the staged proposal in
[yinyang-missing-components-assessment](../../references/yinyang-missing-components-assessment.md#3-should-we-add-them-order-and-smallest-step):
multiscale V1C input summed BEFORE the oriented ratio (article direct path), retaining per-scale responses and the
single-scale limiting case. No scalar placement objective, no pair argmin, no cohesion retuning, no training, no
live/UI/model/default change. Glyphs, bearings/advances and Gray `p/7` coverage stay exact; the existing B2 scorer stays
the comparison and is unchanged.

**Source foundation.** The manuscript direct-approximation step 2 prescribes summing V1 complex responses over scales
"according to the desired contrast sensitivity function" before the oriented ratio; it gives no numeric CSF weights. The
notebook instead builds cross-scale phase coherence (cell 13) plus divisive normalization (cell 14, `β = 0.01`,
threshold `0.03`), keeps the scale axis through the ratio (cells 15/19 with ring filters), and pools scales only in
visualization (cell 22, confidence-weighted mean). These are distinct paths: stage 2 implements the article direct path
ONLY. Notebook normalization/pooling stay deferred and are never silently mixed in.

**Project adaptations (each a named, falsifiable hypothesis).** H-SCALES: one general sourced geometric progression
around the frozen baseline — half-octave, five scales `σ = 1.5·2^(k/2)`, `k = −2…2` (`0.75/1.06/1.5/2.12/3.0` px).
Geometric scale sampling is sourced (manuscript "various spatial frequency scales"; notebook geometric period
progression 30→3); the specific five-scale half-octave centering on the frozen `σ` is a project choice fixed a priori —
no per-font/per-pair tuning, nothing selected on optical looks. H-CSF0: neutral uniform weights (`w_s = 1`) as the
frozen default; custom explicit weight vectors are function input for declared ablations only. Uniform weighting is an
ablation, NOT a human-CSF claim: the article prescribes no numeric CSF. Per-scale V1 uses the same manuscript
derivative-of-Gaussian quadrature instance at `σ_s` (even partner demeaned), with support half-width `w_s = ceil(4·σ_s)`
generalizing the stage-1 rule (`{3,5,6,9,12}` px); pad is `max(w_s) + R`. Per-scale filter gains (kernel L1/L2/peak plus
unit-impulse response peak) are recorded so uniform weights read with interpretable meaning: uniform weighting
emphasizes fine scales by peak gain, disclosed not corrected. No independent per-scale or per-channel normalization of
`U1`/`U2` (that would rescale `d`).

**Frozen stage-2 declaration.** `σ = {0.75, 1.0607, 1.5, 2.1213, 3.0}` px, default `w_s = 1`; `q = 2.0`, `κ = 4.0`, `R =
12` px, `ε = 1e-12`, 8 V1 orientations / 16 directed channels (all inherited from stage 1). Combination `T = Σ_s
w_s·C_s` per orientation precedes directed mapping `T[o] = T[o mod 8]` and the unchanged ratio stage. Outputs per glyph:
per-scale `C_s`, combined `T`, `U1/U2/d`, primary `confidence_notebook`, alternate `arc_strength`, support mask, gains,
weights, pad. Pair output reuses the stage-1 four diagnostics (no cost, no choice, no minimum) with explicit
strength-variant selection (notebook primary, manuscript alternate); fields are cached per glyph and overlaid per step.
B2 interaction is reported alongside as a diagnostic only (different model; no score parity asserted). Workload: the
stage-1 declared workload unchanged (synthetic bars/asymmetric/curves/diagonals/multi-strokes, delivered Roboto/Literata
16/24 px Mono/Gray, focus `um og AV To` + heldout `nn oo HH il`, source `±2` legal integer placements with
contact/overlap-excluded). Falsifiable gates: single-weight-active reproduces stage-1 fields exactly; response-weighted
sum matches an independent loop recompute; per-scale gains recorded with fine-scale dominance disclosed; padding/integer
co-translation consistency; fractional-phase sensitivity measured (not invariant); finite well-supported values with
explicit unsupported regions; determinism scoped as support-exact rerun with stated `C`/`T`/`U` (`1e-12`) and
well-supported-`d` (`1e-8`) bounds (same-input bitwise identity is established for stage 1; cross-padding/perturbation
agreement stays a stability measurement, not a determinism claim); cold/warm runtime and peak memory on actual workloads
with no WASM performance claim absent a bench. Rust/WASM caching advice only after evidence.

**Evidence and commands.** Implementation `experiments/contextual_spacing/yinyang_multiscale_fields.py` (NumPy only,
reuses the stage-1 kernels and pair diagnostics without duplicating them), evidence
`yinyang_multiscale_fields_evidence.py`, tests `tests/test_yinyang_multiscale_fields.py`; arrays and provenance under
`out/diagnostics/contextual-spacing/yinyang-oriented-fields/multiscale/`, reconciliation under the sibling
`reconciliation/`. Commands are in the
[experiment README](../../../experiments/contextual_spacing/README.md#yinyang-multiscale-field-stage).

#### YinYang stage-3 SCORE-v2 hypothesis experiment

Stage 3 of the staged proposal: a separately specified mechanical/model-coherence score over the frozen stage-1/stage-2
fields. No scalar placement objective is promoted to a default, no preview/UI/range change, no training, no optical
acceptance or live promotion. Design authority is
`out/diagnostics/contextual-spacing/yinyang-oriented-fields/score-design/decision.md` (SCORE-v2) with
`probe_score_v2.py`; the probe's approximate column-dx overlay is NOT the reference placement for real glyphs. Source
authority is the manuscript
[direct-approximation steps](https://github.com/skosch/YinYangFit/blob/609d17e8a6446ec4413a1b02a0768b8214d73333/docs/source/algorithms.markdown)
plus the frozen field modules (`yinyang_oriented_fields.py` SHA
`6e3322d9125abdb7247f6bbe6c8d410db501fc523ffcf558c7985e88d74ec6e1`, `yinyang_multiscale_fields.py` SHA
`b16bb4a47642fdf896655d5768f1781af003123892ebf61449cd8aecbadcefca`); raw fields stay frozen and are never duplicated
here. Protected B2 (`yinyangfit_interactive_b2.py` SHA
`5f6f1aebcd4121df0441029a2171457f166b853b15c4a757e2a1c50780fdfdd7`), v3 compute (SHA
`1494199101a9d2cc9eca6e6d0598ccbe94d51da286709a5e53f29ef8f86ca462`) and the reviewed page stay pinned and unchanged.

**Candidate (sole) + one ablation.** Per glyph/channel `E[g,o] = sum c^2` over its own padded lattice once (H-NORM,
candidate/neighbor/domain-independent); per step `s`, `G2(s) = sum_{a,b} sin^2((theta_a-theta_b)/2) sum_p
cLa*cRb*exp(-(dLa-dRb)^2/(2 tau^2))/sqrt(ELa*ERb)`, both-supported else `0`, zero/nonfinite-energy channel contributes
`0`; unsupported canvas yields `G2 = 0` with an explicit abstain. `tau = 0.5` px is untuned (H-TAU2; `0.25/1.0`
sensitivity reported, never selected). `q = 2`, `kappa = 4`, 16 directed channels; `G2` is dimensionless in `[0, 128]`
by Cauchy-Schwarz. H-NORM (isolated normalizers), H-FACE (symmetric facing sum), H-TARGET (deviation-from-`C*` rule) are
source-founded project hypotheses, NOT upstream prescriptions. The ONLY ablation is A1 manuscript strength (`m =
U1*d^3`, `E` recomputed). MAIN path consumes stage-2 COMBINED `T = sum_s w_s C_s` fields (ratio, confidence, isolated
`E`, score); single scale is a limiting-case regression only, never a second model or per-scale-G2 average. No sweep
normalization; the fixed union canvas over the swept steps is embedding only (shared-step `G2` invariant when `+-2`
widens to `+-6`).

**Parent corrections (binding, take precedence over the design draft).** No MARGIN-v2 certainty claim: no complete
conservative UPPER bound over `dU1/dU2/dd/dc`, support changes, `E`/G2 terms exists, so every verdict records
`uncertainty_not_certified` with the known-term budget plus separate empirical direct-vs-FFT/padding/contrast replica
stability; weak-band share `<1%` stays a diagnostic, never a stability proof or blind `1e-6` cutoff. Determinism means
same-input repeatability within stated field-path tolerances, never a last-ULP multiscale gate. Global `C*` uses NEW
model units `[0, 128]`, not B2 cohesion: no optical default, no UI range change, no fitting to metrics; coverage is
reported over the predeclared grid with all ties and uncertainty preserved. Non-defect outcomes (weak share, dilution,
variant choice, flat real pairs, sensitivity) are hypothesis findings pending parent judgment, never silent formula
fixes; only oracle failure / nonfinite / asymmetry / pad-domain dependence / nondeterminism is an implementation defect.

**Predeclared domains and protocol.** 8 captures (Roboto/Literata x 16/24 x Mono/Gray) from the frozen stage provenance,
identities and capture SHAs locked; focus `um og AV To` + heldout `nn oo HH il`; source `+-2` (5 legal steps) plus ONE
broader `+-6` integer diagnostic on the same validity policy (occupied-cell overlap invalid and separate, face/corner
contact allowed, recorded from the baseline `contact_counts`; bearings, native origins, Gray `p/7` exact). Synthetics:
bars, mass contrast, curves, diagonals, repeated-3-bar regression, remote-stem dilution, glyph-mass contrast. Exact `C*`
grid: `[0,1,2,4,6,8,10,12,14,16,20,24,32,48,64,96,128]` (probe signal band `6.0/10.3/14.8` reported as mechanical
context only); target default none. Placement rule TIE-v2: minimizing set `{s: |G2(s)-C*| <= m* + tol}`, `tol =
1e-9*max(1,m*)`, single-pick fallback is global-min then lowest step index, labeled baseline-only comparison, never
optical. Report per pair-case: `G2` curve, support, floor share, `tau`/A1 deltas, turns/boundaries/ties, B2 curves
beside SCORE-v2 as comparison (raw deltas, no score equivalence), and the local-same-gap dilution counterexample without
gloss.

**Evidence and commands.** Implementation `experiments/contextual_spacing/yinyang_oriented_score.py` (NumPy interpreter,
explicit `strength=`, cached per-glyph `E`, native bearing-origin embedding, baseline validity), evidence
`yinyang_oriented_score_evidence.py`, tests `tests/test_yinyang_oriented_score.py`; results under
`out/diagnostics/contextual-spacing/yinyang-oriented-fields/score-experiment/`. Commands are in the
[experiment README](../../../experiments/contextual_spacing/README.md#yinyang-stage-3-score-v2-hypothesis).

The bounded `predictable-spacing` prototype separates optical correction from deliberate letter spacing on the frozen
13-case × 2-profile corpus, with the interaction scorer out of the path. The endpoint is the retained
`hu_fitted_full_density_conserved_touch` construction-order candidate (complete fixed-ASCII source-origin density
target, fitted-outline walls, published aperture depth 0.21 and global factor 0.25, 64 samples per pixel), resolved
through the existing solver composition: the finalized Source adjustment blends with the continuous optical adjustment
before signed whole-pixel rounding (ties away from zero) and the existing feasibility bound. At strength zero an
explicit bypass returns Source exactly with no calibration or feasibility work; at full strength the retained endpoint
applies, including fixed-pitch, source-tabular and unsupported-pair safeguards, which retain Source with a recorded
reason. Endpoint computation is independent of displayed text, slider value and zoom.

Deliberate letter spacing follows the existing span-gap policy: it applies once per internal span gap, spaces keep their
metric word advance, terminal advances are retained and line breaks reset context. It is an integer −2 to +4 px control,
matching the preview tracking range but not its per-advance semantics: this control never touches spaces or terminal
advances, while maintained per-advance tracking adds to every advance. The user offset is unclamped, so negative values
may show touching or overlapping ink; the automatic optical step keeps its own clearance bound, and guard-constrained
plateaus are recorded rather than hidden. Per-pair output is monotone in correction strength within each endpoint's own
direction (rounding and the clearance floor are monotone maps); varying both controls together need not preserve that
direction. No smoothness or jump budget is asserted.

Frozen Gray captures carry no fitted outlines and native capture is Mono-only, so no native Gray-geometry endpoint can
be computed from them. Gray therefore reuses the same mono-pipeline fitted-geometry endpoint through an explicit
source-backed adapter: fractional 26.6 source advances and pair adjustments accumulate fractionally with rounding only
at draw, and the integer correction deltas (automatic minus metric from the retained composition) add to that fractional
pen. Source at zero stays exact by bypass; delivered Gray cells never change. A native Gray-geometry endpoint remains
follow-up work. Mechanical checks establish Source identity, endpoint parity and control behavior; optical assessment of
the endpoint remains pending and nothing here approves it.

#### Electric Bubble full-field reproduction

The bounded `electricbubble-fullfield` experiment tests whether replacing the nearest-occupied-sample proxy with the
author's full-support field mechanism removes or reduces the bumpy distance responses behind the skipped and reversing
placements in `yinyangfit-interactive-v1`. The complete source pipeline changes several model stages, so this comparison
does not isolate support representation. A correct reproduction that still fails is a successful negative result. No
TFJS or current-YinYangFit objective is invented, and neither the JAX nor the historical Torch loss is imported.

The source is the pinned Electric Bubble snapshot
(`out/diagnostics/contextual-spacing/yinyang-alternatives/electricbubble`, `31ce15a`): full saliency construction (ink
and whitespace convolutions), saliency power, `electricBubbleKernel` inverse-power support convolution, the nonlinear
transform and clips, convolution-derived gradients and normalized attention including equidistance, angle-difference and
mean-angle factors, with the author's 80-attempt threshold walk kept as the source search arm beside an exhaustive
common-feasible-domain probe. The frozen nearest-distance scorer is called unchanged; its regularized kernel,
nearest-sample proxy, strength-product weighting and omitted vertical factor stay disclosed departures. Delivered cells
enter through an explicit input adapter at exact `0/1` or Gray `p/7` values with recorded hashes; the author's numeric
scales are preserved verbatim and never silently matched to the proxy's `1.1` cohesion.

Invariants: the reference checkout, the frozen scorer, the v3 page and data, the approved baseline and maintained apps
and crates stay untouched; no new user control, default or preview change follows. Source `Number.MIN_VALUE` floors and
large-power instabilities are recorded as NaN, Inf or zero fields, never silently repaired; a separately named numerical
diagnostic may use safer dtypes. Gates: independently grounded parity for saliency, kernel, field, gradient, attention
and score on minimal fixtures (with tolerances, dtype and alignment); finite, deterministic outputs or explicitly
retained failures; recorded curves, extrema, jumps, reversals, ties, boundary hits and walk termination on frozen
synthetic and real pairs before any bounded corpus comparison; measured cold and warm time and memory on the exact
workload. Optical quality stays pending assessment; mathematical monotonicity of a Tightness control, a desired-value
cost's interior minimum and Correction Strength toward fixed endpoints are three separate concepts. Commands are in the
[experiment README](../../../experiments/contextual_spacing/README.md#electric-bubble-full-field-reproduction); the
[reproduction report](../../references/electricbubble-full-field-reproduction.md) owns the verdict and follow-up.

#### Electric Bubble scale adaptation

The bounded `electricbubble-scale` experiment tests one declared hypothesis: that the author's numeric parameters are
lengths and variances in author-canvas pixels at the author's 72 px render, so expressing them relative to the delivered
font measurement restores scale consistency without per-font, per-size or per-pair tuning. The reference measurement is
the em at the author's render size: `App.js` fixes `fontSize: 72` with `scalingFactor = fontSize / unitsPerEm`, so the
scale ratio is `r = ppem / 72` where `ppem` is the delivered capture's `size_px`. An x-height reference is rejected: the
author states no x-height normalization, and the canvas geometry is defined from the full em (`ascender`/`descender`).
This partial parameter resize is a project adaptation, not an upstream rule or a demonstrated complete scale
normalization.

The mapping scales explicit patch covariances by `r²` and filter supports by `r`, retaining other constants. Concretely:
saliency and bubble `filterSize` support windows become `r`-scaled, rounded to the nearest even integer with a minimum
of 4 (evenness preserves the TF-SAME asymmetric-pad and kernel-center conventions the full-field port verified against
real `tf.conv2d`); `patchSizeX/Y` covariance entries scale by `r²`; the envelope entry `1000 * filterSize` keeps the
dimensionless `1000` with the scaled integer support. Unchanged: gains, bias, valley ratios, orientation angles,
attention coefficients, power 22, `initialStrength`, `distDecay` and the numeric `desiredInteraction` target of 0.01,
assessed without retuning or a complete transport derivation. The bubble kernel still evaluates native pixel distances;
convolution sums have no quadrature reweighting, and the `[1,-1]` gradients remain on the native grid. Additive source
epsilons prevent general cancellation of common gradient magnitude factors. These retained dimensional terms limit the
interpretation to this partial resizing rule.

Two non-uniqueness limits are declared hypotheses, not results. First, the envelope entry mixes a length with a variance
(`1000 * filterSize` used as covariance), so no dimensionally unique scaling exists; the stated choice is one project
reading. Second, the `initialStrength / min(50, saliency^22-convolved)^(-1/22)` nonlinear transform has no
scale-transport derivation in the source; it runs unchanged and its output range is measured, not assumed preserved. If
the source dimensionality prevents a unique faithful mapping, this experiment says so and keeps the alternatives
separate rather than claiming upstream reproduction.

At `r = 1` the rule reproduces the author's verbatim parameters exactly, so identity against the full-field port on
identical inputs is a mechanical gate. Away from `r = 1` the experiment measures, in order: synthetics holding geometry
fixed across scales (parallel, asymmetric and support-multiplicity fixtures, exact integer-grid upsampling so no
interpolation policy intrudes, plus an integer-translation coordinate check); the frozen Roboto/Literata 16 Mono/Gray
core against the unchanged author baseline on identical valid collision-free step masks; then the cheap 5-pair subset
across all 13 captures × 2 profiles only if the core runs complete. Raw and normalized arms share the same steps,
adapter padding, overlap mapping and walk rules; runs break at invalids, and numerical jitter is bounded by recorded
tolerances and amplitudes rather than read as bumpiness. Target behavior is inspected, not fitted: interior versus
boundary minima against the unchanged numeric 0.01 target, guard effects and walk terminations, with no per-pair or
per-size target adjustment. A calibration arm would need a frozen held-out split and a predeclared rule; none is run
here, and target calibration stays explicitly unperformed. Success may be a correct negative: the verdict is only
whether this scaling hypothesis improves the measured response properties, not whether YinYangFit succeeds or fails.

#### Neighbor placement assessment

The [construction-order audit](../../references/hu-hersch-construction-order.md) separates complete-outline cavity
construction from body-window measurement. Its proposed candidate finds cavity supports again after the 45-degree stage
and keeps class body height in the global depth limit. The separate construction-order candidate above implements that
sequence without changing target policy or row weighting. Calibration-induced pixel changes alone do not establish
improved local wall geometry or optical spacing.

A configured reading-page review compares current placements with one-pixel-tighter diagnostic neighbors. The existing
pair-inspector construction supplies the basis: unchanged glyphs at adjacent integer origin steps, with actual bitmap
contact counts. This is evaluation of the unresolved `nx` concern, not a new spacing rule or a glyph exception.

Compare the `nx`/`hx`/`mx`/`dx`/`ux`/`kx` family across complete texts in the four retained 16 px fonts. The alternative
changes only selected transitions. Both binary views follow the same tracking controls, while the normal browser font
retains vanilla shaping and fractional spacing. The regular comparison, presets and solver tables remain available.

Whole-text review follows the selected preset or custom text. Current and diagnostic layouts wrap independently at the
same width, with the diagnostic pair delta applied before wrapping; it must not reuse the current line breaks. Explicit
and automatic line starts have no cross-line pair adjustment. Native and enlarged panes expose the complete text, with
matching scroll progress within each scale group. Contact markers start off for reading and remain available for
inspection. Pair-led review remains a separate optional configuration with zero tracking and no wrapping.

The diagnostic neighbor is intentionally not clamped: an alternative that overlaps must remain visible and be labeled as
violating the current automatic policy. Edge/corner contacts are allowed and displayed separately from overlap. Assess
whether tighter `nx` improves word rhythm or creates a heavy baseline join, and whether the same preference extends to
the facing-stem family. `kx` has more than one contact in Literata; contact counts must come from actual cells rather
than an assumed shared serif pattern. No preference or measured gap automatically promotes a solver change.

### Stem/curve reference experiment

The bounded experiment evaluates the six source-master standards in
[Hersch et al. 1995, pp. 86–87, Figure 21](https://lspwww.epfl.ch/publications/typography/ptgogf_95.pdf#page=11):
`nn`/`HH` for facing stems, `oo`/`OO` for facing curves, and `no`/`HO` for a stem and a curve. This is the paper's
specialized vertical-border convention, not additional targets for the generic filtered-wall area estimator.

First measure unchanged source outlines and source metrics at the retained axes. A supported facing vertical stem
supplies its exterior edge; a supported facing curve supplies its exterior extremum. Source reference gap equals its
designed origin step plus the difference of those two border coordinates. Candidate origin steps solve toward the
matching reference gap. Classification and unsupported cases must be explicit geometric decisions, independent of sample
text and glyph names. No corpus-fit target offset or deliberate tracking selects density.

The source-only experiment must separate supported coverage, generic/ambiguous abstentions, reference reconstruction,
pair changes and overall density. It compares the earlier shared target on the same retained text and four-family scope.
Matching a reference or reducing a mean shift does not establish optical acceptance. Unsupported pairs retain their
source relationship in this diagnostic and must not be counted as successful optical balancing.

Only a supported source-only result proceeds to a separate delivered-cell candidate. Delivered border recovery,
mixed-case composition and reverse stem/curve use must disclose their adaptations and retain missing/ambiguous
fallbacks. Existing rounding, full-bitmap clearance, fixed-pitch/tabular policies and optical-zero identity remain
independent constraints. The maintained renderer, existing comparison modes and earlier preview artifacts stay separate;
no default is promoted by this experiment alone.

The first source-only probe does not establish that gate. The provisional midpoint/segment classifier recognizes a local
primitive, not necessarily the complete facing typographic feature. Flat outer plateaus on round glyphs can be called
stems or become unclassified when the body window changes; the stem beneath an overhanging shoulder can also be mistaken
for a simple facing stem. Available reference reconstruction is therefore insufficient evidence for arbitrary-font use.
The six-standard formula remains a published foundation, but this classifier is not a validated implementation of its
feature categories. Delivered integration is deferred until classification handles those geometric cases without glyph
exceptions or tuned length/angle thresholds.

### Source-relative Hu comparison

The `hu_source_relative` comparison keeps each source pair's measured relationship instead of assigning the shared
`nn`/`HH` area. It adapts the [source-preserving equation](#source-preserving-comparison) to the current Hu/Hersch
measurement. This is a diagnostic compensation model, not Hersch's shared ideal-space rule and not a new optical
approval. Glyphs and the shared-target `hu_hersch` control remain available unchanged.

For the two geometries, use identical physical body windows, sampling and published depth parameters. Continuous source
outlines supply one filtered-wall offset; delivered bitmap cells supply the other. At source-kerning strength `k`:

```text
source_step(k) = source_advance_left + k * source_pair_adjustment
pair_target(k) = source_step(k) + source_filtered_wall_offset
required_delivered_step(k) = pair_target(k) - delivered_filtered_wall_offset
```

The source-kerning control remains active at the full compensation endpoint, as for the earlier source-preserving
comparison. The metric endpoint, blending, signed adjustment rounding, independent bitmap clearance and deliberate
offsets keep the existing placement policy. Source metrics retain captured 1/64 px precision. Finite signed pair targets
are valid; they are not subject to the shared-density positivity requirement.

Delivered `n`, `H` and experimental `0` bounds supply windows only, not whitespace density. Mixed endpoints remain
averaged. Missing windows, unsupported categories, empty geometry or absent shared ink rows in either geometry retain
metric placement with provenance. The source curves are sampled directly without rendering them to another bitmap;
bounded-bay extraction remains a numerical adaptation on those samples. Cache and result identities include both
geometry policies.

Compare native-size `lynx`, `tuft`, the earlier reported pairs, repeated lowercase letters and the longest preset.
Measure source-target residuals separately from integer rounding and clearance. Source-relative compensation can
preserve uneven source spacing; this test does not promise to equalize perceived distance across pairs.

### CounterSpace comparison

The retained comparison reuses Simon Cozens's
[CounterSpace implementation](https://github.com/simoncozens/CounterSpace/tree/01b33477225eb5fc7bedf93a090b5cd7dd0c812b),
with its Apache-2.0 license and dependency identities retained in the isolated experiment. The
[method investigation](../../references/optical-spacing-pair-models.md) owns the source comparison and limitations. This
is a different measurement model, not completion of the Hu/Hersch subset.

CounterSpace constructs a two-dimensional counterspace mask and applies its serif-smoothing and concavity routines
before weighting the remaining space with center, top and bottom Gaussian fields. Font-wide parameters are fitted from
reference pairs at maintained metric placements. Its source implementation supplies the filtering, fitting and scoring
rather than a replacement formula inspired by those operations. Weighted scores have their own units; they are not
horizontal separation pixels.

The source font instance must match the captured font identity and axes. The candidate calibrates and scores the same
retained bitmap cells, replicated into common physical analysis coordinates without changing delivered ink. Reference
origins use finalized advances and the maintained full-kerning metric adjustments, independently of the runtime kerning
slider. Fitting and reference targets both use these delivered shapes and placements. This native-size calibration is a
project adaptation of CounterSpace's raster-based fitting; its optical suitability remains a hypothesis. The previous
source-raster calibration, using capture-authoritative source metrics, remains an explicit comparison.

The captured-font backend exposes tight nonzero ink bounds to CounterSpace. Transparent storage margins are excluded
from analysis dimensions and reference windows while absolute ink-cell coordinates, bitmap display offsets and finalized
advances are preserved. Adding or removing transparent padding must leave fitting, targets, scores and solved placement
unchanged. This applies to delivered scoring under all three variants, including the source-calibrated comparison; older
outputs using storage bounds remain separate diagnostics. The upstream smoothing and concavity routines are unchanged by
this bounds correction.

A private tensorfont intensity adapter runs the original concavity operation in its expected 0–255 contour domain.
CounterSpace's smoothing produces binary 0–1 analysis matrices, whereas tensorfont's contour cutoff is 30; passing those
values through unchanged silently defeats reduction. The adapter scales normalized input to the original domain,
preserves its rendering metadata and restores the normalized result for the exterior masks. Existing byte-scale input
uses the original operation unchanged. This semantic repair applies consistently to fitting, references and pair scoring
and is identified separately from API compatibility changes. It changes only derived analysis masks, not captured ink.

The existing signed-jump cavity classifier remains unchanged during this correction. Repeated-pair assessment separates
intensity repair from that heuristic: opposing contour changes can cancel its signal, so normalization alone does not
establish that open bowls and diagonals receive adequate perceptual filtering. Any classifier change needs its own
source-backed model and held-out assessment. The
[classifier assessment](../../references/counterspace-cavity-classifier.md) records the cancellation and raster-stair
behavior, negative absolute-jump comparison and smallest CounterSpace-based next experiment.

Three variants isolate the changes: source calibration with upstream first crossing, delivered calibration with first
crossing, and delivered calibration with the closest feasible score. First crossing retains the first whole-pixel score
above the target and the upstream maximum-score fallback when none crosses. Closest-score search examines the same
bounded candidate domain, excludes candidates below the existing whole-bitmap clearance bound and minimizes absolute
score error, breaking ties toward the smaller origin step. This discrete optimization is a project adaptation of the
upstream target-score objective, rather than a claim that upstream implements nearest-score search. Scores that change
direction are evaluated explicitly; target crossing, search limits and residuals remain diagnostics.

The placement adapter retains target score, emitted score, residual, reference placements, search outcome and fitted
parameters. Source kerning controls the metric endpoint; full CounterSpace placement is independent of that slider. The
whole-bitmap clearance rule also guards partially blended placement and reports any displacement it adds. Optical zero
preserves metric identity without loading optional numerical dependencies. Fixed-pitch, requested tabular preservation,
empty or unsupported geometry retain metric placement with explicit reasons. Deliberate offsets remain placement
operations; the viewer must not infer their nonlinear CounterSpace score by adding a pixel offset.

The browser selects completed Python tables. CounterSpace-enabled exports include these optional comparison models;
numerical fitting is not a browser or embedded runtime dependency. Original optimizer status, bounded-search limits and
nonfinite failures remain visible. Agreement with upstream code establishes reuse, not native-size optical acceptance.
The reported Literata pairs are assessment inputs, not fitting exceptions.

### Filtered-wall comparison

The retained `filtered_walls` comparison adapts
[Hu §4.4, pp. 88–91](https://lspwww.epfl.ch/publications/typography/sopfbsc.pdf) and
[Hersch et al., pp. 85–88](https://lspwww.epfl.ch/publications/typography/ptgogf_95.pdf). It measures the area between
facing walls after filling concavities with unit-slope (±45°) envelopes. The
[method audit](../../references/filtered-wall-spacing.md) distinguishes published principles from this adaptation. This
replaces the closest-edge weighting for the candidate; the three FontForge methods below remain controls.

Source Bézier intersections and produced full pixel-cell edges are measured in floating pixel coordinates, y-up. A
common uniform midpoint grid uses 64 samples per pixel of height, with a fixed window per class: source bounds of `n`
for lowercase, `H` for uppercase, `0` for digits, and the union of the two letter reference windows for mixed case.
These bounds are a declared reference-height adaptation, not font x-height/cap-height metrics. Empty scanlines use the
opposite horizontal bounding-box edge, as in Hu. The filter uses physical vertical sample distance:

```text
filtered_left[i]  = min_j(left[j]  + abs(y[i] - y[j]))
filtered_right[i] = max_j(right[j] - abs(y[i] - y[j]))
mean_gap(d) = d + mean(filtered_left_right_glyph - filtered_right_left_glyph)
area(d) = mean_gap(d) * window_height
```

Source reference pairs use the same sampling, filtering and window policy at their full designed origin steps. Their
mean gaps calibrate lowercase, uppercase and numeral targets; mixed case uses the arithmetic mean of the two letter
reference mean gaps, integrated over its common union window. The mixed rule and ASCII `00` reference remain project
adaptations. Sampling is numerical integration, not parity with Hu's unavailable original implementation; resolution
convergence, analytic geometry and an independent quadratic-time filter oracle bound mechanical evidence. There is no
invented visual-depth constant or claim to reproduce Hersch's complete cavity-depth/class model.

The candidate retains the existing eligibility and reference-unavailability rules. Missing actual shared ink rows in the
class window abstain. It currently measures Mono bitmap output; the fitted-outline diagnostic retains the old methods.
Shapes, images, offsets and finalized advances remain unchanged.

The ideal origin step solves the shared mean-gap target. Source kerning controls the metric blend endpoint, and has no
influence on the full candidate endpoint. After blending and signed whole-pixel adjustment rounding, a conservative
clearance bound preserves left/right ink order over all occupied bitmap row pairs whose closed cells touch vertically,
including diagonal corner contacts. The integer step must exceed their largest facing-edge difference. This strict
closed-cell no-touch rule adapts Hersch's minimum-clearance principle to Mono cells; it is not the paper's grayscale
0.25-pixel constant. It covers the complete bitmap, including ink outside the measurement window. At any positive
optical strength the bound may override the blend; at zero strength metric identity bypasses it. Deliberate letter
spacing remains a subsequent user offset and may intentionally defeat clearance.

Diagnostics retain target/realized area and mean gap, ideal step, rounded unconstrained step, clearance minimum, emitted
step and residual. Clearance can make equal targets infeasible with unchanged glyphs; constrained results must say so. A
conservative wall-order bound may exclude feasible interlocking placements. Equal measured area does not establish equal
perception, and native-size optical assessment remains pending.

### FontForge comparison methods

The reference is the
[pinned FontForge implementation](https://github.com/fontforge/fontforge/blob/c41bdb922285f35defd1e1385adfd13bde1ab32a/fontforge/autowidth2.c).
It weights facing outline-edge separations by `1 / (separation + em_size / 50)^2`, excluding empty shared bands. Native
envelopes are floored in design units, integer band height uses em/100 or em/200, the upper integration band is
excluded, and the result uses C `rint`. The experiment retains the independently checked estimator; pixel-space flooring
would define another adaptation.

### FontForge font-calibrated targets

[Hersch et al., pp. 85–88](https://lspwww.epfl.ch/publications/typography/ptgogf_95.pdf) derives ideal space from
designed reference pairs and distinguishes case and stem/curve combinations. The selected bounded adaptation measures
reference pairs with FontForge's linear estimator rather than implementing the paper's complete perceptual-area model.
It uses source outlines and metrics at the requested axes and size, avoiding global calibration to an individual
produced raster.

Let `S` be adjacent-box separation, `d` the origin step, and `scale = size_px / em`. Reference advances and pair
adjustments below are already in pixels:

```text
D(d) = d + (xmin_right - xmax_left + S) * scale
T(g) = source_advance_px(g) + source_pair_adjustment_px(g,g)
       + (source_xmin(g) - source_xmax(g) + S_source(g,g)) * scale
```

| Eligible pair class                       | Shared target                                           |
| ----------------------------------------- | ------------------------------------------------------- |
| Latin lowercase + lowercase               | `T(n)` from source `nn`                                 |
| Latin uppercase + uppercase               | `T(H)` from source `HH`                                 |
| Latin uppercase + lowercase, either order | `(T(n) + T(H)) / 2`                                     |
| ASCII numeral + numeral                   | `T(0)` from source `00`; experimental numeral extension |

The mixed rule averages linear targets. It adapts the reference-pair principle, without reproducing the paper's
area/height normalization. The numeral rule extends that principle to a designed numeral reference so numeric pairs
remain measurable; it needs its own optical assessment. There are no adjustments specific to reported pairs.

Eligible Latin letters have Unicode category `Ll` or `Lu` and a name beginning `LATIN `; the Unicode data version is
recorded. This conservative boundary is not a complete Script-property classifier. Other scripts, titlecase,
punctuation, symbols, spaces and mixed numeral/letter pairs retain metric placement with an unsupported-class reason.
Source-relative comparison remains available for those pairs.

Calibration uses fixed full reference kerning, independent of the runtime `k` slider. Auxiliary source-only records for
`n`, `H` and `0` do not expand output repertoire, pair-domain size or supported preview text. Older captures can derive
references already present in their repertoire, with that origin recorded. Missing or unusable references, including
empty geometry and targets at or below zero, leave dependent classes unavailable; other available classes continue. No
fixed-target or individual-pair source fallback is substituted silently. Non-finite calibration data is an input error.

```text
D_produced(d_required) = selected_class_target
optical_adjustment = d_required - finalized_advance_left
```

At full calibrated strength, the selected target replaces source pair kerning. At intermediate strength the metric
endpoint contributes source kerning according to `k`. Deliberate letter spacing remains a separate placement addition.
Reference identities, target classes, availability, coordinate/metric policies and implementation identity accompany the
result. Targets are independent of preview text and cache order.

### Fixed-target diagnostic

The former `balanced` model remains a diagnostic using a configured target in em units, default `0.15 em`. This is
FontForge's fallback when font/lookup separation is absent, rather than a typeface density calibration. Its
`configured_target` provenance distinguishes it from the default font-calibrated model. It retains fractional target
pixels until final signed rounding. The experiment's default em/100 bands differ from native AutoKern's em/200; both
remain available for measurement comparisons.

### Source-preserving comparison

The `source_relative` method instead retains the source pair's individual estimated separation:

```text
d_source(k) = source_advance_left + k * source_pair_adjustment
D_produced(d_required) = D_source(d_source(k))
optical_adjustment(k) = d_required - finalized_advance_left
```

Calculate the estimator weights once at adjacent boxes. The result supplies `optical_adjustment(k)` in the
[placement formula](#placement-and-ownership).

The optical experiment retains metric placement for fixed-pitch fonts, empty glyphs and unusable measurement bands,
recording each reason. Source-tabular digit pairs retain metric placement when **Preserve tabular spacing** is enabled;
otherwise they use the selected optical method like other pairs. Balance uses delivered geometry only; the comparison
additionally needs usable source geometry and shared source bands. Non-finite geometry produces an explicit error.
Signed source overlaps retain their meaning in the comparison. Estimator parameters and geometric rules come from the
selected sources and invariants; reported pairs serve as inspection cases rather than production exceptions.

### Isolated measurement adaptations

Numeric spacing is an explicit layout policy. Equal source digit advances identify tabular forms, while the requested
policy determines whether their pair steps must preserve alignment. Allowing optical correction retains their original
images and finalized advances; it can change the relative origins within a number. Fixed-pitch fonts retain their cell
protection regardless of this choice. This is separate from OpenType
[`pnum`/`tnum` numeral substitution](https://learn.microsoft.com/en-us/typography/opentype/spec/features_pt#pnum), which
selects designed proportional or tabular glyph forms.

Reference comparison pins separate binary64 operations (`-ffp-contract=off`, `-fno-fast-math`). Native cached band
traversal, including its restart at touching segment maxima, is part of the reference behavior. Compiler contraction can
change a floored edge by one design unit; parity with these recorded source-operation semantics does not imply parity
with arbitrary FontForge binaries.

The executable experiment offers two produced-geometry policies. Its default measures the union of delivered binary ink
pixels, with each pixel represented by its full cell on the common baseline. This adapts the outline estimator to the
actual Mono output, including scan-conversion changes. A separate fitted-outline option measures the delivered outline
before scanning. These are alternative project hypotheses, not interchangeable measures or established optical
boundaries for Gray coverage.

Source outlines retain continuous design-unit coordinates. Produced pixel coordinates convert to design units before
envelope flooring. Source advances and kerning retain the maintained scalar policy's nearest-1/64-pixel quantization;
this departure from continuous source positioning is recorded with every capture. Integer band height and integer
envelopes mean arbitrary scaling and vertical translation can change quantization; translation by whole bands preserves
the sampling lattice.

The experiment implements gradual source kerning and optical correction, separate span/space offsets and placement-only
wrapping. Optical correction disabled bypasses optical geometry limits while retaining the metric endpoint policy.
Fixed-grid experiments require neutral deliberate spacing. Completed preview and full-domain requests use the same pair
resolver; incomplete results cannot supply layout. Solver limits are diagnostic configuration, not measured browser
budgets. Contextual variants, Gray boundaries, tracking migration and production integration retain their later gates.

The isolated comparison page consumes completed Python solver tables at five strength settings per control. It draws the
captured bitmaps at native and enlarged sizes and applies deliberate offsets during browser placement. Cross-language
fixtures compare that placement with the Python layout result. It supports the captured repertoire and settings;
displaying a comparison does not adopt the optical model into the editor or establish optical acceptance. Pair
diagnostics distinguish an applied correction, a rounded unchanged result, exact agreement and explicit exclusion or
disabled optical correction. Solver records report the target, realized estimated separation and residual before
deliberate offsets; the page's pair measurement includes those offsets. At full strength with neutral offsets, a solved
pair is within half a pixel of its target. These are computation outcomes, not optical judgments.

## Healing research gate

**Deferred:** no contextual ink translation, shape changes or alternate selection are part of the optical-spacing work.

Before implementing a transformation, define its redistribution target, allowed movement and geometric ownership, its
sourced foundation, and the relationships it preserves. The model declaration also specifies its finite neighbor states,
selection rule and reasons for keeping the original form. Establish what contextual ink translation achieves first, then
investigate geometric redistribution where it offers an additional benefit. Stroke contrast, counters, joins, selected
weight and required advances need separate evidence; a smaller whitespace measurement alone establishes a spacing
change.

Verify selected transformations on controlled geometry before a font sweep. Compare placement-only and shape-changing
results separately, then assess their combined behavior.

## Preview, full generation and resources

Preview and full generation use the same solver and settings. Preview requests the forms, ordered pairs and context
states needed by its text. Full generation requests every ordered pair in the selected repertoire, including repeated
glyphs, and all reachable states in the declared context model. For `N` source glyphs, the initial pair domain has `N²`
entries before sparse omission. The context gate must establish coverage of the additional variant states.

Cache identities include font bytes, axes, size, production policy and the solver inputs that affect a stored result.
Geometric analysis can be reused across control changes when its inputs stay identical. The result must be independent
of request order and cache history for completed calculations. Generation retains identities, resolved settings,
variants, targets, placements, context rules and abstentions so a result can be reproduced.

A resource gate measures cold and warm preview latency, peak memory, candidate-production cost, pair-domain growth and
context-state growth on the agreed browser and native targets. These measurements set preview response budgets, work
limits, cancellation behavior and the supported scope before expansion. Repeat the gate when healing adds variants.

Each result identifies completion, cancellation, an exceeded work limit or unsupported input. A complete generation has
covered its declared domain; an interrupted attempt retains its incomplete status. Preview can retain the preceding
completed view while a replacement is pending, with its status visible. Solver-level limits are shared configuration in
both paths, so identical inputs retain identical results. Sparse output represents zero corrections or explicit
abstentions, while the generation record accounts for the entire domain.

## Delivery and assessment

| Stage                | Deliverable and decision boundary                                                                                                                                                 |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reference parity     | Match the pinned estimator on rectangles, curves, open envelopes, empty bands and disconnected marks; verify translation, scale and identity in the source-preserving comparison. |
| Placement comparison | Compare current and optical placement with unchanged forms and neutral user offsets, using the existing source-kerning endpoints.                                                 |
| Control composition  | Add gradual kerning, optical strength and deliberate spacing; verify each offset's single application and the disabled endpoints.                                                 |
| Resource gate        | Set measured latency, memory and work budgets before expanding the matrix; repeat for shape-changing candidates.                                                                  |
| Healing and context  | Select a sourced transformation and redistribution target; validate the candidate lifecycle, two-sided requests and finite coverage.                                              |
| Integration          | Resolve tracking migration, richer text units where needed and healing-aware line breaks; share the accepted result across native preview, WASM, layout and full generation.      |

The first isolated optical matrix retains Roboto, Roboto Flex, Source Sans 3 and Literata at 12/14/16/18/20/24 px,
weights 300/400/700, default remaining axes and independent optical-size endpoints. Include fixed/tabular controls,
punctuation, supported accented scalars, repeated letters, words, straight/curved/diagonal pairs and alternate prefixes.
Keep automatic, selective, overlay and supported Gray pipelines distinct. The healing gate defines its broader corpus.

Mechanical verification covers source parity, determinism, geometry, movement ownership, required advances, control
composition, cache independence and preview/full-generation agreement. Optical assessment inspects identity, contrast,
rhythm, punctuation and word boundaries at native and enlarged sizes in the browser. The separate approved baseline and
published preview selections retain their existing scope. Findings and adoption decisions belong to the revision record.
