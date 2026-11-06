# Monochrome geometry and spacing

<!-- cspell:words HarfBuzz GSUB GPOS ttfautohint unhinted Skia PathOps autofit afloader rekerning SCANCTRL SCANTYPE fpgm maxp VARC thresholded unrepresentable quantizer CGAL Adafruit Crosspoint pdfontconv Tophat rint tensorfont TypeFacet fullwindow yinyangfit nonconstant -->

Combine native and automatic Mono fitting on independent axes, preserve source shape and weight relationships, and
assess continuity and reading rhythm under bitmap placement. Fitting, scan conversion and layout remain separate:
changing a scanner preserves fitted geometry and metrics; changing fitting can legitimately change both.

The [revision index](README.md) owns renderer identities and iteration status; the
[generator API](../../../crates/generator/API.md) owns runtime contracts; [Hobby fitting](../../hobby-fitting.md) owns
geometric models and adoption mechanics. Findings retain their stated font, size, axes and review scope. Classification
follows the [evaluation rules](../../evaluation.md): mechanical parity does not extend an optical approval beyond its
reviewed scope.

<a id="topics"></a>

## Fitting and source geometry

### Selective native hints and automatic fitting

The working Mono preview uses automatic fitting with an optional **Use font hints** preference. Native instructions own
axes they constrain or measure; automatic fitting supplies independent remaining axes. Disabling hints selects upstream
automatic Mono on both axes. Historical controls, settings and compatibility mappings belong to the
[generator API](../../../crates/generator/API.md#working-candidate-fitting).

[Turner and Lemberg](../../references/papers/2003-turner-lemberg/paper.md) ground independent X/Y analysis.
[TrueType projection, freedom and interpolation](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions)
ground ownership: measurements reserve axes, unchanged coordinates may still be constrained, UTP can clear touched
flags, and IUP without touched points contributes no ownership. PostScript stems/alignment zones provide analogous
source evidence.

**Project adaptation:** combine corresponding native/automatic coordinates only on demonstrably independent axes.
Native-controlled coordinates remain exact; horizontal metrics follow the X owner. Failed execution, explicit native
hint disabling, point-defined vector dependencies, constrained composites, implicit unreserved-axis movement,
transformed PostScript outlines or incompatible commands retain the complete native fit. This is axis fallback, not
per-point completion. Wholly automatic glyphs retain eligible source-relative correction; executed scan state remains
authoritative.

**Confirmed geometric correction; scoped browser assessment:** Roboto 400/16, `wdth=100`, has nearly equal source `i t
f` stems but native Y-only instructions leave unequal X widths. Automatic X restores equal bodies with native dot/hook
heights; inspection at 12/20 px supports local continuity and balance. Broader weight, counter and spacing assessment
remains pending. Both-axis native ownership intentionally retains native output despite possible imbalance.

### Mono fitting and engine selection

Upstream controls use registry Skrifa `Target::Mono`: font hints first selects `Engine::AutoFallback`, while Automatic
Mono forces `Engine::Auto(None)`. Both consume runtime font bytes without family, glyph, size or axis exceptions. The
[engine interface](https://docs.rs/skrifa/0.48.0/skrifa/outline/enum.Engine.html) and
[FreeType load targets](https://freetype.org/freetype2/docs/reference/ft2-glyph_retrieval.html#ft_load_target_xxx)
distinguish engine selection from scanning. Instructions alone do not establish suitability for binary output.

These controls retain the selected upstream outline exactly and can feed independent scanners. Gray retains upstream
Normal automatic fitting. The former `vertical_only`/`vertical-01` composition of source X and Smooth Light Y is retired
and rejected, not an alias for the current policy. Its findings are retained under earlier controls below.

### Scan-control-only program fallback

**Confirmed selection defect, corrected:** Literata 400/16, `opsz=12`, has equal 93-unit `i`/`j` stems. A seven-byte
scan-only `prep`, no `fpgm` and no glyph programs caused upstream selection to retain interpreter outlines, delivering
two versus one columns. Automatic Mono fits both bodies to two columns.

[prep](https://learn.microsoft.com/en-us/typography/opentype/spec/prep) cannot move glyph outline points;
[SCANCTRL/SCANTYPE](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#scan-conversion-control)
govern scanning. The font-wide structural adaptation selects automatic fitting only when simple/composite glyph streams
and `fpgm` are absent and `prep` is absent or scan-only. Other fonts retain upstream selection, including CFF/CFF2/VARC
and explicit engine requests. Font bytes are unchanged. Broader stem-weight assessment remains pending.

### Source-defined x-height alignment

Explicit Mono pipelines recover missed source top-zone associations before optional stroke fitting. Literata's light
sloped serifs can miss the automatic hinter's horizontal-direction test.
[FreeType blue zones](https://freetype.org/autohinting/blues.html) supply references and association ranges;
[Hobby §3.3](../../references/papers/1993-hobby/paper.md#33-fitting-verticals-and-horizontals-to-the-pixel-grid) grounds
interpolation between retained references.

The adaptation captures FreeType's fixed Latin donors independently of requested text. Variation-aware source x-height
seeds association; agreeing grid-aligned donor tops supply fitted height. A straight source top must span at least one
pixel inside the association band, with at least half a pixel of excess. Monotone contraction retains lower geometry,
baseline-crossing curve hulls and X. Overlapping contour bounds, conflicting donors or missing references abstain. The
one-pixel eligibility rule conservatively adapts upstream edge eligibility.

Detached marks follow through source white-distance constraints, adapting
[TrueType relative movement](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#move-direct-relative-point)
and [Shamir §3.2](../../references/papers/2003-shamir/paper.md#32-constraints-and-point-relations). One isolated mark
and one baseline-reaching body must share source/fitted/corrected horizontal projection; the mark's lower source/fitted
extrema must be on-curve. Translate the whole mark by the rounded original gap. Ambiguous owners, multiple marks,
collapsed/colliding gaps or preceding gaps outside the half-pixel rounding allowance retain the whole preceding glyph.

**Confirmed correction; broader optical assessment pending:** Literata 16 px, `wght=252.22`, `opsz=16`, aligns `i`/`j`
bodies with `n`. Body-only correction enlarged the dot gap from two rows to three; relative positioning restores two
blank rows from the 1.92 px source gap while retaining dot shape. Native-owned axes, Gray, historical controls and
spacing remain outside this correction.

### Source-defined baseline alignment

[FreeType blue zones](https://freetype.org/autohinting/blues.html) associate source features with reference lines;
[Shamir §3.2](../../references/papers/2003-shamir/paper.md#32-constraints-and-point-relations) grounds relative point
constraints, and [Hobby §6](../../references/papers/1993-hobby/paper.md#6-curved-outlines) grounds constraints on Bézier
controls. The adaptation restores the source baseline offset of a straight supporting terminal that automatic fitting
has raised by at least half a pixel, within a one-pixel movement budget. It preserves the fitted cap's slant rather than
flattening its endpoints onto one grid line.

**Project adaptation:** one unambiguous terminal must span at least one pixel horizontally, attain the source lower hull
bound, and lie within FreeType's source association band around baseline zero. Source and fitted control hulls must
remain above its supporting line. Equal Y-displacement constraints retain lines and quadratic endpoint tangents with a
nonzero horizontal component; vertical attachments may extend without reversing. The movable component must remain
inside the source baseline band, leaving every upper point and X coordinate fixed. Curvature orientation and
conservative control-hull separation guard the connecting curves. Shared or ambiguous ownership, multiple contours,
cubic curves, unresolved predicates and conflicting attachments retain the preceding fit. Equivalent subdivided geometry
can conservatively abstain when a supporting edge or its ownership cannot be certified.

Explicit automatic Mono pipelines apply this association before optional stroke fitting. Native-owned axes, historical
rendering entry points, Gray and the separately approved comparison retain their existing policies.

**Confirmed local geometric correction; optical assessment pending:** Literata 400/16 at default `opsz=12` has a source
foot ending on the baseline, but automatic fitting raises that endpoint by 0.65625 px; `8` stays baseline-aligned. With
stub rescue excluded, `7` consequently loses the entire last ink row. Restoring the source reference retains cap slant,
tangent directions, upper geometry and metrics, and restores baseline-adjacent ink. At `opsz=16`, the 0.625 px
correction also changes terminal ink despite the preceding bitmap already retaining one bottom pixel. Inspect foot
weight, the leg-to-terminal transition and numeral alignment for both optical sizes. A bounded five-family
12/14/16/18/20 px sweep at weights 300/400/700 changes only these two captures; it does not establish broader optical
acceptance.

### Source-relative straight-stroke correction

[Hobby's coupled-width model](../../hobby-fitting.md#valid-straight-medial-intervals) relates valid straight source
medial-axis portions. Third-boundary contacts end a portion rather than vetoing the pair or being ignored. Source
normals/radii define relative width error; sample pairs carry their equation (17) arc-length product. An upstream
rectilinear stem anchors the change, with its shared attachment fixed. Curves, multiple contours, ownership conflicts
and uncertain/invalid solves abstain. The explicit `source_relative` policy remains a control; selective fitting retains
this correction on wholly automatic glyphs.

**Confirmed scoped weight correction:** Roboto Flex Regular 16 px at default axes loses the heavy upper-left `1` head.
Its normal-width proxy falls from about 1.395 to 1.016 px against a fixed 1 px stem; attachment and advances stay fixed.
Shape terms allow local taper/direction changes, not exact border-direction preservation. Browser inspection at 12/16/20
px supports the local result. Additional `7` leg/end changes retain inspected continuity but broader shape/weight
assessment remains pending. Some apostrophe and 20–23 px `1` geometry changes leave ink unchanged; Source Sans 3
ExtraLight `L` at 20 px gains only an empty frame row. Neither is a visible improvement claim.

### Coupled whole-outline widths

The [coupled model](../../hobby-fitting.md#coupled-whole-outline-widths) shares straight/curve controls in a
source-relative X solve. Upright X anchors and upstream Y stay fixed; axis-aligned angular attachments retain tangent
directions. Certified exterior straight-site gaps constrain whitespace; exact polynomial reassembly removes equivalent
subdivision. The native-Y/automatic-X slice requires one closed line/quadratic contour, exact paired reassembly and
lossless command representation. Unsupported geometry retains the preceding sequence.

**Approved comparison scope:** the 58-glyph comparison approved on 2026-10-27 supports adoption. Roboto 400/16 `c` thins
end-region normal widths and cap spans from about 1.44 to 1.05/0.95 px, retaining its 1 px upright, 3 px opening and
four end tangents. Six pixels are removed. Review against `e o s` supports the retained shape and weight in scope.

| Additional scope    | Assessment question                                          |
| ------------------- | ------------------------------------------------------------ |
| Roboto 400/12 `c`   | One pixel removed; inspect end continuity and curve weight.  |
| Roboto 400/16 `C`   | Four pixels removed; inspect opening and curve/end balance.  |
| Roboto 400/18 `C c` | Mixed ink changes; inspect placement, stepping and contrast. |
| Roboto 400/20 `c`   | Two pixels removed; inspect end shape against the upright.   |

Regular 14 px and tested 16 px weights 300/700 retain bitmaps despite geometric changes. Source Sans `h`/`m` and Roboto
Flex `k`/`s` controls abstain under correspondence limits. Multi-contour shapes, moving joins and unrecognized curved
white features remain unresolved; unchanged output does not establish their correction.

### Local curved-stroke widths

The [curved-width model](../../hobby-fitting.md#joint-placement-and-smooth-curve-continuation) measures source thickness
through certified opposing borders regardless of orientation. Straight/curve attachment polynomials stay fixed while
interior controls can join the source-relative solve, replacing whole-outline exclusion caused by tiny vertical
terminals. Local ownership adapts Hobby §6 and Hersch §2; segment length is not an eligibility threshold. Exact constant
lines are omitted from certificate adjacency without changing source operators/coordinates; real edges and independent
source/upstream/candidate certificates remain authoritative.

**Confirmed height defect, corrected:** Roboto Flex Regular `k`, 16 px at default axes, has a flat source cap below a
taller upright. A former terminal solve raised one endpoint from 9 to 9.3125 px because a global cap box missed that
edge. [Reference-height constraints](../../hobby-fitting.md#terminal-reference-height-constraints) retain both at 9 px
inside the width solve. Independent geometry and browser output support the correction.

**Pending placement/width assessment:** Roboto/Roboto Flex/Source Sans 3 controls span 12/14/16/18/20/24 px, weights
300/400/700 and both hint modes. Against the preceding local-curve candidate, changes are confined to `k x z` (184
outlines, 39 bitmaps); all 2,771 terminal reference edges retain height. Quantized horizontal `x`/`y` edges with nonzero
unrounded source slopes correctly receive no height constraint. Evidence: `out/diagnostics/robotoflex-k-cap-20261022/`.

Roboto Flex Regular 16 px `s` thins three middle-width samples from about 1.60 to 1.30–1.34 px and removes two pixels,
with attachments/Y fixed. Inspect curvature, staircase continuity and upright balance. At 12 px ink is unchanged; 14/18
px thin locally, 20 px mixes additions/removals and 24 px adds ink. Source Sans `h`/`m` attachment controls retain
preceding output. Assessment of `5 G J S U c s` and mixed outlines remains open; retaining Y limits nearly horizontal
corrections, and a two-dimensional placement solve is outside this slice.

### Equal-source upright weight investigation

**Confirmed inherited defect:** earlier main-page Literata 400/16, `opsz=16`, delivered a one-column `t` body against
two-column `i f l` despite equal 93-unit (1.488 px) source uprights. Upstream automatic fitting already placed `t` at
X=2–3 versus `i` at X=1–3. Engine, correction and scanner controls did not remove the discrepancy.
[Hersch §6](../../references/papers/1993-hersch/paper.md) and
[FreeType width normalization](https://freetype.org/autohinting/widths.html) ground the equal-source relationship.

The diagnostic hint plan supports an internal cause: the 93-unit body and narrower head share the source right edge at
X=208.
[Upstream edge-link selection](https://github.com/googlefonts/fontations/blob/skrifa-v0.48.0/skrifa/src/outline/autohint/topo/edges.rs#L230-L263)
prefers the narrower separation, collapsing both left edges to X=2. The public ahead-of-time plan is not a runtime
trace; runtime captures independently confirm unequal bodies. With matching optical size, 12/14 px bodies are one column
throughout, 15/16 px show the mismatch, and 17/18/20 px are two columns. Evidence:
`out/diagnostics/literata-t-20261029/`.

The [shared-border candidate](../../hobby-fitting.md#shared-border-upright-normalization) used certified unanimous
integer donors, related upper/body widths and one shared displacement. It corrected body weight but was rejected for
source-detail loss and attachment distortion. The [paper comparison](../../references/upright-stem-consistency.md)
records the sourced alternatives; the accepted replacement follows.

#### Source-detail review: candidate requires revision

**Historical rejection, superseded below:** Literata 400/16, `opsz=16`, retained only 1.25 px of a 1.776 px raw source
head profile (1.765625 px in captured source), with the upper tangent's horizontal component lost upstream. Translating
the compressed hinted chain could not restore it. Differential movement also fixed the cap between moved borders and
reversed an attached foot quadratic's curvature despite prior topology/tangent checks. These were confirmed
source-fidelity defects, not acceptable deviations. The
[source-detail review](../../../out/diagnostics/upright-stem-implementation-20261029/verification/upper-stem-detail-review.md)
records why source curve, tangent, cap and attachment relationships must participate in one solve.

#### Source-shape correction: approved with limits

The [automatic-Y coupled shape model](../../hobby-fitting.md#automatic-y-coupled-shape-mode) translates the raw source
head profile and couples it to the certified body standard in one bounded whole-outline solve. Source-relative cap and
curve relationships replace hinted-chain translation. Smooth interior knots remain free under retained Y; source-sharp
corners retain orientation. Quantization reserve stays inside original per-owner movement caps. Runtime/capture
identities and historical replay ownership belong to the [revision index](README.md) and owning model.

**User approval, 2026-10-29:** the reviewed 19-case comparison accepts the changed Literata `t` at 15/16 px, weight 400
and matching optical size, with the shown Mono settings. Approval covers body weight, restored upper-left outline, cap
relationship and changed crossbar/foot appearance. The top three bitmap rows remain unchanged despite restored source
profile and upper tangent: an accepted limitation, not approval of unseen corpus cases. The separate approved baseline
remains independent.

The [source-shape report](../../../out/diagnostics/upright-source-shape-20261029/report.md) retains detailed evidence.
The [delivery report](../../../out/diagnostics/approved-main-refresh-20261029/REPORT.md) verifies native/browser/export
agreement at 15/16 px and the existing main-page matrix: only its Literata 16 px image package changed. Rejected
historical packets retain their original replay interpretation.

### Roboto c source correspondence

**Pending existing imbalance:** default Roboto 400/16 `c` has heavy ends relative to its upright. The source-only
investigation attributes it to upstream fitted geometry; retained attachments and same-outline scanner controls
reproduce it without dropout rescue. This is not a regression introduced by the probe.

The [correspondence study](../../hobby-fitting.md#source-feature-correspondence-probe) tests analytic source events,
opposing borders and shared dependencies without StrokeStyles. Six extrema survive exact subdivision, but eight
certified curve contacts become twenty-four: primitive counts are not canonical identities or fitting weights. Source
Sans single-contour controls fail substitution certification; tested multi-contour controls abstain. Feature extent,
shared ownership and apertures remain unresolved, so attachment pins cannot simply be released.

Exact rational subdivision abstains when coordinates cannot be represented in the diagnostic binary format. Four Source
Sans controls hit that limit; earlier rounded results do not establish exact invariance. Evidence remains under
`out/diagnostics/source-correspondence-20261027/`, with preceding captures/research under
`out/diagnostics/roboto-c-20261026/` and `out/diagnostics/roboto-c-terminal-model-20261026/`.

### Fast-math visual assessment

**Declined: confirmed reviewed regression.** [Global fast-math](../../hobby-fitting.md#global-fast-math-experiment)
changes Mono pixels with layout retained, negates much of the reviewed diagonal compensation and loses compensated
arithmetic. A [selective solver experiment](../../hobby-fitting.md#selective-solver-arithmetic-experiment) investigates
a narrower arithmetic seam while keeping geometry strict.

At 16 px, weight 400, selective hints and FreeType Mono, paired views show heavier diagonal spans in Roboto `2 M V Y w
y` and Source Sans `< Z z`. Changes in `* ^ S # K k s` include tips, corners and curves. Local shape/contrast questions
remain pending; counts do not establish improvements or fitting exceptions.

## Scan conversion and preview

### Native monochrome scan conversion

Candidate Mono uses
[FreeType 2.15.0's monochrome scanner](https://github.com/freetype/freetype/blob/VER-2-15-0/src/raster/ftraster.c) on
the whole fitted outline. Nonzero-winding center fill and two-direction dropout replace the former thresholded
coverage/dropout approximation. Zeno coverage remains diagnostic for Mono; Gray, baseline and independent reference
retain their own policies. The [generator API](../../../crates/generator/API.md#working-candidate-fitting) owns scan
controls and coordinate rounding.

Executed TrueType
[SCANCTRL/SCANTYPE](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#scan-conversion-control)
state follows [FreeType loader semantics](https://github.com/freetype/freetype/blob/VER-2-15-0/src/truetype/ttgload.c),
including component markers and final composite global state. This transports metadata without changing fitting or
engine selection. Automatic fitting executes no bytecode and uses its fallback; live defaults come from the
[shared policy](../../../apps/web/src/app/renderer/preview-policy.ts).

**Confirmed scoped continuity correction:** Source Sans 3 ExtraLight 200/16 regains the source-connected `e` crossbar
attachment and shortened `x c k w` ends on identical outlines, matching independent full FreeType. Browser inspection at
14/16/20 px weight 200 and 16 px weights 400/700 supports those local corrections. Restored ends add ink; this is not
general weight preservation or broad font-mode acceptance.

**Unresolved controls:** font hints first at Roboto 400/14, `wdth=100`, retains unequal `m`/`u` principal stems against
`n`. Current selective automatic-X/native-Y captures at 12/14/16 px measure 1 px straight spans throughout; that
native-X defect is not reproduced there. Shoulders/bowls remain pending, including a two-column 14 px `u` bowl. The
[Roboto investigation](../../references/roboto-stem-balance.md) owns that distinction. Literata 400/16, `opsz=12`,
retains equal inspected `i`/`j` bodies; default Roboto Flex 16 px retains readable inspected joins/counters. Neither
extends approval to other weights or sizes.

### Curve scan precision

Candidate Mono requests FreeType's
[high-precision hint](https://freetype.org/freetype2/docs/reference/ft2-outline_processing.html#ft_outline_xxx). Its
[subdivision policy](https://github.com/freetype/freetype/blob/VER-2-15-0/src/raster/ftraster.c#L522-L563) uses finer
intersections for small bitmaps while preserving supplied geometry, origin, metrics and dropout semantics.

**Confirmed scan defect, corrected:** Roboto Flex Regular 16 px, default axes, diagonal fitting off, had an extra
lower-right bowl pixel in `q`/`g`. The curve lies about 0.013 px above the pixel center but ordinary subdivision rounds
onto it. High precision removes the pixel, matching independent full FreeType on identical geometry; the local
correction also applies at 15/17 px.

**Broader assessment pending:** five-family controls cover 12/14/16/18/20/24 px, weights 300/400/700 and Source Sans 3
200, both hint preferences. Roboto Italic 300/12 quotation strokes and Source Sans 3 200/300 at 20 px percent-sign parts
separate. Component increases alone do not demonstrate broken strokes; inspect curve weight, counters, joins and size
transitions.

### Terminal tips and junction continuity

Roboto Flex default 400/16 has a confirmed lower-right `k` extension from stub rescue, also seen at 12–19, 21–22 and 24
px. Global exclusion removes it but breaks the ExtraLight Source Sans 3 200/12 `R` leg and opens source-connected
`6`/`9` bowls at 12–13/12–15 px. **Global exclusion is held for those confirmed regressions.** Simple/smart dropout and
ordinary/high precision do not provide join protection.

[FreeType's recognizer](https://github.com/freetype/freetype/blob/VER-2-15-0/src/raster/ftraster.c) classifies scan
profiles and extrema, not semantic endpoints/junctions.
[Hobby §3.2](../../references/papers/1993-hobby/paper.md#32-width-control) grounds a broader medial-axis hypothesis for
terminal branches and counter paths. Filled shapes, overlaps, holes, ambiguous ownership and movement-free raster
integration require a separate design; uncertainty must retain the scan.

The narrower supporting-cap adaptation below proves a straight cap supports the whole filled shape and both adjacent
borders continue into the filled half-plane. Curves, internal junctions, holes and ambiguous overlaps remain unchanged.
The same geometric rule must suppress terminal extensions while retaining source-connected joins.

Default Roboto Flex 400/16 `1` has a separate upstream imbalance unaffected by stub policy: automatic fitting narrows
its stem from 1.5 to 1 px while retaining roughly the slanted head's source thickness. The
[source-relative correction](#source-relative-straight-stroke-correction) owns that scoped fitting change.

#### Supporting-cap correction assessment

The explicit `free_type_mono_terminals` stage adopts the conservative supporting-cap correction. Matching source/fitted
ownership, a whole-outline supporting half-plane, adjacent-border continuation and a unique finite cap crossing the
rescued pixel square are required. Other boundaries, curve hulls and uncertain predicates veto suppression; optional
work exhaustion keeps the original scan. This is not general medial-axis terminal recognition.

**Confirmed scoped correction:** browser inspection supports removal of the extra default 16 px `k` tip pixel while
retaining ExtraLight `R 6 9` attachments at 12 px and original scans at their other affected sizes. Geometry, coverage,
frames and metrics stay fixed. The 52-case sweep removes 217 certified rescue pixels from 150 glyphs without changed
component/counter counts; broader terminal shape/weight assessment remains pending. Supporting long borders can pass
eligibility: cap-square/other-boundary gates are safeguards, not semantic ownership proofs.

The `k` extension is suppressed at 13/16/19/22 px in the 12–24 px sweep; other sizes can abstain and retain it.
Historical roles, Gray and the separate approved baseline remain outside this stage.

### Landing comparison scan parity

**Confirmed correction:** Rouge Script Regular 20 px previously lost the `t` tip/crossbar and `d` bowl attachment when
landing capture disabled stub rescue. Rescue alone restores three `t` and two `d` pixels without changing outlines,
coverage, bounds or advances. Disabling fitting or terminal suppression does not remove that cause.

Captures share the [working-preview policy](../../../apps/web/src/app/renderer/preview-policy.ts); compatibility and
stale-capture rejection belong to the [web contract](../../../apps/web/CONTRACT.md), converter adaptations to the
[methodology](../../references/font-converters.md). Earlier 16-case scan/shared-policy controls remain under
`out/diagnostics/landing-samples/preview-scan-correction-20261027/` and
`out/diagnostics/shared-preview-settings-20261027/`. Other changes, including mixed Literata 16 px and Rouge Script 8–16
px ink redistribution, retain pending optical status. Historical sweeps do not define current publication scope.

### Defined preview palettes

Browser-local palettes provide 2/4/8/16 coverage colors, defaulting to Monochrome. Gray retains upstream Normal fitting
and Alpha coverage; palettes do not change geometry/layout. This extends
[scalar quantization](../../references/papers/2006-gallager-quantization/paper.md), not fitting. Coverage-index behavior
belongs to the [WASM contract](../../../crates/wasm/README.md#render-spec-controls). Palette-lab browser masks and
nearest-level linear-light specimens are illustrative and need not match native quantization.

## Spacing, glyph selection and display

### Coordinate-selected scalar glyphs

OpenType
[required variation alternates](https://learn.microsoft.com/en-us/typography/opentype/spec/features_pt#tag-rvrn) and
[GSUB variations](https://learn.microsoft.com/en-us/typography/opentype/spec/gsub#featurevariations-table) can select
another outline for a scalar. Resolve it at the requested axes before drawing; Unicode identity stays fixed while
geometry, metrics and pair expectations follow the selected glyph.

Compare shaped advance with the shaper's
[own metric callback](https://docs.rs/harfrust/0.14.0/harfrust/trait.FontFuncs.html) in its integer domain, avoiding
confusion between variation-delta rounding and positioning. Roboto Flex `$`, 14 px, `opsz=14`, `wdth=100`, selects glyph
7 at weight 400 and glyph 602 at 700, for slant 0 and -10. This fixes the previous capability rejection across
rendering/kerning inspection. Contextual substitutions, count/order changes and unrepresentable positioning remain
outside the [supported input contract](../../../crates/generator/README.md#supported-input-and-output).

### Pair spacing and kerning

The [bitmap policy](../../../crates/generator/API.md#live-spacing-api) separates images, advances and pair adjustments.
Fitted advances are used when available, otherwise rounded source advances. Fixed-pitch cells and source-tabular digits
retain common source relationships. Source kerning and available bearing correction resolve once into sparse integer
adjustments; integer accumulation makes each pair prefix-independent. Nearest rounding uses signed half ties away from
zero. Intentional overhang remains, without a neutral blank-column floor. Reference/historical source-linear layout is a
diagnostic control; integer metrics are deliberate, not a bitmap-format requirement.

Foundations are [FreeType metrics](https://freetype.org/freetype2/docs/glyphs/glyphs-3.html),
[kerning](https://freetype.org/freetype2/docs/glyphs/glyphs-4.html),
[Turner–Lemberg metric fitting](../../references/papers/2003-turner-lemberg/paper.md) and
[Hersch §§5–6](../../references/papers/1993-hersch/paper.md). Candidate Gray shares captures/metrics with specimens and
exports; its previous production-target preview is not a pixel-identity reference. Broader Gray assessment remains
pending. The removed projected-gap algorithm was internally consistent in the Roboto 400/14 `AV`/`VA` control, but
perceived diagonal separation was unassessed; it is not a current layout mode.

**Pending Literata spacing assessment:** at 400/16, `opsz=16`, `ck`, `ic` in “quick” and `or` in “liquor” have these
source-to-fitted measurements:

| Pair | Source kern (px, 26.6) | Residual difference (1/64 px) | Outline gap increase (px) |
| ---- | ---------------------: | ----------------------------: | ------------------------: |
| `ck` |              −0.109375 |                            28 |                     0.499 |
| `ic` |              −0.015625 |                            30 |                     0.484 |
| `or` |              −0.156250 |                            14 |                     0.391 |

Each source adjustment rounds to zero and each residual stays below the one-pixel correction boundary. No correction is
missing or doubled. Fitted `c`/`o` advances are 9/10 px versus source 7.984375/9.375 px; the three delivered ink boxes
each leave two blank columns. Bounds do not estimate optical space: the open `c` bowl and facing curves contribute
different whitespace by row. Native captures match publication; overlay-off, forced-auto and hints-first controls retain
the same pair metrics. `ck`/`ic` gap changes reverse at 8/20 px and are small positive at 12 px. These observations do
not establish a contract failure or universal correction. Evidence: `out/diagnostics/literata-spacing-20261029/`.

Front-page comparisons enable source kerning with zero extra tracking. The
[methodology](../../references/font-converters.md#source-kerning) owns native support and composition adaptations;
enabling kerning does not itself resolve these optical concerns.

**Confirmed comparison-fidelity defect:** Crosspoint pairs used the original 150-DPI scale against normalized glyph
sizes, and composition accumulated fractional positions instead of snapping each combined advance and pair step. The
correction aligns pair scaling with glyph size and restores firmware placement while retaining exported glyph shapes and
native advance values. Its visible effect is spacing and placement; comparative optical quality remains pending
assessment under the existing family, size and axis scope.

#### Fitting-bearing compensation investigation

Automatic-Mono captures retain left/right metric-point rounding residuals. Selective fitting carries those of the X
owner identically across scanners. Independent reference, native/interpreter, unhinted, Gray and non-Mono captures
contribute none; fixed-pitch and source-tabular digits have zero residuals.

[FreeType's integer-positioning example](https://freetype.org/freetype2/docs/reference/ft2-glyph_retrieval.html#ft_glyphslotrec)
compares preceding right and current left residuals at its half-pixel boundaries. The
[pinned loader](https://github.com/freetype/freetype/blob/57617782464411201ce7bbc93b086c1b4d7d84a5/src/autofit/afloader.c#L462)
defines them as rounded minus pre-rounding metric position after small-bearing adjustments. Skrifa's
[`AdjustedMetrics`](https://docs.rs/skrifa/0.48.0/skrifa/outline/struct.AdjustedMetrics.html) exposes the rounded
advance and optional bearing but discards these intermediates; the integrated snapshot retains them. Final
bounds/advances cannot uniquely reconstruct that error.

Independent FreeType controls remain under `out/diagnostics/fitting-compensation-20261026/`. Skrifa's empty-outline
phantom fallback differs from FreeType's skip, without integer placement impact at the approved setting. A historical
full-ASCII Literata probe encountered 27 unsupported pairs: a strict shaping-coverage limit, not evidence that supported
subsets cannot use source kerning.

#### Compensated-spacing runtime adoption (open iteration)

Compensation is adopted. Human approval covers the reviewed Roboto 16 px, `wght=400`, `wdth=100`, forced automatic Mono,
FreeTypeMono, diagonal fitting on, source kerning on and zero tracking. Broader combined-policy optical assessment
remains open.

#### Browser comparison for optical assessment (question, not a verdict)

The [approved-setting proof](../../../out/diagnostics/fitting-compensation-review/www/proof-kerning-on/index.html)
compares original, recovered-residual and FreeType-vector-substitution arms on identical glyphs, advances and bitmaps.
Its [rework proposal](../../../out/diagnostics/fitting-compensation-review/rework-proposal.md) records ArrowType control
strings/corpus provenance. Other frozen packets remain diagnostics; canvas agreement establishes comparable output only.

#### Fractional source advances and bitmap placement

**Confirmed prefix-dependent defect, corrected:** default Roboto Flex 14 px had equal 7.90625 px source digit advances.
Fractional accumulation placed the final `98` at a 7 px step in `909192939495969798` and 8 px in `09192939495969798`,
causing touching versus a blank column. Kerning was irrelevant. Fitted automatic advances are 8 px, matching independent
FreeType. Bitmap placement retains that step in both strings, Mono/Gray and both engine policies. Width/wrapping changes
are intentional: eighteen advances total 144 rather than 142.3125 px. Broader optical assessment remains pending.

#### Proposed optical pair-spacing experiment

The isolated optical-spacing experiment is owned by the
[optical-spacing design](../../designs/text-layout/contextual-spacing-and-healing.md#optical-spacing-experiment). The
selected candidate adapts Hu/Hersch depth-limited bitmap walls and reference relationships, retaining CounterSpace, the
earlier slope-only filtered walls and all three FontForge-based methods as comparisons. Glyph forms, images, bitmap
offsets and finalized advances remain unchanged. Source metrics retain nearest-1/64-pixel quantization; source outlines
retain continuous design units.

**Hu/Hersch correction, optical assessment pending:** the [source audit](../../references/hu-hersch-delivered-model.md)
now includes Hersch and Betrisey's US5768490A. Its published depth factors, 0.21 and 0.25, replace the previous fit
without uniquely determined factors. Concavity-only slope filtering and an exterior-lip vertical aperture cutoff replace
the global slope envelope and parallel convex-hull chord cutoff. Monotone stepped shoulders are not bounded cavities.
Asymmetric lips require the published connector construction. The finite-cell cavity detector remains an explicit
adaptation, not recovered author code.

All eligible pairs and their delivered `nn`/`HH` references now share one transformed-wall integral. The previous
classified stem/curve extremum shortcut is removed from the active solve. Delivered full-metric placements still
calibrate density independently of the kerning slider; mixed areas and heights are averaged separately. Experimental
`00` and unsupported-category fallbacks retain their declared scope. CounterSpace development remains paused.

The superseded Literata fit reached relative depth zero and visual factor approximately 0.208. Investigation of `oe`,
`kh`, `rn`, `xn`, `co` separated reference-path differences from cavity filling; clearance was not responsible for those
five steps. Fixed-stem-target and source-calibration probes did not establish a general correction and were not adopted.
In particular, a stem-extremum target cannot be mixed with a filtered-area measurement. The primary-source correction
changes the geometry rather than selecting a density to fit those reported pairs.

For Literata 16 px/400, `opsz=16`, full optical strength and neutral deliberate offsets, the correction changes `oe`
from a 9 to a 10 px origin step and `xn` from 11 to 10. `kh` remains 11, `rn` remains 9 and `co` remains 9; those
reported optical concerns are unresolved. None of the five placements is clearance-limited. Continuous corrected steps
are approximately 10.125, 11.003, 8.803, 10.253 and 9.438 px respectively. The previous and current models use different
walls, so their target numbers alone are not comparable perceived distances. Earlier repeated-pair cases also change:
`ff` emits 7, `cc` 10 and `zz` 10 px. These counts require native-size comparison rather than automatic approval based
on the requested five directions.

The mechanical suite passes 143 tests. Six capture cases cover the four retained families at 16 px and diagnostic
Literata 14/18 px. On the 45-pair Literata sampling probe, 64-to-128 samples per pixel changes continuous steps by at
most 0.000167 px and changes no emitted steps. These are numerical and integration findings, not optical acceptance.

Earlier previews and failed probes are retained under `out/diagnostics/contextual-spacing/hu-hersch-delivered/`,
`hu-five-pair-investigation/` and `hu-consistent-calibration/`. New verification and assessment belong under
`hu-patent-correction/`. Analytic and integration tests establish mechanics, not perceived balance. Reported failures,
held-out words and native-size neighboring choices remain assessment cases. Isolated Literata 14/18 px captures remain
diagnostic only; they do not expand the four-family 16 px preview scope. Glyph bitmaps and the approved renderer
baseline remain unchanged.

**Source-relative Hu comparison, optical assessment pending:** `hu_source_relative` uses the same bounded wall
transformation on continuous source curves and delivered cells, preserving each source pair's filtered relationship. The
[comparison design](../../designs/text-layout/contextual-spacing-and-healing.md#source-relative-hu-comparison) owns its
equation. It retains source kerning at the full compensation endpoint and uses `n`/`H` only for common body windows.
This tests raster compensation separately from shared-density equalization; it does not adopt the patent's shared
ideal-space target or change maintained glyph production. The comparison export can start with this mode while the
solver/exporter default remains shared-target Hu.

For the retained Literata 400/16, `opsz=16` capture at full strength, `nx` changes from shared-Hu 12 to 11 px, `tu` from
7 to 6, and `ft` from 8 to 7. These are source-relationship findings, not automatic optical approval. The same
comparison emits `ff` 6, `cc` 8, `zz` 9, `oe` 9, `kh` 10, `rn` 8, `xn` 9 and `co` 8. In particular, earlier concerns
about crowded repeated pairs and `oe` remain native-size inspection cases; preserving designed relationships cannot
promise to resolve those judgments.

On the longest preset, Aaron Abraham, 1,287 letter-pair occurrences have filtered source mean 2.987 px. Metric delivery
measures 2.997, shared-Hu delivery 3.736 and source-relative Hu delivery 3.039 px. The lowercase Lynx preset measures
2.805 in the source, 3.628 under shared Hu and 2.872 under source-relative Hu. These occurrence-weighted means exclude
spaces and punctuation and use identical windows in both geometries. Repeated `nn` still emits an 11 px step: its
approximately 0.459 px target residual remains after whole-pixel rounding, without imposing that residual on other
pairs. Equal or preserved averages do not establish reading rhythm.

Mechanical verification passes 166 tests and 3,627 unchanged bitmap profiles. Independent comparison against the
previous preview retains all five older models' placement and diagnostic tables over 10,233,250 cells. Six captured
cases cover the four retained 16 px families and diagnostic Literata 14/18 px. Sampling at 64/128/256 samples per pixel
leaves every one of Aaron Abraham's 601 distinct emitted pair steps unchanged. One held-out repeated pair, `zz`, sits
near a half-pixel boundary: ideal steps 8.50323, 8.49936 and 8.50040 emit 9, 8 and 9 px. This is an unresolved numerical
sensitivity, not a reason for a character-specific rounding rule or a preferred-pixel test. The configured grid remains
64 samples per pixel. New artifacts and the separate comparison preview are under
`out/diagnostics/contextual-spacing/hu-source-relative/`; earlier previews remain intact.

The source-relative comparison also has an optional 3-bit grayscale reference retaining the default coverage renderer,
with automatic hinting and gamma 1, and vanilla source metrics from `generate`. It uses the same four families, 16 px
size, axes and preset repertoire. Source advances and kerning accumulate fractionally in 26.6 pixels; only drawing
origins round to pixels, matching native source-linear layout. No bitmap-metric finalization or fitted bearing
corrections apply. Optical and extra-spacing controls affect only the Mono views. This is a visual renderer reference;
Gray optical boundaries and automatic Gray spacing remain outside this experiment. The initial bitmap-spacing reference
remains in `out/diagnostics/contextual-spacing/hu-source-relative-grayscale/`; the corrected source-linear reference is
in `out/diagnostics/contextual-spacing/hu-source-relative-vanilla-grayscale/`.

**Normal-text reference mismatch, corrected:** the 3-bit diagnostic was presented as a normal-font reference despite
using custom coverage quantization and integer drawing origins. The user reported a substantial mismatch with Google
Fonts. The primary reference now embeds the original captured font bytes and renders ordinary DOM text with the
[CSS Font Loading API](https://www.w3.org/TR/css-font-loading-3/), normal browser shaping, kerning, ligatures and
fractional placement at the captured size and axes. The old custom renderer remains a collapsed diagnostic. This matches
the web-font mechanism documented by [Google Fonts](https://developers.google.com/fonts/docs/css2); exact Google Fonts
site appearance is not asserted across font versions, axis settings, browsers and displays. The compact inline resource
uses a layout-preserving subset and documented
[fontTools default-axis pinning](https://fonttools.readthedocs.io/en/latest/varLib/instancer.html), retaining nondefault
variation axes. The retained Literata subset has identical evaluated source outlines and advances for all 79 characters.
Browser glyph positions and line breaks are checked against the original across all seven presets. Browser antialiasing
pixels differ between these resources; exact pixel identity is not asserted. Use the full offline page for the untouched
original-font reference. Fully static instancing was rejected to avoid rounding interpolated coordinates. The browser
reference also follows the shared 2×/4×/8× enlargement control via a
[CSS transform after layout](https://www.w3.org/TR/css-transforms-1/#transform-rendering), preserving native wrapping,
font size and axes. This is enlarged browser text; the browser’s enlarged rendering may differ from magnifying frozen
native pixels. The separate 1× view remains the normal-size reference.

The separate Mono vanilla-spacing reference reuses captured binary cells with fractional source metrics. Generic contact
overlays in the pair inspector distinguish shared edges, corners and overlaps without changing placement. At Literata
400/16, `ty` at a 6 px step has one shared-edge contact; 7 px has none. This supplies no basis to relax the clearance
guard. No optical solver or delivered bitmap changed. Artifacts and mechanical checks are under
`out/diagnostics/contextual-spacing/browser-reference/`; optical assessment remains open.

**Diagonal neighbor review, optical assessment pending:** the user considers `nx` too detached compared with the browser
reference. The fitted-wall candidate emits an 11 px step in Literata 400/16, `opsz=16`; a 10 px step has one permitted
baseline serif-edge contact and no occupied-cell overlap. The wall measurement and rounding choose 11 px before
clearance. In `lynx`, `yn` also tightens relative to source, so the perceived imbalance may involve the allocation of
spacing within the word rather than `nx` alone.

The [neighbor assessment](../../designs/text-layout/contextual-spacing-and-healing.md#neighbor-placement-assessment)
compares current and one-pixel-tighter placements across the facing-stem family and words, retaining the four-font scope
and browser reference. These alternatives are diagnostic placements only. Inspect both local openness and the weight of
joined baseline serifs; do not translate a preferred alternative into an isolated pair override. The solver is
unchanged.

The user finds isolated pairs insufficient to judge the effect. The reading review therefore compares complete preset or
custom texts, independently wrapped for the current and tighter alternatives, alongside normal browser text. Contact
overlays are optional; assess rhythm, word separation and line texture in the full text before interpreting individual
contacts. All seven presets and the four-font scope remain available.

The user finds the whole-text comparison improved and adds `ca` as a loose pair. In Literata 400/16, `opsz=16`, the
source step is 7.984375 px. Shared-target equalization on source outlines raises it to 8.404457 px, and fitted outline
measurement raises it to 8.517686 px, which rounds to 9 px without clearance displacement. An 8 px diagnostic step has
no occupied-cell overlap, edge contact or corner contact. Sampling at 32/64/128 points per pixel preserves the 9 px
rounding result. The whole-text diagnostic includes `ca`; optical assessment remains pending. This is a
measurement/target and quantization concern, not evidence for a pair-specific exception.

The [construction audit](../../references/hu-hersch-construction-order.md) identifies stale pre-filter cavity supports
and clipping before cavity construction as separate limitations. Recomputing supports after the 45-degree stage does not
change current fitted lowercase placements in the four-font corpus. Building complete-outline walls before the retained
body integral changes the shared calibration: Literata `ca` and `en` tighten, while `nx` and `os` remain unchanged.
Their local walls did not improve; the target moved because other glyphs changed. These diagnostic outcomes are pending
optical assessment, not an adopted correction or evidence that the perceptual objective is resolved. The preceding
solver and reading comparison remain the control.

The separate
[construction-order candidate](../../designs/text-layout/contextual-spacing-and-healing.md#construction-order-candidate)
now implements full-outline construction and post-filter cavity supports before the retained body integral. Source
metrics, target policy, signed rounding and the bitmap overlap safeguard are preserved. Its whole-text comparison
retains all four fonts and seven presets with a vanilla browser reference. Optical assessment remains pending; the
calibration-induced Literata `ca`/`en` tightening is not a demonstrated repair of their unchanged local walls, and
`nx`/`os` remain open.

The separate
[predictable-spacing prototype](../../designs/text-layout/contextual-spacing-and-healing.md#predictable-spacing-control-prototype)
exposes that retained full-outline endpoint behind a correction-strength control with an independent span-gap letter
spacing control, on the 13 root samples in both profiles. Strength zero bypasses to Source exactly; full strength
reproduces the retained endpoint including its safeguards. Gray reuses the mono-pipeline endpoint deltas over fractional
source accumulation as an explicit adapter. Mechanical identity, endpoint parity and control behavior are verified; the
endpoint's optical assessment remains pending and nothing here is optically approved.

The user also finds Literata `op` and `os` more detached than `se`. Their steps remain 9, 10 and 7 px under both the
preceding control and construction-order candidate, with no clearance displacement. The final bitmap body-row mean gaps
are 2.625, 3.375 and 2.25 px, with minimum row gaps 2, 2 and 1 px. These are geometric diagnostics, not perceptual
distances. Rounding puts `os` above and `se` below the shared modeled target, separating their realized scores by 0.761
px. `op` rounds down and has a modeled score only 0.137 px above `se`; its remaining visual contrast is not explained by
rounding alone. Fitted-outline raw mean gaps for `op`/`se` are close (2.590/2.654 px), while binary cell conversion
changes them to 2.625/2.25 px. This is an unchanged-output finding and an unresolved measurement/delivery limitation,
not evidence for a global tracking change or a pair exception. Diagnostics are retained under
`out/diagnostics/contextual-spacing/op-os-se/`.

The
[complete-cell geometry assessment](../../designs/text-layout/contextual-spacing-and-healing.md#complete-cell-geometry-assessment)
adds an isolated masked whole-text comparison against the full fitted-outline candidate. In retained Literata 400/16,
`opsz=16`, its bitmap-measured arm changes `os` from 10 to 9 px, but also changes `ca` from 8 to 9 px and `ri` from 8 to
9 px; `op` stays 9 and `nx` stays 11 px. These are placement changes pending assessment, not confirmed improvements or
regressions. The question is whether measuring complete delivered cells improves overall reading rhythm enough to
justify recurring local tradeoffs. Assessment starts with one short Literata passage and chat feedback, with the full
corpus available optionally. A/B meanings stay fixed across selections and method disclosure is optional; no repeated
rating task is required.

The
[YinYangFit feasibility experiment](../../designs/text-layout/contextual-spacing-and-healing.md#yinyangfit-feasibility-experiment)
first checks whether the reference supplies an executable pair-spacing objective. At pinned revision
`609d17e8a6446ec4413a1b02a0768b8214d73333`, the packaged penalty method returns zero for all probed distances and the
selection method retains the first candidate. The [independent audit](../../references/yinyangfit-feasibility.md) finds
a real objective and training loop in historical revision `d9c7e25`, but no recovered fitted state. Its interrupted
training, always-on forward noise and absent held-out validation leave the calibrated-reproduction gate unmet. No
capture adaptation or new preview follows. This is a reference-completeness finding; it supplies no spacing predictions
and does not replace the full fitted-outline control.

The authorized historical recovery now executes the pinned Torch scorer in an isolated modern CPU compatibility
environment. Original-domain Crimson images and the complete lowercase pair/translation manifest are reproducible; the
selected scorer definitions retain their source expressions. Seeded reference-noise and separately named noise-disabled
evaluation produce finite costs that vary with placement, with repeat/order and initialized-state save/load identity.
The noise-disabled `nn` categorical-loss probe has finite gradients for the expected active parameters. This establishes
executable initialization and one backward path, not calibrated spacing or full training.

All three initialized probe pairs favor the widest sampled distance. The historical cubic-loss degeneracy remains a
numerical risk: an exact quadratic has a zero cubic coefficient, while the observed float calculation returns a finite
loss through a tiny nonzero coefficient and a distant unused root. No alternate objective was substituted. Real-pair
cubic backward behavior, stochastic training, convergence and held-out optical quality remain unassessed. Full-size CPU
evaluation takes tens of seconds per pair and the backward probe uses substantial memory, so the historical epoch
ceiling is unsuitable as an automatic next run. Detailed measurements and provenance stay in
`out/diagnostics/contextual-spacing/yinyangfit/`; commands are in the
[experiment README](../../../experiments/contextual_spacing/README.md#yinyangfit-historical-scorer-recovery). The
calibrated-reproduction gate remains unmet; no optimizer update or preview selection follows from this recovery stage.

The subsequent bounded training probe applies the original noisy objective and Adam to three fixed pairs, preserving
training RNG across deterministic evaluation. State-complete checkpoint replay reproduces the final parameters,
optimizer and RNG exactly. All three updates have finite losses and the expected gradient paths; their real-data loss
branches are categorical, so this does not resolve the cubic-backward risk. Fixed-pair cross-entropy decreases, but the
designed position stays third of five and every pair still favors the widest sampled offset. This is successful
optimizer/replay execution without demonstrated placement improvement. Convergence, broader-pair transfer, family
generalization and optical quality remain unassessed. Any larger experiment should examine preferred-distance movement
and held-out behavior rather than accepting lower score magnitudes alone. No maintained kerning method is added.

The broader `yinyangfit-pair-holdout-v1` trial freezes thirteen training pairs covering each lowercase glyph once and
four optimizer-excluded diagnostic pairs (`ca`, `nx`, `os`, `se`). Thirteen updates plus one replay complete in 17.65
minutes with 15.17 GiB peak memory. Independent verification confirms exact final model, Adam, RNG and position replay.
Fixed training-evaluation mean cross-entropy falls from 60.642 to 35.164; held-out mean falls from 50.443 to 30.595.
Nevertheless, all eight evaluated pairs retain the labeled reference at rank three of five and uniquely prefer the
widest sampled offset, `+5 px`. Score spreads narrow without changing selected distances. This establishes bounded
training and pair-holdout execution, not improved spacing or convergence. The holdout shares glyphs within Crimson and
does not establish font, size or glyph-role generalization; all observed update losses are categorical, leaving real
cubic backward behavior untested. Evidence and independent checks stay under
`out/diagnostics/contextual-spacing/yinyangfit/pair-trial-01/` and `pair-trial-verification/`. Audit the scoring
objective and its scale sensitivity before authorizing a longer training run. No renderer or preview selection changes.

The isolated `yinyangfit-interactive-v1` experiment takes the complementary no-training path: a nearest-distance probe
(not a reproduction of YinYangFit's oriented model) whose three interpretable global controls rescore unchanged
delivered Mono and Gray cells at integer steps around metric placement. The controls are target cohesion, interaction
reach in pixels (stored as `feature_scale`, not V1 feature-scale weighting) and proximity falloff (radial decay shape,
not an independent crowding penalty). All costs are finite and nonconstant; the occupied-cell overlap guard fires (more
often under Gray fringe coverage); defaults place most evaluated pairs at interior minima while endpoint settings
saturate at recorded domain edges. Ties anchor at the global valid minimum in both scorer and page mirror. This is
mechanical control evidence with pending visual assessment: `To`/`AV` tighten and rounds widen slightly at defaults,
with `vv` at the domain edge on Literata Mono. Words add a named captured-source fractional baseline beside the
experiment's cumulative whole-pixel layout; the experiment layout does not retain captured Gray spacing. Evidence, the
frozen-setting report and the self-contained interactive page stay under
`out/diagnostics/contextual-spacing/yinyangfit-interactive-v2/` (initial outputs retained under
`yinyangfit-interactive/`); the browser rechecks every displayed choice against embedded Python costs. No maintained
kerning method is added.

The follow-on full-window experimental version `yinyangfit-interactive-b2-fullwindow-v1` keeps the same controls,
ranges, policies and displays while scoring each candidate over the full query window (on-ink positions included at zero
distance through the unchanged regularized kernel) instead of masking them out of the attention-normalized mean. It
carries its own model, implementation and cache identities; v1 tables and pages are archived, never reused as
full-window columns. Optical assessment of the moved default-corpus endpoints and of the residual wider-control turns
stays pending; the approved published selection and all maintained methods are unchanged.

The
[TypeFacet feasibility experiment](../../designs/text-layout/contextual-spacing-and-healing.md#typefacet-feasibility-experiment)
now reproduces the original Python 2 application through actual UFO output, then compares source outlines and exact
delivered-cell rectangles for frozen Literata 400/16. The author-example configuration changes 289 of 676 lowercase
steps against the retained full fitted-outline control, with no occupied-cell overlaps in 680 checked outputs. **Optical
assessment pending:** `os` and `du` tighten, `al` and `ri` widen, and `nx` stays unchanged. These uncalibrated settings
do not establish a general repair. Coordinate doubling changes five rounded source-analysis decisions; component-only
input receives no selected advance. Evidence and reference residuals are retained in
`out/diagnostics/contextual-spacing/typefacet-experiment/verified/`. No reading preview or control replacement follows
before the calibration and coordinate policy are resolved.

**TypeFacet calibration remains unresolved:** two reference-only searches evaluate 3,335 configurations against the
manual's endpoint, body, intrusion and overhang families, excluding reported problem pairs. Direct delivered-cell
calibration reduces reference RMS step error from 1.228 to 0.781 px, but reference errors still exceed one pixel.
Parameter-extreme alternatives within one retained metric quantum of that RMS change up to 118 of 676 lowercase
placements. The best source and cell calibrations emit identical lowercase steps here, expanding mean source-relative
step by 0.791 px and widening 552 pairs against the retained control, including `al`, `ca`, `en` and `ri`. These are
mechanical differences with optical assessment pending, not a demonstrated general repair. The single global parameter
fit does not justify a reading preview or browser port; it does not establish that manual or category-based TypeFacet
tuning is impossible. Protocol, reference residuals, independent UFO parity and sensitivity evidence remain in
`out/diagnostics/contextual-spacing/typefacet-calibration/fit-03/`.

The separate
[TypeFacet density-controlled comparison](../../designs/text-layout/contextual-spacing-and-healing.md#typefacet-density-controlled-comparison)
freezes those fitted parameters and removes only their continuous fixed-alphabet mean shift before rounding and the
retained overlap guard. It changes 163 of 676 lowercase steps against B (66 tighter, 97 wider), with zero continuous
mean drift and −0.00527 px emitted drift against source origins. No safeguard clamp is needed; 102 lowercase pairs touch
without overlapping. This is redistribution at controlled density, not a successful new automatic calibration. **Pending
optical assessment:** `ca`, `pe` and `se` widen, while `nx` remains unchanged; inspect overall word rhythm and whether
local tradeoffs are worthwhile. The single-font page keeps A as this trial and B as the previous control, retaining all
seven presets and unchanged placement outside ASCII lowercase pairs. Baseline table/glyph identity, 676 independent
placements and 42 browser layout fixtures pass. Evidence is under
`out/diagnostics/contextual-spacing/typefacet-density-review/site/`; the earlier four-font comparison remains separate.

**Density trial objection, 2026-11-01:** the user finds A's `gs` too open and `hi` too tight. The browser reproduces
`gs` 9→10 px and `hi` 11→10 px against B. Fresh original Python 2 runs reproduce the raw steps exactly; equivalent
merged cell rectangles do not change them. No table-index, coordinate-unit or arithmetic discrepancy was found. The
failure has two parts: raw TypeFacet already favors a wider `gs`, while subtracting the alphabet mean shift pulls `hi`
below the original minimum and intrusion constraints. Both centered pairs fail the original intrusion predicate; the
current bitmap guard permits `hi`'s one baseline serif contact, as agreed. The disclosed minimum-distance relaxation is
not a hidden contract violation, but original TypeFacet local balance no longer justifies the centered result. This is a
failed local outcome of the project adaptation, not an established reference implementation defect. Keep B; do not
promote A or add pair exceptions. Re-solving at a constrained density remains an unverified alternative, and would not
by itself establish a repair of raw `gs`. Evidence is under `out/diagnostics/contextual-spacing/gs-hi-investigation/`.

**Constrained integer trial, 2026-11-01:** the
[new experiment](../../designs/text-layout/contextual-spacing-and-healing.md#typefacet-constrained-integer-experiment)
removes the post-solve shift and enumerates integer placements inside original TypeFacet minimum-profile, extrema and
both intrusion constraints, with bitmap overlap/order safety. Zero extra minimum distance permits contact. Intermediate
font-unit placement rounding is replaced by pixel-domain selection; analytic half-font-unit contact and disjoint-profile
fallback fixtures pass. Cold replay agrees, and a full original-process profile capture independently verifies all 676
selected placements and 2,303 tested positions, including rejection of every smaller candidate.

The 89-setting lowercase search finds a density-feasible fit: normal distance .0925 em, intrusion .03125 em, fixed .1 em
extrema overlap and .005 em precision. Emitted mean differs from source by −0.01415 px, within the declared 1/64 px
metric band, with no later correction. `gs`/`hi` return to B's 9/11 px steps; `nx` changes to 10 px and `al`/`ca`/`en`
stay at B's placements. **Pending optical assessment:** `ri`, `se` and `pe` widen, and a second density-feasible setting
with equal reference error changes 173 lowercase placements. The fit is deterministic but not uniquely established by
the reference data. The single-font whole-text comparison is a controlled experimental review, not a promoted model or
claim of general optical repair. B and all prior pages remain unchanged. Fit/proof evidence is under
`out/diagnostics/contextual-spacing/typefacet-integer/fit-02/`; the reading page is under its sibling `review/`.

**Interchangeable editor methods, 2026-11-01:** after positive user feedback on the constrained integer Literata trial,
the user requests method selection and matching controls in the main Glypherie editor. The
[method interface](../../designs/text-layout/contextual-spacing-and-healing.md#interchangeable-kerning-methods) owns the
calculation, state and adoption gates. Keep the maintained source/bearing method as default. The TypeFacet port uses
delivered binary cells and manual parameters. The Literata calibration and prior comparisons remain separate evidence,
without an implied universal fit.

**Mechanical verification:** all 60,164 pair origins across 89 retained settings match the original integer oracle; the
selected setting also matches every original bound and intrusion decision at every tested position. The port retains the
original module's one-decimal geometry override and Python 2 decimal rounding, rather than the helper's nominal default.
Native/WASM comparisons cover four fonts, three sizes, two manual parameter settings, tracking and a rounding-sensitive
case. Main-editor switching, settings restoration, reload, specimen Reset and explicit Gray recovery pass browser
verification; the source default and preview/export composition retain their previous contracts. These checks establish
delivery fidelity, not automatic calibration or optical acceptance across fonts. Evidence is under
`out/diagnostics/contextual-spacing/main-editor-methods/`.

**Roboto pair-balance concern, 2026-11-02:** at Regular 400/100, 16 px, default Mono and manual TypeFacet parameters
`.1/.1 em`, the user finds `ac` wider than `ck`. Source origin steps are 8/9 px; TypeFacet selects 8/8 px. The former
has a sustained 2 px central same-row gap, while the latter has 1 px gaps near the tips and a 7 px opening centrally.
The original Python 2 implementation on the identical delivered-cell geometry independently rejects 7 px and accepts 8
px for both pairs, matching the port. The active constraint is the powered intrusion/protrusion test, not occupied-cell
overlap or the mean intrusion tolerance. In particular, `ac` at 7 px is overlap-free but inadmissible to TypeFacet. Gray
fitted-outline analysis also selects 8/8 px. These checks establish model behavior without a demonstrated port defect;
optical balance remains pending assessment. Default manual parameters are not a Roboto calibration, and the predicate
does not enforce equal perceived spacing. Evidence stays in `out/diagnostics/typefacet-ac-ck/`; no parameter, renderer
or preview change follows from this diagnosis.

**Manual TypeFacet adjustment, 2026-11-02:** the editor exposes the original minimum-distance and horizontal extrema
overlap roles alongside normal distance and intrusion tolerance. Values stay per font variant and use the shared
preview/export resolver. Historical values inherit the previous zero minimum and .1 em overlap defaults. This extends
manual adjustment while preserving the source default and existing TypeFacet calculations at their previous settings; it
does not resolve the pending Roboto `ac` optical concern or establish a universal parameter fit.

**Hu/Hersch correction strength, 2026-11-02:** manual strength blends finalized Source spacing with the continuous
Hu/Hersch correction before signed rounding and the existing feasibility bound. Full strength and legacy settings keep
the previous result; zero strength preserves Source exactly and bypasses auxiliary calibration. The density target and
wall construction remain fixed. This is a project composition control, not a new optical model or calibration, and does
not resolve the existing local-spacing assessment. Saved variants, URLs and export retain the same selection.

**Depth controls replace strength blends, 2026-11-06:** the user rejects blending between Source and the selected
method, so both analytic adapters now apply their full correction to every supported pair. Hu/Hersch gains the two
method-owned depth controls from the patent's preferred embodiment: aperture-relative cavity depth (default `0.21`) and
body-height maximum visual depth (default `0.25`), each finite `0..=1`. Both enter the candidate walls and the density
calibration; class body height remains the global cap basis. FontForge keeps its source-relative objective with no new
clearance or shared-target control. Retired `strength` values are rejected at every admission boundary (2026-11-06 hard
cut): they no longer parse, so no saved blend can load as new defaults, including former zero-strength Source identity.
Method names lose their experimental suffixes without asserting optical approval. Defaults reproduce the previous
full-strength tables; pending local-spacing concerns are unchanged.

**Geometry and placement separation, 2026-11-01:** the user identifies that method selection should not be coupled to
Mono output. The
[completed interface](../../designs/text-layout/contextual-spacing-and-healing.md#interchangeable-kerning-methods)
separates font-unit TypeFacet profiles/predicates, delivered-cell and fitted-outline adapters, and current integer-grid
placement. Gray uses fitted commands independently of coverage/gamma/depth. Eligibility no longer filters ASCII
lowercase; shared shaping, whitespace, fixed-pitch and tabular-digit policies remain explicit. Source remains default.

A real Literata Gray `e` contains an exactly vertical quadratic created by fitting. The original offset cannot intersect
its parallel endpoint tangents. The fitted-geometry adapter reduces only proved line-equivalent quadratics, using the
Bezier hull/endpoint properties and exact dyadic arithmetic. It preserves rendered geometry and retains curved or
overshooting segments; no pixel-count tuning or tolerance flattening is introduced. The original core's unsupported
quadratic case stays independently tested. Verification passes through the separated Interface: independent
curve/profile and predicate captures, the composed 60,164-pair Mono oracle, 81 exact native/WASM cases across all four
output depths, and browser profile switching with saved settings. Gamma/threshold/depth independence and Source fallback
policies pass native checks. Optical assessment of the broader repertoire remains separate.

**Method-specific runtime adapters, 2026-11-01:** the
[kerning interface](../../designs/text-layout/contextual-spacing-and-healing.md#interchangeable-kerning-methods) now
separates completed pair-table selection from each method's preparation and solve. Source remains the exact default;
TypeFacet retains its original predicate and smallest-admissible integer search. Hu/Hersch explicitly adopts the full
fitted-outline, fixed-alphabet density-conserving experiment as a distinct analytic adapter. Its auxiliary calibration
captures use the same pipeline without enlarging output glyphs or their pair-shaping domain. This avoids both
text-derived density targets and accidental cross-script shaping requirements.

FontForge-derived spacing is a separate source-relative method, with its own strength blend, native band estimator and
integer placement. It preserves source pair separation rather than Hu/Hersch's shared class density. Missing reference
classes or undefined measurements retain Source; valid zero replacements remain distinct from abstention. CounterSpace
remains a future runtime port because its nonlinear score search and numerical calibration are not equivalent to either
analytic adapter. These ports add selectable calculations without changing glyph geometry. Earlier Literata wall-model
concerns and broader optical acceptance remain pending; reference parity alone cannot establish their resolution.

Independent native checks agree with retained Hu wall, target and placement captures and FontForge C envelope fixtures.
Source identity, the existing TypeFacet profile/origin oracle, calibration-domain isolation and atomic pair replacement
remain intact. This establishes mechanical port fidelity, not improved reading rhythm or optical acceptance.

Final scalar Node and browser SIMD packages each match 110 native render cases and eight byte-identical exports. The new
Hu/Hersch and FontForge WASM matrix covers 16 px at 1/2/3/4-bit depths. All 233 web unit tests and two browser lifecycle
checks pass, including Mono/Gray switching and saved reloads with the new methods. Production build and license checks
pass; rebuilt `out/web` contains the tested browser WASM artifact. Evidence is under
`out/diagnostics/contextual-spacing/interchangeable-kerning/`.

Gray's certified continuous feasibility bound is conservative and materially more expensive than Mono's delivered-cell
bound in native release probes. It may choose a wider integer position when tighter clearance cannot be certified.
Browser interaction latency remains a separate assessment; native timings do not establish it.

**Fitted-wall density candidate, optical assessment pending:** the user finds touching-permitted Literata spacing
improved overall, but reports `en`, `os` and `se` as slightly too wide, with `ri`/`ig` still uneven. None of these pairs
is constrained by the bitmap overlap bound. Their continuous wall measurements and nearest-integer quantization select
the wider steps; this is not a clearance implementation failure.

The
[fitted-wall candidate](../../designs/text-layout/contextual-spacing-and-healing.md#fitted-wall-measurement-candidate)
changes measurement to retained fitted outlines while preserving the source-origin calibration rule, integer rounding
and actual-bitmap overlap protection. The touching-permitted bitmap-wall model remains the control. Its Literata
placement predictions tighten `se` and `ri` but preserve the improved `al`; `en` and `os` remain unchanged. That does
not establish equal optical gaps or resolve the reported rhythm. Centered source-relative calibration remains a separate
research proposal, because it changes the shared-target objective and widens `al` again. No such objective change is
part of this candidate.

**Touching-permitted density candidate, optical assessment pending:** the user finds the fixed-alphabet density result
better overall than the preceding shared target, but reports `al` as too loose and `ri`/`ig` as uneven in Literata
400/16, `opsz=16`. The user explicitly permits glyph pixels to touch. The
[touching-clearance candidate](../../designs/text-layout/contextual-spacing-and-healing.md#touching-clearance-candidate)
uses the same target and rounding with a shared-row non-overlap bound. Contact is allowed; occupied-cell overlap and
same-row ink-order inversion are forbidden. The strict density model remains the separate control.

`al` requests an 8 px step before clearance; the strict model emits 9 px because its baseline serif tips meet at 8 px.
The new candidate permits that contact. `ri` already rounds to 9 px before clearance, while `ig` rounds to 4 px, so this
amendment does not change them. Their remaining wall-measurement and quantization difference is pending assessment; it
must not be hidden by a pair exception or another target offset. Compare all four families and seven presets with the
vanilla browser reference at zero tracking. These diagnostics assess changed placement, not glyph shape or a new
renderer identity.

**Fixed-alphabet density comparison, optical assessment pending:** the
[density experiment](../../designs/text-layout/contextual-spacing-and-healing.md#fixed-alphabet-density-experiment)
separates the generic wall measure from its font-wide density anchor. `hu_alphabet_source_target` uses the complete
fixed alphabet's source-score mean. `hu_density_conserved` uses source steps and candidate walls to conserve the
continuous mean origin step on that fixed pair domain. Neither calibration uses supplied reading text. Both are opt-in;
the existing single-reference and source-relative modes remain controls.

The source-origin arm satisfies its continuous calibration identity across the four retained families, with source,
bitmap and fitted-outline measurement controls. Pixel rounding and the independent bitmap clearance guard can leave
emitted residuals. At Literata 400/16, `opsz=16`, its lowercase bitmap target is 2.464 px. On the held-out lowercase
Lynx preset, eligible origin-step expansion relative to source falls from 0.706 px under the preceding source-`nn` model
to 0.123 px. That is a layout measurement, not a perceived-spacing verdict. `ip` remains at a 4 px origin step while
`pe` changes from 11 to 10 px; their residual score difference remains a native-size assessment case.

The numeral budget exposes a limit imposed by the retained policy: Literata's mean minimum permitted bitmap step is
8.380 px across the fixed digit domain, above its 8.274 px source mean. Exact emitted source-width conservation is
infeasible there under the strict no-touch/facing-order guard. The guard is retained and the residual is disclosed. Word
spacing retains its existing placement policy. Changes in letter density and remaining constrained pairs must be judged
alongside the vanilla browser-font reference at zero tracking.

The rebuilt comparison under `out/diagnostics/contextual-spacing/density-conservation/` retains four families at 16 px,
all seven presets and zoom. It compares the preceding shared target with the fixed-alphabet density candidate. Captured
glyphs and the preceding control's numerical placements remain unchanged. Source-only conservation, independent
bitmap-contact checks and browser layout parity establish mechanics; optical acceptance remains open.

**Shared-target density, candidate assessment pending:** the Literata 400/16 bitmap `nn` reference has a Hu score of
3.625 px, compared with 3.166 px from source outlines and metrics. Across the lowercase Lynx preset, the source mean
score is 2.805 px and the raster-reference shared result is 3.628 px. The user's preferred −1 px tracking brings the
mean to 2.628 px but introduces cell contacts in 56 distinct pairs because deliberate tracking follows clearance. This
is evidence of an overly loose density anchor in this case, not a universal one-pixel correction.

The
[stem/curve source-only experiment](../../designs/text-layout/contextual-spacing-and-healing.md#stemcurve-reference-experiment)
does not pass its integration gate. Its provisional classifier confuses flat portions of round shapes with stems and
mistakes the stem below a shoulder for a simple facing stem. All available standards reconstruct their source spacing,
but that does not validate feature classification. Source-only changes include a substantial contraction of Literata
`rn`; Roboto and Roboto Flex cannot supply all six expected standards with that classifier. Coverage and apparent mean
improvement also depend on body-window policy and unsupported-pair fallback. No new spacing mode or preview default is
adopted from this experiment. Whole-feature classification remains unresolved.

The
[source-designed shared-density candidate](../../designs/text-layout/contextual-spacing-and-healing.md#source-designed-shared-density-candidate)
uses full source `nn`/`HH` metrics and outlines for target calibration while measuring delivered bitmap walls and
preserving the existing rounding and clearance solve. It retains the raster-reference control. No requested-text
average, negative tracking default or word-spacing correction selects the target. Source references remain imperfect
proxies for overall text density, and other families can move in the opposite direction. Assess the new density at
native size against the browser reference and earlier reported pairs before adoption.

The rebuilt comparison is retained under `out/diagnostics/contextual-spacing/source-density/`: four families at 16 px,
all seven presets, original-font browser reference and zoom, with zero deliberate tracking. The Literata lowercase
target changes from 3.625 to 3.166 px; its delivered Lynx mean changes from 3.628 to 3.219 px. Source reference targets
move Roboto and Roboto Flex outward, so a universal tightening is not claimed. All 183 experiment tests and 800
Python/browser layout fixtures pass. Independent full-cell checks find no contacts in 11,332 eligible pair/preservation
policy checks across the four families, including clearance-limited placements. Captured glyphs and retained control
placement tables are unchanged. These are mechanical findings; optical acceptance remains pending.

A dedicated two-mode reading comparison under `out/diagnostics/contextual-spacing/hu-two-modes/` places
`hu_source_relative` and `hu_hersch` side by side at the same controls. It starts with `ip`/`pe` and retains all seven
presets, the four-family full-page scope and the native browser reference with zoom. The model selector controls the
pair inspector; the columns retain their assigned models. Existing solver tables and delivered glyphs are unchanged. For
Literata 400/16, full-strength `ip`/`pe` origin steps are 5/10 px in source-relative mode and 5/11 px with the shared
target. This exposes the reported target/rounding discrepancy for assessment without adopting either result as optically
accepted.

The earlier inline projection accidentally removed all seven presets to meet its document-size limit, although the full
offline page retained them. The corrected inline exporter preserves every supplied preset, all three selected comparison
models and the vanilla-spacing Gray reference through lossless packing. Oversized exports fail explicitly. Browser
verification covers every preset/model combination and exact restored numeric data; the underlying spacing and raster
results are unchanged. This preview regression and its verification are retained under
`out/diagnostics/contextual-spacing/inline-presets/`.

**CounterSpace comparison, assessment pending:** the isolated adapter retains the upstream measurement implementation
and fits font-wide parameters on delivered reference bitmap cells at maintained full metric placements. Delivered cells
are replicated into common analysis coordinates for both fitting and scoring. The earlier source-raster calibration
remains a control; a delivered-calibration first-crossing variant isolates calibration from the candidate's closest
feasible whole-pixel score search. Blending and the independent clearance guard retain actual score residuals and
optimizer status. The
[candidate design](../../designs/text-layout/contextual-spacing-and-healing.md#counterspace-candidate) owns its
adaptations and boundaries. Assess the reported Literata `jo`, `yd`, `le`, `pi`, `ip`, `te`, `tp`, `OE`, `OR` pairs with
surrounding text and held-out words; a reference-code implementation does not establish optical improvement. The
retained implementation supplies an executable comparison without changing maintained glyph production.

**Source-calibrated CounterSpace numerical limitation:** in the four-family 16 px/400 scope below, the upstream
optimizer reports convergence for Literata, Roboto and Roboto Flex, but a failed line search for Source Sans 3. Its
finite returned parameters remain diagnostic and are labeled as provisional in the comparison. Optimizer convergence
alone does not establish a good fit or optical acceptance for the other families. Non-ASCII and punctuation pairs
currently retain metric placement under the adapter's explicit ASCII letter/digit scope.

**CounterSpace storage-bounds defect, corrected; optical assessment pending:** the captured `n` contains a transparent
top row. Treating its storage rectangle as ink bounds extends the lowercase reference window above the actual body. In
Literata 16 px/400, `opsz=16`, the wide void between the `bd` ascender stems in that row contributes about 34% of its
weighted score, despite a mostly 1 px body gap versus 4 px in `du`. Tight nonzero bounds preserve every absolute ink
cell and all fitted parameters while changing `bd` from a 9 to an 11 px origin step; `du` remains 11 px. Independent
transparent margins now leave fitting, scores and placement unchanged. The backend derives analysis dimensions from
nonzero ink rather than storage margins. Padding invariance is a mechanical requirement; broader optical acceptance
remains pending. Source-calibrated comparison scores can also change because its delivered scoring shares this corrected
backend. Displayed glyph images and the four earlier models remain intact.

**CounterSpace intensity mismatch, corrected; optical assessment pending:** upstream smoothing emits 0–1 masks but its
tensorfont concavity operation reads contours at cutoff 30. A private intensity adapter scales normalized masks into the
original operation's byte domain and restores their normalized range and rendering metadata afterward. Fitting,
reference targets and delivered scoring all use the same corrected measurement; byte-scale input and the signed-jump
cavity classifier retain their original behavior. Captured glyph forms remain unchanged.

At Literata 16 px/400, `opsz=16`, normal refitting widens `ff` from a 6 to an 8 px origin step after this repair, while
`cc` and `zz` retain 8 and 9 px. The changed reference measurement also selects 10 rather than 11 px for `bd`; `du`
remains 11 px. This placement change needs renewed optical assessment, rather than a pair-specific preservation rule.
The `c` right face and both `z` faces request no cavity reduction under the current classifier, so their crowded-pair
concern remains a separate pending assessment. Fixed-weight diagnostics using absolute jumps or face blending without a
discontinuity gate leave `cc` and `zz` unchanged and tighten `ff` back to 7 px through their changed reference target;
neither is adopted. No repeated-letter exception or global target increase is introduced. Source Sans 3's
source-calibrated intensity-corrected fit converges, while its delivered fit remains non-converged and provisional.

**Measurement defect:** in Literata 16 px/400, remaining axes at defaults, selective/terminal/overlay Mono, the
FontForge-calibrated `01` and `12` scores approach the shared `00` target despite very different visible whitespace. The
`12` baseline bands carry about 93% of the estimator's weight; broad whitespace above contributes little. Tightened `01`
also acquires diagonal ink contacts. This demonstrates that changing target density alone does not establish the
requested balance. The inverse-square estimator remains useful as an explicit comparison, rather than the candidate.

**Filtered-wall comparison:** Hu's filtered-area measurement gives the whole class height a uniform contribution after
concavity filtering. The source references use the same measurement, and a separate whole-bitmap clearance bound reports
when unchanged serifs prevent reaching the ideal target. The bounded adaptation's numerical integration, reference
windows, case/numeral calibration and strict Mono clearance policy are specified in the design. They do not reproduce
the complete published perceptual model. The experimental `00` reference needs separate optical assessment.

**Confirmed comparison-input mismatch:** earlier spacing captures omitted Literata's `opsz`, selecting the font's
12-point default despite a 16 px rendering size. The current `diagonal-shape-06` renderer reproduced their narrow `t`;
explicit `opsz=16` invokes the approved source-shape correction and restores its two-column body. The refreshed Literata
spacing comparison uses `wght=400, opsz=16`, matching the approved instance. The adapter also inherited generic scan
defaults with font instructions and stubs disabled; those selected the base scanner despite the requested terminal
pipeline. Working captures now explicitly enable both controls, matching the approved Mono settings. Earlier
default-axis results remain distinct input evidence, rather than evidence of a stale renderer or a new fitting
regression. Other families retain their captured instances. Inspect the active axes before comparing glyph forms or
density across these pages.

**Pending placement assessment:** the four-family comparison covers Roboto, Roboto Flex, Source Sans 3 and Literata at
16 px/400, Literata `opsz=16` and other axes at defaults, selective/terminal/overlay Mono. Inspect `01`/`12`/`23`, `re`
with surrounding letters, repeated-letter rhythm, capital/lowercase transitions and open cavities. Distinguish
clearance-limited placements from rounded solutions, and compare source-relative rhythm at native size. Equal filtered
area does not establish equal perceived distance. Unsupported classes and unavailable references retain metric placement
with reasons; auxiliary source references leave output repertoire unchanged. Broader sizes/axes, Gray and optical
acceptance remain open.

**Pending source-preserving comparison assessment:** at 16 px and weight 400, remaining axes at font defaults, the
selective/terminal/overlay Mono experiment changes pair placements across Roboto, Roboto Flex, Source Sans 3 and
Literata. For example, `,A` tightens by one pixel in Roboto and Source Sans 3, while `,0` expands by one pixel in
Literata and Roboto Flex. Inspect punctuation rhythm, neighboring forms and word boundaries in browser comparisons
before judging either direction. Glyph images are unchanged; spacing differences alone demonstrate neither improvement
nor regression.

**Source-preserving numeric limitation:** in the same 16 px/400 scope, `12` tightens by one pixel in Roboto and Roboto
Flex when tabular preservation is disabled. Source Sans 3 and proportional-digit Literata calculate subpixel corrections
that round to unchanged placement. Preserving tabular spacing retains the prior metric steps; inspect numeric rhythm and
the alignment tradeoff before judging the optical option. The control changes pair placement, retaining numeral forms
and finalized advances. Roboto's source estimated separations for `12` and `23` remain about 4.30 and 2.59 px, so
retaining those targets cannot unify the two pairs' estimated whitespace.

**Bounded mechanical parity:** synthetic curves, cavities, marks and boundary cases match independently built pinned
FontForge envelopes and estimates. The four-family source sample also matches integer envelopes and usable pair
estimates at both band settings; continuous curve bounds agree within `1e-7` design units. This comparison pins separate
floating-point operations rather than arbitrary platform binary behavior.

Broader size/weight/axis and pipeline comparisons, real fixed-pitch controls, Gray boundary selection and browser/native
resource limits still gate adoption. Mechanical endpoint, deterministic preview/full-domain and placement checks do not
settle optical quality. Texture healing is deferred; saved-tracking migration and production integration remain separate
decisions.

### Tracking and word separation

[FreeType metrics](https://freetype.org/freetype2/docs/glyphs/glyphs-3.html) and
[BMFont](https://www.angelcode.com/products/bmfont/doc/file_format.html) separate images, advances and pair adjustments;
Hersch §5 explains why fractional movement changes raster phase. The explicit pipeline adds signed whole-pixel tracking
uniformly to finalized advances, including spaces and the final glyph, in Mono and Gray. Negative tracking can narrow
word gaps or overlap glyphs; zero is identity, with no clearance floor or word-gap refund.

Export bakes tracking into advances and retains pair adjustments once. The
[tracking contract](../../../crates/generator/API.md#tracking-policy) owns ranges, historical protected behavior and
adapter representability. Static comparisons retain zero unless requested. This is not optical rekerning or acceptance
of a chosen spacing value.

### Source-kerning inspection

Authentic source pair adjustments are exposed independently of experimental placement through the
[WASM inspection interface](../../../crates/wasm/README.md#kerning-pairs).

### Preview display scaling

Fractional browser composition can make equal native stems appear unequal.
[devicePixelRatio](https://developer.mozilla.org/en-US/docs/Web/API/Window/devicePixelRatio),
[CSS image rendering](https://drafts.csswg.org/css-images-3/#the-image-rendering) and
[Chromium canvas snapping](https://chromium.googlesource.com/chromium/src/+/main/third_party/blink/renderer/core/paint/html_canvas_painter.cc)
ground the optional [display policy](../../../apps/web/src/app/renderer/display-scaling.ts): align origins/extents and
show native pixels as equal integer blocks of physical pixels. Controlled fractional composition reproduces the
artifact; the user's specific cause and other compositors remain unassessed.

## Earlier controls and remaining findings

These findings retain their captured policies. Retired candidates and isolated comparisons below do not describe the
current default or establish new optical approvals.

### Symmetry and grid placement

At Roboto 400/14, `wdth=100`, Mono threshold 128, preceding baseline/candidate native/browser outputs agree. **Confirmed
former imbalance:** nearly equal source `A` legs became about 0.98/1.22 px; source apex offset about −0.007 px grew to
−0.383 px upstream and −0.516 px in the project fit. Different prepared slopes and independent width rounding amplified
it. Source slopes alone could not apply one leg at 14–16 px within movement bounds; a source-endpoint experiment
restored the relationship at 13–20 px while accepting fewer constraints elsewhere. Ownership/fallback remained
unresolved.

**Pending phase findings:** diagnostic `o` centering from 3.90625 to 4 px and `v` translation by 0.125 px restored
binary symmetry at that coordinate without proving a general placement rule.
[Hersch](../../references/papers/1993-hersch/paper.md) explains phase sensitivity;
[Shamir](../../references/papers/2003-shamir/paper.md) grounds ownership/conflict resolution. Neither supplies a
glyph-specific mirror target.

#### Vertical-only candidate findings

Retired source-X fitting corrected the `A` apex displacement to about −0.008 px at 14 px and retained the relationship
at 13/15/16/18/20 px. This was geometric correction, not complete optical acceptance. At 14 px, `o` became
binary-symmetric; source-centered `v` stayed asymmetric with a dropout terminal pixel. Phase/weight questions were not
resolved by forcing mirrors or centering witnesses.

#### Native-coverage A asymmetry: overlap coverage and phase

**Confirmed superseded-raster limitation:** Roboto 400/14 `A`, `wdth=100`, threshold 128, had one unequal below-crossbar
pixel pair despite source X, matched Y and no dropout. Three same-winding overlapping contours produce Zeno coverage
133/96. Independent filled-union clipping/integration gives about 113.88/81.07; equivalent-union raster gives 113/81 and
removes the extra pixel.

The source center is 4.578125 versus bitmap axis 4.5 px. A diagnostic −0.078125 px shift also hides the pixel but
changes placement and conceals the overlap issue. Union coverage and other checked sizes remain asymmetric. Source,
outline, coverage and binary symmetry differ. This motivated
[FreeType overlap mitigation](https://freetype.org/freetype2/docs/reference/ft2-outline_processing.html#ft_outline_xxx),
not a centering rule.

#### Overlap-aware raster investigation

The historical experiment adapted
[FreeType's overlap raster](https://github.com/freetype/freetype/blob/57617782464411201ce7bbc93b086c1b4d7d84a5/src/smooth/ftsmooth.c#L317-L436):
scale an already fitted outline 4×, reduce on the native grid with per-contribution rounding/saturation, threshold once,
then apply original-outline dropout once. One-final-round averaging was a diagnostic alternative, not FreeType parity.
Neither changed fitting size, origin or metrics. Integer-aligned tiles bounded temporary coverage storage, each
receiving the full path to preserve winding contributions.

For 14 px `A`, reductions gave 115/86 or 115/85 versus 133/96, mitigating the extra pixel. **Residual limitation:**
duplicated contours still changed coverage (an identical rectangle totaled 734 versus 859 in one-round 4× coverage).
Opposite-winding disjoint strips could cancel within one native pixel; oversampling separated them. Non-overlapping
paths also changed quantization. Finite oversampling did not establish filled-set invariance.

The five-family 1,900-glyph sweep found no increased component counts, but Source Sans 3 400/14 `!` connected dot/body
at coverage 128 and 400/16 `[` changed three components to one. Mark clearance, weight, joins and counters remained
pending independently of counts. Relevant witnesses did not set the overlap flag.

[FontTools overlap removal](https://fonttools.readthedocs.io/en/latest/ttLib/removeOverlaps.html) and
[Skia Simplify](https://github.com/google/skia/blob/main/include/pathops/SkPathOps.h#L52-L65) were alternatives for a
temporary filled raster path, requiring hole/component preservation, failure handling and dependency assessment.
Rewriting fonts can alter hints/bearings; intersection removal alone misses disjoint signed-area cancellation. Native
Mono scan conversion supersedes this coverage experiment.

#### Terminal stubs and dropout

The former threshold/dropout adaptation excluded caps closing before the next pixel-center scan line using actual arc
continuation/extrema, following
[SCANTYPE mode 5](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#scantype) and the
[FreeType recognizer](https://github.com/freetype/freetype/blob/57617782464411201ce7bbc93b086c1b4d7d84a5/src/raster/ftraster.c#L2206-L2242).
It did not reproduce TrueType center fill or overshoot exceptions and is not current scanner policy.

**Confirmed historical terminal defect:** default Roboto Flex 400/16 `x` had equal source/interpreter terminal heights
at 8.21875 px, but rescue promoted left-cap coverage 34/255 to ink and added one arm's row. Exclusion removed it and
analogous additions at 14/18/20 px. **Pending:** Literata 400, matching optical size, `E` at 14/16/18 px and `@` at 14
px opened small terminal white regions without principal-stroke breaks. Serif attachment, shoulder balance and counter
openness were unassessed. Tiny marks could disappear when all rescues were stubs; complex contours could exhaust bounded
work rather than bypass the rule.

#### Binary stem weight and source phase

**Confirmed source-X/binary-coverage defect:** Roboto 400/14, `wdth=100`, threshold 128, delivered two-column `m`
middle, `u` right and `t` stems against one-column neighbors. All `m` source stems are 1.265625 px yet rasterize
one/two/one. Source/candidate X match; dropout/overlaps do not explain the straight spans. Adjacent coverage examples
are 128/196 (`m`), 132/196 (`u`) and 148/176 (`t`).

[Hersch §§5–6](../../references/papers/1993-hersch/paper.md#5-basic-grid-constraints) and
[ttfautohint](https://freetype.org/ttfautohint/doc/ttfautohint.html#smooth-hinting) explain one/two-column phase changes
for fractional widths. The 4× raster added four `m` pixels at an analytic half-coverage edge but left `u`/`t` unchanged;
one-final-round averaging retained the doubling. Overlap removal, tie adjustment or thickening normal neighbors did not
resolve the full defect.

##### Main-page source-stem calibration

Earlier captures chose one global family/size weight so source `H I l` body sections fit within one pixel. This
controlled common inputs, not every serif/join/diagonal. The current
[configuration](../../../apps/web/scripts/landing-samples/main-page.json) supersedes calibration. Earlier native
converter differences remain **pending weight/continuity assessment**:

| Family/size      | Earlier axes              | Converter                    | Witness                     |
| ---------------- | ------------------------- | ---------------------------- | --------------------------- |
| Roboto 12        | `wght=367.07`, `wdth=100` | pdfontconv, Tophat, Adafruit | `H` has one/two-pixel runs. |
| Roboto Italic 12 | `wght=372.63`, `wdth=100` | pdfontconv, Tophat           | `H` has one/two-pixel runs. |
| Roboto Italic 20 | `wght=253.69`, `wdth=100` | pdfontconv, Tophat, LVGL     | `H` has one/two-pixel runs. |
| Literata 16      | `wght=252.22`, `opsz=16`  | pdfontconv, Tophat           | `H I` have two-pixel runs.  |

#### Coupled width geometry: research direction

[Hobby](../../references/papers/1993-hobby/README.md) motivated source-normal widths, shared relative errors and
whitespace features rather than orientation-specific fixes. The
[equation audit](../../references/papers/1993-hobby/audit.md) and
[prototype](../../../experiments/hobby_fitting/README.md) retain the original research. Sampled curve strain was a
project adaptation; normals alone allowed excessive movement. Real recognition, integer targets, ownership and
center-fill compatibility required further validation. Later adopted slices do not imply a general solution for all
curves, joins and counters.

#### Upstream Mono assessment

**Confirmed existing control imbalance:** Roboto 400/14, `wdth=100`, hints first retained one/two/one `m`, one/two `u`
and two-column `t`; italic `m` retained one/one/two. Automatic fitting restored equal regular stems but made `A` legs
one/two at Y=4–6; `v` stayed two/one. Neither justified per-glyph engine selection. Skrifa 0.48.0/HarfRust 0.14.0
controls reproduced earlier automatic pixels; upgrading dependencies alone was not the remedy. Commands belong to the
[comparison tool](../../../experiments/stem_policy_comparison/README.md). Current selective straight-span findings are
recorded under native scan conversion above.

### Compact marks and stem ownership

The earlier compact-mark experiment assigned detached convex quadratic contours independent dimensions/clearance,
grounded in [Microsoft dot values](https://learn.microsoft.com/en-us/typography/truetype/from-typeface-to-font-file),
[Google Fonts dot guidance](https://googlefonts.github.io/how-to-hint-variable-fonts/),
[Shamir §3](../../references/papers/2003-shamir/paper.md) and
[FreeType widths](https://freetype.org/autohinting/widths.html). It was superseded by now-retired source-X fitting and
is not a current mark owner or one-pixel floor. Balance, tangency and clearance across `! . : ; ? i j` remain pending;
earlier assessment does not approve later geometry. Current body/mark positioning belongs to
[x-height alignment](#source-defined-x-height-alignment).

### Remaining stroke balance

The earlier [joint/smooth-curve candidate](../../hobby-fitting.md#joint-placement-and-smooth-curve-continuation)
retained native coordinates/layout. Its Roboto 400/16, `wdth=100`, Mono, hints-on findings remain scoped questions:

| Feature | Change                                                             | Pending question                                                         |
| ------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------ |
| `s`     | Ink 29→25; frame 7→8 px.                                           | Lower bowl, terminals, continuity and spacing of the lighter/wider form. |
| `x`     | Width about 0.89–0.92→1.11–1.15 px; ink 18→23; symmetric crossing. | Weight, half-pixel phase and side-bearing balance.                       |
| `S`     | Ink 32→26; frame 8→10 px.                                          | Contrast, terminals, openings and spacing.                               |
| `X`     | Phase about +0.5 px; mean width 1.49→1.18 px; ink 28→32.           | Crossing, arm and side-bearing balance.                                  |

Default `2` retained divergent borders (47.24°/43.61°) and a heavy lower staircase: fixed curve-incident endpoints
conflicted with grid/parallelism constraints, motivating attached-diagonal continuation.

**Confirmed excluded regressions:** free-Y broke Source Sans 400/14 `h` and 300/12 `m`; retained-Y broke 300/14 `h` and
400/14 `m`; upright-X pins still broke 300/12 `h`, in both hint modes. The isolated candidate abstained on
source-vertical mixed outlines, preserving those attachments and leaving `c 5 G J U` unchanged. Later eligibility does
not erase those regression controls or the unresolved moving-join problem.

### Attached diagonal consistency

The [attached model](../../hobby-fitting.md#attached-diagonal-and-curve-constraints) shares straight/curve variables
with Y, upright X anchors and layout retained. Sharp corners may rotate without reversing orientation; curve joins
retain signed cross (zero at source-smooth joins), with curvature/tangent inequalities protecting bowls.

**Scoped visual acceptance:** Roboto 400/16, `wdth=100`, hints on, `2` was accepted on 2026-10-21 in the
[comparison](https://solitaire.taile005dc.ts.net:8909/). Ink fell 30→26 with a thinner continuous staircase and
connected bowl/baseline. Only that default `2` is accepted. **Pending:** default `5` redistributes stem/bowl/top-bar ink
without changing its total; 14 px `2` thins, the 300/12 control stays unchanged, and Source Sans 400/16 `v`
redistributes terminal/apex ink. Broader `2 5 V v W w X x Y y S` cases require their own weight, join and spacing
review.

### Combined text assessment

The [combined comparison](https://solitaire.taile005dc.ts.net:8910/) retains identical advances/pair placements against
its width-only control. Inspected Roboto 300/12/16, 400/12/14/16/20 and 700/12/16 hints on, plus 400/700 at 16 px hints
off, and Source Sans 300/12, 400/14/16 and 700/14 support retained attachments/readability without a demonstrated new
break or collision. This is a bounded observation, not full-matrix approval.

| Scope                              | Pending tradeoff                                                                   |
| ---------------------------------- | ---------------------------------------------------------------------------------- |
| Roboto 400/16 `x X`, hints on/off  | Heavier symmetric crossing and changed placement.                                  |
| Roboto 400/20 `s`, hints on        | Flatter/squarer upper shoulder.                                                    |
| Roboto 700/12 `S`, hints on        | Wider form; ink 37→42; terminal/opening contrast.                                  |
| Source Sans 700/14 `s`, both modes | Pinched upper aperture enclosing one white pixel under four-neighbor connectivity. |

Roboto 300/16 `5` loses an enclosed white pixel but retains an open connected source-like lower bowl; default `5` keeps
its attachment, with weight still under assessment. Source Sans 300/12 stays unchanged. The 386 changed bitmaps across
6,840 cases and unchanged ink-component counts establish scope only; 18/24 px and remaining combinations stay pending.

### Source Sans crossing balance

The [source assessment](../../hobby-fitting.md#source-contrast-and-crossing-assessment) finds small real arm contrast:
Source Sans 400/16 `x` widths about 1.125/1.186 px and `X` about 1.185/1.245 px, not exact reflection.

**Confirmed unresolved fitting/raster imbalance:** default 16 px `x` gains an upper-right row despite equal terminal
heights and approximately preserved source contrast; it predates the combined candidate. Restoring automatic Y in a
causality control removes that row but leaves unequal terminal ink. At 14 px the geometrically thinner arm has a
two-pixel lower terminal against one on the other; staircase significance remains pending. The crowded 12 px `X`
crossing is inherited; 16/20 px separation equalization trades away source contrast without eliminating all staircase
asymmetry.

**Confirmed representation limit:** captured collinear quadratics make attached fitting abstain on `x` at 14/16/20 px
and `X` at 12/14 px, although unrounded 16 px `x` source curves have nonzero curvature (maximum discrepancy about 0.013
px). Weakening the gate cannot recover lost information. Retain unrounded features while keeping delivered
rounding/native coordinates authoritative.

The [curved continuation](../../hobby-fitting.md#curved-crossing-prototype) supplies an isolated X solve with finite
source-relative reflection/width terms, retained Y/layout and quadratic attachments. A separate-hook fork is not a
common four-arm crossing. **Pending:** default Source Sans 400/16 `x` loses the isolated row but retains unequal
terminal footprints; `X` changes crossing/terminal ink and widens its extent. The
[comparison](https://solitaire.taile005dc.ts.net:8912/) does not establish optical acceptance by itself.

### Terminal reference heights

The [terminal model](../../hobby-fitting.md#terminal-reference-height-constraints) holds recognized source-horizontal
caps at automatic/native heights inside the width solve, retaining X at source-vertical attachments. Unsupported or
already correct geometry retains the preceding result.

**Confirmed placement correction:** default Source Sans 400/16, both hint modes, removes two below-baseline `A` pixels
and `y`'s extra upper-left row, retaining recognized feet at Y=0 and caps at Y=8. This is a constrained solve, not
bitmap repair. Default `x X` stay unchanged. `K` loses one upper-tip pixel while retaining top ink height; neighboring
weight and attachment assessment remains pending.

**Confirmed certificate correction; optical assessment pending:** at default axes, Roboto Flex Regular 16 px `N` has
disjoint collinear segment hulls after hinting flattens two quadratic attachments. Edge-normal separation alone could
not certify their longitudinal gaps, preventing the existing width correction. The
[exact hull-box separation proof](../../hobby-fitting.md#border-interval-coverage-study) now includes segment and point
hulls, retaining curve commands, uncertain-contact rejection and the remaining fitting guards. The newly eligible
terminal-only fallback exposed a whole-stroke limitation: its curved joins stayed fixed and the delivered middle
staircase remained heavy. A separate existing Roboto Flex `V` imbalance came from individually fitted legs without a
common reflection phase, amplified at the upper right by stub rescue.

The [shared-placement model](../../hobby-fitting.md#shared-stroke-placement) now moves eligible curved attachments with
their straight borders, retaining upright X, preceding Y and the original movement bound. Parallel borders may rotate
together while source-relative width terms retain contrast; a hard integer width no longer makes an otherwise feasible
attached solve fail. Source-certified approximately reflected arms share a geometric frame phase with source mismatch
retained in the objective. The preceding terminal, integer-grid and source-shape sequences remain historical replay
authorities.

**Pending optical assessment:** Roboto Flex Regular at default axes, 16 px, `N V` changes whole-stroke placement and
weight. Inspect middle staircase weight, joins, cap attachments, tip balance and retained source contrast. Nearby
sizes/axes and newly eligible outlines in other families remain pending; phase and width checks do not establish optical
acceptance.

The rebuilt app confirms visible thinning through `N`'s middle staircase and changed `V` stepping/tip placement; neither
observation alone establishes retained optical weight. The isolated 36-cell/four-font sweep changes 37 of 444 outlines
and 28 delivered bitmaps, retaining advances. Its additional letters, numerals and punctuation remain pending assessment
of contrast, joins and placement. Mechanical validation covers bounded geometry, source-mismatch retention through
reflection solving/rounding, historical replay, native/WASM parity and the diagonal-off identity path.

**Pending:** `*` redistributes arm ink with a new diagonal tip/center contact; the grave accent widens into a horizontal
step. Source Sans 400/14 `A y` geometry changes leave bitmaps unchanged, with unequal `A` foot stepping still an
existing concern. At 20 px `A` changes while `y` does not. Roboto 400/16 hints on stays unchanged; hints-off
terminal/diagonal changes and broader weights/sizes remain unassessed.

**Adoption approval, 2026-10-21:** the [terminal comparison](https://solitaire.taile005dc.ts.net:8913/) was approved for
the reviewed sequence, superseding prototype-only status without resolving unrelated curve/aperture findings. The
[adoption record](../../hobby-fitting.md#approved-fitting-sequence-adoption) owns implementation/verification.

### Native adoption verification

Adoption reproduced the approved 72-cell, 6,840-case Roboto/Source Sans 3 comparison over weights 300/400/700, sizes
12/14/16/18/20/24 and both hint modes. **Accepted delivery deviations:** Roboto 300/14 `x` and Source Sans 3 300/18 `x`,
both modes, differ only at 26.6 outline rounding with identical pixels/frames. Roboto 300/18 hints-off `~` retains the
preceding outline after bounded initialization fails, also matching reviewed delivery; that numerical fallback remains a
geometry follow-up, not a glyph exception. Evidence: `out/diagnostics/approved-fitting-native/`.

Native/WASM/export parity supports delivery, not closure of pending optical findings. A historical concurrent-run host
measurement of the adopted 16 px weight-400 pangram was about 3.6–4.4 s for Roboto and 6.5–6.8 s for Source Sans 3,
versus 26–69 ms without fitting. This is a recorded performance limitation, not a current-build benchmark. Measurements
remain in `wasm-runtime-final.json` under the same evidence directory; current identities/default selection belong to
the [revision index](README.md).
