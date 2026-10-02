# Approved baseline diagonal fitter

Base: Skrifa 0.46.2, Fontations commit `f886c9069b08eaddcb1caced3a44b0d8291a159a`, registry SHA-256
`d4febebda507fb889c545a37a135517769d1391941013561292897961d1887d6`. The original MIT and Apache-2.0 licenses are
retained. The package is renamed `skrifa_baseline`; the registry dependency remains the independent reference renderer.

Maintenance owner: the project maintainer. The user accepted 001.02 on 2026-10-02; production uses the separate approved
baseline snapshot.
Upstream contribution remains a separate decision. Rebase against a pinned base, review the isolated source diff, and rerun
disabled parity before publishing new specimens.

## Foundation

- [Hersch 1993, §6/Fig. 25](https://lspwww.epfl.ch/publications/typography/frsa.pdf): paired straight borders,
  parallelization, horizontal width quantization, and equal grid phase.
- [Microsoft VTT DStroke](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/doc/VTT%20Language%20Reference/vttlang.html#cmd_DSTROKE):
  endpoint-controlled diagonal borders.
- [Shamir 2003](../../../../docs/references/papers/2003-shamir/): shared width parameters, dependency relationships, and
  priority-based constraint conflict handling.

## Iteration status

001.02 is the current accepted model, with no newer active candidate. See the accepted 001.02 policy at the end and
its [acceptance record](../../../../docs/revisions/001/02-light-continuity.md#acceptance-and-promotion-2026-10-02).
The following 001.01 sections retain the historical foundation; 001.02 supersedes their integer-width transfer and
coverage-only conversion descriptions.

001.01 is closed and accepted for production on 2026-10-02 following the user's explicit assessment that all current
published quality is acceptable. Ordinary automatic 1-bit generation now enables the accepted diagonal constraints
and source-relative width policy. The independent registry renderer remains the reference. Broader unpublished
observations remain documented for future investigation; existing mechanical and conservative regression guards remain
in force. See the [acceptance record](../../../../docs/revisions/001/01-diagonal-weight.md#acceptance-and-production-promotion-2026-10-02).

## Experimental policy

The constants and automatic feature detector below are project hypotheses, rather than values prescribed by the papers.
The accepted extension applies to Mono automatic fitting in the default script group. Automatic feature detection
remains a project hypothesis rather than an optical acceptance algorithm.

1. Detect adjacent on-curve straight borders with vertical span ≥1/8 em and horizontal/vertical slope magnitude 0.1–2.
   Pair opposite directions within an angle tolerance expressed as `|s1-s2| ≤0.08(1+|s1*s2|)`, overlapping by at least
   half the shorter vertical span. Require positive ink at nine interior sample points under nonzero winding; curves in
   this locator are flattened to 64 subdivisions. Width bounds are 1/50–1/5 em. Mutual best pairing minimizes horizontal
   separation plus taper. Exact score ties use source point order.
2. Prepare Y edges/strong points and X edges/strong points using upstream rules. Retain edge-owned Y coordinates and
   vertical segments spanning ≥1/8 em as hard anchors. Compute a common slope from these prepared coordinates. Estimate
   source perpendicular width from the midpoint horizontal gap and mean source slope. Transfer the nearest positive
   horizontal standard stem's Mono fit ratio to that source thickness, project onto the dominant control axis, and
   bound rounding distortion as detailed in the current width tweak below. Add `ceil(1+|slope|)` 26.6 units to horizontal
   separation to bound endpoint-rounding loss. Thus phase control is approximate, with a declared small geometric safety
   margin. Threshold and coverage conversion stay fixed.
3. Treat vertical segments spanning ≥1/8 em as hard X anchors. Diagonal constraints take precedence over shorter
   near-vertical caps. Each pair supplies two parallel-border equations and one horizontal separation equation. Solve
   connected components jointly for endpoint X and unanchored Y, minimizing squared displacement from prepared X/Y.
   Preserve supported source-overlap attachments to other contours: intersect their flattened boundaries, test endpoint
   containment, and retain the coordinate normal to the nearest long axial source segment (aspect ratio ≥14:1, matching
   upstream direction classification). Retain both coordinates when axial support is absent. Overlaps between two
   diagonally controlled contours remain outside this attachment model; nested contours are not attachment witnesses.
   Endpoints adjacent to off-curve points initially retain both prepared coordinates. An inconsistent component may
   retry with the terminal-curve dependencies described below; unmodeled curve junctions remain protected. The
   minimum-norm solve uses a Gram matrix and rank-aware elimination; redundant compatible equations are supported. Bound
   displacement normal to each border to half a pixel, and along it to one eighth of source border length. This permits
   N-like joins to slide along anchored stems. Inconsistent equations, collapsed Y spans, or excessive movement leave
   the component unapplied. This solve is a project implementation choice inspired by the constraint formulation,
   separate from Shamir's published dependency scheduler.
4. Commit accepted endpoint ownership before axial X point alignment and strong/weak interpolation. Shared endpoints
   have one coordinate variable. Quantize once to 26.6, with residual tolerance bounded by coefficient-weighted
   half-unit rounding error. Other points retain upstream derivation. Glyphs with detected pairs prepare Y before X and
   defer weak Y interpolation until the joint plan is committed; other glyphs retain upstream ordering.

This version handles individual straight segments. Curved diagonals, incomplete pair detection, and constraint conflicts
remain evaluation limitations. The configured corpus has a connected-letter regression gate. Broader size/weight
diagnostics still expose broken joins, recorded in the
[iteration record](../../../../docs/revisions/001/01-diagonal-weight.md); they block acceptance. Zeno coverage,
threshold 128, linear layout metrics, and 3-bit fitting stay upstream.

## Patch surface and validation

Changes are confined to `src/outline/hint.rs`, `src/outline/mod.rs`, `src/outline/autohint/instance.rs`,
`src/outline/autohint/hint/mod.rs`, `src/outline/autohint/hint/outline.rs`, and the added `diagonal.rs`/`curved_diagonal.rs`.
`HintingInstance::set_diagonal_constraints` defaults off; reconfiguration creates a disabled instance.
`AdjustedMetrics::diagonal_pairs` exposes detected/applied/unapplied counts for diagnostics. Unapplied includes
constraint conflicts and an inactive upstream fitting stage.

`tests/iteration.rs` in the parent generator checks disabled parity against registry Skrifa across all ordinary glyphs,
sizes, profiles, and engines, plus candidate determinism, unchanged grayscale/layout, and reported-case coverage. The
generator build hashes vendored source, generated data, manifest, licenses, and this policy into candidate provenance.

The restored, pinned `font-test-data` 0.9.1 dev dependency supports the upstream unit suite, omitted from the registry
manifest. Run `cargo test --manifest-path tools/generator/vendor/skrifa-baseline/Cargo.toml --lib` from the repo root.

## Current 001.01 width tweak: source-relative transfer

The generator's `diagonal-01` renderer enables `set_diagonal_stem_relative(true)` whenever diagonal fitting is enabled.
The low-level switch defaults off and reconfiguration resets it, preserving disabled upstream parity. The earlier
width rule is retained internally for solver unit tests; pre-tweak regression data preserves earlier 001.01 results.
There is one published iteration implementation.

Shamir 2003 §§3.2/3.4 and Fig. 18 motivate shared characteristic widths, relative feature dimensions, and coordinated
size transitions. VTT `RectilinearDistanceOfDiagonal` and `DStroke` in `TTGenerator.cpp` distinguish stroke direction
from X/Y width control. Skrifa's upstream `edges::stem_width` supplies the Mono standard-width rounding rule and, in
its smooth horizontal branch, a quarter-pixel bound on snapping distortion.

The following transfer is a project hypothesis based on those mechanisms, not a reproduction of VTT or Shamir:

1. Measure the source perpendicular thickness `t` and choose the nearest positive horizontal standard stem `w`.
2. Fit that standard to Mono's positive whole-pixel width `W`. Set desired thickness to `t * W / w`, retaining source
   thick/thin ratios while sharing the standard stem's size transition. Without a standard, retain `t`.
3. For prepared slope `s = dx/dy`, project desired thickness onto the dominant control axis:
   `a = t * W / w * sqrt(1 + s*s) / max(1, abs(s))`. Choose the nearest whole-pixel axial width only when it changes
   `a` by less than one quarter pixel; otherwise retain fractional `a`, with a one-pixel axial minimum. The quarter-pixel
   guard's use for Mono diagonals is an explicit experiment, extending the upstream smooth-stem mechanism to prevent
   excessive distortion from a second rounding step.
4. Convert back to horizontal separation, retain the existing rounding safety margin, and use the existing parallel
   border solve, ownership, attachment and displacement constraints. No raster threshold or per-glyph exception changes.

Fractional axial widths relax equal phase; parallelism remains constrained. This tradeoff must be assessed visually.
The first trial always rounded the projected width to whole pixels and made Roboto 18 w too heavy. The bounded trial
reduces that excess, but still increases Roboto 18 v/w beyond upstream ink. It is available for review, not accepted.
Literata 18 v/y remain unchanged because the existing curve/attachment constraints reject their components. Known
broader join failures remain acceptance blockers.

The synthetic thick/thin test checks source contrast and bounded geometric error against independent expected widths.
Integration witnesses check recovered border thickness, unchanged original Roboto 14/16 improvements, deterministic
14–20 size transitions on ordinary slices, layout/grayscale parity, and no additional join failures relative to the earlier results within 001.01.
The web index always shows the latest revision and iteration. For revision 001, symbol comparisons use reference
as the baseline, with shared origins/baselines and native pixel differences.

## Current 001.01 terminal-curve correction

Literata 14 px y supplied a concrete coverage failure: both pairs were detected, but fixing curve-adjacent endpoints in
both coordinates made their parallel-border and width equations inconsistent. There were no hard axial or inter-contour
anchors at those endpoints. This correction belongs to the accepted 001.01 model.

[VTT XSHIFT](../../../../docs/references/VisualTrueType/doc/VTT%20Language%20Reference/vttlang.md#xshift) carries a child by
its parent's X displacement. [Shamir §§3.2–3.3](../../../../docs/references/papers/2003-shamir/paper.md) supplies Dist/Ratio
dependencies and geometric point/segment roles. The following automatic terminal classifier and control-order
interpolation are explicit project hypotheses grounded in those mechanisms:

1. Try the original endpoint ownership first. Only an inconsistent equation system can retry; successful fits keep their
   previous geometry and ownership.
2. Recognize a terminal curve adjoining a straight diagonal endpoint: at least two quadratic controls or exactly two
   cubic controls, ending at a non-diagonal on-curve point whose opposite side is straight. Retain one-control
   quadratics, mixed curves, curve-to-curve junctions, and independently owned controls or far endpoints. Preserve hard
   axial and inter-contour anchors.
3. Release only the recognized diagonal endpoint's X coordinate; retain its prepared Y. The adjacent control inherits
   its X displacement. The far control and far on-curve endpoint retain their prepared X. Interior quadratic controls
   interpolate the displacement by their order in the spline. These relationships preserve the prepared terminal
   tangent vectors' X components; Y continues through upstream fitting and interpolation.
4. Stage control updates before committing anything. Preserve the existing solve, endpoint movement, rounding, and
   residual guards. Bound dependent X motion by the existing half-pixel budget. Reject ownership conflicts atomically.
   Reserve the controlled X coordinates, including stationary far anchors, against subsequent X alignment and
   interpolation; dependent controls do not acquire Y ownership.

The broader trial that released arbitrary curve joins broke Literata k at 14 and 19 px. Its continuous curve junctions
fall outside the terminal classifier and remain protected. A trial using near-contour proximity was discarded; the
current implementation contains no additional proximity threshold or raster-based acceptance rule.

Synthetic tests cover quadratic/cubic terminal tangents after X interpolation, interior spline displacement, protected
controls and far endpoints, continuous curve junctions, and atomic rejection. Integration checks cover Literata y at
14/16/18/20 px, source thick/thin contrast above the existing 14 px one-pixel minimum, the k witnesses, original Roboto
fixes, disabled/reference equality, layout/grayscale equality, determinism, and no additional joins broken in the broader
diagnostic sweep. The Q/x coverage extension below follows this correction. This model is included in the accepted production state.

## Current 001.01 short and curved slant coverage

Literata x's shorter opposing borders meet the geometric length threshold but not the former vertical-span threshold.
Use source chord length for straight-diagonal eligibility. Shamir §3.3 sorts and matches slanted features by angle and
extent. Using Euclidean extent with the existing one-eighth-em minimum is a project hypothesis: orientation should not
by itself discard a supported short border. Existing direction, overlap, positive-ink, width and mutual-matching checks
remain. Newly covered short features receive a conservative width floor; retain prepared thickness if it already exceeds
the transferred target. This extends coverage without a glyph, font, point or row exception.

Q's lower element needs curved features and both control axes. [Shamir §§3.2–3.6](../../../../docs/references/papers/2003-shamir/paper.md)
grounds point roles, Dist/Ratio dependencies, curved/slanted matching, representative points and priority resolution.
[VTT relative shifts/interpolation](../../../../docs/references/VisualTrueType/doc/VTT%20Language%20Reference/vttlang.md)
grounds parent-relative point offsets. These sources do not prescribe the following automatic classifier or numerical
solver; these are explicit project hypotheses:

1. Match monotone quadratic runs with finite slanted chords, compatible opposite tangents, projected overlap and nine
   positive-ink witnesses. Source extent is between one-eighth and one-third em; control deviation from the chord is
   bounded by one-sixteenth em. At least one terminal tangent must have a diagonal role; two axial extrema describe a bow,
   outside this model. The existing 14:1 axial tolerance distinguishes these roles.
2. Choose the width axis from the source chord's dominant direction. For pure curved pairs, require an independent
   interior control on at least one border: paired two-control curves leave only terminal/cap motion after retaining
   tangent dependencies. The trial allowing these pairs broke Literata 17 px c's join; reject this unsupported geometric
   role in every glyph. Supported mixed line/curve roles are described below.
3. Complete upstream weak interpolation before measuring the prepared spline. Mixing fitted extrema with raw controls
   creates artificial control reversals and invalid width/tangent relations. Group shared endpoints into one component;
   preserve hard axis anchors, prior ownership, endpoint tangent offsets, straight caps and neighboring multi-control
   dependencies. Unsupported neighboring shapes remain unchanged. Single-control quadratics cannot independently retain
   both terminal tangents and are deliberately outside this model.
4. Transfer source thickness using the shared diagonal reference described below, independently of the movement axis.
   Impose a signed midpoint representative-width residual, retaining the straight model's rounding-safe axial minimum.
   The earlier additional normal floor and prepared-width ratchet are superseded. Interior controls or supported mixed
   border roles supply width freedom; tangent controls carry endpoint displacement; neighboring controls use Ratio
   interpolation toward their stationary far point. This remains a bounded fit, not a reproduction of Shamir's graph
   scheduler.
5. Give anchors and source point roles priority. Activate monotonicity bounds when minimum motion would introduce an
   extremum. Back off incompatible width residuals and bound accepted coordinate movement by half a pixel. Stage the
   complete component, retain rounding-residual checks, and require whole-offset tangent/cap links to remain exact on the
   26.6 grid. Reserve both axes independently and prevent a previously owned point from being moved by another component.
   Applied counts mean a bounded component fit, not that every desired standard width is attained.

Synthetic tests exercise both axes and reflection, independent affine curve evaluation, source contrast, cap/tangent
relationships after interpolation, ownership, unsupported curve types/roles and atomic rejection. Integration witnesses
check Q/x detection and application, x border parallelism/contrast, Q's global extrema, the c join control and existing
y/k/Roboto controls. No test requires ink count to move in a preferred direction.

The [evaluation rules](../../../../docs/evaluation.md) and Rust evaluator separate mechanical failures from descriptive
geometry/topology/coverage signals. Pixel additions/removals and pair counts alone do not judge quality or acceptance.
The iteration is accepted and closed; the acceptance record distinguishes reviewed output from broader unassessed
diagnostic observations.

## Current 001.01 optical-weight corrections

The user reported excessive weight in Literata 14 px Q's lower tail and x/y terminals, and Source Sans 3 16 px w/x/y.
The other reviewed cases were accepted. Accepted renderings may evolve: the user permits some volatility, and snapshot
identity is not an optical acceptance contract. Disabled parity, untouched profiles, layout, ownership and valid outlines
remain contracts.

### Coherent terminal preparation

Shamir §§3.2–3.3 and VTT XSHIFT describe dependent point offsets. Upstream Skrifa's `align_weak_points` computes the
prepared weak coordinates. The earlier straight retry added endpoint displacement to raw off-curve controls and then
marked them touched, preventing their upstream interpolation. Its preserved offsets were therefore relative to an
incompletely prepared spline. Complete X/Y weak interpolation before source-relative straight fitting as well as curved
fitting. This ordering is an explicit project hypothesis. A reflected synthetic witness with independently moved
anchors checks the prepared tangent offsets, rather than merely mirroring dependency weights.

### Reference class and symmetric curved widths

Shamir §§3.3–3.4 gathers characteristic dimensions by feature type. In VTT `TTGenerator.cpp`, `ClassifyStroke` chooses
X/Y projection from stroke direction; `Stroke` selects the diagonal CVT class separately. Choosing a different axial
reference solely because a curved chord changes its control axis introduces a weight discontinuity. Straight slants
already use the horizontal stem reference even for shallow directions. The explicit project hypothesis is that supported
straight, curved and mixed diagonal roles share this reference. Projection remains geometric and may use either axis;
the hypothesis does not claim that all bars and stems share a weight.

Curved components now solve toward the source-relative target in either direction, with the existing backoff, motion,
ownership, tangent and role guards. Remove the additional one-pixel normal floor and prepared-width ratchet. Retain the
rounding-safe one-pixel dominant-axis minimum and its margin: isolated trials removing these caused visible principal
stroke gaps, despite passing the outline dependency constraints. Those constraints do not establish raster continuity.
No raster threshold, per-font exception or phase search is introduced.

### Mixed line and quadratic borders

Source Sans 3 w's inner strokes have opposite line and two-control quadratic portions. Their straight portions alone
lack the existing half-shorter-span overlap; the full mixed portions meet it. Shamir §§3.3–3.6 supports matching source
feature roles before resolving constraints. The following automatic mixed-role support is a project hypothesis:

- Admit a line against a supported quadratic run, with existing finite extent, angle, overlap, width, winding and
  mutual-best checks. Never add line/line pairs to the curved plan. Retain the pure two-control/two-control bow rejection;
  a mixed component obtains its width variable from a supported line translation and curve dependencies. Conflicting
  anchors or insufficient freedom reject the complete component.
- Evaluate lines with an affine endpoint basis. Preserve each line's prepared tangent by equal endpoint displacement
  in its control axis, and preserve quadratic endpoint-control offsets. Join supported mixed components across shared
  points and directly adjacent transverse caps.
- A transverse cap is flat in both source and prepared longitudinal coordinates. Retain those coordinates and cap
  endpoint order while permitting transverse thickness to follow the width equations. This Dist role avoids freezing
  cap length across opposite-side corrections. A mixed component may include pure-curve pairs. Other components keep
  their whole-offset cap links. Non-transverse or independently owned neighboring geometry stays protected.
- Apply cap-order bounds during the solve and check them again after rounding. Stage all coordinates and ownership
  until the component passes the existing guards; unsupported single-control quadratic dependencies remain excluded.

Synthetic tests use rotations/reflections with deliberately unequal axis standards, preserved line/curve tangents,
longitudinal cap coordinates, ordered cap endpoints, bounded movement and atomic anchor conflicts. The Source Sans
integration witness checks additional inner coverage, cap placement/order, connectivity and layout. Existing bow, c/k,
normal-corpus and broader-sweep controls remain. No test requires ink count to increase or decrease.

## Renderer role

This source tree is the candidate fitter, independent of the other local renderer. Working 001.02 starts from accepted
001.01 and coordinates the shared horizontal diagonal standard with its extra-light stem policy: retain subpixel
normal weight and omit the later axial one-pixel floor when that standard is extra-light. Dropout control in the
candidate generator supplies monochrome visibility. This ratio transfer remains a project hypothesis grounded in
FreeType/Skrifa stem widths and Hersch §7; it is not FreeType diagonal-fitting parity. Motion, tangent, anchor,
ownership and rounding-separation guards remain unchanged. See the
[continuity record](../../../../docs/revisions/001/02-light-continuity.md) for validation and pending optical assessment.
Future experiments change this tree without editing the approved baseline.
The generator, capture adapter and raster/output stages remain shared. Reference rendering uses the separately pinned
registry library. Revision and iteration labels are metadata; no per-iteration Cargo feature selects production.


## Accepted 001.02: dropout and fractional shared widths

The preceding 001.01 descriptions record the approved baseline foundation. Production uses the separate
`skrifa-baseline` snapshot, now promoted to 001.02. The user accepted the current result on 2026-10-02; see
[001.02](../../../../docs/revisions/001/02-light-continuity.md) for evidence, classifications and remaining questions.

Candidate extra-light diagonal transfer honors the standard's actual subpixel fit; the generator adds outline-driven
Mono dropout control based on Hersch §7 and TrueType SCANTYPE, adapting those rules to coverage conversion. Raw
coverage and threshold remain unchanged. Gray and disabled fitting keep independent-reference parity.

The shared-width experiment reuses pinned FreeType's smooth horizontal `stem_width` branch for enabled candidate
Mono/default scripts, including glyphs with no diagonal pair. It clears only HORIZONTAL_SNAP in the effective scale,
retaining Mono, Y snapping, anchors and existing placement rules. Each horizontal standard stores the actual fitted
width; diagonal thickness transfer uses fitted/scaled rather than reconstructing an integer. Source thickness roles,
projection/rounding margins, movement bounds, tangent dependencies and ownership remain in force. This adaptation is
a project hypothesis grounded in FreeType's width policy and Shamir's shared feature dimensions, not FreeType Mono
parity. Synthetic transforms, source-width witnesses, the conservative join sweep and unchanged gray/disabled paths
provide mechanical evidence. The user's web assessment accepted the current weight, continuity and placement tradeoffs,
including the disclosed remaining binary upright step near weight 465. There is no active newer candidate.
