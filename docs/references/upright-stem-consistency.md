# Preserving upright stem weight across local shape changes

The [Literata investigation](../revisions/001/03-spacing-kerning.md#equal-source-upright-weight-investigation)
identifies a source-width relationship lost during automatic fitting. This research asks how to preserve a principal
upright when a narrower upper feature shares one of its borders. It proposes a general model direction; no rendering
change or optical acceptance follows from this note.

## Recommendation

Preserve **local source-stem identities through shared-edge aggregation**, associate recurring stem widths with a
font-wide standard, and retain and resolve the separate width relations when their points are shared. Fit the principal
body and the narrower head through one consistent dependency system, then transfer the displacement to the crossbar,
foot and curves through their actual attachments. The strongest foundations are
[Shamir (2003), §§3.2–3.6](papers/2003-shamir/) for feature relationships and dependency resolution, and
[Hobby (1993), §§3.2, 3.6, 4 and 4.2](papers/1993-hobby/) for local width measurement and font-wide width consistency.

This is narrower than replacing the renderer, but it requires changing the present assumption that every upstream
upright is an authoritative fixed anchor. The
[current investigation](../revisions/001/03-spacing-kerning.md#equal-source-upright-weight-investigation) owns the
observed discrepancy and existing model limits. An already fitted one-pixel stem and an already fitted two-pixel stem
can have the same source width; collecting both as reference anchors does not resolve that contradiction.

The adaptation should extend the existing
[coupled whole-outline model](../hobby-fitting.md#coupled-whole-outline-widths), which already shares straight/curve
variables and certifies joins and selected apertures. Upright movement is a new ownership boundary for that model; it is
not evidence that a parallel fitter or wholesale solver replacement is necessary. Native-owned axes stay fixed.

Equal source widths establish a relationship to preserve, **not which integer width is optically correct**. At 16 px, 93
font units scale to about 1.488 px, whose independent nearest rounding would be one. The existing peers' two-pixel
result therefore cannot be justified by that rounding alone. Preserve or explicitly reassess the font's common
standard-width/grid-fitting decision; do not select two merely because most captured donors already have two. A
successful correction must resolve the shared class coherently while retaining the intended size transition.

## What the papers contribute

| Source                                                                                                 | Applicable mechanism                                                                                                                                          | Limit for this problem                                                                                                                                                                                  |
| ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Turner & Lemberg (2003), feature analysis and grid fitting, pp. 431–434](papers/2003-turner-lemberg/) | Opposing local segments define stems; segments are grouped into edges; reciprocal best links distinguish stems from serifs.                                   | This explains the existing mechanism, but its greedy single-best linking is not a solution to competing local widths after edge aggregation.                                                            |
| [Hersch (1993), §6, pp. 96–98, Figs. 22–25](papers/1993-hersch/)                                       | Shared snapping values make related stems receive coherent raster widths despite small outline differences.                                                   | Standard-width snapping operates on the feature selected by a hint. It cannot by itself repair body fitting governed by the head's narrower pairing.                                                    |
| [Shamir (2003), §§3.3–3.6, pp. 138–144](papers/2003-shamir/)                                           | Extract overlapping segment features, collect type-specific global sizes, express shared point relationships, resolve dependencies and competing constraints. | Feature extraction and complex-feature constraints remain necessary. The paper does not give a ready-made attachment rule for every curved terminal or a proof that its priorities suit this renderer.  |
| [Hobby (1993 report), §§3.2, 3.6, 4.2 and 6](papers/1993-hobby/)                                       | Measure local width from medial contact pairs, couple related relative width errors, cluster font-wide widths, and retain curve geometry during deformation.  | The full method includes global integer decisions and a larger optimization pipeline. Reusing only its relative-width penalties with contradictory frozen upright anchors cannot correct those anchors. |

### Local feature identity must survive shared edges

Turner and Lemberg's segment-linking test scores opposite-facing segments by separation and overlap, then retains a best
candidate. Their explanation distinguishes local segments from fitting edges, which collect segments at a common
coordinate. This identifies where competing relations can be reduced to one controlling decision; it does not establish
that the narrowest pair should control every section of a shared edge. See the paper's segment-scoring code and
reciprocal-link conditions on pp. 432–433 ([public paper](https://www.tug.org/TUGboat/tb24-3/lemberg.pdf)).

Shamir §3.3 matches overlapping segment pairs to features; §3.5 creates point relations from each feature. A shared
point is inserted once, rather than copied once per feature. For the reported geometry, the body and upper section can
consequently retain different width relations to the **same** right-border position. The proposed adaptation must
preserve a connected border, not create a seam between two independent copies. Shamir §§3.2 and 3.6 also explain why
constraints must be ordered and conflicting ones resolved, rather than applied as sequential independent movements
([publication](https://doi.org/10.1145/636886.636887)).

### Standard widths are separate from local stroke recognition

Hersch §6 describes reference snapping values consulted during hint displacement computation. Shamir §3.4 gathers
recurring sizes by feature type and associates the appropriate local constraint with the corresponding global size.
Hobby §4 introduces shared integer font parameters, with equation (20) substituting the same width parameter into
separate feature relations; §4.2 clusters measured widths separately by measurement direction, weighted by medial
length. These are mechanisms for making related decisions jointly, rather than preserving every upstream result as a
trusted target ([Hersch's paper](https://lspwww.epfl.ch/publications/typography/frsa.pdf),
[Hobby's author publication list](https://9p.io/who/hobby/pubs.html)).

A body-width class must remain distinct from genuinely thinner heads, hairlines and serifs. The papers support
feature-sensitive classes and local measurements; they do not authorize a font-wide minimum width that erases contrast.
Membership tolerances, support requirements and class selection for the current variable-font pipeline still need
sourced adaptation and validation. No fixed list of letters is necessary to define the relationship.

### Width matching and attachment are different responsibilities

Hobby §3.2, equations (4)–(5), measures widths through local medial contact pairs and penalizes projected relative width
error. Equation (17) in §3.6 correlates those errors, weighted by width, direction and feature length. It does **not**
require intentionally different source strokes to become equally wide. Section 6 extends shape distortion to Bézier
control points while using simpler geometry for feature analysis. The stored report's mathematical audit records
notation issues and checked equations; use it before implementing formulas.

Shamir §3.2 supplies absolute, distance and ratio relations. A characteristic stem uses a parameterized distance, while
otherwise unconstrained points can follow ratio interpolation. This supplies an established dependency model, not a
complete curve-quality guarantee. Moving a stem border still requires ownership of the adjoining crossbar and curved
foot; simply moving the body endpoints can kink or detach their attachments. The current model's shape, native-axis and
validity protections must remain authoritative for unsupported geometry.

This limitation is corroborated by FreeType's
[strong/weak interpolation discussion](https://freetype.org/autohinting/interpolation.html): global edge interpolation
can damage contours spanning several edges, while contour-local IUP-style interpolation also fails when necessary
extrema are not constrained. Neither interpolation rule alone supplies safe curve ownership or join preservation.

## Ranked implementation directions

1. **Source-local upright constraints with a shared standard-width decision.** Extend the owning fitter to retain the
   body and upper pairings, establish a trustworthy common width decision, and solve their shared border and dependent
   attachments together. This best matches the observed failure and the existing staged pipeline. Its specific bounded
   ownership/solver adaptation is a project hypothesis, not a result already demonstrated by these papers.
2. **Repair upstream edge-link aggregation.** Preserve multiple local reciprocal stem relations when several segments
   become one edge, then resolve them using standard widths and dependencies. This addresses the suspected information
   loss closest to its origin, but needs a runtime trace and broader upstream compatibility analysis. Replacing the
   smaller-width preference with a larger-width preference is not a paper-supported universal policy and does not
   establish correct feature and attachment behavior across fonts.
3. **Adopt the full font-wide optimization framework.** Hobby's shared integer variables and font-wide distortion model
   provide the most comprehensive foundation. This is a larger change to width selection, placement and optimization; it
   is not justified as the first implementation for this isolated defect.

The first direction is the recommended investigation boundary. It must explicitly amend upright-anchor ownership before
implementation; a later curve-fitting stage cannot fix an upright that the model requires it to keep fixed.

## Decision boundary

A prototype should demonstrate retained local pair identity and a coherent standard-width choice before judging pixels.
Use the reported setting, the existing nearby-size evidence, other weights/optical sizes, source-derived examples with
shared borders, transformed equivalents, genuine narrow features, multiple attachments and deliberately conflicting
ownership. Reject or abstain when native-owned coordinates, shared attachments, validity or bounded movement cannot be
preserved. A width-consistency goal does not authorize exceeding the existing movement budget; any such case must
abstain or follow an explicit model revision with separate validation. Keep finalized layout and the separately approved
comparison independent.

Check source-to-upstream and source-to-proposal widths separately, including the upper/body contrast, crossbar, foot,
counters and continuity. Compare an independent reference with the current Rust evaluator, then inspect the actual
monochrome browser output across the agreed corpus. A two-pixel body at one size, a passing topology count or equal
pixel totals would not establish optical acceptance. The choice of one versus two pixels for the whole body-width class
and its transitions remains an explicit assessment question.

The online search also located the EPFL collection's
[Herz & Hersch (1994)](https://lspwww.epfl.ch/publications/typography/tuahsts.pdf) and
[Hertz et al. (1998)](https://lspwww.epfl.ch/publications/typography/awmfatpe.pdf). They were screened as related work,
not adopted as additional implementation foundations. The existing reviewed corpus already supplies the required
feature, width-class and dependency concepts; any later reliance on an absent paper requires the
[paper ingestion and review workflow](papers/README.md#paper-rules).

## Research follow-up: preserving source curves and attachments

The
[source-detail assessment](../../out/diagnostics/upright-stem-implementation-20261029/verification/upper-stem-detail-review.md)
separates inherited upper-head simplification from introduced cap and foot distortion. These require distinct validation
questions: preventing new damage does not establish restoration of detail already lost upstream.

### Applicable primary sources

- **Hobby, Generating Automatically Tuned Bitmaps from Outlines, report §§3.1, 3.6 and 6.**
  [Author publication and report link](https://9p.io/who/hobby/pubs.html),
  [stored §6](papers/1993-hobby/paper.md#6-curved-outlines), [mathematical audit](papers/1993-hobby/audit.md). Section 6
  keeps Bézier control points as the adjusted variables. Polygonal approximation is used for intermediate feature
  analysis, with subdivision refined to an error tolerance; the final output remains curved. Its equation (33) extends
  the source-outline displacement measure to corresponding curve samples. Section 3.6 couples relative width errors.
  Together these provide the strongest foundation for fitting widths and curves in one system. These are soft distortion
  measures, not guarantees that a particular tangent or detail survives. The stored report differs from the
  author-hosted report and is not verified journal typesetting; equation references follow the stored report and its
  audit.
- **Shamir, Constraint-Based Approach for Automatic Hinting of Digital Typefaces (2003), §§3.2–3.6.**
  [Publication](https://doi.org/10.1145/636886.636887), [local copy](papers/2003-shamir/paper.md). Absolute, distance
  and ratio relations connect points to feature anchors and font-wide parameters. Shared points enter the dependency
  graph once; otherwise unconstrained points can use ratio interpolation. This offers a mechanism for a cap point to
  follow its surrounding feature rather than remain accidentally fixed. The appropriate anchors, feature ownership and
  conflict policy still need geometric justification; the paper does not provide an automatic rule for this cap or every
  curved attachment.
- **Hersch, Font Rasterization: the State of the Art (1993), §§2, 5–6.**
  [EPFL original](https://lspwww.epfl.ch/publications/typography/frsa.pdf), [local copy](papers/1993-hersch/paper.md).
  Section 2 supplies the quadratic Bézier basis and endpoint-derivative identities needed for this TrueType input.
  Sections 5–6 explain grid phase and related-width snapping. They support the curve mathematics and width/placement
  decisions, but do not establish the proposed ownership rules or guarantee retention of every visible detail at small
  sizes.
- **FreeType strong/weak interpolation notes** are useful implementation evidence rather than another paper.
  [Official notes](https://freetype.org/autohinting/interpolation.html) show that edge-based interpolation can damage
  contours spanning several edges, while contour-local interpolation also fails when important extrema are not anchored.
  This supports caution about moving controls independently; the specific cap/foot failures here are established by our
  captures, not by that document.

### Recommended adaptation

Extend the [owning coupled whole-outline model](../hobby-fitting.md#coupled-whole-outline-widths), retaining the useful
source-derived width classes and common-standard decision. Use the original curves without hinting as the shape
reference; upstream fitting remains the reference for alignment, layout and movement accounting. Body, head, cap and
foot must share endpoint/control variables and explicit attachment ownership in one constrained deformation. A point
that lies between differently moved owners must receive a justified relation, rather than an incidental zero
displacement.

Treat prevention and restoration as separate requirements within that joint solve, not successive coordinate-moving
passes with fresh movement budgets:

1. **Prevent new damage.** Validate every affected curve and corner, including off-chain controls and extrema beyond the
   width-sampling stations. Existing whole-interval tangent/curvature certificates can reject the observed foot
   reversal; source-relative anchor relations can constrain the cap. These are project constraints built on the cited
   geometry, not guarantees supplied by the papers.
2. **Restore missing source features.** Include original-source shape measures and explicit relations for the
   source-derived features whose detail must survive. A positive tangent dot product and unchanged curvature sign alone
   still admit a vertical endpoint tangent where the source had a horizontal component. Adding those guards would
   prevent some damage without resolving the upper-left profile loss. A soft source-displacement objective alone also
   does not guarantee that the optimizer preserves that feature.

This is an extension, not a drop-in application of the existing solver. The adopted coupled slice currently requires
native Y and pins upright X. The reported case has automatic fitting on both axes. A prototype must define how certified
uprights can participate in the width solve while retaining any native-owned coordinates. Keeping fitted Y is a possible
initial restriction; it must not be relabeled as native-Y ownership or implemented by simply deleting the existing
guard. Quadratic specialization of Hobby's cubic exposition uses Hersch's basis and the project's existing quadratic
machinery.

### Suggested next steps and decision boundary

1. Record failing, source-derived checks for the compressed head profile, cap relationships and foot curvature. Keep the
   current frozen candidate as a comparison; the existing width and topology checks remain useful but incomplete.
2. Run an isolated feasibility prototype of the joint source-relative solve before further maintained integration. Begin
   with the reported 15/16px cases plus transformed synthetic curved heads, caps and multiple attachments. Assess both
   source-shape restoration and the decided body width under the same original movement budgets.
3. If feasible, extend validation to nearby sizes, weights/optical sizes, genuinely narrower features, conflicting
   ownership and native-axis controls, then independent native/WASM replay and browser assessment. Unsupported or
   infeasible geometry must abstain; an abstention that restores the original thin body is a limitation, not a fix.

The papers do not prove that a two-pixel body, every source feature, retained Y and every existing frame can all be
preserved simultaneously. Geometric restoration may or may not alter the delivered bitmap: subpixel changes can cross
scanner boundaries, while identical pixels can hide different outlines. Inspect both layers. Do not select weights,
phases or point exceptions by searching for desirable pixels in the reported glyph. No renderer changes follow from this
research note.
