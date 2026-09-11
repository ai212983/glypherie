# Outline grid fitting research

Date: 2026-09-07
Status: Experimental implementation; user image review pending

## Research and algorithm choice

Move quality corrections into outline grid fitting before binary scan conversion.
Use shared stroke-width references and source-derived geometry constraints. The
active experiment applies zero bitmap edits and zero outline emboldening.

| Source | Relevant method | Application and limits |
| --- | --- | --- |
| [Hersch, Font Rasterization: The State of the Art (1993)](https://lspwww.epfl.ch/publications/typography/frsa.pdf), sections 5–6, printed pp. 90–99 | Align reference points, share width targets, position symmetry axes; make diagonal borders parallel and their horizontal separation an integer (Fig. 25) | Basis for the implemented diagonal and symmetry constraints. Native hints retain baseline and CVT behavior. Curved stroke fitting remains open. |
| [Zongker, Wade & Salesin, Example-Based Hinting of TrueType Fonts (2000)](https://grail.cs.washington.edu/wp-content/uploads/2015/08/Zongker2000.pdf), sections 2–3 | Transfer anchors, links, distances and interpolation constraints from annotated model fonts, with shared control values | Useful direction for richer constraints. Requires model hints and reliable correspondence; this experiment implements neither template matching nor hint transfer. |
| [Kajiya & Ullner, Filtering High Quality Text for Display on Raster Scan Devices (1981)](https://www.cs.jhu.edu/~misha/ReadingSeminar/Papers/Kajiya81.pdf) | Filter grayscale text for the display/viewing model | Explains filtering, but does not establish that offset averaging followed by a binary threshold preserves details or equal stroke widths. |

The recommendation follows Hersch's explicit geometric rules. It is a subset of
that approach, not a reproduction of a complete published hinting system. Automatic
feature detection, width clustering, solver, and rejection thresholds below are
project choices. The papers describe constraints whose selection may depend on
font annotations; automatic discovery remains a separate problem to validate.

## Implemented subset

[paper_gridfit.py](../../tools/font_probe/paper_gridfit.py) operates on outlines:

1. Read the source outline and its native-hinted counterpart at the requested size.
2. Detect opposite straight diagonal borders in simple all-line contours. Group
   similar horizontal widths across the calibration repertoire into shared integer
   targets. Curved and nested contours retain native hinting for this step.
3. Constrain each accepted pair to the target separation at both ends of its shared
   vertical range. This makes the borders parallel with matching raster phase.
4. Where the source control points establish horizontal reflection symmetry, place
   the axis on a pixel centre or boundary and constrain mirrored point pairs.
5. Solve for the smallest horizontal displacement, retaining native vertical
   alignment. Conflicting constraints or moves over one pixel use native fallback
   with an explicit diagnostic. Quantize to FreeType's 1/64-pixel coordinates,
   preserving reflection pairs, and record the remaining constraint error.
6. Scan-convert once with FreeType mono and preserve its advance metrics.

The implementation has no character-specific or family-specific correction rules.
The calibration runner selects three candidate fonts; the fitter accepts a face,
size and measured width table. Broad input-format and repertoire qualification
still belongs to the generator plan. Width references currently depend on the
selected repertoire, so that repertoire is part of the experiment configuration.

## Initial diagonal/symmetry results and limits

Run [run_paper_gridfit.py](../../tools/font_probe/run_paper_gridfit.py) using the
[probe instructions](../../tools/font_probe/README.md). Output under
`tools/font_probe/out/paper-gridfit/` includes images, bitmaps, constraints, width
references, checksums, versions, and native-versus-constrained topology comparisons.

At weight 400 and 14/16/18/20px, with Literata optical size following pixel size:

| Face | Cases | Custom outline constraints applied | Native fallback after rejected constraints | Topology changes from native hints |
| --- | ---: | ---: | ---: | ---: |
| Roboto | 248 | 72 | 0 | 0 |
| Literata | 248 | 0 | 0 | 0 |
| Source Sans 3 | 248 | 32 | 0 | 0 |

All 744 cases rendered. Roboto `X` is exactly left/right symmetric in the resulting
bitmap at all four sizes. Five focused tests cover diagonal width, symmetry,
repeatability, advance preservation, curve exclusion, shared references and fallback.

These results establish a working constraint subset, not general glyph quality.
Literata receives native hints only. Uneven stems and curved join details remain
visible in the Roboto sheet. Topology equality preserves existing native defects
as well as correct shapes. Native-size text, wider scripts, other families, and
physical panels remain unverified.

The user preferred the new `X`. The next experiment extends shared stem-width
and curve-point interpolation constraints below. Integration into the reusable
generator remains pending image review and broader qualification.

The earlier local pixel-repair and offset experiments remain reproducible evidence
in the [calibration journal](font-calibration-2026-09-07.md). Their rules are
superseded as the active algorithm; previous visual approvals apply only to those
specific historical samples.

## Vertical stems and adjoining curves

[stem_gridfit.py](../../tools/font_probe/stem_gridfit.py) extends the experiment
with paired vertical line edges, including those within quadratic-curve contours.
A sampled nonzero-winding check rejects pairs spanning white counters. Similar
source widths share integer targets across the configured repertoire. Stem edges
snap to pixel boundaries near their native-hinted centre. Curve control points
interpolate proportionally between the source and fitted horizontal anchors;
points outside the anchors translate with the nearest support. Native vertical
alignment and advance metrics remain intact.

This follows Hersch's shared widths and support-point interpolation principles.
The automatic edge detector, sampling density, width clustering and one-pixel
movement limit are project choices. Cubic contours currently receive no vertical
stem constraints. Conflicting anchors, collapsed intervals and excessive moves
produce explicit native-stem fallbacks. Diagonal/symmetry fitting follows this
step; the accepted `X` has no vertical stems and stays byte-identical.

Run `run_paper_gridfit.py --stems`. Evidence and paired 16/18px images are in
`tools/font_probe/out/paper-stems/`. The comparison baseline is the preceding
paper-guided diagonal/symmetry output, rather than raw native hinting.

| Face | Cases | Stem constraints applied | Topology changes from preceding output |
| --- | ---: | ---: | ---: |
| Roboto | 248 | 144 | 0 |
| Literata | 248 | 128 | 2 |
| Source Sans 3 | 248 | 136 | 3 |

All 744 cases rendered with no constraint fallbacks. Eight focused tests pass,
including equal `m` stem widths, counter exclusion, control-point movement,
vertical alignment and preservation of Roboto `X` at all four sizes. The full
matrix also preserves `X` in all three families.

Flagged topology changes remain open for image review: Literata `E` at 14px loses
one enclosed white region and `k` at 20px joins two ink components. Source Sans 3
`d`/`q` at 14px and `4` at 18px each lose one enclosed white region. A change may
repair a native defect or introduce one; these counts do not settle that question.

At 16px, Roboto stems converge to one pixel, restoring visible shoulder details;
at 18px their shared target is two pixels. This size transition and curved bowl
weight need user review. The method constrains straight stems; fitting curved bowl
sides to consistent thickness remains open. Current output is an experiment,
with no promotion to production or board verification.

## Curved bowl side supports

[bowl_gridfit.py](../../tools/font_probe/bowl_gridfit.py) identifies opposed vertical
tangent supports in quadratic contours: consecutive on/off-curve points sharing
an x coordinate. It checks orientation, overlap and sampled ink between supports,
then adds the pair to the same width targets and horizontal interpolation used by
stems. This is automatic support discovery inspired by Hersch's reference-point
fitting; the detector and conservative acceptance guards are project choices.

Run `run_paper_gridfit.py --bowls`; outputs are in
`tools/font_probe/out/paper-bowls/`. Comparison rows show the preceding stem output
and the bowl extension at 16/18px; full sheets include 14/20px. `X` is unchanged
across all 12 font/size combinations. Eleven focused tests cover tangent pairing,
equal stem/bowl support widths, vertical alignment, and counter-loss rejection,
as well as the existing diagonal and stem checks.

The sweep renders all 744 cases. Seven candidate topology changes retain the
preceding stem result: Roboto 14px `6`/`9`, 18px `6`; Literata 16px `a`, 18px `5`,
20px `g`/`9`. Their candidate bitmaps and topology counts remain in diagnostics.
Ten conflicting/collapsed bowl-anchor cases also retain the working stem fit:
Literata 14px `B`/`3`, 16px `3`; Source Sans 3 14/16/18px `B`/`3` and 20px `3`.
The delivered output therefore has zero topology changes relative to the stem
baseline. These explicit fallbacks are algorithm limitations, not solved glyphs.
The guard selects a whole outline-rendered glyph; it edits zero bitmap pixels.

The prior five stem-stage changes are shown in `prior-topology-review.png`, using
retained `paper-stems` records for the before/stem columns and this run for the bowl
column. Inspection shows the Literata `k` arm now connects to its stem, and small
white regions disappear in the other four cases. Literata `E` remains visually
problematic. These inherited results remain pending user review; the bowl-stage
guard compares with the stem baseline and does not qualify earlier changes.

At Roboto 16px, the bowl sides become lighter while straight stems and joins remain
available for comparison. The constraint fixes separation at side tangent supports;
it does not enforce constant normal thickness around the full curve. Curves without
aligned supports, cubic outlines, size transitions and residual heavy arcs require
further work. The experiment remains outside the production generator.

## Exception image review

The user approved the displayed Roboto `bhmnpdqX` before/after groups at 16/18px.
That approval is limited to those samples. No new defect was identified in their
full curves; the remaining review concerns the explicit exceptions above.

[review_bowl_exceptions.py](../../tools/font_probe/review_bowl_exceptions.py) creates
`out/paper-bowls/review/topology-and-e.png` (seven rejected candidates plus `E`) and
`anchor-conflicts.png` (ten retained outputs). Each includes an unhinted source
reference sampled at seven times size with the same variation coordinates. This
reference shows design intent, not the desired target-grid bitmap. The manifest
records input and script checksums and the displayed glyphs.

Anchor conflicts stop before rasterization; their panels explicitly show no
candidate. In the topology sheet, visual inspection suggests some rejected
candidates remove spurious tiny gaps: Roboto 14px `6`/`9` and Literata 18px `5`.
Other candidates add gaps or lose details. Preserving baseline topology is a
conservative guard, not a quality verdict. User review of the numbered cases is
pending; the generator algorithm remains unchanged by this review tooling.

## Source-aware counters and open spaces

User feedback: the earlier right-hand experiments are preferable but below the
quality target; Literata `E` needs work. These exceptions remain unapproved.

[source_constraints.py](../../tools/font_probe/source_constraints.py) replaces the
baseline-count veto in the new `--source-aware` experiment. It builds the filled
source shape from flattened quadratic contours using nonzero winding, then matches
source counters one-to-one with four-connected raster white regions. Missing
source counters and extra raster holes are distinct defects. Matching allows a
half-pixel source-region expansion and requires overlap with at least 25% of the
raster region. A split counter can match its source only once.

When a candidate has a structural mismatch, test vertical outline translations
of -0.25, +0.25, -0.5 and +0.5px before scan conversion. Select by fewer source
mismatches, then prefer a corrected experimental candidate over the preceding stem
baseline, smaller translation and lower geometric area difference. Structurally
sound candidates remain unchanged. Preserve advances; record every tested phase
and residual mismatch. This is outline placement and whole-glyph selection, with
zero pixel edits. Vertical bearing/baseline appearance can change and needs review.

Hersch's discussion of grid placement motivates this experiment; region matching,
search bounds and ranking are project heuristics, not a reproduced paper algorithm
or a validated readability metric. Counter presence alone does not establish
adequate counter size, curve quality or reading comfort.

The Literata `E` defect is a grid-phase closure: the upper serif joins the middle
arm and encloses white space absent from the source. A quarter-pixel phase change
opens the gap at 14/16/18/20px. Similar source-aware checks accept the preferred
Roboto 14px `6`/`9` and Literata 18px `5`/20px `9`. The 18px Roboto `6`, 16px
Literata `a` and 20px `g` use adjusted experimental outlines to retain source
counters without the extra gaps seen in the earlier candidates.

The 744-case sweep renders without errors. Nine cases select a quarter-pixel
translation. Four Literata `k` cases (14/16/18/20px) retain an unresolved source vs
raster component-count mismatch. The ten bowl-anchor fallbacks remain. Seventeen
focused tests pass, including four-connected white-region handling, one-to-one
counter matching, source-spurious-hole acceptance, and `E` alignment. The approved
Roboto `bhmnpdqX` groups at 16/18px remain byte-identical.

Run `run_paper_gridfit.py --source-aware`, then
[review_source_constraints.py](../../tools/font_probe/review_source_constraints.py).
The paired review uses the retained earlier exception manifest under
`out/paper-bowls/review/`; generate that first using the documented commands.
Output in `out/paper-source-aware/review/comparison.png` labels **A: previous
experiment** and **B: new**, alongside the source reference. Cases 1/2/5/7 are
unchanged from the preferred earlier experiments; cases 3/4/6/8 show new shapes.
User review of these results is pending. Production integration remains open.

## Sampled curved-stroke widths

User feedback identifies the right arc of Roboto `6` (18px) and the lower bowl of
Literata `g` (20px) as still needing work. The new `--curves` experiment applies
[curve_gridfit.py](../../tools/font_probe/curve_gridfit.py) after the existing
outline constraints and before source-aware raster selection.

Sample quadratic curves with their control-point interpolation weights. Match
nearby samples with opposed tangents, near-normal separation and ink between
them. Relate each sampled width to a shared font-width reference, preserving
local source variation around that reference. Solve regularized normal-distance
constraints while holding vertical extrema fixed. Displacements above 0.5px retain
the preceding outline with a diagnostic. This is a project extension of geometric
width constraints, not a claim that Hersch specifies this sampling or solver.
No raster pixels are edited.

The first broad pass also changed approved mixed stem/bowl glyphs and serif `X`.
The retained experiment is restricted to glyphs without long straight stems or
diagonals, keeping those cases on the preceding pipeline. That is a geometric
scope limit, not a character allowlist. Integrating curved constraints with those
straight features remains open. Cubic curves remain outside this experiment.

For Roboto 18px `6`, 90 sampled pairs reduce RMS normal-width residual from 0.264
to 0.005px, with a maximum control-point displacement of 0.279px. For Literata 20px
`g`, 218 pairs reduce it from 0.184 to 0.041px, with displacement at most 0.413px.
These values measure agreement with the chosen constraints, not visual quality.
The new raster changes the right arc of `6` and thins the lower stroke of `g`.

The 744-case sweep renders without errors. Relative to the source-aware baseline,
48 Roboto, 63 Literata and 64 Source Sans 3 bitmaps change. Nine Literata cases hit
the displacement bound and retain their preceding outlines. Source-counter checks
retain the same four unresolved Literata `k` component mismatches. All 12 `X`
font/size cases and the approved Roboto `bhmnpdqX` groups at 16/18px remain
byte-identical. Twenty-two focused tests pass across the grid-fitting modules.

Run `run_paper_gridfit.py --curves`, then
[review_curve_constraints.py](../../tools/font_probe/review_curve_constraints.py).
`out/paper-curves/review/comparison.png` shows **A: previous** and **B: curved fit**
for the reported sizes plus nearby-size checks. The output remains experimental;
user image review, broader visual review and production integration are pending.

## Paper-alignment audit after curve review

User review: Roboto 18px `6` improves; Literata 20px `g` develops a notch; Roboto
16px `6` loses roundness; Literata 18px `g` looks identical. The sampled-width
objective therefore fails as a sufficient shape-quality objective.

The implementation is paper-inspired, not a faithful complete reproduction.
Diagonal border placement follows Hersch's concrete rule, while later automatic
pairing, width-only least squares, phase search and rejection thresholds are
project heuristics. The curve fitter lacks an explicit shape-bending or tangent
preservation term, and solves continuous coordinates before quantization. Its
small-displacement penalty does not prevent the observed notches or flattening.

The closest newly reviewed source is [Hobby, Generating Automatically-Tuned
Bitmaps from Outlines](https://doi.org/10.1145/138027.138040), JACM 40(1), 48–94,
1993. The inspected [technical-report text](https://telecom.wiki/download/attachments/819301/CSTR%20148.pdf)
includes position/shape distortion (3.1), medial-axis width analysis of black and
white regions (3.2), integer grid restrictions and font-wide relationships in the
remaining parts of section 3, mixed-integer solution/encoding, and curved outlines
(section 6). It is a stronger candidate for a coherent replacement formulation;
it does not establish success on our exact fonts and sizes. Full reproduction and
validation remain work to plan, not a completed implementation.

[Herz & Hersch 1994](https://lspwww.epfl.ch/publications/typography/tuahsts.pdf)
is relevant for automatic detection and black/white stems, but section 3 explicitly
states that curved stems and terminal elements remain future work.
[Hersch & Bétrisey 1991](https://lspwww.epfl.ch/publications/typography/mbmahof.pdf)
provides structural models and hint matching, with model authoring requirements.
Neither should be cited as implementing our sampled curved-width solver.

Recommendation: retain current images as regression evidence, stop adding isolated
curve heuristics, and map a complete chosen formulation to implementation before
further raster experiments. Hobby is the first candidate to assess in detail.
The newly identified papers are also linked in the methodology reference.

## Later work and replacement shortlist

Follow-up research broadens the comparison before choosing a replacement.
Shamir & Rappoport (1996) explicitly extract curved typographic elements; Shamir
(2003) describes automatic hint generation combining glyph features, font-wide
information and ordered constraints. These are relevant later approaches in the
same field; direct completion of Herz & Hersch's stated future work is unverified.
The 1996 institutional abstract and 2003 author's abstract establish scope;
full-text review is needed before translating either into an implementation.

StrokeStyles (2022) supplies a newer geometric stroke/junction analysis and public
code. Its application is stylization; using its representation for grid fitting
would be a project extension. Neural Font Rendering (2022), coauthored by Shamir,
addresses multi-scale rasterization but learns existing target bitmaps and retains
artifacts. It does not establish how to generate better targets for our defects.
All four sources are linked in the [reference](../reference/font-legibility.md).

Compare Hobby's distortion/grid formulation with Shamir's automatic hinting before
selecting a backend. Assess how each represents curved strokes, preserves shape,
resolves competing constraints and shares measurements across glyphs. Consider
StrokeStyles only if structural extraction is the missing component. Retain the
reviewed `6`, `g`, `E`, joins and `X` as acceptance examples across nearby sizes.
Algorithm selection and implementation remain pending.

## Shamir and Hobby: algorithm comparison

The [ACM reader](https://dl.acm.org/doi/epdf/10.1145/636886.636887) provided Shamir's
full text after direct PDF retrieval failed. Inspection of sections 3–6 replaces
the abstract-only assessment above. The user deferred prototype implementation
to make this comparison first.

Shamir classifies outline points, extracts segments and compound features, and
constructs absolute-position, distance and ratio constraints. Shared measurements
parameterize those constraints. Section 3.6 removes lower-priority constraints
from over-constrained points and cycles, then orders dependencies. Font parameters
and character metrics receive priority; remaining ties may be arbitrary with a
warning. Ratio constraints position otherwise unconstrained points. Arcs and bows
use feature-side anchors and distance relations; complex features such as serifs
require declarative hints or a predefined constraint set (3.5). Detailed feature
extraction depends on the 1996 paper. Output is native font hint instructions.

Hobby instead balances geometric distortion terms with integer grid variables.
The report covers position, stretching/bending, black and white widths, approximate
symmetry and shared font parameters. Section 6 maps polygonal feature analysis
back to spline control points. Its lattice reduction and encoding are substantial
implementation work. The distortion weights and feature rules are heuristic;
the formulation provides neither exact shape preservation nor guaranteed visual
quality.

For our reported loss of roundness, Hobby offers a more direct formulation to
assess: shape preservation participates in the same objective as width and grid
placement. This is an engineering recommendation, not comparative visual proof.
Shamir is attractive when the desired output is a conventionally hinted font and
explicit feature priorities are appropriate. Its published method does not provide
a joint curvature-preservation objective that can simply replace our curve fitter.
Neither paper establishes success on our calibration fonts and sizes. Keep the
current images as regression cases; select and map a complete method before coding.

## Independent prototype comparison

[compare_paper_prototypes.py](../../tools/font_probe/compare_paper_prototypes.py)
compares two independent, bounded implementations. Both start from the same
per-size instantiated TrueType outlines. Shamir executes generated native
instructions; Hobby solves for adjusted controls. Both use FreeType MONO with
dropout disabled, without native-hint seeds, raster repairs or candidate selection.

- [Hobby subset](../../tools/font_probe/hobby_prototype.py): joint position,
  stretching/bending, black/white width and grid objective on quadratic controls.
  Departures include normal-ray feature pairing, fixed shared-width tables,
  exact-only symmetry, simplified grid supports and local integer coordinate
  descent instead of the paper's lattice solver.
- [Shamir subset](../../tools/font_probe/shamir_prototype.py): straight/tangent
  features, width clusters, priority/cycle resolution and native CVT/MIAP/MIRP/IUP
  instructions. Departures include omitted serif/slant/counter/ladder rules,
  implicit extrema and overshoot handling, OS/2 height zones instead of extracted
  recurring heights, and IUP instead of an explicit Ratio graph.

The 744-case corpus covers 62 ASCII letters/digits, three calibration fonts and
14/16/18/20px at weight 400, with optical size following size where supported.
All cases render without errors; every Hobby integer solve converges locally.
The two prototypes differ in 692 cases. Source-region diagnostic flags occur in
39 unhinted, 30 Hobby and 14 Shamir cases; these are inspection aids, not a quality
ranking. Advances differ in 730 A/B cases; fixed-cell strips isolate glyph shape,
so spacing remains unevaluated. Thirteen focused tests pass, including native
instruction execution, integer-solver checks and review-cell bounds. A repeated
run reproduces all 23 report/font/image artifacts byte for byte.

User feedback is preliminary: both look good, especially Shamir. The user
explicitly clarified this is not final approval. An initial assistant judgment
that both damaged joins was premature. The discussed concerns are Roboto 16px
`6` lower-bowl corner connections, `b` lower-left stem/bowl join, and `h`/`n`
shoulder flatness. These require comparative review, not automatic rejection.

[review_prototype_concerns.py](../../tools/font_probe/review_prototype_concerns.py)
places these four cases beside the saved source-aware pipeline and subsequent
curved-fit experiment, with enlarged and native-size glyphs. Blue boxes identify
the discussed regions. Earlier variants retain their original scan settings;
this sheet is visual history rather than a controlled scan-conversion comparison.
The lower-left `b` stem projection also exists in the earlier variant, so it does
not establish a new Hobby regression. User image review remains open.

## Controlled Shamir versus source-aware comparison

The user prefers Shamir in the comparison above; final approval remains open.
[compare_shamir_pipeline.py](../../tools/font_probe/compare_shamir_pipeline.py)
keeps both algorithms fixed and compares identical source outlines with common
dropout-off scan settings, including the source-aware pipeline's selection trials.
The corpus expands to 81 characters across three fonts and four sizes: 972 cases.
The gallery includes bowls, shoulders, diagonals, openings, punctuation and native
text in both polarities. Text uses common source-font kerning and each method's
rendered advances. The [probe guide](../../tools/font_probe/README.md) gives the
reproduction command and gallery location.

All cases render successfully. Shamir supplies no composite-level constraints in
36 cases: Roboto `; :` and Source Sans 3 `i j ; : % " =`, at all four sizes.
Component hints can still execute. These cases were initially mislabelled
unhinted; the focused experiment below corrects that interpretation.
Adding punctuation changes shared width measurements; 52 of the 744 previously
tested Shamir glyphs consequently have different bitmaps. Review this expanded
corpus as a new candidate. The source-region diagnostic flags are also used by
the previous pipeline's selector, so their counts cannot rank the methods fairly.

Two focused harness tests cover common scan flags/restoration and actual kerning
with method-specific advances. Two complete runs reproduce all 68 font, image,
report and gallery artifacts byte for byte. Human image review is the next gate.

## Focused Shamir diagnosis: e, X and punctuation

The user identifies `e`, `X` and small punctuation across all three fonts as
refinement targets. [trace_shamir_cases.py](../../tools/font_probe/trace_shamir_cases.py)
compares the saved Shamir output with x-only, y-only and unhinted controls at
14/16/18/20px. The gallery includes 192 focused cases, with enlarged and native
pixels and point/constraint traces; 972 cases receive the rendering checks.

`X` has no recognized width features in any calibration font. Its remaining
height anchors cannot enforce diagonal stroke widths. Literata's 14px `e`
changes markedly when y hints are removed: vertical placement and width rounding
need attention alongside the missing counter relationships. Removing hints is
a diagnostic control, rather than a proposed rendering policy.

The recognizer also pairs some same-facing sides in the sans-serif `e` outlines.
An optional opposed-side rule rejects such pairs using contour direction. This
is a generic extraction experiment; it leaves the published-method subset and
its other limitations in place. Candidate B applies only this rule, using the
same repertoire and scan settings. It changes 49 of 972 bitmaps: 45 Roboto and
four Source Sans 3 cases. Literata and `X` remain unchanged. Those differences
require image review before promotion. The default remains the saved candidate.

The punctuation ablations demonstrate that component programs execute even when
the composite has no own instructions. A native-font test reproduces this; the
reports and gallery now distinguish component hints from composite constraints.
This separates punctuation coverage work from small simple-outline rounding.
Nineteen focused tests pass. All 12 default font files reproduce the saved bytes;
the optional rule remains isolated from the default rendering path.

The review gallery now shows source shape, current Shamir and the opposed-side
candidate. Axis ablations remain in the diagnostic code and report for targeted
debugging; they are omitted from the user-facing comparison.

## Literature check after opposed-side regression

User review rejects the opposed-side candidate as visually worse. The original
Shamir subset remains the preferred baseline. The direction filter demonstrates
that a plausible local recognition rule alone does not establish better fitting.

[Turner & Lemberg 2003](https://www.tug.org/TUGboat/tb24-3/lemberg.pdf), pp. 432–434,
uses opposite directions together with grouped segments, mutual-best pairing,
serif links, round/flat classification and font-wide alignment zones. This is a
more complete recognition/fitting sequence than the tested filter. Placement
details still depend on the implementation. The current
[ttfautohint manual](https://freetype.org/ttfautohint/doc/ttfautohint.html) explicitly
says diagonals receive no special treatment, limiting its relevance to `X`.

A search of [Shamir's publication list](https://faculty.runi.ac.il/arik/site/files/Shamir-cv.pdf)
and related literature found no verified direct extension of the 2003 constraint
hinter for these cases. His later [Neural Font Rendering](https://arxiv.org/html/2211.14802v2)
learns existing target rasters; its reported comparison covers lowercase letters
and retains artifacts. It supplies no demonstrated repair for our `X` or punctuation.

[StrokeStyles 2022](https://doc.gold.ac.uk/autograff/post/papers/strokestyles_2022/)
is relevant to generic recognition of overlapping strokes and junctions using
outline/interior/exterior geometry, without training data or templates. Its
demonstrated goal is stylization; using it to improve grid fitting is a hypothesis.
[Hersch 1993](https://lspwww.epfl.ch/publications/typography/frsa.pdf), pp. 97–98,
directly describes paired parallel diagonal borders and phase control, already
represented in the reference. Neither source proves quality on our exact cases.

Recommended next investigation: audit the missing feature and relationship model
against Shamir's full method and its 1996 extraction prerequisite. Assess strokes,
junctions, counters and diagonal pairs together before another fitting change.
Keep the preferred raster baseline fixed during that recognition audit.

## Shamir method audit — 2026-09-08

Scope: the current [prototype](../../tools/font_probe/shamir_prototype.py), saved
controlled/focused reports, [1996 full text](https://pages.cs.huji.ac.il/sites/www-arir/storage/extraction-typographic-elements.pdf)
sections 3–5, and [2003 full text](https://dl.acm.org/doi/epdf/10.1145/636886.636887)
sections 3–4.1. The 1996 PDF was located on the coauthor's university site;
the 2003 text was read through ACM's browser reader. This supersedes the earlier
abstract-only assessment of the extraction prerequisite.

The diagnostic report's implementation hash matches the current source:
`6c2a1f23440828392fbcecd83177b82bca97700382f6684d7960807c066e2746`.
The audit changes documentation only. The preferred Shamir output and rejected
opposed-side experiment retain their review status.

### Method-to-code mapping

| Stage | Published method | Prototype and consequence |
| --- | --- | --- |
| Outline preparation | 1996 §3 prepares missing extrema, inflections and tangent points. | Uses existing TrueType points. Implicit curve extrema receive no feature identity. |
| Classification | 1996 §§3–4 classifies point/segment types under tolerances. | `features()` requires coordinate equality within `1e-6`; tangent-control spans stand in for curved support. Near-axis and differently encoded curves can be missed. |
| Feature recognition | 1996 §§4.1–4.3 gives separate definitions for slants, bows, arcs and mixed curved/straight strokes. | Outputs axis, endpoint pair, width and straight/curve label. It has no slants, full segment membership or distinct curved-feature models. |
| Serif knowledge | 1996 §4.4 uses reusable sequence recognizers. | Missing. Faithful serif coverage includes a reusable model-authoring task; it is not achieved by a direction filter. |
| Shared measurements | 2003 §3.4 gathers recurring, typed heights and distances. | `width_clusters()` averages every detected pair in broad groups. Heights are baseline zero and OS/2 x/cap-height, with a fixed proximity test. |
| Segment constraints | 2003 §§3.5–3.6 constrains a segment representative and links its other points. | Adds independent endpoint anchors/widths without segment alignment links. Multiple pairs from one bar also contribute repeated width measurements. |
| Local/global choice | 2003 §3.5 chooses Dist or PDist according to proximity to a global value. | Every width uses the nearest cluster and PDist. There is no local Dist path or explicit proximity decision at this stage. The fixed 100px CVT cut-in strongly favors shared widths. |
| Graph resolution | 2003 §3.6 prioritizes, resolves conflicts and sorts dependencies. | This broad structure is present, but operates on the reduced endpoint graph. Character-width, counter, ladder and ratio relationships are absent; ties use point IDs. |
| Interpolation | 2003 §3.2/Table I uses explicit Ratio relations, mapped to IP. | Emits IUP for remaining points. It does not construct the paper's explicit interpolation graph. |
| Translation | 2003 §4.1 emits ordered native instructions using CVT values. | Implemented for the supported cardinal-axis relations. Native execution tests establish functioning bytecode, not completeness of the preceding model. |

### Evidence in the review cases

- **`X`:** all 12 font/size cases have zero detected width features. Width,
  parallelism and crossing balance are therefore outside the current model.
  Implementing the paper's slant recognition is a prerequisite; successful
  recognition alone would still require diagonal constraint translation.
- **Literata 14px `e`:** zero global height anchors. Inner top point 34 moves
  from y=6.566 to 7px; outer top point 8 moves from y=7.294 to 8px through the
  width link. Crossbar points 15/27 move from y=3.458/4.228 to 3/4px.
  This proves the placement sequence, rather than proving that one revised
  constraint would fix the final shape.
- **Sans-serif `e`:** Roboto and Source Sans 3 each report 12 feature pairs at
  14px. Four pairs describe the same crossbar width through different endpoint
  combinations. Source Sans 3 has zero global height anchors; Roboto has two.
  Pair counts should not be interpreted as counts of independent strokes.
- **Punctuation:** Roboto 14px `.` has only a y-width feature; its `!` has only
  the dot's y-width feature. Source Sans 3 `!` has dot features on both axes,
  with no recognized width for the long stroke. Missing feature coverage is
  distinct from the composite case, where component hints can execute but the
  composite arrangement has no own constraints.

### Recommended sequence

1. Build the prepared geometry and typed feature representation from the 1996
   definitions. Include segment membership, curve extrema and diagonal pairs.
   Inspect overlays on the existing cases before changing raster output.
2. Build recurring height/width statistics from those features and construct
   segment-level constraints, including local versus shared distances. Preserve
   feature identity through conflict resolution and interpolation.
3. Compare the resulting coherent candidate with the preferred baseline across
   all fonts and nearby sizes. Keep manual pixel edits outside this experiment.

These are substantive missing stages, not evidence that the full Shamir method
has failed. Some tolerances and hint policies still require engineering choices;
the papers do not guarantee expert-quality bitmaps for every font or size.

## Prepared geometry and recognition checkpoint

The target remains Shamir 2003. Its 1996 extraction prerequisite now has an
independent implementation foundation:

- [shamir_geometry.py](../../tools/font_probe/shamir_geometry.py) resolves
  implicit quadratic points and component transforms, inserts exact curve
  extrema by subdivision, classifies joins and retains source-segment/parameter
  provenance. Prepared IDs are distinct from original TrueType point indices.
- [shamir_features.py](../../tools/font_probe/shamir_features.py) groups contiguous
  near-straight spans and produces typed stem, bar, slant, bow, arc and mixed
  curve/straight candidates. Segment membership survives recognition.
- [review_shamir_features.py](../../tools/font_probe/review_shamir_features.py)
  writes SVG overlays and selectable feature pairs, covering 192 focused cases
  and reporting recognition counts for all 972 calibration cases.

Recognition uses project tolerances of 0.003em and 0.04 radians. Interior checks
use sampled curves. These choices remain subject to review. Curves are preserved
by preparation; no glyph coordinates are grid-fitted and no font hints are changed.

All 12 `X` cases now have slant candidates: four in each sans-serif case and five
in each Literata case. Literata also has extra stem candidates near its serifs;
grouping and semantic rejection remain necessary. Roboto `e` has overlapping
candidate relations, and Literata's curved matching is incomplete at the initial
tolerances. Dots have classified extrema but no complete dot model. The 16
focused composite cases are resolved for geometry analysis, while composite
hint translation remains separate work.

Six new geometry tests cover exact subdivision, rotated/reversed stroke pairs,
white-space rejection, segment membership, inflection classification and
implicit/composite geometry.
Existing Shamir and diagnostic tests also pass. These checks establish geometric
behavior, not visual acceptance or completion of the 2003 method.

Recognition overlays are internal diagnostics. The user reviews rendered glyphs
and native text; the implementer owns recognition validation and paper fidelity.

## Rendered prepared-segment candidate (2026-09-08)

[shamir_segment_fit.py](../../tools/font_probe/shamir_segment_fit.py) now connects
prepared outlines, typed recurring measurements, representative-point constraints,
projected diagonal distances and explicit `IP` interpolation to native TrueType
execution. Composite outlines are decomposed before fitting. The source font and
saved Shamir baseline stay unchanged.

[compare_shamir_segments.py](../../tools/font_probe/compare_shamir_segments.py)
produces `tools/font_probe/out/shamir-controlled/segments/index.html`: native text,
source outlines and enlarged A/B glyphs across the 972-case corpus. A is the saved
Shamir prototype; B is the prepared-segment experiment. Each baseline bitmap is
reproduced and checked against the saved report before comparison. The report also
separates unhinted preparation differences from fitting differences. B changes
716 of 972 bitmaps; preparation alone changes 46. Those 46 cases include an
outline-storage confound and cannot attribute every changed pixel to constraints.

Implementation choices beyond the papers:

- Candidate side conflicts use nearest-width ownership and a 0.18em upper bound.
  This is a conservative heuristic, not completed serif/junction recognition.
- Typed clusters need three distinct character votes within 0.01em. Local widths
  retain local `Dist` constraints when no recurring value is close enough.
- Height clusters distinguish flat and round extrema. Tangent control points
  follow their extremum. Diagonal freedom preserves already constrained heights
  or horizontal positions; groups conflicting in both coordinates are skipped.
- Free coordinates use neighboring contour representatives, with explicit `IP`
  inside their coordinate interval and displacement outside it.
- Exact subdivision is rounded to integer font units for TrueType storage;
  prepared coordinate error is bounded by 0.5 font unit per coordinate.

The candidate remains a partial implementation of the 2003 method. Serif automata,
compound-junction rules and counter ladders are still open. Its rendered output
has regressions: Roboto 14px `X` has a thinner centre, Source Sans 3 14px punctuation
is uneven, and Literata 16px loses weight in several stems and bowls. These are
implementation findings, not evidence against the complete paper. Keep A as the
preferred baseline while diagnosing these mechanisms. No manual glyph fixes or
raster edits are applied.

Sixteen Shamir tests pass, including native projected-distance execution with
preserved height constraints, deterministic output, recurring-measurement voting,
preparation mapping and existing extraction/graph tests. All 972 candidate glyphs
execute with FreeType's pedantic native interpreter. Human review concerns rendered
shape and text; feature overlays remain an internal debugging tool.

## Preserve curved stroke width under height anchoring (2026-09-08)

User review identified excess weight in upper parts. Native instruction tracing
confirmed the cause for Roboto 14px `e`: its outer top moved from about 7.53px to
8px, while the inner top moved from 6.50px to 6px. Two independently rounded
height anchors displaced the recognized stroke-width constraint, doubling the
upper stroke to 2px.

The segment candidate now keeps the outer height anchor for a recognized arc and
derives its inner edge through the width relationship. The connected inner side,
including tangent controls and equivalent representatives, follows that edge.
The same rule applies to upper and lower arcs. It uses feature geometry rather
than glyph names. Pairs with no outer height anchor keep their existing policy.

Roboto 14px `e` now has outer/inner heights of 8px/7px: a 1px upper stroke.
Across 972 cases, 320 corrected arc relationships retain a dependency on their
outer anchor; 54 bitmaps change from the previous candidate (51 Roboto, 2 Literata,
1 Source Sans 3). Recognition coverage still limits where this correction applies.
Existing diagonal and punctuation issues remain separate work.

The gallery retains A as the saved Shamir baseline and updates B to the corrected
candidate. Previous candidate artifacts are preserved in
`tools/font_probe/out/shamir-controlled/segments-before-width-fix/`.
Eighteen Shamir tests pass, including native upper/lower arc widths under competing
height anchors; all 972 calibration glyphs render with the pedantic interpreter.

## Combined-constraint and fidelity audit (2026-09-08)

Scope: current corrected segment candidate B and saved baseline A. This audit
adds diagnostics and documentation; it changes neither renderer nor review fonts.
[The diagnostic runner](../../tools/font_probe/audit_shamir_segments.py) executes
instruction prefixes in temporary fonts across all 972 cases. It compares source,
prepared outline, cardinal constraints, diagonal constraints and final interpolation.
All source/candidate font hashes are checked before and after the run. Results are
in `tools/font_probe/out/shamir-controlled/segments/constraint-audit.json`.

The 2003 full text was reread in the
[ACM reader](https://dl.acm.org/doi/epdf/10.1145/636886.636887), specifically pp.
137–143 (§§3.2–3.6). The comparison below refers to this candidate, superseding
claims about missing stages that were subsequently added to B. Baseline A remains
the older, smaller subset.

### Executed causes

Widths below are exact FreeType outline bounding-box spans in pixels, rather
than bitmap-column counts or advance widths. Advance widths remain equal to A
in all 972 cases.

| 14px case | Source/prepared | After cardinal constraints | After diagonal constraints | Final |
| --- | ---: | ---: | ---: | ---: |
| Literata `X` | 9.484 | 9.484 | 9.484 | 10.328 |
| Source Sans 3 `X` | 6.766 | 6.766 | 6.969 | 7.188 |
| Roboto `X` | 8.016 | 8.016 | 7.938 | 7.609 |
| Literata `!` | 1.969 | 1.969 | 1.969 | 2.312 |

- **Width drift is real and size-dependent.** Literata 14px `X` expands about
  8.9%, entirely during final interpolation. Roboto 14px instead contracts;
  the defect is uncontrolled shape change, not a uniform widening operation.
  Source Sans 3 18px `X` contracts from 8.703px to 7.453px.
- **Diagonal fitting and interpolation are separate procedures.** The former
  chooses a freedom vector from whether *any* point in a group owns x/y. The
  latter still moves free coordinates using contour neighbors. They are never
  jointly resolved. For one Source Sans 3 14px `X` segment, its endpoint angle
  changes from 62.62° after diagonal fitting to 59.66° after interpolation
  (source 62.68°). Interpolation can therefore alter a previously fitted slant.
- **Literata `!` has only a short lower stem feature.** Its upper rounded section
  receives no horizontal feature constraint. Final interpolation carries the
  lower feature's displacement into the top: its left/right upper control
  positions move by unequal amounts (approximately +0.156px/+0.375px), increasing
  width and changing the curve. This is incomplete coverage interacting with
  fallback interpolation.
- **Source Sans 3 14px `!` has zero selected stroke features.** Its lower stem
  anchors move; the unsupported upper section follows by +0.234375px in y.
  Its top moves from 9.375px to 9.609375px. The original taper is retained in
  outline coordinates but sampled at a different vertical position, producing
  a different pixel pattern. This case is not explained by horizontal widening.
- Across the corpus, 79 cases expand and 95 contract by more than 0.5px relative
  to source outline width. Final interpolation changes width in 561 cases.
  These counts locate effects; ordinary hinting also changes dimensions, so the
  counts alone are not defect classifications.

### Fidelity assessment

**Confirmed: B is not a faithful implementation of the complete published method.**
This conclusion follows from the implementation structure, independently of visual
quality. It does not establish that a faithful implementation would solve every
reported case.

| Paper requirement | Current B | Assessment |
| --- | --- | --- |
| §3.3 feature hierarchy, serif/complex-feature automata; §3.5 reusable constraint sets | Basic feature pairs and greedy side ownership; no serif/complex-feature templates | Confirmed omission |
| §3.5 counter/ladders; §3.6 character-width constraints and metric priorities | No counter, ladder or character-width constraints | Confirmed omission, relevant to width drift |
| §§3.2/3.6 dependency resolution including projected and Ratio relations | Resolves cardinal point graphs, then emits diagonals and interpolation separately | Confirmed structural departure |
| §3.6 resolve representative graph first, attach other segment points afterward | Alignment/control-point relations participate in cardinal conflict selection before resolution | Confirmed structural departure |
| §§3.4–3.5 recurring typed measurements and local/global distance choice | Present, with project clustering and proximity settings | Broad mechanism implemented; exact numerical fidelity is unspecified |
| §3.2/Table I explicit Ratio/IP | Emits IP, with project contour-neighbor and out-of-range displacement policy | Instruction family matches; reference selection is an implementation choice |
| §3.6 priority rules | Fixed numeric priorities, separate ownership checks and special curved-anchor reorientation | Partial correspondence; current policy is not a demonstrated reproduction |

The paper permits engineering choices: it uses proximity tolerances, gives an
example occurrence threshold, permits arbitrary unresolved ties with a warning,
and does not supply exhaustive executable rules for reference-point selection or
all rounding settings. These unspecified details must not be presented as proven
paper violations merely because our results are poor. In particular, the previous
upper-curve fix is a project constraint policy, not a rule quoted from Shamir.

The justified next implementation is a combined representative-level constraint
model that includes projected relations, width metrics and interpolation
references, resolves their dependencies, and then attaches segment points.
Feature-coverage gaps for punctuation and serif shapes remain explicit work.
Validate that final interpolation preserves selected feature relations before
requesting another user review. Preserve A as the preferred baseline.

## Combined model review closure

The [conformance review](shamir-model-conformance.md) now owns the finalized
paper-to-code contract and remaining fidelity gaps. A separate combined-model
implementation replaces sequential fitting for internal validation. Its final
constraint checks pass across 972 cases; recognition and authored template
coverage remain necessary before claiming full method fidelity or issuing
another visual candidate.

## Recognition and template gap closure

The combined-model conformance work now includes broken supports with preserved
intervals, analytic curve interiors, curved-extremum matching tolerance, regular
stem ladders and authored bracketed-foot/flat-terminal/rounded-terminal recipes.
Shared Ratio parameters have an explicit native arithmetic translation. The
[conformance review](shamir-model-conformance.md) records the exact coverage,
project choices and interpreter checks. All 972 cases pass the final-constraint
checks, and the specific feature-coverage assertions pass for all three fonts at
14/16/18/20px. Existing user-review images remain unchanged.

## Combined-model rendered checkpoint

The `combined` gallery compares the conformance-checked fonts with all 972 saved
Shamir baseline glyphs, reproduced exactly. B has clear regressions: Roboto 14px
`X` is asymmetric, its `a` extends below the baseline, and Literata 14px `e` is
substantially deformed. The gallery preserves complete glyph bounds and includes
native text. Constraint residuals and feature-presence assertions did not establish
correct feature selection or shape preservation. The
[conformance review](shamir-model-conformance.md) remains open on those questions;
A remains the preferred baseline. These results do not establish a paper defect.

## Constraint fix pass

The [conformance review](shamir-model-conformance.md) records the correction of
silent alignment loss and unstable near-parallel coordinate completion. The
updated `combined` gallery renders hash-verified checked fonts; the previous
candidate is retained under `combined-before-fix`. The lower Roboto `a` artifacts
are removed, while overall shape quality remains subject to image review.
Paper-fidelity and adversarial reviews support the scoped corrections, with
explicit qualifications on interpolation and numerical policies.

## Scalar dependencies and full-corpus review

The scalar dependency correction fixes Roboto 14px `F` and restores 577 alignment
relations previously removed as false cycles. Independent native tests pass.
Review now includes original rejected relationships and all 972 rendered cases,
with separate semantic, numerical and per-font visual reviewers. It fails visual
acceptance: overlapping-contour connectivity and conflicting feature/template
constraints remain unresolved. The [conformance review](shamir-model-conformance.md)
records introduced and retained cases, including the traced Roboto 14px `H` gap.
